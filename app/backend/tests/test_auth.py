"""Konto und Anmeldung -- die Tuer vor allem anderen.

Diese Datei entsteht VOR der PIN, und das ist Absicht. auth.py haelt heute
schon den einzigen Riegel, den diese Anwendung ueberhaupt hat: wer angemeldet
ist, darf alles, was sie kann. Bisher war sie nur nebenbei gepruft -- durch
die API-Tests, die sie benutzen, aber nicht befragen. 91 % Abdeckung ohne
eine einzige Zeile, die sich fuer den Riegel selbst interessiert.

Vor dem Bau der zweiten Stufe (Passphrase-Tresor -> PIN -> TOTP) muss die
erste nachweislich halten. Aus dem Betrieb, 09.09.2026: "muss alles sauber sein und
vorallem jede funktion geprueft !!!! immer !!" -- hier geht es um die Tuer vor
dem Geld.
"""
import json
import os
import time
from pathlib import Path

import pytest

from satcortex import auth


@pytest.fixture
def verwaltung(tmp_path):
    return auth.Kontoverwaltung(str(tmp_path / "ablage"))


# ── Der Hash ───────────────────────────────────────────────────────────────

def test_dasselbe_passwort_passt_und_ein_anderes_nicht():
    h = auth.hashe("richtig-und-lang-genug")
    assert auth.pruefe_passwort(h, "richtig-und-lang-genug")
    assert not auth.pruefe_passwort(h, "richtig-und-lang-genug ")
    assert not auth.pruefe_passwort(h, "falsch")
    assert not auth.pruefe_passwort(h, "")


def test_zweimal_dasselbe_passwort_ergibt_zwei_verschiedene_hashes():
    """Ohne eigenes Salt je Konto waere eine Regenbogentabelle wieder
    brauchbar -- und zwei gleiche Passwoerter waeren an ihrem Hash als
    gleich erkennbar."""
    a, b = auth.hashe("dasselbe-passwort"), auth.hashe("dasselbe-passwort")
    assert a != b
    assert auth.pruefe_passwort(a, "dasselbe-passwort")
    assert auth.pruefe_passwort(b, "dasselbe-passwort")


def test_der_hash_ist_scrypt_und_kein_schneller_hash():
    """Ein SHA-256 ueber ein Passwort laesst sich milliardenfach pro Sekunde
    durchprobieren. Die Parameter gehoeren in den Hash geschrieben, sonst
    laesst er sich spaeter nicht nachrechnen."""
    art, n, r, p, salt, schluessel = auth.hashe("beispielpasswort").split("$")
    assert art == "scrypt"
    assert int(n) >= 2 ** 14, "zu billig zum Durchprobieren"
    assert int(r) >= 8 and int(p) >= 1
    assert len(bytes.fromhex(salt)) >= 16
    assert len(bytes.fromhex(schluessel)) == auth.SCHLUESSEL_LAENGE


def test_ein_hash_aus_einem_fremden_verfahren_wird_abgelehnt():
    """Sonst waere das Verfahren durch Umschreiben der Datei austauschbar --
    etwa gegen ein "klartext$..."-Format, das jeder nachrechnen kann."""
    echt = auth.hashe("beispielpasswort")
    _, n, r, p, salt, schluessel = echt.split("$")
    assert not auth.pruefe_passwort(
        f"sha256${n}${r}${p}${salt}${schluessel}", "beispielpasswort")


@pytest.mark.parametrize("kaputt", [
    "", "scrypt", "scrypt$1$2$3", "scrypt$x$8$1$aabb$ccdd",
    "scrypt$32768$8$1$keinhex$ccdd", "$$$$$",
])
def test_eine_beschaedigte_hashzeile_wirft_nicht_sondern_passt_nicht(kaputt):
    """Eine halb geschriebene Kontodatei darf die Anmeldung nicht mit einem
    Fehler zerreissen -- sie darf nur niemanden hereinlassen."""
    assert auth.pruefe_passwort(kaputt, "irgendwas") is False


def test_der_vergleich_ist_zeitkonstant():
    """Ein "==" verraet ueber die Laufzeit, wie viele Stellen schon stimmen.
    Das ist kein Stil, sondern der Unterschied zwischen 2^256 und 256*16
    Versuchen."""
    quelle = Path(auth.__file__).read_text(encoding="utf-8")
    assert "hmac.compare_digest(schluessel.hex(), erwartet_hex)" in quelle


