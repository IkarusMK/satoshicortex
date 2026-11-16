"""Befund vom 15.11.2026: Zeilen-Einschleusung in die Konfigurationsdateien.

`str.splitlines()` trennt nicht nur an \\n, sondern auch an U+2028, U+2029,
U+0085, \\x0b, \\x0c und \\x1c-\\x1e. `nur_eine_zeile` liess diese Zeichen
durch, die Lese-Aendern-Schreiben-Helfer in nodeconfig zerlegten die Datei mit
splitlines() und fuegten sie mit "\\n" wieder zusammen -- aus dem unscheinbaren
Zeichen wurde beim naechsten Schreibgang eine echte Zeile. Ueber den Alias
landete so `no-macaroons=true` in lnd.conf, ueber eine IPv6-Adresse mit
Scope-Kennung (`fe80::1%x ...`) ein `startupnotify=` in bitcoin.conf, das
Core durch eine Shell schickt.

Diese Tests gehen denselben Weg wie die Nachweise: von der Anmeldung bis in die
Datei, und danach jede Schicht einzeln.
"""
import logging

import pytest

from satcortex import api, dyndns, nodeconfig
from satcortex.services import Konfigurationsablage
from test_api import NETZWEGE, _client, _lnd_conf, _platz

TRENNER = [
    ("U+2028", " "), ("U+2029", " "), ("U+0085", "\u0085"),
    ("x0b", "\x0b"), ("x0c", "\x0c"), ("x1c", "\x1c"), ("x1d", "\x1d"),
    ("x1e", "\x1e"),
]
KENNUNGEN = [k for k, _ in TRENNER]
ZEICHEN = [z for _, z in TRENNER]


def _zeilen(text):
    """Die Zeilen so, wie die Dienste sie lesen: nur an LF getrennt."""
    return text.split("\n")


# ---------------------------------------------------- nur_eine_zeile

@pytest.mark.parametrize("trenner", ZEICHEN, ids=KENNUNGEN)
def test_nur_eine_zeile_lehnt_jedes_trennzeichen_ab(trenner):
    with pytest.raises(ValueError):
        nodeconfig.nur_eine_zeile("x" + trenner + "no-macaroons=true")


@pytest.mark.parametrize("alias", [
    "Mein Knoten", "Käsefüße", "Knoten ⚡ Blitz", "\U0001f9e1 Orange",
    "日本語のノード", "a-b_c.d",
])
def test_nur_eine_zeile_laesst_echte_namen_durch(alias):
    assert nodeconfig.nur_eine_zeile(alias) == alias


def test_nur_eine_zeile_lehnt_andere_unsichtbare_zeichen_ab():
    for z in ("​", "‮", " ", "\x7f", "\t", "\x00"):
        with pytest.raises(ValueError):
            nodeconfig.nur_eine_zeile("a" + z + "b")


# ---------------------------------------------------- Ende zu Ende

@pytest.mark.parametrize("trenner", ZEICHEN, ids=KENNUNGEN)
def test_der_alias_schleust_keine_zeile_in_lnd_conf(tmp_path, monkeypatch,
                                                   trenner):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    pfad = _lnd_conf(c, monkeypatch)
    r = c.post("/api/lightning/name",
               json={"alias": "x" + trenner + "no-macaroons=true"})
    assert r.status_code == 400, r.text
    zeilen = [z.strip() for z in _zeilen(pfad.read_text())]
    assert "no-macaroons=true" not in zeilen
    assert not any(z.startswith("no-macaroons") for z in zeilen)


@pytest.mark.parametrize("trenner", ZEICHEN, ids=KENNUNGEN)
def test_die_adresse_schleust_keine_zeile_in_bitcoind_conf(tmp_path,
                                                          monkeypatch,
                                                          trenner):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    _lnd_conf(c, monkeypatch)
    c.post("/api/knoten/netzwege", json={
        **NETZWEGE, "ipv6": True,
        "externe_adresse": "fe80::1%x" + trenner + "startupnotify=true"})
    c.post("/api/knoten/netzwege", json={**NETZWEGE, "ipv6": True})
    bc = (tmp_path / "config" / "bitcoind.conf").read_text()
    assert not any(z.strip().startswith("startupnotify")
                   for z in _zeilen(bc))
    assert "startupnotify" not in bc


