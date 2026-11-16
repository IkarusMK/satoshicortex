"""Tests zu den Befunden der Pruefung vom 15.11.2026: Anmeldung, Sitzungen und
die Web-Schicht.

Jeder Test steht fuer einen Befund und ist so geschrieben, dass er
FEHLSCHLAEGT, wenn die Behebung wieder herausgenommen wird. Alle sind vor der
Behebung rot gelaufen -- das steht jeweils in der Zeile "Vorher" darunter.
"""
import shutil
import threading
import time
from collections import namedtuple

import pytest
from fastapi.testclient import TestClient

from satcortex import api, auth, nachrichten, oidc, settings

Nutzung = namedtuple("Nutzung", "total used free")
GB = 1024 ** 3
ZUGANG = {"benutzer": "testnutzer", "passwort": "ein-gutes-langes-passwort"}
OIDC = dict(oidc_issuer="https://id.example.test", oidc_client_id="satcortex",
            oidc_client_secret="geheim",
            oidc_rueckweg="https://btc.example.test/api/anmeldung/oidc/callback")


def _konf(tmp_path, monkeypatch, **zusatz):
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * GB, 4000 * GB, 4000 * GB))
    for d in ("bulk", "fast"):
        (tmp_path / d).mkdir(exist_ok=True)
    return settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"), **zusatz)


def _app(tmp_path, monkeypatch, **zusatz):
    return api.baue_app(_konf(tmp_path, monkeypatch, **zusatz))


def _von(app, ip, port=51234):
    return TestClient(app, client=(ip, port))


@pytest.fixture
def app_oidc(tmp_path, monkeypatch):
    return _app(tmp_path, monkeypatch, **OIDC)


@pytest.fixture
def app_ohne(tmp_path, monkeypatch):
    return _app(tmp_path, monkeypatch)


# ── Befund 1: die Nottuer ging bei einem Proxy ohne Kopfzeilen auf ──────────
# Vorher: alle Tests dieses Abschnitts ausser dem LAN-Fall rot (lokal_moeglich
# war True bzw. /anmelden 200).

PROXY_OHNE_KOPF = "10.83.33.1"     # das Gateway des Compose-Netzes = der Host


def test_proxy_im_hostnetz_ohne_kopfzeilen_ist_keine_nottuer(app_oidc):
    """PROXY64 laeuft im Hostnetz und kommt ueber 127.0.0.1:<Port>; im
    Behaelter erscheint er als Gateway des Compose-Netzes -- ganz ohne
    Weiterleitungskopf."""
    c = _von(app_oidc, PROXY_OHNE_KOPF)
    assert c.get("/api/zustand").json()["lokal_moeglich"] is False


def test_anmelden_von_dort_wird_abgewiesen(app_oidc):
    lan = _von(app_oidc, "192.168.1.20")
    lan.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    r = _von(app_oidc, PROXY_OHNE_KOPF).post("/api/anmelden", json=ZUGANG)
    assert r.status_code == 403
    assert r.json()["detail"]["meldung"] == "nur_ueber_oidc"


def test_jeder_andere_rechner_im_compose_netz_zaehlt_auch_nicht(app_oidc):
    assert _von(app_oidc, "10.83.33.5").get(
        "/api/zustand").json()["lokal_moeglich"] is False


def test_das_praefix_kommt_aus_der_einstellung(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, netz_praefix="10.99.7", **OIDC)
    assert _von(app, "10.99.7.1").get(
        "/api/zustand").json()["lokal_moeglich"] is False
    # Das Standardnetz ist dann ein ganz gewoehnliches privates Netz.
    assert _von(app, "10.83.33.1").get(
        "/api/zustand").json()["lokal_moeglich"] is True


def test_ipv4_in_ipv6_schreibweise_umgeht_das_compose_netz_nicht(app_oidc):
    assert _von(app_oidc, "::ffff:10.83.33.1").get(
        "/api/zustand").json()["lokal_moeglich"] is False


@pytest.mark.parametrize("kopf", [
    "X-Real-IP", "Via", "CF-Connecting-IP", "True-Client-IP",
    "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto",
    "X-Forwarded-Port", "X-Forwarded-Server", "Forwarded",
])
@pytest.mark.parametrize("wert", ["1.2.3.4", ""])
def test_jede_proxykopfzeile_zaehlt_auch_leer(app_oidc, kopf, wert):
    c = _von(app_oidc, "192.168.1.20")
    assert c.get("/api/zustand", headers={kopf: wert}
                 ).json()["lokal_moeglich"] is False


