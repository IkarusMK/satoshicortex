"""Der Electrum-Server im Leben der Anwendung: an, aus, Konten.

Die Oberflaeche spricht hierueber; api.py reicht nur durch. Getrennt, weil
api.py ohnehin lang ist -- und weil sich so der ganze Ablauf ohne FastAPI
pruefen laesst.

Das Anmelden eines Kontos laeuft im Hintergrund: importdescriptors kehrt erst
zurueck, wenn Core die Kette durchsucht hat, und das kann an einem echten
Knoten dauern. Solange steht das Konto als "sucht" da und wird nicht
gelesen -- Core lehnt Wallet-Aufrufe waehrend des Nachsuchens teils ab.

Gesucht wird nacheinander, nie fuer zwei Konten zugleich: jede Suche haelt
in Core einen der Plaetze fuer Anfragen und laesst die Platte arbeiten.
Wer wartet, steht als "wartet" da.
"""
from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from . import electrum, electrumserver, fernzugang, lesewallet, rpc

log = logging.getLogger(__name__)

# Mehr braucht ein Haushalt nicht: je Geraet ein, zwei Konten. Jede weitere
# Wallet kostet Core beim Start Zeit und bei jedem Block einen Blick.
KONTEN_HOECHSTENS = 10
NAME_HOECHSTENS = 40

# Ein Konto, dessen Wallet es in Core nicht gibt: seine Anmeldung wurde nie
# fertig -- die Anwendung startete neu, waehrend es auf seine Suche wartete.
UNTERBROCHEN = "el_unterbrochen"


class _Vertreter:
    """Fragt bei JEDEM Aufruf eine frische Verbindung -- die Zugangsdaten
    kommen aus der Ablage und koennen sich aendern."""

    def __init__(self, hole: Callable[[], rpc.Knoten]) -> None:
        self._hole = hole

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        return self._hole().ruf(methode, *params, zeitlimit=zeitlimit,
                                wallet=wallet)

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return self._hole().stapel(aufrufe, zeitlimit=zeitlimit, wallet=wallet)


def _seit_lesen(seit: Optional[str]) -> int:
    """"JJJJ-MM-TT" -> Unix-Zeit um Mitternacht UTC; leer heisst die ganze
    Kette."""
    if not seit:
        return 0
    try:
        tag = datetime.date.fromisoformat(str(seit).strip())
    except ValueError:
        raise lesewallet.SchluesselFehler("el_datum")
    return int(datetime.datetime(tag.year, tag.month, tag.day,
                                 tzinfo=datetime.timezone.utc).timestamp())


