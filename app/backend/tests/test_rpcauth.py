from satcortex import rpcauth


def test_erzeugte_zugangsdaten_passen_zueinander():
    z = rpcauth.erzeuge("satcortex")
    assert rpcauth.pruefe(z.rpcauth, z.benutzer, z.passwort)


def test_format_entspricht_bitcoin_core():
    z = rpcauth.erzeuge("meinnode")
    name, rest = z.rpcauth.split(":", 1)
    salt, signatur = rest.split("$", 1)
    assert name == "meinnode"
    assert len(salt) == 32          # 16 Byte hex
    assert len(signatur) == 64      # SHA256 hex


def test_falsches_passwort_wird_abgelehnt():
    z = rpcauth.erzeuge()
    assert not rpcauth.pruefe(z.rpcauth, z.benutzer, "falsch")


def test_falscher_benutzer_wird_abgelehnt():
    z = rpcauth.erzeuge("a")
    assert not rpcauth.pruefe(z.rpcauth, "b", z.passwort)


def test_kaputte_zeile_stuerzt_nicht_ab():
    assert not rpcauth.pruefe("voellig kaputt", "a", "b")
    assert not rpcauth.pruefe("", "a", "b")
    assert not rpcauth.pruefe("nur:einteil", "nur", "b")


def test_jeder_aufruf_liefert_neue_werte():
    a, b = rpcauth.erzeuge(), rpcauth.erzeuge()
    assert a.passwort != b.passwort
    assert a.rpcauth != b.rpcauth
