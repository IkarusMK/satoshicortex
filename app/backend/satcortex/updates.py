"""Nachsehen, ob es eine neuere Fassung gibt -- von Bitcoin Core und von LND.

Nur NACHSEHEN und MELDEN. Eingespielt wird von Hand: die Anwendung hat
bewusst keinen Docker-Socket, denn auf einem Geraet mit einer Wallet waere er
gleichbedeutend mit root. Ein Knopf, der so aussaehe, als koenne er
aktualisieren, waere schlimmer als keiner.

Die Abfrage laeuft ueber Tor, wenn Tor eingeschaltet ist. Sie verraet sonst,
dass hier jemand einen Bitcoin-Knoten betreibt -- und mit der Zeit auch, wann
er laeuft. Ueber Tor sieht die Gegenseite nur einen Exit-Knoten. Moeglich wird
das ohne zusaetzliche Abhaengigkeit, weil Tor neben SOCKS auch einen
HTTP-Tunnel anbietet (HTTPTunnelPort in der torrc); den versteht die
Standardbibliothek von sich aus.

ZWEI PROJEKTE, ZWEI ZAEHLWEISEN -- und das ist der eigentliche Grund fuer die
Projekt-Beschreibung weiter unten:

* Bitcoin Core zaehlt 31.1 -> 31.2 (Wartung) und 31.x -> 32.0 (Zweigwechsel).
  Der ZWEIG steckt in der ERSTEN Zahl. Und 30.3 ist trotz spaeteren
  Erscheinungsdatums KEIN Update fuer 31.1, sondern eine Nachlieferung fuer
  einen aelteren Zweig -- genau das hat am 27.08.2026 fuer Verwirrung gesorgt.

* LND zaehlt v0.21.2-beta. Die fuehrende Null wechselt nie; der Zweig steckt
  also in der ZWEITEN Zahl. Wer hier dieselbe Regel anwendet wie bei Core,
  haelt 0.22.0 fuer eine harmlose Wartungsversion -- dabei ist es der
  Zweigwechsel, bei dem LND seine Datenbank wandert. Und Wanderungen sind bei
  LND einbahnig: ein Rueckschritt wird ausdruecklich verweigert.
"""
from __future__ import annotations

import errno
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Zeitlimit je Versuch -- grosszuegig, weil der Weg ueber Tor geht.
#
# Vorher standen hier 15 Sekunden, und auf dem Knoten im Betrieb kam die Abfrage
# nie durch: in der Oberflaeche stand tagelang "Noch nicht nachgesehen". Eine
# Anfrage ueber Tor laeuft ueber drei fremde Rechner, und allein der
# TLS-Handschlag dauert dabei regelmaessig zehn bis zwanzig Sekunden -- der
# erste ueber einen frisch gebauten Kreis noch laenger. Fuenfzehn Sekunden
# sind da kein Zeitlimit, sondern ein Muenzwurf.
ZEITSPERRE_SEKUNDEN = 45

# Wie oft es versucht wird, bevor aufgegeben wird.
#
# Tor-Kreise sind unterschiedlich gut, und mancher Exit-Knoten wird von
# GitHub abgewiesen. Ein zweiter Anlauf nimmt oft einen anderen Weg. Mehr als
# drei waeren Trotz: dann liegt es nicht am Kreis.
VERSUCHE = 3

# Einmal am Tag genuegt. Beide Projekte erscheinen ein paar Mal im Jahr;
# haeufiger nachzufragen bringt nichts und faellt bei der Gegenseite nur auf.
INTERVALL_SEKUNDEN = 24 * 60 * 60

# Wie lange DERSELBE Fehlgrund nicht erneut auf WARNING gemeldet wird.
#
# Ein Fehlschlag wird absichtlich nicht als "erledigt" verbucht -- sonst
# schwiege die Anzeige einen ganzen Tag lang. Der Waechter fragt also alle
# zehn Minuten erneut. Steht der Grund aber fest, etwa weil ein Port keine
# Verbindungen annimmt, dann steht er in zehn Minuten immer noch fest, und
# dieselbe Zeile schreibt sich ins Protokoll, bis daneben nichts anderes mehr
# zu lesen ist. Gemeldet wird deshalb, wenn sich der Grund AENDERT -- und
# sonst hoechstens alle sechs Stunden.
MELDEBREMSE_SEKUNDEN = 6 * 3600

