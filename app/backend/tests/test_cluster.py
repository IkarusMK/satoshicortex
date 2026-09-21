"""Der Cluster einer wartenden Transaktion -- in Cores Format von v31.1."""
from satcortex import cluster

ELTERN = "aa" * 32
KIND = "bb" * 32
FREMD = "cc" * 32


def _core(chunks, txcount=3, clusterweight=2200):
    return {"clusterweight": clusterweight, "txcount": txcount, "chunks": chunks}


def test_das_paket_zaehlt_nicht_die_einzelne_transaktion():
    """Ein Kind zahlt fuer seine Eltern: beide kommen als EIN Paket in den
    Block, und fuer das Kind zaehlt die Rate dieses Pakets."""
    roh = _core([
        {"chunkfee": 0.000021, "chunkweight": 1400, "txs": [ELTERN, KIND]},
        {"chunkfee": 0.000002, "chunkweight": 800, "txs": [FREMD]},
    ])
    d = cluster.aus_core(roh, KIND)
    assert d["txzahl"] == 3 and d["vbytes"] == 550
    assert d["eigenes_paket"] == 1
    erstes = d["pakete"][0]
    assert erstes == {"nummer": 1, "txs": [ELTERN, KIND], "gebuehr_sat": 2100,
                      "vbytes": 350, "satz_sat_vb": 6.0}
    assert d["pakete"][1]["satz_sat_vb"] == 1.0


def test_ein_vbyte_wird_aufgerundet_wie_bei_core():
    roh = _core([{"chunkfee": 0.00000201, "chunkweight": 801, "txs": [KIND]}],
                txcount=1, clusterweight=801)
    d = cluster.aus_core(roh, KIND)
    assert d["pakete"][0]["vbytes"] == 201 and d["vbytes"] == 201


def test_unbrauchbares_ergibt_keinen_cluster():
    assert cluster.aus_core(None, KIND) is None
    assert cluster.aus_core({"chunks": []}, KIND) is None
    assert cluster.aus_core({"chunks": ["kaputt"]}, KIND) is None