def test_die_adresse_des_ausweisdienstes_ist_keine_nottuer(app_oidc):
    """Ein Proxy, der Host durchreicht, verraet sich ueber den Host: der
    steht in der Rueckkehradresse."""
    c = _von(app_oidc, "192.168.1.20")
    assert c.get("/api/zustand", headers={"Host": "btc.example.test"}
                 ).json()["lokal_moeglich"] is False
    assert c.get("/api/zustand", headers={"Host": "BTC.example.test:443"}
                 ).json()["lokal_moeglich"] is False


def test_ein_browser_im_heimnetz_kommt_weiter_herein(app_oidc):
    """Die Gegenprobe -- sonst waere die Tuer zugemauert, nicht gesichert."""
    c = _von(app_oidc, "192.168.1.20")
    assert c.get("/api/zustand", headers={"Host": "192.168.1.5:4080"}
                 ).json()["lokal_moeglich"] is True
    c.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    c.post("/api/abmelden")
    assert c.post("/api/anmelden", json=ZUGANG).status_code == 200


# ── Befund 2: /konto/anlegen kannte die Tuer nicht ─────────────────────────
# Vorher: der Aufruf ueber den Proxy bekam 200 und ein Sitzungs-Cookie.

def test_konto_anlegen_ueber_den_proxy_ist_gesperrt(app_oidc):
    c = _von(app_oidc, PROXY_OHNE_KOPF)
    r = c.post("/api/konto/anlegen", json=ZUGANG,
               headers={"X-Forwarded-For": "8.8.4.4"})
    assert r.status_code == 403
    assert r.json()["detail"]["meldung"] == "nur_ueber_oidc"
    assert "set-cookie" not in r.headers
    assert _von(app_oidc, "192.168.1.20").get(
        "/api/zustand").json()["konto_vorhanden"] is False


def test_konto_anlegen_im_heimnetz_geht_mit_ausweisdienst(app_oidc):
    r = _von(app_oidc, "192.168.1.20").post("/api/konto/anlegen", json=ZUGANG)
    assert r.status_code == 200


def test_konto_anlegen_ohne_ausweisdienst_bleibt_ueberall_offen(app_ohne):
    """Ohne Ausweisdienst gibt es keinen anderen Weg -- die Kontoanlage
    darf dort nicht an der Tuer scheitern."""
    r = _von(app_ohne, PROXY_OHNE_KOPF).post(
        "/api/konto/anlegen", json=ZUGANG,
        headers={"X-Forwarded-For": "8.8.4.4"})
    assert r.status_code == 200


# ── Befund 3: die Sperre war fuer alle Rechner gemeinsam ────────────────────
# Vorher: melde_an() kannte keinen Absender (TypeError) -- und in der alten
# Fassung sperrten acht Fehlversuche von irgendwoher den Besitzer 300 s aus.

@pytest.fixture
def verwaltung(tmp_path):
    v = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    v.lege_an("betreiber", "ein-langes-passwort")
    return v


@pytest.fixture
def uhr(monkeypatch):
    stand = [1_000_000.0]
    monkeypatch.setattr(auth.time, "time", lambda: stand[0])
    return stand


def _falsch(v, quelle, n=1):
    for _ in range(n):
        with pytest.raises(PermissionError):
            v.melde_an("betreiber", "falsch", quelle)


def test_ein_fremder_rechner_sperrt_den_besitzer_nicht_aus(verwaltung):
    _falsch(verwaltung, "192.168.1.66", auth.MAX_FEHLVERSUCHE)
    with pytest.raises(PermissionError, match="zu_viele"):
        verwaltung.melde_an("betreiber", "falsch", "192.168.1.66")
    assert verwaltung.melde_an("betreiber", "ein-langes-passwort",
                               "192.168.1.20")


def test_der_fehlerhafte_rechner_selbst_bleibt_gesperrt(verwaltung):
    _falsch(verwaltung, "192.168.1.66", auth.MAX_FEHLVERSUCHE)
    with pytest.raises(PermissionError, match="zu_viele"):
        verwaltung.melde_an("betreiber", "ein-langes-passwort", "192.168.1.66")


