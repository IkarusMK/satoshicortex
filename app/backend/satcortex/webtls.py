"""Das Zertifikat fuer den eigenen HTTPS-Port der Weboberflaeche.

DER BEFUND VOM 15.11.2026 (Sicherheitspruefung): Seed-Woerter, Schluessel fuer
externe Wallets (Macaroons) und die PIN laufen ueber den HTTP-Port im
Klartext durchs Heimnetz, solange kein Reverse Proxy mit TLS davor steht. Der
Eigentuemer hat entschieden: SatoshiCortex bringt sein eigenes, selbst
signiertes Zertifikat mit.

Das hier ist NUR das Zertifikat. Dass es einen zweiten Port gibt und der alte
unveraendert bleibt, steht in __main__.py -- und dort steht auch, warum.

Die Vorlage ist electrumserver._zertifikat_anlegen (EC P-256, Schluessel
0600). Sie ist hier bewusst KOPIERT und nicht geteilt: jenes Zertifikat
gehoert einem anderen Dienst mit anderem Namen, anderer Ablage und anderem
Lebenslauf, und eine gemeinsame Hilfsfunktion haette beide aneinander
gekettet.

Warum selbst signiert, obwohl settings.py seit je dagegen argumentiert (die
Sicherheitswarnung beim ersten Aufruf erzieht zum Wegklicken): die Warnung
bleibt, aber sie ist jetzt ueberpruefbar -- die Oberflaeche zeigt den
Fingerabdruck, der Browser zeigt ihn bei "Zertifikat ansehen" auch, und wer
beide vergleicht, hat die Sache geklaert. Und wer die Warnung scheut, hat den
Klartext-Port weiter.
"""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
import logging
import os
import re
import ssl
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

log = logging.getLogger("satcortex.webtls")

# Namen, die es immer gibt: der Dienstname aus dem Compose-Netz und der eigene
# Rechner. Die Adresse im Heimnetz kennt nur der Eigentuemer -- sie kommt aus
# WEBUI_TLS_NAMES.
DNS_VORGABE = ("satcortex", "localhost")
IP_VORGABE = ("127.0.0.1",)

# Zehn Jahre. Ein Zertifikat, das nach einem Jahr ablaeuft, stuende dem
# Eigentuemer irgendwann mit einer Warnung im Weg, deren Ursache er nicht
# kennt -- und er hat keine Zertifizierungsstelle, die erneuert.
LAUFZEIT_TAGE = 3650
# Wer ein Zertifikat hat, das in weniger als dieser Zeit ablaeuft, bekommt beim
# Start ein neues -- statt mit dem Ablauf eine Warnung im Browser zu erzeugen.
ERNEUERN_VOR_ABLAUF_TAGE = 30

# Obergrenze fuer die zusaetzlichen Namen. Ein Zertifikat mit hundert Namen ist
# kein Wunsch, sondern ein Tippfehler -- und die Liste kommt aus einer
# Umgebungsvariablen.
MAX_NAMEN = 20

_DNS_TEIL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\Z")


class Dateien(NamedTuple):
    zertifikat: str
    schluessel: str
    # Wurde es gerade eben angelegt? Fuer die Meldung beim Start.
    neu: bool


def verzeichnis(config_dir: str) -> str:
    # Neben die Konfiguration, nicht in "tls/": dort legt der Eigentuemer seine
    # eigenen Dateien ab (TLS_CERT=/fast/config/tls/fullchain.pem), und eine
    # Anwendung, die dort schreibt, ueberschriebe sie womoeglich.
    return str(Path(config_dir) / "webtls")


def zertifikat_datei(verz: str) -> str:
    return str(Path(verz) / "web-zertifikat.pem")


def schluessel_datei(verz: str) -> str:
    return str(Path(verz) / "web-schluessel.pem")


# ----------------------------------------------------------------------- Namen

def _gueltiger_dns_name(name: str) -> bool:
    if not name or len(name) > 253 or not name.isascii():
        return False
    teile = name.split(".")
    if not all(_DNS_TEIL.match(t) for t in teile):
        return False
    # "1.2.3" und "999.1.1.1" sehen aus wie Adressen und sind keine Namen.
    return not all(t.isdigit() for t in teile)


