"""Sprechen mit LND ueber seine REST-Schnittstelle.

Warum REST und nicht gRPC: gRPC braeuchte grpcio und erzeugte Stubs im Repo.
grpcio ist ein grosses Rad, das auf arm64 gern selbst uebersetzt wird -- auf
einem NAS sind das Minuten bis Stunden Bauzeit fuer nichts. LNDs
REST-Gateway deckt dieselben Aufrufe ab, und die Standardbibliothek reicht
dafuer aus. Dieselbe Ueberlegung wie bei rpc.py fuer bitcoind.

Zwei Dinge unterscheiden LND von bitcoind:

* TLS. LND erzeugt sein Zertifikat selbst; wir pruefen es gegen genau diese
  Datei statt die Pruefung abzuschalten. Damit der Name stimmt, traegt die
  Konfiguration "tlsextradomain=lnd" -- der Compose-Name.
* Macaroons. Statt Benutzer und Passwort eine Datei mit Berechtigungen. Die
  Anwendung nimmt, wo immer es geht, das readonly.macaroon: sie soll den
  Knoten zeigen, nicht ueber ihn verfuegen.
"""
from __future__ import annotations

import base64
import hashlib
import shutil
import json
import os
import logging
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import fernzugang

log = logging.getLogger(__name__)

LNDDIR = Path("/fast/lnd")
ZERTIFIKAT = LNDDIR / "tls.cert"
MACAROONS = LNDDIR / "data" / "chain" / "bitcoin" / "mainnet"

def passwortdatei(fast: str = "") -> Path:
    """Woraus LND sich beim Start selbst entsperrt.

    Liegt bewusst NEBEN der Wallet und schuetzt sie deshalb nicht gegen
    jemanden, der die Platte hat -- der Tausch ist ein Knoten, der nach einem
    Stromausfall von allein weiterlaeuft, statt auf jemanden zu warten, der
    ein Passwort tippt.

    Der Pfad kommt aus den Einstellungen und ist nicht fest verdrahtet. In der
    Compose sehen Anwendung und LND denselben Einhaengepunkt (/fast), der Weg
    ist also fuer beide derselbe -- aber "ist in der Compose so" ist kein
    Grund, ihn in den Code zu schreiben. Ein Test hat genau darueber
    gestolpert: er wollte die Datei anlegen und landete auf /fast des
    Entwicklungsrechners.
    """
    return Path(fast or LNDDIR.parent) / "lnd" / "wallet.pass"


class NichtErreichbar(Exception):
    """LND antwortet nicht -- laeuft noch nicht oder gerade nicht."""


class Beschaeftigt(NichtErreichbar):
    """LND LAEUFT, kommt aber gerade nicht zum Antworten.

    Derselbe Unterschied wie in rpc.py, und aus demselben Grund: ein
    Zeitlimit heisst "da, aber beschaeftigt", eine abgelehnte Verbindung
    heisst "nicht da". Auf der bitcoind-Seite hat die Verwechslung Tage
    gekostet -- die Oberflaeche meldete "startet noch", waehrend der Knoten
    lief. Hier stand sie am 01.09.2026 noch offen: JEDES Zeitlimit wurde als
    NichtErreichbar gemeldet.

    Bei LND ist das keine Ausnahmelage, sondern der Normalfall beim Start:
    nach dem Entsperren laedt es den Kanalgraphen, und die REST-Antworten
    lassen dabei auf sich warten. Als Unterklasse von NichtErreichbar
    behandeln alle bisherigen Aufrufer sie unveraendert -- wer den
    Unterschied braucht, faengt sie vorher ab.
    """


class ZahlungUnterwegs(Beschaeftigt):
    """Die Zahlung ist losgeschickt, aber in der Frist kam kein Ergebnis.

    Traegt die Zahlungskennung, damit man sie weiterverfolgen kann. Als
    Unterklasse von Beschaeftigt behandelt jeder, der nur das kennt, sie
    unveraendert: "nicht wiederholen, der Ausgang ist offen".

    DER BEFUND VOM 24.09.2026: nach einem Umschichten ohne Antwort wusste
    die Oberflaeche nicht, WELCHE Zahlung sie weiterverfolgen soll.
    """

    def __init__(self, text: str, kennung: str) -> None:
        super().__init__(text)
        self.kennung = kennung


class LndFehler(Exception):
    """LND antwortet, lehnt den Aufruf aber ab."""


# Die Zustaende aus lnrpc/stateservice.proto, in der Reihenfolge des
# Lebenslaufs. Sie sind der Grund, warum die Oberflaeche ueberhaupt etwas
# Verlaessliches sagen kann, bevor eine Wallet existiert: der State-Dienst
# antwortet ab NON_EXISTING.
ZUSTAENDE = {
    "NON_EXISTING": "keine_wallet",     # noch keine Wallet angelegt
    "LOCKED": "gesperrt",               # Wallet da, Passwort fehlt
    "UNLOCKED": "startet",              # entsperrt, Dienst noch nicht bereit
    "RPC_ACTIVE": "startet",            # Dienst da, noch nicht voll bereit
    "SERVER_ACTIVE": "bereit",          # nimmt Aufrufe an
    "WAITING_TO_START": "wartet",       # nur im Cluster-Betrieb
}


# Wie viele Gegenstellen hoechstens im Graphen nachgeschlagen werden, und
# wie lange je Abfrage gewartet wird. Beides deckelt eine Anfrage der
# Oberflaeche auf hoechstens ein paar Sekunden statt auf die Summe aller
# Zeitlimits.
HOECHSTENS_GRAPHFRAGEN = 25
GRAPH_ZEITLIMIT_SEKUNDEN = 2.0

# "Nicht gesagt" und "kein Zeitlimit" sind ZWEI Wuensche, und `zeitlimit or
# self.zeitlimit` machte aus dem zweiten stillschweigend den ersten.
#
# DER BEFUND VOM 17.09.2026, an dem Knoten im Betrieb im Protokoll gefunden: der
# HTLC-Dauerlaeufer rief `strom(..., zeitlimit=None)` auf -- gemeint war "das
# ist ein Strom, der wartet". Angekommen ist die Vorgabe von fuenf Sekunden.
# Alle fuenf Sekunden lief die Leseuhr ab, der Strom riss ab, der Faden haengte
# sich neu an: rund 17.000 Mal am Tag, und jedes Mal ein `context canceled` in
# LNDs Protokoll. Ohne Kanaele war das nur Laerm. Mit Kanaelen waere in jedem
# Abrissfenster ein HTLC-Ereignis verloren -- LND hebt sie nicht auf.
#
# Ein eigener Wert fuer "nicht gesagt" haelt die beiden auseinander. Damit
# heisst None jetzt ueberall in dieser Datei, was es sagt.
VORGABE: Any = object()


