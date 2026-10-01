"""Der Waechter fuer die Electrum-Apps: schlaegt er an, wenn er soll?

Aus dem Betrieb, 28.09.2026: die Frage, wie bestaendig das ist -- dass man
nicht nach sechs Monaten und drei Updates herausfliegt.
Geprueft wird die Auswertung -- ohne Netz, mit ausgedachten Quelltexten.
"""
import importlib.util
from pathlib import Path

from satcortex import electrum

_PFAD = Path(__file__).resolve().parents[3] / "tools" / "electrum_waechter.py"
_SPEC = importlib.util.spec_from_file_location("electrum_waechter", _PFAD)
waechter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waechter)

UNSERE = electrum.Dienst(None, lambda: None).befehle

TREZOR_ARTIG = """
    protocolVersion: '1.4',
    await client.request('blockchain.scripthash.get_history', sh);
    await client.request("server.ping");
"""
BITBOX_ARTIG = '''
const supportedProtocolVersion = "1.4"
err := c.rpc.MethodBlocking(ctx, &r, "blockchain.block.headers", start, n)
'''


def test_befehle_und_version_werden_gefunden():
    assert waechter.befehle(TREZOR_ARTIG) == {
        "blockchain.scripthash.get_history", "server.ping"}
    assert waechter.versionen(TREZOR_ARTIG) == {"1.4"}
    assert waechter.versionen(BITBOX_ARTIG) == {"1.4"}
    assert waechter.versionen('const PROTOCOL_VERSION: &str = "1.4";') == {"1.4"}


def test_alles_bekannte_ergibt_keinen_befund():
    assert waechter.vergleiche("Trezor", waechter.befehle(TREZOR_ARTIG),
                               {"1.4"}, UNSERE, "1.4") == []


def test_ein_neuer_befehl_schlaegt_an():
    """Genau der Fall, vor dem er warnen soll: 1.7 ersetzt scripthash.* durch
    scriptpubkey.* (protocol-changes.rst)."""
    text = TREZOR_ARTIG + "request('blockchain.scriptpubkey.get_history', s)"
    befunde = waechter.vergleiche("Trezor", waechter.befehle(text), {"1.4"},
                                  UNSERE, "1.4")
    assert befunde and "blockchain.scriptpubkey.get_history" in befunde[0]


def test_eine_andere_version_schlaegt_an():
    befunde = waechter.vergleiche("BitBox", {"server.ping"}, {"1.6"},
                                  UNSERE, "1.4")
    assert befunde and "1.6" in befunde[0]


def test_nichts_gefunden_ist_auch_ein_befund():
    """Verschiebt eine App den Code, faende der Waechter nichts -- und
    meldete gruen. Stille darf nicht als "alles gut" durchgehen."""
    assert len(waechter.vergleiche("X", set(), set(), UNSERE, "1.4")) == 2
