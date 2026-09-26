"""Aus den Antworten des Assistenten die Konfiguration der Dienste bauen."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from . import netz, onion, profiles, rpcauth, services

VORLAGEN = Path(__file__).resolve().parents[2] / "templates"

# Ueber onlynet sagt dieser Block NICHTS mehr. Bis 0.40.0 stand hier "onlynet
# wird bewusst NICHT gesetzt" -- ein Satz aus der Zeit, als das stimmte. Seit
# es die Sichtbarkeitswahl gibt, entscheidet der Netzblock darueber, und bei
# "nur ueber Tor" stand die Behauptung dann zwei Zeilen ueber ihrem eigenen
# Gegenteil. Wer seine Konfiguration liest, soll ihr glauben koennen.
TOR_BLOCK = """# Tor: der Knoten ist zusaetzlich als Onion-Dienst erreichbar. Tor-Knoten
# brauchen Gegenstellen, die beide Welten sprechen -- diese Bruecke ist knapp.
#
# ACHTUNG, hier steht bewusst "onion" und NICHT "proxy". "proxy" gilt fuer
# ALLE ausgehenden Verbindungen, auch IPv4 und IPv6 -- der ganze Verkehr liefe
# dann durch Tor, und die DNS-Seeds liefern nichts mehr, weil ueber SOCKS5
# keine DNS-Abfrage geht ("0 addresses found from DNS seeds", am 25.08.2026 am
# laufenden Knoten gemessen). Fuer einen Archiv-Knoten, der anderen die Kette
# ausliefern soll, genau verkehrt.
onion=tor:9050
#
# Den Onion-Dienst legt NICHT bitcoind an, sondern Tor selbst, aus seiner
# eigenen Konfiguration. Bis 0.62.0 stand listenonion hier auf 1: bitcoind bat
# Tor ueber den Steuerport darum, nannte kein Ziel -- und Tor reichte an
# 127.0.0.1 in SEINEM Container weiter, wo nichts horcht. Die .onion stand im
# Netz und war nie erreichbar. Einzelheiten in onion.py.
listenonion=0
# Mit -bind gilt Cores Vorgabe "auf allem horchen" nicht mehr. Deshalb steht
# der gewoehnliche Port ausdruecklich da ...
bind=0.0.0.0:8333
# ... und daneben der, an den Tor weiterreicht. "=onion" sagt Core, dass diese
# Gegenstellen aus dem Onion-Netz kommen -- ueber 8333 hereingereicht hielte er
# sie fuer Nachbarn aus dem Compose-Netz.
bind=0.0.0.0:8334=onion"""

# Die eigene .onion haengt am Ende des Tor-Abschnitts. Sie kommt aus Tors
# Datei "hostname" und steht NICHT bei den Clearnet-Adressen: die tauscht die
# Adressnachfuehrung bei jeder Zwangstrennung aus, und die .onion gehoert
# nicht zu dem, was ein DNS-Name liefert.
TOR_ONION_ZEILE = """# Unter dieser Adresse kuendigt sich der Knoten im Onion-Netz an. Tor hat sie
# angelegt; sie bleibt, solange sein Schluessel unter /fast/tor bleibt.
externalip={adresse}"""


def tor_block(onion_adresse: str = "") -> str:
    """Der Tor-Abschnitt -- mit der eigenen .onion, sobald Tor sie kennt."""
    if not onion_adresse:
        return TOR_BLOCK
    if not onion.ist_gueltig(onion_adresse):
        raise ValueError(f"Keine gueltige Onion-Adresse: {onion_adresse!r}")
    return TOR_BLOCK + "\n" + TOR_ONION_ZEILE.format(adresse=onion_adresse)


TOR_AUS = "# Tor ist abgeschaltet (in der Weboberflaeche einschaltbar)."

# ── Wie der Knoten im Lightning-Netz auftritt ──────────────────────────────
#
# Aus dem Betrieb, 04.09.2026: "das sollte aber jeder Nutzer unter Einstellungen
# immer selber entscheiden koennen ... gibt ja vielleicht politische
# Restriktionen, die das nicht wollen -- da sollte man die Moeglichkeit haben,
# anonym zu bleiben."
#
# Bis dahin stand hier fest verdrahtet der Hybrid-Betrieb, samt einem
# Kommentar, der schlicht falsch war: "die Onion-Adresse allein macht schon
# anonym". Tut sie nicht. LNDs eigene Beschreibung zu
# tor.skip-proxy-for-clearnet-targets, am 04.09.2026 nachgeschlagen:
#
#   "Allow the node to connect to non-onion services directly via clearnet.
#    ... WARNING: This option will reveal the source IP address of the node,
#    and should be used only if privacy is not a concern."
#
# Man kuendigt also eine Onion-Adresse an und verraet seine IP trotzdem --
# an jede Gegenstelle, die man selbst anspricht. Genau die Falle, gegen die
# Der Einwand aus dem Betrieb zielt.

TOR_KOPF = """[Tor]
tor.active=true
tor.socks=tor:9050
# LND legt KEINEN Onion-Dienst an -- das tut Tor selbst, aus seiner eigenen
# Konfiguration, und LND kuendigt die Adresse nur noch an. Bis 0.62.0
# bat LND Tor ueber den Steuerport darum. Das ging zweimal schief: Tor reichte
# an 127.0.0.1 in SEINEM Container weiter, wo LND nicht horcht, und nach jedem
# Neustart von Tor war der Dienst weg -- LNDs Pruefung, die ihn neu anlegt,
# ist in v0.21.3-beta abgeschaltet (healthcheck.torconnection.attempts=0).
# Einzelheiten in onion.py. Der Steuerport ist seitdem zu.
tor.v3=false"""

LND_TOR_NUR = TOR_KOPF + """
# Angekuendigt wird AUSSCHLIESSLICH die Onion-Adresse. Eine zusaetzlich
# eingetragene Clearnet-Adresse waere hier ein Selbsttor: sie verraet die IP
# an jeden im Graphen, ganz gleich wie sorgfaeltig der Ausgang durch Tor
# laeuft. Deshalb laesst baue_lnd sie in dieser Betriebsart weg.
# Ausgehend AUSSCHLIESSLICH durch Tor. Damit erfaehrt keine Gegenstelle die
# eigene IP -- auch keine, die selbst im Clearnet sitzt. Der Preis sind
# hoehere Laufzeiten und gelegentlich zaehere Verbindungen.
tor.skip-proxy-for-clearnet-targets=false
# Jede Verbindung ueber einen eigenen Kreis. Laut LND-Doku ausdruecklich
# NICHT zusammen mit direkten Verbindungen erlaubt ("may not be used while
# direct connections are enabled") -- hier passt es, weil genau die aus sind.
tor.streamisolation=true"""

LND_TOR_HYBRID = TOR_KOPF + """
# Hybrid: erreichbar als Onion-Dienst UND im Clearnet, und ausgehend auf dem
# direkten Weg. Das ist schneller und stabiler -- und verraet die eigene IP
# an jede Gegenstelle im Clearnet. LNDs eigene Warnung dazu: "should be used
# only if privacy is not a concern."
tor.skip-proxy-for-clearnet-targets=true"""

# Still: durch Tor hinaus, aber NICHTS ankuendigen -- auch keine Onion. Fuer
# "still" legt Tor keinen Dienst an (onion.dienste_fuer), und baue_lnd nennt
# keine Adresse. Nur ausgehende Kanaele, kein Weiterleiten.
LND_TOR_STILL = TOR_KOPF + """
tor.skip-proxy-for-clearnet-targets=false
tor.streamisolation=true"""

LND_TOR_BLOCK = LND_TOR_HYBRID

LND_TOR_AUS = """# Tor ist abgeschaltet (in der Weboberflaeche einschaltbar).
# Der Knoten ist dann nur ueber seine gewoehnliche Adresse erreichbar."""

LND_ADRESSE_AUS = """# Keine eigene Adresse angegeben. Ohne sie kuendigt der Knoten im Graphen
# keine erreichbare Adresse an -- andere koennen dann keinen Kanal zu ihm
# oeffnen, auch bei offenem Port. Nachtragen laesst sie sich jederzeit."""


# Was in einer Konfigurationszeile nichts zu suchen hat.
#
# Alias, Farbe und Adressen kommen aus einem Eingabefeld und landen
# unveraendert in einer Datei, die LND Zeile fuer Zeile liest. Ein
# Zeilenumbruch darin waere keine Schoenheitsfrage: dahinter liesse sich jede
# beliebige LND-Option anhaengen -- etwa eine, die das Wallet-Passwort aus
# einer Datei liest. Bei bitcoind faengt das heute die DNS-Aufloesung ab, weil
# nur auflösbare Namen und gueltige IPs durchkommen. Das ist Schutz aus zweiter
# Hand; hier steht er ausdruecklich da.
def nur_eine_zeile(wert: str) -> str:
    """Fuehrende/abschliessende Leerzeichen weg, Steuerzeichen verboten."""
    sauber = (wert or "").strip()
    if any(z in sauber for z in "\r\n") or any(ord(z) < 32 for z in sauber):
        raise ValueError("Steuerzeichen sind in diesem Feld nicht erlaubt.")
    return sauber


