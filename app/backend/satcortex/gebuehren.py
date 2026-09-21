"""Was das Netz fuers Weiterleiten nimmt -- gemessen, nicht behauptet.

DER ANLASS. In der Oberflaeche stand bis zum 18.09.2026 ein Satz: "Der
Netz-Median lag 2026 bei rund 143 ppm." Eine Zahl, die jemand einmal
nachgeschlagen und dann in den Quelltext geschrieben hat. Sie altert still --
niemand sieht ihr an, wann sie zuletzt gestimmt hat, und falsch wird sie ohne
ein einziges Warnzeichen. Dieselbe Fehlerklasse wie die eingefrorene
Boersen-Reihenfolge in kurs.py.

Der eigene Knoten kennt die Antwort selbst. LNDs DescribeGraph liefert jede
oeffentliche Kante des Netzes mit beiden Richtungslinien, und in jeder steht
"fee_rate_milli_msat". Das ist die Wahrheit aus erster Hand -- kein Explorer,
kein Dienst, keine fremde Zahl. Genau die Linie, die dieses Projekt sonst
ueberall faehrt.

WARUM STUECKWEISE GELESEN WIRD. DescribeGraph antwortet mit EINEM JSON-
Dokument ueber das ganze Netz. Bei rund 16.000 Knoten und 33.000 Kanaelen
sind das zweistellige Megabyte; durch json.loads geschickt wuerden daraus
mehrere hundert Megabyte Python-Objekte, und die Anwendung laeuft in einem
Container mit 400 MB Grenze. Sie wuerde also genau dann sterben, wenn das Netz
gross genug ist -- und das ist es heute schon.

Deshalb zerlegt "elemente" den Strom selbst: es sucht EIN Feld, gibt dessen
Listeneintraege einzeln heraus und vergisst jeden sofort wieder. Im Speicher
liegt nie mehr als eine Kante. Der uebrige Inhalt -- die "nodes"-Liste mit
ihren langen Merkmalstabellen -- rauscht vorbei, ohne je ein Objekt zu werden.

DIE FELDNAMEN SIND NACHGESCHLAGEN, nicht erinnert: lnrpc/lightning.proto am
Tag v0.21.3-beta, dieselbe Fassung, aus der auch tests/lnd_rest_routen.tsv
stammt. ChannelGraph traegt "nodes" (1) und "edges" (2); ChannelEdge traegt
"node1_pub", "node2_pub", "node1_policy", "node2_policy"; RoutingPolicy traegt
"fee_base_msat", "fee_rate_milli_msat" und "disabled". Die Tabelle dazu liegt
in tests/lnd_graph_felder.tsv, und ein Test haelt diese Datei und diesen Code
zusammen.

EIN PUNKT, DER LEICHT UEBERSEHEN WIRD: in der JSON-Abbildung von protobuf
fehlen Felder mit ihrem Vorgabewert. Eine Linie mit 0 ppm hat also unter
Umstaenden gar kein "fee_rate_milli_msat" -- und null ppm ist ein voellig
gewoehnlicher Wert. Wer das Feld als "fehlt also ueberspringen" liest, zaehlt
die guenstigsten Kanaele des Netzes nicht mit und bekommt einen zu hohen
Median. Hier heisst "fehlt" deshalb ueberall null, so wie protobuf es meint.
"""
from __future__ import annotations

import codecs
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional

log = logging.getLogger(__name__)

# Vier Wochen. Sie stehen NICHT still -- Aus dem Betrieb, 18.09.2026: "die 4 wochen
# sind ja auch nicht fest sondern aendern sich ja mit ne". Genau so: jeder
# neue Messtag schiebt den aeltesten aus dem Fenster.
FENSTER_TAGE = 28

# So viele Messtage muessen im Fenster liegen, bevor die Automatik ueberhaupt
# etwas anfasst. Mit zwei Tagen gaebe es kein Band, sondern zwei Punkte -- und
# ein Band aus zwei Punkten ist keine Absicherung, sondern eine Verkleidung.
MINDESTENS_TAGE = 7

