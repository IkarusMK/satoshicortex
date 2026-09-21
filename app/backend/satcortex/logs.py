"""Was die Dienste gerade melden -- ohne Docker-Socket.

Der naheliegende Weg waere `docker logs`. Dafuer braeuchte die Anwendung den
Docker-Socket, und der ist auf einem Geraet mit einer Wallet gleichbedeutend
mit root -- deshalb hat sie ihn nicht und soll ihn nie bekommen.

Es geht auch ohne. Die Dienste schreiben ihre Protokolle in dasselbe
Datenverzeichnis, das die Anwendung ohnehin eingehaengt hat:

    satcortex   Ringspeicher im Arbeitsspeicher (siehe unten)
    bitcoind    <fast>/bitcoind/debug.log
    lnd         <fast>/lnd/logs/bitcoin/mainnet/lnd.log
    tor         <fast>/tor/notice.log

Zu bitcoind, weil es verwirrt: in der bitcoin.conf steht `printtoconsole=1`,
und die Hilfe klingt, als ginge die Ausgabe dann NUR auf die Konsole. Tut sie
nicht. In Cores init/common.cpp haengt die Datei an einer anderen Bedingung:

    m_print_to_file    = !args.IsArgNegated("-debuglogfile");
    m_print_to_console = args.GetBoolArg("-printtoconsole", ...);

Zwei unabhaengige Schalter. Die Hilfe zu -printtoconsole sagt es selbst:
"To disable logging to file, set -nodebuglogfile". Wir setzen das nicht, also
gibt es die debug.log.

Tor schrieb bis zum 01.09.2026 nur nach stdout und war damit als einziger
Dienst nicht einsehbar -- ausgerechnet der, bei dem am haeufigsten unklar ist,
was los ist. Die Vorlage hat jetzt eine zweite Log-Zeile in eine Datei.

Zwei Dinge sind hier Absicht und keine Kuer:

* Der Name der Quelle ist das EINZIGE, was von aussen kommt, und er wird
  gegen einen festen Satz geprueft. Waere er ein Pfad, waere diese Anwendung
  ein Dateibetrachter fuer alles, was der Container sieht.
* Gelesen wird vom ENDE her und hoechstens HOECHSTENS_BYTES. Eine debug.log
  waechst ueber Monate; sie ganz einzulesen waere ein sicherer Weg, dem
  Container den Speicher wegzunehmen.
"""
from __future__ import annotations

import logging
import os
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Wieviel vom Ende einer Datei hoechstens gelesen wird. 256 KB sind ein paar
# tausend Zeilen -- mehr, als ein Mensch durchsieht, und wenig genug, dass es
# nicht auffaellt.
HOECHSTENS_BYTES = 256 * 1024

ZEILEN_STANDARD = 200
ZEILEN_HOECHSTENS = 2000

# Wieviele eigene Meldungen aufgehoben werden. Ein Ringspeicher ist eine
# Anzeige, kein Archiv: unbegrenzt waere er ein Leck, das genau so lange
# waechst wie die Anwendung laeuft.
#
# Von 500 auf 2000 erhoeht, als das Betriebsprotokoll dazukam: mit rund 150
# Zeilen am Tag trugen 500 keine vier Tage. Wer am Montag nachsieht, was ueber
# das Wochenende war, soll es noch finden. 2000 Zeilen sind etwa 300 kB im
# Arbeitsspeicher -- bei 400 MB Grenze nicht der Rede wert.
EIGENE_ZEILEN = 2000

EIGENE = "satcortex"

# Die Reihenfolge ist die der Oberflaeche: erst der Ueberblick, den nur diese
# Anwendung hat, dann die Dienste in der Reihenfolge, in der sie starten.
_DATEIEN = {
    "bitcoind": ("bitcoind", "debug.log"),
    "lnd": ("lnd", "logs", "bitcoin", "mainnet", "lnd.log"),
    "tor": ("tor", "notice.log"),
}
NAMEN = [EIGENE, *_DATEIEN]


class Ringspeicher(logging.Handler):
    """Die letzten Meldungen der Anwendung selbst, im Arbeitsspeicher."""

    def __init__(self, plaetze: int = EIGENE_ZEILEN) -> None:
        super().__init__()
        self.zeilen: deque = deque(maxlen=plaetze)

    def emit(self, satz: logging.LogRecord) -> None:
        # Ein Fehler beim Protokollieren darf nie den Aufrufer treffen --
        # sonst stuerzt eine Anwendung daran ab, dass sie etwas melden wollte.
        try:
            self.zeilen.append(self.format(satz))
        except Exception:                                    # noqa: BLE001
            self.handleError(satz)


_ring: Optional[Ringspeicher] = None


