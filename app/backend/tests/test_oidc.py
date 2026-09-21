"""Anmeldung ueber einen fremden Ausweisdienst.

Aus dem Betrieb, 11.09.2026: "damit ich quasie kein lock in fenster mehr habe
sondern nur noch pocket id mich einloggt".

Hier steht der Teil, der stimmen MUSS. Ein Ausweis, den wir zu leicht
annehmen, ist die Eingangstuer zu einem Geraet mit einer Wallet darin --
deshalb wird hier nicht nur der gute Fall geprueft, sondern jede Faelschung
einzeln.
"""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from satcortex import oidc


ISSUER = "https://id.example.test"
CLIENT = "satcortex"


@pytest.fixture(autouse=True)
def leere_zwischenspeicher():
    """Die Zwischenspeicher sind Modulzustand -- sonst faerbt ein Test ab."""
    oidc._entdeckt.update(issuer="", zeit=0.0, wert={})
    oidc._schluessel.update(adresse="", zeit=0.0, wert={})
    yield
    oidc._entdeckt.update(issuer="", zeit=0.0, wert={})
    oidc._schluessel.update(adresse="", zeit=0.0, wert={})


@pytest.fixture
def paar():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64u(roh):
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode("ascii")


def _jwks(paar, kid="k1"):
    z = paar.public_key().public_numbers()
    return {"keys": [{
        "kty": "RSA", "kid": kid, "alg": "RS256", "use": "sig",
        "n": _b64u(z.n.to_bytes((z.n.bit_length() + 7) // 8, "big")),
        "e": _b64u(z.e.to_bytes((z.e.bit_length() + 7) // 8, "big")),
    }]}


def _ausweis(paar, kid="k1", **felder):
    kopf = {"alg": "RS256", "typ": "JWT", "kid": kid}
    nutz = {"iss": ISSUER, "aud": CLIENT, "sub": "abc123",
            "exp": int(time.time()) + 300, "nonce": "N"}
    nutz.update(felder)
    teile = [_b64u(json.dumps(kopf).encode()), _b64u(json.dumps(nutz).encode())]
    signiert = (".".join(teile)).encode("ascii")
    unterschrift = paar.sign(signiert, padding.PKCS1v15(), hashes.SHA256())
    return ".".join(teile + [_b64u(unterschrift)])


@pytest.fixture
def anbieter():
    return oidc.Anbieter(issuer=ISSUER, client_id=CLIENT,
                         client_secret="geheim",
                         rueckweg="https://btc.example.test/zurueck")


@pytest.fixture
def aufgestellt(monkeypatch, paar):
    """Entdeckung und Schluessel vorgeben, ohne ins Netz zu gehen."""
    def _hole(adresse, daten=None, kopf=None):
        if adresse.endswith(oidc.ENTDECKUNG_PFAD):
            return {"issuer": ISSUER,
                    "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/api/oidc/token",
                    "jwks_uri": ISSUER + "/.well-known/jwks.json"}
        if adresse.endswith("jwks.json"):
            return _jwks(paar)
        raise AssertionError("unerwarteter Aufruf: " + adresse)
    monkeypatch.setattr(oidc, "_hole", _hole)
    return paar


def _vorgang(nonce="N"):
    return oidc.Vorgang(state="S", nonce=nonce, beleg="B" * 43,
                        begonnen=time.time())


# ── Der gute Fall ──────────────────────────────────────────────────────────

def test_ein_echter_ausweis_wird_angenommen(anbieter, aufgestellt):
    nutz = oidc.pruefe_ausweis(anbieter, _ausweis(aufgestellt), _vorgang())
    assert nutz["sub"] == "abc123"


def test_die_adressen_kommen_vom_anbieter_nicht_von_uns(anbieter, aufgestellt):
    """Kein fest eingetippter Pocket-ID-Pfad. Derselbe Weg traegt damit auch
    Authentik oder Keycloak."""
    adresse, vorgang = oidc.beginne(anbieter)
    assert adresse.startswith(ISSUER + "/authorize?")
    assert "code_challenge_method=S256" in adresse
    assert "response_type=code" in adresse
    assert vorgang.nonce and vorgang.state and vorgang.beleg


def test_pkce_beweist_sich_selbst(anbieter, aufgestellt):
    """Die Aufgabe in der Adresse muss der SHA-256 des Belegs sein, den wir
    behalten -- sonst ist PKCE Zierde."""
    import hashlib
    adresse, vorgang = oidc.beginne(anbieter)
    erwartet = _b64u(hashlib.sha256(vorgang.beleg.encode()).digest())
    assert "code_challenge=" + erwartet in adresse


# ── Und jetzt die Faelschungen ─────────────────────────────────────────────

def test_eine_fremde_unterschrift_wird_abgewiesen(anbieter, aufgestellt):
    """Der Kern. Wer mit seinem eigenen Schluessel unterschreibt, kommt
    nicht herein -- sonst genuegte ein selbstgebautes JWT."""
    fremd = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter, _ausweis(fremd), _vorgang())


def test_ein_veraenderter_inhalt_wird_abgewiesen(anbieter, aufgestellt):
    """Die Nutzdaten nachtraeglich austauschen und die alte Unterschrift
    danebenlegen."""
    echt = _ausweis(aufgestellt)
    kopf, _, unterschrift = echt.split(".")
    andere = _b64u(json.dumps({"iss": ISSUER, "aud": CLIENT, "sub": "ICH",
                               "exp": int(time.time()) + 300,
                               "nonce": "N"}).encode())
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter, f"{kopf}.{andere}.{unterschrift}",
                            _vorgang())


def test_alg_none_kommt_nicht_durch(anbieter, aufgestellt):
    """Die aelteste JWT-Falle ueberhaupt: alg auf "none" setzen und die
    Unterschrift weglassen."""
    kopf = _b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    nutz = _b64u(json.dumps({"iss": ISSUER, "aud": CLIENT, "sub": "x",
                             "exp": int(time.time()) + 300,
                             "nonce": "N"}).encode())
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter, f"{kopf}.{nutz}.", _vorgang())


def test_ein_ausweis_fuer_jemand_anderen_wird_abgewiesen(anbieter, aufgestellt):
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter, _ausweis(aufgestellt, aud="andere-app"),
                            _vorgang())


