"""Die Coinbase eines Blocks lesen.

Die erste Transaktion jedes Blocks hat keinen echten Eingang. Ihr Eingabefeld
darf der Miner frei befuellen -- und genau das nutzen zwei Dinge, die die
Blockansicht braucht:

  * die Kennung des Mining-Pools ("/Foundry USA Pool/", "/AntPool/" ...)
  * gelegentliche Botschaften. Die beruehmteste steht im allerersten Block:
    "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks" --
    Satoshis Zeitstempel und zugleich eine Ansage.

ACHTUNG bei Block 0: Bitcoin Core verweigert die Genesis-Coinbase ueber
getrawtransaction ausdruecklich -- "The genesis block coinbase is not considered
an ordinary transaction and cannot be retrieved" (src/rpc/rawtransaction.cpp).
Die Blockansicht muss sie also ueber getblock holen. Seit Core 31 liefert
getblock ohnehin ein coinbase_tx-Objekt mit; darueber geht es fuer alle Bloecke
gleich, und ausgerechnet der beruehmteste Block bricht nicht mit einer
raetselhaften Meldung ab.

Das Feld ist ein Bitcoin-Skript, kein Text. Wer einfach alle druckbaren Zeichen
herausfischt, bekommt Muell dazu: im Genesis-Block steht vor der Nachricht das
Laengenbyte 0x45, das zufaellig ein 'E' ergibt. Deshalb laufen wir die
Anweisungen sauber ab und nehmen nur die Daten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Anweisungen, die Daten auf den Stapel legen.
OP_PUSHDATA1 = 0x4C
OP_PUSHDATA2 = 0x4D
OP_PUSHDATA4 = 0x4E
OP_16 = 0x60


@dataclass
class Datenstueck:
    daten: bytes

    @property
    def text(self) -> Optional[str]:
        """Der Inhalt als Text, falls er ueberhaupt Text ist."""
        try:
            s = self.daten.decode("utf-8")
        except UnicodeDecodeError:
            return None
        # Mindestens vier Zeichen und ueberwiegend druckbar -- sonst ist es
        # eine Zahl, ein Hash oder Zufall, der zufaellig lesbar aussieht.
        druckbar = sum(1 for z in s if 32 <= ord(z) < 127 or z in "\n\t")
        if len(s) < 4 or druckbar < len(s) * 0.9:
            return None
        return s


def zerlege(script_sig: bytes) -> List[Datenstueck]:
    """Laeuft das Skript ab und gibt die Datenstuecke zurueck.

    Bewusst nachsichtig: Coinbase-Felder muessen kein gueltiges Skript sein,
    Miner schreiben dort hinein was sie wollen. Bei Unsinn brechen wir ab und
    geben zurueck, was bis dahin gelesen wurde -- ein Fehler waere hier falsch.
    """
    stuecke: List[Datenstueck] = []
    i = 0
    n = len(script_sig)
    while i < n:
        op = script_sig[i]
        i += 1
        if op == 0 or op > OP_PUSHDATA4:
            # OP_0 und alles ab OP_1 legen keine Nutzdaten ab, die uns
            # interessieren (kleine Zahlen, Rechenanweisungen).
            continue
        if op < OP_PUSHDATA1:
            laenge = op
        elif op == OP_PUSHDATA1:
            if i >= n:
                break
            laenge = script_sig[i]; i += 1
        elif op == OP_PUSHDATA2:
            if i + 2 > n:
                break
            laenge = int.from_bytes(script_sig[i:i + 2], "little"); i += 2
        else:
            if i + 4 > n:
                break
            laenge = int.from_bytes(script_sig[i:i + 4], "little"); i += 4
        if i + laenge > n:
            break
        stuecke.append(Datenstueck(script_sig[i:i + laenge]))
        i += laenge
    return stuecke


# Fuers ERKENNEN reichen vier Zeichen: Kennungen wie "Kano" oder "HHTT" sind
# kurz. Fuers ANZEIGEN ist das zu wenig -- vier zufaellig druckbare Bytes gibt
# es in jedem zweiten Hash.
MINDESTENS_ERKENNEN = 4
MINDESTENS_ZEIGEN = 8


def spuren(script_sig_hex: str,
           mindestens: int = MINDESTENS_ERKENNEN) -> List[str]:
    """Alles Lesbare, ohne Ruecksicht auf die Skriptstruktur.

    WARUM ES DAS BRAUCHT, gemessen am 08.09.2026 an des Betreibers Bloecken
    966.077 bis 966.088: der saubere Skriptdurchlauf in zerlege() fand die
    Pool-Kennung in NUR VIER von zwoelf Bloecken. Zwei Gruende, beide
    grundsaetzlich:

    * Foundry schreibt "/Foundry USA Pool #dropgold/" ROH ins Feld, nicht als
      Datenstueck. Das fuehrende "/" ist zufaellig das Opcode 0x2f, also
      "schiebe 47 Bytes" -- so viele sind nicht mehr da, und der Durchlauf
      bricht ab. Sein Ergebnis: nichts.
    * AntPool schreibt "Mined by AntPool " und haengt acht Bytes Extranonce
      an DASSELBE Datenstueck. Von 25 Zeichen sind 17 druckbar, also 68 % --
      unter der 90-%-Schwelle in Datenstueck.text, und das Stueck fliegt raus.
      Mitsamt der Kennung, die darin steht.

    Eine Coinbase ist eben kein gueltiges Skript und muss keines sein. Fuer
    das ERKENNEN eines Pools ist Genauigkeit ohnehin zweitrangig: verglichen
    wird gegen eine bekannte Liste von Kennungen, und "Muell, in dem zufaellig
    '/AntPool/' steht" ist immer noch AntPool.

    Fuer die ANZEIGE gilt das Gegenteil -- dafuer bleibt botschaften().
    """
    try:
        roh = bytes.fromhex(script_sig_hex)
    except ValueError:
        return []
    muster = re.compile(rb"[\x20-\x7e]{%d,}" % max(1, int(mindestens)))
    return [t.decode("ascii") for t in muster.findall(roh)]


def botschaften(script_sig_hex: str) -> List[str]:
    """Die lesbaren Teile der Coinbase, in der Reihenfolge des Skripts.

    Erst der saubere Durchlauf -- er haelt den Genesis-Block frei von dem
    fuehrenden 'E', das in Wahrheit das Laengenbyte 0x45 ist. Findet er
    nichts, gilt der grobe Weg: bei modernen Coinbases ist der saubere
    Durchlauf fast immer leer, und "gar keine Botschaft" waere die falschere
    Antwort als eine mit ein wenig Rauschen daran.
    """
    try:
        roh = bytes.fromhex(script_sig_hex)
    except ValueError:
        return []
    gefunden = []
    for stueck in zerlege(roh):
        text = stueck.text
        if text:
            gefunden.append(text)
    # Mit der hoeheren Schranke: hier wird ANGEZEIGT, und vier zufaellig
    # druckbare Bytes sind keine Botschaft, sondern ein Stueck Hash.
    return gefunden or spuren(script_sig_hex, MINDESTENS_ZEIGEN)
