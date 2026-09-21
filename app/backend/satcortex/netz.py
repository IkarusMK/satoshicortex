"""Das Compose-Netz: feste Adressen fuer die Dienste.

WARUM FESTE ADRESSEN -- der Befund vom 17.09.2026.

Tor laeuft in einem eigenen Container. Bis 0.62.0 legten bitcoind und LND
ihre Onion-Dienste selbst an, ueber Tors Steuerport, und nannten dabei kein
Ziel. Tor setzt dann 127.0.0.1 ein (hs_common.c, hs_parse_port_config:
"Default to 127.0.0.1") -- also seinen EIGENEN Container, in dem weder
bitcoind noch LND horchen. Die .onion-Adressen standen im Netz, und niemand
kam je an ihnen an.

Ein Ziel muss also eine Adresse im Compose-Netz sein. Ein Name wie "lnd"
reicht dafuer nicht, und zwar aus zwei Gruenden, beide im Quelltext belegt:

* Tor loest den Namen GENAU EINMAL auf, beim Lesen seiner Konfiguration
  (tor_addr_port_lookup). Bekommt LND danach eine andere Adresse -- nach
  einem Update, nach einem Neustart des Geraets in anderer Reihenfolge --,
  zeigt der Dienst ins Leere, bis Tor zufaellig selbst neu startet.
* Gibt es "lnd" in dem Moment nicht, verweigert Tor den Start ganz
  ("Unparseable address in hidden service port configuration") und nimmt
  bitcoind damit auch den Weg ins Onion-Netz.

Und Bitcoin Core nimmt fuer sein Onion-Ziel ohnehin keinen Namen an:
-bind wird mit fAllowLookup=false gelesen (init.cpp, v31.1).

Feste Adressen haben keinen dieser Faelle. Sie stehen in der Compose, und
dieses Modul ist die Stelle, an der die Anwendung dieselben Zahlen kennt.
"""
from __future__ import annotations

import ipaddress

# Bewusst NICHT aus 172.16.0.0/12: daraus vergibt Docker selbst seine Netze
# (default-address-pools, 172.17 bis 172.31). Ein festes Netz dort kollidiert
# frueher oder spaeter mit einem, das Docker einem anderen Stapel gegeben hat
# -- und dann startet dieser hier nicht. Auch nicht aus 192.168.0.0/16, dort
# vergibt Docker weiter und dort liegen die meisten Heimnetze. 10.83.33 ist
# "8333" und liegt abseits der ueblichen Belegungen (k3s 10.42/10.43,
# PiVPN 10.6, Umbrel 10.21.21).
PRAEFIX_VORGABE = "10.83.33"

# Die letzte Stelle der Adresse je Dienst. Dieselben Zahlen stehen in der
# Compose; ein Test haelt beide beieinander. Der Rest des /24 (ab .128)
# bleibt Docker fuer alles, was jemand von Hand dazuhaengt -- so kann ein
# fremder Container keinem Dienst die Adresse wegnehmen.
HOSTTEIL = {"app": 10, "bitcoind": 11, "lnd": 12, "tor": 13}

_PRIVAT = tuple(ipaddress.ip_network(n) for n in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def pruefe_praefix(wert: str) -> str:
    """Die ersten drei Stellen eines privaten /24 -- oder ValueError.

    Streng, weil der Wert in zwei Konfigurationen landet: in rpcallowip und
    in Tors Weiterleitungen. Fuehrende Nullen fallen durch, sonst hiesse
    "010" fuer den einen Leser zehn und fuer den anderen acht.
    """
    teile = str(wert).strip().split(".")
    if len(teile) != 3:
        raise ValueError(f"Kein Netz-Praefix aus drei Stellen: {wert!r}")
    for teil in teile:
        if not teil.isdigit() or str(int(teil)) != teil or int(teil) > 255:
            raise ValueError(f"Ungueltige Stelle {teil!r} in {wert!r}")
    netz = ipaddress.ip_network(".".join(teile) + ".0/24")
    if not any(netz.subnet_of(p) for p in _PRIVAT):
        raise ValueError(f"{netz} ist kein privates Netz")
    return ".".join(teile)


def subnetz(praefix: str) -> str:
    """Das ganze Compose-Netz als CIDR."""
    return f"{pruefe_praefix(praefix)}.0/24"


def adresse(praefix: str, dienst: str) -> str:
    """Die feste Adresse eines Dienstes."""
    return f"{pruefe_praefix(praefix)}.{HOSTTEIL[dienst]}"
