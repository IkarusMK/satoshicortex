"""Die Oberflaeche darf nie nichts zeigen.

Am 03.09.2026 meldete der Betreiber: "hey die webui ist abgeschmiert ich drueck auf
web site aktualliesieren und das ding bricht ab! ... ich sehe nix mehr" --
und dazu ein Bild mit schwarzer Flaeche, aber unserem Namen im Reiter. Die
Huelle war also da, der Inhalt nicht.

Der Grund lag in start():

    try { ... if (z.angemeldet) return nachAnmeldung(); }
    catch (e) { ... }

Ohne "await" verlaesst die abgelehnte Zusage die try-Klammer, bevor sie
ausgewertet wird -- der catch greift dann nicht. nachAnmeldung() blendet als
Erstes die Anmeldeseite aus und ruft danach /status auf. Faellt dieser Aufruf
hin, ist ausgeblendet ausgeblendet, und eingeblendet wird nichts mehr. Jede
Sektion in der Vorlage startet versteckt: uebrig bleibt schwarzer Grund.

Diese Tests halten die drei Vorkehrungen fest, die daraus folgen.
"""
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"


@pytest.fixture(scope="module")
def js():
    return (WEB / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html():
    return (WEB / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css():
    return (WEB / "style.css").read_text(encoding="utf-8")


def test_es_gibt_eine_seite_fuer_den_fall_dass_nichts_geht(html, js):
    """Ohne sie bleibt bei einem Fehler nur die schwarze Flaeche."""
    assert 'id="notfall"' in html
    for kennung in ("nf-title", "nf-lead", "nf-detail", "nf-erneut"):
        assert f'id="{kennung}"' in html, f"{kennung} fehlt in der Vorlage"
    assert "function zeigeNotfall" in js


def test_nachanmeldung_wird_abgewartet(js):
    """"return f()" statt "return await f()" verschluckt den Fehler.

    Das ist keine Stilfrage: in einer async-Funktion wird der Rueckgabewert
    erst NACH dem Verlassen der try-Klammer ausgewertet. Der catch daneben
    sieht davon nichts.
    """
    assert "return await nachAnmeldung()" in js
    assert "return nachAnmeldung()" not in js


def test_unbehandelte_fehler_fuehren_zu_einer_sichtbaren_meldung(js):
    """Der Rueckhalt fuer alles, was hier niemand vorhergesehen hat."""
    assert 'addEventListener("unhandledrejection"' in js
    assert 'addEventListener("error"' in js
    assert "function nichtsSichtbar" in js


def test_jede_grosse_sektion_startet_versteckt(html):
    """Der Grund, warum ein abgerissener Start als schwarze Seite endet.

    Das ist so gewollt -- aber es ist auch die Voraussetzung des Fehlers.
    Steht es hier fest, faellt beim naechsten Umbau auf, dass es die
    Notfallseite braucht.
    """
    for kennung in ("gate", "wizard", "app", "notfall"):
        stelle = html.index(f'id="{kennung}"')
        zeile = html[html.rindex("<", 0, stelle):html.index(">", stelle) + 1]
        assert "hidden" in zeile, f"#{kennung}: {zeile}"


# ── Der Kasten fuer Fassungen darf nicht schweigen (03.09.2026) ──────────────
#
# Der Betreiber: "was mir aber auch aufgefallen ist das die aktualliesierungs
# abfrage auch keinen ton mehr von sich gibt .. ob ich den aktuellen stand
# habe oder das da nachgeguckt wird".
#
# Der Kasten wird ausschliesslich aus /api/status gefuellt. Seit 0.30.1 liegt
# dieser Aufruf auf der Einstellungsseite in einem eigenen try, damit ein
# Ausfall die Schalter nicht mitreisst -- aber dessen catch tat nichts.
# Faellt /status waehrend des Erstabgleichs in die Frist, wurde
# zeichneNeuerungen() nie aufgerufen und das leere <div> blieb leer.

def test_der_fassungskasten_sagt_auch_wenn_er_nichts_weiss(js):
    """Ohne Daten eine Begruendung -- nicht Schweigen."""
    assert "e_akt_kein_status" in js
    # Und der Ausfall von /status muss ihn auch wirklich aufrufen.
    assert "zeichneNeuerungen(null)" in js


def test_ein_ausfall_loescht_keine_guten_daten(js):
    """Steht schon ein Befund da, bleibt er stehen: ein misslungenes
    Auffrischen macht aus richtigen Angaben keine leere Flaeche. Dieselbe
    Regel wie bei WEGE_GELADEN in 0.30.1."""
    assert "if (!ziel.firstChild)" in js


# ── Uebersichtlichkeit: eine Navigationsebene (03.09.2026) ──────────────────
#
# Vorher trug der Kopf Reiter (Bitcoin | Lightning | Welt) und die
# Seitenleiste darunter die Abschnitte. Fuer zehn Ansichten zwei Menues, der
# halbe Bestand jeweils unsichtbar, und der Weg von "Bloecke" zu "Kanaele"
# ging ueber zwei Klicks an zwei verschiedenen Bildschirmraendern.

import re


def test_es_gibt_nur_noch_eine_navigationsebene(html, js):
    assert 'class="reiter"' not in html
    assert "data-reiter" not in html
    assert "data-reiter" not in js
    assert "REITER" not in js, "die Reiter-Logik ist noch im Skript"


def test_jeder_menuepunkt_fuehrt_zu_einer_ansicht(html):
    """Ein Knopf ohne Abschnitt zeigt eine leere Seite; ein Abschnitt ohne
    Knopf ist gar nicht erreichbar. Beides faellt sonst niemandem auf."""
    knoepfe = set(re.findall(r'<button data-ansicht="([\w-]+)"', html))
    abschnitte = set(re.findall(r'<section data-ansicht="([\w-]+)"', html))
    assert knoepfe == abschnitte, (
        f"nur Knopf: {knoepfe - abschnitte} · nur Abschnitt: {abschnitte - knoepfe}")


def test_keine_ansicht_versteckt_die_bedienung(css):
    """Die Weltkarte blendete die Seitenleiste aus -- vertretbar, solange die
    Reiter im Kopf stehen blieben. Ohne sie waere es eine Sackgasse."""
    assert "body.ansicht-welt .seitenleiste { display: none" not in css
    assert ".seitenleiste { display: none" not in css


def test_die_gruppen_der_seitenleiste_sind_beschriftet(html):
    """Ohne Ueberschrift waeren es zehn gleich schwere Eintraege in einer
    Reihe -- genau die Rolle, aus der die Reiter einmal herausfuehren
    sollten."""
    assert html.count('class="leiste-titel"') >= 3


# ── Uebersichtlichkeit: Hierarchie in der Kanaele-Ansicht ───────────────────

def test_die_lightning_reiter_haben_klare_zustaendigkeiten(html):
    """Aus dem Betrieb, 10.09.2026: "das wir momentan unter wallet sehen sind alles
    wallet einstellungen!!! und nicht das wallet".

    Er hat recht, und RTL, ThunderHub und Zeus machen es alle gleich: das
    GELD an einer Stelle, die Einrichtung woanders. Also vier Reiter mit je
    einer Zustaendigkeit -- und dieser Test haelt sie auseinander."""
    def abschnitt(name):
        anfang = html.index(f'<section data-ansicht="{name}"')
        return html[anfang:html.index("</section>", anfang)]

    # Wallet = das Geld. Einrichtungsstand als Kopfzeile, dann Guthaben,
    # dann die Einzahladresse.
    geld = abschnitt("ln-wallet")
    assert 'class="ln-kopf"' in geld
    for kasten in ('id="ln-guthaben"', 'id="w-einzahlen"'):
        assert kasten in geld, kasten
    # Und ausdruecklich KEINE Einrichtung mehr.
    for fremd in ('id="w-schritt-start"', 'id="w-sicherung"', 'id="w-tilgen"'):
        assert fremd not in geld, fremd

    # Kanaele = die Verbindungen, samt dem, was sie kosten.
    kanaele = abschnitt("ln-kanaele")
    for kasten in ('id="ln-kanalliste"', 'id="ln-weiter"', 'id="w-gebuehren"'):
        assert kasten in kanaele, kasten
    assert 'id="ln-guthaben"' not in kanaele

    # Einrichtung = alles, was man EINMAL tut.
    einr = abschnitt("ln-einrichtung")
    for kasten in ('id="w-schritt-start"', 'id="w-entsperrweg"',
                   'id="w-sicherung"', 'id="w-tilgen"'):
        assert kasten in einr, kasten


def test_die_kanaele_ansicht_hat_eine_rangfolge(html):
    """Vorher fuenf gleich schwere Kaesten, vier davon gleichzeitig sichtbar,
    sobald LND laeuft. Nichts daran sagte, was wichtig ist."""
    anfang = html.index('<section data-ansicht="ln-kanaele"')
    ende = html.index("</section>", anfang)
    teil = html[anfang:ende]
    # Die beiden Nachschlage-Kaesten stehen nebeneinander, nicht untereinander.
    assert 'class="raster"' in teil
    # Statt Kaesten zu ZAEHLEN die Reihenfolge pruefen. Das ist es, worum es
    # hier geht -- und es bleibt richtig, wenn einer dazukommt, statt bei
    # jedem neuen Kasten eine Zahl nachziehen zu muessen.
    ordnung = ["ln-kanalliste",     # was da ist, fuehrt
               "ln-oeffnen",        # was man damit anfaengt
               "ln-schliessen",
               "ln-schichten",
               "ln-wachturm",
               'class="raster"',    # die Nachschlage-Kaesten
               "ln-durchgang",      # was durchging -- und was nicht
               "w-gebuehren"]       # und die Entscheidung, die daraus folgt
    stellen = [teil.index(name) for name in ordnung]
    assert stellen == sorted(stellen), (
        "die Kanalansicht hat eine Rangfolge, und die ist verrutscht: "
        + repr(ordnung))


def test_die_leere_kanaele_ansicht_sagt_warum(html, js):
    """Die Kopfzeile mit Dienst/Wallet/Kette sitzt seit dem Umbau unter
    "Wallet". Ohne einen Satz waere diese Ansicht ohne laufendes LND
    einfach leer -- und leer sieht aus wie kaputt."""
    anfang = html.index('<section data-ansicht="ln-kanaele"')
    teil = html[anfang:html.index("</section>", anfang)]
    assert 'id="ln-kanaele-leer"' in teil
    assert '$("#ln-kanaele-leer").classList.toggle("hidden", bereit)' in js


# ── Abgeschnittene Bezeichner (03.09.2026) ──────────────────────────────────
#
# Im Pruefstand gefunden, an einem Knoten mit nachweislich fertiger Kette:
# die Oberflaeche las "d.kette_berei" statt "d.kette_bereit". In JavaScript
# ist das kein Fehler, sondern undefined -- also dauerhaft falsch. Die
# Lightning-Kopfzeile haette fuer immer "wird noch abgeglichen" gesagt.
#
# Dieselbe Sorte an drei weiteren Stellen: "d.heima" statt "d.heimat" (die
# Karte nannte nie das Land) und zweimal "textConten" in Kommentaren. Immer
# fehlte GENAU das letzte Zeichen -- irgendwann hat eine Bearbeitung
# Zeilenenden abgeschnitten.
#
# Ein Rechtschreibpruefer findet das nicht, ein Test schon.

# Wortpaare, bei denen die kurze Form ihre eigene, richtige Bedeutung hat.
ERLAUBTE_PAARE = {
    # Einzahl und Mehrzahl, beide gewollt.
    "adresse", "dienst", "externe_adresse", "gegenstelle", "netz", "schritt",
    # dataset.gebiet an einem Umriss, die Liste "gebiete" daneben.
    "gebiet",
    # Was der Browser selbst mitbringt: .value gibt es, .values auch.
    "value", "item", "key", "index", "length", "name", "type", "id",
}


def test_keine_abgeschnittenen_bezeichner(js):
    """Eine Eigenschaft, die es nur einen Buchstaben laenger wirklich gibt."""
    import collections

    hier = Path(__file__).resolve().parents[1] / "satcortex"
    py = "".join((hier / f"{n}.py").read_text(encoding="utf-8")
                 for n in ("api", "lnd", "rpc", "karte", "updates", "state"))
    schluessel = set(re.findall(r'"([a-z][a-z0-9_]{2,})"\s*:', py))
    schluessel |= set(re.findall(r"\b([a-z][a-z0-9_]{2,})=", py))

    gelesen = collections.Counter(re.findall(r"\.([A-Za-z_][A-Za-z0-9_]{2,})", js))
    bekannt = set(gelesen) | schluessel

    treffer = []
    for name in gelesen:
        if name in ERLAUBTE_PAARE or name in schluessel:
            continue
        for zeichen in "tnsem":
            if name + zeichen in schluessel or name + zeichen in bekannt:
                treffer.append(f"{name!r} -- gibt es auch als {name + zeichen!r}")
                break
    assert not treffer, "moeglicherweise abgeschnitten: " + " · ".join(treffer)


def test_die_kette_gilt_als_fertig_wenn_sie_es_ist(js):
    """Der konkrete Fall, ausdruecklich festgehalten."""
    assert "d.kette_bereit" in js
    assert re.search(r"kette_berei(?![t\"])", js) is None


# ── Zwei Uhren in einer Ansicht (03.09.2026) ────────────────────────────────
#
# Der Betreiber, mit Bildschirmfoto: "was ist denn jetzt hier los ... ist das wieder
# kaputt???? das bitcoin protokoll hoert bei 20:08 auf". Bei ihm war es 22:10.
# Die Zeile war EINE Minute alt: Bitcoin Core schreibt UTC (mit "Z"), Tor und
# diese Anwendung schreiben Ortszeit. In derselben Protokollansicht standen
# damit zwei Uhren, und keine war beschriftet.
#
# Nachgerechnet aus seinem eigenen Protokoll: 58 Bloecke in 218 Sekunden.
# Der Knoten lief die ganze Zeit.

def test_protokollzeiten_werden_auf_eine_uhr_gebracht(js):
    assert "function ortszeit" in js
    # Und die Umrechnung muss auch angewandt werden, nicht nur existieren.
    assert ".map(ortszeit)" in js


def test_nur_ein_stempel_am_zeilenanfang_wird_angefasst(js):
    """Ein Protokoll, das die Anzeige umschreibt, waere schlimmer als eines
    mit der falschen Uhr. Der Anker am Zeilenanfang ist deshalb Pflicht."""
    zeile = [z for z in js.splitlines() if "const UTC_STEMPEL" in z]
    assert zeile, "der Ausdruck fehlt"
    assert zeile[0].lstrip().startswith("const UTC_STEMPEL = /^"), zeile[0]


# ── Keine Gegenstellen ist nicht dasselbe wie nichts geliefert ──────────────

def test_der_beitrag_unterscheidet_leere_messung_von_null(js):
    """Sechs Nullen sehen aus wie eine tote Tafel -- und sagen nicht, ob
    wirklich null gemessen wurde oder gar nichts zu messen war."""
    assert "ohneGegenstellen" in js
    assert "b_keine_gegenstellen" in js


def test_null_bytes_tragen_eine_ehrliche_einheit(js):
    """"0 MB" las sich wie eine Rundung, also wie eine Anzeige, die haengt."""
    assert 'return "0 B"' in js
    assert 'return "0 MB"' not in js


# ── Die Weltkarte (04.09.2026) ──────────────────────────────────────────────
#
# Der Betreiber, mit Bildschirmfoto: "diese punkte auf der karte ne ... viel zu gross
# oder unnoetig ... und die ganze leiste im bild verschluckt quasi die
# suedliche himmelsphaere der weltkarte."
#
# Zur LAGE der Punkte: die stimmt. Gegengeprueft an Andorra, Singapur,
# Barbados, Hongkong, Malta und Island -- Abweichung hoechstens 0,2 Grad. Es
# war wirklich nur die Groesse.

def test_die_punkte_der_kleinstaaten_sind_punkte():
    """r=9 auf einer Karte von 2000 Einheiten Breite: Deutschland ist in
    dieser Projektion rund 44 Einheiten breit, der Punkt fuer Andorra war
    also fast halb so gross wie Deutschland."""
    svg = (WEB / "welt.svg").read_text(encoding="utf-8")
    radien = {float(r) for r in re.findall(r'<circle[^>]*\br="([\d.]+)"', svg)}
    assert radien, "keine Punkte gefunden"
    assert max(radien) <= 4, sorted(radien)


def test_erzeuger_und_karte_sagen_dieselbe_groesse():
    """Sonst faellt die Datei beim naechsten Neubau wieder auseinander."""
    werkzeug = (Path(__file__).resolve().parents[3] / "tools"
                / "karte_bauen.py").read_text(encoding="utf-8")
    treffer = re.search(r"^PUNKT_RADIUS = (\d+)", werkzeug, re.M)
    assert treffer, "PUNKT_RADIUS fehlt im Erzeuger"
    svg = (WEB / "welt.svg").read_text(encoding="utf-8")
    assert f'r="{treffer.group(1)}"' in svg


def test_die_karte_bekommt_den_platz_des_streifens_zurueck(css, js):
    """Der Streifen liegt ueber der Karte, und die Karte haengt am
    Bildschirmrand. Ohne Ausgleich verschluckt er die Suedhalbkugel."""
    assert "--streifen-hoehe" in css
    assert "function messeWeltstreifen" in js


def test_die_weltkarte_beginnt_wo_der_inhalt_beginnt(css, js):
    """Gemessen am 14.09.2026 in einem Fenster von 925x520: die Karte
    zeichnete 296x148 px, 9 % der Flaeche, und 45 % davon lagen unter dem
    Kopf. Sie hing oben und links am Fensterrand statt am Inhalt."""
    regel = css[css.index("body.ansicht-welt #karte-hintergrund {"):]
    regel = regel[:regel.index("}")]
    assert "var(--welt-oben" in regel and "var(--welt-links" in regel
    messung = js[js.index("function messeWeltstreifen"):]
    messung = messung[:messung.index("\n}\n")]
    assert "--welt-oben" in messung and "--welt-links" in messung


def test_der_weltstreifen_steht_unten_im_fenster(css, js):
    """War die Seite hoeher als das Fenster, stand der Streifen mitten im
    Bild -- und die Messung zaehlte alles darunter als seinen Platz."""
    regel = css[css.index(".welt-streifen {"):]
    regel = regel[:regel.index("}")]
    assert "position: sticky" in regel
    assert 'body.ansicht-welt section[data-ansicht="welt"] { flex: 1 1 auto; }' in css
    # Scrollen und Fenstergroesse verschieben ihn, ohne seine Groesse zu
    # aendern -- das sieht kein ResizeObserver.
    assert 'addEventListener("resize", weltNeuMessen)' in js
    assert 'addEventListener("scroll", weltNeuMessen' in js


def test_bei_wenig_platz_tritt_der_streifen_zurueck(css):
    """Im selben Fenster nahm er 52 % der Hoehe."""
    assert "@media (max-height: 760px), (max-width: 1100px)" in css


def test_die_zahlen_unter_der_weltkarte_lassen_sich_einklappen(html, css, js):
    """Auf kleinen Bildschirmen blieb neben den Zahlen kaum Platz fuer die
    Welt -- auch mit allem, was sich an Schrift und Abstand sparen liess."""
    assert 'id="w-klapp"' in html and 'aria-expanded="true"' in html
    assert ".welt-streifen.zu > .welt-spalte { display: none; }" in css
    klappen = js[js.index("function weltStreifenKlappen"):]
    klappen = klappen[:klappen.index("\n}\n")]
    # Die Karte bekommt den Platz sofort, nicht erst beim naechsten Zeichnen.
    assert "weltNeuMessen();" in klappen
    # Ohne Speicher -- privates Fenster, gesperrte Cookies -- darf das
    # Klappen nicht werfen.
    assert "try { localStorage.setItem" in klappen


def test_die_messung_haengt_nicht_an_requestAnimationFrame(js):
    """Der laeuft NICHT, solange das Fenster im Hintergrund liegt -- im
    Pruefstand nachgestellt: visibilityState "hidden", Rueckruf kam nie. Wer
    die Ansicht in einem Hintergrundreiter wechselt, haette sonst fuer immer
    den Naeherungswert behalten."""
    stelle = js.index('if (name === "welt")')
    block = js[stelle:stelle + 900]
    assert "messeWeltstreifen();" in block
    assert "requestAnimationFrame(messeWeltstreifen)" not in js


def test_mehrzeilige_felder_sehen_aus_wie_einzeilige(css):
    """Beim ersten Ansehen des Ausweis-Kastens am 04.09.2026 gemessen: das
    Textfeld war 177 Punkte breit in einem Kasten von 1148. Die Regel fuer
    ".feld" erfasste nur input, also blieb das Textfeld auf seiner
    Spaltenzahl stehen -- und in der falschen Schrift dazu."""
    assert ".feld > textarea {" in css
    stelle = css.index(".feld > input,\n.feld > textarea {")
    block = css[stelle:css.index("}", stelle)]
    assert "width: 100%" in block
    assert "var(--mono)" in block


# ── Erreichbarkeit: was man zusagt, muss man nachhalten koennen ─────────────
#
# Aus dem Betrieb, 05.09.2026, nachdem er die Swap-Bindungen bei LightningNetwork+
# gesehen hatte ("three months or more is recommended, and 12 months is
# common"): "dann muss unser system so sauber und stabil laufen das wir
# wirklich 60 monate am stueck online bleiben und nicht zwischen durch
# staendig abbrueche haben."
#
# LND fuehrt die Zahl je Kanal mit -- "lifetime" und "uptime". Wir haben
# beides von Anfang an gelesen und nie gezeigt.

def test_die_erreichbarkeit_wird_gerechnet_und_gezeigt(js):
    assert "function erreichbarkeit" in js
    assert "function gesamterreichbarkeit" in js
    assert "lk_erreichbar_gesamt" in js


def test_ein_frischer_kanal_bekommt_keine_quote(js):
    """"0 %" oder "100 %" nach zwei Minuten waere eine Behauptung ueber
    nichts. Erst ab zehn Minuten Laufzeit gibt es eine Zahl."""
    stelle = js.index("function erreichbarkeit")
    block = js[stelle:stelle + 400]
    assert "return null" in block
    assert "600" in block, "die Untergrenze fehlt"


def test_die_gesamtquote_gewichtet_nach_laufzeit(js):
    """Ein Kanal von gestern darf einen von vor einem Jahr nicht
    ueberstimmen -- sonst zieht eine kurze Stoerung die Bilanz eines Jahres
    nach unten oder ein frischer Kanal schoent sie."""
    stelle = js.index("function gesamterreichbarkeit")
    block = js[stelle:stelle + 500]
    assert "laufzeit_s" in block and "erreichbar_s" in block
    assert "dauer ? oben / dauer" in block


# ── Der Assistent zeigt, was die Anwendung kann (05.09.2026) ────────────────

def test_jeder_schritt_der_vorlage_steht_in_der_schrittfolge(html, js):
    """Ein Schritt im HTML, den SCHRITTE nicht kennt, ist unerreichbar.

    Er faellt niemandem auf: die Seite sieht vollstaendig aus, der Schritt
    wird nur nie angezeigt. Genau deshalb wird er hier gezaehlt.
    """
    import re
    in_html = set(re.findall(r'data-step="([a-z]+)"', html))
    zeile = re.search(r"const SCHRITTE = \[(.*?)\];", js, re.S).group(1)
    in_js = set(re.findall(r'"([a-z]+)"', zeile))
    assert in_html == in_js, f"nur im HTML: {in_html - in_js}, nur im JS: {in_js - in_html}"


def test_jeder_schritt_hat_eine_beschriftung_in_beiden_sprachen(js):
    """Ohne st_<name> traegt die Fortschrittsleiste einen leeren Kasten."""
    import re
    zeile = re.search(r"const SCHRITTE = \[(.*?)\];", js, re.S).group(1)
    for name in re.findall(r'"([a-z]+)"', zeile):
        assert js.count(f"st_{name}:") == 2, f"st_{name} fehlt in einer Sprache"


def test_die_sichtbarkeitswahl_steht_im_assistenten_und_in_den_einstellungen(html):
    """Eine Sache, eine Darstellung.

    Bis 0.40.0 fuehrte die Einstellungsseite mit dieser Wahl und der Assistent
    zeigte die alten Haekchen -- zwei Modelle fuer dieselbe Entscheidung. Wer
    neu installierte, traf sie, ohne sie gesehen zu haben.
    """
    for name in ('name="n-sicht"', 'name="e-ln-sicht"'):
        for wert in ("tor", "hybrid", "still"):
            assert f'{name} value="{wert}"' in html, f"{name}: {wert} fehlt"


def test_der_assistent_schickt_die_wahl_auch_ab(js):
    """Eine Wahl, die nur angezeigt und nicht uebertragen wird, ist Zierde."""
    stelle = js[js.index("async function abschliessen()"):]
    stelle = stelle[:stelle.index("await zeigeUebersicht()")]
    assert "sichtbarkeit: S.sichtbarkeit" in stelle
    assert "rpc_heimnetz:" in stelle


def test_ein_eingeschalteter_schalter_gibt_nie_stillschweigend_nichts_frei(js):
    """Gefunden am 05.09.2026 beim Durchklicken des Assistenten.

    heimnetzVorschlag() liefert nur etwas, wenn die Seite ueber eine
    IPv4-Adresse geoeffnet wurde. Ueber einen Namen aufgerufen kam "" heraus
    -- und ein eingeschalteter Schalter mit leerem Feld schickte damit eine
    LEERE Freigabe ab. Der Schalter stand auf an, freigegeben war nichts, und
    die Meldung sagte "Zugang wieder geschlossen".

    Beide Wege muessen durch dieselbe Pruefung: der Assistent und die
    Einstellungen.
    """
    assert "function heimnetzFehlt(" in js
    for stelle in ("async function rpcFreigabeSpeichern()", "function walletFolgen()"):
        koerper = js[js.index(stelle):]
        koerper = koerper[:koerper.index("\n}\n")]
        assert "heimnetzFehlt(" in koerper, f"{stelle} prueft nicht"


def test_der_schnellstart_nennt_den_port_der_wirklich_gilt():
    """Gefunden am 05.09.2026, als der Betreiber seine Compose zeigte.

    Der Kopf der Compose, die Anleitung und die README sagten alle drei
    "oeffne 4080". Die Vorgabe ist aber bewusst 3333 -- 4080 ist der
    Standardport von mempool.space, und genau das stand zwei Absaetze weiter
    auch so da. Wer dem Schnellstart folgt, bekommt unter 4080 nichts: keinen
    Fehler, keine Meldung, nirgends.
    """
    import re
    wurzel = Path(__file__).resolve().parents[3]
    vorgabe = re.search(r"^WEBUI_PORT=(\d+)$",
                        (wurzel / "example.env").read_text(encoding="utf-8"),
                        re.M).group(1)
    # Beide Platzhalterformen: die Doku ist englisch, die Compose-Kommentare
    # tragen den alten deutschen Text an manchen Stellen noch.
    for name in ("docker-compose.yml", "GUIDE.md", "README.md"):
        text = (wurzel / name).read_text(encoding="utf-8")
        for zeile in text.splitlines():
            for marke in ("<dein-server>:", "<your-server>:"):
                if marke not in zeile:
                    continue
                port = zeile.split(marke)[1][:4].strip("`/ ")
                assert port == vorgabe, (
                    f"{name}: nennt Port {port}, Vorgabe ist {vorgabe}")


# ── Ein Land aus der Naehe (05.09.2026) ────────────────────────────────────

def test_die_landansicht_ist_eine_auflage_und_kein_umbau(html, js):
    """Die Bedingung des Betreibers: "das darf nur unter dem Reiter Welt als Funktion
    zur Verfuegung stehen und darf sonst die Ansicht, die wir bis jetzt
    haben, nicht veraendern."

    Also: der Kasten liegt INNERHALB der Weltansicht, und der Klick auf die
    Karte tut nur dort etwas.
    """
    welt = html[html.index('<section data-ansicht="welt"'):]
    welt = welt[:welt.index("</section>")]
    assert 'id="welt-land"' in welt, "die Auflage liegt nicht in der Weltansicht"

    stelle = js[js.index('$("#karte-hintergrund").addEventListener("click"'):]
    stelle = stelle[:stelle.index("});")]
    assert 'ANSICHT !== "welt"' in stelle, "der Klick greift auch anderswo"


def test_die_landansicht_startet_versteckt(html):
    zeile = [z for z in html.splitlines() if 'id="welt-land"' in z][0]
    assert "hidden" in zeile


def test_ein_reiterwechsel_schliesst_die_landansicht(js):
    """Sonst steht sie beim naechsten Besuch noch da und verdeckt genau die
    Karte, die man sehen wollte."""
    stelle = js[js.index("function zeigeAnsicht("):]
    stelle = stelle[:stelle.index("\n}\n")]
    assert "schliesseLand()" in stelle


def test_zu_jedem_land_der_weltkarte_gibt_es_eine_regionskarte():
    """Der Betreiber: "das gilt fuer jedes Land der Welt!"

    Geprueft wird gegen die Weltkarte selbst: jedes Land, das dort anklickbar
    ist, muss auch eine Regionskarte haben -- sonst fuehrt ein Klick ins
    Leere, und zwar ohne dass irgendwo etwas stuende.
    """
    import re
    welt = (WEB / "welt.svg").read_text(encoding="utf-8")
    ordner = WEB / "regionen"
    anklickbar = set(re.findall(r'id="[lp]-([A-Z]{2})"', welt))
    fehlend = sorted(k for k in anklickbar if not (ordner / f"{k}.svg").exists())
    # Ein paar Kleinstaaten haben bei Natural Earth keine Untergliederung --
    # das ist in Ordnung, sie sind ja selbst kaum groesser als ein Gebiet.
    # Ein Drittel der Welt duerfte es aber nicht sein.
    assert len(fehlend) < len(anklickbar) * 0.25, f"zu viele ohne Karte: {fehlend}"
    for pflicht in ("DE", "AT", "CH", "US", "AU", "FR", "BR", "ZA", "JP", "KE"):
        assert (ordner / f"{pflicht}.svg").exists(), pflicht


def test_die_regionskarten_tragen_ihren_ausschnitt_mit():
    """Ohne die Eckdaten kann die Oberflaeche keinen Punkt einzeichnen -- und
    ohne die Angabe zur Datumsgrenze zerreisst es Russland und die USA."""
    for land in ("DE", "US", "RU", "FJ"):
        karte = (WEB / "regionen" / f"{land}.svg").read_text(encoding="utf-8")
        for feld in ("data-minlon", "data-maxlon", "data-minlat",
                     "data-maxlat", "data-umbruch", "viewBox"):
            assert feld in karte, f"{land}: {feld} fehlt"


def test_alle_svg_sind_gueltiges_xml():
    """Gefunden am 05.09.2026: die erzeugten Dateien trugen "--" in einem
    Kommentar, was XML verbietet. In der Anwendung fiel es nicht auf, weil
    welt.svg per innerHTML eingehaengt wird und der HTML-Parser nachsichtig
    ist -- als SVG geoeffnet brach jede Datei ab."""
    import xml.etree.ElementTree as ET
    for datei in sorted(WEB.rglob("*.svg")):
        try:
            ET.parse(datei)
        except ET.ParseError as fehler:
            raise AssertionError(f"{datei.name}: {fehler}") from fehler


def test_alles_was_ausgeliefert_wird_liegt_auch_im_repo():
    """Der Fehler vom 05.09.2026, gefangen von der CI statt von mir.

    In der .gitignore stand "data/" -- ohne fuehrenden Schraegstrich, also
    fuer JEDES so benannte Verzeichnis auf jeder Ebene. Gemeint war das
    Laufzeitverzeichnis in der Wurzel; verschluckt wurde app/data/regionen.json,
    eine Quelldatei. Lokal war alles gruen, im Checkout fehlte sie, und der
    Bau fiel um.

    Diese Pruefung sieht nicht nach, ob eine Datei DA ist -- das tun die
    anderen. Sie sieht nach, ob git sie kennt. Genau das war der Unterschied.
    """
    import subprocess
    wurzel = WEB.parents[1]
    bekannt = set(subprocess.run(
        ["git", "ls-files", "-z"], cwd=wurzel, capture_output=True,
        text=True, check=True).stdout.split("\0"))
    pflicht = [
        "app/data/regionen.json",
        "app/web/welt.svg",
        "app/web/regionen/DE.svg",
        "app/web/regionen/AU.svg",
        "app/web/app.js",
        "app/web/index.html",
        "app/web/style.css",
    ]
    fehlend = [p for p in pflicht if p not in bekannt]
    assert not fehlend, f"nicht im Repo: {fehlend}"

    # Und die Regionskarten nicht nur stichprobenartig: fehlte der halbe
    # Ordner, waere jeder zweite Klick ins Leere gegangen.
    im_repo = sum(1 for p in bekannt if p.startswith("app/web/regionen/"))
    auf_platte = len(list((WEB / "regionen").glob("*.svg")))
    assert im_repo == auf_platte, f"{auf_platte} Karten, aber {im_repo} im Repo"


def _dockerignore_trifft(pfad: str, regeln) -> bool:
    """Wird dieser Pfad aus dem Baukontext geworfen?

    Nachgebaut nach Dockers Regeln: jedes Muster wird gegen den Pfad
    (relativ zur Wurzel) geprueft, "**" ueberspringt beliebig viele Ebenen,
    ein "!" davor nimmt zurueck -- und der LETZTE Treffer entscheidet.
    """
    import re
    treffer = False
    for regel in regeln:
        regel = regel.strip()
        if not regel or regel.startswith("#"):
            continue
        negiert = regel.startswith("!")
        muster = regel.lstrip("!").rstrip("/")
        teile = []
        for stueck in muster.split("/"):
            if stueck == "**":
                teile.append("(?:.*/)?")
            else:
                teile.append(re.escape(stueck).replace(r"\*", "[^/]*")
                             .replace(r"\?", "[^/]") + "/")
        gebaut = "".join(teile).rstrip("/")
        # Ein Verzeichnismuster trifft auch alles darunter.
        if re.fullmatch(gebaut, pfad) or re.match(gebaut + "/", pfad):
            treffer = not negiert
    return treffer


def test_was_das_dockerfile_kopiert_liegt_auch_im_baukontext():
    """Der zweite Teil des Fehlers vom 05.09.2026.

    Nachdem app/data/regionen.json endlich im Repo lag, brach der Bau immer
    noch ab: "/app/data/regionen.json: not found". In der .dockerignore stand
    "**/data/" -- dieselbe zu breite Regel wie in der .gitignore, nur eine
    Datei weiter. Zweimal derselbe Fehler an zwei Stellen, und beide Male
    fiel es erst in der CI auf.

    Hier wird jede COPY-Quelle des Dockerfiles gegen die .dockerignore
    gehalten -- ohne Docker, denn den gibt es beim Entwickeln nicht immer.
    """
    import re
    wurzel = WEB.parents[1]
    regeln = (wurzel / ".dockerignore").read_text(encoding="utf-8").splitlines()
    dockerfile = (wurzel / "app" / "Dockerfile").read_text(encoding="utf-8")

    quellen = []
    for zeile in dockerfile.splitlines():
        z = zeile.strip()
        if not z.startswith("COPY ") or "--from=" in z:
            continue        # aus einer anderen Stufe, nicht aus dem Kontext
        felder = [f for f in z.split()[1:] if not f.startswith("--")]
        quellen.extend(felder[:-1])       # das letzte ist das Ziel

    verschluckt = [q for q in quellen if _dockerignore_trifft(q, regeln)]
    assert not verschluckt, f"vom Baukontext ausgeschlossen: {verschluckt}"


def test_nichts_liegt_klickdicht_ueber_der_karte(css):
    """Der Fehler vom 06.09.2026: "wenn ich auf ein Land klicke, passiert nix."

    Ursache war .karte-schleier -- ein reiner Farbverlauf, absolut ueber der
    Karte, ohne pointer-events: none. Er hat JEDEN echten Klick geschluckt;
    elementFromPoint mitten in Deutschland lieferte den Schleier, nie das
    Land.

    Warum es nicht auffiel: der Pruefstand hat den Klick per dispatchEvent
    direkt auf den Pfad geschickt. Das umgeht die Trefferpruefung des
    Browsers vollstaendig -- die Pruefung war gruen, die Funktion tot. Ein
    Klick, der nie auf den Bildschirm trifft, prueft nichts.

    Diese Pruefung ersetzt keine Trefferpruefung, aber sie haelt die Regel
    fest, aus der sie folgt: was ueber der Karte liegt und kein
    Bedienelement ist, nimmt keine Klicks.
    """
    import re
    for name in (".karte-schleier", ".karte-marke"):
        block = re.search(re.escape(name) + r"\s*\{(.*?)\}", css, re.S)
        assert block, f"{name} nicht gefunden"
        assert "pointer-events: none" in block.group(1), \
            f"{name} nimmt Klicks entgegen und liegt ueber der Karte"


# ── Die Verbindungslinie folgt ins Land (06.09.2026) ───────────────────────

def test_die_linie_kommt_aus_der_richtung_des_eigenen_knotens(js):
    """Der Betreiber: "wenn mein Verbindungsstrich auf der Weltkarte in ein Land
    geht und ich dann diesem Strich folge und auf das Land klicke -- zeigt
    der Strich dann auf die Region?"

    Die Richtung stammt aus der Weltkarte, nicht aus einer zweiten Quelle:
    der Vektor vom eigenen Knoten zu diesem Land. Nur so kommt die Linie an
    derselben Seite herein, an der sie draussen ankam.
    """
    koerper = js[js.index("function zeichneLandlinien("):]
    koerper = koerper[:koerper.index("\n}\n")]
    assert "anker(heimat)" in koerper and "anker(land)" in koerper
    # Ins eigene Land geht auf der Weltkarte keine Linie -- also auch hier
    # keine. Man ist ja schon da.
    assert "heimat === land" in koerper


def test_die_linie_endet_auf_der_flaeche_und_nicht_daneben(js):
    """Gemessen am 06.09.2026: die Mitte des umschliessenden Rechtecks liegt
    bei Inselgruppen regelmaessig im Meer -- Philippinen 26 von 118,
    Indonesien 10 von 33, Griechenland 5 von 14. Eine Linie, die daneben
    endet, ist schlimmer als keine: sie zeigt auf etwas.

    Deshalb fragt die Mittenbestimmung den Browser (isPointInFill) und sucht
    notfalls ueber ein Raster einen Punkt, der wirklich auf der Flaeche
    liegt. Nachgemessen war danach in denselben sechs Laendern KEIN Punkt
    mehr daneben.
    """
    koerper = js[js.index("function gebietsmitte("):]
    koerper = koerper[:koerper.index("\n}\n")]
    assert "isPointInFill" in koerper
    assert "getPointAtLength" in koerper      # der letzte Ausweg


def test_jeder_umriss_kennt_die_mitte_seiner_hauptflaeche():
    """Der Fehler vom 06.09.2026, im Bild gesehen: die Linie nach Japan
    endete auf einem Punkt weit im Meer suedlich der Hauptinseln.

    Das waren die Ogasawara-Inseln -- sie gehoeren verwaltungsmaessig zu
    TOKIO, stecken also im selben Umriss. Die Mitte des umschliessenden
    Rechtecks lag damit zwischen Honshu und den Inseln, und der Rastersuch-
    Punkt landete auf einer der Inseln. Beides "auf der Flaeche" und beides
    an Tokio vorbei.

    Der Erzeuger rechnet die Mitte jetzt aus der GROESSTEN Teilflaeche und
    schreibt sie in den Umriss.
    """
    import re
    for land in ("JP", "DE", "AU", "FR", "US", "IT", "GR"):
        text = (WEB / "regionen" / f"{land}.svg").read_text(encoding="utf-8")
        pfade = re.findall(r"<path [^>]*>", text)
        assert pfade, land
        ohne = [p for p in pfade if "data-cx=" not in p]
        assert not ohne, f"{land}: {len(ohne)} Umrisse ohne Mitte"


def test_die_mitte_liegt_im_ausschnitt():
    """Ein Punkt ausserhalb des Bildes waere kein Ziel, sondern ein Loch."""
    import re
    for land in ("JP", "DE", "AU", "US", "NL"):
        text = (WEB / "regionen" / f"{land}.svg").read_text(encoding="utf-8")
        kasten = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
        breite, hoehe = float(kasten.group(1)), float(kasten.group(2))
        drin = 0
        for cx, cy in re.findall(r'data-cx="([-\d.]+)" data-cy="([-\d.]+)"', text):
            if 0 <= float(cx) <= breite and 0 <= float(cy) <= hoehe:
                drin += 1
        gesamt = len(re.findall(r'data-cx="', text))
        # Nicht alle: entlegene Gebiete liegen bewusst ausserhalb des
        # Ausschnitts. Aber die grosse Mehrheit gehoert hinein.
        assert drin >= gesamt * 0.75, f"{land}: nur {drin} von {gesamt} im Bild"


# ── Nachrichten ──────────────────────────────────────────────────────────────
# Der Feed holt fremden Text von dreissig Verlagen in die Oberflaeche. Die
# drei Regeln dazu stehen im Quelltext als Kommentar -- hier stehen sie als
# Pruefung, denn ein Kommentar haelt nichts auf.

def _news_teil(js, ohne_kommentare=False):
    teil = js[js.index("/* ── Nachrichten ─"):
              js.index("/* ── Navigation: eine Ebene ─")]
    if not ohne_kommentare:
        return teil
    # Kommentare raus. Sonst schlaegt die Pruefung schon an, weil im Text
    # "textContent, nicht innerHTML" steht -- und wer sie dann gruen bekommen
    # will, entfernt den Kommentar statt des Fehlers.
    ohne = re.sub(r"/\*.*?\*/", " ", teil, flags=re.S)
    # Auch ANGEHAENGTE Kommentare -- der erste Anlauf entfernte nur ganze
    # Zeilen und schlug dann an "a.textContent = b.titel;  // nicht
    # innerHTML" an. Das (?<!:) haelt https:// heraus.
    return re.sub(r"(?<!:)//[^\n]*$", " ", ohne, flags=re.M)


def test_nachrichten_werden_nie_als_html_gezeichnet(js):
    """Fremder Text kommt ausschliesslich ueber textContent in die Seite.

    Ein Feed ist von aussen. Ein einziges innerHTML mit einer Ueberschrift
    aus einem Verlag genuegte, damit ein uebernommener Verlagsserver in
    dieser Oberflaeche Code ausfuehrt -- in einer Anwendung, die neben einer
    Wallet laeuft.
    """
    teil = _news_teil(js, ohne_kommentare=True)
    assert "innerHTML" not in teil, "Nachrichtenteil benutzt innerHTML"
    # Und die Felder, die wirklich von aussen kommen, gehen ueber textContent.
    for feld in ("b.titel", "b.anriss", "b.quellenname", "q.name"):
        assert f"textContent = {feld}" in teil, feld


def test_jeder_nachrichtenverweis_schuetzt_die_herkunft(js):
    """noopener/noreferrer UND no-referrer.

    Ohne das letzte stuende im Referrer die interne Adresse des Knotens --
    man teilte dem Verlag also mit jedem Klick seine Heimnetzadresse mit.
    """
    teil = _news_teil(js)
    assert 'a.rel = "noopener noreferrer"' in teil
    assert 'a.referrerPolicy = "no-referrer"' in teil


def test_der_feed_erzeugt_keine_bilder(js):
    """Ein Vorschaubild von einem Verlagsserver ist ein Zaehlpixel: es meldet
    die echte Adresse des Lesers und macht den Tor-Umweg zunichte."""
    teil = _news_teil(js, ohne_kommentare=True)
    for verboten in ('createElement("img")', "new Image(", ".src ="):
        assert verboten not in teil, verboten


def test_der_feed_hat_einen_ausgeschaltet_zustand(html):
    """Ab Werk aus -- und der Nutzer muss das SEHEN, samt Knopf."""
    assert 'id="news-aus"' in html
    assert 'id="news-einschalten"' in html


def test_der_feed_sagt_wenn_tor_fehlt(html, js):
    """Ohne Tor wird nicht geholt. Ein stiller leerer Reiter saehe aus wie
    'es kommt nichts an' -- derselbe Fehler wie einst bei der
    Versionsabfrage."""
    assert 'id="news-tor"' in html
    assert 'tor_aus' in _news_teil(js)


def test_nachrichten_haben_einen_eigenen_reiter(html):
    """Aus dem Betrieb, 06.09.2026: 'wenn dann bekommt der News Feed links in der
    Menueleiste einen eigenen Reiter'. Und ausdruecklich NICHT auf die
    Uebersicht: dort steht der Betriebszustand."""
    assert 'data-ansicht="news"' in html
    kopf = html[:html.index('<main')]
    assert 'data-ansicht="news"' in kopf, "Reiter fehlt in der Seitenleiste"


def test_kein_uebersetztes_element_hat_kindelemente(html):
    """applyI18n setzt textContent -- und das loescht Kinder.

        $$("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));

    Am 06.09.2026 stand der Ungelesen-Zaehler als <span> IM Menueknopf, der
    ein data-i18n trug. Die Uebersetzung entfernte ihn beim ersten Zeichnen
    aus dem DOM, ladeNews() lief danach auf null, die Ausnahme riss den Start
    mit -- und die Seite blieb SCHWARZ. Genau der Ausfall, den diese Datei
    oben beschreibt, nur mit neuer Ursache.

    Die Regel ist deshalb allgemein: was uebersetzt wird, traegt Text und
    sonst nichts. Beschriftung und Beiwerk gehoeren in getrennte Elemente.
    """
    import re as _re
    # Auf-Marke mit data-i18n, dann bis zur passenden Schluss-Marke sehen.
    for treffer in _re.finditer(r"<(\w+)([^>]*\bdata-i18n=[^>]*)>", html):
        marke, merkmale = treffer.group(1), treffer.group(2)
        if "data-i18n-html" in merkmale:
            continue          # der Weg ist ausdruecklich fuer eigenes Markup
        if marke in ("input", "img", "br", "hr", "meta", "link"):
            continue          # leere Elemente haben ohnehin keine Kinder
        rest = html[treffer.end():]
        schluss = rest.find(f"</{marke}>")
        assert schluss >= 0, f"<{marke}> ohne Schluss-Marke"
        inhalt = rest[:schluss]
        assert "<" not in inhalt, (
            f"<{marke} data-i18n=...> enthaelt ein Kindelement: {inhalt[:70]!r}"
            " -- applyI18n wuerde es beim ersten Zeichnen loeschen.")


def test_verstecktes_bleibt_versteckt(css):
    """Eine Klassenregel mit `display` schlaegt das hidden-Attribut.

    Am 06.09.2026 stand deshalb neben "Nachrichten" eine leere orange Pille,
    obwohl nichts ungelesen war: .ungelesen { display: inline-block } gewann
    gegen [hidden]. Wer display auf eine Klasse setzt, die auch versteckt
    werden soll, muss den versteckten Fall ausdruecklich nennen.
    """
    import re as _re
    # Kommentare zuerst weg: sonst zaehlt der Text davor zum Waehler, und
    # ".ungelesen" wird zu "... Im Bild gesehen. */\n.ungelesen" -- der erste
    # Anlauf dieser Pruefung fand deshalb NICHTS und war wertlos.
    css = _re.sub(r"/\*.*?\*/", " ", css, flags=_re.S)
    mit_display = set()
    for regel in _re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        waehler, koerper = regel.group(1).strip(), regel.group(2)
        if not _re.search(r"(^|;|\s)display\s*:", koerper):
            continue
        for w in waehler.split(","):
            w = w.strip()
            treffer = _re.fullmatch(r"\.([\w-]+)", w)
            if treffer:
                mit_display.add(treffer.group(1))
    for klasse in sorted(mit_display):
        versteckbar = _re.search(rf"\.{_re.escape(klasse)}\[hidden\]", css)
        # Nur Klassen pruefen, die auch wirklich versteckt werden.
        html = (WEB / "index.html").read_text(encoding="utf-8")
        wird_versteckt = _re.search(
            rf'class="[^"]*\b{_re.escape(klasse)}\b[^"]*"[^>]*\shidden', html)
        assert not (wird_versteckt and not versteckbar), (
            f".{klasse} setzt display und wird im HTML mit hidden ausgeliefert"
            f" -- ohne .{klasse}[hidden] {{ display: none }} bleibt es sichtbar.")


def test_die_uebersetzungspruefung_der_ci_laeuft_auch_hier():
    """tools/i18n_pruefen.py als Test, nicht nur als CI-Schritt.

    Am 06.09.2026 war der CI-Lauf "Pruefen" ZWOELF Pushes in Folge rot, seit
    mindestens dem 05.09. -- und niemand hat es bemerkt, weil daneben der
    Lauf "Images bauen" gruen war und nur der gemeldet wurde. Ein Waechter,
    den man nicht sieht, ist keiner.

    Hier laeuft er in derselben Suite wie alles andere. Wer pytest fahren
    kann, sieht ihn.
    """
    import subprocess
    import sys
    wurzel = Path(__file__).resolve().parents[3]
    werkzeug = wurzel / "tools" / "i18n_pruefen.py"
    assert werkzeug.exists(), f"{werkzeug} nicht gefunden"
    lauf = subprocess.run([sys.executable, str(werkzeug)],
                          cwd=str(wurzel), capture_output=True, text=True)
    assert lauf.returncode == 0, (
        "Die Uebersetzungspruefung schlaegt fehl:\n"
        + lauf.stdout + lauf.stderr)


def test_das_javascript_ist_syntaktisch_heil():
    """`node --check` als Test, nicht nur als CI-Schritt.

    Am 06.09.2026 hat ein deutsches Anfuehrungszeichen in einem
    Uebersetzungstext („Quellen") die Zeichenkette geschlossen und die ganze
    Datei zerbrochen -- eine Oberflaeche, die gar nicht mehr laedt. Die CI
    haette es gefunden, aber erst nach dem Push, und dieselbe Lehre wie bei
    der Uebersetzungspruefung gilt hier: ein Waechter, den man beim Arbeiten
    nicht sieht, kommt zu spaet.

    Ist node nicht da, wird uebersprungen statt falsch gruen gemeldet.
    """
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node nicht vorhanden -- die CI prueft es trotzdem")
    for datei in ("app.js", "qr.js"):
        lauf = subprocess.run([node, "--check", str(WEB / datei)],
                              capture_output=True, text=True)
        assert lauf.returncode == 0, datei + ": " + lauf.stderr


# ── Das Kursbild ─────────────────────────────────────────────────────────────
# Zweimal nachgebessert, beide Male weil der Betreiber es im Bild gesehen hat und
# nicht weil ein Test angeschlagen haette. Diese hier halten fest, was daraus
# folgte.

def _kurs_teil(js):
    return js[js.index("/* Die Zeichnung."):js.index("/* ── Nachrichten ─")]


def test_das_kursbild_wird_nicht_gestreckt(html, js):
    """preserveAspectRatio="none" streckt auch die SCHRIFT.

    Am 06.09.2026 stand deshalb ein festes viewBox="0 0 900 220" auf 1850
    Pixel gezogen im Bild, mit breitgezogenen, unlesbaren Beschriftungen.
    Die viewBox kommt jetzt aus der gemessenen Groesse.
    """
    kasten = html[html.index('id="kurs-svg"'):]
    marke = kasten[:kasten.index(">") + 1]
    assert "preserveAspectRatio" not in marke, marke
    assert "viewBox" not in marke, "die viewBox gehoert gemessen, nicht gesetzt"
    assert "getBoundingClientRect" in _kurs_teil(js)


def test_kein_diagramm_wird_gestreckt(js, html):
    """Dieselbe Falle, zweimal getreten -- also eine Wache ueber ALLE.

    Erst das Kursbild (06.09.2026, "mehr als peinlich"), dann am 07.09.2026
    das Feerate-Diagramm im Mempool: festes viewBox="0 0 700 190" auf 1564
    Pixel gezogen, gemessene Streckung 2,23-fach in der Breite bei 1,00 in
    der Hoehe. Die Schrift wird davon genauso breitgezogen wie die Linien.

    preserveAspectRatio="none" ist fuer eine Zeichnung mit Beschriftung
    schlicht falsch. Wer eine SVG auf die Kastenbreite ziehen will, misst den
    Kasten und baut die viewBox daraus -- dann ist der Massstab 1:1 und es
    braucht das Attribut gar nicht.
    """
    # Die Kommentare RICHTIG wegnehmen, nicht Zeile fuer Zeile raten: die
    # Warnung davor steht selbst in einem Blockkommentar, und dessen zweite
    # Zeile faengt mit "1." an. Genau daran ist der erste Anlauf dieses
    # Tests haengengeblieben -- dieselbe Falle wie bei der CSS-Wache, die
    # ihren eigenen Kommentar als Selektor gelesen hat.
    import re
    ohne = {
        "app.js": re.sub(r"//[^\n]*", "",
                         re.sub(r"/\*.*?\*/", "", js, flags=re.S)),
        "index.html": re.sub(r"<!--.*?-->", "", html, flags=re.S),
    }
    for wo, text in ohne.items():
        for zeile in text.splitlines():
            if "preserveAspectRatio" not in zeile:
                continue
            assert '"none"' not in zeile and "'none'" not in zeile, \
                f"{wo}: {zeile.strip()}"


def test_das_feerate_diagramm_misst_seinen_kasten(js):
    """Und zeichnet neu, wenn er sich aendert -- sonst stimmt die viewBox
    nach jedem Fensterwechsel nicht mehr."""
    teil = js[js.index("function zeichneDiagramm"):
              js.index("function diaNeuZeichnenBald")]
    assert "getBoundingClientRect" in teil
    assert "ResizeObserver" in js and "diaNeuZeichnenBald" in js


def test_das_feerate_diagramm_beschriftet_beide_achsen(js):
    """Des Betreibers Beanstandung am Kursbild galt genauso hier: Zahlen ohne
    Einheit auf der einen Achse, gar nichts auf der anderen."""
    teil = js[js.index("function zeichneDiagramm"):
              js.index("function diaNeuZeichnenBald")]
    assert 'a_dia_y' in teil, "die Y-Achse braucht ihre Einheit"
    assert 'a_dia_bloecke' in teil and 'a_dia_block' in teil, \
        "die X-Achse braucht Marken -- und den Singular dazu"


def test_das_kursbild_hat_beide_achsen(js):
    """Der Betreiber: 'es fehlt komplett die Achsenbezeichnung ... der X und Y
    Achse'. Ein Bild ohne Massstab ist eine Form."""
    teil = _kurs_teil(js)
    assert "kursStufe" in teil, "keine runden Stufen fuer die Preisachse"
    assert "kursZeitmarke" in teil, "keine Zeitmarken fuer die X-Achse"
    # Und die Zeitmarken richten sich nach dem Fenster.
    assert '"24h"' in teil and '"5j"' in teil


def test_das_kursbild_laesst_sich_ablesen(js):
    """Der Betreiber: 'ich will dann wie in einem richtigen chart auf nen punkt
    gehen koennen mit uhrzeit tag oder so und dann kurs'."""
    teil = _kurs_teil(js)
    for noetig in ("pointermove", "pointerleave", "kursZeigeBei",
                   "kursIndexBei", "kurs-blase"):
        assert noetig in teil, noetig
    # Mit dem Finger geht es auch -- ein Finger hat kein "verlassen".
    assert "pointerdown" in teil and '"touch"' in teil
    # Und mit der Tastatur: ein Bild, das nur die Maus lesen kann, ist fuer
    # ein Vorleseprogramm gar nichts.
    assert "keydown" in teil
    for taste in ("ArrowLeft", "ArrowRight", "Home", "End", "Escape"):
        assert taste in teil, taste


def test_die_sprechblase_faengt_keine_zeiger_ab(css):
    """Sonst floehe der Zeiger vor seiner eigenen Blase und das Ablesen
    flackerte."""
    block = css[css.index(".kurs-blase {"):]
    assert "pointer-events: none" in block[:block.index("}")]


def test_das_kursbild_folgt_seiner_eigenen_groesse(js):
    """Ein resize-Zuhoerer am Fenster reicht nicht: der Kasten wechselt seine
    Groesse auch beim Einblenden der Ansicht. Beim Pruefen gemessen: Breite
    0, viewBox 900 -- und so waere es geblieben."""
    assert "ResizeObserver" in _kurs_teil(js)


def test_keine_tabelle_kann_ihre_zellen_abschneiden(css):
    """Jede Tabelle braucht eine der beiden Vorkehrungen.

    Am 06.09.2026 schickte der Betreiber ein Bild der Laenderansicht Suedkorea: aus
    "339" war "33" geworden. Nachgemessen -- Tabelle 348 Punkte breit, Zellen
    374, also 26 Punkte Ueberstand. Ursache war der uebliche Kniff
    `td:first-child { width: 100% }` zusammen mit nicht umbrechenden
    Zahlenspalten: die Zellen sprengen den Tabellenkasten. Ein waagerechter
    Rollbalken war zwar da, auf macOS aber unsichtbar -- der Nutzer sieht nur
    abgeschnittene Zahlen.

    Zwei Wege sind in Ordnung:

    * `table-layout: fixed` -- die angegebenen Breiten gelten, nichts laeuft
      hinaus (so jetzt .wl-tabelle);
    * ein Umschlag mit `overflow-x: auto` UND einer sichtbaren Breite, damit
      der Rollbalken auch etwas zu rollen hat (so .ausw-tabelle).

    Was keines von beidem hat, schneidet frueher oder spaeter ab.
    """
    import re as _re
    ohne_kommentare = _re.sub(r"/\*.*?\*/", " ", css, flags=_re.S)
    for treffer in _re.finditer(r"\.([\w-]+)\s*\{([^}]*)\}", ohne_kommentare):
        name, koerper = treffer.group(1), treffer.group(2)
        if "border-collapse" not in koerper:
            continue
        fest = "table-layout" in koerper and "fixed" in koerper
        # Der Umschlag heisst wie die Tabelle, nur ohne " table".
        umschlag = _re.search(
            rf"\.{_re.escape(name)}\s*\{{[^}}]*overflow-x:\s*auto",
            ohne_kommentare)
        assert fest or umschlag, (
            f".{name} hat weder table-layout:fixed noch einen Umschlag mit "
            "overflow-x:auto -- ihre Zellen koennen abgeschnitten werden.")


def test_die_laenderansicht_bricht_lange_namen_um(css):
    """Es gibt Gebietsnamen mit fuenfzig Zeichen -- "Zentraler und westlicher
    Teil von Hong Kong Island". Ohne Umbruch sprengen die jede Spalte."""
    block = css[css.index(".wl-tabelle td:first-child {"):]
    block = block[:block.index("}")]
    assert "overflow-wrap" in block
    # NICHT "anywhere": das trennt mitten im Wort, aus "Chungcheongnam-do"
    # wurde "Chungche-ongnam-do".
    assert "anywhere" not in block, "anywhere trennt mitten im Wort"


def test_hinweistexte_koennen_umbrechen(css):
    """Eine Adresse ohne Leerzeichen sprengt sonst die Seite.

    Am 06.09.2026 auf 375 Punkten gemessen: der Hinweis unter dem
    Sicherungsziel enthaelt
    "https://cloud.example/remote.php/dav/files/DEINNAME/Sicherungen" --
    dreiundsechzig Zeichen am Stueck. Der schob den Rahmen von 375 auf 427
    Punkte, und die ganze Seite lief quer.
    """
    import re as _re
    ohne = _re.sub(r"/\*.*?\*/", " ", css, flags=_re.S)
    assert _re.search(r"\.feld\s*>\s*span[^{]*\{[^}]*overflow-wrap", ohne), (
        "Hinweistexte unter Feldern brechen nicht um")


def test_keine_uebersetzung_traegt_eine_unteilbare_zeile(js):
    """Und der Text selbst darf nicht laenger sein, als ein Telefon breit ist.

    Prueft die Ursache statt der Wirkung: eine Zeichenkette ohne Leerzeichen
    ueber achtzig Zeichen passt auf kein Telefon, auch mit Umbruch nicht
    huebsch. Die eine bekannte Ausnahme ist die Beispieladresse oben -- die
    IST der Hinweis.
    """
    import re as _re
    lang = []
    for treffer in _re.finditer(r'^\s{4}(\w+): "([^"]{40,})"', js, _re.M):
        for wort in treffer.group(2).split():
            if len(wort) > 80:
                lang.append((treffer.group(1), wort[:50]))
    assert not lang, f"unteilbare Zeichenketten: {lang}"


# ── Die Blockstreifen ──────────────────────────────────────────────────────


def test_die_blockkaesten_werden_ohne_innerHTML_gebaut(js):
    """Pool-Namen und Botschaften kommen aus dem Block -- also aus etwas, das
    ein fremder Miner geschrieben hat. Sie als HTML einzusetzen waere die
    klassische Luecke."""
    teil = js[js.index("function zeichneBlockstreifen"):
              js.index("let BLOCK_LISTE = [];")]
    assert "innerHTML" not in teil and "insertAdjacentHTML" not in teil


def test_die_kommenden_bloecke_teilen_ein_haeppchen_anteilig(js):
    """Ein Cluster-Haeppchen reicht oft ueber eine Blockgrenze hinweg. Wer es
    ganz in einen Kasten wirft, bekommt Kaesten mit 1,3 MB -- und eine
    Gebuehrenspanne, die zum falschen Block gehoert."""
    teil = js[js.index("function kommendeBloecke"):
              js.index("function zeichneKommendeBloecke")]
    assert "Math.min(dv, BLOCK_VB - eimer.vsize)" in teil, \
        "das Haeppchen muss an der Blockgrenze geteilt werden"


def test_der_blockstreifen_rollt_statt_umzubrechen(css):
    """Auf dem Handy passt kein Streifen nebeneinander. Er rollt -- mit
    sichtbarem Balken, denn macOS blendet ihn sonst aus."""
    block = css[css.index(".blockstreifen {"):css.index(".blockkasten {")]
    assert "overflow-x: auto" in block
    assert "scrollbar-color" in block


def test_die_blockkaesten_stehen_auf_gleicher_hoehe(css):
    """Kaesten, deren Text unterschiedlich oft umbricht, stehen sonst
    verschieden hoch nebeneinander -- und ein Streifen, dessen Kaesten nicht
    auf einer Linie sitzen, sieht kaputt aus."""
    block = css[css.index(".blockkasten {"):css.index(".blockkasten .bk-kopf")]
    assert "min-height" in block


def test_kleine_groessen_werden_nicht_zu_null_gerundet(js):
    """Eine Transaktion misst zwei-, dreihundert Byte. Als "0 kB" sieht das
    aus wie eine kaputte Anzeige -- dieselbe Falle, die bei "0 MB" waehrend
    des Erstabgleichs schon einmal zugeschlagen hat, nur eine Groessenordnung
    tiefer. Gefunden am 08.09.2026 in der Kachelliste."""
    teil = js[js.index("function menschenBytes"):
              js.index("\n}", js.index("function menschenBytes"))]
    assert 'return Math.round(b) + " B"' in teil, \
        "unter tausend Byte gehoert die Einheit Byte"


# ═════════════════════ die Sichtbarkeit bekommt keine Vorgabe ══════════
#
# Der Betreiber sah am 09.09.2026 auf der Knoten-Seite ZWEI angekuendigte Adressen:
# seine Onion und seine oeffentliche IP. Er hatte nie eine Betriebsart
# gewaehlt -- im Assistenten war "hybrid" vorausgewaehlt, und im Zustand
# stand dasselbe. Wer durchklickt, ohne zu lesen, veroeffentlicht damit
# seinen Anschluss im Lightning-Graphen, ohne je entschieden zu haben.
#
# Und rueckgaengig geht es nicht: die Adresse ist dann unterwegs.

def test_keine_betriebsart_ist_vorausgewaehlt(html):
    block = html[html.index('name="n-sicht"'):]
    block = block[:block.index("</div>")]
    assert "checked" not in block, (
        "eine vorausgewaehlte Betriebsart entscheidet ueber die "
        "Auffindbarkeit des eigenen Anschlusses -- das darf nicht nebenbei "
        "passieren")


def test_der_assistent_startet_ohne_betriebsart(js):
    assert 'sichtbarkeit: "",' in js, \
        "eine Vorgabe im Zustand ist dieselbe Entscheidung wie ein checked"


def test_ohne_wahl_geht_es_nicht_weiter(js):
    assert "const ohneWahl = !S.sichtbarkeit;" in js
    assert "ohneWahl ||" in js, \
        "ohne getroffene Wahl muss der Weiter-Knopf gesperrt bleiben"


def test_jede_betriebsart_sagt_ihre_folge(js):
    """Auch die bequeme. Vorher bekamen nur "tor" und "still" einen
    Folgesatz -- ausgerechnet die Wahl, die die IP veroeffentlicht, blieb
    stumm."""
    for schluessel in ("lnsicht_folge_tor", "lnsicht_folge_still",
                       "lnsicht_folge_hybrid", "lnsicht_waehlen"):
        assert f't("{schluessel}")' in js, schluessel


def test_eine_angekuendigte_ip_wird_als_solche_benannt(js):
    """"Ohnehin oeffentlich" stimmt formal und verharmlost genau das,
    worauf es ankommt: eine .onion ist eine Adresse, eine IP ist der
    Anschluss."""
    assert 'includes(".onion")' in js, \
        "es muss unterschieden werden, ob wirklich Klartext dabei ist"
    assert 't("lgi_klartext")' in js


# ═══════════════════ der Wallet-Ablauf sagt, wo man steht ══════════════
#
# Aus dem Betrieb, 09.09.2026, mitten im Ablauf: "ok ich habe hier nur den button
# woerter erzeugen" -- den Schalter darueber hatte er nicht gesehen. Und
# spaeter: "es sollte dann wallet erstellen heissen und nicht woerter
# erstellen". Der eigentliche Mangel war beides Mal derselbe: der Ablauf hat
# drei Schritte und sagte nie, der wievielte gerade dran ist und ab wann es
# endgueltig wird.

def test_jeder_schritt_sagt_der_wievielte_er_ist(html):
    for pid, schluessel in (("w-schritt-start", "wl_schritt1"),
                            ("w-schritt-woerter", "wl_schritt2"),
                            ("w-schritt-probe", "wl_schritt3")):
        block = html[html.index(f'id="{pid}"'):]
        block = block[:block.index("</h3>")]
        assert f'data-i18n="{schluessel}"' in block, pid


def test_der_erste_schritt_sagt_dass_noch_nichts_entsteht(html):
    block = html[html.index('id="w-schritt-start"'):]
    block = block[:block.index('id="w-schritt-woerter"')]
    assert 'data-i18n="wl_noch_nichts"' in block
    assert 'data-i18n="wl_eine_einzige"' in block, (
        "dass es genau EINE Wallet gibt und sie die Identitaet des Knotens "
        "ist, muss dastehen -- sonst sieht die Abwesenheit eines Namensfelds "
        "wie eine fehlende Funktion aus")


def test_das_passwortfeld_ist_immer_da(html):
    """Vorher war die Zeile versteckt, solange Auto-Entsperren an war -- und
    dann wuerfelte die Anwendung ein Passwort, das niemand je zu sehen
    bekam."""
    block = html[html.index('id="w-passwort-zeile"'):]
    block = block[:block.index(">")]
    assert "hidden" not in block


def test_kein_weg_wuerfelt_das_wallet_passwort(html, js):
    """Die Regel hinter dem Test darueber, jetzt allgemein formuliert.

    Es gab kurz einen Weg, auf dem die Anwendung das Wallet-Passwort selbst
    wuerfelte: den Tresor. Der ist am 10.09.2026 herausgeflogen, und damit
    die Ausnahme. In JEDEM Weg tippt der Nutzer sein Passwort -- ein
    Passwort, das nur die Anwendung kennt, ist nach einem Stromausfall
    keines mehr.
    """
    assert 'id="w-fertig-passwort"' not in html
    assert "wallet_passwort" not in js
    assert 'id="w-passwort-zeile"' in html


def test_der_entsperrweg_steht_beim_passwort(html):
    """Er entscheidet, WO das Passwort liegt. Zwei Schritte vor dem Feld, auf
    das er sich bezieht, waere er eine Frage ohne Zusammenhang."""
    probe = html[html.index('id="w-schritt-probe"'):]
    assert 'name="w-weg"' in probe
    assert probe.index('id="w-passwort-zeile"') < probe.index('name="w-weg"')


def test_es_gibt_drei_entsperrwege_und_jeder_sagt_was_er_kostet(html, js):
    """Aus dem Betrieb, 10.09.2026: "das soll sich jeder nutzer aussuchen koennen
    ob sich das wallet selbst entsperrt ob ich den tresor will .. oder
    nicht." Drei Wege, drei eigene Folgesaetze -- ein gemeinsamer waere
    wieder ein Haekchen mit zwei Antworten."""
    for weg in ("aus", "merken", "datei"):
        assert f'value="{weg}"' in html, weg
        anfang = js.index(f'    wl_weg_folge_{weg}: "')
        satz = js[anfang:js.index('",\n', anfang)]
        assert len(satz) > 120, f"{weg}: das ist keine Folge, das ist ein Wort"
    # Und die Warnung sitzt dort, wo sie hingehoert.
    stelle = js.index("function entsperrwegFolge(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'weg === "datei" ? " warn"' in block


def test_es_gibt_genau_ein_geheimnis_zum_entsperren(js):
    """Der Tresor stellte ein zweites daneben, das dasselbe tat. Aus dem Betrieb, am
    10.09.2026: "ich tausche ein passwort gegen das andere obwohl beide die
    selbe funktion unterm strich haben"."""
    assert "async function entsperrwegLaden(" in js
    stelle = js.index("async function walletEntsperren(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'api("/lightning/entsperren", "POST", { passwort: feld.value })' \
        in block
    assert "passphrase" not in block


def test_der_weg_merken_sagt_dass_er_sich_merkt(js):
    """Sonst sieht die Eingabe genauso aus wie bei "aus" -- und der
    Unterschied waere nirgends zu sehen."""
    stelle = js.index("async function entsperrwegLaden(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'ENTSPERRWEG === "merken" ? " " + t("wl_entsperren_gemerkt")' \
        in block


def test_nach_einem_neustart_sagt_die_oberflaeche_dass_nichts_gemerkt_ist(js):
    """Der Weg "merken" ueberlebt einen Neustart der Anwendung, das gemerkte
    Passwort nicht. Das zu verschweigen hiesse zu behaupten, es kuemmere
    sich jemand darum -- waehrend der Knoten stillsteht."""
    stelle = js.index("function zeichneEntsperrwegWahl(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 't("ew_noch_nicht_gemerkt")' in block
    assert 'ENTSPERRWEG === "merken" && !GEMERKT' in block


def test_der_fehler_zur_wortprobe_steht_bei_der_wortprobe(html, js):
    probe = html[html.index('id="w-schritt-probe"'):]
    assert 'id="w-probe-fehler"' in probe
    assert (probe.index('id="w-probe-felder"')
            < probe.index('id="w-probe-fehler"')
            < probe.index('id="w-passwort-zeile"')), (
        "die Meldung ueber die WOERTER darf nicht unter dem Passwortfeld "
        "stehen -- genau so hat der Betreiber sie auf sein Passwort bezogen")
    assert 'd.meldung === "gegenprobe_falsch"' in js


def test_die_wortfelder_sehen_aus_wie_der_rest(css):
    """Sie waren ungestaltet: weisser Grund, schwarze Schrift, grauer
    Standardrahmen -- mitten in einer dunklen Oberflaeche, und ausgerechnet
    dort, wo jemand unter Zeitdruck seinen Seed tippt."""
    block = css[css.index(".probe-feld input"):]
    block = block[:block.index("}")]
    assert "background:" in block and "color:" in block and "border:" in block
    assert ".seedeingabe input" in css[css.index(".probe-feld input"):
                                       css.index(".probe-feld input") + 200]


def test_die_tunzeile_steht_ueber_allen_ansichten(html):
    """Eine gesperrte Wallet haelt den Knoten an -- das gilt auf jeder
    Seite, nicht nur auf der Uebersicht."""
    inhalt = html[html.index('<main class="inhalt">'):]
    assert inhalt.index('id="tunzeile"') < inhalt.index("<section"), (
        "sie gehoert vor die Ansichten, nicht in eine davon")


def test_die_tunzeile_startet_versteckt(html):
    i = html.index('id="tunzeile"')
    block = html[html.rindex("<div", 0, i):html.index(">", i) + 1]
    assert "hidden" in block, (
        "kein Dauerbanner -- sie erscheint nur, wenn wirklich etwas ansteht")


def test_die_tunzeile_fuehrt_auch_hin(js):
    assert "zeigeAnsicht(schritt.ansicht)" in js, (
        "Befund 13: der Zustand stand dort, wo man nicht handeln kann")


def test_der_lightning_hinweis_kennt_den_wallet_zustand(js):
    """Er kannte bis zum 09.09.2026 NUR die Kette. Der Betreiber hatte seine
    Wallet laengst angelegt und las weiter "der naechste Schritt ist die
    Wallet" -- ein Satz, der schlicht nicht mehr stimmte."""
    block = js[js.index('$("#d-ln-hinweis")') - 400:]
    block = block[:block.index(";", block.index('$("#d-ln-hinweis")'))]
    for schluessel in ("ln_hinweis_sync", "ln_hinweis_bereit",
                       "ln_hinweis_gesperrt", "ln_hinweis_laeuft",
                       "ln_hinweis_startet"):
        assert schluessel in block, schluessel
    assert "lnstand" in block, "ohne den Wallet-Zustand geht es nicht"


def test_nur_waehlbare_hinweise_lassen_sich_wegnehmen(js):
    assert 'weg.classList.toggle("hidden", !schritt.abweisbar)' in js, (
        "ein Zustand darf sich nicht wegklicken lassen -- er verschwindet, "
        "wenn man ihn erledigt")


def test_das_loeschen_sieht_nicht_aus_wie_speichern(html, css):
    """Ein Knopf, der eine Wallet unwiederbringlich zerstoert, darf nicht
    dieselbe Farbe haben wie die Hauptaktion."""
    i = html.index('id="tg-loeschen"')
    block = html[html.rindex("<button", 0, i):html.index(">", i) + 1]
    assert "gefahr" in block
    assert ".btn.gefahr" in css


def test_das_loeschen_verlangt_beides(html):
    formular = html[html.index('id="tg-formular"'):]
    formular = formular[:formular.index('id="tg-loeschen"')]
    assert 'id="tg-passwort"' in formular, "ohne Passwort kein Loeschen"
    assert 'id="tg-alias"' in formular, "und der Name als Bremse"


def test_das_formular_erscheint_erst_bei_gesperrter_wallet(js):
    """LND kann sein Passwort nur beim Entsperren pruefen -- also nur an
    einer gesperrten Wallet. Ein Passwortfeld, das nichts prueft, waere
    eine Attrappe."""
    assert 'const gesperrt = stand === "gesperrt";' in js
    assert '$("#tg-formular").classList.toggle("hidden", !gesperrt)' in js


# ── Ein zugeklappter Abschnitt ist trotzdem ein Abschnitt ──────────────────
#
# Aus dem Betrieb, 10.09.2026, nach dem ersten Blick auf das fertige Loeschen:
# "wallet loeschen erstmal in einem anderen text disgin find ich nicht gut!
# ... und das dass direkt oben als erstes steht find ich auch nicht gut das
# gehoert ans untere ende".
#
# Beides stimmt, und beides hat dieselbe Ursache: <details class="panel">
# wurde wie ein Kasten behandelt, aber sein <summary> nicht wie eine
# Ueberschrift. Die anderen Kaesten holen ihre Schrift aus ".panel h3" --
# ein <summary> erbt davon nichts und bekommt die Vorgabeschrift des
# Browsers. Zwischen lauter orangenen Versalien stand eine weisse Zeile.

def _regelblock(css, selektor):
    stelle = css.index(selektor + " {")
    return css[stelle + len(selektor) + 2:css.index("}", stelle)]


def _schriftbild(block):
    """Nur die typografischen Angaben -- Abstaende duerfen abweichen."""
    gesucht = ("font-size", "letter-spacing", "text-transform", "color",
               "font-weight")
    werte = {}
    for stueck in block.replace("\n", " ").split(";"):
        if ":" not in stueck:
            continue
        name, wert = stueck.split(":", 1)
        if name.strip() in gesucht:
            werte[name.strip()] = wert.strip()
    return werte


def test_ein_zugeklappter_abschnitt_traegt_dieselbe_ueberschrift(html, css):
    """Jedes <details class="panel"> muss aussehen wie seine Nachbarn."""
    assert 'class="panel hidden" id="w-tilgen"' in html, (
        "dieser Test haengt an einem zugeklappten Abschnitt -- wenn es "
        "keinen mehr gibt, gehoert er weg")
    assert _schriftbild(_regelblock(css, "details.panel > summary")) == \
        _schriftbild(_regelblock(css, ".panel h3"))


def test_der_browser_eigene_pfeil_ist_weg(css):
    """Sonst stehen zwei Marken nebeneinander: seine und unsere.

    ``list-style: none`` genuegt dafuer nicht -- WebKit zeichnet sein
    ::-webkit-details-marker unabhaengig davon.
    """
    block = _regelblock(css, "details.panel > summary")
    assert "list-style: none" in block
    assert "details.panel > summary::-webkit-details-marker" in css


def test_das_loeschen_steht_am_ende_der_einrichtung(html):
    """Der gefaehrlichste Handgriff der Ansicht gehoert ans Ende.

    Er stand als erster Kasten ganz oben -- also vor dem Anlegen, vor dem
    Einzahlen, vor der Sicherung. Wer die Wallet einrichten will, liest als
    Erstes, wie man sie wegwirft.
    """
    import re
    abschnitt = html[html.index('<section data-ansicht="ln-einrichtung"'):]
    abschnitt = abschnitt[:abschnitt.index("</section>")]
    kaesten = re.findall(r'class="panel[^"]*" id="([\w-]+)"', abschnitt)
    assert kaesten, "keine Kaesten gefunden -- der Test misst nichts"
    assert kaesten[-1] == "w-tilgen", (
        f"letzter Kasten ist {kaesten[-1]}, erwartet w-tilgen")


# ── Der Umrechner ──────────────────────────────────────────────────────────
#
# Die Rechnung selbst steht in test_rechner.py und laeuft dort durch node.
# Hier nur, was die Rechnung an die Oberflaeche bindet.

def test_der_rechner_hat_seinen_eigenen_reiter(html):
    """Aus dem Betrieb, 10.09.2026: "der umrechner kann ja auch links nen eigenden
    reiter bekommen." """
    assert 'data-ansicht="rechner" data-i18n="nav_rechner"' in html
    assert '<section data-ansicht="rechner"' in html
    for kennung in ("rn-sat", "rn-btc", "rn-fiat", "rn-je-btc", "rn-je-fiat"):
        assert f'id="{kennung}"' in html, f"{kennung} fehlt"


def test_der_rechner_bekommt_seinen_kurs_auch_ohne_die_news_ansicht(js):
    """ladeKurs lief nur, solange die Nachrichten offen waren. Ohne diese
    Zeile stuende im Rechner dauerhaft ein Strich, wo der Kurs hingehoert --
    und die Fremdwaehrung bliebe leer."""
    # Inhaltlich geprueft, nicht als eine bestimmte Zeile: seit dem
    # 16.09.2026 holt auch die Uebersicht den Kurs, und die Bedingung steht
    # deshalb ueber zwei Zeilen.
    bedingung = js[js.index("async function ladeKurs"):
                   js.index("function kursText")]
    assert 'ANSICHT !== "news"' in bedingung
    assert 'ANSICHT !== "rechner"' in bedingung
    assert "zeichneRechner(d);" in js


def test_das_feld_in_dem_getippt_wird_bleibt_unangetastet(js):
    """Wer ein Feld waehrend der Eingabe neu beschreibt, schiebt den
    Schreibzeiger ans Ende -- aus "1,5" wird beim naechsten Zeichen etwas
    anderes, als der Mensch tippen wollte."""
    stelle = js.index("function rechnerSchreiben(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'if (feld && name !== ausser) feld.value = text;' in block


def test_kein_ergebnis_und_das_ergebnis_null_sind_zweierlei(js):
    """"0 sat" ist eine Aussage. Ein leeres Feld auch. Sie duerfen nicht
    dasselbe bedeuten -- deshalb gibt rechnerUmrechnen null zurueck und
    nicht etwa Nullen."""
    stelle = js.index("function rechnerUmrechnen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert block.count("return null;") >= 3


# ── "Da oben steht nix" ────────────────────────────────────────────────────
#
# Aus dem Betrieb, 10.09.2026, mit einem Bild vom leeren Kasten: "unter knoten
# bekomme ich aber keine verbindungs adresse angezeigt oder dauert das nur
# ewig?"
#
# Die Anwendung WEISS die Antwort. Bei "gar nicht ankuendigen" steht dort nie
# etwas, und das ist kein Fehler -- er haette ewig gewartet. Bei "nur ueber
# Tor" entsteht die Onion-Adresse erst beim Start. Bei "Tor und Clearnet"
# fehlt schlicht die eigene Adresse. Drei Lagen, drei naechste Schritte -- und
# gezeigt wurde fuer alle drei derselbe dimme Halbsatz neben dem Knopf.

def test_der_leere_adresskasten_sagt_warum(html, js):
    assert 'id="lgi-warum"' in html
    stelle = js.index("function zeichneEigeneAdresse(")
    block = js[stelle:js.index("\n}\n", stelle)]
    # Der Schluessel wird zusammengesetzt -- seit dem 11.09.2026 ueber eine
    # Zwischenvariable, weil "beschaeftigt" alle drei Betriebsarten schlaegt.
    assert '"lgi_keine_" + (k && k.sichtbarkeit' in block
    assert "t(grund)" in block
    assert '$("#lgi-warum")' in block


def test_jede_betriebsart_hat_ihren_eigenen_satz(js):
    """Ein gemeinsamer Satz fuer drei verschiedene Lagen waere wieder der
    alte Zustand -- nur laenger."""
    saetze = {}
    for art in ("still", "tor", "hybrid", "unklar"):
        anfang = js.index(f"    lgi_keine_{art}: \"")
        saetze[art] = js[anfang:js.index('",\n', anfang)]
    assert len(set(saetze.values())) == 4, "zwei Betriebsarten teilen sich einen Satz"
    # Der wichtigste Unterschied: bei "still" ist es KEIN Fehler und kein
    # Warten, sondern eine Wahl. Genau das muss dort stehen.
    assert "Wahl" in saetze["still"]
    assert "Einstellungen" in saetze["still"]
    # Und bei den beiden anderen gehoert eine Zeitangabe dazu, sonst wartet
    # jemand wieder ins Blaue.
    for art in ("tor", "hybrid"):
        assert "Minuten" in saetze[art], art


def test_die_betriebsart_kommt_aus_der_antwort_und_nicht_aus_lnd(js):
    """Sie ist unsere Einstellung, nicht LNDs Zustand. Kaeme sie aus
    getinfo, stuende sie dort nie."""
    assert "sichtbarkeit: d.sichtbarkeit" in js


# ── Werte, die man weitergeben koennen muss ────────────────────────────────
#
# Aus dem Betrieb, 10.09.2026: "unter Kennung: solte die volle kennung stehen damit
# sie mal kopieren kann und genau das selbe gilt fuer angekuendigt".
#
# kurz() war dort von Anfang an falsch am Platz. Es macht 66 Zeichen lesbar --
# und genau das ist der Punkt: eine gekuerzte Kennung ist nur noch zum ANSEHEN
# gut. Wer sie braucht, braucht sie ganz.

def test_kennung_und_adressen_stehen_vollstaendig_da(js):
    stelle = js.index("function zeichneLnIch(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "kurz(k.kennung" not in block, "die Kennung wird wieder gekuerzt"
    assert "map(kurz)" not in block, "die Adressen werden wieder gekuerzt"
    assert 'langzeile(t("lk_kennung")' in block
    assert 'langzeile(t("lk_adressen")' in block


def test_zu_jedem_langen_wert_gehoert_ein_kopierknopf(js):
    """Markieren mit der Maus ist bei 66 Zeichen kein Weg -- und ueber
    http:// im Heimnetz gibt es die Zwischenablage des Browsers gar nicht.
    Genau dafuer gibt es kopiere() mit seinen drei Stufen."""
    stelle = js.index("function langzeile(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "kopiere(" in block
    assert "user-select" not in block, "das gehoert ins Stilblatt"


def test_ein_langer_wert_laeuft_nicht_aus_dem_kasten(css):
    aussen = css[css.index(".langwert {"):]
    aussen = aussen[:aussen.index("}")]
    assert "min-width: 0" in aussen, "sonst weigert sich der Flex-Kasten zu schrumpfen"
    innen = css[css.index(".langwert .v {"):]
    innen = innen[:innen.index("}")]
    assert "break-all" in innen, "66 Zeichen ohne Umbruch sprengen die Spalte"
    assert "user-select: all" in innen, "ein Klick soll den ganzen Wert fassen"


def test_die_kuerzung_bleibt_wo_sie_hingehoert(js):
    """kurz() ist nicht falsch -- nur an der falschen Stelle. In Listen, in
    denen man zwei Knoten auseinanderhalten will, bleibt es richtig."""
    assert "function kurz(" in js
    assert js.count("kurz(") > 1, "kurz() wird nirgends mehr benutzt"


# ── Den Entsperrweg nachtraeglich wechseln ─────────────────────────────────

def test_der_wechsel_steht_im_reiter_wallet(html, js):
    assert 'id="w-entsperrweg"' in html
    for kennung in ("ew-jetzt", "ew-probe", "ew-passwort", "ew-wechseln"):
        assert f'id="{kennung}"' in html, kennung
    assert "async function entsperrwegWechseln(" in js


def test_der_kasten_sagt_zuerst_was_heute_gilt(js):
    """Ohne das waere es eine Wahl ins Blaue: man sieht drei Moeglichkeiten
    und weiss nicht, in welcher man gerade steht."""
    stelle = js.index("function zeichneEntsperrwegWahl(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 't("ew_jetzt_" + ENTSPERRWEG)' in block
    assert 'passend.checked = true' in block, (
        "die heutige Betriebsart gehoert vorausgewaehlt")


def test_gefragt_wird_nur_was_wirklich_gebraucht_wird(js):
    """DER BEFUND VOM 10.09.2026. Der Betreiber: "habe aber gerade den Haken
    gesetzt bei fuer die Laufzeit merken aber das wird noch nicht
    uebernommen".

    Die Oberflaeche verlangte ein Passwort und eine gesperrte Wallet, um auf
    einen Weg zu wechseln, der gar nichts ablegt. Getippt werden muss es nur
    fuer EINEN Weg: "datei" schreibt Klartext auf die Platte."""
    stelle = js.index("function entsperrwegWahlFolge(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'ENTSPERRWEG === "datei"' in block
    assert 'ENTSPERRWEG === "merken" && GEMERKT' in block
    assert 'ziel === "datei" && !liegt_vor' in block


def test_der_sperrknopf_steht_dort_wo_die_meldung_ihn_verspricht(html, js):
    """Die Meldung sagt "sperre sie zuerst mit dem Knopf daneben". Bis zum
    10.09.2026 gab es ihn nur im Loesch-Kasten -- sie zeigte ins Leere."""
    anfang = html.index('id="w-entsperrweg"')
    teil = html[anfang:html.index("</section>", anfang)]
    assert 'id="ew-sperren"' in teil
    assert '$("#ew-sperren").addEventListener' in js
    # Und derselbe Handgriff, nicht ein zweiter daneben.
    assert "walletSperren(\"#ew-sperren\", \"#ew-sperr-meldung\")" in js


def test_die_eingaben_bleiben_nicht_im_formular_stehen(js):
    stelle = js.index("async function entsperrwegWechseln(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert '$("#ew-passwort").value = "";' in block


# ── Die PIN an der Oberflaeche ─────────────────────────────────────────────
#
# Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also knoten
# oeffnen oder schliessen geld transferieren".
#
# Die Endpunkte standen seit dem 10.09.2026, die Oberflaeche fehlte -- ein
# Schloss, das niemand einbauen kann, ist keines.

def test_die_pin_steht_bei_wer_darf_diesen_knoten_benutzen(html):
    """Nicht bei der Wallet: sie schuetzt gegen etwas anderes als der
    Entsperrweg. Der entscheidet, was jemand mit der PLATTE anfangen kann,
    die PIN steht gegen eine uebernommene SITZUNG."""
    anfang = html.index('<section data-ansicht="einstellungen"')
    teil = html[anfang:html.index("</section>", anfang)]
    assert 'id="e-pin"' in teil


def test_die_pin_einrichten_verlangt_das_kontopasswort(html, js):
    """Der wichtigste Test dieser Gruppe. Waere es anders, koennte eine
    uebernommene Sitzung sich SELBST eine PIN geben und damit anschliessend
    alles freigeben -- ein Schloss, dessen Schluessel der Einbrecher
    aussucht."""
    assert 'id="pin-konto"' in html
    stelle = js.index("async function pinEinrichten(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'passwort: $("#pin-konto").value' in block


def test_die_wiederholung_wird_im_browser_geprueft(html, js):
    """Der Server bekommt nur EINE der beiden Eingaben zu sehen -- er kann
    es also gar nicht merken."""
    assert 'id="pin-wdh"' in html
    stelle = js.index("async function pinEinrichten(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert '$("#pin-neu").value !== $("#pin-wdh").value' in block
    assert 't("pin_stimmt_nicht")' in block


def test_ohne_eingerichtete_pin_fragt_nichts_danach(js):
    """Wer keine will, soll nicht ploetzlich vor einer Abfrage stehen, die
    es fuer ihn gar nicht gibt."""
    stelle = js.index("function mitPin(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 'PIN_DA ? { pin: $(feld).value } : {}' in block
    # Und ob sie eingerichtet ist, weiss nur der Server.
    laden = js[js.index("async function pinLaden("):]
    laden = laden[:laden.index("\n}\n")]
    assert 'api("/freigabe")' in laden
    assert 'PIN_DA = !!d.eingerichtet' in laden


def test_das_loeschen_fragt_nach_der_pin(html, js):
    """Der einzige Handgriff, den sie heute bewacht -- und der, bei dem es
    am meisten zaehlt."""
    assert 'id="tg-pin-zeile"' in html
    stelle = js.index("async function walletTilgen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert '...mitPin("#tg-pin")' in block
    assert '$("#tg-pin").value = "";' in block, (
        "eine PIN, die im Formular stehen bleibt, ist keine")


def test_die_sperre_sagt_wie_lange_noch(js):
    """Ohne die Zahl steht der Nutzer vor einem Feld, das nichts annimmt,
    und weiss nicht, ob es an ihm liegt."""
    stelle = js.index("async function pinLaden(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 't("pin_stand_gesperrt", { sekunden: d.wartet_noch })' in block


def _ohne_js_kommentare(teil):
    ohne = re.sub(r"/\*.*?\*/", " ", teil, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*$", " ", ohne, flags=re.M)


def test_jede_ansicht_mit_pin_feld_fragt_ob_eine_pin_da_ist(html, js):
    """DER BEFUND VOM 24.09.2026, aus dem Betrieb: "wenn ich auf kanal
    oeffnen druecke sagt er mir ich brauche einen PIN und kann niergends
    einen eintragen".

    Das Feld erscheint nur, wenn pinLaden() vorher gelaufen ist. Die
    Kanal-Ansicht rief es nie auf -- wer nach dem Anmelden direkt dorthin
    ging, sah kein Feld, schickte keine PIN und bekam "Dafuer braucht es
    deine PIN." Geprueft wird deshalb nicht eine Liste von Hand, sondern
    jede Ansicht, in der tatsaechlich ein PIN-Feld steht.
    """
    abschnitte = list(re.finditer(r'<section[^>]*data-ansicht="([^"]+)"',
                                  html))
    ansichten = set()
    for feld in re.finditer(r'id="([\w-]+-pin-zeile)"', html):
        davor = [a for a in abschnitte if a.start() < feld.start()]
        ansichten.add(davor[-1].group(1))
    assert {"ln-wallet", "ln-kanaele", "ln-einrichtung"} <= ansichten

    stelle = js.index("function zeigeAnsicht(")
    wechsel = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    for ansicht in sorted(ansichten):
        anfang = wechsel.index(f'if (name === "{ansicht}")')
        zweig = wechsel[anfang:wechsel.index("\n  }", anfang)]
        assert "pinLaden();" in zweig, (
            f"Ansicht {ansicht} hat ein PIN-Feld, fragt aber nie, ob eine "
            "PIN eingerichtet ist -- das Feld bliebe versteckt")


def test_verlangt_der_server_die_pin_erscheint_das_feld(js):
    """Die zweite Sicherung: ist der Stand in der Oberflaeche veraltet --
    PIN in einem anderen Reiter eingerichtet --, sagt der Server
    "pin_noetig". Dann den Stand neu holen, damit das Feld auftaucht und
    die Meldung nicht vor einem Formular ohne Feld steht."""
    stelle = js.index("function geldfehler(")
    block = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    assert 'd.meldung === "pin_noetig"' in block
    assert "pinLaden();" in block


# ── Haengt sie, oder wartet sie nur? (24.09.2026) ──────────────────────────
#
# Aus dem Betrieb: "das er mir jetzt bei jeder transaktion im wallet direkt
# anzeigt 'gebueren erhoehen!'".

def test_der_knopf_steht_nur_unter_einer_haengenden_ausgabe(js):
    """Die Liste ruft den Knopf nicht mehr selbst auf -- sie fragt die
    Lage, und nur "haengt" (oder "unklar", wenn bitcoind schweigt) fuehrt
    zum Knopf."""
    stelle = js.index("function zeichneBewegungen(")
    liste = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    assert "nachbesserZeile(" not in liste
    assert "zeile.append(warteZeile(b))" in liste

    stelle = js.index("function warteZeile(")
    block = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    schranke = block.index(
        'if (w.lage !== "haengt" && w.lage !== "unklar") return hinweis(')
    assert schranke < block.index("nachbesserZeile(b, satz)")
    assert block.index('hinweis(t("nb_nicht_moeglich")') < block.index(
        "nachbesserZeile(b, satz)")


def test_jede_lage_des_servers_hat_ihren_satz(js):
    """Kaeme vom Server eine Lage, die die Oberflaeche nicht kennt, stuende
    dort ein Schluessel statt eines Satzes. Die Liste wird aus dem Server
    gelesen, nicht von Hand gefuehrt."""
    quelle = (Path(__file__).resolve().parents[1] / "satcortex"
              / "cluster.py").read_text(encoding="utf-8")
    teil = quelle[quelle.index("def wartelage("):]
    lagen = set(re.findall(r'"lage": "(\w+)"', teil))
    lagen |= set(re.findall(r'lage = "(\w+)"', teil))
    assert {"haengt", "reicht", "frisch", "nicht_im_mempool",
            "keine_schaetzung", "unklar"} <= lagen
    stelle = js.index("const WARTE_TEXTE = {")
    tabelle = js[stelle:js.index("};", stelle)]
    for lage in lagen:
        assert f"{lage}: " in tabelle or f'"{lage}"' in tabelle, lage


# ── Umschichten: Grenze vorher, Ergebnis danach (24.09.2026) ───────────────
#
# Aus dem Betrieb: ein Umschichten ueber einen Kanal zu einem LDK-Knoten (der
# nimmt nur 25 % der Kapazitaet gleichzeitig an) -- "keine Antwort", Knopf gesperrt bis zum
# Neuladen, und wie es ausging stand nur im LND-Protokoll.

def _block(js, anfang):
    stelle = js.index(anfang)
    return _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])


def test_die_grenze_wird_vor_dem_versuch_geprueft(js):
    block = _block(js, "async function umschichten(")
    assert "umschichtenGrenze(" in block
    assert block.index("umschichtenGrenze(") < block.index(
        'api("/lightning/umschichten"'), "erst pruefen, dann losschicken"


def test_ohne_antwort_sieht_die_app_selbst_nach(js):
    block = _block(js, "async function umschichten(")
    fang = block[block.index("catch (e)"):]
    assert 'd.meldung === "umschichten_unklar"' in fang
    assert "umschichtenVerfolgen(d.kennung)" in fang
    # Waehrend nachgesehen wird, bleibt der Knopf zu.
    zweig = fang[fang.index('d.meldung === "umschichten_unklar"'):]
    zweig = zweig[:zweig.index("}")]
    assert "wiederFrei = false" in zweig


def test_der_knopf_geht_erst_bei_einem_ergebnis_wieder_auf(js):
    block = _block(js, "async function umschichtenVerfolgen(")
    assert ('api("/lightning/umschichten/abwarten?kennung="' in block
            and "FRIST_WARTEN_MS" in block)
    assert block.count("knopf.disabled = false") == 2
    for zustand in ('d.zustand === "angekommen"', 'd.zustand === "gescheitert"'):
        zweig = block[block.index(zustand):]
        zweig = zweig[:zweig.index("return;")]
        assert "knopf.disabled = false" in zweig, zustand


def test_jeder_grund_von_lnd_hat_einen_satz(js):
    """Die Gruende aus router.swagger.json (v0.21.3-beta), ausser NONE."""
    stelle = js.index("const US_GRUENDE = {")
    tabelle = js[stelle:js.index("};", stelle)]
    for grund in ("FAILURE_REASON_TIMEOUT", "FAILURE_REASON_NO_ROUTE",
                  "FAILURE_REASON_ERROR",
                  "FAILURE_REASON_INCORRECT_PAYMENT_DETAILS",
                  "FAILURE_REASON_INSUFFICIENT_BALANCE",
                  "FAILURE_REASON_CANCELED"):
        assert grund in tabelle, grund


# ── Die Kettenzeile im Lightning-Kasten (24.09.2026) ───────────────────────
#
# Aus dem Betrieb: "bei lightning rechts im kasten steht immer noch kann
# eingerichtet werden .. stimmt ja nicht ist ja eingerichtet und laeuft sogar".

def _kettentext_ausfuehren(js, faelle):
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node nicht vorhanden -- die CI prueft es trotzdem")
    stelle = js.index("function kettenText(")
    quelle = js[stelle:js.index("\n}\n", stelle) + 2]
    programm = (
        "const t = (k, w) => w && w.h ? k + '@' + w.h : k;\n"
        "const zahl = (n) => String(n);\n" + quelle +
        "\nconst faelle = " + json.dumps(faelle) + ";\n"
        "console.log(JSON.stringify(faelle.map(kettenText)));\n")
    lauf = subprocess.run([node, "-e", programm], capture_output=True,
                          text=True)
    assert lauf.returncode == 0, lauf.stderr
    return json.loads(lauf.stdout)


def test_mit_wallet_heisst_es_nicht_mehr_kann_eingerichtet_werden(js):
    """Dieselbe Fehlerklasse wie am 09.09.2026 beim Satz darunter: die Zeile
    kannte nur die Kette, nie die Wallet."""
    fertig = {"kette_bereit": True, "dienst": {"zustand": "freigegeben"}}
    ergebnis = _kettentext_ausfuehren(js, [
        {**fertig, "knoten": {"stand": "bereit"}},
        {**fertig, "knoten": {"stand": "gesperrt"}},
        {**fertig, "knoten": {"stand": "startet"}},
        {**fertig, "knoten": {"stand": "keine_wallet"}},
        {"kette_bereit": True, "dienst": {"zustand": "unkonfiguriert"},
         "knoten": {"stand": "aus"}},
        {**fertig, "knoten": {"stand": "aus"}},
        {"kette_bereit": False, "hoehe": 900000,
         "knoten": {"stand": "keine_wallet"}},
    ])
    assert ergebnis == [
        "ln_k_vollstaendig", "ln_k_vollstaendig", "ln_k_vollstaendig",
        "ln_k_bereit", "ln_k_bereit",
        # LND antwortet nicht: ob es eine Wallet gibt, weiss hier niemand --
        # dann auch nichts behaupten.
        "ln_k_vollstaendig",
        "ln_k_sync@900000"]


def test_beide_kaesten_nehmen_dieselbe_kettenzeile(js):
    """Die Uebersicht und die Wallet-Kopfzeile -- zwei Stellen, die bisher
    denselben Ausdruck je fuer sich hatten."""
    for name in ("function zeichneLightning(", "function zeichneLightningKurz("):
        stelle = js.index(name)
        block = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
        assert "kettenText(d)" in block, name
        assert 't("ln_k_bereit")' not in block, name


# ── Kanaele im Aufbau und im Abbau (24.09.2026) ────────────────────────────
#
# Aus dem Betrieb: "ich habe ja jetzt einen kanal geoeffnet zu den anderen
# partner B ... nur warum seh ich das nur in wallet und nicht unter kanal ?"

def test_die_kanalansicht_zeigt_auch_die_im_aufbau(js):
    stelle = js.index("async function ladeLightningKanaele(")
    laden = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    assert "zeichneLnKanaele(d.kanaele || [], d.ausstehend || [])" in laden

    stelle = js.index("function zeichneLnKanaele(")
    block = _ohne_js_kommentare(js[stelle:js.index("\n}\n", stelle)])
    # Erst die ausstehenden zeichnen, DANN bei leerer Liste aussteigen --
    # sonst verschwaende ein Kanal im Aufbau hinter dem fruehen return.
    assert block.index("ausstehendZeile(k)") < block.index("if (!liste.length)")
    # Und "noch keine Kanaele" nur, wenn auch keiner entsteht.
    leer = block[block.index("if (!liste.length)"):]
    assert leer.index("(ausstehend || []).length") < leer.index(
        't("lk_keine_kanaele")')


def test_jeder_stand_aus_lnd_hat_seine_darstellung(js):
    """Die Staende werden aus dem Server gelesen, nicht von Hand gefuehrt."""
    quelle = (Path(__file__).resolve().parents[1] / "satcortex"
              / "lnd.py").read_text(encoding="utf-8")
    staende = set(re.findall(r'_ausstehend_eintrag\("(\w+)"', quelle))
    assert staende == {"oeffnet", "schliesst", "zwangsschluss"}
    stelle = js.index("function ausstehendZeile(")
    block = js[stelle:js.index("\n}\n", stelle)]
    # Der dritte ist der else-Zweig; kaeme ein vierter dazu, fiele er hier
    # als Zwangsschluss durch -- deshalb die genaue Menge oben.
    assert 'k.stand === "oeffnet"' in block
    assert 'k.stand === "schliesst"' in block


# ── Senden an der Oberflaeche ──────────────────────────────────────────────
#
# Die Bedingung des Betreibers vom 30.08.2026: "ich werde nix dahin ueberweisen solange
# ich es nicht zurueck schicken kann".
#
# Der unwiderrufliche Handgriff dieser Anwendung. Die Tests hier pruefen
# weniger, dass er geht, als dass er nicht AUS VERSEHEN geht.

def test_senden_steht_unter_wallet(html):
    """Beim Geld, nicht bei der Einrichtung -- so wie das Einzahlen."""
    anfang = html.index('<section data-ansicht="ln-wallet"')
    teil = html[anfang:html.index("</section>", anfang)]
    assert 'id="w-senden"' in teil
    assert teil.index('id="w-einzahlen"') < teil.index('id="w-senden"'), (
        "erst hinein, dann hinaus -- die haeufigere Handlung zuerst")


def test_der_sendeknopf_faengt_gesperrt_an(html, js):
    """Zwei Schritte, und der erste ist nicht ueberspringbar: erst "was
    kostet das", dann "jetzt senden". Die Schaetzung laeuft an der
    wirklichen Wallet und prueft die Adresse gleich mit."""
    assert 'id="sd-senden" disabled' in html
    stelle = js.index("async function sendenSchaetzen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "SD_FREI = true" in block
    assert '$("#sd-senden").disabled = false' in block


def test_jede_aenderung_nimmt_die_freigabe_zurueck(js):
    """Sonst schaetzte man das eine und schickte das andere."""
    assert "function sendenSperren(" in js
    stelle = js.index("for (const feld of sendenFelder())")
    block = js[stelle:js.index("\n  }\n", stelle)]
    assert 'feld.addEventListener("input", sendenSperren)' in block
    assert 'feld.addEventListener("change", sendenSperren)' in block


def test_ohne_schaetzung_geht_nichts_hinaus(js):
    stelle = js.index("async function sendenAusloesen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "if (!SD_FREI)" in block
    assert 't("sd_erst_schaetzen")' in block


def test_alles_senden_schickt_keinen_betrag_mit(js):
    """Der Server weist beides zusammen ab, und das zu Recht -- was von
    zweien gaelte, waere geraten."""
    stelle = js.index("function sendenLeib(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "betrag: alles ? 0 :" in block


def test_das_senden_fragt_nach_der_pin(html, js):
    assert 'id="sd-pin-zeile"' in html
    stelle = js.index("async function sendenAusloesen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert '...mitPin("#sd-pin")' in block
    assert '$("#sd-pin").value = "";' in block


def test_die_warnung_sagt_was_bei_einem_zeitlimit_zu_tun_ist(js):
    """Der teuerste Fehler ueberhaupt: die Antwort bleibt aus, jemand
    drueckt noch einmal -- und schickt dieselbe Zahlung zweimal."""
    anfang = js.index('    sd_warnung: "')
    satz = js[anfang:js.index('",\n', anfang)]
    assert "NICHT noch einmal" in satz
    assert "zurückholen" in satz


def test_nach_dem_senden_stehen_die_felder_leer(js):
    """Damit niemand zweimal drueckt und dabei glaubt, der erste Druck habe
    nicht gezaehlt."""
    stelle = js.index("async function sendenAusloesen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    for feld in ('$("#sd-adresse").value = "";', '$("#sd-betrag").value = "";'):
        assert feld in block, feld
    assert "SD_FREI = false" in block


# ── Uebersetzbare Attribute (10.09.2026) ───────────────────────────────────
#
# Der Betreiber: "bemueh dich in dieser zeit bitte um eine saubere uebersetzung in
# allen kategorien und moeglichen menuefenstern".
#
# Dabei kam heraus: aria-label stand in beiden Sprachen fest verdrahtet da.
# Ein Vorleser las einem englischen Nutzer "Abschnitte" vor und einem
# deutschen "Language" -- Texte, die niemand SIEHT und jeder HOERT, der auf
# einen Vorleser angewiesen ist.

def test_die_oberflaeche_kann_auch_attribute_uebersetzen(js):
    stelle = js.index("function applyI18n(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert '$$("[data-i18n-attr]")' in block
    assert "el.setAttribute(attr.trim(), t(schluessel.trim()))" in block


def test_die_vorleser_beschriftungen_gehen_durch_die_uebersetzung(html):
    """Beide Stellen, an denen es welche gibt."""
    assert 'data-i18n-attr="aria-label=nav_abschnitte"' in html
    assert 'data-i18n-attr="aria-label=lang_wahl"' in html
    # Und die Sprachumschalter gibt es dreimal -- Anmeldung, Assistent,
    # laufende Oberflaeche. Alle drei muessen es haben.
    assert html.count('data-i18n-attr="aria-label=lang_wahl"') == 3


def test_kein_sichtbarer_text_ohne_uebersetzung(html):
    """Der Rundumschlag: jedes Element mit eigenem Text muss entweder
    uebersetzt sein oder ein Eigenname.

    Die Ausnahmen stehen namentlich da, damit eine NEUE Stelle auffaellt
    statt in der Liste unterzugehen."""
    import re
    EIGENNAMEN = {"Satoshi", "Cortex", "SatoshiCortex", "Bitcoin", "Lightning"}
    ohne = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    ohne = re.sub(r"<(script|style)\b.*?</\1>", "", ohne, flags=re.S | re.I)
    uebrig = []
    for treffer in re.finditer(r"<(\w+)([^>]*)>([^<]+)", ohne):
        tag, attribute, text = treffer.group(1), treffer.group(2), \
            treffer.group(3).strip()
        if not text or tag == "title" or "data-i18n" in attribute:
            continue
        if not re.search(r"[A-Za-zÄÖÜäöü]{3}", text):
            continue
        if text in EIGENNAMEN:
            continue
        uebrig.append(f"<{tag}> {text!r}")
    assert not uebrig, "fest eingebauter Text ohne Uebersetzung: " + \
        ", ".join(uebrig)


# ── Der Knopf, der eine Minute lang schwieg (11.09.2026) ───────────────────

def test_nach_dem_sperren_wird_gewartet_und_nachgesehen(js):
    """Der Betreiber: "da drueck ich drauf passiert nix". Der einzige Takt dieser
    Oberflaeche frischt die Uebersicht auf, nicht die Wallet-Ansicht -- der
    Kasten blieb also stehen, wie er war, und das Loeschformular kam nie."""
    stelle = js.index("async function walletSperren(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "await warteBisGesperrt(meldungId)" in block

    warte = js[js.index("async function warteBisGesperrt("):]
    warte = warte[:warte.index("\n}\n")]
    assert 'api("/lightning")' in warte
    assert 'stand === "gesperrt"' in warte
    # Und danach beide Kaesten neu zeichnen: das Loeschformular haengt daran
    # genauso wie die Wahl des Entsperrwegs.
    assert "await ladeWallet()" in warte
    assert "await entsperrwegLaden()" in warte


def test_die_rueckmeldung_steht_beim_knopf_und_ist_sichtbar(html, js):
    """Aus dem Betrieb, 11.09.2026, zum zweiten Mal: "also hier passiert nix wenn
    ich auf wallet sperren druecke".

    Sie stand in #tg-meldung -- der LETZTEN Zeile des Kastens, hinter dem
    (versteckten) Loeschformular, als graue Kleinschrift. Wer den Knopf
    drueckt, sieht dorthin nicht. Ein Vorgang, der bis zu neunzig Sekunden
    dauert, muss dort melden, wo geklickt wurde."""
    anfang = html.index('id="tg-sperren-block"')
    block = html[anfang:html.index("</div>", html.index('id="tg-sperr-meldung"'))]
    assert 'id="tg-sperren"' in block
    assert 'id="tg-sperr-meldung"' in block, "die Meldung gehoert in denselben Block"
    assert block.index('id="tg-sperren"') < block.index('id="tg-sperr-meldung"')
    # Ein Kasten, keine graue Kleinschrift.
    assert 'class="note hidden" id="tg-sperr-meldung"' in html

    # Und er muss auch wirklich sichtbar gemacht werden -- sonst bleibt er
    # versteckt und der Knopf schweigt wieder.
    stelle = js.index("async function walletSperren(")
    ablauf = js[stelle:js.index("\n}\n", stelle)]
    assert 'meldung.classList.remove("hidden")' in ablauf
    assert '"#tg-sperr-meldung"' in ablauf


def test_das_warten_hat_ein_ende_und_sagt_es(js):
    """Ein Balken, der ewig laeuft, ist so schlecht wie gar keiner."""
    warte = js[js.index("async function warteBisGesperrt("):]
    warte = warte[:warte.index("\n}\n")]
    assert 't("tg_sperren_haengt")' in warte
    # Und waehrenddessen zaehlt es mit -- eine Anzeige, die sich nicht
    # ruehrt, sieht aus wie eine haengende.
    assert 't("tg_sperren_laeuft", { rest: uebrig })' in warte


# ── Der Klick, der ein Ereignis statt eines Selektors bekam (11.09.2026) ────
#
# Der Betreiber: "also hier passiert nix wenn ich auf wallet sperren druecke".
#
# Und er hatte wortwoertlich recht: es passierte NICHTS. Der Zuhoerer hing
# direkt an der Funktion --
#
#     $("#tg-sperren").addEventListener("click", walletSperren);
#
# -- und walletSperren hatte seit dem Tag zuvor Parameter. Ein Zuhoerer
# bekommt das Klick-Ereignis als erstes Argument, also lief die erste Zeile
# als $(ereignis). document.querySelector("[object PointerEvent]") wirft
# einen SyntaxError, und der Knopf tat gar nichts -- ohne ein Wort, ohne eine
# Zeile im Protokoll.
#
# Die Falle ist in diesem Projekt aktenkundig: bei einzahladresseHolen steht
# seit Tagen der Kommentar "`neu` MUSS ausdruecklich uebergeben werden".
# Genau deshalb steht hier jetzt eine Pruefung statt eines Kommentars.

def test_kein_zuhoerer_bekommt_versehentlich_das_ereignis(js):
    """Eine benannte Funktion darf nur dann direkt als Zuhoerer haengen,
    wenn ihr erster Parameter das EREIGNIS ist. Alles andere ist die Falle:
    der Aufrufer glaubt, seine Vorgabewerte gelten -- und bekommt
    stattdessen einen PointerEvent."""
    import re
    EREIGNISNAMEN = {"e", "ev", "event", "ereignis"}

    parameter = {}
    for treffer in re.finditer(
            r"\b(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)", js):
        parameter[treffer.group(1)] = [
            p.strip() for p in treffer.group(2).split(",") if p.strip()]

    schlimm = []
    for treffer in re.finditer(
            r'addEventListener\(\s*"([a-z]+)"\s*,\s*([A-Za-z0-9_$]+)\s*[,)]',
            js):
        name = treffer.group(2)
        p = parameter.get(name)
        if not p:
            continue                      # ohne Parameter ist alles gut
        erster = p[0].split("=")[0].strip()
        if erster not in EREIGNISNAMEN:
            schlimm.append(f'{treffer.group(1)} -> {name}({", ".join(p)})')

    assert not schlimm, (
        "Diese Zuhoerer bekommen das Klick-Ereignis als erstes Argument, "
        "statt ihrer Vorgabewerte -- haeng sie in eine Pfeilfunktion: "
        + "; ".join(schlimm))


# ── Die Seed-Passphrase, die niemand gesetzt hat (11.09.2026) ──────────────
#
# Der Betreiber: "er sagt er kann mit der seed kein wallet wieder herstellen die
# pruefsummer stummt nicht .. bin mir aber zu 100% sicher das dass stimmt!"
#
# Das Feld ist ein type="password" in einem zugeklappten Abschnitt, den fast
# niemand aufmacht -- und genau so etwas fuellen Browser und
# Passwortverwaltungen gern von allein aus; Safari haelt sich nicht an
# autocomplete="off". Der Nutzer sieht davon nichts, LND bekommt eine
# Passphrase, die er nie gesetzt hat, und lehnt den richtigen Seed ab.

def test_eine_zugeklappte_passphrase_zaehlt_nicht(html, js):
    assert 'id="wh-pass-block"' in html
    stelle = js.index("function whPassphrase(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "block.open" in block, (
        "nur ein absichtlich aufgeklappter Abschnitt darf zaehlen")
    assert 'passphrase: whPassphrase()' in js


def test_das_passphrasenfeld_wehrt_sich_gegen_autoausfuellen(html):
    """autocomplete="off" allein genuegt nicht -- die grossen
    Passwortverwaltungen haben eigene Kennungen dafuer."""
    anfang = html.index('id="wh-pass-block"')
    block = html[anfang:html.index("</details>", anfang)]
    assert 'autocomplete="new-password"' in block
    assert "data-1p-ignore" in block
    assert 'data-lpignore="true"' in block


def test_die_meldung_zum_abgelehnten_seed_raet_nicht_mehr(js):
    """Sie behauptete in jedem Fall, der Zettel sei falsch. Jetzt traegt sie
    LNDs eigenen Wortlaut und unterscheidet die beiden Faelle."""
    anfang = js.index('    seed_nicht_angenommen: "')
    satz = js[anfang:js.index('",\n', anfang)]
    assert "{einzelheit}" in satz
    assert "Passphrase" in satz, "der zweite Fall muss benannt sein"


# ── Die Wortliste (11.09.2026) ─────────────────────────────────────────────
#
# Der Betreiber brauchte eine Stunde und einen Blick ins LND-Protokoll fuer diese
# Zeile:
#
#     word mopth isn't a part of default word list (index=7)
#
# Gemeint war "month" -- das EINZIGE Wort der Liste, das einen Buchstaben
# davon entfernt liegt. Er hatte recht: sein Zettel stimmte, das p war ein n.
#
# LND rechnet die Pruefsumme erst, wenn alle vierundzwanzig Woerter bekannt
# sind; ein vertipptes scheitert davor. Genau diese Frage stellt die
# Oberflaeche jetzt selbst -- am Feld, waehrend man tippt.

@pytest.fixture(scope="module")
def bip39():
    return (WEB / "bip39.js").read_text(encoding="utf-8")


def test_die_wortliste_ist_vollstaendig_und_echt(bip39):
    """2048 Woerter, sortiert, eindeutig, klein. Eine unvollstaendige Liste
    waere schlimmer als keine: sie wuerde richtige Woerter anmeckern."""
    import re
    treffer = re.search(r"const BIP39 = `\n(.*?)\n`", bip39, re.S)
    assert treffer, "die Liste steht nicht mehr da, wo sie stand"
    woerter = treffer.group(1).split()
    assert len(woerter) == 2048
    assert len(set(woerter)) == 2048
    assert woerter == sorted(woerter)
    assert all(w.isascii() and w.islower() and w.isalpha() for w in woerter)
    assert woerter[0] == "abandon" and woerter[-1] == "zoo"
    assert "month" in woerter and "mopth" not in woerter
    # Und die Herkunft gehoert dokumentiert, samt Pruefsumme.
    assert "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda" \
        in bip39


def test_die_vorlage_laedt_die_liste_vor_der_anwendung(html):
    assert '<script src="bip39.js"></script>' in html
    assert html.index('src="bip39.js"') < html.index('src="app.js"'), \
        "app.js braucht die Liste beim Bauen der Felder"


def test_die_felder_pruefen_gegen_die_liste(html, js):
    assert 'id="bip39-liste"' in html
    assert 'id="wh-wortfehler"' in html
    assert 'feld.setAttribute("list", "bip39-liste")' in js
    # Geprueft wird beim VERLASSEN des Feldes -- waehrend man "month" tippt,
    # ist "mont" nun einmal kein Wort der Liste.
    assert 'feld.addEventListener("blur"' in js


def test_ohne_gueltige_woerter_geht_nichts_hinaus(js):
    """LND wuerde dasselbe sagen, aber erst nach einem Rundlauf und nur mit
    EINEM Wort. Hier stehen gleich alle -- mit Vorschlag."""
    stelle = js.index("async function walletWiederherstellen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "const schlecht = whUnbekannteWoerter()" in block
    assert "if (schlecht.length)" in block
    assert 't("wh_erst_woerter")' in block
    # Und zwar VOR dem Absenden.
    assert block.index("whUnbekannteWoerter()") < block.index('api("/lightning/wiederherstellen"')


def test_ein_eindeutiger_vorschlag_wird_genannt(js):
    """Bei einem Tippfehler gibt es fast immer genau ein Wort, das einen
    Buchstaben entfernt liegt. Es zu verschweigen waere die halbe Auskunft."""
    assert "function bip39Nahe(" in js
    anfang = js.index('    wh_wort_vielleicht: "')
    satz = js[anfang:js.index('",\n', anfang)]
    assert "{nahe}" in satz and "{nr}" in satz


def test_ohne_knoten_bleibt_der_adresskasten_nicht_stumm(js, html):
    """Aus dem Betrieb, 11.09.2026: "aber es wird mir noch keine verbindungs
    adresse angezeigt". Fiel getinfo weg, wurde zeichneEigeneAdresse gar
    nicht erst gerufen -- der Kasten blieb leer, ohne ein Wort dazu. Eine
    leere Flaeche ohne Grund ist die schlechteste aller Auskuenfte."""
    stelle = js.index("async function ladeLightningKanaele(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "beschaeftigt: true" in block, (
        "ohne getinfo muss der Kasten trotzdem gezeichnet werden")
    assert "veraltet: !!d.knoten_veraltet" in block

    # Und "beschaeftigt" schlaegt jeden anderen Grund: solange getinfo
    # schweigt, waere "trag deine Adresse ein" ein falscher Rat.
    stelle = js.index("function zeichneEigeneAdresse(")
    zeichnen = js[stelle:js.index("\n}\n", stelle)]
    assert 'k.beschaeftigt ? "lgi_keine_beschaeftigt"' in zeichnen
    assert 'id="lgi-veraltet"' in html


def test_der_kennungswechsel_steht_beim_knoten(html, js):
    """Aus dem Betrieb, 11.09.2026: "keine ahnung habe mir die kennung nicht
    vorher angesehen". Dass er sie sich von Hand notieren sollte, war unser
    Versaeumnis -- die Anwendung kennt sie ohnehin."""
    anfang = html.index('<section data-ansicht="ln-knoten"')
    teil = html[anfang:html.index("</section>", anfang)]
    assert 'id="lgi-kennung-anders"' in teil
    assert 'id="lgi-kennung-ok"' in teil, (
        "ein Hinweis, den man nicht wegbekommt, wird nicht mehr gelesen")
    assert "function zeichneKennungswechsel(" in js
    assert "async function kennungUebernehmen(" in js


def test_der_hinweis_nennt_beide_kennungen(js):
    """Eine Warnung ohne die Zahlen waere keine: man kann sie nicht
    nachpruefen."""
    anfang = js.index('    lgi_kennung_anders: "')
    satz = js[anfang:js.index('",\n', anfang)]
    assert "{vorher}" in satz and "{jetzt}" in satz
    # Und beide Faelle muessen benannt sein -- nach einer NEUEN Wallet ist
    # eine andere Kennung richtig.
    assert "Wiederherstellung" in satz and "NEU" in satz


# ── Teuer oder guenstig? (11.09.2026) ──────────────────────────────────────
#
# Der Betreiber: "waere das nicht gut wenn er uns sagen wuerde ob das momentan
# teuer oder guenstig ist im durchschnitt .. ?? das mann ne orientierung
# hat".
#
# Eine Einordnung GAB es -- sie mass nur das Falsche: die Gebuehr am eigenen
# On-Chain-Guthaben. Wer noch keins hat, sah gar nichts. Also fiel die
# Orientierung genau dann weg, wenn man seinen ersten Kanal plant.

def test_die_einordnung_steht_vor_dem_guthaben(js):
    """Die Reihenfolge IST der Fix: die alte Einordnung stieg mit einem
    return aus, sobald kein Guthaben da war. Alles, was auch ohne Guthaben
    gilt, muss davor stehen."""
    stelle = js.index("function zeichneKanalkosten(")
    block = js[stelle:js.index("\n}\n", stelle)]
    lage = block.index('$("#kk-lage")')
    aussteigen = block.index("anteil_prozent === undefined")
    assert lage < aussteigen, "die Gebuehrenlage darf nicht am Guthaben haengen"


def test_beide_stellen_sagen_dasselbe(js):
    """Die Einordnung steht an zwei Stellen -- unter "Wallet" neben den
    Gebuehren und im Rechner neben der Kanalgroesse. Aus EINER Funktion:
    zweimal derselbe Satz aus zwei Quellen waere der Anfang zweier
    verschiedener Wahrheiten."""
    assert js.count("function lagehinweis(") == 1
    assert js.count("lagehinweis(k)") >= 2


def test_die_einordnung_nennt_die_spanne(js):
    """"Guenstig" allein ist eine Behauptung. Erst die Spanne der Woche
    macht daraus etwas, das man selbst nachvollziehen kann."""
    for sprache in ("kk_lage_guenstig", "kk_lage_normal", "kk_lage_teuer"):
        assert sprache in js
    assert "{unten}" in js and "{oben}" in js and "{mitte}" in js


# ── Was fuer einen Kanal einzuzahlen ist ───────────────────────────────────
#
# Der Betreiber: "ok dein knoten soll die menge an sat haben dann musst du aber das
# plus exit und gebueren an sat einzahlen weisst du was ich meine?"

def test_der_kanalrechner_steht_im_rechner_reiter(html, js):
    """Der Betreiber: "wir haben ja schon ein rechner reiter kann das da nicht mit
    rein?" -- und dort gehoert er hin, weil dort der KURS liegt. "160.339
    sat" sagt einem Menschen nichts, der Betrag in Euro sagt alles."""
    # <section, nicht der Navigationsknopf -- der traegt dasselbe Merkmal.
    anfang = html.index('<section data-ansicht="rechner"')
    ende = html.index("<section", anfang + 10)
    reiter = html[anfang:ende]
    assert 'id="kkp-groesse"' in reiter, "der Rechner gehoert in den Reiter"
    assert 'id="kkp-zahlen"' in reiter
    # Und er wird beim Wechsel in den Reiter auch geladen.
    assert 'if (name === "rechner")' in js and "ladeKanalrechner()" in js


def test_der_kanalrechner_zeigt_auch_die_waehrung(js):
    """Der ganze Grund fuer den Umzug. Ohne den Betrag daneben waere der
    Rechner an dieser Stelle nur verschoben, nicht besser."""
    stelle = js.index("function kanalplanRechnen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "satsUndFiat(" in block
    assert "sats(n)" in js[js.index("function satsUndFiat("):]


def test_ohne_schaetzung_sagt_der_rechner_warum(js, html):
    """Eine Tabelle voller Nullen waere schlechter als ein Satz, der sagt,
    warum gerade nichts dasteht."""
    assert 'id="kkp-ohne"' in html
    stelle = js.index("function zeichneKanalplan(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "kkp-ohne" in block


def test_der_rechner_haengt_seinen_zuhoerer_nur_einmal(js):
    """zeichneKanalplan laeuft bei JEDER Auffrischung. Ohne die Sperre
    haengen nach einer Stunde hundert Zuhoerer an einem Feld."""
    stelle = js.index("function zeichneKanalplan(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "dataset.verdrahtet" in block
    # Und als Pfeilfunktion -- siehe die Falle vom selben Tag weiter oben.
    assert 'addEventListener("input", () =>' in block


def test_ohne_ruecklage_wird_keine_null_gezeigt(js):
    """Eine Null hiesse "du brauchst nichts zurueckzulegen". Solange LND
    nicht laeuft, faellt die Zeile weg statt zu luegen."""
    stelle = js.index("function kanalplanRechnen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "ruecklage !== undefined && ruecklage !== null" in block


def test_der_rechner_trennt_einzahlen_von_nutzbar(js):
    """Die beiden Zahlen, um die es der Betreiber ging: was rein muss, und was
    danach im Kanal wirklich zur Verfuegung steht."""
    assert "kkp_einzahlen" in js and "kkp_nutzbar" in js


# ── Nach dem Wiederanmelden war die Weltkarte weg (12.09.2026) ─────────────
#
# Der Betreiber: "wenn sich die app sitzung abmeldet und ich mich wieder einlogge
# dann laedt die welt karte nicht automatisch ich muss dann erst nach dem
# anmelden die browser seite refreshen".
#
# Die Ursache war eine Unwucht: das AUSBLENDEN steht in zeigeTor() und laeuft
# bei jeder abgelaufenen Sitzung, das EINBLENDEN stand in einem Block, der nur
# EINMAL je Seitenaufruf laeuft ("die Umrisse nur einmal laden"). Nach dem
# Abmelden war die Karte also versteckt, und nichts holte sie wieder hervor.
# Ein Neuladen der Seite setzte die Sperre zurueck -- deshalb half es.

def test_die_karte_wird_bei_jedem_aufruf_wieder_eingeblendet(js):
    stelle = js.index("async function ladeKarte(")
    block = js[stelle:js.index("\n}\n", stelle)]
    einmal = block.index("if (!KARTE_GEHOLT)")
    einblenden = block.index('$("#karte-hintergrund").classList.remove')
    sperre = block.index("KARTE_ABSTAND_MS")
    einmal_ende = block.index("\n  }\n", einmal)
    assert einblenden > einmal_ende, (
        "das Einblenden darf NICHT im Einmal-Block stehen -- genau das war "
        "der Fehler")
    assert einblenden < sperre, (
        "auch ein uebersprungener Abruf muss die Karte wieder zeigen")


def test_wer_ausblendet_muss_auch_einblenden(js):
    """Die Unwucht als solche festhalten: beides muss es geben."""
    assert js.count('$("#karte-hintergrund").classList.add("hidden")') >= 1
    assert js.count('$("#karte-hintergrund").classList.remove("hidden")') >= 1


def test_nach_dem_wiederanmelden_wird_die_ansicht_neu_aufgebaut(js):
    """Sonst kommt man auf eine Seite mit zwoelf Stunden alten Zahlen
    zurueck: die Lader ueberspringen den Abruf, solange ihre Daten "frisch"
    sind -- und frisch heisst dort nur "juenger als der Abstand"."""
    stelle = js.index("async function nachAnmeldung(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "KARTE_STAND = LN_STAND = BEITRAG_STAND = AUSW_STAND = 0" in block
    assert "zeigeAnsicht(ANSICHT)" in block, (
        "die Ansicht, auf der der Nutzer steht, muss auch neu gezeichnet "
        "werden -- nicht nur die Uebersicht")


# ── Kanal oeffnen und zahlen: erst ansehen, dann freigeben (12.09.2026) ────
#
# Dieselbe Reihenfolge wie beim On-Chain-Senden, und aus demselben Grund: der
# Knopf, der Geld aus der Hand gibt, geht NUR nach einem Blick darauf auf.

@pytest.mark.parametrize("knopf", ["zl-zahlen", "ko-oeffnen"])
def test_der_gefaehrliche_knopf_beginnt_gesperrt(html, knopf):
    stelle = html.index(f'id="{knopf}"')
    umfeld = html[stelle - 160:stelle + 160]
    assert "disabled" in umfeld, (
        f"{knopf} muss gesperrt beginnen -- erst ansehen, dann freigeben")
    assert "gefahr" in umfeld, "und als gefaehrlich erkennbar sein"


@pytest.mark.parametrize("sperre,frei", [("zahlenSperren", "ZL_FREI"),
                                         ("kanalSperren", "KO_FREI")])
def test_jede_aenderung_nimmt_auch_hier_die_freigabe_zurueck(js, sperre, frei):
    """Sonst liest man das eine und bezahlt das andere. Denselben Griff gibt
    es beim On-Chain-Senden schon -- er gilt hier genauso."""
    stelle = js.index(f"function {sperre}(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert f"{frei} = false" in block
    assert "disabled = true" in block


def test_die_freigabe_faellt_nur_nach_dem_ansehen(js):
    """ZL_FREI und KO_FREI duerfen NUR in der Vorschau gesetzt werden --
    nicht irgendwo sonst, wo jemand sie versehentlich oeffnet."""
    import re
    for name, erlaubt in (("ZL_FREI", "rechnungLesen"),
                          ("KO_FREI", "kanalPruefen")):
        setzt = [m.start() for m in re.finditer(rf"\b{name} = true", js)]
        assert len(setzt) == 1, f"{name} wird an mehreren Stellen geoeffnet"
        anfang = js.index(f"async function {erlaubt}(")
        assert anfang < setzt[0] < js.index("\n}\n", anfang), (
            f"{name} gehoert in {erlaubt}, sonst nirgends")


def test_eine_laufende_zahlung_sagt_dass_sie_laeuft(js):
    """Eine Lightning-Zahlung kann eine Minute unterwegs sein. Ohne ein Wort
    dazu sieht das aus, als haette der Knopf nichts getan -- und der naechste
    Griff waere, ihn noch einmal zu druecken."""
    stelle = js.index("async function rechnungZahlen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert 't("zl_unterwegs")' in block


def test_der_kanal_wird_nur_freigegeben_wenn_das_guthaben_reicht(js):
    """LND wuerde sonst ablehnen -- aber erst, nachdem der Nutzer den
    gefaehrlichen Knopf gedrueckt hat."""
    stelle = js.index("async function kanalPruefen(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "if (d.reicht)" in block
    assert block.index("if (d.reicht)") < block.index("KO_FREI = true")


# ── Umschichten (12.09.2026) ───────────────────────────────────────────────
#
# Der Betreiber: "kann ich dann mehre kanäle balancen??"

def test_umschichten_erscheint_erst_ab_zwei_kanaelen(js):
    """Mit einem Kanal gibt es nichts umzuschichten. Ein Kasten, der nie
    geht, ist schlechter als keiner."""
    stelle = js.index("function fuelleUmschichten(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "brauchbar.length < 2" in block


def test_die_auswahl_kommt_aus_der_kanalliste(js):
    """Niemand soll eine Kanalnummer abtippen muessen."""
    stelle = js.index("function fuelleUmschichten(")
    block = js[stelle:js.index("\n}\n", stelle)]
    assert "k.nummer" in block and "k.kennung" in block


def test_selbstzahlung_ist_nur_beim_umschichten_an(js, html):
    """Beim Bezahlen einer fremden Rechnung ist Selbstzahlung ein Unfall,
    beim Umschichten der Zweck. Zwei Vorgaenge, zwei Knoepfe."""
    assert 'id="zl-zahlen"' in html and 'id="us-los"' in html
    # Und im Backend haengt es an zwei verschiedenen Funktionen.
    from pathlib import Path
    quelle = Path(__file__).resolve().parents[1] / "satcortex" / "lnd.py"
    text = quelle.read_text(encoding="utf-8")
    assert '"allow_self_payment": False' in text
    assert '"allow_self_payment": True' in text


def test_der_eigene_turm_verspricht_keine_gebuehren(js):
    """Die Frage aus dem Betrieb war, ob der Turm Gebuehren einbringt. Tut er nicht --
    LND betreibt ihn altruistisch. Das gehoert dort gesagt, wo die Adresse
    steht, sonst entsteht genau diese Erwartung."""
    assert "wt_eigen_fuss" in js
    stelle = js.index("wt_eigen_fuss:")
    text = js[stelle:stelle + 400]
    assert "KEINE Gebühren" in text or "NO fees" in text


def test_kanalpartner_und_verbindungen_heissen_verschieden(js, html):
    """Bis zum 14.09.2026 hiess beides "Gegenstellen": "Verbunden mit 3
    Gegenstellen" zaehlte Leitungen, "Deine Gegenstellen -- mit wem du direkt
    verbunden bist" zeigte Kanalpartner. Die Frage danach war, ob man mit
    einer Verbindung schon einen Kanal hat."""
    import re
    deutsch = js[js.index("const I18N = {"):js.index("\n  en: {")]

    def text(schluessel):
        return re.search(r"\n    " + schluessel + r': "([^"]*)"', deutsch).group(1)

    assert text("lk_gegenstellen") == "Verbindungen"
    assert "Kanalpartner" in text("lg_gegen_titel")
    assert "verbunden" not in text("lg_gegen_d").lower()
    # Dass "Kanal oeffnen" selbst verbindet, muss beim Verbinden dastehen --
    # sonst sieht es aus wie ein Pflichtschritt.
    #
    # Stand bis zum 19.09.2026 in vb_lead, im Kasten unter "Knoten". Genau
    # das war die Schwaeche: der aufklaerende Satz lag in dem Reiter, in dem
    # man gerade NICHT ist. Seit die drei Knoepfe beieinanderstehen, steht er
    # bei ihnen -- und der Test haengt an der Aussage, nicht am alten Ort.
    assert "Kanal öffnen" in text("ko_knoepfe_d")
    assert 'id="lv-liste"' in html


def test_das_diagramm_nennt_sein_alter_und_den_wahren_grund(js):
    """Bis zum 15.09.2026 sah ein altes Diagramm aus wie eins von jetzt, und
    ohne Diagramm hiess es immer "der Mempool fuellt sich erst, wenn die Kette
    steht" -- auch bei laengst stehender Kette."""
    teil = js[js.index("function zeichneDiagramm"):]
    teil = teil[:teil.index("\n}\n")]
    assert "a_dia_alt" in teil and "a_dia_kein_zulauf" in teil


def test_die_adressabfrage_fragt_nur_weiter_solange_sie_laeuft(js, html):
    """Ein Scan dauert Minuten. Weiterfragen, wenn keiner hinsieht oder er
    laengst fertig ist, waere Last ohne Nutzen."""
    teil = js[js.index("async function adresseStandLaden"):]
    teil = teil[:teil.index("\n}\n")]
    assert 'd.laeuft && ANSICHT === "bloecke"' in teil
    assert 'id="a-adresse"' in html and 'id="a-pool-fenster"' in html


# ── Befunde vom 15.09.2026, bei der ersten echten Einzahlung ────────────────

def test_qr_js_wird_vor_der_anwendung_geladen(html):
    assert html.index('src="qr.js"') < html.index('src="app.js"')


def test_ausgebbar_ist_nur_das_bestaetigte_guthaben(js):
    """Senden verlangt min_confs=1. Die Summe mit dem Unbestaetigten liess
    eine frische Einzahlung ausgebbar aussehen."""
    anfang = js.index("function zeichneLnGuthaben")
    teil = js[anfang:anfang + 2000]
    assert '[t("lk_onchain"), g.kette_bestaetigt]' in teil
    assert '[t("lk_onchain"), g.kette_gesamt]' not in teil


def test_die_adressabfrage_kuerzt_die_txid_nicht(js):
    teil = js[js.index("function zeichneAdressstand"):
              js.index("/* ── Bewegungen der On-Chain-Wallet")]
    assert "kurz(a.txid)" not in teil
    assert "txidZeile(a.txid" in teil


def test_die_bewegungen_laufen_nur_bei_offener_wallet(js):
    teil = js[js.index("async function ladeBewegungen"):
              js.index("function zeichneBewegungen")]
    assert 'if (ANSICHT !== "ln-wallet") return;' in teil
    assert "clearTimeout(BEWEGUNGEN_TAKT)" in teil



def test_kleine_betraege_verschwinden_nicht_hinter_btc(js):
    """btc() rundet auf vier Nachkommastellen. In der Bewegungsliste stand
    deshalb "-0.0000 BTC" fuer 2.141 sat -- im Browser gesehen am
    15.09.2026. Einzahlungen und Rueckwege sind am Anfang genau so klein."""
    bewegungen = js[js.index("function zeichneBewegungen"):
                    js.index("function txidZeile")]
    adresse = js[js.index("function zeichneAdressstand"):
                 js.index("/* ── Bewegungen der On-Chain-Wallet")]
    assert "btc(" not in bewegungen
    assert "btc(" not in adresse


def test_der_hinweis_zum_unbestaetigten_steht_unter_den_kennzahlen(html, js):
    anfang = js.index("function zeichneLnGuthaben")
    teil = js[anfang:anfang + 2000]
    assert 'hinweis(t("lk_unterwegs_d")' not in teil
    assert "#ln-guthaben-hinweis" in teil
    assert html.index('id="ln-guthaben-inhalt"') < html.index('id="ln-guthaben-hinweis"')


# ── Empfangen ueber Lightning (16.09.2026) ─────────────────────────────────

def test_die_wallet_hat_eine_flaeche_zum_empfangen(html):
    assert 'id="w-empfangen"' in html
    assert 'id="rq-erstellen"' in html
    assert 'id="rq-qr"' in html
    # Vor dem Zahlen-Panel: erst hereinbekommen, dann hinausgeben.
    assert html.index('id="w-empfangen"') < html.index('id="w-zahlen"')


def test_die_rechnung_geht_gross_geschrieben_in_den_qr_code(js):
    """Klein geschrieben faellt sie in den Byte-Modus und passt nicht mehr."""
    teil = js[js.index("async function rechnungErstellen"):
              js.index("async function rechnungKopieren")]
    assert 'd.rechnung.toUpperCase()' in teil


def test_ohne_empfangsraum_sagt_die_flaeche_das(js):
    teil = js[js.index("function zeichneRechnungen"):
              js.index("function dauerKurz")]
    assert 'kanal_drueben' in teil
    assert 't("rq_kein_raum")' in teil


def test_die_upload_meldung_nennt_das_fenster_und_die_restzeit(js):
    """Core rechnet in 24 Stunden (MAX_UPLOAD_TIMEFRAME), nicht im Monat.
    Die Meldung sagte bis zum 16.09.2026 nur "bis zum Ende des Zeitraums"."""
    anfang = js.index("const b = d.budget || {}")
    teil = js[anfang:anfang + 800]
    assert "rest: restzeit" in teil
    zeile = [z for z in js.splitlines()
             if z.strip().startswith("b_budget_erschoepft:")]
    assert zeile, "Text b_budget_erschoepft fehlt"
    assert any("24 Stunden" in z and "{rest}" in z for z in zeile)


# ── Die Uebersicht (16.09.2026) ────────────────────────────────────────────
#
# Der Betreiber: "lass uns mal noch was machen mit der leeren uebersichts seite".
# Waehrend des Erstabgleichs war sie in Ordnung; danach stand dort nur, was
# der Knoten TUT, und nichts davon, was man wissen will.

def test_die_uebersicht_zeigt_kurs_guthaben_und_lightning(html):
    for kennung in ("d-kurs-wert", "d-kurs-wechsel", "d-wallet", "d-ln-kurz"):
        assert f'id="{kennung}"' in html, kennung
    # Vor Teilnahme und Diensten: erst die Zahlen, dann der Betriebszustand.
    assert html.index('id="d-kurs-wert"') < html.index('id="d-chain"')


def test_die_uebersicht_holt_keine_teure_kanalabfrage(js):
    """Die Startseite laedt alle zehn Sekunden. /lightning/kanaele zieht
    getinfo, Kanalliste, Graph und Weiterleitungen mit -- dort gehoert es
    nicht hin."""
    teil = js[js.index("function zeichneLightningKurz"):
              js.index("function dauerKurz")]
    assert "/lightning/kanaele" not in teil
    assert "d.guthaben" in teil


def test_ohne_offene_wallet_steht_der_grund_da(js):
    teil = js[js.index("function zeichneLightningKurz"):
              js.index("function dauerKurz")]
    assert 'd_w_gesperrt' in teil and 'd_w_keine_wallet' in teil
    # Keine erfundenen Nullen, wenn das Guthaben nicht abrufbar ist.
    assert "if (!g) {" in teil


def test_der_kurs_laedt_auch_auf_der_uebersicht(js):
    teil = js[js.index("async function ladeKurs"):
              js.index("function kursText")]
    assert 'ANSICHT !== "uebersicht"' in teil
    assert "zeichneKursKurz(d)" in teil


def test_ohne_kanal_behauptet_die_oberflaeche_keine_sichtbarkeit(js):
    """Bis zum 19.09.2026 stand hier: "Ohne sie ist dein Knoten im Graphen
    eine Sackgasse -- SICHTBAR, aber ohne Weg hindurch."

    Das ist falsch, und zwar nachweisbar. BOLT 7, node_announcement: "if
    node_id is NOT previously known from a channel_announcement message
    [...] SHOULD ignore the message." Ohne angekuendigten Kanal ist ein
    Knoten im Netz kein bekannter Knoten -- seine Namensmeldung wird weder
    angenommen noch weitergereicht. Er ist nicht sichtbar, er ist ABWESEND.

    Gemessen am 18./19.09.2026 an die eigene Knoten: LightningNetwork+
    zeigte "Inactive", "Connection: Unknown" und seinen Schluessel statt
    seines Alias. Und andersherum kannte sein Graph einen seit 2022
    schweigenden Knoten gar nicht mehr.
    """
    import re
    for sprache in ("de", "en"):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    lk_keine_kanaele: "([^"]*)"', block).group(1)
        assert "BOLT 7" in text, sprache
        assert "sichtbar, aber" not in text and "visible, but" not in text, sprache


def test_ein_unbekannter_knoten_ist_kein_ausschluss(js):
    """Hier stand bis zum 19.09.2026: "oder er kuendigt sich gar nicht an --
    dann kaeme ein Kanal OHNEHIN NICHT ZUSTANDE."

    Falsch. Ein Kanal kommt sehr wohl zustande, wenn man die Adresse selbst
    mitbringt -- LND verbindet sich damit direkt, ganz ohne Graphen. Das ist
    buchstaeblich die eigene Lage: sein Knoten steht mangels
    oeffentlichem Kanal nicht im Graphen, und deshalb hat er seinen
    Ring-Partnern auf LightningNetwork+ die .onion in den Swap geschrieben,
    damit sie von Hand anklopfen koennen.

    Der Hinweis muss also den Ausweg nennen, nicht die Tuer zuschlagen.
    """
    import re
    for sprache, knopf in (("de", "Verbinden"), ("en", "Connect")):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    ko_b_unbekannt: "([^"]*)"', block).group(1)
        assert knopf in text, sprache
        assert "ohnehin nicht zustande" not in text, sprache
        assert "not come about anyway" not in text, sprache


def test_das_gegenstellenfeld_verlangt_keine_adresse(html, js):
    """Aus dem Betrieb, 19.09.2026: "warum kann ich mir eigentlich keinen knoten
    mit public key ansehen ... will der immer ne komplette verbindung".

    Er tat es laengst -- die nackte Kennung funktionierte. Nur stand im
    Platzhalter "02abc…@host:9735", also die volle Form, waehrend der
    Beschreibungstext darunter seit dem Umbau sagt, dass die Adresse
    optional ist. Ein Feld darf seiner eigenen Beschriftung nicht
    widersprechen; gelesen wird der Platzhalter.
    """
    import re
    stelle = html.index('id="ko-gegenstelle"')
    feld = html[stelle:stelle + 400]
    platzhalter = re.search(r'placeholder="([^"]*)"', feld).group(1)
    assert "@" not in platzhalter, platzhalter
    # Und die Beschreibung muss weiterhin sagen, dass die Adresse geht.
    for sprache in ("de", "en"):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    ko_gegenstelle_d: "([^"]*)"', block).group(1)
        assert "9735" in text, sprache


def test_der_eigene_wachturm_verschwindet_nicht_wortlos(html, js):
    """Gefunden im Regtest-Durchlauf am 19.09.2026 gegen ein echtes LND.

    LND lieferte fuer den eigenen Turm::

        {"aktiv": true, "kennung": "...", "uris": [],
         "lauscht": ["127.0.0.1:19775"]}

    Der Turm LAEUFT also und bewacht fremde Kanaele -- er hat nur keine
    Adresse nach aussen, weil watchtower.externalip fehlt. Genau das ist die
    Lage bei "gar nicht ankuendigen" ohne .onion.

    Die Oberflaeche haengte den Kasten an der Adresse statt am Turm und
    blendete in dieser Lage ALLES aus: Ueberschrift, Erklaerung, Fussnote.
    Wer gelesen hatte, dass sein Knoten fremde Kanaele bewacht, suchte die
    Adresse zum Weitergeben und fand eine leere Stelle ohne ein Wort dazu.

    Dass der Turm dann wirklich nicht erreichbar ist, stimmt -- und gehoert
    hingeschrieben, nicht verschwiegen. Dieselbe Familie wie die drei
    Befunde vom selben Tag: die Oberflaeche schweigt statt zu erklaeren.
    """
    import re
    # Der Kasten haengt am Turm, nicht an seiner Adresse.
    stelle = js.index("function zeichneEigenenTurm")
    rumpf = js[stelle:stelle + 1200]
    assert 'toggle("hidden", !turm.aktiv)' in rumpf, rumpf[:400]
    assert 'toggle("hidden", !uri)\n}' not in rumpf

    # Und es gibt eine Stelle, an der die Erklaerung landet.
    assert 'id="wt-eigen-ohne"' in html
    assert 'data-i18n="wt_eigen_ohne"' in html

    # In beiden Sprachen, und sie muss den Ausweg nennen -- nicht nur
    # feststellen, dass nichts da ist.
    for sprache, wort in (("de", "9911"), ("en", "9911")):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    wt_eigen_ohne: "([^"]*)"', block).group(1)
        assert wort in text, sprache
        assert len(text) > 120, sprache


def test_die_gebuehrenspanne_wird_nicht_mitte_genannt(js):
    """Der Befund vom 21.09.2026 aus dem Betrieb.

    Angezeigt wurde: "Median 100 ppm · Mitte des Netzes 1-600 ppm". Die
    Rueckfrage kam prompt und war berechtigt: "das kann ja nicht richtig
    sein oder" -- denn wer "Mitte" liest, rechnet (1+600)/2 = 300 und findet
    100 daneben.

    Beides stimmt. 100 ist der MEDIAN (die Haelfte nimmt weniger), die
    Spanne ist das mittlere Viertelpaar. Weil im Lightning-Netz sehr viele
    Richtungen bei null oder einem ppm stehen, liegt der Median nicht in
    der Mitte der Spanne.

    Die Zahl war also nie falsch -- ihre Beschriftung war es. Der Test haelt
    fest, dass die Spanne sagt, WAS in ihr liegt.
    """
    import re
    for sprache, wort in (("de", "50 %"), ("en", "50 %")):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    gb_netz_zahlen: "([^"]*)"', block).group(1)
        assert "Mitte des Netzes" not in text, sprache
        assert "Middle of the network" not in text, sprache
        # Und der Median muss als solcher benannt sein, nicht als Schnitt.
        assert "Median" in text, sprache
        assert "urchschnitt" not in text and "verage" not in text, sprache
        # Die Spanne steht seit dem 21.09.2026 in einem eigenen Text -- sie
        # erscheint nur noch, wo keine Verteilung vorliegt. Auch dort muss
        # sie sagen, WAS in ihr liegt.
        spanne = re.search(r'\n    gb_netz_spanne: "([^"]*)"', block).group(1)
        assert wort in spanne, (sprache, spanne)


# Hier stand bis zum 21.09.2026 test_zur_schiefen_verteilung_gibt_es_eine_
# erklaerung -- die Wache ueber den Absatz, der die Schiefe in Worten
# erklaerte. Der Absatz ist weg, die Verteilungsleiste zeigt dieselbe Schiefe
# als Bild. Was davon bleibt, steht weiter unten unter
# test_der_erklaerabsatz_ist_weg.


def test_die_uebersicht_holt_den_kurs_auch_selbst(js):
    """Der Befund vom 21.09.2026 aus dem Betrieb: "der kurs von btc laedt
    gefuehlt garnicht auf der uebersichts seite".

    Er lud dort nie. Der Kasten auf der Uebersicht (#d-kurs-wert) wird von
    zeichneKursKurz() gefuellt, und die wird ausschliesslich aus ladeKurs()
    gerufen. ladeKurs() LAESST die Uebersicht ausdruecklich zu -- sie steht
    in seiner Abbruchbedingung --, aber gerufen wurde es nur beim Wechsel
    nach News oder Rechner. Wer neu lud und auf der Uebersicht blieb, sah
    dauerhaft einen Gedankenstrich.

    Ein halb gemachter Umbau: die Bedingung wurde erweitert, der Aufruf
    vergessen. Der Test haelt beide Haelften zusammen.
    """
    anf = js.index("async function zeigeUebersicht()")
    ende = min(x for x in (js.index("\nasync function ", anf + 10),
                           js.index("\nfunction ", anf + 10)) if x > anf)
    # OHNE die Kommentare. Beim ersten Anlauf am 21.09.2026 fand dieser Test
    # den Namen in der Erklaerung darueber und blieb gruen, nachdem ich den
    # Aufruf zur Gegenprobe entfernt hatte. Ein Test, der den Kommentar
    # prueft, prueft nichts.
    rumpf = "\n".join(z for z in js[anf:ende].splitlines()
                      if not z.lstrip().startswith("//"))
    assert "ladeKurs(" in rumpf, \
        "die Uebersicht muss den Kurs selbst anstossen"
    # NICHT abgewartet -- der Endpunkt liest nur aus dem Zwischenspeicher,
    # aber die Uebersicht soll auf gar nichts warten muessen.
    assert "await ladeKurs" not in rumpf, \
        "der Kurs darf die Uebersicht nicht aufhalten"
    # Und die Abbruchbedingung muss die Uebersicht weiterhin zulassen,
    # sonst liefe der Aufruf ins Leere.
    stelle = js.index("async function ladeKurs(")
    assert '"uebersicht"' in js[stelle:stelle + 400]


def test_der_blockkopf_zeigt_was_die_anwendung_laengst_weiss(js):
    """Der Befund vom 21.09.2026, als Vergleich mit mempool.space gemeldet:
    "sieht unsere block anzeige irgendwie vergleichbar oder genau so
    uebersichtlich aus ... ich glaube nicht".

    Sie sah es nicht, und der Grund war nicht das Aussehen: die Kopfzeile
    zeigte den Blocknamen und die Gebuehrenspanne, mehr nicht. Die Anzahl
    der Transaktionen und die Summe der Gebuehren liefert der Endpunkt
    (b.anzahl, b.sat) seit jeher mit -- sie wurden ausgelesen und
    weggeworfen. Die Zeit bis zum Block fehlte ganz, obwohl das die Frage
    ist, die man an eine Blockliste hat.
    """
    stelle = js.index("function zeichneKacheln")
    rumpf = js[stelle:stelle + 6000]
    for was, wo in (("b.anzahl", "die Zahl der Transaktionen"),
                    ("b.sat", "die Summe der Gebuehren"),
                    ("a_kb_wann", "die Zeit bis zum Block")):
        assert was in rumpf, f"{wo} fehlt im Blockkopf"


def test_der_blockkopf_laeuft_nicht_in_die_nachbarspalte(js):
    """Im selben Bildschirmfoto las sich die erste Spalte "ock".

    Bei acht Bloecken auf einem schmalen Fenster ist "naechster Block"
    breiter als die Spalte, und der Text lief einfach weiter. Gemessen wurde
    nie. Jetzt schon -- und was nicht ganz hinpasst, faellt weg, statt halb
    dazustehen: "0.11 - 2.…" beantwortet keine Frage.
    """
    stelle = js.index("function zeichneKacheln")
    rumpf = js[stelle:stelle + 6000]
    assert "measureText" in rumpf, "die Breite muss gemessen werden"
    # Die beiden unteren Zeilen haengen an einer Platzpruefung, nicht am
    # Kuerzen.
    assert "c.measureText(spanne).width <= spalte" in rumpf
    assert "c.measureText(inhalt).width <= spalte" in rumpf


def test_der_fassungskasten_nennt_auch_die_eigene_fassung(js):
    """Der Befund vom 21.09.2026 aus dem Betrieb.

    Der Knoten lief auf 0.66, 1.0.1 lag seit Stunden in der Registry, und
    die Anwendung erwaehnte es mit keinem Wort -- sie sah nur nach
    Neuerungen fuer bitcoind und LND. Der Betreiber ging stattdessen ueber
    die Docker-Oberflaeche seines NAS, die nur zieht, was in der .env steht.

    Zwei Haelften, und beide mussten nachgetragen werden: die Pruefung im
    Hintergrund (updates.SATCORTEX) und diese Liste hier. Sie war fest
    verdrahtet -- dieselbe Falle wie beim Kurs am selben Tag: die
    Schnittstelle liefert es, die Oberflaeche zaehlt es nicht auf.
    """
    stelle = js.index("function zeichneNeuerungen")
    rumpf = js[stelle:stelle + 1500]
    assert '"satcortex"' in rumpf, "die eigene Fassung fehlt in der Liste"
    # Und sie steht oben: es ist die einzige, die dieser Kasten selbst meint.
    assert rumpf.index('"satcortex"') < rumpf.index('"bitcoind"')


# ── Die Gebuehrenverteilung: gezeigt, nicht erklaert ───────────────────────
#
# Der Befund vom 21.09.2026 aus dem Betrieb, mit Bild: derselbe fuenfzeilige
# Absatz stand NEUNMAL untereinander im Gebuehrenkasten. Dazu der Betreiber:
# "was das den bitte fuer ein riesen text ?? was soll sowas immer ... kann
# mann nicht einfach machen: 50% 0-100 die anderen 50% 100-600".
#
# Zwei Fehler in einem Bild. Der zweite ist der eigentliche.

def test_die_gebuehrenzeile_haengt_nichts_an_ihren_nachbarn(js):
    """DER FEHLER, der das Bild erzeugt hat.

    zeichneNetzgebuehren() lief bei jedem Anzeigen und haengte den Absatz per
    zahlen.after() als NEUES Geschwister an. Entfernt hat ihn nie jemand.
    Nach neun Durchlaeufen stand er neunmal da.

    Dieselbe Falle ist an anderer Stelle schon einmal aufgeschlagen -- in
    zeigeUebersicht() steht seitdem "Festes Element statt .after()". Hier
    wird sie festgenagelt: in dieser Funktion wird nichts angehaengt, was
    nicht vorher geleert wurde.
    """
    import re
    anfang = js.index("function zeichneNetzgebuehren(")
    ende = re.search(r"\n(?:async )?function ", js[anfang + 10:])
    rumpf = js[anfang:anfang + 10 + ende.start()]
    # OHNE Kommentarzeilen. Beim ersten Anlauf war dieser Test gruen aus dem
    # falschen Grund: er fand "zahlen.after()" in dem Kommentar, der den
    # Fehler BESCHREIBT. Genau die Falle, vor der AGENTS.md warnt.
    code = "\n".join(z for z in rumpf.splitlines()
                     if not z.lstrip().startswith("//"))
    assert ".after(" not in code


def test_der_erklaerabsatz_ist_weg(js):
    """Fuenf Zeilen, die erklaerten, dass die Verteilung schief ist. Die
    Verteilung zeigt das jetzt selbst -- und sagt zusaetzlich, WO die Masse
    liegt. Das stand in dem Absatz nie."""
    assert "gb_netz_schief" not in js


def test_die_verteilung_wird_gezeichnet(js, html):
    assert 'id="gb-netz-verteilung"' in html
    assert "function zeichneVerteilung(" in js


def test_die_stufen_nennen_ihre_spanne_und_ihren_anteil(js):
    """Eine Leiste ohne Beschriftung waere Dekoration. Gefragt war
    "50% 0-100" -- also beides."""
    for schluessel in ("gb_stufe_von_bis", "gb_stufe_ab",
                       "gb_stufe_anteil"):
        assert js.count(schluessel + ":") == 2       # deutsch und englisch


def test_ohne_stufen_steht_dort_die_spanne(js):
    """Jede Messung von vor dem 21.09.2026 hat keine Verteilung. Dann die
    alte Spannenzeile -- und keine leere Leiste."""
    assert js.count("gb_netz_spanne:") == 2


# ── Die Blockzeit in der Uebersicht ────────────────────────────────────────

def test_die_uebersicht_hat_eine_blockzeit(html, js):
    """Der Betreiber, 21.09.2026: "sone arte block zeit in der uebersicht"."""
    abschnitt = html[html.index('<section data-ansicht="uebersicht">'):]
    abschnitt = abschnitt[:abschnitt.index("</section>")]
    assert 'id="d-blockzeit"' in abschnitt
    assert "function zeichneBlockzeit(" in js


def test_die_blockzeit_wird_aus_dem_status_gefuellt(js):
    """Kein eigener Abruf: die Zahlen stehen in der Antwort, die die
    Uebersicht ohnehin holt."""
    anfang = js.index("async function zeigeUebersicht()")
    rumpf = js[anfang:anfang + 9000]
    code = "\n".join(z for z in rumpf.splitlines()
                     if not z.lstrip().startswith("//"))
    assert "zeichneBlockzeit(d.halbierung)" in code


def test_die_belohnung_bekommt_so_viele_stellen_wie_sie_braucht(js):
    """3,125 und nicht 3,12500000 -- aber ab der neunten Halbierung werden
    es wirklich acht Stellen, und dann muessen sie dastehen."""
    assert "function belohnungBtc(" in js


def test_das_geschaetzte_datum_gibt_sich_nicht_genauer_als_es_ist(js):
    """Ueber anderthalb Jahre hochgerechnet ist ein Tagesdatum eine
    Behauptung. Monat und Jahr sind die ehrliche Genauigkeit -- dafuer gibt
    es monatJahr() schon."""
    import re
    anfang = js.index("function zeichneBlockzeit(")
    ende = re.search(r"\n(?:async )?function ", js[anfang + 10:])
    rumpf = js[anfang:anfang + 10 + ende.start()]
    assert "monatJahr(" in rumpf
    assert "toLocaleDateString" not in rumpf


def test_die_blockzeit_sagt_ob_gemessen_oder_gerechnet_wurde(js):
    """Waehrend des Abgleichs ist der eigene Takt nicht messbar. Dann steht
    dort der Zielabstand -- und die Zeile muss das zugeben, statt eine
    Messung zu behaupten."""
    for schluessel in ("bz_takt_gemessen", "bz_takt_gerechnet"):
        assert js.count(schluessel + ":") == 2


# ── Die Geldwege: ein Abbruch ist kein Fehlschlag (Befund 22.09.2026) ──────
#
# Beim Audit gefunden, und es ist der teuerste Befund bisher: die Oberflaeche
# brach jeden Aufruf nach 25 Sekunden ab. Der Server wartet beim Zahlen aber
# bis zu 80 und antwortet dann mit "zahlung_unklar" -- "kann trotzdem
# unterwegs sein, NICHT wiederholen". Dieser Text war unerreichbar. Was der
# Mensch sah, war "Fehler", ueber eine Zahlung, die gerade lief.

WEB_BACKEND = Path(__file__).resolve().parents[1] / "satcortex"


def test_die_frist_fuer_geld_ist_laenger_als_das_zeitlimit_des_servers(js):
    """DIE WACHE, die den Befund festnagelt.

    Sie vergleicht die beiden Zahlen ueber die Dateigrenze hinweg. Stellt
    jemand eine davon um, faellt es hier auf -- und nicht erst bei einer
    Zahlung, die gerade unterwegs ist.
    """
    import re
    lnd = (WEB_BACKEND / "lnd.py").read_text(encoding="utf-8")
    zeitlimit = int(re.search(r"ZAHLUNG_ZEITLIMIT_SEKUNDEN = (\d+)",
                              lnd).group(1))
    luft = float(re.search(r"ZAHLUNG_LUFT_SEKUNDEN = ([\d.]+)", lnd).group(1))
    frist_ms = int(re.search(r"const FRIST_GELD_MS = (\d+)", js).group(1))
    assert frist_ms > (zeitlimit + luft) * 1000, (
        "die Oberflaeche gibt auf, bevor der Server antworten kann")


def test_die_geldwege_nehmen_die_laengere_frist(js):
    """Alle fuenf -- eine vergessene genuegt, um den Befund zurueckzuholen."""
    for pfad in ("/lightning/senden", "/lightning/rechnung/zahlen",
                 "/lightning/kanal/oeffnen", "/lightning/kanal/schliessen",
                 "/lightning/umschichten"):
        stelle = js.index('api("%s"' % pfad)
        assert "FRIST_GELD_MS" in js[stelle:stelle + 400], pfad


def test_ohne_bescheid_wird_kein_fehlschlag_gemeldet(js):
    """Der Kern: kein Bescheid heisst "unklar", nicht "Fehler"."""
    anfang = js.index("function geldfehler(")
    import re
    ende = re.search(r"\n(?:async )?function ", js[anfang + 10:])
    rumpf = js[anfang:anfang + 10 + ende.start()]
    code = "\n".join(z for z in rumpf.splitlines()
                     if not z.lstrip().startswith("//"))
    assert "netzfehler" in code, "der Abbruch der Oberflaeche"
    assert "504" in code, "und das Zeitlimit des Servers"


def test_nach_einem_abbruch_bleibt_der_knopf_zu(js):
    """"NICHT wiederholen" ist eine Anweisung -- die Oberflaeche soll das
    Wiederholen nicht im selben Atemzug wieder anbieten."""
    for name in ("sendenAusloesen", "rechnungZahlen"):
        anfang = js.index("function %s(" % name)
        import re
        ende = re.search(r"\n(?:async )?function ", js[anfang + 10:])
        rumpf = js[anfang:anfang + 10 + ende.start()]
        code = "\n".join(z for z in rumpf.splitlines()
                         if not z.lstrip().startswith("//"))
        assert "knopf.disabled = false;" not in code.replace(
            "if (wiederFrei) knopf.disabled = false;", ""), name
        assert "wiederFrei" in code, name


def test_fuer_jede_art_von_unklarheit_gibt_es_einen_eigenen_text(js):
    """"in den Kanaelen nachsehen" waere bei einer Ueberweisung falsch --
    dort sieht man in die Kette."""
    for schluessel in ("zahlung_unklar", "sendung_unklar", "kanal_unklar"):
        assert js.count(schluessel + ":") == 2, schluessel


# ── Der Sprachwechsel (Befund 22.09.2026) ─────────────────────────────────

def test_die_gegenstellenwege_folgen_dem_sprachwechsel(js):
    """Die Liste wurde EINMAL gebaut ("einmal reicht") und trug uebersetzten
    Text. Wer auf Englisch umschaltete, behielt sie dauerhaft auf Deutsch --
    sie wird nirgendwo sonst angefasst."""
    anfang = js.index("function zeichneGegenstellenwege(")
    import re
    ende = re.search(r"\n(?:async )?function ", js[anfang + 10:])
    code = "\n".join(z for z in js[anfang:anfang + 10 + ende.start()]
                     .splitlines() if not z.lstrip().startswith("//"))
    assert "ziel.firstChild" not in code, "die Wache war der Fehler"
    assert "textContent = \"\"" in code, "leeren statt aussteigen"


def test_die_seedfelder_beschriften_sich_neu(js):
    """Dieselbe Sache bei den aria-label der 24 Woerter. Nur fuer
    Vorlesewerkzeuge sichtbar -- und genau deshalb faellt es sonst nie auf."""
    assert "function whBeschriften(" in js


# ── "Nicht gemessen" darf keine Messung werden (Befund 22.09.2026) ─────────

def test_unbekannte_tx_zahl_wird_nicht_zur_null(js):
    """DER BEFUND, und das Backend sagt selbst, worum es geht:

        # Ausdruecklich None statt null-Zahlen: wir waren nicht dabei,
        # und eine Null saehe aus wie eine Messung.
        "bekannte_tx": None,

    Die Oberflaeche machte daraus zahl(b.bekannte_tx || 0) und zeigte
    "0 / 2431 Tx" -- genau die Messung, die das Backend zu erfinden sich
    geweigert hatte. Und das bei der Zahl, fuer die man einen eigenen Knoten
    betreibt.
    """
    code = "\n".join(z for z in js.splitlines()
                     if not z.lstrip().startswith("//"))
    assert "bekannte_tx || 0" not in code


def test_es_gibt_einen_text_fuer_nicht_dabei_gewesen(js):
    for schluessel in ("a_kb_nicht_dabei", "a_nicht_dabei_kurz"):
        assert js.count(schluessel + ":") == 2, schluessel


# ── Zahlen, die die Oberflaeche nicht selbst besitzt ───────────────────────

def test_die_staubgrenze_stimmt_mit_dem_backend_ueberein(js):
    """546 steht als Literal in beiden Uebersetzungen ("Mindestens 546
    Satoshi. Darunter nimmt das Netz die Ausgabe nicht an"). Die Wahrheit
    ist lnd.SENDEN_MIN_SAT. Laufen sie auseinander, behauptet die
    Oberflaeche etwas Falsches ueber das Netz -- und der Nutzer bekommt
    eine Abfuhr mit einer anderen Zahl als der angezeigten."""
    import re
    lnd = (WEB_BACKEND / "lnd.py").read_text(encoding="utf-8")
    echt = int(re.search(r"SENDEN_MIN_SAT = (\d+)", lnd).group(1))
    for sprache in ("de", "en"):
        anfang = js.index("\n  %s: {" % sprache)
        block = js[anfang:anfang + 200000]
        text = re.search(r'\n    sd_betrag_d: "([^"]*)"', block).group(1)
        assert str(echt) in text, (sprache, text[:80])


def test_das_wiederherstellungsfenster_stimmt_mit_dem_backend_ueberein(js):
    """Dasselbe fuer die 2500 Adressen, die LND beim Wiederherstellen
    absucht. Die Zahl steht fest in app.js, waehrend lnd.py sie besitzt."""
    import re
    lnd = (WEB_BACKEND / "lnd.py").read_text(encoding="utf-8")
    echt = int(re.search(r"WIEDERHERSTELLUNG_FENSTER = (\d+)", lnd).group(1))
    code = "\n".join(z for z in js.splitlines()
                     if not z.lstrip().startswith("//"))
    stelle = code.index('t("wh_dauer"')
    assert str(echt) in code[stelle:stelle + 120], code[stelle:stelle + 120]


def test_jeder_angefasste_bezeichner_steht_auch_in_der_vorlage(html, js):
    """Ein Tippfehler in einem Bezeichner ist kein kleiner Fehler.

    $("#gibts-nicht") liefert null. Steht das im Verdrahten der Knoepfe, wirft
    die Zeile -- und ALLES, was danach verdrahtet worden waere, bleibt tot.
    Der Nutzer sieht eine Seite, die aussieht wie immer und auf der die
    Haelfte der Knoepfe nichts tut. Im Protokoll steht nichts, denn der Fehler
    passierte einmal beim Start.

    Aufgefallen beim Einbau des Zuruecknehmens am 23.09.2026: der Knopf wurde
    im Skript angefasst, bevor er in der Vorlage stand.
    """
    import re
    vorhanden = set(re.findall(r'id="([^"]+)"', html))
    angefasst = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', js))
    assert angefasst, "die Suche hat gar nichts gefunden -- Muster pruefen"
    fehlt = sorted(angefasst - vorhanden)
    assert not fehlt, ("im Skript angefasst, in der Vorlage nicht vorhanden: "
                       + ", ".join(fehlt))


def test_die_frist_fuer_die_kacheln_ist_laenger_als_die_des_servers(js):
    """DER BEFUND VOM 23.09.2026 aus dem Betrieb: "brauch ich immer 5 mal
    klicken im schnitt damit was geht".

    Der Browser gab nach 25 Sekunden auf, der Server gestand Core 45 zu --
    und das gilt fuer jedes SCHWEIGEN im Strom, nicht fuer den ganzen Abruf;
    danach wird noch gerechnet. Deshalb mindestens das Doppelte.
    """
    import re
    quelle = (WEB_BACKEND / "api.py").read_text(encoding="utf-8")
    server_s = float(re.search(r"KACHEL_RPC_ZEITLIMIT_S = ([\d.]+)",
                               quelle).group(1))
    frist_ms = int(re.search(r"const FRIST_KACHELN_MS = (\d+)", js).group(1))
    assert frist_ms >= 2 * server_s * 1000, (
        "die Oberflaeche gibt auf, bevor der Server fertig sein kann")
    stelle = js.index('api("/auswertung/mempool/kacheln"')
    assert "FRIST_KACHELN_MS" in js[stelle:stelle + 200], (
        "der Abruf nimmt die eigene Frist nicht")


def test_der_sammeltext_behauptet_kein_speichern(js):
    """Der Ersatztext fuer jeden Fehler ohne eigene Meldung lautete "Konnte
    nicht gespeichert werden" -- und diente an 36 Stellen als Ersatz, fast
    immer dort, wo nichts gespeichert wird: beim Holen der Kacheln, beim
    Zurueckziehen einer Rechnung, bei Messungen. Am 13.09.2026 wurde das an
    EINER Stelle geflickt (Wachturm-Pruefung); der Text selbst blieb."""
    import re
    texte = re.findall(r'e_fehler: "([^"]*)"', js)
    assert len(texte) == 2, "je Sprache genau einer"
    for text in texte:
        assert not re.search(r"gespeichert|saved", text, re.I), text


# ── Externe Wallets ─────────────────────────────────────────────────────────
#
# Aus dem Betrieb, 26.09.2026: "dann solte es links einen neuen reiter geben
# externe wallet oder so wo mann dann die sachen findet! und es wird dann nur
# tor und vpn angeboten".

def _abschnitt(html, name):
    anfang = html.index(f'<section data-ansicht="{name}"')
    return html[anfang:html.index("</section>", anfang)]


def test_es_gibt_links_einen_reiter_fuer_externe_wallets(html):
    leiste = html[html.index('<nav class="seitenleiste"'):html.index("</nav>")]
    assert 'data-ansicht="extern"' in leiste
    assert '<section data-ansicht="extern"' in html


def test_angeboten_werden_genau_tor_und_vpn(html):
    wege = re.findall(r'name="fz-weg" value="([^"]+)"',
                      _abschnitt(html, "extern"))
    assert sorted(wege) == ["tor", "vpn"]


def test_die_stufen_der_oberflaeche_sind_die_des_servers(html):
    from satcortex import fernzugang
    stufen = re.findall(r'name="fz-stufe" value="([^"]+)"',
                        _abschnitt(html, "extern"))
    assert tuple(stufen) == fernzugang.STUFEN_REIHENFOLGE
    for stufe in stufen:
        assert f'data-i18n="fz_stufe_{stufe}_d"' in _abschnitt(html, "extern")


def test_sparrow_steht_jetzt_bei_den_externen_wallets(html):
    assert 'id="e-rpc-an"' in _abschnitt(html, "extern")
    assert 'id="e-rpc-an"' not in _abschnitt(html, "einstellungen")


def test_die_sparrow_freigabe_schickt_nur_das_heimnetz(js):
    """Die Einstellungsfelder koennen ungeladen sein, wenn man direkt in den
    Reiter geht -- ihre Vorgaben duerfen dann nicht mitgespeichert werden."""
    block = _block(js, "async function rpcFreigabeSpeichern(")
    assert 'api("/knoten/rpc-freigabe", "POST", { rpc_heimnetz: netz })' in block
    assert "/knoten/netzwege" not in block
    assert '$("#e-tor")' not in block


def test_anlegen_und_widerrufen_schicken_die_pin(js):
    anlegen = _block(js, "async function geraetErstellen(")
    assert 'mitPin("#fz-pin")' in anlegen
    widerruf = _block(js, "function fzWiderrufenKnopf(")
    assert 'mitPin("#fz-pin")' in widerruf
    assert "#fz-pin-zeile" in _block(js, "async function pinLaden(")


def test_der_schluessel_verschwindet_beim_verlassen_des_reiters(js):
    block = _block(js, "function zeigeAnsicht(")
    zeile = next(z for z in block.splitlines() if "fzErgebnisWeg()" in z)
    assert 'ANSICHT === "extern"' in zeile and 'name !== "extern"' in zeile
    weg = _block(js, "function fzErgebnisWeg(")
    assert '$("#fz-text").textContent = ""' in weg
    assert '$("#fz-qr").textContent = ""' in weg


def test_der_schluessel_wird_nur_als_text_gesetzt(js):
    """Er kommt vom Server, aber als Text -- nie als HTML."""
    block = _block(js, "async function geraetErstellen(")
    assert '$("#fz-text").textContent = d.verbindung' in block
    assert "innerHTML" not in block
    assert "innerHTML" not in _block(js, "function zeichneFzListe(")