def mitschreiben() -> Ringspeicher:
    """Den Ringspeicher an den Wurzel-Logger haengen -- genau einmal.

    baue_app() laeuft in den Tests dutzendfach. Ohne diese Schranke haette der
    Wurzel-Logger am Ende dutzende Handler, und jede Meldung stuende
    entsprechend oft da.
    """
    global _ring
    wurzel = logging.getLogger()
    # Der Ringspeicher haengt am Wurzel-Logger, und DESSEN Stufe entscheidet,
    # was ueberhaupt bei ihm ankommt. Pythons Vorgabe ist WARNING -- damit
    # faellt jede INFO-Meldung weg, bevor ein Handler sie sieht, und die
    # Protokollansicht ist leer, ohne dass irgendwo ein Fehler stuende.
    #
    # Bis zum 05.09.2026 verliess sich das darauf, dass __main__ vorher
    # basicConfig(level=INFO) aufruft. Im Container stimmt das; im Pruefstand
    # stimmte es nicht, und die Ansicht war prompt leer. Eine Anzeige, die
    # von der Startart des Prozesses abhaengt, ist keine -- also stellt sie
    # ihre eigene Voraussetzung her. Ein absichtliches DEBUG wird dabei nicht
    # angehoben, nur ein zu grobes zurechtgerueckt.
    if not wurzel.isEnabledFor(logging.INFO):
        wurzel.setLevel(logging.INFO)
    if _ring is None:
        _ring = Ringspeicher()
        _ring.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s  %(message)s",
            datefmt="%d.%m. %H:%M:%S"))
        wurzel.addHandler(_ring)
    return _ring


def _pfad(name: str, fast: str) -> Path:
    return Path(fast).joinpath(*_DATEIEN[name])


def _zeilenzahl(gewuenscht: Optional[int]) -> int:
    if not gewuenscht:
        return ZEILEN_STANDARD if gewuenscht is None else 1
    return max(1, min(int(gewuenscht), ZEILEN_HOECHSTENS))


def quellen(fast: str) -> List[Dict]:
    """Was es zu lesen gibt, und ob schon etwas darin steht."""
    raus: List[Dict] = [{
        "name": EIGENE,
        "da": True,
        "groesse_bytes": None,
        "geaendert": None,
    }]
    for name in _DATEIEN:
        pfad = _pfad(name, fast)
        try:
            stand = pfad.stat()
        except OSError:
            raus.append({"name": name, "da": False,
                         "groesse_bytes": None, "geaendert": None})
            continue
        raus.append({"name": name, "da": True,
                     "groesse_bytes": stand.st_size,
                     "geaendert": int(stand.st_mtime)})
    return raus


def _vom_ende(pfad: Path, zeilen: int) -> Dict:
    with pfad.open("rb") as datei:
        groesse = datei.seek(0, os.SEEK_END)
        anfang = max(0, groesse - HOECHSTENS_BYTES)
        datei.seek(anfang)
        roh = datei.read()

    # Kaputte Zeichen ersetzen statt daran zu scheitern: ein Protokoll ist
    # kein sauber kodierter Datensatz, und eine unlesbare Stelle darf nicht
    # die lesbaren mitnehmen.
    text = roh.decode("utf-8", errors="replace")
    gefunden = text.splitlines()

    # Wer mitten in einer Zeile zu lesen anfaengt, bekommt ihren Rest. Ein
    # halber Zeitstempel sieht aus wie eine Meldung und ist keine.
    beschnitten = anfang > 0
    if beschnitten and gefunden:
        gefunden = gefunden[1:]

    return {
        "zeilen": gefunden[-zeilen:],
        "groesse_bytes": groesse,
        "abgeschnitten": beschnitten or len(gefunden) > zeilen,
    }


def lies(name: str, fast: str, zeilen: Optional[int] = None) -> Dict:
    """Das Ende eines Protokolls.

    `name` muss einer der festen Namen sein -- alles andere fliegt raus,
    bevor daraus ein Pfad wird.
    """
    if name not in NAMEN:
        raise ValueError(f"unbekannte Protokollquelle: {name!r}")
    anzahl = _zeilenzahl(zeilen)

    if name == EIGENE:
        vorhanden = list(_ring.zeilen) if _ring else []
        return {"name": name, "da": True, "zeilen": vorhanden[-anzahl:],
                "groesse_bytes": None,
                "abgeschnitten": len(vorhanden) > anzahl}

    pfad = _pfad(name, fast)
    try:
        d = _vom_ende(pfad, anzahl)
    except OSError as fehler:
        # Kein Fehler nach aussen: vor der Einrichtung gibt es die Datei
        # schlicht noch nicht. Das ist ein Zustand, den die Oberflaeche
        # anzeigen soll, keine Stoerung.
        log.debug("Protokoll %s nicht lesbar: %s", pfad, fehler)
        return {"name": name, "da": False, "zeilen": [],
                "groesse_bytes": None, "abgeschnitten": False}
    d.update(name=name, da=True)
    return d
