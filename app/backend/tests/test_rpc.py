"""Der Weg von bitcoind bis in die Uebersicht.

Der Punkt dieser Tests ist nicht die Rechnerei, sondern das Verhalten in den
Faellen, die der Nutzer tatsaechlich sieht: bitcoind ist noch nicht da,
bitcoind synchronisiert, bitcoind ist fertig.
"""
import socket
from unittest.mock import patch

import pytest

from satcortex import rpc


class FakeKnoten(rpc.Knoten):
    """Ein Knoten mit vorgegebenen Antworten.

    Die Signatur von ruf() muss die der echten Klasse spiegeln -- SAMT
    zeitlimit. Eine Attrappe, die weniger annimmt als das Original, faellt
    genau dann um, wenn jemand einen Aufruf verfeinert: der Test meldet dann
    einen TypeError statt eines Befunds. Dasselbe ist hier schon einmal
    passiert, als kettenlage anfing, ein eigenes Zeitlimit mitzugeben.
    """

    def __init__(self, antworten):
        super().__init__()
        self.antworten = antworten
        self.fristen = {}

    def ruf(self, methode, *params, zeitlimit=None):
        self.fristen[methode] = zeitlimit
        wert = self.antworten.get(methode)
        if isinstance(wert, Exception):
            raise wert
        return wert


def test_ohne_bitcoind_gibt_es_keine_lage():
    """Kein Absturz, wenn bitcoind noch startet -- das ist der Normalfall."""
    knoten = FakeKnoten({"getblockchaininfo": rpc.NichtErreichbar("noch nicht da")})
    assert rpc.kettenlage(knoten) is None


def test_falsche_zugangsdaten_sind_auch_keine_lage():
    knoten = FakeKnoten({"getblockchaininfo": rpc.RpcFehler("401")})
    assert rpc.kettenlage(knoten) is None


def test_waehrend_des_erstsyncs():
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 400000, "headers": 963597,
            "verificationprogress": 0.1234, "initialblockdownload": True,
            "size_on_disk": 120_000_000_000,
        },
        "getnetworkinfo": {"connections_in": 0, "connections_out": 10},
    })
    lage = rpc.kettenlage(knoten)
    assert lage["im_erstsync"] is True
    assert lage["hoehe"] == 400000
    assert lage["kopfzeilen"] == 963597
    assert abs(lage["fortschritt"] - 0.1234) < 1e-9
    # Ohne eingehende Verbindungen ist der Knoten Zuschauer, nicht Teilnehmer.
    assert lage["erreichbar"] is False


def test_fertig_und_erreichbar():
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 963597, "headers": 963597,
            "verificationprogress": 0.9999999, "initialblockdownload": False,
            "size_on_disk": 762_000_000_000,
        },
        "getnetworkinfo": {"connections_in": 37, "connections_out": 10},
    })
    lage = rpc.kettenlage(knoten)
    assert lage["im_erstsync"] is False
    assert lage["erreichbar"] is True
    assert lage["verbindungen_ein"] == 37


def test_fortschritt_ueberschreitet_nie_eins():
    """Core meldet gelegentlich knapp ueber 1.0 -- 100,3 % waere Unsinn."""
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 1, "headers": 1,
            "verificationprogress": 1.0000004, "initialblockdownload": False,
            "size_on_disk": 1,
        },
        "getnetworkinfo": {"connections_in": 1, "connections_out": 1},
    })
    assert rpc.kettenlage(knoten)["fortschritt"] == 1.0


def test_netzinfo_darf_fehlen():
    """getnetworkinfo kann scheitern, ohne dass die Kettenlage verlorengeht."""
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 5, "headers": 5,
            "verificationprogress": 0.5, "initialblockdownload": True,
            "size_on_disk": 10,
        },
        "getnetworkinfo": rpc.NichtErreichbar("weg"),
        "getpeerinfo": [],          # gemessen: wirklich keine Gegenstelle
    })
    lage = rpc.kettenlage(knoten)
    assert lage["hoehe"] == 5
    # Und die Verbindungszahlen kommen aus getpeerinfo -- der braucht laut
    # v31.1/src/rpc/net.cpp KEIN cs_main und kommt deshalb auch durch,
    # waehrend getnetworkinfo wartet.
    assert lage["netzinfo_da"] is False
    assert lage["verbindungen_aus"] == 0, "getpeerinfo lieferte eine leere Liste"


