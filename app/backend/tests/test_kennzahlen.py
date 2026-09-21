"""Die Zahlen, die auf der Weltansicht unter der Karte stehen.

Der Betreiber, 01.09.2026: "der naechste bitcoin block blocknummer inhalt ...
netzwerk gebueren aktuell difficultly ... das sind so sachen die fehlen
momentan auch noch".

Sie fehlten wirklich -- die Difficulty sogar, obwohl getblockchaininfo sie bei
jedem Abruf mitliefert und die Anwendung sie wegwarf.
"""
import pytest

from satcortex import kennzahlen, rpc


class Attrappe:
    """Ein Knoten, der genau die vorgegebenen Antworten gibt."""

    def __init__(self, antworten):
        self.antworten = antworten
        self.gefragt = []

    def ruf(self, methode, *params, zeitlimit=None):
        self.gefragt.append((methode, params))
        wert = self.antworten.get(methode)
        if isinstance(wert, Exception):
            raise wert
        if callable(wert):
            return wert(*params)
        if wert is None:
            raise rpc.RpcFehler(f"nicht vorgesehen: {methode}")
        return wert


# ── Der naechste Block ─────────────────────────────────────────────────────

VORLAGE = {
    "height": 964_122,
    "coinbasevalue": 315_600_000,
    "weightlimit": 4_000_000,
    "curtime": 1_756_700_000,
    "transactions": [
        # fee in Satoshi, weight in Gewichtseinheiten -- so steht es in
        # Cores rpc/mining.cpp.
        {"txid": "a" * 64, "fee": 4_400, "weight": 400},    # 44 sat/vB
        {"txid": "b" * 64, "fee": 1_800, "weight": 400},    # 18 sat/vB
        {"txid": "c" * 64, "fee": 600, "weight": 400},      #  6 sat/vB
    ],
}


def test_der_naechste_block_wird_aus_der_vorlage_gerechnet():
    k = Attrappe({"getblocktemplate": VORLAGE})
    d = kennzahlen.naechster_block(k)
    assert d["hoehe"] == 964_122
    assert d["transaktionen"] == 3
    assert d["gewicht"] == 1_200
    # Groesse in vByte ist Gewicht durch vier -- so rechnet SegWit.
    assert d["vbytes"] == 300
    assert d["gebuehren_sat"] == 6_800


def test_die_gebuehrenspanne_ist_die_des_billigsten_und_teuersten():
    """Die Spanne sagt, was gerade genuegt und was zu viel ist. Ein
    Mittelwert taete das nicht: er verschweigt beide Enden."""
    k = Attrappe({"getblocktemplate": VORLAGE})
    d = kennzahlen.naechster_block(k)
    assert d["sat_vb_min"] == pytest.approx(6.0)
    assert d["sat_vb_max"] == pytest.approx(44.0)


def test_waehrend_des_abgleichs_gibt_es_keine_vorlage():
    """Core lehnt getblocktemplate im Erstabgleich ausdruecklich ab
    ("is in initial sync and waiting for blocks"). Das ist kein Fehler,
    sondern eine Auskunft -- die Oberflaeche soll sie zeigen koennen."""
    k = Attrappe({"getblocktemplate": rpc.RpcFehler(
        "Bitcoin Core is in initial sync and waiting for blocks...")})
    assert kennzahlen.naechster_block(k) is None


def test_ein_leerer_block_ist_kein_absturz():
    k = Attrappe({"getblocktemplate": dict(VORLAGE, transactions=[])})
    d = kennzahlen.naechster_block(k)
    assert d["transaktionen"] == 0 and d["gebuehren_sat"] == 0
    assert d["sat_vb_min"] == 0 and d["sat_vb_max"] == 0


def test_segwit_muss_mitgefragt_werden():
    """Ohne die Regel antwortet Core mit einem Fehler statt mit einer
    Vorlage. Das ist keine Feinheit, sondern Bedingung."""
    k = Attrappe({"getblocktemplate": VORLAGE})
    kennzahlen.naechster_block(k)
    (methode, params), = k.gefragt
    assert methode == "getblocktemplate"
    assert params[0]["rules"] == ["segwit"]


