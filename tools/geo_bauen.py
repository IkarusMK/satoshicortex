#!/usr/bin/env python3
"""Aus der DB-IP-Liste eine kompakte Nachschlagetabelle bauen.

Laeuft BEIM BAUEN DES ABBILDS, nicht im Betrieb. Das Ergebnis liegt fertig im
Abbild; die Anwendung fragt dafuer niemanden im Netz.

Warum ueberhaupt lokal: Die Karte muss zu jeder Adresse, die unser Knoten
kennt, einen Ort wissen. Der bequeme Weg waere ein Online-Dienst -- und der
bekaeme damit unsere komplette Nachbarliste. Genau das vermeiden wir bei der
Versionsabfrage schon ueber Tor; hier waere es noch schlimmer, weil es um
Adressen ginge, mit denen wir tatsaechlich sprechen.

Seit 0.42.0 traegt jede Zeile zusaetzlich ein GEBIET -- das, was DB-IP eine
Region nennt und was auf der Karte ein Bundesland, ein Kanton, ein Staat oder
eine Provinz ist. Die Zuordnung von Namen auf Umrisse steht fertig in
app/data/regionen.json (siehe tools/regionen_zuordnen.py); hier wird sie nur
angewandt. Ein Name, den sie nicht kennt, wird zu Gebiet 0 -- also "Land
bekannt, Gebiet nicht". Nie zu einem falschen Gebiet.

Format (alles Little-Endian, beide Zielarchitekturen sind das):

    "SATGEO03"      8 Byte Kennung
    stand           8 Byte   Jahrgang der Liste, ASCII "2026-09", mit Nullen
                             aufgefuellt. Er gehoert in die Oberflaeche: eine
                             zwei Jahre alte Liste ordnet still falsch zu, und
                             DB-IP steht unter CC BY -- die Herkunft muss
                             ohnehin genannt werden.
    n4              uint32   Anzahl IPv4-Bereiche
    n6              uint32   Anzahl IPv6-Bereiche
    n4 x uint32     Anfaenge, aufsteigend
    n4 x 2 Byte     Laenderkuerzel
    n4 x uint16     Gebietsnummern
    n6 x uint64     Anfaenge (oberste 64 Bit), aufsteigend
    n6 x 2 Byte     Laenderkuerzel
    n6 x uint16     Gebietsnummern

KEIN ENDE je Bereich, und das ist kein Sparzwang, sondern eine gepruefte
Eigenschaft der Quelle: am 05.09.2026 nachgezaehlt schliesst in der
DB-IP-Liste JEDER Bereich luekenlos an den vorigen an -- 3.588.553 IPv4- und
4.160.445 IPv6-Bereiche, null Luecken. Das Ende eines Bereichs ist damit der
Anfang des naechsten, und die Tabelle wird ein Drittel kleiner. Sollte die
Quelle das je aendern, faellt es hier beim Bauen auf: es wird geprueft.

Zur IPv6-Verkuerzung: gespeichert werden nur die obersten 64 Bit, also die
Genauigkeit eines /64 -- das kleinste Netz, das ueberhaupt vergeben wird.
"""
from __future__ import annotations

import csv
import ipaddress
import json
import struct
import sys
from array import array
from pathlib import Path
from typing import Dict, List, Tuple

KENNUNG = b"SATGEO03"


def _lade_zuordnung(pfad: Path) -> Dict[str, int]:
    if not pfad.exists():
        print(f"WARNUNG: {pfad} fehlt -- die Tabelle bekommt keine Gebiete.")
        return {}
    return json.loads(pfad.read_text(encoding="utf-8")).get("namen", {})


