"""Die Datenhaltung der Auswertung.

Der Kern ist eine Zahl, die sich nicht nachtraeglich erfinden laesst: wann
DIESER Knoten eine Transaktion zum ersten Mal gesehen hat. Die Tests kreisen
darum, dass sie entsteht, stehen bleibt und richtig verrechnet wird.
"""
import threading
import time
from pathlib import Path

import pytest

from satcortex import store


@pytest.fixture
def ablage(tmp_path):
    a = store.Ablage(str(tmp_path / "unter" / "auswertung.db"))
    yield a
    a.schliesse()


def test_datei_und_schema_entstehen_von_selbst(tmp_path):
    """Auch das Verzeichnis darunter -- beim ersten Start gibt es das noch
    nicht."""
    a = store.Ablage(str(tmp_path / "gibtsnochnicht" / "x.db"))
    assert (tmp_path / "gibtsnochnicht" / "x.db").exists()
    assert a.eckdaten() == {"transaktionen": 0, "sammelt_seit_ms": None,
                            "bloecke": 0, "luecken_24h": 0, "reorgs_24h": 0}
    a.schliesse()


def test_der_erste_zeitpunkt_gewinnt(ablage):
    """DAS ist die Zahl, die kein Explorer hat. Sie ein zweites Mal zu
    schreiben -- nach einer Reorg etwa -- wuerde sie wegwerfen."""
    ablage.tx_aufgenommen("aa" * 32, 1000, 5)
    ablage.tx_aufgenommen("aa" * 32, 9999, 6)
    assert ablage.eine_tx("aa" * 32)["zuerst_ms"] == 1000


def test_verweildauer_und_median(ablage):
    """Nicht 'wann wurde bestaetigt', sondern 'wie lange lag sie bei MIR'."""
    for i, txid in enumerate(["a" * 64, "b" * 64, "c" * 64]):
        ablage.tx_aufgenommen(txid, 1000 * (i + 1), i)
    # Block kommt bei 10_000: Dauern 9000, 8000, 7000
    ergebnis = ablage.tx_bestaetigt(["a" * 64, "b" * 64, "c" * 64], 900000, 10000)
    assert ergebnis["bekannt"] == 3
    assert ergebnis["median_ms"] == 8000
    assert ablage.eine_tx("a" * 64)["verweildauer_ms"] == 9000
    assert ablage.eine_tx("a" * 64)["hoehe"] == 900000


def test_unbekannte_transaktionen_zaehlen_nicht_mit(ablage):
    """Waehrend eines Blocks tauchen Transaktionen auf, die wir nie im Mempool
    hatten -- direkt an den Miner gegeben etwa. Sie duerfen die Verweildauer
    nicht mit einer erfundenen Null verwaessern."""
    ablage.tx_aufgenommen("a" * 64, 1000, 1)
    ergebnis = ablage.tx_bestaetigt(["a" * 64, "unbekannt" + "0" * 55], 1, 5000)
    assert ergebnis["bekannt"] == 1
    assert ergebnis["median_ms"] == 4000
    assert ablage.eine_tx("unbekannt" + "0" * 55) is None


def test_ein_block_zaehlt_nur_einmal(ablage):
    """Kommt derselbe Block zweimal -- Reorg, Neustart --, darf die
    Verweildauer nicht neu berechnet werden."""
    ablage.tx_aufgenommen("a" * 64, 1000, 1)
    ablage.tx_bestaetigt(["a" * 64], 100, 5000)
    zweimal = ablage.tx_bestaetigt(["a" * 64], 100, 9000)
    assert zweimal["bekannt"] == 0
    assert ablage.eine_tx("a" * 64)["verweildauer_ms"] == 4000


def test_leerer_block_bricht_nicht(ablage):
    assert ablage.tx_bestaetigt([], 1, 1000) == {"bekannt": 0, "median_ms": None}


