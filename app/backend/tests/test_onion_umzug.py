"""Vom Zustand 0.62.0 in den heutigen -- ohne dass jemand etwas anfasst.

Der Anlass, 17.09.2026: die Onion-Dienste von bitcoind, LND und Wachturm
zeigten ins Leere (onion.py, netz.py). Wer 0.63.0 einspielt, hat auf der
Platte noch den alten Stand: torrc mit Steuerport, bitcoind mit listenonion
auf 1, LND mit tor.v3, rpcallowip fuer 172.16.0.0/12 -- und die Schluessel
der .onion bei den Diensten.

Was hier geprueft wird, ist der eine Durchgang des Waechters, der daraus den
neuen Stand macht. Und zwar so, dass die ADRESSEN bleiben, dass jeder Dienst
nur EINMAL neu startet, und dass ein zweiter Durchgang nichts mehr anfasst.
"""
import base64
from collections import namedtuple
import shutil

import pytest
from fastapi.testclient import TestClient

from satcortex import api, netz, nodeconfig, onion, settings

Nutzung = namedtuple("Nutzung", "total used free")
ZUGANG = {"benutzer": "pruefer", "passwort": "ein-gutes-langes-passwort"}

# Echte v3-Adressen mit stimmender Pruefsumme (DuckDuckGo, Tor Project,
# und eine dritte, hier berechnet -- onion.ist_gueltig prueft sie).
ADRESSE = {
    "bitcoind": "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion",
    "lnd": "2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion",
}


def _dritte_adresse():
    import hashlib
    schluessel = bytes(range(32))
    pruef = hashlib.sha3_256(b".onion checksum" + schluessel + b"\x03").digest()[:2]
    return base64.b32encode(schluessel + pruef + b"\x03").decode().lower() + ".onion"


ADRESSE["wachturm"] = _dritte_adresse()
ALTE_SCHLUESSEL = {n: bytes([i + 1]) * 64 for i, n in enumerate(onion.REIHENFOLGE)}

ALTE_TORRC = """SocksPort 0.0.0.0:9050
ControlPort 0.0.0.0:9051
HTTPTunnelPort 0.0.0.0:9080
CookieAuthentication 1
CookieAuthFile /fast/tor/control_auth_cookie
CookieAuthFileGroupReadable 1
DataDirectory /fast/tor
"""

ALTER_TORBLOCK = """# Tor: der Knoten ist zusaetzlich als Onion-Dienst erreichbar. Tor-Knoten
# brauchen Gegenstellen, die beide Welten sprechen -- diese Bruecke ist knapp.
onion=tor:9050
torcontrol=tor:9051
listenonion=1"""


