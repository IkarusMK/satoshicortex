"""Die eigene Adresse aktuell halten.

Bitcoin Core loest -externalip NUR BEIM START auf. Steht dort ein Name, bleibt
die Auflösung von damals stehen -- bei einem Anschluss mit taeglicher
Zwangstrennung also hoechstens einen Tag lang richtig.

Die Folge ist schlimmer als "wird nicht gefunden": Der Knoten kuendigt eine
Adresse an, die inzwischen jemand anderem gehoert, und traegt sie im
Gossip-Netz weiter. Am 26.08.2026 am Geraet gesehen -- angekuendigt war
79.223.252.78, der Name zeigte laengst auf 84.134.34.64.

Deshalb steht in der Konfiguration die aufgeloeste IP und nicht der Name. Der
Name bleibt in der gespeicherten Wahl; dieses Modul haelt die IP daneben
aktuell. Aendert sie sich, wird die Konfiguration neu geschrieben -- und der
Waechter im Startskript startet bitcoind daraufhin sauber neu.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Callable, List, Sequence

from . import onion

log = logging.getLogger(__name__)

# Wie oft nachgesehen wird. Eine Zwangstrennung passiert typischerweise
# nachts; zehn Minuten sind kurz genug, dass der Knoten nicht lange falsch
# wirbt, und lang genug, um den DNS-Server nicht zu belaesten.
INTERVALL_SEKUNDEN = 600


def ist_ip(wert: str) -> bool:
    try:
        ipaddress.ip_address(wert)
        return True
    except ValueError:
        return False


# Wie oft eine Abfrage wiederholt wird, bevor sie als gescheitert gilt.
#
# DNS laeuft ueber UDP. Ein verlorenes Paket ist kein Ausfall, sondern
# Alltag -- und die Antwort auf Alltag ist ein zweiter Versuch, nicht eine
# Fehlermeldung.
VERSUCHE = 2

# Die beiden Familien, einzeln gefragt.
_FAMILIEN = ((socket.AF_INET, "A"), (socket.AF_INET6, "AAAA"))


def _je_familie(name: str, familie: int) -> List[str]:
    """Eine Familie abfragen. Leere Liste, wenn es dazu nichts gibt."""
    letzter = None
    for _ in range(VERSUCHE):
        try:
            infos = socket.getaddrinfo(name, None, family=familie,
                                       proto=socket.IPPROTO_TCP)
            return [eintrag[4][0] for eintrag in infos]
        except OSError as fehler:
            letzter = fehler
    if letzter is not None:
        log.debug("%s fuer %s: %s", familie, name, letzter)
    return []


def _brauchbar(adresse: str) -> bool:
    """Adressen aussortieren, die als externalip nichts taugen.

    Der Anlass: bei der Probe am 31.08.2026 kam auf die AAAA-Frage
    "::ffff:84.134.34.64" zurueck -- eine IPv4-Adresse in IPv6-Schreibweise.
    Ungeprueft waere daraus "externalip=::ffff:84.134.34.64" geworden: eine
    Adresse, unter der den Knoten niemand erreicht, angekuendigt als waere
    sie echt.

    Ebenso draussen bleiben private und Link-Local-Adressen. Im Container
    sieht der Knoten ohnehin nur die Docker-interne 172.x; sie anzukuendigen
    hilft niemandem.
    """
    try:
        art = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    if getattr(art, "ipv4_mapped", None) is not None:
        return False
    return not (art.is_private or art.is_link_local or art.is_loopback
                or art.is_reserved or art.is_multicast)


def _aufloesen(name: str) -> List[str]:
    """Alle brauchbaren A- und AAAA-Eintraege zu einem Namen.

    JE FAMILIE GETRENNT, und das ist der Punkt. Vorher stand hier ein
    einziger Aufruf ohne Familienangabe -- der fragt A und AAAA zusammen und
    scheitert als GANZES, wenn eine der beiden Antworten nicht taugt.

    Genau das ist am 31.08.2026 bei der Betreiber passiert: "[Errno -5] No address
    associated with hostname", waehrend derselbe Name von aussen ueber drei
    Resolver einwandfrei aufloeste. Sein Name hat kein AAAA; antwortet der
    DNS-Server darauf mit einem Fehler statt mit einer leeren Antwort, nimmt
    er die funktionierende IPv4-Antwort mit ins Grab.

    Getrennt gefragt kann das nicht mehr passieren: was da ist, kommt zurueck.
    """
    gefunden: List[str] = []
    gescheitert = []
    for familie, wie in _FAMILIEN:
        treffer = [a for a in _je_familie(name, familie) if _brauchbar(a)]
        if treffer:
            gefunden.extend(treffer)
        else:
            gescheitert.append(wie)
    if not gefunden:
        log.warning("Name %s nicht aufloesbar (%s ohne Ergebnis)",
                    name, " und ".join(gescheitert))
    # Reihenfolge stabil halten, sonst gilt eine Konfiguration als geaendert,
    # nur weil der DNS-Server die Antworten anders sortiert hat.
    return sorted(set(gefunden))


def loese_auf(
    adressen: Sequence[str],
    aufloeser: Callable[[str], List[str]] = _aufloesen,
) -> List[str]:
    """Namen zu IPs aufloesen, IPs unveraendert uebernehmen.

    Laesst sich ein Name gerade nicht aufloesen, faellt er weg statt eine
    Konfiguration mit einem unbrauchbaren Wert zu erzeugen. Beim naechsten
    Durchlauf wird es erneut versucht.
    """
    ergebnis: List[str] = []
    for eintrag in adressen:
        eintrag = eintrag.strip()
        if not eintrag:
            continue
        if ist_ip(eintrag):
            ergebnis.append(eintrag)
            continue
        ergebnis.extend(_aufloesen_gemerkt(eintrag, aufloeser))
    # Doppelte entfernen, Reihenfolge behalten.
    gesehen = set()
    return [a for a in ergebnis if not (a in gesehen or gesehen.add(a))]


def _aufloesen_gemerkt(name: str, aufloeser: Callable[[str], List[str]]) -> List[str]:
    treffer = aufloeser(name)
    if not treffer:
        log.warning("Kein Eintrag fuer %s -- Adresse bleibt diesmal aussen vor", name)
    return treffer


def hat_sich_geaendert(conf: str, soll: Sequence[str]) -> bool:
    """Steht in der Konfiguration etwas anderes als das, was gelten soll?"""
    # Ohne die eigene .onion: die legt Tor an, kein DNS-Name liefert sie.
    # Mitgezaehlt stuende sie immer als "Unterschied" da -- und der Waechter
    # startete bitcoind bei jedem Durchgang neu.
    ist = sorted(
        z.strip().split("=", 1)[1]
        for z in conf.splitlines()
        if z.strip().startswith("externalip=")
        and not onion.ist_onion(z.strip().split("=", 1)[1])
    )
    return ist != sorted(soll)
