"""Gebuehr und Hoechstbetrag je Kanal nach Fuellstand -- rechnen, nicht handeln.

DER ANLASS. Aus dem Betrieb, 30.09.2026: fuer einen Routing-Betrieb fehlten
Gebuehren je Kanal nach Fuellstand und ein Hoechstbetrag pro Zahlung. Die
bisherige Automatik setzte EINEN Satz fuer alle Kanaele -- den Netz-Median.

DIE REGEL. Wo viel auf deiner Seite liegt, darf es billig abfliessen; wo es
knapp wird, wird es teurer, damit der Kanal nicht ganz leerlaeuft. Die Mitte
ist der gemessene Netz-Median im Vier-Wochen-Band (gebuehren.vorschlag) --
dieselbe Zahl, die die Automatik bisher fuer alle Kanaele setzte.

    eigener Anteil   Stufe   Satz
    ab 80 %            1     Mittel x 0,5
    50 bis 80 %        2     Mittel
    20 bis 50 %        3     Mittel x 1,5
    unter 20 %         4     Mittel x 3

KEINE MOMENTAUFNAHMEN. Aus dem Betrieb: ein Schwall, der einen Kanal am Abend
fuer ein paar Minuten leert und gleich darauf zurueckfliesst, darf nichts
umstellen -- entschieden wird einmal am Tag oder alle drei Tage. Deshalb wird
der Fuellstand stuendlich gemessen und ueber 24 (bzw. 72) Stunden gemittelt; an
den Stufengrenzen gibt es fuenf Prozentpunkte Spiel; und je Kanal wird
hoechstens einmal pro Abstand geaendert. Andere Knoten nehmen zu haeufige
Kanal-Updates ohnehin nicht an.

Diese Datei fasst nichts an. Sie liefert Zahlen und ob gehandelt werden soll;
das Setzen macht api.py ueber lnd.setze_gebuehren.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

# Untergrenze je Stufe und Faktor auf das Netz-Mittel. Stufe = Stelle + 1.
STUFEN = ((0.80, 0.5), (0.50, 1.0), (0.20, 1.5), (0.0, 3.0))
HYSTERESE = 0.05
HOECHSTSATZ_PPM = 10_000
# Unter so vielen ppm Abstand zum geltenden Satz wird nichts neu gesetzt --
# derselbe Wert wie bei der bisherigen Automatik (gebuehren.ABSTAND_PPM).
ABSTAND_PPM = 5

# Der Hoechstbetrag pro Zahlung: die Haelfte dessen, was auf deiner Seite
# ausgebbar ist, auf 10.000 sat abgerundet. So leert keine einzelne Zahlung
# den Kanal, und Absender versuchen keine Betraege, die ohnehin scheitern.
HB_ANTEIL = 0.5
HB_RASTER = 10_000
# Nie weniger als 1 % der Kapazitaet (mindestens 1.000 sat) -- ein
# Hoechstbetrag nahe null legte das Weiterleiten still.
HB_UNTERGRENZE_ANTEIL = 0.01
HB_UNTERGRENZE_SAT = 1_000
# Erst ab einem Viertel Abweichung neu setzen.
HB_ABWEICHUNG = 0.25

ABSTAENDE_TAGE = (1, 3)
# Ohne Messreihe kein Durchschnitt: erst wenn mindestens der halbe Abstand
# gemessen ist (stuendlich, also 12 Messungen fuer einen Tag, 36 fuer drei),
# fasst die Automatik einen Kanal an. Direkt nach dem Update oder bei einem
# neuen Kanal gaebe es sonst nur den Augenblick.
MESSUNGEN_JE_TAG = 24
MESSREIHE_ANTEIL = 0.5
# Der taegliche Lauf kommt nicht auf die Minute.
SPIEL_SEKUNDEN = 600


def stufe(anteil: float, bisher: Optional[int] = None) -> int:
    """Die Stufe fuer einen Anteil -- mit Spiel an den Grenzen der bisherigen."""
    roh = next((i + 1 for i, (ab, _) in enumerate(STUFEN) if anteil >= ab),
               len(STUFEN))
    if bisher is None or roh == bisher or not 1 <= bisher <= len(STUFEN):
        return roh
    unten = STUFEN[bisher - 1][0]
    oben = 1.0 if bisher == 1 else STUFEN[bisher - 2][0]
    if unten - HYSTERESE <= anteil < oben + HYSTERESE:
        return bisher
    return roh


def satz(anker_ppm: int, stufe_: int) -> int:
    """Der Satz einer Stufe, ausgerichtet am Netz-Mittel."""
    faktor = STUFEN[max(1, min(len(STUFEN), stufe_)) - 1][1]
    return max(0, min(HOECHSTSATZ_PPM, round(int(anker_ppm) * faktor)))


def hoechstbetrag(verfuegbar_sat: int, kapazitaet_sat: int,
                  grenze_sat: Optional[int]) -> int:
    """Der Hoechstbetrag pro Zahlung fuer diesen Fuellstand.

    Nie ueber LNDs Grenze -- max_htlc darf weder die Kapazitaet noch den
    ausgehandelten Hoechstwert in Bewegung uebersteigen
    (routing/localchans/manager.go, v0.21.3), sonst lehnt LND ab.
    """
    wert = int(max(0, verfuegbar_sat) * HB_ANTEIL) // HB_RASTER * HB_RASTER
    unten = max(HB_UNTERGRENZE_SAT, int(kapazitaet_sat * HB_UNTERGRENZE_ANTEIL))
    wert = max(unten, wert)
    if grenze_sat:
        wert = min(wert, int(grenze_sat))
    return wert


def faellig(zuletzt_s: Optional[int], jetzt_s: int, abstand_tage: int) -> bool:
    """Ob fuer diesen Kanal wieder entschieden werden darf."""
    if not zuletzt_s:
        return True
    return jetzt_s - int(zuletzt_s) >= int(abstand_tage) * 86_400 - SPIEL_SEKUNDEN


def messreihe_reicht(mittel: Optional[Dict[str, Any]], abstand_tage: int) -> bool:
    """Ob der Durchschnitt aus genug Messungen stammt, um danach zu handeln."""
    if not mittel:
        return False
    noetig = math.ceil(max(1, int(abstand_tage)) * MESSUNGEN_JE_TAG * MESSREIHE_ANTEIL)
    return int(mittel.get("messungen") or 0) >= noetig


def wahl(eintrag: Dict[str, Any], alle_automatik: bool) -> Tuple[str, str]:
    """Was fuer diesen Kanal gilt: (Gebuehr, Hoechstbetrag).

    Ohne eigene Wahl folgt ein Kanal dem Schalter fuer alle. Der
    Hoechstbetrag folgt dem Fuellstand, sobald die Gebuehr es tut -- es sei
    denn, er wurde ausdruecklich festgelegt.
    """
    gebuehr = eintrag.get("gebuehr") or ("automatik" if alle_automatik else "fest")
    hoechst = eintrag.get("hoechstbetrag") or (
        "fuellstand" if gebuehr == "automatik" else "fest")
    return gebuehr, hoechst


def planen(kanal: Dict[str, Any], mittel: Optional[Dict[str, Any]],
           anker_ppm: Optional[int], eintrag: Dict[str, Any],
           jetzt_ppm: Optional[int],
           jetzt_hoechstbetrag_sat: Optional[int]) -> Dict[str, Any]:
    """Was die Automatik fuer diesen Kanal setzen wuerde -- und ob.

    mittel ist der Durchschnitt ueber den Abstand ({anteil, verfuegbar});
    fehlt er (noch keine Messreihe), zaehlt der Augenblick -- das taugt fuer
    die Vorschau, gehandelt wird so nie (messreihe_reicht).
    """
    anteil = float(mittel["anteil"]) if mittel else float(kanal.get("anteil_hier") or 0)
    verfuegbar = int(mittel["verfuegbar"]) if mittel else int(kanal.get("verfuegbar") or 0)
    st = stufe(anteil, eintrag.get("stufe"))
    ppm = satz(anker_ppm, st) if anker_ppm is not None else None
    hb = hoechstbetrag(verfuegbar, int(kanal.get("kapazitaet") or 0),
                       kanal.get("hinaus_hoechstens"))
    gebuehr_handeln = ppm is not None and (
        jetzt_ppm is None or abs(ppm - int(jetzt_ppm)) >= ABSTAND_PPM)
    hb_handeln = (not jetzt_hoechstbetrag_sat
                  or abs(hb - int(jetzt_hoechstbetrag_sat))
                  > HB_ABWEICHUNG * int(jetzt_hoechstbetrag_sat))
    return {"stufe": st, "satz_ppm": ppm, "hoechstbetrag_sat": hb,
            "anteil": round(anteil, 3),
            "gebuehr_handeln": gebuehr_handeln,
            "hoechstbetrag_handeln": hb_handeln}
