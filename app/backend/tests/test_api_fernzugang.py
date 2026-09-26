"""Externe Wallets ueber die Schnittstelle: Geraete anlegen und widerrufen.

Aus dem Betrieb, 26.09.2026: Zeus soll den Knoten vom Telefon aus bedienen,
ueber Tor oder VPN, mit Rechten, die hier eingestellt werden. Ein Schluessel
mit der Stufe "voll" ist so viel wert wie das Guthaben -- deshalb gilt fuer
das Ausstellen dasselbe wie fuer jeden Geldweg: die PIN zuerst.

Alle Werte ausgedacht.
"""
import base64
import hashlib

import pytest

from satcortex import fernzugang, settings
from tests.test_api import (PIN, FakeLnd, _client, _freigabe_ein, _platz,
                            _richte_ein)

ERSTE = fernzugang.ERSTE_KENNUNG


def _onion(fuellung=b"\x11"):
    """Eine gueltige v3-Adresse aus einem ausgedachten Schluessel."""
    schluessel = fuellung * 32
    pruef = hashlib.sha3_256(b".onion checksum" + schluessel
                             + b"\x03").digest()[:2]
    return (base64.b32encode(schluessel + pruef + b"\x03").decode().lower()
            + ".onion")


ONION = _onion()


class LndMitGeraeten(FakeLnd):
    """LND mit Schluesselverwaltung: backen, auflisten, loeschen."""

    def __init__(self):
        super().__init__(stand="SERVER_ACTIVE")
        self.wurzeln = [0]
        self.gebacken = []
        self.geloescht = []
        self.unerreichbar = False

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None,
            methode=None):
        if pfad.startswith("/v1/macaroon"):
            from satcortex import lnd as lnd_modul
            if self.unerreichbar:
                raise lnd_modul.NichtErreichbar("LND schlaeft")
            assert macaroon == "admin", "Schluessel gibt es nur mit admin"
            if pfad == "/v1/macaroon/ids":
                return {"root_key_ids": [str(w) for w in self.wurzeln]}
            if pfad == "/v1/macaroon" and daten is not None:
                self.gebacken.append(daten)
                self.wurzeln.append(int(daten["root_key_id"]))
                return {"macaroon": "0201036c6e64" + "cd" * 20}
            if methode == "DELETE":
                kennung = int(pfad.rsplit("/", 1)[1])
                self.geloescht.append(kennung)
                da = kennung in self.wurzeln
                self.wurzeln = [w for w in self.wurzeln if w != kennung]
                return {"deleted": da}
        return super().ruf(pfad, macaroon, daten, zeitlimit, methode)


@pytest.fixture
def lnd_geraete(monkeypatch):
    from satcortex import api as api_modul
    knoten = LndMitGeraeten()
    monkeypatch.setattr(api_modul.lnd, "Knoten", lambda **kw: knoten)
    return knoten


@pytest.fixture
def tor_da(monkeypatch):
    """Tor legt die Adresse sofort an -- ohne echtes Tor."""
    from satcortex import api as api_modul
    from satcortex import onion
    monkeypatch.setattr(api_modul, "FZ_ONION_FRIST_SEKUNDEN", 0.2)
    original = onion.abwarten

    def abwarten(fast, namen, frist, **kw):
        if "fernzugang" in namen:
            ordner = onion.verzeichnis(fast, "fernzugang")
            ordner.mkdir(parents=True, exist_ok=True)
            (ordner / "hostname").write_text(ONION + "\n")
        return original(fast, namen, frist, **kw)
    monkeypatch.setattr(api_modul.onion, "abwarten", abwarten)


