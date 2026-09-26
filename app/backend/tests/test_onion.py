"""Die Onion-Dienste in Tors Hand -- und das feste Netz, auf das sie zeigen.

Der Anlass, 17.09.2026: bis 0.62.0 zeigten alle drei Onion-Dienste des
Knotens auf 127.0.0.1 im Tor-Container, wo nichts horcht. Angekuendigt waren
sie trotzdem. Diese Tests halten fest, was seitdem gilt.
"""
import base64
import os
import stat

import pytest

from satcortex import netz, onion

# Zwei echte, seit Jahren oeffentliche v3-Adressen. Ihre Pruefsumme hat Tor
# selbst berechnet -- ein Vektor, den dieser Code nicht erzeugt hat.
DUCKDUCKGO = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion"
TORPROJECT = "2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion"


# ── Das Netz ────────────────────────────────────────────────────────────────

def test_die_vorgabe_liegt_nicht_in_dockers_eigenen_netzen():
    """Docker vergibt 172.17 bis 172.31 und 192.168 selbst. Ein festes Netz
    dort kollidiert irgendwann mit einem anderen Stapel -- und dann startet
    dieser hier nicht."""
    import ipaddress
    unser = ipaddress.ip_network(netz.subnetz(netz.PRAEFIX_VORGABE))
    for docker in ("172.16.0.0/12", "192.168.0.0/16"):
        assert not unser.overlaps(ipaddress.ip_network(docker))


def test_feste_adressen_liegen_unterhalb_des_freien_bereichs():
    """Ab .128 vergibt Docker an alles, was jemand von Hand anhaengt. Unsere
    Dienste liegen darunter -- sonst koennte ein fremder Container einem von
    ihnen die Adresse wegnehmen."""
    assert all(2 <= teil < 128 for teil in netz.HOSTTEIL.values())
    assert len(set(netz.HOSTTEIL.values())) == len(netz.HOSTTEIL)
    assert netz.adresse("10.83.33", "lnd") == "10.83.33.12"


@pytest.mark.parametrize("falsch", [
    "10.83", "10.83.33.0", "10.83.033", "10.83.256", "8.8.8", "10.83.x",
    "100.64.1", "10.83.33\nrpcallowip=0.0.0.0/0", ""])
def test_ein_falsches_praefix_kommt_nicht_durch(falsch):
    """Der Wert landet in rpcallowip und in Tors Weiterleitungen. Ein
    oeffentliches Netz oder ein angehaengter Zeilenumbruch haette dort nichts
    zu suchen."""
    with pytest.raises(ValueError):
        netz.pruefe_praefix(falsch)


# ── Welche Dienste es gibt ──────────────────────────────────────────────────

def test_nur_tor_und_hybrid_bekommen_onion_dienste():
    assert onion.dienste_fuer(True, "tor") == ("bitcoind", "lnd", "wachturm")
    assert onion.dienste_fuer(True, "hybrid") == ("bitcoind", "lnd", "wachturm")
    # "still" heisst in der Oberflaeche "weder .onion noch IP".
    assert onion.dienste_fuer(True, "still") == ()
    assert onion.dienste_fuer(False, "tor") == ()


def test_die_torrc_zeigt_auf_die_festen_adressen():
    block = onion.torrc_block(("bitcoind", "lnd", "wachturm"), "10.83.33")
    zeilen = block.splitlines()
    assert "HiddenServiceDir /fast/tor/onion-bitcoind" in zeilen
    # 8334: dort nimmt Core an, was aus dem Onion-Netz kommt.
    assert "HiddenServicePort 8333 10.83.33.11:8334" in zeilen
    assert "HiddenServicePort 9735 10.83.33.12:9735" in zeilen
    assert "HiddenServicePort 9911 10.83.33.12:9911" in zeilen
    # Der Fehler von 0.62.0 in seiner Form: ein Ziel ohne Adresse.
    for zeile in zeilen:
        if zeile.startswith("HiddenServicePort"):
            assert len(zeile.split()) == 3 and ":" in zeile.split()[2], zeile
            assert "127.0.0.1" not in zeile and "localhost" not in zeile


def test_der_wachturm_hat_ein_eigenes_verzeichnis():
    """Eine eigene Adresse, wie LND sie selbst hielt: ueber den Turm soll
    niemand auf den Knoten schliessen koennen."""
    verzeichnisse = {d.verzeichnis for d in onion.DIENSTE.values()}
    assert len(verzeichnisse) == len(onion.DIENSTE)


def test_dieselbe_wahl_ergibt_dieselbe_torrc():
    """Sonst saehe der Waechter bei jedem Durchgang eine Aenderung und
    startete Tor ohne Anlass neu."""
    assert onion.torrc_block(("wachturm", "bitcoind", "lnd"), "10.83.33") \
        == onion.torrc_block(("lnd", "bitcoind", "wachturm"), "10.83.33")


def test_ohne_dienste_steht_keine_weiterleitung_drin():
    block = onion.torrc_block((), "10.83.33")
    assert "HiddenService" not in block.replace("# ", "")
    assert all(z.startswith("#") for z in block.splitlines())


