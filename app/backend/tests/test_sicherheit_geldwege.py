"""Sicherheitspruefung der Geldwege vom 15.11.2026.

Neun Befunde, alle am laufenden Code nachgestellt, bevor irgendetwas
geaendert wurde. Jeder Test hier war ROT, ehe der Befund behoben war -- das
steht bei den Tests, die es betrifft, und die Reihenfolge ist der Grund, warum
man ihnen trauen darf.

Alle Werte ausgedacht.
"""
import os
import re
import stat
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from satcortex import auth, lnd, services, sicherung, state, storage
from tests.test_api import (ADRESSE, PIN, ZUGANG, FakeLnd, _freigabe_ein,
                            _sendebereit, client, lnd_da)  # noqa: F401

KONTO_PW = ZUGANG["passwort"]
KENNUNG = "02" + "ab" * 32
PUNKT = "ab" * 32 + ":0"


@pytest.fixture
def roh(client):
    """Der Client OHNE die Hilfe, die alten Tests das Kontopasswort anhaengt.

    Hier wird geprueft, was ohne Hilfe passiert.
    """
    client.auto_passwort = False
    return client


@pytest.fixture
def lnd_politik(lnd_da):
    """FakeLnd nimmt UpdateChannelPolicy an und merkt sich, was kam."""
    echt = lnd_da.ruf

    def ruf(pfad, *a, **k):
        if pfad == "/v1/chanpolicy":
            lnd_da.gesendet_an[pfad] = k.get("daten")
            return {}
        return echt(pfad, *a, **k)

    lnd_da.ruf = ruf
    return lnd_da


def _zweite_sitzung(client):
    """Dieselbe Anwendung, ein zweites Cookie -- der Eigentuemer am Laptop,
    waehrend jemand mit einer gestohlenen Sitzung am Telefon haengt."""
    zweiter = TestClient(client.app)
    zweiter.auto_passwort = False
    assert zweiter.post("/api/anmelden", json=ZUGANG).status_code == 200
    return zweiter


# Jede Route, die Geld bewegt oder ein Schloss aufmacht -- mit einem Rumpf,
# der die Pydantic-Pruefung besteht. Das Tor kommt vor dem Rest.
GATE_ROUTEN = [
    ("/api/lightning/senden", {"adresse": ADRESSE, "betrag": 1000}),
    ("/api/lightning/senden/nachbessern", {"txid": "a" * 64, "ausgang": 0}),
    ("/api/lightning/kanal/oeffnen",
     {"gegenstelle": KENNUNG + "@1.2.3.4:9735", "betrag": 100_000}),
    ("/api/lightning/kanal/schliessen", {"punkt": PUNKT}),
    ("/api/lightning/kanal/schliessen", {"punkt": PUNKT, "erzwingen": True}),
    ("/api/lightning/rechnung/zahlen", {"rechnung": "lnbc1xyz"}),
    ("/api/lightning/umschichten",
     {"von": "123", "nach": KENNUNG, "betrag": 1000}),
    ("/api/lightning/wallet/loeschen",
     {"passwort": "w", "alias": "SatoshiCortex"}),
    ("/api/fernzugang/geraet", {"name": "Telefon", "stufe": "lesen",
                                "weg": "tor"}),
    ("/api/fernzugang/geraet/1/widerrufen", {}),
]
GATE_IDS = [f"{p.rsplit('/api/', 1)[1]}{'+' if b.get('erzwingen') or b.get('url') else ''}"
            for p, b in GATE_ROUTEN]


# ═════════════════════════════════════════════════════════════════════════
# Befund 1 (HOCH): ohne PIN bewegte eine nackte Sitzung Geld.
# ═════════════════════════════════════════════════════════════════════════

def test_ohne_pin_bewegt_eine_nackte_sitzung_kein_geld(roh, lnd_da,
                                                       monkeypatch):
    """ROT vorher: 200 und FakeLnd.sende_alles -- jetzt 403."""
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/senden",
                 json={"adresse": ADRESSE, "alles": True})
    assert a.status_code == 403, a.text
    assert a.json()["detail"]["meldung"] == "kontopasswort_noetig"
    assert lnd_da.gesendet is None


