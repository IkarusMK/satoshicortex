#!/bin/sh
# Kommt man ueber die .onion wirklich an? -- mit echtem Tor und echtem bitcoind.
#
# DER BEFUND VOM 17.09.2026. Bis 0.62.0 legten bitcoind und LND ihre
# Onion-Dienste selbst an, ueber Tors Steuerport und ohne Ziel. Tor setzte
# 127.0.0.1 ein -- seinen EIGENEN Container, in dem niemand horcht. Die
# Adressen standen im Netz, und niemand kam je an ihnen an. Aufgefallen ist es
# nicht, weil es nie jemand von aussen gemessen hat.
#
# Genau das tut dieses Skript, im Stapel-Test der CI:
#
#   1. torrc und bitcoind.conf entstehen aus dem Code der Anwendung -- nicht
#      von Hand. Geprueft wird, was ausgeliefert wird.
#   2. Tors Steuerport ist zu.
#   3. Die Uebernahme eines Schluessels von 0.62.0 ergibt bei ECHTEM Tor
#      dieselbe Adresse.
#   4. Ein zweites, frisches Tor misst ueber das Tor-Netz: Wachturm und
#      Lightning (an einer Attrappe auf LNDs fester Adresse) und bitcoind mit
#      echtem Bitcoin-Handschlag.
#   5. Und die Gegenprobe: ein Dienst, hinter dem niemand horcht, meldet sich
#      als "abgelehnt" -- der Zustand von 0.62.0. Ohne die Gegenprobe haette
#      eine Messung, die immer "erreichbar" sagt, genauso bestanden.
#      Erkennbar ist das nur mit Tors ExtendedErrors: ohne sie meldet Tor
#      den Fall als "allgemeinen Fehler" (am 17.09.2026 hier gemessen) und
#      er sieht aus wie ein Weg, der nicht zustande kam.
#
#   onion_stapeltest.sh <DATA_FAST auf dem Host>
set -eu

FAST="${1:?Aufruf: onion_stapeltest.sh <DATA_FAST>}"
PRAEFIX="${NETWORK_PREFIX:-10.83.33}"
NETZ="satcortex-netz"
APP_ABBILD="ghcr.io/ikarusmk/satcortex:latest"
TOR_ABBILD="ghcr.io/ikarusmk/satcortex-tor:latest"

log() { printf '\n── %s\n' "$*"; }
py() { docker compose exec -T app python -c "$1"; }

# Die beiden Hilfscontainer gehoeren nicht zur Compose. Blieben sie haengen,
# koennte "docker compose down" das Netz nicht abbauen.
trap 'docker rm -f lnd-ersatz tor-pruefer >/dev/null 2>&1 || true' EXIT

warte_auf_adressen() {
  i=0
  while [ "$i" -lt 60 ]; do
    fehlt=""
    for d in bitcoind lnd wachturm; do
      [ -s "$FAST/tor/onion-$d/hostname" ] || fehlt="$fehlt $d"
    done
    [ -z "$fehlt" ] && return 0
    i=$((i + 1)); sleep 2
  done
  echo "FEHLER: Tor hat keine Adresse hinterlegt fuer:$fehlt"
  docker compose logs tor
  return 1
}

adresse() { tr -d '\n' < "$FAST/tor/onion-$1/hostname"; }

# ---------------------------------------------------------------- 1. Tor
log "torrc aus nodeconfig.baue_tor"
py '
from satcortex import nodeconfig, onion, services, settings
konf = settings.laden()
ablage = services.Konfigurationsablage(konf.config_dir)
ablage.schreibe("tor", nodeconfig.baue_tor(onion.REIHENFOLGE, konf.netz_praefix))
ablage.gib_frei("tor")
'
grep -n "HiddenService" "$FAST/config/tor.conf"
warte_auf_adressen
for d in bitcoind lnd wachturm; do echo "$d: $(adresse "$d")"; done

# ---------------------------------------------------------------- 2. Steuerport
log "Tors Steuerport ist zu"
if docker compose exec -T tor bash -c 'exec 3<>/dev/tcp/127.0.0.1/9051' 2>/dev/null; then
  echo "FEHLER: auf 9051 horcht etwas -- der Steuerport ist offen"; exit 1
fi
echo "9051: niemand zu Hause."

# ---------------------------------------------------------------- 3. Uebernahme
# Aus Tors eigenem Schluessel wird die Datei, die LND bis 0.62.0 ablegte.
# Danach wird Tors Verzeichnis geloescht, die Anwendung uebernimmt den
# Schluessel, und Tor muss beim Start DIESELBE Adresse hinterlegen.
log "Ein Schluessel von 0.62.0 behaelt bei echtem Tor seine Adresse"
vorher=$(adresse lnd)
docker compose stop tor
py '
import base64, pathlib, shutil
from satcortex import onion, settings
konf = settings.laden()
ordner = onion.verzeichnis(konf.fast, "lnd")
roh = (ordner / onion.SCHLUESSELDATEI).read_bytes()
assert roh[:32] == onion.SCHLUESSELKOPF, roh[:32]
alt = pathlib.Path(konf.fast, *onion.DIENSTE["lnd"].alter_schluessel)
alt.write_bytes(b"ED25519-V3:" + base64.b64encode(roh[32:]))
shutil.rmtree(ordner)
assert onion.uebernimm_schluessel(konf.fast, "lnd")
'
docker compose start tor
warte_auf_adressen
nachher=$(adresse lnd)
echo "vorher:  $vorher"; echo "nachher: $nachher"
[ "$vorher" = "$nachher" ] || { echo "FEHLER: die Adresse hat sich geaendert"; exit 1; }

