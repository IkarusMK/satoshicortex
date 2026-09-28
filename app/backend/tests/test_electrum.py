"""Der Electrum-Dienst: jeder Befehl, den BitBoxApp und Trezor Suite schicken.

Die Befehlsliste stammt aus dem Quelltext beider Apps (28.09.2026): Trezor
Suite schickt 13 verschiedene, die BitBoxApp 11, zusammen rund 16. Die
Formate stammen aus der Spezifikation (spesmilo/electrum-protocol), fuer
Protokoll 1.4 -- das sprechen beide Apps fest, und genau das spricht auch
electrs, der Server hinter Umbrel, StartOS und RaspiBlitz.
"""
import hashlib

import pytest

from satcortex import electrum, kontobuch, rpc
from satcortex.kontobuch import Tx

EIGEN = "aa" * 32
FREMD = "ff" * 32
TX1 = "11" * 32
KOPF = "00" * 80


class Core:
    def __init__(self, **antworten):
        self.antworten = antworten
        self.aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        self.aufrufe.append((methode, params))
        antwort = self.antworten.get(methode)
        if callable(antwort):
            antwort = antwort(*params)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return [self.ruf(m, *p) for m, p in aufrufe]


def _kette(hoehe=10):
    """Eine Kette mit durchnummerierten Bloecken."""
    return dict(
        getblockcount=hoehe,
        getblockhash=lambda h: (_ for _ in ()).throw(
            rpc.RpcFehler("Block height out of range", -8))
        if h > hoehe else f"{h:064x}",
        getblockheader=lambda blockhash, ausfuehrlich=True:
            f"{int(blockhash, 16) % 256:02x}" * 80,   # 80 Byte, wie echt
    )


def _dienst(buch=None, eigene=frozenset({EIGEN}), **core):
    antworten = _kette()
    antworten.update(core)
    buch = buch or kontobuch.Buch([
        Tx(TX1, 7, 1, None, ((0, EIGEN, 5000),), ())])
    return electrum.Dienst(Core(**antworten), lambda: (buch, eigene),
                           version="1.4.0")


def _frag(dienst, methode, *params, sitzung=None):
    return dienst.bearbeite(sitzung or electrum.Sitzung(), methode,
                            list(params))


# ── Aushandlung ────────────────────────────────────────────────────────────

def test_die_version_wird_ausgehandelt():
    s = electrum.Sitzung()
    antwort = _dienst().bearbeite(s, "server.version", ["Trezor Suite", "1.4"])
    assert antwort == ["SatoshiCortex 1.4.0", "1.4"]
    assert s.version == "1.4"


def test_ein_bereich_wird_verstanden():
    antwort = _frag(_dienst(), "server.version", "Electrum", ["1.2", "1.4"])
    assert antwort[1] == "1.4"


def test_ohne_gemeinsame_version_wird_getrennt():
    """Spezifikation: gibt es keine gemeinsame Version, muss der Server
    die Verbindung schliessen."""
    s = electrum.Sitzung()
    with pytest.raises(electrum.ElectrumFehler):
        _dienst().bearbeite(s, "server.version", ["x", ["1.6", "1.7"]])
    assert s.schliessen


def test_nur_die_erste_versionsnachricht_gilt():
    s = electrum.Sitzung()
    d = _dienst()
    d.bearbeite(s, "server.version", ["x", "1.4"])
    with pytest.raises(electrum.ElectrumFehler):
        d.bearbeite(s, "server.version", ["x", "1.4"])


def test_die_merkmale_nennen_netz_und_version():
    m = _frag(_dienst(), "server.features")
    assert m["genesis_hash"] == f"{0:064x}"
    assert (m["protocol_min"], m["protocol_max"]) == ("1.4", "1.4")
    assert m["server_version"] == "SatoshiCortex 1.4.0"
    assert m["hash_function"] == "sha256"