def test_kontrolle_leerzeichen_und_umbruch_schleusen_nichts_ein(
        tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    pfad = _lnd_conf(c, monkeypatch)
    for alias in ("x no-macaroons=true", "x\nno-macaroons=true"):
        c.post("/api/lightning/name", json={"alias": alias})
        assert "no-macaroons=true" not in [z.strip() for z in
                                           _zeilen(pfad.read_text())]


def test_kontrolle_ein_normaler_alias_und_eine_normale_adresse_gehen(
        tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    pfad = _lnd_conf(c, monkeypatch)
    r = c.post("/api/lightning/name", json={"alias": "Käse \U0001f9e1"})
    assert r.status_code == 200, r.text
    assert "alias=Käse \U0001f9e1" in _zeilen(pfad.read_text())
    r = c.post("/api/knoten/netzwege", json={**NETZWEGE, "ipv6": True,
                                             "externe_adresse": "2001:db8::7"})
    assert r.status_code == 200, r.text
    bc = (tmp_path / "config" / "bitcoind.conf").read_text()
    assert "externalip=2001:db8::7" in _zeilen(bc)


# ---------------------------------------------------- Adressen

@pytest.mark.parametrize("adresse", [
    "fe80::1%eth0", "fe80::1%x", "fe80::1%x startupnotify=1",
    "2001:db8::1%0", "fe80::1%x startupnotify=1",
])
def test_scope_kennungen_sind_keine_adressen(adresse):
    assert dyndns.ist_ip(adresse) is False
    assert nodeconfig.adressen_fuer_netze([adresse], True, True) == []
    assert "externalip" not in nodeconfig.adressblock([adresse])
    assert "externalip" not in nodeconfig.lnd_adressblock([adresse])
    assert "externalip" not in nodeconfig.wachturm_adressblock([adresse], 9911)


def test_adressen_werden_normalisiert_ausgegeben_nicht_roh():
    assert nodeconfig.adressen_fuer_netze(
        ["2001:0DB8:0:0:0:0:0:0007"], True, True) == ["2001:db8::7"]
    assert "externalip=2001:db8::7" in _zeilen(
        nodeconfig.adressblock(["2001:0DB8:0:0:0:0:0:0007"]))
    assert "externalip=2001:db8::7" in _zeilen(
        nodeconfig.lnd_adressblock(["2001:0DB8::7"]))


@pytest.mark.parametrize("adresse,soll", [
    ("203.0.113.7", "203.0.113.7"),
    ("203.0.113.7:9735", "203.0.113.7:9735"),
    ("2001:db8::7", "2001:db8::7"),
    ("[2001:db8::7]:9735", "[2001:db8::7]:9735"),
    ("node.example.org", "node.example.org"),
    ("node.example.org:9735", "node.example.org:9735"),
    ("mein_knoten.example.org", "mein_knoten.example.org"),
    ("192.168.1.20:9735", "192.168.1.20:9735"),
])
def test_kontrolle_gueltige_adressen_bleiben(adresse, soll):
    assert nodeconfig.normiere_adresse(adresse) == soll


@pytest.mark.parametrize("adresse", [
    "", "fe80::1%x", "203.0.113.7:99999", "[2001:db8::7]%x:9735",
    "-bad.example", "a b.example", "a..b",
    "203.0.113.7;x", "x=1", "203.0.113.7 x",
])
def test_normiere_adresse_lehnt_ab(adresse):
    with pytest.raises(ValueError):
        nodeconfig.normiere_adresse(adresse)


# ---------------------------------------------------- Lese-Aendern-Schreiben

@pytest.mark.parametrize("trenner", ZEICHEN, ids=KENNUNGEN)
@pytest.mark.parametrize("name,aendere", [
    ("dbcache", lambda c: nodeconfig.setze_dbcache(c, 1000)),
    ("netze", lambda c: nodeconfig.setze_netze(c, ("ipv4", "onion"), "")),
    ("adressen", lambda c: nodeconfig.setze_adressen(c, ["203.0.113.7"])),
    ("tor", lambda c: nodeconfig.setze_tor(c, True, "")),
    ("indizes", lambda c: nodeconfig.setze_indizes(c, True)),
])
def test_die_helfer_machen_aus_einem_trennzeichen_keine_zeile(
        name, aendere, trenner):
    conf = "dbcache=450\nfremd=a" + trenner + "startupnotify=1\n"
    neu = aendere(conf)
    assert "fremd=a" + trenner + "startupnotify=1" in _zeilen(neu)
    assert "startupnotify=1" not in _zeilen(neu)


# ---------------------------------------------------- letzte Sperre

@pytest.mark.parametrize("trenner", ZEICHEN, ids=KENNUNGEN)
def test_die_ablage_schreibt_keinen_inhalt_mit_fremdem_trenner(
        tmp_path, trenner, caplog):
    ablage = Konfigurationsablage(str(tmp_path / "config"))
    geheim = "GEHEIMNUTZLAST" + trenner + "startupnotify=1"
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError):
            ablage.schreibe("bitcoind", "dbcache=1\n" + geheim + "\n")
    assert ablage.lies("bitcoind") is None
    assert not list((tmp_path / "config").glob("*.tmp"))
    assert "GEHEIMNUTZLAST" not in caplog.text


def test_die_ablage_schreibt_normalen_inhalt(tmp_path):
    ablage = Konfigurationsablage(str(tmp_path / "config"))
    ablage.schreibe("bitcoind", "dbcache=1\n\n# Käse ⚡\nalias=a b\n")
    assert ablage.lies("bitcoind").startswith("dbcache=1")


def test_die_ablage_lehnt_auch_wagenruecklauf_ab(tmp_path):
    ablage = Konfigurationsablage(str(tmp_path / "config"))
    with pytest.raises(ValueError):
        ablage.schreibe("bitcoind", "a=1\r\nb=2\r\n")
    assert ablage.lies("bitcoind") is None


# ---------------------------------------------------- rpcallowip

@pytest.mark.parametrize("netz", [
    "::ffff:0.0.0.0/96", "::ffff:192.168.1.0/120", "::1/128", "0.0.0.0/8",
    "240.0.0.0/4", "192.0.2.0/24", "fe80::/10", "0.0.0.0/0", "::/0",
    "127.0.0.0/8", "169.254.0.0/16", "100.64.0.0/10", "172.0.0.0/8",
    "10.0.0.0/7", "192.168.0.0/15", "fc00::/6", "198.51.100.0/24",
])
def test_rpcallowip_lehnt_alles_ausser_heimnetzen_ab(netz):
    with pytest.raises(ValueError):
        api._heimnetz_pruefen(netz)


@pytest.mark.parametrize("netz,soll", [
    ("192.168.1.0/24", "192.168.1.0/24"), ("192.168.0.0/16", "192.168.0.0/16"),
    ("10.0.0.0/8", "10.0.0.0/8"), ("172.16.0.0/12", "172.16.0.0/12"),
    ("172.20.0.0/16", "172.20.0.0/16"), ("192.168.2.0/24", "192.168.2.0/24"),
    ("192.168.1.7", "192.168.1.7/32"), ("fc00::/7", "fc00::/7"),
    ("fd12:3456::/32", "fd12:3456::/32"), ("", ""),
])
def test_kontrolle_rpcallowip_laesst_heimnetze_durch(netz, soll):
    assert api._heimnetz_pruefen(netz) == soll


def test_rpcallowip_gemappt_wird_ueber_die_route_abgelehnt(tmp_path,
                                                          monkeypatch):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    _lnd_conf(c, monkeypatch)
    r = c.post("/api/knoten/netzwege",
               json={**NETZWEGE, "rpc_heimnetz": "::ffff:0.0.0.0/96"})
    assert r.status_code == 422


# ---------------------------------------------------- Kontrollen: es geht wie vorher

@pytest.mark.parametrize("name", [
    "meinknoten.dyndns.example", "mein-knoten.example.org",
    "mein_knoten.example.org", "knoten.example.org.", "k\u00e4se.example.org",
])
def test_kontrolle_dyndns_namen_werden_weiter_aufgeloest(name):
    gefragt = []

    def aufloeser(n):
        gefragt.append(n)
        return ["203.0.113.9"]
    assert dyndns.loese_auf([name], aufloeser=aufloeser) == ["203.0.113.9"]
    assert gefragt == [name]


def test_kontrolle_dyndns_ips_gehen_unveraendert_durch():
    assert dyndns.loese_auf(["203.0.113.7", "2001:db8::7"],
                            aufloeser=lambda n: []) == [
        "203.0.113.7", "2001:db8::7"]


@pytest.mark.parametrize("wert", ["2001:db8::7", "203.0.113.7"])
def test_kontrolle_ip_ohne_scope_ist_weiter_eine_ip(wert):
    assert dyndns.ist_ip(wert)


def test_kontrolle_lightning_adressen_mit_und_ohne_port():
    block = _zeilen(nodeconfig.lnd_adressblock(
        ["203.0.113.7", "203.0.113.8:9736", "[2001:db8::7]:9735",
         "knoten.example.org"]))
    for z in ("externalip=203.0.113.7", "externalip=203.0.113.8:9736",
              "externalip=[2001:db8::7]:9735",
              "externalip=knoten.example.org"):
        assert z in block


def test_kontrolle_rpc_heimnetz_ueber_die_route(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path)
    _lnd_conf(c, monkeypatch)
    r = c.post("/api/knoten/netzwege",
               json={**NETZWEGE, "rpc_heimnetz": "192.168.1.0/24"})
    assert r.status_code == 200, r.text
