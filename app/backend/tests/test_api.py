import ast
import re
import shutil
import time
from collections import namedtuple
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from satcortex import api, auth, nodeconfig, settings

Nutzung = namedtuple("Nutzung", "total used free")
GB = 1024 ** 3


def _platz(monkeypatch, frei_gb):
    """Freien Platz vortaeuschen.

    Ohne das haengen die Tests davon ab, wieviel auf der Entwicklungsmaschine
    zufaellig frei ist -- und dort liegt fast nie ein Terabyte herum.
    """
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda _p: Nutzung(frei_gb * 2 * GB, frei_gb * GB, frei_gb * GB),
    )


ZUGANG = {"benutzer": "pruefer", "passwort": "ein-gutes-langes-passwort"}


def _client(tmp_path, konf=None, anmelden=True):
    """Client mit angelegtem Konto.

    Seit der Sicherheitspruefung liegt alles hinter einer Anmeldung -- die
    Tests muessen sich also anmelden wie ein echter Nutzer auch.
    """
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(exist_ok=True); fast.mkdir(exist_ok=True)
    konf = konf or settings.Einstellungen(
        bulk=str(bulk), fast=str(fast), config_dir=str(tmp_path / "config")
    )
    c = TestClient(api.baue_app(konf))
    c.tmp = tmp_path
    if anmelden:
        if (tmp_path / "config" / "konto.json").exists():
            c.post("/api/anmelden", json=ZUGANG)
        else:
            c.post("/api/konto/anlegen", json=ZUGANG)
    return c


@pytest.fixture
def client(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)          # reichlich Platz, damit der Ablauf durchlaeuft
    return _client(tmp_path)


@pytest.fixture
def client_ohne_platz(tmp_path, monkeypatch):
    _platz(monkeypatch, 50)
    return _client(tmp_path)


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_einrichtung_startet_bei_willkommen(client):
    d = client.get("/api/einrichtung").json()
    assert d["schritt"] == "willkommen"
    assert d["nummer"] == 1
    assert d["fertig"] is False


def test_durch_den_assistenten_blaettern(client):
    schritte = []
    for _ in range(5):
        d = client.post("/api/einrichtung/weiter", json={"antworten": {}}).json()
        schritte.append(d["schritt"])
    assert schritte == ["speicher", "leistung", "netz", "konto", "fertig"]


def test_fortschritt_ueberlebt_einen_neustart(client):
    client.post("/api/einrichtung/weiter", json={"antworten": {"gelesen": True}})
    # Neue Anwendung auf demselben Verzeichnis = wie ein Neustart des Containers
    zweiter = _client(client.tmp)
    d = zweiter.get("/api/einrichtung").json()
    assert d["schritt"] == "speicher"
    assert d["antworten"]["willkommen"] == {"gelesen": True}


def test_weiter_nach_dem_ende_wird_abgelehnt(client):
    for _ in range(5):
        client.post("/api/einrichtung/weiter", json={"antworten": {}})
    antwort = client.post("/api/einrichtung/weiter", json={"antworten": {}})
    assert antwort.status_code == 409


def test_speicherpruefung_meldet_die_lage(client):
    d = client.get("/api/speicher").json()
    assert "bulk" in d and "fast" in d
    assert d["gesamt"] in ("genug", "knapp", "zu_wenig", "fehlt")


def test_leistungsvorschau_erklaert_die_folgen(client):
    d = client.post("/api/leistung/vorschau", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True}).json()
    assert d["dbcache_erstsync_mb"] > d["dbcache_betrieb_mb"]
    assert d["upload_unbegrenzt"] is False
    assert d["meldung_upload"] == "upload_begrenzt"


def test_unsinnige_werte_werden_abgewiesen(client):
    zu_viele = client.post("/api/leistung/vorschau", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 9999, "tor_aktiv": True})
    assert zu_viele.status_code == 422       # maxconnections hat eine Obergrenze

    zu_wenig_ram = client.post("/api/leistung/vorschau", json={
        "speichergrenze_mb": 10, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    assert zu_wenig_ram.status_code == 422


def test_unter_zwoelf_verbindungen_nimmt_der_assistent_nicht_an(client):
    def vorschau(n):
        return client.post("/api/leistung/vorschau", json={
            "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
            "verbindungen": n, "tor_aktiv": True}).status_code
    assert vorschau(11) == 422
    assert vorschau(12) == 200


def test_zwoelf_ist_der_kleinste_wert_mit_blockgegenstellen_und_eingehenden():
    """Die Zahl ist nicht gewuerfelt, sondern Cores eigene Rechnung
    (src/net.h, v31.1): erst acht volle Gegenstellen, dann zwei reine
    Block-Gegenstellen, dann ein Fuehler -- und nur, was danach uebrig ist,
    steht Eingehenden offen. Aendert Core die Konstanten, gehoert die
    Untergrenze neu nachgerechnet, nicht dieser Test angepasst."""
    from satcortex import api

    def plaetze(n):
        voll = min(8, n)
        block = min(2, n - voll)
        eingehend = max(0, n - (voll + block + 1))
        return block, eingehend

    assert plaetze(8) == (0, 0), "bei 8 keine einzige Block-Gegenstelle"
    kleinster = next(n for n in range(126)
                     if plaetze(n)[0] == 2 and plaetze(n)[1] >= 1)
    assert kleinster == api.MINDEST_VERBINDUNGEN == 12


def test_struktur_steht_schon_vor_dem_abschluss(client):
    """Die Verzeichnisse entstehen beim START der Anwendung, nicht erst beim
    Abschliessen des Assistenten. Vorher hing die ganze Struktur an einer
    Platzpruefung -- auf einem Geraet ohne 860 GB frei kam sie nie zustande,
    und schon das Anlegen des Kontos hatte keinen Ort."""
    assert (client.tmp / "bulk" / "blocks").is_dir()
    assert (client.tmp / "fast" / "config").is_dir()
    assert (client.tmp / "fast" / "bitcoind" / "indexes").is_symlink()


def test_abschluss_legt_alles_an_und_weckt_die_dienste(client):
    d = client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True}).json()

    assert d["ok"] is True

    zustaende = {x["name"]: x["zustand"] for x in d["dienste"]}
    assert zustaende["bitcoind"] == "freigegeben"
    assert zustaende["tor"] == "freigegeben"


def test_abschluss_ohne_tor_laesst_tor_gesperrt(client):
    d = client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": False}).json()
    zustaende = {x["name"]: x["zustand"] for x in d["dienste"]}
    assert zustaende["tor"] == "unkonfiguriert"
    assert zustaende["bitcoind"] == "freigegeben"


def test_geschriebene_konfiguration_ist_die_echte(client):
    client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 1500, "upload_gb_pro_monat": 0,
        "verbindungen": 125, "tor_aktiv": True})
    text = (client.tmp / "config" / "bitcoind.conf").read_text()
    # Waehrend des Erstabgleichs sind die Indizes aus -- die Anwendung
    # schaltet sie ein, sobald die Kette steht.
    assert "txindex=0" in text
    assert "peerblockfilters=0" in text
    assert "prune=0" in text
    assert "maxuploadtarget=0" in text        # unbegrenzt, wie gewaehlt
    assert "maxconnections=125" in text
    assert nodeconfig.lies_tor(text)
    assert "{{" not in text


def test_status_nach_dem_abschluss(client):
    client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    d = client.get("/api/status").json()
    assert d["eingerichtet"] is True
    # bitcoind und tor. Fest verdrahtete Zahlen altern schlecht -- gegen die
    # Liste pruefen, die die Anwendung tatsaechlich fuehrt.
    assert [x["name"] for x in d["dienste"]] == api.DIENSTE


def test_zu_wenig_platz_verhindert_den_abschluss(client_ohne_platz):
    """Die wichtigste Sperre: lieber jetzt abbrechen als nach zwei Wochen
    Erstsync mit voller Platte stehenbleiben."""
    antwort = client_ohne_platz.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    assert antwort.status_code == 400
    detail = antwort.json()["detail"]
    assert detail["meldung"] == "platz_reicht_nicht"
    assert detail["bulk"]["meldung"] == "platz_zu_wenig"
    assert not (client_ohne_platz.tmp / "config" / "bitcoind.conf").exists()


def test_assistent_laesst_sich_bis_zum_ende_durchklicken(client):
    """Der Weg, den ein Nutzer tatsaechlich geht.

    Die bisherigen Tests riefen /abschliessen direkt auf und haben damit den
    entscheidenden Fall verfehlt: wer sich durch den Assistenten klickt, steht
    beim Druecken des Knopfes auf dem LETZTEN Schritt. Die Sperre gegen
    doppelte Einrichtung prueft aber genau darauf -- und machte den Assistenten
    dadurch unbenutzbar. Jeder Versuch endete mit 409, ohne dass je etwas
    eingerichtet wurde.
    """
    # bis ans Ende blaettern, wie die Oberflaeche es tut
    for _ in range(10):
        d = client.get("/api/einrichtung").json()
        if d["fertig"]:
            break
        client.post("/api/einrichtung/weiter", json={})
    else:
        raise AssertionError("Der Assistent erreicht sein Ende nicht.")

    # Auf dem letzten Schritt darf noch NICHTS eingerichtet sein.
    assert client.get("/api/status").json()["eingerichtet"] is False

    a = client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    assert a.status_code == 200, a.json()

    assert client.get("/api/status").json()["eingerichtet"] is True

    # Und erst JETZT greift die Sperre.
    zweiter = client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    assert zweiter.status_code == 409


def test_auf_der_zusammenfassung_darf_man_zurueck(client):
    """Dort korrigiert man seine Wahl -- vorher war das gesperrt."""
    for _ in range(10):
        if client.get("/api/einrichtung").json()["fertig"]:
            break
        client.post("/api/einrichtung/weiter", json={})
    vorher = client.get("/api/einrichtung").json()["schritt"]
    client.post("/api/einrichtung/zurueck")
    assert client.get("/api/einrichtung").json()["schritt"] != vorher


def test_oberflaeche_wird_nicht_blind_zwischengespeichert(client):
    """Sonst behaelt der Browser nach einem Update die alte Fassung.

    Beim Rollout genau so passiert: der Container lieferte die reparierte
    app.js aus, Safari nahm die alte aus dem Zwischenspeicher und fragte nicht
    einmal nach. Im Server-Protokoll fehlte die Anfrage dann komplett -- was
    die Suche in die voellig falsche Richtung geschickt hat.
    """
    # "/" gehoert unbedingt dazu -- und stand hier bis zum 03.09.2026 nicht
    # drin. Es ist der einzige dieser Wege, den ein Mensch wirklich eintippt;
    # die benannten Dateien holt der Browser nur nach. Genau der ungeprueften
    # Startseite fehlte die Kopfzeile, und Safari hielt beim Neuladen eine
    # alte Huelle fest, deren Gegenstelle es nicht mehr gab.
    for datei in ("/", "/app.js", "/style.css", "/index.html"):
        a = client.get(datei)
        if a.status_code != 200:
            continue
        steuerung = a.headers.get("cache-control", "")
        assert "no-cache" in steuerung, f"{datei} hat Cache-Control: {steuerung!r}"


# ── Adresse nachtragen, ohne den Assistenten zu wiederholen (26.08.2026) ────

def _richte_ein(client, **abweichungen):
    wahl = {"speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
            "verbindungen": 80, "tor_aktiv": True}
    wahl.update(abweichungen)
    return client.post("/api/einrichtung/abschliessen", json=wahl)


def test_adresse_aus_dem_assistenten_landet_in_der_konfiguration(client):
    _richte_ein(client, externe_adresse="203.0.113.7")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=203.0.113.7" in conf


def test_adresse_laesst_sich_nachtragen(client):
    """Der Fall vom 26.08.: eingerichtet, Knoten laeuft, Adresse fehlt."""
    _richte_ein(client)
    r = client.post("/api/knoten/adresse", json={"externe_adresse": "203.0.113.8"})
    assert r.status_code == 200

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=203.0.113.8" in conf


def test_nachtragen_laesst_alles_andere_unangetastet(client):
    """Der Weg ist eng gebaut: er darf Tor nicht abschalten, das Upload-Budget
    nicht wuergen und die Verbindungszahl nicht druecken -- Letzteres
    erleichtert eine Eclipse-Attacke erheblich."""
    _richte_ein(client, verbindungen=80, upload_gb_pro_monat=300, tor_aktiv=True)
    client.post("/api/knoten/adresse", json={"externe_adresse": "203.0.113.10"})

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "maxconnections=80" in conf
    assert nodeconfig.lies_tor(conf)
    assert "maxuploadtarget=0" not in conf


def test_rpc_zugangsdaten_ueberleben_das_nachtragen(client):
    """Neue Zugangsdaten wuerden die Anwendung von ihrem eigenen Knoten
    aussperren."""
    _richte_ein(client)
    vorher = (client.tmp / "config" / "bitcoind.conf").read_text()
    zeile = [z for z in vorher.splitlines() if z.startswith("rpcauth=")][0]

    client.post("/api/knoten/adresse", json={"externe_adresse": "203.0.113.10"})
    nachher = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert zeile in nachher


def test_ohne_einrichtung_gibt_es_nichts_nachzutragen(client):
    r = client.post("/api/knoten/adresse", json={"externe_adresse": "203.0.113.10"})
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "noch_nicht_eingerichtet"


def test_adresse_nachtragen_braucht_eine_anmeldung(tmp_path, monkeypatch):
    from satcortex import api, settings
    from fastapi.testclient import TestClient
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    c = TestClient(api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"))))
    assert c.post("/api/knoten/adresse",
                  json={"externe_adresse": "203.0.113.10"}).status_code == 401


def test_adresse_nachtragen_geht_auch_bei_alter_einrichtung(client):
    """Des Betreibers Fall am 26.08.: eingerichtet unter 0.3.2, wo die Auswahl noch
    nicht festgehalten wurde. Die erste Fassung dieses Weges lehnte das ab und
    verlangte eine komplette Neueinrichtung -- fuer eine einzige Zeile."""
    _richte_ein(client)

    # Den Zustand auf den Stand von damals zuruecksetzen: Konfiguration da,
    # gespeicherte Wahl weg.
    from satcortex import state
    ablage = state.Ablage(str(client.tmp / "config"))
    e = ablage.laden()
    e.knotenwahl = {}
    ablage.speichern(e)

    r = client.post("/api/knoten/adresse", json={"externe_adresse": "203.0.113.9"})
    assert r.status_code == 200, r.json()

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=203.0.113.9" in conf
    assert "maxconnections=80" in conf, "die uebrige Konfiguration muss stehen bleiben"


def test_unaufloesbarer_name_landet_nicht_in_der_konfiguration(client):
    """Lieber gar keine Adresse als eine, die niemand aufloesen kann -- der
    Knoten wuerde sonst mit etwas werben, das ins Leere zeigt."""
    _richte_ein(client)
    r = client.post("/api/knoten/adresse",
                    json={"externe_adresse": "gibtsnicht.invalid"})
    assert r.status_code == 200
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert not any(z.startswith("externalip=") for z in conf.splitlines())


# ── Der Hintergrundwaechter darf unter keinen Umstaenden sterben ────────────

def test_scheiternde_aufloesung_kippt_den_endpunkt_nicht(client, monkeypatch):
    """Der Weg zum Eintragen der Adresse darf bei einem DNS-Problem keinen
    Serverfehler liefern -- der Nutzer soll es spaeter erneut versuchen
    koennen, nicht auf eine 500 starren."""
    from satcortex import api as api_modul
    _richte_ein(client)

    monkeypatch.setattr(api_modul.dyndns, "loese_auf", lambda *_a, **_k: [])
    r = client.post("/api/knoten/adresse", json={"externe_adresse": "irgendwas.example"})
    assert r.status_code == 200

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert not any(z.startswith("externalip=") for z in conf.splitlines())


def test_status_zeigt_mempool_erst_nach_dem_abgleich(client, monkeypatch):
    """Waehrend des Erstsyncs nimmt Core keine Transaktionen an; ein
    Mempool-Block waere dort eine leere Kachel."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 400_000, "kopfzeilen": 964_000,
        "fortschritt": 0.07, "im_erstsync": True, "belegt_bytes": 1,
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_452_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})
    d = client.get("/api/status").json()
    assert "mempool" not in d
    assert "tempo" in d


# ── Nur ueber Tor erreichbar sein (27.08.2026) ──────────────────────────────

def test_abgeschaltet_kuendigt_keine_adresse_an(client):
    """Fuer Betreiber, die ausschliesslich ueber Tor erreichbar sein wollen."""
    _richte_ein(client, externe_adresse="203.0.113.7")
    r = client.post("/api/knoten/adresse",
                    json={"externe_adresse": "203.0.113.7", "ankuendigen": False})
    assert r.status_code == 200

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert not any(z.startswith("externalip=") for z in conf.splitlines())
    # Tor bleibt an: die .onion haelt Tor selbst, sie haengt nicht an der
    # Clearnet-Adresse.
    assert nodeconfig.lies_tor(conf)


def test_der_name_bleibt_beim_abschalten_gespeichert(client):
    """Wer zurueckschaltet, soll ihn nicht neu tippen muessen."""
    _richte_ein(client)
    client.post("/api/knoten/adresse",
                json={"externe_adresse": "203.0.113.7", "ankuendigen": False})
    wahl = client.get("/api/status").json()["einrichtung"]["knotenwahl"]
    assert wahl["externe_adresse"] == "203.0.113.7"
    assert wahl["adresse_ankuendigen"] is False


def test_zurueckschalten_kuendigt_wieder_an(client):
    _richte_ein(client)
    client.post("/api/knoten/adresse",
                json={"externe_adresse": "203.0.113.7", "ankuendigen": False})
    client.post("/api/knoten/adresse",
                json={"externe_adresse": "203.0.113.7", "ankuendigen": True})
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=203.0.113.7" in conf


def test_ohne_adresse_im_assistenten_startet_der_schalter_aus(client):
    """Wer nichts angibt, will auch nichts angekuendigt haben."""
    _richte_ein(client)
    wahl = client.get("/api/status").json()["einrichtung"]["knotenwahl"]
    assert wahl["adresse_ankuendigen"] is False


def test_status_nennt_alle_drei_projekte(client):
    """Lightning wird genauso geprueft wie Bitcoin Core -- und seit dem
    21.09.2026 die Anwendung selbst.

    Der Anlass kam aus dem Betrieb: der Knoten lief auf 0.66, 1.0.1 lag
    bereit, und die Oberflaeche erwaehnte es mit keinem Wort. Wer seine
    eigene Software ausliefert, soll auch sagen, wenn es eine neuere gibt.

    Der Abbildname muss mitkommen, weil die Oberflaeche daraus die Zeile zum
    Uebernehmen baut. Ohne ihn stuende dort "image: :0.21.2-beta"."""
    d = client.get("/api/status").json()["neuerungen"]
    assert set(d) == {"satcortex", "bitcoind", "lnd"}
    assert d["bitcoind"]["abbild"].endswith("satcortex-bitcoind")
    assert d["lnd"]["abbild"].endswith("satcortex-lnd")
    assert d["satcortex"]["abbild"].endswith("/satcortex")
    # Noch nichts nachgeschlagen: die Anzeige sagt dann "noch nicht gesehen"
    # statt "aktuell". Der Unterschied ist wichtig.
    assert d["lnd"]["stand"] is None and d["lnd"]["gefunden"] is None


def test_die_fassungspruefung_braucht_keinen_knoten(client, monkeypatch):
    """Aus dem Betrieb, 03.09.2026: "der fassungskasten hat nie zu schweigen ...
    eine begruendung fuer ne fehl funktion ist trotzdem eine fehlfunktion".

    Er hat recht. Die Auskunft liegt fertig im Arbeitsspeicher; sie hing nur
    als Beipack an /status, und der wartet auf bitcoind. Dieser Weg darf
    keinen einzigen RPC-Aufruf ausloesen -- dann kann er auch nicht in eine
    Frist laufen.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    def keiner(*_a, **_k):
        raise AssertionError("die Fassungspruefung hat den Knoten gefragt")

    monkeypatch.setattr(rpc_modul, "kettenlage", keiner)
    monkeypatch.setattr(rpc_modul, "lage_mit_grund", keiner)

    d = client.get("/api/neuerungen").json()["neuerungen"]
    assert set(d) == {"satcortex", "bitcoind", "lnd"}


def test_der_kasten_nennt_immer_beide_zahlen(client):
    """Was laeuft, und was es draussen gibt -- notfalls als None, aber die
    Felder sind da. Ohne sie kann die Anzeige nur Fliesstext zeigen."""
    d = client.get("/api/neuerungen").json()["neuerungen"]
    for name in ("satcortex", "bitcoind", "lnd"):
        assert "laufend" in d[name], name
        assert "neueste" in d[name], name


def test_die_tor_pause_schaltet_die_versionsabfrage_nicht_ab(client, monkeypatch):
    """Die Frage aus dem Betrieb am 03.09.2026: "weil ich tor abgeschaltet habe fuer den
    erst sync lauf?? schaltet er auch tor ab fuer die versions abfrage?"

    Nein. Es sind zwei verschiedene Schalter. Die Pause aendert nur, ueber
    welche Netze bitcoind seine Gegenstellen sucht (onlynet); der Tor-Dienst
    selbst haengt allein an tor_aktiv und laeuft weiter. Die Versionsabfrage
    geht ueber genau diesen Dienst.

    Waere es anders, stuende im Kasten "Ohne Tor wird nicht nachgefragt" --
    ein Satz. Der Betreiber sah gar nichts, und das hatte einen anderen Grund.
    """
    from satcortex import rpc as rpc_modul
    from satcortex import updates as updates_modul
    _richte_ein(client)          # tor_aktiv=True, Pause auf der Vorgabe True

    wahl = client.get("/api/status").json()["einrichtung"]["knotenwahl"]
    assert wahl["tor_aktiv"] is True
    assert wahl["tor_pause_beim_abgleich"] is True, "sonst prueft der Test nichts"

    gefragt = []
    monkeypatch.setattr(updates_modul, "hole_versionen",
                        lambda proxy=None, projekt=None: (gefragt.append(proxy), [])[1])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 680_000, "kopfzeilen": 964_000,
        "fortschritt": 0.6, "im_erstsync": True, "belegt_bytes": 1,
        "kennung": "/Satoshi:31.1.0/",
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_600_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})

    client.app.state.einmal_nachsehen()

    d = client.get("/api/status").json()["neuerungen"]
    assert d["bitcoind"]["grund"] != "tor_aus"
    assert gefragt, "waehrend der Pause wurde gar nicht erst ueber Tor gefragt"
    assert gefragt[0].startswith("http://"), gefragt[0]


def _mit_fassung(tmp_path, monkeypatch, version, abbild_tag=""):
    """Ein Client, der sich fuer eine veroeffentlichte Fassung haelt."""
    _platz(monkeypatch, 4000)
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(exist_ok=True); fast.mkdir(exist_ok=True)
    konf = settings.Einstellungen(bulk=str(bulk), fast=str(fast),
                                  config_dir=str(tmp_path / "config"),
                                  version=version, abbild_tag=abbild_tag)
    return _client(tmp_path, konf=konf)


def _versionen_und_kette(monkeypatch, gefragt):
    from satcortex import rpc as rpc_modul
    from satcortex import updates as updates_modul

    def hole(proxy=None, projekt=None):
        gefragt.append(projekt.name)
        if projekt.name == "satcortex":
            return [(1, 0, 2), (1, 0, 3), (1, 0, 4), (1, 1, 0), (1, 2, 0)]
        if projekt.name == "lnd":
            return [(0, 21, 3)]          # LND traegt immer drei Stellen
        return [(31, 1)]
    monkeypatch.setattr(updates_modul, "hole_versionen", hole)
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 964_000, "kopfzeilen": 964_000,
        "fortschritt": 1.0, "im_erstsync": False, "belegt_bytes": 1,
        "kennung": "/Satoshi:31.1.0/",
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_758_600_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})


def test_der_kasten_weiss_wem_die_installation_folgt(tmp_path, monkeypatch):
    """Aus dem Betrieb, 23.09.2026: "ich will ja immer latest! und nicht
    gepinnt auf eine version!" -- und der Kasten reichte ihm eine Zeile zum
    Festnageln. Er muss wissen, wem die Installation folgt, sonst kann er
    nicht den richtigen Weg nennen."""
    c = _mit_fassung(tmp_path, monkeypatch, "1.0.2", abbild_tag="latest")
    _richte_ein(c)
    gefragt = []
    _versionen_und_kette(monkeypatch, gefragt)
    c.app.state.einmal_nachsehen()

    eigen = c.get("/api/neuerungen").json()["neuerungen"]["satcortex"]
    assert eigen["folgt"] == "latest"
    assert eigen["laufend"] == "1.0.2"
    # Die neueste, nicht die neueste 1.0.x -- das war der Befund.
    assert eigen["gefunden"]["version"] == "1.2.0"
    assert eigen["gefunden"]["art"] == "neuer"


def test_ohne_angabe_ist_unbekannt_wem_sie_folgt(client):
    """Eine Compose-Datei von vor dem 23.09.2026 reicht den Wert nicht
    durch. Dann ist es UNBEKANNT -- nicht "latest" und nicht eine Nummer,
    denn beides waere geraten."""
    eigen = client.get("/api/neuerungen").json()["neuerungen"]["satcortex"]
    assert eigen["folgt"] is None


def test_die_eigene_fassung_wird_oefter_nachgesehen_als_core(tmp_path,
                                                             monkeypatch):
    """"Einmal am Tag genuegt" stand als Begruendung fuer ZWEI Projekte da,
    die ein paar Mal im Jahr erscheinen. SatoshiCortex hatte in neunzehn
    Stunden vier Fassungen -- und der Kasten zeigte einen Tag lang eine
    Auskunft von vor dreien davon."""
    from satcortex import updates as updates_modul
    c = _mit_fassung(tmp_path, monkeypatch, "1.0.2", abbild_tag="latest")
    _richte_ein(c)
    gefragt = []
    _versionen_und_kette(monkeypatch, gefragt)
    uhr = [1_758_600_000.0]
    monkeypatch.setattr(api.time, "time", lambda: uhr[0])

    c.app.state.einmal_nachsehen()
    assert gefragt.count("satcortex") == 1 and gefragt.count("bitcoind") == 1

    uhr[0] += updates_modul.INTERVALL_EIGENE_SEKUNDEN + 1
    c.app.state.einmal_nachsehen()
    assert gefragt.count("satcortex") == 2, "die eigene Fassung ist faellig"
    assert gefragt.count("bitcoind") == 1, "Core bleibt bei einmal am Tag"

    uhr[0] += updates_modul.INTERVALL_SEKUNDEN
    c.app.state.einmal_nachsehen()
    assert gefragt.count("bitcoind") == 2


def test_der_kasten_nennt_den_zeitpunkt_der_auskunft(tmp_path, monkeypatch):
    """"Neueste bekannte" heisst: bekannt SEIT WANN. Ohne den Zeitpunkt sah
    eine Auskunft von gestern aus wie eine von eben."""
    c = _mit_fassung(tmp_path, monkeypatch, "1.0.2", abbild_tag="latest")
    _richte_ein(c)
    _versionen_und_kette(monkeypatch, [])
    c.app.state.einmal_nachsehen()
    eigen = c.get("/api/neuerungen").json()["neuerungen"]["satcortex"]
    assert isinstance(eigen["stand"], (int, float)) and eigen["stand"] > 0


def test_karte_antwortet_auch_ohne_knoten(client):
    """Ohne bitcoind bleibt die Karte leer -- aber sie antwortet. Ein Fehler
    hier wuerde die halbe Uebersicht mitreissen."""
    d = client.get("/api/karte").json()
    assert d["eingerichtet"] is False        # Assistent noch nicht durch


def test_karte_holt_das_adressbuch_nicht_im_anfrageweg(client, monkeypatch):
    """Das Adressbuch ist der einzige teure Aufruf der Anwendung -- mit
    dreissig Sekunden Frist. Passierte er im Anfrageweg, haenge die Seite,
    und zwar ausgerechnet beim ersten Aufruf der Karte."""
    client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})

    gerufen = []
    monkeypatch.setattr(api.karte, "verorte_adressbuch",
                        lambda *a, **k: gerufen.append(1) or ({}, 0, 0))

    d = client.get("/api/karte").json()
    assert d["eingerichtet"] is True
    # Die Antwort steht, bevor irgendetwas ausgewertet ist.
    assert d["buch_stand"] is None
    assert d["laender"] == []


def test_auswertung_antwortet_von_anfang_an(client):
    """Auch wenn noch nichts gesammelt wurde. Eine leere Auswertung ist ein
    Zustand, kein Fehler."""
    d = client.get("/api/auswertung").json()
    assert d["transaktionen"] == 0 and d["bloecke"] == 0
    assert d["bloecke_liste"] == [] and d["sammelt_seit_ms"] is None
    assert d["laeuft"] is False        # der Zulauf wartet auf den Abgleich


def test_verfolgen_weist_unsinn_ab(client):
    """Der Pfad geht ungeprueft in eine Datenbankabfrage -- da gehoert eine
    Schranke davor."""
    for unsinn in ("kurz", "z" * 64, "../../etc/passwd", ""):
        assert client.get(f"/api/auswertung/tx/{unsinn}").status_code in (400, 404)


def test_verfolgen_nennt_den_eigenen_zeitstempel(client):
    """Das ist der Punkt der Ansicht: nicht 'wann wurde bestaetigt', sondern
    'wann habe ICH sie zuerst gesehen'."""
    from satcortex import store as st
    txid = "ab" * 32
    # In dieselbe Datei schreiben, die die Anwendung benutzt.
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    ablage.tx_aufgenommen(txid, 1_700_000_000_000, 42)
    ablage.sichern()
    ablage.schliesse()

    d = client.get(f"/api/auswertung/tx/{txid}").json()
    assert d["eigen"]["zuerst_ms"] == 1_700_000_000_000
    assert d["knoten"] is None          # bitcoind laeuft im Test nicht
    assert d["cluster"] is None


def _bitcoind(monkeypatch, antworten):
    """bitcoind nachstellen: Methode -> Antwort (oder aufrufbar)."""
    from satcortex import rpc as rpc_modul
    aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None):
        aufrufe.append((methode, params))
        if methode in antworten:
            a = antworten[methode]
            return a(*params) if callable(a) else a
        raise rpc_modul.NichtErreichbar("im Test nicht da")
    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)
    return aufrufe


def test_eine_wartende_transaktion_zeigt_ihren_cluster(client, monkeypatch):
    txid = "bb" * 32
    _bitcoind(monkeypatch, {
        "getrawtransaction": {"vsize": 141, "confirmations": 0, "vin": [{}],
                              "vout": [{}, {}]},
        "getmempoolcluster": {"clusterweight": 1400, "txcount": 2, "chunks": [
            {"chunkfee": 0.000021, "chunkweight": 1400,
             "txs": ["aa" * 32, txid]}]},
    })
    d = client.get(f"/api/auswertung/tx/{txid}").json()
    assert d["cluster"]["eigenes_paket"] == 1
    assert d["cluster"]["pakete"][0]["satz_sat_vb"] == 6.0


def test_eine_bestaetigte_transaktion_hat_keinen_cluster(client, monkeypatch):
    txid = "bb" * 32
    aufrufe = _bitcoind(monkeypatch, {
        "getrawtransaction": {"vsize": 141, "confirmations": 3, "vin": [],
                              "vout": []}})
    d = client.get(f"/api/auswertung/tx/{txid}").json()
    assert d["cluster"] is None
    assert "getmempoolcluster" not in [m for m, _ in aufrufe]


def test_die_pool_anteile_kommen_aus_der_eigenen_ablage(client):
    from satcortex import store as st
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    for hoehe, pool in ((10, "Foundry USA"), (11, "AntPool"), (12, "Foundry USA")):
        ablage.block_eingetragen({
            "hoehe": hoehe, "hash": f"h{hoehe}", "blockzeit": 0,
            "empfangen_ms": 0, "gewicht": 0, "txzahl": 0, "gebuehren_sat": 0,
            "pool": pool, "botschaft": None, "bekannte_tx": 0,
            "verweildauer_ms": None})
    ablage.sichern()
    ablage.schliesse()
    d = client.get("/api/auswertung/pools?bloecke=144").json()
    assert d["fenster"] == 144 and d["bloecke"] == 3
    assert d["pools"][0]["pool"] == "Foundry USA" and d["pools"][0]["anzahl"] == 2
    assert client.get("/api/auswertung/pools?bloecke=7").status_code == 400


def test_die_auswertung_nennt_das_alter_des_diagramms(client):
    d = client.get("/api/auswertung").json()
    assert "diagramm_zeit_s" in d and "reorgs_24h" in d


ADRESSE = "bc1q" + "a" * 38


def _scan(monkeypatch, halt=None, gueltig=True):
    """validateaddress und scantxoutset nachstellen. Mit "halt" bleibt der Scan
    stehen, bis jemand ihn freigibt -- so laesst sich der laufende Zustand
    pruefen."""
    import threading
    abgebrochen = threading.Event()

    def scan(aktion, *rest):
        if aktion == "status":
            return {"progress": 42}
        if aktion == "abort":
            abgebrochen.set()
            if halt is not None:
                halt.set()
            return True
        if halt is not None:
            halt.wait(5)
        if abgebrochen.is_set():
            return {"success": False}
        return {"success": True, "txouts": 180_000_000, "height": 966_963,
                "total_amount": 0.30000000000000004, "unspents": [
                    {"txid": "cd" * 32, "vout": 1, "amount": 0.1,
                     "height": 966_900, "confirmations": 64},
                    {"txid": "ef" * 32, "vout": 0, "amount": 0.2,
                     "height": 966_950, "confirmations": 14}]}
    return _bitcoind(monkeypatch, {
        "validateaddress": lambda a: {"isvalid": gueltig, "address": a},
        "scantxoutset": scan})


def _warte_auf_ende(client):
    import time
    for _ in range(200):
        stand = client.get("/api/auswertung/adresse").json()
        if not stand["laeuft"]:
            return stand
        time.sleep(0.02)
    raise AssertionError("der Scan wurde nie fertig")


def test_eine_adresse_wird_im_hintergrund_abgefragt(client, monkeypatch):
    """Core braucht fuer einen Scan Minuten -- eine so lange offene Anfrage
    bricht ein Proxy ab. Also im Hintergrund, mit Stand zum Abfragen."""
    import threading
    halt = threading.Event()
    aufrufe = _scan(monkeypatch, halt=halt)
    r = client.post("/api/auswertung/adresse", json={"adresse": ADRESSE})
    assert r.status_code == 200, r.text
    zweiter = client.post("/api/auswertung/adresse", json={"adresse": ADRESSE})
    assert zweiter.status_code == 409, "zwei Scans gleichzeitig kann Core nicht"
    stand = client.get("/api/auswertung/adresse").json()
    assert stand["laeuft"] is True and stand["fortschritt"] == 42
    halt.set()
    stand = _warte_auf_ende(client)
    assert stand["fehler"] is None
    assert stand["ergebnis"]["bestand_sat"] == 30_000_000
    assert [a["hoehe"] for a in stand["ergebnis"]["ausgaben"]] == [966_950, 966_900]
    start = [p for m, p in aufrufe if m == "scantxoutset" and p[0] == "start"]
    assert start[0][1] == [f"addr({ADRESSE})"]


def test_eine_ungueltige_adresse_startet_keinen_scan(client, monkeypatch):
    aufrufe = _scan(monkeypatch, gueltig=False)
    for eingabe in (ADRESSE, ADRESSE + "),raw(00"):
        r = client.post("/api/auswertung/adresse", json={"adresse": eingabe})
        assert r.status_code == 400
        assert r.json()["detail"]["meldung"] == "adresse_ungueltig"
    assert "scantxoutset" not in [m for m, _ in aufrufe]


def test_ein_scan_laesst_sich_abbrechen(client, monkeypatch):
    import threading
    halt = threading.Event()
    _scan(monkeypatch, halt=halt)
    assert client.post("/api/auswertung/adresse",
                       json={"adresse": ADRESSE}).status_code == 200
    assert client.post("/api/auswertung/adresse/abbrechen").status_code == 200
    stand = _warte_auf_ende(client)
    assert stand["fehler"] == "a_ad_abgebrochen" and stand["ergebnis"] is None


# ── Lightning ──────────────────────────────────────────────────────────────

def test_lightning_antwortet_bevor_es_lightning_gibt(client):
    """Ueber Tage der Normalzustand: der Container laeuft und wartet, LND
    antwortet nicht, eine Wallet gibt es nicht. Nichts davon ist ein Fehler,
    und die Ansicht darf daran nicht zerbrechen."""
    client.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})

    d = client.get("/api/lightning").json()
    assert d["eingerichtet"] is True
    # Der Assistent richtet lnd bewusst NICHT mit ein.
    assert d["dienst"]["zustand"] == "unkonfiguriert"
    assert d["knoten"] == {"da": False, "stand": "aus", "roh": None}
    # Ohne bitcoind gilt die Kette als nicht fertig -- lieber warten als eine
    # Wallet auf einer halben Kette anlegen.
    assert d["kette_bereit"] is False


def test_lightning_vor_der_einrichtung(client):
    assert client.get("/api/lightning").json() == {"eingerichtet": False}


def test_lnd_steht_in_der_dienstliste(client):
    """Der Container laeuft von Anfang an mit. Ihn zu verschweigen, weil er
    noch nichts tut, waere die falsche Freundlichkeit: wer in der Uebersicht
    nachsieht, soll ihn finden."""
    namen = [d["name"] for d in client.get("/api/status").json()["dienste"]]
    assert "lnd" in namen


# ── Indizes an der Betriebsphase ───────────────────────────────────────────

def _konf_mit_indizes(client, an):
    """Die Konfiguration auf einen bekannten Stand bringen."""
    from satcortex import nodeconfig
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), an))
    return pfad


def test_indizes_gehen_waehrend_des_abgleichs_aus(client, monkeypatch):
    """Der Fall, den ein erster Entwurf verfehlte: ein Knoten, der mitten im
    Abgleich steckt und die Indizes noch an hat. Wer nur einschaltet, laesst
    genau die stehen, denen es am meisten nuetzen wuerde."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = _konf_mit_indizes(client, True)          # wie eine alte Anlage

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 680_000, "kopfzeilen": 964_000,
        "fortschritt": 0.6, "im_erstsync": True, "belegt_bytes": 1,
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_600_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})
    client.app.state.einmal_nachsehen()

    text = pfad.read_text()
    assert "txindex=0" in text
    # Der Fallstrick: ohne diesen dritten Schalter startet Core nicht mehr.
    assert "peerblockfilters=0" in text
    # Und die Zugangsdaten stehen weiter drin.
    assert "rpcauth=" in text


def test_indizes_kommen_zurueck_wenn_die_kette_steht(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = _konf_mit_indizes(client, False)

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 964_000, "kopfzeilen": 964_000,
        "fortschritt": 1.0, "im_erstsync": False, "belegt_bytes": 1,
        "verbindungen_ein": 3, "verbindungen_aus": 10, "erreichbar": True,
        "blockzeit": 1_780_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})
    client.app.state.einmal_nachsehen()

    text = pfad.read_text()
    assert "txindex=1" in text and "peerblockfilters=1" in text


def test_der_waechter_schreibt_nicht_bei_jedem_durchgang(client, monkeypatch):
    """Jede Aenderung an der Konfiguration startet bitcoind neu. Ein Waechter,
    der ohne Anlass schreibt, wuerde den Knoten alle paar Minuten
    durchstarten -- und der Abgleich kaeme nie voran."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 680_000, "kopfzeilen": 964_000,
        "fortschritt": 0.6, "im_erstsync": True, "belegt_bytes": 1,
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_600_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})

    client.app.state.einmal_nachsehen()
    erste = pfad.read_text()
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()
    assert pfad.read_text() == erste