ADRESSE_AUS = """# Keine eigene Adresse angegeben. Der Knoten versucht dann, sie von seinen
# Gegenstellen zu lernen -- das gelingt oft, aber nicht immer und nicht sofort.
# Nachtragen laesst sie sich jederzeit in der Weboberflaeche."""


def setze_dbcache(conf: str, megabyte: int) -> str:
    """Den Datenbank-Cache in einer BESTEHENDEN Konfiguration aendern.

    Waehrend des Erstabgleichs bringt ein grosser Cache am meisten -- er spart
    zaehe Schreibzugriffe. Danach ist er verschwendet: der laufende Betrieb
    braucht ihn nicht, und der Speicher steht anderen Diensten auf dem Geraet
    zu. Auf einem NAS mit Immich, Paperless und Nextcloud daneben ist das kein
    Detail.

    Wie bei setze_adressen wird die Datei gezielt geaendert statt neu gebaut:
    alles andere bleibt Zeichen fuer Zeichen stehen, auch die rpcauth-Zeile.
    """
    heraus = f"dbcache={megabyte}"
    zeilen = []
    ersetzt = False
    for zeile in conf.splitlines():
        if zeile.strip().startswith("dbcache="):
            zeilen.append(heraus)
            ersetzt = True
        else:
            zeilen.append(zeile)
    if not ersetzt:
        zeilen += ["", heraus]
    return "\n".join(zeilen).rstrip() + "\n"


# Die drei Schalter, die zusammen gehoeren. peerblockfilters ist dabei kein
# Beiwerk: ohne blockfilterindex bricht Bitcoin Core den Start ab --
# "Cannot set -peerblockfilters without -blockfilterindex." Wer nur zwei von
# dreien umlegt, hat einen Knoten, der nicht mehr hochkommt.
INDEX_SCHALTER = ("txindex", "blockfilterindex", "peerblockfilters")

INDIZES_AUS = """# ============================================================ Indizes
# Waehrend des Erstabgleichs ABGESCHALTET -- und das ist kein Verzicht,
# sondern eine Reihenfolge.
#
# txindex und der Blockfilter-Index sind LevelDB-Datenbanken. Sie schreiben
# bei jedem Block mit wahlfreiem Zugriff, also mit Spruengen, und sie liegen
# auf derselben Platte wie die Bloecke. Auf einer Festplatte sind das genau
# die Zugriffe, auf die der Abgleich ohnehin schon wartet.
#
# Gebraucht werden beide erst DANACH: der eine fuer die
# Transaktionsverfolgung und fuer Wallets wie Sparrow, der andere fuer
# Leichtgewicht-Wallets, die ihre Filter bei uns holen. Waehrend die Kette
# laedt, fragt danach niemand.
#
# Nichts geht dabei verloren. Core merkt sich den Stand jedes Index als
# Locator in dessen eigener Datenbank und setzt beim Wiedereinschalten dort
# fort ("Syncing ... with block chain from height N"); abgeschaltete Indizes
# werden nicht geloescht. Geprueft in src/index/base.cpp und src/init.cpp
# gegen Core 31.1.
#
# Die Anwendung schaltet sie selbst wieder ein, sobald die Kette steht.
txindex=0
blockfilterindex=0
peerblockfilters=0"""

INDIZES_AN = """# ============================================================ Indizes
# txindex: fuer die Transaktionsverfolgung und fuer Wallets, die sich direkt
# mit Bitcoin Core verbinden.
txindex=1

# BIP158-Filter erzeugen UND ausliefern -- damit bedient dieser Knoten
# Leichtgewicht-Wallets, die sonst einen fremden Server fragen muessten.
blockfilterindex=1
peerblockfilters=1"""


# Waehrend des Erstabgleichs KEINE ausgehenden Verbindungen ueber Tor.
#
# Am 29.08.2026 an dem Knoten im Betrieb beobachtet: bei einem Tor-Anteil von 100 %
# lief der Abgleich mit 49,9 Bloecken/Minute, bei 18 % mit 58,9. Zwei
# Datenpunkte sind kein Beweis -- aber Tor ist um ein Vielfaches langsamer
# als eine gewoehnliche Verbindung, und der Anteil schwankt unkontrolliert
# je nachdem, welche Gegenstellen der Knoten zufaellig zuerst erwischt.
#
# WAS ES KOSTET -- hier stand bis zum 31.08.2026 das Gegenteil, und des Betreibers
# Screenshot hat es aufgedeckt: seine Onion-Adresse verschwand aus der
# Anzeige, nachdem bitcoind mit gesetztem onlynet neu gestartet war.
#
# Cores Hilfetext sagt "Inbound and manual connections are not affected by
# this option", und das stimmt -- fuer das ANNEHMEN von Verbindungen. Ueber
# die ANKUENDIGUNG der eigenen Adresse sagt er nichts, und die ist sehr wohl
# betroffen:
#
#   init.cpp   onlynet gesetzt -> g_reachable_nets.RemoveAll(), dann nur die
#              genannten Netze wieder hinein
#   net.cpp    AddLocal(): "if (!g_reachable_nets.Contains(addr)) return
#              false" -- die eigene Onion-Adresse kommt damit gar nicht erst
#              in mapLocalHost
#
# Folge: waehrend der Pause steht die .onion nicht in
# getnetworkinfo.localaddresses und wird nicht angekuendigt. Der Onion-Dienst
# laeuft weiter und nimmt eingehende Verbindungen an; neue Gegenstellen
# erfahren die Adresse aber nicht.
#
# Vertretbar bleibt es trotzdem: waehrend des Abgleichs kann der Knoten
# ohnehin nichts ausliefern. Und die Adresse geht nicht verloren -- ihr
# Schluessel liegt im Datenverzeichnis, dieselbe kommt zurueck. Wer den
# Tausch nicht will, schaltet die Pause in der Oberflaeche ab.
#
# Beide Clearnet-Netze muessen dastehen. Nur ipv4 waere ein stiller Verzicht
# auf IPv6, und Core lehnt ausserdem ein ausdrueckliches -dnsseed=1 ab, wenn
# onlynet IPv4 UND IPv6 verbietet.
# Die drei Wege, auf denen ein Knoten hinaus kann. Die Namen sind Cores
# eigene -- sie stehen so in der Konfiguration.
NETZE = ("ipv4", "ipv6", "onion")

ALLE_NETZE = """# onlynet ist nicht gesetzt: IPv4, IPv6 und Onion laufen alle.
# Tor-Knoten brauchen Gegenstellen, die beide Welten sprechen -- diese
# Bruecke ist knapp."""


def netzblock(erlaubt, grund: str = "") -> str:
    """Der onlynet-Abschnitt fuer die erlaubten Netze.

    Sind alle drei erlaubt, wird onlynet NICHT gesetzt -- das ist nicht
    dasselbe wie "alle drei aufzaehlen", sondern Cores Standard, und er
    schliesst kuenftige Netze mit ein.

    Wichtig fuer das Verstaendnis der Schalter: onlynet gilt laut Cores
    eigener Hilfe nur fuer automatische AUSGEHENDE Verbindungen --
    "Inbound and manual connections are not affected by this option."
    Ein abgeschaltetes Netz macht den Knoten dort also nicht unerreichbar;
    er ruft dort nur von sich aus niemanden mehr an. Erreichbarkeit steuern
    listen, listenonion und die angekuendigten Adressen.
    """
    gewaehlt = [n for n in NETZE if n in set(erlaubt)]
    if len(gewaehlt) == len(NETZE):
        return ALLE_NETZE
    kopf = ["# Ausgehende Verbindungen nur ueber: " + ", ".join(gewaehlt) + ".",
            "# Eingehende Verbindungen sind davon NICHT betroffen -- onlynet",
            "# gilt allein fuer Verbindungen, die dieser Knoten selbst aufbaut."]
    # Jede Zeile einzeln auskommentieren. Ein mehrzeiliger Grund, bei dem nur
    # die erste Zeile ein '#' bekommt, schreibt den Rest als Konfiguration in
    # die Datei -- Core bricht dann beim Start ab.
    kopf += [("# " + z).rstrip() for z in grund.splitlines() if grund]
    return "\n".join(kopf + [f"onlynet={n}" for n in gewaehlt])


