"""Der Startpunkt im Container -- geprueft, ohne einen Server zu starten.

`python -m satcortex` war bis zum 16.09.2026 der einzige Teil der Anwendung
ohne jede Pruefung: 35 Anweisungen, 0 %. Ausgerechnet dort steht der Filter,
der das Zugriffsprotokoll lesbar haelt -- und ein Filter, der zu viel
verschluckt, ist schlimmer als gar keiner.
"""
import logging

import pytest

from satcortex import __main__ as start


def zugriff(pfad, code):
    """Eine Zugriffszeile bauen, genau wie uvicorn sie meldet.

    Das Format ist '%s - "%s %s HTTP/%s" %d' -- der Pfad steht an Stelle 2,
    der Statuscode an Stelle 4. Genau daran haengt der Filter.
    """
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5", "GET", pfad, "1.1", code), None)


# ── Was still bleiben soll ─────────────────────────────────────────────────

@pytest.mark.parametrize("pfad", start.OhneTaktrauschen.STILL)
def test_die_regelmaessigen_abrufe_bleiben_still(pfad):
    """Rund zwanzig Zeilen je Minute, dauerhaft -- daneben geht bitcoinds
    Fortschritt unter."""
    assert start.OhneTaktrauschen().filter(zugriff(pfad, 200)) is False


def test_auch_mit_anhaengsel_bleibt_es_still():
    """Der Vergleich geht auf den Pfad ohne Abfrageteil."""
    assert start.OhneTaktrauschen().filter(
        zugriff("/api/auswertung?seit=100", 200)) is False


# ── Was NICHT verschluckt werden darf ──────────────────────────────────────

def test_ein_fehler_auf_stillem_pfad_steht_trotzdem_da():
    """Ein Protokoll, das auch Fehler verschluckt, waere schlimmer als eines,
    das rauscht."""
    assert start.OhneTaktrauschen().filter(zugriff("/api/status", 500)) is True


def test_ein_abgelehnter_zugriff_steht_da():
    assert start.OhneTaktrauschen().filter(zugriff("/api/status", 401)) is True


def test_ein_fremder_pfad_steht_da():
    assert start.OhneTaktrauschen().filter(zugriff("/api/lightning/senden",
                                                   200)) is True


@pytest.mark.parametrize("args", [
    None,                                   # gar keine Argumente
    ("zu", "kurz"),                         # weniger als fuenf
    ("a", "b", "/api/status", "d", "kein code"),   # Code nicht lesbar
])
def test_was_nicht_nach_zugriffszeile_aussieht_bleibt_stehen(args):
    """Im Zweifel durchlassen. Ein Filter, der Unbekanntes verschluckt,
    verliert genau die Meldungen, die niemand erwartet hat."""
    satz = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                             "irgendwas", args, None)
    assert start.OhneTaktrauschen().filter(satz) is True


# ── Der Start selbst ───────────────────────────────────────────────────────

class Konfiguration:
    tls_aktiv = False
    tls_cert = ""
    tls_key = ""


@pytest.fixture
def gestartet(monkeypatch):
    """uvicorn wird NICHT wirklich gestartet -- nur festgehalten, womit."""
    gemerkt = {}
    monkeypatch.setattr(start.uvicorn, "run",
                        lambda app, **kw: gemerkt.update(app=app, **kw))
    monkeypatch.setattr(start.api, "baue_app", lambda konf: "die-anwendung")
    monkeypatch.setattr(start.settings, "laden", Konfiguration)
    return gemerkt


def test_der_start_bindet_im_container_auf_alle_schnittstellen(gestartet,
                                                               monkeypatch):
    """Docker leitet den veroeffentlichten Port an das Container-Netz weiter,
    und das erreicht man nur ueber 0.0.0.0. Nach aussen sichtbar ist
    ausschliesslich, was die Compose freigibt."""
    monkeypatch.delenv("BIND_HOST", raising=False)
    start.main()
    assert gestartet["host"] == "0.0.0.0"          # nosec B104
    assert gestartet["port"] == 8000
    assert gestartet["app"] == "die-anwendung"


def test_wer_enger_binden_will_kann_das(gestartet, monkeypatch):
    monkeypatch.setenv("BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("BIND_PORT", "9999")
    start.main()
    assert gestartet["host"] == "127.0.0.1"
    assert gestartet["port"] == 9999


def test_ein_arbeiter_genuegt(gestartet):
    """Die Anwendung ist I/O-gebunden und soll auf einem NAS wenig Speicher
    belegen."""
    start.main()
    assert gestartet["workers"] == 1


def test_ohne_tls_wird_kein_zertifikat_uebergeben(gestartet):
    start.main()
    assert "ssl_certfile" not in gestartet


def test_mit_tls_gehen_beide_dateien_mit(gestartet, monkeypatch):
    class MitTls(Konfiguration):
        tls_aktiv = True
        tls_cert = "/fast/cert.pem"
        tls_key = "/fast/key.pem"
    monkeypatch.setattr(start.settings, "laden", MitTls)
    start.main()
    assert gestartet["ssl_certfile"] == "/fast/cert.pem"
    assert gestartet["ssl_keyfile"] == "/fast/key.pem"


def test_nur_ein_halbes_tls_laeuft_unverschluesselt_und_sagt_es(gestartet,
                                                                monkeypatch,
                                                                capsys):
    """Nur eines von beiden ist ein Konfigurationsfehler, kein Wunsch nach
    Klartext -- das gehoert gesagt, statt still auf HTTP zu fallen."""
    class HalbesTls(Konfiguration):
        tls_aktiv = False
        tls_cert = "/fast/cert.pem"
        tls_key = ""
    monkeypatch.setattr(start.settings, "laden", HalbesTls)
    start.main()
    assert "ssl_certfile" not in gestartet
    assert "ACHTUNG" in capsys.readouterr().out


def test_der_aussenport_steht_im_protokoll(gestartet, monkeypatch, capsys):
    """uvicorn meldet Port 8000 -- das stimmt im Container und fuehrt von
    aussen in die Irre."""
    monkeypatch.setenv("WEBUI_PORT", "3333")
    start.main()
    assert "3333" in capsys.readouterr().out
