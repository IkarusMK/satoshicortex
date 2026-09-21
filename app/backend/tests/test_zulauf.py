"""Der ZMQ-Zulauf -- ohne ZMQ geprueft.

Die Nachrichten sind ein paar Bytes mit fester Form; sie lassen sich bauen.
Ein echter Broker daneben wuerde die Tests langsam und wackelig machen und
nichts zusaetzlich zeigen.
"""
import logging
import struct
import time

import pytest

from satcortex import rpc, store, zulauf

HASH_A = "aa" * 32
HASH_B = "bb" * 32


def nachricht(kennung_hex: str, art: str, folge=None, nummer: int = 0):
    """Eine sequence-Nachricht bauen, genau wie bitcoind sie sendet."""
    rumpf = bytes.fromhex(kennung_hex) + art.encode("ascii")
    if folge is not None:
        rumpf += struct.pack("<Q", folge)
    return [b"sequence", rumpf, struct.pack("<I", nummer)]


class Knoten(rpc.Knoten):
    def __init__(self, antworten=None):
        super().__init__()
        self.antworten = antworten or {}
        self.aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None):
        self.aufrufe.append(methode)
        wert = self.antworten.get(methode)
        if wert is None:
            raise rpc.NichtErreichbar("nicht gesetzt")
        return wert(*params) if callable(wert) else wert


@pytest.fixture
def z(tmp_path):
    ablage = store.Ablage(str(tmp_path / "a.db"))
    knoten = Knoten()
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://nirgends:1")
    lauf.knoten = knoten
    yield lauf
    ablage.schliesse()


def test_aufnahme_wird_mit_zeitstempel_festgehalten(z):
    z._eine_nachricht(nachricht(HASH_A, "A", folge=7, nummer=1))
    eintrag = z.ablage.eine_tx(HASH_A)
    assert eintrag is not None and eintrag["folge"] == 7
    assert eintrag["zuerst_ms"] > 0


def test_hashes_werden_nicht_noch_einmal_gedreht(z):
    """doc/zmq.md: die Hashes kommen BEREITS in umgekehrter Byte-Reihenfolge,
    also so, wie sie ueberall angezeigt werden. Sie erneut zu drehen ist der
    naheliegende Fehler -- dann waere jede txid falsch."""
    z._eine_nachricht(nachricht("01" + "00" * 31, "A", folge=1, nummer=1))
    assert z.ablage.eine_tx("01" + "00" * 31) is not None
    assert z.ablage.eine_tx("00" * 31 + "01") is None


def test_entfernen_wird_vermerkt(z):
    """ZMQ sagt nur "ohne Block entfernt", nicht warum. Bis zum 15.09.2026
    stand hier fest "verdraengt" -- auch fuer Abgelaufenes und wegen Platz
    Hinausgeworfenes."""
    z._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=1))
    z._eine_nachricht(nachricht(HASH_A, "R", folge=2, nummer=2))
    assert z.ablage.eine_tx(HASH_A)["grund"] == "ohne_block"


def test_eine_reorg_ist_kein_verlust(z):
    z._eine_nachricht(nachricht(HASH_A, "D", nummer=1))
    d = z.ablage.eckdaten()
    assert d["luecken_24h"] == 0 and d["reorgs_24h"] == 1


def test_luecke_im_zmq_strom_wird_festgehalten(z):
    """Verwirft ZMQ Nachrichten, fehlen uns Zeitstempel -- und jeder
    Durchschnitt daneben ist ab da geraten. Das gehoert vermerkt."""
    z._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=41))
    z._eine_nachricht(nachricht(HASH_B, "A", folge=2, nummer=43))   # 42 fehlt
    assert z.ablage.eckdaten()["luecken_24h"] == 1


def test_zaehlerueberlauf_ist_keine_luecke(z):
    """Die Nachrichtennummer ist 4 Byte breit und laeuft irgendwann ueber.
    Wer das nicht bedenkt, meldet an dieser Stelle eine Luecke, die keine
    ist."""
    z._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=2**32 - 1))
    z._eine_nachricht(nachricht(HASH_B, "A", folge=2, nummer=0))
    assert z.ablage.eckdaten()["luecken_24h"] == 0


