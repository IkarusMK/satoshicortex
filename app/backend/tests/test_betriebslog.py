"""Die Anwendung soll sagen, was sie tut.

Aus dem Betrieb, 05.09.2026: "was mir auch aufgefallen ist, dass unter Protokoll und
dann Satoshi -- also unsere App -- nie wirklich was steht ausser diesen
Standard vier Zeilen. Aber sonst gibt unsere App kein Protokoll wieder??"

Nachgesehen: er hat recht, und es war keine Stoerung. Die Anwendung schrieb
ausschliesslich bei EREIGNISSEN -- Konfiguration geaendert, Sicherung
abgelegt, Ausnahme gefangen. Waehrend eines Erstabgleichs passiert davon
tagelang nichts. Uebrig blieben die paar Zeilen vom Start.

Ein Protokoll, das ueber eine laufende Maschine nichts sagt, ist keines. Der
Sammler kennt die Lage ohnehin alle fuenf Sekunden; hier wird daraus etwas
Lesbares -- Uebergaenge sofort, Fortschritt in ruhigem Takt.
"""
import logging
from pathlib import Path

import pytest

from satcortex import betriebslog, rpc


class Uhr:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def weiter(self, sekunden: float) -> None:
        self.t += sekunden


@pytest.fixture
def uhr():
    return Uhr()


@pytest.fixture
def schreiber(uhr, caplog):
    # Immer auf INFO, und vor der zu pruefenden Stelle wird geleert. Vorher
    # stand hier "with caplog.at_level(...)" um die interessante Zeile -- das
    # sah nach Abgrenzung aus, war aber keine: caplog haengt ohnehin dauerhaft
    # am Wurzel-Logger und zeichnete alles davor mit auf, sobald dessen Stufe
    # INFO war. Die Tests bestanden nur, solange sie allein liefen.
    caplog.set_level(logging.INFO)
    return betriebslog.Betriebslog(uhr=uhr)


def lage(hoehe=800000, kopfzeilen=965000, erstsync=True, ein=3, aus=10):
    return {"hoehe": hoehe, "kopfzeilen": kopfzeilen,
            "fortschritt": hoehe / kopfzeilen, "im_erstsync": erstsync,
            "verbindungen_ein": ein, "verbindungen_aus": aus}


def zeilen(caplog):
    return [s.getMessage() for s in caplog.records]


def test_der_erste_kontakt_wird_gemeldet(schreiber, caplog):
    caplog.clear()
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    assert len(zeilen(caplog)) == 1
    assert "800.000" in zeilen(caplog)[0]


def test_zwischendurch_bleibt_es_still(schreiber, uhr, caplog):
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    caplog.clear()
    for i in range(1, 10):
        uhr.weiter(5)
        schreiber.melde(lage(hoehe=800000 + i), rpc.KNOTEN_DA)
    assert zeilen(caplog) == []


def test_nach_dem_takt_kommt_eine_fortschrittszeile(schreiber, uhr, caplog):
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    uhr.weiter(betriebslog.TAKT_SEKUNDEN)
    caplog.clear()
    schreiber.melde(lage(hoehe=800600), rpc.KNOTEN_DA)
    text = zeilen(caplog)[0]
    assert "800.600" in text
    # 600 Bloecke in zehn Minuten sind 60 je Minute.
    assert "60" in text


def test_ohne_fortschritt_steht_das_auch_da(schreiber, uhr, caplog):
    """Ein haengender Abgleich ist die wichtigste Meldung ueberhaupt."""
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    uhr.weiter(betriebslog.TAKT_SEKUNDEN)
    caplog.clear()
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    assert "kein Fortschritt" in zeilen(caplog)[0]


def test_ein_ausfall_wird_sofort_gemeldet_und_nur_einmal(schreiber, uhr, caplog):
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    caplog.clear()
    schreiber.melde(None, rpc.KNOTEN_WEG)
    uhr.weiter(5)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    uhr.weiter(5)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    assert len(zeilen(caplog)) == 1


def test_die_rueckkehr_wird_gemeldet(schreiber, uhr, caplog):
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    uhr.weiter(30)
    caplog.clear()
    schreiber.melde(lage(hoehe=800010), rpc.KNOTEN_DA)
    assert "wieder" in zeilen(caplog)[0].lower()


def test_beschaeftigt_ist_kein_ausfall(schreiber, uhr, caplog):
    """Core haelt cs_main beim Schreiben des chainstate -- das ist normal.

    Waere das ein Ausfall, stuende bei jedem Schreibvorgang eine Warnung im
    Protokoll, und die echten Ausfaelle gingen darin unter.
    """
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    caplog.clear()
    schreiber.melde(None, rpc.KNOTEN_BESCHAEFTIGT)
    assert zeilen(caplog) == []


def test_das_ende_des_abgleichs_wird_gemeldet(schreiber, uhr, caplog):
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    uhr.weiter(5)
    caplog.clear()
    schreiber.melde(lage(hoehe=965000, erstsync=False), rpc.KNOTEN_DA)
    assert any("Kette" in z for z in zeilen(caplog))


