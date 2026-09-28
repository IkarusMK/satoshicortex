"""Der Electrum-Server im Netz: echte Sockets auf 127.0.0.1.

Geprueft wird, was an der Leitung passiert -- Zeilen, Buendel, Fehler,
Benachrichtigungen, TLS und Klartext auf DEMSELBEN Port, Grenzen. Was die
Befehle antworten, pruefen die Tests des Dienstes (test_electrum.py).
"""
import asyncio
import json
import os
import ssl
import stat

import pytest

from satcortex import electrum, electrumserver, kontobuch


class Core:
    def __init__(self, hoehe=10):
        self.hoehe = hoehe

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        if methode == "getblockcount":
            return self.hoehe
        if methode == "getblockhash":
            return f"{params[0]:064x}"
        if methode == "getblockheader":
            return f"{int(params[0], 16) % 256:02x}" * 80
        raise AssertionError(methode)

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return [self.ruf(m, *p) for m, p in aufrufe]


class Bestand:
    """Ersetzt den echten Bestand -- zaehlt, wie oft aufgefrischt wird."""

    def __init__(self):
        self.auffrischungen = 0
        self.veraltet_gemeldet = 0

    def aktuell(self):
        return kontobuch.Buch([]), frozenset()

    def auffrischen(self):
        self.auffrischungen += 1

    def veraltet(self):
        self.veraltet_gemeldet += 1


def _server(tmp_path=None, core=None, **kw):
    core = core or Core()
    bestand = Bestand()
    dienst = electrum.Dienst(core, bestand.aktuell, version="test")
    tls = electrumserver.tls_kontext(str(tmp_path)) if tmp_path else None
    kw.setdefault("verzoegerung", 0.0)
    return electrumserver.ElectrumServer(dienst, bestand, tls=tls,
                                         host="127.0.0.1", port=0, **kw), core, bestand


async def _verbinden(server, tls_datei=None):
    kontext = None
    if tls_datei:
        kontext = ssl.create_default_context(cafile=tls_datei)
        kontext.check_hostname = False
    return await asyncio.open_connection("127.0.0.1", server.port, ssl=kontext)


async def _frag(reader, writer, nachricht):
    writer.write((json.dumps(nachricht) + "\n").encode())
    await writer.drain()
    return json.loads(await asyncio.wait_for(reader.readline(), 5))


def _laeuft(szenario):
    asyncio.run(asyncio.wait_for(szenario(), 20))


VERSION = {"jsonrpc": "2.0", "id": 1, "method": "server.version",
           "params": ["test", "1.4"]}


