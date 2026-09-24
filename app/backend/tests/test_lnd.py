"""Die Anbindung an LND.

Der wichtigste Fall ist der langweiligste: LND laeuft noch gar nicht. Das ist
ueber Tage der Normalzustand -- erst muss die Kette fertig sein -- und die
Oberflaeche darf daran nicht zerbrechen.
"""
import base64
import json
import ssl
import urllib.error
from io import BytesIO
from pathlib import Path

import pytest

from satcortex import lnd


class Antwort:
    """Ein urlopen-Ergebnis, wie es der Kontextmanager erwartet."""

    def __init__(self, nutzlast):
        self._daten = json.dumps(nutzlast).encode("utf-8")

    def read(self):
        return self._daten

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _knoten(tmp_path, mit_zertifikat=True, mit_macaroon=False):
    zert = tmp_path / "tls.cert"
    if mit_zertifikat:
        zert.write_text("nicht echt, wird nicht geparst")
    mac = tmp_path / "data" / "chain" / "bitcoin" / "mainnet"
    if mit_macaroon:
        mac.mkdir(parents=True)
        (mac / "readonly.macaroon").write_bytes(b"\x00\x01\xff")
    return lnd.Knoten(zertifikat=zert, macaroons=mac)


def _ohne_tls(monkeypatch):
    """Den TLS-Kontext ausklammern -- geprueft wird hier die Logik daneben."""
    monkeypatch.setattr(lnd.Knoten, "_kontext", lambda self: None)


def test_ohne_zertifikat_ist_lnd_einfach_aus(tmp_path, monkeypatch):
    """Vor LNDs erstem Start gibt es kein Zertifikat. Ohne diesen Fall liefe
    jeder Aufruf in einen TLS-Fehler, dessen Wortlaut niemandem etwas sagt --
    und die Uebersicht zeigte einen Fehler statt "laeuft noch nicht"."""
    def platzt(*a, **k):
        raise AssertionError("es darf gar nicht erst gefragt werden")
    monkeypatch.setattr(lnd.urllib.request, "urlopen", platzt)

    d = lnd.zustand(_knoten(tmp_path, mit_zertifikat=False))
    assert d == {"da": False, "stand": "aus", "roh": None}


def test_zustand_vor_der_wallet(tmp_path, monkeypatch):
    """NON_EXISTING ist kein Fehler, sondern der Anfang. Der State-Dienst
    antwortet genau dafuer -- ohne Macaroon, das es noch gar nicht gibt."""
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["url"] = anfrage.full_url
        gesehen["kopf"] = dict(anfrage.header_items())
        return Antwort({"state": "NON_EXISTING"})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.zustand(_knoten(tmp_path))
    assert d["da"] is True and d["stand"] == "keine_wallet"
    assert gesehen["url"] == "https://lnd:8080/v1/state"
    # Kein Macaroon im Kopf: es gibt noch keines, und der Aufruf braucht keins.
    assert not [k for k in gesehen["kopf"] if k.lower().startswith("grpc")]


def test_ruf_kann_auch_loeschen(tmp_path, monkeypatch):
    """Ein Wachturm wird mit DELETE ausgetragen -- ruf kannte bis zum
    15.09.2026 nur GET und POST."""
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["rumpf"] = anfrage.data
        return Antwort({})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    knoten = _knoten(tmp_path, mit_macaroon=True)
    assert knoten.ruf("/v2/watchtower/client/abc", methode="DELETE") == {}
    assert gesehen == {"methode": "DELETE", "rumpf": None}
    # Ohne Angabe bleibt alles, wie es war.
    knoten.ruf("/v1/getinfo")
    assert gesehen["methode"] == "GET"


@pytest.mark.parametrize("roh,erwartet", [
    ("NON_EXISTING", "keine_wallet"),
    ("LOCKED", "gesperrt"),
    ("UNLOCKED", "startet"),
    ("RPC_ACTIVE", "startet"),
    ("SERVER_ACTIVE", "bereit"),
    ("WAS_AUCH_IMMER", "unbekannt"),
])
def test_alle_zustaende_werden_uebersetzt(tmp_path, monkeypatch, roh, erwartet):
    _ohne_tls(monkeypatch)
    monkeypatch.setattr(lnd.urllib.request, "urlopen",
                        lambda *a, **k: Antwort({"state": roh}))
    assert lnd.zustand(_knoten(tmp_path))["stand"] == erwartet


def test_lnd_nicht_erreichbar_ist_kein_absturz(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)

    def kaputt(*a, **k):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr(lnd.urllib.request, "urlopen", kaputt)
    assert lnd.zustand(_knoten(tmp_path)) == {"da": False, "stand": "aus",
                                              "roh": None}


def test_das_macaroon_geht_als_hex_in_den_kopf(tmp_path, monkeypatch):
    """LND erwartet es hex-kodiert im Kopf "Grpc-Metadata-macaroon" --
    so steht es in docs/macaroons.md."""
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen.update({k.lower(): v for k, v in anfrage.header_items()})
        return Antwort({"ok": True})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    k = _knoten(tmp_path, mit_macaroon=True)
    k.ruf("/v1/getinfo")
    assert gesehen["grpc-metadata-macaroon"] == "0001ff"


def test_ohne_macaroon_wird_gar_nicht_erst_gefragt(tmp_path, monkeypatch):
    """Vor der Wallet-Anlage gibt es keine Macaroons. Ein Aufruf, der eines
    braucht, soll das sagen -- statt LND mit einer Anfrage ohne Berechtigung
    zu behelligen und einen 500er zurueckzubekommen."""
    _ohne_tls(monkeypatch)

    def platzt(*a, **k):
        raise AssertionError("es darf gar nicht erst gefragt werden")
    monkeypatch.setattr(lnd.urllib.request, "urlopen", platzt)

    with pytest.raises(lnd.NichtErreichbar, match="keine Wallet"):
        _knoten(tmp_path).ruf("/v1/getinfo")


def test_der_grund_einer_ablehnung_bleibt_erhalten(tmp_path, monkeypatch):
    """LND legt den Grund in den Rumpf. Ihn wegzuwerfen und nur "500" zu
    melden waere die haeufigste Art, eine Fehlersuche zu verlaengern."""
    _ohne_tls(monkeypatch)

    def urlopen(*a, **k):
        raise urllib.error.HTTPError(
            "https://lnd:8080/v1/x", 500, "Internal", {},
            BytesIO(json.dumps({"message": "wallet locked"}).encode()))
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    with pytest.raises(lnd.LndFehler, match="wallet locked"):
        _knoten(tmp_path, mit_macaroon=True).ruf("/v1/getinfo")


def test_die_tls_pruefung_wird_nicht_abgeschaltet(tmp_path):
    """Selbstsigniert heisst nicht ungeprueft: wir kennen die Datei. Die
    Pruefung abzuschalten waere bequemer und genau der Fehler -- im
    Compose-Netz kann mehr als ein Container antworten.

    Geprueft werden die beiden Schalter, die dabei umgelegt wuerden. Ein
    erster Anlauf schrieb stattdessen eine leere Zertifikatsdatei und
    erwartete einen Fehler -- der kam auch, aber weil die Datei leer war,
    nicht weil geprueft wird. Ein gruener Test, der nichts belegt."""
    vorrat = ssl.get_default_verify_paths().cafile
    if not vorrat or not Path(vorrat).exists():
        pytest.skip("kein CA-Vorrat auf diesem System")
    zert = tmp_path / "tls.cert"
    zert.write_bytes(Path(vorrat).read_bytes())

    kontext = lnd.Knoten(zertifikat=zert)._kontext()
    assert kontext.verify_mode is ssl.CERT_REQUIRED
    assert kontext.check_hostname is True
    # Und: es wird gegen UNSERE Datei geprueft, nicht gegen den Systemvorrat.
    assert kontext.cert_store_stats()["x509_ca"] > 0


def test_der_macaroon_pfad_folgt_lnds_aufbau():
    """lnddir/data/chain/bitcoin/mainnet/ -- so steht es in docs/macaroons.md.
    Ein falscher Pfad faellt sonst erst auf, wenn eine Wallet existiert."""
    assert lnd.MACAROONS == lnd.LNDDIR / "data" / "chain" / "bitcoin" / "mainnet"
    assert lnd.ZERTIFIKAT == lnd.LNDDIR / "tls.cert"


# ── Die Lightning-Ansichten ────────────────────────────────────────────────
#
# LND schickt alle Betraege und Kennungen als ZEICHENKETTEN -- es sind
# 64-Bit-Ganzzahlen, und JavaScript kann die nicht genau darstellen. Wer sie
# ungeprueft weiterreicht, bekommt "1000000" neben "999999" sortiert und
# Summen, die nicht stimmen.

class FakeRuf:
    def __init__(self, antworten):
        self.antworten = antworten
        self.gerufen = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.gerufen.append((pfad, daten))
        return self.antworten.get(pfad.split("?")[0], {})


def test_betraege_kommen_als_zahlen_heraus():
    k = FakeRuf({"/v1/channels": {"channels": [{
        "active": True, "peer_alias": "ACINQ", "remote_pubkey": "03ab",
        "channel_point": "abc:0", "capacity": "5000000",
        "local_balance": "2000000", "remote_balance": "3000000",
        "total_satoshis_sent": "100", "total_satoshis_received": "250",
        "lifetime": "86400", "uptime": "86000", "private": False}]}})
    kanal = lnd.kanaele(k)[0]
    assert kanal["kapazitaet"] == 5_000_000 and isinstance(kanal["kapazitaet"], int)
    assert kanal["hier"] == 2_000_000
    assert kanal["anteil_hier"] == 0.4


def test_ein_kanal_nennt_was_die_gegenstelle_gleichzeitig_annimmt():
    """DER BEFUND VOM 24.09.2026: LDK nimmt je Kanal nur 25 % der Kapazitaet
    gleichzeitig an. Das steht in LOCAL_constraints -- nachgelesen, nicht
    geraten: funding/manager.go gibt das max_htlc_value_in_flight der
    Gegenstelle an CommitConstraints, das legt es in UNSERE Konfiguration,
    und lnwallet/channel.go prueft unsere eigenen HTLCs gegen genau die
    (v0.21.3-beta)."""
    k = FakeRuf({"/v1/channels": {"channels": [{
        "active": True, "capacity": "200000", "local_balance": "180000",
        "local_constraints": {"max_pending_amt_msat": "50000000"},
        "remote_constraints": {"max_pending_amt_msat": "190000000"}},
        {"active": True, "capacity": "150000", "local_balance": "0"}]}})
    mit, ohne = sorted(lnd.kanaele(k), key=lambda x: -x["kapazitaet"])
    assert mit["hinaus_hoechstens"] == 50_000
    # Was in EINEN Durchgang passt: Betrag plus Gebuehrengrenze darunter.
    b = mit["umschichten_hoechstens"]
    assert b + lnd.gebuehrgrenze(b) <= 50_000
    assert (b + 1) + lnd.gebuehrgrenze(b + 1) > 50_000
    # Ohne Angabe: unbekannt, nicht null. Null hiesse "geht gar nicht".
    assert ohne["hinaus_hoechstens"] is None
    assert ohne["umschichten_hoechstens"] is None


def test_ohne_alias_lookup_saehe_man_nur_schluessel():
    """LNDs eigene Beschreibung: "It is turned off by default." Ohne das steht
    in der Liste ueberall nur ein Schluessel aus 66 Zeichen."""
    k = FakeRuf({"/v1/channels": {"channels": []}})
    lnd.kanaele(k)
    assert "peer_alias_lookup=true" in k.gerufen[0][0]


def test_stille_kanaele_stehen_oben():
    """Ein Kanal, der nicht aktiv ist, ist das, was Aufmerksamkeit braucht."""
    k = FakeRuf({"/v1/channels": {"channels": [
        {"active": True, "capacity": "9000000"},
        {"active": False, "capacity": "1000000"},
        {"active": True, "capacity": "2000000"}]}})
    liste = lnd.kanaele(k)
    assert liste[0]["aktiv"] is False
    assert [x["kapazitaet"] for x in liste[1:]] == [2_000_000, 9_000_000]


def test_ein_kanal_ohne_kapazitaet_teilt_nicht_durch_null():
    k = FakeRuf({"/v1/channels": {"channels": [
        {"active": True, "capacity": "0", "local_balance": "0"}]}})
    assert lnd.kanaele(k)[0]["anteil_hier"] == 0.0


# ── Kanaele im Aufbau und im Abbau (24.09.2026) ────────────────────────────
#
# Aus dem Betrieb: "ich habe ja jetzt einen kanal geoeffnet zu den anderen
# partner B ... nur warum seh ich das nur in wallet und nicht unter kanal ?"
# /v1/channels kennt nur OFFENE Kanaele. Bis die Gegenstelle genug
# Bestaetigungen hat, steht ein neuer Kanal nur in /v1/channels/pending --
# Feldnamen aus lightning.swagger.json, v0.21.3-beta.

GEGEN = "03" + "ab" * 32


def _ausstehend(**mehr):
    antworten = {"/v1/channels/pending": {
        "pending_open_channels": [{
            "channel": {"remote_node_pub": GEGEN,
                        "channel_point": "ee" * 32 + ":0",
                        "capacity": "100000", "local_balance": "99000",
                        "remote_balance": "0", "initiator": "INITIATOR_LOCAL",
                        "private": False},
            "confirmations_until_active": 1, "confirmation_height": 900000,
            "funding_expiry_blocks": 2011}],
        "waiting_close_channels": [{
            "channel": {"remote_node_pub": "02" + "cd" * 32,
                        "channel_point": "aa:1", "capacity": "200000",
                        "local_balance": "150000", "remote_balance": "50000"},
            "limbo_balance": "150000", "closing_txid": "cc" * 32,
            "blocks_til_close_confirmed": 3}],
        "pending_force_closing_channels": [{
            "channel": {"remote_node_pub": "02" + "ef" * 32,
                        "channel_point": "bb:0", "capacity": "300000",
                        "local_balance": "100000", "remote_balance": "0"},
            "closing_txid": "dd" * 32, "limbo_balance": "100000",
            "blocks_til_maturity": 140}],
    }, f"/v1/graph/node/{GEGEN}": {"node": {"alias": "Beispielknoten"}}}
    antworten.update(mehr)
    return FakeRuf(antworten)


def test_ein_kanal_im_aufbau_steht_mit_seinen_bestaetigungen_da():
    k = _ausstehend()
    liste = lnd.ausstehende_kanaele(k)
    auf = [x for x in liste if x["stand"] == "oeffnet"]
    assert auf == [{
        "stand": "oeffnet", "gegenstelle": "Beispielknoten", "kennung": GEGEN,
        "punkt": "ee" * 32 + ":0", "kapazitaet": 100_000, "hier": 99_000,
        "drueben": 0, "privat": False, "von_uns": True,
        "noch_bloecke": 1, "txid": "ee" * 32}]


def test_schliessende_kanaele_verschwinden_nicht_aus_der_ansicht():
    """Auch beim Schliessen faellt ein Kanal aus /v1/channels heraus -- und
    das Geld darin ist in dieser Zeit weder im Kanal noch in der Wallet."""
    liste = lnd.ausstehende_kanaele(_ausstehend())
    zu = {x["stand"]: x for x in liste if x["stand"] != "oeffnet"}
    assert zu["schliesst"]["noch_bloecke"] == 3
    assert zu["schliesst"]["txid"] == "cc" * 32
    assert zu["schliesst"]["gesperrt"] == 150_000
    assert zu["zwangsschluss"]["noch_bloecke"] == 140
    assert zu["zwangsschluss"]["gesperrt"] == 100_000


def test_ohne_graph_eintrag_bleibt_die_kennung():
    """Eine Gegenstelle ohne Kanal steht nicht im Graphen -- dann eben die
    Kennung, aber der Kanal fehlt deswegen nicht."""
    k = _ausstehend(**{f"/v1/graph/node/{GEGEN}": {}})
    auf = lnd.ausstehende_kanaele(k)[0]
    assert auf["gegenstelle"] == "" and auf["kennung"] == GEGEN


def test_nichts_im_aufbau_heisst_leere_liste():
    assert lnd.ausstehende_kanaele(FakeRuf({})) == []


def test_die_sicherung_nennt_ihre_kanaele_lesbar():
    """Die Kanalpunkte sind der Fingerabdruck der Sicherung (der Klumpen ist
    bei jeder Ausfuhr ein anderer). funding_txid_bytes steht in interner
    Reihenfolge -- rueckwaerts zu dem, was ein Explorer zeigt."""
    import base64 as b64
    # Ausgedacht -- nur unsymmetrisch genug, dass eine vergessene Umkehrung
    # auffaellt.
    txid = "0123456789abcdef" * 4
    roh = b64.b64encode(bytes.fromhex(txid)[::-1]).decode()
    k = FakeRuf({"/v1/channels/backup": {"multi_chan_backup": {
        "multi_chan_backup": "AAAA",
        "chan_points": [{"funding_txid_bytes": roh, "output_index": 1},
                        {"funding_txid_str": "ab" * 32}]}}})
    d = lnd.sicherung_holen(k)
    assert d["punkte"] == [f"{txid}:1", "ab" * 32 + ":0"]
    assert d["kanaele"] == 2


def test_guthaben_zaehlt_kette_und_kanaele_nicht_zusammen():
    """Was in einem Kanal liegt, ist gebunden. Was auf der ANDEREN Seite
    liegt, ist gar nicht deins -- aber genau das, was du empfangen kannst."""
    k = FakeRuf({
        "/v1/balance/blockchain": {"total_balance": "150000",
                                   "confirmed_balance": "100000"},
        "/v1/balance/channels": {"local_balance": {"sat": "42000", "msat": "0"},
                                 "remote_balance": {"sat": "58000"}}})
    d = lnd.guthaben(k)
    assert d == {"kette_gesamt": 150000, "kette_bestaetigt": 100000,
                 "kanal_hier": 42000, "kanal_drueben": 58000}


