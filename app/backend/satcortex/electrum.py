"""Der Electrum-Dienst: beantwortet, was BitBoxApp und Trezor Suite fragen.

Aus dem Betrieb, 28.09.2026: "was will den trezor haben damit man trezor
direkt verbinden kann ???" -- und dann: "ich bin da kein fan von ... das ist
wieder ein docker stack dabei". Deshalb kein electrs daneben, sondern das
Protokoll hier selbst.

Protokoll 1.4 (spesmilo/electrum-protocol). Das sprechen beide Apps fest
(Quelltext: Trezor protocolVersion '1.4', BitBox supportedProtocolVersion
"1.4"), und genau das spricht electrs v0.12.0 -- der Server hinter Umbrel,
StartOS und RaspiBlitz. Solange die Apps dort funktionieren, muessen sie 1.4
sprechen.

Fast alles beantwortet Bitcoin Core direkt. Die Geschichte der Skripte kommt
aus dem Kontobuch der angemeldeten Konten (lesewallet.Leser). Ein Skript,
das keinem angemeldeten Konto gehoert, hat hier KEINE Geschichte -- auch
wenn es im Buch vorkommt, etwa als Ziel einer Ausgabe. Dessen Geschichte
kennen wir nur zum Teil, und eine halbe Antwort waere eine falsche.

Diese Datei kennt kein Netzwerk; das steht in electrumserver.py. Hier wird
nur beantwortet -- und zwar synchron, weil Core ueber urllib gefragt wird.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from . import kontobuch, rpc

log = logging.getLogger(__name__)

PROTOKOLL = "1.4"
SOFTWARE = "SatoshiCortex"

# Der uebliche Electrum-Port fuer Klartext. Hier kommt TLS auf DEMSELBEN
# Port dazu (electrumserver.py erkennt es am ersten Byte), deshalb gibt es
# keinen zweiten.
PORT = 50001

# Wie viele Koepfe blockchain.block.headers hoechstens liefert. Die
# Spezifikation empfiehlt mindestens eine Anpassungsperiode, also 2016.
KOEPFE_HOECHSTENS = 2016

# Fehlercodes. -32601/-32602 sind JSON-RPC; 2 nimmt ElectrumX fuer "der
# Knoten hat abgelehnt" -- so erkennen Apps, dass es nicht an ihnen lag.
UNBEKANNT = -32601
UNGUELTIG = -32602
KNOTEN_LEHNT_AB = 2

_HEX = set("0123456789abcdef")


class ElectrumFehler(Exception):
    """Wird als JSON-RPC-Fehler an die App zurueckgegeben."""

    def __init__(self, code: int, meldung: str) -> None:
        super().__init__(meldung)
        self.code = code
        self.meldung = meldung


@dataclass
class Sitzung:
    """Was eine Verbindung ausgehandelt und abonniert hat."""
    version: Optional[str] = None
    schliessen: bool = False
    koepfe: bool = False
    letzter_kopf: Optional[Dict] = None
    # Skripthash -> zuletzt gemeldeter Status
    abos: Dict[str, Optional[str]] = field(default_factory=dict)


def _version_zerlegen(text: str) -> Tuple[int, ...]:
    try:
        return tuple(int(t) for t in str(text).split("."))
    except ValueError:
        raise ElectrumFehler(UNGUELTIG, f"unlesbare Version: {text}")


def version_aushandeln(angebot: Any) -> str:
    """Die hoechste gemeinsame Protokollversion -- oder ein Fehler.

    Die App nennt eine Version oder einen Bereich [min, max]. Wir sprechen
    genau 1.4; liegt das nicht im Bereich, gibt es nichts Gemeinsames.
    """
    if isinstance(angebot, (list, tuple)) and len(angebot) == 2:
        tief, hoch = angebot
    else:
        tief = hoch = angebot
    eigen = _version_zerlegen(PROTOKOLL)
    if _version_zerlegen(tief) <= eigen <= _version_zerlegen(hoch):
        return PROTOKOLL
    raise ElectrumFehler(UNGUELTIG, f"keine gemeinsame Protokollversion "
                                    f"(angeboten {angebot}, hier {PROTOKOLL})")


def merkle_zweig(txids: List[str], stelle: int) -> List[str]:
    """Die Nachbarn auf dem Weg von einer Transaktion zur Merkle-Wurzel,
    tiefster zuerst -- so, wie get_merkle sie verlangt."""
    ebene = [bytes.fromhex(t)[::-1] for t in txids]
    zweig = []
    while len(ebene) > 1:
        if len(ebene) % 2:
            ebene.append(ebene[-1])
        zweig.append(ebene[stelle ^ 1][::-1].hex())
        ebene = [hashlib.sha256(hashlib.sha256(ebene[i] + ebene[i + 1])
                                .digest()).digest()
                 for i in range(0, len(ebene), 2)]
        stelle //= 2
    return zweig


def _hex32(wert: Any, was: str) -> str:
    """32 Byte hexadezimal -- txid oder Skripthash. Sonst ein Fehler."""
    if not isinstance(wert, str) or len(wert) != 64 \
            or not set(wert.lower()) <= _HEX:
        raise ElectrumFehler(UNGUELTIG, f"{was}: 64 Hexzeichen erwartet")
    return wert.lower()


def _ganzzahl(wert: Any, was: str) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int) or wert < 0:
        raise ElectrumFehler(UNGUELTIG, f"{was}: nicht-negative Ganzzahl erwartet")
    return wert


def _core_meldung(fehler: rpc.RpcFehler) -> str:
    """Cores Begruendung ohne das Drumherum -- "min relay fee not met"
    hilft der App, "{'code': -26, 'message': ...}" nicht."""
    text = str(fehler)
    if "'message': '" in text:
        return text.split("'message': '", 1)[1].rsplit("'", 1)[0]
    return text


class Dienst:
    """Beantwortet Electrum-Befehle aus Core und dem Kontobuch.

    bestand liefert (Kontobuch, eigene Skripthashes). Es wird vom Server
    zwischengespeichert und nach neuen Bloecken und Transaktionen
    aufgefrischt -- hier wird es nur gelesen.
    """

    def __init__(self, knoten, bestand: Callable[[], Tuple[
            kontobuch.Buch, FrozenSet[str]]], version: str = "") -> None:
        self.knoten = knoten
        self.bestand = bestand
        self.software = f"{SOFTWARE} {version}".strip()
        self._befehle: Dict[str, Callable[..., Any]] = {
            "server.version": self._version,
            "server.features": self._merkmale,
            "server.banner": lambda s: f"{self.software} -- dein eigener Knoten",
            "server.ping": lambda s: None,
            "server.peers.subscribe": lambda s: [],
            "server.donation_address": lambda s: "",
            "blockchain.headers.subscribe": self._koepfe_abonnieren,
            "blockchain.block.header": self._kopf,
            "blockchain.block.headers": self._koepfe,
            "blockchain.estimatefee": self._gebuehr,
            "blockchain.relayfee": self._weitergabegebuehr,
            "blockchain.transaction.get": self._tx,
            "blockchain.transaction.get_merkle": self._merkle,
            "blockchain.transaction.broadcast": self._senden,
            "blockchain.scripthash.subscribe": self._abonnieren,
            "blockchain.scripthash.unsubscribe": self._abbestellen,
            "blockchain.scripthash.get_history": self._geschichte,
            "blockchain.scripthash.get_balance": self._guthaben,
            "blockchain.scripthash.listunspent": self._unverbraucht,
            "blockchain.scripthash.get_mempool": self._mempool,
        }

    @property
    def befehle(self) -> FrozenSet[str]:
        return frozenset(self._befehle)

    def bearbeite(self, sitzung: Sitzung, methode: str,
                  params: List[Any]) -> Any:
        befehl = self._befehle.get(methode)
        if befehl is None:
            raise ElectrumFehler(UNBEKANNT, f"unbekannter Befehl: {methode}")
        if not isinstance(params, list):
            raise ElectrumFehler(UNGUELTIG, "params muss eine Liste sein")
        try:
            return befehl(sitzung, *params)
        except TypeError as fehler:
            raise ElectrumFehler(UNGUELTIG, f"falsche Argumente fuer {methode}") \
                from fehler
        except rpc.RpcFehler as fehler:
            raise ElectrumFehler(KNOTEN_LEHNT_AB, _core_meldung(fehler)) \
                from fehler

    # ── Server ─────────────────────────────────────────────────────────────

    def _version(self, s: Sitzung, name: str = "", angebot: Any = PROTOKOLL):
        if s.version is not None:
            raise ElectrumFehler(UNGUELTIG, "die Version ist schon ausgehandelt")
        try:
            s.version = version_aushandeln(angebot)
        except ElectrumFehler:
            s.schliessen = True
            raise
        return [self.software, s.version]

    def _merkmale(self, s: Sitzung):
        return {
            "hosts": {},
            "genesis_hash": self.knoten.ruf("getblockhash", 0),
            "server_version": self.software,
            "protocol_min": PROTOKOLL,
            "protocol_max": PROTOKOLL,
            "pruning": None,
            "hash_function": "sha256",
        }

    # ── Kette ──────────────────────────────────────────────────────────────

    def _spitze(self) -> Dict:
        hoehe = self.knoten.ruf("getblockcount")
        blockhash = self.knoten.ruf("getblockhash", hoehe)
        return {"height": hoehe,
                "hex": self.knoten.ruf("getblockheader", blockhash, False)}

    def _koepfe_abonnieren(self, s: Sitzung):
        kopf = self._spitze()
        s.koepfe = True
        s.letzter_kopf = kopf
        return kopf

    def _kopf(self, s: Sitzung, hoehe: Any, pruefpunkt: Any = 0):
        hoehe = _ganzzahl(hoehe, "height")
        if pruefpunkt:
            # Ein Merkle-Beweis ueber alle Koepfe bis dahin. Keine der beiden
            # Apps fragt danach; lieber ehrlich ablehnen als halb liefern.
            raise ElectrumFehler(UNGUELTIG, "cp_height wird nicht unterstuetzt")
        blockhash = self.knoten.ruf("getblockhash", hoehe)
        return self.knoten.ruf("getblockheader", blockhash, False)

    def _koepfe(self, s: Sitzung, start: Any, anzahl: Any, pruefpunkt: Any = 0):
        start = _ganzzahl(start, "start_height")
        anzahl = min(_ganzzahl(anzahl, "count"), KOEPFE_HOECHSTENS)
        if pruefpunkt:
            raise ElectrumFehler(UNGUELTIG, "cp_height wird nicht unterstuetzt")
        spitze = self.knoten.ruf("getblockcount")
        anzahl = max(0, min(anzahl, spitze - start + 1))
        # Zweimal gebuendelt statt 2*anzahl Einzelanfragen: die BitBoxApp
        # holt ab ihrem Pruefpunkt rund 27.000 Koepfe.
        hashes = self.knoten.stapel(
            [("getblockhash", [h]) for h in range(start, start + anzahl)])
        koepfe = self.knoten.stapel(
            [("getblockheader", [b, False]) for b in hashes])
        return {"count": anzahl, "hex": "".join(koepfe),
                "max": KOEPFE_HOECHSTENS}

    def _gebuehr(self, s: Sitzung, bloecke: Any, modus: Any = None):
        bloecke = _ganzzahl(bloecke, "number")
        params = [bloecke] + ([modus] if modus else [])
        schaetzung = self.knoten.ruf("estimatesmartfee", *params)
        rate = (schaetzung or {}).get("feerate")
        return rate if rate is not None else -1

    def _weitergabegebuehr(self, s: Sitzung):
        return self.knoten.ruf("getnetworkinfo").get("relayfee")

    # ── Transaktionen ──────────────────────────────────────────────────────

    def _tx(self, s: Sitzung, txid: Any, ausfuehrlich: Any = False):
        txid = _hex32(txid, "tx_hash")
        return self.knoten.ruf("getrawtransaction", txid,
                               1 if ausfuehrlich else 0)

    def _merkle(self, s: Sitzung, txid: Any, hoehe: Any):
        txid = _hex32(txid, "tx_hash")
        hoehe = _ganzzahl(hoehe, "height")
        blockhash = self.knoten.ruf("getblockhash", hoehe)
        txids = self.knoten.ruf("getblock", blockhash, 1)["tx"]
        if txid not in txids:
            raise ElectrumFehler(UNGUELTIG,
                                 f"{txid} steht nicht in Block {hoehe}")
        stelle = txids.index(txid)
        return {"block_height": hoehe, "pos": stelle,
                "merkle": merkle_zweig(txids, stelle)}

    def _senden(self, s: Sitzung, roh: Any):
        """Eine FERTIG unterschriebene Transaktion weiterreichen. Unterschrieben
        hat das Geraet; hier gibt es keinen Schluessel und nie einen."""
        if not isinstance(roh, str) or not roh or not set(roh.lower()) <= _HEX:
            raise ElectrumFehler(UNGUELTIG, "raw_tx: Hexzeichen erwartet")
        txid = self.knoten.ruf("sendrawtransaction", roh)
        log.info("Electrum: Transaktion weitergereicht: %s", txid)
        return txid

    # ── Skripthashes ───────────────────────────────────────────────────────

    def _eigen(self, skript: Any) -> Tuple[str, Optional[kontobuch.Buch]]:
        """Der Skripthash und das Buch -- None, wenn er uns nicht gehoert."""
        skript = _hex32(skript, "scripthash")
        buch, eigene = self.bestand()
        return skript, (buch if skript in eigene else None)

    def _status(self, skript: str) -> Optional[str]:
        skript, buch = self._eigen(skript)
        return buch.status(skript) if buch else None

    def _abonnieren(self, s: Sitzung, skript: Any):
        status = self._status(skript)
        s.abos[_hex32(skript, "scripthash")] = status
        return status

    def _abbestellen(self, s: Sitzung, skript: Any):
        return s.abos.pop(_hex32(skript, "scripthash"), "fehlt") != "fehlt"

    def _geschichte(self, s: Sitzung, skript: Any):
        skript, buch = self._eigen(skript)
        return buch.geschichte(skript) if buch else []

    def _guthaben(self, s: Sitzung, skript: Any):
        skript, buch = self._eigen(skript)
        return buch.guthaben(skript) if buch else {"confirmed": 0,
                                                    "unconfirmed": 0}

    def _unverbraucht(self, s: Sitzung, skript: Any):
        skript, buch = self._eigen(skript)
        return buch.unverbraucht(skript) if buch else []

    def _mempool(self, s: Sitzung, skript: Any):
        skript, buch = self._eigen(skript)
        return buch.mempool(skript) if buch else []

    # ── Benachrichtigungen ─────────────────────────────────────────────────

    def neuigkeiten(self, s: Sitzung) -> List[Tuple[str, List[Any]]]:
        """Was dieser Sitzung zu melden ist -- nur, was sich geaendert hat.

        Merkt sich das Gemeldete in der Sitzung, damit dieselbe Neuigkeit
        nicht zweimal kommt.
        """
        meldungen: List[Tuple[str, List[Any]]] = []
        if s.koepfe:
            kopf = self._spitze()
            if kopf != s.letzter_kopf:
                s.letzter_kopf = kopf
                meldungen.append(("blockchain.headers.subscribe", [kopf]))
        for skript, alt in list(s.abos.items()):
            neu = self._status(skript)
            if neu != alt:
                s.abos[skript] = neu
                meldungen.append(("blockchain.scripthash.subscribe",
                                  [skript, neu]))
        return meldungen