@pytest.mark.parametrize("pfad,rumpf", GATE_ROUTEN, ids=GATE_IDS)
def test_ohne_pin_verlangt_jede_geldroute_das_kontopasswort(
        roh, lnd_da, monkeypatch, pfad, rumpf):
    """ROT vorher: die vier neuen Routen liessen alles durch, die neun alten
    nur, solange keine PIN stand."""
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post(pfad, json=rumpf)
    assert a.status_code == 403, (pfad, a.text)
    assert a.json()["detail"]["meldung"] == "kontopasswort_noetig"
    b = roh.post(pfad, json={**rumpf, "konto_passwort": "falsch-falsch-xx"})
    assert b.status_code == 400, (pfad, b.text)
    assert b.json()["detail"]["meldung"] == "kontopasswort_falsch"


@pytest.mark.parametrize("pfad,rumpf", GATE_ROUTEN, ids=GATE_IDS)
def test_mit_pin_verlangt_jede_geldroute_die_pin(roh, lnd_da, monkeypatch,
                                                 pfad, rumpf):
    """"""
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    a = roh.post(pfad, json=rumpf)
    assert a.status_code == 403, (pfad, a.text)
    assert a.json()["detail"]["meldung"] == "pin_noetig"
    # Das Kontopasswort ersetzt die PIN NICHT, wenn eine eingerichtet ist --
    # sonst waere sie nur ein Hindernis fuer den Eigentuemer.
    b = roh.post(pfad, json={**rumpf, "konto_passwort": KONTO_PW})
    assert b.status_code == 403
    assert b.json()["detail"]["meldung"] == "pin_noetig"
    c = roh.post(pfad, json={**rumpf, "pin": "000001"})
    assert c.status_code == 400
    assert c.json()["detail"]["meldung"] == "pin_falsch"


def test_mit_kontopasswort_geht_das_senden_ohne_pin(roh, lnd_da, monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "alles": True, "konto_passwort": KONTO_PW})
    assert a.status_code == 200, a.text
    assert lnd_da.gesendet is not None


def test_mit_pin_geht_das_senden_wie_zuvor(roh, lnd_da, monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    a = roh.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "betrag": 1000, "pin": PIN})
    assert a.status_code == 200, a.text


def test_die_notbremse_bleibt_ohne_schloss(roh, lnd_da, monkeypatch):
    """wallet/sperren steht mit Absicht NICHT hinter dem Tor: es ist die
    Notbremse. Wer sie zieht, bewegt nichts -- ein Angreifer gewaenne einen
    Aerger, der Eigentuemer muss sie sofort ziehen koennen."""
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    a = roh.post("/api/lightning/wallet/sperren")
    assert a.status_code != 403, a.text


def test_das_kontopasswort_prueft_das_tor_vor_der_eingabe(roh, lnd_da,
                                                          monkeypatch):
    """Die Reihenfolge, die AGENTS.md verspricht: das Tor vor Betrag und
    Adresse -- ein unsinniger Betrag verraet ohne Passwort nichts."""
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/senden",
                 json={"adresse": "kaputt", "betrag": 5})
    assert a.status_code == 403


def test_das_kontopasswort_wird_gebremst(roh, lnd_da, monkeypatch):
    """Der Zugang ueber das Passwort ist ein Ratebereich wie die PIN -- er
    teilt deren Waechter."""
    _sendebereit(roh, lnd_da, monkeypatch)
    codes = []
    for _ in range(auth.PIN_MAX_VERSUCHE + 1):
        a = roh.post("/api/lightning/senden", json={
            "adresse": ADRESSE, "betrag": 1000,
            "konto_passwort": "falsch-falsch-xx"})
        codes.append(a.status_code)
        if a.status_code == 400:
            # Wartezeit abkuerzen: der Zaehler steht in der Datei.
            _wartezeit_erlassen(roh)
    assert codes[-1] == 429, codes
    assert lnd_da.gesendet is None


def _wartezeit_erlassen(client):
    """Die Zeitstempel in der Zaehlerdatei um eine Stunde zurueckstellen --
    nur die kurze Wartezeit, nicht die Sperre, soll uebersprungen werden."""
    import json
    pfad = Path(client.tmp) / "config" / "freigabe_versuche.json"
    d = json.loads(pfad.read_text())
    for k, v in d.items():
        d[k] = [t - 10 for t in v]
    pfad.write_text(json.dumps(d))


# ═════════════════════════════════════════════════════════════════════════
# Befund 3 (MITTEL): eine Sitzung sperrte den Eigentuemer aus.
# ═════════════════════════════════════════════════════════════════════════

