"""Eigenes HTTPS der Weboberflaeche -- geprueft ueber die Leitung, nicht nur im
Aufbau.

DER BEFUND VOM 15.11.2026 (Sicherheitspruefung): Seed-Woerter, Schluessel fuer
externe Wallets (Macaroons) und die PIN laufen im Heimnetz im Klartext durch
die Leitung, solange die Oberflaeche nicht hinter einem TLS-Proxy steht. Der
Eigentuemer hat entschieden: SatoshiCortex bringt sein eigenes, selbst
signiertes Zertifikat mit -- auf einem ZWEITEN Port, damit der bisherige
HTTP-Port (und mit ihm jeder Reverse Proxy davor) unveraendert weiterlaeuft.

Die Module werden in Fixtures geladen, nicht oben: so scheitert jeder Test
einzeln und lesbar, solange es das Modul noch nicht gibt.
"""
import asyncio
import datetime
import http.client
import importlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest
from cryptography import x509
from fastapi import FastAPI
from fastapi.testclient import TestClient

from satcortex import api, settings

WEB = Path(__file__).resolve().parents[2] / "web"
ZUGANG = {"benutzer": "pruefer", "passwort": "ein-gutes-langes-passwort"}


@pytest.fixture
def wt():
    return importlib.import_module("satcortex.webtls")


@pytest.fixture
def start():
    return importlib.import_module("satcortex.__main__")


def _san(pfad):
    zert = x509.load_pem_x509_certificate(Path(pfad).read_bytes())
    erw = zert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    return (set(erw.value.get_values_for_type(x509.DNSName)),
            {str(i) for i in erw.value.get_values_for_type(x509.IPAddress)})


# ── Namen: was ins Zertifikat darf ─────────────────────────────────────────

def test_namen_werden_getrennt_in_dns_und_ip(wt):
    dns, ips, abgelehnt = wt.lese_namen("nas.local, 192.168.1.5 ,Knoten,fd00::5")
    assert dns == ["nas.local", "knoten"]
    assert ips == ["192.168.1.5", "fd00::5"]
    assert abgelehnt == []


@pytest.mark.parametrize("roh", [None, "", "  ", ",,"])
def test_leere_namensliste_ist_leer(wt, roh):
    assert wt.lese_namen(roh) == ([], [], [])


@pytest.mark.parametrize("schlecht", [
    "mit leerzeichen", "unter_strich", "-anfang.de", "ende-.de", "*.wild.de",
    "a" * 64 + ".de", "a." * 130 + "de", "böse.de", "1.2.3", "999.1.1.1",
    "x;rm -rf", "a/b", "<script>",
])
def test_ungueltige_namen_werden_abgelehnt_und_gemeldet(wt, schlecht):
    dns, ips, abgelehnt = wt.lese_namen(f"gut.de,{schlecht}")
    assert dns == ["gut.de"] and ips == []
    assert abgelehnt == [schlecht]


def test_doppelte_namen_und_eine_obergrenze(wt):
    dns, _, _ = wt.lese_namen("a.de,A.de,a.de")
    assert dns == ["a.de"]
    viele = ",".join(f"h{i}.de" for i in range(100))
    dns, _, abgelehnt = wt.lese_namen(viele)
    assert len(dns) == wt.MAX_NAMEN
    assert len(abgelehnt) == 100 - wt.MAX_NAMEN


# ── Zertifikat: Anlegen, Rechte, Wiederverwenden ───────────────────────────

def test_zertifikat_enthaelt_die_vorgabenamen_und_die_eigenen(wt, tmp_path):
    d = wt.sicherstellen(str(tmp_path), "nas.local,192.168.1.5")
    dns, ips = _san(d.zertifikat)
    assert {"satcortex", "localhost", "nas.local"} <= dns
    assert {"127.0.0.1", "192.168.1.5"} <= ips


