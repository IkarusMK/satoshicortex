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


def _melden(lauf, teile):
    """Eine Meldung verarbeiten UND schreiben.

    Seit dem 26.09.2026 sammelt der Zulauf im Speicher und schreibt
    gebuendelt. Wer gleich danach in der Ablage nachsieht, muss vorher
    schreiben lassen -- sonst waere ein "0 Luecken" hier auch dann gruen,
    wenn der Zulauf gar nichts geschrieben haette.
    """
    lauf._eine_nachricht(teile)
    assert lauf._sichern(trotz_pause=True), "die Ablage nahm nichts an"


@pytest.fixture
def z(tmp_path):
    ablage = store.Ablage(str(tmp_path / "a.db"))
    knoten = Knoten()
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://nirgends:1")
    lauf.knoten = knoten
    yield lauf
    ablage.schliesse()


def test_aufnahme_wird_mit_zeitstempel_festgehalten(z):
    _melden(z, nachricht(HASH_A, "A", folge=7, nummer=1))
    eintrag = z.ablage.eine_tx(HASH_A)
    assert eintrag is not None and eintrag["folge"] == 7
    assert eintrag["zuerst_ms"] > 0


def test_hashes_werden_nicht_noch_einmal_gedreht(z):
    """doc/zmq.md: die Hashes kommen BEREITS in umgekehrter Byte-Reihenfolge,
    also so, wie sie ueberall angezeigt werden. Sie erneut zu drehen ist der
    naheliegende Fehler -- dann waere jede txid falsch."""
    _melden(z, nachricht("01" + "00" * 31, "A", folge=1, nummer=1))
    assert z.ablage.eine_tx("01" + "00" * 31) is not None
    assert z.ablage.eine_tx("00" * 31 + "01") is None


def test_entfernen_wird_vermerkt(z):
    """ZMQ sagt nur "ohne Block entfernt", nicht warum. Bis zum 15.09.2026
    stand hier fest "verdraengt" -- auch fuer Abgelaufenes und wegen Platz
    Hinausgeworfenes."""
    _melden(z, nachricht(HASH_A, "A", folge=1, nummer=1))
    _melden(z, nachricht(HASH_A, "R", folge=2, nummer=2))
    assert z.ablage.eine_tx(HASH_A)["grund"] == "ohne_block"


def test_eine_reorg_ist_kein_verlust(z):
    _melden(z, nachricht(HASH_A, "D", nummer=1))
    d = z.ablage.eckdaten()
    assert d["luecken_24h"] == 0 and d["reorgs_24h"] == 1


def test_luecke_im_zmq_strom_wird_festgehalten(z):
    """Verwirft ZMQ Nachrichten, fehlen uns Zeitstempel -- und jeder
    Durchschnitt daneben ist ab da geraten. Das gehoert vermerkt."""
    _melden(z, nachricht(HASH_A, "A", folge=1, nummer=41))
    _melden(z, nachricht(HASH_B, "A", folge=2, nummer=43))   # 42 fehlt
    assert z.ablage.eckdaten()["luecken_24h"] == 1


def test_zaehlerueberlauf_ist_keine_luecke(z):
    """Die Nachrichtennummer ist 4 Byte breit und laeuft irgendwann ueber.
    Wer das nicht bedenkt, meldet an dieser Stelle eine Luecke, die keine
    ist."""
    _melden(z, nachricht(HASH_A, "A", folge=1, nummer=2**32 - 1))
    _melden(z, nachricht(HASH_B, "A", folge=2, nummer=0))
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
    _melden(z, nachricht(HASH_A, "A", folge=10, nummer=1))
    _melden(z, nachricht(HASH_B, "A", folge=2014, nummer=2))
    assert z.ablage.eckdaten()["luecken_24h"] == 0, \
        "ein Sprung in der Mempoolfolge ist Cores Normalbetrieb"


def test_die_zmq_zaehlung_meldet_weiterhin_echten_verlust(z):
    """Die bleibt, denn sie ist genau dafuer gemacht: "message sequence
    number represents message count to detect lost messages" (doc/zmq.md).
    Sie ist je Thema fortlaufend und springt NICHT von allein."""
    _melden(z, nachricht(HASH_A, "A", folge=10, nummer=1))
    _melden(z, nachricht(HASH_B, "A", folge=2014, nummer=9))
    assert z.ablage.eckdaten()["luecken_24h"] == 1