def test_entfernen_ohne_block(ablage):
    ablage.tx_aufgenommen("a" * 64, 1000, 1)
    ablage.tx_entfernt("a" * 64, 4000, "weg")
    z = ablage.eine_tx("a" * 64)
    assert z["entfernt_ms"] == 4000 and z["grund"] == "weg"
    # Ein zweites Entfernen ueberschreibt den ersten Zeitpunkt nicht.
    ablage.tx_entfernt("a" * 64, 8000, "nochmal")
    assert ablage.eine_tx("a" * 64)["entfernt_ms"] == 4000


def test_bloecke_lesen_sich_neueste_zuerst(ablage):
    for hoehe in (100, 102, 101):
        ablage.block_eingetragen({
            "hoehe": hoehe, "hash": f"{hoehe:064d}", "blockzeit": hoehe,
            "empfangen_ms": hoehe * 1000, "gewicht": 4000000, "txzahl": 2000,
            "gebuehren_sat": 12345, "pool": "Foundry USA", "botschaft": None,
            "bekannte_tx": 1900, "verweildauer_ms": 60000})
    assert [b["hoehe"] for b in ablage.letzte_bloecke()] == [102, 101, 100]
    assert ablage.letzte_bloecke(1)[0]["pool"] == "Foundry USA"


def test_luecken_werden_festgehalten(ablage):
    """Ohne diese Tabelle waeren alle Zahlen daneben stille Behauptungen."""
    ablage.luecke("zmq", 41, 43)
    assert ablage.eckdaten()["luecken_24h"] == 1


def test_mempool_verlauf_und_diagramm(ablage):
    jetzt = int(time.time())
    ablage.mempool_punkt(jetzt - 100, 4000, 2_000_000, 1.5, None)
    ablage.mempool_punkt(jetzt, 4200, 2_100_000, 1.8, [{"weight": 1, "fee": 2}])
    verlauf = ablage.mempool_verlauf(jetzt - 200)
    assert [p["txzahl"] for p in verlauf] == [4000, 4200]
    assert ablage.letztes_diagramm() == [{"weight": 1, "fee": 2}]
    # Ohne die Zeit sieht ein altes Diagramm aus wie eins von jetzt.
    assert ablage.diagramm_zeit() == jetzt


def test_aufraeumen_wirft_nur_altes_weg(ablage):
    jetzt_ms = int(time.time() * 1000)
    ablage.tx_aufgenommen("alt" + "0" * 61, jetzt_ms - 40 * 86400 * 1000, 1)
    ablage.tx_aufgenommen("neu" + "0" * 61, jetzt_ms, 2)
    ablage.block_eingetragen({
        "hoehe": 1, "hash": "x", "blockzeit": 0, "empfangen_ms": 0,
        "gewicht": 0, "txzahl": 0, "gebuehren_sat": 0, "pool": None,
        "botschaft": None, "bekannte_tx": 0, "verweildauer_ms": None})

    assert ablage.aufraeumen(tage=30) == 1
    assert ablage.eine_tx("alt" + "0" * 61) is None
    assert ablage.eine_tx("neu" + "0" * 61) is not None
    # Bloecke bleiben: sie sind klein und werden mit den Jahren interessant.
    assert ablage.eckdaten()["bloecke"] == 1