@pytest.fixture
def client(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    return _client(tmp_path)


@pytest.fixture
def client_vpn(tmp_path, monkeypatch):
    """Eine Compose, die LNDs Schnittstelle im Heimnetz freigibt."""
    _platz(monkeypatch, 4000)
    konf = settings.Einstellungen(
        bulk=str(tmp_path / "bulk"), fast=str(tmp_path / "fast"),
        config_dir=str(tmp_path / "config"),
        lnd_lan_bind="0.0.0.0", lnd_lan_port="8080")
    return _client(tmp_path, konf=konf)


def _neu(client, **abweichungen):
    wunsch = {"name": "Telefon", "stufe": "voll", "weg": "tor",
              "host": "", "pin": PIN}
    wunsch.update(abweichungen)
    return client.post("/api/fernzugang/geraet", json=wunsch)


def _torrc(client):
    return (client.tmp / "config" / "tor.conf").read_text()


# ── Die Uebersicht ──────────────────────────────────────────────────────────

def test_die_uebersicht_nennt_wege_stufen_und_geraete(client, lnd_geraete):
    _richte_ein(client)
    d = client.get("/api/fernzugang").json()
    assert d["stufen"] == ["ansehen", "empfangen", "lightning", "voll"]
    assert d["geraete"] == []
    assert d["lightning"] == "bereit"
    assert d["tor"]["moeglich"] is True
    assert d["tor"]["aktiv"] is False
    # Ohne die Variablen reicht die Compose nichts durch -- sie ist aelter.
    assert d["vpn"] == {"stand": "compose_alt", "port": None}


def test_die_uebersicht_kennt_eine_freigegebene_compose(client_vpn,
                                                        lnd_geraete):
    _richte_ein(client_vpn)
    assert client_vpn.get("/api/fernzugang").json()["vpn"] == {
        "stand": "bereit", "port": 8080}


# ── Die PIN zuerst ──────────────────────────────────────────────────────────

def test_ohne_pin_wird_kein_schluessel_gebacken(client, lnd_geraete, tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, pin="")
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"
    assert lnd_geraete.gebacken == []
    assert client.get("/api/fernzugang").json()["geraete"] == []


def test_die_falsche_pin_backt_nichts(client, lnd_geraete, tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, pin="000000")
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "pin_falsch"
    assert lnd_geraete.gebacken == []


def test_die_pin_kommt_vor_jeder_anderen_pruefung(client, lnd_geraete):
    """Wer ohne PIN eine unsinnige Stufe schickt, erfaehrt nichts ueber die
    Stufe -- nur, dass die PIN fehlt."""
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, pin="", stufe="admin", weg="irgendwo", name="")
    assert a.status_code == 403
    assert a.json()["detail"]["meldung"] == "pin_noetig"


# ── Ueber Tor ───────────────────────────────────────────────────────────────

def test_ein_geraet_ueber_tor(client, lnd_geraete, tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, stufe="lightning")
    assert a.status_code == 200, a.text
    d = a.json()

    assert d["verbindung"].startswith(f"lndconnect://{ONION}:8080?macaroon=")
    [gebacken] = lnd_geraete.gebacken
    assert int(gebacken["root_key_id"]) >= ERSTE
    assert [(p["entity"], p["action"]) for p in gebacken["permissions"]] == \
        list(fernzugang.rechte("lightning"))

    [geraet] = client.get("/api/fernzugang").json()["geraete"]
    assert geraet["name"] == "Telefon"
    assert geraet["stufe"] == "lightning"
    assert geraet["weg"] == "tor"
    assert geraet["kennung"] == int(gebacken["root_key_id"])
    # Und die Onion fuer den Zugang steht jetzt in der torrc.
    assert "HiddenServiceDir /fast/tor/onion-fernzugang" in _torrc(client)
    assert client.get("/api/fernzugang").json()["tor"]["adresse"] == ONION


def test_der_schluessel_wird_nirgends_aufgehoben(client, lnd_geraete, tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    _neu(client)
    for datei in (client.tmp / "config").rglob("*"):
        if datei.is_file():
            assert "cd" * 20 not in datei.read_text(errors="ignore"), datei


def test_ohne_onion_adresse_wird_nichts_gebacken(client, lnd_geraete,
                                                 monkeypatch):
    """Tor braucht nach dem Neustart einen Moment. Kommt die Adresse nicht
    rechtzeitig, gibt es keinen Schluessel ohne Weg -- ein zweiter Versuch
    findet sie dann."""
    from satcortex import api as api_modul
    monkeypatch.setattr(api_modul, "FZ_ONION_FRIST_SEKUNDEN", 0.1)
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client)
    assert a.status_code == 503
    assert a.json()["detail"]["meldung"] == "fz_onion_fehlt"
    assert lnd_geraete.gebacken == []


def test_ohne_tor_gibt_es_den_tor_weg_nicht(client, lnd_geraete):
    _richte_ein(client, tor_aktiv=False)
    _freigabe_ein(client)
    assert client.get("/api/fernzugang").json()["tor"]["moeglich"] is False
    a = _neu(client)
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "fz_tor_aus"


# ── Ueber VPN ───────────────────────────────────────────────────────────────