@pytest.fixture
def knoten(tmp_path, monkeypatch):
    """Ein eingerichteter Knoten mit fertiger Kette und Lightning -- und eine
    Attrappe fuer Tor, die tut, was Tor beim Start tut: die Adressen der
    Dienste hinterlegen, die in seiner torrc stehen."""
    from satcortex import dyndns as dyndns_modul, rpc as rpc_modul
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _p: Nutzung(8000 * 1024 ** 3, 1, 4000 * 1024 ** 3))
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda namen: list(namen))
    monkeypatch.setattr(rpc_modul, "kettenlage", lambda _k, *_a: {
        "kette": "main", "hoehe": 966_370, "kopfzeilen": 966_370,
        "fortschritt": 1.0, "im_erstsync": False, "belegt_bytes": 1,
        "verbindungen_ein": 3, "verbindungen_aus": 8, "erreichbar": True,
        "blockzeit": 1_800_000_000, "adressen": [], "netze": {},
        "empfangen_bytes": 0, "gesendet_bytes": 0})

    fast = tmp_path / "fast"
    (tmp_path / "bulk").mkdir()
    fast.mkdir()
    konf = settings.Einstellungen(bulk=str(tmp_path / "bulk"), fast=str(fast),
                                  config_dir=str(tmp_path / "config"))
    tor = {"laeuft": True}

    def tor_startet():
        """Was Tor beim Start tut: fuer jeden Dienst in seiner torrc die
        Adresse hinterlegen -- unabhaengig davon, ob jemand wartet."""
        pfad = tmp_path / "config" / "tor.conf"
        conf = pfad.read_text() if pfad.exists() else ""
        for name in onion.REIHENFOLGE:
            if f"/fast/tor/{onion.DIENSTE[name].verzeichnis}" in conf:
                ordner = onion.verzeichnis(str(fast), name)
                ordner.mkdir(parents=True, exist_ok=True)
                (ordner / "hostname").write_text(ADRESSE[name] + "\n")

    def abwarten(fast_pfad, namen, frist, **_kw):
        if tor["laeuft"]:
            tor_startet()
        return {n: onion.lies_adresse(fast_pfad, n) for n in namen}

    monkeypatch.setattr(onion, "abwarten", abwarten)

    c = TestClient(api.baue_app(konf))
    c.tmp = tmp_path
    c.tor = tor
    c.tor_startet = tor_startet
    c.post("/api/konto/anlegen", json=ZUGANG)
    c.post("/api/einrichtung/abschliessen", json={
        "speichergrenze_mb": 2500, "upload_gb_pro_monat": 300,
        "verbindungen": 80, "tor_aktiv": True,
        "externe_adresse": "203.0.113.9", "sichtbarkeit": "hybrid"})
    c.app.state.einmal_nachsehen()     # schreibt die lnd.conf
    assert (tmp_path / "config" / "lnd.conf").exists()
    return c


def _datei(knoten, name):
    return knoten.tmp / "config" / f"{name}.conf"


def _auf_0_62_zurueck(knoten):
    """Den Stand herstellen, den ein Knoten vor dem Update auf der Platte hat."""
    fast = knoten.tmp / "fast"
    shutil.rmtree(fast / "tor")
    (fast / "tor").mkdir()
    for name, schluessel in ALTE_SCHLUESSEL.items():
        pfad = fast.joinpath(*onion.DIENSTE[name].alter_schluessel)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"ED25519-V3:" + base64.b64encode(schluessel))

    _datei(knoten, "tor").write_text(ALTE_TORRC)

    btc = _datei(knoten, "bitcoind").read_text()
    btc = nodeconfig.setze_tor(btc, False).replace(nodeconfig.TOR_AUS,
                                                   ALTER_TORBLOCK)
    btc = btc.replace(f"rpcallowip={nodeconfig.RPC_COMPOSE_NETZ}",
                      "rpcallowip=172.16.0.0/12")
    _datei(knoten, "bitcoind").write_text(btc)

    lnd_text = "\n".join(
        z for z in _datei(knoten, "lnd").read_text().splitlines()
        if ".onion" not in z or z.startswith("#"))
    lnd_text = lnd_text.replace("tor.v3=false",
                                "tor.control=tor:9051\ntor.v3=true")
    _datei(knoten, "lnd").write_text(lnd_text + "\n")

    assert nodeconfig.tor_nach_altem_muster(_datei(knoten, "bitcoind").read_text())
    assert nodeconfig.lnd_nach_altem_muster(_datei(knoten, "lnd").read_text())


def _alle(knoten):
    return {n: _datei(knoten, n).read_text() for n in ("tor", "bitcoind", "lnd")}


# ── Der Umzug ───────────────────────────────────────────────────────────────

