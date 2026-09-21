"""Was eine Abfuhr bedeutet -- an einer Stelle, fuer alle.

Der Anlass steht im Modulkopf: in das Betriebsprotokoll vom 10.09.2026 standen
vier Abweisungen untereinander, drei erklaert und eine nicht. Die eine war
ein HTTP 418, und den kannte keine der beiden Listen, die es damals gab.
"""
import pytest

from satcortex import abweisung


@pytest.mark.parametrize("code", [401, 403, 404, 418, 429, 451, 500, 502, 503])
def test_jeder_bekannte_code_bekommt_einen_satz(code):
    satz = abweisung.deute_http(code, "Die Quelle")
    assert satz and str(code) in satz
    assert satz.endswith("."), "ein Satz, keine Fehlermeldung"


@pytest.mark.parametrize("code", [None, 200, 302, 600, "403", 0])
def test_was_keinen_bekannten_grund_hat_bekommt_keinen_erfundenen(code):
    """Nicht alles wegerklaeren. Ein Fehler ohne bekannte Bedeutung soll
    seinen Wortlaut behalten -- sonst sucht man ihn nirgends wieder."""
    assert abweisung.deute_http(code, "Die Quelle") is None


def test_das_hauptwort_kommt_vom_aufrufer():
    """Dasselbe Modul bedient Nachrichtenquellen und Boersen."""
    assert "Die Boerse" in abweisung.deute_http(403, "Die Boerse")
    assert "Die Quelle" in abweisung.deute_http(403, "Die Quelle")


def test_ueber_tor_ist_eine_abfuhr_der_regelfall():
    """Wer das nicht dazusagt, schickt jemanden auf Fehlersuche nach einem
    Fehler, den es nicht gibt."""
    for code in (401, 403, 418):
        assert "Tor" in abweisung.deute_http(code, "Die Quelle")


def test_zu_haeufig_gefragt_hat_mit_tor_nichts_zu_tun():
    """429 heisst "spaeter nochmal", 403 heisst "du nicht". Bis zum
    10.09.2026 bekamen beide denselben Satz ueber Tor-Ausgangsknoten -- und
    damit wies die Meldung bei 429 in die falsche Richtung."""
    satz = abweisung.deute_http(429, "Die Boerse")
    assert "Tor" not in satz and "Abstand" in satz


def test_ein_fehler_der_gegenseite_verlangt_nichts_von_uns():
    for code in (500, 502, 503):
        satz = abweisung.deute_http(code, "Die Quelle")
        assert "etwas zu tun" in satz
