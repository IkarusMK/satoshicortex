"""Der Electrum-Betrieb: Server an und aus, Konten an- und abmelden.

Das Nachsuchen in der Kette laeuft im Hintergrund -- an einem echten Knoten
kann es dauern, und die Oberflaeche soll derweil den Fortschritt zeigen,
nicht haengen.
"""
import asyncio
import threading

import pytest

from satcortex import electrumbetrieb, lesewallet, rpc
from satcortex.state import Ablage

from test_lesewallet import BIP84_ZPUB, BIP84_ZPRV, _mit_version

TPUB = _mit_version(BIP84_ZPUB, "043587cf")       # tpub: die Art ist offen
VPUB = _mit_version(BIP84_ZPUB, "045f1cf6")       # vpub: Native SegWit


class Core:
    def __init__(self):
        self.aufrufe = []
        self.kette = "regtest"

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        self.aufrufe.append((methode, params, wallet))
        if methode == "getblockchaininfo":
            return {"chain": self.kette}
        if methode == "getwalletinfo":
            return {"scanning": False}
        if methode == "unloadwallet":
            return {}
        if methode == "loadwallet":
            raise rpc.RpcFehler("already loaded", -35)
        return None

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return [self.ruf(m, *p, wallet=wallet) for m, p in aufrufe]


@pytest.fixture
def betrieb(tmp_path, monkeypatch):
    core = Core()
    zustand = Ablage(str(tmp_path / "zustand"))
    b = electrumbetrieb.Betrieb(lambda: core, zustand,
                                str(tmp_path / "electrum"), version="test",
                                host="127.0.0.1", port=0)
    b.core = core
    b.zustand = zustand
    b.angemeldet = []
    b.freigabe = threading.Event()
    b.freigabe.set()
    b.drin = threading.Event()          # eine Suche hat begonnen
    b.gleichzeitig = 0
    b.hoechstens_gleichzeitig = 0
    zaehler = threading.Lock()

    def anmelden(knoten, schluessel, art, seit=0, **_kw):
        with zaehler:
            b.gleichzeitig += 1
            b.hoechstens_gleichzeitig = max(b.hoechstens_gleichzeitig,
                                            b.gleichzeitig)
        b.drin.set()
        try:
            b.freigabe.wait(5)
            b.angemeldet.append((schluessel.normiert, art, seit))
            if getattr(b, "anmelden_scheitert", False):
                raise lesewallet.LeseFehler("kaputt")
            return lesewallet.walletname(schluessel, art)
        finally:
            with zaehler:
                b.gleichzeitig -= 1
    monkeypatch.setattr(lesewallet, "anmelden", anmelden)
    return b


def _fertig(b):
    for faden in list(b._faeden):
        faden.join(5)


# ── Anmelden ───────────────────────────────────────────────────────────────

def test_ein_konto_wird_angemeldet_und_gemerkt(betrieb):
    wallet = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    _fertig(betrieb)
    konten = betrieb.zustand.laden().electrumwahl["konten"]
    assert [(k["wallet"], k["name"], k["art"]) for k in konten] == [
        (wallet, "BitBox", "wpkh")]
    assert betrieb.angemeldet[0][1] == "wpkh"


def test_ist_die_art_offen_muss_sie_gewaehlt_werden(betrieb):
    """Ein xpub/tpub kann Taproot, Legacy oder SegWit sein -- raten hiesse,
    im Zweifel eine leere Wallet zu zeigen."""
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.konto_anmelden(TPUB, None, "Trezor", None)
    assert fehler.value.schluessel == "el_art_waehlen"
    betrieb.konto_anmelden(TPUB, "tr", "Trezor", None)
    _fertig(betrieb)
    assert betrieb.angemeldet[0][1] == "tr"


def test_eine_art_die_dem_praefix_widerspricht_wird_abgewiesen(betrieb):
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.konto_anmelden(VPUB, "tr", "BitBox", None)
    assert fehler.value.schluessel == "el_art_passt_nicht"


def test_ein_privater_schluessel_kommt_nicht_einmal_bis_core(betrieb):
    with pytest.raises(lesewallet.SchluesselFehler):
        betrieb.konto_anmelden(BIP84_ZPRV, None, "x", None)
    assert betrieb.core.aufrufe == []
    assert betrieb.angemeldet == []


def test_ein_schluessel_aus_dem_falschen_netz_faellt_sofort_auf(betrieb):
    """Nicht erst im Hintergrund: wer klickt, soll es gleich erfahren."""
    betrieb.core.kette = "main"
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.konto_anmelden(VPUB, None, "BitBox", None)
    assert fehler.value.schluessel == "el_falsches_netz"
    assert betrieb.zustand.laden().electrumwahl == {}


