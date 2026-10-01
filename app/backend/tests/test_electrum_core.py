"""Von Anfang bis Ende: echtes Core, echter Server, echte Verbindung.

Aus dem Betrieb, 28.09.2026: vorher wird es mit den Befehlen selbst
ausprobiert.

Hier werden die Befehlsfolgen nachgespielt, die Trezor Suite und die
BitBoxApp schicken (aus ihrem Quelltext, nur die Befehlsnamen und ihre
Reihenfolge) -- ueber einen echten Socket gegen einen echten Server, der ein
echtes Bitcoin Core (Regtest) fragt. Und eine Zahlung, die die
nachgestellte Hardware-Wallet unterschreibt und ueber UNSEREN Server ins
Netz schickt.

Was der Server sagt, wird gegen das gepruefte, was die Wallet mit den
Schluesseln selbst sagt -- nicht gegen eine eigene Erwartung.
"""
import asyncio
import hashlib
import json
import ssl

import pytest

from satcortex import electrum, electrumserver, lesewallet, rpc
from regtest_kette import core, nur_mit_core, warten  # noqa: F401 -- core ist eine Fixture

pytestmark = nur_mit_core


@pytest.fixture(scope="module")
def szenario(core):
    core.ruf("createwallet", "geldgeber")
    core.ruf("createwallet", "geraet")
    geld = lambda: core.ruf("getnewaddress", wallet="geldgeber")  # noqa: E731
    core.ruf("generatetoaddress", 101, geld())
    konto = {d["internal"]: d["desc"] for d in core.ruf(
        "listdescriptors", wallet="geraet")["descriptors"]
        if d["desc"].startswith("wpkh(")}
    empfang = core.ruf("deriveaddresses", konto[False], [0, 9])
    core.ruf("sendtoaddress", empfang[0], 0.5, wallet="geldgeber")
    core.ruf("sendtoaddress", empfang[3], 0.25, wallet="geldgeber")
    core.ruf("generatetoaddress", 1, geld())
    core.ruf("sendtoaddress", geld(), 0.1, wallet="geraet")
    core.ruf("generatetoaddress", 1, geld())
    core.ruf("sendtoaddress", empfang[1], 0.01, wallet="geldgeber")
    warten(core)
    tpub = konto[False].split("]")[1].split("/")[0]
    name = lesewallet.anmelden(core, lesewallet.lies_schluessel(tpub), "wpkh")
    warten(core)
    return {"name": name, "konto": konto, "geld": geld}


def _skripte(core, szenario, bis=20):
    """Was eine App selbst ableitet: Empfang und Wechsel, je die ersten 20."""
    adressen = []
    for intern in (False, True):
        adressen += core.ruf("deriveaddresses", szenario["konto"][intern],
                             [0, bis - 1])
    return [lesewallet.skripthash(core.ruf("validateaddress", a)[
        "scriptPubKey"]) for a in adressen]


