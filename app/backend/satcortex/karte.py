"""Was unser Knoten vom Netz weiss -- auf eine Weltkarte gebracht.

Der Unterschied zu einem Explorer, und der Grund, warum es sich lohnt:

Ein Explorer krabbelt das Netz ab und zeigt allen dieselbe Karte. Ein
Bitcoin-Knoten kann das nicht -- es gibt keine Liste aller Knoten, und das ist
Absicht. Was er aber hat, ist sein ADRESSBUCH: jede Adresse, die ihm im Lauf
der Zeit ueber addr-Nachrichten zugetragen wurde. Zehntausende, mit der Zeit.

Das ist keine Notloesung, sondern die ehrlichere Karte: sie zeigt nicht "das
Netz", sondern was DIESER Knoten davon kennengelernt hat. Sie waechst mit ihm.

Drei Quellen, jede mit einer eigenen Aufgabe:

* getaddrmaninfo   -- die genauen Zahlen je Netz. Winzige Antwort, keine
                      einzige Adresse. Daher stammen die Gesamtwerte.
* getnodeaddresses -- die Adressen selbst, aber NUR fuer IPv4 und IPv6. Onion,
                      I2P und CJDNS haben keinen Ort; sie zu holen waere Last
                      fuer nichts, ihre Anzahl steht schon oben.
* getpeerinfo      -- mit wem wir gerade wirklich sprechen.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List, Optional

from . import rpc

log = logging.getLogger(__name__)

# Netze, in denen eine Adresse ueberhaupt einen Ort haben kann.
VERORTBAR = ("ipv4", "ipv6")

# Netze ohne Ort -- nicht aus Mangel an Daten, sondern dem Zweck nach.
ORTLOS = ("onion", "i2p", "cjdns")

# Obergrenze je Netz -- eine Notbremse, kein Regelfall.
#
# Vorher stand hier fest 20.000, und am 27.08.2026 hat der Deckel am echten
# Knoten gegriffen: 42.812 Adressen im Adressbuch, 25.870 angesehen. Die
# Differenz stand nirgends, und IPv4 lag vermutlich haargenau auf der Grenze.
# Ein Deckel, den man der Anzeige nicht ansieht, ist schlimmer als keiner.
#
# Jetzt wird gefragt, was der Knoten laut getaddrmaninfo tatsaechlich hat.
# Nach oben bleibt eine Grenze: das Adressbuch fasst rund 81.000 Eintraege,
# und die alle als JSON zu zerlegen waere auf einem NAS spuerbar.
OBERGRENZE_JE_NETZ = 60000

# Grosszuegiger als die ueblichen fuenf Sekunden: die Antwort kann einige
# Megabyte gross sein, und sie kommt waehrend des Erstabgleichs von einem
# Knoten, der gerade beschaeftigt ist.
ZEITLIMIT_SEKUNDEN = 30.0


# Womit gefragt wird, wenn getaddrmaninfo einmal nicht antwortet.
#
# Der Aufruf sagt nur, WIE VIELE Adressen der Knoten kennt -- er dient dazu,
# die richtige Menge anzufordern. Bis zum 01.09.2026 war ein Aussetzer dort
# das Ende der ganzen Karte: bekannt={} liess verorte_adressbuch jedes Netz
# ueberspringen, adressbuch lieferte ein leeres Buch, karte_auffrischen warf
# es weg ("Knoten antwortet nicht") -- und die Weltkarte blieb leer, bis eine
# halbe Stunde spaeter der naechste Versuch lief. Fuer eine Zahl, die nur die
# Menge bestimmt.
#
# getnodeaddresses gibt von sich aus nicht mehr her, als da ist. Eine
# grosszuegige Vorgabe kostet also nichts ausser einer Zahl, die in der
# Aufschluesselung als geschaetzt zu erkennen ist.
ERSATZMENGE_JE_NETZ = 20000


def bekannte_zahlen(knoten: rpc.Knoten) -> Dict[str, int]:
    """Wie viele Adressen der Knoten je Netz kennt -- die genauen Werte."""
    try:
        roh = knoten.ruf("getaddrmaninfo",
                         zeitlimit=rpc.GEDULD_SEKUNDEN)
    except rpc.Beschaeftigt as fehler:
        log.debug("getaddrmaninfo gerade nicht moeglich: %s", fehler)
        return {}
    except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
        log.info("getaddrmaninfo nicht moeglich: %s -- es wird mit %d je Netz "
                 "gefragt", fehler, ERSATZMENGE_JE_NETZ)
        return {}
    if not isinstance(roh, dict):
        return {}

    heraus: Dict[str, int] = {}
    for netz, werte in roh.items():
        if isinstance(werte, dict) and isinstance(werte.get("total"), int):
            heraus[netz] = werte["total"]
    return heraus


def verorte_adressbuch(knoten: rpc.Knoten, tabelle,
                       bekannt: Dict[str, int]) -> tuple:
    """Das Adressbuch nach Laendern zaehlen.

    Gibt (Zaehlung nach Land, je_netz, Zaehlung nach Gebiet) zurueck. Die Aufschluesselung je Netz ist kein
    Beiwerk: ohne sie stuende auf der Karte eine Laenderverteilung, von der
    niemand weiss, wie viel sie abdeckt -- und niemand merkt, wenn eine
    Obergrenze gegriffen hat.
    """
    zaehlung: Counter = Counter()
    # Zusaetzlich je Gebiet -- das ist die Grundlage fuer den Klick auf ein
    # Land. Gezaehlt wird im selben Durchgang: ein zweiter waere ein zweiter
    # Satz getnodeaddresses-Aufrufe, und die Zahlen koennten auseinanderlaufen.
    nach_gebiet: Counter = Counter()
    je_netz: Dict[str, Dict[str, int]] = {}
    if tabelle is None:
        return zaehlung, je_netz, nach_gebiet

    # Ohne getaddrmaninfo wissen wir nicht, wie viel da ist -- gefragt wird
    # trotzdem. Vorher hiess "keine Zahl" hier "kein Netz", und ein einzelner
    # Aussetzer bei einem Aufruf, der nicht einmal cs_main braucht, liess die
    # ganze Weltkarte fuer eine halbe Stunde leer.
    ohne_zahlen = not bekannt
    for netz in VERORTBAR:
        vorhanden = bekannt.get(netz, 0)
        if not vorhanden and not ohne_zahlen:
            continue
        wieviele = min(vorhanden or ERSATZMENGE_JE_NETZ, OBERGRENZE_JE_NETZ)
        stand = {"bekannt": vorhanden, "gefragt": wieviele,
                 "gesehen": 0, "verortet": 0}
        je_netz[netz] = stand
        try:
            adressen = knoten.ruf("getnodeaddresses", wieviele, netz,
                                  zeitlimit=ZEITLIMIT_SEKUNDEN)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.info("getnodeaddresses(%s) nicht moeglich: %s", netz, fehler)
            continue
        if not isinstance(adressen, list):
            continue
        for eintrag in adressen:
            if not isinstance(eintrag, dict):
                continue
            stand["gesehen"] += 1
            land, gebiet = tabelle.ort(eintrag.get("address", ""))
            if land:
                zaehlung[land] += 1
                stand["verortet"] += 1
                if gebiet:
                    nach_gebiet[gebiet] += 1
    return zaehlung, je_netz, nach_gebiet


def verorte_peers(knoten: rpc.Knoten, tabelle, peers=None) -> Dict:
    """Mit wem wir gerade sprechen -- und wo die sitzen.

    Die Richtung wird bewusst nicht "eingehend/ausgehend" genannt. Die Woerter
    werden staendig verwechselt, weil sie nach Datenrichtung klingen und
    Verbindungsrichtung meinen.
    """
    ergebnis = {"gesamt": 0, "aufgebaut": 0, "angenommen": 0,
                "verortet": 0, "laender": Counter(), "gebiete": Counter(),
                # Wofuer die Gegenstellen UNSERE Adresse halten. Zweitquelle
                # fuer den eigenen Ort, siehe eigener_ort().
                "gesehen_als": Counter()}
    try:
        if peers is None:
            peers = knoten.ruf("getpeerinfo", zeitlimit=rpc.GEDULD_SEKUNDEN)
    except (rpc.NichtErreichbar, rpc.RpcFehler):
        return ergebnis
    if not isinstance(peers, list):
        return ergebnis

    for p in peers:
        if not isinstance(p, dict):
            continue
        ergebnis["gesamt"] += 1
        if p.get("inbound"):
            ergebnis["angenommen"] += 1
        else:
            ergebnis["aufgebaut"] += 1
        if tabelle is None:
            continue
        # "addr" ist "host:port" -- bei IPv6 mit Klammern, also von rechts
        # trennen und Klammern abstreifen.
        land, gebiet = tabelle.ort(_nur_adresse(p.get("addr", "")))
        if land:
            ergebnis["laender"][land] += 1
            ergebnis["verortet"] += 1
            if gebiet:
                ergebnis["gebiete"][gebiet] += 1
        # "addrlocal" ist laut Core-Hilfe "Local address as reported by the
        # peer" und ausdruecklich optional -- eine Gegenstelle muss sie nicht
        # nennen.
        heim = tabelle.land(_nur_adresse(p.get("addrlocal", "")))
        if heim:
            ergebnis["gesehen_als"][heim] += 1
    return ergebnis


def eigener_ort(knoten: rpc.Knoten, tabelle,
                gesehen_als: Optional[Counter] = None,
                adressen: Optional[list] = None) -> Optional[str]:
    """In welchem Land unser eigener Knoten sitzt.

    Das ist der Ursprung der Linien auf der Karte: ohne ihn haengen die
    Verbindungen im Nichts. Zwei Quellen, beide schon im Haus -- keine
    Anfrage nach draussen, kein "wie ist meine IP"-Dienst.

    1. getnetworkinfo.localaddresses -- was der Knoten selbst fuer seine
       Adresse haelt. Der "score" zaehlt, wie oft ihm eine Adresse als die
       eigene gemeldet wurde; die hoechste zuerst.
    2. getpeerinfo.addrlocal -- wofuer die Gegenstellen uns halten. Greift,
       wenn discover abgeschaltet ist oder der Knoten nur ueber Tor laeuft.
       Die Angabe stammt von der Gegenstelle und koennte gelogen sein, daher
       das haeufigste Land ueber alle Peers statt eines einzelnen Zeugen.

    Nur das Laenderkuerzel verlaesst diese Funktion. Die eigene Adresse
    gehoert nicht in eine Weboberflaeche, auch nicht in eine geschuetzte.
    """
    if tabelle is None:
        return None

    # "adressen" reicht der Aufrufer herein: die Kettenlage holt
    # getnetworkinfo ohnehin und legt sie fuer ein paar Sekunden beiseite.
    # Hier ein zweites Mal zu fragen war der Grund fuer die Meldung
    # "getnetworkinfo nicht moeglich: antwortet nicht innerhalb von 15 s" --
    # und eine laengere Leine waere die falsche Antwort gewesen. Von den vier
    # Aufrufen der Karte ist das der einzige, der laut
    # v31.1/src/rpc/net.cpp LOCK(cs_main) nimmt; getaddrmaninfo,
    # getnodeaddresses und getpeerinfo tun es nicht. Er wartet also genau
    # dann, wenn Core den chainstate wegschreibt -- also regelmaessig.
    #
    # Die Schluesselnamen sind die der Kettenlage ("adresse"), nicht die von
    # Core ("address"). Beide werden gelesen, damit ein direkter Aufruf mit
    # Cores Antwort weiterhin geht.
    if adressen is None:
        try:
            netz = knoten.ruf("getnetworkinfo", zeitlimit=rpc.GEDULD_SEKUNDEN)
        except rpc.Beschaeftigt as fehler:
            log.debug("getnetworkinfo gerade nicht moeglich: %s", fehler)
            netz = None
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.info("getnetworkinfo nicht moeglich: %s", fehler)
            netz = None
        if isinstance(netz, dict):
            adressen = netz.get("localaddresses")

    if isinstance(adressen, list):
        eintraege = [e for e in adressen if isinstance(e, dict)]
        eintraege.sort(key=lambda e: e.get("score") or 0, reverse=True)
        for eintrag in eintraege:
            # Onion- und I2P-Adressen stehen hier mit drin und haben keinen
            # Ort -- die Tabelle gibt dafuer None, und wir gehen weiter.
            land = tabelle.land(
                str(eintrag.get("adresse") or eintrag.get("address") or ""))
            if land:
                return land

    if gesehen_als:
        for land, _ in gesehen_als.most_common(1):
            return land
    return None


def _nur_adresse(mit_port: str) -> str:
    """"1.2.3.4:8333" -> "1.2.3.4", "[2a02::1]:8333" -> "2a02::1"."""
    wert = (mit_port or "").strip()
    if wert.startswith("["):
        ende = wert.find("]")
        return wert[1:ende] if ende > 0 else wert
    # IPv6 ohne Klammern hat mehr als einen Doppelpunkt -- da ist nichts
    # abzutrennen, sonst schneidet man eine Zifferngruppe ab.
    if wert.count(":") == 1:
        return wert.rsplit(":", 1)[0]
    return wert


# Wie oft das Adressbuch neu ausgewertet wird. Es waechst langsam -- eine
# halbe Stunde aendert daran nichts Sichtbares, und der Aufruf ist der einzige
# teure in der ganzen Anwendung.
BUCH_INTERVALL_SEKUNDEN = 1800

# Was gilt, solange noch nichts ausgewertet ist. Kein Sonderfall im Aufrufer,
# und die Karte zeigt derweil schon die eigenen Gegenstellen.
LEERES_BUCH: Dict = {"laender": Counter(), "gebiete": Counter(),
                     "bekannt": {}, "je_netz": {},
                     "angesehen": 0, "verortet": 0}


def verorte_lightning(gegenstellen: list, tabelle) -> Dict:
    """Wo das Kapital liegt, das in Kanaelen gebunden ist.

    Dieselbe Ortstabelle wie fuer die Bitcoin-Seite -- ein Ort ist ein Ort,
    egal welches Netz danach fragt.

    Eine Gegenstelle zaehlt EINMAL, auch wenn sie IPv4, IPv6 und eine
    Onion-Adresse ankuendigt: sie sitzt trotzdem an einem Ort. Die erste
    Adresse, zu der es ein Land gibt, gewinnt.

    Wer keinen Ort hat, verschwindet nicht, sondern wird gezaehlt. Eine
    Onion-Adresse hat keinen, und das Kapital liegt trotzdem dort -- es
    wegzulassen ergaebe eine Karte, die weniger zeigt als es gibt, ohne es
    zu sagen.
    """
    ergebnis = {"laender": Counter(), "kapazitaet_je_land": Counter(),
                "gebiete": Counter(), "kapazitaet_je_gebiet": Counter(),
                "verortet": 0, "ohne_ort": 0, "kapazitaet_ohne_ort": 0,
                "gegenstellen": []}
    for g in gegenstellen or []:
        land = None
        gebiet = 0
        if tabelle is not None:
            for adresse in g.get("adressen") or []:
                land, gebiet = tabelle.ort(_nur_adresse(adresse))
                if land:
                    break
        kapazitaet = int(g.get("kapazitaet") or 0)
        if land:
            ergebnis["laender"][land] += 1
            ergebnis["kapazitaet_je_land"][land] += kapazitaet
            ergebnis["verortet"] += 1
            if gebiet:
                ergebnis["gebiete"][gebiet] += 1
                ergebnis["kapazitaet_je_gebiet"][gebiet] += kapazitaet
        else:
            ergebnis["ohne_ort"] += 1
            ergebnis["kapazitaet_ohne_ort"] += kapazitaet
        ergebnis["gegenstellen"].append({
            "alias": g.get("alias", ""),
            "land": land or "",
            "kapazitaet": kapazitaet,
            "kanaele": int(g.get("kanaele") or 0),
        })
    ergebnis["laender"] = dict(ergebnis["laender"])
    ergebnis["kapazitaet_je_land"] = dict(ergebnis["kapazitaet_je_land"])
    return ergebnis


def adressbuch(knoten: rpc.Knoten, tabelle) -> Dict:
    """Der teure Teil: Zahlen und Laenderverteilung des Adressbuchs.

    Getrennt vom Rest, damit er zwischengespeichert werden kann. Die eigenen
    Gegenstellen wechseln staendig und werden bei jedem Aufruf frisch geholt;
    das Adressbuch nicht.
    """
    bekannt = bekannte_zahlen(knoten)
    zaehlung, je_netz, nach_gebiet = verorte_adressbuch(
        knoten, tabelle, bekannt)
    if not bekannt:
        # getaddrmaninfo hat ausgesetzt. Was getnodeaddresses geliefert hat,
        # ist trotzdem etwas wert -- als GEZAEHLTE Zahl, nicht als geratene.
        # Bleibt auch das leer, bleibt das Buch leer, und der Waechter
        # behaelt zu Recht das alte.
        bekannt = {n: w["gesehen"] for n, w in je_netz.items() if w["gesehen"]}
        for netz, wert in bekannt.items():
            je_netz[netz]["bekannt"] = wert
        je_netz = {n: w for n, w in je_netz.items() if w["gesehen"]}
    return {
        "laender": zaehlung, "gebiete": nach_gebiet,
        "bekannt": bekannt, "je_netz": je_netz,
        "angesehen": sum(n["gesehen"] for n in je_netz.values()),
        "verortet": sum(n["verortet"] for n in je_netz.values()),
    }


def sammle(knoten: rpc.Knoten, tabelle, buch: Optional[Dict] = None,
           adressen: Optional[list] = None, peers=None) -> Dict:
    """Alles zusammen -- fertig fuer die Karte.

    Ohne buch wird das Adressbuch mitgeholt. Der Waechter reicht stattdessen
    sein zwischengespeichertes herein.
    """
    if buch is None:
        buch = adressbuch(knoten, tabelle)
    bekannt = buch["bekannt"]
    zaehlung = buch["laender"]
    angesehen, verortet = buch["angesehen"], buch["verortet"]
    verortet_peers = verorte_peers(knoten, tabelle, peers)
    heimat = eigener_ort(knoten, tabelle,
                         verortet_peers.get("gesehen_als"), adressen)
    peers = verortet_peers

    # Wie viele Adressen ueberhaupt einen Ort haben KOENNTEN. Ohne diese Zahl
    # laesst sich "angesehen" nicht einordnen: die Differenz zum Adressbuch
    # sind die Tor-Adressen, und die haben keinen Ort, sondern keinen Grund
    # dafuer, einen zu haben.
    verortbar = sum(bekannt.get(n, 0) for n in VERORTBAR)

    laender: List[Dict] = [
        {"land": land, "adressen": anzahl,
         "peers": peers["laender"].get(land, 0)}
        for land, anzahl in zaehlung.most_common()
    ]
    # Laender, in denen wir eine Gegenstelle haben, die aber nicht in der
    # Stichprobe auftauchten -- sonst faellt ausgerechnet ein echter Nachbar
    # von der Karte.
    for land, anzahl in peers["laender"].items():
        if land not in zaehlung:
            laender.append({"land": land, "adressen": 0, "peers": anzahl})

    return {
        "laender": laender,
        "bekannt": bekannt,
        "ortlos": sum(bekannt.get(n, 0) for n in ORTLOS),
        "angesehen": angesehen,
        "verortet": verortet,
        "verortbar": verortbar,
        "je_netz": buch.get("je_netz", {}),
        "peers": {k: v for k, v in peers.items()
                  if k not in ("laender", "gesehen_als")},
        # Woher die Linien ausgehen. None heisst: nicht feststellbar -- dann
        # zeigt die Karte die Laender, aber keine Verbindungen.
        "heimat": heimat,
        "tabelle_da": tabelle is not None,
        # Jahrgang der Ortsliste. Muss angezeigt werden: DB-IP steht unter
        # CC BY, und eine alte Liste ordnet still falsch zu.
        "orte_stand": getattr(tabelle, "stand", "") or "",
    }