def test_kurze_oder_fremde_nachrichten_kippen_nichts(z):
    _melden(z, [b"hashblock", b"x" * 32, b"\0\0\0\0"])
    _melden(z, [b"sequence", b"zu kurz", b"\0\0\0\0"])
    _melden(z, [b"sequence"])
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
    """Reindex oder grosse Reorg: dann gehoert der Zulauf wieder schlafen --
    auf ein klares Ja von bitcoind, nicht auf ein Schweigen."""
    monkeypatch.setattr(zulauf, "ABGLEICH_PRUEFEN_SEKUNDEN", 0)
    z.knoten.antworten["getblockchaininfo"] = {"initialblockdownload": True}
    z._zuletzt_schnappschuss = time.time()
    with caplog.at_level(logging.INFO):
        z._lausche(FakeZmq(FakeSteckdose()))
    assert any("pausiert" in r.message for r in caplog.records)


# ── Nebenher: sichern und Schnappschuss ───────────────────────────────────

def test_ein_volles_buendel_wird_weggeschrieben(z):
    z._zuletzt_gesichert = time.time()          # die Zeit ist es nicht
    z._zuletzt_schnappschuss = time.time()
    for i in range(zulauf.BUENDEL):
        z._eine_nachricht(nachricht(f"{i:064x}", "A", folge=i, nummer=i))
    z._zwischendurch()
    assert z._stapel == []
    assert z.ablage.eckdaten()["transaktionen"] == zulauf.BUENDEL


def test_offene_zeilen_werden_auch_nach_zeit_weggeschrieben(z):
    z._zuletzt_schnappschuss = time.time()
    z._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=1))
    z._zuletzt_gesichert = time.time() - zulauf.BUENDEL_SEKUNDEN - 1
    z._zwischendurch()
    assert z.ablage.eine_tx(HASH_A) is not None, \
        "eine einzelne offene Zeile blieb liegen"


def test_ohne_offene_zeilen_wird_nicht_gesichert(z, monkeypatch):
    gesichert = []
    monkeypatch.setattr(z.ablage, "ereignisse",
                        lambda liste: gesichert.append(liste) or [])
    z._zuletzt_schnappschuss = time.time()
    z._zuletzt_gesichert = 0
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


# ═══════════════ Die Ablage frei halten (Befund 26.09.2026) ═══════════════
#
# Aus dem Betrieb, 26.09.2026, zwei Zeilen kurz hintereinander:
#
#     sqlite3.OperationalError: database is locked
#     Luecke im zmq-Strom: erwartet ..., bekommen ...
#
# Beide hatten dieselbe Wurzel im Zulauf. Er fragte bei JEDER Meldung aus dem
# Strom den Knoten, ob er wieder im Abgleich ist -- ueber rpc.kettenlage(),
# also fuenf Aufrufe, darunter getblockchaininfo, das auf cs_main wartet.
# Waehrend eines Blocks sind das bis zu fuenfzehn Sekunden. Und das alles mit
# offener Schreibtransaktion: die Zeilen der letzten zwei Sekunden waren
# eingetragen, aber noch nicht gesichert. Jeder andere Schreibende wartete
# zwanzig Sekunden und gab auf. Riss dem Zulauf selbst die Geduld, hielt er
# das fuer "wieder im Abgleich", legte die Steckdose weg, verband sich neu --
# und alles, was dazwischen kam, war verloren.

import sqlite3                                            # noqa: E402


class Pruefknoten(Knoten):
    """Sieht bei JEDEM Aufruf nach, ob ein anderer jetzt schreiben koennte.

    Ein Aufruf an den Knoten kann Sekunden dauern. Waehrenddessen darf der
    Zulauf niemandem die Ablage versperren.
    """

    def __init__(self, pfad, antworten=None):
        super().__init__(antworten)
        self.pfad = str(pfad)
        self.gesperrt = []

    def ruf(self, methode, *params, zeitlimit=None):
        fremd = sqlite3.connect(self.pfad, timeout=0.2)
        try:
            fremd.execute("BEGIN IMMEDIATE")
            fremd.rollback()
        except sqlite3.OperationalError:
            self.gesperrt.append(methode)
        finally:
            fremd.close()
        return super().ruf(methode, *params, zeitlimit=zeitlimit)


BLOCK_ANTWORTEN = {
    "getblockchaininfo": {"initialblockdownload": False, "blocks": 900000,
                          "headers": 900000, "verificationprogress": 1.0},
    "getmempoolinfo": {"size": 2, "bytes": 500, "mempoolminfee": 0.00001},
    "getblock": {"height": 900000, "time": 1756000000, "weight": 4000,
                 "nTx": 2, "tx": ["cb" + "0" * 62, HASH_A],
                 "coinbase_tx": {"coinbase": "03a0bb0d"}},
    "getblockstats": {"totalfee": 1000},
}


def _bis_der_strom_leer_ist(lauf, steckdose, monkeypatch):
    """Die Schleife endet sonst nie -- sie wartet ja auf die naechste Meldung."""
    echtes = lauf._zwischendurch

    def dann_schluss():
        echtes()
        if not steckdose._nachrichten:
            lauf._ende.set()
    monkeypatch.setattr(lauf, "_zwischendurch", dann_schluss)