# Der Grund, der im Erstabgleich mit in die Datei geschrieben wird. Wer die
# Konfiguration spaeter liest, soll nicht raten muessen, warum Tor dort fehlt.
ABGLEICH_GRUND = """Waehrend des Erstabgleichs bleibt Tor aussen vor: es ist um ein Vielfaches
langsamer, und beim Laden der Kette zaehlt nur der Durchsatz.

ACHTUNG, das kostet mehr als nur ausgehende Verbindungen -- hier stand
frueher das Gegenteil. onlynet setzt, welche Netze Core fuer "erreichbar"
haelt (init.cpp: g_reachable_nets.RemoveAll()), und AddLocal lehnt jede
eigene Adresse ab, deren Netz nicht darin steht (net.cpp: "if
(!g_reachable_nets.Contains(addr)) return false"). Die Onion-Adresse taucht
damit nicht in getnetworkinfo.localaddresses auf und wird NICHT angekuendigt.

Der Onion-Dienst laeuft weiter und nimmt eingehende Verbindungen an -- aber
neue Gegenstellen erfahren die Adresse nicht. Waehrend des Abgleichs ist das
verschmerzbar: ausliefern kann der Knoten ohnehin nichts. Die Adresse selbst
geht nicht verloren, der Schluessel liegt im Datenverzeichnis. Die Anwendung
nimmt das von selbst zurueck, sobald die Kette steht."""

# Womit ein erzeugter onlynet-Abschnitt anfaengt -- die aktuellen Fassungen und
# die aelteren. Daran wird der Block beim Neuschreiben wiedererkannt und im
# Ganzen entfernt, statt einzelne Saetze aus ihm herauszufischen.
_NETZBLOCK_ANFANG = (
    "# onlynet ist nicht gesetzt:",
    "# Ausgehende Verbindungen nur ueber:",
    # vor 0.16.0
    "# onlynet ist bewusst NICHT gesetzt:",
    "# Waehrend des Erstabgleichs baut der Knoten selbst keine",
)


def _ohne_block(conf: str, anfaenge: tuple, schluessel: tuple,
                gehoert_dazu=lambda _zeile: False) -> list:
    """Einen erzeugten Abschnitt im Ganzen aus der Konfiguration nehmen.

    Ein Abschnitt ist zusammenhaengend: seine Kommentarzeilen und seine
    Einstellungszeilen stehen ohne Leerzeile beieinander. Deshalb wird ab der
    Anfangszeile alles verschluckt, bis etwas kommt, das weder Kommentar noch
    eine der Zeilen des Abschnitts ist.

    Einzelne Saetze wiederzuerkennen waere die Alternative gewesen -- und jede
    Umformulierung haette dann eine Kommentarleiche in der Datei hinterlassen.
    """
    zeilen: list = []
    ueberspringen = False
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        eigen = nackt.startswith(schluessel) or gehoert_dazu(nackt)
        if ueberspringen:
            if nackt.startswith("#") or eigen:
                continue
            ueberspringen = False
        if nackt.startswith(anfaenge):
            ueberspringen = True
            while zeilen and not zeilen[-1].strip():
                zeilen.pop()            # die Leerzeile davor gehoert dazu
            continue
        if eigen:
            continue                # Rest eines Abschnitts oder von Hand gesetzt
        zeilen.append(zeile)
    return zeilen


def setze_netze(conf: str, erlaubt, grund: str = "") -> str:
    """onlynet in einer BESTEHENDEN Konfiguration setzen oder entfernen.

    Gezielt geaendert, nicht neu gebaut: alles andere bleibt Zeichen fuer
    Zeichen stehen, auch die rpcauth-Zeile, ohne die sich die Anwendung von
    ihrem eigenen Knoten aussperren wuerde.
    """
    zeilen = _ohne_block(conf, _NETZBLOCK_ANFANG, ("onlynet=",))
    block = netzblock(erlaubt, grund).splitlines()
    # Direkt hinter discover=1, wo auch die externen Adressen stehen.
    for i, zeile in enumerate(zeilen):
        if zeile.strip() == "discover=1":
            zeilen[i + 1:i + 1] = ["", *block]
            break
    else:
        zeilen += ["", *block]
    return "\n".join(zeilen).rstrip() + "\n"


# ── Wallet-Software im Heimnetz ────────────────────────────────────────────
#
# Aus dem Betrieb, 05.09.2026: "was mir auch schmecken wuerde, wenn ich meine
# Transaktionen von meinem Hardware-Wallet dann auch ueber meinen BTC-Knoten
# machen koennte."
#
# Der uebliche Weg dafuer ist Sparrow: die Wallet haelt die Schluessel selbst
# (bzw. das Hardware-Geraet tut es), der eigene Knoten liefert nur die
# Kettendaten. Sparrows eigene Beschreibung, am 05.09.2026 nachgeschlagen:
# "Sparrow does not use Bitcoin Core's internal wallet" -- es wird also KEINE
# Wallet im Knoten angelegt und keine Schluessel dorthin gegeben. Fuer
# entfernte Verbindungen nennt sie rpcbind, rpcallowip und Benutzer/Passwort.
#
# Was das oeffnet, gehoert trotzdem gesagt: wer im Heimnetz an diesen Port
# kommt UND die Zugangsdaten hat, kann den Knoten befragen und Transaktionen
# einreichen. Deshalb ist es abschaltbar und standardmaessig aus.
_RPC_FREIGABE_ANFANG = "# ─ Wer die RPC-Schnittstelle benutzen darf"

# Das Netz der Compose. Ohne diese Freigabe spraeche die Anwendung nicht mehr
# mit ihrem eigenen Knoten -- sie steht deshalb IMMER im Block.
#
# Seit 0.63.0 genau das /24 der Compose, nicht mehr 172.16.0.0/12. Das weite
# Netz war noetig, solange Docker die Adressen frei vergab; es liess aber auch
# jede Gegenstelle durch, die zufaellig aus 172.16/12 kommt -- und so sehen
# manche Heimnetze aus. Mit festen Adressen (netz.py) geht es enger.
RPC_COMPOSE_NETZ = netz.subnetz(netz.PRAEFIX_VORGABE)

# Was bis 0.62.0 als Compose-Netz dastand. Beim Lesen ist das KEIN Heimnetz.
FRUEHERE_COMPOSE_NETZE = ("172.16.0.0/12",)


def rpc_freigabe_block(heimnetz: str = "",
                       compose_netz: str = RPC_COMPOSE_NETZ) -> str:
    """Alle rpcallowip-Zeilen an EINER Stelle.

    Beide Zeilen gehoeren in denselben Block, und zwar aus einem handfesten
    Grund: der Block wird beim Umschalten im Ganzen entfernt und neu gesetzt,
    und dabei verschwinden alle rpcallowip-Zeilen der Datei. Stuende die
    Compose-Zeile ausserhalb, waere sie nach dem ersten Umschalten weg -- und
    die Anwendung von ihrem eigenen Knoten ausgesperrt. Beim Bauen gemerkt,
    bevor es jemanden getroffen hat.
    """
    zeilen = [
        _RPC_FREIGABE_ANFANG,
        "# Das Compose-Netz immer -- daraus spricht die Anwendung selbst.",
        f"rpcallowip={compose_netz}",
    ]
    if heimnetz:
        zeilen += [
            "# Dazu das Heimnetz: eine Wallet-Software darf diesen Knoten als",
            "# Hintergrund benutzen (Sparrow und Verwandte). Sie legt dabei",
            "# KEINE Wallet im Knoten an -- die Schluessel bleiben bei ihr",
            "# bzw. auf dem Hardware-Geraet. Wer hier hereinkommt UND die",
            "# Zugangsdaten hat, kann den Knoten befragen und Transaktionen",
            "# einreichen; Geld bewegen kann er damit nicht.",
            f"rpcallowip={heimnetz}",
        ]
    return "\n".join(zeilen)


def setze_rpc_freigabe(conf: str, heimnetz: str,
                       compose_netz: str = RPC_COMPOSE_NETZ) -> str:
    """Die RPC-Freigabe in einer BESTEHENDEN Konfiguration setzen.

    Setzt auch das Compose-Netz neu -- bei einer Datei von vor 0.63.0 steht
    dort noch 172.16.0.0/12, und aus dem festen Netz kaeme die Anwendung
    damit nicht mehr an ihren eigenen Knoten heran.
    """
    zeilen = _ohne_block(conf, _RPC_FREIGABE_ANFANG, ("rpcallowip=",))
    block = rpc_freigabe_block(heimnetz, compose_netz).splitlines()
    for i, zeile in enumerate(zeilen):
        if zeile.strip().startswith("rpcbind="):
            zeilen[i + 1:i + 1] = ["", *block]
            break
    else:
        zeilen += ["", *block]
    return "\n".join(zeilen).rstrip() + "\n"


def lies_rpc_freigabe(conf: str, compose_netz: str = RPC_COMPOSE_NETZ) -> str:
    """Welches Heimnetz laut Konfiguration gerade freigegeben ist."""
    compose = {compose_netz, *FRUEHERE_COMPOSE_NETZE}
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if not nackt.startswith("rpcallowip="):
            continue
        wert = nackt.split("=", 1)[1].strip()
        if wert not in compose:
            return wert
    return ""


