"""Sprechen mit bitcoind ueber JSON-RPC.

Bewusst mit der Standardbibliothek statt einer HTTP-Bibliothek: es sind ein
paar Aufrufe gegen einen Dienst im selben Compose-Netz, und jede zusaetzliche
Abhaengigkeit ist eine mehr, die gepflegt und auf Schwachstellen geprueft
werden muss.

Wichtig ist die Fehlerbehandlung. Waehrend der Einrichtung, beim Neustart und
in den ersten Minuten des Erstsyncs ist bitcoind schlicht nicht da. Das ist
kein Fehler, sondern der Normalfall -- die Oberflaeche soll dann "wird
gestartet" zeigen und nicht eine Ausnahme.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
import logging
import socket
import time
import urllib.error
import urllib.request
from base64 import b64encode
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional


log = logging.getLogger(__name__)


class NichtErreichbar(Exception):
    """bitcoind antwortet nicht -- laeuft noch nicht oder gerade nicht."""


class Beschaeftigt(NichtErreichbar):
    """bitcoind LAEUFT, kommt aber gerade nicht zum Antworten.

    Ein eigener Fall, weil er etwas voellig anderes bedeutet -- und weil die
    Verwechslung teuer war: die Uebersicht meldete "bitcoind antwortet noch
    nicht", der Fortschritt sprang auf "—", und es sah aus, als starte der
    Dienst staendig neu. Er startete nie neu.

    Waehrend des Erstabgleichs schreibt Bitcoin Core den chainstate weg,
    sobald der dbcache voll ist. Dabei haelt es cs_main, und jeder Aufruf,
    der diese Sperre braucht -- getblockchaininfo gehoert dazu -- wartet.
    Auf einer langsamen Ablage dauert das nicht Millisekunden, sondern
    Sekunden bis Minuten. Von aussen ist derselbe Knoten in dieser Zeit auch
    ueber P2P nicht zu sprechen: am 28.08.2026 gemessen, zwei Handschlaege
    in 0,0 und 0,2 Sekunden, der dritte lief in 20 Sekunden Zeitlimit.

    Unterschieden wird an der Ursache, nicht am Gefuehl: ein Zeitlimit heisst
    "da, aber beschaeftigt", eine abgelehnte Verbindung heisst "nicht da".
    Das eine ist zu warten, das andere zu beheben.
    """


class RpcFehler(Exception):
    """bitcoind antwortet, lehnt den Aufruf aber ab."""


@dataclass
class Knoten:
    host: str = "bitcoind"
    port: int = 8332
    benutzer: str = ""
    passwort: str = ""
    zeitlimit: float = 5.0

    def ruf(self, methode: str, *params: Any,
            zeitlimit: Optional[float] = None) -> Any:
        """Einen RPC-Aufruf machen.

        zeitlimit ueberschreibt das der Instanz fuer diesen einen Aufruf.
        Gedacht fuer die wenigen Abfragen, deren Antwort gross ist -- das
        Adressbuch etwa -- ohne deswegen allen anderen Aufrufen die kurze
        Leine zu nehmen, an der sie einen abwesenden Knoten schnell erkennen.
        """
        rumpf = json.dumps({
            "jsonrpc": "1.0", "id": "satcortex",
            "method": methode, "params": list(params),
        }).encode("utf-8")

        anfrage = urllib.request.Request(
            f"http://{self.host}:{self.port}/",
            data=rumpf,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + b64encode(
                    f"{self.benutzer}:{self.passwort}".encode("utf-8")
                ).decode("ascii"),
            },
        )
        try:
            frist = self.zeitlimit if zeitlimit is None else zeitlimit
            with urllib.request.urlopen(anfrage, timeout=frist) as antwort:  # nosec B310
                daten = json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            # 401 heisst falsche Zugangsdaten, 500 kommt bei abgelehnten
            # Aufrufen -- beides ist etwas anderes als "nicht da".
            if fehler.code == 401:
                raise RpcFehler("Zugangsdaten werden abgelehnt") from fehler
            # 503 ist der eine Statuscode, der genau "da, aber beschaeftigt"
            # bedeutet -- und er landete bis zum 01.09.2026 bei RpcFehler,
            # also bei "antwortet und lehnt ab". Geprueft gegen Bitcoin Core
            # v31.1, src/httpserver.cpp:
            #
            #   if (... WorkQueueSize() >= g_max_queue_depth) {
            #       LogWarning("Request rejected because http work queue
            #                   depth exceeded, it can be increased with the
            #                   -rpcworkqueue= setting");
            #       hreq->WriteReply(HTTP_SERVICE_UNAVAILABLE,
            #                        "Work queue depth exceeded");
            #
            # Die Schlange ist 64 tief (DEFAULT_HTTP_WORKQUEUE in
            # httpserver.h), bedient von 16 Faeden (DEFAULT_HTTP_THREADS).
            # Voll wird sie, wenn Cores RPC-Faeden an cs_main haengen -- also
            # genau in den Phasen, in denen der Knoten den chainstate
            # wegschreibt. Der Rumpf ist dabei kein JSON, sondern der Satz
            # oben; deshalb faellt er unten ohnehin durch json.loads.
            if fehler.code == 503:
                raise Beschaeftigt(
                    "die Warteschlange von bitcoind ist voll") from fehler
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                raise RpcFehler(str(inhalt.get("error", fehler.code))) from fehler
            except (ValueError, AttributeError):
                raise RpcFehler(f"HTTP {fehler.code}") from fehler
        except (urllib.error.URLError, socket.timeout, ConnectionError,
                OSError) as fehler:
            # urllib verpackt das Zeitlimit in URLError -- der Grund steckt
            # dann in .reason. Ohne diesen Griff sieht ein Zeitlimit aus wie
            # ein abgelehnter Verbindungsversuch.
            grund = getattr(fehler, "reason", fehler)
            if isinstance(fehler, socket.timeout) or isinstance(grund, socket.timeout) \
               or isinstance(grund, TimeoutError) or isinstance(fehler, TimeoutError):
                raise Beschaeftigt(
                    f"antwortet nicht innerhalb von {frist:.0f} s") from fehler
            raise NichtErreichbar(str(fehler)) from fehler

        if daten.get("error"):
            raise RpcFehler(str(daten["error"]))
        return daten.get("result")

    # ------------------------------------------------------------ Strom
    #
    # DER BEFUND VOM 21.09.2026: "wenn der mempool voll ist oder fast voll
    # ist kann ich keine kacheln mehr holen".
    #
    # Die Kachelansicht holte den Mempool mit ruf("getrawmempool", True) --
    # also die ganze Antwort auf einmal, und zwar dreifach gleichzeitig:
    # read() als Bytes, decode() als String, json.loads() als Objekte.
    # Nachgemessen mit Cores eigener Feldliste (rpc/mempool.cpp, entryToJSON):
    #
    #     10.000 TX ->  4,8 MB JSON ->  26 MB beim Einlesen
    #     50.000 TX -> 23,8 MB JSON -> 134 MB
    #    150.000 TX -> 71,4 MB JSON -> 397 MB
    #
    # Das Limit des app-Containers steht auf 400M. Ein voller Mempool hat
    # gereicht, um den Container vom OOM-Killer beenden zu lassen -- und weil
    # er "restart: unless-stopped" traegt, war danach die ganze Oberflaeche
    # kurz weg. Nicht nur die Kacheln.
    #
    # Deshalb hier derselbe Weg wie bei LNDs Netzgraph (lnd.Knoten.brocken):
    # in Stuecken lesen und nebenher auswerten, statt alles zu halten.
    def brocken(self, methode: str, *params: Any,
                zeitlimit: Optional[float] = None,
                haeppchen: int = 256 * 1024) -> Iterator[bytes]:
        """Die Antwort in Stuecken, ohne sie je ganz im Speicher zu halten.

        Fehler werden genauso uebersetzt wie in ruf() -- wer streamt, soll
        dieselben Ausnahmen behandeln muessen und nicht andere.
        """
        rumpf = json.dumps({
            "jsonrpc": "1.0", "id": "satcortex",
            "method": methode, "params": list(params),
        }).encode("utf-8")
        anfrage = urllib.request.Request(
            f"http://{self.host}:{self.port}/",
            data=rumpf,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + b64encode(
                    f"{self.benutzer}:{self.passwort}".encode("utf-8")
                ).decode("ascii"),
            },
        )
        frist = self.zeitlimit if zeitlimit is None else zeitlimit
        try:
            antwort = urllib.request.urlopen(anfrage, timeout=frist)  # nosec B310
        except urllib.error.HTTPError as fehler:
            if fehler.code == 401:
                raise RpcFehler("Zugangsdaten werden abgelehnt") from fehler
            if fehler.code == 503:
                raise Beschaeftigt(
                    "die Warteschlange von bitcoind ist voll") from fehler
            raise RpcFehler(f"HTTP {fehler.code}") from fehler
        except (urllib.error.URLError, socket.timeout, ConnectionError,
                OSError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            if isinstance(fehler, (socket.timeout, TimeoutError)) or \
               isinstance(grund, (socket.timeout, TimeoutError)):
                raise Beschaeftigt(
                    f"antwortet nicht innerhalb von {frist:.0f} s") from fehler
            raise NichtErreichbar(str(fehler)) from fehler
        with antwort:
            while True:
                stueck = antwort.read(haeppchen)
                if not stueck:
                    return
                yield stueck


# Wieviel Geduld die Statusabfrage mitbringt.
#
# Fuenf Sekunden -- das Zeitlimit fuer alles Uebrige -- reichen waehrend des
# Erstabgleichs nicht. Am 28.08.2026 von aussen gemessen: von fuenf sauberen
# Handschlaegen kamen vier in unter 0,2 Sekunden zurueck und einer gar nicht,
# auch nach zwanzig Sekunden nicht. In diesen Phasen schreibt Core den
# chainstate weg und haelt cs_main; getblockchaininfo wartet darauf.
#
# Rund ein Fuenftel der Zeit war der Knoten so nicht ansprechbar. Mit fuenf
# Sekunden faellt die Anzeige also bei jedem fuenften Abruf zurueck -- richtig
# beschriftet inzwischen, aber unnoetig. Mit fuenfzehn wartet sie die
# allermeisten Schreibvorgaenge einfach ab.
#
# Nach oben ist es bewusst begrenzt: die Seite fragt alle zehn Sekunden nach,
# und ein Zeitlimit, das laenger ist als der Takt, staut Abfragen auf. Wenn
# es wirklich einmal laenger dauert, sagt die Oberflaeche das jetzt richtig.
# Waehrend des Erstabgleichs ist bitcoind mit Pruefen beschaeftigt, und seine
# RPC-Arbeiter stehen in der Schlange. Die voreingestellten fuenf Sekunden
# sind dann zu knapp: am 01.09.2026 stand "getnetworkinfo nicht moeglich:
# antwortet nicht innerhalb von 5 s" in das Betriebsprotokoll, waehrend der
# Knoten voellig gesund war und mit 176 Bloecken je Minute durchlief.
#
# Das gilt fuer alles, was im Hintergrund und in Abstaenden fragt. Was an
# einer Eingabe haengt, bleibt kurz -- dort ist Warten schlimmer als eine
# ehrliche Fehlanzeige.
GEDULD_SEKUNDEN = 15.0

# Frueherer Name, gleicher Wert -- die Kettenlage war die erste Abfrage, der
# die fuenf Sekunden zu knapp wurden.
GEDULD_LAGE_SEKUNDEN = GEDULD_SEKUNDEN


def kettenlage(knoten: Knoten, peers=None, gesamt=None) -> Optional[dict]:
    """Fortschritt des Abgleichs -- oder None, wenn bitcoind nicht da ist.

    Die Prozentzahl kommt aus verificationprogress, nicht aus blocks/headers.
    Der Unterschied ist gross: die Kopfzeilen sind nach Minuten vollstaendig,
    waehrend die eigentliche Arbeit -- Bloecke pruefen -- noch tagelang laeuft.
    Wer blocks/headers anzeigt, meldet nach einer Stunde "99 %" und laesst den
    Nutzer danach eine Woche im Ungewissen.
    """
    # EIN Budget fuer die ganze Lage, nicht eines je Aufruf.
    #
    # Es sind vier Aufrufe. Je fuenfzehn Sekunden waeren im schlimmsten Fall
    # eine Minute -- bei einem Takt von zehn Sekunden stauen sich die Abrufe
    # dann auf. Der alte Weg loeste das, indem nur getblockchaininfo Geduld
    # bekam; das war aber genau der Grund, warum getnetworkinfo bei jedem
    # chainstate-Schreibvorgang ausfiel, obwohl es dieselbe Sperre braucht.
    #
    # Mit einem gemeinsamen Ablauf bekommt jeder Aufruf, was noch da ist.
    # Die ganze Lage ist damit nach GEDULD_SEKUNDEN vorbei, ganz gleich wie
    # viele Aufrufe es sind.
    ablauf = time.monotonic() + GEDULD_SEKUNDEN

    def uebrig() -> float:
        # Nie ganz auf null: ein Aufruf mit Frist 0 waere kein Versuch mehr.
        return max(1.0, ablauf - time.monotonic())

    try:
        # Nur DIESER Aufruf bekommt die lange Leine. Kommt er durch, ist der
        # Knoten frei und alles Weitere geht ohnehin in Millisekunden. Allen
        # Aufrufen mehr Zeit zu geben hiesse, bei einem wirklich abwesenden
        # Knoten ein Vielfaches zu warten.
        kette = knoten.ruf("getblockchaininfo", zeitlimit=uebrig())
    except (NichtErreichbar, RpcFehler):
        # Bewusst KEINE Ausnahme nach draussen -- sechs Stellen rufen diese
        # Funktion, und eine davon ist ein Hintergrundfaden. Wer den
        # Unterschied zwischen "beschaeftigt" und "weg" braucht, nimmt
        # lage_mit_grund() darunter.
        return None

    eingehend = ausgehend = 0
    adressen = []
    kennung = ""
    netzinfo_da = False
    try:
        # Dieselbe Geduld wie getblockchaininfo, und aus demselben Grund:
        # beide nehmen laut v31.1/src/rpc/net.cpp LOCK(cs_main). Mit den
        # voreingestellten fuenf Sekunden fiel dieser Aufruf bei jedem
        # chainstate-Schreibvorgang aus -- der Aufruf, an dem die eigenen
        # Adressen und die Fassung haengen.
        netz = knoten.ruf("getnetworkinfo", zeitlimit=uebrig()) or {}
        netzinfo_da = True
        eingehend = netz.get("connections_in", 0)
        ausgehend = netz.get("connections_out", 0)
        # Was der Knoten SELBST als Fassung meldet, z. B. "/Satoshi:31.1.0/".
        # Zuverlaessiger als der Abbildname: der sagt nur, was gezogen werden
        # sollte, nicht was laeuft.
        kennung = netz.get("subversion", "") or ""
        # Die Adressen, unter denen sich der Knoten dem Netz anbietet. Steht
        # hier nur die Onion-Adresse, kennt er seine oeffentliche IP nicht --
        # dann findet ihn ueber Clearnet niemand, egal ob der Port offen ist.
        # Der "score" kommt mit und wird gebraucht: er zaehlt, wie oft dem
        # Knoten eine Adresse als die eigene gemeldet wurde. Die Karte
        # sortiert danach. Ohne ihn hier muesste sie getnetworkinfo ein
        # zweites Mal stellen -- und das ist der eine Aufruf, der laut
        # v31.1/src/rpc/net.cpp LOCK(cs_main) nimmt und deshalb waehrend
        # eines chainstate-Schreibvorgangs minutenlang wartet.
        adressen = [
            {"adresse": a.get("address", ""), "port": a.get("port", 0),
             "score": a.get("score", 0)}
            for a in (netz.get("localaddresses") or [])
            if isinstance(a, dict)
        ]
    except (NichtErreichbar, RpcFehler) as fehler:
        # KEIN stilles pass mehr. Vorher blieben eingehend/ausgehend auf 0,
        # adressen leer und kennung leer -- und die Oberflaeche zeigte das
        # als MESSWERT: "0 von mir aufgebaut · 0 von aussen angenommen",
        # "noch keine eigene Adresse bekannt". Waehrend jedes
        # chainstate-Schreibvorgangs, alle paar Minuten. Genau das Bild, das
        # Aus dem Betrieb, 02.09.2026 als "ich habe quasi keine Verbindung mehr zu
        # irgendwas" gemeldet hat.
        log.debug("getnetworkinfo nicht moeglich: %s", fehler)

    fortschritt = float(kette.get("verificationprogress", 0.0))
    ergebnis = {
        # Kein Standard "main". Ein fehlender Wert waere sonst nicht von
        # der Wahrheit zu unterscheiden -- und ausgerechnet bei der Frage
        # "haenge ich am richtigen Netz" darf nichts geraten werden.
        "kette": kette.get("chain", ""),
        "hoehe": kette.get("blocks", 0),
        "kopfzeilen": kette.get("headers", 0),
        "fortschritt": min(fortschritt, 1.0),
        "im_erstsync": bool(kette.get("initialblockdownload", True)),
        "belegt_bytes": kette.get("size_on_disk", 0),
        # Kam bei jedem Aufruf mit und wurde bis zum 01.09.2026 weggeworfen.
        "difficulty": kette.get("difficulty", 0),
        # Platzhalter -- gleich unten aus getpeerinfo ersetzt, wo es geht.
        "verbindungen_ein": eingehend,
        "verbindungen_aus": ausgehend,
        "erreichbar": eingehend > 0,
        # Ob die Adressen und die Fassung wirklich gemessen wurden. Fehlt
        # das, zeigt die Oberflaeche einen Gedankenstrich statt einer Null.
        "netzinfo_da": netzinfo_da,
        # Wo in der Zeit der Knoten gerade steht. Waehrend des Erstabgleichs
        # die anschaulichste Zahl ueberhaupt: eine Prozentangabe sagt wenig,
        # "gerade im Januar 2016 angekommen" sagt sofort etwas.
        "blockzeit": kette.get("time") or kette.get("mediantime") or 0,
        "kennung": kennung,
        "adressen": adressen,
    }
    ergebnis.update(_netzverkehr(knoten, uebrig(), gesamt))
    # NUR nach dem Abgleich. Waehrend des Abgleichs sind die Indizes ohnehin
    # abgeschaltet, die Antwort waere immer leer -- und ein Aufruf je Takt,
    # der nichts sagen kann, ist ein Aufruf zu viel bei einem Knoten, der
    # gerade jede Umdrehung der Platte braucht.
    ergebnis["indizes"] = (None if ergebnis["im_erstsync"]
                           else _indizes(knoten, uebrig()))
    # Die Verbindungszahlen kommen bevorzugt aus getpeerinfo: der Aufruf
    # braucht laut v31.1/src/rpc/net.cpp KEIN cs_main und kommt deshalb auch
    # dann durch, wenn getnetworkinfo gerade wartet. Nur wenn auch er
    # ausfaellt, bleibt es bei dem, was getnetworkinfo geliefert hat -- und
    # wenn beide ausfielen, bei None statt bei einer erfundenen Null.
    peerlage = _netze(knoten, uebrig(), peers)
    ergebnis["netze"] = peerlage["netze"]
    if peerlage["ein"] is not None:
        ergebnis["verbindungen_ein"] = peerlage["ein"]
        ergebnis["verbindungen_aus"] = peerlage["aus"]
        ergebnis["erreichbar"] = peerlage["ein"] > 0
    elif not netzinfo_da:
        ergebnis["verbindungen_ein"] = None
        ergebnis["verbindungen_aus"] = None
        ergebnis["erreichbar"] = None
    return ergebnis


# BTC pro kvB in Sat pro vB: 1e8 Sat je BTC, geteilt durch 1000 vB.
BTC_KVB_IN_SAT_VB = 100_000


def sat_aus_btc(wert: Any) -> int:
    """Einen BTC-Betrag aus Cores JSON in Satoshi -- ohne Fliesskommafehler.

    json.loads liest Cores Betraege als float, und 0.1 + 0.2 ist dort nicht
    0.3. Bei Geld rundet man nicht auf gut Glueck: der Umweg ueber die
    Dezimaldarstellung trifft den Satoshi, den Core gemeint hat.
    """
    try:
        return int((Decimal(str(wert)) * 100_000_000).to_integral_value())
    except (InvalidOperation, ValueError, TypeError):
        return 0


def mempoollage(knoten: Knoten) -> Optional[dict]:
    """Was im eigenen Mempool liegt -- oder None, wenn er noch nicht steht.

    Waehrend des Erstabgleichs nimmt Bitcoin Core gar keine Transaktionen an;
    "loaded" ist dann false und es gibt schlicht nichts zu zeigen.

    Die wichtigste Zahl hier ist mempoolminfee: die Gebuehrenrate, unterhalb
    derer dieser Knoten gerade verwirft. Sie ist der Grund, warum der eigene
    Knoten mehr weiss als ein oeffentlicher Explorer -- die grossen betreiben
    ihre Knoten mit so hohem Limit, dass sie NIE verwerfen muessen, und sehen
    diese Grenze darum nie.
    """
    try:
        m = knoten.ruf("getmempoolinfo")
    except (NichtErreichbar, RpcFehler):
        return None
    if not isinstance(m, dict) or not m.get("loaded", False):
        return None

    def sat_pro_vb(feld: str) -> float:
        # str_amount: Core liefert diese Werte als Zeichenkette, damit keine
        # Fliesskomma-Ungenauigkeit entsteht. Erst hier wird gerechnet.
        try:
            return round(float(m.get(feld, 0)) * BTC_KVB_IN_SAT_VB, 3)
        except (TypeError, ValueError):
            return 0.0

    grenze = m.get("maxmempool", 0)
    belegt = m.get("usage", 0)
    return {
        "transaktionen": m.get("size", 0),
        "vbytes": m.get("bytes", 0),
        "belegt_bytes": belegt,
        "grenze_bytes": grenze,
        "auslastung": round(belegt / grenze, 4) if grenze else 0.0,
        # Die Verwerfungsgrenze. Steht sie ueber der Mindest-Weiterleitungsrate,
        # ist der Mempool voll und der Knoten wirft das Guenstigste hinaus.
        "purge_sat_vb": sat_pro_vb("mempoolminfee"),
        "minimum_sat_vb": sat_pro_vb("minrelaytxfee"),
        "verwirft_gerade": sat_pro_vb("mempoolminfee") > sat_pro_vb("minrelaytxfee"),
        "gebuehren_btc": m.get("total_fee", "0"),
    }


def _netzverkehr(knoten: Knoten, frist: float = 5.0, n=None) -> dict:
    """Wie viel dieser Knoten empfangen und ausgeliefert hat.

    Die gesendete Menge ist die ehrlichste Zahl zum eigenen Beitrag: sie
    misst, was der Knoten anderen GEGEBEN hat.
    """
    leer = {"empfangen_bytes": 0, "gesendet_bytes": 0}
    try:
        # "n" reicht der Aufrufer herein, wenn er es ohnehin schon geholt hat.
        if n is None:
            n = knoten.ruf("getnettotals", zeitlimit=frist)
    except (NichtErreichbar, RpcFehler):
        return leer
    if not isinstance(n, dict):
        return leer
    return {
        "empfangen_bytes": n.get("totalbytesrecv", 0),
        "gesendet_bytes": n.get("totalbytessent", 0),
    }


def _netze(knoten: Knoten, frist: float = 5.0, peers=None) -> dict:
    """Peers nach Netz und Richtung.

    getpeerinfo statt getnetworkinfo, weil nur dort steht, ueber welches Netz
    die einzelne Verbindung laeuft. Wer beide Welten bedient -- Clearnet UND
    Onion --, ist im Netz die knappe Ressource.
    """
    leer = {"ipv4": 0, "ipv6": 0, "onion": 0, "sonstige": 0}
    try:
        if peers is None:
            peers = knoten.ruf("getpeerinfo", zeitlimit=frist)
    except (NichtErreichbar, RpcFehler):
        return {"netze": leer, "ein": None, "aus": None}
    if not isinstance(peers, list):
        return {"netze": leer, "ein": None, "aus": None}
    ein = aus = 0
    for p in peers:
        if not isinstance(p, dict):
            continue
        art = p.get("network", "")
        leer[art if art in leer else "sonstige"] += 1
        if p.get("inbound"):
            ein += 1
        else:
            aus += 1
    return {"netze": leer, "ein": ein, "aus": aus}


# Was der Knoten gerade ist -- und warum die Unterscheidung zaehlt.
KNOTEN_DA = "da"
KNOTEN_BESCHAEFTIGT = "beschaeftigt"
KNOTEN_WEG = "weg"
# "Wir haben noch nicht gefragt" ist ein dritter Zustand neben "laeuft" und
# "antwortet nicht" -- und der einzige richtige in den ersten Sekunden nach
# dem Start, solange der Sammler seine erste Runde noch nicht beendet hat.
# Ohne ihn stuende dort "Wird gestartet", also eine Behauptung ueber einen
# Dienst, ueber den wir nichts wissen.
KNOTEN_UNGEFRAGT = "ungefragt"


def _indizes(knoten: Knoten, zeitlimit: float) -> Optional[Dict]:
    """Wie weit die Indizes sind -- txindex und der Blockfilter.

    WARUM DAS SICHTBAR GEHOERT: SatoshiCortex schaltet beide waehrend des
    Erstabgleichs AUS, damit die Platte nicht doppelt beschrieben wird, und
    danach wieder ein. Core baut sie dann nach -- und das dauert bei einer
    fertigen Kette Stunden. In dieser Zeit findet die Transaktionssuche
    nichts, und Wallet-Software, die sich anschliessen will, bekommt keine
    Antwort.

    Bis zum 08.09.2026 stand darueber NIRGENDS etwas. Der Betreiber hat es von
    selbst vermutet ("vielleicht liegt es daran, dass das nicht geklappt
    hat") -- und genau das ist der Punkt: eine Anwendung, in der man raten
    muss, was ihr Knoten gerade tut, erklaert ihn nicht.

    None heisst "nicht abrufbar", ein leeres Verzeichnis "kein Index aktiv"
    (so ist es waehrend des Abgleichs). Beides ist etwas anderes als "fertig".
    """
    try:
        roh = knoten.ruf("getindexinfo", zeitlimit=zeitlimit)
    except (NichtErreichbar, RpcFehler) as fehler:
        log.debug("getindexinfo nicht moeglich: %s", fehler)
        return None
    if not isinstance(roh, dict):
        return None
    return {
        name: {"fertig": bool(w.get("synced")),
               "hoehe": int(w.get("best_block_height") or 0)}
        for name, w in roh.items() if isinstance(w, dict)
    }


def lage_mit_grund(knoten: Knoten, peers=None, gesamt=None) -> tuple:
    """(Lage, Grund) statt nur (Lage).

    Der Grund ist der ganze Punkt. Vorher gab es nur "Lage oder None", und
    None hiess sowohl "laeuft nicht" als auch "kommt gerade nicht zum
    Antworten". Die Oberflaeche machte daraus "bitcoind antwortet noch nicht"
    und setzte den Fortschritt auf "—" -- es sah aus, als starte der Dienst
    im Minutentakt neu. Er startete nie neu.

    Waehrend des Erstabgleichs schreibt Core den chainstate weg, sobald der
    dbcache voll ist, und haelt dabei cs_main. getblockchaininfo braucht
    dieselbe Sperre und wartet. Auf einer langsamen Ablage sind das Sekunden
    bis Minuten -- in denen der Knoten auch ueber P2P nicht zu sprechen ist.
    """
    lage = kettenlage(knoten, peers, gesamt)
    if lage:
        return lage, KNOTEN_DA

    # Nur wenn nichts kam, wird nach dem GRUND gefragt -- also genau dann,
    # wenn ohnehin nichts zu tun ist. Der erste Anlauf fragte immer zuerst
    # nach dem Grund und holte die Lage danach: zwei Aufrufe im Normalfall
    # statt einem, und er ging an kettenlage vorbei. Ein Test, der kettenlage
    # ersetzte, sah davon nichts mehr und fiel um.
    #
    # Kurze Leine: den Grund zu erfahren ist nicht wichtig genug, um dafuer
    # noch einmal das volle Zeitlimit zu warten.
    try:
        knoten.ruf("getblockchaininfo", zeitlimit=2)
    except Beschaeftigt:
        return None, KNOTEN_BESCHAEFTIGT
    except (NichtErreichbar, RpcFehler):
        return None, KNOTEN_WEG
    return None, KNOTEN_WEG
