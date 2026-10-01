"""Nur-Lese-Wallets fuer Electrum: Schluessel lesen, Deskriptoren bauen.

Aus dem Betrieb, 28.09.2026: die Frage, was Trezor fuer eine direkte
Verbindung braucht -- BitBoxApp und Trezor Suite sprechen nur
Electrum. SatoshiCortex beantwortet es selbst; die Geschichte der Adressen
kommt aus einer Nur-Lese-Wallet in Bitcoin Core, die nur den OEFFENTLICHEN
Kontoschluessel kennt.

Die Pruefwerte stammen aus BIP-84 (Konto 0 der Merkwoerter "abandon ...
about"), nicht aus dem Gedaechtnis.
"""
import hashlib

import pytest

from satcortex import lesewallet

# BIP-84, "Account 0, root = m/84'/0'/0'".
BIP84_ZPUB = ("zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3Ef"
              "H1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs")
# Derselbe Vektor, privat. Ein oeffentlicher Testvektor -- genau das, was
# niemand je einfuegen soll, und deshalb der richtige Pruefstein.
BIP84_ZPRV = ("zprvAdG4iTXWBoARxkkzNpNh8r6Qag3irQB8PzEMkAFeTRXxHpbF9z4QgEvB"
              "RmfvqWvGp42t42nvgGpNgYSJA9iefm1yYNZKEm7z6qUWCroSQnE")

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58(roh: bytes) -> str:
    """Base58Check -- hier im Test unabhaengig nachgebaut, damit er den
    Code unter Test nicht mit sich selbst vergleicht."""
    roh = roh + hashlib.sha256(hashlib.sha256(roh).digest()).digest()[:4]
    n = int.from_bytes(roh, "big")
    text = ""
    while n:
        n, rest = divmod(n, 58)
        text = _ALPHABET[rest] + text
    return "1" * (len(roh) - len(roh.lstrip(b"\0"))) + text


def _roh(text: str) -> bytes:
    n = 0
    for zeichen in text:
        n = n * 58 + _ALPHABET.index(zeichen)
    return n.to_bytes(82, "big")[:-4]


def _mit_version(text: str, version: str) -> str:
    return _b58(bytes.fromhex(version) + _roh(text)[4:])


# ── Schluessel lesen ───────────────────────────────────────────────────────

def test_ein_zpub_ist_native_segwit_im_hauptnetz():
    s = lesewallet.lies_schluessel(BIP84_ZPUB)
    assert s.art == "wpkh"
    assert s.netz == "main"
    assert s.tiefe == 3


def test_der_zpub_wird_in_cores_schreibweise_umgerechnet():
    """Core nimmt vpub/zpub nicht an -- am 28.09.2026 an Core v31.1
    gemessen: "key '...' is not valid". Umgerechnet wird nur die
    Versionskennung, der Schluessel selbst bleibt Bit fuer Bit gleich."""
    s = lesewallet.lies_schluessel(BIP84_ZPUB)
    assert s.normiert.startswith("xpub")
    assert _roh(s.normiert)[4:] == _roh(BIP84_ZPUB)[4:]
    assert _mit_version(s.normiert, "04b24746") == BIP84_ZPUB


@pytest.mark.parametrize("version,art,netz", [
    ("049d7cb2", "sh-wpkh", "main"),   # ypub
    ("04b24746", "wpkh", "main"),      # zpub
    ("0488b21e", None, "main"),        # xpub: Taproot, Legacy oder SegWit
    ("044a5262", "sh-wpkh", "test"),   # upub
    ("045f1cf6", "wpkh", "test"),      # vpub
    ("043587cf", None, "test"),        # tpub
])
def test_die_art_folgt_dem_praefix(version, art, netz):
    s = lesewallet.lies_schluessel(_mit_version(BIP84_ZPUB, version))
    assert (s.art, s.netz) == (art, netz)


def test_leerraum_und_zeilenumbrueche_stoeren_nicht():
    s = lesewallet.lies_schluessel("  \n" + BIP84_ZPUB + " \n")
    assert s.art == "wpkh"


def test_ein_privater_schluessel_wird_abgewiesen():
    """Wer einen privaten Schluessel einfuegt, hat sich vertan -- und muss
    das deutlich erfahren. Er darf weder gespeichert noch an Core gereicht
    werden."""
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        lesewallet.lies_schluessel(BIP84_ZPRV)
    assert fehler.value.schluessel == "el_privat"