# ── Gebuehrenschaetzung ────────────────────────────────────────────────────

def test_gebuehren_kommen_in_sat_pro_vbyte_an():
    """estimatesmartfee antwortet in BTC je kvB. Ungerechnet stuenden dort
    0.00044 statt 44 -- eine Zahl, die niemand liest."""
    k = Attrappe({"estimatesmartfee": lambda ziel, *r: {
        1: {"feerate": 0.00044, "blocks": 1},
        3: {"feerate": 0.00018, "blocks": 3},
        6: {"feerate": 0.00006, "blocks": 6},
    }[ziel]})
    d = kennzahlen.gebuehren(k)
    assert d == {"schnell": 44.0, "normal": 18.0, "guenstig": 6.0}


def test_eine_schaetzung_ohne_ergebnis_faellt_weg_statt_null_zu_behaupten():
    """Kurz nach dem Start hat Core noch keine Datengrundlage und antwortet
    mit "errors" statt mit feerate. Daraus 0 sat/vB zu machen waere eine
    Falschauskunft -- 0 hiesse "umsonst"."""
    k = Attrappe({"estimatesmartfee": lambda ziel, *r: (
        {"feerate": 0.00044, "blocks": 1} if ziel == 1
        else {"errors": ["Insufficient data or no feerate found"]})})
    assert kennzahlen.gebuehren(k) == {"schnell": 44.0}


def test_antwortet_der_knoten_gar_nicht_gibt_es_nichts():
    k = Attrappe({"estimatesmartfee": rpc.NichtErreichbar("aus")})
    assert kennzahlen.gebuehren(k) == {}


# ── Schwierigkeit ──────────────────────────────────────────────────────────

# Nicht von Hand ausgerechnet -- beim ersten Anlauf stand hier 234 statt 474,
# und der Test war falsch, nicht der Code.
HOEHE = 964_122
SEIT_ANFANG = HOEHE % kennzahlen.PERIODE          # 474
PERIODENANFANG = HOEHE - SEIT_ANFANG
ERWARTET_S = SEIT_ANFANG * kennzahlen.ZIELABSTAND_SEKUNDEN


def test_bloecke_bis_zur_anpassung():
    k = Attrappe({})
    d = kennzahlen.schwierigkeit(k, {"hoehe": HOEHE, "difficulty": 1.421e14})
    assert d["wert"] == 1.421e14
    assert d["bloecke_bis_anpassung"] == kennzahlen.PERIODE - SEIT_ANFANG


def test_schneller_als_zehn_minuten_heisst_hoehere_schwierigkeit():
    """Das Netz hat die bisherigen Bloecke in fuenf Sechsteln der gewollten
    Zeit geschafft -- es war zwanzig Prozent schneller, also steigt die
    Schwierigkeit um zwanzig Prozent."""
    jetzt = 1_756_700_000
    k = Attrappe({
        "getblockhash": lambda h: "start" if h == PERIODENANFANG else "?",
        "getblockheader": lambda h, *r: {"time": jetzt - ERWARTET_S / 1.2},
    })
    d = kennzahlen.schwierigkeit(k, {"hoehe": HOEHE, "difficulty": 1.0},
                                 jetzt=jetzt)
    assert d["aenderung_prozent"] == pytest.approx(20.0, abs=0.5)


def test_langsamer_heisst_niedrigere_schwierigkeit():
    jetzt = 1_756_700_000
    k = Attrappe({
        "getblockhash": lambda h: "start",
        "getblockheader": lambda h, *r: {"time": jetzt - ERWARTET_S * 1.25},
    })
    d = kennzahlen.schwierigkeit(k, {"hoehe": HOEHE, "difficulty": 1.0},
                                 jetzt=jetzt)
    assert d["aenderung_prozent"] < 0


