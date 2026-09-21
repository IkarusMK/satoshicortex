"""HTTP-Schnittstelle: Einrichtungsassistent und Uebersicht."""
from __future__ import annotations

import base64
import ipaddress
import logging
import math
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import (APIRouter, Cookie, Depends, FastAPI, HTTPException,
                     Request, Response)
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, field_validator

import asyncio
import contextlib

from . import (auth, beitrag, betriebslog, coinbase, dyndns, erreichbar,
               gebiete, gebuehren as netzgebuehren, geo, karte,
               kennzahlen, kurs, lnd, logs, mempoolstrom, merker,
               nachrichten, nodeconfig,
               oidc, onion, pools, profiles, rpc, services, settings,
               sicherung, state, storage, store, tempo, updates, zulauf)
from . import adresse as adressabfrage, cluster as mempoolcluster

# lnd steht mit in der Liste, obwohl es zu Anfang nur wartet. Es zu
# verschweigen, weil es noch nichts tut, waere die falsche Freundlichkeit:
# der Container LAEUFT, und wer in der Uebersicht nachsieht, soll ihn finden.
DIENSTE: List[str] = ["bitcoind", "lnd", "tor"]

# Wieviele Transaktionen eines Blocks hoechstens ausgeliefert werden. Ein
# voller Block hat bis zu ein paar tausend; die laengsten Wartezeiten stehen
# oben, und wer die ersten fuenfhundert gesehen hat, hat die Aussage.
BLOCK_TX_GRENZE = 500
# Wie lange ein Adress-Scan hoechstens dauern darf. Core durchsucht dafuer den
# ganzen UTXO-Satz; auf einem NAS sind das Minuten, nicht Sekunden.
ADRESS_FRIST_S = 900.0
# Die Fenster fuer die Pool-Anteile: ein Tag, eine Woche, alles Aufgezeichnete.
POOL_FENSTER = (144, 1008, 0)

# Ein Block fasst rund eine Million vByte.
BLOCK_VBYTE = 1_000_000

# Wieviele Kacheln hoechstens gezeichnet werden. Darunter wird jede Flaeche
# kleiner als ein Pixel -- mehr zu schicken kostet Bandbreite und zeigt
# nichts. Und wieviele Bloecke tief: was in zehn Bloecken nicht drin ist,
# wartet ohnehin Stunden.
# JE BLOCK, nicht insgesamt. Eine gemeinsame Obergrenze war der Fehler: bei
# Des Betreibers 31.716 wartenden Transaktionen war sie nach sechs Spalten
# aufgebraucht, und die letzten Bloecke standen als leere Rahmen da. Was
# darueber liegt, wird je Block zu EINER Restkachel zusammengefasst -- dann
# stimmt die Flaeche weiter.
KACHEL_JE_BLOCK = 1200
KACHEL_BLOECKE = 8

# Wie lange eine Kachelantwort gilt. getrawmempool ist der groesste Aufruf,
# den diese Anwendung kennt; ihn bei jedem Blick neu zu stellen waere Last
# ohne Gegenwert -- der Mempool aendert sich in Sekunden kaum sichtbar.
KACHEL_FRIST_S = 20.0

# Wie lange eine geholte Kettenlage weiterverwendet werden darf.
#
# Die Oberflaeche fragt im Zehn-Sekunden-Takt und ruft dabei mehrere
# Endpunkte an. Drei Sekunden genuegen, damit sich die Abrufe EINES Taktes
# eine Antwort teilen -- und sind kurz genug, dass niemand veraltete Zahlen
# sieht.
LAGE_FRISCHE_SEKUNDEN = 3.0
# Wie oft der Sammler die Lage neu misst. Waehrend des Erstabgleichs braucht
# eine Runde bis zu fuenfzehn Sekunden -- der Takt begrenzt sich damit selbst
# und wird nicht enger als "eine Runde plus Pause". Wichtiger als die Zahl:
# die Last haengt jetzt am Sammler, nicht mehr an der Zahl offener Browser.
SAMMLER_TAKT_SEKUNDEN = 5.0

# Wie oft hoechstens nachgesehen wird, ob eine gemerkte Wallet wieder
# zugefallen ist. Der Sammler kaeme alle fuenf Sekunden vorbei; ein Neustart
# von LND dauert laenger als das, und jede Abfrage an einen hochfahrenden
# Dienst kostet eine Wartezeit.
OFFENHALTEN_TAKT_SEKUNDEN = 20.0

# Wie lange der Waechter nach dem Start wartet, bevor er das erste Mal
# nachsieht. Bewusst kurz, aber nicht null: bitcoind laedt beim Start den
# chainstate und antwortet vorher nicht.
ERSTER_WAECHTERLAUF_SEKUNDEN = 30.0

# Wie lange auf Tors "hostname"-Dateien gewartet wird, nachdem die torrc neu
# geschrieben wurde. Tor legt sie beim Laden der Dienste an, lange bevor es
# mit dem Netz verbunden ist -- nach einem Neustart meist binnen Sekunden.
#
# Gewartet wird, damit bitcoind und LND ihre .onion im SELBEN Schreibvorgang
# bekommen wie den Rest. Ohne das startete jeder zweimal neu, und bei LND
# heisst ein Neustart ohne Auto-Entsperren: Wallet zu. Im Waechter darf es
# laenger dauern, in einer Anfrage nicht -- die Oberflaeche gibt nach 25 s auf.
# Wie viele Adressen eines Wachturms hoechstens gemessen werden.
#
# Jede Messung laeuft ueber Tor und dauert bis zu erreichbar.ZEITLIMIT_SEKUNDEN.
# Drei mal dreissig Sekunden sind die Obergrenze, die ein Browser und ein
# Reverse Proxy davor noch aushalten; mehr Adressen traegt in der Praxis kein
# Turm, und beim ersten Erfolg wird ohnehin abgebrochen.
WACHTURM_PRUEF_HOECHSTENS = 3

ONION_FRIST_WAECHTER_SEKUNDEN = 45.0
ONION_FRIST_ANFRAGE_SEKUNDEN = 12.0

# Wie lange Tors Freigabe fehlen muss, damit der Waechter im Container es
# bemerkt. Er sieht alle zwei Sekunden nach (entrypoint.sh, INTERVAL); drei
# Durchgaenge sind sicher.
TOR_NEUSTART_PAUSE_SEKUNDEN = 6.0

SITZUNGS_KEKS = "satcortex_sitzung"
# Groesse der frei belegbaren Antworten je Schritt. Ohne Deckel kann jeder ohne
# Anmeldung die Platte volllaufen lassen -- gemessen: 195 kB aus einem Aufruf.
MAX_ANTWORT_ZEICHEN = 4096


# ------------------------------------------------------------------ Modelle

class Antwort(BaseModel):
    antworten: Dict = Field(default_factory=dict)


class Zugangsdaten(BaseModel):
    benutzer: str = Field(min_length=2, max_length=64)
    passwort: str = Field(min_length=auth.MIN_PASSWORTLAENGE, max_length=256)


def _heimnetz_pruefen(wert: str) -> str:
    """Ein CIDR, oder gar nichts.

    Ungepruefter Text landete sonst in einer Zeile, die bitcoind liest -- und
    bei einem Tippfehler startet es gar nicht mehr. Ausserdem waere eine
    Freigabe wie 0.0.0.0/0 keine Freigabe fuers Heimnetz, sondern fuer alle,
    die den Port erreichen.

    Freistehend und nicht als Methode, weil zwei Modelle sie brauchen: der
    Assistent stellt dieselbe Frage wie die Einstellungsseite, und zwei
    Abschriften derselben Pruefung waeren eine zu viel.
    """
    roh = (wert or "").strip()
    if not roh:
        return ""
    try:
        netz = ipaddress.ip_network(roh, strict=False)
    except ValueError as fehler:
        raise ValueError("Das ist kein gueltiges Netz (etwa "
                         "192.168.178.0/24).") from fehler
    if netz.prefixlen == 0 or not netz.is_private:
        raise ValueError("Nur private Heimnetze -- eine Freigabe ins offene "
                         "Internet gibt es hier nicht.")
    return str(netz)


# Die Untergrenze fuer maxconnections ist Cores eigene Rechnung (src/net.h,
# v31.1): von den Plaetzen gehen zuerst acht an volle Gegenstellen, dann zwei
# an reine Block-Gegenstellen, dann einer an den Fuehler -- erst was danach
# uebrig ist, steht Eingehenden offen. Bei 8 bleibt also KEINE
# Block-Gegenstelle, und genau die schuetzen davor, unbemerkt von der Kette
# abgetrennt zu werden. 12 ist der kleinste Wert mit beidem: zwei
# Block-Gegenstellen und einem Platz fuer Eingehende.
MINDEST_VERBINDUNGEN = 12


class Leistungswahl(BaseModel):
    speichergrenze_mb: int = Field(2500, ge=400, le=64000)
    upload_gb_pro_monat: int = Field(300, ge=0, le=100000)
    verbindungen: int = Field(80, ge=MINDEST_VERBINDUNGEN, le=125)
    tor_aktiv: bool = True
    netz_ipv4: bool = True
    netz_ipv6: bool = True
    tor_pause_beim_abgleich: bool = True
    # Freiwillig. Leer heisst: der Knoten versucht, seine Adresse von den
    # Gegenstellen zu lernen.
    externe_adresse: str = Field("", max_length=255)
    # Dieselbe Wahl wie in den Einstellungen, mit denselben drei Werten.
    #
    # Aus dem Betrieb, 05.09.2026: "wenn jemand das so neu installiert, hat er ja
    # noch keine Ahnung -- die Installationsanleitung, die wir am Anfang
    # unserer App haben, sollte mit den Funktionen, die wir dann alle schon
    # drin haben, auch gefuehrt sein."
    #
    # Der Befund dahinter war schaerfer als die Frage: seit 0.38.0 fuehrte die
    # Einstellungsseite mit dieser Wahl, der Assistent zeigte weiterhin nur
    # die Haekchen. Zwei Darstellungen derselben Sache, und die wichtigere
    # Entscheidung -- anonym bleiben oder nicht -- traf man im Assistenten,
    # ohne sie je gesehen zu haben.
    sichtbarkeit: Literal["tor", "hybrid", "still"] = "hybrid"
    # Aus welchem Netz eine Wallet-Software den Knoten benutzen darf. Leer
    # heisst: nur die Anwendung selbst.
    rpc_heimnetz: str = Field("", max_length=64)

    _pruefe_heimnetz = field_validator("rpc_heimnetz")(_heimnetz_pruefen)


class Adresswahl(BaseModel):
    externe_adresse: str = Field("", max_length=255)
    # Aus heisst: nur ueber Tor erreichbar. Der eingetragene Name bleibt
    # erhalten -- wer zurueckschaltet, muss ihn nicht neu tippen.
    ankuendigen: bool = True


class Gegenprobe(BaseModel):
    """Die abgefragten Woerter aus dem Seed -- und wie entsperrt werden soll."""
    antworten: Dict[str, str] = {}
    # Vorgabe AUS, und das ist eine Entscheidung, keine Bequemlichkeit.
    # Aus dem Betrieb, 31.08.2026: "das ist ein sicherheits risiko". Er hat recht --
    # nicht fuer den Fall, den er nannte (wer den laufenden Knoten uebernimmt,
    # findet ohnehin das admin.macaroon auf derselben Platte), aber fuer den
    # Fall, der wirklich zaehlt: gestohlene Platte, kopiertes Backup. Dort ist
    # ein Passwort, das danebenliegt, kein Passwort.
    automatisch_entsperren: bool = False
    # Der dritte Weg, seit dem 10.09.2026. Der Betreiber: "das soll sich jeder
    # nutzer aussuchen koennen ob sich das wallet selbst entsperrt ob ich den
    # tresor will .. oder nicht". Leer heisst: das alte Haekchen darueber
    # gilt -- ein gespeicherter Assistentenzustand traegt womoeglich noch
    # nichts anderes.
    entsperrweg: str = Field("", max_length=16)
    # Das Wallet-Passwort. Verlaesst die Anwendung nie in Richtung Platte --
    # ausser der Nutzer waehlt ausdruecklich den Weg "datei".
    passwort: str = Field("", max_length=256)


class Wiederherstellung(BaseModel):
    """Einen gesicherten Knoten zurueckholen.

    Der Gegenweg zur Gegenprobe: dort beweist der Nutzer, dass er die Woerter
    HAT, hier legt er sie vor. Sie werden -- wie beim Anlegen -- nirgendwo
    geschrieben, sondern gehen durch diese Funktion hindurch zu LND und sonst
    nirgendwohin.
    """
    woerter: List[str] = Field(default_factory=list, max_length=64)
    # Nur, wenn der Seed anderswo mit einer Passphrase erzeugt wurde.
    # SatoshiCortex setzt selbst nie eine -- aber wer einen Seed aus `lncli
    # create` mitbringt, kaeme ohne dieses Feld hier nicht weiter.
    passphrase: str = Field("", max_length=256)
    automatisch_entsperren: bool = False
    # Der dritte Weg, seit dem 10.09.2026. Der Betreiber: "das soll sich jeder
    # nutzer aussuchen koennen ob sich das wallet selbst entsperrt ob ich den
    # tresor will .. oder nicht". Leer heisst: das alte Haekchen darueber
    # gilt -- ein gespeicherter Assistentenzustand traegt womoeglich noch
    # nichts anderes.
    entsperrweg: str = Field("", max_length=16)
    passwort: str = Field("", max_length=256)
    # Die Kanalsicherung, base64. Leer heisst: nur die Kette, keine Kanaele.
    kanalsicherung: str = Field("", max_length=4_000_000)
    # Statt sie hochzuladen: von dem WebDAV-Ziel holen, das eingerichtet ist.
    vom_ziel: bool = False


class Sicherungsprobe(BaseModel):
    """Eine Sicherung zum Nachsehen vorlegen.

    Leer heisst: die des laufenden Knotens. Sonst die base64-kodierte Datei,
    die der Nutzer in der Hand hat -- und genau darum geht es. Dass der Knoten
    eine heile Sicherung erzeugen KANN, sagt nichts darueber, ob die Kopie auf
    dem Stick die richtige ist.
    """
    blob: str = Field("", max_length=4_000_000)
    vom_ziel: bool = False


class Gebuehren(BaseModel):
    """Was der Knoten fuers Weiterleiten nimmt.

    Die Obergrenzen sind nicht willkuerlich: wer ein Vielfaches des
    Netz-Ueblichen setzt, wird schlicht gemieden -- das gehoert verhindert,
    bevor jemand sich wundert, warum nichts mehr durchgeht.

    Was "ueblich" heisst, steht hier bewusst NICHT als Zahl. Bis zum
    18.09.2026 tat es das -- "rund 143 ppm" -- und eine solche Zahl altert
    still. Der Knoten kann sie selbst messen; das tut satcortex/gebuehren.py.
    """
    basis_msat: int = Field(0, ge=0, le=100_000)
    satz_ppm: int = Field(100, ge=0, le=10_000)
    zeitsperre: int = Field(144, ge=18, le=2016)
    # Leer heisst: fuer alle Kanaele.
    kanalpunkt: str = Field("", max_length=128)


class Gebuehrenautomatik(BaseModel):
    """Soll der Knoten seinen Satz dem Netz nachfuehren?"""
    automatik: bool = False


class Sicherungsziel(BaseModel):
    """Wohin die Kanalsicherung geht. Leere URL heisst: gar nicht mehr."""
    url: str = Field("", max_length=1024)
    benutzer: str = Field("", max_length=256)
    passwort: str = Field("", max_length=512)


class Entsperrwegwahl(BaseModel):
    """Den Entsperrweg an einer BESTEHENDEN Wallet wechseln.

    Ob das Passwort mitgeschickt werden muss, haengt am heutigen Weg: liegt
    es in der Klartextdatei oder im Speicher dieser Anwendung, holt sie es
    sich dort. Liegt es nirgends, muss der Nutzer es tippen.
    """
    weg: str = Field(max_length=16)
    # Das heutige Wallet-Passwort -- nur noetig, wenn es nirgends liegt.
    passwort: str = Field("", max_length=256)


class Entsperrung(BaseModel):
    """Eine gesperrte Wallet aufmachen -- mit dem Wallet-Passwort.

    Es gibt nur dieses eine Geheimnis. Ein zweites danebenzustellen, das
    dasselbe tut, war der Fehler des Tresors.
    """
    passwort: str = Field("", max_length=256)


class Kanalwunsch(BaseModel):
    """Einen Kanal oeffnen -- der Schritt, der aus einem Knoten einen
    Teilnehmer macht.

    Bis zum 12.09.2026 bot diese Anwendung dafuer keinen Endpunkt an, und in
    der README stand: "When one appears, it belongs behind the same PIN."
    Genau so ist es gekommen.
    """
    # Kennung@Adresse:Port, so wie es im Graphen steht.
    gegenstelle: str = Field("", max_length=256)
    betrag: int = Field(0, ge=0, le=21_000_000 * 100_000_000)
    tempo: str = Field("normal", max_length=16)
    # Ein privater Kanal steht in keinem Graphen -- fuer einen Knoten, der
    # teilnehmen soll, ist das die Ausnahme und nicht die Vorgabe.
    privat: bool = False
    pin: str = Field("", max_length=32)


class Umschichtung(BaseModel):
    """Zwischen eigenen Kanaelen umschichten.

    "von" ist der Kanal, durch den es HINAUSgeht -- der wird leerer.
    "nach" ist die Gegenstelle, ueber die es ZURUECKkommt -- die wird voller.
    """
    von: str = Field("", max_length=32)
    nach: str = Field("", max_length=80)
    betrag: int = Field(0, ge=0, le=21_000_000 * 100_000_000)
    gebuehrengrenze: int = Field(0, ge=0, le=100_000_000)
    pin: str = Field("", max_length=32)


class Kanalschluss(BaseModel):
    """Einen Kanal schliessen.

    "erzwingen" ist ein eigener Schalter und keine Ausweichroute: das
    einvernehmliche Schliessen ist guenstig und sofort, das erzwungene teuer
    und mit Wartezeit. Wer das eine will, will selten still das andere.
    """
    punkt: str = Field("", max_length=160)
    tempo: str = Field("normal", max_length=16)
    erzwingen: bool = False
    pin: str = Field("", max_length=32)


class Wachturm(BaseModel):
    """Einen Wachturm eintragen -- Kennung@Adresse:Port."""
    adresse: str = Field("", max_length=256)


class Wachturmaustrag(BaseModel):
    """Einen Wachturm austragen -- seine Kennung."""
    kennung: str = Field("", max_length=66)


class Adressfrage(BaseModel):
    """Eine Adresse, deren Bestand abgefragt werden soll."""
    adresse: str = Field("", max_length=100)


class Rechnungsanfrage(BaseModel):
    """Eine eigene Rechnung, damit jemand an diesen Knoten zahlen kann.

    Betrag 0 ist erlaubt und heisst: die Rechnung nennt keinen, der Zahlende
    bestimmt ihn.
    """
    betrag: int = Field(0, ge=0, le=21_000_000 * 100_000_000)
    zweck: str = Field("", max_length=120)
    gueltig_min: int = Field(60, ge=1, le=1440)


class Rechnungswunsch(BaseModel):
    """Eine Lightning-Rechnung lesen oder bezahlen."""
    rechnung: str = Field("", max_length=2048)
    # Nur bei einer Rechnung OHNE Betrag -- dann bestimmt ihn der Zahlende.
    betrag: int = Field(0, ge=0, le=21_000_000 * 100_000_000)
    # Was die Weiterleitung hoechstens kosten darf. 0 heisst "nimm den
    # Vorschlag" -- die Zahl steht dann in der Vorschau.
    gebuehrengrenze: int = Field(0, ge=0, le=100_000_000)
    pin: str = Field("", max_length=32)


class Sendung(BaseModel):
    """On-Chain senden -- der Weg zurueck aus der Wallet heraus.

    Die Bedingung des Betreibers vom 30.08.2026: "ich werde nix dahin ueberweisen
    solange ich es nicht zurueck schicken kann". Eine Wallet, aus der man
    nicht wieder herauskommt, ist keine Wallet.

    Das Tempo ist KEINE Satoshi-je-vByte-Zahl, und das ist Absicht: die
    Schaetzung kommt aus dem EIGENEN bitcoind (estimatesmartfee fuer einen,
    drei und sechs Bloecke). Wer die Zahl selbst setzen will, sieht sie in
    der Schaetzung stehen -- raten muss sie niemand.
    """
    adresse: str = Field("", max_length=128)
    betrag: int = Field(0, ge=0, le=21_000_000 * 100_000_000)
    # Alles heisst alles: die On-Chain-Wallet wird leergeraeumt, die Gebuehr
    # geht vom Betrag ab. Dann darf KEIN Betrag danebenstehen.
    alles: bool = False
    tempo: str = Field("normal", max_length=16)
    pin: str = Field("", max_length=12)


class Netzwegewahl(BaseModel):
    """Die vier Wege, auf denen dieser Knoten am Netz teilnimmt.

    Sie sind ausdruecklich UNABHAENGIG voneinander. Kein Schalter legt einen
    anderen um, keiner sperrt einen anderen -- Tor und Clearnet sind kein
    Entweder-oder, sondern zwei Wege, die derselbe Knoten gleichzeitig geht.
    Genau diese Bruecke ist im Netz knapp.

    Die einzige Grenze ist keine zwischen den Schaltern, sondern eine des
    Ganzen: sind alle drei Netze aus, hat der Knoten keinen Weg mehr hinaus.
    """
    tor: bool = True
    ipv4: bool = True
    ipv6: bool = True
    # Der Name (oder die feste IP), unter der andere den Knoten finden.
    externe_adresse: str = Field("", max_length=255)
    adresse_ankuendigen: bool = True
    # Kein vierter Weg, sondern eine Einstellung zum ersten: waehrend die
    # Kette laedt, ruft der Knoten ueber Tor niemanden von sich aus an. Er
    # bleibt dabei unter seiner Onion-Adresse erreichbar.
    tor_pause_beim_abgleich: bool = True
    # Was dieser Knoten von sich preisgibt -- fuer BEIDE Dienste.
    #
    # Aus dem Betrieb, 05.09.2026: "verstehe nicht, warum diese Einstellungen nur
    # fuer LND gelten und nicht generell fuer unsere App?" -- und gleich
    # darauf: "kann ja auch fuer BTC gut sein, die Auswahl."
    #
    # Er hat recht, und es gab keinen guten Grund, nur einen historischen. Die
    # Faehigkeit war bei bitcoind laengst da: Tor an, IPv4 und IPv6 aus ergibt
    # onlynet=onion, also genau "nur ueber Tor". Verschieden war allein die
    # Darstellung -- drei Haekchen hier, drei Knoepfe dort.
    #
    #   "tor"    Nur ueber Tor. Angekuendigt wird ausschliesslich die
    #            Onion-Adresse; nach draussen geht nichts am Tor vorbei.
    #   "hybrid" Tor UND Clearnet. Die Haekchen fuer IPv4/IPv6 gelten, die
    #            eigene Adresse wird angekuendigt. Schneller, IP oeffentlich.
    #   "still"  Nichts ankuendigen. Ausgehend wie gewaehlt, aber niemand
    #            kann von aussen einen Kanal oder eine Verbindung aufbauen.
    sichtbarkeit: Literal["tor", "hybrid", "still"] = "hybrid"
    # Aus welchem Netz eine Wallet-Software den Knoten benutzen darf. Leer
    # heisst: nur die Anwendung selbst, wie bisher.
    #
    # Aus dem Betrieb, 05.09.2026: "was mir auch schmecken wuerde, wenn ich meine
    # Transaktionen von meinem Hardware-Wallet dann auch ueber meinen
    # BTC-Knoten machen koennte."
    rpc_heimnetz: str = Field("", max_length=64)

    _pruefe_heimnetz = field_validator("rpc_heimnetz")(_heimnetz_pruefen)


class Nachrichtenwahl(BaseModel):
    """Was der Nutzer am Feed einstellt."""
    aktiv: bool = False
    # Eng ist die Vorgabe: Bitcoin und Lightning. Der weite Filter nimmt die
    # Krypto-Nachbarschaft dazu -- gemessen ist das bei einer Fachquelle der
    # Unterschied zwischen "Bitcoin" und "auch Ethereum und Zcash".
    weit: bool = False
    # Gemerkt wird der WIDERSPRUCH zur Werksvorgabe, nicht die Auswahl.
    # Sonst bleibt jede spaeter hinzugefuegte Quelle bei bestehenden Nutzern
    # fuer immer aus -- genau das ist am 06.09.2026 passiert.
    abgewaehlt: Optional[List[str]] = None
    zugewaehlt: List[str] = []
    eigene: List[Dict] = []


class Quellensuche(BaseModel):
    adresse: str


class Freigabewahl(BaseModel):
    """Die PIN einrichten.

    Das KONTOPASSWORT gehoert dazu, und das ist kein Zierrat: waere es
    anders, koennte eine uebernommene Sitzung sich selbst eine PIN geben und
    damit anschliessend alles freigeben. Ein Schloss, dessen Schluessel der
    Einbrecher aussucht, ist keines.
    """
    passwort: str = Field(max_length=512)
    pin: str = Field(max_length=32)


class Pinwechsel(BaseModel):
    alt: str = Field(max_length=32)
    neu: str = Field(max_length=32)


class Pineingabe(BaseModel):
    pin: str = Field(max_length=32)


class Wallettilgung(BaseModel):
    """Die Wallet loeschen, um von vorn anzufangen.

    Zwei Angaben, und beide muessen stimmen: das Wallet-Passwort -- das bei
    abgeschaltetem Auto-Entsperren NIRGENDS auf der Platte liegt -- und der
    Name des Knotens, abgetippt. Der Name ist keine Sicherheit, sondern eine
    Bremse: er zwingt dazu, kurz hinzusehen, statt auf einen roten Knopf zu
    klicken.
    """
    passwort: str = Field("", max_length=256)
    alias: str = Field("", max_length=64)
    # Und die PIN, sobald eine eingerichtet ist. Eine PIN, die nichts
    # bewacht, waere eine Behauptung -- das Loeschen ist heute der einzige
    # Handgriff, der etwas Unwiederbringliches tut, also faengt sie dort an.
    pin: str = Field("", max_length=32)


class Hinweiswahl(BaseModel):
    was: str = Field("", max_length=40)


class Gegenstellenwahl(BaseModel):
    """Die uebliche Zeile aus dem Graphen: Kennung@Adresse:Port."""
    # Grosszuegig: eine Onion-Adresse allein ist 62 Zeichen, dazu 66 fuer
    # die Kennung, das At und der Port.
    adresse: str = Field("", max_length=200)


class Knotenname(BaseModel):
    """Wie dieser Knoten im Lightning-Netz heisst, aussieht -- und was er annimmt.

    Aus dem Betrieb, 09.09.2026: "ich moechte nicht das alles immer nur
    satoshicortex heisst!!" -- und er hatte recht: der Alias stand als
    Vorgabe in einer Datenklasse und wurde beim Einrichten NIE uebergeben.
    Jeder Knoten dieser Software hiess damit gleich, was fuer ihn nutzlos
    und fuer das Netz verwirrend ist.
    """
    # Die Laenge prueft nodeconfig.pruefe_alias in BYTE, nicht in Zeichen --
    # durch den Gossip passen 32 Byte, und ein Emoji frisst vier davon.
    alias: str = Field("", max_length=32)
    farbe: str = Field("", max_length=7)
    # Die kleinste Kanalgroesse, die dieser Knoten ANNIMMT. Sie steht hier
    # bei Name und Farbe, weil alle drei in derselben lnd.conf landen -- und
    # ein Neustart fuer drei Aenderungen ist besser als drei Neustarts.
    #
    # Null heisst "nicht mitgeschickt" und laesst den bisherigen Wert stehen.
    # Ohne diese Unterscheidung wuerde jeder Klick auf "Namen speichern" aus
    # einer aelteren Oberflaeche die Untergrenze stillschweigend
    # zurueckdrehen -- dieselbe Falle wie ein Vorgabewert, der zugleich ein
    # gueltiger Wert ist.
    minchansize: int = Field(0, ge=0, le=100_000_000)


class Unterschriftswahl(BaseModel):
    """Der Text, den eine fremde Stelle unterschrieben sehen will.

    Grosszuegig bemessen und trotzdem begrenzt: LightningNetwork+ und
    Verwandte geben kurze Zeichenketten vor, ein Megabyte waere nur eine
    Einladung.
    """
    text: str = Field("", max_length=2000)


log = logging.getLogger(__name__)

# Wie lange ein erzeugter Seed auf seine Gegenprobe wartet. Lange genug, um
# vierundzwanzig Woerter in Ruhe abzuschreiben und zweimal zu vergleichen;
# kurz genug, dass er nicht den ganzen Tag im Speicher steht, weil jemand den
# Reiter offen gelassen hat.
SEED_FRIST_SEKUNDEN = 30 * 60

# Wie viele Stellen abgefragt werden. Vier von vierundzwanzig heisst: wer
# raet, hat rechnerisch keine Chance -- und wer abgeschrieben hat, ist in
# einer halben Minute durch.
GEGENPROBE_STELLEN = 4
GEGENPROBE_VERSUCHE = 5

# Wie lange auf ein sauber beendetes LND gewartet wird. Der Waechter im
# Startskript sieht die fehlende Freigabe im Sekundentakt; danach schreibt
# LND seine Kanal-Datenbank weg. Die Compose gibt ihm dafuer drei Minuten
# (stop_grace_period), hier genuegt weniger: es geht nur darum, dass der
# Prozess wirklich weg ist, bevor jemand an seine Dateien geht.
# Die drei Wege, auf denen eine Wallet wieder aufgeht. Die Wahl gehoert dem
# Nutzer -- Aus dem Betrieb, 10.09.2026: "das soll sich jeder nutzer aussuchen
# koennen ob sich das wallet selbst entsperrt ob ich den tresor will .. oder
# nicht".
#
#   aus     nichts liegt irgendwo, und die Anwendung merkt sich nichts. Nach
#           JEDEM Neustart tippt jemand das Wallet-Passwort -- auch nach
#           einem, den diese Anwendung selbst ausgeloest hat.
#   merken  nichts liegt auf der Platte. Die Anwendung behaelt das Passwort,
#           solange sie laeuft: startet SIE LND neu, macht sie die Wallet
#           selbst wieder auf. Nach einem Stromausfall wird wieder getippt.
#   datei   das Wallet-Passwort im Klartext neben der Wallet. Der Knoten
#           laeuft nach einem Stromausfall von allein weiter -- und wer die
#           Platte hat, hat beides.
#
# Der Tresor, der hier bis zum 10.09.2026 als dritter Weg stand, ist weg.
# Der Betreiber hat ihn zerlegt: "ich tausche ein passwort gegen das andere obwohl
# beide die selbe funktion unterm strich haben". Die Begruendung steht bei
# merker.Merker; "merken" loest das Problem, das der Tresor loesen sollte,
# ohne ein zweites Geheimnis und ohne eine zweite Datei.
ENTSPERRWEGE = ("aus", "merken", "datei")

WALLET_NEUSTART_FRIST = 90.0


def _wege(wahl: Optional[Dict]) -> Dict:
    """Die vier Schalter aus der gespeicherten Wahl -- mit Vorgaben.

    Wer vor 0.16.0 eingerichtet hat, hat nur "tor_aktiv" gespeichert. Fehlende
    Schalter stehen deshalb auf AN: das ist der Zustand, in dem solch ein
    Knoten bisher lief, und ein Update darf ihm nicht stillschweigend ein Netz
    abschalten.
    """
    w = wahl or {}
    gelesen = {
        "tor": bool(w.get("tor_aktiv", True)),
        "ipv4": bool(w.get("netz_ipv4", True)),
        "ipv6": bool(w.get("netz_ipv6", True)),
        "externe_adresse": w.get("externe_adresse", "") or "",
        "adresse_ankuendigen": bool(w.get("adresse_ankuendigen", True)),
        "tor_pause_beim_abgleich": bool(w.get("tor_pause_beim_abgleich", True)),
        "sichtbarkeit": _sichtbarkeit_von(w),
        "rpc_heimnetz": w.get("rpc_heimnetz", "") or "",
    }
    # Bewusst NICHT abgeleitet: hier steht, was der Nutzer gewaehlt hat. Wer
    # von "nur ueber Tor" zurueckschaltet, findet sein IPv4 wieder vor, statt
    # es neu anhaken zu muessen. Was daraus fuer die Konfiguration folgt,
    # entscheidet _nach_sichtbarkeit -- eine Ebene tiefer.
    return gelesen


# Welche Hinweise sich wegklicken lassen. Ausdruecklich NICHT die, die einen
# Zustand beschreiben: eine gesperrte Wallet verschwindet, wenn man sie
# entsperrt, nicht wenn man den Hinweis wegnimmt.
ABWEISBAR = ("sicherungsziel", "wachturm")


def _abgewiesen(e) -> list:
    return list((e.knotenwahl or {}).get("hinweise_abgewiesen") or [])


def _sichtbarkeit_von(w: Dict) -> str:
    """Die Betriebsart -- gespeichert, oder aus dem Bestand abgeleitet.

    Die Ableitung ist der heikle Teil. Ein Knoten, der seit Tagen abgleicht,
    darf durch ein Update NICHT ploetzlich auf onlynet=onion springen: das
    kostete der Betreiber seine zehn IPv4-Gegenstellen mitten im Erstabgleich.
    Abgeleitet wird deshalb aus dem, was er HEUTE tut, nicht aus einer
    Vorgabe -- und ausdruecklich nicht aus dem alten Feld
    "lightning_sichtbarkeit". Das galt nur fuer LND und stand auf "tor";
    darauf umzuschalten waere genau der Sprung, den es zu vermeiden gilt.
    """
    gespeichert = w.get("sichtbarkeit")
    if gespeichert in ("tor", "hybrid", "still"):
        return gespeichert
    if not bool(w.get("adresse_ankuendigen", True)):
        return "still"
    if bool(w.get("netz_ipv4", True)) or bool(w.get("netz_ipv6", True)):
        return "hybrid"
    return "tor"


def _nach_sichtbarkeit(wege: Dict) -> Dict:
    """Die Wahl auf die einzelnen Schalter anwenden.

    EINE Stelle, sonst driften Lesen und Schreiben auseinander. Die Wahl ist
    das Grobe, die Haekchen sind die Feinheit darunter -- und in der
    Betriebsart "nur ueber Tor" gibt es nichts fein einzustellen: dort ist
    Clearnet aus, sonst waere die Wahl eine Behauptung ohne Folge.
    """
    aus = dict(wege)
    if aus["sichtbarkeit"] == "tor":
        aus["ipv4"] = False
        aus["ipv6"] = False
        aus["adresse_ankuendigen"] = False
    elif aus["sichtbarkeit"] == "still":
        aus["adresse_ankuendigen"] = False
    return aus


def _erlaubte_netze(wege: Dict, lage: Optional[Dict],
                    jetzt: tuple = ()) -> Tuple[list, str]:
    """Welche Netze der Knoten selbst anrufen darf -- und warum.

    Zwei Dinge kommen hier zusammen, und sie duerfen einander nicht
    ueberschreiben: was der Nutzer eingestellt hat, und in welcher
    Betriebsphase der Knoten gerade ist. Die Phase kann Tor voruebergehend
    aussen vor lassen; den SCHALTER laesst sie unangetastet. Sobald die Kette
    steht, gilt wieder ausschliesslich das Eingestellte.

    "jetzt" ist, was in der Konfiguration schon steht. Ohne diese Angabe
    entstuende ein Pendel: die Pause nimmt Tor den Ausgang, daraufhin faellt
    die Zahl der Tor-Gegenstellen auf null, daraufhin greift die Bedingung
    "nur pausieren, wenn es Tor-Gegenstellen gibt" nicht mehr, die Pause faellt
    weg -- und zehn Minuten spaeter von vorn. Jeder Durchgang mit einem
    bitcoind-Neustart.
    """
    erlaubt = [n for n, an in (("ipv4", wege["ipv4"]), ("ipv6", wege["ipv6"]))
               if an]
    if not wege["tor"]:
        return erlaubt, ""

    # OHNE LAGE WIRD NICHTS ENTSCHIEDEN.
    #
    # Hier stand bis zum 01.09.2026 nur "bool((lage or {}).get(...))" -- und
    # damit galt eine AUSGEFALLENE Abfrage als "kein Erstabgleich". Waehrend
    # des Abgleichs faellt getblockchaininfo regelmaessig aus: es braucht
    # cs_main, und Core haelt die Sperre bei jedem chainstate-Schreibvorgang.
    # Am 28.08.2026 gemessen: rund jeder fuenfte Abruf kam nicht durch.
    #
    # Die Folge war ein Pendel mit teuren Ausschlaegen. Faellt die Lage aus,
    # wird die Pause aufgehoben -> onlynet verschwindet -> die Datei aendert
    # sich -> gib_frei() -> bitcoind startet neu. Kommt die Lage zurueck,
    # greift die Pause wieder -> onlynet zurueck -> noch ein Neustart. Jeder
    # davon kostet auf einem NAS Minuten zum Laden des chainstate, und in der
    # Zeit hat der Knoten KEINE Verbindungen -- genau das Bild, das der Betreiber
    # gemeldet hat: "quasi keine Verbindung mehr zu irgendwas".
    #
    # Richtig ist: was gerade laeuft, bleibt. Die Schalter des Nutzers gelten
    # weiter -- ueber die entscheidet die Phase ohnehin nicht.
    if lage is None:
        if not jetzt or "onion" in jetzt:
            return erlaubt + ["onion"], ""
        return erlaubt, nodeconfig.ABGLEICH_GRUND

    im_erstsync = bool(lage.get("im_erstsync"))
    if not (im_erstsync and wege["tor_pause_beim_abgleich"]):
        return erlaubt + ["onion"], ""
    if not erlaubt:
        # Ohne einen anderen Weg waere die Pause ein stiller Schuss ins Knie:
        # der Knoten haette waehrend des Abgleichs gar keinen Ausgang mehr.
        return ["onion"], ""
    if jetzt and "onion" not in jetzt:
        return erlaubt, nodeconfig.ABGLEICH_GRUND   # laeuft schon so
    # Vor dem Umschalten wird auf die Wirklichkeit geschaut, nicht auf den
    # Schalter: ohne Clearnet-Gegenstellen faende der Knoten anschliessend
    # womoeglich niemanden mehr, und ohne Tor-Gegenstellen gaebe es nichts
    # abzuschalten -- der Neustart waere dann umsonst.
    netze = lage.get("netze") or {}
    if (netze.get("ipv4") or netze.get("ipv6")) and netze.get("onion"):
        return erlaubt, nodeconfig.ABGLEICH_GRUND
    return erlaubt + ["onion"], ""


def _adressliste(eingabe: str) -> tuple:
    """Eine Eingabe wie "1.2.3.4, meinhost.example" in einzelne Adressen.

    Bewusst nachsichtig beim Trennzeichen und streng beim Inhalt: was Core
    nicht aufloesen kann, verwirft es beim Start ohnehin -- aber Leerzeichen
    oder Anfuehrungszeichen in einer conf-Zeile fuehren zu Fehlern, die
    niemand sucht.
    """
    if not eingabe:
        return ()
    roh = eingabe.replace(";", ",").replace(" ", ",").split(",")
    return tuple(a.strip().strip('"\'') for a in roh if a.strip())


# ------------------------------------------------------------------ Anwendung

def baue_app(konf: Optional[settings.Einstellungen] = None) -> FastAPI:
    konf = konf or settings.laden()
    # Zwei Pfade gibt der Nutzer an, alles darunter entsteht hier -- und zwar
    # jetzt, nicht erst beim Abschliessen des Assistenten: die Zeilen darunter
    # schreiben bereits nach <fast>/config.
    # Als Erstes: ab hier landen die eigenen Meldungen zusaetzlich in einem
    # Ringspeicher, damit die Oberflaeche sie zeigen kann. Sie gehen weiterhin
    # auch nach stdout -- das Container-Protokoll bleibt unveraendert. Ganz
    # nach vorn, weil die Zeilen darunter bereits melden koennen.
    logs.mitschreiben()
    storage.bereite_vor(konf.bulk, konf.fast)
    zustand = state.Ablage(konf.config_dir)
    # Lebt im Arbeitsspeicher und fuellt sich, waehrend die Uebersicht offen
    # ist. Nach einem Neustart gibt es einige Minuten keine Restdauer -- lieber
    # keine Zahl als eine erfundene.
    verlauf = tempo.Verlauf()
    # Ergebnis der letzten Versionsabfrage, je Projekt. Lebt im
    # Arbeitsspeicher: nach einem Neustart wird einfach neu nachgesehen.
    neuerungen: Dict[str, Dict] = {
        p.name: {"stand": None, "gefunden": None, "grund": "",
                 "abbild": p.abbild, "variable": p.variable,
                 "laeuft": None, "versucht": None,
                 # Die beiden Zahlen, um die es eigentlich geht. Aus dem Betrieb, am
                 # 03.09.2026: "entweder weiss er welche version wir haben
                 # und welche bereit steht oder er weiss es nicht". Sie
                 # gehoeren in die Antwort, nicht nur in einen Fliesstext.
                 "laufend": None, "neueste": None,
                 "fehlversuche": 0}
        for p in updates.PROJEKTE
    }
    # Was der Knoten zuletzt als seine Fassung gemeldet hat. Siehe
    # nach_updates_sehen(): eine ausgefallene Abfrage darf sie nicht loeschen.
    kennungsspeicher: Dict[str, str] = {"wert": ""}
    ablage = services.Konfigurationsablage(konf.config_dir)

    # Die Ortstabelle liegt im Abbild und wird einmal geladen. Fehlt sie,
    # bleibt sie None -- die Karte sagt das dann selbst, statt zu scheitern.
    ortstabelle = geo.lade()
    # Die Namen zu den Gebietsnummern aus der Ortstabelle. Fehlen sie,
    # bleibt die Karte bei den Laendern -- kein Grund, nicht zu starten.
    gebietsnamen = gebiete.lade()
    # Das Adressbuch ist der einzige teure Aufruf der ganzen Anwendung.
    # Deshalb wertet ihn der Waechter aus und legt das Ergebnis hier ab.
    kartenbuch: Dict = {"stand": None, "daten": None, "laeuft": False,
                        # Wo der Knoten steht -- nebenbei beim
                        # Auffrischen ermittelt. Der Nachrichten-Feed
                        # waehlt daran seine Sprache, ohne dafuer eine
                        # eigene Frage zu stellen.
                        "heimat": None}

    # Die Auswertung. Die Datenbank liegt auf der schnellen Platte -- bei
    # zwoelf Millionen Zeilen ist das kein Detail, sondern der Unterschied
    # zwischen fluessig und zaeh.
    # oeffne statt Ablage(): auf einem NAS gehoert der eingehaengte Ordner
    # haeufig einem anderen Benutzer, und dann laesst sich hier nicht
    # schreiben. Die Auswertung ist ein Teil, nicht das Ganze -- Assistent,
    # Uebersicht und Karte haben mit ihr nichts zu tun und sollen laufen.
    auswertung = store.oeffne(str(Path(konf.fast) / "app" / "auswertung.db"))
    poolliste = pools.lade()

    def _tor_proxy() -> Optional[str]:
        """Der Weg nach draussen -- oder nichts.

        Nichts heisst: es wird nicht gefragt. Dieselbe Regel wie bei der
        Versionsabfrage, und aus demselben Grund: eine Abfrage an einem Verlag
        verraet sonst, dass hier jemand einen Bitcoin-Knoten betreibt, und mit
        der Zeit auch, wann er laeuft.
        """
        e = zustand.laden()
        if not bool((e.knotenwahl or {}).get("tor_aktiv", True)):
            return None
        return f"http://{konf.tor_host}:{konf.tor_http_port}"

    feed = nachrichten.Feed(auswertung, _tor_proxy, zustand)
    # Der Kurs kommt von aussen -- der Knoten kennt keinen. Deshalb
    # derselbe Weg und dieselbe Regel: ohne Tor wird nicht gefragt.
    kurstafel = kurs.Kurstafel(_tor_proxy)
    # Eigener Stand statt des Aufraeumstands weiter unten: der
    # entsteht erst spaeter im Bauplan, und eine Abhaengigkeit von
    # der Reihenfolge zweier Zeilen ist eine Falle fuer den Naechsten.
    nachrichtenstand = {"aufgeraeumt": 0.0}

    app = FastAPI(
        title="SatoshiCortex",
        description="Eigener Bitcoin- und Lightning-Knoten",
        docs_url="/api/doku",
    )
    konten = auth.Kontoverwaltung(konf.config_dir)
    # Das Wallet-Passwort fuer die Laufzeit -- im Speicher, nirgendwo sonst.
    # Es ueberlebt einen Neustart von LND, aber keinen dieser Anwendung.
    walletmerker = merker.Merker()
    # Die PIN liegt daneben. Sie hat mit der Wallet nichts zu tun -- sie ist
    # das Schloss vor den Handgriffen dieser Anwendung.
    freigabe = auth.Freigabe(konf.config_dir)
    api = APIRouter(prefix="/api")

    def benoetigt_anmeldung(
        satcortex_sitzung: Optional[str] = Cookie(default=None),
    ) -> None:
        """Torwaechter fuer alles, was den Knoten betrifft.

        Vorher war jeder Endpunkt offen: wer die Adresse im Heimnetz kannte,
        konnte einen LAUFENDEN Knoten umkonfigurieren -- Tor abschalten, den
        Upload entfesseln oder die Verbindungen auf 8 druecken und damit eine
        Eclipse-Attacke erheblich erleichtern.
        """
        if not konten.angemeldet(satcortex_sitzung):
            raise HTTPException(401, {"meldung": "anmeldung_noetig"})

    geschuetzt = [Depends(benoetigt_anmeldung)]

    # ----------------------------------------------------------- Konto
    @api.get("/zustand")
    def zustand_oeffentlich(
        anfrage: Request,
        satcortex_sitzung: Optional[str] = Cookie(default=None),
    ) -> Dict:
        """Das Einzige, was ohne Anmeldung zu erfahren ist: ob es schon ein
        Konto gibt und ob diese Sitzung gilt."""
        return {
            "konto_vorhanden": konten.vorhanden,
            "angemeldet": konten.angemeldet(satcortex_sitzung),
            "version": konf.version,
            # Damit die Oberflaeche die Zahl nicht ein zweites Mal fuehren
            # muss -- zweimal getippt heisst irgendwann zweimal
            # verschieden. Sie stand in zwei Uebersetzungen fest drin.
            "passwort_mindestlaenge": auth.MIN_PASSWORTLAENGE,
            # Ohne beschreibbare Ablage laesst sich kein Konto anlegen und
            # keine Konfiguration schreiben. Frueher starb die Anwendung an
            # dieser Stelle wortlos; jetzt sagt sie es, damit man PUID/PGID
            # und die Rechte pruefen kann, statt zu raten.
            "verschluesselt": konf.tls_aktiv,
            "ablage_bereit": os.access(konf.config_dir, os.W_OK),
            "ablage_pfad": konf.config_dir,
            # Womit man sich hier anmelden kann. Beides, damit die Oberflaeche
            # kein Feld zeigt, das der Server ohnehin abweist -- ein
            # Anmeldefenster, das nie funktioniert, ist schlimmer als keines.
            "oidc": konf.oidc_aktiv,
            "lokal_moeglich": _lokal_erlaubt(anfrage),
        }

    def _verschluesselt_zum_browser() -> bool:
        """Ist die Strecke bis zum Browser verschluesselt?

        NICHT dasselbe wie "wir halten das Zertifikat". Hinter einem Reverse
        Proxy spricht diese Anwendung Klartext, der Browser aber https --
        und genau dann braucht das Cookie sein Secure am dringendsten.
        Ohne TLS_EXTERN bekaeme es ausgerechnet im Internet-Betrieb keines.
        """
        return konf.tls_aktiv or konf.tls_extern

    def _setze_sitzung(antwort: Response, token: str) -> None:
        antwort.set_cookie(
            SITZUNGS_KEKS, token,
            httponly=True,        # kein Zugriff aus JavaScript
            # "lax", nicht "strict" -- und das ist eine Bedingung, keine
            # Lockerung. Bei der Rueckkehr vom Ausweisdienst ist der Aufruf
            # ein Seitenwechsel von fremder Seite; unter "strict" schickt der
            # Browser das Cookie dabei NICHT mit, und die Anmeldung ueber
            # Pocket ID endete stumm wieder am Anfang. "lax" sendet bei
            # solchen Wechseln nur bei GET -- schreibende Aufrufe von fremden
            # Seiten bleiben aussen vor, worum es bei "strict" ging.
            samesite="lax",
            # Unter reinem HTTP wuerde secure das Merkmal unbrauchbar machen
            # und niemanden mehr hereinlassen.
            secure=_verschluesselt_zum_browser(),
            path="/",
            max_age=auth.SITZUNG_GUELTIG_SEKUNDEN,
        )

    @api.post("/konto/anlegen")
    def konto_anlegen(daten: Zugangsdaten, antwort: Response) -> Dict:
        try:
            konten.lege_an(daten.benutzer, daten.passwort)
        except PermissionError:
            raise HTTPException(409, {"meldung": "konto_existiert"})
        except ValueError as f:
            raise HTTPException(400, {"meldung": str(f)})
        _setze_sitzung(antwort, konten.melde_an(daten.benutzer, daten.passwort))
        return {"ok": True}

    # ── Anmeldung ueber Pocket ID, und die Nottuer dahinter ───────────────
    #
    # Aus dem Betrieb, 11.09.2026: "generelle solte das sauber funktionieren so das
    # ich quasie kein lock in fenster mehr habe sonder nur noch pocket id mich
    # einloggt oder wenn ein neuer von mir freigebner pocket id nutzer sich da
    # anmelden kann".
    #
    # WER hereindarf, entscheidet dabei Pocket ID, nicht diese Anwendung: ein
    # neuer OIDC-Client erlaubt dort zunaechst NIEMANDEM den Zugang, und man
    # gibt gezielt Gruppen frei. Eine zweite Namensliste hier waere eine
    # zweite Wahrheit, die mit der ersten auseinanderlaeuft.
    #
    # Die Nottuer ist seine Entscheidung vom selben Abend: das lokale Konto
    # bleibt, aber nur noch fuer Aufrufe, die NICHT durch den Reverse Proxy
    # gekommen sind. Von aussen gibt es damit wirklich nur Pocket ID; im
    # Heimnetz steht die Tuer, durch die man wieder hereinkommt, wenn der
    # Ausweisdienst ausfaellt oder der Passkey weg ist. Auf einem Geraet mit
    # einer Wallet darin ist "ausgesperrt" kein hinnehmbarer Zustand.

    def _ortsnah(anfrage: Request) -> bool:
        """Kam dieser Aufruf direkt aus dem Heimnetz -- ohne Proxy dazwischen?

        Zwei Bedingungen, und beide werden gebraucht:

        * Die Gegenstelle ist eine private Adresse. Allein genuegt das NICHT:
          laeuft der Reverse Proxy auf demselben NAS, ist auch ein Aufruf aus
          dem Internet am Ende ein Aufruf von nebenan.
        * Es liegt KEIN Weiterleitungskopf an. Den setzt jeder Proxy von
          selbst; faelschen kann ihn nur, wer die Anwendung ohnehin schon
          direkt erreicht -- und dafuer muesste er im Heimnetz stehen.

        Damit das stimmt, darf der Oberflaechen-Port nicht ins Internet
        weitergereicht werden. Nach aussen gehen 8333 und 9735, auf Wunsch der
        Wachturm auf 9911 -- die Oberflaeche nie.
        """
        for kopf in ("x-forwarded-for", "x-forwarded-host",
                     "x-forwarded-proto", "forwarded"):
            if anfrage.headers.get(kopf):
                return False
        gegenstelle = (anfrage.client.host if anfrage.client else "") or ""
        try:
            adresse = ipaddress.ip_address(gegenstelle)
        except ValueError:
            return False
        return bool(adresse.is_private or adresse.is_loopback
                    or adresse.is_link_local)

    def _lokal_erlaubt(anfrage: Request) -> bool:
        """Darf sich hier jemand mit Benutzername und Passwort anmelden?

        Ohne Ausweisdienst: immer -- es gibt ja nichts anderes. Mit
        Ausweisdienst: nur ortsnah.
        """
        return not konf.oidc_aktiv or _ortsnah(anfrage)

    def _anbieter() -> oidc.Anbieter:
        return oidc.Anbieter(issuer=konf.oidc_issuer,
                             client_id=konf.oidc_client_id,
                             client_secret=konf.oidc_client_secret,
                             rueckweg=konf.oidc_rueckweg)

    # Angefangene Anmeldevorgaenge. Im Speicher, nicht auf der Platte: so ein
    # Vorgang lebt Minuten, und was Minuten lebt, hat auf einer Platte nichts
    # zu suchen -- schon gar nicht neben einer Wallet.
    anmeldevorgaenge: Dict[str, oidc.Vorgang] = {}

    def _vorgaenge_aufraeumen(jetzt: float) -> None:
        for state, v in list(anmeldevorgaenge.items()):
            if jetzt - v.begonnen > oidc.VORGANG_GUELTIG_SEKUNDEN:
                anmeldevorgaenge.pop(state, None)

    @api.get("/anmeldung/oidc/start")
    def oidc_start() -> Response:
        """Zum Ausweisdienst schicken."""
        if not konf.oidc_aktiv:
            raise HTTPException(404, {"meldung": "oidc_aus"})
        jetzt = time.time()
        _vorgaenge_aufraeumen(jetzt)
        # Ein Riegel gegen das Vollaufen: mehr offene Vorgaenge als das
        # braucht niemand, und jeder ist ein Stueck Speicher.
        if len(anmeldevorgaenge) > 50:
            anmeldevorgaenge.clear()
        try:
            adresse, vorgang = oidc.beginne(_anbieter(), jetzt)
        except oidc.OidcFehler as fehler:
            log.warning("Ausweisdienst nicht erreichbar: %s", fehler)
            raise HTTPException(502, {"meldung": "oidc_nicht_erreichbar"})
        anmeldevorgaenge[vorgang.state] = vorgang
        return RedirectResponse(adresse, status_code=303)

    # "callback" -- das einzige englische Wort in dieser sonst deutschen
    # Schnittstelle, und das mit Absicht.
    #
    # Aus dem Betrieb, 12.09.2026: "wir machen das allgemein gueltig! mit callback".
    #
    # Der Standard schreibt keinen Pfad vor: RFC 6749 kennt einen
    # "Redirection Endpoint" und den Parameter redirect_uri, mehr nicht.
    # "Callback" ist Umgangssprache -- aber genau die, die in jedem fremden
    # Admin-Fenster steht, in das diese Adresse eingetragen wird. Und dieses
    # Repo soll oeffentlich werden: wer von aussen die example.env liest,
    # erkennt "callback" auf Anhieb wieder.
    @api.get("/anmeldung/oidc/callback")
    def oidc_callback(anfrage: Request, code: str = "", state: str = "",
                      error: str = "") -> Response:
        """Zurueck vom Ausweisdienst.

        Endet IMMER mit einer Weiterleitung auf die Oberflaeche -- auch im
        Fehlerfall. Wer hier landet, hat gerade auf einen Anmeldeknopf
        gedrueckt; eine nackte JSON-Fehlermeldung im Browserfenster waere
        die unfreundlichste aller Antworten.
        """
        if not konf.oidc_aktiv:
            raise HTTPException(404, {"meldung": "oidc_aus"})
        jetzt = time.time()
        _vorgaenge_aufraeumen(jetzt)
        # Der Vorgang wird IMMER entnommen, auch wenn danach etwas schiefgeht:
        # ein state gilt genau einmal.
        vorgang = anmeldevorgaenge.pop(state, None)

        def zurueck_mit(grund: str) -> Response:
            log.warning("Anmeldung ueber den Ausweisdienst abgebrochen: %s",
                        grund)
            return RedirectResponse("/?anmeldung=" + grund, status_code=303)

        if error:
            # Der haeufigste Fall hier ist kein Fehler, sondern eine Absage:
            # der Nutzer gehoert keiner freigegebenen Gruppe an.
            return zurueck_mit("abgelehnt")
        if not code or vorgang is None:
            return zurueck_mit("abgelaufen")
        try:
            token = oidc.loese_ein(_anbieter(), code, vorgang, jetzt)
            nutz = oidc.pruefe_ausweis(_anbieter(), token.get("id_token") or "",
                                       vorgang, jetzt)
        except oidc.OidcFehler as fehler:
            log.warning("Ausweis nicht angenommen: %s", fehler)
            return zurueck_mit("ungueltig")

        log.info("Angemeldet ueber den Ausweisdienst: %s", oidc.name_aus(nutz))
        antwort = RedirectResponse("/", status_code=303)
        _setze_sitzung(antwort, konten.sitzung_eroeffnen())
        return antwort

    @api.post("/anmelden")
    def anmelden(daten: Zugangsdaten, antwort: Response,
                 anfrage: Request) -> Dict:
        # Mit eingerichtetem Ausweisdienst ist das lokale Konto die Nottuer --
        # und eine Nottuer, die auch von der Strasse aus aufgeht, ist keine.
        if not _lokal_erlaubt(anfrage):
            raise HTTPException(403, {"meldung": "nur_ueber_oidc"})
        try:
            token = konten.melde_an(daten.benutzer, daten.passwort)
        except PermissionError as f:
            raise HTTPException(401, {"meldung": str(f)})
        _setze_sitzung(antwort, token)
        return {"ok": True}

    @api.post("/abmelden")
    def abmelden(
        antwort: Response,
        satcortex_sitzung: Optional[str] = Cookie(default=None),
    ) -> Dict:
        konten.melde_ab(satcortex_sitzung)
        antwort.delete_cookie(SITZUNGS_KEKS, path="/")
        return {"ok": True}

    # -------------------------------------------------------------- Betrieb
    @app.get("/healthz")
    def healthz() -> Dict:
        return {"ok": True}

    # --------------------------------------------------------- Einrichtung
    @api.get("/einrichtung", dependencies=geschuetzt)
    def einrichtung_lesen() -> Dict:
        return zustand.laden().to_dict()

    @api.post("/einrichtung/weiter", dependencies=geschuetzt)
    def einrichtung_weiter(eingabe: Antwort) -> Dict:
        e = zustand.laden()
        if e.fertig:
            raise HTTPException(409, {"meldung": "einrichtung_abgeschlossen"})
        import json as _json
        if len(_json.dumps(eingabe.antworten)) > MAX_ANTWORT_ZEICHEN:
            raise HTTPException(413, {"meldung": "antwort_zu_gross"})
        e.weiter(eingabe.antworten)
        zustand.speichern(e)
        return e.to_dict()

    @api.post("/einrichtung/zurueck", dependencies=geschuetzt)
    def einrichtung_zurueck() -> Dict:
        e = zustand.laden()
        e.zurueck()
        zustand.speichern(e)
        return e.to_dict()

    @api.get("/speicher", dependencies=geschuetzt)
    def speicher_pruefen() -> Dict:
        return storage.pruefe(konf.bulk, konf.fast)

    @api.post("/leistung/vorschau", dependencies=geschuetzt)
    def leistung_vorschau(wahl: Leistungswahl) -> Dict:
        """Zeigt vor dem Bestaetigen, was die Wahl konkret bedeutet."""
        return profiles.zusammenfassung(
            wahl.speichergrenze_mb, wahl.upload_gb_pro_monat, wahl.verbindungen
        )

    @api.post("/einrichtung/abschliessen", dependencies=geschuetzt)
    def abschliessen(wahl: Leistungswahl) -> Dict:
        """Verzeichnisse anlegen, Konfiguration schreiben, Dienste wecken."""
        # Nur einmal. Sonst laesst sich ein laufender Knoten jederzeit
        # umkonfigurieren -- inklusive Austausch der RPC-Zugangsdaten.
        # Aenderungen im Betrieb bekommen spaeter einen eigenen, ausdruecklichen
        # Weg mit Bestaetigung.
        if zustand.laden().eingerichtet:
            raise HTTPException(409, {"meldung": "einrichtung_abgeschlossen"})
        pruefung = storage.pruefe(konf.bulk, konf.fast)
        if not pruefung["weiter_moeglich"]:
            # Auch Fehler tragen nur einen Schluessel -- sonst waere die
            # Meldung in der englischen Oberflaeche trotzdem deutsch.
            raise HTTPException(
                400,
                {
                    "meldung": "platz_reicht_nicht",
                    "bulk": pruefung["bulk"],
                    "fast": pruefung["fast"],
                },
            )

        angelegt = storage.lege_struktur_an(konf.bulk, konf.fast)

        # Was der Nutzer gewaehlt hat -- und was daraus folgt. Dieselbe
        # Ableitung wie in /knoten/netzwege, und aus demselben Grund: eine
        # Wahl, die nur gemerkt und nicht angewandt wird, ist eine Behauptung
        # ohne Folge. Wer "nur ueber Tor" waehlt und danach einen Knoten mit
        # offenem IPv4 bekommt, ist schlechter dran als ohne die Frage.
        roh = {
            "tor": wahl.tor_aktiv,
            "ipv4": wahl.netz_ipv4,
            "ipv6": wahl.netz_ipv6,
            "externe_adresse": wahl.externe_adresse,
            # Wer im Assistenten keine Adresse angibt, will sie auch nicht
            # angekuendigt haben -- der Schalter startet dann aus.
            "adresse_ankuendigen": bool(wahl.externe_adresse),
            "tor_pause_beim_abgleich": wahl.tor_pause_beim_abgleich,
            "sichtbarkeit": wahl.sichtbarkeit,
            "rpc_heimnetz": wahl.rpc_heimnetz,
        }
        wege = _nach_sichtbarkeit(roh)

        adressen = (dyndns.loese_auf(_adressliste(wege["externe_adresse"]))
                    if wege["adresse_ankuendigen"] else ())
        adressen = nodeconfig.adressen_fuer_netze(
            adressen, wege["ipv4"], wege["ipv6"])

        # Tor ZUERST: bitcoind will beim Start den Proxy erreichen, und die
        # eigene .onion legt Tor an -- sie soll schon in der ersten
        # bitcoind.conf stehen, nicht erst nach einem Neustart.
        onions = tor_schreiben(wege, ONION_FRIST_ANFRAGE_SEKUNDEN)

        knoten = nodeconfig.Knoteneinstellungen(
            speichergrenze_mb=wahl.speichergrenze_mb,
            upload_gb_pro_monat=wahl.upload_gb_pro_monat,
            verbindungen=wahl.verbindungen,
            tor_aktiv=wege["tor"],
            externe_adressen=tuple(adressen),
            im_erstsync=True,
            onion_adresse=onions.get("bitcoind", ""),
            rpc_netz=konf.compose_netz,
            rpc_heimnetz=wege["rpc_heimnetz"],
            zugang=nodeconfig.hole_oder_erzeuge_zugang(ablage),
        )
        conf = nodeconfig.baue_bitcoind(knoten)
        # Hier ist noch kein bitcoind befragbar -- es startet ja gleich erst.
        # _erlaubte_netze kommt damit zurecht: ohne Lage bleibt alles offen,
        # was der Nutzer gewaehlt hat, Tor eingeschlossen.
        erlaubt, grund = _erlaubte_netze(wege, None)
        conf = nodeconfig.setze_netze(conf, erlaubt, grund)
        ablage.schreibe("bitcoind", conf)
        # Die Wahl festhalten, damit sich die Konfiguration spaeter erneuern
        # laesst, ohne den ganzen Assistenten zu wiederholen. Gemerkt wird das
        # ROHE -- sonst loeschte ein Start in "nur ueber Tor" die Haekchen
        # dauerhaft, und beim Umschalten stuende der Knoten ohne IPv4 da.
        gemerkt = wahl.model_dump()
        gemerkt["adresse_ankuendigen"] = roh["adresse_ankuendigen"]
        zustand.merke_knotenwahl(gemerkt)

        # Kam Tor nicht rechtzeitig mit der Adresse, traegt der Waechter sie
        # nach -- mit einem Neustart mehr, aber ohne dass sie fehlt.
        ablage.gib_frei("bitcoind")

        # lnd bleibt hier unberuehrt. Es laeuft von Anfang an mit und wartet,
        # aber eingerichtet wird es erst, wenn die Kette steht -- mit einem
        # eigenen, gefuehrten Ablauf. Eine Wallet nebenbei anzulegen, deren
        # Seed niemand aufgeschrieben hat, waere keine Bequemlichkeit,
        # sondern eine Falle.

        e = zustand.laden()
        while not e.fertig:
            e.weiter()
        e.als_eingerichtet_markieren()
        zustand.speichern(e)

        return {
            "ok": True,
            "verzeichnisse_angelegt": angelegt,
            "dienste": ablage.alle(DIENSTE),
            "meldung": "abgeschlossen",
        }

    # ------------------------------------------------------------- Uebersicht
    # Die Kettenlage EINMAL je Takt holen, nicht drei Mal.
    #
    # Die Oberflaeche fragt alle zehn Sekunden nach, und sie fragt dabei
    # mehrere Endpunkte an: /status, /lightning, /beitrag. Zwei davon holten
    # sich die Kettenlage getrennt -- also zwei Mal getblockchaininfo,
    # getnetworkinfo, getnettotals und getpeerinfo, im Abstand von
    # Millisekunden, mit garantiert derselben Antwort.
    #
    # Waehrend des Erstabgleichs ist das nicht egal: getblockchaininfo
    # braucht cs_main, und genau die haelt Core, waehrend es den chainstate
    # wegschreibt. Jede ueberfluessige Anfrage stellt sich in dieselbe
    # Schlange.
    lagespeicher: Dict = {"stand": 0.0, "wert": None,
                          "grund": rpc.KNOTEN_UNGEFRAGT}
    # Nur fuer die allererste Messung. Die Endpunkte laufen in einem
    # Threadpool: ohne diese Sperre wuerden zwei gleichzeitig geoeffnete
    # Reiter beide dieselben fuenfzehn Sekunden warten.
    # RLock, nicht Lock: der Kaltstart nimmt sie und ruft dann
    # lage_auffrischen, das sie ebenfalls nimmt -- derselbe Faden, also darf
    # er das. Der Sammler nimmt sie fuer jede Runde; ein Aufruf, der genau
    # dann hereinkommt, wartet dadurch NICHT mit, sondern bekommt
    # "ungefragt" und beim naechsten Takt die Zahlen.
    erstmessung = threading.RLock()
    # Der Mempool gehoert zur selben Bereitstellung. Erst nach dem Abgleich
    # gibt es ihn ueberhaupt -- vorher nimmt Core keine Transaktionen an.
    mempoolspeicher: Dict = {"wert": None}

    def lage_mit_grund_gebuendelt() -> Tuple[Optional[Dict], str]:
        """Die zuletzt gemessene Kettenlage. Fragt NICHT selbst nach.

        Aus dem Betrieb, 04.09.2026: "der Aufruf der App dauert immer noch sehr
        lange im Browser, bis man mal die Daten sieht ... vielleicht liegt es
        daran, dass unsere App kein richtiges Backend und Frontend hat, wo die
        Daten zur Bereitstellung liegen?"

        Der Einwand trifft. Bis hierher holte JEDER Aufruf die Lage selbst,
        sobald der Zwischenspeicher aelter als drei Sekunden war -- und
        waehrend Core den chainstate schreibt, haelt es cs_main und die
        Abfrage wartet bis zu fuenfzehn Sekunden. Der Anzeigetakt betraegt
        zehn Sekunden, der Speicher war also bei praktisch jedem Aufruf kalt.
        Damit wartete der Mensch vor dem Bildschirm auf bitcoind.

        Jetzt sammelt ein Hintergrundfaden, und die Schnittstelle liest nur
        noch ab. Die Zahl ist dann ein paar Sekunden alt -- und ein paar
        Sekunden alt ist unendlich viel besser als fuenfzehn Sekunden nicht
        da. Genau das Muster steht auch in die eigene Web-Regeln:
        zwischengespeichertes sofort ausliefern, im Hintergrund erneuern.

        EINE Ausnahme: solange noch nie etwas gemessen wurde, wird einmal
        gewartet. Das ist der Kaltstart -- unmittelbar nach dem Hochfahren,
        einmal, nicht bei jedem Aufruf. Ein "wird geladen", das erst beim
        naechsten Anzeigetakt in zehn Sekunden verschwindet, waere hier
        schlechter als drei Sekunden warten.

        Kommt in genau diesem Augenblick ein zweiter Aufruf herein -- zwei
        Reiter, gleichzeitig geoeffnet --, wartet er NICHT mit. Er bekommt
        "ungefragt" und beim naechsten Takt die Zahlen.
        """
        if lagespeicher["stand"] == 0.0 and erstmessung.acquire(blocking=False):
            try:
                if lagespeicher["stand"] == 0.0:
                    lage_auffrischen()
            finally:
                erstmessung.release()
        return lagespeicher["wert"], lagespeicher["grund"]

    # ── Hintergrundarbeit, die jemand im Blick behaelt ────────────────────
    #
    # Am 10.09.2026 in der Pruefung aufgefallen, und der Befund gilt im
    # Betrieb genauso: das Einschalten der Nachrichten startete jedes Mal
    # einen Faden, den niemand mitzaehlte. Wer den Schalter fuenfmal
    # umlegt, hatte fuenf Feed-Abrufe GLEICHZEITIG ueber Tor laufen -- und
    # genau so ist am 30.08.2026 das Budget eines Ausgangsknotens
    # aufgebraucht worden. Dieselben Faeden ueberlebten ausserdem den
    # Dienst, der sie gestartet hatte.
    #
    # Also: ein Faden je Aufgabe. Laeuft schon einer, wird kein zweiter
    # geboren, und beim Herunterfahren wird eingeholt statt liegengelassen.
    hintergrund: Dict[str, threading.Thread] = {}

    # Das Haltesignal fuer die Dauerlaeufer. Ein Faden mit "while True" laesst
    # sich nicht einholen -- join wartet dann nur die Frist ab und gibt auf,
    # und der Faden laeuft weiter in einen Dienst hinein, den niemand mehr
    # betreut. Genau diese Fehlerklasse stand am 10.09.2026 schon einmal hier
    # (der Nachrichtenfaden eines beendeten Testfalls schrieb in die Attrappe
    # des naechsten); mit dem HTLC-Dauerlaeufer war sie zurueck. Am 12.09.2026
    # gemessen: 35 Faeden "htlc-strom" lebten am Ende eines Testlaufs noch.
    #
    # Wer wartet, wartet deshalb nicht mehr mit sleep, sondern auf dieses
    # Ereignis -- dann endet er sofort statt nach bis zu fuenf Minuten.
    beenden = threading.Event()

    def im_hintergrund(name: str, arbeit) -> bool:
        """Gibt zurueck, ob wirklich einer gestartet wurde."""
        if beenden.is_set():
            # Wird gerade heruntergefahren. Eine Anfrage, die noch in der
            # Leitung steckt, soll keinen Faden mehr hinterlassen, den
            # niemand mehr einholt.
            return False
        alt = hintergrund.get(name)
        if alt is not None and alt.is_alive():
            # Auf "debug", nicht "info": htlc_anstossen() laeuft im
            # Zwanzig-Sekunden-Takt mit, und der Normalfall ist, dass der
            # Dauerlaeufer schon laeuft. Auf INFO waren das 4.300 Zeilen am
            # Tag, die nichts melden ausser "alles wie erwartet".
            log.debug("%s laeuft schon -- kein zweiter Anlauf", name)
            return False

        def mit_auffangbuegel() -> None:
            # Ein Faden, der mit einer unbehandelten Ausnahme endet, stirbt
            # lautlos. Der Nutzer saehe nur einen leeren Reiter.
            try:
                arbeit()
            except Exception:                                # nosec B902
                log.exception("%s fehlgeschlagen", name)

        faden = threading.Thread(target=mit_auffangbuegel, name=name,
                                 daemon=True)
        hintergrund[name] = faden
        faden.start()
        return True

    def hintergrund_einholen(frist: float = 5.0) -> None:
        # Erst das Signal, dann warten. Ohne das Signal laeuft die Frist bei
        # jedem Dauerlaeufer garantiert ab.
        beenden.set()
        # Ein laufender Adress-Scan haelt bitcoind minutenlang beschaeftigt --
        # fuer niemanden, wenn die Anwendung gerade geht.
        if adresssuche.get("laeuft"):
            with contextlib.suppress(rpc.NichtErreichbar, rpc.RpcFehler):
                knotenverbindung().ruf("scantxoutset", "abort", zeitlimit=2.0)
        for name, faden in list(hintergrund.items()):
            if faden.is_alive():
                faden.join(timeout=frist)
                if faden.is_alive():
                    log.info("%s laeuft beim Beenden noch", name)

    def lage_auffrischen() -> None:
        """Eine Runde des Sammlers -- der EINZIGE Ort, der noch wartet.

        Laeuft im Hintergrundfaden. Dass er dabei fuenfzehn Sekunden haengen
        kann, ist hier folgenlos: es sitzt niemand davor.
        """
        # Die beiden Rohabfragen kommen aus demselben Takt-Zwischenspeicher
        # wie alles andere -- sonst holt die Kettenlage sie ein zweites Mal.
        with erstmessung:
            _lage_auffrischen_unter_sperre()

    def _lage_auffrischen_unter_sperre() -> None:
        peers, gesamt = rohdaten_auffrischen()
        wert, grund = rpc.lage_mit_grund(knotenverbindung(), peers, gesamt)
        lagespeicher.update(stand=time.monotonic(), wert=wert, grund=grund)
        # Lightning einrichten, sobald die Kette steht -- HIER und nicht im
        # Waechter. Der schlief nach jedem Neustart erst zehn Minuten, und
        # danach stand die Einrichtung auch noch hinter zwei Abbruechen, die
        # mit Lightning nichts zu tun haben (Tor-Vorlage, Adressnachfuehrung).
        # Aus dem Betrieb, 08.09.2026, nach dem Update auf 0.46.0: "das hat nicht
        # geklappt" -- LND stand weiter auf "wartet auf Einrichtung".
        #
        # Hier kostet es nichts: der Sammler hat die Lage ohnehin, und nach
        # dem ersten Mal ist es ein Blick auf einen Merker im Speicher.
        lightning_bereitstellen(wert)
        # Und danach: ist die Wallet zugefallen, weil diese Anwendung LND
        # neu gestartet hat? Dann macht sie sie selbst wieder auf -- aber
        # nur, wenn der Nutzer den Weg "merken" gewaehlt und einmal getippt
        # hat. Ohne gemerktes Passwort kostet der Aufruf einen Blick auf ein
        # leeres Feld.
        wallet_offenhalten()
        # Der Sammler weiss ohnehin alle fuenf Sekunden Bescheid. Bis zum
        # 05.09.2026 behielt er es fuer sich: die Anwendung schrieb nur bei
        # Ereignissen, und waehrend eines tagelangen Abgleichs tritt keines
        # ein. Der Betreiber sah deshalb im eigenen Protokoll nur die Startzeilen.
        betriebsprotokoll.melde(wert, grund)
        # Solange abgeglichen wird, gibt es keinen Mempool zu holen.
        if wert and not wert.get("im_erstsync"):
            mempoolspeicher["wert"] = rpc.mempoollage(knotenverbindung())
        kennzahlen_auffrischen(wert)

    def lage_holen() -> Optional[Dict]:
        """Nur die Lage -- fuer alle, die den Grund nicht brauchen."""
        return lage_mit_grund_gebuendelt()[0]

    def lage_ohne_warten() -> Optional[Dict]:
        """Die zuletzt geholte Lage -- OHNE neue Abfrage.

        Aus dem Betrieb, 03.09.2026: "das dauert halt ewig .. solange der Bitcoin
        Knoten wegschreibt kann die ganze App nix machen". Genau so war es,
        und es lag nicht an bitcoind.

        Waehrend Core den chainstate schreibt, haelt es cs_main; jede frische
        Abfrage wartet dann bis zu fuenfzehn Sekunden. Fuer die Uebersicht
        ist das richtig -- die Kettenlage IST ihr Inhalt. Fuer eine Seite,
        die Schalter aus einer Datei auf der Platte zeigt, ist es unsinnig:
        sie braucht die Lage nur als Beiwerk ("worueber ruft der Knoten
        gerade an") und haengt trotzdem an ihr.

        Hier wird deshalb nur genommen, was ohnehin schon dasteht. Ist es
        aelter als der Takt, macht das nichts: es ist die letzte bekannte
        Wahrheit, und die Alternative waere kein besserer Wert, sondern eine
        Wartezeit. Kam noch nie etwas an, ist es None -- die Oberflaeche
        behauptet dann nichts.
        """
        return lagespeicher["wert"]

    betriebsprotokoll = betriebslog.Betriebslog()

    rohspeicher: Dict = {"stand": 0.0, "peers": None, "gesamt": None}

    def rohdaten() -> Tuple[Optional[list], Optional[Dict]]:
        """getpeerinfo und getnettotals, hoechstens einmal je Takt.

        Am 02.09.2026 gezaehlt: ein Anzeigetakt der Uebersicht kostete zwoelf
        RPC-Aufrufe, davon ACHT doppelte -- getpeerinfo viermal, getnettotals
        dreimal, weil /status, /beitrag und /karte sie unabhaengig
        voneinander holten.

        Waehrend des Erstabgleichs stehen sie alle in derselben Schlange:
        Core bedient HTTP mit sechzehn Faeden, und die haengen an cs_main,
        sobald der chainstate geschrieben wird. Jeder doppelte Aufruf macht
        also das Zeitlimit der anderen wahrscheinlicher -- und genau diese
        Zeitlimits waren die Meldungen, die eine Woche lang im Protokoll
        standen.

        Dieselbe Frische wie die Kettenlage: was ein paar Sekunden alt ist,
        ist richtiger als ein Aufruf, der den Knoten weiter drueckt.
        """
        return rohspeicher["peers"], rohspeicher["gesamt"]

    def rohdaten_auffrischen() -> Tuple[Optional[list], Optional[Dict]]:
        """Die beiden Rohabfragen wirklich machen -- nur im Sammler."""
        k = knotenverbindung()
        peers = gesamt = None
        try:
            peers = k.ruf("getpeerinfo", zeitlimit=rpc.GEDULD_SEKUNDEN)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.debug("getpeerinfo nicht moeglich: %s", fehler)
        try:
            gesamt = k.ruf("getnettotals", zeitlimit=rpc.GEDULD_SEKUNDEN)
        except (rpc.NichtErreichbar, rpc.RpcFehler) as fehler:
            log.debug("getnettotals nicht moeglich: %s", fehler)
        # Ein Fehlschlag ueberschreibt NICHT den letzten guten Stand: sonst
        # waere ein einzelnes Zeitlimit gleichbedeutend mit "keine
        # Gegenstellen", und die Anzeige zeigte sechs Nullen.
        rohspeicher.update(stand=time.monotonic(),
                           peers=peers if peers is not None else rohspeicher["peers"],
                           gesamt=gesamt if gesamt is not None else rohspeicher["gesamt"])
        return rohspeicher["peers"], rohspeicher["gesamt"]

    def knotenverbindung() -> rpc.Knoten:
        """Zugang zu bitcoind. Die Zugangsdaten entstehen einmal und bleiben."""
        z = nodeconfig.hole_oder_erzeuge_zugang(ablage)
        return rpc.Knoten(
            host=konf.bitcoind_host,
            port=konf.bitcoind_rpc_port,
            benutzer=z.benutzer,
            passwort=z.passwort,
        )

    def lndverbindung() -> lnd.Knoten:
        """Zugang zu LND. Kein Passwort, kein Geheimnis in der Konfiguration:
        TLS gegen LNDs eigenes Zertifikat, Berechtigung ueber Macaroon."""
        return lnd.Knoten(host=konf.lnd_host, port=konf.lnd_rest_port)

    def netzwege_schreiben(roh: Dict) -> Dict:
        """Alle vier Wege in EINEM Schreibvorgang.

        Einer, nicht vier: jede Aenderung an der Konfiguration startet
        bitcoind neu, und ein Knoten, der zum Laden des chainstate Minuten
        braucht, soll das nicht viermal hintereinander tun.

        Was hier bewusst NICHT angefasst wird: Upload-Budget, Verbindungszahl
        und die RPC-Zeile. Die Verbindungszahl zu druecken erleichtert eine
        Eclipse-Attacke erheblich, und ohne die alte rpcauth-Zeile spraeche
        die Anwendung nicht mehr mit ihrem eigenen Knoten.
        """
        e = zustand.laden()
        if not e.eingerichtet:
            raise HTTPException(409, {"meldung": "noch_nicht_eingerichtet"})
        # Dieselbe Ableitung wie beim Lesen, und zwar HIER -- der eine
        # Trichter, durch den jede Aenderung muss. Stuende sie nur im
        # Lesepfad, koennte man ueber die Schnittstelle "nur ueber Tor"
        # zusammen mit eingeschaltetem IPv4 ablegen, und die Wahl waere eine
        # Behauptung ohne Folge.
        roh.setdefault("sichtbarkeit", _sichtbarkeit_von(e.knotenwahl or {}))
        # "wege" ist das Abgeleitete und geht in die Konfiguration. Gemerkt
        # wird weiter unten "roh" -- die Wahl des Nutzers. Ohne diese
        # Trennung loeschte ein Ausflug nach "nur ueber Tor" die Haekchen
        # dauerhaft, und beim Zurueckschalten stuende der Knoten ohne IPv4 da.
        wege = _nach_sichtbarkeit(roh)
        vorhanden = ablage.lies("bitcoind")
        if not vorhanden:
            raise HTTPException(409, {"meldung": "konfiguration_fehlt"})

        if not (wege["tor"] or wege["ipv4"] or wege["ipv6"]):
            # Die einzige Grenze, und sie liegt nicht zwischen den Schaltern:
            # ohne ein einziges Netz koennte der Knoten weder jemanden
            # erreichen noch erreicht werden.
            raise HTTPException(400, {"meldung": "kein_weg_ins_netz"})

        lage, _ = lage_mit_grund_gebuendelt()
        erlaubt, grund = _erlaubte_netze(
            wege, lage, nodeconfig.lies_netze(vorhanden))

        # Tor zuerst -- die torrc folgt der Sichtbarkeit, und die .onion, die
        # bitcoind und LND gleich ankuendigen, legt Tor an.
        onions = tor_schreiben(wege, ONION_FRIST_ANFRAGE_SEKUNDEN)

        neu = nodeconfig.setze_rpc_freigabe(
            vorhanden, wege.get("rpc_heimnetz", ""), konf.compose_netz)
        neu = nodeconfig.setze_tor(
            neu, wege["tor"], _bitcoind_onion(wege, vorhanden, onions))
        # In die Konfiguration geht die aufgeloeste IP, nicht der Name: Core
        # loest -externalip nur beim Start auf, und ein Name wuerde nach der
        # naechsten Zwangstrennung auf eine fremde Adresse zeigen.
        aufgeloest = (dyndns.loese_auf(_adressliste(wege["externe_adresse"]))
                      if wege["adresse_ankuendigen"] else [])
        # Eine IPv6-Adresse anzukuendigen, waehrend IPv6 aus ist, waere eine
        # Einladung, die niemand annehmen kann.
        aufgeloest = nodeconfig.adressen_fuer_netze(
            aufgeloest, wege["ipv4"], wege["ipv6"])
        # Und ein DNS-Aussetzer waehrend des Speicherns darf die angekuendigte
        # Adresse nicht mitnehmen. Der Waechter war dagegen laengst geschuetzt
        # ("if not soll: return False"); dieser Weg hier war es nicht -- wer
        # zufaellig in einer Aussetzer-Sekunde auf Speichern drueckte, stand
        # danach ohne angekuendigte Adresse da, ohne dass es irgendwo stand.
        adressen = list(nodeconfig.adressen_halten(
            vorhanden, aufgeloest, wege["adresse_ankuendigen"]))
        neu = nodeconfig.setze_adressen(neu, adressen)
        if erlaubt:
            neu = nodeconfig.setze_netze(neu, erlaubt, grund)

        geaendert = neu != vorhanden
        if geaendert:
            ablage.schreibe("bitcoind", neu)
            ablage.gib_frei("bitcoind")

        wahl_neu = dict(e.knotenwahl or {})
        wahl_neu.update(
            tor_aktiv=roh["tor"],
            netz_ipv4=roh["ipv4"],
            netz_ipv6=roh["ipv6"],
            externe_adresse=roh["externe_adresse"],
            adresse_ankuendigen=roh["adresse_ankuendigen"],
            tor_pause_beim_abgleich=roh["tor_pause_beim_abgleich"],
            sichtbarkeit=roh["sichtbarkeit"],
            rpc_heimnetz=roh.get("rpc_heimnetz", ""),
        )
        zustand.merke_knotenwahl(wahl_neu)
        # UND Lightning. Vorher endete jede Einstellung hier bei bitcoind;
        # LND behielt, was beim allerersten Schreiben dastand.
        lnd_geaendert = lightning_conf_nachziehen(wege, adressen)
        # Was tatsaechlich abgelegt wurde -- nachlesbar unter "Protokolle".
        # Ohne diese Zeile blieb bei "meine Einstellung kommt nicht an" nur
        # die Wahl zwischen zwei Vermutungen: der Knopf wurde nicht gedrueckt,
        # oder das Ablegen ging schief. Jetzt steht es da.
        log.info("Netzwege abgelegt: tor=%s pause=%s ipv4=%s ipv6=%s "
                 "ankuendigen=%s adresse=%r sichtbar=%s -> ruft an ueber %s%s",
                 wege["tor"], wege["tor_pause_beim_abgleich"], wege["ipv4"],
                 wege["ipv6"], wege["adresse_ankuendigen"],
                 wege["externe_adresse"], wege["sichtbarkeit"],
                 ", ".join(erlaubt) or "nichts",
                 "; bitcoind startet neu" if geaendert else "")
        # Die geaenderte Pruefsumme laesst der Waechter im Startskript den
        # Dienst sauber beenden; restart: unless-stopped startet ihn neu.
        return {"ok": True, **wege, "angekuendigt": adressen,
                "ruft_an": erlaubt, "neustart_noetig": geaendert,
                # Getrennt ausgewiesen: ein LND-Neustart sperrt bei
                # abgeschaltetem Auto-Entsperren die Wallet zu. Das darf die
                # Oberflaeche sagen koennen, BEVOR jemand den Knopf drueckt.
                "lightning_neustart": lnd_geaendert}

    @api.get("/knoten/netzwege", dependencies=geschuetzt)
    def netzwege_lesen() -> Dict:
        """Wie der Knoten gerade am Netz teilnimmt.

        Neben den Schaltern steht, was daraus GERADE folgt: waehrend des
        Erstabgleichs ruft der Knoten ueber Tor niemanden an, obwohl der
        Schalter auf an steht. Die Oberflaeche soll das sagen koennen, statt
        einen Schalter zu zeigen, der etwas anderes behauptet als die
        Wirklichkeit.
        """
        e = zustand.laden()
        wege = _wege(e.knotenwahl)
        # Ohne Warten: die Schalter stehen in einer Datei, nicht im Knoten.
        lage = lage_ohne_warten()
        erlaubt, _grund = _erlaubte_netze(
            wege, lage, nodeconfig.lies_netze(ablage.lies("bitcoind") or ""))
        # Wie lange der Name schon nicht mehr aufloest. None heisst: noch nie
        # nachgesehen -- das ist etwas anderes als "geht nicht".
        seit = None
        if adressstand["fehler"] and adressstand["versucht"]:
            seit = int(time.time() - (adressstand["zuletzt_ok"]
                                      or adressstand["versucht"]))
        return {
            **wege,
            "eingerichtet": e.eingerichtet,
            "ruft_an": erlaubt,
            "name_haengt_seit_s": seit,
            "tor_pausiert": bool(wege["tor"] and "onion" not in erlaubt),
            # None heisst "gerade nicht feststellbar" -- und das ist etwas
            # anderes als "nein". Als false gemeldet, behauptete die
            # Oberflaeche bei jedem ausgefallenen getblockchaininfo "die
            # Kette steht", mitten im Erstabgleich.
            "im_erstsync": None if lage is None else bool(lage.get("im_erstsync")),
        }

    @api.post("/knoten/netzwege", dependencies=geschuetzt)
    def netzwege_setzen(wahl: Netzwegewahl) -> Dict:
        return netzwege_schreiben({
            "tor": wahl.tor,
            "ipv4": wahl.ipv4,
            "ipv6": wahl.ipv6,
            "externe_adresse": wahl.externe_adresse,
            "adresse_ankuendigen": wahl.adresse_ankuendigen,
            "tor_pause_beim_abgleich": wahl.tor_pause_beim_abgleich,
            "sichtbarkeit": wahl.sichtbarkeit,
            "rpc_heimnetz": wahl.rpc_heimnetz,
        })

    @api.get("/knoten/rpc-zugang", dependencies=geschuetzt)
    def rpc_zugang_lesen() -> Dict:
        """Was eine Wallet-Software braucht, um diesen Knoten zu benutzen.

        Ja, hier steht ein Passwort im Klartext auf dem Bildschirm. Das ist
        eine bewusste Entscheidung und keine Nachlaessigkeit:

        - Ohne diese Angaben laesst sich Sparrow gar nicht einrichten; sie
          von Hand aus einer Datei auf dem NAS zu fischen waere der einzige
          andere Weg.
        - Die Seite steht ohnehin hinter der Anmeldung, und wer die hat,
          kaeme auch sonst an die Datei.
        - Und der Zugang bewegt kein Geld: Sparrow legt laut eigener
          Beschreibung KEINE Wallet im Knoten an ("Sparrow does not use
          Bitcoin Core's internal wallet"), also gibt es dort auch keine
          Schluessel, die jemand ausgeben koennte.

        Was er erlaubt, steht in der Oberflaeche daneben: die Kette befragen
        und Transaktionen einreichen.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}
        z = nodeconfig.hole_oder_erzeuge_zugang(ablage)
        return {
            "eingerichtet": True,
            "benutzer": z.benutzer,
            "passwort": z.passwort,
            "port": konf.bitcoind_rpc_port,
            "heimnetz": _wege(zustand.laden().knotenwahl)["rpc_heimnetz"],
        }

    @api.post("/knoten/adresse", dependencies=geschuetzt)
    def adresse_setzen(wahl: Adresswahl) -> Dict:
        """Nur die eigene Adresse nachtragen, ohne den Assistenten zu wiederholen.

        Der schmale Weg von frueher, jetzt auf demselben Unterbau wie die
        Netzwege: er aendert genau die Adresse und laesst die drei Netze so,
        wie sie eingestellt sind.
        """
        wege = _wege(zustand.laden().knotenwahl)
        wege["externe_adresse"] = wahl.externe_adresse
        # "Adresse ankuendigen" IST die Betriebsart, seit die Wahl fuer beide
        # Dienste gilt. Der schmale Weg von frueher bleibt benutzbar -- er
        # verschiebt jetzt die Wahl, statt neben ihr her einen zweiten
        # Schalter zu fuehren, der ihr widerspricht.
        #
        # Nur wenn es sich WIDERSPRICHT: wer in "nur ueber Tor" steht und die
        # Ankuendigung abschaltet, will nicht nach "still" geschoben werden.
        if wahl.ankuendigen and wege["sichtbarkeit"] != "hybrid":
            wege["sichtbarkeit"] = "hybrid"
        elif not wahl.ankuendigen and wege["sichtbarkeit"] == "hybrid":
            wege["sichtbarkeit"] = "still"
        wege["adresse_ankuendigen"] = wahl.ankuendigen
        antwort = netzwege_schreiben(wege)
        return {"ok": True, "adresse": wahl.externe_adresse,
                "ankuendigen": wahl.ankuendigen,
                "neustart_noetig": antwort["neustart_noetig"]}

    @api.get("/beitrag", dependencies=geschuetzt)
    def beitrag_lesen() -> Dict:
        """Was dieser Knoten dem Netz tatsaechlich gegeben hat.

        "Gesendete Bytes" allein sagt wenig -- da steckt Handschlag, Ping und
        Adressgeplauder mit drin. Hier steht, wieviel davon BLOCKDATEN waren.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}
        peers, gesamt = rohdaten()
        if peers is None:
            # Der Sammler war noch nicht durch. sammle() wuerde die Abfrage
            # sonst selbst machen -- und genau das soll kein Aufruf mehr tun.
            d = beitrag.ohne_auskunft()
        else:
            d = beitrag.sammle(knotenverbindung(), peers, gesamt)
        d["eingerichtet"] = True
        return d

    # getblocktemplate baut jedes Mal wirklich eine Vorlage. Alle paar
    # Sekunden danach zu fragen waere Arbeit fuer nichts -- ein Block kommt
    # im Schnitt alle zehn Minuten.
    kennzahlen_stand: Dict[str, Any] = {"zeit": 0.0, "wert": {}}
    KENNZAHLEN_FRISCHE = 20.0

    # Die Gebuehrenlage der letzten Woche -- der Massstab, an dem "teuer" oder
    # "guenstig" ueberhaupt erst eine Bedeutung bekommt.
    #
    # Eigener, viel langsamerer Takt als alles andere hier: es sind rund 144
    # Leseaufrufe auf die Platte, auf der die Bloecke liegen (bei uns die
    # HDD). Eine Woche verschiebt sich in einer Stunde nicht messbar, also
    # wird hoechstens stuendlich neu gerechnet -- und in einem EIGENEN Faden,
    # damit der Sammler nicht darauf wartet.
    verlauf_stand: Dict[str, Any] = {"hoehe": 0, "wert": None}
    VERLAUF_FRISCHE_BLOECKE = 6

    def verlauf_anstossen(hoehe: int) -> None:
        """Die Wochenverteilung nachrechnen lassen, wenn sie alt genug ist.

        Die Hoehe wird auch dann fortgeschrieben, wenn nichts herauskam --
        sonst liefe waehrend des Abgleichs alle zwanzig Sekunden ein neuer
        Anlauf gegen einen Knoten, der ohnehin am Anschlag arbeitet.
        """
        if hoehe <= 0 or hoehe - verlauf_stand["hoehe"] < VERLAUF_FRISCHE_BLOECKE:
            return

        def rechnen() -> None:
            wert = kennzahlen.gebuehrenverlauf(knotenverbindung(), hoehe)
            verlauf_stand["hoehe"] = hoehe
            if wert is not None:
                verlauf_stand["wert"] = wert
                log.info("Gebuehrenlage der letzten Woche: Mitte %s sat/vB "
                         "(%s Bloecke).", wert["mitte"], wert["bloecke"])

        im_hintergrund("gebuehrenverlauf", rechnen)

    @api.get("/kennzahlen", dependencies=geschuetzt)
    def kennzahlen_lesen() -> Dict:
        """Was unter der Weltkarte steht: naechster Block, Gebuehren, Schwierigkeit.

        Der naechste Block ist keine Schaetzung von aussen, sondern die
        Auswahl DIESES Knotens aus SEINEM Mempool -- genau die Sorte
        Auskunft, fuer die man einen eigenen Knoten betreibt. Waehrend des
        Abgleichs gibt es sie nicht; Core lehnt die Vorlage dann ab, und das
        steht dann auch so in der Antwort.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}
        # Nur ablesen. Am 04.09.2026 im Pruefstand gemessen: dieser Aufruf
        # brauchte SIEBENUNDZWANZIG Sekunden, waehrend alle anderen schon
        # unter zwei Millisekunden lagen -- er holte die Kettenlage ein
        # zweites Mal (obwohl sie im Sammler lag) und dazu getblocktemplate,
        # das jedes Mal wirklich eine Blockvorlage baut.
        return kennzahlen_stand["wert"] or {"eingerichtet": True}

    @api.get("/kanalrechner", dependencies=geschuetzt)
    def kanalrechner() -> Dict:
        """Was ein Kanal kostet -- und was dafuer einzuzahlen ist.

        Aus dem Betrieb, 11.09.2026: "wir haben ja schon ein rechner reiter kann das
        da nicht mit rein?" Doch, und dort gehoert es hin: im Rechner steht
        der Kurs, also kann dort neben den Satoshi auch der Betrag in Euro
        stehen. Genau der ist die Zahl, in der man plant.

        Ein eigener, kleiner Endpunkt statt der grossen Lightning-Antwort:
        die zieht getinfo, Kanalliste, Graph und Weiterleitungen mit. Fuer
        zwei Zahlen waere das vier Aufrufe zuviel.

        Die Gebuehren kommen aus bitcoind und stehen auch ohne Lightning zur
        Verfuegung -- genau dann plant man ja seinen ersten Kanal. Nur die
        Anker-Ruecklage braucht einen laufenden LND; ohne ihn fehlt sie,
        statt als Null zu erscheinen.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}
        ruecklage = None
        try:
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] == "bereit":
                ruecklage = lnd.ruecklage(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.debug("Ruecklage fuer den Rechner nicht zu haben: %s", fehler)
        return {
            "eingerichtet": True,
            "kanalkosten": kennzahlen.kanalkosten(
                (kennzahlen_stand["wert"] or {}).get("gebuehren") or {},
                verlauf=verlauf_stand["wert"], ruecklage_sat=ruecklage),
        }

    def kennzahlen_auffrischen(lage: Optional[Dict]) -> None:
        """Die Kennzahlen unter der Weltkarte -- im Sammler, nicht im Aufruf.

        Eigener, langsamerer Takt: getblocktemplate baut jedes Mal wirklich
        eine Vorlage, und ein Block kommt im Schnitt alle zehn Minuten.
        """
        jetzt = time.time()
        if jetzt - kennzahlen_stand["zeit"] < KENNZAHLEN_FRISCHE:
            return
        if not zustand.laden().eingerichtet:
            return
        knoten = knotenverbindung()
        # Die Lage kommt aus derselben Runde -- kein zweiter Aufruf.
        lage = lage or {}
        im_erstsync = bool(lage.get("im_erstsync", True))
        # Waehrend des Abgleichs geben beide nichts her: Core lehnt die
        # Blockvorlage ab ("Bitcoin is in initial sync"), und ohne Mempool
        # gibt es keine Gebuehrenschaetzung. naechster_block faengt das ab
        # und liefert None -- dasselbe None bekommt man ohne den Aufruf.
        # Sie tagelang alle zwanzig Sekunden trotzdem zu stellen, ist Last
        # fuer nichts, und zwar genau an dem Knoten, der ohnehin am Anschlag
        # laeuft.
        kennzahlen_stand.update(zeit=jetzt, wert={
            "eingerichtet": True,
            "im_erstsync": im_erstsync,
            "hoehe": lage.get("hoehe", 0),
            "blockzeit": lage.get("blockzeit", 0),
            "naechster_block": None if im_erstsync
                               else kennzahlen.naechster_block(knoten),
            "gebuehren": None if im_erstsync else kennzahlen.gebuehren(knoten),
            "schwierigkeit": kennzahlen.schwierigkeit(knoten, lage),
        })
        if not im_erstsync:
            verlauf_anstossen(int(lage.get("hoehe") or 0))
        # Der HTLC-Dauerlaeufer. Kostet nichts, wenn er schon laeuft.
        htlc_anstossen()

    @api.get("/logs", dependencies=geschuetzt)
    def logs_quellen() -> Dict:
        """Welche Protokolle es gibt und ob schon etwas darin steht.

        Ohne Docker-Socket -- der waere auf einem Geraet mit einer Wallet
        gleichbedeutend mit root. Gelesen wird, was die Dienste ohnehin in das
        eingehaengte Datenverzeichnis schreiben.
        """
        return {"quellen": logs.quellen(konf.fast)}

    @api.get("/logs/{quelle}", dependencies=geschuetzt)
    def logs_lesen(quelle: str, zeilen: int = logs.ZEILEN_STANDARD) -> Dict:
        """Das Ende eines Protokolls.

        `quelle` wird gegen einen festen Satz Namen geprueft, bevor daraus ein
        Pfad wird. Sonst waere dieser Endpunkt ein Dateibetrachter fuer alles,
        was der Container sieht.
        """
        try:
            return logs.lies(quelle, konf.fast, zeilen)
        except ValueError:
            raise HTTPException(404, {"meldung": "protokoll_unbekannt"})

    @api.get("/auswertung", dependencies=geschuetzt)
    def auswertung_lesen() -> Dict:
        """Was der Knoten seit der Inbetriebnahme gesehen hat.

        Die Geschichte faengt hier an und nicht bei Block 0 -- einen
        First-Seen-Zeitstempel kann man nicht nachtraeglich erfinden. Deshalb
        steht das Datum der ersten Messung mit in der Antwort: ohne es sagt
        "1.240 Transaktionen" nichts.
        """
        strom = getattr(app.state, "zulauf", None)
        antwort = auswertung.eckdaten()
        antwort.update(
            verfuegbar=auswertung.verfuegbar,
            grund=getattr(auswertung, "grund", ""),
            laeuft=bool(strom and strom.laeuft_mit),
            gesehen=strom.gesehen if strom else 0,
            bloecke_liste=auswertung.letzte_bloecke(12),
            diagramm=auswertung.letztes_diagramm(),
            diagramm_zeit_s=auswertung.diagramm_zeit(),
            mempool=auswertung.mempool_verlauf(int(time.time()) - 6 * 3600),
        )
        return antwort

    # ── Die Kacheln: jede wartende Transaktion als Flaeche ─────────────
    #
    # Alles davon kommt aus DIESEM Knoten. getrawmempool liefert, was in
    # seinem Mempool liegt, die Zeitstempel stehen in unserer eigenen Ablage.
    # Nichts wird von aussen geholt -- Aus dem Betrieb, 08.09.2026: "jede info die
    # wir brauchen kommt aus dem netzwerk und nicht von extern".
    #
    # ZWEI EHRLICHE EINSCHRAENKUNGEN, die in die Ansicht gehoeren:
    #
    # 1. Die Reihenfolge ist eine NAEHERUNG. Sortiert wird nach der
    #    Vorfahren-Gebuehrenrate -- danach waehlt ein Miner grob aus, und
    #    genau dafuer liefert Core ancestorsize und fees.ancestor. Die
    #    endgueltige Wahrheit ist Cores Cluster-Reihenfolge; die steht im
    #    Feerate-Diagramm, nicht hier.
    # 2. Der Aufruf ist der groesste, den diese Anwendung kennt. Bei des Betreibers
    #    ruhigem Mempool sind es ein paar Megabyte, bei vollem Mempool
    #    deutlich mehr. Deshalb NUR auf Anforderung, mit Zwischenspeicher --
    #    und nicht im Takt des Waechters.
    kachelspeicher: Dict = {"wert": None, "zeit": 0.0}

    @api.get("/auswertung/mempool/kacheln", dependencies=geschuetzt)
    def mempool_kacheln() -> Dict:
        """Jede wartende Transaktion als Flaeche, gruppiert nach Block."""
        if (kachelspeicher["wert"] is not None
                and time.monotonic() - kachelspeicher["zeit"] < KACHEL_FRIST_S):
            return kachelspeicher["wert"]

        # IM STROM, nicht am Stueck. Der Befund vom 21.09.2026 aus dem
        # Betrieb: "wenn der mempool voll ist oder fast voll ist kann ich
        # keine kacheln mehr holen".
        #
        # Vorher stand hier ruf("getrawmempool", True) -- die ganze Antwort
        # auf einmal, und zwar dreifach gleichzeitig: als Bytes, als String
        # und als Objekte. Nachgemessen mit Cores eigener Feldliste kostete
        # das bei 150.000 Transaktionen 397 MB, bei einem Containerlimit von
        # 400M. Der Container starb am OOM-Killer und startete neu -- es
        # fehlten also nicht die Kacheln, es fehlte die ganze Oberflaeche.
        #
        # Der Strom haelt die Antwort nie: gemessen 0,20 MB, gleich ob 500
        # oder 32.000 Transaktionen darin stehen.
        try:
            eintraege = mempoolstrom.auswerten(mempoolstrom.begrenzt(
                knotenverbindung().brocken("getrawmempool", True,
                                           zeitlimit=45.0)))
        except (rpc.NichtErreichbar, rpc.RpcFehler,
                mempoolstrom.MempoolAbgerissen) as fehler:
            log.info("Mempool nicht abrufbar: %s", fehler)
            raise HTTPException(503, {"meldung": "mempool_nicht_abrufbar"})
        except mempoolstrom.MempoolZuGross as fehler:
            # Keine stille Kuerzung: eine Kachelansicht aus einem halben
            # Mempool saehe richtig aus und waere falsch.
            log.warning("Mempool unplausibel gross: %s", fehler)
            raise HTTPException(503, {"meldung": "mempool_zu_gross"})

        kacheln: List[Dict] = []
        reste: Dict[int, Dict] = {}
        bloecke: List[Dict] = []
        laufend = 0
        for _, txid, vsize, satvb in eintraege:
            n = int(laufend // BLOCK_VBYTE)
            while len(bloecke) <= n:
                bloecke.append({"n": len(bloecke), "anzahl": 0, "vsize": 0,
                                "sat": 0.0, "tiefste": None, "hoechste": None})
            b = bloecke[n]
            b["anzahl"] += 1
            b["vsize"] += vsize
            b["sat"] += satvb * vsize
            b["tiefste"] = satvb if b["tiefste"] is None else min(b["tiefste"], satvb)
            b["hoechste"] = satvb if b["hoechste"] is None else max(b["hoechste"], satvb)
            if n < KACHEL_BLOECKE:
                if b["anzahl"] <= KACHEL_JE_BLOCK:
                    kacheln.append({"txid": txid, "vsize": vsize,
                                    "satvb": round(satvb, 3), "block": n})
                else:
                    # Alles darueber wird zu EINER Restkachel je Block
                    # zusammengefasst. Sonst fehlte der Spalte Flaeche, und
                    # der Treemap zeichnete einen halb leeren Block --
                    # genau das hat Aus dem Betrieb, 08.09.2026 gesehen: bei
                    # 31.716 wartenden Transaktionen war die gemeinsame
                    # Obergrenze nach sechs Spalten aufgebraucht, und die
                    # letzten standen als leere Rahmen da.
                    rest = reste.setdefault(n, {"txid": "", "vsize": 0,
                                                "satvb": satvb, "block": n,
                                                "anzahl": 0, "rest": True})
                    rest["vsize"] += vsize
                    rest["anzahl"] += 1
                    rest["satvb"] = round(satvb, 3)   # die unterste im Block
            laufend += vsize

        for b in bloecke:
            b["sat"] = int(b["sat"])
            b["tiefste"] = round(b["tiefste"], 3) if b["tiefste"] is not None else None
            b["hoechste"] = round(b["hoechste"], 3) if b["hoechste"] is not None else None

        # Und jetzt das, was kein Explorer dazulegen kann: wann DIESER Knoten
        # sie zuerst gesehen hat. Aus der eigenen Ablage, in einer Abfrage.
        zeiten = auswertung.zuerst_gesehen([k["txid"] for k in kacheln])
        for k in kacheln:
            k["zuerst_ms"] = zeiten.get(k["txid"])

        # Die Restkacheln ans Ende ihres Blocks -- sie sind die kleinsten und
        # liegen im Treemap damit hinten.
        for n in sorted(reste):
            r = dict(reste[n])
            r["zuerst_ms"] = None
            kacheln.append(r)

        antwort = {
            "stand_s": int(time.time()),
            "gesamt": len(eintraege),
            "vsize_gesamt": laufend,
            "bloecke": bloecke[:KACHEL_BLOECKE],
            "kacheln": kacheln,
            "gekuerzt": bool(reste),
            "grenze": KACHEL_JE_BLOCK,
        }
        kachelspeicher.update(wert=antwort, zeit=time.monotonic())
        return antwort

    def block_aus_der_kette(hoehe: int) -> Optional[Dict]:
        """Einen Block holen, den unsere Aufzeichnung nicht kennt.

        Die Aufzeichnung faengt mit der Inbetriebnahme an -- alles davor ist
        ihr fremd. Die KETTE kennt es trotzdem, vollstaendig und un-pruned,
        und das ist der halbe Sinn eines Archiv-Knotens. Also fragen wir sie.

        Der Anlass, 08.09.2026: der Betreiber wollte Satoshis Schlagzeile sehen.
        Die Blockansicht wirbt in ihrem eigenen Erklaertext damit -- "im
        allerersten Block steht dort die Schlagzeile, mit der alles anfing"
        -- und kannte doch nur die zwoelf letzten. Ein Versprechen, das die
        Oberflaeche selbst gibt und nicht einloest.

        Was hier fehlt und fehlen MUSS: "vorher bei dir" und die
        Verweildauer. Einen First-Seen-Zeitstempel kann man nicht
        nachtraeglich erfinden, und wir waren 2009 nicht dabei.
        """
        knoten = knotenverbindung()
        try:
            blockhash = knoten.ruf("getblockhash", int(hoehe), zeitlimit=10.0)
            if not isinstance(blockhash, str):
                return None
            roh = knoten.ruf("getblock", blockhash, 1, zeitlimit=20.0)
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            return None
        if not isinstance(roh, dict):
            return None

        coinbase_hex = ((roh.get("coinbase_tx") or {}).get("coinbase") or "")
        stuecke = [x for x in coinbase.botschaften(coinbase_hex) if len(x) >= 4]
        gebuehren = None
        try:
            werte = knoten.ruf("getblockstats", blockhash, ["totalfee"],
                               zeitlimit=20.0)
            if isinstance(werte, dict):
                gebuehren = werte.get("totalfee")
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            pass
        return {
            "hoehe": roh.get("height", hoehe),
            "hash": blockhash,
            "blockzeit": roh.get("time"),
            "empfangen_ms": None,
            "gewicht": roh.get("weight"),
            "txzahl": roh.get("nTx"),
            "gebuehren_sat": gebuehren,
            "pool": poolliste.erkenne(coinbase_hex, []) if poolliste else None,
            "botschaft": " ".join(stuecke)[:200] or None,
            # Ausdruecklich None statt null-Zahlen: wir waren nicht dabei,
            # und eine Null saehe aus wie eine Messung.
            "bekannte_tx": None,
            "verweildauer_ms": None,
        }

    @api.get("/auswertung/block/{hoehe}", dependencies=geschuetzt)
    def ein_block(hoehe: int) -> Dict:
        """Was in diesem Block steht -- aus der Sicht DIESES Knotens.

        Der Unterschied zu jedem Explorer der Welt steht in zwei Spalten:
        wann dieser Knoten die Transaktion zuerst sah, und wie lange sie
        danach bei ihm wartete. Beides kann man nicht nachtraeglich
        herstellen; wer es nicht mitgeschrieben hat, hat es nicht.

        Bewusst NICHT die vollstaendige Transaktionsliste des Blocks: die
        stuende auch anderswo, kostet einen grossen RPC-Aufruf und waere die
        langweilige Haelfte. Hier stehen die, die durch unseren Mempool kamen
        -- die Blockzeile nennt beide Zahlen nebeneinander.
        """
        if hoehe < 0:
            raise HTTPException(400, {"meldung": "block_unbekannt"})
        block = auswertung.ein_block(hoehe)
        aus_kette = False
        if not block:
            # Nicht in unserer Aufzeichnung -- dann eben aus der Kette. Ein
            # Archiv-Knoten hat sie vollstaendig; danach zu fragen ist der
            # halbe Sinn der Sache.
            block = block_aus_der_kette(hoehe)
            aus_kette = True
        if not block:
            raise HTTPException(404, {"meldung": "block_unbekannt"})
        return {"block": block, "aus_kette": aus_kette,
                "transaktionen": ([] if aus_kette else
                                  auswertung.tx_eines_blocks(hoehe,
                                                             BLOCK_TX_GRENZE)),
                "grenze": BLOCK_TX_GRENZE}

    @api.get("/auswertung/tx/{txid}", dependencies=geschuetzt)
    def eine_transaktion(txid: str) -> Dict:
        """Was WIR ueber diese Transaktion wissen.

        Bewusst zuerst aus der eigenen Ablage: der First-Seen-Zeitstempel ist
        das, was dieser Knoten exklusiv hat. Was danach kommt -- Gebuehr,
        Groesse, Bestaetigungen -- weiss auch jeder Explorer, und das holen
        wir uns erst auf Nachfrage beim eigenen Knoten.
        """
        sauber = (txid or "").strip().lower()
        if len(sauber) != 64 or not all(c in "0123456789abcdef" for c in sauber):
            raise HTTPException(400, {"meldung": "keine_txid"})

        eigen = auswertung.eine_tx(sauber)
        knoten: Optional[Dict] = None
        try:
            roh = knotenverbindung().ruf("getrawtransaction", sauber, 1)
            if isinstance(roh, dict):
                knoten = {
                    "groesse": roh.get("vsize"),
                    "gewicht": roh.get("weight"),
                    "bestaetigungen": roh.get("confirmations", 0),
                    "blockhash": roh.get("blockhash"),
                    "blockzeit": roh.get("blocktime"),
                    "eingaenge": len(roh.get("vin") or []),
                    "ausgaenge": len(roh.get("vout") or []),
                }
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            pass

        if eigen is None and knoten is None:
            raise HTTPException(404, {"meldung": "tx_unbekannt"})

        # Der Cluster -- nur, solange sie wartet. Bestaetigte Transaktionen
        # haben keinen mehr, und Core antwortet dann mit einem Fehler.
        paket: Optional[Dict] = None
        if knoten is None or not knoten.get("bestaetigungen"):
            try:
                paket = mempoolcluster.aus_core(
                    knotenverbindung().ruf("getmempoolcluster", sauber,
                                           zeitlimit=10.0), sauber)
            except (rpc.NichtErreichbar, rpc.RpcFehler):
                paket = None
        return {"txid": sauber, "eigen": eigen, "knoten": knoten,
                "cluster": paket}

    # ── Wer die Bloecke findet ─────────────────────────────────────────

    @api.get("/auswertung/pools", dependencies=geschuetzt)
    def pool_anteile(bloecke: int = 144) -> Dict:
        """Die Anteile der Mining-Pools an den aufgezeichneten Bloecken.

        Nur aus dem, was dieser Knoten selbst mitgeschrieben hat -- ein Pool
        wird an seiner Kennung in der Coinbase erkannt (pools.py). Die
        Grundlage steht mit in der Antwort.
        """
        if bloecke not in POOL_FENSTER:
            raise HTTPException(400, {"meldung": "pool_fenster_unbekannt"})
        return {"fenster": bloecke, **auswertung.pool_anteile(bloecke)}

    # ── Eine Adresse abfragen ──────────────────────────────────────────
    #
    # Im Hintergrund, weil Core fuer einen Scan Minuten braucht -- eine
    # Anfrage, die so lange offen steht, bricht ein Proxy unterwegs ab. Die
    # Oberflaeche fragt stattdessen den Stand ab.
    adresssuche: Dict = {"adresse": None, "laeuft": False, "ergebnis": None,
                         "fehler": None, "grund": "", "start": 0.0,
                         "ende": 0.0}
    adresssperre = threading.Lock()

    def adresse_scannen(adresse: str) -> None:
        ergebnis: Optional[Dict] = None
        fehler: Optional[str] = "a_ad_fehler"
        grund = ""
        try:
            roh = knotenverbindung().ruf(
                "scantxoutset", "start", [adressabfrage.descriptor(adresse)],
                zeitlimit=ADRESS_FRIST_S)
            if isinstance(roh, dict) and roh.get("success"):
                ergebnis, fehler = adressabfrage.ergebnis(roh), None
            else:
                fehler = "a_ad_abgebrochen"
        except rpc.RpcFehler as f:
            grund = str(f)
            if "already in progress" in grund:
                fehler = "scan_belegt"
        except rpc.NichtErreichbar as f:
            grund = str(f)
        finally:
            with adresssperre:
                adresssuche.update(laeuft=False, ergebnis=ergebnis,
                                   fehler=fehler, grund=grund,
                                   ende=time.time())

    @api.post("/auswertung/adresse", dependencies=geschuetzt)
    def adresse_abfragen(frage: Adressfrage) -> Dict:
        """Einen Adress-Scan starten. Das Ergebnis holt GET /auswertung/adresse."""
        with adresssperre:
            if adresssuche["laeuft"]:
                raise HTTPException(409, {"meldung": "adresse_laeuft_schon"})
        try:
            adresse = adressabfrage.pruefe(knotenverbindung(), frage.adresse)
        except adressabfrage.AdresseUngueltig:
            raise HTTPException(400, {"meldung": "adresse_ungueltig"})
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            raise HTTPException(503, {"meldung": "a_ad_kein_bitcoind"})
        with adresssperre:
            if adresssuche["laeuft"]:
                raise HTTPException(409, {"meldung": "adresse_laeuft_schon"})
            adresssuche.update(adresse=adresse, laeuft=True, ergebnis=None,
                               fehler=None, grund="", start=time.time(),
                               ende=0.0)
        if not im_hintergrund("adresssuche", lambda: adresse_scannen(adresse)):
            with adresssperre:
                adresssuche.update(laeuft=False)
            raise HTTPException(409, {"meldung": "adresse_laeuft_schon"})
        # Die Adresse steht bewusst NICHT im Protokoll: wonach jemand sucht,
        # geht niemanden etwas an, auch keine Logdatei.
        log.info("Adressabfrage gestartet.")
        return {"ok": True, "adresse": adresse}

    @api.get("/auswertung/adresse", dependencies=geschuetzt)
    def adresse_stand() -> Dict:
        """Wie weit der Scan ist -- und was er gefunden hat."""
        with adresssperre:
            stand = dict(adresssuche)
        fortschritt = None
        if stand["laeuft"]:
            with contextlib.suppress(rpc.NichtErreichbar, rpc.RpcFehler):
                s = knotenverbindung().ruf("scantxoutset", "status",
                                           zeitlimit=3.0)
                if isinstance(s, dict):
                    fortschritt = s.get("progress")
        dauer = None
        if stand["start"]:
            dauer = round((stand["ende"] or time.time()) - stand["start"], 1)
        return {"laeuft": stand["laeuft"], "adresse": stand["adresse"],
                "fortschritt": fortschritt, "ergebnis": stand["ergebnis"],
                "fehler": stand["fehler"], "grund": stand["grund"],
                "dauer_s": dauer}

    @api.post("/auswertung/adresse/abbrechen", dependencies=geschuetzt)
    def adresse_abbrechen() -> Dict:
        try:
            knotenverbindung().ruf("scantxoutset", "abort", zeitlimit=5.0)
        except (rpc.NichtErreichbar, rpc.RpcFehler):
            raise HTTPException(503, {"meldung": "a_ad_kein_bitcoind"})
        return {"ok": True}

    # ── Lightning: die Wallet anlegen ──────────────────────────────────
    #
    # Der Seed lebt AUSSCHLIESSLICH hier: im Arbeitsspeicher, zwischen dem
    # Erzeugen und der Gegenprobe, mit Verfallsdatum. Er wird nicht
    # geschrieben, nicht protokolliert und nicht in den Zustand gelegt.
    # Die Vorgabe des Betreibers dazu ist eindeutig und aelter als dieses Projekt: "eine
    # wallet seed gehoert immer auf ein blatt papier nie auf platte irgendwo".
    #
    # Ein Neustart der Anwendung wirft ihn damit weg. Das ist kein Mangel,
    # sondern die Probe aufs Exempel: wer ihn dann nicht auf Papier hat, hat
    # ihn nicht.
    seedhalter: Dict = {"woerter": [], "stellen": [], "erzeugt": 0.0,
                        "versuche": 0}

    def seed_vergessen() -> None:
        seedhalter.update(woerter=[], stellen=[], erzeugt=0.0, versuche=0)

    def seed_frisch() -> bool:
        return bool(seedhalter["woerter"]) and (
            time.monotonic() - seedhalter["erzeugt"] < SEED_FRIST_SEKUNDEN)

    def wallet_passwort(gewaehlt: str) -> str:
        """Das Wallet-Passwort -- IMMER eines, das der Nutzer kennt.

        Bis zum 09.09.2026 stand hier:

            if automatisch:
                return secrets.token_urlsafe(32)

        Bei eingeschaltetem Auto-Entsperren wuerfelte die Anwendung also
        selbst eines, schrieb es neben die Wallet und zeigte es NIE an --
        auch spaeter nicht. Der Betreiber sah das sofort: "wenn ich auch das auto
        entsperren aktiviere sollte ich das passwort selbst gewaehlt haben
        oder es mir wenigstens anzeigen lassen".

        Er hat recht, und die Folge ist groesser als die Unbequemlichkeit:
        geht die Datei wallet.pass verloren, waehrend die Wallet bleibt, ist
        sie zu -- und NIEMAND kann sie oeffnen. Weder er noch diese
        Anwendung. Es hilft dann nur der Seed und eine vollstaendige
        Wiederherstellung. Ein Passwort, das man nicht kennt, ist kein
        Passwort, sondern eine zweite Datei, die kaputtgehen kann.

        Der Schalter entscheidet jetzt nur noch, WO das Passwort liegt --
        auf der Platte oder im Kopf. Nicht mehr, wer es kennt. Damit faellt
        ein ganzer Zweig weg, und die Frage wird ehrlich.
        """
        gewaehlt = gewaehlt or ""
        if len(gewaehlt) < auth.MIN_PASSWORTLAENGE:
            raise HTTPException(400, {"meldung": "passwort_zu_kurz",
                                      "mindestens": auth.MIN_PASSWORTLAENGE})
        return gewaehlt

    def waehle_entsperrweg(roh: str, altes_haekchen: bool) -> str:
        """Welcher der drei Wege gemeint ist.

        Leer heisst: das alte Haekchen gilt. Ein gespeicherter
        Assistentenzustand traegt womoeglich noch nichts anderes, und der
        darf nicht stillschweigend in einer anderen Betriebsart landen.
        """
        weg = (roh or "").strip().lower()
        if weg in ENTSPERRWEGE:
            return weg
        return "datei" if altes_haekchen else "aus"

    def entsperrweg_einrichten(weg: str, passwort: str) -> Dict:
        """Nach dem Anlegen: wie kommt die Wallet kuenftig wieder auf?

        Drei Wege, und die Wahl gehoert dem Nutzer. Aus dem Betrieb, 10.09.2026:
        "das soll sich jeder nutzer aussuchen koennen ob sich das wallet
        selbst entsperrt ob ich den tresor will .. oder nicht".

        Gespeichert wird nur die WAHL. Das Passwort geht bei "datei" in LNDs
        Entsperrdatei, bei "merken" in den Arbeitsspeicher und bei "aus"
        nirgendwohin -- weder in den Zustand noch ins Protokoll.
        """
        vorhanden = ablage.lies("lnd") or ""
        pfad = lnd.passwortdatei(konf.fast)
        zustand.merke_walletwahl({"entsperrweg": weg})

        if weg == "datei":
            storage.schreibe_geheimnis(str(pfad), passwort)
            walletmerker.vergiss()      # die Datei macht ihn ueberfluessig
            if vorhanden:
                ablage.schreibe("lnd", nodeconfig.setze_entsperrdatei(
                    vorhanden, str(pfad)))
                ablage.gib_frei("lnd")
            return {"ok": True, "entsperrweg": "datei",
                    "automatisch_entsperren": True,
                    "neustart_noetig": bool(vorhanden)}

        geaendert = _entsperrdatei_loeschen(vorhanden, pfad)
        if weg == "merken":
            # Leer ist erlaubt und heisst: der Weg gilt ab jetzt, gemerkt ist
            # noch nichts. Genau so wechselt jemand von "aus" hierher, ohne
            # sein Passwort tippen zu muessen -- beim naechsten Entsperren
            # faellt es von allein an, und dann ist es geprueft.
            #
            # Was hier ankommt, ist entweder leer oder geprueft: LND hat die
            # Wallet gerade damit angelegt, sich damit entsperren lassen, oder
            # es kam aus der Entsperrdatei.
            walletmerker.merke(passwort)
            return {"ok": True, "entsperrweg": "merken",
                    "automatisch_entsperren": False,
                    "neustart_noetig": geaendert}

        # "aus": nichts bleibt zurueck. Nach jedem Start von LND fragt die
        # Oberflaeche danach.
        walletmerker.vergiss()
        return {"ok": True, "entsperrweg": "aus",
                "automatisch_entsperren": False,
                "neustart_noetig": geaendert}

    def _entsperrdatei_loeschen(vorhanden: str, pfad) -> bool:
        """Klartext weg, Zeile weg. Gibt zurueck, ob LND neu starten muss."""
        pfad.unlink(missing_ok=True)
        if vorhanden and nodeconfig.lies_entsperrdatei(vorhanden):
            ablage.schreibe("lnd", nodeconfig.setze_entsperrdatei(vorhanden, ""))
            ablage.gib_frei("lnd")
            return True
        return False

    @api.post("/lightning/seed", dependencies=geschuetzt)
    def seed_erzeugen() -> Dict:
        """Vierundzwanzig Woerter erzeugen und EINMAL zeigen.

        Folgenlos: LND wuerfelt und antwortet, angelegt wird dabei nichts.
        Wer hier abbricht, hinterlaesst keinen halben Zustand.
        """
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)
        if stand["stand"] != "keine_wallet":
            # Einen zweiten Seed anzubieten, waehrend eine Wallet existiert,
            # waere die gefaehrlichste Verwechslung, die diese Oberflaeche
            # anbieten koennte.
            raise HTTPException(409, {"meldung": "wallet_gibt_es_schon",
                                      "stand": stand["stand"]})
        try:
            woerter = lnd.erzeuge_seed(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.warning("Seed konnte nicht erzeugt werden: %s", fehler)
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})

        # Welche Stellen abgefragt werden, wird JETZT gewuerfelt und
        # festgehalten -- nicht erst bei der Gegenprobe. Sonst koennte man
        # die Frage so lange neu stellen lassen, bis eine kommt, die man
        # zufaellig beantworten kann.
        stellen = sorted(secrets.SystemRandom().sample(
            range(1, lnd.SEED_WOERTER + 1), GEGENPROBE_STELLEN))
        seedhalter.update(woerter=woerter, stellen=stellen,
                          erzeugt=time.monotonic(), versuche=0)
        return {"woerter": woerter, "stellen": stellen,
                "frist_minuten": int(SEED_FRIST_SEKUNDEN // 60)}

    @api.post("/lightning/wallet", dependencies=geschuetzt)
    def wallet_anlegen(probe: Gegenprobe) -> Dict:
        """Die Gegenprobe abnehmen -- und erst dann die Wallet anlegen.

        Die Reihenfolge ist der Punkt. Wer die Woerter nicht abgeschrieben
        hat, bekommt hier keine Wallet, sondern die Frage noch einmal. Eine
        Wallet, deren Seed niemand hat, ist keine Bequemlichkeit, sondern
        eine Falle mit Zeitzuender.
        """
        if not seed_frisch():
            seed_vergessen()
            raise HTTPException(409, {"meldung": "seed_abgelaufen"})

        seedhalter["versuche"] += 1
        erwartet = {str(nr): seedhalter["woerter"][nr - 1]
                    for nr in seedhalter["stellen"]}
        gegeben = {str(k): (v or "").strip().lower()
                   for k, v in (probe.antworten or {}).items()}
        if any(gegeben.get(nr) != wort for nr, wort in erwartet.items()):
            uebrig = GEGENPROBE_VERSUCHE - seedhalter["versuche"]
            if uebrig <= 0:
                # Wer ihn nach fuenf Anlaeufen nicht vorlesen kann, hat ihn
                # nicht aufgeschrieben. Dann lieber von vorn -- mit einem
                # neuen Seed, damit der alte nicht halb bekannt herumliegt.
                seed_vergessen()
                raise HTTPException(400, {"meldung": "gegenprobe_aufgegeben"})
            raise HTTPException(400, {"meldung": "gegenprobe_falsch",
                                      "versuche_uebrig": uebrig})

        weg = waehle_entsperrweg(probe.entsperrweg,
                                 probe.automatisch_entsperren)
        # Getippt wird es in JEDEM der drei Wege. Auch bei "merken": nach
        # einem Stromausfall faellt diese Anwendung mit, und dann muss der
        # Nutzer es kennen. Ein Passwort, das die Anwendung fuer ihn
        # gewuerfelt hat, waere in genau dem Moment keines mehr.
        passwort = wallet_passwort(probe.passwort)

        # Erst die Wallet, dann die Entsperrdatei. Andersherum bricht LND den
        # Start ab: "wallet unlock password file was specified but wallet
        # does not exist" (config_builder.go, v0.21.2-beta).
        try:
            lnd.lege_wallet_an(lndverbindung(), passwort, seedhalter["woerter"])
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.warning("Wallet konnte nicht angelegt werden: %s", fehler)
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        finally:
            # Ob es geklappt hat oder nicht: der Seed hat hier nichts mehr
            # verloren. Bei Erfolg ist er auf Papier, bei Misserfolg gehoert
            # ein neuer gewuerfelt.
            seed_vergessen()

        return entsperrweg_einrichten(weg, passwort)

    # ── Lightning: einen gesicherten Knoten zurueckholen ───────────────
    #
    # Der Weg, den es lange NICHT gab -- und dessen Fehlen der groesste Mangel
    # am ganzen Knoten war. Eine Sicherung, die man nicht zurueckspielen kann,
    # ist keine Sicherung, sondern eine Beruhigung.
    #
    # Er laeuft ueber DENSELBEN Aufruf wie das Anlegen, weil LND es so
    # vorsieht: initwallet nimmt neben dem Seed zwei weitere Felder entgegen.
    # Das hat eine Folge, die hier ausdruecklich festgehalten gehoert: der
    # Aufruf braucht KEIN Macaroon, denn es gibt noch keine Wallet. Die
    # Anwendung kann also wiederherstellen, ohne dafuer je ein Recht zu
    # halten, das Geld bewegen koennte. Der Weg ueber RestoreChannelBackups
    # am laufenden Knoten braeuchte offchain:write -- und dasselbe Recht
    # erlaubt bei LND SendPaymentV2.
    #
    # WAS DABEI ZURUECKKOMMT, und was nicht:
    #
    #   * Die On-Chain-Mittel. Vollstaendig, aus den vierundzwanzig Woertern.
    #   * Die abgerechneten Guthaben in den Kanaelen -- ueber die
    #     Kanalsicherung. LND zwingt die Gegenstellen dabei zum
    #     Zwangsschluss und holt das Geld auf die Kette. Die Kanaele selbst
    #     sind danach zu; wiederhergestellt wird das Geld, nicht der Betrieb.
    #   * NICHT zurueck kommen schwebende HTLCs. LNDs eigene Formulierung:
    #     "funds that are in the base commitment outputs, and not HTLCs"
    #     (docs/recovery.md).
    @api.post("/lightning/wiederherstellen", dependencies=geschuetzt)
    def wallet_wiederherstellen(eingabe: Wiederherstellung) -> Dict:
        """Aus vierundzwanzig Woertern und einer Kanalsicherung zurueck."""
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)
        if stand["stand"] == "aus":
            # "Aus" heisst: nicht erreichbar, nicht "es gibt keine Wallet".
            # Das auseinanderzuhalten zaehlt genau hier am meisten -- wer aus
            # einem Datenverlust kommt und "es gibt bereits eine Wallet"
            # liest, sucht an der voellig falschen Stelle.
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        if stand["stand"] != "keine_wallet":
            # Genau wie beim Anlegen: eine zweite Wallet neben einer
            # bestehenden ist die gefaehrlichste Verwechslung, die diese
            # Oberflaeche anrichten koennte.
            raise HTTPException(409, {"meldung": "wallet_gibt_es_schon",
                                      "stand": stand["stand"]})

        # Abgeschrieben wird von Hand und abgetippt auch. Grossschreibung,
        # Leerzeichen und ein versehentlich in EIN Feld geklebter Seed sind
        # kein Grund zu scheitern -- ein falsches Wort schon, und das faengt
        # LNDs Pruefsumme ab.
        woerter = " ".join(eingabe.woerter or []).lower().split()
        if len(woerter) != lnd.SEED_WOERTER:
            raise HTTPException(400, {"meldung": "seed_unvollstaendig",
                                      "gezaehlt": len(woerter),
                                      "erwartet": lnd.SEED_WOERTER})

        blob = eingabe.kanalsicherung or ""
        if eingabe.vom_ziel:
            blob = sicherung_vom_ziel_holen()
        if blob:
            try:
                roh = base64.b64decode(blob, validate=True)
            except (ValueError, TypeError):
                raise HTTPException(400, {"meldung": "sicherung_unlesbar"})
            # Mehr laesst sich ohne laufenden Knoten nicht pruefen: die Datei
            # ist mit einem Schluessel aus dem Seed verschluesselt. Was hier
            # durchkommt und trotzdem falsch ist, merkt erst LND -- und dann
            # startet es nicht. Deshalb steht in der Oberflaeche daneben, dass
            # man das VORHER prueft, solange der alte Knoten noch laeuft.
            if not lnd.sicherung_plausibel(roh):
                raise HTTPException(400, {"meldung": "sicherung_zu_klein",
                                          "bytes": len(roh)})

        weg = waehle_entsperrweg(eingabe.entsperrweg,
                                 eingabe.automatisch_entsperren)
        passwort = wallet_passwort(eingabe.passwort)
        try:
            lnd.lege_wallet_an(
                knoten, passwort, woerter,
                passphrase=eingabe.passphrase,
                fenster=lnd.WIEDERHERSTELLUNG_FENSTER,
                kanalsicherung=blob)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            # Bewusst NICHT als "LND antwortet nicht" abgetan. Beim
            # Wiederherstellen ist der haeufigste Fehlschlag ein vertipptes
            # Wort, und den faengt aezeeds Pruefsumme ab. Wer stattdessen
            # "Dienst nicht erreichbar" liest, sucht an der falschen Stelle.
            #
            # UND LNDS EIGENER WORTLAUT KOMMT MIT. Bis zum 11.09.2026 blieb
            # er im Protokoll, und die Oberflaeche behauptete in JEDEM Fall,
            # der Zettel sei falsch. LND lehnt aber aus mehreren Gruenden ab
            # -- eine Passphrase, die niemand gesetzt hat, ist einer davon.
            # Jemandem zu sagen "deine vierundzwanzig Woerter stimmen nicht",
            # wenn sie stimmen, ist die teuerste Falschauskunft, die diese
            # Anwendung geben kann: am Ende wirft er den Zettel weg.
            log.warning("Wiederherstellung abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "seed_nicht_angenommen",
                                      "einzelheit": str(fehler)})
        finally:
            # Die Woerter haben hier nichts mehr verloren -- so wenig wie die
            # selbst erzeugten beim Anlegen.
            woerter = []

        antwort = entsperrweg_einrichten(weg, passwort)
        antwort["mit_kanaelen"] = bool(blob)
        antwort["fenster"] = lnd.WIEDERHERSTELLUNG_FENSTER
        return antwort

    def gelebter_entsperrweg() -> str:
        """Welcher Weg TATSAECHLICH gilt -- nicht welcher einmal gewaehlt
        wurde.

        Die Klartextdatei entscheidet zuerst, und zwar weil sie eine Tatsache
        auf der Platte ist: liegt sie da, entsperrt LND sich damit selbst,
        ganz gleich was irgendwo notiert steht. Erst danach zaehlt die
        gespeicherte Wahl -- "merken" und "aus" hinterlassen beide nichts,
        also kann man sie nur dort auseinanderhalten.
        """
        if lnd.passwortdatei(konf.fast).exists():
            return "datei"
        gewaehlt = (zustand.laden().walletwahl or {}).get("entsperrweg", "")
        return "merken" if gewaehlt == "merken" else "aus"

    # ── Die PIN: das Schloss vor jeder Geldbewegung ────────────────────
    #
    # Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also
    # knoten oeffnen oder schliessen geld transferieren".
    #
    # Sie schuetzt gegen etwas anderes als der Entsperrweg: der entscheidet,
    # was jemand mit der PLATTE anfangen kann, die PIN steht gegen eine
    # uebernommene SITZUNG in dieser Oberflaeche. Warum sechs Stellen dafuer
    # genuegen und was daraus folgt, steht bei auth.Freigabe.

    def freigabe_pruefen(pin: str) -> None:
        """Der Torwaechter fuer alles, was Unwiederbringliches tut.

        Ohne eingerichtete PIN tut er NICHTS. Wer keine will, soll nicht
        ploetzlich vor einer Abfrage stehen, die es fuer ihn gar nicht gibt.
        """
        if not freigabe.vorhanden:
            return
        if not pin:
            raise HTTPException(403, {"meldung": "pin_noetig"})
        try:
            freigabe.pruefe(pin)
        except auth.FreigabeGesperrt:
            raise HTTPException(429, {"meldung": "zu_viele_versuche",
                                      "wartet_noch": freigabe.wartet_noch()})
        except auth.FreigabeAbgelehnt:
            raise HTTPException(400, {"meldung": "pin_falsch",
                                      "wartet_noch": freigabe.wartet_noch()})

    @api.get("/freigabe", dependencies=geschuetzt)
    def freigabe_lesen() -> Dict:
        return {"eingerichtet": freigabe.vorhanden,
                # Ohne diese Zahl steht der Nutzer vor einem Feld, das nichts
                # annimmt, und weiss nicht, ob es an ihm liegt.
                "wartet_noch": round(freigabe.wartet_noch()),
                "stellen_min": auth.PIN_MIN_STELLEN,
                "stellen_max": auth.PIN_MAX_STELLEN}

    @api.post("/freigabe", dependencies=geschuetzt)
    def freigabe_einrichten(wahl: Freigabewahl) -> Dict:
        konto = konten.lade()
        if not konto or not auth.pruefe_passwort(konto.hash, wahl.passwort):
            # Bewusst 403 und nicht 400: es ist keine Formfrage, sondern eine
            # abgelehnte Berechtigung.
            raise HTTPException(403, {"meldung": "passwort_falsch"})
        try:
            freigabe.einrichten(wahl.pin)
        except PermissionError:
            raise HTTPException(409, {"meldung": "pin_existiert"})
        except ValueError as fehler:
            raise HTTPException(400, {"meldung": str(fehler),
                                      "stellen_min": auth.PIN_MIN_STELLEN,
                                      "stellen_max": auth.PIN_MAX_STELLEN})
        log.info("PIN eingerichtet -- Handgriffe mit Folgen fragen ab jetzt.")
        return {"ok": True, "eingerichtet": True}

    @api.post("/freigabe/aendern", dependencies=geschuetzt)
    def freigabe_aendern(wahl: Pinwechsel) -> Dict:
        if not freigabe.vorhanden:
            raise HTTPException(409, {"meldung": "keine_pin"})
        try:
            freigabe.aendern(wahl.alt, wahl.neu)
        except auth.FreigabeGesperrt:
            raise HTTPException(429, {"meldung": "zu_viele_versuche",
                                      "wartet_noch": freigabe.wartet_noch()})
        except auth.FreigabeAbgelehnt:
            raise HTTPException(400, {"meldung": "pin_falsch",
                                      "wartet_noch": freigabe.wartet_noch()})
        except ValueError as fehler:
            raise HTTPException(400, {"meldung": str(fehler),
                                      "stellen_min": auth.PIN_MIN_STELLEN,
                                      "stellen_max": auth.PIN_MAX_STELLEN})
        return {"ok": True}

    @api.post("/freigabe/entfernen", dependencies=geschuetzt)
    def freigabe_entfernen(wahl: Pineingabe) -> Dict:
        """Nur, wer sie kennt, darf sie abschaffen.

        Das Kontopasswort waere hier KEIN zusaetzlicher Schutz: wer die PIN
        kennt, kommt ohnehin an alles, was sie bewacht.
        """
        if not freigabe.vorhanden:
            return {"ok": True, "eingerichtet": False}
        try:
            freigabe.entfernen(wahl.pin)
        except auth.FreigabeGesperrt:
            raise HTTPException(429, {"meldung": "zu_viele_versuche",
                                      "wartet_noch": freigabe.wartet_noch()})
        except auth.FreigabeAbgelehnt:
            raise HTTPException(400, {"meldung": "pin_falsch",
                                      "wartet_noch": freigabe.wartet_noch()})
        log.warning("PIN abgeschafft.")
        return {"ok": True, "eingerichtet": False}

    @api.get("/lightning/entsperrweg", dependencies=geschuetzt)
    def entsperrweg_lesen() -> Dict:
        """Wie die Wallet heute wieder aufgeht -- und ob gerade jemand
        tippen muss.

        "gemerkt" ist die Auskunft, an der die Oberflaeche haengt: im Weg
        "merken" nach einem Neustart DIESER Anwendung ist er falsch, und
        dann steht wieder eine Eingabe an. Ohne diese Unterscheidung wuerde
        sie behaupten, es kuemmere sich jemand darum.
        """
        return {"weg": gelebter_entsperrweg(),
                "gemerkt": walletmerker.hat,
                "wege": list(ENTSPERRWEGE)}

    @api.post("/lightning/entsperrweg", dependencies=geschuetzt)
    def entsperrweg_wechseln(wahl: Entsperrwegwahl) -> Dict:
        """Den Entsperrweg an einer bestehenden Wallet umstellen.

        Waehlbar war der Weg bisher nur beim Anlegen -- wer schon eine
        Wallet hatte, kam nie daran. "Dann leg sie halt neu an" ist keine
        Antwort, sobald Geld darin liegt.

        DIE REGEL, die alles andere bestimmt: ein Wallet-Passwort, das diese
        Anwendung nicht GEPRUEFT hat, darf sie nicht auf die PLATTE schreiben.
        Sonst startet LND kuenftig mit einem Passwort, das es ablehnt -- es
        haengt dann in einer Endlosschleife, und niemand sieht warum.

        Pruefen kann das nur LND, und nur an einer GESPERRTEN Wallet. Deshalb
        derselbe Umweg wie beim Loeschen: erst sperren, dann umstellen.

        DAS GILT ABER NUR FUER DEN WEG "datei". Aus dem Betrieb, 10.09.2026: "habe
        aber gerade den Haken gesetzt bei fuer die Laufzeit merken aber das
        wird noch nicht uebernommen". Er hatte den Weg "aus" -- und diese
        Funktion verlangte von ihm ein getipptes Passwort UND eine gesperrte
        Wallet, um auf "merken" zu wechseln. Fuer nichts:

          * "aus" legt nirgends etwas ab. Es gibt nichts zu pruefen.
          * "merken" legt nichts auf die PLATTE. Ein falsches Passwort im
            Arbeitsspeicher richtet keinen Schaden an -- der Sammler legt es
            LND einmal vor, faengt sich eine Abfuhr, wirft es weg und laesst
            fragen. Genau der Zustand, in dem man ohnehin war.

        Also wird nur dort gefragt, wo es gebraucht wird. Und wo das Passwort
        schon nachweislich funktioniert -- in der Klartextdatei, aus der LND
        sich seit jeher entsperrt, oder im Speicher, in den es nur nach einem
        gelungenen Entsperren gelangt -- entfaellt die Probe ohnehin.
        """
        ziel = (wahl.weg or "").strip().lower()
        if ziel not in ENTSPERRWEGE:
            raise HTTPException(400, {"meldung": "entsperrweg_unbekannt",
                                      "wege": list(ENTSPERRWEGE)})

        heute = gelebter_entsperrweg()
        pfad = lnd.passwortdatei(konf.fast)

        # 1. An das heutige Wallet-Passwort kommen -- soweit es OHNE eine
        #    Eingabe geht. Beide Quellen sind bereits geprueft: aus der
        #    Klartextdatei entsperrt LND sich seit jeher, und in den Speicher
        #    gelangt es nur nach einem gelungenen Entsperren.
        passwort = ""
        if heute == "datei":
            try:
                passwort = pfad.read_text(encoding="utf-8").strip()
            except OSError as fehler:
                log.error("Entsperrdatei nicht lesbar: %s", fehler)
                raise HTTPException(500, {"meldung": "entsperrdatei_fehlt"})
        elif heute == "merken" and walletmerker.hat:
            passwort = walletmerker.hol()

        # 2. Fehlt es, wird es nur fuer den einen Weg verlangt, der es
        #    wirklich braucht: "datei" schreibt Klartext auf die Platte, und
        #    ein falsches Passwort dort haengt LND beim naechsten Start auf.
        #    "aus" und "merken" schreiben nichts -- dort waere die Abfrage
        #    eine Huerde ohne Zweck.
        if not passwort and ziel == "datei":
            passwort = wahl.passwort
            if not passwort:
                raise HTTPException(400, {"meldung": "passwort_fehlt"})
            # Nur hier kommt es aus einer Eingabe -- also nur hier wird es
            # geprueft, und zwar von LND selbst.
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] != "gesperrt":
                raise HTTPException(409, {"meldung": "wallet_nicht_gesperrt"})
            try:
                lnd.entsperre(knoten, passwort)
            except lnd.LndFehler as fehler:
                log.info("Wechsel abgelehnt: %s", fehler)
                raise HTTPException(400, {"meldung": "passwort_falsch"})
            except lnd.NichtErreichbar:
                raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})

        # 3. Den alten Weg abraeumen -- erst danach den neuen anlegen, damit
        #    nie zwei gleichzeitig gelten.
        vorhanden = ablage.lies("lnd") or ""
        _entsperrdatei_loeschen(vorhanden, pfad)

        antwort = entsperrweg_einrichten(ziel, passwort)
        # Unter demselben Namen wie beim Lesen: die Oberflaeche fragt
        # /lightning/entsperrweg und bekommt "weg" -- sie soll nach dem
        # Wechsel nicht ploetzlich woanders nachsehen muessen.
        antwort["weg"] = ziel
        log.info("Entsperrweg gewechselt: %s -> %s", heute, ziel)
        return antwort

    @api.post("/lightning/entsperren", dependencies=geschuetzt)
    def wallet_entsperren(eingabe: Entsperrung) -> Dict:
        """Eine gesperrte Wallet entsperren -- mit dem Wallet-Passwort.

        Es geht durch diese Funktion hindurch und nirgendwo sonst hin. Ob
        etwas davon haengen bleibt, entscheidet ausschliesslich der gewaehlte
        Weg: bei "merken" behaelt die Anwendung es, solange sie laeuft, bei
        "aus" ist es nach dieser Anfrage fort. Diese Anwendung merkt sich
        nichts heimlich, weil es bequemer waere.
        """
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)
        if stand["stand"] not in ("gesperrt", "aus"):
            return {"ok": True, "stand": stand["stand"]}

        passwort = eingabe.passwort
        if not passwort:
            raise HTTPException(400, {"meldung": "passwort_fehlt"})

        try:
            lnd.entsperre(knoten, passwort)
        except lnd.LndFehler as fehler:
            # LND unterscheidet nicht zwischen "falsches Passwort" und
            # anderem Aerger -- der Wortlaut steht im Protokoll, dem Nutzer
            # gegenueber bleibt es bei der einen Erklaerung, die passt.
            log.info("Entsperren abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "passwort_falsch"})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        # ERST JETZT gemerkt, nach der einzigen Pruefung, die es gibt. Ein
        # Passwort vor der Probe zu merken hiesse, dem Sammler ein falsches
        # in die Hand zu geben, das er dann im Takt wiederholt.
        if gelebter_entsperrweg() == "merken":
            walletmerker.merke(passwort)
        return {"ok": True, "stand": "startet"}

    # ── Die Wallet offen halten ────────────────────────────────────────
    #
    # Der eigentliche Grund, warum es "merken" gibt. Nicht der Stromausfall
    # -- der kommt selten -- sondern die Neustarts, die DIESE ANWENDUNG
    # ausloest: Name geaendert, Sichtbarkeit geaendert, Adresse neu
    # aufgeloest. Jedes Mal faehrt LND neu hoch und die Wallet steht zu.
    #
    # Der Sammler laeuft alle fuenf Sekunden. So oft muss das nicht sein --
    # ein Neustart dauert laenger als das -- und eine Abfrage an einen
    # Dienst, der gerade hochfaehrt, kostet jedes Mal eine Wartezeit.
    offenhaltestand = {"zuletzt": 0.0}

    def wallet_offenhalten() -> bool:
        """Die Wallet nach einem Neustart selbst wieder aufmachen.

        Tut GAR NICHTS, solange kein Passwort gemerkt ist -- also im Weg
        "aus" nie, und im Weg "merken" erst, nachdem der Nutzer einmal
        getippt hat. Nach einem Neustart dieser Anwendung ist der Merker
        leer, und dann wartet der Knoten wieder auf ihn. Genau das ist der
        Unterschied zur Klartextdatei.
        """
        try:
            if not walletmerker.hat:
                return False
            jetzt = time.monotonic()
            if jetzt - offenhaltestand["zuletzt"] < OFFENHALTEN_TAKT_SEKUNDEN:
                return False
            offenhaltestand["zuletzt"] = jetzt
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] != "gesperrt":
                return False
            lnd.entsperre(knoten, walletmerker.hol())
            log.info("Wallet nach einem Neustart selbst wieder entsperrt.")
            return True
        except lnd.NichtErreichbar:
            return False        # LND faehrt noch hoch -- beim naechsten Mal
        except lnd.LndFehler as fehler:
            # Das gemerkte Passwort passt nicht mehr. Es weiter vorzulegen
            # waere ein Rateversuch im Fuenfsekundentakt -- also weg damit
            # und den Nutzer fragen lassen.
            log.warning("Gemerktes Wallet-Passwort abgelehnt, verworfen: %s",
                        fehler)
            walletmerker.vergiss()
            return False
        except Exception:                                        # nosec B902
            log.exception("Selbstentsperren fehlgeschlagen")
            return False

    app.state.wallet_offenhalten = wallet_offenhalten

    # ── Kanalsicherung ─────────────────────────────────────────────────
    #
    # Die vierundzwanzig Woerter stellen die On-Chain-Wallet wieder her, die
    # Guthaben IN den Kanaelen nicht. Dafuer braucht es diese Datei -- und sie
    # muss ausser Haus, sonst sichert sie gegen genau die Sache nicht, gegen
    # die man sich sichert.
    sicherungsstand = sicherung.Stand(konf.config_dir)

    def sicherungsziel() -> Dict:
        """Das eingerichtete Ziel -- ohne das Passwort."""
        d = zustand.laden().sicherungsziel or {}
        return {"url": d.get("url", ""), "benutzer": d.get("benutzer", "")}

    def sicherungsziel_passwort() -> str:
        """Das Passwort des Ziels. Eigene Datei, enge Rechte, nie im Zustand."""
        try:
            return (Path(konf.config_dir) / "sicherung.pass").read_text(
                encoding="utf-8")
        except OSError:
            return ""

    def sicherung_vom_ziel_holen() -> str:
        """Die abgelegte Sicherung zurueckholen -- base64, wie LND sie will.

        Der Weg fuer den Fall, fuer den das Ganze gebaut ist: die Platte ist
        hin, die Datei liegt woanders. Dass das Ziel eingerichtet ist, heisst
        dabei nicht, dass dort etwas liegt -- deshalb die eigenen Meldungen.
        """
        ziel = sicherungsziel()
        if not ziel["url"]:
            raise HTTPException(409, {"meldung": "kein_ziel"})
        passwort = sicherungsziel_passwort()
        if not passwort:
            raise HTTPException(409, {"meldung": "kein_passwort"})
        try:
            return sicherung.hole_ab(ziel["url"], ziel["benutzer"], passwort)
        except sicherung.ZielFehler as fehler:
            # Kennt die Anwendung den Fall, sagt sie, was zu tun ist; der
            # Wortlaut des Servers geht trotzdem mit.
            raise HTTPException(400, {"meldung": fehler.grund
                                      or "ziel_gibt_nichts_her",
                                      "einzelheit": str(fehler)})

    def sicherung_hochladen(blob: str) -> str:
        """Zum eingerichteten Ziel schicken. Gibt den Fehler zurueck, oder ""."""
        ziel = sicherungsziel()
        if not ziel["url"]:
            return "kein_ziel"
        passwort = sicherungsziel_passwort()
        if not passwort:
            return "kein_passwort"
        try:
            sicherung.lade_hoch(blob, ziel["url"], ziel["benutzer"], passwort)
        except sicherung.ZielFehler as fehler:
            if fehler.grund:
                # In die Ablage geht der Schluessel -- daraus macht die
                # Oberflaeche einen Satz. Der Wortlaut des Servers gehoert
                # ins Protokoll.
                log.warning("Sicherungsziel antwortet: %s", fehler)
            return fehler.grund or str(fehler)
        return ""

    def sicherung_nachziehen() -> None:
        """Hat sich etwas geaendert? Dann hoch damit.

        Laeuft im Waechter. Ein Kanal, der seit der letzten Sicherung
        dazugekommen ist, ist ein Kanal ohne Sicherung -- und das faellt sonst
        erst auf, wenn die Platte hin ist.
        """
        if not sicherungsziel()["url"]:
            return
        try:
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] != "bereit":
                return
            d = lnd.sicherung_holen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler):
            return
        alt = sicherungsstand.laden()
        if not sicherung.faellig(alt, d["blob"]):
            return
        fehler = sicherung_hochladen(d["blob"])
        sicherung.vermerke(sicherungsstand, d["blob"], d["kanaele"],
                           sicherungsziel()["url"], fehler)
        if fehler:
            log.warning("Kanalsicherung konnte nicht abgelegt werden: %s", fehler)
        else:
            log.info("Kanalsicherung abgelegt (%d Kanaele).", d["kanaele"])

    app.state.sicherung_nachziehen = sicherung_nachziehen

    @api.get("/lightning/sicherung", dependencies=geschuetzt)
    def sicherung_lesen() -> Dict:
        """Wie es um die Sicherung steht -- ohne sie selbst herauszugeben."""
        antwort: Dict = {"ziel": sicherungsziel(), "stand": sicherungsstand.laden(),
                         "kanaele": None, "aktuell": None}
        try:
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] != "bereit":
                return antwort
            d = lnd.sicherung_holen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler):
            return antwort
        antwort["kanaele"] = d["kanaele"]
        # "Aktuell" heisst: was zuletzt abgelegt wurde, entspricht dem, was
        # der Knoten jetzt hat. Ohne Kanaele gibt es nichts zu sichern -- das
        # ist dann auch kein Rueckstand.
        antwort["aktuell"] = (d["kanaele"] == 0
                              or not sicherung.faellig(antwort["stand"], d["blob"]))
        return antwort

    @api.get("/lightning/sicherung/datei", dependencies=geschuetzt)
    def sicherung_herunterladen() -> Response:
        """Die Sicherung als Datei. Der Weg, der immer geht und nichts braucht."""
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        try:
            d = lnd.sicherung_holen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler):
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        if not d["blob"]:
            raise HTTPException(409, {"meldung": "keine_kanaele"})
        if not lnd.sicherung_pruefen(knoten, d["blob"]):
            # Lieber gar keine Datei als eine, auf die sich jemand verlaesst.
            raise HTTPException(500, {"meldung": "sicherung_unbrauchbar"})
        return Response(
            content=base64.b64decode(d["blob"]),
            media_type="application/octet-stream",
            headers={"Content-Disposition":
                     f'attachment; filename="{sicherung.DATEINAME}"'})

    @api.post("/lightning/sicherung/pruefen", dependencies=geschuetzt)
    def sicherung_pruefen(probe: Sicherungsprobe) -> Dict:
        """Nachsehen lassen, ob eine Sicherung wirklich etwas hergibt.

        DER PUNKT DIESES ENDPUNKTS ist nicht die Sicherung, die der Knoten
        gerade selbst erzeugt -- die ist per Bauart heil. Es geht um die
        KOPIE: die Datei auf dem Stick, die in der Cloud, die von vor drei
        Monaten. Ob die etwas taugt, erfaehrt man sonst an dem einen Tag, an
        dem man es nicht mehr erfahren will.

        LND muss sie dafuer wirklich aufschliessen. Damit ist zweierlei
        bewiesen: sie ist heil, und sie gehoert zu DIESEM Knoten -- der
        Schluessel stammt aus dem Seed. Die fremde Sicherung eines anderen
        Knotens scheitert hier, statt spaeter still nichts zurueckzuholen.

        Braucht offchain:read. Kein Recht, das irgendetwas bewegen koennte.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})

        blob = probe.blob or ""
        quelle = "vorgelegt"
        if probe.vom_ziel:
            blob, quelle = sicherung_vom_ziel_holen(), "ziel"
        elif not blob:
            # Ohne Vorlage die des laufenden Knotens -- der Vollstaendigkeit
            # halber, und weil es die Gegenprobe zur eigenen Datei ist.
            try:
                blob = lnd.sicherung_holen(knoten)["blob"]
            except (lnd.NichtErreichbar, lnd.LndFehler):
                raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
            quelle = "knoten"
        if not blob:
            raise HTTPException(409, {"meldung": "keine_kanaele"})

        try:
            base64.b64decode(blob, validate=True)
        except (ValueError, TypeError):
            raise HTTPException(400, {"meldung": "sicherung_unlesbar"})

        try:
            punkte = lnd.sicherung_kanalpunkte(knoten, blob)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.info("Vorgelegte Kanalsicherung abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "sicherung_unbrauchbar"})

        # Heil ist nicht dasselbe wie aktuell. Eine tadellose Sicherung von
        # vorgestern deckt den Kanal von gestern nicht ab -- und genau das
        # ist der Fehler, den man sonst erst hinterher bemerkt.
        offen = None
        try:
            offen = lnd.sicherung_holen(knoten)["kanaele"]
        except (lnd.NichtErreichbar, lnd.LndFehler):
            pass
        return {"ok": True, "quelle": quelle, "kanalpunkte": punkte,
                "abgedeckt": len(punkte), "offen": offen,
                "vollstaendig": offen is not None and len(punkte) >= offen}

    @api.post("/lightning/sicherung/ziel", dependencies=geschuetzt)
    def sicherungsziel_setzen(wahl: Sicherungsziel) -> Dict:
        """Ein Ziel einrichten -- und dabei gleich beweisen, dass es taugt.

        Eingerichtet gilt es erst, wenn eine Sicherung wirklich dort
        angekommen ist. Zugangsdaten zu merken, die noch nie funktioniert
        haben, waere eine Sicherung auf dem Papier.
        """
        e = zustand.laden()
        pfad = Path(konf.config_dir) / "sicherung.pass"
        if not wahl.url:
            zustand.merke_sicherungsziel({})
            pfad.unlink(missing_ok=True)
            return {"ok": True, "ziel": {"url": "", "benutzer": ""}}

        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        try:
            d = lnd.sicherung_holen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler):
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})

        try:
            sicherung.lade_hoch(d["blob"], wahl.url, wahl.benutzer, wahl.passwort)
        except sicherung.ZielFehler as fehler:
            raise HTTPException(400, {"meldung": fehler.grund
                                      or "ziel_nimmt_nichts_an",
                                      "einzelheit": str(fehler)})

        storage.schreibe_geheimnis(str(pfad), wahl.passwort)
        zustand.merke_sicherungsziel({"url": wahl.url, "benutzer": wahl.benutzer})
        stand = sicherung.vermerke(sicherungsstand, d["blob"], d["kanaele"],
                                   wahl.url)
        return {"ok": True, "ziel": {"url": wahl.url, "benutzer": wahl.benutzer},
                "stand": stand}

    @api.post("/knoten/erreichbarkeit", dependencies=geschuetzt)
    def erreichbarkeit_pruefen() -> Dict:
        """Kommt von aussen wirklich jemand an diesen Knoten heran?

        Bewusst POST und bewusst nicht im Takt: die Messung baut echte
        Verbindungen ueber Tor auf und dauert je Adresse bis zu einer halben
        Minute.

        Bewusst SYNCHRON, seit dem 01.09.2026. Vorher war das die einzige
        async-Funktion unter den Endpunkten: die eigentliche Messung lief
        korrekt in einem Thread, die Vorbereitung davor aber NICHT -- eine
        DNS-Aufloesung und ein getblockchaininfo mit fuenfzehn Sekunden
        Geduld, beides mitten in der Ereignisschleife. Solange die liefen,
        stand die gesamte Oberflaeche: kein Fortschritt, kein Protokoll,
        keine andere Abfrage. Als synchrone Funktion gibt FastAPI sie in
        seinen Threadpool, wie jeden anderen Endpunkt hier auch.

        Geprueft werden die Adressen, die der Knoten ANKUENDIGT -- nicht die,
        die er hat. Genau das ist die Frage: findet jemand, der nur die
        Ankuendigung kennt, auch tatsaechlich einen Weg hierher?
        """
        e = zustand.laden()
        if not e.eingerichtet:
            return {"eingerichtet": False}
        # Abgeleitet, nicht roh: bei "nur ueber Tor" wird keine
        # Clearnet-Adresse angekuendigt, auch wenn noch eine eingetragen ist.
        # Sie zu pruefen hiesse, einen Weg zu messen, den es nicht gibt.
        wege = _nach_sichtbarkeit(_wege(e.knotenwahl))
        if not wege["tor"]:
            # Von innen liesse sich das nicht ehrlich messen; siehe das
            # Modul. Lieber nichts sagen als etwas Falsches.
            return {"eingerichtet": True, "erreichbar": None, "geprueft": False,
                    "grund": "tor_aus", "adressen": []}

        adressen = []
        if wege["adresse_ankuendigen"] and wege["externe_adresse"]:
            adressen = nodeconfig.adressen_fuer_netze(
                dyndns.loese_auf(_adressliste(wege["externe_adresse"])),
                wege["ipv4"], wege["ipv6"])
        clearnet_eingetragen = bool(
            wege["adresse_ankuendigen"] and wege["externe_adresse"])

        # Die eigene .onion gehoert dazu -- sie ist einer der Wege, und der
        # verlaesslichste: sie aendert sich bei einer Zwangstrennung nicht.
        #
        # Sie kommt aus dem, was der Knoten SELBST ankuendigt. Steht sie
        # nicht in localaddresses, wird sie gerade nicht angekuendigt -- dann
        # gibt es auch nichts zu pruefen.
        #
        # Bis 0.62.0 lief diese Stelle nur, wenn zusaetzlich eine
        # Clearnet-Adresse eingetragen war. Bei "nur ueber Tor" wurde die
        # .onion deshalb NIE gemessen -- genau die Betriebsart, in der sie der
        # einzige Weg ist. So blieb unbemerkt, dass sie ins Leere zeigte.
        gewollt = onion.dienste_fuer(wege["tor"], wege["sichtbarkeit"])
        lage, _ = lage_mit_grund_gebuendelt()
        onions = [a["adresse"] for a in (lage or {}).get("adressen") or []
                  if str(a.get("adresse", "")).endswith(".onion")]
        if gewollt:
            adressen += onions

        # Fehlt die Onion, wird das GESAGT statt verschwiegen.
        #
        # Der Betreiber hat am 01.09.2026 gemeldet, die Pruefung melde "immer nur
        # IPv4, nie Tor" -- ueber Wochen, bei jedem Versuch. Die Ursache steht
        # seit dem 31.08. im Kommentar zu ABGLEICH_GRUND: waehrend der
        # Abgleich-Pause setzt die Konfiguration onlynet=ipv4,ipv6, und Cores
        # AddLocal() nimmt eine Adresse aus einem nicht erreichbaren Netz gar
        # nicht erst in mapLocalHost auf. Eine ausgelassene Messung gehoert
        # benannt, sonst ist sie eine stille Falschaussage.
        tor_hinweis = ""
        if gewollt and not onions:
            laeuft_mit = nodeconfig.lies_netze(ablage.lies("bitcoind") or "")
            tor_hinweis = ("tor_pausiert" if "onion" not in laeuft_mit
                           else "keine_onion")

        # Lightning und der Wachturm -- mit dem, was LND laut seiner
        # Konfiguration ankuendigt. Ohne Bitcoin-Handschlag: sie sprechen
        # ein anderes Protokoll, und die Frage ist allein, ob Tor bis zu
        # ihnen durchkommt.
        lightning = []
        lnd_conf = ablage.lies("lnd") or ""
        if gewollt and lnd_conf:
            for dienst, adresse in (
                    ("lightning", nodeconfig.lies_lnd_onion(lnd_conf)),
                    ("wachturm", nodeconfig.lies_wachturm_onion(lnd_conf))):
                if adresse:
                    name = "lnd" if dienst == "lightning" else dienst
                    lightning.append(
                        (dienst, adresse, onion.DIENSTE[name].port))

        if not adressen and not lightning:
            grund = ("nicht_aufloesbar" if clearnet_eingetragen
                     else "keine_adresse")
            return {"eingerichtet": True, "erreichbar": False, "geprueft": False,
                    "grund": grund, "adressen": [],
                    "tor_hinweis": tor_hinweis}

        # Tors Messport mit erweiterten Fehlercodes -- nur mit ihnen laesst
        # sich bei einer .onion "dahinter nimmt niemand an" erkennen.
        proxy = (konf.tor_host, konf.tor_pruef_port)
        ergebnis: Dict = {"port": konf.bitcoin_p2p_port, "adressen": [],
                          "erreichbar": False, "geprueft": False}
        if adressen:
            bitcoin = erreichbar.pruefe(adressen, konf.bitcoin_p2p_port, proxy,
                                        erweitert=True)
            ergebnis = {**bitcoin, "adressen": [
                dict(a, dienst="bitcoin") for a in bitcoin.get("adressen", [])]}
        for dienst, adresse, port in lightning:
            einzeln = erreichbar.pruefe([adresse], port, proxy,
                                        handschlag=False, erweitert=True)
            zeilen = [dict(a, dienst=dienst)
                      for a in einzeln.get("adressen", [])]
            ergebnis["adressen"] = ergebnis["adressen"] + zeilen
            ergebnis["erreichbar"] = bool(ergebnis["erreichbar"]
                                          or einzeln.get("erreichbar"))
            ergebnis["geprueft"] = bool(ergebnis["geprueft"]
                                        or einzeln.get("geprueft"))
        return {"eingerichtet": True, "tor_hinweis": tor_hinweis, **ergebnis}

    def guthaben_kurz() -> Optional[Dict]:
        """On-Chain und Kanalguthaben -- oder None, wenn es nichts zu holen gibt.

        None statt Nullen: "0 sat" bei gesperrter Wallet waere eine Auskunft,
        die nicht stimmt.
        """
        try:
            knoten = lndverbindung()
            if lnd.zustand(knoten)["stand"] != "bereit":
                return None
            return lnd.guthaben(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            log.debug("Guthaben fuer die Uebersicht nicht abrufbar: %s", fehler)
            return None

    @api.get("/lightning", dependencies=geschuetzt)
    def lightning() -> Dict:
        """Wo Lightning steht -- und ob es ueberhaupt schon losgehen kann.

        Drei Dinge, die zusammengehoeren und deshalb in einer Antwort stehen:
        was der Dienst gerade macht, was LND selbst von sich sagt, und ob die
        Kette weit genug ist. Getrennt abgefragt haette die Oberflaeche drei
        Halbwahrheiten und muesste sie selbst zusammensetzen.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}

        dienst = ablage.status("lnd").to_dict()
        lage = lage_holen()
        # LND braucht eine fertige Kette. Es waehrend des Erstabgleichs zu
        # starten ginge zwar, waere aber sinnlos: es kaeme ueber "warte auf
        # bitcoind" nicht hinaus und schriebe dabei stundenlang Protokoll.
        kette_bereit = bool(lage) and not lage.get("im_erstsync", True)

        return {
            "eingerichtet": True,
            "dienst": dienst,
            "kette_bereit": kette_bereit,
            "hoehe": (lage or {}).get("hoehe", 0),
            "knoten": lnd.zustand(lndverbindung()),
            # Das Guthaben gehoert auf die Uebersicht -- und dafuer taugt die
            # grosse Kanal-Antwort nicht: die zieht getinfo, Kanalliste,
            # Graph und Weiterleitungen mit. Hier sind es zwei Abfragen, und
            # nur, wenn die Wallet ueberhaupt offen ist.
            "guthaben": guthaben_kurz(),
            # Laeuft gerade ein Neustart, den die Oberflaeche ausgeloest
            # hat? Ohne diese Auskunft steht jemand vor einem Knopf, den er
            # gedrueckt hat, und sieht eine Minute lang nichts.
            #
            # Aus dem Betrieb, 11.09.2026: "dazu steht hier wallet sperren .. da
            # drueck ich drauf passiert nix". Es passierte sehr wohl etwas
            # -- nur nicht auf dem Bildschirm.
            "arbeit_laeuft": bool(wallet_arbeit["laeuft"]),
        }

    def macaroon_sicherstellen(knoten) -> bool:
        """Das eigene Macaroon anlegen, falls es noch keines gibt.

        Bewusst NICHT direkt nach dem Anlegen der Wallet: LND braucht danach
        einen Moment, bis sein RPC-Dienst wirklich antwortet
        (NON_EXISTING -> UNLOCKED -> RPC_ACTIVE -> SERVER_ACTIVE). Ein Backen
        in dieser Luecke scheiterte, und niemand haette gewusst warum.

        Also beim ersten Bedarf und im Waechter. Ist es da, wird admin nie
        wieder angefasst.
        """
        try:
            # Nicht nur "ist eines da", sondern "passt es noch". Ohne die
            # zweite Frage kaeme ein spaeter ergaenztes Recht bei bestehenden
            # Anlagen NIE an -- gebacken wurde bisher nur, wenn gar keines da
            # war. Genau so waere message:write liegengeblieben, das seit dem
            # 04.09.2026 dazugehoert.
            passt = lnd.rechte_passen(knoten.macaroons)
            if lnd.macaroon_da(knoten) and passt:
                return True
            if lnd.zustand(knoten)["stand"] != "bereit":
                return False
            erneuert = lnd.macaroon_da(knoten)
            lnd.lege_macaroon_ab(lnd.backe_macaroon(knoten), knoten.macaroons)
            lnd.merke_rechte(knoten.macaroons)
            log.info("Eigenes Macaroon %s -- ohne onchain:write, also ohne "
                     "die Moeglichkeit, Geld zu bewegen.",
                     "erneuert (Rechte haben sich geaendert)" if erneuert
                     else "angelegt")
            return True
        except (lnd.NichtErreichbar, lnd.LndFehler, OSError) as fehler:
            log.warning("Eigenes Macaroon konnte nicht angelegt werden: %s", fehler)
            return False

    app.state.macaroon_sicherstellen = macaroon_sicherstellen

    @api.post("/lightning/einzahladresse", dependencies=geschuetzt)
    def einzahladresse(art: str = lnd.ADRESSART_VORGABE,
                       neu: bool = False) -> Dict:
        """Eine Adresse fuer die On-Chain-Wallet von LND.

        Ohne `neu` die aktuelle unbenutzte -- sie bleibt beim Neuladen
        dieselbe und rueckt erst weiter, wenn jemand darauf gezahlt hat.
        Vorher erzeugte JEDER Aufruf eine neue, auch das blosse Oeffnen der
        Seite: die Wallet fuellte sich mit ungenutzten Adressen, und die
        Zeile auf dem Bildschirm sprang bei jedem Blick.

        `art` gibt es, weil manche Boersen bis heute nicht an Taproot senden
        koennen. Ohne die Wahl stand man davor und die Anwendung bot keinen
        Ausweg.
        """
        if art not in lnd.ADRESSARTEN:
            raise HTTPException(400, {"meldung": "adressart_unbekannt",
                                      "moeglich": list(lnd.ADRESSARTEN)})
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        if not macaroon_sicherstellen(knoten):
            raise HTTPException(503, {"meldung": "kein_macaroon"})
        try:
            adresse = lnd.einzahladresse(knoten, art, neu)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.warning("Einzahladresse nicht erhalten: %s", fehler)
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        return {"adresse": adresse, "art": art}

    # ── Senden: der Weg zurueck aus der Wallet heraus ──────────────────
    #
    # Aus dem Betrieb, 30.08.2026: "ich werde nix dahin ueberweisen solange ich es
    # nicht zurueck schicken kann". Genau richtig, und deshalb kam es nach
    # der PIN und nicht davor.
    #
    # WAS SICH DAMIT AENDERT: das eigene Macaroon haelt ab jetzt
    # onchain:write. Fuer jemanden mit der PLATTE aendert das nichts -- dort
    # liegt ohnehin LNDs admin.macaroon, und das kann alles. Fuer eine
    # uebernommene SITZUNG in dieser Oberflaeche aendert es alles: ab jetzt
    # gibt es einen Endpunkt, der zahlt. Dagegen steht die PIN.

    TEMPO_ZIELE = {"schnell": 1, "normal": 3, "guenstig": 6}

    def sendesatz(tempo: str) -> int:
        """Satoshi je vByte fuer das gewaehlte Tempo -- aus dem EIGENEN Knoten.

        Aus dem Betrieb, 30.08.2026: "jede info die wir brauchen kommt aus dem
        netzwerk und nicht von extern". Hier ist es die Schaetzung des
        eigenen bitcoind, nicht die eines fremden Dienstes.

        Ohne Schaetzung gibt es KEINEN Satz. Eine Eins hinzuschreiben waere
        bequem und teuer: die Zahlung bliebe womoeglich tagelang liegen.
        """
        name = (tempo or "").strip().lower()
        if name not in TEMPO_ZIELE:
            raise HTTPException(400, {"meldung": "tempo_unbekannt",
                                      "tempi": list(TEMPO_ZIELE)})
        saetze = (kennzahlen_stand["wert"] or {}).get("gebuehren") or {}
        satz = saetze.get(name)
        if not satz:
            raise HTTPException(503, {"meldung": "keine_gebuehrenschaetzung"})
        # Aufgerundet, nie abgerundet: eine Zahlung, die knapp unter der
        # Schaetzung liegt, bleibt liegen.
        return max(1, math.ceil(float(satz)))

    def sendeziel(wunsch: Sendung) -> str:
        """Die Adresse -- geprueft, soweit es ohne LND geht."""
        adresse = (wunsch.adresse or "").strip()
        if not adresse:
            raise HTTPException(400, {"meldung": "adresse_fehlt"})
        return adresse

    def sendebetrag(wunsch: Sendung) -> int:
        """Der Betrag -- oder die Ansage, dass alles gemeint ist.

        Beides zusammen waere geraten: LND lehnt send_all mit einem Betrag
        ab, und was von zweien gaelte, stuende nirgends.
        """
        if wunsch.alles:
            if wunsch.betrag:
                raise HTTPException(400, {"meldung": "alles_und_betrag"})
            return 0
        if wunsch.betrag < lnd.SENDEN_MIN_SAT:
            raise HTTPException(400, {"meldung": "betrag_zu_klein",
                                      "mindestens": lnd.SENDEN_MIN_SAT})
        return wunsch.betrag

    def sendbereit():
        """LND muss laufen und die Wallet offen sein. Sonst nichts."""
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)["stand"]
        if stand == "gesperrt":
            raise HTTPException(409, {"meldung": "wallet_gesperrt"})
        if stand != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        return knoten

    @api.post("/lightning/senden/schaetzen", dependencies=geschuetzt)
    def senden_schaetzen(wunsch: Sendung) -> Dict:
        """Was diese Zahlung kosten wuerde. Bewegt nichts.

        Deshalb auch KEINE PIN: eine Abfrage, die nichts tut, hinter ein
        Schloss zu stellen, macht das Schloss nur laestig und nichts
        sicherer.

        Bei "alles" gibt es keine Schaetzung, und das ist ehrlicher als eine
        erfundene: LND kennt den Betrag erst, wenn es die Eingaben
        zusammengesucht hat -- die Gebuehr geht dann von der Summe ab.
        """
        knoten = sendbereit()
        adresse = sendeziel(wunsch)
        betrag = sendebetrag(wunsch)
        satz = sendesatz(wunsch.tempo)
        if wunsch.alles:
            return {"satz_sat_vb": satz, "alles": True}
        try:
            d = lnd.kosten_schaetzen(knoten, adresse, betrag,
                                     TEMPO_ZIELE[wunsch.tempo])
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            # Der haeufigste Grund ist eine vertippte Adresse, der
            # zweithaeufigste zu wenig Guthaben. Beides sagt LND im Klartext
            # -- und beides gehoert dem Nutzer gesagt, nicht dem Protokoll.
            log.info("Schaetzung abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "senden_abgelehnt",
                                      "einzelheit": str(fehler)})
        d["satz_sat_vb"] = d.get("satz_sat_vb") or satz
        d["alles"] = False
        return d

    @api.post("/lightning/senden", dependencies=geschuetzt)
    def senden(wunsch: Sendung) -> Dict:
        """On-Chain senden. UNWIDERRUFLICH.

        Die PIN wird ZUERST geprueft, vor allem anderen. Eine Reihenfolge,
        in der erst der Betrag und dann die Berechtigung geprueft wird,
        verraet einem Angreifer, ob sein Betrag gepasst haette -- und, viel
        wichtiger, sie ist eine Zeile vom Unfall entfernt.

        NICHT wiederholen bei einem Zeitlimit. Die Zahlung ist womoeglich
        laengst unterwegs und nur die Antwort blieb aus; ein zweiter Versuch
        schickt sie ein zweites Mal. Wer hier etwas wiederholen will, sieht
        vorher in die Kette.
        """
        freigabe_pruefen(wunsch.pin)
        knoten = sendbereit()
        adresse = sendeziel(wunsch)
        betrag = sendebetrag(wunsch)
        satz = sendesatz(wunsch.tempo)
        try:
            txid = lnd.sende(knoten, adresse, betrag, satz, alles=wunsch.alles)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.warning("Senden abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "senden_abgelehnt",
                                      "einzelheit": str(fehler)})
        # Ins Betriebsprotokoll, und zwar OHNE den Betrag klein zu reden:
        # das ist der eine Vorgang dieser Anwendung, der Geld aus der Hand
        # gibt. Wer spaeter nachsieht, was passiert ist, soll ihn finden.
        log.warning("On-Chain gesendet: %s sat an %s (%s sat/vB), txid %s",
                    "alles" if wunsch.alles else betrag, adresse, satz, txid)
        return {"ok": True, "txid": txid, "satz_sat_vb": satz,
                "alles": wunsch.alles}

    # ── Einen Kanal oeffnen, und ueber Lightning zahlen ──────────────────
    #
    # Aus dem Betrieb, 12.09.2026: "ja dann machen wir mal mit Punkt 1 und 2
    # weiter." Bis hierher konnte diese Anwendung On-Chain senden -- also die
    # langsame, teure Art -- aber weder einen Kanal oeffnen noch ueber
    # Lightning zahlen, wofuer der ganze Knoten da ist.
    #
    # Beides steht hinter derselben PIN wie das Senden, und die wird ZUERST
    # geprueft. Beides gibt Geld aus der Hand.

    @api.post("/lightning/kanal/schaetzen", dependencies=geschuetzt)
    def kanal_schaetzen(wunsch: Kanalwunsch) -> Dict:
        """Was dieser Kanal kosten und was er binden wuerde. Bewegt nichts.

        KEINE PIN: hier wird gerechnet, nicht ausgegeben. Wer vor der
        Entscheidung eine PIN eintippen muss, tippt sie irgendwann
        gedankenlos -- und genau das soll sie nicht werden.
        """
        # Der Betrag ZUERST: "zu klein" ist die handfestere Auskunft, und sie
        # haengt an keiner Gebuehrenschaetzung. Andersherum bekaeme jemand
        # mit einem 5.000-sat-Wunsch waehrend des Abgleichs "keine
        # Gebuehrenschaetzung" zu lesen -- richtig und nutzlos.
        betrag = int(wunsch.betrag)
        if betrag < lnd.KANAL_MIN_SAT:
            raise HTTPException(400, {"meldung": "kanal_zu_klein",
                                      "einzelheit": str(lnd.KANAL_MIN_SAT)})
        knoten = sendbereit()
        satz = sendesatz(wunsch.tempo)
        ruecklage = lnd.ruecklage(knoten)
        try:
            guthaben = lnd.guthaben(knoten).get("kette_bestaetigt", 0)
        except (lnd.NichtErreichbar, lnd.LndFehler):
            guthaben = 0
        gebuehr = round(kennzahlen.KANAL_VBYTE * satz)
        gebraucht = betrag + gebuehr + (ruecklage or 0)
        return {
            "betrag": betrag,
            "satz_sat_vb": satz,
            "oeffnen_sat": gebuehr,
            "ruecklage_sat": ruecklage,
            "gebraucht_sat": gebraucht,
            "guthaben_sat": guthaben,
            # Die eine Zahl, die zaehlt: reicht es?
            "reicht": guthaben >= gebraucht,
            "fehlt_sat": max(0, gebraucht - guthaben),
            # Kein Riegel, eine Warnung: unterhalb dieser Groesse kann ein
            # Kanal bei hohen Ketten-Gebuehren unschliessbar werden -- und
            # was man nicht schliessen kann, kann man auch nicht gegen einen
            # Betrugsversuch verteidigen. Die Entscheidung bleibt seine.
            "knapp": betrag < lnd.KANAL_RATSAM_SAT,
            "ratsam_ab_sat": lnd.KANAL_RATSAM_SAT,
            "reserve_prozent": kennzahlen.KANAL_RESERVE_PROZENT,
        }

    @api.post("/lightning/kanal/oeffnen", dependencies=geschuetzt)
    def kanal_oeffnen(wunsch: Kanalwunsch) -> Dict:
        """Einen Kanal oeffnen. Das Geld ist danach GEBUNDEN.

        Nicht verloren -- gebunden. Es kommt erst wieder heraus, wenn der
        Kanal geschlossen wird, und das kostet ein zweites Mal Gebuehren.
        Deshalb dieselbe PIN wie beim Senden, und zuerst geprueft.
        """
        freigabe_pruefen(wunsch.pin)
        knoten = sendbereit()
        satz = sendesatz(wunsch.tempo)
        try:
            d = lnd.kanal_oeffnen(knoten, wunsch.gegenstelle, wunsch.betrag,
                                  satz, privat=wunsch.privat)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.warning("Kanal oeffnen abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "kanal_abgelehnt",
                                      "einzelheit": str(fehler)})
        # Ins Betriebsprotokoll, mit allem, was man spaeter sucht.
        log.warning("Kanal geoeffnet: %s sat zu %s (%s sat/vB), txid %s:%s",
                    wunsch.betrag, d["gegenstelle"], satz, d["txid"],
                    d["ausgang"])
        # Die Sicherung ist ab JETZT eine andere -- es gibt einen Kanal mehr.
        # Sie sofort nachzuziehen ist der halbe Sinn des Sicherungsziels.
        app.state.sicherung_nachziehen()
        return {"ok": True, "satz_sat_vb": satz, **d}

    @api.post("/lightning/gegenstelle/ansehen", dependencies=geschuetzt)
    def gegenstelle_ansehen(wunsch: Kanalwunsch) -> Dict:
        """Was der eigene Graph ueber diese Gegenstelle weiss. Bewegt nichts.

        Aus dem Betrieb, 12.09.2026: "gibt es uns die moeglichkeit einen channel den
        wir verknuepfen wollen vorher zu scannen".

        Die Auskunft kommt aus dem EIGENEN Graphen -- jeder Knoten kuendigt
        sich selbst an, unser Knoten hat es mitgehoert. Keine fremde Seite,
        kein Konto, keine Abfrage, die jemandem verraet, mit wem wir einen
        Kanal erwaegen.
        """
        knoten = sendbereit()
        try:
            return lnd.gegenstelle_ansehen(knoten, wunsch.gegenstelle)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            raise HTTPException(400, {"meldung": "gegenstelle_unlesbar",
                                      "grund": str(fehler)})

    # ── Der HTLC-Strom ───────────────────────────────────────────────────
    #
    # Ein DAUERLAEUFER, anders als alles andere hier: er wartet auf
    # Ereignisse, statt sie abzurufen. Wenn niemand zuhoert, sind sie weg --
    # LND hebt sie nicht auf.
    #
    # Deshalb mit eingebautem Wiederanlauf: reisst die Verbindung ab (LND
    # startet neu, Wallet wird gesperrt, Netz zuckt), wird gewartet und neu
    # angefangen. Wartezeit steigend, damit aus einem laenger kaputten LND
    # kein Dauerfeuer im Protokoll wird.
    HTLC_WARTE_ANFANG = 5.0
    HTLC_WARTE_MAX = 300.0
    # Ab wann ein Strom als "hat gestanden" gilt und die Wartezeit wieder von
    # vorne anfaengt. Am 17.09.2026 stand der Rueckfall VOR dem Lesen: die
    # Wartezeit wurde also schon beim Anhaengen zurueckgesetzt, und die
    # Verdopplung kam nie zum Tragen. Im Protokoll standen durchgehend fuenf
    # Sekunden, nie zehn. Anhaengen ist kein Beweis -- Stehen ist einer.
    HTLC_GESUND_SEKUNDEN = 60.0

    def htlc_sammeln() -> None:
        warte = HTLC_WARTE_ANFANG
        while not beenden.is_set():
            angefangen = time.monotonic()
            fehler: Optional[Exception] = None
            try:
                knoten = lndverbindung()
                if lnd.zustand(knoten)["stand"] != "bereit":
                    # Wallet zu oder LND startet noch. Kein Fehler -- aber
                    # auch kein Grund, ewig im Fuenf-Sekunden-Takt zu fragen.
                    # Vorher sprang der Lauf hier per "continue" an der
                    # Verdopplung vorbei; bei dem Knoten im Betrieb, der ohne
                    # Auto-Entsperren laeuft, hiess das: Dauerfrage, solange
                    # die Wallet zu ist.
                    raise lnd.Beschaeftigt("LND ist noch nicht bereit")
                log.info("HTLC-Strom: haenge mich an.")
                for zeile in lnd.htlc_strom(knoten):
                    # Beim Herunterfahren wird nichts mehr weggeschrieben:
                    # die Ablage gehoert einem Dienst, den es gleich nicht
                    # mehr gibt.
                    if beenden.is_set():
                        return
                    auswertung.htlc_merken(zeile)
                    if zeile["art"] == "link_fehl":
                        # Ins Protokoll, und zwar sichtbar: das ist der eine
                        # Fall, an dem man etwas aendern kann.
                        log.info("HTLC bei uns gescheitert: %s (rein %s, "
                                 "raus %s)", zeile["grund"],
                                 zeile["rein_kanal"], zeile["raus_kanal"])
            except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt,
                    OSError) as f:
                fehler = f
            # Ein Strom, der eine Minute gestanden hat, war gesund -- auch
            # wenn in der Zeit kein einziges Ereignis kam. Erst dann faengt
            # die Wartezeit wieder von vorne an. Riss er frueher ab,
            # verdoppelt sie sich, sonst klopft ein dauerhaft kaputtes LND
            # bis in alle Ewigkeit im selben Takt an.
            if time.monotonic() - angefangen >= HTLC_GESUND_SEKUNDEN:
                warte = HTLC_WARTE_ANFANG
            if fehler is not None:
                log.info("HTLC-Strom unterbrochen (%s) -- neuer Versuch in "
                         "%.0f s.", fehler, warte)
            beenden.wait(warte)
            warte = min(warte * 2, HTLC_WARTE_MAX)

    def htlc_anstossen() -> None:
        """Den Dauerlaeufer starten, falls er nicht laeuft.

        im_hintergrund startet keinen zweiten, solange einer lebt -- damit
        genuegt es, das hier im Takt aufzurufen.
        """
        if zustand.laden().eingerichtet:
            im_hintergrund("htlc-strom", htlc_sammeln)

    @api.get("/lightning/htlc", dependencies=geschuetzt)
    def htlc_lesen(grenze: int = 60) -> Dict:
        """Was durch diesen Knoten ging -- und was nicht.

        Die Fehlschlaege stehen dabei VORNE und getrennt. Eine Liste, in der
        Gelungenes und Gescheitertes durcheinanderlaufen, beantwortet die
        Frage nicht, die man hier hat: welcher Kanal macht Aerger?
        """
        seit = int((time.time() - 7 * 86400) * 1000)
        return {
            "ereignisse": auswertung.htlc_lesen(min(max(int(grenze), 1), 500)),
            "gruende": auswertung.htlc_gruende(seit),
            "speicher": auswertung.verfuegbar,
        }

    @api.get("/lightning/bewegungen", dependencies=geschuetzt)
    def bewegungen_lesen() -> Dict:
        """Ein- und Ausgaenge der On-Chain-Wallet, mit voller txid.

        Befund vom 15.09.2026: nach dem ersten Einzahlung stand nur eine
        Zahl im Guthaben -- keine txid, keine Bestaetigungen, kein "ist es
        angekommen?". Nur lesend (onchain:read), deshalb ohne PIN.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            return {"bereit": False, "bewegungen": [], "weitere": 0}
        try:
            d = lnd.bewegungen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            log.info("Bewegungen nicht abrufbar: %s", fehler)
            return {"bereit": True, "bewegungen": [], "weitere": 0,
                    "fehler": True}
        return {"bereit": True, **d}

    @api.get("/lightning/wachtuerme", dependencies=geschuetzt)
    def wachtuerme_lesen() -> Dict:
        """Wer unsere Kanaele bewacht -- und ob ueberhaupt jemand.

        Der Befund vom 12.09.2026: in der Konfiguration stand
        wtclient.active=true, eingetragen war aber kein einziger Turm. Der
        Schutz sah eingeschaltet aus und war es nicht. Deshalb steht die Zahl
        jetzt in der Oberflaeche statt in einer Konfigurationsdatei.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            return {"bereit": False, "tuerme": []}
        # Die eigene Turmkennung ZUERST: ohne sie laesst sich in der Liste
        # nicht erkennen, welcher Eintrag der eigene ist -- und genau der
        # darf nicht als Schutz zaehlen.
        try:
            eigener = lnd.eigener_turm(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.debug("Eigener Turm nicht abrufbar: %s", fehler)
            eigener = {"aktiv": False, "kennung": "", "uris": [],
                       "lauscht": []}
        try:
            tuerme = lnd.wachtuerme(knoten, eigener.get("kennung", ""))
            kanaele = lnd.kanaele(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            log.info("Wachtuerme nicht abrufbar: %s", fehler)
            return {"bereit": True, "tuerme": [], "fehler": str(fehler)}
        # Was die Tuerme angenommen haben. Fehlt das, fehlt eine Zahl -- ob
        # bewacht wird, sagen die Sitzungen trotzdem.
        try:
            zaehler = lnd.wachturm_zaehler(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            log.debug("Wachturm-Zaehler nicht abrufbar: %s", fehler)
            zaehler = None
        return {"bereit": True, "tuerme": tuerme, "eigener": eigener,
                "zaehler": zaehler, "kanaele": len(kanaele),
                "ungedeckt": lnd.ungedeckte_arten(kanaele, tuerme)}

    @api.post("/lightning/wachtuerme", dependencies=geschuetzt)
    def wachturm_eintragen(wunsch: Wachturm) -> Dict:
        """Einen Wachturm eintragen.

        KEINE PIN: das hier bewegt kein Geld, es schuetzt welches. Eine Huerde
        davor waere eine Huerde vor der Sicherung.

        Was der Turm bekommt, ist ein verschluesselter Strafzug je Zustand.
        Damit kann er nichts ausgeben -- nur im Betrugsfall veroeffentlichen,
        was ohnehin uns zusteht.
        """
        knoten = sendbereit()
        try:
            kennung = lnd.wachturm_eintragen(knoten, wunsch.adresse)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            raise HTTPException(400, {"meldung": "wachturm_abgelehnt",
                                      "grund": str(fehler)})
        log.info("Wachturm eingetragen: %s", kennung[:16])
        return {"ok": True, "kennung": kennung}

    @api.post("/lightning/wachtuerme/entfernen", dependencies=geschuetzt)
    def wachturm_austragen(wunsch: Wachturmaustrag) -> Dict:
        """Einen Wachturm austragen.

        Bis zum 15.09.2026 ging nur Eintragen -- mit Tuermen aus oeffentlichen
        Listen, von denen viele laengst tot sind, waechst die Liste dann
        endlos.

        KEINE PIN, aus demselben Grund wie beim Eintragen: es bewegt kein
        Geld. Die Oberflaeche fragt aber einmal nach, denn ein ausgetragener
        Turm kann der einzige gewesen sein, der die Kanaele bewacht hat.
        """
        knoten = sendbereit()
        try:
            kennung = lnd.wachturm_entfernen(knoten, wunsch.kennung)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            # Der eine Fall mit klarer Ursache (wtdb/client_db.go,
            # ErrTowerUnackedUpdates): beim Turm liegen noch Kanalstaende,
            # die er nicht bestaetigt hat. Das ist kein Fehler, sondern ein
            # "noch nicht" -- und gehoert auch so gesagt.
            if "unacked updates" in str(fehler):
                raise HTTPException(409, {"meldung": "wachturm_offene_staende"})
            raise HTTPException(400, {"meldung": "wachturm_nicht_entfernt",
                                      "grund": str(fehler)})
        log.info("Wachturm ausgetragen: %s", kennung[:16])
        return {"ok": True, "kennung": kennung}

    @api.post("/lightning/wachtuerme/pruefen", dependencies=geschuetzt)
    def wachturm_pruefen(wunsch: Wachturmaustrag) -> Dict:
        """Antwortet dieser Turm ueberhaupt noch?

        DER BEFUND VOM 17.09.2026, an dem Knoten im Betrieb. In seiner Liste standen
        vier Tuerme, bei allen stand "keine Sitzung" -- und die Oberflaeche
        konnte nicht sagen, warum. Zwei Ursachen sehen dort gleich aus:
        der Turm ist nicht erreichbar, oder LND hat schlicht noch nichts zu
        sichern. Zwei der vier waren tot, ihre .onion gab es nicht mehr; zu
        sehen war das nur im Tor-Protokoll, und auch dort nur, wenn man wusste,
        wonach man sucht.

        Hier wird es gemessen -- ueber denselben Weg, mit dem der Knoten seine
        eigene Erreichbarkeit prueft: durch Tor, von aussen, mit Tors
        erweiterten Fehlercodes. Damit unterscheidet die Antwort drei Faelle,
        die vorher alle "keine Sitzung" hiessen:

            erreichbar        der Turm nimmt an -- an LND fehlt es dann nicht
            abgelehnt         erreicht, aber niemand nimmt an
            nicht_pruefbar    der Weg kam nicht zustande (Tor hat die
                              Beschreibung nicht gefunden -- bei einer .onion
                              heisst das meist: den Dienst gibt es nicht mehr)

        KEINE PIN: es wird nur eine Verbindung aufgebaut und sofort wieder
        geschlossen. Es bewegt nichts und verraet nichts, was der Turm nicht
        ohnehin weiss -- er steht ja in der eigenen Liste.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        try:
            tuerme = lnd.wachtuerme(knoten, _eigene_turmkennung(knoten))
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht",
                                      "grund": str(fehler)})
        gesucht = (wunsch.kennung or "").strip().lower()
        turm = next((t for t in tuerme if t["kennung"] == gesucht), None)
        if turm is None:
            raise HTTPException(404, {"meldung": "wachturm_unbekannt"})

        proxy = (konf.tor_host, konf.tor_pruef_port)
        zeilen = []
        # Die Dauer dieses Aufrufs muss vorhersagbar bleiben. Eine Messung
        # ueber Tor laeuft bis zu erreichbar.ZEITLIMIT_SEKUNDEN, und ein
        # Turm darf beliebig viele Adressen tragen -- ungedeckelt waere das
        # ein Aufruf, den irgendwann jeder Browser und jeder Reverse Proxy
        # davor abbricht. Deshalb zweierlei:
        #
        #   * beim ersten Erfolg aufhoeren. Eine erreichbare Adresse
        #     beantwortet die Frage; die restlichen zu messen kostet nur Zeit.
        #   * hoechstens WACHTURM_PRUEF_HOECHSTENS Adressen anfassen.
        for eintrag in turm["adressen"][:WACHTURM_PRUEF_HOECHSTENS]:
            # Ohne Port in der Zeile gilt der Standardport eines Wachturms --
            # nicht der, den DIESER Knoten fuer seinen eigenen benutzt.
            wirt, port = erreichbar.zerlege(eintrag,
                                            onion.DIENSTE["wachturm"].port)
            zeilen.append({"eintrag": eintrag,
                           **erreichbar.pruefe_eine(wirt, port, proxy,
                                                    handschlag=False,
                                                    erweitert=True)})
            if zeilen[-1].get("erreichbar"):
                break
        log.info("Wachturm geprueft: %s -- %s", gesucht[:16],
                 ", ".join(f"{z['eintrag']}: {z.get('grund') or 'erreichbar'}"
                           for z in zeilen) or "keine Adresse")
        return {
            "kennung": gesucht,
            "eigen": bool(turm.get("eigen")),
            # Eine erreichbare Adresse genuegt: der Turm ist dann da.
            "erreichbar": any(z.get("erreichbar") for z in zeilen),
            "geprueft": any(z.get("geprueft") for z in zeilen),
            "adressen": zeilen,
        }

    @api.post("/lightning/rechnung/erstellen", dependencies=geschuetzt)
    def rechnung_erstellen(wunsch: Rechnungsanfrage) -> Dict:
        """Eine Rechnung ausstellen, um ueber Lightning zu EMPFANGEN.

        Aus dem Betrieb, 16.09.2026: "solte halt nur auch geld rein bekommen".

        Keine PIN: eine Rechnung fordert nur, sie bewegt nichts. Das
        Schwerste, was eine uebernommene Sitzung damit anrichten kann, ist
        eine Forderung, die niemand bezahlt.
        """
        knoten = sendbereit()
        try:
            d = lnd.rechnung_erstellen(knoten, wunsch.betrag, wunsch.zweck,
                                       wunsch.gueltig_min * 60)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.info("Rechnung nicht erstellt: %s", fehler)
            raise HTTPException(400, {"meldung": "rechnung_nicht_erstellt",
                                      "einzelheit": str(fehler)})
        return d

    @api.get("/lightning/rechnungen", dependencies=geschuetzt)
    def rechnungen_lesen() -> Dict:
        """Die eigenen Rechnungen und ob sie bezahlt wurden. Nur lesend."""
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            return {"bereit": False, "rechnungen": [], "weitere": 0}
        try:
            d = lnd.rechnungen(knoten)
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            log.info("Rechnungen nicht abrufbar: %s", fehler)
            return {"bereit": True, "rechnungen": [], "weitere": 0,
                    "fehler": True}
        return {"bereit": True, **d}

    @api.post("/lightning/rechnung/lesen", dependencies=geschuetzt)
    def rechnung_lesen(wunsch: Rechnungswunsch) -> Dict:
        """Was in dieser Rechnung steht. Bewegt nichts.

        Der wichtigste Schritt am ganzen Vorgang, und deshalb ein eigener:
        eine Lightning-Rechnung ist eine unleserliche Zeichenkette. Wer sie
        ohne Nachsehen bezahlt, weiss weder an wen noch wieviel.
        """
        knoten = sendbereit()
        try:
            d = lnd.rechnung_lesen(knoten, wunsch.rechnung)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            raise HTTPException(400, {"meldung": "rechnung_unlesbar",
                                      "einzelheit": str(fehler)})
        betrag = wunsch.betrag if d["offener_betrag"] else d["betrag"]
        d["gebuehrengrenze"] = lnd.gebuehrgrenze(betrag)
        d["abgelaufen"] = bool(d["laeuft_ab"]) and d["laeuft_ab"] < time.time()
        return d

    @api.post("/lightning/rechnung/zahlen", dependencies=geschuetzt)
    def rechnung_zahlen(wunsch: Rechnungswunsch) -> Dict:
        """Eine Lightning-Rechnung bezahlen. UNWIDERRUFLICH.

        NICHT wiederholen bei einem Zeitlimit. Die Zahlung ist womoeglich
        laengst unterwegs und nur die Antwort blieb aus; ein zweiter Versuch
        schickt sie ein zweites Mal. Wer hier etwas wiederholen will, sieht
        vorher in die Zahlungsliste.
        """
        freigabe_pruefen(wunsch.pin)
        knoten = sendbereit()
        # Erst lesen, dann zahlen -- damit die Grenze zu DIESER Rechnung
        # passt und nicht zu einer, die der Aufrufer behauptet hat.
        try:
            gelesen = lnd.rechnung_lesen(knoten, wunsch.rechnung)
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            raise HTTPException(400, {"meldung": "rechnung_unlesbar",
                                      "einzelheit": str(fehler)})

        betrag = int(wunsch.betrag) if gelesen["offener_betrag"] \
            else gelesen["betrag"]
        if betrag <= 0:
            raise HTTPException(400, {"meldung": "betrag_fehlt"})
        grenze = int(wunsch.gebuehrengrenze) or lnd.gebuehrgrenze(betrag)

        try:
            d = lnd.zahle(knoten, gelesen["rechnung"], grenze,
                          betrag_sat=betrag if gelesen["offener_betrag"] else 0)
        except lnd.Beschaeftigt as fehler:
            # Ein Zeitlimit ist KEIN Fehlschlag. Die Zahlung kann laufen.
            log.warning("Zahlung ohne Antwort im Zeitlimit: %s", fehler)
            raise HTTPException(504, {"meldung": "zahlung_unklar"})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.warning("Zahlung gescheitert: %s", fehler)
            raise HTTPException(400, {"meldung": "zahlung_gescheitert",
                                      "einzelheit": str(fehler)})
        log.warning("Lightning gezahlt: %s sat an %s, Gebuehr %s sat",
                    d["betrag"], gelesen["ziel"][:16], d["gebuehr"])
        return {"ok": True, "zweck": gelesen["zweck"], **d}

    @api.post("/lightning/kanal/schliessen", dependencies=geschuetzt)
    def kanal_schliessen(wunsch: Kanalschluss) -> Dict:
        """Einen Kanal schliessen.

        Aus dem Betrieb, 12.09.2026: "kann ich dann auch selber ein kanal kuendigen
        oder schliessen?"

        Bis dahin nicht -- und die Begruendung dafuer war zu kurz. Sein
        eigener Satz trifft es besser: nichts dahin ueberweisen, solange man
        es nicht zurueckschicken kann. Ein Kanal, den man aus der eigenen
        Software nicht schliessen kann, ist eine Einbahnstrasse.

        Hinter der PIN, und die zuerst. Erzwingen ist ein eigener Schalter,
        den der Aufrufer bewusst setzen muss.
        """
        freigabe_pruefen(wunsch.pin)
        knoten = sendbereit()
        # Beim Erzwingen bestimmt LND die Gebuehr selbst -- dann brauchen wir
        # auch keine Schaetzung und scheitern nicht an ihrem Fehlen.
        satz = 0 if wunsch.erzwingen else sendesatz(wunsch.tempo)
        try:
            d = lnd.kanal_schliessen(knoten, wunsch.punkt, satz,
                                     erzwingen=wunsch.erzwingen)
        except lnd.Beschaeftigt:
            raise HTTPException(504, {"meldung": "schliessen_unklar"})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.warning("Kanal schliessen abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "schliessen_abgelehnt",
                                      "einzelheit": str(fehler)})
        log.warning("Kanal %s wird %s geschlossen, txid %s", wunsch.punkt,
                    "erzwungen" if wunsch.erzwingen else "einvernehmlich",
                    d["txid"])
        # Ein Kanal weniger heisst eine andere Sicherung.
        app.state.sicherung_nachziehen()
        return {"ok": True, **d}

    @api.post("/lightning/umschichten", dependencies=geschuetzt)
    def umschichten(wunsch: Umschichtung) -> Dict:
        """Liquiditaet von einem eigenen Kanal in einen anderen schieben.

        Aus dem Betrieb, 12.09.2026: "kann ich dann mehre kanäle balancen??"

        Das Geld bleibt die ganze Zeit seins -- es wechselt nur die Seite.
        Verloren gehen kann nur die Weiterleitungsgebuehr des Rundwegs, und
        die ist gedeckelt.

        TROTZDEM HINTER DER PIN. Nicht, weil hier Geld verschwinden koennte,
        sondern weil eine uebernommene Sitzung sonst in Ruhe Gebuehren
        verbrennen koennte -- ein Umschichten nach dem anderen, jedes fuer
        sich unauffaellig.
        """
        freigabe_pruefen(wunsch.pin)
        knoten = sendbereit()
        grenze = int(wunsch.gebuehrengrenze) or lnd.gebuehrgrenze(wunsch.betrag)
        try:
            d = lnd.umschichten(knoten, wunsch.von, wunsch.nach,
                                wunsch.betrag, grenze)
        except lnd.Beschaeftigt:
            raise HTTPException(504, {"meldung": "zahlung_unklar"})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        except lnd.LndFehler as fehler:
            log.info("Umschichten gescheitert: %s", fehler)
            raise HTTPException(400, {"meldung": "umschichten_gescheitert",
                                      "einzelheit": str(fehler)})
        log.info("Umgeschichtet: %s sat, Gebuehr %s sat",
                 d["betrag"], d["gebuehr"])
        return {"ok": True, **d}

    @api.post("/lightning/gebuehren", dependencies=geschuetzt)
    def gebuehren_setzen(wahl: Gebuehren) -> Dict:
        """Was dieser Knoten fuers Weiterleiten nimmt.

        Ohne Kanalpunkt fuer alle Kanaele, mit fuer genau einen -- und das ist
        der eigentliche Betriebsgriff: teuer machen, wo ein Kanal leerlaeuft,
        billig, wo er aufgefuellt werden soll.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        if not macaroon_sicherstellen(knoten):
            raise HTTPException(503, {"meldung": "kein_macaroon"})
        try:
            lnd.setze_gebuehren(knoten, wahl.basis_msat, wahl.satz_ppm,
                                wahl.zeitsperre, wahl.kanalpunkt)
        except lnd.LndFehler as fehler:
            log.info("Gebuehren abgelehnt: %s", fehler)
            raise HTTPException(400, {"meldung": "gebuehren_abgelehnt",
                                      "einzelheit": str(fehler)})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        return {"ok": True, "fuer_alle": not wahl.kanalpunkt}

    # ------------------------------------------------- Gebuehren und das Netz
    #
    # Aus dem Betrieb, 18.09.2026: "koennten wir hier im gebueren feld irgendwie
    # immer mal so den durchschnitt anzeigen lassen der letzten 4 wochen ..
    # oder das ganze irgendwie automatisieren das wir entweder immer den netz
    # durchschnitt als gebueren nehemen und der sich automatisch anpasst am
    # netz". Und auf die Rueckfrage, ob stufenweise: "wenn dann 100% und alle
    # 3 Stufen gemeinsam! Obergrenze ist max wert der letzten 4 wochen und
    # untergrenze ist dann min wert der letzten 4 wochen fuer die automatik ..
    # die 4 wochen sind ja auch nicht fest sondern aendern sich ja mit".
    #
    # Drei Stufen, und sie bauen aufeinander auf:
    #   1. messen, was das Netz nimmt -- taeglich, aus dem eigenen Graphen
    #   2. die Messungen aufheben, daraus wird nach vier Wochen ein Band
    #   3. den eigenen Satz darin nachfuehren -- auf Ansage, nicht von selbst
    # "versucht" ist None, solange es noch keinen Versuch gab -- und NICHT
    # 0.0. Der Unterschied ist derselbe wie beim Zeitlimit am 17.09.2026:
    # time.monotonic() zaehlt ab dem Systemstart, also ist 0.0 ein echter,
    # erreichbarer Zeitpunkt und kein "nie". Auf einer Maschine, die seit
    # weniger als einer Stunde laeuft, hiesse 0.0 damit "gerade eben erst
    # versucht" -- und gemessen wuerde gar nicht.
    #
    # Gefunden hat das die CI, nicht der Entwicklungsrechner: der lief seit
    # 26 Stunden, dort greift die Sperre nie. Ein frisch gestarteter Laeufer
    # ist Minuten alt. Genau so waere es nach jedem NAS-Neustart gewesen:
    # eine Stunde lang keine Messung, ohne ein Wort im Protokoll.
    gebuehrenstand: Dict[str, Any] = {"laeuft": False, "versucht": None,
                                      "fehler": ""}

    # Schlaegt eine Messung fehl, wird nicht alle zehn Minuten wieder der
    # ganze Netzgraph angefordert. Einmal die Stunde reicht.
    GEBUEHREN_WIEDERHOLUNG_SEKUNDEN = 3600.0

    def _netzgebuehren_messen() -> Dict[str, Any]:
        """Einmal den Graphen lesen und den heutigen Tag festhalten.

        Laeuft NUR, wenn LNDs Netzkarte vollstaendig ist. Ein Knoten, der
        gerade erst hochgefahren ist, kennt ein paar hundert Kanaele statt
        dreissigtausend -- ein Median daraus waere eine Zahl ohne Deckung,
        und er landete in der Messreihe, wo er wochenlang das Band verzerrt.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        ueber = lnd.uebersicht(knoten)
        if not ueber.get("graph_aktuell"):
            raise HTTPException(409, {"meldung": "graph_nicht_aktuell"})
        werte = netzgebuehren.messen(knoten, ueber.get("kennung", ""))
        if werte.get("median_ppm") is None:
            raise HTTPException(409, {"meldung": "graph_leer"})
        tag = netzgebuehren.heute()
        auswertung.netzgebuehren_merken(tag, int(time.time()), werte)
        auswertung.netzgebuehren_aufraeumen()
        log.info("Netzgebuehren gemessen: Median %s ppm aus %s Linien in "
                 "%s Kanaelen.", werte["median_ppm"], werte["linien"],
                 werte["kanaele"])
        return {"tag": tag, **werte}

    def _gebuehrenlage() -> Dict[str, Any]:
        """Was gemessen wurde, was das Band sagt -- und was die Automatik taete.

        Der Vorschlag steht hier auch dann, wenn die Automatik AUS ist. Man
        soll sehen koennen, was sie taete, bevor man sie einschaltet; ein
        Schalter, hinter dem eine Ueberraschung wartet, gehoert nicht an
        einen Knoten, auf dem Geld liegt.
        """
        verlauf = auswertung.netzgebuehren_verlauf(netzgebuehren.FENSTER_TAGE)
        heute = netzgebuehren.heute()
        heutige = next((z for z in verlauf if z.get("tag") == heute), None)
        grenzen = netzgebuehren.band(verlauf, ohne_tag=heute)
        wahl = zustand.laden().gebuehrenwahl or {}
        # WAS GILT GERADE? Zwei Quellen, und die Reihenfolge entscheidet.
        #
        # Die Messung liest aus dem Graphen, was das Netz von uns sieht --
        # das ist die ehrlichere Zahl, denn sie stammt nicht aus unserer
        # eigenen Erinnerung. Sie ist aber von HEUTE FRUEH: hat die Automatik
        # seitdem gesetzt, ist sie ueberholt. Ohne diese Reihenfolge stuende
        # in der Oberflaeche direkt nach dem Setzen "wuerde jetzt X setzen" --
        # fuer genau den Wert, der eine Sekunde vorher gesetzt wurde.
        if wahl.get("zuletzt_am") == heute and wahl.get("zuletzt_ppm") is not None:
            jetzt = wahl.get("zuletzt_ppm")
        else:
            jetzt = (heutige or {}).get("eigen_ppm")
            if jetzt is None:
                jetzt = wahl.get("zuletzt_ppm")
        rat = netzgebuehren.vorschlag((heutige or {}).get("median_ppm"),
                                      grenzen, jetzt)
        return {
            "heute": heutige,
            "band": grenzen,
            "vorschlag": rat,
            "jetzt_ppm": jetzt,
            "automatik": bool(wahl.get("automatik")),
            "zuletzt": {k: wahl.get(k) for k in
                        ("zuletzt_ppm", "zuletzt_am", "zuletzt_grund")},
            "verlauf": [{"tag": z.get("tag"), "median_ppm": z.get("median_ppm"),
                         "eigen_ppm": z.get("eigen_ppm")} for z in verlauf],
            "fenster_tage": netzgebuehren.FENSTER_TAGE,
            "braucht_tage": netzgebuehren.MINDESTENS_TAGE,
            "misst_gerade": bool(gebuehrenstand["laeuft"]),
            "fehler": gebuehrenstand["fehler"],
        }

    def _gebuehren_nachziehen() -> Dict[str, Any]:
        """Die Automatik EINMAL anwenden -- wenn sie darf.

        Sie fasst ausschliesslich den Satz an, nie die Grundgebuehr, und sie
        setzt ihn fuer ALLE Kanaele. Einzelne Kanaele nach Liquiditaets-
        richtung zu steuern ist etwas anderes und bleibt Handarbeit: dafuer
        braucht es den HTLC-Strom und nicht den Netz-Median.
        """
        lage = _gebuehrenlage()
        if not lage["automatik"]:
            return {"getan": False, "grund": "aus"}
        rat = lage["vorschlag"]
        if not rat.get("handeln"):
            return {"getan": False, "grund": rat.get("grund")}
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            return {"getan": False, "grund": "lightning_nicht_bereit"}
        if not macaroon_sicherstellen(knoten):
            return {"getan": False, "grund": "kein_macaroon"}
        # Ohne Kanaele gibt es nichts zu setzen. LND wuerde den Aufruf
        # klaglos annehmen und nichts tun -- und in der Oberflaeche staende
        # "gesetzt", wo nichts gesetzt wurde.
        if not lnd.kanaele(knoten):
            return {"getan": False, "grund": "keine_kanaele"}
        wahl = dict(zustand.laden().gebuehrenwahl or {})
        basis = int(wahl.get("basis_msat") or 0)
        lnd.setze_gebuehren(knoten, basis, int(rat["satz_ppm"]))
        wahl.update({"zuletzt_ppm": int(rat["satz_ppm"]),
                     "zuletzt_am": netzgebuehren.heute(),
                     "zuletzt_grund": rat.get("grund")})
        zustand.merke_gebuehrenwahl(wahl)
        log.info("Gebuehrenautomatik: Satz auf %s ppm gesetzt (%s, Band "
                 "%s-%s ppm aus %s Tagen).", rat["satz_ppm"],
                 rat.get("grund"), lage["band"].get("unten_ppm"),
                 lage["band"].get("oben_ppm"), lage["band"].get("tage"))
        return {"getan": True, "satz_ppm": int(rat["satz_ppm"]),
                "grund": rat.get("grund")}

    def gebuehren_wenn_faellig() -> None:
        """Einmal am Tag messen -- und danach die Automatik anwenden.

        "Einmal am Tag" haengt an der Messreihe selbst, nicht an einer Uhr im
        Arbeitsspeicher: liegt fuer heute schon eine Zeile, ist nichts zu
        tun. Damit ueberlebt der Takt jeden Neustart der Anwendung, ohne dass
        ein Datum irgendwo mitgeschrieben werden muesste.
        """
        if gebuehrenstand["laeuft"]:
            return
        letzte = auswertung.netzgebuehren_verlauf(1)
        if letzte and letzte[0].get("tag") == netzgebuehren.heute():
            return
        jetzt = time.monotonic()
        vorher = gebuehrenstand["versucht"]
        if vorher is not None and jetzt - vorher < GEBUEHREN_WIEDERHOLUNG_SEKUNDEN:
            return
        gebuehrenstand["versucht"] = jetzt

        def arbeit() -> None:
            gebuehrenstand["laeuft"] = True
            try:
                _netzgebuehren_messen()
                gebuehrenstand["fehler"] = ""
                _gebuehren_nachziehen()
            except HTTPException as fehler:
                grund = fehler.detail
                gebuehrenstand["fehler"] = (grund or {}).get("meldung", "") \
                    if isinstance(grund, dict) else str(grund)
                log.info("Netzgebuehren noch nicht messbar: %s",
                         gebuehrenstand["fehler"])
            except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt,
                    netzgebuehren.GraphZuGross,
                    netzgebuehren.GraphAbgerissen) as fehler:
                gebuehrenstand["fehler"] = "messung_fehlgeschlagen"
                log.info("Netzgebuehren nicht gemessen: %s", fehler)
            finally:
                gebuehrenstand["laeuft"] = False

        im_hintergrund("netzgebuehren", arbeit)

    app.state.gebuehren_wenn_faellig = gebuehren_wenn_faellig

    @api.get("/lightning/netzgebuehren", dependencies=geschuetzt)
    def netzgebuehren_lesen() -> Dict:
        """Was das Netz nimmt, was es vier Wochen lang nahm, und was folgt."""
        return _gebuehrenlage()

    @api.post("/lightning/netzgebuehren/messen", dependencies=geschuetzt)
    def netzgebuehren_messen_jetzt() -> Dict:
        """Jetzt nachsehen, statt auf den taeglichen Durchgang zu warten.

        Der Graph ist zweistellige Megabyte und LND braucht dafuer Zeit --
        das gehoert nicht in eine Anfrage, die der Browser offenhaelt.
        Deshalb im Hintergrund; die Oberflaeche fragt danach nach.
        """
        if gebuehrenstand["laeuft"]:
            return {"laeuft": True, "gestartet": False}

        def arbeit() -> None:
            gebuehrenstand["laeuft"] = True
            try:
                _netzgebuehren_messen()
                gebuehrenstand["fehler"] = ""
                _gebuehren_nachziehen()
            except HTTPException as fehler:
                grund = fehler.detail
                gebuehrenstand["fehler"] = (grund or {}).get("meldung", "") \
                    if isinstance(grund, dict) else str(grund)
            except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt,
                    netzgebuehren.GraphZuGross,
                    netzgebuehren.GraphAbgerissen) as fehler:
                gebuehrenstand["fehler"] = "messung_fehlgeschlagen"
                log.info("Netzgebuehren nicht gemessen: %s", fehler)
            finally:
                gebuehrenstand["laeuft"] = False

        gestartet = im_hintergrund("netzgebuehren", arbeit)
        return {"laeuft": True, "gestartet": gestartet}

    @api.post("/lightning/gebuehrenautomatik", dependencies=geschuetzt)
    def gebuehrenautomatik_setzen(wunsch: Gebuehrenautomatik) -> Dict:
        """Ein- oder ausschalten -- und beim Einschalten gleich anwenden.

        Sofort anwenden, weil der Vorschlag daneben steht: wer den Schalter
        umlegt, hat die Zahl gesehen, die dabei herauskommt. Ein Schalter,
        nach dem bis zum naechsten Tag nichts passiert, sieht dagegen aus wie
        einer, der nicht funktioniert.
        """
        wahl = dict(zustand.laden().gebuehrenwahl or {})
        wahl["automatik"] = bool(wunsch.automatik)
        zustand.merke_gebuehrenwahl(wahl)
        log.info("Gebuehrenautomatik %s.",
                 "eingeschaltet" if wunsch.automatik else "ausgeschaltet")
        getan: Dict[str, Any] = {"getan": False, "grund": "aus"}
        if wunsch.automatik:
            try:
                getan = _gebuehren_nachziehen()
            except (lnd.NichtErreichbar, lnd.LndFehler,
                    lnd.Beschaeftigt) as fehler:
                log.info("Automatik konnte nicht gleich greifen: %s", fehler)
                getan = {"getan": False, "grund": "lnd_antwortet_nicht"}
        return {"ok": True, "automatik": bool(wunsch.automatik), **getan}

    # Laeuft gerade ein Neustart oder eine Tilgung? Zwei gleichzeitig waeren
    # ein Wettlauf um dieselben Dateien.
    wallet_arbeit = {"laeuft": False}

    def _lnd_neu_starten(danach=None) -> None:
        """Freigabe zuruecknehmen, warten bis LND weg ist, wieder freigeben.

        Der Weg ueber die Freigabemarke ist derselbe, den die Anwendung
        ueberall nutzt -- ohne Docker-Socket. Der Waechter im Startskript
        sieht die fehlende Marke, beendet den Dienst SAUBER, und
        `restart: unless-stopped` startet ihn wieder, sobald sie da ist.

        `danach` laeuft, waehrend LND garantiert nicht laeuft. Genau dort
        gehoert das Loeschen hin: an einer laufenden Kanal-Datenbank
        herumzuloeschen waere der sichere Weg in eine kaputte.
        """
        # LAUT ins Protokoll, jeden Schritt. Aus dem Betrieb, 11.09.2026: "also
        # hier passiert nix wenn ich auf wallet sperren druecke" -- und das
        # Protokoll schwieg dazu genauso wie der Bildschirm. Ein Vorgang, der
        # bis zu neunzig Sekunden dauern darf und dabei keine Spur
        # hinterlaesst, ist nicht nachpruefbar.
        angefangen = time.monotonic()
        try:
            log.warning("Sperre LND: Freigabe wird zurueckgenommen. Der "
                        "Waechter im Container beendet den Dienst, danach "
                        "startet er neu und die Wallet ist zu.")
            ablage.sperre("lnd")
            ende = angefangen + WALLET_NEUSTART_FRIST
            while time.monotonic() < ende:
                if lnd.zustand(lndverbindung())["stand"] == "aus":
                    log.warning("LND ist nach %.0f s weg.",
                                time.monotonic() - angefangen)
                    break
                time.sleep(1.0)
            else:
                log.error("LND war nach %.0f s IMMER NOCH da -- nicht "
                          "angefasst. Laeuft im lnd-Container das Startskript "
                          "mit dem Waechter? Es meldet sonst 'Freigabe "
                          "zurueckgenommen' im Protokoll.",
                          WALLET_NEUSTART_FRIST)
                return
            if danach is not None:
                danach()
        finally:
            # Was auch schiefgeht: die Freigabe kommt zurueck. Ohne sie
            # bliebe Lightning fuer immer aus, und niemand wuesste warum.
            ablage.gib_frei("lnd")
            wallet_arbeit["laeuft"] = False
            log.warning("Freigabe fuer LND zurueckgegeben nach %.0f s -- es "
                        "startet jetzt wieder.", time.monotonic() - angefangen)

    def _wallet_arbeit_starten(danach=None) -> None:
        wallet_arbeit["laeuft"] = True
        threading.Thread(target=lambda: _lnd_neu_starten(danach),
                         name="lnd-neustart", daemon=True).start()

    @api.post("/lightning/wallet/sperren", dependencies=geschuetzt)
    def wallet_sperren() -> Dict:
        """LND neu starten, damit die Wallet zufaellt.

        Es gibt bei LND keinen Aufruf "sperre dich". Gesperrt ist sie nach
        einem Neustart -- und genau den macht das hier.
        """
        if wallet_arbeit["laeuft"]:
            raise HTTPException(409, {"meldung": "wallet_arbeit_laeuft"})
        if lnd.passwortdatei(konf.fast).exists():
            # Mit Auto-Entsperren entsperrt LND sich beim Start selbst --
            # der Neustart brraechte nichts.
            raise HTTPException(409, {"meldung": "auto_entsperren_an"})
        # UND DAS GEMERKTE PASSWORT VERGESSEN. Ohne diese Zeile haette der
        # Weg "merken" den Nutzer bekaempft: er sperrt die Wallet absichtlich
        # zu -- um sie zu loeschen oder den Entsperrweg zu wechseln -- und
        # der Sammler macht sie binnen zwanzig Sekunden von allein wieder
        # auf. Ein ausdruecklicher Handgriff schlaegt eine Bequemlichkeit.
        walletmerker.vergiss()
        _wallet_arbeit_starten()
        return {"ok": True, "laeuft": True}

    @api.post("/lightning/wallet/loeschen", dependencies=geschuetzt)
    def wallet_loeschen(wahl: Wallettilgung) -> Dict:
        """Die Wallet tilgen -- und dabei beweisen, dass man sie besitzt.

        Aus dem Betrieb, 09.09.2026: "mach es dann moeglich ein wallet zu loeschen
        mit dem wallet passwort zum entsperren ... dann kann ich die ganze
        initialisierung nochmal machen und testen."

        Sein Riegel ist der richtige, und er verlangt einen Umweg: LND kann
        sein Wallet-Passwort NUR beim Entsperren pruefen, also nur an einer
        gesperrten Wallet. Ein Passwortfeld, das nichts prueft, waere eine
        Attrappe -- deshalb muss die Wallet vorher zu sein, und deshalb gibt
        es den Knopf zum Sperren daneben.
        """
        if wallet_arbeit["laeuft"]:
            raise HTTPException(409, {"meldung": "wallet_arbeit_laeuft"})
        # ZUERST die PIN, vor jeder anderen Pruefung. Wer sie nicht hat, soll
        # nicht erst erfahren, ob sein Wallet-Passwort stimmt.
        freigabe_pruefen(wahl.pin)
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)["stand"]
        if stand != "gesperrt":
            # Kein Loeschen ohne Beweis. Die Oberflaeche bietet daneben den
            # Knopf an, der genau diesen Zustand herstellt.
            raise HTTPException(409, {"meldung": "wallet_erst_sperren",
                                      "stand": stand})
        wahl_alias = (zustand.laden().knotenwahl or {}).get(
            "lightning_alias") or nodeconfig.ALIAS_VORGABE
        if (wahl.alias or "").strip() != wahl_alias:
            raise HTTPException(400, {"meldung": "alias_stimmt_nicht",
                                      "erwartet": wahl_alias})
        try:
            # DAS ist die Pruefung: LND selbst entscheidet, ob das Passwort
            # stimmt. Wir vergleichen nichts, was wir selbst abgelegt haben.
            lnd.entsperre(knoten, wahl.passwort)
        except lnd.LndFehler:
            raise HTTPException(400, {"meldung": "passwort_falsch"})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})

        def tilgen() -> None:
            lnd.loesche_wallet(Path(konf.fast) / "lnd")
            # Das Versprechen "eine NEUE Onion-Adresse" hing bis 0.62.0 daran,
            # dass LND seinen Schluessel im eigenen Verzeichnis ablegte. Seit
            # Tor die Dienste haelt, liegen sie unter /fast/tor -- sie bleiben
            # sonst stehen, und die neue Wallet traete unter der alten
            # Adresse auf. Wer neu anfaengt, soll nicht mit dem alten Knoten
            # in Verbindung zu bringen sein.
            lightning_onions_erneuern()
            log.warning("Wallet geloescht -- LND faengt bei NON_EXISTING an. "
                        "Der Knoten bekommt eine NEUE Onion-Adresse.")

        _wallet_arbeit_starten(tilgen)
        return {"ok": True, "laeuft": True}

    @api.post("/lightning/verbinden", dependencies=geschuetzt)
    def gegenstelle_verbinden(wahl: Gegenstellenwahl) -> Dict:
        """Sich mit einer Gegenstelle verbinden -- ohne Kanal, ohne Geld.

        Aus dem Betrieb, 09.09.2026: "man will sich ja nicht nur ein kanal oder
        knoten erstellen sondern sich auch einen anschliessen."

        Das Recht dafuer (peers:write) lag seit jeher im Macaroon, mit
        Kommentar und allem -- benutzt hat es nie jemand. Entweder bauen oder
        streichen; hier ist das Bauen.

        Was es NICHT tut: einen Kanal oeffnen. Dafuer braeuchte es
        onchain:write, und das haelt diese Anwendung ausdruecklich nicht.
        """
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lightning_nicht_bereit"})
        if not macaroon_sicherstellen(knoten):
            raise HTTPException(503, {"meldung": "kein_macaroon"})
        try:
            # Derselbe Weg wie beim Kanaloeffnen: fehlt die Adresse, wird
            # sie im eigenen Graphen nachgeschlagen. Drei Knoepfe, ein
            # Verhalten -- sonst haette "Nur verbinden" wieder seine eigene
            # Kante, und genau die ist gerade weggefallen.
            lnd.verbinde_gegenstelle(knoten, wahl.adresse)
        except lnd.LndFehler as fehler:
            # Eine unbrauchbare Eingabe ist etwas anderes als ein Ausfall --
            # und der Unterschied gehoert in die Antwort, sonst sucht der
            # Nutzer den Fehler an der falschen Stelle.
            log.info("Verbinden nicht moeglich: %s", fehler)
            raise HTTPException(400, {"meldung": "gegenstelle_abgelehnt",
                                      "grund": str(fehler)})
        except lnd.NichtErreichbar:
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        return {"ok": True}

    @api.get("/lightning/name", dependencies=geschuetzt)
    def knotenname_lesen() -> Dict:
        wahl = zustand.laden().knotenwahl or {}
        return {"alias": wahl.get("lightning_alias")
                or nodeconfig.ALIAS_VORGABE,
                "farbe": wahl.get("lightning_farbe")
                or nodeconfig.FARBE_VORGABE,
                "vorgabe": nodeconfig.ALIAS_VORGABE,
                "hoechstens_byte": nodeconfig.ALIAS_MAX_BYTE,
                "minchansize": wahl.get("lightning_minchansize")
                or nodeconfig.MINCHANSIZE_VORGABE,
                "minchansize_vorgabe": nodeconfig.MINCHANSIZE_VORGABE,
                "minchansize_min": nodeconfig.MINCHANSIZE_MIN,
                "minchansize_max": nodeconfig.MINCHANSIZE_MAX}

    @api.post("/lightning/name", dependencies=geschuetzt)
    def knotenname_setzen(wahl: Knotenname) -> Dict:
        """Alias und Farbe -- das sichtbare "ich bin dabei".

        Bis zum 09.09.2026 gab es dafuer kein einziges Eingabefeld. Der
        Knoten hiess "SatoshiCortex" und die Farbe war das Bitcoin-Orange,
        beide fest verdrahtet. Fuer der Betreiber war sein Knoten damit im Netz
        nicht von einem fremden zu unterscheiden -- und ein Name, den man
        wiedererkennt, ist die Voraussetzung dafuer, dass jemand einen Kanal
        zu einem aufmacht.
        """
        e = zustand.laden()
        bisher = dict(e.knotenwahl or {})
        try:
            alias = nodeconfig.pruefe_alias(
                wahl.alias or nodeconfig.ALIAS_VORGABE)
            farbe = nodeconfig.pruefe_farbe(
                wahl.farbe or nodeconfig.FARBE_VORGABE)
        except ValueError:
            raise HTTPException(400, {"meldung": "name_ungueltig",
                                      "hoechstens_byte":
                                      nodeconfig.ALIAS_MAX_BYTE})
        # Null heisst "nicht mitgeschickt": dann bleibt stehen, was steht.
        gewuenscht = int(wahl.minchansize) or bisher.get(
            "lightning_minchansize") or nodeconfig.MINCHANSIZE_VORGABE
        try:
            minchansize = nodeconfig.pruefe_minchansize(gewuenscht)
        except ValueError as fehler:
            raise HTTPException(400, {
                "meldung": "minchansize_ungueltig",
                "einzelheit": str(fehler),
                "min": nodeconfig.MINCHANSIZE_MIN,
                "max": nodeconfig.MINCHANSIZE_MAX})
        neu = dict(bisher)
        neu.update(lightning_alias=alias, lightning_farbe=farbe,
                   lightning_minchansize=minchansize)
        zustand.merke_knotenwahl(neu)
        # Und in die Datei. Ohne diesen Schritt stuende der neue Name im
        # Zustand und der alte weiter im Graphen -- genau die Sorte
        # Halbherzigkeit, die Befund 9 ausgemacht hat.
        wege = _nach_sichtbarkeit(_wege(neu))
        adressen = nodeconfig.lies_lnd_adressen(ablage.lies("lnd") or "")
        geaendert = lightning_conf_nachziehen(wege, list(adressen))
        return {"ok": True, "alias": alias, "farbe": farbe,
                "minchansize": minchansize,
                # LND startet dabei neu, und bei abgeschaltetem
                # Auto-Entsperren ist die Wallet danach zu. Das darf die
                # Oberflaeche sagen, BEVOR jemand speichert.
                "lightning_neustart": geaendert}

    @api.post("/lightning/unterschrift", dependencies=geschuetzt)
    def unterschrift_leisten(wahl: Unterschriftswahl) -> Dict:
        """Einen vorgegebenen Text mit dem Knotenschluessel unterschreiben.

        Der Ausweis gegenueber Stellen wie LightningNetwork+: sie geben einen
        Text vor, man unterschreibt ihn, und damit ist bewiesen, dass einem
        der Knoten gehoert. Es bewegt kein Geld und gibt keinen Schluessel
        preis -- deshalb darf die Anwendung es.
        """
        # Zuerst das Offensichtliche, und zwar mit dem richtigen Grund. Ohne
        # diese Zeile lief ein leerer Text in denselben Fehler wie ein
        # abgestuerztes LND und meldete "antwortet nicht" -- eine Auskunft,
        # die in die falsche Richtung schickt.
        if not wahl.text.strip():
            raise HTTPException(400, {"meldung": "unt_leer"})
        knoten = lndverbindung()
        if lnd.zustand(knoten)["stand"] != "bereit":
            raise HTTPException(409, {"meldung": "lnd_nicht_bereit"})
        if not macaroon_sicherstellen(knoten):
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})
        try:
            unterschrift = lnd.unterschreibe(knoten, wahl.text)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.info("Unterschrift nicht moeglich: %s", fehler)
            raise HTTPException(503, {"meldung": "lnd_antwortet_nicht"})

        # Und gleich nachrechnen lassen. Vorher kam eine Zeichenkette
        # zurueck, und man sah ihr die RICHTIGKEIT nicht an -- nur die Form.
        # Die eigentliche Probe ist der Schluessel, den LND dabei nennt: er
        # muss der eigene Knotenschluessel sein. Steht dort ein anderer,
        # stimmt etwas Grundsaetzliches nicht.
        #
        # Scheitert die Pruefung selbst, ist das kein Grund, die Unterschrift
        # zurueckzuhalten: sie ist erzeugt, und der Nutzer braucht sie. Dann
        # steht eben "nicht nachgeprueft" daneben statt einer Behauptung.
        geprueft = None
        try:
            ergebnis = lnd.pruefe_unterschrift(knoten, wahl.text, unterschrift)
            eigen = lnd.uebersicht(knoten).get("kennung", "")
            geprueft = bool(ergebnis["gueltig"]
                            and eigen and ergebnis["kennung"] == eigen)
        except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
            log.info("Unterschrift nicht nachpruefbar: %s", fehler)
        return {"unterschrift": unterschrift, "geprueft": geprueft}

    # Der letzte Stand aus getinfo. Siehe die Begruendung unten im Endpunkt.
    knotenstand: Dict[str, Any] = {"wert": None, "zeit": 0.0}

    def ausweis_pruefen(antwort: Dict) -> None:
        """Ist das noch derselbe Knoten wie vorher?

        DER BEFUND VOM 11.09.2026. Der Betreiber hatte die Wiederherstellung aus
        seinen vierundzwanzig Woertern durch und fragte hinterher: "keine
        ahnung habe mir die kennung nicht vorher angesehen .. oder muss ich
        alles noch mal neu machen weil ich die kennung nicht hatte?"

        Musste er nicht -- aber dass er sie sich von Hand haette notieren
        sollen, war unser Versaeumnis. Die Anwendung kennt die Kennung
        ohnehin, und sie kann die Frage selbst beantworten.

        Die Kennung ist KEIN Geheimnis: sie ist der oeffentliche Schluessel
        dieses Knotens, im ganzen Lightning-Netz bekannt. Sie festzuhalten
        gibt nichts preis, was nicht ohnehin offen liegt.

        UEBERSCHRIEBEN WIRD NICHTS. Genau der Wechsel ist die Auskunft:
        nach einer Wiederherstellung MUSS dieselbe Kennung herauskommen,
        nach einer neu angelegten Wallet eine andere. Beides gehoert
        gesagt, nicht stillschweigend geglaettet.
        """
        kennung = (antwort.get("knoten") or {}).get("kennung") or ""
        if not kennung:
            return
        gemerkt = (zustand.laden().knotenausweis or {}).get("kennung") or ""
        if not gemerkt:
            zustand.merke_knotenausweis(kennung)
            return
        if gemerkt != kennung:
            antwort["kennung_vorher"] = gemerkt

    @api.post("/lightning/kennung/uebernehmen", dependencies=geschuetzt)
    def kennung_uebernehmen() -> Dict:
        """Die neue Kennung als die richtige festhalten.

        Der bewusste Handgriff nach einer neu angelegten Wallet: ja, das ist
        jetzt ein anderer Knoten, und das war Absicht. Ohne ihn stuende der
        Hinweis fuer immer da -- und ein Hinweis, den man nicht wegbekommt,
        wird nach drei Tagen nicht mehr gelesen.
        """
        stand = knotenstand["wert"] or {}
        kennung = stand.get("kennung") or ""
        if not kennung:
            raise HTTPException(409, {"meldung": "keine_kennung"})
        zustand.merke_knotenausweis(kennung)
        log.warning("Neue Knotenkennung uebernommen: %s", kennung)
        return {"ok": True, "kennung": kennung}

    @api.get("/lightning/kanaele", dependencies=geschuetzt)
    def lightning_kanaele() -> Dict:
        """Kanaele, Guthaben und Weiterleitungen -- in EINER Antwort.

        Vier Aufrufe an LND, aber nur einer an uns. Die Oberflaeche fragt im
        Takt nach; vier getrennte Endpunkte waeren vier Runden ueber das Netz
        fuer eine Ansicht, die als Ganzes gelesen wird.

        Faellt einer der vier aus, fehlt genau der -- der Rest steht trotzdem
        da. Eine Ansicht, die wegen der Weiterleitungsstatistik auch die
        Kanalliste verschweigt, waere schlechter als eine unvollstaendige.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}
        knoten = lndverbindung()
        stand = lnd.zustand(knoten)
        antwort: Dict = {"eingerichtet": True, "stand": stand["stand"]}
        # Die gewaehlte Betriebsart gehoert mit in die Antwort.
        #
        # Aus dem Betrieb, 10.09.2026: "unter knoten bekomme ich aber keine
        # verbindungs adresse angezeigt oder dauert das nur ewig?" -- und im
        # Bild darauf ein leerer Kasten ohne ein Wort dazu.
        #
        # Die Anwendung WEISS die Antwort: bei "gar nicht ankuendigen" steht
        # dort nie etwas und das ist kein Fehler, bei "nur ueber Tor" entsteht
        # die Onion-Adresse erst beim Start, und bei "Tor und Clearnet" fehlt
        # dann schlicht die eigene Adresse. Drei verschiedene Lagen, drei
        # verschiedene naechste Schritte -- und die Oberflaeche zeigte fuer
        # alle drei dasselbe Nichts.
        antwort["sichtbarkeit"] = _sichtbarkeit_von(
            zustand.laden().knotenwahl or {})

        def kosten_dazu(guthaben_sat: int = 0,
                        ruecklage_sat: Optional[int] = None) -> None:
            """Was ein Kanal an On-Chain-Gebuehren kostet.

            Haengt an bitcoind, NICHT an LND -- und gehoert deshalb auch dann
            in die Antwort, wenn Lightning noch gar nicht eingerichtet ist.
            Genau dann plant man ja seinen ersten Kanal und will wissen, ob
            der Zeitpunkt taugt.

            Die Einordnung ("guenstig oder teuer") kommt aus der eigenen
            Kette und braucht LND ebenfalls nicht. Die Anker-Ruecklage schon
            -- sie faellt weg, solange es keinen laufenden Knoten gibt.
            """
            k = kennzahlen.kanalkosten(
                (kennzahlen_stand["wert"] or {}).get("gebuehren") or {},
                guthaben_sat,
                verlauf=verlauf_stand["wert"],
                ruecklage_sat=ruecklage_sat)
            if k:
                antwort["kanalkosten"] = k

        if stand["stand"] != "bereit":
            kosten_dazu()
            return antwort

        for name, holen in (("knoten", lambda: lnd.uebersicht(knoten)),
                            ("guthaben", lambda: lnd.guthaben(knoten)),
                            ("kanaele", lambda: lnd.kanaele(knoten)),
                            ("netz", lambda: lnd.netzgraph(knoten)),
                            ("weiterleitungen", lambda: lnd.weiterleitungen(knoten))):
            try:
                antwort[name] = holen()
            except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
                log.info("Lightning: %s nicht abrufbar (%s)", name, fehler)

        # Die Leitungen -- nur zusammen mit der Kanalliste. Ohne sie stuende
        # jede Verbindung als "ohne Kanal" da, und genau diese Verwechslung
        # von Verbindung und Kanal soll hier weg.
        if antwort.get("kanaele") is not None:
            try:
                antwort["verbindungen"] = lnd.verbindungen(
                    knoten, antwort["kanaele"])
            except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
                log.info("Lightning: verbindungen nicht abrufbar (%s)", fehler)

        # DER LETZTE BEKANNTE STAND, wenn getinfo gerade nicht antwortet.
        #
        # Aus dem Betrieb, 11.09.2026: "aber es wird mir noch keine verbindungs
        # adresse angezeigt". Sie steckt in getinfo -- und genau das lief
        # waehrend der Wiederherstellung ins Zeitlimit, weil LNDs Wallet die
        # Kette durchsuchte. Fiel das Feld weg, zeichnete die Oberflaeche den
        # Adresskasten GAR NICHT neu: er blieb leer, ohne ein Wort dazu.
        #
        # Derselbe Griff wie bei der Kettenlage (lage_ohne_warten): lieber
        # der letzte bekannte Wert mit dem Hinweis, dass er von vorhin ist,
        # als eine leere Flaeche. Die Alternative waere kein besserer Wert,
        # sondern gar keiner.
        if antwort.get("knoten"):
            knotenstand.update(wert=antwort["knoten"], zeit=time.time())
            ausweis_pruefen(antwort)
        elif knotenstand["wert"]:
            antwort["knoten"] = knotenstand["wert"]
            antwort["knoten_veraltet"] = True
        else:
            # Noch nie eine Antwort gehabt. Dann wenigstens sagen, DASS
            # gerade niemand antwortet -- die Oberflaeche behauptet sonst
            # nichts und zeigt nichts.
            antwort["knoten_beschaeftigt"] = True

        # DIE RESERVE, aufsummiert. Sie steht in der Kanalliste und nicht in
        # /v1/balance/channels -- LND fuehrt sie je Kanal, nicht als Summe.
        #
        # Nachgelesen bei lightningnode.info, nachdem der Betreiber die Seite
        # geschickt hat: jeder Kanal haelt auf beiden Seiten ein Prozent
        # zurueck. local_balance enthaelt es, ausgeben kann man es nicht.
        # Die Oberflaeche zeigte also Geld als verfuegbar, das es nicht ist.
        guthaben = antwort.get("guthaben")
        kanaele = antwort.get("kanaele")
        if guthaben is not None and kanaele is not None:
            reserve = sum(k.get("reserve", 0) for k in kanaele)
            guthaben["kanal_reserve"] = reserve
            guthaben["kanal_frei"] = max(
                0, guthaben.get("kanal_hier", 0) - reserve)

        # Jetzt mit Guthaben: erst der Anteil macht aus einer Satoshi-Zahl
        # eine Aussage.
        #
        # OHNE die Anker-Ruecklage: die braucht nur der Kanalrechner, und der
        # steht seit dem 11.09.2026 unter "Rechner" mit eigenem Endpunkt. Sie
        # hier trotzdem zu holen waere ein LND-Aufruf je Auffrischung fuer
        # eine Zahl, die auf dieser Seite niemand sieht.
        kosten_dazu((antwort.get("guthaben") or {}).get("kette_gesamt", 0))
        return antwort

    @api.get("/karte", dependencies=geschuetzt)
    def weltkarte() -> Dict:
        """Was dieser Knoten vom Netz kennt, nach Laendern.

        Das Adressbuch kommt aus dem Zwischenspeicher -- der Waechter frischt
        es halbstuendlich auf. Die eigenen Gegenstellen werden bei jedem
        Aufruf frisch geholt: die wechseln staendig, und genau sie sind der
        Teil der Karte, der einem selbst gehoert.
        """
        if not zustand.laden().eingerichtet:
            return {"eingerichtet": False}

        # Beim allerersten Aufruf gibt es noch kein Buch -- der Waechter kommt
        # erst nach zehn Minuten das erste Mal vorbei. Es HIER zu holen waere
        # der teure Aufruf mitten im Anfrageweg, mit dreissig Sekunden Frist:
        # die Seite haenge, und zwar ausgerechnet beim ersten Eindruck.
        # Stattdessen im Hintergrund anstossen und sofort zeigen, was da ist.
        if kartenbuch["daten"] is None:
            starte_buchauswertung()

        # Die eigenen Adressen kommen aus der zwischengespeicherten
        # Kettenlage statt aus einem zweiten getnetworkinfo. Das war die
        # Quelle der Meldung "getnetworkinfo nicht moeglich: antwortet nicht
        # innerhalb von 15 s": von den vier Aufrufen der Karte ist er der
        # einzige, der laut v31.1/src/rpc/net.cpp LOCK(cs_main) nimmt, und
        # cs_main haelt Core waehrend jedes chainstate-Schreibvorgangs.
        lage = lage_holen()
        # Eine leere Liste, KEIN None. Der Unterschied ist der ganze Fix:
        # None heisst fuer sammle() "hol sie dir selbst", und genau das war
        # am 02.09.2026 um 07:08 wieder im Protokoll -- "getnetworkinfo nicht
        # moeglich: antwortet nicht innerhalb von 15 s". Ist die Lage nicht da,
        # ist bitcoind gerade beschaeftigt; dann ist ein zweiter Versuch mit
        # demselben Aufruf, der als einziger cs_main braucht, sicher vergebens.
        # Ohne eigene Adressen faellt eigener_ort auf das zurueck, wofuer die
        # Gegenstellen uns halten -- das kostet keinen einzigen Aufruf.
        d = karte.sammle(knotenverbindung(), ortstabelle,
                         kartenbuch["daten"] or karte.LEERES_BUCH,
                         (lage or {}).get("adressen") or [],
                         # Wieder: leere Liste, kein None. Solange der
                         # Sammler nichts hat, wird nicht nachgefragt.
                         rohdaten()[0] or [])
        d["eingerichtet"] = True
        d["buch_stand"] = kartenbuch["stand"]
        d["buch_laeuft"] = kartenbuch["laeuft"]

        # Die Lightning-Haelfte: wohin Kapital gebunden ist. Dieselbe
        # Ortstabelle wie die Bitcoin-Seite -- ein Ort ist ein Ort, egal
        # welches Netz danach fragt.
        #
        # Faellt weg, solange es keine Wallet gibt. Ein leerer Block waere
        # kein Schaden, aber jeder Aufruf kostete dann einen Fehlschlag
        # gegen einen Dienst, der noch gar nichts zu sagen hat.
        d["lightning"] = None
        if lnd.macaroon_da(lndverbindung()):
            try:
                d["lightning"] = karte.verorte_lightning(
                    lnd.gegenstellen(lndverbindung()), ortstabelle)
            except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
                log.debug("Lightning-Orte nicht abrufbar: %s", fehler)
        return d

    @api.get("/karte/land/{kuerzel}", dependencies=geschuetzt)
    def land_aufschluesseln(kuerzel: str) -> Dict:
        """Ein Land, nach Gebieten aufgeschluesselt.

        Aus dem Betrieb, 05.09.2026: "dass man in der Weltkarte auf die einzelnen
        Laender klicken kann und die dann gross werden und uns da in den
        einzelnen Bundeslaendern zeigen, wo die Knoten sind" -- und gleich
        darauf: "das gilt fuer jedes Land der Welt!"

        KEIN einziger neuer Aufruf an bitcoind: gezaehlt wurde schon, als die
        Weltkarte gebaut wurde. Hier wird nur nach Land geschnitten. Ein
        eigener Abruf je Klick waere sonst ein zweiter Satz
        getnodeaddresses-Aufrufe -- und die Zahlen koennten neben denen der
        Weltkarte stehen und ihnen widersprechen.
        """
        land = (kuerzel or "").strip().upper()
        if len(land) != 2 or not land.isalpha():
            raise HTTPException(404, {"meldung": "land_unbekannt"})
        if gebietsnamen is None:
            # Ehrlich sagen, dass es die Aufschluesselung hier nicht gibt --
            # statt ein leeres Land zu zeigen, das aussaehe wie "niemand da".
            return {"land": land, "moeglich": False, "gebiete": []}

        buch = kartenbuch["daten"] or karte.LEERES_BUCH
        peers = karte.verorte_peers(knotenverbindung(), ortstabelle,
                                    rohdaten()[0] or [])
        # Die Lightning-Seite wie in /karte: frisch geholt, aber nur wenn es
        # ueberhaupt eine Wallet gibt. Ein Klick ist kein Anzeigetakt --
        # einmal fragen ist hier in Ordnung, dauernd fragen waere es nicht.
        lightning: Dict = {}
        if lnd.macaroon_da(lndverbindung()):
            try:
                lightning = karte.verorte_lightning(
                    lnd.gegenstellen(lndverbindung()), ortstabelle)
            except (lnd.NichtErreichbar, lnd.LndFehler) as fehler:
                log.debug("Lightning-Orte nicht abrufbar: %s", fehler)

        aus_buch = buch.get("gebiete") or {}
        aus_peers = peers.get("gebiete") or {}
        aus_ln = lightning.get("gebiete") or {}
        kapazitaet = lightning.get("kapazitaet_je_gebiet") or {}

        zeilen = []
        for e in gebietsnamen.eines_landes(land):
            n = e["n"]
            zeile = {
                "n": n, "de": e.get("de", ""), "en": e.get("en", ""),
                "iso": e.get("iso") or [],
                "bitcoin": int(aus_peers.get(n, 0)),
                "adressbuch": int(aus_buch.get(n, 0)),
                "lightning": int(aus_ln.get(n, 0)),
                "kapazitaet": int(kapazitaet.get(n, 0)),
            }
            zeilen.append(zeile)
        # ALLE Gebiete, nicht nur die mit Zahlen. Aus dem Betrieb, 06.09.2026
        # ausdruecklich: "ich klicke auf ein leuchtendes ODER NICHT
        # leuchtendes Bundesland" -- ein Umriss, der sich nicht anklicken
        # laesst, sieht kaputt aus, auch wenn dahinter nur eine Null steht.
        # Sortiert bleibt trotzdem nach Gewicht: was etwas zu sagen hat,
        # steht oben.
        zeilen.sort(key=lambda z: (-z["bitcoin"], -z["lightning"],
                                   -z["adressbuch"], z["de"]))

        # Was im Land liegt, aber in keinem Gebiet. Es wegzulassen ergaebe
        # eine Summe, die kleiner ist als die der Weltkarte -- ohne dass
        # jemand erfuehre, wo der Rest geblieben ist.
        bekannt = {e["n"] for e in gebietsnamen.eines_landes(land)}
        return {
            "land": land,
            "moeglich": True,
            "stand": getattr(ortstabelle, "stand", "") if ortstabelle else "",
            "gebiete": zeilen,
            "ohne_gebiet": {
                "bitcoin": int(peers.get("laender", {}).get(land, 0))
                - sum(z["bitcoin"] for z in zeilen),
                "adressbuch": int(buch.get("laender", {}).get(land, 0))
                - sum(z["adressbuch"] for z in zeilen),
                "lightning": int((lightning.get("laender") or {}).get(land, 0))
                - sum(z["lightning"] for z in zeilen),
            },
            "unbekannte_gebiete": sum(
                1 for n in set(aus_peers) | set(aus_buch) | set(aus_ln)
                if n not in bekannt and (gebietsnamen.eines(n) or {}).get("land") == land),
        }

    @api.get("/neuerungen", dependencies=geschuetzt)
    def neuerungen_lesen() -> Dict:
        """Der Stand der Fassungspruefung -- und sonst nichts.

        Eigener Weg, weil diese Auskunft KEINEN Knoten braucht: sie liegt
        fertig im Arbeitsspeicher, hingelegt vom Waechter. Bis zum 03.09.2026
        kam sie nur als Beipack von /status -- und /status wartet auf
        bitcoind. Waehrend des Erstabgleichs lief der Aufruf regelmaessig in
        die Frist, und die kostenlose Auskunft ging mit unter.

        Dazu aus dem Betrieb, zu Recht: "der fassungskasten hat nie zu schweigen ...
        eine begruendung fuer ne fehl funktion ist trotzdem eine
        fehlfunktion". Ein Wert, der dasteht, darf nicht an einem Aufruf
        haengen, der ihn gar nicht braucht.
        """
        return {"neuerungen": neuerungen}

    # --------------------------------------------------------- Nachrichten
    #
    # Aus dem Betrieb, 06.09.2026, nachdem er die Chat-Idee selbst verworfen hatte:
    # "was aber vielleicht meinen Cortex von anderen unterscheiden wuerde
    # waere ein Nachrichten-Feed ... von regional von wo ich bin bis
    # international". Und einen Tag spaeter die Verschaerfung, die den
    # Zuschnitt bestimmt hat: "wenn ich in Algerien sitze und habe die
    # Software am Laufen, bringt mir Blocktrainer nichts".
    #
    # Deshalb Sprache statt Land -- siehe nachrichten.SPRACHE_JE_LAND.

    def _mein_land() -> Optional[str]:
        """Wo der Knoten steht. Aus der Weltkarte, nicht aus einer Frage."""
        return kartenbuch.get("heimat")

    @api.get("/nachrichten", dependencies=geschuetzt)
    def nachrichten_lesen(grenze: int = 60) -> Dict:
        """Die Meldungen, die Einstellungen und der Zustand je Quelle."""
        land = _mein_land()
        w = feed.wahl()
        gewaehlt = [q.kennung for q in feed.quellen(land)]
        fenster = min(max(int(grenze), 1), 200)
        return {
            "aktiv": w["aktiv"],
            "weit": w["weit"],
            "land": land,
            "sprache": nachrichten.sprache_fuer(land),
            "beitraege": auswertung.nachrichten_lesen(fenster, gewaehlt),
            # DIESELBE Grenze wie die Liste, nicht "alle ungelesenen".
            #
            # Aus dem Betrieb, 11.09.2026: "er zeigt mir links unter nachrrichten 25
            # neue an und wenn ich drauf klicke ist es vieleicht eine". Genau
            # so war es: gezaehlt wurde ueber die ganze Ablage, gezeigt wurden
            # die neuesten sechzig. Was darunter lag, war nicht anzuklicken --
            # blieb also ungelesen, und der Zaehler ging nie wieder herunter.
            "ungelesen": auswertung.nachrichten_ungelesen(gewaehlt, fenster),
            "quellen": feed.lagen(land),
            "speicher": auswertung.verfuegbar,
            # Wie viele der EINGESCHALTETEN Quellen gerade abgewiesen werden.
            # Ohne diese Zahl sieht ein duenner Feed aus wie "die schreiben
            # nichts" -- und der Nutzer sucht den Fehler bei sich. Genau das
            # ist Aus dem Betrieb, 06.09.2026 passiert: von 26 eingeschalteten
            # Fachquellen kam eine an, und nichts sagte, warum.
            "abgewiesen": sum(1 for q in feed.lagen(land)
                              if q["an"] and q["grund"]
                              and q["grund"] != "tor_aus"),
            # Damit niemand Reuters ein zweites Mal vorschlaegt.
            "nicht_verfuegbar": nachrichten.NICHT_VERFUEGBAR,
        }

    @api.post("/nachrichten/einstellungen", dependencies=geschuetzt)
    def nachrichten_einstellen(wahl: Nachrichtenwahl) -> Dict:
        # Eigene Quellen sind fremder Text. Was die Pruefung nicht besteht --
        # etwa ein javascript:-Verweis -- wird gar nicht erst gemerkt.
        eigene = [e for e in wahl.eigene if nachrichten.eigene_quelle(e)]
        verworfen = len(wahl.eigene) - len(eigene)
        zustand.merke_nachrichtenwahl({
            "aktiv": wahl.aktiv, "weit": wahl.weit,
            "abgewaehlt": wahl.abgewaehlt or [],
            "zugewaehlt": wahl.zugewaehlt, "eigene": eigene,
        })
        # Beim Einschalten sofort holen, nicht erst in einer Stunde: sonst
        # sieht der Nutzer einen leeren Reiter und haelt ihn fuer kaputt.
        #
        # Ein eigener Faden, NICHT asyncio.get_event_loop(). Dieser Endpunkt
        # ist synchron, FastAPI fuehrt ihn also in einem Arbeitsfaden aus --
        # und dort gibt es keine Ereignisschleife. Der erste Entwurf stuerzte
        # deshalb genau beim Einschalten ab: "There is no current event loop
        # in thread 'AnyIO worker thread'". Vom Pruefstand gefunden, nicht im
        # Betrieb.
        if wahl.aktiv:
            im_hintergrund("nachrichten-erstabruf",
                           lambda: feed.einmal_holen(_mein_land(), True))
        return {"ok": True, "verworfen": verworfen}

    @api.post("/nachrichten/gelesen", dependencies=geschuetzt)
    def nachrichten_gelesen(kennung: Optional[str] = None) -> Dict:
        if kennung:
            auswertung.nachricht_gelesen(kennung)
        else:
            auswertung.nachrichten_alle_gelesen()
        return {"ok": True}

    @api.post("/nachrichten/quelle-suchen", dependencies=geschuetzt)
    async def nachrichten_quelle_suchen(suche: Quellensuche) -> Dict:
        """Zu einer Webseite ihre Feed-Adresse finden.

        Die Seite sagt es selbst, im Kopf ihres HTML. Das traegt aber nicht
        immer -- handelsblatt.com deklariert nichts, sein Feed liegt auf einem
        anderen Rechner. Findet sich nichts, bleibt das Feld von Hand.
        """
        proxy = _tor_proxy()
        if not proxy:
            return {"gefunden": [], "grund": "tor_aus"}
        gefunden = await asyncio.to_thread(
            nachrichten.entdecke, suche.adresse[:500], proxy)
        return {"gefunden": gefunden, "grund": "" if gefunden else "nichts"}

    @api.get("/kurs", dependencies=geschuetzt)
    def kurs_lesen(waehrung: str = "usd",
                   zeitraum: str = kurs.VORGABE_ZEITRAUM) -> Dict:
        """Kurs und Verlauf -- aus dem Zwischenspeicher, nie aus dem Aufrufweg.

        Ein Abruf ueber Tor dauert bis zu 45 Sekunden. Haenge die Anzeige
        daran, staende die Seite bei jedem Oeffnen still. Geholt wird im
        Waechter; hier wird nur abgelesen.

        Der einzige Fall, in dem doch geholt wird: ein Zeitraum oder eine
        Waehrung, die noch nie geholt wurde -- sonst bliebe der Kasten nach
        einem Klick auf "1 Jahr" bis zur naechsten vollen Stunde leer.

        Bis zum 08.09.2026 stand hier nur "kein Verlauf". Beim Umschalten auf
        Euro war der Verlauf aber da -- nur der Kurs fehlte, und die Tafel
        reichte stattdessen den Dollarkurs durch. Beides muss zaehlen.
        """
        d = kurstafel.als_dict(waehrung, zeitraum)
        if not (d["verlauf"] and d["kurs"]) and not d["grund"]:
            threading.Thread(
                target=lambda: _kurs_holen(waehrung, zeitraum, True),
                name="kurs-nachladen", daemon=True).start()
        return d

    # Kanaele da, aber kein Turm? Mit eigenem, langsamem Takt: die Antwort
    # aendert sich hoechstens, wenn jemand einen Kanal oeffnet oder einen Turm
    # eintraegt -- beides Vorgaenge, die man selbst ausloest. Sie bei jedem
    # Statusabruf neu zu erfragen waere zwei LND-Aufrufe im Sekundentakt fuer
    # eine Zahl, die minutenlang dieselbe bleibt.
    turmstand: Dict[str, Any] = {"zeit": 0.0, "luecke": False}
    TURM_FRISCHE = 60.0

    def _eigene_turmkennung(knoten) -> str:
        """Der Schluessel unseres eigenen Turms -- oder "" .

        Leer heisst hier "es gibt keinen": laeuft der Wachturm-Server nicht,
        schickt LND keine Kennung, und dann steht auch kein eigener Turm in
        der Liste. Faellt der Aufruf voruebergehend aus, zaehlt der eigene
        Turm fuer diesen einen Durchgang mit -- deshalb faengt der Aufruf
        seine Fehler hier und nicht beim Aufrufer, wo er die ganze
        Wachturmlage mitnehmen wuerde.
        """
        try:
            return lnd.eigener_turm(knoten).get("kennung", "")
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as f:
            log.debug("Eigene Turmkennung nicht zu haben: %s", f)
            return ""

    def wachturmluecke(jetzt: Optional[float] = None) -> bool:
        jetzt = time.time() if jetzt is None else jetzt
        if jetzt - turmstand["zeit"] < TURM_FRISCHE:
            return bool(turmstand["luecke"])
        turmstand["zeit"] = jetzt
        knoten = lndverbindung()
        try:
            kanaele = lnd.kanaele(knoten)
            # Eingetragen ist nicht bewacht: auch ein Turm, der nie eine
            # Sitzung angenommen hat, laesst die Kanaele ungeschuetzt. Und
            # der eigene Turm zaehlt nicht mit -- er faellt mit dem Knoten
            # zusammen aus, den er bewachen soll.
            tuerme = lnd.wachtuerme(knoten, _eigene_turmkennung(knoten))
            turmstand["luecke"] = bool(kanaele) and bool(
                lnd.ungedeckte_arten(kanaele, tuerme))
        except (lnd.NichtErreichbar, lnd.LndFehler, lnd.Beschaeftigt) as fehler:
            # Keine Auskunft ist keine Luecke. Einen Hinweis auf Verdacht zu
            # zeigen waere schlechter als keiner.
            log.debug("Wachturmlage nicht zu haben: %s", fehler)
            turmstand["luecke"] = False
        return bool(turmstand["luecke"])

    def naechster_schritt(e, lage: Optional[Dict]) -> Optional[Dict]:
        """Was JETZT zu tun ist -- oder nichts.

        Aus dem Betrieb, 09.09.2026 zu seinen Befunden 1, 12 und 13: der Zustand
        stand dort, wo man nicht handeln kann, und das Handeln dort, wo man
        nicht hinsieht.

        - Die Uebersicht meldete "LND laeuft", waehrend der Knoten mit
          gesperrter Wallet stillstand und nichts weiterleitete.
        - Die Kanalseite sagte "angelegt, aber gesperrt" -- ohne einen Weg
          zum Entsperren.
        - Und dass ueberhaupt zuerst eine Wallet noetig ist, stand in genau
          einem Satz, ausgerechnet unter Lightning -> Knoten.

        Die Reihenfolge ist nach Dringlichkeit: eine gesperrte Wallet haelt
        einen laufenden Knoten an, das wiegt schwerer als eine fehlende.

        Und ausdruecklich seine Bedingung: "wenn alles da, muss man ja nicht
        mehr sehen was zu tun ist". Steht nichts an, gibt diese Funktion
        None zurueck und die Zeile erscheint gar nicht -- kein Dauerbanner.
        Nach einem Stromausfall mit gesperrter Wallet erscheint sie sehr
        wohl, und genau dann braucht man sie.
        """
        if not e.eingerichtet:
            return None            # der Assistent fuehrt bereits
        if lage is None or lage.get("im_erstsync", True):
            return None            # es gibt nichts zu tun ausser warten
        stand = lnd.zustand(lndverbindung())["stand"]
        if stand == "gesperrt":
            return {"was": "wallet_entsperren", "ansicht": "ln-einrichtung",
                    "dringend": True}
        if stand == "keine_wallet":
            return {"was": "wallet_anlegen", "ansicht": "ln-einrichtung",
                    "dringend": False}
        if (stand == "bereit" and not (e.sicherungsziel or {}).get("url")
                and "sicherungsziel" not in _abgewiesen(e)):
            # Ohne Sicherung sind die Kanal-Guthaben bei Datenverlust weg,
            # und zwar auch mit dem Zettel in der Hand. Das gehoert gesagt.
            #
            # ABER: gesagt, nicht verlangt. Aus dem Betrieb, 09.09.2026: "das
            # aufmerksam machen auf die kanal sicherung nervt! ... das
            # sollten wir dem kunden ueberlassen, es sollte keine pflicht
            # sein!" Er hat recht -- die anderen beiden Faelle verschwinden
            # von allein, sobald man sie erledigt. Dieser hier ist eine
            # WAHL, und eine Wahl, die man taeglich neu wegklicken muss,
            # ist keine. Deshalb abweisbar, und zwar dauerhaft.
            return {"was": "sicherungsziel", "ansicht": "ln-einrichtung",
                    "dringend": False, "abweisbar": True}
        # KANAELE OHNE WACHTURM.
        #
        # Aus dem Betrieb, 12.09.2026: "warum muss ich einen wachtum seperate
        # anwaehlen wieso startet nicht einfach der wachtum selbstaendig wenn
        # ich einen kanal aufmache???"
        #
        # Weil das Protokoll keine Wachturm-Suche kennt: Tuerme werden im
        # Graphen nicht angekuendigt, unser Knoten WEISS gar nicht, welche es
        # gibt. Jemand muss eine Adresse nennen -- und wem man verraet, dass
        # man Kanaele hat, waehlt der Betreiber selbst.
        #
        # Was wir tun koennen: es sagen, und zwar dort, wo es auffaellt.
        # Bisher stand der Hinweis nur unter "Kanaele" -- man musste
        # hinsehen. Hier steht er auf jeder Seite.
        #
        # Abweisbar wie das Sicherungsziel, aus demselben Grund: es ist eine
        # WAHL, und eine Wahl, die man taeglich wegklicken muss, ist keine.
        if stand == "bereit" and "wachturm" not in _abgewiesen(e) \
                and wachturmluecke():
            return {"was": "wachturm", "ansicht": "ln-kanaele",
                    "dringend": False, "abweisbar": True}
        return None

    @api.post("/hinweis/abweisen", dependencies=geschuetzt)
    def hinweis_abweisen(wahl: Hinweiswahl) -> Dict:
        """Einen Hinweis dauerhaft wegnehmen.

        Nur fuer die, die eine WAHL beschreiben und keinen Zustand. Eine
        gesperrte Wallet laesst sich nicht wegklicken -- die verschwindet,
        wenn man sie entsperrt.
        """
        if wahl.was not in ABWEISBAR:
            raise HTTPException(400, {"meldung": "hinweis_unbekannt"})
        e = zustand.laden()
        neu = dict(e.knotenwahl or {})
        offen = [x for x in _abgewiesen(e) if x != wahl.was]
        neu["hinweise_abgewiesen"] = offen + [wahl.was]
        zustand.merke_knotenwahl(neu)
        return {"ok": True}

    @api.get("/status", dependencies=geschuetzt)
    def status() -> Dict:
        e = zustand.laden()
        antwort: Dict = {
            "eingerichtet": e.eingerichtet,
            "einrichtung": e.to_dict(),
            "dienste": ablage.alle(DIENSTE),
            "neuerungen": neuerungen,
        }
        # Erst nach der Einrichtung gibt es einen Knoten, mit dem man reden
        # kann. Vorher waere jeder Aufruf ein garantierter Fehlschlag.
        knoten, grund = ((None, rpc.KNOTEN_WEG) if not e.eingerichtet
                         else lage_mit_grund_gebuendelt())
        antwort["knoten"] = knoten
        # Der Grund gehoert mit in die Antwort. Ohne ihn kann die Oberflaeche
        # "laeuft nicht" nicht von "kommt gerade nicht zum Antworten"
        # unterscheiden -- und meldet beim Zweiten faelschlich einen Neustart.
        antwort["knoten_grund"] = grund

        # Jeder Aufruf der Uebersicht ist zugleich ein Messpunkt. Die Anzeige
        # laedt alle zehn Sekunden nach, damit fuellt sich das Fenster von
        # selbst -- ohne eigene Hintergrundaufgabe.
        if knoten and knoten.get("im_erstsync"):
            verlauf.merke(knoten["fortschritt"], knoten["hoehe"])
            antwort["tempo"] = verlauf.schaetzung()
        elif knoten:
            # Erst nach dem Abgleich gibt es einen Mempool: waehrend des
            # Erstsyncs nimmt Bitcoin Core gar keine Transaktionen an.
            # Aus dem Sammler, nicht frisch geholt: es ist derselbe Weg
            # durch dieselbe Warteschlange wie alles andere. Am 04.09.2026
            # im Pruefstand gemessen -- mit dieser einen Zeile dauerte jeder
            # /status-Aufruf wieder volle vier Sekunden, obwohl die
            # Kettenlage laengst bereitlag.
            antwort["mempool"] = mempoolspeicher["wert"]
        # Was jetzt zu tun ist -- oder gar nichts. Siehe naechster_schritt().
        try:
            antwort["naechster_schritt"] = naechster_schritt(e, knoten)
        except Exception:                                        # nosec B902
            # Eine Fuehrungszeile darf die Uebersicht nie mitreissen.
            log.exception("Naechster Schritt nicht bestimmbar")
            antwort["naechster_schritt"] = None
        return antwort

    # Wann der eingetragene Name zuletzt aufloesbar war.
    #
    # Der Anlass, 31.08.2026: Im Betriebsprotokoll stand "Name ... nicht
    # aufloesbar: [Errno -5]". Von aussen loeste derselbe Name ueber drei
    # Resolver einwandfrei auf -- es scheiterte nur im Container. Die
    # Anwendung hat richtig reagiert und die Adresse in Ruhe gelassen, statt
    # eine kaputte zu schreiben.
    #
    # Aber genau das ist die Falle: nach aussen sieht alles gut aus. Der
    # Knoten wirbt weiter mit der Adresse von damals, und nach der naechsten
    # Zwangstrennung gehoert die jemand anderem. Sichtbar war das nur im
    # Protokoll -- also an der Stelle, an der niemand nachsieht, solange
    # nichts weh tut.
    adressstand: Dict = {"zuletzt_ok": 0.0, "versucht": 0.0, "fehler": ""}

    # ── Die Onion-Dienste: Tor haelt sie, bitcoind und LND kuendigen an ──
    #
    # Die Einzelheiten stehen in onion.py und netz.py. Hier steht nur die
    # Reihenfolge, und die ist nicht beliebig:
    #
    #   1. Alte Schluessel an Tor uebergeben (sonst legt Tor neue an und die
    #      .onion wechselt).
    #   2. torrc schreiben -- Tor startet neu und hinterlegt "hostname".
    #   3. Kurz warten, bis die Adressen da sind.
    #   4. Erst dann bitcoind.conf und lnd.conf, jeweils EIN Schreibvorgang.
    #
    # Ohne Schritt 3 bekaemen beide ihre .onion erst beim naechsten
    # Durchgang -- ein zweiter Neustart, und bei LND ohne Auto-Entsperren eine
    # zweite gesperrte Wallet.

    def _onion_von(name: str, wege: Dict, bisher: str = "",
                   gefunden: Optional[Dict] = None) -> str:
        """Welche .onion ein Dienst ankuendigen soll -- oder "".

        Was Tor hinterlegt hat, gilt. Kann die Datei gerade nicht gelesen
        werden, bleibt die bisherige stehen -- dieselbe Regel wie bei einem
        DNS-Aussetzer: ein Wackler darf keine Adresse aus der Ankuendigung
        nehmen und keinen Dienst neu starten.
        """
        if not onion.dienste_fuer(wege["tor"], wege["sichtbarkeit"]):
            return ""
        return ((gefunden or {}).get(name)
                or onion.lies_adresse(konf.fast, name) or bisher)

    def _bitcoind_onion(wege: Dict, vorhanden: str,
                        gefunden: Optional[Dict] = None) -> str:
        return _onion_von("bitcoind", wege,
                          nodeconfig.lies_onion(vorhanden or ""), gefunden)

    def _schluessel_uebernehmen(dienste) -> None:
        for name in dienste:
            try:
                onion.uebernimm_schluessel(konf.fast, name)
            except OSError:
                # Dann legt Tor eine neue Adresse an. Schlechter als die alte,
                # aber kein Grund, Tor gar nicht zu konfigurieren.
                log.exception("Onion-Schluessel fuer %s nicht uebernommen", name)

    def _tor_ablegen(wege: Dict) -> bool:
        """Die torrc zur Wahl ablegen. Gibt zurueck, ob sie sich geaendert hat."""
        dienste = onion.dienste_fuer(wege["tor"], wege["sichtbarkeit"])
        _schluessel_uebernehmen(dienste)
        soll = nodeconfig.baue_tor(dienste, konf.netz_praefix)
        if ablage.lies("tor") == soll:
            return False
        ablage.schreibe("tor", soll)
        ablage.gib_frei("tor")
        log.info("Tor-Konfiguration abgelegt (Onion-Dienste: %s) -- Tor "
                 "startet einmal neu.", ", ".join(dienste) or "keine")
        return True

    def tor_schreiben(wege: Dict, frist: float) -> Dict[str, str]:
        """torrc ablegen, Tor freigeben -- und auf seine Adressen warten.

        Fuer den Assistenten und die Einstellungen. Tor folgt dem Schalter:
        abgeschaltet heisst gesperrt, ein Onion-Dienst ohne Tor waere ein
        Dienst, den niemand braucht.
        """
        if not wege["tor"]:
            ablage.sperre("tor")
            return {}
        _tor_ablegen(wege)
        ablage.gib_frei("tor")
        dienste = onion.dienste_fuer(wege["tor"], wege["sichtbarkeit"])
        return onion.abwarten(konf.fast, dienste, frist) if dienste else {}

    def soll_rpc(vorhanden: str) -> str:
        """rpcallowip auf das Compose-Netz dieser Anlage bringen.

        Bis 0.62.0 stand dort 172.16.0.0/12. Aus dem festen Netz kaeme die
        Anwendung damit nicht mehr an ihren eigenen Knoten -- und LND auch
        nicht. Deshalb laeuft das hier OHNE RPC: gerade die Verbindung, die es
        wiederherstellt, gibt es vorher nicht.
        """
        if nodeconfig.lies_rpc_compose_netz(vorhanden) == konf.compose_netz:
            return vorhanden
        heimnetz = _wege(zustand.laden().knotenwahl)["rpc_heimnetz"]
        return nodeconfig.setze_rpc_freigabe(
            vorhanden, heimnetz, konf.compose_netz)

    def bitcoind_netz_nachziehen() -> bool:
        """Compose-Netz und Tor-Abschnitt von bitcoind -- nur aus Dateien."""
        try:
            if not zustand.laden().eingerichtet:
                return False
            vorhanden = ablage.lies("bitcoind")
            if not vorhanden:
                return False
            neu = soll_tor(soll_rpc(vorhanden))
            if neu == vorhanden:
                return False
            ablage.schreibe("bitcoind", neu)
            ablage.gib_frei("bitcoind")
            log.info("bitcoind nachgezogen (RPC aus %s, .onion %s) -- "
                     "bitcoind startet einmal neu.", konf.compose_netz,
                     nodeconfig.lies_onion(neu) or "keine")
            return True
        except Exception:                                        # nosec B902
            log.exception("Nachziehen der bitcoind-Netzeinstellungen "
                          "fehlgeschlagen")
            return False

    def lightning_onions_erneuern() -> None:
        """Neue .onion fuer Knoten und Wachturm -- fuer "Wallet loeschen".

        Laeuft, waehrend LND angehalten ist (_lnd_neu_starten, "danach").

        1. Die alten Adressen aus der lnd.conf nehmen. Ohne das hielte
           _onion_von sie fest, solange Tor noch keine neuen hinterlegt hat,
           und die neue Wallet traete unter der alten Adresse auf.
        2. Die Schluessel wegwerfen.
        3. Tor neu starten -- es haelt den alten Schluessel noch im Speicher
           und erzeugt neue erst beim Start. Ausgeloest ueber die fehlende
           Freigabemarke, derselbe Weg wie ueberall.
        4. Die neuen Adressen eintragen. Kam Tor nicht rechtzeitig, holt der
           Waechter es nach -- ohne Adresse, nie mit der alten.
        """
        namen = ("lnd", "wachturm")
        vorhanden = ablage.lies("lnd")
        if vorhanden:
            ohne = nodeconfig.lnd_ohne_onion(vorhanden)
            if ohne != vorhanden:
                # Ohne gib_frei: LND ist gerade angehalten, und die Freigabe
                # gibt _lnd_neu_starten am Ende zurueck.
                ablage.schreibe("lnd", ohne)
        for name in namen:
            ziel = onion.verzeichnis(konf.fast, name)
            if ziel.is_symlink():
                ziel.unlink()
            elif ziel.is_dir():
                shutil.rmtree(ziel)
        if ablage.lies("tor") is not None:
            ablage.sperre("tor")
            time.sleep(TOR_NEUSTART_PAUSE_SEKUNDEN)
            ablage.gib_frei("tor")
            onion.abwarten(konf.fast, namen, ONION_FRIST_WAECHTER_SEKUNDEN)
        lightning_adressen_sicherstellen()

    app.state.lightning_onions_erneuern = lightning_onions_erneuern

    def _lightning_einstellungen(wege: Dict, adressen, vorhanden: str
                                 ) -> nodeconfig.Lightningeinstellungen:
        """Wie lnd.conf zum heutigen Zustand aussehen muesste.

        Name und Farbe kommen aus der Wahl des Nutzers -- bis zum 09.09.2026
        wurden sie nie uebergeben, und deshalb hiess jeder Knoten dieser
        Software gleich.
        """
        wahl = zustand.laden().knotenwahl or {}
        return nodeconfig.Lightningeinstellungen(
            alias=wahl.get("lightning_alias") or nodeconfig.ALIAS_VORGABE,
            farbe=wahl.get("lightning_farbe") or nodeconfig.FARBE_VORGABE,
            minchansize=wahl.get("lightning_minchansize")
            or nodeconfig.MINCHANSIZE_VORGABE,
            sichtbarkeit=wege["sichtbarkeit"],
            tor_aktiv=wege["tor"],
            externe_adressen=nodeconfig.lnd_adressen_halten(
                vorhanden, adressen, wege["adresse_ankuendigen"],
                konf.lightning_p2p_port),
            wachturm_port=konf.wachturm_port,
            onion_adresse=_onion_von(
                "lnd", wege, nodeconfig.lies_lnd_onion(vorhanden or "")),
            wachturm_onion=_onion_von(
                "wachturm", wege, nodeconfig.lies_wachturm_onion(vorhanden or "")),
            # Der Entsperrweg kommt aus der vorhandenen Datei -- lnd_soll
            # traegt ihn nach. Er haengt an der Wallet, nicht an der
            # Sichtbarkeit.
            entsperrdatei="")

    def lightning_conf_nachziehen(wege: Dict, adressen) -> bool:
        """Eine BESTEHENDE lnd.conf dem heutigen Zustand angleichen.

        DER SCHRITT, DER GEFEHLT HAT. Bis zum 09.09.2026 wurde lnd.conf genau
        einmal geschrieben; danach war jede Einstellung wirkungslos. Das
        Nachfuehren tauschte nur die externalip-Zeilen -- und auch das nur,
        solange "adresse_ankuendigen" AN war. Wer auf "nur ueber Tor"
        umstellte, setzte damit genau dieses Haekchen auf aus und schnitt
        sich den einzigen Weg ab, auf dem die Aenderung angekommen waere.

        Der Schalter stand also auf "nur ueber Tor", und der Knoten kuendigte
        weiter die Wohnanschrift an. Der Betreiber hat am 09.09.2026 genau danach
        gefragt, bevor er umgestellt hat -- gut, dass er es tat.

        Legt NICHTS an: das erste Schreiben bleibt bei
        lightning_bereitstellen, das auf die fertige Kette wartet.
        """
        try:
            vorhanden = ablage.lies("lnd")
            if not vorhanden:
                return False        # Lightning ist noch nicht eingerichtet
            soll = nodeconfig.lnd_soll(
                vorhanden, _lightning_einstellungen(wege, adressen, vorhanden))
            if not nodeconfig.lnd_muss_neu(vorhanden, soll):
                return False
            ablage.schreibe("lnd", soll)
            ablage.gib_frei("lnd")
            # Die Folge gehoert ins Protokoll, weil sie den Knoten anhaelt:
            # ohne Entsperrdatei ist die Wallet nach dem Neustart zu, und
            # solange sie zu ist, leitet er nichts weiter.
            zu = not nodeconfig.lies_entsperrdatei(soll)
            log.info("Lightning nachgezogen (%s, kuendigt %s an) -- LND "
                     "startet neu%s.", wege["sichtbarkeit"],
                     ", ".join(nodeconfig.lies_lnd_adressen(soll))
                     or "keine Adresse",
                     " und die Wallet ist danach gesperrt" if zu else "")
            return True
        except Exception:                                        # nosec B902
            log.exception("Nachziehen der lnd.conf fehlgeschlagen")
            return False

    def lightning_adresse_nachziehen(adressen: List[str]) -> bool:
        """Nur noch der Einsprung aus der Adressnachfuehrung.

        Frueher flickte diese Funktion selbst an den externalip-Zeilen. Das
        war der halbe Weg: eine geaenderte Sichtbarkeit erreichte LND nie.
        Jetzt geht auch sie durch den einen Erbauer.
        """
        wege = _nach_sichtbarkeit(_wege(zustand.laden().knotenwahl))
        passend = nodeconfig.adressen_fuer_netze(
            adressen, wege["ipv4"], wege["ipv6"])
        return lightning_conf_nachziehen(wege, passend)

    def lightning_adressen_sicherstellen() -> bool:
        """Die lnd.conf bei JEDEM Durchgang auf den heutigen Stand bringen.

        DER BEFUND VOM 10.09.2026. Der Knoten im Betrieb zeigte unter "Knoten"
        keine Verbindungsadresse, obwohl in den Einstellungen alles stand:
        Sichtbarkeit "Tor und Clearnet", eigene Adresse eingetragen, und
        bitcoind kuendigte sie nachweislich an.

        Die lnd.conf wurde von genau EINER Stelle nachgezogen, und die hing
        an einer Bedingung, die bitcoind betrifft:

            if not soll or not dyndns.hat_sich_geaendert(vorhanden, soll):
                return False
            ablage.schreibe("bitcoind", ...)
            lightning_adresse_nachziehen(soll)      <-- nur hier

        hat_sich_geaendert() vergleicht mit der BITCOIND-Konfiguration. Steht
        die Adresse dort schon, steigt die Funktion aus -- und LND wird nie
        angefasst. Fehlt sie in der lnd.conf, fehlt sie fuer immer, ganz
        gleich wie lange man wartet. Dieselbe Fehlerklasse wie Befund 9: der
        Lightning-Weg haengt an einer Bedingung, die ihn nichts angeht.

        Jetzt gleicht der Waechter jeden Durchgang ab. Das kostet nichts:
        lnd_muss_neu() vergleicht den Inhalt und schreibt nur bei echtem
        Unterschied -- ein Neustart, der die Wallet sperrt, entsteht also
        weiterhin nur, wenn sich wirklich etwas geaendert hat.

        Die Adressen kommen aus der BITCOIND-Konfiguration und nicht aus einer
        zweiten DNS-Abfrage. Dort stehen sie bereits aufgeloest -- und bereits
        gegen einen DNS-Aussetzer gehalten. Zweimal aufzuloesen hiesse, sich
        zwei verschiedene Antworten einzuhandeln.
        """
        try:
            if not ablage.lies("lnd"):
                return False        # Lightning ist noch nicht eingerichtet
            bitcoind_conf = ablage.lies("bitcoind")
            if not bitcoind_conf:
                return False
            wege = _nach_sichtbarkeit(_wege(zustand.laden().knotenwahl))
            adressen = (list(nodeconfig.lies_adressen(bitcoind_conf))
                        if wege["adresse_ankuendigen"] else [])
            return lightning_conf_nachziehen(wege, adressen)
        except Exception:                                        # nosec B902
            log.exception("Abgleich der lnd.conf fehlgeschlagen")
            return False

    def adresse_nachfuehren() -> bool:
        """Zeigt der eingetragene Name noch auf die Adresse in der conf?

        Gibt zurueck, ob etwas geaendert wurde. Laeuft im Hintergrund und darf
        deshalb NIE eine Ausnahme nach oben lassen -- ein Fehler hier wuerde
        sonst die ganze Anwendung mitnehmen.
        """
        try:
            e = zustand.laden()
            wahl = e.knotenwahl or {}
            gewaehlt = wahl.get("externe_adresse", "")
            # Abgeschaltet heisst abgeschaltet: kein DNS-Aufruf, kein
            # stiller Neustart, keine Adresse in der Konfiguration.
            if not wahl.get("adresse_ankuendigen", True):
                return False
            if not e.eingerichtet or not gewaehlt:
                return False
            vorhanden = ablage.lies("bitcoind")
            if not vorhanden:
                return False

            adressstand["versucht"] = time.time()
            soll = dyndns.loese_auf(_adressliste(gewaehlt))
            if soll:
                adressstand.update(zuletzt_ok=time.time(), fehler="")
            else:
                # Ein Name, der sich nicht aufloesen laesst, ist kein Fehler
                # dieses Durchgangs -- aber einer, der bestehen bleibt, ist
                # einer der Anlage.
                adressstand["fehler"] = "nicht_aufloesbar"
            if not soll or not dyndns.hat_sich_geaendert(vorhanden, soll):
                return False

            ablage.schreibe("bitcoind", nodeconfig.setze_adressen(vorhanden, soll))
            ablage.gib_frei("bitcoind")
            lightning_adresse_nachziehen(soll)
            log.info("Eigene Adresse geaendert, jetzt %s -- bitcoind wird neu "
                     "gestartet.", ", ".join(soll))
            return True
        except Exception:                                        # nosec B902
            log.exception("Nachfuehren der Adresse fehlgeschlagen")
            return False

    def soll_cache(vorhanden: str, im_erstsync: bool) -> str:
        """Den Datenbank-Cache an die Betriebsphase anpassen.

        Waehrend des Abgleichs gross, danach klein: auf einem NAS, auf dem
        noch Immich, Paperless und Nextcloud laufen, bleibt sonst dauerhaft
        rund ein Gigabyte gebunden, das niemand mehr braucht.
        """
        grenze = (zustand.laden().knotenwahl or {}).get("speichergrenze_mb")
        if not grenze:
            # Vor 0.4.1 eingerichtet: die Grenze ist nicht festgehalten. Aus
            # dem eingestellten Wert zurueckzurechnen waere Raterei.
            return vorhanden
        soll = profiles.dbcache_mb(grenze, im_erstsync)
        if nodeconfig.lies_dbcache(vorhanden) == soll:
            return vorhanden
        return nodeconfig.setze_dbcache(vorhanden, soll)

    def soll_indizes(vorhanden: str, im_erstsync: bool) -> str:
        """txindex und Blockfilter an die Betriebsphase anpassen.

        Waehrend des Abgleichs aus. Beide sind LevelDB-Datenbanken, die bei
        jedem Block mit Spruengen schreiben -- auf derselben Platte wie die
        Bloecke. Auf einer Festplatte nehmen sie genau die Zugriffe weg, auf
        die der Abgleich ohnehin wartet. Gebraucht werden sie erst danach.

        Verloren geht nichts: Core merkt sich den Stand jedes Index als
        Locator in dessen eigener Datenbank und setzt beim Einschalten dort
        fort; ein abgeschalteter Index wird nicht geloescht. Geprueft in
        src/index/base.cpp und src/init.cpp gegen Core 31.1.
        """
        an = not im_erstsync
        if nodeconfig.lies_indizes(vorhanden) == an:
            return vorhanden
        return nodeconfig.setze_indizes(vorhanden, an)

    def soll_ausgang(vorhanden: str, lage: Dict) -> str:
        """onlynet an die eingestellten Wege UND die Betriebsphase anpassen.

        Beides zusammen, an einer Stelle. Vorher regelte hier allein die
        Betriebsphase -- und haette damit einen Schalter ueberschrieben, den
        es zu dem Zeitpunkt noch nicht gab.
        """
        wege = _wege(zustand.laden().knotenwahl)
        jetzt = nodeconfig.lies_netze(vorhanden)
        erlaubt, grund = _erlaubte_netze(wege, lage, jetzt)
        if not erlaubt:
            # Alle drei aus waere ein Knoten ohne Ausgang. Der Weg dahin ist
            # ueber die Oberflaeche versperrt; kommt es trotzdem so weit,
            # bleibt die Datei lieber, wie sie ist.
            return vorhanden
        if tuple(jetzt) == tuple(erlaubt):
            return vorhanden
        return nodeconfig.setze_netze(vorhanden, erlaubt, grund)

    def soll_tor(vorhanden: str) -> str:
        """Der Tor-Abschnitt folgt dem Schalter und der Sichtbarkeit.

        Verglichen wird, was bitcoind liest -- nicht der Text. Sonst startete
        eine umformulierte Kommentarzeile im Abbild jeden Knoten neu.
        """
        wege = _nach_sichtbarkeit(_wege(zustand.laden().knotenwahl))
        neu = nodeconfig.setze_tor(vorhanden, wege["tor"],
                                   _bitcoind_onion(wege, vorhanden))
        if nodeconfig.wirksam(neu) == nodeconfig.wirksam(vorhanden):
            return vorhanden
        return neu

    lightning_steht = {"ja": False}

    def lightning_bereitstellen(lage: Optional[Dict]) -> bool:
        """LND einrichten, sobald die Kette steht -- und keinen Schritt weiter.

        DER SCHRITT, DEN ES NIE GAB. baue_lnd() stand seit Wochen fertig im
        Modul und wurde von keiner einzigen Stelle im laufenden Code
        aufgerufen -- nur aus Tests. Ohne lnd.conf schreibt niemand die
        Freigabe, ohne Freigabe wartet das Startskript im Container ewig, und
        die Oberflaeche meldet vollkommen zu Recht "wartet auf Einrichtung".

        Damit war der ganze Lightning-Teil unerreichbar: kein Seed, keine
        Wallet, keine Wiederherstellung. Aus dem Betrieb, 08.09.2026, nachdem seine
        Kette durch war: "was ist mit dem LND der nicht laeuft anzeigt sondern
        warte auf einrichtung?" -- eine Sackgasse, aus der die Oberflaeche
        keinen Ausweg anbot.

        WARUM DAS VON ALLEIN GESCHIEHT und nicht auf Knopfdruck: ein LND ohne
        Wallet ist reglos. Es hat keinen Knotenschluessel, meldet sich im
        Lightning-Netz nicht an, oeffnet keinen Kanal und haelt keinen
        Satoshi -- es steht in NON_EXISTING und wartet. Auch der Onion-Dienst
        entsteht erst mit der Wallet. Es zu starten aendert also nichts an
        der Sicherheitslage; es macht den naechsten Schritt ueberhaupt erst
        moeglich.

        Was NICHT von allein geschieht, bleibt genau wie bisher: die Wallet
        anlegen. Dort haengt der Seed dran, und dort bleibt jede Frage eine
        bewusste Handlung.
        """
        try:
            if lightning_steht["ja"]:
                return False        # in diesem Lauf schon erledigt
            if lage is None or lage.get("im_erstsync", True):
                return False        # vor der fertigen Kette legt LND nichts an
            if ablage.lies("lnd"):
                lightning_steht["ja"] = True
                return False        # laengst geschrieben
            wahl = zustand.laden().knotenwahl or {}
            # Die ABGELEITETEN Wege, nicht die rohen. Vorher stand hier
            # _wege(wahl): in "nur ueber Tor" lieferte das
            # adresse_ankuendigen=True, und die Adressen wurden aufgeloest
            # und uebergeben -- weggeworfen hat sie erst baue_lnd, weil die
            # Sichtbarkeit nicht hybrid war. Es stimmte durch einen zweiten
            # Riegel, nicht durch die Rechnung.
            wege = _nach_sichtbarkeit(_wege(wahl))
            adressen = ()
            if wege["adresse_ankuendigen"]:
                adressen = nodeconfig.adressen_fuer_netze(
                    dyndns.loese_auf(_adressliste(wege["externe_adresse"])),
                    wege["ipv4"], wege["ipv6"])
            # Derselbe Erbauer wie beim Nachziehen -- eine Stelle, an der die
            # Datei entsteht. Damit kommen Name und Farbe schon beim ersten
            # Schreiben an, und die Adressen tragen ihren Port.
            conf = nodeconfig.lnd_soll(
                "", _lightning_einstellungen(wege, adressen, ""))
            ablage.schreibe("lnd", conf)
            ablage.gib_frei("lnd")
            lightning_steht["ja"] = True
            log.info("Lightning eingerichtet -- LND startet jetzt und wartet "
                     "auf eine Wallet (Sichtbarkeit: %s, Name: %s).",
                     wege["sichtbarkeit"],
                     wahl.get("lightning_alias") or nodeconfig.ALIAS_VORGABE)
            return True
        except Exception:                                        # nosec B902
            log.exception("Lightning konnte nicht eingerichtet werden")
            return False

    app.state.lightning_bereitstellen = lightning_bereitstellen

    def konfiguration_nachregeln(lage: Dict) -> bool:
        """Alle Anpassungen an der Betriebsphase -- in EINEM Schreibvorgang.

        Frueher schrieb jede Anpassung fuer sich. Jede davon startet bitcoind
        neu, und der Waechter laeuft alle zehn Minuten: drei Anpassungen
        waeren drei Neustarts ueber eine halbe Stunde gewesen. Bei einem
        Knoten, der zum Laden des chainstate ohnehin Minuten braucht, ist das
        spuerbar -- und vollkommen unnoetig, denn die Datei wird ja ohnehin
        als Ganzes geschrieben.
        """
        try:
            if not zustand.laden().eingerichtet:
                return False
            vorhanden = ablage.lies("bitcoind")
            if not vorhanden:
                return False

            im_erstsync = bool(lage.get("im_erstsync"))
            neu = soll_cache(vorhanden, im_erstsync)
            neu = soll_indizes(neu, im_erstsync)
            neu = soll_tor(neu)
            neu = soll_ausgang(neu, lage)
            if neu == vorhanden:
                return False

            ablage.schreibe("bitcoind", neu)
            ablage.gib_frei("bitcoind")
            log.info("Konfiguration an die Betriebsphase angepasst (%s) -- "
                     "bitcoind startet einmal neu.",
                     "Erstabgleich" if im_erstsync else "laufender Betrieb")
            return True
        except Exception:                                        # nosec B902
            log.exception("Nachregeln der Konfiguration fehlgeschlagen")
            return False

    def lnd_fassung() -> Tuple[Optional[Tuple[int, ...]], bool]:
        """Welche LND-Fassung verglichen wird -- und ob sie wirklich laeuft.

        Sobald es den Dienst gibt, kommt die Nummer aus GetInfo. Bis dahin ist
        es die, die wir ausliefern: die Frage, ob das Abbild noch aktuell ist,
        stellt sich schon vorher -- und gerade bei Lightning, wo eine Fassung
        Kanaele und damit Geld betrifft. Die Oberflaeche sagt dazu, woher die
        Zahl stammt; hier steht die eine Zeile, die in Phase 7 wechselt.
        """
        return updates.LND_AUSGELIEFERT, False

    def eine_pruefung(projekt: updates.Projekt, laufend, laeuft: bool,
                      tor_an: bool, jetzt: float) -> None:
        """Ein Projekt nachschlagen -- und den Befund festhalten."""
        eintrag = neuerungen[projekt.name]
        if eintrag["stand"] and jetzt - eintrag["stand"] < updates.INTERVALL_SEKUNDEN:
            return
        # Nach einem Fehlschlag nicht sofort wieder. Der Waechter laeuft alle
        # zehn Minuten -- mal drei Versuche, mal zwei Projekte waeren das
        # sechsunddreissig Anfragen je Stunde an dieselbe Gegenstelle. Genau
        # das hat am 30.08.2026 mitgeholfen, das Anfragebudget des
        # Tor-Ausgangsknotens aufzubrauchen: "403 rate limit exceeded". Wer
        # auf eine Abfuhr haemmert, macht sie wahrscheinlicher.
        wartezeit = updates.wartezeit(eintrag["fehlversuche"])
        if eintrag["versucht"] and jetzt - eintrag["versucht"] < wartezeit:
            return
        # Was hier laeuft, wissen wir unabhaengig davon, ob die Abfrage nach
        # draussen gelingt. Also wird es auch unabhaengig davon gemeldet.
        eintrag["laufend"] = projekt.beschrifte(laufend) if laufend else None
        if not tor_an:
            eintrag.update(stand=jetzt, gefunden=None, grund="tor_aus",
                           laeuft=laeuft)
            return
        # Zwei stille Rueckkehrpunkte standen hier -- und beide hinterliessen
        # dauerhaft "Noch nicht nachgesehen". Der Betreiber hat genau das gemeldet:
        # eine Anzeige, die seit Tagen behauptet, es sei noch nichts versucht
        # worden, obwohl es jedes Mal versucht und jedes Mal nichts wurde.
        #
        # Der Grund wird jetzt festgehalten, der STAND aber nicht: so bleibt
        # es beim naechsten Durchgang ein neuer Versuch, statt einen Tag lang
        # zu schweigen.
        if not laufend:
            # Zwei verschiedene Lagen, die frueher denselben Satz bekamen:
            # der Dienst laeuft nicht -- oder er laeuft, und nur seine
            # Fassungsnummer ist gerade nicht abrufbar.
            eintrag.update(gefunden=None, laeuft=laeuft,
                           grund="fassung_unbekannt" if laeuft
                           else "laeuft_nicht")
            return

        proxy = f"http://{konf.tor_host}:{konf.tor_http_port}"
        verfuegbar = updates.hole_versionen(proxy=proxy, projekt=projekt)
        if not verfuegbar:
            # Ueber Tor kommt das vor -- die Abfrage geht ueber drei fremde
            # Rechner. Kein Drama, aber es gehoert gesagt.
            eintrag.update(gefunden=None, grund="nicht_erreichbar",
                           laeuft=laeuft, versucht=jetzt,
                           fehlversuche=eintrag["fehlversuche"] + 1)
            return
        eintrag.update(stand=jetzt, grund="", laeuft=laeuft, versucht=jetzt,
                       fehlversuche=0,
                       neueste=projekt.beschrifte(max(verfuegbar)),
                       gefunden=updates.waehle(laufend, verfuegbar, projekt))

    def nach_updates_sehen(lage: Optional[Dict]) -> None:
        """Einmal taeglich nachsehen, ob es neuere Fassungen gibt.

        AUSSCHLIESSLICH ueber Tor. Eine solche Abfrage verraet sonst, dass hier
        jemand einen Bitcoin-Knoten betreibt -- und mit der Zeit auch, wann er
        laeuft. Ist Tor abgeschaltet, wird nicht gefragt; die Oberflaeche sagt
        dann auch, warum.

        Beide Projekte werden nacheinander geprueft. Fehlt eines -- LND laeuft
        noch nicht, Core antwortet gerade nicht --, wird das andere trotzdem
        nachgeschlagen: ein stiller Ausfall bei einem darf den anderen nicht
        mitnehmen.
        """
        jetzt = time.time()
        e = zustand.laden()
        tor_an = bool((e.knotenwahl or {}).get("tor_aktiv", True))

        # Die Kettenlage kommt vom Aufrufer: der hat sie fuer das Nachregeln
        # des Caches ohnehin schon geholt. Sie hier ein zweites Mal zu
        # erfragen waere alle zehn Minuten ein RPC-Aufruf fuer nichts.
        # Die Kennung wird GEMERKT, nicht bei jedem Ausfall vergessen.
        #
        # Sie kommt aus getnetworkinfo.subversion -- also aus dem einen
        # Aufruf, der cs_main braucht und waehrend des Erstabgleichs
        # regelmaessig ausfaellt. Ohne Gedaechtnis stand deshalb im
        # Update-Kasten "Bitcoin Core laeuft hier noch nicht", waehrend der
        # Knoten sichtbar die Kette lud. Eine Fassungsnummer aendert sich
        # aber nur, wenn jemand das Abbild tauscht -- die letzte bekannte
        # ist also richtig, bis eine neue kommt.
        if (lage or {}).get("kennung"):
            kennungsspeicher["wert"] = lage["kennung"]
        core = updates.laufende_version(kennungsspeicher["wert"])
        # "laeuft" heisst: der Dienst ist da. Dass wir seine Nummer gerade
        # nicht kennen, ist etwas anderes -- und antwortet bitcoind
        # ueberhaupt, dann laeuft es.
        eine_pruefung(updates.BITCOIN_CORE, core,
                      lage is not None or bool(kennungsspeicher["wert"]),
                      tor_an, jetzt)

        lnd, lnd_laeuft = lnd_fassung()
        eine_pruefung(updates.LND, lnd, lnd_laeuft, tor_an, jetzt)

    def _kurs_holen(waehrung: str = "usd",
                    zeitraum: str = kurs.VORGABE_ZEITRAUM,
                    erzwingen: bool = False) -> None:
        """Auffangbuegel um den Kursabruf. Er darf nichts mitreissen."""
        try:
            kurstafel.einmal_holen(waehrung, zeitraum, erzwingen)
        except Exception:                                        # nosec B902
            log.exception("Kursabruf fehlgeschlagen")

    def _kurs_auffrischen() -> None:
        """Was der Waechter im Fuenf-Minuten-Takt holt.

        Vorher: _kurs_holen() ohne Argument, also FEST Dollar. Wer die
        Oberflaeche auf Euro stehen hatte, bekam damit nie einen frischen
        Eurokurs -- die Tafel hielt dauerhaft Dollar und lieferte ihn unter
        dem Euro-Zeichen aus. Jetzt wird das aufgefrischt, was tatsaechlich
        angesehen wird; die Tafel deckelt die Zahl selbst, damit ueber Tor
        nicht ein Dutzend Kreise je Durchgang aufgehen.
        """
        for waehrung, zeitraum in kurstafel.in_gebrauch():
            _kurs_holen(waehrung, zeitraum)

    def nachrichten_holen() -> None:
        """Stuendlich die Feeds abrufen -- wenn eingeschaltet und Tor laeuft.

        KEIN eigener Container und kein eigener Faden: das haengt an
        demselben Waechter wie die Versionspruefung und geht denselben Weg
        nach draussen. Dazu aus dem Betrieb am 06.09.2026: "nicht wieder ein neues
        Docker-Stack draus machen, das soll dann so in der App laufen."

        Der Feed entscheidet selbst, ob er faellig ist. Eine Ausnahme darf
        den Waechter nicht mitnehmen -- an ihm haengen die Adressnachfuehrung
        und die Kanalsicherung.
        """
        try:
            feed.einmal_holen(kartenbuch.get("heimat"))
            if time.time() - nachrichtenstand["aufgeraeumt"] > 24 * 3600:
                nachrichtenstand["aufgeraeumt"] = time.time()
                auswertung.nachrichten_aufraeumen()
        except Exception:                                        # nosec B902
            log.exception("Nachrichtenabruf fehlgeschlagen")

    def karte_auffrischen() -> None:
        """Das Adressbuch neu auswerten -- halbstuendlich.

        Der einzige teure Aufruf der Anwendung: getnodeaddresses liefert
        zehntausende Eintraege. Deshalb laeuft er hier im Hintergrund und
        nicht, wenn jemand die Karte oeffnet.
        """
        jetzt = time.time()
        stand = kartenbuch["stand"]
        if stand and jetzt - stand < karte.BUCH_INTERVALL_SEKUNDEN:
            return
        if kartenbuch["laeuft"]:
            return          # laeuft schon -- nicht zweimal gleichzeitig
        kartenbuch["laeuft"] = True
        try:
            verbindung = knotenverbindung()
            buch = karte.adressbuch(verbindung, ortstabelle)
            if not buch["bekannt"]:
                return      # Knoten antwortet nicht -- altes Buch behalten
            kartenbuch.update(stand=jetzt, daten=buch)
            # Zwei billige RPC-Aufrufe, kein Weg nach draussen. Bleibt es
            # None -- etwa weil der Knoten nur ueber Tor laeuft und seinen
            # Standort bewusst nicht preisgibt --, bekommt der Feed die
            # internationalen englischen Quellen. Das ist dann auch richtig.
            try:
                heimat = karte.eigener_ort(verbindung, ortstabelle)
                if heimat:
                    kartenbuch["heimat"] = heimat
            except Exception:                                    # nosec B902
                log.debug("Heimatland nicht bestimmbar", exc_info=True)
        finally:
            kartenbuch["laeuft"] = False

    def starte_buchauswertung() -> None:
        """Die Auswertung im Hintergrund anstossen, ohne auf sie zu warten."""
        if kartenbuch["laeuft"]:
            return

        im_hintergrund("adressbuch", karte_auffrischen)

    def tor_nachziehen() -> bool:
        """Die torrc auf den Stand bringen, der zur Wahl und zum Abbild gehoert.

        Geschrieben wurde sie frueher genau EINMAL, im Assistenten. Jede
        spaetere Verbesserung erreichte damit nur, wer danach neu einrichtete;
        ein neues Abbild half ausdruecklich NICHT: die Vorlage liegt im
        Abbild, die geltende Datei im Volume. Am 29.08.2026 lief deshalb die
        Versionsabfrage alle zehn Minuten gegen einen HTTP-Tunnel, den des Betreibers
        Tor gar nicht kannte:

            Versionsabfrage (bitcoind) nach 3 Versuchen aufgegeben:
            URLError: <urlopen error [Errno 111] Connection refused>

        Seit 0.63.0 traegt die torrc ausserdem die Onion-Dienste -- welche,
        folgt der Sichtbarkeit. Weicht die Datei ab, wird sie erneuert; der
        Waechter im Container sieht die neue Pruefsumme und startet Tor einmal
        geordnet neu.
        """
        try:
            e = zustand.laden()
            if not e.eingerichtet:
                return False
            wege = _nach_sichtbarkeit(_wege(e.knotenwahl))
            if not wege["tor"]:
                return False    # abgeschaltet -- dann gibt es nichts zu pflegen
            return _tor_ablegen(wege)
        except Exception:                                        # nosec B902
            log.exception("Erneuern der Tor-Konfiguration fehlgeschlagen")
            return False

    # Der alte Name bleibt als Einsprung fuer den Pruefstand.
    vorlagen_nachziehen = tor_nachziehen

    app.state.vorlagen_nachziehen = vorlagen_nachziehen

    def einmal_nachsehen() -> None:
        """Ein Durchgang des Waechters. Laeuft vollstaendig in einem Thread."""
        if not zustand.laden().eingerichtet:
            # Vorher gibt es weder eine Konfiguration noch einen Knoten -- und
            # knotenverbindung() wuerde RPC-Zugangsdaten anlegen, bevor der
            # Nutzer den Assistenten ueberhaupt gesehen hat.
            return
        # ZUERST, was nur Dateien braucht -- und zwar vor jeder RPC-Abfrage.
        # Nach dem Update auf 0.63.0 laesst bitcoind die Anwendung erst
        # wieder herein, wenn rpcallowip das feste Netz kennt.
        tor_neu = tor_nachziehen()
        if tor_neu:
            wege = _nach_sichtbarkeit(_wege(zustand.laden().knotenwahl))
            dienste = onion.dienste_fuer(wege["tor"], wege["sichtbarkeit"])
            gefunden = onion.abwarten(konf.fast, dienste,
                                      ONION_FRIST_WAECHTER_SEKUNDEN)
            fehlt = [n for n, a in gefunden.items() if not a]
            if fehlt:
                log.warning("Tor hat nach %.0f s noch keine Adresse fuer %s "
                            "hinterlegt -- sie kommt beim naechsten "
                            "Durchgang.", ONION_FRIST_WAECHTER_SEKUNDEN,
                            ", ".join(fehlt))
        netz_neu = bitcoind_netz_nachziehen()
        if tor_neu or netz_neu:
            lightning_adressen_sicherstellen()
            # Tor oder bitcoind fahren gerade neu hoch. Die Versionsabfrage
            # laeuft ueber Tor, die Lage ueber bitcoind -- beides haette in
            # diesem Takt keine Aussicht.
            return
        if adresse_nachfuehren():
            return          # nicht im selben Durchgang zweimal neu starten

        # Nachrichten und Kurs ZUERST. Sie brauchen nur Tor und haben mit
        # bitcoind nichts zu tun -- sie hinter rpc.kettenlage() zu haengen
        # hiess, dass sie waehrend eines haengenden oder fehlschlagenden
        # Erstabgleichs gar nicht liefen. Eine Abhaengigkeit, die es in der
        # Sache nicht gibt.
        nachrichten_holen()
        _kurs_auffrischen()

        lage = rpc.kettenlage(knotenverbindung())
        if lage is not None:
            konfiguration_nachregeln(lage)
            # Erst nach dem Nachregeln: steht die Kette, hat bitcoind in
            # diesem Durchgang womoeglich gerade eine neue Konfiguration
            # bekommen. LND danach zu wecken kostet nichts und haelt die
            # Reihenfolge, in der die Dienste voneinander abhaengen.
            lightning_bereitstellen(lage)
        # Und danach: stimmt die lnd.conf noch mit dem ueberein, was
        # eingestellt ist? Bis zum 10.09.2026 wurde das nur gefragt, wenn
        # sich bei bitcoind etwas geaendert hatte -- und LND blieb stehen,
        # wo es stand.
        lightning_adressen_sicherstellen()
        nach_updates_sehen(lage)
        macaroon_sicherstellen(lndverbindung())
        sicherung_nachziehen()
        karte_auffrischen()
        aufraeumen_wenn_faellig()
        gebuehren_wenn_faellig()

    # Der Waechter laeuft sonst nur als Hintergrundaufgabe, alle paar Minuten.
    # Damit war seine Logik von aussen nicht ansprechbar und blieb ungeprueft --
    # ausgerechnet die Stelle, die eine laufende Konfiguration umschreibt und
    # bitcoind neu startet.
    app.state.einmal_nachsehen = einmal_nachsehen
    # Auch der Sammler von aussen ansprechbar: seit dem 08.09.2026 haengt die
    # Lightning-Einrichtung an ihm, und die gehoert geprueft.
    app.state.lage_auffrischen = lage_auffrischen
    # Damit der Pruefstand die Dauerlaeufer beenden kann: dort laeuft das
    # Herunterfahren der App nie (TestClient ohne "with"), und ein Faden, den
    # niemand anhaelt, arbeitet in den naechsten Testfall hinein.
    app.state.hintergrund_stoppen = hintergrund_einholen

    aufraeumstand = {"zuletzt": 0.0}

    def aufraeumen_wenn_faellig() -> None:
        """Einmal am Tag die alten Transaktionszeilen wegwerfen.

        Bloecke bleiben dauerhaft -- die sind klein und werden mit den Jahren
        erst interessant. Die einzelnen Transaktionen nicht: bei 400.000 am
        Tag waere die Datei nach einem Jahr unbrauchbar gross.
        """
        jetzt = time.time()
        if jetzt - aufraeumstand["zuletzt"] < 24 * 3600:
            return
        aufraeumstand["zuletzt"] = jetzt
        auswertung.aufraeumen()



    async def lagesammler() -> None:
        """Haelt die Kettenlage frisch, damit kein Aufruf mehr wartet.

        Das ist die Antwort auf die Frage aus dem Betrieb vom 04.09.2026, wo denn "die
        Daten zur Bereitstellung liegen". Ab hier: hier. Die Schnittstelle
        liest nur noch ab.
        """
        while True:
            try:
                await asyncio.to_thread(lage_auffrischen)
            except Exception:                                    # nosec B902
                # Eine Ausnahme wuerde den Sammler beenden -- und damit die
                # ganze Anzeige einfrieren, ohne ein Wort im Protokoll.
                log.exception("Sammler-Durchlauf fehlgeschlagen")
            await asyncio.sleep(SAMMLER_TAKT_SEKUNDEN)

    async def adresswaechter() -> None:
        # ERST kurz warten, dann arbeiten -- und nicht zehn Minuten. Bisher
        # stand der sleep am Schleifenanfang mit der vollen Frist: nach jedem
        # Neustart geschah zehn Minuten lang gar nichts. Das betrifft mehr als
        # Lightning; auch die Indizes werden hier wieder eingeschaltet.
        #
        # Die halbe Minute ist Absicht: bitcoind laedt beim Start den
        # chainstate und antwortet vorher nicht. Wer sofort fragt, bekommt
        # keine Lage und muesste doch wieder warten.
        wartezeit = ERSTER_WAECHTERLAUF_SEKUNDEN
        while True:
            await asyncio.sleep(wartezeit)
            wartezeit = dyndns.INTERVALL_SEKUNDEN
            try:
                await asyncio.to_thread(einmal_nachsehen)
            except Exception:                                    # nosec B902
                # Eine Ausnahme hier wuerde den Task beenden -- und damit
                # WORTLOS auch die Adressnachfuehrung, fuer immer. Der Knoten
                # wuerbe dann nach der naechsten Zwangstrennung dauerhaft mit
                # einer fremden Adresse.
                log.exception("Waechter-Durchlauf fehlgeschlagen")

    @app.on_event("startup")
    async def _starte_waechter() -> None:
        # Die erste Zeile im Protokoll sagt, WAS hier laeuft. Bisher fing es
        # mit geladenen Tabellen an -- richtig, aber nicht das, was jemand
        # sucht, der wissen will, welche Fassung mit welchen Einstellungen
        # gerade arbeitet.
        e = zustand.laden()
        log.info(
            "SatoshiCortex %s startet -- %s, Sichtbarkeit %s%s.",
            konf.version,
            "eingerichtet" if e.eingerichtet else "noch nicht eingerichtet",
            _sichtbarkeit_von(e.knotenwahl or {}),
            (", Wallet-Software aus " + (e.knotenwahl or {}).get("rpc_heimnetz", ""))
            if (e.knotenwahl or {}).get("rpc_heimnetz") else "",
        )

        # Gleich beim Start, nicht erst nach zehn Minuten: wer eine neue
        # Fassung einspielt, hat eine veraltete Dienstkonfiguration damit
        # sofort weg statt nach dem ersten Waechterlauf. Es ist ein
        # Dateivergleich -- im Normalfall passiert dabei gar nichts.
        vorlagen_nachziehen()

        # Nachrichten und Kurs gleich beim Start holen, nicht erst beim
        # ersten Waechterlauf. Der Zustand je Quelle liegt nur im
        # Arbeitsspeicher; nach einem Neustart stand deshalb bei JEDER Quelle
        # "noch nicht abgerufen", bis zu zehn Minuten lang. Das sah aus wie
        # ein Defekt und war keiner.
        #
        # Der Faden wird gemerkt und beim Herunterfahren eingeholt. Ohne das
        # ueberlebt er den Dienst, der ihn gestartet hat -- am 10.09.2026 in
        # der Pruefung gesehen: der Faden eines beendeten Testfalls rief
        # nachrichten.hole() waehrend eines SPAETEREN auf, landete in dessen
        # Attrappe und liess sie zwei Abrufe zaehlen statt einem. Im Betrieb
        # ist es dasselbe in gross: ein halb gelaufener Abruf schreibt in
        # einen Zustand, den gerade niemand mehr betreut.
        im_hintergrund("nachrichten-start",
                       lambda: (nachrichten_holen(), _kurs_auffrischen()))

        app.state.waechter = asyncio.create_task(adresswaechter())
        # Sofort loslaufen, nicht erst nach dem ersten Takt: die erste Runde
        # ist die, auf die die Oberflaeche nach einem Neustart wartet.
        app.state.sammler = asyncio.create_task(lagesammler())

        # Ohne Ablage gibt es nichts zu sammeln -- dann faengt der Zulauf gar
        # nicht erst an, statt ins Leere zu schreiben.
        if not auswertung.verfuegbar:
            return

        # Der Zulauf laeuft in einem eigenen Faden, nicht in der Ereignis-
        # schleife: er wartet auf ZMQ-Nachrichten und macht dabei RPC-Aufrufe.
        # Beides blockiert, und beides gehoert damit nicht dorthin, wo die
        # Oberflaeche bedient wird.
        strom = zulauf.Zulauf(
            auswertung, knotenverbindung,
            f"tcp://{konf.bitcoind_host}:{konf.zmq_sequence_port}",
            poolliste)
        app.state.zulauf = strom
        strom.start()

    @app.on_event("shutdown")
    async def _stoppe_waechter() -> None:
        # Kurz, nicht ewig: die Faeden haengen an fremden Rechnern, und ein
        # Container, der beim Stoppen wartet, wird nach zehn Sekunden
        # abgewuergt.
        hintergrund_einholen(5.0)

        for name in ("waechter", "sammler"):
            aufgabe = getattr(app.state, name, None)
            if aufgabe:
                aufgabe.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await aufgabe

        strom = getattr(app.state, "zulauf", None)
        if strom:
            strom.beende()
            # Kurz warten, damit Angefangenes noch geschrieben wird -- aber
            # nicht ewig: ein Container, der beim Stoppen haengt, wird nach
            # zehn Sekunden abgewuergt, und dann ist gar nichts gesichert.
            strom.join(timeout=5)

    # ── Antworten der Schnittstelle sind NIE zwischenspeicherbar ──────────
    #
    # Fuer die statischen Dateien steht die Lehre schon weiter unten -- sie
    # hat beim Rollout eine Stunde gekostet. Fuer die API wurde sie nie
    # gezogen: sie sendete gar keine Cache-Angabe.
    #
    # "Gar keine" heisst NICHT "nicht zwischenspeichern". RFC 9111 Abschnitt 3
    # erlaubt das Ablegen jeder Antwort mit einem Statuscode, der
    # "heuristically cacheable" ist -- 200 gehoert dazu. Und Abschnitt 4.2.2:
    # "A cache MAY assign a heuristic expiration time when an explicit time is
    # not specified, employing algorithms that use other field values (such as
    # the Last-Modified time) to estimate a plausible expiration time."
    #
    # Genau das erklaert des Betreibers Befund vom 01.09.2026: gespeicherte
    # Einstellungen waren nach einem Neuladen wieder die alten. Das Ablegen
    # war in Ordnung -- am echten Backend ueber einen vollstaendigen Neustart
    # geprueft -- und die ausgelieferten Dateien waren byte-identisch mit der
    # Fassung. Es war das GET danach: der Browser durfte es aus seinem eigenen
    # Zwischenspeicher beantworten und tat es.
    #
    # Die drei Kopfzeilen sind die uebliche Kombination (so etwa in
    # discord/access, api/middleware.py): no-store fuer alles ab HTTP/1.1,
    # Pragma und Expires fuer alles davor und fuer Zwischenstationen, die
    # sich nicht daran halten.
    @app.middleware("http")
    async def keine_zwischenspeicherung(anfrage, weiter):
        antwort = await weiter(anfrage)
        if anfrage.url.path.startswith("/api/"):
            antwort.headers["Cache-Control"] = "no-store, max-age=0"
            antwort.headers["Pragma"] = "no-cache"
            antwort.headers["Expires"] = "0"
        return antwort

    # ── Die Regel, dass nichts von aussen nachgeladen wird ─────────────
    #
    # Aus dem Betrieb, 08.09.2026: "mit google wollen wir nix zu tun haben .. wir
    # bleiben unser eigener knoten und teil des netzwerkes, jede info die wir
    # brauchen kommt aus dem netzwerk und nicht von extern."
    #
    # Nachgesehen: die Oberflaeche haelt das schon. Keine fremde Schrift, kein
    # CDN, keine Zaehlpixel -- alles liegt im Abbild, die Schriftliste nennt
    # nur, was auf dem Geraet ohnehin da ist. Aber es war eine GEWOHNHEIT und
    # keine Regel. Eine einzige spaeter eingefuegte <script src="https://...">
    # haette es still gebrochen.
    #
    # Diese Kopfzeile macht daraus eine Regel, die der BROWSER durchsetzt:
    #
    #   default-src 'self'   nichts von fremden Servern, in keiner Form
    #   img-src 'self' data: Bilder auch als Daten-URI (die Weltkarte)
    #   style-src ... 'unsafe-inline'  Stilangaben stehen an einigen
    #                        Stellen direkt am Element -- ohne diese
    #                        Erlaubnis waere die Karte farblos. Fremde
    #                        Stylesheets bleiben trotzdem draussen.
    #   connect-src 'self'   die Oberflaeche darf nur den eigenen Knoten
    #                        fragen. Was der Knoten von aussen holt --
    #                        Nachrichten, Kurs -- geht ueber Tor und nicht
    #                        ueber den Browser.
    #   frame-ancestors 'none'  niemand haengt diese Oberflaeche in einen
    #                        eigenen Rahmen.
    #
    # Bewusst OHNE 'unsafe-eval' und ohne fremde Quellen. Faellt hier je etwas
    # aus, ist das die richtige Meldung: dann hat jemand etwas eingebaut, das
    # hier nicht hingehoert.
    CSP = ("default-src 'self'; "
           "img-src 'self' data:; "
           "style-src 'self' 'unsafe-inline'; "
           "script-src 'self'; "
           "connect-src 'self'; "
           "font-src 'self'; "
           "object-src 'none'; "
           "base-uri 'self'; "
           "form-action 'self'; "
           "frame-ancestors 'none'")

    @app.middleware("http")
    async def eigene_herkunft(anfrage, weiter):
        antwort = await weiter(anfrage)
        antwort.headers.setdefault("Content-Security-Policy", CSP)
        antwort.headers.setdefault("X-Content-Type-Options", "nosniff")
        antwort.headers.setdefault("Referrer-Policy", "no-referrer")
        # Nichts davon braucht diese Anwendung -- und was man nicht braucht,
        # gibt man auch nicht frei.
        antwort.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        return antwort

    # Komprimierung. Am 04.09.2026 an dem Knoten im Betrieb gemessen: die
    # Oberflaeche sind 440 kB, und sie gingen unkomprimiert ueber die Leitung
    # -- eine Anfrage mit "Accept-Encoding: gzip" bekam Byte fuer Byte
    # dieselbe Menge zurueck. Im LAN kostet das wenig, ueber die Zoraxy-
    # Weiterleitung von aussen deutlich mehr.
    #
    # Aus dem Quelltext der ausgelieferten Fassung (starlette 1.6.0,
    # middleware/gzip.py) geprueft: komprimiert wird NUR, wenn der Browser
    # "gzip" in Accept-Encoding nennt; "Vary: Accept-Encoding" wird gesetzt,
    # damit ein Zwischenspeicher die beiden Fassungen auseinanderhaelt; und
    # Bilder, Schriften und Ereignisstroeme sind ab Werk ausgenommen.
    #
    # compresslevel bewusst 6 statt der Vorgabe 9: auf einem NAS, das
    # gleichzeitig die Blockkette prueft, ist das letzte Prozent Ersparnis
    # teurer als es wert ist.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

    app.include_router(api)

    # Die Oberflaeche. Fehlt sie (etwa beim Entwickeln am Backend), bleibt die
    # Schnittstelle trotzdem benutzbar -- der Container soll deswegen nicht
    # scheitern.
    web = Path(__file__).resolve().parents[2] / "web"
    if web.is_dir():

        @app.get("/{pfad:path}", include_in_schema=False)
        def oberflaeche(pfad: str):
            # Unbekannte API-Pfade duerfen nicht als Startseite durchgehen --
            # ein Client wuerde HTML als Antwort missdeuten.
            if pfad.startswith("api/"):
                raise HTTPException(404, {"meldung": "unbekannt"})
            ziel = (web / pfad).resolve()
            # Kein Ausbruch aus dem Web-Verzeichnis ueber ../ im Pfad.
            if pfad and web in ziel.parents and ziel.is_file():
                # no-cache heisst NICHT "nicht zwischenspeichern", sondern
                # "vor der Wiederverwendung nachfragen". Der Browser schickt
                # dann seinen ETag mit und bekommt meist ein 304 zurueck --
                # billig, aber er bemerkt eine neue Fassung sofort.
                #
                # Ohne das behaelt er app.js und style.css nach einem Update
                # einfach, ohne auch nur zu fragen. Beim Rollout hat das eine
                # Stunde gekostet: der Container lieferte die reparierte
                # Fassung aus, der Browser zeigte weiter die kaputte, und im
                # Protokoll tauchte nicht einmal eine Anfrage fuer app.js auf.
                return FileResponse(ziel, headers={"Cache-Control": "no-cache"})
            # Auch der Rueckfall braucht die Kopfzeile -- und zwar am
            # noetigsten. "/" ist der Weg, den ein Mensch tatsaechlich
            # aufruft; "/index.html" tippt niemand. Am 03.09.2026 stand
            # deshalb genau hier die Luecke: die benannten Dateien waren
            # versorgt, die Startseite nicht. Safari durfte sie nach RFC 9111
            # Abschnitt 4.2.2 nach eigenem Ermessen aufheben und lieferte beim
            # Neuladen eine Huelle aus, deren Gegenstelle es nicht mehr gab.
            return FileResponse(web / "index.html",
                                headers={"Cache-Control": "no-cache"})

    return app