# ── Adressen lesen ──────────────────────────────────────────────────────────

def test_echte_adressen_bestehen_die_pruefsumme():
    assert onion.ist_gueltig(DUCKDUCKGO)
    assert onion.ist_gueltig(TORPROJECT)


def test_ein_vertipptes_zeichen_faellt_auf():
    kaputt = ("e" if DUCKDUCKGO[0] != "e" else "f") + DUCKDUCKGO[1:]
    assert not onion.ist_gueltig(kaputt)


@pytest.mark.parametrize("falsch", [
    "", "abc.onion", DUCKDUCKGO.upper(), DUCKDUCKGO + "\n",
    DUCKDUCKGO + "\nexternalip=1.2.3.4", DUCKDUCKGO.replace(".onion", ".exit")])
def test_nur_genau_eine_adresse_zaehlt(falsch):
    assert not onion.ist_gueltig(falsch)


def _hostname(fast, name, inhalt):
    ziel = onion.verzeichnis(str(fast), name)
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "hostname").write_text(inhalt, encoding="ascii")


def test_die_adresse_kommt_aus_tors_datei(tmp_path):
    _hostname(tmp_path, "lnd", DUCKDUCKGO + "\n")
    assert onion.lies_adresse(str(tmp_path), "lnd") == DUCKDUCKGO
    assert onion.lies_adresse(str(tmp_path), "bitcoind") == ""


def test_eine_untergeschobene_zeile_landet_nicht_in_der_konfiguration(tmp_path):
    _hostname(tmp_path, "lnd", DUCKDUCKGO + "\ntor.control=tor:9051\n")
    assert onion.lies_adresse(str(tmp_path), "lnd") == ""


def test_abwarten_gibt_auf_statt_zu_haengen(tmp_path):
    uhr = iter(range(0, 1000, 1))
    gefunden = onion.abwarten(str(tmp_path), ("lnd",), frist=3,
                              schlaf=lambda _s: None, uhr=lambda: next(uhr))
    assert gefunden == {"lnd": ""}


def test_abwarten_kehrt_zurueck_sobald_alles_da_ist(tmp_path):
    _hostname(tmp_path, "lnd", DUCKDUCKGO)
    _hostname(tmp_path, "wachturm", TORPROJECT)
    gefunden = onion.abwarten(str(tmp_path), ("lnd", "wachturm"), frist=0,
                              schlaf=lambda _s: pytest.fail("gewartet"))
    assert gefunden == {"lnd": DUCKDUCKGO, "wachturm": TORPROJECT}


def test_ist_onion_mit_und_ohne_port():
    assert onion.ist_onion(DUCKDUCKGO)
    assert onion.ist_onion(DUCKDUCKGO + ":9735")
    assert not onion.ist_onion("203.0.113.7:9735")
    assert not onion.ist_onion("[2001:db8::1]:9735")
    assert not onion.ist_onion("onion.example")


# ── Die Adresse bleibt: Schluessel von 0.62.0 uebernehmen ──────────────────

SCHLUESSEL = bytes(range(64))


def _alt(fast, name, inhalt):
    pfad = fast.joinpath(*onion.DIENSTE[name].alter_schluessel)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    return pfad


def _altformat(schluessel=SCHLUESSEL):
    return b"ED25519-V3:" + base64.b64encode(schluessel)


def test_der_schluessel_wandert_in_tors_format(tmp_path):
    _alt(tmp_path, "bitcoind", _altformat())
    assert onion.uebernimm_schluessel(str(tmp_path), "bitcoind") is True
    datei = onion.verzeichnis(str(tmp_path), "bitcoind") / "hs_ed25519_secret_key"
    inhalt = datei.read_bytes()
    # Kopf Byte fuer Byte wie crypto_write_tagged_contents_to_file.
    assert inhalt[:32] == b"== ed25519v1-secret: type0 ==\x00\x00\x00"
    assert inhalt[32:] == SCHLUESSEL
    assert len(inhalt) == 96


def test_tor_akzeptiert_die_rechte(tmp_path):
    """check_private_dir: 0700 fuer das Verzeichnis. Der Schluessel ist
    ausser fuer den Eigentuemer fuer niemanden lesbar."""
    _alt(tmp_path, "lnd", _altformat())
    onion.uebernimm_schluessel(str(tmp_path), "lnd")
    ordner = onion.verzeichnis(str(tmp_path), "lnd")
    assert stat.S_IMODE(os.stat(ordner).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(ordner / "hs_ed25519_secret_key").st_mode) == 0o600


def test_alle_drei_alten_orte_stimmen(tmp_path):
    """Wo Core und LND ihre Schluessel ablegten -- mit den Pfaden aus der
    Compose (-datadir=/fast/bitcoind, --lnddir=/fast/lnd)."""
    assert onion.DIENSTE["bitcoind"].alter_schluessel == (
        "bitcoind", "onion_v3_private_key")           # torcontrol.cpp
    assert onion.DIENSTE["lnd"].alter_schluessel == (
        "lnd", "v3_onion_private_key")                # config.go: lndDir
    assert onion.DIENSTE["wachturm"].alter_schluessel == (
        "lnd", "data", "watchtower", "v3_onion_private_key")  # TowerDir