def test_waehrend_der_zulauf_den_knoten_fragt_ist_die_ablage_frei(
        tmp_path, monkeypatch):
    monkeypatch.setattr(zulauf, "ABGLEICH_PRUEFEN_SEKUNDEN", 0, raising=False)
    pfad = tmp_path / "a.db"
    ablage = store.Ablage(str(pfad))
    knoten = Pruefknoten(pfad, BLOCK_ANTWORTEN)
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://x:1")
    steckdose = FakeSteckdose([
        nachricht(HASH_A, "A", folge=1, nummer=1),
        nachricht(HASH_B, "A", folge=2, nummer=2),
        nachricht("cc" * 32, "C", nummer=3),
        nachricht("dd" * 32, "A", folge=3, nummer=4),
    ])
    _bis_der_strom_leer_ist(lauf, steckdose, monkeypatch)

    lauf._lausche(FakeZmq(steckdose))

    assert knoten.aufrufe, "der Knoten wurde nie gefragt -- Test prueft nichts"
    assert not knoten.gesperrt, (
        "waehrend dieser Aufrufe war die Ablage fuer alle anderen gesperrt: "
        + repr(knoten.gesperrt))
    # Und angekommen ist trotzdem alles.
    assert ablage.eine_tx(HASH_A)["hoehe"] == 900000
    assert ablage.eine_tx("dd" * 32) is not None
    assert ablage.letzte_bloecke(1)[0]["bekannte_tx"] == 1
    ablage.schliesse()


def test_der_zulauf_fragt_nicht_bei_jeder_meldung_nach_dem_abgleich(
        tmp_path, monkeypatch):
    """Bei einem vollen Mempool kommen Dutzende Meldungen je Sekunde. Je
    Meldung fuenf Aufrufe waren eine Last, die der Knoten nicht braucht --
    und die den Zulauf selbst so ausbremste, dass er hinterherhinkte."""
    ablage = store.Ablage(str(tmp_path / "a.db"))
    knoten = Knoten(BLOCK_ANTWORTEN)
    lauf = zulauf.Zulauf(ablage, lambda: knoten, "tcp://x:1")
    steckdose = FakeSteckdose([
        nachricht(f"{i:064x}", "A", folge=i, nummer=i) for i in range(1, 31)])
    _bis_der_strom_leer_ist(lauf, steckdose, monkeypatch)

    lauf._lausche(FakeZmq(steckdose))

    gefragt = knoten.aufrufe.count("getblockchaininfo")
    assert gefragt <= 1, f"{gefragt} Mal nach dem Abgleich gefragt bei 30 Meldungen"
    assert ablage.eckdaten()["transaktionen"] == 30
    ablage.schliesse()


def test_ein_kurzer_aussetzer_beim_abgleich_legt_den_zulauf_nicht_schlafen(
        z, monkeypatch, caplog):
    """Keine Antwort heisst "weiss nicht", nicht "wieder im Abgleich". Wer
    darauf die Steckdose weglegt, verliert alles, was bis zum Wiederverbinden
    kommt -- genau die Luecke vom 26.09.2026."""
    monkeypatch.setattr(zulauf, "ABGLEICH_PRUEFEN_SEKUNDEN", 0, raising=False)
    steckdose = FakeSteckdose([nachricht(HASH_A, "A", folge=1, nummer=1)])
    _bis_der_strom_leer_ist(z, steckdose, monkeypatch)
    with caplog.at_level(logging.INFO):
        z._lausche(FakeZmq(steckdose))       # der Knoten antwortet auf nichts
    assert not any("pausiert" in r.message for r in caplog.records)
    assert z.ablage.eine_tx(HASH_A) is not None


def test_eine_gesperrte_ablage_verliert_keine_meldung(tmp_path, monkeypatch):
    """Haelt ein anderer die Sperre, wartet das Gesammelte und wird spaeter
    geschrieben -- mit dem Zeitpunkt, zu dem es ankam, nicht dem des
    Schreibens. Vorher flog der Fehler aus dem Faden, und der Zulauf war
    tot, bis jemand die Anwendung neu startete."""
    monkeypatch.setattr(store, "WARTEN_AUF_SPERRE_SEKUNDEN", 0.2,
                        raising=False)
    monkeypatch.setattr(zulauf, "NEUER_VERSUCH_SEKUNDEN", 0, raising=False)
    pfad = tmp_path / "a.db"
    ablage = store.Ablage(str(pfad))
    lauf = zulauf.Zulauf(ablage, lambda: Knoten(), "tcp://x:1")
    lauf._zuletzt_schnappschuss = time.time()          # kein Schnappschuss
    fremd = sqlite3.connect(str(pfad), timeout=0.2)
    fremd.execute("BEGIN IMMEDIATE")

    lauf._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=1))
    angekommen = ablage.eine_tx(HASH_A)
    lauf._zuletzt_gesichert = 0
    lauf._zwischendurch()                              # scheitert, bleibt liegen

    fremd.rollback()
    fremd.close()
    lauf._zuletzt_gesichert = 0
    lauf._zwischendurch()                              # jetzt geht es

    assert angekommen is None
    tx = ablage.eine_tx(HASH_A)
    assert tx is not None, "die Meldung ging verloren"
    assert time.time() * 1000 - tx["zuerst_ms"] < 60_000
    ablage.schliesse()


