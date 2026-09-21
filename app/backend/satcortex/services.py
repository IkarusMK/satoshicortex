"""Konfiguration der Dienste schreiben und ihren Zustand ablesen.

Die Anwendung steuert die Dienste ueber Dateien, nicht ueber den Docker-Socket
(der waere auf einem Geraet mit Wallet gleichbedeutend mit root). Je Dienst gibt
es zwei Dateien im gemeinsamen Volume:

    <name>.conf    die Konfiguration
    <name>.ready   die Freigabe -- erst damit laeuft der Dienst los

Das Startskript im Container wartet auf beide, merkt sich die Pruefsumme der
Konfiguration und faehrt den Dienst geordnet herunter, wenn sie sich aendert.
Docker startet ihn dann mit den neuen Werten neu.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from . import storage
from typing import Dict, List, Optional

PLATZHALTER = re.compile(r"\{\{([A-Z_]+)\}\}")


class Zustand(str, Enum):
    UNKONFIGURIERT = "unkonfiguriert"   # noch keine Konfiguration geschrieben
    WARTET = "wartet"                   # Konfiguration da, aber nicht freigegeben
    FREIGEGEBEN = "freigegeben"         # laeuft (oder startet gerade)


@dataclass
class DienstStatus:
    name: str
    zustand: Zustand
    pruefsumme: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "zustand": self.zustand.value,
            "pruefsumme": self.pruefsumme,
        }


def rendere(vorlage: str, werte: Dict[str, str]) -> str:
    """Ersetzt {{PLATZHALTER}} durch Werte.

    Bewusst kein string.Template: der rpcauth-Hash enthaelt ein '$', woran
    dessen Syntax scheitern wuerde. Und bewusst kein str.format: Konfigurationen
    duerfen geschweifte Klammern enthalten, ohne dass es knallt.
    """
    fehlend = sorted(
        {m.group(1) for m in PLATZHALTER.finditer(vorlage)} - set(werte)
    )
    if fehlend:
        raise KeyError(
            "Die Vorlage verlangt Werte, die nicht geliefert wurden: "
            + ", ".join(fehlend)
        )
    return PLATZHALTER.sub(lambda m: str(werte[m.group(1)]), vorlage)


class Konfigurationsablage:
    """Verwaltet das gemeinsame config-Volume."""

    def __init__(self, verzeichnis: str) -> None:
        self.pfad = Path(verzeichnis)
        storage.lege_ablage_an(str(self.pfad))

    def _conf(self, name: str) -> Path:
        return self.pfad / f"{name}.conf"

    def _ready(self, name: str) -> Path:
        return self.pfad / f"{name}.ready"

    def lies(self, name: str) -> Optional[str]:
        """Die aktuell geltende Konfiguration eines Dienstes.

        Grundlage fuer gezielte Aenderungen im Betrieb: die Datei selbst ist
        die Wahrheit. Sie aus gespeicherten Antworten neu zu bauen scheitert
        bei jedem, der vor 0.4.1 eingerichtet hat.
        """
        ziel = self._conf(name)
        try:
            return ziel.read_text(encoding="utf-8")
        except OSError:
            return None

    def schreibe(self, name: str, inhalt: str) -> str:
        """Schreibt die Konfiguration ATOMAR und gibt die Pruefsumme zurueck.

        Das Umbenennen am Ende ist entscheidend: der Waechter im Container
        vergleicht Pruefsummen im Sekundentakt. Wuerde er eine halb
        geschriebene Datei erwischen, wuerde er den Dienst grundlos neu starten
        -- bei bitcoind mitten im Schreiben des chainstate.
        """
        ziel = self._conf(name)
        temp = ziel.with_suffix(".conf.tmp")
        temp.write_text(inhalt, encoding="utf-8")
        # Rechte VOR dem Umbenennen setzen, sonst gibt es ein Zeitfenster, in
        # dem die Datei fuer alle lesbar ist. 0640: Eigentuemer schreibt, die
        # Gruppe liest -- die Dienste laufen unter derselben Kennung und
        # brauchen Lesezugriff. Der Rest des Geraets nicht.
        #
        # In bitcoind.conf steht die rpcauth-Zeile. Deren Passwort hat 256 Bit
        # Zufall und ist nicht durchprobierbar -- das macht die Zeile aber nicht
        # zu etwas, das jeder Benutzer des Geraets lesen koennen muss.
        os.chmod(temp, 0o640)
        os.replace(temp, ziel)          # atomar innerhalb desselben Dateisystems
        return self.pruefsumme(name)

    def pruefsumme(self, name: str) -> Optional[str]:
        import hashlib
        ziel = self._conf(name)
        if not ziel.exists():
            return None
        return hashlib.sha256(ziel.read_bytes()).hexdigest()

    def gib_frei(self, name: str) -> None:
        # Auch die Freigabemarke bekommt enge Rechte. Ihr Inhalt ist harmlos --
        # ein Zeitstempel --, aber im config-Verzeichnis soll nichts liegen,
        # das weiter lesbar ist als noetig. Die Dienste lesen sie unter
        # derselben Kennung.
        marke = self._ready(name)
        marke.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        os.chmod(marke, 0o640)

    def sperre(self, name: str) -> None:
        """Nimmt die Freigabe zurueck -- der Dienst faehrt daraufhin herunter."""
        self._ready(name).unlink(missing_ok=True)

    def status(self, name: str) -> DienstStatus:
        if not self._conf(name).exists():
            return DienstStatus(name, Zustand.UNKONFIGURIERT, None)
        if not self._ready(name).exists():
            return DienstStatus(name, Zustand.WARTET, self.pruefsumme(name))
        return DienstStatus(name, Zustand.FREIGEGEBEN, self.pruefsumme(name))

    def alle(self, namen: List[str]) -> List[Dict]:
        return [self.status(n).to_dict() for n in namen]

    # ------------------------------------------------------------ Geheimnisse
    def schreibe_geheim(self, name: str, daten: Dict) -> None:
        """Legt Zugangsdaten ab, die nur die Anwendung selbst braucht.

        Getrennt von den Konfigurationsdateien, weil die von allen Diensten
        gelesen werden. Rechte 0600, und zwar VOR dem Sichtbarmachen -- sonst
        gibt es ein Zeitfenster, in dem die Datei fuer alle lesbar ist.
        """
        import json
        ziel = self.pfad / f"{name}.geheim.json"
        temp = ziel.with_suffix(".json.tmp")
        temp.write_text(json.dumps(daten), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, ziel)

    def lies_geheim(self, name: str) -> Optional[Dict]:
        import json
        ziel = self.pfad / f"{name}.geheim.json"
        if not ziel.exists():
            return None
        try:
            return json.loads(ziel.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
