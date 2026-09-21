"""Tests zu den Befunden der Sicherheitsprüfung vom 23.08.2026.

Jeder Test hier steht für einen Fund. Sie sind bewusst so geschrieben, dass sie
FEHLSCHLAGEN, wenn jemand die Absicherung später wieder herausnimmt.
"""
import json
import shutil
from collections import namedtuple

import pytest
from fastapi.testclient import TestClient

from satcortex import api, auth, settings

Nutzung = namedtuple("Nutzung", "total used free")
GB = 1024 ** 3
ZUGANG = {"benutzer": "testnutzer", "passwort": "ein-gutes-langes-passwort"}


def baue_client(tmp_path):
    """Eine frische Anwendung auf einem vorhandenen Verzeichnis -- genau das,
    was ein Neustart des Containers ist."""
    c = TestClient(api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"))))
    c.tmp = tmp_path
    return c


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    return baue_client(tmp_path)


@pytest.fixture
def angemeldet(client):
    client.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    return client


# ── Fund 1: es gab ueberhaupt keine Anmeldung ────────────────────────────────

GESCHUETZT_GET = ["/api/status", "/api/speicher", "/api/einrichtung"]
GESCHUETZT_POST = [
    ("/api/einrichtung/weiter", {"antworten": {}}),
    ("/api/einrichtung/zurueck", None),
    ("/api/leistung/vorschau", {"speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
                                "verbindungen": 80, "tor_aktiv": True}),
    ("/api/einrichtung/abschliessen", {"speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
                                       "verbindungen": 80, "tor_aktiv": True}),
]


@pytest.mark.parametrize("pfad", GESCHUETZT_GET)
def test_lesen_ohne_anmeldung_wird_abgewiesen(client, pfad):
    assert client.get(pfad).status_code == 401


@pytest.mark.parametrize("pfad,koerper", GESCHUETZT_POST)
def test_schreiben_ohne_anmeldung_wird_abgewiesen(client, pfad, koerper):
    assert client.post(pfad, json=koerper).status_code == 401


def test_nach_anmeldung_geht_es(angemeldet):
    assert angemeldet.get("/api/status").status_code == 200


def test_abmelden_entzieht_den_zugang(angemeldet):
    angemeldet.post("/api/abmelden")
    assert angemeldet.get("/api/status").status_code == 401


def test_erfundenes_sitzungsmerkmal_nuetzt_nichts(client):
    client.cookies.set("satcortex_sitzung", "ausgedacht")
    assert client.get("/api/status").status_code == 401


# ── Fund 2: Kontoanlage ──────────────────────────────────────────────────────

def test_zweites_konto_wird_verweigert(angemeldet):
    """Sonst uebernimmt der Naechste im Netz einfach das Geraet."""
    assert angemeldet.post("/api/konto/anlegen", json=ZUGANG).status_code == 409


def test_kurzes_passwort_wird_abgelehnt(client):
    r = client.post("/api/konto/anlegen", json={"benutzer": "a", "passwort": "kurz"})
    assert r.status_code == 422


def test_passwort_wird_nicht_im_klartext_abgelegt(angemeldet):
    inhalt = (angemeldet.tmp / "config" / "konto.json").read_text()
    assert ZUGANG["passwort"] not in inhalt
    assert "scrypt$" in inhalt


def test_kontodatei_ist_nur_fuer_den_besitzer_lesbar(angemeldet):
    modus = (angemeldet.tmp / "config" / "konto.json").stat().st_mode & 0o777
    assert modus == 0o600


def test_falsches_passwort_meldet_nicht_an(angemeldet):
    angemeldet.post("/api/abmelden")
    r = angemeldet.post("/api/anmelden",
                        json={"benutzer": "testnutzer", "passwort": "falsch-aber-lang"})
    assert r.status_code == 401
    assert angemeldet.get("/api/status").status_code == 401


def test_durchprobieren_wird_gebremst(client):
    client.post("/api/konto/anlegen", json=ZUGANG)
    client.post("/api/abmelden")
    for _ in range(auth.MAX_FEHLVERSUCHE):
        client.post("/api/anmelden", json={"benutzer": "testnutzer", "passwort": "falsch-aber-lang"})
    # Ab jetzt auch mit dem RICHTIGEN Passwort gesperrt.
    r = client.post("/api/anmelden", json=ZUGANG)
    assert r.status_code == 401
    assert r.json()["detail"]["meldung"] == "zu_viele_versuche"


# ── Fund 3: laufender Knoten liess sich umkonfigurieren ──────────────────────

def test_einrichtung_laesst_sich_nicht_wiederholen(angemeldet):
    """Sonst kann jeder Angemeldete Tor abschalten, den Upload entfesseln oder
    die Verbindungen auf das Minimum druecken -- Letzteres erleichtert eine
    Eclipse-Attacke erheblich."""
    daten = {"speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
             "verbindungen": 80, "tor_aktiv": True}
    assert angemeldet.post("/api/einrichtung/abschliessen", json=daten).status_code == 200
    # 12 und nicht weniger: darunter weist schon die Eingabepruefung ab
    # (422), und dann pruefte dieser Test sie statt der Sperre.
    angriff = {"speichergrenze_mb": 400, "upload_gb_pro_monat": 0,
               "verbindungen": 12, "tor_aktiv": False}
    r = angemeldet.post("/api/einrichtung/abschliessen", json=angriff)
    assert r.status_code == 409

    text = (angemeldet.tmp / "config" / "bitcoind.conf").read_text()
    assert "maxconnections=80" in text          # unveraendert
    assert "onion=tor:9050" in text.splitlines()  # Tor blieb an


# ── Fund 4: RPC-Zugangsdaten wurden weggeworfen ──────────────────────────────

def test_rpc_zugangsdaten_werden_behalten(angemeldet):
    angemeldet.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True})
    geheim = angemeldet.tmp / "config" / "bitcoind-rpc.geheim.json"
    assert geheim.exists(), "ohne das kann die Anwendung nie mit bitcoind sprechen"
    assert geheim.stat().st_mode & 0o777 == 0o600
    daten = json.loads(geheim.read_text())
    conf = (angemeldet.tmp / "config" / "bitcoind.conf").read_text()
    assert daten["rpcauth"] in conf
    assert daten["passwort"] not in conf        # nur der Hash geht an die Dienste


