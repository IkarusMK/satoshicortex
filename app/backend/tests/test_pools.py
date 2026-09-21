"""Die Pool-Erkennung.

Bitcoin kennt keine Pools -- man erkennt sie nur an Spuren, die sie selbst
hinterlassen. Beide Wege werden geprueft, und vor allem der Fall, in dem
keiner greift: dann muss "unbekannt" herauskommen und nicht geraten werden.
"""
import json

import pytest

from satcortex import pools

LISTE = [
    {"name": "Foundry USA", "addresses": ["1FoundryAdr"],
     "tags": ["/Foundry USA Pool/", "Foundry"]},
    {"name": "AntPool", "addresses": ["1AntAdr"], "tags": ["/AntPool/"]},
    {"name": "BTC.com", "addresses": [], "tags": ["/BTC.COM/"]},
    {"name": "Kaputt ohne Namen", "addresses": [], "tags": []},
    {"name": "", "addresses": ["1EgalAdr"], "tags": ["egal"]},
    "gar kein Objekt",
]


def kennung(text: str) -> str:
    """Ein Coinbase-Skript bauen, das diesen Text als Datenstueck enthaelt."""
    roh = text.encode("ascii")
    return (b"\x03\x00\x00\x00" + bytes([len(roh)]) + roh).hex()


@pytest.fixture
def verzeichnis(tmp_path):
    p = tmp_path / "pools.json"
    p.write_text(json.dumps(LISTE))
    return pools.lade(str(p))


def test_erkennung_ueber_die_auszahlungsadresse(verzeichnis):
    """Der verlaesslichere Weg: ein Pool zahlt sich ueber Jahre an dieselben
    Adressen aus."""
    assert verzeichnis.erkenne("", ["1AntAdr"]) == "AntPool"


def test_erkennung_ueber_die_kennung(verzeichnis):
    assert verzeichnis.erkenne(kennung("/AntPool/")) == "AntPool"
    assert verzeichnis.erkenne(kennung("xx/BTC.COM/yy")) == "BTC.com"


def test_die_adresse_gewinnt_gegen_die_kennung(verzeichnis):
    """Die Kennung ist freiwillig und faelschbar -- jeder kann '/AntPool/' in
    seine Coinbase schreiben. Die Auszahlungsadresse nicht."""
    assert verzeichnis.erkenne(kennung("/AntPool/"), ["1FoundryAdr"]) == "Foundry USA"


def test_die_laengere_kennung_gewinnt(verzeichnis):
    """Sonst schlaegt 'Foundry' zu, bevor '/Foundry USA Pool/' drankommt --
    hier zufaellig derselbe Name, bei anderen Paaren waere es der falsche."""
    assert verzeichnis.erkenne(kennung("/Foundry USA Pool/")) == "Foundry USA"


def test_unbekannt_bleibt_unbekannt(verzeichnis):
    """Einen Pool zu raten waere schlimmer als keiner: die Blockansicht ist
    dann eine Behauptung."""
    assert verzeichnis.erkenne(kennung("/voellig anderes/"), ["1Fremd"]) is None
    assert verzeichnis.erkenne("") is None


def test_kaputte_eintraege_kippen_die_liste_nicht(verzeichnis):
    assert verzeichnis.erkenne("", ["1EgalAdr"]) is None      # Eintrag ohne Namen
    assert len(verzeichnis) == 3                              # die drei echten


def test_fehlende_liste_ist_kein_fehler(tmp_path):
    """Ein fehlendes Namensschild haelt die Auswertung nicht an."""
    assert pools.lade(str(tmp_path / "gibtsnicht.json")) is None


def test_unbrauchbare_liste_ist_kein_fehler(tmp_path):
    kaputt = tmp_path / "k.json"
    kaputt.write_text("{ kein json")
    assert pools.lade(str(kaputt)) is None

    fremd = tmp_path / "f.json"
    fremd.write_text('{"gar": "keine liste"}')
    assert pools.lade(str(fremd)) is None