@pytest.mark.parametrize("version", ["0295b43f", "02aa7ed3",
                                     "024289ef", "02575483"])
def test_mehrfachsignatur_wird_abgewiesen(version):
    """Ypub/Zpub/Upub/Vpub gehoeren zu Mehrfachsignatur-Wallets. Die
    brauchen mehrere Schluessel und ein Quorum -- das hier kann das nicht,
    und es soll das sagen, statt eine leere Wallet zu zeigen."""
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        lesewallet.lies_schluessel(_mit_version(BIP84_ZPUB, version))
    assert fehler.value.schluessel == "el_mehrfach"


@pytest.mark.parametrize("text", [
    "", "hallo", BIP84_ZPUB[:-1] + ("A" if BIP84_ZPUB[-1] != "A" else "B"),
    BIP84_ZPUB + "0", "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu",
])
def test_was_kein_schluessel_ist_faellt_auf(text):
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        lesewallet.lies_schluessel(text)
    assert fehler.value.schluessel == "el_kein_schluessel"


# ── Deskriptoren ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("art,empfang", [
    ("wpkh", "wpkh(K/0/*)"),
    ("tr", "tr(K/0/*)"),
    ("pkh", "pkh(K/0/*)"),
    ("sh-wpkh", "sh(wpkh(K/0/*))"),
])
def test_je_art_zwei_ketten_empfang_und_wechsel(art, empfang):
    e, w = lesewallet.deskriptoren("K", art)
    assert e == empfang
    assert w == empfang.replace("/0/*", "/1/*")


def test_eine_unbekannte_art_wird_abgewiesen():
    with pytest.raises(lesewallet.SchluesselFehler):
        lesewallet.deskriptoren("K", "wsh")


# ── Name der Wallet in Core ────────────────────────────────────────────────

def test_derselbe_schluessel_ergibt_dieselbe_wallet():
    """Wer dasselbe Konto zweimal anmeldet, bekommt keine zweite Wallet --
    und der Name verraet nichts ueber den Schluessel."""
    s = lesewallet.lies_schluessel(BIP84_ZPUB)
    a = lesewallet.walletname(s, "wpkh")
    assert a == lesewallet.walletname(
        lesewallet.lies_schluessel(" " + BIP84_ZPUB), "wpkh")
    assert a.startswith("satcortex-lesen-")
    assert BIP84_ZPUB[4:20] not in a and s.normiert[4:20] not in a


def test_dasselbe_konto_als_andere_art_ist_eine_andere_wallet():
    s = lesewallet.lies_schluessel(_mit_version(BIP84_ZPUB, "0488b21e"))
    assert lesewallet.walletname(s, "tr") != lesewallet.walletname(s, "pkh")


# ── Mit Core sprechen ──────────────────────────────────────────────────────

from satcortex import rpc  # noqa: E402

TPUB_SCHLUESSEL = lesewallet.lies_schluessel(
    _mit_version(BIP84_ZPUB, "045f1cf6"))       # vpub -> tpub, Native SegWit


class Core:
    """Ein Knoten mit vorgegebenen Antworten -- Signatur wie rpc.Knoten."""

    def __init__(self, **antworten):
        self.antworten = antworten
        self.aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None, wallet=None):
        self.aufrufe.append((methode, params, wallet))
        antwort = self.antworten.get(methode)
        if callable(antwort):
            antwort = antwort(*params, wallet=wallet)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    def stapel(self, aufrufe, zeitlimit=None, wallet=None):
        return [self.ruf(m, *p, wallet=wallet) for m, p in aufrufe]

    def gerufen(self, methode):
        return [(p, w) for m, p, w in self.aufrufe if m == methode]


def _mit_pruefsumme(desc, **_kw):
    return {"descriptor": desc + "#abcdefgh"}


def _core_zum_anmelden(**abweichungen):
    antworten = dict(
        getblockchaininfo={"chain": "regtest"},
        createwallet={"name": "x"},
        getdescriptorinfo=_mit_pruefsumme,
        importdescriptors=[{"success": True}, {"success": True}],
    )
    antworten.update(abweichungen)
    return Core(**antworten)


