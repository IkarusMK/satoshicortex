"""Zu einer IP-Adresse das Land nachschlagen -- ohne jemanden zu fragen.

Die Karte braucht zu jeder Adresse, die unser Knoten kennt, einen Ort. Der
bequeme Weg waere ein Online-Dienst. Der bekaeme damit unsere komplette
Nachbarliste -- also genau die Auskunft, die wir bei der Versionsabfrage schon
hinter Tor verstecken. Hier waere sie noch heikler, weil es um Adressen geht,
mit denen wir tatsaechlich sprechen.

Deshalb liegt die Tabelle fertig im Abbild (tools/geo_bauen.py baut sie beim
Bauen aus der freien DB-IP-Liste). Im Betrieb geht keine einzige Anfrage
hinaus.

Fehlt die Datei, ist das kein Fehler: dann gibt es eben keine Laender, die
Karte sagt das, und alles andere laeuft weiter. Ein Abbild ohne Tabelle soll
nicht am Start scheitern.

Genauigkeit: Land und GEBIET, nicht Stadt.

Das Gebiet ist das, was DB-IP eine Region nennt und was auf der Karte ein
Bundesland, ein Kanton, ein Staat oder eine Provinz ist. Aus dem Betrieb, am
05.09.2026: "wo genau in Bayern ist auch egal, es sollte halt nur Bayern
sein, welcher Ort genau sollte nicht interessieren." Genau diese Grenze ist
hier gezogen -- und sie ist auch die, die die freie DB-IP-Liste ehrlich
hergibt: ein Punkt laege ohnehin beim Rechenzentrum, nicht bei einem
Menschen.

Der Preis steht in der Datei: 41 MB statt 9. Gelesen wird sie deshalb ueber
mmap statt in den Speicher kopiert -- ein Nachschlagen liest zwei bis drei
Seiten, und der Rest bleibt auf der Platte. Bei IPv6 wird auf /64 gerundet,
das kleinste Netz, das ueberhaupt vergeben wird.
"""
from __future__ import annotations

import bisect
import ipaddress
import logging
import mmap
import os
import struct
import sys
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

KENNUNG = b"SATGEO03"
STANDARDPFAD = os.environ.get("GEO_DATEI", "/opt/satcortex/geo.dat")

# DB-IP kennzeichnet damit alles, was keinem Land zugeordnet ist -- private
# Bereiche, Reserviertes, Unbekanntes. Als Land taugt das nicht.
OHNE_LAND = "ZZ"


class Tabelle:
    """Die Nachschlagetabelle. Einmal geoeffnet, oft gefragt.

    Die Datei bleibt liegen, wo sie ist: gelesen wird ueber mmap, und die
    Speicheransichten zeigen direkt hinein. Bei 41 MB ist das der Unterschied
    zwischen "kostet nichts" und "kostet ein Zehntel des Speichers, den der
    Container ueberhaupt haben darf".
    """

    def __init__(self, karte, a4, l4, g4, a6, l6, g6, stand: str = ""):
        self._karte = karte              # festhalten: sonst wird sie geschlossen
        self._a4, self._l4, self._g4 = a4, l4, g4
        self._a6, self._l6, self._g6 = a6, l6, g6
        # Jahrgang der Liste. Gehoert in die Oberflaeche: eine alte Liste
        # ordnet still falsch zu, und DB-IP steht unter CC BY -- die Herkunft
        # muss ohnehin genannt werden.
        self.stand = stand

    def __len__(self) -> int:
        return len(self._a4) + len(self._a6)

    def land(self, adresse: str) -> Optional[str]:
        """Laenderkuerzel -- oder None.

        None heisst: keine IP-Adresse (Onion, I2P), nicht in der Tabelle, oder
        ausdruecklich keinem Land zugeordnet. Die Karte zaehlt alle drei
        Faelle sichtbar, statt sie verschwinden zu lassen.
        """
        return self.ort(adresse)[0]

    def ort(self, adresse: str) -> Tuple[Optional[str], int]:
        """(Laenderkuerzel, Gebietsnummer). Gebiet 0 heisst: keines bekannt.

        Beides in EINEM Nachschlagen. Zweimal zu suchen waere nicht nur
        doppelt so teuer, sondern koennte auch zwei verschiedene Zeilen
        treffen, wenn die Tabelle dazwischen getauscht wuerde -- und dann
        stuende ein Gebiet neben einem Land, in dem es gar nicht liegt.
        """
        try:
            wert = ipaddress.ip_address((adresse or "").strip())
        except ValueError:
            return None, 0                   # .onion, .i2p, Unsinn

        if wert.version == 6:
            # Manche Knoten melden IPv4 in IPv6-Schreibweise. Die gehoert in
            # die IPv4-Tabelle, sonst faellt sie stumm heraus.
            eingebettet = wert.ipv4_mapped
            if eingebettet is not None:
                return self._suche(int(eingebettet), self._a4, self._l4, self._g4)
            return self._suche(int(wert) >> 64, self._a6, self._l6, self._g6)
        return self._suche(int(wert), self._a4, self._l4, self._g4)

    @staticmethod
    def _suche(zahl: int, anfaenge, laender, gebiete) -> Tuple[Optional[str], int]:
        # Der letzte Bereich, dessen Anfang nicht ueber der Zahl liegt. Ein
        # Ende gibt es nicht: die Bereiche der Quelle schliessen lueckenlos
        # aneinander an (beim Bauen geprueft), also reicht der naechste
        # Anfang als Grenze.
        i = bisect.bisect_right(anfaenge, zahl) - 1
        if i < 0:
            return None, 0
        kuerzel = bytes(laender[i * 2:i * 2 + 2]).decode("ascii", "replace")
        if kuerzel == OHNE_LAND:
            return None, 0
        return kuerzel, int(gebiete[i])