# Je Projekt: der zuletzt gemeldete Grund und wann. Modulweit, weil die
# Abfrage aus einem Hintergrundfaden kommt und keinen Ort hat, an dem sie
# sich etwas merken koennte.
_zuletzt_gemeldet: Dict[str, Tuple[str, float]] = {}

# Wie lange nach einem Fehlschlag gewartet wird, bevor es der naechste
# Waechterlauf noch einmal versucht -- wachsend.
#
# Der Anlass: der Waechter laeuft alle zehn Minuten. Ohne Bremse waeren das
# mal drei Versuchen, mal zwei Projekten sechsunddreissig Anfragen je Stunde
# an dieselbe Gegenstelle -- und genau das hat am 30.08.2026 mitgeholfen, das
# Anfragebudget des Tor-Ausgangsknotens aufzubrauchen. Wer auf eine Abfuhr
# haemmert, macht sie wahrscheinlicher.
#
# Der erste Fehlschlag darf ein Ausrutscher sein und wird bald wiederholt.
# Bleibt es dabei, wird der Abstand groesser -- bei einer Frage, deren Antwort
# sich ein paar Mal im Jahr aendert, kostet Warten nichts.
WARTEN_NACH_FEHLSCHLAG = (10 * 60, 30 * 60, 2 * 3600, 6 * 3600)


def wartezeit(fehlversuche: int) -> float:
    """Sekunden bis zum naechsten Versuch, nach so vielen Fehlschlaegen."""
    if fehlversuche <= 0:
        return 0.0
    return float(WARTEN_NACH_FEHLSCHLAG[
        min(fehlversuche, len(WARTEN_NACH_FEHLSCHLAG)) - 1])


_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")

# Absichtlich verankert: "v0.21.2-beta" ja, "v0.21.2-beta.rc1" nein. Die
# Vorabfassungen sind bei GitHub zwar als solche gekennzeichnet, aber darauf
# allein wollen wir uns nicht verlassen -- ein falsch gesetztes Haekchen
# wuerde sonst eine Vorabfassung als Update anbieten.
_LND_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-beta$")

# LND meldet im Betrieb "0.21.2-beta commit=v0.21.2-beta".
_LND_LAEUFT = re.compile(r"(\d+)\.(\d+)\.(\d+)-beta")


def zerlege(tag: str) -> Optional[Tuple[int, ...]]:
    """Core-Schema: "v31.1" -> (31, 1, 0). None, wenn es nicht passt."""
    treffer = _VERSION.match((tag or "").strip())
    if not treffer:
        return None
    haupt, neben, punkt = treffer.groups()
    return (int(haupt), int(neben), int(punkt or 0))


def zerlege_lnd(tag: str) -> Optional[Tuple[int, ...]]:
    """LND-Schema: "v0.21.2-beta" -> (0, 21, 2). None, wenn es nicht passt."""
    treffer = _LND_TAG.match((tag or "").strip())
    if not treffer:
        return None
    return tuple(int(z) for z in treffer.groups())


def laufende_version(subversion: str) -> Optional[Tuple[int, ...]]:
    """Aus "/Satoshi:31.1.0/" die Version des laufenden Knotens.

    Bewusst aus dem, was der Knoten SELBST meldet, und nicht aus dem
    Abbildnamen: Letzterer sagt nur, was gezogen werden sollte.
    """
    treffer = re.search(r"Satoshi:(\d+)\.(\d+)(?:\.(\d+))?", subversion or "")
    if not treffer:
        return None
    haupt, neben, punkt = treffer.groups()
    return (int(haupt), int(neben), int(punkt or 0))


def laufende_version_lnd(gemeldet: str) -> Optional[Tuple[int, ...]]:
    """Aus dem, was LND unter GetInfo.version meldet."""
    treffer = _LND_LAEUFT.search(gemeldet or "")
    if not treffer:
        return None
    return tuple(int(z) for z in treffer.groups())


def _core_beschriftung(v: Tuple[int, ...]) -> str:
    return ".".join(str(z) for z in v[:2])


def _lnd_beschriftung(v: Tuple[int, ...]) -> str:
    return "%d.%d.%d-beta" % v[:3]


