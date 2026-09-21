"""Wo die Gegenstellen unserer Lightning-Kanaele sitzen.

Fuer die orangen Linien auf der Weltkarte. Sie laufen neben den gelben, die
schon da sind -- gelb ist, mit wem der Bitcoin-Knoten spricht, orange, wohin
Kapital gebunden ist. Zwei Netze, ein Bild.

Geprueft am 01.09.2026 gegen lnrpc/lightning.proto:
    LightningNode { ... repeated NodeAddress addresses = 4; ... }
    NodeAddress   { string network = 1; string addr = 2; }
"""
from satcortex import karte, lnd


class LndAttrappe:
    def __init__(self, knoten_nach_schluessel, kanaele=None):
        self._knoten = knoten_nach_schluessel
        self._kanaele = kanaele
        self.gefragt = []

    def ruf(self, pfad, macaroon="", daten=None, **kw):
        self.gefragt.append(pfad)
        if pfad.startswith("/v1/channels"):
            return {"channels": self._kanaele or []}
        if pfad.startswith("/v1/graph/node/"):
            schluessel = pfad.rsplit("/", 1)[-1].split("?")[0]
            if schluessel not in self._knoten:
                raise lnd.LndFehler("unknown node")
            return {"node": self._knoten[schluessel]}
        raise lnd.LndFehler(f"nicht vorgesehen: {pfad}")


def _kanal(pubkey, alias, kapazitaet=1_000_000):
    return {"active": True, "remote_pubkey": pubkey, "peer_alias": alias,
            "capacity": str(kapazitaet), "local_balance": "400000",
            "remote_balance": "600000", "channel_point": "abc:0"}


def _knoten(alias, *adressen):
    return {"alias": alias, "addresses": [
        {"network": "tcp", "addr": a} for a in adressen]}


def test_zu_jeder_gegenstelle_kommen_ihre_adressen():
    k = LndAttrappe(
        {"03aa": _knoten("ACINQ", "13.248.222.197:9735"),
         "03bb": _knoten("Bitrefill", "52.50.244.44:9735")},
        [_kanal("03aa", "ACINQ", 5_000_000), _kanal("03bb", "Bitrefill")])
    liste = lnd.gegenstellen(k)
    # Groesste zuerst -- ACINQ hat 5 Mio, Bitrefill 1 Mio.
    assert [g["alias"] for g in liste] == ["ACINQ", "Bitrefill"]
    assert liste[0]["adressen"] == ["13.248.222.197:9735"]
    assert liste[0]["kapazitaet"] == 5_000_000


def test_zwei_kanaele_zur_selben_gegenstelle_werden_zusammengefasst():
    """Sonst zaehlte dieselbe Gegenstelle doppelt auf der Karte -- und der
    Knoten wuerde zweimal abgefragt, ohne dass es etwas braechte."""
    k = LndAttrappe({"03aa": _knoten("ACINQ", "13.248.222.197:9735")},
                    [_kanal("03aa", "ACINQ", 2_000_000),
                     _kanal("03aa", "ACINQ", 3_000_000)])
    liste = lnd.gegenstellen(k)
    assert len(liste) == 1
    assert liste[0]["kapazitaet"] == 5_000_000
    assert liste[0]["kanaele"] == 2
    assert sum(1 for p in k.gefragt if p.startswith("/v1/graph/node/")) == 1


def test_eine_unbekannte_gegenstelle_wirft_den_rest_nicht_weg():
    """Ein Knoten, der sich nie angekuendigt hat, steht nicht im Graphen.
    Das ist Alltag und darf die anderen nicht mitnehmen."""
    k = LndAttrappe({"03bb": _knoten("Bitrefill", "52.50.244.44:9735")},
                    [_kanal("03aa", "Unbekannt"), _kanal("03bb", "Bitrefill")])
    liste = lnd.gegenstellen(k)
    # Gleiche Kapazitaet, also bleibt die Reihenfolge der Kanalliste.
    assert {g["alias"] for g in liste} == {"Unbekannt", "Bitrefill"}
    ohne = [g for g in liste if g["alias"] == "Unbekannt"][0]
    assert ohne["adressen"] == []


class TabelleAttrappe:
    # Adresse -> (Land, Gebiet). Wie die echte Tabelle: ort() ist die Quelle,
    # land() nur die kurze Frage daran.
    ORTE = {"13.248.222.197": ("FR", 11), "52.50.244.44": ("IE", 22)}

    def ort(self, adresse):
        return self.ORTE.get(adresse, (None, 0))

    def land(self, adresse):
        return self.ort(adresse)[0]


def test_gegenstellen_bekommen_ein_land():
    orte = karte.verorte_lightning([
        {"alias": "ACINQ", "kapazitaet": 5_000_000, "kanaele": 1,
         "adressen": ["13.248.222.197:9735"]},
        {"alias": "Bitrefill", "kapazitaet": 1_000_000, "kanaele": 1,
         "adressen": ["52.50.244.44:9735"]},
    ], TabelleAttrappe())
    assert orte["laender"] == {"FR": 1, "IE": 1}
    assert orte["verortet"] == 2 and orte["ohne_ort"] == 0
    assert orte["kapazitaet_je_land"] == {"FR": 5_000_000, "IE": 1_000_000}


def test_eine_onion_gegenstelle_hat_keinen_ort_und_verschwindet_nicht():
    """Sie hat keinen -- eine Onion-Adresse ist keine IP. Sie zu
    verschweigen waere aber falsch: das Kapital liegt trotzdem dort."""
    orte = karte.verorte_lightning([
        {"alias": "Versteckt", "kapazitaet": 2_000_000, "kanaele": 1,
         "adressen": ["abcdefg.onion:9735"]}], TabelleAttrappe())
    assert orte["laender"] == {}
    assert orte["ohne_ort"] == 1
    assert orte["kapazitaet_ohne_ort"] == 2_000_000


def test_mehrere_adressen_zaehlen_einmal():
    """Ein Knoten kuendigt oft IPv4, IPv6 UND eine Onion-Adresse an. Er sitzt
    trotzdem an einem Ort."""
    orte = karte.verorte_lightning([
        {"alias": "ACINQ", "kapazitaet": 5_000_000, "kanaele": 1,
         "adressen": ["abc.onion:9735", "13.248.222.197:9735"]}],
        TabelleAttrappe())
    assert orte["laender"] == {"FR": 1} and orte["ohne_ort"] == 0


def test_ohne_ortstabelle_gibt_es_keine_laender_aber_auch_keinen_absturz():
    orte = karte.verorte_lightning([
        {"alias": "ACINQ", "kapazitaet": 1, "kanaele": 1,
         "adressen": ["13.248.222.197:9735"]}], None)
    assert orte["laender"] == {} and orte["verortet"] == 0
