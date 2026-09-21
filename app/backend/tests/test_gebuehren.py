"""Was das Netz fuers Weiterleiten nimmt.

Zwei Dinge werden hier geprueft, und sie sind verschieden schwer.

Das Leichte ist die Rechnung: Median, Band, Vorschlag. Das Schwere ist das
Lesen -- ein Dokument von zweistelligen Megabyte stueckweise zu zerlegen,
ohne es je ganz im Speicher zu haben. Dort sitzen die Fehler, die man einer
Zahl spaeter nicht mehr ansieht: eine Klammer in einem Text, ein Umlaut
zwischen zwei Haeppchen, eine Leitung, die mittendrin abreisst.
"""
import json
import re
from pathlib import Path

import pytest

from satcortex import gebuehren


# ---------------------------------------------------------------- Hilfen

def _kante(satz1=None, satz2=None, basis1=0, basis2=0,
           aus1=False, aus2=False, pub1="01" * 33, pub2="02" * 33):
    kante = {"channel_id": "1", "node1_pub": pub1, "node2_pub": pub2}
    for nummer, satz, basis, aus in ((1, satz1, basis1, aus1),
                                     (2, satz2, basis2, aus2)):
        if satz is None and not aus:
            continue
        politik = {}
        if satz is not None:
            politik["fee_rate_milli_msat"] = str(satz)
        if basis:
            politik["fee_base_msat"] = str(basis)
        if aus:
            politik["disabled"] = True
        kante[f"node{nummer}_policy"] = politik
    return kante


def _graph(kanten, knoten=None):
    return json.dumps({"nodes": knoten or [], "edges": kanten}).encode("utf-8")


def _haeppchen(roh, groesse):
    return [roh[i:i + groesse] for i in range(0, len(roh), groesse)]


# ------------------------------------------------------- Das Lesen im Strom

def test_die_kanten_kommen_einzeln_heraus():
    roh = _graph([_kante(50), _kante(150)])
    assert len(list(gebuehren.elemente([roh], "edges"))) == 2


@pytest.mark.parametrize("groesse", [1, 2, 3, 7, 64, 100000])
def test_die_haeppchengroesse_aendert_nichts(groesse):
    """Die Grenze zwischen zwei Haeppchen faellt irgendwohin -- mitten in
    einen Schluessel, mitten in eine Zahl, mitten in einen Umlaut. Keine
    dieser Stellen darf ein anderes Ergebnis liefern."""
    roh = _graph([_kante(50), _kante(150), _kante(70)],
                 knoten=[{"alias": "Knoten mit Umlauten: ÄÖÜ und 🛰"}])
    gelesen = list(gebuehren.elemente(_haeppchen(roh, groesse), "edges"))
    assert [k["node1_pub"] for k in gelesen] == ["01" * 33] * 3
    assert len(gelesen) == 3


def test_klammern_in_einem_text_zaehlen_nicht():
    """Ein Alias darf alles enthalten -- auch das, was wie Struktur aussieht.

    Genau daran scheitert jeder Ansatz, der mit einem Suchmuster ueber den
    Rohtext geht statt die Struktur zu verfolgen.
    """
    roh = _graph([_kante(50)],
                 knoten=[{"alias": '}] ,"edges": [ {"fee_rate_milli_msat":"9"}'}])
    gelesen = list(gebuehren.elemente([roh], "edges"))
    assert len(gelesen) == 1
    assert gelesen[0]["node1_policy"]["fee_rate_milli_msat"] == "50"


def test_entwertete_anfuehrungszeichen_beenden_keinen_text():
    roh = _graph([_kante(50)], knoten=[{"alias": 'er sagte \\"edges\\": ['}])
    assert len(list(gebuehren.elemente([roh], "edges"))) == 1


def test_derselbe_name_als_WERT_ist_kein_feld():
    """"edges" kann auch rechts vom Doppelpunkt stehen. Dann ist es Text."""
    roh = json.dumps({"woher": "edges", "edges": [_kante(50)]}).encode("utf-8")
    assert len(list(gebuehren.elemente([roh], "edges"))) == 1


def test_derselbe_name_eine_ebene_tiefer_ist_kein_feld():
    roh = json.dumps({"fremd": {"edges": [_kante(9), _kante(9)]},
                      "edges": [_kante(50)]}).encode("utf-8")
    gelesen = list(gebuehren.elemente([roh], "edges"))
    assert len(gelesen) == 1
    assert gelesen[0]["node1_policy"]["fee_rate_milli_msat"] == "50"