def test_anmelden_legt_eine_wallet_ohne_private_schluessel_an():
    core = _core_zum_anmelden()
    name = lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh")
    [(params, _w)] = core.gerufen("createwallet")
    # createwallet: name, disable_private_keys, blank, passphrase,
    # avoid_reuse, descriptors, load_on_startup
    assert params == (name, True, True, "", False, True, True)


def test_anmelden_spielt_empfang_und_wechsel_aktiv_ein():
    core = _core_zum_anmelden()
    name = lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh", seit=1_700_000_000)
    [(params, wallet)] = core.gerufen("importdescriptors")
    assert wallet == name
    empfang, wechsel = params[0]
    assert empfang["desc"] == f"wpkh({TPUB_SCHLUESSEL.normiert}/0/*)#abcdefgh"
    assert (empfang["active"], empfang["internal"]) == (True, False)
    assert (wechsel["active"], wechsel["internal"]) == (True, True)
    assert wechsel["desc"].startswith(f"wpkh({TPUB_SCHLUESSEL.normiert}/1/*)")
    assert empfang["timestamp"] == wechsel["timestamp"] == 1_700_000_000


def test_ohne_zeitangabe_wird_die_ganze_kette_durchsucht():
    core = _core_zum_anmelden()
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh")
    [(params, _w)] = core.gerufen("importdescriptors")
    assert all(d["timestamp"] == 0 for d in params[0])


def test_eine_schon_vorhandene_wallet_wird_nur_geladen():
    """Dasselbe Konto noch einmal: Core lehnt einen zweiten Import ab, weil
    der Vorrat inzwischen gewachsen ist ("new range must include current
    range = [0,1003]" -- an der Regtest-Kette gefunden, 28.09.2026). Sind
    die Deskriptoren schon da, wird also nur geladen."""
    empfang, wechsel = lesewallet.deskriptoren(TPUB_SCHLUESSEL.normiert, "wpkh")
    core = _core_zum_anmelden(
        createwallet=rpc.RpcFehler("Database already exists.", -4),
        loadwallet=rpc.RpcFehler("already loaded", -35),
        listdescriptors={"descriptors": [
            {"desc": empfang + "#abcdefgh", "active": True, "range": [0, 1003]},
            {"desc": wechsel + "#abcdefgh", "active": True, "range": [0, 1001]},
        ]})
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh")
    assert core.gerufen("loadwallet")
    assert not core.gerufen("importdescriptors")


def _core_mit_vorhandenem_konto(zeitstempel):
    empfang, wechsel = lesewallet.deskriptoren(TPUB_SCHLUESSEL.normiert, "wpkh")
    core = _core_zum_anmelden(
        createwallet=rpc.RpcFehler("Database already exists.", -4),
        loadwallet=rpc.RpcFehler("already loaded", -35),
        listdescriptors={"descriptors": [
            {"desc": empfang + "#abcdefgh", "active": True, "range": [0, 1003],
             "timestamp": zeitstempel, "internal": False},
            {"desc": wechsel + "#abcdefgh", "active": True, "range": [0, 1001],
             "timestamp": zeitstempel, "internal": True},
        ]})
    return core, empfang, wechsel


def test_ein_frueheres_datum_sucht_ab_dort_noch_einmal():
    """Wer beim ersten Mal ein zu spaetes "benutzt seit" angab, dem fehlte
    die aeltere Geschichte -- und ein zweites Anmelden aenderte nichts, weil
    es nur lud. Jetzt sucht Core ab dem frueheren Datum noch einmal. Der
    Bereich schliesst den bisherigen ein, sonst lehnt Core ab."""
    core, empfang, wechsel = _core_mit_vorhandenem_konto(1_700_000_000)
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh", seit=1_600_000_000)
    [(params, wallet)] = core.gerufen("importdescriptors")
    assert wallet == lesewallet.walletname(TPUB_SCHLUESSEL, "wpkh")
    assert {(d["desc"].split("#")[0], d["timestamp"], tuple(d["range"]),
             d["internal"], d["active"]) for d in params[0]} == {
        (empfang, 1_600_000_000, (0, 1003), False, True),
        (wechsel, 1_600_000_000, (0, 1001), True, True)}


def test_ohne_datum_heisst_auch_beim_zweiten_mal_die_ganze_kette():
    core, _e, _w = _core_mit_vorhandenem_konto(1_700_000_000)
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh", seit=0)
    [(params, _wallet)] = core.gerufen("importdescriptors")
    assert all(d["timestamp"] == 0 for d in params[0])


