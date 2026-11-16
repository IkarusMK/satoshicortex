"""Fremde Ziele, die diese Anwendung im Auftrag eines Menschen anwaehlt.

DER BEFUND VOM 15.11.2026: drei Stellen waehlen eine Adresse an, die jemand
in der Oberflaeche eingetippt hat -- das Sicherungsziel (WebDAV, mit Basic-
Anmeldung), "mit Gegenstelle verbinden" und "Wachturm eintragen" (LND waehlt
an). Keine pruefte, WOHIN. Mit einer uebernommenen Sitzung wurde die Anwendung
so zum Wegweiser nach innen: Adressen im Compose-Netz (LND, bitcoind, Tor
mit ihren Steuerports), die eigene Schleife, die Dienstnamen. Antwortzeit und
Fehlertext verrieten, was dort offen ist -- ein Portscanner mit unserem
Absender, und beim Sicherungsziel sogar mit unseren Zugangsdaten im Kopf.

Gesperrt wird nach INNEN, nicht nach Heimnetz: ein NAS unter 192.168.x ist
das uebliche Sicherungsziel und muss gehen. Gesperrt sind Schleife, "unspecified"
(0.0.0.0), Link-Local (169.254.x, Metadaten-Dienste), das Compose-Netz
(NETWORK_PREFIX/24) und die Dienstnamen.

Namen werden NICHT aufgeloest: eine Pruefung, die den Namen aufloest und dann
einen zweiten Aufruf zulaesst, der ihn noch einmal aufloest, ist durch ein
Umbiegen der Antwort dazwischen zu umgehen. Hier steht, was sich ohne Netz
entscheiden laesst.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from . import netz

# Die Namen der Dienste im Compose-Netz -- dieselben, die Docker intern
# aufloest. Klein geschrieben verglichen.
DIENSTNAMEN = ("lnd", "bitcoind", "tor", "app")
INTERNE_NAMEN = DIENSTNAMEN + ("localhost", "localhost.localdomain")


def host_aus(wirt: str) -> str:
    """Der Rechnername oder die Adresse aus "host", "host:port",
    "[v6]:port" -- ohne Port, ohne Klammern."""
    w = (wirt or "").strip()
    if w.startswith("["):
        ende = w.find("]")
        return w[1:ende] if ende > 0 else w[1:]
    if w.count(":") == 1:
        return w.partition(":")[0]
    return w


def grund_intern(host: str, praefix: str) -> Optional[str]:
    """Warum dieser Host ein inneres Ziel ist -- oder None."""
    h = (host or "").strip().strip(".").lower()
    if not h:
        return "kein Rechner angegeben"
    if h in INTERNE_NAMEN:
        return "ein interner Name"
    try:
        adresse = ipaddress.ip_address(h)
    except ValueError:
        return None
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped:
        adresse = adresse.ipv4_mapped
    if adresse.is_loopback or adresse.is_unspecified or adresse.is_link_local:
        return "die eigene Schleife oder eine Sonderadresse"
    if adresse in ipaddress.ip_network(netz.subnetz(praefix)):
        return "das interne Netz dieser Anwendung"
    return None