# ── Fund 5: unbegrenzte Nutzlast fuellte die Platte ──────────────────────────

def test_uebergrosse_antwort_wird_abgewiesen(angemeldet):
    r = angemeldet.post("/api/einrichtung/weiter",
                        json={"antworten": {"x": "y" * 200_000}})
    assert r.status_code == 413


# ── Fund 6: unbekannte API-Pfade lieferten die Startseite ────────────────────

def test_unbekannter_api_pfad_ist_404(client):
    r = client.get("/api/gibtsnicht")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


# ── Sitzungs-Keks ────────────────────────────────────────────────────────────

def test_keks_ist_gegen_javascript_und_fremdseiten_geschuetzt(client):
    """httponly und samesite -- aber samesite=LAX, nicht strict.

    Das ist seit dem 11.09.2026 eine Bedingung, keine Lockerung: bei der
    Rueckkehr vom Ausweisdienst (Pocket ID) ist der Aufruf ein Seitenwechsel
    von fremder Seite. Unter "strict" schickt der Browser das Cookie dabei
    NICHT mit -- die Anmeldung landete stumm wieder am Anfang.

    "lax" sendet bei solchen Wechseln nur bei GET. Schreibende Aufrufe von
    fremden Seiten bleiben damit weiterhin draussen, und genau darum ging es
    bei "strict".
    """
    r = client.post("/api/konto/anlegen", json=ZUGANG)
    gesetzt = r.headers.get("set-cookie", "").lower()
    assert "httponly" in gesetzt        # nicht aus JavaScript auslesbar
    assert "samesite=lax" in gesetzt
    assert "samesite=strict" not in gesetzt


