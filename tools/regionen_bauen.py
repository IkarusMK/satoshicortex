#!/usr/bin/env python3
"""Aus Natural-Earth-Umrissen je Land eine Regionskarte bauen.

Gewuenscht war: in der Weltkarte auf ein Land klicken, es wird gross, und
darin sind die Verwaltungseinheiten zu sehen, samt der Knoten, mit denen
dieser Knoten verbunden ist. Und zwar fuer die ganze Welt, nicht nur fuer
ein Land -- Australien mit seinen Bundesstaaten genauso wie
oder Afrika."

Laeuft von Hand wie karte_bauen.py, das Ergebnis liegt im Repo. Eine Datei je
Land unter app/web/regionen/<KUERZEL>.svg -- geladen wird nur die, die
jemand anklickt. Die Weltkarte selbst bleibt unberuehrt.

Quelle: ne_10m_admin_1_states_provinces, Natural Earth, gemeinfrei.

Warum der FEINE Satz und nicht der mittlere: ne_50m_admin_1 enthaelt nur
neun Laender (RU, US, IN, ID, CN, BR, CA, AU, ZA) -- am 05.09.2026
nachgezaehlt, 294 Objekte. Deutschland ist nicht dabei, die Schweiz auch
nicht. Der 10m-Satz hat 4.596 Regionen in 241 Laendern und traegt damit
genau das, was verlangt war: die ganze Welt.

Eigener Ausschnitt je Land
--------------------------
Die Weltkarte bildet auf ein festes Rechteck von 2000x1000 ab. Hier geht das
nicht: Russland und Luxemburg brauchen verschiedene Massstaebe. Also bekommt
jedes Land seinen eigenen Kasten, 1000 Einheiten breit, und die Datei traegt
in data-Attributen, welcher Laengen- und Breitengrad an seinen Raendern
liegt. Damit kann die Oberflaeche einen Knoten an seiner echten Koordinate
eintragen, ohne die Projektion zu kennen.

Zur Verzerrung: ein Grad Laenge ist auf 50 Grad Nord nur noch 64 Prozent so
lang wie ein Grad Breite. Ohne Ausgleich saehe Deutschland anderthalbmal zu
breit aus. Multipliziert wird deshalb mit dem Kosinus der mittleren Breite --
die einfachste ehrliche Korrektur, und sie steht hier statt in einer Formel,
die niemand nachrechnet.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

BREITE = 1000.0

# Rand um das Land herum, in Anteilen der Ausdehnung. Ohne ihn klebt der
# Umriss am Bildrand und sieht abgeschnitten aus.
RAND = 0.03

# Nachkommastellen im Bildraum. Bei 1000 Einheiten Breite ist eine Stelle
# feiner als ein Bildschirmpunkt -- dieselbe Ueberlegung wie in
# karte_bauen.py, nur auf den kleineren Kasten bezogen.
STELLEN = 1

# Laender, deren Gebiete ueber die Datumsgrenze reichen. Ohne Behandlung
# spannt der Kasten dann einmal um die ganze Erde, und das Land verschwindet
# als Strich am Rand. Betrifft in diesem Satz Russland, Fidschi, Kiribati und
# die USA (Aleuten) -- nachgezaehlt, nicht vermutet.
UM_DIE_DATUMSGRENZE = {"RU", "FJ", "KI", "US", "NZ", "AQ"}


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


def _sicher(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


# Wie weit ein Gebiet vom bisherigen Ausschnitt entfernt sein darf, um noch
# dazuzugehoeren -- gemessen in dessen eigener Ausdehnung.
#
# Befund aus dem Betrieb: viele kleine Laender wurden in ihrer
# Originalgroesse angezeigt statt gezoomt. Die Ursache waren die
# Ueberseegebiete. Die Niederlande spannten von -70,7 bis 9,5 Grad Laenge,
# weil Bonaire, Sint Eustatius und Saba in der Karibik liegen -- das
# eigentliche Land war darin ein Fleck von wenigen Bildpunkten. Betroffen
# waren 27 Laender, darunter Frankreich (Guadeloupe, Guayana), Norwegen
# (Bouvetinsel) und Chile (Osterinsel).
#
# Der Wert 1,5 trennt genau die beiden Faelle, die getrennt gehoeren:
# Alaska liegt rund 35 Grad von den unteren 48 entfernt, die selbst 58 Grad
# spannen -- Verhaeltnis 0,6, bleibt drin. Bonaire liegt 65 Grad von einem
# Land entfernt, das 4 Grad spannt -- Verhaeltnis 16, faellt heraus.
NACHBARSCHAFT = 1.5


def _kaesten(objekt: Dict, verschieben: bool) -> List[Tuple]:
    """Ein Kasten je TEILFLAECHE, nicht einer je Gebiet.

    Der Unterschied entscheidet ueber Chile. Die Osterinsel gehoert
    verwaltungsmaessig zur Region Valparaiso -- also zu DEMSELBEN Gebiet wie
    das Festland um Vina del Mar. Ein Kasten je Gebiet spannte damit von
    -109 bis -70 Grad, und kein Zusammenfassen der Welt haette daran etwas
    geaendert: die Insel klebte am Festland, weil sie im selben Umriss
    steckt. Je Ring gerechnet sind es zwei Flaechen, und die eine liegt
    dreissig Grad von der anderen.
    """
    heraus: List[Tuple] = []
    for ring in _ringe(objekt.get("geometry") or {}):
        lons: List[float] = []
        lats: List[float] = []
        for paar in ring:
            if not isinstance(paar, (list, tuple)) or len(paar) < 2:
                continue
            lon = float(paar[0])
            if verschieben and lon < 0:
                lon += 360.0
            lons.append(lon)
            lats.append(float(paar[1]))
        if lons:
            heraus.append((min(lons), min(lats), max(lons), max(lats)))
    return heraus


def _abstand(a, b) -> float:
    """Wie weit zwei Kaesten auseinanderliegen. Null, wenn sie sich beruehren."""
    dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
    dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
    return max(dx, dy)


def _grenzen(objekte: List[Dict], kuerzel: str) -> Tuple[float, float, float, float]:
    """Der Ausschnitt in Grad: (min_lon, min_lat, max_lon, max_lat).

    NICHT der Kasten um alles: der um die HAUPTLANDMASSE. Angefangen wird
    beim groessten Gebiet, dann wandert alles hinzu, was nah genug daran
    liegt -- und was uebrig bleibt, sind die weit entfernten Aussenposten.
    Sie stehen weiterhin in der Datei, nur nicht mehr im Bild; die Tabelle
    daneben fuehrt sie ohnehin.

    Bei Laendern ueber der Datumsgrenze werden negative Laengen um 360 Grad
    verschoben, damit der Kasten schmal bleibt statt die Erde zu umspannen.
    """
    verschieben = kuerzel in UM_DIE_DATUMSGRENZE
    kaesten: List[Tuple] = []
    for o in objekte:
        kaesten.extend(_kaesten(o, verschieben))
    if not kaesten:
        raise ValueError(f"{kuerzel}: keine Punkte")

    # Von JEDEM Gebiet aus einen Haufen wachsen lassen und den mit den
    # meisten Mitgliedern nehmen.
    #
    # Der erste Anlauf nahm das flaechengroesste Gebiet als Anker. Bei
    # Frankreich war das Franzoesisch-Guayana -- gross, aber allein. Der
    # Ausschnitt umfasste dann Guayana statt Frankreich, 3,1 mal 3,9 Grad
    # statt der erwarteten dreizehn. Die Zahl der Nachbarn ist der bessere
    # Massstab: 96 Departements gegen eines.
    beste = None
    for start in range(len(kaesten)):
        haufen = list(kaesten[start])
        rest = [k for i, k in enumerate(kaesten) if i != start]
        mitglieder = 1
        gewachsen = True
        while gewachsen and rest:
            gewachsen = False
            # Die KLEINERE Ausdehnung entscheidet, nicht die groessere.
            # Chile ist 9 Grad breit und 39 hoch; mit der groesseren waere
            # die Osterinsel (34 Grad entfernt) noch "benachbart", und die
            # Karte waere fuenfmal zu breit fuer das Land darauf.
            spanne = max(min(haufen[2] - haufen[0], haufen[3] - haufen[1]), 0.05)
            for i, k in enumerate(rest):
                if _abstand(haufen, k) <= spanne * NACHBARSCHAFT:
                    haufen = [min(haufen[0], k[0]), min(haufen[1], k[1]),
                              max(haufen[2], k[2]), max(haufen[3], k[3])]
                    rest.pop(i)
                    mitglieder += 1
                    gewachsen = True
                    break
        flaeche = (haufen[2] - haufen[0]) * (haufen[3] - haufen[1])
        if beste is None or (mitglieder, flaeche) > beste[0]:
            beste = ((mitglieder, flaeche), haufen)
    haufen = beste[1]
    return haufen[0], haufen[1], haufen[2], haufen[3]


class Kasten:
    """Rechnet Grad in Bildkoordinaten -- und sagt, wie es geht."""

    def __init__(self, min_lon, min_lat, max_lon, max_lat, verschieben: bool):
        self.verschieben = verschieben
        spanne_lon = max(max_lon - min_lon, 1e-6)
        spanne_lat = max(max_lat - min_lat, 1e-6)
        rand_lon = spanne_lon * RAND
        rand_lat = spanne_lat * RAND
        self.min_lon = min_lon - rand_lon
        self.max_lon = max_lon + rand_lon
        self.min_lat = min_lat - rand_lat
        self.max_lat = max_lat + rand_lat
        mitte = math.radians((self.min_lat + self.max_lat) / 2)
        # Nie ganz null: an den Polen waere die Karte sonst unendlich breit.
        self.xskala = max(math.cos(mitte), 0.05)
        self.hoehe = round(
            BREITE * (self.max_lat - self.min_lat)
            / ((self.max_lon - self.min_lon) * self.xskala), 1)

    def x(self, lon: float) -> float:
        if self.verschieben and lon < 0:
            lon += 360.0
        return (lon - self.min_lon) / (self.max_lon - self.min_lon) * BREITE

    def y(self, lat: float) -> float:
        return (self.max_lat - lat) / (self.max_lat - self.min_lat) * self.hoehe


def _pfad(ring: List, kasten: Kasten) -> str:
    heraus: List[str] = []
    vorher = None
    for paar in ring:
        if not isinstance(paar, (list, tuple)) or len(paar) < 2:
            continue
        x = round(kasten.x(float(paar[0])), STELLEN)
        y = round(kasten.y(float(paar[1])), STELLEN)
        if (x, y) == vorher:
            continue        # nach dem Runden doppelt -- spart spuerbar Platz
        vorher = (x, y)
        heraus.append(f"{x:g},{y:g}")
    if len(heraus) < 3:
        return ""
    return "M" + "L".join(heraus) + "Z"


def _hauptmitte(geometrie: Dict, kasten: "Kasten"):
    """Die Mitte der GROESSTEN Teilflaeche, im Bildraum.

    Nicht die Mitte des ganzen Gebiets: Tokio umfasst die Ogasawara-Inseln
    tausend Kilometer suedlich, und eine Linie, die dorthin zeigt, zeigt an
    Tokio vorbei. Am 06.09.2026 im Bild gesehen -- die Verbindung nach Japan
    endete auf einem Punkt weit im Meer.

    Genommen wird deshalb der flaechengroesste Ring. Bei Tokio ist das das
    Festlandstueck, bei Bayern ohnehin das einzige.
    """
    beste = None
    groesste = 0.0
    for ring in _ringe(geometrie):
        punkte = [(float(q[0]), float(q[1])) for q in ring
                  if isinstance(q, (list, tuple)) and len(q) >= 2]
        if len(punkte) < 3:
            continue
        # Gaussche Trapezformel -- doppelte Flaeche, Vorzeichen egal.
        flaeche = 0.0
        for i in range(len(punkte)):
            x1, y1 = punkte[i]
            x2, y2 = punkte[(i + 1) % len(punkte)]
            flaeche += x1 * y2 - x2 * y1
        flaeche = abs(flaeche)
        if flaeche <= groesste:
            continue
        groesste = flaeche
        lons = [q[0] for q in punkte]
        lats = [q[1] for q in punkte]
        beste = ((min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2)
    if beste is None:
        return None
    return (round(kasten.x(beste[0]), STELLEN),
            round(kasten.y(beste[1]), STELLEN))


def _namen(p: Dict) -> Tuple[str, str]:
    en = p.get("name_en") or p.get("name") or "?"
    return (p.get("name_de") or p.get("name") or en, en)


def baue(quelle: Path, ziel_ordner: Path) -> None:
    daten = json.loads(quelle.read_text(encoding="utf-8"))
    nach_land: Dict[str, List[Dict]] = {}
    for objekt in daten.get("features", []):
        kuerzel = (objekt.get("properties", {}).get("iso_a2") or "").strip().upper()
        if len(kuerzel) != 2:
            continue
        nach_land.setdefault(kuerzel, []).append(objekt)

    ziel_ordner.mkdir(parents=True, exist_ok=True)
    for alt in ziel_ordner.glob("*.svg"):
        alt.unlink()

    gesamt = 0
    geschrieben = 0
    for kuerzel, objekte in sorted(nach_land.items()):
        try:
            min_lon, min_lat, max_lon, max_lat = _grenzen(objekte, kuerzel)
        except ValueError:
            continue
        kasten = Kasten(min_lon, min_lat, max_lon, max_lat,
                        kuerzel in UM_DIE_DATUMSGRENZE)

        zeilen = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {BREITE:g} {kasten.hoehe:g}" class="regionskarte" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'data-land="{kuerzel}" '
            f'data-minlon="{kasten.min_lon:.4f}" data-maxlon="{kasten.max_lon:.4f}" '
            f'data-minlat="{kasten.min_lat:.4f}" data-maxlat="{kasten.max_lat:.4f}" '
            f'data-umbruch="{1 if kasten.verschieben else 0}">',
            "<!-- Umrisse: Natural Earth (ne_10m_admin_1_states_provinces),",
            "     gemeinfrei. Erzeugt von tools/regionen_bauen.py, nicht von",
            "     Hand aendern. -->",
            '<g class="regionen">',
        ]
        anzahl = 0
        for objekt in objekte:
            p = objekt.get("properties", {})
            d = "".join(_pfad(r, kasten)
                        for r in _ringe(objekt.get("geometry") or {}))
            if not d:
                continue
            de, en = _namen(p)
            iso = (p.get("iso_3166_2") or "").strip()
            # Wo eine Linie enden soll: auf der groessten Teilflaeche, nicht
            # in der Mitte aller. Die Oberflaeche prueft den Punkt trotzdem
            # noch einmal gegen die Flaeche -- er kann bei einem gebogenen
            # Gebiet danebenliegen.
            mitte = _hauptmitte(objekt.get("geometry") or {}, kasten)
            mitteltext = (f' data-cx="{mitte[0]:g}" data-cy="{mitte[1]:g}"'
                          if mitte else "")
            zeilen.append(
                f'<path id="r-{_sicher(iso) or kuerzel + str(anzahl)}" '
                f'data-de="{_sicher(de)}" data-en="{_sicher(en)}"'
                f'{mitteltext} d="{d}">'
                f'<title>{_sicher(en)}</title></path>')
            anzahl += 1
        if not anzahl:
            continue
        zeilen += ["</g>", "</svg>", ""]
        datei = ziel_ordner / f"{kuerzel}.svg"
        datei.write_text("\n".join(zeilen), encoding="utf-8")
        gesamt += datei.stat().st_size
        geschrieben += 1

    print(f"{ziel_ordner}: {geschrieben} Laender, "
          f"{gesamt / 1048576:.1f} MB zusammen, "
          f"groesste {max((p.stat().st_size for p in ziel_ordner.glob('*.svg')), default=0) / 1024:.0f} kB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Aufruf: regionen_bauen.py "
                         "<ne_10m_admin_1_states_provinces.geojson> <zielordner>")
    baue(Path(sys.argv[1]), Path(sys.argv[2]))