def test_weiterleitungen_werden_summiert():
    k = FakeRuf({"/v1/switch": {"forwarding_events": [
        {"timestamp": "1780000000", "amt_out": "10000", "fee_msat": "1500",
         "peer_alias_in": "A", "peer_alias_out": "B"},
        {"timestamp": "1780000100", "amt_out": "20000", "fee_msat": "2500",
         "peer_alias_in": "B", "peer_alias_out": "C"}]}})
    d = lnd.weiterleitungen(k)
    assert d["anzahl"] == 2 and d["menge"] == 30000 and d["gebuehr_msat"] == 4000
    assert d["letzte"][0]["von"] == "B", "die neueste zuerst"


def test_die_uebersicht_kommt_auch_ohne_kanaele_zurecht():
    """Am Anfang ist das die interessantere Haelfte: bin ich sichtbar?"""
    k = FakeRuf({"/v1/getinfo": {
        "identity_pubkey": "03ab", "alias": "Testknoten", "color": "#f7931a",
        "uris": ["03ab@1.2.3.4:9735"], "synced_to_chain": True}})
    d = lnd.uebersicht(k)
    assert d["alias"] == "Testknoten" and d["adressen"] == ["03ab@1.2.3.4:9735"]
    assert d["kanaele_aktiv"] == 0 and d["kette_aktuell"] is True


# ── Zeitlimit ist nicht dasselbe wie abwesend ─────────────────────────────
#
# Auf der bitcoind-Seite kostete diese Verwechslung Tage: die Oberflaeche
# meldete "startet noch", waehrend der Knoten lief und nur beschaeftigt war.
# In lnd.py stand sie am 01.09.2026 noch offen -- ausgerechnet dort, wo
# Warten der Normalfall ist: nach dem Entsperren laedt LND den Kanalgraphen.


def test_zeitlimit_heisst_beschaeftigt(monkeypatch, tmp_path):
    import socket
    import urllib.request
    from satcortex import lnd

    zert = tmp_path / "tls.cert"
    zert.write_text("x")
    knoten = lnd.Knoten(zertifikat=zert, macaroons=tmp_path)
    monkeypatch.setattr(lnd.Knoten, "_kontext", lambda self: None)

    def zeit_ab(*_a, **_kw):
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", zeit_ab)

    with pytest.raises(lnd.Beschaeftigt):
        knoten.ruf("/v1/state", macaroon="")


def test_abgelehnte_verbindung_bleibt_nicht_erreichbar(monkeypatch, tmp_path):
    import urllib.error
    import urllib.request
    from satcortex import lnd

    zert = tmp_path / "tls.cert"
    zert.write_text("x")
    knoten = lnd.Knoten(zertifikat=zert, macaroons=tmp_path)
    monkeypatch.setattr(lnd.Knoten, "_kontext", lambda self: None)

    def abgelehnt(*_a, **_kw):
        raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
    monkeypatch.setattr(urllib.request, "urlopen", abgelehnt)

    with pytest.raises(lnd.NichtErreichbar) as gefangen:
        knoten.ruf("/v1/state", macaroon="")
    assert not isinstance(gefangen.value, lnd.Beschaeftigt)


def test_der_graph_wird_nicht_unbegrenzt_befragt(monkeypatch):
    """Bei vielen Gegenstellen liefe sonst eine Anfrage der Oberflaeche in
    die Summe aller Zeitlimits."""
    from satcortex import lnd

    viele = [{"kennung": f"{n:066x}", "kapazitaet": 1000 - n,
              "gegenstelle": f"knoten{n}"} for n in range(60)]
    monkeypatch.setattr(lnd, "kanaele", lambda _k: viele)

    gefragt = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        gefragt.append((pfad, zeitlimit))
        return {"node": {"alias": "x", "addresses": []}}
    monkeypatch.setattr(lnd.Knoten, "ruf", ruf)

    raus = lnd.gegenstellen(lnd.Knoten())
    assert len(raus) == 60, "gezeigt werden alle -- gefragt wird nur oben"
    assert len(gefragt) == lnd.HOECHSTENS_GRAPHFRAGEN
    assert all(z == lnd.GRAPH_ZEITLIMIT_SEKUNDEN for _p, z in gefragt)
    # Und zwar die groessten: die Karte zeichnet nach Kapazitaet.
    assert raus[0]["kapazitaet"] > raus[-1]["kapazitaet"]


def test_der_zeitpunkt_kommt_aus_dem_nicht_veralteten_feld():
    """LND markiert "timestamp" als veraltet ("Deprecated by timestamp_ns").

    Nachgeschlagen am 03.09.2026 in der Referenz von Lightning Labs. Das Feld
    steht heute noch drin -- aber wenn es verschwindet, staende bei jeder
    Weiterleitung der 1. Januar 1970, und niemand wuesste warum.
    """
    class Attrappe:
        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            return {"forwarding_events": [{
                "timestamp": "1", "timestamp_ns": "1788400000000000000",
                "amt_out": "1000", "fee_msat": "500",
                "peer_alias_in": "A", "peer_alias_out": "B"}]}

    d = lnd.weiterleitungen(Attrappe())
    assert d["letzte"][0]["zeitpunkt"] == 1_788_400_000


def test_ohne_nanosekunden_gilt_das_alte_feld():
    """Eine aeltere LND-Fassung kennt vielleicht nur das alte. Dann ist das
    alte richtig -- und nicht null."""
    class Alt:
        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            return {"forwarding_events": [{
                "timestamp": "1788400000", "amt_out": "1000",
                "fee_msat": "500"}]}

    d = lnd.weiterleitungen(Alt())
    assert d["letzte"][0]["zeitpunkt"] == 1_788_400_000


# ── Sich gegenueber einem Dienst ausweisen (04.09.2026) ─────────────────────
#
# Der Betreiber: "was ich auch gesehen habe, das mann im LightningNetwork+ sich
# signieren muss ... ich hoffe das unsere knoten dann auch alle notwendingen
# funktionen beherscht die wir brauchen um uns groessere netzwerke
# anzuschliessen."
#
# Er hat richtig hingesehen: message:write fehlte in unserem eigenen
# Macaroon. LNDs rpcserver.go, v0.21.3-beta:
#   "/lnrpc.Lightning/SignMessage": {{Entity: "message", Action: "write"}}
# Ohne dieses Recht haette sich die Anwendung bei keiner solchen Stelle
# ausweisen koennen.

def test_das_recht_zum_unterschreiben_ist_da():
    assert ("message", "write") in lnd.EIGENE_RECHTE


def test_onchain_write_ist_das_schwerste_recht_in_der_liste():
    """Bis zum 10.09.2026 stand hier das Gegenteil, mit guter Begruendung:
    onchain:write erlaubt laut LNDs Rechtetabelle sowohl Kanaele oeffnen als
    auch Coins senden -- LND trennt das nicht, und ein Macaroon kennt keine
    Betragsgrenze.

    Es ist jetzt drin, aus die Bedingung des Betreibers vom 30.08.2026: "ich werde nix
    dahin ueberweisen solange ich es nicht zurueck schicken kann". Eine
    Wallet, aus der man nicht wieder herauskommt, ist keine.

    Was den Ausschlag gab: fuer jemanden mit der PLATTE aendert es nichts --
    dort liegt ohnehin LNDs admin.macaroon. Fuer eine uebernommene SITZUNG
    aendert es alles, und genau dagegen steht seit demselben Tag die PIN.

    Der Test bleibt stehen, damit die Entscheidung eine bewusste bleibt: er
    faellt, wenn jemand das Recht wieder herausnimmt (dann faellt das Senden
    mit weg) -- und er verbietet weiterhin die Rechte, die admin auf Umwegen
    waeren."""
    assert ("onchain", "write") in lnd.EIGENE_RECHTE, \
        "Wurde es entfernt? Dann faellt /lightning/senden mit weg."
    for verboten in ("macaroon", "signer", "walletrpc"):
        assert not any(e == verboten for e, _ in lnd.EIGENE_RECHTE), verboten


def test_offchain_write_ist_kein_harmloses_recht():
    """Festgehalten, weil hier bis zum 07.09.2026 das Gegenteil behauptet
    wurde -- im Kommentar und in der oeffentlichen README.

    LNDs Rechtetabelle, v0.21.3-beta, lnrpc/routerrpc/router_server.go:
        "/routerrpc.Router/SendPaymentV2": {{Entity: "offchain",
                                             Action: "write"}}

    Dasselbe Recht, mit dem dieser Knoten seine Kanalgebuehren setzt, erlaubt
    ein POST auf /v2/router/send -- also eine Lightning-Zahlung. Wer das
    Macaroon als DATEI hat, kann damit zahlen.

    Seit dem 12.09.2026 nutzt die Anwendung das Recht selbst: sie zahlt
    Rechnungen, schichtet zwischen eigenen Kanaelen um und oeffnet Kanaele,
    alles hinter der PIN. Der Test haelt fest, dass das Recht bewusst da ist
    -- und verhindert, dass es jemand wieder fuer harmlos haelt."""
    assert ("offchain", "write") in lnd.EIGENE_RECHTE, \
        "Wurde es entfernt? Dann fallen Lightning zahlen, Umschichten, " \
        "Kanal oeffnen und /lightning/gebuehren mit weg."


def test_die_nachricht_geht_als_base64_hinaus():
    """REST verlangt es so ("must be encoded as base64"). Roher Text kaeme
    als Unsinn an -- und die Unterschrift passte dann zu nichts."""
    import base64

    gesehen = {}

    class Attrappe:
        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            gesehen["pfad"] = pfad
            gesehen["daten"] = daten
            return {"signature": "rbyfd123"}

    assert lnd.unterschreibe(Attrappe(), "hallo welt") == "rbyfd123"
    assert gesehen["pfad"] == "/v1/signmessage"
    assert base64.b64decode(gesehen["daten"]["msg"]) == b"hallo welt"


def test_ohne_unterschrift_gibt_es_keinen_stillen_leerstring():
    class Leer:
        def ruf(self, *a, **k):
            return {}

    try:
        lnd.unterschreibe(Leer(), "text")
    except lnd.LndFehler:
        return
    raise AssertionError("eine leere Unterschrift wurde durchgereicht")


def test_geaenderte_rechte_werden_erkannt(tmp_path):
    """Gebacken wurde bisher nur, wenn gar kein Macaroon da war. Ein spaeter
    ergaenztes Recht waere bei bestehenden Anlagen also NIE angekommen."""
    assert lnd.rechte_passen(tmp_path) is False
    lnd.merke_rechte(tmp_path)
    assert lnd.rechte_passen(tmp_path) is True
    (tmp_path / lnd.RECHTE_MARKE).write_text("von frueher", encoding="utf-8")
    assert lnd.rechte_passen(tmp_path) is False


# ── Anlegen und Wiederherstellen ──────────────────────────────────────────
#
# Es ist derselbe LND-Aufruf. Was ihn unterscheidet, sind drei Felder -- und
# genau die sind hier festgenagelt, weil ein falsch kodiertes Feld eine
# Wallet mit einem ANDEREN Seed ergibt als dem auf dem Zettel.

WOERTER_24 = [f"wort{n:02d}" for n in range(1, 25)]


class Mitschrift:
    """Merkt sich, was an LND geschickt wurde."""

    def __init__(self, antwort=None):
        self.antwort = antwort or {}
        self.daten = None
        self.pfad = None
        self.macaroon = None

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.pfad, self.daten, self.macaroon = pfad, daten, macaroon
        return self.antwort


def test_eine_frische_wallet_sucht_die_kette_nicht_ab():
    """recovery_window bei einer neuen Wallet waere ein langer Kettenlauf
    ohne Ergebnis -- es gibt nichts zu finden."""
    k = Mitschrift()
    lnd.lege_wallet_an(k, "achtzehn-zeichen", WOERTER_24)
    assert k.pfad == "/v1/initwallet"
    assert k.macaroon == "", "vor der Wallet gibt es kein Macaroon"
    assert "recovery_window" not in k.daten
    assert "channel_backups" not in k.daten
    assert "aezeed_passphrase" not in k.daten


def test_die_woerter_gehen_im_klartext_an_lnd():
    """cipher_seed_mnemonic ist "repeated string", KEIN Byte-Feld. Wer es
    base64 kodiert, bekommt eine Wallet mit einem anderen Seed."""
    import base64 as b64
    k = Mitschrift()
    lnd.lege_wallet_an(k, "achtzehn-zeichen", WOERTER_24)
    assert k.daten["cipher_seed_mnemonic"] == WOERTER_24
    assert b64.b64decode(k.daten["wallet_password"]) == b"achtzehn-zeichen"


def test_beim_wiederherstellen_kommen_fenster_und_sicherung_mit():
    k = Mitschrift()
    lnd.lege_wallet_an(k, "achtzehn-zeichen", WOERTER_24,
                       fenster=lnd.WIEDERHERSTELLUNG_FENSTER,
                       kanalsicherung="QUJD")
    assert k.daten["recovery_window"] == 2500, "LNDs eigener Vorgabewert"
    assert k.daten["channel_backups"] == {
        "multi_chan_backup": {"multi_chan_backup": "QUJD"}}


def test_die_seed_passphrase_geht_als_byte_feld():
    """aezeed_passphrase ist "bytes" -- ueber REST also base64. Anders als
    die Woerter daneben, und genau diese Unsymmetrie ist die Falle."""
    import base64 as b64
    k = Mitschrift()
    lnd.lege_wallet_an(k, "achtzehn-zeichen", WOERTER_24, passphrase="geheim")
    assert b64.b64decode(k.daten["aezeed_passphrase"]) == b"geheim"


@pytest.mark.parametrize("woerter", [WOERTER_24[:23], WOERTER_24 + ["mehr"]])
def test_ein_seed_hat_vierundzwanzig_woerter(woerter):
    with pytest.raises(ValueError):
        lnd.lege_wallet_an(Mitschrift(), "achtzehn-zeichen", woerter)


def test_ein_zu_kurzes_wallet_passwort_erreicht_lnd_gar_nicht():
    k = Mitschrift()
    with pytest.raises(ValueError):
        lnd.lege_wallet_an(k, "kurz", WOERTER_24)
    assert k.pfad is None


# ── Die Sicherung pruefen ─────────────────────────────────────────────────


def test_die_pruefung_nennt_die_abgedeckten_kanaele():
    """Heil ist nicht dasselbe wie aktuell. Erst die Zahl der Kanalpunkte
    laesst sich gegen die offenen Kanaele halten."""
    k = Mitschrift({"chan_points": ["abc:0", "def:1"]})
    assert lnd.sicherung_kanalpunkte(k, "QUJD") == ["abc:0", "def:1"]
    assert k.pfad == "/v1/channels/backup/verify"
    assert k.daten == {"multi_chan_backup": {"multi_chan_backup": "QUJD"}}


def test_eine_unbrauchbare_sicherung_wird_nicht_still_durchgereicht():
    class Weigert:
        def ruf(self, *a, **k):
            raise lnd.LndFehler("invalid multi channel backup")

    assert lnd.sicherung_pruefen(Weigert(), "QUJD") is False
    with pytest.raises(lnd.LndFehler):
        lnd.sicherung_kanalpunkte(Weigert(), "QUJD")


def test_zu_kleine_dateien_sind_keine_sicherung():
    """LNDs eigene Rechnung: 24 Byte Nonce + 16 Byte MAC + 1 Byte Fassung +
    4 Byte fuer "null Eintraege" (chanbackup/multi.go, NilMultiSizePacked).
    Mehr laesst sich ohne den Schluessel nicht sagen -- aber das faengt den
    abgebrochenen Download und die leere Datei ab."""
    assert lnd.SICHERUNG_MINDESTGROESSE == 45
    assert lnd.sicherung_plausibel(b"") is False
    assert lnd.sicherung_plausibel(b"x" * 44) is False
    assert lnd.sicherung_plausibel(b"x" * 45) is True


# ═════════════════════════════ Einzahladresse: Typ und Bestaendigkeit ═══
#
# Aus dem Betrieb, 09.09.2026: "wenn ich einzahlen will muss ich erst eine neue
# adresse erzeugen?? sollte ich nicht eine wallet adresse haben?"
#
# Die Frage trifft zwei Dinge. Das eine ist ein Missverstaendnis -- eine
# Wallet hat keine Adresse, sie hat beliebig viele, und eine frische je
# Zahlung ist die billigste Datenschutzmassnahme in Bitcoin. Das andere ist
# ein echter Mangel: JEDER Aufruf erzeugte eine neue, auch das blosse
# Oeffnen der Seite. Damit fuellte sich die Wallet mit ungenutzten Adressen,
# und die Zeile auf dem Bildschirm sprang bei jedem Blick.
#
# LND kennt dafuer die UNUSED_-Spielarten: sie geben die AKTUELLE unbenutzte
# Adresse zurueck und ruecken erst weiter, wenn jemand darauf gezahlt hat.
# Bestaendig auf dem Schirm, frisch je Zahlung.

def test_die_angezeigte_adresse_springt_nicht_bei_jedem_blick():
    m = Mitschrift({"address": "bc1p..."})
    lnd.einzahladresse(m)
    assert "UNUSED_TAPROOT_PUBKEY" in m.pfad, \
        "das blosse Ansehen darf keine neue Adresse verbrauchen"


def test_eine_neue_wird_nur_auf_ausdruecklichen_wunsch_erzeugt():
    m = Mitschrift({"address": "bc1p..."})
    lnd.einzahladresse(m, neu=True)
    assert "type=TAPROOT_PUBKEY" in m.pfad
    assert "UNUSED" not in m.pfad


def test_es_gibt_einen_ausweg_fuer_boersen_ohne_taproot():
    """Manche Boersen koennen bis heute nicht an bc1p senden. Ohne Auswahl
    stand man davor und die App bot keinen Ausweg -- obwohl LND laengst
    beide anderen Formen kann."""
    for art, erwartet in (("taproot", "TAPROOT_PUBKEY"),
                          ("segwit", "WITNESS_PUBKEY_HASH"),
                          ("kompatibel", "NESTED_PUBKEY_HASH")):
        m = Mitschrift({"address": "x"})
        lnd.einzahladresse(m, art=art, neu=True)
        assert f"type={erwartet}" in m.pfad, art


