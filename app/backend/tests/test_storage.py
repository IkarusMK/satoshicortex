import os
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from satcortex import facts, storage

Nutzung = namedtuple("Nutzung", "total used free")
GB = 1024 ** 3


def _fake_platz(monkeypatch, frei_gb, gesamt_gb=None):
    gesamt_gb = gesamt_gb or frei_gb * 2
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda _p: Nutzung(gesamt_gb * GB, (gesamt_gb - frei_gb) * GB, frei_gb * GB),
    )


def test_fehlender_pfad_wird_erkannt(tmp_path):
    p = storage.pruefe_platte(str(tmp_path / "gibtsnicht"), 100, 50, "DATA_BULK")
    assert p.bewertung is storage.Bewertung.FEHLT
    assert not p.vorhanden
    assert p.meldung == "pfad_fehlt"
    assert p.werte["variable"] == "DATA_BULK"   # nennt die richtige Variable


def test_genug_platz(tmp_path, monkeypatch):
    _fake_platz(monkeypatch, 2000)
    p = storage.pruefe_platte(str(tmp_path), 1000, 900, "DATA_BULK")
    assert p.bewertung is storage.Bewertung.GENUG
    assert p.frei_gb == 2000


def test_knapper_platz_nennt_die_fehlende_menge(tmp_path, monkeypatch):
    _fake_platz(monkeypatch, 950)
    p = storage.pruefe_platte(str(tmp_path), 1000, 900, "DATA_BULK")
    assert p.bewertung is storage.Bewertung.KNAPP
    assert p.werte["fehlend"] == 50


def test_zu_wenig_platz_erklaert_warum_pruning_nicht_hilft(tmp_path, monkeypatch):
    _fake_platz(monkeypatch, 10)
    p = storage.pruefe_platte(str(tmp_path), 1000, 900, "DATA_BULK")
    assert p.bewertung is storage.Bewertung.ZU_WENIG
    assert p.meldung == "platz_zu_wenig"


def test_gesamturteil_richtet_sich_nach_dem_schlechteren(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()
    _fake_platz(monkeypatch, 5)                       # viel zu wenig
    ergebnis = storage.pruefe(str(bulk), str(fast))
    assert ergebnis["gesamt"] == "zu_wenig"
    assert ergebnis["weiter_moeglich"] is False


def test_eine_platte_fuer_beides_wird_erkannt_und_erklaert(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()
    _fake_platz(monkeypatch, 5000)
    ergebnis = storage.pruefe(str(bulk), str(fast))
    assert ergebnis["gleiche_platte"] is True
    assert ergebnis["meldung_gleiche_platte"] == "eine_platte"
    assert ergebnis["weiter_moeglich"] is True


def test_eine_platte_verlangt_die_summe_beider_bedarfe(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()
    # Genug fuer BULK allein, aber nicht fuer BULK+FAST zusammen.
    _fake_platz(monkeypatch, facts.bedarf_bulk_gb() + 5)
    ergebnis = storage.pruefe(str(bulk), str(fast))
    assert ergebnis["gleiche_platte"] is True
    assert ergebnis["bulk"]["bewertung"] != "genug"


def test_struktur_wird_angelegt_und_ist_wiederholbar(tmp_path):
    bulk = tmp_path / "bulk"; fast = tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()

    neu = storage.lege_struktur_an(str(bulk), str(fast))
    # Alle Unterordner plus der Verweis, der die Indizes auf die grosse
    # Platte holt.
    assert len(neu) == len(storage.BULK_UNTERORDNER) + len(storage.FAST_UNTERORDNER) + 1
    assert (bulk / "blocks").is_dir()
    assert (fast / "bitcoind").is_dir()

    # Zweiter Aufruf darf nicht scheitern und nichts doppelt melden.
    assert storage.lege_struktur_an(str(bulk), str(fast)) == []


def test_bedarfszahlen_sind_plausibel():
    assert facts.bedarf_bulk_gb() > facts.KETTE_GB
    assert facts.bedarf_fast_gb() < 50          # die schnelle Platte bleibt klein
    assert facts.MINDEST_BULK_GB < facts.bedarf_bulk_gb()


# ── Zwei Pfade genuegen: den Rest legt die Anwendung an (25.08.2026) ─────────

def test_struktur_entsteht_aus_zwei_pfaden(tmp_path):
    """Der Nutzer gibt DATA_BULK und DATA_FAST an -- sonst nichts."""
    bulk, fast = tmp_path / "bulk", tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()

    storage.lege_struktur_an(str(bulk), str(fast))

    for name in storage.BULK_UNTERORDNER:
        assert (bulk / name).is_dir(), f"{name} fehlt auf der grossen Platte"
    for name in storage.FAST_UNTERORDNER:
        assert (fast / name).is_dir(), f"{name} fehlt auf der schnellen Platte"


def test_indizes_zeigen_auf_die_grosse_platte(tmp_path):
    """Core kennt keine Option fuer den Index-Pfad -- ohne den Verweis lägen
    die rund 75 GB auf der kleinen schnellen Platte."""
    bulk, fast = tmp_path / "bulk", tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()

    storage.lege_struktur_an(str(bulk), str(fast))

    verweis = fast / "bitcoind" / "indexes"
    assert verweis.is_symlink(), "der Verweis auf die Indizes fehlt"
    assert Path(os.readlink(verweis)) == bulk / "coreindex"


def test_zweiter_aufruf_stolpert_nicht_ueber_den_verweis(tmp_path):
    bulk, fast = tmp_path / "bulk", tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()

    storage.lege_struktur_an(str(bulk), str(fast))
    neu = storage.lege_struktur_an(str(bulk), str(fast))

    assert neu == [], "beim zweiten Mal darf nichts mehr entstehen"


def test_vorhandenes_index_verzeichnis_wird_nicht_ueberschrieben(tmp_path):
    """Wer von einer aelteren Fassung kommt, hat dort echte Daten liegen."""
    bulk, fast = tmp_path / "bulk", tmp_path / "fast"
    bulk.mkdir(); fast.mkdir()
    echte_daten = fast / "bitcoind" / "indexes"
    echte_daten.mkdir(parents=True)
    (echte_daten / "txindex").mkdir()

    storage.lege_struktur_an(str(bulk), str(fast))

    assert not echte_daten.is_symlink()
    assert (echte_daten / "txindex").is_dir()