@pytest.mark.parametrize("seit", [1_700_000_000, 1_800_000_000])
def test_ein_gleiches_oder_spaeteres_datum_sucht_nicht_noch_einmal(seit):
    """Was schon durchsucht ist, bleibt durchsucht -- ein spaeteres Datum
    kann nichts hinzufuegen."""
    core, _e, _w = _core_mit_vorhandenem_konto(1_700_000_000)
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh", seit=seit)
    assert not core.gerufen("importdescriptors")


def test_der_vorrat_wird_ausdruecklich_angegeben():
    """Ohne Angabe nimmt Core seinen Vorgabe-Vorrat und warnt ("Range not
    given, using default keypool range"). Lieber sagen, was gemeint ist."""
    core = _core_zum_anmelden()
    lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh")
    [(params, _w)] = core.gerufen("importdescriptors")
    assert all(d["range"] == [0, lesewallet.VORRAT - 1] for d in params[0])


def test_ein_fehlgeschlagener_import_wird_gemeldet():
    core = _core_zum_anmelden(importdescriptors=[
        {"success": False, "error": {"code": -5, "message": "kaputt"}},
        {"success": True}])
    with pytest.raises(lesewallet.LeseFehler):
        lesewallet.anmelden(core, TPUB_SCHLUESSEL, "wpkh")


def test_ein_schluessel_aus_dem_falschen_netz_wird_abgewiesen():
    """Ein Hauptnetz-Schluessel an einem Testknoten -- oder umgekehrt --
    ergaebe eine Wallet, die nie etwas findet. Lieber gleich sagen."""
    haupt = lesewallet.lies_schluessel(BIP84_ZPUB)
    core = _core_zum_anmelden(getblockchaininfo={"chain": "regtest"})
    with pytest.raises(lesewallet.SchluesselFehler) as fehler:
        lesewallet.anmelden(core, haupt, "wpkh")
    assert fehler.value.schluessel == "el_falsches_netz"
    assert not core.gerufen("createwallet")


@pytest.mark.parametrize("kette,netz,passt", [
    ("main", "main", True), ("main", "test", False),
    ("test", "test", True), ("testnet4", "test", True),
    ("signet", "test", True), ("regtest", "test", True),
    ("regtest", "main", False),
])
def test_welches_netz_zu_welcher_kette_passt(kette, netz, passt):
    assert lesewallet.netz_passt(kette, netz) is passt


def test_der_fortschritt_kommt_aus_getwalletinfo():
    core = Core(getwalletinfo={"scanning": {"duration": 12, "progress": 0.42}})
    assert lesewallet.fortschritt(core, "w") == 0.42
    core = Core(getwalletinfo={"scanning": False})
    assert lesewallet.fortschritt(core, "w") is None


def test_abmelden_entlaedt_und_nimmt_den_autostart_zurueck():
    core = Core(unloadwallet={})
    lesewallet.abmelden(core, "w")
    assert core.gerufen("unloadwallet") == [(("w", False), None)]


def test_abmelden_einer_nicht_geladenen_wallet_ist_kein_fehler():
    core = Core(unloadwallet=rpc.RpcFehler("not loaded", -18))
    lesewallet.abmelden(core, "w")


def test_laden_uebergeht_eine_schon_geladene_wallet():
    core = Core(loadwallet=rpc.RpcFehler("already loaded", -35))
    lesewallet.laden(core, "w")


def test_nur_eine_fehlende_wallet_gilt_als_nicht_vorhanden():
    assert lesewallet.gibt_es_nicht(rpc.RpcFehler("not found", -18))
    assert not lesewallet.gibt_es_nicht(rpc.RpcFehler("rescanning", -4))
    assert not lesewallet.gibt_es_nicht(rpc.RpcFehler("ohne Code"))


# ── Der Leser: aus Cores Wallets wird das Kontobuch ────────────────────────
#
# Die Antworten haben die Form, die an der Regtest-Kette (Core v31.1) zu
# sehen war -- auch darin, was FEHLT: eine Transaktion im Mempool hat bei
# getrawtransaction ..., 2 kein "prevout".

def _sh(spk):
    return hashlib.sha256(bytes.fromhex(spk)).digest()[::-1].hex()