def test_hinter_einem_tls_proxy_bekommt_der_keks_sein_secure(monkeypatch,
                                                             tmp_path):
    """Der Fund vom 11.09.2026.

    "secure" hing bis dahin allein daran, ob die ANWENDUNG das Zertifikat
    haelt. Hinter einem Reverse Proxy tut sie das nicht -- der Browser sieht
    trotzdem https. Das Cookie bekam also ausgerechnet im Internet-Betrieb
    kein Secure und durfte damit auch ueber Klartext mitgeschickt werden.
    """
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)

    def keks(**zusatz):
        c = TestClient(api.baue_app(settings.Einstellungen(
            bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
            config_dir=str(tmp_path / "config"), **zusatz)))
        r = c.post("/api/anmelden", json=ZUGANG)
        return r.headers.get("set-cookie", "").lower()

    # Erst ein Konto anlegen, danach immer nur anmelden.
    TestClient(api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config")))).post(
            "/api/konto/anlegen", json=ZUGANG).raise_for_status()

    assert "secure" not in keks()                     # nackt im Heimnetz
    assert "secure" in keks(tls_extern=True)          # Proxy davor


def test_alles_in_config_hat_enge_rechte(tmp_path):
    """Kein Verlass auf die Standardrechte -- jede Datei nachmessen.

    Vorher setzte nur das Schreiben von Geheimnissen die Rechte. Die
    Konfigurationsdateien landeten mit dem, was die umask gerade vorgab --
    typisch 0644, also fuer jeden Benutzer des Geraets lesbar. In bitcoind.conf
    steht die rpcauth-Zeile.
    """
    from satcortex import services

    ablage = services.Konfigurationsablage(str(tmp_path))
    ablage.schreibe("bitcoind", "rpcauth=satcortex:abc$def\n")
    ablage.schreibe_geheim("bitcoind-rpc", {"benutzer": "x", "passwort": "y", "rpcauth": "z"})
    ablage.gib_frei("bitcoind")

    erlaubt = {0o600, 0o640}
    for datei in sorted(tmp_path.iterdir()):
        modus = datei.stat().st_mode & 0o777
        assert modus in erlaubt, f"{datei.name} hat {oct(modus)}, erlaubt sind {[oct(m) for m in erlaubt]}"


# ── Fund 7: jeder Neustart meldete den Nutzer ab ─────────────────────────────
#
# Aufgefallen am 25.08.2026 auf dem Geraet: Der Assistent blieb im
# Speicher-Schritt stehen und zeigte "Die Anwendung antwortet nicht. Laeuft der
# Container noch?" -- waehrend der Container einwandfrei antwortete und
# korrekt 401 schickte. Die Sitzungen lagen nur im Arbeitsspeicher.

def test_sitzung_ueberlebt_einen_neustart(angemeldet):
    keks = angemeldet.cookies.get("satcortex_sitzung")
    assert keks, "ohne Sitzungsmerkmal prueft dieser Test nichts"

    nachher = baue_client(angemeldet.tmp)
    nachher.cookies.set("satcortex_sitzung", keks)
    assert nachher.get("/api/status").status_code == 200, \
        "nach einem Neustart war der Nutzer abgemeldet -- mitten im Assistenten"


def test_abmelden_wirkt_auch_ueber_einen_neustart(angemeldet):
    keks = angemeldet.cookies.get("satcortex_sitzung")
    angemeldet.post("/api/abmelden")

    nachher = baue_client(angemeldet.tmp)
    nachher.cookies.set("satcortex_sitzung", keks)
    assert nachher.get("/api/status").status_code == 401


def test_sitzungsmerkmal_steht_nicht_im_klartext_auf_der_platte(angemeldet):
    """Wer die Datei liest, soll damit keine fremde Sitzung uebernehmen koennen."""
    keks = angemeldet.cookies.get("satcortex_sitzung")
    datei = angemeldet.tmp / "config" / "sitzungen.json"
    assert datei.exists()
    assert keks not in datei.read_text(encoding="utf-8")


def test_sitzungsdatei_ist_nur_fuer_den_besitzer_lesbar(angemeldet):
    modus = (angemeldet.tmp / "config" / "sitzungen.json").stat().st_mode & 0o777
    assert modus == 0o600


def test_beschaedigte_sitzungsdatei_sperrt_niemanden_aus(angemeldet):
    """Lieber neu anmelden als eine Anwendung, die nicht mehr startet."""
    (angemeldet.tmp / "config" / "sitzungen.json").write_text("{kaputt", encoding="utf-8")
    nachher = baue_client(angemeldet.tmp)
    assert nachher.get("/api/zustand").status_code == 200
    assert nachher.get("/api/status").status_code == 401


