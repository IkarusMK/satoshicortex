"""Nur-Lese-Wallets in Bitcoin Core -- die Grundlage fuer Electrum.

Aus dem Betrieb, 28.09.2026: "was will den trezor haben damit man trezor
direkt verbinden kann ???"

BitBoxApp und Trezor Suite sprechen nur das Electrum-Protokoll. Fast alles
darin beantwortet Bitcoin Core direkt. Die eine schwere Frage -- "welche
Transaktionen gehoeren zu dieser Adresse?" -- braeuchte fuer beliebige
Adressen einen Index ueber die ganze Kette (electrs: 60 bis 100 GB). Wir
beantworten sie nur fuer die EIGENEN Konten: Core verfolgt sie als
Nur-Lese-Wallet, die ausschliesslich den oeffentlichen Kontoschluessel
kennt. Ausgeben kann sie nichts.

Am 28.09.2026 an einer Regtest-Kette mit Core v31.1 von Hand durchgespielt,
bevor hier eine Zeile stand:

  * importdescriptors mit NUR dem oeffentlichen Schluessel findet alle Ein-
    und Ausgaenge, Wechselgeld und Mempool -- das Guthaben stimmte auf den
    Satoshi mit der Wallet, die die Schluessel hielt.
  * Aktive Deskriptoren fuellen ihren Vorrat selbst nach: nach einer Zahlung
    an Adresse #990 reichte der Bereich bis #1990.
  * Core braucht nach einem Block oder einer Transaktion einen Moment, bis
    die Wallet nachgezogen hat. Wer sofort fragt, sieht den alten Stand.
  * vpub/zpub nimmt Core nicht an -- deshalb die Umrechnung hier.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

from . import kontobuch, rpc

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Laenge eines erweiterten Schluessels ohne Pruefsumme (BIP-32).
_SCHLUESSEL_BYTES = 78

# Versionskennungen nach SLIP-132. Die Apps zeigen den Kontoschluessel oft
# mit dem Praefix, der die Adressart verraet (zpub = Native SegWit); Core
# kennt nur xpub/tpub. Umgerechnet wird ausschliesslich die Kennung.
#
#   Kennung -> (Netz, Art oder None, falls der Praefix es offenlaesst)
_OEFFENTLICH: Dict[bytes, Tuple[str, Optional[str]]] = {
    bytes.fromhex("0488b21e"): ("main", None),       # xpub
    bytes.fromhex("049d7cb2"): ("main", "sh-wpkh"),  # ypub
    bytes.fromhex("04b24746"): ("main", "wpkh"),     # zpub
    bytes.fromhex("043587cf"): ("test", None),       # tpub
    bytes.fromhex("044a5262"): ("test", "sh-wpkh"),  # upub
    bytes.fromhex("045f1cf6"): ("test", "wpkh"),     # vpub
}
# Mehrfachsignatur (Ypub, Zpub, Upub, Vpub): braucht mehrere Schluessel und
# ein Quorum. Das kann diese Wallet nicht -- und sagt es.
_MEHRFACH = {bytes.fromhex(k) for k in (
    "0295b43f", "02aa7ed3", "024289ef", "02575483")}
# Private Schluessel. Wer einen einfuegt, hat sich vertan; er wird weder
# gespeichert noch an Core gereicht.
_PRIVAT = {bytes.fromhex(k) for k in (
    "0488ade4", "049d7878", "04b2430c", "04358394", "044a4e28", "045f18bc",
    "0295b005", "02aa7a99", "024285b5", "02575048")}
_NORMIERT = {"main": bytes.fromhex("0488b21e"),
             "test": bytes.fromhex("043587cf")}

# Die vier Arten, die BitBoxApp und Trezor Suite fuer Einzelkonten nutzen.
# Das Muster steht fuer die Empfangskette; die Wechselkette ist /1/*.
_MUSTER = {
    "pkh": "pkh({k}/{kette}/*)",            # BIP-44, Legacy
    "sh-wpkh": "sh(wpkh({k}/{kette}/*))",   # BIP-49, SegWit in P2SH
    "wpkh": "wpkh({k}/{kette}/*)",          # BIP-84, Native SegWit
    "tr": "tr({k}/{kette}/*)",              # BIP-86, Taproot
}
ARTEN = tuple(_MUSTER)

WALLET_PRAEFIX = "satcortex-lesen-"


class SchluesselFehler(ValueError):
    """Der eingefuegte Text taugt nicht als Kontoschluessel.

    schluessel ist der Uebersetzungsschluessel der Oberflaeche -- die
    Meldung selbst steht dort, in beiden Sprachen.
    """

    def __init__(self, schluessel: str) -> None:
        super().__init__(schluessel)
        self.schluessel = schluessel


@dataclass(frozen=True)
class Schluessel:
    normiert: str           # in Cores Schreibweise: xpub... oder tpub...
    netz: str               # "main" oder "test" (Testnetz und Regtest)
    art: Optional[str]      # aus dem Praefix, None wenn er es offenlaesst
    tiefe: int              # 3 bei einem Kontoschluessel nach BIP-44/84/86


def _doppel_sha(roh: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(roh).digest()).digest()


def _base58_lesen(text: str) -> bytes:
    """Base58Check lesen; ohne gueltige Pruefsumme gibt es nichts."""
    if not text or any(z not in _ALPHABET for z in text):
        raise SchluesselFehler("el_kein_schluessel")
    n = 0
    for zeichen in text:
        n = n * 58 + _ALPHABET.index(zeichen)
    laenge = _SCHLUESSEL_BYTES + 4
    if n.bit_length() > laenge * 8:
        raise SchluesselFehler("el_kein_schluessel")
    roh = n.to_bytes(laenge, "big")
    if _doppel_sha(roh[:-4])[:4] != roh[-4:]:
        raise SchluesselFehler("el_kein_schluessel")
    return roh[:-4]


def _base58_schreiben(roh: bytes) -> str:
    roh = roh + _doppel_sha(roh)[:4]
    n = int.from_bytes(roh, "big")
    text = ""
    while n:
        n, rest = divmod(n, 58)
        text = _ALPHABET[rest] + text
    return "1" * (len(roh) - len(roh.lstrip(b"\0"))) + text


def lies_schluessel(text: str) -> Schluessel:
    """Einen eingefuegten Kontoschluessel pruefen und in Cores Schreibweise
    bringen."""
    roh = _base58_lesen((text or "").strip())
    version = roh[:4]
    if version in _PRIVAT:
        raise SchluesselFehler("el_privat")
    if version in _MEHRFACH:
        raise SchluesselFehler("el_mehrfach")
    if version not in _OEFFENTLICH:
        raise SchluesselFehler("el_kein_schluessel")
    netz, art = _OEFFENTLICH[version]
    return Schluessel(
        normiert=_base58_schreiben(_NORMIERT[netz] + roh[4:]),
        netz=netz,
        art=art,
        tiefe=roh[4],
    )


def deskriptoren(normiert: str, art: str) -> Tuple[str, str]:
    """Empfangs- und Wechselkette als Deskriptoren, noch ohne Pruefsumme."""
    if art not in _MUSTER:
        raise SchluesselFehler("el_art_unbekannt")
    muster = _MUSTER[art]
    return (muster.format(k=normiert, kette=0),
            muster.format(k=normiert, kette=1))


def walletname(schluessel: Schluessel, art: str) -> str:
    """Der Name der Nur-Lese-Wallet in Core.

    Aus dem Schluessel abgeleitet, damit dasselbe Konto nie zwei Wallets
    bekommt -- und gehasht, damit der Name nichts ueber ihn verraet. Je Art
    eine eigene: Core erlaubt je Wallet nur einen aktiven Deskriptor pro
    Adressart, und zwei Konten derselben Art (BitBox und Trezor) wuerden
    sich sonst gegenseitig verdraengen.
    """
    kern = hashlib.sha256(f"{art}:{schluessel.normiert}".encode()).hexdigest()
    return WALLET_PRAEFIX + kern[:16]


# ── Die Wallet in Core verwalten ───────────────────────────────────────────

# Das Nachsuchen in der Kette laeuft INNERHALB von importdescriptors; der
# Aufruf kehrt erst zurueck, wenn es fertig ist. Mit Blockfiltern geht das
# schnell (Core 25.0: "significantly faster if compact block filters are
# available"), aber wie schnell an einem echten Knoten, ist gemessen erst,
# wenn es gemessen ist. Grosszuegig bemessen -- der Aufruf laeuft im
# Hintergrund, den Fortschritt zeigt getwalletinfo.
IMPORT_ZEITLIMIT_SEKUNDEN = 6 * 3600.0

# Wie viele Adressen je Kette die Wallet von Anfang an kennt. Core fuellt
# den Vorrat danach selbst nach (gemessen: nach einer Zahlung an #990 reichte
# er bis #1990). Ausdruecklich angegeben, sonst warnt Core ("Range not given,
# using default keypool range").
VORRAT = 1000

# Cores Fehlernummern, die hier etwas bedeuten (rpc/protocol.h):
_WALLET_NICHT_GELADEN = -18
_WALLET_GIBT_ES_SCHON = -4
_WALLET_SCHON_GELADEN = -35

# Welche Ketten ein Testschluessel (tpub/upub/vpub) bedienen kann.
_TESTKETTEN = ("test", "testnet4", "signet", "regtest")


class LeseFehler(RuntimeError):
    """Core hat die Nur-Lese-Wallet nicht so angenommen wie verlangt."""


def netz_passt(kette: str, netz: str) -> bool:
    """Passt ein Schluessel dieses Netzes zu dieser Kette?"""
    if netz == "main":
        return kette == "main"
    return kette in _TESTKETTEN


def gibt_es_nicht(fehler: rpc.RpcFehler) -> bool:
    """Meldet Core, dass es diese Wallet nicht gibt (oder sie nicht geladen
    ist)? An der Regtest-Kette gemessen: loadwallet und jeder Aufruf mit
    Wallet-Pfad antworten dann mit demselben Code."""
    return fehler.code == _WALLET_NICHT_GELADEN


def laden(knoten, name: str) -> None:
    """Die Wallet laden, falls sie es nicht schon ist."""
    try:
        knoten.ruf("loadwallet", name, True)
    except rpc.RpcFehler as fehler:
        if fehler.code != _WALLET_SCHON_GELADEN:
            raise


def anmelden(knoten, schluessel: Schluessel, art: str, seit: int = 0,
             zeitlimit: float = IMPORT_ZEITLIMIT_SEKUNDEN) -> str:
    """Ein Konto als Nur-Lese-Wallet anmelden und seine Geschichte suchen.

    seit: Unix-Zeit, ab der gesucht wird. 0 heisst die ganze Kette --
    richtig, wenn niemand weiss, seit wann das Konto benutzt wird.
    Kehrt erst zurueck, wenn Core fertig gesucht hat.
    """
    kette = knoten.ruf("getblockchaininfo").get("chain", "")
    if not netz_passt(kette, schluessel.netz):
        raise SchluesselFehler("el_falsches_netz")
    empfang, wechsel = deskriptoren(schluessel.normiert, art)
    name = walletname(schluessel, art)
    try:
        # name, disable_private_keys, blank, passphrase, avoid_reuse,
        # descriptors, load_on_startup -- ohne private Schluessel, und nach
        # einem Neustart von Core wieder da.
        knoten.ruf("createwallet", name, True, True, "", False, True, True)
    except rpc.RpcFehler as fehler:
        if fehler.code != _WALLET_GIBT_ES_SCHON:
            raise
        laden(knoten, name)
    # Sind die Deskriptoren schon da, ist das Konto schon angemeldet. Ein
    # zweiter Import wuerde abgelehnt, sobald der Vorrat gewachsen ist ("new
    # range must include current range = [0,1003]" -- an der Regtest-Kette
    # gefunden, 28.09.2026), und er wuerde ohnehin nur neu suchen.
    vorhanden = {d.get("desc", "").split("#")[0] for d in (
        knoten.ruf("listdescriptors", wallet=name) or {}).get("descriptors", [])}
    if {empfang, wechsel} <= vorhanden:
        return name
    anfragen = [
        {"desc": knoten.ruf("getdescriptorinfo", d)["descriptor"],
         "active": True, "internal": intern, "range": [0, VORRAT - 1],
         "timestamp": int(seit)}
        for d, intern in ((empfang, False), (wechsel, True))
    ]
    ergebnis = knoten.ruf("importdescriptors", anfragen,
                          zeitlimit=zeitlimit, wallet=name)
    fehlgeschlagen = [e for e in ergebnis or [] if not e.get("success")]
    if fehlgeschlagen or len(ergebnis or []) != len(anfragen):
        raise LeseFehler(f"importdescriptors: {fehlgeschlagen or ergebnis}")
    return name


def fortschritt(knoten, name: str) -> Optional[float]:
    """Wie weit das Nachsuchen ist -- None, wenn gerade nichts gesucht wird."""
    lage = knoten.ruf("getwalletinfo", wallet=name).get("scanning")
    if isinstance(lage, dict):
        return float(lage.get("progress", 0.0))
    return None


def abmelden(knoten, name: str) -> None:
    """Die Wallet entladen und nicht wieder von selbst laden lassen.

    Geloescht wird sie nicht: Core hat dafuer keinen Befehl, und sie enthaelt
    ohnehin nur den oeffentlichen Schluessel. Wer dasselbe Konto wieder
    anmeldet, bekommt sie samt Geschichte zurueck.
    """
    try:
        knoten.ruf("unloadwallet", name, False)
    except rpc.RpcFehler as fehler:
        if fehler.code != _WALLET_NICHT_GELADEN:
            raise



# ── Der Leser: aus Cores Wallets wird das Kontobuch ────────────────────────

# So viele Eintraege je listtransactions-Aufruf. Seitenweise, damit auch ein
# Konto mit langer Geschichte nicht als eine riesige Antwort kommt.
SEITE = 1000

_Zerlegt = Tuple[Tuple[Tuple[int, str, int], ...],
                 Tuple[Tuple[str, int, str, int], ...]]


def skripthash(spk_hex: str) -> str:
    """Der Skripthash nach Electrum: sha256 des scriptPubKey, umgedreht."""
    return hashlib.sha256(bytes.fromhex(spk_hex)).digest()[::-1].hex()


class Leser:
    """Liest die angemeldeten Wallets und baut daraus das Kontobuch.

    Zerlegte Transaktionen werden gemerkt: ihr Inhalt aendert sich nie, nur
    ihre Hoehe -- und die kommt bei jedem Lesen frisch aus der Wallet. So
    kostet ein neuer Block nur die Aufrufe fuer das, was neu ist.
    """

    def __init__(self, knoten, wallets: Callable[[], Sequence[str]],
                 fehlt: Optional[Callable[[str], bool]] = None) -> None:
        self.knoten = knoten
        self._wallets = wallets
        # Gefragt, wenn Core eine Wallet nicht kennt: steht fest, dass es sie
        # nicht gibt? Nur dann wird sie uebergangen.
        self._fehlt = fehlt or (lambda _name: False)
        self._zerlegt: Dict[str, _Zerlegt] = {}
        # (wallet, deskriptor, bereich) -> Skripthashes. Neu abgeleitet wird
        # nur, wenn Core den Vorrat erweitert hat.
        self._abgeleitet: Dict[Tuple[str, str, Tuple[int, int]],
                               FrozenSet[str]] = {}

    def lesen(self) -> Tuple[kontobuch.Buch, FrozenSet[str]]:
        """Das Kontobuch und die Skripthashes, die uns gehoeren."""
        lage: Dict[str, Tuple[int, int, int]] = {}   # txid -> (konf, hoehe, stelle)
        eigene: set = set()
        for name in self._wallets():
            try:
                skripte = self._eigene_skripte(name)
                eintraege = self._eintraege(name)
            except rpc.RpcFehler as fehler:
                # Eine Wallet, die es in Core nicht gibt, darf das Lesen der
                # anderen nicht aufhalten -- aber nur, wenn das feststeht.
                # Sonst lieber kein neuer Stand als einer, in dem ein Konto
                # still fehlt.
                if not gibt_es_nicht(fehler) or not self._fehlt(name):
                    raise
                continue
            eigene |= skripte
            for e in eintraege:
                if e.get("confirmations", -1) < 0:
                    continue            # verdraengt: weder Kette noch Mempool
                lage[e["txid"]] = (e["confirmations"],
                                   e.get("blockheight") or 0,
                                   e.get("blockindex") or 0)

        mempool = self._mempool([t for t, (k, _h, _s) in lage.items() if k == 0])
        txs: List[kontobuch.Tx] = []
        for txid, (konf, hoehe, stelle) in lage.items():
            if konf == 0 and txid not in mempool:
                continue                # in der Wallet, aber nicht mehr im Mempool
            ausgaenge, eingaenge = self._zerlege(txid, bestaetigt=konf > 0)
            gebuehr = None
            if konf == 0:
                hoehe, gebuehr = mempool[txid]
            txs.append(kontobuch.Tx(txid=txid, hoehe=hoehe, position=stelle,
                                    gebuehr=gebuehr, ausgaenge=ausgaenge,
                                    eingaenge=eingaenge))
        return kontobuch.Buch(txs), frozenset(eigene)

    def _eigene_skripte(self, name: str) -> FrozenSet[str]:
        """Jeder Skripthash, den die aktiven Deskriptoren der Wallet ableiten.

        NICHT aus den Empfangseintraegen: Core blendet Wechselgeld in
        listtransactions aus, und die erste Fassung verlor es genau so
        (Regtest, 28.09.2026). Aus den Deskriptoren kommt auch, was noch nie
        benutzt wurde -- die Frage nach einer leeren Adresse ist dann eine
        leere Antwort, keine unbekannte.
        """
        skripte: set = set()
        for d in (self.knoten.ruf("listdescriptors", wallet=name)
                  or {}).get("descriptors", []):
            bereich = d.get("range")
            if not d.get("active") or not bereich:
                continue
            schluessel = (name, d["desc"], (bereich[0], bereich[1]))
            if schluessel not in self._abgeleitet:
                adressen = self.knoten.ruf("deriveaddresses", d["desc"],
                                           [bereich[0], bereich[1]])
                antworten = self.knoten.stapel(
                    [("validateaddress", [a]) for a in adressen])
                self._abgeleitet[schluessel] = frozenset(
                    skripthash(a["scriptPubKey"]) for a in antworten
                    if a.get("isvalid"))
            skripte |= self._abgeleitet[schluessel]
        return frozenset(skripte)

    def _eintraege(self, name: str) -> List[Dict]:
        eintraege: List[Dict] = []
        while True:
            seite = self.knoten.ruf("listtransactions", "*", SEITE,
                                    len(eintraege), True, wallet=name) or []
            eintraege += seite
            if len(seite) < SEITE:
                return eintraege

    def _mempool(self, txids: List[str]) -> Dict[str, Tuple[int, int]]:
        """txid -> (Hoehe 0 oder -1, Gebuehr in sat), nur was wirklich drin ist.

        Einzeln gefragt und nicht ueber getrawmempool: das waere der ganze
        Mempool, und genau so ein Aufruf hat den Container schon einmal ueber
        seine Speichergrenze gehoben (21.09.2026). Eigene Transaktionen im
        Mempool sind eine Handvoll.
        """
        lage = {}
        for txid in txids:
            try:
                eintrag = self.knoten.ruf("getmempoolentry", txid)
            except rpc.RpcFehler:
                continue                # nicht (mehr) im Mempool
            hoehe = -1 if eintrag.get("depends") else 0
            gebuehr = rpc.sat_aus_btc((eintrag.get("fees") or {}).get("base"))
            lage[txid] = (hoehe, gebuehr)
        return lage

    def _zerlege(self, txid: str, bestaetigt: bool) -> _Zerlegt:
        if txid in self._zerlegt:
            return self._zerlegt[txid]
        # Stufe 2 liefert zu jedem Eingang, was er ausgibt ("prevout") --
        # aber nur fuer Bestaetigte. Im Mempool fehlt es (gemessen), dann
        # wird der Vorgaenger nachgeschlagen; txindex ist an.
        roh = self.knoten.ruf("getrawtransaction", txid, 2 if bestaetigt else 1)
        ausgaenge = tuple(
            (a["n"], skripthash(a["scriptPubKey"]["hex"]),
             rpc.sat_aus_btc(a["value"])) for a in roh.get("vout") or [])
        eingaenge = []
        for e in roh.get("vin") or []:
            if "txid" not in e:
                continue                # Coinbase: gibt nichts aus
            vorher = e.get("prevout")
            if vorher is None:
                vorgaenger = self.knoten.ruf("getrawtransaction", e["txid"], 1)
                vorher = next((a for a in vorgaenger.get("vout") or []
                               if a.get("n") == e["vout"]), None)
                if vorher is None:
                    # Nie still ueberspringen: ein fehlender Eingang
                    # verfaelschte das Guthaben. Lieber gar kein neuer Stand.
                    raise LeseFehler(f"{e['txid']}:{e['vout']} nicht gefunden")
            eingaenge.append((e["txid"], e["vout"],
                              skripthash(vorher["scriptPubKey"]["hex"]),
                              rpc.sat_aus_btc(vorher["value"])))
        zerlegt = (ausgaenge, tuple(eingaenge))
        self._zerlegt[txid] = zerlegt
        return zerlegt