def test_zertifikat_ist_ec_p256_mit_langer_laufzeit(wt, tmp_path):
    d = wt.sicherstellen(str(tmp_path), "")
    z = x509.load_pem_x509_certificate(Path(d.zertifikat).read_bytes())
    assert z.public_key().curve.name == "secp256r1"
    laufzeit = z.not_valid_after_utc - z.not_valid_before_utc
    assert datetime.timedelta(days=3000) < laufzeit < datetime.timedelta(days=4000)
    ku = z.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in ku
    bc = z.extensions.get_extension_for_class(x509.BasicConstraints).value
    # Ein Blatt, keine Zertifizierungsstelle: wer es im Geraet als vertrauens-
    # wuerdig eintraegt, soll damit keine fremden Namen beglaubigen koennen.
    assert bc.ca is False


def test_der_schluessel_entsteht_von_anfang_an_mit_0600_und_exklusiv(
        wt, tmp_path, monkeypatch):
    """Nicht erst per chmod: dazwischen laege er kurz offen."""
    aufrufe = []
    echtes = os.open

    def merkend(pfad, flags, mode=0o777, **kw):
        aufrufe.append((str(pfad), flags, mode))
        return echtes(pfad, flags, mode, **kw)

    monkeypatch.setattr(wt.os, "open", merkend)
    old = os.umask(0)
    try:
        d = wt.sicherstellen(str(tmp_path), "")
    finally:
        os.umask(old)
    zum_schluessel = [a for a in aufrufe if a[0] == d.schluessel]
    assert zum_schluessel, "der Schluessel wurde nicht ueber os.open angelegt"
    _, flags, mode = zum_schluessel[0]
    assert mode == 0o600
    assert flags & os.O_EXCL and flags & os.O_CREAT and flags & os.O_WRONLY
    assert stat.S_IMODE(os.stat(d.schluessel).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(d.zertifikat).st_mode) == 0o644


def test_ein_vorhandenes_zertifikat_wird_wiederverwendet(wt, tmp_path):
    erstes = wt.sicherstellen(str(tmp_path), "")
    assert erstes.neu is True
    zweites = wt.sicherstellen(str(tmp_path), "")
    assert zweites.neu is False
    assert wt.fingerabdruck(zweites.zertifikat) == wt.fingerabdruck(erstes.zertifikat)


@pytest.mark.parametrize("was", ["zertifikat", "schluessel"])
def test_fehlt_eine_datei_wird_neu_angelegt(wt, tmp_path, was):
    erstes = wt.sicherstellen(str(tmp_path), "")
    vorher = wt.fingerabdruck(erstes.zertifikat)
    os.unlink(getattr(erstes, was))
    zweites = wt.sicherstellen(str(tmp_path), "")
    assert zweites.neu is True
    ssl.create_default_context().load_cert_chain(zweites.zertifikat,
                                                 zweites.schluessel)
    assert wt.fingerabdruck(zweites.zertifikat) != vorher


def test_unlesbares_zertifikat_wird_ersetzt(wt, tmp_path):
    erstes = wt.sicherstellen(str(tmp_path), "")
    Path(erstes.zertifikat).write_text("kein zertifikat")
    zweites = wt.sicherstellen(str(tmp_path), "")
    assert zweites.neu is True
    ssl.create_default_context().load_cert_chain(zweites.zertifikat,
                                                 zweites.schluessel)


def test_zertifikat_und_schluessel_die_nicht_zusammenpassen_werden_ersetzt(
        wt, tmp_path):
    a = wt.sicherstellen(str(tmp_path / "a"), "")
    b = wt.sicherstellen(str(tmp_path / "b"), "")
    shutil.copy(b.schluessel, a.schluessel)
    c = wt.sicherstellen(str(tmp_path / "a"), "")
    assert c.neu is True
    ssl.create_default_context().load_cert_chain(c.zertifikat, c.schluessel)


def test_abgelaufen_oder_fast_abgelaufen_wird_erneuert(wt, tmp_path):
    erstes = wt.sicherstellen(str(tmp_path), "")
    vorher = wt.fingerabdruck(erstes.zertifikat)
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    noch_gut = wt.sicherstellen(str(tmp_path), "",
                                jetzt=jetzt + datetime.timedelta(days=3000))
    assert noch_gut.neu is False
    bald = wt.sicherstellen(str(tmp_path), "",
                            jetzt=jetzt + datetime.timedelta(days=3640))
    assert bald.neu is True
    assert wt.fingerabdruck(bald.zertifikat) != vorher


