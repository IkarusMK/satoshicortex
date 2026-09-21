"""Der Nachrichten-Feed.

Geprueft wird vor allem, was NICHT passieren darf: kein Abruf ohne
Einwilligung, keiner ohne Tor, kein fremdes HTML in der Oberflaeche, kein
javascript:-Verweis, keine Quelle, die es gar nicht gibt.
"""
import datetime as dt
import time

import pytest

from satcortex import nachrichten as N


# --------------------------------------------------------------- Quellen ---

def test_jede_quelle_hat_eine_pruefbare_adresse():
    for q in N.QUELLEN:
        assert q.adresse.startswith("https://"), q.name
        assert N._verweis(q.adresse) == q.adresse


def test_kennungen_sind_eindeutig():
    kennungen = [q.kennung for q in N.QUELLEN]
    assert len(kennungen) == len(set(kennungen))


def test_leitmedien_sind_ab_werk_aus():
    """Gemessen 0 bis 10 Prozent Ausbeute -- ein leerer Reiter waere ein
    schlechter erster Eindruck."""
    for q in N.QUELLEN:
        if q.art == "leit":
            assert not q.ab_werk, q.name


def test_nur_leitmedien_werden_gefiltert():
    for q in N.QUELLEN:
        assert q.gefiltert == (q.art == "leit")


def test_reuters_ist_nicht_dabei_und_der_grund_steht_da():
    """Am 06.09.2026 gemessen: fuenf Adressen, keine antwortet."""
    assert not any("reuters" in q.adresse.lower() for q in N.QUELLEN)
    assert "Reuters" in N.NICHT_VERFUEGBAR


def test_jede_zugeordnete_sprache_hat_auch_quellen():
    """Sonst zeigt die Zuordnung auf eine leere Liste -- und ein Nutzer in
    diesem Land bekaeme weniger als einer ohne Zuordnung."""
    vorhanden = {q.sprache for q in N.QUELLEN}
    for land, sprache in N.SPRACHE_JE_LAND.items():
        assert sprache in vorhanden, f"{land} zeigt auf {sprache}"


# ------------------------------------------------------- Sprache und Land ---

def test_algerien_bekommt_franzoesisch():
    """Des Betreibers Pruefstein: 'wenn ich in Algerien sitze, bringt mir
    Blocktrainer nichts'."""
    assert N.sprache_fuer("DZ") == "fr"
    erste = N.fuer_land("DZ")[0]
    assert erste.sprache == "fr"
    assert "blocktrainer" not in [q.kennung for q in N.fuer_land("DZ")[:3]]


def test_unbekanntes_land_bekommt_englisch():
    assert N.sprache_fuer("AU") == "en"
    assert N.sprache_fuer(None) == "en"
    assert N.sprache_fuer("") == "en"


def test_englische_quellen_sind_immer_dabei():
    """Auch bei fremder Sprache -- sie sind der Grundstock, nicht der Ersatz."""
    for land in ("DZ", "BR", "JP", "DE", "XX"):
        sprachen = {q.sprache for q in N.fuer_land(land)}
        assert "en" in sprachen, land


def test_regionale_quellen_stehen_vorn():
    for land, sprache in (("DE", "de"), ("BR", "pt"), ("JP", "ja")):
        assert N.fuer_land(land)[0].sprache == sprache


def test_kein_land_ist_zwei_sprachen_zugeordnet():
    assert len(N.SPRACHE_JE_LAND) == len(set(N.SPRACHE_JE_LAND))


# ---------------------------------------------------------------- Filter ---

@pytest.mark.parametrize("text", [
    "Bitcoin steigt auf 80.000 Dollar",
    "BTC-Kurs faellt",
    "Das Lightning-Netzwerk waechst",
    "Satoshi-Wallet bewegt sich",
    "Halving steht bevor",
    "Taproot-Adoption nimmt zu",
])
def test_enger_filter_trifft_das_thema(text):
    assert N.passt(text)


@pytest.mark.parametrize("text", [
    "Tarifrunde im oeffentlichen Dienst",
    "Lightning strikes twice in Ohio",       # Gewitter, nicht Lightning-Netz
    "Lithium mining in Chile expands",       # Bergbau, nicht Bitcoin-Mining
    "Ethereum-Update steht an",              # Krypto, aber nicht eng
])
def test_enger_filter_laesst_das_uebrige_liegen(text):
    assert not N.passt(text)


def test_weiter_filter_nimmt_die_nachbarschaft_dazu():
    assert not N.passt("Ethereum-Update steht an")
    assert N.passt("Ethereum-Update steht an", weit=True)
    # Das Gewitter bleibt auch weit draussen.
    assert not N.passt("Lightning strikes twice in Ohio", weit=True)


def test_krypto_mining_zaehlt_nur_verbunden():
    assert N.passt("Krypto-Mining in Kasachstan")
    assert not N.passt("Mining in Kasachstan")


# -------------------------------------------------------------- Zerlegen ---

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Bitcoin steigt</title>
 <link>https://beispiel.test/a</link>
 <description>&lt;p&gt;Ein &lt;b&gt;Text&lt;/b&gt; mit
   &lt;img src="https://verlag.test/zaehlpixel.gif"&gt; darin.&lt;/p&gt;</description>
 <pubDate>Sat, 06 Sep 2026 11:20:00 +0200</pubDate>
 <guid>abc-1</guid></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Lightning waechst</title>
 <link rel="alternate" href="https://beispiel.test/b"/>
 <summary>Kurzfassung</summary>
 <published>2026-09-06T09:00:00Z</published>
 <id>xyz-2</id></entry>