def test_ohne_jede_netzauskunft_wird_keine_null_erfunden():
    """Fallen BEIDE aus, ist die Zahl unbekannt -- nicht null. Als 0 stand
    dort "0 von mir aufgebaut · 0 von aussen angenommen", und das las sich
    wie ein Messwert. Aus dem Betrieb, 02.09.2026: "ich habe quasi keine
    Verbindung mehr zu irgendwas"."""
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 5, "headers": 5,
            "verificationprogress": 0.5, "initialblockdownload": True,
        },
        "getnetworkinfo": rpc.Beschaeftigt("antwortet nicht"),
        "getpeerinfo": rpc.Beschaeftigt("antwortet nicht"),
    })
    lage = rpc.kettenlage(knoten)
    assert lage["hoehe"] == 5, "die Kette selbst steht weiterhin da"
    assert lage["verbindungen_ein"] is None
    assert lage["verbindungen_aus"] is None
    assert lage["erreichbar"] is None


def test_die_verbindungszahlen_kommen_aus_getpeerinfo():
    """Auch wenn getnetworkinfo etwas anderes behauptet: getpeerinfo zaehlt
    die Verbindungen, die es WIRKLICH gibt, und braucht kein cs_main."""
    knoten = FakeKnoten({
        "getblockchaininfo": {
            "chain": "main", "blocks": 5, "headers": 5,
            "verificationprogress": 0.5, "initialblockdownload": True,
        },
        "getnetworkinfo": {"connections_in": 99, "connections_out": 99},
        "getpeerinfo": [
            {"network": "ipv4", "inbound": False},
            {"network": "ipv4", "inbound": False},
            {"network": "onion", "inbound": True},
        ],
    })
    lage = rpc.kettenlage(knoten)
    assert lage["verbindungen_aus"] == 2
    assert lage["verbindungen_ein"] == 1
    assert lage["erreichbar"] is True
    assert lage["netze"]["ipv4"] == 2 and lage["netze"]["onion"] == 1


# ── Was die Uebersicht waehrend des Abgleichs zeigen soll (25.08.2026) ───────

def _voller_knoten(**abweichungen):
    antworten = {
        "getblockchaininfo": {
            "chain": "main", "blocks": 393_957, "headers": 964_178,
            "verificationprogress": 0.0745, "initialblockdownload": True,
            "size_on_disk": 64_300_000_000, "time": 1_452_000_000,
        },
        "getnetworkinfo": {
            "connections_in": 0, "connections_out": 10,
            "localaddresses": [{"address": "abc.onion", "port": 8333, "score": 4}],
        },
        "getnettotals": {"totalbytesrecv": 64_000_000_000, "totalbytessent": 900_000},
        "getpeerinfo": [
            {"network": "ipv4"}, {"network": "ipv4"}, {"network": "ipv6"},
            {"network": "onion"}, {"network": "i2p"},
        ],
    }
    antworten.update(abweichungen)
    return FakeKnoten(antworten)


def test_zeitpunkt_der_kette_kommt_mit():
    """'Angekommen im Januar 2016' sagt mehr als jede Prozentzahl."""
    lage = rpc.kettenlage(_voller_knoten())
    assert lage["blockzeit"] == 1_452_000_000


def test_peers_werden_nach_netz_gezaehlt():
    """Wer Clearnet UND Onion bedient, ist im Netz die knappe Ressource."""
    lage = rpc.kettenlage(_voller_knoten())
    assert lage["netze"] == {"ipv4": 2, "ipv6": 1, "onion": 1, "sonstige": 1}


def test_ausgeliefertes_volumen_ist_der_beitrag():
    lage = rpc.kettenlage(_voller_knoten())
    assert lage["empfangen_bytes"] == 64_000_000_000
    assert lage["gesendet_bytes"] == 900_000


def test_eigene_adressen_werden_gemeldet():
    """Steht dort nur die Onion-Adresse, kennt der Knoten seine oeffentliche
    IP nicht -- dann findet ihn ueber Clearnet niemand, offener Port hin oder
    her. Genau dieser Fall trat am 25.08. auf."""
    lage = rpc.kettenlage(_voller_knoten())
    # Der score kommt seit dem 01.09.2026 mit: die Karte sortiert danach und
    # muss getnetworkinfo deshalb nicht ein zweites Mal stellen -- den einen
    # Aufruf, der laut v31.1/src/rpc/net.cpp LOCK(cs_main) nimmt.
    assert lage["adressen"] == [
        {"adresse": "abc.onion", "port": 8333, "score": 4}]