def test_ohne_freigabe_in_der_compose_gibt_es_den_vpn_weg_nicht(client,
                                                               lnd_geraete):
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, weg="vpn", host="192.168.1.10")
    assert a.status_code == 409
    assert a.json()["detail"] == {"meldung": "fz_vpn_nicht_frei",
                                  "stand": "compose_alt"}
    assert lnd_geraete.gebacken == []


def test_ein_geraet_ueber_vpn(client_vpn, lnd_geraete):
    _richte_ein(client_vpn)
    _freigabe_ein(client_vpn)
    a = _neu(client_vpn, weg="vpn", host=" 192.168.1.10 ", stufe="ansehen")
    assert a.status_code == 200, a.text
    assert a.json()["verbindung"].startswith(
        "lndconnect://192.168.1.10:8080?macaroon=")
    # Der VPN-Weg braucht keinen Onion-Dienst.
    assert "onion-fernzugang" not in _torrc(client_vpn)


def test_eine_unbrauchbare_adresse_wird_abgewiesen(client_vpn, lnd_geraete):
    _richte_ein(client_vpn)
    _freigabe_ein(client_vpn)
    a = _neu(client_vpn, weg="vpn", host="http://192.168.1.10:8080")
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == "fz_host_ungueltig"
    assert lnd_geraete.gebacken == []


# ── Was sonst abgewiesen wird ───────────────────────────────────────────────

@pytest.mark.parametrize("feld,wert,meldung", [
    ("stufe", "admin", "fz_stufe_unbekannt"),
    ("weg", "lnc", "fz_weg_unbekannt"),
    ("name", "   ", "fz_name_ungueltig"),
])
def test_unsinn_wird_nach_der_pin_abgewiesen(client, lnd_geraete, tor_da,
                                            feld, wert, meldung):
    _richte_ein(client)
    _freigabe_ein(client)
    a = _neu(client, **{feld: wert})
    assert a.status_code == 400
    assert a.json()["detail"]["meldung"] == meldung
    assert lnd_geraete.gebacken == []


