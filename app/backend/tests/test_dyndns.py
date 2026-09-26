"""Die eigene Adresse aktuell halten.

Hintergrund: Bitcoin Core loest -externalip nur beim Start auf. Am 26.08.2026
kuendigte der Knoten 79.223.252.78 an, waehrend der Name laengst auf
84.134.34.64 zeigte -- also eine Adresse, die inzwischen jemand anderem
gehoert.
"""
from satcortex import dyndns


def test_ip_bleibt_ip():
    assert dyndns.loese_auf(("203.0.113.7",)) == ["203.0.113.7"]
    assert dyndns.loese_auf(("2001:db8::1",)) == ["2001:db8::1"]


def test_name_wird_aufgeloest():
    auf = {"meinhost.example": ["203.0.113.7"]}
    assert dyndns.loese_auf(("meinhost.example",),
                            aufloeser=auf.get) == ["203.0.113.7"]


def test_nicht_aufloesbarer_name_faellt_weg_statt_kaputt_zu_landen():
    """Sonst stuende ein unbrauchbarer Wert in der Konfiguration, und der
    Knoten wuerbe mit einem Namen, den niemand aufloesen kann."""
    assert dyndns.loese_auf(("weg.example",), aufloeser=lambda _n: []) == []


def test_doppelte_verschwinden():
    auf = {"a.example": ["203.0.113.7"], "b.example": ["203.0.113.7"]}
    assert dyndns.loese_auf(("a.example", "b.example", "203.0.113.7"),
                            aufloeser=auf.get) == ["203.0.113.7"]


CONF = "listen=1\ndiscover=1\nexternalip=79.223.252.78\nmaxconnections=80\n"


def test_wechsel_wird_erkannt():
    assert dyndns.hat_sich_geaendert(CONF, ["84.134.34.64"]) is True


def test_unveraenderte_adresse_loest_keinen_neustart_aus():
    """Sonst startete bitcoind alle zehn Minuten neu -- mitten im Abgleich."""
    assert dyndns.hat_sich_geaendert(CONF, ["79.223.252.78"]) is False


def test_reihenfolge_allein_ist_keine_aenderung():
    """Ein DNS-Server darf seine Antworten sortieren, wie er will."""
    zwei = CONF + "externalip=2001:db8::1\n"
    assert dyndns.hat_sich_geaendert(zwei, ["2001:db8::1", "79.223.252.78"]) is False


# ── Je Familie getrennt fragen ─────────────────────────────────────────────
#
# Der Anlass, 31.08.2026: Im Betriebsprotokoll stand "[Errno -5] No address
# associated with hostname", waehrend derselbe Name von aussen ueber drei
# Resolver einwandfrei aufloeste. Vorher stand hier EIN getaddrinfo ohne
# Familienangabe -- der fragt A und AAAA zusammen und scheitert als GANZES,
# wenn eine der beiden Antworten nicht taugt. Sein Name hat kein AAAA.

import socket

import pytest

from satcortex import dyndns

# Eine Adresse aus einem ECHTEN oeffentlichen Bereich.
#
# Nicht 203.0.113.x, so naheliegend das waere: RFC 5737 haelt die Bereiche
# fuer Dokumentation frei, und Pythons ipaddress zaehlt sie seit 3.13 zu
# is_private. Fuer einen Filter, der genau private Adressen aussortiert, sind
# sie damit als Testdaten unbrauchbar -- er wuerde sie zu Recht wegwerfen und
# der Test schluege fehl, ohne dass etwas kaputt waere.
OEFFENTLICH = "93.184.216.34"


def test_ein_fehler_bei_aaaa_nimmt_die_ipv4_antwort_nicht_mit(monkeypatch):
    """DER Fall. Antwortet der DNS-Server auf die AAAA-Frage mit einem Fehler
    statt mit einer leeren Antwort, muss die funktionierende A-Antwort
    trotzdem durchkommen."""
    def gefragt(name, port, family=0, **kw):
        if family == socket.AF_INET6:
            raise socket.gaierror(-5, "No address associated with hostname")
        return [(socket.AF_INET, 0, 0, "", (OEFFENTLICH, 0))]
    monkeypatch.setattr(socket, "getaddrinfo", gefragt)
    assert dyndns._aufloesen("meinknoten.example") == [OEFFENTLICH]


def test_faellt_beides_aus_gibt_es_nichts(monkeypatch, caplog):
    def platzt(*a, **kw):
        raise socket.gaierror(-5, "No address associated with hostname")
    monkeypatch.setattr(socket, "getaddrinfo", platzt)
    with caplog.at_level("WARNING"):
        assert dyndns._aufloesen("meinknoten.example") == []
    assert any("A und AAAA" in s.getMessage() for s in caplog.records)


def test_ein_verlorenes_paket_ist_kein_ausfall(monkeypatch):
    """DNS laeuft ueber UDP. Ein verlorenes Paket ist Alltag, und die Antwort
    auf Alltag ist ein zweiter Versuch."""
    versuche = []

    def erst_beim_zweiten(name, port, family=0, **kw):
        versuche.append(family)
        if versuche.count(family) < 2:
            raise socket.timeout("keine Antwort")
        if family == socket.AF_INET6:
            raise socket.gaierror(-5, "kein AAAA")
        return [(socket.AF_INET, 0, 0, "", (OEFFENTLICH, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", erst_beim_zweiten)
    assert dyndns._aufloesen("meinknoten.example") == [OEFFENTLICH]


def test_eine_ipv4_in_ipv6_schreibweise_taugt_nicht_als_externalip():
    """Bei der Probe kam auf die AAAA-Frage "::ffff:84.134.34.64" zurueck.
    Ungeprueft waere daraus "externalip=::ffff:84.134.34.64" geworden -- eine
    Adresse, unter der den Knoten niemand erreicht, angekuendigt als waere sie
    echt."""
    assert dyndns._brauchbar("::ffff:84.134.34.64") is False
    assert dyndns._brauchbar(OEFFENTLICH) is True


@pytest.mark.parametrize("adresse", [
    "172.20.0.3",        # die Docker-interne, die der Knoten von sich sieht
    "192.168.1.10",
    "127.0.0.1",
    "169.254.1.1",
    "fe80::1",
    "kein-ip",
])
def test_was_als_eigene_adresse_nichts_taugt(adresse):
    assert dyndns._brauchbar(adresse) is False


@pytest.mark.parametrize("adresse", [OEFFENTLICH, "2003:db8::1"])
def test_was_taugt(adresse):
    assert dyndns._brauchbar(adresse) is True