def test_die_kettenlage_wird_nicht_dreimal_je_takt_geholt(client, monkeypatch):
    """Die Oberflaeche fragt alle zehn Sekunden nach und ruft dabei mehrere
    Endpunkte an. Zwei davon holten sich die Kettenlage getrennt -- zwei Mal
    getblockchaininfo im Abstand von Millisekunden, mit garantiert derselben
    Antwort. Waehrend des Abgleichs ist das nicht egal: der Aufruf braucht
    cs_main, und genau die haelt Core beim Wegschreiben."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    gerufen = []

    def einmal(_k, *_a):
        gerufen.append(1)
        return {"kette": "main", "hoehe": 688_000, "kopfzeilen": 964_000,
                "fortschritt": 0.46, "im_erstsync": True, "belegt_bytes": 1,
                "verbindungen_ein": 0, "verbindungen_aus": 10,
                "erreichbar": False, "blockzeit": 1_620_000_000,
                "adressen": [], "netze": {}, "empfangen_bytes": 0,
                "gesendet_bytes": 0}
    monkeypatch.setattr(rpc_modul, "kettenlage", einmal)

    client.get("/api/status")
    client.get("/api/lightning")
    assert len(gerufen) == 1, "zweimal geholt, obwohl dieselbe Antwort"


# ── Ausgehende Netze waehrend des Abgleichs ────────────────────────────────

def _lage(**mehr):
    d = {"kette": "main", "hoehe": 688_000, "kopfzeilen": 964_000,
         "fortschritt": 0.46, "im_erstsync": True, "belegt_bytes": 1,
         "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
         "blockzeit": 1_620_000_000, "adressen": [],
         "netze": {"ipv4": 5, "onion": 5},
         "empfangen_bytes": 0, "gesendet_bytes": 0}
    d.update(mehr)
    return d


def test_tor_ausgang_geht_waehrend_des_abgleichs_aus(client, monkeypatch):
    from satcortex import nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    # Die Indizes vorher auf den Sollzustand, damit dieser Waechter drankommt.
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    text = pfad.read_text()
    assert "onlynet=ipv4" in text and "onlynet=ipv6" in text
    # Die Onion-Adresse bleibt: onlynet gilt nur fuer AUSGEHENDE Verbindungen.
    assert nodeconfig.lies_tor(text)
    assert "rpcauth=" in text


def test_ohne_clearnet_wird_tor_nicht_abgeschaltet(client, monkeypatch):
    """Sonst haette der Knoten womoeglich gar keine Verbindungen mehr --
    ein Schuss ins Knie, und zwar ein stiller."""
    from satcortex import nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))

    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(netze={"onion": 8}))
    client.app.state.einmal_nachsehen()
    assert "onlynet=" not in pfad.read_text()


def test_ohne_tor_wird_nichts_umgeschrieben(client, monkeypatch):
    """Nichts abzuschalten heisst: nichts anfassen. Jede Aenderung startet
    bitcoind neu."""
    from satcortex import nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))
    vorher = pfad.read_text()

    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(netze={"ipv4": 10}))
    client.app.state.einmal_nachsehen()
    # Nur der Cache darf sich geaendert haben, kein onlynet.
    assert "onlynet=" not in pfad.read_text()


def test_nach_dem_abgleich_darf_tor_wieder_hinaus(client, monkeypatch):
    from satcortex import nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    text = nodeconfig.setze_indizes(pfad.read_text(), True)
    pfad.write_text(nodeconfig.setze_netze(text, ("ipv4", "ipv6")))

    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(im_erstsync=False, fortschritt=1.0))
    client.app.state.einmal_nachsehen()
    assert "onlynet=" not in pfad.read_text()


def test_ein_einziger_schreibvorgang_fuer_alles(client, monkeypatch):
    """Cache, Indizes und Ausgangsnetze aendern sich beim Uebergang alle drei.
    Frueher schrieb jede Anpassung fuer sich, und jede startet bitcoind neu --
    bei einem Waechter im Zehn-Minuten-Takt waeren das drei Neustarts ueber
    eine halbe Stunde. Jetzt genuegt EIN Durchgang, und danach ist Ruhe."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    vorher = pfad.read_text()
    client.app.state.einmal_nachsehen()
    nach_eins = pfad.read_text()
    assert nach_eins != vorher, "der erste Durchgang muss alles setzen"
    # Alles auf einmal: Indizes aus UND Ausgang auf Clearnet.
    assert "txindex=0" in nach_eins
    assert "onlynet=ipv4" in nach_eins
    # Und danach Ruhe -- ein Waechter, der ohne Anlass schreibt, wuerde den
    # Knoten alle zehn Minuten durchstarten.
    for _ in range(3):
        client.app.state.einmal_nachsehen()
    assert pfad.read_text() == nach_eins


# ── Veraltete Dienstkonfiguration heilt sich selbst ────────────────────────
#
# Der Anlass, 29.08.2026: das Betriebsprotokoll zeigte alle zehn Minuten
#
#     Versionsabfrage (bitcoind) nach 3 Versuchen aufgegeben:
#     URLError: <urlopen error [Errno 111] Connection refused>
#
# Nicht GitHub wies ab, sondern sein eigenes Tor. Der HTTPTunnelPort kam am
# 27.08. in die Vorlage; sein Knoten war laenger eingerichtet. Und die torrc
# wurde genau einmal geschrieben, im Assistenten -- ein neues Abbild konnte
# das also nie heilen. Das ist die eigentliche Fehlerklasse: die Vorlage liegt
# im Abbild, die geltende Datei im Volume, und beide liefen auseinander.


def test_die_tor_konfiguration_wird_erneuert_wenn_sie_veraltet_ist(client):
    _richte_ein(client)
    pfad = client.tmp / "config" / "tor.conf"
    pfad.write_text("SocksPort 0.0.0.0:9050\n")     # Stand vor dem 27.08.

    client.app.state.einmal_nachsehen()

    text = pfad.read_text()
    assert "HTTPTunnelPort" in text, \
        "ohne den laeuft die Versionsabfrage gegen einen toten Port"
    assert (client.tmp / "config" / "tor.ready").exists(), \
        "ohne Freigabe faehrt Tor nach dem Neustart nicht wieder hoch"


def test_eine_aktuelle_tor_konfiguration_wird_nicht_angefasst(client):
    """Jedes Schreiben startet Tor neu -- und mit ihm die Onion-Adresse. Ein
    Waechter, der ohne Anlass schreibt, tut das alle zehn Minuten."""
    _richte_ein(client)
    pfad = client.tmp / "config" / "tor.conf"
    vorher = pfad.stat().st_mtime_ns

    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()

    assert pfad.stat().st_mtime_ns == vorher


def test_bei_abgeschaltetem_tor_wird_nichts_geschrieben(client):
    """Wer Tor aus hat, bekommt es nicht durch die Hintertuer zurueck."""
    _richte_ein(client, tor_aktiv=False)
    assert not client.app.state.vorlagen_nachziehen()
    assert not (client.tmp / "config" / "tor.ready").exists()


def test_der_erneuerte_takt_regelt_bitcoind_nicht_gleichzeitig_um(client, monkeypatch):
    """Tor neu starten UND bitcoind neu starten im selben Durchgang waere
    zweimal Stillstand auf einmal -- und die Versionsabfrage danach haette
    ohnehin keine Aussicht, weil Tor gerade hochfaehrt."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    (client.tmp / "config" / "tor.conf").write_text("SocksPort 0.0.0.0:9050\n")
    bitcoind = client.tmp / "config" / "bitcoind.conf"
    vorher = bitcoind.read_text()

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 705_633, "kopfzeilen": 964_000,
        "fortschritt": 0.48, "im_erstsync": True, "belegt_bytes": 1,
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_634_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})

    client.app.state.einmal_nachsehen()
    assert bitcoind.read_text() == vorher


# ── Vier Wege ins Netz, unabhaengig voneinander ────────────────────────────
#
# Des Betreibers Anforderung vom 29.08.2026, woertlich: "es muss 4 wege geben zum
# verbinden ... keiner dieser regler solte sich geseitig ausschliessen oder
# behindern sollen koennen". Tor, IPv4, IPv6 und die eigene Adresse sind
# deshalb vier Schalter, nicht ein Auswahlfeld: Tor und Clearnet sind kein
# Entweder-oder, und gerade Knoten, die beide Welten sprechen, sind knapp.


def _wege(client, **abweichungen):
    wahl = {"tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
            "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True}
    wahl.update(abweichungen)
    return client.post("/api/knoten/netzwege", json=wahl)


def test_tor_und_clearnet_schliessen_einander_nicht_aus(client):
    _richte_ein(client)
    r = _wege(client, tor=True, ipv4=True, ipv6=True,
              externe_adresse="203.0.113.7")
    assert r.status_code == 200

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert nodeconfig.lies_tor(conf)
    assert "externalip=203.0.113.7" in conf
    # Alle drei erlaubt heisst: KEIN onlynet. Das ist Cores Standard und
    # schliesst kuenftige Netze mit ein.
    assert "onlynet=" not in conf


def test_jeder_schalter_wirkt_fuer_sich(client):
    _richte_ein(client)
    _wege(client, ipv6=False)
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=ipv4" in conf and "onlynet=onion" in conf
    assert "onlynet=ipv6" not in conf
    assert nodeconfig.lies_tor(conf), "IPv6 aus darf Tor nicht mitnehmen"


def test_tor_laesst_sich_nachtraeglich_abschalten_und_wieder_an(client):
    """Frueher steckte der Tor-Abschnitt nur in der Vorlage: einmal beim
    Einrichten gesetzt und danach nicht mehr zu bewegen."""
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"

    _wege(client, tor=False)
    conf = pfad.read_text()
    assert not nodeconfig.lies_tor(conf) and "onion=tor:9050" not in conf
    assert not (client.tmp / "config" / "tor.ready").exists()
    assert "rpcauth=" in conf

    _wege(client, tor=True)
    conf = pfad.read_text()
    assert nodeconfig.lies_tor(conf) and "bind=0.0.0.0:8334=onion" in conf
    assert (client.tmp / "config" / "tor.ready").exists()


def test_alle_netze_aus_wird_abgelehnt(client):
    """Keine Grenze zwischen den Schaltern, sondern eine des Ganzen: ohne ein
    einziges Netz haette der Knoten keinen Weg mehr hinaus."""
    _richte_ein(client)
    r = _wege(client, tor=False, ipv4=False, ipv6=False)
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "kein_weg_ins_netz"
    # Und die Konfiguration bleibt, wie sie war.
    assert nodeconfig.lies_tor((client.tmp / "config" / "bitcoind.conf").read_text())


def test_eine_ipv6_adresse_wird_nicht_angekuendigt_wenn_ipv6_aus_ist(client):
    """Sonst wirbt der Knoten mit einer Einladung, die niemand annehmen kann."""
    _richte_ein(client)
    _wege(client, ipv6=False, externe_adresse="2001:db8::1")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=2001:db8::1" not in conf


def test_alles_in_einem_schreibvorgang(client):
    """Jede Aenderung startet bitcoind neu. Vier Schalter duerfen nicht vier
    Neustarts bedeuten."""
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    stand = pfad.stat().st_mtime_ns
    _wege(client, tor=False, ipv6=False, externe_adresse="203.0.113.9")
    assert pfad.stat().st_mtime_ns != stand
    conf = pfad.read_text()
    assert not nodeconfig.lies_tor(conf)
    assert "onlynet=ipv4" in conf and "onlynet=ipv6" not in conf
    assert "externalip=203.0.113.9" in conf


def test_die_schalter_ueberleben_einen_waechterlauf(client, monkeypatch):
    """Der Waechter regelt die Betriebsphase -- er darf dabei keinen Schalter
    umlegen, den der Nutzer gesetzt hat."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    _wege(client, tor=False, ipv6=False)
    pfad = client.tmp / "config" / "bitcoind.conf"

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()

    conf = pfad.read_text()
    assert not nodeconfig.lies_tor(conf), "der Waechter hat Tor wieder eingeschaltet"
    assert "onlynet=ipv6" not in conf
    assert "onlynet=ipv4" in conf


def test_die_abgleichspause_pendelt_nicht(client, monkeypatch):
    """Die Falle: die Pause nimmt Tor den Ausgang, daraufhin faellt die Zahl
    der Tor-Gegenstellen auf null, daraufhin greift die Bedingung "nur
    pausieren, wenn es Tor-Gegenstellen gibt" nicht mehr -- und zehn Minuten
    spaeter geht es von vorn los. Mit einem bitcoind-Neustart je Runde."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    assert "onlynet=ipv4" in pfad.read_text()

    # Genau das, was danach passiert: keine Tor-Gegenstellen mehr.
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(netze={"ipv4": 9}))
    stand = pfad.stat().st_mtime_ns
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()
    assert pfad.stat().st_mtime_ns == stand, "die Pause hat sich selbst aufgehoben"


def test_nach_dem_abgleich_gilt_wieder_der_schalter(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    assert "onlynet=onion" not in pfad.read_text()

    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(im_erstsync=False, fortschritt=1.0))
    client.app.state.einmal_nachsehen()
    assert "onlynet=" not in pfad.read_text()


def test_wer_die_pause_nicht_will_bekommt_sie_nicht(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    _wege(client, tor_pause_beim_abgleich=False)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    assert "onlynet=" not in pfad.read_text()


def test_die_auskunft_nennt_die_pause_beim_namen(client, monkeypatch):
    """Ein Schalter auf "an", waehrend der Knoten ueber Tor niemanden anruft,
    waere eine Anzeige, die etwas anderes behauptet als die Wirklichkeit."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    pfad = client.tmp / "config" / "bitcoind.conf"
    pfad.write_text(nodeconfig.setze_indizes(pfad.read_text(), False))
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    d = client.get("/api/knoten/netzwege").json()
    assert d["tor"] is True, "der Schalter bleibt, was er ist"
    assert d["tor_pausiert"] is True
    assert "onion" not in d["ruft_an"]


def test_ein_alter_knoten_verliert_kein_netz(client):
    """Wer vor 0.16.0 eingerichtet hat, hat nur "tor_aktiv" gespeichert. Ein
    Update darf ihm nicht stillschweigend IPv4 oder IPv6 abschalten."""
    from satcortex import state
    _richte_ein(client)
    zustand = state.Ablage(str(client.tmp / "config"))
    zustand.merke_knotenwahl({"speichergrenze_mb": 2500,
                              "upload_gb_pro_monat": 300,
                              "verbindungen": 80, "tor_aktiv": True})

    d = client.get("/api/knoten/netzwege").json()
    assert d["ipv4"] is True and d["ipv6"] is True and d["tor"] is True


# ── Erreichbarkeit von aussen ──────────────────────────────────────────────
#
# Der Anlass, 31.08.2026: der Knoten im Betrieb hatte seit Tag eins null eingehende
# Verbindungen. Der Grund lag nicht in der Software -- Port 8333 war im Router
# nicht freigegeben, von aussen kam "Connection refused nach 0,0 Sekunden".
# Das haette die App selbst sagen koennen, statt dass jemand es fuer ihn misst.


def test_ohne_angekuendigte_adresse_gibt_es_nichts_zu_pruefen(client):
    """Und das ist selbst der Befund: so findet einen niemand."""
    _richte_ein(client)
    d = client.post("/api/knoten/erreichbarkeit").json()
    assert d["geprueft"] is False and d["erreichbar"] is False
    assert d["grund"] == "keine_adresse"


def test_ohne_tor_wird_die_erreichbarkeit_nicht_behauptet(client):
    """Von innen liesse sich das nicht ehrlich messen -- bei IPv6 gaebe es
    ueberhaupt kein NAT, die Verbindung ginge direkt und gelaenge auch bei
    geschlossener Firewall. Lieber nichts sagen als etwas Falsches."""
    _richte_ein(client, externe_adresse="203.0.113.7")
    _wege(client, tor=False, externe_adresse="203.0.113.7")
    d = client.post("/api/knoten/erreichbarkeit").json()
    assert d["geprueft"] is False
    assert d["erreichbar"] is None, "'nicht gemessen' ist nicht 'nicht erreichbar'"
    assert d["grund"] == "tor_aus"


def test_geprueft_wird_nur_was_auch_angekuendigt_ist(client, monkeypatch):
    """Eine IPv6-Adresse zu pruefen, waehrend IPv6 aus ist, hiesse einen Weg
    zu messen, den der Knoten gar nicht anbietet."""
    from satcortex import erreichbar as modul
    _richte_ein(client)
    _wege(client, ipv6=False, externe_adresse="203.0.113.7, 2001:db8::1")

    gesehen = {}
    monkeypatch.setattr(modul, "pruefe", lambda a, p, proxy, **kw: (
        gesehen.update(adressen=list(a), port=p),
        {"port": p, "adressen": [], "erreichbar": False, "geprueft": True})[1])

    client.post("/api/knoten/erreichbarkeit")
    assert gesehen["adressen"] == ["203.0.113.7"]
    assert gesehen["port"] == 8333


def test_vor_der_einrichtung_wird_nicht_gemessen(client):
    d = client.post("/api/knoten/erreichbarkeit").json()
    assert d["eingerichtet"] is False


# ── Lightning: die Wallet anlegen ──────────────────────────────────────────
#
# Der heikelste Ablauf im Projekt. Die Vorgabe des Betreibers steht ueber allem und ist
# aelter als dieses Repo: "eine wallet seed gehoert immer auf ein blatt papier
# nie auf platte irgendwo". Die Tests hier pruefen deshalb nicht nur, dass es
# funktioniert, sondern vor allem, was NICHT passiert.

WOERTER = [f"wort{n:02d}" for n in range(1, 25)]


class FakeLnd:
    """LND, so weit es fuer diesen Ablauf noetig ist."""

    def __init__(self, stand="NON_EXISTING", macaroons=None):
        self.stand = stand
        self.angelegt = None
        self.entsperrt = None
        self.entsperrfehler = False
        self.verbunden = None
        # Welcher Wachturm zuletzt ausgetragen wurde -- und ob LND ablehnt.
        self.ausgetragen = None
        self.austragfehler = ""
        # Was zuletzt gesendet wurde -- und ob es ueberhaupt angenommen wird.
        self.gesendet = None
        self.geschaetzt = None
        # Was GetTransactions liefert -- roh, wie LND es schickt.
        self.bewegungen_roh = []
        # Und was ListInvoices liefert, plus die zuletzt bestellte Rechnung.
        self.rechnungen_roh = []
        self.rechnung_bestellt = None
        # Eine EINZELNE Rechnung: was LookupInvoiceV2 herausgibt, was der
        # Strom nacheinander meldet, und was zuletzt storniert wurde.
        self.rechnung_einzeln = None
        self.rechnung_strom = []
        self.storniert = None
        self.abgewartet = ""
        self.sendefehler = ""
        # Pfade, auf denen LND nicht rechtzeitig antwortet. Kein Fehlschlag:
        # der Auftrag kann laengst ausgefuehrt sein, nur die Antwort blieb
        # aus. Genau darum geht es in den Tests unten.
        self.beschaeftigt_auf = set()
        # Was auf welchem Pfad ankam -- fuer Pruefungen, bei denen der
        # genaue Feldname entscheidet.
        self.gesendet_an = {}
        # Erst noetig, seit es Endpunkte gibt, die das eigene Macaroon
        # brauchen -- vorher kam die Attrappe nie so weit.
        self.macaroons = macaroons or Path("/nicht/vorhanden")
        self.zertifikat = type("P", (), {"exists": staticmethod(lambda: True)})()

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        """Nur SubscribeSingleInvoice -- mehr braucht diese Attrappe nicht.

        Ohne Meldungen verhaelt sie sich wie LND bei einer Rechnung, an der
        sich nichts tut: die Frist laeuft ab.
        """
        if not pfad.startswith("/v2/invoices/subscribe/"):
            raise AssertionError(f"unerwarteter Strom: {pfad}")
        self.abgewartet = pfad
        if not self.rechnung_strom:
            from satcortex import lnd as lnd_modul
            raise lnd_modul.Beschaeftigt("keine Meldung innerhalb der Frist")
        for r in self.rechnung_strom:
            yield {"result": r}

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None,
            methode=None):
        if daten is not None:
            self.gesendet_an[pfad.split("?")[0]] = daten
        # Auch ohne den Abfrageteil vergleichen: gemeint ist die ROUTE, und
        # seit /v2/invoices/lookup?payment_hash=... gibt es welche, die einen
        # tragen. Vorher fiel so eine still durch und der Test prueffte
        # einen ganz anderen Fehlerweg.
        if pfad in self.beschaeftigt_auf \
           or pfad.split("?")[0] in self.beschaeftigt_auf:
            from satcortex import lnd as lnd_modul
            raise lnd_modul.Beschaeftigt("kein Wort innerhalb des Zeitlimits")
        if pfad == "/v1/state":
            return {"state": self.stand}
        if methode == "DELETE" and pfad.startswith("/v2/watchtower/client/"):
            if self.austragfehler:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler(self.austragfehler)
            self.ausgetragen = pfad
            return {}
        if pfad == "/v1/genseed":
            return {"cipher_seed_mnemonic": list(WOERTER)}
        if pfad == "/v1/initwallet":
            self.angelegt = daten
            self.stand = "SERVER_ACTIVE"
            return {}
        if pfad == "/v1/macaroon":
            return {"macaroon": "0201036c6e64"}
        if pfad == "/v1/peers":
            self.verbunden = daten
            return {}
        if pfad.split("?")[0] == "/v2/invoices/lookup":
            if self.rechnung_einzeln is None:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler("404: invoice not found")
            return dict(self.rechnung_einzeln)
        if pfad == "/v2/invoices/cancel":
            self.storniert = daten
            if self.rechnung_einzeln is not None:
                self.rechnung_einzeln = {**self.rechnung_einzeln,
                                         "state": "CANCELED"}
            return {}
        if pfad.split("?")[0] == "/v1/invoices":
            # POST stellt aus, GET listet -- derselbe Pfad, zwei Vorgaenge.
            if daten is not None:
                import base64 as b64
                self.rechnung_bestellt = daten
                return {"payment_request": "lnbc1500n1pbeispiel",
                        "r_hash": b64.b64encode(bytes.fromhex("cd" * 32)).decode()}
            return {"invoices": list(self.rechnungen_roh)}
        if pfad.split("?")[0] == "/v1/transactions/fee":
            from satcortex import lnd as lnd_modul
            # Wie LNDs grpc-gateway: EstimateFee gibt es nur als GET. Die
            # Attrappe verglich bis zum 15.09.2026 nur den Pfad -- und liess
            # so ein POST durch, das am echten Knoten mit 501 scheiterte.
            if daten is not None or (methode or "GET") != "GET":
                raise lnd_modul.LndFehler("501: Method Not Allowed")
            if self.sendefehler:
                raise lnd_modul.LndFehler(self.sendefehler)
            self.geschaetzt = pfad
            return {"fee_sat": "1420", "sat_per_vbyte": "5"}
        if pfad == "/v1/transactions" and daten is None:
            # GetTransactions: ein GET auf denselben Pfad, der mit POST
            # sendet (lightning.yaml, v0.21.3-beta).
            return {"transactions": list(self.bewegungen_roh)}
        if pfad == "/v1/transactions":
            if self.sendefehler:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler(self.sendefehler)
            self.gesendet = daten
            return {"txid": "a" * 64}
        if pfad == "/v2/wallet/bumpfee":
            return {}
        if pfad == "/v2/router/mc":
            return {"pairs": [{
                "node_from": "aa" * 33, "node_to": "bb" * 33,
                "history": {"fail_time": "1758400000",
                            "fail_amt_sat": "50000",
                            "success_time": "1758399000",
                            "success_amt_sat": "20000"}}]}
        if pfad == "/v1/balance/blockchain":
            # Fuer die Uebersicht: unbestaetigt ist der Unterschied zwischen
            # beiden Zahlen -- genau daran haengt die Anzeige.
            return {"total_balance": "150000", "confirmed_balance": "100000"}
        if pfad == "/v1/balance/channels":
            return {"local_balance": {"sat": "0"}, "remote_balance": {"sat": "0"}}
        if pfad.startswith("/v2/wallet/reserve"):
            # Was On-Chain liegenbleiben muss, wenn ein Kanal dazukommt.
            # LND nennt die Zahl selbst -- wir schaetzen sie nicht.
            return {"required_reserve": "10000"}
        if pfad == "/v2/watchtower/server":
            # Unser EIGENER Turm. Die Kennung wird gebraucht, um ihn in der
            # Liste der eingetragenen Tuerme wiederzuerkennen -- er darf dort
            # nicht als Schutz zaehlen. Hier laeuft keiner.
            return {}
        if pfad == "/v1/unlockwallet":
            import base64
            if self.entsperrfehler:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler("invalid passphrase for master public key")
            self.entsperrt = base64.b64decode(daten["wallet_password"]).decode()
            self.stand = "RPC_ACTIVE"
            return {}
        # Seit dem 19.09.2026 schlaegt das Oeffnen eines Kanals die Adresse
        # im eigenen Graphen nach, wenn nur die Kennung angegeben wurde --
        # genau das war vorher die stille Kante.
        if pfad.startswith("/v1/graph/node/"):
            return {"node": {"addresses": [{"addr": "gegenstelle.onion:9735"}]}}
        raise AssertionError(f"unerwarteter Aufruf: {pfad}")


@pytest.fixture
def lnd_da(monkeypatch, tmp_path):
    from satcortex import api as api_modul
    ordner = tmp_path / "macaroons"
    ordner.mkdir(exist_ok=True)
    knoten = FakeLnd(macaroons=ordner)
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def _seed(client):
    return client.post("/api/lightning/seed").json()


WALLET_PASSWORT = "ein-langes-wallet-passwort"


def _antworten(d, woerter=None, **mehr):
    quelle = woerter or WOERTER
    leib = {"antworten": {str(n): quelle[n - 1] for n in d["stellen"]},
            "passwort": WALLET_PASSWORT}
    leib.update(mehr)
    return leib


def test_der_seed_kommt_mit_vierundzwanzig_woertern(client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    assert len(d["woerter"]) == 24
    assert len(d["stellen"]) == 4
    assert all(1 <= n <= 24 for n in d["stellen"])


def test_der_seed_landet_nirgends_auf_der_platte(client, lnd_da):
    """Der wichtigste Test in dieser Datei. Er sucht das erste Wort des Seeds
    in JEDER Datei, die die Anwendung anfasst -- Konfiguration, Zustand,
    Ablagen."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet", json=_antworten(d))

    gefunden = []
    for pfad in client.tmp.rglob("*"):
        if not pfad.is_file():
            continue
        try:
            inhalt = pfad.read_text(errors="ignore")
        except OSError:
            continue
        if any(w in inhalt for w in WOERTER):
            gefunden.append(str(pfad))
    assert not gefunden, f"Der Seed steht in: {gefunden}"


def test_ohne_gegenprobe_gibt_es_keine_wallet(client, lnd_da):
    """Eine Wallet, deren Seed niemand hat, ist keine Bequemlichkeit, sondern
    eine Falle mit Zeitzuender."""
    _richte_ein(client)
    d = _seed(client)
    falsch = {"antworten": {str(n): "falsch" for n in d["stellen"]}}
    r = client.post("/api/lightning/wallet", json=falsch)
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "gegenprobe_falsch"
    assert lnd_da.angelegt is None, "trotz falscher Gegenprobe angelegt"


def test_mit_gegenprobe_wird_die_wallet_angelegt(client, lnd_da):
    import base64
    _richte_ein(client)
    d = _seed(client)
    r = client.post("/api/lightning/wallet", json=_antworten(d))
    assert r.status_code == 200
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == WOERTER
    assert lnd_da.angelegt["stateless_init"] is False, \
        "ohne Macaroon-Dateien kaeme die Oberflaeche an ihren Knoten nicht heran"
    passwort = base64.b64decode(lnd_da.angelegt["wallet_password"]).decode()
    assert passwort == WALLET_PASSWORT, "es gilt das gewaehlte Passwort"


def test_grossschreibung_und_leerzeichen_sind_kein_grund_zu_scheitern(client, lnd_da):
    """Abgeschrieben wird von Hand. Wer "Wort07 " tippt, hat den Seed."""
    _richte_ein(client)
    d = _seed(client)
    schlampig = _antworten(d, woerter=[w.upper() + " " for w in WOERTER])
    assert client.post("/api/lightning/wallet", json=schlampig).status_code == 200


def test_die_abgefragten_stellen_stehen_vorher_fest(client, lnd_da):
    """Wuerfelte man sie erst bei der Gegenprobe, koennte man so lange neu
    fragen lassen, bis eine Frage kommt, die man zufaellig beantworten kann."""
    _richte_ein(client)
    d = _seed(client)
    for _ in range(3):
        client.post("/api/lightning/wallet",
                    json={"antworten": {str(n): "falsch" for n in d["stellen"]}})
    # Die Stellen aus dem ersten Aufruf gelten weiter.
    assert client.post("/api/lightning/wallet",
                       json=_antworten(d)).status_code == 200


def test_nach_fuenf_fehlversuchen_faengt_es_von_vorn_an(client, lnd_da):
    """Wer ihn nach fuenf Anlaeufen nicht vorlesen kann, hat ihn nicht
    aufgeschrieben. Dann lieber ein neuer Seed als einer, der halb bekannt
    herumliegt."""
    _richte_ein(client)
    d = _seed(client)
    falsch = {"antworten": {str(n): "falsch" for n in d["stellen"]}}
    for _ in range(4):
        client.post("/api/lightning/wallet", json=falsch)
    letzte = client.post("/api/lightning/wallet", json=falsch)
    assert letzte.json()["detail"]["meldung"] == "gegenprobe_aufgegeben"
    # Und danach greift auch die richtige Antwort nicht mehr.
    r = client.post("/api/lightning/wallet", json=_antworten(d))
    assert r.json()["detail"]["meldung"] == "seed_abgelaufen"
    assert lnd_da.angelegt is None


def test_ein_alter_seed_wird_nicht_mehr_angenommen(client, lnd_da, monkeypatch):
    from satcortex import api as api_modul
    _richte_ein(client)
    d = _seed(client)
    monkeypatch.setattr(api_modul, "SEED_FRIST_SEKUNDEN", -1)
    r = client.post("/api/lightning/wallet", json=_antworten(d))
    assert r.json()["detail"]["meldung"] == "seed_abgelaufen"
    assert lnd_da.angelegt is None


def test_der_seed_ist_nach_der_anlage_vergessen(client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet", json=_antworten(d))
    r = client.post("/api/lightning/wallet", json=_antworten(d))
    assert r.json()["detail"]["meldung"] == "seed_abgelaufen"


def test_zu_einer_bestehenden_wallet_gibt_es_keinen_zweiten_seed(client, lnd_da):
    """Die gefaehrlichste Verwechslung, die diese Oberflaeche anbieten
    koennte."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/seed")
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "wallet_gibt_es_schon"


def test_die_entsperrdatei_kommt_erst_nach_der_wallet(client, lnd_da):
    """LND bricht sonst den Start ab: "wallet unlock password file was
    specified but wallet does not exist" (config_builder.go, v0.21.2-beta)."""
    from satcortex import nodeconfig, lnd as lnd_modul
    _richte_ein(client)
    ablage = client.tmp / "config"
    (ablage / "lnd.conf").write_text(
        nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen()))

    ziel = lnd_modul.passwortdatei(str(client.tmp / "fast"))
    assert not ziel.exists()
    d = _seed(client)
    assert not ziel.exists(), "die Datei war schon da, bevor es eine Wallet gab"

    client.post("/api/lightning/wallet",
                json=_antworten(d, automatisch_entsperren=True))
    assert ziel.exists() and oct(ziel.stat().st_mode)[-3:] == "600"
    conf = (ablage / "lnd.conf").read_text()
    assert nodeconfig.lies_entsperrdatei(conf) == str(ziel)


def test_die_passwortdatei_ist_nur_fuer_den_besitzer_lesbar(tmp_path):
    """Und ohne abschliessenden Zeilenumbruch: LND schneidet ihn zwar ab, aber
    sich darauf zu verlassen hiesse, sich auf fremden Code zu verlassen, der
    das nie versprochen hat."""
    from satcortex import storage
    ziel = tmp_path / "unter" / "wallet.pass"
    storage.schreibe_geheimnis(str(ziel), "geheim-genug-fuer-lnd")
    assert oct(ziel.stat().st_mode)[-3:] == "600"
    assert ziel.read_bytes() == b"geheim-genug-fuer-lnd"
    assert not list(tmp_path.rglob("*.neu")), "Zwischendatei liegen geblieben"


# ── Entsperren: der Nutzer entscheidet, nicht die Anwendung ────────────────
#
# Der Einwand aus dem Betrieb vom 31.08.2026 zur automatischen Entsperrung: "das ist ein
# sicherheits risiko". Seine Begruendung -- wer die NAS uebernimmt, kann die
# Wallet leerraeumen -- trifft den Fall nicht ganz: dafuer braucht es kein
# Passwort, sondern das admin.macaroon, und das liegt bei laufendem Knoten
# ohnehin auf derselben Platte. Fuer den Fall, der wirklich zaehlt, hat er
# aber recht: gestohlene Platte, kopiertes Backup. Dort ist ein Passwort, das
# danebenliegt, kein Passwort. Also entscheidet er, und die Vorgabe ist seine.


def test_ohne_ausdrueckliche_wahl_wird_nichts_auf_die_platte_gelegt(client, lnd_da):
    from satcortex import lnd as lnd_modul
    _richte_ein(client)
    d = _seed(client)
    r = client.post("/api/lightning/wallet", json=_antworten(d))
    assert r.status_code == 200
    assert r.json()["automatisch_entsperren"] is False
    assert not lnd_modul.passwortdatei(str(client.tmp / "fast")).exists()