def test_ein_ausweis_eines_anderen_ausstellers_wird_abgewiesen(
        anbieter, aufgestellt):
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter,
                            _ausweis(aufgestellt, iss="https://boese.test"),
                            _vorgang())


def test_ein_abgelaufener_ausweis_wird_abgewiesen(anbieter, aufgestellt):
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter,
                            _ausweis(aufgestellt, exp=int(time.time()) - 3600),
                            _vorgang())


def test_ein_ausweis_aus_einem_anderen_vorgang_wird_abgewiesen(
        anbieter, aufgestellt):
    """Die Nonce bindet den Ausweis an GENAU diese Anmeldung. Ohne sie
    liesse sich ein anderswo erbeuteter Ausweis hier einreichen."""
    with pytest.raises(oidc.OidcFehler):
        oidc.pruefe_ausweis(anbieter, _ausweis(aufgestellt, nonce="ANDERS"),
                            _vorgang(nonce="N"))


def test_ein_anbieter_der_sich_anders_nennt_faellt_auf(monkeypatch, anbieter):
    """Wenn die Entdeckung einen anderen Aussteller nennt, zeigt unsere
    Einstellung woandershin als gedacht."""
    monkeypatch.setattr(oidc, "_hole", lambda *a, **k: {
        "issuer": "https://wo-anders.test",
        "authorization_endpoint": "x", "token_endpoint": "y", "jwks_uri": "z"})
    with pytest.raises(oidc.OidcFehler):
        oidc.entdecke(ISSUER)


def test_ohne_https_wird_nicht_gesprochen():
    """Ein Ausweisdienst ueber Klartext waere keiner."""
    with pytest.raises(oidc.OidcFehler):
        oidc._hole("http://id.example.test/.well-known/openid-configuration")


# ── Pocket ID vergibt kein Secret mehr (12.09.2026) ────────────────────────
#
# Der Betreiber: "poket id erstellt mir kein secred mehr ?"
#
# Stimmt, und es war meine falsche Annahme. Aus Pocket IDs eigener Doku:
# "Only public clients are supported, so token_endpoint_auth_method must be
# none. PKCE is enabled automatically."
#
# Ein Pflichtfeld dafuer haette den Anmeldeweg unbenutzbar gemacht -- und zwar
# genau fuer den Anbieter, fuer den er gebaut ist.

