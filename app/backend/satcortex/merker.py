"""Das Wallet-Passwort fuer die Laufzeit dieser Anwendung -- und keinen Takt
laenger.

WARUM ES DAS GIBT, UND WARUM DER TRESOR WEG IST.

Bis zum 10.09.2026 stand hier ein Tresor: das Wallet-Passwort, verschluesselt
mit einer Passphrase, die der Nutzer nach jedem Neustart tippt. Der Betreiber hat
ihn zerlegt, und er hatte recht:

    "das macht keinen sinn ich tausche ein passwort gegen das andere obwohl
     beide die selbe funktion unterm strich haben!!"

Nachgerechnet stimmt das genau. Gegen "ich tippe das Wallet-Passwort" gewinnt
ein Tresor nichts -- gleicher Aufwand, ein Artefakt mehr auf der Platte -- und
gegen "von allein entsperren" liefert er nicht das, wofuer man diese Betriebs-
art nimmt: der Knoten laeuft nach einem Stromausfall trotzdem nicht weiter.
Er sass zwischen zwei Wegen und bediente keinen davon.

DAS EIGENTLICHE PROBLEM war ein anderes, und es steht hier: nicht der
Stromausfall -- der kommt selten -- sondern dass DIESE ANWENDUNG LND staendig
selbst neu startet. Name geaendert, Sichtbarkeit geaendert, Adresse neu
aufgeloest, Konfiguration nachgezogen: jedes Mal faehrt LND neu hoch, und
jedes Mal steht die Wallet wieder zu, bis jemand davorsitzt. Das ist die
Reibung, die man spuert.

Dagegen genuegt etwas viel Kleineres als ein Tresor: das Passwort fuer die
Laufzeit der Anwendung im Arbeitsspeicher behalten. Dann macht sie die Wallet
nach IHREN EIGENEN Neustarts selbst wieder auf. Faellt der Strom aus, faellt
auch diese Anwendung -- und dann wird wieder getippt.

WAS DAS KOSTET, ehrlich benannt: wer den laufenden Prozess uebernimmt, findet
das Passwort im Speicher. Wer den laufenden Prozess uebernimmt, findet aber
ohnehin das admin.macaroon auf derselben Platte -- und das ist bei LND der
maechtigere Fund. Gegen den Fall, der wirklich zaehlt, ist dieser Weg genauso
gut wie "aus": gestohlene Platte, kopiertes Backup, ausgebaute NAS. Dort steht
nichts.

Deshalb gibt es hier keinen Pfad, keine Datei und keine Serialisierung. Nur
eine Zeichenkette in einem Objekt, das mit dem Prozess stirbt.
"""
from __future__ import annotations

import threading


class Merker:
    """Haelt genau ein Geheimnis, im Speicher, thread-sicher.

    Thread-sicher ist kein Zierrat: geschrieben wird aus einer Anfrage,
    gelesen aus dem Sammlerfaden, der alle paar Sekunden nachsieht, ob die
    Wallet wieder zugefallen ist.
    """

    def __init__(self) -> None:
        self._sperre = threading.Lock()
        self._geheimnis = ""

    @property
    def hat(self) -> bool:
        """Liegt etwas vor? Ohne das Geheimnis dabei herauszugeben."""
        with self._sperre:
            return bool(self._geheimnis)

    def merke(self, geheimnis: str) -> None:
        """Nur aufrufen, wenn LND das Passwort ANGENOMMEN hat.

        Ein Passwort zu merken, das nicht passt, waere schlimmer als keines:
        der Sammler wuerde es LND alle paar Sekunden erneut vorlegen.
        """
        with self._sperre:
            self._geheimnis = geheimnis or ""

    def hol(self) -> str:
        """Das Geheimnis -- leer, wenn keines da ist."""
        with self._sperre:
            return self._geheimnis

    def vergiss(self) -> None:
        with self._sperre:
            self._geheimnis = ""