def test_eine_frage_eine_antwort_im_klartext():
    async def szenario():
        server, _c, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = await _frag(r, w, VERSION)
            assert antwort == {"jsonrpc": "2.0", "id": 1,
                               "result": ["SatoshiCortex test", "1.4"]}
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_buendel_bekommt_ein_buendel():
    async def szenario():
        server, _c, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = await _frag(r, w, [
                VERSION,
                {"jsonrpc": "2.0", "id": 2, "method": "server.ping",
                 "params": []}])
            assert sorted(a["id"] for a in antwort) == [1, 2]
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_unbekannter_befehl_ist_ein_json_rpc_fehler():
    async def szenario():
        server, _c, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = await _frag(r, w, {"jsonrpc": "2.0", "id": 7,
                                         "method": "gibts.nicht", "params": []})
            assert antwort["id"] == 7
            assert antwort["error"]["code"] == electrum.UNBEKANNT
            # Die Verbindung bleibt stehen.
            assert (await _frag(r, w, VERSION))["result"][1] == "1.4"
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_unlesbares_json_wird_beantwortet_nicht_verschluckt():
    async def szenario():
        server, _c, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            w.write(b"{kaputt\n")
            antwort = json.loads(await asyncio.wait_for(r.readline(), 5))
            assert antwort["error"]["code"] == -32700 and antwort["id"] is None
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ohne_gemeinsame_version_wird_getrennt():
    async def szenario():
        server, _c, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = await _frag(r, w, {"jsonrpc": "2.0", "id": 1,
                                         "method": "server.version",
                                         "params": ["x", ["1.6", "1.7"]]})
            assert "error" in antwort
            assert await asyncio.wait_for(r.read(), 5) == b""
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_tls_und_klartext_auf_demselben_port(tmp_path):
    """Die BitBoxApp kann beides, Trezor Suite auch. Ein Port reicht: am
    ersten Byte (0x16, TLS-Handschlag) ist zu erkennen, was kommt."""
    async def szenario():
        server, _c, _b = _server(tmp_path)
        await server.starten()
        try:
            r, w = await _verbinden(server, electrumserver.zertifikat_datei(
                str(tmp_path)))
            assert (await _frag(r, w, VERSION))["result"][1] == "1.4"
            w.close()
            r, w = await _verbinden(server)
            assert (await _frag(r, w, VERSION))["result"][1] == "1.4"
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_neuer_block_wird_von_selbst_gemeldet():
    async def szenario():
        server, core, bestand = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, {"jsonrpc": "2.0", "id": 1,
                               "method": "blockchain.headers.subscribe",
                               "params": []})
            core.hoehe = 11
            server.anstossen()
            meldung = json.loads(await asyncio.wait_for(r.readline(), 5))
            assert meldung == {"jsonrpc": "2.0",
                               "method": "blockchain.headers.subscribe",
                               "params": [{"height": 11, "hex": "0b" * 80}]}
            assert bestand.auffrischungen >= 1
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_anstossen_geht_auch_aus_einem_anderen_faden():
    """Der ZMQ-Zulauf ist ein Faden, kein Teil der Ereignisschleife."""
    async def szenario():
        server, core, _b = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, {"jsonrpc": "2.0", "id": 1,
                               "method": "blockchain.headers.subscribe",
                               "params": []})
            core.hoehe = 12
            await asyncio.to_thread(server.anstossen)
            meldung = json.loads(await asyncio.wait_for(r.readline(), 5))
            assert meldung["params"][0]["height"] == 12
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_eine_zu_lange_zeile_trennt_die_verbindung():
    async def szenario():
        server, _c, _b = _server(zeile_hoechstens=1024)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            w.write(b"x" * 5000 + b"\n")
            await w.drain()
            assert await asyncio.wait_for(r.read(), 5) == b""
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_mehr_verbindungen_als_erlaubt_werden_abgewiesen():
    async def szenario():
        server, _c, _b = _server(verbindungen_hoechstens=1)
        await server.starten()
        try:
            r1, w1 = await _verbinden(server)
            assert (await _frag(r1, w1, VERSION))["result"]
            r2, w2 = await _verbinden(server)
            assert await asyncio.wait_for(r2.read(), 5) == b""
            w1.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_zu_grosses_buendel_wird_abgewiesen():
    async def szenario():
        server, _c, _b = _server(buendel_hoechstens=3)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            antwort = await _frag(r, w, [
                {"jsonrpc": "2.0", "id": i, "method": "server.ping",
                 "params": []} for i in range(4)])
            assert antwort["error"]["code"] == -32600
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── Das Zertifikat ─────────────────────────────────────────────────────────

def test_das_zertifikat_entsteht_einmal_und_bleibt(tmp_path):
    electrumserver.tls_kontext(str(tmp_path))
    erster = electrumserver.fingerabdruck(str(tmp_path))
    electrumserver.tls_kontext(str(tmp_path))
    assert electrumserver.fingerabdruck(str(tmp_path)) == erster
    assert len(erster.replace(":", "")) == 64


def test_der_private_schluessel_ist_nur_fuer_den_eigentuemer(tmp_path):
    electrumserver.tls_kontext(str(tmp_path))
    modus = os.stat(electrumserver.schluessel_datei(str(tmp_path))).st_mode
    assert stat.S_IMODE(modus) == 0o600


