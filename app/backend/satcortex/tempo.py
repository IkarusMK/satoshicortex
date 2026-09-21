"""Wie schnell der Abgleich vorankommt -- und wie lange er noch braucht.

Der Erstabgleich laeuft ueber Tage. Eine Prozentzahl allein laesst den Nutzer
damit im Ungewissen: sie bewegt sich so langsam, dass man ihr beim besten
Willen nicht ansieht, ob noch zwei Tage oder zwei Wochen vor einem liegen.

Deshalb misst dieses Modul den Fortschritt ueber ein gleitendes Fenster und
rechnet hoch. Bewusst NICHT ueber die gesamte Laufzeit gemittelt: die ersten
Bloecke von 2009 fliegen durch, spaetere kosten ein Vielfaches. Ein Mittel
ueber alles waere darum dauerhaft zu optimistisch.

Der Verlauf lebt nur im Arbeitsspeicher. Nach einem Neustart gibt es einige
Minuten lang keine Schaetzung -- das ist beabsichtigt: lieber gar keine Zahl
als eine erfundene.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

# Unter dieser Spanne ist jede Hochrechnung Rauschen: ein einzelner Block, der
# zufaellig schnell durchlief, wuerde die Restdauer halbieren.
MINDESTSPANNE_SEKUNDEN = 120

# Wie weit zurueck gemessen wird. Eine halbe Stunde glaettet einzelne
# Ausreisser, folgt einer echten Tempoaenderung aber noch zeitnah.
FENSTER_SEKUNDEN = 1800


@dataclass(frozen=True)
class Messpunkt:
    zeit: float
    fortschritt: float
    hoehe: int


class Verlauf:
    def __init__(self, fenster_sekunden: int = FENSTER_SEKUNDEN) -> None:
        self.fenster = fenster_sekunden
        self._punkte: Deque[Messpunkt] = deque()

    def merke(self, fortschritt: float, hoehe: int, jetzt: Optional[float] = None) -> None:
        jetzt = time.time() if jetzt is None else jetzt
        self._punkte.append(Messpunkt(jetzt, fortschritt, hoehe))
        grenze = jetzt - self.fenster
        while len(self._punkte) > 2 and self._punkte[0].zeit < grenze:
            self._punkte.popleft()

    def schaetzung(self) -> Optional[Dict]:
        """Tempo und Restdauer -- oder None, solange die Grundlage fehlt."""
        if len(self._punkte) < 2:
            return None
        alt, neu = self._punkte[0], self._punkte[-1]
        spanne = neu.zeit - alt.zeit
        if spanne < MINDESTSPANNE_SEKUNDEN:
            return None

        zuwachs = neu.fortschritt - alt.fortschritt
        bloecke_pro_minute = (neu.hoehe - alt.hoehe) / spanne * 60

        rest_sekunden = None
        if zuwachs > 0:
            rest_sekunden = int((1.0 - neu.fortschritt) / (zuwachs / spanne))

        return {
            "bloecke_pro_minute": round(bloecke_pro_minute, 1),
            "rest_sekunden": rest_sekunden,
            "gemessen_ueber_sekunden": int(spanne),
        }