def lese_namen(text: Optional[str]) -> Tuple[List[str], List[str], List[str]]:
    """Die zusaetzlichen Namen aus WEBUI_TLS_NAMES: (DNS, IP, abgelehnt).

    Kommagetrennt, GEPRUEFT. Was nicht passt, wird nicht stillschweigend
    uebergangen, sondern in der dritten Liste zurueckgegeben -- der Aufrufer
    sagt es im Protokoll. Ungueltiges bricht den Start nicht ab: der Zugang
    soll wegen eines Tippfehlers in einer Namensliste nicht ausbleiben.
    """
    dns: List[str] = []
    ips: List[str] = []
    abgelehnt: List[str] = []
    for roh in (text or "").split(","):
        eintrag = roh.strip()
        if not eintrag:
            continue
        if len(dns) + len(ips) >= MAX_NAMEN:
            abgelehnt.append(eintrag)
            continue
        try:
            ip = str(ipaddress.ip_address(eintrag.strip("[]")))
        except ValueError:
            name = eintrag.lower()
            if _gueltiger_dns_name(name):
                if name not in dns:
                    dns.append(name)
            else:
                abgelehnt.append(eintrag)
            continue
        if ip not in ips:
            ips.append(ip)
    return dns, ips, abgelehnt


# ------------------------------------------------------------------ Zertifikat

