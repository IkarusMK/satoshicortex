"""Die Ortstabelle -- Bauen und Nachschlagen zusammen geprueft.

Die beiden gehoeren zusammen getestet: das Format ist nur zwischen ihnen
verabredet, und ein Fehler darin faellt sonst erst im fertigen Abbild auf.
"""
import importlib.util
import pathlib

import pytest

from satcortex import geo

WURZEL = pathlib.Path(__file__).resolve().parents[3]


def _bauer():
    """tools/geo_bauen.py laden -- es liegt ausserhalb des Pakets, weil es
    beim Bauen des Abbilds laeuft und nicht im Betrieb."""
    pfad = WURZEL / "tools" / "geo_bauen.py"
    spec = importlib.util.spec_from_file_location("geo_bauen", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# Die Stadt-Liste von DB-IP: Anfang, Ende, Kontinent, Land, Region, Ort,
# Breite, Laenge. LUECKENLOS -- so kommt die echte Liste auch, am 05.09.2026
# nachgezaehlt (3.588.553 IPv4- und 4.160.445 IPv6-Bereiche, null Luecken),
# und das Format setzt es voraus.
PROBE = """0.0.0.0,0.255.255.255,ZZ,ZZ,,,0,0
1.0.0.0,1.0.0.255,OC,AU,New South Wales,Sydney,-33.8688,151.209
1.0.1.0,1.255.255.255,ZZ,ZZ,,,0,0
2.0.0.0,2.255.255.255,EU,FR,Bretagne,Rennes,48.1147,-1.6794
3.0.0.0,9.255.255.255,ZZ,ZZ,,,0,0
10.0.0.0,10.255.255.255,ZZ,ZZ,,,0,0
11.0.0.0,84.133.255.255,ZZ,ZZ,,,0,0
84.134.0.0,84.134.255.255,EU,DE,Bavaria,Munich,48.1374,11.5755
84.135.0.0,255.255.255.255,ZZ,ZZ,,,0,0
::,2001:485f:ffff:ffff:ffff:ffff:ffff:ffff,ZZ,ZZ,,,0,0
2001:4860::,2001:4860:ffff:ffff:ffff:ffff:ffff:ffff,NA,US,California,Mountain View,37.4056,-122.079
2001:4861::,2a02:7fff:ffff:ffff:ffff:ffff:ffff:ffff,ZZ,ZZ,,,0,0
2a02:8000::,2a02:8fff:ffff:ffff:ffff:ffff:ffff:ffff,EU,DE,Berlin,Berlin,52.5244,13.4105
2a02:9000::,ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff,ZZ,ZZ,,,0,0
"""

# Die Zuordnung, die sonst im Repo liegt. Klein gehalten und absichtlich
# UNVOLLSTAENDIG: "Bretagne" fehlt, damit gepruefte Wirklichkeit ist, was das
# Format verspricht -- ein unbekannter Name faellt auf das Land zurueck, nie
# auf eine falsche Region.
ZUORDNUNG = {
    "gebiete": [
        {"n": 1, "land": "DE", "de": "Bayern", "en": "Bavaria", "iso": ["DE-BY"]},
        {"n": 2, "land": "DE", "de": "Berlin", "en": "Berlin", "iso": ["DE-BE"]},
        {"n": 3, "land": "US", "de": "Kalifornien", "en": "California",
         "iso": ["US-CA"]},
        {"n": 4, "land": "AU", "de": "New South Wales", "en": "New South Wales",
         "iso": ["AU-NSW"]},
    ],
    "namen": {
        "DE|Bavaria": 1, "DE|Berlin": 2, "US|California": 3,
        "AU|New South Wales": 4,
    },
}


@pytest.fixture
def tabelle(tmp_path):
    import json
    csv = tmp_path / "probe.csv"
    csv.write_text(PROBE)
    zuordnung = tmp_path / "regionen.json"
    zuordnung.write_text(json.dumps(ZUORDNUNG), encoding="utf-8")
    dat = tmp_path / "probe.dat"
    _bauer().baue(csv, dat, "2026-08", zuordnung)
    return geo.lade(str(dat))


def test_adressen_finden_ihr_land(tabelle):
    assert tabelle.land("1.0.0.7") == "AU"
    assert tabelle.land("2.3.4.5") == "FR"
    assert tabelle.land("84.134.34.64") == "DE"
    assert tabelle.land("2001:4860:4860::8888") == "US"
    assert tabelle.land("2a02:8071:1234::1") == "DE"


def test_raender_der_bereiche_zaehlen_noch_dazu(tabelle):
    """Ein Vertippen um eins hier wuerde bei Millionen Adressen nie auffallen
    -- ausser genau am Rand."""
    assert tabelle.land("1.0.0.0") == "AU"
    assert tabelle.land("1.0.0.255") == "AU"
    assert tabelle.land("1.0.1.0") is None        # der naechste Bereich, ZZ


def test_zz_ist_kein_land(tabelle):
    """DB-IP kennzeichnet damit Privates und Reserviertes. Als Land auf einer
    Karte waere das falsch -- es gehoert zu den Unbekannten."""
    assert tabelle.land("10.1.2.3") is None


def test_onion_hat_keinen_ort_und_das_ist_der_zweck(tabelle):
    assert tabelle.land("abcdefghij234567.onion") is None
    assert tabelle.land("") is None
    assert tabelle.land("keine-adresse") is None


def test_ipv4_in_ipv6_schreibweise(tabelle):
    """Manche Knoten melden so. Ohne Sonderbehandlung fiele die Adresse in die
    IPv6-Tabelle und damit stumm heraus."""
    assert tabelle.land("::ffff:84.134.34.64") == "DE"


def test_unbekanntes_bleibt_unbekannt(tabelle):
    assert tabelle.land("3.0.0.1") is None
    assert tabelle.land("255.255.255.255") is None


def test_eine_lueckenhafte_liste_wird_abgelehnt(tmp_path):
    """Das Format speichert kein Ende je Bereich, sondern verlaesst sich
    darauf, dass der naechste Anfang eines ist. Kaeme die Quelle eines Tages
    mit Luecken, bekaemen Adressen darin still das Land ihres Vorgaengers --
    also eine Behauptung statt eines Nichtwissens. Deshalb bricht der Bau ab,
    statt es zu schlucken.
    """
    csv = tmp_path / "luecke.csv"
    csv.write_text("0.0.0.0,0.255.255.255,ZZ,ZZ,,,0,0\n"
                   "5.0.0.0,5.255.255.255,EU,DE,Bavaria,Munich,48.1,11.6\n")
    with pytest.raises(SystemExit, match="Luecken"):
        _bauer().baue(csv, tmp_path / "x.dat", "2026-08")


def test_gebiete_kommen_mit(tabelle):
    """Der eigentliche Zweck: nicht nur das Land, sondern das Bundesland."""
    assert tabelle.ort("84.134.34.64") == ("DE", 1)      # Bayern
    assert tabelle.ort("2a02:8071:1234::1") == ("DE", 2)  # Berlin
    assert tabelle.ort("2001:4860:4860::8888") == ("US", 3)


def test_ein_unbekannter_name_faellt_auf_das_land_zurueck(tabelle):
    """"Bretagne" steht nicht in der Zuordnung. Das Land bleibt trotzdem
    stehen -- die Karte verliert Frankreich nicht, sie weiss nur das Gebiet
    nicht. Eine falsche Region waere schlimmer als keine."""
    assert tabelle.ort("2.3.4.5") == ("FR", 0)


def test_land_und_gebiet_kommen_aus_derselben_zeile(tabelle):
    """land() ist nur die kurze Frage an dieselbe Suche."""
    for adresse in ("84.134.34.64", "2.3.4.5", "10.1.2.3", "quatsch"):
        assert tabelle.land(adresse) == tabelle.ort(adresse)[0]


def test_jahrgang_der_liste_kommt_mit(tabelle):
    """Er gehoert in die Oberflaeche: eine alte Liste ordnet still falsch zu,
    und DB-IP steht unter CC BY -- die Herkunft muss genannt werden."""
    assert tabelle.stand == "2026-08"


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    """Ein Abbild ohne Tabelle soll starten. Die Karte sagt es dann selbst."""
    assert geo.lade(str(tmp_path / "gibtsnicht.dat")) is None


def test_beschaedigte_datei_haelt_die_anwendung_nicht_auf(tmp_path):
    kaputt = tmp_path / "kaputt.dat"
    kaputt.write_bytes(b"SATGEO03" + b"\xff" * 40)
    assert geo.lade(str(kaputt)) is None

    fremd = tmp_path / "fremd.dat"
    fremd.write_bytes(b"IRGENDWAS" * 10)
    assert geo.lade(str(fremd)) is None