def test_ist_core_nicht_da_wird_nichts_gemerkt(betrieb):
    def weg(*_a, **_kw):
        raise rpc.NichtErreichbar("weg")
    betrieb.core.ruf = weg
    with pytest.raises(rpc.NichtErreichbar):
        betrieb.konto_anmelden(VPUB, None, "BitBox", None)
    assert betrieb.zustand.laden().electrumwahl == {}


def test_ein_datum_wird_zur_suchgrenze(betrieb):
    betrieb.konto_anmelden(VPUB, None, "BitBox", "2024-03-01")
    _fertig(betrieb)
    assert betrieb.angemeldet[0][2] == 1709251200


@pytest.mark.parametrize("seit", ["gestern", "2024-13-01", "1.3.2024"])
def test_ein_unlesbares_datum_wird_abgewiesen(betrieb, seit):
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.konto_anmelden(VPUB, None, "BitBox", seit)
    assert fehler.value.schluessel == "el_datum"


def test_dasselbe_konto_zweimal_ergibt_einen_eintrag(betrieb):
    a = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    _fertig(betrieb)
    b = betrieb.konto_anmelden(VPUB, None, "Nochmal", None)["wallet"]
    _fertig(betrieb)
    assert a == b
    assert len(betrieb.zustand.laden().electrumwahl["konten"]) == 1


def test_mehr_als_zehn_konten_gehen_nicht(betrieb, monkeypatch):
    monkeypatch.setattr(electrumbetrieb, "KONTEN_HOECHSTENS", 1)
    betrieb.konto_anmelden(VPUB, None, "Eins", None)
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.konto_anmelden(TPUB, "tr", "Zwei", None)
    assert fehler.value.schluessel == "el_zu_viele"


def test_der_name_ist_pflicht_und_begrenzt(betrieb):
    for name in ("", "   ", "x" * 41):
        with pytest.raises(lesewallet.SchluesselFehler) as fehler:
            betrieb.konto_anmelden(VPUB, None, name, None)
        assert fehler.value.schluessel == "el_name_ungueltig"


def test_waehrend_der_suche_steht_das_konto_als_suchend_da(betrieb):
    betrieb.freigabe.clear()
    wallet = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    konto = next(k for k in betrieb.lage()["konten"] if k["wallet"] == wallet)
    assert konto["sucht"] is True
    # ... und wird so lange nicht gelesen: Core lehnt Wallet-Aufrufe
    # waehrend des Nachsuchens teils ab.
    assert wallet not in betrieb.wallets()
    betrieb.freigabe.set()
    _fertig(betrieb)
    assert wallet in betrieb.wallets()
    assert next(k for k in betrieb.lage()["konten"]
                if k["wallet"] == wallet)["sucht"] is False


def test_zwei_konten_suchen_nacheinander(betrieb):
    """Jede Suche haelt in Core einen der Plaetze fuer Anfragen und laesst
    die Platte arbeiten. Zwei auf einmal kosten doppelt und sind nicht
    frueher fertig."""
    betrieb.freigabe.clear()
    a = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    b = betrieb.konto_anmelden(TPUB, "tr", "Trezor", None)["wallet"]
    assert betrieb.drin.wait(5)
    konten = {k["wallet"]: k for k in betrieb.lage()["konten"]}
    assert konten[a]["sucht"] and konten[b]["sucht"]
    # Genau eine sucht, die andere wartet -- und sagt das auch.
    assert sorted([konten[a]["wartet"], konten[b]["wartet"]]) == [False, True]
    wartend = a if konten[a]["wartet"] else b
    assert konten[wartend]["fortschritt"] is None
    betrieb.freigabe.set()
    _fertig(betrieb)
    assert betrieb.hoechstens_gleichzeitig == 1
    assert len(betrieb.angemeldet) == 2
    assert set(betrieb.wallets()) == {a, b}
    assert not any(k["wartet"] for k in betrieb.lage()["konten"])


def test_dasselbe_konto_waehrend_der_suche_wird_nicht_zweimal_gesucht(betrieb):
    betrieb.freigabe.clear()
    a = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    b = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    betrieb.freigabe.set()
    _fertig(betrieb)
    assert a == b
    assert len(betrieb.angemeldet) == 1


def test_scheitert_die_suche_steht_der_grund_da(betrieb):
    betrieb.anmelden_scheitert = True
    wallet = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    _fertig(betrieb)
    konto = next(k for k in betrieb.lage()["konten"] if k["wallet"] == wallet)
    assert konto["fehler"] and konto["sucht"] is False