# ── Das Konto ──────────────────────────────────────────────────────────────

def test_ohne_konto_gibt_es_nichts_zu_laden(verwaltung):
    assert verwaltung.vorhanden is False
    assert verwaltung.lade() is None


def test_ein_konto_ueberlebt_den_neustart(verwaltung, tmp_path):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    zweite = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    assert zweite.vorhanden
    assert zweite.lade().benutzer == "testnutzer"
    assert zweite.melde_an("testnutzer", "einlangespasswort")


def test_ein_zweites_konto_wird_verweigert(verwaltung):
    """Wer das Geraet beansprucht hat, hat es beansprucht. Sonst koennte ein
    zweiter im Heimnetz sich einfach danebensetzen."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    with pytest.raises(PermissionError, match="konto_existiert"):
        verwaltung.lege_an("fremder", "auchlangespasswort")


@pytest.mark.parametrize("benutzer", ["", " ", "x", "  a  ", "y" * 65])
def test_unbrauchbare_benutzernamen_werden_abgelehnt(verwaltung, benutzer):
    with pytest.raises(ValueError, match="benutzer_ungueltig"):
        verwaltung.lege_an(benutzer, "einlangespasswort")


def test_ein_zu_kurzes_passwort_wird_abgelehnt(verwaltung):
    zu_kurz = "x" * (auth.MIN_PASSWORTLAENGE - 1)
    with pytest.raises(ValueError, match="passwort_zu_kurz"):
        verwaltung.lege_an("testnutzer", zu_kurz)
    assert not verwaltung.vorhanden, "nach einem Fehlschlag darf nichts liegen"


def test_das_passwort_steht_nirgends_in_der_datei(verwaltung):
    verwaltung.lege_an("testnutzer", "geheimes-langes-passwort")
    roh = verwaltung.datei.read_text(encoding="utf-8")
    assert "geheimes-langes-passwort" not in roh
    assert json.loads(roh)["hash"].startswith("scrypt$")


def test_die_kontodatei_gehoert_niemandem_sonst(verwaltung):
    """0600. Auf einem NAS liegt die Ablage in einem Verzeichnis, in das auch
    andere Dienste sehen koennen."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    assert os.stat(verwaltung.datei).st_mode & 0o077 == 0

    # Und es darf kein Zeitfenster geben, in dem sie offen liegt: die Rechte
    # werden auf der temporaeren Datei gesetzt, BEVOR sie an ihren Platz
    # geschoben wird.
    quelle = Path(auth.__file__).read_text(encoding="utf-8")
    for stelle in ("self.datei", "self.sitzungsdatei"):
        block = quelle[quelle.index(f"temp = {stelle}.with_suffix"):]
        block = block[:block.index("os.replace")]
        assert "os.chmod(temp" in block, f"{stelle}: erst umbenannt, dann Rechte"


def test_eine_zerschossene_kontodatei_meldet_kein_konto_statt_zu_sterben(verwaltung):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    verwaltung.datei.write_text("{kein json", encoding="utf-8")
    assert verwaltung.lade() is None
    verwaltung.datei.write_text('{"benutzer": "testnutzer"}', encoding="utf-8")
    assert verwaltung.lade() is None, "ohne hash ist es kein Konto"


# ── Die Anmeldung ──────────────────────────────────────────────────────────

def test_das_richtige_passwort_gibt_ein_merkmal(verwaltung):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    assert len(token) >= 32
    assert verwaltung.angemeldet(token)


def test_das_falsche_passwort_gibt_keines(verwaltung):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    with pytest.raises(PermissionError, match="anmeldung_fehlgeschlagen"):
        verwaltung.melde_an("testnutzer", "einlangespasswortt")