class Client:
    """Ein kleiner Electrum-Client: Fragen per Kennung, Meldungen gesammelt."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.kennung = 0
        self.meldungen = []

    async def frag(self, methode, *params):
        self.kennung += 1
        self.writer.write((json.dumps({"jsonrpc": "2.0", "id": self.kennung,
                                       "method": methode,
                                       "params": list(params)}) + "\n").encode())
        await self.writer.drain()
        while True:
            nachricht = json.loads(await asyncio.wait_for(
                self.reader.readline(), 30))
            if "id" not in nachricht:
                self.meldungen.append(nachricht)
                continue
            assert nachricht["id"] == self.kennung
            if "error" in nachricht:
                raise AssertionError(f"{methode}: {nachricht['error']}")
            return nachricht["result"]

    async def meldung(self, methode):
        for i, m in enumerate(self.meldungen):
            if m["method"] == methode:
                return self.meldungen.pop(i)
        while True:
            nachricht = json.loads(await asyncio.wait_for(
                self.reader.readline(), 30))
            if nachricht.get("method") == methode:
                return nachricht
            self.meldungen.append(nachricht)


def _mit_server(core, szenario, test, tls_verzeichnis=None):
    async def ablauf():
        leser = lesewallet.Leser(core, lambda: [szenario["name"]])
        bestand = electrumserver.Bestand(leser)
        dienst = electrum.Dienst(core, bestand.aktuell, version="test")
        tls = (electrumserver.tls_kontext(tls_verzeichnis)
               if tls_verzeichnis else None)
        server = electrumserver.ElectrumServer(
            dienst, bestand, tls=tls, host="127.0.0.1", port=0,
            verzoegerung=0.2)
        await server.starten()
        try:
            kontext = None
            if tls_verzeichnis:
                kontext = ssl.create_default_context(
                    cafile=electrumserver.zertifikat_datei(tls_verzeichnis))
                kontext.check_hostname = False
            r, w = await asyncio.open_connection("127.0.0.1", server.port,
                                                 ssl=kontext)
            await test(Client(r, w), server)
            w.close()
        finally:
            await server.beenden()
    asyncio.run(asyncio.wait_for(ablauf(), 120))


def _sats(btc):
    return rpc.sat_aus_btc(btc)


# ── Trezor Suite ───────────────────────────────────────────────────────────

def test_die_trezor_folge_zeigt_was_das_geraet_selbst_sagt(core, szenario):
    async def test(c, _server):
        assert (await c.frag("server.version", "Trezor Suite", "1.4"))[1] == "1.4"
        kopf = await c.frag("blockchain.headers.subscribe")
        assert kopf["height"] == core.ruf("getblockcount")
        gesehen, bestaetigt, offen, unverbraucht = set(), 0, 0, set()
        for skript in _skripte(core, szenario):
            await c.frag("blockchain.scripthash.subscribe", skript)
            for eintrag in await c.frag("blockchain.scripthash.get_history",
                                        skript):
                gesehen.add(eintrag["tx_hash"])
            guthaben = await c.frag("blockchain.scripthash.get_balance", skript)
            bestaetigt += guthaben["confirmed"]
            offen += guthaben["unconfirmed"]
            for u in await c.frag("blockchain.scripthash.listunspent", skript):
                unverbraucht.add((u["tx_hash"], u["tx_pos"]))
        for txid in gesehen:
            tx = await c.frag("blockchain.transaction.get", txid, True)
            assert tx["txid"] == txid
        assert await c.frag("blockchain.estimatefee", 2) == -1   # Regtest
        hoehe = kopf["height"]
        assert len(await c.frag("blockchain.block.header", hoehe)) == 160

        geraet = core.ruf("getbalances", wallet="geraet")["mine"]
        assert bestaetigt + offen == _sats(geraet["trusted"]) + _sats(
            geraet["untrusted_pending"])
        assert unverbraucht == {(u["txid"], u["vout"]) for u in core.ruf(
            "listunspent", 0, wallet="geraet")}
        assert gesehen == {e["txid"] for e in core.ruf(
            "listtransactions", "*", 100, 0, True, wallet="geraet")}
    _mit_server(core, szenario, test)


# ── BitBoxApp ──────────────────────────────────────────────────────────────

def _blockhash(kopf_hex):
    return hashlib.sha256(hashlib.sha256(bytes.fromhex(kopf_hex))
                          .digest()).digest()[::-1].hex()


def test_die_bitbox_folge_prueft_koepfe_und_merkle_beweise(core, szenario):
    """Die BitBoxApp prueft selbst nach (SPV): die Koepfe muessen eine Kette
    bilden, und jeder Merkle-Beweis muss zur Wurzel im Kopf fuehren."""
    async def test(c, _server):
        await c.frag("server.version", "BitBoxApp", "1.4")
        spitze = (await c.frag("blockchain.headers.subscribe"))["height"]
        koepfe, start = [], 0
        while start <= spitze:
            stueck = await c.frag("blockchain.block.headers", start, 2016)
            assert stueck["max"] == 2016
            koepfe += [stueck["hex"][i:i + 160]
                       for i in range(0, len(stueck["hex"]), 160)]
            start += stueck["count"]
            if not stueck["count"]:
                break
        assert len(koepfe) == spitze + 1
        for vorher, kopf in zip(koepfe, koepfe[1:]):
            assert bytes.fromhex(kopf)[4:36][::-1].hex() == _blockhash(vorher)
        assert _blockhash(koepfe[-1]) == core.ruf("getbestblockhash")

        for skript in _skripte(core, szenario):
            for eintrag in await c.frag("blockchain.scripthash.get_history",
                                        skript):
                if eintrag["height"] <= 0:
                    continue
                beweis = await c.frag("blockchain.transaction.get_merkle",
                                      eintrag["tx_hash"], eintrag["height"])
                h = bytes.fromhex(eintrag["tx_hash"])[::-1]
                stelle = beweis["pos"]
                for nachbar in beweis["merkle"]:
                    n = bytes.fromhex(nachbar)[::-1]
                    h = hashlib.sha256(hashlib.sha256(
                        n + h if stelle & 1 else h + n).digest()).digest()
                    stelle >>= 1
                kopf = bytes.fromhex(koepfe[eintrag["height"]])
                assert h == kopf[36:68]
        assert await c.frag("blockchain.relayfee") > 0
    _mit_server(core, szenario, test)


# ── Senden ueber unseren Server ────────────────────────────────────────────

def test_eine_vom_geraet_unterschriebene_zahlung_geht_ueber_uns_hinaus(
        core, szenario):
    """So zahlt eine Hardware-Wallet ueber Electrum: das GERAET unterschreibt,
    der Server reicht nur weiter. Danach meldet er die Aenderung von selbst
    -- erst im Mempool, dann im Block."""
    async def test(c, server):
        await c.frag("server.version", "Trezor Suite", "1.4")
        await c.frag("blockchain.headers.subscribe")
        skripte = _skripte(core, szenario)
        for skript in skripte:
            await c.frag("blockchain.scripthash.subscribe", skript)

        fertig = core.ruf("send", [{szenario["geld"](): 0.02}], None,
                          "unset", None, {"add_to_wallet": False},
                          wallet="geraet")
        assert fertig["complete"]
        txid = await c.frag("blockchain.transaction.broadcast", fertig["hex"])
        assert txid == core.ruf("decoderawtransaction", fertig["hex"])["txid"]
        assert txid in core.ruf("getrawmempool")

        warten(core)
        server.anstossen()
        meldung = await c.meldung("blockchain.scripthash.subscribe")
        skript = meldung["params"][0]
        assert skript in skripte
        geschichte = await c.frag("blockchain.scripthash.get_history", skript)
        assert {"tx_hash": txid, "height": 0} == {
            k: v for k, v in geschichte[-1].items() if k != "fee"}

        core.ruf("generatetoaddress", 1, szenario["geld"]())
        warten(core)
        server.anstossen()
        kopf = await c.meldung("blockchain.headers.subscribe")
        assert kopf["params"][0]["height"] == core.ruf("getblockcount")
        await c.meldung("blockchain.scripthash.subscribe")
        geschichte = await c.frag("blockchain.scripthash.get_history", skript)
        assert geschichte[-1] == {"tx_hash": txid,
                                  "height": core.ruf("getblockcount")}
    _mit_server(core, szenario, test)


def test_eine_abgelehnte_zahlung_kommt_mit_cores_begruendung_zurueck(
        core, szenario):
    async def test(c, _server):
        await c.frag("server.version", "BitBoxApp", "1.4")
        with pytest.raises(AssertionError) as fehler:
            await c.frag("blockchain.transaction.broadcast", "00" * 60)
        assert "decode" in str(fehler.value).lower()
    _mit_server(core, szenario, test)


def test_ueber_tls_genauso(core, szenario, tmp_path):
    async def test(c, _server):
        assert (await c.frag("server.version", "BitBoxApp", "1.4"))[1] == "1.4"
        skript = _skripte(core, szenario, bis=1)[0]
        assert await c.frag("blockchain.scripthash.get_history", skript)
    _mit_server(core, szenario, test, tls_verzeichnis=str(tmp_path))