class Betrieb:

    def __init__(self, knoten_hole: Callable[[], rpc.Knoten], zustand,
                 tls_verzeichnis: str, version: str = "",
                 host: str = "0.0.0.0",  # nosec B104 -- im Container
                 port: int = electrum.PORT) -> None:
        self.knoten = _Vertreter(knoten_hole)
        self.zustand = zustand
        self.tls_verzeichnis = tls_verzeichnis
        self.version = version
        self.host = host
        self.port = port
        self._sperre = threading.Lock()
        self._suchend: Set[str] = set()
        # Eine Suche nach der anderen; _aktiv ist die, die gerade laeuft.
        self._suche = threading.Lock()
        self._aktiv: Optional[str] = None
        self._fehler: Dict[str, str] = {}
        self._faeden: List[threading.Thread] = []
        self._server: Optional[electrumserver.ElectrumServer] = None
        self._bestand = electrumserver.Bestand(
            lesewallet.Leser(self.knoten, self.wallets, fehlt=self._fehlt))

    # ── Konten ─────────────────────────────────────────────────────────────

    def _konten(self) -> List[Dict]:
        return list((self.zustand.laden().electrumwahl or {}).get("konten")
                    or [])

    def wallets(self) -> List[str]:
        """Die Wallets, die gelesen werden -- ohne die, die noch suchen, und
        ohne die, die es in Core nicht gibt."""
        with self._sperre:
            aussen_vor = set(self._suchend) | {
                w for w, f in self._fehler.items() if f == UNTERBROCHEN}
        return [k["wallet"] for k in self._konten()
                if k.get("wallet") and k["wallet"] not in aussen_vor]

    def _fehlt(self, wallet: str) -> bool:
        """Gibt es die Wallet in Core nicht? Dann wird das Konto als
        unterbrochen gefuehrt. Gibt es sie, wird sie geladen."""
        try:
            lesewallet.laden(self.knoten, wallet)
        except rpc.RpcFehler as fehler:
            if not lesewallet.gibt_es_nicht(fehler):
                raise
            log.warning("Electrum: Wallet %s gibt es in Core nicht -- die "
                        "Anmeldung wurde unterbrochen", wallet)
            with self._sperre:
                self._fehler[wallet] = UNTERBROCHEN
            return True
        return False

    def _merken(self, konten: List[Dict], an: Optional[bool] = None) -> None:
        wahl = dict(self.zustand.laden().electrumwahl or {})
        wahl["konten"] = konten
        if an is not None:
            wahl["an"] = an
        self.zustand.merke_electrumwahl(wahl)

    def konto_anmelden(self, schluessel_text: str, art: Optional[str],
                       name: str, seit: Optional[str]) -> Dict:
        """Ein Konto anmelden. Kehrt sofort zurueck; gesucht wird im
        Hintergrund."""
        schluessel = lesewallet.lies_schluessel(schluessel_text)
        if schluessel.art is None and not art:
            raise lesewallet.SchluesselFehler("el_art_waehlen")
        if schluessel.art is not None and art and art != schluessel.art:
            raise lesewallet.SchluesselFehler("el_art_passt_nicht")
        art = schluessel.art or art
        if art not in lesewallet.ARTEN:
            raise lesewallet.SchluesselFehler("el_art_unbekannt")
        name = (name or "").strip()
        if not name or len(name) > NAME_HOECHSTENS:
            raise lesewallet.SchluesselFehler("el_name_ungueltig")
        zeit = _seit_lesen(seit)
        wallet = lesewallet.walletname(schluessel, art)
        # Das Netz gleich hier: wer klickt, soll es sofort erfahren und nicht
        # erst, nachdem im Hintergrund nichts gefunden wurde.
        kette = (self.knoten.ruf("getblockchaininfo") or {}).get("chain", "")
        if not lesewallet.netz_passt(kette, schluessel.netz):
            raise lesewallet.SchluesselFehler("el_falsches_netz")

        with self._sperre:
            if wallet in self._suchend:
                return {"wallet": wallet}       # sucht schon oder wartet
            konten = self._konten()
            if not any(k.get("wallet") == wallet for k in konten):
                if len(konten) >= KONTEN_HOECHSTENS:
                    raise lesewallet.SchluesselFehler("el_zu_viele")
                konten.append({
                    "wallet": wallet, "name": name, "art": art,
                    "angelegt": datetime.datetime.now(
                        datetime.timezone.utc).isoformat()})
                self._merken(konten)
            self._suchend.add(wallet)
            self._fehler.pop(wallet, None)

        faden = threading.Thread(
            target=self._suchen, args=(schluessel, art, zeit, wallet),
            name=f"electrum-anmelden-{wallet[-6:]}", daemon=True)
        self._faeden = [f for f in self._faeden if f.is_alive()] + [faden]
        faden.start()
        return {"wallet": wallet}

    def _suchen(self, schluessel, art: str, zeit: int, wallet: str) -> None:
        try:
            with self._suche:
                with self._sperre:
                    self._aktiv = wallet
                try:
                    lesewallet.anmelden(self.knoten, schluessel, art,
                                        seit=zeit)
                finally:
                    with self._sperre:
                        self._aktiv = None
            log.info("Electrum: Konto %s angemeldet", wallet)
        except lesewallet.SchluesselFehler as fehler:
            with self._sperre:
                self._fehler[wallet] = fehler.schluessel
        except (lesewallet.LeseFehler, rpc.NichtErreichbar,
                rpc.RpcFehler) as fehler:
            log.warning("Electrum: Konto %s nicht angemeldet: %s",
                        wallet, fehler)
            with self._sperre:
                # Ein Uebersetzungsschluessel, keine Rohmeldung von Core --
                # die steht im Protokoll.
                self._fehler[wallet] = "el_suche_gescheitert"
        finally:
            with self._sperre:
                self._suchend.discard(wallet)
            self._bestand.veraltet()
            self.anstossen()

    def konto_abmelden(self, wallet: str) -> None:
        """Nur, was hier angemeldet wurde -- nie eine fremde Wallet."""
        with self._sperre:
            konten = self._konten()
            if not any(k.get("wallet") == wallet for k in konten):
                raise KeyError(wallet)
            self._merken([k for k in konten if k.get("wallet") != wallet])
            self._fehler.pop(wallet, None)
        try:
            lesewallet.abmelden(self.knoten, wallet)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            # Vergessen ist sie trotzdem: gelesen wird sie nicht mehr. Laedt
            # Core sie beim naechsten Start noch einmal, liegt darin nur der
            # oeffentliche Schluessel -- und niemand fragt sie.
            log.warning("Electrum: %s nicht entladen: %s", wallet, fehler)
        self._bestand.veraltet()
        self.anstossen()

    # ── Server ─────────────────────────────────────────────────────────────

    @property
    def laeuft(self) -> bool:
        return self._server is not None

    async def einschalten(self) -> None:
        if self._server is None:
            dienst = electrum.Dienst(self.knoten, self._bestand.aktuell,
                                     version=self.version)
            tls = electrumserver.tls_kontext(self.tls_verzeichnis)
            server = electrumserver.ElectrumServer(
                dienst, self._bestand, tls=tls, host=self.host, port=self.port)
            await server.starten()
            self._server = server
            self.port = server.port
        with self._sperre:
            self._merken(self._konten(), an=True)

    async def anhalten(self) -> None:
        """Den Server stoppen, die Wahl stehen lassen -- beim Herunterfahren
        der Anwendung. Sonst waere Electrum nach jedem Neustart aus."""
        server, self._server = self._server, None
        if server is not None:
            await server.beenden()

    async def ausschalten(self) -> None:
        await self.anhalten()
        with self._sperre:
            self._merken(self._konten(), an=False)

    async def beim_start(self) -> None:
        """Nach einem Neustart der Anwendung: jedes Konto nachsehen -- auch
        bei ausgeschaltetem Dienst, damit die Liste stimmt --, dann an, wenn
        er an war."""
        for wallet in self.wallets():
            try:
                self._fehlt(wallet)
            except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
                # Core startet vielleicht noch. Dann faellt eine fehlende
                # Wallet beim ersten Lesen auf.
                log.info("Electrum: %s noch nicht geladen: %s",
                         wallet, fehler)
        if (self.zustand.laden().electrumwahl or {}).get("an"):
            await self.einschalten()

    def anstossen(self, block: bool = True) -> None:
        """Aus dem ZMQ-Zulauf (einem Faden) oder nach einer Anmeldung."""
        server = self._server
        if server is not None:
            server.anstossen(block)

    # ── Fuer die Oberflaeche ───────────────────────────────────────────────

    def lage(self, heimnetz_bind: Optional[str] = None,
             heimnetz_port: Optional[str] = None) -> Dict:
        with self._sperre:
            suchend = set(self._suchend)
            aktiv = self._aktiv
            fehler = dict(self._fehler)
        konten = []
        for k in self._konten():
            wallet = k.get("wallet", "")
            wartet = wallet in suchend and wallet != aktiv
            fortschritt = None
            if wallet in suchend and not wartet:
                try:
                    fortschritt = lesewallet.fortschritt(self.knoten, wallet)
                except (rpc.NichtErreichbar, rpc.RpcFehler):
                    fortschritt = None
            konten.append({**k, "sucht": wallet in suchend, "wartet": wartet,
                           "fortschritt": fortschritt,
                           "fehler": fehler.get(wallet)})
        tls = None
        if Path(electrumserver.zertifikat_datei(self.tls_verzeichnis)).exists():
            tls = {"pem": electrumserver.zertifikat_pem(self.tls_verzeichnis),
                   "fingerabdruck": electrumserver.fingerabdruck(
                       self.tls_verzeichnis)}
        return {
            "an": bool((self.zustand.laden().electrumwahl or {}).get("an")),
            "laeuft": self.laeuft,
            "konten": konten,
            "hoechstens": KONTEN_HOECHSTENS,
            "arten": list(lesewallet.ARTEN),
            "heimnetz": fernzugang.vpn_lage(heimnetz_bind, heimnetz_port),
            "tls": tls,
        }