</feed>"""

FACH = N.Quelle("t", "Test", "https://beispiel.test/feed", "de", "fach")
LEIT = N.Quelle("l", "Blatt", "https://beispiel.test/feed", "de", "leit")


def test_rss_wird_zerlegt():
    b = N.zerlege(RSS.encode(), FACH)
    assert len(b) == 1
    assert b[0].titel == "Bitcoin steigt"
    assert b[0].verweis == "https://beispiel.test/a"
    erwartet = dt.datetime(2026, 9, 6, 9, 20,
                           tzinfo=dt.timezone.utc).timestamp()
    assert b[0].zeitpunkt == int(erwartet)   # 11:20 +0200


def test_atom_wird_zerlegt():
    b = N.zerlege(ATOM.encode(), FACH)
    assert len(b) == 1
    assert b[0].verweis == "https://beispiel.test/b"
    erwartet = dt.datetime(2026, 9, 6, 9, 0,
                           tzinfo=dt.timezone.utc).timestamp()
    assert b[0].zeitpunkt == int(erwartet)


def test_kein_html_ueberlebt_den_zerleger():
    """Fremder Text wird nie als HTML gezeichnet -- und ein Vorschaubild von
    einem fremden Server waere ein Zaehlpixel, das die echte Adresse des
    Lesers meldet und den Tor-Umweg zunichtemacht."""
    anriss = N.zerlege(RSS.encode(), FACH)[0].anriss
    for verboten in ("<", ">", "img", "zaehlpixel", "verlag.test"):
        assert verboten not in anriss, anriss
    assert "Ein Text mit" in anriss


def test_fachquelle_wird_nicht_gefiltert():
    """Auch ein Beitrag ohne Stichwort gehoert dazu -- bei einer
    Bitcoin-Redaktion traegt nicht jede Ueberschrift das Wort."""
    ohne = RSS.replace("Bitcoin steigt", "Ein Rueckblick auf das Jahr")
    assert len(N.zerlege(ohne.encode(), FACH)) == 1


def test_leitmedium_wird_gefiltert():
    ohne = RSS.replace("Bitcoin steigt", "Tarifrunde im Dienst")
    assert N.zerlege(ohne.encode(), LEIT) == []
    assert len(N.zerlege(RSS.encode(), LEIT)) == 1


def test_beitrag_ohne_verweis_faellt_weg():
    """Der ganze Sinn ist das Draufklicken."""
    ohne = RSS.replace("<link>https://beispiel.test/a</link>", "")
    assert N.zerlege(ohne.encode(), FACH) == []


@pytest.mark.parametrize("boese", [
    "javascript:alert(1)", "data:text/html,alert", "file:///etc/passwd",
    "  javascript:alert(1)  ", "JAVASCRIPT:alert(1)", "vbscript:x", "//ohne",
])
def test_gefaehrliche_verweise_werden_verworfen(boese):
    assert N._verweis(boese) == ""


@pytest.mark.parametrize("boese", [
    "javascript:alert(1)", "file:///etc/passwd", "JAVASCRIPT:alert(1)",
])
def test_beitrag_mit_gefaehrlichem_verweis_faellt_weg(boese):
    """Ein Feed ist fremder Text. Ohne diese Pruefung stuende im Anker, was
    der Verlag hineinschreibt."""
    kaputt = RSS.replace("https://beispiel.test/a", boese)
    assert N.zerlege(kaputt.encode(), FACH) == []


def test_dtd_wird_abgewiesen(monkeypatch):
    """Der Riegel gegen die Speicherfalle -- und nebenbei ein Melder fuer
    'das ist gar kein Feed'. Coin68 lieferte am 06.09.2026 eine HTML-Seite."""
    class Antwort:
        def read(self, n): return b'<!DOCTYPE html><html lang="vi">'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Oeffner:
        def open(self, *a, **k): return Antwort()

    monkeypatch.setattr(N, "_oeffner", lambda proxy: Oeffner())
    with pytest.raises(N.Abgewiesen, match="DTD"):
        N.hole("https://beispiel.test/feed")


@pytest.mark.parametrize("roh,quelle,erwartet", [
    # Genau so am 06.09.2026 aus den echten Feeds gelesen.
    ("Die Blockchain verzeichnete hoehere Zufluesse. Source: BTC-ECHO BTC-ECHO",
     "BTC-ECHO", "Die Blockchain verzeichnete hoehere Zufluesse."),
    ("Un regain de volatilite. L\u2019article Bien reussir en crypto est "
     "apparu en premier sur Cryptoast .",
     "Cryptoast", "Un regain de volatilite."),
    ("Crimes digitais e fraudes. Siga o Livecoins no Facebook , Twitter , "
     "Instagram e YouTube .",
     "Livecoins", "Crimes digitais e fraudes."),
    ("Der Kurs faellt. Der Beitrag Etwas erschien zuerst auf Blatt.",
     "Blatt", "Der Kurs faellt."),
    ("Price fell today. The post Something appeared first on Paper.",
     "Paper", "Price fell today."),
])
def test_verlagsnachspann_faellt_weg(roh, quelle, erwartet):
    """Die Quelle steht bei uns in einer eigenen Zeile -- der Nachspann des
    Verlags waere dieselbe Angabe ein zweites Mal, in jeder Meldung."""
    assert N._ohne_nachspann(roh, quelle) == erwartet


def test_nachspann_wird_nur_hinten_geschnitten():
    """Ein 'Quelle:' im Fliesstext darf die Meldung nicht halbieren."""
    text = ("Quelle: dpa meldet, dass der Kurs steigt. " + "Weiterer Text. " * 6)
    assert N._ohne_nachspann(text, "X").startswith("Quelle: dpa meldet")


def test_ohne_nachspann_laesst_saubere_texte_in_ruhe():
    sauber = "Bitcoin ist nach starken US-Arbeitsmarktdaten gefallen."
    assert N._ohne_nachspann(sauber, "Blocktrainer") == sauber


def test_anriss_wird_gekuerzt():
    lang = "Bitcoin " + "Wort " * 300
    kurz = N._kuerzen(lang)
    assert len(kurz) <= N.ANRISS_ZEICHEN + 2
    assert kurz.endswith("…")


def test_hoechstlaenge_reicht_fuer_optech():
    """Optech liefert 665 kB. Mit den 512 kB der Versionsabfrage waere die
    Antwort mitten im XML abgeschnitten und die Quelle haette nie geparst."""
    assert N.HOECHSTLAENGE >= 1024 * 1024


# ---------------------------------------------------------- Eigene Quellen ---

def test_eigene_quelle_wird_geprueft():
    assert N.eigene_quelle({"adresse": "javascript:alert(1)"}) is None
    assert N.eigene_quelle({"adresse": ""}) is None
    q = N.eigene_quelle({"adresse": "https://x.test/feed", "name": "Meine"})
    assert q and q.name == "Meine" and q.kennung.startswith("eigen:")


def test_eigener_name_wird_von_html_befreit():
    q = N.eigene_quelle({"adresse": "https://x.test/f",
                         "name": "<script>alert(1)</script>Boese"})
    assert "<" not in q.name and "script" not in q.name.lower()


# ----------------------------------------------------------------- Betrieb ---

def nur(*kennungen):
    """Eine Wahl, in der GENAU diese Quellen an sind.

    Seit 0.44.4 merkt sich die Anwendung den Widerspruch zur Werksvorgabe,
    nicht die Auswahl -- sonst blieben spaeter hinzugefuegte Quellen bei
    bestehenden Nutzern fuer immer aus. Fuer einen Test, der zwei bestimmte
    Quellen will, heisst das: alles andere abwaehlen.
    """
    merk = set(kennungen)
    return {"aktiv": True,
            "abgewaehlt": [q.kennung for q in N.QUELLEN
                           if q.ab_werk and q.kennung not in merk],
            "zugewaehlt": [q.kennung for q in N.QUELLEN
                           if not q.ab_werk and q.kennung in merk]}


class Zustand:
    def __init__(self, wahl=None): self._w = wahl or {}
    def laden(self):
        return type("E", (), {"nachrichtenwahl": self._w})()
    def merke_nachrichtenwahl(self, w): self._w = dict(w)


class Ablage:
    def __init__(self): self.gemerkt = []
    def nachricht_merken(self, b, s):
        if b["kennung"] in [x["kennung"] for x in self.gemerkt]:
            return False
        self.gemerkt.append(b)
        return True


def test_ab_werk_wird_nichts_abgerufen():
    """Eine frische Installation, die von sich aus dreissig Verlage anruft,
    ist ein Uebergriff -- auch ueber Tor."""
    f = N.Feed(Ablage(), lambda: "http://tor:9080", Zustand())
    assert f.einmal_holen() == {"uebersprungen": "aus"}


def test_ohne_tor_wird_nicht_gefragt():
    """Dieselbe Regel wie bei der Versionsabfrage."""
    f = N.Feed(Ablage(), lambda: None, Zustand({"aktiv": True}))
    assert f.einmal_holen() == {"uebersprungen": "tor_aus"}


def test_werksauswahl_enthaelt_keine_leitmedien():
    f = N.Feed(Ablage(), lambda: "p", Zustand({"aktiv": True}))
    assert [q for q in f.quellen("DE") if q.art == "leit"] == []
    assert len(f.quellen("DE")) > 10


def test_takt_bremst():
    f = N.Feed(Ablage(), lambda: "p", Zustand({"aktiv": True}))
    assert f.faellig()
    f._letzter_lauf = time.time()
    assert not f.faellig()
    assert f.einmal_holen() == {"uebersprungen": "zu_frueh"}


def test_lagen_nennen_jede_quelle_mit_zustand():
    f = N.Feed(Ablage(), lambda: "p", Zustand({"aktiv": True}))
    lagen = f.lagen("DE")
    assert len(lagen) == len(N.QUELLEN)
    for l in lagen:
        assert {"kennung", "name", "an", "grund", "art"} <= set(l)


def test_eigene_quelle_taucht_in_den_lagen_auf():
    z = Zustand({"aktiv": True,
                 "eigene": [{"adresse": "https://x.test/f", "name": "Meine"}]})
    f = N.Feed(Ablage(), lambda: "p", z)
    assert any(l["eigen"] and l["name"] == "Meine" for l in f.lagen("DE"))


# ------------------------------------------------------------ Schnittstelle ---
#
# Die Endpunkte gegen den echten Bauplan, nicht gegen eine Attrappe: es geht
# vor allem darum, dass sie ANTWORTEN, wenn nichts da ist -- kein Knoten,
# kein Tor, keine Datenbank. Ein Reiter, der dann einen Fehler wirft, ist
# schlimmer als einer, der leer ist und den Grund nennt.

from tests.test_api import _client, _platz                      # noqa: E402


@pytest.fixture
def angemeldet(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    return _client(tmp_path)


def test_feed_antwortet_auch_ohne_knoten(angemeldet):
    a = angemeldet.get("/api/nachrichten")
    assert a.status_code == 200
    d = a.json()
    assert d["aktiv"] is False           # ab Werk aus
    assert d["beitraege"] == []
    assert d["ungelesen"] == 0
    assert d["sprache"] == "en"          # ohne Karte kein Land -> englisch
    assert len(d["quellen"]) == len(N.QUELLEN)


def test_feed_ohne_anmeldung_verweigert(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    c = _client(tmp_path, anmelden=False)
    assert c.get("/api/nachrichten").status_code == 401
    assert c.post("/api/nachrichten/einstellungen",
                  json={"aktiv": True}).status_code == 401


def test_einschalten_wird_gemerkt(angemeldet, monkeypatch):
    # Einschalten stoesst den Erstabruf an. Ohne Attrappe griffe der Test
    # nach dem echten Tor-Ausgang -- und ein Test, der nach draussen
    # telefoniert, prueft das Wetter mit.
    monkeypatch.setattr(N, "hole",
                        lambda a, p=None, hoechstlaenge=None: b"<rss/>")
    angemeldet.post("/api/nachrichten/einstellungen", json={
        "aktiv": True, "weit": True,
        "abgewaehlt": [q.kennung for q in N.QUELLEN
                       if q.ab_werk and q.kennung != "optech"]})
    d = angemeldet.get("/api/nachrichten").json()
    assert d["aktiv"] is True and d["weit"] is True
    assert [q["kennung"] for q in d["quellen"] if q["an"]] == ["optech"]


def test_gefaehrliche_eigene_quelle_wird_verworfen(angemeldet):
    """Eine selbst eingetragene Adresse ist fremder Text."""
    a = angemeldet.post("/api/nachrichten/einstellungen", json={
        "aktiv": True,
        "eigene": [{"adresse": "javascript:alert(1)", "name": "Boese"},
                   {"adresse": "https://gut.test/feed", "name": "Gut"}]})
    assert a.json()["verworfen"] == 1
    namen = [q["name"] for q in angemeldet.get("/api/nachrichten").json()["quellen"]]
    assert "Gut" in namen and "Boese" not in namen


def test_quellensuche_ohne_tor_sagt_warum(angemeldet):
    """Nicht stumm leer: der Grund gehoert in die Antwort."""
    # Den Zustand direkt setzen: /api/knoten/netzwege verlangt einen
    # eingerichteten Knoten (409), und den gibt es hier nicht. Ohne diesen
    # Schritt bliebe Tor an -- und der Test griffe wirklich ins Netz.
    from satcortex import state as _state
    _state.Ablage(str(angemeldet.tmp / "config")).merke_knotenwahl(
        {"tor_aktiv": False})
    d = angemeldet.post("/api/nachrichten/quelle-suchen",
                        json={"adresse": "https://beispiel.test"}).json()
    assert d["gefunden"] == [] and d["grund"] == "tor_aus"


def test_grenze_laesst_sich_nicht_ins_unermessliche_treiben(angemeldet):
    assert angemeldet.get("/api/nachrichten?grenze=999999").status_code == 200
    assert angemeldet.get("/api/nachrichten?grenze=-5").status_code == 200


def test_alles_gelesen_geht_auch_ohne_meldungen(angemeldet):
    assert angemeldet.post("/api/nachrichten/gelesen").status_code == 200


# ------------------------------------------------- Der Abruf, ohne Netz ---
#
# Bis hierher blieb der Erfolgspfad ungeprueft: alles, was WIRKLICH abruft,
# hing am Netz und damit an fremden Rechnern. Ein Test, der nach draussen
# telefoniert, prueft das Wetter mit. Also eine Attrappe statt einer Leitung.

FEED_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Bitcoin {n}</title><link>https://q.test/{n}</link>
<description>Text {n}</description><guid>g{n}</guid></item>
<item><title>Wetterbericht {n}</title><link>https://q.test/w{n}</link>
<description>Es regnet</description><guid>w{n}</guid></item>
</channel></rss>"""


