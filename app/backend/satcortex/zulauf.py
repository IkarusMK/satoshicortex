"""Der Strom der Ereignisse aus bitcoind -- die Quelle der Auswertung.

bitcoind meldet ueber ZMQ jede Aufnahme in den Mempool, jedes Entfernen und
jeden Block. Daraus entsteht die eine Zahl, die kein Explorer liefern kann:
wann DIESER Knoten eine Transaktion zum ersten Mal gesehen hat.

Format (nachgelesen in doc/zmq.md von Core 31.1, nicht aus dem Gedaechtnis):

    Teil 1  b"sequence"
    Teil 2  32 Byte Hash  +  1 Byte Kennbuchstabe  [+ 8 Byte LE Mempool-Folge]
    Teil 3  4 Byte LE -- fortlaufende Nachrichtennummer, je Thema eigen

    A  Transaktion in den Mempool aufgenommen   (mit Mempool-Folge)
    R  Transaktion ohne Block wieder entfernt   (mit Mempool-Folge)
    C  Block verbunden                          (ohne)
    D  Block getrennt                           (ohne)

Die Hashes kommen bereits in UMGEKEHRTER Byte-Reihenfolge, also so, wie sie
ueberall angezeigt werden. Sie noch einmal zu drehen waere der naheliegende
Fehler -- dann waere jede txid falsch.

ZWEI Zaehler, zwei verschiedene Luecken:

  * Die Nachrichtennummer in Teil 3 zeigt, ob ZMQ etwas verworfen hat -- das
    passiert, wenn wir zu langsam lesen.
  * Die Mempool-Folge in Teil 2 zeigt, ob bitcoind selbst Ereignisse hatte,
    die wir nie gesehen haben.

Beide werden mitgefuehrt und jede Luecke festgehalten. Ohne das waeren alle
Durchschnitte daneben stille Behauptungen: fehlt ein Zeitstempel, ist die
Verweildauer daneben falsch, und niemand koennte es merken.

WAEHREND DES ERSTABGLEICHS BLEIBT DER ZULAUF STILL. Dafuer gibt es zwei
Gruende, und beide sind zwingend:

  1. bitcoind nimmt waehrend des Abgleichs keine Transaktionen in den Mempool.
     Es gaebe also gar nichts zu messen.
  2. Es meldet aber jeden einzelnen der Hunderttausenden aufzuholenden Bloecke
     als C. Jeder davon wuerde drei RPC-Aufrufe und Tausende Datenbankzeilen
     ausloesen -- auf einem NAS waere das nicht nur nutzlos, sondern
     schaedlich: es wuerde den Abgleich, auf den man ohnehin wartet, weiter
     ausbremsen.

Ein First-Seen-Zeitstempel fuer einen Block aus dem Jahr 2018 waere ohnehin
eine Luege. Die Geschichte faengt an, wenn die Kette steht.
"""
from __future__ import annotations

import logging
import struct
import threading
import time
from typing import Dict, List, Optional

from . import rpc

log = logging.getLogger(__name__)

THEMA = b"sequence"

# Wie lange auf eine Nachricht gewartet wird, bevor der Faden einmal Luft holt
# (Abbruch pruefen, Mempool-Schnappschuss, Aufraeumen).
WARTEN_MS = 1000

# Wie oft der Mempool als Ganzes festgehalten wird. Haeufiger brachte nichts:
# die Kurve bewegt sich in Minuten, nicht in Sekunden.
SCHNAPPSCHUSS_SEKUNDEN = 60

# Wie oft nachgesehen wird, ob der Erstabgleich vorbei ist.
WARTELAUF_SEKUNDEN = 30

# Nach so vielen Ereignissen wird geschrieben. Jede Zeile einzeln zu sichern
# hiesse bei jedem Block Tausende fsync -- das haelt keine Platte aus.
BUENDEL = 200
BUENDEL_SEKUNDEN = 2.0