EIGEN_A = "0014" + "a1" * 20       # Empfangsadresse
EIGEN_W = "0014" + "c3" * 20       # Wechseladresse
FREMD = "0014" + "f9" * 20
TX1, TX2, TX3 = "11" * 32, "22" * 32, "33" * 32
QUELLE = "99" * 32


def _aus(n, spk, btc):
    return {"n": n, "value": btc, "scriptPubKey": {"hex": spk}}


ROH = {
    # Zahlung an uns, bestaetigt (Block 104, Stelle 1).
    (TX1, 2): {"txid": TX1, "vin": [{"txid": QUELLE, "vout": 0, "prevout": {
        "value": 1.0, "scriptPubKey": {"hex": FREMD}}}],
        "vout": [_aus(0, FREMD, 0.4999), _aus(1, EIGEN_A, 0.5)]},
    # Wir geben aus, bestaetigt: 0,5 von EIGEN_A -> 0,1 fort, Rest Wechsel.
    (TX2, 2): {"txid": TX2, "vin": [{"txid": TX1, "vout": 1, "prevout": {
        "value": 0.5, "scriptPubKey": {"hex": EIGEN_A}}}],
        "vout": [_aus(0, EIGEN_W, 0.3999718), _aus(1, FREMD, 0.1)]},
    # Wir geben im Mempool aus -- OHNE prevout, wie bei Core.
    (TX3, 1): {"txid": TX3, "vin": [{"txid": TX2, "vout": 0}],
               "vout": [_aus(0, FREMD, 0.2), _aus(1, EIGEN_W, 0.1999)]},
    (TX2, 1): {"txid": TX2, "vout": [_aus(0, EIGEN_W, 0.3999718),
                                     _aus(1, FREMD, 0.1)]},
}


def _eintrag(txid, kategorie, vout, konf, hoehe=None, stelle=None):
    e = {"txid": txid, "category": kategorie, "vout": vout,
         "confirmations": konf}
    if hoehe is not None:
        e.update(blockheight=hoehe, blockindex=stelle)
    return e


# Wie Core: Wechselgeld steht NICHT als "receive" da -- listtransactions
# blendet es aus. Genau daran ist die erste Fassung gescheitert: sie nahm die
# Empfangseintraege als Liste der eigenen Skripte und verlor das Wechselgeld
# (an der Regtest-Kette gefunden, 28.09.2026: 0,1499718 fehlten).
EINTRAEGE = [
    _eintrag(TX1, "receive", 1, 3, 104, 1),
    _eintrag(TX2, "send", 1, 2, 105, 2),
    _eintrag(TX3, "send", 0, 0),
]

# Was die Deskriptoren der Wallet ableiten: Empfang #0 und Wechsel #0.
DESKRIPTOREN = {"descriptors": [
    {"desc": "wpkh(tpubX/0/*)#aaaa", "active": True, "internal": False,
     "range": [0, 1]},
    {"desc": "wpkh(tpubX/1/*)#bbbb", "active": True, "internal": True,
     "range": [0, 1]},
]}
ADRESSEN = {"wpkh(tpubX/0/*)#aaaa": ["adr-a0", "adr-a1"],
            "wpkh(tpubX/1/*)#bbbb": ["adr-w0", "adr-w1"]}
SKRIPTE = {"adr-a0": EIGEN_A, "adr-a1": "0014" + "a2" * 20,
           "adr-w0": EIGEN_W, "adr-w1": "0014" + "c4" * 20}


def _core_zum_lesen(eintraege=EINTRAEGE, mempool=None, seite=None):
    def listtransactions(_label, anzahl, ab, _nur_lesen, wallet=None):
        return eintraege[ab:ab + anzahl]

    def getrawtransaction(txid, stufe, wallet=None):
        return ROH[(txid, stufe)]

    def getmempoolentry(txid, wallet=None):
        eintrag = (mempool or {}).get(txid)
        if eintrag is None:
            return rpc.RpcFehler("Transaction not in mempool", -5)
        return eintrag
    def deriveaddresses(desc, bereich, wallet=None):
        return ADRESSEN[desc][bereich[0]:bereich[1] + 1]

    def validateaddress(adresse, wallet=None):
        return {"isvalid": True, "scriptPubKey": SKRIPTE[adresse]}

    return Core(listtransactions=listtransactions,
                getrawtransaction=getrawtransaction,
                getmempoolentry=getmempoolentry,
                listdescriptors=DESKRIPTOREN,
                deriveaddresses=deriveaddresses,
                validateaddress=validateaddress)