@pytest.fixture
def ohne_netz(monkeypatch):
    """hole() liefert einen Feed, ohne dass eine Verbindung entsteht."""
    gerufen = []

    def falsches_hole(adresse, proxy=None, hoechstlaenge=N.HOECHSTLAENGE):
        gerufen.append((adresse, proxy))
        if "kaputt" in adresse:
            raise N.Abgewiesen("Die Quelle weist uns ab (HTTP 403).")
        # Je Adresse IMMER dasselbe. Der erste Entwurf zaehlte die Aufrufe
        # mit und lieferte jedes Mal andere Kennungen -- damit gab es keine
        # Dubletten zu finden, und die Dublettenpruefung prueft sich selbst.
        return FEED_RSS.format(n=abs(hash(adresse)) % 1000).encode()

    monkeypatch.setattr(N, "hole", falsches_hole)
    return gerufen


def test_abruf_legt_ab_und_zaehlt(ohne_netz):
    z = Zustand(nur("optech", "btcecho"))
    a = Ablage()
    f = N.Feed(a, lambda: "http://tor:9080", z)
    erg = f.einmal_holen("DE")
    # VIER, nicht zwei: beides sind Fachquellen, und die werden nicht
    # gefiltert -- auch der "Wetterbericht" gehoert dort dazu. Bei einer
    # Bitcoin-Redaktion traegt nicht jede Ueberschrift das Stichwort.
    assert erg["neu"] == 4 and erg["gesehen"] == 4
    assert len(a.gemerkt) == 4
    # Und der Weg ging ueber den Proxy, nicht daran vorbei.
    assert all(p == "http://tor:9080" for _, p in ohne_netz)