def _sicht(karte, versatz: int, anzahl: int, format_zeichen: str, breite: int):
    """Ein Stueck der Datei als Zahlenfolge -- ohne es zu kopieren."""
    return memoryview(karte)[versatz:versatz + anzahl * breite].cast(format_zeichen)


def lade(pfad: Optional[str] = None) -> Optional[Tabelle]:
    """Die Tabelle oeffnen. None, wenn es sie nicht gibt oder sie unbrauchbar ist."""
    p = Path(pfad or STANDARDPFAD)
    if not p.exists():
        log.info("Keine Ortstabelle unter %s -- die Karte bleibt ohne Laender.", p)
        return None
    if sys.byteorder != "little":
        # Die Datei ist Little-Endian, und memoryview.cast liest in der
        # Reihenfolge der Maschine. Auf einer Big-Endian-Maschine kaeme
        # stiller Unsinn heraus -- lieber gar keine Karte als eine falsche.
        log.warning("Ortstabelle wird auf Big-Endian nicht gelesen.")
        return None
    karte = None
    try:
        datei = p.open("rb")
        try:
            karte = mmap.mmap(datei.fileno(), 0, access=mmap.ACCESS_READ)
        finally:
            # Die Abbildung haelt die Datei offen, der Deskriptor wird nicht
            # mehr gebraucht.
            datei.close()
        if karte[:8] != KENNUNG:
            raise ValueError("unbekannte Kennung")
        stand = bytes(karte[8:16]).rstrip(b"\0").decode("ascii", "replace")
        n4, n6 = struct.unpack_from("<II", karte, 16)

        erwartet = 24 + n4 * 8 + n6 * 12
        if len(karte) < erwartet:
            raise ValueError("Datei ist unvollstaendig")

        v = 24
        a4 = _sicht(karte, v, n4, "I", 4); v += n4 * 4
        l4 = memoryview(karte)[v:v + n4 * 2]; v += n4 * 2
        g4 = _sicht(karte, v, n4, "H", 2); v += n4 * 2
        a6 = _sicht(karte, v, n6, "Q", 8); v += n6 * 8
        l6 = memoryview(karte)[v:v + n6 * 2]; v += n6 * 2
        g6 = _sicht(karte, v, n6, "H", 2); v += n6 * 2
    except (OSError, ValueError, struct.error) as fehler:
        # Eine kaputte Tabelle darf die Anwendung nicht am Start hindern.
        if karte is not None:
            karte.close()
        log.warning("Ortstabelle %s unbrauchbar (%s) -- die Karte bleibt ohne "
                    "Laender.", p, fehler)
        return None

    log.info("Ortstabelle geladen: %d Bereiche, Stand %s.", n4 + n6,
             stand or "unbekannt")
    return Tabelle(karte, a4, l4, g4, a6, l6, g6, stand)
