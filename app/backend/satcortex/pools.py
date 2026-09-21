"""Welcher Mining-Pool hat diesen Block gefunden?

Es gibt keine Stelle im Block, die das sagt -- Bitcoin kennt keine Pools. Man
erkennt sie an zwei Spuren, die sie selbst hinterlassen:

  * an der AUSZAHLUNGSADRESSE der Coinbase. Wenn sie in der Liste steht, ist
    sie die sichere Antwort -- sie laesst sich nicht mit einem Satz Text
    faelschen.
  * an einer KENNUNG im Coinbase-Skript ("/Foundry USA Pool/", "/AntPool/").
    Freiwillig und faelschbar, aber in der Praxis der Weg, der traegt.

Deshalb erst die Adresse, dann die Kennung. Mit einer Einschraenkung, die am
08.09.2026 an zwoelf echten Bloecken gemessen wurde: die Adressliste aus
pools-v2.json ist historisch und traf bei KEINEM einzigen davon zu -- Foundry,
AntPool und F2Pool zahlen sich laengst an andere Adressen aus als die dort
verzeichneten. Getragen hat allein die Kennung. Die Reihenfolge bleibt
trotzdem, denn wenn die Adresse trifft, ist sie die bessere Antwort. Wer beides nicht hat, bleibt
"unbekannt" -- und das ist eine ehrliche Antwort. Einen Pool zu raten waere
schlimmer als keiner: die Blockansicht ist dann eine Behauptung.

Die Zuordnungsliste stammt aus dem Repository mempool/mining-pools (MIT) und
liegt fertig im Abbild. Zur Laufzeit wird nichts nachgeladen -- eine
woechentliche Abfrage waere ein weiterer Weg, auf dem dieser Knoten sich zu
erkennen gibt. Neue Pools kommen also mit dem naechsten Abbild.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import coinbase

log = logging.getLogger(__name__)

STANDARDPFAD = os.environ.get("POOLS_DATEI", "/opt/satcortex/pools.json")


class Verzeichnis:
    def __init__(self, nach_adresse: Dict[str, str],
                 nach_kennung: List[tuple]) -> None:
        self._adressen = nach_adresse
        # Absteigend nach Laenge: "/BTC.COM/" soll nicht von "/BTC" gewinnen.
        # Kleingeschrieben, weil auch verglichen wird, ohne auf Gross- und
        # Kleinschreibung zu achten -- siehe erkenne().
        self._kennungen = sorted(((k.lower(), n) for k, n in nach_kennung),
                                 key=lambda p: -len(p[0]))

    def __len__(self) -> int:
        return len(set(self._adressen.values()) | {n for _, n in self._kennungen})

    def erkenne(self, coinbase_hex: str,
                adressen: Optional[List[str]] = None) -> Optional[str]:
        for adresse in adressen or []:
            treffer = self._adressen.get(adresse)
            if treffer:
                return treffer

        # spuren() statt botschaften(): fuer das ERKENNEN zaehlt, dass die
        # Kennung ueberhaupt gefunden wird, nicht dass drumherum sauberer Text
        # steht. Mit dem sauberen Skriptdurchlauf lagen wir am 08.09.2026 bei
        # 4 von 12 echten Bloecken, damit bei 12 von 12.
        #
        # Ohne Ruecksicht auf Gross- und Kleinschreibung, weil dieselben Pools
        # es selbst nicht halten: F2Pool schreibt mal "/F2Pool/", mal
        # "/f2pool.kz/", und die Liste kennt nur die eine Schreibweise.
        for text in coinbase.spuren(coinbase_hex or ""):
            klein = text.lower()
            for kennung, name in self._kennungen:
                if kennung in klein:
                    return name
        return None


def lade(pfad: Optional[str] = None) -> Optional[Verzeichnis]:
    """Die Liste laden. None, wenn es sie nicht gibt oder sie unbrauchbar ist.

    Fehlt sie, bleibt die Pool-Spalte leer -- die Blockansicht funktioniert
    weiter. Ein fehlendes Namensschild ist kein Grund, die Auswertung
    anzuhalten.
    """
    p = Path(pfad or STANDARDPFAD)
    if not p.exists():
        log.info("Keine Pool-Liste unter %s -- Bloecke bleiben ohne Pool.", p)
        return None
    try:
        roh = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(roh, list):
            raise ValueError("erwartet wird eine Liste von Pools")
    except (OSError, ValueError) as fehler:
        log.warning("Pool-Liste %s unbrauchbar (%s).", p, fehler)
        return None

    nach_adresse: Dict[str, str] = {}
    nach_kennung: List[tuple] = []
    for eintrag in roh:
        if not isinstance(eintrag, dict):
            continue
        name = (eintrag.get("name") or "").strip()
        if not name:
            continue
        for adresse in eintrag.get("addresses") or []:
            if isinstance(adresse, str) and adresse:
                nach_adresse.setdefault(adresse, name)
        for kennung in eintrag.get("tags") or []:
            if isinstance(kennung, str) and kennung:
                nach_kennung.append((kennung, name))

    verzeichnis = Verzeichnis(nach_adresse, nach_kennung)
    log.info("Pool-Liste geladen: %d Pools, %d Adressen, %d Kennungen.",
             len(verzeichnis), len(nach_adresse), len(nach_kennung))
    return verzeichnis