# ---------------------------------------------------------------- bitcoind
log "bitcoind mit der Konfiguration aus nodeconfig.baue_bitcoind"
py '
from satcortex import nodeconfig, onion, services, settings
konf = settings.laden()
ablage = services.Konfigurationsablage(konf.config_dir)
conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(
    tor_aktiv=True, onion_adresse=onion.lies_adresse(konf.fast, "bitcoind"),
    rpc_netz=konf.compose_netz,
    zugang=nodeconfig.hole_oder_erzeuge_zugang(ablage)))
ablage.schreibe("bitcoind", conf)
ablage.gib_frei("bitcoind")
'
i=0
until docker compose logs bitcoind 2>&1 | grep -q "Bound to 0.0.0.0:8334"; do
  i=$((i + 1))
  [ "$i" -lt 90 ] || { echo "FEHLER: bitcoind horcht nicht auf 8334"; docker compose logs bitcoind | tail -50; exit 1; }
  sleep 2
done
echo "bitcoind horcht auf 8334 -- dort, wohin Tor weiterreicht."

# ---------------------------------------------------------------- Attrappe fuer LND
# LND selbst braucht eine fertige Kette, bevor es Verbindungen annimmt. Fuer
# die Frage "reicht Tor bis zu LNDs Adresse durch" genuegt ein Dienst, der auf
# derselben festen Adresse dieselben Ports annimmt.
ersatz() {
  docker rm -f lnd-ersatz >/dev/null 2>&1 || true
  docker run -d --name lnd-ersatz --network "$NETZ" --ip "$PRAEFIX.12" \
    --entrypoint python "$APP_ABBILD" -c '
import socket, sys, threading
def dienen(port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(8)
    while True:
        verbindung, _ = s.accept()
        verbindung.close()
faeden = [threading.Thread(target=dienen, args=(int(p),)) for p in sys.argv[1:]]
for f in faeden:
    f.start()
for f in faeden:
    f.join()
' "$@" >/dev/null
  sleep 2
}
docker compose rm -sf lnd
ersatz 9911                # 9735 bleibt zu -- fuer die Gegenprobe

# ---------------------------------------------------------------- 4. Messen
# Ein ZWEITES Tor misst, nicht das des Knotens: so kommt die Verbindung
# wirklich von aussen. Und es laesst sich neu starten, wenn es eine .onion
# zu frueh gesucht hat -- Tor fragt dieselben Verzeichnisse sonst erst nach
# einer Viertelstunde wieder.
tor_pruefer() {
  docker rm -f tor-pruefer >/dev/null 2>&1 || true
  docker run -d --name tor-pruefer --network "$NETZ" --entrypoint tor "$TOR_ABBILD" \
    --SocksPort "0.0.0.0:9150 ExtendedErrors" --DataDirectory /tmp/tor-pruefer \
    --Log "notice stdout" >/dev/null
  i=0
  until docker logs tor-pruefer 2>&1 | grep -q "Bootstrapped 100%"; do
    i=$((i + 1))
    [ "$i" -lt 120 ] || { echo "FEHLER: das pruefende Tor kam nicht hoch"; docker logs tor-pruefer; return 1; }
    sleep 2
  done
}

messen() {   # Name Adresse Port Handschlag(True/False) Erwartung
  versuch=1
  while [ "$versuch" -le 4 ]; do
    ergebnis=$(py "
import json
from satcortex import erreichbar
print(json.dumps(erreichbar.pruefe_eine('$2', $3, ('tor-pruefer', 9150), 90, handschlag=$4, erweitert=True)))
")
    echo "$1, Versuch $versuch: $ergebnis"
    befund=$(printf '%s' "$ergebnis" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("erreichbar" if d.get("erreichbar") else (d.get("grund") or "unbekannt"))')
    if [ "$befund" = "$5" ]; then
      return 0
    fi
    case "$befund" in
      nicht_pruefbar|keine_antwort)
        # Der Weg kam nicht zustande -- kein Befund. Frisches Tor, neuer Anlauf.
        tor_pruefer; sleep 30 ;;
      *)
        echo "FEHLER: $1 -- erwartet $5, gemessen $befund"; return 1 ;;
    esac
    versuch=$((versuch + 1))
  done
  echo "FEHLER: $1 liess sich viermal nicht messen"; return 1
}

log "Ein frisches Tor misst von aussen"
tor_pruefer
# Die Dienste des Knotens muessen ihre Beschreibung erst veroeffentlichen.
sleep 90

messen "Wachturm"  "$(adresse wachturm)" 9911 False erreichbar
messen "Gegenprobe: niemand horcht auf 9735" "$(adresse lnd)" 9735 False abgelehnt
ersatz 9735 9911
messen "Lightning" "$(adresse lnd)" 9735 False erreichbar
messen "bitcoind"  "$(adresse bitcoind)" 8333 True erreichbar

log "Alle drei Onion-Dienste sind von aussen erreichbar."