# Unter diesem Abstand wird nicht nachgezogen. Jede Gebuehrenaenderung ist ein
# channel_update, das der Knoten ins ganze Netz ruft; wer wegen zwei ppm
# taeglich funkt, faellt bei den Gegenstellen unter deren Ratenbegrenzung und
# erreicht am Ende weniger als wer stillhaelt.
ABSTAND_PPM = 5

# Dieselbe absolute Grenze wie im Formular. Sie steht hier ein zweites Mal,
# weil die Automatik nicht durch das Formular geht.
HOECHSTSATZ_PPM = 10_000

# LND braucht fuer den ganzen Graphen ein paar Sekunden bis Minuten -- er
# serialisiert dabei zweistellige Megabyte. Einmal am Tag darf das dauern.
GRAPH_ZEITLIMIT_SEKUNDEN = 300.0

# Und eine Notbremse: laeuft der Graph unerwartet auf, wird abgebrochen statt
# gelesen, bis der Speicher voll ist. 512 MB sind rund das Zehnfache dessen,
# was heute zu erwarten ist.
GRAPH_HOECHSTENS_BYTES = 512 * 1024 * 1024

GRAPH_PFAD = "/v1/graph"

# Das eine Feld der Antwort, das uns angeht. Die "nodes"-Liste daneben ist die
# groessere -- sie laeuft vorbei, ohne je ein Objekt zu werden.
GRAPH_FELD = "edges"


class GraphZuGross(Exception):
    """Der Graph war groesser als die Notbremse erlaubt."""


class GraphAbgerissen(Exception):
    """Die Leitung endete mitten in der Liste.

    Das ist wichtiger, als es aussieht. Bricht die Verbindung ab, waehrend
    die Kanten gelesen werden, haette man eine HALBE Messung -- und die sieht
    einer ganzen zum Verwechseln aehnlich. Sie ginge in die Messreihe ein und
    verzoege das Vier-Wochen-Band wochenlang, ohne dass irgendwo ein Fehler
    stuende. Deshalb endet ein Abriss hier laut.
    """


def _zahl(wert: Any, standard: int = 0) -> int:
    """LND schickt 64-Bit-Zahlen als Zeichenkette. Beides muss hier ankommen."""
    if wert is None:
        return standard
    try:
        return int(wert)
    except (TypeError, ValueError):
        return standard


def _median(werte: List[int]) -> Optional[int]:
    if not werte:
        return None
    werte = sorted(werte)
    mitte = len(werte) // 2
    if len(werte) % 2:
        return werte[mitte]
    return (werte[mitte - 1] + werte[mitte]) // 2


def _quantil(werte: List[int], anteil: float) -> Optional[int]:
    """Das untere Viertel und das obere -- die Spanne, in der das Netz lebt.

    Min und Max waeren hier wertlos: es gibt Linien mit null ppm und Linien
    mit Fantasiepreisen im Millionenbereich, durch die nie jemand routet.
    """
    if not werte:
        return None
    werte = sorted(werte)
    stelle = int(anteil * (len(werte) - 1))
    return werte[max(0, min(len(werte) - 1, stelle))]


def heute(zeit_s: Optional[float] = None) -> str:
    """Der Tag in UTC, als YYYY-MM-DD.

    UTC und nicht Ortszeit: sonst haette die Umstellung auf Sommerzeit einen
    Tag mit zwei Messungen und einen mit keiner, und das Fenster waere still
    um einen Tag daneben.
    """
    punkt = datetime.now(timezone.utc) if zeit_s is None \
        else datetime.fromtimestamp(zeit_s, timezone.utc)
    return punkt.strftime("%Y-%m-%d")


