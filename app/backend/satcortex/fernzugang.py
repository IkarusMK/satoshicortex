"""Externe Wallets: Zeus als Fernbedienung fuer diesen Knoten.

Aus dem Betrieb, 26.09.2026: "also wenn dann will ich vollen umfangreichen
funktionen also alles weil du ja gesagt hast wir koennen dann die rechte fuer
zeus in der app steuern! ... und es wird dann nur tor und vpn angeboten".

Zeus spricht LNDs REST-Schnittstelle an -- direkt, an dieser Anwendung
vorbei. Es braucht dafuer eine Adresse, unter der es LND erreicht, und einen
Schluessel (Macaroon). Diese Datei entscheidet, WELCHE Rechte ein solcher
Schluessel bekommt, und baut den Verbindungstext, den Zeus einliest. Mit LND
selbst spricht sie nicht; das tun lnd.geraeteschluessel_*.

WAS EIN SCHLUESSEL NICHT KANN, und das gehoert gesagt, nicht verschwiegen:

* Eine BETRAGSGRENZE gibt es nicht. macaroons/constraints.go kennt nur
  Ablaufzeit, IP-Bindung und freie Bedingungen, die einen eingebauten
  Acceptor braeuchten. Wer ein entsperrtes Telefon mit der Stufe "voll" hat,
  kommt an alles.
* Die PIN dieser Anwendung greift in Zeus NICHT. Zeus fragt LND direkt; der
  Schutz auf dem Telefon ist Zeus' eigene PIN oder Gesichtserkennung.
* Die IP-BINDUNG hilft hier nicht. Geplant war, einen Tor-Schluessel nur ueber
  Tor und einen VPN-Schluessel nur aus dem Heimnetz gelten zu lassen. LNDs
  Pruefung (IPLockChecker) liest aber die Gegenstelle der gRPC-Verbindung,
  und REST-Anfragen reicht LND intern ueber 127.0.0.1 an gRPC weiter
  (lnd.go, v0.21.3-beta: restProxyDest, "0.0.0.0" -> "127.0.0.1"). Fuer jede
  REST-Anfrage steht dort also 127.0.0.1 -- die Bindung koennte zwei Wege
  nicht auseinanderhalten. Gefunden am 26.09.2026, vor dem Bau.

Was bleibt, ist genug: jedes Geraet bekommt einen EIGENEN Wurzelschluessel
(root_key_id). Loescht man ihn, sind alle Macaroons dieses Geraets sofort
wertlos -- die der anderen Geraete und das der Anwendung nicht.
"""
from __future__ import annotations

import base64
import ipaddress
import re
import unicodedata
from typing import Dict, Iterable, Optional, Tuple

# ── Rechtestufen ────────────────────────────────────────────────────────────
#
# Nachgeschlagen in LNDs Rechtetabelle, v0.21.3-beta (rpcserver.go und
# lnrpc/routerrpc/router_server.go), am 26.09.2026:
#
#   SendCoins          onchain:write
#   OpenChannel        onchain:write + offchain:write
#   CloseChannel       onchain:write + offchain:write
#   SendPaymentV2      offchain:write           (Lightning zahlen)
#   AddInvoice         invoices:write
#   NewAddress         address:write
#   BakeMacaroon       macaroon:generate
#   DeleteMacaroonID   macaroon:write
#
# Daraus folgen die Grenzen der Stufen. "lightning" zahlt Rechnungen, kann
# aber weder on-chain senden noch Kanaele oeffnen oder schliessen -- das
# verlangt onchain:write. offchain:write erlaubt dafuer auch das Setzen von
# Kanalgebuehren; LND trennt das nicht.
#
# "macaroon" bekommt KEINE Stufe, auch "voll" nicht. Mit macaroon:generate
# koennte sich ein gestohlenes Telefon einen Ersatzschluessel backen, der den
# Widerruf ueberlebt -- und mit macaroon:write den Schluessel der Anwendung
# loeschen.
_LESEN: Tuple[Tuple[str, str], ...] = (
    ("info", "read"),
    ("onchain", "read"),
    ("offchain", "read"),
    ("address", "read"),
    ("invoices", "read"),
    ("peers", "read"),
    ("message", "read"),
    ("signer", "read"),
)
_EMPFANGEN = _LESEN + (
    ("invoices", "write"),      # Rechnungen ausstellen
    ("address", "write"),       # Einzahladressen erzeugen
)
_LIGHTNING = _EMPFANGEN + (
    ("offchain", "write"),      # Lightning zahlen, Kanalgebuehren setzen
    ("peers", "write"),         # sich mit Gegenstellen verbinden
    ("message", "write"),       # Nachrichten unterschreiben
)
_VOLL = _LIGHTNING + (
    ("onchain", "write"),       # on-chain senden, Kanaele oeffnen/schliessen
    ("info", "write"),          # u. a. LND beenden (StopDaemon)
    ("signer", "generate"),     # Signaturen fuer eigene Ausgaben
)

STUFEN: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "ansehen": _LESEN,
    "empfangen": _EMPFANGEN,
    "lightning": _LIGHTNING,
    "voll": _VOLL,
}
STUFEN_REIHENFOLGE = ("ansehen", "empfangen", "lightning", "voll")

# Die zwei Wege. Mehr gibt es mit Absicht nicht: LNC ginge ueber einen
# Vermittlungsserver von Lightning Labs, eine offene Portfreigabe waere LNDs
# Schnittstelle fuer das ganze Internet.
WEGE = ("tor", "vpn")

