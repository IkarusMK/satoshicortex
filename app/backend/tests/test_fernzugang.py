"""Externe Wallets: Rechtestufen, Kennungen, Eingaben, Verbindungstext.

Alle Werte ausgedacht. Die Rechte werden gegen LNDs eigene Liste der
gueltigen Entitaeten und Aktionen geprueft (rpcserver.go, v0.21.3-beta:
validEntities, validActions) -- ein Tippfehler dort liesse LND das Backen
ablehnen, und das faende sonst erst jemand am echten Knoten.
"""
import base64

import pytest

from satcortex import fernzugang

# rpcserver.go, v0.21.3-beta. "uri" ist macaroons.PermissionEntityCustomURI.
LND_ENTITAETEN = {"onchain", "offchain", "address", "message", "peers", "info",
                  "invoices", "signer", "macaroon", "uri"}
LND_AKTIONEN = {"read", "write", "generate"}


def _menge(stufe):
    return set(fernzugang.rechte(stufe))


# ── Rechtestufen ────────────────────────────────────────────────────────────

def test_es_gibt_genau_die_vier_stufen_in_dieser_reihenfolge():
    assert fernzugang.STUFEN_REIHENFOLGE == (
        "ansehen", "empfangen", "lightning", "voll")
    assert set(fernzugang.STUFEN) == set(fernzugang.STUFEN_REIHENFOLGE)


@pytest.mark.parametrize("stufe", ["ansehen", "empfangen", "lightning", "voll"])
def test_jedes_recht_kennt_lnd(stufe):
    for entitaet, aktion in fernzugang.rechte(stufe):
        assert entitaet in LND_ENTITAETEN, entitaet
        assert aktion in LND_AKTIONEN, aktion


def test_jede_stufe_enthaelt_die_vorige():
    reihe = fernzugang.STUFEN_REIHENFOLGE
    for kleiner, groesser in zip(reihe, reihe[1:]):
        assert _menge(kleiner) < _menge(groesser), (kleiner, groesser)


def test_ansehen_liest_nur():
    assert {a for _, a in _menge("ansehen")} == {"read"}


def test_empfangen_gibt_kein_geld_aus():
    rechte = _menge("empfangen")
    assert ("invoices", "write") in rechte
    assert ("address", "write") in rechte
    # SendPaymentV2 haengt an offchain:write, SendCoins an onchain:write.
    assert ("offchain", "write") not in rechte
    assert ("onchain", "write") not in rechte


def test_lightning_zahlt_aber_sendet_nicht_on_chain():
    """OpenChannel und CloseChannel verlangen onchain:write UND
    offchain:write (rpcserver.go, v0.21.3-beta). Ohne onchain:write geht
    also weder Senden noch Oeffnen noch Schliessen."""
    rechte = _menge("lightning")
    assert ("offchain", "write") in rechte
    assert ("onchain", "write") not in rechte


def test_voll_kann_alles_ausser_schluessel_ausstellen():
    rechte = _menge("voll")
    for recht in [("onchain", "write"), ("offchain", "write"),
                  ("address", "write"), ("invoices", "write"),
                  ("peers", "write"), ("message", "write"),
                  ("info", "write"), ("signer", "generate")]:
        assert recht in rechte, recht


@pytest.mark.parametrize("stufe", ["ansehen", "empfangen", "lightning", "voll"])
def test_keine_stufe_darf_schluessel_ausstellen_oder_loeschen(stufe):
    """Sonst koennte sich ein gestohlenes Geraet einen Ersatzschluessel
    backen, der seinen Widerruf ueberlebt."""
    assert not [r for r in fernzugang.rechte(stufe) if r[0] == "macaroon"]


def test_eine_unbekannte_stufe_wird_abgewiesen():
    with pytest.raises(ValueError):
        fernzugang.rechte("admin")


# ── Kennungen ───────────────────────────────────────────────────────────────

def test_die_erste_kennung_liegt_weit_weg_von_null():
    """Kennung 0 ist LNDs Standardschluessel: an ihm haengen admin,
    readonly, invoice -- und das eigene Macaroon der Anwendung."""
    assert fernzugang.ERSTE_KENNUNG >= 1000


def test_ohne_vorhandene_kennungen_kommt_die_erste():
    assert fernzugang.naechste_kennung([], []) == fernzugang.ERSTE_KENNUNG


def test_fremde_kleine_kennungen_zaehlen_nicht():
    assert fernzugang.naechste_kennung([0, 1, 7], []) == fernzugang.ERSTE_KENNUNG


def test_die_naechste_liegt_ueber_allem_bekannten():
    erste = fernzugang.ERSTE_KENNUNG
    assert fernzugang.naechste_kennung([0, erste + 4], [erste + 1]) == erste + 5
    assert fernzugang.naechste_kennung([0], [erste + 9]) == erste + 10


# ── Eingaben ────────────────────────────────────────────────────────────────

def test_der_name_wird_beschnitten_und_behalten():
    assert fernzugang.pruefe_name("  Telefon  ") == "Telefon"


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "Tele\nfon", "a\x00b"])
def test_ungueltige_namen_werden_abgewiesen(name):
    with pytest.raises(ValueError):
        fernzugang.pruefe_name(name)