def test_nach_der_liste_wird_nicht_weitergelesen():
    """Sobald die Kanten durch sind, endet das Lesen -- der Rest der Antwort
    wird gar nicht mehr vom Betriebssystem geholt."""
    roh = json.dumps({"edges": [_kante(50)], "nodes": [{"a": 1}]}).encode("utf-8")
    angefasst = []

    def zaehlend():
        for stueck in _haeppchen(roh, 8):
            angefasst.append(stueck)
            yield stueck

    list(gebuehren.elemente(zaehlend(), "edges"))
    assert b"".join(angefasst) != roh, "es wurde bis zum Ende gelesen"


def test_eine_abgerissene_leitung_wird_nicht_zur_halben_messung():
    """DER Fall, der still falsch waere: die Verbindung endet mitten in den
    Kanten. Eine halbe Messung sieht einer ganzen zum Verwechseln aehnlich --
    und stuende vier Wochen lang im Band."""
    roh = _graph([_kante(50), _kante(150)])
    with pytest.raises(gebuehren.GraphAbgerissen):
        list(gebuehren.elemente([roh[:len(roh) - 20]], "edges"))


def test_ein_fehlendes_feld_liefert_einfach_nichts():
    roh = json.dumps({"nodes": []}).encode("utf-8")
    assert list(gebuehren.elemente([roh], "edges")) == []


def test_die_notbremse_greift():
    roh = _graph([_kante(50)] * 10)
    with pytest.raises(gebuehren.GraphZuGross):
        list(gebuehren.begrenzt(_haeppchen(roh, 16), hoechstens=32))


def test_unterhalb_der_notbremse_bleibt_alles_gleich():
    roh = _graph([_kante(50)] * 10)
    durch = b"".join(gebuehren.begrenzt(_haeppchen(roh, 16),
                                        hoechstens=len(roh)))
    assert durch == roh


# ------------------------------------------------------------- Die Rechnung

def test_der_median_kommt_aus_beiden_richtungen():
    kanten = [_kante(10, 20), _kante(30, 40)]
    d = gebuehren.auswerten(kanten)
    assert d["linien"] == 4
    assert d["kanaele"] == 2
    assert d["median_ppm"] == 25


def test_eine_fehlende_gebuehr_ist_null_und_nicht_nichts():
    """In der JSON-Abbildung von protobuf fehlen Felder mit Vorgabewert.

    Eine Linie mit null ppm hat also womoeglich gar kein
    "fee_rate_milli_msat" -- und null ppm ist ein voellig gewoehnlicher Wert.
    Wer "fehlt" als "ueberspringen" liest, laesst die guenstigsten Kanaele
    des Netzes aus und bekommt einen zu hohen Median. Hier: vier Linien, zwei
    davon ohne Feld. Mit ihnen ist der Median 5, ohne sie waere er 15.
    """
    kanten = [{"node1_pub": "a", "node2_pub": "b",
               "node1_policy": {}, "node2_policy": {}},
              _kante(10, 20)]
    d = gebuehren.auswerten(kanten)
    assert d["linien"] == 4
    assert d["median_ppm"] == 5


def test_eine_fehlende_LINIE_zaehlt_dagegen_nicht_mit():
    """"kein Feld in der Linie" und "gar keine Linie" sind zweierlei."""
    kanten = [{"node1_pub": "a", "node2_pub": "b"}, _kante(10, 20)]
    d = gebuehren.auswerten(kanten)
    assert d["linien"] == 2
    assert d["median_ppm"] == 15


def test_abgeschaltete_richtungen_bleiben_draussen():
    """Durch eine abgeschaltete Richtung geht nichts -- ihr Preis ist keiner.

    Sie wird trotzdem gezaehlt, damit die Zahl daneben erklaerbar bleibt.
    """
    kanten = [_kante(10, 9999, aus2=True), _kante(20, 30)]
    d = gebuehren.auswerten(kanten)
    assert d["abgeschaltet"] == 1
    assert d["linien"] == 3
    assert d["median_ppm"] == 20


def test_der_eigene_satz_wird_aus_dem_graphen_gelesen():
    """Nicht aus der Erinnerung, sondern aus dem, was das Netz von uns sieht."""
    ich = "03" + "cd" * 32
    kanten = [_kante(11, 22, pub1=ich), _kante(33, 44, pub2=ich),
              _kante(55, 66)]
    d = gebuehren.auswerten(kanten, eigene_kennung=ich)
    # Unsere beiden Linien: 11 (als node1) und 44 (als node2).
    assert d["eigen"]["linien"] == 2
    assert d["eigen"]["satz_ppm"] == 27


def test_ohne_eigene_kennung_bleibt_der_eigene_satz_leer():
    d = gebuehren.auswerten([_kante(11, 22)])
    assert d["eigen"]["linien"] == 0
    assert d["eigen"]["satz_ppm"] is None


def test_zahlen_kommen_als_zeichenkette_und_als_zahl_an():
    """LND schickt 64-Bit-Werte als Text. Beides muss ankommen."""
    kanten = [{"node1_pub": "a", "node2_pub": "b",
               "node1_policy": {"fee_rate_milli_msat": 40},
               "node2_policy": {"fee_rate_milli_msat": "60"}}]
    assert gebuehren.auswerten(kanten)["median_ppm"] == 50


