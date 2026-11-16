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
import threading
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
# MAX_FEHLVERSUCHE gilt je GEGENSTELLE (siehe "Fehlversuche" unten), die
# gemeinsame Decke darueber ist MAX_FEHLVERSUCHE_GESAMT.
MAX_FEHLVERSUCHE = 8
SPERRE_SEKUNDEN = 300
# Die gemeinsame Decke: fuenf Gegenstellen mit je voller Sperre. Darueber
# wird nicht mehr gesperrt, sondern getaktet -- ein Versuch alle
# BREMSE_TAKT_SEKUNDEN fuer ALLE zusammen.
MAX_FEHLVERSUCHE_GESAMT = 5 * MAX_FEHLVERSUCHE
BREMSE_TAKT_SEKUNDEN = 10
# Wie viele Gegenstellen sich die Platte merkt. Mehr braucht ein Heimnetz
# nicht; wer so viele Adressen aufbringt, verdraengt hoechstens aeltere
# Eintraege -- die gemeinsame Decke haelt trotzdem.
MAX_ABSENDER = 256


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
        # Ein Schloss ueber Pruefen UND Zaehlen. Ohne es liefen beide
        # auseinander -- siehe melde_an().
        self._schloss = threading.Lock()
        # Ein eigenes Schloss fuer die Kontoanlage -- siehe lege_an().
        self._konto_schloss = threading.Lock()
        # Wann zuletzt ein Versuch durch die Bremse der gemeinsamen Decke
        # gelassen wurde. None = noch nie; nur im Speicher, ein Neustart
        # schenkt hoechstens EINEN Versuch.
        self._letzte_bremse: Optional[float] = None
        self.fehlerdatei = self.pfad / "fehlversuche.json"
        self._fehlversuche: Dict[str, list] = self._lade_fehlversuche()

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

    # ---------------------------------------------------- Fehlversuche
    #
    # DER BEFUND VOM 22.09.2026, drei Teile:
    #
    # 1. Gezaehlt wurde unter dem Namen, den der Angreifer TIPPT. Der Eintrag
    #    wuchs damit unbegrenzt -- ein Anmeldeversuch je neuem Namen genuegte,
    #    unangemeldet, auf einem Behaelter mit 400 MB Grenze, der genau daran
    #    schon einmal gestorben ist. Eine blosse Obergrenze waere die falsche
    #    Behebung: dann liesse sich der Eintrag des ECHTEN Namens
    #    hinausdraengen und seine Sperre damit aufheben. Es gibt genau EIN
    #    Konto, also gibt es zwei Toepfe: dieses Konto und alles andere.
    #
    # 2. Die Sperre lag nur im Arbeitsspeicher -- waehrend Sitzungen
    #    ausdruecklich auf die Platte geschrieben werden, weil "ein Neustart
    #    sich aus der Oberflaeche ausloesen laesst". Fuer die Sperre gilt das
    #    genauso, und dort wiegt es mehr.
    #
    # 3. Pruefen und Zaehlen liefen ohne Schloss, und dazwischen liegt scrypt.
    #    Gemessen: sechs gleichzeitige Versuche kamen ALLE an der Sperre
    #    vorbei, wo einer durchgehen darf.
    #
    # DER BEFUND VOM 15.11.2026: auch die zwei Toepfe waren ZU GROB. Es gab
    # nur einen fuer das echte Konto -- acht falsche Passwoerter von IRGENDEINEM
    # Rechner im Heimnetz sperrten den Besitzer fuer 300 Sekunden aus, und
    # das beliebig oft wiederholbar (gemessen mit einer Schleife ueber die
    # Schnittstelle, ein einziger fremder Laptop genuegte). Auf einem Geraet,
    # dessen Anmeldung die Tuer zu einer Wallet ist, ist "jeder im LAN kann
    # den Besitzer aussperren" ein echter Mangel, auch wenn kein Geld fliesst.
    #
    # Jetzt wird je GEGENSTELLE gezaehlt -- die unmittelbare Adresse der
    # Verbindung, die api.py uebergibt. NIE ein X-Forwarded-For: den schreibt
    # der Angreifer selbst, und er koennte damit entweder die eigene Sperre
    # umgehen oder fremde Adressen aussperren.
    #
    # Das allein loeste das Durchprobieren nicht mehr global: wer viele
    # Adressen hat, bekaeme je Adresse acht Versuche. Darum gibt es eine
    # gemeinsame Decke (MAX_FEHLVERSUCHE_GESAMT). Sie SPERRT NICHT -- das
    # waere dieselbe Aussperrung in grossem -- sie TAKTET: darueber geht je
    # BREMSE_TAKT_SEKUNDEN genau ein Versuch durch, fuer alle zusammen. Der
    # Besitzer mit dem richtigen Passwort kommt damit immer herein (nach
    # hoechstens einem Takt, in dem er es erneut versucht), ein Angreifer
    # bleibt auf 6 Versuche pro Minute begrenzt. Der Preis: ein Angreifer,
    # der DAUERND in den Takt hineinfeuert, kann dem Besitzer den freien Platz
    # wegnehmen; dafuer braucht er aber mindestens fuenf eigene Adressen im
    # selben Netz -- und der Besitzer hat die Nottuer ueber die Dateien auf
    # der NAS. Im Betrieb hinter einem Proxy sehen wir fuer alle Besucher
    # dieselbe Gegenstelle (die des Proxys); dort bleibt die Sperre
    # faktisch gemeinsam, und mit Ausweisdienst ist dieser Weg ohnehin zu.
    #
    # Beschraenkt bleibt die Platte: hoechstens MAX_ABSENDER Eintraege plus
    # die Decke, aeltere werden verdraengt.
    UNBEKANNT = "\x00andere"
    GLOBAL = "\x00gesamt"
    _TRENNER = "\x1f"

    def _topf(self, benutzer: str) -> str:
        """Unter welchem Schluessel ein Fehlversuch gezaehlt wird."""
        konto = self.lade()
        if konto and hmac.compare_digest(konto.benutzer.encode("utf-8"),
                                         (benutzer or "").encode("utf-8")):
            return konto.benutzer
        return self.UNBEKANNT

    def _lade_fehlversuche(self) -> Dict[str, list]:
        try:
            roh = json.loads(self.fehlerdatei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(roh, dict):
            return {}
        return {k: [t for t in v if isinstance(t, (int, float))]
                for k, v in roh.items() if isinstance(v, list)}

    # DER BEFUND VOM 15.11.2026, nachgezogen beim Zusammenfuehren am
    # 16.11.2026: hier stand "Erst die Rechte, dann sichtbar machen" -- und
    # gemacht wurde write_text (0666 & ~umask, meist 0644), DANACH chmod. Der
    # Inhalt lag also kurz lesbar da. Jetzt wie bei allen Geheimnissen ueber
    # storage.schreibe_privat: 0600 ab dem ersten Byte.
    def _speichere_fehlversuche(self) -> None:
        storage.schreibe_privat(self.fehlerdatei,
                                json.dumps(self._fehlversuche))

    def _speichere_sitzungen(self) -> None:
        storage.schreibe_privat(self.sitzungsdatei,
                                json.dumps(self._sitzungen))

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
        # DER BEFUND VOM 15.11.2026: Pruefen, scrypt und Ersetzen liefen ohne
        # Schloss, und dazwischen liegt scrypt. Zwei gleichzeitige Aufrufe
        # kamen beide am "vorhanden" vorbei, schrieben in dieselbe .tmp-Datei
        # und der zweite ueberschrieb das Konto des ersten -- gemessen mit
        # vier Threads. Das erste Konto ist der Anspruch auf das Geraet.
        #
        # Das Schloss gilt fuer diesen Prozess (ein einziger Arbeiter); die
        # Zwischendatei bekommt trotzdem einen eigenen Namen und wird mit
        # O_EXCL angelegt, damit nie zwei in dieselbe schreiben.
        benutzer = (benutzer or "").strip()
        with self._konto_schloss:
            if self.vorhanden:
                raise PermissionError("konto_existiert")
            if not 2 <= len(benutzer) <= 64:
                raise ValueError("benutzer_ungueltig")
            if len(passwort) < MIN_PASSWORTLAENGE:
                raise ValueError("passwort_zu_kurz")
            inhalt = json.dumps({
                "benutzer": benutzer, "hash": hashe(passwort),
                "angelegt_am": time.time(),
            }).encode("utf-8")
            temp = self.datei.with_name(f"konto.json.{secrets.token_hex(8)}.tmp")
            # Von Anfang an mit 0600 -- ein nachtraegliches chmod liesse ein
            # Zeitfenster, in dem der Hash fuer alle lesbar ist.
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(inhalt)
                os.replace(temp, self.datei)
            except BaseException:
                try:
                    os.unlink(temp)
                except OSError:
                    pass
                raise

    # --------------------------------------------------------- Anmeldung
    def _gesperrt(self, schluessel: str) -> bool:
        jetzt = time.time()
        versuche = [t for t in self._fehlversuche.get(schluessel, [])
                    if jetzt - t < SPERRE_SEKUNDEN]
        self._fehlversuche[schluessel] = versuche
        return len(versuche) >= MAX_FEHLVERSUCHE

    def _raeume_auf(self, jetzt: float) -> None:
        """Abgelaufenes entfernen und die Zahl der Eintraege begrenzen.

        Ohne das wuchse die Datei mit jeder fremden Adresse -- siehe den
        Befund oben. Verdraengt wird, wer am laengsten nichts mehr versucht
        hat.
        """
        for schluessel in list(self._fehlversuche):
            frisch = [t for t in self._fehlversuche[schluessel]
                      if jetzt - t < SPERRE_SEKUNDEN]
            if frisch:
                self._fehlversuche[schluessel] = frisch
            else:
                del self._fehlversuche[schluessel]
        absender = [k for k in self._fehlversuche if k != self.GLOBAL]
        ueber = len(absender) - (MAX_ABSENDER - 1)
        if ueber > 0:
            absender.sort(key=lambda k: max(self._fehlversuche[k]))
            for k in absender[:ueber]:
                del self._fehlversuche[k]

    def melde_an(self, benutzer: str, passwort: str, quelle: str = "") -> str:
        """quelle: die unmittelbare Gegenstelle der Verbindung -- siehe den
        Befund vom 15.11.2026 oben. Leer heisst "unbekannt" und teilt sich
        einen Eintrag."""
        # Pruefen und Zaehlen in EINEM Zug, unter dem Schloss -- und der
        # Versuch wird VOR der teuren Rechnung vermerkt, nicht danach. Genau
        # der Abstand dazwischen war die Luecke: scrypt braucht seine Zeit,
        # und in dieser Zeit kamen alle gleichzeitigen Versuche an einer
        # Sperre vorbei, die keiner von ihnen schon hochgezaehlt hatte.
        topf = self._topf(benutzer)
        schluessel = f"{topf}{self._TRENNER}{quelle or ''}"
        with self._schloss:
            jetzt = time.time()
            self._raeume_auf(jetzt)
            if self._gesperrt(schluessel):
                raise PermissionError("zu_viele_versuche")
            if len(self._fehlversuche.get(self.GLOBAL, [])) \
                    >= MAX_FEHLVERSUCHE_GESAMT:
                # Die gemeinsame Decke: nicht sperren, takten.
                if self._letzte_bremse is not None \
                        and jetzt - self._letzte_bremse < BREMSE_TAKT_SEKUNDEN:
                    raise PermissionError("zu_viele_versuche_gesamt")
                self._letzte_bremse = jetzt
            self._fehlversuche.setdefault(schluessel, []).append(jetzt)
            self._fehlversuche.setdefault(self.GLOBAL, []).append(jetzt)
            self._speichere_fehlversuche()

        konto = self.lade()
        # Auch ohne Konto rechnen, damit die Antwortzeit nicht verraet, ob es
        # den Benutzer gibt.
        gespeichert = konto.hash if konto else hashe("platzhalter")
        passt = pruefe_passwort(gespeichert, passwort) and konto is not None \
            and hmac.compare_digest(konto.benutzer.encode("utf-8"),
                                    (benutzer or "").encode("utf-8"))
        if not passt:
            raise PermissionError("anmeldung_fehlgeschlagen")
        with self._schloss:
            self._fehlversuche.pop(schluessel, None)
            # Dieser Versuch war keiner: aus der gemeinsamen Zaehlung nehmen,
            # sonst bremste jede gelungene Anmeldung die naechste.
            gesamt = self._fehlversuche.get(self.GLOBAL, [])
            if jetzt in gesamt:
                gesamt.remove(jetzt)
            self._speichere_fehlversuche()
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
# Aus dem Betrieb, 08.09.2026: eine eigene PIN fuer alles, was Geld bewegt --
# Kanaele oeffnen und schliessen, Zahlungen, Ueberweisungen.
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
# So viele Sitzungen fuehrt der Zaehler hoechstens -- die Datei bleibt klein.
PIN_MAX_SITZUNGEN = 64
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
    """Die PIN als Datei -- mit einem Waechter, der einen Neustart ueberlebt.

    DER BEFUND VOM 15.11.2026: der Waechter zaehlte EINMAL fuer alle. Wer eine
    Sitzung uebernommen hatte, brauchte nur zwei falsche Versuche, und die
    richtige PIN des Eigentuemers bekam ein 429 -- bis zu 900 Sekunden,
    ueber einen Neustart hinweg. Die uebernommene Sitzung sperrte also den
    aus, gegen den sie geschuetzt werden sollte.

    Jetzt zaehlt jede Sitzung fuer sich, unter dem SHA-256 ihres Merkmals (nie
    dem Merkmal selbst, wie bei den Sitzungen). Eine gestohlene Sitzung sperrt
    nur sich. Die Stufen und die lange Sperre bleiben, je Sitzung.

    Der Zaehler liegt in einer EIGENEN Datei, nicht in freigabe.json: "vorhanden"
    bedeutet, dass die PIN-Datei da ist, und der Zaehler muss auch dort
    zaehlen, wo es KEINE PIN gibt -- dort verlangt das Tor das Kontopasswort
    und braucht dieselbe Bremse.

    Beschraenkt ist die Datei auf PIN_MAX_SITZUNGEN Eintraege; abgelaufene
    fallen beim Schreiben heraus, bei Ueberlauf die aeltesten. Sitzungen
    entstehen nur durch eine Anmeldung, die Zahl ist also ohnehin klein.
    """

    def __init__(self, verzeichnis: str) -> None:
        self.pfad = Path(verzeichnis)
        storage.lege_ablage_an(str(self.pfad))
        self.datei = self.pfad / "freigabe.json"
        self.zaehlerdatei = self.pfad / "freigabe_versuche.json"
        # Dasselbe Schloss wie bei der Anmeldung, aus demselben Grund -- hier
        # wiegt es sogar mehr: dieser Zaehler steht zwischen einer
        # uebernommenen Sitzung und den sechs Wegen, die Geld bewegen.
        self._schloss = threading.Lock()

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
        # Mit 0600 von der Anlage an -- siehe storage.schreibe_privat.
        storage.schreibe_privat(self.datei, json.dumps(eintrag))

    # -------------------------------------------------------------- Waechter
    def _lies_zaehler(self) -> Dict[str, list]:
        jetzt = time.time()
        try:
            roh = json.loads(self.zaehlerdatei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(roh, dict):
            return {}
        ergebnis: Dict[str, list] = {}
        for schluessel, liste in roh.items():
            if not isinstance(liste, list):
                continue
            frisch = [t for t in liste if isinstance(t, (int, float))
                      and jetzt - t < PIN_SPERRE_SEKUNDEN]
            if frisch:
                ergebnis[str(schluessel)] = frisch
        return ergebnis

    def _schreib_zaehler(self, zaehler: Dict[str, list]) -> None:
        if len(zaehler) > PIN_MAX_SITZUNGEN:
            # Die mit dem juengsten letzten Versuch bleiben.
            neueste = sorted(zaehler, key=lambda k: zaehler[k][-1],
                             reverse=True)[:PIN_MAX_SITZUNGEN]
            zaehler = {k: zaehler[k] for k in neueste}
        storage.schreibe_privat(self.zaehlerdatei, json.dumps(zaehler))

    def _versuche(self, sitzung: str = "") -> list:
        return self._lies_zaehler().get(_merkmal(sitzung or ""), [])

    def wartet_noch(self, sitzung: str = "") -> float:
        """Wie viele Sekunden noch zu warten sind. 0 heisst: jetzt."""
        versuche = self._versuche(sitzung)
        if not versuche:
            return 0.0
        if len(versuche) >= PIN_MAX_VERSUCHE:
            return max(0.0, versuche[-1] + PIN_SPERRE_SEKUNDEN - time.time())
        frist = PIN_WARTEN[min(len(versuche), len(PIN_WARTEN)) - 1]
        return max(0.0, versuche[-1] + frist - time.time())

    def _merke_fehlversuch(self, sitzung: str) -> None:
        zaehler = self._lies_zaehler()
        schluessel = _merkmal(sitzung or "")
        zaehler[schluessel] = zaehler.get(schluessel, []) + [time.time()]
        self._schreib_zaehler(zaehler)

    def _frei(self, sitzung: str) -> None:
        zaehler = self._lies_zaehler()
        if zaehler.pop(_merkmal(sitzung or ""), None) is not None:
            self._schreib_zaehler(zaehler)

    # ------------------------------------------------------------ Handgriffe
    def einrichten(self, pin: str) -> None:
        if self.vorhanden:
            raise PermissionError("pin_existiert")
        pruefe_pin(pin)
        self._schreib({"hash": hashe(pin), "angelegt_am": time.time()})

    def _versuch(self, sitzung: str, stimmt) -> bool:
        """Sperre pruefen, Versuch vermerken, DANN rechnen -- je Sitzung.

        DER BEFUND VOM 22.09.2026: Warten-pruefen, rechnen, zaehlen waren drei
        Schritte ohne Schloss, und der mittlere ist scrypt -- ein langer
        Augenblick. Mehrere gleichzeitige Versuche lasen denselben Stand und
        schrieben ihn wieder; gemessen wurden bei fuenf Versuchen drei bis
        vier Eintraege. Der Rest fiel unter den Tisch.

        Deshalb: Sperre pruefen UND Versuch vermerken in einem Zug unter dem
        Schloss, danach erst die teure Rechnung, und bei Erfolg wieder unter
        dem Schloss aufraeumen.

        (Die erste Behebung dieses Befundes hat nur die Anmeldung erfasst und
        diese Klasse vergessen. Der oertliche Lauf war gruen -- ein Wettlauf
        trifft nicht zuverlaessig --, CI hat es gefangen.)

        `stimmt` ist die Pruefung selbst (PIN oder Kontopasswort); beide
        teilen den Zaehler der Sitzung -- zwei Tueren mit zwei Zaehlern waeren
        eine Bremse mit einer zweiten Tuer daneben.
        """
        with self._schloss:
            if self.wartet_noch(sitzung) > 0:
                raise FreigabeGesperrt("zu_viele_versuche")
            self._merke_fehlversuch(sitzung)

        if not stimmt():
            raise FreigabeAbgelehnt("pin_falsch")
        with self._schloss:
            self._frei(sitzung)
        return True

    def pruefe(self, pin: str, sitzung: str = "") -> bool:
        """Die PIN pruefen -- und den Versuch zaehlen, bevor gerechnet wird."""
        gespeichert = self._lies().get("hash") or ""
        return self._versuch(
            sitzung,
            lambda: bool(gespeichert) and pruefe_passwort(gespeichert,
                                                          pin or ""))

    def pruefe_konto(self, passwort: str, konto_hash: str,
                     sitzung: str = "") -> bool:
        """Ersatz, solange keine PIN steht: das Kontopasswort -- am selben
        Zaehler wie die PIN."""
        return self._versuch(
            sitzung,
            lambda: bool(konto_hash) and pruefe_passwort(konto_hash,
                                                         passwort or ""))

    def aendern(self, alt: str, neu: str, sitzung: str = "") -> None:
        pruefe_pin(neu)
        self.pruefe(alt, sitzung)
        self._schreib({"hash": hashe(neu), "angelegt_am": time.time()})

    def entfernen(self, pin: str, sitzung: str = "") -> None:
        """Nur, wer sie kennt, darf sie abschaffen."""
        self.pruefe(pin, sitzung)
        self.datei.unlink(missing_ok=True)