# ── Die laufende Fassung muss ablesbar sein ──────────────────────────────────
#
# Am 25.08.2026 lief auf dem Geraet stundenlang 0.2.3, waehrend wir ueber 0.2.6
# sprachen. Erkennbar war das nur an der Dateigroesse der ausgelieferten
# app.js. Das darf nicht der Weg sein.

def test_version_steht_ohne_anmeldung_bereit(client):
    """Gerade wenn man sich nicht anmelden kann, will man wissen, was laeuft."""
    d = client.get("/api/zustand").json()
    assert "version" in d
    assert d["version"], "leere Version ist so nutzlos wie gar keine"


# ── Nicht beschreibbare Ablage: erklaeren statt sterben (25.08.2026) ─────────

def test_anwendung_startet_auch_ohne_schreibrechte(tmp_path, monkeypatch):
    """Auf einem UGREEN-NAS mit falscher PGID gehoerte der Ordner einer
    Gruppe, die es dort nicht gibt. Die Anwendung starb dann beim Anlegen
    ihrer Ablage -- der Nutzer sah nur einen Container in der
    Neustartschleife und nirgends einen Grund."""
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    gesperrt = tmp_path / "gesperrt"
    gesperrt.mkdir()
    gesperrt.chmod(0o500)          # lesbar, nicht beschreibbar
    try:
        c = TestClient(api.baue_app(settings.Einstellungen(
            bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
            config_dir=str(gesperrt))))
        d = c.get("/api/zustand").json()
        assert d["ablage_bereit"] is False, "der Zustand muss ehrlich gemeldet werden"
        assert d["ablage_pfad"] == str(gesperrt)
    finally:
        gesperrt.chmod(0o700)


def test_bei_gesunder_ablage_meldet_sie_sich_bereit(client):
    assert client.get("/api/zustand").json()["ablage_bereit"] is True


# ── Verschluesselung: freiwillig, aber dann richtig ──────────────────────────

def test_ohne_zertifikat_kein_secure_flag(client):
    """Unter HTTP wuerde secure das Sitzungsmerkmal unbrauchbar machen --
    niemand kaeme mehr herein."""
    r = client.post("/api/anmelden", json=ZUGANG)
    gesetzt = r.headers.get("set-cookie", "").lower()
    assert "secure" not in gesetzt


def test_mit_zertifikat_traegt_der_keks_secure(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    c = TestClient(api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"),
        tls_cert="/fast/config/tls/fullchain.pem",
        tls_key="/fast/config/tls/privkey.pem")))
    r = c.post("/api/konto/anlegen", json=ZUGANG)
    assert "secure" in r.headers.get("set-cookie", "").lower()


def test_halbe_angabe_gilt_nicht_als_verschluesselt():
    """Nur eines von beiden ist ein Konfigurationsfehler, kein Wunsch nach
    Klartext -- und darf nicht als Verschluesselung durchgehen."""
    halb = settings.Einstellungen(tls_cert="/nur/eins.pem", tls_key="")
    assert halb.tls_aktiv is False


def test_zustand_meldet_ob_verschluesselt_wird(client):
    assert client.get("/api/zustand").json()["verschluesselt"] is False


# ── Fund vom 27.08.2026: die Anwendung startete nicht mehr ──────────────────

def test_app_startet_auch_wenn_fast_nicht_beschreibbar_ist(tmp_path):
    """Der CI-Probelauf haengt /fast mit einem fremden Eigentuemer ein -- so
    wie ein NAS, auf dem der Nutzer seine Ordner im Dateimanager anlegt. Mit
    Phase 6 starb die Anwendung daran beim Import, weil die Auswertungs-
    datenbank im Konstruktor angelegt wird.

    Das Abbild war gebaut und veroeffentlicht; nur weil die CI das Abbild
    WIRKLICH STARTET, ist es nicht auf des Betreibers Geraet gelandet.

    Der Test baut die Anwendung gegen einen schreibgeschuetzten Ordner. Sie
    muss stehen -- die Auswertung darf ausfallen, der Assistent nicht.
    """
    bulk = tmp_path / "bulk"; bulk.mkdir()
    fast = tmp_path / "fast"; fast.mkdir()
    (fast / "config").mkdir()
    fast.chmod(0o555)                     # lesen und betreten, nicht schreiben
    try:
        konf = settings.Einstellungen(
            bulk=str(bulk), fast=str(fast), config_dir=str(fast / "config"))
        c = TestClient(api.baue_app(konf))
        assert c.get("/healthz").status_code == 200
        # Und sie sagt, warum die Auswertung fehlt, statt sie leer zu zeigen.
        c.post("/api/konto/anlegen", json=ZUGANG)
        d = c.get("/api/auswertung").json()
        assert d["verfuegbar"] is False and d["grund"]
    finally:
        fast.chmod(0o755)