def test_das_gewaehlte_passwort_landet_nirgends(client, lnd_da):
    """Wer den sicheren Weg waehlt, soll ihn auch bekommen -- und nicht eine
    Anwendung, die das Passwort heimlich behaelt, weil es bequemer ist."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet", json=_antworten(d))

    gefunden = [str(p) for p in client.tmp.rglob("*")
                if p.is_file() and WALLET_PASSWORT in p.read_text(errors="ignore")]
    assert not gefunden, f"Das Wallet-Passwort steht in: {gefunden}"


def test_ein_zu_kurzes_passwort_bekommt_keine_wallet(client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    r = client.post("/api/lightning/wallet", json=_antworten(d, passwort="kurz"))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "passwort_zu_kurz"
    assert lnd_da.angelegt is None


def test_bei_manueller_entsperrung_bleibt_die_lnd_conf_unberuehrt(client, lnd_da):
    from satcortex import nodeconfig
    _richte_ein(client)
    ablage = client.tmp / "config"
    (ablage / "lnd.conf").write_text(
        nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen()))
    d = _seed(client)
    client.post("/api/lightning/wallet", json=_antworten(d))
    conf = (ablage / "lnd.conf").read_text()
    assert nodeconfig.lies_entsperrdatei(conf) == ""


def test_eine_gesperrte_wallet_laesst_sich_entsperren(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    r = client.post("/api/lightning/entsperren",
                    json={"passwort": WALLET_PASSWORT})
    assert r.status_code == 200
    assert lnd_da.entsperrt == WALLET_PASSWORT


def test_ein_falsches_passwort_wird_als_solches_gemeldet(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    lnd_da.entsperrfehler = True
    r = client.post("/api/lightning/entsperren", json={"passwort": "danebengetippt"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "passwort_falsch"


def test_das_entsperrpasswort_wird_nicht_gemerkt(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    client.post("/api/lightning/entsperren", json={"passwort": WALLET_PASSWORT})
    gefunden = [str(p) for p in client.tmp.rglob("*")
                if p.is_file() and WALLET_PASSWORT in p.read_text(errors="ignore")]
    assert not gefunden, f"Das Passwort steht in: {gefunden}"


def test_die_mindestlaenge_kommt_vom_server(client):
    """Sie stand in zwei Uebersetzungen fest eingetippt. Zweimal getippt
    heisst irgendwann zweimal verschieden."""
    from satcortex import auth
    d = client.get("/api/zustand").json()
    assert d["passwort_mindestlaenge"] == auth.MIN_PASSWORTLAENGE


# ── Kanalsicherung ─────────────────────────────────────────────────────────
#
# Die vierundzwanzig Woerter auf Papier stellen die On-Chain-Wallet wieder
# her. Die Guthaben IN den Kanaelen NICHT. Dafuer braucht es diese Datei -- und
# sie muss ausser Haus, sonst sichert sie gegen genau die Sache nicht, gegen
# die man sich sichert.

import base64 as _b64

SICHERUNG = _b64.b64encode(b"so-sieht-eine-kanalsicherung-aus").decode()


class LndMitKanaelen(FakeLnd):
    def __init__(self, kanaele=3, heil=True, blob=SICHERUNG, abgedeckt=None):
        super().__init__(stand="SERVER_ACTIVE")
        self.kanaele = kanaele
        self.heil = heil
        self.blob = blob
        # Was die vorgelegte Sicherung abdeckt. None heisst: so viele, wie
        # offen sind. Eine kleinere Zahl ist der Fall, der wirklich weh tut --
        # eine heile Sicherung, die zu alt ist.
        self.abgedeckt = abgedeckt
        self.geprueft = None

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if pfad == "/v1/channels/backup":
            return {"multi_chan_backup": {
                "multi_chan_backup": self.blob,
                "chan_points": [{"x": n} for n in range(self.kanaele)]}}
        if pfad == "/v1/channels/backup/verify":
            self.geprueft = daten
            if not self.heil:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler("unable to unpack chan backup")
            wieviele = self.kanaele if self.abgedeckt is None else self.abgedeckt
            return {"chan_points": [f"abc{n}:0" for n in range(wieviele)]}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_kanaele(monkeypatch):
    from satcortex import api as api_modul
    knoten = LndMitKanaelen()
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_die_wachturmansicht_sagt_ob_wirklich_bewacht_wird(client, lnd_kanaele,
                                                         monkeypatch):
    """Eingetragen ist nicht bewacht. Bis zum 14.09.2026 stand hier gruen
    "eingetragen", sobald ein Turm in der Liste war."""
    from satcortex import api as api_modul
    _richte_ein(client)
    lnd_modul = api_modul.lnd
    monkeypatch.setattr(lnd_modul, "zustand", lambda k: {"stand": "bereit"})
    monkeypatch.setattr(lnd_modul, "kanaele",
                        lambda k: [{"sitzungsart": "ANCHOR"}])
    monkeypatch.setattr(lnd_modul, "eigener_turm",
                        lambda k: {"aktiv": False, "uris": [], "lauscht": []})
    monkeypatch.setattr(lnd_modul, "wachturm_zaehler", lambda k: {
        "bestaetigt": 3, "ausstehend": 0, "abgewiesen": 0, "sitzungen_neu": 1})
    eingetragen = [{"kennung": KENNUNG_TURM, "adressen": ["t.onion:9911"],
                    "arten": {}, "sitzungen": 0}]
    monkeypatch.setattr(lnd_modul, "wachtuerme",
                        lambda k, eigen="": eingetragen)

    d = client.get("/api/lightning/wachtuerme").json()
    assert d["ungedeckt"] == ["ANCHOR"], "eingetragen galt als bewacht"
    assert d["kanaele"] == 1

    eingetragen[0]["arten"] = {"ANCHOR": {"sitzungen": 1, "nutzbar": 1,
                                          "bestaetigt": 3, "ausstehend": 0}}
    d = client.get("/api/lightning/wachtuerme").json()
    assert d["ungedeckt"] == []
    assert d["zaehler"]["bestaetigt"] == 3


def test_ohne_zaehler_bleibt_das_urteil(client, lnd_kanaele, monkeypatch):
    """Die Zahl ist Beiwerk. Ob bewacht wird, sagen die Sitzungen."""
    from satcortex import api as api_modul
    _richte_ein(client)
    lnd_modul = api_modul.lnd
    monkeypatch.setattr(lnd_modul, "zustand", lambda k: {"stand": "bereit"})
    monkeypatch.setattr(lnd_modul, "kanaele", lambda k: [])
    monkeypatch.setattr(lnd_modul, "eigener_turm",
                        lambda k: {"aktiv": False, "uris": [], "lauscht": []})
    monkeypatch.setattr(lnd_modul, "wachtuerme", lambda k, eigen="": [
        {"kennung": KENNUNG_TURM, "adressen": [], "sitzungen": 1,
         "arten": {"ANCHOR": {"sitzungen": 1, "nutzbar": 1, "bestaetigt": 0,
                              "ausstehend": 0}}}])

    def platzt(k):
        raise lnd_modul.LndFehler("stats gibt es nicht")
    monkeypatch.setattr(lnd_modul, "wachturm_zaehler", platzt)

    d = client.get("/api/lightning/wachtuerme").json()
    assert d["zaehler"] is None
    assert d["ungedeckt"] == [] and d["kanaele"] == 0


KENNUNG_TURM = "02" + "cd" * 32


def test_die_sicherung_laesst_sich_herunterladen(client, lnd_kanaele):
    _richte_ein(client)
    r = client.get("/api/lightning/sicherung/datei")
    assert r.status_code == 200
    assert r.content == b"so-sieht-eine-kanalsicherung-aus"
    assert "channel.backup" in r.headers["content-disposition"]


def test_eine_unbrauchbare_sicherung_wird_nicht_ausgeliefert(client, lnd_kanaele):
    """Lieber gar keine Datei als eine, auf die sich jemand verlaesst."""
    _richte_ein(client)
    lnd_kanaele.heil = False
    r = client.get("/api/lightning/sicherung/datei")
    assert r.status_code == 500
    assert r.json()["detail"]["meldung"] == "sicherung_unbrauchbar"


def test_ohne_kanaele_gibt_es_nichts_zu_sichern(client, lnd_kanaele):
    _richte_ein(client)
    lnd_kanaele.kanaele = 0
    lnd_kanaele.blob = ""
    r = client.get("/api/lightning/sicherung/datei")
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "keine_kanaele"

    d = client.get("/api/lightning/sicherung").json()
    assert d["kanaele"] == 0
    assert d["aktuell"] is True, "nichts zu sichern ist kein Rueckstand"


def test_ein_ziel_gilt_erst_wenn_wirklich_etwas_angekommen_ist(client, lnd_kanaele,
                                                               monkeypatch):
    """Zugangsdaten zu merken, die noch nie funktioniert haben, waere eine
    Sicherung auf dem Papier."""
    from satcortex import sicherung as modul
    _richte_ein(client)

    def platzt(*a, **kw):
        raise modul.ZielFehler("401: Unauthorized")
    monkeypatch.setattr(modul, "lade_hoch", platzt)

    r = client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "app-passwort"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "ziel_nimmt_nichts_an"
    assert not (client.tmp / "config" / "sicherung.pass").exists()
    assert client.get("/api/lightning/sicherung").json()["ziel"]["url"] == ""


def test_ein_bekannter_zielfehler_sagt_was_zu_tun_ist(client, lnd_kanaele,
                                                      monkeypatch):
    """Die nackte Zahl half niemandem. Der Satz kommt als Meldung, der
    Wortlaut des Servers geht als Einzelheit trotzdem mit."""
    from satcortex import sicherung as modul
    _richte_ein(client)

    def platzt(*a, **kw):
        raise modul.ZielFehler("404: Not Found", "ziel_adresse_unbekannt")
    monkeypatch.setattr(modul, "lade_hoch", platzt)

    r = client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "app-passwort"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "ziel_adresse_unbekannt"
    assert r.json()["detail"]["einzelheit"] == "404: Not Found"


def test_ein_taugliches_ziel_wird_gemerkt_das_passwort_aber_nicht_im_klartext(
        client, lnd_kanaele, monkeypatch):
    from satcortex import sicherung as modul
    _richte_ein(client)
    hochgeladen = []
    monkeypatch.setattr(modul, "lade_hoch",
                        lambda blob, url, b, p, **kw: hochgeladen.append((url, b, p)))

    r = client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "ein-app-passwort"})
    assert r.status_code == 200
    assert hochgeladen, "es wurde nichts hochgeladen, aber das Ziel gilt"

    d = client.get("/api/lightning/sicherung").json()
    assert d["ziel"] == {"url": "https://cloud.example/dav", "benutzer": "testnutzer"}
    assert d["aktuell"] is True

    # Das Passwort gehoert in eine Datei mit engen Rechten, nicht in den
    # Zustand -- der ist fuer die Gruppe lesbar, weil die Dienste ihn brauchen.
    zustandsdatei = client.tmp / "config" / "einrichtung.json"
    if zustandsdatei.exists():
        assert "ein-app-passwort" not in zustandsdatei.read_text()
    pfad = client.tmp / "config" / "sicherung.pass"
    assert pfad.exists() and oct(pfad.stat().st_mode)[-3:] == "600"


def test_der_waechter_sichert_nur_bei_aenderung(client, lnd_kanaele, monkeypatch):
    """Jeder Durchlauf eine Datei hochzuschieben, die sich nicht geaendert
    hat, ist Last beim Nutzer und beim Ziel -- und verdeckt im Protokoll die
    Laeufe, die wirklich etwas getan haben."""
    from satcortex import sicherung as modul
    _richte_ein(client)
    hoch = []
    monkeypatch.setattr(modul, "lade_hoch",
                        lambda blob, url, b, p, **kw: hoch.append(blob))
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "s", "passwort": "p"})
    assert len(hoch) == 1

    client.app.state.sicherung_nachziehen()
    client.app.state.sicherung_nachziehen()
    assert len(hoch) == 1, "ohne Aenderung wurde erneut hochgeladen"

    lnd_kanaele.blob = _b64.b64encode(b"ein-vierter-kanal-kam-dazu").decode()
    lnd_kanaele.kanaele = 4
    client.app.state.sicherung_nachziehen()
    assert len(hoch) == 2
    assert client.get("/api/lightning/sicherung").json()["stand"]["kanaele"] == 4


def test_ein_rueckstand_bleibt_sichtbar_wenn_das_ziel_streikt(client, lnd_kanaele,
                                                              monkeypatch):
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "s", "passwort": "p"})

    def platzt(*a, **kw):
        raise modul.ZielFehler("Verbindung abgelehnt")
    monkeypatch.setattr(modul, "lade_hoch", platzt)
    lnd_kanaele.blob = _b64.b64encode(b"ein-vierter-kanal-kam-dazu").decode()
    lnd_kanaele.kanaele = 4
    client.app.state.sicherung_nachziehen()

    d = client.get("/api/lightning/sicherung").json()
    assert d["aktuell"] is False, "der Rueckstand wurde still abgehakt"
    assert d["stand"]["fehler"]


def test_im_hintergrund_landet_der_schluessel_in_der_ablage(client, lnd_kanaele,
                                                            monkeypatch):
    """Daraus macht die Oberflaeche den Satz. Stuende dort "401:
    Unauthorized", laese man im Kasten wieder nur die Zahl."""
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "s", "passwort": "p"})

    def platzt(*a, **kw):
        raise modul.ZielFehler("401: Unauthorized", "ziel_anmeldung_abgelehnt")
    monkeypatch.setattr(modul, "lade_hoch", platzt)
    lnd_kanaele.blob = _b64.b64encode(b"ein-vierter-kanal-kam-dazu").decode()
    lnd_kanaele.kanaele = 4
    client.app.state.sicherung_nachziehen()

    d = client.get("/api/lightning/sicherung").json()
    assert d["stand"]["fehler"] == "ziel_anmeldung_abgelehnt"


def test_ohne_ziel_laeuft_der_waechter_ins_leere_ohne_zu_klagen(client, lnd_kanaele):
    _richte_ein(client)
    client.app.state.sicherung_nachziehen()
    assert client.get("/api/lightning/sicherung").json()["stand"] == {}


# ── Die Lightning-Ansicht ──────────────────────────────────────────────────

class LndVollstaendig(FakeLnd):
    def __init__(self):
        super().__init__(stand="SERVER_ACTIVE")
        self.faellt_aus = set()
        self.gefragt = []
        self.geoeffnet = None
        self.gezahlt = None

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        """LNDs Zahl-Endpunkt antwortet als Strom -- mehrfach.

        Das Abwarten einer Rechnung ist ebenfalls ein Strom, aber ein GET
        ohne Rumpf; das geht an die Fassung der Elternklasse.
        """
        if pfad.startswith("/v2/invoices/subscribe/"):
            yield from FakeLnd.strom(self, pfad, daten, macaroon, zeitlimit,
                                     methode)
            return
        self.gezahlt = daten
        yield {"result": {"status": "IN_FLIGHT"}}
        yield {"result": {"status": "SUCCEEDED", "value_sat": "1500",
                          "fee_sat": "2", "payment_preimage": "beleg",
                          "payment_hash": "aa"}}

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.gefragt.append(pfad)
        nackt = pfad.split("?")[0]
        if nackt in self.faellt_aus:
            from satcortex import lnd as lnd_modul
            raise lnd_modul.LndFehler("500: irgendwas")
        if nackt == "/v1/getinfo":
            return {"identity_pubkey": "03ab", "alias": "Testknoten",
                    "color": "#f7931a", "num_active_channels": 2,
                    "num_peers": 5, "synced_to_chain": True,
                    "uris": ["03ab@203.0.113.7:9735"]}
        if nackt == "/v1/balance/blockchain":
            return {"total_balance": "150000", "confirmed_balance": "150000"}
        if nackt == "/v1/balance/channels":
            return {"local_balance": {"sat": "42000"},
                    "remote_balance": {"sat": "58000"}}
        if nackt == "/v1/channels":
            # GET listet, POST oeffnet -- derselbe Pfad, zwei Vorgaenge.
            if daten is not None:
                import base64 as b64
                self.geoeffnet = daten
                roh = bytes.fromhex("ab" * 32)[::-1]
                return {"funding_txid_bytes": b64.b64encode(roh).decode(),
                        "output_index": 0}
            return {"channels": [{"active": True, "peer_alias": "ACINQ",
                                  "capacity": "5000000",
                                  "local_balance": "2000000",
                                  "remote_balance": "3000000"}]}
        if nackt.startswith("/v1/payreq/"):
            return {"destination": "03ff" + "aa" * 31, "num_satoshis": "1500",
                    "timestamp": "1000", "expiry": "9999999999",
                    "description": "Kaffee", "payment_hash": "aa"}
        if nackt == "/v1/graph/info":
            return {"num_nodes": 6100, "num_channels": 20500,
                    "total_network_capacity": "300000000000"}
        if nackt == "/v1/switch":
            return {"forwarding_events": []}
        if nackt == "/v1/peers":
            return {"peers": [{"pub_key": "02" + "ee" * 32, "inbound": False,
                               "sync_type": "ACTIVE_SYNC"}]}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_voll(monkeypatch):
    from satcortex import api as api_modul
    knoten = LndVollstaendig()
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_die_kanalansicht_kommt_in_einer_antwort(client, lnd_voll):
    _richte_ein(client)
    d = client.get("/api/lightning/kanaele").json()
    assert d["stand"] == "bereit"
    assert d["knoten"]["alias"] == "Testknoten"
    assert d["guthaben"]["kanal_hier"] == 42000
    assert d["kanaele"][0]["gegenstelle"] == "ACINQ"
    assert d["netz"]["knoten"] == 6100
    assert d["weiterleitungen"]["anzahl"] == 0
    # Die Leitungen kommen mit -- und eine Leitung ist kein Kanal.
    assert d["verbindungen"] == [{"kennung": "02" + "ee" * 32, "name": "",
                                  "mit_kanal": False, "eingehend": False,
                                  "netzkarte": True}]


def test_ein_ausfall_nimmt_nicht_die_ganze_ansicht_mit(client, lnd_voll):
    """Eine Ansicht, die wegen der Weiterleitungsstatistik auch die
    Kanalliste verschweigt, waere schlechter als eine unvollstaendige."""
    _richte_ein(client)
    lnd_voll.faellt_aus = {"/v1/switch", "/v1/graph/info"}
    d = client.get("/api/lightning/kanaele").json()
    assert "weiterleitungen" not in d and "netz" not in d
    assert d["kanaele"][0]["kapazitaet"] == 5_000_000
    assert d["knoten"]["alias"] == "Testknoten"


def test_ohne_wallet_wird_gar_nicht_erst_gefragt(client, lnd_da):
    _richte_ein(client)
    d = client.get("/api/lightning/kanaele").json()
    assert d["stand"] == "keine_wallet"
    assert "kanaele" not in d


# ── Das eigene Macaroon und seine Rechte ───────────────────────────────────
#
# Am 31.08.2026 sollte die Weboberflaeche kein Geld bewegen koennen. Seit dem
# 10.09.2026 haelt das Macaroon onchain:write (Senden), seit dem 12.09.2026
# oeffnet, schliesst und zahlt die Anwendung auch -- alles hinter der PIN.
# LNDs Rechtetabelle trennt OpenChannel und SendCoins nicht; gegen eine
# uebernommene Sitzung steht deshalb die PIN, nicht das Macaroon.


class LndMitMacaroon(LndVollstaendig):
    def __init__(self):
        super().__init__()
        self.gebacken = None
        self.gebuehren = None
        self.benutzte_macaroons = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        nackt = pfad.split("?")[0]
        self.benutzte_macaroons.append((nackt, macaroon))
        if nackt == "/v1/macaroon":
            self.gebacken = daten
            return {"macaroon": "0201036c6e6402"}
        if nackt == "/v1/newaddress":
            return {"address": "bc1p" + "q" * 58}
        if nackt == "/v1/chanpolicy":
            self.gebuehren = daten
            return {}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_macaroon(monkeypatch, tmp_path):
    from satcortex import api as api_modul
    knoten = LndMitMacaroon()
    knoten.macaroons = tmp_path / "mac"
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_das_gebackene_macaroon_haelt_genau_die_liste(client, lnd_macaroon):
    """Bis zum 10.09.2026 hiess dieser Test "hat kein onchain:write", und die
    Begruendung stimmte: onchain:write erlaubt bei LND auch SendCoins, die
    Berechtigung laesst sich nicht trennen.

    Sie ist jetzt drin, und zwar aus die Bedingung des Betreibers vom 30.08.2026: "ich
    werde nix dahin ueberweisen solange ich es nicht zurueck schicken kann".
    Was den Ausschlag gab, ist die Rechnung dahinter:

      * Fuer jemanden mit der PLATTE aendert es nichts -- dort liegt ohnehin
        LNDs admin.macaroon, und das kann alles.
      * Fuer eine uebernommene SITZUNG aendert es alles -- und genau dagegen
        steht seit demselben Tag die PIN.

    Der Test bleibt trotzdem stehen, nur andersherum: er haelt die Liste
    fest, damit ein weiteres Recht nicht unbemerkt dazukommt."""
    _richte_ein(client)
    client.post("/api/lightning/einzahladresse")

    rechte = {(p["entity"], p["action"])
              for p in lnd_macaroon.gebacken["permissions"]}
    assert ("onchain", "write") in rechte      # senden, seit 10.09.2026
    assert ("address", "write") in rechte      # Einzahladressen
    assert ("offchain", "write") in rechte     # Lightning zahlen, Gebuehren
    assert ("onchain", "read") in rechte       # Guthaben anzeigen
    # Und ausdruecklich NICHT: wer selbst Macaroons backen darf, kann sich
    # jedes weitere Recht ausstellen -- das waere admin auf Umwegen.
    for verboten in ("macaroon", "signer", "walletrpc"):
        assert not any(e == verboten for e, _ in rechte), verboten


def test_admin_wird_nur_zum_backen_angefasst(client, lnd_macaroon):
    _richte_ein(client)
    client.post("/api/lightning/einzahladresse")
    client.post("/api/lightning/einzahladresse")

    mit_admin = [p for p, m in lnd_macaroon.benutzte_macaroons if m == "admin"]
    assert mit_admin == ["/v1/macaroon"], \
        f"admin wurde ausserhalb des Backens benutzt: {mit_admin}"


def test_ist_das_macaroon_da_wird_nicht_erneut_gebacken(client, lnd_macaroon):
    _richte_ein(client)
    client.post("/api/lightning/einzahladresse")
    lnd_macaroon.gebacken = None
    client.post("/api/lightning/einzahladresse")
    assert lnd_macaroon.gebacken is None


def test_die_einzahladresse_ist_jedes_mal_eine_neue_und_kommt_ohne_admin(
        client, lnd_macaroon):
    """Eine wiederbenutzte Adresse verknuepft Einzahlungen miteinander und
    macht sie fuer jeden nachvollziehbar, der die Kette liest."""
    _richte_ein(client)
    r = client.post("/api/lightning/einzahladresse")
    assert r.status_code == 200 and r.json()["adresse"].startswith("bc1p")
    fuer_adresse = [m for p, m in lnd_macaroon.benutzte_macaroons
                    if p == "/v1/newaddress"]
    assert fuer_adresse == ["satcortex"]


def test_gebuehren_gelten_ohne_kanalpunkt_fuer_alle(client, lnd_macaroon):
    _richte_ein(client)
    r = client.post("/api/lightning/gebuehren",
                    json={"basis_msat": 0, "satz_ppm": 120})
    assert r.status_code == 200 and r.json()["fuer_alle"] is True
    assert lnd_macaroon.gebuehren["global"] is True
    assert lnd_macaroon.gebuehren["fee_rate_ppm"] == 120
    assert lnd_macaroon.gebuehren["base_fee_msat"] == "0"


def test_gebuehren_lassen_sich_je_kanal_setzen(client, lnd_macaroon):
    """Der eigentliche Betriebsgriff: teuer machen, wo ein Kanal leerlaeuft."""
    _richte_ein(client)
    client.post("/api/lightning/gebuehren", json={
        "basis_msat": 1000, "satz_ppm": 800, "kanalpunkt": "abcdef:1"})
    d = lnd_macaroon.gebuehren
    assert "global" not in d
    assert d["chan_point"] == {"funding_txid_str": "abcdef", "output_index": 1}


def test_unsinnige_gebuehren_werden_abgewiesen(client, lnd_macaroon):
    """Der Netz-Median lag 2026 bei rund 143 ppm. Wer 50.000 setzt, wird
    gemieden -- das gehoert verhindert, bevor jemand sich wundert."""
    _richte_ein(client)
    r = client.post("/api/lightning/gebuehren",
                    json={"basis_msat": 0, "satz_ppm": 50_000})
    assert r.status_code == 422
    assert lnd_macaroon.gebuehren is None


def test_ohne_lightning_gibt_es_keine_adresse(client, lnd_da):
    _richte_ein(client)
    r = client.post("/api/lightning/einzahladresse")
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "lightning_nicht_bereit"


# ── Ein Name, der still nicht mehr aufloest ────────────────────────────────
#
# Der Anlass, 31.08.2026: Im Betriebsprotokoll stand "Name ... nicht
# aufloesbar: [Errno -5]". Von aussen loeste derselbe Name ueber drei Resolver
# einwandfrei auf -- es scheiterte nur im Container. Die Anwendung hat richtig
# reagiert und die Adresse in Ruhe gelassen.
#
# Genau das ist aber die Falle: nach aussen sieht alles gut aus. Der Knoten
# wirbt weiter mit der Adresse von damals, und nach der naechsten
# Zwangstrennung gehoert die jemand anderem.


def test_ein_haengender_name_wird_gemeldet(client, monkeypatch):
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    _wege(client, externe_adresse="meinknoten.example")

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: [])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    d = client.get("/api/knoten/netzwege").json()
    assert d["name_haengt_seit_s"] is not None
    assert d["name_haengt_seit_s"] >= 0


def test_ein_aufloesbarer_name_haengt_nicht(client, monkeypatch):
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    _wege(client, externe_adresse="meinknoten.example")

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["203.0.113.7"])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    assert client.get("/api/knoten/netzwege").json()["name_haengt_seit_s"] is None


def test_ohne_nachgesehen_zu_haben_wird_nichts_behauptet(client):
    """"Noch nie nachgesehen" ist etwas anderes als "geht nicht"."""
    _richte_ein(client)
    assert client.get("/api/knoten/netzwege").json()["name_haengt_seit_s"] is None


def test_ein_haengender_name_laesst_die_konfiguration_in_ruhe(client, monkeypatch):
    """Lieber die alte Adresse als eine leere: ohne externalip lernt der
    Knoten seine Adresse gar nicht mehr an."""
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["203.0.113.7"])
    _wege(client, externe_adresse="meinknoten.example")
    pfad = client.tmp / "config" / "bitcoind.conf"
    assert "externalip=203.0.113.7" in pfad.read_text()

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: [])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    assert "externalip=203.0.113.7" in pfad.read_text()


# ── Adresswechsel: Lightning kann, was Bitcoin nicht kann ──────────────────
#
# Die Frage aus dem Betrieb am 31.08.2026: kann man dem Netz sagen, dass die neue IP die
# alte ersetzen soll? Bei Bitcoin nicht -- ein Knoten hat keine Identitaet, er
# IST seine Adresse; die alte altert nur weg (bis zu 30 Tage, ADDRMAN_HORIZON).
# Bei Lightning schon: der Knoten hat einen Pubkey, und ein node_announcement
# mit neuerem Zeitstempel ersetzt das alte samt Adressen (BOLT 7).
#
# LND schickt das von allein -- aber nur, wenn es die neue Adresse kennt. Und
# das Nachfuehren schrieb bisher NUR in die bitcoind-Konfiguration.


def _mit_lnd(client):
    from satcortex import nodeconfig
    (client.tmp / "config" / "lnd.conf").write_text(
        nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen()))
    return client.tmp / "config" / "lnd.conf"


def test_ein_adresswechsel_erreicht_auch_lightning(client, monkeypatch):
    from satcortex import dyndns as dyndns_modul, nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    _wege(client, externe_adresse="meinknoten.example")
    pfad = _mit_lnd(client)

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["198.18.7.7"])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    assert nodeconfig.lies_lnd_adressen(pfad.read_text()) == ["198.18.7.7:9735"]


def test_ohne_lightning_stoert_das_nachfuehren_nicht(client, monkeypatch):
    """Wer Lightning noch nicht eingerichtet hat, soll davon nichts merken."""
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    _wege(client, externe_adresse="meinknoten.example")

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["198.18.7.7"])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=198.18.7.7" in conf
    assert not (client.tmp / "config" / "lnd.conf").exists()


def test_lightning_bekommt_nur_eingeschaltete_netze(client, monkeypatch):
    """Eine IPv6-Adresse anzukuendigen, waehrend IPv6 aus ist, waere auch bei
    Lightning eine Einladung, die niemand annehmen kann."""
    from satcortex import dyndns as dyndns_modul, nodeconfig, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    _wege(client, ipv6=False, externe_adresse="meinknoten.example")
    pfad = _mit_lnd(client)

    monkeypatch.setattr(dyndns_modul, "loese_auf",
                        lambda *a, **kw: ["198.18.7.7", "2003:db8::1"])
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()

    assert nodeconfig.lies_lnd_adressen(pfad.read_text()) == ["198.18.7.7:9735"]


def test_ohne_aenderung_startet_lnd_nicht_neu(client, monkeypatch):
    """Jeder Schreibvorgang startet LND neu -- und ein Neustart trennt kurz
    alle Kanaele."""
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["198.18.7.7"])
    _wege(client, externe_adresse="meinknoten.example")
    pfad = _mit_lnd(client)
    client.app.state.macaroon_sicherstellen  # nur damit der Zustand steht

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage())
    client.app.state.einmal_nachsehen()
    stand = pfad.stat().st_mtime_ns
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()
    assert pfad.stat().st_mtime_ns == stand


def test_die_eigene_onion_wird_mitgeprueft(client, lnd_da, monkeypatch):
    """Sie ist einer der vier Wege -- und der verlaesslichste: sie aendert
    sich bei einer Zwangstrennung nicht."""
    from satcortex import dyndns as dyndns_modul, erreichbar as modul
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    # VOR dem Speichern setzen: die Kettenlage wird drei Sekunden lang
    # zwischengespeichert, und das Speichern holt sie sich bereits.
    onion = "kscutiudrd2kwjwucpu5da5r6ni47yypcgsmvtxy6bz7qpimqepkqiyd.onion"
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage(adressen=[
        {"adresse": "93.184.216.34", "port": 8333},
        {"adresse": onion, "port": 8333}]))
    _wege(client, externe_adresse="meinknoten.example")

    gesehen = {}
    monkeypatch.setattr(modul, "pruefe", lambda a, p, proxy, **kw: (
        gesehen.update(adressen=list(a)),
        {"port": p, "adressen": [], "erreichbar": True, "geprueft": True})[1])
    client.post("/api/knoten/erreichbarkeit")
    assert onion in gesehen["adressen"]


def test_ohne_tor_wird_die_onion_nicht_geprueft(client, lnd_da, monkeypatch):
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    _wege(client, tor=False, externe_adresse="meinknoten.example")
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _lage(adressen=[
        {"adresse": "abc.onion", "port": 8333}]))
    d = client.post("/api/knoten/erreichbarkeit").json()
    assert d["grund"] == "tor_aus", "ohne Tor gibt es keinen ehrlichen Test"


# Gemeldet am 01.09.2026: "da steht nie das ich ueber tor erreichbar bin, nie,
# und ich habe das schon 10 mal probiert -- immer nur ipv4". Kein Fehler in
# der Messung: waehrend der Abgleich-Pause steht die .onion nicht in
# localaddresses (siehe ABGLEICH_GRUND), es gab also nichts zu pruefen. Die
# Antwort sah trotzdem vollstaendig aus. Eine ausgelassene Messung, die sich
# nicht zu erkennen gibt, ist eine stille Falschaussage.


def _ohne_onion(client, monkeypatch, *, im_erstsync):
    from satcortex import dyndns as dyndns_modul, erreichbar as modul
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    # Vor dem Speichern: netzwege_schreiben holt sich die Lage bereits, und
    # aus ihr entsteht die onlynet-Zeile, die dieser Test spaeter liest.
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(im_erstsync=im_erstsync, adressen=[
                            {"adresse": "93.184.216.34", "port": 8333}]))
    _wege(client, externe_adresse="meinknoten.example")
    monkeypatch.setattr(modul, "pruefe", lambda a, p, proxy, **kw: {
        "port": p, "adressen": [], "erreichbar": True, "geprueft": True})
    return client.post("/api/knoten/erreichbarkeit").json()


def test_die_pausierte_onion_wird_benannt_statt_ausgelassen(client, monkeypatch):
    """Tor an, aber waehrend des Abgleichs nicht angekuendigt -- das gehoert
    hingeschrieben, sonst sucht man den Fehler im eigenen Router."""
    d = _ohne_onion(client, monkeypatch, im_erstsync=True)
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=ipv4" in conf, "Voraussetzung des Tests: die Pause laeuft"
    assert d["tor_hinweis"] == "tor_pausiert"


def test_fehlende_onion_ohne_pause_ist_ein_befund(client, monkeypatch):
    """Steht die Kette und Tor ist an, MUSS die Adresse da sein. Fehlt sie
    trotzdem, ist etwas mit dem Steuerport -- ein anderer Satz."""
    d = _ohne_onion(client, monkeypatch, im_erstsync=False)
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=" not in conf, "Voraussetzung des Tests: keine Pause"
    assert d["tor_hinweis"] == "keine_onion"


def test_mit_angekuendigter_onion_gibt_es_nichts_zu_erklaeren(client, monkeypatch):
    from satcortex import dyndns as dyndns_modul, erreichbar as modul
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda *a, **kw: ["93.184.216.34"])
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lage(im_erstsync=False, adressen=[
                            {"adresse": "93.184.216.34", "port": 8333},
                            {"adresse": "abc.onion", "port": 8333}]))
    _wege(client, externe_adresse="meinknoten.example")
    monkeypatch.setattr(modul, "pruefe", lambda a, p, proxy, **kw: {
        "port": p, "adressen": [], "erreichbar": True, "geprueft": True})
    d = client.post("/api/knoten/erreichbarkeit").json()
    assert d["tor_hinweis"] == ""


# ── Eine ausgefallene Abfrage ist kein Zustand ────────────────────────────
#
# Der teuerste Fehler dieser Sitzung, gemeldet als "ich habe quasi keine
# Verbindung mehr zu irgendwas". _erlaubte_netze las eine AUSGEFALLENE
# Kettenlage als "kein Erstabgleich": bool((lage or {}).get("im_erstsync")).
#
# Waehrend des Abgleichs faellt getblockchaininfo regelmaessig aus -- es
# braucht cs_main, und Core haelt die Sperre bei jedem
# chainstate-Schreibvorgang; am 28.08.2026 kam rund jeder fuenfte Abruf nicht
# durch. Jeder dieser Ausfaelle hob die Tor-Pause auf, onlynet verschwand aus
# der Datei, gib_frei() startete bitcoind neu. Beim naechsten Durchgang mit
# funktionierender Lage dasselbe rueckwaerts. Ein Pendel, dessen Ausschlag
# jeweils Minuten ohne Verbindungen kostet.


def test_ohne_lage_bleibt_die_pause_stehen():
    wege = _wege_dict()
    erlaubt, _grund = api._erlaubte_netze(wege, None, ("ipv4", "ipv6"))
    assert "onion" not in erlaubt, (
        "eine ausgefallene Abfrage darf die Pause nicht aufheben -- das "
        "schreibt die Konfiguration um und startet bitcoind neu")


def test_ohne_lage_wird_die_pause_auch_nicht_angeworfen():
    """Dieselbe Regel in die andere Richtung: was laeuft, laeuft weiter."""
    wege = _wege_dict()
    erlaubt, _grund = api._erlaubte_netze(wege, None, ("ipv4", "ipv6", "onion"))
    assert "onion" in erlaubt


def test_mit_lage_greift_die_pause_weiterhin():
    from satcortex import nodeconfig

    wege = _wege_dict()
    lage = _lage(netze={"ipv4": 5, "onion": 5})
    erlaubt, grund = api._erlaubte_netze(wege, lage, ("ipv4", "ipv6", "onion"))
    assert "onion" not in erlaubt and grund == nodeconfig.ABGLEICH_GRUND


def test_unbekannte_phase_wird_nicht_als_fertig_gemeldet(client, monkeypatch):
    """Die Oberflaeche schrieb sonst "die Kette steht" -- mitten im
    Erstabgleich, nur weil eine Abfrage nicht durchkam."""
    from satcortex import rpc as rpc_modul

    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: None)
    d = client.get("/api/knoten/netzwege").json()
    assert d["im_erstsync"] is None


def _wege_dict(**mehr):
    d = {"tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
         "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True}
    d.update(mehr)
    return d


# ── Kein Aufruf zweimal je Takt ────────────────────────────────────────────
#
# Am 02.09.2026 gezaehlt: ein Anzeigetakt der Uebersicht kostete ZWOELF
# RPC-Aufrufe, davon acht doppelte -- getpeerinfo viermal, getnettotals
# dreimal, getblockchaininfo und getnetworkinfo je zweimal. /status,
# /beitrag und /karte holten sie unabhaengig voneinander.
#
# Waehrend des Erstabgleichs stehen sie alle in derselben Schlange: Core
# bedient HTTP mit sechzehn Faeden (DEFAULT_HTTP_THREADS in
# v31.1/src/httpserver.h), und die haengen an cs_main, sobald der chainstate
# geschrieben wird. Jeder doppelte Aufruf macht damit das Zeitlimit der
# anderen wahrscheinlicher -- und genau diese Zeitlimits standen eine Woche
# lang im Protokoll.


def test_kein_rpc_aufruf_wird_je_takt_wiederholt(client, monkeypatch):
    import collections

    from satcortex import rpc as rpc_modul

    _richte_ein(client)
    antworten = {
        "getblockchaininfo": {
            "chain": "main", "blocks": 827_000, "headers": 965_000,
            "verificationprogress": 0.68, "initialblockdownload": True,
            "size_on_disk": 1, "difficulty": 1.0, "time": 1_706_000_000},
        "getnetworkinfo": {"connections_in": 0, "connections_out": 10,
                           "subversion": "/S/", "localaddresses": []},
        "getnettotals": {"totalbytesrecv": 1, "totalbytessent": 1},
        "getpeerinfo": [{"addr": "1.2.3.4:8333", "network": "ipv4",
                         "inbound": False, "bytessent": 1,
                         "bytessent_per_msg": {"block": 0}}],
        "getaddrmaninfo": {"ipv4": {"total": 0}},
        "getmempoolinfo": {"loaded": False},
    }
    gezaehlt: collections.Counter = collections.Counter()

    def ruf(self, methode, *p, **kw):
        gezaehlt[methode] += 1
        if methode in antworten:
            return antworten[methode]
        raise rpc_modul.RpcFehler("unbekannt: " + methode)

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)

    # Genau das holt die Oberflaeche in einem Durchgang.
    for pfad in ("/api/status", "/api/beitrag", "/api/karte"):
        client.get(pfad)

    doppelt = {m: n for m, n in gezaehlt.items() if n > 1}
    assert not doppelt, (
        "Diese Aufrufe gingen mehrfach an bitcoind, obwohl ein Takt "
        "dieselbe Antwort bekommt: " + ", ".join(
            f"{n}x {m}" for m, n in sorted(doppelt.items())))
    # Sechs, und getindexinfo ist bewusst NICHT dabei: waehrend des
    # Abgleichs sind die Indizes ohnehin abgeschaltet und die Antwort waere
    # immer leer. Nach dem Abgleich kommt er dazu -- siehe den Test darunter.
    assert sum(gezaehlt.values()) <= 6, (
        f"ein Takt sollte mit einer Handvoll Aufrufe auskommen, waren "
        f"{sum(gezaehlt.values())}")
    assert "getindexinfo" not in gezaehlt, \
        "waehrend des Abgleichs sagt getindexinfo nichts und kostet trotzdem"


def test_die_einstellungen_warten_nicht_auf_bitcoind(client, monkeypatch):
    """Aus dem Betrieb, 03.09.2026: "solange der Bitcoin Knoten wegschreibt kann
    die ganze App nix machen". Die Schalter stehen in einer Datei auf der
    Platte -- diese Seite darf keinen einzigen RPC-Aufruf ausloesen."""
    from satcortex import rpc as rpc_modul

    _richte_ein(client)
    gerufen = []

    def ruf(self, methode, *p, **kw):
        gerufen.append(methode)
        raise rpc_modul.Beschaeftigt("antwortet nicht innerhalb von 15 s")

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)
    r = client.get("/api/knoten/netzwege")
    assert r.status_code == 200
    assert r.json()["tor"] is True, "die gespeicherte Wahl kommt trotzdem"
    assert gerufen == [], (
        "die Einstellungen haben bitcoind gefragt und damit auf cs_main "
        f"gewartet: {gerufen}")


# ── Die Daten liegen bereit, sie werden nicht geholt (04.09.2026) ───────────
#
# Der Betreiber: "der aufruf der app dauert immer noch sehr lange im browser .. bis
# man mal die daten sieht ... vielleicht liegt es daran das unsere app kein
# richtiges backend und frontend hat ... wo die daten zur bereitstellung
# liegen??"
#
# Der Einwand traf. Jeder Endpunkt holte seine Zahlen selbst, sobald der
# Zwischenspeicher aelter als drei Sekunden war -- und der Anzeigetakt sind
# zehn. Er war also bei praktisch jedem Aufruf kalt, und waehrend Core den
# chainstate schreibt, wartet so eine Abfrage bis zu fuenfzehn Sekunden.
#
# Im Pruefstand gemessen, mit einem bitcoind das vier Sekunden je Aufruf
# braucht: sieben Schnittstellen zusammen VORHER 95,3 s, NACHHER 0,015 s.


def _zaehlender_knoten(monkeypatch, antworten):
    import collections

    from satcortex import rpc as rpc_modul

    gezaehlt: collections.Counter = collections.Counter()

    def ruf(self, methode, *p, **kw):
        gezaehlt[methode] += 1
        if methode in antworten:
            return antworten[methode]
        raise rpc_modul.RpcFehler("unbekannt: " + methode)

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)
    return gezaehlt


ANTWORTEN = {
    "getblockchaininfo": {
        "chain": "main", "blocks": 827_000, "headers": 965_000,
        "verificationprogress": 0.68, "initialblockdownload": True,
        "size_on_disk": 1, "difficulty": 1.0, "time": 1_706_000_000},
    "getnetworkinfo": {"connections_in": 0, "connections_out": 10,
                       "subversion": "/S/", "localaddresses": []},
    "getnettotals": {"totalbytesrecv": 1, "totalbytessent": 1},
    "getpeerinfo": [{"addr": "1.2.3.4:8333", "network": "ipv4",
                     "inbound": False, "bytessent": 1,
                     "bytessent_per_msg": {"block": 0}}],
    "getaddrmaninfo": {"ipv4": {"total": 0}},
    "getmempoolinfo": {"loaded": False},
}


def test_nach_der_ersten_messung_fragt_kein_aufruf_mehr_nach(client, monkeypatch):
    """Der Kern der Sache: der Mensch vor dem Bildschirm wartet nie auf
    bitcoind. Genau EINMAL wird gemessen -- danach wird nur noch abgelesen,
    bis der Sammler im Hintergrund neue Zahlen hinlegt."""
    _richte_ein(client)
    gezaehlt = _zaehlender_knoten(monkeypatch, ANTWORTEN)

    # Der erste Seitenaufbau darf messen -- das ist der Kaltstart.
    seiten = ("/api/status", "/api/beitrag", "/api/karte", "/api/kennzahlen")
    for pfad in seiten:
        client.get(pfad)
    nach_dem_ersten = sum(gezaehlt.values())
    assert nach_dem_ersten > 0, "der Kaltstart hat gar nicht gemessen"

    # Jeder weitere darf es nicht mehr.
    for _ in range(3):
        for pfad in seiten:
            client.get(pfad)

    assert sum(gezaehlt.values()) == nach_dem_ersten, (
        "ein Aufruf hat bitcoind erneut gefragt: "
        + ", ".join(f"{n}x {m}" for m, n in sorted(gezaehlt.items())))


