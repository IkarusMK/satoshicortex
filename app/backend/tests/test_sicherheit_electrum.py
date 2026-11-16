"""Sicherheit des Electrum-Dienstes: ein Port ohne Anmeldung, im Heimnetz und
ueber Tor erreichbar.

DER BEFUND VOM 16.11.2026: mit dem echten Server und einem nachgebildeten
Core gemessen. Eine Zeile von 9,4 KB (100 x blockchain.block.headers
[800000, 2016]) liess 400.000 Core-Aufrufe und eine Antwort von 32 MB
entstehen -- 185 MB Speicher fuer EINE Verbindung, bei vier ueber 300 MB
von 400 erlaubten. Dazu: kein Bremsklotz auf Core, jede Verbindung entwertete
den Bestand (16.340 volle Neulesungen in 5 s), die Annahmeschleife starb bei
EMFILE, unbegrenzt viele halboffene und leere Verbindungen, RecursionError,
unbegrenzte Abos, Log-Flut.

Alle Tests messen Mengen und Groessen, nichts wird real ausgereizt.
"""
import asyncio
import json
import logging
import re
import threading
from pathlib import Path

import pytest

from satcortex import electrum, electrumserver, kontobuch

VERSION = {"jsonrpc": "2.0", "id": 1, "method": "server.version",
           "params": ["test", "1.4"]}