def test_faellt_ein_einzelner_aufruf_aus_bleibt_der_rest_stehen():
    """getpeerinfo kann waehrend eines Neustarts scheitern -- die Uebersicht
    darf deswegen nicht komplett leer bleiben."""
    knoten = _voller_knoten(getpeerinfo=rpc.RpcFehler("gerade nicht"),
                            getnettotals=rpc.NichtErreichbar("weg"))
    lage = rpc.kettenlage(knoten)
    assert lage["hoehe"] == 393_957
    assert lage["netze"] == {"ipv4": 0, "ipv6": 0, "onion": 0, "sonstige": 0}
    assert lage["gesendet_bytes"] == 0


# ── Mempool: erst nach dem Abgleich, dann mit der Zahl, die zaehlt ───────────

def test_waehrend_des_abgleichs_gibt_es_keinen_mempool():
    """Core nimmt waehrend des Erstsyncs keine Transaktionen an -- "loaded"
    ist false, und es gibt schlicht nichts zu zeigen."""
    knoten = FakeKnoten({"getmempoolinfo": {"loaded": False}})
    assert rpc.mempoollage(knoten) is None


def test_ohne_bitcoind_auch_kein_mempool():
    knoten = FakeKnoten({"getmempoolinfo": rpc.NichtErreichbar("weg")})
    assert rpc.mempoollage(knoten) is None


def _mempool(**abweichungen):
    m = {
        "loaded": True, "size": 4200, "bytes": 12_000_000, "usage": 45_000_000,
        "maxmempool": 300_000_000, "total_fee": "0.04812000",
        # str_amount: Core liefert diese als Zeichenkette, damit keine
        # Fliesskomma-Ungenauigkeit entsteht.
        "mempoolminfee": "0.00001000", "minrelaytxfee": "0.00001000",
    }
    m.update(abweichungen)
    return FakeKnoten({"getmempoolinfo": m})


def test_gebuehrenrate_wird_in_sat_pro_vbyte_umgerechnet():
    """0,00001 BTC/kvB ist die Vorgabe von Core und entspricht 1 sat/vB."""
    lage = rpc.mempoollage(_mempool())
    assert lage["purge_sat_vb"] == 1.0
    assert lage["minimum_sat_vb"] == 1.0


def test_ein_voller_mempool_verwirft_und_sagt_es():
    """Die Verwerfungsgrenze ueber der Mindestrate heisst: der Mempool ist voll
    und wirft das Guenstigste hinaus. Genau diese Zahl sehen die grossen
    Explorer nicht, weil sie ihr Limit so hoch drehen, dass sie nie verwerfen."""
    lage = rpc.mempoollage(_mempool(mempoolminfee="0.00004500"))
    assert lage["purge_sat_vb"] == 4.5
    assert lage["verwirft_gerade"] is True


def test_ein_leerer_mempool_verwirft_nicht():
    assert rpc.mempoollage(_mempool())["verwirft_gerade"] is False


def test_auslastung_wird_berechnet():
    lage = rpc.mempoollage(_mempool())
    assert lage["auslastung"] == 0.15
    assert lage["transaktionen"] == 4200


def test_unerwartete_werte_stuerzen_nicht_ab():
    lage = rpc.mempoollage(_mempool(mempoolminfee=None, maxmempool=0))
    assert lage["purge_sat_vb"] == 0.0
    assert lage["auslastung"] == 0.0


def test_die_kennung_des_knotens_kommt_mit():
    """Grundlage der Versionspruefung: was LAEUFT, nicht was gezogen werden
    sollte."""
    knoten = _voller_knoten(getnetworkinfo={
        "connections_in": 0, "connections_out": 10,
        "subversion": "/Satoshi:31.1.0/", "localaddresses": []})
    assert rpc.kettenlage(knoten)["kennung"] == "/Satoshi:31.1.0/"


def test_fehlende_kennung_ist_kein_fehler():
    lage = rpc.kettenlage(_voller_knoten())
    assert lage["kennung"] == ""


