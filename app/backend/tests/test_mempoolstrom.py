"""Den Mempool lesen, ohne ihn zu halten.

Der Befund vom 21.09.2026: bei vollem Mempool starb der app-Container, weil
``getrawmempool True`` als Ganzes eingelesen wurde. Die Tests hier halten
beides fest: dass der Strom richtig liest, und dass er den Speicher nicht
mit der Eingabe wachsen laesst.
"""
import gc
import json
import tracemalloc

import pytest

from satcortex import mempoolstrom


def brocken(text: str, groesse: int):
    """Einen Text in Stuecken liefern -- wie eine echte Leitung."""
    roh = text.encode("utf-8")
    for i in range(0, len(roh), groesse):
        yield roh[i:i + groesse]


def vorbereitet(text: str, groesse: int = 64 * 1024):
    """Dieselben Stuecke, aber FERTIG, bevor gemessen wird.

    Sonst misst man das Testgeruest mit: text.encode() legt die ganze
    Antwort noch einmal an, und zwar innerhalb der Messung. Genau darauf
    bin ich am 21.09.2026 hereingefallen -- die Kurve sah nach einem Leck
    im Parser aus und war eine im Test.
    """
    roh = text.encode("utf-8")
    return [roh[i:i + groesse] for i in range(0, len(roh), groesse)]


def antwort(eintraege: dict) -> str:
    return json.dumps({"result": eintraege, "error": None, "id": "satcortex"})


def eintrag(vsize=141, base=0.00000282, ancestor=None, ancestorsize=None):
    """Ein Eintrag mit Cores echter Feldliste (rpc/mempool.cpp)."""
    return {
        "vsize": vsize, "weight": vsize * 4, "time": 1789000000,
        "height": 964012, "descendantcount": 1, "descendantsize": vsize,
        "ancestorcount": 1, "ancestorsize": ancestorsize or vsize,
        "wtxid": "aa" * 32,
        "fees": {"base": base, "modified": base,
                 "ancestor": ancestor if ancestor is not None else base,
                 "descendant": base},
        "depends": [], "spentby": [], "bip125-replaceable": True,
        "unbroadcast": False,
    }


# ── Lesen ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("haeppchen", [1, 2, 7, 64, 1024, 1_000_000])
def test_paare_kommen_vollstaendig_an_egal_wie_zerhackt(haeppchen):
    """Die Stueckelung der Leitung darf am Ergebnis nichts aendern.

    Ein Parser, der bei 1024 Byte stimmt und bei 7 nicht, ist einer, der
    zufaellig funktioniert.
    """
    daten = {f"{i:064x}": eintrag(vsize=100 + i) for i in range(25)}
    gelesen = dict(mempoolstrom.paare(brocken(antwort(daten), haeppchen)))
    assert gelesen == daten


def test_ein_leerer_mempool_ist_kein_fehler():
    assert list(mempoolstrom.paare(brocken(antwort({}), 8))) == []


def test_result_null_endet_still():
    """bitcoind schickt bei manchen Fehlern "result": null."""
    text = json.dumps({"result": None, "error": None, "id": "x"})
    assert list(mempoolstrom.paare(brocken(text, 4))) == []


def test_felder_vor_und_nach_result_stoeren_nicht():
    text = ('{"id":"satcortex","error":null,"result":'
            + json.dumps({"ab" * 32: eintrag()})
            + ',"nachher":{"egal":[1,2,3]}}')
    gelesen = dict(mempoolstrom.paare(brocken(text, 3)))
    assert list(gelesen) == ["ab" * 32]


def test_geschweifte_klammern_in_einem_text_zaehlen_nicht_mit():
    """Ein "}" in einer Zeichenkette darf das Objekt nicht beenden."""
    e = eintrag()
    e["kommentar"] = 'ein } und ein { mitten im Text'
    gelesen = dict(mempoolstrom.paare(brocken(antwort({"cd" * 32: e}), 5)))
    assert gelesen["cd" * 32]["kommentar"] == 'ein } und ein { mitten im Text'


def test_entwertete_anfuehrungszeichen():
    e = eintrag()
    e["kommentar"] = 'er sagte \\" und dann }'
    gelesen = dict(mempoolstrom.paare(brocken(antwort({"ef" * 32: e}), 2)))
    assert gelesen["ef" * 32]["kommentar"] == 'er sagte \\" und dann }'


