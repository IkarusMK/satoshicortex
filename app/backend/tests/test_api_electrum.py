"""Electrum ueber die Schnittstelle: Schalter, Konten, Wege.

Hier wird die Verdrahtung geprueft -- was gemerkt wird, was in die torrc
kommt, was die Oberflaeche erfaehrt. Der Server selbst laeuft in diesen
Tests nicht: der Testclient startet jede Anfrage in einer eigenen
Ereignisschleife, und ein darin gestarteter Server stuerbe mit ihr. Dass er
wirklich lauscht, pruefen test_electrumbetrieb.py und test_electrum_core.py
mit echten Sockets.

Alle Werte ausgedacht; die Schluessel sind die Testvektoren aus BIP-84.
"""
import pytest

from satcortex import electrumserver, lesewallet, rpc, settings
from tests.test_api import _client, _platz, _richte_ein
from tests.test_lesewallet import BIP84_ZPRV, BIP84_ZPUB, _mit_version

VPUB = _mit_version(BIP84_ZPUB, "045f1cf6")


class Server:
    """Statt des echten Servers: merkt sich nur, dass er laufen soll."""

    def __init__(self, dienst, bestand, tls=None, host="", port=0, **kw):
        self.port = port or 50001
        self.tls = tls

    async def starten(self):
        pass

    async def beenden(self):
        pass

    def anstossen(self, block=True):
        pass


@pytest.fixture
def ohne_netz(monkeypatch):
    monkeypatch.setattr(electrumserver, "ElectrumServer", Server)


@pytest.fixture
def core(monkeypatch):
    """bitcoind auf Regtest -- nur was das Anmelden braucht."""
    lage = {"kette": "regtest", "weg": False}

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        if lage["weg"]:
            raise rpc.NichtErreichbar("weg")
        if methode == "getblockchaininfo":
            return {"chain": lage["kette"]}
        if methode == "getwalletinfo":
            return {"scanning": False}
        if methode == "unloadwallet":
            return {}
        raise rpc.NichtErreichbar(methode)
    monkeypatch.setattr(rpc.Knoten, "ruf", ruf)
    monkeypatch.setattr(lesewallet, "anmelden", lambda knoten, s, art, seit=0, **kw:
                        lesewallet.walletname(s, art))
    return lage


@pytest.fixture
def client(tmp_path, monkeypatch, ohne_netz):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    _richte_ein(c)
    return c


def _torrc(client):
    return (client.tmp / "config" / "tor.conf").read_text()


def _fertig(client):
    betrieb = client.app.state.electrum
    for faden in list(betrieb._faeden):
        faden.join(5)


# ── Die Uebersicht ─────────────────────────────────────────────────────────

def test_die_uebersicht_am_anfang(client):
    d = client.get("/api/electrum").json()
    assert d["an"] is False and d["laeuft"] is False
    assert d["konten"] == []
    assert d["arten"] == ["pkh", "sh-wpkh", "wpkh", "tr"]
    assert d["tls"] is None
    # Ohne die Variablen reicht die Compose nichts durch -- sie ist aelter.
    assert d["heimnetz"] == {"stand": "compose_alt", "port": None}
    assert d["tor"]["moeglich"] is True and d["tor"]["adresse"] == ""


def test_die_uebersicht_kennt_ein_freigegebenes_heimnetz(tmp_path, monkeypatch,
                                                         ohne_netz):
    _platz(monkeypatch, 4000)
    konf = settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"),
        electrum_bind="0.0.0.0", electrum_lan_port="50001")
    c = _client(tmp_path, konf=konf)
    _richte_ein(c)
    assert c.get("/api/electrum").json()["heimnetz"] == {
        "stand": "bereit", "port": 50001}


def test_ohne_anmeldung_gibt_es_nichts(tmp_path, monkeypatch, ohne_netz):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path, anmelden=False)
    assert c.get("/api/electrum").status_code == 401
    assert c.post("/api/electrum/schalter", json={"an": True}).status_code == 401


# ── Der Schalter ───────────────────────────────────────────────────────────