MEMPOOL = {TX3: {"depends": [], "fees": {"base": 0.0000282}}}


def _lesen(core, wallets=("w1",)):
    return lesewallet.Leser(core, lambda: list(wallets)).lesen()


def test_bestaetigte_haben_hoehe_und_stelle_aus_der_wallet():
    buch, _eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL))
    assert buch.geschichte(_sh(EIGEN_A)) == [
        {"tx_hash": TX1, "height": 104}, {"tx_hash": TX2, "height": 105}]


def test_eine_ausgabe_steht_bei_der_adresse_von_der_sie_kam():
    buch, _eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL))
    assert buch.guthaben(_sh(EIGEN_A)) == {"confirmed": 0, "unconfirmed": 0}


def test_bei_einer_ausgabe_im_mempool_wird_der_vorgaenger_nachgeschlagen():
    buch, _eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL))
    assert buch.guthaben(_sh(EIGEN_W)) == {
        "confirmed": 39_997_180, "unconfirmed": 19_990_000 - 39_997_180}
    assert buch.mempool(_sh(EIGEN_W)) == [
        {"tx_hash": TX3, "height": 0, "fee": 2820}]


def test_ein_unbestaetigter_vorgaenger_macht_die_hoehe_minus_eins():
    buch, _eigene = _lesen(_core_zum_lesen(mempool={
        TX3: {"depends": [TX2], "fees": {"base": 0.0000282}}}))
    assert buch.mempool(_sh(EIGEN_W))[0]["height"] == -1


def test_was_nicht_mehr_im_mempool_ist_faellt_heraus():
    """Verdraengt oder verworfen: die Wallet listet sie noch mit 0
    Bestaetigungen, in Kette und Mempool steht sie aber nicht mehr."""
    buch, _eigene = _lesen(_core_zum_lesen(mempool={}))
    assert TX3 not in [e["tx_hash"] for e in buch.geschichte(_sh(EIGEN_W))]


def test_eine_verdraengte_transaktion_zaehlt_nicht():
    eintraege = EINTRAEGE + [_eintrag("44" * 32, "receive", 0, -1)]
    buch, _eigene = _lesen(_core_zum_lesen(eintraege, mempool=MEMPOOL))
    assert "44" * 32 not in {e["tx_hash"] for s in buch.beruehrt()
                             for e in buch.geschichte(s)}


def test_eigen_ist_was_die_deskriptoren_ableiten_auch_das_wechselgeld():
    """Auch Adressen ohne Empfangseintrag -- das Wechselgeld -- und auch
    noch unbenutzte. Nicht das Ziel einer Ausgabe."""
    _buch, eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL))
    assert eigene == {_sh(s) for s in SKRIPTE.values()}
    assert _sh(FREMD) not in eigene


def test_die_ableitung_wird_gemerkt_solange_der_bereich_gleich_bleibt():
    core = _core_zum_lesen(mempool=MEMPOOL)
    leser = lesewallet.Leser(core, lambda: ["w1"])
    leser.lesen()
    leser.lesen()
    assert len(core.gerufen("deriveaddresses")) == 2   # je Kette einmal


def test_waechst_der_vorrat_wird_neu_abgeleitet():
    """Core fuellt den Vorrat selbst nach (gemessen: nach Adresse #990
    reichte er bis #1990). Dann muss die Liste der eigenen Skripte mit."""
    core = _core_zum_lesen(mempool=MEMPOOL)
    leser = lesewallet.Leser(core, lambda: ["w1"])
    leser.lesen()
    core.antworten["listdescriptors"] = {"descriptors": [
        dict(DESKRIPTOREN["descriptors"][0], range=[0, 0]),
        DESKRIPTOREN["descriptors"][1]]}
    _buch, eigene = leser.lesen()
    assert len(core.gerufen("deriveaddresses")) == 3
    assert _sh("0014" + "a2" * 20) not in eigene


def test_die_wallet_wird_seitenweise_gelesen(monkeypatch):
    monkeypatch.setattr(lesewallet, "SEITE", 1)
    core = _core_zum_lesen(mempool=MEMPOOL)
    buch, _eigene = _lesen(core)
    # drei volle Seiten zu je einem Eintrag, dann eine leere
    assert len(core.gerufen("listtransactions")) == 4
    assert buch.guthaben(_sh(EIGEN_A))["confirmed"] == 0