def test_zweiter_abruf_bringt_keine_dubletten(ohne_netz):
    z = Zustand(nur("optech"))
    a = Ablage()
    f = N.Feed(a, lambda: "p", z)
    f.einmal_holen("DE")
    f._letzter_lauf = 0
    zweite = f.einmal_holen("DE")
    assert zweite["neu"] == 0


def test_eine_abgewiesene_quelle_reisst_die_anderen_nicht_mit(ohne_netz):
    """Ein stiller Ausfall bei einer darf die uebrigen nicht mitnehmen."""
    eigen = {"adresse": "https://kaputt.test/feed", "name": "Kaputt"}
    z = Zustand({**nur("optech"), "eigene": [eigen]})
    f = N.Feed(Ablage(), lambda: "p", z)
    erg = f.einmal_holen("DE")
    # Zwei: die gute Quelle ist eine Fachquelle und liefert beide Beitraege.
    assert erg["neu"] == 2                       # die gute Quelle kam durch
    lagen = {l["name"]: l for l in f.lagen("DE")}
    assert "403" in lagen["Kaputt"]["grund"]
    assert lagen["Bitcoin Optech"]["grund"] == ""


def test_nach_fehlschlaegen_wird_zurueckhaltender(ohne_netz):
    """Auf eine Abfuhr zu haemmern macht sie wahrscheinlicher -- genau das
    hat am 30.08.2026 das Budget eines Tor-Ausgangsknotens aufgebraucht."""
    # Nur die kaputte Quelle: alles Mitgelieferte abwaehlen.
    z = Zustand({**nur(), "eigene": [{"adresse": "https://kaputt.test/feed",
                                      "n": 1}]})
    f = N.Feed(Ablage(), lambda: "p", z)
    f.einmal_holen("DE")
    assert len(ohne_netz) == 1
    f._letzter_lauf = 0
    f.einmal_holen("DE")            # zu frueh fuer einen zweiten Versuch
    assert len(ohne_netz) == 1, "es wurde trotz Sperrfrist erneut gefragt"


