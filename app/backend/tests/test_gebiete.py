"""Ein Land, nach Bundeslaendern aufgeschluesselt.

Aus dem Betrieb, 05.09.2026: "dass man in der Weltkarte auf die einzelnen Laender
klicken kann und die dann gross werden und uns da in den einzelnen
Bundeslaendern zeigen, wo die Knoten sind, mit denen wir in Verbindung sind
... das gilt fuer jedes Land der Welt!" -- und dazu die Grenze, die die
Genauigkeit rettet: "wo genau in Bayern ist auch egal, es sollte halt nur
Bayern sein."
"""
import json
import pathlib

import pytest

from satcortex import gebiete

WURZEL = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def namen(tmp_path):
    datei = tmp_path / "regionen.json"
    datei.write_text(json.dumps({"gebiete": [
        {"n": 1, "land": "DE", "de": "Bayern", "en": "Bavaria",
         "iso": ["DE-BY"]},
        {"n": 2, "land": "DE", "de": "Berlin", "en": "Berlin",
         "iso": ["DE-BE"]},
        {"n": 3, "land": "FR", "de": "Auvergne-Rhône-Alpes",
         "en": "Auvergne-Rhône-Alpes", "iso": ["FR-01", "FR-03", "FR-07"]},
    ]}), encoding="utf-8")
    return gebiete.lade(str(datei))


def test_gebiete_lassen_sich_nach_land_finden(namen):
    assert [g["de"] for g in namen.eines_landes("DE")] == ["Bayern", "Berlin"]
    assert namen.eines_landes("de") == namen.eines_landes("DE")
    assert namen.eines_landes("XX") == []


def test_ein_gebiet_kann_mehrere_umrisse_haben(namen):
    """Natural Earth fuehrt Frankreich als 101 Departements, DB-IP als 13
    Regionen. Ein einzelnes Departement einzufaerben waere praeziser, als wir
    wissen koennen."""
    assert len(namen.eines(3)["iso"]) == 3


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    assert gebiete.lade(str(tmp_path / "gibtsnicht.json")) is None


