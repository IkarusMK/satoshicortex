"""Was dieser Knoten dem Netz tatsaechlich gegeben hat.

"Gesendete Bytes" allein sagt wenig: da steckt Handschlag, Ping und
Adressgeplauder mit drin. Die Frage, um die es wirklich geht, lautet: nimmt
jemand BLOECKE von mir? Und die laesst sich beantworten -- getpeerinfo
schluesselt die gesendeten Bytes nach Nachrichtenart auf.

    block, blocktxn, cmpctblock   Blockdaten. Das ist der eigentliche Beitrag.
    tx                            weitergereichte Transaktionen
    cfilter, cfheaders, cfcheckpt BIP158-Filter fuer Leichtgewicht-Wallets
    headers                       Kopfzeilen -- Wegweiser, keine Nutzlast
    addr, addrv2                  das Adressbuch, das die Karte speist
    Rest                          Handschlag, Ping, Anfragen

EHRLICHKEIT ZUR REICHWEITE: bytessent_per_msg zaehlt je VERBINDUNG und faengt
mit ihr bei null an. Die Aufschluesselung gilt also fuer die Gegenstellen, die
gerade verbunden sind -- nicht fuer die gesamte Laufzeit. Die Gesamtsumme aus
getnettotals gilt seit dem Start des Dienstes. Beides steht nebeneinander und
wird auch so benannt; eine Aufschluesselung als Lebenszeitwert auszugeben
waere schlicht falsch.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from . import rpc

log = logging.getLogger(__name__)

# Nachrichtenarten, gruppiert nach dem, was sie fuer die Gegenstelle bedeuten.
GRUPPEN = {
    "bloecke": ("block", "blocktxn", "cmpctblock"),
    "transaktionen": ("tx",),
    "filter": ("cfilter", "cfheaders", "cfcheckpt"),
    "kopfzeilen": ("headers",),
    "adressen": ("addr", "addrv2"),
}


def _gruppe(art: str) -> str:
    for name, arten in GRUPPEN.items():
        if art in arten:
            return name
    return "rest"


def ohne_auskunft() -> Dict:
    """Die Form der Antwort, wenn nichts zu melden ist.

    Benennbar, weil der Aufrufer sie seit dem 04.09.2026 auch selbst braucht:
    liegen im Sammler noch keine Rohdaten, soll er sie zurueckgeben, statt
    eine frische Abfrage auszuloesen. "erreichbar: False" heisst dabei
    ausdruecklich "nicht gemessen" -- die Oberflaeche zeichnet dann gar
    nichts, statt Nullen zu zeigen.
    """
    return {
        "erreichbar": False,
        "ausgeliefert": {k: 0 for k in list(GRUPPEN) + ["rest"]},
        "gegenstellen": [], "insgesamt": {}, "budget": {},
    }


def sammle(knoten: rpc.Knoten, peers=None, gesamt=None) -> Dict:
    """Beitrag und Gegenstellen -- oder leere Werte, wenn nichts antwortet.

    "peers" und "gesamt" reicht der Aufrufer herein, wenn er sie ohnehin
    schon geholt hat. Am 02.09.2026 gezaehlt: ein Anzeigetakt kostete zwoelf
    RPC-Aufrufe, davon acht doppelte -- getpeerinfo viermal, getnettotals
    dreimal. Waehrend des Erstabgleichs stehen alle in derselben Schlange
    hinter cs_main, und jeder doppelte Aufruf macht die Zeitlimits der
    anderen wahrscheinlicher.
    """
    leer = ohne_auskunft()
    try:
        if peers is None:
            peers = knoten.ruf("getpeerinfo", zeitlimit=rpc.GEDULD_SEKUNDEN)
        if gesamt is None:
            gesamt = knoten.ruf("getnettotals", zeitlimit=rpc.GEDULD_SEKUNDEN)
    except rpc.Beschaeftigt as fehler:
        # Waehrend des Erstabgleichs der Normalfall, nicht die Ausnahme:
        # bitcoind haelt cs_main, und die HTTP-Arbeiter stehen dahinter in
        # der Schlange. Es ist sauber abgefangen -- die Anzeige behaelt ihre
        # letzten Zahlen. Auf INFO stand es zwanzigmal je Stunde im
        # Protokoll und hat die Zeilen zugedeckt, die wirklich etwas sagen.
        log.debug("Beitrag gerade nicht abrufbar: %s", fehler)
        return leer
    except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
        log.info("Beitrag nicht abrufbar: %s", fehler)
        return leer
    if not isinstance(peers, list) or not isinstance(gesamt, dict):
        return leer

    ausgeliefert = {k: 0 for k in list(GRUPPEN) + ["rest"]}
    gegenstellen: List[Dict] = []

    for p in peers:
        if not isinstance(p, dict):
            continue
        je_art = p.get("bytessent_per_msg") or {}
        eigen = {k: 0 for k in ausgeliefert}
        for art, menge in je_art.items():
            if isinstance(menge, int):
                eigen[_gruppe(art)] += menge
        for k, v in eigen.items():
            ausgeliefert[k] += v

        gegenstellen.append({
            "adresse": p.get("addr", ""),
            "netz": p.get("network", ""),
            # Wieder bewusst nicht "eingehend/ausgehend": die Woerter klingen
            # nach Datenrichtung und meinen Verbindungsrichtung.
            "angenommen": bool(p.get("inbound")),
            "art": p.get("connection_type", ""),
            "seit_s": p.get("conntime"),
            "gesendet": p.get("bytessent", 0),
            "bloecke": eigen["bloecke"],
            "kennung": (p.get("subver") or "").strip("/"),
        })

    # Die groessten Abnehmer zuerst -- wer nimmt am meisten von uns?
    gegenstellen.sort(key=lambda g: (-g["bloecke"], -g["gesendet"]))

    budget = gesamt.get("uploadtarget") or {}
    return {
        "erreichbar": True,
        "ausgeliefert": ausgeliefert,
        "gegenstellen": gegenstellen,
        "insgesamt": {
            "gesendet": gesamt.get("totalbytessent", 0),
            "empfangen": gesamt.get("totalbytesrecv", 0),
        },
        "budget": {
            "grenze": budget.get("target", 0),
            "erreicht": bool(budget.get("target_reached")),
            # DAS ist die Zeile, die zaehlt: ist sie falsch, liefert der Knoten
            # Neueinsteigern die alten Bloecke nicht mehr aus -- und genau das
            # ist der Beitrag, um den es geht.
            "liefert_alte_bloecke": bool(budget.get("serve_historical_blocks", True)),
            "rest_bytes": budget.get("bytes_left_in_cycle", 0),
            "rest_sekunden": budget.get("time_left_in_cycle", 0),
        },
    }
