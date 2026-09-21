#!/usr/bin/env python3
"""Die Regionsnamen der IP-Liste auf die Umrisse von Natural Earth abbilden.

Warum das ueberhaupt noetig ist: die beiden Quellen benennen dieselbe Region
verschieden. Am 05.09.2026 nachgemessen, Anteil der Zeilen, deren Regionsname
woertlich passt:

    Niederlande  100,0 %      Deutschland  86,5 %
    USA          100,0 %      Oesterreich  77,6 %
    Schweiz       63,5 %      FRANKREICH    0,0 %

Frankreich trifft KEIN einziges Mal -- die Gebietsreform von 2016 hat die
Regionen umbenannt, DB-IP fuehrt die neuen, Natural Earth teils die alten.
Wer hier auf Namen baut, bekommt eine Karte, auf der Frankreich leer bleibt,
ohne dass irgendwo ein Fehler stuende.

Also drei Stufen, und die zweite ist die, die es rettet:

  1. Name woertlich (auch ueber name/name_de/name_en und ohne Akzente).
  2. PUNKTPROBE: die Koordinaten, die DB-IP zu diesem Namen nennt, werden
     gegen die Umrisse geprueft (Punkt-im-Polygon). Damit ist die Zuordnung
     von der Schreibweise unabhaengig.
  3. Bleibt es offen, entscheidet die naechstgelegene Region desselben Landes
     -- und wenn auch das nicht geht, bleibt es beim Land allein.

Eine IP-Region deckt manchmal MEHRERE Umrisse ab
------------------------------------------------
Natural Earth fuehrt Frankreich als 101 Departements, DB-IP als 13 Regionen.
"Auvergne-Rhone-Alpes" ist also nicht EIN Umriss, sondern zwoelf. Der erste
Anlauf nahm den Umriss, in dem der Schwerpunkt liegt -- damit haette die
Karte ein einzelnes Departement eingefaerbt und behauptet, der Knoten stehe
dort. Das waere praeziser gewesen, als wir wissen koennen.

Deshalb ist eine Zuordnung eine LISTE von Umrissen: geprueft werden bis zu
PROBEN verschiedene Koordinaten je Name, und jeder Umriss, der eine davon
enthaelt, gehoert dazu. Bei Bayern ist das Ergebnis ein Umriss, bei
Auvergne-Rhone-Alpes sind es zwoelf -- und eingefaerbt wird, was die Quelle
wirklich hergibt.

Das Ergebnis liegt im Repo (app/data/regionen.json), wie die Umrisse auch:
Regionsgrenzen aendern sich nicht monatlich, und so ist nachlesbar, was
ausgeliefert wird. Taucht in einer neueren IP-Liste ein unbekannter Name auf,
faellt er auf das Land zurueck -- nie auf eine falsche Region.
"""
from __future__ import annotations

import csv
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def schlicht(text: str) -> str:
    """Kleinschreibung, ohne Akzente, ohne Beiwerk.

    "Baden-Wurttemberg" und "Baden-Württemberg" sind dieselbe Region; DB-IP
    schreibt mal so, mal so. Ebenso "State of Vienna" und "Wien".
    """
    ohne = unicodedata.normalize("NFKD", text or "")
    ohne = "".join(z for z in ohne if not unicodedata.combining(z))
    ohne = ohne.casefold().replace("-", " ").replace("'", "")
    for weg in ("state of ", "province of ", "city state ",
                "free and hanseatic city of ", "free hanseatic city of ",
                "region of ", "canton of ", "the "):
        if ohne.startswith(weg):
            ohne = ohne[len(weg):]
    return " ".join(ohne.split())


def _ringe(geometrie: Dict) -> List[List]:
    art = geometrie.get("type")
    if art == "Polygon":
        return list(geometrie.get("coordinates", []))
    if art == "MultiPolygon":
        ringe: List[List] = []
        for teil in geometrie.get("coordinates", []):
            ringe.extend(teil)
        return ringe
    return []


def im_polygon(lon: float, lat: float, ring: List) -> bool:
    """Strahlenverfahren. Ungerade Zahl von Schnitten heisst: drinnen."""
    drin = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            schnitt = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < schnitt:
                drin = not drin
        j = i
    return drin