def test_banner_ping_und_peers():
    d = _dienst()
    assert "SatoshiCortex" in _frag(d, "server.banner")
    assert _frag(d, "server.ping") is None
    assert _frag(d, "server.peers.subscribe") == []


def test_ein_unbekannter_befehl_ist_ein_sauberer_fehler():
    with pytest.raises(electrum.ElectrumFehler) as fehler:
        _frag(_dienst(), "blockchain.address.get_balance", "1abc")
    assert fehler.value.code == electrum.UNBEKANNT


# ── Kette ──────────────────────────────────────────────────────────────────

def test_der_kopf_der_kette_und_sein_abo():
    s = electrum.Sitzung()
    kopf = _dienst().bearbeite(s, "blockchain.headers.subscribe", [])
    assert kopf == {"height": 10, "hex": "0a" * 80}
    assert s.koepfe and s.letzter_kopf == kopf


def test_ein_einzelner_blockkopf():
    assert _frag(_dienst(), "blockchain.block.header", 5) == "05" * 80


def test_ein_pruefpunkt_beweis_wird_nicht_vorgetaeuscht():
    """cp_height verlangt einen Merkle-Beweis ueber alle Koepfe. Keine der
    beiden Apps fragt danach (Quelltext); statt etwas Halbes zu liefern,
    sagt der Server, dass er es nicht kann."""
    with pytest.raises(electrum.ElectrumFehler):
        _frag(_dienst(), "blockchain.block.header", 5, 8)


def test_ein_block_hinter_der_spitze_ist_ein_fehler():
    with pytest.raises(electrum.ElectrumFehler):
        _frag(_dienst(), "blockchain.block.header", 11)


def test_koepfe_im_block_als_ein_hexstring_wie_in_1_4():
    """Die BitBoxApp liest das Feld "hex" (block-client-go). "headers" als
    Liste kam erst mit 1.6."""
    antwort = _frag(_dienst(), "blockchain.block.headers", 8, 5)
    assert antwort == {"count": 3, "hex": "08" * 80 + "09" * 80 + "0a" * 80,
                       "max": 2016}


def test_mehr_als_das_hoechstmass_wird_gekuerzt():
    d = _dienst(**_kette(5000))
    antwort = _frag(d, "blockchain.block.headers", 0, 3000)
    assert antwort["count"] == 2016
    assert len(antwort["hex"]) == 2016 * 160


def test_ein_start_hinter_der_spitze_ergibt_nichts():
    assert _frag(_dienst(), "blockchain.block.headers", 20, 5) == {
        "count": 0, "hex": "", "max": 2016}


def test_die_gebuehrenschaetzung_kommt_von_core():
    d = _dienst(estimatesmartfee={"feerate": 0.00012, "blocks": 2})
    assert _frag(d, "blockchain.estimatefee", 2) == 0.00012


def test_ohne_schaetzung_gibt_es_minus_eins():
    """Wie an der Regtest-Kette gesehen: "Insufficient data or no feerate
    found". Die Spezifikation verlangt dann -1."""
    d = _dienst(estimatesmartfee={
        "errors": ["Insufficient data or no feerate found"], "blocks": 0})
    assert _frag(d, "blockchain.estimatefee", 2) == -1


def test_die_mindestgebuehr_fuer_die_weitergabe():
    d = _dienst(getnetworkinfo={"relayfee": 0.00001})
    assert _frag(d, "blockchain.relayfee") == 0.00001


# ── Transaktionen ──────────────────────────────────────────────────────────

def test_eine_transaktion_roh_und_ausfuehrlich():
    gefragt = []

    def roh(txid, stufe):
        gefragt.append(stufe)
        return "0200" if stufe == 0 else {"txid": txid}
    d = _dienst(getrawtransaction=roh)
    assert _frag(d, "blockchain.transaction.get", TX1) == "0200"
    assert _frag(d, "blockchain.transaction.get", TX1, True) == {"txid": TX1}
    assert gefragt == [0, 1]