def test_ein_schluessel_der_wie_das_feld_heisst_taeuscht_nicht():
    """Eine txid "result" gibt es nicht -- aber verlassen wird sich nicht
    darauf, sondern auf die Tiefe."""
    e = eintrag()
    e["result"] = {"vsize": 999}
    gelesen = dict(mempoolstrom.paare(brocken(antwort({"11" * 32: e}), 6)))
    assert len(gelesen) == 1
    assert gelesen["11" * 32]["result"] == {"vsize": 999}


def test_umlaute_ueberleben_die_stueckelung():
    """Ein Mehrbyte-Zeichen, das genau auf einer Brockengrenze zerfaellt."""
    e = eintrag()
    e["kommentar"] = "Gebuehren fuer Grosse: ÄÖÜ äöü ß € 😀"
    text = antwort({"22" * 32: e})
    for h in (1, 2, 3, 5):
        gelesen = dict(mempoolstrom.paare(brocken(text, h)))
        assert gelesen["22" * 32]["kommentar"] == e["kommentar"], h


# ── Abbruchgruende ─────────────────────────────────────────────────────────

def test_ein_abriss_endet_laut():
    """Eine halb gelesene Antwort sieht aus wie ein halb leerer Mempool.

    Daraus eine Gebuehrenschaetzung zu bauen waere schlimmer als keine --
    also muss der Abriss eine Ausnahme sein und keine kurze Liste.
    """
    text = antwort({f"{i:064x}": eintrag() for i in range(10)})
    halb = text[:len(text) // 2]
    with pytest.raises(mempoolstrom.MempoolAbgerissen):
        list(mempoolstrom.paare(brocken(halb, 64)))


def test_die_notbremse_greift():
    def endlos():
        while True:
            yield b"x" * 4096
    with pytest.raises(mempoolstrom.MempoolZuGross):
        list(mempoolstrom.begrenzt(endlos(), hoechstens=100_000))


def test_die_notbremse_laesst_normales_durch():
    text = antwort({f"{i:064x}": eintrag() for i in range(5)})
    stuecke = list(mempoolstrom.begrenzt(brocken(text, 128)))
    assert b"".join(stuecke).decode("utf-8") == text


# ── Auswerten ──────────────────────────────────────────────────────────────

def test_auswerten_sortiert_nach_dem_paketsatz():
    """Sortiert wird nach dem Satz MIT Vorfahren -- danach waehlt der Miner."""
    daten = {
        "aa" * 32: eintrag(vsize=100, base=0.00001000),     # 1000 sat/100 = 10
        "bb" * 32: eintrag(vsize=100, base=0.00005000),     # 50
        "cc" * 32: eintrag(vsize=100, base=0.00002000),     # 20
    }
    raus = mempoolstrom.auswerten(brocken(antwort(daten), 512))
    assert [x[1] for x in raus] == ["bb" * 32, "cc" * 32, "aa" * 32]
    assert raus[0][0] == pytest.approx(50.0)
    assert raus[0][3] == pytest.approx(50.0)


def test_der_paketsatz_rechnet_die_vorfahren_mit():
    """Eine teure Transaktion mit billigem Vorfahren rutscht nach hinten."""
    daten = {
        "aa" * 32: eintrag(vsize=100, base=0.00010000,
                           ancestor=0.00010500, ancestorsize=10000),
        "bb" * 32: eintrag(vsize=100, base=0.00002000),
    }
    raus = mempoolstrom.auswerten(brocken(antwort(daten), 256))
    # aa zahlt selbst 100 sat/vB, im Paket aber nur 10500/10000 = 1,05
    assert [x[1] for x in raus] == ["bb" * 32, "aa" * 32]
    assert raus[1][0] == pytest.approx(1.05)
    assert raus[1][3] == pytest.approx(100.0)


@pytest.mark.parametrize("kaputt", [
    {"vsize": 0}, {"vsize": -5}, {"vsize": "viel"}, {"vsize": None},
])
def test_unbrauchbare_eintraege_fallen_weg_statt_zu_sprengen(kaputt):
    e = eintrag(); e.update(kaputt)
    daten = {"aa" * 32: e, "bb" * 32: eintrag()}
    raus = mempoolstrom.auswerten(brocken(antwort(daten), 128))
    assert [x[1] for x in raus] == ["bb" * 32]


def test_ein_eintrag_ohne_fees_faellt_nicht_um():
    e = eintrag(); del e["fees"]
    raus = mempoolstrom.auswerten(brocken(antwort({"aa" * 32: e}), 64))
    assert raus == [(0.0, "aa" * 32, 141, 0.0)]


# ── Der eigentliche Punkt ──────────────────────────────────────────────────

def test_das_LESEN_waechst_nicht_mit_der_antwort():
    """Das ist der Befund vom 21.09.2026, als Gegenprobe.

    Vorher wuchs die Spitze linear mit der Antwort: 150.000 Transaktionen
    kosteten 397 MB bei einem Containerlimit von 400M. Gemessen wird deshalb
    genau das LESEN -- der Verbraucher haelt nichts fest, damit die Ausgabe
    die Messung nicht faelscht. Dass eine groessere Ausgabe mehr Platz
    braucht, ist richtig so und nicht der Befund.

    Geprueft wird das Verhaeltnis, nicht ein absoluter Wert: eine feste
    Schranke in Megabyte waere eine Zahl, die auf einem anderen Rechner aus
    einem anderen Grund stimmt oder nicht.
    """
    messungen = {}
    for n in (500, 8000):
        stuecke = vorbereitet(antwort(
            {f"{i:064x}": eintrag(vsize=100 + (i % 400)) for i in range(n)}))
        gc.collect()
        gezaehlt = 0
        tracemalloc.start()
        for _txid, _e in mempoolstrom.paare(iter(stuecke)):
            gezaehlt += 1          # nichts behalten, nur durchlaufen
        _, spitze = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert gezaehlt == n
        messungen[n] = spitze
        del stuecke
        gc.collect()

    # Sechzehnmal so viele Transaktionen. Waechst die Spitze mit, ist der
    # Strom keiner. Gemessen am 21.09.2026: 0,20 MB bei beiden Groessen,
    # und auch noch bei 32.000.
    assert messungen[8000] < messungen[500] * 1.5, messungen


def test_gegen_die_alte_bauweise_gehalten():
    """Zum Vergleich: dasselbe Dokument einmal ganz eingelesen.

    Kein Werturteil im Test, nur die Messung -- sie muss deutlich schlechter
    sein, sonst hat der Umbau nichts gebracht. Verglichen wird wieder das
    Lesen: beim Strom ein Durchlauf ohne Ablage, bei der alten Bauweise das,
    was json.loads unvermeidlich anlegt.
    """
    n = 8000
    text = antwort({f"{i:064x}": eintrag() for i in range(n)})
    stuecke = vorbereitet(text)
    roh = text.encode("utf-8")
    gc.collect()

    gezaehlt = 0
    tracemalloc.start()
    for _txid, _e in mempoolstrom.paare(iter(stuecke)):
        gezaehlt += 1
    _, spitze_strom = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()

    tracemalloc.start()
    ganz = json.loads(roh.decode("utf-8"))
    _, spitze_ganz = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert gezaehlt == n and len(ganz["result"]) == n
    assert spitze_strom < spitze_ganz / 20, (spitze_strom, spitze_ganz)


def test_und_die_ausgabe_bleibt_klein_gegen_die_eingabe():
    """Was auswerten() zurueckgibt, sind vier Zahlen je Transaktion --
    nicht fuenfzehn Felder. Auch das gehoert zum Befund: selbst WENN man
    alles behalten muss, ist es ein Bruchteil."""
    n = 8000
    text = antwort({f"{i:064x}": eintrag() for i in range(n)})
    stuecke = vorbereitet(text)
    roh = text.encode("utf-8")
    gc.collect()

    tracemalloc.start()
    raus = mempoolstrom.auswerten(iter(stuecke))
    _, spitze_strom = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()

    tracemalloc.start()
    ganz = json.loads(roh.decode("utf-8"))
    _, spitze_ganz = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(raus) == n and len(ganz["result"]) == n
    assert spitze_strom < spitze_ganz / 2, (spitze_strom, spitze_ganz)