def test_waehrend_des_abgleichs_wird_keine_blockvorlage_gebaut(client, monkeypatch):
    """getblocktemplate baut jedes Mal wirklich eine Vorlage -- und Core
    lehnt sie waehrend des Erstabgleichs ohnehin ab. Sie tagelang alle
    zwanzig Sekunden trotzdem anzufordern, ist Last genau an dem Knoten, der
    schon am Anschlag laeuft."""
    _richte_ein(client)
    gezaehlt = _zaehlender_knoten(monkeypatch, ANTWORTEN)
    client.get("/api/status")
    client.get("/api/kennzahlen")
    assert gezaehlt["getblocktemplate"] == 0
    assert gezaehlt["estimatesmartfee"] == 0


def test_die_kennzahlen_holen_die_kettenlage_nicht_ein_zweites_mal(client, monkeypatch):
    """Sie lag im Sammler bereit -- und wurde trotzdem noch einmal geholt.
    Das allein waren im Pruefstand siebenundzwanzig Sekunden."""
    _richte_ein(client)
    gezaehlt = _zaehlender_knoten(monkeypatch, ANTWORTEN)
    client.get("/api/status")
    vorher = gezaehlt["getblockchaininfo"]
    client.get("/api/kennzahlen")
    assert gezaehlt["getblockchaininfo"] == vorher


# ── Lightning-Sichtbarkeit gehoert zu den Netzeinstellungen (04.09.2026) ────
#
# Der Betreiber: "kann man das nicht ueber die einstellung wo wir bis jetzt auch
# unsere ip geschichten haben mit einbinden?? ... man soll immer die wahl
# haben ob only ueber tor (anonym) oder tor mit ip freigabe router oder ip
# freigabe clearnet mit dyndns weiterleitung."

def test_die_sichtbarkeit_ueberlebt_das_speichern(client):
    _richte_ein(client)
    for art in ("hybrid", "still", "tor"):
        client.post("/api/knoten/netzwege", json={
            "tor": True, "ipv4": True, "ipv6": False,
            "externe_adresse": "meinknoten.example",
            "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True,
            "sichtbarkeit": art})
        d = client.get("/api/knoten/netzwege").json()
        assert d["sichtbarkeit"] == art


def test_die_wahl_gilt_fuer_beide_dienste(client):
    """Aus dem Betrieb, 05.09.2026: "verstehe nicht, warum diese Einstellungen nur
    fuer LND gelten und nicht generell fuer unsere App?" -- und: "kann ja
    auch fuer BTC gut sein, die Auswahl."

    Also gilt sie fuer beide. "Nur ueber Tor" heisst dann auch bei bitcoind
    onlynet=onion; die Haekchen fuer IPv4 und IPv6 sind in dieser Betriebsart
    ohne Wirkung, und die Anzeige sagt das auch. Waeren sie es nicht, waere
    die Wahl eine Behauptung ohne Folge -- der schlimmste Fall bei einer
    Einstellung, die Anonymitaet verspricht.
    """
    _richte_ein(client)
    client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": True,
        "externe_adresse": "meinknoten.example",
        "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True,
        "sichtbarkeit": "tor"})
    # Die WAHL des Nutzers bleibt stehen -- sie ist seine Voreinstellung fuer
    # den Fall, dass er zurueckschaltet.
    d = client.get("/api/knoten/netzwege").json()
    assert d["sichtbarkeit"] == "tor"
    assert d["ipv4"] is True, "die Haekchen duerfen nicht geloescht werden"

    # Entscheidend ist, was in der Konfiguration steht. Dort gilt die Wahl.
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    zeile = [z for z in conf.splitlines() if z.startswith("onlynet=")]
    assert zeile == ["onlynet=onion"], zeile
    assert "meinknoten.example" not in conf, "es wurde etwas angekuendigt"


def test_die_adresse_bleibt_erhalten_wenn_man_zurueckschaltet(client):
    """Der eingetragene Name verschwindet nicht, nur weil gerade nichts
    angekuendigt wird -- sonst muesste man ihn jedes Mal neu tippen."""
    _richte_ein(client)
    for art in ("hybrid", "tor", "hybrid"):
        client.post("/api/knoten/netzwege", json={
            "tor": True, "ipv4": True, "ipv6": True,
            "externe_adresse": "meinknoten.example",
            "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True,
            "sichtbarkeit": art})
    d = client.get("/api/knoten/netzwege").json()
    assert d["externe_adresse"] == "meinknoten.example"
    assert d["ipv4"] is True


def test_eine_falsche_angabe_wird_abgelehnt(client):
    """Ein unbekannter Wert duerfte nicht stillschweigend zu "hybrid"
    werden -- das waere die Preisgabe, die niemand gewaehlt hat."""
    _richte_ein(client)
    a = client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
        "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
        "sichtbarkeit": "oeffentlich_bitte"})
    assert a.status_code == 422


def test_die_wahl_aendert_wirklich_die_bitcoind_konfiguration(client):
    """Frueher stand hier das Gegenteil: die Wahl galt nur fuer LND, also
    durfte sie bitcoind nicht anfassen. Seit sie fuer beide Dienste gilt, ist
    genau das falsch -- eine Betriebsart "nur ueber Tor", die bitcoind
    weiterhin ueber IPv4 telefonieren laesst, waere eine Luege.

    Der Preis ist ein Neustart von bitcoind. Der steht in der Oberflaeche
    auch dabei.
    """
    _richte_ein(client)
    grund = {"tor": True, "ipv4": True, "ipv6": True,
             "externe_adresse": "meinknoten.example",
             "adresse_ankuendigen": True, "tor_pause_beim_abgleich": False}
    client.post("/api/knoten/netzwege", json={**grund, "sichtbarkeit": "hybrid"})
    hybrid = (client.tmp / "config" / "bitcoind.conf").read_text()
    antwort = client.post("/api/knoten/netzwege",
                          json={**grund, "sichtbarkeit": "tor"})
    nur_tor = (client.tmp / "config" / "bitcoind.conf").read_text()

    assert nur_tor != hybrid
    assert "onlynet=onion" in nur_tor and "ipv4" not in nur_tor.split("onlynet=")[1].split("\n")[0]
    assert "meinknoten.example" not in nur_tor      # nichts angekuendigt
    assert antwort.json()["neustart_noetig"] is True


def test_ein_bestehender_knoten_aendert_sich_durch_das_update_nicht(client):
    """Der heikelste Teil des Umbaus.

    dem Knoten im Betrieb laeuft seit Tagen im Erstabgleich: Tor an, IPv4 an, IPv6
    aus, eigene Adresse angekuendigt. Wuerde die neue Wahl mit ihrer Vorgabe
    starten statt aus dem Bestand abgeleitet zu werden, spraenge er auf
    onlynet=onion -- und verloere mitten im Abgleich seine zehn
    IPv4-Gegenstellen. Ein Update darf so etwas nicht tun.
    """
    _richte_ein(client)
    # Ein Zustand, wie ihn eine aeltere Fassung hinterlassen hat: die neue
    # Wahl gibt es dort noch gar nicht.
    from satcortex import state as state_modul
    ablage = state_modul.Ablage(str(client.tmp / "config"))
    alt = dict(ablage.laden().knotenwahl or {})
    alt.update(tor_aktiv=True, netz_ipv4=True, netz_ipv6=False,
               adresse_ankuendigen=True, externe_adresse="meinknoten.example")
    alt.pop("sichtbarkeit", None)
    ablage.merke_knotenwahl(alt)

    d = client.get("/api/knoten/netzwege").json()
    assert d["sichtbarkeit"] == "hybrid", "der Knoten waere still geworden"
    assert d["ipv4"] is True and d["ipv6"] is False
    assert d["adresse_ankuendigen"] is True
    assert d["externe_adresse"] == "meinknoten.example"


def test_wer_nichts_ankuendigt_bleibt_still(client):
    """Die andere Richtung der Ableitung: ein Knoten ohne Ankuendigung darf
    durch das Update nicht ploetzlich seine Adresse verraten."""
    _richte_ein(client)
    from satcortex import state as state_modul
    ablage = state_modul.Ablage(str(client.tmp / "config"))
    alt = dict(ablage.laden().knotenwahl or {})
    alt.update(tor_aktiv=True, netz_ipv4=True, netz_ipv6=True,
               adresse_ankuendigen=False, externe_adresse="meinknoten.example")
    alt.pop("sichtbarkeit", None)
    ablage.merke_knotenwahl(alt)

    d = client.get("/api/knoten/netzwege").json()
    assert d["sichtbarkeit"] == "still"
    assert d["adresse_ankuendigen"] is False


# ── Wallet-Software im Heimnetz (05.09.2026) ────────────────────────────────
#
# Der Betreiber: "was mir auch schmecken wuerde wenn ich meine transaktionen von
# meinem hardware wallet dann auch ueber mein btc knoten machen koennte ...
# der bitcoin core zugangsdaten ... solte dann in den einstellungen sichtbar
# sein weil wenn ich mich mit der macsoftware an meinem knoten anmelden will
# brauche ich ja die daten."
#
# Sparrows eigene Beschreibung, am 05.09.2026 nachgeschlagen: "Sparrow does
# not use Bitcoin Core's internal wallet" -- es wird also keine Wallet im
# Knoten angelegt und kein Schluessel dorthin gegeben.

def test_die_freigabe_landet_in_der_konfiguration(client):
    _richte_ein(client)
    grund = {"tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
             "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
             "sichtbarkeit": "still"}
    client.post("/api/knoten/netzwege",
                json={**grund, "rpc_heimnetz": "192.168.178.0/24"})
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    zeilen = [z for z in conf.splitlines() if z.startswith("rpcallowip=")]
    assert "rpcallowip=192.168.178.0/24" in zeilen
    # Und die Zeile fuer das Compose-Netz MUSS stehen bleiben -- ohne sie
    # spraeche die Anwendung nicht mehr mit ihrem eigenen Knoten.
    assert any(z.endswith(nodeconfig.RPC_COMPOSE_NETZ) for z in zeilen), zeilen


def test_das_abschalten_nimmt_nur_die_heimnetz_zeile(client):
    _richte_ein(client)
    grund = {"tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
             "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
             "sichtbarkeit": "still"}
    client.post("/api/knoten/netzwege",
                json={**grund, "rpc_heimnetz": "192.168.178.0/24"})
    client.post("/api/knoten/netzwege", json={**grund, "rpc_heimnetz": ""})
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    zeilen = [z for z in conf.splitlines() if z.startswith("rpcallowip=")]
    assert zeilen == [f"rpcallowip={nodeconfig.RPC_COMPOSE_NETZ}"], zeilen


def test_eine_freigabe_ins_offene_internet_wird_abgelehnt(client):
    """0.0.0.0/0 waere keine Freigabe fuers Heimnetz, sondern fuer alle, die
    den Port erreichen. Das gibt es hier nicht, auch nicht auf Wunsch."""
    _richte_ein(client)
    for netz in ("0.0.0.0/0", "8.8.8.8/32", "::/0"):
        a = client.post("/api/knoten/netzwege", json={
            "tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
            "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
            "sichtbarkeit": "still", "rpc_heimnetz": netz})
        assert a.status_code == 422, netz


def test_ein_tippfehler_startet_bitcoind_nicht_kaputt(client):
    """Ungepruefter Text landete sonst in einer Zeile, die bitcoind liest --
    und bei einem Tippfehler kommt es gar nicht mehr hoch."""
    _richte_ein(client)
    a = client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": True, "externe_adresse": "",
        "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
        "sichtbarkeit": "still", "rpc_heimnetz": "192.168.178."})
    assert a.status_code == 422


def test_die_zugangsdaten_sind_die_des_knotens(client):
    """Sie muessen zu dem passen, womit die Anwendung selbst spricht --
    sonst schickt man den Menschen mit einem Passwort los, das nirgends
    gilt."""
    _richte_ein(client)
    d = client.get("/api/knoten/rpc-zugang").json()
    assert d["eingerichtet"] is True
    assert d["benutzer"] and d["passwort"]
    assert d["port"] == 8332
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert d["benutzer"] in conf          # als rpcauth-Zeile
    assert d["passwort"] not in conf, "das Klartext-Passwort gehoert NICHT in die Datei"


# ── Der Assistent kennt, was die Einstellungen koennen (05.09.2026) ─────────
#
# Der Betreiber: "das sind dann aber alles so Einstellungen, die sollten dann in der
# example.env und vor allem auch in den Einstellungen am Anfang beim
# Installationsverfahren als Schritt gezeigt werden, oder nicht?? Wenn jemand
# das so neu installiert, hat er ja noch keine Ahnung."
#
# Er hat recht, und der Befund war schlimmer als die Frage: seit 0.38.0 fuehrte
# die Einstellungsseite mit der Sichtbarkeitswahl, der Assistent zeigte
# weiterhin die alten Haekchen. Zwei Modelle fuer dieselbe Sache -- wer neu
# installiert, trifft die Entscheidung blind und findet danach eine andere
# Darstellung vor. Ab hier gilt im Assistenten dieselbe Wahl, und sie hat
# dieselbe Folge.

def test_assistent_nur_ueber_tor_schreibt_onlynet(client):
    """Die Wahl muss in der Konfiguration ankommen, nicht nur im Gedaechtnis.

    Sonst waere sie eine Behauptung ohne Folge -- genau der Fehler, gegen den
    /knoten/netzwege schon abgesichert ist.
    """
    _richte_ein(client, sichtbarkeit="tor", externe_adresse="203.0.113.7")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=onion" in conf
    # Wer nur ueber Tor erreichbar sein will, kuendigt keine Klarnetz-Adresse
    # an. Sonst stuende die IP im Gossip, die gerade nicht benutzt werden soll.
    assert "externalip=203.0.113.7" not in conf


def test_assistent_hybrid_laesst_alle_netze_offen(client):
    """Die Vorgabe. Sie darf sich gegenueber frueher nicht veraendern."""
    _richte_ein(client, sichtbarkeit="hybrid", externe_adresse="203.0.113.7")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=" not in conf
    assert "externalip=203.0.113.7" in conf


def test_assistent_still_kuendigt_nichts_an(client):
    """Erreichbar bleiben, aber nicht auffindbar sein."""
    _richte_ein(client, sichtbarkeit="still", externe_adresse="203.0.113.7")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "externalip=" not in conf


def test_assistent_ohne_angabe_bleibt_alles_wie_bisher(client):
    """Keine Sichtbarkeit im Aufruf heisst: die Vorgabe, also hybrid.

    Wichtig fuer alles, was den Assistenten schon benutzt -- eine neue Angabe
    darf bestehende Ablaeufe nicht umlegen.
    """
    _richte_ein(client, externe_adresse="203.0.113.7")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "onlynet=" not in conf
    assert "externalip=203.0.113.7" in conf


def test_assistent_wahl_steht_danach_in_den_einstellungen(client):
    """Der Assistent stellt ein, die Einstellungsseite zeigt dasselbe an.

    Ohne das Merken faellt die Anzeige auf die Ableitung aus den Haekchen
    zurueck -- und die kennt den Unterschied zwischen "still" und "hybrid ohne
    Adresse" nicht.
    """
    # Mit Adresse und eingeschaltetem IPv4 wuerde die Ableitung "hybrid"
    # sagen. Nur das Gemerkte kann hier "tor" ergeben.
    _richte_ein(client, sichtbarkeit="tor", externe_adresse="203.0.113.7")
    assert client.get("/api/knoten/netzwege").json()["sichtbarkeit"] == "tor"


def test_assistent_gibt_das_heimnetz_frei(client):
    _richte_ein(client, rpc_heimnetz="192.168.178.0/24")
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert "rpcallowip=192.168.178.0/24" in conf
    # Und das Compose-Netz bleibt drin -- ohne das spraeche die Anwendung
    # nicht mehr mit ihrem eigenen Knoten.
    assert f"rpcallowip={nodeconfig.RPC_COMPOSE_NETZ}" in conf


def test_assistent_ohne_heimnetz_bleibt_die_schnittstelle_zu(client):
    _richte_ein(client)
    conf = (client.tmp / "config" / "bitcoind.conf").read_text()
    assert conf.count("rpcallowip=") == 1


def test_assistent_lehnt_ein_oeffentliches_netz_ab(client):
    """Dieselbe Pruefung wie in den Einstellungen, an derselben Stelle.

    Ein Tippfehler landet sonst in einer Zeile, die bitcoind liest -- und dann
    kommt der Knoten gar nicht erst hoch.
    """
    assert _richte_ein(client, rpc_heimnetz="0.0.0.0/0").status_code == 422


# ── Ein Land nach Gebieten (05.09.2026) ────────────────────────────────────

def test_ein_land_laesst_sich_aufschluesseln(client):
    _richte_ein(client)
    d = client.get("/api/karte/land/DE").json()
    assert d["land"] == "DE"
    assert isinstance(d["gebiete"], list)


def test_kleinschreibung_gilt_auch(client):
    _richte_ein(client)
    assert client.get("/api/karte/land/de").json()["land"] == "DE"


def test_unsinn_als_land_wird_abgewiesen(client):
    """Das Kuerzel ist das EINZIGE, was hier von aussen kommt.

    Nicht in der Liste: "..". Der Client loest es im Pfad auf, bevor der
    Aufruf ueberhaupt hier ankommt -- ein Test darauf pruefte das Verhalten
    von httpx, nicht unseres. Gefaehrlich waere es ohnehin nicht: das
    Kuerzel wird nachgeschlagen, nie zu einem Dateipfad.
    """
    _richte_ein(client)
    for unsinn in ("DEU", "D", "1A", "%2e%2e", "de%2Fx"):
        assert client.get(f"/api/karte/land/{unsinn}").status_code == 404, unsinn


def test_ohne_gebietsnamen_sagt_es_das_statt_leer_zu_wirken(tmp_path):
    """Ein Abbild ohne regionen.json ist denkbar. Dann darf die Antwort nicht
    aussehen wie "in diesem Land ist niemand" -- das waere eine Aussage, wo
    ein Nichtwissen steht.

    Die Namen werden beim BAUEN der Anwendung geladen, nicht beim Aufruf --
    also muss der Client innerhalb des Austauschs entstehen.
    """
    from unittest import mock
    import satcortex.api as api_modul
    with mock.patch.object(api_modul.gebiete, "lade", return_value=None):
        c = _client(tmp_path)
        _richte_ein(c)
        d = c.get("/api/karte/land/DE").json()
    assert d["moeglich"] is False
    assert d["gebiete"] == []


def test_auch_gebiete_ohne_gegenstellen_stehen_in_der_liste(client):
    """Aus dem Betrieb, 06.09.2026: "ich klicke auf ein leuchtendes ODER NICHT
    leuchtendes Bundesland."

    Ein Umriss, den man nicht anklicken kann, sieht kaputt aus -- auch wenn
    dahinter nur eine Null steht. Und nur was in der Liste steht, bekommt in
    der Oberflaeche eine Nummer und damit einen Klick.
    """
    import pathlib
    from unittest import mock
    import satcortex.api as api_modul

    # Gegen die AUSGELIEFERTE Zuordnung, nicht gegen eine erfundene: sonst
    # prueft der Test seine eigene Attrappe. Ein Ueberspringen waere hier das
    # Schlechteste -- es sieht gruen aus und prueft nichts.
    echt = (pathlib.Path(__file__).resolve().parents[2] / "data"
            / "regionen.json")
    assert echt.exists(), echt
    with mock.patch.object(api_modul.gebiete, "STANDARDPFAD", str(echt)):
        eigen = client.tmp.parent / "gebietsprobe"
        eigen.mkdir(parents=True, exist_ok=True)
        c = _client(eigen)
        _richte_ein(c)
        d = c.get("/api/karte/land/DE").json()

    assert d["moeglich"] is True
    # Ohne echte Gegenstellen haben ALLE Gebiete Null -- und muessen trotzdem
    # dastehen, sonst laesst sich ein dunkles Bundesland nicht anklicken.
    assert len(d["gebiete"]) == 16, [g["de"] for g in d["gebiete"]]
    assert all(g["iso"] for g in d["gebiete"])
    assert {"Bayern", "Sachsen", "Mecklenburg-Vorpommern"} <= {
        g["de"] for g in d["gebiete"]}


# ── Einen gesicherten Knoten zurueckholen ──────────────────────────────────
#
# Der Weg, den es lange NICHT gab -- und dessen Fehlen der groesste Mangel am
# ganzen Knoten war. Eine Sicherung, die man nicht zurueckspielen kann, ist
# keine Sicherung, sondern eine Beruhigung.
#
# Er laeuft ueber DENSELBEN LND-Aufruf wie das Anlegen. Das hat eine Folge,
# die hier festgehalten gehoert: initwallet braucht kein Macaroon, denn es
# gibt noch keine Wallet. Die Anwendung kann also wiederherstellen, ohne je
# ein Recht zu halten, das Geld bewegen koennte.


def _zurueck(**mehr):
    leib = {"woerter": list(WOERTER), "passwort": WALLET_PASSWORT}
    leib.update(mehr)
    return leib


def test_aus_den_woertern_wird_die_wallet_neu_aufgebaut(client, lnd_da):
    import base64
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen", json=_zurueck())
    assert r.status_code == 200
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == WOERTER
    assert lnd_da.angelegt["recovery_window"] == 2500, \
        "ohne Fenster sucht LND die Kette gar nicht erst ab"
    passwort = base64.b64decode(lnd_da.angelegt["wallet_password"]).decode()
    assert passwort == WALLET_PASSWORT


def test_der_vorgelegte_seed_landet_nirgends_auf_der_platte(client, lnd_da):
    """Dieselbe Regel wie beim Anlegen, und sie gilt hier genauso: die Woerter
    gehen durch die Anwendung hindurch zu LND und sonst nirgendwohin."""
    _richte_ein(client)
    client.post("/api/lightning/wiederherstellen", json=_zurueck())

    gefunden = []
    for pfad in client.tmp.rglob("*"):
        if not pfad.is_file():
            continue
        try:
            inhalt = pfad.read_text(errors="ignore")
        except OSError:
            continue
        if any(w in inhalt for w in WOERTER):
            gefunden.append(str(pfad))
    assert not gefunden, f"Der Seed steht in: {gefunden}"


# Gross genug, um die Groessenprobe zu bestehen: LNDs kleinstmoegliche
# verpackte Sicherung misst 45 Byte.
ECHTE_GROESSE = _b64.b64encode(b"k" * 300).decode()


def test_die_kanalsicherung_geht_mit(client, lnd_da):
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(kanalsicherung=ECHTE_GROESSE))
    assert r.status_code == 200
    assert r.json()["mit_kanaelen"] is True
    assert lnd_da.angelegt["channel_backups"] == {
        "multi_chan_backup": {"multi_chan_backup": ECHTE_GROESSE}}


def test_ohne_sicherung_kommt_nur_die_kette_zurueck(client, lnd_da):
    """Das ist ein gueltiger Weg, kein Fehlschlag: wer die Datei nicht hat,
    bekommt sein On-Chain-Guthaben trotzdem."""
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen", json=_zurueck())
    assert r.json()["mit_kanaelen"] is False
    assert "channel_backups" not in lnd_da.angelegt


def test_alle_vierundzwanzig_in_einem_feld_sind_kein_fehler(client, lnd_da):
    """Wer sie aus einem Passwortmanager holt, hat sie als EINE Zeile."""
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(woerter=[" ".join(WOERTER).upper()]))
    assert r.status_code == 200
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == WOERTER


@pytest.mark.parametrize("woerter", [WOERTER[:23], WOERTER + ["wort25"], []])
def test_zu_wenige_oder_zu_viele_woerter_erreichen_lnd_nicht(client, lnd_da,
                                                             woerter):
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(woerter=woerter))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "seed_unvollstaendig"
    assert lnd_da.angelegt is None


def test_ein_vertipptes_wort_heisst_nicht_dienst_nicht_erreichbar(client, lnd_da,
                                                                  monkeypatch):
    """Beim Wiederherstellen ist der haeufigste Fehlschlag ein falsches Wort,
    und aezeeds Pruefsumme faengt ihn ab. Wer stattdessen "LND antwortet
    nicht" liest, sucht an der voellig falschen Stelle."""
    _richte_ein(client)

    from satcortex import api as api_modul
    from satcortex import lnd as lnd_modul

    def weigert(*a, **k):
        raise lnd_modul.LndFehler("invalid cipher seed mnemonic")

    monkeypatch.setattr(api_modul.lnd, "lege_wallet_an", weigert)
    r = client.post("/api/lightning/wiederherstellen", json=_zurueck())
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "seed_nicht_angenommen"


def test_neben_einer_bestehenden_wallet_wird_nichts_wiederhergestellt(client,
                                                                      lnd_da):
    """Die gefaehrlichste Verwechslung, die diese Oberflaeche anrichten
    koennte: am Ende zwei Wallets und die Frage, welche jetzt gilt."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/wiederherstellen", json=_zurueck())
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "wallet_gibt_es_schon"
    assert lnd_da.angelegt is None


def test_eine_zu_kleine_datei_erreicht_lnd_gar_nicht(client, lnd_da):
    """LND nimmt sie bei initwallet ungeprueft entgegen und scheitert erst
    beim STARTEN daran. Dann steht eine Wallet da und der Dienst laeuft nicht
    -- also lieber hier abfangen, was sich abfangen laesst."""
    import base64
    _richte_ein(client)
    winzig = base64.b64encode(b"x" * 20).decode()
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(kanalsicherung=winzig))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "sicherung_zu_klein"
    assert lnd_da.angelegt is None


def test_was_keine_base64_ist_ist_keine_sicherung(client, lnd_da):
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(kanalsicherung="das hier ist keine datei!"))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "sicherung_unlesbar"
    assert lnd_da.angelegt is None


def test_ohne_eingerichtetes_ziel_gibt_es_von_dort_nichts_zu_holen(client, lnd_da):
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(vom_ziel=True))
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "kein_ziel"
    assert lnd_da.angelegt is None


# ── Die Kopie pruefen, die man in der Hand haelt ───────────────────────────
#
# Dass der Knoten eine heile Sicherung erzeugen KANN, sagt nichts ueber die
# Kopie auf dem Stick. Der einzige Tag, an dem man das nicht mehr herausfinden
# kann, ist der, an dem man es braucht.


def test_die_vorgelegte_kopie_wird_von_lnd_aufgeschlossen(client, lnd_kanaele):
    _richte_ein(client)
    r = client.post("/api/lightning/sicherung/pruefen", json={"blob": SICHERUNG})
    assert r.status_code == 200
    d = r.json()
    assert d["quelle"] == "vorgelegt"
    assert d["abgedeckt"] == 3 and d["offen"] == 3
    assert d["vollstaendig"] is True
    # Geprueft wurde wirklich die vorgelegte Datei, nicht die des Knotens.
    assert lnd_kanaele.geprueft == {
        "multi_chan_backup": {"multi_chan_backup": SICHERUNG}}


def test_heil_ist_nicht_dasselbe_wie_aktuell(client, lnd_kanaele):
    """Eine tadellose Sicherung von vorgestern deckt den Kanal von gestern
    nicht ab. Das ist der Fehler, den man sonst erst hinterher bemerkt."""
    _richte_ein(client)
    lnd_kanaele.abgedeckt = 2          # drei Kanaele offen, zwei gesichert
    d = client.post("/api/lightning/sicherung/pruefen",
                    json={"blob": SICHERUNG}).json()
    assert d["abgedeckt"] == 2 and d["offen"] == 3
    assert d["vollstaendig"] is False


def test_eine_fremde_oder_kaputte_kopie_faellt_durch(client, lnd_kanaele):
    """LND muss die Datei zum Pruefen wirklich aufschliessen, und der
    Schluessel stammt aus dem Seed. Die Sicherung eines FREMDEN Knotens
    scheitert hier -- statt spaeter still nichts zurueckzuholen."""
    _richte_ein(client)
    lnd_kanaele.heil = False
    r = client.post("/api/lightning/sicherung/pruefen", json={"blob": SICHERUNG})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "sicherung_unbrauchbar"


def test_ohne_vorlage_wird_die_des_knotens_geprueft(client, lnd_kanaele):
    _richte_ein(client)
    d = client.post("/api/lightning/sicherung/pruefen", json={}).json()
    assert d["quelle"] == "knoten"
    assert d["vollstaendig"] is True


def test_ohne_lightning_gibt_es_nichts_zu_pruefen(client, lnd_da):
    _richte_ein(client)
    r = client.post("/api/lightning/sicherung/pruefen", json={"blob": SICHERUNG})
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "lightning_nicht_bereit"


def test_ein_ruhendes_lnd_ist_nicht_dasselbe_wie_eine_bestehende_wallet(client,
                                                                        lnd_da):
    """Wer aus einem Datenverlust kommt und "es gibt bereits eine Wallet"
    liest, obwohl LND nur noch nicht laeuft, sucht an der falschen Stelle."""
    _richte_ein(client)

    from satcortex import lnd as lnd_modul

    def schweigt(*a, **k):
        raise lnd_modul.NichtErreichbar("connection refused")

    lnd_da.ruf = schweigt
    r = client.post("/api/lightning/wiederherstellen", json=_zurueck())
    assert r.status_code == 503
    assert r.json()["detail"]["meldung"] == "lnd_antwortet_nicht"


def test_die_sicherung_kommt_vom_ziel_zurueck_in_die_wiederherstellung(
        client, lnd_kanaele, monkeypatch):
    """Der Weg, fuer den das Ganze gebaut ist: die Platte ist hin, die Datei
    liegt woanders. Erst Ziel einrichten, dann so tun, als waere alles weg."""
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "ein-app-passwort"})

    geholt = []

    def holt(url, benutzer, passwort, **kw):
        geholt.append((url, benutzer, passwort))
        return ECHTE_GROESSE

    monkeypatch.setattr(modul, "hole_ab", holt)
    # Und jetzt der Ernstfall: es gibt keine Wallet mehr.
    lnd_kanaele.stand = "NON_EXISTING"
    lnd_kanaele.angelegt = None
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(vom_ziel=True))
    assert r.status_code == 200
    assert r.json()["mit_kanaelen"] is True
    assert geholt == [("https://cloud.example/dav", "testnutzer", "ein-app-passwort")]
    assert lnd_kanaele.angelegt["channel_backups"] == {
        "multi_chan_backup": {"multi_chan_backup": ECHTE_GROESSE}}


def test_ein_ziel_das_nichts_hergibt_legt_keine_wallet_an(client, lnd_kanaele,
                                                          monkeypatch):
    """Sonst stuende am Ende eine Wallet ohne Kanaele da -- und der Nutzer
    haette seinen einen Versuch mit der Sicherung verbraucht."""
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "ein-app-passwort"})

    def leer(*a, **kw):
        raise modul.ZielFehler("404: Not Found")

    monkeypatch.setattr(modul, "hole_ab", leer)
    lnd_kanaele.stand = "NON_EXISTING"
    lnd_kanaele.angelegt = None
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(vom_ziel=True))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "ziel_gibt_nichts_her"
    assert lnd_kanaele.angelegt is None


def test_vom_ziel_kommt_der_satz_zum_fall_statt_der_zahl(client, lnd_kanaele,
                                                         monkeypatch):
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "ein-app-passwort"})

    def leer(*a, **kw):
        raise modul.ZielFehler("404: Not Found", "ziel_keine_sicherung_dort")

    monkeypatch.setattr(modul, "hole_ab", leer)
    lnd_kanaele.stand = "NON_EXISTING"
    lnd_kanaele.angelegt = None
    r = client.post("/api/lightning/wiederherstellen",
                    json=_zurueck(vom_ziel=True))
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "ziel_keine_sicherung_dort"
    assert lnd_kanaele.angelegt is None


def test_auch_die_am_ziel_abgelegte_laesst_sich_pruefen(client, lnd_kanaele,
                                                        monkeypatch):
    from satcortex import sicherung as modul
    _richte_ein(client)
    monkeypatch.setattr(modul, "lade_hoch", lambda *a, **kw: None)
    client.post("/api/lightning/sicherung/ziel", json={
        "url": "https://cloud.example/dav", "benutzer": "testnutzer",
        "passwort": "ein-app-passwort"})
    monkeypatch.setattr(modul, "hole_ab", lambda *a, **kw: ECHTE_GROESSE)

    d = client.post("/api/lightning/sicherung/pruefen",
                    json={"vom_ziel": True}).json()
    assert d["quelle"] == "ziel"
    assert lnd_kanaele.geprueft["multi_chan_backup"]["multi_chan_backup"] \
        == ECHTE_GROESSE


def test_nach_dem_abgleich_wird_der_indexstand_mitgeliefert(client, monkeypatch):
    """Core baut txindex und Blockfilter erst NACH dem Abgleich -- und das
    dauert Stunden. Solange findet die Transaktionssuche nichts, und
    Wallet-Software bekommt keine Antwort.

    Bis zum 08.09.2026 stand darueber nirgends etwas. Der Betreiber hat es von
    selbst vermutet: "vielleicht liegt es daran, dass das nicht geklappt
    hat." Eine Anwendung, in der man raten muss, was der Knoten gerade tut,
    erklaert ihn nicht.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    antworten = {
        "getblockchaininfo": {"chain": "main", "blocks": 966088,
                              "headers": 966088, "verificationprogress": 1.0,
                              "initialblockdownload": False,
                              "size_on_disk": 800_000_000_000, "time": 1788800000},
        "getnetworkinfo": {"connections_in": 3, "connections_out": 10,
                           "subversion": "/Satoshi:31.1.0/", "localaddresses": []},
        "getpeerinfo": [],
        "getnettotals": {"totalbytesrecv": 1, "totalbytessent": 2},
        "getindexinfo": {
            "txindex": {"synced": True, "best_block_height": 966088},
            "basic block filter index": {"synced": False,
                                         "best_block_height": 412000},
        },
        "getblockhash": "00" * 32,
        "getaddrmaninfo": {"ipv4": {"total": 0}},
        "getmempoolinfo": {"loaded": True, "size": 0, "bytes": 0,
                           "maxmempool": 300_000_000, "mempoolminfee": 0.00001,
                           "total_fee": 0},
    }

    def ruf(self, methode, *p, **kw):
        if methode in antworten:
            return antworten[methode]
        raise rpc_modul.RpcFehler("unbekannt: " + methode)

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)
    idx = client.get("/api/status").json()["knoten"]["indizes"]
    assert idx["txindex"] == {"fertig": True, "hoehe": 966088}
    assert idx["basic block filter index"] == {"fertig": False,
                                               "hoehe": 412000}, \
        "ein halb fertiger Index muss als halb fertig durchkommen"


# ── Lightning wird ueberhaupt erst eingerichtet ────────────────────────────
#
# DER FEHLER, DEN 825 TESTS NICHT GEFUNDEN HABEN. nodeconfig.baue_lnd() stand
# seit Wochen fertig da und wurde von keiner einzigen Stelle im laufenden Code
# aufgerufen -- nur aus tests/test_nodeconfig.py. Jeder Test pruefte, dass die
# Datei RICHTIG aussaehe, keiner, dass sie jemals ENTSTEHT.
#
# Die Folge auf dem Knoten im Betrieb: kein lnd.conf, keine Freigabe, das
# Startskript im Container wartet ewig, die Oberflaeche meldet "wartet auf
# Einrichtung". Der ganze Lightning-Teil war damit unerreichbar -- Seed,
# Wallet, Wiederherstellung. Aufgefallen erst, als seine Kette durch war.


def _kettenlage(im_erstsync: bool) -> dict:
    return {"kette": "main", "hoehe": 966_088, "kopfzeilen": 966_088,
            "fortschritt": 0.6 if im_erstsync else 1.0,
            "im_erstsync": im_erstsync, "belegt_bytes": 1,
            "verbindungen_ein": 3, "verbindungen_aus": 10, "erreichbar": True,
            "blockzeit": 1_788_800_000, "adressen": [], "netze": {},
            "empfangen_bytes": 0, "gesendet_bytes": 0}


def test_vor_der_fertigen_kette_bleibt_lightning_unkonfiguriert(client,
                                                                monkeypatch):
    """LND legt ohne synchrone Kette weder Wallet noch Kanal an -- das ist
    LNDs Bedingung, nicht unsere. Vorher zu konfigurieren brauchte einen
    Dienst, der nur wartend Speicher belegt."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _kettenlage(True))
    client.app.state.einmal_nachsehen()
    assert not (client.tmp / "config" / "lnd.conf").exists()


def test_steht_die_kette_wird_lightning_eingerichtet(client, monkeypatch):
    """Der Test, der gefehlt hat."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _kettenlage(False))
    client.app.state.einmal_nachsehen()

    pfad = client.tmp / "config" / "lnd.conf"
    assert pfad.exists(), "ohne lnd.conf wartet der Container ewig"
    text = pfad.read_text()
    assert "alias=" in text and "minchansize=" in text
    # Und freigegeben -- ohne die Freigabe liegt die Datei nur da.
    assert (client.tmp / "config" / "lnd.ready").exists(), \
        "geschrieben, aber nie freigegeben: der Dienst startet trotzdem nicht"


def test_der_dienst_meldet_sich_danach_als_freigegeben(client, monkeypatch):
    """Was die Oberflaeche zeigt, ist genau das, was der Betreiber vermisst hat."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    vorher = {d["name"]: d["zustand"]
              for d in client.get("/api/status").json()["dienste"]}
    assert vorher["lnd"] == "unkonfiguriert"

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _kettenlage(False))
    client.app.state.einmal_nachsehen()
    nachher = {d["name"]: d["zustand"]
               for d in client.get("/api/status").json()["dienste"]}
    assert nachher["lnd"] == "freigegeben"


def test_die_gewaehlte_sichtbarkeit_landet_in_der_konfiguration(client,
                                                                monkeypatch):
    """Sie ist laengst beantwortet -- im Assistenten oder in den
    Einstellungen. Sie noch einmal zu erfragen waere eine Frage zu viel; sie
    zu ignorieren waere schlimmer."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": False,
        "externe_adresse": "meinknoten.example",
        "adresse_ankuendigen": True, "tor_pause_beim_abgleich": True,
        "sichtbarkeit": "still"})

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _kettenlage(False))
    client.app.state.einmal_nachsehen()
    text = (client.tmp / "config" / "lnd.conf").read_text()
    # "still" heisst: nicht ankuendigen. Weder Onion noch Clearnet.
    assert "externalip=" not in text