# ── Nichts Blockierendes in der Ereignisschleife ───────────────────────────
#
# Befund vom 01.09.2026. erreichbarkeit_pruefen() war die einzige
# async-Funktion unter den Endpunkten. Die eigentliche Messung lief korrek
# in einem Thread -- die Vorbereitung davor nicht: eine DNS-Aufloesung und
# ein getblockchaininfo mit fuenfzehn Sekunden Geduld, mitten in der
# Ereignisschleife. Solange die liefen, stand die ganze Oberflaeche.
#
# Das ist keine Frage des Stils. FastAPI gibt SYNCHRONE Endpunkte in einen
# Threadpool und laesst ASYNCHRONE in der Schleife laufen -- wer dort etwas
# Blockierendes aufruft, legt jede andere Abfrage still mit. Der Test macht
# daraus eine Regel statt einer Erinnerung.

# Was blockiert: Netz, Platte, Unterprozess. Die Namen stammen aus diesem
# Projekt -- eine neue blockierende Funktion gehoert hier eingetragen.
BLOCKIERT = {
    "ruf", "kettenlage", "mempoollage", "lage_holen", "lage_mit_grund",
    "lage_mit_grund_gebuendelt", "lies", "schreibe", "gib_frei", "sperre",
    "loese_auf", "pruefe", "pruefe_eine", "verorte", "gegenstellen",
    "kanaele", "naechster_block", "gebuehren", "schwierigkeit",
    "urlopen", "run", "check_output", "read_text", "write_text",
}


def _blockierende_aufrufe(quelle):
    """Jeder Aufruf in einer async-Funktion, der nicht abgewartet wird."""
    import ast

    funde = []
    for fn in ast.walk(ast.parse(quelle.read_text(encoding="utf-8"))):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        # Was awaited wird, laeuft entweder selbst asynchron oder ueber
        # asyncio.to_thread -- beides ist in Ordnung.
        abgewartet = {
            f.func.id if isinstance(f.func, ast.Name) else f.func.attr
            for n in ast.walk(fn) if isinstance(n, ast.Await)
            for f in ast.walk(n) if isinstance(f, ast.Call)
            and isinstance(f.func, (ast.Name, ast.Attribute))
        }
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            if not isinstance(n.func, (ast.Name, ast.Attribute)):
                continue
            name = (n.func.id if isinstance(n.func, ast.Name)
                    else n.func.attr)
            if name in BLOCKIERT and name not in abgewartet:
                funde.append(f"{quelle.name}:{n.lineno} {fn.name}() -> {name}()")
    return funde


def test_keine_blockierenden_aufrufe_in_der_ereignisschleife():
    from pathlib import Path

    paket = Path(api.__file__).parent
    funde = []
    for datei in sorted(paket.glob("*.py")):
        funde += _blockierende_aufrufe(datei)
    assert not funde, (
        "In einer async-Funktion wird etwas Blockierendes ohne await "
        "aufgerufen -- das legt die gesamte Oberflaeche still. Entweder den "
        "Endpunkt synchron machen (dann nimmt FastAPI seinen Threadpool) "
        "oder asyncio.to_thread davorsetzen:\n  " + "\n  ".join(funde))


