"""Ist dieser Knoten von aussen erreichbar? Gemessen, nicht geraten.

DAS PROBLEM MIT SELBSTTESTS: Von innen laesst sich die eigene Freigabe nicht
ehrlich pruefen.

* Bei IPv4 versuchen viele Router erst gar keine Rueckverbindung aus dem
  eigenen Netz auf die eigene oeffentliche Adresse (NAT-Loopback). Der Test
  meldete dann "geschlossen", obwohl die Freigabe steht.
* Bei IPv6 ist es umgekehrt und schlimmer: es gibt kein NAT. Eine Verbindung
  aus dem LAN zur globalen IPv6 der NAS geht direkt dorthin und gelingt AUCH
  DANN, wenn die Firewall im Router zu ist. Ein Test von innen wuerde also
  immer "erreichbar" melden -- eine Auskunft, die nie falsch klingt und nie
  etwas wert ist.

DESHALB UEBER TOR. Die Verbindung verlaesst das Haus, laeuft ueber drei fremde
Rechner und kommt von aussen zurueck -- genau der Weg, den auch eine echte
Gegenstelle nimmt. Nebenbei ist es der einzige Weg, der keinen fremden Dienst
fragen muss: ein "pruef mal meinen Knoten"-Dienst bekaeme Adresse und Port
frei Haus, und das ist dieselbe Preisgabe, wegen der schon die Versionsabfrage
ueber Tor laeuft.

Python spricht kein SOCKS5. Die noetigen zwanzig Zeilen stehen hier statt
einer weiteren Abhaengigkeit; RFC 1928 ist kurz und aendert sich nicht.

WAS EIN FEHLSCHLAG BEDEUTET, ist dabei nicht einerlei -- und das ist der
eigentliche Wert dieses Moduls. "Abgelehnt" ist ein Befund: der Ausgangsknoten
hat den Rechner erreicht und ein RST bekommen, die Freigabe fehlt also. "Nicht
erlaubt" ist KEIN Befund: dann wollte der Ausgangsknoten den Port nicht
herstellen. Wer beides gleich behandelt, meldet einen Fehler, wo er nur nicht
messen konnte.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
import struct
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Mainnet. Steht so in jedem Kopf jeder Nachricht des Bitcoin-Protokolls.
MAGIE = bytes.fromhex("f9beb4d9")
PROTOKOLL = 70016

# Ueber Tor dauert allein der Aufbau des Kreises regelmaessig zehn bis zwanzig
# Sekunden. Kuerzer zu messen hiesse, die Langsamkeit des Weges als
# Unerreichbarkeit des Knotens zu melden.
ZEITLIMIT_SEKUNDEN = 30.0

# SOCKS5-Antwortcodes, RFC 1928 Abschnitt 6. Uebersetzt in das, was sie fuer
# diese Frage bedeuten -- und ob sie ueberhaupt etwas ueber den Knoten sagen.
_SOCKS_ANTWORT = {
    0x00: ("", True),
    0x01: ("allgemeiner Fehler im Ausgangsknoten", False),
    0x02: ("der Ausgangsknoten erlaubt diesen Port nicht", False),
    0x03: ("Netz nicht erreichbar", False),
    0x04: ("Rechner nicht erreichbar", False),
    0x05: ("abgelehnt", True),
    0x06: ("Zeit abgelaufen", False),
    0x07: ("Befehl nicht unterstuetzt", False),
    0x08: ("Adressart nicht unterstuetzt", False),
    # Tors erweiterte Codes (man tor, SocksPort-Flag ExtendedErrors). Alle
    # beschreiben, dass der Weg zum Onion-Dienst nicht zustande kam -- keiner
    # sagt etwas darueber, was HINTER dem Dienst ist.
    0xF0: ("Tor findet die Beschreibung des Onion-Dienstes nicht", False),
    0xF1: ("die Beschreibung des Onion-Dienstes ist ungueltig", False),
    0xF2: ("die Einfuehrung beim Onion-Dienst ist fehlgeschlagen", False),
    0xF3: ("der Treffpunkt mit dem Onion-Dienst ist fehlgeschlagen", False),
    0xF4: ("der Onion-Dienst verlangt eine Freigabe", False),
    0xF5: ("der Onion-Dienst verlangt eine andere Freigabe", False),
    0xF6: ("die .onion-Adresse ist ungueltig", False),
    0xF7: ("die Einfuehrung beim Onion-Dienst lief in die Zeit", False),
}

# Was ein blanker "allgemeiner Fehler" bei einer .onion bedeutet, WENN Tor
# seine erweiterten Codes schickt. Gemessen am 17.09.2026 in der CI, mit Tor
# 0.4.9.11 gegen einen Onion-Dienst, hinter dem niemand horchte: Antwort 0x01,
# jedes Mal. Der Grund steht in Tors Quelltext: der Dienst beendet den Strom,
# und der Grund kommt als END_STREAM_REASON_MISC an (connection_edge.c,
# connection_edge_end), das wird zu 0x01 (reasons.c). Scheitert dagegen der
# Weg zum Dienst, kommt einer der Codes 0xF0 bis 0xF7.
ONION_DAHINTER_NIEMAND = "Tor hat den Onion-Dienst erreicht, aber dahinter nahm niemand an"


class NichtGeprueft(Exception):
    """Die Messung kam nicht zustande -- das ist KEIN Befund ueber den Knoten."""


class Abgelehnt(Exception):
    """Der Rechner wurde erreicht und hat abgelehnt -- das IST ein Befund."""


def _socks5(proxy: tuple, ziel: str, port: int, zeitlimit: float,
            erweitert: bool = False) -> socket.socket:
    """Eine Verbindung durch Tors SOCKS5-Proxy aufbauen."""
    try:
        s = socket.create_connection(proxy, timeout=zeitlimit)
    except OSError as fehler:
        raise NichtGeprueft(f"Tor ist nicht erreichbar ({fehler})") from fehler
    s.settimeout(zeitlimit)
    try:
        s.sendall(b"\x05\x01\x00")                  # nur "keine Anmeldung"
        antwort = s.recv(2)
        if antwort[:1] != b"\x05" or antwort[1:2] != b"\x00":
            raise NichtGeprueft("Tor will eine Anmeldung, die es nicht geben sollte")

        # IP-Adressen gehen als LITERAL hinaus, nicht als Name: aufgeloest
        # sind sie hier laengst, und ein Name wuerde den Ausgangsknoten die
        # Aufloesung machen lassen -- womoeglich auf eine andere Adresse als
        # die, die wir pruefen wollen.
        #
        # Bei einer .onion ist es genau umgekehrt: die MUSS als Name hinaus.
        # Sie hat keine IP, hinter der man sie erreichen koennte -- Tor selbst
        # loest sie ueber das Verzeichnis der versteckten Dienste auf. Ein
        # Versuch, sie in eine IP zu verwandeln, waere sinnlos.
        try:
            art = ipaddress.ip_address(ziel)
            kopf = (b"\x05\x01\x00" + (b"\x01" if art.version == 4 else b"\x04")
                    + art.packed + struct.pack(">H", port))
        except ValueError:
            roh = ziel.encode("idna")
            if len(roh) > 255:
                raise NichtGeprueft("Der Name ist zu lang fuer SOCKS5")
            kopf = (b"\x05\x01\x00\x03" + bytes([len(roh)]) + roh
                    + struct.pack(">H", port))
        s.sendall(kopf)
        kopf_zurueck = s.recv(4)
        if len(kopf_zurueck) < 2:
            raise NichtGeprueft("Tor hat die Verbindung ohne Antwort beendet")
        code = kopf_zurueck[1]
        text, aussagekraeftig = _SOCKS_ANTWORT.get(code, (f"Code {code}", False))
        if erweitert and code == 0x01 and ziel.endswith(".onion"):
            raise Abgelehnt(ONION_DAHINTER_NIEMAND)
        if code == 0x00:
            # Den Rest der Antwort wegleiten, sonst steckt er im Datenstrom.
            rest = {0x01: 4, 0x03: -1, 0x04: 16}.get(kopf_zurueck[3], 0)
            if rest == -1:
                rest = s.recv(1)[0]
            if rest:
                s.recv(rest)
            s.recv(2)                                # Port
            return s
        if aussagekraeftig:
            raise Abgelehnt(text)
        raise NichtGeprueft(text)
    except (Abgelehnt, NichtGeprueft):
        s.close()
        raise
    except OSError as fehler:
        s.close()
        raise NichtGeprueft(f"Verbindung zu Tor abgebrochen ({fehler})") from fehler


def _version_nachricht() -> bytes:
    """Die erste Nachricht, die jeder Bitcoin-Knoten von einem Gegenueber will."""
    last = (struct.pack("<iQq", PROTOKOLL, 0, int(time.time()))
            + b"\0" * 26 + b"\0" * 26
            + struct.pack("<Q", 0) + b"\x00"
            + struct.pack("<i?", 0, False))
    pruef = hashlib.sha256(hashlib.sha256(last).digest()).digest()[:4]
    return (MAGIE + b"version".ljust(12, b"\0")
            + struct.pack("<I", len(last)) + pruef + last)


def _kennung(antwort: bytes) -> Optional[str]:
    """Aus der version-Antwort die Kennung des Knotens ("/Satoshi:31.1.0/")."""
    if len(antwort) < 24 or antwort[:4] != MAGIE:
        return None
    if antwort[4:16].rstrip(b"\0") != b"version":
        return None
    last = antwort[24:]
    if len(last) < 81:
        return None
    laenge = last[80]
    if len(last) < 81 + laenge:
        return None
    return last[81:81 + laenge].decode("ascii", "replace")


def _netz(adresse: str) -> str:
    """Welcher der drei Wege hier geprueft wird."""
    if adresse.endswith(".onion"):
        return "onion"
    return "ipv6" if ":" in adresse else "ipv4"


def zerlege(wirt: str, vorgabe_port: int) -> Tuple[str, int]:
    """"host:port" in seine zwei Teile -- auch bei IPv6.

    LND gibt die Adresse eines Wachturms als EINE Zeichenkette heraus, mit
    Port daran. Ein blankes split(":") zerlegt dabei jede IPv6-Adresse in
    Stuecke; die gehoert in eckige Klammern, und erst der Doppelpunkt DAHINTER
    trennt den Port ab.

    Ohne lesbaren Port gilt der vorgegebene -- eine Adresse ohne Port ist
    keine kaputte Angabe, sondern eine, die den Standardport meint.
    """
    text = (wirt or "").strip()
    if text.startswith("["):                       # [2001:db8::1]:9911
        ende = text.find("]")
        if ende > 0:
            rest = text[ende + 1:]
            port = rest[1:] if rest.startswith(":") else ""
            return text[1:ende], int(port) if port.isdigit() else vorgabe_port
        return text.strip("[]"), vorgabe_port
    kopf, trenner, schwanz = text.rpartition(":")
    if trenner and schwanz.isdigit() and ":" not in kopf:
        return kopf, int(schwanz)
    return text, vorgabe_port                      # nackte IPv6 oder kein Port


def pruefe_eine(adresse: str, port: int, proxy: tuple,
                zeitlimit: float = ZEITLIMIT_SEKUNDEN,
                handschlag: bool = True, erweitert: bool = False) -> Dict:
    """Eine Adresse pruefen. Immer mit Begruendung, nie nur ja/nein.

    handschlag=False fuer Dienste, die kein Bitcoin sprechen -- Lightning und
    der Wachturm. Dort ist die Frage allein, ob die Verbindung von aussen bis
    zum Dienst durchkommt. Bei einer .onion beantwortet das Tor selbst: eine
    Zusage (0x00) gibt es erst, wenn der Onion-Dienst die Verbindung zum Ziel
    hergestellt hat (RELAY_CONNECTED). Genau das fehlte bis 0.62.0 -- Tor
    fand den Dienst, und dahinter nahm niemand an.

    erweitert=True, wenn der Proxy Tors ExtendedErrors schickt. Nur dann
    laesst sich bei einer .onion "dahinter nimmt niemand an" von "der Weg kam
    nicht zustande" unterscheiden -- siehe ONION_DAHINTER_NIEMAND.
    """
    begonnen = time.monotonic()
    ergebnis = {"adresse": adresse, "port": port, "netz": _netz(adresse)}
    try:
        s = _socks5(proxy, adresse, port, zeitlimit, erweitert)
    except Abgelehnt as fehler:
        # Der eine Fall, in dem ein Fehlschlag wirklich etwas aussagt.
        ergebnis.update(erreichbar=False, geprueft=True, grund="abgelehnt",
                        port_offen=False, einzelheit=str(fehler))
        return ergebnis
    except NichtGeprueft as fehler:
        ergebnis.update(erreichbar=None, geprueft=False, grund="nicht_pruefbar",
                        einzelheit=str(fehler))
        return ergebnis

    # AB HIER STEHT EINE TATSACHE FEST, und sie ist die eigentliche Frage
    # dieses Tests: der Ausgangsknoten hat eine TCP-Verbindung von aussen
    # nach adresse:port aufgebaut (RFC 1928, Antwort 0x00 heisst "succeeded").
    # Die Freigabe im Router trägt also.
    #
    # Bis zum 01.09.2026 ging das unter: brach der Handschlag danach ab,
    # meldete die Zeile rot "die Verbindung kam zustande und brach dann ab" --
    # und verschwieg dabei genau das, weswegen jemand den Knopf drueckt.
    ergebnis["port_offen"] = True

    if not handschlag:
        s.close()
        ergebnis.update(erreichbar=True, geprueft=True, grund="",
                        dauer_s=round(time.monotonic() - begonnen, 1))
        return ergebnis

    try:
        s.sendall(_version_nachricht())
        puffer = b""
        while len(puffer) < 24 + 81:
            stueck = s.recv(4096)
            if not stueck:
                break
            puffer += stueck
    except (socket.timeout, TimeoutError) as fehler:
        # Ein Zeitlimit ist KEIN Abbruch. socket.timeout ist eine Unterklasse
        # von OSError und landete deshalb im selben Topf wie ein RST -- die
        # Zeile behauptete dann "brach ab", wo niemand etwas abgebrochen hat.
        # Ueber Tor ist das haeufig: der Kreis steht, aber die Antwort kommt
        # nicht in der verbliebenen Frist. Der Port bleibt nachweislich offen.
        ergebnis.update(erreichbar=None, geprueft=False, grund="keine_antwort",
                        einzelheit=str(fehler))
        return ergebnis
    except OSError as fehler:
        ergebnis.update(erreichbar=False, geprueft=True, grund="kein_handschlag",
                        einzelheit=str(fehler))
        return ergebnis
    finally:
        s.close()

    kennung = _kennung(puffer)
    if kennung is None:
        # Der Port ist offen, aber dahinter spricht niemand Bitcoin. Fast
        # immer eine Freigabe, die auf das falsche Geraet zeigt.
        ergebnis.update(erreichbar=False, geprueft=True, grund="kein_knoten",
                        einzelheit="")
        return ergebnis
    ergebnis.update(erreichbar=True, geprueft=True, grund="", kennung=kennung,
                    dauer_s=round(time.monotonic() - begonnen, 1))
    return ergebnis


def pruefe(adressen: List[str], port: int, proxy: tuple,
           zeitlimit: float = ZEITLIMIT_SEKUNDEN,
           handschlag: bool = True, erweitert: bool = False) -> Dict:
    """Alle angekuendigten Adressen pruefen, je Netz getrennt."""
    einzeln = [pruefe_eine(a, port, proxy, zeitlimit, handschlag, erweitert)
               for a in adressen]
    return {
        "port": port,
        "adressen": einzeln,
        # Erreichbar ist der Knoten, sobald EIN Weg trägt. Zwei Wege sind
        # besser, aber einer genuegt, um Teil des Netzes zu sein.
        "erreichbar": any(e.get("erreichbar") for e in einzeln),
        "geprueft": any(e.get("geprueft") for e in einzeln),
    }
