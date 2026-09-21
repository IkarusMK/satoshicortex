"""Anmeldung ueber einen fremden Ausweisdienst -- OpenID Connect.

Gebaut fuer Pocket ID, aber ohne eine Zeile, die nur dort stimmt: alles
Adressenwissen kommt aus der Entdeckung des Anbieters, nicht aus fest
eingetippten Pfaden. Derselbe Weg traegt damit auch Authentik oder Keycloak.

Warum die Anwendung SELBST der Ausweisnehmer ist und nicht der Reverse Proxy:
ein Tor im Proxy laesst die Anwendung dahinter unveraendert -- sie wuerde
danach IMMER NOCH ihr eigenes Anmeldefenster zeigen. Zwei Anmeldungen
hintereinander sind genau das, was hier weg soll.

Was hier NICHT steht, und warum:

* Kein eigenes JWT-Rad. Die Signatur wird mit `cryptography` geprueft --
  derselben Bibliothek, die seit dem Tresor ohnehin in den Abhaengigkeiten
  steht und seit dessen Ausbau niemand mehr benutzt hat.
* Kein "verlass dich auf TLS". Der Standard erlaubt ausdruecklich, die
  Signatur zu ueberspringen, wenn das Token direkt vom Token-Endpunkt kommt.
  Das ist hier trotzdem nicht der Weg: die Pruefung kostet nichts, und an
  einem Geraet mit einer Wallet ist der bequeme Pfad der falsche.
* Keine Zustandshaltung ueber Dateien. State, Nonce und PKCE-Beleg leben im
  Speicher und verfallen nach Minuten -- eine Anmeldung dauert keine Stunde.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

log = logging.getLogger(__name__)

# Der Pfad, unter dem JEDER OIDC-Anbieter seine Adressen nennt. Das ist der
# einzige Pfad, den wir kennen muessen -- alles andere steht darin.
ENTDECKUNG_PFAD = "/.well-known/openid-configuration"

ZEITLIMIT_SEKUNDEN = 10.0
# Die Adressen eines Anbieters aendern sich praktisch nie, seine Schluessel
# schon -- aber auch nicht im Minutentakt.
ENTDECKUNG_FRISCHE = 3600.0
SCHLUESSEL_FRISCHE = 3600.0
# Wie lange ein angefangener Anmeldevorgang gilt. Wer laenger braucht, faengt
# neu an; ein offener Vorgang ist ein offenes Fenster.
VORGANG_GUELTIG_SEKUNDEN = 600.0
# Etwas Spielraum fuer auseinanderlaufende Uhren, aber nicht mehr.
UHRSCHLUPF_SEKUNDEN = 60.0

# Was wir wissen wollen. "openid" ist Pflicht, der Rest ist der Name, der
# hinterher in der Oberflaeche steht.
UMFANG = "openid profile email"


class OidcFehler(Exception):
    """Der Ausweisdienst antwortet nicht, oder seine Antwort taugt nicht."""


@dataclass(frozen=True)
class Anbieter:
    """Alles, was eine Anmeldung braucht. Kommt aus der Umgebung."""
    issuer: str
    client_id: str
    client_secret: str
    rueckweg: str


def _hole(adresse: str, daten: Optional[bytes] = None,
          kopf: Optional[Dict[str, str]] = None) -> Dict:
    """Ein Aufruf beim Anbieter. Nur https, und nur JSON zurueck."""
    if not adresse.lower().startswith("https://"):
        # Ein Ausweisdienst ueber Klartext waere kein Ausweisdienst.
        raise OidcFehler(f"nur https: {adresse}")
    anfrage = urllib.request.Request(
        adresse, data=daten, headers=kopf or {},
        method="POST" if daten is not None else "GET")
    try:
        with urllib.request.urlopen(                      # nosec B310
                anfrage, timeout=ZEITLIMIT_SEKUNDEN) as antwort:
            return json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        # Der Grund steht im Rumpf. Ihn wegzuwerfen und nur "400" zu melden
        # ist die haeufigste Art, eine Fehlersuche zu verlaengern.
        try:
            rumpf = fehler.read().decode("utf-8", "replace")[:300]
        except OSError:
            rumpf = ""
        raise OidcFehler(f"{fehler.code}: {rumpf}") from fehler
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        raise OidcFehler(str(fehler)) from fehler


_entdeckt: Dict[str, Any] = {"issuer": "", "zeit": 0.0, "wert": {}}


def entdecke(issuer: str, jetzt: Optional[float] = None) -> Dict:
    """Die Adressen des Anbieters -- von ihm selbst, nicht von uns geraten."""
    jetzt = time.time() if jetzt is None else jetzt
    if (_entdeckt["issuer"] == issuer
            and jetzt - _entdeckt["zeit"] < ENTDECKUNG_FRISCHE):
        return _entdeckt["wert"]
    d = _hole(issuer.rstrip("/") + ENTDECKUNG_PFAD)
    # Der Anbieter muss sich selbst so nennen, wie wir ihn angeschrieben
    # haben. Sonst zeigt unsere Einstellung woandershin als gedacht.
    if str(d.get("issuer", "")).rstrip("/") != issuer.rstrip("/"):
        raise OidcFehler(
            f"nennt sich {d.get('issuer')!r}, angeschrieben war {issuer!r}")
    for pflicht in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not d.get(pflicht):
            raise OidcFehler(f"Anbieter nennt kein {pflicht}")
    _entdeckt.update(issuer=issuer, zeit=jetzt, wert=d)
    return d


_schluessel: Dict[str, Any] = {"adresse": "", "zeit": 0.0, "wert": {}}


def schluessel(jwks_uri: str, jetzt: Optional[float] = None,
               frisch: bool = False) -> Dict:
    """Die oeffentlichen Schluessel des Anbieters."""
    jetzt = time.time() if jetzt is None else jetzt
    if (not frisch and _schluessel["adresse"] == jwks_uri
            and jetzt - _schluessel["zeit"] < SCHLUESSEL_FRISCHE):
        return _schluessel["wert"]
    d = _hole(jwks_uri)
    _schluessel.update(adresse=jwks_uri, zeit=jetzt, wert=d)
    return d


def _b64u(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode("ascii")


def _b64u_zurueck(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _zahl(text: str) -> int:
    return int.from_bytes(_b64u_zurueck(text), "big")


@dataclass
class Vorgang:
    """Ein angefangener Anmeldevorgang. Lebt Minuten, nicht laenger."""
    state: str
    nonce: str
    beleg: str            # PKCE code_verifier
    begonnen: float


def beginne(anbieter: Anbieter,
            jetzt: Optional[float] = None) -> tuple:
    """Wohin der Browser geschickt wird -- und was wir uns dazu merken.

    PKCE ist hier nicht optional. Es kostet zwei Zeilen und nimmt einem
    abgefangenen Code seinen Wert.
    """
    jetzt = time.time() if jetzt is None else jetzt
    vorgang = Vorgang(state=secrets.token_urlsafe(32),
                      nonce=secrets.token_urlsafe(32),
                      beleg=secrets.token_urlsafe(48),
                      begonnen=jetzt)
    aufgabe = _b64u(hashlib.sha256(vorgang.beleg.encode("ascii")).digest())
    d = entdecke(anbieter.issuer, jetzt)
    frage = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": anbieter.client_id,
        "redirect_uri": anbieter.rueckweg,
        "scope": UMFANG,
        "state": vorgang.state,
        "nonce": vorgang.nonce,
        "code_challenge": aufgabe,
        "code_challenge_method": "S256",
    })
    trenner = "&" if "?" in d["authorization_endpoint"] else "?"
    return d["authorization_endpoint"] + trenner + frage, vorgang


def loese_ein(anbieter: Anbieter, code: str, vorgang: Vorgang,
              jetzt: Optional[float] = None) -> Dict:
    """Den Code gegen die Token tauschen.

    MIT ODER OHNE Secret. Pocket ID vergibt fuer seine Clients keins mehr --
    aus der eigenen Doku: "Only public clients are supported, so
    token_endpoint_auth_method must be none. PKCE is enabled automatically."

    Ein leeres client_secret mitzuschicken ist nicht dasselbe wie keines: ein
    Anbieter, der "none" erwartet, darf ein leeres Feld als falschen Ausweis
    werten. Also faellt es ganz weg, wenn keines eingetragen ist.

    Was den Tausch dann schuetzt, ist PKCE: der Beleg wurde nie uebertragen,
    nur sein SHA-256. Ein abgefangener Code allein nuetzt niemandem etwas --
    genau dafuer gibt es das Verfahren, und genau deshalb ist es hier von
    Anfang an nicht optional.
    """
    d = entdecke(anbieter.issuer, jetzt)
    felder = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": anbieter.rueckweg,
        "client_id": anbieter.client_id,
        "code_verifier": vorgang.beleg,
    }
    if anbieter.client_secret:
        felder["client_secret"] = anbieter.client_secret
    rumpf = urllib.parse.urlencode(felder).encode("ascii")
    return _hole(d["token_endpoint"], rumpf,
                 {"Content-Type": "application/x-www-form-urlencoded"})


def _pruefe_unterschrift(kopf: Dict, signiert: bytes, unterschrift: bytes,
                         jwks: Dict) -> None:
    """Die Signatur gegen den passenden Schluessel des Anbieters."""
    alg = kopf.get("alg")
    if alg not in ("RS256", "ES256"):
        raise OidcFehler(f"Signaturverfahren {alg!r} wird hier nicht genommen")
    kid = kopf.get("kid")
    passende = [k for k in jwks.get("keys") or []
                if not kid or k.get("kid") == kid]
    if not passende:
        raise OidcFehler("kein passender Schluessel beim Anbieter")
    for k in passende:
        try:
            if alg == "RS256":
                oeff = rsa.RSAPublicNumbers(
                    _zahl(k["e"]), _zahl(k["n"])).public_key()
                oeff.verify(unterschrift, signiert,
                            padding.PKCS1v15(), hashes.SHA256())
            else:
                oeff = ec.EllipticCurvePublicNumbers(
                    _zahl(k["x"]), _zahl(k["y"]),
                    ec.SECP256R1()).public_key()
                # ES256 unterschreibt roh (r||s), nicht in DER.
                haelfte = len(unterschrift) // 2
                from cryptography.hazmat.primitives.asymmetric.utils import (
                    encode_dss_signature)
                oeff.verify(encode_dss_signature(
                    int.from_bytes(unterschrift[:haelfte], "big"),
                    int.from_bytes(unterschrift[haelfte:], "big")),
                    signiert, ec.ECDSA(hashes.SHA256()))
            return
        except (KeyError, ValueError, TypeError):
            continue                      # naechster Schluessel
        except Exception:                 # nosec B112 - ungueltige Signatur
            continue
    raise OidcFehler("Unterschrift passt zu keinem Schluessel des Anbieters")


def pruefe_ausweis(anbieter: Anbieter, id_token: str, vorgang: Vorgang,
                   jetzt: Optional[float] = None) -> Dict:
    """Den Ausweis pruefen und seinen Inhalt herausgeben.

    Geprueft wird alles, was der Standard verlangt: Unterschrift, Aussteller,
    Empfaenger, Ablauf -- und die Nonce, die diesen Ausweis an GENAU diesen
    Anmeldevorgang bindet. Ohne sie liesse sich ein anderswo erbeuteter
    Ausweis hier einreichen.
    """
    jetzt = time.time() if jetzt is None else jetzt
    teile = id_token.split(".")
    if len(teile) != 3:
        raise OidcFehler("kein JWT")
    try:
        kopf = json.loads(_b64u_zurueck(teile[0]))
        nutz = json.loads(_b64u_zurueck(teile[1]))
        unterschrift = _b64u_zurueck(teile[2])
    except (ValueError, TypeError) as fehler:
        raise OidcFehler(f"Ausweis nicht lesbar: {fehler}") from fehler

    signiert = (teile[0] + "." + teile[1]).encode("ascii")
    d = entdecke(anbieter.issuer, jetzt)
    try:
        _pruefe_unterschrift(kopf, signiert, unterschrift,
                             schluessel(d["jwks_uri"], jetzt))
    except OidcFehler:
        # Ein Schluesselwechsel beim Anbieter ist der haeufigste Grund. Einmal
        # frisch holen, bevor wir jemanden abweisen.
        _pruefe_unterschrift(kopf, signiert, unterschrift,
                             schluessel(d["jwks_uri"], jetzt, frisch=True))

    if str(nutz.get("iss", "")).rstrip("/") != anbieter.issuer.rstrip("/"):
        raise OidcFehler("Ausweis eines anderen Ausstellers")
    empfaenger = nutz.get("aud")
    empfaenger = empfaenger if isinstance(empfaenger, list) else [empfaenger]
    if anbieter.client_id not in empfaenger:
        raise OidcFehler("Ausweis fuer einen anderen Empfaenger")
    if len(empfaenger) > 1 and nutz.get("azp") != anbieter.client_id:
        raise OidcFehler("Ausweis fuer mehrere Empfaenger, aber nicht fuer uns")
    try:
        ablauf = float(nutz.get("exp") or 0)
    except (TypeError, ValueError) as fehler:
        raise OidcFehler("Ausweis ohne Ablauf") from fehler
    if ablauf + UHRSCHLUPF_SEKUNDEN < jetzt:
        raise OidcFehler("Ausweis abgelaufen")
    if nutz.get("nonce") != vorgang.nonce:
        raise OidcFehler("Ausweis gehoert nicht zu diesem Anmeldevorgang")
    return nutz


def name_aus(nutz: Dict) -> str:
    """Wie der Mensch heissen soll, der sich da angemeldet hat."""
    for feld in ("preferred_username", "name", "email"):
        wert = (nutz.get(feld) or "").strip()
        if wert:
            return wert[:64]
    return str(nutz.get("sub") or "")[:64]