def test_ein_ueberlaufender_stapel_wird_als_luecke_vermerkt(
        tmp_path, monkeypatch):
    """Nimmt die Ablage lange nichts an -- Platte voll, Datei kaputt --, darf
    der Zulauf den Speicher nicht volllaufen lassen. Was er wegwerfen muss,
    steht danach als Luecke da, statt still zu fehlen."""
    monkeypatch.setattr(zulauf, "STAPEL_HOECHSTENS", 5, raising=False)
    monkeypatch.setattr(zulauf, "NEUER_VERSUCH_SEKUNDEN", 0, raising=False)
    ablage = store.Ablage(str(tmp_path / "a.db"))
    lauf = zulauf.Zulauf(ablage, lambda: Knoten(), "tcp://x:1")
    lauf._zuletzt_schnappschuss = time.time()
    echtes = ablage.ereignisse
    gesperrt = {"ja": True}

    def vielleicht(liste):
        if gesperrt["ja"]:
            raise sqlite3.OperationalError("database is locked")
        return echtes(liste)
    monkeypatch.setattr(ablage, "ereignisse", vielleicht)

    for i in range(1, 13):
        lauf._eine_nachricht(nachricht(f"{i:064x}", "A", folge=i, nummer=i))
        lauf._zuletzt_gesichert = 0
        lauf._zwischendurch()
    gesperrt["ja"] = False
    lauf._zuletzt_gesichert = 0
    lauf._zwischendurch()

    assert ablage.eckdaten()["luecken_24h"] == 1
    assert ablage.eine_tx(f"{12:064x}") is not None, "das Neueste fehlt"
    assert ablage.eine_tx(f"{1:064x}") is None
    ablage.schliesse()


def test_ein_unerwarteter_fehler_beendet_den_zulauf_nicht(z, monkeypatch,
                                                            caplog):
    """Der Zulauf laeuft nicht unter dem Auffangbuegel der anderen
    Hintergrundfaeden. Eine Ausnahme hiess bisher: Faden tot, Auswertung
    steht still, und niemand startet ihn wieder."""
    import sys
    monkeypatch.setitem(sys.modules, "zmq", FakeZmq(FakeSteckdose()))
    monkeypatch.setattr(z, "_im_erstsync", lambda: False)
    monkeypatch.setattr(z._ende, "wait", lambda _s: False)
    anlaeufe = []

    def lausche(_zmq):
        anlaeufe.append(1)
        if len(anlaeufe) == 1:
            raise RuntimeError("etwas Unvorhergesehenes")
        z._ende.set()
    monkeypatch.setattr(z, "_lausche", lausche)

    with caplog.at_level(logging.ERROR):
        z.run()
    assert len(anlaeufe) == 2, "nach dem Fehler kam kein neuer Anlauf"
    assert any("Zulauf" in r.message for r in caplog.records)


def test_ein_unlesbares_buendel_blockiert_nicht_alles_danach(
        tmp_path, monkeypatch, caplog):
    """Scheitert das Schreiben NICHT an der Sperre, sondern an einem Fehler
    im Gesammelten, hilft kein zweiter Versuch -- derselbe Stapel scheiterte
    sonst bei jedem Anlauf wieder, und es wuerde nie mehr etwas geschrieben.
    Er wird verworfen, als Luecke vermerkt und gemeldet."""
    ablage = store.Ablage(str(tmp_path / "a.db"))
    lauf = zulauf.Zulauf(ablage, lambda: Knoten(), "tcp://x:1")
    lauf._zuletzt_schnappschuss = time.time()
    lauf._stapel.append(("?", "kaputt"))
    lauf._eine_nachricht(nachricht(HASH_A, "A", folge=1, nummer=1))
    with caplog.at_level(logging.ERROR):
        assert lauf._sichern() is False
    assert any("verworfen" in r.message for r in caplog.records)

    lauf._eine_nachricht(nachricht(HASH_B, "A", folge=2, nummer=2))
    assert lauf._sichern() is True
    assert ablage.eine_tx(HASH_B) is not None, "danach kam nichts mehr an"
    assert ablage.eckdaten()["luecken_24h"] == 1
    ablage.schliesse()