def test_ein_knoten_von_0_62_zieht_in_einem_durchgang_um(knoten):
    _auf_0_62_zurueck(knoten)
    knoten.app.state.einmal_nachsehen()
    neu = _alle(knoten)

    # Tor: kein Steuerport, die drei Dienste auf die festen Adressen.
    assert not any(z.startswith(("ControlPort", "CookieAuthentication"))
                   for z in nodeconfig.wirksam(neu["tor"]))
    assert "HiddenServicePort 8333 10.83.33.11:8334" in neu["tor"]
    assert "HiddenServicePort 9735 10.83.33.12:9735" in neu["tor"]
    assert "HiddenServicePort 9911 10.83.33.12:9911" in neu["tor"]

    # bitcoind: kommt wieder an die RPC-Schnittstelle, kuendigt die .onion an.
    btc = nodeconfig.wirksam(neu["bitcoind"])
    assert f"rpcallowip={netz.subnetz(netz.PRAEFIX_VORGABE)}" in btc
    assert "rpcallowip=172.16.0.0/12" not in btc
    assert "listenonion=0" in btc and not any(z.startswith("torcontrol") for z in btc)
    assert f"externalip={ADRESSE['bitcoind']}" in btc
    # Die Clearnet-Adresse bleibt, wie sie war.
    assert "externalip=203.0.113.9" in btc

    # LND: legt nichts mehr selbst an, kuendigt beide .onion an.
    ln = nodeconfig.wirksam(neu["lnd"])
    assert "tor.v3=false" in ln and not any(z.startswith("tor.control") for z in ln)
    assert f"externalip={ADRESSE['lnd']}:9735" in ln
    assert f"watchtower.externalip={ADRESSE['wachturm']}:9911" in ln
    assert "externalip=203.0.113.9:9735" in ln


def test_die_alten_schluessel_gehen_an_tor(knoten):
    """Damit die Adressen bleiben: Tor findet den Schluessel vor und legt
    keinen neuen an."""
    _auf_0_62_zurueck(knoten)
    knoten.app.state.einmal_nachsehen()
    for name, schluessel in ALTE_SCHLUESSEL.items():
        datei = onion.verzeichnis(str(knoten.tmp / "fast"), name) \
            / "hs_ed25519_secret_key"
        assert datei.read_bytes() == onion.SCHLUESSELKOPF + schluessel, name


def test_ein_zweiter_durchgang_fasst_nichts_mehr_an(knoten):
    """Jedes Schreiben startet einen Dienst neu -- bei LND ohne
    Auto-Entsperren heisst das: Wallet zu."""
    _auf_0_62_zurueck(knoten)
    knoten.app.state.einmal_nachsehen()
    nach_dem_ersten = _alle(knoten)
    knoten.app.state.einmal_nachsehen()
    knoten.app.state.einmal_nachsehen()
    assert _alle(knoten) == nach_dem_ersten


def test_ohne_rechtzeitige_adressen_wird_trotzdem_umgestellt(knoten):
    """Kommt Tor nicht rechtzeitig hoch, darf LND nicht auf der alten
    Konfiguration sitzen bleiben: die zeigt auf einen Steuerport, den es
    nicht mehr gibt, und beim naechsten Neustart kaeme LND gar nicht hoch.
    Die Adressen kommen dann beim naechsten Durchgang nach."""
    _auf_0_62_zurueck(knoten)
    knoten.tor["laeuft"] = False
    knoten.app.state.einmal_nachsehen()
    assert not nodeconfig.lnd_nach_altem_muster(_datei(knoten, "lnd").read_text())
    assert not nodeconfig.tor_nach_altem_muster(
        _datei(knoten, "bitcoind").read_text())

    knoten.tor["laeuft"] = True
    knoten.tor_startet()               # Tor kommt spaeter doch noch hoch
    knoten.app.state.einmal_nachsehen()
    assert f"externalip={ADRESSE['lnd']}:9735" in _datei(knoten, "lnd").read_text()
    assert f"externalip={ADRESSE['bitcoind']}" in \
        _datei(knoten, "bitcoind").read_text()


# ── Im laufenden Betrieb ────────────────────────────────────────────────────

def test_eine_verschwundene_hostname_datei_nimmt_keine_adresse_weg(knoten):
    """Dieselbe Regel wie beim DNS-Aussetzer: ein Wackler darf keine Adresse
    aus der Ankuendigung nehmen und keinen Dienst neu starten."""
    knoten.app.state.einmal_nachsehen()
    vorher = _alle(knoten)
    assert f"externalip={ADRESSE['lnd']}:9735" in vorher["lnd"]
    for name in onion.REIHENFOLGE:
        (onion.verzeichnis(str(knoten.tmp / "fast"), name) / "hostname").unlink()
    knoten.app.state.einmal_nachsehen()
    assert _alle(knoten) == vorher