def test_ein_leerer_graph_liefert_keinen_median():
    d = gebuehren.auswerten([])
    assert d["median_ppm"] is None and d["linien"] == 0


# ------------------------------------------------------------------ Das Band

def _reihe(werte, ab="2026-08-%02d"):
    return [{"tag": ab % (i + 1), "median_ppm": w}
            for i, w in enumerate(werte)]


def test_das_band_ist_min_und_max_der_messtage():
    d = gebuehren.band(_reihe([90, 120, 100, 140, 110]))
    assert (d["unten_ppm"], d["oben_ppm"], d["tage"]) == (90, 140, 5)


def test_der_heutige_tag_gehoert_nicht_ins_eigene_band():
    """Der Punkt, an dem das Band ueberhaupt erst eine Absicherung ist.

    Zaehlte die heutige Messung mit, laege sie IMMER innerhalb ihres eigenen
    Bandes -- ein Ausreisser wuerde sich seine Grenze selbst aufmachen und
    ungebremst durchschlagen. Genau davor soll das Band schuetzen.
    """
    reihe = _reihe([90, 120, 100]) + [{"tag": "heute", "median_ppm": 9000}]
    mit = gebuehren.band(reihe)
    ohne = gebuehren.band(reihe, ohne_tag="heute")
    assert mit["oben_ppm"] == 9000
    assert ohne["oben_ppm"] == 120 and ohne["tage"] == 3


def test_tage_ohne_messwert_zaehlen_nicht_mit():
    reihe = _reihe([90, None, 120])
    assert gebuehren.band(reihe)["tage"] == 2


def test_ohne_messungen_gibt_es_kein_band():
    d = gebuehren.band([])
    assert d == {"tage": 0, "unten_ppm": None, "oben_ppm": None}


# -------------------------------------------------------------- Der Vorschlag

def _volles_band(unten=80, oben=140, tage=gebuehren.MINDESTENS_TAGE):
    return {"tage": tage, "unten_ppm": unten, "oben_ppm": oben}


def test_innerhalb_des_bandes_gilt_der_median():
    d = gebuehren.vorschlag(110, _volles_band(), jetzt_ppm=50)
    assert (d["satz_ppm"], d["grund"], d["handeln"]) == (110, "median", True)


def test_ueber_dem_band_wird_gedeckelt():
    d = gebuehren.vorschlag(5000, _volles_band(), jetzt_ppm=100)
    assert (d["satz_ppm"], d["grund"]) == (140, "gedeckelt")


def test_unter_dem_band_wird_angehoben():
    d = gebuehren.vorschlag(3, _volles_band(), jetzt_ppm=100)
    assert (d["satz_ppm"], d["grund"]) == (80, "angehoben")


def test_ohne_genug_messtage_ruehrt_die_automatik_nichts_an():
    d = gebuehren.vorschlag(110, _volles_band(tage=gebuehren.MINDESTENS_TAGE - 1))
    assert d["handeln"] is False and d["grund"] == "sammelt_noch"


def test_ein_winziger_unterschied_loest_keine_meldung_ans_netz_aus():
    """Jede Aenderung ist ein channel_update ins ganze Netz. Wer wegen zwei
    ppm taeglich funkt, faellt bei den Gegenstellen unter deren
    Ratenbegrenzung und erreicht am Ende weniger als wer stillhaelt."""
    d = gebuehren.vorschlag(102, _volles_band(), jetzt_ppm=100)
    assert d["handeln"] is False and d["grund"] == "unveraendert"


def test_ohne_messung_gibt_es_keinen_vorschlag():
    d = gebuehren.vorschlag(None, _volles_band(), jetzt_ppm=100)
    assert d["satz_ppm"] is None and d["handeln"] is False


def test_die_absolute_obergrenze_gilt_auch_ohne_band():
    d = gebuehren.vorschlag(999_999, {"tage": 0}, jetzt_ppm=0)
    assert d["satz_ppm"] == gebuehren.HOECHSTSATZ_PPM


# ----------------------------------------------------------------- Der Tag

def test_der_tag_ist_utc():
    # 2026-01-01 00:30 UTC -- in Ortszeit Berlin waere das schon der 1., in
    # Ortszeit Honolulu noch der 31.12. Die Messreihe darf davon nicht
    # abhaengen, sonst hat ein Tag zwei Messungen und ein anderer keine.
    assert gebuehren.heute(1767227400.0) == "2026-01-01"


# ------------------------------------------------- Die Felder sind nachgesehen

