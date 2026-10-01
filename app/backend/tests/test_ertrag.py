"""Was jeder Kanal eingebracht hat und was er gekostet hat.

Alle Zahlen ausgedacht.
"""
from satcortex import ertrag

TAG = 86_400
JETZT = 1_790_000_000          # irgendwann Ende September 2026
A, B, C = "1001", "1002", "1003"

OFFEN = [{"nummer": A, "gegenstelle": "Alpha", "kapazitaet": 2_000_000},
         {"nummer": B, "gegenstelle": "Beta", "kapazitaet": 1_000_000}]
ZU = [{"nummer": C, "name": "", "kapazitaet": 500_000}]


def _w(tage_her, rein, raus, raus_sat, gebuehr_msat, **name):
    return {"zeit_s": JETZT - tage_her * TAG, "rein": rein, "raus": raus,
            "rein_sat": raus_sat + gebuehr_msat // 1000, "raus_sat": raus_sat,
            "gebuehr_msat": gebuehr_msat, **name}


WEITER = [
    _w(1, B, A, 100_000, 25_500),      # verdient bei A (hinaus), 25,5 sat
    _w(2, B, A, 60_000, 12_500),
    _w(10, A, B, 80_000, 40_000),      # bei B
    _w(45, B, A, 10_000, 5_000),       # ausserhalb von 30 Tagen
    _w(200, A, C, 20_000, 9_000, raus_name="Gamma"),   # zu einem geschlossenen Kanal
]
OEFFNEN = {A: {"sat": 400, "zeit_s": JETZT - 100 * TAG},
           B: {"sat": 350, "zeit_s": JETZT - 20 * TAG}}
SCHLIESSEN = {C: {"sat": 300, "zeit_s": JETZT - 150 * TAG}}
UMSCHICHTEN = [{"zeit_s": JETZT - 5 * TAG, "rein_kanal": A, "gebuehr_sat": 120}]


def _rechnen(tage):
    return ertrag.rechnen(WEITER, OEFFNEN, SCHLIESSEN, UMSCHICHTEN, OFFEN, ZU,
                          tage=tage, jetzt_s=JETZT, hoehe=900_000)


def test_die_gebuehr_zaehlt_beim_ausgehenden_kanal():
    d = _rechnen(30)
    je = {k["nummer"]: k for k in d["kanaele"]}
    assert je[A]["zeitraum"]["eingenommen_sat"] == 38      # 25,5 + 12,5
    assert je[A]["zeitraum"]["weiterleitungen"] == 2
    assert je[A]["zeitraum"]["raus_sat"] == 160_000
    assert je[B]["zeitraum"]["eingenommen_sat"] == 40
    # Beta hat auch Durchsatz HEREIN -- er zaehlt, verdient wird aber hinaus.
    assert je[B]["zeitraum"]["rein_sat"] == 160_000 + 25 + 12


def test_kosten_zaehlen_im_zeitraum_und_beim_richtigen_kanal():
    d = _rechnen(30)
    je = {k["nummer"]: k for k in d["kanaele"]}
    # Alpha: vor 100 Tagen eroeffnet (nicht im Zeitraum), vor 5 Tagen
    # aufgefuellt -- das Umschichten zaehlt beim AUFGEFUELLTEN Kanal.
    assert je[A]["zeitraum"]["kosten_sat"] == 120
    assert je[A]["zeitraum"]["netto_sat"] == 38 - 120
    # Beta: vor 20 Tagen eroeffnet.
    assert je[B]["zeitraum"]["kosten_sat"] == 350
    assert d["summe"] == {"eingenommen_sat": 78, "kosten_sat": 470,
                          "netto_sat": 78 - 470, "weiterleitungen": 3,
                          "raus_sat": 240_000}


def test_seit_eroeffnung_steht_alles_drin():
    d = _rechnen(30)
    je = {k["nummer"]: k for k in d["kanaele"]}
    g = je[A]["gesamt"]
    assert (g["eingenommen_sat"], g["oeffnen_sat"], g["umschichten_sat"]) == (43, 400, 120)
    assert g["netto_sat"] == 43 - 400 - 120
    assert g["weiterleitungen"] == 3
    # Die 30 Tage fuer die Kanalzeile -- unabhaengig vom gewaehlten Zeitraum.
    assert _rechnen(7)["kanaele"][0]["tage30"] == {"eingenommen_sat": 38,
                                                   "netto_sat": 38 - 120}


def test_geschlossene_kanaele_stehen_mit_ihrer_schlussbilanz_da():
    d = _rechnen(0)
    zu = [k for k in d["kanaele"] if not k["offen"]]
    assert len(zu) == 1
    assert zu[0]["name"] == "Gamma", "der Name kommt aus den Weiterleitungen"
    assert zu[0]["gesamt"]["schliessen_sat"] == 300
    assert zu[0]["gesamt"]["eingenommen_sat"] == 9
    assert zu[0]["gesamt"]["netto_sat"] == 9 - 300


def test_ertrag_je_million_und_monat():
    """Damit Kanaele verschiedener Groesse vergleichbar werden."""
    d = _rechnen(30)
    je = {k["nummer"]: k for k in d["kanaele"]}
    assert je[A]["pro_mio_monat_sat"] == 19        # 38 sat auf 2 Mio in 30 Tagen
    assert je[B]["pro_mio_monat_sat"] == 40
    # Seit Beginn: geteilt durch das Alter des Kanals aus seiner Nummer --
    # ohne lesbare Nummer gibt es keine Rate statt einer erfundenen.
    assert je[A]["pro_mio_monat_sat"] is not None
    assert {k["nummer"]: k["pro_mio_monat_sat"] for k in _rechnen(0)["kanaele"]}[A] is None


def test_die_monate_stehen_in_der_richtigen_reihenfolge():
    d = _rechnen(30)
    monate = d["monate"]
    assert len(monate) == 6
    assert [m["monat"] for m in monate] == sorted(m["monat"] for m in monate)
    assert monate == [
        {"monat": "2026-04", "eingenommen_sat": 0, "kosten_sat": 300},   # geschlossen
        {"monat": "2026-05", "eingenommen_sat": 0, "kosten_sat": 0},
        {"monat": "2026-06", "eingenommen_sat": 0, "kosten_sat": 400},   # eroeffnet
        {"monat": "2026-07", "eingenommen_sat": 0, "kosten_sat": 0},
        {"monat": "2026-08", "eingenommen_sat": 5, "kosten_sat": 0},
        {"monat": "2026-09", "eingenommen_sat": 78, "kosten_sat": 470}]


def test_ohne_weiterleitungen_ist_alles_null_und_nichts_bricht():
    d = ertrag.rechnen([], {}, {}, [], OFFEN, [], tage=30, jetzt_s=JETZT,
                       hoehe=900_000)
    assert d["summe"]["eingenommen_sat"] == 0
    assert all(k["zeitraum"]["netto_sat"] == 0 for k in d["kanaele"])
