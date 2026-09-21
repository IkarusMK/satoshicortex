"""Nachsehen, ob es eine neuere Fassung gibt -- und die richtige melden.

Der Anlass: Am 27.08.2026 erschienen 30.3 und 29.4 ZWEI TAGE NACH 31.1. Das
sah nach einem dringenden Update aus, war aber eine Nachlieferung fuer aeltere
Zweige. Wer auf 31.1 sitzt, darf sie nicht angeboten bekommen -- das waere ein
Rueckschritt.
"""
import json
import logging
import pathlib
import re
import urllib.error
import urllib.request

import pytest

from satcortex import updates


def _atom(*kennungen: str) -> str:
    """Ein Atom-Feed, wie GitHub ihn ausliefert -- auf das Noetige gekuerzt."""
    eintraege = "".join(
        f"<entry><id>tag:github.com,2008:Repository/1181927/{k}</id>"
        f"<title>irgendein Name</title></entry>" for k in kennungen)
    return ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f"<title>Release notes</title>{eintraege}</feed>")


def test_versionen_zerlegen():
    assert updates.zerlege("v31.1") == (31, 1, 0)
    assert updates.zerlege("31.1.2") == (31, 1, 2)
    assert updates.zerlege("v0.21.2-beta") is None      # LND-Schema, nicht Core
    assert updates.zerlege("") is None


def test_laufende_version_aus_der_kennung_des_knotens():
    """Aus dem, was der Knoten SELBST meldet -- der Abbildname sagt nur, was
    gezogen werden sollte."""
    assert updates.laufende_version("/Satoshi:31.1.0/") == (31, 1, 0)
    assert updates.laufende_version("/Satoshi:30.3.0(irgendwas)/") == (30, 3, 0)
    assert updates.laufende_version("") is None


def test_aeltere_zweige_sind_kein_update():
    """DER Fall vom 27.08.2026."""
    laufend = (31, 1, 0)
    verfuegbar = [(29, 4, 0), (30, 3, 0), (31, 0, 0), (31, 1, 0)]
    assert updates.waehle(laufend, verfuegbar) is None


def test_wartungsversion_im_eigenen_zweig():
    ergebnis = updates.waehle((31, 1, 0), [(30, 3, 0), (31, 2, 0)])
    assert ergebnis["version"] == "31.2"
    assert ergebnis["art"] == "wartung"


def test_zweigwechsel_wird_als_solcher_benannt():
    """Eine neue Hauptversion kann Regelwerk und Datenbankformat aendern --
    das gehoert gelesen, nicht durchgewinkt."""
    ergebnis = updates.waehle((31, 1, 0), [(32, 0, 0)])
    assert ergebnis["version"] == "32.0"
    assert ergebnis["art"] == "zweigwechsel"


def test_wartung_geht_vor_zweigwechsel():
    """Gibt es beides, ist die Wartungsversion die dringlichere Meldung: sie
    laesst sich gefahrlos einspielen."""
    ergebnis = updates.waehle((31, 1, 0), [(31, 2, 0), (32, 0, 0)])
    assert ergebnis["version"] == "31.2"
    assert ergebnis["art"] == "wartung"
    assert ergebnis["auch_verfuegbar"] == "32.0"


def test_gleiche_version_meldet_nichts():
    assert updates.waehle((31, 1, 0), [(31, 1, 0)]) is None


def test_abfrage_ohne_netz_ist_kein_drama():
    """Ueber Tor kommt das vor -- manche Dienste weisen Exit-Knoten ab. Dann
    gibt es diesmal keine Meldung, mehr nicht."""
    assert updates.hole_versionen(proxy="http://127.0.0.1:1") == []


# ── LND: dieselbe Frage, eine andere Zaehlweise ─────────────────────────────
#
# Der Anlass: der Betreiber wollte am 27.08.2026 wissen, ob Lightning genauso
# geprueft wird. Wird es -- aber nicht mit derselben Regel. Bei LND wechselt
# die fuehrende Null nie, der Zweig steckt in der ZWEITEN Zahl. Wer hier die
# Core-Regel anwendet, haelt 0.22.0 fuer eine harmlose Wartungsversion.


def test_lnd_tags_zerlegen():
    assert updates.zerlege_lnd("v0.21.2-beta") == (0, 21, 2)
    assert updates.zerlege_lnd("v0.20.3-beta") == (0, 20, 3)


