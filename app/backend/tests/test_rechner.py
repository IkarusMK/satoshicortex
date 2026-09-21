"""Der Umrechner rechnet -- und zwar nachweislich.

Aus dem Betrieb, 10.09.2026: "dann brauchen wir auch noch mal nen richtigen
waehrungs rechner .. damit mann auch klar kommt mit den sat und bitcoin und
waehrungen".

Die uebrigen Oberflaechen-Tests pruefen Quelltext: steht der Aufruf da, ist
der Schluessel uebersetzt. Fuer einen Rechner reicht das nicht -- eine
Umrechnung, die niemand nachgerechnet hat, ist eine Behauptung. Also werden
hier die REINEN Rechenfunktionen aus app.js herausgeloest und mit node
ausgefuehrt. Kein Browser, kein DOM, kein Testlaufwerk fuer JavaScript im
Projekt: node steht ohnehin schon in der Pruefung (node --check app.js).

Der heikle Teil ist nicht die Multiplikation, sondern das LESEN einer
getippten Zahl. "1.000" heisst auf Deutsch tausend und auf Englisch eins.
Wer das verwechselt, verrechnet sich um den Faktor tausend -- bei einem
Betrag, den jemand gleich verschicken will.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
FUNKTIONEN = ("zahlLesen", "zahlSchreiben", "rechnerUmrechnen")
KONSTANTEN = ("SAT_JE_BTC", "BTC_HOECHSTENS")


def _herausloesen() -> str:
    """Die Rechenfunktionen aus app.js schneiden -- ohne alles daneben."""
    quelle = (WEB / "app.js").read_text(encoding="utf-8")
    stuecke = []
    for name in KONSTANTEN:
        anfang = quelle.index(f"const {name} = ")
        stuecke.append(quelle[anfang:quelle.index("\n", anfang)])
    for name in FUNKTIONEN:
        anfang = quelle.index(f"function {name}(")
        # Die Funktionen stehen in Spalte 0, ihre schliessende Klammer also
        # auch. Alles dazwischen gehoert dazu.
        stuecke.append(quelle[anfang:quelle.index("\n}\n", anfang) + 2])
    return "\n".join(stuecke)


@pytest.fixture(scope="module")
def rechne():
    if not shutil.which("node"):
        pytest.skip("node nicht vorhanden")
    kern = _herausloesen()

    def lauf(aufrufe):
        skript = kern + """