def test_ein_neuer_name_in_der_einstellung_erneuert_das_zertifikat(wt, tmp_path):
    """Sonst bliebe die Warnung 'falscher Name' stehen, obwohl man den Namen
    eingetragen hat."""
    wt.sicherstellen(str(tmp_path), "")
    neu = wt.sicherstellen(str(tmp_path), "nas.fritz.box")
    assert neu.neu is True
    assert "nas.fritz.box" in _san(neu.zertifikat)[0]
    nochmal = wt.sicherstellen(str(tmp_path), "nas.fritz.box")
    assert nochmal.neu is False
    # Weniger Namen als im Zertifikat ist kein Grund, es zu wechseln.
    assert wt.sicherstellen(str(tmp_path), "").neu is False


def test_unbeschreibbare_ablage_wirft_und_ueberschreibt_nichts(wt, tmp_path):
    datei = tmp_path / "keinordner"
    datei.write_text("x")
    with pytest.raises(OSError):
        wt.sicherstellen(str(datei), "")


# ── Fingerabdruck ──────────────────────────────────────────────────────────

def test_fingerabdruck_ist_sha256_in_doppelpunktschreibweise(wt, tmp_path):
    import hashlib
    d = wt.sicherstellen(str(tmp_path), "")
    der = ssl.PEM_cert_to_DER_cert(Path(d.zertifikat).read_text())
    erwartet = ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())
    assert wt.fingerabdruck(d.zertifikat) == erwartet
    assert re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", erwartet)


def test_fingerabdruck_ohne_datei_ist_none(wt, tmp_path):
    assert wt.fingerabdruck(str(tmp_path / "gibtsnicht.pem")) is None


# ── Einstellungen ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("wert", ["off", "OFF", " Off ", "0", "false", "no",
                                  "nein", "aus"])
def test_webui_tls_aus_schaltet_ab(wert):
    assert settings.tls_schalter(wert) is False


@pytest.mark.parametrize("wert", [None, "", "on", "true", "1", "ja", "quatsch"])
def test_alles_andere_laesst_es_an(wert):
    """Im Zweifel verschluesselt: ein Tippfehler darf nicht stillschweigend
    den sicheren Weg abschalten."""
    assert settings.tls_schalter(wert) is True


def test_einstellungen_vorgaben_fuer_den_zweiten_port():
    e = settings.Einstellungen()
    assert e.webui_tls_an is True
    assert e.bind_tls_port == 8443


def test_der_aussenport_ist_unbekannt_wenn_die_compose_ihn_nicht_reicht():
    assert settings.Einstellungen(webui_tls_port=None).webui_tls_port is None
    assert settings.Einstellungen().webui_tls_port is None or \
        settings.Einstellungen().webui_tls_port.isdigit()


def test_abgeschaltet_gibt_es_keine_zertifikatsdateien(wt, tmp_path):
    e = settings.Einstellungen(config_dir=str(tmp_path), webui_tls_an=False)
    assert wt.dateien_fuer(e) is None


def test_eigenes_zertifikat_aus_tls_cert_hat_vorrang(wt, tmp_path):
    e = settings.Einstellungen(config_dir=str(tmp_path), tls_cert="/x/c.pem",
                               tls_key="/x/k.pem")
    d = wt.dateien_fuer(e)
    assert (d.zertifikat, d.schluessel, d.neu) == ("/x/c.pem", "/x/k.pem", False)


def test_ohne_eigenes_zertifikat_liegt_es_in_der_ablage(wt, tmp_path):
    e = settings.Einstellungen(config_dir=str(tmp_path))
    d = wt.dateien_fuer(e)
    assert Path(d.zertifikat).parent == Path(wt.verzeichnis(str(tmp_path)))
    assert Path(d.zertifikat).is_file()


# ── Start: zwei Server, ein Ereignisschleife ───────────────────────────────

class _Konf:
    tls_aktiv = False
    tls_cert = ""
    tls_key = ""
    webui_tls_an = True
    webui_tls_namen = ""
    webui_tls_port = "3334"
    bind_tls_port = 8443
    config_dir = ""