def begrenzt(brocken: Iterable[bytes],
             hoechstens: int = GRAPH_HOECHSTENS_BYTES) -> Iterator[bytes]:
    """Durchreichen -- aber mitzaehlen und rechtzeitig abbrechen."""
    gelesen = 0
    for stueck in brocken:
        gelesen += len(stueck)
        if gelesen > hoechstens:
            raise GraphZuGross(
                f"mehr als {hoechstens // (1024 * 1024)} MB Netzgraph")
        yield stueck


def elemente(brocken: Iterable[bytes], feld: str) -> Iterator[Dict[str, Any]]:
    """Die Listeneintraege EINES Feldes aus einem grossen JSON-Dokument.

    Gesucht wird der Schluessel auf der obersten Ebene; alles andere -- auch
    eine zweite, viel groessere Liste daneben -- laeuft vorbei, ohne dass ein
    Objekt entsteht. Herausgegeben wird jeder Eintrag einzeln, geparst mit
    dem richtigen JSON-Leser und nicht mit einem Suchmuster: auf die
    Reihenfolge der Felder verlaesst sich hier nichts.
    """
    entschluessler = codecs.getincrementaldecoder("utf-8")()
    tiefe = 0
    in_text = False
    entwertet = False
    text: List[str] = []
    schluessel = ""
    warte_auf_doppelpunkt = False
    warte_auf_klammer = False
    sammeln = False
    element: List[str] = []
    elementtiefe = 0
    element_in_text = False
    element_entwertet = False
    fertig = False

    for stueck in brocken:
        for z in entschluessler.decode(stueck):
            if sammeln:
                # ---- innerhalb der gesuchten Liste ----
                if elementtiefe:
                    element.append(z)
                    if element_in_text:
                        if element_entwertet:
                            element_entwertet = False
                        elif z == "\\":
                            element_entwertet = True
                        elif z == '"':
                            element_in_text = False
                    elif z == '"':
                        element_in_text = True
                    elif z in "{[":
                        elementtiefe += 1
                    elif z in "}]":
                        elementtiefe -= 1
                        if elementtiefe == 0:
                            yield json.loads("".join(element))
                            element = []
                    continue
                if z in "{[":
                    elementtiefe = 1
                    element = [z]
                elif z == "]":
                    # Die Liste ist zu Ende. Was danach kommt, interessiert
                    # niemanden mehr -- und der Rest der Leitung wird nicht
                    # mehr gelesen.
                    sammeln = False
                    fertig = True
                    return
                continue

            # ---- noch auf der Suche ----
            if in_text:
                text.append(z)
                if entwertet:
                    entwertet = False
                elif z == "\\":
                    entwertet = True
                elif z == '"':
                    in_text = False
                    if tiefe == 1:
                        schluessel = json.loads("".join(text))
                        warte_auf_doppelpunkt = True
                continue
            if warte_auf_doppelpunkt:
                if z.isspace():
                    continue
                warte_auf_doppelpunkt = False
                if z == ":" and schluessel == feld:
                    warte_auf_klammer = True
                    continue
            if warte_auf_klammer:
                if z.isspace():
                    continue
                warte_auf_klammer = False
                if z == "[":
                    tiefe += 1
                    sammeln = True
                    continue
            if z == '"':
                in_text = True
                text = ['"']
            elif z in "{[":
                tiefe += 1
            elif z in "}]":
                tiefe -= 1
    if sammeln and not fertig:
        raise GraphAbgerissen(
            "die Liste \"%s\" endete ohne schliessende Klammer" % feld)


def _linie(politik: Any) -> Optional[Dict[str, int]]:
    """Eine Richtungslinie als zwei Zahlen -- oder nichts.

    "Nichts" heisst: fuer diese Richtung kennt der Graph keine Linie. Das ist
    etwas anderes als "null ppm" und darf nicht mitgezaehlt werden.
    """
    if not isinstance(politik, dict):
        return None
    if politik.get("disabled"):
        return None
    return {"satz_ppm": _zahl(politik.get("fee_rate_milli_msat")),
            "basis_msat": _zahl(politik.get("fee_base_msat"))}