def test_lightning_wird_nicht_bei_jedem_durchgang_neu_geschrieben(client,
                                                                  monkeypatch):
    """Jede Aenderung startet LND neu. Bei einem Knoten mit offenen Kanaelen
    ist ein Neustart je Wachdurchgang nicht harmlos."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: _kettenlage(False))
    client.app.state.einmal_nachsehen()
    pfad = client.tmp / "config" / "lnd.conf"
    erste = pfad.read_text()
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()
    assert pfad.read_text() == erste


def test_jeder_dienst_hat_eine_stelle_die_ihn_freigibt():
    """Die Wache gegen genau diese Fehlerklasse.

    baue_lnd() war fertig, richtig und getestet -- und wurde von nirgendwo
    aufgerufen. Alle Tests prueften, wie die Datei AUSSAEHE, keiner, ob sie
    je entsteht. Ein Dienst, den niemand freigibt, wartet fuer immer, und die
    Oberflaeche sagt dazu wahrheitsgemaess "wartet auf Einrichtung".

    Deshalb hier nicht der Umweg ueber einen weiteren Einzelfall, sondern die
    Regel: fuer JEDEN Dienst in DIENSTE muss es im laufenden Code eine Stelle
    geben, die ihn schreibt UND eine, die ihn freigibt.
    """
    quelle = (Path(__file__).resolve().parents[1]
              / "satcortex" / "api.py").read_text(encoding="utf-8")
    fehlt = []
    for dienst in api.DIENSTE:
        if f'schreibe("{dienst}"' not in quelle:
            fehlt.append(f"{dienst}: niemand schreibt seine Konfiguration")
        if f'gib_frei("{dienst}")' not in quelle:
            fehlt.append(f"{dienst}: niemand gibt ihn frei")
    assert not fehlt, "; ".join(fehlt)


def test_jeder_konfigurationsbauer_wird_auch_benutzt():
    """Das Gegenstueck von der anderen Seite: eine baue_*-Funktion, die nur
    Tests aufrufen, ist toter Code mit einem Feature-Anschein."""
    nodeconfig_quelle = (Path(__file__).resolve().parents[1]
                         / "satcortex" / "nodeconfig.py").read_text(encoding="utf-8")
    api_quelle = (Path(__file__).resolve().parents[1]
                  / "satcortex" / "api.py").read_text(encoding="utf-8")
    bauer = re.findall(r"^def (baue_\w+)", nodeconfig_quelle, re.M)
    assert bauer, "keine baue_*-Funktion gefunden -- die Suche stimmt nicht mehr"

    # Der Text-Vergleich von frueher reichte nur, solange api.py jeden Bauer
    # selbst aufrief. Seit dem 09.09.2026 geht das Schreiben der lnd.conf
    # durch lnd_soll(), damit Erst- und Folgeschreiben dieselbe Datei
    # erzeugen -- baue_lnd waere damit faelschlich als tot gemeldet worden.
    #
    # Statt die Pruefung aufzuweichen, folgt sie jetzt dem Aufrufweg: welche
    # nodeconfig-Funktionen ruft api.py, und was rufen DIESE auf. Das ist
    # strenger als vorher, denn es entlarvt auch einen Bauer, den nur eine
    # ihrerseits tote Funktion benutzt.
    baum = ast.parse(nodeconfig_quelle)
    ruft = {k.name: {n.func.id for n in ast.walk(k)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            for k in baum.body if isinstance(k, ast.FunctionDef)}
    erreichbar = {f for f in ruft if f"nodeconfig.{f}(" in api_quelle}
    while True:
        weiter = {g for f in erreichbar for g in ruft.get(f, ()) if g in ruft}
        if weiter <= erreichbar:
            break
        erreichbar |= weiter

    unbenutzt = [b for b in bauer if b not in erreichbar]
    assert not unbenutzt, (
        "fertig gebaut und von nirgendwo aufgerufen: " + ", ".join(unbenutzt))


# ── Ein Block, aus der Sicht dieses Knotens ────────────────────────────────


def test_ein_unbekannter_block_ist_ein_ehrliches_404(client):
    _richte_ein(client)
    r = client.get("/api/auswertung/block/1")
    assert r.status_code == 404
    assert r.json()["detail"]["meldung"] == "block_unbekannt"


def test_zu_einem_block_kommen_die_transaktionen_mit_verweildauer(client):
    """Der Unterschied zu jedem Explorer: nicht "welche Transaktionen sind in
    dem Block", sondern "welche davon lagen vorher bei MIR und wie lange"."""
    from satcortex import store as st
    _richte_ein(client)
    # In dieselbe Datei schreiben, die die Anwendung benutzt.
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    for i, txid in enumerate(("aa" * 32, "bb" * 32)):
        ablage.tx_aufgenommen(txid, 1_000_000 + i * 1000, i)
    ablage.tx_bestaetigt(["aa" * 32, "bb" * 32], 966_088, 1_100_000)
    ablage.block_eingetragen({
        "hoehe": 966_088, "hash": "00" * 32, "blockzeit": 1_788_800_000,
        "empfangen_ms": 1_100_000, "gewicht": 3_980_000, "txzahl": 2_400,
        "gebuehren_sat": 1_234_000, "pool": "Foundry USA",
        "botschaft": "/Foundry USA Pool #dropgold/", "bekannte_tx": 2,
        "verweildauer_ms": 99_500})
    ablage.sichern()
    ablage.schliesse()

    d = client.get("/api/auswertung/block/966088").json()
    assert d["block"]["pool"] == "Foundry USA"
    assert d["block"]["botschaft"] == "/Foundry USA Pool #dropgold/"
    txe = d["transaktionen"]
    assert [x["txid"] for x in txe] == ["aa" * 32, "bb" * 32], \
        "die laengste Wartezeit gehoert nach oben"
    assert txe[0]["verweildauer_ms"] == 100_000


# ── Die Kacheln ────────────────────────────────────────────────────────────


def _mempool_roh(n=30):
    """Ein Mempool, wie getrawmempool ihn liefert -- absteigende Gebuehren."""
    raus = {}
    for i in range(n):
        satvb = 50.0 / (i + 1)
        vsize = 400
        raus["%064x" % i] = {
            "vsize": vsize, "ancestorsize": vsize,
            "fees": {"base": satvb * vsize / 1e8,
                     "ancestor": satvb * vsize / 1e8},
        }
    return raus


def _mempool_strom(monkeypatch, rpc_modul, gefragt=None, n=30, roh=None):
    """Die Attrappe fuer den STROM statt fuer den Aufruf am Stueck.

    Seit dem Befund vom 21.09.2026 liest der Kachelweg brocken() statt
    ruf(): bei vollem Mempool sprengte die ganze Antwort das Speicherlimit
    des Containers. Die Attrappe muss demselben Weg folgen, sonst prueft sie
    einen, den es nicht mehr gibt.
    """
    import json as _json

    def brocken(self, methode, *p, **kw):
        if gefragt is not None:
            gefragt.append(methode)
        if methode != "getrawmempool":
            raise rpc_modul.RpcFehler("unerwartet: " + methode)
        assert p == (True,), "ohne True fehlen Gebuehr und Groesse"
        text = _json.dumps({
            "result": _mempool_roh(n) if roh is None else roh,
            "error": None, "id": "satcortex"}).encode("utf-8")
        # In Stuecken, wie eine echte Leitung -- absichtlich klein, damit
        # der Parser ueber die Grenzen hinweg geprueft wird.
        for i in range(0, len(text), 997):
            yield text[i:i + 997]

    monkeypatch.setattr(rpc_modul.Knoten, "brocken", brocken)
    return brocken


def test_die_kacheln_kommen_aus_dem_eigenen_knoten(client, monkeypatch):
    """Nichts davon wird von aussen geholt -- Aus dem Betrieb, 08.09.2026: "jede
    info die wir brauchen kommt aus dem netzwerk und nicht von extern"."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    gefragt = []

    _mempool_strom(monkeypatch, rpc_modul, gefragt)
    d = client.get("/api/auswertung/mempool/kacheln").json()
    assert gefragt == ["getrawmempool"], "genau ein Aufruf, an den eigenen Knoten"
    assert d["gesamt"] == 30
    assert len(d["kacheln"]) == 30
    # Absteigend nach Gebuehr: die teuerste zuerst.
    assert d["kacheln"][0]["satvb"] > d["kacheln"][-1]["satvb"]
    assert all(k["block"] == 0 for k in d["kacheln"]), \
        "12 kB passen alle in den ersten Block"


def test_die_kacheln_werden_auf_bloecke_verteilt(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    # 6000 Stueck a 400 Byte = 2,4 MB, also drei Bloecke.
    roh = {"%064x" % i: {"vsize": 400, "ancestorsize": 400,
                         "fees": {"base": (6000 - i) * 400 / 1e8,
                                  "ancestor": (6000 - i) * 400 / 1e8}}
           for i in range(6000)}
    _mempool_strom(monkeypatch, rpc_modul, roh=roh)
    d = client.get("/api/auswertung/mempool/kacheln").json()
    assert [b["n"] for b in d["bloecke"]] == [0, 1, 2]
    assert sum(b["anzahl"] for b in d["bloecke"]) == 6000
    for b in d["bloecke"][:2]:
        assert 990_000 <= b["vsize"] <= 1_010_000, "ein Block fasst ~1 Mio. vByte"
    # Innerhalb eines Blocks faellt die Gebuehr, und Block 2 liegt unter 1.
    assert d["bloecke"][0]["tiefste"] > d["bloecke"][1]["hoechste"]


def test_die_kacheln_tragen_unseren_eigenen_zeitstempel(client, monkeypatch):
    """Die Zeile, die kein Explorer hat -- und sie kommt aus unserer Ablage,
    nicht aus dem Mempool."""
    from satcortex import rpc as rpc_modul
    from satcortex import store as st
    _richte_ein(client)
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    ablage.tx_aufgenommen("%064x" % 3, 1_700_000_000_000, 7)
    ablage.sichern()
    ablage.schliesse()

    _mempool_strom(monkeypatch, rpc_modul)
    d = client.get("/api/auswertung/mempool/kacheln").json()
    treffer = {k["txid"]: k["zuerst_ms"] for k in d["kacheln"]}
    assert treffer["%064x" % 3] == 1_700_000_000_000
    assert treffer["%064x" % 4] is None, \
        "was wir nie gesehen haben, bekommt keinen erfundenen Zeitstempel"


def test_ein_beschaeftigter_knoten_ist_kein_leerer_mempool(client, monkeypatch):
    """Ein Fehlschlag darf nicht als "der Mempool ist leer" durchgehen."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    def weg(self, m, *p, **kw):
        raise rpc_modul.NichtErreichbar("timeout")
        yield b""          # macht es zum Generator, wie brocken() einer ist

    monkeypatch.setattr(rpc_modul.Knoten, "brocken", weg)
    r = client.get("/api/auswertung/mempool/kacheln")
    assert r.status_code == 503
    assert r.json()["detail"]["meldung"] == "mempool_nicht_abrufbar"


def test_der_grosse_aufruf_wird_nicht_bei_jedem_blick_wiederholt(client,
                                                                 monkeypatch):
    """getrawmempool ist der groesste Aufruf dieser Anwendung. Ihn bei jedem
    Blick neu zu stellen waere Last ohne Gegenwert."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    zaehler = []
    _mempool_strom(monkeypatch, rpc_modul, zaehler)
    for _ in range(4):
        client.get("/api/auswertung/mempool/kacheln")
    assert zaehler == ["getrawmempool"], \
        "vier Blicke, EIN Aufruf -- der Rest kommt aus dem Zwischenspeicher"


def test_lightning_haengt_nicht_am_zehn_minuten_takt(client, monkeypatch):
    """Der Fehler, den Aus dem Betrieb, 08.09.2026 gemeldet hat: nach dem Update auf
    0.46.0 stand LND weiter auf "wartet auf Einrichtung".

    Zwei Ursachen, beide im Takt und nicht in der Logik. Der Waechter schlief
    nach jedem Neustart ERST zehn Minuten und arbeitete dann; und die
    Einrichtung stand hinter zwei Abbruechen, die mit Lightning nichts zu tun
    haben -- der Tor-Vorlage und der Adressnachfuehrung.

    Jetzt haengt sie am Sammler, der die Kettenlage ohnehin alle fuenf
    Sekunden holt.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "lage_mit_grund",
                        lambda *a, **kw: (_kettenlage(False), ""))
    client.app.state.lage_auffrischen()
    assert (client.tmp / "config" / "lnd.conf").exists(), \
        "der Sammler hat die Lage, also gehoert die Einrichtung dorthin"
    assert (client.tmp / "config" / "lnd.ready").exists()


def test_der_sammler_sieht_danach_nicht_mehr_auf_die_platte(client, monkeypatch):
    """Alle fuenf Sekunden eine Datei zu lesen, um festzustellen, dass sich
    nichts geaendert hat, ist Last ohne Gegenwert."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "lage_mit_grund",
                        lambda *a, **kw: (_kettenlage(False), ""))
    client.app.state.lage_auffrischen()
    pfad = client.tmp / "config" / "lnd.conf"
    erste = pfad.read_text()

    # Der Merker im Speicher muss genuegen: alle fuenf Sekunden eine Datei zu
    # lesen, um festzustellen, dass sich nichts geaendert hat, ist Last ohne
    # Gegenwert. Geprueft ueber die Schreibzeit -- wird nicht geschrieben,
    # war auch nichts zu tun.
    stand = pfad.stat().st_mtime_ns
    for _ in range(5):
        client.app.state.lage_auffrischen()
    assert pfad.read_text() == erste
    assert pfad.stat().st_mtime_ns == stand, "die Datei wurde erneut geschrieben"


def test_bei_vollem_mempool_bekommt_jeder_block_kacheln(client, monkeypatch):
    """Der Fehler, den Aus dem Betrieb, 08.09.2026 im Bild hatte: Block 6 war
    ausgewaehlt, die Spalte leer und die Liste darunter leer.

    Die Obergrenze fuer Kacheln galt ueber ALLE Bloecke. Bei seinen 31.716
    wartenden Transaktionen war sie nach sechs Spalten aufgebraucht, und die
    letzten Bloecke standen als leere Rahmen da -- mit Kopfzeile und
    Gebuehrenspanne, aber ohne Inhalt.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    # 30.000 Stueck a 400 Byte = 12 MB, also zwoelf Bloecke.
    roh = {"%064x" % i: {"vsize": 400, "ancestorsize": 400,
                         "fees": {"base": (30000 - i) * 400 / 1e8,
                                  "ancestor": (30000 - i) * 400 / 1e8}}
           for i in range(30000)}
    _mempool_strom(monkeypatch, rpc_modul, roh=roh)
    d = client.get("/api/auswertung/mempool/kacheln").json()

    for b in d["bloecke"]:
        eigene = [k for k in d["kacheln"] if k["block"] == b["n"]]
        assert eigene, f"Block {b['n']} hat keine einzige Kachel"
        # Und die Flaechen muessen zusammen den Block fuellen -- sonst
        # zeichnet der Treemap eine halb leere Spalte.
        assert sum(k["vsize"] for k in eigene) == b["vsize"], \
            f"Block {b['n']}: Flaeche stimmt nicht"


def test_was_ueber_die_grenze_geht_wird_zusammengefasst(client, monkeypatch):
    """Nicht weggelassen, sondern gebuendelt: sonst fehlte der Spalte
    Flaeche, und der Block saehe kleiner aus als er ist."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    roh = {"%064x" % i: {"vsize": 200, "ancestorsize": 200,
                         "fees": {"base": (9000 - i) * 200 / 1e8,
                                  "ancestor": (9000 - i) * 200 / 1e8}}
           for i in range(9000)}          # 1,8 MB, aber 5000 im ersten Block
    _mempool_strom(monkeypatch, rpc_modul, roh=roh)
    d = client.get("/api/auswertung/mempool/kacheln").json()

    reste = [k for k in d["kacheln"] if k.get("rest")]
    assert reste, "ueber der Grenze gehoert eine Restkachel"
    assert d["gekuerzt"] is True
    for r in reste:
        assert r["anzahl"] > 0 and r["vsize"] > 0


def test_ein_alter_block_kommt_aus_der_kette(client, monkeypatch):
    """Aus dem Betrieb, 08.09.2026: "und wie find ich jetzt satoshis nachricht??"

    Die Blockansicht wirbt in ihrem eigenen Erklaertext damit ("im
    allerersten Block steht dort die Schlagzeile, mit der alles anfing") und
    kannte doch nur die zwoelf letzten. Ein Versprechen, das die Oberflaeche
    selbst gibt und nicht einloest.

    Die KETTE kennt ihn -- vollstaendig und un-pruned. Danach zu fragen ist
    der halbe Sinn eines Archiv-Knotens.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    # Die Coinbase des Genesis-Blocks, wortwoertlich aus der Kette.
    genesis = ("04ffff001d0104455468652054696d65732030332f4a616e2f3230303920"
               "4368616e63656c6c6f72206f6e206272696e6b206f66207365636f6e6420"
               "6261696c6f757420666f722062616e6b73")

    def ruf(self, methode, *p, **kw):
        if methode == "getblockhash":
            assert p[0] == 0
            return "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
        if methode == "getblock":
            return {"height": 0, "time": 1231006505, "weight": 1140, "nTx": 1,
                    "coinbase_tx": {"coinbase": genesis}}
        if methode == "getblockstats":
            return {"totalfee": 0}
        raise rpc_modul.RpcFehler("unerwartet: " + methode)

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", ruf)
    d = client.get("/api/auswertung/block/0").json()
    assert d["aus_kette"] is True
    assert d["block"]["botschaft"] == (
        "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"), \
        "das fuehrende 'E' ist das Laengenbyte 0x45 und gehoert nicht dazu"
    # Was wir nicht wissen koennen, behaupten wir auch nicht.
    assert d["block"]["bekannte_tx"] is None
    assert d["block"]["verweildauer_ms"] is None
    assert d["transaktionen"] == []


def test_eine_unsinnige_hoehe_wird_abgewiesen(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    def weg(self, m, *p, **kw):
        raise rpc_modul.RpcFehler("Block height out of range")

    monkeypatch.setattr(rpc_modul.Knoten, "ruf", weg)
    r = client.get("/api/auswertung/block/99999999")
    assert r.status_code == 404
    assert r.json()["detail"]["meldung"] == "block_unbekannt"


# ═══════════════════════════════════ die Sichtbarkeit wirkt wirklich ═══
#
# Aus dem Betrieb, 09.09.2026, bevor er umgestellt hat: "wichtiger ist, wenn ich
# spaeter mal sage ich will nur noch tor, ob das dann alles auch noch
# funktioniert?" Die ehrliche Antwort war NEIN.
#
# lnd.conf wurde genau einmal geschrieben. Danach flickte nur noch das
# Adressnachfuehren an den externalip-Zeilen -- und auch das nur, solange
# "adresse_ankuendigen" AN war. Wer auf "nur ueber Tor" umstellte, setzte
# genau dieses Haekchen auf aus und schnitt sich den einzigen Weg ab, auf
# dem die Aenderung angekommen waere. Der Schalter stand auf "nur ueber
# Tor", und der Knoten kuendigte weiter die Wohnanschrift an.

NETZWEGE = {"tor": True, "ipv4": True, "ipv6": False,
            "externe_adresse": "203.0.113.7", "adresse_ankuendigen": True,
            "tor_pause_beim_abgleich": True, "sichtbarkeit": "hybrid",
            "rpc_heimnetz": ""}


def _lnd_conf(client, monkeypatch):
    """Eingerichtet, Kette steht, lnd.conf geschrieben."""
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _kettenlage(False))
    client.app.state.einmal_nachsehen()
    pfad = client.tmp / "config" / "lnd.conf"
    assert pfad.exists()
    return pfad


def test_die_sichtbarkeit_kommt_bei_lightning_wirklich_an(client, monkeypatch):
    pfad = _lnd_conf(client, monkeypatch)

    r = client.post("/api/knoten/netzwege", json=NETZWEGE)
    assert r.status_code == 200, r.text
    text = pfad.read_text()
    assert "externalip=203.0.113.7:9735" in text, \
        "hybrid kuendigt die eigene Adresse an -- mit Port"
    assert "tor.skip-proxy-for-clearnet-targets=true" in text

    r = client.post("/api/knoten/netzwege",
                    json={**NETZWEGE, "sichtbarkeit": "tor"})
    assert r.status_code == 200, r.text
    text = pfad.read_text()
    assert "externalip=" not in text, \
        "GENAU der Fehler: der Schalter stand auf Tor, die IP stand weiter drin"
    assert "tor.skip-proxy-for-clearnet-targets=false" in text
    assert "tor.streamisolation=true" in text


def test_der_rueckweg_wirkt_genauso(client, monkeypatch):
    """Der war ebenso kaputt: das Nachfuehren verglich gegen die
    bitcoind-Konfiguration und meldete "nichts geaendert", waehrend Lightning
    seine Adresse nie bekam."""
    pfad = _lnd_conf(client, monkeypatch)
    client.post("/api/knoten/netzwege",
                json={**NETZWEGE, "sichtbarkeit": "tor"})
    assert "externalip=" not in pfad.read_text()

    client.post("/api/knoten/netzwege", json=NETZWEGE)
    assert "externalip=203.0.113.7:9735" in pfad.read_text()


def test_ohne_echte_aenderung_startet_lnd_nicht_neu(client, monkeypatch):
    """Die Falle, die beim Bauen zuerst auffiel.

    baue_lnd stempelt jede Fassung mit ihrem Erzeugungszeitpunkt. Ein
    Vergleich ueber den rohen Text waere immer verschieden gewesen -- LND
    waere bei jedem Durchgang neu gestartet, und bei abgeschaltetem
    Auto-Entsperren spraenge dabei jedes Mal die Wallet zu. Aus einem
    Abgleich waere ein Dauerausfall geworden.
    """
    _lnd_conf(client, monkeypatch)
    erst = client.post("/api/knoten/netzwege", json=NETZWEGE).json()
    assert erst["lightning_neustart"] is True
    zweit = client.post("/api/knoten/netzwege", json=NETZWEGE).json()
    assert zweit["lightning_neustart"] is False, \
        "zweimal dasselbe gespeichert darf LND nicht anhalten"


def test_ein_dns_aussetzer_haelt_den_knoten_nicht_an(client, monkeypatch):
    """Ein Netzwackler von Sekunden darf keine Adresse loeschen.

    Ohne die Regel wuerde eine voruebergehend gescheiterte Aufloesung die
    externalip entfernen, LND neu starten und die Wallet zusperren.
    """
    from satcortex import dyndns as dyndns_modul
    pfad = _lnd_conf(client, monkeypatch)
    client.post("/api/knoten/netzwege", json=NETZWEGE)
    assert "externalip=203.0.113.7:9735" in pfad.read_text()

    # Und jetzt faellt die Aufloesung aus, waehrend sonst alles gleich bleibt.
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda _n: [])
    r = client.post("/api/knoten/netzwege", json=NETZWEGE)
    assert r.status_code == 200, r.text
    assert "externalip=" in pfad.read_text(), \
        "der Aussetzer hat die angekuendigte Adresse mitgenommen"


def test_still_kuendigt_nichts_an(client, monkeypatch):
    pfad = _lnd_conf(client, monkeypatch)
    client.post("/api/knoten/netzwege", json=NETZWEGE)
    client.post("/api/knoten/netzwege",
                json={**NETZWEGE, "sichtbarkeit": "still"})
    text = pfad.read_text()
    assert "externalip=" not in text
    assert "tor.v3=false" in text, "ohne v3 entsteht gar kein versteckter Dienst"


def test_der_entsperrweg_ueberlebt_den_wechsel(client, monkeypatch):
    """Wer die Betriebsart wechselt, darf nicht nebenbei sein
    Auto-Entsperren verlieren -- der Knoten stuende nach dem naechsten
    Stromausfall still, ohne dass jemand wuesste warum."""
    from satcortex import services
    pfad = _lnd_conf(client, monkeypatch)
    ablage = services.Konfigurationsablage(str(client.tmp / "config"))
    ablage.schreibe("lnd", nodeconfig.setze_entsperrdatei(
        pfad.read_text(), "/fast/lnd/wallet.pass"))

    client.post("/api/knoten/netzwege",
                json={**NETZWEGE, "sichtbarkeit": "tor"})
    assert nodeconfig.lies_entsperrdatei(pfad.read_text()) == \
        "/fast/lnd/wallet.pass"


# ═════════════ das Passwort kennt der Nutzer -- immer ══════════════════
#
# Aus dem Betrieb, 09.09.2026: "wenn ich auch das auto entsperren aktiviere sollte
# ich das passwort selbst gewaehlt haben oder es mir wenigstens anzeigen
# lassen". Bis dahin stand in wallet_passwort:
#
#     if automatisch:
#         return secrets.token_urlsafe(32)
#
# Die Anwendung wuerfelte also eines, schrieb es neben die Wallet und zeigte
# es NIE an -- auch spaeter nicht. Die Folge ist groesser als die
# Unbequemlichkeit: geht wallet.pass verloren, waehrend die Wallet bleibt,
# ist sie zu, und NIEMAND kann sie oeffnen. Es hilft dann nur der Seed und
# eine vollstaendige Wiederherstellung.
#
# Der Schalter entscheidet jetzt nur noch, WO das Passwort liegt. Nicht mehr,
# wer es kennt.

def test_auch_beim_auto_entsperren_gilt_das_gewaehlte_passwort(client, lnd_da):
    import base64
    from satcortex import lnd as lnd_modul
    _richte_ein(client)
    d = _seed(client)
    r = client.post("/api/lightning/wallet",
                    json=_antworten(d, automatisch_entsperren=True))
    assert r.status_code == 200, r.text

    an_lnd = base64.b64decode(lnd_da.angelegt["wallet_password"]).decode()
    assert an_lnd == WALLET_PASSWORT, "es darf nichts gewuerfelt werden"
    auf_platte = lnd_modul.passwortdatei(str(client.tmp / "fast")).read_bytes()
    assert auf_platte == WALLET_PASSWORT.encode(), \
        "auf der Platte muss dasselbe stehen, das der Nutzer kennt"


def test_ohne_passwort_gibt_es_auch_mit_auto_entsperren_keine_wallet(client,
                                                                    lnd_da):
    """Vorher fuellte die Anwendung die Luecke still mit einem gewuerfelten
    Passwort -- und legte damit eine Wallet an, die ihr Besitzer nicht
    oeffnen kann, sobald eine Datei fehlt."""
    _richte_ein(client)
    d = _seed(client)
    leib = _antworten(d, automatisch_entsperren=True)
    leib["passwort"] = ""
    r = client.post("/api/lightning/wallet", json=leib)
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "passwort_zu_kurz"
    assert lnd_da.angelegt is None, "trotz fehlendem Passwort angelegt"


def test_auch_die_wiederherstellung_wuerfelt_nichts(client, lnd_da):
    """Dieselbe Entscheidung an der zweiten Stelle -- sie darf nicht an zwei
    Orten anders ausfallen."""
    _richte_ein(client)
    r = client.post("/api/lightning/wiederherstellen",
                    json={"woerter": WOERTER, "passwort": "",
                          "automatisch_entsperren": True})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "passwort_zu_kurz"


# ═══════════════════ was jetzt zu tun ist -- und wann nicht ════════════
#
# Aus dem Betrieb, 09.09.2026, nach dem Neustart von LND: "in der uebersicht steht
# das lnd laeuft aber nix vom wallet ... auf kanaele steht dass das wallet
# bereit ist aber gesperrt ist (aber nicht wo ich es entsperren kann..) und
# bei wallet werde ich aufgefordert das wallet passwort einzugeben."
#
# Der Zustand stand dort, wo man nicht handeln kann, und das Handeln dort,
# wo man nicht hinsieht. Und seine Bedingung dazu: "wenn alles da, muss man
# ja nicht mehr sehen was zu tun ist".

def _mit_kette(client, monkeypatch):
    from satcortex import rpc as rpc_modul
    monkeypatch.setattr(rpc_modul, "lage_mit_grund",
                        lambda *a, **kw: (_kettenlage(False), ""))
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _kettenlage(False))


def _schritt(client):
    return client.get("/api/status").json().get("naechster_schritt")


def test_ohne_wallet_fuehrt_die_uebersicht_zur_wallet(client, lnd_da,
                                                      monkeypatch):
    """Befund 1: dass ueberhaupt zuerst eine Wallet noetig ist, stand in
    genau einem Satz -- ausgerechnet unter Lightning -> Knoten."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    d = _schritt(client)
    assert d and d["was"] == "wallet_anlegen"
    assert d["ansicht"] == "ln-einrichtung", "der Hinweis muss auch hinfuehren"


def test_eine_gesperrte_wallet_ist_dringend(client, lnd_da, monkeypatch):
    """Befund 12: die Uebersicht meldete "LND laeuft", waehrend der Knoten
    stillstand und nichts weiterleitete."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "LOCKED"
    d = _schritt(client)
    assert d and d["was"] == "wallet_entsperren"
    assert d["dringend"] is True, "ein stillstehender Knoten wiegt schwerer"


def test_steht_alles_gibt_es_keinen_hinweis(client, lnd_da, monkeypatch):
    """Die Bedingung des Betreibers, woertlich. Kein Dauerbanner."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    # Direkt in den Zustand: der Endpunkt laedt beim Einrichten wirklich
    # eine Sicherung hoch, und hier geht es um die Fuehrung, nicht um das
    # Ziel.
    from satcortex import state
    state.Ablage(str(client.tmp / "config")).merke_sicherungsziel(
        {"url": "https://wolke.example/dav/", "benutzer": "ich"})
    assert _schritt(client) is None


def test_ohne_sicherungsziel_wird_daran_erinnert(client, lnd_da, monkeypatch):
    """Vor dem ersten Kanal, nicht danach: ohne Sicherung sind die
    Kanal-Guthaben bei Datenverlust weg -- auch mit dem Zettel in der Hand."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    d = _schritt(client)
    assert d and d["was"] == "sicherungsziel"


def _mit_sicherung_und_kanal(client, monkeypatch, tuerme):
    """Sicherungsziel steht, ein Anker-Kanal ist offen -- uebrig bleibt nur
    die Frage nach dem Wachturm."""
    from satcortex import api as api_modul, state
    state.Ablage(str(client.tmp / "config")).merke_sicherungsziel(
        {"url": "https://wolke.example/dav/", "benutzer": "ich"})
    kanal = {"aktiv": True, "gegenstelle": "", "kennung": KENNUNG_TURM,
             "punkt": "", "nummer": "1", "kapazitaet": 1_000_000, "hier": 0,
             "reserve": 0, "verfuegbar": 0, "drueben": 0, "anteil_hier": 0.0,
             "privat": False, "sitzungsart": "ANCHOR", "gesendet": 0,
             "empfangen": 0, "laufzeit_s": 0, "erreichbar_s": 0}
    monkeypatch.setattr(api_modul.lnd, "kanaele", lambda k: [kanal])
    monkeypatch.setattr(api_modul.lnd, "wachtuerme",
                        lambda k, eigen="": tuerme)