def test_der_zweite_server_hat_den_lebenszyklus_aus(start, wt, tmp_path):
    k = _Konf()
    k.config_dir = str(tmp_path)
    haupt, neben = start.baue_server(k, object(), host="127.0.0.1", port=8000,
                                     log_level="info")
    assert haupt.config.lifespan == "auto"
    assert neben.config.lifespan == "off"
    assert neben.config.port == 8443
    assert neben.config.ssl_certfile.endswith(".pem")
    assert haupt.config.ssl_certfile is None
    assert haupt.config.port == 8000


def test_der_http_port_behaelt_ein_eigenes_zertifikat(start, tmp_path):
    k = _Konf()
    k.config_dir = str(tmp_path)
    k.tls_aktiv, k.tls_cert, k.tls_key = True, "/fast/c.pem", "/fast/k.pem"
    haupt, neben = start.baue_server(k, object(), host="127.0.0.1", port=8000,
                                     log_level="info")
    assert haupt.config.ssl_certfile == "/fast/c.pem"
    assert haupt.config.ssl_keyfile == "/fast/k.pem"
    assert neben.config.ssl_certfile == "/fast/c.pem"


def test_abgeschaltet_gibt_es_keinen_zweiten_server(start, tmp_path):
    k = _Konf()
    k.webui_tls_an = False
    k.config_dir = str(tmp_path)
    haupt, neben = start.baue_server(k, object(), host="127.0.0.1", port=8000,
                                     log_level="info")
    assert neben is None and haupt is not None
    assert not (tmp_path / "webtls").exists()


def test_scheitert_das_zertifikat_laeuft_http_trotzdem(start, tmp_path, capsys):
    """Die Ablage kann unbeschreibbar sein. Daran darf der Zugang, der heute
    funktioniert, nicht sterben."""
    datei = tmp_path / "keinordner"
    datei.write_text("x")
    k = _Konf()
    k.config_dir = str(datei)
    haupt, neben = start.baue_server(k, object(), host="127.0.0.1", port=8000,
                                     log_level="info")
    assert neben is None and haupt is not None
    assert "ACHTUNG" in capsys.readouterr().out


def test_main_ohne_zweiten_server_ruft_uvicorn_run_wie_bisher(
        start, monkeypatch):
    gemerkt = {}
    monkeypatch.setattr(start.uvicorn, "run",
                        lambda app, **kw: gemerkt.update(app=app, **kw))
    monkeypatch.setattr(start.api, "baue_app", lambda konf: "die-app")

    class K(_Konf):
        webui_tls_an = False
    monkeypatch.setattr(start.settings, "laden", K)
    start.main()
    assert gemerkt["app"] == "die-app" and gemerkt["workers"] == 1


def test_main_mit_zweitem_server_startet_beide(start, monkeypatch, tmp_path):
    gemerkt = {}

    async def attrappe(haupt, neben):
        gemerkt["haupt"], gemerkt["neben"] = haupt, neben
    monkeypatch.setattr(start, "laufe_beide", attrappe)
    monkeypatch.setattr(start.api, "baue_app", lambda konf: FastAPI())

    class K(_Konf):
        config_dir = str(tmp_path)
    monkeypatch.setattr(start.settings, "laden", K)
    start.main()
    assert gemerkt["neben"].config.lifespan == "off"


# ── Auf der Leitung: beide Ports, einmal gestartet ─────────────────────────

