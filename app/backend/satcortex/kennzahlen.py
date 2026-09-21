"""Die Zahlen, die unter der Weltkarte stehen.

Vier Auskuenfte, die ein Mensch beim Hinsehen sucht: Was kommt als naechstes
in einen Block? Was kostet das gerade? Wie schwer ist Schuerfen im Moment,
und wohin geht es? Sie standen bisher nirgends -- die Schwierigkeit sogar,
obwohl getblockchaininfo sie bei jedem Abruf mitliefert und weggeworfen wurde.

Zwei Eigenheiten, die man kennen muss:

* getblocktemplate ist WAEHREND DES ABGLEICHS nicht zu haben. Core lehnt es
  ausdruecklich ab ("is in initial sync and waiting for blocks"), und das ist
  richtig so: ohne vollstaendige Kette waere jede Vorlage geraten. Fehlt sie,
  gibt es hier None -- und die Oberflaeche sagt es statt eine Null zu zeigen.

* estimatesmartfee antwortet in BTC je kvB. Ungerechnet stuende dort 0.00044
  statt 44 sat/vB. Dieselbe Umrechnung wie bei mempoolminfee in zulauf.py:
  mal 100.000.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from . import rpc

log = logging.getLogger(__name__)

# Wieviele Bloecke zwischen zwei Anpassungen der Schwierigkeit liegen. Steht
# in Cores chainparams.cpp als nPowTargetTimespan / nPowTargetSpacing.
PERIODE = 2016
# Die angestrebte Zeit je Block. Das ganze Gerede von "alle zehn Minuten"
# steckt in dieser einen Zahl.
ZIELABSTAND_SEKUNDEN = 600

# Das Protokoll laesst je Anpassung hoechstens Vervierfachung und Viertelung
# zu (chainparams: nPowTargetTimespan/4 bzw. *4). Eine Schaetzung von +900 %
# waere also nicht nur unwahrscheinlich, sondern schlicht unmoeglich.
GRENZE_HOCH = 300.0
GRENZE_RUNTER = -75.0

# Fuer welche Wartezeiten geschaetzt wird. Mehr Ziele braeuchte niemand: die
# Frage ist "gleich, bald oder irgendwann".
ZIELE = (("schnell", 1), ("normal", 3), ("guenstig", 6))

# BTC je kvB -> Satoshi je vByte.
JE_VBYTE = 100_000


def naechster_block(knoten: rpc.Knoten) -> Optional[Dict[str, Any]]:
    """Was dieser Knoten als naechsten Block bauen wuerde.

    Nicht "was mempool.space schaetzt" -- das hier ist die Auswahl DIESES
    Knotens aus SEINEM Mempool, nach seiner Policy. Genau die Sorte Auskunft,
    fuer die man einen eigenen Knoten betreibt.

    Die Regel "segwit" muss mitgefragt werden; ohne sie antwortet Core mit
    einem Fehler statt mit einer Vorlage.
    """
    try:
        vorlage = knoten.ruf("getblocktemplate", {"rules": ["segwit"]},
                             zeitlimit=20.0)
    except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
        # Im Erstabgleich der Normalfall, kein Grund fuer eine Warnung.
        log.debug("Keine Blockvorlage: %s", fehler)
        return None
    if not isinstance(vorlage, dict):
        return None

    txe = vorlage.get("transactions") or []
    gewicht = sum(int(t.get("weight") or 0) for t in txe)
    gebuehren = sum(int(t.get("fee") or 0) for t in txe)

    saetze = []
    for t in txe:
        w = int(t.get("weight") or 0)
        if w > 0:
            # vByte ist Gewicht durch vier -- so rechnet SegWit.
            saetze.append(int(t.get("fee") or 0) / (w / 4))

    return {
        "hoehe": int(vorlage.get("height") or 0),
        "transaktionen": len(txe),
        "gewicht": gewicht,
        "vbytes": gewicht // 4,
        "gebuehren_sat": gebuehren,
        # Die Belohnung enthaelt die neuen Coins UND die Gebuehren.
        "belohnung_sat": int(vorlage.get("coinbasevalue") or 0),
        "sat_vb_min": round(min(saetze), 1) if saetze else 0,
        "sat_vb_max": round(max(saetze), 1) if saetze else 0,
        "gewichtsgrenze": int(vorlage.get("weightlimit") or 4_000_000),
    }


def gebuehren(knoten: rpc.Knoten) -> Dict[str, float]:
    """Was es kostet, in einen der naechsten Bloecke zu kommen.

    Fehlt zu einem Ziel die Datengrundlage, faellt es WEG statt als 0 zu
    erscheinen. Null hiesse "umsonst" -- das waere eine Falschauskunft, und
    zwar eine teure.
    """
    raus: Dict[str, float] = {}
    for name, ziel in ZIELE:
        try:
            d = knoten.ruf("estimatesmartfee", ziel) or {}
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.debug("Keine Gebuehrenschaetzung: %s", fehler)
            return raus
        satz = d.get("feerate")
        if satz is None:
            continue
        try:
            raus[name] = round(float(satz) * JE_VBYTE, 1)
        except (TypeError, ValueError):
            continue
    return raus


# ── Was ein Kanal an On-Chain-Gebuehren kostet ─────────────────────────────
#
# Aus dem Betrieb, 04.09.2026: "die Gebuehrenlage beim Oeffnen und Schliessen, das
# sollte unsere App dann direkt da, wo es passiert, sauber anzeigen, damit es
# nicht zu boesen Ueberraschungen kommt."
#
# Besonders wichtig, bei einem kleinen Einstieg: bei einem Kanal von rund 146.000
# Sats sind zwei Sats je vByte Kleingeld -- zweihundert waeren ein Drittel
# davon. Dieselbe Gebuehr, voellig andere Bedeutung.
#
# Groessen einer Taproot-Transaktion, aus den Standardwerten gerechnet:
# Eingang ueber den Schluesselpfad 57,5 vB, Ausgang 43 vB, Rahmen 10,5 vB.
#   Oeffnen: 1 Eingang + Kanalausgang + Wechselgeld = 57,5 + 43 + 43 + 10,5
#   Einvernehmlich schliessen: 1 Eingang + 2 Ausgaenge = dasselbe
# Beides aufgerundet auf 154 vB. Es ist eine Schaetzung und heisst in der
# Oberflaeche auch so -- die wirkliche Groesse haengt daran, wieviele
# Eingaenge die Wallet zusammensuchen muss.
KANAL_VBYTE = 154

# Was in JEDEM Kanal auf beiden Seiten liegenbleibt und nicht ausgegeben
# werden kann. BOLT 2 empfiehlt ein Prozent der Kapazitaet, LND setzt es so.
# Beim PLANEN ist es eine Faustzahl -- bei einem bestehenden Kanal fragen wir
# LND nach dem wirklichen Wert (local_chan_reserve_sat in lnd.kanaele).
KANAL_RESERVE_PROZENT = 1.0


def kanalkosten(gebuehren: Dict[str, float],
                guthaben_sat: int = 0,
                verlauf: Optional[Dict[str, Any]] = None,
                ruecklage_sat: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Oeffnen und Schliessen in Satoshi, bei der jetzigen Gebuehrenlage.

    Ohne Schaetzung gibt es KEINE Zahl -- eine Null hiesse "umsonst", und das
    waere hier die teuerste Falschauskunft von allen.

    "verlauf" ist die Verteilung der letzten Woche aus der eigenen Kette. Erst
    damit wird aus "2,2 sat/vB" eine Auskunft statt einer Zahl.

    "ruecklage_sat" ist LNDs eigene Antwort darauf, was On-Chain liegenbleiben
    muss, wenn ein Kanal dazukommt -- nicht unsere Schaetzung.
    """
    satz = gebuehren.get("normal") or gebuehren.get("guenstig") \
        or gebuehren.get("schnell")
    if not satz:
        return None
    oeffnen = round(KANAL_VBYTE * satz)
    schliessen = round(KANAL_VBYTE * satz)
    aus: Dict[str, Any] = {
        "satz_sat_vb": satz,
        "oeffnen_sat": oeffnen,
        "schliessen_sat": schliessen,
        "zusammen_sat": oeffnen + schliessen,
    }
    # Der Anteil ist die eigentliche Aussage. Absolute Satoshi sagen einem
    # Menschen nichts; "ein Drittel deines Guthabens" sagt alles.
    if guthaben_sat > 0:
        aus["anteil_prozent"] = round(
            (oeffnen + schliessen) / guthaben_sat * 100, 2)

    # Der Vergleich mit der eigenen letzten Woche. Er steht bewusst NICHT
    # unter der Bedingung "guthaben_sat > 0": wer plant, hat noch nichts --
    # und braucht die Einordnung am dringendsten.
    if verlauf:
        aus["verlauf"] = verlauf
        lage = einordnung(satz, verlauf)
        if lage:
            aus["lage"] = lage

    # Was zur Kanalgroesse dazukommt, damit das Oeffnen ueberhaupt gelingt.
    if ruecklage_sat is not None:
        aus["ruecklage_sat"] = ruecklage_sat
    aus["reserve_prozent"] = KANAL_RESERVE_PROZENT
    return aus