# Unter diesem Port antwortet LND im Onion-Dienst. Derselbe wie im Container
# -- Zeus schlaegt fuer LND ohnehin 8080 vor.
ONION_PORT = 8080

# Die erste Wurzelkennung fuer Geraete. Weit weg von 0: an Kennung 0 haengen
# LNDs admin-, readonly- und invoice-Macaroon UND das eigene der Anwendung.
# Wer 0 loescht, sperrt die Anwendung aus ihrem eigenen Knoten aus.
ERSTE_KENNUNG = 1_000_000

# Eine Obergrenze, damit ein uebernommenes Konto nicht beliebig viele
# Schluessel ausstellt. Zwanzig Telefone hat niemand.
HOECHSTENS_GERAETE = 20

NAME_HOECHSTENS = 40


def rechte(stufe: str) -> Tuple[Tuple[str, str], ...]:
    try:
        return STUFEN[stufe]
    except KeyError:
        raise ValueError(f"unbekannte Stufe: {stufe!r}") from None


def naechste_kennung(bei_lnd: Iterable[int], bei_uns: Iterable[int]) -> int:
    """Die naechste freie Wurzelkennung fuer ein neues Geraet.

    Ueber ALLEM, was LND kennt, nicht nur ueber dem, was wir vergeben haben:
    wer mit lncli selbst Schluessel gebacken hat, dessen Kennungen bleiben
    unberuehrt.
    """
    groesste = ERSTE_KENNUNG - 1
    for kennung in list(bei_lnd) + list(bei_uns):
        if kennung >= ERSTE_KENNUNG:
            groesste = max(groesste, kennung)
    return groesste + 1


def pruefe_name(name: str) -> str:
    """Wie das Geraet in der Liste heisst. Nur zur Anzeige."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Das Geraet braucht einen Namen.")
    if len(name) > NAME_HOECHSTENS:
        raise ValueError(f"Hoechstens {NAME_HOECHSTENS} Zeichen.")
    if any(unicodedata.category(z) == "Cc" for z in name):
        raise ValueError("Steuerzeichen sind im Namen nicht erlaubt.")
    return name


_LABEL = re.compile(r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)")


def pruefe_host(host: str) -> str:
    """Die Adresse des Servers im Heimnetz, wie das Telefon sie erreicht.

    Eine IP-Adresse oder ein Name -- ohne Schema, ohne Port, ohne Pfad. Der
    Wert landet im Verbindungstext, und dort darf nichts stehen, was Zeus
    beim Zerlegen an der falschen Stelle trennt.
    """
    roh = (host or "").strip()
    if roh.startswith("[") and roh.endswith("]"):
        roh = roh[1:-1]
    if not roh:
        raise ValueError("Die Adresse fehlt.")
    try:
        return str(ipaddress.ip_address(roh))
    except ValueError:
        pass
    if len(roh) > 253 or not all(_LABEL.fullmatch(t) for t in roh.split(".")):
        raise ValueError("Keine gueltige Adresse -- nur IP oder Name, "
                         "ohne http:// und ohne Port.")
    return roh


def verbindungstext(host: str, port: int, macaroon_hex: str) -> str:
    """Der Text, den Zeus einliest -- als QR-Code oder zum Einfuegen.

    lndconnect://host:port?macaroon=<base64url>. Das Zertifikat bleibt
    draussen: Zeus liest den Parameter "cert" nicht
    (utils/ConnectionFormatUtils.ts, processLndConnectUrl gibt nur host,
    port, macaroonHex und enableTor zurueck), und er machte den QR-Code nur
    groesser. Bei einer .onion schaltet Zeus Tor von selbst ein.

    base64url OHNE Auffuellung: Zeus zerlegt die Parameter an jedem "=".
    """
    if not isinstance(port, int) or not 0 < port < 65536:
        raise ValueError(f"unmoeglicher Port: {port!r}")
    if not macaroon_hex:
        raise ValueError("Kein Schluessel.")
    wert = base64.urlsafe_b64encode(bytes.fromhex(macaroon_hex)).decode()
    wert = wert.rstrip("=")
    ziel = f"[{host}]" if ":" in host else host
    return f"lndconnect://{ziel}:{port}?macaroon={wert}"


# Was "nur auf dem Server selbst" heisst. Dorthin zeigt die Vorgabe der
# Compose -- so aendert sich fuer niemanden etwas, der den Weg nicht will.
_NUR_HIER = {"127.0.0.1", "::1", "localhost", ""}


def vpn_lage(bind: Optional[str], port_roh: Optional[str]) -> Dict:
    """Ob LNDs Schnittstelle im Heimnetz erreichbar ist -- laut Compose.

    Die Anwendung oeffnet keinen Port selbst; das kann sie ohne
    Docker-Socket nicht, und den bekommt sie auf einer Maschine mit Wallet
    nicht. Entschieden wird in der .env (LND_REST_BIND, LND_REST_LAN_PORT),
    und hier wird nur gelesen, was die Compose durchreicht:

      compose_alt  die Variablen fehlen ganz -- die Compose ist aelter
      aus          nur auf dem Server selbst, oder ohne festen Port
      bereit       im Heimnetz, unter genau diesem Port

    Ohne festen Port waehlt Docker einen zufaelligen, und den kennt die
    Anwendung nicht -- dann gaebe es keinen Verbindungstext, der stimmt.
    """
    if bind is None:
        return {"stand": "compose_alt", "port": None}
    try:
        port = int((port_roh or "").strip())
    except ValueError:
        port = None
    if bind.strip() in _NUR_HIER or port is None or not 0 < port < 65536:
        return {"stand": "aus", "port": None}
    return {"stand": "bereit", "port": port}
