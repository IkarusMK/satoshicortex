"""Der Bitcoin-Kurs -- geholt ueber Tor, gezeichnet ohne fremde Bibliothek.

Der Knoten kennt keinen Kurs. Bitcoin Core hat keine Preisdaten und soll auch
keine haben: ein Preis ist eine Meinung des Marktes, keine Eigenschaft der
Kette. Also muss er von aussen kommen -- und damit gilt dieselbe Regel wie bei
Versionsabfrage und Nachrichten:

    AUSSCHLIESSLICH UEBER TOR. Eine regelmaessige Kursabfrage verraet sonst,
    dass hier jemand einen Bitcoin-Knoten betreibt, und mit der Zeit auch,
    wann er laeuft.

WARUM BITSTAMP AM ANFANG DER LISTE STEHT -- gemessen am 06.09.2026:

    CoinGecko, Kraken, Coinbase, Blockchain.info, Bitfinex   Server: cloudflare
    Bitstamp                                                 Server: nginx

Acht von elf geprueften Kursquellen stehen hinter Cloudflare, und Cloudflare
behandelt Tor-Ausgangsknoten misstrauisch -- bei den Nachrichtenquellen hat
genau das Bitcoin Magazine mit einem 403 aus der Liste geworfen. Bitstamp ist
die einzige ohne, liefert Kurs UND Verlauf, und braucht keinen Schluessel.

Kraken und Coinbase bleiben als Rueckfall: nicht weil sie besser waeren,
sondern damit ein Ausfall bei einem Anbieter nicht den ganzen Kasten leert.

UND WARUM DIESE REIHENFOLGE NUR NOCH DER ANFANG IST. Am 17.09.2026 schickte
Bitstamp Tor-Ausgaenge im Kreis (302, urllib bricht mit "infinite loop" ab).
Die Messung von oben war elf Tage alt und damit falsch -- der Rueckfall trug
den Kasten, aber jeder Abruf lief erst in die tote Quelle. Eine Rangfolge, die
aus einer einmaligen Messung stammt, veraltet genau so. Deshalb merkt sich der
Abruf, wer zuletzt geliefert hat (_ZULETZT, _reihenfolge) und fragt den
zuerst. Die Liste hier ist nur noch der Startwert.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import abweisung
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Wie oft nachgesehen wird. Ein Kurs, der sich alle fuenf Minuten aendert,
# muss nicht jede Minute geholt werden -- und ueber Tor kostet jeder Abruf
# einen Kreisaufbau. Wer den Sekundenkurs braucht, hat eine Boerse offen.
INTERVALL_SEKUNDEN = 300

# Der Verlauf aendert sich langsamer als der Kurs: die letzte Tageskerze
# steht erst am Tagesende fest.
VERLAUF_INTERVALL_SEKUNDEN = 3600

ZEITSPERRE_SEKUNDEN = 45
HOECHSTLAENGE = 512 * 1024

# Was Bitstamp fuer Bitcoin anbietet (trading-pairs-info, 06.09.2026).
# Mehr waeren Fantasiewaehrungen: btcusdt und btcusdc sind Stablecoins und
# damit derselbe Dollar mit einem Umweg.
WAEHRUNGEN: Tuple[str, ...] = ("usd", "eur", "gbp")

# Zeitraeume: Schrittweite und Anzahl. Die Werte fuer `step` sind nicht frei
# waehlbar -- Bitstamp kennt eine feste Liste, und 3600/86400/259200 sind
# daraus die drei, die sich sinnvoll auf diese Fenster abbilden.
ZEITRAEUME: Dict[str, Tuple[int, int]] = {
    "24h":  (3600, 24),
    "30t":  (86400, 30),
    "1j":   (86400, 365),
    "5j":   (259200, 610),
}
VORGABE_ZEITRAUM = "30t"

# Wie lange eine angesehene Waehrung als "in Gebrauch" gilt, und wie viele
# Kombinationen der Waechter hoechstens frisch haelt.
#
# Ueber Tor kostet jeder Abruf einen Kreisaufbau. Wer alle Ansichten
# durchklickt, darf damit nicht ein Dutzend Abrufe im Fuenf-Minuten-Takt
# ausloesen -- und wer nur Euro ansieht, soll auch Euro frisch bekommen.
GEBRAUCH_FRIST_SEKUNDEN = 3600
GEBRAUCH_HOECHSTENS = 4


# Welche Boerse zuletzt geliefert hat -- je Zweck ("kurs", "verlauf").
#
# WARUM DAS HIER STEHT UND NICHT EINE NEUE FESTE REIHENFOLGE. Der Modulkopf
# begruendet "Bitstamp zuerst" mit einer Messung vom 06.09.2026. Am 17.09.2026
# stand in das Betriebsprotokoll dreimal:
#
#     Kurs (Bitstamp): HTTPError: HTTP Error 302 ... infinite loop
#
# Bitstamp schickt Tor-Ausgaenge seither im Kreis. Der Rueckfall griff, der
# Kurs war da -- aber jeder Abruf lief erst in die tote Quelle, und das ueber
# Tor, wo jeder Versuch einen Kreisaufbau kostet. Die Reihenfolge einfach
# umzustellen waere die naechste Momentaufnahme, die in zwei Wochen wieder
# falsch ist. Stattdessen merkt sich der Abruf, wer zuletzt geantwortet hat,
# und fragt den zuerst. Faellt der aus, faellt er in die Liste zurueck und
# merkt sich den neuen. Die feste Reihenfolge ist damit nur noch der Anfang.
_ZULETZT: Dict[str, str] = {}


def _reihenfolge(zweck: str) -> List[Boerse]:
    """Die Boersen, die zuletzt erfolgreiche zuerst."""
    name = _ZULETZT.get(zweck)
    if not name:
        return list(BOERSEN)
    return (sorted(BOERSEN, key=lambda b: b.name != name))


class Abgewiesen(Exception):
    """Die Gegenstelle hat nicht geliefert."""


def _oeffner(proxy: Optional[str]):
    return urllib.request.build_opener(urllib.request.ProxyHandler(
        {"https": proxy, "http": proxy} if proxy else {}))


def _hole_json(adresse: str, proxy: Optional[str]) -> Dict:
    anfrage = urllib.request.Request(adresse, headers={
        "Accept": "application/json",
        # Kein Kennzeichen, das den Betreiber wiedererkennbar macht.
        "User-Agent": "satcortex",
    })
    try:
        with _oeffner(proxy).open(anfrage,
                                  timeout=ZEITSPERRE_SEKUNDEN) as antwort:
            roh = antwort.read(HOECHSTLAENGE)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as f:
        erklaerung = abweisung.deute_http(getattr(f, "code", None),
                                          "Die Boerse")
        raise Abgewiesen(erklaerung or f"{type(f).__name__}: {f}") from f
    try:
        return json.loads(roh)
    except (json.JSONDecodeError, UnicodeDecodeError) as f:
        raise Abgewiesen("Die Antwort war kein JSON.") from f


def _zahl(wert) -> Optional[float]:
    """Eine Zahl aus fremden Daten -- oder None.

    Boersen liefern ihre Kurse als Zeichenketten ("79805.00"), und was von
    aussen kommt, wird geprueft und nicht geglaubt. Ein NaN oder eine
    Unendlichkeit wuerde die Zeichnung still zerstoeren.
    """
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return None
    if z != z or z in (float("inf"), float("-inf")) or z <= 0:
        return None
    return z


# ---------------------------------------------------------------- Quellen ---

@dataclass(frozen=True)
class Boerse:
    name: str
    hinter_cloudflare: bool
    kurs_adresse: Callable[[str], str]
    kurs_lesen: Callable[[Dict], Dict]
    verlauf_adresse: Optional[Callable[[str, int, int], str]] = None
    verlauf_lesen: Optional[Callable[[Dict], List[Tuple[int, float]]]] = None


def _bitstamp_kurs(d: Dict) -> Dict:
    return {
        "kurs": _zahl(d.get("last")),
        "offen": _zahl(d.get("open")),
        "hoch": _zahl(d.get("high")),
        "tief": _zahl(d.get("low")),
        # NICHT _zahl(): die weist alles <= 0 ab, und ein Minustag ist
        # ein Tag wie jeder andere.
        "wechsel24": _roh_prozent(d.get("percent_change_24")),
        "stand": int(d.get("timestamp") or time.time()),
    }


def _roh_prozent(wert) -> Optional[float]:
    """Die Tagesveraenderung darf negativ und null sein -- anders als ein Kurs.

    _zahl() weist alles <= 0 ab, weil ein Kurs von null keiner ist. Bei einer
    Prozentangabe waere genau das falsch: ein Minustag ist ein Tag wie jeder
    andere, und ihn zu verschlucken hiesse, nur die guten Tage zu zeigen.
    """
    try:
        z = float(wert)
    except (TypeError, ValueError):
        return None
    return None if z != z else z


def _bitstamp_verlauf(d: Dict) -> List[Tuple[int, float, float, float]]:
    punkte = []
    for k in (d.get("data") or {}).get("ohlc") or []:
        schluss = _zahl(k.get("close"))
        if schluss is None:
            continue
        try:
            zeit = int(k.get("timestamp"))
        except (TypeError, ValueError):
            continue
        # Hoch und Tief kommen ohnehin mit. Sie wegzuwerfen und die
        # Sprechblase dann nur den Schlusskurs zeigen zu lassen, waere
        # Verschwendung -- gerade bei einer Tageskerze ist die Spanne die
        # interessantere Zahl.
        punkte.append((zeit, schluss,
                       _zahl(k.get("high")) or schluss,
                       _zahl(k.get("low")) or schluss))
    return punkte


def _kraken_kurs(d: Dict) -> Dict:
    ergebnis = d.get("result") or {}
    if not ergebnis:
        raise Abgewiesen("Kraken meldete kein Ergebnis.")
    erstes = ergebnis[list(ergebnis)[0]]
    letzter = _zahl((erstes.get("c") or [None])[0])
    offen = _zahl(erstes.get("o"))
    return {
        "kurs": letzter, "offen": offen,
        "hoch": _zahl((erstes.get("h") or [None, None])[1]),
        "tief": _zahl((erstes.get("l") or [None, None])[1]),
        "wechsel24": (round((letzter - offen) / offen * 100, 2)
                      if letzter and offen else None),
        "stand": int(time.time()),
    }


def _kraken_verlauf(d: Dict) -> List[Tuple[int, float, float, float]]:
    """Krakens Kerze: [Zeit, offen, hoch, tief, schluss, ...]."""
    ergebnis = {k: v for k, v in (d.get("result") or {}).items()
                if k != "last"}
    if not ergebnis:
        return []
    punkte = []
    for k in ergebnis[list(ergebnis)[0]]:
        if len(k) < 5:
            continue
        schluss = _zahl(k[4])
        if schluss is None:
            continue
        punkte.append((int(k[0]), schluss,
                       _zahl(k[2]) or schluss, _zahl(k[3]) or schluss))
    return punkte


def _coinbase_kurs(d: Dict) -> Dict:
    return {"kurs": _zahl((d.get("data") or {}).get("amount")),
            "offen": None, "hoch": None, "tief": None,
            "wechsel24": None, "stand": int(time.time())}


BOERSEN: Tuple[Boerse, ...] = (
    # Zuerst die ohne Cloudflare -- siehe Modulkopf.
    Boerse("Bitstamp", False,
           lambda w: f"https://www.bitstamp.net/api/v2/ticker/btc{w}/",
           _bitstamp_kurs,
           lambda w, schritt, anzahl: (
               f"https://www.bitstamp.net/api/v2/ohlc/btc{w}/"
               f"?step={schritt}&limit={anzahl}"),
           _bitstamp_verlauf),
    Boerse("Kraken", True,
           lambda w: ("https://api.kraken.com/0/public/Ticker"
                      f"?pair=XBT{w.upper()}"),
           _kraken_kurs,
           lambda w, schritt, anzahl: (
               "https://api.kraken.com/0/public/OHLC"
               f"?pair=XBT{w.upper()}&interval={max(1, schritt // 60)}"),
           _kraken_verlauf),
    # Nur Kurs, kein Verlauf -- der letzte Halm.
    Boerse("Coinbase", True,
           lambda w: (f"https://api.coinbase.com/v2/prices/BTC-{w.upper()}"
                      "/spot"),
           _coinbase_kurs),
)


def _pruefe_waehrung(waehrung: str) -> str:
    w = (waehrung or "usd").lower()
    return w if w in WAEHRUNGEN else "usd"


def _pruefe_zeitraum(zeitraum: str) -> str:
    """Damit ein unbekanntes Fenster nicht unter eigenem Schluessel ablegt.

    Vorher fiel die Schrittweite auf die Vorgabe zurueck, der Ablageschluessel
    aber nicht -- die Daten landeten unter dem Fantasienamen und wurden nie
    wieder gefunden.
    """
    return zeitraum if zeitraum in ZEITRAEUME else VORGABE_ZEITRAUM


def hole_kurs(waehrung: str = "usd",
              proxy: Optional[str] = None) -> Tuple[Dict, str]:
    """Der aktuelle Kurs, von der ersten Boerse, die antwortet.

    AttributeError gehoert mit in die Fangliste, und das ist kein Zierrat:
    liefert eine Boerse statt eines Objekts eine Zeichenkette oder eine Liste,
    scheitert der Auswerter an `.get` -- also mit AttributeError, nicht mit
    TypeError. Ohne ihn riss eine einzige Formataenderung bei EINER Quelle den
    ganzen Abruf mit, statt die naechste zu fragen. Genau dafuer stehen Kraken
    und Coinbase in der Liste. Aufgefallen am 08.09.2026 beim Nachziehen der
    Tests, die es fuer dieses Modul nie gab.
    """
    w = _pruefe_waehrung(waehrung)
    letzter = ""
    for boerse in _reihenfolge("kurs"):
        try:
            roh = _hole_json(boerse.kurs_adresse(w), proxy)
            werte = boerse.kurs_lesen(roh)
        except Abgewiesen as fehler:
            letzter = f"{boerse.name}: {fehler}"
            log.info("Kurs (%s): %s", boerse.name, fehler)
            continue
        except (AttributeError, KeyError, IndexError, TypeError,
                ValueError) as fehler:
            letzter = f"{boerse.name}: unerwartete Antwort ({fehler})"
            continue
        if werte.get("kurs"):
            werte["boerse"] = boerse.name
            werte["waehrung"] = w
            _ZULETZT["kurs"] = boerse.name
            return werte, ""
        letzter = f"{boerse.name}: Antwort ohne Kurs"
    raise Abgewiesen(letzter or "Keine Boerse hat geantwortet.")


def hole_verlauf(waehrung: str = "usd", zeitraum: str = VORGABE_ZEITRAUM,
                 proxy: Optional[str] = None
                 ) -> Tuple[List[Tuple[int, float, float, float]], str]:
    """Der Kursverlauf als Punkte (Zeit, Schluss, Hoch, Tief)."""
    w = _pruefe_waehrung(waehrung)
    schritt, anzahl = ZEITRAEUME.get(zeitraum, ZEITRAEUME[VORGABE_ZEITRAUM])
    letzter = ""
    for boerse in _reihenfolge("verlauf"):
        if not boerse.verlauf_adresse or not boerse.verlauf_lesen:
            continue
        try:
            roh = _hole_json(boerse.verlauf_adresse(w, schritt, anzahl), proxy)
            punkte = boerse.verlauf_lesen(roh)
        except Abgewiesen as fehler:
            letzter = f"{boerse.name}: {fehler}"
            continue
        except (AttributeError, KeyError, IndexError, TypeError,
                ValueError) as fehler:
            letzter = f"{boerse.name}: unerwartete Antwort ({fehler})"
            continue
        if len(punkte) >= 2:
            # Aufsteigend, und hoechstens so viele, wie angefragt waren:
            # Kraken liefert grundsaetzlich 720 Kerzen, egal was man fragt.
            punkte.sort(key=lambda p: p[0])
            _ZULETZT["verlauf"] = boerse.name
            return punkte[-anzahl:], boerse.name
    raise Abgewiesen(letzter or "Keine Boerse hat einen Verlauf geliefert.")


class Kurstafel:
    """Haelt Kurs und Verlauf frisch -- im app-Prozess, ohne eigenen Dienst.

    Wie der Nachrichten-Feed: angestossen vom vorhandenen Waechter, geholt
    ueber denselben Tor-Ausgang. Kein Container, kein Faden, kein Port.
    """

    def __init__(self, proxy_gibt: Callable[[], Optional[str]]) -> None:
        self._proxy_gibt = proxy_gibt
        # JE WAEHRUNG -- und das ist der ganze Punkt.
        #
        # Bis zum 08.09.2026 stand hier ein einziges Dict OHNE Waehrung,
        # waehrend der Verlauf gleich darunter von Anfang an nach Waehrung
        # abgelegt war. Der Waechter holte alle fuenf Minuten Dollar; wer
        # danach auf Euro schaltete, dessen Kurs war keine fuenf Minuten alt
        # und wurde gar nicht erst geholt. Ergebnis in der Oberflaeche:
        # 78.417 Dollar mit einem Euro-Zeichen davor, daneben ein Diagramm,
        # das korrekt 67-68k zeichnete. Der Betreiber sah es sofort.
        self._kurs: Dict[str, Dict] = {}
        self._kurs_stand: Dict[str, float] = {}
        self._verlauf: Dict[str, List[Tuple[int, float, float, float]]] = {}
        self._verlauf_stand: Dict[str, float] = {}
        # Was tatsaechlich angesehen wurde -- siehe in_gebrauch().
        self._benutzt: Dict[Tuple[str, str], float] = {}
        self._grund = ""

    @property
    def grund(self) -> str:
        return self._grund

    def einmal_holen(self, waehrung: str = "usd",
                     zeitraum: str = VORGABE_ZEITRAUM,
                     erzwingen: bool = False) -> None:
        """Nachsehen, wenn es faellig ist. Ein Fehlschlag leert nichts.

        Der zuletzt bekannte Kurs bleibt stehen und wird mit seinem Alter
        angezeigt. Eine Tafel, die bei jedem Aussetzer leer wird, ist
        schlechter als eine, die sagt, wie alt ihre Zahl ist.
        """
        proxy = self._proxy_gibt()
        if not proxy:
            self._grund = "tor_aus"
            return
        jetzt = time.time()
        w = _pruefe_waehrung(waehrung)
        z = _pruefe_zeitraum(zeitraum)
        schluessel = f"{w}:{z}"

        if erzwingen or jetzt - self._kurs_stand.get(w, 0.0) >= (
                INTERVALL_SEKUNDEN):
            try:
                werte, _ = hole_kurs(w, proxy)
                self._kurs[w] = werte
                self._kurs_stand[w] = jetzt
                self._grund = ""
            except Abgewiesen as fehler:
                self._grund = str(fehler)

        alt = jetzt - self._verlauf_stand.get(schluessel, 0.0)
        if erzwingen or alt >= VERLAUF_INTERVALL_SEKUNDEN:
            try:
                punkte, boerse = hole_verlauf(w, z, proxy)
                self._verlauf[schluessel] = punkte
                self._verlauf_stand[schluessel] = jetzt
            except Abgewiesen as fehler:
                if not self._grund:
                    self._grund = str(fehler)

    def _passender_kurs(self, w: str) -> Dict:
        """Nur ein Kurs, der WIRKLICH zu dieser Waehrung gehoert.

        Doppelter Boden neben dem getrennten Zwischenspeicher: kaeme die
        Ablage je wieder durcheinander, ist "noch kein Kurs" das ehrliche
        Ergebnis. Eine falsche Zahl unter einem Waehrungszeichen ist
        schlimmer als gar keine -- sie sieht richtig aus.
        """
        gehalten = self._kurs.get(w) or {}
        return gehalten if gehalten.get("waehrung") == w else {}

    def in_gebrauch(self) -> List[Tuple[str, str]]:
        """Was der Waechter frisch halten soll.

        Nicht "alles" und nicht fest "usd", sondern das, was in der letzten
        Stunde tatsaechlich angesehen wurde -- die juengsten zuerst, gedeckelt.
        """
        jetzt = time.time()
        frisch = [(paar, t) for paar, t in self._benutzt.items()
                  if jetzt - t < GEBRAUCH_FRIST_SEKUNDEN]
        frisch.sort(key=lambda e: e[1], reverse=True)
        paare = [paar for paar, _ in frisch[:GEBRAUCH_HOECHSTENS]]
        return paare or [("usd", VORGABE_ZEITRAUM)]

    def als_dict(self, waehrung: str = "usd",
                 zeitraum: str = VORGABE_ZEITRAUM) -> Dict:
        w = _pruefe_waehrung(waehrung)
        z = _pruefe_zeitraum(zeitraum)
        # Hingesehen heisst in Gebrauch. Das ist eine Nebenwirkung im
        # Ablesepfad, und sie steht hier mit Absicht: dies ist die einzige
        # Stelle, die erfaehrt, was die Oberflaeche gerade zeigt.
        self._benutzt[(w, z)] = time.time()
        kurs_jetzt = self._passender_kurs(w)
        punkte = self._verlauf.get(f"{w}:{z}", [])
        return {
            "waehrung": w,
            "zeitraum": z,
            "zeitraeume": list(ZEITRAEUME),
            "waehrungen": list(WAEHRUNGEN),
            "kurs": kurs_jetzt.get("kurs"),
            "wechsel24": kurs_jetzt.get("wechsel24"),
            "hoch": kurs_jetzt.get("hoch"),
            "tief": kurs_jetzt.get("tief"),
            "boerse": kurs_jetzt.get("boerse", ""),
            "stand": self._kurs_stand.get(w) or None,
            # [Zeit, Schluss, Hoch, Tief] -- knapp gehalten,
            # bei 610 Punkten zaehlt jedes Feld.
            "verlauf": [list(p) for p in punkte],
            "grund": self._grund,
        }