const aufrufe = JSON.parse(process.argv[1]);
const raus = aufrufe.map(([name, args]) => {
  const f = { zahlLesen, zahlSchreiben, rechnerUmrechnen }[name];
  const w = f.apply(null, args);
  // NaN ueberlebt JSON nicht -- als Wort schon.
  return (typeof w === "number" && Number.isNaN(w)) ? "NaN" : w;
});
process.stdout.write(JSON.stringify(raus));
"""
        fertig = subprocess.run(
            ["node", "-e", skript, json.dumps(aufrufe)],
            capture_output=True, text=True, timeout=30)
        assert fertig.returncode == 0, fertig.stderr
        return json.loads(fertig.stdout)

    return lauf


def test_die_rechenfunktionen_sind_ueberhaupt_zu_finden():
    """Faellt der Schnitt aus, wuerde der Rest der Datei still uebersprungen
    -- und niemand merkte, dass der Rechner ungeprueft ist."""
    kern = _herausloesen()
    for name in FUNKTIONEN + KONSTANTEN:
        assert name in kern
    assert "document." not in kern, "hier darf nichts am DOM haengen"
    assert len(kern.splitlines()) > 40, "verdaechtig wenig herausgeschnitten"


# ── Getippte Zahlen lesen ──────────────────────────────────────────────────
#
# Der Faktor-tausend-Fehler wohnt genau hier.

GELESEN = [
    # Ohne Trenner
    ("1000", "de", 1000), ("1000", "en", 1000), ("0", "de", 0),
    # Der entscheidende Fall: derselbe Text, zwei Bedeutungen
    ("1.000", "de", 1000), ("1.000", "en", 1),
    ("1,000", "de", 1), ("1,000", "en", 1000),
    # Zwei Trenner: der hintere trennt die Nachkommastellen
    ("1.234,56", "de", 1234.56), ("1,234.56", "en", 1234.56),
    ("1.234.567,89", "de", 1234567.89),
    # Ein Trenner, der kein Tausenderpunkt sein kann
    ("1.5", "de", 1.5), ("1,5", "de", 1.5), (",5", "de", 0.5),
    ("100.00", "de", 100.0), ("1.0000", "de", 1.0),
    ("1234.567", "de", 1234.567),
    # Mehrere Tausendertrenner
    ("12.345.678", "de", 12345678), ("12,345,678", "en", 12345678),
    # Was Menschen beim Tippen einstreuen
    ("12 345", "de", 12345), ("12'345", "de", 12345),
    (" 1 000 ", "de", 1000),
    # Die kleinste und die groesste sinnvolle Zahl
    ("0,00000001", "de", 0.00000001), ("21000000", "de", 21000000),
    # Und was keine Zahl ist
    ("", "de", "NaN"), ("abc", "de", "NaN"), ("-5", "de", "NaN"),
    ("1,,5", "de", "NaN"), ("1.2.3", "de", "NaN"),
    ("12.34.567", "de", "NaN"), ("1e5", "de", "NaN"),
    (".", "de", "NaN"), (",", "de", "NaN"),
]


def test_getippte_zahlen_werden_gelesen_wie_gemeint(rechne):
    ergebnis = rechne([["zahlLesen", [text, spr]] for text, spr, _ in GELESEN])
    falsch = [(text, spr, ist, soll)
              for (text, spr, soll), ist in zip(GELESEN, ergebnis)
              if ist != soll]
    assert not falsch, "\n".join(
        f"{t!r} ({s}) -> {i!r}, erwartet {e!r}" for t, s, i, e in falsch)


# ── Umrechnen ──────────────────────────────────────────────────────────────

# Der Kurs aus dem Vorbild am 10.09.2026, damit die Zahlen vergleichbar sind:
# 66.468,30 Euro je Bitcoin -> 1.504 Sats fuer einen Euro.
KURS = 66468.30


def test_ein_bitcoin_sind_hundert_millionen_sats(rechne):
    d, = rechne([["rechnerUmrechnen", ["btc", 1, KURS]]])
    assert d["sat"] == 100_000_000
    assert round(d["fiat"], 2) == KURS


def test_ein_euro_sind_rund_1504_sats(rechne):
    """Gegengerechnet mit dem Vorbild, das der Betreiber verlinkt hat."""
    d, = rechne([["rechnerUmrechnen", ["fiat", 1, KURS]]])
    assert d["sat"] == 1504
    # 1 / 66468,30 = 0,0000150447... -- gerundet 1504 Sats, wie beim Vorbild.
    assert d["btc"] == pytest.approx(1 / KURS, rel=1e-12)


def test_der_weg_hin_und_zurueck_verliert_keinen_sat(rechne):
    """Ohne saubere Rundung kaeme aus 1.504 Sats "0,99999" Euro und daraus
    wieder 1.503 -- der Rechner wuerde beim Hin und Her Sats verlieren."""
    aufrufe = []
    for sat in (1, 21, 1504, 100000, 2100000, 100000000):
        aufrufe.append(["rechnerUmrechnen", ["sat", sat, KURS]])
    for sat, d in zip((1, 21, 1504, 100000, 2100000, 100000000),
                      rechne(aufrufe)):
        zurueck, = rechne([["rechnerUmrechnen", ["btc", d["btc"], KURS]]])
        assert zurueck["sat"] == sat


def test_sats_sind_ganze_zahlen(rechne):
    """Ein halber Satoshi kann on-chain nicht existieren."""
    d, e = rechne([["rechnerUmrechnen", ["sat", 1500.6, KURS]],
                   ["rechnerUmrechnen", ["btc", 0.000000005, KURS]]])
    assert d["sat"] == 1501 and isinstance(d["sat"], int)
    assert e["sat"] == 1


def test_ohne_kurs_rechnet_er_trotzdem_sats_und_bitcoin(rechne):
    """Beim ersten Oeffnen ist der Kurs noch unterwegs -- die Umrechnung
    zwischen Sats und Bitcoin braucht ihn gar nicht."""
    d, = rechne([["rechnerUmrechnen", ["sat", 100000, None]]])
    assert d["sat"] == 100000 and d["btc"] == 0.001
    assert d["fiat"] is None, "kein Kurs heisst kein Betrag, nicht null"


def test_ohne_kurs_gibt_es_aus_einem_geldbetrag_nichts_zu_rechnen(rechne):
    d, = rechne([["rechnerUmrechnen", ["fiat", 100, None]]])
    assert d is None


@pytest.mark.parametrize("feld,wert", [
    ("sat", -1), ("btc", -0.5), ("fiat", -100),
    ("btc", 21000001), ("sat", 2100000000000001),
    ("btc", "NaN"), ("quatsch", 5),
])
def test_unsinnige_eingaben_geben_kein_ergebnis(rechne, feld, wert):
    """Kein Ergebnis ist etwas anderes als das Ergebnis null -- die
    Oberflaeche unterscheidet das, und die Rechnung muss es hergeben."""
    roh = None if wert == "NaN" else wert
    d, = rechne([["rechnerUmrechnen", [feld, roh, KURS]]])
    assert d is None


def test_die_obergrenze_ist_genau_die_gesamtmenge(rechne):
    """21 Millionen muessen noch gehen -- darueber hoert Bitcoin auf, und
    JavaScripts Ganzzahlen fangen an zu runden."""
    geht, = rechne([["rechnerUmrechnen", ["btc", 21000000, KURS]]])
    assert geht["sat"] == 2_100_000_000_000_000


# ── Zahlen hinschreiben ────────────────────────────────────────────────────

def test_zahlen_werden_in_der_eingestellten_sprache_geschrieben(rechne):
    de, en = rechne([["zahlSchreiben", [1234567.891, 2, "de"]],
                     ["zahlSchreiben", [1234567.891, 2, "en"]]])
    assert de == "1.234.567,89"
    assert en == "1,234,567.89"


def test_bitcoin_wird_mit_acht_stellen_geschrieben(rechne):
    """Sonst sieht 0,00001504 wie 0,00002 aus -- und der Unterschied ist
    Geld."""
    a, b = rechne([["zahlSchreiben", [0.00001504, 8, "de"]],
                   ["zahlSchreiben", [1, 8, "de"]]])
    assert a == "0,00001504"
    assert b == "1,00000000"


def test_was_keine_zahl_ist_wird_gar_nicht_geschrieben(rechne):
    leer, = rechne([["zahlSchreiben", [None, 2, "de"]]])
    assert leer == ""