# Die Stufen, auf die die Saetze verteilt werden. Runde Grenzen, fest
# gewaehlt -- nicht aus der Verteilung selbst gerechnet. Eine Stufe, die
# jeden Tag woanders liegt, kann man nicht mit gestern vergleichen.
#
# Warum ueberhaupt Stufen: bis zum 21.09.2026 stand unter dem Median ein
# fuenfzeiliger Absatz, der ERKLAERTE, dass die Verteilung schief ist. Der
# Betreiber dazu: "was das den bitte fuer ein riesen text ??". Er hat recht
# -- fuenf Prozentzahlen zeigen dieselbe Schiefe auf einen Blick, und sie
# sagen zusaetzlich, WO die Masse liegt. Das stand in dem Absatz nicht.
STUFEN_GRENZEN = (1, 10, 100, 1000)


def verteilung(saetze: List[int]) -> List[Dict[str, Any]]:
    """Wie sich die Saetze auf die Stufen verteilen, in ganzen Prozent.

    Die Anteile ergeben zusammen GENAU hundert. Einzeln gerundet taeten sie
    das naemlich nicht -- drei Drittel ergaeben 99 --, und unter einer Zeile,
    die "so verteilt sich das Netz" heisst, ist das ein Widerspruch, den der
    Leser findet und nicht aufloesen kann. Die uebrigen Prozentpunkte gehen
    deshalb an die groessten Nachkommateile (die uebliche Sitzverteilung
    nach groesstem Rest).

    Leere Stufen bleiben in der Liste stehen: die Form soll von Tag zu Tag
    dieselbe Gestalt haben, auch wenn eine Stufe gerade niemanden enthaelt.
    """
    if not saetze:
        return []
    koerbe = [0] * (len(STUFEN_GRENZEN) + 1)
    for satz in saetze:
        stufe = 0
        while stufe < len(STUFEN_GRENZEN) and satz >= STUFEN_GRENZEN[stufe]:
            stufe += 1
        koerbe[stufe] += 1

    roh = [k * 100.0 / len(saetze) for k in koerbe]
    anteile = [int(x) for x in roh]
    nach = sorted(range(len(roh)), key=lambda i: anteile[i] - roh[i])
    for i in nach[:100 - sum(anteile)]:
        anteile[i] += 1

    von = (0,) + STUFEN_GRENZEN
    return [{
        "von": von[i],
        # Die oberste Stufe ist offen: nach oben gibt es im Lightning-Netz
        # keine Grenze, und "1000 bis 2000" waere schlicht falsch.
        "bis": (STUFEN_GRENZEN[i] - 1) if i < len(STUFEN_GRENZEN) else None,
        "anteil": anteile[i],
    } for i in range(len(anteile))]


def auswerten(kanten: Iterable[Dict[str, Any]],
              eigene_kennung: str = "") -> Dict[str, Any]:
    """Aus den Kanten des Graphen die Zahlen machen, die man ansehen kann.

    Abgeschaltete Richtungen bleiben draussen: durch sie geht nichts, ihr
    Preis ist also keiner. Sie werden trotzdem gezaehlt, damit die Zahl
    daneben erklaerbar bleibt.
    """
    saetze: List[int] = []
    basen: List[int] = []
    eigene: List[Dict[str, int]] = []
    kanaele = 0
    abgeschaltet = 0
    for kante in kanten:
        kanaele += 1
        for seite, name in (("node1_pub", "node1_policy"),
                            ("node2_pub", "node2_policy")):
            politik = kante.get(name)
            if isinstance(politik, dict) and politik.get("disabled"):
                abgeschaltet += 1
            linie = _linie(politik)
            if linie is None:
                continue
            saetze.append(linie["satz_ppm"])
            basen.append(linie["basis_msat"])
            if eigene_kennung and kante.get(seite) == eigene_kennung:
                eigene.append(linie)
    return {
        "median_ppm": _median(saetze),
        "stufen": verteilung(saetze),
        "p25_ppm": _quantil(saetze, 0.25),
        "p75_ppm": _quantil(saetze, 0.75),
        "basis_median_msat": _median(basen),
        "linien": len(saetze),
        "abgeschaltet": abgeschaltet,
        "kanaele": kanaele,
        "eigen": {
            "satz_ppm": _median([e["satz_ppm"] for e in eigene]),
            "basis_msat": _median([e["basis_msat"] for e in eigene]),
            "linien": len(eigene),
        },
    }