class Core:
    def __init__(self, hoehe=100_000, tx_hex_laenge=0):
        self.hoehe = hoehe
        self.aufrufe = 0
        self.faeden = set()
        self.tx_hex_laenge = tx_hex_laenge

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        self.aufrufe += 1
        self.faeden.add(threading.current_thread().name)
        if methode == "getblockcount":
            return self.hoehe
        if methode == "getblockhash":
            return f"{params[0]:064x}"
        if methode == "getblockheader":
            return "ab" * 80
        if methode == "getrawtransaction":
            return "00" * (self.tx_hex_laenge // 2)
        raise AssertionError(methode)

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return [self.ruf(m, *p) for m, p in aufrufe]


class Bestand:
    def __init__(self):
        self.auffrischungen = 0

    def aktuell(self):
        return kontobuch.Buch([]), frozenset()

    def auffrischen(self):
        self.auffrischungen += 1

    def veraltet(self, mindestalter=0.0):
        pass


def _server(core=None, bestand=None, **kw):
    core = core or Core()
    bestand = bestand or Bestand()
    dienst = electrum.Dienst(core, bestand.aktuell, version="test")
    kw.setdefault("verzoegerung", 0.0)
    return electrumserver.ElectrumServer(
        dienst, bestand, tls=None, host="127.0.0.1", port=0, **kw), core


async def _verbinden(server):
    return await asyncio.open_connection("127.0.0.1", server.port,
                                           limit=64_000_000)


async def _frag_zeile(reader, writer, text: bytes, grenze=60_000_000):
    writer.write(text + b"\n")
    await writer.drain()
    return await asyncio.wait_for(reader.readline(), 20)


def _laeuft(szenario):
    asyncio.run(asyncio.wait_for(szenario(), 30))


def _kopf_buendel(n=100, start=0, anzahl=2016):
    return json.dumps([{"jsonrpc": "2.0", "id": i,
                        "method": "blockchain.block.headers",
                        "params": [start, anzahl]} for i in range(n)]).encode()


# ── 1. Speicher: ein kleines Buendel darf nicht Dutzende MB erzeugen ───────

def test_buendel_aus_kopfanfragen_teilt_sich_ein_kopfbudget():
    async def szenario():
        server, core = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            zeile = await _frag_zeile(r, w, _kopf_buendel())
            antworten = json.loads(zeile)
            geliefert = sum(a["result"]["count"] for a in antworten
                            if "result" in a)
            assert geliefert <= electrum.KOPF_BUDGET
            assert len(antworten) == 100        # jede Anfrage bekommt Antwort
            assert any("error" in a for a in antworten)
            # Core: je Kopf hoechstens ein Hash- und ein Kopf-Aufruf
            assert core.aufrufe <= 2 * electrum.KOPF_BUDGET + 10
            assert len(zeile) < 1_000_000  # 4032 Koepfe = 645 KB
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_einzelner_kopfauftrag_wird_weiter_voll_beantwortet():
    async def szenario():
        server, _core = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            zeile = await _frag_zeile(r, w, json.dumps(
                {"id": 1, "method": "blockchain.block.headers",
                 "params": [0, 2016]}).encode())
            assert json.loads(zeile)["result"]["count"] == 2016
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_erster_abgleich_mit_vielen_zeilen_bleibt_unbehelligt():
    """BitBoxApp: 27.000 Koepfe als 14 Zeilen zu je 2016 -- die Bremse darf
    dabei nie warten oder abweisen."""
    async def szenario():
        server, _core = _server(core=Core(hoehe=1_000_000))
        await server.starten()
        try:
            r, w = await _verbinden(server)
            for i in range(14):
                zeile = await _frag_zeile(r, w, json.dumps(
                    {"id": i, "method": "blockchain.block.headers",
                     "params": [i * 2016, 2016]}).encode())
                assert json.loads(zeile)["result"]["count"] == 2016
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_sparrow_holt_2000_transaktionen_ohne_einen_fehler():
    async def szenario():
        server, _core = _server(core=Core(tx_hex_laenge=600))
        await server.starten()
        try:
            r, w = await _verbinden(server)
            for z in range(20):
                antworten = json.loads(await _frag_zeile(r, w, json.dumps(
                    [{"id": i, "method": "blockchain.transaction.get",
                      "params": ["11" * 32]} for i in range(100)]).encode()))
                assert all("result" in a for a in antworten)
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_das_kopfbudget_gilt_je_zeile_nicht_je_verbindung():
    async def szenario():
        server, _core = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            for _ in range(2):
                zeile = await _frag_zeile(r, w, json.dumps(
                    {"id": 1, "method": "blockchain.block.headers",
                     "params": [0, 2016]}).encode())
                assert json.loads(zeile)["result"]["count"] == 2016
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_die_antwort_einer_zeile_hat_eine_obergrenze():
    """100 grosse Transaktionen in einer Zeile: ab der Obergrenze Fehler statt
    Antwort."""
    async def szenario():
        server, _core = _server(core=Core(tx_hex_laenge=100_000),
                                antwort_hoechstens=300_000)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            zeile = await _frag_zeile(r, w, json.dumps(
                [{"id": i, "method": "blockchain.transaction.get",
                  "params": ["11" * 32]} for i in range(100)]).encode())
            antworten = json.loads(zeile)
            assert len(antworten) == 100
            assert len(zeile) < 300_000 + 100_000 + 20_000
            assert sum("result" in a for a in antworten) >= 1
            assert sum("error" in a for a in antworten) >= 90
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 2. Core-Bremse und eigener Pool ────────────────────────────────────────

class Uhr:
    def __init__(self):
        self.jetzt = 1000.0

    def __call__(self):
        return self.jetzt


def test_der_eimer_gibt_nach_der_fuellung_nur_im_takt_frei():
    uhr = Uhr()
    eimer = electrumserver.Eimer(rate=10.0, fassung=20.0, uhr=uhr)
    assert eimer.entnehmen(20) == 0.0
    assert eimer.entnehmen(10) == pytest.approx(1.0)
    uhr.jetzt += 1.0
    assert eimer.entnehmen(0) == 0.0


def test_der_eimer_weist_zu_lange_wartezeiten_ab_ohne_zu_buchen():
    uhr = Uhr()
    eimer = electrumserver.Eimer(rate=1.0, fassung=1.0, uhr=uhr)
    assert eimer.entnehmen(1) == 0.0
    assert eimer.entnehmen(1000, hoechstens=5.0) is None
    assert eimer.entnehmen(3, hoechstens=5.0) == pytest.approx(3.0)


def test_core_befehle_kosten_scripthash_befehle_nicht():
    assert electrum.kosten("blockchain.scripthash.get_history", ["aa"]) == 0
    assert electrum.kosten("server.ping", []) == 0
    assert electrum.kosten("blockchain.transaction.get", ["x"]) >= 1
    assert electrum.kosten("blockchain.block.headers", [0, 2016]) > \
        electrum.kosten("blockchain.block.header", [0])
    assert electrum.kosten("blockchain.block.headers", "kaputt") >= 1


def test_zu_viele_core_anfragen_werden_mit_fehler_beantwortet():
    async def szenario():
        server, core = _server(core=Core(tx_hex_laenge=2),
                               core_rate=1.0, core_fassung=3.0,
                               core_wartezeit=0.0)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antworten = json.loads(await _frag_zeile(r, w, json.dumps(
                [{"id": i, "method": "blockchain.transaction.get",
                  "params": ["11" * 32]} for i in range(10)]).encode()))
            assert sum("result" in a for a in antworten) == 3
            assert sum("error" in a for a in antworten) == 7
            assert core.aufrufe == 3
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_der_dienst_hat_einen_eigenen_pool_nicht_den_der_anwendung():
    async def szenario():
        server, core = _server(core=Core(tx_hex_laenge=2))
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag_zeile(r, w, json.dumps(
                {"id": 1, "method": "blockchain.transaction.get",
                 "params": ["11" * 32]}).encode())
            assert core.faeden
            assert all(n.startswith("electrum") for n in core.faeden), \
                core.faeden
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 3. Verbindungen entwerten den Bestand nicht mehr im Sekundentakt ───────

class Leser:
    def __init__(self):
        self.gelesen = 0

    def lesen(self):
        self.gelesen += 1
        return kontobuch.Buch([]), frozenset()


def test_veraltet_mit_mindestalter_liest_nicht_erneut():
    uhr = Uhr()
    leser = Leser()
    b = electrumserver.Bestand(leser, uhr=uhr)
    b.aktuell()
    b.veraltet(10.0)
    b.aktuell()
    assert leser.gelesen == 1
    uhr.jetzt += 11
    b.veraltet(10.0)
    b.aktuell()
    assert leser.gelesen == 2


def test_veraltet_ohne_mindestalter_wirkt_sofort():
    """Eine Kontenaenderung darf nie warten."""
    leser = Leser()
    b = electrumserver.Bestand(leser, uhr=Uhr())
    b.aktuell()
    b.veraltet()
    b.aktuell()
    assert leser.gelesen == 2


def test_eine_verbindungsflut_loest_hoechstens_eine_neulesung_aus():
    async def szenario():
        leser = Leser()
        bestand = electrumserver.Bestand(leser)
        server, _core = _server(bestand=bestand, verbindungen_hoechstens=50)
        await server.starten()
        try:
            for _ in range(30):
                r, w = await _verbinden(server)
                await _frag_zeile(r, w, json.dumps(VERSION).encode())
                await _frag_zeile(r, w, json.dumps(
                    {"id": 2, "method": "blockchain.scripthash.get_balance",
                     "params": ["aa" * 32]}).encode())
                w.close()
            assert leser.gelesen <= 2
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 4. Annahme: Fehler, Zaehlung ab dem Annehmen ───────────────────────────

def test_die_annahme_ueberlebt_einen_fehler_beim_annehmen():
    async def szenario():
        loop = asyncio.get_running_loop()
        echt = loop.sock_accept
        faelle = {"n": 0}

        async def kaputt(sock):
            faelle["n"] += 1
            if faelle["n"] <= 2:
                raise OSError(24, "Too many open files")
            return await echt(sock)

        loop.sock_accept = kaputt
        server, _core = _server(annahme_pause=0.01)
        await server.starten()
        try:
            await asyncio.sleep(0.1)
            r, w = await _verbinden(server)
            assert json.loads(await _frag_zeile(
                r, w, json.dumps(VERSION).encode()))["result"]
            assert faelle["n"] >= 3
        finally:
            await server.beenden()
            del loop.sock_accept
    _laeuft(szenario)


def test_verbindungen_zaehlen_ab_dem_annehmen_nicht_erst_nach_dem_handschlag():
    async def szenario():
        server, _core = _server(verbindungen_hoechstens=2)
        await server.starten()
        try:
            stumm = [await _verbinden(server) for _ in range(2)]
            await asyncio.sleep(0.1)       # beide angenommen, nichts gesendet
            r3, _w3 = await _verbinden(server)
            assert await asyncio.wait_for(r3.read(), 2) == b""
            for _r, w in stumm:
                w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_freigewordener_platz_wird_wieder_vergeben():
    async def szenario():
        server, _core = _server(verbindungen_hoechstens=1)
        await server.starten()
        try:
            r1, w1 = await _verbinden(server)
            await _frag_zeile(r1, w1, json.dumps(VERSION).encode())
            w1.close()
            await asyncio.sleep(0.2)
            r2, w2 = await _verbinden(server)
            assert json.loads(await _frag_zeile(
                r2, w2, json.dumps(VERSION).encode()))["result"]
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 5. Leere Verbindungen halten keinen Platz ──────────────────────────────

def test_wer_keine_erste_zeile_schickt_wird_getrennt():
    async def szenario():
        server, _core = _server(vorlauf=0.3)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            w.write(b"{")
            await w.drain()
            assert await asyncio.wait_for(r.read(), 3) == b""
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_wer_nie_die_version_nennt_wird_getrennt():
    async def szenario():
        server, _core = _server(vorlauf=0.3)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            w.write(b'{"id":1,"method":"server.ping","params":[]}\n')
            await w.drain()
            await r.readline()
            assert await asyncio.wait_for(r.read(), 3) == b""
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_nach_der_version_gilt_wieder_der_lange_leerlauf():
    async def szenario():
        server, _core = _server(vorlauf=0.2)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag_zeile(r, w, json.dumps(VERSION).encode())
            await asyncio.sleep(0.5)
            assert json.loads(await _frag_zeile(
                r, w, b'{"id":2,"method":"server.ping","params":[]}'))["id"] == 2
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 6. Tief verschachteltes JSON ───────────────────────────────────────────

def test_tief_verschachteltes_json_ist_ein_parse_fehler_und_die_leitung_lebt():
    async def szenario():
        server, _core = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = json.loads(await _frag_zeile(r, w, b"[" * 900_000))
            assert antwort["error"]["code"] == -32700
            assert json.loads(await _frag_zeile(
                r, w, json.dumps(VERSION).encode()))["result"]
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── 7. Abos je Verbindung ──────────────────────────────────────────────────

def test_abos_je_verbindung_sind_begrenzt(monkeypatch):
    monkeypatch.setattr(electrum, "ABOS_HOECHSTENS", 3)
    dienst = electrum.Dienst(Core(), lambda: (kontobuch.Buch([]), frozenset()))
    s = electrum.Sitzung()
    for i in range(3):
        dienst.bearbeite(s, "blockchain.scripthash.subscribe",
                         [f"{i:064x}"])
    with pytest.raises(electrum.ElectrumFehler):
        dienst.bearbeite(s, "blockchain.scripthash.subscribe",
                         [f"{9:064x}"])
    # ein schon abonnierter Skripthash zaehlt nicht doppelt
    dienst.bearbeite(s, "blockchain.scripthash.subscribe", [f"{1:064x}"])
    # Abbestellen macht Platz
    dienst.bearbeite(s, "blockchain.scripthash.unsubscribe", [f"{1:064x}"])
    dienst.bearbeite(s, "blockchain.scripthash.subscribe", [f"{9:064x}"])
    assert len(s.abos) == 3


def test_die_abo_grenze_liegt_ueber_dem_was_wallets_brauchen():
    # Sparrow mit grossem Gap-Limit, BitBoxApp, Trezor Suite: wenige Tausend.
    assert electrum.ABOS_HOECHSTENS >= 20_000


# ── 8. Log-Flut ────────────────────────────────────────────────────────────

def test_gedrosseltes_log_meldet_je_fenster_einmal_und_zaehlt_den_rest():
    uhr = Uhr()
    ausgabe = []
    dr = electrumserver.Gedrosselt(lambda t, *a: ausgabe.append(t % a),
                                   fenster=60.0, uhr=uhr)
    for _ in range(50):
        dr("abgewiesen: %d", 1)
    assert len(ausgabe) == 1
    uhr.jetzt += 61
    dr("abgewiesen: %d", 1)
    assert len(ausgabe) == 2
    assert "49" in ausgabe[1]


def test_abgewiesene_verbindungen_fluten_das_protokoll_nicht(caplog):
    async def szenario():
        server, _core = _server(verbindungen_hoechstens=0)
        await server.starten()
        try:
            for _ in range(30):
                r, w = await _verbinden(server)
                await asyncio.wait_for(r.read(), 2)
                w.close()
        finally:
            await server.beenden()
    with caplog.at_level(logging.INFO, logger="satcortex.electrumserver"):
        _laeuft(szenario)
    zeilen = [x for x in caplog.records if "abgewiesen" in x.getMessage()]
    assert 1 <= len(zeilen) <= 2


# ── 9. Ehrlicher Text ──────────────────────────────────────────────────────

def _app_js():
    pfad = Path(__file__).resolve().parents[2] / "web" / "app.js"
    text = pfad.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*$", " ", text, flags=re.M)


def test_die_karte_sagt_dass_der_port_keine_anmeldung_hat():
    js = _app_js()
    lead = re.findall(r'el_lead:\s*"([^"]*)"', js)
    assert len(lead) == 2
    de, en = lead
    assert "ohne Anmeldung" in de and "Adresse" in de
    assert "without a login" in en and "address" in en