def test_nach_der_suche_wird_angestossen(betrieb):
    angestossen = []
    betrieb.anstossen = lambda block=True: angestossen.append(block)
    betrieb.konto_anmelden(VPUB, None, "BitBox", None)
    _fertig(betrieb)
    assert angestossen


# ── Abmelden ───────────────────────────────────────────────────────────────

def test_abmelden_entlaedt_und_vergisst(betrieb):
    wallet = betrieb.konto_anmelden(VPUB, None, "BitBox", None)["wallet"]
    _fertig(betrieb)
    betrieb.konto_abmelden(wallet)
    assert betrieb.zustand.laden().electrumwahl["konten"] == []
    assert ("unloadwallet", (wallet, False), None) in betrieb.core.aufrufe


def test_ein_unbekanntes_konto_abzumelden_ist_ein_fehler(betrieb):
    with pytest.raises(KeyError):
        betrieb.konto_abmelden("satcortex-lesen-gibtsnicht")


def test_fremde_wallets_werden_nicht_angefasst(betrieb):
    """Nur, was dieser Betrieb selbst angelegt hat -- nie eine Wallet, die
    jemand anderes im Knoten hat."""
    with pytest.raises(KeyError):
        betrieb.konto_abmelden("geldgeber")
    assert not [a for a in betrieb.core.aufrufe if a[0] == "unloadwallet"]


# ── Server an und aus ──────────────────────────────────────────────────────

def test_einschalten_startet_den_server_und_merkt_es(betrieb):
    async def ablauf():
        await betrieb.einschalten()
        assert betrieb.laeuft and betrieb.zustand.laden().electrumwahl["an"]
        r, w = await asyncio.open_connection("127.0.0.1", betrieb.port)
        w.write(b'{"jsonrpc":"2.0","id":1,"method":"server.ping","params":[]}\n')
        assert b'"result": null' in await asyncio.wait_for(r.readline(), 5)
        w.close()
        await betrieb.ausschalten()
        assert not betrieb.laeuft
        assert betrieb.zustand.laden().electrumwahl["an"] is False
    asyncio.run(ablauf())


def test_die_konten_bleiben_beim_ausschalten_angemeldet(betrieb):
    """Aus heisst: niemand verbindet sich. Die Konten bleiben, damit man
    beim Wiedereinschalten nicht alles neu anmelden muss."""
    async def ablauf():
        betrieb.konto_anmelden(VPUB, None, "BitBox", None)
        _fertig(betrieb)
        await betrieb.einschalten()
        await betrieb.ausschalten()
        assert len(betrieb.zustand.laden().electrumwahl["konten"]) == 1
    asyncio.run(ablauf())


def test_beim_start_laeuft_er_nur_wenn_er_an_war(betrieb):
    async def ablauf():
        await betrieb.beim_start()
        assert not betrieb.laeuft
        betrieb.zustand.merke_electrumwahl({"an": True, "konten": []})
        await betrieb.beim_start()
        assert betrieb.laeuft
        await betrieb.ausschalten()
    asyncio.run(ablauf())


def test_anhalten_laesst_die_wahl_stehen(betrieb):
    """Beim Herunterfahren der Anwendung wird angehalten, nicht
    ausgeschaltet -- sonst waere Electrum nach jedem Neustart aus."""
    async def ablauf():
        await betrieb.einschalten()
        await betrieb.anhalten()
        assert not betrieb.laeuft
        assert betrieb.zustand.laden().electrumwahl["an"] is True
    asyncio.run(ablauf())


def test_anstossen_ohne_laufenden_server_ist_harmlos(betrieb):
    betrieb.anstossen()
    betrieb.anstossen(block=False)


def test_die_lage_nennt_zertifikat_erst_wenn_es_eines_gibt(betrieb):
    assert betrieb.lage()["tls"] is None

    async def ablauf():
        await betrieb.einschalten()
        tls = betrieb.lage()["tls"]
        assert tls["pem"].startswith("-----BEGIN CERTIFICATE-----")
        assert len(tls["fingerabdruck"].split(":")) == 32
        await betrieb.ausschalten()
    asyncio.run(ablauf())


# ── Eine Anmeldung, die ein Neustart unterbrochen hat ──────────────────────
#
# Wer auf seine Suche wartet, hat in Core noch keine Wallet. Startet die
# Anwendung in der Zeit neu, bleibt nur der Name -- der Schluessel wird nie
# gespeichert. Das Konto muss das sagen, und die anderen muessen weiter
# gelesen werden.

