"""Das Kontobuch: aus Transaktionen wird, was Electrum je Skripthash fragt.

Geschichte, Status, Guthaben, unverbrauchte Ausgaenge. Reine Rechnerei --
die Werte kommen aus der Spezifikation (spesmilo/electrum-protocol,
protocol-basics.rst, "Status Example"), nicht aus eigener Annahme.
"""
import hashlib

from satcortex import kontobuch
from satcortex.kontobuch import Tx

A = "aa" * 32   # ein eigener Skripthash
B = "bb" * 32   # noch einer
F = "ff" * 32   # ein fremder


def _tx(txid, hoehe, position=0, gebuehr=None, aus=(), ein=()):
    return Tx(txid=txid, hoehe=hoehe, position=position, gebuehr=gebuehr,
              ausgaenge=tuple(aus), eingaenge=tuple(ein))


def _txid(zeichen):
    return zeichen * 64


# ── Das Beispiel der Spezifikation ─────────────────────────────────────────

SPEC = [
    ("a6c9c361bd0bc536d6a22648efbf8f9b200e425ef6c3a7a9669dc444c532a347", 2472),
    ("9c42f84b2fcdaff676ba25d9d4941741cc0d1a01cce0c23fdc4c0b2afa38431c", 2473),
    ("770f2d4371b3fabb902dd9a103e2dd005fcd3971181078fca4a2a1d6ff127b30", 2473),
    ("80b19848aed792565ab7c5a79b7c2a00fbf985741579396ebe0ab6098e607311", 0),
    ("e02a1dadfa83b996b24175df807b271ea5d02937ef5b35c195fac1e1bdc3198f", 0),
    ("bb4c8ab438c13b89ca80d1d5bee25b0b6b7f55673f4d801998ba97db161d9e85", -1),
]
SPEC_STATUS = "78e96c6562cafa71c115503b9411fdfdc595a45031e2ab76ff75162fe1b0590d"


def _spec_buch(reihenfolge):
    gebuehren = {SPEC[3][0]: 200, SPEC[4][0]: 300, SPEC[5][0]: 200}
    txs = []
    for i in reihenfolge:
        txid, hoehe = SPEC[i]
        txs.append(_tx(txid, hoehe, position=i, gebuehr=gebuehren.get(txid),
                       aus=[(0, A, 1000)]))
    return kontobuch.Buch(txs)


def test_der_status_stimmt_mit_dem_beispiel_der_spezifikation():
    assert _spec_buch(range(6)).status(A) == SPEC_STATUS


def test_die_reihenfolge_der_eingabe_spielt_keine_rolle():
    """Bestaetigte nach Hoehe und Stelle im Block, Mempool nach (-Hoehe,
    txid) -- egal, in welcher Folge Core sie liefert."""
    assert _spec_buch([5, 3, 1, 0, 4, 2]).status(A) == SPEC_STATUS


def test_die_geschichte_entspricht_dem_beispiel():
    g = _spec_buch([5, 4, 3, 2, 1, 0]).geschichte(A)
    assert g == [
        {"tx_hash": SPEC[0][0], "height": 2472},
        {"tx_hash": SPEC[1][0], "height": 2473},
        {"tx_hash": SPEC[2][0], "height": 2473},
        {"tx_hash": SPEC[3][0], "height": 0, "fee": 200},
        {"tx_hash": SPEC[4][0], "height": 0, "fee": 300},
        {"tx_hash": SPEC[5][0], "height": -1, "fee": 200},
    ]


def test_ohne_geschichte_ist_der_status_null():
    assert kontobuch.Buch([]).status(A) is None
    assert kontobuch.Buch([_tx(_txid("1"), 5, aus=[(0, F, 5)])]).status(A) is None


def test_der_status_ist_sha256_der_verketteten_zeile():
    buch = kontobuch.Buch([_tx(_txid("1"), 7, aus=[(0, A, 5)])])
    erwartet = hashlib.sha256(f"{_txid('1')}:7:".encode()).hexdigest()
    assert buch.status(A) == erwartet