def test_weiter_filter_wirkt_auf_leitmedien(ohne_netz, monkeypatch):
    krypto = FEED_RSS.replace("Wetterbericht {n}", "Ethereum steigt {n}")
    monkeypatch.setattr(N, "hole",
                        lambda a, p=None, hoechstlaenge=None: krypto.format(n=1).encode())
    leit = N.Quelle("x", "Blatt", "https://q.test/f", "de", "leit")
    assert len(N.zerlege(N.hole("x"), leit, weit=False)) == 1
    assert len(N.zerlege(N.hole("x"), leit, weit=True)) == 2


def test_selbstsuche_findet_angekuendigte_feeds(monkeypatch):
    seite = b"""<html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
      <link rel="alternate" type="application/atom+xml"
            href="https://anders.test/atom">
      <link rel="alternate" type="text/html" href="/nicht-dieser">
      <link rel="stylesheet" href="/stil.css">
    </head></html>"""
    monkeypatch.setattr(N, "hole", lambda a, p=None, hoechstlaenge=None: seite)
    gefunden = N.entdecke("https://q.test/", "p")
    assert gefunden == ["https://q.test/feed.xml", "https://anders.test/atom"]


def test_selbstsuche_schweigt_wenn_die_seite_nichts_sagt(monkeypatch):
    """handelsblatt.com deklariert nichts -- gemessen am 06.09.2026. Dann
    bleibt das Feld von Hand, statt etwas zu erfinden."""
    monkeypatch.setattr(N, "hole", lambda a, p=None, hoechstlaenge=None: b"<html></html>")
    assert N.entdecke("https://q.test/", "p") == []


def test_selbstsuche_ueberlebt_eine_abfuhr(monkeypatch):
    def weist_ab(*a, **k):
        raise N.Abgewiesen("HTTP 403")
    monkeypatch.setattr(N, "hole", weist_ab)
    assert N.entdecke("https://q.test/", "p") == []


# ---------------------------------------------------------------- Der Kurs ---
#
# Der Knoten kennt keinen Kurs -- er kommt von aussen und damit ueber Tor.
# Geprueft wird vor allem, was NICHT passieren darf.

from satcortex import kurs as K                                 # noqa: E402


def test_ohne_tor_wird_kein_kurs_geholt():
    """Dieselbe Regel wie bei Nachrichten und Versionsabfrage."""
    tafel = K.Kurstafel(lambda: None)
    tafel.einmal_holen("usd", erzwingen=True)
    assert tafel.grund == "tor_aus"
    assert tafel.als_dict()["kurs"] is None