class Zulauf(threading.Thread):
    """Liest den sequence-Strom und schreibt ihn in die Ablage."""

    def __init__(self, ablage, knoten_hole, adresse: str,
                 poolliste=None) -> None:
        super().__init__(name="zulauf", daemon=True)
        self.ablage = ablage
        self._knoten_hole = knoten_hole      # gibt eine rpc.Knoten-Instanz
        self.adresse = adresse
        self.pools = poolliste

        self._ende = threading.Event()
        self._letzte_nachricht: Optional[int] = None
        self._letzte_mempoolfolge: Optional[int] = None
        self._offen = 0
        self._zuletzt_gesichert = 0.0
        self._zuletzt_schnappschuss = 0.0
        self.laeuft_mit = False              # steht der Strom gerade?
        self.gesehen = 0

    # ── Steuerung ──────────────────────────────────────────────────────────

    def beende(self) -> None:
        self._ende.set()

    def _im_erstsync(self) -> bool:
        lage = rpc.kettenlage(self._knoten_hole())
        # Kein Kontakt: lieber warten als blind loslegen.
        return True if lage is None else bool(lage["im_erstsync"])

    def run(self) -> None:
        try:
            import zmq
        except ImportError:
            log.error("pyzmq fehlt -- die Auswertung bleibt aus.")
            return

        gemeldet = False
        while not self._ende.is_set():
            if self._im_erstsync():
                # Einmal sagen, nicht alle dreissig Sekunden. Auf des Betreibers
                # Knoten waren das 120 gleiche Zeilen je Stunde -- und
                # dazwischen gingen die zwei unter, die wirklich etwas
                # meldeten. Ein Protokoll, das man durchblaettern muss, ist
                # keines.
                if not gemeldet:
                    log.info("Erstabgleich laeuft -- der Zulauf wartet.")
                    gemeldet = True
                if self._ende.wait(WARTELAUF_SEKUNDEN):
                    return
                continue
            gemeldet = False
            self._lausche(zmq)

    def _lausche(self, zmq) -> None:
        zusammenhang = zmq.Context.instance()
        steckdose = zusammenhang.socket(zmq.SUB)
        # Nicht ewig auf ungesendete Nachrichten warten, wenn wir schliessen.
        steckdose.setsockopt(zmq.LINGER, 0)
        steckdose.setsockopt(zmq.SUBSCRIBE, THEMA)
        # Lieber alte Nachrichten verlieren als Speicher volllaufen lassen --
        # eine Luecke faellt auf, ein wachsender Puffer nicht.
        steckdose.setsockopt(zmq.RCVHWM, 20000)
        steckdose.connect(self.adresse)
        log.info("Zulauf verbunden mit %s.", self.adresse)
        self.laeuft_mit = True

        try:
            while not self._ende.is_set():
                if steckdose.poll(WARTEN_MS):
                    self._eine_nachricht(steckdose.recv_multipart())
                self._zwischendurch()
                # Kehrt der Knoten in den Abgleich zurueck -- Reindex, grosse
                # Reorg --, gehoert der Zulauf wieder schlafen gelegt.
                if self._zuletzt_schnappschuss and self._im_erstsync():
                    log.info("Knoten ist wieder im Abgleich -- Zulauf pausiert.")
                    return
        finally:
            self.laeuft_mit = False
            steckdose.close()
            self._sichern()

    # ── Ereignisse ─────────────────────────────────────────────────────────

    def _eine_nachricht(self, teile: List[bytes]) -> None:
        if len(teile) < 3 or teile[0] != THEMA:
            return
        rumpf, zaehler = teile[1], teile[2]

        # Teil 3: hat ZMQ Nachrichten verworfen?
        nummer = struct.unpack("<I", zaehler)[0] if len(zaehler) == 4 else None
        if nummer is not None:
            if (self._letzte_nachricht is not None
                    and nummer != (self._letzte_nachricht + 1) % 2**32):
                self.ablage.luecke("zmq", self._letzte_nachricht + 1, nummer)
            self._letzte_nachricht = nummer

        if len(rumpf) < 33:
            return
        kennung = rumpf[:32].hex()
        art = chr(rumpf[32])
        folge = (struct.unpack("<Q", rumpf[33:41])[0]
                 if len(rumpf) >= 41 else None)

        # Teil 2: die Mempool-Folgenummer. Sie wird MITGEFUEHRT, aber eine
        # Luecke darin ist KEIN Verlust -- und das war bis zum 08.09.2026
        # falsch verstanden.
        #
        # Core zaehlt sie bei JEDER Entfernung hoch, auch bei der, die keine
        # Meldung ausloest. Woertlich aus src/txmempool.cpp (v31.1,
        # removeUnchecked):
        #
        #     // We increment mempool sequence value no matter removal reason
        #     // even if not directly reported below.
        #     uint64_t mempool_sequence = GetAndIncrementSequence();
        #     if (reason != MemPoolRemovalReason::BLOCK && ...) {
        #         ... TransactionRemovedFromMempool(...)
        #
        # Jede Transaktion, die in einen Block kommt, springt also die Nummer
        # weiter, ohne dass etwas geschickt wird -- das ist Absicht, dafuer
        # gibt es die C-Meldung. Bei zweitausend Transaktionen je Block sind
        # das tausende Spruenge am Tag.
        #
        # Des Betreibers Uebersicht meldete deshalb "6070 verlorene Meldungen in
        # 24 h -- dort fehlen Zeitstempel". Es fehlte kein einziger: die
        # Transaktionen hatten ihren Zeitstempel vom A-Ereignis und ihren
        # Block vom C-Ereignis. Der Waechter rief sechstausendmal am Tag
        # Wolf.
        #
        # Was WIRKLICH Verlust anzeigt, ist die ZMQ-Zaehlung darueber: sie
        # ist je Thema fortlaufend und genau dafuer gemacht ("message
        # sequence number represents message count to detect lost messages",
        # doc/zmq.md). Die bleibt.
        if folge is not None:
            self._letzte_mempoolfolge = folge

        jetzt_ms = int(time.time() * 1000)
        self.gesehen += 1
        if art == "A":
            self.ablage.tx_aufgenommen(kennung, jetzt_ms, folge)
            self._offen += 1
        elif art == "R":
            # Ohne Block entfernt -- WARUM, sagt ZMQ nicht. Bis zum 15.09.2026
            # stand hier fest "verdraengt". "R" deckt aber alles ab, was
            # nicht in einen Block ging: ersetzt, abgelaufen, wegen Platz
            # hinausgeworfen, im Konflikt mit einer bestaetigten Transaktion.
            # Aeltere Zeilen tragen noch "verdraengt"; angezeigt wird der
            # Grund nirgends.
            self.ablage.tx_entfernt(kennung, jetzt_ms, "ohne_block")
            self._offen += 1
        elif art == "C":
            self._block(kennung, jetzt_ms)
        elif art == "D":
            # Eine Reorg. Der Block, den wir eingetragen haben, gilt nicht
            # mehr -- das gehoert festgehalten, nicht stillschweigend
            # ueberschrieben.
            self.ablage.reorg_vermerken()
            self._offen += 1

    def _block(self, blockhash: str, jetzt_ms: int) -> None:
        """Einen verbundenen Block auswerten.

        Drei kleine Aufrufe statt einem grossen: getblock mit Ausfuehrlichkeit
        1 liefert die txid-Liste (nicht jede Transaktion vollstaendig -- das
        waeren mehrere Megabyte JSON), getrawtransaction die Auszahlungs-
        adressen der Coinbase, getblockstats die Gebuehrensumme.
        """
        knoten = self._knoten_hole()
        try:
            block = knoten.ruf("getblock", blockhash, 1, zeitlimit=30.0)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.warning("Block %s nicht abrufbar: %s", blockhash[:12], fehler)
            return
        if not isinstance(block, dict):
            return

        txids = [t for t in block.get("tx") or [] if isinstance(t, str)]
        coinbase_hex = ((block.get("coinbase_tx") or {}).get("coinbase") or "")
        # ERST die Aufrufe nach draussen, DANN schreiben.
        #
        # DER BEFUND VOM 22.09.2026: tx_bestaetigt() oeffnet eine
        # Schreibtransaktion, und die Werte des folgenden Aufrufs wurden
        # danach ausgerechnet -- darunter _gebuehren() und _pool(), zwei
        # RPC-Aufrufe mit 30 und 20 Sekunden Zeitlimit. Die Transaktion stand
        # also bis zu fuenfzig Sekunden offen, waehrend jeder andere
        # Schreibende nur zwanzig Sekunden Geduld hat ("database is locked").
        gebuehren = self._gebuehren(knoten, blockhash)
        pool = self._pool(knoten, blockhash, txids, coinbase_hex)
        botschaft = self._botschaft(coinbase_hex)

        lage = self.ablage.tx_bestaetigt(txids, block.get("height", 0), jetzt_ms)
        self.ablage.block_eingetragen({
            "hoehe": block.get("height", 0),
            "hash": blockhash,
            "blockzeit": block.get("time"),
            "empfangen_ms": jetzt_ms,
            "gewicht": block.get("weight"),
            "txzahl": block.get("nTx", len(txids)),
            "gebuehren_sat": gebuehren,
            "pool": pool,
            "botschaft": botschaft,
            "bekannte_tx": lage["bekannt"],
            "verweildauer_ms": lage["median_ms"],
        })
        self._offen += 1
        self._sichern()
        log.info("Block %s (%s Transaktionen, davon %s vorher bei uns).",
                 block.get("height"), len(txids), lage["bekannt"])

    def _gebuehren(self, knoten, blockhash: str) -> Optional[int]:
        try:
            werte = knoten.ruf("getblockstats", blockhash, ["totalfee"],
                               zeitlimit=30.0)
            return werte.get("totalfee") if isinstance(werte, dict) else None
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            return None

    def _pool(self, knoten, blockhash: str, txids: List[str],
              coinbase_hex: str) -> Optional[str]:
        if self.pools is None or not txids:
            return None
        adressen: List[str] = []
        try:
            roh = knoten.ruf("getrawtransaction", txids[0], 2, blockhash,
                             zeitlimit=20.0)
            for ausgang in (roh or {}).get("vout") or []:
                adresse = (ausgang.get("scriptPubKey") or {}).get("address")
                if adresse:
                    adressen.append(adresse)
        except (rpc.NichtErreichbar, rpc.RpcFehler, AttributeError):
            pass                    # dann eben nur ueber die Kennung
        return self.pools.erkenne(coinbase_hex, adressen)

    @staticmethod
    def _botschaft(coinbase_hex: str) -> Optional[str]:
        from . import coinbase as cb
        stuecke = [s for s in cb.botschaften(coinbase_hex) if len(s) >= 4]
        return " ".join(stuecke)[:200] or None

    # ── Nebenher ───────────────────────────────────────────────────────────

    def _zwischendurch(self) -> None:
        jetzt = time.time()
        if (self._offen >= BUENDEL
                or (self._offen and jetzt - self._zuletzt_gesichert > BUENDEL_SEKUNDEN)):
            self._sichern()
        if jetzt - self._zuletzt_schnappschuss > SCHNAPPSCHUSS_SEKUNDEN:
            self._zuletzt_schnappschuss = jetzt
            self._schnappschuss()

    def _sichern(self) -> None:
        if self._offen:
            self.ablage.sichern()
            self._offen = 0
        self._zuletzt_gesichert = time.time()

    def _schnappschuss(self) -> None:
        """Groesse und Verwerfungsgrenze des Mempools festhalten.

        Die Verwerfungsgrenze ist der Wert, den grosse Explorer NICHT zeigen
        koennen: sie fahren ihre Knoten mit so hohem Limit, dass sie nie
        verwerfen muessen. Dieser hier laeuft mit dem Standardwert und sieht
        deshalb, ab welcher Gebuehr eine Transaktion wirklich herausfaellt.
        """
        knoten = self._knoten_hole()
        try:
            info = knoten.ruf("getmempoolinfo")
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            return
        if not isinstance(info, dict):
            return

        diagramm = None
        try:
            roh = knoten.ruf("getmempoolfeeratediagram", zeitlimit=20.0)
            if isinstance(roh, list):
                diagramm = roh
            self._diagramm_fehlt = False
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            # Erst ab Core 31 vorhanden -- und bei vollem Mempool kann der
            # Aufruf sein Zeitlimit reissen. Fehlt es, bleibt der Rest
            # stehen. Einmal melden, nicht jede Minute: die Oberflaeche zeigt
            # das Alter des letzten Diagramms ohnehin an.
            if not getattr(self, "_diagramm_fehlt", False):
                log.warning("Feerate-Diagramm nicht abrufbar: %s", fehler)
            self._diagramm_fehlt = True

        try:
            # mempoolminfee kommt in BTC je kvB. Mal 100.000 ergibt sat/vB --
            # die Einheit, in der jeder ueber Gebuehren spricht.
            grenze = float(info.get("mempoolminfee", 0)) * 100_000
        except (TypeError, ValueError):
            grenze = 0.0

        self.ablage.mempool_punkt(
            int(time.time()), int(info.get("size", 0)),
            int(info.get("bytes", 0)), round(grenze, 3), diagramm)
        self.ablage.sichern()
