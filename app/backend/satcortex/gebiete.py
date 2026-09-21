"""Die Namen der Gebiete -- Bundeslaender, Kantone, Staaten, Provinzen.

Die Ortstabelle (geo.py) liefert zu einer Adresse eine GEBIETSNUMMER. Was
diese Nummer heisst und welche Umrisse zu ihr gehoeren, steht hier.

Erzeugt wird die Datei von tools/regionen_zuordnen.py aus zwei Quellen:
Natural Earth (die Umrisse) und der DB-IP-Liste (die Namen, die dort an den
IP-Bereichen haengen). Beide benennen dieselbe Region verschieden -- am
05.09.2026 gemessen passte bei Frankreich KEIN einziger Name woertlich --,
deshalb wird beim Erzeugen ueber die Koordinaten zugeordnet und nicht ueber
die Schreibweise. Hier wird das Ergebnis nur noch gelesen.

Ein Gebiet kann MEHRERE Umrisse haben: Natural Earth fuehrt Frankreich als
101 Departements, DB-IP als 13 Regionen. "Auvergne-Rhone-Alpes" ist damit
kein Umriss, sondern dreizehn -- und eingefaerbt wird, was die Quelle
wirklich hergibt, statt ein einzelnes Departement herauszugreifen und mehr
Genauigkeit zu behaupten, als da ist.

Fehlt die Datei, ist das kein Fehler: dann gibt es eben keine Gebiete, die
Karte bleibt bei den Laendern, und alles andere laeuft weiter.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

STANDARDPFAD = os.environ.get("GEBIETE_DATEI", "/opt/satcortex/regionen.json")


class Gebiete:
    """Nummer -> Land, Name, Umrisse."""

    def __init__(self, eintraege: List[Dict]):
        self._nach_nummer: Dict[int, Dict] = {}
        self._nach_land: Dict[str, List[Dict]] = {}
        for e in eintraege:
            nummer = int(e.get("n") or 0)
            if not nummer:
                continue
            self._nach_nummer[nummer] = e
            self._nach_land.setdefault(e.get("land", ""), []).append(e)

    def __len__(self) -> int:
        return len(self._nach_nummer)

    def eines(self, nummer: int) -> Optional[Dict]:
        return self._nach_nummer.get(int(nummer or 0))

    def eines_landes(self, land: str) -> List[Dict]:
        return self._nach_land.get((land or "").upper(), [])

    def laender(self) -> List[str]:
        return sorted(self._nach_land)


def lade(pfad: Optional[str] = None) -> Optional[Gebiete]:
    p = Path(pfad or STANDARDPFAD)
    if not p.exists():
        log.info("Keine Gebietsnamen unter %s -- die Karte bleibt bei den "
                 "Laendern.", p)
        return None
    try:
        daten = json.loads(p.read_text(encoding="utf-8"))
        eintraege = daten.get("gebiete")
        if not isinstance(eintraege, list) or not eintraege:
            raise ValueError("keine Gebiete darin")
    except (OSError, ValueError) as fehler:
        log.warning("Gebietsnamen %s unbrauchbar (%s) -- die Karte bleibt bei "
                    "den Laendern.", p, fehler)
        return None
    g = Gebiete(eintraege)
    log.info("Gebietsnamen geladen: %d Gebiete in %d Laendern.",
             len(g), len(g.laender()))
    return g