def lies_rpc_compose_netz(conf: str) -> str:
    """Welches Compose-Netz die Datei durchlaesst -- "" wenn keins.

    Die erste rpcallowip-Zeile des Blocks ist die des Compose-Netzes; so
    schreibt rpc_freigabe_block sie.
    """
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if nackt.startswith("rpcallowip="):
            return nackt.split("=", 1)[1].strip()
    return ""


def lies_netze(conf: str) -> tuple:
    """Welche Netze der Knoten laut Konfiguration gerade selbst anruft.

    Keine onlynet-Zeile heisst ALLE -- das ist Cores Standard und nicht etwa
    "keine". Ein Leser, der das verwechselt, schaltet dem Knoten den Ausgang
    ab, weil er glaubt, es sei ohnehin schon so.
    """
    gefunden = tuple(
        z.strip().split("=", 1)[1].strip().lower()
        for z in conf.splitlines() if z.strip().startswith("onlynet=")
    )
    if not gefunden:
        return NETZE
    return tuple(n for n in NETZE if n in gefunden)


# ------------------------------------------------------------------- Tor
#
# Der Tor-Abschnitt stand bisher nur in der Vorlage: er wurde beim Einrichten
# einmal eingesetzt und war danach nicht mehr zu bewegen, ohne die ganze
# Konfiguration neu zu bauen. Fuer einen Schalter, den man jederzeit umlegen
# koennen soll, reicht das nicht.
_TORBLOCK_ANFANG = (
    "# Tor: der Knoten ist zusaetzlich als Onion-Dienst erreichbar.",
    "# Tor ist abgeschaltet",
)
_TOR_SCHLUESSEL = ("onion=", "torcontrol=", "listenonion=", "bind=")


def _ist_onion_zeile(nackt: str) -> bool:
    """Eine externalip-Zeile mit der eigenen .onion -- sie gehoert zu Tor."""
    return (nackt.startswith("externalip=")
            and onion.ist_onion(nackt.split("=", 1)[1]))


def setze_tor(conf: str, an: bool, onion_adresse: str = "") -> str:
    """Den Tor-Abschnitt in einer BESTEHENDEN Konfiguration umlegen."""
    zeilen = _ohne_block(conf, _TORBLOCK_ANFANG, _TOR_SCHLUESSEL,
                         _ist_onion_zeile)
    block = (tor_block(onion_adresse) if an else TOR_AUS).splitlines()
    # Dorthin, wo er beim Neubau auch steht: hinter das Upload-Budget.
    for i, zeile in enumerate(zeilen):
        if zeile.strip().startswith("maxuploadtarget="):
            zeilen[i + 1:i + 1] = ["", *block]
            break
    else:
        zeilen += ["", *block]
    return "\n".join(zeilen).rstrip() + "\n"


def lies_tor(conf: str) -> bool:
    """Steht Tor an?

    Am onion= -- der Proxy steht in jeder Fassung des Abschnitts, der alten
    und der neuen. Bis 0.62.0 wurde hier listenonion gelesen; das steht seit
    0.63.0 immer auf 0, weil Tor die Dienste selbst haelt.
    """
    return any(z.strip().startswith("onion=") for z in conf.splitlines())


def lies_onion(conf: str) -> str:
    """Die eigene .onion, die die Datei ankuendigt -- oder ""."""
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if _ist_onion_zeile(nackt):
            return nackt.split("=", 1)[1].strip()
    return ""


def tor_nach_altem_muster(conf: str) -> bool:
    """Legt bitcoind laut Datei seinen Onion-Dienst noch selbst an (bis 0.62.0)?"""
    zeilen = {z.strip() for z in conf.splitlines()}
    return "listenonion=1" in zeilen or any(
        z.startswith("torcontrol=") for z in zeilen)


def adressen_fuer_netze(adressen, ipv4: bool, ipv6: bool) -> list:
    """Nur die Adressen behalten, deren Netz auch eingeschaltet ist.

    Sonst wuerbe der Knoten mit einer IPv6-Adresse, waehrend IPv6 aus ist --
    eine Einladung, die niemand annehmen kann. Namen kommen hier nicht mehr
    an: dyndns.loese_auf hat sie vorher zu IPs gemacht.
    """
    behalten = []
    for a in adressen:
        try:
            art = ipaddress.ip_address(str(a).strip())
        except ValueError:
            continue
        if art.version == 4 and ipv4:
            behalten.append(str(a).strip())
        elif art.version == 6 and ipv6:
            behalten.append(str(a).strip())
    return behalten


def setze_indizes(conf: str, an: bool) -> str:
    """txindex und Blockfilter in einer BESTEHENDEN Konfiguration umlegen.

    Alle drei Schalter zusammen, nie einzeln -- siehe INDEX_SCHALTER.

    Wie bei setze_dbcache wird die Datei gezielt geaendert statt neu gebaut:
    alles andere bleibt Zeichen fuer Zeichen stehen, auch die rpcauth-Zeile,
    ohne die sich die Anwendung von ihrem eigenen Knoten aussperren wuerde.
    """
    zeilen = []
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        # Die alten Schalter und die Erklaerungen dazu fallen weg; der neue
        # Block bringt seine eigenen mit.
        if any(nackt.startswith(f"{name}=") for name in INDEX_SCHALTER):
            continue
        if nackt.startswith("# ") and "Indizes" in nackt:
            continue
        zeilen.append(zeile)

    block = (INDIZES_AN if an else INDIZES_AUS).splitlines()
    # Dorthin, wo sie beim Neubau auch stehen: vor prune. Fehlt die Zeile
    # (fremd bearbeitete Datei), kommt der Block ans Ende -- die Reihenfolge
    # ist Core egal.
    for i, zeile in enumerate(zeilen):
        if zeile.strip().startswith("prune="):
            zeilen[i:i] = block + [""]
            break
    else:
        zeilen += ["", *block]
    return "\n".join(zeilen).rstrip() + "\n"


def lies_indizes(conf: str) -> bool:
    """Sind die Indizes gerade an? Die Datei ist die Wahrheit, nicht ein Merker."""
    for zeile in conf.splitlines():
        if zeile.strip().startswith("txindex="):
            return zeile.strip().split("=", 1)[1].strip() not in ("0", "")
    return False


def lies_dbcache(conf: str) -> Optional[int]:
    """Was gerade eingestellt ist -- None, wenn die Zeile fehlt."""
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if nackt.startswith("dbcache="):
            try:
                return int(nackt.split("=", 1)[1])
            except ValueError:
                return None
    return None


def setze_adressen(conf: str, adressen) -> str:
    """Die externalip-Zeilen einer BESTEHENDEN Konfiguration austauschen.

    Der naheliegende Weg waere, die Datei aus den urspruenglichen Antworten
    neu zu bauen. Der scheitert aber bei jedem, der vor 0.4.1 eingerichtet
    hat -- damals wurde die Wahl nicht festgehalten. Und er ist unnoetig: die
    Datei SELBST ist die Wahrheit. Hier aendert sich genau eine Sache, alles
    andere bleibt Zeichen fuer Zeichen stehen -- auch die rpcauth-Zeile, ohne
    die sich die Anwendung von ihrem eigenen Knoten aussperren wuerde.
    """
    behalten = []
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        # Die eigene .onion gehoert zum Tor-Abschnitt, nicht zu den Adressen,
        # die ein DNS-Name liefert. Sie hier zu entfernen hiesse, sie bei
        # jeder Zwangstrennung aus der Ankuendigung zu nehmen.
        if nackt.startswith("externalip=") and not _ist_onion_zeile(nackt):
            continue
        if nackt in ADRESSE_AUS.splitlines():
            continue
        behalten.append(zeile)

    block = adressblock(adressen)
    # Direkt hinter discover=1, wo die Zeilen auch beim Neubau stehen. Fehlt
    # die Zeile (fremd bearbeitete Datei), kommt der Block ans Ende -- die
    # Reihenfolge ist Core egal, die Lesbarkeit leidet nur minimal.
    for i, zeile in enumerate(behalten):
        if zeile.strip() == "discover=1":
            behalten[i + 1:i + 1] = block.splitlines()
            break
    else:
        behalten += ["", *block.splitlines()]
    return "\n".join(behalten).rstrip() + "\n"


def adressblock(adressen) -> str:
    """externalip-Zeilen aus den angegebenen Adressen.

    Im Container sieht Core nur die Docker-interne 172.x. Die ist nicht
    routbar, also kuendigt er ohne diese Angabe keine Clearnet-Adresse an --
    und wird nicht gefunden, selbst wenn der Port im Router offen steht.
    Genau dieser Fall trat am 26.08.2026 auf: erreichbar war der Port,
    angekuendigt war nur die Onion-Adresse.
    """
    # Eintraege mit Steuerzeichen fallen weg statt in die Datei zu wandern.
    # Bis hierher kommen sie ohnehin nicht: dyndns.loese_auf laesst nur
    # gueltige IPs und aufloesbare Namen durch. Aber dieser Schutz gehoert
    # nicht in eine andere Funktion.
    sauber = []
    for a in adressen:
        try:
            wert = nur_eine_zeile(a or "")
        except ValueError:
            continue
        if wert and not onion.ist_onion(wert):
            sauber.append(wert)
    if not sauber:
        return ADRESSE_AUS
    zeilen = ["# Unter diesen Adressen bietet sich der Knoten dem Netz an."]
    zeilen += [f"externalip={a}" for a in sauber]
    return "\n".join(zeilen)