def test_bitstamp_steht_vorn_weil_kein_cloudflare():
    """Acht von elf geprueften Kursquellen stehen hinter Cloudflare, und
    Cloudflare weist Tor-Ausgangsknoten haeufig ab. Die eine ohne gehoert
    deshalb an die erste Stelle -- nicht die bekannteste."""
    assert K.BOERSEN[0].name == "Bitstamp"
    assert K.BOERSEN[0].hinter_cloudflare is False


def test_es_gibt_einen_rueckfall_mit_verlauf():
    """Faellt Bitstamp aus, darf nicht nur der Kurs bleiben und das Bild
    verschwinden."""
    mit_verlauf = [b for b in K.BOERSEN if b.verlauf_adresse]
    assert len(mit_verlauf) >= 2


@pytest.mark.parametrize("boese", ["", None, "abc", float("nan"),
                                   float("inf"), "-5", 0, "0"])
def test_unsinnige_kurse_werden_verworfen(boese):
    """Was von aussen kommt, wird geprueft. Ein NaN zerstoerte die Zeichnung
    still -- die Linie waere einfach weg, ohne eine Meldung."""
    assert K._zahl(boese) is None


def test_eine_negative_tagesveraenderung_ueberlebt():
    """_zahl() weist alles <= 0 ab, weil ein Kurs von null keiner ist. Bei
    der Tagesveraenderung waere das falsch: dann zeigte der Kasten nur die
    guten Tage."""
    assert K._roh_prozent("-2.5") == -2.5
    assert K._roh_prozent("0") == 0.0
    assert K._roh_prozent("abc") is None


def test_fremde_waehrung_faellt_auf_dollar_zurueck():
    for unsinn in ("xyz", "", None, "'; DROP TABLE--"):
        assert K._pruefe_waehrung(unsinn) == "usd"
    assert K._pruefe_waehrung("EUR") == "eur"


def test_unbekannter_zeitraum_kippt_nichts():
    tafel = K.Kurstafel(lambda: None)
    d = tafel.als_dict("usd", "gibtsnicht")
    assert d["zeitraum"] == K.VORGABE_ZEITRAUM


def test_bitstamp_verlauf_traegt_hoch_und_tief():
    """Vier Felder je Punkt: Zeit, Schluss, Hoch, Tief.

    Beide Boersen liefern die Spanne ohnehin mit. Sie wegzuwerfen und die
    Sprechblase dann nur den Schlusskurs zeigen zu lassen waere Verschwendung
    -- gerade bei einer Tageskerze ist die Spanne die interessantere Zahl.
    """
    roh = {"data": {"pair": "BTC/USD", "ohlc": [
        {"timestamp": "1786147200", "close": "64908.72",
         "high": "65134.90", "low": "64801.24"},
        {"timestamp": "1786233600", "close": "65100.00",
         "high": "65200.00", "low": "65000.00"},
        {"timestamp": "1786320000", "close": "nicht-zahl"},
    ]}}
    assert K._bitstamp_verlauf(roh) == [
        (1786147200, 64908.72, 65134.90, 64801.24),
        (1786233600, 65100.0, 65200.0, 65000.0)]


def test_fehlendes_hoch_faellt_auf_den_schlusskurs_zurueck():
    """Sonst zeichnete das Band gegen null und risse das ganze Bild mit."""
    roh = {"data": {"ohlc": [{"timestamp": "1", "close": "100"}]}}
    assert K._bitstamp_verlauf(roh) == [(1, 100.0, 100.0, 100.0)]


def test_kraken_verlauf_liest_die_richtigen_felder():
    """Krakens Kerze: [Zeit, offen, hoch, tief, schluss, ...] -- wer hoch und
    tief vertauscht, zeichnet das Band auf den Kopf."""
    roh = {"result": {"XXBTZUSD": [
        [1786147200, "64000", "65134.9", "63800", "64908.72", "0", "0", 1],
        [1786233600, "64908", "65200", "64500", "65100", "0", "0", 1],
    ], "last": 1786233600}}
    assert K._kraken_verlauf(roh) == [
        (1786147200, 64908.72, 65134.9, 63800.0),
        (1786233600, 65100.0, 65200.0, 64500.0)]


def test_ein_ausfall_leert_die_tafel_nicht(monkeypatch):
    """Der zuletzt bekannte Kurs bleibt mit seinem Alter stehen. Eine Tafel,
    die bei jedem Aussetzer leer wird, ist schlechter als eine, die sagt,
    wie alt ihre Zahl ist."""
    tafel = K.Kurstafel(lambda: "http://tor:9080")
    monkeypatch.setattr(K, "hole_kurs",
                        lambda w, p: ({"kurs": 79000.0, "wechsel24": 1.0,
                                       "boerse": "Test", "waehrung": w}, ""))
    monkeypatch.setattr(K, "hole_verlauf",
                        lambda w, z, p: ([(1, 1.0), (2, 2.0)], "Test"))
    tafel.einmal_holen("usd", erzwingen=True)
    assert tafel.als_dict()["kurs"] == 79000.0

    def faellt_aus(*a, **k):
        raise K.Abgewiesen("Die Boerse weist uns ab (HTTP 403).")
    monkeypatch.setattr(K, "hole_kurs", faellt_aus)
    monkeypatch.setattr(K, "hole_verlauf", faellt_aus)
    tafel.einmal_holen("usd", erzwingen=True)
    d = tafel.als_dict()
    assert d["kurs"] == 79000.0            # steht noch
    assert "403" in d["grund"]             # und sagt, was los ist
    assert len(d["verlauf"]) == 2


