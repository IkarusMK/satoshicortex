"""Der Merker haelt genau ein Geheimnis -- im Speicher, sonst nirgends.

Er ist der Ersatz fuer den Tresor, den Aus dem Betrieb, 10.09.2026 zerlegt hat:
"ich tausche ein passwort gegen das andere obwohl beide die selbe funktion
unterm strich haben". Die Begruendung steht im Modul; hier steht, was er
tatsaechlich tut.
"""
import threading

from satcortex.merker import Merker


def test_frisch_ist_er_leer():
    m = Merker()
    assert m.hat is False
    assert m.hol() == ""


def test_er_gibt_zurueck_was_er_bekommen_hat():
    m = Merker()
    m.merke("ein-gutes-langes-passwort")
    assert m.hat is True
    assert m.hol() == "ein-gutes-langes-passwort"


def test_vergessen_heisst_vergessen():
    m = Merker()
    m.merke("ein-gutes-langes-passwort")
    m.vergiss()
    assert m.hat is False
    assert m.hol() == ""


def test_eine_leere_eingabe_merkt_nichts():
    """Sonst stuende "hat" auf wahr, waehrend nichts da ist -- und der
    Sammler wuerde LND eine leere Zeichenkette vorlegen."""
    m = Merker()
    m.merke("")
    assert m.hat is False
    m.merke(None)                                   # type: ignore[arg-type]
    assert m.hat is False


def test_er_haelt_immer_nur_das_letzte():
    m = Merker()
    m.merke("das-alte-passwort")
    m.merke("das-neue-passwort")
    assert m.hol() == "das-neue-passwort"


def test_er_vertraegt_zwei_faeden_gleichzeitig():
    """Geschrieben wird aus einer Anfrage, gelesen aus dem Sammlerfaden.
    Ohne Sperre waere das eine Wettlaufsituation an der einen Stelle, an der
    sie am teuersten ist."""
    m = Merker()
    m.merke("ein-gutes-langes-passwort")
    gelesen = []

    def lesen():
        for _ in range(500):
            gelesen.append(m.hol())

    faeden = [threading.Thread(target=lesen) for _ in range(4)]
    for f in faeden:
        f.start()
    for _ in range(500):
        m.merke("ein-gutes-langes-passwort")
    for f in faeden:
        f.join()

    assert set(gelesen) == {"ein-gutes-langes-passwort"}