def test_vorabfassungen_werden_nicht_angeboten():
    """rc1 ist bei GitHub als Vorabfassung gekennzeichnet -- darauf allein
    wollen wir uns aber nicht verlassen. Ein falsch gesetztes Haekchen wuerde
    sonst eine Vorabfassung als Update anbieten."""
    assert updates.zerlege_lnd("v0.21.2-beta.rc1") is None
    assert updates.zerlege_lnd("v31.1") is None
    assert updates.zerlege_lnd("") is None


def test_laufende_lnd_fassung_aus_dem_was_lnd_meldet():
    assert updates.laufende_version_lnd(
        "0.21.2-beta commit=v0.21.2-beta") == (0, 21, 2)
    assert updates.laufende_version_lnd("") is None


def test_lnd_wartungsversion_im_eigenen_zweig():
    ergebnis = updates.waehle((0, 21, 1), [(0, 20, 3), (0, 21, 2)], updates.LND)
    assert ergebnis["version"] == "0.21.2-beta"
    assert ergebnis["art"] == "wartung"


def test_lnd_zweigwechsel_steckt_in_der_zweiten_zahl():
    """DER Unterschied zu Core. Mit der Core-Regel (erste Zahl) waere 0.22.0
    eine Wartungsversion -- dabei wandert LND dort die Datenbank, und die
    Wanderung ist einbahnig: ein Rueckschritt wird verweigert."""
    ergebnis = updates.waehle((0, 21, 2), [(0, 22, 0)], updates.LND)
    assert ergebnis["art"] == "zweigwechsel"
    assert ergebnis["version"] == "0.22.0-beta"


def test_lnd_aelterer_zweig_ist_kein_update():
    """0.20.3 erschien am selben Tag wie 0.21.2 -- derselbe Fall wie bei Core
    mit 30.3 neben 31.1. Wer auf 0.21.2 sitzt, darf 0.20.3 nicht angeboten
    bekommen."""
    assert updates.waehle((0, 21, 2), [(0, 20, 3), (0, 21, 2)], updates.LND) is None


def test_ausgelieferte_lnd_fassung_passt_zum_dockerfile():
    """Sobald es das Abbild gibt, duerfen Konstante und Dockerfile nicht
    auseinanderlaufen -- sonst meldet die Anzeige eine Fassung, die gar nicht
    ausgeliefert wird. Bis dahin uebersprungen, statt sie zu erfinden."""
    pfad = (pathlib.Path(__file__).resolve().parents[3]
            / "images" / "lnd" / "Dockerfile")
    if not pfad.exists():
        pytest.skip("images/lnd/Dockerfile gibt es noch nicht -- Phase 7")
    treffer = re.search(r"^ARG\s+LND_VERSION=(\S+)", pfad.read_text(), re.M)
    assert treffer, "Das Dockerfile nennt keine LND_VERSION"
    assert updates.zerlege_lnd(treffer.group(1)) == updates.LND_AUSGELIEFERT


# ── Die Abfrage muss durchkommen, nicht nur ihr Scheitern melden ───────────

def test_ein_zweiter_anlauf_wenn_der_erste_nicht_durchkommt(monkeypatch):
    """Auf dem Knoten im Betrieb stand tagelang "Noch nicht nachgesehen". Die
    Abfrage laeuft ueber Tor -- drei fremde Rechner, und mancher Exit-Knoten
    wird von GitHub abgewiesen. Ein zweiter Anlauf nimmt oft einen anderen
    Weg."""
    versuche = []

    class Antwort:
        def read(self, hoechstens=None):
            return _atom("v31.2").encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    def oeffnen(self, anfrage, timeout=None):
        versuche.append(timeout)
        if len(versuche) < 2:
            raise urllib.error.URLError("Tor-Kreis taugt nichts")
        return Antwort()

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", oeffnen)
    assert updates.hole_versionen() == [(31, 2, 0)]
    assert len(versuche) == 2, "der zweite Anlauf muss kommen"


def test_nach_erfolg_wird_nicht_weiter_versucht(monkeypatch):
    versuche = []

    class Antwort:
        def read(self, hoechstens=None):
            return _atom().encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    monkeypatch.setattr(urllib.request.OpenerDirector, "open",
                        lambda self, a, timeout=None: (versuche.append(1), Antwort())[1])
    updates.hole_versionen()
    assert len(versuche) == 1