def test_ohne_periodenanfang_bleibt_die_schaetzung_weg():
    """Lieber keine Zahl als eine erfundene: waehrend des Abgleichs liegt der
    Anfang der Periode womoeglich noch gar nicht vor."""
    k = Attrappe({"getblockhash": rpc.RpcFehler("Block height out of range")})
    d = kennzahlen.schwierigkeit(k, {"hoehe": HOEHE, "difficulty": 1.0})
    assert "aenderung_prozent" not in d
    assert d["bloecke_bis_anpassung"] == kennzahlen.PERIODE - SEIT_ANFANG


def test_die_anpassung_wird_gekappt():
    """Das Protokoll laesst hoechstens Vervierfachung und Viertelung zu.
    Eine Schaetzung von +900 % waere schlicht falsch."""
    jetzt = 1_756_700_000
    k = Attrappe({
        "getblockhash": lambda h: "start",
        "getblockheader": lambda h, *r: {"time": jetzt - 100},
    })
    d = kennzahlen.schwierigkeit(k, {"hoehe": HOEHE, "difficulty": 1.0},
                                 jetzt=jetzt)
    assert d["aenderung_prozent"] == 300.0


# ── Was ein Kanal an Gebuehren kostet (04.09.2026) ──────────────────────────
#
# Der Betreiber: "die gebuehren lage beim oeffnen und schliessen, das sollte unsere
# app dann direkt da wo es passiert sauber anzeigen, damit es nicht zu boesen
# ueberraschungen kommt."
#
# Besonders wichtig, bei einem kleinen Einstieg -- mit rund hundert Euro. Zwei
# Sats je vByte sind dann Kleingeld, zweihundert ein Drittel des Kanals.

def test_ohne_schaetzung_gibt_es_keine_zahl():
    """Eine Null hiesse "umsonst". Das waere hier die teuerste
    Falschauskunft von allen -- lieber gar nichts anzeigen."""
    assert kennzahlen.kanalkosten({}, 146_304) is None
    assert kennzahlen.kanalkosten({"normal": 0}, 146_304) is None


def test_oeffnen_und_schliessen_werden_beide_gezaehlt():
    """Ein Kanal kostet ZWEIMAL Gebuehren -- das ist der Teil, den man
    beim Oeffnen gern vergisst."""
    d = kennzahlen.kanalkosten({"normal": 10})
    assert d["oeffnen_sat"] > 0 and d["schliessen_sat"] > 0
    assert d["zusammen_sat"] == d["oeffnen_sat"] + d["schliessen_sat"]


def test_der_anteil_macht_aus_der_zahl_eine_aussage():
    """1.540 Sats sagen einem Menschen nichts. "Ein Prozent deines
    Guthabens" sagt alles -- und "zweiundvierzig Prozent" erst recht."""
    klein = kennzahlen.kanalkosten({"normal": 200}, 146_304)
    assert klein["anteil_prozent"] > 40, klein
    gross = kennzahlen.kanalkosten({"normal": 200}, 10_000_000)
    assert gross["anteil_prozent"] < 1, gross


def test_ohne_guthaben_wird_kein_anteil_erfunden():
    """Vor der Einrichtung gibt es noch kein On-Chain-Guthaben. Dann steht
    die Satoshi-Zahl da und sonst nichts."""
    d = kennzahlen.kanalkosten({"normal": 5}, 0)
    assert "anteil_prozent" not in d


# ── Ist die Gebuehr gerade teuer oder guenstig? ────────────────────────────
#
# Aus dem Betrieb, 11.09.2026: "waere das nicht gut wenn er uns sagen wuerde ob das
# momentan teuer oder guenstig ist im durchschnitt .. ?? das mann ne
# orientierung hat".
#
# Der Massstab kommt aus der EIGENEN Kette -- getblockstats sagt je Block, bei
# welchen Saetzen wirklich bestaetigt wurde. Keine fremde Seite.

HOEHE = 964_122