def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Laufend:
    """Beide Server in einem Faden, mit eigener Schleife -- so kann der Test
    in seinem Faden blockierend anfragen."""

    def __init__(self, start, konf, app, port_neben=None, neben_scheitert=False):
        self.konf = konf
        self.neben_scheitert = neben_scheitert
        self.port = _freier_port()
        konf.bind_tls_port = port_neben or _freier_port()
        self.haupt, self.neben = start.baue_server(
            konf, app, host="127.0.0.1", port=self.port, log_level="warning")
        self.faden = threading.Thread(
            target=lambda: asyncio.run(start.laufe_beide(self.haupt, self.neben)),
            daemon=True)

    def __enter__(self):
        self.faden.start()
        ende = time.time() + 15
        while time.time() < ende:
            if self.haupt.started and (self.neben_scheitert or self.neben is None
                                       or self.neben.started):
                return self
            time.sleep(0.05)
        raise AssertionError("Server kamen nicht hoch")

    def __exit__(self, *a):
        self.haupt.should_exit = True
        self.faden.join(timeout=15)
        assert not self.faden.is_alive()

    def http(self, pfad="/healthz"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", pfad)
        r = c.getresponse()
        return r.status, r.read()

    def https(self, cafile, pfad="/healthz"):
        ctx = ssl.create_default_context(cafile=cafile)
        c = http.client.HTTPSConnection("127.0.0.1", self.konf.bind_tls_port,
                                        timeout=5, context=ctx)
        c.request("GET", pfad)
        r = c.getresponse()
        return r.status, r.read()


def _zaehl_app():
    zaehler = {"start": 0, "ende": 0}
    app = FastAPI()

    @app.on_event("startup")
    async def _auf():
        zaehler["start"] += 1

    @app.on_event("shutdown")
    async def _zu():
        zaehler["ende"] += 1

    @app.get("/healthz")
    def h():
        return {"ok": True}
    return app, zaehler


def test_beide_ports_antworten_und_der_start_laeuft_genau_einmal(
        start, wt, tmp_path):
    k = _Konf()
    k.config_dir = str(tmp_path)
    app, zaehler = _zaehl_app()
    with _Laufend(start, k, app) as l:
        cert = wt.dateien_fuer(k).zertifikat
        assert l.http() == (200, b'{"ok":true}')
        # Verifiziert gegen das erzeugte Zertifikat, nicht gegen "unsicher".
        assert l.https(cert) == (200, b'{"ok":true}')
        assert zaehler == {"start": 1, "ende": 0}
    assert zaehler == {"start": 1, "ende": 1}


def test_klartext_auf_dem_tls_port_und_tls_auf_dem_klartextport_gehen_nicht(
        start, wt, tmp_path):
    k = _Konf()
    k.config_dir = str(tmp_path)
    app, _ = _zaehl_app()
    with _Laufend(start, k, app) as l:
        cert = wt.dateien_fuer(k).zertifikat
        c = http.client.HTTPConnection("127.0.0.1", k.bind_tls_port, timeout=5)
        with pytest.raises((http.client.HTTPException, OSError)):
            c.request("GET", "/healthz")
            c.getresponse()
        ctx = ssl.create_default_context(cafile=cert)
        with pytest.raises((ssl.SSLError, OSError)):
            c2 = http.client.HTTPSConnection("127.0.0.1", l.port, timeout=5,
                                             context=ctx)
            c2.request("GET", "/healthz")
            c2.getresponse()


def test_ein_fremdes_zertifikat_wird_nicht_akzeptiert(start, wt, tmp_path):
    """Die Gegenprobe zur Pruefung oben: ohne sie bewiese 'verifiziert' nichts."""
    k = _Konf()
    k.config_dir = str(tmp_path / "a")
    app, _ = _zaehl_app()
    fremd = wt.sicherstellen(str(tmp_path / "fremd"), "").zertifikat
    with _Laufend(start, k, app) as l:
        with pytest.raises(ssl.SSLCertVerificationError):
            l.https(fremd)


def test_belegter_tls_port_laesst_den_http_port_laufen(start, tmp_path):
    k = _Konf()
    k.config_dir = str(tmp_path)
    app, zaehler = _zaehl_app()
    with socket.socket() as belegt:
        belegt.bind(("127.0.0.1", 0))
        belegt.listen(1)
        port = belegt.getsockname()[1]
        with _Laufend(start, k, app, port_neben=port, neben_scheitert=True) as l:
            assert l.http()[0] == 200
    assert zaehler == {"start": 1, "ende": 1}


# ── Cookie: Name und Secure je nach Weg ────────────────────────────────────

def _client(tmp_path, basis, **konf):
    e = settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"), **konf)
    c = TestClient(api.baue_app(e), base_url=basis)
    c.konf = e
    return c


def _setzt(antwort):
    """Alle Set-Cookie-Zeilen einer Antwort."""
    return antwort.headers.get_list("set-cookie")


def test_ueber_http_heisst_das_cookie_wie_bisher_und_ist_nicht_secure(tmp_path):
    c = _client(tmp_path, "http://testserver")
    z = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))
    assert len(z) == 1
    assert z[0].startswith("satcortex_sitzung=")
    assert "Secure" not in z[0] and "HttpOnly" in z[0]