def test_mehrere_threads_teilen_sich_die_datei(ablage):
    """Der Zulauf schreibt, die Oberflaeche liest -- gleichzeitig. Ohne eine
    Verbindung je Thread wirft SQLite hier."""
    fehler = []

    def schreibe(von, bis):
        try:
            for i in range(von, bis):
                ablage.tx_aufgenommen(f"{i:064d}", 1000 + i, i)
            ablage.sichern()
        except Exception as f:                                   # nosec B902
            fehler.append(f)

    faeden = [threading.Thread(target=schreibe, args=(i * 50, i * 50 + 50))
              for i in range(4)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert not fehler
    assert ablage.eckdaten()["transaktionen"] == 200


def test_ein_sehr_voller_block(ablage):
    """Ein Block mit mehreren tausend Transaktionen. Der erste Anlauf baute
    daraus eine Abfrage mit ebenso vielen Platzhaltern -- das laeuft gegen
    SQLites Obergrenze, und zwar erst bei einem besonders vollen Block, also
    genau nicht beim Testen."""
    txids = [f"{i:064x}" for i in range(5000)]
    for i, txid in enumerate(txids[:3000]):
        ablage.tx_aufgenommen(txid, 1000 + i, i)

    ergebnis = ablage.tx_bestaetigt(txids, 900000, 100000)
    assert ergebnis["bekannt"] == 3000
    assert ablage.eine_tx(txids[0])["hoehe"] == 900000
    assert ablage.eine_tx(txids[0])["verweildauer_ms"] == 99000
    assert ablage.eine_tx(txids[2999])["verweildauer_ms"] == 99000 - 2999


def test_unbeschreibbarer_ort_haelt_die_anwendung_nicht_auf(tmp_path):
    """DER Fall vom 27.08.2026: der CI-Probelauf haengt /fast mit einem
    fremden Eigentuemer ein -- genau wie ein NAS, auf dem der Nutzer seine
    Ordner im Dateimanager anlegt. Die Anwendung starb daran beim Import.

    Hier wird ein Verzeichnis erzwungen, wo eine Datei liegt: das scheitert
    unabhaengig von Rechten und Benutzer, also auch, wenn die Tests als root
    laufen."""
    sperre = tmp_path / "keinordner"
    sperre.write_text("ich bin eine Datei")

    ablage = store.oeffne(str(sperre / "unter" / "a.db"))
    assert ablage.verfuegbar is False
    assert ablage.grund                      # der Grund gehoert in die Anzeige

    # Und sie nimmt alles entgegen, ohne zu werfen -- der Rest der Anwendung
    # soll nicht an jeder Stelle nachfragen muessen.
    ablage.tx_aufgenommen("a" * 64, 1000, 1)
    ablage.tx_entfernt("a" * 64, 2000, "weg")
    ablage.luecke("zmq", 1, 3)
    ablage.mempool_punkt(1, 2, 3, 4.0, None)
    ablage.block_eingetragen({"hoehe": 1})
    ablage.sichern()
    assert ablage.tx_bestaetigt(["a" * 64], 1, 2) == {"bekannt": 0, "median_ms": None}
    assert ablage.letzte_bloecke() == []
    assert ablage.eine_tx("a" * 64) is None
    assert ablage.mempool_verlauf(0) == []
    assert ablage.letztes_diagramm() is None
    assert ablage.diagramm_zeit() is None
    ablage.reorg_vermerken()
    assert ablage.pool_anteile(144)["bloecke"] == 0
    assert ablage.aufraeumen() == 0
    assert ablage.eckdaten()["transaktionen"] == 0


def test_ein_brauchbarer_ort_meldet_sich_als_verfuegbar(ablage):
    assert ablage.verfuegbar is True


def test_platzhalter_baut_nur_fragezeichen():
    """Was in die Abfrage gehaengt wird, haengt allein an der ANZAHL."""
    assert store._platzhalter(0) == ""
    assert store._platzhalter(1) == "?"
    assert store._platzhalter(3) == "?,?,?"


def test_ein_boeser_quellenname_ist_ein_wert_und_kein_befehl(tmp_path):
    """Der Beweis zur nosec-Begruendung in store.py.

    Quellennamen koennen vom Nutzer stammen -- er darf eigene Feeds
    eintragen. Landete so ein Name im SQL-TEXT statt in den Parametern,
    genuegte einer mit einem DROP TABLE darin.
    """
    a = store.Ablage(str(tmp_path / "p.db"))
    a.nachricht_merken({"kennung": "k1", "quelle": "gut", "quellenname": "Gut",
                        "titel": "T", "verweis": "https://x.test",
                        "zeitpunkt": 1000}, 1000)
    boese = "x'); DROP TABLE nachrichten; --"
    assert a.nachrichten_lesen(10, [boese]) == []
    assert a.nachrichten_ungelesen([boese]) == 0
    # Die Tabelle steht noch, und der gute Eintrag auch.
    assert len(a.nachrichten_lesen(10)) == 1
    assert a.nachrichten_ungelesen() == 1


# ── Der Zaehler und die Liste muessen dasselbe meinen (11.09.2026) ─────────
#
# Der Betreiber: "er zeigt mir links unter nachrrichten 25 neue an und wenn ich
# drauf klicke ist es vieleicht eine .. weil die andere ich garnicht wolte."
#
# Die Vermutung war falsch, der Befund richtig. Nachgemessen: die Quellenwahl
# wirkte auf BEIDE Abfragen gleich. Der Unterschied war die GRENZE -- gezaehlt
# wurde ueber die ganze Ablage, gezeigt wurden die neuesten sechzig. Was
# darunter lag, konnte man nicht anklicken, blieb also ungelesen, und der
# Zaehler ging nie wieder herunter.
#
# Bei dreissig ab Werk eingeschalteten Quellen reicht EIN Abrufdurchgang, um
# mehr als sechzig Meldungen zu bringen. Der Zustand war also nicht selten,
# sondern der Normalfall nach kurzer Laufzeit.

def _meldung(a, kennung, quelle, zeitpunkt):
    a.nachricht_merken({"kennung": kennung, "quelle": quelle,
                        "quellenname": "X", "titel": kennung, "anriss": "",
                        "verweis": "https://x.test", "zeitpunkt": zeitpunkt,
                        "sprache": "de"}, zeitpunkt)


def test_der_zaehler_zaehlt_nicht_ueber_die_liste_hinaus(tmp_path):
    """Der Befund, nachgestellt: achtzig gelesene neuere Meldungen, darunter
    fuenfundzwanzig ungelesene aeltere. Vorher stand der Zaehler auf 25 und
    in der Liste war nichts Frisches zu sehen."""
    a = store.Ablage(str(tmp_path / "p.db"))
    for i in range(80):
        _meldung(a, f"neu{i}", "abo", 1_000_000 - i * 60)
    a.nachrichten_alle_gelesen()
    for i in range(25):
        _meldung(a, f"alt{i}", "abo", 900_000 - i * 60)

    liste = a.nachrichten_lesen(60, ["abo"])
    frisch = sum(1 for b in liste if not b["gelesen"])
    assert frisch == 0, "unterhalb der Grenze ist nichts anzuklicken"
    assert a.nachrichten_ungelesen(["abo"], 60) == 0, \
        "dann darf der Zaehler auch nichts versprechen"


def test_zaehler_und_liste_sagen_immer_dasselbe(tmp_path):
    """Die eigentliche Zusage: was der Zaehler nennt, ist in der Liste auch
    zu finden. Einmal quer durch verschiedene Lagen geprueft."""
    a = store.Ablage(str(tmp_path / "p.db"))
    for i in range(120):
        _meldung(a, f"m{i}", "abo", 1_000_000 - i * 60)
    a.nachricht_gelesen("m0")
    a.nachricht_gelesen("m5")
    for grenze in (1, 10, 60, 120, 200):
        liste = a.nachrichten_lesen(grenze, ["abo"])
        frisch = sum(1 for b in liste if not b["gelesen"])
        assert a.nachrichten_ungelesen(["abo"], grenze) == frisch, grenze


def test_abgeschaltete_quellen_zaehlen_nicht_mit(tmp_path):
    """Das war des Betreibers Vermutung -- und sie stimmte nicht, die Wahl wirkte
    schon vorher auf beide Abfragen. Der Test haelt es fest, damit es so
    bleibt."""
    a = store.Ablage(str(tmp_path / "p.db"))
    _meldung(a, "meine", "abo", 1_000_000)
    for i in range(25):
        _meldung(a, f"fremd{i}", "nicht_abonniert", 1_000_000 - i)
    assert a.nachrichten_ungelesen(["abo"], 60) == 1
    assert len(a.nachrichten_lesen(60, ["abo"])) == 1


# ── Was DIESER Knoten von einem Block gesehen hat ──────────────────────────
#
# Der Unterschied zu jedem Explorer der Welt: nicht "welche Transaktionen sind
# in dem Block" (das weiss jeder), sondern "welche davon lagen vorher bei MIR
# und wie lange". Einen First-Seen-Zeitstempel kann man nicht nachtraeglich
# erfinden.


def _mit_bloecken(tmp_path):
    ablage = store.Ablage(str(tmp_path / "a.db"))
    # Drei Transaktionen, unterschiedlich lange gesehen.
    for i, txid in enumerate(("aa" * 32, "bb" * 32, "cc" * 32)):
        ablage.tx_aufgenommen(txid, 1_000_000 + i * 1000, i)
    return ablage


def test_die_transaktionen_eines_blocks_kommen_mit_verweildauer(tmp_path):
    ablage = _mit_bloecken(tmp_path)
    ablage.tx_bestaetigt(["aa" * 32, "bb" * 32], 900_000, 1_100_000)

    liste = ablage.tx_eines_blocks(900_000)
    assert [z["txid"] for z in liste] == ["aa" * 32, "bb" * 32], \
        "die laengste Wartezeit gehoert nach oben"
    assert liste[0]["verweildauer_ms"] == 100_000
    assert liste[1]["verweildauer_ms"] == 99_000
    # Die dritte war nie in diesem Block.
    assert all(z["txid"] != "cc" * 32 for z in liste)


def test_ein_block_ohne_gesehene_transaktionen_ist_kein_fehler(tmp_path):
    ablage = _mit_bloecken(tmp_path)
    assert ablage.tx_eines_blocks(123_456) == []


def test_die_blockliste_wird_begrenzt(tmp_path):
    """Ein voller Block hat mehrere tausend Transaktionen. Sie alle durch die
    Schnittstelle zu schieben waere Last fuer eine Ansicht, die ohnehin nur
    die obersten zeigt."""
    ablage = store.Ablage(str(tmp_path / "b.db"))
    txids = ["%064x" % n for n in range(50)]
    for i, txid in enumerate(txids):
        ablage.tx_aufgenommen(txid, 1_000 + i, i)
    ablage.tx_bestaetigt(txids, 700_000, 500_000)
    assert len(ablage.tx_eines_blocks(700_000, grenze=10)) == 10


# ── Der HTLC-Strom (12.09.2026) ────────────────────────────────────────────

def _htlc(a, art, grund=None, raus="222", zeit=1_000_000):
    a.htlc_merken({"zeit_ms": zeit, "art": art, "rein_kanal": "111",
                   "raus_kanal": raus, "betrag": 1000, "gebuehr": 5,
                   "grund": grund})


def test_die_gruende_werden_nach_kanal_gezaehlt(tmp_path):
    """Nicht "es ist etwas schiefgegangen", sondern "an DIESEM Kanal ist
    siebenmal das Guthaben ausgegangen". Das eine ist eine Meldung, das
    andere ein Handgriff."""
    a = store.Ablage(str(tmp_path / "p.db"))
    for _ in range(7):
        _htlc(a, "link_fehl", "INSUFFICIENT_BALANCE", raus="222")
    _htlc(a, "link_fehl", "INSUFFICIENT_BALANCE", raus="333")
    _htlc(a, "erledigt")

    gruende = a.htlc_gruende()
    assert gruende[0]["anzahl"] == 7
    assert gruende[0]["grund"] == "INSUFFICIENT_BALANCE"
    assert gruende[0]["raus_kanal"] == "222"
    # Gelungenes zaehlt hier NICHT mit -- sonst waere die Liste unbrauchbar.
    assert all(g["grund"] for g in gruende)


def test_nur_fehlschlaege_bei_uns_zaehlen(tmp_path):
    """Weiter hinten im Weg gescheitert ist nichts, woran man etwas aendern
    kann. Es gehoert nicht in die Liste der Handgriffe."""
    a = store.Ablage(str(tmp_path / "p.db"))
    _htlc(a, "fehl", "IRGENDWAS")
    assert a.htlc_gruende() == []


def test_alte_ereignisse_zaehlen_nicht_mehr_mit(tmp_path):
    """Ein Kanal, der vor drei Monaten leer war, sagt nichts ueber heute."""
    a = store.Ablage(str(tmp_path / "p.db"))
    _htlc(a, "link_fehl", "INSUFFICIENT_BALANCE", zeit=1_000)
    assert a.htlc_gruende(seit_ms=500_000) == []
    assert a.htlc_gruende(seit_ms=0)[0]["anzahl"] == 1


def test_die_neuesten_ereignisse_stehen_vorne(tmp_path):
    a = store.Ablage(str(tmp_path / "p.db"))
    _htlc(a, "erledigt", zeit=1_000)
    _htlc(a, "link_fehl", "INSUFFICIENT_BALANCE", zeit=2_000)
    assert a.htlc_lesen(10)[0]["art"] == "link_fehl"


def test_eine_reorg_ist_keine_verlorene_meldung(ablage):
    """Bis zum 15.09.2026 zaehlte eine Reorg als Luecke. bitcoind hat sie
    aber sauber gemeldet -- verloren ging dabei nichts."""
    ablage.reorg_vermerken()
    ablage.luecke("zmq", 41, 43)
    d = ablage.eckdaten()
    assert d["luecken_24h"] == 1 and d["reorgs_24h"] == 1


def _block(ablage, hoehe, pool):
    ablage.block_eingetragen({
        "hoehe": hoehe, "hash": f"h{hoehe}", "blockzeit": 1_700_000_000 + hoehe,
        "empfangen_ms": 0, "gewicht": 0, "txzahl": 0, "gebuehren_sat": 0,
        "pool": pool, "botschaft": None, "bekannte_tx": 0,
        "verweildauer_ms": None})


def test_pool_anteile_nennen_ihre_grundlage(ablage):
    """Ein Anteil ohne die Zahl der Bloecke dahinter waere eine Behauptung."""
    for hoehe, pool in ((1, "Foundry USA"), (2, "Foundry USA"), (3, "AntPool"),
                        (4, None), (5, "Foundry USA")):
        _block(ablage, hoehe, pool)
    alle = ablage.pool_anteile(0)
    assert alle["bloecke"] == 5 and (alle["von_hoehe"], alle["bis_hoehe"]) == (1, 5)
    assert alle["pools"][0] == {"pool": "Foundry USA", "anzahl": 3, "anteil": 0.6}
    assert {"pool": None, "anzahl": 1, "anteil": 0.2} in alle["pools"], \
        "was sich nicht zuordnen laesst, bleibt als unbekannt stehen"
    juengste = ablage.pool_anteile(2)
    assert juengste["bloecke"] == 2 and juengste["von_hoehe"] == 4
    assert sum(p["anzahl"] for p in juengste["pools"]) == 2



# ------------------------------------------------------------ Netzgebuehren
#
# Einen Vier-Wochen-Verlauf kann man nicht nachtraeglich abrufen. Er entsteht,
# indem taeglich hingesehen wird, oder er entsteht nie -- dieselbe Sache wie
# beim ersten Sehen einer Transaktion. Deshalb liegt er hier und nicht in
# einer Einstellungsdatei.

def _messung(median, eigen=None):
    return {"median_ppm": median, "p25_ppm": 20, "p75_ppm": 400,
            "basis_median_msat": 1000, "linien": 65000, "kanaele": 33000,
            "eigen": {"satz_ppm": eigen}}


def test_eine_messung_kommt_zurueck_wie_sie_hineinging(ablage):
    ablage.netzgebuehren_merken("2026-09-18", 1758000000, _messung(112, 100))
    z = ablage.netzgebuehren_verlauf()[0]
    assert (z["tag"], z["median_ppm"], z["eigen_ppm"]) == ("2026-09-18", 112, 100)
    assert (z["p25_ppm"], z["p75_ppm"], z["linien"]) == (20, 400, 65000)


def test_zweimal_am_selben_tag_ueberschreibt_sich(ablage):
    """Sonst haette ein Tag mit zwei Messungen doppeltes Gewicht im Band --
    und ein Neustart, der eine Messung ausloest, verzoege es still."""
    ablage.netzgebuehren_merken("2026-09-18", 1, _messung(100))
    ablage.netzgebuehren_merken("2026-09-18", 2, _messung(140))
    verlauf = ablage.netzgebuehren_verlauf()
    assert len(verlauf) == 1 and verlauf[0]["median_ppm"] == 140


def test_der_verlauf_kommt_neueste_zuerst_und_begrenzt(ablage):
    for tag in range(1, 11):
        ablage.netzgebuehren_merken(f"2026-09-{tag:02d}", tag, _messung(tag))
    verlauf = ablage.netzgebuehren_verlauf(4)
    assert [z["tag"] for z in verlauf] == ["2026-09-10", "2026-09-09",
                                           "2026-09-08", "2026-09-07"]


def test_das_fenster_zaehlt_messtage_und_nicht_kalendertage(ablage):
    """Stand der Knoten zwei Wochen still, sollen die Tage davor noch
    zaehlen. Sonst waere das Band nach jedem laengeren Ausfall leer --
    ausgerechnet dann, wenn man es braucht."""
    ablage.netzgebuehren_merken("2026-01-01", 1, _messung(90))
    ablage.netzgebuehren_merken("2026-09-17", 2, _messung(110))
    ablage.netzgebuehren_merken("2026-09-18", 3, _messung(120))
    assert len(ablage.netzgebuehren_verlauf(28)) == 3


def test_alte_tageszeilen_werden_irgendwann_weggeraeumt(ablage):
    for tag in range(1, 13):
        ablage.netzgebuehren_merken(f"2026-09-{tag:02d}", tag, _messung(tag))
    assert ablage.netzgebuehren_aufraeumen(behalten=5) == 7
    verlauf = ablage.netzgebuehren_verlauf(28)
    assert len(verlauf) == 5 and verlauf[-1]["tag"] == "2026-09-08"


def test_ohne_datenbank_bleibt_es_still(tmp_path):
    """Die Auswertung ist ein Teil, nicht das Ganze -- auf einem NAS gehoert
    der eingehaengte Ordner schnell einmal jemand anderem."""
    leer = store.LeereAblage("kein Schreibrecht")
    leer.netzgebuehren_merken("2026-09-18", 1, _messung(100))
    assert leer.netzgebuehren_verlauf() == []
    assert leer.netzgebuehren_aufraeumen() == 0


# ── Die Verteilung, und eine Datenbank, die es schon gibt ──────────────────

STUFEN = [{"von": 0, "bis": 0, "anteil": 40},
          {"von": 1, "bis": 9, "anteil": 30},
          {"von": 10, "bis": 99, "anteil": 20},
          {"von": 100, "bis": 999, "anteil": 10},
          {"von": 1000, "bis": None, "anteil": 0}]


def test_die_verteilung_ueberlebt_den_neustart(ablage):
    """Gemessen wird einmal am Tag. Ohne Ablage waere die Verteilung nach
    jedem Neustart der Anwendung bis zum naechsten Messtag weg."""
    ablage.netzgebuehren_merken("2026-09-21", 1758400000,
                                {**_messung(100), "stufen": STUFEN})
    assert ablage.netzgebuehren_verlauf()[0]["stufen"] == STUFEN


def test_eine_messung_ohne_verteilung_bleibt_lesbar(ablage):
    """Alle Zeilen von vor dem 21.09.2026 haben keine."""
    ablage.netzgebuehren_merken("2026-09-20", 1758300000, _messung(100))
    assert ablage.netzgebuehren_verlauf()[0]["stufen"] is None


def test_eine_bestehende_datenbank_bekommt_die_spalte_nachgereicht(tmp_path):
    """DER PUNKT, an dem das sonst schiefgeht.

    Das Schema steht als CREATE TABLE IF NOT EXISTS da -- auf einer Datei,
    die es schon gibt, passiert also NICHTS. Wer die Anwendung seit Wochen
    laufen hat, haette die neue Spalte damit nie bekommen: der Fehler kaeme
    nicht beim Update, sondern beim naechsten Messen einen Tag spaeter.
    """
    pfad = str(tmp_path / "alt.db")
    alt = store.Ablage(pfad)
    alt.v.execute("DROP TABLE netzgebuehren")
    alt.v.execute("CREATE TABLE netzgebuehren (tag TEXT PRIMARY KEY, "
                  "zeit_s INTEGER NOT NULL, median_ppm INTEGER, "
                  "p25_ppm INTEGER, p75_ppm INTEGER, "
                  "basis_median_msat INTEGER, linien INTEGER, "
                  "kanaele INTEGER, eigen_ppm INTEGER)")
    alt.v.execute("INSERT INTO netzgebuehren (tag, zeit_s, median_ppm) "
                  "VALUES ('2026-09-01', 1, 88)")
    alt.v.commit()
    alt.schliesse()

    neu = store.Ablage(pfad)
    try:
        # Die alte Zeile steht noch da -- nachgereicht heisst nicht neu.
        assert neu.netzgebuehren_verlauf()[0]["median_ppm"] == 88
        neu.netzgebuehren_merken("2026-09-21", 2,
                                 {**_messung(100), "stufen": STUFEN})
        assert neu.netzgebuehren_verlauf()[0]["stufen"] == STUFEN
    finally:
        neu.schliesse()


# ── Befunde des Audits vom 22.09.2026 ──────────────────────────────────────

def _htlc_zeile(zeit_ms, art="weiterleitung"):
    return {"zeit_ms": zeit_ms, "art": art, "rein_kanal": "111",
            "raus_kanal": "222", "betrag": 1000, "gebuehr": 1, "grund": None}

def test_die_htlc_tabelle_wird_ueberhaupt_aufgeraeumt():
    """DER BEFUND: htlc_aufraeumen() war da und wurde NIE gerufen.

    Daneben haengt nachrichten_aufraeumen() seit jeher im Waechter. Auf
    einem Knoten, der weiterleitet, schreibt htlc_merken() bei jedem
    HTLC-Ereignis eine Zeile -- also dauernd. Die Tabelle wuchs damit ohne
    Ende, ausgerechnet auf dem Knoten, der seinen Zweck erfuellt.

    Diese Wache prueft die EINHAENGUNG, nicht die Funktion: dass es sie gibt,
    war ja nie das Problem. Sie muss dort stehen, wo ihr Schwesterstueck
    schon steht -- im selben taeglichen Fenster.
    """
    quelle = (Path(__file__).resolve().parents[1]
              / "satcortex" / "api.py").read_text(encoding="utf-8")
    stelle = quelle.index("auswertung.nachrichten_aufraeumen()")
    # Im selben Block -- bis zum naechsten "def" auf Methodenebene.
    rest = quelle[stelle:]
    block = rest[:rest.index("\n    def ")]
    assert "auswertung.htlc_aufraeumen()" in block


def test_kein_aufraeumer_leert_bei_null_tagen_die_ganze_tabelle(ablage):
    """netzgebuehren_aufraeumen klammert mit max(1, ...), die beiden
    anderen nicht. Heute unerreichbar -- aber eine Null loescht dort alles,
    und "heute unerreichbar" ist keine Eigenschaft, auf die man baut."""
    jetzt_ms = int(time.time() * 1000)
    ablage.htlc_merken(_htlc_zeile(jetzt_ms))
    assert ablage.htlc_aufraeumen(0) == 0
    assert ablage.htlc_aufraeumen(-5) == 0
    assert ablage.nachrichten_aufraeumen(0) == 0