# ── Gegen ECHTE Bloecke ───────────────────────────────────────────────────
#
# Nicht erfunden: des Betreibers Bloecke 966.077 bis 966.088 vom 08.09.2026, so wie
# sein Knoten sie gesehen hat. In der Ansicht standen ACHT von zwoelf als
# "unbekannt" -- das sah aus wie eine kaputte Ansicht und war eine kaputte
# Erkennung.
#
# Warum sie versagte, steht in coinbase.spuren(): der saubere Skriptdurchlauf
# findet bei modernen Coinbases fast nichts. Foundry schreibt seine Kennung
# roh ins Feld (das fuehrende "/" ist Opcode 0x2f und laesst den Durchlauf
# abbrechen), AntPool haengt Extranonce an dieselbe Zeichenkette und drueckt
# sie damit unter die Druckbarkeitsschwelle.
#
# Die Kennungen unten sind der zutreffende Ausschnitt aus pools-v2.json
# (mempool/mining-pools, MIT). Die Adressen sind bewusst LEER: sie halfen bei
# keinem einzigen dieser zwoelf Bloecke, weil die Liste dort historisch ist.
# Genau das soll dieser Test mit abbilden -- getragen hat allein die Kennung.

ECHTE_KENNUNGEN = [
    {
        "name": "F2Pool",
        "addresses": [],
        "tags": [
            "七彩神仙鱼",
            "F2Pool",
            "🐟"
        ]
    },
    {
        "name": "AntPool",
        "addresses": [],
        "tags": [
            "/AntPool/",
            "Mined By AntPool",
            "Mined by AntPool"
        ]
    },
    {
        "name": "NiceHash",
        "addresses": [],
        "tags": [
            "/NiceHashSolo",
            "/NiceHash/",
            "/NiceHashMining/"
        ]
    },
    {
        "name": "ViaBTC",
        "addresses": [],
        "tags": [
            "/ViaBTC/",
            "viabtc.com deploy"
        ]
    },
    {
        "name": "Binance Pool",
        "addresses": [],
        "tags": [
            "/Binance/",
            "binance"
        ]
    },
    {
        "name": "Foundry USA",
        "addresses": [],
        "tags": [
            "/2cDw/",
            "Foundry USA Pool"
        ]
    },
    {
        "name": "MARA Pool",
        "addresses": [],
        "tags": [
            "MARA Pool",
            "MARA Made in USA"
        ]
    }
]