def test_ueber_https_heisst_es_host_praefix_und_ist_secure(tmp_path):
    c = _client(tmp_path, "https://testserver")
    z = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))
    assert len(z) == 1
    # __Host-: nur ueber https setzbar, nur fuer genau diesen Host, Pfad /, kein
    # Domain-Attribut -- ein Klartext-Lauscher kann es weder setzen noch
    # ueberschreiben.
    assert z[0].startswith("__Host-satcortex_sitzung=")
    assert "Secure" in z[0] and "Path=/" in z[0]
    assert "Domain" not in z[0] and "HttpOnly" in z[0]


def test_hinter_einem_proxy_ist_es_secure_auch_wenn_die_app_klartext_sieht(
        tmp_path):
    """TLS_EXTERN: der Browser spricht https, die Anwendung sieht http."""
    c = _client(tmp_path, "http://testserver", tls_extern=True)
    z = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))
    assert z[0].startswith("__Host-satcortex_sitzung=")
    assert "Secure" in z[0]


def test_mit_eigenem_zertifikat_am_klartextport_ist_es_secure(tmp_path):
    c = _client(tmp_path, "https://testserver", tls_cert="/x", tls_key="/y")
    z = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))
    assert "Secure" in z[0]


@pytest.mark.parametrize("basis", ["http://testserver", "https://testserver"])
def test_anmelden_setzt_auf_beiden_wegen_ein_brauchbares_cookie(tmp_path, basis):
    c = _client(tmp_path, basis)
    c.post("/api/konto/anlegen", json=ZUGANG)
    c.cookies.clear()
    r = c.post("/api/anmelden", json=ZUGANG)
    assert r.status_code == 200
    kopf = _setzt(r)[0]
    name, rest = kopf.split(";")[0].split("=", 1)
    # Der Browser schickt es bei diesem Weg zurueck -- hier von Hand, weil der
    # Cookie-Topf des Testclients Secure ueber http nicht zurueckgeben wuerde.
    z = c.get("/api/zustand", headers={"Cookie": f"{name}={rest}"})
    assert z.json()["angemeldet"] is True


@pytest.mark.parametrize("basis", ["http://testserver", "https://testserver"])
@pytest.mark.parametrize("name", ["satcortex_sitzung",
                                  "__Host-satcortex_sitzung"])
def test_beide_namen_werden_beim_lesen_angenommen(tmp_path, basis, name):
    """Wer vor dem Update angemeldet war, behaelt seine Sitzung -- auch hinter
    einem Proxy, wo er bisher das Cookie ohne Praefix hatte."""
    c = _client(tmp_path, basis)
    kopf = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))[0]
    token = kopf.split(";")[0].split("=", 1)[1]
    c.cookies.clear()
    z = c.get("/api/zustand", headers={"Cookie": f"{name}={token}"})
    assert z.json()["angemeldet"] is True
    # Und der Schutz hinter der Anmeldung greift mit demselben Cookie.
    ok = c.get("/api/status", headers={"Cookie": f"{name}={token}"})
    assert ok.status_code != 401