@dataclass
class Knoteneinstellungen:
    """Was der Nutzer im Assistenten waehlt."""
    speichergrenze_mb: int = 2500
    upload_gb_pro_monat: int = 300
    verbindungen: int = 80
    tor_aktiv: bool = True
    # Unter welchen Adressen sich der Knoten dem Netz anbietet. Ohne das kennt
    # Core im Container nur die Docker-interne 172.x -- die ist nicht routbar,
    # also kuendigt er gar nichts an und wird nicht gefunden, auch bei offenem
    # Port. Ein Hostname ist hier erlaubt und bei wechselnder IP der bessere
    # Weg; Core loest ihn allerdings nur beim Start auf.
    externe_adressen: tuple = ()
    im_erstsync: bool = True
    # Die eigene .onion, wie Tor sie hinterlegt hat. Leer, solange Tor sie
    # noch nicht kennt oder die Betriebsart keine vorsieht.
    onion_adresse: str = ""
    # Nur das Compose-Netz darf an die RPC-Schnittstelle.
    rpc_netz: str = RPC_COMPOSE_NETZ
    # Leer heisst: nur das Compose-Netz. Sonst ein CIDR wie 192.168.1.0/24.
    rpc_heimnetz: str = ""
    zugang: rpcauth.RpcZugang = field(default=None)

    def __post_init__(self) -> None:
        if self.zugang is None:
            self.zugang = rpcauth.erzeuge()


def lade_vorlage(name: str) -> str:
    return (VORLAGEN / name).read_text(encoding="utf-8")


def baue_tor(dienste, praefix: str = netz.PRAEFIX_VORGABE) -> str:
    """Die torrc -- mit den Onion-Diensten, die diese Wahl vorsieht.

    Ohne Zeitstempel, anders als bitcoind.conf und lnd.conf: der Waechter
    vergleicht die Datei im Ganzen, und ein Stempel machte jede Fassung
    "neu" -- Tor startete bei jedem Durchgang ohne Anlass neu.
    """
    return services.rendere(lade_vorlage("torrc.tmpl"), {
        "ONION_DIENSTE": onion.torrc_block(dienste, praefix),
    })


def hole_oder_erzeuge_zugang(ablage) -> rpcauth.RpcZugang:
    """Die RPC-Zugangsdaten EINMAL erzeugen und dann behalten.

    Vorher entstanden bei jedem Schreiben der Konfiguration neue Zugangsdaten:
    der Hash landete in der bitcoin.conf, das Klartext-Passwort wurde
    weggeworfen. Die Anwendung konnte danach nie mit bitcoind sprechen -- also
    weder Fortschritt noch Blockhoehe anzeigen -- und jede Neukonfiguration
    haette einen laufenden Knoten von seinen Zugangsdaten getrennt.
    """
    gespeichert = ablage.lies_geheim("bitcoind-rpc")
    if gespeichert:
        return rpcauth.RpcZugang(
            benutzer=gespeichert["benutzer"],
            passwort=gespeichert["passwort"],
            rpcauth=gespeichert["rpcauth"],
        )
    neu = rpcauth.erzeuge()
    ablage.schreibe_geheim("bitcoind-rpc", {
        "benutzer": neu.benutzer, "passwort": neu.passwort, "rpcauth": neu.rpcauth,
    })
    return neu


def baue_bitcoind(einstellungen: Knoteneinstellungen) -> str:
    werte: Dict[str, str] = {
        "ERZEUGT_AM": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "RPCAUTH": einstellungen.zugang.rpcauth,
        "RPC_FREIGABE": rpc_freigabe_block(einstellungen.rpc_heimnetz,
                                           einstellungen.rpc_netz),
        "MAXCONNECTIONS": str(einstellungen.verbindungen),
        "MAXUPLOADTARGET": str(
            profiles.upload_gb_pro_monat_zu_mib_pro_tag(einstellungen.upload_gb_pro_monat)
        ),
        "DBCACHE": str(
            profiles.dbcache_mb(einstellungen.speichergrenze_mb, einstellungen.im_erstsync)
        ),
        "TOR_BLOCK": (tor_block(einstellungen.onion_adresse)
                      if einstellungen.tor_aktiv else TOR_AUS),
        "EXTERNE_ADRESSEN": adressblock(einstellungen.externe_adressen),
        # Waehrend des Erstabgleichs aus, danach an. Die Anwendung legt den
        # Schalter selbst um, sobald die Kette steht.
        "INDIZES": INDIZES_AUS if einstellungen.im_erstsync else INDIZES_AN,
    }
    return services.rendere(lade_vorlage("bitcoin.conf.tmpl"), werte)


# ---------------------------------------------------------------- Lightning

# Der Alias reist im Gossip als Feld fester Groesse: 32 BYTE, nicht 32
# Zeichen. "Müllers Knoten" braucht in UTF-8 mehr Platz als es Buchstaben hat,
# und ein Emoji vier. Wer nach Zeichen zaehlt, baut einen Alias, den LND beim
# Start ablehnt -- und der Fehler taucht dann in einem Container-Protokoll auf,
# nicht im Eingabefeld.
ALIAS_MAX_BYTE = 32

# Die kleinste Kanalgroesse, die dieser Knoten ANNIMMT -- und der eine Wert,
# der darueber entscheidet, ob ein eingehender Kanal ueberhaupt zustande
# kommt. LNDs eigene Beschreibung (sample-lnd.conf, v0.21.3-beta): "The
# smallest channel size (in satoshis) that we should accept. Incoming
# channels smaller than this will be rejected."
#
# DASS ER EINSTELLBAR IST, ist der Befund vom 18.09.2026. Er stand fest im
# Quelltext -- ausgerechnet die Einstellung, die entscheidet, ob man ein
# Geschenk annehmen darf. Aufgefallen ist es an dem ersten
# Liquiditaets-Ring: der laeuft ueber 100.000 sat, und der Wert stand auf
# genau 100.000. Das geht gerade noch durch ("smaller than" ist echt
# kleiner), hat aber NULL Abstand -- oeffnet die Gegenstelle aus irgendeinem
# Grund 99.500, lehnt der eigene Knoten den Kanal ab, den man sich gerade
# verdient hat. Und es saehe aus, als haette der andere nicht geliefert.
MINCHANSIZE_VORGABE = 100_000

# LNDs eigene Untergrenze fuers OEFFNEN (funding.MinChanFundingSize).
# Darunter entsteht ohnehin kein Kanal, den man annehmen koennte.
MINCHANSIZE_MIN = 20_000

# Die groesste Kanalgroesse ohne Wumbo: 2^24-1 sat. Wer seine Untergrenze
# darueber setzt, lehnt jeden gewoehnlichen Kanal ab -- das ist keine
# Einstellung mehr, das ist ein Tippfehler.
MINCHANSIZE_MAX = 16_777_215

# Bitcoin-Orange, dieselbe Farbe wie im Logo. Sie erscheint im Graphen und auf
# amboss.space.
ALIAS_VORGABE = "SatoshiCortex"
FARBE_VORGABE = "#f7931a"

