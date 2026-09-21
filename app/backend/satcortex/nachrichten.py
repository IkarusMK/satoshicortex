"""Nachrichten zu Bitcoin und Lightning -- geholt, gefiltert, verlinkt.

Kein neuer Dienst, kein neuer Container: das hier laeuft als Hintergrundtakt
im bestehenden app-Prozess, neben dem, der nach neuen Fassungen sieht. Es
benutzt denselben Weg nach draussen -- Tors HTTP-Tunnel -- und aus demselben
Grund:

    Ein Feedleser auf dem eigenen Rechner erzaehlt jedem Verlag taeglich, dass
    sich hinter dieser Anschlusskennung jemand fuer Bitcoin interessiert, und
    ueber Monate auch, wann er wach ist. Ueber Tor sieht die Gegenseite einen
    Ausgangsknoten.

Geholt werden RSS- und Atom-Feeds, keine abgekratzten Webseiten. Ein Feed ist
ein Angebot; ein HTML-Grabber ist in drei Monaten kaputt, weil jemand sein
Seitenlayout geaendert hat.

ZWEI ARTEN VON QUELLE, und das ist die Achse, an der alles haengt -- gemessen
am 06.09.2026, nicht geschaetzt:

    BTC-ECHO       25 von 25 Beitraegen zum Thema   100 %
    Bitcoin Optech 10 von 10                        100 %
    Blocktrainer   28 von 30                         93 %
    Cointelegraph  24 von 30                         80 %
    ----------------------------------------------------
    CNBC            3 von 30                         10 %
    WSJ Markets     1 von 20                          5 %
    Guardian        1 von 40   (Fehltreffer)        2,5 %
    Handelsblatt    0 von 50                          0 %
    Die Zeit        0 von 15                          0 %
    Welt            0 von 30                          0 %
    BBC             0 von 70                          0 %

Fachquellen kommen ungefiltert herein -- alles, was sie schreiben, ist Thema.
Leitmedien brauchen einen Filter, sonst kippen zweihundert Artikel taeglich
ueber Tarifrunden und Bundesliga in den Feed. Und sie bleiben ab Werk AUS: bei
null Prozent gemessener Ausbeute waere ein leerer Reiter der erste Eindruck.
"""
from __future__ import annotations

import html
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405

from . import abweisung
from dataclasses import dataclass
from typing import (Callable, Dict, List, Optional, Sequence,
                    Tuple)

log = logging.getLogger(__name__)

# Wie viel von einem Feed gelesen wird.
#
# Die Versionsabfrage begnuegt sich mit 512 kB. Fuer Feeds ist das ZU WENIG,
# und zwar messbar: Bitcoin Optech liefert 665 kB, weil dort die vollen
# Artikeltexte mitkommen. Mit dem kleineren Wert waere die Antwort mitten im
# XML abgeschnitten und die Quelle haette NIE geparst -- ein stiller Ausfall,
# der wie "die schreiben gerade nichts" ausgesehen haette.
HOECHSTLAENGE = 2 * 1024 * 1024

# Grosszuegig, weil der Weg ueber drei fremde Rechner geht. Dieselbe
# Begruendung wie bei der Versionsabfrage, wo 15 Sekunden ein Muenzwurf waren.
ZEITSPERRE_SEKUNDEN = 45

# Stuendlich. Haeufiger bringt nichts -- auch eine Fachredaktion schreibt
# keine zwei Artikel je Stunde -- und faellt der Gegenseite nur auf.
INTERVALL_SEKUNDEN = 3600

# Wie viele Beitraege je Quelle hoechstens uebernommen werden. Verhindert,
# dass eine Quelle mit hundert Eintraegen den Feed allein fuellt.
JE_QUELLE = 40

# Wie lang der uebernommene Anriss hoechstens ist.
#
# Nicht aus Platzgruenden: manche Feeds liefern den GANZEN Artikel im
# <content:encoded>. Den vollstaendig anzuzeigen waere ein Nachdruck, und der
# steht uns nicht zu -- wir zeigen die Ueberschrift, ein paar Zeilen, und
# verlinken zur Quelle. Genau so war es auch gewuenscht: draufklicken und dort
# lesen.
ANRISS_ZEICHEN = 320


# ---------------------------------------------------------------- Quellen ---

@dataclass(frozen=True)
class Quelle:
    """Eine Nachrichtenquelle.

    `laender` sagt, fuer wen sie regional ist. Leer heisst international.
    Sortiert wird spaeter danach, in welchem Land der KNOTEN steht -- den Wert
    kennt die Anwendung aus der Weltkarte bereits (karte.eigener_ort), es
    braucht dafuer keine neue Einstellung und keine Frage im Assistenten.
    """
    kennung: str
    name: str
    adresse: str
    sprache: str                       # "de" | "en"
    art: str                           # "fach" | "leit" | "direkt"
    laender: Tuple[str, ...] = ()
    bezahlschranke: bool = False
    ab_werk: bool = True
    hinweis: str = ""
    # Steht die Quelle hinter Cloudflare?
    #
    # Gemessen am 06.09.2026 an den Antwortkopfzeilen (Server / CF-Ray).
    # Cloudflare behandelt Tor-Ausgangsknoten misstrauisch und weist sie
    # haeufig ab -- und wir fragen ausschliesslich ueber Tor. Auf des Betreibers
    # Knoten kam deshalb von 26 eingeschalteten Fachquellen genau EINE an.
    #
    # Es ist kein sicheres Nein: manche Betreiber lassen Tor durch. Aber es
    # ist der Unterschied zwischen "kommt vermutlich an" und "kann klappen",
    # und das gehoert dem Nutzer gesagt, statt dass er eine leere Liste sieht
    # und die Software fuer kaputt haelt.
    hinter_cloudflare: bool = False
    # Seit welcher Fassung es diese Quelle gibt.
    #
    # Gebraucht fuer die Umstellung unten: wer seine Auswahl gespeichert hat,
    # bevor es eine Quelle gab, hat sie nicht abgewaehlt -- er kannte sie nur
    # nicht. Ohne diese Unterscheidung bliebe jede spaeter hinzugefuegte
    # Quelle bei bestehenden Nutzern fuer immer aus. Genau das ist am
    # 06.09.2026 auf dem Knoten im Betrieb passiert: vier neue Quellen, alle "aus".
    seit: str = ""

    @property
    def gefiltert(self) -> bool:
        """Nur Leitmedien werden gefiltert. Fachquellen sind ganz Thema."""
        return self.art == "leit"


