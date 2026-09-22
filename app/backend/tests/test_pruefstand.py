"""Der Pruefstand selbst -- er darf nicht am Netz haengen.

Am 10.09.2026 lief dieselbe Pruefung hier gruen und in der CI rot. Der
Unterschied war nicht der Code, sondern das Netz: auf dem Mac glueckten die
Abrufe nach GitHub, Bitstamp und zu den Nachrichtenquellen, in der CI nicht.
Eine Pruefung, deren Ergebnis vom DNS des Rechners abhaengt, prueft nicht die
Anwendung.

Diese Datei haelt die Sperre fest, damit sie nicht unbemerkt wieder faellt.
"""
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def test_beide_wege_nach_draussen_sind_zu():
    """urlopen ist der offensichtliche -- der andere ist der Oeffner mit
    eigenem Proxy, und genau den benutzt nachrichten.hole()."""
    assert urllib.request.urlopen.__name__ == "kein_urlopen"
    assert urllib.request.OpenerDirector.open.__name__ == "kein_oeffner"


@pytest.mark.parametrize("adresse", [
    "https://github.com/lightningnetwork/lnd/releases.atom",
    "https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "https://bitcoinmagazine.com/feed",
])
def test_nach_draussen_geht_nichts(adresse, netzversuche):
    with pytest.raises(urllib.error.URLError, match="Attrappe statt Leitung"):
        urllib.request.urlopen(adresse)
    assert adresse in netzversuche


@pytest.mark.parametrize("name", ["bitcoind", "lnd", "tor"])
def test_die_dienste_aus_dem_compose_scheitern_wie_im_betrieb(name):
    """Nicht mit einem eigenen Fehler, sondern mit dem, den das
    Betriebssystem schickt, wenn niemand da ist -- den fangen die Aufrufer
    ab, und genau dieser Fall gehoert geprueft."""
    with pytest.raises(urllib.error.URLError, match="kein Dienst"):
        urllib.request.urlopen(f"http://{name}:8332/")


