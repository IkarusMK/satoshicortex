"""Leistungsprofile und die Umrechnung von Netzlast-Angaben.

Ein NAS betreibt normalerweise noch andere Dienste. Die harten Grenzen stehen
in der Compose (CPU und Speicher je Container); hier geht es um das, was die
Anwendung INNERHALB dieser Grenzen selbst regelt -- vor allem den
Datenbank-Cache, der waehrend der Ersteinrichtung gross sein darf und danach
wieder klein wird.
"""
from __future__ import annotations

from typing import Dict

TAGE_PRO_MONAT = 30.44
MIB_PRO_GB = 1024


def upload_gb_pro_monat_zu_mib_pro_tag(gb_pro_monat: int) -> int:
    """Rechnet das Monatsbudget in Bitcoin Cores Tageswert um.

    0 bedeutet unbegrenzt und bleibt 0 -- Bitcoin Core versteht das so.
    """
    if gb_pro_monat <= 0:
        return 0
    return max(1, round(gb_pro_monat * MIB_PRO_GB / TAGE_PRO_MONAT))


def dbcache_mb(speichergrenze_mb: int, im_erstsync: bool) -> int:
    """Waehlt den Datenbank-Cache passend zur Speichergrenze des Containers.

    Waehrend des Erstsyncs bringt ein grosser Cache am meisten -- er spart
    zaehe Schreibzugriffe auf die Platte. Danach ist er verschwendet: der
    laufende Betrieb braucht ihn nicht, und der Speicher steht dann anderen
    Diensten auf dem Geraet zur Verfuegung.

    Es bleibt bewusst Luft: bitcoind belegt neben dem Cache noch Speicher fuer
    Verbindungen, Mempool und die Signaturpruefung. Wer den Cache bis an die
    Grenze zieht, wird vom OOM-Killer abgeraeumt.
    """
    if im_erstsync:
        cache = int(speichergrenze_mb * 0.60)
        return max(300, min(cache, 4000))
    cache = int(speichergrenze_mb * 0.25)
    return max(150, min(cache, 1000))


def zusammenfassung(speichergrenze_mb: int, upload_gb: int, verbindungen: int) -> Dict:
    """Was der Assistent dem Nutzer als Folge seiner Wahl anzeigt."""
    return {
        "dbcache_erstsync_mb": dbcache_mb(speichergrenze_mb, True),
        "dbcache_betrieb_mb": dbcache_mb(speichergrenze_mb, False),
        "upload_mib_pro_tag": upload_gb_pro_monat_zu_mib_pro_tag(upload_gb),
        "upload_unbegrenzt": upload_gb <= 0,
        "verbindungen": verbindungen,
        # Schluessel statt Satz: die Oberflaeche uebersetzt.
        "meldung_upload": "upload_unbegrenzt" if upload_gb <= 0 else "upload_begrenzt",
        "upload_gb": upload_gb,
    }