# ── Ein- und Ausgaenge, wie an der Regtest-Kette gesehen ───────────────────
#
# T1 zahlt 50 an A, T2 zahlt 25 an B, T3 gibt die 25 von B aus (10 fort,
# 14 Wechselgeld an A... hier vereinfacht), T4 zahlt 1 an A im Mempool.

T1, T2, T3, T4 = _txid("1"), _txid("2"), _txid("3"), _txid("4")


def _szenario():
    return kontobuch.Buch([
        _tx(T1, 104, 1, aus=[(0, F, 999), (1, A, 50)]),
        _tx(T2, 104, 2, aus=[(0, B, 25), (1, F, 100)]),
        _tx(T3, 105, 1, aus=[(0, A, 14), (1, F, 10)],
            ein=[(T2, 0, B, 25)]),
        _tx(T4, 0, gebuehr=282, aus=[(0, A, 1)]),
    ])


def test_eine_ausgabe_gehoert_in_die_geschichte_der_adresse_von_der_sie_kam():
    """Genau das liefert Cores Wallet nicht direkt: bei einer Ausgabe nennt
    sie das ZIEL, nicht die eigene Adresse, von der das Geld kam."""
    assert [e["tx_hash"] for e in _szenario().geschichte(B)] == [T2, T3]


def test_das_guthaben_trennt_bestaetigt_und_unbestaetigt():
    buch = _szenario()
    assert buch.guthaben(A) == {"confirmed": 64, "unconfirmed": 1}
    assert buch.guthaben(B) == {"confirmed": 0, "unconfirmed": 0}


def test_eine_ausgabe_im_mempool_macht_unbestaetigt_negativ():
    """Die Spezifikation laesst das ausdruecklich zu: was im Mempool
    ausgegeben wird, ist bestaetigt noch da und unbestaetigt schon weg."""
    buch = kontobuch.Buch([
        _tx(T1, 100, aus=[(0, A, 50)]),
        _tx(T2, 0, gebuehr=100, aus=[(0, F, 40)], ein=[(T1, 0, A, 50)]),
    ])
    assert buch.guthaben(A) == {"confirmed": 50, "unconfirmed": -50}


def test_unverbraucht_ist_nur_was_niemand_ausgibt():
    buch = _szenario()
    assert buch.unverbraucht(A) == [
        {"tx_hash": T1, "tx_pos": 1, "height": 104, "value": 50},
        {"tx_hash": T3, "tx_pos": 0, "height": 105, "value": 14},
        {"tx_hash": T4, "tx_pos": 0, "height": 0, "value": 1},
    ]
    assert buch.unverbraucht(B) == []


def test_was_im_mempool_ausgegeben_wird_ist_nicht_mehr_unverbraucht():
    buch = kontobuch.Buch([
        _tx(T1, 100, aus=[(0, A, 50)]),
        _tx(T2, 0, gebuehr=100, aus=[(0, F, 40)], ein=[(T1, 0, A, 50)]),
    ])
    assert buch.unverbraucht(A) == []


def test_der_mempool_teil_der_geschichte():
    assert _szenario().mempool(A) == [
        {"tx_hash": T4, "height": 0, "fee": 282}]


def test_eine_transaktion_zweimal_geliefert_zaehlt_einmal():
    """Zahlt eine Transaktion an zwei angemeldete Konten, liefern beide
    Wallets sie -- im Buch steht sie trotzdem nur einmal."""
    t = _tx(T1, 100, aus=[(0, A, 50)])
    buch = kontobuch.Buch([t, t])
    assert buch.geschichte(A) == [{"tx_hash": T1, "height": 100}]
    assert buch.guthaben(A)["confirmed"] == 50


def test_skripthashes_kennt_alle_eigenen_beruehrten():
    assert _szenario().beruehrt() >= {A, B}