def test_ein_sprung_in_der_mempoolfolge_ist_KEIN_verlust(z):
    """Der Fehlalarm, der des Betreibers Uebersicht am 08.09.2026 mit "6070
    verlorene Meldungen in 24 h" beschriftet hat.

    Core zaehlt die Mempool-Folgenummer bei JEDER Entfernung hoch, auch bei
    der, die keine Meldung ausloest. Woertlich aus src/txmempool.cpp
    (v31.1, removeUnchecked):

        // We increment mempool sequence value no matter removal reason
        // even if not directly reported below.

    Jede Transaktion, die in einen Block kommt, springt die Nummer also
    weiter, ohne dass etwas geschickt wird. Bei zweitausend Transaktionen je
    Block sind das tausende Spruenge am Tag -- und kein einziger davon ist
    ein Verlust. Die Zeitstempel sind alle da: vom A-Ereignis der Zeitpunkt,
    vom C-Ereignis der Block.
    """
    z._eine_nachricht(nachricht(HASH_A, "A", folge=10, nummer=1))
    z._eine_nachricht(nachricht(HASH_B, "A", folge=2014, nummer=2))
    assert z.ablage.eckdaten()["luecken_24h"] == 0, \
        "ein Sprung in der Mempoolfolge ist Cores Normalbetrieb"


def test_die_zmq_zaehlung_meldet_weiterhin_echten_verlust(z):
    """Die bleibt, denn sie ist genau dafuer gemacht: "message sequence
    number represents message count to detect lost messages" (doc/zmq.md).
    Sie ist je Thema fortlaufend und springt NICHT von allein."""
    z._eine_nachricht(nachricht(HASH_A, "A", folge=10, nummer=1))
    z._eine_nachricht(nachricht(HASH_B, "A", folge=2014, nummer=9))
    assert z.ablage.eckdaten()["luecken_24h"] == 1


def test_kurze_oder_fremde_nachrichten_kippen_nichts(z):
    z._eine_nachricht([b"hashblock", b"x" * 32, b"\0\0\0\0"])
    z._eine_nachricht([b"sequence", b"zu kurz", b"\0\0\0\0"])
    z._eine_nachricht([b"sequence"])
    assert z.ablage.eckdaten()["transaktionen"] == 0


def test_block_traegt_verweildauer_und_pool_ein(tmp_path):
    ablage = store.Ablage(str(tmp_path / "b.db"))
    knoten = Knoten({
        "getblock": {
            "height": 900000, "time": 1756000000, "weight": 3993000,
            "nTx": 3, "tx": ["cb" + "0" * 62, HASH_A, HASH_B],
            "coinbase_tx": {"coinbase": "0300000004deadbeef"},
        },
        "getblockstats": {"totalfee": 4200000},
        "getrawtransaction": {"vout": [
            {"scriptPubKey": {"address": "1PoolAdresse"}}]},
    })

    class Liste:
        def erkenne(self, coinbase_hex, adressen=None):
            return "Testpool" if "1PoolAdresse" in (adressen or []) else None

    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://x:1", poolliste=Liste())
    ablage.tx_aufgenommen(HASH_A, 1_000_000, 1)
    ablage.tx_aufgenommen(HASH_B, 1_002_000, 2)

    lauf._block("cc" * 32, 1_010_000)

    block = ablage.letzte_bloecke(1)[0]
    assert block["hoehe"] == 900000
    assert block["pool"] == "Testpool"
    assert block["gebuehren_sat"] == 4200000
    # Zwei der drei Transaktionen kannten wir; die Coinbase nie.
    assert block["bekannte_tx"] == 2
    assert block["verweildauer_ms"] == 9000        # Median aus 10000 und 8000
    ablage.schliesse()


def test_block_ohne_erreichbaren_knoten_bricht_nicht(z):
    z._block("cc" * 32, 1000)
    assert z.ablage.letzte_bloecke() == []


def test_ohne_poolliste_bleibt_die_spalte_leer(tmp_path):
    """Ein fehlendes Namensschild ist kein Grund, die Auswertung anzuhalten."""
    ablage = store.Ablage(str(tmp_path / "c.db"))
    knoten = Knoten({"getblock": {"height": 1, "time": 0, "weight": 0,
                                  "nTx": 0, "tx": [], "coinbase_tx": {}}})
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://x:1", poolliste=None)
    lauf._block("dd" * 32, 1000)
    assert ablage.letzte_bloecke(1)[0]["pool"] is None
    assert "getrawtransaction" not in knoten.aufrufe   # gar nicht erst gefragt
    ablage.schliesse()