def test_eine_unbekannte_adressart_wird_nicht_durchgereicht():
    """Sonst stuende ein fremder Wert im Aufrufweg zu LND."""
    m = Mitschrift({"address": "x"})
    with pytest.raises(ValueError):
        lnd.einzahladresse(m, art="phantasie")
    assert m.pfad is None


def test_jede_adressart_hat_beide_spielarten():
    for art in lnd.ADRESSARTEN:
        neu, bestand = lnd.ADRESSARTEN[art]
        assert bestand == f"UNUSED_{neu}", art


# ═══════════════════════════ die eigene Unterschrift nachpruefen ═══════
#
# Bis zum 09.09.2026 konnte die Anwendung unterschreiben und ihre eigene
# Unterschrift NICHT nachpruefen -- message:read fehlte um genau eine Zeile.
# Man sah, DASS etwas herauskam und dass es die richtige Form hatte, nicht
# aber, dass es rechnerisch stimmt.

def test_das_recht_zum_nachpruefen_ist_da():
    assert ("message", "read") in lnd.EIGENE_RECHTE


def test_die_pruefung_fragt_lnd_mit_text_und_unterschrift():
    m = Mitschrift({"valid": True, "pubkey": "02aa"})
    d = lnd.pruefe_unterschrift(m, "hallo welt", "rbyfd123")
    assert m.pfad == "/v1/verifymessage"
    assert m.daten["signature"] == "rbyfd123"
    assert base64.b64decode(m.daten["msg"]).decode() == "hallo welt"
    assert d == {"gueltig": True, "kennung": "02aa"}


def test_eine_ungueltige_unterschrift_wird_auch_so_gemeldet():
    m = Mitschrift({"valid": False, "pubkey": ""})
    assert lnd.pruefe_unterschrift(m, "hallo", "xxx")["gueltig"] is False


def test_die_pruefung_nimmt_die_gleiche_kodierung_wie_das_unterschreiben():
    """base64 fuer den Text, zbase32 fuer die Unterschrift -- verwechselt
    man das, meldet LND schlicht "ungueltig" und niemand weiss warum."""
    unt = Mitschrift({"signature": "rbyfd123"})
    lnd.unterschreibe(unt, "derselbe text")
    pruef = Mitschrift({"valid": True, "pubkey": "02aa"})
    lnd.pruefe_unterschrift(pruef, "derselbe text", "rbyfd123")
    assert unt.daten["msg"] == pruef.daten["msg"]


# ═══════════════════ sich mit einer Gegenstelle verbinden ══════════════
#
# Befund 20: peers:write stand seit jeher in EIGENE_RECHTE -- mit dem
# Kommentar "sich mit einer Gegenstelle verbinden" -- und ConnectPeer war
# nirgends implementiert. Wir trugen ein Recht spazieren, das wir nie
# benutzten. Doppelt schlecht: die Funktion fehlte, und die Linie dieses
# Projekts lautet, nur zu halten, was gebraucht wird.
#
# Aus dem Betrieb, 09.09.2026: "man will sich ja nicht nur ein kanal oder knoten
# erstellen sondern sich auch einen anschliessen".

def test_verbinden_zerlegt_die_uebliche_zeile():
    m = Mitschrift({})
    lnd.verbinde(m, "02aabb@example.onion:9735")
    assert m.pfad == "/v1/peers"
    assert m.daten["addr"] == {"pubkey": "02aabb", "host": "example.onion:9735"}


def test_verbinden_haelt_die_verbindung_nicht_dauerhaft():
    """perm=true liesse LND ewig nachverbinden -- auch zu einer Gegenstelle,
    die man einmal versehentlich eingetippt hat. Verbindungen zu Kanaelen
    haelt LND ohnehin von allein."""
    m = Mitschrift({})
    lnd.verbinde(m, "02aabb@example.onion:9735")
    assert m.daten["perm"] is False


def test_verbinden_braucht_beide_haelften():
    for kaputt in ("02aabb", "@example.onion:9735", "", "  ",
                   "02aabb@", "kein-at-zeichen"):
        with pytest.raises(lnd.LndFehler):
            lnd.verbinde(Mitschrift({}), kaputt)


def test_verbinden_laesst_keine_steuerzeichen_durch():
    """Was aus einem Eingabefeld kommt, geht hier in einen Aufrufweg."""
    with pytest.raises(lnd.LndFehler):
        lnd.verbinde(Mitschrift({}), "02aa\nbb@example.onion:9735")


def test_verbinden_nimmt_umschliessende_leerzeichen_hin():
    """Wer eine Zeile aus amboss kopiert, hat oft eines dabei."""
    m = Mitschrift({})
    lnd.verbinde(m, "  02aabb@example.onion:9735\n")
    assert m.daten["addr"]["pubkey"] == "02aabb"


# ══════════════════════════ die Wallet wieder loswerden ════════════════
#
# Aus dem Betrieb, 09.09.2026: "mach es dann moeglich ein wallet zu loeschen mit
# dem wallet passwort zum entsperren ... dann kann ich die ganze
# initialisierung nochmal machen und testen."
#
# Das Passwort ist der richtige Riegel: bei abgeschaltetem Auto-Entsperren
# liegt es NIRGENDS auf der Platte. Eine uebernommene Browser-Sitzung hat
# es also nicht.

def test_geloescht_wird_nur_unterhalb_des_wallet_verzeichnisses(tmp_path):
    lnd_dir = tmp_path / "lnd"
    (lnd_dir / "data" / "chain").mkdir(parents=True)
    (lnd_dir / "data" / "chain" / "wallet.db").write_text("x")
    (lnd_dir / "tls.cert").write_text("x")
    (lnd_dir / "wallet.pass").write_text("x")
    daneben = tmp_path / "bitcoind"
    daneben.mkdir()
    (daneben / "blocks.dat").write_text("wichtig")

    lnd.loesche_wallet(lnd_dir)

    assert lnd_dir.exists(), "der Einhaengepunkt selbst bleibt stehen"
    assert not list(lnd_dir.iterdir()), "darunter darf nichts uebrig bleiben"
    assert (daneben / "blocks.dat").read_text() == "wichtig", \
        "ausserhalb des Wallet-Verzeichnisses wird NICHTS angefasst"


def test_ein_fehlendes_verzeichnis_ist_kein_fehler(tmp_path):
    """Wer zweimal auf loeschen drueckt, soll keinen Absturz sehen."""
    lnd.loesche_wallet(tmp_path / "gibtsnicht")


def test_geloescht_wird_nichts_ausserhalb_per_verweis(tmp_path):
    """Ein Symlink im Wallet-Verzeichnis darf nicht dazu fuehren, dass
    ausserhalb geloescht wird."""
    lnd_dir = tmp_path / "lnd"
    lnd_dir.mkdir()
    fremd = tmp_path / "fremd"
    fremd.mkdir()
    (fremd / "wichtig.dat").write_text("bleibt")
    (lnd_dir / "verweis").symlink_to(fremd)

    lnd.loesche_wallet(lnd_dir)

    assert not list(lnd_dir.iterdir())
    assert (fremd / "wichtig.dat").read_text() == "bleibt", \
        "dem Verweis wurde gefolgt -- das haette fremde Daten geloescht"


# ── Weiterleitungen: LND blaettert vom AELTESTEN aufwaerts ─────────────────
#
# Gefunden am 10.09.2026 beim Beantworten von die Frage aus dem Betrieb, wo die
# verdienten Gebuehren landen. Der Aufruf holte 500 Ereignisse ab Index 0 --
# und LNDs eigene Beschreibung sagt, in welche Richtung das laeuft:
#
#   index_offset: "Index offset is the offset in the time series to start
#                  at. As each response can only contain 50k records,
#                  callers can use this to skip around within a packed time
#                  series."
#   last_offset_index: "The index of the last time in the set of returned
#                       forwarding events. Can be used to seek further,
#                       pagination style."
#
# Also: Offset 0 heisst die AELTESTEN. Ab der 501. Weiterleitung waere
# "Sats verdient" auf der Summe der ersten 500 eingefroren, und "die letzten
# zwanzig" waeren die Nummern 481-500 statt der neuesten. Eine Zahl, die
# still falsch wird -- dieselbe Sorte wie der Euro-Kurs im September.

class Blaetterer:
    """LNDs Verhalten: ab index_offset vorwaerts, hoechstens num_max_events."""

    def __init__(self, anzahl):
        self.alle = [{
            "timestamp_ns": str((1_780_000_000 + i) * 1_000_000_000),
            "amt_out": "1000", "fee_msat": "500",
            "peer_alias_in": "A", "peer_alias_out": f"Z{i}",
        } for i in range(anzahl)]
        self.seiten = 0

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.seiten += 1
        ab = int((daten or {}).get("index_offset") or 0)
        wieviel = int((daten or {}).get("num_max_events") or 100)
        stueck = self.alle[ab:ab + wieviel]
        return {"forwarding_events": stueck,
                "last_offset_index": str(ab + len(stueck))}


@pytest.fixture
def kleine_seite(monkeypatch):
    """Die Seitengroesse klein machen, damit geblaettert werden MUSS.

    Sonst haengt der Test an der Zahl in lnd.py -- und die ist absichtlich so
    gross, dass ein Heimknoten jahrelang mit einem Aufruf auskommt.
    """
    monkeypatch.setattr(lnd, "WEITERLEITUNG_SEITE", 100)
    return 100


def test_die_summe_umfasst_auch_die_weiterleitung_nummer_501(kleine_seite):
    """Sonst friert das Verdiente ein, ohne dass es jemand merkt."""
    k = Blaetterer(1234)
    d = lnd.weiterleitungen(k)
    assert d["anzahl"] == 1234
    assert d["menge"] == 1234 * 1000
    assert d["gebuehr_msat"] == 1234 * 500
    assert k.seiten == 13, "12 volle Seiten und eine angebrochene"


def test_die_letzten_sind_die_neuesten_und_nicht_die_von_seite_eins(kleine_seite):
    k = Blaetterer(1234)
    letzte = lnd.weiterleitungen(k)["letzte"]
    assert len(letzte) == lnd.WEITERLEITUNG_ZEIGEN
    assert letzte[0]["nach"] == "Z1233", "die neueste zuerst"
    assert letzte[-1]["nach"] == "Z1214"


def test_ein_knoten_mit_wenig_verkehr_wird_einmal_gefragt():
    """Die Seite ist absichtlich gross: Blaettern ist der Ausnahmefall."""
    k = Blaetterer(3)
    d = lnd.weiterleitungen(k)
    assert d["anzahl"] == 3 and k.seiten == 1


def test_das_blaettern_hat_ein_ende_auch_wenn_lnd_sich_verschluckt():
    """Ein Knoten, der immer wieder dieselbe volle Seite liefert, darf die
    Anwendung nicht in eine Endlosschleife ziehen."""
    class Klemmt:
        def __init__(self):
            self.seiten = 0

        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            self.seiten += 1
            wieviel = int((daten or {}).get("num_max_events") or 100)
            return {"forwarding_events": [
                {"timestamp": "1780000000", "amt_out": "1", "fee_msat": "1"}
            ] * wieviel, "last_offset_index": "0"}

    k = Klemmt()
    lnd.weiterleitungen(k)
    assert k.seiten <= lnd.WEITERLEITUNG_SEITEN_HOECHSTENS


def test_ohne_weiterleitungen_wird_nicht_geblaettert():
    k = FakeRuf({"/v1/switch": {"forwarding_events": []}})
    d = lnd.weiterleitungen(k)
    assert d == {"anzahl": 0, "menge": 0, "gebuehr_msat": 0, "letzte": []}
    assert len(k.gerufen) == 1


# ── Die Kanalreserve (10.09.2026) ──────────────────────────────────────────
#
# Nachgelesen bei lightningnode.info, nachdem der Betreiber die Seite geschickt hat:
# jeder Kanal haelt auf BEIDEN Seiten ein Prozent seiner Kapazitaet zurueck.
# Es ist das Pfand, das einen Betrugsversuch teuer macht -- und es ist nicht
# ausgebbar.
#
# local_balance enthaelt es trotzdem. Bis dahin zeigte die Oberflaeche also
# Geld als verfuegbar, das es nicht ist. Bei kleinen Kanaelen faellt das ins
# Gewicht, und der Tag, an dem man es merkt, ist der, an dem eine Zahlung
# scheitert.

class _KanalKnoten:
    def __init__(self, kanal):
        self.kanal = kanal

    def ruf(self, pfad, *a, **kw):
        assert pfad.startswith("/v1/channels")
        return {"channels": [self.kanal]}


def test_die_reserve_wird_vom_ausgebbaren_abgezogen():
    knoten = _KanalKnoten({
        "active": True, "capacity": "146000", "local_balance": "146000",
        "remote_balance": "0", "local_chan_reserve_sat": "1460",
        "remote_pubkey": "02" + "a" * 64, "channel_point": "x:0",
    })
    k = lnd.kanaele(knoten)[0]
    assert k["hier"] == 146_000, "die rohe Zahl bleibt, wie LND sie meldet"
    assert k["reserve"] == 1460
    assert k["verfuegbar"] == 144_540


def test_ohne_reserve_ist_alles_verfuegbar():
    """Aeltere Kanaele und Attrappen melden das Feld gar nicht. Dann darf
    daraus keine Null-Reserve mit falschem Abzug werden."""
    knoten = _KanalKnoten({
        "active": True, "capacity": "100000", "local_balance": "60000",
        "remote_balance": "40000", "remote_pubkey": "02" + "b" * 64,
        "channel_point": "y:0",
    })
    k = lnd.kanaele(knoten)[0]
    assert k["reserve"] == 0
    assert k["verfuegbar"] == 60_000


def test_die_reserve_kann_das_verfuegbare_nicht_negativ_machen():
    """Direkt nach dem Oeffnen liegt auf der Gegenseite weniger als ihre
    Reserve -- fuer die eigene Seite gilt dasselbe umgekehrt. Eine negative
    Zahl waere sinnlos."""
    knoten = _KanalKnoten({
        "active": True, "capacity": "100000", "local_balance": "500",
        "remote_balance": "99500", "local_chan_reserve_sat": "1000",
        "remote_pubkey": "02" + "c" * 64, "channel_point": "z:0",
    })
    assert lnd.kanaele(knoten)[0]["verfuegbar"] == 0


# ── Die Anker-Ruecklage ────────────────────────────────────────────────────
#
# Aus dem Betrieb, 11.09.2026: "dein knoten soll die menge an sat haben dann musst
# du aber das plus exit und gebueren an sat einzahlen".
#
# Sein Gefuehl stimmt, der Mechanismus ist nur ein anderer: die Schliessgebuehr
# wird beim einvernehmlichen Schliessen vom KANALGUTHABEN abgezogen, nicht
# vorher eingezahlt. Was zusaetzlich in der Wallet liegen muss, ist die
# Anker-Ruecklage -- und die schaetzen wir nicht, LND nennt sie.

def test_die_ruecklage_wird_bei_lnd_erfragt():
    """Nachgesehen in der API-Doku am 11.09.2026: GET /v2/wallet/reserve
    mit additional_public_channels, Antwort required_reserve."""
    class Attrappe:
        def __init__(self):
            self.pfade = []

        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            self.pfade.append(pfad)
            return {"required_reserve": "10000"}

    knoten = Attrappe()
    assert lnd.ruecklage(knoten) == 10_000
    assert knoten.pfade == ["/v2/wallet/reserve?additional_public_channels=1"]


def test_mehr_kanaele_mehr_ruecklage():
    """Die Frage lautet "wenn so viele dazukaemen" -- die Zahl gehoert in
    den Aufruf, nicht in eine Faustformel bei uns."""
    class Attrappe:
        def __init__(self):
            self.pfad = ""

        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            self.pfad = pfad
            return {"required_reserve": 30_000}

    knoten = Attrappe()
    assert lnd.ruecklage(knoten, 3) == 30_000
    assert knoten.pfad.endswith("additional_public_channels=3")


def test_ohne_antwort_gibt_es_keine_ruecklage():
    """None statt 0. Eine Null hiesse "du brauchst nichts zurueckzulegen" --
    und genau daran scheitert man spaeter beim erzwungenen Schliessen."""
    class Stumm:
        def ruf(self, *a, **k):
            raise lnd.NichtErreichbar("LND antwortet nicht")

    class Leer:
        def ruf(self, *a, **k):
            return {}

    assert lnd.ruecklage(Stumm()) is None
    assert lnd.ruecklage(Leer()) is None


# ── Einen Kanal oeffnen (12.09.2026) ───────────────────────────────────────
#
# Der Betreiber: "ja dann machen wir mal mit Punkt 1 und 2 weiter."

KENNUNG = "02" + "ab" * 32          # 66 Hexzeichen, wie im Graphen


class Kanalattrappe:
    def __init__(self, txid_hex="", verbindungsfehler=None):
        self.gerufen = []
        self.txid_hex = txid_hex or ("d4" * 32)
        self.verbindungsfehler = verbindungsfehler
        self.ohne_adresse_im_graph = False

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.gerufen.append((pfad, daten))
        if pfad == "/v1/peers":
            if self.verbindungsfehler:
                raise lnd.LndFehler(self.verbindungsfehler)
            return {}
        if pfad == "/v1/channels":
            import base64 as b64
            # LND liefert die Bytes in INTERNER Reihenfolge -- rueckwaerts.
            roh = bytes.fromhex(self.txid_hex)[::-1]
            return {"funding_txid_bytes": b64.b64encode(roh).decode(),
                    "output_index": 1}
        # Seit dem 19.09.2026 schlaegt das Oeffnen die Adresse im eigenen
        # Graphen nach, wenn nur die Kennung angegeben wurde.
        if pfad.startswith("/v1/graph/node/"):
            if self.ohne_adresse_im_graph:
                return {"node": {"addresses": []}}
            return {"node": {"addresses": [{"addr": "aus-dem-graph.onion:9735"}]}}
        raise AssertionError("unerwartet: " + pfad)


