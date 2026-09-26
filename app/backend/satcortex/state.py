"""Zustand der Ersteinrichtung.

Der Assistent darf jederzeit unterbrochen werden -- Browser zu, Geraet neu
gestartet, egal. Deshalb liegt der Fortschritt auf der Platte und nicht im
Speicher.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from . import storage
from typing import Dict, List, Optional


class Schritt(str, Enum):
    WILLKOMMEN = "willkommen"
    SPEICHER = "speicher"
    LEISTUNG = "leistung"
    NETZ = "netz"
    KONTO = "konto"
    FERTIG = "fertig"


REIHENFOLGE: List[Schritt] = [
    Schritt.WILLKOMMEN,
    Schritt.SPEICHER,
    Schritt.LEISTUNG,
    Schritt.NETZ,
    Schritt.KONTO,
    Schritt.FERTIG,
]

TITEL: Dict[Schritt, str] = {
    Schritt.WILLKOMMEN: "Willkommen",
    Schritt.SPEICHER: "Speicherplatz",
    Schritt.LEISTUNG: "Leistung",
    Schritt.NETZ: "Netz und Teilnahme",
    Schritt.KONTO: "Dein Konto",
    Schritt.FERTIG: "Fertig",
}


@dataclass
class Einrichtung:
    schritt: Schritt = Schritt.WILLKOMMEN
    antworten: Dict = field(default_factory=dict)
    abgeschlossen_am: Optional[str] = None
    # Was beim Abschliessen gewaehlt wurde. Vorher ging das nur in die
    # Konfigurationsdatei -- wer die spaeter erneuern wollte, hatte die Werte
    # nicht mehr und musste die ganze Einrichtung wiederholen.
    knotenwahl: Dict = field(default_factory=dict)
    # Wohin die Kanalsicherung geht -- URL und Benutzer. Das Passwort steht
    # NICHT hier: diese Datei ist fuer die Gruppe lesbar, weil die Dienste
    # sie brauchen. Es liegt in sicherung.pass mit 0600.
    sicherungsziel: Dict = field(default_factory=dict)
    # Ob der Nachrichten-Feed laeuft, welche Quellen und wie eng gefiltert
    # wird. AUS, solange hier nichts steht: eine frische Installation, die
    # von sich aus dreissig Verlage anruft, ist ein Uebergriff -- auch ueber
    # Tor. Der Nutzer schaltet ihn ein, nicht wir.
    nachrichtenwahl: Dict = field(default_factory=dict)
    # Wie die Wallet nach einem Neustart wieder aufgeht -- "aus", "merken"
    # oder "datei". Hier steht die WAHL, nie ein Geheimnis: bei "datei" liegt
    # das Passwort in LNDs eigener Entsperrdatei, bei "merken" nur im
    # Arbeitsspeicher dieser Anwendung, bei "aus" nirgends. Dass jemand die
    # Bequemlichkeit gewaehlt hat, ist selbst kein Geheimnis.
    walletwahl: Dict = field(default_factory=dict)
    # Die Kennung dieses Knotens -- sein oeffentlicher Schluessel, 66
    # Zeichen. KEIN Geheimnis: er steht im Lightning-Netz, jeder Knoten
    # kennt ihn. Er steht hier, damit die Anwendung nach einer
    # Wiederherstellung selbst sagen kann, ob es derselbe Knoten ist.
    #
    # Aus dem Betrieb, 11.09.2026, nach der Probe: "keine ahnung habe mir die
    # kennung nicht vorher angesehen". Dass er sie sich von Hand notieren
    # sollte, war unser Versaeumnis -- die Anwendung kennt sie ohnehin.
    knotenausweis: Dict = field(default_factory=dict)
    # Ob die Gebuehren dem Netz folgen sollen, und was dabei zuletzt gesetzt
    # wurde. AUS, solange hier nichts steht -- eine Automatik, die ungefragt
    # an den Gebuehren eines Knotens dreht, auf dem fremdes Geld unterwegs
    # ist, waere genau die Art Ueberraschung, die hier nichts zu suchen hat.
    # Der Nutzer schaltet sie ein, nicht wir.
    gebuehrenwahl: Dict = field(default_factory=dict)
    # Externe Wallets (Zeus): welche Geraete verbunden sind, mit Name, Stufe,
    # Weg und Wurzelkennung -- und ob der Onion-Dienst dafuer stehen soll.
    # NIE der Schluessel selbst: der wird einmal angezeigt und dann
    # vergessen. Diese Datei ist fuer die Gruppe lesbar.
    fernzugang: Dict = field(default_factory=dict)

    # ------------------------------------------------------------ Ablauf
    @property
    def index(self) -> int:
        return REIHENFOLGE.index(self.schritt)

    @property
    def fertig(self) -> bool:
        """Steht der Nutzer auf dem letzten Schritt?

        NICHT zu verwechseln mit "eingerichtet". Der letzte Schritt ist die
        Zusammenfassung MIT dem Knopf, der die Einrichtung ausloest -- man ist
        also zwangslaeufig hier, BEVOR etwas passiert ist. Genau diese
        Verwechslung hat den Assistenten unbenutzbar gemacht: die Sperre gegen
        doppelte Einrichtung prueft auf "fertig" und griff damit, sobald man
        die Seite mit dem Knopf ueberhaupt erreichte.
        """
        return self.schritt is Schritt.FERTIG

    @property
    def eingerichtet(self) -> bool:
        """Wurde die Einrichtung tatsaechlich durchgefuehrt?"""
        return self.abgeschlossen_am is not None

    def naechster(self) -> Schritt:
        if self.fertig:
            return Schritt.FERTIG
        return REIHENFOLGE[self.index + 1]

    def weiter(self, antworten: Optional[Dict] = None) -> Schritt:
        if antworten:
            self.antworten[self.schritt.value] = antworten
        self.schritt = self.naechster()
        return self.schritt

    def als_eingerichtet_markieren(self) -> None:
        """Setzt den Zeitstempel -- ausschliesslich, wenn wirklich
        eingerichtet wurde. Blaettern allein reicht dafuer nicht."""
        if not self.abgeschlossen_am:
            self.abgeschlossen_am = datetime.now(timezone.utc).isoformat()

    def zurueck(self) -> Schritt:
        """Zurueckblaettern -- solange nicht eingerichtet wurde.

        Auf der Zusammenfassung muss Zurueckblaettern moeglich bleiben: dort
        korrigiert man seine Wahl, bevor man ausloest.
        """
        if self.index > 0 and not self.eingerichtet:
            self.schritt = REIHENFOLGE[self.index - 1]
        return self.schritt

    def to_dict(self) -> Dict:
        return {
            "schritt": self.schritt.value,
            "titel": TITEL[self.schritt],
            "nummer": self.index + 1,
            "von": len(REIHENFOLGE),
            "fertig": self.fertig,
            "antworten": self.antworten,
            "abgeschlossen_am": self.abgeschlossen_am,
            "knotenwahl": self.knotenwahl,
            "sicherungsziel": self.sicherungsziel,
            "schritte": [
                {"name": s.value, "titel": TITEL[s], "erledigt": i < self.index}
                for i, s in enumerate(REIHENFOLGE)
            ],
        }


class Ablage:
    """Liest und schreibt den Fortschritt -- atomar, damit ein Absturz
    mitten im Schreiben keinen halben Zustand hinterlaesst."""

    def __init__(self, verzeichnis: str) -> None:
        self.pfad = Path(verzeichnis)
        storage.lege_ablage_an(str(self.pfad))
        self.datei = self.pfad / "einrichtung.json"

    def laden(self) -> Einrichtung:
        if not self.datei.exists():
            return Einrichtung()
        try:
            roh = json.loads(self.datei.read_text(encoding="utf-8"))
            # Gueltiges JSON ist noch kein Objekt: "null", "42" und "[]"
            # kommen hier unbeschadet durch und lassen dann roh.get() mit
            # einem AttributeError durchschlagen -- der unten NICHT gefangen
            # wird. Befund vom 22.09.2026. Eine kaputte Zustandsdatei soll
            # zum Neuanfang fuehren, nicht zum Absturz beim Start.
            if not isinstance(roh, dict):
                raise ValueError("Zustandsdatei ist kein Objekt")
            return Einrichtung(
                schritt=Schritt(roh.get("schritt", Schritt.WILLKOMMEN.value)),
                antworten=roh.get("antworten", {}),
                abgeschlossen_am=roh.get("abgeschlossen_am"),
                knotenwahl=roh.get("knotenwahl", {}),
                sicherungsziel=roh.get("sicherungsziel", {}),
                nachrichtenwahl=roh.get("nachrichtenwahl", {}),
                walletwahl=roh.get("walletwahl", {}),
                knotenausweis=roh.get("knotenausweis", {}),
                gebuehrenwahl=roh.get("gebuehrenwahl", {}),
                fernzugang=roh.get("fernzugang", {}),
            )
        except (json.JSONDecodeError, ValueError):
            # Lieber von vorn anfangen als mit kaputtem Zustand weitermachen.
            return Einrichtung()

    def merke_knotenwahl(self, wahl: Dict) -> None:
        """Haelt fest, was der Nutzer gewaehlt hat.

        Ohne das liesse sich die Konfiguration spaeter nicht erneuern: die
        Werte standen nur in der geschriebenen conf, und die wieder
        einzulesen waere Raterei.
        """
        e = self.laden()
        e.knotenwahl = dict(wahl)
        self.speichern(e)

    def merke_knotenausweis(self, kennung: str) -> None:
        """Die Kennung festhalten -- einmal, und dann nur auf Ansage.

        Sie darf sich NICHT still aendern: genau der Wechsel ist die
        Auskunft, um die es geht. Wer eine neue Wallet anlegt, bekommt zu
        Recht eine andere -- und soll das sehen, nicht ueberschrieben
        bekommen.
        """
        e = self.laden()
        e.knotenausweis = {
            "kennung": kennung,
            "seit": datetime.now(timezone.utc).isoformat(),
        }
        self.speichern(e)

    def merke_walletwahl(self, wahl: Dict) -> None:
        """Den Entsperrweg festhalten.

        Ohne das waere "merken" von "aus" nicht zu unterscheiden: beide
        hinterlassen nichts auf der Platte, und die Oberflaeche wuesste nach
        einem Neustart nicht mehr, was der Nutzer gewaehlt hat.
        """
        e = self.laden()
        e.walletwahl = dict(wahl)
        self.speichern(e)

    def merke_gebuehrenwahl(self, wahl: Dict) -> None:
        """Die Wahl zur Gebuehrenautomatik festhalten.

        Hier steht nur, WAS gewollt ist -- ob die Automatik laeuft, und was
        sie zuletzt gesetzt hat. Die Messreihe selbst gehoert nicht hierher,
        sondern in die Auswertungsdatenbank: das sind Zeitreihen, und die
        haben in einer Einstellungsdatei nichts verloren.
        """
        e = self.laden()
        e.gebuehrenwahl = dict(wahl)
        self.speichern(e)

    # Was von einem Geraet festgehalten wird -- und nichts sonst. Eine
    # Liste statt "alles ausser dem Macaroon": kommt spaeter ein Feld dazu,
    # das nicht hierher gehoert, faellt es heraus, statt still mitzureisen.
    GERAETEFELDER = ("kennung", "name", "stufe", "weg", "angelegt")

    def merke_fernzugang(self, wahl: Dict) -> None:
        """Die verbundenen Geraete festhalten -- ohne ihre Schluessel."""
        e = self.laden()
        e.fernzugang = {
            "tor": bool(wahl.get("tor")),
            "geraete": [{k: g[k] for k in self.GERAETEFELDER if k in g}
                        for g in wahl.get("geraete") or []],
        }
        self.speichern(e)

    def merke_nachrichtenwahl(self, wahl: Dict) -> None:
        e = self.laden()
        e.nachrichtenwahl = dict(wahl)
        self.speichern(e)

    def merke_sicherungsziel(self, ziel: Dict) -> None:
        e = self.laden()
        e.sicherungsziel = dict(ziel)
        self.speichern(e)

    def speichern(self, e: Einrichtung) -> None:
        temp = self.datei.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(
                {
                    "schritt": e.schritt.value,
                    "antworten": e.antworten,
                    "abgeschlossen_am": e.abgeschlossen_am,
                    "knotenwahl": e.knotenwahl,
                    "sicherungsziel": e.sicherungsziel,
                    "nachrichtenwahl": e.nachrichtenwahl,
                    "walletwahl": e.walletwahl,
                    "knotenausweis": e.knotenausweis,
                    "gebuehrenwahl": e.gebuehrenwahl,
                    "fernzugang": e.fernzugang,
                },
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temp, self.datei)
