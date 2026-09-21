"""Die Kanalsicherung aktuell halten -- und ausser Haus bringen.

WARUM DAS EIGENSTAENDIG ZAEHLT: Die vierundzwanzig Woerter auf Papier stellen
die On-Chain-Wallet wieder her. Die Guthaben IN den Kanaelen stellen sie NICHT
wieder her. Ein Kanal ist eine gemeinsame Ausgabe mit einer Gegenstelle; um
ihn ohne deren Mithilfe aufzuloesen, braucht es seinen Zustand -- und der
steht in dieser Datei. Platte kaputt, Sicherung weg, Kanalguthaben weg. Mit
Seed.

WOHIN: ausser Haus, und das ist die ganze Anforderung. Eine Sicherung auf
derselben Platte wie die Wallet sichert gegen die Sache, gegen die man sich
sichert, gerade nicht. Zwei Wege stehen zur Wahl:

* Herunterladen. Braucht nichts, geht immer, und der Nutzer entscheidet, wo
  sie landet.
* WebDAV. Nextcloud, ein Hoster, was auch immer -- einmal einrichten, danach
  laeuft es mit.

Beides ist unbedenklich, weil die Datei verschluesselt ist: der Schluessel
steckt im Seed. Ohne die Woerter ist sie niemandem etwas wert. Muesste man sie
wie den Seed behandeln, gaebe es sie in der Praxis nicht.

WANN: bei jeder Aenderung. Ein Kanal, der seit der letzten Sicherung
dazugekommen ist, ist ein Kanal ohne Sicherung.

UND ZURUECK: `hole_ab` ist das Gegenstueck zu `lade_hoch`, und es hat lange
gefehlt. Eine Sicherung, die man nur hinschieben, aber nicht zurueckholen
kann, ist keine -- wer sie braucht, hat gerade kein NAS mehr, auf dem er
nachsehen koennte, wohin sie ging.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

DATEINAME = "channel.backup"

# Wie lange auf den fremden Server gewartet wird. Er steht womoeglich im
# selben Haus, womoeglich hinter einer langsamen Leitung -- aber ein
# Sicherungslauf, der Minuten haengt, blockiert den Waechter.
ZEITLIMIT_SEKUNDEN = 30.0

# Wieviel beim Zurueckholen hoechstens gelesen wird. Eine Kanalsicherung
# umfasst ein paar hundert Byte je Kanal; wer hier ein Megabyte bekommt, hat
# nicht seine Sicherung erwischt, sondern irgendetwas anderes.
HOECHSTGROESSE = 1024 * 1024


class ZielFehler(Exception):
    """Das Ziel hat die Sicherung nicht angenommen.

    `grund` ist ein Schluessel fuer die Oberflaeche, wenn der Fall bekannt ist
    -- dann steht dort ein Satz, der sagt, was zu tun ist. Sonst leer, und es
    bleibt beim Wortlaut des Servers.
    """

    def __init__(self, text: str, grund: str = "") -> None:
        super().__init__(text)
        self.grund = grund


# Was die Antwortcodes eines WebDAV-Ziels bedeuten. Bis zum 14.09.2026 kam
# jeder davon als nackte Zahl in der Oberflaeche an ("404: Not Found") -- und
# ausgerechnet 404, der Fall mit der eindeutigsten Ursache, sagte am wenigsten.
#
# 401 und 403 bedeuten Verschiedenes: wer sie zusammenwirft, schickt jemanden
# sein Passwort suchen, obwohl es an den Rechten liegt. 404 und 409 ebenso --
# nachgesehen in sabre/dav, auf dem Nextclouds WebDAV laeuft (Server.php,
# createFile): ein PUT in einen Ordner, den es nicht gibt, beantwortet der
# Server mit 409 ("Files cannot be created in non-existent collections"). Ein
# 404 beim Ablegen heisst deshalb: nicht der Ordner fehlt, die Adresse stimmt
# nicht.
DEUTUNG_BEIM_ABLEGEN = {
    401: "ziel_anmeldung_abgelehnt",
    403: "ziel_verweigert",
    404: "ziel_adresse_unbekannt",
    409: "ziel_ordner_fehlt",
}
# Beim Zurueckholen heisst 404 etwas anderes: dort liegt keine Datei. Ob nie
# eine abgelegt wurde oder die Adresse auf einen anderen Ordner zeigt, kann
# der Server nicht unterscheiden -- der Satz dazu nennt beides.
DEUTUNG_BEIM_HOLEN = {
    401: "ziel_anmeldung_abgelehnt",
    403: "ziel_verweigert",
    404: "ziel_keine_sicherung_dort",
}


def pruefsumme(blob: str) -> str:
    """Woran erkannt wird, dass sich etwas geaendert hat.

    Ueber den entschluesselten Inhalt laesst sich das nicht sagen -- wir sehen
    nur den verschluesselten Klumpen. Der aendert sich aber bei jeder
    Kanalaenderung, und mehr braucht es nicht.
    """
    return hashlib.sha256((blob or "").encode("utf-8")).hexdigest()


class Stand:
    """Was zuletzt gesichert wurde, wohin und wann.

    Im Konfigurationsverzeichnis, neben allem anderen. Enthaelt ausdruecklich
    KEINE Zugangsdaten -- die liegen in einer eigenen Datei mit engen Rechten.
    """

    def __init__(self, verzeichnis: str) -> None:
        self.datei = Path(verzeichnis) / "sicherung.json"

    def laden(self) -> Dict:
        try:
            return json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def speichern(self, wert: Dict) -> None:
        temp = self.datei.with_suffix(".json.neu")
        temp.write_text(json.dumps(wert, indent=2), encoding="utf-8")
        os.chmod(temp, 0o640)
        os.replace(temp, self.datei)


def _webdav_url(basis: str) -> str:
    return basis.rstrip("/") + "/" + DATEINAME


def lade_hoch(blob: str, url: str, benutzer: str, passwort: str,
              zeitlimit: float = ZEITLIMIT_SEKUNDEN) -> None:
    """Die Sicherung per WebDAV ablegen. PUT, mehr ist es nicht.

    Bewusst ohne fremde Bibliothek: ein PUT mit Basic-Auth ist genau das, was
    die Standardbibliothek kann. Und bewusst OHNE einen Handler, der
    Anmeldedaten erst nach einer 401 nachreicht -- der schickte die Datei sonst
    einmal unangemeldet los.
    """
    daten = base64.b64decode(blob) if blob else b""
    anfrage = urllib.request.Request(_webdav_url(url), data=daten, method="PUT")
    anfrage.add_header("Content-Type", "application/octet-stream")
    marke = base64.b64encode(f"{benutzer}:{passwort}".encode()).decode()
    anfrage.add_header("Authorization", "Basic " + marke)
    try:
        with urllib.request.urlopen(anfrage, timeout=zeitlimit) as antwort:  # nosec B310
            if antwort.status not in (200, 201, 204):
                raise ZielFehler(f"unerwartete Antwort {antwort.status}")
    except urllib.error.HTTPError as fehler:
        # Die Zahl allein hilft niemandem -- was sie bedeutet, steht in
        # DEUTUNG_BEIM_ABLEGEN.
        raise ZielFehler(f"{fehler.code}: {fehler.reason}",
                         DEUTUNG_BEIM_ABLEGEN.get(fehler.code, "")) from fehler
    except (urllib.error.URLError, OSError) as fehler:
        raise ZielFehler(str(fehler)) from fehler


def hole_ab(url: str, benutzer: str, passwort: str,
            zeitlimit: float = ZEITLIMIT_SEKUNDEN) -> str:
    """Die abgelegte Sicherung zurueckholen. GET, das Gegenstueck zu lade_hoch.

    ES GAB DIESEN WEG LANGE NICHT, und das war der Fehler: eine Sicherung, die
    man nur hinschieben, aber nicht zurueckholen kann, ist keine. Wer sie
    braucht, hat gerade kein NAS mehr, auf dem er nachsehen koennte, wohin sie
    ging.

    Zurueck kommt sie base64-kodiert -- so, wie LND sie erwartet, und so, wie
    sie durch die Schnittstelle geht.
    """
    anfrage = urllib.request.Request(_webdav_url(url), method="GET")
    marke = base64.b64encode(f"{benutzer}:{passwort}".encode()).decode()
    anfrage.add_header("Authorization", "Basic " + marke)
    try:
        with urllib.request.urlopen(anfrage, timeout=zeitlimit) as antwort:  # nosec B310
            if antwort.status != 200:
                raise ZielFehler(f"unerwartete Antwort {antwort.status}")
            # Begrenzt gelesen: was hier zurueckkommt, bestimmt ein fremder
            # Server. Eine echte Kanalsicherung liegt bei ein paar hundert
            # Byte je Kanal -- ein Megabyte ist grosszuegig und deckelt
            # trotzdem, was ein falsch geratener Pfad hereinreichen kann.
            roh = antwort.read(HOECHSTGROESSE + 1)
    except urllib.error.HTTPError as fehler:
        raise ZielFehler(f"{fehler.code}: {fehler.reason}",
                         DEUTUNG_BEIM_HOLEN.get(fehler.code, "")) from fehler
    except (urllib.error.URLError, OSError) as fehler:
        raise ZielFehler(str(fehler)) from fehler
    if len(roh) > HOECHSTGROESSE:
        raise ZielFehler("die Datei dort ist zu gross fuer eine Kanalsicherung")
    return base64.b64encode(roh).decode()


def faellig(stand: Dict, blob: str) -> bool:
    """Hat sich seit der letzten Sicherung etwas geaendert?"""
    return bool(blob) and stand.get("pruefsumme") != pruefsumme(blob)


def vermerke(stand_ablage: Stand, blob: str, kanaele: int,
             ziel: str, fehler: str = "") -> Dict:
    wert = {
        "pruefsumme": pruefsumme(blob) if not fehler else
                      (stand_ablage.laden().get("pruefsumme") or ""),
        "kanaele": kanaele,
        "zeitpunkt": time.time(),
        "ziel": ziel,
        "fehler": fehler,
    }
    stand_ablage.speichern(wert)
    return wert