def _gefangener_tausch(monkeypatch):
    """Faengt den Rumpf ab, den wir an den Token-Endpunkt schicken."""
    gesehen = {}

    def _hole(adresse, daten=None, kopf=None):
        if adresse.endswith(oidc.ENTDECKUNG_PFAD):
            return {"issuer": ISSUER,
                    "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/api/oidc/token",
                    "jwks_uri": ISSUER + "/.well-known/jwks.json"}
        gesehen["rumpf"] = (daten or b"").decode("ascii")
        return {"id_token": "x.y.z"}

    monkeypatch.setattr(oidc, "_hole", _hole)
    return gesehen


def test_ohne_secret_wird_keins_mitgeschickt(monkeypatch):
    """Ein LEERES client_secret ist nicht dasselbe wie keines: ein Anbieter,
    der "none" erwartet, darf ein leeres Feld als falschen Ausweis werten."""
    gesehen = _gefangener_tausch(monkeypatch)
    ohne = oidc.Anbieter(issuer=ISSUER, client_id=CLIENT, client_secret="",
                         rueckweg="https://btc.example.test/zurueck")
    oidc.loese_ein(ohne, "code123", _vorgang())
    assert "client_secret" not in gesehen["rumpf"]
    # Was den Tausch stattdessen schuetzt, muss drin sein.
    assert "code_verifier=" in gesehen["rumpf"]
    assert "client_id=" + CLIENT in gesehen["rumpf"]


def test_mit_secret_wird_es_mitgeschickt(monkeypatch, anbieter):
    """Wer einen Anbieter hat, der noch Secrets vergibt (Authentik,
    Keycloak), soll es auch nutzen koennen. Beides muss gehen."""
    gesehen = _gefangener_tausch(monkeypatch)
    oidc.loese_ein(anbieter, "code123", _vorgang())
    assert "client_secret=geheim" in gesehen["rumpf"]


def test_ohne_secret_gilt_der_anmeldeweg_trotzdem_als_eingerichtet():
    """Die Bedingung darf nicht am Secret haengen -- sonst waere Pocket ID
    gar nicht einzutragen."""
    from satcortex import settings
    ohne = settings.Einstellungen(
        oidc_issuer=ISSUER, oidc_client_id=CLIENT, oidc_client_secret="",
        oidc_rueckweg="https://btc.example.test/api/anmeldung/oidc/callback")
    assert ohne.oidc_aktiv is True
    # Aber ohne Rueckkehradresse geht es nicht -- die muss beim Anbieter
    # eingetragen sein und zeichengenau passen.
    assert settings.Einstellungen(
        oidc_issuer=ISSUER, oidc_client_id=CLIENT,
        oidc_client_secret="").oidc_aktiv is False


# ── Die Pfade, die beim ersten Mal nicht durchlaufen wurden ────────────────
#
# Aus dem Betrieb, 12.09.2026: "warum nicht 100%??" -- die Zahl ist die Abdeckung,
# nicht die Bestehensquote. Beim Nachsehen fiel auf, dass hier Sicherheitscode
# ungeprueft blieb: die zweite Signaturart und der Schluesselwechsel.

def test_auch_es256_wird_geprueft(monkeypatch):
    """Pocket ID signiert mit RS256, andere Anbieter mit ES256. Die Rohform
    der Unterschrift ist dabei eine andere (r||s statt DER) -- wer das
    verwechselt, weist jeden gueltigen Ausweis ab."""
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    paar = ec.generate_private_key(ec.SECP256R1())
    z = paar.public_key().public_numbers()
    jwks = {"keys": [{"kty": "EC", "crv": "P-256", "kid": "e1", "alg": "ES256",
                      "x": _b64u(z.x.to_bytes(32, "big")),
                      "y": _b64u(z.y.to_bytes(32, "big"))}]}

    kopf = {"alg": "ES256", "typ": "JWT", "kid": "e1"}
    nutz = {"iss": ISSUER, "aud": CLIENT, "sub": "ec1",
            "exp": int(time.time()) + 300, "nonce": "N"}
    teile = [_b64u(json.dumps(kopf).encode()), _b64u(json.dumps(nutz).encode())]
    der = paar.sign(".".join(teile).encode(), ec.ECDSA(hashes.SHA256()))
    r, sS = utils.decode_dss_signature(der)
    roh = r.to_bytes(32, "big") + sS.to_bytes(32, "big")
    ausweis = ".".join(teile + [_b64u(roh)])

    def _hole(adresse, daten=None, kopf=None):
        if adresse.endswith(oidc.ENTDECKUNG_PFAD):
            return {"issuer": ISSUER, "authorization_endpoint": "x",
                    "token_endpoint": "y",
                    "jwks_uri": ISSUER + "/.well-known/jwks.json"}
        return jwks
    monkeypatch.setattr(oidc, "_hole", _hole)

    anbieter = oidc.Anbieter(issuer=ISSUER, client_id=CLIENT,
                             client_secret="", rueckweg="https://x.test/z")
    assert oidc.pruefe_ausweis(anbieter, ausweis, _vorgang())["sub"] == "ec1"