def test_einschalten_merkt_es_und_legt_den_onion_dienst_an(client):
    assert "onion-electrum" not in _torrc(client)
    assert client.post("/api/electrum/schalter", json={"an": True}).status_code == 200
    d = client.get("/api/electrum").json()
    assert d["an"] is True and d["laeuft"] is True
    assert d["tls"]["pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert "HiddenServicePort 50001 " in _torrc(client)


def test_ausschalten_nimmt_den_onion_dienst_wieder_heraus(client):
    client.post("/api/electrum/schalter", json={"an": True})
    client.post("/api/electrum/schalter", json={"an": False})
    d = client.get("/api/electrum").json()
    assert d["an"] is False and d["laeuft"] is False
    assert "onion-electrum" not in _torrc(client)


def test_der_onion_dienst_ueberlebt_den_zeus_zugang(client):
    """Jeder Weg zur torrc fuehrt durch dieselbe Stelle. Staende Electrum
    nur beim Einschalten darin, naehme die naechste Aenderung ihn wieder
    heraus."""
    client.post("/api/electrum/schalter", json={"an": True})
    client.app.state.tor_neu_ablegen()
    assert "onion-electrum" in _torrc(client)


# ── Konten ─────────────────────────────────────────────────────────────────

def test_ein_konto_anmelden(client, core):
    antwort = client.post("/api/electrum/konto", json={
        "schluessel": VPUB, "name": "BitBox"})
    assert antwort.status_code == 200
    wallet = antwort.json()["wallet"]
    _fertig(client)
    [konto] = client.get("/api/electrum").json()["konten"]
    assert (konto["wallet"], konto["name"], konto["art"]) == (
        wallet, "BitBox", "wpkh")
    assert konto["sucht"] is False and konto["fehler"] is None


def test_der_schluessel_landet_nirgends_in_den_einstellungen(client, core):
    client.post("/api/electrum/konto", json={"schluessel": VPUB,
                                             "name": "BitBox"})
    _fertig(client)
    text = (client.tmp / "config" / "einrichtung.json").read_text()
    assert VPUB[4:30] not in text and "tpub" not in text


@pytest.mark.parametrize("schluessel,meldung", [
    ("hallo", "el_kein_schluessel"),
    (BIP84_ZPRV, "el_privat"),
    (_mit_version(BIP84_ZPUB, "043587cf"), "el_art_waehlen"),
])
def test_was_nicht_passt_kommt_mit_grund_zurueck(client, core, schluessel,
                                                 meldung):
    antwort = client.post("/api/electrum/konto", json={
        "schluessel": schluessel, "name": "x"})
    assert antwort.status_code == 400
    assert antwort.json()["detail"]["meldung"] == meldung


def test_ein_schluessel_aus_dem_falschen_netz(client, core):
    core["kette"] = "main"
    antwort = client.post("/api/electrum/konto", json={
        "schluessel": VPUB, "name": "BitBox"})
    assert antwort.json()["detail"]["meldung"] == "el_falsches_netz"


def test_ohne_bitcoind_kein_anmelden(client, core):
    core["weg"] = True
    antwort = client.post("/api/electrum/konto", json={
        "schluessel": VPUB, "name": "BitBox"})
    assert antwort.status_code == 503
    assert antwort.json()["detail"]["meldung"] == "el_bitcoind_weg"


def test_ein_konto_abmelden(client, core):
    wallet = client.post("/api/electrum/konto", json={
        "schluessel": VPUB, "name": "BitBox"}).json()["wallet"]
    _fertig(client)
    antwort = client.post(f"/api/electrum/konto/{wallet}/abmelden")
    assert antwort.status_code == 200
    assert client.get("/api/electrum").json()["konten"] == []


def test_ein_unbekanntes_konto_abmelden(client, core):
    antwort = client.post("/api/electrum/konto/geldgeber/abmelden")
    assert antwort.status_code == 404
    assert antwort.json()["detail"]["meldung"] == "el_unbekannt"


def test_ueberlange_eingaben_werden_abgewiesen(client, core):
    antwort = client.post("/api/electrum/konto", json={
        "schluessel": "x" * 5000, "name": "BitBox"})
    assert antwort.status_code == 422
