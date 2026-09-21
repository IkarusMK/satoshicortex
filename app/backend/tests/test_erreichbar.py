"""Der Erreichbarkeitstest -- gegen einen echten SOCKS5-Gegenpart.

Warum ein richtiger Socket und keine Attrappe: geprueft wird hier ein
Drahtprotokoll. Eine Attrappe wuerde genau das bestaetigen, was ich mir beim
Schreiben gedacht habe, und genau das nicht finden, was ich falsch verstanden
habe. Der Gegenpart unten spricht RFC 1928, nicht meine Annahme davon.
"""
import socket
import struct
import threading

import pytest

from satcortex import erreichbar


class SocksAttrappe:
    """Ein SOCKS5-Gegenpart, der sich so verhaelt wie ein Tor-Ausgangsknoten."""

    def __init__(self, antwortcode=0x00, danach=b"", *, adressart=0x01):
        self.antwortcode = antwortcode
        self.danach = danach          # was der "Zielrechner" zurueckschickt
        self.adressart = adressart
        self.gesehen = {}
        self.horcher = socket.socket()
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(1)
        self.adresse = self.horcher.getsockname()
        self.faden = threading.Thread(target=self._bedienen, daemon=True)
        self.faden.start()

    def _bedienen(self):
        try:
            s, _ = self.horcher.accept()
        except OSError:
            return
        try:
            s.recv(3)                                  # Begruessung
            s.sendall(b"\x05\x00")
            kopf = s.recv(4)                           # ver, cmd, rsv, atyp
            self.gesehen["adressart"] = kopf[3]
            if kopf[3] == 0x03:                    # Name: erst die Laenge
                laenge = s.recv(1)[0]
            else:
                laenge = {0x01: 4, 0x04: 16}[kopf[3]]
            self.gesehen["ziel"] = s.recv(laenge)
            self.gesehen["port"] = struct.unpack(">H", s.recv(2))[0]
            s.sendall(bytes([0x05, self.antwortcode, 0x00, self.adressart])
                      + b"\0" * (4 if self.adressart == 0x01 else 16)
                      + b"\0\0")
            if self.antwortcode == 0x00:
                s.recv(4096)                           # unsere version-Nachricht
                if self.danach:
                    s.sendall(self.danach)
        except OSError:
            pass
        finally:
            s.close()

    def schliessen(self):
        self.horcher.close()


def _version_antwort(kennung=b"/Satoshi:31.1.0/"):
    """Eine echte version-Antwort, wie ein Knoten sie schickt."""
    last = (struct.pack("<iQq", 70016, 1033, 1_780_000_000)
            + b"\0" * 26 + b"\0" * 26 + struct.pack("<Q", 7)
            + bytes([len(kennung)]) + kennung
            + struct.pack("<i?", 964_708, True))
    return (erreichbar.MAGIE + b"version".ljust(12, b"\0")
            + struct.pack("<I", len(last)) + b"\0\0\0\0" + last)


@pytest.fixture
def attrappe():
    gebaut = []

    def bauen(**kw):
        a = SocksAttrappe(**kw)
        gebaut.append(a)
        return a
    yield bauen
    for a in gebaut:
        a.schliessen()


def test_ein_antwortender_knoten_gilt_als_erreichbar(attrappe):
    a = attrappe(danach=_version_antwort())
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert d["erreichbar"] is True and d["geprueft"] is True
    assert d["kennung"] == "/Satoshi:31.1.0/"
    assert d["netz"] == "ipv4"


def test_die_adresse_geht_als_literal_hinaus_nicht_als_name(attrappe):
    """Ein Name wuerde den Ausgangsknoten aufloesen lassen -- moeglicherweise
    auf eine ANDERE Adresse als die, die geprueft werden soll. Dann pruefte
    der Test etwas, das er nicht gefragt hat."""
    a = attrappe(danach=_version_antwort())
    erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert a.gesehen["adressart"] == 0x01
    assert a.gesehen["ziel"] == bytes([203, 0, 113, 7])
    assert a.gesehen["port"] == 8333


def test_ipv6_geht_als_ipv6_hinaus(attrappe):
    a = attrappe(danach=_version_antwort(), adressart=0x04)
    d = erreichbar.pruefe_eine("2001:db8::1", 8333, a.adresse, zeitlimit=5)
    assert a.gesehen["adressart"] == 0x04
    assert len(a.gesehen["ziel"]) == 16
    assert d["netz"] == "ipv6"