def test_die_kennung_wird_geprueft_bevor_lnd_gefragt_wird():
    """66 Hexzeichen, sonst gar nicht erst losgehen. Eine lesbare Auskunft
    statt einer gRPC-Meldung ueber einen ungueltigen Punkt."""
    a = Kanalattrappe()
    for falsch in ("", "abc", "z" * 66, KENNUNG[:-1]):
        with pytest.raises(lnd.LndFehler):
            lnd.kanal_oeffnen(a, falsch, 100_000, 5)
    assert a.gerufen == [], "nichts davon darf LND ueberhaupt erreichen"


def test_ein_zu_kleiner_kanal_wird_abgelehnt():
    a = Kanalattrappe()
    with pytest.raises(lnd.LndFehler):
        lnd.kanal_oeffnen(a, KENNUNG, lnd.KANAL_MIN_SAT - 1, 5)
    assert a.gerufen == []


def test_erst_verbinden_dann_oeffnen():
    """LND oeffnet nur zu jemandem, mit dem es GERADE verbunden ist. Der
    Schritt wird gern vergessen und ist dann schwer zu deuten."""
    a = Kanalattrappe()
    lnd.kanal_oeffnen(a, KENNUNG + "@1.2.3.4:9735", 100_000, 5)
    assert [p for p, _ in a.gerufen] == ["/v1/peers", "/v1/channels"]


def test_eine_bestehende_verbindung_ist_kein_fehler():
    """Bei einer Gegenstelle, mit der man schon Kanaele hat, ist "already
    connected" der Normalfall -- kein Grund, das Oeffnen abzubrechen."""
    a = Kanalattrappe(verbindungsfehler="already connected to peer")
    d = lnd.kanal_oeffnen(a, KENNUNG + "@1.2.3.4:9735", 100_000, 5)
    assert d["txid"]


def test_die_txid_kommt_richtigherum_zurueck():
    """DIE FALLE. LNDs funding_txid_bytes stehen in interner Reihenfolge,
    also rueckwaerts zu dem, was jeder Explorer zeigt. Wer sie einfach in
    Hex wandelt, gibt dem Nutzer eine Kennung, die es nirgends gibt."""
    echt = "1f" * 16 + "2e" * 16
    a = Kanalattrappe(txid_hex=echt)
    d = lnd.kanal_oeffnen(a, KENNUNG, 100_000, 5)
    assert d["txid"] == echt
    assert d["ausgang"] == 1


def test_der_kanal_wird_oeffentlich_und_ohne_geschenk_geoeffnet():
    """Oeffentlich, weil dieser Knoten teilnehmen soll -- ein privater Kanal
    steht in keinem Graphen. Und push_sat=0, weil ein Geschenk an die
    Gegenstelle niemand erwartet."""
    a = Kanalattrappe()
    lnd.kanal_oeffnen(a, KENNUNG, 100_000, 5)
    daten = dict(a.gerufen)["/v1/channels"]
    assert daten["private"] is False
    assert daten["push_sat"] == "0"
    assert daten["min_confs"] == 1
    assert daten["spend_unconfirmed"] is False


# ── Eine Lightning-Rechnung lesen und bezahlen ─────────────────────────────

class Zahlattrappe:
    """Ein Knoten, dessen Zahl-Endpunkt einen STROM liefert."""

    def __init__(self, meldungen, rechnung=None):
        self.meldungen = meldungen
        self.rechnung = rechnung or {}
        self.gesendet = None

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if pfad.startswith("/v1/payreq/"):
            return self.rechnung
        raise AssertionError("unerwartet: " + pfad)

    def strom(self, pfad, daten, macaroon="readonly", zeitlimit=None):
        self.gesendet = daten
        for m in self.meldungen:
            yield m


def test_eine_rechnung_wird_gelesen_bevor_jemand_zahlt():
    a = Zahlattrappe([], rechnung={
        "destination": "03ff", "num_satoshis": "1500", "timestamp": "1000",
        "expiry": "3600", "description": "Kaffee", "payment_hash": "aa"})
    d = lnd.rechnung_lesen(a, "lightning:LNBC15u1p...")
    assert d["betrag"] == 1500
    assert d["offener_betrag"] is False
    assert d["zweck"] == "Kaffee"
    assert d["laeuft_ab"] == 4600
    # Das Praefix der Wallet-Apps darf nicht mitwandern.
    assert not d["rechnung"].lower().startswith("lightning:")


def test_eine_rechnung_ohne_betrag_faellt_auf():
    """Sonst stuende dort "0 sat" und saehe aus wie umsonst."""
    a = Zahlattrappe([], rechnung={"num_satoshis": "0", "timestamp": "1"})
    assert lnd.rechnung_lesen(a, "lnbc1...")["offener_betrag"] is True


def test_der_strom_wird_bis_zum_ende_gelesen():
    """DER PUNKT beim Zahlen. LND meldet mehrfach; erst die LETZTE Meldung
    sagt, wie es ausging. Wer nur die erste liest, haelt jede Zahlung fuer
    unterwegs -- und meldet Erfolg, wo keiner ist."""
    a = Zahlattrappe([
        {"result": {"status": "IN_FLIGHT"}},
        {"result": {"status": "IN_FLIGHT"}},
        {"result": {"status": "SUCCEEDED", "fee_sat": "3",
                    "value_sat": "1500", "payment_preimage": "beleg",
                    "payment_hash": "aa"}},
    ])
    d = lnd.zahle(a, "lnbc1...", 15)
    assert d["gebuehr"] == 3 and d["betrag"] == 1500 and d["beleg"] == "beleg"


def test_eine_gescheiterte_zahlung_nennt_den_grund():
    """"Fehlgeschlagen" allein sagt niemandem, ob er es gleich noch einmal
    versuchen soll."""
    a = Zahlattrappe([
        {"result": {"status": "IN_FLIGHT"}},
        {"result": {"status": "FAILED",
                    "failure_reason": "FAILURE_REASON_NO_ROUTE"}},
    ])
    with pytest.raises(lnd.LndFehler, match="NO_ROUTE"):
        lnd.zahle(a, "lnbc1...", 15)


def test_die_gebuehrengrenze_geht_immer_mit():
    """Ohne sie nimmt LND, was die Route kostet -- und das kann bei einer
    schlechten Route ein Vielfaches des Betrags sein."""
    a = Zahlattrappe([{"result": {"status": "SUCCEEDED"}}])
    lnd.zahle(a, "lnbc1...", 42)
    assert a.gesendet["fee_limit_sat"] == "42"
    assert a.gesendet["allow_self_payment"] is False
    # Ohne offenen Betrag darf kein amt mitgehen -- das widerspraeche der
    # Rechnung, und LND lehnt ab.
    assert "amt" not in a.gesendet


def test_bei_offenem_betrag_geht_der_betrag_mit():
    a = Zahlattrappe([{"result": {"status": "SUCCEEDED"}}])
    lnd.zahle(a, "lnbc1...", 42, betrag_sat=2000)
    assert a.gesendet["amt"] == "2000"


def test_die_vorgeschlagene_grenze_waechst_mit_dem_betrag():
    assert lnd.gebuehrgrenze(100) == lnd.GEBUEHRGRENZE_MIN_SAT
    assert lnd.gebuehrgrenze(1_000_000) == 10_000


# ── Die Gegenstelle ansehen, bevor ein Kanal steht (12.09.2026) ────────────
#
# Der Betreiber: "gibt es uns die moeglichkeit einen channel den wir verknuepfen
# wollen vorher zu scannen und zu warnen ob das sinn macht??"
#
# Aus dem EIGENEN Graphen. Und ausdruecklich OHNE Note oder Vertrauenswert --
# das waere erfundene Genauigkeit. Es sind Tatsachen, und drei davon sagen
# wirklich etwas.

JETZT = 1_800_000_000


class Graphattrappe:
    def __init__(self, antwort=None, fehler=None):
        self.antwort = antwort
        self.fehler = fehler

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if self.fehler:
            raise lnd.LndFehler(self.fehler)
        return self.antwort


def _graph(last_update, kanaele=20, adressen=("1.2.3.4:9735",),
           kapazitaet="50000000"):
    return {"node": {"alias": "ACINQ", "last_update": last_update,
                     "addresses": [{"addr": a} for a in adressen]},
            "num_channels": kanaele, "total_capacity": kapazitaet}


def test_eine_unbekannte_gegenstelle_ist_eine_auskunft_kein_fehler():
    """Steht sie nicht im eigenen Graphen, ist das genau das, was man vor
    einem Kanal wissen will."""
    d = lnd.gegenstelle_ansehen(Graphattrappe(fehler="unable to find node"),
                                KENNUNG, jetzt=JETZT)
    assert d["bekannt"] is False


def test_ein_stiller_knoten_faellt_auf():
    """Der teuerste Fall von allen: die Gegenstelle verschwindet. Dann gibt
    es kein einvernehmliches Schliessen mehr -- nur noch das erzwungene."""
    alt = JETZT - 40 * 86400
    d = lnd.gegenstelle_ansehen(Graphattrappe(_graph(alt)), KENNUNG,
                                jetzt=JETZT)
    assert d["still"] is True
    assert d["still_seit_tagen"] == 40


def test_ein_lebendiger_knoten_gilt_nicht_als_still():
    d = lnd.gegenstelle_ansehen(Graphattrappe(_graph(JETZT - 3600)), KENNUNG,
                                jetzt=JETZT)
    assert d["still"] is False
    assert d["wenig_verbunden"] is False
    assert d["alias"] == "ACINQ"


def test_wenig_verbunden_und_ohne_adresse_fallen_getrennt_auf():
    """Bewusst einzeln benannt statt zu einer Note verrechnet: wer einen
    Befund hinnehmen will, soll wissen, welchen."""
    d = lnd.gegenstelle_ansehen(
        Graphattrappe(_graph(JETZT, kanaele=2, adressen=())), KENNUNG,
        jetzt=JETZT)
    assert d["wenig_verbunden"] is True
    assert d["ohne_adresse"] is True


def test_nur_ueber_tor_wird_vermerkt():
    """Kein Mangel, aber ein Unterschied: ein Kanal zu einem reinen
    Tor-Knoten haengt an Tor."""
    d = lnd.gegenstelle_ansehen(
        Graphattrappe(_graph(JETZT, adressen=("abc.onion:9735",))), KENNUNG,
        jetzt=JETZT)
    assert d["nur_tor"] is True


# ── Wachtuerme ─────────────────────────────────────────────────────────────
#
# Der Befund vom 12.09.2026: wtclient.active=true stand in der Konfiguration,
# eingetragen war kein einziger Turm. Der Schutz sah eingeschaltet aus und war
# es nicht.

class Turmattrappe:
    """Antwortet wie LND -- auch darin, was es WEGLAESST.

    Ohne include_sessions=true schickt LND keine Sitzungslisten
    (wtclientrpc/wtclient.go, marshallTower). Die erste Attrappe hier hatte
    sie trotzdem, und so bestaetigte der Test eine Anzeige, die bei echtem
    LND immer "0 Sitzungen" zeigte.
    """

    def __init__(self, tuerme=None, zaehler=None):
        self.tuerme = tuerme or []
        self.zaehler = zaehler or {}
        self.eingetragen = None
        self.pfade = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.pfade.append(pfad)
        if pfad == "/v2/watchtower/client/stats":
            return self.zaehler
        basis, _, frage = pfad.partition("?")
        assert basis == "/v2/watchtower/client"
        if daten is not None:
            self.eingetragen = daten
            return {}
        if "include_sessions=true" in frage:
            return {"towers": self.tuerme}
        return {"towers": [
            dict(turm, sessions=[], session_info=[
                dict(info, sessions=[])
                for info in turm.get("session_info") or []])
            for turm in self.tuerme]}


def _lnd_turm(*session_info, adresse="t.onion:9911"):
    """Ein Turm, wie LND v0.21.3 ihn ueber REST schickt."""
    return {
        "pubkey": base64.b64encode(bytes.fromhex(KENNUNG)).decode(),
        "addresses": [adresse],
        # Die veralteten Felder. LND fuellt sie noch, aber nur mit dem, was
        # es fuer EINE Sitzungsart weiss.
        "active_session_candidate": True, "num_sessions": 0, "sessions": [],
        "session_info": list(session_info),
    }


def _sitzungsinfo(art, *sitzungen):
    return {"policy_type": art, "active_session_candidate": True,
            "num_sessions": len(sitzungen), "sessions": list(sitzungen)}


def _sitzung(bestaetigt=0, ausstehend=0, hoechstens=1024):
    return {"num_backups": bestaetigt, "num_pending_backups": ausstehend,
            "max_backups": hoechstens, "sweep_sat_per_byte": 10,
            "sweep_sat_per_vbyte": 10, "id": "AAAA"}


def test_ohne_turm_ist_die_liste_leer_und_sagt_das():
    assert lnd.wachtuerme(Turmattrappe()) == []


def test_die_sitzungen_werden_wirklich_abgefragt():
    """Der Befund vom 14.09.2026: ohne include_sessions=true stand bei jedem
    Turm "0 Sitzungen", egal wie es wirklich stand."""
    a = Turmattrappe([_lnd_turm(_sitzungsinfo("ANCHOR", _sitzung(12)))])
    d = lnd.wachtuerme(a)[0]
    assert "include_sessions=true" in a.pfade[0]
    assert d["sitzungen"] == 1
    assert d["arten"]["ANCHOR"] == {"sitzungen": 1, "nutzbar": 1,
                                    "bestaetigt": 12, "ausstehend": 0}
    assert d["adressen"] == ["t.onion:9911"]
    assert d["kennung"] == KENNUNG, "REST schickt base64, gezeigt wird hex"


def test_jede_sitzungsart_wird_fuer_sich_gezaehlt():
    """LND fuehrt je Kanalart einen eigenen Client. Taproot zusaetzlich als
    Nummer: sollte REST sie je so schicken, wird sie trotzdem erkannt."""
    a = Turmattrappe([_lnd_turm(
        _sitzungsinfo("ANCHOR", _sitzung(3, ausstehend=1)),
        _sitzungsinfo(2),
    )])
    arten = lnd.wachtuerme(a)[0]["arten"]
    assert arten["ANCHOR"]["ausstehend"] == 1
    assert arten["TAPROOT"] == {"sitzungen": 0, "nutzbar": 0,
                                "bestaetigt": 0, "ausstehend": 0}


def test_eine_volle_sitzung_nimmt_nichts_mehr_an():
    a = Turmattrappe([_lnd_turm(_sitzungsinfo(
        "ANCHOR", _sitzung(1020, ausstehend=4, hoechstens=1024)))])
    anker = lnd.wachtuerme(a)[0]["arten"]["ANCHOR"]
    assert anker["sitzungen"] == 1 and anker["nutzbar"] == 0


def test_ein_turm_braucht_kennung_und_adresse():
    """Ohne Adresse ist ein Turm nicht erreichbar -- und ein Turm, den man
    nicht erreicht, bewacht nichts."""
    a = Turmattrappe()
    for falsch in ("", KENNUNG, "@host:9911", "zzz@host:9911"):
        with pytest.raises(lnd.LndFehler):
            lnd.wachturm_eintragen(a, falsch)
    assert a.eingetragen is None


class Austragattrappe:
    def __init__(self):
        self.aufrufe = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None,
            methode=None):
        self.aufrufe.append({"pfad": pfad, "macaroon": macaroon,
                             "daten": daten, "methode": methode})
        return {}


def test_ein_turm_laesst_sich_austragen():
    """Sonst waechst die Liste endlos -- oeffentliche Turmlisten sind voller
    Tuerme, die es nicht mehr gibt."""
    # Genau der Fall, um den es geht: gewoehnliches base64 enthielte hier
    # einen Schraegstrich, und der zerbraeche den Pfad.
    kennung = "03" + "ff" * 32
    assert "/" in base64.b64encode(bytes.fromhex(kennung)).decode()
    a = Austragattrappe()
    assert lnd.wachturm_entfernen(a, kennung.upper()) == kennung
    aufruf = a.aufrufe[0]
    assert aufruf["methode"] == "DELETE" and aufruf["daten"] is None
    assert aufruf["macaroon"] == lnd.EIGENES_MACAROON
    schluessel = aufruf["pfad"][len("/v2/watchtower/client/"):]
    assert aufruf["pfad"].startswith("/v2/watchtower/client/")
    assert "/" not in schluessel, "ein Schraegstrich zerbraeche den Pfad"
    assert base64.urlsafe_b64decode(schluessel).hex() == kennung


def test_austragen_braucht_eine_echte_kennung():
    a = Austragattrappe()
    for falsch in ("", "zz" * 33, "03ab", KENNUNG + "@host:9911"):
        with pytest.raises(lnd.LndFehler):
            lnd.wachturm_entfernen(a, falsch)
    assert a.aufrufe == [], "mit einer kaputten Kennung geht nichts an LND"


def test_die_kennung_geht_als_bytes_an_lnd():
    """REST nimmt sie base64-kodiert, nicht als Hex."""
    import base64 as b64
    a = Turmattrappe()
    lnd.wachturm_eintragen(a, KENNUNG + "@t.onion:9911")
    assert a.eingetragen["address"] == "t.onion:9911"
    assert b64.b64decode(a.eingetragen["pubkey"]).hex() == KENNUNG


@pytest.mark.parametrize("kanalart, sitzungsart", [
    ("TAPROOT", "TAPROOT"),
    ("SIMPLE_TAPROOT_FINAL", "TAPROOT"),
    ("SIMPLE_TAPROOT", "TAPROOT"),
    ("ANCHORS", "ANCHOR"),
    ("SCRIPT_ENFORCED_LEASE", "ANCHOR"),
    ("STATIC_REMOTE_KEY", "LEGACY"),
    ("LEGACY", "LEGACY"),
    (None, "LEGACY"),
])
def test_die_sitzungsart_folgt_der_kanalart_wie_bei_lnd(kanalart, sitzungsart):
    """watchtower/blob/type.go, TypeFromChannel: Taproot vor Anker vor allem
    anderen."""
    assert lnd.sitzungsart(kanalart) == sitzungsart