def test_nach_dem_abgleich_wird_seltener_gemeldet(schreiber, uhr, caplog):
    """Ein fertiger Knoten meldet einen Block alle zehn Minuten -- da braucht
    es keine Fortschrittszeile im selben Takt."""
    schreiber.melde(lage(hoehe=965000, erstsync=False), rpc.KNOTEN_DA)
    uhr.weiter(betriebslog.TAKT_SEKUNDEN)
    caplog.clear()
    schreiber.melde(lage(hoehe=965001, erstsync=False), rpc.KNOTEN_DA)
    assert zeilen(caplog) == []
    uhr.weiter(betriebslog.TAKT_RUHE_SEKUNDEN)
    caplog.clear()
    schreiber.melde(lage(hoehe=965002, erstsync=False), rpc.KNOTEN_DA)
    assert len(zeilen(caplog)) == 1


def test_eine_ausnahme_im_protokoll_trifft_nie_den_aufrufer(schreiber, caplog):
    """Der Sammler darf nicht daran sterben, dass er etwas melden wollte."""
    schreiber.melde({"hoehe": None}, rpc.KNOTEN_DA)   # kaputte Lage


def test_ein_knoten_der_nie_kam_wird_nach_einer_weile_gemeldet(schreiber, uhr, caplog):
    """Der stillste aller Faelle -- und der, bei dem Stille am meisten schadet.

    Beim Start antwortet bitcoind minutenlang nicht: es laedt den chainstate.
    Das sofort zu melden waere Rauschen. Kommt es aber ueberhaupt nicht, sagte
    das Protokoll bisher gar nichts, und die Anwendung sah aus wie tot.
    """
    caplog.clear()
    schreiber.melde(None, rpc.KNOTEN_WEG)
    uhr.weiter(60)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    assert zeilen(caplog) == []

    caplog.clear()
    uhr.weiter(betriebslog.TAKT_SEKUNDEN)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    assert len(zeilen(caplog)) == 1
    assert "seit dem Start" in zeilen(caplog)[0]


def test_ein_dauerausfall_wiederholt_sich_nur_im_ruhigen_takt(schreiber, uhr, caplog):
    """Einmal melden ist richtig, einmal fuer immer schweigen nicht.

    Wer nach zwei Tagen ins Protokoll sieht, soll erkennen, dass der Zustand
    ANHAELT -- und nicht nur eine Zeile von vorgestern finden.
    """
    schreiber.melde(lage(), rpc.KNOTEN_DA)
    caplog.clear()
    schreiber.melde(None, rpc.KNOTEN_WEG)
    uhr.weiter(betriebslog.TAKT_SEKUNDEN - 1)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    assert zeilen(caplog) == ["bitcoind antwortet nicht mehr."]

    caplog.clear()
    uhr.weiter(2)
    schreiber.melde(None, rpc.KNOTEN_WEG)
    assert len(zeilen(caplog)) == 1
    assert "weiterhin" in zeilen(caplog)[0]


def test_die_protokollansicht_sorgt_selbst_dafuer_dass_sie_etwas_sieht():
    """Gefunden am 05.09.2026 im Pruefstand: die Ansicht war leer.

    Der Ringspeicher haengt am Wurzel-Logger, und dessen Vorgabe ist WARNING.
    Jede INFO-Meldung fiel damit weg, BEVOR ein Handler sie sah -- ohne dass
    irgendwo ein Fehler stand. Im Container ging es gut, weil __main__ vorher
    basicConfig(level=INFO) ruft. Eine Anzeige, die davon abhaengt, wie der
    Prozess gestartet wurde, ist keine.
    """
    from satcortex import logs

    wurzel = logging.getLogger()
    vorher = wurzel.level
    try:
        wurzel.setLevel(logging.WARNING)
        logs.mitschreiben()
        assert wurzel.isEnabledFor(logging.INFO)
    finally:
        wurzel.setLevel(vorher)


def test_die_gruende_kommen_aus_rpc_und_nicht_aus_der_fantasie():
    """Der Fehler, der diesen Test verdient hat (05.09.2026).

    Im Modul stand "knoten_beschaeftigt" -- ein Wert, den es nicht gibt; die
    Konstante heisst "beschaeftigt". Jeder chainstate-Schreibvorgang waere
    damit als Ausfall protokolliert worden, also rund jeder fuenfte Abruf
    waehrend des Abgleichs. Aufgefallen ist es NICHT in den Pruefungen: die
    benutzten dieselbe erfundene Zeichenkette und stimmten mit dem Fehler
    ueberein.
    """
    quelle = (Path(betriebslog.__file__)).read_text(encoding="utf-8")
    assert "knoten_beschaeftigt" not in quelle
    assert "rpc.KNOTEN_BESCHAEFTIGT" in quelle
