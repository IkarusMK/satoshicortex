"""Konto und Anmeldung.

Vor dem Umbau war jeder Endpunkt offen: wer die Adresse im Heimnetz kannte,
konnte den Knoten einrichten -- und einen laufenden Knoten umkonfigurieren.
Deshalb steht die Kontoanlage jetzt VOR dem Assistenten. Wer das Geraet
einrichtet, beansprucht es zuerst.

Bewusst ohne zusaetzliche Abhaengigkeit: scrypt steckt in der Standardbibliothek
und ist fuer Passwoerter geeignet. Ein Passwort-Hash aus einer schnellen
Hashfunktion waere hier fahrlaessig.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from . import storage
from typing import Dict, Optional

# scrypt-Parameter. n=2**15 braucht rund 32 MB und einen Sekundenbruchteil --
# fuer eine Anmeldung unmerklich, fuer das Durchprobieren von Passwoertern teuer.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCHLUESSEL_LAENGE = 32
# OpenSSL begrenzt den scrypt-Speicher standardmaessig auf 32 MB -- genau der
# Bedarf dieser Parameter (128 * n * r). Ohne ein ausdrueckliches maxmem
# scheitert das Anlegen eines Kontos mit "memory limit exceeded".
SCRYPT_MAXMEM = 128 * SCRYPT_N * SCRYPT_R * 2

MIN_PASSWORTLAENGE = 10
SITZUNG_GUELTIG_SEKUNDEN = 12 * 60 * 60

# Schutz gegen Durchprobieren: nach zu vielen Fehlversuchen wird gebremst.
MAX_FEHLVERSUCHE = 8
SPERRE_SEKUNDEN = 300


def _merkmal(token: str) -> str:
    """Was von einer Sitzung auf die Platte darf.

    Nicht das Sitzungsmerkmal selbst, sondern sein SHA-256. Wer die Datei
    liest, haelt damit kein gueltiges Merkmal in der Hand. Ein schneller Hash
    genuegt hier -- anders als bei Passwoertern gibt es nichts zu erraten:
    das Merkmal ist bereits 256 Bit Zufall.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hashe(passwort: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    schluessel = hashlib.scrypt(
        passwort.encode("utf-8"), salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCHLUESSEL_LAENGE,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${schluessel.hex()}"


def pruefe_passwort(gespeichert: str, passwort: str) -> bool:
    try:
        art, n, r, p, salt_hex, erwartet_hex = gespeichert.split("$")
        if art != "scrypt":
            return False
        schluessel = hashlib.scrypt(
            passwort.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(erwartet_hex)),
            maxmem=128 * int(n) * int(r) * 2,
        )
    except (ValueError, TypeError):
        return False
    # Zeitkonstanter Vergleich -- sonst verraet die Laufzeit den Hash Stueck fuer Stueck.
    return hmac.compare_digest(schluessel.hex(), erwartet_hex)


@dataclass
class Konto:
    benutzer: str
    hash: str
    angelegt_am: float


class Kontoverwaltung:
    def __init__(self, verzeichnis: str) -> None:
        self.pfad = Path(verzeichnis)
        storage.lege_ablage_an(str(self.pfad))
        self.datei = self.pfad / "konto.json"
        self.sitzungsdatei = self.pfad / "sitzungen.json"
        self._sitzungen: Dict[str, float] = self._lade_sitzungen()
        self._fehlversuche: Dict[str, list] = {}

    # -------------------------------------------------------- Sitzungen
    def _lade_sitzungen(self) -> Dict[str, float]:
        """Sitzungen ueberdauern einen Neustart des Containers.

        Vorher lagen sie ausschliesslich im Arbeitsspeicher. Jedes Update --
        und jeder Neustart des Stapels -- meldete den Nutzer damit ab, ohne
        dass eine offene Seite es merkte: Sie lief in 401 und zeigte "die
        Anwendung antwortet nicht", waehrend der Container einwandfrei
        antwortete. Genau das hat den Assistenten im Speicher-Schritt
        festgesetzt.
        """
        try:
            roh = json.loads(self.sitzungsdatei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(roh, dict):
            return {}
        jetzt = time.time()
        return {
            m: a for m, a in roh.items()
            if isinstance(m, str) and isinstance(a, (int, float)) and a > jetzt
        }

    def _speichere_sitzungen(self) -> None:
        temp = self.sitzungsdatei.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self._sitzungen), encoding="utf-8")
        # Erst die Rechte, dann sichtbar machen -- wie bei der Kontodatei.
        os.chmod(temp, 0o600)
        os.replace(temp, self.sitzungsdatei)

    # ------------------------------------------------------------- Konto
    @property
    def vorhanden(self) -> bool:
        return self.datei.exists()

    def lade(self) -> Optional[Konto]:
        if not self.vorhanden:
            return None
        try:
            d = json.loads(self.datei.read_text(encoding="utf-8"))
            return Konto(d["benutzer"], d["hash"], d.get("angelegt_am", 0))
        except (json.JSONDecodeError, KeyError):
            return None

    def lege_an(self, benutzer: str, passwort: str) -> None:
        if self.vorhanden:
            raise PermissionError("konto_existiert")
        benutzer = (benutzer or "").strip()
        if not 2 <= len(benutzer) <= 64:
            raise ValueError("benutzer_ungueltig")
        if len(passwort) < MIN_PASSWORTLAENGE:
            raise ValueError("passwort_zu_kurz")

        temp = self.datei.with_suffix(".json.tmp")
        temp.write_text(json.dumps({
            "benutzer": benutzer, "hash": hashe(passwort), "angelegt_am": time.time(),
        }), encoding="utf-8")
        # Erst die Rechte setzen, dann sichtbar machen -- sonst gibt es ein
        # Zeitfenster, in dem der Hash fuer alle lesbar ist.
        os.chmod(temp, 0o600)
        os.replace(temp, self.datei)

    # --------------------------------------------------------- Anmeldung
    def _gesperrt(self, benutzer: str) -> bool:
        jetzt = time.time()
        versuche = [t for t in self._fehlversuche.get(benutzer, []) if jetzt - t < SPERRE_SEKUNDEN]
        self._fehlversuche[benutzer] = versuche
        return len(versuche) >= MAX_FEHLVERSUCHE

    def melde_an(self, benutzer: str, passwort: str) -> str:
        if self._gesperrt(benutzer):
            raise PermissionError("zu_viele_versuche")
        konto = self.lade()
        # Auch ohne Konto rechnen, damit die Antwortzeit nicht verraet, ob es
        # den Benutzer gibt.
        gespeichert = konto.hash if konto else hashe("platzhalter")
        passt = pruefe_passwort(gespeichert, passwort) and konto is not None \
            and hmac.compare_digest(konto.benutzer, benutzer)
        if not passt:
            self._fehlversuche.setdefault(benutzer, []).append(time.time())
            raise PermissionError("anmeldung_fehlgeschlagen")
        self._fehlversuche.pop(benutzer, None)
        token = secrets.token_urlsafe(32)
        self._sitzungen[_merkmal(token)] = time.time() + SITZUNG_GUELTIG_SEKUNDEN
        self._speichere_sitzungen()
        return token

    def sitzung_eroeffnen(self) -> str:
        """Eine Sitzung ohne Passwort -- fuer die Anmeldung ueber OIDC.

        Der Ausweisdienst hat den Menschen schon geprueft, und zwar
        gruendlicher, als wir es koennten (Pocket ID mit Passkey). Hier
        entsteht nur noch die Sitzung, die daraus folgt.

        Bewusst OHNE Benutzernamen: wer hereindarf, entscheidet der
        Ausweisdienst ueber seine Gruppenfreigabe -- ein zweites Namensregister
        hier waere eine zweite Wahrheit, die mit der ersten auseinanderlaeuft.
        """
        token = secrets.token_urlsafe(32)
        self._sitzungen[_merkmal(token)] = time.time() + SITZUNG_GUELTIG_SEKUNDEN
        self._speichere_sitzungen()
        return token

    def melde_ab(self, token: Optional[str]) -> None:
        if token and self._sitzungen.pop(_merkmal(token), None) is not None:
            self._speichere_sitzungen()

    def angemeldet(self, token: Optional[str]) -> bool:
        if not token:
            return False
        merkmal = _merkmal(token)
        ablauf = self._sitzungen.get(merkmal)
        if ablauf is None:
            return False
        if ablauf < time.time():
            self._sitzungen.pop(merkmal, None)
            self._speichere_sitzungen()
            return False
        return True