def test_die_kanalliste_fuehrt_die_sitzungsart_mit():
    class Kanalattrappe:
        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            return {"channels": [{"capacity": "1000000", "local_balance": "0",
                                  "active": True,
                                  "commitment_type": "ANCHORS"}]}
    assert lnd.kanaele(Kanalattrappe())[0]["sitzungsart"] == "ANCHOR"


def _turm_mit(**arten):
    return {"arten": {art: {"sitzungen": n, "nutzbar": n, "bestaetigt": 0,
                            "ausstehend": 0} for art, n in arten.items()}}


def test_eingetragen_ist_nicht_bewacht():
    """Ein Turm, der nie eine Sitzung angenommen hat, bewacht nichts -- er
    steht aber genauso in der Liste wie einer, der arbeitet."""
    anker = [{"sitzungsart": "ANCHOR"}]
    assert lnd.ungedeckte_arten(anker, [_turm_mit()]) == ["ANCHOR"]
    assert lnd.ungedeckte_arten(anker, []) == ["ANCHOR"]


def test_ein_ausgetragener_turm_bewacht_nichts_mehr():
    """LND fuehrt einen ausgetragenen Turm, der Sitzungen hatte, weiter in
    seiner Liste -- nur nicht mehr als Kandidaten. Seine alten Sitzungen
    duerfen nicht als Schutz zaehlen, sonst stuende "Bewacht" da."""
    info = {"policy_type": "ANCHOR", "active_session_candidate": False,
            "num_sessions": 1, "sessions": [_sitzung(7)]}
    a = Turmattrappe([_lnd_turm(info)])
    turm = lnd.wachtuerme(a)[0]
    assert turm["aktiv"] is False
    assert turm["arten"]["ANCHOR"]["nutzbar"] == 1, "die Sitzung selbst sieht gut aus"
    assert lnd.ungedeckte_arten([{"sitzungsart": "ANCHOR"}], [turm]) == ["ANCHOR"]


def test_ein_eingetragener_turm_ist_aktiv():
    a = Turmattrappe([_lnd_turm(_sitzungsinfo("ANCHOR"))])
    assert lnd.wachtuerme(a)[0]["aktiv"] is True


def test_ein_turm_in_reserve_ist_keine_luecke():
    """LND handelt je Kanalart mit genau einem Turm. Der zweite wartet."""
    anker = [{"sitzungsart": "ANCHOR"}]
    assert lnd.ungedeckte_arten(anker, [_turm_mit(), _turm_mit(ANCHOR=1)]) == []


def test_der_eigene_turm_zaehlt_nicht_als_schutz():
    """DER BEFUND VOM 17.09.2026 an dem Knoten im Betrieb.

    Er hatte seinen eigenen Wachturm mit eingetragen. LND handelte mit ihm
    Sitzungen fuer alle Kanalarten aus, und die Oberflaeche meldete gruen
    "Bereit". Gedeckt war damit alles ausser dem einen Fall, fuer den es
    einen Wachturm gibt: dass DIESER Knoten gerade nicht laeuft. Dann laeuft
    der Turm auf derselben Maschine auch nicht.
    """
    anker = [{"sitzungsart": "ANCHOR"}]
    eigener = dict(_turm_mit(ANCHOR=1), eigen=True)
    fremder = dict(_turm_mit(ANCHOR=1), eigen=False)

    assert lnd.ungedeckte_arten(anker, [eigener]) == ["ANCHOR"], \
        "der eigene Turm galt als Schutz"
    assert lnd.ungedeckte_arten(anker, [fremder]) == []
    # Und zusammen: der fremde deckt, der eigene aendert daran nichts.
    assert lnd.ungedeckte_arten(anker, [eigener, fremder]) == []


def test_der_eigene_turm_wird_in_der_liste_erkannt():
    """Ohne die Kennzeichnung sieht man dem Eintrag nicht an, dass er der
    eigene ist -- in der Liste steht nur die Adresse."""
    a = Turmattrappe([_lnd_turm(_sitzungsinfo("ANCHOR"))])
    assert lnd.wachtuerme(a, KENNUNG)[0]["eigen"] is True
    # Ohne bekannte eigene Kennung wird nichts geraten.
    assert lnd.wachtuerme(a)[0]["eigen"] is False
    assert lnd.wachtuerme(a, "02" + "cd" * 32)[0]["eigen"] is False


def test_eine_anker_sitzung_bewacht_keinen_taproot_kanal():
    kanaele = [{"sitzungsart": "ANCHOR"}, {"sitzungsart": "TAPROOT"}]
    assert lnd.ungedeckte_arten(kanaele, [_turm_mit(ANCHOR=1)]) == ["TAPROOT"]


def test_ohne_kanal_zaehlt_die_art_eines_neuen_kanals():
    assert lnd.ungedeckte_arten([], [_turm_mit()]) == [
        lnd.SITZUNGSART_NEUER_KANAELE]
    assert lnd.ungedeckte_arten([], [_turm_mit(ANCHOR=1)]) == []


def test_die_zaehler_kommen_aus_lnds_statistik():
    a = Turmattrappe(zaehler={"num_backups": 12, "num_pending_backups": 1,
                              "num_failed_backups": 0,
                              "num_sessions_acquired": 2,
                              "num_sessions_exhausted": 0})
    assert lnd.wachturm_zaehler(a) == {"bestaetigt": 12, "ausstehend": 1,
                                       "abgewiesen": 0, "sitzungen_neu": 2}


# ── Zwischen eigenen Kanaelen umschichten (12.09.2026) ─────────────────────
#
# Der Betreiber: "kann ich dann mehre kanäle balancen??"
#
# Der Mechanismus ist derselbe, den ich beim ZAHLEN ausdruecklich gesperrt
# habe: eine Zahlung an sich selbst. Beim Bezahlen einer fremden Rechnung ist
# das ein Unfall, beim Umschichten der Zweck. Zwei Vorgaenge, zwei Knoepfe --
# und nur einer hat allow_self_payment an. Die Tests halten beide Seiten fest.

class Schichtattrappe:
    def __init__(self, meldungen=None, rechnung="lnbc1rechnung"):
        self.meldungen = meldungen or [
            {"result": {"status": "SUCCEEDED", "value_sat": "50000",
                        "fee_sat": "7"}}]
        self.rechnung = rechnung
        self.ausgestellt = None
        self.gesendet = None

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        assert pfad == "/v1/invoices", pfad
        import base64 as b64
        self.ausgestellt = daten
        # Wie LND: r_hash kommt als base64.
        return {"payment_request": self.rechnung,
                "r_hash": b64.b64encode(bytes.fromhex("cd" * 32)).decode()}

    def strom(self, pfad, daten, macaroon="readonly", zeitlimit=None):
        self.gesendet = daten
        for m in self.meldungen:
            if m == "ausbleiben":
                raise lnd.Beschaeftigt("kein Wort innerhalb der Frist")
            yield m


def test_umschichten_stellt_zuerst_eine_eigene_rechnung_aus():
    """Ohne eigene Rechnung gibt es nichts, was man sich selbst zahlen
    koennte."""
    a = Schichtattrappe()
    d = lnd.umschichten(a, "12345", KENNUNG, 50_000, 100)
    assert a.ausgestellt["value"] == "50000"
    assert a.gesendet["payment_request"] == "lnbc1rechnung"
    assert d["betrag"] == 50_000 and d["gebuehr"] == 7


def test_beim_umschichten_ist_selbstzahlung_AN():
    """Genau hier -- und nur hier. Beim Bezahlen einer fremden Rechnung
    bleibt sie aus, das haelt test_die_gebuehrengrenze_geht_immer_mit fest."""
    a = Schichtattrappe()
    lnd.umschichten(a, "12345", KENNUNG, 50_000, 100)
    assert a.gesendet["allow_self_payment"] is True


def test_richtung_und_rueckweg_werden_vorgegeben():
    """Ohne beides sucht LND sich einen beliebigen Rundweg -- und schichtet
    womoeglich genau falschherum um."""
    import base64 as b64
    a = Schichtattrappe()
    lnd.umschichten(a, "12345", KENNUNG, 50_000, 100)
    assert a.gesendet["outgoing_chan_ids"] == ["12345"]
    assert b64.b64decode(a.gesendet["last_hop_pubkey"]).hex() == KENNUNG
    assert a.gesendet["fee_limit_sat"] == "100"


def test_umschichten_prueft_seine_eingaben():
    a = Schichtattrappe()
    with pytest.raises(lnd.LndFehler):        # Ziel keine Kennung
        lnd.umschichten(a, "12345", "abc", 50_000, 100)
    with pytest.raises(lnd.LndFehler):        # kein Ausgangskanal
        lnd.umschichten(a, "", KENNUNG, 50_000, 100)
    with pytest.raises(lnd.LndFehler):        # kein Betrag
        lnd.umschichten(a, "12345", KENNUNG, 0, 100)
    assert a.ausgestellt is None, "nichts davon darf eine Rechnung erzeugen"


def test_ein_gescheiterter_rundweg_nennt_den_grund():
    a = Schichtattrappe([
        {"result": {"status": "IN_FLIGHT"}},
        {"result": {"status": "FAILED",
                    "failure_reason": "FAILURE_REASON_NO_ROUTE"}}])
    with pytest.raises(lnd.LndFehler, match="NO_ROUTE"):
        lnd.umschichten(a, "12345", KENNUNG, 50_000, 100)


def test_bleibt_die_antwort_aus_nennt_das_umschichten_seine_kennung():
    """DER BEFUND VOM 24.09.2026: mehr als ein LDK-Kanal gleichzeitig
    annimmt, LND teilte auf, der zweite Teil kam nie los -- und die Oberflaeche wusste
    danach nicht, WELCHE Zahlung sie weiterverfolgen soll."""
    a = Schichtattrappe([{"result": {"status": "IN_FLIGHT"}}, "ausbleiben"])
    with pytest.raises(lnd.ZahlungUnterwegs) as fehler:
        lnd.umschichten(a, "12345", KENNUNG, 50_000, 100)
    assert fehler.value.kennung == "cd" * 32
    # Weiterhin ein Beschaeftigt -- wer nur das kennt, behandelt es richtig.
    assert isinstance(fehler.value, lnd.Beschaeftigt)


class Verfolgattrappe:
    """TrackPaymentV2 -- ein Strom, dessen erste Meldung den Stand von jetzt
    traegt (router.swagger.json, v0.21.3-beta)."""

    def __init__(self, meldungen):
        self.meldungen = meldungen
        self.gefragt = None

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        self.gefragt = (pfad, daten, macaroon, methode)
        for m in self.meldungen:
            if m == "ausbleiben":
                raise lnd.Beschaeftigt("kein Wort innerhalb der Frist")
            yield m


def test_eine_zahlung_laesst_sich_weiterverfolgen():
    import base64 as b64
    a = Verfolgattrappe([
        {"result": {"status": "IN_FLIGHT"}},
        {"result": {"status": "SUCCEEDED", "value_sat": "20000",
                    "fee_sat": "3"}}])
    d = lnd.zahlung_abwarten(a, "cd" * 32)
    assert d == {"zustand": "angekommen", "betrag": 20_000, "gebuehr": 3,
                 "grund": ""}
    pfad, daten, macaroon, methode = a.gefragt
    # bytes im Pfad: URL-sicheres base64, prozentkodiert -- genau wie beim
    # Abwarten einer Rechnung. Das REST-Tor dekodiert es vor dem Routen.
    import urllib.parse
    assert pfad.startswith("/v2/router/track/")
    assert urllib.parse.unquote(pfad[len("/v2/router/track/"):]) == \
        b64.urlsafe_b64encode(bytes.fromhex("cd" * 32)).decode()
    assert "/" not in pfad[len("/v2/router/track/"):]
    assert daten is None and methode == "GET"
    assert macaroon == lnd.EIGENES_MACAROON


def test_eine_gescheiterte_zahlung_nennt_ihren_grund():
    a = Verfolgattrappe([{"result": {
        "status": "FAILED", "failure_reason": "FAILURE_REASON_TIMEOUT"}}])
    d = lnd.zahlung_abwarten(a, "cd" * 32)
    assert d["zustand"] == "gescheitert"
    assert d["grund"] == "FAILURE_REASON_TIMEOUT"


def test_ohne_endgueltigen_stand_ist_sie_noch_unterwegs():
    """Die Frist um ist kein Fehler -- es hat sich eben noch nichts getan."""
    a = Verfolgattrappe([{"result": {"status": "IN_FLIGHT"}}, "ausbleiben"])
    assert lnd.zahlung_abwarten(a, "cd" * 32)["zustand"] == "unterwegs"


def test_eine_unbrauchbare_kennung_fragt_gar_nicht_erst():
    a = Verfolgattrappe([])
    with pytest.raises(lnd.LndFehler):
        lnd.zahlung_abwarten(a, "keine-kennung")
    assert a.gefragt is None


def test_rechnungen_ausstellen_braucht_das_recht_dafuer():
    """invoices:write kam am 12.09.2026 dazu. Ohne es koennte die Anwendung
    nicht umschichten -- und auch nie etwas empfangen."""
    assert ("invoices", "write") in lnd.EIGENE_RECHTE


# ── Einen Kanal schliessen (12.09.2026) ────────────────────────────────────
#
# Der Betreiber: "kann ich dann auch selber ein kanal kuendigen oder schliessen?"
#
# Bis dahin nicht -- meine Begruendung war zu kurz. Sein eigener Satz vom
# 30.08.2026 trifft es besser: nichts dahin ueberweisen, solange man es nicht
# zurueckschicken kann.

PUNKT = "ab" * 32 + ":1"


class Schliessattrappe:
    def __init__(self, meldungen=None):
        import base64 as b64
        roh = bytes.fromhex("cd" * 32)[::-1]
        # "is None", nicht "or": eine LEERE Liste ist hier ein Fall und
        # keine fehlende Angabe -- genau den prueft ein Test weiter unten.
        self.meldungen = [
            {"result": {"close_pending": {"txid": b64.b64encode(roh).decode(),
                                          "output_index": 0}}}
        ] if meldungen is None else meldungen
        self.pfad = ""
        self.methode = ""

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        self.pfad = pfad
        self.methode = methode
        for m in self.meldungen:
            yield m


def test_schliessen_geht_als_delete_auf_den_kanalpunkt():
    a = Schliessattrappe()
    d = lnd.kanal_schliessen(a, PUNKT, 5)
    assert a.methode == "DELETE"
    assert a.pfad.startswith("/v1/channels/" + "ab" * 32 + "/1?")
    assert "force=false" in a.pfad and "sat_per_vbyte=5" in a.pfad
    assert d["erzwungen"] is False


def test_die_schliesskennung_kommt_richtigherum():
    """Dieselbe Falle wie beim Oeffnen: LND liefert die Bytes rueckwaerts."""
    assert lnd.kanal_schliessen(Schliessattrappe(), PUNKT, 5)["txid"] \
        == "cd" * 32


def test_beim_erzwingen_setzen_wir_keine_gebuehr():
    """Die Verpflichtungstransaktion steht laengst fest und traegt ihre
    eigene Gebuehr -- eine mitgeschickte waere wirkungslos und irrefuehrend."""
    a = Schliessattrappe()
    d = lnd.kanal_schliessen(a, PUNKT, 5, erzwingen=True)
    assert "force=true" in a.pfad
    assert "sat_per_vbyte" not in a.pfad
    assert d["erzwungen"] is True


def test_ein_unlesbarer_kanalpunkt_wird_abgefangen():
    a = Schliessattrappe()
    for falsch in ("", "abc", "ab" * 32, "ab" * 32 + ":x"):
        with pytest.raises(lnd.LndFehler):
            lnd.kanal_schliessen(a, falsch, 5)
    assert a.pfad == "", "nichts davon darf LND erreichen"


def test_ohne_schliesstransaktion_gibt_es_keine_erfolgsmeldung():
    """Ein Strom, der endet, ohne dass etwas steht, ist kein Erfolg."""
    with pytest.raises(lnd.LndFehler):
        lnd.kanal_schliessen(Schliessattrappe(meldungen=[]), PUNKT, 5)


# ── Der eigene Turm (12.09.2026) ───────────────────────────────────────────
#
# Der Betreiber: "unsere lightning node kann ja schon ein eigender watch tower sein
# .. und wenn andere unsere watch tower benutzen kann bekommen wir doch auch
# gebueren oder?"
#
# Kann sie, und tut es seit Tag eins. Gebuehren gibt es dafuer aber nicht --
# nachgelesen in LNDs eigener Doku: "an altruist watchtower returns all of the
# victim's funds (minus on-chain fees) without taking a cut", und "reward
# watchtowers will be enabled in a subsequent release".
#
# Und wie viele Kanaele der Turm bewacht, erfaehrt man NICHT: GetInfo liefert
# genau drei Felder. Das ist kein Versaeumnis, sondern die Bauart -- der Turm
# bekommt verschluesselte Paeckchen, die er selbst nicht oeffnen kann.

class EigenerTurmAttrappe:
    def __init__(self, antwort):
        self.antwort = antwort
        self.pfad = ""

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.pfad = pfad
        return self.antwort


def test_die_eigene_turmadresse_wird_herausgegeben():
    """Ohne sie kann niemand diesen Turm eintragen."""
    a = EigenerTurmAttrappe({"pubkey": "03aa", "listeners": ["0.0.0.0:9911"],
                             "uris": ["03aa@abc.onion:9911"]})
    d = lnd.eigener_turm(a)
    assert a.pfad == "/v2/watchtower/server"
    assert d["aktiv"] is True
    assert d["uris"] == ["03aa@abc.onion:9911"]


def test_ohne_turm_ist_er_nicht_aktiv():
    d = lnd.eigener_turm(EigenerTurmAttrappe({}))
    assert d["aktiv"] is False and d["uris"] == []