# ── Antworten der Schnittstelle duerfen nie aus dem Browser-Zwischenspeicher
#    kommen ──────────────────────────────────────────────────────────────
#
# Der Betreiber, 01.09.2026: "das was dann in der webui gespeichert wird wird nach
# einem refresh immer noch nicht gespeichert und wieder angezeigt". Das
# Ablegen war in Ordnung -- ueber einen vollstaendigen Neustart geprueft --
# und die ausgelieferten Dateien byte-identisch mit der Fassung. Es war das
# GET danach.
#
# RFC 9111 Abschnitt 3 erlaubt das Ablegen jeder Antwort mit einem Statuscode,
# der "heuristically cacheable" ist; 200 gehoert dazu. Abschnitt 4.2.2: "A
# cache MAY assign a heuristic expiration time when an explicit time is not
# specified." Ohne Angabe entscheidet also der Browser -- und Safari legt ab.


def test_api_antworten_sind_nicht_zwischenspeicherbar(angemeldet):
    for pfad in ("/api/zustand", "/api/status", "/api/knoten/netzwege"):
        r = angemeldet.get(pfad)
        kopf = r.headers.get("cache-control", "")
        assert "no-store" in kopf, f"{pfad} sendet '{kopf}'"
        assert r.headers.get("pragma") == "no-cache", pfad
        assert r.headers.get("expires") == "0", pfad


def test_die_oberflaeche_bleibt_nachfragbar(angemeldet):
    """no-cache heisst "vor der Wiederverwendung nachfragen" -- das soll fuer
    die statischen Dateien so bleiben, sonst wird jeder Aufruf teuer."""
    r = angemeldet.get("/index.html")
    assert r.headers.get("cache-control") == "no-cache"


# ── Nichts von aussen ──────────────────────────────────────────────────────
#
# Aus dem Betrieb, 08.09.2026: "mit google wollen wir nix zu tun haben .. wir
# bleiben unser eigener knoten und teil des netzwerkes, jede info die wir
# brauchen kommt aus dem netzwerk und nicht von extern."
#
# Die Oberflaeche hielt das schon -- aber als Gewohnheit, nicht als Regel.
# Eine einzige spaeter eingefuegte Zeile haette es still gebrochen.


def test_die_oberflaeche_darf_nichts_von_aussen_laden(client):
    r = client.get("/")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "connect-src 'self'" in csp, \
        "die Oberflaeche darf nur den eigenen Knoten fragen"
    assert "frame-ancestors 'none'" in csp
    # Kein Schlupfloch: keine fremde Quelle, kein eval.
    assert "http://" not in csp and "https://" not in csp
    assert "unsafe-eval" not in csp


def test_die_ueblichen_kopfzeilen_stehen(client):
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_die_oberflaeche_laedt_nichts_von_fremden_adressen():
    """Die Kopfzeile ist die Durchsetzung, das hier der Beweis.

    Gesucht wird nach LADENDEN Stellen -- src, href, @import, url() -- und
    ausdruecklich nicht nach jedem Vorkommen von "https". Ein
    placeholder="https://…" im WebDAV-Feld ist ein Hinweis fuer den Nutzer
    und laedt gar nichts; ein erster Anlauf dieses Tests ist genau darueber
    gestolpert.
    """
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[2] / "web"
    ladend = re.compile(
        r"""(?:\bsrc\s*=|\bhref\s*=|@import\s+|\burl\()\s*["']?\s*"""
        r"""(https?:|//)""", re.I)
    treffer = []
    for name in ("index.html", "style.css", "app.js"):
        text = (web / name).read_text(encoding="utf-8")
        # Kommentare weg, sonst zaehlt eine Quellenangabe als Fund.
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"^\s*//[^\n]*", "", text, flags=re.M)
        for m in ladend.finditer(text):
            treffer.append(f"{name}: …{text[max(0, m.start()-30):m.end()+30]}…")
    assert not treffer, "laedt von aussen: " + " · ".join(treffer)


# ── Anmeldung ueber Pocket ID, und die Nottuer dahinter (11.09.2026) ────────
#
# Der Betreiber: "damit ich quasie kein lock in fenster mehr habe sonder nur noch
# pocket id mich einloggt" -- und auf die Rueckfrage, wie er dann noch
# hereinkommt, wenn der Ausweisdienst ausfaellt: das lokale Konto bleibt, aber
# nur im Heimnetz.
#
# Auf einem Geraet mit einer Wallet darin ist "ausgesperrt" kein hinnehmbarer
# Zustand -- und eine Nottuer, die auch von der Strasse aus aufgeht, ist keine.

