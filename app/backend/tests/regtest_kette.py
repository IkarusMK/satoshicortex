"""Eine frische Regtest-Kette mit echtem Bitcoin Core -- fuer die Tests, die
pruefen, ob Core sich so verhaelt, wie die Attrappen es behaupten.

Laeuft, wenn SATCORTEX_BITCOIND auf ein bitcoind zeigt; sonst werden die
Tests uebersprungen. Ohne jede Verbindung nach aussen, in einem
Wegwerfverzeichnis, RPC nur auf 127.0.0.1.
"""
import os
import secrets
import socket
import subprocess
import time

import pytest

from satcortex import rpc

BITCOIND = os.environ.get("SATCORTEX_BITCOIND", "")

nur_mit_core = pytest.mark.skipif(
    not (BITCOIND and os.path.exists(BITCOIND)),
    reason="SATCORTEX_BITCOIND zeigt auf kein bitcoind")


def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    verzeichnis = tmp_path_factory.mktemp("regtest")
    port = _freier_port()
    passwort = secrets.token_hex(16)
    prozess = subprocess.Popen([
        BITCOIND, "-regtest", f"-datadir={verzeichnis}", "-server",
        "-listen=0", "-connect=0", "-dnsseed=0", "-fixedseeds=0",
        "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1", f"-rpcport={port}",
        "-rpcuser=probe", f"-rpcpassword={passwort}",
        "-txindex=1", "-blockfilterindex=1", "-fallbackfee=0.0002",
        "-printtoconsole=0",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    knoten = rpc.Knoten(host="127.0.0.1", port=port, benutzer="probe",
                        passwort=passwort, zeitlimit=30)
    frist = time.time() + 60
    while True:
        try:
            knoten.ruf("getblockchaininfo")
            break
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            if time.time() > frist or prozess.poll() is not None:
                prozess.kill()
                pytest.fail("bitcoind kam nicht hoch")
            time.sleep(0.3)
    try:
        yield knoten
    finally:
        try:
            knoten.ruf("stop")
            prozess.wait(timeout=30)
        except Exception:  # noqa: BLE001 -- aufgeraeumt wird trotzdem
            prozess.kill()


def warten(knoten):
    """Bis Cores Wallets nachgezogen haben -- an der Kette gemessen: wer
    sofort fragt, sieht den alten Stand."""
    knoten.ruf("syncwithvalidationinterfacequeue")