# ── Der HTLC-Strom (12.09.2026) ────────────────────────────────────────────
#
# Der Betreiber: "koennen wir noch den HTLC-Strom mit rein nehmen?"
#
# Bis hierher las die Anwendung /v1/switch -- die Historie der ABGESCHLOSSENEN
# Weiterleitungen. Die sagt, was gelungen ist. Das Betriebswissen steckt im
# Gegenteil: ein LinkFailEvent traegt einen Grund, und "INSUFFICIENT_BALANCE"
# heisst nicht "es ging etwas schief", sondern "DIESER Kanal ist leer".

class Stromattrappe:
    def __init__(self, meldungen):
        self.meldungen = meldungen
        self.pfad = ""
        self.methode = ""

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        self.pfad = pfad
        self.methode = methode
        for m in self.meldungen:
            yield m


def _ereignis(feld, **rest):
    inhalt = {"info": {"incoming_amt_msat": "1005000",
                       "outgoing_amt_msat": "1000000"}}
    inhalt.update(rest)
    return {"result": {"timestamp_ns": "1700000000000000000",
                       "incoming_channel_id": "111",
                       "outgoing_channel_id": "222", feld: inhalt}}


def test_der_strom_haengt_sich_lesend_an():
    """offchain:read genuegt -- Zuhoeren bewegt nichts."""
    a = Stromattrappe([_ereignis("forward_event")])
    list(lnd.htlc_strom(a))
    assert a.pfad == "/v2/router/htlcevents" and a.methode == "GET"


def test_kein_zeitlimit_heisst_kein_zeitlimit(tmp_path, monkeypatch):
    """DER BEFUND VOM 17.09.2026, in das Betriebsprotokoll gefunden.

    Der HTLC-Dauerlaeufer rief `strom(..., zeitlimit=None)` auf -- gemeint
    war "das ist ein Strom, der wartet". `timeout=zeitlimit or
    self.zeitlimit` machte daraus die Vorgabe von fuenf Sekunden. Alle fuenf
    Sekunden lief die Leseuhr ab, der Strom riss ab und haengte sich neu an:
    rund 17.000 Mal am Tag. Ohne Kanaele war das Laerm -- mit Kanaelen waere
    in jedem Abrissfenster ein HTLC-Ereignis verloren, denn LND hebt sie
    nicht auf.

    Drei Faelle, drei verschiedene Antworten. Vor dem Fix waren es zwei.
    """
    _ohne_tls(monkeypatch)
    gesehen = []

    class Zeilen:
        def __enter__(self):
            return [b'{"result": {}}\n']

        def __exit__(self, *_):
            return False

    def urlopen(anfrage, timeout="nicht gefragt", context=None):
        gesehen.append(timeout)
        return Zeilen()
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    knoten = _knoten(tmp_path, mit_macaroon=True)
    list(knoten.strom("/v2/router/htlcevents"))                   # nicht gesagt
    list(knoten.strom("/v2/router/htlcevents", zeitlimit=None))   # keines
    list(knoten.strom("/v2/router/htlcevents", zeitlimit=30.0))   # genau die
    assert gesehen == [knoten.zeitlimit, None, 30.0]


def test_eine_ausdrueckliche_null_bleibt_eine_null(tmp_path, monkeypatch):
    """Dieselbe Falle im Einzelaufruf: `zeitlimit or self.zeitlimit` haette
    aus einer 0 still die Vorgabe gemacht."""
    _ohne_tls(monkeypatch)
    gesehen = []

    def urlopen(anfrage, timeout="nicht gefragt", context=None):
        gesehen.append(timeout)
        return Antwort({})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    knoten = _knoten(tmp_path, mit_macaroon=True)
    knoten.ruf("/v1/state", macaroon="")
    knoten.ruf("/v1/state", macaroon="", zeitlimit=0)
    assert gesehen == [knoten.zeitlimit, 0]


def test_millisatoshi_werden_umgerechnet():
    """LND rechnet hier in MILLIsatoshi. Wer das uebersieht, zeigt
    tausendfache Betraege."""
    d = list(lnd.htlc_strom(Stromattrappe([_ereignis("forward_event")])))[0]
    assert d["betrag"] == 1000        # 1.000.000 msat
    assert d["gebuehr"] == 5          # 5.000 msat Differenz


def test_der_grund_eines_linkfehlers_ueberlebt():
    """DAS ist der Punkt am ganzen Strom."""
    d = list(lnd.htlc_strom(Stromattrappe([
        _ereignis("link_fail_event", failure_detail="INSUFFICIENT_BALANCE",
                  wire_failure="TEMPORARY_CHANNEL_FAILURE")])))[0]
    assert d["art"] == "link_fehl"
    # failure_detail ist die genauere der beiden Angaben.
    assert d["grund"] == "INSUFFICIENT_BALANCE"
    assert d["raus_kanal"] == "222"


def test_die_vier_arten_werden_auseinandergehalten():
    """Gelungen, unterwegs gescheitert und BEI UNS gescheitert sind drei
    verschiedene Auskuenfte -- nur die letzte ist ein Handgriff."""
    arten = [list(lnd.htlc_strom(Stromattrappe([_ereignis(feld)])))[0]["art"]
             for feld, _ in lnd.HTLC_ARTEN]
    assert arten == ["weiterleiten", "erledigt", "fehl", "link_fehl"]


def test_ein_erfolgreiches_ereignis_hat_keinen_grund():
    """Sonst stuende bei jeder gelungenen Weiterleitung ein leerer Grund --
    und die Auswertung zaehlte ihn mit."""
    d = list(lnd.htlc_strom(Stromattrappe([_ereignis("settle_event")])))[0]
    assert d["grund"] is None


def test_unbekannte_meldungen_stoeren_den_strom_nicht():
    """LND kann Felder dazubekommen. Ein unbekanntes Ereignis darf den Strom
    nicht anhalten -- dann waere ein Update das Ende der Auswertung."""
    a = Stromattrappe([{"result": {}}, {"result": {"was_neues": {}}},
                       _ereignis("settle_event")])
    assert len(list(lnd.htlc_strom(a))) == 1


# ── Verbindungen: Leitungen, nicht Kanaele (14.09.2026) ────────────────────

class Peerattrappe:
    def __init__(self, peers):
        self.peers = peers
        self.aufrufe = []

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        self.aufrufe.append((pfad, macaroon))
        assert pfad == "/v1/peers" and daten is None
        return {"peers": self.peers}


def test_eine_verbindung_ist_noch_kein_kanal():
    """Bis zum 14.09.2026 hiess beides "Gegenstellen". Die Liste haelt es
    auseinander: wer nur verbunden ist, steht dort ausdruecklich ohne Kanal."""
    partner = "03" + "cd" * 32
    a = Peerattrappe([
        {"pub_key": KENNUNG, "address": "198.51.100.4:9735", "inbound": True,
         "sync_type": "PASSIVE_SYNC"},
        {"pub_key": partner, "address": "x.onion:9735", "inbound": False,
         "sync_type": "ACTIVE_SYNC"},
    ])
    liste = lnd.verbindungen(a, [{"kennung": partner, "gegenstelle": "ACINQ"}])
    assert [v["mit_kanal"] for v in liste] == [True, False], "Kanalpartner zuerst"
    assert liste[0]["name"] == "ACINQ" and liste[1]["name"] == ""
    assert liste[0]["netzkarte"] is True and liste[1]["netzkarte"] is False
    assert liste[1]["eingehend"] is True
    assert a.aufrufe == [("/v1/peers", "readonly")], \
        "peers:read steckt im readonly.macaroon -- kein neues Recht noetig"


def test_der_abgleich_wird_auch_als_nummer_erkannt():
    a = Peerattrappe([{"pub_key": KENNUNG, "sync_type": 3}])
    assert lnd.verbindungen(a, [])[0]["netzkarte"] is True


def test_eine_verbindung_zeigt_keine_fremde_ip():
    """Bei eingehenden Verbindungen ist die Adresse die eines anderen --
    womoeglich sein Anschluss zu Hause. Sie hat in der Liste nichts zu
    suchen."""
    a = Peerattrappe([{"pub_key": KENNUNG, "address": "203.0.113.9:51234",
                       "inbound": True}])
    assert "203.0.113.9" not in str(lnd.verbindungen(a, []))



# ── Jede Anfrage trifft eine echte LND-Route ───────────────────────────────
#
# Befund vom 15.09.2026, bei dem ersten Rueckweg mit echtem Geld: die
# Kostenschaetzung ging als POST hinaus, LND kennt sie nur als GET und
# antwortete "501: Method Not Allowed". Weil "Jetzt senden" erst nach der
# Schaetzung aufgeht, war Senden am echten Knoten nie moeglich. Die Attrappen
# hatten Pfade verglichen, nie Methoden.
#
# Diese Tests fragen deshalb nicht eine Attrappe, sondern LNDs eigene
# Routentabelle (lnd_rest_routen.tsv, erzeugt aus den yaml-Dateien von
# v0.21.3-beta): jede Anfrage, die lnd.py wirklich baut, muss dort mit
# Methode UND Pfad stehen.

KENNUNG_TEST = "02" + "ab" * 32


def _mit_eigenem(tmp_path):
    """Ein Knoten, der auch das EIGENE Macaroon auf der Platte hat --
    _knoten legt nur das readonly an."""
    knoten = _knoten(tmp_path, mit_macaroon=True)
    (knoten.macaroons / f"{lnd.EIGENES_MACAROON}.macaroon").write_bytes(b"\x00\x01\xff")
    return knoten
KANALPUNKT_TEST = "cd" * 32 + ":0"
KENNUNG_ZAHLUNG = "ab" * 32      # 32 Byte Zahlungshash, in Hex


def _routen():
    import re
    tabelle = []
    datei = Path(__file__).with_name("lnd_rest_routen.tsv")
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        if not zeile or zeile.startswith("#"):
            continue
        methode, muster, _rpc = zeile.split("\t")
        tabelle.append((methode, re.compile(
            "^" + re.sub(r"\{[^}]+\}", "[^/]+", muster) + "$")))
    return tabelle


def _trifft_route(methode, url):
    from urllib.parse import urlsplit
    pfad = urlsplit(url).path
    return any(m == methode and muster.match(pfad) for m, muster in _routen())


# Funktionen mit knoten, die LND gar nicht fragen -- ausdruecklich benannt,
# damit sie nicht still aus der Pruefung fallen.
#   macaroon_da: sieht nur nach, ob die Macaroon-Datei auf der Platte liegt.
OHNE_ANFRAGE = {"macaroon_da"}

AUFRUFE = [
    ("zustand", lambda k: lnd.zustand(k)),
    ("erzeuge_seed", lambda k: lnd.erzeuge_seed(k)),
    ("lege_wallet_an", lambda k: lnd.lege_wallet_an(
        k, "ein-langes-wallet-passwort", ["abandon"] * 24)),
    ("entsperre", lambda k: lnd.entsperre(k, "ein-langes-wallet-passwort")),
    ("sicherung_holen", lambda k: lnd.sicherung_holen(k)),
    ("sicherung_kanalpunkte", lambda k: lnd.sicherung_kanalpunkte(k, "AAAA")),
    ("sicherung_pruefen", lambda k: lnd.sicherung_pruefen(k, "AAAA")),
    ("uebersicht", lambda k: lnd.uebersicht(k)),
    ("guthaben", lambda k: lnd.guthaben(k)),
    ("bewegungen", lambda k: lnd.bewegungen(k)),
    ("ruecklage", lambda k: lnd.ruecklage(k)),
    ("kanaele", lambda k: lnd.kanaele(k)),
    ("ausstehende_kanaele", lambda k: lnd.ausstehende_kanaele(k)),
    ("verbindungen", lambda k: lnd.verbindungen(k, [])),
    ("gegenstellen", lambda k: lnd.gegenstellen(k)),
    ("netzgraph", lambda k: lnd.netzgraph(k)),
    ("weiterleitungen", lambda k: lnd.weiterleitungen(k)),
    ("unterschreibe", lambda k: lnd.unterschreibe(k, "hallo")),
    ("backe_macaroon", lambda k: lnd.backe_macaroon(k)),
    ("einzahladresse", lambda k: lnd.einzahladresse(k)),
    ("pruefe_unterschrift", lambda k: lnd.pruefe_unterschrift(
        k, "hallo", "d" * 104)),
    ("kosten_schaetzen", lambda k: lnd.kosten_schaetzen(k, "bc1qziel", 2000)),
    ("sende", lambda k: lnd.sende(k, "bc1qziel", 2000, 5)),
    ("wegwissen", lambda k: lnd.wegwissen(k)),
    ("gebuehr_erhoehen", lambda k: lnd.gebuehr_erhoehen(
        k, "a" * 64, 1, 12, hoechstens_sat=4000)),
    ("verbinde", lambda k: lnd.verbinde(k, KENNUNG_TEST + "@example.onion:9735")),
    ("verbinde_gegenstelle",
     lambda k: lnd.verbinde_gegenstelle(k, KENNUNG_TEST + "@example.onion:9735")),
    ("_adressen_aus_graph", lambda k: lnd._adressen_aus_graph(k, KENNUNG_TEST)),
    ("kanal_oeffnen", lambda k: lnd.kanal_oeffnen(
        k, KENNUNG_TEST + "@1.2.3.4:9735", 100_000, 5)),
    ("gegenstelle_ansehen", lambda k: lnd.gegenstelle_ansehen(k, KENNUNG_TEST)),
    ("wachtuerme", lambda k: lnd.wachtuerme(k)),
    ("wachturm_zaehler", lambda k: lnd.wachturm_zaehler(k)),
    ("eigener_turm", lambda k: lnd.eigener_turm(k)),
    ("wachturm_eintragen", lambda k: lnd.wachturm_eintragen(
        k, KENNUNG_TEST + "@1.2.3.4:9911")),
    ("wachturm_entfernen", lambda k: lnd.wachturm_entfernen(k, KENNUNG_TEST)),
    ("rechnung_lesen", lambda k: lnd.rechnung_lesen(k, "lnbc1500n1pbeispiel")),
    ("zahle", lambda k: lnd.zahle(k, "lnbc1500n1pbeispiel", 10)),
    ("rechnung_ausstellen", lambda k: lnd.rechnung_ausstellen(k, 1000)),
    ("rechnung_erstellen", lambda k: lnd.rechnung_erstellen(k, 1000, "Test")),
    ("rechnungen", lambda k: lnd.rechnungen(k)),
    ("rechnung_nachsehen", lambda k: lnd.rechnung_nachsehen(k, KENNUNG_ZAHLUNG)),
    ("rechnung_abwarten", lambda k: lnd.rechnung_abwarten(k, KENNUNG_ZAHLUNG)),
    ("rechnung_stornieren",
     lambda k: lnd.rechnung_stornieren(k, KENNUNG_ZAHLUNG)),
    ("zahlung_abwarten", lambda k: lnd.zahlung_abwarten(k, "cd" * 32)),
    ("umschichten", lambda k: lnd.umschichten(
        k, "123456789", KENNUNG_TEST, 1000, 10)),
    ("htlc_strom", lambda k: next(iter(lnd.htlc_strom(k)))),
    ("kanal_schliessen", lambda k: lnd.kanal_schliessen(k, KANALPUNKT_TEST, 5)),
    ("setze_gebuehren", lambda k: lnd.setze_gebuehren(k, 1000, 100)),
]


@pytest.mark.parametrize("name,aufruf", AUFRUFE, ids=[n for n, _ in AUFRUFE])
def test_jede_anfrage_trifft_eine_echte_lnd_route(tmp_path, monkeypatch,
                                                 name, aufruf):
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    for datei in ("satcortex", "admin"):
        (knoten.macaroons / f"{datei}.macaroon").write_bytes(b"\x00\x01\xff")
    gesehen = []

    def urlopen(anfrage, timeout=None, context=None):
        gesehen.append((anfrage.get_method(), anfrage.full_url))
        return Antwort({})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    try:
        aufruf(knoten)
    except Exception:  # noqa: BLE001 -- die Antwort ist leer; es zaehlt die Anfrage
        pass
    assert gesehen, f"{name}: keine Anfrage aufgezeichnet -- Argumente pruefen"
    falsch = [(m, u) for m, u in gesehen if not _trifft_route(m, u)]
    assert not falsch, f"{name}: keine LND-Route fuer {falsch}"


def test_jede_lnd_funktion_steht_in_der_routenpruefung():
    """Wer eine neue Funktion mit knoten schreibt, muss sie oben eintragen --
    sonst prueft niemand ihre Methode gegen LND."""
    import inspect
    mit_knoten = {
        n for n, f in inspect.getmembers(lnd, inspect.isfunction)
        if f.__module__ == lnd.__name__
        and list(inspect.signature(f).parameters)[:1] == ["knoten"]}
    assert mit_knoten - {n for n, _ in AUFRUFE} - OHNE_ANFRAGE == set()
    # Und eine Ausnahme, die es nicht mehr gibt, faellt auch auf.
    assert OHNE_ANFRAGE <= mit_knoten