# ── Die Freigabe: das Schloss vor jeder Geldbewegung ───────────────────────
#
# Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also knoten
# oeffnen oder schliessen geld transferieren".
#
# SIE SCHUETZT GEGEN ETWAS ANDERES ALS DER TRESOR, und darin liegt der ganze
# Grund, warum es beide gibt:
#
#   Tresor  gegen jemanden mit der PLATTE. Dort sitzt kein Waechter davor --
#           er kopiert die Datei und raet auf seinem eigenen Rechner, so oft
#           er mag. Deshalb muss dort eine echte Passphrase stehen, und
#           deshalb ist die Ableitung dort absichtlich teuer.
#   PIN     gegen eine uebernommene SITZUNG in dieser Weboberflaeche. Hier
#           sitzt ein Waechter davor und zaehlt mit. Genau deshalb reichen
#           sechs Stellen -- und NUR deshalb.
#
# Der Waechter ist damit kein Beiwerk, sondern die Voraussetzung. Faellt er,
# ist eine sechsstellige PIN in Minuten durch: eine Million Moeglichkeiten
# sind fuer einen Rechner nichts.
#
# Zwei Dinge folgen daraus, und beide stehen unten im Code:
#
#   1. Die Wartezeit waechst mit jedem Fehlversuch, bevor die Sperre
#      ueberhaupt greift. Ein Waechter, der nur zaehlt, laesst die ersten
#      Versuche beliebig schnell zu.
#   2. Der Zaehler ueberlebt einen Neustart. Laege er nur im Arbeitsspeicher,
#      haette jeder Neustart wieder fuenf freie Versuche geschenkt -- und
#      einen Neustart kann ausloesen, wer an der Oberflaeche haengt.

