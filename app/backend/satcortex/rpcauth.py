"""Zugangsdaten fuer die Bitcoin-Core-RPC-Schnittstelle.

Der Nutzer bekommt diese Werte nie zu Gesicht und muss sie nirgends eintragen.
In die bitcoin.conf wandert nur der Hash; das Klartext-Passwort bleibt in der
internen Konfiguration der Anwendung, weil die Dienste damit sprechen muessen.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import NamedTuple


class RpcZugang(NamedTuple):
    benutzer: str
    passwort: str
    rpcauth: str


def erzeuge(benutzer: str = "satcortex") -> RpcZugang:
    """Erzeugt Benutzer, Passwort und die passende rpcauth-Zeile.

    Format wie in Bitcoin Cores eigenem rpcauth.py:
        <benutzer>:<salt>$<HMAC-SHA256(salt, passwort)>
    """
    passwort = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    signatur = hmac.new(
        salt.encode("utf-8"), passwort.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return RpcZugang(
        benutzer=benutzer,
        passwort=passwort,
        rpcauth=f"{benutzer}:{salt}${signatur}",
    )


def pruefe(rpcauth: str, benutzer: str, passwort: str) -> bool:
    """Prueft eine rpcauth-Zeile gegen Benutzer und Klartext-Passwort."""
    try:
        name, rest = rpcauth.split(":", 1)
        salt, signatur = rest.split("$", 1)
    except ValueError:
        return False
    if name != benutzer:
        return False
    erwartet = hmac.new(
        salt.encode("utf-8"), passwort.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(erwartet, signatur)