def schwierigkeit(knoten: rpc.Knoten, lage: Dict[str, Any],
                  jetzt: Optional[float] = None) -> Dict[str, Any]:
    """Wie schwer Schuerfen gerade ist -- und wohin es geht.

    Die Schaetzung der naechsten Anpassung ist kein Orakel, sondern ein
    Dreisatz: das Netz braucht fuer die bisherigen Bloecke dieser Periode
    eine bestimmte Zeit, gewollt waeren zehn Minuten je Block. Der
    Unterschied ist die Anpassung.

    Sie faellt weg, wenn der Anfang der Periode nicht vorliegt -- waehrend
    des Abgleichs der Normalfall. Lieber keine Zahl als eine erfundene.
    """
    hoehe = int(lage.get("hoehe") or 0)
    seit_anfang = hoehe % PERIODE
    d: Dict[str, Any] = {
        "wert": lage.get("difficulty"),
        "bloecke_bis_anpassung": PERIODE - seit_anfang,
        "bloecke_seit_anpassung": seit_anfang,
    }
    if seit_anfang == 0:
        return d

    try:
        hash_ = knoten.ruf("getblockhash", hoehe - seit_anfang)
        kopf = knoten.ruf("getblockheader", hash_) or {}
        angefangen = float(kopf.get("time") or 0)
    except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
        log.debug("Periodenanfang nicht zu haben: %s", fehler)
        return d
    if angefangen <= 0:
        return d

    vergangen = (time.time() if jetzt is None else jetzt) - angefangen
    if vergangen <= 0:
        return d
    erwartet = seit_anfang * ZIELABSTAND_SEKUNDEN
    aenderung = (erwartet / vergangen - 1) * 100
    d["aenderung_prozent"] = round(
        max(GRENZE_RUNTER, min(GRENZE_HOCH, aenderung)), 1)
    return d