# ── "beschaeftigt" ist nicht "weg" ─────────────────────────────────────────

def test_zeitlimit_heisst_beschaeftigt_nicht_weg(monkeypatch):
    """Der Unterschied, an dem die Uebersicht gescheitert ist: ein Zeitlimit
    heisst "da, aber schreibt gerade weg", eine abgelehnte Verbindung heisst
    "laeuft nicht". Vorher war beides dieselbe Ausnahme -- und die Anzeige
    machte daraus "wird gestartet", im Minutentakt."""
    def zeitlimit(*a, **k):
        raise socket.timeout("timed out")
    monkeypatch.setattr(rpc.urllib.request, "urlopen", zeitlimit)

    with pytest.raises(rpc.Beschaeftigt):
        rpc.Knoten().ruf("getblockchaininfo")


def test_zeitlimit_auch_wenn_urllib_es_verpackt(monkeypatch):
    """urllib reicht das Zeitlimit gern als URLError mit .reason weiter.
    Ohne diesen Griff saehe ein Zeitlimit aus wie ein abgelehnter Versuch."""
    def verpackt(*a, **k):
        raise rpc.urllib.error.URLError(socket.timeout("timed out"))
    monkeypatch.setattr(rpc.urllib.request, "urlopen", verpackt)

    with pytest.raises(rpc.Beschaeftigt):
        rpc.Knoten().ruf("getblockchaininfo")


def test_abgelehnte_verbindung_bleibt_nicht_erreichbar(monkeypatch):
    def abgelehnt(*a, **k):
        raise ConnectionRefusedError("Connection refused")
    monkeypatch.setattr(rpc.urllib.request, "urlopen", abgelehnt)

    with pytest.raises(rpc.NichtErreichbar) as f:
        rpc.Knoten().ruf("getblockchaininfo")
    assert not isinstance(f.value, rpc.Beschaeftigt)


def test_beschaeftigt_ist_eine_unterklasse(monkeypatch):
    """Damit bestehender Code, der NichtErreichbar faengt, weiter greift.
    Sechs Stellen rufen kettenlage(), eine davon ist ein Hintergrundfaden --
    eine neue Ausnahme, die dort durchschlaegt, waere ein Ausfall."""
    assert issubclass(rpc.Beschaeftigt, rpc.NichtErreichbar)


def test_kettenlage_wirft_weiterhin_nichts(monkeypatch):
    """Die alte Zusicherung bleibt: kettenlage gibt None zurueck, egal was
    schiefgeht. Sonst haette die neue Unterscheidung sechs Aufrufstellen
    kaputtgemacht."""
    def zeitlimit(*a, **k):
        raise socket.timeout("timed out")
    monkeypatch.setattr(rpc.urllib.request, "urlopen", zeitlimit)
    assert rpc.kettenlage(rpc.Knoten()) is None


def test_lage_mit_grund_unterscheidet_die_drei_faelle(monkeypatch):
    def zeitlimit(*a, **k):
        raise socket.timeout("timed out")
    monkeypatch.setattr(rpc.urllib.request, "urlopen", zeitlimit)
    lage, grund = rpc.lage_mit_grund(rpc.Knoten())
    assert lage is None and grund == rpc.KNOTEN_BESCHAEFTIGT

    def abgelehnt(*a, **k):
        raise ConnectionRefusedError("Connection refused")
    monkeypatch.setattr(rpc.urllib.request, "urlopen", abgelehnt)
    lage, grund = rpc.lage_mit_grund(rpc.Knoten())
    assert lage is None and grund == rpc.KNOTEN_WEG