def test_kurs_endpunkt_antwortet_ohne_alles(angemeldet):
    a = angemeldet.get("/api/kurs")
    assert a.status_code == 200
    d = a.json()
    assert d["waehrung"] == "usd" and d["verlauf"] == []
    assert set(d["waehrungen"]) == set(K.WAEHRUNGEN)


def test_kurs_endpunkt_ohne_anmeldung_verweigert(tmp_path, monkeypatch):
    _platz(monkeypatch, 4000)
    assert _client(tmp_path, anmelden=False).get(
        "/api/kurs").status_code == 401


# ------------------------------------------- Neue Quellen erreichen Nutzer ---
#
# Am 06.09.2026 hat der Betreiber ein Bild seiner Quellenliste geschickt: vier in
# 0.44.2 hinzugefuegte Quellen standen auf "aus". Der Grund war das Modell --
# gemerkt wurden die EINGESCHALTETEN, und was es beim Speichern nicht gab,
# stand in keiner Liste. Diese Tests halten die Umkehrung fest.

EINE_AUSWAHL = ["optech", "bitcoincom", "cointelegraph", "theblock",
                    "coindesk", "cnbc", "wsj", "btcecho", "bitcoinblog",
                    "blocktrainer", "bit2me", "livecoins"]


def test_eine_neue_quelle_erreicht_bestehende_nutzer():
    """Der Fehler, den der Betreiber im Bild gesehen hat."""
    z = Zustand({"aktiv": True, "quellen": EINE_AUSWAHL})
    an = {q.kennung for q in N.Feed(Ablage(), lambda: "p", z).quellen("DE")}
    neue = [q for q in N.QUELLEN if q.seit]
    assert neue, "keine Quelle traegt 'seit' -- der Test prueft nichts"
    for q in neue:
        assert q.kennung in an, f"{q.name} bleibt bei einem Bestandsnutzer aus"


def test_die_umstellung_haelt_seine_auswahl(monkeypatch):
    """Was er abgewaehlt hatte, bleibt aus -- auch nach der Umstellung."""
    z = Zustand({"aktiv": True, "quellen": EINE_AUSWAHL})
    an = {q.kennung for q in N.Feed(Ablage(), lambda: "p", z).quellen("DE")}
    for kennung in ("journalducoin", "cryptoast", "bitcoinfr", "forklog"):
        assert kennung not in an, kennung


def test_ein_selbst_angeschaltetes_leitmedium_ueberlebt():
    """CNBC und WSJ sind ab Werk AUS -- er hatte sie angeschaltet.

    Der erste Anlauf der Umstellung kannte nur "abgewaehlt" und liess beide
    fallen. Im Pruefstand an seiner echten Auswahl aufgefallen.
    """
    z = Zustand({"aktiv": True, "quellen": EINE_AUSWAHL})
    an = {q.kennung for q in N.Feed(Ablage(), lambda: "p", z).quellen("DE")}
    assert "cnbc" in an and "wsj" in an


def test_abwaehlen_und_zuwaehlen_ueberleben_das_speichern():
    z = Zustand({"aktiv": True, "abgewaehlt": ["btcecho"],
                 "zugewaehlt": ["cnbc"]})
    an = {q.kennung for q in N.Feed(Ablage(), lambda: "p", z).quellen("DE")}
    assert "btcecho" not in an          # ab Werk an, abgewaehlt
    assert "cnbc" in an                 # ab Werk aus, zugewaehlt
    assert "blocktrainer" in an         # unberuehrt -> Werksvorgabe


def test_die_regel_steht_nur_an_einer_stelle():
    """Auswahl und Anzeige duerfen nie auseinanderlaufen."""
    z = Zustand({"aktiv": True, "abgewaehlt": ["btcecho"],
                 "zugewaehlt": ["cnbc"]})
    f = N.Feed(Ablage(), lambda: "p", z)
    aus_auswahl = {q.kennung for q in f.quellen("DE")}
    aus_anzeige = {l["kennung"] for l in f.lagen("DE") if l["an"]}
    assert aus_auswahl == aus_anzeige


def test_jede_neue_quelle_traegt_ihre_fassung():
    """Ohne 'seit' laesst sich beim Umstellen nicht unterscheiden, ob der
    Nutzer eine Quelle abgewaehlt oder nie gesehen hat."""
    for q in N.QUELLEN:
        if q.seit:
            assert q.seit.count(".") == 2, q.seit


# ── Ein Faden je Aufgabe ───────────────────────────────────────────────────
#
# Gefunden am 10.09.2026, weil die Pruefung in der CI rot wurde: der Faden
# eines beendeten Testfalls rief nachrichten.hole() waehrend eines SPAETEREN
# auf und liess dessen Attrappe zwei Abrufe zaehlen statt einem.
#
# Der Testfehler war nur die Spitze. Im Betrieb steht dahinter: das
# Einschalten der Nachrichten startete JEDES MAL einen Faden, den niemand
# mitzaehlte. Wer den Schalter fuenfmal umlegt, hatte fuenf Feed-Abrufe
# gleichzeitig ueber Tor laufen -- und genau so ist am 30.08.2026 das Budget
# eines Ausgangsknotens aufgebraucht worden.