class Region:
    __slots__ = ("nummer", "land", "iso", "de", "en", "schlicht_name",
                 "ringe", "kasten", "mitte")

    def __init__(self, nummer: int, land: str, p: Dict, geometrie: Dict):
        self.nummer = nummer
        self.land = land
        self.iso = (p.get("iso_3166_2") or "").strip()
        self.en = p.get("name_en") or p.get("name") or "?"
        self.de = p.get("name_de") or p.get("name") or self.en
        # Das SCHLICHTE "name" gehoert dazu, und es zu vergessen kostete
        # Bremen: Natural Earth fuehrt es als name "Bremen", name_de "Freie
        # Hansestadt Bremen", name_en "Free Hanseatic Bremen". Ohne das erste
        # traf der Namensvergleich nicht, und der Schwerpunkt der beiden
        # Exklaven Bremen und Bremerhaven liegt DAZWISCHEN -- also in
        # Niedersachsen. Bremer Knoten waeren still in Niedersachsen gelandet.
        self.schlicht_name = p.get("name") or ""
        self.ringe = [[(float(q[0]), float(q[1])) for q in r
                       if isinstance(q, (list, tuple)) and len(q) >= 2]
                      for r in _ringe(geometrie)]
        self.ringe = [r for r in self.ringe if len(r) >= 3]
        punkte = [q for r in self.ringe for q in r]
        if punkte:
            self.kasten = (min(q[0] for q in punkte), min(q[1] for q in punkte),
                           max(q[0] for q in punkte), max(q[1] for q in punkte))
            self.mitte = (sum(q[0] for q in punkte) / len(punkte),
                          sum(q[1] for q in punkte) / len(punkte))
        else:
            self.kasten = None
            self.mitte = None

    def enthaelt(self, lon: float, lat: float) -> bool:
        if not self.kasten:
            return False
        x0, y0, x1, y1 = self.kasten
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            return False        # der Kasten spart die teure Pruefung
        return any(im_polygon(lon, lat, r) for r in self.ringe)


def lies_regionen(quelle: Path) -> Tuple[List[Region], Dict[str, List[Region]]]:
    daten = json.loads(quelle.read_text(encoding="utf-8"))
    alle: List[Region] = []
    je_land: Dict[str, List[Region]] = defaultdict(list)
    for objekt in daten.get("features", []):
        p = objekt.get("properties", {})
        land = (p.get("iso_a2") or "").strip().upper()
        if len(land) != 2:
            continue
        # Nummer 0 bleibt frei: sie heisst "keine Region bekannt".
        r = Region(len(alle) + 1, land, p, objekt.get("geometry") or {})
        if not r.ringe:
            continue
        alle.append(r)
        je_land[land].append(r)
    return alle, je_land


# Wie viele verschiedene Orte je Name geprueft werden. Genug, um bei einer
# franzoesischen Region alle Departements zu treffen; wenig genug, dass die
# Punkt-im-Polygon-Pruefung in Sekunden statt Stunden laeuft.
PROBEN = 400

# Auf welches Raster die Proben gerundet werden, bevor sie als "verschieden"
# gelten. 0,25 Grad sind rund 28 Kilometer -- feiner braucht es nicht, um ein
# Departement zu treffen.
RASTER = 0.25


def sammle_namen(liste: Path):
    """(Land, Regionsname) -> (Zeilen, Proben als Liste von (lon, lat))."""
    zahl: Dict[Tuple[str, str], int] = defaultdict(int)
    proben: Dict[Tuple[str, str], Dict[Tuple[int, int], Tuple[float, float]]] = \
        defaultdict(dict)
    with liste.open(newline="", encoding="utf-8", errors="replace") as f:
        for z in csv.reader(f):
            if len(z) < 8:
                continue
            land, region = z[3].strip().upper(), z[4].strip()
            if len(land) != 2 or not region:
                continue
            try:
                lat, lon = float(z[6]), float(z[7])
            except ValueError:
                continue
            schluessel = (land, region)
            zahl[schluessel] += 1
            eimer = proben[schluessel]
            if len(eimer) < PROBEN:
                eimer.setdefault((round(lon / RASTER), round(lat / RASTER)),
                                 (lon, lat))
    return {k: (zahl[k], list(proben[k].values())) for k in zahl}