def test_eine_fremde_sitzung_sperrt_den_eigentuemer_nicht_aus(
        roh, lnd_da, monkeypatch):
    """ROT vorher: nach zwei falschen Versuchen der einen Sitzung bekam die
    andere mit der RICHTIGEN PIN ein 429."""
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    eigentuemer = _zweite_sitzung(roh)
    for _ in range(2):
        roh.post("/api/lightning/senden", json={
            "adresse": ADRESSE, "betrag": 1000, "pin": "000001"})
    gesperrt = roh.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "betrag": 1000, "pin": PIN})
    assert gesperrt.status_code == 429, "die fremde Sitzung sperrt sich selbst"

    a = eigentuemer.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "betrag": 1000, "pin": PIN})
    assert a.status_code == 200, a.text
    assert eigentuemer.get("/api/freigabe").json()["wartet_noch"] == 0


def test_auch_ueber_https_zaehlt_jede_sitzung_fuer_sich(client, lnd_da,
                                                       monkeypatch):
    """DER BEFUND VOM 16.11.2026, beim Zusammenfuehren mit dem eigenen TLS:
    ueber HTTPS (und hinter einem Proxy mit TLS_EXTERN) heisst das Cookie
    "__Host-satcortex_sitzung". Die Geldwege lasen nur den alten Namen und
    zaehlten jede solche Sitzung als "" -- alle in EINEM Topf, und eine
    fremde Sitzung sperrte den Eigentuemer wieder aus.
    ROT vorher: der Eigentuemer bekam mit der RICHTIGEN PIN ein 429."""
    _sendebereit(client, lnd_da, monkeypatch)
    _freigabe_ein(client)

    def https_sitzung():
        c = TestClient(client.app, base_url="https://testserver")
        assert c.post("/api/anmelden", json=ZUGANG).status_code == 200
        assert any(n.startswith("__Host-") for n in c.cookies.keys())
        return c

    fremd, eigentuemer = https_sitzung(), https_sitzung()
    for _ in range(2):
        fremd.post("/api/lightning/senden", json={
            "adresse": ADRESSE, "betrag": 1000, "pin": "000001"})
    gesperrt = fremd.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "betrag": 1000, "pin": PIN})
    assert gesperrt.status_code == 429, "die fremde Sitzung sperrt sich selbst"

    a = eigentuemer.post("/api/lightning/senden", json={
        "adresse": ADRESSE, "betrag": 1000, "pin": PIN})
    assert a.status_code == 200, a.text
    assert eigentuemer.get("/api/freigabe").json()["wartet_noch"] == 0