def _satcortex_beschriftung(v: Tuple[int, ...]) -> str:
    """Drei Stellen -- und genau so heisst auch der Abbild-Tag.

    Bei Bitcoin Core sind es zwei (31.1), weil dort die dritte die
    Wartungsnummer ist und das Abbild sie nicht traegt. Hier traegt es sie:
    ghcr.io/ikarusmk/satcortex:1.0.1. Wer die Zahl aus der Oberflaeche in
    die .env abtippt, muss damit etwas ziehen koennen -- "1.0" gibt es
    nicht.
    """
    return "%d.%d.%d" % (v + (0, 0, 0))[:3]


@dataclass(frozen=True)
class Projekt:
    """Alles, was sich zwischen Core und LND unterscheidet, an einer Stelle."""

    name: str
    quelle: str
    abbild: str
    # Die Zeile in der .env, ueber die diese Version eingestellt wird -- und
    # das Praefix, mit dem der Abbild-Tag geschrieben ist. Bei LND heisst er
    # "v0.21.3-beta"; ohne das "v" nennt die Oberflaeche einen Namen, den es
    # in der Registry nicht gibt, und das Ziehen scheitert mit
    # "manifest unknown".
    variable: str
    tag_praefix: str
    # Wie viele der Zahlen den Zweig ausmachen. Core: 1 (31.x). LND: 2
    # (0.21.x), weil die fuehrende Null nie wechselt.
    zweigtiefe: int
    zerlege_tag: Callable[[str], Optional[Tuple[int, ...]]]
    beschrifte: Callable[[Tuple[int, ...]], str]


BITCOIN_CORE = Projekt(
    name="bitcoind",
    quelle="https://github.com/bitcoin/bitcoin/releases.atom",
    abbild="ghcr.io/ikarusmk/satcortex-bitcoind",
    variable="BITCOIN_VERSION",
    tag_praefix="",
    zweigtiefe=1,
    zerlege_tag=zerlege,
    beschrifte=_core_beschriftung,
)

LND = Projekt(
    name="lnd",
    quelle="https://github.com/lightningnetwork/lnd/releases.atom",
    abbild="ghcr.io/ikarusmk/satcortex-lnd",
    variable="LND_VERSION",
    tag_praefix="v",
    zweigtiefe=2,
    zerlege_tag=zerlege_lnd,
    beschrifte=_lnd_beschriftung,
)

# DIE EIGENE FASSUNG. Nachgetragen am 21.09.2026.
#
# Bis dahin sah diese Anwendung nach Neuerungen fuer bitcoind und LND -- und
# schwieg ueber sich selbst. Aus dem Betrieb kam der Fall: der Knoten lief auf
# 0.66, 1.0.1 lag seit Stunden bereit, und die Oberflaeche erwaehnte es mit
# keinem Wort. Der Betreiber ging stattdessen ueber die Docker-Oberflaeche
# seines NAS, die nur das zieht, was in der .env steht -- also wieder 0.66.
#
# Wer seine eigene Software ausliefert, soll auch sagen, wenn es eine neuere
# gibt. Die Quelle ist der Tag-Feed des Projekts: Releases gibt es nicht,
# Tags schon, und sie heissen genauso wie die Abbilder.
SATCORTEX = Projekt(
    name="satcortex",
    quelle="https://github.com/IkarusMK/satoshicortex/tags.atom",
    abbild="ghcr.io/ikarusmk/satcortex",
    variable="SATCORTEX_VERSION",
    tag_praefix="",
    # Zwei: 1.0 und 1.1 sind verschiedene Zweige, 1.0.1 ist Wartung darin.
    zweigtiefe=2,
    zerlege_tag=zerlege,
    beschrifte=_satcortex_beschriftung,
)

PROJEKTE = (SATCORTEX, BITCOIN_CORE, LND)

# Die LND-Fassung, die SatoshiCortex ausliefert.
#
# Solange der Dienst noch nicht laeuft, ist sie der einzige Vergleichspunkt --
# und das ist kein Notbehelf: die Frage "ist das Abbild, das wir ausliefern,
# noch aktuell?" stellt sich schon, bevor jemand Lightning einrichtet. Sobald
# es images/lnd/Dockerfile gibt, wacht ein Test darueber, dass beide Zahlen
# nicht auseinanderlaufen.
#
# Sie steht an DREI Stellen -- hier, als ARG im images/lnd/Dockerfile und als
# LND_VERSION in example.env. Ein Test vergleicht inzwischen alle drei; bis
# zum 03.09.2026 verglich er nur die ersten beiden, und weil die gemeinsam
# veralteten, blieb er gruen. Die Folge stand im Update-Kasten: "Version
# 0.21.3-beta ist verfuegbar", waehrend genau die schon lief.
LND_AUSGELIEFERT = (0, 21, 3)


