"""Was die Dienste melden -- lesbar ohne Docker-Socket.

Der Socket kaeme fuer diese Anwendung nicht in Frage: auf einem Geraet mit
einer Wallet ist er gleichbedeutend mit root. "docker logs" faellt damit aus.
Es geht auch ohne -- die Dienste schreiben ihre Protokolle in dasselbe
Datenverzeichnis, das die Anwendung ohnehin eingehaengt hat.
"""
import logging

import pytest

from satcortex import logs


# ── Welche Quellen es gibt ─────────────────────────────────────────────────

def test_die_vier_quellen_stehen_fest(tmp_path):
    """Ein fester Satz Namen, keine freien Pfade. Der Name ist das EINZIGE,
    was von aussen kommt -- waere er ein Pfad, waere die Anwendung ein
    Dateibetrachter fuer das ganze Dateisystem."""
    namen = [q["name"] for q in logs.quellen(str(tmp_path))]
    assert namen == ["satcortex", "bitcoind", "lnd", "tor"]


def test_ein_erfundener_name_wird_abgewiesen(tmp_path):
    for boese in ("../../etc/passwd", "/etc/passwd", "bitcoind/../../x", ""):
        with pytest.raises(ValueError):
            logs.lies(boese, str(tmp_path))


def test_quellen_sagen_ob_es_die_datei_gibt(tmp_path):
    (tmp_path / "bitcoind").mkdir()
    (tmp_path / "bitcoind" / "debug.log").write_text("eine Zeile\n")
    nach_name = {q["name"]: q for q in logs.quellen(str(tmp_path))}
    assert nach_name["bitcoind"]["da"] is True
    assert nach_name["bitcoind"]["groesse_bytes"] == len("eine Zeile\n")
    # lnd laeuft in diesem Fall noch nicht
    assert nach_name["lnd"]["da"] is False


# ── Das Ende einer Datei lesen ─────────────────────────────────────────────

def _log(tmp_path, zeilen):
    ziel = tmp_path / "bitcoind" / "debug.log"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("".join(f"{z}\n" for z in zeilen), encoding="utf-8")
    return ziel


def test_kurze_datei_kommt_ganz(tmp_path):
    _log(tmp_path, ["eins", "zwei", "drei"])
    d = logs.lies("bitcoind", str(tmp_path))
    assert d["zeilen"] == ["eins", "zwei", "drei"]
    assert d["abgeschnitten"] is False


def test_nur_die_letzten_zeilen(tmp_path):
    _log(tmp_path, [str(i) for i in range(1000)])
    d = logs.lies("bitcoind", str(tmp_path), zeilen=5)
    assert d["zeilen"] == ["995", "996", "997", "998", "999"]


def test_eine_riesige_datei_wird_nicht_ganz_gelesen(tmp_path, monkeypatch):
    """debug.log wird ueber Monate gross. Sie ganz einzulesen waere ein
    sicherer Weg, dem Container den Speicher wegzunehmen -- also wird vom
    Ende her gelesen, nicht von vorn."""
    monkeypatch.setattr(logs, "HOECHSTENS_BYTES", 200)
    _log(tmp_path, [f"zeile-{i:04d}" for i in range(500)])
    d = logs.lies("bitcoind", str(tmp_path), zeilen=logs.ZEILEN_HOECHSTENS)
    assert d["abgeschnitten"] is True
    assert d["zeilen"][-1] == "zeile-0499"
    # Nicht mehr, als in die Grenze passt
    assert sum(len(z) + 1 for z in d["zeilen"]) <= 200


