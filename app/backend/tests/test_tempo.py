"""Tests zur Hochrechnung der Restdauer."""
from satcortex import tempo


def test_ohne_genug_daten_gibt_es_keine_schaetzung():
    """Lieber gar keine Zahl als eine erfundene."""
    v = tempo.Verlauf()
    assert v.schaetzung() is None

    v.merke(0.10, 100_000, jetzt=1000)
    assert v.schaetzung() is None, "ein einzelner Punkt ergibt keine Rate"

    v.merke(0.11, 101_000, jetzt=1000 + 30)
    assert v.schaetzung() is None, "30 Sekunden sind Rauschen, keine Messung"


def test_rechnet_restdauer_aus_dem_gemessenen_tempo():
    v = tempo.Verlauf()
    # In einer Stunde von 20 % auf 30 % -- also noch 70 %, macht sieben Stunden.
    v.merke(0.20, 400_000, jetzt=0)
    v.merke(0.30, 460_000, jetzt=3600)

    s = v.schaetzung()
    assert s["rest_sekunden"] == 7 * 3600
    assert s["bloecke_pro_minute"] == 1000.0
    assert s["gemessen_ueber_sekunden"] == 3600


def test_ohne_fortschritt_keine_restdauer_aber_ein_tempo():
    """Steht die Pruefarbeit still, ist die Restdauer unendlich -- dann gehoert
    dort nichts hin. Die Blockrate bleibt trotzdem eine ehrliche Auskunft."""
    v = tempo.Verlauf()
    v.merke(0.42, 500_000, jetzt=0)
    v.merke(0.42, 500_000, jetzt=600)

    s = v.schaetzung()
    assert s["rest_sekunden"] is None
    assert s["bloecke_pro_minute"] == 0.0


def test_altes_faellt_aus_dem_fenster():
    """Die ersten Bloecke fliegen durch, spaetere kosten ein Vielfaches. Ein
    Mittel ueber die ganze Laufzeit waere dauerhaft zu optimistisch."""
    v = tempo.Verlauf(fenster_sekunden=1800)
    v.merke(0.05, 100_000, jetzt=0)          # faellt spaeter heraus
    v.merke(0.40, 500_000, jetzt=3600)
    v.merke(0.41, 505_000, jetzt=5000)

    s = v.schaetzung()
    assert s["gemessen_ueber_sekunden"] == 1400, "nur das Fenster zaehlt"


def test_zwei_punkte_bleiben_immer_erhalten():
    """Sonst gaebe es nach einer Pause gar keine Grundlage mehr."""
    v = tempo.Verlauf(fenster_sekunden=60)
    v.merke(0.10, 100_000, jetzt=0)
    v.merke(0.20, 200_000, jetzt=10_000)
    assert v.schaetzung() is not None