def test_die_sperre_eines_rechners_laeuft_ab(verwaltung, uhr):
    _falsch(verwaltung, "a", auth.MAX_FEHLVERSUCHE)
    uhr[0] += auth.SPERRE_SEKUNDEN + 1
    assert verwaltung.melde_an("betreiber", "ein-langes-passwort", "a")


def test_viele_rechner_zusammen_stossen_an_die_gemeinsame_decke(verwaltung):
    """Brute Force bleibt GLOBAL begrenzt: wer die Adresse wechselt, kommt an
    der Einzelsperre vorbei, nicht an der gemeinsamen Decke."""
    rechner = 0
    while len(verwaltung._fehlversuche.get(verwaltung.GLOBAL, [])) < auth.MAX_FEHLVERSUCHE_GESAMT:
        _falsch(verwaltung, f"r{rechner}", auth.MAX_FEHLVERSUCHE)
        rechner += 1
    # Ein erster Versuch eines frischen Rechners passiert die Bremse ...
    _falsch(verwaltung, "frisch-1")
    # ... der naechste, gleich danach, nicht mehr.
    with pytest.raises(PermissionError, match="zu_viele_versuche"):
        verwaltung.melde_an("betreiber", "falsch", "frisch-2")


def test_der_besitzer_kommt_auch_unter_dauerfeuer_herein(verwaltung, uhr):
    """DER PUNKT der Konstruktion: die Decke sperrt nicht aus, sie bremst.
    Nach der Wartezeit passt ein sauberer Rechner mit dem richtigen
    Passwort durch."""
    rechner = 0
    while len(verwaltung._fehlversuche.get(verwaltung.GLOBAL, [])) < auth.MAX_FEHLVERSUCHE_GESAMT:
        _falsch(verwaltung, f"r{rechner}", auth.MAX_FEHLVERSUCHE)
        rechner += 1
    _falsch(verwaltung, "angreifer")      # nimmt den freien Platz im Takt
    with pytest.raises(PermissionError, match="zu_viele_versuche"):
        verwaltung.melde_an("betreiber", "ein-langes-passwort", "besitzer")
    uhr[0] += auth.BREMSE_TAKT_SEKUNDEN + 1
    assert verwaltung.melde_an("betreiber", "ein-langes-passwort", "besitzer")


def test_unter_der_decke_bremst_nichts_anderes(verwaltung):
    _falsch(verwaltung, "a", 3)
    _falsch(verwaltung, "b", 3)
    assert verwaltung.melde_an("betreiber", "ein-langes-passwort", "c")


def test_die_fehlerdatei_bleibt_beschraenkt(verwaltung):
    for n in range(auth.MAX_ABSENDER * 3):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("betreiber", "falsch", f"10.1.{n // 250}.{n % 250}")
    assert len(verwaltung._fehlversuche) <= auth.MAX_ABSENDER + 2
    assert verwaltung.fehlerdatei.stat().st_size < 64 * 1024


def test_die_gezaehlten_absender_ueberleben_den_neustart(verwaltung, tmp_path):
    _falsch(verwaltung, "a", auth.MAX_FEHLVERSUCHE)
    frisch = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    with pytest.raises(PermissionError, match="zu_viele"):
        frisch.melde_an("betreiber", "ein-langes-passwort", "a")
    assert frisch.melde_an("betreiber", "ein-langes-passwort", "b")


def test_die_schnittstelle_zaehlt_nach_der_direkten_gegenstelle(app_ohne):
    """X-Forwarded-For ist frei erfunden und darf hier nie zaehlen: weder zum
    Aussperren eines anderen noch zum Umgehen der eigenen Sperre."""
    besitzer = _von(app_ohne, "192.168.1.20")
    besitzer.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    besitzer.post("/api/abmelden")
    angreifer = _von(app_ohne, "192.168.1.66")
    falsch = {"benutzer": "testnutzer", "passwort": "falsch-aber-lang"}
    for n in range(auth.MAX_FEHLVERSUCHE):
        angreifer.post("/api/anmelden", json=falsch,
                       headers={"X-Forwarded-For": f"192.168.1.{n}"})
    # Der Angreifer bleibt gesperrt, auch mit neuer Absenderangabe ...
    r = angreifer.post("/api/anmelden", json=ZUGANG,
                       headers={"X-Forwarded-For": "192.168.1.20"})
    assert r.json()["detail"]["meldung"] == "zu_viele_versuche"
    # ... und der Besitzer kommt weiter hinein.
    assert besitzer.post("/api/anmelden", json=ZUGANG,
                         headers={"X-Forwarded-For": "192.168.1.66"}
                         ).status_code == 200