def test_die_auskunft_zeigt_die_wartezeit_der_eigenen_sitzung(roh, lnd_da,
                                                              monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    andere = _zweite_sitzung(roh)
    roh.post("/api/freigabe/entfernen", json={"pin": "000001"})
    assert roh.get("/api/freigabe").json()["wartet_noch"] > 0
    assert andere.get("/api/freigabe").json()["wartet_noch"] == 0


@pytest.fixture
def freigabe(tmp_path):
    return auth.Freigabe(str(tmp_path / "ablage"))


@pytest.fixture
def mit_pin(freigabe):
    freigabe.einrichten(PIN)
    return freigabe


def test_der_zaehler_zaehlt_je_sitzung(mit_pin):
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe("000001", "sitzung-a")
    assert mit_pin.wartet_noch("sitzung-a") > 0
    assert mit_pin.wartet_noch("sitzung-b") == 0
    assert mit_pin.pruefe(PIN, "sitzung-b") is True


def test_die_stufen_gelten_je_sitzung(mit_pin):
    """Die Eskalation bis zur langen Sperre bleibt, nur eben je Sitzung."""
    uhr = [1_000_000.0]
    import satcortex.auth as modul
    echt = modul.time.time
    modul.time.time = lambda: uhr[0]
    try:
        for _ in range(auth.PIN_MAX_VERSUCHE):
            uhr[0] += mit_pin.wartet_noch("a") + 1
            with pytest.raises(auth.FreigabeAbgelehnt):
                mit_pin.pruefe("000001", "a")
        uhr[0] += max(auth.PIN_WARTEN) + 1
        with pytest.raises(auth.FreigabeGesperrt):
            mit_pin.pruefe(PIN, "a")
        assert mit_pin.pruefe(PIN, "b") is True
    finally:
        modul.time.time = echt


def test_die_zaehlerdatei_enthaelt_nie_das_rohe_merkmal(mit_pin, tmp_path):
    roh_merkmal = "ein-geheimes-sitzungsmerkmal-123456"
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe("000001", roh_merkmal)
    inhalt = "".join(p.read_text() for p in
                     (tmp_path / "ablage").glob("*.json"))
    assert roh_merkmal not in inhalt
    assert auth._merkmal(roh_merkmal) in inhalt


def test_die_zaehlerdatei_bleibt_beschraenkt(mit_pin, tmp_path):
    for i in range(auth.PIN_MAX_SITZUNGEN + 50):
        with pytest.raises(auth.FreigabeAbgelehnt):
            mit_pin.pruefe("000001", f"sitzung-{i}")
    import json
    d = json.loads((tmp_path / "ablage" / "freigabe_versuche.json")
                   .read_text())
    assert len(d) <= auth.PIN_MAX_SITZUNGEN


def test_das_kontopasswort_teilt_den_zaehler_der_sitzung(mit_pin):
    hash_ = auth.hashe(KONTO_PW)
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe("000001", "s")
    with pytest.raises(auth.FreigabeGesperrt):
        mit_pin.pruefe_konto(KONTO_PW, hash_, "s")
    assert mit_pin.pruefe_konto(KONTO_PW, hash_, "t") is True


def test_der_zaehler_gilt_auch_ohne_pin(freigabe):
    hash_ = auth.hashe(KONTO_PW)
    with pytest.raises(auth.FreigabeAbgelehnt):
        freigabe.pruefe_konto("falsch-falsch-xx", hash_, "s")
    assert freigabe.wartet_noch("s") > 0
    assert freigabe.vorhanden is False, "der Zaehler ist keine PIN"


# ═════════════════════════════════════════════════════════════════════════
# Befund 4 (NIEDRIG): Sicherungsziel ohne Einschraenkung.
# ═════════════════════════════════════════════════════════════════════════

BOESE_ZIELE = [
    "https://cloud.example/v1/state#",            # Pfad abschneiden
    "https://cloud.example/dav?x=",               # Suffix in die Abfrage
    "https://u:p@cloud.example/dav/",             # Anmeldedaten in der URL
    "file:///etc/passwd",
    "gopher://cloud.example/x",
    "ftp://cloud.example/x",
    "http://127.0.0.1:8080/dav/",
    "http://localhost/dav/",
    "http://[::1]/dav/",
    "http://10.83.33.12:8080/",                   # lnd im Compose-Netz
    "http://10.83.33.200/",                       # irgendwo im /24
    "http://lnd:8080/",
    "http://bitcoind:8332/",
    "http://tor:9050/",
    "http://app:8080/",
    "http://LND:8080/",
    "http://169.254.169.254/latest/meta-data/",
    "http://0.0.0.0:80/",
    "",
]


@pytest.mark.parametrize("url", [u for u in BOESE_ZIELE if u])
def test_ein_boeses_sicherungsziel_wird_abgelehnt(url):
    """ROT vorher: es gab keine Pruefung -- pruefe_ziel existierte nicht."""
    with pytest.raises(sicherung.ZielFehler):
        sicherung.pruefe_ziel(url, "10.83.33")


@pytest.mark.parametrize("url", [
    "https://cloud.example/remote.php/dav/files/u/Sicherung",
    "https://cloud.example:8443/dav/",
    "http://192.168.1.20:8080/dav/",              # NAS im Heimnetz
    "http://nas.local/dav/",
])
def test_ein_gewoehnliches_ziel_bleibt_erlaubt(url):
    sicherung.pruefe_ziel(url, "10.83.33")


def test_ein_anderes_compose_netz_gilt_auch(monkeypatch):
    with pytest.raises(sicherung.ZielFehler):
        sicherung.pruefe_ziel("http://10.99.1.12/", "10.99.1")
    sicherung.pruefe_ziel("http://10.83.33.12/", "10.99.1")


def test_die_webdav_adresse_schneidet_nichts_ab():
    # Der GRUND zaehlt: vorher scheiterten diese Aufrufe nur zufaellig am
    # Netz (kein Rechner, keine Datei) -- "ziel_url_ungueltig" kommt nur aus
    # der Pruefung, bevor irgendetwas versucht wird.
    with pytest.raises(sicherung.ZielFehler) as a:
        sicherung.lade_hoch("", "https://cloud.example/v1/state#", "u", "p")
    assert a.value.grund == "ziel_url_ungueltig"
    with pytest.raises(sicherung.ZielFehler) as b:
        sicherung.hole_ab("file:///etc/passwd", "u", "p")
    assert b.value.grund == "ziel_url_ungueltig"


def test_die_route_lehnt_ein_boeses_ziel_ab_bevor_sie_wegschickt(
        roh, lnd_da, monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    gesehen = []
    monkeypatch.setattr(lnd, "sicherung_holen", lambda k: {
        "blob": "AA==", "punkte": [], "kanaele": 0})
    monkeypatch.setattr(sicherung, "lade_hoch",
                        lambda *a, **k: gesehen.append(a))
    a = roh.post("/api/lightning/sicherung/ziel", json={
        "url": "http://10.83.33.12:8080/v1/state#", "benutzer": "u",
        "passwort": "p"})
    assert a.status_code == 400, a.text
    assert gesehen == []


@pytest.mark.parametrize("pfad,rumpf", [
    ("/api/lightning/sicherung/ziel", {"url": ""}),
    ("/api/lightning/wachtuerme/entfernen", {"kennung": KENNUNG}),
    ("/api/lightning/entsperrweg", {"weg": "aus"}),
])
def test_diese_routen_fragen_bewusst_nichts_ab(roh, lnd_da, monkeypatch,
                                               pfad, rumpf):
    """Entscheidung des Eigentuemers vom 15.11.2026: die Handhabung bleibt
    wie sie war -- Schutz von aussen, keine Abfrage bei jedem Handgriff."""
    _sendebereit(roh, lnd_da, monkeypatch)
    _freigabe_ein(roh)
    a = roh.post(pfad, json=rumpf)
    assert a.status_code != 403, a.text


# ═════════════════════════════════════════════════════════════════════════
# Befund 5 (NIEDRIG): Verbinden / Wachturm als Portscanner nach innen.
# ═════════════════════════════════════════════════════════════════════════

INNERE_WIRTE = ["127.0.0.1:22", "localhost:8080", "[::1]:9735",
                "10.83.33.12:10009", "10.83.33.11:8332", "lnd:10009",
                "bitcoind:8332", "tor:9050", "app:8080", "0.0.0.0:1",
                "169.254.169.254:80"]


class _Stumm:
    """Ein Knoten, der jeden Anruf meldet -- es darf keiner kommen."""

    def __init__(self):
        self.aufrufe = []

    def ruf(self, *a, **k):
        self.aufrufe.append(a)
        return {}


@pytest.mark.parametrize("wirt", INNERE_WIRTE)
def test_verbinden_waehlt_keine_inneren_ziele_an(wirt):
    knoten = _Stumm()
    with pytest.raises(lnd.LndFehler):
        lnd.verbinde(knoten, f"{KENNUNG}@{wirt}", "10.83.33")
    assert knoten.aufrufe == []


@pytest.mark.parametrize("wirt", INNERE_WIRTE)
def test_wachturm_waehlt_keine_inneren_ziele_an(wirt):
    knoten = _Stumm()
    with pytest.raises(lnd.LndFehler):
        lnd.wachturm_eintragen(knoten, f"{KENNUNG}@{wirt}", "10.83.33")
    assert knoten.aufrufe == []


@pytest.mark.parametrize("wirt", ["203.0.113.5:9735", "192.168.1.50:9911",
                                  "abcdefghij234567.onion:9735",
                                  "node.example.org:9735"])
def test_aeussere_und_heimnetz_ziele_bleiben_moeglich(wirt):
    knoten = _Stumm()
    lnd.verbinde(knoten, f"{KENNUNG}@{wirt}", "10.83.33")
    assert len(knoten.aufrufe) == 1
    lnd.wachturm_eintragen(knoten, f"{KENNUNG}@{wirt}", "10.83.33")
    assert len(knoten.aufrufe) == 2


def test_die_route_verbinden_reicht_das_compose_netz_durch(roh, lnd_da,
                                                           monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/verbinden",
                 json={"adresse": f"{KENNUNG}@10.83.33.12:10009"})
    assert a.status_code == 400, a.text
    assert lnd_da.verbunden is None


# ═════════════════════════════════════════════════════════════════════════
# Befund 6 (NIEDRIG): Geheimnisse standen kurz mit 0644 da.
# ═════════════════════════════════════════════════════════════════════════

def _beobachte_anlegen(monkeypatch):
    """Haelt fest, mit welchen Rechten Dateien ANGELEGT werden.

    Nachtraegliches chmod nuetzt nichts, wenn der Inhalt schon geschrieben
    ist -- also wird die Anlage selbst beobachtet: os.open (Rechte-Argument)
    und der Zustand der Datei im Augenblick jedes chmod-Aufrufs.
    """
    angelegt = []
    echt_open = os.open
    echt_chmod = os.chmod

    def beobachteter_open(pfad, flags, mode=0o777, *a, **k):
        if flags & os.O_CREAT:
            angelegt.append(("open", str(pfad), mode, bool(flags & os.O_EXCL)))
        return echt_open(pfad, flags, mode, *a, **k)

    def beobachtetes_chmod(pfad, mode, *a, **k):
        try:
            angelegt.append(("chmod_vorher", str(pfad),
                             stat.S_IMODE(os.stat(pfad).st_mode), False))
        except OSError:
            pass
        return echt_chmod(pfad, mode, *a, **k)

    monkeypatch.setattr(os, "open", beobachteter_open)
    monkeypatch.setattr(os, "chmod", beobachtetes_chmod)
    return angelegt


def _schreiber(tmp_path):
    ablage = tmp_path / "ablage"
    ablage.mkdir()
    return {
        "storage.schreibe_geheimnis":
            (lambda: storage.schreibe_geheimnis(str(ablage / "wallet.pass"),
                                                "geheim"), ablage / "wallet.pass"),
        "services.schreibe_geheim":
            (lambda: services.Konfigurationsablage(str(ablage))
             .schreibe_geheim("x", {"k": "geheim"}), ablage / "x.geheim.json"),
        "auth.Freigabe":
            (lambda: auth.Freigabe(str(ablage)).einrichten(PIN),
             ablage / "freigabe.json"),
        "state.Ablage":
            (lambda: state.Ablage(str(ablage)).speichern(state.Einrichtung()),
             ablage / "einrichtung.json"),
        # Nachgezogen beim Zusammenfuehren (16.11.2026): dieselbe Luecke
        # stand in der Kontoverwaltung -- Sitzungen und Fehlversuche.
        "auth.Kontoverwaltung.sitzungen":
            (lambda: auth.Kontoverwaltung(str(ablage)).sitzung_eroeffnen(),
             ablage / "sitzungen.json"),
        "auth.Kontoverwaltung.fehlversuche":
            (lambda: _ein_fehlversuch(ablage), ablage / "fehlversuche.json"),
    }


def _ein_fehlversuch(ablage):
    konten = auth.Kontoverwaltung(str(ablage))
    if not konten.vorhanden:
        konten.lege_an(ZUGANG["benutzer"], KONTO_PW)
    with pytest.raises(PermissionError):
        konten.melde_an(ZUGANG["benutzer"], "falsch-falsch-falsch")


@pytest.mark.parametrize("name", ["storage.schreibe_geheimnis",
                                  "services.schreibe_geheim",
                                  "auth.Freigabe", "state.Ablage",
                                  "auth.Kontoverwaltung.sitzungen",
                                  "auth.Kontoverwaltung.fehlversuche"])
def test_geheimnisse_werden_nie_breiter_als_0600_angelegt(tmp_path,
                                                          monkeypatch, name):
    """ROT vorher: write_text legt mit 0666 & ~umask an (0644), chmod folgt
    erst danach; state.json blieb sogar bei 0644."""
    os.umask(0o022)
    schreibe, ziel = _schreiber(tmp_path)[name]
    angelegt = _beobachte_anlegen(monkeypatch)
    schreibe()
    monkeypatch.undo()
    assert stat.S_IMODE(ziel.stat().st_mode) == 0o600
    breite = [e for e in angelegt
              if e[0] == "chmod_vorher" and e[2] & 0o077]
    assert breite == [], f"Datei war vor dem chmod zu offen: {breite}"
    oeffnungen = [e for e in angelegt if e[0] == "open"]
    assert oeffnungen, "die Datei wurde nicht ueber os.open angelegt"
    assert all(e[2] == 0o600 and e[3] for e in oeffnungen), oeffnungen


def test_ein_gescheitertes_schreiben_laesst_nichts_liegen(tmp_path,
                                                          monkeypatch):
    ablage = tmp_path / "a"
    ablage.mkdir()
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(
        OSError("voll")))
    with pytest.raises(OSError):
        storage.schreibe_geheimnis(str(ablage / "x.pass"), "g")
    assert list(ablage.iterdir()) == []


# ═════════════════════════════════════════════════════════════════════════
# Befund 7 (NIEDRIG): falsche Aussagen ueber das eigene Macaroon.
# ═════════════════════════════════════════════════════════════════════════

def test_die_aussagen_ueber_das_macaroon_stimmen():
    """ROT vorher: 'ohne onchain:write, also ohne die Moeglichkeit, Geld zu
    bewegen' und 'onchain:write, und das haelt diese Anwendung ausdruecklich
    nicht'."""
    quelle = (Path(api_datei()).read_text(encoding="utf-8"))
    assert "ohne onchain:write" not in quelle
    assert "haelt diese Anwendung ausdruecklich nicht" not in quelle
    assert ("onchain", "write") in lnd.EIGENE_RECHTE
    assert ("offchain", "write") in lnd.EIGENE_RECHTE


def api_datei():
    from satcortex import api
    return api.__file__


# ═════════════════════════════════════════════════════════════════════════
# Befund 8 (NIEDRIG): doppeltes Absenden.
# ═════════════════════════════════════════════════════════════════════════

def _gleichzeitig(client, pfad, rumpf, monkeypatch, ziel):
    """Zwei gleiche Aufrufe, der erste haelt in LND fest, bis der zweite
    beantwortet ist."""
    festhalten, weiter, aufrufe = threading.Event(), threading.Event(), []

    def langsam(*a, **k):
        aufrufe.append(1)
        festhalten.set()
        assert weiter.wait(10)
        raise lnd.LndFehler("nur ein Versuch")

    monkeypatch.setattr(lnd, ziel, langsam)
    ergebnis = {}

    def erster():
        ergebnis["a"] = client.post(pfad, json=rumpf)

    faden = threading.Thread(target=erster)
    faden.start()
    assert festhalten.wait(10)
    zweiter = TestClient(client.app)
    zweiter.cookies.update(client.cookies)
    zweiter.auto_passwort = False
    b = zweiter.post(pfad, json=rumpf)
    weiter.set()
    faden.join(10)
    return b, ergebnis["a"], aufrufe


def test_zweimal_senden_fuehrt_nur_einmal_aus(roh, lnd_da, monkeypatch):
    """ROT vorher: beide Anfragen erreichten lnd.sende."""
    _sendebereit(roh, lnd_da, monkeypatch)
    rumpf = {"adresse": ADRESSE, "betrag": 1000, "konto_passwort": KONTO_PW}
    b, a, aufrufe = _gleichzeitig(roh, "/api/lightning/senden", rumpf,
                                  monkeypatch, "sende")
    assert b.status_code == 409, b.text
    assert b.json()["detail"]["meldung"] == "vorgang_laeuft_schon"
    assert len(aufrufe) == 1
    assert a.status_code == 400


def test_zweimal_kanal_oeffnen_fuehrt_nur_einmal_aus(roh, lnd_da,
                                                     monkeypatch):
    _sendebereit(roh, lnd_da, monkeypatch)
    rumpf = {"gegenstelle": KENNUNG + "@203.0.113.5:9735", "betrag": 100_000,
             "konto_passwort": KONTO_PW}
    b, a, aufrufe = _gleichzeitig(roh, "/api/lightning/kanal/oeffnen", rumpf,
                                  monkeypatch, "kanal_oeffnen")
    assert b.status_code == 409, b.text
    assert b.json()["detail"]["meldung"] == "vorgang_laeuft_schon"
    assert len(aufrufe) == 1


def test_nach_dem_ersten_senden_geht_das_naechste_wieder(roh, lnd_da,
                                                         monkeypatch):
    """Die Sperre haelt nur, solange der Vorgang laeuft."""
    _sendebereit(roh, lnd_da, monkeypatch)
    rumpf = {"adresse": ADRESSE, "betrag": 1000, "konto_passwort": KONTO_PW}
    assert roh.post("/api/lightning/senden", json=rumpf).status_code == 200
    assert roh.post("/api/lightning/senden", json=rumpf).status_code == 200


# ═════════════════════════════════════════════════════════════════════════
# Befund 2 (MITTEL), zweiter Teil: Boden fuer time_lock_delta.
# ═════════════════════════════════════════════════════════════════════════

def test_die_zeitsperre_hat_einen_boden_ueber_dem_protokollminimum(
        roh, lnd_politik, monkeypatch):
    """ROT vorher: 18 (LNDs Protokollminimum) wurde angenommen."""
    lnd_da = lnd_politik
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/gebuehren", json={
        "basis_msat": 0, "satz_ppm": 10, "zeitsperre": 18})
    assert a.status_code == 422, a.text
    b = roh.post("/api/lightning/gebuehren", json={
        "basis_msat": 0, "satz_ppm": 10, "zeitsperre": lnd.ZEITSPERRE_MIN})
    assert b.status_code == 200, b.text