def test_der_richtige_name_zum_falschen_konto_reicht_nicht(verwaltung):
    """Das Passwort allein oeffnet nicht -- sonst waere der Name Zierde."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    with pytest.raises(PermissionError, match="anmeldung_fehlgeschlagen"):
        verwaltung.melde_an("fremder", "einlangespasswort")


def test_ohne_konto_meldet_sich_niemand_an(verwaltung):
    with pytest.raises(PermissionError, match="anmeldung_fehlgeschlagen"):
        verwaltung.melde_an("testnutzer", "einlangespasswort")


def test_auch_ohne_konto_wird_gerechnet(verwaltung):
    """Sonst antwortet die Anwendung auf einen unbekannten Namen sofort und
    auf einen bekannten nach einer Sekunde -- und verraet damit, welcher
    Name der richtige ist."""
    beginn = time.monotonic()
    with pytest.raises(PermissionError):
        verwaltung.melde_an("gibtsnicht", "einlangespasswort")
    gerechnet = time.monotonic() - beginn

    verwaltung.lege_an("testnutzer", "einlangespasswort")
    beginn = time.monotonic()
    with pytest.raises(PermissionError):
        verwaltung.melde_an("testnutzer", "falschespasswort")
    mit_konto = time.monotonic() - beginn

    # Kein Zeitvergleich auf die Millisekunde -- nur die Groessenordnung.
    # Ohne den Platzhalter-Hash waere die eine Antwort um Faktoren schneller.
    assert gerechnet > mit_konto / 10


def test_nach_zu_vielen_fehlversuchen_ist_zu(verwaltung):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    for _ in range(auth.MAX_FEHLVERSUCHE):
        with pytest.raises(PermissionError, match="anmeldung_fehlgeschlagen"):
            verwaltung.melde_an("testnutzer", "falschespasswort")
    with pytest.raises(PermissionError, match="zu_viele_versuche"):
        verwaltung.melde_an("testnutzer", "einlangespasswort")


def test_die_sperre_faellt_nach_ihrer_frist(verwaltung, monkeypatch):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    for _ in range(auth.MAX_FEHLVERSUCHE):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("testnutzer", "falschespasswort")

    spaeter = time.time() + auth.SPERRE_SEKUNDEN + 1
    monkeypatch.setattr(auth.time, "time", lambda: spaeter)
    assert verwaltung.melde_an("testnutzer", "einlangespasswort")


def test_eine_gelungene_anmeldung_loescht_die_fehlversuche(verwaltung):
    """Sonst summieren sich Vertipper ueber Tage zu einer Sperre."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    for _ in range(auth.MAX_FEHLVERSUCHE - 1):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("testnutzer", "falschespasswort")
    verwaltung.melde_an("testnutzer", "einlangespasswort")
    for _ in range(auth.MAX_FEHLVERSUCHE - 1):
        with pytest.raises(PermissionError, match="anmeldung_fehlgeschlagen"):
            verwaltung.melde_an("testnutzer", "falschespasswort")


# ── Die Sitzung ────────────────────────────────────────────────────────────

