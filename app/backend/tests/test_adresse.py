"""Adressen abfragen -- und dabei nichts einschleusen lassen."""
import pytest

from satcortex import adresse


class Knoten:
    def __init__(self, gueltig=True, normiert=None):
        self.gueltig = gueltig
        self.normiert = normiert
        self.aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None):
        self.aufrufe.append((methode, params))
        assert methode == "validateaddress"
        return {"isvalid": self.gueltig,
                "address": self.normiert or params[0]}


GUT = "bc1q" + "a" * 38


@pytest.mark.parametrize("eingabe", [
    "",
    "zu-kurz",
    GUT + "),raw(00",            # ein zweiter Descriptor im Eingabefeld
    "addr(" + GUT + ")",
    GUT[:20] + " " + GUT[20:],
    "a" * 91,
])
def test_was_kein_adresszeichen_ist_geht_nicht_an_bitcoind(eingabe):
    """Ein Descriptor ist eine kleine Sprache. Klammern und Kommas
    durchzulassen hiesse, fremde Suchausdruecke einschleusen zu lassen."""
    k = Knoten()
    with pytest.raises(adresse.AdresseUngueltig):
        adresse.pruefe(k, eingabe)
    assert k.aufrufe == []


def test_bitcoind_hat_das_letzte_wort():
    """Die Pruefsumme und das Netz kennt nur der Knoten selbst -- eine
    Testnetz-Adresse ist auf Mainnet ungueltig."""
    with pytest.raises(adresse.AdresseUngueltig):
        adresse.pruefe(Knoten(gueltig=False), GUT)
    assert adresse.pruefe(Knoten(normiert=GUT.lower()), "  " + GUT + " ") == GUT.lower()
    assert adresse.descriptor(GUT) == f"addr({GUT})"


def test_das_ergebnis_trifft_den_satoshi():
    """json.loads liefert Cores Betraege als float -- 0.1 + 0.2 ist dort nicht
    0.3."""
    roh = {"success": True, "txouts": 180_000_000, "height": 966_963,
           "total_amount": 0.30000000000000004,
           "unspents": [
               {"txid": "cd" * 32, "vout": 1, "amount": 0.1, "height": 966_900,
                "confirmations": 64, "coinbase": False},
               {"txid": "ef" * 32, "vout": 0, "amount": 0.2, "height": 966_950,
                "confirmations": 14, "coinbase": True},
           ]}
    d = adresse.ergebnis(roh)
    assert d["bestand_sat"] == 30_000_000
    assert [a["betrag_sat"] for a in d["ausgaben"]] == [20_000_000, 10_000_000]
    assert d["ausgaben"][0]["hoehe"] == 966_950, "die juengste zuerst"
    assert d["anzahl"] == 2 and d["weitere"] == 0 and d["hoehe"] == 966_963


def test_eine_sammeladresse_sprengt_die_antwort_nicht():
    roh = {"success": True, "total_amount": 5.0, "unspents": [
        {"txid": f"{i:064x}", "vout": 0, "amount": 0.01, "height": i,
         "confirmations": 1} for i in range(250)]}
    d = adresse.ergebnis(roh, hoechstens=200)
    assert d["anzahl"] == 250 and len(d["ausgaben"]) == 200 and d["weitere"] == 50
    assert d["bestand_sat"] == 500_000_000, "die Summe stimmt trotzdem"