def fingerabdruck(zertifikat: str) -> Optional[str]:
    """SHA-256 des Zertifikats, wie Browser ihn zeigen: Doppelpunkte, Grossbuchstaben.

    None, wenn die Datei fehlt oder kein Zertifikat ist -- die Oberflaeche
    zeigt dann einfach keinen.
    """
    try:
        der = ssl.PEM_cert_to_DER_cert(Path(zertifikat).read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    roh = hashlib.sha256(der).hexdigest().upper()
    return ":".join(roh[i:i + 2] for i in range(0, len(roh), 2))


def _anlegen(verz: str, dns: List[str], ips: List[str],
             jetzt: datetime.datetime) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    Path(verz).mkdir(parents=True, exist_ok=True)
    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "SatoshiCortex Weboberflaeche")])
    namen = ([x509.DNSName(d) for d in dns]
             + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips])
    zertifikat = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        # Einen Tag zurueck: ein Geraet, dessen Uhr etwas nachgeht, soll das
        # Zertifikat nicht als "noch nicht gueltig" abweisen.
        .not_valid_before(jetzt - datetime.timedelta(days=1))
        .not_valid_after(jetzt + datetime.timedelta(days=LAUFZEIT_TAGE))
        .add_extension(x509.SubjectAlternativeName(namen), critical=False)
        # Ein Blatt, KEINE Zertifizierungsstelle. Wer es im Geraet als
        # vertrauenswuerdig einhaengt, soll damit nicht auch fremde Namen
        # beglaubigen koennen.
        .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                       critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                       critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(
            schluessel.public_key()), critical=False)
        .sign(schluessel, hashes.SHA256())
    )
    # Ein Rest aus einem abgebrochenen frueheren Lauf wuerde O_EXCL zum
    # Scheitern bringen -- und er gehoert ohnehin ersetzt.
    for alt in (schluessel_datei(verz), zertifikat_datei(verz)):
        try:
            os.unlink(alt)
        except FileNotFoundError:
            pass
    # Der private Schluessel nur fuer den Eigentuemer -- und zwar von Anfang
    # an, nicht erst nach einem chmod, zwischen dem und dem Schreiben er kurz
    # fuer alle lesbar waere. O_EXCL: legt jemand zwischen unlink und open
    # eine Datei oder einen Verweis dorthin, scheitert das lautstark, statt
    # durch ihn hindurch an eine fremde Stelle zu schreiben.
    fd = os.open(schluessel_datei(verz),
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as datei:
        datei.write(schluessel.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    # Das Zertifikat ist oeffentlich: es geht an jeden Browser, der anklopft.
    fd = os.open(zertifikat_datei(verz),
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as datei:
        datei.write(zertifikat.public_bytes(serialization.Encoding.PEM))
    # Die Umask darf das 0644 nicht enger machen als gemeint -- aber auch nicht
    # weiter; der Schluessel steht bei 0600 und bleibt dort.
    os.chmod(zertifikat_datei(verz), 0o644)


def _taugt(verz: str, dns: List[str], ips: List[str],
           jetzt: datetime.datetime) -> bool:
    """Ist das vorhandene Zertifikat brauchbar -- lesbar, passend, gueltig,
    mit allen gewuenschten Namen?"""
    from cryptography import x509

    try:
        zert = x509.load_pem_x509_certificate(
            Path(zertifikat_datei(verz)).read_bytes())
        # Passt der Schluessel zum Zertifikat? Das prueft der Ladevorgang, so
        # wie uvicorn es gleich tun wird -- schlaegt es hier fehl, dort auch.
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
            zertifikat_datei(verz), schluessel_datei(verz))
        san = zert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
    except (OSError, ValueError, ssl.SSLError, x509.ExtensionNotFound):
        return False
    if zert.not_valid_after_utc - jetzt < datetime.timedelta(
            days=ERNEUERN_VOR_ABLAUF_TAGE):
        return False
    if zert.not_valid_before_utc > jetzt + datetime.timedelta(days=2):
        return False
    vorhanden_dns = set(san.get_values_for_type(x509.DNSName))
    vorhanden_ip = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    # Nur "fehlt etwas Gewuenschtes" ist ein Grund. Mehr Namen im Zertifikat
    # als gewuenscht schadet nicht, und ein Wechsel aendert den Fingerabdruck,
    # den der Eigentuemer sich gemerkt haben koennte.
    return set(dns) <= vorhanden_dns and set(ips) <= vorhanden_ip


def sicherstellen(verz: str, namen: Optional[str], *,
                  jetzt: Optional[datetime.datetime] = None) -> Dateien:
    """Das Zertifikat bereitstellen: vorhandenes weiterverwenden, sonst anlegen.

    `verz` ist das Verzeichnis der Dateien (siehe verzeichnis()). Neu angelegt
    wird nur, wenn etwas fehlt, nicht lesbar ist, nicht zusammenpasst, in
    weniger als ERNEUERN_VOR_ABLAUF_TAGE ablaeuft oder ein gewuenschter Name
    nicht darin steht. Wirft OSError, wenn die Ablage nicht beschreibbar ist --
    der Aufrufer entscheidet, was dann gilt.
    """
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    extra_dns, extra_ip, abgelehnt = lese_namen(namen)
    for a in abgelehnt:
        log.warning("WEBUI_TLS_NAMES: %r ist kein gueltiger Name und kein "
                    "gueltige Adresse -- uebergangen.", a)
    dns = list(DNS_VORGABE) + [d for d in extra_dns if d not in DNS_VORGABE]
    ips = list(IP_VORGABE) + [i for i in extra_ip if i not in IP_VORGABE]
    if _taugt(verz, dns, ips, jetzt):
        return Dateien(zertifikat_datei(verz), schluessel_datei(verz), False)
    _anlegen(verz, dns, ips, jetzt)
    log.info("Neues Zertifikat fuer die Weboberflaeche angelegt (%s).",
             ", ".join(dns + ips))
    return Dateien(zertifikat_datei(verz), schluessel_datei(verz), True)


def dateien_fuer(konf) -> Optional[Dateien]:
    """Welches Zertifikat der zweite Port benutzt -- oder None, wenn es ihn
    nicht gibt.

    Eigene Dateien aus TLS_CERT/TLS_KEY haben Vorrang: wer Zertifikate hat,
    nimmt sie. Sonst das selbst erzeugte aus der Ablage.
    """
    if not konf.webui_tls_an:
        return None
    if konf.tls_aktiv:
        return Dateien(konf.tls_cert, konf.tls_key, False)
    return sicherstellen(verzeichnis(konf.config_dir), konf.webui_tls_namen)


def fingerabdruck_fuer(konf) -> Optional[str]:
    """Der Fingerabdruck fuer die Oberflaeche -- nur LESEN.

    Der oeffentliche Zustandsabruf darf kein Zertifikat anlegen; das tut der
    Start. Gibt es keines (zweiter Port aus, Start noch nicht durch), ist die
    Antwort None und die Oberflaeche zeigt keinen Fingerabdruck.
    """
    if not konf.webui_tls_an:
        return None
    pfad = (konf.tls_cert if konf.tls_aktiv
            else zertifikat_datei(verzeichnis(konf.config_dir)))
    return fingerabdruck(pfad)