def beurteile(laufend: Tuple[int, ...], kandidat: Tuple[int, ...],
              zweigtiefe: int = 1) -> str:
    """wartung | zweigwechsel | keiner"""
    if kandidat <= laufend:
        return "keiner"
    if kandidat[:zweigtiefe] > laufend[:zweigtiefe]:
        return "zweigwechsel"
    return "wartung"


def waehle(laufend: Tuple[int, ...], verfuegbar: List[Tuple[int, ...]],
           projekt: Projekt = BITCOIN_CORE) -> Optional[Dict]:
    """Die sinnvollste Neuerung -- oder None.

    Gemeldet wird hoechstens eine, und zwar die hoechste. Eine Nachlieferung
    fuer einen aelteren Zweig ist ausdruecklich kein Update: sie waere ein
    Rueckschritt.
    """
    neuere = [v for v in verfuegbar if v > laufend]
    if not neuere:
        return None
    beste = max(neuere)

    # Gibt es im EIGENEN Zweig noch etwas, ist das die dringlichere Meldung:
    # eine Wartungsversion laesst sich gefahrlos einspielen, ein Zweigwechsel
    # will gelesen werden.
    tiefe = projekt.zweigtiefe
    im_zweig = [v for v in neuere if v[:tiefe] == laufend[:tiefe]]
    gewaehlt = max(im_zweig) if im_zweig else beste

    zusatz = ""
    if im_zweig and beste[:tiefe] > laufend[:tiefe]:
        zusatz = projekt.beschrifte(beste)

    return {
        "version": projekt.beschrifte(gewaehlt),
        # Wie der Abbild-Tag WIRKLICH heisst. "version" ist die lesbare
        # Fassung fuer den Fliesstext; abgetippt wird diese hier.
        "tag": projekt.tag_praefix + projekt.beschrifte(gewaehlt),
        "art": beurteile(laufend, gewaehlt, tiefe),
        "auch_verfuegbar": zusatz,
    }


def _deutung(fehler: BaseException, proxy: Optional[str]) -> str:
    """Aus dem rohen Fehler eine Zeile machen, mit der sich etwas anfangen laesst.

    "URLError: <urlopen error [Errno 111] Connection refused>" nennt zwar den
    Fehler, aber nicht die Sache. Abgewiesen wird die Verbindung dabei nicht
    von GitHub, sondern vom eigenen Tor -- eine Anfrage, die den Rechner nie
    verlassen hat. Das ist ein ganz anderer Befund als ein Exit-Knoten, der
    nicht mag, und gehoert auch anders dazustehen.
    """
    grund = getattr(fehler, "reason", None) or fehler
    if isinstance(grund, ConnectionRefusedError) or (
            isinstance(grund, OSError) and grund.errno == errno.ECONNREFUSED):
        return (f"Der Tor-HTTP-Tunnel ({proxy}) nimmt keine Verbindungen an. "
                "Laeuft Tor -- und steht in seiner Konfiguration eine Zeile "
                "HTTPTunnelPort?")
    return f"{type(fehler).__name__}: {fehler}"


def _melde_fehlschlag(name: str, grund: str) -> None:
    """Einmal deutlich, danach leise -- solange sich nichts aendert."""
    jetzt = time.monotonic()
    vorher, wann = _zuletzt_gemeldet.get(name, ("", 0.0))
    if grund == vorher and jetzt - wann < MELDEBREMSE_SEKUNDEN:
        log.info("Versionsabfrage (%s) weiterhin ohne Erfolg: %s", name, grund)
        return
    _zuletzt_gemeldet[name] = (grund, jetzt)
    log.warning("Versionsabfrage (%s) nach %d Versuchen aufgegeben: %s",
                name, VERSUCHE, grund)


