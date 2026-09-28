"""Das Kontobuch fuer Electrum -- was je Skripthash gefragt wird.

Reine Rechnerei ueber Transaktionen, die schon aufbereitet hereinkommen:
wer Core fragt, steht in lesewallet.py. Getrennt, damit sich jede Regel hier
gegen die Beispiele der Spezifikation pruefen laesst, ohne einen Knoten.

Die Regeln stehen in spesmilo/electrum-protocol, protocol-basics.rst,
Abschnitt "Status" -- und die Tests rechnen dessen Beispiel nach:

  * Beteiligt ist jede Transaktion, die an das Skript zahlt ODER von ihm
    ausgibt, bestaetigt oder im Mempool.
  * Bestaetigte nach Hoehe, bei gleicher Hoehe nach der Stelle im Block.
  * Im Mempool Hoehe 0, wenn alle Eingaenge bestaetigt sind, sonst -1;
    geordnet nach (-Hoehe, txid).
  * Status = sha256 ueber "txid:hoehe:" aller in dieser Folge, hexadezimal;
    null, wenn es keine gibt.

Die Ausgabe-Seite ist der Grund, warum es dieses Modul gibt: Cores Wallet
nennt bei einer Ausgabe das ZIEL, nicht die eigene Adresse, von der das Geld
kam (an der Regtest-Kette am 28.09.2026 gesehen). Hier steht jeder Eingang
mit dem Skripthash, den er ausgibt.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Tx:
    txid: str
    # > 0 im Block; 0 im Mempool mit bestaetigten Eingaengen; -1 im Mempool
    # mit mindestens einem unbestaetigten Eingang.
    hoehe: int
    position: int                 # Stelle im Block; im Mempool bedeutungslos
    gebuehr: Optional[int]        # sat -- die Spezifikation nennt sie nur im Mempool
    # (n, skripthash, sat) je Ausgang
    ausgaenge: Tuple[Tuple[int, str, int], ...]
    # (vorgaenger_txid, n, skripthash, sat) je Eingang
    eingaenge: Tuple[Tuple[str, int, str, int], ...]

    @property
    def im_mempool(self) -> bool:
        return self.hoehe <= 0


def _ordnung(tx: Tx) -> tuple:
    """Die Reihenfolge der Spezifikation: erst die Kette, dann der Mempool."""
    if tx.im_mempool:
        return (1, -tx.hoehe, tx.txid)
    return (0, tx.hoehe, tx.position)


class Buch:
    """Alle Transaktionen der angemeldeten Konten, nach Skripthash erschlossen."""

    def __init__(self, txs: Iterable[Tx]) -> None:
        eindeutig: Dict[str, Tx] = {}
        for tx in txs:
            eindeutig[tx.txid] = tx
        self._txs = sorted(eindeutig.values(), key=_ordnung)
        self._nach_skript: Dict[str, List[Tx]] = {}
        for tx in self._txs:
            beteiligt = {s for _n, s, _w in tx.ausgaenge}
            beteiligt |= {s for _t, _n, s, _w in tx.eingaenge}
            for skript in beteiligt:
                self._nach_skript.setdefault(skript, []).append(tx)
        # Welche Ausgaenge irgendwer ausgibt -- bestaetigt oder im Mempool.
        self._ausgegeben: Set[Tuple[str, int]] = {
            (t, n) for tx in self._txs for t, n, _s, _w in tx.eingaenge}

    def beruehrt(self) -> Set[str]:
        """Jeder Skripthash, den eine Transaktion im Buch beruehrt."""
        return set(self._nach_skript)

    def geschichte(self, skript: str) -> List[Dict]:
        eintraege = []
        for tx in self._nach_skript.get(skript, []):
            eintrag = {"tx_hash": tx.txid, "height": tx.hoehe}
            if tx.im_mempool and tx.gebuehr is not None:
                eintrag["fee"] = tx.gebuehr
            eintraege.append(eintrag)
        return eintraege

    def mempool(self, skript: str) -> List[Dict]:
        return [e for e in self.geschichte(skript) if e["height"] <= 0]

    def status(self, skript: str) -> Optional[str]:
        txs = self._nach_skript.get(skript, [])
        if not txs:
            return None
        zeile = "".join(f"{tx.txid}:{tx.hoehe}:" for tx in txs)
        return hashlib.sha256(zeile.encode("ascii")).hexdigest()

    def guthaben(self, skript: str) -> Dict[str, int]:
        """Bestaetigt und unbestaetigt getrennt, wie Electrum es erwartet.

        Unbestaetigt darf negativ sein: was im Mempool ausgegeben wird, ist
        bestaetigt noch da und unbestaetigt schon weg.
        """
        summen = {"confirmed": 0, "unconfirmed": 0}
        for tx in self._nach_skript.get(skript, []):
            feld = "unconfirmed" if tx.im_mempool else "confirmed"
            summen[feld] += sum(w for _n, s, w in tx.ausgaenge if s == skript)
            summen[feld] -= sum(w for _t, _n, s, w in tx.eingaenge
                                if s == skript)
        return summen

    def unverbraucht(self, skript: str) -> List[Dict]:
        """Was an dieses Skript ging und von niemandem ausgegeben wird."""
        return [
            {"tx_hash": tx.txid, "tx_pos": n, "height": tx.hoehe, "value": w}
            for tx in self._nach_skript.get(skript, [])
            for n, s, w in tx.ausgaenge
            if s == skript and (tx.txid, n) not in self._ausgegeben
        ]