def test_abgelehnt_ist_ein_befund(attrappe):
    """Der Ausgangsknoten hat den Rechner ERREICHT und ein RST bekommen. Damit
    steht fest: die Freigabe fehlt. Genau dieser Fall lag am 31.08.2026 bei
    Der Betreiber vor -- "Connection refused nach 0,0 Sekunden"."""
    a = attrappe(antwortcode=0x05)
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert d["geprueft"] is True
    assert d["erreichbar"] is False
    assert d["grund"] == "abgelehnt"


def test_ein_ausgangsknoten_der_den_port_nicht_mag_ist_KEIN_befund(attrappe):
    """Der wichtigste Test hier. Tor-Ausgangsknoten haben eigene Regeln, und
    manche stellen ungewoehnliche Ports gar nicht erst her. Das sagt nichts
    ueber den geprueften Knoten -- wer es trotzdem als "nicht erreichbar"
    meldet, schickt jemanden in seinen Router, um dort etwas zu reparieren,
    das nie kaputt war."""
    a = attrappe(antwortcode=0x02)
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert d["geprueft"] is False
    assert d["erreichbar"] is None
    assert d["grund"] == "nicht_pruefbar"


@pytest.mark.parametrize("code", [0x01, 0x03, 0x04, 0x06, 0x07, 0x08])
def test_alle_uebrigen_codes_gelten_als_nicht_pruefbar(attrappe, code):
    a = attrappe(antwortcode=code)
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert d["geprueft"] is False, f"Code {code:#x} wurde als Befund gewertet"


def test_offener_port_ohne_bitcoin_dahinter(attrappe):
    """Fast immer eine Freigabe, die auf das falsche Geraet zeigt."""
    a = attrappe(danach=b"HTTP/1.1 200 OK\r\n\r\n" + b"x" * 200)
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5)
    assert d["geprueft"] is True and d["erreichbar"] is False
    assert d["grund"] == "kein_knoten"


def test_ohne_tor_wird_nichts_behauptet():
    """Kein Tor heisst: nicht gemessen. Nicht: nicht erreichbar."""
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, ("127.0.0.1", 1), zeitlimit=2)
    assert d["geprueft"] is False and d["erreichbar"] is None
    assert "Tor" in d["einzelheit"]


def test_ein_tragender_weg_genuegt(attrappe):
    """Zwei Wege sind besser, einer genuegt, um Teil des Netzes zu sein."""
    gut = attrappe(danach=_version_antwort())
    d = erreichbar.pruefe(["203.0.113.7"], 8333, gut.adresse, zeitlimit=5)
    assert d["erreichbar"] is True
    assert len(d["adressen"]) == 1


def test_ohne_adressen_wird_nichts_geprueft():
    d = erreichbar.pruefe([], 8333, ("127.0.0.1", 1))
    assert d["erreichbar"] is False and d["geprueft"] is False


# ── Die eigene .onion pruefen ──────────────────────────────────────────────
#
# Sie ist einer von des Betreibers vier Wegen und gehoerte von Anfang an in diesen
# Test. Bei einer .onion ist es genau umgekehrt wie bei einer IP: sie MUSS als
# Name hinausgehen. Sie hat keine Adresse, hinter der man sie erreichen
# koennte -- Tor loest sie ueber das Verzeichnis der versteckten Dienste auf.

ONION = "kscutiudrd2kwjwucpu5da5r6ni47yypcgsmvtxy6bz7qpimqepkqiyd.onion"


def test_eine_onion_geht_als_NAME_hinaus_nicht_als_adresse(attrappe):
    a = attrappe(danach=_version_antwort())
    d = erreichbar.pruefe_eine(ONION, 8333, a.adresse, zeitlimit=5)
    assert a.gesehen["adressart"] == 0x03, \
        "als IP-Literal waere die .onion nicht aufloesbar"
    assert a.gesehen["ziel"] == ONION.encode()
    assert d["erreichbar"] is True
    assert d["netz"] == "onion"


def test_die_drei_netze_werden_auseinandergehalten(attrappe):
    a = attrappe(danach=_version_antwort())
    for adresse, netz in ((ONION, "onion"), ("203.0.113.7", "ipv4"),
                          ("2001:db8::1", "ipv6")):
        assert erreichbar._netz(adresse) == netz


def test_eine_nicht_erreichbare_onion_ist_ein_befund(attrappe):
    """Tor meldet einen unerreichbaren versteckten Dienst als Fehler des
    Ausgangsknotens -- das ist KEIN Befund ueber unseren Knoten, sondern
    heisst nur, dass der Weg nicht zustande kam."""
    a = attrappe(antwortcode=0x04)      # Rechner nicht erreichbar
    d = erreichbar.pruefe_eine(ONION, 8333, a.adresse, zeitlimit=5)
    assert d["geprueft"] is False and d["erreichbar"] is None