def ordne_zu(liste: Path, umrisse: Path, ziel: Path) -> None:
    alle, je_land = lies_regionen(umrisse)
    nach_name: Dict[str, Dict[str, Region]] = defaultdict(dict)
    for r in alle:
        for name in (r.schlicht_name, r.en, r.de, r.iso):
            if name:
                nach_name[r.land].setdefault(schlicht(name), r)

    namen = sammle_namen(liste)
    # Die Nummer ist ab hier die eines GEBIETS -- also dessen, was DB-IP eine
    # Region nennt. Ein Gebiet zeigt auf einen oder mehrere Umrisse.
    gebiete: List[Dict] = []
    nach_gebiet: Dict[str, int] = {}
    # Umrissmenge -> Gebietsnummer, damit zwei Schreibweisen desselben
    # Bundeslands nicht zwei Gebiete werden.
    nach_umriss: Dict = {}
    wege = {"name": 0, "punktprobe": 0, "naechste": 0, "offen": 0}
    zeilen = {"name": 0, "punktprobe": 0, "naechste": 0, "offen": 0}

    for (land, region), (anzahl, proben) in sorted(namen.items()):
        treffer: List[Region] = []
        weg = "name"
        einer = nach_name.get(land, {}).get(schlicht(region))
        if einer is not None:
            treffer = [einer]
        else:
            weg = "punktprobe"
            gefunden = {}
            for lon, lat in proben:
                for r in je_land.get(land, ()):
                    if r.nummer not in gefunden and r.enthaelt(lon, lat):
                        gefunden[r.nummer] = r
                        break
            treffer = [gefunden[n] for n in sorted(gefunden)]
        if not treffer and proben:
            kandidaten = [r for r in je_land.get(land, ()) if r.mitte]
            if kandidaten:
                lon = sum(p[0] for p in proben) / len(proben)
                lat = sum(p[1] for p in proben) / len(proben)
                treffer = [min(kandidaten,
                               key=lambda r: (r.mitte[0] - lon) ** 2
                               + (r.mitte[1] - lat) ** 2)]
                weg = "naechste"
        if not treffer:
            wege["offen"] += 1
            zeilen["offen"] += anzahl
            continue
        # Der angezeigte Name: bei genau einem Umriss der von Natural Earth --
        # der ist auf Deutsch da ("Bayern" statt "Bavaria"). Bei mehreren
        # nimmt keiner von ihnen das Ganze vorweg, dann gilt der Name der
        # IP-Liste ("Auvergne-Rhone-Alpes").
        if len(treffer) == 1:
            de, en = treffer[0].de, treffer[0].en
        else:
            de = en = region
        # Mehrere Schreibweisen, EIN Gebiet. DB-IP fuehrt Berlin als "Berlin"
        # und als "State of Berlin", Bremen sogar dreifach -- und beide zeigen
        # auf denselben Umriss. Ohne diese Zusammenfassung stuende das
        # Bundesland zweimal in der Liste, mit auf zwei Zeilen verteilten
        # Zahlen, und die Karte faerbte es nach der zufaellig letzten davon.
        # Am 06.09.2026 nachgezaehlt: 467 Umrissmengen waren mehrfach
        # vergeben, betroffen 1.187 von 3.839 Gebieten -- fast ein Drittel.
        iso = [r.iso for r in treffer if r.iso]
        schluessel = (land, tuple(sorted(iso))) if iso else None
        if schluessel is not None and schluessel in nach_umriss:
            nummer = nach_umriss[schluessel]
        else:
            gebiete.append({
                "n": len(gebiete) + 1, "land": land, "de": de, "en": en,
                "iso": iso,
            })
            nummer = len(gebiete)
            if schluessel is not None:
                nach_umriss[schluessel] = nummer
        nach_gebiet[f"{land}|{region}"] = nummer
        wege[weg] += 1
        zeilen[weg] += anzahl

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps({
        "quelle": "ne_10m_admin_1_states_provinces (Natural Earth) "
                  "+ dbip-city-lite (DB-IP, CC BY 4.0)",
        "gebiete": gebiete,
        "namen": nach_gebiet,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    gesamt = sum(zeilen.values()) or 1
    mehrfach = sum(1 for g in gebiete if len(g["iso"]) > 1)
    print(f"{ziel}: {len(gebiete)} Gebiete aus {len(alle)} Umrissen, "
          f"davon {mehrfach} ueber mehrere Umrisse, "
          f"{ziel.stat().st_size / 1024:.0f} kB")
    for weg in ("name", "punktprobe", "naechste", "offen"):
        print(f"  ueber {weg:12} {wege[weg]:>5} Namen, "
              f"{zeilen[weg] / gesamt * 100:5.1f} % der Zeilen")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Aufruf: regionen_zuordnen.py <dbip-city.csv> "
                         "<ne_10m_admin_1.geojson> <ziel.json>")
    ordne_zu(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
