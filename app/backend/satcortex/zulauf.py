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
import sqlite3
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

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

# Und wie oft, waehrend der Strom laeuft, ob der Knoten WIEDER im Abgleich
# ist (Reindex, grosse Reorg).
#
# DER BEFUND VOM 26.09.2026: Das wurde bei JEDER Meldung aus dem Strom
# gefragt, und zwar ueber rpc.kettenlage() -- fuenf Aufrufe, darunter
# getblockchaininfo und getnetworkinfo, die beide auf cs_main warten. Bei
# einem vollen Mempool sind das Dutzende Meldungen je Sekunde, also Hunderte
# Aufrufe, und waehrend eines Blocks haengt jeder davon bis zu fuenfzehn
# Sekunden. Ein Reindex kommt nicht ueberraschend in der naechsten
# Millisekunde; einmal je halbe Minute reicht.
ABGLEICH_PRUEFEN_SEKUNDEN = 30

# Nach so vielen Ereignissen wird geschrieben. Jede Zeile einzeln zu sichern
# hiesse bei jedem Block Tausende Schreibvorgaenge.
#
# Gesammelt wird im SPEICHER, nicht in einer offenen Transaktion. Bis zum
# 26.09.2026 trug der Zulauf jede Zeile sofort ein und sicherte erst Sekunden
# spaeter; dazwischen hielt er die Schreibsperre -- auch dann, wenn er
# gerade den Knoten fragte. Siehe store.Ablage.ereignisse().
BUENDEL = 200
BUENDEL_SEKUNDEN = 2.0

# Nimmt die Ablage gerade nichts an, bleibt das Gesammelte liegen und wird
# nach dieser Pause noch einmal versucht. Ohne Pause stuende der Zulauf bei
# jeder Meldung die volle Geduld der Ablage lang still und kaeme mit dem
# Lesen nicht mehr nach.
NEUER_VERSUCH_SEKUNDEN = 30

# Hoechstens so viele Ereignisse warten im Speicher. Bei einem vollen Mempool
# ist das rund eine halbe Stunde. Nimmt die Ablage laenger nichts an -- Platte
# voll, Datei kaputt --, wird verworfen und als Luecke vermerkt, statt den
# Speicher des Containers volllaufen zu lassen.
STAPEL_HOECHSTENS = 50_000