def _knoten_mit(saetzen):
    """Ein Knoten, der der Reihe nach diese Mediane liefert.

    None an einer Stelle heisst: dieser Block gibt nichts her.
    """
    folge = list(saetzen)
    zaehler = {"i": 0}

    def stats(hoehe, felder, *rest):
        i = zaehler["i"]
        zaehler["i"] += 1
        satz = folge[i % len(folge)]
        if satz is None:
            raise rpc.RpcFehler("Block nicht lesbar")
        # Fuenf Stellen: 10., 25., 50., 75., 90. Die Mitte ist Index 2.
        return {"feerate_percentiles": [1, 2, satz, 30, 90]}

    return Attrappe({"getblockstats": stats})


def test_der_massstab_kommt_aus_der_eigenen_kette():
    """Die Verteilung einer Woche, aus den eigenen Bloecken gerechnet."""
    knoten = _knoten_mit([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    d = kennzahlen.gebuehrenverlauf(knoten, HOEHE)
    assert d is not None
    assert d["bloecke"] > 100
    # Nur getblockstats, und nur mit dem einen Feld -- nicht der ganze Block.
    assert {m for m, _ in knoten.gefragt} == {"getblockstats"}
    assert knoten.gefragt[0][1][1] == ["feerate_percentiles"]
    assert d["unten"] <= d["unteres_viertel"] <= d["mitte"]
    assert d["mitte"] <= d["oberes_viertel"] <= d["oben"]


def test_ohne_genug_kette_gibt_es_keinen_massstab():
    """Waehrend des Abgleichs der Normalfall. Eine Verteilung aus fuenf
    Bloecken waere keine -- dann lieber gar keine Aussage."""
    assert kennzahlen.gebuehrenverlauf(_knoten_mit([5]), 500) is None


def test_einzelne_luecken_kippen_den_massstab_nicht():
    """Aus 130 statt 145 Stichproben wird dieselbe Aussage. Wegen eines
    unlesbaren Blocks die ganze Einordnung fallenzulassen waere falsch."""
    # Jeder fuenfte Block antwortet nicht.
    d = kennzahlen.gebuehrenverlauf(_knoten_mit([4, 5, 6, 7, None]), HOEHE)
    assert d is not None
    assert d["bloecke"] > kennzahlen.VERLAUF_MINDESTENS


def test_zu_viele_luecken_und_es_gibt_keine_aussage():
    """Unter der Mindestzahl ist es keine Verteilung mehr, sondern Zufall."""
    folge = [5] + [None] * 40
    assert kennzahlen.gebuehrenverlauf(_knoten_mit(folge), HOEHE) is None


def test_guenstig_normal_teuer():
    """Die Grenzen liegen in der Verteilung, nicht bei festen Satzzahlen --
    eine feste Zahl waere im naechsten Jahr falsch."""
    verlauf = {"unteres_viertel": 3.0, "mitte": 6.0, "oberes_viertel": 12.0}
    assert kennzahlen.einordnung(2.2, verlauf) == "guenstig"
    assert kennzahlen.einordnung(3.0, verlauf) == "guenstig"
    assert kennzahlen.einordnung(6.0, verlauf) == "normal"
    assert kennzahlen.einordnung(12.0, verlauf) == "teuer"
    assert kennzahlen.einordnung(80.0, verlauf) == "teuer"


def test_ohne_massstab_wird_nichts_eingeordnet():
    """Lieber keine Einordnung als eine erfundene."""
    assert kennzahlen.einordnung(2.2, None) is None
    assert kennzahlen.einordnung(0, {"unteres_viertel": 1, "mitte": 2,
                                     "oberes_viertel": 3}) is None


def test_die_einordnung_steht_auch_ohne_guthaben():
    """DER PUNKT, der bisher fehlte.

    Die alte Einordnung mass die Gebuehr am eigenen Guthaben -- und fiel
    damit genau dann weg, wenn man noch keins hat. Also beim Planen des
    ersten Kanals, wo man sie am dringendsten braucht.
    """
    verlauf = {"unteres_viertel": 3.0, "mitte": 6.0, "oberes_viertel": 12.0,
               "unten": 1.0, "oben": 40.0, "tage": 7.0, "bloecke": 144}
    d = kennzahlen.kanalkosten({"normal": 2.2}, 0, verlauf=verlauf)
    assert "anteil_prozent" not in d       # kein Guthaben, kein Anteil
    assert d["lage"] == "guenstig"         # trotzdem eine Auskunft
    assert d["verlauf"]["mitte"] == 6.0


# ── Was fuer einen Kanal einzuzahlen ist ───────────────────────────────────

def test_die_ruecklage_wird_nicht_erfunden():
    """Ohne laufenden LND gibt es die Zahl nicht. Eine Null hiesse "du
    brauchst nichts zurueckzulegen" -- und daran scheitert man spaeter."""
    d = kennzahlen.kanalkosten({"normal": 5})
    assert "ruecklage_sat" not in d


def test_die_ruecklage_kommt_von_lnd_durch():
    """Nicht geschaetzt: LND kennt die Zahl und nennt sie."""
    d = kennzahlen.kanalkosten({"normal": 5}, 0, ruecklage_sat=10_000)
    assert d["ruecklage_sat"] == 10_000
    # Die Kanal-Reserve ist etwas anderes und steht immer dabei.
    assert d["reserve_prozent"] == kennzahlen.KANAL_RESERVE_PROZENT


# ── Die Uhr der Kette: Halbierung ──────────────────────────────────────────
#
# Der Betreiber, 21.09.2026: "sone arte block zeit in der uebersicht .. anzahl
# der bloecke bis zum naechsten halving .. geschaetztes datum .. und wie hoch
# die revard ist beim naechsten halving".

def test_die_belohnung_folgt_cores_eigener_rechnung():
    """Ganzzahlig geschoben, nicht in Gleitkomma geteilt.

    3,125 BTC sind in Gleitkomma nicht darstellbar; 312.500.000 Satoshi
    schon. Cores GetBlockSubsidy schiebt deshalb ganzzahlig, und hier wird
    genauso gerechnet.
    """
    assert kennzahlen.belohnung_sat(0) == 5_000_000_000            # 50 BTC
    assert kennzahlen.belohnung_sat(209_999) == 5_000_000_000
    assert kennzahlen.belohnung_sat(210_000) == 2_500_000_000      # 25 BTC
    assert kennzahlen.belohnung_sat(630_000) == 625_000_000        # 6,25
    assert kennzahlen.belohnung_sat(840_000) == 312_500_000        # 3,125
    assert kennzahlen.belohnung_sat(1_050_000) == 156_250_000      # 1,5625


def test_die_letzte_halbierung_endet_bei_null():
    """Das Ende der Ausschuettung, rund im Jahr 2140.

    Nach 33 Halbierungen ist von 5.000.000.000 nichts mehr uebrig -- genau
    wie in Cores validation.cpp, wo derselbe Schiebevorgang steht.
    """
    letzte = 32 * kennzahlen.HALBIERUNG_PERIODE
    assert kennzahlen.belohnung_sat(letzte) == 1                   # ein Satoshi
    assert kennzahlen.belohnung_sat(33 * kennzahlen.HALBIERUNG_PERIODE) == 0


def test_bis_zur_naechsten_halbierung_wird_gezaehlt_nicht_geschaetzt():
    d = kennzahlen.halbierung(967_296, 600.0, jetzt=1_758_400_000.0)
    assert d["naechste_hoehe"] == 1_050_000
    assert d["bloecke_bis"] == 82_704
    assert d["belohnung_sat"] == 312_500_000
    assert d["belohnung_danach_sat"] == 156_250_000


def test_das_datum_rechnet_mit_dem_gemessenen_takt():
    """Nicht mit dem Lehrbuchwert, wenn die eigene Kette einen echten hat."""
    jetzt = 1_758_400_000.0
    d = kennzahlen.halbierung(967_296, 570.0, jetzt=jetzt)
    assert d["schnitt_sekunden"] == 570.0
    assert d["gemessen"] is True
    # Die Fensterbreite kommt mit, damit die Oberflaeche sie nicht ein
    # zweites Mal kennen muss und irgendwann eine falsche Zahl nennt.
    assert d["rueckblick"] == kennzahlen.TAKT_RUECKBLICK
    assert d["geschaetzt_ts"] == pytest.approx(jetzt + 82_704 * 570.0)


def test_ohne_messung_gilt_der_zielabstand_und_sagt_es_auch():
    """Waehrend des Abgleichs gibt es keinen brauchbaren eigenen Takt.

    Dann sind zehn Minuten die ehrlichste Annahme -- aber die Antwort muss
    dazusagen, dass gerechnet und nicht gemessen wurde.
    """
    d = kennzahlen.halbierung(967_296, None, jetzt=1_758_400_000.0)
    assert d["gemessen"] is False
    assert d["schnitt_sekunden"] == kennzahlen.ZIELABSTAND_SEKUNDEN


def test_das_geschaetzte_datum_ist_plausibel():
    """Die Gegenprobe gegen die Wirklichkeit.

    Fuenfte Halbierung: Block 840.000 am 20.04.2024. Von dort mit dem
    tatsaechlichen Takt weitergerechnet muss die sechste im Fruehjahr 2028
    landen -- nicht 2026 und nicht 2035. Faellt die Zahl aus diesem Fenster,
    stimmt die Rechnung nicht, egal wie gruen die anderen Tests sind.
    """
    import datetime as dt
    # Stand 21.09.2026, mit 9,7 min je Block seit der letzten Halbierung.
    jetzt = dt.datetime(2026, 9, 21, tzinfo=dt.timezone.utc).timestamp()
    d = kennzahlen.halbierung(967_296, 582.0, jetzt=jetzt)
    ziel = dt.datetime.fromtimestamp(d["geschaetzt_ts"], dt.timezone.utc)
    assert ziel.year == 2028
    assert 1 <= ziel.month <= 6


def test_nach_der_letzten_halbierung_gibt_es_keine_naechste():
    """Kein erfundenes Datum im Jahr 2140 und keine Division durch nichts."""
    d = kennzahlen.halbierung(33 * kennzahlen.HALBIERUNG_PERIODE, 600.0,
                              jetzt=1_758_400_000.0)
    assert d["naechste_hoehe"] is None
    assert d["bloecke_bis"] is None
    assert d["geschaetzt_ts"] is None
    assert d["belohnung_sat"] == 0


# ── Der gemessene Takt ─────────────────────────────────────────────────────

def test_der_takt_kommt_aus_der_eigenen_kette():
    """Zwei Kopfzeilen, sonst nichts -- und daraus der wirkliche Abstand."""
    rueck = kennzahlen.TAKT_RUECKBLICK
    zeiten = {967_296: 1_758_400_000, 967_296 - rueck: 1_758_400_000 - 15_000_000}
    k = Attrappe({
        "getblockhash": lambda h: f"hash-{h}",
        "getblockheader": lambda h: {"time": zeiten[int(h.split("-")[1])]},
    })
    schnitt = kennzahlen.takt(k, 967_296)
    assert schnitt == pytest.approx(15_000_000 / rueck)


def test_ohne_genug_kette_wird_kein_takt_behauptet():
    k = Attrappe({})
    assert kennzahlen.takt(k, 100) is None
    assert not k.gefragt                   # gar nicht erst gefragt


def test_ein_unbrauchbarer_zeitstempel_ergibt_keinen_takt():
    """Blockzeiten duerfen laut Protokoll rueckwaerts springen.

    Ueber 26.280 Bloecke faellt das nicht ins Gewicht -- eine Reihenfolge,
    die insgesamt rueckwaerts laeuft, ist aber keine Messung, sondern ein
    Fehler. Dann lieber nichts.
    """
    k = Attrappe({
        "getblockhash": lambda h: f"hash-{h}",
        "getblockheader": lambda h: {"time": 1_000_000},
    })
    assert kennzahlen.takt(k, 967_296) is None


def test_ein_stiller_knoten_reisst_den_takt_nicht_mit():
    k = Attrappe({"getblockhash": rpc.NichtErreichbar("weg")})
    assert kennzahlen.takt(k, 967_296) is None