def _erstabrufe():
    import threading as _t
    return [f for f in _t.enumerate() if f.name == "nachrichten-erstabruf"]


def test_der_schalter_startet_keinen_zweiten_abruf(angemeldet, monkeypatch):
    import threading as _t
    laeuft, weiter = _t.Event(), _t.Event()

    def langsam(adresse, proxy=None, hoechstlaenge=N.HOECHSTLAENGE):
        laeuft.set()
        weiter.wait(10)
        raise N.Abgewiesen("Schluss fuer heute")

    monkeypatch.setattr(N, "hole", langsam)
    einstellungen = {
        "aktiv": True,
        "eigene": [{"adresse": "https://langsam.test/feed", "name": "Langsam"}],
        "abgewaehlt": [q.kennung for q in N.QUELLEN if q.ab_werk],
    }
    try:
        assert angemeldet.post("/api/nachrichten/einstellungen",
                               json=einstellungen).status_code == 200
        assert laeuft.wait(10), "der erste Abruf kam gar nicht los"
        # Waehrend der erste noch haengt: noch dreimal umlegen.
        for _ in range(3):
            angemeldet.post("/api/nachrichten/einstellungen",
                            json=einstellungen)
        assert len(_erstabrufe()) == 1, (
            f"{len(_erstabrufe())} Abrufe gleichzeitig -- einer davon reicht")
    finally:
        weiter.set()


def test_ein_beendeter_abruf_gibt_den_platz_wieder_frei(angemeldet, monkeypatch):
    """Sonst waere aus der Bremse eine Sperre geworden: nach dem ersten
    Abruf duerfte nie wieder einer starten."""
    import threading as _t
    fertig = _t.Event()

    def schnell(adresse, proxy=None, hoechstlaenge=N.HOECHSTLAENGE):
        fertig.set()
        # Gelingen, nicht scheitern: nach einer Abfuhr wartet die Quelle
        # ihre Sperrfrist ab, und dann bliebe offen, ob der zweite Abruf an
        # der Sperrfrist scheiterte oder am Faden. Geprueft wird der Faden.
        return FEED_RSS.format(n=7).encode()

    monkeypatch.setattr(N, "hole", schnell)
    einstellungen = {
        "aktiv": True,
        "eigene": [{"adresse": "https://schnell.test/feed", "name": "Schnell"}],
        "abgewaehlt": [q.kennung for q in N.QUELLEN if q.ab_werk],
    }
    angemeldet.post("/api/nachrichten/einstellungen", json=einstellungen)
    assert fertig.wait(10)
    for faden in _erstabrufe():
        faden.join(timeout=10)

    fertig.clear()
    angemeldet.post("/api/nachrichten/einstellungen", json=einstellungen)
    assert fertig.wait(10), "der zweite Abruf kam nie los"


# ── Was eine Abfuhr bedeutet, gehoert dazugesagt ───────────────────────────
#
# Aus dem Betrieb, 10.09.2026 aus seinem Protokoll:
#
#   Nachrichten (Bit2Me News): HTTPError: HTTP Error 418: I'm a teapot
#
# Das ist kein Fehler der Anwendung -- 418 ist der Scherz-Statuscode aus
# RFC 2324, den Schutzdienste wie Cloudflare vergeben, wenn sie den Anrufer
# fuer einen Automaten halten. Aber die Zeile sagt das nicht. Sie sieht aus
# wie ein Defekt und ist eine Abweisung, genau wie die 403 zwei Zeilen
# darueber -- nur unuebersetzt.

def _http(code, text="x"):
    import urllib.error
    from io import BytesIO
    return urllib.error.HTTPError("https://q.test/f", code, text, {},
                                  BytesIO(b""))


@pytest.mark.parametrize("code", [401, 403, 418, 429, 451])
def test_jede_abfuhr_wird_erklaert_und_nicht_nur_gemeldet(code):
    satz = N._deutung(_http(code), "http://tor:9080")
    assert str(code) in satz
    assert "HTTPError" not in satz, "der rohe Klassenname erklaert nichts"
    assert satz.endswith("."), "ein Satz, keine Fehlermeldung"


def test_der_teekannen_code_wird_beim_namen_genannt():
    satz = N._deutung(_http(418, "I'm a teapot"), "http://tor:9080")
    assert "418" in satz
    assert "Automat" in satz or "Schutzdienst" in satz


def test_zu_haeufig_gefragt_ist_etwas_anderes_als_gesperrt():
    """429 heisst "spaeter nochmal", 403 heisst "du nicht". Wer das
    zusammenwirft, sucht an der falschen Stelle."""
    viel = N._deutung(_http(429), None)
    nie = N._deutung(_http(403), None)
    assert viel != nie
    assert "429" in viel and "403" in nie


def test_ein_fehler_der_gegenseite_ist_nicht_unser_fehler():
    satz = N._deutung(_http(503), None)
    assert "503" in satz
    assert "HTTPError" not in satz


def test_was_wirklich_unbekannt_ist_bleibt_roh():
    """Nicht alles wegerklaeren: ein Fehler ohne HTTP-Code soll seinen
    Wortlaut behalten, sonst sucht man ihn nirgends."""
    satz = N._deutung(ValueError("etwas ganz anderes"), None)
    assert "ValueError" in satz
