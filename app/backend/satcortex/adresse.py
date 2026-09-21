"""Was einer Adresse JETZT gehoert -- aus dem UTXO-Satz des eigenen Knotens.

Ohne Adressindex -- dieser Stapel fuehrt keinen -- gibt es genau einen
Weg: scantxoutset. Bitcoin Core durchsucht dafuer den ganzen Satz der
unverbrauchten Ausgaben nach einem Descriptor. Heraus kommt der aktuelle
Bestand -- keine Historie und keine unbestaetigten Eingaenge, denn beides
steht nicht im UTXO-Satz.

Nachgelesen in src/rpc/blockchain.cpp (v31.1): "start" kehrt erst nach dem
Durchlauf zurueck, "status" liefert den Fortschritt in Prozent oder null,
"abort" bricht ab. Es laeuft immer nur EIN Scan; ein zweites "start" wirft
"Scan already in progress".

Die Eingabe wird ZWEIMAL geprueft, bevor sie in den Descriptor "addr(...)"
kommt: erst auf Zeichen, dann durch bitcoind selbst (validateaddress). Ein
Descriptor ist eine kleine Sprache -- wer Klammern oder Kommas durchlaesst,
laesst jemanden eigene Suchausdruecke einschleusen. Bech32 und Base58 kommen
beide mit Buchstaben und Ziffern aus.

Die Abfrage verlaesst den Knoten nicht. Kein Explorer erfaehrt, wonach gesucht
wurde.
"""
from __future__ import annotations

import string
from typing import Any, Dict

from . import rpc

ERLAUBT = frozenset(string.ascii_letters + string.digits)
# Die kuerzeste gebraeuchliche Adresse (Base58, P2PKH) hat 26 Zeichen, die
# laengste Bech32m-Adresse hoechstens 90 -- mit etwas Luft nach unten.
KUERZESTE = 14
LAENGSTE = 90
# Eine Sammeladresse kann Tausende unverbrauchter Ausgaben halten. Die
# Summe stimmt trotzdem immer; gelistet werden nur die juengsten.
LISTE_HOECHSTENS = 200


class AdresseUngueltig(ValueError):
    """Keine gueltige Adresse fuer das Netz dieses Knotens."""


def _nur_erlaubte_zeichen(text: str) -> bool:
    return bool(text) and all(z in ERLAUBT for z in text)


def pruefe(knoten: Any, eingabe: str) -> str:
    """Die Adresse, so wie bitcoind sie kennt -- oder AdresseUngueltig."""
    sauber = (eingabe or "").strip()
    if not KUERZESTE <= len(sauber) <= LAENGSTE \
            or not _nur_erlaubte_zeichen(sauber):
        raise AdresseUngueltig(sauber)
    antwort = knoten.ruf("validateaddress", sauber)
    if not isinstance(antwort, dict) or not antwort.get("isvalid"):
        raise AdresseUngueltig(sauber)
    adresse = antwort.get("address") or sauber
    if not _nur_erlaubte_zeichen(adresse):
        raise AdresseUngueltig(sauber)
    return adresse


def descriptor(adresse: str) -> str:
    return f"addr({adresse})"


def ergebnis(roh: Dict[str, Any],
             hoechstens: int = LISTE_HOECHSTENS) -> Dict[str, Any]:
    """Cores Scan-Ergebnis, lesbar gemacht. Die juengsten Ausgaben zuerst."""
    ausgaben = []
    for u in roh.get("unspents") or []:
        if not isinstance(u, dict):
            continue
        try:
            hoehe = int(u.get("height") or 0)
            vout = int(u.get("vout") or 0)
            bestaetigungen = int(u.get("confirmations") or 0)
        except (TypeError, ValueError):
            continue
        ausgaben.append({
            "txid": str(u.get("txid") or ""),
            "vout": vout,
            "betrag_sat": rpc.sat_aus_btc(u.get("amount")),
            "hoehe": hoehe,
            "bestaetigungen": bestaetigungen,
            "coinbase": bool(u.get("coinbase")),
        })
    ausgaben.sort(key=lambda a: (-a["hoehe"], a["txid"], a["vout"]))
    try:
        hoehe = int(roh.get("height") or 0)
        durchsucht = int(roh.get("txouts") or 0)
    except (TypeError, ValueError):
        hoehe, durchsucht = 0, 0
    return {
        "bestand_sat": rpc.sat_aus_btc(roh.get("total_amount")),
        "anzahl": len(ausgaben),
        "ausgaben": ausgaben[:hoechstens],
        "weitere": max(0, len(ausgaben) - hoechstens),
        "hoehe": hoehe,
        "durchsucht": durchsucht,
    }
