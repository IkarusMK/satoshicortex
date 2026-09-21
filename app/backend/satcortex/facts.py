"""Gemessene Eckdaten des Bitcoin-Netzes.

Diese Zahlen veralten. Sie stehen deshalb an EINER Stelle mit Messdatum, statt
verstreut im Code -- so sieht man beim Nachpflegen sofort, wie alt sie sind.
Der Assistent zeigt das Datum mit an, damit niemand einer Schaetzung von
vorgestern mehr traut als noetig.
"""
from __future__ import annotations

# Stand der Messung (Blockhoehe und Groesse von blockchain.info bzw. mempool.space)
GEMESSEN_AM = "2026-08-22"
BLOCKHOEHE = 963_597
KETTE_GB = 762
WACHSTUM_GB_PRO_JAHR = 85

# Platzbedarf der Indizes, in GB.
# txindex + blockfilterindex zusammen. Ein Adressindex ist nicht dabei --
# der laege bei 7-14 % der Blockdaten.
CORE_INDIZES_GB = 75

# chainstate + blocks/index -- klein, aber mit wahlfreiem Zugriff.
CHAINSTATE_GB = 18
LND_GB = 3
SQLITE_GB = 8


def bedarf_bulk_gb(jahre_puffer: int = 1) -> int:
    """Platz auf der grossen Platte, inklusive Puffer fuer kuenftiges Wachstum."""
    return (
        KETTE_GB
        + CORE_INDIZES_GB
        + WACHSTUM_GB_PRO_JAHR * jahre_puffer
    )


def bedarf_fast_gb() -> int:
    """Platz auf der schnellen Platte. Bewusst klein gehalten."""
    return CHAINSTATE_GB + LND_GB + SQLITE_GB


# Ohne Puffer laeuft es an, aber es wird eng -- dann warnt der Assistent.
MINDEST_BULK_GB = KETTE_GB + CORE_INDIZES_GB
MINDEST_FAST_GB = bedarf_fast_gb()
