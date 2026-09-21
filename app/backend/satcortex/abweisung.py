"""Was eine Abfuhr bedeutet -- in einem Satz, an EINER Stelle.

Am 10.09.2026 schickte der Betreiber einen Ausschnitt aus seinem Protokoll und
fragte, ob das normal sei. Drei Zeilen davon waren erklaerte Abweisungen, eine
nicht:

    Nachrichten (CNBC): Die Quelle weist uns ab (HTTP 403). Das trifft ueber
    Tor haeufiger zu -- manche Verlage sperren Ausgangsknoten.
    ...
    Nachrichten (Bit2Me News): HTTPError: HTTP Error 418: I'm a teapot

Dieselbe Sache, einmal erklaert und einmal nicht. Der Grund war, dass zwei
Module ihre eigene kleine Liste fuehrten und beide unvollstaendig waren --
die Nachrichten kannten 404, die Boersen kannten 429, und 418 kannte keiner.
Zwei Listen, die dasselbe tun, laufen auseinander; das ist keine Vorhersage,
das ist hier passiert.

Also eine Liste, und die Module setzen nur noch ihr eigenes Hauptwort davor.
"""
from __future__ import annotations

from typing import Optional

# Ueber Tor ist eine Abfuhr der Regelfall und kein Defekt. Genau das muss in
# den Saetzen stehen -- sonst sucht jemand einen Fehler, den es nicht gibt.
_UEBER_TOR = ("Ueber Tor ist das der Regelfall, nicht die Ausnahme -- "
              "viele Anbieter sperren Ausgangsknoten.")


def deute_http(code: Optional[int], was: str) -> Optional[str]:
    """Ein Satz zum Statuscode, oder None, wenn es keinen bekannten Fall gibt.

    ``was`` ist das Hauptwort des Aufrufers: "Die Quelle", "Die Boerse".
    None zurueckzugeben ist Absicht -- nicht alles wegerklaeren. Ein Fehler
    ohne bekannte Bedeutung soll seinen Wortlaut behalten, sonst sucht man
    ihn nirgends wieder.
    """
    if not isinstance(code, int):
        return None
    if code in (401, 403):
        return f"{was} weist uns ab (HTTP {code}). {_UEBER_TOR}"
    # Der Scherz-Statuscode aus RFC 2324. Schutzdienste vor grossen Seiten --
    # Cloudflare voran -- vergeben ihn, wenn sie den Anrufer fuer einen
    # Automaten halten. Es ist dasselbe wie eine 403, es stand nur nicht da.
    if code == 418:
        return (f"Der Schutzdienst haelt uns fuer einen Automaten "
                f"(HTTP {code}). {_UEBER_TOR}")
    # Nicht dasselbe wie 403: "spaeter nochmal" statt "du nicht". Wer das
    # zusammenwirft, sucht an der falschen Stelle.
    if code == 429:
        return (f"Zu haeufig gefragt (HTTP {code}). Beim naechsten Durchgang "
                "wieder -- es wird nur um Abstand gebeten.")
    if code == 451:
        return f"{was} ist aus rechtlichen Gruenden gesperrt (HTTP {code})."
    if code == 404:
        return f"{was} gibt es unter dieser Adresse nicht mehr (HTTP {code})."
    if 500 <= code < 600:
        return (f"{was} hat gerade selbst ein Problem (HTTP {code}). Das geht "
                "vorbei, ohne dass hier etwas zu tun waere.")
    return None