@pytest.mark.parametrize("txid", ["", "zz" * 32, "11" * 31, 5, None])
def test_eine_unlesbare_kennung_wird_abgewiesen(txid):
    with pytest.raises(electrum.ElectrumFehler) as fehler:
        _frag(_dienst(), "blockchain.transaction.get", txid)
    assert fehler.value.code == electrum.UNGUELTIG


def test_senden_reicht_die_fertige_transaktion_an_core():
    d = _dienst(sendrawtransaction=lambda roh: TX1)
    assert _frag(d, "blockchain.transaction.broadcast", "0200aa") == TX1


def test_lehnt_core_ab_steht_seine_begruendung_im_fehler():
    d = _dienst(sendrawtransaction=rpc.RpcFehler(
        "{'code': -26, 'message': 'min relay fee not met'}", -26))
    with pytest.raises(electrum.ElectrumFehler) as fehler:
        _frag(d, "blockchain.transaction.broadcast", "0200aa")
    assert "min relay fee not met" in fehler.value.meldung


def _merkle_wurzel(txids):
    """Unabhaengig nachgebaut: die ganze Baumrechnung, nicht der Zweig."""
    ebene = [bytes.fromhex(t)[::-1] for t in txids]
    while len(ebene) > 1:
        if len(ebene) % 2:
            ebene.append(ebene[-1])
        ebene = [hashlib.sha256(hashlib.sha256(ebene[i] + ebene[i + 1])
                                .digest()).digest()
                 for i in range(0, len(ebene), 2)]
    return ebene[0][::-1].hex()


def _aus_zweig(txid, pos, zweig):
    h = bytes.fromhex(txid)[::-1]
    for nachbar in zweig:
        n = bytes.fromhex(nachbar)[::-1]
        h = hashlib.sha256(hashlib.sha256(
            n + h if pos & 1 else h + n).digest()).digest()
        pos >>= 1
    return h[::-1].hex()


@pytest.mark.parametrize("anzahl", [1, 2, 3, 5, 8, 13])
def test_der_merkle_zweig_fuehrt_zur_wurzel(anzahl):
    txids = [hashlib.sha256(bytes([i])).hexdigest() for i in range(anzahl)]
    wurzel = _merkle_wurzel(txids)
    for pos, txid in enumerate(txids):
        zweig = electrum.merkle_zweig(txids, pos)
        assert _aus_zweig(txid, pos, zweig) == wurzel


def test_get_merkle_nennt_hoehe_stelle_und_zweig():
    txids = [hashlib.sha256(bytes([i])).hexdigest() for i in range(3)]
    d = _dienst(getblock=lambda blockhash, stufe: {"tx": txids})
    antwort = _frag(d, "blockchain.transaction.get_merkle", txids[2], 7)
    assert antwort == {"block_height": 7, "pos": 2,
                       "merkle": electrum.merkle_zweig(txids, 2)}


def test_get_merkle_fuer_eine_transaktion_die_dort_nicht_steht():
    d = _dienst(getblock=lambda blockhash, stufe: {"tx": ["22" * 32]})
    with pytest.raises(electrum.ElectrumFehler):
        _frag(d, "blockchain.transaction.get_merkle", TX1, 7)


# ── Skripthashes ───────────────────────────────────────────────────────────

def test_ein_abo_liefert_den_status_und_merkt_ihn():
    s = electrum.Sitzung()
    d = _dienst()
    status = d.bearbeite(s, "blockchain.scripthash.subscribe", [EIGEN])
    assert status == hashlib.sha256(f"{TX1}:7:".encode()).hexdigest()
    assert s.abos == {EIGEN: status}


def test_abbestellen():
    s = electrum.Sitzung()
    d = _dienst()
    d.bearbeite(s, "blockchain.scripthash.subscribe", [EIGEN])
    assert d.bearbeite(s, "blockchain.scripthash.unsubscribe", [EIGEN]) is True
    assert d.bearbeite(s, "blockchain.scripthash.unsubscribe", [EIGEN]) is False