def messen(knoten, eigene_kennung: str = "",
           zeitlimit: float = GRAPH_ZEITLIMIT_SEKUNDEN,
           hoechstens_bytes: int = GRAPH_HOECHSTENS_BYTES) -> Dict[str, Any]:
    """Einmal den ganzen Graphen lesen und die Gebuehren daraus ziehen."""
    brocken = begrenzt(knoten.brocken(GRAPH_PFAD, zeitlimit=zeitlimit),
                       hoechstens_bytes)
    return auswerten(elemente(brocken, GRAPH_FELD), eigene_kennung)


def band(verlauf: List[Dict[str, Any]], ohne_tag: str = "") -> Dict[str, Any]:
    """Ober- und Untergrenze aus den letzten vier Wochen.

    OHNE den heutigen Tag, und das ist der ganze Punkt. Der Betreiber will das Band
    als Absicherung: "Obergrenze ist max wert der letzten 4 wochen und
    untergrenze ist dann min wert der letzten 4 wochen". Zaehlte die heutige
    Messung mit, laege sie IMMER innerhalb ihres eigenen Bandes -- eine
    Messung, die einmal danebengeht, wuerde sich ihre Grenze selbst
    aufmachen und ungebremst durchschlagen. Genau davor soll das Band
    schuetzen, also gehoert der heutige Tag nicht hinein.
    """
    werte = [int(z["median_ppm"]) for z in verlauf
             if z.get("median_ppm") is not None and z.get("tag") != ohne_tag]
    if not werte:
        return {"tage": 0, "unten_ppm": None, "oben_ppm": None}
    return {"tage": len(werte), "unten_ppm": min(werte),
            "oben_ppm": max(werte)}


def vorschlag(heute_ppm: Optional[int], grenzen: Dict[str, Any],
              jetzt_ppm: Optional[int] = None) -> Dict[str, Any]:
    """Was die Automatik setzen wuerde -- und warum.

    Rechnen und Handeln sind hier getrennt: diese Funktion fasst nichts an.
    Sie liefert eine Zahl und einen Grund, und die Oberflaeche zeigt beides,
    auch wenn die Automatik aus ist. Man soll sehen koennen, was sie taete,
    bevor man sie einschaltet.
    """
    if heute_ppm is None:
        return {"satz_ppm": None, "grund": "keine_messung", "handeln": False}
    ziel = max(0, min(HOECHSTSATZ_PPM, int(heute_ppm)))
    tage = int(grenzen.get("tage") or 0)
    if tage < MINDESTENS_TAGE:
        return {"satz_ppm": ziel, "grund": "sammelt_noch", "handeln": False,
                "tage": tage, "braucht_tage": MINDESTENS_TAGE}
    unten = grenzen.get("unten_ppm")
    oben = grenzen.get("oben_ppm")
    grund = "median"
    if oben is not None and ziel > oben:
        ziel, grund = int(oben), "gedeckelt"
    elif unten is not None and ziel < unten:
        ziel, grund = int(unten), "angehoben"
    if jetzt_ppm is not None and abs(ziel - int(jetzt_ppm)) < ABSTAND_PPM:
        return {"satz_ppm": ziel, "grund": "unveraendert", "handeln": False,
                "tage": tage}
    return {"satz_ppm": ziel, "grund": grund, "handeln": True, "tage": tage}
