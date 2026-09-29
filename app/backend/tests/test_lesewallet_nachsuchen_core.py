"""Noch einmal suchen, wenn ein frueheres Datum kommt -- gegen ECHTES Core.

Aus dem Betrieb, 29.09.2026: Wer ein Konto mit zu spaetem "benutzt seit"
anmeldete, dem fehlte die aeltere Geschichte, und ein zweites Anmelden half
nicht. Ob Core dann wirklich ab dem neuen Datum sucht, zeigt nur Core
selbst.

Eigenes Modul, weil hier die Uhr der Kette vorgestellt wird (setmocktime):
aeltere Bloecke muessen WIRKLICH aelter sein als das Datum, sonst sucht Core
ohnehin alles ab (er nimmt zwei Stunden Spielraum vor dem Datum).
"""
import time

from satcortex import lesewallet, rpc
from regtest_kette import core, nur_mit_core, warten  # noqa: F401 -- core ist eine Fixture

pytestmark = nur_mit_core

TAG = 86400


def _guthaben(core, name):
    buch, eigene = lesewallet.Leser(core, lambda: [name]).lesen()
    return sum(buch.guthaben(s)["confirmed"] + buch.guthaben(s)["unconfirmed"]
               for s in eigene)


def test_ein_frueheres_datum_findet_die_aeltere_geschichte(core):
    core.ruf("createwallet", "geldgeber")
    core.ruf("createwallet", "geraet")
    geld = lambda: core.ruf("getnewaddress", wallet="geldgeber")  # noqa: E731
    core.ruf("generatetoaddress", 101, geld())
    konto = next(d["desc"] for d in core.ruf(
        "listdescriptors", wallet="geraet")["descriptors"]
        if d["desc"].startswith("wpkh(") and not d["internal"])
    empfang = core.ruf("deriveaddresses", konto, [0, 5])

    # Die alte Zahlung, dann zehn Tage spaeter die neue.
    core.ruf("sendtoaddress", empfang[0], 0.5, wallet="geldgeber")
    core.ruf("generatetoaddress", 1, geld())
    spaeter = int(time.time()) + 10 * TAG
    core.ruf("setmocktime", spaeter)
    core.ruf("generatetoaddress", 6, geld())
    core.ruf("sendtoaddress", empfang[2], 0.2, wallet="geldgeber")
    core.ruf("generatetoaddress", 1, geld())
    warten(core)

    tpub = konto.split("]")[1].split("/")[0]
    schluessel = lesewallet.lies_schluessel(tpub)

    # Erst mit einem Datum NACH der alten Zahlung: sie fehlt.
    name = lesewallet.anmelden(core, schluessel, "wpkh", seit=spaeter - 3600)
    warten(core)
    assert _guthaben(core, name) == rpc.sat_aus_btc(0.2)
    stempel = {d["timestamp"] for d in core.ruf(
        "listdescriptors", wallet=name)["descriptors"]}
    assert stempel == {spaeter - 3600}

    # Dasselbe Datum noch einmal: nichts Neues.
    lesewallet.anmelden(core, schluessel, "wpkh", seit=spaeter - 3600)
    warten(core)
    assert _guthaben(core, name) == rpc.sat_aus_btc(0.2)

    # Ohne Datum -- die ganze Kette: jetzt ist die alte Zahlung da, und das
    # Guthaben ist das, was das Geraet selbst sagt.
    lesewallet.anmelden(core, schluessel, "wpkh", seit=0)
    warten(core)
    geraet = core.ruf("getbalances", wallet="geraet")["mine"]
    assert _guthaben(core, name) == rpc.sat_aus_btc(0.7) == (
        rpc.sat_aus_btc(geraet["trusted"])
        + rpc.sat_aus_btc(geraet["untrusted_pending"]))