def test_kaputte_datei_haelt_die_anwendung_nicht_auf(tmp_path):
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{kein json", encoding="utf-8")
    assert gebiete.lade(str(kaputt)) is None

    leer = tmp_path / "leer.json"
    leer.write_text('{"gebiete": []}', encoding="utf-8")
    assert gebiete.lade(str(leer)) is None


# ── Die ausgelieferte Zuordnung selbst ────────────────────────────────────

@pytest.fixture(scope="module")
def echt():
    return json.loads((WURZEL / "app" / "data" / "regionen.json")
                      .read_text(encoding="utf-8"))


def test_jedes_gebiet_hat_einen_namen_und_ein_land(echt):
    for g in echt["gebiete"]:
        assert g["de"] and g["en"], g
        assert len(g["land"]) == 2, g


def test_die_nummern_sind_luekenlos_und_beginnen_bei_eins(echt):
    """Null bedeutet "kein Gebiet bekannt" und darf keinem gehoeren."""
    nummern = [g["n"] for g in echt["gebiete"]]
    assert nummern == list(range(1, len(nummern) + 1))


def test_jeder_zugeordnete_name_zeigt_auf_ein_vorhandenes_gebiet(echt):
    vorhanden = {g["n"] for g in echt["gebiete"]}
    for name, nummer in echt["namen"].items():
        assert nummer in vorhanden, name


def test_der_name_gehoert_zum_land_des_gebiets(echt):
    """"DE|Bavaria" darf nicht auf ein franzoesisches Gebiet zeigen -- das
    waere still falsch und faellt auf der Karte niemandem auf."""
    nach_nummer = {g["n"]: g for g in echt["gebiete"]}
    for name, nummer in echt["namen"].items():
        land = name.split("|", 1)[0]
        assert nach_nummer[nummer]["land"] == land, name


def test_zu_jedem_umriss_gibt_es_eine_datei(echt):
    """Ein Gebiet, dessen Umrisse in keiner Landkarte stehen, laesst sich
    nicht einfaerben -- der Klick ginge ins Leere."""
    ordner = WURZEL / "app" / "web" / "regionen"
    fehlend = {g["land"] for g in echt["gebiete"]
               if g["iso"] and not (ordner / f"{g['land']}.svg").exists()}
    assert not fehlend, f"keine Regionskarte fuer: {sorted(fehlend)}"


def test_die_umrisse_der_zuordnung_stehen_auch_in_den_karten(echt):
    """Stichprobe ueber die Laender, die am ehesten jemand anklickt."""
    ordner = WURZEL / "app" / "web" / "regionen"
    for land in ("DE", "AT", "CH", "US", "AU", "FR", "ZA", "BR", "JP"):
        karte = (ordner / f"{land}.svg").read_text(encoding="utf-8")
        for g in echt["gebiete"]:
            if g["land"] != land:
                continue
            for iso in g["iso"]:
                assert f'id="r-{iso}"' in karte, f"{land}: {iso} fehlt"


def test_deutschland_hat_seine_bundeslaender(echt):
    de = {g["de"] for g in echt["gebiete"] if g["land"] == "DE"}
    for pflicht in ("Bayern", "Berlin", "Freie Hansestadt Bremen",
                    "Baden-Württemberg", "Sachsen"):
        assert pflicht in de, f"{pflicht} fehlt"


def test_bremen_liegt_nicht_in_niedersachsen(echt):
    """Der Fehler vom 05.09.2026: die Zuordnung indizierte name_de und
    name_en, aber nicht das schlichte "name". Bremen fiel damit auf die
    Punktprobe zurueck -- und der Mittelwert der beiden Exklaven Bremen und
    Bremerhaven liegt DAZWISCHEN, also in Niedersachsen. Bremer Knoten waeren
    still im falschen Bundesland gelandet."""
    nach_nummer = {g["n"]: g for g in echt["gebiete"]}
    for name in ("DE|Bremen", "DE|City state Bremen",
                 "DE|Free Hanseatic City of Bremen"):
        assert "Bremen" in nach_nummer[echt["namen"][name]]["de"], name


def test_kein_gebiet_steht_zweimal_da(echt):
    """Der Fehler vom 06.09.2026, sichtbar im Bild: Berlin stand zweimal in
    der Liste, seine Zahlen auf zwei Zeilen verteilt.

    DB-IP fuehrt dasselbe Bundesland unter mehreren Namen -- "Berlin" und
    "State of Berlin", Bremen sogar dreifach. Jeder Name wurde ein eigenes
    Gebiet, obwohl alle auf denselben Umriss zeigten. Nachgezaehlt waren 467
    Umrissmengen mehrfach vergeben, betroffen 1.187 von 3.839 Gebieten.

    Die Karte faerbte so ein Bundesland nach der zufaellig zuletzt
    verarbeiteten Zeile -- also nach einem Teil seiner Knoten, nicht nach
    allen.
    """
    from collections import defaultdict
    nach_umriss = defaultdict(list)
    for g in echt["gebiete"]:
        if g["iso"]:
            nach_umriss[(g["land"], tuple(sorted(g["iso"])))].append(g["de"])
    doppelt = {k: v for k, v in nach_umriss.items() if len(v) > 1}
    assert not doppelt, f"{len(doppelt)} Umrissmengen mehrfach vergeben: " \
                        f"{list(doppelt.items())[:3]}"


def test_jede_schreibweise_eines_bundeslands_zeigt_auf_dasselbe_gebiet(echt):
    """Konkret nachgeprueft, weil es im Bild aufgefallen ist."""
    n = echt["namen"]
    assert n["DE|Berlin"] == n["DE|State of Berlin"]
    assert n["DE|Bremen"] == n["DE|City state Bremen"] \
        == n["DE|Free Hanseatic City of Bremen"]
    assert n["DE|Hamburg"] == n["DE|Free and Hanseatic City of Hamburg"]
    assert n["DE|Baden-Wurttemberg"] == n["DE|Baden-Württemberg"]


def test_deutschland_hat_genau_sechzehn_bundeslaender(echt):
    de = [g for g in echt["gebiete"] if g["land"] == "DE"]
    assert len(de) == 16, sorted(g["de"] for g in de)