def test_padding_darf_fehlen(tmp_path):
    ohne = _altformat().rstrip(b"=")
    _alt(tmp_path, "wachturm", ohne)
    assert onion.uebernimm_schluessel(str(tmp_path), "wachturm") is True


def test_ein_vorhandener_schluessel_wird_nie_ueberschrieben(tmp_path):
    """Das waere ein Adresswechsel ohne Not."""
    ordner = onion.verzeichnis(str(tmp_path), "lnd")
    ordner.mkdir(parents=True)
    (ordner / "hs_ed25519_secret_key").write_bytes(b"tors eigener")
    _alt(tmp_path, "lnd", _altformat())
    assert onion.uebernimm_schluessel(str(tmp_path), "lnd") is False
    assert (ordner / "hs_ed25519_secret_key").read_bytes() == b"tors eigener"


def test_reste_die_nicht_passen_werden_entfernt(tmp_path):
    """Passt ein alter oeffentlicher Schluessel nicht, verweigert Tor den
    Start: "does not match" (loadkey.c)."""
    ordner = onion.verzeichnis(str(tmp_path), "bitcoind")
    ordner.mkdir(parents=True)
    (ordner / "hs_ed25519_public_key").write_bytes(b"fremd")
    (ordner / "hostname").write_text(TORPROJECT)
    _alt(tmp_path, "bitcoind", _altformat())
    onion.uebernimm_schluessel(str(tmp_path), "bitcoind")
    assert not (ordner / "hs_ed25519_public_key").exists()
    assert not (ordner / "hostname").exists()


@pytest.mark.parametrize("inhalt", [
    b"",
    b"RSA1024:abcd",
    b"ED25519-V3:",
    b"ED25519-V3:nicht base64!!",
    b"ED25519-V3:" + base64.b64encode(bytes(32)),     # zu kurz
    b"\xff\xfe verschluesselt",                        # tor.encryptkey
])
def test_was_kein_schluessel_ist_bleibt_liegen(tmp_path, inhalt):
    """Dann legt Tor eine neue Adresse an. Lieber das als ein Schluessel, den
    Tor nicht laden kann -- dann startete Tor gar nicht."""
    _alt(tmp_path, "lnd", inhalt)
    assert onion.uebernimm_schluessel(str(tmp_path), "lnd") is False
    assert not (onion.verzeichnis(str(tmp_path), "lnd")
                / "hs_ed25519_secret_key").exists()


def test_ohne_alten_schluessel_passiert_nichts(tmp_path):
    assert onion.uebernimm_schluessel(str(tmp_path), "bitcoind") is False
    assert not onion.verzeichnis(str(tmp_path), "bitcoind").exists()


# ── Der Zugang fuer externe Wallets ─────────────────────────────────────────
#
# Seit dem 26.09.2026: ein vierter Onion-Dienst fuer LNDs REST-Schnittstelle,
# ueber den Zeus den Knoten bedient. Er wird NICHT angekuendigt -- er steht
# nicht in dienste_fuer und damit weder in bitcoind noch in LND als
# externalip. Seine Adresse kennt nur, wem man den Verbindungstext gibt.

def test_der_fernzugang_wird_nie_angekuendigt():
    for sicht in ("tor", "hybrid", "still"):
        assert "fernzugang" not in onion.dienste_fuer(True, sicht)


def test_der_fernzugang_zeigt_auf_lnds_rest_schnittstelle():
    block = onion.torrc_block(("fernzugang",), "10.83.33")
    zeilen = block.splitlines()
    assert "HiddenServiceDir /fast/tor/onion-fernzugang" in zeilen
    assert "HiddenServicePort 8080 10.83.33.12:8080" in zeilen
    assert "onion-lnd" not in block


def test_der_fernzugang_steht_immer_zuletzt():
    """Feste Reihenfolge, damit dieselbe Wahl dieselbe Datei ergibt -- und
    damit die torrc aller, die ihn NICHT nutzen, Byte fuer Byte bleibt, wie
    sie war. Sonst startete jedes Update Tor ohne Anlass neu."""
    mit = onion.torrc_block(("fernzugang", "lnd", "bitcoind", "wachturm"),
                            "10.83.33")
    ohne = onion.torrc_block(("bitcoind", "lnd", "wachturm"), "10.83.33")
    assert mit.startswith(ohne)
    assert mit.index("onion-wachturm") < mit.index("onion-fernzugang")


def test_der_fernzugang_hat_keinen_alten_schluessel(tmp_path):
    """Es gab ihn vor 0.63.0 nicht -- nichts zu uebernehmen."""
    assert onion.DIENSTE["fernzugang"].alter_schluessel == ()
    assert onion.uebernimm_schluessel(str(tmp_path), "fernzugang") is False