def _lies(quelle, namen: Dict[str, int]) -> Tuple[List, List, int]:
    """Die CSV-Zeilen in zwei sortierte Listen (Anfang, Land, Gebiet).

    Zusammengefasst wird gleich hier: folgen mehrere Bereiche mit demselben
    Land UND demselben Gebiet aufeinander, bleibt nur der erste stehen. Bei
    der Stadt-Liste halbiert das die Zeilenzahl -- sie unterteilt fein nach
    Orten, die uns gar nicht interessieren.
    """
    v4: List[Tuple[int, bytes, int]] = []
    v6: List[Tuple[int, bytes, int]] = []
    letzt4 = letzt6 = None
    naechster4 = naechster6 = None
    luecken = 0

    for teile in csv.reader(quelle):
        if len(teile) < 5:
            continue
        anfang, ende, land, region = teile[0], teile[1], teile[3], teile[4]
        kuerzel = land.strip().upper()[:2].encode("ascii", "replace")
        if len(kuerzel) != 2:
            continue
        gebiet = namen.get(f"{land.strip().upper()}|{region.strip()}", 0)
        marke = (kuerzel, gebiet)

        if ":" in anfang:
            a = int(ipaddress.IPv6Address(anfang)) >> 64
            e = int(ipaddress.IPv6Address(ende)) >> 64
            if naechster6 is not None and a > naechster6:
                luecken += 1
            naechster6 = e + 1
            if marke != letzt6:
                letzt6 = marke
                # Nach der Verkuerzung auf /64 koennen zwei Bereiche
                # denselben Anfang haben. Dann gewinnt der erste -- sonst
                # entstuende eine Zeile ohne Ausdehnung.
                if not v6 or v6[-1][0] != a:
                    v6.append((a, kuerzel, gebiet))
        else:
            a = int(ipaddress.IPv4Address(anfang))
            e = int(ipaddress.IPv4Address(ende))
            if naechster4 is not None and a > naechster4:
                luecken += 1
            naechster4 = e + 1
            if marke != letzt4:
                letzt4 = marke
                v4.append((a, kuerzel, gebiet))

    v4.sort()
    v6.sort()
    return v4, v6, luecken


def _packe(bereiche: List, typenkuerzel: str) -> bytes:
    anfaenge = array(typenkuerzel, [b[0] for b in bereiche])
    gebiete = array("H", [b[2] for b in bereiche])
    if sys.byteorder == "big":
        anfaenge.byteswap()
        gebiete.byteswap()
    laender = b"".join(b[1] for b in bereiche)
    return anfaenge.tobytes() + laender + gebiete.tobytes()


def baue(quelle: Path, ziel: Path, stand: str = "",
         zuordnung: Path = None) -> None:
    namen = _lade_zuordnung(zuordnung or Path("app/data/regionen.json"))
    with quelle.open(newline="", encoding="utf-8", errors="replace") as f:
        v4, v6, luecken = _lies(f, namen)
    # Die Luecken ZUERST: sie sind der genauere Befund. Eine Liste, die auch
    # noch unvollstaendig ist, meldet sonst nur "leer", und man sucht an der
    # falschen Stelle.
    if luecken:
        # Das Format setzt Lueckenlosigkeit voraus: ohne sie waere das Ende
        # eines Bereichs nicht mehr der Anfang des naechsten, und Adressen in
        # der Luecke bekaemen still das Land ihres Vorgaengers.
        raise SystemExit(
            f"Die Liste hat {luecken} Luecken -- das Format setzt "
            "lueckenlose Bereiche voraus. Bitte geo_bauen.py anpassen.")
    if not v4 or not v6:
        raise SystemExit("Die Liste enthaelt keine brauchbaren Bereiche.")

    mit_gebiet = sum(1 for b in v4 if b[2]) + sum(1 for b in v6 if b[2])
    ziel.write_bytes(
        KENNUNG + stand.encode("ascii", "replace")[:8].ljust(8, b"\0")
        + struct.pack("<II", len(v4), len(v6))
        + _packe(v4, "I") + _packe(v6, "Q")
    )
    print(f"{ziel}: {len(v4)} IPv4-Bereiche, {len(v6)} IPv6-Bereiche, "
          f"{mit_gebiet / (len(v4) + len(v6)) * 100:.1f} % mit Gebiet, "
          f"Stand {stand or 'unbekannt'}, "
          f"{ziel.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        raise SystemExit("Aufruf: geo_bauen.py <dbip-city.csv> <ziel.dat> "
                         "[stand] [regionen.json]")
    baue(Path(sys.argv[1]), Path(sys.argv[2]),
         sys.argv[3] if len(sys.argv) >= 4 else "",
         Path(sys.argv[4]) if len(sys.argv) == 5 else None)