def test_die_adressnachfuehrung_laesst_die_onion_stehen(knoten, monkeypatch):
    """Eine Zwangstrennung tauscht die Clearnet-Adresse -- die .onion hat
    damit nichts zu tun."""
    from satcortex import dyndns as dyndns_modul
    knoten.app.state.einmal_nachsehen()
    knoten.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": False,
        "externe_adresse": "meinknoten.example", "adresse_ankuendigen": True,
        "sichtbarkeit": "hybrid"})
    monkeypatch.setattr(dyndns_modul, "loese_auf", lambda _n: ["198.51.100.4"])
    knoten.app.state.einmal_nachsehen()
    btc = _datei(knoten, "bitcoind").read_text().splitlines()
    assert "externalip=198.51.100.4" in btc
    assert f"externalip={ADRESSE['bitcoind']}" in btc


def test_still_bekommt_keine_onion_dienste(knoten):
    """"Weder .onion noch IP" -- bis 0.62.0 legte bitcoind dort trotzdem eine
    an und kuendigte sie an."""
    knoten.app.state.einmal_nachsehen()
    r = knoten.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": True, "ipv6": False, "externe_adresse": "",
        "adresse_ankuendigen": False, "sichtbarkeit": "still"})
    assert r.status_code == 200
    neu = _alle(knoten)
    assert not any(z.startswith("HiddenService")
                   for z in nodeconfig.wirksam(neu["tor"]))
    for name in ("bitcoind", "lnd"):
        assert not any(".onion" in z for z in nodeconfig.wirksam(neu[name])), name


def test_zurueck_auf_tor_bringt_dieselben_adressen(knoten):
    """Die Schluessel bleiben liegen, wenn "still" die Dienste abschaltet.
    Wer zurueckschaltet, ist unter derselben .onion wieder da."""
    knoten.app.state.einmal_nachsehen()
    for sicht in ("still", "tor"):
        knoten.post("/api/knoten/netzwege", json={
            "tor": True, "ipv4": False, "ipv6": False, "externe_adresse": "",
            "adresse_ankuendigen": False, "sichtbarkeit": sicht})
    assert f"externalip={ADRESSE['bitcoind']}" in \
        _datei(knoten, "bitcoind").read_text().splitlines()
    ln = _datei(knoten, "lnd").read_text().splitlines()
    assert f"externalip={ADRESSE['lnd']}:9735" in ln
    # Und bei "nur ueber Tor" ausschliesslich die .onion.
    assert not any(z.startswith("externalip=203.") for z in ln)


def test_tor_aus_sperrt_tor_und_kuendigt_keine_onion_an(knoten):
    knoten.app.state.einmal_nachsehen()
    knoten.post("/api/knoten/netzwege", json={
        "tor": False, "ipv4": True, "ipv6": False,
        "externe_adresse": "203.0.113.9", "adresse_ankuendigen": True,
        "sichtbarkeit": "hybrid"})
    assert not (knoten.tmp / "config" / "tor.ready").exists()
    for name in ("bitcoind", "lnd"):
        assert not any(".onion" in z
                       for z in nodeconfig.wirksam(_datei(knoten, name).read_text()))


def test_der_assistent_schreibt_die_onion_schon_ins_erste_bitcoind_conf(knoten):
    """Tor zuerst, dann bitcoind -- sonst startete bitcoind gleich nach dem
    ersten Start ein zweites Mal, nur um seine .onion zu bekommen."""
    btc = _datei(knoten, "bitcoind").read_text().splitlines()
    assert f"externalip={ADRESSE['bitcoind']}" in btc


# ── Wallet loeschen heisst neue Adressen ─────────────────────────────────────