def _zwei_konten(betrieb, an=False):
    betrieb.zustand.merke_electrumwahl({"an": an, "konten": [
        {"wallet": "satcortex-lesen-da", "name": "Da", "art": "wpkh",
         "angelegt": "2026-09-28T00:00:00+00:00"},
        {"wallet": "satcortex-lesen-weg", "name": "Weg", "art": "wpkh",
         "angelegt": "2026-09-28T00:00:00+00:00"}]})
    echt = betrieb.core.ruf

    def ruf(methode, *params, zeitlimit=None, wallet=None):
        if (methode == "loadwallet" and params[0] == "satcortex-lesen-weg") \
                or wallet == "satcortex-lesen-weg":
            betrieb.core.aufrufe.append((methode, params, wallet))
            raise rpc.RpcFehler("Requested wallet does not exist", -18)
        return echt(methode, *params, zeitlimit=zeitlimit, wallet=wallet)
    betrieb.core.ruf = ruf


def _konto(betrieb, wallet):
    return next(k for k in betrieb.lage()["konten"] if k["wallet"] == wallet)


def test_nach_dem_neustart_steht_eine_unterbrochene_anmeldung_da(betrieb):
    """Auch wenn der Dienst aus ist: die Liste soll stimmen, bevor jemand
    ihn einschaltet."""
    _zwei_konten(betrieb, an=False)
    asyncio.run(betrieb.beim_start())
    assert _konto(betrieb, "satcortex-lesen-weg")["fehler"] == "el_unterbrochen"
    assert _konto(betrieb, "satcortex-lesen-da")["fehler"] is None
    assert betrieb.wallets() == ["satcortex-lesen-da"]


def test_das_lesen_uebergeht_eine_wallet_die_es_nicht_gibt(betrieb):
    """Fand der Start Core noch nicht bereit, faellt es beim ersten Lesen
    auf -- und haelt die anderen Konten nicht auf."""
    _zwei_konten(betrieb, an=True)
    betrieb._bestand.auffrischen()
    assert _konto(betrieb, "satcortex-lesen-weg")["fehler"] == "el_unterbrochen"
    assert ("listtransactions", ("*", lesewallet.SEITE, 0, True),
            "satcortex-lesen-da") in betrieb.core.aufrufe
    assert betrieb.wallets() == ["satcortex-lesen-da"]


def test_wer_neu_anmeldet_raeumt_die_unterbrechung_weg(betrieb):
    _zwei_konten(betrieb, an=False)
    asyncio.run(betrieb.beim_start())
    betrieb.core.ruf = Core().ruf
    betrieb.konto_anmelden(VPUB, None, "BitBox", None)
    _fertig(betrieb)
    wallet = lesewallet.walletname(lesewallet.lies_schluessel(VPUB), "wpkh")
    assert _konto(betrieb, wallet)["fehler"] is None


# ── Die Adresse der NAS im Heimnetz ────────────────────────────────────────
#
# Aus dem Betrieb, 29.09.2026: die Karte zeigte den Namen aus der
# Adresszeile -- geoeffnet ueber eine Domain hinter einem Reverse Proxy war
# das die Domain, und ueber die geht Electrum nicht.

@pytest.mark.parametrize("host", ["192.0.2.20", "nas.local", "nas",
                                  "fd00::12", "NAS-1.fritz.box"])
def test_die_heimnetz_adresse_wird_gemerkt(betrieb, host):
    betrieb.heimnetz_host_setzen(host)
    assert betrieb.lage()["heimnetz_host"] == host


def test_die_heimnetz_adresse_ueberlebt_das_anmelden_eines_kontos(betrieb):
    betrieb.heimnetz_host_setzen("192.0.2.20")
    betrieb.konto_anmelden(VPUB, None, "BitBox", None)
    _fertig(betrieb)
    asyncio.run(betrieb.einschalten())
    asyncio.run(betrieb.ausschalten())
    assert betrieb.lage()["heimnetz_host"] == "192.0.2.20"


def test_leer_heisst_wieder_aus_der_adresszeile(betrieb):
    betrieb.heimnetz_host_setzen("192.0.2.20")
    betrieb.heimnetz_host_setzen("  ")
    assert betrieb.lage()["heimnetz_host"] == ""


@pytest.mark.parametrize("host", ["http://192.0.2.20", "192.0.2.20:50001",
                                  "nas lan", "<b>nas</b>", "x" * 254,
                                  "192.0.2.20/24", "-nas", "192.168.1.300"])
def test_eine_unbrauchbare_heimnetz_adresse_wird_abgewiesen(betrieb, host):
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        betrieb.heimnetz_host_setzen(host)
    assert fehler.value.schluessel == "el_heim_host_ungueltig"