def test_ein_ungueltiges_cookie_gilt_nicht_und_das_andere_rettet_es_nicht_vor_dem_pruefen(
        tmp_path):
    c = _client(tmp_path, "http://testserver")
    kopf = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))[0]
    token = kopf.split(";")[0].split("=", 1)[1]
    c.cookies.clear()
    schlecht = c.get("/api/zustand", headers={
        "Cookie": "satcortex_sitzung=quatsch; __Host-satcortex_sitzung=quatsch2"})
    assert schlecht.json()["angemeldet"] is False
    # Ein altes, abgelaufenes plus ein gueltiges: das gueltige entscheidet.
    gemischt = c.get("/api/zustand", headers={
        "Cookie": f"satcortex_sitzung=alt; __Host-satcortex_sitzung={token}"})
    assert gemischt.json()["angemeldet"] is True
    nichts = c.get("/api/status", headers={"Cookie": "satcortex_sitzung=quatsch"})
    assert nichts.status_code == 401


def test_abmelden_beendet_die_sitzung_gleich_unter_welchem_namen(tmp_path):
    c = _client(tmp_path, "https://testserver")
    kopf = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))[0]
    token = kopf.split(";")[0].split("=", 1)[1]
    c.cookies.clear()
    r = c.post("/api/abmelden",
               headers={"Cookie": f"__Host-satcortex_sitzung={token}"})
    assert r.status_code == 200
    geloescht = " ".join(_setzt(r))
    assert "__Host-satcortex_sitzung=" in geloescht
    assert re.search(r'(^|\s)satcortex_sitzung=', geloescht)
    nach = c.get("/api/zustand",
                 headers={"Cookie": f"__Host-satcortex_sitzung={token}"})
    assert nach.json()["angemeldet"] is False


def test_abmelden_ueber_http_beendet_auch_ein_host_cookie_serverseitig(tmp_path):
    c = _client(tmp_path, "http://testserver")
    kopf = _setzt(c.post("/api/konto/anlegen", json=ZUGANG))[0]
    token = kopf.split(";")[0].split("=", 1)[1]
    c.cookies.clear()
    c.post("/api/abmelden", headers={"Cookie": f"__Host-satcortex_sitzung={token}"})
    nach = c.get("/api/zustand", headers={"Cookie": f"satcortex_sitzung={token}"})
    assert nach.json()["angemeldet"] is False


# ── Was die Oberflaeche vom Server erfaehrt ────────────────────────────────

def test_zustand_nennt_tls_lage_und_fingerabdruck(tmp_path):
    from satcortex import webtls
    c = _client(tmp_path, "http://testserver", webui_tls_port="3334")
    # Ohne Zertifikat (Start noch nicht durch) gibt es nichts zu zeigen -- und
    # der Abruf legt keines an.
    assert c.get("/api/zustand").json()["tls_fingerabdruck"] is None
    d = webtls.dateien_fuer(c.konf)
    z = c.get("/api/zustand").json()
    assert z["tls_extern"] is False
    assert z["tls_port"] == "3334"
    # Der Fingerabdruck ist der des Zertifikats, das der zweite Port benutzt.
    assert z["tls_fingerabdruck"] == webtls.fingerabdruck(d.zertifikat)
    assert re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", z["tls_fingerabdruck"])


def test_zustand_ohne_zweiten_port_nennt_weder_port_noch_fingerabdruck(tmp_path):
    c = _client(tmp_path, "http://testserver", webui_tls_an=False,
                webui_tls_port="3334")
    z = c.get("/api/zustand").json()
    assert z["tls_port"] is None and z["tls_fingerabdruck"] is None


def test_zustand_meldet_tls_extern(tmp_path):
    c = _client(tmp_path, "http://testserver", tls_extern=True)
    assert c.get("/api/zustand").json()["tls_extern"] is True


# ── Oberflaeche: Hinweis, kein Verbot ──────────────────────────────────────

def _ohne_kommentare_js(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith("//"))