# Nach einem unerwarteten Fehler: so lange warten, dann neu anlaufen.
NEUER_ANLAUF_SEKUNDEN = 10


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
        # Was gesammelt, aber noch nicht geschrieben ist. Eintraege wie in
        # store.Ablage.ereignisse() beschrieben.
        self._stapel: List[Tuple] = []
        self._verworfen = 0
        self._naechster_versuch: Optional[float] = None     # monotonic
        self._sperre_gemeldet = False
        self._abgleich_geprueft: Optional[float] = None     # monotonic
        self._zuletzt_gesichert = 0.0
        self._zuletzt_schnappschuss = 0.0
        self.laeuft_mit = False              # steht der Strom gerade?
        self.gesehen = 0

    # ── Steuerung ──────────────────────────────────────────────────────────

    def beende(self) -> None:
        self._ende.set()

    def _abgleichstand(self) -> Optional[bool]:
        """Ist der Knoten im Abgleich? None heisst: weiss ich gerade nicht.

        EIN Aufruf, nicht rpc.kettenlage() mit fuenf -- gebraucht wird hier
        genau ein Feld.
        """
        try:
            kette = self._knoten_hole().ruf("getblockchaininfo",
                                            zeitlimit=rpc.GEDULD_SEKUNDEN)
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            return None
        if not isinstance(kette, dict):
            return None
        return bool(kette.get("initialblockdownload", True))

    def _im_erstsync(self) -> bool:
        # Vor dem Anlaufen: kein Kontakt heisst warten, nicht blind loslegen.
        return self._abgleichstand() is not False

    def run(self) -> None:
        try:
            import zmq
        except ImportError:
            log.error("pyzmq fehlt -- die Auswertung bleibt aus.")
            return

        gemeldet = False
        while not self._ende.is_set():
            # Dieser Faden laeuft NICHT unter dem Auffangbuegel der anderen
            # Hintergrundfaeden, und niemand startet ihn neu. Eine Ausnahme
            # hiess bis zum 26.09.2026: Faden tot, Auswertung steht, bis
            # jemand die Anwendung neu startet -- und nichts sagt es einem.
            try:
                if self._im_erstsync():
                    # Einmal sagen, nicht alle dreissig Sekunden. Auf des
                    # Betreibers Knoten waren das 120 gleiche Zeilen je
                    # Stunde -- und dazwischen gingen die zwei unter, die
                    # wirklich etwas meldeten. Ein Protokoll, das man
                    # durchblaettern muss, ist keines.
                    if not gemeldet:
                        log.info("Erstabgleich laeuft -- der Zulauf wartet.")
                        gemeldet = True
                    if self._ende.wait(WARTELAUF_SEKUNDEN):
                        return
                    continue
                gemeldet = False
                self._lausche(zmq)
            except Exception:                                # nosec B902
                log.exception("Zulauf unterbrochen -- neuer Anlauf in %d s.",
                              NEUER_ANLAUF_SEKUNDEN)
                if self._ende.wait(NEUER_ANLAUF_SEKUNDEN):
                    return

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
        # run() hat eben erst gefragt.
        self._abgleich_geprueft = time.monotonic()

        try:
            while not self._ende.is_set():
                if steckdose.poll(WARTEN_MS):
                    self._eine_nachricht(steckdose.recv_multipart())
                self._zwischendurch()
                # Kehrt der Knoten in den Abgleich zurueck -- Reindex, grosse
                # Reorg --, gehoert der Zulauf wieder schlafen gelegt.
                #
                # Aber NUR auf ein klares Ja. Bis zum 26.09.2026 galt auch
                # "keine Antwort" als Abgleich: haengt getblockchaininfo
                # waehrend eines Blocks einmal an cs_main, legte der Zulauf
                # die Steckdose weg und verband sich neu -- und alles, was
                # dazwischen kam, war verloren. Aus dem Betrieb, 26.09.2026:
                # eine "Luecke im zmq-Strom" gleich nach dem Sperrfehler.
                if self._abgleich_faellig() and self._abgleichstand() is True:
                    log.info("Knoten ist wieder im Abgleich -- Zulauf pausiert.")
                    return
        finally:
            self.laeuft_mit = False
            steckdose.close()
            self._sichern(trotz_pause=True)

    def _abgleich_faellig(self) -> bool:
        jetzt = time.monotonic()
        if (self._abgleich_geprueft is not None
                and jetzt - self._abgleich_geprueft < ABGLEICH_PRUEFEN_SEKUNDEN):
            return False
        self._abgleich_geprueft = jetzt
        return True

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
                erwartet = self._letzte_nachricht + 1
                log.warning("Luecke im zmq-Strom: erwartet %s, bekommen %s",
                            erwartet, nummer)
                self._vormerken(("L", int(time.time() * 1000), "zmq",
                                 erwartet, nummer))
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
            self._vormerken(("A", kennung, jetzt_ms, folge))
        elif art == "R":
            # Ohne Block entfernt -- WARUM, sagt ZMQ nicht. Bis zum 15.09.2026
            # stand hier fest "verdraengt". "R" deckt aber alles ab, was
            # nicht in einen Block ging: ersetzt, abgelaufen, wegen Platz
            # hinausgeworfen, im Konflikt mit einer bestaetigten Transaktion.
            # Aeltere Zeilen tragen noch "verdraengt"; angezeigt wird der
            # Grund nirgends.
            self._vormerken(("R", kennung, jetzt_ms, "ohne_block"))
        elif art == "C":
            self._block(kennung, jetzt_ms)
        elif art == "D":
            # Eine Reorg. Der Block, den wir eingetragen haben, gilt nicht
            # mehr -- das gehoert festgehalten, nicht stillschweigend
            # ueberschrieben.
            log.info("Reorg: ein Block wurde von der Kette getrennt.")
            self._vormerken(("D", jetzt_ms))

    def _vormerken(self, eintrag: Tuple) -> None:
        """Ein Ereignis zum Schreiben vormerken -- im Speicher."""
        if len(self._stapel) >= STAPEL_HOECHSTENS:
            # Die Ablage nimmt seit langem nichts an. Weitersammeln hiesse,
            # den Container am Speicherlimit sterben zu lassen. Was hier
            # wegfaellt, steht danach als Luecke in der Ablage -- sobald sie
            # wieder etwas annimmt.
            log.error("Die Ablage nimmt seit langem nichts an -- %d "
                      "gesammelte Ereignisse werden verworfen.",
                      len(self._stapel))
            self._verworfen += len(self._stapel)
            self._stapel = []
        self._stapel.append(eintrag)

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
        #
        # Und DER BEFUND VOM 26.09.2026 dazu: die Reihenfolge allein genuegte
        # nicht. Die Aufnahmen der letzten Sekunden waren zu diesem Zeitpunkt
        # schon EINGETRAGEN, aber noch nicht gesichert -- die Transaktion
        # war also bereits offen, als die Aufrufe hier begannen. Seitdem
        # liegt alles bis zum Schreiben im Speicher.
        gebuehren = self._gebuehren(knoten, blockhash)
        pool = self._pool(knoten, blockhash, txids, coinbase_hex)
        botschaft = self._botschaft(coinbase_hex)

        self._vormerken(("C", {
            "hoehe": block.get("height", 0),
            "hash": blockhash,
            "blockzeit": block.get("time"),
            "empfangen_ms": jetzt_ms,
            "gewicht": block.get("weight"),
            "txzahl": block.get("nTx", len(txids)),
            "gebuehren_sat": gebuehren,
            "pool": pool,
            "botschaft": botschaft,
        }, txids))
        self._sichern()

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
        if (len(self._stapel) >= BUENDEL
                or (self._stapel
                    and jetzt - self._zuletzt_gesichert > BUENDEL_SEKUNDEN)):
            self._sichern()
        if jetzt - self._zuletzt_schnappschuss > SCHNAPPSCHUSS_SEKUNDEN:
            self._zuletzt_schnappschuss = jetzt
            self._schnappschuss()

    def _sichern(self, trotz_pause: bool = False) -> bool:
        """Das Gesammelte schreiben. Gibt zurueck, ob es geklappt hat.

        Klappt es nicht, bleibt alles liegen und wird nach
        NEUER_VERSUCH_SEKUNDEN noch einmal versucht -- mit den Zeitpunkten,
        zu denen es ankam, nicht denen des Schreibens. Bis zum 26.09.2026
        flog der Fehler aus dem Faden, und der Zulauf war tot.
        """
        self._zuletzt_gesichert = time.time()
        if not self._stapel and not self._verworfen:
            return True
        if (not trotz_pause and self._naechster_versuch is not None
                and time.monotonic() < self._naechster_versuch):
            return False
        eintraege = list(self._stapel)
        if self._verworfen:
            # Voran, damit sie mit dem Rest steht oder faellt. In "erwartet"
            # steht bei dieser Art die Zahl der verworfenen Ereignisse --
            # eine Nachrichtennummer wie beim zmq-Strom gibt es hier nicht.
            eintraege.insert(0, ("L", int(time.time() * 1000), "ablage",
                                 self._verworfen, None))
        try:
            bloecke = self.ablage.ereignisse(eintraege)
        except sqlite3.Error as fehler:
            self._naechster_versuch = time.monotonic() + NEUER_VERSUCH_SEKUNDEN
            if not self._sperre_gemeldet:
                log.warning("Die Ablage nimmt gerade nichts an (%s) -- %d "
                            "Ereignisse warten und werden in %d s erneut "
                            "geschrieben.", fehler, len(self._stapel),
                            NEUER_VERSUCH_SEKUNDEN)
                self._sperre_gemeldet = True
            return False
        except Exception:                                    # nosec B902
            # Kein Sperrproblem, sondern etwas im Gesammelten selbst. Dann
            # hilft kein zweiter Versuch: derselbe Stapel scheiterte bei
            # jedem Anlauf wieder, und es kaeme nie mehr etwas an. Also
            # verwerfen -- und als Luecke vermerken, beim naechsten
            # Schreiben, statt es still fehlen zu lassen.
            log.exception("Gesammelte Ereignisse liessen sich nicht "
                          "schreiben -- %d werden verworfen.",
                          len(self._stapel))
            self._verworfen += len(self._stapel)
            self._stapel = []
            return False
        if self._sperre_gemeldet:
            log.info("Die Ablage nimmt wieder an -- alles Gesammelte ist "
                     "geschrieben.")
            self._sperre_gemeldet = False
        self._stapel = []
        self._verworfen = 0
        self._naechster_versuch = None
        for block in bloecke:
            log.info("Block %s (%s Transaktionen, davon %s vorher bei uns).",
                     block["hoehe"], block["txzahl"], block["bekannt"])
        return True

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

        self._vormerken(("M", int(time.time()), int(info.get("size", 0)),
                         int(info.get("bytes", 0)), round(grenze, 3),
                         diagramm))
        self._sichern()