def test_die_lage_bekommt_mehr_geduld_als_der_rest():
    """Waehrend Core den chainstate wegschreibt, wartet getblockchaininfo auf
    dieselbe Sperre. Am 28.08.2026 gemessen: rund ein Fuenftel der Zeit war
    der Knoten nicht ansprechbar, auch nach zwanzig Sekunden nicht. Mit fuenf
    Sekunden faellt die Anzeige bei jedem fuenften Abruf zurueck.

    Seit dem 02.09.2026 gilt das fuer die GANZE Lage, nicht fuer einen
    Aufruf: getnetworkinfo nimmt dieselbe Sperre (v31.1, src/rpc/net.cpp)
    und fiel mit fuenf Sekunden bei jedem Schreibvorgang aus. Vier eigene
    Fristen waeren aber im schlimmsten Fall eine Minute, bei einem Takt von
    zehn Sekunden. Deshalb ein gemeinsames Budget: jeder Aufruf bekommt,
    was noch uebrig ist, und die ganze Lage ist danach vorbei."""
    knoten = FakeKnoten({
        "getblockchaininfo": {"chain": "main", "blocks": 1, "headers": 1,
                              "verificationprogress": 1.0,
                              "initialblockdownload": False},
        "getnetworkinfo": {"connections_in": 0, "connections_out": 0},
    })
    rpc.kettenlage(knoten)
    assert rpc.GEDULD_LAGE_SEKUNDEN > rpc.Knoten.zeitlimit
    # Der erste Aufruf bekommt (fast) das ganze Budget ...
    assert knoten.fristen["getblockchaininfo"] > rpc.GEDULD_SEKUNDEN - 1
    # ... und jeder weitere hoechstens noch den Rest davon, nie mehr.
    for methode, frist in knoten.fristen.items():
        assert frist is not None, methode
        assert frist <= rpc.GEDULD_SEKUNDEN, methode
    summe_waere = rpc.GEDULD_SEKUNDEN * len(knoten.fristen)
    assert max(knoten.fristen.values()) < summe_waere, (
        "vier eigene Fristen waeren im schlimmsten Fall ein Vielfaches")


# ── Was 503 bedeutet ──────────────────────────────────────────────────────
#
# Geprueft gegen Bitcoin Core v31.1: src/httpserver.cpp antwortet mit
# HTTP_SERVICE_UNAVAILABLE und "Work queue depth exceeded", sobald die
# Schlange voll ist (DEFAULT_HTTP_WORKQUEUE=64, DEFAULT_HTTP_THREADS=16 in
# src/httpserver.h). Das ist woertlich "da, aber beschaeftigt" -- und landete
# bis zum 01.09.2026 bei RpcFehler, also bei "antwortet und lehnt ab".


def _fehler(code, rumpf=b""):
    import io
    import urllib.error

    def werfen(*_a, **_kw):
        raise urllib.error.HTTPError(
            "http://bitcoind:8332/", code, "x", {}, io.BytesIO(rumpf))
    return werfen


def test_volle_warteschlange_heisst_beschaeftigt(monkeypatch):
    import urllib.request
    from satcortex import rpc

    monkeypatch.setattr(urllib.request, "urlopen",
                        _fehler(503, b"Work queue depth exceeded"))
    with pytest.raises(rpc.Beschaeftigt):
        rpc.Knoten().ruf("getblockchaininfo")


def test_beschaeftigt_ist_kein_rpcfehler(monkeypatch):
    """Der Unterschied ist der ganze Zweck der Klasse: das eine ist
    abzuwarten, das andere zu beheben."""
    import urllib.request
    from satcortex import rpc

    monkeypatch.setattr(urllib.request, "urlopen",
                        _fehler(503, b"Work queue depth exceeded"))
    try:
        rpc.Knoten().ruf("getblockchaininfo")
    except rpc.RpcFehler:                       # pragma: no cover
        pytest.fail("503 darf nicht als RpcFehler ankommen")
    except rpc.Beschaeftigt:
        pass


def test_abgelehnter_aufruf_bleibt_ein_rpcfehler(monkeypatch):
    import urllib.request
    from satcortex import rpc

    monkeypatch.setattr(urllib.request, "urlopen",
                        _fehler(500, b'{"error": {"message": "kaputt"}}'))
    with pytest.raises(rpc.RpcFehler):
        rpc.Knoten().ruf("getblockchaininfo")


def test_das_netz_wird_nicht_erfunden(monkeypatch):
    """Fehlt die Angabe, ist sie unbekannt -- nicht "main". Ausgerechnet bei
    der Frage "haenge ich am richtigen Netz" darf nichts geraten werden."""
    from satcortex import rpc

    class Knoten:
        def ruf(self, methode, *p, **kw):
            if methode == "getblockchaininfo":
                return {"blocks": 1, "headers": 1, "verificationprogress": 1.0}
            raise rpc.NichtErreichbar("x")

    assert rpc.kettenlage(Knoten())["kette"] == ""