def test_alles_was_die_anwendung_selbst_setzt_liegt_ueber_dem_boden():
    assert lnd.ZEITSPERRE_MIN > 18
    assert lnd.ZEITSPERRE_MIN <= 80, "LNDs Vorgabe muss immer durchgehen"
    assert lnd.ZEITSPERRE_MIN <= 144, "die Vorgabe der Oberflaeche auch"


def test_die_automatik_hebt_eine_zu_kleine_geltende_zeitsperre_an(
        lnd_politik):
    lnd_da = lnd_politik
    """Eine Gegenstelle oder ein Fremdwerkzeug hat 18 gesetzt: die Automatik
    reicht den geltenden Wert weiter und darf daran nicht scheitern -- sie
    hebt ihn auf den Boden."""
    lnd.setze_gebuehren(lnd_da, 0, 10, 18, "")
    daten = lnd_da.gesendet_an["/v1/chanpolicy"]
    assert daten["time_lock_delta"] == lnd.ZEITSPERRE_MIN
    lnd.setze_gebuehren(lnd_da, 0, 10, 144, "")
    assert lnd_da.gesendet_an["/v1/chanpolicy"]["time_lock_delta"] == 144


# ═════════════════════════════════════════════════════════════════════════
# Befund 9 (NIEDRIG): kanalpunkt "abc:xyz" -> 500.
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("punkt", ["abc:xyz", "nur-text", ("ab" * 32) + ":x",
                                   ("ab" * 31) + ":0", ("zz" * 32) + ":0",
                                   ("ab" * 32) + ":-1", ("ab" * 32) + ":0:1",
                                   ("ab" * 32) + ":99999999999"])