# Die mitgelieferte Liste. Jede Zeile wurde am 06.09.2026 abgerufen und
# gezaehlt; die Quote steht im Kommentar. Wer eigene Quellen will, traegt sie
# in den Einstellungen nach -- diese Liste ist ein Vorschlag, keine Vorgabe.
QUELLEN: Tuple[Quelle, ...] = (
    # ============ FACHQUELLEN =========================================
    # Ungefiltert: alles, was sie schreiben, ist Thema. Die Quote hinter
    # jeder Zeile wurde am 06.09.2026 mit tools/quellen_pruefen.py gemessen.

    # -- international, englisch. Der Rueckfall fuer die ganze Welt: es
    #    gibt in den meisten Laendern keine eigene Bitcoin-Presse, aber
    #    ueberall Leser dieser hier.
    Quelle("optech", "Bitcoin Optech", "https://bitcoinops.org/feed.xml",
           "en", "fach",
           hinweis="Woechentlich, technisch -- fuer Knotenbetreiber."),  # 100 %
    Quelle("bitcoincom", "Bitcoin.com News", "https://news.bitcoin.com/feed/",
           "en", "fach",
           hinter_cloudflare=True),                                            # 100 %    # Ohne Cloudflare -- kommt ueber Tor durch, wo die meisten scheitern.
    Quelle("nobsbitcoin", "NoBSBitcoin", "https://www.nobsbitcoin.com/rss/",
           "en", "fach", seit="0.44.2"),                                            # 100 %
    Quelle("cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss",
           "en", "fach",
           hinter_cloudflare=True),                                            #  80 %
    Quelle("theblock", "The Block", "https://www.theblock.co/rss.xml",
           "en", "fach",
           hinter_cloudflare=True),                                            #  75 %
    Quelle("coindesk", "CoinDesk",
           "https://www.coindesk.com/arc/outboundfeeds/rss?outputType=xml",
           "en", "fach"),                                            # s.u.
    Quelle("decrypt", "Decrypt", "https://decrypt.co/feed",
           "en", "fach", ab_werk=False,
           hinter_cloudflare=True),                             #  57 %

    # -- deutsch: DE AT CH LI LU
    Quelle("btcecho", "BTC-ECHO", "https://www.btc-echo.de/feed/",
           "de", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("bitcoinblog", "Bitcoinblog", "https://bitcoinblog.de/feed/",
           "de", "fach"),                                            # 100 %
    Quelle("blocktrainer", "Blocktrainer",
           "https://www.blocktrainer.de/feed.xml", "de", "fach"),    #  90 %
    Quelle("coinkurier", "Coinkurier", "https://coinkurier.de/feed/",
           "de", "fach", seit="0.44.2"),                                            #  68 %

    # -- franzoesisch: FR BE CH CA MC -- und der ganze frankophone Raum
    #    Afrikas. Genau der Fall, an dem sich das entschieden hat: wer in
    #    Algerien sitzt, bekommt hiermit etwas Lesbares statt Blocktrainer.
    Quelle("journalducoin", "Journal du Coin", "https://journalducoin.com/feed/",
           "fr", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("cryptoast", "Cryptoast", "https://cryptoast.fr/feed/",
           "fr", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("bitcoinfr", "Bitcoin.fr", "https://bitcoin.fr/feed/",
           "fr", "fach"),                                            # 100 %

    # -- spanisch: ES und fast ganz Lateinamerika
    Quelle("diariobitcoin", "DiarioBitcoin", "https://www.diariobitcoin.com/feed/",
           "es", "fach"),                                            # 100 %
    Quelle("bit2me", "Bit2Me News", "https://news.bit2me.com/feed",
           "es", "fach",
           hinter_cloudflare=True),                                            #  92 %

    # -- portugiesisch: BR PT AO MZ ...
    Quelle("livecoins", "Livecoins", "https://livecoins.com.br/feed/",
           "pt", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("criptofacil", "CriptoFacil", "https://www.criptofacil.com/feed/",
           "pt", "fach",
           hinter_cloudflare=True),                                            # 100 %

    # -- weitere Sprachraeume
    Quelle("cryptonomist", "The Cryptonomist", "https://cryptonomist.ch/feed/",
           "it", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("cryptosmart", "CryptoSmart", "https://cryptosmart.it/feed/",
           "it", "fach", seit="0.44.2"),                                            # 100 %
    Quelle("bitcoinmagnl", "Bitcoin Magazine NL",
           "https://bitcoinmagazine.nl/feed/", "nl", "fach",
           hinter_cloudflare=True),        # 100 %
    Quelle("cryptoinsiders", "Crypto Insiders",
           "https://www.crypto-insiders.nl/feed/", "nl", "fach",
           hinter_cloudflare=True),    # 100 %
    Quelle("uzmancoin", "Uzmancoin", "https://uzmancoin.com/feed/",
           "tr", "fach",
           hinter_cloudflare=True),                                            # 100 %
    Quelle("koinbulteni", "Koin Bulteni", "https://koinbulteni.com/feed",
           "tr", "fach",
           hinter_cloudflare=True),                                            #  83 %
    Quelle("forklog", "ForkLog", "https://forklog.com/feed/",
           "ru", "fach"),                                            #  60 %
    Quelle("bithub", "Bithub", "https://bithub.pl/feed/",
           "pl", "fach",
           hinter_cloudflare=True),                                            #  50 %
    Quelle("coinpost", "CoinPost", "https://coinpost.jp/?feed=rss2",
           "ja", "fach"),                                            # 100 %
    Quelle("coinchoice", "CoinChoice", "https://coinchoice.net/feed/",
           "ja", "fach"),                                            # 100 %
    Quelle("neweconomy", "\u3042\u305f\u3089\u3057\u3044\u7d4c\u6e08",
           "https://www.neweconomy.jp/feed", "ja", "fach"),          # 100 %
    Quelle("tokenpostkr", "TokenPost", "https://www.tokenpost.kr/rss",
           "ko", "fach",
           hinter_cloudflare=True),                                            #  60 %
    Quelle("blockmedia", "Blockmedia", "https://www.blockmedia.co.kr/feed",
           "ko", "fach", seit="0.44.2"),
    Quelle("coingape", "CoinGape", "https://coingape.com/feed/",
           "en", "fach", ab_werk=False,
           hinweis="Schwerpunkt Indien und Asien.",
           hinter_cloudflare=True),                 #  95 %

    # ============ LEITMEDIEN ==========================================
    # Gefiltert, und ab Werk AUS. Begruendung im Modulkopf: gemessene
    # Ausbeute zwischen 0 und 10 Prozent.
    Quelle("cnbc", "CNBC",
           "https://www.cnbc.com/id/10000664/device/rss/rss.html",
           "en", "leit", ab_werk=False),                             #  10 %
    Quelle("wsj", "Wall Street Journal",
           "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
           "en", "leit", bezahlschranke=True, ab_werk=False),        #   5 %
    Quelle("handelsblatt", "Handelsblatt",
           "https://feeds.cms.handelsblatt.com/schlagzeilen",
           "de", "leit", bezahlschranke=True, ab_werk=False,
           hinter_cloudflare=True),        #   0 %
    Quelle("zeit", "Die Zeit", "https://newsfeed.zeit.de/index",
           "de", "leit", bezahlschranke=True, ab_werk=False),        #   0 %
    Quelle("welt", "Welt", "https://www.welt.de/feeds/latest.rss",
           "de", "leit", bezahlschranke=True, ab_werk=False),        #   0 %
)


# Welches Land welche Sprache liest.
#
# NICHT je Land eine Quellenliste -- das waeren 241 Listen, die niemand
# pflegen kann und die zur Haelfte leer waeren. Es gibt keine algerische
# Bitcoin-Presse; es gibt eine franzoesische, und Algerien liest
# franzoesisch. Ueber die Sprache wird die Welt abgedeckt, nicht ueber die
# Grenze.
#
# Was hier nicht steht, bekommt die internationalen englischen Quellen. Das
# ist keine Notloesung, sondern die Lage: Bitcoin-Berichterstattung ist
# ueberwiegend englisch, und in den meisten Laendern der Welt ist sie
# ausschliesslich englisch.
SPRACHE_JE_LAND: Dict[str, str] = {}


def _eintragen(sprache: str, laender: str) -> None:
    for k in laender.split():
        SPRACHE_JE_LAND[k] = sprache


_eintragen("de", "DE AT CH LI LU")
_eintragen("fr", "FR MC BE LU DZ MA TN SN CI ML BF NE TD CG CD GA CM BJ TG "
                 "GN MG HT KM DJ CF MU SC BI RW VU NC PF")
_eintragen("es", "ES MX AR CO CL PE VE EC GT CU BO DO HN PY SV NI CR PA UY "
                 "GQ PR")
_eintragen("pt", "PT BR AO MZ CV GW ST TL")
_eintragen("it", "IT SM VA")
_eintragen("nl", "NL SR AW CW SX BQ")
_eintragen("tr", "TR")
_eintragen("ru", "RU BY KZ KG TJ AM MD")
_eintragen("pl", "PL")
_eintragen("ja", "JP")
_eintragen("ko", "KR")


def sprache_fuer(land: Optional[str]) -> str:
    """Welche Sprache zu einem Laenderkuerzel gehoert. Vorgabe: englisch."""
    return SPRACHE_JE_LAND.get((land or "").upper(), "en")


def fuer_land(land: Optional[str],
              quellen: Sequence[Quelle] = QUELLEN) -> List[Quelle]:
    """Die Quellen fuer einen Standort -- regionale zuerst, dann international.

    Die englischen Quellen sind IMMER dabei, auch bei fremder Sprache: sie
    sind der Grundstock, die regionalen kommen obendrauf. Wer in Algerien
    sitzt, bekommt franzoesische UND internationale -- nicht nur die eine
    oder die andere.
    """
    sp = sprache_fuer(land)
    regional = [q for q in quellen if q.sprache == sp and sp != "en"]
    international = [q for q in quellen if q.sprache == "en"]
    rest = [q for q in quellen
            if q not in regional and q not in international]
    return regional + international + rest


NICHT_VERFUEGBAR: Dict[str, str] = {
    "Reuters": "hat RSS eingestellt und weist Nicht-Browser mit 401 ab",
    "AP News": "weist Nicht-Browser mit 403 ab",
    "Bitcoin Magazine": "weist Nicht-Browser mit 403 ab",
}


# ----------------------------------------------------------------- Filter ---

# Der enge Filter -- die Voreinstellung.
#
# Jedes Wort hier ist EINDEUTIG. Das ist bei Leitmedien der ganze Trick:
# "Mining" allein trifft Kohle und Lithium, "Lightning" allein trifft das
# Gewitter, "Node" trifft jede Netzwerkmeldung. Solche Woerter zaehlen
# deshalb nur in Verbindung mit Bitcoin (siehe _VERBUNDEN).
_EINDEUTIG = re.compile(
    r"\b(bitcoin\w*|btc|satoshi\w*|halving|mempool|taproot|segwit|"
    r"lnd|hodl|blockhalbierung)\b", re.I)

# Und dasselbe in Schriften ohne lateinische Buchstaben.
#
# Am 06.09.2026 zweimal in dieselbe Falle getreten: CoinPost kam mit 25 %
# durch die Messung, weil Japanisch ビットコイン schreibt und nicht
# "Bitcoin" -- und danach Blockmedia mit 30 %, weil Koreanisch 비트코인
# schreibt. Beides waren gute Quellen und ein schlechtes Suchmuster.
#
# \b funktioniert hier nicht: diese Schriften kennen keine Wortgrenzen im
# Sinne der Regex-Bibliothek. Die Begriffe sind lang genug, dass es ohne geht.
_SCHRIFTEN = re.compile(
    "ビットコイン|サトシ|ライトニング|"                    # ja
    "비트코인|사토시|라이트닝|"                            # ko
    "比特幣|比特币|"                                       # zh
    "بيتكوين|"                                             # ar
    "बिटकॉइन|"                                                 # hi
    "บิทคอยน์")                                              # th

# Die Nachbarschaft in denselben Schriften -- fuer den weiten Filter.
_SCHRIFTEN_WEIT = re.compile(
    "仮想通貨|暗号資産|ブロックチェーン|"                  # ja
    "암호화폐|가상자산|블록체인|코인|스테이블코인|"        # ko
    "加密货币|加密貨幣|區塊鏈|区块链|"                     # zh
    "عملات رقمية|تشفير|"                                   # ar
    "क्रिप्टो")                                                  # hi

# Mehrwortbegriffe, die fuer sich stehen.
_VERBUNDEN = re.compile(
    r"(lightning[- ]?(network|netzwerk|node|knoten)|"
    r"krypto[- ]?mining|crypto[- ]?mining|"
    r"digitale[sn]? gold)", re.I)

# Der weite Filter -- der Schalter "auch Krypto allgemein".
#
# Nimmt die Nachbarschaft dazu. Gemessen an BTC-ECHO ist das genau der
# Unterschied zwischen "Bitcoin" und "auch Ethereum und Zcash".
_WEIT = re.compile(
    r"\b(krypto\w*|crypto\w*|blockchain|ethereum|eth|altcoin\w*|"
    r"stablecoin\w*|defi|mica|kryptoboerse|coinbase|binance|"
    r"digital assets?)\b", re.I)


def passt(text: str, weit: bool = False) -> bool:
    """Ist dieser Beitrag Thema?

    Wird NUR auf Leitmedien angewandt. Bei einer Fachquelle ist ohnehin alles
    Thema, und ein Filter wuerde dort nur Beitraege schlucken, die das Wort
    zufaellig nicht in der Ueberschrift tragen.
    """
    if (_EINDEUTIG.search(text) or _VERBUNDEN.search(text)
            or _SCHRIFTEN.search(text)):
        return True
    return bool(weit and (_WEIT.search(text)
                          or _SCHRIFTEN_WEIT.search(text)))


# ------------------------------------------------------------------ Holen ---

# Was ein Feed niemals braucht -- und was ein Angreifer braeuchte.
#
# Pythons eingebauter XML-Leser laesst sich mit einer verschachtelten
# Entity-Deklaration von wenigen Kilobyte dazu bringen, den Arbeitsspeicher
# vollzuschreiben ("billion laughs"). Der uebliche Rat lautet, dafuer
# defusedxml einzubauen.
#
# Gemessen am 06.09.2026: KEINE der acht echten Quellen enthaelt eine DTD
# oder Entity-Deklaration -- RSS und Atom brauchen so etwas nicht. Ein Riegel
# davor ist deshalb strenger als die Abhaengigkeit und kostet keine.
_GEFAEHRLICH = re.compile(rb"<!DOCTYPE|<!ENTITY", re.I)


class Abgewiesen(Exception):
    """Die Antwort war keine, mit der wir weiterarbeiten."""


def _oeffner(proxy: Optional[str]):
    return urllib.request.build_opener(urllib.request.ProxyHandler(
        {"https": proxy, "http": proxy} if proxy else {}))


def hole(adresse: str, proxy: Optional[str] = None,
         hoechstlaenge: int = HOECHSTLAENGE) -> bytes:
    """Einen Feed abrufen. Wirft Abgewiesen, wenn daraus nichts wird."""
    anfrage = urllib.request.Request(adresse, headers={
        "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
        # Kein Kennzeichen, das den Betreiber wiedererkennbar macht. Ueber Tor
        # waere ein individueller Name genau die Spur, die der Umweg vermeidet.
        "User-Agent": "satcortex",
    })
    try:
        with _oeffner(proxy).open(anfrage,
                                  timeout=ZEITSPERRE_SEKUNDEN) as antwort:
            roh = antwort.read(hoechstlaenge)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as f:
        raise Abgewiesen(_deutung(f, proxy)) from f
    if _GEFAEHRLICH.search(roh):
        raise Abgewiesen("Die Antwort enthaelt eine DTD -- kein Feed tut das.")
    return roh


def _deutung(fehler: BaseException, proxy: Optional[str]) -> str:
    """Aus dem rohen Fehler eine Zeile machen, mit der man etwas anfangen kann.

    Wichtig ist die Unterscheidung, wer abgewiesen hat: der eigene Tor, den
    es vielleicht gar nicht gibt -- oder die Gegenseite. Das ist derselbe
    Befund wie bei der Versionsabfrage, wo tagelang "Noch nicht nachgesehen"
    stand, obwohl jedes Mal gefragt wurde.
    """
    grund = getattr(fehler, "reason", None) or fehler
    code = getattr(fehler, "code", None)
    erklaerung = abweisung.deute_http(code, "Die Quelle")
    if erklaerung:
        return erklaerung
    if isinstance(grund, ConnectionRefusedError):
        return (f"Der Tor-HTTP-Tunnel ({proxy}) nimmt keine Verbindungen an. "
                "Laeuft Tor -- und steht HTTPTunnelPort in seiner torrc?")
    return f"{type(fehler).__name__}: {fehler}"

# --------------------------------------------------------------- Zerlegen ---

ATOM = "{http://www.w3.org/2005/Atom}"

# Feeds liefern ihren Anriss als HTML. Wir zeigen ihn als TEXT -- immer.
#
# Das ist keine Bequemlichkeit, sondern die Regel: fremder Text wird nie als
# HTML gezeichnet. Und es erledigt nebenbei den zweiten Punkt, denn ein
# Vorschaubild von einem fremden Server ist ein Zaehlpixel. Es wuerde die
# echte Adresse des Lesers an den Verlag melden und den ganzen Tor-Umweg in
# derselben Sekunde zunichtemachen. Kein <img> ueberlebt diesen Schritt.
_MARKE = re.compile(r"<[^>]{0,2000}>")
_LEERRAUM = re.compile(r"\s+")


def _text(roh: Optional[str]) -> str:
    """Aus einem Feld eines Feeds schlichten Text machen."""
    if not roh:
        return ""
    ohne = _MARKE.sub(" ", roh)
    # Zweimal aufloesen: manche Feeds verpacken ihr HTML doppelt, sodass
    # nach dem ersten Durchgang noch &lt;p&gt; dasteht. Danach noch einmal
    # Marken entfernen, sonst stuende die aufgeloeste Marke im Text.
    ohne = html.unescape(html.unescape(ohne))
    ohne = _MARKE.sub(" ", ohne)
    return _LEERRAUM.sub(" ", ohne).strip()


# Was Verlage ihren Anrissen anhaengen.
#
# Am 06.09.2026 an den echten Feeds abgelesen, nicht ausgedacht:
#
#   BTC-ECHO    "... betroffen. Source: BTC-ECHO BTC-ECHO"
#   Cryptoast   "... est apparu en premier sur Cryptoast ."
#   Livecoins   "... Siga o Livecoins no Facebook , Twitter , Instagram ..."
#
# Die ersten beiden sind Standard-Nachspaenne von WordPress, den es in jeder
# Sprache gibt; der dritte ist ein Aufruf, dem Verlag zu folgen. Alle drei
# sagen nichts ueber die Meldung -- und die Quelle steht bei uns ohnehin in
# einer eigenen Zeile darunter.
# Der WordPress-Nachspann. Er ist NIE Fliesstext: "The post <Titel>
# appeared first on <Blatt>." steht unter jedem Beitrag eines solchen
# Systems und sagt nichts ueber die Meldung.
#
# Er faengt mit seinem eigenen SATZANFANG an -- wer erst ab "est apparu"
# schneidet, laesst "L'article <Titel>" stehen. Genau das war am 06.09.2026
# bei Cryptoast im Bild zu sehen.
_ANFANG = (r"\b(?:der\s+(?:beitrag|artikel)|the\s+post|l\W{0,2}article"
           r"|la\s+entrada|el\s+art\u00edculo|o\s+post|o\s+artigo"
           r"|l\W{0,2}articolo)\b[^.]{0,300}?")
_MARKE_WP = (r"\b(?:erschien\s+zuerst\s+auf|appeared\s+first\s+on"
             r"|est\s+apparu\s+en\s+premier\s+sur"
             r"|apareci\u00f3\s+primero\s+en|apareceu\s+primeiro\s+em"
             r"|compare\s+prima\s+su)\b.*")
_NACHSPANN_SICHER = re.compile(
    f"(?:{_ANFANG}{_MARKE_WP}|{_MARKE_WP}"
    # Der Aufruf, dem Verlag zu folgen -- ebenso eindeutig.
    r"|\b(?:siga|segui|folge|follow)\b[^.]{0,80}?"
    r"\b(?:facebook|twitter|instagram|youtube|telegram)\b.*"
    r")\Z", re.I | re.S)

# Diese hier sind MEHRDEUTIG: "Quelle: dpa meldet ..." kann sehr wohl der
# Anfang einer Meldung sein. Deshalb nur schneiden, wenn es hinten steht.
_NACHSPANN_UNSICHER = re.compile(
    r"\b(?:source|quelle|fuente|fonte)\s*:\s*.*\Z", re.I | re.S)


def _ohne_nachspann(text: str, quellenname: str = "") -> str:
    """Den Verlagsnachspann abschneiden.

    Zwei Stufen, weil nicht jeder Nachspann gleich sicher ist -- siehe die
    beiden Muster oben. Der erste Entwurf hatte nur eine Positionsregel fuer
    beide, und die warf den deutschen Nachspann weg: dessen Satzanfang liegt
    bei einem kurzen Anriss VOR der Mitte, obwohl er eindeutig Nachspann ist.
    """
    treffer = _NACHSPANN_SICHER.search(text)
    if treffer:
        text = text[:treffer.start()].strip()
    treffer = _NACHSPANN_UNSICHER.search(text)
    if treffer and treffer.start() > len(text) * 0.5:
        text = text[:treffer.start()].strip()
    # Und ein blosser Namensnachklapp ("... BTC-ECHO BTC-ECHO").
    name = (quellenname or "").strip()
    while name and text.lower().rstrip(" .,\u2013-").endswith(name.lower()):
        text = text.rstrip(" .,\u2013-")[:-len(name)].strip()
    return text.strip(" \u2013-\u00b7|")


def _kuerzen(text: str, zeichen: int = ANRISS_ZEICHEN) -> str:
    """Auf Anrisslaenge bringen, aber an einer Wortgrenze."""
    if len(text) <= zeichen:
        return text
    schnitt = text[:zeichen]
    luecke = schnitt.rfind(" ")
    if luecke > zeichen * 0.6:
        schnitt = schnitt[:luecke]
    return schnitt.rstrip(" ,;:-") + " …"


def _zeitpunkt(roh: Optional[str]) -> Optional[int]:
    """Datum eines Beitrags als Unix-Sekunden. None, wenn unlesbar.

    RSS schreibt RFC 822 ("Sat, 06 Sep 2026 11:20:00 +0200"), Atom schreibt
    ISO 8601 ("2026-09-06T11:20:00Z"). Beide kommen vor, oft im selben Feed.
    """
    if not roh:
        return None
    roh = roh.strip()
    try:
        from email.utils import parsedate_to_datetime
        return int(parsedate_to_datetime(roh).timestamp())
    except Exception:                                            # nosec B902
        pass
    try:
        import datetime as _dt
        return int(_dt.datetime.fromisoformat(
            roh.replace("Z", "+00:00")).timestamp())
    except Exception:                                            # nosec B902
        return None


def _verweis(roh: Optional[str]) -> str:
    """Nur http und https. Sonst nichts.

    Ein Feed ist fremder Text, und ein Verweis daraus landet in einem
    Anker-Element. Ohne diese Pruefung stuende dort, was der Verlag
    hineinschreibt -- javascript: eingeschlossen.
    """
    if not roh:
        return ""
    ziel = roh.strip()
    try:
        teile = urllib.parse.urlsplit(ziel)
    except ValueError:
        return ""
    if teile.scheme.lower() not in ("http", "https") or not teile.netloc:
        return ""
    return ziel


@dataclass
class Beitrag:
    """Eine Meldung. Das, was am Ende in der Liste steht."""
    kennung: str
    quelle: str
    quellenname: str
    titel: str
    anriss: str
    verweis: str
    zeitpunkt: Optional[int]
    sprache: str = "en"
    bezahlschranke: bool = False

    def als_dict(self) -> Dict:
        return {
            "kennung": self.kennung, "quelle": self.quelle,
            "quellenname": self.quellenname, "titel": self.titel,
            "anriss": self.anriss, "verweis": self.verweis,
            "zeitpunkt": self.zeitpunkt, "sprache": self.sprache,
            "bezahlschranke": self.bezahlschranke,
        }


def _finde(stueck: ET.Element, *namen: str) -> Optional[str]:
    """Das erste vorhandene Feld -- in RSS wie in Atom."""
    for name in namen:
        el = stueck.find(name)
        if el is not None and (el.text or "").strip():
            return el.text
    return None


def _lies_xml(roh: bytes) -> ET.Element:
    """XML einlesen -- aber erst, nachdem der Riegel gehalten hat.

    Pythons ElementTree laesst sich mit einer verschachtelten
    Entity-Deklaration von wenigen Kilobyte dazu bringen, den Arbeitsspeicher
    vollzuschreiben ("billion laughs"). Der uebliche Rat ist defusedxml.

    Gemessen am 06.09.2026: KEINE der acht echten Quellen enthaelt eine DTD --
    RSS und Atom brauchen so etwas nicht. Der Riegel davor ist deshalb
    strenger als die Abhaengigkeit und kostet keine.

    Er steht HIER und nicht nur in hole(): zerlege() ist oeffentlich, und ein
    Aufruf mit Bytes aus einer anderen Quelle waere sonst ungeschuetzt. Ein
    Schutz, der an der Aufrufreihenfolge haengt, ist keiner.
    """
    if _GEFAEHRLICH.search(roh):
        raise Abgewiesen("Die Antwort enthaelt eine DTD -- kein Feed tut das.")
    # Der Riegel oben ist die Gegenmassnahme -- Begruendung im Text.
    return ET.fromstring(roh)  # nosec B314


def zerlege(roh: bytes, quelle: Quelle,
            weit: bool = False) -> List[Beitrag]:
    """Aus einem abgerufenen Feed die Beitraege machen.

    Gefiltert wird nur bei Leitmedien. Bei einer Fachquelle waere ein Filter
    schaedlich: er schluckte jeden Beitrag, der das Stichwort zufaellig nicht
    in der Ueberschrift traegt -- und bei einer Bitcoin-Redaktion ist das
    haeufig, weil dort niemand jeden Titel mit "Bitcoin" beginnen laesst.
    """
    wurzel = _lies_xml(roh)
    stuecke = (wurzel.findall(".//item")
               or wurzel.findall(f".//{ATOM}entry"))

    beitraege: List[Beitrag] = []
    for stueck in stuecke[:JE_QUELLE]:
        titel = _text(_finde(stueck, "title", f"{ATOM}title"))
        if not titel:
            continue

        # Der Verweis steht in RSS im Text, in Atom im href-Merkmal.
        ziel = _verweis(_finde(stueck, "link"))
        if not ziel:
            for el in stueck.findall(f"{ATOM}link"):
                art = el.get("rel") or "alternate"
                if art == "alternate":
                    ziel = _verweis(el.get("href"))
                    if ziel:
                        break
        if not ziel:
            # Ohne Ziel ist die Meldung wertlos: der ganze Sinn ist das
            # Draufklicken und beim Verlag weiterlesen.
            continue

        roh_anriss = _finde(
            stueck, "description", f"{ATOM}summary", f"{ATOM}content",
            "{http://purl.org/rss/1.0/modules/content/}encoded")
        # Erst den Nachspann weg, DANN kuerzen -- andersherum bliebe
        # er stehen, sobald der Text ohnehin abgeschnitten wird.
        anriss = _kuerzen(_ohne_nachspann(_text(roh_anriss),
                                          quelle.name))

        if quelle.gefiltert and not passt(f"{titel} {anriss}", weit):
            continue

        kennung = (_finde(stueck, "guid", f"{ATOM}id") or ziel).strip()
        beitraege.append(Beitrag(
            kennung=f"{quelle.kennung}:{kennung}"[:400],
            quelle=quelle.kennung,
            quellenname=quelle.name,
            titel=_kuerzen(titel, 200),
            anriss=anriss,
            verweis=ziel,
            zeitpunkt=_zeitpunkt(_finde(stueck, "pubDate", "date",
                                        f"{ATOM}published", f"{ATOM}updated")),
            sprache=quelle.sprache,
            bezahlschranke=quelle.bezahlschranke,
        ))
    return beitraege


# ------------------------------------------------------------ Selbstsuche ---

_ALTERNATE = re.compile(r"<link[^>]{0,600}?>", re.I)
_IST_FEED = re.compile(r'type=["\']application/(rss|atom)\+xml["\']', re.I)
_HREF = re.compile(r'href=["\']([^"\']{1,500})["\']', re.I)


def entdecke(seite: str, proxy: Optional[str] = None) -> List[str]:
    """Zu einer Webseite ihre Feed-Adressen finden.

    Eine Seite, die einen Feed anbietet, sagt das selbst im Kopf ihres HTML:
    <link rel="alternate" type="application/rss+xml" href="...">. Das ist der
    vorgesehene Weg -- kein Raten und kein Abkratzen.

    Er traegt aber nicht immer: gemessen am 06.09.2026 deklarieren
    blocktrainer.de, btc-echo.de und zeit.de ihren Feed, handelsblatt.com
    nicht -- dessen Feed liegt auf einem ganz anderen Rechner. Deshalb bleibt
    das Feld fuer die Adresse von Hand bestehen.
    """
    if not _verweis(seite):
        seite = "https://" + seite.lstrip("/")
    try:
        roh = hole(seite, proxy, hoechstlaenge=400_000)
    except Abgewiesen:
        return []
    text = roh.decode("utf-8", "replace")
    gefunden: List[str] = []
    for marke in _ALTERNATE.findall(text):
        if not _IST_FEED.search(marke):
            continue
        treffer = _HREF.search(marke)
        if not treffer:
            continue
        voll = urllib.parse.urljoin(seite, html.unescape(treffer.group(1)))
        if _verweis(voll) and voll not in gefunden:
            gefunden.append(voll)
    return gefunden


# ------------------------------------------------------------- Der Betrieb ---

@dataclass
class Lage:
    """Wie es einer Quelle zuletzt ergangen ist.

    Das ist kein Beiwerk. Eine Quelle, die abgewiesen wird, sieht in einer
    Liste genauso aus wie eine, die gerade nichts schreibt -- und das war
    schon einmal der Fehler: bei der Versionsabfrage stand tagelang "Noch
    nicht nachgesehen", obwohl jedes Mal gefragt wurde. Wer den Grund nicht
    anzeigt, laesst den Nutzer den Fehler bei sich suchen.
    """
    versucht: float = 0.0
    gelungen: float = 0.0
    grund: str = ""
    beitraege: int = 0
    fehlversuche: int = 0

    def als_dict(self) -> Dict:
        return {"versucht": self.versucht or None,
                "gelungen": self.gelungen or None,
                "grund": self.grund, "beitraege": self.beitraege,
                "fehlversuche": self.fehlversuche}


def eigene_quelle(roh: Dict) -> Optional[Quelle]:
    """Aus einem selbst eingetragenen Eintrag eine Quelle machen.

    Selbst eingetragen heisst: der Nutzer bestimmt Name und Adresse. Beides
    ist damit fremder Text und wird geprueft, nicht geglaubt -- die Adresse
    muss http oder https sein, der Name wird beschnitten.
    """
    adresse = _verweis(str(roh.get("adresse", "")))
    if not adresse:
        return None
    name = _text(str(roh.get("name", "")))[:60] or adresse[:60]
    kennung = "eigen:" + re.sub(r"[^a-z0-9]+", "-",
                                adresse.lower())[:60].strip("-")
    return Quelle(kennung=kennung, name=name, adresse=adresse,
                  sprache=str(roh.get("sprache", ""))[:5] or "??",
                  art=("leit" if roh.get("gefiltert") else "fach"))


def _ist_an(quelle: Quelle, abgewaehlt: set, zugewaehlt: set) -> bool:
    """Ist diese Quelle eingeschaltet?

    EINE Stelle fuer die Regel. Vorher stand sie zweimal da -- einmal fuer
    das Holen und einmal fuer die Anzeige --, und zwei Kopien derselben Regel
    laufen frueher oder spaeter auseinander.
    """
    if quelle.kennung in abgewaehlt:
        return False
    if quelle.kennung in zugewaehlt:
        return True
    # Eigene Quellen sind an, sonst haette das Eintragen keine Wirkung.
    return quelle.ab_werk or quelle.kennung.startswith("eigen:")


class Feed:
    """Der Nachrichtentakt. Laeuft im app-Prozess, nicht in einem Container.

    Bewusst ohne eigenen Faden: er wird vom vorhandenen Waechter angestossen,
    genau wie die Versionspruefung. Ein Dienst mehr waere ein Dienst mehr.
    """

    def __init__(self, ablage, proxy_gibt: Callable[[], Optional[str]],
                 zustand) -> None:
        self._ablage = ablage
        self._proxy_gibt = proxy_gibt
        self._zustand = zustand
        self._lagen: Dict[str, Lage] = {}
        self._letzter_lauf = 0.0

    # -------------------------------------------------------- Einstellungen

    def wahl(self) -> Dict:
        """Die Einstellungen, mit Vorgaben aufgefuellt."""
        roh = dict(self._zustand.laden().nachrichtenwahl or {})
        return {
            # AUS, solange niemand eingeschaltet hat.
            "aktiv": bool(roh.get("aktiv", False)),
            # Eng: nur Bitcoin und Lightning. So gewuenscht am 06.09.2026.
            "weit": bool(roh.get("weit", False)),
            "abgewaehlt": self._umstellen(roh)[0],
            "zugewaehlt": self._umstellen(roh)[1],
            "eigene": list(roh.get("eigene") or []),
        }

    @staticmethod
    def _umstellen(roh: Dict) -> Tuple[Optional[List[str]], List[str]]:
        """Was der Nutzer ABGESCHALTET und was er ZUGESCHALTET hat.

        Zwei Mengen, nicht eine Liste der eingeschalteten. Das ist die
        entscheidende Wendung: eine Quelle, die es beim Speichern noch nicht
        gab, steht in keiner Liste eingeschalteter und bliebe damit fuer
        immer aus. Auf dem Knoten im Betrieb waren am 06.09.2026 genau so vier neue
        Quellen tot.

        Gemerkt wird deshalb nur der WIDERSPRUCH zur Werksvorgabe -- in beide
        Richtungen. Alles Uebrige folgt der Vorgabe, auch das, was spaeter
        dazukommt.

        UMSTELLUNG einer alten Auswahl:

        * abgewaehlt = was ab Werk an waere, aber nicht in seiner Liste steht
          -- ohne die Quellen mit `seit`. Wer vor ihrer Zeit gespeichert hat,
          hat sie nicht abgewaehlt, sondern nicht gekannt. Wer sie doch
          abgewaehlt hatte, bekommt sie einmal zurueck; das ist der kleinere
          Schaden.
        * zugewaehlt = was ab Werk aus waere, aber in seiner Liste steht.
          Ohne das verloere er die Leitmedien, die er selbst angeschaltet hat
          -- im Pruefstand an seiner echten Auswahl aufgefallen: CNBC fiel
          heraus.
        """
        if roh.get("abgewaehlt") is not None or roh.get("zugewaehlt") is not None:
            return ([str(k) for k in (roh.get("abgewaehlt") or [])],
                    [str(k) for k in (roh.get("zugewaehlt") or [])])
        alt = roh.get("quellen")
        if alt is None:
            return None, []                 # nie etwas gewaehlt -> ab Werk
        merk = set(alt)
        return ([q.kennung for q in QUELLEN
                 if q.ab_werk and not q.seit and q.kennung not in merk],
                [q.kennung for q in QUELLEN
                 if not q.ab_werk and q.kennung in merk])

    def quellen(self, land: Optional[str] = None) -> List[Quelle]:
        """Welche Quellen jetzt gelten -- mitgelieferte und eigene."""
        w = self.wahl()
        alle = list(fuer_land(land))
        for roh in w["eigene"]:
            q = eigene_quelle(roh)
            if q:
                alle.append(q)
        # Die Werksvorgabe gilt, abzueglich dessen, was der Nutzer
        # abgeschaltet hat. Fachquellen an, Leitmedien aus -- bei null bis
        # zehn Prozent gemessener Ausbeute waere ein leerer Reiter der erste
        # Eindruck. Eigene Quellen sind immer an, sonst haette das Eintragen
        # keinen Sichtbaren Effekt.
        aus = set(w["abgewaehlt"] or ())
        dazu = set(w["zugewaehlt"] or ())
        return [q for q in alle if _ist_an(q, aus, dazu)]

    # --------------------------------------------------------------- Holen

    def faellig(self, jetzt: Optional[float] = None) -> bool:
        jetzt = jetzt if jetzt is not None else time.time()
        return jetzt - self._letzter_lauf >= INTERVALL_SEKUNDEN

    def einmal_holen(self, land: Optional[str] = None,
                     erzwingen: bool = False) -> Dict:
        """Alle gewaehlten Quellen einmal abrufen."""
        jetzt = time.time()
        w = self.wahl()
        if not w["aktiv"]:
            return {"uebersprungen": "aus"}
        if not erzwingen and not self.faellig(jetzt):
            return {"uebersprungen": "zu_frueh"}

        proxy = self._proxy_gibt()
        if not proxy:
            # Dieselbe Regel wie bei der Versionsabfrage: ohne Tor wird nicht
            # gefragt. Ein Feedabruf ueber die eigene Leitung verraet dem
            # Verlag, dass hier jemand einen Bitcoin-Knoten betreibt.
            for q in self.quellen(land):
                self._lagen.setdefault(q.kennung, Lage()).grund = "tor_aus"
            return {"uebersprungen": "tor_aus"}

        self._letzter_lauf = jetzt
        neu = gesamt = 0
        for quelle in self.quellen(land):
            lage = self._lagen.setdefault(quelle.kennung, Lage())
            # Nach Fehlschlaegen zurueckhaltender werden. Auf eine Abfuhr zu
            # haemmern macht sie wahrscheinlicher -- genau das hat am
            # 30.08.2026 das Budget eines Tor-Ausgangsknotens aufgebraucht.
            # Nach einem Fehlschlag nicht sofort, aber auch nicht gleich
            # eine Stunde: Cloudflare weist je nach AUSGANGSKNOTEN ab, und
            # der naechste Versuch nimmt oft einen anderen. Eine Stunde
            # Sperre nach einem einzigen Nein verschenkt genau das.
            # Zehn Minuten, dann eine halbe Stunde, dann zwei Stunden, dann
            # taeglich -- hoeflich genug, dass daraus kein Haemmern wird.
            if lage.fehlversuche and jetzt - lage.versucht < min(
                    600 * 3 ** (lage.fehlversuche - 1), 86400):
                continue
            lage.versucht = jetzt
            try:
                beitraege = zerlege(hole(quelle.adresse, proxy), quelle,
                                    w["weit"])
            except Abgewiesen as fehler:
                lage.grund = str(fehler)
                lage.fehlversuche += 1
                log.info("Nachrichten (%s): %s", quelle.name, fehler)
                continue
            except ET.ParseError as fehler:
                lage.grund = f"Kein lesbarer Feed: {fehler}"
                lage.fehlversuche += 1
                continue
            lage.grund = ""
            lage.fehlversuche = 0
            lage.gelungen = jetzt
            lage.beitraege = len(beitraege)
            gesamt += len(beitraege)
            for b in beitraege:
                neu += bool(self._ablage.nachricht_merken(b.als_dict(),
                                                          int(jetzt)))
        if neu:
            log.info("Nachrichten: %d neue Meldungen aus %d Beitraegen.",
                     neu, gesamt)
        return {"neu": neu, "gesehen": gesamt}

    # --------------------------------------------------------------- Lesen

    def lagen(self, land: Optional[str] = None) -> List[Dict]:
        """Der Zustand je Quelle -- fuer die Anzeige in den Einstellungen."""
        w = self.wahl()
        abgewaehlt = set(w["abgewaehlt"] or ())
        zugewaehlt = set(w["zugewaehlt"] or ())
        aus = []
        alle = list(fuer_land(land))
        for roh in w["eigene"]:
            q = eigene_quelle(roh)
            if q:
                alle.append(q)
        for q in alle:
            an = _ist_an(q, abgewaehlt, zugewaehlt)
            eintrag = {
                "kennung": q.kennung, "name": q.name, "sprache": q.sprache,
                "art": q.art, "bezahlschranke": q.bezahlschranke,
                "hinweis": q.hinweis, "eigen": q.kennung.startswith("eigen:"),
                "an": an, "hinter_cloudflare": q.hinter_cloudflare,
                # Die Oberflaeche braucht die Werksvorgabe, um daraus den
                # Widerspruch zu bilden -- sonst muesste sie sie erraten.
                "ab_werk": q.ab_werk, "adresse": q.adresse,
            }
            eintrag.update(self._lagen.get(q.kennung, Lage()).als_dict())
            aus.append(eintrag)
        return aus