def test_die_kostenschaetzung_ist_ein_get_mit_der_map_in_der_url(tmp_path,
                                                                 monkeypatch):
    """LNDs EstimateFee gibt es ueber REST nur als GET (lightning.yaml,
    v0.21.3-beta). Die Map AddrToAmount liest grpc-gateway v2.16.0 aus der
    URL als Name[Schluessel]=Wert (runtime/query.go)."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    (knoten.macaroons / "satcortex.macaroon").write_bytes(b"\x00\x01\xff")
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["url"] = anfrage.full_url
        gesehen["rumpf"] = anfrage.data
        return Antwort({"fee_sat": "141", "sat_per_vbyte": "1"})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.kosten_schaetzen(knoten, "bc1qziel", 2000, 6)
    assert d == {"gebuehr_sat": 141, "satz_sat_vb": 1}
    assert gesehen["methode"] == "GET"
    assert gesehen["rumpf"] is None
    from urllib.parse import parse_qs, urlsplit
    teile = urlsplit(gesehen["url"])
    assert teile.path == "/v1/transactions/fee"
    abfrage = parse_qs(teile.query)
    assert abfrage["AddrToAmount[bc1qziel]"] == ["2000"]
    assert abfrage["target_conf"] == ["6"]
    assert abfrage["min_confs"] == ["1"]
    assert abfrage["spend_unconfirmed"] == ["false"]


def test_die_bewegungen_kommen_vollstaendig_und_sortiert(tmp_path, monkeypatch):
    """GetTransactions, v0.21.3-beta: int64 als Zeichenkette, ausgehend
    negativ, unbestaetigt mit num_confirmations 0 und block_height 0."""
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["url"] = anfrage.full_url
        return Antwort({"transactions": [
            {"tx_hash": "11" * 32, "amount": "50000", "num_confirmations": 120,
             "block_height": 899000, "time_stamp": "1757000000",
             "total_fees": "0", "label": "", "raw_tx_hex": "00"},
            {"tx_hash": "22" * 32, "amount": "-100250", "num_confirmations": 6,
             "block_height": 899114, "time_stamp": "1757100000",
             "total_fees": "250", "label": "0:openchannel:shortchanid-1"},
            {"tx_hash": "33" * 32, "amount": "2000", "num_confirmations": 0,
             "block_height": 0, "time_stamp": "1757200000",
             "total_fees": "0", "label": ""},
        ]})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.bewegungen(_knoten(tmp_path, mit_macaroon=True))
    assert gesehen["methode"] == "GET"
    assert gesehen["url"] == "https://lnd:8080/v1/transactions"
    assert [b["txid"] for b in d["bewegungen"]] == ["33" * 32, "22" * 32, "11" * 32]
    kanal = d["bewegungen"][1]
    assert kanal == {"txid": "22" * 32, "ziel": "", "betrag_sat": -100250,
                     "bestaetigungen": 6, "hoehe": 899114,
                     "zeit_s": 1757100000, "gebuehr_sat": 250,
                     "art": "kanal_auf",
                     # Seit dem 22.09.2026: der Ausgang, der uns gehoert --
                     # ohne ihn laesst sich die Gebuehr nicht nachbessern.
                     # Diese Attrappe nennt keine Ausgaenge, also None.
                     "eigener_ausgang": None}
    # Nichts, was die Oberflaeche nicht braucht -- keine Rohdaten.
    assert "raw_tx_hex" not in d["bewegungen"][2]
    assert d["weitere"] == 0


def test_die_bewegungen_sind_gedeckelt(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)
    monkeypatch.setattr(lnd.urllib.request, "urlopen",
                        lambda anfrage, timeout=None, context=None: Antwort(
                            {"transactions": [
                                {"tx_hash": f"{i:064x}", "amount": "1",
                                 "num_confirmations": 1, "block_height": i}
                                for i in range(1, 8)]}))
    d = lnd.bewegungen(_knoten(tmp_path, mit_macaroon=True), hoechstens=5)
    assert len(d["bewegungen"]) == 5
    assert d["weitere"] == 2
    assert d["bewegungen"][0]["hoehe"] == 7


# ── Empfangen ueber Lightning (16.09.2026) ─────────────────────────────────

def test_eine_rechnung_wird_richtig_bestellt(tmp_path, monkeypatch):
    """AddInvoice: POST auf /v1/invoices, r_hash kommt als base64 zurueck."""
    import base64 as b64
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["url"] = anfrage.full_url
        gesehen["rumpf"] = json.loads(anfrage.data.decode("utf-8"))
        return Antwort({"payment_request": "lnbc1500n1pbeispiel",
                        "r_hash": b64.b64encode(bytes.fromhex("ab" * 32)).decode()})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.rechnung_erstellen(_mit_eigenem(tmp_path), 1500, "Kaffee", 900)
    assert gesehen["methode"] == "POST"
    assert gesehen["url"] == "https://lnd:8080/v1/invoices"
    assert gesehen["rumpf"]["value"] == "1500"
    assert gesehen["rumpf"]["memo"] == "Kaffee"
    assert gesehen["rumpf"]["expiry"] == "900"
    assert d["rechnung"] == "lnbc1500n1pbeispiel"
    assert d["kennung"] == "ab" * 32
    assert d["betrag_sat"] == 1500
    assert d["laeuft_ab_s"] > 0


def test_eine_rechnung_ohne_betrag_ist_erlaubt(tmp_path, monkeypatch):
    """Betrag 0 heisst: der Zahlende bestimmt ihn. LND kennt das, und eine
    Spende ohne festen Betrag ist der haeufigste Fall dafuer."""
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["rumpf"] = json.loads(anfrage.data.decode("utf-8"))
        return Antwort({"payment_request": "lnbc1pbeispiel"})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.rechnung_erstellen(_mit_eigenem(tmp_path))
    assert gesehen["rumpf"]["value"] == "0"
    assert d["betrag_sat"] == 0
    assert d["kennung"] == ""          # ohne r_hash keine erfundene Kennung


def test_ohne_rechnung_von_lnd_gibt_es_einen_fehler(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)
    monkeypatch.setattr(lnd.urllib.request, "urlopen",
                        lambda anfrage, timeout=None, context=None: Antwort({}))
    with pytest.raises(lnd.LndFehler):
        lnd.rechnung_erstellen(_mit_eigenem(tmp_path), 10)


def test_die_eigenen_rechnungen_kommen_mit_zustand(tmp_path, monkeypatch):
    import base64 as b64
    _ohne_tls(monkeypatch)
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["url"] = anfrage.full_url
        return Antwort({"invoices": [
            {"r_hash": b64.b64encode(bytes.fromhex("11" * 32)).decode(),
             "payment_request": "lnbc1", "memo": "alt", "value": "1000",
             "amt_paid_sat": "0", "creation_date": "1757000000",
             "settle_date": "0", "expiry": "3600", "state": "OPEN"},
            {"r_hash": b64.b64encode(bytes.fromhex("22" * 32)).decode(),
             "payment_request": "lnbc2", "memo": "Kaffee", "value": "2500",
             "amt_paid_sat": "2500", "creation_date": "1757100000",
             "settle_date": "1757100060", "expiry": "3600", "state": "SETTLED"},
        ]})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    d = lnd.rechnungen(_knoten(tmp_path, mit_macaroon=True))
    assert gesehen["methode"] == "GET"
    assert "reversed=true" in gesehen["url"]
    # Die juengste zuerst, egal in welcher Reihenfolge LND liefert.
    assert [r["kennung"] for r in d["rechnungen"]] == ["22" * 32, "11" * 32]
    bezahlt = d["rechnungen"][0]
    assert bezahlt["zustand"] == "bezahlt"
    assert bezahlt["bezahlt_sat"] == 2500
    assert bezahlt["zweck"] == "Kaffee"
    assert d["rechnungen"][1]["zustand"] == "offen"
    assert d["rechnungen"][1]["laeuft_ab_s"] == 1757000000 + 3600


def test_bei_einem_ausgang_steht_das_ziel_dabei(tmp_path, monkeypatch):
    """Befund vom 16.09.2026: an WEN gesendet wurde, stand nur im Protokoll.
    Die eigene Wechselgeld-Ausgabe zaehlt dabei nicht als Ziel."""
    _ohne_tls(monkeypatch)
    monkeypatch.setattr(lnd.urllib.request, "urlopen",
                        lambda anfrage, timeout=None, context=None: Antwort(
                            {"transactions": [
                                {"tx_hash": "aa" * 32, "amount": "-3141",
                                 "num_confirmations": 1, "block_height": 915000,
                                 "total_fees": "141", "output_details": [
                                     {"address": "bc1qwechselgeld",
                                      "is_our_address": True},
                                     {"address": "bc1qempfaenger",
                                      "is_our_address": False}]},
                                {"tx_hash": "bb" * 32, "amount": "40000",
                                 "num_confirmations": 2, "block_height": 914900,
                                 "output_details": [
                                     {"address": "bc1pmeine",
                                      "is_our_address": True}]},
                            ]}))
    d = lnd.bewegungen(_knoten(tmp_path, mit_macaroon=True))
    aus = [b for b in d["bewegungen"] if b["betrag_sat"] < 0][0]
    ein = [b for b in d["bewegungen"] if b["betrag_sat"] > 0][0]
    assert aus["ziel"] == "bc1qempfaenger"
    assert aus["gebuehr_sat"] == 141
    # Bei einem EINGANG waere die eigene Adresse keine Auskunft ueber "wohin".
    assert ein["ziel"] == ""



# ---------------------------------------------------------------- brocken
#
# Der einzige Aufruf, der nicht in den Speicher passt: DescribeGraph liefert
# den ganzen Netzgraphen in EINEM Dokument. "ruf" wuerde ihn komplett lesen
# und durch json.loads schicken -- in einem Container mit 400 MB Grenze ist
# das der Tag, an dem die Anwendung stirbt, sobald das Netz gross genug ist.

class Strombahn:
    """Ein urlopen-Ergebnis, das sich HAEPPCHENWEISE lesen laesst."""

    def __init__(self, roh: bytes):
        self._puffer = BytesIO(roh)
        self.gelesen = 0

    def read(self, wieviel=-1):
        stueck = self._puffer.read(wieviel)
        self.gelesen += len(stueck)
        return stueck

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_brocken_liefert_die_antwort_stueckweise(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)
    roh = b"x" * 1000
    gesehen = {}

    def urlopen(anfrage, timeout=None, context=None):
        gesehen["methode"] = anfrage.get_method()
        gesehen["macaroon"] = anfrage.headers.get("Grpc-metadata-macaroon")
        return Strombahn(roh)
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    knoten = _knoten(tmp_path, mit_macaroon=True)
    stuecke = list(knoten.brocken("/v1/graph", haeppchen=256))
    assert len(stuecke) == 4
    assert b"".join(stuecke) == roh
    assert gesehen["methode"] == "GET"
    assert gesehen["macaroon"]


def test_brocken_haelt_nie_alles_auf_einmal(tmp_path, monkeypatch):
    """Der eigentliche Punkt: wer nur den Anfang braucht, liest nur den
    Anfang. Bei einem Dokument von zweistelligen Megabyte ist das der
    Unterschied zwischen laufen und sterben."""
    _ohne_tls(monkeypatch)
    bahn = Strombahn(b"y" * 100_000)
    monkeypatch.setattr(lnd.urllib.request, "urlopen",
                        lambda *a, **k: bahn)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    strom = knoten.brocken("/v1/graph", haeppchen=1024)
    next(strom)
    next(strom)
    strom.close()
    assert bahn.gelesen == 2048


def test_brocken_ohne_macaroon_sagt_es(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=False)
    with pytest.raises(lnd.NichtErreichbar):
        list(knoten.brocken("/v1/graph"))


def test_brocken_uebersetzt_ein_zeitlimit(tmp_path, monkeypatch):
    import socket as sockets
    _ohne_tls(monkeypatch)

    def platzt(*a, **k):
        raise sockets.timeout("zu langsam")
    monkeypatch.setattr(lnd.urllib.request, "urlopen", platzt)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    with pytest.raises(lnd.Beschaeftigt):
        list(knoten.brocken("/v1/graph", zeitlimit=30.0))


def test_brocken_uebersetzt_einen_fehler_von_lnd(tmp_path, monkeypatch):
    _ohne_tls(monkeypatch)

    def platzt(*a, **k):
        raise urllib.error.HTTPError(
            "https://lnd:8080/v1/graph", 500, "kaputt", {},
            BytesIO(json.dumps({"message": "graph nicht bereit"}).encode()))
    monkeypatch.setattr(lnd.urllib.request, "urlopen", platzt)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    with pytest.raises(lnd.LndFehler) as fehler:
        list(knoten.brocken("/v1/graph"))
    assert "graph nicht bereit" in str(fehler.value)


# ── Verbinden, egal in welcher Form die Kennung kommt ──────────────────────
#
# Bis zum 19.09.2026 nahm dasselbe Eingabefeld zwei Formen an und verhielt
# sich verschieden:
#
#     02abc...@host:9735   ->  verbunden, Kanal geoeffnet
#     02abc...             ->  NICHT verbunden, und LND lehnte den Kanal ab
#
# Die Pruefung liess beide klaglos durch. Wer eine Kennung aus einem Explorer
# kopierte -- dort steht sie meist ohne Adresse -- bekam einen Fehler, den
# nichts erklaerte. Aus dem Betrieb, 19.09.2026: "ich wuesste jetzt nicht wie ich
# mich mit einem anderen knoten verbinden sollte".

class Verbindungsattrappe:
    """Ein Knoten, der den Graphen kennt und mitschreibt, wohin verbunden wird."""

    def __init__(self, adressen=("erste.onion:9735",), scheitern=()):
        self.adressen = list(adressen)
        self.scheitern = set(scheitern)
        self.versuche = []
        self.graph_gefragt = 0

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
        if pfad.startswith("/v1/graph/node/"):
            self.graph_gefragt += 1
            return {"node": {"addresses": [{"addr": a} for a in self.adressen]}}
        if pfad == "/v1/peers":
            wirt = daten["addr"]["host"]
            self.versuche.append(wirt)
            if wirt in self.scheitern:
                raise lnd.LndFehler("dial tcp: connection refused")
            return {}
        raise AssertionError("unerwartet: " + pfad)


def test_nur_die_kennung_genuegt_die_adresse_steht_im_eigenen_graphen():
    """DER Kern der Sache: der Knoten weiss die Adresse laengst -- er hat die
    Ankuendigung mitgehoert. Sie vom Nutzer zu verlangen war unnoetig."""
    a = Verbindungsattrappe(adressen=("ausm-graph.onion:9735",))
    assert lnd.verbinde_gegenstelle(a, KENNUNG) == "ausm-graph.onion:9735"
    assert a.graph_gefragt == 1
    assert a.versuche == ["ausm-graph.onion:9735"]


def test_mit_adresse_wird_der_graph_gar_nicht_erst_gefragt():
    """Wer die Adresse mitschickt, meint sie auch -- etwa bei einem Knoten,
    der noch gar nicht im Graphen steht. Genau der Fall aus des Betreibers
    Liquiditaets-Ring."""
    a = Verbindungsattrappe()
    zeile = KENNUNG + "@von-hand.onion:9735"
    assert lnd.verbinde_gegenstelle(a, zeile) == "von-hand.onion:9735"
    assert a.graph_gefragt == 0
    assert a.versuche == ["von-hand.onion:9735"]


def test_scheitert_die_erste_adresse_kommt_die_naechste_dran():
    a = Verbindungsattrappe(adressen=("kaputt.onion:9735", "geht.onion:9735"),
                            scheitern=("kaputt.onion:9735",))
    assert lnd.verbinde_gegenstelle(a, KENNUNG) == "geht.onion:9735"
    assert a.versuche == ["kaputt.onion:9735", "geht.onion:9735"]


def test_es_werden_nicht_beliebig_viele_adressen_durchprobiert():
    """Ein Knoten darf beliebig viele ankuendigen, und jede kostet im
    schlechtesten Fall ein volles Zeitlimit."""
    viele = tuple(f"a{i}.onion:9735" for i in range(9))
    a = Verbindungsattrappe(adressen=viele, scheitern=viele)
    with pytest.raises(lnd.LndFehler):
        lnd.verbinde_gegenstelle(a, KENNUNG)
    assert len(a.versuche) == lnd.VERBINDUNGSVERSUCHE


def test_ohne_adresse_im_graphen_sagt_es_die_meldung():
    a = Verbindungsattrappe(adressen=())
    with pytest.raises(lnd.LndFehler) as fehler:
        lnd.verbinde_gegenstelle(a, KENNUNG)
    assert "Kennung@Adresse:Port" in str(fehler.value)


def test_schon_verbunden_ist_kein_fehler():
    class Schon(Verbindungsattrappe):
        def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None):
            if pfad == "/v1/peers":
                raise lnd.LndFehler("500: already connected to peer")
            return super().ruf(pfad, macaroon, daten, zeitlimit)
    assert lnd.verbinde_gegenstelle(Schon(), KENNUNG) == ""


@pytest.mark.parametrize("falsch", ["", "abc", "z" * 66, "02aabb@wirt:9735"])
def test_eine_kennung_wird_geprueft_bevor_irgendwer_gefragt_wird(falsch):
    """Ein Lightning-Schluessel hat IMMER 66 Hexzeichen. Vorher ging jede
    Zeichenkette durch und LND antwortete mit einer gRPC-Meldung."""
    a = Verbindungsattrappe()
    with pytest.raises(lnd.LndFehler):
        lnd.verbinde_gegenstelle(a, falsch)
    assert a.versuche == [] and a.graph_gefragt == 0


# ── Die Gebuehr einer haengenden Ueberweisung erhoehen (22.09.2026) ────────


class _Mitschrift:
    """Eine Attrappe, die auch festhaelt, WAS geschickt wurde.

    Die Tests hier pruefen nicht nur das Ergebnis, sondern die Anfrage: bei
    LND entscheidet der genaue Feldname, ob eine Gebuehr erhoeht wird oder
    ob gar nichts passiert.
    """

    def __init__(self, antworten):
        self.antworten = antworten
        self.gesendet = {}

    def ruf(self, pfad, macaroon="readonly", daten=None, zeitlimit=None,
            methode=None):
        if daten is not None:
            self.gesendet[pfad.split("?")[0]] = daten
        schluessel = pfad.split("?")[0]
        if schluessel in self.antworten:
            return self.antworten[schluessel]
        raise AssertionError(f"unerwarteter Aufruf: {pfad}")

# ── Die Gebuehr einer haengenden Ueberweisung erhoehen (22.09.2026) ────────
#
# Beim Abgleich unserer Oberflaeche gegen das, was LND wirklich anbietet:
# walletrpc hat dreissig Routen, wir nutzten EINE. Darin steckt BumpFee --
# also genau die Antwort auf die Frage, die nach der gestrigen Arbeit als
# naechste kommt. Wir sagen jetzt ehrlich "die Ueberweisung kann unterwegs
# sein"; was fehlt, ist "sie haengt fest, was nun".

def test_die_bewegung_sagt_ob_sie_nachbesserbar_ist():
    """Nachbessern geht nur ueber einen Ausgang, der UNS gehoert -- das
    Wechselgeld. Ohne einen solchen kann LND nichts anhaengen, und dann darf
    die Oberflaeche den Knopf gar nicht erst anbieten."""
    k = _Mitschrift({"/v1/transactions": {"transactions": [
        {"tx_hash": "a" * 64, "amount": "-50000", "num_confirmations": "0",
         "block_height": "0", "time_stamp": "1758400000",
         "total_fees": "300", "label": "",
         "output_details": [
             {"is_our_address": False, "address": "bc1qfremd"},
             {"is_our_address": True, "address": "bc1qunser",
              "output_index": "1"}]},
        # Alles verschickt, kein Wechselgeld -- nicht nachbesserbar.
        {"tx_hash": "b" * 64, "amount": "-90000", "num_confirmations": "0",
         "block_height": "0", "time_stamp": "1758400001",
         "total_fees": "300", "label": "",
         "output_details": [
             {"is_our_address": False, "address": "bc1qfremd"}]},
    ]}})
    liste = lnd.bewegungen(k)["bewegungen"]
    nach = {b["txid"]: b["eigener_ausgang"] for b in liste}
    assert nach["a" * 64] == 1
    assert nach["b" * 64] is None


def test_nachbessern_schickt_genau_die_felder_die_lnd_kennt():
    """Gegen LNDs eigene Schnittstellenbeschreibung des gepinnten Tags
    geprueft (walletkit.swagger.json, v0.21.3-beta): outpoint mit txid_str
    und output_index, sat_per_vbyte als Zeichenkette, immediate."""
    k = _Mitschrift({"/v2/wallet/bumpfee": {}})
    lnd.gebuehr_erhoehen(k, "c" * 64, 1, 12, hoechstens_sat=4000)
    daten = k.gesendet["/v2/wallet/bumpfee"]
    assert daten["outpoint"] == {"txid_str": "c" * 64, "output_index": 1}
    assert daten["sat_per_vbyte"] == "12"
    assert daten["immediate"] is True
    # Eine Obergrenze ist PFLICHT -- ohne sie nimmt LND sich, was es fuer
    # noetig haelt. Dieselbe Entscheidung wie bei der Gebuehrengrenze einer
    # Lightning-Zahlung.
    assert daten["budget"] == "4000"


def test_nachbessern_ohne_obergrenze_gibt_es_nicht():
    k = _Mitschrift({"/v2/wallet/bumpfee": {}})
    with pytest.raises(ValueError):
        lnd.gebuehr_erhoehen(k, "c" * 64, 1, 12, hoechstens_sat=0)


# ── Mission Control: was LND ueber Wege gelernt hat (22.09.2026) ───────────
#
# Aus dem Abgleich gegen LNDs Umfang: routerrpc hat neunzehn Routen, wir
# nutzten zwei. Mission Control ist LNDs Gedaechtnis darueber, welche
# Gegenstellenpaare zuletzt versagt oder getragen haben -- und der
# urspruengliche Plan nennt es "den eigentlichen Engpass" fuers Weiterleiten.
#
# Die Antwort kann GROSS werden: ein Knoten mit Verkehr sammelt tausende
# Paare. Zusammengefasst wird deshalb HIER und nicht im Browser.

def test_das_wegwissen_wird_zusammengefasst_statt_durchgereicht():
    k = _Mitschrift({"/v2/router/mc": {"pairs": [
        {"node_from": "aa" * 33, "node_to": "bb" * 33,
         "history": {"fail_time": "1758400000", "fail_amt_sat": "50000",
                     "success_time": "0", "success_amt_sat": "0"}},
        {"node_from": "aa" * 33, "node_to": "cc" * 33,
         "history": {"fail_time": "0", "fail_amt_sat": "0",
                     "success_time": "1758400100",
                     "success_amt_sat": "120000"}},
        {"node_from": "dd" * 33, "node_to": "ee" * 33,
         "history": {"fail_time": "1758399000", "fail_amt_sat": "1000",
                     "success_time": "1758399500",
                     "success_amt_sat": "900"}},
    ]}})
    d = lnd.wegwissen(k, hoechstens=2)
    assert d["paare"] == 3
    assert d["mit_fehlschlag"] == 2
    assert d["mit_erfolg"] == 2
    # Nur die juengsten, und gedeckelt -- nicht tausende in den Browser.
    assert len(d["letzte"]) == 2
    assert d["letzte"][0]["zeitpunkt"] == 1_758_400_100


def test_das_wegwissen_nennt_die_grenze_die_es_gefunden_hat():
    """Der Nutzen der Zahl: unterhalb welchen Betrags ein Weg zuletzt trug,
    und ab welchem er versagte. Genau das sagt einem, ob es an der
    Liquiditaet liegt."""
    k = _Mitschrift({"/v2/router/mc": {"pairs": [
        {"node_from": "aa" * 33, "node_to": "bb" * 33,
         "history": {"fail_time": "1758400000", "fail_amt_sat": "50000",
                     "success_time": "1758399000",
                     "success_amt_sat": "20000"}},
    ]}})
    e = lnd.wegwissen(k)["letzte"][0]
    assert e["fehl_ab_sat"] == 50000
    assert e["trug_bis_sat"] == 20000
    assert e["von"].startswith("aa") and len(e["von"]) < 66


def test_ohne_gedaechtnis_ist_das_wegwissen_leer_und_nicht_kaputt():
    k = _Mitschrift({"/v2/router/mc": {}})
    d = lnd.wegwissen(k)
    assert d["paare"] == 0 and d["letzte"] == []


# ── Eine EINZELNE Rechnung: nachsehen, abwarten, zuruecknehmen ────────────
#
# Der Punkt, an dem das lautlos schiefgeht, ist die KENNUNG. Ueberall sonst
# in dieser Anwendung reist sie als Hex; diese drei Routen nehmen sie als
# bytes-Feld, und LNDs REST-Tor liest bytes als base64. Hex kaeme als Unsinn
# an -- und die Routenpruefung merkte davon NICHTS, denn Pfad und Methode
# waeren tadellos. Genau diese Klasse Fehler (richtige Route, falscher
# Inhalt) hat am 15.09.2026 das Senden am echten Knoten unmoeglich gemacht.
# Deshalb hier die Gegenprobe auf den Inhalt.

B64_KENNUNG = base64.b64encode(bytes.fromhex(KENNUNG_ZAHLUNG)).decode()


class Stromzeilen:
    """Ein urlopen-Ergebnis, das sich Zeile fuer Zeile lesen laesst."""

    def __init__(self, meldungen):
        self._zeilen = [json.dumps(m).encode("utf-8") + b"\n"
                        for m in meldungen]

    def __iter__(self):
        return iter(self._zeilen)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Zaehlstrom:
    """Zaehlt mit, wie viele Meldungen wirklich gelesen wurden."""

    def __init__(self, meldungen):
        self.meldungen = meldungen
        self.gelesen = 0
        self.pfad = ""
        self.methode = ""

    def strom(self, pfad, daten=None, macaroon="readonly", zeitlimit=None,
              methode=""):
        self.pfad, self.methode = pfad, methode
        for m in self.meldungen:
            self.gelesen += 1
            yield m


def _aufzeichnen(monkeypatch, nutzlast=None):
    """Jede Anfrage mitschreiben, statt sie zu beantworten."""
    gesehen = []

    def urlopen(anfrage, timeout=None, context=None):
        gesehen.append({"methode": anfrage.get_method(),
                        "url": anfrage.full_url, "rumpf": anfrage.data})
        return Antwort(nutzlast if nutzlast is not None else {})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)
    return gesehen


def test_die_zahlungskennung_reist_als_base64_und_nicht_als_hex(tmp_path,
                                                                monkeypatch):
    """grpc-gateway v2.16.0, runtime/convert.go: bytes kommen ueber base64
    herein -- erst das Standard-Alphabet, dann das URL-sichere, beide MIT
    Fuellzeichen. Eine ungefuellte Form scheitert dort, Hex erst recht."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    gesehen = _aufzeichnen(monkeypatch)

    lnd.rechnung_nachsehen(knoten, KENNUNG_ZAHLUNG)

    from urllib.parse import parse_qs, urlsplit
    teile = urlsplit(gesehen[0]["url"])
    assert gesehen[0]["methode"] == "GET"
    assert teile.path == "/v2/invoices/lookup"
    roh = parse_qs(teile.query)["payment_hash"][0]
    assert roh != KENNUNG_ZAHLUNG
    assert roh.endswith("="), "ohne Fuellzeichen scheitert Gos Decoder"
    assert base64.urlsafe_b64decode(roh) == bytes.fromhex(KENNUNG_ZAHLUNG)


