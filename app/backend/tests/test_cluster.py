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


# ── Haengt sie, oder wartet sie nur? (24.09.2026) ──────────────────────────
#
# Aus dem Betrieb: "das er mir jetzt bei jeder transaktion im wallet direkt
# anzeigt 'gebueren erhoehen!'". Die Wartelage entscheidet, ob der Knopf
# ueberhaupt Sinn hat. Eintraege in Cores Format von getmempoolentry (v31.1).

def _eintrag(chunk_btc=0.0000141, chunkweight=564, hoehe=900_000, **mehr):
    e = {"vsize": 141, "height": hoehe, "chunkweight": chunkweight,
         "ancestorsize": 141,
         "fees": {"base": 0.0000141, "ancestor": 0.0000141,
                  "chunk": chunk_btc}}
    e.update(mehr)
    return e


def test_wer_genug_zahlt_bekommt_keinen_knopf():
    """10 sat/vB gezahlt, 8 geschaetzt: Erhoehen auf 8 beschleunigt nichts."""
    d = cluster.wartelage(_eintrag(), 900_003, 8)
    assert d == {"lage": "reicht", "satz_sat_vb": 10.0, "noetig_sat_vb": 8,
                 "seit_block": 900_000}


def test_frisch_gesendet_haengt_noch_nicht():
    """Seit sie im Mempool liegt, kam noch kein Block -- sie hatte noch gar
    keine Gelegenheit, mitgenommen zu werden."""
    d = cluster.wartelage(_eintrag(), 900_000, 12)
    assert d["lage"] == "frisch"
    assert d["satz_sat_vb"] == 10.0 and d["noetig_sat_vb"] == 12


def test_haengt_erst_wenn_ein_block_ohne_sie_kam_und_sie_zu_wenig_zahlt():
    d = cluster.wartelage(_eintrag(), 900_001, 12)
    assert d == {"lage": "haengt", "satz_sat_vb": 10.0, "noetig_sat_vb": 12,
                 "seit_block": 900_000}


def test_es_zaehlt_das_paket_nicht_die_einzelne_transaktion():
    """Hat schon ein Kind nachgebessert, zahlt das PAKET mehr als die
    Transaktion allein -- und genau danach waehlt ein Miner aus."""
    e = _eintrag(chunk_btc=0.000042, chunkweight=1200)
    d = cluster.wartelage(e, 900_005, 12)
    assert d["satz_sat_vb"] == 14.0
    assert d["lage"] == "reicht"


def test_ohne_chunkangaben_gilt_die_vorfahrenrate():
    e = _eintrag()
    del e["chunkweight"]
    del e["fees"]["chunk"]
    e["fees"]["ancestor"] = 0.00000282
    e["ancestorsize"] = 282
    assert cluster.wartelage(e, 900_001, 2)["satz_sat_vb"] == 1.0


def test_nicht_im_mempool_heisst_kein_knopf():
    """Ein Kind an einer Transaktion, die der eigene Knoten nicht kennt,
    lehnt Core ab -- der Knopf scheiterte sicher."""
    assert cluster.wartelage(None, 900_001, 12) == {"lage": "nicht_im_mempool"}


def test_ohne_schaetzung_laesst_sich_nichts_sagen():
    """Und nachbessern ginge ohnehin nicht: der Endpunkt braucht den Satz."""
    assert cluster.wartelage(_eintrag(), 900_001, None) == {
        "lage": "keine_schaetzung"}
    assert cluster.wartelage(_eintrag(), 900_001, 0) == {
        "lage": "keine_schaetzung"}


def test_ein_unbrauchbarer_eintrag_ist_unklar():
    assert cluster.wartelage({"height": 900_000}, 900_001, 12) == {
        "lage": "unklar"}
