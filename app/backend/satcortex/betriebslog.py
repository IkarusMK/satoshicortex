"""Was die Anwendung im laufenden Betrieb ueber sich selbst sagt.

Aus dem Betrieb, 05.09.2026: unter Protokoll -> SatoshiCortex stuenden nie mehr als
die paar Zeilen vom Start. Nachgesehen und bestaetigt: die Anwendung schrieb
ausschliesslich bei Ereignissen -- eine geaenderte Konfiguration, eine
abgelegte Kanalsicherung, eine gefangene Ausnahme. Waehrend eines
Erstabgleichs tritt davon tagelang keines ein. Das war kein Fehler in der
Anzeige und keine verlorene Meldung; es gab schlicht nichts zu zeigen.

Ein Protokoll, das ueber eine arbeitende Maschine nichts sagt, ist trotzdem
keines. Der Sammler kennt die Kettenlage ohnehin alle fuenf Sekunden -- diese
Stelle macht daraus etwas, das ein Mensch liest.

Zwei Regeln, und beide sind wichtig:

* GEMELDET WIRD, WAS SICH AENDERT. Der Knoten ist weg, der Knoten ist wieder
  da, der Abgleich ist fertig. Solche Zeilen kommen sofort und genau einmal --
  eine Meldung, die alle fuenf Sekunden wiederkehrt, ist Rauschen, und im
  Rauschen findet man den einen echten Ausfall nicht mehr.
* DAZWISCHEN EIN RUHIGER TAKT. Waehrend des Abgleichs alle zehn Minuten eine
  Zeile mit Hoehe, Anteil und Tempo; ist die Kette da, nur noch stuendlich.
  Das sind rund 150 Zeilen am Tag -- genug, um am naechsten Morgen zu sehen,
  was ueber Nacht war, und wenig genug, dass der Ringspeicher mehrere Tage
  traegt.

Ausdruecklich NICHT hier: "beschaeftigt". Core haelt beim Wegschreiben des
chainstate die Sperre cs_main, und getblockchaininfo wartet dann. Am
28.08.2026 gemessen kam waehrend des Abgleichs rund jeder fuenfte Abruf nicht
durch. Das ist der Normalfall einer arbeitenden Maschine und keine Stoerung --
stuende es im Protokoll, gingen die echten Ausfaelle darin unter.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional

from . import rpc

log = logging.getLogger(__name__)

# Wie oft waehrend des Erstabgleichs eine Fortschrittszeile faellt.
TAKT_SEKUNDEN = 600.0

# Und wie oft, wenn die Kette steht. Dann passiert im Schnitt alle zehn
# Minuten ein Block; eine Zeile je Stunde genuegt, um zu sehen, dass es laeuft.
TAKT_RUHE_SEKUNDEN = 3600.0


def _zahl(n) -> str:
    """1234567 -> "1.234.567". Blockhoehen liest niemand ohne Trennzeichen."""
    return f"{int(n):,}".replace(",", ".")


class Betriebslog:
    """Verdichtet den Strom der Kettenlagen zu lesbaren Zeilen.

    Die Uhr ist einsetzbar, damit die Pruefungen nicht zehn Minuten warten
    muessen -- und weil eine Zeitmessung, die man nicht stellen kann, sich
    auch nicht pruefen laesst.
    """

    def __init__(self, uhr: Callable[[], float] = time.monotonic) -> None:
        self._uhr = uhr
        self._erreichbar: Optional[bool] = None
        self._erstsync: Optional[bool] = None
        self._letzte_zeile = uhr()
        self._letzte_hoehe: Optional[int] = None

    # ── oeffentlich ────────────────────────────────────────────────────────
    def melde(self, lage: Optional[Dict], grund: str = "") -> None:
        """Einmal je Sammlertakt aufrufen. Schreibt selten und nie zweimal.

        Faengt alles: diese Stelle laeuft im Sammler, und der darf niemals
        daran scheitern, dass er etwas melden wollte.
        """
        try:
            self._melde(lage, grund)
        except Exception:                                        # noqa: BLE001
            log.debug("Betriebsprotokoll uebersprungen", exc_info=True)

    # ── innen ──────────────────────────────────────────────────────────────
    def _melde(self, lage: Optional[Dict], grund: str) -> None:
        if lage is None:
            # Beschaeftigt heisst: er arbeitet. Kein Wort darueber.
            # Die KONSTANTE, nicht eine abgeschriebene Zeichenkette. Beim
            # ersten Anlauf stand hier ein Wert mit Praefix, den es gar nicht
            # gibt -- der Grund heisst schlicht "beschaeftigt". Damit waere
            # jeder chainstate-Schreibvorgang als Ausfall im Protokoll
            # gelandet, also genau das Rauschen, das dieser Zweig verhindern
            # soll. Die eigenen Pruefungen sahen davon nichts: sie benutzten
            # denselben erfundenen Wert und stimmten mit dem Fehler ueberein.
            if grund != rpc.KNOTEN_BESCHAEFTIGT:
                self._ausfall()
            return
        self._rueckkehr(lage)
        self._phasenwechsel(lage)
        self._fortschritt(lage)

    def _ausfall(self) -> None:
        # Der Uebergang von "da" nach "weg": sofort, und genau einmal.
        if self._erreichbar is True:
            self._erreichbar = False
            self._sagen("bitcoind antwortet nicht mehr.")
            return

        # Danach nur noch im ruhigen Takt. Einmal melden und dann fuer immer
        # schweigen waere zu wenig: wer nach zwei Tagen hinsieht, soll
        # erkennen, dass der Zustand ANHAELT, und nicht bloss eine Zeile von
        # vorgestern finden.
        if self._uhr() - self._letzte_zeile < TAKT_SEKUNDEN:
            return
        if self._erreichbar is None:
            # Beim Start laedt Core minutenlang den chainstate und antwortet
            # dabei nicht -- das sofort zu melden waere Rauschen. Kommt es
            # aber ueberhaupt nicht, sagte das Protokoll bisher gar nichts,
            # und die Anwendung sah aus wie tot.
            self._sagen("bitcoind hat sich seit dem Start nicht gemeldet.")
        else:
            self._sagen("bitcoind antwortet weiterhin nicht.")

    def _sagen(self, satz: str, *werte) -> None:
        log.info(satz, *werte)
        self._letzte_zeile = self._uhr()

    def _rueckkehr(self, lage: Dict) -> None:
        if self._erreichbar is True:
            return
        wieder = self._erreichbar is False
        log.info(
            "bitcoind ist %sda -- Hoehe %s von %s, %.2f %%, %d Gegenstellen.",
            "wieder " if wieder else "",
            _zahl(lage["hoehe"]), _zahl(lage.get("kopfzeilen") or 0),
            float(lage.get("fortschritt") or 0.0) * 100,
            int(lage.get("verbindungen_ein") or 0)
            + int(lage.get("verbindungen_aus") or 0),
        )
        self._erreichbar = True
        self._erstsync = bool(lage.get("im_erstsync"))
        self._letzte_zeile = self._uhr()
        self._letzte_hoehe = int(lage["hoehe"])

    def _phasenwechsel(self, lage: Dict) -> None:
        jetzt = bool(lage.get("im_erstsync"))
        if self._erstsync is None or jetzt == self._erstsync:
            self._erstsync = jetzt
            return
        self._erstsync = jetzt
        if jetzt:
            log.info("Die Kette ist wieder im Abgleich -- Hoehe %s.",
                     _zahl(lage["hoehe"]))
        else:
            log.info("Die Kette steht: Hoehe %s. Der Knoten laeuft ab jetzt "
                     "im Normalbetrieb.", _zahl(lage["hoehe"]))
        self._letzte_zeile = self._uhr()
        self._letzte_hoehe = int(lage["hoehe"])

    def _fortschritt(self, lage: Dict) -> None:
        takt = TAKT_SEKUNDEN if lage.get("im_erstsync") else TAKT_RUHE_SEKUNDEN
        jetzt = self._uhr()
        vergangen = jetzt - self._letzte_zeile
        if vergangen < takt:
            return
        hoehe = int(lage["hoehe"])
        gewachsen = hoehe - (self._letzte_hoehe if self._letzte_hoehe is not None
                             else hoehe)
        self._letzte_zeile = jetzt
        self._letzte_hoehe = hoehe

        if not lage.get("im_erstsync"):
            log.info("Kette bei %s, %d Gegenstellen (%d eingehend).",
                     _zahl(hoehe),
                     int(lage.get("verbindungen_ein") or 0)
                     + int(lage.get("verbindungen_aus") or 0),
                     int(lage.get("verbindungen_ein") or 0))
            return

        if gewachsen <= 0:
            # Die wichtigste Zeile im ganzen Protokoll: ein Abgleich, der
            # steht, sieht von aussen genauso aus wie einer, der laeuft.
            log.info("Abgleich bei %s -- seit %d Minuten kein Fortschritt.",
                     _zahl(hoehe), round(vergangen / 60))
            return

        je_minute = gewachsen / (vergangen / 60)
        fehlt = max(0, int(lage.get("kopfzeilen") or 0) - hoehe)
        rest = f", noch rund {round(fehlt / je_minute / 60)} Stunden" if je_minute else ""
        log.info("Abgleich bei %s von %s (%.2f %%), %s Bloecke je Minute%s.",
                 _zahl(hoehe), _zahl(lage.get("kopfzeilen") or 0),
                 float(lage.get("fortschritt") or 0.0) * 100,
                 _zahl(round(je_minute)), rest)