def test_ohne_kontakt_gilt_erstabgleich(z):
    """Kein Kontakt heisst NICHT 'dann eben loslegen'. Blind zu starten waere
    im Zweifel der teure Fall: Hunderttausende Bloecke aufholen."""
    assert z._im_erstsync() is True


def test_schnappschuss_rechnet_die_verwerfungsgrenze_um(tmp_path):
    """mempoolminfee kommt in BTC je kvB -- mal 100.000 ergibt sat/vB. Wer das
    vergisst, zeigt 0,00001 statt 1."""
    ablage = store.Ablage(str(tmp_path / "d.db"))
    knoten = Knoten({"getmempoolinfo": {
        "size": 4210, "bytes": 2_100_000, "mempoolminfee": 0.00002}})
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://x:1")
    lauf._schnappschuss()
    punkt = ablage.mempool_verlauf(0)[-1]
    assert punkt["txzahl"] == 4210
    assert punkt["mindestgebuehr"] == 2.0
    ablage.schliesse()


# ═══════════════ Der Lebenslauf des Fadens ════════════════════════════════
#
# Bis zum 16.09.2026 war geprueft, was der Zulauf mit einer Nachricht MACHT --
# nicht aber, wie er anlaeuft, wartet, lauscht und wieder aufraeumt. Genau
# dort sitzt aber das Verhalten, auf das sich ein Knoten im Dauerbetrieb
# verlassen muss.

class FakeSteckdose:
    def __init__(self, nachrichten=None, laeuft=None):
        self.gesetzt = {}
        self.verbunden = None
        self.geschlossen = False
        self._nachrichten = list(nachrichten or [])
        self._laeuft = laeuft

    def setsockopt(self, name, wert):
        self.gesetzt[name] = wert

    def connect(self, adresse):
        self.verbunden = adresse

    def poll(self, ms):
        return bool(self._nachrichten)

    def recv_multipart(self):
        return self._nachrichten.pop(0)

    def close(self):
        self.geschlossen = True


class FakeZmq:
    """Nur die Handvoll Namen, die der Zulauf wirklich benutzt."""
    SUB = "sub"
    LINGER = "linger"
    SUBSCRIBE = "subscribe"
    RCVHWM = "rcvhwm"

    def __init__(self, steckdose):
        self.steckdose = steckdose
        aussen = self

        class Context:
            @staticmethod
            def instance():
                return aussen

        self.Context = Context

    def socket(self, art):
        self.art = art
        return self.steckdose


def test_beenden_setzt_das_ende(z):
    assert not z._ende.is_set()
    z.beende()
    assert z._ende.is_set()


def test_ohne_pyzmq_bleibt_die_auswertung_aus(z, monkeypatch, caplog):
    """Kein Absturz, sondern eine Meldung -- der Rest der Anwendung laeuft
    weiter, nur die Auswertung sammelt nichts."""
    import sys
    monkeypatch.setitem(sys.modules, "zmq", None)
    with caplog.at_level(logging.ERROR):
        z.run()
    assert any("pyzmq" in r.message for r in caplog.records)
    assert z.laeuft_mit is False


def test_im_erstabgleich_meldet_der_zulauf_genau_einmal(z, monkeypatch, caplog):
    """Auf dem Knoten im Betrieb waren das 120 gleiche Zeilen je Stunde -- und
    dazwischen gingen die zwei unter, die wirklich etwas meldeten."""
    import sys
    monkeypatch.setitem(sys.modules, "zmq", FakeZmq(FakeSteckdose()))
    monkeypatch.setattr(z, "_im_erstsync", lambda: True)
    runden = {"n": 0}

    def warte(_sekunden):
        runden["n"] += 1
        return runden["n"] >= 3          # beim dritten Mal ist Schluss
    monkeypatch.setattr(z._ende, "wait", warte)

    with caplog.at_level(logging.INFO):
        z.run()
    gemeldet = [r for r in caplog.records if "Erstabgleich" in r.message]
    assert len(gemeldet) == 1, [r.message for r in gemeldet]