# ── Lightning und Wachturm: ohne Bitcoin-Handschlag ────────────────────────
#
# Befund vom 17.09.2026: die .onion von LND und vom Wachturm stand im Netz,
# und Tor reichte an einen Container weiter, in dem niemand horchte. Gemessen
# wurde das nie -- die Pruefung kannte nur bitcoind. Fuer die beiden genuegt
# die Zusage von Tor: bei einer .onion kommt sie erst, wenn der Dienst die
# Verbindung zum Ziel hergestellt hat. Nahm dort niemand an, meldet Tor
# CONNECTREFUSED -- als SOCKS "abgelehnt" (reasons.c,
# stream_end_reason_to_socks5_response).


def test_ohne_handschlag_genuegt_die_zusage_von_tor(attrappe):
    a = attrappe()
    d = erreichbar.pruefe_eine(ONION, 9735, a.adresse, zeitlimit=5,
                               handschlag=False)
    assert d["erreichbar"] is True and d["geprueft"] is True
    assert d["port"] == 9735 and a.gesehen["port"] == 9735
    assert "kennung" not in d, "ohne Handschlag gibt es keine Kennung"


def test_ohne_handschlag_bleibt_abgelehnt_ein_befund(attrappe):
    """Genau das haette 0.62.0 gemeldet: Tor findet den Dienst, dahinter
    nimmt niemand an."""
    a = attrappe(antwortcode=0x05)
    d = erreichbar.pruefe_eine(ONION, 9911, a.adresse, zeitlimit=5,
                               handschlag=False)
    assert d["erreichbar"] is False and d["geprueft"] is True
    assert d["grund"] == "abgelehnt"


def test_mit_erweiterten_codes_heisst_allgemeiner_fehler_dahinter_niemand(attrappe):
    """Am 17.09.2026 in der CI gemessen: ein Onion-Dienst, hinter dem niemand
    horcht, kommt bei Tor 0.4.9.11 als 0x01 an -- und ohne erweiterte Codes
    sah das aus wie ein Weg, der nicht zustande kam. Mit ExtendedErrors
    scheitert der Weg mit 0xF0 bis 0xF7; ein blankes 0x01 ist dann der Befund."""
    a = attrappe(antwortcode=0x01)
    d = erreichbar.pruefe_eine(ONION, 9735, a.adresse, zeitlimit=5,
                               handschlag=False, erweitert=True)
    assert d["geprueft"] is True and d["erreichbar"] is False
    assert d["grund"] == "abgelehnt"
    assert d["einzelheit"] == erreichbar.ONION_DAHINTER_NIEMAND


def test_ohne_erweiterte_codes_bleibt_der_allgemeine_fehler_unklar(attrappe):
    a = attrappe(antwortcode=0x01)
    d = erreichbar.pruefe_eine(ONION, 9735, a.adresse, zeitlimit=5,
                               handschlag=False, erweitert=False)
    assert d["geprueft"] is False and d["erreichbar"] is None


def test_im_clearnet_bleibt_der_allgemeine_fehler_unklar(attrappe):
    """Die erweiterten Codes gibt es nur fuer .onion. Bei einer IP sagt 0x01
    weiterhin nichts ueber den Knoten."""
    a = attrappe(antwortcode=0x01)
    d = erreichbar.pruefe_eine("203.0.113.7", 8333, a.adresse, zeitlimit=5,
                               erweitert=True)
    assert d["geprueft"] is False and d["erreichbar"] is None


@pytest.mark.parametrize("code", range(0xF0, 0xF8))
def test_scheitert_der_weg_zur_onion_ist_das_kein_befund(attrappe, code):
    a = attrappe(antwortcode=code)
    d = erreichbar.pruefe_eine(ONION, 9735, a.adresse, zeitlimit=5,
                               handschlag=False, erweitert=True)
    assert d["geprueft"] is False and d["erreichbar"] is None
    assert not d["einzelheit"].startswith("Code "), "der Code hat einen Namen"


def test_pruefe_reicht_den_handschlag_durch(attrappe):
    a = attrappe()
    d = erreichbar.pruefe([ONION], 9735, a.adresse, zeitlimit=5,
                          handschlag=False)
    assert d["erreichbar"] is True