@pytest.mark.parametrize("host,erwartet", [
    ("192.168.1.10", "192.168.1.10"),
    ("  10.0.0.5 ", "10.0.0.5"),
    ("nas.fritz.box", "nas.fritz.box"),
    ("server-1.local", "server-1.local"),
    ("fd00::5", "fd00::5"),
    ("[fd00::5]", "fd00::5"),
])
def test_gueltige_adressen(host, erwartet):
    assert fernzugang.pruefe_host(host) == erwartet


@pytest.mark.parametrize("host", [
    "", "http://192.168.1.10", "192.168.1.10:8080", "nas fritz", "a/b",
    "x" * 254, "-start.example", "nas..box", "1.2.3.4?x=1",
])
def test_ungueltige_adressen(host):
    with pytest.raises(ValueError):
        fernzugang.pruefe_host(host)


# ── Der Verbindungstext ─────────────────────────────────────────────────────

MACAROON_HEX = "0201036c6e6402f801" + "ab" * 40


def _zeus_liest(text):
    """So zerlegt Zeus einen lndconnect-Text (utils/ConnectionFormatUtils.ts,
    processLndConnectUrl): am ersten "?" die Parameter, am "=" Schluessel
    und Wert, der Host bis zum Doppelpunkt, bei IPv6 bis "]:"."""
    rest = text.split("lndconnect://")[1]
    params = dict(teil.split("=") for teil in text.split("?")[1].split("&"))
    if "[" in text:
        host = rest.split("]:")[0] + "]"
        port = rest.split("]:")[1].split("?")[0]
    else:
        host = rest.split(":")[0]
        port = rest.split(":")[1].split("?")[0]
    roh = params["macaroon"]
    macaroon = base64.urlsafe_b64decode(roh + "=" * (-len(roh) % 4)).hex()
    return host, port, macaroon


def test_der_text_folgt_lndconnect():
    text = fernzugang.verbindungstext("192.168.1.10", 8080, MACAROON_HEX)
    assert text.startswith("lndconnect://192.168.1.10:8080?macaroon=")
    # base64url ohne Auffuellung: kein "=", kein "+", kein "/" -- sonst
    # zerlegt Zeus den Text an der falschen Stelle.
    wert = text.split("macaroon=", 1)[1]
    assert not set(wert) & set("=+/")


@pytest.mark.parametrize("host,port", [
    ("192.168.1.10", 8080),
    ("x" * 56 + ".onion", 8080),
    ("nas.fritz.box", 18080),
])
def test_zeus_liest_heraus_was_hineinging(host, port):
    text = fernzugang.verbindungstext(host, port, MACAROON_HEX)
    assert _zeus_liest(text) == (host, str(port), MACAROON_HEX)


def test_ipv6_steht_in_eckigen_klammern():
    text = fernzugang.verbindungstext("fd00::5", 8080, MACAROON_HEX)
    assert text.startswith("lndconnect://[fd00::5]:8080?")
    assert _zeus_liest(text) == ("[fd00::5]", "8080", MACAROON_HEX)


def test_kein_zertifikat_im_text():
    """Zeus liest den Parameter "cert" gar nicht (processLndConnectUrl
    gibt nur host, port, macaroonHex und enableTor zurueck). Er machte den
    QR-Code nur groesser."""
    assert "cert=" not in fernzugang.verbindungstext("10.0.0.5", 8080,
                                                     MACAROON_HEX)


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_ein_unmoeglicher_port_wird_abgewiesen(port):
    with pytest.raises(ValueError):
        fernzugang.verbindungstext("10.0.0.5", port, MACAROON_HEX)


def test_ein_leeres_macaroon_wird_abgewiesen():
    with pytest.raises(ValueError):
        fernzugang.verbindungstext("10.0.0.5", 8080, "")


# ── Ist der VPN-Weg freigeschaltet? ─────────────────────────────────────────
#
# Das entscheidet die .env (LND_REST_BIND, LND_REST_LAN_PORT), nicht die
# Anwendung: ohne Docker-Socket kann sie keinen Port oeffnen. Sie kann nur
# ehrlich sagen, was sie vorfindet.

def test_ohne_die_variablen_ist_die_compose_aelter():
    assert fernzugang.vpn_lage(None, None) == {"stand": "compose_alt",
                                               "port": None}


@pytest.mark.parametrize("bind,port", [
    ("127.0.0.1", "8080"),      # die Vorgabe: nur auf dem Server selbst
    ("::1", "8080"),
    ("localhost", "8080"),
    ("0.0.0.0", ""),            # freigegeben, aber ohne festen Port
    ("0.0.0.0", None),
    ("0.0.0.0", "abc"),
    ("0.0.0.0", "70000"),
])
def test_was_nicht_im_heimnetz_erreichbar_ist_heisst_aus(bind, port):
    assert fernzugang.vpn_lage(bind, port)["stand"] == "aus"


@pytest.mark.parametrize("bind,port,erwartet", [
    ("0.0.0.0", "8080", 8080),
    ("192.168.1.10", "18080", 18080),
    (" 0.0.0.0 ", " 8080 ", 8080),
])
def test_freigegeben_mit_festem_port_ist_bereit(bind, port, erwartet):
    assert fernzugang.vpn_lage(bind, port) == {"stand": "bereit",
                                               "port": erwartet}
