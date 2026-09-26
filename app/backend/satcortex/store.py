"""Was der Knoten gesehen hat -- dauerhaft, in SQLite.

Das Herzstueck der Auswertung ist eine Zahl, die man NICHT nachtraeglich
erfinden kann: wann DIESER Knoten eine Transaktion zum ersten Mal gesehen hat.
Kein Explorer kann sie liefern, kein spaeterer Abruf sie rekonstruieren. Sie
entsteht in dem Moment, in dem die Transaktion ankommt -- oder gar nicht.

Deshalb faengt die Geschichte mit der Inbetriebnahme an und nicht bei Block 0.

Warum SQLite: eine Datei, keine zweite Anwendung, kein Passwort, und sie laesst
sich mitsichern wie alles andere auch. Bei rund 400.000 Transaktionen am Tag
und dreissig Tagen Aufbewahrung sind das etwa zwoelf Millionen Zeilen -- fuer
SQLite unkritisch, solange die Datei auf der schnellen Platte liegt.

WAL-Modus, weil ein Schreiber (der Zulauf) und mehrere Leser (die Oberflaeche)
gleichzeitig arbeiten. Ohne WAL sperrt jeder Schreibvorgang die ganze Datei,
und die Uebersicht bliebe bei jedem Block kurz stehen.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# Wie lange einzelne Transaktionszeilen aufbewahrt werden. Bloecke und
# Tagessummen bleiben dauerhaft -- die sind klein und werden mit den Jahren
# erst interessant.
AUFBEWAHRUNG_TAGE = 30

# Nachrichten leben laenger als Transaktionen und kosten fast nichts: rund
# dreissig Quellen mal ein paar Meldungen taeglich sind im Jahr ein einziges
# Megabyte. Zwei Monate, damit man nach einem Urlaub noch findet, was man
# verpasst hat.
NACHRICHTEN_TAGE = 60

# Wieviele Meldungen die Liste hoechstens zeigt -- UND wieviele der Zaehler
# hoechstens zaehlt. Dass das dieselbe Zahl ist, ist der ganze Punkt.
#
# Aus dem Betrieb, 11.09.2026: "er zeigt mir links unter nachrrichten 25 neue an und
# wenn ich drauf klicke ist es vieleicht eine".
#
# Der Zaehler zaehlte ALLE ungelesenen Zeilen, die Liste zeigte die neuesten
# sechzig. Meldungen unterhalb dieser Grenze waren damit unerreichbar: sie
# liessen sich nicht anklicken, blieben also ungelesen, und der Zaehler stand
# fuer immer auf einer Zahl, zu der es nichts zu sehen gab. Bei dreissig ab
# Werk eingeschalteten Quellen bringt EIN Abrufdurchgang leicht mehr als
# sechzig Meldungen -- der Rest fiel sofort unter die Grenze.
NACHRICHTEN_FENSTER = 60

# Wie lange ein Schreibender auf die Sperre wartet, bevor er aufgibt.
#
# Die Zahl allein schuetzt vor nichts. DER BEFUND VOM 26.09.2026, aus dem
# Betrieb: "sqlite3.OperationalError: database is locked". Ursache war nicht
# eine zu kurze Geduld, sondern jemand, der die Sperre laenger hielt -- der
# Zulauf fragte bei offener Transaktion den Knoten, und das dauert waehrend
# eines Blocks gern fuenfzehn Sekunden. Die Regel dahinter steht bei
# _schreibend(): eine Schreibtransaktion enthaelt Datenbankarbeit und sonst
# nichts.
WARTEN_AUF_SPERRE_SEKUNDEN = 20.0

# In wie grossen Happen aufgeraeumt wird. Ein Tag Transaktionen sind rund
# 400.000 Zeilen; in EINEM Rutsch hielte das die Schreibsperre so lange, wie
# das Loeschen auf dem NAS eben dauert. Zwischen den Happen kommt jeder andere
# Schreibende dran.
AUFRAEUMEN_HAPPEN = 5000

SCHEMA = """
CREATE TABLE IF NOT EXISTS tx_gesehen (
    txid            TEXT PRIMARY KEY,
    zuerst_ms       INTEGER NOT NULL,
    folge           INTEGER,
    entfernt_ms     INTEGER,
    grund           TEXT,
    hoehe           INTEGER,
    verweildauer_ms INTEGER
);
CREATE INDEX IF NOT EXISTS tx_nach_zeit  ON tx_gesehen(zuerst_ms);
CREATE INDEX IF NOT EXISTS tx_nach_hoehe ON tx_gesehen(hoehe);