def test_ein_ungueltiger_kanalpunkt_ist_ein_422(roh, lnd_da, monkeypatch,
                                                punkt):
    """ROT vorher: ValueError in int(index or 0) -> 500."""
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/gebuehren", json={
        "basis_msat": 0, "satz_ppm": 1, "zeitsperre": 144,
        "kanalpunkt": punkt})
    assert a.status_code == 422, a.text
    assert "/v1/chanpolicy" not in lnd_da.gesendet_an


def test_ein_gueltiger_kanalpunkt_geht_durch(roh, lnd_politik, monkeypatch):
    lnd_da = lnd_politik
    _sendebereit(roh, lnd_da, monkeypatch)
    a = roh.post("/api/lightning/gebuehren", json={
        "basis_msat": 0, "satz_ppm": 1, "zeitsperre": 144,
        "kanalpunkt": PUNKT})
    assert a.status_code == 200, a.text


# ═════════════════════════════════════════════════════════════════════════
# Oberflaeche: das Feld fuers Kontopasswort -- in app.js als Text gelesen,
# Kommentare vorher entfernt (AGENTS.md).
# ═════════════════════════════════════════════════════════════════════════

def _app_js_ohne_kommentare():
    quelle = (Path(__file__).resolve().parents[2] / "web" / "app.js"
              ).read_text(encoding="utf-8")
    quelle = re.sub(r"/\*.*?\*/", "", quelle, flags=re.S)
    return "\n".join(z for z in quelle.splitlines()
                     if not z.lstrip().startswith("//"))


def test_die_oberflaeche_schickt_das_kontopasswort_mit():
    js = _app_js_ohne_kommentare()
    assert "konto_passwort" in js


def test_die_oberflaeche_kennt_die_neuen_fehlermeldungen():
    js = _app_js_ohne_kommentare()
    for schluessel in ("kontopasswort_noetig", "kontopasswort_falsch",
                       "vorgang_laeuft_schon"):
        assert schluessel in js, schluessel