# ── Ist die Gebuehr gerade teuer oder guenstig? ────────────────────────────
#
# Aus dem Betrieb, 11.09.2026: "waere das nicht gut wenn er uns sagen wuerde ob das
# momentan teuer oder guenstig ist im durchschnitt .. ?? das mann ne
# orientierung hat".
#
# Eine Zahl wie "2,2 sat/vB" sagt einem Menschen nichts. Erst der Vergleich
# macht daraus eine Auskunft. Und der Vergleich kommt aus der EIGENEN Kette,
# nicht von einer fremden Seite: getblockstats sagt je Block, bei welchen
# Saetzen tatsaechlich bestaetigt wurde. Genommen wird der Median -- der Satz
# der mittleren Transaktion, also das, was die meisten wirklich gezahlt haben.
#
# Eine Woche, jeder siebte Block. Warum nicht jeder: das waeren 1008
# Leseaufrufe auf die Platte, auf der die Bloecke liegen (bei uns die HDD).
# Fuer eine Verteilung braucht es das nicht -- 144 Stichproben ueber dieselbe
# Woche ergeben dieselbe Aussage zu einem Siebtel des Aufwands.
VERLAUF_BLOECKE = 1008
VERLAUF_SCHRITT = 7
# Darunter ist es keine Verteilung mehr, sondern Zufall. Dann lieber nichts.
VERLAUF_MINDESTENS = 30
# Je Block ein Aufruf, und die Bloecke liegen auf einer drehenden Platte.
VERLAUF_ZEITLIMIT = 20.0
# Wo die Grenzen zwischen guenstig, normal und teuer liegen -- als Stelle in
# der Verteilung der Woche, nicht als feste Satzzahl. Eine feste Zahl waere
# im naechsten Jahr falsch; "unteres Viertel der Woche" bleibt richtig.
GRENZE_GUENSTIG = 0.25
GRENZE_TEUER = 0.75