def test_der_zulauf_haengt_sich_richtig_an_den_strom(z, monkeypatch):
    """Die drei Einstellungen sind keine Schoenheit: LINGER=0 haelt das
    Schliessen kurz, RCVHWM begrenzt den Puffer -- eine Luecke faellt auf,
    ein wachsender Puffer nicht."""
    steckdose = FakeSteckdose()
    zmq = FakeZmq(steckdose)
    monkeypatch.setattr(z, "_im_erstsync", lambda: False)
    z._ende.set()                      # eine Runde, dann Schluss
    z._lausche(zmq)

    assert steckdose.verbunden == z.adresse
    assert steckdose.gesetzt[zmq.LINGER] == 0
    assert steckdose.gesetzt[zmq.SUBSCRIBE] == zulauf.THEMA
    assert steckdose.gesetzt[zmq.RCVHWM] == 20000
    assert steckdose.geschlossen is True, "die Steckdose blieb offen"
    assert z.laeuft_mit is False


def test_eine_nachricht_aus_dem_strom_landet_in_der_ablage(z, monkeypatch):
    steckdose = FakeSteckdose([nachricht(HASH_A, "A", folge=5, nummer=1)])
    monkeypatch.setattr(z, "_im_erstsync", lambda: False)

    # Nach der ersten Runde ist Schluss -- sonst laeuft die Schleife ewig.
    echtes = z._zwischendurch
    def einmal():
        echtes()
        z._ende.set()
    monkeypatch.setattr(z, "_zwischendurch", einmal)

    z._lausche(FakeZmq(steckdose))
    assert z.ablage.eine_tx(HASH_A) is not None


def test_kehrt_der_knoten_in_den_abgleich_zurueck_pausiert_der_zulauf(
        z, monkeypatch, caplog):
    """Reindex oder grosse Reorg: dann gehoert der Zulauf wieder schlafen."""
    monkeypatch.setattr(z, "_im_erstsync", lambda: True)
    z._zuletzt_schnappschuss = time.time()
    with caplog.at_level(logging.INFO):
        z._lausche(FakeZmq(FakeSteckdose()))
    assert any("pausiert" in r.message for r in caplog.records)


# ── Nebenher: sichern und Schnappschuss ───────────────────────────────────

def test_ein_volles_buendel_wird_weggeschrieben(z, monkeypatch):
    z._offen = zulauf.BUENDEL
    gesichert = []
    monkeypatch.setattr(z.ablage, "sichern", lambda: gesichert.append(1))
    z._zwischendurch()
    assert gesichert and z._offen == 0


def test_offene_zeilen_werden_auch_nach_zeit_weggeschrieben(z, monkeypatch):
    z._offen = 1
    z._zuletzt_gesichert = time.time() - zulauf.BUENDEL_SEKUNDEN - 1
    gesichert = []
    monkeypatch.setattr(z.ablage, "sichern", lambda: gesichert.append(1))
    z._zwischendurch()
    assert gesichert, "eine einzelne offene Zeile blieb liegen"


def test_ohne_offene_zeilen_wird_nicht_gesichert(z, monkeypatch):
    gesichert = []
    monkeypatch.setattr(z.ablage, "sichern", lambda: gesichert.append(1))
    z._zuletzt_schnappschuss = time.time()
    z._zwischendurch()
    assert not gesichert


def test_ein_nicht_erreichbarer_knoten_kippt_den_schnappschuss_nicht(z):
    z._schnappschuss()          # der Knoten der Fixture antwortet auf nichts


def test_eine_unlesbare_mempoolgrenze_wird_zu_null(tmp_path):
    """float("viel") waere ein Absturz mitten im Hintergrundfaden."""
    ablage = store.Ablage(str(tmp_path / "b.db"))
    knoten = Knoten({"getmempoolinfo": {"size": 3, "bytes": 900,
                                        "mempoolminfee": "viel"}})
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://nirgends:1")
    lauf._schnappschuss()
    assert ablage.mempool_verlauf(1)[0]["mindestgebuehr"] == 0.0
    ablage.schliesse()


def test_ein_fehlendes_feerate_diagramm_meldet_sich_nur_einmal(tmp_path, caplog):
    """Erst ab Core 31 vorhanden. Einmal melden, nicht jede Minute."""
    ablage = store.Ablage(str(tmp_path / "c.db"))
    knoten = Knoten({"getmempoolinfo": {"size": 1, "bytes": 1,
                                        "mempoolminfee": 0.00001}})
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://nirgends:1")
    with caplog.at_level(logging.WARNING):
        lauf._schnappschuss()
        lauf._schnappschuss()
    gemeldet = [r for r in caplog.records if "Diagramm" in r.message]
    assert len(gemeldet) == 1, [r.message for r in gemeldet]
    ablage.schliesse()
