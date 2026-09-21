"""Der eigene Beitrag -- nach Zweck aufgeschluesselt.

Anlass: "das keiner bloecke von mir will oder keine bekommen kann von mir ist
schon nicht foerderlich." Genau das laesst sich messen, statt es zu vermuten:
getpeerinfo schluesselt die gesendeten Bytes nach Nachrichtenart auf.
"""
from satcortex import beitrag, rpc


class Knoten(rpc.Knoten):
    def __init__(self, antworten, scheitern=False):
        super().__init__()
        self.antworten = antworten
        self.scheitern = scheitern

    def ruf(self, methode, *params, zeitlimit=None):
        if self.scheitern:
            raise rpc.NichtErreichbar("Attrappe")
        return self.antworten.get(methode)


PEERS = [
    {   # Ein echter Abnehmer: holt Bloecke von uns.
        "addr": "1.2.3.4:8333", "network": "ipv4", "inbound": True,
        "connection_type": "inbound", "conntime": 1756000000,
        "bytessent": 5_100_000, "subver": "/Satoshi:29.0.0/",
        "bytessent_per_msg": {"block": 4_900_000, "headers": 90_000,
                              "tx": 60_000, "ping": 400, "addrv2": 2000,
                              "cfilter": 40_000},
    },
    {   # Eine ausgehende Verbindung: von der LADEN wir, wir geben kaum etwas.
        "addr": "[2a02::1]:8333", "network": "ipv6", "inbound": False,
        "connection_type": "outbound-full-relay", "conntime": 1756000100,
        "bytessent": 12_000, "subver": "/Satoshi:31.1.0/",
        "bytessent_per_msg": {"version": 130, "verack": 24, "ping": 8000,
                              "getdata": 3800},
    },
    {   # Onion, nur Geplauder -- genau der Fall, der wie ein Beitrag aussieht.
        "addr": "abc.onion:8333", "network": "onion", "inbound": False,
        "connection_type": "block-relay-only", "conntime": 1756000200,
        "bytessent": 53_000, "subver": "/Satoshi:28.0.0/",
        "bytessent_per_msg": {"ping": 51_000, "addr": 2000},
    },
]

NETTOTALS = {
    "totalbytessent": 900_000_000, "totalbytesrecv": 400_000_000_000,
    "uploadtarget": {"timeframe": 86400, "target": 322_122_547_200,
                     "target_reached": False, "serve_historical_blocks": True,
                     "bytes_left_in_cycle": 300_000_000_000,
                     "time_left_in_cycle": 40_000},
}


def test_blockdaten_werden_von_geplauder_getrennt():
    """53 kB ueber Tor sehen nach Beitrag aus und sind Ping. Das ist der
    Unterschied, um den es geht."""
    d = beitrag.sammle(Knoten({"getpeerinfo": PEERS, "getnettotals": NETTOTALS}))
    a = d["ausgeliefert"]
    assert a["bloecke"] == 4_900_000
    assert a["transaktionen"] == 60_000
    assert a["filter"] == 40_000        # BIP158 fuer Leichtgewicht-Wallets
    assert a["kopfzeilen"] == 90_000
    assert a["adressen"] == 4000        # addr + addrv2
    # Ping, version, verack, getdata -- alles, was kein Beitrag ist.
    assert a["rest"] == 400 + 130 + 24 + 8000 + 3800 + 51_000


def test_die_groessten_abnehmer_zuerst():
    d = beitrag.sammle(Knoten({"getpeerinfo": PEERS, "getnettotals": NETTOTALS}))
    assert d["gegenstellen"][0]["adresse"] == "1.2.3.4:8333"
    assert d["gegenstellen"][0]["bloecke"] == 4_900_000
    assert d["gegenstellen"][0]["angenommen"] is True
    assert d["gegenstellen"][-1]["bloecke"] == 0


def test_das_budget_sagt_ob_alte_bloecke_noch_rausgehen():
    """Ist das Upload-Budget erschoepft, liefert der Knoten keine alten
    Bloecke mehr aus -- Neueinsteiger koennen dann nicht mehr bei ihm
    synchronisieren. Genau der Beitrag, um den es geht."""
    d = beitrag.sammle(Knoten({"getpeerinfo": PEERS, "getnettotals": NETTOTALS}))
    assert d["budget"]["liefert_alte_bloecke"] is True
    assert d["budget"]["erreicht"] is False

    erschoepft = dict(NETTOTALS)
    erschoepft["uploadtarget"] = dict(NETTOTALS["uploadtarget"],
                                      target_reached=True,
                                      serve_historical_blocks=False)
    d2 = beitrag.sammle(Knoten({"getpeerinfo": PEERS,
                                "getnettotals": erschoepft}))
    assert d2["budget"]["liefert_alte_bloecke"] is False


def test_ohne_budget_wird_nicht_faelschlich_nein_gesagt():
    """Fehlt uploadtarget ganz, heisst das 'unbegrenzt' -- nicht 'liefert
    nichts aus'. Ein falsches Nein hier waere ein Fehlalarm."""
    ohne = {k: v for k, v in NETTOTALS.items() if k != "uploadtarget"}
    d = beitrag.sammle(Knoten({"getpeerinfo": PEERS, "getnettotals": ohne}))
    assert d["budget"]["liefert_alte_bloecke"] is True


def test_ohne_knoten_bleibt_alles_bei_null():
    d = beitrag.sammle(Knoten({}, scheitern=True))
    assert d["erreichbar"] is False
    assert d["gegenstellen"] == []
    assert d["ausgeliefert"]["bloecke"] == 0


def test_unerwartete_antworten_kippen_nichts():
    assert beitrag.sammle(Knoten({"getpeerinfo": "kein array",
                                  "getnettotals": NETTOTALS}))["erreichbar"] is False
    d = beitrag.sammle(Knoten({"getpeerinfo": [None, 5, {}],
                               "getnettotals": NETTOTALS}))
    assert d["erreichbar"] is True and len(d["gegenstellen"]) == 1