def _stelle(sortiert, anteil: float) -> float:
    """Der Wert an dieser Stelle der sortierten Reihe (0.0 = der kleinste)."""
    if not sortiert:
        return 0.0
    i = int(round(anteil * (len(sortiert) - 1)))
    return sortiert[max(0, min(len(sortiert) - 1, i))]


def gebuehrenverlauf(knoten: rpc.Knoten, hoehe: int) -> Optional[Dict[str, Any]]:
    """Bei welchen Saetzen in der letzten Woche wirklich bestaetigt wurde.

    Gibt None, wenn zu wenige Bloecke zusammenkamen -- waehrend des Abgleichs
    der Normalfall, und eine Verteilung aus fuenf Bloecken waere keine.

    Einzelne Ausfaelle sind dagegen kein Grund aufzugeben: aus 130 statt 144
    Stichproben wird dieselbe Aussage.
    """
    if hoehe <= VERLAUF_BLOECKE:
        return None
    saetze = []
    for h in range(hoehe - VERLAUF_BLOECKE, hoehe + 1, VERLAUF_SCHRITT):
        try:
            werte = knoten.ruf("getblockstats", h, ["feerate_percentiles"],
                               zeitlimit=VERLAUF_ZEITLIMIT)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.debug("Block %s ohne Gebuehrenwerte: %s", h, fehler)
            continue
        reihe = (werte or {}).get("feerate_percentiles") or []
        # Fuenf Werte: 10., 25., 50., 75., 90. Stelle. Uns interessiert die
        # Mitte -- was die mittlere Transaktion dieses Blocks gezahlt hat.
        if len(reihe) >= 3:
            try:
                saetze.append(float(reihe[2]))
            except (TypeError, ValueError):
                continue
    if len(saetze) < VERLAUF_MINDESTENS:
        return None
    saetze.sort()
    return {
        "bloecke": len(saetze),
        "tage": round(VERLAUF_BLOECKE / 144, 1),
        "unten": round(_stelle(saetze, 0.1), 1),
        "unteres_viertel": round(_stelle(saetze, GRENZE_GUENSTIG), 1),
        "mitte": round(_stelle(saetze, 0.5), 1),
        "oberes_viertel": round(_stelle(saetze, GRENZE_TEUER), 1),
        "oben": round(_stelle(saetze, 0.9), 1),
    }


def einordnung(satz: float, verlauf: Optional[Dict[str, Any]]) -> Optional[str]:
    """Guenstig, normal oder teuer -- gemessen an der eigenen letzten Woche."""
    if not verlauf or not satz:
        return None
    if satz <= verlauf["unteres_viertel"]:
        return "guenstig"
    if satz >= verlauf["oberes_viertel"]:
        return "teuer"
    return "normal"