def _ohne_kommentare_html(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


@pytest.fixture(scope="module")
def js():
    return _ohne_kommentare_js((WEB / "app.js").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def html():
    return _ohne_kommentare_html((WEB / "index.html").read_text(encoding="utf-8"))


def _funktion(js, name):
    m = re.search(r"function " + name + r"\([^)]*\) \{.*?\n\}\n", js, re.S)
    assert m, f"function {name} fehlt"
    return m.group(0)


def test_die_oberflaeche_liest_die_tls_lage_aus_dem_zustand(js):
    for feld in ("z.tls_extern", "z.tls_port", "z.tls_fingerabdruck"):
        assert feld in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")
@pytest.mark.parametrize("protokoll,host,extern,erwartet", [
    ("http:", "192.168.1.5", False, True),
    ("http:", "satcortex.local", False, True),
    ("http:", "localhost", False, False),
    ("http:", "127.0.0.1", False, False),
    ("http:", "::1", False, False),
    ("http:", "[::1]", False, False),
    ("https:", "192.168.1.5", False, False),
    ("http:", "192.168.1.5", True, False),
])
def test_wann_der_hinweis_erscheint(js, protokoll, host, extern, erwartet):
    quelle = _funktion(js, "tlsHinweisNoetig")
    ergebnis = subprocess.run(
        ["node", "-e", quelle + f"console.log(JSON.stringify(tlsHinweisNoetig("
         f"{json.dumps(protokoll)},{json.dumps(host)},{json.dumps(extern)})))"],
        capture_output=True, text=True, timeout=20, check=True)
    assert json.loads(ergebnis.stdout) is erwartet


def test_der_hinweis_wird_ohne_innerhtml_gebaut(js):
    """Host und Fingerabdruck stammen aus der Adresszeile und vom Server --
    kein Weg ins HTML."""
    quelle = _funktion(js, "zeigeTlsHinweise")
    assert "innerHTML" not in quelle
    assert "textContent" in quelle
    assert "createElement" in quelle


def test_der_hinweis_verlinkt_dieselbe_adresse_auf_dem_tls_port(js):
    quelle = _funktion(js, "tlsAdresse")
    assert "https://" in quelle and "location.hostname" in quelle
    assert "TLS_PORT" in quelle


def test_der_hinweis_ist_keine_sperre(js):
    """Information, kein Verbot: kein Knopf wird deswegen abgeschaltet."""
    quelle = _funktion(js, "zeigeTlsHinweise")
    assert "disabled" not in quelle and "preventDefault" not in quelle


def test_hinweisstellen_stehen_im_banner_im_seed_und_im_schluesseldialog(html):
    stellen = re.findall(r'data-tls-hinweis="(lang|kurz)"', html)
    assert stellen.count("lang") >= 1
    assert stellen.count("kurz") >= 2
    # Seed-Anzeige und Erstellen-Dialog fuer externe Wallets tragen je eine.
    seed = html[html.index('id="w-schritt-woerter"'):]
    assert "data-tls-hinweis" in seed[:seed.index("</div>\n\n")] or \
        "data-tls-hinweis" in seed[:1500]
    fz = html[html.index('id="fz-panel"'):]
    assert "data-tls-hinweis" in fz[:6000]


def test_der_grosse_hinweis_ist_schliessbar_und_merkt_es_sich(js):
    """Ruhig und abstellbar: Knopf, Wahl in localStorage, in try/catch."""
    quelle = _funktion(js, "tlsHinweisGeschlossen") + _funktion(
        js, "tlsHinweisSchliessen")
    assert "localStorage.getItem" in quelle and "localStorage.setItem" in quelle
    assert quelle.count("try {") == 2 and quelle.count("catch") == 2
    anzeige = _funktion(js, "zeigeTlsHinweise")
    assert "tlsHinweisGeschlossen()" in anzeige
    assert 't("tls_schliessen")' in anzeige and "tlsHinweisSchliessen" in anzeige


def test_die_kurze_zeile_hat_weder_knopf_noch_rueckfrage(js):
    """Nichts darf den normalen Ablauf um einen Schritt verlaengern."""
    anzeige = _funktion(js, "zeigeTlsHinweise")
    kurz = anzeige.split("if (!lang) return;")[0]
    assert 'createElement("button")' not in kurz
    assert "confirm(" not in anzeige and "prompt(" not in anzeige


@pytest.mark.parametrize("schluessel", ["tls_hinweis_lang", "tls_hinweis_kurz",
                                        "tls_link", "tls_fingerabdruck",
                                        "tls_schliessen"])
def test_texte_stehen_auf_deutsch_und_englisch(js, schluessel):
    assert len(re.findall(r"^\s*" + schluessel + r':\s*"', js, re.M)) == 2
