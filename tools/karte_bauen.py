#!/usr/bin/env python3
"""Aus Natural-Earth-Umrissen ein kompaktes SVG der Weltkarte bauen.

Laeuft von Hand, wenn die Umrisse erneuert werden sollen -- das Ergebnis
(app/web/welt.svg) liegt im Repo. Es beim Bauen des Abbilds zu erzeugen waere
unnoetig: Landesgrenzen aendern sich nicht monatlich, und so ist im Repo
sichtbar, was ausgeliefert wird.

Quellen (beide Natural Earth, gemeinfrei, ausdruecklich ohne
Namensnennungspflicht -- genannt werden sie trotzdem, in der Oberflaeche und
in THIRD-PARTY-LICENSES.md):

* ne_110m_admin_0_countries       -- die Umrisse
* ne_50m_admin_0_tiny_countries   -- Punkte fuer die Laender, die bei dieser
                                     Aufloesung gar keinen Umriss haetten

Der zweite Datensatz ist kein Beiwerk. Ohne ihn fehlen 75 Kuerzel auf der
Karte, darunter SINGAPUR, HONGKONG, MALTA, LIECHTENSTEIN, MAURITIUS und die
SEYCHELLEN -- allesamt Orte, an denen tatsaechlich Knoten stehen. Sie waeren
still von der Karte gefallen, waehrend die Liste daneben sie auffuehrt.

Projektion: gleichabstaendig (Laengengrad -> x, Breitengrad -> y). Nicht die
schoenste, aber die ehrlichste einfache: keine versteckten Verzerrungsformeln,
und jeder erkennt sie. Der Ausschnitt endet bei 58 Grad Sued -- die Antarktis
faellt damit weg. Ein Verlust ist das nicht: die Laendertabelle daneben zeigt
ohnehin jedes Land, auch eines ohne Umriss.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

BREITE = 2000
HOEHE = 1000

# Ausschnitt. Oben knapp ueber Spitzbergen, unten knapp unter Feuerland.
NORD = 84.0
SUED = -58.0

# Auf wie viele Nachkommastellen im Bildraum gerundet wird. 1 entspricht bei
# 2000 Punkten Breite etwa 0,02 Grad -- feiner als jeder Bildschirm zeigt.
STELLEN = 1

# Radius der Punkte fuer Laender ohne eigene Flaeche (Andorra, Singapur, die
# Karibik-Inseln, insgesamt 63 Stueck).
#
# Stand bis zum 04.09.2026 auf 9 -- also 18 Einheiten Durchmesser auf einer
# Karte von 2000 Einheiten Breite. Deutschland ist in dieser Projektion rund
# 44 Einheiten breit: der Punkt fuer Andorra war damit fast halb so gross wie
# Deutschland. Der Betreiber: "entweder sind sie nicht sauber ... viel zu gross oder
# unnoetig". Die Lage stimmt uebrigens -- gegengeprueft an Andorra, Singapur,
# Barbados, Hongkong, Malta und Island, Abweichung hoechstens 0,2 Grad. Es
# war wirklich nur die Groesse.
PUNKT_RADIUS = 3


def _x(laenge: float) -> float:
    return (laenge + 180.0) / 360.0 * BREITE


def _y(breite: float) -> float:
    return (NORD - breite) / (NORD - SUED) * HOEHE


def _sicher(text: str) -> str:
    """Fuer ein Attribut bzw. einen Textknoten entschaerfen."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _ring(punkte: List) -> str:
    """Einen Ring als SVG-Pfad. Leer, wenn zu wenig davon uebrig bleibt."""
    heraus: List[str] = []
    vorher = None
    for paar in punkte:
        if not isinstance(paar, (list, tuple)) or len(paar) < 2:
            continue
        x = round(_x(paar[0]), STELLEN)
        y = round(_y(paar[1]), STELLEN)
        if (x, y) == vorher:
            continue        # nach dem Runden doppelt -- spart spuerbar Platz
        vorher = (x, y)
        heraus.append(f"{x:g},{y:g}")
    if len(heraus) < 3:
        return ""
    return "M" + "L".join(heraus) + "Z"


def _pfade(geometrie: Dict) -> str:
    return "".join(_ring(r) for r in _ringe(geometrie))


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


