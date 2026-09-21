import json

import pytest

from satcortex.state import Ablage, Einrichtung, Schritt, REIHENFOLGE


def test_start_ist_willkommen():
    e = Einrichtung()
    assert e.schritt is Schritt.WILLKOMMEN
    assert not e.fertig


def test_weiter_geht_die_reihenfolge_durch():
    e = Einrichtung()
    gesehen = [e.schritt]
    while not e.fertig:
        gesehen.append(e.weiter())
    assert gesehen == REIHENFOLGE


def test_antworten_werden_dem_richtigen_schritt_zugeordnet():
    e = Einrichtung()
    e.weiter({"gelesen": True})                 # willkommen
    e.weiter({"bulk": "/bulk"})                 # speicher
    assert e.antworten["willkommen"] == {"gelesen": True}
    assert e.antworten["speicher"] == {"bulk": "/bulk"}


def test_blaettern_allein_richtet_nichts_ein():
    """Bis ans Ende zu blaettern ist noch keine Einrichtung.

    Vorher setzte weiter() den Zeitstempel selbst, sobald der letzte Schritt
    erreicht war. Damit galt die Einrichtung als erledigt, bevor irgendetwas
    geschrieben wurde -- und die Sperre gegen doppeltes Einrichten schlug zu,
    noch bevor man den Knopf druecken konnte.
    """
    e = Einrichtung()
    while not e.fertig:
        e.weiter()
    assert e.fertig is True              # auf dem letzten Schritt
    assert e.eingerichtet is False       # aber nichts getan
    assert e.abgeschlossen_am is None


def test_erst_das_markieren_macht_eingerichtet():
    e = Einrichtung()
    while not e.fertig:
        e.weiter()
    e.als_eingerichtet_markieren()
    assert e.eingerichtet is True
    assert e.abgeschlossen_am is not None


def test_weiter_nach_dem_ende_bleibt_am_ende():
    e = Einrichtung()
    while not e.fertig:
        e.weiter()
    zeitpunkt = e.abgeschlossen_am
    e.weiter()
    assert e.schritt is Schritt.FERTIG
    assert e.abgeschlossen_am == zeitpunkt      # wird nicht ueberschrieben


def test_zurueckblaettern():
    e = Einrichtung()
    e.weiter(); e.weiter()
    assert e.schritt is Schritt.LEISTUNG
    assert e.zurueck() is Schritt.SPEICHER


def test_vor_dem_ersten_schritt_gibt_es_kein_zurueck():
    e = Einrichtung()
    assert e.zurueck() is Schritt.WILLKOMMEN


def test_auf_der_zusammenfassung_darf_man_zurueck():
    """Dort korrigiert man seine Wahl, bevor man ausloest."""
    e = Einrichtung()
    while not e.fertig:
        e.weiter()
    assert e.zurueck() is not Schritt.FERTIG


def test_nach_der_einrichtung_bleibt_es_dabei():
    e = Einrichtung()
    while not e.fertig:
        e.weiter()
    e.als_eingerichtet_markieren()
    assert e.zurueck() is Schritt.FERTIG


def test_darstellung_zeigt_fortschritt():
    e = Einrichtung(); e.weiter(); e.weiter()
    d = e.to_dict()
    assert d["nummer"] == 3
    assert d["von"] == len(REIHENFOLGE)
    erledigt = [s["name"] for s in d["schritte"] if s["erledigt"]]
    assert erledigt == ["willkommen", "speicher"]


# ------------------------------------------------------------------ Ablage

def test_zustand_ueberlebt_einen_neustart(tmp_path):
    a = Ablage(str(tmp_path))
    e = a.laden()
    e.weiter({"gelesen": True})
    a.speichern(e)

    wieder = Ablage(str(tmp_path)).laden()
    assert wieder.schritt is Schritt.SPEICHER
    assert wieder.antworten["willkommen"] == {"gelesen": True}


def test_ohne_datei_faengt_es_von_vorn_an(tmp_path):
    assert Ablage(str(tmp_path)).laden().schritt is Schritt.WILLKOMMEN


def test_kaputte_datei_fuehrt_nicht_zum_absturz(tmp_path):
    a = Ablage(str(tmp_path))
    a.datei.write_text("{das ist kein json", encoding="utf-8")
    assert a.laden().schritt is Schritt.WILLKOMMEN


def test_unbekannter_schritt_fuehrt_nicht_zum_absturz(tmp_path):
    a = Ablage(str(tmp_path))
    a.datei.write_text(json.dumps({"schritt": "gibtsnicht"}), encoding="utf-8")
    assert a.laden().schritt is Schritt.WILLKOMMEN


def test_speichern_hinterlaesst_keine_reste(tmp_path):
    a = Ablage(str(tmp_path))
    a.speichern(a.laden())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["einrichtung.json"]