def test_im_pfad_steht_die_url_sichere_form(tmp_path, monkeypatch):
    """Im PFAD ist sie Pflicht, nicht Geschmackssache: ein "/" aus dem
    Standard-Alphabet wuerde /v2/invoices/subscribe/{r_hash} zerschneiden und
    auf eine Route zeigen, die es nicht gibt. Die Kennung hier ist mit Absicht
    eine, deren Standard-Form voller Schraegstriche steckt."""
    _ohne_tls(monkeypatch)
    schraeg = "ff" * 32
    assert "/" in base64.b64encode(bytes.fromhex(schraeg)).decode()
    knoten = _knoten(tmp_path, mit_macaroon=True)
    gesehen = []

    # Der Strom MUSS hier etwas sagen. Schweigt er, faellt rechnung_abwarten
    # auf das Nachschlagen zurueck -- und dann prueft dieser Test eine Route,
    # die er gar nicht meint.
    def urlopen(anfrage, timeout=None, context=None):
        gesehen.append({"methode": anfrage.get_method(),
                        "url": anfrage.full_url, "rumpf": anfrage.data})
        return Stromzeilen([{"result": {
            "r_hash": base64.b64encode(bytes.fromhex(schraeg)).decode(),
            "state": "SETTLED", "value": "1000", "amt_paid_sat": "1000"}}])
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    assert lnd.rechnung_abwarten(knoten, schraeg)["zustand"] == "bezahlt"
    assert len(gesehen) == 1, "nach einer endgueltigen Meldung folgt kein Abruf"

    # Gepruefte Form ist die ENTSCHLUESSELTE. Ein "/" als %2F zu schreiben
    # rettet nichts: Gos net/http entschluesselt den Pfad, bevor
    # grpc-gateway ihn an den Schraegstrichen in Abschnitte zerlegt. Ein
    # Test, der nur die rohe Zeichenkette ansieht, waere gruen und der
    # Aufruf trotzdem auf einer Route, die es nicht gibt.
    from urllib.parse import unquote, urlsplit
    vorspann = "/v2/invoices/subscribe/"
    pfad = unquote(urlsplit(gesehen[0]["url"]).path)
    assert pfad.startswith(vorspann)
    rest = pfad[len(vorspann):]
    assert "/" not in rest, "Go macht aus %2F wieder / und zerschneidet die Route"
    assert "+" not in rest
    assert base64.urlsafe_b64decode(rest) == bytes.fromhex(schraeg)
    assert _trifft_route("GET", unquote(gesehen[0]["url"]))


def test_das_abwarten_kehrt_zurueck_sobald_bezahlt_ist():
    """SubscribeSingleInvoice schickt sofort den Stand von jetzt und danach
    jede Aenderung. Gewartet wird bis zur ersten endgueltigen -- und keine
    Zeile laenger, sonst haengt der Aufruf an einem Strom, der nie endet."""
    a = Zaehlstrom([
        {"result": {}},                     # leere Zwischenmeldung
        {"result": {"r_hash": B64_KENNUNG, "state": "OPEN", "value": "1000",
                    "creation_date": "1758600000", "expiry": "3600"}},
        {"result": {"r_hash": B64_KENNUNG, "state": "SETTLED", "value": "1000",
                    "amt_paid_sat": "1000", "settle_date": "1758600030",
                    "creation_date": "1758600000", "expiry": "3600"}},
        {"result": {"r_hash": B64_KENNUNG, "state": "OPEN"}},
    ])
    d = lnd.rechnung_abwarten(a, KENNUNG_ZAHLUNG)
    assert d["zustand"] == "bezahlt" and d["bezahlt_sat"] == 1000
    assert d["bezahlt_s"] == 1758600030
    assert a.gelesen == 3, "die letzte Meldung haette niemand mehr lesen duerfen"
    assert a.methode == "GET"


def test_eine_abgelaufene_frist_beim_abwarten_ist_kein_fehler():
    """Niemand hat bezahlt -- das ist der Normalfall, kein Zwischenfall. Wer
    die Ausnahme hier durchliesse, machte aus "noch nichts" ein "kaputt", und
    die Oberflaeche sagte bei jeder Runde einmal Fehler."""
    class Stillstand:
        pfad = ""

        def strom(self, *_a, **_k):
            raise lnd.Beschaeftigt("keine Meldung innerhalb von 45 s")
            yield {}                       # macht daraus einen Generator

        def ruf(self, pfad, **_k):
            self.pfad = pfad
            return {"r_hash": B64_KENNUNG, "state": "OPEN", "value": "1000",
                    "creation_date": "1758600000", "expiry": "3600"}

    a = Stillstand()
    d = lnd.rechnung_abwarten(a, KENNUNG_ZAHLUNG)
    assert d["zustand"] == "offen" and d["betrag_sat"] == 1000
    assert a.pfad.startswith("/v2/invoices/lookup")


def test_eine_unsinnige_kennung_geht_gar_nicht_erst_hinaus(tmp_path,
                                                           monkeypatch):
    """Geprueft wird VOR dem Aufruf. Was kein 32-Byte-Hash ist, hat bei LND
    nichts zu suchen -- und eine Fehlermeldung von LND ueber etwas, das wir
    selbst haetten sehen koennen, ist eine schlechte Fehlermeldung."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    (knoten.macaroons / f"{lnd.EIGENES_MACAROON}.macaroon").write_bytes(b"\x00")
    gesehen = _aufzeichnen(monkeypatch)

    for falsch in ("", "abc", "zz" * 32, KENNUNG_ZAHLUNG + "00", None):
        for aufruf in (lnd.rechnung_nachsehen, lnd.rechnung_abwarten,
                       lnd.rechnung_stornieren):
            with pytest.raises(lnd.LndFehler):
                aufruf(knoten, falsch)
    assert gesehen == [], "eine unsinnige Kennung darf LND nie erreichen"


def test_grosse_buchstaben_in_der_kennung_sind_dieselbe_kennung(tmp_path,
                                                                monkeypatch):
    """Ein Hash aus einer fremden Oberflaeche kommt oft in Grossbuchstaben.
    Dasselbe Geschaeft zweimal zu fuehren, nur weil die Schreibweise
    abweicht, waere eine Falle ohne jeden Gegenwert."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    gesehen = _aufzeichnen(monkeypatch)
    lnd.rechnung_nachsehen(knoten, KENNUNG_ZAHLUNG.upper() + "  ")
    lnd.rechnung_nachsehen(knoten, KENNUNG_ZAHLUNG)
    assert gesehen[0]["url"] == gesehen[1]["url"]


def test_das_stornieren_schickt_die_kennung_im_rumpf(tmp_path, monkeypatch):
    """CancelInvoice nimmt sie im Rumpf, nicht in der URL -- und auch dort als
    base64. LNDs eigene Beschreibung von CancelInvoiceMsg, v0.21.3-beta:
    "When using REST, this field must be encoded as base64"."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    (knoten.macaroons / f"{lnd.EIGENES_MACAROON}.macaroon").write_bytes(b"\x00")
    gesehen = _aufzeichnen(monkeypatch)

    lnd.rechnung_stornieren(knoten, KENNUNG_ZAHLUNG)

    assert len(gesehen) == 1 and gesehen[0]["methode"] == "POST"
    assert gesehen[0]["url"].endswith("/v2/invoices/cancel")
    rumpf = json.loads(gesehen[0]["rumpf"])
    assert base64.urlsafe_b64decode(
        rumpf["payment_hash"]) == bytes.fromhex(KENNUNG_ZAHLUNG)


def test_das_stornieren_braucht_das_eigene_macaroon(tmp_path, monkeypatch):
    """invoices:write -- dasselbe Recht wie das Ausstellen. Mit readonly
    ginge es nicht, und das soll hier auffallen, nicht erst im Betrieb."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    (knoten.macaroons / f"{lnd.EIGENES_MACAROON}.macaroon").write_bytes(b"\x07")
    gesehen = []

    def urlopen(anfrage, timeout=None, context=None):
        gesehen.append(anfrage.headers.get("Grpc-metadata-macaroon"))
        return Antwort({})
    monkeypatch.setattr(lnd.urllib.request, "urlopen", urlopen)

    lnd.rechnung_stornieren(knoten, KENNUNG_ZAHLUNG)
    assert gesehen == ["07"]


def test_liste_und_nachschlagen_beschreiben_dieselbe_rechnung(tmp_path,
                                                              monkeypatch):
    """Beide Wege muessen dieselben Felder liefern. Sonst zeigt die
    Oberflaeche ueber denselben Vorgang zweierlei, je nachdem woher sie ihn
    gerade hat -- und niemand faende je heraus, welches stimmt."""
    _ohne_tls(monkeypatch)
    knoten = _knoten(tmp_path, mit_macaroon=True)
    roh = {"r_hash": B64_KENNUNG, "state": "SETTLED", "value": "2500",
           "amt_paid_sat": "2500", "memo": "Kaffee", "settle_date": "1758600030",
           "creation_date": "1758600000", "expiry": "3600",
           "payment_request": "lnbc25u1pbeispiel"}

    _aufzeichnen(monkeypatch, {"invoices": [roh]})
    aus_liste = lnd.rechnungen(knoten)["rechnungen"][0]
    _aufzeichnen(monkeypatch, roh)
    nachgesehen = lnd.rechnung_nachsehen(knoten, KENNUNG_ZAHLUNG)

    assert aus_liste == nachgesehen
    assert nachgesehen["kennung"] == KENNUNG_ZAHLUNG
    assert nachgesehen["zustand"] == "bezahlt"
    assert nachgesehen["laeuft_ab_s"] == 1758603600
