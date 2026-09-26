"""Die Onion-Dienste des Knotens -- gehalten von Tor selbst.

BIS 0.62.0 legten bitcoind und LND ihre Onion-Dienste selbst an: sie meldeten
sich an Tors Steuerport und schickten ADD_ONION. Am 17.09.2026 hat sich
gezeigt, dass daran drei Dinge hingen, und keins davon war zu halten:

1. Die Dienste zeigten ins Leere. Ohne ausdrueckliches Ziel setzt Tor
   127.0.0.1 ein -- seinen eigenen Container. Die Einzelheiten stehen in
   netz.py.

2. Nach einem Neustart von Tor waren LNDs Dienste weg. ADD_ONION legt einen
   FLUECHTIGEN Dienst an, der mit Tor endet. LND hat zwar eine Pruefung, die
   ihn wieder anlegt -- aber abgeschaltet: healthcheck.torconnection.attempts
   steht in v0.21.3-beta auf 0 (config.go: defaultTCAttempts = 0), und
   healthcheck.go ueberspringt jede Pruefung mit null Versuchen. Selbst
   eingeschaltet legte sie nur den Kanal-Dienst neu an, nicht den des
   Wachturms (server.go, createNewHiddenService). Tor startet aber
   regelmaessig neu: bei jeder geaenderten Konfiguration und bei jedem neuen
   Abbild.

3. Tors Steuerport stand dafuer im ganzen Compose-Netz offen. Die
   Cookie-Datei, die ihn schuetzen sollte, liegt unter /fast/tor -- und /fast
   sieht jeder Container, auch die Weboberflaeche.

JETZT stehen die Dienste in Tors eigener Konfiguration (HiddenServiceDir).
Tor legt sie bei jedem Start von selbst an, gleich wer wann neu startet, und
den Steuerport braucht niemand mehr -- er ist zu. bitcoind und LND erfahren
ihre Adresse aus der Datei "hostname", die Tor daneben schreibt, und
kuendigen sie als externalip an. So machen es auch andere Container-Knoten
seit Jahren (Umbrel: HiddenServicePort auf feste Container-Adressen).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

from . import fernzugang, netz

log = logging.getLogger(__name__)

# Unter /fast. Tors DataDirectory -- so steht es in der torrc.
TOR_VERZEICHNIS = "tor"
# Derselbe Ort, wie ihn der TOR-Container sieht. Die torrc spricht dessen
# Sprache, nicht die der Anwendung (in den Tests liegt /fast woanders).
TOR_PFAD_IM_CONTAINER = "/fast/tor"


@dataclass(frozen=True)
class Dienst:
    name: str
    verzeichnis: str        # HiddenServiceDir unter /fast/tor
    port: int               # unter diesem Port erreicht man die .onion
    ziel: str               # der Container dahinter (netz.HOSTTEIL)
    zielport: int           # und dort dieser Port
    alter_schluessel: Tuple[str, ...]   # wo der Dienst ihn bis 0.62.0 ablegte
    zweck: str


DIENSTE: Dict[str, Dienst] = {d.name: d for d in (
    # 8334, nicht 8333. Core nimmt auf 8334 an, was aus dem Onion-Netz kommt
    # ("bind=...:8334=onion"), und weiss dann, woher die Gegenstelle stammt.
    # Ueber 8333 hereingereicht hielte er sie fuer einen Nachbarn aus dem
    # Compose-Netz.
    Dienst("bitcoind", "onion-bitcoind", 8333, "bitcoind", 8334,
           ("bitcoind", "onion_v3_private_key"),
           "Bitcoin: Gegenstellen aus dem Onion-Netz"),
    Dienst("lnd", "onion-lnd", 9735, "lnd", 9735,
           ("lnd", "v3_onion_private_key"),
           "Lightning: Kanaele und Weiterleitungen"),
    # Eine EIGENE Adresse fuer den Wachturm, wie LND es selbst hielt: ueber
    # die Turm-Adresse soll niemand auf den Knoten schliessen koennen.
    Dienst("wachturm", "onion-wachturm", 9911, "lnd", 9911,
           ("lnd", "data", "watchtower", "v3_onion_private_key"),
           "Wachturm: bewacht die Kanaele anderer"),
    # Seit dem 26.09.2026: LNDs REST-Schnittstelle fuer externe Wallets
    # (Zeus). Ein Dienst anderer Art als die drei oben -- er wird NIE
    # angekuendigt, steht deshalb nicht in REIHENFOLGE und nicht in
    # dienste_fuer. Seine Adresse kennt nur, wem man den Verbindungstext
    # gibt. Eine eigene Adresse, damit niemand von ihr auf den Knoten
    # schliessen kann. Einen alten Schluessel gibt es nicht: den Dienst gab
    # es vor 0.63.0 nicht.
    Dienst("fernzugang", "onion-fernzugang", fernzugang.ONION_PORT, "lnd",
           8080, (), "Externe Wallets: LNDs Schnittstelle fuer Zeus"),
)}

# Die Reihenfolge, in der sie in der torrc stehen -- fest, damit dieselbe
# Wahl immer dieselbe Datei ergibt. Sonst sahe der Waechter bei jedem Blick
# eine "geaenderte" Konfiguration und startete Tor ohne Anlass neu.
REIHENFOLGE = ("bitcoind", "lnd", "wachturm")

# Was zusaetzlich in der torrc stehen kann, ohne angekuendigt zu werden.
# IMMER hinter den dreien oben: so bleibt die torrc aller, die ihn nicht
# nutzen, Byte fuer Byte, wie sie war -- sonst startete jedes Update Tor neu.
FERNZUGANG = "fernzugang"
ZUSATZDIENSTE = (FERNZUGANG,)

HOSTNAME = "hostname"
SCHLUESSELDATEI = "hs_ed25519_secret_key"
# crypto_write_tagged_contents_to_file (crypto_format.c, Tor 0.4.9.11):
# "== %s: %s ==" mit typestring und tag, mit Nullen auf 32 Byte aufgefuellt.
# typestring "ed25519v1-secret" (crypto_ed25519.c), tag "type0" (loadkey.c).
SCHLUESSELKOPF = b"== ed25519v1-secret: type0 ==".ljust(32, b"\0")

_ADRESSE = re.compile(r"[a-z2-7]{56}\.onion")


def dienste_fuer(tor_an: bool, sichtbarkeit: str) -> Tuple[str, ...]:
    """Welche Onion-Dienste es bei dieser Wahl gibt.

    Nur bei "tor" und "hybrid". "still" heisst laut Oberflaeche "weder
    .onion noch IP" -- bis 0.62.0 legte bitcoind dort trotzdem eine .onion
    an und kuendigte sie an.
    """
    if tor_an and sichtbarkeit in ("tor", "hybrid"):
        return REIHENFOLGE
    return ()


def ist_onion(adresse: str) -> bool:
    """Ist das eine .onion -- mit oder ohne Port?"""
    host = str(adresse).strip()
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    return host.lower().endswith(".onion")


def ist_gueltig(adresse: str) -> bool:
    """Eine v3-Adresse mit stimmender Pruefsumme.

    Die Datei "hostname" schreibt Tor. Geprueft wird trotzdem, und nicht nur
    auf die Form: der Wert wandert in die Konfiguration von bitcoind und LND,
    und dort hat nichts zu suchen, was nicht genau eine Adresse ist.
    Pruefsumme nach rend-spec-v3, 6. Encoding onion addresses.
    """
    if not _ADRESSE.fullmatch(adresse or ""):
        return False
    roh = base64.b32decode(adresse[:56].upper())
    schluessel, pruefsumme, version = roh[:32], roh[32:34], roh[34:]
    if version != b"\x03":
        return False
    erwartet = hashlib.sha3_256(
        b".onion checksum" + schluessel + version).digest()[:2]
    return pruefsumme == erwartet


def verzeichnis(fast: str, name: str) -> Path:
    return Path(fast) / TOR_VERZEICHNIS / DIENSTE[name].verzeichnis


def lies_adresse(fast: str, name: str) -> str:
    """Die .onion eines Dienstes, wie Tor sie hinterlegt hat -- oder ""."""
    try:
        text = (verzeichnis(fast, name) / HOSTNAME).read_text(
            encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    return text if ist_gueltig(text) else ""


def abwarten(fast: str, namen: Iterable[str], frist: float,
             schlaf: Callable[[float], None] = time.sleep,
             uhr: Callable[[], float] = time.monotonic) -> Dict[str, str]:
    """Bis zu "frist" Sekunden warten, bis Tor alle Adressen hinterlegt hat.

    Tor schreibt "hostname" beim Laden der Dienste, lange bevor es sich mit
    dem Netz verbunden hat -- nach einem Neustart meist binnen Sekunden.
    Zurueck kommt, was da ist; was fehlt, steht als "".
    """
    namen = tuple(namen)
    ende = uhr() + frist
    while True:
        gefunden = {n: lies_adresse(fast, n) for n in namen}
        if all(gefunden.values()) or uhr() >= ende:
            return gefunden
        schlaf(0.5)


def torrc_block(namen: Iterable[str], praefix: str) -> str:
    """Die HiddenService-Zeilen fuer die gewaehlten Dienste."""
    zeilen = []
    for name in REIHENFOLGE + ZUSATZDIENSTE:
        if name not in set(namen):
            continue
        d = DIENSTE[name]
        zeilen += [
            f"# {d.zweck}",
            f"HiddenServiceDir {TOR_PFAD_IM_CONTAINER}/{d.verzeichnis}",
            f"HiddenServicePort {d.port} "
            f"{netz.adresse(praefix, d.ziel)}:{d.zielport}",
            "",
        ]
    if not zeilen:
        return ("# Keine Onion-Dienste: der Knoten kuendigt sich in dieser "
                "Betriebsart\n# nicht ueber Tor an.")
    return "\n".join(zeilen).rstrip()


def schluessel_aus_altbestand(roh: bytes) -> Optional[bytes]:
    """Den geheimen Schluessel aus dem Format, das Core und LND ablegten.

    Beide speicherten, was Tor ihnen auf ADD_ONION zurueckgab:
    "ED25519-V3:" und dahinter die 64 Byte des erweiterten Schluessels in
    Base64 (Core: torcontrol.cpp, add_onion_cb; LND: tor/cmd_onion.go,
    StorePrivateKey). Tor liest den Blob in genau die Struktur, die es auch
    in hs_ed25519_secret_key ablegt (control_cmd.c: base64_decode in
    sk->seckey). Es ist also dasselbe Material -- nur anders verpackt.

    None, wenn es nicht so aussieht. LND kann den Schluessel verschluesselt
    ablegen (tor.encryptkey); den kann hier niemand lesen, und das ist
    richtig so.
    """
    try:
        text = roh.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    art, _, blob = text.partition(":")
    if art != "ED25519-V3" or not blob:
        return None
    try:
        schluessel = base64.b64decode(blob + "=" * (-len(blob) % 4),
                                      validate=True)
    except (binascii.Error, ValueError):
        return None
    return schluessel if len(schluessel) == 64 else None


def uebernimm_schluessel(fast: str, name: str) -> bool:
    """Den Schluessel von 0.62.0 an Tor uebergeben -- damit die Adresse bleibt.

    Nur, wenn Tor fuer diesen Dienst noch KEINEN Schluessel hat. Ein
    vorhandener wird nie ueberschrieben: das waere ein Adresswechsel ohne
    Not, und im schlimmsten Fall der Verlust einer Adresse, die jemand
    schon eingetragen hat.

    Muss VOR dem Schreiben der torrc laufen. Faende Tor den Dienst ohne
    Schluessel vor, legte es einen neuen an -- und die alte Adresse waere weg.
    """
    ziel_dir = verzeichnis(fast, name)
    ziel = ziel_dir / SCHLUESSELDATEI
    if ziel.exists() or not DIENSTE[name].alter_schluessel:
        return False
    quelle = Path(fast).joinpath(*DIENSTE[name].alter_schluessel)
    try:
        roh = quelle.read_bytes()
    except OSError:
        return False
    schluessel = schluessel_aus_altbestand(roh)
    if schluessel is None:
        log.warning("Onion-Schluessel fuer %s unter %s nicht lesbar -- Tor "
                    "legt eine neue Adresse an.", name, quelle)
        return False

    ziel_dir.mkdir(parents=True, exist_ok=True)
    # Tor verlangt 0700 und denselben Eigentuemer (dir.c, check_private_dir).
    # Die Anwendung laeuft unter derselben Kennung wie Tor.
    os.chmod(ziel_dir, 0o700)
    # Reste, die nicht zum Schluessel passen, liessen Tor den Start
    # verweigern: "%s does not match %s!" (loadkey.c). Tor schreibt beide
    # aus dem geheimen Schluessel neu.
    for rest in ("hs_ed25519_public_key", HOSTNAME):
        (ziel_dir / rest).unlink(missing_ok=True)
    temp = ziel_dir / (SCHLUESSELDATEI + ".neu")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as datei:
        datei.write(SCHLUESSELKOPF + schluessel)
    os.chmod(temp, 0o600)
    os.replace(temp, ziel)
    log.info("Onion-Schluessel fuer %s an Tor uebergeben -- die Adresse "
             "bleibt dieselbe.", name)
    return True