def test_das_merkmal_selbst_liegt_nicht_auf_der_platte(verwaltung):
    """Wer die Datei liest, haelt sonst eine gueltige Sitzung in der Hand --
    ohne das Passwort je gesehen zu haben."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    roh = verwaltung.sitzungsdatei.read_text(encoding="utf-8")
    assert token not in roh
    assert len(next(iter(json.loads(roh)))) == 64, "SHA-256 in hex"


def test_die_sitzungsdatei_gehoert_niemandem_sonst(verwaltung):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    verwaltung.melde_an("testnutzer", "einlangespasswort")
    assert os.stat(verwaltung.sitzungsdatei).st_mode & 0o077 == 0


def test_eine_sitzung_ueberlebt_den_neustart(verwaltung, tmp_path):
    """Der Grund steht in auth.py: vorher lagen Sitzungen nur im Speicher,
    und jedes Update meldete den Nutzer mitten im Assistenten ab."""
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    assert auth.Kontoverwaltung(str(tmp_path / "ablage")).angemeldet(token)


def test_abmelden_macht_das_merkmal_wertlos(verwaltung, tmp_path):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    verwaltung.melde_ab(token)
    assert not verwaltung.angemeldet(token)
    assert not auth.Kontoverwaltung(str(tmp_path / "ablage")).angemeldet(token)


def test_abmelden_ohne_merkmal_tut_nichts(verwaltung):
    verwaltung.melde_ab(None)
    verwaltung.melde_ab("")
    verwaltung.melde_ab("gibtsnicht")


@pytest.mark.parametrize("token", [None, "", "gibtsnicht", "x" * 43])
def test_ein_fremdes_merkmal_oeffnet_nichts(verwaltung, token):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    verwaltung.melde_an("testnutzer", "einlangespasswort")
    assert verwaltung.angemeldet(token) is False


def test_eine_abgelaufene_sitzung_gilt_nicht_mehr(verwaltung, monkeypatch):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    spaeter = time.time() + auth.SITZUNG_GUELTIG_SEKUNDEN + 1
    monkeypatch.setattr(auth.time, "time", lambda: spaeter)
    assert verwaltung.angemeldet(token) is False
    # Und sie wird dabei auch weggeraeumt, statt liegenzubleiben.
    assert json.loads(verwaltung.sitzungsdatei.read_text(encoding="utf-8")) == {}


def test_abgelaufene_sitzungen_kommen_nach_einem_neustart_nicht_zurueck(
        verwaltung, tmp_path):
    verwaltung.lege_an("testnutzer", "einlangespasswort")
    token = verwaltung.melde_an("testnutzer", "einlangespasswort")
    merkmal = next(iter(json.loads(verwaltung.sitzungsdatei.read_text())))
    verwaltung.sitzungsdatei.write_text(
        json.dumps({merkmal: time.time() - 1}), encoding="utf-8")
    assert not auth.Kontoverwaltung(str(tmp_path / "ablage")).angemeldet(token)


@pytest.mark.parametrize("inhalt", [
    "{kein json", "[]", '"nur ein wort"', "null",
    '{"merkmal": "kein zeitstempel"}',
])
def test_eine_zerschossene_sitzungsdatei_beginnt_leer(tmp_path, inhalt):
    """Sie darf den Start nicht verhindern -- ein Container, der wegen einer
    halb geschriebenen Datei endlos neu startet, zeigt gar nichts mehr."""
    ablage = tmp_path / "ablage"
    ablage.mkdir()
    (ablage / "sitzungen.json").write_text(inhalt, encoding="utf-8")
    assert auth.Kontoverwaltung(str(ablage)).angemeldet("irgendwas") is False


# ── Die PIN: das Schloss vor jeder Geldbewegung ────────────────────────────
#
# Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also knoten
# oeffnen oder schliessen geld transferieren".
#
# SIE SCHUETZT GEGEN ETWAS ANDERES ALS DER TRESOR, und das ist der ganze
# Grund, warum es beide gibt:
#
#   Tresor  gegen jemanden mit der PLATTE. Dort sitzt kein Waechter davor --
#           er kopiert die Datei und raet auf seinem eigenen Rechner, so oft
#           er mag. Deshalb muss dort eine echte Passphrase stehen.
#   PIN     gegen eine uebernommene SITZUNG in der Weboberflaeche. Hier sitzt
#           ein Waechter davor und zaehlt mit. Genau deshalb reichen sechs
#           Stellen -- und nur deshalb.
#
# Der Waechter ist damit kein Beiwerk, sondern die Voraussetzung. Faellt er,
# ist eine sechsstellige PIN in Minuten durch.

PIN = "402719"


@pytest.fixture
def freigabe(tmp_path):
    return auth.Freigabe(str(tmp_path / "ablage"))


@pytest.fixture
def mit_pin(freigabe):
    freigabe.einrichten(PIN)
    return freigabe


def test_ohne_eingerichtete_pin_gibt_es_keine(freigabe):
    assert freigabe.vorhanden is False


def test_die_richtige_pin_wird_angenommen(mit_pin):
    assert mit_pin.pruefe(PIN) is True


def test_die_falsche_pin_nicht(mit_pin):
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe("402718")


def test_die_pin_ueberlebt_den_neustart(mit_pin, tmp_path):
    zweite = auth.Freigabe(str(tmp_path / "ablage"))
    assert zweite.vorhanden
    assert zweite.pruefe(PIN) is True


def test_die_pin_steht_nicht_in_der_datei(mit_pin):
    roh = mit_pin.datei.read_text(encoding="utf-8")
    assert PIN not in roh
    assert json.loads(roh)["hash"].startswith("scrypt$")


def test_die_datei_gehoert_niemandem_sonst(mit_pin):
    assert os.stat(mit_pin.datei).st_mode & 0o077 == 0


@pytest.mark.parametrize("schwach", [
    "", "1", "12345", "111111", "000000", "123456", "654321",
    "abcdef", "12 34 56", "1234567890123",
])
def test_was_keine_pin_ist_wird_abgelehnt(freigabe, schwach):
    """Sechs Stellen sind nur deshalb genug, weil ein Waechter mitzaehlt.
    Eine Reihe oder sechsmal dieselbe Ziffer haelt auch das nicht auf."""
    with pytest.raises(ValueError):
        freigabe.einrichten(schwach)
    assert not freigabe.vorhanden


@pytest.mark.parametrize("gut", ["402719", "90210", "1357924"])
def test_eine_brauchbare_pin_geht_durch(tmp_path, gut):
    f = auth.Freigabe(str(tmp_path / str(len(gut))))
    f.einrichten(gut)
    assert f.pruefe(gut) is True


# ── Der Waechter, ohne den die sechs Stellen nichts taugen ────────────────
#
# Der geduldige Angreifer ist der interessante. Wer stumpf draufhaemmert,
# scheitert schon an der Wartezeit -- also wird hier IMMER die Wartezeit
# abgesessen, und trotzdem ist nach fuenf Versuchen Schluss.

class Uhr:
    """Eine Uhr, die sich weiterstellen laesst."""

    def __init__(self):
        self.jetzt = time.time()

    def __call__(self):
        return self.jetzt

    def weiter(self, sekunden):
        self.jetzt += sekunden


@pytest.fixture
def uhr(monkeypatch):
    u = Uhr()
    monkeypatch.setattr(auth.time, "time", u)
    return u


def _daneben(freigabe, uhr, wie_oft):
    """So oft danebengreifen, wie ein geduldiger Angreifer es koennte."""
    wartezeiten = []
    for _ in range(wie_oft):
        uhr.weiter(freigabe.wartet_noch() + 1)
        with pytest.raises(auth.FreigabeAbgelehnt):
            freigabe.pruefe("000001")
        wartezeiten.append(freigabe.wartet_noch())
    return wartezeiten


def test_nach_zu_vielen_pin_fehlversuchen_ist_zu(mit_pin, uhr):
    """Auch wer jede Wartezeit brav aussitzt, kommt nicht durch."""
    _daneben(mit_pin, uhr, auth.PIN_MAX_VERSUCHE)
    uhr.weiter(max(auth.PIN_WARTEN) + 1)
    with pytest.raises(auth.FreigabeGesperrt):
        mit_pin.pruefe(PIN)


def test_die_wartezeit_waechst_mit_jedem_fehlversuch(mit_pin, uhr):
    """Ein Waechter, der nur zaehlt, laesst die ersten Versuche beliebig
    schnell zu. Die wachsende Wartezeit ist das, was Durchprobieren teuer
    macht, BEVOR die Sperre ueberhaupt greift."""
    zeiten = _daneben(mit_pin, uhr, auth.PIN_MAX_VERSUCHE - 1)
    assert zeiten == sorted(zeiten), "die Wartezeit waechst nicht"
    assert zeiten[-1] > zeiten[0]


def test_waehrend_der_wartezeit_wird_gar_nicht_erst_geprueft(mit_pin):
    """Der Fall ohne Geduld: zweimal hintereinander geht nicht, auch nicht
    mit der richtigen PIN."""
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe("000001")
    assert mit_pin.wartet_noch() > 0
    with pytest.raises(auth.FreigabeGesperrt):
        mit_pin.pruefe(PIN)


def test_die_pin_sperre_faellt_nach_ihrer_frist(mit_pin, uhr):
    _daneben(mit_pin, uhr, auth.PIN_MAX_VERSUCHE)
    uhr.weiter(auth.PIN_SPERRE_SEKUNDEN + 1)
    assert mit_pin.pruefe(PIN) is True


def test_eine_gelungene_freigabe_loescht_die_fehlversuche(mit_pin, uhr):
    _daneben(mit_pin, uhr, 1)
    uhr.weiter(auth.PIN_WARTEN[0] + 1)
    assert mit_pin.pruefe(PIN) is True
    assert mit_pin.wartet_noch() == 0


def test_die_sperre_ueberlebt_einen_neustart(mit_pin, uhr, tmp_path):
    """Sonst waere sie geschenkt: wer die Anwendung neu startet -- und das
    kann jeder ausloesen, der an der Oberflaeche haengt --, haette wieder
    fuenf freie Versuche."""
    _daneben(mit_pin, uhr, auth.PIN_MAX_VERSUCHE)
    zweite = auth.Freigabe(str(tmp_path / "ablage"))
    with pytest.raises(auth.FreigabeGesperrt):
        zweite.pruefe(PIN)


# ── Aendern und abschaffen ────────────────────────────────────────────────

def test_die_pin_laesst_sich_aendern(mit_pin):
    mit_pin.aendern(PIN, "846201")
    assert mit_pin.pruefe("846201") is True
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe(PIN)


def test_ohne_die_alte_pin_wird_nichts_geaendert(mit_pin, uhr):
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.aendern("000001", "846201")
    uhr.weiter(auth.PIN_WARTEN[0] + 1)
    assert mit_pin.pruefe(PIN) is True


def test_auch_das_aendern_faellt_unter_den_waechter(mit_pin, uhr):
    """Eine Bremse mit einer zweiten Tuer daneben ist keine."""
    for _ in range(auth.PIN_MAX_VERSUCHE):
        uhr.weiter(mit_pin.wartet_noch() + 1)
        with pytest.raises(auth.FreigabeAbgelehnt):
            mit_pin.aendern("000001", "846201")
    uhr.weiter(max(auth.PIN_WARTEN) + 1)
    with pytest.raises(auth.FreigabeGesperrt):
        mit_pin.aendern(PIN, "846201")


def test_eine_schwache_neue_pin_wird_abgelehnt(mit_pin):
    with pytest.raises(ValueError):
        mit_pin.aendern(PIN, "111111")
    assert mit_pin.pruefe(PIN) is True


def test_entfernen_geht_nur_mit_der_pin(mit_pin, uhr):
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.entfernen("000001")
    assert mit_pin.vorhanden
    uhr.weiter(auth.PIN_WARTEN[0] + 1)
    mit_pin.entfernen(PIN)
    assert not mit_pin.vorhanden


def test_eine_zweite_pin_ueberschreibt_die_erste_nicht(mit_pin):
    with pytest.raises(PermissionError, match="pin_existiert"):
        mit_pin.einrichten("846201")
    assert mit_pin.pruefe(PIN) is True


def test_eine_zerschossene_datei_gilt_nicht_als_fehlende_pin(mit_pin):
    """Waere sie "keine PIN", faele das Schloss vor dem Geld weg -- und zwar
    lautlos. Lieber gar nichts freigeben als versehentlich alles."""
    mit_pin.datei.write_text("{kein json", encoding="utf-8")
    assert mit_pin.vorhanden, "die Datei ist da, also ist die PIN da"
    with pytest.raises(auth.FreigabeAbgelehnt):
        mit_pin.pruefe(PIN)


# ── Befunde des Audits vom 22.09.2026 ──────────────────────────────────────

def test_fehlversuche_unter_fremden_namen_fuellen_nichts_auf(verwaltung):
    """DER BEFUND: gezaehlt wurde unter dem Namen, den der Angreifer TIPPT.

    Der Eintrag wuchs damit unbegrenzt -- ein Anmeldeversuch mit jeweils
    neuem Namen genuegte, unangemeldet, auf einem Behaelter mit 400 MB
    Grenze, der genau daran schon einmal gestorben ist.

    Und eine blosse Obergrenze waere die falsche Behebung gewesen: dann
    haette man den Eintrag des ECHTEN Namens hinausdraengen und so seine
    Sperre aufheben koennen. Es gibt genau ein Konto -- also gibt es auch
    nur zwei Toepfe: dieses Konto und alles andere.
    """
    verwaltung.lege_an("betreiber", "ein-langes-passwort")
    for n in range(50):
        with pytest.raises(PermissionError):
            verwaltung.melde_an(f"fremd-{n}", "falsch")
    assert len(verwaltung._fehlversuche) <= 2


def test_fremde_namen_heben_die_sperre_des_echten_nicht_auf(verwaltung):
    """Die Gegenprobe zur Behebung: wer den echten Namen ausgesperrt hat,
    darf ihn nicht durch Rauschen wieder freibekommen."""
    verwaltung.lege_an("betreiber", "ein-langes-passwort")
    for _ in range(auth.MAX_FEHLVERSUCHE):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("betreiber", "falsch")
    for n in range(40):
        with pytest.raises(PermissionError):
            verwaltung.melde_an(f"fremd-{n}", "falsch")
    # Immer noch gesperrt -- auch mit dem RICHTIGEN Passwort.
    with pytest.raises(PermissionError) as f:
        verwaltung.melde_an("betreiber", "ein-langes-passwort")
    assert "zu_viele" in str(f.value)


def test_die_anmeldesperre_ueberlebt_einen_neustart(verwaltung, tmp_path):
    """Die PIN-Sperre tut das laengst (siehe oben), die ANMELDE-Sperre nicht.

    Sitzungen ueberdauern einen Neustart, die Sperre bisher nicht -- und
    das Protokoll dieser Anwendung sagt selbst, warum das zaehlt: ein
    Neustart laesst sich aus der Oberflaeche ausloesen."""
    verwaltung.lege_an("betreiber", "ein-langes-passwort")
    for _ in range(auth.MAX_FEHLVERSUCHE):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("betreiber", "falsch")
    frisch = auth.Kontoverwaltung(str(tmp_path / "ablage"))
    with pytest.raises(PermissionError) as f:
        frisch.melde_an("betreiber", "ein-langes-passwort")
    assert "zu_viele" in str(f.value)


def test_gleichzeitige_versuche_zaehlen_alle(verwaltung, monkeypatch):
    """DER TOCTOU-BEFUND. Pruefen und Zaehlen liefen ohne Schloss, und
    dazwischen liegt scrypt -- also ein langer Augenblick. Mehrere
    gleichzeitige Versuche kamen alle an der Sperre vorbei, bevor der erste
    sie hochgezaehlt hatte.

    Erzwungene Verschraenkung statt Hoffen: die Passwortpruefung wird
    kuenstlich langsam gemacht. Ohne sie ist der Test gruen, egal wie der
    Code aussieht -- und waere damit wertlos.
    """
    import threading
    verwaltung.lege_an("betreiber", "ein-langes-passwort")
    # Einen Versuch unter der Grenze aufbauen.
    for _ in range(auth.MAX_FEHLVERSUCHE - 1):
        with pytest.raises(PermissionError):
            verwaltung.melde_an("betreiber", "falsch")

    echt = auth.pruefe_passwort
    monkeypatch.setattr(auth, "pruefe_passwort",
                        lambda h, p: (time.sleep(0.25), echt(h, p))[1])

    ergebnis = []

    def versuchen():
        try:
            verwaltung.melde_an("betreiber", "falsch")
            ergebnis.append("durch")
        except PermissionError as f:
            ergebnis.append("zu_viele" if "zu_viele" in str(f) else "falsch")

    faeden = [threading.Thread(target=versuchen) for _ in range(6)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    # Genau EINER darf die Passwortpruefung noch erreichen; die Sperre faellt
    # mit seinem Versuch. Ohne Schloss kamen alle sechs durch.
    durchgelassen = sum(1 for e in ergebnis if e == "falsch")
    assert durchgelassen == 1, ergebnis


def test_gleichzeitige_pin_versuche_zaehlen_alle(tmp_path, monkeypatch):
    """Dasselbe fuer die PIN. Dort liegt der Zaehler in einer DATEI, und
    Lesen-Aendern-Schreiben ohne Schloss VERLIERT Versuche -- bei genau dem
    Zaehler, der zwischen einer uebernommenen Sitzung und dem Geld steht.

    Aus dem Ruhezustand heraus: alle fuenf duerfen die Pruefung erreichen,
    also muessen danach auch fuenf gezaehlt sein. Ohne Schloss sind es
    weniger, weil jeder Faden denselben Stand gelesen hat.
    """
    import threading
    frei = auth.Freigabe(str(tmp_path / "pin"))
    frei.einrichten("531794")

    echt = auth.pruefe_passwort
    monkeypatch.setattr(auth, "pruefe_passwort",
                        lambda h, p: (time.sleep(0.25), echt(h, p))[1])

    def versuchen():
        try:
            frei.pruefe("000000")
        except Exception:
            pass

    faeden = [threading.Thread(target=versuchen) for _ in range(5)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    assert len(frei._versuche()) == 5, len(frei._versuche())
