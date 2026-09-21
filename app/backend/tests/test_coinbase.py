"""Die Coinbase lesen -- gepruefte Faelle aus der echten Blockkette."""
import pytest

from satcortex import coinbase

# Der allererste Block, wie ihn jeder vollstaendige Knoten selbst besitzt.
GENESIS = ("04ffff001d0104455468652054696d65732030332f4a616e2f32303039204368616e"
           "63656c6c6f72206f6e206272696e6b206f66207365636f6e64206261696c6f757420"
           "666f722062616e6b73")
GENESIS_TEXT = ("The Times 03/Jan/2009 Chancellor on brink of "
                "second bailout for banks")


def test_satoshis_nachricht_im_ersten_block():
    assert GENESIS_TEXT in coinbase.botschaften(GENESIS)


def test_das_laengenbyte_landet_nicht_im_text():
    """Vor der Nachricht steht 0x45 -- als Zeichen ein 'E'.

    Wer einfach alle druckbaren Bytes herausfischt, liefert 'EThe Times ...'.
    Genau dieser Fehler soll nicht wieder passieren.
    """
    gefunden = coinbase.botschaften(GENESIS)
    assert GENESIS_TEXT in gefunden
    assert not any(t.startswith("EThe") for t in gefunden)


def test_pool_kennung_wird_gefunden():
    # Muster einer heutigen Coinbase: Hoehe, dann die Kennung des Pools.
    kennung = b"/Foundry USA Pool #dropgold/"
    script = bytes([3, 0x01, 0x02, 0x03]) + bytes([len(kennung)]) + kennung
    assert "/Foundry USA Pool #dropgold/" in coinbase.botschaften(script.hex())


def test_pushdata1_wird_verstanden():
    text = b"x" * 200                       # zu lang fuer ein einfaches Push
    script = bytes([coinbase.OP_PUSHDATA1, 200]) + text
    assert coinbase.botschaften(script.hex()) == ["x" * 200]


def test_zufallsdaten_werden_nicht_als_text_ausgegeben():
    # Ein Hash sieht in Teilen druckbar aus, ist aber keine Botschaft.
    zufall = bytes(range(32))
    script = bytes([32]) + zufall
    assert coinbase.botschaften(script.hex()) == []


def test_abgeschnittenes_skript_stuerzt_nicht_ab():
    # Kuendigt 100 Bytes an, liefert 3. Miner schreiben dort beliebiges hinein.
    #
    # Frueher stand hier == [], und das war zu streng: genau SO sieht die
    # Coinbase von Foundry aus. Deren "/Foundry USA Pool #dropgold/" beginnt
    # mit "/" -- Opcode 0x2f, "schiebe 47 Bytes", die es nicht gibt. Wer hier
    # nichts zurueckgibt, gibt auch bei Foundry nichts zurueck.
    #
    # Zum Anzeigen gilt trotzdem eine hoehere Schranke: vier zufaellig
    # druckbare Bytes ("dABC") sind keine Botschaft.
    assert coinbase.botschaften("64414243") == []
    assert coinbase.spuren("64414243") == ["dABC"], "zum Erkennen zaehlt es"


def test_eine_kennung_ausserhalb_eines_datenstuecks_geht_nicht_verloren():
    """Der Fall Foundry, klein nachgebaut: roher Text, dessen erstes Zeichen
    zufaellig ein Push-Opcode ist."""
    roh = b"/Foundry USA Pool #dropgold/"
    assert coinbase.botschaften(roh.hex()) == ["/Foundry USA Pool #dropgold/"]


@pytest.mark.parametrize("unsinn", ["", "zz", "0", "4c"])
def test_unsinn_liefert_leere_liste(unsinn):
    assert coinbase.botschaften(unsinn) == []


def test_mehrere_stuecke_bleiben_in_reihenfolge():
    a, b = b"erster teil", b"zweiter teil"
    script = bytes([len(a)]) + a + bytes([len(b)]) + b
    assert coinbase.botschaften(script.hex()) == ["erster teil", "zweiter teil"]