# Aus dem Atom-Feed die Kennung jeder Veroeffentlichung.
#
# WARUM NICHT DIE API: sie laesst ohne Anmeldung 60 Anfragen je Stunde und IP
# zu -- und ueber Tor teilen sich Hunderte Nutzer die IP des Ausgangsknotens.
# Am 30.08.2026 stand deshalb in das Betriebsprotokoll:
#
#     Versionsabfrage (lnd) nach 3 Versuchen aufgegeben:
#     HTTPError: HTTP Error 403: rate limit exceeded
#
# Nachgemessen: die API antwortet mit "x-ratelimit-limit: 60", der Atom-Feed
# schickt ueberhaupt keine Ratenkopfzeile -- er ist der gewoehnliche Web-Weg,
# nicht die Schnittstelle. Er traegt genau das, was wir brauchen: die Kennung
# der letzten zehn Veroeffentlichungen.
#
# Ausgewertet wird das <id>-Feld, nicht der Titel. Der Titel ist der frei
# gewaehlte Name ("Bitcoin Core 31.1"), die id traegt die Kennung selbst
# ("tag:github.com,2008:Repository/1181927/v31.1").
_ATOM_ID = re.compile(r"<id>tag:github\.com,\d+:Repository/\d+/([^<]{1,64})</id>")

# Der Feed ist rund 30 kB gross. Mehr als ein halbes Megabyte zu lesen waere
# kein Feed mehr, sondern ein Grund, misstrauisch zu werden -- und ueber einen
# fremden Ausgangsknoten will man dabei keine offene Grenze haben.
HOECHSTLAENGE = 512 * 1024


def hole_versionen(proxy: Optional[str] = None,
                   projekt: Projekt = BITCOIN_CORE) -> List[Tuple[int, ...]]:
    """Veroeffentlichte Fassungen abfragen. Leer, wenn es gerade nicht geht.

    Ein Fehlschlag ist ausdruecklich kein Drama: dann gibt es diesmal keine
    Meldung und beim naechsten Mal wird es erneut versucht. Ueber Tor kommt
    das vor -- manche Dienste weisen Exit-Knoten ab.
    """
    oeffner = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {})
    )
    anfrage = urllib.request.Request(projekt.quelle, headers={
        "Accept": "application/atom+xml",
        # Kein Kennzeichen, das den Betreiber wiedererkennbar macht.
        "User-Agent": "satcortex",
    })

    roh = None
    letzter = ""
    for versuch in range(1, VERSUCHE + 1):
        try:
            with oeffner.open(anfrage, timeout=ZEITSPERRE_SEKUNDEN) as antwort:
                roh = antwort.read(HOECHSTLAENGE).decode("utf-8", "replace")
            break
        except (urllib.error.URLError, OSError, ValueError,
                TimeoutError) as fehler:
            letzter = _deutung(fehler, proxy)
            log.info("Versionsabfrage (%s), Versuch %d von %d: %s",
                     projekt.name, versuch, VERSUCHE, letzter)

    if roh is None:
        # Auf WARNING, nicht auf INFO. Der Container protokolliert erst ab
        # WARNING -- auf INFO stand der Grund zwar im Code, aber nirgends,
        # wo ihn jemand haette lesen koennen. Genau deshalb sah es aus, als
        # wuerde gar nicht erst gefragt. Wiederholt wird die Meldung aber
        # nicht: siehe MELDEBREMSE_SEKUNDEN.
        _melde_fehlschlag(projekt.name, letzter)
        return []

    # Es geht wieder. Damit ist der naechste Fehlschlag ein neuer und wird
    # auch wieder deutlich gemeldet.
    _zuletzt_gemeldet.pop(projekt.name, None)

    # Auch der Erfolg gehoert ins Protokoll. Bis zum 05.09.2026 stand hier
    # ausschliesslich, wenn etwas SCHIEFGING -- und ein stilles Protokoll
    # sieht genauso aus wie eine Abfrage, die gar nicht erst laeuft.
    log.info("Versionsabfrage (%s): Antwort erhalten.", projekt.name)

    # Vorabfassungen fallen hier durch die Form der Kennung heraus, nicht
    # durch ein Haekchen der Gegenseite: "v31.1rc1" und "v0.21.3-beta.rc1"
    # passen auf keines der beiden Muster. Das ist der strengere Weg -- ein
    # falsch gesetztes Haekchen wuerde sonst eine Vorabfassung anbieten.
    versionen = []
    for kennung in _ATOM_ID.findall(roh):
        v = projekt.zerlege_tag(kennung)
        if v:
            versionen.append(v)
    return sorted(set(versionen))