def test_ein_turm_ohne_sitzung_laesst_den_hinweis_stehen(client, lnd_da,
                                                          monkeypatch):
    """Eingetragen ist nicht bewacht. Bis zum 14.09.2026 verschwand der
    Hinweis, sobald irgendein Turm in der Liste stand -- auch einer, der nie
    erreichbar war."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    _mit_sicherung_und_kanal(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "adressen": ["t.onion:9911"],
         "arten": {}, "sitzungen": 0}])
    d = _schritt(client)
    assert d and d["was"] == "wachturm"


def test_ein_turm_mit_sitzung_beendet_den_hinweis(client, lnd_da, monkeypatch):
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    _mit_sicherung_und_kanal(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "adressen": ["t.onion:9911"], "sitzungen": 1,
         "arten": {"ANCHOR": {"sitzungen": 1, "nutzbar": 1, "bestaetigt": 0,
                              "ausstehend": 0}}}])
    assert _schritt(client) is None


def test_waehrend_des_erstabgleichs_gibt_es_nichts_zu_tun(client, lnd_da,
                                                          monkeypatch):
    from satcortex import rpc as rpc_modul
    _richte_ein(client)
    monkeypatch.setattr(rpc_modul, "lage_mit_grund",
                        lambda *a, **kw: (_kettenlage(True), ""))
    assert _schritt(client) is None, "warten ist keine Aufgabe"


def test_vor_der_einrichtung_fuehrt_der_assistent(client):
    assert _schritt(client) is None


# ═══════════════════════ der Knoten bekommt einen Namen ════════════════
#
# Aus dem Betrieb, 09.09.2026: "ich moechte nicht das alles immer nur
# satoshicortex heisst!!"
#
# Er hatte recht, und es war peinlich: alias stand als Vorgabe in einer
# Datenklasse, und lightning_bereitstellen uebergab ihn NIE. In der ganzen
# Oberflaeche gab es kein einziges Eingabefeld dafuer. Jeder Knoten, den
# irgendwer je mit dieser Software aufsetzt, hiess "SatoshiCortex".

def test_ohne_eigene_wahl_steht_die_vorgabe_da(client):
    d = client.get("/api/lightning/name").json()
    assert d["alias"] == nodeconfig.ALIAS_VORGABE
    assert d["farbe"] == nodeconfig.FARBE_VORGABE


def test_der_gewaehlte_name_landet_in_der_lnd_conf(client, monkeypatch):
    pfad = _lnd_conf(client, monkeypatch)
    r = client.post("/api/lightning/name",
                    json={"alias": "dem Knoten im Betrieb", "farbe": "#3355FF"})
    assert r.status_code == 200, r.text
    text = pfad.read_text()
    assert "alias=dem Knoten im Betrieb" in text
    assert "color=#3355ff" in text, "Farben werden klein geschrieben"
    assert r.json()["lightning_neustart"] is True


def test_der_name_ueberlebt_das_nachziehen_der_wege(client, monkeypatch):
    """Sonst waere er beim naechsten Speichern der Netzwege wieder weg."""
    pfad = _lnd_conf(client, monkeypatch)
    client.post("/api/lightning/name", json={"alias": "dem Knoten im Betrieb"})
    client.post("/api/knoten/netzwege", json=NETZWEGE)
    assert "alias=dem Knoten im Betrieb" in pfad.read_text()


def test_ein_zu_langer_alias_wird_abgewiesen(client):
    """32 BYTE, nicht 32 Zeichen -- durch den Gossip passt nicht mehr."""
    r = client.post("/api/lightning/name", json={"alias": "ä" * 20})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "name_ungueltig"


def test_ein_alias_mit_zeilenumbruch_kommt_nicht_durch(client):
    """Sonst liesse sich an eine Konfigurationszeile jede beliebige weitere
    anhaengen -- etwa eine, die das Wallet-Passwort aus einer Datei liest."""
    # Kurz genug, dass die Laengenpruefung NICHT schon greift -- sonst
    # bewiese der Test nur, dass 33 Zeichen zu viele sind.
    r = client.post("/api/lightning/name", json={"alias": "brav\nx=1"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "name_ungueltig"


def test_eine_unsinnige_farbe_wird_abgewiesen(client):
    r = client.post("/api/lightning/name",
                    json={"alias": "gut", "farbe": "blau"})
    assert r.status_code == 400


# ═══════════════════ sich anschliessen, ohne Geld zu bewegen ═══════════
#
# Aus dem Betrieb, 09.09.2026: "man will sich ja nicht nur ein kanal oder knoten
# erstellen sondern sich auch einen anschliessen." Befund 20: das Recht
# peers:write lag seit jeher im Macaroon -- benutzt hat es nie jemand.

def test_eine_unbrauchbare_adresse_ist_kein_ausfall(client, lnd_da):
    """Der Unterschied gehoert in die Antwort, sonst sucht man den Fehler
    an der falschen Stelle."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/verbinden",
                    json={"adresse": "kein-at-zeichen"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "gegenstelle_abgelehnt"
    assert lnd_da.verbunden is None, "trotz unbrauchbarer Adresse gefragt"


def test_ein_wachturm_laesst_sich_austragen(client, lnd_da):
    """Sonst waechst die Liste endlos -- oeffentliche Turmlisten sind voller
    Tuerme, die es nicht mehr gibt."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    kennung = "03" + "ff" * 32          # gewoehnliches base64 enthielte "/"
    r = client.post("/api/lightning/wachtuerme/entfernen",
                    json={"kennung": kennung})
    assert r.status_code == 200, r.text
    assert r.json()["kennung"] == kennung
    praefix = "/v2/watchtower/client/"
    assert lnd_da.ausgetragen.startswith(praefix)
    assert "/" not in lnd_da.ausgetragen[len(praefix):]


def test_offene_kanalstaende_sind_ein_noch_nicht(client, lnd_da):
    """wtdb/client_db.go: ErrTowerUnackedUpdates. Kein Fehler, sondern ein
    "noch nicht" -- und so steht es dann auch da."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.austragfehler = "500: tower has unacked updates"
    r = client.post("/api/lightning/wachtuerme/entfernen",
                    json={"kennung": "03" + "ab" * 32})
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "wachturm_offene_staende"


def test_eine_kaputte_turmkennung_geht_nicht_an_lnd(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/wachtuerme/entfernen",
                    json={"kennung": "keine-kennung"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "wachturm_nicht_entfernt"
    assert lnd_da.ausgetragen is None


def test_eine_gute_adresse_geht_an_lnd(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/verbinden",
                    json={"adresse": "02aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.onion:9735"})
    assert r.status_code == 200, r.text
    # Seit dem 19.09.2026 wird die Kennung geprueft, BEVOR LND gefragt wird:
    # ein Lightning-Schluessel hat immer 66 Hexzeichen. Vorher ging jede
    # Zeichenkette durch und LND antwortete mit einer gRPC-Meldung.
    assert lnd_da.verbunden["addr"] == {"pubkey": "02aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                                        "host": "example.onion:9735"}
    assert lnd_da.verbunden["perm"] is False


def test_ohne_laufendes_lightning_wird_gar_nicht_erst_gefragt(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    r = client.post("/api/lightning/verbinden",
                    json={"adresse": "02aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.onion:9735"})
    assert r.status_code == 409


def test_das_verbinden_oeffnet_keinen_kanal(client, lnd_voll, tmp_path):
    """Sich verbinden und einen Kanal oeffnen sind zwei verschiedene Dinge.

    Bis zum 15.09.2026 durchsuchte dieser Test die Routenliste der App nach
    "kanal/oeffnen". Nachgemessen: dort stand keine einzige /api/lightning-
    Route -- er war immer gruen und pruefte nichts. Seine Aussage ("es gibt
    keinen Endpunkt, der einen Kanal oeffnet") stimmte seit dem 12.09.2026
    ohnehin nicht mehr.

    Geprueft wird jetzt am Verhalten: das Verbinden erreicht LND, und ein
    Kanal wird dabei nicht geoeffnet. Dass das Oeffnen selbst hinter der PIN
    steht, haelt test_die_pin_steht_vor_dem_kanal fest.
    """
    _richte_ein(client)
    lnd_voll.macaroons = tmp_path / "macaroons"
    lnd_voll.macaroons.mkdir(exist_ok=True)
    r = client.post("/api/lightning/verbinden",
                    json={"adresse": "02aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.onion:9735"})
    assert r.status_code == 200, r.text
    assert "/v1/peers" in lnd_voll.gefragt
    assert lnd_voll.geoeffnet is None


def test_der_sicherungs_hinweis_laesst_sich_wegnehmen(client, lnd_da,
                                                      monkeypatch):
    """Aus dem Betrieb, 09.09.2026: "das aufmerksam machen auf die kanal sicherung
    nervt! ... das sollten wir dem kunden ueberlassen, es sollte keine
    pflicht sein!"

    Er hat recht. Die anderen Hinweise verschwinden von allein, sobald man
    sie erledigt -- dieser beschreibt eine WAHL, und eine Wahl, die man
    taeglich neu wegklicken muss, ist keine.
    """
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    assert _schritt(client)["was"] == "sicherungsziel"
    assert _schritt(client)["abweisbar"] is True

    assert client.post("/api/hinweis/abweisen",
                       json={"was": "sicherungsziel"}).status_code == 200
    assert _schritt(client) is None


def test_ein_zustand_laesst_sich_nicht_wegklicken(client, lnd_da, monkeypatch):
    """Eine gesperrte Wallet verschwindet, wenn man sie ENTSPERRT."""
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "LOCKED"
    assert _schritt(client).get("abweisbar") is not True
    r = client.post("/api/hinweis/abweisen",
                    json={"was": "wallet_entsperren"})
    assert r.status_code == 400
    assert _schritt(client)["was"] == "wallet_entsperren"


def test_das_wegnehmen_ueberdauert_einen_neustart(client, lnd_da, monkeypatch):
    _richte_ein(client)
    _mit_kette(client, monkeypatch)
    lnd_da.stand = "SERVER_ACTIVE"
    client.post("/api/hinweis/abweisen", json={"was": "sicherungsziel"})
    zweiter = _client(client.tmp)
    from satcortex import api as api_modul
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: lnd_da)
    _mit_kette(zweiter, monkeypatch)
    assert zweiter.get("/api/status").json().get("naechster_schritt") is None


# ═══════════════════════ die Wallet wieder loswerden ═══════════════════
#
# Aus dem Betrieb, 09.09.2026: "mach es dann moeglich ein wallet zu loeschen mit
# dem wallet passwort zum entsperren ... dann kann ich die ganze
# initialisierung nochmal machen und testen."
#
# Sein Riegel ist der richtige: bei abgeschaltetem Auto-Entsperren liegt das
# Wallet-Passwort NIRGENDS auf der Platte. Er verlangt aber einen Umweg --
# LND kann es nur beim Entsperren pruefen, also nur an einer GESPERRTEN
# Wallet. Ein Passwortfeld, das nichts prueft, waere eine Attrappe.

def _tilgung(client, **mehr):
    leib = {"passwort": WALLET_PASSWORT, "alias": nodeconfig.ALIAS_VORGABE}
    leib.update(mehr)
    return client.post("/api/lightning/wallet/loeschen", json=leib)


def test_ohne_gesperrte_wallet_wird_nicht_geloescht(client, lnd_da):
    """Sonst waere das Passwortfeld eine Attrappe: an einer laufenden Wallet
    kann LND es gar nicht pruefen."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = _tilgung(client)
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "wallet_erst_sperren"


def test_ein_falsches_passwort_loescht_nichts(client, lnd_da, tmp_path):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    lnd_da.entsperrfehler = True
    (tmp_path / "fast" / "lnd").mkdir(parents=True, exist_ok=True)
    zeuge = tmp_path / "fast" / "lnd" / "wallet.db"
    zeuge.write_text("meine wallet")

    r = _tilgung(client, passwort="falsch-aber-lang-genug")
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "passwort_falsch"
    assert zeuge.exists(), "trotz falschem Passwort geloescht"


def test_ein_falscher_alias_loescht_nichts(client, lnd_da):
    """Die Bremse: er zwingt dazu, kurz hinzusehen."""
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    r = _tilgung(client, alias="irgendwas")
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "alias_stimmt_nicht"
    assert lnd_da.entsperrt is None, "das Passwort wurde trotzdem geprueft"


def test_mit_beidem_richtig_wird_getilgt(client, lnd_da, tmp_path,
                                          monkeypatch):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    lnd_dir = tmp_path / "fast" / "lnd"
    lnd_dir.mkdir(parents=True, exist_ok=True)
    (lnd_dir / "wallet.db").write_text("meine wallet")

    # Der Hintergrundlauf wartet sonst darauf, dass LND wirklich verschwindet.
    from satcortex import api as api_modul
    monkeypatch.setattr(api_modul.lnd, "zustand",
                        lambda _k: {"da": False, "stand": "aus", "roh": None})

    assert _tilgung(client).status_code == 409, \
        "mit vorgetaeuschtem 'aus' darf gar nicht erst geloescht werden"


def test_mit_auto_entsperren_laesst_sich_nicht_sperren(client, lnd_da,
                                                        tmp_path):
    """Mit Auto-Entsperren entsperrt LND sich beim Start selbst -- ein
    Neustart braechte nichts, und ein Knopf, der nichts bewirkt, ist
    schlimmer als keiner."""
    from satcortex import lnd as lnd_modul
    _richte_ein(client)
    ziel = lnd_modul.passwortdatei(str(tmp_path / "fast"))
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("gewuerfelt")
    r = client.post("/api/lightning/wallet/sperren")
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "auto_entsperren_an"


# ── Die lnd.conf holt ihre Adresse selbst nach ─────────────────────────────
#
# Aus dem Betrieb, 10.09.2026: unter "Knoten" blieb die Verbindungsadresse leer,
# obwohl in den Einstellungen alles stand -- Sichtbarkeit "Tor und Clearnet",
# eigene Adresse eingetragen, und bitcoind kuendigte sie nachweislich an
# ("Angekuendigt wird zurzeit: 78.223.248.60, ...onion").
#
# Der Grund war eine Bedingung, die auf der falschen Seite haengt:
#
#     if not soll or not dyndns.hat_sich_geaendert(vorhanden, soll):
#         return False
#     ablage.schreibe("bitcoind", ...)
#     lightning_adresse_nachziehen(soll)          <-- nur hier
#
# hat_sich_geaendert() vergleicht mit der BITCOIND-Konfiguration. Steht die
# Adresse dort schon, steigt die Funktion aus -- und LND wird nie angefasst.
# Fehlt die Adresse in der lnd.conf, bleibt sie fuer immer fehlend, egal wie
# lange man wartet. Dieselbe Fehlerklasse wie Befund 9: der Lightning-Weg
# haengt an einer Bedingung, die bitcoind betrifft.

def _lightning_lage(hoehe=966_370):
    return {"kette": "main", "hoehe": hoehe, "kopfzeilen": hoehe,
            "fortschritt": 1.0, "im_erstsync": False, "belegt_bytes": 1,
            "verbindungen_ein": 3, "verbindungen_aus": 8, "erreichbar": True,
            "blockzeit": 1_800_000_000, "adressen": [], "netze": {},
            "empfangen_bytes": 0, "gesendet_bytes": 0}


def _mit_lightning(client, monkeypatch, adresse="203.0.113.9"):
    """Ein eingerichteter Knoten mit fertiger Kette und geschriebener
    lnd.conf -- der Zustand, in dem der Betreiber stand."""
    from satcortex import dyndns as dyndns_modul
    from satcortex import rpc as rpc_modul
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda namen: list(namen))
    monkeypatch.setattr(rpc_modul, "kettenlage",
                        lambda _k, *_a: _lightning_lage())
    _richte_ein(client, externe_adresse=adresse)
    client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": False,
        "externe_adresse": adresse, "adresse_ankuendigen": True,
        "sichtbarkeit": "hybrid"})
    client.app.state.einmal_nachsehen()
    return client.tmp / "config" / "lnd.conf"


def test_die_lnd_conf_bekommt_die_adresse_auch_nachtraeglich(
        client, monkeypatch):
    """Der Fall von dem Knoten im Betrieb: bitcoind hat die Adresse, LND nicht.

    Ohne den Waechter bliebe das fuer immer so -- und unter "Knoten" stuende
    ewig ein leerer Kasten.
    """
    lnd_conf = _mit_lightning(client, monkeypatch)
    assert lnd_conf.exists(), "lnd.conf wurde gar nicht erst geschrieben"

    # Die Adresse von Hand herausnehmen -- genau die Lage, in der er stand.
    ohne = "\n".join(z for z in lnd_conf.read_text().splitlines()
                     if not z.strip().startswith("externalip="))
    lnd_conf.write_text(ohne, encoding="utf-8")
    # Dieselbe Pruefung wie beim Herausnehmen: Zeilen, die mit externalip=
    # BEGINNEN. Die Turm-Zeile watchtower.externalip= ist eine andere und
    # bleibt zu Recht stehen -- die blosse Zeichenfolge traefe sie mit.
    assert not any(z.strip().startswith("externalip=")
                   for z in lnd_conf.read_text().splitlines())

    # bitcoind.conf bleibt unveraendert -- es gibt also nichts, was sich
    # "geaendert" haette. Genau daran haengt der Fehler.
    client.app.state.einmal_nachsehen()

    assert "externalip=203.0.113.9:9735" in lnd_conf.read_text(), (
        "die lnd.conf holt ihre Adresse nicht nach, solange bitcoind "
        "zufrieden ist")


def test_ein_zweiter_durchgang_schreibt_die_lnd_conf_nicht_noch_einmal(
        client, monkeypatch):
    """Jedes Schreiben startet LND neu, und ein Neustart sperrt bei
    abgeschaltetem Auto-Entsperren die Wallet. Ein Waechter, der bei jedem
    Durchgang schreibt, haelt den Knoten dauerhaft still."""
    lnd_conf = _mit_lightning(client, monkeypatch)
    vorher = lnd_conf.read_text()
    client.app.state.einmal_nachsehen()
    client.app.state.einmal_nachsehen()
    assert lnd_conf.read_text() == vorher


def test_ein_dns_aussetzer_nimmt_die_lnd_adresse_nicht_mit(
        client, monkeypatch):
    """Ein Aussetzer von Sekunden darf nicht dazu fuehren, dass der Knoten
    seine angekuendigte Adresse verliert und neu startet."""
    from satcortex import dyndns as dyndns_modul
    lnd_conf = _mit_lightning(client, monkeypatch)
    assert "externalip=203.0.113.9:9735" in lnd_conf.read_text()

    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda namen: [])
    client.app.state.einmal_nachsehen()
    assert "externalip=203.0.113.9:9735" in lnd_conf.read_text()


# ── Die drei Wege, auf denen eine Wallet wieder aufgeht ────────────────────
#
# Aus dem Betrieb, 10.09.2026: "wie ich es habe ist unintressant! weil das soll sich
# jeder nutzer aussuchen koennen ob sich das wallet selbst entsperrt ob ich
# den tresor will .. oder nicht".
#
# Der Tresor, der hier bis zum 10.09.2026 als dritter Weg stand, ist weg.
# Der Betreiber hat ihn zerlegt: "ich tausche ein passwort gegen das andere obwohl
# beide die selbe funktion unterm strich haben!!" -- und die Rechnung geht
# auf. Gegen "ich tippe das Wallet-Passwort" gewann er nichts und kostete ein
# Artefakt mehr auf der Platte; gegen "von allein entsperren" lieferte er
# nicht, wofuer man diese Betriebsart nimmt.
#
# An seiner Stelle steht "merken" -- und das loest das Problem, das der
# Tresor loesen sollte:
#
#   aus     nichts liegt irgendwo, nichts wird gemerkt. Nach JEDEM Neustart
#           tippt jemand das Wallet-Passwort.
#   merken  nichts liegt auf der Platte. Die Anwendung behaelt das Passwort,
#           solange sie laeuft -- startet SIE LND neu, macht sie die Wallet
#           selbst wieder auf. Nach einem Stromausfall wird getippt.
#   datei   das Wallet-Passwort im Klartext neben der Wallet. Wer die Platte
#           hat, hat beides.

def _passdatei(client):
    from satcortex import lnd as lnd_modul
    return lnd_modul.passwortdatei(str(client.tmp / "fast"))


def _alle_dateien(client):
    return [d for d in client.tmp.rglob("*") if d.is_file()]


@pytest.mark.parametrize("weg,datei_da", [
    ("aus", False), ("merken", False), ("datei", True)])
def test_die_drei_wege_sind_beim_anlegen_waehlbar(client, lnd_da, weg,
                                                  datei_da):
    _richte_ein(client)
    d = _seed(client)
    a = client.post("/api/lightning/wallet",
                    json=_antworten(d, entsperrweg=weg))
    assert a.status_code == 200, a.text
    assert a.json()["entsperrweg"] == weg
    assert _passdatei(client).exists() is datei_da


def test_im_weg_merken_liegt_das_passwort_auf_keiner_platte(client, lnd_da):
    """Der wichtigste Test dieser Gruppe -- und die Antwort auf des Betreibers
    Einwand, sein Wallet-Passwort liege unverschluesselt herum.

    Er sucht das Passwort in JEDER Datei, die die Anwendung angefasst hat,
    genau wie es der Seed-Test tut."""
    _richte_ein(client)
    d = _seed(client)
    a = client.post("/api/lightning/wallet",
                    json=_antworten(d, entsperrweg="merken"))
    assert a.status_code == 200, a.text

    roh = WALLET_PASSWORT.encode()
    for datei in _alle_dateien(client):
        assert roh not in datei.read_bytes(), f"steht in {datei}"


def test_im_weg_merken_entsperrt_lnd_sich_nicht_selbst(client, lnd_da):
    """Eine Entsperrdatei waere genau der Klartext, den dieser Weg
    vermeidet -- beides zusammen waere ein Schloss mit dem Schluessel
    daneben."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))
    assert not _passdatei(client).exists()
    lnd_conf = client.tmp / "config" / "lnd.conf"
    # Ohne fertige Kette gibt es noch gar keine lnd.conf -- dann gibt es
    # trivialerweise auch keine Entsperrzeile darin.
    if lnd_conf.exists():
        assert "wallet-unlock-password-file" not in lnd_conf.read_text()


def test_auch_im_weg_merken_tippt_der_nutzer_sein_passwort(client, lnd_da):
    """Es wird NICHT gewuerfelt. Nach einem Stromausfall faellt diese
    Anwendung mit -- und dann muss der Nutzer es kennen. Ein Passwort, das
    nur sie kannte, waere in genau dem Moment keines mehr."""
    _richte_ein(client)
    d = _seed(client)
    a = client.post("/api/lightning/wallet",
                    json=_antworten(d, entsperrweg="merken", passwort=""))
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "passwort_zu_kurz"
    assert lnd_da.angelegt is None, "die Wallet wurde trotzdem angelegt"


def test_das_alte_haekchen_gilt_weiter(client, lnd_da):
    """Ein gespeicherter Assistentenzustand kann noch das alte Feld tragen.
    Er darf dadurch nicht in einer anderen Betriebsart landen."""
    _richte_ein(client)
    d = _seed(client)
    a = client.post("/api/lightning/wallet",
                    json=_antworten(d, automatisch_entsperren=True))
    assert a.json()["entsperrweg"] == "datei"
    assert _passdatei(client).exists()


def test_die_oberflaeche_erfaehrt_welcher_weg_gilt(client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))
    d2 = client.get("/api/lightning/entsperrweg").json()
    assert d2["weg"] == "merken"
    assert d2["gemerkt"] is True


# ── Die Wallet nach einem Neustart selbst wieder aufmachen ─────────────────
#
# Der eigentliche Grund, warum es "merken" gibt. Nicht der Stromausfall --
# der kommt selten -- sondern die Neustarts, die DIESE ANWENDUNG ausloest:
# Name geaendert, Sichtbarkeit geaendert, Adresse neu aufgeloest. Jedes Mal
# faehrt LND neu hoch und die Wallet steht zu.

def test_nach_einem_neustart_macht_die_anwendung_die_wallet_selbst_auf(
        client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))

    lnd_da.stand = "LOCKED"
    lnd_da.entsperrt = None
    assert client.app.state.wallet_offenhalten() is True
    assert lnd_da.entsperrt == WALLET_PASSWORT


def test_im_weg_aus_wartet_der_knoten_auf_den_nutzer(client, lnd_da):
    """Der Unterschied zur Klartextdatei -- und zu "merken"."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet", json=_antworten(d, entsperrweg="aus"))

    lnd_da.stand = "LOCKED"
    lnd_da.entsperrt = None
    assert client.app.state.wallet_offenhalten() is False
    assert lnd_da.entsperrt is None


def test_nach_einem_neustart_DIESER_anwendung_ist_nichts_mehr_gemerkt(
        client, lnd_da, tmp_path):
    """Genau das trennt "merken" von der Klartextdatei: der Merker stirbt
    mit dem Prozess. Wer die NAS neu startet, tippt wieder."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))

    # Dieselben Verzeichnisse, neue Anwendung -- also ein Neustart.
    neu = _client(tmp_path)
    auskunft = neu.get("/api/lightning/entsperrweg").json()
    assert auskunft["weg"] == "merken", "die Wahl ueberlebt den Neustart"
    assert auskunft["gemerkt"] is False, "das Passwort aber nicht"

    lnd_da.stand = "LOCKED"
    lnd_da.entsperrt = None
    assert neu.app.state.wallet_offenhalten() is False
    assert lnd_da.entsperrt is None


def test_ein_gemerktes_passwort_das_nicht_mehr_passt_wird_verworfen(
        client, lnd_da):
    """Sonst waere es ein Rateversuch im Takt des Sammlers."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))

    lnd_da.stand = "LOCKED"
    lnd_da.entsperrfehler = True
    assert client.app.state.wallet_offenhalten() is False
    assert client.get("/api/lightning/entsperrweg").json()["gemerkt"] is False


def test_wer_von_hand_entsperrt_wird_ab_dann_gemerkt(client, lnd_da):
    """Nach einem Neustart der Anwendung ist der Merker leer. Das erste
    Entsperren fuellt ihn wieder -- und zwar ERST nach der Pruefung durch
    LND."""
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))
    neu = _client(client.tmp)
    assert neu.get("/api/lightning/entsperrweg").json()["gemerkt"] is False

    lnd_da.stand = "LOCKED"
    a = neu.post("/api/lightning/entsperren", json={"passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    assert neu.get("/api/lightning/entsperrweg").json()["gemerkt"] is True


def test_ein_falsches_passwort_wird_nicht_gemerkt(client, lnd_da):
    _richte_ein(client)
    d = _seed(client)
    client.post("/api/lightning/wallet",
                json=_antworten(d, entsperrweg="merken"))
    neu = _client(client.tmp)

    lnd_da.stand = "LOCKED"
    lnd_da.entsperrfehler = True
    a = neu.post("/api/lightning/entsperren", json={"passwort": "danebengetippt"})
    assert a.status_code == 400
    assert neu.get("/api/lightning/entsperrweg").json()["gemerkt"] is False


# ── Den Entsperrweg nachtraeglich wechseln ─────────────────────────────────
#
# Wer schon eine Wallet hat, kommt sonst nie an einen anderen Weg -- waehlbar
# war er nur beim Anlegen. "Dann leg die Wallet halt neu an" ist keine
# Antwort, sobald Geld darin liegt.
#
# DIE REGEL, die alles andere bestimmt: ein Wallet-Passwort, das die Anwendung
# nicht GEPRUEFT hat, darf sie nirgendwo hinterlegen. Sonst entsperrt sich
# beim naechsten Neustart nichts mehr, und der Nutzer steht vor einer Wallet,
# die niemand mehr oeffnet.
#
# Pruefen kann das nur LND selbst, und nur an einer GESPERRTEN Wallet. Also
# derselbe Umweg wie beim Loeschen: erst sperren, dann umstellen.

def _wallet_mit_weg(client, weg, **mehr):
    d = _seed(client)
    leib = _antworten(d, entsperrweg=weg, **mehr)
    return client.post("/api/lightning/wallet", json=leib)


def test_von_datei_auf_merken_ohne_dass_jemand_etwas_tippen_muss(
        client, lnd_da):
    """Das Passwort steht in wallet.pass, und LND entsperrt sich damit seit
    jeher erfolgreich. Besser laesst es sich gar nicht pruefen."""
    _richte_ein(client)
    _wallet_mit_weg(client, "datei")
    assert _passdatei(client).exists()

    a = client.post("/api/lightning/entsperrweg", json={"weg": "merken"})
    assert a.status_code == 200, a.text
    assert a.json()["weg"] == "merken"
    assert not _passdatei(client).exists(), "der Klartext muss weg sein"

    # Und gemerkt ist wirklich das Passwort, mit dem die Wallet aufgeht.
    lnd_da.stand = "LOCKED"
    lnd_da.entsperrt = None
    assert client.app.state.wallet_offenhalten() is True
    assert lnd_da.entsperrt == WALLET_PASSWORT


def test_von_aus_auf_merken_geht_ohne_alles(client, lnd_da):
    """DER BEFUND VOM 10.09.2026. Der Betreiber: "habe aber gerade den Haken
    gesetzt bei fuer die Laufzeit merken aber das wird noch nicht
    uebernommen".

    Er hatte den Weg "aus", und der Wechsel verlangte von ihm ein getipptes
    Passwort UND eine gesperrte Wallet -- fuer nichts. "aus" legt nirgends
    etwas ab, "merken" legt nichts auf die PLATTE. Es gab nichts zu pruefen.

    Ein falsches Passwort im Arbeitsspeicher richtet keinen Schaden an: der
    Sammler legt es LND einmal vor, faengt sich eine Abfuhr, wirft es weg
    und laesst fragen -- genau der Zustand, in dem man ohnehin war."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    assert lnd_da.stand == "SERVER_ACTIVE", "die Wallet laeuft"

    a = client.post("/api/lightning/entsperrweg", json={"weg": "merken"})
    assert a.status_code == 200, a.text
    auskunft = client.get("/api/lightning/entsperrweg").json()
    assert auskunft["weg"] == "merken"
    # Gemerkt ist noch nichts -- das faellt beim naechsten Entsperren an.
    assert auskunft["gemerkt"] is False


def test_nach_dem_wechsel_auf_merken_faellt_das_passwort_von_allein_an(
        client, lnd_da):
    """Der zweite Halbsatz zum Test darueber: der Weg gilt sofort, das
    Passwort kommt beim naechsten Entsperren -- und ist dann geprueft."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    client.post("/api/lightning/entsperrweg", json={"weg": "merken"})

    lnd_da.stand = "LOCKED"
    a = client.post("/api/lightning/entsperren",
                    json={"passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    assert client.get("/api/lightning/entsperrweg").json()["gemerkt"] is True


def test_von_aus_auf_datei_nur_an_einer_gesperrten_wallet(client, lnd_da):
    """Hier bleibt die Probe, und nur hier: "datei" schreibt Klartext auf
    die Platte, und ein falsches Passwort dort haengt LND beim naechsten
    Start auf -- ohne dass jemand sieht warum."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    assert lnd_da.stand == "SERVER_ACTIVE"

    a = client.post("/api/lightning/entsperrweg",
                    json={"weg": "datei", "passwort": WALLET_PASSWORT})
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "wallet_nicht_gesperrt"
    assert not _passdatei(client).exists()


def test_an_der_gesperrten_wallet_geht_der_wechsel_auf_datei(client, lnd_da):
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "LOCKED"

    a = client.post("/api/lightning/entsperrweg",
                    json={"weg": "datei", "passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    # Geprueft wurde durch einen echten Entsperrversuch.
    assert lnd_da.entsperrt == WALLET_PASSWORT
    assert _passdatei(client).read_text().strip() == WALLET_PASSWORT


def test_ein_falsches_wallet_passwort_wird_nicht_uebernommen(client, lnd_da):
    """Der wichtigste Test dieser Gruppe."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "LOCKED"
    lnd_da.entsperrfehler = True

    a = client.post("/api/lightning/entsperrweg", json={
        "weg": "datei", "passwort": "das-ist-nicht-das-richtige"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "passwort_falsch"
    assert not _passdatei(client).exists()


def test_ohne_passwort_geht_der_wechsel_auf_datei_nicht(client, lnd_da):
    """Nur dieser eine Weg braucht es -- und ohne bekommt man auch keinen
    halben Zustand, sondern eine klare Abfuhr."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "LOCKED"
    a = client.post("/api/lightning/entsperrweg", json={"weg": "datei"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "passwort_fehlt"
    assert not _passdatei(client).exists()


def test_von_merken_auf_datei_ohne_dass_jemand_etwas_tippen_muss(
        client, lnd_da):
    """Gemerkt wird nur, was LND angenommen hat -- also ist es geprueft."""
    _richte_ein(client)
    _wallet_mit_weg(client, "merken")

    a = client.post("/api/lightning/entsperrweg", json={"weg": "datei"})
    assert a.status_code == 200, a.text
    assert _passdatei(client).read_text().strip() == WALLET_PASSWORT


def test_von_merken_auf_aus_vergisst_das_passwort(client, lnd_da):
    _richte_ein(client)
    _wallet_mit_weg(client, "merken")

    a = client.post("/api/lightning/entsperrweg", json={"weg": "aus"})
    assert a.status_code == 200, a.text
    auskunft = client.get("/api/lightning/entsperrweg").json()
    assert auskunft["weg"] == "aus"
    assert auskunft["gemerkt"] is False


def test_ein_unbekannter_weg_wird_abgewiesen(client, lnd_da):
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    a = client.post("/api/lightning/entsperrweg", json={"weg": "quatsch"})
    assert a.status_code == 400


def test_der_tresor_ist_kein_weg_mehr(client, lnd_da):
    """Er wurde am 10.09.2026 herausgenommen. Wer ihn noch anfragt -- eine
    alte Oberflaeche im Browsercache -- bekommt eine klare Abfuhr statt
    einer halben Einrichtung."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    a = client.post("/api/lightning/entsperrweg", json={"weg": "tresor"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "entsperrweg_unbekannt"



# ── Die PIN an der Oberflaeche ─────────────────────────────────────────────
#
# Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also knoten
# oeffnen oder schliessen geld transferieren".
#
# EINRICHTEN VERLANGT DAS KONTOPASSWORT, und das ist kein Zierrat: waere es
# anders, koennte eine uebernommene Sitzung sich SELBST eine PIN geben und
# damit anschliessend alles freigeben. Ein Schloss, dessen Schluessel der
# Einbrecher aussucht, ist keines.

PIN = "402719"


def _freigabe_ein(client, pin=PIN):
    return client.post("/api/freigabe", json={
        "passwort": ZUGANG["passwort"], "pin": pin})


def test_ohne_pin_meldet_die_auskunft_das_auch(client):
    d = client.get("/api/freigabe").json()
    assert d["eingerichtet"] is False
    assert d["stellen_min"] == auth.PIN_MIN_STELLEN


def test_die_pin_laesst_sich_einrichten(client):
    assert _freigabe_ein(client).status_code == 200
    assert client.get("/api/freigabe").json()["eingerichtet"] is True


def test_ohne_kontopasswort_gibt_es_keine_pin(client):
    """Sonst gaebe eine uebernommene Sitzung sich selbst das Schloss."""
    a = client.post("/api/freigabe", json={"passwort": "falsch", "pin": PIN})
    assert a.status_code == 403
    assert client.get("/api/freigabe").json()["eingerichtet"] is False


def test_eine_schwache_pin_wird_abgewiesen(client):
    a = client.post("/api/freigabe", json={
        "passwort": ZUGANG["passwort"], "pin": "123456"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "pin_ist_eine_reihe"


def test_eine_zweite_pin_ueberschreibt_die_erste_nicht(client):
    _freigabe_ein(client)
    a = _freigabe_ein(client, "846201")
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "pin_existiert"


def test_die_pin_laesst_sich_aendern_und_abschaffen(client):
    _freigabe_ein(client)
    assert client.post("/api/freigabe/aendern",
                       json={"alt": PIN, "neu": "846201"}).status_code == 200
    assert client.post("/api/freigabe/entfernen",
                       json={"pin": "846201"}).status_code == 200
    assert client.get("/api/freigabe").json()["eingerichtet"] is False


def test_mit_der_falschen_pin_wird_nichts_abgeschafft(client):
    _freigabe_ein(client)
    a = client.post("/api/freigabe/entfernen", json={"pin": "000001"})
    assert a.status_code == 400
    assert client.get("/api/freigabe").json()["eingerichtet"] is True


def test_die_auskunft_sagt_wie_lange_noch_zu_warten_ist(client):
    """Ohne diese Zahl steht der Nutzer vor einem Feld, das nichts annimmt,
    und weiss nicht, ob es an ihm liegt."""
    _freigabe_ein(client)
    client.post("/api/freigabe/entfernen", json={"pin": "000001"})
    assert client.get("/api/freigabe").json()["wartet_noch"] > 0


# ── Und sie bekommt sofort eine echte Aufgabe ──────────────────────────────
#
# Eine PIN, die nichts bewacht, ist eine Behauptung. Das Loeschen der Wallet
# ist heute der einzige Handgriff, der etwas Unwiederbringliches tut -- also
# faengt sie dort an. Das Senden kommt spaeter dazu.

def test_mit_eingerichteter_pin_verlangt_das_loeschen_sie_auch(client, lnd_da):
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    _freigabe_ein(client)
    lnd_da.stand = "LOCKED"

    a = client.post("/api/lightning/wallet/loeschen", json={
        "passwort": WALLET_PASSWORT, "alias": "SatoshiCortex"})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_die_falsche_pin_loescht_nichts(client, lnd_da):
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    _freigabe_ein(client)
    lnd_da.stand = "LOCKED"

    a = client.post("/api/lightning/wallet/loeschen", json={
        "passwort": WALLET_PASSWORT, "alias": "SatoshiCortex", "pin": "000001"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "pin_falsch"


def test_ohne_eingerichtete_pin_bleibt_das_loeschen_wie_es_war(client, lnd_da):
    """Wer keine PIN eingerichtet hat, soll nicht ploetzlich vor einer
    Abfrage stehen, die es fuer ihn gar nicht gibt."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "LOCKED"
    a = client.post("/api/lightning/wallet/loeschen", json={
        "passwort": WALLET_PASSWORT, "alias": "SatoshiCortex"})
    assert a.status_code == 200, a.text


# ── Senden: der Weg zurueck aus der Wallet heraus ──────────────────────────
#
# Die Bedingung des Betreibers vom 30.08.2026: "ich werde nix dahin ueberweisen solange
# ich es nicht zurueck schicken kann". Eine Wallet, aus der man nicht wieder
# herauskommt, ist keine Wallet, sondern ein Einbahnstrassenschild.
#
# Es kam NACH der PIN und nicht davor, und das ist der Grund: mit
# onchain:write gibt es zum ersten Mal einen Endpunkt dieser Anwendung, der
# zahlt. Fuer jemanden mit der Platte aendert das nichts -- dort liegt ohnehin
# LNDs admin.macaroon. Fuer eine uebernommene SITZUNG aendert es alles.

ADRESSE = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"


def _mit_gebuehren(client, monkeypatch, saetze=None):
    """Gebuehrenschaetzung aus dem EIGENEN bitcoind vortaeuschen.

    Ohne sie gibt es keinen Satz -- und das ist Absicht: eine Eins
    hinzuschreiben waere bequem und teuer.
    """
    from satcortex import kennzahlen as kz_modul
    monkeypatch.setattr(kz_modul, "gebuehren", lambda _k: saetze if saetze
                        is not None else {"schnell": 12.0, "normal": 4.2,
                                          "guenstig": 2.0})
    monkeypatch.setattr(kz_modul, "naechster_block", lambda _k: None)
    monkeypatch.setattr(kz_modul, "schwierigkeit", lambda *a, **kw: {})
    _mit_kette(client, monkeypatch)
    # Gefuellt wird der Kennzahlen-Speicher vom SAMMLER, nicht vom Endpunkt
    # -- der liest nur ab. Genau deshalb wartet dort nie jemand.
    client.app.state.lage_auffrischen()


def _sendebereit(client, lnd_da, monkeypatch):
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "SERVER_ACTIVE"
    _mit_gebuehren(client, monkeypatch)


def test_die_schaetzung_sagt_was_es_kostet(client, lnd_da, monkeypatch):
    """Die einzige Frage, die man vor dem Druecken hat."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden/schaetzen",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 200, a.text
    d = a.json()
    assert d["gebuehr_sat"] == 1420
    assert d["alles"] is False


def test_die_schaetzung_bewegt_nichts(client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    client.post("/api/lightning/senden/schaetzen",
                json={"adresse": ADRESSE, "betrag": 100_000})
    assert lnd_da.gesendet is None


def test_gesendet_wird_mit_dem_satz_aus_dem_eigenen_knoten(client, lnd_da,
                                                           monkeypatch):
    """Aus dem Betrieb, 30.08.2026: "jede info die wir brauchen kommt aus dem
    netzwerk und nicht von extern". Der Satz kommt aus estimatesmartfee des
    EIGENEN bitcoind -- und wird aufgerundet, nie ab: eine Zahlung knapp
    unter der Schaetzung bleibt liegen."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000,
                          "tempo": "normal"})
    assert a.status_code == 200, a.text
    assert a.json()["txid"] == "a" * 64
    assert lnd_da.gesendet["addr"] == ADRESSE
    assert lnd_da.gesendet["amount"] == "100000"
    assert lnd_da.gesendet["sat_per_vbyte"] == "5", "4,2 muss auf 5 aufgehen"


def test_ohne_gebuehrenschaetzung_wird_nicht_gesendet(client, lnd_da,
                                                      monkeypatch):
    """Eine Eins hinzuschreiben waere bequem: die Zahlung bliebe tagelang
    liegen, und niemand haette es gewollt."""
    _richte_ein(client)
    _wallet_mit_weg(client, "aus")
    lnd_da.stand = "SERVER_ACTIVE"
    _mit_gebuehren(client, monkeypatch, saetze={})
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 503
    assert a.json()["detail"]["meldung"] == "keine_gebuehrenschaetzung"
    assert lnd_da.gesendet is None


def test_alles_raeumt_die_wallet_leer_und_nennt_keinen_betrag(client, lnd_da,
                                                              monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "alles": True})
    assert a.status_code == 200, a.text
    assert lnd_da.gesendet["send_all"] is True
    assert "amount" not in lnd_da.gesendet


def test_alles_und_ein_betrag_zusammen_werden_abgewiesen(client, lnd_da,
                                                         monkeypatch):
    """Was von zweien gaelte, waere geraten -- und geraten wird hier nicht."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000,
                          "alles": True})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "alles_und_betrag"
    assert lnd_da.gesendet is None


def test_ein_staubbetrag_wird_abgewiesen(client, lnd_da, monkeypatch):
    """Unter der Staubgrenze nimmt das Netz die Ausgabe nicht an. LNDs
    Abfuhr versteht niemand -- also hier abfangen und es sagen."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "betrag_zu_klein"
    assert lnd_da.gesendet is None


def test_ohne_adresse_geht_nichts_hinaus(client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden", json={"betrag": 100_000})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "adresse_fehlt"
    assert lnd_da.gesendet is None


def test_aus_einer_gesperrten_wallet_geht_nichts_hinaus(client, lnd_da,
                                                        monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    lnd_da.stand = "LOCKED"
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "wallet_gesperrt"
    assert lnd_da.gesendet is None


def test_eine_abfuhr_von_lnd_wird_im_klartext_weitergereicht(client, lnd_da,
                                                             monkeypatch):
    """Der haeufigste Grund ist eine vertippte Adresse, der zweithaeufigste
    zu wenig Guthaben. Beides sagt LND im Klartext -- und beides gehoert dem
    Nutzer gesagt, nicht dem Protokoll."""
    _sendebereit(client, lnd_da, monkeypatch)
    lnd_da.sendefehler = "insufficient funds available to construct transaction"
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 400
    d = a.json()["detail"]
    assert d["meldung"] == "senden_abgelehnt"
    assert "insufficient funds" in d["einzelheit"]


def test_ein_unbekanntes_tempo_wird_abgewiesen(client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000,
                          "tempo": "umsonst"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "tempo_unbekannt"


def test_mit_eingerichteter_pin_verlangt_das_senden_sie_auch(client, lnd_da,
                                                             monkeypatch):
    """Das ist der ganze Grund, warum die PIN zuerst kam."""
    _sendebereit(client, lnd_da, monkeypatch)
    assert _freigabe_ein(client).status_code == 200
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"
    assert lnd_da.gesendet is None, "trotz fehlender PIN gesendet"

    b = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000, "pin": PIN})
    assert b.status_code == 200, b.text
    assert lnd_da.gesendet is not None


def test_eine_falsche_pin_sendet_nichts(client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    _freigabe_ein(client)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000,
                          "pin": "999888"})
    assert a.status_code == 400
    assert lnd_da.gesendet is None


def test_die_schaetzung_braucht_keine_pin(client, lnd_da, monkeypatch):
    """Eine Abfrage, die nichts tut, hinter ein Schloss zu stellen, macht
    das Schloss nur laestig und nichts sicherer."""
    _sendebereit(client, lnd_da, monkeypatch)
    _freigabe_ein(client)
    a = client.post("/api/lightning/senden/schaetzen",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 200, a.text


def test_die_anwendung_darf_jetzt_onchain_schreiben(client):
    """Das schwerste Recht in der Liste. Es steht hier, damit ein
    versehentliches Herausnehmen auffaellt -- und damit ein
    versehentliches HINZUFUEGEN von noch mehr es auch tut."""
    from satcortex import lnd as lnd_modul
    assert ("onchain", "write") in lnd_modul.EIGENE_RECHTE
    # Und nichts darueber hinaus: macaroon:generate wuerde erlauben, sich
    # selbst weitere Rechte auszustellen.
    for verboten in ("macaroon", "signer", "walletrpc"):
        assert not any(e == verboten for e, _ in lnd_modul.EIGENE_RECHTE), \
            verboten


# ── Sperren: der Knopf, der eine Minute lang schwieg ───────────────────────
#
# Aus dem Betrieb, 11.09.2026: "dazu steht hier wallet sperren .. da drueck ich
# drauf passiert nix".
#
# Es passierte sehr wohl etwas -- LND wurde beendet und neu gestartet, was bis
# zu neunzig Sekunden dauert. Nur sah man davon nichts. Ein Knopf, der eine
# Minute lang arbeitet und dabei schweigt, ist von einem kaputten Knopf nicht
# zu unterscheiden.

def test_die_auskunft_sagt_ob_gerade_ein_neustart_laeuft(client, lnd_da):
    """Ohne diese Zahl kann die Oberflaeche nur raten, ob sie warten soll."""
    _richte_ein(client)
    assert client.get("/api/lightning").json()["arbeit_laeuft"] is False


def test_wer_absichtlich_sperrt_will_nicht_sofort_wieder_auf(client, lnd_da):
    """DER ZWEITE BEFUND, und der waere gleich danach gekommen.

    Im Weg "merken" haette der Sammler die Wallet binnen zwanzig Sekunden
    von allein wieder aufgemacht -- waehrend der Nutzer sie absichtlich
    zugesperrt hat, um sie zu loeschen oder den Entsperrweg zu wechseln. Die
    Anwendung haette ihren eigenen Nutzer bekaempft.

    Ein ausdruecklicher Handgriff schlaegt eine Bequemlichkeit."""
    _richte_ein(client)
    _wallet_mit_weg(client, "merken")
    assert client.get("/api/lightning/entsperrweg").json()["gemerkt"] is True

    a = client.post("/api/lightning/wallet/sperren")
    assert a.status_code == 200, a.text
    assert client.get("/api/lightning/entsperrweg").json()["gemerkt"] is False

    # Und der Waechter macht sie folglich auch nicht wieder auf.
    lnd_da.stand = "LOCKED"
    lnd_da.entsperrt = None
    assert client.app.state.wallet_offenhalten() is False
    assert lnd_da.entsperrt is None


def test_mit_entsperrdatei_bringt_das_sperren_nichts(client, lnd_da):
    """Dann entsperrt LND sich beim Start selbst -- der Neustart waere ein
    Neustart fuer nichts, und der Nutzer stuende danach vor derselben Lage."""
    _richte_ein(client)
    _wallet_mit_weg(client, "datei")
    a = client.post("/api/lightning/wallet/sperren")
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "auto_entsperren_an"


# ── Wenn LND den Seed ablehnt, sagt er WARUM ───────────────────────────────
#
# Aus dem Betrieb, 11.09.2026: "er sagt er kann mit der seed kein wallet wieder
# herstellen die pruefsummer stummt nicht .. bin mir aber zu 100% sicher das
# dass stimmt!"
#
# Die Meldung behauptete in JEDEM Fall, der Zettel sei falsch -- LNDs eigener
# Wortlaut blieb im Protokoll. LND lehnt aber aus mehreren Gruenden ab. Und
# jemandem zu sagen "deine vierundzwanzig Woerter stimmen nicht", wenn sie
# stimmen, ist die teuerste Falschauskunft dieser Anwendung: am Ende wirft er
# den Zettel weg.

def test_die_abfuhr_von_lnd_nennt_ihren_grund(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "NON_EXISTING"
    lnd_da.sendefehler = ""

    from satcortex import lnd as lnd_modul
    urspruenglich = lnd_modul.lege_wallet_an

    def abweisen(*a, **kw):
        raise lnd_modul.LndFehler("invalid passphrase for cipher seed")

    import satcortex.api as api_modul
    api_modul.lnd.lege_wallet_an = abweisen
    try:
        a = client.post("/api/lightning/wiederherstellen", json={
            "woerter": list(WOERTER), "passwort": WALLET_PASSWORT})
    finally:
        api_modul.lnd.lege_wallet_an = urspruenglich

    assert a.status_code == 400
    d = a.json()["detail"]
    assert d["meldung"] == "seed_nicht_angenommen"
    assert "passphrase" in d["einzelheit"], (
        "ohne LNDs Wortlaut behauptet die Meldung, der Zettel sei falsch")


# ── Kommen die Woerter unveraendert bei LND an? ────────────────────────────
#
# Aus dem Betrieb, 11.09.2026: "und was ist wenn die app einfach die woerter nicht
# wieder zurueck in die pruefsumme zurueck umwandelt .. dann kann lnd das auch
# nicht erkennen".
#
# Die richtige Frage, und sie gehoert gemessen statt beteuert. aezeed rechnet
# die Pruefsumme aus den WOERTERN -- also darf zwischen Tastatur und LND kein
# einziges Zeichen verlorengehen oder dazukommen.

def test_die_woerter_kommen_unveraendert_bei_lnd_an(client, lnd_da):
    _richte_ein(client)
    a = client.post("/api/lightning/wiederherstellen", json={
        "woerter": list(WOERTER), "passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    # KEIN base64, keine Umsortierung, kein fehlendes Wort.
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == list(WOERTER)


def test_tippfehler_der_form_werden_geglaettet_der_inhalt_nicht(client, lnd_da):
    """Grossschreibung und Leerzeichen am Rand duerfen einen richtigen Seed
    nicht zu Fall bringen -- die BIP39-Woerter sind durchgehend klein. Am
    WORT selbst wird dabei nichts geaendert."""
    _richte_ein(client)
    schief = [f"  {w.upper()} " for w in WOERTER]
    a = client.post("/api/lightning/wiederherstellen", json={
        "woerter": schief, "passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == list(WOERTER)


def test_eine_leere_passphrase_wird_gar_nicht_erst_mitgeschickt(client, lnd_da):
    """Sonst bekaeme LND ein Feld, das den Seed anders entschluesselt -- und
    lehnte einen richtigen Zettel ab."""
    _richte_ein(client)
    client.post("/api/lightning/wiederherstellen", json={
        "woerter": list(WOERTER), "passwort": WALLET_PASSWORT,
        "passphrase": ""})
    assert "aezeed_passphrase" not in lnd_da.angelegt


def test_eine_gesetzte_passphrase_geht_mit(client, lnd_da):
    """Der Gegenbeweis zum Test darueber: wer eine hat, braucht sie auch."""
    _richte_ein(client)
    client.post("/api/lightning/wiederherstellen", json={
        "woerter": list(WOERTER), "passwort": WALLET_PASSWORT,
        "passphrase": "etwas"})
    assert "aezeed_passphrase" in lnd_da.angelegt


def test_der_seed_aus_dem_anlegen_passt_zum_wiederherstellen(client, lnd_da):
    """Der eigentliche Rundlauf: was die Oberflaeche beim Anlegen ZEIGT,
    muss beim Zurueckholen wieder angenommen werden. Geht dabei etwas
    verloren, stimmt der Zettel nie -- und niemand koennte sagen warum."""
    _richte_ein(client)
    gezeigt = client.post("/api/lightning/seed").json()["woerter"]
    assert len(gezeigt) == 24

    a = client.post("/api/lightning/wiederherstellen", json={
        "woerter": gezeigt, "passwort": WALLET_PASSWORT})
    assert a.status_code == 200, a.text
    assert lnd_da.angelegt["cipher_seed_mnemonic"] == gezeigt


# ── Wenn getinfo gerade nicht antwortet (11.09.2026) ───────────────────────
#
# Der Betreiber: "aber es wird mir noch keine verbindungs adresse angezeigt".
#
# Seine beiden Protokolle nebeneinander sagten alles:
#
#   App:  knoten nicht abrufbar (antwortet nicht innerhalb von 5 s)
#         21:31:33 · :35 · :37 · :39
#   LND:  elapsed time for diameter calculation: 3.4 ms
#         21:31:33 · :35 · :37 · :39
#
# Dieselben Sekunden: der Graph-Aufruf antwortete in drei Millisekunden,
# getinfo lief ins Zeitlimit. LNDs RPC war kerngesund -- die WALLET war
# beschaeftigt (BTWL-Zeilen: sie durchsuchte die Kette nach benutzten
# Adressen, der Rueckweg einer Wiederherstellung).
#
# Die Verbindungsadresse steckt in getinfo. Fiel der Aufruf weg, fiel das
# ganze Feld weg -- und die Oberflaeche zeichnete den Adresskasten gar nicht
# erst neu.

def test_getinfo_bekommt_mehr_luft_als_der_rest(client):
    """Fuenf Sekunden sind fuer einen ruhenden Knoten grosszuegig und fuer
    eine laufende Wiederherstellung zu knapp."""
    from satcortex import lnd as lnd_modul
    assert lnd_modul.UEBERSICHT_ZEITLIMIT_SEKUNDEN > lnd_modul.Knoten.zeitlimit


class _BeschaeftigtesLnd(FakeLnd):
    """Antwortet auf alles -- nur auf getinfo nicht."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.getinfo_haengt = False

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if pfad == "/v1/getinfo":
            if self.getinfo_haengt:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.Beschaeftigt(
                    "antwortet nicht innerhalb von 15 s")
            return {"identity_pubkey": "02" + "a" * 64, "alias": "Probe",
                    "uris": ["02" + "a" * 64 + "@abc.onion:9735"]}
        if pfad.startswith("/v1/balance") or pfad.startswith("/v1/channels"):
            return {}
        if pfad.startswith("/v1/graph/info"):
            return {"num_nodes": "17000"}
        if pfad.startswith("/v1/switch"):
            return {}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_beschaeftigt(monkeypatch, tmp_path):
    from satcortex import api as api_modul
    ordner = tmp_path / "macaroons"
    ordner.mkdir(exist_ok=True)
    knoten = _BeschaeftigtesLnd(stand="SERVER_ACTIVE", macaroons=ordner)
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_der_letzte_bekannte_stand_bleibt_stehen(client, lnd_beschaeftigt):
    """Lieber der Wert von vorhin MIT dem Hinweis, dass er von vorhin ist,
    als eine leere Flaeche. Die Alternative waere kein besserer Wert,
    sondern gar keiner."""
    _richte_ein(client)
    erst = client.get("/api/lightning/kanaele").json()
    assert erst["knoten"]["adressen"], "der erste Abruf muss klappen"
    assert not erst.get("knoten_veraltet")

    lnd_beschaeftigt.getinfo_haengt = True
    dann = client.get("/api/lightning/kanaele").json()
    assert dann["knoten"]["adressen"] == erst["knoten"]["adressen"]
    assert dann["knoten_veraltet"] is True


def test_ohne_je_eine_antwort_sagt_die_auskunft_wenigstens_das(
        client, lnd_beschaeftigt):
    """Hat es nie geklappt, gibt es nichts zu zeigen -- dann muss wenigstens
    dastehen, DASS gerade niemand antwortet."""
    _richte_ein(client)
    lnd_beschaeftigt.getinfo_haengt = True
    d = client.get("/api/lightning/kanaele").json()
    assert "knoten" not in d
    assert d["knoten_beschaeftigt"] is True


# ── Ist das noch derselbe Knoten? (11.09.2026) ─────────────────────────────
#
# Der Betreiber, nach seiner Wiederherstellung: "keine ahnung habe mir die kennung
# nicht vorher angesehen .. oder muss ich alles noch mal neu machen weil ich
# die kennung nicht hatte?"
#
# Musste er nicht -- aber dass er sie sich von HAND haette notieren sollen,
# war unser Versaeumnis. Die Anwendung kennt die Kennung ohnehin: sie ist der
# oeffentliche Schluessel dieses Knotens, im ganzen Lightning-Netz bekannt.
# Sie festzuhalten gibt nichts preis, was nicht offen liegt.

class _LndMitKennung(FakeLnd):
    def __init__(self, kennung, **kw):
        super().__init__(**kw)
        self.kennung = kennung

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if pfad == "/v1/getinfo":
            return {"identity_pubkey": self.kennung, "alias": "Probe"}
        if pfad.startswith("/v1/balance") or pfad.startswith("/v1/channels"):
            return {}
        if pfad.startswith("/v1/graph/info"):
            return {"num_nodes": "1"}
        if pfad.startswith("/v1/switch"):
            return {}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


def _mit_kennung(monkeypatch, tmp_path, kennung):
    from satcortex import api as api_modul
    ordner = tmp_path / "macaroons"
    ordner.mkdir(exist_ok=True)
    knoten = _LndMitKennung(kennung, stand="SERVER_ACTIVE", macaroons=ordner)
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


KENNUNG_A = "03" + "a" * 64
KENNUNG_B = "03" + "b" * 64


def test_die_kennung_wird_beim_ersten_mal_gemerkt(client, monkeypatch,
                                                  tmp_path):
    _mit_kennung(monkeypatch, tmp_path, KENNUNG_A)
    _richte_ein(client)
    d = client.get("/api/lightning/kanaele").json()
    assert d["knoten"]["kennung"] == KENNUNG_A
    assert "kennung_vorher" not in d, "beim ersten Mal gibt es nichts zu vergleichen"


def test_dieselbe_kennung_sagt_nichts(client, monkeypatch, tmp_path):
    """Der Normalfall nach einer gelungenen Wiederherstellung: still, weil
    alles stimmt."""
    _mit_kennung(monkeypatch, tmp_path, KENNUNG_A)
    _richte_ein(client)
    client.get("/api/lightning/kanaele")
    d = client.get("/api/lightning/kanaele").json()
    assert "kennung_vorher" not in d


def test_eine_andere_kennung_faellt_auf(client, monkeypatch, tmp_path):
    """Genau das, wofuer der Betreiber sich einen Zettel haette machen sollen."""
    _mit_kennung(monkeypatch, tmp_path, KENNUNG_A)
    _richte_ein(client)
    client.get("/api/lightning/kanaele")

    _mit_kennung(monkeypatch, tmp_path, KENNUNG_B)
    d = client.get("/api/lightning/kanaele").json()
    assert d["kennung_vorher"] == KENNUNG_A
    assert d["knoten"]["kennung"] == KENNUNG_B


def test_die_gemerkte_kennung_wird_nicht_still_ueberschrieben(
        client, monkeypatch, tmp_path):
    """Genau der Wechsel IST die Auskunft. Wer ihn stillschweigend glaettet,
    nimmt dem Nutzer die einzige Probe, die er hat."""
    _mit_kennung(monkeypatch, tmp_path, KENNUNG_A)
    _richte_ein(client)
    client.get("/api/lightning/kanaele")

    _mit_kennung(monkeypatch, tmp_path, KENNUNG_B)
    for _ in range(3):
        d = client.get("/api/lightning/kanaele").json()
        assert d["kennung_vorher"] == KENNUNG_A, "sie wurde ueberschrieben"


def test_eine_neue_kennung_laesst_sich_bewusst_uebernehmen(
        client, monkeypatch, tmp_path):
    """Nach einer NEU angelegten Wallet ist eine andere Kennung richtig --
    ein Hinweis, den man nicht wegbekommt, wird nach drei Tagen nicht mehr
    gelesen."""
    _mit_kennung(monkeypatch, tmp_path, KENNUNG_A)
    _richte_ein(client)
    client.get("/api/lightning/kanaele")

    _mit_kennung(monkeypatch, tmp_path, KENNUNG_B)
    client.get("/api/lightning/kanaele")
    a = client.post("/api/lightning/kennung/uebernehmen")
    assert a.status_code == 200, a.text
    assert a.json()["kennung"] == KENNUNG_B
    assert "kennung_vorher" not in client.get("/api/lightning/kanaele").json()


# ── Was fuer einen Kanal einzuzahlen ist (11.09.2026) ──────────────────────
#
# Der Betreiber: "ok dein knoten soll die menge an sat haben dann musst du aber das
# plus exit und gebueren an sat einzahlen weisst du was ich meine?"
#
# Sein Gefuehl stimmt, der Mechanismus ist ein anderer: die Schliessgebuehr
# geht beim einvernehmlichen Schliessen vom KANALGUTHABEN ab. Zusaetzlich in
# die Wallet gehoert die Anker-Ruecklage -- und die kommt von LND.

def test_der_kanalrechner_fragt_lnd_nach_der_ruecklage(client, lnd_voll):
    """Nicht geschaetzt: der Rechner fragt LND danach.

    Was aus der Zahl wird, steht in test_kennzahlen -- hier geht es nur
    darum, dass ueberhaupt gefragt wird. Eine Faustformel an dieser Stelle
    waere der Fehler, den man erst beim Schliessen bemerkt.
    """
    _richte_ein(client)
    assert client.get("/api/kanalrechner").json()["eingerichtet"] is True
    assert any(p.startswith("/v2/wallet/reserve") for p in lnd_voll.gefragt), \
        lnd_voll.gefragt


def test_die_kanalansicht_holt_die_ruecklage_nicht(client, lnd_voll):
    """Sie zeigt sie nicht -- der Rechner tut das. Ein LND-Aufruf je
    Auffrischung fuer eine Zahl, die auf der Seite niemand sieht, ist Last
    fuer nichts."""
    _richte_ein(client)
    client.get("/api/lightning/kanaele")
    assert not any(p.startswith("/v2/wallet/reserve")
                   for p in lnd_voll.gefragt), lnd_voll.gefragt


def test_ohne_gebuehrenschaetzung_rechnet_der_rechner_nicht(client, lnd_voll):
    """Ohne bitcoind gibt es keinen Satz -- und dann auch keine Rechnung.
    Eine Null hiesse "ein Kanal kostet nichts"."""
    _richte_ein(client)
    assert client.get("/api/kanalrechner").json()["kanalkosten"] is None


# ── Kanal oeffnen und ueber Lightning zahlen (12.09.2026) ──────────────────
#
# Der Betreiber: "ja dann machen wir mal mit Punkt 1 und 2 weiter."
#
# Beides gibt Geld aus der Hand, beides steht hinter derselben PIN wie das
# Senden -- und die wird ZUERST geprueft. Eine Reihenfolge, in der erst der
# Betrag und dann die Berechtigung geprueft wird, ist eine Zeile vom Unfall
# entfernt.

KENNUNG66 = "02" + "ab" * 32


def test_die_pin_steht_vor_dem_kanal(client, lnd_voll):
    """Vor allem anderen -- auch vor der Pruefung, ob das Guthaben reicht."""
    _richte_ein(client)
    _freigabe_ein(client)
    a = client.post("/api/lightning/kanal/oeffnen", json={
        "gegenstelle": KENNUNG66, "betrag": 100_000})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_die_pin_steht_vor_der_zahlung(client, lnd_voll):
    _richte_ein(client)
    _freigabe_ein(client)
    a = client.post("/api/lightning/rechnung/zahlen",
                    json={"rechnung": "lnbc1..."})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_die_falsche_pin_oeffnet_keinen_kanal(client, lnd_voll):
    _richte_ein(client)
    _freigabe_ein(client)
    a = client.post("/api/lightning/kanal/oeffnen", json={
        "gegenstelle": KENNUNG66, "betrag": 100_000, "pin": "000001"})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "pin_falsch"


def test_das_nachrechnen_braucht_keine_pin(client, lnd_voll, monkeypatch):
    """Hier wird gerechnet, nicht ausgegeben. Wer vor jeder Ueberlegung eine
    PIN eintippen muss, tippt sie irgendwann gedankenlos -- und genau das
    soll sie nicht werden."""
    _richte_ein(client)
    _freigabe_ein(client)
    _mit_gebuehren(client, monkeypatch)
    a = client.post("/api/lightning/kanal/schaetzen", json={
        "gegenstelle": KENNUNG66, "betrag": 100_000})
    assert a.status_code == 200, a.text
    d = a.json()
    # Die eine Zahl, die zaehlt: reicht es?
    assert "reicht" in d and "gebraucht_sat" in d


def test_ein_zu_kleiner_kanal_faellt_schon_beim_rechnen_auf(client, lnd_voll):
    """Bevor jemand den gefaehrlichen Knopf drueckt, nicht danach."""
    _richte_ein(client)
    a = client.post("/api/lightning/kanal/schaetzen", json={
        "gegenstelle": KENNUNG66, "betrag": 5_000})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "kanal_zu_klein"


def test_die_ruecklage_zaehlt_beim_kanal_mit(client, lnd_voll, monkeypatch):
    """Kanalgroesse plus Oeffnungsgebuehr plus Anker-Ruecklage -- wer nur die
    Kanalgroesse einzahlt, scheitert am Oeffnen und weiss nicht warum."""
    _richte_ein(client)
    _mit_gebuehren(client, monkeypatch)
    d = client.post("/api/lightning/kanal/schaetzen", json={
        "gegenstelle": KENNUNG66, "betrag": 100_000}).json()
    assert d["ruecklage_sat"] == 10_000
    assert d["gebraucht_sat"] == 100_000 + d["oeffnen_sat"] + 10_000


# ── Und jetzt die Erfolgspfade (12.09.2026) ────────────────────────────────
#
# Der Betreiber: "89% grün .. warum nicht 100%??" -- die Zahl ist die Abdeckung,
# nicht die Bestehensquote. Beim Nachsehen fiel aber auf, dass ausgerechnet
# die ERFOLGSPFADE dieser beiden Endpunkte nicht durchlaufen wurden: geprueft
# war "PIN fehlt", "Betrag zu klein", "Guthaben reicht nicht" -- nicht, dass
# der Kanal wirklich aufgeht und die Rechnung wirklich bezahlt wird.
#
# Bei zwei Endpunkten, die Geld aus der Hand geben, ist das die falsche Luecke.

def _kanalbereit(client, monkeypatch):
    _richte_ein(client)
    _freigabe_ein(client)
    _mit_gebuehren(client, monkeypatch)


def test_ein_kanal_wird_wirklich_geoeffnet(client, lnd_voll, monkeypatch):
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/kanal/oeffnen", json={
        "gegenstelle": KENNUNG66 + "@1.2.3.4:9735", "betrag": 100_000,
        "pin": PIN})
    assert a.status_code == 200, a.text
    d = a.json()
    # DIE FALLE: LND liefert die Kennung rueckwaerts. Was hier herauskommt,
    # muss die sein, die ein Explorer kennt.
    assert d["txid"] == "ab" * 32
    assert d["ok"] is True
    # Und LND hat den Auftrag auch wirklich bekommen.
    assert lnd_voll.geoeffnet["local_funding_amount"] == "100000"
    assert lnd_voll.geoeffnet["private"] is False


def test_ein_neuer_kanal_zieht_die_sicherung_nach(client, lnd_voll,
                                                  monkeypatch):
    """Die Sicherung ist ab jetzt eine andere -- es gibt einen Kanal mehr.
    Sie erst beim naechsten Takt nachzuziehen hiesse, ein Fenster zu lassen,
    in dem der neue Kanal ungesichert ist."""
    _kanalbereit(client, monkeypatch)
    gerufen = []
    monkeypatch.setattr(client.app.state, "sicherung_nachziehen",
                        lambda: gerufen.append(True))
    client.post("/api/lightning/kanal/oeffnen", json={
        "gegenstelle": KENNUNG66, "betrag": 100_000, "pin": PIN})
    assert gerufen, "ohne das bleibt der neue Kanal bis zum naechsten Takt ungesichert"


def test_eine_rechnung_wird_wirklich_bezahlt(client, lnd_voll, monkeypatch):
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/rechnung/zahlen", json={
        "rechnung": "lnbc15u1abc", "pin": PIN})
    assert a.status_code == 200, a.text
    d = a.json()
    assert d["betrag"] == 1500 and d["gebuehr"] == 2
    assert d["zweck"] == "Kaffee"
    # Die Gebuehrengrenze MUSS mitgegangen sein -- ohne sie nimmt LND, was
    # die Route kostet.
    from satcortex import lnd as lnd_modul
    assert lnd_voll.gezahlt["fee_limit_sat"] == str(
        lnd_modul.gebuehrgrenze(1500))
    assert lnd_voll.gezahlt["allow_self_payment"] is False


def test_die_rechnung_laesst_sich_vorher_ansehen(client, lnd_voll, monkeypatch):
    """Der wichtigste Schritt, und er bewegt nichts."""
    _kanalbereit(client, monkeypatch)
    d = client.post("/api/lightning/rechnung/lesen",
                    json={"rechnung": "lnbc15u1abc"}).json()
    assert d["betrag"] == 1500
    assert d["zweck"] == "Kaffee"
    assert d["gebuehrengrenze"] > 0
    assert d["abgelaufen"] is False
    assert lnd_voll.gezahlt is None, "das Ansehen darf nichts zahlen"


def test_eine_eigene_gebuehrengrenze_wird_genommen(client, lnd_voll,
                                                   monkeypatch):
    """Der Vorschlag ist ein Vorschlag. Wer ihn aendert, bekommt seinen."""
    _kanalbereit(client, monkeypatch)
    client.post("/api/lightning/rechnung/zahlen", json={
        "rechnung": "lnbc15u1abc", "gebuehrengrenze": 3, "pin": PIN})
    assert lnd_voll.gezahlt["fee_limit_sat"] == "3"


# ── Ein zu kleiner Kanal ist ein SICHERHEITSproblem (12.09.2026) ───────────
#
# Der Betreiber: "ist das alles nochmal validiert gegen unsere lndinfo quelle?"
#
# War es nicht -- und beim Nachholen kam ein Befund heraus, den ich nicht auf
# dem Schirm hatte. lightningnode.info nennt 200K-500K sat als Untergrenze und
# begruendet das NICHT wirtschaftlich:
#
#   "A channel too small will result in being unable to close when on-chain
#    fees are high. This will leave the channel vulnerable in a case, when the
#    counterparty would try to close with a previous state."
#
# Wer bei hohen Gebuehren nicht schliessen KANN, kann auch einen Betrugs-
# versuch nicht mehr bestrafen. Genau davon lebt die Sicherheit eines Kanals.

def test_ein_knapper_kanal_wird_benannt(client, lnd_voll, monkeypatch):
    _kanalbereit(client, monkeypatch)
    d = client.post("/api/lightning/kanal/schaetzen", json={
        "gegenstelle": KENNUNG66, "betrag": 146_000}).json()
    assert d["knapp"] is True, "146.000 sat liegen unter der Empfehlung"
    assert d["ratsam_ab_sat"] == 200_000


def test_ein_ausreichender_kanal_wird_nicht_angemahnt(client, lnd_voll,
                                                      monkeypatch):
    _kanalbereit(client, monkeypatch)
    d = client.post("/api/lightning/kanal/schaetzen", json={
        "gegenstelle": KENNUNG66, "betrag": 500_000}).json()
    assert d["knapp"] is False


def test_knapp_ist_eine_warnung_und_kein_riegel(client, lnd_voll, monkeypatch):
    """Die Entscheidung gehoert dem Betreiber. Ein Riegel waere Bevormundung
    -- und LNDs eigene Untergrenze liegt bei 20.000."""
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/kanal/oeffnen", json={
        "gegenstelle": KENNUNG66, "betrag": 50_000, "pin": PIN})
    assert a.status_code == 200, a.text


def test_die_pin_steht_vor_dem_umschichten(client, lnd_voll, monkeypatch):
    """Nicht, weil hier Geld verschwinden koennte -- sondern weil eine
    uebernommene Sitzung sonst in Ruhe Gebuehren verbrennen koennte, ein
    Umschichten nach dem anderen, jedes fuer sich unauffaellig."""
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/umschichten", json={
        "von": "12345", "nach": KENNUNG66, "betrag": 50_000})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_die_pin_steht_vor_dem_schliessen(client, lnd_voll, monkeypatch):
    """Ein Kanal, den eine uebernommene Sitzung schliessen koennte, ist ein
    Verlust -- auch wenn das Geld zurueckkommt: die Gebuehren sind weg, und
    beim Erzwingen liegt es fuer die Zeitsperre fest."""
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/kanal/schliessen",
                    json={"punkt": "ab" * 32 + ":0"})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_der_wachturmhinweis_laesst_sich_abweisen(client):
    """Wie das Sicherungsziel: es ist eine WAHL, und eine Wahl, die man
    taeglich wegklicken muss, ist keine."""
    from satcortex import api as api_modul
    assert "wachturm" in api_modul.ABWEISBAR


# ── Bewegungen der On-Chain-Wallet (15.09.2026) ─────────────────────────────
#
# Befund bei dem ersten Einzahlung: nur eine Zahl im Guthaben, keine
# txid, keine Bestaetigungen. Die Boerse nannte nur eine eigene Vorgangsnummer.

def test_die_wallet_zeigt_ihre_bewegungen(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.bewegungen_roh = [
        {"tx_hash": "aa" * 32, "amount": "30000", "num_confirmations": 3,
         "block_height": 900000, "time_stamp": "1757900000",
         "total_fees": "0", "label": ""},
        {"tx_hash": "bb" * 32, "amount": "-2141", "num_confirmations": 0,
         "block_height": 0, "time_stamp": "1757990000",
         "total_fees": "141", "label": ""},
    ]
    r = client.get("/api/lightning/bewegungen")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["bereit"] is True
    # Die unbestaetigte zuerst -- auf die wartet man.
    assert [b["txid"] for b in d["bewegungen"]] == ["bb" * 32, "aa" * 32]
    assert d["bewegungen"][0]["betrag_sat"] == -2141
    assert d["bewegungen"][0]["bestaetigungen"] == 0
    assert d["bewegungen"][1]["betrag_sat"] == 30000
    assert d["bewegungen"][1]["bestaetigungen"] == 3
    assert d["weitere"] == 0


def test_ohne_laufendes_lightning_gibt_es_keine_bewegungen(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    d = client.get("/api/lightning/bewegungen").json()
    assert d == {"bereit": False, "bewegungen": [], "weitere": 0}


def test_die_bewegungen_brauchen_eine_anmeldung(tmp_path):
    c = _client(tmp_path, anmelden=False)
    assert c.get("/api/lightning/bewegungen").status_code == 401


# ── Empfangen ueber Lightning (16.09.2026) ─────────────────────────────────
#
# Der Betreiber: "Rechnungen bezahlen gibt es ja schon ... solte halt nur auch geld
# rein bekommen". Bis dahin hatte die Anwendung keinen Endpunkt dafuer.

def test_eine_rechnung_laesst_sich_ausstellen(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/rechnung/erstellen",
                    json={"betrag": 1500, "zweck": "Kaffee", "gueltig_min": 30})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rechnung"] == "lnbc1500n1pbeispiel"
    assert d["kennung"] == "cd" * 32
    assert d["betrag_sat"] == 1500
    assert lnd_da.rechnung_bestellt["expiry"] == "1800"


def test_eine_rechnung_braucht_keine_pin(client, lnd_da):
    """Sie fordert nur -- sie bewegt nichts. Eine PIN davor waere ein
    Schloss ohne Tuer."""
    _richte_ein(client)
    _freigabe_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/rechnung/erstellen", json={"betrag": 10})
    assert r.status_code == 200, r.text


def test_die_eigenen_rechnungen_stehen_in_der_liste(client, lnd_da):
    import base64 as b64
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnungen_roh = [
        {"r_hash": b64.b64encode(bytes.fromhex("11" * 32)).decode(),
         "payment_request": "lnbc1", "memo": "Spende", "value": "0",
         "amt_paid_sat": "0", "creation_date": "1757000000",
         "settle_date": "0", "expiry": "3600", "state": "OPEN"},
    ]
    d = client.get("/api/lightning/rechnungen").json()
    assert d["bereit"] is True
    assert d["rechnungen"][0]["zweck"] == "Spende"
    assert d["rechnungen"][0]["zustand"] == "offen"
    assert d["rechnungen"][0]["betrag_sat"] == 0


def test_ohne_laufendes_lightning_gibt_es_keine_rechnungen(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    assert client.get("/api/lightning/rechnungen").json() == {
        "bereit": False, "rechnungen": [], "weitere": 0}


def test_die_rechnungen_brauchen_eine_anmeldung(tmp_path):
    c = _client(tmp_path, anmelden=False)
    assert c.get("/api/lightning/rechnungen").status_code == 401
    assert c.post("/api/lightning/rechnung/erstellen",
                  json={"betrag": 1}).status_code == 401


# ── Eine EINZELNE Rechnung (23.09.2026) ───────────────────────────────────
#
# Bis dahin gab es nur die Liste der letzten zwanzig, im Anzeigetakt
# nachgeladen. Wer einen QR-Code hinhaelt, will aber nicht wissen, ob unter
# den letzten zwanzig eine bezahlte ist -- er will wissen, ob DIESE eine
# gerade bezahlt wurde, und zwar in dem Augenblick.

KENNUNG_RECHNUNG = "cd" * 32


def _rechnung_roh(zustand="OPEN", **rest):
    import base64 as b64
    roh = {"r_hash": b64.b64encode(bytes.fromhex(KENNUNG_RECHNUNG)).decode(),
           "payment_request": "lnbc1500n1pbeispiel", "memo": "Kaffee",
           "value": "1500", "amt_paid_sat": "0", "settle_date": "0",
           "creation_date": "1758600000", "expiry": "3600", "state": zustand}
    roh.update(rest)
    return roh


def test_eine_einzelne_rechnung_laesst_sich_nachschlagen(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh()
    r = client.get("/api/lightning/rechnung/stand",
                   params={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kennung"] == KENNUNG_RECHNUNG
    assert d["zustand"] == "offen" and d["betrag_sat"] == 1500


def test_eine_unbekannte_rechnung_sagt_das_auch(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = None
    r = client.get("/api/lightning/rechnung/stand",
                   params={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "rechnung_unbekannt"


def test_das_abwarten_meldet_die_bezahlte_rechnung(client, lnd_da):
    """Der eigentliche Gewinn: kein Nachladen im Sekundentakt, sondern LND
    sagt selbst Bescheid, sobald das Geld da ist."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_strom = [
        _rechnung_roh("OPEN"),
        _rechnung_roh("SETTLED", amt_paid_sat="1500",
                      settle_date="1758600030"),
    ]
    r = client.get("/api/lightning/rechnung/abwarten",
                   params={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["zustand"] == "bezahlt" and d["bezahlt_sat"] == 1500
    assert lnd_da.abgewartet.startswith("/v2/invoices/subscribe/")


def test_ein_abwarten_ohne_ereignis_ist_kein_fehler(client, lnd_da):
    """Niemand hat bezahlt. Das ist der Normalfall -- und muss mit 200 und
    dem Stand von jetzt zurueckkommen, nicht mit einer Stoerungsmeldung, die
    bei jeder Runde einmal aufblitzt."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_strom = []                 # die Frist laeuft ab
    lnd_da.rechnung_einzeln = _rechnung_roh()
    r = client.get("/api/lightning/rechnung/abwarten",
                   params={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 200, r.text
    assert r.json()["zustand"] == "offen"


def test_eine_offene_rechnung_laesst_sich_zurueckziehen(client, lnd_da):
    import base64 as b64
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh()
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 200, r.text
    assert r.json()["zustand"] == "storniert"
    assert b64.urlsafe_b64decode(
        lnd_da.storniert["payment_hash"]) == bytes.fromhex(KENNUNG_RECHNUNG)


def test_eine_rechnung_mit_geld_darin_wird_nicht_angefasst(client, lnd_da):
    """"unterwegs" heisst: der Zahlende haelt bereits Geld fest. Ein Storno
    gaebe es ihm zurueck -- das ist die Bauart einer Halterechnung und keine
    Entscheidung, die hier nebenbei fallen soll."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh("ACCEPTED")
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 409
    assert r.json()["detail"]["meldung"] == "rechnung_nicht_offen"
    assert r.json()["detail"]["zustand"] == "unterwegs"
    assert lnd_da.storniert is None, "es darf nichts hinausgegangen sein"


def test_eine_schon_bezahlte_rechnung_wird_nicht_storniert(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh("SETTLED")
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 409
    assert lnd_da.storniert is None


def test_das_zuruecknehmen_braucht_keine_pin(client, lnd_da):
    """Wie das Ausstellen: es bewegt kein Geld, es nimmt eine Forderung
    zurueck."""
    _richte_ein(client)
    _freigabe_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh()
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 200, r.text


def test_eine_kennung_falscher_laenge_kommt_nicht_durch(client, lnd_da):
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": "cd" * 10})
    assert r.status_code == 422
    assert lnd_da.storniert is None


def test_ohne_laufendes_lightning_gibt_es_keinen_rechnungsstand(client,
                                                                lnd_da):
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    for pfad in ("/api/lightning/rechnung/stand",
                 "/api/lightning/rechnung/abwarten"):
        r = client.get(pfad, params={"kennung": KENNUNG_RECHNUNG})
        assert r.status_code == 409, pfad
        assert r.json()["detail"]["meldung"] == "lightning_nicht_bereit"


def test_ein_schweigendes_lnd_meldet_sich_als_solches(client, lnd_da):
    """Nicht "Rechnung unbekannt" -- das waere eine Aussage ueber die
    Rechnung, und die hat hier niemand geprueft."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_strom = []
    lnd_da.rechnung_einzeln = _rechnung_roh()    # da waere sie ja
    lnd_da.beschaeftigt_auf = {"/v2/invoices/lookup"}
    for pfad in ("/api/lightning/rechnung/stand",
                 "/api/lightning/rechnung/abwarten"):
        r = client.get(pfad, params={"kennung": KENNUNG_RECHNUNG})
        assert r.status_code == 503, pfad
        assert r.json()["detail"]["meldung"] == "lnd_antwortet_nicht"
    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 503
    assert lnd_da.storniert is None


def test_das_abwarten_einer_unbekannten_rechnung_sagt_das_auch(client, lnd_da):
    """Der Strom schweigt, das Nachschlagen findet nichts -- dann ist die
    Kennung falsch und nicht der Knoten kaputt."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_strom = []
    lnd_da.rechnung_einzeln = None
    r = client.get("/api/lightning/rechnung/abwarten",
                   params={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "rechnung_unbekannt"


def test_ein_storno_das_lnd_ablehnt_wird_gemeldet(client, lnd_da):
    """LND kann nein sagen, auch wenn der Zustand eben noch "offen" war --
    zwischen Nachsehen und Handeln liegt ein Augenblick, in dem bezahlt
    worden sein kann."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    lnd_da.rechnung_einzeln = _rechnung_roh()
    from satcortex import lnd as lnd_modul
    echt = lnd_da.ruf

    def ruf(pfad, macaroon="readonly", daten=None, zeitlimit=None,
            methode=None):
        if pfad == "/v2/invoices/cancel":
            raise lnd_modul.LndFehler("invoice already settled")
        return echt(pfad, macaroon, daten, zeitlimit, methode)
    lnd_da.ruf = ruf

    r = client.post("/api/lightning/rechnung/stornieren",
                    json={"kennung": KENNUNG_RECHNUNG})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "rechnung_nicht_storniert"


def test_die_einzelne_rechnung_braucht_eine_anmeldung(tmp_path):
    c = _client(tmp_path, anmelden=False)
    assert c.get("/api/lightning/rechnung/stand",
                 params={"kennung": KENNUNG_RECHNUNG}).status_code == 401
    assert c.get("/api/lightning/rechnung/abwarten",
                 params={"kennung": KENNUNG_RECHNUNG}).status_code == 401
    assert c.post("/api/lightning/rechnung/stornieren",
                  json={"kennung": KENNUNG_RECHNUNG}).status_code == 401


# ── Die Uebersicht braucht Guthaben, ohne die teure Kanal-Antwort ──────────

def test_die_lightning_antwort_traegt_das_guthaben(client, lnd_da):
    """Aus dem Betrieb, 16.09.2026 wollte das Guthaben auf der Startseite. Die
    grosse Kanal-Antwort zieht getinfo, Kanalliste, Graph und
    Weiterleitungen mit -- fuer eine Seite, die alle zehn Sekunden laedt,
    waere das zu teuer."""
    _richte_ein(client)
    lnd_da.stand = "SERVER_ACTIVE"
    d = client.get("/api/lightning").json()
    assert d["guthaben"]["kette_gesamt"] == 150000
    assert d["guthaben"]["kette_bestaetigt"] == 100000


def test_ohne_offene_wallet_gibt_es_kein_guthaben(client, lnd_da):
    """Null waere gelogen: das hiesse "nichts da", nicht "kann ich nicht
    sehen"."""
    _richte_ein(client)
    lnd_da.stand = "LOCKED"
    assert client.get("/api/lightning").json()["guthaben"] is None



# ══════════ Fuenf Endpunkte, die die Oberflaeche benutzt und niemand prueft ══
#
# Gefunden am 16.09.2026 beim Durchgang durch alle 82 Endpunkte: die Module
# dahinter sind gruendlich geprueft (test_logs.py, test_lnd.py, test_store.py),
# die TUER davor war es nicht. Bei den Protokollen sitzt genau dort die
# Pruefung des Quellennamens -- faellt sie aus, ist der Endpunkt ein
# Dateibetrachter fuer alles, was der Container sieht.

def test_die_protokollquellen_kommen_ueber_die_api(client):
    d = client.get("/api/logs").json()
    assert [q["name"] for q in d["quellen"]] == ["satcortex", "bitcoind",
                                                 "lnd", "tor"]


def test_ein_protokoll_laesst_sich_ueber_die_api_lesen(client):
    ordner = client.tmp / "fast" / "bitcoind"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "debug.log").write_text("erste Zeile\nzweite Zeile\n")
    d = client.get("/api/logs/bitcoind").json()
    assert d["da"] is True
    assert d["zeilen"] == ["erste Zeile", "zweite Zeile"]


def test_ein_fehlendes_protokoll_ist_ein_zustand_keine_stoerung(client):
    """Vor der Einrichtung gibt es die Datei schlicht noch nicht. Das gehoert
    angezeigt, nicht als Fehler gemeldet."""
    d = client.get("/api/logs/lnd").json()
    assert d["da"] is False and d["zeilen"] == []


@pytest.mark.parametrize("boese", [
    "erfunden",
    "bitcoind%2F..%2F..%2Fetc%2Fpasswd",
    "..%2F..%2Fetc%2Fpasswd",
])
def test_eine_erfundene_protokollquelle_kommt_nicht_durch(client, boese):
    """Der Name ist das EINZIGE, was von aussen kommt."""
    assert client.get(f"/api/logs/{boese}").status_code == 404


# ── Der HTLC-Strom ─────────────────────────────────────────────────────────

def test_der_htlc_strom_zaehlt_die_fehlschlaege_je_kanal(client):
    """Nicht "es ist etwas schiefgegangen", sondern "an diesem Kanal ist
    dreimal das Guthaben ausgegangen". Das eine ist eine Meldung, das andere
    ein Handgriff."""
    import time as zeitmodul

    from satcortex import store as st
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    jetzt = int(zeitmodul.time() * 1000)
    ablage.htlc_merken({"zeit_ms": jetzt, "art": "weiterleitung",
                        "rein_kanal": "1", "raus_kanal": "2",
                        "betrag": 5000, "gebuehr": 2, "grund": None})
    for _ in range(3):
        ablage.htlc_merken({"zeit_ms": jetzt, "art": "link_fehl",
                            "rein_kanal": "1", "raus_kanal": "2",
                            "betrag": 0, "gebuehr": 0,
                            "grund": "INSUFFICIENT_BALANCE"})

    d = client.get("/api/lightning/htlc").json()
    assert d["speicher"] is True
    assert len(d["ereignisse"]) == 4
    nach_grund = {g["grund"]: g["anzahl"] for g in d["gruende"]}
    assert nach_grund["INSUFFICIENT_BALANCE"] == 3, d["gruende"]


def test_die_grenze_des_htlc_stroms_wird_eingehalten(client):
    import time as zeitmodul

    from satcortex import store as st
    ablage = st.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    for i in range(5):
        ablage.htlc_merken({"zeit_ms": int(zeitmodul.time() * 1000) + i,
                            "art": "weiterleitung", "rein_kanal": "1",
                            "raus_kanal": "2", "betrag": 1, "gebuehr": 0,
                            "grund": None})
    assert len(client.get("/api/lightning/htlc?grenze=2").json()["ereignisse"]) == 2


# ── Eine Gegenstelle ansehen, bevor man einen Kanal zu ihr oeffnet ─────────

KENNUNG_IM_GRAPH = "02" + "ee" * 32


class LndMitGraph(LndVollstaendig):
    def __init__(self):
        super().__init__()
        self.graph_leer = False

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        nackt = pfad.split("?")[0]
        if nackt.startswith("/v1/graph/node/"):
            self.gefragt.append(pfad)
            if self.graph_leer:
                from satcortex import lnd as lnd_modul
                raise lnd_modul.LndFehler("unable to find node")
            import time as zeitmodul
            return {"node": {"alias": "ACINQ",
                             "last_update": int(zeitmodul.time()),
                             "addresses": [{"addr": "203.0.113.9:9735"}]},
                    "num_channels": 42, "total_capacity": "500000000"}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_graph(monkeypatch):
    from satcortex import api as api_modul
    knoten = LndMitGraph()
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_eine_gegenstelle_laesst_sich_vorher_ansehen(client, lnd_graph):
    _richte_ein(client)
    d = client.post("/api/lightning/gegenstelle/ansehen",
                    json={"gegenstelle": KENNUNG_IM_GRAPH}).json()
    assert d["bekannt"] is True
    assert d["alias"] == "ACINQ"
    assert d["kanaele"] == 42
    # Die drei Befunde stehen einzeln da, statt zu einer Note verrechnet zu
    # werden -- wer einen hinnehmen will, soll wissen, welchen.
    assert d["still"] is False
    assert d["ohne_adresse"] is False


def test_die_auskunft_kommt_aus_dem_eigenen_graphen(client, lnd_graph):
    """Keine fremde Seite, kein Konto, keine Abfrage, die jemandem verraet,
    mit wem wir einen Kanal erwaegen."""
    _richte_ein(client)
    client.post("/api/lightning/gegenstelle/ansehen",
                json={"gegenstelle": KENNUNG_IM_GRAPH})
    assert any(p.startswith("/v1/graph/node/") for p in lnd_graph.gefragt)
    assert lnd_graph.geoeffnet is None, "das Ansehen darf keinen Kanal oeffnen"


def test_eine_unbekannte_gegenstelle_ist_eine_auskunft_kein_fehler(client,
                                                                   lnd_graph):
    _richte_ein(client)
    lnd_graph.graph_leer = True
    r = client.post("/api/lightning/gegenstelle/ansehen",
                    json={"gegenstelle": KENNUNG_IM_GRAPH})
    assert r.status_code == 200
    assert r.json()["bekannt"] is False


def test_was_keine_knotenkennung_ist_faellt_vorher_auf(client, lnd_graph):
    _richte_ein(client)
    r = client.post("/api/lightning/gegenstelle/ansehen",
                    json={"gegenstelle": "zu-kurz"})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "gegenstelle_unlesbar"


# ── Der Ausweis gegenueber Stellen wie LightningNetwork+ ──────────────────

class LndMitAusweis(LndMitMacaroon):
    def __init__(self):
        super().__init__()
        self.unterschrieben = None
        self.kennung_zurueck = "03ab"          # der eigene Schluessel

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        nackt = pfad.split("?")[0]
        if nackt == "/v1/signmessage":
            self.benutzte_macaroons.append((nackt, macaroon))
            self.unterschrieben = daten
            return {"signature": "rbyfd" * 20}
        if nackt == "/v1/verifymessage":
            self.benutzte_macaroons.append((nackt, macaroon))
            return {"valid": True, "pubkey": self.kennung_zurueck}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_ausweis(monkeypatch, tmp_path):
    from satcortex import api as api_modul
    knoten = LndMitAusweis()
    knoten.macaroons = tmp_path / "mac"
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def test_der_ausweis_unterschreibt_und_rechnet_gleich_nach(client, lnd_ausweis):
    import base64 as b64

    _richte_ein(client)
    d = client.post("/api/lightning/unterschrift",
                    json={"text": "lightningnetwork+ probe"}).json()
    assert d["unterschrift"] == "rbyfd" * 20
    assert d["geprueft"] is True, "die eigene Unterschrift wurde nicht geprueft"
    # REST erwartet die Nachricht als base64 -- wer das verwechselt, bekommt
    # ein schlichtes "ungueltig" und sucht an der falschen Stelle.
    assert b64.b64decode(
        lnd_ausweis.unterschrieben["msg"]).decode() == "lightningnetwork+ probe"


def test_ein_fremder_schluessel_faellt_beim_nachrechnen_auf(client, lnd_ausweis):
    """Die eigentliche Probe ist der Schluessel, den LND dabei nennt: er MUSS
    der eigene Knotenschluessel sein."""
    _richte_ein(client)
    lnd_ausweis.kennung_zurueck = "03ff"
    d = client.post("/api/lightning/unterschrift",
                    json={"text": "probe"}).json()
    assert d["unterschrift"], "die Unterschrift gehoert dem Nutzer, auch so"
    assert d["geprueft"] is False


def test_ohne_text_gibt_es_nichts_zu_unterschreiben(client, lnd_ausweis):
    """Ohne diese Abfrage lief ein leerer Text in denselben Fehler wie ein
    abgestuerztes LND und meldete "antwortet nicht" -- eine Auskunft, die in
    die falsche Richtung schickt."""
    r = client.post("/api/lightning/unterschrift", json={"text": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "unt_leer"


# ------------------------------------------- Einen Wachturm einzeln pruefen ---

def _turmpruefung(client, monkeypatch, tuerme, antworten):
    """LND liefert die Turmliste, die Erreichbarkeitspruefung die Befunde."""
    from satcortex import api as api_modul
    lnd_modul = api_modul.lnd
    monkeypatch.setattr(lnd_modul, "zustand", lambda k: {"stand": "bereit"})
    monkeypatch.setattr(lnd_modul, "eigener_turm",
                        lambda k: {"aktiv": False, "kennung": "", "uris": [],
                                   "lauscht": []})
    monkeypatch.setattr(lnd_modul, "wachtuerme", lambda k, eigen="": tuerme)
    gefragt = []

    def pruefe_eine(adresse, port, proxy, zeitlimit=30.0, handschlag=True,
                    erweitert=False):
        gefragt.append((adresse, port, handschlag, erweitert))
        return dict(antworten[adresse], adresse=adresse, port=port)
    monkeypatch.setattr(api_modul.erreichbar, "pruefe_eine", pruefe_eine)
    return gefragt


def test_ein_toter_turm_wird_als_solcher_erkannt(client, lnd_kanaele,
                                                 monkeypatch):
    """DER BEFUND VOM 17.09.2026: zwei eingetragene Tuerme waren tot, ihre
    .onion gab es nicht mehr. In der Liste stand bei beiden "keine Sitzung" --
    dasselbe, was auch dasteht, wenn es schlicht nichts zu sichern gibt."""
    _richte_ein(client)
    gefragt = _turmpruefung(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "adressen": ["tot.onion:9911"],
         "arten": {}, "sitzungen": 0, "eigen": False}],
        {"tot.onion": {"erreichbar": None, "geprueft": False,
                       "grund": "nicht_pruefbar",
                       "einzelheit": "Tor findet die Beschreibung nicht"}})

    d = client.post("/api/lightning/wachtuerme/pruefen",
                    json={"kennung": KENNUNG_TURM}).json()
    assert d["erreichbar"] is False and d["geprueft"] is False
    assert d["adressen"][0]["grund"] == "nicht_pruefbar"
    # Gemessen wird ueber Tors Messport, ohne Bitcoin-Handschlag: ein Turm
    # spricht kein Bitcoin.
    assert gefragt == [("tot.onion", 9911, False, True)]


def test_ein_lebender_turm_meldet_sich_erreichbar(client, lnd_kanaele,
                                                  monkeypatch):
    _richte_ein(client)
    _turmpruefung(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "adressen": ["lebt.onion:9911"],
         "arten": {}, "sitzungen": 0, "eigen": False}],
        {"lebt.onion": {"erreichbar": True, "geprueft": True, "grund": ""}})

    d = client.post("/api/lightning/wachtuerme/pruefen",
                    json={"kennung": KENNUNG_TURM}).json()
    assert d["erreichbar"] is True
    # Erreichbar UND trotzdem keine Sitzung heisst: es liegt nicht am Turm.
    assert d["eigen"] is False


def test_eine_erreichbare_adresse_genuegt(client, lnd_kanaele, monkeypatch):
    """Ein Turm mit Clearnet- UND Onion-Adresse ist da, sobald eine traegt."""
    _richte_ein(client)
    _turmpruefung(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "eigen": False, "arten": {}, "sitzungen": 0,
         "adressen": ["203.0.113.7:9911", "lebt.onion:9911"]}],
        {"203.0.113.7": {"erreichbar": False, "geprueft": True,
                         "grund": "abgelehnt"},
         "lebt.onion": {"erreichbar": True, "geprueft": True, "grund": ""}})

    d = client.post("/api/lightning/wachtuerme/pruefen",
                    json={"kennung": KENNUNG_TURM}).json()
    assert d["erreichbar"] is True
    assert len(d["adressen"]) == 2


def test_ein_unbekannter_turm_ist_kein_serverfehler(client, lnd_kanaele,
                                                    monkeypatch):
    _richte_ein(client)
    _turmpruefung(client, monkeypatch, [], {})
    r = client.post("/api/lightning/wachtuerme/pruefen",
                    json={"kennung": KENNUNG_TURM})
    assert r.status_code == 404


def test_beim_ersten_erfolg_wird_aufgehoert(client, lnd_kanaele, monkeypatch):
    """Eine erreichbare Adresse beantwortet die Frage.

    Die restlichen zu messen kostet je bis zu eine halbe Minute ueber Tor --
    und genau daran ist der erste Anlauf am 18.09.2026 gescheitert: der
    Browser brach ab, bevor der Knoten fertig war.
    """
    _richte_ein(client)
    gefragt = _turmpruefung(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "eigen": False, "arten": {}, "sitzungen": 0,
         "adressen": ["lebt.onion:9911", "zweit.onion:9911"]}],
        {"lebt.onion": {"erreichbar": True, "geprueft": True, "grund": ""},
         "zweit.onion": {"erreichbar": True, "geprueft": True, "grund": ""}})

    d = client.post("/api/lightning/wachtuerme/pruefen",
                    json={"kennung": KENNUNG_TURM}).json()
    assert d["erreichbar"] is True
    assert len(gefragt) == 1, "die zweite Adresse wurde unnoetig gemessen"


def test_mehr_adressen_als_erlaubt_werden_nicht_alle_gemessen(
        client, lnd_kanaele, monkeypatch):
    """Ungedeckelt waere das ein Aufruf, den jeder Browser abbricht."""
    from satcortex import api as api_modul
    _richte_ein(client)
    viele = [f"t{i}.onion:9911" for i in range(6)]
    gefragt = _turmpruefung(client, monkeypatch, [
        {"kennung": KENNUNG_TURM, "eigen": False, "arten": {}, "sitzungen": 0,
         "adressen": viele}],
        {f"t{i}.onion": {"erreichbar": False, "geprueft": True,
                         "grund": "abgelehnt"} for i in range(6)})

    client.post("/api/lightning/wachtuerme/pruefen",
                json={"kennung": KENNUNG_TURM})
    assert len(gefragt) == api_modul.WACHTURM_PRUEF_HOECHSTENS


# ── Was das Netz fuers Weiterleiten nimmt ──────────────────────────────────
#
# Aus dem Betrieb, 18.09.2026: "wenn dann 100% und alle 3 Stufen gemeinsam!
# Obergrenze ist max wert der letzten 4 wochen und untergrenze ist dann min
# wert der letzten 4 wochen fuer die automatik".
#
# Drei Stufen: messen, aufheben, nachfuehren. Geprueft wird jede einzeln --
# und vor allem, dass die dritte NICHT laeuft, solange die zweite noch keine
# Grundlage hat.

def _graphstrom(saetze, eigen_satz=None, eigene_kennung="03ab"):
    """Ein DescribeGraph-Dokument, wie LND es ueber REST schickt."""
    import json as js
    kanten = []
    for satz in saetze:
        kanten.append({"channel_id": "1", "node1_pub": "aa", "node2_pub": "bb",
                       "node1_policy": {"fee_rate_milli_msat": str(satz),
                                        "fee_base_msat": "1000"}})
    if eigen_satz is not None:
        kanten.append({"channel_id": "2", "node1_pub": eigene_kennung,
                       "node2_pub": "cc",
                       "node1_policy": {"fee_rate_milli_msat": str(eigen_satz),
                                        "fee_base_msat": "0"}})
    roh = js.dumps({"nodes": [{"alias": "irgendwer"}],
                    "edges": kanten}).encode("utf-8")
    return [roh[i:i + 64] for i in range(0, len(roh), 64)]


class LndMitNetzgraph(LndMitMacaroon):
    """Ein Knoten, der auch DescribeGraph beantwortet."""

    def __init__(self, saetze=(50, 100, 150, 200, 900), eigen=None,
                 graph_aktuell=True, kanaele=True):
        super().__init__()
        self.saetze = list(saetze)
        self.eigen = eigen
        self.graph_aktuell = graph_aktuell
        self.hat_kanaele = kanaele
        self.graph_gelesen = 0

    def brocken(self, pfad, macaroon="readonly", zeitlimit=None,
                haeppchen=256 * 1024):
        self.graph_gelesen += 1
        for stueck in _graphstrom(self.saetze, self.eigen):
            yield stueck

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        nackt = pfad.split("?")[0]
        if nackt == "/v1/getinfo":
            d = dict(super().ruf(pfad, macaroon, daten, zeitlimit))
            d["synced_to_graph"] = self.graph_aktuell
            return d
        if nackt == "/v1/channels" and daten is None and not self.hat_kanaele:
            return {"channels": []}
        return super().ruf(pfad, macaroon, daten, zeitlimit)


@pytest.fixture
def lnd_netzgraph(monkeypatch, tmp_path):
    from satcortex import api as api_modul
    knoten = LndMitNetzgraph()
    knoten.macaroons = tmp_path / "mac"
    knoten.macaroons.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


def _messen(client):
    r = client.post("/api/lightning/netzgebuehren/messen")
    client.app.state.hintergrund_stoppen()
    return r


def _messreihe(client, werte, ab=1):
    """Vergangene Messtage direkt in die Ablage schreiben.

    Vier Wochen abzuwarten ist keine Pruefmethode.
    """
    from satcortex import store as store_modul
    a = store_modul.Ablage(str(client.tmp / "fast" / "app" / "auswertung.db"))
    for i, wert in enumerate(werte):
        a.netzgebuehren_merken(f"2026-08-{ab + i:02d}", 1000 + i,
                               {"median_ppm": wert, "eigen": {}})
    a.schliesse()


def test_der_netz_median_kommt_aus_dem_eigenen_graphen(client, lnd_netzgraph):
    _richte_ein(client)
    _messen(client)
    d = client.get("/api/lightning/netzgebuehren").json()
    assert lnd_netzgraph.graph_gelesen == 1
    assert d["heute"]["median_ppm"] == 150
    assert d["heute"]["linien"] == 5
    assert d["heute"]["basis_median_msat"] == 1000
    assert d["fehler"] == ""


def test_ohne_fertige_netzkarte_wird_nicht_gemessen(client, lnd_netzgraph):
    """Ein frisch gestarteter Knoten kennt ein paar hundert Kanaele statt
    dreissigtausend. Ein Median daraus ist eine Zahl ohne Deckung -- und er
    stuende vier Wochen lang im Band."""
    _richte_ein(client)
    lnd_netzgraph.graph_aktuell = False
    _messen(client)
    d = client.get("/api/lightning/netzgebuehren").json()
    assert d["heute"] is None
    assert d["fehler"] == "graph_nicht_aktuell"


def test_der_eigene_satz_wird_mitgelesen(client, lnd_netzgraph):
    _richte_ein(client)
    lnd_netzgraph.eigen = 77
    _messen(client)
    d = client.get("/api/lightning/netzgebuehren").json()
    assert d["heute"]["eigen_ppm"] == 77
    assert d["jetzt_ppm"] == 77


def test_ohne_messreihe_sagt_der_vorschlag_dass_er_noch_sammelt(
        client, lnd_netzgraph):
    _richte_ein(client)
    _messen(client)
    d = client.get("/api/lightning/netzgebuehren").json()
    assert d["vorschlag"]["grund"] == "sammelt_noch"
    assert d["vorschlag"]["handeln"] is False
    assert d["band"]["tage"] == 0


def test_die_automatik_setzt_den_satz_erst_mit_genug_messtagen(
        client, lnd_netzgraph):
    """Die Sperre, die am meisten wert ist: einschalten darf man sofort,
    wirken darf sie erst, wenn es ein Band gibt."""
    _richte_ein(client)
    _messen(client)
    r = client.post("/api/lightning/gebuehrenautomatik",
                    json={"automatik": True})
    assert r.json()["automatik"] is True
    assert r.json()["getan"] is False
    assert r.json()["grund"] == "sammelt_noch"
    assert lnd_netzgraph.gebuehren is None


def test_mit_messreihe_zieht_die_automatik_den_satz_nach(
        client, lnd_netzgraph):
    _richte_ein(client)
    _messreihe(client, [120, 130, 125, 140, 135, 128, 132, 138])
    lnd_netzgraph.eigen = 40           # weit weg vom Netz
    _messen(client)
    r = client.post("/api/lightning/gebuehrenautomatik",
                    json={"automatik": True})
    assert r.json()["getan"] is True
    # Sechs Linien im Netz: 40, 50, 100, 150, 200, 900 -- Median 125. Der
    # eigene Kanal zaehlt dabei mit; er IST ein Teil des Netzes.
    # 125 liegt im Band 120-140, wird also unveraendert uebernommen.
    assert (r.json()["satz_ppm"], r.json()["grund"]) == (125, "median")
    assert lnd_netzgraph.gebuehren["fee_rate_ppm"] == 125
    # Fuer ALLE Kanaele -- einzelne nach Liquiditaetsrichtung zu steuern ist
    # etwas anderes und bleibt Handarbeit.
    assert lnd_netzgraph.gebuehren["global"] is True
    # Und die Grundgebuehr bleibt, wo sie war.
    assert lnd_netzgraph.gebuehren["base_fee_msat"] == "0"


def test_die_obergrenze_kommt_aus_den_vier_wochen_und_nicht_von_heute(
        client, lnd_netzgraph):
    """Genau die Bedingung des Betreibers, und der Grund, warum der heutige Tag NICHT
    ins eigene Band gehoert: sonst deckelt sich ein Ausreisser selbst auf
    seinen eigenen Wert und schlaegt ungebremst durch."""
    _richte_ein(client)
    _messreihe(client, [100, 105, 102, 108, 104, 101, 106, 103])
    lnd_netzgraph.saetze = [5000, 6000, 7000, 8000, 9000]   # Ausreisser
    _messen(client)
    d = client.get("/api/lightning/netzgebuehren").json()
    assert d["heute"]["median_ppm"] == 7000
    assert d["band"]["oben_ppm"] == 108
    assert d["vorschlag"]["satz_ppm"] == 108


def test_ohne_kanaele_wird_nichts_gesetzt(client, lnd_netzgraph):
    """LND wuerde den Aufruf klaglos annehmen und nichts tun -- und in der
    Oberflaeche staende "gesetzt", wo nichts gesetzt wurde."""
    _richte_ein(client)
    _messreihe(client, [120, 130, 125, 140, 135, 128, 132, 138])
    lnd_netzgraph.hat_kanaele = False
    _messen(client)
    r = client.post("/api/lightning/gebuehrenautomatik",
                    json={"automatik": True})
    assert r.json()["getan"] is False and r.json()["grund"] == "keine_kanaele"
    assert lnd_netzgraph.gebuehren is None


def test_ausschalten_ruehrt_die_gebuehren_nicht_an(client, lnd_netzgraph):
    """Der Satz bleibt stehen, wo er steht. Eine Automatik, die beim
    Abschalten auf irgendeinen Ausgangswert zurueckspringt, waere eine
    Ueberraschung an einer Stelle, wo keine hingehoert."""
    _richte_ein(client)
    _messreihe(client, [120, 130, 125, 140, 135, 128, 132, 138])
    _messen(client)
    client.post("/api/lightning/gebuehrenautomatik", json={"automatik": True})
    lnd_netzgraph.gebuehren = None
    r = client.post("/api/lightning/gebuehrenautomatik",
                    json={"automatik": False})
    assert r.json()["automatik"] is False
    assert lnd_netzgraph.gebuehren is None


def test_die_automatik_ueberlebt_einen_neustart(client, lnd_netzgraph):
    _richte_ein(client)
    client.post("/api/lightning/gebuehrenautomatik", json={"automatik": True})
    assert client.get("/api/lightning/netzgebuehren").json()["automatik"]
    import json as js
    wahl = js.loads((client.tmp / "config" / "einrichtung.json")
                    .read_text(encoding="utf-8"))["gebuehrenwahl"]
    assert wahl["automatik"] is True


def test_zweimal_am_selben_tag_wird_nicht_zweimal_gemessen(
        client, lnd_netzgraph):
    """Der Graph ist zweistellige Megabyte. Der Waechter laeuft alle paar
    Minuten -- ohne diese Sperre waere das ein Dauerlauf."""
    _richte_ein(client)
    client.app.state.gebuehren_wenn_faellig()
    client.app.state.hintergrund_stoppen()
    client.app.state.gebuehren_wenn_faellig()
    client.app.state.hintergrund_stoppen()
    assert lnd_netzgraph.graph_gelesen == 1


def test_nach_dem_setzen_steht_nicht_gleich_wieder_ein_vorschlag_da(
        client, lnd_netzgraph):
    """Zwei Quellen fuer "was gilt gerade", und die Reihenfolge entscheidet.

    Die Messung liest aus dem Graphen, was das NETZ von uns sieht -- die
    ehrlichere Zahl, weil sie nicht aus unserer eigenen Erinnerung stammt.
    Sie ist aber von heute frueh. Hat die Automatik seitdem gesetzt, ist sie
    ueberholt, und in der Oberflaeche stuende "wuerde jetzt 125 ppm setzen"
    fuer genau den Wert, der eine Sekunde vorher gesetzt wurde.
    """
    _richte_ein(client)
    _messreihe(client, [120, 130, 125, 140, 135, 128, 132, 138])
    lnd_netzgraph.eigen = 40
    _messen(client)
    gesetzt = client.post("/api/lightning/gebuehrenautomatik",
                          json={"automatik": True}).json()
    assert gesetzt["satz_ppm"] == 125
    d = client.get("/api/lightning/netzgebuehren").json()
    # Der Graph sagt immer noch 40 -- das ist die Messung von vorhin.
    assert d["heute"]["eigen_ppm"] == 40
    # Was GILT, ist trotzdem der gesetzte Wert.
    assert d["jetzt_ppm"] == 125
    assert d["vorschlag"]["grund"] == "unveraendert"
    assert d["vorschlag"]["handeln"] is False


def test_kurz_nach_dem_hochfahren_wird_trotzdem_gemessen(
        client, lnd_netzgraph, monkeypatch):
    """DER FEHLER, DEN DIE CI GEFANGEN HAT UND DER MAC NICHT.

    time.monotonic() zaehlt ab dem SYSTEMSTART. Die Sperre gegen zu haeufige
    Wiederholung verglich gegen einen Anfangswert von 0.0 -- und 0.0 ist auf
    dieser Uhr ein echter, erreichbarer Zeitpunkt und kein "nie". Auf einer
    Maschine, die seit weniger als einer Stunde laeuft, heisst 0.0 damit
    "gerade eben erst versucht", und gemessen wird gar nicht.

    Auf einem Entwicklungsrechner mit 26 Stunden Laufzeit faellt das nie auf.
    Auf einem frisch gestarteten CI-Laeufer sofort -- und auf einem NAS nach
    jedem Neustart, eine Stunde lang, ohne ein Wort im Protokoll.

    Dieselbe Falle wie `zeitlimit or self.zeitlimit` am 17.09.2026: ein
    Vorgabewert, der auch ein gueltiger Wert ist.
    """
    from satcortex import api as api_modul
    monkeypatch.setattr(api_modul.time, "monotonic", lambda: 5.0)
    _richte_ein(client)
    client.app.state.gebuehren_wenn_faellig()
    client.app.state.hintergrund_stoppen()
    assert lnd_netzgraph.graph_gelesen == 1


# ── Was der Knoten an eingehenden Kanaelen annimmt ─────────────────────────
#
# Befund vom 18.09.2026, gefunden an dem ersten Liquiditaets-Ring: der
# laeuft ueber 100.000 sat, und minchansize stand fest im Quelltext auf genau
# 100.000. Das geht gerade noch durch -- LNDs Wortlaut ist "Incoming channels
# SMALLER than this will be rejected" -- aber der Abstand ist null. Oeffnet
# die Gegenstelle aus irgendeinem Grund 99.500, lehnt der eigene Knoten den
# Kanal ab, den man sich gerade verdient hat. Und es saehe aus, als haette
# der andere nicht geliefert.
#
# Ausgerechnet die Einstellung, die darueber entscheidet, ob man ein Geschenk
# annehmen darf, war nicht erreichbar.

def test_die_untergrenze_steht_mit_ihren_grenzen_in_der_auskunft(client):
    d = client.get("/api/lightning/name").json()
    assert d["minchansize"] == nodeconfig.MINCHANSIZE_VORGABE
    assert d["minchansize_min"] == nodeconfig.MINCHANSIZE_MIN
    assert d["minchansize_max"] == nodeconfig.MINCHANSIZE_MAX


def test_die_gewaehlte_untergrenze_landet_in_der_lnd_conf(client, monkeypatch):
    pfad = _lnd_conf(client, monkeypatch)
    r = client.post("/api/lightning/name",
                    json={"alias": "MyLightningNode", "minchansize": 50000})
    assert r.status_code == 200, r.text
    assert r.json()["minchansize"] == 50000
    assert "minchansize=50000" in pfad.read_text()


def test_sie_ueberlebt_einen_neustart(client, monkeypatch):
    _lnd_conf(client, monkeypatch)
    client.post("/api/lightning/name",
                json={"alias": "MyLightningNode", "minchansize": 50000})
    assert client.get("/api/lightning/name").json()["minchansize"] == 50000


def test_eine_null_heisst_nicht_mitgeschickt_und_nicht_null(client, monkeypatch):
    """Dieselbe Falle wie ueberall: ein Vorgabewert, der auch ein Wert ist.

    Eine aeltere Oberflaeche -- oder ein Aufruf, der nur den Namen aendern
    will -- schickt kein minchansize mit. Wuerde die fehlende Angabe als
    "null" gelesen, drehte jeder Klick auf "Namen speichern" die Untergrenze
    still auf die Vorgabe zurueck. Der Nutzer haette sie eingestellt, und sie
    waere beim naechsten unbeteiligten Speichern wieder weg.
    """
    pfad = _lnd_conf(client, monkeypatch)
    client.post("/api/lightning/name",
                json={"alias": "MyLightningNode", "minchansize": 50000})
    r = client.post("/api/lightning/name", json={"alias": "Anderer Name"})
    assert r.status_code == 200, r.text
    assert r.json()["minchansize"] == 50000
    assert "minchansize=50000" in pfad.read_text()


@pytest.mark.parametrize("wert", [19999, 16_777_216])
def test_werte_ausserhalb_der_spanne_werden_abgelehnt(client, monkeypatch, wert):
    """Unter LNDs eigener Untergrenze entsteht ohnehin kein Kanal; ueber der
    groessten Kanalgroesse ohne Wumbo lehnt man JEDEN gewoehnlichen ab --
    das waere kein Einstellwert mehr, sondern ein Tippfehler."""
    _lnd_conf(client, monkeypatch)
    r = client.post("/api/lightning/name",
                    json={"alias": "MyLightningNode", "minchansize": wert})
    assert r.status_code == 400
    assert r.json()["detail"]["meldung"] == "minchansize_ungueltig"


# ── Die Uhr der Kette in der Uebersicht ────────────────────────────────────

def test_status_zaehlt_bis_zur_naechsten_halbierung(client, monkeypatch):
    """Der Betreiber, 21.09.2026: "anzahl der bloecke bis zum naechsten
    halving .. geschaetztes datum .. und wie hoch die revard ist".

    Gerechnet, nicht geholt: die Hoehe liegt ohnehin in der Antwort.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 967_296, "kopfzeilen": 967_296,
        "fortschritt": 1.0, "im_erstsync": False, "belegt_bytes": 1,
        "verbindungen_ein": 3, "verbindungen_aus": 10, "erreichbar": True,
        "blockzeit": 1_758_400_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})
    h = client.get("/api/status").json()["halbierung"]
    assert h["naechste_hoehe"] == 1_050_000
    assert h["bloecke_bis"] == 82_704
    assert h["belohnung_sat"] == 312_500_000
    assert h["belohnung_danach_sat"] == 156_250_000
    assert h["geschaetzt_ts"] > time.time()


def test_die_halbierung_zaehlt_ab_der_spitze_des_netzes(client, monkeypatch):
    """DER PUNKT, an dem es sonst falsch waere.

    Waehrend des Abgleichs steht die eigene Hoehe Jahre zurueck. Von ihr aus
    zu zaehlen ergaebe eine Auskunft ueber eine Halbierung, die laengst war.
    Die Kopfzeilen kennt der Knoten dagegen nach Minuten -- und sie sind die
    Spitze, die das Netz gerade hat.
    """
    from satcortex import rpc as rpc_modul
    _richte_ein(client)

    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 400_000, "kopfzeilen": 967_296,
        "fortschritt": 0.07, "im_erstsync": True, "belegt_bytes": 1,
        "verbindungen_ein": 0, "verbindungen_aus": 10, "erreichbar": False,
        "blockzeit": 1_452_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})
    h = client.get("/api/status").json()["halbierung"]
    assert h["hoehe"] == 967_296                  # nicht 400.000
    assert h["naechste_hoehe"] == 1_050_000
    # Waehrend des Abgleichs ist der eigene Takt nicht messbar -- unsere
    # Bloecke sind von 2016. Dann der Zielabstand, und die Antwort sagt es.
    assert h["gemessen"] is False


# ── Ein Zeitlimit ist kein Fehlschlag (Befund vom 22.09.2026) ──────────────
#
# Beim Audit der Geldwege gefunden: lnd.py unterscheidet sauber zwischen "LND
# ist weg" (NichtErreichbar) und "LND antwortet nicht rechtzeitig"
# (Beschaeftigt). Nur ERBT Beschaeftigt von NichtErreichbar -- und wer nur die
# Oberklasse faengt, macht aus beidem dieselbe Meldung.
#
# Beim Zahlen und Umschichten war das richtig gebaut. Bei den zwei
# unwiderruflichen ON-CHAIN-Vorgaengen nicht: "LND antwortet nicht" liest sich
# wie "es ist nichts passiert" -- und der naechste Griff ist, es noch einmal
# zu versuchen. On-Chain gibt es dagegen keinen Schutz: der zweite Versuch
# ist eine zweite Transaktion.

def test_ein_zeitlimit_beim_senden_heisst_nicht_dass_nichts_geschah(
        client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    lnd_da.beschaeftigt_auf = {"/v1/transactions"}
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 504, a.text
    assert a.json()["detail"]["meldung"] == "sendung_unklar"


def test_ein_zeitlimit_beim_kanal_oeffnen_heisst_nicht_dass_nichts_geschah(
        client, lnd_da, monkeypatch):
    """Das Oeffnen ist eine On-Chain-Transaktion wie das Senden."""
    _sendebereit(client, lnd_da, monkeypatch)
    lnd_da.beschaeftigt_auf = {"/v1/channels"}
    a = client.post("/api/lightning/kanal/oeffnen",
                    json={"gegenstelle": "02" + "ab" * 32 + "@127.0.0.1:9735",
                          "betrag": 1_000_000})
    assert a.status_code == 504, a.text
    assert a.json()["detail"]["meldung"] == "kanal_unklar"


def test_ein_wirklich_abwesendes_lnd_bleibt_unterscheidbar(client, lnd_da,
                                                           monkeypatch):
    """Die Gegenprobe: "weg" darf NICHT zu "unklar" werden.

    Sonst waere der Fix nur ein Umbenennen -- und jemand suchte nach einer
    Transaktion, die es nie gab.
    """
    from satcortex import lnd as lnd_modul
    _sendebereit(client, lnd_da, monkeypatch)

    def weg(*_a, **_kw):
        raise lnd_modul.NichtErreichbar("connection refused")
    monkeypatch.setattr(lnd_modul, "sende", weg)
    a = client.post("/api/lightning/senden",
                    json={"adresse": ADRESSE, "betrag": 100_000})
    assert a.status_code == 503
    assert a.json()["detail"]["meldung"] == "lnd_antwortet_nicht"


# ── Die uebrigen Befunde des Audits ────────────────────────────────────────

def test_die_pin_wird_auch_beim_loeschen_als_erstes_geprueft(client, lnd_da):
    """Fuenf der sechs Geldwege pruefen die PIN als allererste Zeile.

    Das Loeschen sah zuerst nach, ob gerade eine Wallet-Arbeit laeuft -- der
    Kommentar DARUNTER sagte dabei "ZUERST die PIN, vor jeder anderen
    Pruefung". Die Zeile widersprach also dem Satz, der sie erklaerte.
    """
    _richte_ein(client)
    _freigabe_ein(client)
    a = _tilgung(client, pin="000001")
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "pin_falsch"


def test_ein_zu_kleiner_kanal_wird_auch_beim_oeffnen_abgewiesen(
        client, lnd_da, monkeypatch):
    """Die Schaetzung prueft die Mindestgroesse, das Oeffnen bisher nicht --
    wer den Endpunkt direkt ruft, umging sie."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/kanal/oeffnen",
                    json={"gegenstelle": "02" + "ab" * 32 + "@127.0.0.1:9735",
                          "betrag": 5_000})
    assert a.status_code == 400, a.text
    assert a.json()["detail"]["meldung"] == "kanal_zu_klein"


def test_eine_gebuehrengrenze_von_null_bleibt_null(client, lnd_voll,
                                                   monkeypatch):
    """"0" hiess bisher "nimm den Vorschlag" -- die Sentinel-Falle aus der
    eigenen AGENTS.md, diesmal beim Geld. Wer ausdruecklich null schreibt,
    meint null: zahle nur, wenn die Route nichts kostet."""
    _kanalbereit(client, monkeypatch)
    a = client.post("/api/lightning/rechnung/zahlen", json={
        "rechnung": "lnbc15u1abc", "gebuehrengrenze": 0, "pin": PIN})
    assert a.status_code == 200, a.text
    assert lnd_voll.gezahlt["fee_limit_sat"] == "0"


def test_ohne_angabe_gilt_weiter_der_vorschlag(client, lnd_voll, monkeypatch):
    """Die Gegenprobe: das Feld wegzulassen muss den Vorschlag ergeben --
    die Oberflaeche schickt es naemlich gar nicht mit."""
    from satcortex import lnd as lnd_modul
    _kanalbereit(client, monkeypatch)
    client.post("/api/lightning/rechnung/zahlen", json={
        "rechnung": "lnbc15u1abc", "pin": PIN})
    assert lnd_voll.gezahlt["fee_limit_sat"] == str(
        lnd_modul.gebuehrgrenze(1500))


# ── Eine haengende Ueberweisung nachbessern (22.09.2026) ───────────────────

def test_die_pin_steht_vor_dem_nachbessern(client, lnd_voll):
    """Es kostet zusaetzliche Gebuehr -- also dieselbe PIN wie beim Senden,
    und die zuerst."""
    _richte_ein(client)
    _freigabe_ein(client)
    a = client.post("/api/lightning/senden/nachbessern",
                    json={"txid": "a" * 64, "ausgang": 1})
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


def test_nachbessern_gibt_den_satz_aus_dem_eigenen_knoten(client, lnd_da,
                                                          monkeypatch):
    """Wie beim Senden: der Satz kommt aus estimatesmartfee des EIGENEN
    bitcoind, nicht aus einer Zahl, die jemand tippt."""
    _sendebereit(client, lnd_da, monkeypatch)
    a = client.post("/api/lightning/senden/nachbessern",
                    json={"txid": "a" * 64, "ausgang": 1, "tempo": "schnell"})
    assert a.status_code == 200, a.text
    gesendet = lnd_da.gesendet_an["/v2/wallet/bumpfee"]
    assert gesendet["sat_per_vbyte"] == "12"
    assert int(gesendet["budget"]) > 0


def test_ein_zeitlimit_beim_nachbessern_heisst_nicht_dass_nichts_geschah(
        client, lnd_da, monkeypatch):
    _sendebereit(client, lnd_da, monkeypatch)
    lnd_da.beschaeftigt_auf = {"/v2/wallet/bumpfee"}
    a = client.post("/api/lightning/senden/nachbessern",
                    json={"txid": "a" * 64, "ausgang": 1})
    assert a.status_code == 504
    assert a.json()["detail"]["meldung"] == "sendung_unklar"


# ── Das Wegwissen in der Oberflaeche (22.09.2026) ──────────────────────────

def test_das_wegwissen_braucht_keine_pin(client, lnd_voll, monkeypatch):
    """Es wird nur gelesen. Eine PIN, die man fuer eine Auskunft tippt,
    tippt man irgendwann gedankenlos -- und genau das soll sie nicht
    werden."""
    _kanalbereit(client, monkeypatch)
    a = client.get("/api/lightning/wegwissen")
    assert a.status_code == 200, a.text
    d = a.json()
    assert "paare" in d and "letzte" in d


def test_ohne_lightning_gibt_es_kein_wegwissen(client):
    _richte_ein(client)
    a = client.get("/api/lightning/wegwissen")
    assert a.status_code in (409, 503)
