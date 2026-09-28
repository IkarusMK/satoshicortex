"""Der Electrum-Server im Netz: Verbindungen, Zeilen, TLS, Benachrichtigungen.

Was die Befehle antworten, steht in electrum.py. Hier steht nur, was an der
Leitung passiert:

  * JSON-RPC 2.0, eine Nachricht je Zeile, auch als Buendel.
  * TLS UND Klartext auf demselben Port. Beide Apps koennen beides; am ersten
    Byte ist zu erkennen, was kommt -- ein TLS-Handschlag beginnt mit 0x16,
    eine JSON-Zeile mit "{" oder "[". Das Byte wird nur angesehen, nicht
    gelesen, und die Verbindung dann passend an asyncio uebergeben.
  * Benachrichtigungen: nach einem Anstoss (neuer Block, neue Transaktion --
    aus dem ZMQ-Zulauf, also aus einem anderen Faden) und sonst im Takt.
    Mit kurzer Verzoegerung: Cores Wallet zieht einen Moment nach (an der
    Regtest-Kette gemessen), und ein neuer Block bringt Dutzende Anstoesse
    auf einmal, die EINE Auffrischung ergeben sollen.

Grenzen, weil der Port im Heimnetz und ueber Tor erreichbar ist: hoechstens
16 Verbindungen, Zeilen bis 1 MB (eine grosse Transaktion als Hex passt),
Buendel bis 100 Eintraege, Trennung nach zehn Minuten Stille -- so sieht es
auch die Spezifikation vor.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import hashlib
import json
import logging
import os
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

from . import electrum, kontobuch, lesewallet, rpc

log = logging.getLogger(__name__)

TLS_ERSTES_BYTE = b"\x16"

_PARSE = -32700
_ANFRAGE = -32600
_INTERN = -32603


# ── Das Zertifikat ─────────────────────────────────────────────────────────
#
# Selbst ausgestellt: fuer einen Dienst im eigenen Heimnetz gibt es keine
# Stelle, die es beglaubigen koennte. Die BitBoxApp nimmt dafuer das
# Zertifikat selbst entgegen und prueft genau dieses (block-client-go,
# "Expecting a self-signed cert"). Die Oberflaeche zeigt es deshalb samt
# Fingerabdruck zum Kopieren.

def zertifikat_datei(verzeichnis: str) -> str:
    return str(Path(verzeichnis) / "electrum-zertifikat.pem")


def schluessel_datei(verzeichnis: str) -> str:
    return str(Path(verzeichnis) / "electrum-schluessel.pem")


def _zertifikat_anlegen(verzeichnis: str) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    Path(verzeichnis).mkdir(parents=True, exist_ok=True)
    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "SatoshiCortex Electrum")])
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    zertifikat = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - datetime.timedelta(days=1))
        .not_valid_after(jetzt + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName("satcortex")]), critical=False)
        .sign(schluessel, hashes.SHA256())
    )
    # Der private Schluessel nur fuer den Eigentuemer -- und zwar von Anfang
    # an, nicht erst nach einem chmod, zwischen dem und dem Schreiben er
    # kurz fuer alle lesbar waere.
    fd = os.open(schluessel_datei(verzeichnis),
                 os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as datei:
        datei.write(schluessel.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    Path(zertifikat_datei(verzeichnis)).write_bytes(
        zertifikat.public_bytes(serialization.Encoding.PEM))


def tls_kontext(verzeichnis: str) -> ssl.SSLContext:
    """Der TLS-Kontext des Servers; das Zertifikat entsteht beim ersten Mal."""
    if not (Path(zertifikat_datei(verzeichnis)).exists()
            and Path(schluessel_datei(verzeichnis)).exists()):
        _zertifikat_anlegen(verzeichnis)
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.minimum_version = ssl.TLSVersion.TLSv1_2
    kontext.load_cert_chain(zertifikat_datei(verzeichnis),
                            schluessel_datei(verzeichnis))
    return kontext


def zertifikat_pem(verzeichnis: str) -> str:
    return Path(zertifikat_datei(verzeichnis)).read_text(encoding="ascii")


def fingerabdruck(verzeichnis: str) -> str:
    """SHA-256 des Zertifikats, wie Browser und Apps ihn zeigen."""
    der = ssl.PEM_cert_to_DER_cert(zertifikat_pem(verzeichnis))
    roh = hashlib.sha256(der).hexdigest().upper()
    return ":".join(roh[i:i + 2] for i in range(0, len(roh), 2))


# ── Der Bestand: Kontobuch, zwischengespeichert ────────────────────────────

class Bestand:
    """Haelt das Kontobuch bereit, statt es bei jeder Frage neu zu lesen.

    Eine App fragt beim Verbinden Dutzende Skripthashes ab; jede Frage
    einzeln an Core weiterzureichen hiesse, die Wallets Dutzende Male zu
    lesen. Aufgefrischt wird nach einem Anstoss und im Takt -- und beim
    naechsten Blick, wenn der Stand als veraltet gilt.

    Scheitert das Lesen, bleibt der alte Stand stehen. Eine leere Wallet
    saehe aus, als waere das Geld weg.
    """

    def __init__(self, leser) -> None:
        self.leser = leser
        self._sperre = threading.Lock()
        self._stand = None
        self._frisch = False
        self._leer = (kontobuch.Buch([]), frozenset())

    def _lesen(self) -> None:
        try:
            self._stand = self.leser.lesen()
            self._frisch = True
        except (rpc.NichtErreichbar, rpc.RpcFehler, KeyError, ValueError,
                lesewallet.LeseFehler):
            log.warning("Electrum: Kontobuch nicht aufgefrischt",
                        exc_info=True)

    def aktuell(self):
        with self._sperre:
            if not self._frisch:
                self._lesen()
            return self._stand or self._leer

    def auffrischen(self) -> None:
        with self._sperre:
            self._lesen()

    def veraltet(self) -> None:
        with self._sperre:
            self._frisch = False


# ── Der Server ─────────────────────────────────────────────────────────────

@dataclass(eq=False)
class _Verbindung:
    writer: asyncio.StreamWriter
    sitzung: electrum.Sitzung = field(default_factory=electrum.Sitzung)
    # Anfragen und Benachrichtigungen derselben Sitzung nie gleichzeitig:
    # beide lesen und schreiben ihre Abos.
    sperre: asyncio.Lock = field(default_factory=asyncio.Lock)


def _fehler(code: int, meldung: str, kennung: Any = None) -> Dict:
    return {"jsonrpc": "2.0", "id": kennung,
            "error": {"code": code, "message": meldung}}


class ElectrumServer:

    def __init__(self, dienst: electrum.Dienst, bestand, tls: Optional[ssl.SSLContext],
                 host: str = "0.0.0.0", port: int = 50001,  # nosec B104 -- im Container
                 verbindungen_hoechstens: int = 16,
                 zeile_hoechstens: int = 1_000_000,
                 buendel_hoechstens: int = 100,
                 verzoegerung: float = 1.0,
                 mempool_abstand: float = 5.0,
                 takt: float = 30.0,
                 leerlauf: float = 600.0,
                 handschlag: float = 15.0) -> None:
        self.dienst = dienst
        self.bestand = bestand
        self.tls = tls
        self.host = host
        self.port = port
        self.verbindungen_hoechstens = verbindungen_hoechstens
        self.zeile_hoechstens = zeile_hoechstens
        self.buendel_hoechstens = buendel_hoechstens
        self.verzoegerung = verzoegerung
        self.mempool_abstand = mempool_abstand
        self.takt = takt
        self._block_neu = False
        self._zuletzt = 0.0             # monotonic der letzten Auffrischung
        self.leerlauf = leerlauf
        self.handschlag = handschlag
        self._verbindungen: Set[_Verbindung] = set()
        self._aufgaben: Set[asyncio.Task] = set()
        self._sock: Optional[socket.socket] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._anstoss: Optional[asyncio.Event] = None

    # ── Lebenslauf ─────────────────────────────────────────────────────────

    async def starten(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._anstoss = asyncio.Event()
        self._sock = socket.create_server((self.host, self.port))
        self._sock.setblocking(False)
        self.port = self._sock.getsockname()[1]
        self._aufgabe(self._annehmen())
        self._aufgabe(self._benachrichtigen())
        log.info("Electrum-Server lauscht auf %s:%s (TLS %s)", self.host,
                 self.port, "an" if self.tls else "aus")

    async def beenden(self) -> None:
        for aufgabe in list(self._aufgaben):
            aufgabe.cancel()
        for aufgabe in list(self._aufgaben):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await aufgabe
        for v in list(self._verbindungen):
            v.writer.close()
        if self._sock is not None:
            self._sock.close()

    def anstossen(self, block: bool = True) -> None:
        """Neuer Block oder neue Transaktion -- aus JEDEM Faden aufrufbar.

        Ein Block wird gleich weitergegeben (nach der kurzen Verzoegerung,
        in der Cores Wallet nachzieht); der Mempool gedrosselt.
        """
        if self._loop is None or self._anstoss is None:
            return
        self._loop.call_soon_threadsafe(self._anstoss_setzen, block)

    def _anstoss_setzen(self, block: bool) -> None:
        self._block_neu = self._block_neu or block
        self._anstoss.set()

    def _aufgabe(self, koroutine) -> asyncio.Task:
        aufgabe = asyncio.get_running_loop().create_task(koroutine)
        self._aufgaben.add(aufgabe)
        aufgabe.add_done_callback(self._aufgaben.discard)
        return aufgabe

    # ── Verbindungen ───────────────────────────────────────────────────────

    async def _annehmen(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            client, _adresse = await loop.sock_accept(self._sock)
            if len(self._verbindungen) >= self.verbindungen_hoechstens:
                log.info("Electrum: Verbindung abgewiesen, schon %d offen",
                         len(self._verbindungen))
                client.close()
                continue
            self._aufgabe(self._verbindung(client))

    async def _spaehen(self, client: socket.socket) -> bytes:
        """Das erste Byte ansehen, ohne es zu lesen."""
        loop = asyncio.get_running_loop()
        fertig: asyncio.Future = loop.create_future()
        fd = client.fileno()

        def bereit() -> None:
            try:
                daten = client.recv(1, socket.MSG_PEEK)
            except BlockingIOError:
                return
            except OSError:
                daten = b""
            if not fertig.done():
                fertig.set_result(daten)

        loop.add_reader(fd, bereit)
        try:
            return await asyncio.wait_for(fertig, self.handschlag)
        finally:
            loop.remove_reader(fd)

    async def _verbindung(self, client: socket.socket) -> None:
        client.setblocking(False)
        try:
            erstes = await self._spaehen(client)
        except (asyncio.TimeoutError, OSError):
            client.close()
            return
        tls = erstes == TLS_ERSTES_BYTE
        if not erstes or (tls and self.tls is None):
            client.close()
            return
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=self.zeile_hoechstens)
        protokoll = asyncio.StreamReaderProtocol(reader)
        try:
            transport, _ = await loop.connect_accepted_socket(
                lambda: protokoll, sock=client,
                ssl=self.tls if tls else None,
                ssl_handshake_timeout=self.handschlag if tls else None)
        except (ssl.SSLError, OSError, asyncio.TimeoutError) as fehler:
            log.info("Electrum: Handschlag gescheitert: %s", fehler)
            client.close()
            return
        verbindung = _Verbindung(asyncio.StreamWriter(
            transport, protokoll, reader, loop))
        # Ohne verbundene App wird nicht aufgefrischt; wer neu kommt, soll
        # nicht den Stand von vor Stunden sehen.
        self.bestand.veraltet()
        self._verbindungen.add(verbindung)
        try:
            await self._lesen(reader, verbindung)
        finally:
            self._verbindungen.discard(verbindung)
            verbindung.writer.close()

    async def _lesen(self, reader: asyncio.StreamReader,
                     verbindung: _Verbindung) -> None:
        while not verbindung.sitzung.schliessen:
            try:
                zeile = await asyncio.wait_for(reader.readline(),
                                               self.leerlauf)
            except (asyncio.TimeoutError, ValueError, ConnectionError,
                    asyncio.LimitOverrunError):
                return          # Stille, zu lange Zeile oder abgerissen
            if not zeile:
                return
            if not zeile.strip():
                continue
            antwort = await self._verarbeiten(zeile, verbindung)
            if antwort is not None and not await self._senden(
                    verbindung, antwort):
                return

    async def _verarbeiten(self, zeile: bytes,
                           verbindung: _Verbindung) -> Optional[Any]:
        try:
            nachricht = json.loads(zeile)
        except (ValueError, UnicodeDecodeError):
            return _fehler(_PARSE, "unlesbares JSON")
        if isinstance(nachricht, list):
            if not nachricht or len(nachricht) > self.buendel_hoechstens:
                return _fehler(_ANFRAGE, f"Buendel mit 1 bis "
                                         f"{self.buendel_hoechstens} Eintraegen erwartet")
            antworten = [await self._eine(n, verbindung) for n in nachricht]
            antworten = [a for a in antworten if a is not None]
            return antworten or None
        return await self._eine(nachricht, verbindung)

    async def _eine(self, anfrage: Any, verbindung: _Verbindung) -> Optional[Dict]:
        if not isinstance(anfrage, dict) or not isinstance(
                anfrage.get("method"), str):
            return _fehler(_ANFRAGE, "keine gueltige Anfrage")
        kennung = anfrage.get("id")
        params = anfrage.get("params", [])
        try:
            async with verbindung.sperre:
                ergebnis = await asyncio.to_thread(
                    self.dienst.bearbeite, verbindung.sitzung,
                    anfrage["method"], params)
            antwort = {"jsonrpc": "2.0", "id": kennung, "result": ergebnis}
        except electrum.ElectrumFehler as fehler:
            antwort = _fehler(fehler.code, fehler.meldung, kennung)
        except Exception:  # noqa: BLE001 -- die App bekommt eine Antwort
            log.exception("Electrum: %s scheiterte", anfrage["method"])
            antwort = _fehler(_INTERN, "interner Fehler", kennung)
        # Ohne Kennung ist es eine Benachrichtigung der App: keine Antwort.
        return antwort if "id" in anfrage else None

    async def _senden(self, verbindung: _Verbindung, nachricht: Any) -> bool:
        try:
            verbindung.writer.write((json.dumps(nachricht) + "\n").encode())
            await asyncio.wait_for(verbindung.writer.drain(), self.handschlag)
            return True
        except (ConnectionError, asyncio.TimeoutError, OSError):
            return False

    # ── Benachrichtigungen ─────────────────────────────────────────────────

    async def _benachrichtigen(self) -> None:
        while True:
            try:
                angestossen = True
                try:
                    await asyncio.wait_for(self._anstoss.wait(), self.takt)
                except asyncio.TimeoutError:
                    angestossen = False
                if not self._verbindungen:
                    # Niemand zu benachrichtigen -- sonst liefe Core bei jedem
                    # Block und jeder Mempool-Meldung fuer niemanden.
                    self._anstoss.clear()
                    self._block_neu = False
                    continue
                warten = self.verzoegerung
                if angestossen and not self._block_neu:
                    warten = max(warten, self.mempool_abstand
                                 - (time.monotonic() - self._zuletzt))
                await asyncio.sleep(max(0.0, warten))
                self._anstoss.clear()
                self._block_neu = False
                self._zuletzt = time.monotonic()
                await asyncio.to_thread(self.bestand.auffrischen)
                for verbindung in list(self._verbindungen):
                    async with verbindung.sperre:
                        meldungen = await asyncio.to_thread(
                            self.dienst.neuigkeiten, verbindung.sitzung)
                    for methode, params in meldungen:
                        await self._senden(verbindung, {
                            "jsonrpc": "2.0", "method": methode,
                            "params": params})
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- der Melder darf nie sterben
                log.exception("Electrum: Benachrichtigen scheiterte")
                await asyncio.sleep(self.verzoegerung or 1.0)