# ── Was der SOCKS-CONNECT allein schon beweist ────────────────────────────
#
# Des Betreibers Screenshot vom 01.09.2026: "IPv4 · 203.0.113.7 — die Verbindung
# kam zustande und brach dann ab", rot. Der Satz verschwieg genau das, wofuer
# man den Knopf drueckt: dass die Freigabe im Router traegt. Antwort 0x00 aus
# RFC 1928 heisst "succeeded" -- der Ausgangsknoten HAT eine TCP-Verbindung
# von aussen nach adresse:port aufgebaut.
#
# Und ein Zeitlimit ist kein Abbruch: socket.timeout ist eine Unterklasse von
# OSError und landete deshalb im selben Topf wie ein RST.


class _Steckdose:
    """Ein Gegenueber, das den SOCKS-Handschlag mitmacht und danach tut,
    was der Test vorgibt."""

    def __init__(self, danach):
        self.danach = danach
        self.gesendet = b""
        self._antworten = [b"\x05\x00", b"\x05\x00\x00\x01",
                           b"\x00\x00\x00\x00", b"\x00\x00"]

    def sendall(self, daten):
        self.gesendet += daten

    def recv(self, _n):
        if self._antworten:
            return self._antworten.pop(0)
        if isinstance(self.danach, Exception):
            raise self.danach
        return self.danach

    def settimeout(self, _t):
        pass

    def close(self):
        pass


def _mit_steckdose(monkeypatch, danach):
    import socket as socket_modul
    from satcortex import erreichbar as modul

    dose = _Steckdose(danach)
    monkeypatch.setattr(modul.socket, "create_connection",
                        lambda *a, **kw: dose)
    return modul.pruefe_eine("203.0.113.7", 8333, ("tor", 9050), zeitlimit=1.0)


def test_zeitlimit_beim_handschlag_ist_kein_abbruch(monkeypatch):
    import socket

    d = _mit_steckdose(monkeypatch, socket.timeout("timed out"))
    assert d["grund"] == "keine_antwort"
    assert d["geprueft"] is False, "nicht gemessen ist nicht 'nicht erreichbar'"
    assert d["port_offen"] is True, "die Verbindung STAND -- das gehoert gesagt"


def test_abbruch_bleibt_ein_abbruch_und_nennt_den_offenen_port(monkeypatch):
    d = _mit_steckdose(monkeypatch, ConnectionResetError(104, "reset"))
    assert d["grund"] == "kein_handschlag"
    assert d["geprueft"] is True
    assert d["port_offen"] is True


def test_abgelehnt_heisst_port_zu(monkeypatch):
    from satcortex import erreichbar as modul

    class Abgewiesen(_Steckdose):
        def __init__(self):
            super().__init__(b"")
            self._antworten = [b"\x05\x00", b"\x05\x05\x00\x01"]

    monkeypatch.setattr(modul.socket, "create_connection",
                        lambda *a, **kw: Abgewiesen())
    d = modul.pruefe_eine("203.0.113.7", 8333, ("tor", 9050), zeitlimit=1.0)
    assert d["grund"] == "abgelehnt"
    assert d["port_offen"] is False


# ------------------------------------------------- Adresse und Port trennen ---

def test_zerlege_trennt_wirt_und_port():
    """LND gibt die Adresse eines Wachturms als EINE Zeichenkette heraus."""
    assert erreichbar.zerlege("abc.onion:9911", 9911) == ("abc.onion", 9911)
    assert erreichbar.zerlege("203.0.113.7:9911", 9911) == ("203.0.113.7", 9911)
    # Ein abweichender Port gehoert uebernommen, nicht ueberschrieben.
    assert erreichbar.zerlege("abc.onion:19911", 9911) == ("abc.onion", 19911)


def test_zerlege_zerlegt_keine_ipv6_adresse():
    """Ein blankes split(':') macht aus einer IPv6-Adresse Konfetti.

    In eckigen Klammern trennt erst der Doppelpunkt DAHINTER den Port ab --
    und eine nackte IPv6-Adresse hat gar keinen.
    """
    assert erreichbar.zerlege("[2001:db8::1]:9911", 9911) == ("2001:db8::1", 9911)
    assert erreichbar.zerlege("2001:db8::1", 9911) == ("2001:db8::1", 9911)
    assert erreichbar.zerlege("[2001:db8::1]", 9911) == ("2001:db8::1", 9911)


def test_zerlege_ohne_port_gilt_die_vorgabe():
    """Eine Adresse ohne Port ist keine kaputte Angabe -- sie meint den
    Standardport."""
    assert erreichbar.zerlege("abc.onion", 9911) == ("abc.onion", 9911)
    assert erreichbar.zerlege("  abc.onion  ", 9911) == ("abc.onion", 9911)
    # Was hinter dem Doppelpunkt keine Zahl ist, ist kein Port.
    assert erreichbar.zerlege("abc.onion:tor", 9911) == ("abc.onion:tor", 9911)
