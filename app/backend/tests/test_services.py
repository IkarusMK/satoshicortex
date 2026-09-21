import hashlib
from pathlib import Path

import pytest

from satcortex import services


# ----------------------------------------------------------------- rendern

def test_platzhalter_werden_ersetzt():
    assert services.rendere("a={{EINS}} b={{ZWEI}}", {"EINS": "1", "ZWEI": "2"}) == "a=1 b=2"


def test_rpcauth_mit_dollarzeichen_ueberlebt():
    # Genau daran waere string.Template gescheitert.
    hash_ = "nutzer:abc123$deadbeefcafe"
    ergebnis = services.rendere("rpcauth={{RPCAUTH}}", {"RPCAUTH": hash_})
    assert ergebnis == f"rpcauth={hash_}"


def test_geschweifte_klammern_im_wert_stoeren_nicht():
    # Daran waere str.format gescheitert.
    ergebnis = services.rendere("x={{W}}", {"W": "{nicht: ersetzen}"})
    assert ergebnis == "x={nicht: ersetzen}"


def test_fehlender_wert_meldet_sich_deutlich():
    with pytest.raises(KeyError) as fehler:
        services.rendere("{{DA}} und {{FEHLT}}", {"DA": "x"})
    assert "FEHLT" in str(fehler.value)
    assert "DA" not in str(fehler.value)      # nur das Fehlende wird genannt


def test_derselbe_platzhalter_mehrfach():
    assert services.rendere("{{A}}-{{A}}", {"A": "z"}) == "z-z"


# ------------------------------------------------------------------ ablage

@pytest.fixture
def ablage(tmp_path):
    return services.Konfigurationsablage(str(tmp_path / "config"))


def test_neuer_dienst_ist_unkonfiguriert(ablage):
    assert ablage.status("bitcoind").zustand is services.Zustand.UNKONFIGURIERT


def test_geschrieben_aber_nicht_freigegeben_heisst_wartet(ablage):
    ablage.schreibe("bitcoind", "inhalt")
    assert ablage.status("bitcoind").zustand is services.Zustand.WARTET


def test_nach_freigabe_laeuft_der_dienst(ablage):
    ablage.schreibe("bitcoind", "inhalt")
    ablage.gib_frei("bitcoind")
    assert ablage.status("bitcoind").zustand is services.Zustand.FREIGEGEBEN


def test_sperren_nimmt_die_freigabe_zurueck(ablage):
    ablage.schreibe("bitcoind", "inhalt")
    ablage.gib_frei("bitcoind")
    ablage.sperre("bitcoind")
    assert ablage.status("bitcoind").zustand is services.Zustand.WARTET
    ablage.sperre("bitcoind")          # zweimal darf nicht scheitern


def test_pruefsumme_entspricht_dem_inhalt(ablage):
    ablage.schreibe("tor", "hallo")
    erwartet = hashlib.sha256(b"hallo").hexdigest()
    assert ablage.pruefsumme("tor") == erwartet


def test_pruefsumme_aendert_sich_mit_dem_inhalt(ablage):
    a = ablage.schreibe("tor", "eins")
    b = ablage.schreibe("tor", "zwei")
    assert a != b


def test_schreiben_hinterlaesst_keine_temporaeren_reste(ablage):
    ablage.schreibe("lnd", "x" * 10000)
    dateien = sorted(p.name for p in Path(ablage.pfad).iterdir())
    assert dateien == ["lnd.conf"]      # kein .tmp uebrig geblieben


def test_alle_liefert_jeden_dienst(ablage):
    ablage.schreibe("bitcoind", "a")
    ablage.gib_frei("bitcoind")
    ergebnis = ablage.alle(["bitcoind", "lnd", "tor"])
    zustaende = {d["name"]: d["zustand"] for d in ergebnis}
    assert zustaende == {
        "bitcoind": "freigegeben",
        "lnd": "unkonfiguriert",
        "tor": "unkonfiguriert",
    }