PIN_MIN_STELLEN = 5
PIN_MAX_STELLEN = 12
PIN_MAX_VERSUCHE = 5
PIN_SPERRE_SEKUNDEN = 900
# Was nach dem n-ten Fehlversuch zu warten ist. Die letzte Zahl gilt, bis die
# Sperre greift.
PIN_WARTEN = (2, 5, 15, 60)


class FreigabeAbgelehnt(Exception):
    """Die PIN passt nicht."""


class FreigabeGesperrt(Exception):
    """Zu oft danebengegriffen -- jetzt ist erst einmal Ruhe."""


def pruefe_pin(pin: str) -> str:
    """Wirft ValueError, wenn daraus kein Schloss wird."""
    p = (pin or "").strip()
    if not p.isdigit():
        raise ValueError("pin_nur_ziffern")
    if not PIN_MIN_STELLEN <= len(p) <= PIN_MAX_STELLEN:
        raise ValueError("pin_laenge")
    if len(set(p)) == 1:
        raise ValueError("pin_zu_einfoermig")
    # Eine Reihe -- vorwaerts wie rueckwaerts. "123456" ist die haeufigste
    # PIN der Welt, und der Waechter haelt sie nicht auf: sie steht bei
    # jedem Angreifer an erster Stelle.
    ziffern = [int(z) for z in p]
    schritte = {b - a for a, b in zip(ziffern, ziffern[1:])}
    if schritte in ({1}, {-1}):
        raise ValueError("pin_ist_eine_reihe")
    return p


class Freigabe:
    """Die PIN als Datei -- mit einem Waechter, der einen Neustart ueberlebt."""

    def __init__(self, verzeichnis: str) -> None:
        self.pfad = Path(verzeichnis)
        storage.lege_ablage_an(str(self.pfad))
        self.datei = self.pfad / "freigabe.json"

    # -------------------------------------------------------------- Ablage
    @property
    def vorhanden(self) -> bool:
        """Die DATEI ist der Massstab, nicht ihr Inhalt.

        Waere eine kaputte Datei "keine PIN", faele das Schloss vor dem Geld
        weg -- und zwar lautlos. Lieber gar nichts freigeben als
        versehentlich alles.
        """
        return self.datei.exists()

    def _lies(self) -> Dict:
        try:
            d = json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return d if isinstance(d, dict) else {}

    def _schreib(self, eintrag: Dict) -> None:
        temp = self.datei.with_suffix(".json.tmp")
        temp.write_text(json.dumps(eintrag), encoding="utf-8")
        # Erst die Rechte, dann sichtbar machen.
        os.chmod(temp, 0o600)
        os.replace(temp, self.datei)

    # -------------------------------------------------------------- Waechter
    def _versuche(self) -> list:
        jetzt = time.time()
        roh = self._lies().get("versuche") or []
        return [t for t in roh
                if isinstance(t, (int, float)) and jetzt - t < PIN_SPERRE_SEKUNDEN]

    def wartet_noch(self) -> float:
        """Wie viele Sekunden noch zu warten sind. 0 heisst: jetzt."""
        versuche = self._versuche()
        if not versuche:
            return 0.0
        if len(versuche) >= PIN_MAX_VERSUCHE:
            return max(0.0, versuche[-1] + PIN_SPERRE_SEKUNDEN - time.time())
        frist = PIN_WARTEN[min(len(versuche), len(PIN_WARTEN)) - 1]
        return max(0.0, versuche[-1] + frist - time.time())

    def _merke_fehlversuch(self) -> None:
        eintrag = self._lies()
        eintrag["versuche"] = self._versuche() + [time.time()]
        self._schreib(eintrag)

    def _frei(self) -> None:
        eintrag = self._lies()
        if eintrag.pop("versuche", None) is not None:
            self._schreib(eintrag)

    # ------------------------------------------------------------ Handgriffe
    def einrichten(self, pin: str) -> None:
        if self.vorhanden:
            raise PermissionError("pin_existiert")
        pruefe_pin(pin)
        self._schreib({"hash": hashe(pin), "angelegt_am": time.time()})

    def pruefe(self, pin: str) -> bool:
        if self.wartet_noch() > 0:
            raise FreigabeGesperrt("zu_viele_versuche")
        gespeichert = self._lies().get("hash") or ""
        if not gespeichert or not pruefe_passwort(gespeichert, pin or ""):
            self._merke_fehlversuch()
            raise FreigabeAbgelehnt("pin_falsch")
        self._frei()
        return True

    def aendern(self, alt: str, neu: str) -> None:
        pruefe_pin(neu)
        self.pruefe(alt)
        self._schreib({"hash": hashe(neu), "angelegt_am": time.time()})

    def entfernen(self, pin: str) -> None:
        """Nur, wer sie kennt, darf sie abschaffen."""
        self.pruefe(pin)
        self.datei.unlink(missing_ok=True)
