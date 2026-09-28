"""Die Nur-Lese-Wallet gegen ein ECHTES Bitcoin Core (Regtest).

Die Einheitstests pruefen die Regeln gegen Attrappen. Ob Core sich so
verhaelt, wie die Attrappen es behaupten, zeigt nur Core selbst -- genau
daran ist dieses Projekt schon mehrfach gescheitert ("eine Aussage ueber die
Aussenwelt wurde geglaubt statt gemessen").

Laeuft, wenn SATCORTEX_BITCOIND auf ein bitcoind zeigt; sonst uebersprungen.
Die Kette ist eine frische Regtest-Kette in einem Wegwerfverzeichnis, ohne
jede Verbindung nach aussen.

Das Szenario stellt eine Hardware-Wallet nach: eine Wallet MIT Schluesseln
("geraet"), deren oeffentlicher Kontoschluessel angemeldet wird. Was das
Kontobuch sagt, muss mit dem uebereinstimmen, was das Geraet selbst sagt.
"""
import pytest

from satcortex import lesewallet, rpc
from regtest_kette import core, nur_mit_core, warten  # noqa: F401 -- core ist eine Fixture

pytestmark = nur_mit_core


def _sats(btc):
    return rpc.sat_aus_btc(btc)


@pytest.fixture(scope="module")
def szenario(core):
    """Geschichte entsteht, BEVOR das Konto angemeldet wird -- genau die
    muss das Nachsuchen finden."""
    core.ruf("createwallet", "geldgeber")
    core.ruf("createwallet", "geraet")
    geld = lambda: core.ruf("getnewaddress", wallet="geldgeber")  # noqa: E731
    core.ruf("generatetoaddress", 101, geld())

    konto = next(d["desc"] for d in core.ruf(
        "listdescriptors", wallet="geraet")["descriptors"]
        if d["desc"].startswith("wpkh(") and not d["internal"])
    tpub = konto.split("]")[1].split("/")[0]
    empfang = core.ruf("deriveaddresses", konto, [0, 5])

    t = {}
    t["ein0"] = core.ruf("sendtoaddress", empfang[0], 0.5, wallet="geldgeber")
    t["ein3"] = core.ruf("sendtoaddress", empfang[3], 0.25, wallet="geldgeber")
    core.ruf("generatetoaddress", 1, geld())
    t["aus"] = core.ruf("sendtoaddress", geld(), 0.1, wallet="geraet")
    core.ruf("generatetoaddress", 1, geld())
    t["mempool"] = core.ruf("sendtoaddress", empfang[0], 0.01,
                            wallet="geldgeber")
    warten(core)

    name = lesewallet.anmelden(core, lesewallet.lies_schluessel(tpub), "wpkh")
    warten(core)
    return {"name": name, "empfang": empfang, "t": t, "geld": geld}


def _buch(core, szenario):
    warten(core)
    return lesewallet.Leser(core, lambda: [szenario["name"]]).lesen()


def _summe(buch, eigene):
    bestaetigt = sum(buch.guthaben(s)["confirmed"] for s in eigene)
    offen = sum(buch.guthaben(s)["unconfirmed"] for s in eigene)
    return bestaetigt, offen


def _skript(core, adresse):
    return lesewallet.skripthash(
        core.ruf("validateaddress", adresse)["scriptPubKey"])


def test_das_guthaben_stimmt_mit_dem_geraet_ueberein(core, szenario):
    buch, eigene = _buch(core, szenario)
    geraet = core.ruf("getbalances", wallet="geraet")["mine"]
    bestaetigt, offen = _summe(buch, eigene)
    assert bestaetigt + offen == _sats(geraet["trusted"]) + _sats(
        geraet["untrusted_pending"])


def test_unverbraucht_ist_genau_was_das_geraet_ausgeben_kann(core, szenario):
    buch, eigene = _buch(core, szenario)
    unsere = {(u["tx_hash"], u["tx_pos"]) for s in eigene
              for u in buch.unverbraucht(s)}
    geraet = {(u["txid"], u["vout"])
              for u in core.ruf("listunspent", 0, wallet="geraet")}
    assert unsere == geraet


def test_die_adresse_hinter_der_luecke_hat_ein_und_ausgang(core, szenario):
    """#3 bekam 0,25 und hat sie ausgegeben. Die Ausgabe steht bei Core als
    "send" mit dem ZIEL -- das Kontobuch muss sie trotzdem hier fuehren."""
    buch, _eigene = _buch(core, szenario)
    geschichte = buch.geschichte(_skript(core, szenario["empfang"][3]))
    assert [e["tx_hash"] for e in geschichte] == [
        szenario["t"]["ein3"], szenario["t"]["aus"]]
    assert all(e["height"] > 0 for e in geschichte)