def test_nach_allen_versuchen_wird_aufgegeben(monkeypatch, caplog):
    """Und zwar hoerbar: der Grund gehoert auf WARNING. Der Container
    protokolliert erst ab da -- auf INFO stand er zwar im Code, aber nirgends,
    wo ihn jemand haette lesen koennen."""
    def platzt(self, anfrage, timeout=None):
        raise urllib.error.URLError("abgewiesen")
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", platzt)

    with caplog.at_level(logging.WARNING):
        assert updates.hole_versionen() == []
    assert any(s.levelno >= logging.WARNING and "aufgegeben" in s.getMessage()
               for s in caplog.records)


def test_das_zeitlimit_ist_fuer_tor_bemessen():
    """Ueber Tor dauert allein der TLS-Handschlag regelmaessig zehn bis
    zwanzig Sekunden. Fuenfzehn Sekunden waren ein Muenzwurf."""
    assert updates.ZEITSPERRE_SEKUNDEN >= 30
    assert updates.VERSUCHE >= 2


# ── Ein Fehlschlag darf sich nicht in Endlosschleife melden ────────────────
#
# Der Anlass: der Betreiber schickte am 29.08.2026 einen Protokollausschnitt, in dem
# zwischen den Fortschrittsmeldungen von bitcoind alle zehn Minuten zweimal
# dasselbe stand -- einmal fuer Core, einmal fuer LND. Seine Antwort darauf
# war eindeutig: "es bringt mir nichts fehlschlaege sichtbar zu machen, es
# darf erst keine geben". Beides gilt: die Ursache gehoert behoben (siehe
# test_api.test_die_tor_konfiguration_wird_erneuert), und was danach noch
# schiefgeht, gehoert einmal gesagt und nicht sechsmal pro Stunde.


@pytest.fixture(autouse=True)
def _frische_meldebremse():
    """Die Bremse merkt sich etwas modulweit -- zwischen Tests gehoert sie leer."""
    updates._zuletzt_gemeldet.clear()
    yield
    updates._zuletzt_gemeldet.clear()


def _immer_abgewiesen(monkeypatch, fehler=None):
    def platzt(self, anfrage, timeout=None):
        raise fehler or urllib.error.URLError(
            ConnectionRefusedError(111, "Connection refused"))
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", platzt)


def _warnungen(caplog):
    return [s for s in caplog.records if s.levelno >= logging.WARNING]


def test_derselbe_grund_wird_nicht_bei_jedem_durchgang_gemeldet(monkeypatch, caplog):
    _immer_abgewiesen(monkeypatch)
    with caplog.at_level(logging.INFO):
        updates.hole_versionen(proxy="http://tor:9080")
        caplog.clear()
        updates.hole_versionen(proxy="http://tor:9080")
    assert not _warnungen(caplog), \
        "derselbe Fehlgrund gehoert nicht alle zehn Minuten erneut ins Protokoll"
    assert any("weiterhin" in s.getMessage() for s in caplog.records), \
        "ganz verschwinden darf er auch nicht -- nur leiser werden"


def test_ein_ANDERER_grund_wird_wieder_deutlich_gemeldet(monkeypatch, caplog):
    """Sonst verschluckte die Bremse den Wechsel von "Tor tot" zu etwas
    Neuem -- und genau der waere die Nachricht."""
    _immer_abgewiesen(monkeypatch)
    with caplog.at_level(logging.INFO):
        updates.hole_versionen(proxy="http://tor:9080")
        caplog.clear()
        _immer_abgewiesen(monkeypatch, urllib.error.URLError("timed out"))
        updates.hole_versionen(proxy="http://tor:9080")
    assert _warnungen(caplog), "ein neuer Grund ist eine neue Meldung"


def test_nach_einem_erfolg_zaehlt_der_naechste_fehlschlag_wieder(monkeypatch, caplog):
    _immer_abgewiesen(monkeypatch)
    with caplog.at_level(logging.WARNING):
        updates.hole_versionen(proxy="http://tor:9080")

    class Antwort:
        def read(self, hoechstens=None):
            return _atom().encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    monkeypatch.setattr(urllib.request.OpenerDirector, "open",
                        lambda self, a, timeout=None: Antwort())
    updates.hole_versionen(proxy="http://tor:9080")

    _immer_abgewiesen(monkeypatch)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        updates.hole_versionen(proxy="http://tor:9080")
    assert _warnungen(caplog), \
        "nach einem gelungenen Durchgang ist ein Fehlschlag wieder eine Nachricht"


