"""Der QR-Code der Einzahladresse (app/web/qr.js).

Aus dem Betrieb, 15.09.2026: "aus ner bitcoin adresse mal direkt nen QR code machen
... zum scannen macht das ueberweissen einfacher".

Ein QR-Code, der falsch gerechnet ist, scannt entweder gar nicht -- oder, und
das waere schlimmer, er scannt etwas anderes. Deshalb zweierlei:

* feste Werte aus der Norm (Kapazitaeten, Format- und Versionsinformation,
  das Reed-Solomon-Beispiel "HELLO WORLD" 1-M), gegen die qr.js rechnen muss;
* ein Zuruecklesen: der erzeugte Code wird hier in Python Modul fuer Modul
  gelesen, entmaskiert, entschraenkt, seine Fehlerkorrektur mit einer EIGENEN
  Reed-Solomon-Rechnung nachgeprueft und der Text zurueckgewonnen.

Ist node nicht da, wird uebersprungen statt falsch gruen gemeldet.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

QR_JS = Path(__file__).resolve().parents[2] / "web" / "qr.js"


def _node(ausdruck):
    node = shutil.which("node")
    if not node:
        pytest.skip("node nicht vorhanden -- die CI prueft es trotzdem")
    skript = (f"const QR = require({json.dumps(str(QR_JS))});"
              f"process.stdout.write(JSON.stringify({ausdruck}));")
    lauf = subprocess.run([node, "-e", skript], capture_output=True,
                          text=True, timeout=60)
    assert lauf.returncode == 0, lauf.stderr
    return json.loads(lauf.stdout)


# ── Feste Werte der Norm ────────────────────────────────────────────────────

def test_die_kapazitaeten_stimmen_mit_der_norm():
    """Byte-Modus, Stufe M, Versionen 1 bis 10 (ISO/IEC 18004, Tabelle 7)."""
    assert _node("[1,2,3,4,5,6,7,8,9,10].map((v) => QR._kapazitaet(v))") == [
        14, 26, 42, 62, 84, 106, 122, 152, 180, 213]


def test_die_alphanumerischen_kapazitaeten_stimmen_auch():
    """Zwei Zeichen in 11 Bit -- deshalb passt eine Lightning-Rechnung in
    Grossbuchstaben hinein, im Byte-Modus aber nicht."""
    assert _node("[1,2,3,4,5,6,7,8,9,10].map((v) => QR._kapazitaet(v, true))") == [
        20, 38, 61, 90, 122, 154, 178, 221, 262, 311]


def test_die_kapazitaeten_bis_version_20_stimmen_mit_der_norm():
    """Seit dem 26.09.2026 geht der Rechner bis Version 20: ein Schluessel
    fuer eine externe Wallet (lndconnect) ist rund 450 Zeichen lang und
    passt in Version 10 nicht hinein. Werte aus ISO/IEC 18004, Tabelle 7,
    Stufe M."""
    versionen = list(range(11, 21))
    assert _node(f"{versionen}.map((v) => QR._kapazitaet(v))") == [
        251, 287, 331, 362, 412, 450, 504, 560, 624, 666]
    assert _node(f"{versionen}.map((v) => QR._kapazitaet(v, true))") == [
        366, 419, 483, 528, 600, 656, 734, 816, 909, 970]


def test_der_modus_wird_am_inhalt_erkannt():
    assert _node('QR._istAlnum("LNBC1500N1PBEISPIEL")') is True
    assert _node('QR._istAlnum("lnbc1500n1pbeispiel")') is False
    assert _node('QR.matrix("LNBC1500N1PBEISPIEL").modus') == "alnum"
    assert _node('QR.matrix("bitcoin:bc1qar0srrr").modus') == "byte"


def test_die_formatinformation_stimmt_fuer_alle_masken():
    assert _node("[0,1,2,3,4,5,6,7].map(QR._formatBits)") == [
        0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0]


def test_die_versionsinformation_stimmt():
    assert _node("[7,8,9,10].map(QR._versionsBits)") == [
        0x07C94, 0x085BC, 0x09A99, 0x0A4D3]


HELLO_DATEN = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17,
               236, 17]
HELLO_ECC = [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


def test_reed_solomon_rechnet_das_beispiel_der_norm():
    assert _node(f"QR._rsRest({HELLO_DATEN}, 10)") == HELLO_ECC


# ── Eine eigene Reed-Solomon-Rechnung, um qr.js nicht mit sich selbst zu
#    pruefen: Logarithmentafeln und Polynomdivision statt des Teiler-Verfahrens
#    in qr.js. ─────────────────────────────────────────────────────────────────

EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _rs_rest(daten, grad):
    erzeuger = [1]
    for i in range(grad):
        neu = [0] * (len(erzeuger) + 1)
        for j, k in enumerate(erzeuger):
            neu[j] ^= k
            neu[j + 1] ^= _gmul(k, EXP[i])
        erzeuger = neu
    nachricht = list(daten) + [0] * grad
    for i in range(len(daten)):
        faktor = nachricht[i]
        if faktor:
            for j in range(1, len(erzeuger)):
                nachricht[i + j] ^= _gmul(erzeuger[j], faktor)
    return nachricht[len(daten):]


def test_die_eigene_reed_solomon_rechnung_stimmt_auch():
    assert _rs_rest(HELLO_DATEN, 10) == HELLO_ECC


# ── Zuruecklesen ────────────────────────────────────────────────────────────

ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
# Stufe M, je Version die Bloecke der Norm (ISO/IEC 18004, Tabelle 9) als
# (Anzahl, Codewoerter je Block, davon Daten) -- bewusst in DIESER Form und
# nicht als die zwei Zahlenreihen, die qr.js fuehrt. Daraus abgeleitet sind
# ECC je Block und Blockzahl ein unabhaengiger Vergleich: ein Tippfehler in
# qr.js faellt beim Zuruecklesen auf, statt sich hier zu wiederholen.
BLOCKTABELLE_M = {
    1: [(1, 26, 16)], 2: [(1, 44, 28)], 3: [(1, 70, 44)],
    4: [(2, 50, 32)], 5: [(2, 67, 43)], 6: [(4, 43, 27)],
    7: [(4, 49, 31)], 8: [(2, 60, 38), (2, 61, 39)],
    9: [(3, 58, 36), (2, 59, 37)], 10: [(4, 69, 43), (1, 70, 44)],
    11: [(1, 80, 50), (4, 81, 51)], 12: [(6, 58, 36), (2, 59, 37)],
    13: [(8, 59, 37), (1, 60, 38)], 14: [(4, 64, 40), (5, 65, 41)],
    15: [(5, 65, 41), (5, 66, 42)], 16: [(7, 73, 45), (3, 74, 46)],
    17: [(10, 74, 46), (1, 75, 47)], 18: [(9, 69, 43), (4, 70, 44)],
    19: [(3, 70, 44), (11, 71, 45)], 20: [(3, 67, 41), (13, 68, 42)],
}
ECC_M = [0] + [BLOCKTABELLE_M[v][0][1] - BLOCKTABELLE_M[v][0][2]
               for v in range(1, 21)]
BLOECKE_M = [0] + [sum(g[0] for g in BLOCKTABELLE_M[v]) for v in range(1, 21)]


def _roh_module(v):
    n = (16 * v + 128) * v + 64
    if v >= 2:
        a = v // 7 + 2
        n -= (25 * a - 10) * a - 55
        if v >= 7:
            n -= 36
    return n


def _maskiert(maske, x, y):
    return [
        (x + y) % 2 == 0,
        y % 2 == 0,
        x % 3 == 0,
        (x + y) % 3 == 0,
        (x // 3 + y // 2) % 2 == 0,
        (x * y) % 2 + (x * y) % 3 == 0,
        ((x * y) % 2 + (x * y) % 3) % 2 == 0,
        ((x + y) % 2 + (x * y) % 3) % 2 == 0,
    ][maske]


def _bch_format(daten):
    rest = daten
    for _ in range(10):
        rest = (rest << 1) ^ ((rest >> 9) * 0x537)
    return ((daten << 10) | rest) ^ 0x5412


def _lies(erg):
    m, fest, n = erg["module"], erg["fest"], erg["groesse"]
    v = (n - 17) // 4

    def bit(x, y):
        return 1 if m[y][x] else 0

    # Suchmuster links oben: Rand dunkel, Ring hell, Kern dunkel.
    assert all(m[0][x] and m[6][x] for x in range(7))
    assert not any(m[1][x] for x in range(1, 6))
    assert all(m[y][x] for y in range(2, 5) for x in range(2, 5))
    # Taktlinie und das immer dunkle Modul.
    assert [m[6][x] for x in range(8, n - 8)] == \
        [x % 2 == 0 for x in range(8, n - 8)]
    assert m[n - 8][8]

    # Formatinformation: beide Kopien lesen, sie muessen gleich und gueltig sein.
    f1 = sum(bit(8, i) << i for i in range(6))
    f1 |= bit(8, 7) << 6 | bit(8, 8) << 7 | bit(7, 8) << 8
    f1 |= sum(bit(14 - i, 8) << i for i in range(9, 15))
    f2 = sum(bit(n - 1 - i, 8) << i for i in range(8))
    f2 |= sum(bit(8, n - 15 + i) << i for i in range(8, 15))
    assert f1 == f2
    daten = (f1 ^ 0x5412) >> 10
    assert _bch_format(daten) == f1
    assert daten >> 3 == 0, "Stufe muss M sein"
    maske = daten & 7

    if v >= 7:
        versions = sum(bit(n - 11 + i % 3, i // 3) << i for i in range(18))
        gespiegelt = sum(bit(i // 3, n - 11 + i % 3) << i for i in range(18))
        assert versions == gespiegelt
        assert versions >> 12 == v

    # Datenmodule im Zickzack lesen und entmaskieren.
    bits = []
    rechts = n - 1
    while rechts >= 1:
        if rechts == 6:
            rechts = 5
        aufwaerts = ((rechts + 1) & 2) == 0
        for schritt in range(n):
            for j in range(2):
                x = rechts - j
                y = n - 1 - schritt if aufwaerts else schritt
                if not fest[y][x]:
                    bits.append(bit(x, y) ^ (1 if _maskiert(maske, x, y) else 0))
        rechts -= 2
    roh = _roh_module(v) // 8
    woerter = [int("".join(map(str, bits[i * 8:i * 8 + 8])), 2)
               for i in range(roh)]

    # Entschraenken: erst die Datenbytes aller Bloecke, dann die ECC-Bytes.
    anzahl, ecc = BLOECKE_M[v], ECC_M[v]
    kurze = anzahl - roh % anzahl
    kurz_laenge = roh // anzahl
    laengen = [kurz_laenge - ecc + (0 if i < kurze else 1)
               for i in range(anzahl)]
    bloecke = [[] for _ in range(anzahl)]
    pos = 0
    for i in range(max(laengen)):
        for j in range(anzahl):
            if i < laengen[j]:
                bloecke[j].append(woerter[pos])
                pos += 1
    ecc_bloecke = [[] for _ in range(anzahl)]
    for _ in range(ecc):
        for j in range(anzahl):
            ecc_bloecke[j].append(woerter[pos])
            pos += 1
    assert pos == roh
    # Und die Laengen der Datenbloecke genau so, wie die Norm sie vorgibt.
    assert laengen == [daten for anzahl_g, _, daten in BLOCKTABELLE_M[v]
                       for _ in range(anzahl_g)]
    for block, korrektur in zip(bloecke, ecc_bloecke):
        assert _rs_rest(block, ecc) == korrektur

    # Den Text aus den Datenbytes.
    datenbits = "".join(f"{b:08b}" for block in bloecke for b in block)
    modus = datenbits[:4]
    assert modus in ("0100", "0010"), f"unbekannter Modus {modus}"
    if modus == "0100":
        zaehler = 8 if v < 10 else 16
        laenge = int(datenbits[4:4 + zaehler], 2)
        start = 4 + zaehler
        inhalt = bytes(int(datenbits[start + 8 * i:start + 8 * i + 8], 2)
                       for i in range(laenge))
        return inhalt.decode("utf-8")
    # Alphanumerisch: zwei Zeichen in 11 Bit, ein uebriges in 6.
    zaehler = 9 if v < 10 else 11
    laenge = int(datenbits[4:4 + zaehler], 2)
    pos = 4 + zaehler
    zeichen = []
    while len(zeichen) < laenge:
        if laenge - len(zeichen) >= 2:
            wert = int(datenbits[pos:pos + 11], 2)
            zeichen.append(ALNUM[wert // 45])
            zeichen.append(ALNUM[wert % 45])
            pos += 11
        else:
            zeichen.append(ALNUM[int(datenbits[pos:pos + 6], 2)])
            pos += 6
    return "".join(zeichen)


TAPROOT = "bitcoin:bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusxg3297"
SEGWIT = "bitcoin:bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
KOMPATIBEL = "bitcoin:3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"


RECHNUNG = (
    "LNBC2500U1PVJLUEZPP5QQQSYQCYQ5RQWZQFQQQSYQCYQ5RQWZQFQQQSYQCYQ5RQWZQFQYPQ"
    "DQ5XYSXXATSYP3K7ENXV4JSXQZPUAZTRNWNGZN3KDZW5HYDLZF03QDGM2HDQ27CQV3AGM2AW"
    "HZ5SE903VRUATFHQ77W3LS4EVS3CH9ZW97J25EMUDUPQ63NYW24CG27H2RSPFJ9SRP").upper()
RECHNUNG_LANG = (RECHNUNG
                 + "XQZPUAZTRNWNGZN3KDZW5HYDLZF03QDGM2HDQ27CQV3AGM2AWHZ5SE903"
                   "VRUATFHQ77W3LS4EV")

# Aufbau wie ein echter Verbindungstext fuer Zeus: Onion-Adresse, Port, ein
# Macaroon in base64url. Alles ausgedacht -- nur die Laenge ist die eines
# gebackenen Schluessels mit vollen Rechten.
LNDCONNECT = ("lndconnect://" + "x" * 56 + ".onion:8080?macaroon="
              + "AgEDbG5kAvgBAwoQ" * 25)

@pytest.mark.parametrize("text,version", [
    (TAPROOT, 5),
    (SEGWIT, 4),             # 8 + 42 = 50 Byte, Version 3-M fasst nur 42
    (KOMPATIBEL, 3),
    ("x" * 150, 8),          # ab Version 7 mit Versionsinformation
    ("y" * 213, 10),         # das groesste, was im Byte-Modus hineinpasst
    (RECHNUNG, 8),           # eine Lightning-Rechnung, alphanumerisch
    (RECHNUNG_LANG, 10),     # eine lange -- in Grossbuchstaben passt sie
    ("z" * 251, 11),         # ab hier die Versionen fuer externe Wallets
    ("z" * 252, 12),
    (LNDCONNECT, 17),        # ein Schluessel fuer Zeus, Groessenordnung echt
    ("q" * 666, 20),         # das groesste, was im Byte-Modus hineinpasst
    ("A" * 970, 20),         # und alphanumerisch
])
def test_der_code_liest_sich_zurueck(text, version):
    erg = _node(f"QR.matrix({json.dumps(text)})")
    assert erg["version"] == version
    assert erg["groesse"] == 4 * version + 17
    assert _lies(erg) == text


def test_zu_langer_text_wird_abgewiesen_statt_abgeschnitten():
    node = shutil.which("node")
    if not node:
        pytest.skip("node nicht vorhanden -- die CI prueft es trotzdem")
    skript = (f"const QR = require({json.dumps(str(QR_JS))});"
              "try { QR.matrix('z'.repeat(667)); process.exit(3); }"
              " catch (e) { process.stdout.write(e.message); }")
    lauf = subprocess.run([node, "-e", skript], capture_output=True,
                          text=True, timeout=60)
    assert lauf.returncode == 0, "ein zu langer Text wurde angenommen"
    assert "zu lang" in lauf.stdout


def test_eine_rechnung_gross_geschrieben_gibt_den_kleineren_code():
    """Eine Rechnung mit Betrag und Zweck wird schnell ueber 213 Zeichen
    lang. Klein geschrieben faellt sie in den Byte-Modus, gross geschrieben
    passt sie alphanumerisch in eine kleinere Version -- BOLT 11 sieht das
    vor, bech32 ist gegenueber Gross- und Kleinschreibung gleichgueltig.

    Bis zum 26.09.2026 war bei Version 10 Schluss, und klein geschrieben
    passte sie gar nicht. Seit der Rechner bis Version 20 geht, passt sie
    auch so -- aber dichter, und ein dichterer Code scannt schlechter.
    Deshalb schreibt die Oberflaeche sie weiterhin gross."""
    gross = _node(f"QR.matrix({json.dumps(RECHNUNG_LANG)}).version")
    klein = _node(f"QR.matrix({json.dumps(RECHNUNG_LANG.lower())}).version")
    assert gross == 10
    assert klein > gross