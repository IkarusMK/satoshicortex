"""Gebuehr und Hoechstbetrag je Kanal nach Fuellstand -- die Rechenregeln.

Aus dem Betrieb, 30.09.2026: ein Schwall, der einen Kanal fuer ein paar
Minuten leert und gleich zurueckfliesst, darf nichts umstellen. Deshalb:
Durchschnitt statt Augenblick, Hysterese an den Stufengrenzen, hoechstens
eine Aenderung je Abstand -- und ohne Messreihe gar keine.
"""
import pytest

from satcortex import kanalsteuerung as ks


@pytest.mark.parametrize("anteil, stufe", [
    (1.0, 1), (0.80, 1), (0.79, 2), (0.50, 2), (0.49, 3), (0.20, 3),
    (0.19, 4), (0.0, 4), (-0.1, 4), (1.3, 1)])
def test_die_stufe_folgt_dem_anteil_auf_deiner_seite(anteil, stufe):
    assert ks.stufe(anteil) == stufe


@pytest.mark.parametrize("anteil, bisher, erwartet", [
    (0.47, 2, 2),     # knapp unter der Grenze 50 %: bleibt
    (0.44, 2, 3),     # deutlich darunter: wechselt
    (0.83, 2, 2),     # knapp ueber 80 %: bleibt
    (0.86, 2, 1),
    (0.22, 4, 4),     # knapp ueber 20 %, vorher fast leer: bleibt
    (0.26, 4, 3),
    (0.60, 4, 2),     # weit weg: springt direkt
])
def test_an_den_grenzen_wird_nicht_hin_und_her_geschaltet(anteil, bisher, erwartet):
    assert ks.stufe(anteil, bisher) == erwartet


def test_der_satz_richtet_sich_am_netz_mittel_aus():
    assert [ks.satz(100, s) for s in (1, 2, 3, 4)] == [50, 100, 150, 300]
    assert ks.satz(9000, 4) == ks.HOECHSTSATZ_PPM, "gedeckelt"
    assert ks.satz(0, 4) == 0


@pytest.mark.parametrize("verfuegbar, kapazitaet, grenze, erwartet", [
    (3_460_000, 4_000_000, 3_960_000, 1_730_000),   # Haelfte, auf 10.000 gerundet
    (3_469_999, 4_000_000, 3_960_000, 1_730_000),
    (0, 4_000_000, 3_960_000, 40_000),              # nie unter 1 % der Kapazitaet
    (9_000_000, 4_000_000, 3_960_000, 3_960_000),   # nie ueber LNDs Grenze
    (64_000, 100_000, 99_000, 30_000),
])
def test_der_hoechstbetrag_folgt_dem_ausgebbaren(verfuegbar, kapazitaet, grenze, erwartet):
    assert ks.hoechstbetrag(verfuegbar, kapazitaet, grenze) == erwartet


def test_faellig_ist_erst_nach_dem_abstand():
    tag = 86_400
    assert ks.faellig(None, 10 * tag, 1)
    assert not ks.faellig(10 * tag, 10 * tag + 20 * 3600, 1)
    assert ks.faellig(10 * tag, 11 * tag, 1)
    # Der taegliche Lauf kommt nicht auf die Minute -- zehn Minuten Spiel.
    assert ks.faellig(10 * tag, 11 * tag - 300, 1)
    assert not ks.faellig(10 * tag, 12 * tag, 3)
    assert ks.faellig(10 * tag, 13 * tag, 3)


KANAL = {"punkt": "ab:1", "kapazitaet": 4_000_000, "hier": 800_000,
         "verfuegbar": 760_000, "anteil_hier": 0.2, "hinaus_hoechstens": 3_960_000}


def test_geplant_wird_mit_dem_durchschnitt_nicht_mit_dem_augenblick():
    """Gerade ist der Kanal fast leer (20 %), im Tagesschnitt aber
    ausgewogen (60 %). Entschieden wird nach dem Schnitt."""
    plan = ks.planen(KANAL, {"anteil": 0.60, "verfuegbar": 2_360_000},
                     anker_ppm=100, eintrag={}, jetzt_ppm=100,
                     jetzt_hoechstbetrag_sat=1_180_000)
    assert (plan["stufe"], plan["satz_ppm"]) == (2, 100)
    assert plan["hoechstbetrag_sat"] == 1_180_000
    assert plan["gebuehr_handeln"] is False, "gleicher Satz: nichts zu tun"
    assert plan["hoechstbetrag_handeln"] is False


def test_ohne_messreihe_zaehlt_der_augenblick():
    plan = ks.planen(KANAL, None, anker_ppm=100, eintrag={}, jetzt_ppm=100,
                     jetzt_hoechstbetrag_sat=None)
    assert plan["stufe"] == 3 and plan["satz_ppm"] == 150
    assert plan["gebuehr_handeln"] is True
    assert plan["hoechstbetrag_handeln"] is True


def test_kleine_abweichungen_loesen_nichts_aus():
    plan = ks.planen(KANAL, {"anteil": 0.60, "verfuegbar": 2_360_000},
                     anker_ppm=100, eintrag={"stufe": 2}, jetzt_ppm=97,
                     jetzt_hoechstbetrag_sat=1_000_000)
    assert plan["gebuehr_handeln"] is False, "unter 5 ppm Abstand"
    assert plan["hoechstbetrag_handeln"] is False, "unter 25 % Abweichung"


def test_ohne_anker_setzt_die_automatik_keine_gebuehr():
    """Ohne Netzmessung gibt es kein Mittel, an dem sich die Stufe
    ausrichten koennte -- dann bleibt die Gebuehr, wie sie ist."""
    plan = ks.planen(KANAL, None, anker_ppm=None, eintrag={}, jetzt_ppm=100,
                     jetzt_hoechstbetrag_sat=None)
    assert plan["satz_ppm"] is None and plan["gebuehr_handeln"] is False


def test_die_wirksame_wahl_eines_kanals():
    """Ohne eigene Wahl folgt ein Kanal dem Schalter fuer alle. Wer einen
    Kanal auf fest stellt, dem fasst keine Automatik ihn an."""
    assert ks.wahl({}, alle_automatik=False) == ("fest", "fest")
    assert ks.wahl({}, alle_automatik=True) == ("automatik", "fuellstand")
    assert ks.wahl({"gebuehr": "fest"}, alle_automatik=True) == ("fest", "fest")
    assert ks.wahl({"gebuehr": "automatik"}, alle_automatik=False) == (
        "automatik", "fuellstand")
    assert ks.wahl({"gebuehr": "automatik", "hoechstbetrag": "fest"},
                   alle_automatik=False) == ("automatik", "fest")
    assert ks.wahl({"gebuehr": "fest", "hoechstbetrag": "fuellstand"},
                   alle_automatik=False) == ("fest", "fuellstand")


def test_ohne_messreihe_gibt_es_keinen_durchschnitt():
    """Direkt nach dem Update, bei einem neuen Kanal: eine einzelne Messung
    ist der Augenblick, kein Durchschnitt. Erst der halbe Abstand zaehlt --
    stuendlich gemessen 12 Messungen fuer einen Tag, 36 fuer drei."""
    assert ks.messreihe_reicht(None, 1) is False
    assert ks.messreihe_reicht({}, 1) is False
    assert ks.messreihe_reicht({"messungen": 1}, 1) is False
    assert ks.messreihe_reicht({"messungen": 11}, 1) is False
    assert ks.messreihe_reicht({"messungen": 12}, 1) is True
    assert ks.messreihe_reicht({"messungen": 35}, 3) is False
    assert ks.messreihe_reicht({"messungen": 36}, 3) is True