def _anker(geometrie: Dict):
    """Ein Punkt, an dem eine Linie zu diesem Land ansetzen kann.

    Der Schwerpunkt der GROESSTEN Flaeche, nicht der aller zusammen. Bei
    Frankreich mit Franzoesisch-Guayana, bei den USA mit Alaska und Hawaii
    laege ein gemeinsamer Schwerpunkt sonst im Meer -- und die Linie endete
    dort, wo nichts ist.
    """
    beste = None
    groesste = 0.0
    for ring in _ringe(geometrie):
        punkte = [(p[0], p[1]) for p in ring
                  if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(punkte) < 3:
            continue
        # Gaussche Trapezformel: doppelte Flaeche und Schwerpunkt in einem.
        flaeche = sx = sy = 0.0
        for i in range(len(punkte)):
            x1, y1 = punkte[i]
            x2, y2 = punkte[(i + 1) % len(punkte)]
            kreuz = x1 * y2 - x2 * y1
            flaeche += kreuz
            sx += (x1 + x2) * kreuz
            sy += (y1 + y2) * kreuz
        if abs(flaeche) < 1e-12:
            continue
        if abs(flaeche) > groesste:
            groesste = abs(flaeche)
            beste = (sx / (3 * flaeche), sy / (3 * flaeche))
    if beste is None:
        return None
    laenge, breite = beste
    # Ausserhalb des Ausschnitts hat der Anker nichts verloren.
    if not SUED <= breite <= NORD:
        return None
    return round(_x(laenge), STELLEN), round(_y(breite), STELLEN)


def _namen(eigenschaften: Dict, kuerzel: str) -> tuple:
    """(deutsch, englisch). Natural Earth fuehrt beide mit.

    Ohne Namen ist ein Punkt im Ozean keine Information, sondern ein Raetsel --
    genau dieser Eindruck entstand am 27.08.2026 beim ersten Blick auf die
    fertige Karte.
    """
    en = eigenschaften.get("NAME") or kuerzel
    return (eigenschaften.get("NAME_DE") or en, en)


def _punkte(quelle: Path) -> Dict[str, tuple]:
    """Kuerzel -> (x, y, name_de, name_en) fuer Laender ohne eigenen Umriss."""
    if not quelle.exists():
        return {}
    daten = json.loads(quelle.read_text(encoding="utf-8"))
    heraus: Dict[str, tuple] = {}
    for objekt in daten.get("features", []):
        eigenschaften = objekt.get("properties", {})
        kuerzel = (eigenschaften.get("ISO_A2_EH")
                   or eigenschaften.get("ISO_A2") or "").strip().upper()
        geometrie = objekt.get("geometry") or {}
        if len(kuerzel) != 2 or geometrie.get("type") != "Point":
            continue
        laenge, breite = geometrie["coordinates"][:2]
        if not SUED <= breite <= NORD:
            continue
        de, en = _namen(eigenschaften, kuerzel)
        heraus[kuerzel] = (round(_x(laenge), STELLEN),
                           round(_y(breite), STELLEN), de, en)
    return heraus


def baue(quelle: Path, ziel: Path, kleine: Path = None) -> None:
    daten = json.loads(quelle.read_text(encoding="utf-8"))

    # Mehrere Objekte koennen dasselbe Land sein (Inselgruppen, Exklaven).
    nach_land: Dict[str, List[str]] = {}
    namen: Dict[str, tuple] = {}
    anker: Dict[str, tuple] = {}
    groesse: Dict[str, float] = {}
    for objekt in daten.get("features", []):
        eigenschaften = objekt.get("properties", {})
        kuerzel = (eigenschaften.get("ISO_A2_EH")
                   or eigenschaften.get("ISO_A2") or "").strip().upper()
        if len(kuerzel) != 2 or kuerzel == "-9":
            continue        # nicht anerkannte Gebiete ohne ISO-Kuerzel
        geometrie = objekt.get("geometry") or {}
        d = _pfade(geometrie)
        if d:
            nach_land.setdefault(kuerzel, []).append(d)
            namen.setdefault(kuerzel, _namen(eigenschaften, kuerzel))
            # Mehrere Objekte je Land: der Anker gehoert zum groessten davon.
            punkt = _anker(geometrie)
            flaeche = sum(len(r) for r in _ringe(geometrie))
            if punkt and flaeche > groesse.get(kuerzel, 0):
                groesse[kuerzel] = flaeche
                anker[kuerzel] = punkt

    zeilen = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {BREITE} {HOEHE}" class="weltkarte" '
        'preserveAspectRatio="xMidYMid meet" aria-hidden="true">',
        "<!-- Umrisse: Natural Earth (ne_110m_admin_0_countries), gemeinfrei.",
        "     Erzeugt von tools/karte_bauen.py, nicht von Hand aendern. -->",
        '<g class="laender">',
    ]
    for kuerzel in sorted(nach_land):
        d = "".join(nach_land[kuerzel])
        de, en = namen[kuerzel]
        a = anker.get(kuerzel)
        ortung = f' data-x="{a[0]:g}" data-y="{a[1]:g}"' if a else ""
        zeilen.append(
            f'<path id="l-{kuerzel}" data-de="{_sicher(de)}" '
            f'data-en="{_sicher(en)}"{ortung} d="{d}">'
            f'<title>{_sicher(en)}</title></path>')
    zeilen.append("</g>")
    # Leere Ebene fuer die Verbindungslinien. Sie liegt UEBER den Flaechen und
    # UNTER den Punkten -- sonst verdeckt eine Linie den Marker, auf den sie
    # zeigt. Gefuellt wird sie erst im Browser, wenn die Gegenstellen bekannt
    # sind.
    zeilen.append('<g class="linien"></g>')

    # Punkte NUR fuer Laender ohne eigenen Umriss -- sonst laege ueber
    # Deutschland ein Punkt auf der Flaeche.
    punkte = {k: v for k, v in _punkte(kleine or Path("/nichts")).items()
              if k not in nach_land}
    if punkte:
        zeilen.append('<g class="kleine">')
        for kuerzel in sorted(punkte):
            x, y, de, en = punkte[kuerzel]
            zeilen.append(
                f'<circle id="p-{kuerzel}" data-de="{_sicher(de)}" '
                f'data-en="{_sicher(en)}" data-x="{x:g}" data-y="{y:g}" '
                f'cx="{x:g}" cy="{y:g}" r="{PUNKT_RADIUS}">'
                f'<title>{_sicher(en)}</title></circle>')
        zeilen.append("</g>")

    zeilen += ["</svg>", ""]

    ziel.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"{ziel}: {len(nach_land)} Laender mit Umriss, "
          f"{len(punkte)} als Punkt, {ziel.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit("Aufruf: karte_bauen.py <ne_110m_countries.geojson> "
                         "<ziel.svg> [ne_50m_tiny_countries.geojson]")
    baue(Path(sys.argv[1]), Path(sys.argv[2]),
         Path(sys.argv[3]) if len(sys.argv) == 4 else None)