def test_ohne_bereites_lightning_gibt_es_keinen_schluessel(client,
                                                           lnd_geraete,
                                                           tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    lnd_geraete.stand = "LOCKED"
    a = _neu(client)
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "lightning_nicht_bereit"


def test_die_zahl_der_geraete_ist_begrenzt(client, lnd_geraete, tor_da,
                                           monkeypatch):
    monkeypatch.setattr(fernzugang, "HOECHSTENS_GERAETE", 2)
    _richte_ein(client)
    _freigabe_ein(client)
    assert _neu(client, name="Eins").status_code == 200
    assert _neu(client, name="Zwei").status_code == 200
    a = _neu(client, name="Drei")
    assert a.status_code == 409
    assert a.json()["detail"]["meldung"] == "fz_zu_viele"


def test_die_kennung_liegt_ueber_dem_was_lnd_schon_kennt(client, lnd_geraete,
                                                        tor_da):
    """Wer mit lncli selbst Schluessel gebacken hat, dessen Wurzeln bleiben
    unberuehrt."""
    lnd_geraete.wurzeln = [0, ERSTE + 5]
    _richte_ein(client)
    _freigabe_ein(client)
    _neu(client)
    assert int(lnd_geraete.gebacken[0]["root_key_id"]) == ERSTE + 6


# ── Widerrufen ──────────────────────────────────────────────────────────────

def _widerrufe(client, kennung, pin=PIN):
    return client.post(f"/api/fernzugang/geraet/{kennung}/widerrufen",
                       json={"pin": pin})


def test_widerrufen_verlangt_die_pin(client, lnd_geraete, tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    kennung = _neu(client).json()["geraet"]["kennung"]
    a = _widerrufe(client, kennung, pin="")
    assert a.status_code == 403
    assert lnd_geraete.geloescht == []


def test_widerrufen_loescht_die_wurzel_und_den_eintrag(client, lnd_geraete,
                                                      tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    kennung = _neu(client).json()["geraet"]["kennung"]

    a = _widerrufe(client, kennung)
    assert a.status_code == 200, a.text
    assert lnd_geraete.geloescht == [kennung]
    assert client.get("/api/fernzugang").json()["geraete"] == []
    # Das letzte Tor-Geraet ist weg -- und mit ihm der Onion-Dienst.
    assert "onion-fernzugang" not in _torrc(client)


def test_ein_verbleibendes_tor_geraet_behaelt_den_dienst(client, lnd_geraete,
                                                        tor_da):
    _richte_ein(client)
    _freigabe_ein(client)
    erstes = _neu(client, name="Eins").json()["geraet"]["kennung"]
    _neu(client, name="Zwei")
    _widerrufe(client, erstes)
    assert "onion-fernzugang" in _torrc(client)
    assert [g["name"] for g in
            client.get("/api/fernzugang").json()["geraete"]] == ["Zwei"]


def test_ein_unbekanntes_geraet_wird_nicht_widerrufen(client, lnd_geraete):
    """Und schon gar nicht Kennung 0 -- an der haengt die Anwendung selbst."""
    _richte_ein(client)
    _freigabe_ein(client)
    for kennung in (0, ERSTE + 99):
        a = _widerrufe(client, kennung)
        assert a.status_code == 404
    assert lnd_geraete.geloescht == []


def test_schlaeft_lnd_bleibt_das_geraet_in_der_liste(client, lnd_geraete,
                                                    tor_da):
    """Ein Eintrag, der verschwindet, obwohl der Schluessel noch gilt, waere
    die gefaehrlichste Luege in dieser Ansicht."""
    _richte_ein(client)
    _freigabe_ein(client)
    kennung = _neu(client).json()["geraet"]["kennung"]
    lnd_geraete.unerreichbar = True
    a = _widerrufe(client, kennung)
    assert a.status_code == 503
    assert len(client.get("/api/fernzugang").json()["geraete"]) == 1


# ── Sparrow: der schmale Weg ────────────────────────────────────────────────
#
# Die Freigabe fuer Wallet-Software zog am 26.09.2026 in den Reiter
# "Externe Wallets". Bis dahin schickte ihr Speichern ALLE Netzwege mit --
# aus Feldern einer anderen Ansicht. Wer sie nie geoeffnet hatte, haette so
# die Vorgaben festgeschrieben. Jetzt aendert der Weg genau eine Angabe.

def test_die_freigabe_aendert_nur_das_heimnetz(client):
    _richte_ein(client)
    client.post("/api/knoten/netzwege", json={
        "tor": True, "ipv4": False, "ipv6": True, "externe_adresse": "",
        "adresse_ankuendigen": False, "tor_pause_beim_abgleich": True,
        "sichtbarkeit": "still", "rpc_heimnetz": ""})
    vorher = client.get("/api/knoten/netzwege").json()

    a = client.post("/api/knoten/rpc-freigabe",
                    json={"rpc_heimnetz": "192.168.1.0/24"})
    assert a.status_code == 200, a.text

    nachher = client.get("/api/knoten/netzwege").json()
    assert nachher["rpc_heimnetz"] == "192.168.1.0/24"
    for feld in ("tor", "ipv4", "ipv6", "sichtbarkeit", "adresse_ankuendigen"):
        assert nachher[feld] == vorher[feld], feld


def test_eine_unsinnige_freigabe_wird_abgewiesen(client):
    _richte_ein(client)
    a = client.post("/api/knoten/rpc-freigabe",
                    json={"rpc_heimnetz": "0.0.0.0/0"})
    assert a.status_code == 422


def test_zwei_gleichzeitige_anfragen_bekommen_verschiedene_wurzeln(
        client_vpn, lnd_geraete, monkeypatch):
    """Ohne Sperre zoegen beide dieselbe naechste Kennung -- und ein
    Widerruf traefe dann zwei Geraete zugleich."""
    import threading
    import time as zeit
    _richte_ein(client_vpn)
    # OHNE PIN: die PIN-Bremse laesst zwei Pruefungen im selben Augenblick
    # nicht zu (429) -- gewollt, aber hier geht es um die Wurzeln.
    echt = lnd_geraete.ruf

    def langsam(pfad, *a, **kw):
        antwort = echt(pfad, *a, **kw)
        if pfad == "/v1/macaroon/ids":
            zeit.sleep(0.3)        # der zweite holt sich die Liste inzwischen
        return antwort
    monkeypatch.setattr(lnd_geraete, "ruf", langsam)

    antworten = []
    faeden = [threading.Thread(target=lambda n=n: antworten.append(
        _neu(client_vpn, name=f"Geraet {n}", weg="vpn", host="10.0.0.5")))
        for n in range(2)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    assert [a.status_code for a in antworten] == [200, 200]
    wurzeln = [int(g["root_key_id"]) for g in lnd_geraete.gebacken]
    assert len(set(wurzeln)) == 2, wurzeln