OIDC = dict(oidc_issuer="https://id.example.test", oidc_client_id="satcortex",
            oidc_client_secret="geheim",
            oidc_rueckweg="https://btc.example.test/api/anmeldung/oidc/callback")


def _mit_oidc(tmp_path, monkeypatch, **zusatz):
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    app = api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"), **{**OIDC, **zusatz}))
    return TestClient(app, client=("192.168.178.20", 51234))


def test_ohne_ausweisdienst_bleibt_alles_wie_es_war(client):
    z = client.get("/api/zustand").json()
    assert z["oidc"] is False
    assert z["lokal_moeglich"] is True
    assert client.get("/api/anmeldung/oidc/start",
                      follow_redirects=False).status_code == 404


def test_mit_ausweisdienst_sagt_die_seite_es_auch(tmp_path, monkeypatch):
    c = _mit_oidc(tmp_path, monkeypatch)
    assert c.get("/api/zustand").json()["oidc"] is True


def test_die_nottuer_geht_im_heimnetz_auf(tmp_path, monkeypatch):
    """Direkt aus dem Heimnetz, ohne Proxy dazwischen: das lokale Konto
    funktioniert weiter. Sonst waere der Knoten bei einem Ausfall des
    Ausweisdienstes nur noch ueber Dateien auf der NAS erreichbar."""
    c = _mit_oidc(tmp_path, monkeypatch)
    assert c.get("/api/zustand").json()["lokal_moeglich"] is True
    c.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    c.post("/api/abmelden")
    assert c.post("/api/anmelden", json=ZUGANG).status_code == 200


def test_von_aussen_geht_nur_noch_der_ausweisdienst(tmp_path, monkeypatch):
    """DER PUNKT. Durch den Reverse Proxy hindurch nimmt der Server das
    lokale Passwort nicht mehr an -- auch nicht mit dem richtigen."""
    c = _mit_oidc(tmp_path, monkeypatch)
    c.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    c.post("/api/abmelden")
    durch_proxy = {"X-Forwarded-For": "203.0.113.9",
                   "X-Forwarded-Proto": "https"}
    assert c.get("/api/zustand", headers=durch_proxy
                 ).json()["lokal_moeglich"] is False
    r = c.post("/api/anmelden", json=ZUGANG, headers=durch_proxy)
    assert r.status_code == 403
    assert r.json()["detail"]["meldung"] == "nur_ueber_oidc"


def test_eine_fremde_adresse_ist_keine_nottuer(tmp_path, monkeypatch):
    """Auch ohne Weiterleitungskopf: eine oeffentliche Gegenstelle ist nicht
    das Heimnetz."""
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    c = TestClient(api.baue_app(settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"), **OIDC)),
        client=("8.8.8.8", 51234))
    # 203.0.113.x taugt hier NICHT: Python zaehlt die Dokumentationsbereiche
    # seit 3.12 zu is_private. Also eine wirklich oeffentliche Adresse.
    assert c.get("/api/zustand").json()["lokal_moeglich"] is False


def test_ein_erfundener_rueckweg_meldet_niemanden_an(tmp_path, monkeypatch):
    """Wer die Rueckkehradresse einfach aufruft, bekommt keine Sitzung --
    ohne passenden Vorgang gibt es keine Anmeldung."""
    c = _mit_oidc(tmp_path, monkeypatch)
    r = c.get("/api/anmeldung/oidc/callback?code=abc&state=ausgedacht",
              follow_redirects=False)
    assert r.status_code == 303
    assert "anmeldung=abgelaufen" in r.headers["location"]
    assert "set-cookie" not in {k.lower() for k in r.headers}
    assert c.get("/api/status").status_code == 401


def test_eine_absage_des_ausweisdienstes_wird_erklaert(tmp_path, monkeypatch):
    """Der haeufigste Fall ist kein Fehler, sondern eine Absage: der Nutzer
    gehoert keiner freigegebenen Gruppe an. Ohne ein Wort dazu saehe er nur
    wieder die Anmeldeseite und hielte sie fuer kaputt."""
    c = _mit_oidc(tmp_path, monkeypatch)
    r = c.get("/api/anmeldung/oidc/callback?error=access_denied&state=x",
              follow_redirects=False)
    assert "anmeldung=abgelehnt" in r.headers["location"]