def test_das_zertifikat_ist_lesbares_pem(tmp_path):
    electrumserver.tls_kontext(str(tmp_path))
    pem = electrumserver.zertifikat_pem(str(tmp_path))
    assert pem.startswith("-----BEGIN CERTIFICATE-----")
    assert "PRIVATE" not in pem


@pytest.mark.parametrize("anzahl", [1, 3])
def test_viele_anstoesse_kurz_hintereinander_ergeben_eine_auffrischung(anzahl):
    """Ein neuer Block bringt Dutzende Mempool-Meldungen mit -- das soll
    EINE Auffrischung ergeben, nicht Dutzende."""
    async def szenario():
        server, _c, bestand = _server(verzoegerung=0.2)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, VERSION)
            for _ in range(anzahl):
                server.anstossen()
            await asyncio.sleep(0.6)
            assert bestand.auffrischungen == 1
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ohne_verbundene_app_wird_nichts_aufgefrischt():
    """Niemand zu benachrichtigen, nichts zu tun -- sonst liefe Core bei
    jedem Block und jeder Mempool-Meldung fuer niemanden."""
    async def szenario():
        server, _c, bestand = _server()
        await server.starten()
        try:
            server.anstossen()
            server.anstossen(block=False)
            await asyncio.sleep(0.3)
            assert bestand.auffrischungen == 0
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_der_mempool_frischt_hoechstens_im_abstand_auf():
    """Auf dem echten Netz kommen mehrere Mempool-Meldungen je Sekunde."""
    async def szenario():
        server, _c, bestand = _server(mempool_abstand=0.6)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, VERSION)
            server.anstossen(block=False)
            await asyncio.sleep(0.15)
            assert bestand.auffrischungen == 1
            server.anstossen(block=False)
            await asyncio.sleep(0.15)
            assert bestand.auffrischungen == 1       # noch im Abstand
            await asyncio.sleep(0.7)
            assert bestand.auffrischungen == 2
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_ein_block_wartet_nicht_auf_den_mempool_abstand():
    async def szenario():
        server, _c, bestand = _server(mempool_abstand=5.0)
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, VERSION)
            server.anstossen(block=False)
            await asyncio.sleep(0.15)
            server.anstossen(block=True)
            await asyncio.sleep(0.15)
            assert bestand.auffrischungen == 2
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


def test_eine_neue_verbindung_bekommt_einen_frischen_stand():
    """Ohne verbundene App wird nicht aufgefrischt -- wer neu kommt, darf
    deshalb nicht den Stand von vor Stunden bekommen."""
    async def szenario():
        server, _c, bestand = _server()
        await server.starten()
        try:
            r, w = await _verbinden(server)
            await _frag(r, w, VERSION)
            assert bestand.veraltet_gemeldet == 1
            w.close()
        finally:
            await server.beenden()
    _laeuft(szenario)


# ── Der echte Bestand ──────────────────────────────────────────────────────

class Leser:
    def __init__(self):
        self.gelesen = 0
        self.kaputt = False

    def lesen(self):
        if self.kaputt:
            raise electrumserver.rpc.NichtErreichbar("weg")
        self.gelesen += 1
        return kontobuch.Buch([]), frozenset({str(self.gelesen)})


def test_der_bestand_liest_beim_ersten_mal_und_dann_nicht_wieder():
    leser = Leser()
    b = electrumserver.Bestand(leser)
    assert b.aktuell()[1] == {"1"}
    assert b.aktuell()[1] == {"1"}
    assert leser.gelesen == 1


def test_veraltet_heisst_beim_naechsten_mal_neu_lesen():
    leser = Leser()
    b = electrumserver.Bestand(leser)
    b.aktuell()
    b.veraltet()
    assert b.aktuell()[1] == {"2"}


def test_ist_core_weg_bleibt_der_alte_stand_stehen():
    """Lieber der Stand von eben als eine leere Wallet -- die saehe aus,
    als waere das Geld weg."""
    leser = Leser()
    b = electrumserver.Bestand(leser)
    b.aktuell()
    leser.kaputt = True
    b.auffrischen()
    b.veraltet()
    assert b.aktuell()[1] == {"1"}