def test_die_zahlung_im_mempool_steht_mit_hoehe_null_und_gebuehr(core, szenario):
    buch, _eigene = _buch(core, szenario)
    geschichte = buch.geschichte(_skript(core, szenario["empfang"][0]))
    letzte = geschichte[-1]
    assert letzte["tx_hash"] == szenario["t"]["mempool"]
    assert letzte["height"] == 0 and letzte["fee"] > 0


def test_eine_ausgabe_aus_dem_mempool_wird_gesehen(core, szenario):
    """Ohne prevout (gemessen): der Vorgaenger muss nachgeschlagen werden."""
    txid = core.ruf("sendtoaddress", szenario["geld"](), 0.05, wallet="geraet")
    buch, eigene = _buch(core, szenario)
    assert any(txid in {e["tx_hash"] for e in buch.geschichte(s)}
               for s in eigene)
    test_das_guthaben_stimmt_mit_dem_geraet_ueberein(core, szenario)


def test_ein_unbestaetigter_vorgaenger_ergibt_minus_eins(core, szenario):
    adresse = szenario["empfang"][2]
    vorher = core.ruf("sendtoaddress", adresse, 0.04, wallet="geldgeber")
    warten(core)
    vout = next(a["n"] for a in core.ruf("getrawtransaction", vorher, 1)["vout"]
                if a["scriptPubKey"].get("address") == adresse)
    roh = core.ruf("createrawtransaction", [{"txid": vorher, "vout": vout}],
                   [{szenario["geld"](): 0.0399}])
    nachher = core.ruf("sendrawtransaction", core.ruf(
        "signrawtransactionwithwallet", roh, wallet="geraet")["hex"])
    buch, _eigene = _buch(core, szenario)
    hoehen = {e["tx_hash"]: e["height"]
              for e in buch.geschichte(_skript(core, adresse))}
    assert hoehen == {vorher: 0, nachher: -1}


def test_nach_dem_naechsten_block_ist_alles_bestaetigt(core, szenario):
    core.ruf("generatetoaddress", 1, szenario["geld"]())
    buch, eigene = _buch(core, szenario)
    assert all(e["height"] > 0 for s in eigene for e in buch.geschichte(s))
    bestaetigt, offen = _summe(buch, eigene)
    assert offen == 0
    geraet = core.ruf("getbalances", wallet="geraet")["mine"]
    assert bestaetigt == _sats(geraet["trusted"])


def test_derselbe_schluessel_noch_einmal_angemeldet_ist_dieselbe_wallet(
        core, szenario):
    konto = next(d["desc"] for d in core.ruf(
        "listdescriptors", wallet="geraet")["descriptors"]
        if d["desc"].startswith("wpkh(") and not d["internal"])
    tpub = konto.split("]")[1].split("/")[0]
    name = lesewallet.anmelden(core, lesewallet.lies_schluessel(tpub), "wpkh")
    assert name == szenario["name"]


def test_die_wallet_ist_wirklich_nur_lesend(core, szenario):
    info = core.ruf("getwalletinfo", wallet=szenario["name"])
    assert info["private_keys_enabled"] is False
    with pytest.raises(rpc.RpcFehler):
        core.ruf("sendtoaddress", szenario["geld"](), 0.001,
                 wallet=szenario["name"])


# ── Eine Wallet, die es nicht gibt ──────────────────────────────────────────
#
# Darauf baut das Erkennen einer unterbrochenen Anmeldung: Core muss eine
# fehlende Wallet beim Laden UND beim Fragen mit demselben Code melden. Das
# war bisher nur angenommen.

NIE_ANGELEGT = "satcortex-lesen-nie-angelegt"


def test_eine_nie_angelegte_wallet_meldet_core_als_nicht_vorhanden(core):
    with pytest.raises(rpc.RpcFehler) as laden:
        lesewallet.laden(core, NIE_ANGELEGT)
    assert lesewallet.gibt_es_nicht(laden.value)
    with pytest.raises(rpc.RpcFehler) as fragen:
        core.ruf("listdescriptors", wallet=NIE_ANGELEGT)
    assert lesewallet.gibt_es_nicht(fragen.value)


def test_der_leser_uebergeht_eine_wallet_die_es_nicht_gibt(core, szenario):
    gemeldet = []
    buch, eigene = lesewallet.Leser(
        core, lambda: [NIE_ANGELEGT, szenario["name"]],
        fehlt=lambda name: gemeldet.append(name) or True).lesen()
    assert gemeldet == [NIE_ANGELEGT]
    assert _summe(buch, eigene) == _summe(*_buch(core, szenario))