CREATE TABLE IF NOT EXISTS nachrichten (
    kennung        TEXT PRIMARY KEY,
    quelle         TEXT NOT NULL,
    quellenname    TEXT NOT NULL,
    titel          TEXT NOT NULL,
    anriss         TEXT,
    verweis        TEXT NOT NULL,
    zeitpunkt      INTEGER,
    geholt_s       INTEGER NOT NULL,
    sprache        TEXT,
    bezahlschranke INTEGER DEFAULT 0,
    gelesen        INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS nachrichten_nach_zeit
    ON nachrichten(zeitpunkt DESC);
CREATE INDEX IF NOT EXISTS nachrichten_nach_quelle ON nachrichten(quelle);

CREATE TABLE IF NOT EXISTS bloecke (
    hoehe               INTEGER PRIMARY KEY,
    hash                TEXT NOT NULL,
    blockzeit           INTEGER,
    empfangen_ms        INTEGER,
    gewicht             INTEGER,
    txzahl              INTEGER,
    gebuehren_sat       INTEGER,
    pool                TEXT,
    botschaft           TEXT,
    bekannte_tx         INTEGER,
    verweildauer_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS bloecke_nach_hash ON bloecke(hash);

CREATE TABLE IF NOT EXISTS mempool_verlauf (
    zeit_s          INTEGER PRIMARY KEY,
    txzahl          INTEGER,
    bytes           INTEGER,
    mindestgebuehr  REAL,
    diagramm        TEXT
);

-- Ohne diese Tabelle waeren alle Zahlen daneben stille Behauptungen.
-- Geht eine ZMQ-Nachricht verloren, fehlt uns ein Zeitstempel, und der
-- Durchschnitt daneben stimmt nicht mehr. Das gehoert festgehalten und
-- angezeigt, nicht weggelaechelt.
CREATE TABLE IF NOT EXISTS luecken (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit_ms   INTEGER NOT NULL,
    art       TEXT NOT NULL,
    erwartet  INTEGER,
    bekommen  INTEGER
);
CREATE INDEX IF NOT EXISTS luecken_nach_zeit ON luecken(zeit_ms);

-- Der HTLC-Strom: was durch diesen Knoten hindurchgeht -- und was NICHT.
--
-- Aus dem Betrieb, 12.09.2026: "koennen wir noch den HTLC-Strom mit rein nehmen".
--
-- Bis hierher las die Anwendung LNDs /v1/switch: die Historie der
-- ABGESCHLOSSENEN Weiterleitungen. Die sagt, was gelungen ist. Das
-- Betriebswissen steckt aber im Gegenteil -- in dem, was gescheitert ist und
-- warum. "INSUFFICIENT_BALANCE" heisst: dieser Kanal ist leer und gehoert
-- nachgefuellt. Das steht in keiner Historie, das kommt nur live.
CREATE TABLE IF NOT EXISTS htlc (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit_ms     INTEGER NOT NULL,
    art         TEXT NOT NULL,      -- weiterleiten | erledigt | fehl | link_fehl
    rein_kanal  TEXT,
    raus_kanal  TEXT,
    betrag      INTEGER,
    gebuehr     INTEGER,
    grund       TEXT                -- nur bei link_fehl: die eigentliche Auskunft
);
CREATE INDEX IF NOT EXISTS htlc_nach_zeit ON htlc(zeit_ms);
CREATE INDEX IF NOT EXISTS htlc_nach_grund ON htlc(grund);

-- Was das NETZ fuers Weiterleiten nimmt, einmal am Tag gemessen.
--
-- Eine Zeile je Tag, und der Tag ist der Schluessel: wer zweimal misst,
-- ueberschreibt sich selbst, statt den Durchschnitt zu verdoppeln. Ein
-- Jahrzehnt davon sind rund 3.600 Zeilen -- das ist nichts, und erst mit
-- den Jahren wird es interessant.
--
-- Warum ueberhaupt gespeichert: einen Vier-Wochen-Verlauf kann man nicht
-- nachtraeglich abrufen. Er entsteht, indem man taeglich hinsieht, oder er
-- entsteht nie. Dieselbe Sache wie beim ersten Sehen einer Transaktion.
CREATE TABLE IF NOT EXISTS netzgebuehren (
    tag               TEXT PRIMARY KEY,   -- YYYY-MM-DD in UTC
    zeit_s            INTEGER NOT NULL,
    median_ppm        INTEGER,
    p25_ppm           INTEGER,
    p75_ppm           INTEGER,
    basis_median_msat INTEGER,
    linien            INTEGER,
    kanaele           INTEGER,
    -- Was WIR an diesem Tag genommen haben. Steht daneben, weil die
    -- interessante Frage nicht "was nimmt das Netz" ist, sondern "wie weit
    -- bin ich davon weg" -- und weil die Automatik damit sehen kann, ob sie
    -- ueberhaupt etwas zu tun hat, ohne sich auf ihre eigene Erinnerung zu
    -- verlassen.
    eigen_ppm         INTEGER,
    -- Wie sich die Saetze auf ein paar runde Stufen verteilen, als JSON.
    -- Nachgereicht am 21.09.2026 -- siehe NACHGEREICHT unten.
    stufen            TEXT
);
"""

# Spalten, die spaeter dazugekommen sind.
#
# Das Schema oben steht als CREATE TABLE IF NOT EXISTS da: auf einer Datei,
# die es schon gibt, passiert dadurch GAR NICHTS. Wer die Anwendung seit
# Wochen laufen hat, bekaeme eine neue Spalte also nie zu sehen -- und den
# Fehler nicht beim Update, sondern beim naechsten Schreibvorgang.
#
# ALTER TABLE ADD COLUMN ist in SQLite ein Eintrag im Schema und beruehrt die
# Zeilen nicht; bestehende bekommen NULL. Deshalb steht hier auch nur diese
# eine Form: eine Spalte anhaengen, nie eine aendern oder entfernen.
NACHGEREICHT = (
    ("netzgebuehren", "stufen", "TEXT"),
)


def _median(werte: List[int]) -> Optional[int]:
    """Der echte Median, auch bei gerader Anzahl.

    Der erste Anlauf nahm einfach werte[n // 2] -- bei zwei Werten also den
    oberen. Bei einem Block mit Tausenden Transaktionen faellt das nie auf,
    bei einem leeren Block mit zwei bekannten schon. Ein Feld, das "Median"
    heisst, soll auch einer sein.
    """
    if not werte:
        return None
    werte = sorted(werte)
    mitte = len(werte) // 2
    if len(werte) % 2:
        return werte[mitte]
    return (werte[mitte - 1] + werte[mitte]) // 2


def _stufen_lesen(roh: Any) -> Optional[List[Dict]]:
    """Die gespeicherte Verteilung zurueckholen -- oder None.

    None heisst "an diesem Tag wurde noch keine erhoben", nicht "sie war
    leer". Jede Zeile von vor dem 21.09.2026 ist so eine, und die Oberflaeche
    zeigt dann die Spanne statt der Stufen, statt eine leere Leiste zu malen.

    Kaputtes JSON wird verschluckt: eine unlesbare Nebenauskunft darf die
    ganze Messreihe nicht mitreissen.
    """
    if not roh:
        return None
    try:
        wert = json.loads(roh)
    except (TypeError, ValueError):
        log.debug("Unlesbare Stufen in der Ablage.")
        return None
    return wert if isinstance(wert, list) else None


def _platzhalter(anzahl: int) -> str:
    """"?,?,?" fuer eine IN-Liste -- und NUR das.

    SQLite kennt keine Bindung fuer eine ganze Liste; die Fragezeichen muss
    man selbst zaehlen. Was hier entsteht, haengt allein an der ANZAHL --
    kein einziges Zeichen aus den Daten erreicht den SQL-Text, die Werte
    gehen als Parameter mit. Der Beweis steht in test_store.py, wo ein
    Quellenname mit einem DROP TABLE darin als Wert ankommt und nicht als
    Befehl.

    Eigene Funktion, damit die Absicht am Aufrufort lesbar ist -- eine
    f-Zeichenkette mitten in einer Abfrage sieht wie eine Einladung aus,
    und ein Pruefwerkzeug liest sie auch so.
    """
    return ",".join("?" * max(0, int(anzahl)))


class Ablage:
    """Die Datenbank. Eine Verbindung je Thread, WAL fuer nebenlaeufiges Lesen."""

    def __init__(self, pfad: str) -> None:
        self.pfad = Path(pfad)
        self._oertlich = threading.local()
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        # Einmal beim Anlegen: Schema und Einstellungen.
        with self._neu() as v:
            v.executescript(SCHEMA)
            self._spalten_nachreichen(v)

    @staticmethod
    def _spalten_nachreichen(v: sqlite3.Connection) -> None:
        """Was einer bestehenden Datei noch fehlt, anhaengen."""
        for tabelle, spalte, typ in NACHGEREICHT:
            da = {z["name"] for z in
                  v.execute(f"PRAGMA table_info({tabelle})").fetchall()}
            if da and spalte not in da:
                log.info("Spalte %s.%s wird nachgereicht.", tabelle, spalte)
                v.execute(
                    f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")

    def _neu(self) -> sqlite3.Connection:
        # IMMEDIATE: jede Transaktion, die Python von sich aus beginnt, holt
        # sich die Schreibsperre GLEICH am Anfang -- und wartet dort, wenn
        # jemand anders sie hat.
        #
        # DER BEFUND VOM 26.09.2026, gemessen: Ohne das beginnt SQLite eine
        # Transaktion als lesende. tx_bestaetigt() liest erst und schreibt
        # dann; speichert dazwischen ein anderer Faden etwas, ist der
        # gelesene Stand veraltet, und das Schreiben scheitert SOFORT mit
        # "database is locked". Die Geduld oben greift dabei gar nicht --
        # Warten wuerde den Stand ja nicht wieder aktuell machen.
        v = sqlite3.connect(str(self.pfad), timeout=WARTEN_AUF_SPERRE_SEKUNDEN,
                            isolation_level="IMMEDIATE")
        v.row_factory = sqlite3.Row
        v.execute("PRAGMA journal_mode=WAL")
        # NORMAL statt FULL: bei WAL bleibt die Datenbank auch so nach einem
        # Absturz heil, es koennen nur die letzten Sekunden fehlen. Fuer
        # Messwerte ist das der richtige Tausch -- FULL bedeutet ein fsync je
        # Transaktion, und davon haben wir bei jedem Block Tausende.
        v.execute("PRAGMA synchronous=NORMAL")
        v.execute("PRAGMA foreign_keys=ON")
        return v

    @property
    def v(self) -> sqlite3.Connection:
        verbindung = getattr(self._oertlich, "verbindung", None)
        if verbindung is None:
            verbindung = self._neu()
            self._oertlich.verbindung = verbindung
        return verbindung

    def schliesse(self) -> None:
        verbindung = getattr(self._oertlich, "verbindung", None)
        if verbindung is not None:
            verbindung.close()
            self._oertlich.verbindung = None

    @contextlib.contextmanager
    def _schreibend(self) -> Iterator[sqlite3.Connection]:
        """Eine Schreibtransaktion: ganz oder gar nicht, und KURZ.

        Kurz heisst: darin steht Datenbankarbeit und sonst nichts. Kein
        Aufruf an den Knoten, kein Warten auf das Netz. Wer die Sperre haelt,
        haelt sie fuer alle -- den HTLC-Strom, die Nachrichten, die
        Oberflaeche.

        Und bei einem Fehler wird zurueckgerollt. Vorher blieb eine
        Transaktion, deren Schreiben gescheitert war, einfach offen: der
        Faden las danach auf einem eingefrorenen Stand, jeder weitere
        Schreibversuch scheiterte wieder, und SQLite konnte sein
        Schreibprotokoll nicht mehr einarbeiten -- es waechst dann ohne Ende.
        """
        v = self.v
        try:
            yield v
            v.commit()
        except BaseException:
            v.rollback()
            raise

    # ── Schreiben ──────────────────────────────────────────────────────────

    def tx_aufgenommen(self, txid: str, zeit_ms: int, folge: Optional[int]) -> None:
        """Eine Transaktion ist in unseren Mempool gekommen.

        OR IGNORE, nicht OR REPLACE: taucht dieselbe txid ein zweites Mal auf
        -- nach einer Reorg etwa --, zaehlt der ERSTE Zeitpunkt. Ihn zu
        ueberschreiben hiesse, die einzige Zahl wegzuwerfen, die dieser Knoten
        exklusiv hat.
        """
        self.v.execute(
            "INSERT OR IGNORE INTO tx_gesehen (txid, zuerst_ms, folge) "
            "VALUES (?, ?, ?)", (txid, zeit_ms, folge))

    def tx_entfernt(self, txid: str, zeit_ms: int, grund: str) -> None:
        """Aus dem Mempool geflogen, ohne in einem Block zu landen."""
        self.v.execute(
            "UPDATE tx_gesehen SET entfernt_ms = ?, grund = ? "
            "WHERE txid = ? AND entfernt_ms IS NULL",
            (zeit_ms, grund, txid))

    def block_eingetragen(self, block: Dict) -> None:
        self.v.execute(
            "INSERT OR REPLACE INTO bloecke (hoehe, hash, blockzeit, "
            "empfangen_ms, gewicht, txzahl, gebuehren_sat, pool, botschaft, "
            "bekannte_tx, verweildauer_ms) "
            "VALUES (:hoehe, :hash, :blockzeit, :empfangen_ms, :gewicht, "
            ":txzahl, :gebuehren_sat, :pool, :botschaft, :bekannte_tx, "
            ":verweildauer_ms)", block)

    def tx_bestaetigt(self, txids: List[str], hoehe: int, zeit_ms: int) -> Dict:
        """Die Transaktionen eines Blocks als bestaetigt eintragen.

        Gibt zurueck, wie viele davon wir vorher kannten und wie lange sie im
        Schnitt bei uns lagen. Genau das ist die Zahl, die kein Explorer hat:
        nicht "wann wurde sie bestaetigt", sondern "wie lange lag sie bei MIR".
        """
        if not txids:
            return {"bekannt": 0, "median_ms": None}

        # Ueber eine Hilfstabelle statt "IN (?, ?, ... )".
        #
        # Ein Block hat bis zu mehrere tausend Transaktionen. Die alle als
        # Platzhalter in eine Abfrage zu schreiben laeuft irgendwann gegen
        # SQLites Obergrenze fuer Variablen -- und zwar erst dann, wenn mal
        # ein besonders voller Block kommt, also genau nicht beim Testen.
        # Ausserdem wird aus dem Aktualisieren so EINE Anweisung statt einer
        # Schleife ueber tausende Zeilen.
        v = self.v
        v.execute("CREATE TEMP TABLE IF NOT EXISTS blocktx (txid TEXT PRIMARY KEY)")
        v.execute("DELETE FROM blocktx")
        v.executemany("INSERT OR IGNORE INTO blocktx VALUES (?)",
                      ((t,) for t in txids))

        dauern = [zeit_ms - z["zuerst_ms"] for z in v.execute(
            "SELECT t.zuerst_ms FROM tx_gesehen t "
            "JOIN blocktx b ON b.txid = t.txid WHERE t.hoehe IS NULL")]

        v.execute(
            "UPDATE tx_gesehen SET hoehe = ?, verweildauer_ms = ? - zuerst_ms "
            "WHERE hoehe IS NULL AND txid IN (SELECT txid FROM blocktx)",
            (hoehe, zeit_ms))

        return {"bekannt": len(dauern), "median_ms": _median(dauern)}

    def mempool_punkt(self, zeit_s: int, txzahl: int, bytes_: int,
                      mindestgebuehr: float, diagramm: Optional[List]) -> None:
        self.v.execute(
            "INSERT OR REPLACE INTO mempool_verlauf "
            "(zeit_s, txzahl, bytes, mindestgebuehr, diagramm) "
            "VALUES (?, ?, ?, ?, ?)",
            (zeit_s, txzahl, bytes_, mindestgebuehr,
             json.dumps(diagramm) if diagramm else None))

    def luecke(self, art: str, erwartet: Optional[int],
               bekommen: Optional[int]) -> None:
        """Eine verlorene Nachricht festhalten.

        Wird angezeigt, nicht versteckt: ab hier fehlen Zeitstempel, und jeder
        Durchschnitt daneben ist ein Stueck weit geraten.
        """
        self._luecke_eintragen(int(time.time() * 1000), art, erwartet, bekommen)
        log.warning("Luecke im %s-Strom: erwartet %s, bekommen %s",
                    art, erwartet, bekommen)

    def _luecke_eintragen(self, zeit_ms: int, art: str,
                          erwartet: Optional[int],
                          bekommen: Optional[int]) -> None:
        self.v.execute(
            "INSERT INTO luecken (zeit_ms, art, erwartet, bekommen) "
            "VALUES (?, ?, ?, ?)", (zeit_ms, art, erwartet, bekommen))

    def ereignisse(self, liste: Sequence[Tuple]) -> List[Dict]:
        """Was der Zulauf gesammelt hat -- in EINER kurzen Transaktion.

        Der Zulauf haelt seine Ereignisse im Speicher und reicht sie hier
        gebuendelt herein. So steht die Schreibsperre nur fuer die Dauer des
        Schreibens, nie fuer die Zeit dazwischen, in der er auf den Strom
        oder auf den Knoten wartet. Bis zum 26.09.2026 trug er jede Zeile
        sofort ein und sicherte erst Sekunden spaeter -- dazwischen war die
        Ablage fuer alle anderen zu.

        Ganz oder gar nicht: scheitert es, steht nichts davon in der Datei,
        und der Zulauf kann dasselbe Buendel spaeter noch einmal reichen,
        ohne dass etwas doppelt ankommt.

        Die Eintraege, jeweils ein Tupel mit der Art vorne:

            ("A", txid, zeit_ms, folge)       in den Mempool aufgenommen
            ("R", txid, zeit_ms, grund)       ohne Block entfernt
            ("C", block, txids)               Block verbunden; block traegt
                                              die Spalten ausser bekannte_tx
                                              und verweildauer_ms
            ("D", zeit_ms)                    Block getrennt (Reorg)
            ("L", zeit_ms, art, erwartet, bekommen)   Luecke
            ("M", zeit_s, txzahl, bytes, mindestgebuehr, diagramm)
                                              Mempool-Schnappschuss

        Gibt je Block zurueck, wie viele seiner Transaktionen wir vorher
        kannten -- das ist die Zeile, die der Zulauf ins Protokoll schreibt.
        """
        bloecke: List[Dict] = []
        with self._schreibend():
            for eintrag in liste:
                art, werte = eintrag[0], eintrag[1:]
                if art == "A":
                    self.tx_aufgenommen(*werte)
                elif art == "R":
                    self.tx_entfernt(*werte)
                elif art == "C":
                    block, txids = werte
                    lage = self.tx_bestaetigt(txids, block["hoehe"],
                                              block["empfangen_ms"])
                    self.block_eingetragen({
                        **block, "bekannte_tx": lage["bekannt"],
                        "verweildauer_ms": lage["median_ms"]})
                    bloecke.append({"hoehe": block["hoehe"],
                                    "txzahl": block["txzahl"],
                                    "bekannt": lage["bekannt"]})
                elif art == "D":
                    self._reorg_eintragen(*werte)
                elif art == "L":
                    self._luecke_eintragen(*werte)
                elif art == "M":
                    self.mempool_punkt(*werte)
                else:
                    raise ValueError(f"unbekannte Ereignisart {art!r}")
        return bloecke

    def sichern(self) -> None:
        self.v.commit()

    # ── Lesen ──────────────────────────────────────────────────────────────

    def letzte_bloecke(self, wieviele: int = 15) -> List[Dict]:
        return [dict(z) for z in self.v.execute(
            "SELECT * FROM bloecke ORDER BY hoehe DESC LIMIT ?",
            (wieviele,)).fetchall()]

    def tx_eines_blocks(self, hoehe: int, grenze: int = 500) -> List[Dict]:
        """Die Transaktionen eines Blocks -- die, die WIR gesehen haben.

        DAS IST DIE ANSICHT, DIE KEIN EXPLORER LIEFERN KANN. Dass eine
        Transaktion in Block 966.088 steht, weiss jeder. Wann sie zum ersten
        Mal bei DIESEM Knoten ankam und wie lange sie dort wartete, weiss nur
        dieser Knoten -- einen First-Seen-Zeitstempel kann man nicht
        nachtraeglich erfinden.

        Die laengste Wartezeit zuerst: das ist die interessante Seite. Eine
        Transaktion, die zwei Stunden lag, sagt mehr ueber den Gebuehrenmarkt
        als tausend, die in Sekunden durchgingen.

        NICHT vollstaendig, und das gehoert dazugesagt: hier stehen nur die
        Transaktionen, die vor dem Block durch unseren Mempool kamen. Was der
        Miner selbst beisteuerte oder was uns waehrend einer Luecke im
        ZMQ-Strom entging, fehlt. Die Ansicht nennt beide Zahlen
        nebeneinander -- "davon vorher bei dir".
        """
        return [dict(z) for z in self.v.execute(
            "SELECT txid, zuerst_ms, verweildauer_ms FROM tx_gesehen "
            "WHERE hoehe = ? ORDER BY verweildauer_ms DESC LIMIT ?",
            (int(hoehe), int(grenze))).fetchall()]

    def ein_block(self, hoehe: int) -> Optional[Dict]:
        z = self.v.execute("SELECT * FROM bloecke WHERE hoehe = ?",
                           (int(hoehe),)).fetchone()
        return dict(z) if z else None

    def zuerst_gesehen(self, txids: List[str]) -> Dict[str, int]:
        """Zu vielen Transaktionen auf einmal: wann sahen WIR sie zuerst?

        Ueber eine Hilfstabelle statt "IN (?, ?, ...)" -- dieselbe Ueberlegung
        wie bei tx_bestaetigt: es koennen tausende sein, und SQLite hat eine
        Obergrenze fuer Platzhalter, gegen die man erst bei besonders vielen
        laeuft. Also genau dann, wenn es darauf ankommt.
        """
        if not txids:
            return {}
        v = self.v
        v.execute("CREATE TEMP TABLE IF NOT EXISTS suchtx (txid TEXT PRIMARY KEY)")
        v.execute("DELETE FROM suchtx")
        v.executemany("INSERT OR IGNORE INTO suchtx VALUES (?)",
                      ((t,) for t in txids))
        return {z["txid"]: z["zuerst_ms"] for z in v.execute(
            "SELECT t.txid, t.zuerst_ms FROM tx_gesehen t "
            "JOIN suchtx s ON s.txid = t.txid")}

    def eine_tx(self, txid: str) -> Optional[Dict]:
        z = self.v.execute("SELECT * FROM tx_gesehen WHERE txid = ?",
                           (txid,)).fetchone()
        return dict(z) if z else None

    def mempool_verlauf(self, seit_s: int) -> List[Dict]:
        return [dict(z) for z in self.v.execute(
            "SELECT zeit_s, txzahl, bytes, mindestgebuehr FROM mempool_verlauf "
            "WHERE zeit_s >= ? ORDER BY zeit_s", (seit_s,)).fetchall()]

    def diagramm_zeit(self) -> Optional[int]:
        """Wann das zuletzt gespeicherte Diagramm entstand, in Sekunden.

        letztes_diagramm() nimmt den juengsten Schnappschuss MIT Diagramm --
        auch wenn danach eine Stunde lang keins mehr kam. Ohne diese Zeit
        zeigte die Oberflaeche ein altes Diagramm, als waere es von jetzt.
        """
        z = self.v.execute(
            "SELECT MAX(zeit_s) AS t FROM mempool_verlauf "
            "WHERE diagramm IS NOT NULL").fetchone()
        return z["t"] if z and z["t"] is not None else None

    def reorg_vermerken(self) -> None:
        """Ein Block wurde getrennt -- eine Reorg, KEIN Verlust.

        Bis zum 15.09.2026 lief das ueber luecke() und zaehlte als "verlorene
        Meldung". Eine Reorg ist das Gegenteil: bitcoind hat sauber gemeldet,
        dass ein Block nicht mehr gilt.
        """
        self._reorg_eintragen(int(time.time() * 1000))
        log.info("Reorg: ein Block wurde von der Kette getrennt.")

    def _reorg_eintragen(self, zeit_ms: int) -> None:
        self.v.execute(
            "INSERT INTO luecken (zeit_ms, art, erwartet, bekommen) "
            "VALUES (?, 'reorg', NULL, NULL)", (zeit_ms,))

    def pool_anteile(self, letzte: int = 0) -> Dict:
        """Wer die aufgezeichneten Bloecke gefunden hat.

        "letzte" sind die juengsten N Bloecke, 0 heisst alle. Gezaehlt wird nur,
        was dieser Knoten selbst mitgeschrieben hat -- deshalb stehen Anzahl
        und Hoehenbereich mit in der Antwort. Ein Anteil ohne seine Grundlage
        waere eine Behauptung.
        """
        grenze = letzte if letzte > 0 else -1          # LIMIT -1: alle
        basis = self.v.execute(
            "SELECT COUNT(*) AS n, MIN(hoehe) AS von, MAX(hoehe) AS bis, "
            "MIN(blockzeit) AS ab FROM (SELECT hoehe, blockzeit FROM bloecke "
            "ORDER BY hoehe DESC LIMIT ?)", (grenze,)).fetchone()
        n = basis["n"] or 0
        zeilen = self.v.execute(
            "SELECT COALESCE(pool, '') AS pool, COUNT(*) AS anzahl "
            "FROM (SELECT pool FROM bloecke ORDER BY hoehe DESC LIMIT ?) "
            "GROUP BY COALESCE(pool, '') ORDER BY anzahl DESC, pool",
            (grenze,)).fetchall()
        return {
            "bloecke": n,
            "von_hoehe": basis["von"],
            "bis_hoehe": basis["bis"],
            "ab_blockzeit": basis["ab"],
            "pools": [{"pool": z["pool"] or None, "anzahl": z["anzahl"],
                       "anteil": round(z["anzahl"] / n, 4) if n else 0.0}
                      for z in zeilen],
        }

    def letztes_diagramm(self) -> Optional[List]:
        z = self.v.execute(
            "SELECT diagramm FROM mempool_verlauf WHERE diagramm IS NOT NULL "
            "ORDER BY zeit_s DESC LIMIT 1").fetchone()
        if not z or not z["diagramm"]:
            return None
        try:
            return json.loads(z["diagramm"])
        except ValueError:
            return None

    def eckdaten(self) -> Dict:
        """Was die Auswertung bisher gesammelt hat."""
        z = self.v.execute(
            "SELECT COUNT(*) AS tx, MIN(zuerst_ms) AS seit FROM tx_gesehen"
        ).fetchone()
        bloecke = self.v.execute("SELECT COUNT(*) AS n FROM bloecke").fetchone()
        grenze_ms = int((time.time() - 86400) * 1000)
        # Reorgs getrennt: eine Reorg ist keine verlorene Meldung.
        luecken = self.v.execute(
            "SELECT COUNT(*) AS n FROM luecken WHERE zeit_ms > ? "
            "AND art != 'reorg'", (grenze_ms,)).fetchone()
        reorgs = self.v.execute(
            "SELECT COUNT(*) AS n FROM luecken WHERE zeit_ms > ? "
            "AND art = 'reorg'", (grenze_ms,)).fetchone()
        return {"transaktionen": z["tx"], "sammelt_seit_ms": z["seit"],
                "bloecke": bloecke["n"], "luecken_24h": luecken["n"],
                "reorgs_24h": reorgs["n"]}

    # ── Pflege ─────────────────────────────────────────────────────────────

    verfuegbar = True

    # ------------------------------------------------- Nachrichten ---

    def nachricht_merken(self, b: Dict, geholt_s: int) -> bool:
        """Eine Meldung ablegen. Wahr, wenn sie neu war.

        INSERT OR IGNORE, nicht REPLACE: der Zeitpunkt, zu dem WIR eine
        Meldung zuerst gesehen haben, soll stehen bleiben. Verlage
        ueberschreiben ihre Beitraege gern nachtraeglich -- eine korrigierte
        Ueberschrift darf die Meldung nicht wieder nach oben spuelen und
        schon gar nicht als ungelesen zurueckkehren lassen.
        """
        with self._schreibend() as v:
            c = v.execute(
                """INSERT OR IGNORE INTO nachrichten
                   (kennung, quelle, quellenname, titel, anriss, verweis,
                    zeitpunkt, geholt_s, sprache, bezahlschranke)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (b["kennung"], b["quelle"], b["quellenname"], b["titel"],
                 b.get("anriss", ""), b["verweis"], b.get("zeitpunkt"),
                 geholt_s, b.get("sprache", ""),
                 1 if b.get("bezahlschranke") else 0))
        return c.rowcount > 0

    def nachrichten_lesen(self, grenze: int = NACHRICHTEN_FENSTER,
                          quellen: Optional[List[str]] = None) -> List[Dict]:
        """Die neuesten Meldungen, neueste zuerst.

        Sortiert wird nach dem Zeitpunkt des VERLAGS, ersatzweise nach dem
        unseren -- manche Feeds liefern kein Datum, und die sollen nicht
        stumm ans Ende rutschen.
        """
        wo, werte = "", []
        if quellen is not None:
            if not quellen:
                return []
            wo = " WHERE quelle IN (" + _platzhalter(len(quellen)) + ")"
            werte = list(quellen)
        werte.append(int(grenze))
        # Angehaengt wird nur die Fragezeichenliste aus _platzhalter().
        return [dict(r) for r in self.v.execute(
            "SELECT * FROM nachrichten" + wo +  # nosec B608
            " ORDER BY COALESCE(zeitpunkt, geholt_s) DESC LIMIT ?",
            werte).fetchall()]

    def nachricht_gelesen(self, kennung: str) -> None:
        with self._schreibend() as v:
            v.execute("UPDATE nachrichten SET gelesen=1 WHERE kennung=?",
                      (kennung,))

    def nachrichten_alle_gelesen(self) -> None:
        with self._schreibend() as v:
            v.execute("UPDATE nachrichten SET gelesen=1 WHERE gelesen=0")

    def nachrichten_ungelesen(self, quellen: Optional[List[str]] = None,
                              grenze: int = NACHRICHTEN_FENSTER) -> int:
        """Wieviele ungelesene -- IN DEM FENSTER, DAS DIE LISTE ZEIGT.

        Dieselbe Auswahl wie nachrichten_lesen, nur gezaehlt statt gelesen.
        Ein Zaehler, der ueber die Liste hinauszaehlt, nennt eine Zahl, zu der
        es nichts anzuklicken gibt -- und er geht nie wieder herunter, weil
        ungelesen bleibt, was man nicht erreichen kann.
        """
        wo, werte = "", []
        if quellen is not None:
            if not quellen:
                return 0
            wo = " WHERE quelle IN (" + _platzhalter(len(quellen)) + ")"
            werte = list(quellen)
        werte.append(int(grenze))
        # Wie oben: nur Fragezeichen, die Werte gehen als Parameter mit.
        return int(self.v.execute(
            "SELECT COUNT(*) FROM (SELECT gelesen FROM nachrichten"  # nosec B608
            + wo + " ORDER BY COALESCE(zeitpunkt, geholt_s) DESC LIMIT ?)"
            " WHERE gelesen=0", werte).fetchone()[0])

    # ── Der HTLC-Strom ────────────────────────────────────────────────
    def htlc_merken(self, e: Dict) -> None:
        with self._schreibend() as v:
            v.execute(
                "INSERT INTO htlc (zeit_ms, art, rein_kanal, raus_kanal,"
                " betrag, gebuehr, grund) VALUES (:zeit_ms, :art,"
                " :rein_kanal, :raus_kanal, :betrag, :gebuehr, :grund)", e)

    def htlc_lesen(self, grenze: int = 100) -> List[Dict]:
        return [dict(r) for r in self.v.execute(
            "SELECT * FROM htlc ORDER BY zeit_ms DESC LIMIT ?",
            (int(grenze),)).fetchall()]

    def htlc_gruende(self, seit_ms: int = 0) -> List[Dict]:
        """Die Fehlschlaege nach Grund UND Kanal -- die eigentliche Auskunft.

        Nicht "es ist etwas schiefgegangen", sondern "an diesem Kanal ist
        siebenmal das Guthaben ausgegangen". Das eine ist eine Meldung, das
        andere ein Handgriff.
        """
        return [dict(r) for r in self.v.execute(
            "SELECT grund, rein_kanal, raus_kanal, COUNT(*) AS anzahl "
            "FROM htlc WHERE art='link_fehl' AND grund IS NOT NULL "
            "AND zeit_ms >= ? GROUP BY grund, rein_kanal, raus_kanal "
            "ORDER BY anzahl DESC LIMIT 50", (int(seit_ms),)).fetchall()]

    def netzgebuehren_merken(self, tag: str, zeit_s: int,
                             werte: Dict) -> None:
        """Die Tagesmessung festhalten -- oder die des Tages ersetzen."""
        with self._schreibend() as v:
            v.execute(
                "INSERT OR REPLACE INTO netzgebuehren "
                "(tag, zeit_s, median_ppm, p25_ppm, p75_ppm,"
                " basis_median_msat, linien, kanaele, eigen_ppm, stufen)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(tag), int(zeit_s), werte.get("median_ppm"),
                 werte.get("p25_ppm"), werte.get("p75_ppm"),
                 werte.get("basis_median_msat"), werte.get("linien"),
                 werte.get("kanaele"),
                 (werte.get("eigen") or {}).get("satz_ppm"),
                 json.dumps(werte["stufen"]) if werte.get("stufen")
                 else None))

    def netzgebuehren_verlauf(self, tage: int = 28) -> List[Dict]:
        """Die letzten Messtage, der juengste zuerst.

        Begrenzt wird ueber die ANZAHL der Zeilen, nicht ueber ein Datum:
        stand der Knoten drei Tage still, sollen die Tage davor noch zaehlen
        und nicht stillschweigend aus dem Fenster fallen. Das Fenster ist
        "die letzten vier Wochen, AN DENEN GEMESSEN WURDE".
        """
        zeilen = self.v.execute(
            "SELECT * FROM netzgebuehren ORDER BY tag DESC LIMIT ?",
            (max(1, int(tage)),)).fetchall()
        return [{**dict(z), "stufen": _stufen_lesen(z["stufen"])}
                for z in zeilen]

    def netzgebuehren_aufraeumen(self, behalten: int = 400) -> int:
        """Alte Tageszeilen wegwerfen. Ein gutes Jahr bleibt stehen."""
        with self._schreibend() as v:
            weg = v.execute(
                "DELETE FROM netzgebuehren WHERE tag NOT IN "
                "(SELECT tag FROM netzgebuehren ORDER BY tag DESC LIMIT ?)",
                (max(1, int(behalten)),)).rowcount
        return weg

    def htlc_aufraeumen(self, tage: int = NACHRICHTEN_TAGE) -> int:
        # max(1, ...) wie beim Nachbarn: ohne die Klammer raeumt eine Null
        # die ganze Tabelle ab. Heute ruft das niemand mit einer Null -- und
        # "heute ruft das niemand so" ist keine Eigenschaft, auf die man baut.
        grenze = int((time.time() - max(1, int(tage)) * 86400) * 1000)
        with self._schreibend() as v:
            c = v.execute("DELETE FROM htlc WHERE zeit_ms < ?", (grenze,))
        return c.rowcount

    def nachrichten_aufraeumen(self, tage: int = NACHRICHTEN_TAGE) -> int:
        grenze = int(time.time()) - max(1, int(tage)) * 86400
        with self._schreibend() as v:
            c = v.execute(
                "DELETE FROM nachrichten "
                "WHERE COALESCE(zeitpunkt, geholt_s) < ?", (grenze,))
        return c.rowcount

    def aufraeumen(self, tage: int = AUFBEWAHRUNG_TAGE) -> int:
        """Alte Transaktionszeilen wegwerfen. Bloecke bleiben.

        In Happen, jeder in seiner eigenen kurzen Transaktion -- siehe
        AUFRAEUMEN_HAPPEN. Ueber rowid statt ueber die Zeit allein, weil
        DELETE ... LIMIT in SQLite eine Uebersetzungsoption braucht, die
        Pythons SQLite nicht mitbringt.
        """
        grenze = int((time.time() - tage * 86400) * 1000)
        weg = 0
        while True:
            with self._schreibend() as v:
                happen = v.execute(
                    "DELETE FROM tx_gesehen WHERE rowid IN (SELECT rowid "
                    "FROM tx_gesehen WHERE zuerst_ms < ? LIMIT ?)",
                    (grenze, AUFRAEUMEN_HAPPEN)).rowcount
            weg += happen
            if happen < AUFRAEUMEN_HAPPEN:
                break
        with self._schreibend() as v:
            v.execute("DELETE FROM luecken WHERE zeit_ms < ?", (grenze,))
        if weg:
            log.info("Aufgeraeumt: %d Transaktionszeilen aelter als %d Tage.",
                     weg, tage)
        return weg


class LeereAblage:
    """Wenn die Datenbank nicht geoeffnet werden kann.

    Der haeufigste Grund ist banal und auf einem NAS die Regel: der
    eingehaengte Ordner gehoert einem anderen Benutzer, und der Dienst darf
    darin nicht schreiben. Genau daran ist am 27.08.2026 der Probelauf der CI
    gescheitert -- und das war gut so, denn es ist dieselbe Lage wie bei einem
    Nutzer, der seine Ordner im Dateimanager anlegt.

    Die Anwendung deswegen gar nicht erst starten zu lassen waere falsch: die
    Auswertung ist ein Teil, nicht das Ganze. Assistent, Uebersicht, Karte und
    Versionspruefung haben mit ihr nichts zu tun.

    Also nimmt diese Ablage alles entgegen und gibt Leeres zurueck -- aber
    STILL ist sie nicht: der Grund steht im Protokoll und in der Antwort von
    /api/auswertung, und die Oberflaeche sagt ihn dem Nutzer.
    """

    verfuegbar = False

    def __init__(self, grund: str = "") -> None:
        self.grund = grund

    def _nichts(self, *a, **k) -> None:
        return None

    tx_aufgenommen = tx_entfernt = block_eingetragen = _nichts
    mempool_punkt = luecke = sichern = schliesse = _nichts

    def ereignisse(self, liste) -> List[Dict]:
        return []

    def tx_bestaetigt(self, txids, hoehe, zeit_ms) -> Dict:
        return {"bekannt": 0, "median_ms": None}

    def letzte_bloecke(self, wieviele: int = 15) -> List[Dict]:
        return []

    def tx_eines_blocks(self, hoehe, grenze: int = 500) -> List[Dict]:
        return []

    def ein_block(self, hoehe) -> Optional[Dict]:
        return None

    def zuerst_gesehen(self, txids) -> Dict[str, int]:
        return {}

    def eine_tx(self, txid: str) -> Optional[Dict]:
        return None

    def mempool_verlauf(self, seit_s: int) -> List[Dict]:
        return []

    def letztes_diagramm(self) -> Optional[List]:
        return None

    def diagramm_zeit(self) -> Optional[int]:
        return None

    def reorg_vermerken(self) -> None:
        pass

    def pool_anteile(self, letzte: int = 0) -> Dict:
        return {"bloecke": 0, "von_hoehe": None, "bis_hoehe": None,
                "ab_blockzeit": None, "pools": []}

    def eckdaten(self) -> Dict:
        return {"transaktionen": 0, "sammelt_seit_ms": None,
                "bloecke": 0, "luecken_24h": 0, "reorgs_24h": 0}

    def aufraeumen(self, tage: int = AUFBEWAHRUNG_TAGE) -> int:
        return 0

    # Nachrichten: dieselbe Haltung wie oben. Ohne Datenbank gibt es keinen
    # Verlauf -- aber der Reiter darf deswegen nicht mit einem Fehler
    # antworten, sondern zeigt eine leere Liste und den Grund.
    def nachricht_merken(self, b: Dict, geholt_s: int) -> bool:
        return False

    def nachrichten_lesen(self, grenze: int = NACHRICHTEN_FENSTER,
                          quellen: Optional[List[str]] = None) -> List[Dict]:
        return []

    nachricht_gelesen = nachrichten_alle_gelesen = _nichts

    def nachrichten_ungelesen(self, quellen: Optional[List[str]] = None,
                              grenze: int = NACHRICHTEN_FENSTER) -> int:
        return 0

    htlc_merken = _nichts

    def htlc_lesen(self, grenze: int = 100) -> List[Dict]:
        return []

    def htlc_gruende(self, seit_ms: int = 0) -> List[Dict]:
        return []

    def htlc_aufraeumen(self, tage: int = NACHRICHTEN_TAGE) -> int:
        return 0

    netzgebuehren_merken = _nichts

    def netzgebuehren_verlauf(self, tage: int = 28) -> List[Dict]:
        return []

    def netzgebuehren_aufraeumen(self, behalten: int = 400) -> int:
        return 0

    def nachrichten_aufraeumen(self, tage: int = NACHRICHTEN_TAGE) -> int:
        return 0


def oeffne(pfad: str):
    """Die Ablage oeffnen -- oder eine leere, die den Grund kennt.

    Gibt IMMER etwas zurueck, an dem der Rest der Anwendung arbeiten kann.
    Ein fehlgeschlagener Zugriff auf eine Nebendatenbank darf nicht den
    ganzen Dienst am Start hindern.
    """
    try:
        return Ablage(pfad)
    except (OSError, sqlite3.Error) as fehler:
        log.error("Auswertungsdatenbank %s nicht nutzbar: %s -- die Auswertung "
                  "bleibt aus, alles andere laeuft weiter.", pfad, fehler)
        return LeereAblage(str(fehler))