@dataclass
class Knoten:
    host: str = "lnd"
    port: int = 8080
    zeitlimit: float = 5.0
    zertifikat: Path = ZERTIFIKAT
    macaroons: Path = MACAROONS

    # -------------------------------------------------------------- intern
    def _kontext(self) -> ssl.SSLContext:
        """TLS gegen LNDs eigenes Zertifikat pruefen.

        Selbstsigniert heisst nicht ungeprueft: wir kennen die Datei, weil
        sie im selben Datenverzeichnis liegt. Die Pruefung abzuschalten waere
        bequemer und waere genau der Fehler -- im Compose-Netz kann mehr als
        ein Container antworten.
        """
        return ssl.create_default_context(cafile=str(self.zertifikat))

    def _macaroon(self, name: str) -> Optional[str]:
        pfad = self.macaroons / f"{name}.macaroon"
        try:
            return pfad.read_bytes().hex()
        except OSError:
            # Vor der Wallet-Anlage gibt es noch keine Macaroons. Das ist
            # kein Fehler, sondern der Anfang.
            return None

    def strom(self, pfad: str, daten: Optional[Dict] = None,
              macaroon: str = "readonly", zeitlimit: Any = VORGABE,
              methode: str = ""):
        """Ein Aufruf, der NICHT einmal antwortet, sondern laufend.

        Genau einer wird hier gebraucht: das Zahlen. LNDs SendPaymentV2 ist
        ein Strom -- es meldet "unterwegs", dann "unterwegs ueber eine andere
        Route", und irgendwann "angekommen" oder "gescheitert". Ueber REST
        kommt das als eine JSON-Zeile je Meldung.

        "ruf" kann das nicht: es liest bis zum Ende und wirft den ganzen
        Rumpf durch json.loads -- bei mehreren Objekten hintereinander
        scheitert das. Deshalb hier ein eigener Weg, Zeile fuer Zeile.

        Gibt die Meldungen der Reihe nach heraus. Wer sie auswertet,
        entscheidet selbst, wann er aufhoert.

        "zeitlimit" kennt drei Faelle, und sie sind verschieden gemeint:
        weggelassen -> die Vorgabe des Knotens; eine Zahl -> genau die;
        None -> GAR KEINES. Das letzte braucht der HTLC-Strom: er wartet auf
        Ereignisse, die stunden- oder tagelang ausbleiben duerfen, und
        Schweigen ist dort kein Fehler, sondern der Normalfall.

        Ohne Zeitlimit zu lesen ist hier vertretbar, weil zwischen uns und LND
        NICHTS steht -- zwei Container am selben Docker-Netz. Stirbt LND,
        kommt ein RST oder ein FIN und das Lesen endet von selbst. Es gibt
        keine Zwischenstelle, die eine ruhende Verbindung stillschweigend
        vergisst. Ueber ein echtes Netz waere dieselbe Entscheidung falsch.
        """
        hexwert = self._macaroon(macaroon)
        if hexwert is None:
            raise NichtErreichbar(
                f"{macaroon}.macaroon fehlt -- es gibt noch keine Wallet.")
        anfrage = urllib.request.Request(
            f"https://{self.host}:{self.port}{pfad}",
            data=json.dumps(daten).encode("utf-8") if daten is not None else None,
            headers={"Content-Type": "application/json",
                     "Grpc-Metadata-macaroon": hexwert},
            # Das Schliessen eines Kanals ist ein DELETE und traegt keinen
            # Rumpf -- es ist aber genauso ein Strom wie das Zahlen.
            method=methode or ("POST" if daten is not None else "GET"))
        frist = self.zeitlimit if zeitlimit is VORGABE else zeitlimit
        try:
            with urllib.request.urlopen(                      # nosec B310
                    anfrage, timeout=frist,
                    context=self._kontext()) as antwort:
                for zeile in antwort:
                    roh = zeile.decode("utf-8").strip()
                    if not roh:
                        continue
                    try:
                        yield json.loads(roh)
                    except ValueError:
                        # Eine unverstaendliche Zwischenmeldung ist kein
                        # Grund, eine laufende Zahlung abzubrechen.
                        log.debug("Stromzeile nicht lesbar: %s", roh[:200])
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                grund = inhalt.get("message") or inhalt.get("error") or str(fehler)
            except (ValueError, OSError):
                grund = str(fehler)
            raise LndFehler(f"{fehler.code}: {grund}") from fehler
        except (urllib.error.URLError, socket.timeout, OSError,
                ssl.SSLError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            if isinstance(fehler, (socket.timeout, TimeoutError)) \
               or isinstance(grund, (socket.timeout, TimeoutError)):
                # Nicht mehr "die Zahlung": ueber diesen Weg laufen auch das
                # Schliessen eines Kanals und der HTLC-Strom. Die Frist
                # gehoert in die Meldung -- sonst sieht man im Protokoll
                # nicht, WELCHE Uhr abgelaufen ist.
                raise Beschaeftigt(
                    "keine Meldung innerhalb von "
                    + (f"{frist:.0f} s" if frist else "der Frist")) from fehler
            raise NichtErreichbar(str(fehler)) from fehler

    def ruf(self, pfad: str, macaroon: str = "readonly",
            daten: Optional[Dict] = None,
            zeitlimit: Optional[float] = None,
            methode: Optional[str] = None) -> Any:
        """Einen REST-Aufruf machen. Ohne "daten" ein GET, sonst ein POST.

        "methode" nur fuer das, was keines von beiden ist -- etwa ein DELETE
        zum Austragen eines Wachturms.
        """
        kopf = {"Content-Type": "application/json"}
        if macaroon:
            hexwert = self._macaroon(macaroon)
            if hexwert is None:
                raise NichtErreichbar(
                    f"{macaroon}.macaroon fehlt -- es gibt noch keine Wallet.")
            kopf["Grpc-Metadata-macaroon"] = hexwert

        rumpf = json.dumps(daten).encode("utf-8") if daten is not None else None
        anfrage = urllib.request.Request(
            f"https://{self.host}:{self.port}{pfad}",
            data=rumpf, headers=kopf,
            method=methode or ("POST" if daten is not None else "GET"))

        # Wie oben: "nicht gesagt" ist None, und nur das nimmt die Vorgabe.
        # Eine ausdrueckliche 0 bliebe sonst still auf fuenf Sekunden stehen.
        frist = self.zeitlimit if zeitlimit is None else zeitlimit
        try:
            with urllib.request.urlopen(
                    anfrage, timeout=frist,
                    context=self._kontext()) as antwort:      # nosec B310
                return json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            # LND legt den Grund in den Rumpf. Ihn wegzuwerfen und nur "500"
            # zu melden waere die haeufigste Art, eine Fehlersuche zu
            # verlaengern.
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                grund = inhalt.get("message") or inhalt.get("error") or str(fehler)
            except (ValueError, OSError):
                grund = str(fehler)
            raise LndFehler(f"{fehler.code}: {grund}") from fehler
        except (urllib.error.URLError, socket.timeout, OSError,
                ssl.SSLError) as fehler:
            # urllib verpackt das Zeitlimit in URLError -- der Grund steckt
            # dann in .reason. Ohne diesen Griff sieht ein Zeitlimit aus wie
            # ein abgelehnter Verbindungsversuch. Wortgleich zu rpc.py.
            grund = getattr(fehler, "reason", fehler)
            if isinstance(fehler, (socket.timeout, TimeoutError)) \
               or isinstance(grund, (socket.timeout, TimeoutError)):
                raise Beschaeftigt(
                    f"antwortet nicht innerhalb von {frist:.0f} s") from fehler
            raise NichtErreichbar(str(fehler)) from fehler
        except ValueError as fehler:
            raise LndFehler(f"unverstaendliche Antwort: {fehler}") from fehler

    def brocken(self, pfad: str, macaroon: str = "readonly",
                zeitlimit: Any = VORGABE,
                haeppchen: int = 256 * 1024):
        """Eine Antwort STUECKWEISE lesen, ohne sie ganz in den Speicher zu
        nehmen.

        Es gibt genau einen Aufruf bei LND, der das braucht: DescribeGraph.
        Er liefert den gesamten Netzgraphen in EINEM JSON-Dokument -- bei rund
        16.000 Knoten und 33.000 Kanaelen sind das zweistellige Megabyte am
        Stueck. "ruf" wuerde das komplett lesen und durch json.loads schicken;
        die entstehenden Python-Objekte sind ein Vielfaches des Rohtextes,
        und die Anwendung laeuft in einem Container mit 400 MB Grenze.

        Deshalb hier nur der Hahn: Haeppchen fuer Haeppchen, roh. Wer sie
        auswertet, entscheidet selbst, was er behaelt -- und was er sofort
        wieder wegwirft.

        "strom" kann das nicht: der liest ZEILEN und erwartet in jeder ein
        vollstaendiges JSON-Objekt. Ein grosses Dokument hat keine Zeilen.
        """
        hexwert = self._macaroon(macaroon)
        if hexwert is None:
            raise NichtErreichbar(
                f"{macaroon}.macaroon fehlt -- es gibt noch keine Wallet.")
        anfrage = urllib.request.Request(
            f"https://{self.host}:{self.port}{pfad}",
            headers={"Grpc-Metadata-macaroon": hexwert}, method="GET")
        frist = self.zeitlimit if zeitlimit is VORGABE else zeitlimit
        try:
            with urllib.request.urlopen(                      # nosec B310
                    anfrage, timeout=frist,
                    context=self._kontext()) as antwort:
                while True:
                    stueck = antwort.read(haeppchen)
                    if not stueck:
                        return
                    yield stueck
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                grund = inhalt.get("message") or inhalt.get("error") or str(fehler)
            except (ValueError, OSError):
                grund = str(fehler)
            raise LndFehler(f"{fehler.code}: {grund}") from fehler
        except (urllib.error.URLError, socket.timeout, OSError,
                ssl.SSLError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            if isinstance(fehler, (socket.timeout, TimeoutError)) \
               or isinstance(grund, (socket.timeout, TimeoutError)):
                raise Beschaeftigt(
                    "keine Antwort innerhalb von "
                    + (f"{frist:.0f} s" if frist else "der Frist")) from fehler
            raise NichtErreichbar(str(fehler)) from fehler


def zustand(knoten: Knoten) -> Dict[str, Any]:
    """Wo LND gerade steht -- ohne Macaroon, ab dem allerersten Start.

    Gibt immer ein Ergebnis zurueck, nie eine Ausnahme: fuer die Oberflaeche
    ist "LND laeuft noch nicht" ein Zustand wie jeder andere und kein Fehler.
    """
    if not knoten.zertifikat.exists():
        # Vor dem ersten Start von LND gibt es kein Zertifikat. Ohne diese
        # Abkuerzung liefe jeder Aufruf in einen TLS-Fehler, dessen Wortlaut
        # ("cafile ... no such file") niemandem etwas sagt.
        return {"da": False, "stand": "aus", "roh": None}
    try:
        antwort = knoten.ruf("/v1/state", macaroon="")
    except (NichtErreichbar, LndFehler) as fehler:
        log.debug("LND-Zustand nicht abrufbar: %s", fehler)
        return {"da": False, "stand": "aus", "roh": None}

    roh = (antwort or {}).get("state", "")
    return {"da": True, "stand": ZUSTAENDE.get(roh, "unbekannt"), "roh": roh}


# ── Wallet anlegen ────────────────────────────────────────────────────────
#
# Der heikelste Ablauf im ganzen Projekt, und zwar aus zwei Gruenden.
#
# 1. DER SEED. Vierundzwanzig Woerter, aus denen sich alles wiederherstellen
#    laesst. Die Vorgabe des Betreibers ist eindeutig: "eine wallet seed gehoert immer
#    auf ein blatt papier nie auf platte irgendwo". Er wird deshalb hier
#    erzeugt, EINMAL angezeigt und nie geschrieben -- nicht in eine Datei,
#    nicht ins Protokoll, nicht in den Zustand. Wer ihn nicht abschreibt, hat
#    ihn verloren, und genau so soll es sein.
#
# 2. DIE UNAUTHENTIFIZIERTE LUECKE. Solange keine Wallet existiert, nimmt LND
#    den Anlege-Aufruf OHNE Macaroon an -- LNDs eigene Doku warnt davor:
#    "the wallet creation RPC is unauthenticated and an attacker could inject
#    a seed while lnd is in that state". Deshalb bleibt
#    wallet-unlock-allow-create aus, und die Entsperrdatei kommt erst dazu,
#    wenn die Wallet steht.

# LND verlangt mindestens acht Zeichen. Wir erzeugen deutlich mehr, weil
# niemand es tippen muss -- siehe api.wallet_passwort.
PASSWORT_MINDESTLAENGE = 8

# aezeed: immer vierundzwanzig Woerter. Eine andere Zahl ist kein Seed.
SEED_WOERTER = 24


def erzeuge_seed(knoten: Knoten) -> list:
    """Vierundzwanzig Woerter von LND erzeugen lassen.

    Ohne Macaroon -- den gibt es vor der Wallet noch nicht. Der Aufruf ist
    folgenlos: LND wuerfelt und antwortet, angelegt wird dabei nichts. Wer
    abbricht, hinterlaesst keinen halben Zustand.
    """
    antwort = knoten.ruf("/v1/genseed", macaroon="")
    woerter = (antwort or {}).get("cipher_seed_mnemonic") or []
    if len(woerter) != SEED_WOERTER:
        raise LndFehler(
            f"LND lieferte {len(woerter)} Woerter statt {SEED_WOERTER}")
    return list(woerter)


# Wie weit LND beim Wiederherstellen nach benutzten Adressen sucht. Der Wert
# ist LNDs eigener: "Input an optional address look-ahead used to scan for used
# keys (default 2500)" (docs/recovery.md, v0.21.3-beta). Beim Anlegen einer
# frischen Wallet ist er null -- da gibt es nichts zu suchen, und jede Suche
# waere nur ein langer Kettendurchlauf ohne Ergebnis.
WIEDERHERSTELLUNG_FENSTER = 2500

# Die kleinstmoegliche verpackte Kanalsicherung. LNDs eigene Rechnung
# (chanbackup/multi.go, NilMultiSizePacked): "the 24 byte chacha nonce, the 16
# byte MAC, one byte for the version, and 4 bytes to signal zero entries".
# Mehr laesst sich ohne den Schluessel nicht pruefen -- alles darueber ist
# Zufallsrauschen, solange man den Seed nicht hat.
SICHERUNG_MINDESTGROESSE = 24 + 16 + 1 + 4


def lege_wallet_an(knoten: Knoten, passwort: str, woerter: list, *,
                   passphrase: str = "", fenster: int = 0,
                   kanalsicherung: str = "") -> None:
    """Die Wallet mit genau diesem Seed und diesem Passwort anlegen.

    Dieselbe Funktion legt an UND stellt wieder her -- weil LND es auch so
    macht. Der Unterschied sind drei Felder:

    * ``fenster`` (recovery_window) laesst LND die Kette nach schon benutzten
      Adressen absuchen. Null heisst "frisch angelegt, es gibt nichts zu
      finden"; beim Wiederherstellen gehoert WIEDERHERSTELLUNG_FENSTER hin.
    * ``kanalsicherung`` stoesst das Data-Loss-Protection-Verfahren an. Ohne
      sie kommen die On-Chain-Mittel zurueck, die Guthaben IN den Kanaelen
      nicht.
    * ``passphrase`` gibt es nur, wenn der Seed anderswo mit einer erzeugt
      wurde. SatoshiCortex selbst setzt nie eine.

    stateless_init bleibt AUS: mit ihm schriebe LND keine Macaroon-Dateien,
    und ohne die koennte die Oberflaeche ihren eigenen Knoten hinterher nicht
    mehr lesen.
    """
    if len(passwort) < PASSWORT_MINDESTLAENGE:
        raise ValueError("Das Wallet-Passwort ist zu kurz.")
    if len(woerter) != SEED_WOERTER:
        raise ValueError("Ein Seed hat vierundzwanzig Woerter.")
    daten: Dict[str, Any] = {
        # REST erwartet Byte-Felder als base64 -- so steht es in der
        # Swagger-Beschreibung von v0.21.2-beta ("string, format: byte").
        "wallet_password": base64.b64encode(passwort.encode()).decode(),
        # cipher_seed_mnemonic ist KEIN Byte-Feld, sondern "repeated string".
        # Wer es base64-kodiert, bekommt von LND eine Wallet mit einem
        # anderen Seed als dem auf dem Zettel.
        "cipher_seed_mnemonic": list(woerter),
        "stateless_init": False,
    }
    if passphrase:
        daten["aezeed_passphrase"] = base64.b64encode(
            passphrase.encode()).decode()
    if fenster:
        daten["recovery_window"] = int(fenster)
    if kanalsicherung:
        daten["channel_backups"] = {
            "multi_chan_backup": {"multi_chan_backup": kanalsicherung}}
    knoten.ruf("/v1/initwallet", macaroon="", daten=daten)


def entsperre(knoten: Knoten, passwort: str) -> None:
    """Eine bestehende Wallet entsperren."""
    knoten.ruf("/v1/unlockwallet", macaroon="", daten={
        "wallet_password": base64.b64encode(passwort.encode()).decode(),
    })


# ── Kanalsicherung ────────────────────────────────────────────────────────
#
# Die vierundzwanzig Woerter stellen die On-Chain-Wallet wieder her -- die
# Guthaben IN den Kanaelen nicht. Ein Kanal ist eine gemeinsame Ausgabe mit
# einer Gegenstelle, und um sie ohne deren Mithilfe aufzuloesen, braucht es
# den Zustand des Kanals. Genau der steht in dieser Sicherung.
#
# Sie ist verschluesselt, mit einem Schluessel aus dem Seed -- so steht es in
# LNDs eigener Beschreibung: "A single encrypted blob ... can be stored as a
# single file or blob, and safely be replaced with any prior/future versions."
# Deshalb darf sie ueberall hin: fremde Cloud, USB-Stick, Mail. Wer sie ohne
# die Woerter hat, hat nichts.
#
# Und deshalb ist sie ueberhaupt automatisierbar. Waere sie es nicht, muesste
# man sie wie den Seed behandeln -- und dann gaebe es sie in der Praxis nicht.


def sicherung_holen(knoten: Knoten) -> Dict[str, Any]:
    """Die Sicherung aller offenen Kanaele holen.

    Braucht Leserechte, nicht mehr: die Anwendung soll den Knoten sichern
    koennen, ohne ueber ihn verfuegen zu koennen.
    """
    antwort = knoten.ruf("/v1/channels/backup") or {}
    multi = antwort.get("multi_chan_backup") or {}
    blob = multi.get("multi_chan_backup") or ""
    punkte = multi.get("chan_points") or []
    # Die Kanalpunkte lesbar -- sie sind der Fingerabdruck der Sicherung,
    # denn der Klumpen selbst ist bei jeder Ausfuhr ein anderer (siehe
    # sicherung.inhalt).
    return {"blob": blob, "kanaele": len(punkte),
            "punkte": [_kanalpunkt(p) for p in punkte]}


def _kanalpunkt(punkt: Any) -> str:
    """Ein lnrpcChannelPoint als "txid:ausgang".

    REST liefert die txid als funding_txid_bytes (base64, interne
    Reihenfolge) oder als funding_txid_str -- lightning.swagger.json,
    v0.21.3-beta.
    """
    if not isinstance(punkt, dict):
        return str(punkt)
    txid = (str(punkt.get("funding_txid_str") or "")
            or _txid_lesbar(punkt.get("funding_txid_bytes") or ""))
    return f"{txid}:{_zahl(punkt.get('output_index'))}"


def sicherung_kanalpunkte(knoten: Knoten, blob: str) -> List[str]:
    """LND selbst nachsehen lassen, was in dieser Sicherung steht.

    Eine Sicherung, die nie geprueft wurde, ist eine Hoffnung. Der Aufruf
    kostet nichts und beweist zweierlei auf einmal, weil LND die Datei dafuer
    wirklich aufschliessen muss:

    * sie ist heil -- nicht abgeschnitten, nicht das falsche Ding,
    * und sie gehoert zu DIESEM Seed. Der Schluessel wird aus ihm abgeleitet
      (chanbackup/multi.go), die Sicherung eines fremden Knotens scheitert
      hier also, statt spaeter still nichts zurueckzuholen.

    Zurueck kommen die Kanalpunkte, die sie abdeckt. Ihre Anzahl gegen die
    offenen Kanaele zu halten, ist die zweite Haelfte der Probe: eine heile
    Datei von vorgestern deckt den Kanal von gestern nicht ab.

    Braucht offchain:read -- Lesen, mehr nicht.
    """
    antwort = knoten.ruf(
        "/v1/channels/backup/verify",
        daten={"multi_chan_backup": {"multi_chan_backup": blob}}) or {}
    return [str(p) for p in (antwort.get("chan_points") or [])]


def sicherung_pruefen(knoten: Knoten, blob: str) -> bool:
    """Wie sicherung_kanalpunkte, aber nur die Ja-Nein-Antwort.

    Fuer die Stellen, die weiterlaufen muessen statt zu scheitern.
    """
    try:
        sicherung_kanalpunkte(knoten, blob)
        return True
    except LndFehler as fehler:
        log.warning("Kanalsicherung nicht verwertbar: %s", fehler)
        return False


def sicherung_plausibel(roh: bytes) -> bool:
    """Was sich an einer Sicherung OHNE laufenden Knoten sagen laesst.

    Und das ist wenig: die Datei ist verschluesselt, ohne den Seed ist sie
    Rauschen. Geprueft wird deshalb nur die Groesse -- das faengt die Faelle
    ab, die in der Praxis wirklich vorkommen: eine leere Datei, ein
    abgebrochener Download, die Fehlerseite eines Servers statt der Datei.

    Beim Wiederherstellen ist das die einzige Probe, die es gibt: LND nimmt
    die Datei bei initwallet ungeprueft entgegen und scheitert erst beim
    Starten daran (server.go: "unable to unpack chan backup"). Deshalb wird
    hier wenigstens das Wenige geprueft, statt gar nichts.
    """
    return len(roh) >= SICHERUNG_MINDESTGROESSE


# ── Was der Knoten im Lightning-Netz ist und tut ──────────────────────────
#
# EINE EIGENHEIT VORWEG, die still falsche Zahlen erzeugt: LND schickt alle
# Betraege und Kennungen als ZEICHENKETTEN. Das ist kein Schoenheitsfehler,
# sondern Absicht -- es sind 64-Bit-Ganzzahlen, und JavaScript kann die nicht
# genau darstellen. Wer sie ungeprueft weiterreicht, bekommt in der Oberflaeche
# "1000000" neben "999999" sortiert und Summen, die nicht stimmen. Deshalb
# wird hier ueberall umgewandelt, und zwar an genau einer Stelle.


def _zahl(wert: Any, standard: int = 0) -> int:
    """Aus LNDs Zeichenkette eine Zahl. Unlesbares wird zum Standard."""
    try:
        return int(wert)
    except (TypeError, ValueError):
        return standard


def _betrag(feld: Any) -> int:
    """lnrpcAmount ist ein Objekt aus sat und msat -- wir nehmen sat."""
    if isinstance(feld, dict):
        return _zahl(feld.get("sat"))
    return _zahl(feld)


# getinfo ist der EINZIGE Aufruf dieser Anwendung, der LNDs Wallet anfasst
# -- er meldet unter anderem synced_to_chain und die Blockhoehe. Und genau
# deshalb braucht er mehr Luft als die fuenf Sekunden, die fuer alles andere
# reichen.
#
# DER BEFUND VOM 11.09.2026. Das Betriebsprotokoll nebeneinander:
#
#   App:  Lightning: knoten nicht abrufbar (antwortet nicht innerhalb von 5 s)
#         21:31:33 · 21:31:35 · 21:31:37 · 21:31:39
#   LND:  RPCS: elapsed time for diameter (11) calculation: 3.4 ms
#         21:31:33 · 21:31:35 · 21:31:37 · 21:31:39
#
# Dieselben Sekunden: der Graph-Aufruf antwortet in DREI MILLISEKUNDEN,
# getinfo laeuft ins Zeitlimit. LNDs RPC war also kerngesund -- nur die
# Wallet war beschaeftigt. Zwei Zeilen weiter stand auch womit:
#
#   BTWL: Received non-standard input sig=, witness=[]   (vielfach)
#
# BTWL ist btcwallet. Es durchsuchte die Kette nach benutzten Adressen --
# der Rueckweg einer Wiederherstellung, mit einem Suchfenster von 2500.
# Genau dann steht in "Deine Verbindungsadresse" nichts, weil getinfo die
# angekuendigten Adressen traegt. Fuenf Sekunden sind fuer einen ruhenden
# Knoten grosszuegig und fuer diesen Moment zu knapp.
UEBERSICHT_ZEITLIMIT_SEKUNDEN = 15.0


def uebersicht(knoten: Knoten,
               zeitlimit: Optional[float] = None) -> Dict[str, Any]:
    """Wer dieser Knoten ist, und wie er im Netz steht.

    Alles, was ohne Kanaele schon Sinn ergibt -- Alias, Kennung, angekuendigte
    Adressen. Gerade am Anfang ist das die interessantere Haelfte: es
    beantwortet "bin ich sichtbar?", lange bevor es "wieviel verdiene ich?"
    zu beantworten gibt.
    """
    d = knoten.ruf("/v1/getinfo",
                   zeitlimit=zeitlimit or UEBERSICHT_ZEITLIMIT_SEKUNDEN) or {}
    return {
        "kennung": d.get("identity_pubkey", ""),
        "alias": d.get("alias", ""),
        "farbe": d.get("color", ""),
        "fassung": d.get("version", ""),
        "adressen": list(d.get("uris") or []),
        "kanaele_aktiv": _zahl(d.get("num_active_channels")),
        "kanaele_still": _zahl(d.get("num_inactive_channels")),
        "kanaele_offen_werdend": _zahl(d.get("num_pending_channels")),
        "gegenstellen": _zahl(d.get("num_peers")),
        "hoehe": _zahl(d.get("block_height")),
        "kette_aktuell": bool(d.get("synced_to_chain")),
        "graph_aktuell": bool(d.get("synced_to_graph")),
    }


def guthaben(knoten: Knoten) -> Dict[str, int]:
    """On-Chain und in den Kanaelen -- zwei verschiedene Dinge.

    Sie zusammenzuzaehlen waere bequem und falsch: was in einem Kanal liegt,
    ist gebunden, bis der Kanal geschlossen wird. Und was auf der ANDEREN
    Seite liegt, ist gar nicht deins -- es ist aber genau das, was du
    empfangen kannst.
    """
    kette = knoten.ruf("/v1/balance/blockchain") or {}
    kanal = knoten.ruf("/v1/balance/channels") or {}
    return {
        "kette_gesamt": _zahl(kette.get("total_balance")),
        "kette_bestaetigt": _zahl(kette.get("confirmed_balance")),
        "kanal_hier": _betrag(kanal.get("local_balance")),
        "kanal_drueben": _betrag(kanal.get("remote_balance")),
    }


# Wie viele Bewegungen die Wallet-Ansicht zeigt. Mehr passt nicht sinnvoll auf
# eine Seite; eine aeltere txid findet man unter Bloecke.
BEWEGUNGEN_HOECHSTENS = 50


def bewegungen(knoten: Knoten,
               hoechstens: int = BEWEGUNGEN_HOECHSTENS) -> Dict[str, Any]:
    """Was in die On-Chain-Wallet kam und was sie verliess.

    Befund vom 15.09.2026, bei dem ersten Einzahlung: die Anwendung
    zeigte nur eine Zahl. Ob etwas angekommen war, unter welcher txid und mit
    wie vielen Bestaetigungen, liess sich nirgends ablesen -- und die Boerse
    nannte nur eine eigene Vorgangsnummer.

    GetTransactions ist ein GET auf /v1/transactions und braucht onchain:read
    (lightning.yaml und rpcserver.go, v0.21.3-beta). Ohne end_height liefert
    LND alles bis zur Kettenspitze EINSCHLIESSLICH der unbestaetigten.
    Betraege kommen als int64 und damit als Zeichenkette; ausgehende sind
    negativ.
    """
    d = knoten.ruf("/v1/transactions") or {}
    liste = []
    for tx in d.get("transactions") or []:
        etikett = str(tx.get("label") or "")
        art = ("kanal_auf" if "openchannel" in etikett
               else "kanal_zu" if "closechannel" in etikett else "")
        betrag = _mit_vorzeichen(tx.get("amount"))
        # Bei einem Ausgang: an WEN ging es? Die erste Ausgabe, die nicht uns
        # gehoert. Stand bis zum 16.09.2026 nur im Protokoll -- und genau die
        # braucht man, wenn ein Empfaenger bestreitet, etwas bekommen zu
        # haben.
        ziel = ""
        if betrag < 0:
            for ausgabe in tx.get("output_details") or []:
                if not ausgabe.get("is_our_address"):
                    ziel = str(ausgabe.get("address") or "")
                    break
        # Und welcher Ausgang gehoert UNS? Das ist das Wechselgeld, und nur
        # daran kann LND eine Kind-Transaktion haengen, um die Gebuehr
        # nachzubessern (CPFP). Gibt es keinen -- etwa weil alles verschickt
        # wurde --, geht das Nachbessern nicht, und dann darf die Oberflaeche
        # den Knopf auch nicht anbieten. Befund vom 22.09.2026.
        eigener = None
        for ausgabe in tx.get("output_details") or []:
            if ausgabe.get("is_our_address"):
                eigener = _mit_vorzeichen(ausgabe.get("output_index"))
                break
        liste.append({
            "txid": str(tx.get("tx_hash") or ""),
            "ziel": ziel,
            "betrag_sat": betrag,
            "bestaetigungen": max(0, _mit_vorzeichen(tx.get("num_confirmations"))),
            "hoehe": max(0, _mit_vorzeichen(tx.get("block_height"))),
            "zeit_s": max(0, _mit_vorzeichen(tx.get("time_stamp"))),
            "gebuehr_sat": max(0, _mit_vorzeichen(tx.get("total_fees"))),
            "art": art,
            "eigener_ausgang": eigener,
        })
    # Unbestaetigte zuerst -- genau die will man sehen, wenn man auf eine
    # Einzahlung wartet --, danach die juengsten Bloecke.
    liste.sort(key=lambda b: (b["bestaetigungen"] > 0, -b["hoehe"], -b["zeit_s"]))
    return {"bewegungen": liste[:hoechstens],
            "weitere": max(0, len(liste) - hoechstens)}


def _mit_vorzeichen(wert: Any) -> int:
    """Eine Ganzzahl aus LNDs JSON -- int64 kommt als Zeichenkette, auch negativ."""
    try:
        return int(str(wert))
    except (TypeError, ValueError):
        return 0


# Wieviel On-Chain liegenbleiben MUSS, wenn ein Kanal dazukommt.
#
# Aus dem Betrieb, 11.09.2026: "wenn ich einen Kanal erstellen will, dass er mir
# direkt sagt: ok, dein Knoten soll die Menge an Sat haben, dann musst du aber
# das plus Exit und Gebuehren an Sat einzahlen".
#
# Sein Gefuehl stimmt -- der Mechanismus ist nur ein anderer, als er klingt:
#
# * Die SCHLIESSGEBUEHR zahlt man nicht vorher ein. Beim einvernehmlichen
#   Schliessen wird sie vom Kanalguthaben abgezogen, nicht von der Wallet.
# * Was sehr wohl zusaetzlich in der Wallet liegen muss, ist die
#   ANKER-RUECKLAGE: Geld, mit dem LND einen erzwungenen Abschluss notfalls
#   nachfinanzieren kann (CPFP auf die Verpflichtungstransaktion).
#
# Die Zahl wird NICHT geschaetzt. LND kennt sie und nennt sie auf Nachfrage --
# nachgesehen in der API-Doku am 11.09.2026: GET /v2/wallet/reserve mit
# additional_public_channels, Antwort required_reserve.
RUECKLAGE_PFAD = "/v2/wallet/reserve?additional_public_channels="


def ruecklage(knoten: Knoten, zusaetzliche_kanaele: int = 1) -> Optional[int]:
    """Was On-Chain liegenbleiben muss, wenn so viele Kanaele dazukaemen.

    None statt 0, wenn LND nicht antwortet. Eine Null hiesse "du brauchst
    nichts zurueckzulegen" -- und genau das waere die Auskunft, an der man
    spaeter beim erzwungenen Schliessen scheitert.
    """
    try:
        d = knoten.ruf(RUECKLAGE_PFAD + str(int(zusaetzliche_kanaele)))
    except (NichtErreichbar, LndFehler) as fehler:
        log.debug("Ruecklage nicht zu haben: %s", fehler)
        return None
    if not isinstance(d, dict) or d.get("required_reserve") is None:
        return None
    return _zahl(d.get("required_reserve"))


def kanaele(knoten: Knoten) -> List[Dict[str, Any]]:
    """Die offenen Kanaele, mit dem, was im Betrieb zaehlt.

    peer_alias_lookup MUSS gesetzt werden -- laut LNDs eigener Beschreibung
    ist es "turned off by default". Ohne das steht in der Liste ueberall nur
    ein Schluessel aus 66 Zeichen, und niemand erkennt seine Gegenstellen
    wieder.
    """
    d = knoten.ruf("/v1/channels?peer_alias_lookup=true") or {}
    liste = []
    for k in d.get("channels") or []:
        kapazitaet = _zahl(k.get("capacity"))
        hier = _zahl(k.get("local_balance"))
        # DIE RESERVE, und sie fehlte bis zum 10.09.2026 ueberall.
        #
        # Nachgelesen bei lightningnode.info: jeder Kanal haelt auf beiden
        # Seiten ein Prozent der Kapazitaet zurueck. Es ist das Pfand, das
        # einen Betrugsversuch teuer macht -- und es ist NICHT ausgebbar.
        #
        # local_balance enthaelt es trotzdem. Wer also "hier: 146.000 sat"
        # las, sah eine Zahl, von der rund 1.460 sat gar nicht zur Verfuegung
        # stehen. Bei kleinen Kanaelen faellt das ins Gewicht, und der Tag,
        # an dem man es merkt, ist der, an dem eine Zahlung scheitert.
        reserve = _zahl(k.get("local_chan_reserve_sat"))
        liste.append({
            "aktiv": bool(k.get("active")),
            "gegenstelle": k.get("peer_alias") or "",
            "kennung": k.get("remote_pubkey", ""),
            "punkt": k.get("channel_point", ""),
            # Die Nummer, mit der LND einen Kanal in einer Route benennt.
            # Ohne sie liesse sich beim Umschichten nicht sagen, WELCHER
            # Kanal der Ausgang sein soll.
            "nummer": str(k.get("chan_id") or ""),
            "kapazitaet": kapazitaet,
            "hier": hier,
            "reserve": reserve,
            # Was davon wirklich hinausgehen kann.
            "verfuegbar": max(0, hier - reserve),
            "drueben": _zahl(k.get("remote_balance")),
            # Der eine Wert, an dem man einen Kanal im Betrieb erkennt: liegt
            # alles auf einer Seite, leitet er in eine Richtung nichts mehr
            # weiter. 0.0 = leer bei uns, 1.0 = voll bei uns.
            "anteil_hier": round(hier / kapazitaet, 3) if kapazitaet else 0.0,
            "privat": bool(k.get("private")),
            # Was die Gegenstelle GLEICHZEITIG von uns annimmt -- ihr
            # max_htlc_value_in_flight. DER BEFUND VOM 24.09.2026: LDK nimmt
            # nur 25 % der Kapazitaet, und ein Umschichten mit mehr als diesem
            # Anteil konnte deshalb nie gelingen.
            #
            # Es steht in LOCAL_constraints, nicht in remote_constraints --
            # nachgelesen in v0.21.3-beta: funding/manager.go gibt den Wert
            # der Gegenstelle an CommitConstraints, das legt ihn in UNSERE
            # Konfiguration, und lnwallet/channel.go prueft unsere eigenen
            # HTLCs gegen genau die. None heisst: unbekannt, NICHT null.
            "hinaus_hoechstens": _hoechstens_sat(k.get("local_constraints")),
            "umschichten_hoechstens": (
                None if _hoechstens_sat(k.get("local_constraints")) is None
                else umschichten_hoechstens(
                    _hoechstens_sat(k.get("local_constraints")))),
            # Welche Sitzung dieser Kanal bei einem Wachturm braucht. Ein
            # Turm, der nur Anker-Sitzungen haelt, bewacht keinen
            # Taproot-Kanal.
            "sitzungsart": sitzungsart(k.get("commitment_type")),
            "gesendet": _zahl(k.get("total_satoshis_sent")),
            "empfangen": _zahl(k.get("total_satoshis_received")),
            "laufzeit_s": _zahl(k.get("lifetime")),
            "erreichbar_s": _zahl(k.get("uptime")),
        })
    # Die stillen zuerst: ein Kanal, der nicht aktiv ist, ist das, was
    # Aufmerksamkeit braucht. Danach nach Kapazitaet.
    liste.sort(key=lambda k: (k["aktiv"], k["kapazitaet"]))
    return liste


def _hoechstens_sat(bedingungen: Any) -> Optional[int]:
    """max_pending_amt_msat in Satoshi -- oder None, wenn LND nichts sagt."""
    if not isinstance(bedingungen, dict):
        return None
    roh = bedingungen.get("max_pending_amt_msat")
    if roh is None:
        return None
    try:
        return int(roh) // 1000
    except (TypeError, ValueError):
        return None


def umschichten_hoechstens(grenze_sat: int) -> int:
    """Der groesste Betrag, der samt Gebuehrengrenze unter die Grenze passt.

    Das HTLC, das hinausgeht, traegt den Betrag PLUS die Gebuehren der
    Knoten dahinter. Genau an der Grenze haette der Rundweg also schon zu
    viel -- deshalb zaehlt die vorgeschlagene Gebuehrengrenze mit.
    """
    grenze = max(0, int(grenze_sat))
    b = int(grenze / (1 + GEBUEHRGRENZE_ANTEIL))
    while b > 0 and b + gebuehrgrenze(b) > grenze:
        b -= 1
    while b + 1 + gebuehrgrenze(b + 1) <= grenze:
        b += 1
    return b


def _ausstehend_eintrag(stand: str, k: Dict[str, Any]) -> Dict[str, Any]:
    kanal = k.get("channel") or {}
    punkt = str(kanal.get("channel_point") or "")
    return {
        "stand": stand,
        "gegenstelle": "",
        "kennung": str(kanal.get("remote_node_pub") or ""),
        "punkt": punkt,
        "kapazitaet": _zahl(kanal.get("capacity")),
        "hier": _zahl(kanal.get("local_balance")),
        "drueben": _zahl(kanal.get("remote_balance")),
        "privat": bool(kanal.get("private")),
        # Beim Oeffnen ist die txid der Teil vor dem Doppelpunkt.
        "txid": punkt.partition(":")[0],
    }


def ausstehende_kanaele(knoten: Knoten) -> List[Dict[str, Any]]:
    """Kanaele, die es noch nicht oder nicht mehr ganz gibt.

    DER BEFUND VOM 24.09.2026, aus dem Betrieb: "ich habe ja jetzt einen
    kanal geoeffnet zu den anderen partner B ... nur warum seh ich das nur in
    wallet und nicht unter kanal ?"

    /v1/channels kennt nur OFFENE Kanaele. Ein neuer Kanal steht dort erst,
    wenn die Gegenstelle genug Bestaetigungen hat -- wie viele, entscheidet
    SIE. Bis dahin stand er nur als Ausgabe in der Wallet, und in der
    Kanal-Ansicht fehlte er ganz. Dasselbe beim Schliessen: der Kanal faellt
    aus /v1/channels heraus, und das Geld darin ist eine Weile weder im
    Kanal noch in der Wallet zu sehen.

    Feldnamen aus LNDs eigener Beschreibung (lightning.swagger.json,
    v0.21.3-beta), nicht aus dem Gedaechtnis. pending_closing_channels ist
    dort als veraltet gefuehrt und wird nicht gelesen.
    """
    d = knoten.ruf("/v1/channels/pending") or {}
    liste: List[Dict[str, Any]] = []
    for k in d.get("pending_open_channels") or []:
        kanal = k.get("channel") or {}
        liste.append({
            **_ausstehend_eintrag("oeffnet", k),
            "von_uns": kanal.get("initiator") == "INITIATOR_LOCAL",
            # 0 heisst laut LND: jetzt aktiv. Bis zum naechsten Abruf
            # steht er dann schon unter den offenen.
            "noch_bloecke": _zahl(k.get("confirmations_until_active")),
        })
    for k in d.get("waiting_close_channels") or []:
        liste.append({
            **_ausstehend_eintrag("schliesst", k),
            "txid": str(k.get("closing_txid") or ""),
            "gesperrt": _zahl(k.get("limbo_balance")),
            "noch_bloecke": _zahl(k.get("blocks_til_close_confirmed")),
        })
    for k in d.get("pending_force_closing_channels") or []:
        liste.append({
            **_ausstehend_eintrag("zwangsschluss", k),
            "txid": str(k.get("closing_txid") or ""),
            "gesperrt": _zahl(k.get("limbo_balance")),
            # Negativ heisst: schon reif. Dann steht hier null.
            "noch_bloecke": max(0, _zahl(k.get("blocks_til_maturity"))),
        })
    # Den Namen aus dem eigenen Graphen. Wer noch keinen oeffentlichen Kanal
    # hat, steht dort nicht -- dann bleibt die Kennung, und der Kanal fehlt
    # deswegen nicht.
    for eintrag in liste[:HOECHSTENS_GRAPHFRAGEN]:
        if not eintrag["kennung"]:
            continue
        try:
            g = knoten.ruf(f"/v1/graph/node/{eintrag['kennung']}",
                           macaroon=EIGENES_MACAROON,
                           zeitlimit=GRAPH_ZEITLIMIT_SEKUNDEN) or {}
        except (NichtErreichbar, LndFehler) as fehler:
            log.debug("Kein Graph-Eintrag zu %s: %s",
                      eintrag["kennung"][:12], fehler)
            continue
        eintrag["gegenstelle"] = str((g.get("node") or {}).get("alias") or "")
    return liste


# Welche Abgleichsarten heissen: ueber diese Leitung kommt die Netzkarte.
# SyncType aus lightning.proto -- REST schickt den Namen, die Nummer wird
# trotzdem verstanden.
_ABGLEICH_AKTIV = ("ACTIVE_SYNC", "PINNED_SYNC", "1", "3")


def verbindungen(knoten: Knoten,
                 kanaele_liste: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mit welchen Knoten gerade eine LEITUNG besteht -- mit Kanal oder ohne.

    Nicht zu verwechseln mit den Kanalpartnern. Bis zum 14.09.2026 hiess
    beides "Gegenstellen": die Zahl unter "Dein Knoten im Netz" zaehlte
    Leitungen (getinfo, num_peers), die Liste unter "Knoten" zeigte
    Kanalpartner -- ueberschrieben mit "mit wem du direkt verbunden bist".
    Wer sich verband, fand die Verbindung danach nirgends wieder.

    Leitungen ohne Kanal sind Alltag: LND haelt von sich aus mindestens drei,
    um die Netzkarte abzugleichen (server.go, defaultMinPeers). Das Recht
    dafuer, peers:read, steckt im readonly.macaroon.

    Die Adresse der Gegenseite kommt bewusst NICHT mit: bei eingehenden
    Verbindungen ist das die IP eines anderen, womoeglich sein Anschluss zu
    Hause.
    """
    d = knoten.ruf("/v1/peers") or {}
    partner = {k.get("kennung"): k.get("gegenstelle") or ""
               for k in kanaele_liste if k.get("kennung")}
    raus = []
    for peer in d.get("peers") or []:
        kennung = peer.get("pub_key", "")
        raus.append({
            "kennung": kennung,
            "name": partner.get(kennung, ""),
            "mit_kanal": kennung in partner,
            "eingehend": bool(peer.get("inbound")),
            "netzkarte": str(peer.get("sync_type", "")).upper() in _ABGLEICH_AKTIV,
        })
    # Kanalpartner zuerst: sie sind es, an denen Geld haengt.
    raus.sort(key=lambda v: (not v["mit_kanal"], v["name"] or v["kennung"]))
    return raus


def gegenstellen(knoten: Knoten) -> List[Dict[str, Any]]:
    """Mit wem wir Kanaele haben -- und wo die sich im Netz melden.

    Fuer die orangen Linien auf der Weltkarte. Die Adressen stehen nicht in
    der Kanalliste, sie stehen im Graphen: jeder Knoten kuendigt sie per
    node_announcement an. Geprueft gegen lnrpc/lightning.proto:

        LightningNode { ... repeated NodeAddress addresses = 4; ... }
        NodeAddress   { string network = 1; string addr = 2; }

    Zwei Kanaele zur selben Gegenstelle werden zusammengefasst. Sonst zaehlte
    sie auf der Karte doppelt -- und wir fragten den Graphen zweimal nach
    derselben Auskunft.

    Ein Knoten, der nicht im Graphen steht, kommt trotzdem in die Liste, nur
    ohne Adressen: er hat sich nie angekuendigt (private Kanaele, frisch
    dazugekommen), und das ist Alltag. Ihn wegzulassen hiesse, Kapital zu
    verschweigen, das dort tatsaechlich liegt.
    """
    raus: List[Dict[str, Any]] = []
    nach_schluessel: Dict[str, Dict[str, Any]] = {}
    for kanal in kanaele(knoten):
        schluessel = kanal.get("kennung") or ""
        eintrag = nach_schluessel.get(schluessel)
        if eintrag is None:
            eintrag = {
                "kennung": schluessel,
                "alias": kanal.get("gegenstelle") or schluessel[:12],
                "kapazitaet": 0,
                "kanaele": 0,
                "adressen": [],
            }
            nach_schluessel[schluessel] = eintrag
            raus.append(eintrag)
        eintrag["kapazitaet"] += int(kanal.get("kapazitaet") or 0)
        eintrag["kanaele"] += 1

    # Erst sortieren, DANN fragen. Jede Abfrage ist ein eigener
    # REST-Aufruf mit eigenem Zeitlimit, und sie laufen nacheinander: bei
    # dreissig Gegenstellen und einem langsamen LND waeren das im
    # schlimmsten Fall dreissig mal fuenf Sekunden, alle auf dem Weg einer
    # Anfrage der Oberflaeche. Die Karte zeichnet Linien nach Kapazitaet --
    # was unten steht, ist dort ohnehin ein Haarstrich.
    raus.sort(key=lambda g: -g["kapazitaet"])
    for eintrag in raus[:HOECHSTENS_GRAPHFRAGEN]:
        if not eintrag["kennung"]:
            continue
        try:
            d = knoten.ruf(f"/v1/graph/node/{eintrag['kennung']}",
                           macaroon=EIGENES_MACAROON,
                           zeitlimit=GRAPH_ZEITLIMIT_SEKUNDEN) or {}
        except (NichtErreichbar, LndFehler) as fehler:
            log.debug("Kein Graph-Eintrag zu %s: %s",
                      eintrag["kennung"][:12], fehler)
            continue
        knotendaten = d.get("node") or {}
        if knotendaten.get("alias"):
            eintrag["alias"] = knotendaten["alias"]
        eintrag["adressen"] = [a.get("addr", "")
                               for a in (knotendaten.get("addresses") or [])
                               if a.get("addr")]
    # Groesste zuerst -- oben schon geschehen. kanaele() sortiert bewusst
    # andersherum: dort zaehlt, was Aufmerksamkeit braucht (die stillen).
    # Hier zaehlt, wo das Kapital liegt, und das liest man von oben nach
    # unten.
    return raus


def netzgraph(knoten: Knoten) -> Dict[str, int]:
    """Wie gross das Netz ist, in dem dieser Knoten steht."""
    d = knoten.ruf("/v1/graph/info") or {}
    return {
        "knoten": _zahl(d.get("num_nodes")),
        "kanaele": _zahl(d.get("num_channels")),
        "kapazitaet": _zahl(d.get("total_network_capacity")),
        "median_kanal": _zahl(d.get("median_channel_size_sat")),
        "grad_mittel": float(d.get("avg_out_degree") or 0.0),
    }


# LNDs Weiterleitungs-Historie blaettert VOM AELTESTEN AUFWAERTS. Seine
# eigene Beschreibung, am 10.09.2026 nachgeschlagen:
#
#   index_offset       "the offset in the time series to start at"
#   last_offset_index  "The index of the last time in the set of returned
#                       forwarding events. Can be used to seek further,
#                       pagination style."
#
# Ein einzelner Aufruf mit Offset 0 liefert also die AELTESTEN. Genau so
# stand es hier bis zum 10.09.2026, mit 500 Stueck: ab der 501. Weiterleitung
# waere "Sats verdient" auf der Summe der ersten 500 eingefroren, und "die
# letzten zwanzig" waeren die Nummern 481-500 gewesen. Eine Zahl, die still
# falsch wird, ohne dass jemand einen Fehler sieht.
#
# Deshalb wird geblaettert, bis nichts mehr kommt. Die Seite ist gross genug,
# dass ein Heimknoten jahrelang mit einem Aufruf auskommt.
WEITERLEITUNG_SEITE = 10_000
# Und eine Notbremse: liefert ein Knoten immer wieder dieselbe volle Seite,
# darf uns das nicht in eine Endlosschleife ziehen.
WEITERLEITUNG_SEITEN_HOECHSTENS = 20
# So viele Weiterleitungen zeigt die Oberflaeche einzeln.
WEITERLEITUNG_ZEIGEN = 20


def weiterleitungen(knoten: Knoten) -> Dict[str, Any]:
    """Was FREMDE durch diesen Knoten geschickt haben.

    Der Moment, in dem der Knoten wirklich Teil des Netzes ist -- nicht die
    erste eigene Zahlung, sondern die erste fremde, die hindurchgeht.
    """
    anzahl = menge = gebuehr = 0
    letzte_roh: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(WEITERLEITUNG_SEITEN_HOECHSTENS):
        d = knoten.ruf("/v1/switch", macaroon="readonly", daten={
            "index_offset": offset,
            "num_max_events": WEITERLEITUNG_SEITE,
            "peer_alias_lookup": True,
        }) or {}
        seite = d.get("forwarding_events") or []
        if not seite:
            break
        anzahl += len(seite)
        gebuehr += sum(_zahl(e.get("fee_msat")) for e in seite)
        menge += sum(_zahl(e.get("amt_out")) for e in seite)
        # Nur das Ende mitschleppen -- der Rest waere Ballast im Speicher.
        letzte_roh = (letzte_roh + seite)[-WEITERLEITUNG_ZEIGEN:]
        if len(seite) < WEITERLEITUNG_SEITE:
            break
        # Ohne Fortschritt im Offset waere die naechste Seite dieselbe.
        weiter = _zahl(d.get("last_offset_index"))
        offset = weiter if weiter > offset else offset + len(seite)
    letzte = [{
        # "timestamp" ist in LNDs eigener Beschreibung als veraltet markiert
        # ("Deprecated by timestamp_ns"), am 03.09.2026 nachgeschlagen. Es
        # steht heute noch drin -- aber veraltete Felder verschwinden
        # irgendwann, und dann staende hier bei jeder Weiterleitung 1970.
        # Nanosekunden, also durch eine Milliarde; der Rueckfall bleibt fuer
        # den Fall, dass eine aeltere Fassung nur das alte Feld kennt.
        "zeitpunkt": (_zahl(e.get("timestamp_ns")) // 1_000_000_000
                      or _zahl(e.get("timestamp"))),
        "von": e.get("peer_alias_in") or "",
        "nach": e.get("peer_alias_out") or "",
        "menge": _zahl(e.get("amt_out")),
        "gebuehr_msat": _zahl(e.get("fee_msat")),
    } for e in letzte_roh]
    letzte.reverse()
    return {
        "anzahl": anzahl,
        "menge": menge,
        "gebuehr_msat": gebuehr,
        "letzte": letzte,
    }


# ── Ein eigenes Macaroon -- und was es darf ───────────────────────────────
#
# Jede Stufe wurde bewusst entschieden:
#
#   31.08.2026  Kein Recht, das Geld bewegt; die Oberflaeche oeffnet keine
#               Kanaele.
#   10.09.2026  onchain:write kommt dazu, hinter der PIN -- Senden, damit man
#               aus der Wallet wieder herauskommt.
#   12.09.2026  Kanal oeffnen, Kanal schliessen und Lightning zahlen kommen
#               dazu, alle hinter derselben PIN. Damit ist auch offchain:write
#               entschieden (siehe unten).
#
# LNDs Rechtetabelle trennt dabei nicht, was man gern getrennt haette
# (rpcserver.go, v0.21.2-beta):
#
#   NewAddress          -> address:write
#   UpdateChannelPolicy -> offchain:write
#   ConnectPeer         -> peers:write
#   OpenChannel         -> onchain:write + offchain:write
#   SendCoins           -> onchain:write        <-- dieselbe Berechtigung
#
# Das admin.macaroon liegt trotzdem auf der Platte -- LND schreibt es. Wer die
# Platte hat, hat es. Gegen eine uebernommene SITZUNG in der Weboberflaeche
# steht deshalb nicht das Macaroon, sondern die PIN: jeder Endpunkt, der Geld
# aus der Hand gibt, prueft sie.
EIGENES_MACAROON = "satcortex"

EIGENE_RECHTE = (
    ("info", "read"),
    ("onchain", "read"),
    ("offchain", "read"),
    ("address", "read"),
    ("peers", "read"),
    ("invoices", "read"),
    # Ab hier schreibend.
    # Rechnungen ausstellen. Kam am 12.09.2026 dazu, fuer das UMSCHICHTEN
    # zwischen eigenen Kanaelen: das laeuft als Zahlung an sich selbst, und
    # dafuer braucht es zuerst eine eigene Rechnung.
    #
    # Was es erlaubt: eine Forderung aufmachen. Das bewegt KEIN Geld aus der
    # Wallet heraus -- im Gegenteil, es ist die Voraussetzung dafuer, welches
    # hereinzubekommen. Das schwerste, was jemand damit anrichten kann, ist
    # eine Rechnung auszustellen, die niemand bezahlt.
    ("invoices", "write"),
    ("address", "write"),      # Einzahladressen erzeugen
    # ACHTUNG, und das stand hier bis zum 07.09.2026 falsch: "keines davon
    # bewegt Geld" gilt fuer offchain:write NICHT. Nachgeschlagen in LNDs
    # eigener Rechtetabelle, v0.21.3-beta:
    #
    #   lnrpc/routerrpc/router_server.go:
    #     "/routerrpc.Router/SendPaymentV2": {{Entity: "offchain",
    #                                          Action: "write"}}
    #
    # Dasselbe Recht, mit dem dieser Knoten seine Kanalgebuehren setzt,
    # erlaubt ueber REST ein POST auf /v2/router/send -- also eine
    # Lightning-Zahlung. LND trennt das nicht, und ein Macaroon kennt keine
    # Betragsgrenze (macaroons/constraints.go: nur Ablaufzeit, IP-Bindung und
    # freie Bedingungen, die einen eingebauten Acceptor braeuchten).
    #
    # Bis zum 12.09.2026 stand hier, der eigentliche Schutz sei, dass die
    # Anwendung KEINEN Endpunkt anbietet, der zahlt -- und ob das Recht
    # bleibt, sei eine offene Abwaegung gegen die Gebuehrensteuerung. Beides
    # ist ueberholt: seit dem 12.09.2026 zahlt die Anwendung selbst ueber
    # Lightning (/lightning/rechnung/zahlen), schichtet zwischen eigenen
    # Kanaelen um (/lightning/umschichten) und oeffnet Kanaele (OpenChannel
    # braucht es mit). Alle drei brauchen genau dieses Recht, alle drei stehen
    # hinter der PIN. Entschieden ist damit: das Recht bleibt.
    #
    # Was weiterhin gilt: wer die Macaroon-DATEI hat, kann ohne PIN zahlen --
    # der hat dann aber ohnehin die Platte, und dort liegt auch das
    # admin.macaroon.
    ("offchain", "write"),     # Lightning zahlen, umschichten, Kanal, Gebuehren
    ("peers", "write"),        # sich mit einer Gegenstelle verbinden
    # Eine Nachricht mit dem Knotenschluessel unterschreiben. Bewegt kein
    # Geld -- es beweist nur, dass dieser Knoten einem gehoert.
    #
    # Aus dem Betrieb, 04.09.2026: "was ich auch gesehen habe, dass man im
    # LightningNetwork+ sich signieren muss ... ich hoffe, dass unser Knoten
    # dann auch alle notwendigen Funktionen beherrscht, die wir brauchen, um
    # uns groesseren Netzwerken anzuschliessen."
    #
    # Er hat richtig hingesehen: genau dieses Recht fehlte. Ohne
    # message:write scheitert SignMessage -- nachgeschlagen in LNDs
    # rpcserver.go, v0.21.3-beta:
    #   "/lnrpc.Lightning/SignMessage": {{Entity: "message", Action: "write"}}
    # Damit haette sich die Anwendung bei keiner dieser Stellen ausweisen
    # koennen.
    ("message", "write"),
    # Und das Gegenstueck. Ohne message:read kann die Anwendung
    # unterschreiben, aber ihre eigene Unterschrift nicht nachrechnen --
    # sie sieht die richtige FORM und nicht die Richtigkeit. Es bewegt kein
    # Geld und gibt keinen Schluessel preis; es liest nur nach.
    ("message", "read"),
    # SENDEN. Das schwerste Recht in dieser Liste, und es kam erst am
    # 10.09.2026 dazu -- nach der Bedingung des Betreibers vom 30.08.2026: "ich werde
    # nix dahin ueberweisen solange ich es nicht zurueck schicken kann".
    # Eine Wallet, aus der man nicht wieder herauskommt, ist keine Wallet,
    # sondern ein Einbahnstrassenschild.
    #
    # Was es erlaubt, nachgeschlagen in LNDs eigener Rechtetabelle
    # (rpcserver.go, v0.21.3-beta): "/lnrpc.Lightning/SendCoins" und
    # "/lnrpc.Lightning/OpenChannel" haengen BEIDE an onchain:write. LND
    # trennt das nicht, und ein Macaroon kennt keine Betragsgrenze
    # (macaroons/constraints.go: nur Ablaufzeit, IP-Bindung und freie
    # Bedingungen, die einen eingebauten Acceptor braeuchten).
    #
    # WAS SICH DADURCH AENDERT -- und was nicht:
    #
    #   * Fuer jemanden mit der PLATTE aendert sich NICHTS. Dort liegt
    #     ohnehin LNDs eigenes admin.macaroon, und das kann alles. Unser
    #     Macaroon macht diesen Angreifer nicht maechtiger.
    #   * Fuer eine uebernommene SITZUNG in dieser Oberflaeche aendert sich
    #     alles: ab jetzt gibt es einen Endpunkt, der zahlt. Genau dagegen
    #     steht die PIN, und deshalb kam sie zuerst.
    ("onchain", "write"),
)

# Woran sich erkennen laesst, ob ein abgelegtes Macaroon noch zu obiger Liste
# passt. Ohne diese Marke wuerde ein neues Recht bei bestehenden Anlagen NIE
# ankommen: gebacken wird nur, wenn gar keines da ist.
RECHTE_MARKE = "satcortex.rechte"


def rechte_kennung() -> str:
    """Ein kurzer Fingerabdruck der Rechteliste."""
    roh = ";".join(f"{a}:{b}" for a, b in EIGENE_RECHTE).encode()
    return hashlib.sha256(roh).hexdigest()[:16]


def rechte_passen(verzeichnis: Path) -> bool:
    """Ob das abgelegte Macaroon zur aktuellen Rechteliste gehoert."""
    try:
        return (verzeichnis / RECHTE_MARKE).read_text().strip() == rechte_kennung()
    except OSError:
        return False


def merke_rechte(verzeichnis: Path) -> None:
    (verzeichnis / RECHTE_MARKE).write_text(rechte_kennung(), encoding="utf-8")


def unterschreibe(knoten: Knoten, text: str) -> str:
    """Eine Nachricht mit dem Knotenschluessel unterschreiben.

    Das ist der Ausweis gegenueber Diensten wie LightningNetwork+: sie geben
    einen Text vor, man unterschreibt ihn, und damit ist bewiesen, dass einem
    der Knoten gehoert. Es bewegt kein Geld und gibt keinen Schluessel preis.

    REST erwartet die Nachricht als base64 ("must be encoded as base64"),
    zurueck kommt eine Unterschrift in zbase32.
    """
    if not text.strip():
        raise LndFehler("Es gibt nichts zu unterschreiben.")
    antwort = knoten.ruf("/v1/signmessage", macaroon=EIGENES_MACAROON, daten={
        "msg": base64.b64encode(text.encode("utf-8")).decode(),
    }) or {}
    unterschrift = antwort.get("signature") or ""
    if not unterschrift:
        raise LndFehler("LND lieferte keine Unterschrift.")
    return unterschrift


def backe_macaroon(knoten: Knoten) -> str:
    """Das eigene Macaroon von LND backen lassen. Braucht einmal admin.

    Einmal, direkt nach dem Anlegen der Wallet. Danach nutzt die Anwendung
    nur noch das gebackene und fasst admin nicht mehr an.
    """
    antwort = knoten.ruf("/v1/macaroon", macaroon="admin", daten={
        "permissions": [{"entity": e, "action": a} for e, a in EIGENE_RECHTE],
    }) or {}
    hexwert = antwort.get("macaroon") or ""
    if not hexwert:
        raise LndFehler("LND hat kein Macaroon zurueckgegeben")
    return hexwert


def lege_macaroon_ab(hexwert: str, verzeichnis: Optional[Path] = None) -> Path:
    """Das gebackene Macaroon dorthin, wo _macaroon() es findet."""
    ziel = (verzeichnis or MACAROONS) / f"{EIGENES_MACAROON}.macaroon"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    temp = ziel.with_name(ziel.name + ".neu")
    temp.write_bytes(bytes.fromhex(hexwert))
    os.chmod(temp, 0o600)
    os.replace(temp, ziel)
    return ziel


def macaroon_da(knoten: Knoten) -> bool:
    return (knoten.macaroons / f"{EIGENES_MACAROON}.macaroon").exists()


# ── Schluessel fuer externe Wallets ─────────────────────────────────────────
#
# Aus dem Betrieb, 26.09.2026: Zeus soll den Knoten vom Telefon aus bedienen,
# mit Rechten, die in dieser Anwendung eingestellt werden. Welche Rechte
# welche Stufe bekommt, steht in fernzugang.py; hier wird nur mit LND
# gesprochen.
#
# ALLE DREI mit admin. Backen verlangt macaroon:generate, Loeschen
# macaroon:write, Auflisten macaroon:read -- und das eigene Macaroon der
# Anwendung haelt keines davon, mit Absicht (EIGENE_RECHTE): mit
# macaroon:generate koennte es sich jedes Recht selbst ausstellen. admin
# liegt ohnehin auf der Platte; gebraucht wird es hier nur auf ausdruecklichen
# Knopfdruck, und der steht hinter der PIN.
#
# Jedes Geraet bekommt eine EIGENE Wurzelkennung (root_key_id). Wird sie
# geloescht, sind die Macaroons dieses Geraets wertlos -- und nur diese.
# Die Sperre unten gegen alles unter fernzugang.ERSTE_KENNUNG ist keine
# Vorsicht aus Gewohnheit: an Kennung 0 haengen admin, readonly, invoice und
# das Macaroon der Anwendung. Sie zu loeschen sperrte die Anwendung aus
# ihrem eigenen Knoten aus.

def _geraetekennung(kennung: int) -> int:
    if not isinstance(kennung, int) or kennung < fernzugang.ERSTE_KENNUNG:
        raise ValueError(f"keine Geraetekennung: {kennung!r}")
    return kennung


def geraeteschluessel_kennungen(knoten: Knoten) -> List[int]:
    """Alle Wurzelkennungen, die LND kennt -- auch fremde."""
    antwort = knoten.ruf("/v1/macaroon/ids", macaroon="admin") or {}
    return [int(k) for k in antwort.get("root_key_ids") or []]


def geraeteschluessel_backen(knoten: Knoten,
                             rechte: Sequence[Tuple[str, str]],
                             kennung: int) -> str:
    """Ein Macaroon fuer ein Geraet, auf eigener Wurzel. Gibt es als Hex."""
    antwort = knoten.ruf("/v1/macaroon", macaroon="admin", daten={
        "permissions": [{"entity": e, "action": a} for e, a in rechte],
        # uint64 geht ueber REST als Zeichenkette (proto3 JSON).
        "root_key_id": str(_geraetekennung(kennung)),
    }) or {}
    hexwert = antwort.get("macaroon") or ""
    if not hexwert:
        raise LndFehler("LND hat kein Macaroon zurueckgegeben")
    return hexwert


def geraeteschluessel_widerrufen(knoten: Knoten, kennung: int) -> bool:
    """Die Wurzel eines Geraets loeschen. Danach ist sein Schluessel wertlos.

    Gibt zurueck, ob LND etwas geloescht hat. False heisst: die Wurzel gab es
    nicht (mehr) -- der Schluessel war also ohnehin schon ungueltig.
    """
    antwort = knoten.ruf(f"/v1/macaroon/{_geraetekennung(kennung)}",
                         macaroon="admin", methode="DELETE") or {}
    return bool(antwort.get("deleted"))


# Welche Adressformen LND erzeugen kann, und wie sie hier heissen.
#
# Taproot ist die guenstigste Ausgabe und macht einen daraus finanzierten
# Kanal billiger -- deshalb die Vorgabe. Sie war bis zum 09.09.2026 aber die
# EINZIGE, fest im Aufrufweg verdrahtet. Manche Boersen koennen bis heute
# nicht an bc1p senden; wer an so eine geriet, stand vor einer Wand, und die
# Anwendung bot keinen Ausweg, obwohl LND die beiden anderen Formen laengst
# kann.
#
# Je Form zwei Spielarten. Der Unterschied ist der Punkt:
#   TAPROOT_PUBKEY          erzeugt jedes Mal eine NEUE Adresse
#   UNUSED_TAPROOT_PUBKEY   gibt die aktuelle unbenutzte zurueck und rueckt
#                           erst weiter, wenn jemand darauf gezahlt hat
#
# Zum Anzeigen gehoert die zweite: sonst verbraucht schon das blosse
# Oeffnen der Seite eine Adresse, die Wallet fuellt sich mit ungenutzten,
# und die Zeile auf dem Bildschirm springt bei jedem Blick. Frisch je
# Zahlung bleibt sie trotzdem -- und genau darum geht es beim Datenschutz.
ADRESSARTEN = {
    "taproot":    ("TAPROOT_PUBKEY", "UNUSED_TAPROOT_PUBKEY"),
    "segwit":     ("WITNESS_PUBKEY_HASH", "UNUSED_WITNESS_PUBKEY_HASH"),
    "kompatibel": ("NESTED_PUBKEY_HASH", "UNUSED_NESTED_PUBKEY_HASH"),
}
ADRESSART_VORGABE = "taproot"


def einzahladresse(knoten: Knoten, art: str = ADRESSART_VORGABE,
                   neu: bool = False) -> str:
    """Eine Adresse fuer die On-Chain-Wallet.

    Ohne `neu` die aktuelle unbenutzte -- bestaendig auf dem Schirm, und
    trotzdem frisch je Zahlung. Eine wiederbenutzte Adresse verknuepft
    Einzahlungen miteinander und macht sie fuer jeden nachvollziehbar, der
    die Kette liest; genau das verhindern die UNUSED_-Spielarten, ohne bei
    jedem Seitenaufruf eine zu verbrauchen.
    """
    if art not in ADRESSARTEN:
        raise ValueError(f"unbekannte Adressart: {art}")
    erzeugend, bestaendig = ADRESSARTEN[art]
    typ = erzeugend if neu else bestaendig
    d = knoten.ruf(f"/v1/newaddress?type={typ}",
                   macaroon=EIGENES_MACAROON) or {}
    return d.get("address", "")


def pruefe_unterschrift(knoten: Knoten, text: str,
                        unterschrift: str) -> Dict[str, Any]:
    """Die eigene Unterschrift nachrechnen lassen.

    Bis zum 09.09.2026 konnte diese Anwendung unterschreiben und ihre eigene
    Unterschrift NICHT nachpruefen -- message:read fehlte um genau eine
    Zeile. Man sah, DASS etwas herauskam und dass es die richtige Form
    hatte (104 Zeichen zbase32), nicht aber, dass es rechnerisch stimmt.

    Die Kodierung ist dieselbe wie beim Unterschreiben: der Text base64, die
    Unterschrift in zbase32. Wer das verwechselt, bekommt von LND ein
    schlichtes "ungueltig" und sucht an der falschen Stelle.

    Der zurueckgegebene Schluessel ist die eigentliche Probe: er MUSS der
    eigene Knotenschluessel sein. Steht dort ein anderer, stimmt etwas
    Grundsaetzliches nicht.
    """
    antwort = knoten.ruf("/v1/verifymessage", macaroon=EIGENES_MACAROON,
                         daten={
                             "msg": base64.b64encode(
                                 text.encode("utf-8")).decode(),
                             "signature": unterschrift,
                         }) or {}
    return {"gueltig": bool(antwort.get("valid")),
            "kennung": antwort.get("pubkey", "")}


# Unter dieser Grenze nimmt das Bitcoin-Netz eine Ausgabe nicht an: sie
# waere "Staub", also weniger wert als das, was ihr spaeteres Ausgeben
# kostet. Wer es trotzdem versucht, bekommt von LND eine Abfuhr, die niemand
# versteht -- also lieber hier abfangen und es sagen.
SENDEN_MIN_SAT = 546

# Wie viele Bestaetigungen eine Eingabe haben muss, bevor sie wieder
# ausgegeben werden darf. Eins heisst: sobald sie in einem Block steht.
# Unbestaetigtes mitauszugeben waere bequem und riskant -- verschwindet die
# Eingabe durch einen Ersatz (RBF), verschwindet auch die eigene Zahlung.
SENDEN_MIN_CONFS = 1


def kosten_schaetzen(knoten: Knoten, adresse: str, betrag: int,
                     ziel_bloecke: int = 3) -> Dict[str, int]:
    """Was diese Zahlung an Gebuehr kostet -- BEVOR sie hinausgeht.

    LND rechnet das an der wirklichen Wallet: es sucht die Eingaben
    zusammen, die es nehmen wuerde, und daraus faellt die Groesse und damit
    die Gebuehr ab. Eine Schaetzung "ueber den Daumen" waere hier wertlos,
    weil sie genau das nicht weiss -- wer viele kleine Eingaben hat, zahlt
    ein Vielfaches dessen, was ein Ueberschlag sagt.

    Der Aufruf bewegt nichts. Er ist die Antwort auf die einzige Frage, die
    man vor dem Druecken hat: was kostet das?
    """
    # GET, nicht POST. LNDs REST-Tabelle (lnrpc/lightning.yaml, v0.21.3-beta):
    #   lnrpc.Lightning.EstimateFee -> get: "/v1/transactions/fee"
    # Bis zum 15.09.2026 ging hier ein POST mit Rumpf hinaus, und LNDs
    # grpc-gateway antwortete "501: Method Not Allowed". Weil "Jetzt senden"
    # erst nach der Schaetzung aufgeht, liess sich am echten Knoten nie ein
    # Betrag senden -- gefunden bei dem ersten Rueckweg. Die Attrappe
    # hatte nur den Pfad verglichen, nicht die Methode.
    #
    # Die Map steht in der URL als AddrToAmount[<adresse>]=<betrag>
    # (grpc-gateway v2.16.0, runtime/query.go: valuesKeyRegexp und
    # populateMapField); Felder findet es ueber den Proto-Namen.
    anfrage = urllib.parse.urlencode({
        f"AddrToAmount[{adresse}]": str(int(betrag)),
        "target_conf": int(ziel_bloecke),
        "min_confs": SENDEN_MIN_CONFS,
        "spend_unconfirmed": "false",
    })
    d = knoten.ruf(f"/v1/transactions/fee?{anfrage}",
                   macaroon=EIGENES_MACAROON) or {}
    return {
        "gebuehr_sat": _zahl(d.get("fee_sat")),
        "satz_sat_vb": _zahl(d.get("sat_per_vbyte")),
    }


def sende(knoten: Knoten, adresse: str, betrag: int, satz_sat_vb: int,
          alles: bool = False) -> str:
    """On-Chain senden. Gibt die Transaktionsnummer zurueck.

    UNWIEDERBRINGLICH, und deshalb steht hier nichts Bequemes: kein
    stillschweigendes Aufrunden, kein Wiederholen bei Zeitueberschreitung.
    Ein zweiter Versuch nach einem Zeitlimit koennte dieselbe Zahlung ein
    zweites Mal ausloesen -- die erste ist womoeglich laengst unterwegs, nur
    die Antwort blieb aus. Wer hier etwas wiederholt, muss vorher in die
    Kette sehen.

    `alles` raeumt die On-Chain-Wallet leer. Dann darf KEIN Betrag
    danebenstehen: LND lehnt beides zusammen ab, und zwar zu Recht -- was
    von zweien gaelte, waere geraten.
    """
    daten: Dict[str, Any] = {
        "addr": adresse,
        "sat_per_vbyte": str(int(satz_sat_vb)),
        "min_confs": SENDEN_MIN_CONFS,
        "spend_unconfirmed": False,
    }
    if alles:
        daten["send_all"] = True
    else:
        daten["amount"] = str(int(betrag))
    d = knoten.ruf("/v1/transactions", macaroon=EIGENES_MACAROON,
                   daten=daten) or {}
    return d.get("txid", "")


def _kurz(kennung: str) -> str:
    """Eine Knotenkennung fuers Auge: Anfang und Ende, Punkte dazwischen.

    Sechsundsechzig Zeichen sagen niemandem etwas, und nebeneinander sehen
    zwei verschiedene Kennungen gleich aus. Wer die volle braucht, findet
    sie im Graphen.
    """
    k = (kennung or "").strip()
    return k if len(k) <= 16 else f"{k[:8]}…{k[-4:]}"


# Wieviele Paare hoechstens einzeln genannt werden. Der Rest steckt in den
# Zaehlern darueber: ein Knoten mit Verkehr sammelt tausende, und die
# gehoeren nicht in einen Browser.
WEGWISSEN_HOECHSTENS = 25


def wegwissen(knoten: Knoten,
              hoechstens: int = WEGWISSEN_HOECHSTENS) -> Dict[str, Any]:
    """Was LND ueber Wege gelernt hat -- Mission Control.

    LND merkt sich je Gegenstellenpaar, wann zuletzt eine Weiterleitung
    versagte und bis zu welchem Betrag eine getragen hat. Genau danach
    waehlt es spaeter Routen aus; ein Knoten, der dort leer steht, wird
    gemieden. Der urspruengliche Plan nennt das "den eigentlichen Engpass".

    Der Nutzen sind nicht die Paare, sondern die zwei Betraege je Paar:
    "trug bis X" und "versagte ab Y". Liegt Y knapp ueber X, ist der Weg
    nicht kaputt, sondern LEER -- das ist eine Liquiditaetsfrage und keine
    Stoerung, und sie ist behebbar.

    Zusammengefasst wird hier, nicht im Browser: die Antwort kann tausende
    Paare enthalten.
    """
    d = knoten.ruf("/v2/router/mc", macaroon=EIGENES_MACAROON) or {}
    paare = d.get("pairs") or []
    eintraege = []
    mit_fehl = mit_erfolg = 0
    for p in paare:
        if not isinstance(p, dict):
            continue
        h = p.get("history") or {}
        fehl_zeit = _mit_vorzeichen(h.get("fail_time"))
        erfolg_zeit = _mit_vorzeichen(h.get("success_time"))
        if fehl_zeit > 0:
            mit_fehl += 1
        if erfolg_zeit > 0:
            mit_erfolg += 1
        eintraege.append({
            # Gekuerzt: die volle Kennung hat 66 Zeichen und sagt dem Auge
            # nichts. Wer sie ganz braucht, sucht im Graphen.
            "von": _kurz(str(p.get("node_from") or "")),
            "nach": _kurz(str(p.get("node_to") or "")),
            "zeitpunkt": max(fehl_zeit, erfolg_zeit),
            "fehl_ab_sat": _mit_vorzeichen(h.get("fail_amt_sat")),
            "trug_bis_sat": _mit_vorzeichen(h.get("success_amt_sat")),
        })
    eintraege.sort(key=lambda e: -e["zeitpunkt"])
    return {
        "paare": len(eintraege),
        "mit_fehlschlag": mit_fehl,
        "mit_erfolg": mit_erfolg,
        "letzte": eintraege[:max(1, int(hoechstens))] if eintraege else [],
    }


def gebuehr_erhoehen(knoten: Knoten, txid: str, ausgang: int,
                     satz_sat_vb: int, hoechstens_sat: int) -> Dict[str, Any]:
    """Die Gebuehr einer noch unbestaetigten Ueberweisung nachbessern.

    WAS HIER WIRKLICH PASSIERT -- und das gehoert verstanden, bevor man
    darauf klickt: LND haengt eine KIND-Transaktion an unser Wechselgeld
    (Child Pays For Parent). Die alte Transaktion verschwindet nicht; sie
    wird zusammen mit dem Kind attraktiver, weil ein Miner beide nur
    gemeinsam nehmen kann. Es entsteht also eine ZWEITE Transaktion, und die
    kostet zusaetzlich.

    Deshalb braucht es einen Ausgang, der uns gehoert. Wurde alles
    verschickt, gibt es keinen -- dann geht es nicht, und das sagen wir,
    statt es zu versuchen und an LNDs Abfuhr zu scheitern.

    Die Obergrenze ist PFLICHT und hat keinen Vorgabewert. Ohne sie nimmt
    LND, was es fuer noetig haelt (laut eigener Beschreibung bis zur Haelfte
    des Ausgangs) -- dieselbe Entscheidung wie bei der Gebuehrengrenze einer
    Lightning-Zahlung, aus demselben Grund: wer eine Gebuehr auslost, soll
    vorher wissen, wie hoch sie hoechstens wird.

    Die Feldnamen stammen aus LNDs eigener Beschreibung des gepinnten Tags
    (walletkit.swagger.json, v0.21.3-beta), nicht aus dem Gedaechtnis.
    """
    if int(hoechstens_sat) <= 0:
        raise ValueError("ohne Obergrenze wird keine Gebuehr erhoeht")
    return knoten.ruf("/v2/wallet/bumpfee", macaroon=EIGENES_MACAROON, daten={
        "outpoint": {"txid_str": str(txid), "output_index": int(ausgang)},
        "sat_per_vbyte": str(int(satz_sat_vb)),
        # Sofort anstossen statt auf den naechsten Block zu warten -- wer
        # hier klickt, wartet ohnehin schon.
        "immediate": True,
        "budget": str(int(hoechstens_sat)),
    }) or {}


def loesche_wallet(verzeichnis: Path) -> None:
    """Alles unterhalb des Wallet-Verzeichnisses entfernen.

    Aus dem Betrieb, 09.09.2026: "mach es dann moeglich ein wallet zu loeschen mit
    dem wallet passwort zum entsperren ... dann kann ich die ganze
    initialisierung nochmal machen und testen."

    Weg sind damit: die Wallet selbst, die Kanal-Datenbank, die Macaroons,
    das TLS-Zertifikat und der Schluessel des Onion-Dienstes. LND faengt
    danach bei NON_EXISTING an -- und der Knoten bekommt eine NEUE
    Onion-Adresse, weil der alte Schluessel mit weg ist.

    DER EINHAENGEPUNKT SELBST BLEIBT. Ihn zu entfernen hiesse, in ein
    Docker-Volume hineinzuloeschen, das uns nicht gehoert.

    Symlinks werden geloescht, aber NICHT verfolgt: ein Verweis, der aus
    diesem Verzeichnis hinausfuehrt, darf nicht dazu fuehren, dass draussen
    etwas verschwindet.
    """
    if not verzeichnis.is_dir():
        return                      # zweimal geloescht ist kein Fehler
    for eintrag in verzeichnis.iterdir():
        if eintrag.is_symlink() or eintrag.is_file():
            eintrag.unlink(missing_ok=True)
        elif eintrag.is_dir():
            shutil.rmtree(eintrag)


def verbinde(knoten: Knoten, zeile: str) -> None:
    """Sich mit einer Gegenstelle verbinden -- ohne Kanal, ohne Geld.

    Befund 20 vom 09.09.2026: das Recht peers:write stand seit jeher in
    EIGENE_RECHTE, mit dem Kommentar "sich mit einer Gegenstelle verbinden"
    -- und ConnectPeer war nirgends implementiert. Wir trugen ein Recht
    spazieren, das wir nie benutzten. Das ist doppelt schlecht: die Funktion
    fehlte, und die Linie dieses Projekts lautet, nur zu halten, was
    gebraucht wird.

    Was das bewirkt: eine Netzverbindung zur Gegenstelle, sonst nichts. Kein
    Kanal, kein Satoshi. Es ist die Vorstufe -- fuer einen Kanal muss danach
    jemand einen oeffnen, und das geht seit dem 12.09.2026 nur hinter der PIN.

    Erwartet wird die uebliche Zeile aus dem Graphen:
        02abc...def@xyz.onion:9735
    """
    sauber = (zeile or "").strip()
    if any(z in sauber for z in "\r\n") or any(ord(z) < 32 for z in sauber):
        raise LndFehler("In der Adresse stehen Steuerzeichen.")
    kennung, trenner, wirt = sauber.partition("@")
    if not (trenner and kennung and wirt):
        raise LndFehler(
            "Erwartet wird Kennung@Adresse:Port, so wie im Graphen.")
    knoten.ruf("/v1/peers", macaroon=EIGENES_MACAROON, daten={
        "addr": {"pubkey": kennung, "host": wirt},
        # NICHT dauerhaft. perm=true liesse LND ewig nachverbinden, auch zu
        # einer Gegenstelle, die jemand einmal versehentlich eingetippt hat.
        # Verbindungen, an denen ein Kanal haengt, haelt LND ohnehin selbst.
        "perm": False,
    })


# So viele angekuendigte Adressen einer Gegenstelle werden hoechstens
# durchprobiert. Ein Knoten darf beliebig viele ankuendigen; jede kostet im
# schlechtesten Fall ein volles Verbindungs-Zeitlimit.
VERBINDUNGSVERSUCHE = 3


def _adressen_aus_graph(knoten: Knoten, kennung: str) -> List[str]:
    """Wo das NETZ sagt, dass diese Gegenstelle zu erreichen ist.

    Aus dem eigenen Graphen, nicht von einer fremden Stelle -- dieselbe
    Quelle, aus der auch "Gegenstelle ansehen" liest.
    """
    try:
        d = knoten.ruf(f"/v1/graph/node/{kennung}",
                       macaroon=EIGENES_MACAROON) or {}
    except LndFehler as fehler:
        log.info("Keine Adresse fuer %s im Graphen: %s", kennung[:12], fehler)
        return []
    eintrag = d.get("node") or {}
    return [a.get("addr", "") for a in (eintrag.get("addresses") or [])
            if a.get("addr")]


def verbinde_gegenstelle(knoten: Knoten, zeile: str) -> str:
    """Verbinden -- mit angegebener Adresse ODER mit der aus dem Graphen.

    DIE KANTE, DIE HIER WEGFAELLT. Bis zum 19.09.2026 nahm dasselbe
    Eingabefeld zwei Formen an und verhielt sich verschieden:

        02abc...@host:9735   -> verbunden, Kanal geoeffnet
        02abc...             -> NICHT verbunden, und LND lehnte den Kanal ab

    Die Pruefung liess beide Formen klaglos durch. Wer eine Kennung aus einem
    Explorer kopierte -- dort steht sie meist ohne Adresse -- bekam einen
    Fehler, den nichts erklaerte. Aus dem Betrieb, 19.09.2026: "ich wuesste jetzt
    nicht wie ich mich mit einem anderen knoten verbinden sollte".

    Jetzt ist es egal, welche Form ankommt: fehlt die Adresse, wird sie im
    eigenen Graphen nachgeschlagen. Der Knoten weiss sie ohnehin -- er hat
    die Ankuendigung mitgehoert.

    Gibt die Adresse zurueck, ueber die es geklappt hat. Leer heisst: es
    bestand schon eine Verbindung.
    """
    sauber = (zeile or "").strip()
    kennung, trenner, _wirt = sauber.partition("@")
    kennung = kennung.strip().lower()
    if len(kennung) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in kennung):
        raise LndFehler(
            "Das ist keine Knotenkennung -- erwartet werden 66 Hexzeichen.")

    if trenner:
        kandidaten = [sauber]
    else:
        adressen = _adressen_aus_graph(knoten, kennung)
        if not adressen:
            raise LndFehler(
                "Zu dieser Kennung kennt dein Graph keine Adresse. Gib sie "
                "als Kennung@Adresse:Port an -- oder der Knoten hat noch nie "
                "eine angekuendigt.")
        kandidaten = [f"{kennung}@{a}"
                      for a in adressen[:VERBINDUNGSVERSUCHE]]

    letzter: Optional[LndFehler] = None
    for kandidat in kandidaten:
        try:
            verbinde(knoten, kandidat)
            return kandidat.partition("@")[2]
        except LndFehler as fehler:
            # Schon verbunden ist kein Fehler, sondern der Normalfall bei
            # einer Gegenstelle, mit der man bereits Kanaele hat.
            if "already connected" in str(fehler).lower():
                return ""
            letzter = fehler
    raise letzter or LndFehler("Verbindung nicht zustande gekommen.")


# ── Einen Kanal oeffnen ────────────────────────────────────────────────────
#
# Aus dem Betrieb, 12.09.2026, nach der Bestandsaufnahme: "ja dann machen wir mal mit
# Punkt 1 und 2 weiter" -- Kanal oeffnen und Lightning zahlen.
#
# Bis hierher stand in der README: "No endpoint opens or closes a channel yet.
# When one appears, it belongs behind the same PIN." Der Satz gilt weiter, er
# hat jetzt nur einen Endpunkt hinter sich. Das Recht dafuer (onchain:write)
# liegt seit dem 10.09.2026 ohnehin im Macaroon -- LND haengt SendCoins und
# OpenChannel an dieselbe Berechtigung und trennt sie nicht.

# LNDs eigene Untergrenze fuer einen Kanal (funding.MinChanFundingSize).
# Darunter lehnt es selbst ab; wir fangen es vorher ab, um einen lesbaren
# Satz zu geben statt einer gRPC-Meldung.
KANAL_MIN_SAT = 20_000

# Ab wo ein Kanal nicht mehr KNAPP ist -- und das ist keine Geschmacksfrage.
#
# Nachgelesen bei lightningnode.info am 12.09.2026, weil der Betreiber ausdruecklich
# danach gefragt hat ("ist das alles nochmal validiert gegen unsere lndinfo
# quelle?"). Die Seite nennt 200K-500K sat und begruendet es mit einem Risiko,
# das nichts mit Wirtschaftlichkeit zu tun hat:
#
#   "A channel too small will result in being unable to close when on-chain
#    fees are high. This will leave the channel vulnerable in a case, when the
#    counterparty would try to close with a previous state (the funds in the
#    channel can be cheated out)."
#
# Also: steigen die Ketten-Gebuehren, kostet das Schliessen mehr, als der
# Kanal wert ist. Wer dann nicht schliessen KANN, kann auch einen Betrugs-
# versuch der Gegenstelle nicht mehr bestrafen -- und genau davon lebt die
# Sicherheit eines Kanals.
#
# Deshalb ist das hier kein Riegel, sondern eine Warnung mit Begruendung: die
# Entscheidung gehoert dem Betreiber. LNDs eigene Untergrenze bleibt 20.000.
KANAL_RATSAM_SAT = 200_000
# Eine Kennung ist ein komprimierter Punkt: 33 Byte, 66 Hexzeichen.
KENNUNG_ZEICHEN = 66


def _txid_lesbar(roh: str) -> str:
    """Aus LNDs funding_txid_bytes die Kennung, die ein Mensch wiedererkennt.

    DIE FALLE: die Bytes stehen in interner Reihenfolge, also rueckwaerts zu
    dem, was jeder Explorer anzeigt. Wer sie einfach in Hex wandelt, bekommt
    eine Kennung, die es nirgends gibt -- und sucht dann seine Transaktion in
    einem Explorer, der sie nicht kennt.
    """
    try:
        return bytes(reversed(base64.b64decode(roh))).hex()
    except (ValueError, TypeError):
        return ""


def kanal_oeffnen(knoten: Knoten, zeile: str, betrag_sat: int,
                  satz_sat_vb: int, privat: bool = False) -> Dict[str, Any]:
    """Einen Kanal zu einer Gegenstelle oeffnen.

    Zwei Schritte, und der erste wird gern vergessen: LND oeffnet nur zu
    jemandem, mit dem es GERADE verbunden ist. Also erst verbinden, dann
    oeffnen -- eine bestehende Verbindung stoert dabei nicht.

    Genommen wird OpenChannelSync (/v1/channels), nicht der Strom: uns
    interessiert die Finanzierungstransaktion, und die steht sofort fest. Was
    danach kommt -- Bestaetigungen abwarten, Kanal wird aktiv -- sieht man
    ohnehin in der Kanalliste.
    """
    kennung, _trenner, _wirt = (zeile or "").strip().partition("@")
    kennung = kennung.strip().lower()
    if len(kennung) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in kennung):
        raise LndFehler(
            "Das ist keine Knotenkennung -- erwartet werden 66 Hexzeichen.")
    if betrag_sat < KANAL_MIN_SAT:
        raise LndFehler(
            f"Ein Kanal braucht mindestens {KANAL_MIN_SAT} sat.")
    if satz_sat_vb < 1:
        raise LndFehler("Die Gebuehr muss mindestens 1 sat/vB sein.")

    # Erst verbinden -- ueber die angegebene Adresse oder ueber die aus dem
    # eigenen Graphen. Eine bestehende Verbindung stoert dabei nicht.
    verbinde_gegenstelle(knoten, zeile)

    antwort = knoten.ruf("/v1/channels", macaroon=EIGENES_MACAROON, daten={
        # REST nimmt die Kennung als base64 der rohen Bytes.
        "node_pubkey": base64.b64encode(bytes.fromhex(kennung)).decode(),
        "local_funding_amount": str(int(betrag_sat)),
        "sat_per_vbyte": str(int(satz_sat_vb)),
        # Ein oeffentlicher Kanal erscheint im Graphen -- genau darum geht es
        # bei einem Knoten, der teilnehmen soll. Privat ist die Ausnahme.
        "private": bool(privat),
        # Kein Geld an die Gegenstelle verschenken. push_sat waere ein
        # Geschenk ohne Gegenleistung, und niemand erwartet es.
        "push_sat": "0",
        # Nur bestaetigte Mittel. Unbestaetigte koennten noch verschwinden,
        # und ein Kanal auf einer verschwundenen Ausgabe ist ein Problem,
        # das man erst Stunden spaeter bemerkt.
        "min_confs": 1,
        "spend_unconfirmed": False,
    }, zeitlimit=60.0) or {}

    txid = _txid_lesbar(antwort.get("funding_txid_bytes") or "")
    return {
        "txid": txid or (antwort.get("funding_txid_str") or ""),
        "ausgang": _zahl(antwort.get("output_index")),
        "gegenstelle": kennung,
        "betrag": int(betrag_sat),
    }


# ── Die Gegenstelle ansehen, BEVOR ein Kanal steht ────────────────────────
#
# Aus dem Betrieb, 12.09.2026: "gibt es uns die moeglichkeit einen channel den wir
# verknuepfen wollen vorher zu scannen und zu warnen ob das sinn macht??"
#
# Ja -- und die Auskunft kommt aus dem EIGENEN Graphen, nicht von einer
# fremden Seite. Jeder Knoten kuendigt sich per node_announcement selbst an;
# unser Knoten hat das laengst mitgehoert.
#
# Was hier NICHT entsteht, ist eine Note oder ein Vertrauenswert. Das waere
# erfundene Genauigkeit. Es sind Tatsachen, und drei davon sagen wirklich
# etwas.

# Ab wann ein Knoten als STILL gilt. LND kuendigt sich im Normalbetrieb
# regelmaessig neu an; wer seit Wochen schweigt, ist meist weg -- und eine
# Gegenstelle, die verschwindet, ist der teuerste Fall von allen: kein
# einvernehmliches Schliessen, also erzwingen, also Gebuehren und Wartezeit.
STILL_AB_TAGEN = 14
# Unter so wenigen Kanaelen ist ein Knoten kaum eingebunden -- ueber ihn
# fuehrt dann fast kein Weg ins restliche Netz.
WENIG_KANAELE = 5


def gegenstelle_ansehen(knoten: Knoten, zeile: str,
                        jetzt: Optional[float] = None) -> Dict[str, Any]:
    """Was der eigene Graph ueber diese Gegenstelle weiss."""
    jetzt = time.time() if jetzt is None else jetzt
    kennung, _trenner, _wirt = (zeile or "").strip().partition("@")
    kennung = kennung.strip().lower()
    if len(kennung) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in kennung):
        raise LndFehler(
            "Das ist keine Knotenkennung -- erwartet werden 66 Hexzeichen.")

    try:
        d = knoten.ruf(f"/v1/graph/node/{kennung}",
                       macaroon=EIGENES_MACAROON) or {}
    except LndFehler as fehler:
        # "unable to find node" heisst: in UNSEREM Graphen steht er nicht.
        # Das ist eine Auskunft und kein Fehler -- und eine wichtige.
        log.info("Gegenstelle %s nicht im Graphen: %s", kennung[:12], fehler)
        return {"kennung": kennung, "bekannt": False}

    eintrag = d.get("node") or {}
    gemeldet = _zahl(eintrag.get("last_update"))
    adressen = [a.get("addr", "") for a in (eintrag.get("addresses") or [])
                if a.get("addr")]
    tage = int((jetzt - gemeldet) / 86400) if gemeldet else None
    kanaele = _zahl(d.get("num_channels"))
    return {
        "kennung": kennung,
        "bekannt": True,
        "alias": eintrag.get("alias", ""),
        "kanaele": kanaele,
        "kapazitaet": _zahl(d.get("total_capacity")),
        "adressen": adressen,
        "still_seit_tagen": tage,
        # Die drei Befunde, die wirklich etwas heissen. Bewusst einzeln und
        # benannt statt zu einer Note verrechnet: wer einen davon hinnehmen
        # will, soll wissen, welchen.
        "still": tage is not None and tage >= STILL_AB_TAGEN,
        "wenig_verbunden": kanaele < WENIG_KANAELE,
        "ohne_adresse": not adressen,
        "nur_tor": bool(adressen) and all(
            ".onion" in a.lower() for a in adressen),
    }


# ── Wachtuerme ─────────────────────────────────────────────────────────────
#
# Aus dem Betrieb, 12.09.2026: "ich will wenn es um unser geld geht immer 100%!!"
#
# Der Befund, der dazu gefuehrt hat: in der Konfiguration stand
# wtclient.active=true -- "meine Kanaele sollen bewacht werden". Das schaltet
# aber nur den CLIENT ein. Eingetragen war kein einziger Turm, also bewachte
# niemand etwas. Die Konfiguration sah aus, als waere der Schutz da.
#
# Wofuer er da ist: veroeffentlicht eine Gegenstelle einen ALTEN Kanalzustand,
# muss das innerhalb der Zeitsperre bestraft werden. Laeuft der eigene Knoten
# gerade -- Stromausfall, Update, Plattenschaden --, merkt es niemand. Genau
# dafuer gibt es einen fremden Turm, der nur den Strafzug kennt und sonst
# nichts: er kann mit dem, was er bekommt, kein Geld bewegen.


# Welche Sitzungsart ein Kanal beim Turm braucht. So entscheidet LND selbst
# (watchtower/blob/type.go, TypeFromChannel): Taproot vor Anker vor allem
# anderen. Links die Namen aus lightning.proto, so wie REST sie schickt.
_SITZUNGSART_JE_KANALART = {
    "TAPROOT": "TAPROOT",
    "SIMPLE_TAPROOT_FINAL": "TAPROOT",
    "SIMPLE_TAPROOT": "TAPROOT",
    "SIMPLE_TAPROOT_OVERLAY": "TAPROOT",
    "ANCHORS": "ANCHOR",
    "SCRIPT_ENFORCED_LEASE": "ANCHOR",
}
# PolicyType aus wtclient.proto, in der Reihenfolge seiner Nummern. REST
# schickt den Namen; die Nummer wird trotzdem verstanden.
_SITZUNGSARTEN = ("LEGACY", "ANCHOR", "TAPROOT")
# Neue Kanaele oeffnet diese Anwendung ohne commitment_type, und dann
# handelt LND Anker-Kanaele aus. Solange es keinen Kanal gibt, ist das die
# Art, auf die es ankommt.
SITZUNGSART_NEUER_KANAELE = "ANCHOR"


def sitzungsart(kanalart: Any) -> str:
    """Die Sitzungsart, die ein Kanal dieser Art beim Turm braucht."""
    return _SITZUNGSART_JE_KANALART.get(str(kanalart or "").upper(), "LEGACY")


def _sitzungsart_name(wert: Any) -> str:
    if isinstance(wert, int) and 0 <= wert < len(_SITZUNGSARTEN):
        return _SITZUNGSARTEN[wert]
    name = str(wert or "").upper()
    return name if name in _SITZUNGSARTEN else "LEGACY"


def _kennung_als_hex(wert: str) -> str:
    """REST schickt Schluessel als base64 der rohen 33 Bytes."""
    try:
        roh = base64.b64decode(wert or "", validate=True)
    except ValueError:
        return wert or ""
    return roh.hex() if len(roh) == 33 else (wert or "")


def wachtuerme(knoten: Knoten,
               eigene_kennung: str = "") -> List[Dict[str, Any]]:
    """Welche Tuerme unsere Kanaele bewachen -- und ob sie es wirklich tun.

    "eigene_kennung" ist der Schluessel UNSERES eigenen Turms. Ein Turm, der
    auf derselben Maschine laeuft, wird damit als solcher gekennzeichnet --
    siehe ungedeckte_arten, wo er nicht als Schutz zaehlen darf.

    BIS ZUM 14.09.2026 STAND HIER BEI JEDEM TURM "0 SITZUNGEN". Gezaehlt
    wurde die Liste "sessions", und die schickt LND nur mit
    include_sessions=true (lnrpc/wtclientrpc/wtclient.go, marshallTower).
    Ohne das bleibt sie leer, egal wie es wirklich steht.

    Die Angaben stehen je Sitzungsart unter session_info. LND fuehrt fuer
    jede Kanalart einen eigenen Client, und jeder handelt seine Sitzung mit
    genau EINEM Turm aus (session_negotiator.go: zurueck nach der ersten,
    die gelingt). Ein zweiter Turm ohne Sitzung ist deshalb Reserve, kein
    Ausfall.
    """
    d = knoten.ruf("/v2/watchtower/client?include_sessions=true",
                   macaroon=EIGENES_MACAROON) or {}
    raus = []
    for turm in d.get("towers") or []:
        arten: Dict[str, Dict[str, int]] = {}
        for info in turm.get("session_info") or []:
            art = arten.setdefault(_sitzungsart_name(info.get("policy_type")), {
                "sitzungen": 0, "nutzbar": 0, "bestaetigt": 0, "ausstehend": 0})
            for sitzung in info.get("sessions") or []:
                bestaetigt = int(sitzung.get("num_backups") or 0)
                ausstehend = int(sitzung.get("num_pending_backups") or 0)
                art["sitzungen"] += 1
                art["bestaetigt"] += bestaetigt
                art["ausstehend"] += ausstehend
                # Eine volle Sitzung nimmt keinen neuen Stand mehr an.
                if bestaetigt + ausstehend < int(sitzung.get("max_backups") or 0):
                    art["nutzbar"] += 1
        # AUSGETRAGEN heisst nicht verschwunden. LND fuehrt einen Turm, der
        # Sitzungen hatte, nach dem Austragen weiter in seiner Liste
        # (Manager.RegisteredTowers liest ohne Filter) -- nur nicht mehr als
        # Kandidaten. active_session_candidate ist genau das: steht der Turm
        # noch in der Kandidatenliste (candidate_iterator.go, IsActive)? Ohne
        # diese Unterscheidung zaehlten die alten Sitzungen eines
        # ausgetragenen Turms als Schutz.
        infos = turm.get("session_info") or []
        aktiv = (any(bool(i.get("active_session_candidate")) for i in infos)
                 if infos else bool(turm.get("active_session_candidate", True)))
        kennung = _kennung_als_hex(turm.get("pubkey", ""))
        raus.append({
            "kennung": kennung,
            "adressen": [a for a in (turm.get("addresses") or []) if a],
            "arten": arten,
            "sitzungen": sum(a["sitzungen"] for a in arten.values()),
            "aktiv": aktiv,
            "eigen": bool(eigene_kennung) and kennung == eigene_kennung,
        })
    return raus


def wachturm_zaehler(knoten: Knoten) -> Dict[str, int]:
    """Was die Tuerme angenommen haben -- seit dem letzten Start von LND.

    Die Zaehler liegen bei LND nur im Speicher (watchtower/wtclient/stats.go)
    und beginnen nach jedem Neustart bei null. Deshalb steht das so in der
    Oberflaeche: eine Null nach einem Update heisst nichts.
    """
    d = knoten.ruf("/v2/watchtower/client/stats",
                   macaroon=EIGENES_MACAROON) or {}
    return {
        "bestaetigt": int(d.get("num_backups") or 0),
        "ausstehend": int(d.get("num_pending_backups") or 0),
        "abgewiesen": int(d.get("num_failed_backups") or 0),
        "sitzungen_neu": int(d.get("num_sessions_acquired") or 0),
    }


def ungedeckte_arten(kanaele: List[Dict[str, Any]],
                     tuerme: List[Dict[str, Any]]) -> List[str]:
    """Fuer welche Kanalarten gerade KEIN Turm eine nutzbare Sitzung haelt.

    Eingetragen ist nicht bewacht: ein Turm, der nie erreichbar war, steht
    genauso in der Liste wie einer, der arbeitet. Ohne Kanal zaehlt die Art,
    die ein neuer Kanal bekaeme.

    DER EIGENE TURM ZAEHLT NICHT. Befund vom 17.09.2026 an dem Knoten im Betrieb:
    er hatte seinen eigenen Turm mit eingetragen, LND handelte mit ihm
    Sitzungen fuer alle drei Kanalarten aus, und die Oberflaeche meldete
    gruen "Bereit". Gedeckt war damit alles ausser dem einen Fall, fuer den
    es einen Wachturm ueberhaupt gibt: dass DIESER Knoten gerade nicht
    laeuft. Laeuft er nicht, laeuft der Turm auf derselben Maschine auch
    nicht -- gleiches Netzteil, gleicher Strom, gleiche Platte. Eine Anzeige,
    die das als Schutz fuehrt, ist schlimmer als gar keine.
    """
    noetig = {k.get("sitzungsart") or SITZUNGSART_NEUER_KANAELE
              for k in kanaele} or {SITZUNGSART_NEUER_KANAELE}
    gedeckt = {art for turm in tuerme
               if turm.get("aktiv", True) and not turm.get("eigen")
               for art, stand in (turm.get("arten") or {}).items()
               if stand.get("nutzbar")}
    return sorted(noetig - gedeckt)


def eigener_turm(knoten: Knoten) -> Dict[str, Any]:
    """Die Adresse, unter der UNSER Turm erreichbar ist.

    Ohne sie kann niemand diesen Turm eintragen -- und bis zum 12.09.2026
    stand sie nirgends in der Oberflaeche. Ein Dienst, dessen Adresse nur der
    Betreiber nicht kennt, ist ein seltsamer Dienst.

    Was NICHT dabei herauskommt, und zwar aus Prinzip: wie viele Kanaele
    dieser Turm bewacht. LNDs GetInfo des Wachturms liefert genau drei Felder
    -- Schluessel, Lauschadressen, URIs. Keine Kundenzahl, keine Sitzungen.
    Das ist kein Versaeumnis, sondern die Bauart: ein Turm bekommt
    verschluesselte Paeckchen, die er nicht oeffnen kann, bis die passende
    Transaktion in der Kette auftaucht. Er weiss selbst nicht, was er
    bewacht -- und genau das macht ihn vertrauenswuerdig.
    """
    d = knoten.ruf("/v2/watchtower/server", macaroon=EIGENES_MACAROON) or {}
    uris = [u for u in (d.get("uris") or []) if u]
    return {
        "aktiv": bool(d.get("pubkey")),
        # Die Kennung wird gebraucht, um unseren eigenen Turm in der Liste
        # der eingetragenen wiederzuerkennen -- er darf dort nicht als
        # Schutz zaehlen (ungedeckte_arten).
        "kennung": _kennung_als_hex(d.get("pubkey", "")),
        "uris": uris,
        "lauscht": [a for a in (d.get("listeners") or []) if a],
    }


def wachturm_eintragen(knoten: Knoten, zeile: str) -> str:
    """Einen Wachturm eintragen. Erwartet Kennung@Adresse:Port."""
    sauber = (zeile or "").strip()
    kennung, trenner, wirt = sauber.partition("@")
    kennung = kennung.strip().lower()
    if not (trenner and wirt.strip()):
        raise LndFehler(
            "Erwartet wird Kennung@Adresse:Port, so wie beim Kanal.")
    if len(kennung) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in kennung):
        raise LndFehler(
            "Das ist keine Knotenkennung -- erwartet werden 66 Hexzeichen.")
    knoten.ruf("/v2/watchtower/client", macaroon=EIGENES_MACAROON, daten={
        "pubkey": base64.b64encode(bytes.fromhex(kennung)).decode(),
        "address": wirt.strip(),
    })
    return kennung


def wachturm_entfernen(knoten: Knoten, kennung: str) -> str:
    """Einen Wachturm austragen. Erwartet seine Kennung (66 Hexzeichen).

    Damit die Liste nicht endlos waechst: oeffentliche Turmlisten sind voller
    Tuerme, die es laengst nicht mehr gibt.

    Was LND dabei tut (watchtower/wtclient/client.go, handleStaleTower): der
    Turm wird fuer neue Sitzungen und Sicherungen nicht mehr benutzt, seine
    Sitzungen werden beendet, und noch nicht bestaetigte Kanalstaende gehen
    zurueck in die Warteschlange -- sie landen beim naechsten Turm, nicht im
    Nichts. Hielt er die aktive Sitzung, handelt LND mit dem naechsten
    eingetragenen Turm eine neue aus. Wieder eintragen geht jederzeit.

    Der Schluessel steht als Bytes im PFAD. Gewoehnliches base64 enthaelt "/",
    und das zerbraeche die Adresse -- deshalb die URL-sichere Form, die LNDs
    REST-Schicht ebenfalls annimmt (grpc-gateway v2.16.0, runtime.Bytes).
    """
    sauber = (kennung or "").strip().lower()
    if len(sauber) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in sauber):
        raise LndFehler(
            "Das ist keine Knotenkennung -- erwartet werden 66 Hexzeichen.")
    schluessel = base64.urlsafe_b64encode(bytes.fromhex(sauber)).decode()
    knoten.ruf(f"/v2/watchtower/client/{schluessel}",
               macaroon=EIGENES_MACAROON, methode="DELETE")
    return sauber


# ── Eine Lightning-Rechnung lesen und bezahlen ─────────────────────────────
#
# Der zweite Teil von des Betreibers "Punkt 1 und 2". Bis hierher konnte diese
# Anwendung On-Chain senden -- also die langsame, teure Art. Ueber Lightning
# zu zahlen, wofuer der ganze Knoten da ist, konnte sie nicht.

# Wie lange eine Zahlung laufen darf. LND probiert in dieser Zeit mehrere
# Routen; laenger zu warten bringt selten etwas und blockiert nur die
# Oberflaeche.
ZAHLUNG_ZEITLIMIT_SEKUNDEN = 60
# Etwas Luft obendrauf, damit unser eigenes Warten nicht VOR LNDs Zeitlimit
# ablaeuft -- sonst saehe eine noch laufende Zahlung wie ein Fehler aus.
ZAHLUNG_LUFT_SEKUNDEN = 20.0

# Was eine Weiterleitung hoechstens kosten darf, wenn niemand etwas anderes
# sagt: ein Prozent, mindestens aber ein paar Sats. Der Netz-Median liegt bei
# rund 100 ppm, also einem Zehntel davon -- die Grenze ist Schutz vor
# Ausreissern, keine Zielvorgabe.
GEBUEHRGRENZE_ANTEIL = 0.01
GEBUEHRGRENZE_MIN_SAT = 5


def gebuehrgrenze(betrag_sat: int) -> int:
    """Die vorgeschlagene Obergrenze fuer die Weiterleitungsgebuehr."""
    return max(GEBUEHRGRENZE_MIN_SAT,
               int(round(int(betrag_sat) * GEBUEHRGRENZE_ANTEIL)))


def rechnung_lesen(knoten: Knoten, rechnung: str) -> Dict[str, Any]:
    """Was in einer Rechnung steht -- BEVOR jemand sie bezahlt.

    Der wichtigste Schritt am ganzen Vorgang. Eine Lightning-Rechnung ist eine
    unleserliche Zeichenkette; wer sie ohne Nachsehen bezahlt, weiss weder an
    wen noch wieviel. LND liest sie auf, ohne irgendetwas zu bewegen.

    Braucht offchain:read -- Lesen, mehr nicht.
    """
    sauber = (rechnung or "").strip()
    # Viele Wallets geben "lightning:lnbc..." heraus.
    if sauber.lower().startswith("lightning:"):
        sauber = sauber[len("lightning:"):]
    if not sauber or any(z in sauber for z in " \r\n\t/?#"):
        raise LndFehler("Das sieht nicht nach einer Lightning-Rechnung aus.")

    d = knoten.ruf("/v1/payreq/" + urllib.parse.quote(sauber, safe="")) or {}
    betrag = _zahl(d.get("num_satoshis"))
    erstellt = _zahl(d.get("timestamp"))
    gueltig = _zahl(d.get("expiry"))
    return {
        "rechnung": sauber,
        "ziel": d.get("destination", ""),
        "betrag": betrag,
        # Eine Rechnung OHNE Betrag ist zulaessig -- dann bestimmt ihn der
        # Zahlende. Das gehoert gesagt, sonst steht dort "0 sat" und sieht
        # aus wie umsonst.
        "offener_betrag": betrag == 0,
        "zweck": (d.get("description") or "")[:300],
        "erstellt": erstellt,
        "laeuft_ab": erstellt + gueltig if erstellt and gueltig else 0,
        "kennung": d.get("payment_hash", ""),
    }


def zahle(knoten: Knoten, rechnung: str, gebuehrengrenze_sat: int,
          betrag_sat: int = 0) -> Dict[str, Any]:
    """Eine Lightning-Rechnung bezahlen.

    Ueber den STROM, nicht ueber einen einzelnen Aufruf: LND meldet waehrend
    des Versuchs mehrfach, und erst die letzte Meldung sagt, wie es ausging.
    Wer nur die erste liest, haelt jede Zahlung fuer "unterwegs".

    Die Gebuehrengrenze ist Pflicht und hat keinen Vorgabewert hier: ohne sie
    nimmt LND, was die Route kostet, und das kann bei einer schlechten Route
    ein Vielfaches des Betrags sein. Sie gehoert vom Aufrufer gesetzt, der
    sie dem Menschen auch gezeigt hat.
    """
    daten: Dict[str, Any] = {
        "payment_request": (rechnung or "").strip(),
        "timeout_seconds": ZAHLUNG_ZEITLIMIT_SEKUNDEN,
        "fee_limit_sat": str(int(gebuehrengrenze_sat)),
        # Sich selbst zu bezahlen ist kein sinnvoller Vorgang und ein
        # beliebter Weg, Kanaele umzuschichten. Nicht ueber diesen Endpunkt.
        "allow_self_payment": False,
    }
    # Nur bei einer Rechnung ohne Betrag -- sonst widerspraeche die Angabe
    # der Rechnung, und LND lehnt ab.
    if betrag_sat:
        daten["amt"] = str(int(betrag_sat))

    letzte: Dict[str, Any] = {}
    for meldung in knoten.strom(
            "/v2/router/send", daten, macaroon=EIGENES_MACAROON,
            zeitlimit=ZAHLUNG_ZEITLIMIT_SEKUNDEN + ZAHLUNG_LUFT_SEKUNDEN):
        if meldung.get("error"):
            raise LndFehler(str(meldung["error"]))
        ergebnis = meldung.get("result") or {}
        if ergebnis:
            letzte = ergebnis
        if ergebnis.get("status") in ("SUCCEEDED", "FAILED"):
            break

    stand = letzte.get("status") or "UNBEKANNT"
    if stand != "SUCCEEDED":
        # Der Grund ist die eigentliche Auskunft. "Zahlung fehlgeschlagen"
        # allein sagt niemandem, ob er es gleich noch einmal versuchen soll.
        raise LndFehler(letzte.get("failure_reason") or stand)
    return {
        "kennung": letzte.get("payment_hash", ""),
        "betrag": _zahl(letzte.get("value_sat")),
        "gebuehr": _zahl(letzte.get("fee_sat")),
        "beleg": letzte.get("payment_preimage", ""),
    }


# ── Zwischen eigenen Kanaelen umschichten ──────────────────────────────────
#
# Aus dem Betrieb, 12.09.2026: "kann ich dann mehre kanäle balancen??"
#
# Ja -- und der Mechanismus ist derselbe, den ich beim Zahlen ausdruecklich
# gesperrt habe: eine Zahlung AN SICH SELBST. Raus durch den einen Kanal,
# zurueck herein ueber den anderen. Danach liegt Liquiditaet dort, wo sie
# gebraucht wird.
#
# Warum das trotzdem ein EIGENER Weg ist und kein Haken am Zahlknopf: beim
# Bezahlen einer fremden Rechnung ist Selbstzahlung ein Unfall und gehoert
# verhindert. Beim Umschichten ist sie der Zweck. Zwei verschiedene Vorgaenge,
# zwei verschiedene Knoepfe -- und nur einer davon hat allow_self_payment an.
#
# Was es kostet: nur die Weiterleitungsgebuehr des Rundwegs. Das Geld bleibt
# die ganze Zeit deins; es wechselt nur die Seite. Ein Rundweg, der mehr
# kostet als er bringt, ist trotzdem verlorenes Geld -- deshalb ist die
# Gebuehrengrenze auch hier Pflicht.

UMSCHICHTEN_ZWECK = "satcortex: umschichten"


# ── Empfangen: eine Rechnung ausstellen ───────────────────────────────────
#
# Aus dem Betrieb, 16.09.2026: "Rechnungen bezahlen gibt es ja schon ... solte halt
# nur auch geld rein bekommen". Bis dahin konnte diese Anwendung ueber
# Lightning nur zahlen: rechnung_ausstellen gab es zwar, aber ausschliesslich
# als Innenteil des Umschichtens -- ohne Endpunkt und ohne Oberflaeche. Ein
# Knoten, der nicht empfangen kann, ist auf der halben Strecke taub.
#
# AddInvoice ist ein POST auf /v1/invoices und braucht invoices:write; das
# Recht liegt seit dem 12.09.2026 im Macaroon. Es bewegt kein Geld -- das
# Schwerste, was jemand damit anrichten kann, ist eine Forderung, die niemand
# bezahlt. Deshalb steht es auch nicht hinter der PIN.
RECHNUNG_GUELTIG_S = 3600
RECHNUNGEN_HOECHSTENS = 20
ZWECK_ZEICHEN = 120


def _hex_aus_b64(wert: Any) -> str:
    """LND schickt Hashes ueber REST als base64 -- lesbar ist Hex."""
    try:
        return base64.b64decode(str(wert or ""), validate=True).hex()
    except (ValueError, TypeError):
        return ""


def rechnung_erstellen(knoten: Knoten, betrag_sat: int = 0, zweck: str = "",
                       gueltig_s: int = RECHNUNG_GUELTIG_S) -> Dict[str, Any]:
    """Eine Rechnung, damit jemand an diesen Knoten zahlen kann.

    Betrag 0 heisst: die Rechnung nennt keinen: der Zahlende bestimmt ihn.
    Das ist gewollt und gebraeuchlich -- etwa fuer eine Spende.

    Was eine Rechnung NICHT kann: Geld herbeischaffen. Bezahlt werden kann sie
    nur, wenn auf der Gegenseite eines Kanals genug liegt (Empfangsraum). Ohne
    einen einzigen Kanal laeuft jede Zahlung ins Leere, und die Oberflaeche
    sagt das auch.
    """
    gueltig = max(60, int(gueltig_s))
    sauber = (zweck or "")[:ZWECK_ZEICHEN]
    d = knoten.ruf("/v1/invoices", macaroon=EIGENES_MACAROON, daten={
        "value": str(max(0, int(betrag_sat))),
        "memo": sauber,
        "expiry": str(gueltig),
    }) or {}
    rechnung = d.get("payment_request") or ""
    if not rechnung:
        raise LndFehler("LND hat keine Rechnung herausgegeben.")
    return {
        "rechnung": rechnung,
        "kennung": _hex_aus_b64(d.get("r_hash")),
        "betrag_sat": max(0, int(betrag_sat)),
        "zweck": sauber,
        "laeuft_ab_s": int(time.time()) + gueltig,
    }


# Wie LNDs Zustaende hier heissen. ACCEPTED ist eine Halteklammer (AMP oder
# Hold-Invoice): angenommen, aber noch nicht abgerechnet.
RECHNUNGSZUSTAENDE = {
    "SETTLED": "bezahlt",
    "CANCELED": "storniert",
    "ACCEPTED": "unterwegs",
}

# Welche davon endgueltig sind. "unterwegs" gehoert NICHT dazu: eine
# angenommene Rechnung kann noch abgerechnet oder storniert werden.
RECHNUNG_ENDZUSTAENDE = ("bezahlt", "storniert")


def _rechnung_auslesen(r: Dict[str, Any]) -> Dict[str, Any]:
    """Eine Rechnung von LND in unsere Form -- eine Stelle fuer alle Wege.

    Die Liste, das Nachschlagen und das Abwarten liefern dieselbe Rechnung.
    Also muss sie ueberall gleich aussehen, sonst zeigt die Oberflaeche je
    nach Weg etwas anderes ueber denselben Vorgang.
    """
    erstellt = _mit_vorzeichen(r.get("creation_date"))
    zustand = str(r.get("state") or "OPEN").upper()
    return {
        "kennung": _hex_aus_b64(r.get("r_hash")),
        "rechnung": str(r.get("payment_request") or ""),
        "zweck": str(r.get("memo") or ""),
        "betrag_sat": _mit_vorzeichen(r.get("value")),
        "bezahlt_sat": _mit_vorzeichen(r.get("amt_paid_sat")),
        "erstellt_s": erstellt,
        "bezahlt_s": _mit_vorzeichen(r.get("settle_date")),
        "laeuft_ab_s": erstellt + _mit_vorzeichen(r.get("expiry")),
        "zustand": RECHNUNGSZUSTAENDE.get(zustand, "offen"),
    }


def rechnungen(knoten: Knoten,
               hoechstens: int = RECHNUNGEN_HOECHSTENS) -> Dict[str, Any]:
    """Die letzten eigenen Rechnungen -- und ob sie bezahlt wurden.

    ListInvoices ist ein GET auf /v1/invoices und braucht nur invoices:read.
    "reversed" liefert die juengsten; sortiert wird hier trotzdem selbst,
    denn die Reihenfolge innerhalb der Antwort ist nicht zugesichert.
    """
    d = knoten.ruf("/v1/invoices?reversed=true&num_max_invoices="
                   + str(int(hoechstens))) or {}
    liste = [_rechnung_auslesen(r) for r in d.get("invoices") or []]
    liste.sort(key=lambda r: -r["erstellt_s"])
    return {"rechnungen": liste[:hoechstens],
            "weitere": max(0, len(liste) - hoechstens)}


# ── Eine EINZELNE Rechnung: nachsehen, abwarten, zuruecknehmen ────────────
#
# LNDs zweite Rechnungsschnittstelle (invoicesrpc) lag bis zum 23.09.2026
# vollstaendig brach -- sechs Routen, keine einzige benutzt. Ausgestellt wurde
# ueber /v1/invoices, und ob bezahlt wurde, stand in der nachgeladenen Liste
# der letzten zwanzig. Das beantwortet "sind meine letzten zwanzig bezahlt?",
# nicht "ist DIESE eine gerade bezahlt worden?". Wer einen QR-Code hinhaelt,
# will genau das zweite wissen, und zwar in dem Augenblick, in dem es
# geschieht.
#
# ACHTUNG, Hex gilt hier NICHT. Ueberall sonst in dieser Datei reist eine
# Kennung als Hex; diese Routen nehmen die Zahlungskennung als bytes-Feld,
# und LNDs REST-Tor setzt bytes ueber base64 um. Nachgeschlagen, nicht
# geraten: lnd v0.21.3-beta haengt laut seiner go.mod an grpc-gateway/v2
# v2.16.0, und dort steht in runtime/convert.go:
#
#     func Bytes(val string) ([]byte, error) {
#         b, err := base64.StdEncoding.DecodeString(val)
#         if err != nil { b, err = base64.URLEncoding.DecodeString(val) }
#
# Erst das Standard-Alphabet, dann das URL-sichere -- beide MIT Fuellzeichen,
# eine ungefuellte Form scheitert. Hex kaeme als Unsinn an. Genommen wird die
# URL-sichere Form, denn im Pfad von /v2/invoices/subscribe/{r_hash} wuerde
# ein "/" aus dem Standard-Alphabet die Route zerschneiden. Im Rumpf des
# Stornos ist beides recht (protojson liest beide Alphabete) -- eine Form
# fuer alle drei ist trotzdem die, die man nicht verwechseln kann.

ZAHLUNGSKENNUNG_ZEICHEN = 64      # 32 Byte Hash, in Hex geschrieben

# Wie lange ein Abwarten hoechstens stillsteht, bevor es ohne Ergebnis
# zurueckkehrt. Keine Ewigkeit: hinter dem Aufruf steht ein Browser, der
# irgendwann von selbst aufgibt, und ein Arbeitsfaden, der solange gebunden
# ist. Wer weiterwarten will, fragt noch einmal.
RECHNUNG_WARTEN_S = 45


def _kennung_b64(kennung: str) -> str:
    """Eine Zahlungskennung so, wie LNDs REST-Tor sie annimmt."""
    sauber = (kennung or "").strip().lower()
    if len(sauber) != ZAHLUNGSKENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in sauber):
        raise LndFehler("Das ist keine gueltige Zahlungskennung.")
    return base64.urlsafe_b64encode(bytes.fromhex(sauber)).decode()


def rechnung_nachsehen(knoten: Knoten, kennung: str) -> Dict[str, Any]:
    """Der Stand EINER Rechnung -- LookupInvoiceV2.

    Die Liste reicht bis zu den letzten zwanzig; was aelter ist, faellt aus
    ihr heraus. Hier gibt es die eine, nach der gefragt wird, gleichgueltig
    wie viele seither dazugekommen sind.

    Braucht invoices:read -- Lesen, mehr nicht.
    """
    d = knoten.ruf("/v2/invoices/lookup?payment_hash="
                   + urllib.parse.quote(_kennung_b64(kennung), safe="")) or {}
    return _rechnung_auslesen(d)


def rechnung_abwarten(knoten: Knoten, kennung: str,
                      frist_s: int = RECHNUNG_WARTEN_S) -> Dict[str, Any]:
    """Auf DIESE eine Rechnung warten -- SubscribeSingleInvoice.

    Ein Strom, kein Abruf: LND meldet sich von selbst, sobald sich an der
    Rechnung etwas tut. Die erste Meldung kommt sofort und traegt den Stand
    von jetzt; danach kommt nur noch etwas, wenn wirklich etwas geschieht.

    Kehrt zurueck, sobald der Stand endgueltig ist -- oder wenn die Frist um
    ist, dann mit dem zuletzt bekannten. Eine abgelaufene Frist ist hier KEIN
    Fehler, sondern der Normalfall: es hat eben noch niemand bezahlt.
    """
    pfad = "/v2/invoices/subscribe/" + urllib.parse.quote(
        _kennung_b64(kennung), safe="")
    letzte: Dict[str, Any] = {}
    try:
        for meldung in knoten.strom(pfad, methode="GET", zeitlimit=frist_s):
            r = meldung.get("result") or {}
            if not r:
                continue
            letzte = _rechnung_auslesen(r)
            if letzte["zustand"] in RECHNUNG_ENDZUSTAENDE:
                return letzte
    except Beschaeftigt:
        # Frist um, ohne dass sich etwas getan hat. Genau dafuer ist sie da.
        pass
    # Hat der Strom gar nichts gesagt -- etwa weil LND gerade erst hochkam --
    # bleibt der Abruf. Lieber ein Stand als eine leere Antwort.
    return letzte or rechnung_nachsehen(knoten, kennung)


def rechnung_stornieren(knoten: Knoten, kennung: str) -> None:
    """Eine Rechnung unbezahlbar machen -- CancelInvoice.

    Wofuer: ein Betrag vertippt, ein falscher Zweck, oder die Sache hat sich
    erledigt. Eine Rechnung laeuft sonst bis zu ihrem Ablauf weiter und kann
    bis dahin jederzeit bezahlt werden -- auch von jemandem, der den QR-Code
    noch offen hat. Geld bewegt das keines, es nimmt nur die Forderung
    zurueck.

    NUR fuer eine offene Rechnung gedacht. Eine angenommene ("unterwegs")
    haelt bereits Geld des Zahlenden fest; sie zu stornieren gaebe es zurueck
    -- das ist der Sinn einer Halterechnung, und die stellt diese Anwendung
    nicht aus. Geprueft wird das eine Stelle hoeher, dort wo auch die Antwort
    dafuer steht.

    Braucht invoices:write -- dasselbe Recht wie das Ausstellen.
    """
    knoten.ruf("/v2/invoices/cancel", macaroon=EIGENES_MACAROON,
               daten={"payment_hash": _kennung_b64(kennung)})


# ── Halterechnungen und der HTLC-Eingriff: mit Absicht nicht gebaut ───────
#
# invoicesrpc hat sechs Routen. Drei stehen oben, drei bleiben draussen --
# und das ist eine Entscheidung, kein Vergessen:
#
#   POST /v2/invoices/hodl     AddHoldInvoice
#   POST /v2/invoices/settle   SettleInvoice
#       Eine Halterechnung nimmt das Geld des Zahlenden an und haelt es fest,
#       ohne es zu vereinnahmen -- bis jemand abrechnet oder storniert. Der
#       Baustein fuer "erst die Ware, dann das Geld". Wer nicht abrechnet,
#       haelt fremdes Geld in einem HTLC fest, bis dessen Sperrfrist ablaeuft;
#       dann erzwingt die Gegenstelle das Schliessen des Kanals. Ein Knopf
#       dafuer in einer Oberflaeche, hinter der kein Laden steht, ist kein
#       Werkzeug, sondern eine Falle -- es gibt hier nichts zu liefern,
#       worauf jemand warten muesste.
#
#   POST /v2/invoices/htlcmodifier   HtlcModifier
#       Ein Eingriff in hereinkommende HTLCs, und zwar als zweiseitiger
#       Strom. Er wirkt nur, solange am anderen Ende jemand zuhoert -- und
#       darin liegt das Problem: haengt sich ein Eingriff an und stirbt,
#       bleiben hereinkommende Zahlungen stehen. Ein Dienst, der sich
#       gelegentlich neu startet, wuerde damit das Empfangen kaputtmachen
#       statt es zu verbessern.


def rechnung_ausstellen(knoten: Knoten, betrag_sat: int,
                        zweck: str = "") -> Dict[str, Any]:
    """Die Rechnung fuers Umschichten -- kurz gueltig, eigener Zweck.

    Sie wird in Sekunden bezahlt oder gar nicht; deshalb laeuft sie schnell
    ab statt eine Stunde lang offen zu stehen. Zurueck kommen die Rechnung
    UND ihre Kennung: mit der laesst sich die Zahlung weiterverfolgen, wenn
    sie in der Frist kein Ergebnis bringt.
    """
    return rechnung_erstellen(
        knoten, betrag_sat, zweck or UMSCHICHTEN_ZWECK,
        int(ZAHLUNG_ZEITLIMIT_SEKUNDEN * 5))


def umschichten(knoten: Knoten, von_nummer: str, nach_kennung: str,
                betrag_sat: int, gebuehrengrenze_sat: int) -> Dict[str, Any]:
    """Liquiditaet von einem eigenen Kanal in einen anderen schieben.

    "von" ist der Kanal, durch den es HINAUSgeht -- der wird leerer.
    "nach" ist die Gegenstelle, ueber die es ZURUECKkommt -- der wird voller.

    Beides muss vorgegeben werden, sonst sucht LND sich irgendeinen Weg und
    schichtet womoeglich genau falsch herum um.
    """
    nach = (nach_kennung or "").strip().lower()
    if len(nach) != KENNUNG_ZEICHEN or any(
            z not in "0123456789abcdef" for z in nach):
        raise LndFehler("Die Zielgegenstelle ist keine gueltige Kennung.")
    if not (von_nummer or "").strip().isdigit():
        raise LndFehler("Der Ausgangskanal fehlt.")
    if betrag_sat <= 0:
        raise LndFehler("Ohne Betrag gibt es nichts umzuschichten.")

    ausgestellt = rechnung_ausstellen(knoten, betrag_sat)
    daten: Dict[str, Any] = {
        "payment_request": ausgestellt["rechnung"],
        "timeout_seconds": ZAHLUNG_ZEITLIMIT_SEKUNDEN,
        "fee_limit_sat": str(int(gebuehrengrenze_sat)),
        # HIER an, und nur hier: das ist der Zweck des Vorgangs.
        "allow_self_payment": True,
        # Ohne diese beiden sucht LND sich einen beliebigen Rundweg.
        "outgoing_chan_ids": [str(von_nummer).strip()],
        "last_hop_pubkey": base64.b64encode(bytes.fromhex(nach)).decode(),
    }
    letzte: Dict[str, Any] = {}
    try:
        for meldung in knoten.strom(
                "/v2/router/send", daten, macaroon=EIGENES_MACAROON,
                zeitlimit=ZAHLUNG_ZEITLIMIT_SEKUNDEN + ZAHLUNG_LUFT_SEKUNDEN):
            if meldung.get("error"):
                raise LndFehler(str(meldung["error"]))
            ergebnis = meldung.get("result") or {}
            if ergebnis:
                letzte = ergebnis
            if ergebnis.get("status") in ("SUCCEEDED", "FAILED"):
                break
    except ZahlungUnterwegs:
        raise
    except Beschaeftigt as fehler:
        # Losgeschickt, aber kein Ergebnis in der Frist. Mit der Kennung
        # laesst sie sich weiterverfolgen, statt dass jemand raten muss.
        raise ZahlungUnterwegs(str(fehler), ausgestellt["kennung"]) from fehler

    if letzte.get("status") != "SUCCEEDED":
        raise LndFehler(letzte.get("failure_reason")
                        or letzte.get("status") or "UNBEKANNT")
    return {
        "betrag": _zahl(letzte.get("value_sat")),
        "gebuehr": _zahl(letzte.get("fee_sat")),
    }


# Wie lange ein Abwarten einer Zahlung hoechstens stillsteht -- dieselbe
# Frist wie bei einer Rechnung, aus demselben Grund: lang genug, dass die
# Oberflaeche nicht klopfen muss, kurz genug fuer jeden Proxy davor.
ZAHLUNG_WARTEN_S = RECHNUNG_WARTEN_S

# Welche Zustaende von TrackPaymentV2 endgueltig sind (router.swagger.json,
# v0.21.3-beta: UNKNOWN, IN_FLIGHT, SUCCEEDED, FAILED, INITIATED).
_ZAHLUNG_ENDE = {"SUCCEEDED": "angekommen", "FAILED": "gescheitert"}


def zahlung_abwarten(knoten: Knoten, kennung: str,
                     frist_s: int = ZAHLUNG_WARTEN_S) -> Dict[str, Any]:
    """Eine eigene, losgeschickte Zahlung weiterverfolgen -- TrackPaymentV2.

    DER BEFUND VOM 24.09.2026: ein Umschichten bekam in der Frist keine
    Antwort, die Oberflaeche sagte "nicht wiederholen" und sperrte den Knopf
    -- und dann wusste niemand, wie es ausging. Die Antwort stand nur im
    LND-Protokoll ("MPPTimeout@3").

    Ein Strom: die erste Meldung traegt den Stand von jetzt, danach kommt
    etwas, wenn sich etwas tut. Kehrt zurueck, sobald der Stand endgueltig
    ist -- oder mit "unterwegs", wenn die Frist um ist. Das ist kein Fehler,
    es hat sich eben noch nichts entschieden.

    bytes im Pfad: URL-sicheres base64, dieselbe Falle wie bei den
    Rechnungen (siehe dort). Nur lesend: offchain:read.
    """
    pfad = "/v2/router/track/" + urllib.parse.quote(
        _kennung_b64(kennung), safe="")
    letzte: Dict[str, Any] = {}
    try:
        for meldung in knoten.strom(pfad, macaroon=EIGENES_MACAROON,
                                    zeitlimit=frist_s, methode="GET"):
            if meldung.get("error"):
                raise LndFehler(str(meldung["error"]))
            ergebnis = meldung.get("result") or {}
            if ergebnis:
                letzte = ergebnis
            if ergebnis.get("status") in _ZAHLUNG_ENDE:
                break
    except ZahlungUnterwegs:
        raise
    except Beschaeftigt:
        pass
    zustand = _ZAHLUNG_ENDE.get(letzte.get("status", ""), "unterwegs")
    return {
        "zustand": zustand,
        "betrag": _zahl(letzte.get("value_sat")),
        "gebuehr": _zahl(letzte.get("fee_sat")),
        "grund": (str(letzte.get("failure_reason") or "")
                  if zustand == "gescheitert" else ""),
    }


# ── Der HTLC-Strom: was hindurchgeht -- und was NICHT ──────────────────────
#
# Aus dem Betrieb, 12.09.2026: "koennen wir noch den HTLC-Strom mit rein nehmen?"
#
# Bis hierher las die Anwendung LNDs /v1/switch -- die Historie der
# ABGESCHLOSSENEN Weiterleitungen. Die sagt, was gelungen ist.
#
# Das Betriebswissen steckt im Gegenteil. Ein LinkFailEvent traegt einen
# Grund, und der ist die eigentliche Auskunft: "INSUFFICIENT_BALANCE" heisst
# nicht "es ging etwas schief", sondern "DIESER Kanal ist leer und gehoert
# nachgefuellt". Das steht in keiner Historie -- es kommt nur live, und wenn
# niemand zuhoert, ist es weg.
#
# Vier Ereignisarten, und sie bedeuten Verschiedenes:
#
#   forward_event      -- eine Weiterleitung hat begonnen
#   settle_event       -- sie ist angekommen (und hat Gebuehr gebracht)
#   forward_fail_event -- weiter hinten im Weg gescheitert, nicht bei uns
#   link_fail_event    -- BEI UNS gescheitert, mit Grund. Das ist der Fall,
#                         an dem man etwas aendern kann.

# Die Zuordnung Ereignis -> unsere Art. Kurz und in unserer Sprache, damit
# die Oberflaeche nicht LNDs Namen ausstellen muss.
HTLC_ARTEN = (
    ("forward_event", "weiterleiten"),
    ("settle_event", "erledigt"),
    ("forward_fail_event", "fehl"),
    ("link_fail_event", "link_fehl"),
)


def _htlc_betrag(roh: Dict) -> tuple:
    """Betrag und Gebuehr einer Weiterleitung, in Satoshi.

    LND rechnet hier in MILLIsatoshi. Wer das uebersieht, zeigt tausendfache
    Betraege -- und die Gebuehr ist die Differenz zwischen dem, was
    hereinkam, und dem, was hinausging.
    """
    info = (roh.get("info") or {})
    rein = _zahl(info.get("incoming_amt_msat"))
    raus = _zahl(info.get("outgoing_amt_msat"))
    return raus // 1000, max(0, rein - raus) // 1000


def htlc_strom(knoten: Knoten):
    """Der laufende Strom. Gibt fertige Zeilen heraus, keine LND-Rohdaten.

    Laeuft, bis die Verbindung abreisst -- wer ihn benutzt, faengt ihn wieder
    an. Ein Strom mit eingebautem Wiederanlauf waere schwerer zu pruefen und
    haette denselben Nutzen.
    """
    for meldung in knoten.strom("/v2/router/htlcevents", macaroon="readonly",
                                methode="GET", zeitlimit=None):
        e = meldung.get("result") or {}
        if not e:
            continue
        art = ""
        einzelheit = {}
        for feld, name in HTLC_ARTEN:
            if e.get(feld) is not None:
                art, einzelheit = name, e.get(feld) or {}
                break
        if not art:
            continue
        betrag, gebuehr = _htlc_betrag(einzelheit)
        # Der Grund gibt es nur beim link_fail -- und dort ist er der Punkt.
        # failure_detail ist die genauere der beiden Angaben; wire_failure
        # ist das, was die Gegenstelle zu sehen bekam.
        grund = (einzelheit.get("failure_detail")
                 or einzelheit.get("wire_failure") or "") or None
        yield {
            # LND zaehlt in Nanosekunden seit der Epoche.
            "zeit_ms": _zahl(e.get("timestamp_ns")) // 1_000_000
                       or int(time.time() * 1000),
            "art": art,
            "rein_kanal": str(e.get("incoming_channel_id") or "") or None,
            "raus_kanal": str(e.get("outgoing_channel_id") or "") or None,
            "betrag": betrag,
            "gebuehr": gebuehr,
            "grund": grund,
        }


# ── Einen Kanal schliessen ─────────────────────────────────────────────────
#
# Aus dem Betrieb, 12.09.2026: "kann ich dann auch selber ein kanal kuendigen oder
# schliessen?"
#
# Bis dahin nicht, und meine Begruendung war zu kurz: "ein Kanal, den eine
# uebernommene Sitzung schliessen koennte, ist ein Verlust". Sein eigener Satz
# vom 30.08.2026 trifft es besser -- nichts dahin ueberweisen, solange man es
# nicht zurueckschicken kann. Fuer Kanaele gilt dasselbe: einer, den man aus
# der eigenen Software nicht schliessen kann, ist eine Einbahnstrasse. Und man
# waere ausgerechnet dann auf fremde Werkzeuge angewiesen, wenn etwas
# schiefgeht.
#
# ZWEI VERSCHIEDENE VORGAENGE, und sie gehoeren auseinandergehalten:
#
#   einvernehmlich -- beide machen mit. Guenstig, das Geld ist sofort zurueck.
#                     Der Normalfall.
#   erzwungen      -- nur, wenn die Gegenstelle nicht mehr antwortet. Teurer,
#                     und das Guthaben liegt danach fuer die Zeitsperre fest.
#
# Deshalb ist "erzwingen" hier ein eigener Schalter und keine Ausweichroute,
# die automatisch greift, wenn das Einvernehmliche scheitert.


def kanal_schliessen(knoten: Knoten, kanalpunkt: str, satz_sat_vb: int = 0,
                     erzwingen: bool = False) -> Dict[str, Any]:
    """Einen Kanal schliessen. Gibt die Kennung der Schliesstransaktion.

    Zurueck kommt, sobald die Transaktion steht -- nicht erst, wenn sie
    bestaetigt ist. Auf die Bestaetigung zu warten hiesse, die Oberflaeche
    fuer Bloecke anzuhalten; sie steht ohnehin gleich in der Kanalliste.
    """
    txid, _trenner, ausgang = (kanalpunkt or "").strip().partition(":")
    if not (txid and ausgang.isdigit()):
        raise LndFehler("Der Kanalpunkt fehlt oder ist unlesbar.")

    frage = {"force": "true" if erzwingen else "false"}
    # Beim erzwungenen Schliessen bestimmt LND die Gebuehr selbst -- die
    # Verpflichtungstransaktion steht laengst fest und traegt ihre eigene.
    if satz_sat_vb and not erzwingen:
        frage["sat_per_vbyte"] = str(int(satz_sat_vb))
    pfad = (f"/v1/channels/{urllib.parse.quote(txid, safe='')}/"
            f"{int(ausgang)}?" + urllib.parse.urlencode(frage))

    for meldung in knoten.strom(pfad, macaroon=EIGENES_MACAROON,
                                methode="DELETE", zeitlimit=60.0):
        if meldung.get("error"):
            raise LndFehler(str(meldung["error"]))
        ergebnis = meldung.get("result") or {}
        offen = ergebnis.get("close_pending") or {}
        if offen:
            return {
                "txid": _txid_lesbar(offen.get("txid") or ""),
                "erzwungen": bool(erzwingen),
            }
    raise LndFehler("LND hat keine Schliesstransaktion gemeldet.")


def setze_gebuehren(knoten: Knoten, basis_msat: int, satz_ppm: int,
                    zeitsperre: int = 144,
                    kanalpunkt: str = "") -> Dict[str, Any]:
    """Was dieser Knoten fuers Weiterleiten nimmt.

    Ohne Kanalpunkt gilt es fuer ALLE Kanaele. Mit Kanalpunkt nur fuer den
    einen -- und genau das ist der Betriebsgriff: teuer machen, wo ein Kanal
    leerlaeuft, billig, wo er aufgefuellt werden soll.
    """
    daten: Dict[str, Any] = {
        "base_fee_msat": str(int(basis_msat)),
        "fee_rate_ppm": int(satz_ppm),
        "time_lock_delta": int(zeitsperre),
    }
    if kanalpunkt:
        txid, _, index = kanalpunkt.partition(":")
        daten["chan_point"] = {"funding_txid_str": txid,
                               "output_index": int(index or 0)}
    else:
        daten["global"] = True
    return knoten.ruf("/v1/chanpolicy", macaroon=EIGENES_MACAROON,
                      daten=daten) or {}
