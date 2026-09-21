"""Speicherplatz pruefen und die Verzeichnisstruktur anlegen.

Der Nutzer gibt in der .env nur zwei Mountpunkte an. Alles darunter legt die
Anwendung selbst an -- inklusive der Dreiteilung von Bitcoin Cores
Datenverzeichnis, die dafuer sorgt, dass die schnelle Platte klein bleiben darf.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List

from . import facts

GB = 1024 ** 3

log = logging.getLogger(__name__)

# Was unter den beiden Mountpunkten entsteht. Getrennte Verzeichnisse je Dienst,
# damit man einzelne spaeter verschieben kann, ohne den Rest anzufassen.
BULK_UNTERORDNER = ("blocks", "coreindex")
FAST_UNTERORDNER = ("config", "bitcoind", "lnd", "tor", "app")

# Bitcoin Core kennt -datadir und -blocksdir, aber KEINE Option fuer die
# Indizes: txindex und die Blockfilter liegen zwingend unter
# <datadir>/indexes/. Zusammen sind das rund 75 GB, die auf die grosse Platte
# gehoeren und nicht auf die kleine schnelle.
#
# Frueher loeste das ein verschachtelter Einhaengepunkt in der Compose. Der
# zwang den Nutzer aber, jeden Unterordner vorab von Hand anzulegen -- auf
# einem UGREEN-NAS verweigert die Oberflaeche das Bereitstellen sonst. Ein
# Verweis erledigt dasselbe, und angeben muss man nur noch die zwei Wurzeln.
#
# Der Verweis zeigt auf den Pfad, wie ihn die CONTAINER sehen (/bulk/...).
# Im Dateimanager des NAS wirkt er deshalb ins Leere -- die Daten selbst
# liegen ganz normal sichtbar unter DATA_BULK/coreindex.
INDEX_VERWEIS = ("bitcoind", "indexes")


class Bewertung(str, Enum):
    GENUG = "genug"
    KNAPP = "knapp"
    ZU_WENIG = "zu_wenig"
    FEHLT = "fehlt"


@dataclass
class Platte:
    pfad: str
    vorhanden: bool
    frei_gb: int
    gesamt_gb: int
    bewertung: Bewertung
    empfohlen_gb: int
    mindestens_gb: int
    # Kein fertiger Satz, sondern Schluessel + Zahlen: uebersetzt wird in der
    # Oberflaeche. Ein hier zusammengebauter deutscher Text bliebe deutsch,
    # egal welche Sprache der Nutzer waehlt.
    meldung: str
    werte: Dict

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["bewertung"] = self.bewertung.value
        return d


def _frei_gb(pfad: Path) -> tuple:
    nutzung = shutil.disk_usage(pfad)
    return nutzung.free // GB, nutzung.total // GB


def pruefe_platte(pfad: str, empfohlen_gb: int, mindestens_gb: int, rolle: str) -> Platte:
    p = Path(pfad)
    if not p.exists():
        return Platte(
            pfad=pfad, vorhanden=False, frei_gb=0, gesamt_gb=0,
            bewertung=Bewertung.FEHLT,
            empfohlen_gb=empfohlen_gb, mindestens_gb=mindestens_gb,
            meldung="pfad_fehlt", werte={"pfad": pfad, "variable": rolle},
        )

    frei, gesamt = _frei_gb(p)

    werte = {
        "frei": frei,
        "empfohlen": empfohlen_gb,
        "mindestens": mindestens_gb,
        "fehlend": max(0, empfohlen_gb - frei),
        "wachstum": facts.WACHSTUM_GB_PRO_JAHR,
    }

    if frei >= empfohlen_gb:
        bewertung, meldung = Bewertung.GENUG, "platz_genug"
    elif frei >= mindestens_gb:
        bewertung, meldung = Bewertung.KNAPP, "platz_knapp"
    else:
        bewertung, meldung = Bewertung.ZU_WENIG, "platz_zu_wenig"

    return Platte(
        pfad=pfad, vorhanden=True, frei_gb=frei, gesamt_gb=gesamt,
        bewertung=bewertung, empfohlen_gb=empfohlen_gb,
        mindestens_gb=mindestens_gb, meldung=meldung, werte=werte,
    )


def pruefe(bulk: str, fast: str) -> Dict:
    """Beide Mountpunkte pruefen und ein Gesamturteil bilden."""
    b = pruefe_platte(bulk, facts.bedarf_bulk_gb(), facts.MINDEST_BULK_GB, "DATA_BULK")
    f = pruefe_platte(fast, facts.bedarf_fast_gb(), facts.MINDEST_FAST_GB, "DATA_FAST")

    gleiche_platte = _gleiches_geraet(bulk, fast)
    if gleiche_platte:
        # Dann darf der Platz nicht doppelt gezaehlt werden.
        b = pruefe_platte(
            bulk,
            facts.bedarf_bulk_gb() + facts.bedarf_fast_gb(),
            facts.MINDEST_BULK_GB + facts.MINDEST_FAST_GB,
            "DATA_BULK",
        )

    schlimmstes = _schlimmste([b.bewertung, f.bewertung])
    return {
        "bulk": b.to_dict(),
        "fast": f.to_dict(),
        "gleiche_platte": gleiche_platte,
        "gesamt": schlimmstes.value,
        "weiter_moeglich": schlimmstes in (Bewertung.GENUG, Bewertung.KNAPP),
        "meldung_gleiche_platte": "eine_platte" if gleiche_platte else "",
        "stand": facts.GEMESSEN_AM,
    }


def _gleiches_geraet(a: str, b: str) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def _schlimmste(bewertungen: List[Bewertung]) -> Bewertung:
    rang = {
        Bewertung.GENUG: 0,
        Bewertung.KNAPP: 1,
        Bewertung.ZU_WENIG: 2,
        Bewertung.FEHLT: 3,
    }
    return max(bewertungen, key=lambda b: rang[b])


def lege_ablage_an(pfad: str) -> bool:
    """Ein Verzeichnis anlegen, ohne den Start zu gefaehrden.

    Stimmen die Rechte nicht -- auf einem UGREEN-NAS etwa, wenn PGID nicht auf
    10 steht --, dann starb die Anwendung frueher hier mit einem
    PermissionError, noch bevor sie eine Zeile ausliefern konnte. Der Nutzer
    sah einen Container, der endlos neu startet, und nirgends einen Grund.
    Jetzt startet sie, meldet den Zustand ueber /api/zustand und kann in der
    Oberflaeche sagen, was zu tun ist.
    """
    try:
        Path(pfad).mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        log.warning("Verzeichnis %s nicht nutzbar: %s", pfad, fehler)
        return False
    return os.access(pfad, os.W_OK)


def bereite_vor(bulk: str, fast: str) -> List[str]:
    """Beim Start der Anwendung aufgerufen.

    Die Struktur muss stehen, BEVOR jemand den Assistenten durchlaeuft: die
    Anwendung schreibt ihr Konto nach <fast>/config, und die Dienste warten
    dort auf ihre Konfiguration. Sie erst beim Abschliessen anzulegen war ein
    Denkfehler -- dann haengt sie an einer Platzpruefung, die auf einem
    Testlaeufer nie durchgeht.

    Fehlende Einhaengepunkte oder Rechte duerfen den Start NICHT verhindern:
    sonst kommt der Nutzer nicht einmal an die Oberflaeche, die ihm erklaeren
    wuerde, was fehlt.
    """
    try:
        return lege_struktur_an(bulk, fast)
    except OSError as fehler:
        log.warning("Verzeichnisstruktur konnte nicht angelegt werden: %s", fehler)
        return []


def lege_struktur_an(bulk: str, fast: str) -> List[str]:
    """Legt die Unterverzeichnisse an. Gibt zurueck, was neu entstanden ist.

    Der Nutzer gibt zwei Pfade an -- alles darunter entsteht hier.
    """
    neu: List[str] = []
    for wurzel, unterordner in ((bulk, BULK_UNTERORDNER), (fast, FAST_UNTERORDNER)):
        for name in unterordner:
            ziel = Path(wurzel) / name
            if not ziel.exists():
                ziel.mkdir(parents=True, exist_ok=True)
                neu.append(str(ziel))

    verweis = Path(fast).joinpath(*INDEX_VERWEIS)
    index_ziel = Path(bulk) / "coreindex"
    # is_symlink() zusaetzlich zu exists(): ein Verweis auf ein Ziel, das die
    # Anwendung nicht sieht, meldet exists() == False -- ohne die zweite
    # Pruefung scheiterte jeder zweite Aufruf an einem schon vorhandenen
    # Verweis.
    if not verweis.exists() and not verweis.is_symlink():
        verweis.symlink_to(index_ziel, target_is_directory=True)
        neu.append(f"{verweis} -> {index_ziel}")
    return neu


def schreibe_geheimnis(pfad: str, inhalt: str) -> None:
    """Eine Datei schreiben, die ausser dem Besitzer niemand lesen darf.

    Drei Dinge, die hier zusammenkommen muessen:

    * 0600, und zwar BEVOR der Inhalt sichtbar wird. Deshalb erst schreiben,
      dann Rechte setzen, dann umbenennen -- die Zwischendatei traegt einen
      Namen, den niemand kennt, und ist nie unter dem Zielnamen zu breit
      lesbar.
    * Atomar. LND liest die Datei beim Start; eine halb geschriebene ergaebe
      ein falsches Passwort und einen Knoten, der nicht hochkommt.
    * KEIN abschliessender Zeilenumbruch. LND schneidet zwar "\r\n" ab
      (config_builder.go, v0.21.2-beta), aber sich darauf zu verlassen heisst,
      sich auf eine Zeile fremden Codes zu verlassen, die niemand
      versprochen hat.
    """
    ziel = Path(pfad)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    temp = ziel.with_name(ziel.name + ".neu")
    temp.write_text(inhalt, encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, ziel)