def test_ein_abgewiesener_proxy_wird_als_solcher_benannt(monkeypatch, caplog):
    """"Connection refused" nennt den Fehler, aber nicht die Sache: abgewiesen
    hat nicht GitHub, sondern das eigene Tor -- die Anfrage hat den Rechner nie
    verlassen. Wer das Protokoll liest, soll den Unterschied sehen."""
    _immer_abgewiesen(monkeypatch)
    with caplog.at_level(logging.WARNING):
        updates.hole_versionen(proxy="http://tor:9080")
    text = " ".join(s.getMessage() for s in caplog.records)
    assert "tor:9080" in text and "HTTPTunnelPort" in text


# ── Die Abfrage laeuft ueber den Feed, nicht ueber die API ─────────────────
#
# Der Anlass, 30.08.2026: nachdem der Tor-Tunnel wieder stand, kam
#
#     Versionsabfrage (lnd) nach 3 Versuchen aufgegeben:
#     HTTPError: HTTP Error 403: rate limit exceeded
#
# Die GitHub-API laesst ohne Anmeldung 60 Anfragen je Stunde und IP zu --
# und ueber Tor teilen sich Hunderte Nutzer die IP des Ausgangsknotens.
# Nachgemessen: die API antwortet mit "x-ratelimit-limit: 60", der Atom-Feed
# schickt ueberhaupt keine Ratenkopfzeile.


def _antwortet_mit(monkeypatch, text: str):
    class Antwort:
        def read(self, hoechstens=None):
            return text.encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
    monkeypatch.setattr(urllib.request.OpenerDirector, "open",
                        lambda self, a, timeout=None: Antwort())


def test_die_quellen_sind_der_feed_und_nicht_die_api():
    """Atom, nicht die API.

    Seit dem 21.09.2026 ist auch die EIGENE Fassung dabei -- und weil es
    fuer dieses Projekt keine Releases gibt, sondern nur Tags, ist ihre
    Quelle tags.atom. Derselbe Weg, dasselbe Format, dieselbe Regel: kein
    Aufruf an api.github.com, der ein Kennzeichen hinterliesse.
    """
    for projekt in updates.PROJEKTE:
        assert projekt.quelle.endswith((".atom",)), projekt.name
        assert "api.github.com" not in projekt.quelle, projekt.name


def test_kennungen_kommen_aus_dem_feed(monkeypatch):
    _antwortet_mit(monkeypatch, _atom("v31.1", "v30.3", "v29.4"))
    assert updates.hole_versionen() == [(29, 4, 0), (30, 3, 0), (31, 1, 0)]


def test_vorabfassungen_fallen_durch_die_form_der_kennung(monkeypatch):
    """Der Feed sagt NICHT, ob etwas eine Vorabfassung ist -- die API tat das.
    Verlassen wird sich deshalb auf die Kennung selbst, und das ist der
    strengere Weg: ein falsch gesetztes Haekchen kann hier nichts kaputt
    machen."""
    _antwortet_mit(monkeypatch, _atom("v31.2rc1", "v31.1", "v32.0rc2"))
    assert updates.hole_versionen() == [(31, 1, 0)]

    _antwortet_mit(monkeypatch, _atom("v0.21.3-beta.rc1", "v0.21.2-beta"))
    assert updates.hole_versionen(projekt=updates.LND) == [(0, 21, 2)]


def test_der_titel_wird_nicht_ausgewertet(monkeypatch):
    """Im Titel steht der frei gewaehlte Name ("Bitcoin Core 31.1"), in der id
    die Kennung. Wer den Titel liest, liest etwas, das jederzeit anders
    lauten darf."""
    feed = _atom("v31.1").replace("irgendein Name", "Bitcoin Core 99.9")
    _antwortet_mit(monkeypatch, feed)
    assert updates.hole_versionen() == [(31, 1, 0)]


def test_ein_riesiger_feed_wird_nicht_ganz_gelesen(monkeypatch):
    """Ueber einen fremden Ausgangsknoten will man keine offene Grenze haben."""
    gelesen = []

    class Antwort:
        def read(self, hoechstens=None):
            gelesen.append(hoechstens)
            return _atom("v31.1").encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    monkeypatch.setattr(urllib.request.OpenerDirector, "open",
                        lambda self, a, timeout=None: Antwort())
    updates.hole_versionen()
    assert gelesen and gelesen[0] == updates.HOECHSTLAENGE