def test_wallet_loeschen_wirft_die_alten_schluessel_weg(knoten, monkeypatch):
    """Die Oberflaeche verspricht beim Loeschen der Wallet "eine NEUE
    Onion-Adresse". Seit Tor die Schluessel haelt, muss das ausdruecklich
    geschehen -- sonst traete die neue Wallet unter der alten Adresse auf."""
    monkeypatch.setattr(api, "TOR_NEUSTART_PAUSE_SEKUNDEN", 0.0)
    knoten.app.state.einmal_nachsehen()
    fast = str(knoten.tmp / "fast")
    for name in ("lnd", "wachturm"):
        (onion.verzeichnis(fast, name) / "hs_ed25519_secret_key").write_bytes(b"alt")
    btc_schluessel = onion.verzeichnis(fast, "bitcoind") / "hs_ed25519_secret_key"
    btc_schluessel.write_bytes(b"bleibt")
    vorher = dict(ADRESSE)
    neu = {"lnd": _dritte_adresse(), "wachturm": vorher["bitcoind"]}
    monkeypatch.setitem(ADRESSE, "lnd", neu["lnd"])
    monkeypatch.setitem(ADRESSE, "wachturm", neu["wachturm"])

    knoten.app.state.lightning_onions_erneuern()

    for name in ("lnd", "wachturm"):
        assert not (onion.verzeichnis(fast, name) / "hs_ed25519_secret_key").exists()
    assert btc_schluessel.read_bytes() == b"bleibt", "bitcoind hat damit nichts zu tun"
    ln = _datei(knoten, "lnd").read_text().splitlines()
    assert f"externalip={neu['lnd']}:9735" in ln
    assert f"externalip={vorher['lnd']}:9735" not in ln
    assert (knoten.tmp / "config" / "tor.ready").exists(), \
        "ohne Freigabe startet Tor nicht wieder"


def test_kommt_tor_nicht_rechtzeitig_steht_nie_die_alte_adresse_da(
        knoten, monkeypatch):
    """Lieber gar keine Adresse als die alte: die verbaende im Graphen den
    alten Knoten mit dem neuen."""
    monkeypatch.setattr(api, "TOR_NEUSTART_PAUSE_SEKUNDEN", 0.0)
    knoten.app.state.einmal_nachsehen()
    alt = ADRESSE["lnd"]
    assert f"externalip={alt}:9735" in _datei(knoten, "lnd").read_text()
    knoten.tor["laeuft"] = False

    knoten.app.state.lightning_onions_erneuern()

    text = _datei(knoten, "lnd").read_text()
    assert alt not in text
    assert ADRESSE["wachturm"] not in text


# ── Erreichbarkeit: auch Lightning und Wachturm ─────────────────────────────

def test_die_pruefung_misst_auch_lightning_und_den_wachturm(knoten, monkeypatch):
    """Die Luecke, durch die der Befund vom 17.09.2026 nie auffiel: gemessen
    wurde nur bitcoind, und auch das nur mit eingetragener Clearnet-Adresse."""
    from satcortex import erreichbar as modul
    knoten.app.state.einmal_nachsehen()
    knoten.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": False, "ipv6": False, "externe_adresse": "",
        "adresse_ankuendigen": False, "sichtbarkeit": "tor"})
    aufrufe = []
    gesehen = {}

    def pruefe(adressen, port, proxy, **kw):
        aufrufe.append((list(adressen), port, kw.get("handschlag", True)))
        gesehen.update(proxy=proxy, erweitert=kw.get("erweitert"))
        return {"port": port, "erreichbar": True, "geprueft": True,
                "adressen": [{"adresse": a, "port": port, "netz": "onion",
                              "erreichbar": True, "geprueft": True}
                             for a in adressen]}
    monkeypatch.setattr(modul, "pruefe", pruefe)

    d = knoten.post("/api/knoten/erreichbarkeit").json()
    assert ([ADRESSE["lnd"]], 9735, False) in aufrufe
    assert ([ADRESSE["wachturm"]], 9911, False) in aufrufe
    dienste = {a["dienst"] for a in d["adressen"]}
    assert {"lightning", "wachturm"} <= dienste
    assert d["erreichbar"] is True
    # Ueber Tors Messport mit erweiterten Codes -- nur dort ist "dahinter
    # nimmt niemand an" von "der Weg kam nicht zustande" zu unterscheiden.
    assert gesehen["proxy"] == ("tor", 9052) and gesehen["erweitert"] is True