def test_der_eigene_rechner_bleibt_erreichbar(netzversuche):
    """Zwei Testdateien starten mit gutem Grund einen echten kleinen Server
    und reden ueber einen echten Socket mit ihm. Der eigene Rechner ist
    nicht "draussen"."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Griff(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Griff)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{server.server_port}/"
        with urllib.request.urlopen(adresse, timeout=5) as antwort:
            assert antwort.read() == b"ok"
        assert adresse not in netzversuche
    finally:
        server.shutdown()


# ── Zwei Tests mit demselben Namen sind einer ──────────────────────────────
#
# Gefunden am 10.09.2026 beim Bau der PIN. In test_auth.py hiessen die
# Konto-Sperre und die PIN-Sperre beide
# "test_nach_zu_vielen_fehlversuchen_ist_zu" -- und in Python gewinnt die
# zweite Definition. Zwei Tests der Kontoanmeldung liefen damit gar nicht
# mehr, ohne dass irgendwo eine Zahl kleiner geworden waere: die Gesamtzahl
# stieg ja, weil neue dazukamen.
#
# Aufgefallen ist es nur, weil die Abdeckung von auth.py um eine Zeile fiel.
# Darauf will ich mich nicht verlassen -- fuer JavaScript prueft die CI
# doppelte Funktionsnamen seit dem 03.09.2026 aus genau demselben Grund.

def test_keine_zwei_tests_teilen_sich_einen_namen():
    import re
    doppelte = {}
    for datei in sorted(Path(__file__).parent.glob("test_*.py")):
        namen = re.findall(r"^def (test_[A-Za-z0-9_]+)",
                           datei.read_text(encoding="utf-8"), re.M)
        mehrfach = {n for n in namen if namen.count(n) > 1}
        if mehrfach:
            doppelte[datei.name] = sorted(mehrfach)
    assert not doppelte, (
        "diese Namen sind je Datei doppelt vergeben -- die zweite Definition "
        "gewinnt, die erste laeuft nie: " + repr(doppelte))


# ── Faeden, die ihren Testfall ueberleben ──────────────────────────────────
#
# Am 11.09.2026 meldete tools/pruefen.sh einmal "✗ Tests und Abdeckung" und
# lief danach sechzehnmal sauber durch. Der Fehlschlag wurde nicht
# festgehalten und war nie wieder da -- geblieben war nur eine Zahl: 608
# ungedeckte Zeilen statt 607. Eine einzelne Zeile Unterschied heisst, dass
# ein Pfad mal lief und mal nicht, also etwas Zeitabhaengiges.
#
# Am 12.09.2026 nachgemessen statt geraten: am Ende eines Laufs lebten 35
# Faeden "htlc-strom". Sie gehoerten zu 35 laengst beendeten Testfaellen.
# Dieselbe Fehlerklasse wie am 10.09.2026 beim Nachrichtenfaden -- nur dass
# dieser hier ein "while True" hat und sich deshalb gar nicht einholen liess.
#
# Ob das der Fehlschlag von damals war, ist nicht mehr feststellbar. Dass es
# ein Weg dorthin ist, schon.

def test_kein_hintergrundfaden_ueberlebt_seinen_testfall(tmp_path, monkeypatch):
    """Wer hier faellt, hat einen Dauerlaeufer ohne Haltesignal gebaut.

    Ein solcher Faden schreibt in die Ablage eines Testfalls, den es nicht
    mehr gibt -- und trifft damit die Attrappe des naechsten.
    """
    import collections
    import shutil
    import threading

    from fastapi.testclient import TestClient

    from satcortex import api, settings

    # Reichlich Platz vortaeuschen, sonst lehnt der Assistent ab -- auf einer
    # Entwicklungsmaschine liegt selten ein Terabyte herum.
    gb = 1024 ** 3
    nutzung = collections.namedtuple("Nutzung", "total used free")
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: nutzung(8000 * gb, 4000 * gb, 4000 * gb))

    vorher = {f.name for f in threading.enumerate()}

    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()
    app = api.baue_app(settings.Einstellungen(
        bulk=str(bulk), fast=str(fast), config_dir=str(tmp_path / "config")))
    client = TestClient(app)
    client.post("/api/konto/anlegen",
                json={"benutzer": "pruefer",
                      "passwort": "ein-gutes-langes-passwort"})
    # Erst ein eingerichteter Knoten startet den Dauerlaeufer.
    client.post("/api/einrichtung/abschliessen",
                json={"speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
                      "verbindungen": 80, "tor_aktiv": True})
    # Der Kaltstart -- erst er misst wirklich und stoesst dabei den
    # Dauerlaeufer an. /kennzahlen allein liest nur ab.
    client.get("/api/status")
    client.get("/api/kennzahlen")

    gestartet = {f.name for f in threading.enumerate()} - vorher
    assert "htlc-strom" in gestartet, (
        "der Dauerlaeufer lief gar nicht -- dann prueft dieser Test nichts. "
        "Wurde er umbenannt oder an eine andere Bedingung gehaengt? "
        + repr(sorted(gestartet)))

    app.state.hintergrund_stoppen(2.0)

    uebrig = sorted(f.name for f in threading.enumerate()
                    if f.name not in vorher and f.is_alive())
    assert not uebrig, (
        "diese Faeden laufen nach dem Einholen weiter -- sie beachten das "
        "Haltesignal nicht: " + repr(uebrig))


# ── Die Abhaengigkeitssperre (Befund 22.09.2026) ───────────────────────────

def test_die_sperre_kennt_jede_gepinnte_abhaengigkeit():
    """requirements.lock ist erzeugt, nicht gepflegt -- und genau deshalb
    laeuft es auseinander, sobald jemand requirements.txt anfasst und das
    Erzeugen vergisst. Dann baut das Abbild stillschweigend mit der ALTEN
    Fassung weiter, waehrend pip-audit die neue prueft.

    Die Wache vergleicht beide: jedes mit == gepinnte Paket muss in der
    Sperre mit derselben Fassung stehen.
    """
    import re
    wurzel = Path(__file__).resolve().parents[1]
    quelle = (wurzel / "requirements.txt").read_text(encoding="utf-8")
    sperre = (wurzel / "requirements.lock").read_text(encoding="utf-8")

    def normal(name):
        return re.sub(r"[-_.]+", "-", name).lower()

    gesperrt = dict(re.findall(r"^([A-Za-z0-9._-]+)==([^\s\\]+)", sperre,
                               re.M))
    gesperrt = {normal(k): v for k, v in gesperrt.items()}

    fehlt = []
    for zeile in quelle.splitlines():
        zeile = zeile.split("#")[0].strip()
        treffer = re.match(r"^([A-Za-z0-9._-]+)(\[[^\]]*\])?==([^\s;]+)",
                           zeile)
        if not treffer:
            continue
        name, fassung = normal(treffer.group(1)), treffer.group(3)
        if gesperrt.get(name) != fassung:
            fehlt.append(f"{name}: requirements.txt {fassung}, "
                         f"Sperre {gesperrt.get(name, 'fehlt')}")
    assert not fehlt, fehlt


def test_die_sperre_traegt_zu_jedem_paket_pruefsummen():
    """Ohne Pruefsumme ist die Sperre nur eine Liste. --require-hashes
    verlangt fuer JEDES Paket mindestens eine."""
    import re
    sperre = (Path(__file__).resolve().parents[1]
              / "requirements.lock").read_text(encoding="utf-8")
    pakete = re.findall(r"^([A-Za-z0-9._-]+)==[^\s\\]+(.*?)(?=^\S|\Z)",
                        sperre, re.M | re.S)
    assert len(pakete) >= 15, len(pakete)
    ohne = [n for n, rest in pakete if "--hash=sha256:" not in rest]
    assert not ohne, ohne
