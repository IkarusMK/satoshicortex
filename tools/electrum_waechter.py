"""Frühwarnung: sprechen BitBoxApp und Trezor Suite noch, was wir beantworten?

Aus dem Betrieb, 28.09.2026: "wie konstant ist das ganze nicht das wir da
nach 6 monaten und 3 updates nicht mehr dabei sind und raus fliegen".

Liest aus den Quellen beider Apps die Protokollversion und die Namen der
Electrum-Befehle, die sie schicken, und vergleicht mit dem, was
satcortex.electrum beantwortet. Scheitert, sobald eine App einen Befehl
schickt, den wir nicht kennen, oder eine andere Protokollversion verlangt.
Nennt dazu, welche Version electrs spricht -- der Server hinter Umbrel,
StartOS und RaspiBlitz: solange der 1.4 spricht, muessen die Apps es auch.

Gelesen wird nur, gespeichert und veroeffentlicht nichts. Trezor Suite steht
unter der Trezor Reference Source License, die genau dieses Lesen erlaubt
("enhancing the interoperability of your products with the software").

  PYTHONPATH=app/backend python tools/electrum_waechter.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Iterable, List, Set

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

TREZOR = ("trezor/trezor-suite", "packages/blockchain-link/src/workers/electrum")
BITBOX = ("BitBoxSwiss/block-client-go", "electrum/client.go")
ELECTRS = ("romanz/electrs", "src/electrum.rs")

_BEFEHL = re.compile(r"""['"]((?:blockchain|server|mempool)\.[a-z_]+(?:\.[a-z_]+)*)['"]""")
_VERSION = (
    re.compile(r"""protocolVersion:\s*['"]([\d.]+)['"]"""),           # Trezor
    re.compile(r"""supportedProtocolVersion\s*=\s*"([\d.]+)\""""),     # BitBox
    re.compile(r"""PROTOCOL_VERSION:\s*&str\s*=\s*"([\d.]+)\""""),     # electrs
)


def befehle(quelltext: str) -> Set[str]:
    return set(_BEFEHL.findall(quelltext))


def versionen(quelltext: str) -> Set[str]:
    gefunden: Set[str] = set()
    for muster in _VERSION:
        gefunden.update(muster.findall(quelltext))
    return gefunden


def vergleiche(name: str, geschickt: Set[str], verlangt: Set[str],
               beantwortet: Iterable[str], unsere_version: str) -> List[str]:
    """Die Befunde fuer eine App -- leer, wenn alles passt."""
    befunde = []
    fehlt = sorted(geschickt - set(beantwortet))
    if fehlt:
        befunde.append(f"{name} schickt Befehle, die wir nicht beantworten: "
                       + ", ".join(fehlt))
    if not verlangt:
        befunde.append(f"{name}: keine Protokollversion gefunden -- hat sich "
                       "die Stelle im Quelltext verschoben?")
    elif verlangt != {unsere_version}:
        befunde.append(f"{name} verlangt Protokoll {', '.join(sorted(verlangt))}"
                       f", wir sprechen {unsere_version}")
    if not geschickt:
        befunde.append(f"{name}: keine Befehle gefunden -- hat sich die Stelle "
                       "im Quelltext verschoben?")
    return befunde


def _holen(url: str) -> bytes:
    kopf = {"User-Agent": "satoshicortex-electrum-waechter"}
    schluessel = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if schluessel and url.startswith(API):
        kopf["Authorization"] = f"Bearer {schluessel}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=kopf),  # nosec B310
                                timeout=30) as antwort:
        return antwort.read()


def _dateien(repo: str, pfad: str) -> List[str]:
    """Alle Quelltexte unter einem Verzeichnis, ohne Tests."""
    liste = json.loads(_holen(f"{API}/repos/{repo}/contents/{pfad}"))
    dateien = []
    for eintrag in liste:
        if eintrag["type"] == "dir":
            dateien += _dateien(repo, eintrag["path"])
        elif eintrag["name"].endswith((".ts", ".go", ".rs")) \
                and ".test." not in eintrag["name"]:
            dateien.append(eintrag["path"])
    return dateien


def _lesen(repo: str, pfade: Iterable[str]) -> str:
    standard = json.loads(_holen(f"{API}/repos/{repo}"))["default_branch"]
    return "\n".join(_holen(f"{RAW}/{repo}/{standard}/{p}").decode("utf-8")
                     for p in pfade)


def main() -> int:
    from satcortex import electrum
    dienst = electrum.Dienst(None, lambda: None)
    trezor = _lesen(TREZOR[0], _dateien(*TREZOR))
    bitbox = _lesen(BITBOX[0], [BITBOX[1]])
    electrs = _lesen(ELECTRS[0], [ELECTRS[1]])

    befunde: List[str] = []
    for name, text in (("Trezor Suite", trezor), ("BitBoxApp", bitbox)):
        befunde += vergleiche(name, befehle(text), versionen(text),
                              dienst.befehle, electrum.PROTOKOLL)
        print(f"{name}: Protokoll {', '.join(sorted(versionen(text)))}, "
              f"{len(befehle(text))} Befehle")
    print(f"electrs: Protokoll {', '.join(sorted(versionen(electrs))) or '?'}")
    for befund in befunde:
        print(f"::error::{befund}")
    return 1 if befunde else 0


if __name__ == "__main__":
    sys.exit(main())
