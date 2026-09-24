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


# ── Haengt sie, oder wartet sie nur? ───────────────────────────────────────
#
# DER BEFUND VOM 24.09.2026, aus dem Betrieb: "das er mir jetzt bei jeder
# transaktion im wallet direkt anzeigt 'gebueren erhoehen!' ??? das ist ja
# glaub ich uach nicht richtig von der logig her".
#
# Stimmte. Die Oberflaeche bot "Gebuehr erhoehen" bei JEDER unbestaetigten
# Ausgabe an: Sekunden nach dem Senden, und auch dann, wenn die Gebuehr
# laengst reichte. Der Knopf hebt auf den Satz "schnell" -- zahlt die
# Transaktion den schon, kostet er nur, ohne etwas zu beschleunigen.
#
# Haengen heisst zweierlei, und beides kommt aus dem EIGENEN Mempool
# (getmempoolentry, Feldliste nachgelesen in src/rpc/mempool.cpp, v31.1):
#
# 1. Es kam mindestens ein Block ohne sie. "height" ist die Hoehe, bei der
#    sie in den Mempool kam; liegt die Kette jetzt hoeher, hatte sie ihre
#    Gelegenheit und wurde nicht mitgenommen. Nach einem Neustart von
#    bitcoind beginnt die Zaehlung neu (Core liest den Mempool dann mit der
#    aktuellen Hoehe ein) -- das verschiebt den Knopf um einen Block, bietet
#    ihn aber nie zu Unrecht an.
# 2. Ihr Paket zahlt weniger, als der Knoten fuer "schnell" schaetzt. Es
#    zaehlt der Chunk, nicht die einzelne Transaktion: hat schon ein Kind
#    nachgebessert, zahlt das Paket mehr, und nur als Paket kommt es in den
#    Block.

# Ab so vielen Bloecken ohne sie gilt eine Transaktion als haengend.
HAENGT_AB_BLOECKEN = 1


def _satz(eintrag: Dict[str, Any]) -> Optional[float]:
    """Sat/vByte ihres Pakets -- aus dem Chunk, sonst aus den Vorfahren."""
    gebuehren = eintrag.get("fees")
    if not isinstance(gebuehren, dict):
        return None
    vbytes = _vbytes(eintrag.get("chunkweight"))
    if vbytes and gebuehren.get("chunk") is not None:
        return rpc.sat_aus_btc(gebuehren.get("chunk")) / vbytes
    try:
        vbytes = int(eintrag.get("ancestorsize") or 0)
    except (TypeError, ValueError):
        return None
    if vbytes <= 0 or gebuehren.get("ancestor") is None:
        return None
    return rpc.sat_aus_btc(gebuehren.get("ancestor")) / vbytes


def wartelage(eintrag: Optional[Dict[str, Any]], hoehe_jetzt: int,
              noetig_sat_vb: Optional[float]) -> Dict[str, Any]:
    """Ob eine wartende Transaktion haengt -- und woran man es sieht.

    eintrag ist Cores Antwort auf getmempoolentry, None heisst "nicht im
    Mempool". noetig_sat_vb ist derselbe Satz, auf den das Nachbessern hebt.
    """
    if eintrag is None:
        return {"lage": "nicht_im_mempool"}
    if not noetig_sat_vb:
        return {"lage": "keine_schaetzung"}
    satz = _satz(eintrag)
    try:
        seit = int(eintrag.get("height"))
    except (TypeError, ValueError):
        seit = None
    if satz is None or seit is None:
        return {"lage": "unklar"}
    if satz >= noetig_sat_vb:
        lage = "reicht"
    elif hoehe_jetzt - seit < HAENGT_AB_BLOECKEN:
        lage = "frisch"
    else:
        lage = "haengt"
    return {"lage": lage, "satz_sat_vb": round(satz, 1),
            "noetig_sat_vb": noetig_sat_vb, "seit_block": seit}