def _felder():
    datei = Path(__file__).with_name("lnd_graph_felder.tsv")
    tabelle = {}
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        if not zeile or zeile.startswith("#"):
            continue
        nachricht, feld, _typ = zeile.split("\t")
        tabelle.setdefault(nachricht, set()).add(feld)
    return tabelle


def test_jeder_benutzte_feldname_steht_in_LNDs_eigener_tabelle():
    """Kein Feldname aus der Erinnerung.

    gebuehren.py greift auf eine Handvoll Felder des Netzgraphen zu. Sie
    stehen in lnd_graph_felder.tsv, erzeugt aus lnrpc/lightning.proto des
    Tags v0.21.3-beta. Benennt LND eines um, wird dieser Test rot -- und
    nicht der Median still leer.
    """
    tabelle = _felder()
    quelle = Path(gebuehren.__file__).read_text(encoding="utf-8")
    benutzt = {
        "ChannelGraph": {gebuehren.GRAPH_FELD},
        "ChannelEdge": set(re.findall(r'"(node[12]_(?:pub|policy))"', quelle)),
        "RoutingPolicy": set(re.findall(
            r'"(fee_rate_milli_msat|fee_base_msat|disabled)"', quelle)),
    }
    assert benutzt["ChannelEdge"] == {"node1_pub", "node2_pub",
                                      "node1_policy", "node2_policy"}
    assert benutzt["RoutingPolicy"] == {"fee_rate_milli_msat",
                                        "fee_base_msat", "disabled"}
    for nachricht, felder in benutzt.items():
        fehlend = felder - tabelle[nachricht]
        assert not fehlend, f"{nachricht}: {fehlend} kennt LND nicht"


def test_der_graphpfad_steht_in_LNDs_routentabelle():
    datei = Path(__file__).with_name("lnd_rest_routen.tsv")
    routen = {zeile.split("\t")[1] for zeile in
              datei.read_text(encoding="utf-8").splitlines()
              if zeile and not zeile.startswith("#")}
    assert gebuehren.GRAPH_PFAD in routen


# ── Die Verteilung statt der Erklaerung ────────────────────────────────────
#
# Der Betreiber, 21.09.2026, zu dem Absatz, der unter dem Median stand: "was
# das den bitte fuer ein riesen text ?? ... kann mann nicht einfach machen:
# 50% 0-100 die anderen 50% 100-600".
#
# Doch. Der Absatz erklaerte in fuenf Zeilen, dass die Verteilung schief ist.
# Ein paar Prozentzahlen ZEIGEN es -- und sagen nebenbei mehr, als der Absatz
# je gesagt hat.

def test_die_verteilung_zeigt_die_form_der_saetze():
    saetze = ([0] * 4          # nimmt nichts
              + [1, 5, 9]      # 1 bis 9
              + [10, 99]       # 10 bis 99
              + [100]          # 100 bis 999
              )                # zusammen zehn
    stufen = gebuehren.verteilung(saetze)
    assert [s["anteil"] for s in stufen] == [40, 30, 20, 10, 0]
    # Die Stufen sagen selbst, wofuer sie stehen -- die Oberflaeche muss
    # nichts ueber die Grenzen wissen.
    assert stufen[0] == {"von": 0, "bis": 0, "anteil": 40}
    assert stufen[1]["von"] == 1 and stufen[1]["bis"] == 9
    assert stufen[4] == {"von": 1000, "bis": None, "anteil": 0}


def test_die_anteile_ergeben_genau_hundert():
    """Wer nachrechnet, soll recht behalten.

    Drei Drittel ergeben einzeln gerundet 33 + 33 + 33 = 99. Unter einer
    Zeile, die "so verteilt sich das Netz" heisst, ist das ein Widerspruch,
    den der Leser findet und nicht erklaeren kann.
    """
    for saetze in ([0, 5, 50],                       # drei Drittel
                   [0] * 3 + [5] * 3 + [50],         # sieben
                   list(range(0, 2000, 7)),          # krumm
                   [0, 0, 1, 10, 100, 1000, 5000]):
        assert sum(s["anteil"] for s in gebuehren.verteilung(saetze)) == 100


def test_ohne_saetze_wird_keine_verteilung_behauptet():
    assert gebuehren.verteilung([]) == []


def test_sehr_hohe_saetze_landen_in_der_obersten_stufe():
    """Nach oben gibt es im Lightning-Netz keine Grenze -- die oberste Stufe
    ist deshalb offen und nicht "1000 bis 2000"."""
    stufen = gebuehren.verteilung([50_000, 1_000, 999_999])
    assert stufen[4]["anteil"] == 100
    assert stufen[4]["bis"] is None


def test_die_verteilung_kommt_aus_der_auswertung_mit():
    d = gebuehren.auswerten([_kante(satz1=0, satz2=0),
                             _kante(satz1=100, satz2=2_000)])
    assert [s["anteil"] for s in d["stufen"]] == [50, 0, 0, 25, 25]
