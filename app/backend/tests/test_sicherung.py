"""Die Kanalsicherung -- gegen einen echten Server, nicht gegen eine Attrappe.

Warum ein richtiger Socket: geprueft wird, was ueber die Leitung geht. Eine
Attrappe bestaetigt, was ich mir beim Schreiben gedacht habe. Der Server unten
schreibt auf, was wirklich ankam -- inklusive der Frage, ob die Anmeldedaten
schon beim ERSTEN Versuch dabei waren.
"""
import base64
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from satcortex import sicherung


class WebdavAttrappe:
    def __init__(self, antwort=201, inhalt=b"", holen=200):
        self.antwort = antwort
        # Was beim Zurueckholen herauskommt -- der Weg, den es lange nicht gab.
        self.inhalt = inhalt
        self.holen = holen
        self.anfragen = []
        aussen = self

        class Griff(BaseHTTPRequestHandler):
            def do_GET(self):
                aussen.anfragen.append({
                    "pfad": self.path,
                    "auth": self.headers.get("Authorization"),
                    "verb": "GET",
                })
                self.send_response(aussen.holen)
                self.send_header("Content-Length", str(len(aussen.inhalt)))
                self.end_headers()
                self.wfile.write(aussen.inhalt)

            def do_PUT(self):
                laenge = int(self.headers.get("Content-Length") or 0)
                aussen.anfragen.append({
                    "pfad": self.path,
                    "auth": self.headers.get("Authorization"),
                    "leib": self.rfile.read(laenge),
                    "typ": self.headers.get("Content-Type"),
                })
                self.send_response(aussen.antwort)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Griff)
        self.url = "http://127.0.0.1:%d/dav/sicherungen" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def schliessen(self):
        self.server.shutdown()


@pytest.fixture
def ziel():
    gebaut = []

    def bauen(**kw):
        z = WebdavAttrappe(**kw)
        gebaut.append(z)
        return z
    yield bauen
    for z in gebaut:
        z.schliessen()


BLOB = base64.b64encode(b"so-sieht-eine-kanalsicherung-aus").decode()


def test_die_sicherung_landet_unter_ihrem_namen(ziel):
    z = ziel()
    sicherung.lade_hoch(BLOB, z.url, "testnutzer", "geheim")
    assert z.anfragen[0]["pfad"].endswith("/channel.backup")
    assert z.anfragen[0]["leib"] == b"so-sieht-eine-kanalsicherung-aus"


def test_die_anmeldung_geht_schon_beim_ersten_versuch_mit(ziel):
    """Pythons AuthHandler reicht die Anmeldedaten erst NACH einer 401 nach --
    er schickte die Datei also einmal unangemeldet los. Deshalb steht der
    Kopf hier von Hand drin."""
    z = ziel()
    sicherung.lade_hoch(BLOB, z.url, "testnutzer", "geheim")
    assert len(z.anfragen) == 1, "es gab einen unangemeldeten ersten Versuch"
    erwartet = "Basic " + base64.b64encode(b"testnutzer:geheim").decode()
    assert z.anfragen[0]["auth"] == erwartet


def test_ein_abgewiesenes_ziel_meldet_seinen_code(ziel):
    """401 und 403 bedeuten Verschiedenes. Wer sie zusammenwirft, schickt
    jemanden sein Passwort suchen, obwohl der Ordner nicht existiert."""
    z = ziel(antwort=403)
    with pytest.raises(sicherung.ZielFehler) as fehler:
        sicherung.lade_hoch(BLOB, z.url, "testnutzer", "geheim")
    assert "403" in str(fehler.value)


@pytest.mark.parametrize("code, grund", [
    (401, "ziel_anmeldung_abgelehnt"),
    (403, "ziel_verweigert"),
    # Nicht "Ordner fehlt" -- den meldet WebDAV beim Ablegen mit 409.
    (404, "ziel_adresse_unbekannt"),
    (409, "ziel_ordner_fehlt"),
])
def test_beim_ablegen_bekommt_jeder_bekannte_code_seinen_satz(ziel, code, grund):
    """Bis zum 14.09.2026 kam jeder dieser Codes als nackte Zahl an."""
    z = ziel(antwort=code)
    with pytest.raises(sicherung.ZielFehler) as fehler:
        sicherung.lade_hoch(BLOB, z.url, "testnutzer", "geheim")
    assert fehler.value.grund == grund
    assert str(code) in str(fehler.value), "der Wortlaut des Servers geht mit"


def test_ein_unbekannter_code_bleibt_beim_wortlaut_des_servers(ziel):
    z = ziel(antwort=507)
    with pytest.raises(sicherung.ZielFehler) as fehler:
        sicherung.lade_hoch(BLOB, z.url, "testnutzer", "geheim")
    assert fehler.value.grund == ""
    assert "507" in str(fehler.value)


def test_ein_totes_ziel_ist_ein_zielfehler_und_kein_absturz():
    with pytest.raises(sicherung.ZielFehler):
        sicherung.lade_hoch(BLOB, "http://127.0.0.1:1/dav", "a", "b", zeitlimit=2)


def test_ein_schraegstrich_zu_viel_macht_keinen_unterschied(ziel):
    z = ziel()
    sicherung.lade_hoch(BLOB, z.url + "///", "a", "b")
    assert z.anfragen[0]["pfad"].count("//") == 0 or \
        z.anfragen[0]["pfad"].endswith("/channel.backup")


