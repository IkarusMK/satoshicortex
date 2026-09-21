"""Den Mempool lesen, ohne ihn zu halten.

DER BEFUND VOM 21.09.2026, aus dem Betrieb: "wenn der mempool voll ist oder
fast voll ist kann ich keine kacheln mehr holen".

Die Kachelansicht holte ``getrawmempool True`` mit einem gewoehnlichen Aufruf
-- die ganze Antwort auf einmal. Nachgemessen mit Cores eigener Feldliste
(``rpc/mempool.cpp``, ``entryToJSON``):

=============  ===========  ==========================
Transaktionen  JSON         Spitze beim Einlesen
=============  ===========  ==========================
     10.000      4,8 MB       26 MB
     50.000     23,8 MB      134 MB
    150.000     71,4 MB      397 MB
=============  ===========  ==========================

Das Speicherlimit des ``app``-Containers steht auf 400M. Ein voller Mempool
hat also gereicht, um den Container vom OOM-Killer beenden zu lassen -- und
weil er ``restart: unless-stopped`` traegt, war danach die ganze Oberflaeche
kurz weg. Es fehlten nicht die Kacheln, es fehlte alles.

Hier wird deshalb dasselbe gemacht wie bei LNDs Netzgraph in
``gebuehren.py``: in Stuecken lesen und nebenher auswerten. Was im Speicher
bleibt, ist die AUSGABE (vier Zahlen je Transaktion) und nicht die Eingabe
(fuenfzehn Felder je Transaktion, als Python-Objekte).

Der Unterschied zu ``gebuehren.elemente``: dort ist die gesuchte Stelle eine
LISTE, hier ist sie ein OBJEKT, dessen Schluessel die txids sind. Es gibt
also Paare herauszugeben, nicht Eintraege.
"""
from __future__ import annotations

import codecs
import json
import logging
from typing import Any, Dict, Iterable, Iterator, List, Tuple

log = logging.getLogger(__name__)

# Die Notbremse. Ein Mempool von 300 MB -- Cores Vorgabe fuer maxmempool --
# ergibt als JSON grob 70 bis 100 MB. Wer mehr schickt, schickt nicht mehr
# den Mempool, und dann ist Abbrechen richtiger als Weiterlesen.
HOECHSTENS_BYTES = 256 * 1024 * 1024

# Das Feld, in dem bitcoind seine Antwort ablegt.
FELD = "result"


class MempoolZuGross(Exception):
    """Die Antwort sprengt jede plausible Groesse."""


class MempoolAbgerissen(Exception):
    """Die Leitung endete mitten im Dokument.

    Eigene Ausnahme, weil ein Abriss LAUT enden muss: eine halb gelesene
    Antwort sieht aus wie ein halb leerer Mempool, und daraus eine
    Gebuehrenschaetzung zu bauen waere schlimmer als gar keine.
    """


def begrenzt(brocken: Iterable[bytes],
             hoechstens: int = HOECHSTENS_BYTES) -> Iterator[bytes]:
    """Durchreichen -- aber mitzaehlen und rechtzeitig abbrechen."""
    gelesen = 0
    for stueck in brocken:
        gelesen += len(stueck)
        if gelesen > hoechstens:
            raise MempoolZuGross(
                f"mehr als {hoechstens // (1024 * 1024)} MB Mempool")
        yield stueck