ECHTE_BLOECKE = (
    (966088, "F2Pool",
     "03c8bd0e2cfabe6d6d1b59c5fdc32436bf55d870ff242b5751b79753b9473fa1b10989cf231b526ecf10000000f09f909f092f4632506f6f6c2f650000000000000000000000000000000000000000000000000000000000000000000000050018e6f175"),
    (966087, "NiceHash",
     "03c7bd0e9c68db2cab10152b870000052f4e696365486173684d696e696e672f"),
    (966086, "AntPool",
     "03c6bd0e194d696e656420627920416e74506f6f6c20000023008b4fa021fabe6d6d9f129e0ce05bb0377a39289bc8dc1244c8c8acbf8e8e8284f50f99212aaee80e1000000000000000000030b8f8c9e3f700000000"),
    (966085, "Foundry USA",
     "03c5bd0e048e9901172f466f756e6472792055534120506f6f6c202364726f70676f6c642f2a1140d11d2c000000000000"),
    (966084, "F2Pool",
     "03c4bd0e2cfabe6d6df7d99ceea687f9a248c2b8cf9cd5cc3c8346348de9fc7c391c71a82826db25ba10000000f09f909f0c2f6632706f6f6c2e6b7a2f63000000000000000000000000000000000000000000000000000000000000000005004fa30200"),
    (966083, "ViaBTC",
     "03c3bd0e082f5669614254432f2cfabe6d6df86564611927c1c28788210d26c90d6b75a1c949011718ac00a55d7e21c67c5e1000000000000000109549ec03b21642f7a93c3016d9b5000000000000"),
    (966082, "Foundry USA",
     "03c2bd0e04c6a66e0d2f466f756e6472792055534120506f6f6c202364726f70676f6c642f10182bce0107000000000000"),
    (966081, "Foundry USA",
     "03c1bd0e0481bbe50b2f466f756e6472792055534120506f6f6c202364726f70676f6c642f0826a7b32000000000000000"),
    (966080, "AntPool",
     "03c0bd0e1b4d696e656420627920416e74506f6f6c393539150021017405f39dfabe6d6db99a73a615ddd22f9f058592027ca5d9e077ff58b8600330c5353f962813d799100000000000000000002fde795b010000000000"),
    (966079, "MARA Pool",
     "03bfbd0e04a806a06a7c204d415241204d61646520696e2055534120f09f87baf09f87b8207c76303513fdbad5700000374985ffffffff"),
    (966078, "ViaBTC",
     "03bebd0e182f5669614254432f4d696e6564206279206563676274632f2cfabe6d6d5eeda0c9139c29556be2c2558c2613f84d51004f7d3a6729a4ca2a223ed82c92100000000000000010a448bf024f421990aa4555fc651d010000000000"),
    (966077, "Binance Pool",
     "03bdbd0e1062696e616e63652f7d00ac0368c0b33bfabe6d6d9cb7757ef23f9e3067a3dbf5f5fb1c52c34e6efb95f19c887ede7e43cbccdf5d100000000000000000003718e209000000000000"),
)


@pytest.fixture
def echtes_verzeichnis(tmp_path):
    p = tmp_path / "echte_pools.json"
    p.write_text(json.dumps(ECHTE_KENNUNGEN), encoding="utf-8")
    return pools.lade(str(p))


def test_die_pools_echter_bloecke_werden_erkannt(echtes_verzeichnis):
    """Vorher vier von zwoelf, jetzt zwoelf von zwoelf."""
    daneben = [(h, erwartet, echtes_verzeichnis.erkenne(cb, []))
               for h, erwartet, cb in ECHTE_BLOECKE
               if echtes_verzeichnis.erkenne(cb, []) != erwartet]
    assert not daneben, f"nicht erkannt: {daneben}"


def test_die_kennung_zaehlt_auch_wenn_muell_daneben_steht(echtes_verzeichnis):
    """AntPool haengt acht Bytes Extranonce an "Mined by AntPool ". Der
    saubere Durchlauf warf das ganze Stueck weg, Kennung inklusive."""
    _, erwartet, cb = next(b for b in ECHTE_BLOECKE if b[0] == 966086)
    assert erwartet == "AntPool"
    assert echtes_verzeichnis.erkenne(cb, []) == "AntPool"


def test_die_kennung_zaehlt_auch_ausserhalb_eines_datenstuecks(echtes_verzeichnis):
    """Foundry schreibt "/Foundry USA Pool #dropgold/" roh ins Feld. Das
    fuehrende "/" ist Opcode 0x2f -- "schiebe 47 Bytes", die es nicht gibt."""
    _, erwartet, cb = next(b for b in ECHTE_BLOECKE if b[0] == 966085)
    assert erwartet == "Foundry USA"
    assert echtes_verzeichnis.erkenne(cb, []) == "Foundry USA"


def test_grossschreibung_entscheidet_nicht_ueber_den_pool(echtes_verzeichnis):
    """F2Pool schreibt mal "/F2Pool/", mal "/f2pool.kz/". Die Liste kennt nur
    die eine Schreibweise -- und beide Bloecke sind F2Pool."""
    for hoehe in (966088, 966084):
        _, erwartet, cb = next(b for b in ECHTE_BLOECKE if b[0] == hoehe)
        assert echtes_verzeichnis.erkenne(cb, []) == "F2Pool" == erwartet
