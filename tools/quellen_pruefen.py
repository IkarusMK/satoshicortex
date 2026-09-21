"""Die AUSGELIEFERTEN Nachrichtenquellen messen, statt sie zu glauben.

Feeds verrotten: Adressen ziehen um, Verlage stellen RSS ein, Sperren gegen
Nicht-Browser kommen dazu. Reuters ist das Lehrstueck -- fuenf dokumentierte
Adressen, keine antwortet noch. Cointelegraph hat alle zwoelf Sprachausgaben
abgeschaltet.

Geprueft wird die Liste aus satcortex/nachrichten.py SELBST. Der erste Entwurf
fuehrte eine eigene Kandidatenliste daneben -- und die lief binnen eines Tages
auseinander: das Werkzeug prueft dann etwas anderes, als ausgeliefert wird,
und das ist schlimmer als gar keine Pruefung.

    python3 tools/quellen_pruefen.py            # alles
    python3 tools/quellen_pruefen.py fr es      # nur diese Sprachen
    python3 tools/quellen_pruefen.py --cf       # nur die Cloudflare-Frage
"""
from __future__ import annotations

import concurrent.futures
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))
from satcortex import nachrichten as N                          # noqa: E402

# Derselbe Filter wie im Betrieb, plus die Schriftzeichen: Japanisch schreibt
# ビットコイン, nicht "Bitcoin". Ohne sie kam CoinPost auf 25 % und waere
# ausgeschieden -- der Fehler lag im Muster, nicht in der Quelle.
# Aus nachrichten.py, damit Werkzeug und Betrieb dasselbe messen.
NATIV = re.compile(N._SCHRIFTEN.pattern + "|" + N._SCHRIFTEN_WEIT.pattern)
LATEIN = re.compile(
    r"\b(bitcoin\w*|btc|satoshi\w*|halving|mempool|taproot|lightning"
    r"|krypto\w*|crypto\w*|cripto\w*|kripto\w*|blockchain)\b", re.I)

GEFAEHRLICH = re.compile(rb"<!DOCTYPE|<!ENTITY", re.I)
MINDESTQUOTE = 50.0


def _kopfzeilen(antwort) -> tuple:
    """Server-Kennung und ob Cloudflare davorsteht.

    Das ist keine Nebensache: Cloudflare weist Tor-Ausgangsknoten haeufig ab,
    und wir fragen ausschliesslich ueber Tor. Am 06.09.2026 kamen auf
    einem Testknoten von 26 eingeschalteten Fachquellen genau EINE an --
    eine der wenigen ohne Cloudflare.
    """
    h = antwort.headers
    server = h.get("Server", "?")
    cf = bool(h.get("CF-Ray") or h.get("cf-cache-status")
              or "cloudflare" in server.lower())
    return server, cf


def pruefe(quelle: "N.Quelle") -> dict:
    lage = {"quelle": quelle, "server": "-", "cf": False,
            "punkte": 0, "quote": 0.0, "fehler": ""}
    try:
        anfrage = urllib.request.Request(quelle.adresse, headers={
            "Accept": "application/rss+xml, application/atom+xml, */*",
            "User-Agent": "satcortex"})
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            roh = antwort.read(N.HOECHSTLAENGE)
            lage["server"], lage["cf"] = _kopfzeilen(antwort)
    except urllib.error.HTTPError as fehler:
        lage["server"], lage["cf"] = _kopfzeilen(fehler)
        lage["fehler"] = f"HTTP {fehler.code}"
        return lage
    except Exception as fehler:                                  # nosec B902
        lage["fehler"] = type(fehler).__name__
        return lage
    if GEFAEHRLICH.search(roh):
        lage["fehler"] = "kein Feed (HTML)"
        return lage
    try:
        wurzel = ET.fromstring(roh)                              # nosec B314
    except ET.ParseError as fehler:
        lage["fehler"] = f"XML: {fehler}"
        return lage
    stuecke = (wurzel.findall(".//item")
               or wurzel.findall(f".//{N.ATOM}entry"))
    treffer = sum(
        1 for s in stuecke
        if LATEIN.search(t := " ".join(e.text or "" for e in s.iter() if e.text))
        or NATIV.search(t))
    lage["punkte"] = len(stuecke)
    lage["quote"] = 100.0 * treffer / len(stuecke) if stuecke else 0.0
    return lage


def main() -> int:
    argumente = [a.lower() for a in sys.argv[1:]]
    nur_cf = "--cf" in argumente
    sprachen = [a for a in argumente if not a.startswith("-")]
    quellen = [q for q in N.QUELLEN if not sprachen or q.sprache in sprachen]
    if not quellen:
        print(f"Keine Quellen fuer {sprachen}.")
        return 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as p:
        lagen = list(p.map(pruefe, quellen))

    schlecht = []
    for lage in sorted(lagen, key=lambda l: (l["quelle"].sprache,
                                             l["quelle"].name)):
        q = lage["quelle"]
        if lage["fehler"]:
            zustand, ok = lage["fehler"], False
        else:
            zustand = f"{lage['punkte']:>3} Stk {lage['quote']:5.1f}%"
            # Leitmedien duerfen wenig liefern -- sie werden gefiltert und
            # sind ab Werk aus. Bei einer Fachquelle waere es ein Befund.
            ok = lage["punkte"] > 0 and (q.art == "leit"
                                         or lage["quote"] >= MINDESTQUOTE)
        if not ok:
            schlecht.append((q, zustand))
        tor = "CF!" if lage["cf"] else "   "
        print(f" {'OK ' if ok else '-- '}{tor} {q.sprache}  {q.name:22} "
              f"{str(lage['server'])[:14]:14} {zustand}")
        if lage["cf"] != q.hinter_cloudflare and not lage["fehler"]:
            print(f"      ^ hinter_cloudflare steht auf "
                  f"{q.hinter_cloudflare}, gemessen wurde {lage['cf']}")

    hinter = sum(1 for l in lagen if l["cf"])
    print(f"\n{len(lagen) - len(schlecht)} von {len(lagen)} in Ordnung. "
          f"{hinter} hinter Cloudflare -- die kommen ueber Tor haeufig NICHT "
          f"durch.")
    if nur_cf:
        return 0
    for q, zustand in schlecht:
        print(f"  PRUEFEN: {q.name} ({q.sprache}) -- {zustand}")
    return 1 if schlecht else 0


if __name__ == "__main__":
    raise SystemExit(main())