def test_eine_zerlegte_bestaetigte_transaktion_wird_gemerkt():
    core = _core_zum_lesen(mempool=MEMPOOL)
    leser = lesewallet.Leser(core, lambda: ["w1"])
    leser.lesen()
    vorher = len(core.gerufen("getrawtransaction"))
    leser.lesen()
    assert len(core.gerufen("getrawtransaction")) == vorher


def test_dieselbe_transaktion_aus_zwei_wallets_zaehlt_einmal():
    buch, _eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL), ("w1", "w2"))
    assert buch.geschichte(_sh(EIGEN_A)) == [
        {"tx_hash": TX1, "height": 104}, {"tx_hash": TX2, "height": 105}]


def test_die_wallets_werden_mit_ihrem_pfad_gefragt():
    core = _core_zum_lesen(mempool=MEMPOOL)
    _lesen(core, ("w1", "w2"))
    assert {w for _p, w in core.gerufen("listtransactions")} == {"w1", "w2"}


def test_ein_fehlender_vorgaenger_ist_ein_fehler_kein_stilles_auslassen():
    """Ein uebersprungener Eingang verfaelschte das Guthaben -- lieber gar
    kein neuer Stand als ein falscher."""
    core = _core_zum_lesen(mempool=MEMPOOL)
    ROH_OHNE = dict(ROH)
    ROH_OHNE[(TX2, 1)] = {"txid": TX2, "vout": []}
    core.antworten["getrawtransaction"] = lambda txid, stufe, wallet=None: \
        ROH_OHNE[(txid, stufe)]
    with pytest.raises(lesewallet.LeseFehler):
        _lesen(core)


# ── Eine Wallet, die es in Core nicht gibt ─────────────────────────────────
#
# Die Suchen laufen nacheinander. Wer wartet, hat in Core noch keine Wallet;
# startet die Anwendung in der Zeit neu, steht das Konto in der Liste, die
# Wallet fehlt. Das darf das Lesen der anderen nicht aufhalten -- aber nur,
# wenn SICHER ist, dass es sie nicht gibt.

def _core_mit_fehlender(fehler=-18):
    core = _core_zum_lesen(mempool=MEMPOOL)

    def listdescriptors(wallet=None):
        if wallet == "weg":
            return rpc.RpcFehler("Requested wallet does not exist or is not "
                                 "loaded", fehler)
        return DESKRIPTOREN
    core.antworten["listdescriptors"] = listdescriptors
    return core


def test_eine_wallet_die_es_nicht_gibt_haelt_die_anderen_nicht_auf():
    gemeldet = []
    buch, eigene = lesewallet.Leser(
        _core_mit_fehlender(), lambda: ["weg", "w1"],
        fehlt=lambda name: gemeldet.append(name) or True).lesen()
    allein_buch, allein_eigene = _lesen(_core_zum_lesen(mempool=MEMPOOL))
    assert gemeldet == ["weg"]
    assert eigene == allein_eigene
    assert buch.geschichte(_sh(EIGEN_A)) == allein_buch.geschichte(_sh(EIGEN_A))


def test_ist_nicht_sicher_dass_es_sie_nicht_gibt_bleibt_es_beim_fehler():
    """Lieber kein neuer Stand als einer, in dem ein Konto still fehlt."""
    with pytest.raises(rpc.RpcFehler):
        lesewallet.Leser(_core_mit_fehlender(), lambda: ["weg", "w1"],
                         fehlt=lambda name: False).lesen()


def test_ohne_rueckfrage_bleibt_eine_fehlende_wallet_ein_fehler():
    with pytest.raises(rpc.RpcFehler):
        lesewallet.Leser(_core_mit_fehlender(), lambda: ["weg", "w1"]).lesen()


def test_andere_fehler_einer_wallet_werden_nicht_uebergangen():
    gemeldet = []
    with pytest.raises(rpc.RpcFehler):
        lesewallet.Leser(_core_mit_fehlender(-4), lambda: ["weg", "w1"],
                         fehlt=lambda name: gemeldet.append(name) or True
                         ).lesen()
    assert gemeldet == []