# ── Befund 4: zwei Kontoanlagen zugleich ───────────────────────────────────
# Vorher: mehrere Threads kamen durch, der letzte ueberschrieb das Konto.

def test_gleichzeitige_kontoanlage_laesst_genau_eine_durch(tmp_path, monkeypatch):
    v = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    echt = auth.hashe
    monkeypatch.setattr(auth, "hashe",
                        lambda p, s=None: (time.sleep(0.2), echt(p, s))[1])
    ergebnis = {}
    start = threading.Barrier(4)

    def versuch(name):
        start.wait()
        try:
            v.lege_an(name, "ein-langes-passwort")
            ergebnis[name] = "ok"
        except PermissionError:
            ergebnis[name] = "vorhanden"

    faeden = [threading.Thread(target=versuch, args=(f"nutzer{i}",))
              for i in range(4)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    sieger = [n for n, e in ergebnis.items() if e == "ok"]
    assert len(sieger) == 1, ergebnis
    assert v.lade().benutzer == sieger[0]
    # Keine Reste der Zwischendateien.
    assert [p.name for p in v.pfad.glob("konto*")] == ["konto.json"]


def test_die_kontodatei_entsteht_nie_mit_offenen_rechten(tmp_path):
    v = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    v.lege_an("betreiber", "ein-langes-passwort")
    assert v.datei.stat().st_mode & 0o777 == 0o600


# ── Befund 5: der Anmeldestart war fuer alle ein Hebel ─────────────────────
# Vorher: der 52. Aufruf leerte alle offenen Vorgaenge (clear()).

@pytest.fixture
def mit_attrappe(monkeypatch):
    """Ausweisdienst ersetzt: beginne() liefert nur einen frischen Vorgang."""
    def beginne(_anbieter, jetzt=None):
        v = oidc.Vorgang(state=f"s{time.monotonic_ns()}", nonce="n",
                         beleg="b" * 43, begonnen=jetzt or time.time())
        return "https://id.example.test/authorize?state=" + v.state, v
    monkeypatch.setattr(oidc, "beginne", beginne)
    monkeypatch.setattr(oidc, "loese_ein",
                        lambda *_a, **_k: {"id_token": "x"})
    monkeypatch.setattr(oidc, "pruefe_ausweis",
                        lambda *_a, **_k: {"sub": "abc"})


def _state(r):
    return r.headers["location"].split("state=")[1]


def _zurueck(c, state):
    r = c.get(f"/api/anmeldung/oidc/callback?code=c&state={state}",
              follow_redirects=False)
    return r.headers["location"]


def test_ein_einzelner_rechner_kann_die_anmeldung_nicht_leerraeumen(
        app_oidc, mit_attrappe):
    besitzer = _von(app_oidc, "192.168.1.20")
    state = _state(besitzer.get("/api/anmeldung/oidc/start",
                                follow_redirects=False))
    flut = _von(app_oidc, "192.168.1.66")
    antworten = [flut.get("/api/anmeldung/oidc/start",
                          follow_redirects=False).status_code
                 for _ in range(80)]
    assert 429 in antworten, "die Flut wird nicht gebremst"
    assert _zurueck(besitzer, state) == "/"


def test_die_obergrenze_raeumt_die_aeltesten_ab_nicht_alle(app_oidc, mit_attrappe):
    zustaende = []
    for n in range(205):
        c = _von(app_oidc, f"192.168.{n // 250}.{n % 250 + 1}")
        zustaende.append(_state(c.get("/api/anmeldung/oidc/start",
                                      follow_redirects=False)))
    # Nummer 150 lag im Block, den das alte clear() beim 154. Aufruf wegwarf.
    assert _zurueck(_von(app_oidc, "192.168.9.9"), zustaende[150]) == "/"
    # Die Aeltesten sind die, die Platz machen mussten.
    assert _zurueck(_von(app_oidc, "192.168.9.9"),
                    zustaende[0]).startswith("/?anmeldung=")


# ── Befund 6: keine zweite Verteidigung gegen fremde Seiten ────────────────
# Vorher: alle Ablehnungen unten gaben 200.

@pytest.fixture
def drinnen(app_ohne):
    c = _von(app_ohne, "192.168.1.20")
    c.post("/api/konto/anlegen", json=ZUGANG).raise_for_status()
    return c


@pytest.mark.parametrize("seite", ["cross-site", "same-site"])
def test_schreibende_aufrufe_von_fremden_seiten_werden_abgewiesen(drinnen, seite):
    r = drinnen.post("/api/einrichtung/zurueck",
                     headers={"Sec-Fetch-Site": seite})
    assert r.status_code == 403
    assert r.json()["detail"]["meldung"] == "herkunft_unzulaessig"


@pytest.mark.parametrize("methode", ["post", "put", "patch", "delete"])
def test_alle_schreibenden_methoden_sind_erfasst(drinnen, methode):
    r = getattr(drinnen, methode)("/api/einrichtung/zurueck",
                                  headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_hinter_dem_proxy_geht_die_oberflaeche_wie_zuvor(drinnen):
    """Beschluss des Betreibers: der Proxy (Hostnetz, http://127.0.0.1:3333)
    darf nichts Neues kosten. Der Browser nennt die oeffentliche Domain als
    Origin, die Anwendung sieht Host 127.0.0.1:3333 -- ein Vergleich beider
    wuerde JEDEN schreibenden Aufruf ablehnen. Darum entscheidet allein
    Sec-Fetch-Site, das der Browser selbst berechnet."""
    r = drinnen.post("/api/einrichtung/zurueck",
                     headers={"Host": "127.0.0.1:3333",
                              "Origin": "https://node.example.com",
                              "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_origin_allein_entscheidet_nichts(drinnen):
    r = drinnen.post("/api/einrichtung/zurueck",
                     headers={"Origin": "https://node.example.com"})
    assert r.status_code == 200


@pytest.mark.parametrize("seite", ["same-origin", "none"])
def test_die_eigene_oberflaeche_funktioniert(drinnen, seite):
    r = drinnen.post("/api/einrichtung/zurueck",
                     headers={"Sec-Fetch-Site": seite,
                              "Origin": "http://testserver"})
    assert r.status_code == 200


def test_clients_ohne_browserkopfzeilen_funktionieren(drinnen):
    """curl, Skripte, die Tests: weder Origin noch Sec-Fetch-Site."""
    assert drinnen.post("/api/einrichtung/zurueck").status_code == 200


def test_lesende_aufrufe_von_fremden_seiten_bleiben_moeglich(drinnen):
    """Der Rueckweg vom Ausweisdienst ist ein GET von fremder Seite."""
    r = drinnen.get("/api/zustand", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200


def test_der_rueckweg_vom_ausweisdienst_geht_von_fremder_seite(
        app_oidc, mit_attrappe):
    c = _von(app_oidc, "192.168.1.20")
    state = _state(c.get("/api/anmeldung/oidc/start", follow_redirects=False))
    r = c.get(f"/api/anmeldung/oidc/callback?code=c&state={state}",
              headers={"Sec-Fetch-Site": "cross-site"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "satcortex_sitzung" in r.headers["set-cookie"]


def test_auch_die_anmeldung_selbst_ist_geschuetzt(app_ohne):
    """Login-CSRF: eine fremde Seite loggt den Besucher in ein fremdes Konto."""
    c = _von(app_ohne, "192.168.1.20")
    r = c.post("/api/konto/anlegen", json=ZUGANG,
               headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert c.get("/api/zustand").json()["konto_vorhanden"] is False


# ── Befund 7: die Beschreibung der Schnittstelle war oeffentlich ───────────
# Vorher: alle drei Adressen antworteten ohne Sitzung mit 200.

BESCHREIBUNG = ["/openapi.json", "/api/doku", "/redoc"]


@pytest.mark.parametrize("pfad", BESCHREIBUNG)
def test_beschreibung_ohne_sitzung_gibt_es_nicht(app_ohne, pfad):
    assert _von(app_ohne, "192.168.1.20").get(pfad).status_code == 401


@pytest.mark.parametrize("pfad", BESCHREIBUNG)
def test_beschreibung_mit_sitzung_bleibt_erhalten(drinnen, pfad):
    """Nicht entfernt, nur zugeschlossen."""
    assert drinnen.get(pfad).status_code == 200


def test_die_beschreibung_ist_vollstaendig(drinnen):
    pfade = drinnen.get("/openapi.json").json()["paths"]
    assert "/api/zustand" in pfade and len(pfade) > 50


def test_die_beschreibung_ist_nicht_selbst_beschrieben(drinnen):
    pfade = drinnen.get("/openapi.json").json()["paths"]
    assert "/openapi.json" not in pfade and "/api/doku" not in pfade


def test_der_oeffentliche_zustand_nennt_den_pfad_nicht_bei_gesunder_ablage(app_ohne):
    z = _von(app_ohne, "192.168.1.20").get("/api/zustand").json()
    assert z["ablage_bereit"] is True
    assert "ablage_pfad" not in z


# ── Befund 8: ein NUL-Byte im Pfad war ein 500 ─────────────────────────────
# Vorher: ValueError ("embedded null byte") -> 500.

@pytest.mark.parametrize("pfad", ["/%00", "/foo%00bar", "/%00.js", "/a/%00/b"])
def test_nul_im_pfad_ist_ein_404(app_ohne, pfad):
    c = TestClient(app_ohne, raise_server_exceptions=False)
    assert c.get(pfad).status_code == 404


def test_die_oberflaeche_wird_weiter_ausgeliefert(app_ohne):
    c = TestClient(app_ohne)
    assert c.get("/").status_code == 200
    assert c.get("/app.js").status_code == 200


# ── Befund 9: der DTD-Riegel sah UTF-16 nicht ──────────────────────────────
# Vorher: das UTF-16-Dokument wurde gelesen (Riegel auf Bytes fand nichts).

def _feed(kopf, kodierung, dtd=True):
    d = ('<!DOCTYPE rss [<!ENTITY a "aaaa">]>' if dtd else "")
    titel = "&a;" if dtd else "Titel"
    text = (kopf + d + '<rss version="2.0"><channel><item><title>' + titel + '</title>'
            '<link>https://a.test/</link></item></channel></rss>')
    return text.encode(kodierung)


FACH = nachrichten.Quelle("t", "Test", "https://beispiel.test/feed", "de", "fach")


@pytest.mark.parametrize("roh", [
    _feed('<?xml version="1.0" encoding="utf-16"?>', "utf-16"),          # mit BOM
    _feed('<?xml version="1.0" encoding="utf-16"?>', "utf-16-le"),
    _feed('<?xml version="1.0" encoding="utf-16"?>', "utf-16-be"),
    _feed('<?xml version="1.0"?>', "utf-16-le"),                          # ohne alles
    _feed('<?xml version="1.0" encoding="utf-32"?>', "utf-32"),
    _feed('<?xml version="1.0" encoding="cp037"?>', "cp037"),            # EBCDIC
    _feed('<?xml version="1.0" encoding="UTF-16"?>', "utf-8", dtd=False),  # nur behauptet
])
def test_fremde_kodierungen_werden_abgewiesen(roh):
    with pytest.raises(nachrichten.Abgewiesen):
        nachrichten.zerlege(roh, FACH)


def test_hole_weist_utf16_ab(monkeypatch):
    roh = _feed('<?xml version="1.0" encoding="utf-16"?>', "utf-16")

    class Antwort:
        def read(self, n): return roh
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Oeffner:
        def open(self, *a, **k): return Antwort()

    monkeypatch.setattr(nachrichten, "_oeffner", lambda proxy: Oeffner())
    with pytest.raises(nachrichten.Abgewiesen):
        nachrichten.hole("https://beispiel.test/feed")


@pytest.mark.parametrize("kopf,kodierung", [
    ('<?xml version="1.0"?>', "utf-8"),
    ('<?xml version="1.0" encoding="UTF-8"?>', "utf-8"),
    ('﻿<?xml version="1.0" encoding="utf-8"?>', "utf-8"),          # BOM
    ('<?xml version="1.0" encoding="ISO-8859-1"?>', "iso-8859-1"),
    ("<?xml version='1.0' encoding='us-ascii'?>", "ascii"),
])
def test_gewoehnliche_feeds_gehen_weiter_durch(kopf, kodierung):
    roh = _feed(kopf, kodierung, dtd=False)
    assert nachrichten.zerlege(roh, FACH)[0].titel == "Titel"
