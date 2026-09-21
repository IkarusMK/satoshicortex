"""Der Cluster einer unbestaetigten Transaktion -- so, wie Core 31 ihn sieht.

Seit Bitcoin Core 31 ist der Mempool in Clustern organisiert: Transaktionen,
die ueber unbestaetigte Ein- und Ausgaenge zusammenhaengen, bilden einen
Cluster. Core ordnet jeden Cluster in Chunks -- Pakete, die in dieser
Reihenfolge und nur als Ganzes in eine Blockvorlage kommen. Fuer eine
Transaktion zaehlt deshalb die Gebuehrenrate ihres Pakets, nicht ihre eigene.

Format nachgelesen in src/rpc/mempool.cpp (v31.1, ClusterDescription und
clusterToJSON), nicht aus dem Gedaechtnis:

    {"clusterweight": int, "txcount": int,
     "chunks": [{"chunkfee": BTC als Zahl, "chunkweight": int,
                 "txs": [txid, ...]}, ...]}          # in Mining-Reihenfolge

Das Gewicht ist das sigops-bereinigte Gewicht nach BIP 141. Ein vByte sind vier
Gewichtseinheiten, aufgerundet -- wie Core es bei vsize tut.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import rpc

GEWICHT_JE_VBYTE = 4


def _vbytes(gewicht: Any) -> int:
    try:
        g = int(gewicht)
    except (TypeError, ValueError):
        return 0
    return -(-g // GEWICHT_JE_VBYTE)


def aus_core(roh: Any, txid: str) -> Optional[Dict[str, Any]]:
    """Cores Antwort auf getmempoolcluster, lesbar gemacht.

    None, wenn nichts Brauchbares darin steht -- dann zeigt die Oberflaeche
    keinen Cluster statt eines leeren.
    """
    if not isinstance(roh, dict):
        return None
    pakete = []
    eigenes = None
    for nummer, chunk in enumerate(roh.get("chunks") or [], start=1):
        if not isinstance(chunk, dict):
            continue
        txs = [t for t in chunk.get("txs") or [] if isinstance(t, str)]
        sat = rpc.sat_aus_btc(chunk.get("chunkfee"))
        vbytes = _vbytes(chunk.get("chunkweight"))
        if txid in txs:
            eigenes = nummer
        pakete.append({
            "nummer": nummer,
            "txs": txs,
            "gebuehr_sat": sat,
            "vbytes": vbytes,
            "satz_sat_vb": round(sat / vbytes, 2) if vbytes else 0.0,
        })
    if not pakete:
        return None
    try:
        txzahl = int(roh.get("txcount"))
    except (TypeError, ValueError):
        txzahl = sum(len(p["txs"]) for p in pakete)
    return {
        "txzahl": txzahl,
        "vbytes": _vbytes(roh.get("clusterweight")),
        "pakete": pakete,
        "eigenes_paket": eigenes,
    }