def test_die_eigene_geschichte_guthaben_und_ausgaenge():
    d = _dienst()
    assert _frag(d, "blockchain.scripthash.get_history", EIGEN) == [
        {"tx_hash": TX1, "height": 7}]
    assert _frag(d, "blockchain.scripthash.get_balance", EIGEN) == {
        "confirmed": 5000, "unconfirmed": 0}
    assert _frag(d, "blockchain.scripthash.listunspent", EIGEN) == [
        {"tx_hash": TX1, "tx_pos": 0, "height": 7, "value": 5000}]
    assert _frag(d, "blockchain.scripthash.get_mempool", EIGEN) == []


def test_ein_fremdes_skript_ist_leer_auch_wenn_es_im_buch_vorkommt():
    """Das Buch kennt auch fremde Skripte -- das Ziel einer Ausgabe etwa.
    Deren Geschichte kennen wir aber nur zum Teil; eine halbe Antwort waere
    falsch. Angemeldet ist, was uns gehoert, und nur das wird beantwortet."""
    buch = kontobuch.Buch([Tx(TX1, 7, 1, None, ((0, FREMD, 9),), ())])
    d = _dienst(buch=buch, eigene=frozenset())
    assert _frag(d, "blockchain.scripthash.subscribe", FREMD) is None
    assert _frag(d, "blockchain.scripthash.get_history", FREMD) == []
    assert _frag(d, "blockchain.scripthash.get_balance", FREMD) == {
        "confirmed": 0, "unconfirmed": 0}
    assert _frag(d, "blockchain.scripthash.listunspent", FREMD) == []


@pytest.mark.parametrize("skript", ["", "aa", "gg" * 32, None, 7, "AA" * 32 + "0"])
def test_ein_unlesbarer_skripthash_wird_abgewiesen(skript):
    with pytest.raises(electrum.ElectrumFehler) as fehler:
        _frag(_dienst(), "blockchain.scripthash.get_history", skript)
    assert fehler.value.code == electrum.UNGUELTIG


def test_grossbuchstaben_im_skripthash_werden_verstanden():
    assert _frag(_dienst(), "blockchain.scripthash.get_history",
                 EIGEN.upper()) == [{"tx_hash": TX1, "height": 7}]


# ── Was sich seit dem letzten Blick geaendert hat ─────────────────────────

def test_neuigkeiten_nennen_nur_was_sich_geaendert_hat():
    s = electrum.Sitzung()
    stand = {"buch": kontobuch.Buch([])}
    d = electrum.Dienst(Core(**_kette()), lambda: (stand["buch"],
                                                   frozenset({EIGEN})))
    d.bearbeite(s, "blockchain.headers.subscribe", [])
    d.bearbeite(s, "blockchain.scripthash.subscribe", [EIGEN])
    assert d.neuigkeiten(s) == []
    stand["buch"] = kontobuch.Buch([Tx(TX1, 0, 0, 100, ((0, EIGEN, 5),), ())])
    neu = d.neuigkeiten(s)
    assert neu == [("blockchain.scripthash.subscribe",
                    [EIGEN, stand["buch"].status(EIGEN)])]
    assert d.neuigkeiten(s) == []


def test_ein_neuer_block_wird_gemeldet():
    s = electrum.Sitzung()
    kette = _kette(10)
    core = Core(**kette)
    d = electrum.Dienst(core, lambda: (kontobuch.Buch([]), frozenset()))
    d.bearbeite(s, "blockchain.headers.subscribe", [])
    core.antworten.update(_kette(11))
    assert d.neuigkeiten(s) == [
        ("blockchain.headers.subscribe", [{"height": 11, "hex": "0b" * 80}])]


def test_ohne_abo_wird_nichts_gemeldet():
    s = electrum.Sitzung()
    core = Core(**_kette(10))
    d = electrum.Dienst(core, lambda: (kontobuch.Buch([]), frozenset()))
    core.antworten.update(_kette(11))
    assert d.neuigkeiten(s) == []