_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class Lightningeinstellungen:
    """Was der Nutzer im Lightning-Ablauf waehlt.

    Getrennt von den Knoteneinstellungen: das sind zwei Netze mit zwei
    Lebenslaeufen. Bitcoin ist eingerichtet, lange bevor hier die erste Frage
    gestellt wird.
    """
    # EINE Stelle fuer den Namen. Er stand hier als nackte Zeichenkette, und
    # lightning_bereitstellen uebergab ihn nie -- also hiess JEDER Knoten
    # dieser Software "SatoshiCortex", auch des Betreibers. Am 09.09.2026:
    # "ich moechte nicht das alles immer nur satoshicortex heisst!!"
    alias: str = ALIAS_VORGABE
    farbe: str = FARBE_VORGABE
    # Keine Grundgebuehr. Der Netz-Median lag 2026 bei rund 0,444 Sat, aber
    # die Wegfindung bestraft Grundgebuehren staerker als ppm -- viele
    # Routing-Knoten setzen sie deshalb auf null.
    basefee_msat: int = 0
    # ppm, und bewusst NICHT die 2000 aus der Lightning-Labs-Vorlage: die
    # zielt auf grosse Router, und mit ihr wuerde der Knoten schlicht
    # gemieden.
    #
    # Dass hier ueberhaupt eine feste Zahl steht, ist eine Notwendigkeit und
    # kein Wert, auf den man sich verlassen soll: sie gilt fuer die Zeit,
    # bevor der Knoten selbst gemessen hat. Sobald LNDs Netzkarte steht,
    # liest satcortex/gebuehren.py taeglich aus dem eigenen Graphen, was das
    # Netz wirklich nimmt -- und die Oberflaeche zeigt DIESE Zahl, nicht
    # diese hier. Die Groessenordnung stammt aus einer Messung vom
    # 04.09.2026; sie altert, und genau deshalb haengt nichts mehr an ihr.
    feerate_ppm: int = 100
    # Die kleinste Kanalgroesse, die wir ANNEHMEN. Laut LNDs eigener
    # Beschreibung (sample-lnd.conf, v0.21.3-beta) betrifft die Einstellung
    # ausschliesslich eingehende Kanaele: "The smallest channel size (in
    # satoshis) that we should accept. Incoming channels smaller than this
    # will be rejected." Was der Knoten SELBST oeffnet, begrenzt sie nicht.
    #
    # Bis zum 04.09.2026 stand hier eine Million -- aus der Routing-Knoten-
    # Planung, wo Kanaele unter dieser Groesse tatsaechlich kaum etwas
    # weiterleiten. Fuer einen Knoten, der klein anfaengt -- etwa mit rund
    # hundert Euro, also rund 146.000 sat --, war das falsch herum gedacht.
    # Ein eingehender Kanal ist fuer ihn geschenkte
    # Empfangs-Liquiditaet -- die Gegenstelle zahlt die On-Chain-Gebuehr und
    # bindet ihr eigenes Geld. Einen von 500.000 sat abzulehnen, weil er
    # unter einer Million liegt, waere das Gegenteil von hilfreich gewesen.
    #
    # Die Entscheidung vom 04.09.2026: eine kleine Groesse muss gehen, groesser
    # geht dann immer. Also eine Untergrenze in seiner
    # Groessenordnung statt in der eines Grossrouters. LNDs eigene Vorgabe
    # waere 20.000 -- so tief muss es nicht, das waere gegenueber seinem
    # eigenen Kanal kaum noch etwas.
    minchansize: int = MINCHANSIZE_VORGABE
    # Wie der Knoten im Netz auftritt. Drei Moeglichkeiten, und keine ist
    # fuer alle richtig:
    #
    #   "tor"    Nur ueber Tor. Vollwertiges Mitglied -- erreichbar, im
    #            Graphen, kann weiterleiten -- aber ohne dass jemand die IP
    #            erfaehrt. Langsamer, und man braucht Gegenstellen, die Tor
    #            sprechen.
    #   "hybrid" Tor UND Clearnet. Schneller und besser erreichbar; die
    #            eigene IP ist damit oeffentlich.
    #   "still"  Gar nicht ankuendigen. Nur ausgehende Kanaele, kein
    #            Weiterleiten -- im Graphen eine Sackgasse.
    #
    # Vorgabe ist "tor": wer nicht ausdruecklich waehlt, soll nicht
    # versehentlich seine Adresse preisgeben. Die Wahl selbst gehoert in den
    # Lightning-Aufbau, nicht in eine Vorgabe.
    sichtbarkeit: str = "tor"
    # Woraus sich LND beim Start selbst entsperrt. Leer heisst: von Hand.
    #
    # Steht hier, damit ein NEUBAU der Konfiguration die Zeile nicht verliert.
    # Bis zum 05.09.2026 wurde sie nur nachtraeglich in die bestehende Datei
    # gesetzt (setze_entsperrdatei) -- die Vorlage kannte sie gar nicht. Wer
    # Monate spaeter eine Einstellung aendert und die Datei damit neu bauen
    # laesst, haette sie stillschweigend verloren: der Knoten bliebe nach dem
    # naechsten Neustart gesperrt und damit offline, ohne dass irgendwo etwas
    # danebenstuende.
    #
    # Aus dem Betrieb, 05.09.2026 zu den Swap-Bindungen: "dann muss unser System so
    # sauber und stabil laufen, dass wir wirklich 60 Monate am Stueck online
    # bleiben und nicht zwischendurch staendig Abbrueche haben." Genau das
    # waere so ein Abbruch gewesen -- und der teuerste, weil unbemerkt.
    entsperrdatei: str = ""
    tor_aktiv: bool = True
    externe_adressen: tuple = ()
    # Von aussen, fuer die angekuendigte Turm-Adresse. Siehe settings.py.
    wachturm_port: int = 9911
    # Die beiden .onion, wie Tor sie hinterlegt hat (onion.lies_adresse).
    # Leer, solange Tor sie noch nicht kennt.
    onion_adresse: str = ""
    wachturm_onion: str = ""


def pruefe_minchansize(wert: Any) -> int:
    """Die Untergrenze fuer eingehende Kanaele -- oder ein lesbarer Fehler."""
    try:
        zahl = int(wert)
    except (TypeError, ValueError):
        raise ValueError("Die Untergrenze muss eine Zahl sein.")
    if zahl < MINCHANSIZE_MIN or zahl > MINCHANSIZE_MAX:
        raise ValueError(
            f"Die Untergrenze liegt zwischen {MINCHANSIZE_MIN} und "
            f"{MINCHANSIZE_MAX} Satoshi.")
    return zahl


def pruefe_alias(wert: str) -> str:
    """Alias auf das begrenzen, was durch den Gossip passt."""
    alias = nur_eine_zeile(wert)
    if not alias:
        raise ValueError("Der Alias darf nicht leer sein.")
    laenge = len(alias.encode("utf-8"))
    if laenge > ALIAS_MAX_BYTE:
        raise ValueError(
            f"Der Alias ist {laenge} Byte lang, erlaubt sind "
            f"{ALIAS_MAX_BYTE}. Umlaute und Emoji zaehlen mehrfach."
        )
    return alias


def pruefe_farbe(wert: str) -> str:
    farbe = nur_eine_zeile(wert)
    if not _FARBE.match(farbe):
        raise ValueError("Die Farbe muss als #rrggbb angegeben werden.")
    return farbe.lower()


# setze_lnd_adressen() stand hier bis zum 09.09.2026 und tauschte einzelne
# externalip-Zeilen aus. Sie war der halbe Weg und damit die Ursache von
# Befund 9: eine geaenderte Sichtbarkeit erreichte LND nie, weil nur die
# Adresszeilen geflickt wurden -- und auch das nur, solange
# "adresse_ankuendigen" AN war. Wer auf "nur ueber Tor" umstellte, schaltete
# genau das ab und schnitt sich den einzigen Weg ab.
#
# Ersetzt durch lnd_soll(), das die ganze Datei aus dem heutigen Zustand
# baut. Die Erkenntnis dahinter bleibt gueltig und steht jetzt dort: ein
# Lightning-Knoten hat einen Pubkey als Identitaet, und BOLT 7 laesst ein
# node_announcement mit neuerem Zeitstempel das alte samt Adressen netzweit
# ersetzen -- LND schickt das von allein, sobald es die neue Adresse kennt.

def lies_lnd_adressen(conf: str) -> list:
    """Welche CLEARNET-Adressen LND laut Konfiguration gerade ankuendigt.

    Ohne die .onion: die kommt aus Tors Datei, nicht aus der
    Adressnachfuehrung -- und lnd_adressen_halten darf sie bei einem
    DNS-Aussetzer nicht als Clearnet-Adresse wieder einsetzen.
    """
    return [z.strip().split("=", 1)[1].strip()
            for z in conf.splitlines()
            if z.strip().startswith("externalip=")
            and not _ist_onion_zeile(z.strip())]


def lies_lnd_onion(conf: str) -> str:
    """Die .onion, die LND laut Datei ankuendigt, ohne Port -- oder ""."""
    wert = lies_onion(conf)
    return wert.rsplit(":", 1)[0] if wert else ""


def lies_wachturm_onion(conf: str) -> str:
    """Die .onion des Wachturms laut Datei, ohne Port -- oder ""."""
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if nackt.startswith("watchtower.externalip="):
            wert = nackt.split("=", 1)[1].strip()
            if onion.ist_onion(wert):
                return wert.rsplit(":", 1)[0]
    return ""


def lnd_ohne_onion(conf: str) -> str:
    """Die .onion von Knoten und Wachturm aus einer lnd.conf nehmen.

    Fuer "Wallet loeschen": die neue Wallet darf nicht einen Augenblick unter
    der alten Adresse auftreten. Kaeme Tor mit den neuen nicht rechtzeitig,
    hielte das Nachziehen sonst die alte fest -- und verbaende im Graphen den
    alten Knoten mit dem neuen.
    """
    behalten = []
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        schluessel, _, wert = nackt.partition("=")
        if schluessel in ("externalip", "watchtower.externalip") \
                and onion.ist_onion(wert):
            continue
        behalten.append(zeile)
    return "\n".join(behalten).rstrip() + "\n"