def test_faellig_ist_nur_was_sich_geaendert_hat():
    assert sicherung.faellig({}, BLOB) is True
    assert sicherung.faellig({"pruefsumme": sicherung.pruefsumme(BLOB)}, BLOB) is False
    assert sicherung.faellig({"pruefsumme": "etwas anderes"}, BLOB) is True
    # Ohne Sicherung gibt es nichts zu tun -- und schon gar keinen Grund,
    # eine leere Datei ueber die alte zu schreiben.
    assert sicherung.faellig({}, "") is False


def test_ein_fehlschlag_ueberschreibt_die_letzte_gute_pruefsumme_nicht(tmp_path):
    """Sonst gaelte beim naechsten Durchgang alles als erledigt -- und die
    Sicherung, die nie ankam, waere still abgehakt."""
    stand = sicherung.Stand(str(tmp_path))
    sicherung.vermerke(stand, BLOB, 3, "http://ziel")
    gut = stand.laden()["pruefsumme"]

    neu = base64.b64encode(b"ein-vierter-kanal-kam-dazu").decode()
    sicherung.vermerke(stand, neu, 4, "http://ziel", fehler="401: Unauthorized")
    d = stand.laden()
    assert d["pruefsumme"] == gut
    assert d["fehler"]
    assert sicherung.faellig(d, neu) is True, "der Rueckstand muss bestehen bleiben"


# ── Zurueckholen ──────────────────────────────────────────────────────────
#
# Der Weg, den es lange NICHT gab. Eine Sicherung, die man nur hinschieben,
# aber nicht zurueckholen kann, ist keine -- und wer sie braucht, hat gerade
# kein NAS mehr, auf dem er nachsehen koennte, wohin sie ging.


def test_die_sicherung_kommt_auch_wieder_zurueck(ziel):
    z = ziel(inhalt=b"so-sieht-eine-kanalsicherung-aus")
    zurueck = sicherung.hole_ab(z.url, "testnutzer", "geheim")
    assert base64.b64decode(zurueck) == b"so-sieht-eine-kanalsicherung-aus"
    assert z.anfragen[0]["verb"] == "GET"
    assert z.anfragen[0]["pfad"].endswith("/channel.backup")


def test_auch_beim_holen_geht_die_anmeldung_gleich_mit(ziel):
    z = ziel(inhalt=b"x" * 64)
    sicherung.hole_ab(z.url, "testnutzer", "geheim")
    marke = base64.b64encode(b"testnutzer:geheim").decode()
    assert z.anfragen[0]["auth"] == "Basic " + marke


def test_ein_leeres_ziel_ist_kein_stiller_erfolg(ziel):
    """404 heisst: dort liegt nichts. Wer das als leere Sicherung durchreicht,
    schickt jemanden mit einer Datei aus null Byte in die Wiederherstellung."""
    z = ziel(holen=404)
    with pytest.raises(sicherung.ZielFehler):
        sicherung.hole_ab(z.url, "testnutzer", "geheim")


def test_was_zu_gross_ist_ist_nicht_die_sicherung(ziel):
    """Was dort liegt, bestimmt ein fremder Server. Eine Kanalsicherung misst
    ein paar hundert Byte je Kanal -- ein Megabyte ist etwas anderes."""
    z = ziel(inhalt=b"x" * (sicherung.HOECHSTGROESSE + 1))
    with pytest.raises(sicherung.ZielFehler):
        sicherung.hole_ab(z.url, "testnutzer", "geheim")


@pytest.mark.parametrize("code, grund", [
    (401, "ziel_anmeldung_abgelehnt"),
    (403, "ziel_verweigert"),
    # Beim Holen heisst 404 wirklich: dort liegt nichts.
    (404, "ziel_keine_sicherung_dort"),
])
def test_beim_holen_bekommt_jeder_bekannte_code_seinen_satz(ziel, code, grund):
    z = ziel(holen=code)
    with pytest.raises(sicherung.ZielFehler) as fehler:
        sicherung.hole_ab(z.url, "testnutzer", "geheim")
    assert fehler.value.grund == grund


def test_jeder_grund_hat_einen_satz_in_beiden_sprachen_ohne_platzhalter():
    """Die Saetze stehen in app.js, die Schluessel hier -- ein Tippfehler auf
    einer Seite, und in der Oberflaeche stuende wieder etwas Rohes.

    Und ohne Platzhalter: beim Sichern im Hintergrund landet nur der
    Schluessel in der Ablage, ohne Werte. Ein {einzelheit} bliebe dort als
    Klammer im Satz stehen.
    """
    wurzel = Path(__file__).resolve().parents[3]
    bauplan = importlib.util.spec_from_file_location(
        "i18n_pruefen", wurzel / "tools" / "i18n_pruefen.py")
    werkzeug = importlib.util.module_from_spec(bauplan)
    bauplan.loader.exec_module(werkzeug)
    text = (wurzel / "app" / "web" / "app.js").read_text(encoding="utf-8")

    gruende = (set(sicherung.DEUTUNG_BEIM_ABLEGEN.values())
               | set(sicherung.DEUTUNG_BEIM_HOLEN.values()))
    for sprache in ("de", "en"):
        saetze = werkzeug._werte(text, sprache)
        fehlt = sorted(gruende - set(saetze))
        assert not fehlt, f"{sprache}: kein Satz fuer {fehlt}"
        mit_platzhalter = sorted(g for g in gruende if "{" in saetze[g])
        assert not mit_platzhalter, f"{sprache}: {mit_platzhalter}"