def test_ein_schluesselwechsel_beim_anbieter_wird_aufgeholt(monkeypatch, paar):
    """Anbieter tauschen ihre Schluessel aus. Wuerden wir nur den
    zwischengespeicherten nehmen, waere nach jedem Wechsel bis zu einer
    Stunde lang keine Anmeldung moeglich."""
    alt = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    stand = {"jwks": _jwks(alt), "abrufe": 0}

    def _hole(adresse, daten=None, kopf=None):
        if adresse.endswith(oidc.ENTDECKUNG_PFAD):
            return {"issuer": ISSUER, "authorization_endpoint": "x",
                    "token_endpoint": "y",
                    "jwks_uri": ISSUER + "/.well-known/jwks.json"}
        stand["abrufe"] += 1
        # Beim ZWEITEN Abruf liegt der neue Schluessel vor.
        return stand["jwks"] if stand["abrufe"] > 1 else _jwks(alt)
    monkeypatch.setattr(oidc, "_hole", _hole)
    stand["jwks"] = _jwks(paar)

    anbieter = oidc.Anbieter(issuer=ISSUER, client_id=CLIENT,
                             client_secret="", rueckweg="https://x.test/z")
    # Unterschrieben mit dem NEUEN Schluessel, im Speicher liegt der alte.
    nutz = oidc.pruefe_ausweis(anbieter, _ausweis(paar), _vorgang())
    assert nutz["sub"] == "abc123"
    assert stand["abrufe"] >= 2, "es muss frisch nachgeholt worden sein"


def test_der_grund_des_anbieters_geht_nicht_verloren(monkeypatch):
    """Wer nur "400" meldet, verlaengert jede Fehlersuche. Der Rumpf sagt,
    was wirklich falsch war."""
    import io
    import urllib.error

    def _urlopen(*a, **k):
        raise urllib.error.HTTPError(
            "https://id.example.test/x", 400, "Bad Request", {},
            io.BytesIO(b'{"error":"invalid_client"}'))
    monkeypatch.setattr(oidc.urllib.request, "urlopen", _urlopen)
    with pytest.raises(oidc.OidcFehler, match="invalid_client"):
        oidc._hole("https://id.example.test/x")


def test_der_name_faellt_der_reihe_nach_zurueck():
    """Was in der Oberflaeche steht, wenn jemand sich angemeldet hat."""
    assert oidc.name_aus({"preferred_username": "testnutzer"}) == "testnutzer"
    assert oidc.name_aus({"name": "der Betreiber H."}) == "der Betreiber H."
    assert oidc.name_aus({"email": "a@b.test"}) == "a@b.test"
    # Und wenn gar nichts dabeisteht, wenigstens die Kennung.
    assert oidc.name_aus({"sub": "xyz"}) == "xyz"


def test_die_entdeckung_wird_nur_einmal_geholt(monkeypatch, aufgestellt):
    """Die Adressen eines Anbieters aendern sich praktisch nie. Sie bei jeder
    Anmeldung neu zu holen waere ein Aufruf mehr, der nichts bringt."""
    zaehler = {"n": 0}
    echt = oidc._hole

    def _hole(adresse, daten=None, kopf=None):
        if adresse.endswith(oidc.ENTDECKUNG_PFAD):
            zaehler["n"] += 1
        return echt(adresse, daten, kopf)
    monkeypatch.setattr(oidc, "_hole", _hole)

    anbieter = oidc.Anbieter(issuer=ISSUER, client_id=CLIENT,
                             client_secret="", rueckweg="https://x.test/z")
    oidc.beginne(anbieter)
    oidc.beginne(anbieter)
    assert zaehler["n"] == 1