def lnd_nach_altem_muster(conf: str) -> bool:
    """Legt LND laut Datei seine Onion-Dienste noch selbst an (bis 0.62.0)?"""
    zeilen = {z.strip() for z in conf.splitlines()}
    return "tor.v3=true" in zeilen or any(
        z.startswith("tor.control=") for z in zeilen)


def _pruefe_onion(adresse: str) -> str:
    if adresse and not onion.ist_gueltig(adresse):
        raise ValueError(f"Keine gueltige Onion-Adresse: {adresse!r}")
    return adresse


def lnd_adressblock(adressen, onion_adresse: str = "") -> str:
    """externalip-Zeilen fuer LND.

    Getrennt von adressblock(): dieselbe Idee, aber ein anderes Ziel. Bei
    Lightning gehoert der Port dazu -- ohne ihn nimmt LND 9735 an, und das
    stimmt nur, solange niemand den Port in der Compose geaendert hat.

    Die .onion steht mit dem Port, unter dem Tor sie anbietet. Der ist
    unabhaengig von LIGHTNING_P2P_PORT: der aendert nur die Weiterleitung am
    Geraet, nicht den Onion-Dienst.
    """
    sauber = []
    if _pruefe_onion(onion_adresse):
        sauber.append(f"{onion_adresse}:{onion.DIENSTE['lnd'].port}")
    for a in adressen:
        try:
            wert = nur_eine_zeile(a or "")
        except ValueError:
            continue
        if wert and not onion.ist_onion(wert):
            sauber.append(wert)
    if not sauber:
        return LND_ADRESSE_AUS
    zeilen = ["# Unter diesen Adressen bietet sich der Knoten dem Netz an."]
    zeilen += [f"externalip={a}" for a in sauber]
    return "\n".join(zeilen)


def _ohne_port(adresse: str) -> str:
    """Den Port von einer Adresse abnehmen -- das Gegenstueck zu _mit_port.

    Die angekuendigten Lightning-Adressen tragen schon den Kanal-Port;
    lnd_adressen_halten haengt ihn an. _mit_port laesst eine Adresse, die
    einen Port mitbringt, unveraendert. Haengte man den Turm-Port also einfach
    an, stuende der Turm unter host:9735 im Verzeichnis -- dort ist er nie.
    """
    a = str(adresse).strip()
    if a.startswith("["):
        return a.split("]", 1)[0] + "]"
    if a.count(":") > 1:
        return a                        # blankes IPv6, ohne Port
    return a.split(":", 1)[0]


# Bewusst OHNE das Wort, das die Anonymitaetstests suchen: diese Zeile steht
# in jeder Betriebsart ohne Turm-Adresse in der Datei.
WACHTURM_KEINE_ADRESSE = """# Der Wachturm nennt keine Adresse. Bei "nur ueber Tor" und "Tor und
# Clearnet" steht hier seine eigene .onion, sobald Tor sie angelegt hat."""


def wachturm_adressblock(adressen, port: int, onion_adresse: str = "") -> str:
    """Unter welcher Clearnet-Adresse andere unseren Wachturm eintragen.

    Befund vom 17.09.2026: der Turm war seit dem ersten Tag eingeschaltet,
    die Oberflaeche zeigte seine Adresse zum Weitergeben -- und erreichen
    konnte ihn niemand. Kein Port in der Compose, und ohne diese Zeile nennt
    LND fuer den Turm keine Clearnet-Adresse (sample-lnd.conf: sie "will make
    the full URI (pubkey@host:port) available").

    Dieselbe Regel wie bei den Kanal-Adressen, aus demselben Grund: nur im
    Hybrid-Betrieb. Das entscheidet baue_lnd, nicht diese Funktion.
    """
    zeilen = []
    if _pruefe_onion(onion_adresse):
        zeilen += [
            "# Ueber Tor erreichbar, ohne Portfreigabe. Eine eigene .onion,",
            "# getrennt von der des Knotens.",
            f"watchtower.externalip={onion_adresse}:"
            f"{onion.DIENSTE['wachturm'].port}"]
    sauber = []
    for a in adressen:
        try:
            wert = nur_eine_zeile(a or "")
        except ValueError:
            continue
        if wert and not onion.ist_onion(wert):
            sauber.append(_mit_port(_ohne_port(wert), port))
    if sauber:
        zeilen += ["# Im Clearnet erreichbar -- dafuer gehoert der Port im "
                   "Router weitergeleitet."]
        zeilen += [f"watchtower.externalip={a}" for a in sauber]
    return "\n".join(zeilen) if zeilen else WACHTURM_KEINE_ADRESSE


# ---------------------------------------------------- Wallet automatisch auf
#
# Ein Routing-Knoten, der nach jedem Neustart auf jemanden wartet, der ein
# Passwort tippt, ist kein Routing-Knoten. Reputation im Lightning-Netz baut
# sich ueber Betriebszeit auf; jede Stunde gesperrte Wallet ist eine Stunde,
# in der Zahlungen an diesem Knoten scheitern.
#
# Was das kostet, gehoert dazugesagt: das Passwort liegt neben der Wallet. Es
# schuetzt sie damit NICHT gegen jemanden, der die Platte hat. Dagegen
# schuetzt nur, dass dort nur so viel liegt, wie verschmerzbar ist -- und der
# Seed, der auf Papier gehoert und nirgends sonst.
#
# ZWEI PHASEN, und das ist keine Umstaendlichkeit. LND bricht den Start ab,
# wenn die Entsperrdatei gesetzt ist und noch keine Wallet existiert:
#   "wallet unlock password file was specified but wallet does not exist"
# (config_builder.go, v0.21.2-beta). Der Ausweg waere
# wallet-unlock-allow-create -- den LND selbst nicht empfiehlt, weil der
# Anlege-Aufruf in diesem Zustand ohne Macaroon auskommt und ein Fremder
# einen eigenen Seed unterschieben koennte. Also: erst Wallet, dann Datei.
ENTSPERRDATEI_ANFANG = ("# Die Wallet wird beim Start automatisch entsperrt",)


def setze_entsperrdatei(conf: str, pfad: str) -> str:
    """Automatisches Entsperren ein- oder ausschalten.

    Leerer Pfad heisst aus -- dann fragt LND beim Start nach dem Passwort.
    """
    zeilen = _ohne_block(conf, ENTSPERRDATEI_ANFANG,
                         ("wallet-unlock-password-file=",))
    if pfad:
        block = [
            "# Die Wallet wird beim Start automatisch entsperrt -- sonst",
            "# stuende der Knoten nach jedem Neustart still, bis jemand ein",
            "# Passwort tippt. Das Passwort liegt dafuer neben der Wallet und",
            "# schuetzt sie nicht gegen jemanden, der die Platte hat. Was",
            "# wirklich schuetzt, ist der Seed auf Papier.",
            # Durch dieselbe Wache wie jeder andere freie Wert in dieser
            # Datei. Heute kommt der Pfad ausschliesslich von uns selbst --
            # aber diese eine Schreibfunktion war die einzige im Modul, die
            # sich nicht so verteidigt wie ihre Nachbarn. Befund vom
            # 22.09.2026.
            f"wallet-unlock-password-file={nur_eine_zeile(str(pfad))}",
        ]
        # Hinter die Identitaet, noch in den [Application Options].
        #
        # Die Leerzeile gehoert VOR den Block, nicht dahinter: _ohne_block
        # verschluckt beim Entfernen die Leerzeile davor. Andersherum bliebe
        # bei jedem Aus- und Einschalten eine Leerzeile mehr stehen -- die
        # Datei waere nach ein paar Runden voller Luecken, und der Vergleich
        # "hat sich etwas geaendert" schluege ohne Anlass an.
        for i, zeile in enumerate(zeilen):
            if zeile.strip().startswith("color="):
                zeilen[i + 1:i + 1] = ["", *block]
                break
        else:
            zeilen += ["", *block]
    return "\n".join(zeilen).rstrip() + "\n"


def lies_entsperrdatei(conf: str) -> str:
    for zeile in conf.splitlines():
        nackt = zeile.strip()
        if nackt.startswith("wallet-unlock-password-file="):
            return nackt.split("=", 1)[1].strip()
    return ""


def _tor_block(einstellungen: Lightningeinstellungen) -> str:
    """Der Tor-Abschnitt, passend zum gewaehlten Auftritt."""
    if not einstellungen.tor_aktiv:
        return LND_TOR_AUS
    if einstellungen.sichtbarkeit == "hybrid":
        return LND_TOR_HYBRID
    if einstellungen.sichtbarkeit == "still":
        return LND_TOR_STILL
    return LND_TOR_NUR