def paare(brocken: Iterable[bytes],
          feld: str = FELD) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Die Schluessel-Wert-Paare EINES Objektfeldes, eines nach dem anderen.

    Gesucht wird der Schluessel auf der obersten Ebene. Herausgegeben wird
    jedes Paar einzeln, mit dem richtigen JSON-Leser geparst und nicht mit
    einem Suchmuster -- auf die Reihenfolge der Felder verlaesst sich hier
    nichts.

    Gearbeitet wird auf einem PUFFER mit Indizes, nicht auf Listen von
    Einzelzeichen. Der Unterschied ist nicht Geschmack: ein Ein-Zeichen-String
    kostet in Python rund fuenfzig Byte, und ein Mempool-Eintrag hat etwa
    sechshundert Zeichen. Zeichenweise gesammelt braucht das Lesen damit ein
    Vielfaches dessen, was der Eintrag selbst wiegt -- bei genau der Abfrage,
    derentwegen dieses Modul existiert.
    """
    entschluessler = codecs.getincrementaldecoder("utf-8")()
    puffer = ""
    i = 0

    # Zustand der Suche nach dem Feld
    tiefe = 0
    schluessel = ""
    warte_auf_doppelpunkt = False
    warte_auf_klammer = False
    sammeln = False

    # Zustand innerhalb des Objekts
    paarschluessel = ""
    wertanfang = -1
    werttiefe = 0
    warte_auf_paarwert = False

    # Textzustand -- gilt fuer beide Ebenen, weil zu jedem Zeitpunkt nur
    # eine von ihnen liest.
    in_text = False
    entwertet = False
    textanfang = -1

    for stueck in brocken:
        neues = entschluessler.decode(stueck)
        if not neues:
            continue
        # Verarbeitetes vorne abschneiden, damit der Puffer nicht mitwaechst.
        # Was noch gebraucht wird -- ein angefangener Text, ein angefangener
        # Wert -- bleibt stehen; sein Anfang ist der frueheste Index.
        behalten = min([x for x in (textanfang, wertanfang, i) if x >= 0])
        if behalten > 0:
            puffer = puffer[behalten:]
            i -= behalten
            if textanfang >= 0:
                textanfang -= behalten
            if wertanfang >= 0:
                wertanfang -= behalten
        puffer += neues

        while i < len(puffer):
            z = puffer[i]

            if in_text:
                if entwertet:
                    entwertet = False
                elif z == "\\":
                    entwertet = True
                elif z == '"':
                    in_text = False
                    roh = puffer[textanfang:i + 1]
                    textanfang = -1
                    if sammeln and not werttiefe:
                        paarschluessel = json.loads(roh)
                        warte_auf_paarwert = True
                    elif not sammeln and tiefe == 1:
                        schluessel = json.loads(roh)
                        warte_auf_doppelpunkt = True
                i += 1
                continue

            if werttiefe:
                if z == '"':
                    in_text = True
                    textanfang = i
                elif z in "{[":
                    werttiefe += 1
                elif z in "}]":
                    werttiefe -= 1
                    if werttiefe == 0:
                        yield paarschluessel, json.loads(
                            puffer[wertanfang:i + 1])
                        wertanfang = -1
                        paarschluessel = ""
                i += 1
                continue

            if sammeln:
                if warte_auf_paarwert:
                    if z.isspace() or z == ":":
                        i += 1
                        continue
                    warte_auf_paarwert = False
                    wertanfang = i
                    if z in "{[":
                        werttiefe = 1
                        i += 1
                        continue
                    # Ein flacher Wert. Im Mempool kommt das nicht vor;
                    # stillschweigend falsch zu lesen ist trotzdem keine
                    # Antwort darauf.
                    ende_flach = i
                    while ende_flach < len(puffer) and \
                            puffer[ende_flach] not in ",}":
                        ende_flach += 1
                    if ende_flach >= len(puffer):
                        break            # mehr Puffer holen
                    yield paarschluessel, json.loads(
                        puffer[wertanfang:ende_flach].strip())
                    wertanfang = -1
                    paarschluessel = ""
                    i = ende_flach
                    continue
                if z == '"':
                    in_text = True
                    textanfang = i
                elif z == "}":
                    # Das Objekt ist zu Ende. Was danach kommt -- "error",
                    # "id" -- interessiert niemanden mehr.
                    return
                i += 1
                continue

            # ---- noch auf der Suche nach dem Feld ----
            if warte_auf_doppelpunkt:
                if z.isspace():
                    i += 1
                    continue
                warte_auf_doppelpunkt = False
                if z == ":" and schluessel == feld:
                    warte_auf_klammer = True
                    i += 1
                    continue
            if warte_auf_klammer:
                if z.isspace():
                    i += 1
                    continue
                warte_auf_klammer = False
                if z == "{":
                    sammeln = True
                    i += 1
                    continue
                # Das Feld ist da, aber kein Objekt -- etwa "result": null,
                # wie bitcoind es bei einem Fehler schickt.
                return
            if z == '"':
                in_text = True
                textanfang = i
            elif z in "{[":
                tiefe += 1
            elif z in "}]":
                tiefe -= 1
            i += 1

    # Hier angekommen heisst: die Brocken sind ausgegangen, ohne dass das
    # Objekt je geschlossen wurde.
    if sammeln:
        raise MempoolAbgerissen(
            "die Mempool-Antwort endete mitten im Dokument")


# Was von jeder Transaktion uebrig bleibt: genau das, was die Kachelansicht
# rechnet. Vier Zahlen statt fuenfzehn Feldern.
#
#   satvb_paket  -- Gebuehrensatz des Pakets (Vorfahren mitgerechnet). Danach
#                   waehlt der Miner, also danach wird sortiert.
#   vsize        -- die eigene Groesse, sie bestimmt die Kachelflaeche.
#   satvb        -- der eigene Satz, er faerbt die Kachel.
def auswerten(brocken: Iterable[bytes]) -> List[Tuple[float, str, int, float]]:
    """Aus dem Strom die Liste, aus der die Kacheln entstehen.

    Rueckgabe je Transaktion: (satvb_paket, txid, vsize, satvb) -- absteigend
    nach satvb_paket, also in der Reihenfolge, in der ein Miner sie nimmt.
    """
    eintraege: List[Tuple[float, str, int, float]] = []
    for txid, e in paare(brocken):
        if not isinstance(e, dict):
            continue
        try:
            vsize = int(e.get("vsize") or 0)
        except (TypeError, ValueError):
            continue
        if vsize <= 0:
            continue
        gebuehren = e.get("fees") or {}
        if not isinstance(gebuehren, dict):
            gebuehren = {}
        try:
            basis = float(gebuehren.get("base") or 0.0) * 1e8
            vorfahren = float(gebuehren.get("ancestor") or 0.0) * 1e8
            vorfahrengroesse = int(e.get("ancestorsize") or vsize) or vsize
        except (TypeError, ValueError):
            continue
        eintraege.append(
            (vorfahren / vorfahrengroesse, txid, vsize, basis / vsize))
    eintraege.sort(key=lambda x: -x[0])
    return eintraege