def test_die_angeschnittene_erste_zeile_faellt_weg(tmp_path, monkeypatch):
    """Wer mitten in einer Zeile zu lesen anfaengt, bekommt ihren Rest. Ein
    halber Zeitstempel sieht aus wie eine echte Meldung und ist keine."""
    monkeypatch.setattr(logs, "HOECHSTENS_BYTES", 25)
    _log(tmp_path, ["aaaaaaaaaaaaaaaaaaaa", "bbbb", "cccc"])
    d = logs.lies("bitcoind", str(tmp_path), zeilen=99)
    assert all(not z.startswith("a") for z in d["zeilen"]), d["zeilen"]


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    """Vor der Einrichtung gibt es sie noch nicht. Das ist ein Zustand, keine
    Stoerung -- die Oberflaeche soll es sagen koennen, nicht abstuerzen."""
    d = logs.lies("lnd", str(tmp_path))
    assert d["da"] is False and d["zeilen"] == []


def test_kaputte_zeichen_werfen_nichts_um(tmp_path):
    ziel = tmp_path / "bitcoind" / "debug.log"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"gut\n\xff\xfe kaputt\nauch gut\n")
    d = logs.lies("bitcoind", str(tmp_path))
    assert d["zeilen"][0] == "gut" and d["zeilen"][-1] == "auch gut"


def test_leere_datei(tmp_path):
    _log(tmp_path, [])
    assert logs.lies("bitcoind", str(tmp_path))["zeilen"] == []


@pytest.mark.parametrize("gewuenscht,erwartet", [
    (0, 1), (-5, 1), (99999, logs.ZEILEN_HOECHSTENS), (50, 50),
])
def test_die_zeilenzahl_wird_eingegrenzt(tmp_path, gewuenscht, erwartet):
    """Sonst bestimmte der Aufrufer, wieviel Arbeit der Server macht."""
    assert logs._zeilenzahl(gewuenscht) == erwartet


# ── Das eigene Protokoll ───────────────────────────────────────────────────

def test_die_eigenen_meldungen_landen_im_ringspeicher(tmp_path):
    ring = logs.Ringspeicher(plaetze=3)
    ring.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    ring.emit(logging.LogRecord("t", logging.INFO, "?", 1, "hallo", (), None))
    assert list(ring.zeilen) == ["INFO hallo"]


def test_der_ringspeicher_laeuft_nicht_ueber(tmp_path):
    """Er ist eine Anzeige, kein Archiv. Unbegrenzt waere er ein Leck, das
    genau so lange waechst wie die Anwendung laeuft."""
    ring = logs.Ringspeicher(plaetze=3)
    ring.setFormatter(logging.Formatter("%(message)s"))
    for i in range(10):
        ring.emit(logging.LogRecord("t", logging.INFO, "?", 1, str(i), (), None))
    assert list(ring.zeilen) == ["7", "8", "9"]


def test_mitschreiben_haengt_sich_nur_einmal_ein():
    """baue_app() laeuft in den Tests dutzendfach. Jedes Mal einen Handler
    mehr, und dieselbe Meldung stuende hinterher dutzendfach da.

    Vorher aufraeumen: andere Tests bauen die App und haengen ihn dabei schon
    ein. Dieser Test soll die Schranke pruefen, nicht die Reihenfolge, in der
    pytest laeuft."""
    wurzel = logging.getLogger()
    for vorhandener in [h for h in wurzel.handlers
                        if isinstance(h, logs.Ringspeicher)]:
        wurzel.removeHandler(vorhandener)
    logs._ring = None

    vorher = len(wurzel.handlers)
    erster = logs.mitschreiben()
    zweiter = logs.mitschreiben()
    try:
        assert erster is zweiter
        assert len(wurzel.handlers) == vorher + 1
    finally:
        wurzel.removeHandler(erster)
        logs._ring = None


def test_das_eigene_protokoll_kommt_ueber_dieselbe_tuer(tmp_path):
    ring = logs.mitschreiben()
    try:
        logging.getLogger("satcortex.test").warning("etwas ist passiert")
        d = logs.lies("satcortex", str(tmp_path))
        assert any("etwas ist passiert" in z for z in d["zeilen"])
        assert d["da"] is True
    finally:
        logging.getLogger().removeHandler(ring)
        logs._ring = None