def _onion_wenn_gewollt(einstellungen: Lightningeinstellungen,
                        adresse: str) -> str:
    """Eine .onion nur in den Betriebsarten, fuer die Tor sie anlegt.

    Dieselbe Regel wie onion.dienste_fuer -- eine Stelle entscheidet, ob es
    den Dienst gibt, und dieselbe, ob er angekuendigt wird. Sonst stuende bei
    "still" eine Adresse im Graphen, hinter der Tor nichts mehr anbietet.
    """
    gewollt = onion.dienste_fuer(einstellungen.tor_aktiv,
                                 einstellungen.sichtbarkeit)
    return adresse if gewollt else ""


def baue_lnd(einstellungen: Lightningeinstellungen) -> str:
    werte: Dict[str, str] = {
        "ERZEUGT_AM": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "ALIAS": pruefe_alias(einstellungen.alias),
        "FARBE": pruefe_farbe(einstellungen.farbe),
        "BASEFEE": str(int(einstellungen.basefee_msat)),
        "FEERATE": str(int(einstellungen.feerate_ppm)),
        "MINCHANSIZE": str(int(einstellungen.minchansize)),
        "TOR_BLOCK": _tor_block(einstellungen),
        # NUR im Hybrid-Betrieb wird eine Clearnet-Adresse angekuendigt.
        #
        # Beim ersten Anlauf stand hier "ausser bei still" -- damit kuendigte
        # ausgerechnet die Betriebsart "nur ueber Tor" weiter den eigenen
        # Hostnamen an. Der Ausgang lief sauber durch Tor, und die IP stand
        # trotzdem fuer jeden im Graphen. Beim Durchsehen der drei erzeugten
        # Dateien aufgefallen, bevor es je eine Wallet gab.
        "EXTERNE_ADRESSEN": lnd_adressblock(
            einstellungen.externe_adressen
            if einstellungen.sichtbarkeit == "hybrid" else (),
            _onion_wenn_gewollt(einstellungen, einstellungen.onion_adresse)),
        # Der Wachturm unter derselben Regel. Seine .onion legt Tor an, als
        # eigenen Dienst neben dem des Knotens.
        "WACHTURM_ADRESSEN": wachturm_adressblock(
            einstellungen.externe_adressen
            if einstellungen.sichtbarkeit == "hybrid" else (),
            einstellungen.wachturm_port,
            _onion_wenn_gewollt(einstellungen, einstellungen.wachturm_onion)),
    }
    conf = services.rendere(lade_vorlage("lnd.conf.tmpl"), werte)
    # Nach dem Rendern, mit derselben Funktion wie beim nachtraeglichen
    # Umschalten -- eine Stelle, an der die Zeile entsteht, statt zwei.
    return setze_entsperrdatei(conf, einstellungen.entsperrdatei)


# ─────────────────────────────────────────── lnd.conf nachziehen ─────
#
# BIS ZUM 09.09.2026 WURDE DIESE DATEI GENAU EINMAL GESCHRIEBEN.
#
# lightning_bereitstellen() stieg mit `if ablage.lies("lnd"): return` aus,
# und das Nachfuehren tauschte nur die externalip-Zeilen -- und auch das nur,
# wenn "adresse_ankuendigen" AN war. Wer auf "nur ueber Tor" umstellte, setzte
# damit genau dieses Haekchen auf aus und schnitt sich den einzigen Weg ab,
# auf dem die Aenderung je angekommen waere.
#
# Folge: Sichtbarkeit, Alias und Farbe waren nach der Einrichtung
# unveraenderlich. Der Schalter stand auf "nur ueber Tor", und der Knoten
# kuendigte weiter die Wohnanschrift an. Der Betreiber fragte am 09.09.2026
# ausdruecklich danach -- "wenn ich spaeter mal sage ich will nur noch tor,
# ob das dann alles auch noch funktioniert?" -- und die ehrliche Antwort war
# nein.
#
# Der Ersatz ist ein Erbauer statt dreier Flicker: die gewuenschte Datei aus
# dem heutigen Zustand bauen, mit der vorhandenen vergleichen, bei
# Unterschied schreiben.


def wirksam(conf: str) -> tuple:
    """Nur die Zeilen, die ein Dienst tatsaechlich liest -- fuer jeden Dienst.

    Dieselbe Regel wie bei lnd_wirksam, und aus demselben Grund: wer den Text
    vergleicht, startet einen Dienst fuer eine geaenderte Kommentarzeile neu.
    """
    return tuple(z.strip() for z in conf.splitlines()
                 if z.strip() and not z.strip().startswith("#"))


def lnd_wirksam(conf: str) -> tuple:
    """Nur die Zeilen, die LND tatsaechlich liest.

    Der Vergleich MUSS die Kommentare weglassen, und das ist keine
    Kosmetik: baue_lnd stempelt jede Fassung mit ihrem
    Erzeugungszeitpunkt. Ein Vergleich ueber den rohen Text waere damit
    immer verschieden -- der Waechter startete LND bei jedem Durchgang neu,
    und bei abgeschaltetem Auto-Entsperren spraenge dabei jedes Mal die
    Wallet zu. Aus einem Abgleich waere ein Dauerausfall geworden.
    """
    return tuple(z.strip() for z in conf.splitlines()
                 if z.strip() and not z.strip().startswith("#"))


def lnd_muss_neu(vorhanden: str, soll: str) -> bool:
    """Unterscheiden sich die beiden in dem, was LND liest?"""
    return lnd_wirksam(vorhanden) != lnd_wirksam(soll)


def _mit_port(adresse: str, port: int) -> str:
    """Eine Adresse so schreiben, dass LND den Port erkennt.

    Ohne Port nimmt LND 9735 an. Das stimmt genau so lange, wie niemand
    LIGHTNING_P2P_PORT geaendert hat -- und beim ersten Schreiben fehlte er
    tatsaechlich, weil dort die blanken aufgeloesten Adressen durchgereicht
    wurden. Es fiel nie auf, weil die Annahme zufaellig der Vorgabe entsprach.
    """
    a = str(adresse).strip()
    if a.startswith("["):
        return a if "]:" in a else f"{a}:{port}"
    if a.count(":") > 1:
        return f"[{a}]:{port}"          # blankes IPv6
    if ":" in a:
        return a                        # bringt seinen Port schon mit
    return f"{a}:{port}"


def lies_adressen(conf: str) -> list:
    """Die angekuendigten Adressen aus einer bitcoind-Konfiguration.

    Das Gegenstueck zu lies_lnd_adressen. Es gab es nicht, und deshalb
    konnte auch niemand fragen "was steht denn gerade drin?" -- genau die
    Frage, die ein DNS-Aussetzer beantwortet haben will.
    """
    return [z.strip().split("=", 1)[1].strip()
            for z in conf.splitlines()
            if z.strip().startswith("externalip=")
            and not _ist_onion_zeile(z.strip())]


def _halten(bestehende, aufgeloest, ankuendigen: bool, umformen) -> tuple:
    """Die gemeinsame Regel fuer beide Dienste.

    DER HEIKLE FALL ist die voruebergehend gescheiterte Namensaufloesung.
    Ohne diese Regel wuerde ein DNS-Aussetzer von Sekunden die angekuendigte
    Adresse entfernen, den Dienst neu starten und -- bei LND mit
    abgeschaltetem Auto-Entsperren -- die Wallet zusperren. Ein Netzwackler
    darf keinen Knoten anhalten.

    Der Unterschied zum Abschalten ist Absicht: dort hat jemand entschieden,
    und dann verschwindet die Adresse wirklich.
    """
    if not ankuendigen:
        return ()
    if aufgeloest:
        return tuple(umformen(a) for a in aufgeloest)
    return tuple(bestehende)


def adressen_halten(vorhanden: str, aufgeloest, ankuendigen: bool) -> tuple:
    """Fuer bitcoind -- ohne Port, so schreibt Core seine externalip."""
    return _halten(lies_adressen(vorhanden or ""), aufgeloest, ankuendigen,
                   str)


def lnd_adressen_halten(vorhanden: str, aufgeloest, ankuendigen: bool,
                        port: int = 9735) -> tuple:
    """Fuer LND -- mit Port, weil dort ein abweichender moeglich ist."""
    return _halten(lies_lnd_adressen(vorhanden or ""), aufgeloest,
                   ankuendigen, lambda a: _mit_port(a, port))


def lnd_soll(vorhanden: str, einstellungen: Lightningeinstellungen) -> str:
    """Die lnd.conf, wie sie zu diesen Einstellungen gehoert.

    Ein Wert wird ausdruecklich aus der VORHANDENEN Datei uebernommen: der
    Entsperrweg. Er haengt an der Wallet, nicht an der Sichtbarkeit -- wer
    die Betriebsart wechselt, darf nicht nebenbei sein Auto-Entsperren
    verlieren und nach dem naechsten Stromausfall vor einem stillstehenden
    Knoten sitzen.
    """
    conf = baue_lnd(einstellungen)
    bisher = lies_entsperrdatei(vorhanden or "")
    if bisher:
        conf = setze_entsperrdatei(conf, bisher)
    return conf
