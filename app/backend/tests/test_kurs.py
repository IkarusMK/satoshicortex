"""Die Kurstafel.

Dieses Modul hatte bis zum 08.09.2026 KEINEN einzigen Test -- und genau hier
stand die Zahl, an der ein Nutzer abliest, was sein Geld wert ist. Der Betreiber
sah in der Oberflaeche "EUR 78.417", waehrend das Diagramm daneben 67-68k
zeichnete und die Meldung darunter von "$78,000" sprach.

Der Dollarkurs mit einem Euro-Zeichen davor. Nicht seit heute: seit es die
Kurstafel gibt, denn USD stimmte immer -- und nur USD wurde je angesehen.

Geprueft wird deshalb vor allem eines: dass keine Zahl unter einer Waehrung
erscheint, zu der sie nicht gehoert.
"""
import time

import pytest

from satcortex import kurs as K


# ------------------------------------------------------- kleine Bausteine ---

def test_zahl_weist_unbrauchbares_ab():
    assert K._zahl("79805.00") == 79805.0
    for schrott in (None, "", "viel", float("nan"), float("inf"), 0, -5):
        assert K._zahl(schrott) is None, schrott


def test_prozent_darf_negativ_sein():
    """Ein Minustag ist ein Tag wie jeder andere -- _zahl() wuerde ihn
    verschlucken und nur die guten Tage zeigen."""
    assert K._roh_prozent("-0.85") == -0.85
    assert K._roh_prozent(0) == 0.0
    assert K._roh_prozent("nichts") is None


def test_jede_boerse_baut_fuer_jede_waehrung_eine_https_adresse():
    for boerse in K.BOERSEN:
        for w in K.WAEHRUNGEN:
            adresse = boerse.kurs_adresse(w)
            assert adresse.startswith("https://"), (boerse.name, w)
            if boerse.verlauf_adresse:
                schritt, anzahl = K.ZEITRAEUME[K.VORGABE_ZEITRAUM]
                assert boerse.verlauf_adresse(w, schritt, anzahl).startswith(
                    "https://"), (boerse.name, w)


def test_unbekannte_waehrung_faellt_auf_dollar_zurueck():
    assert K._pruefe_waehrung("btc") == "usd"
    assert K._pruefe_waehrung("") == "usd"
    assert K._pruefe_waehrung("EUR") == "eur"


# ------------------------------------------------------------- Kurstafel ---

def _tafel(monkeypatch, kurse, verlaeufe=None):
    """Eine Tafel mit erfundenen Boersendaten, ohne Netz und ohne Tor."""
    geholt = []

    def falscher_kurs(w, proxy):
        geholt.append(w)
        return {"kurs": kurse[w], "wechsel24": -0.85, "hoch": None,
                "tief": None, "stand": int(time.time()),
                "boerse": "Attrappe", "waehrung": w}, ""

    def falscher_verlauf(w, zeitraum, proxy):
        punkte = (verlaeufe or {}).get(w) or [
            (1, kurse[w], kurse[w], kurse[w]),
            (2, kurse[w], kurse[w], kurse[w])]
        return punkte, "Attrappe"

    monkeypatch.setattr(K, "hole_kurs", falscher_kurs)
    monkeypatch.setattr(K, "hole_verlauf", falscher_verlauf)
    return K.Kurstafel(lambda: "http://tor:9080"), geholt


KURSE = {"usd": 78417.0, "eur": 67830.0, "gbp": 58200.0}


def test_waehrungswechsel_zeigt_nicht_den_alten_kurs(monkeypatch):
    """DER Fehler vom 08.09.2026.

    Der Waechter holt alle fuenf Minuten den Dollarkurs. Schaltet die
    Oberflaeche danach auf Euro, war der gespeicherte Kurs keine fuenf
    Minuten alt -- es wurde gar nicht erst geholt, und die 78.417 Dollar
    erschienen mit einem Euro-Zeichen davor.
    """
    tafel, _ = _tafel(monkeypatch, KURSE)

    tafel.einmal_holen("usd")                     # der Waechter, wie immer
    assert tafel.als_dict("usd")["kurs"] == 78417.0

    tafel.einmal_holen("eur")                     # der Nutzer schaltet um
    assert tafel.als_dict("eur")["kurs"] == 67830.0


def test_kurs_wird_je_waehrung_getrennt_gehalten(monkeypatch):
    tafel, _ = _tafel(monkeypatch, KURSE)
    for w in ("usd", "eur", "gbp"):
        tafel.einmal_holen(w)
    for w, erwartet in KURSE.items():
        d = tafel.als_dict(w)
        assert d["kurs"] == erwartet, w
        assert d["waehrung"] == w


def test_kurs_einer_fremden_waehrung_wird_nie_ausgeliefert(monkeypatch):
    """Doppelter Boden: waere die Ablage doch einmal durcheinander, kommt
    lieber gar kein Kurs als ein falscher."""
    tafel, _ = _tafel(monkeypatch, KURSE)
    tafel.einmal_holen("usd")
    # Von Hand verbogen -- so, wie es der Fehler oben getan hat.
    tafel._kurs["eur"] = dict(tafel._kurs["usd"])
    assert tafel.als_dict("eur")["kurs"] is None


def test_zweiter_abruf_binnen_der_frist_holt_nicht_erneut(monkeypatch):
    """Ueber Tor kostet jeder Abruf einen Kreisaufbau. Der Zwischenspeicher
    muss halten -- nur eben je Waehrung."""
    tafel, geholt = _tafel(monkeypatch, KURSE)
    tafel.einmal_holen("eur")
    tafel.einmal_holen("eur")
    assert geholt == ["eur"]


def test_fehlschlag_laesst_den_letzten_kurs_stehen(monkeypatch):
    """Eine Tafel, die bei jedem Aussetzer leer wird, ist schlechter als
    eine, die sagt, wie alt ihre Zahl ist."""
    tafel, _ = _tafel(monkeypatch, KURSE)
    tafel.einmal_holen("eur")

    def weist_ab(w, proxy):
        raise K.Abgewiesen("Die Boerse weist uns ab (HTTP 403).")

    monkeypatch.setattr(K, "hole_kurs", weist_ab)
    tafel.einmal_holen("eur", erzwingen=True)
    d = tafel.als_dict("eur")
    assert d["kurs"] == 67830.0
    assert "403" in d["grund"]


def test_ohne_tor_wird_nichts_geholt(monkeypatch):
    tafel, geholt = _tafel(monkeypatch, KURSE)
    tafel._proxy_gibt = lambda: None
    tafel.einmal_holen("eur")
    assert geholt == []
    assert tafel.grund == "tor_aus"


# --------------------------------------------------- was der Waechter holt ---

def test_angesehene_waehrung_kommt_in_den_gebrauch(monkeypatch):
    """Der Waechter holte fest "usd" -- deshalb blieb Euro ewig kalt.
    Jetzt frischt er das auf, was tatsaechlich angesehen wurde."""
    tafel, _ = _tafel(monkeypatch, KURSE)
    tafel.als_dict("eur", "24h")
    assert ("eur", "24h") in tafel.in_gebrauch()


def test_ohne_jeden_abruf_bleibt_dollar_die_vorgabe(monkeypatch):
    tafel, _ = _tafel(monkeypatch, KURSE)
    assert tafel.in_gebrauch() == [("usd", K.VORGABE_ZEITRAUM)]


def test_der_gebrauch_ist_gedeckelt(monkeypatch):
    """Sonst zoege ein Nutzer, der alle Ansichten durchklickt, im
    Fuenf-Minuten-Takt ein Dutzend Tor-Kreise auf."""
    tafel, _ = _tafel(monkeypatch, KURSE)
    for w in K.WAEHRUNGEN:
        for z in K.ZEITRAEUME:
            tafel.als_dict(w, z)
    assert len(tafel.in_gebrauch()) <= K.GEBRAUCH_HOECHSTENS


def test_alter_gebrauch_faellt_wieder_heraus(monkeypatch):
    tafel, _ = _tafel(monkeypatch, KURSE)
    tafel.als_dict("gbp", "1j")
    tafel._benutzt[("gbp", "1j")] = time.time() - K.GEBRAUCH_FRIST_SEKUNDEN - 1
    assert ("gbp", "1j") not in tafel.in_gebrauch()


# ------------------------------------------------ die Auswerter der Boersen ---
#
# Diese Funktionen lesen fremde Antworten. Sie waren bis zum 08.09.2026
# ungeprueft -- und aus einer von ihnen kam die Zahl, die der Betreiber unter dem
# falschen Waehrungszeichen sah. Die Antwortformen unten sind die echten.

BITSTAMP_TICKER = {
    "timestamp": "1757340000", "open": "68410.00", "high": "68900.00",
    "low": "66800.00", "last": "67830.00", "volume": "812.4",
    "percent_change_24": "-0.85",
}

KRAKEN_TICKER = {"error": [], "result": {"XXBTZEUR": {
    "a": ["67831.00", "1", "1.000"], "b": ["67829.00", "2", "2.000"],
    "c": ["67830.00", "0.00100000"], "v": ["100.0", "812.4"],
    "p": ["67900.0", "67750.0"], "t": [1200, 18400],
    "l": ["67100.0", "66800.0"], "h": ["68100.0", "68900.0"],
    "o": "68410.0"}}}

KRAKEN_OHLC = {"error": [], "result": {
    "XXBTZEUR": [
        [1757336400, "68410.0", "68500.0", "68000.0", "68100.0", "68200.0",
         "12.5", 340],
        [1757340000, "68100.0", "68200.0", "67500.0", "67830.0", "67900.0",
         "9.1", 280]],
    "last": 1757340000}}


def test_bitstamp_ticker_wird_richtig_gelesen():
    d = K._bitstamp_kurs(BITSTAMP_TICKER)
    assert d["kurs"] == 67830.0
    assert d["offen"] == 68410.0
    assert d["hoch"] == 68900.0 and d["tief"] == 66800.0
    assert d["wechsel24"] == -0.85          # negativ, nicht verschluckt
    assert d["stand"] == 1757340000


def test_bitstamp_verlauf_ueberspringt_kaputte_kerzen():
    roh = {"data": {"ohlc": [
        {"timestamp": "1757336400", "close": "68100.0",
         "high": "68500.0", "low": "68000.0"},
        {"timestamp": "1757340000", "close": "keine Zahl"},   # weg
        {"timestamp": "kein Zeitpunkt", "close": "67830.0"},  # weg
        {"timestamp": "1757343600", "close": "67830.0"},      # ohne hoch/tief
    ]}}
    punkte = K._bitstamp_verlauf(roh)
    assert [p[0] for p in punkte] == [1757336400, 1757343600]
    assert punkte[0] == (1757336400, 68100.0, 68500.0, 68000.0)
    # Fehlt die Spanne, tritt der Schlusskurs an ihre Stelle -- nicht None,
    # sonst zerfaellt die Zeichnung an einer einzigen luecken Kerze.
    assert punkte[1] == (1757343600, 67830.0, 67830.0, 67830.0)


def test_kraken_ticker_nimmt_den_letzten_kurs_und_die_24h_spanne():
    d = K._kraken_kurs(KRAKEN_TICKER)
    assert d["kurs"] == 67830.0             # c[0], der letzte Handel
    assert d["offen"] == 68410.0            # o, Tageseroeffnung
    assert d["hoch"] == 68900.0             # h[1] = 24 h, nicht h[0] = heute
    assert d["tief"] == 66800.0             # l[1], ebenso
    assert d["wechsel24"] == round((67830.0 - 68410.0) / 68410.0 * 100, 2)
    assert d["wechsel24"] < 0


def test_kraken_ohne_ergebnis_wird_abgewiesen():
    with pytest.raises(K.Abgewiesen):
        K._kraken_kurs({"error": ["EQuery:Unknown asset pair"], "result": {}})


def test_kraken_verlauf_laesst_den_last_zeiger_liegen():
    """Krakens Antwort mischt die Kerzen mit einem Feld "last". Wer das
    mitliest, iteriert ueber eine Zahl."""
    punkte = K._kraken_verlauf(KRAKEN_OHLC)
    assert len(punkte) == 2
    assert punkte[1] == (1757340000, 67830.0, 68200.0, 67500.0)


def test_kraken_verlauf_ohne_kerzen_ist_leer():
    assert K._kraken_verlauf({"result": {"last": 1757340000}}) == []


def test_coinbase_liefert_nur_den_blanken_kurs():
    d = K._coinbase_kurs({"data": {"base": "BTC", "currency": "EUR",
                                   "amount": "67830.00"}})
    assert d["kurs"] == 67830.0
    assert d["hoch"] is None and d["wechsel24"] is None


# ------------------------------------------------------- Reihenfolge & Fall ---

@pytest.fixture(autouse=True)
def _ohne_gedaechtnis():
    """_ZULETZT ist Modulzustand und ueberlebt sonst den einzelnen Test.

    Ohne dieses Zuruecksetzen haengt das Ergebnis davon ab, welcher Test
    vorher lief -- und ein Test, der von der Reihenfolge seiner Nachbarn
    abhaengt, beweist nichts.
    """
    K._ZULETZT.clear()
    yield
    K._ZULETZT.clear()


def _antworten(monkeypatch, plan):
    """_hole_json ersetzen: je Adressteil eine Antwort oder ein Fehler."""
    gefragt = []

    def falsch(adresse, proxy):
        gefragt.append(adresse)
        for teil, antwort in plan.items():
            if teil in adresse:
                if isinstance(antwort, Exception):
                    raise antwort
                return antwort
        raise K.Abgewiesen("nicht eingeplant")

    monkeypatch.setattr(K, "_hole_json", falsch)
    return gefragt


def test_kurs_traegt_immer_die_angefragte_waehrung(monkeypatch):
    """Auf dieses Feld stuetzt sich der doppelte Boden in _passender_kurs.
    Faellt es weg, liefert die Tafel voellig zu Recht gar nichts mehr."""
    _antworten(monkeypatch, {"bitstamp.net": BITSTAMP_TICKER})
    for w in K.WAEHRUNGEN:
        werte, _ = K.hole_kurs(w, "http://tor:9080")
        assert werte["waehrung"] == w
        assert werte["boerse"] == "Bitstamp"


def test_die_waehrung_steht_in_der_abgefragten_adresse(monkeypatch):
    gefragt = _antworten(monkeypatch, {"bitstamp.net": BITSTAMP_TICKER})
    K.hole_kurs("eur", "http://tor:9080")
    assert "btceur" in gefragt[0]


def test_faellt_eine_boerse_aus_kommt_die_naechste(monkeypatch):
    """Genau dafuer stehen Kraken und Coinbase in der Liste."""
    gefragt = _antworten(monkeypatch, {
        "bitstamp.net": K.Abgewiesen("HTTP 403"),
        "kraken.com": KRAKEN_TICKER,
    })
    werte, _ = K.hole_kurs("eur", "http://tor:9080")
    assert werte["boerse"] == "Kraken"
    assert werte["kurs"] == 67830.0
    assert len(gefragt) == 2


def test_antwortet_keine_boerse_gibt_es_einen_grund(monkeypatch):
    _antworten(monkeypatch, {})
    with pytest.raises(K.Abgewiesen):
        K.hole_kurs("eur", "http://tor:9080")


def test_eine_antwort_ohne_kurs_zaehlt_nicht_als_antwort(monkeypatch):
    """Eine Boerse, die 200 sagt und nichts liefert, darf die Kette nicht
    beenden -- sonst steht der Kasten leer, obwohl zwei Quellen bereitstehen."""
    _antworten(monkeypatch, {
        "bitstamp.net": {"last": None},
        "kraken.com": KRAKEN_TICKER,
    })
    werte, _ = K.hole_kurs("eur", "http://tor:9080")
    assert werte["boerse"] == "Kraken"


def test_verlauf_kommt_aufsteigend_und_gekuerzt(monkeypatch):
    """Kraken liefert grundsaetzlich 720 Kerzen, egal was man fragt."""
    viele = [[1757000000 + i * 3600, "1", "2", "0.5", str(60000 + i),
              "1", "1", 1] for i in range(100)]
    _antworten(monkeypatch, {
        "bitstamp.net": K.Abgewiesen("HTTP 403"),
        "kraken.com": {"result": {"XXBTZEUR": list(reversed(viele)),
                                  "last": 1}},
    })
    punkte, boerse = K.hole_verlauf("eur", "24h", "http://tor:9080")
    assert boerse == "Kraken"
    assert len(punkte) == K.ZEITRAEUME["24h"][1]
    assert [p[0] for p in punkte] == sorted(p[0] for p in punkte)


def test_ein_einzelner_punkt_ist_kein_verlauf(monkeypatch):
    """Mit einem Punkt laesst sich keine Linie zeichnen -- dann lieber die
    naechste Quelle fragen."""
    _antworten(monkeypatch, {
        "bitstamp.net": {"data": {"ohlc": [{"timestamp": "1", "close": "1"}]}},
        "kraken.com": KRAKEN_OHLC,
    })
    punkte, boerse = K.hole_verlauf("eur", "24h", "http://tor:9080")
    assert boerse == "Kraken"


# ------------------------------------------------------ der Abruf selbst ---
#
# _hole_json ist die Stelle, an der fremde Daten ins Haus kommen. Sie hat
# eine Laengengrenze und eine eigene Behandlung fuer die Abweisungen, die
# ueber Tor regelmaessig vorkommen -- beides gehoert geprueft.

class _Antwort:
    def __init__(self, roh):
        self._roh = roh
        self.gelesen = None

    def read(self, hoechstens):
        self.gelesen = hoechstens
        return self._roh[:hoechstens]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Oeffner:
    def __init__(self, ergebnis):
        self._ergebnis = ergebnis
        self.anfrage = None
        self.frist = None

    def open(self, anfrage, timeout=None):
        self.anfrage = anfrage
        self.frist = timeout
        if isinstance(self._ergebnis, Exception):
            raise self._ergebnis
        return self._ergebnis


def _oeffner_ersetzen(monkeypatch, ergebnis):
    o = _Oeffner(ergebnis)
    monkeypatch.setattr(K, "_oeffner", lambda proxy: o)
    return o


def test_abruf_gibt_json_zurueck_und_verraet_nichts(monkeypatch):
    o = _oeffner_ersetzen(monkeypatch, _Antwort(b'{"last": "67830.00"}'))
    assert K._hole_json("https://example.invalid/x", "http://tor:9080") == {
        "last": "67830.00"}
    # Kein Kennzeichen, an dem der Betreiber wiedererkennbar waere.
    kennung = o.anfrage.get_header("User-agent")
    assert kennung == "satcortex"
    assert "satoshi" not in kennung.lower()
    assert o.frist == K.ZEITSPERRE_SEKUNDEN


def _abfuhr(monkeypatch, code):
    import urllib.error
    _oeffner_ersetzen(monkeypatch, urllib.error.HTTPError(
        "https://example.invalid/x", code, "Nope", {}, None))
    with pytest.raises(K.Abgewiesen) as fehler:
        K._hole_json("https://example.invalid/x", "http://tor:9080")
    return str(fehler.value)


@pytest.mark.parametrize("code", [401, 403, 418])
def test_abweisung_wird_als_tor_problem_erklaert(monkeypatch, code):
    """Ueber Tor ist das der haeufigste Fall -- Cloudflare mag keine
    Ausgangsknoten. Die Meldung muss das sagen, sonst sucht man am
    falschen Ende.

    418 kam am 10.09.2026 dazu: derselbe Fall, nur mit dem Scherz-Code aus
    RFC 2324, den Schutzdienste fuer "du bist ein Automat" vergeben. In
    Das Betriebsprotokoll stand dafuer noch der rohe Wortlaut.
    """
    satz = _abfuhr(monkeypatch, code)
    assert str(code) in satz
    assert "Tor" in satz


def test_zu_haeufig_gefragt_ist_kein_tor_problem(monkeypatch):
    """Bis zum 10.09.2026 stand 429 in derselben Zeile wie 403 und bekam
    denselben Satz ueber Tor-Ausgangsknoten. Das ist falsch und schickt bei
    der Fehlersuche in die falsche Richtung: 429 heisst "spaeter nochmal",
    403 heisst "du nicht". Dass die Boerse um Abstand bittet, hat mit dem
    Weg dorthin nichts zu tun."""
    satz = _abfuhr(monkeypatch, 429)
    assert "429" in satz
    assert "Tor" not in satz
    assert "Abstand" in satz


def test_ein_fehler_der_boerse_ist_nicht_unser_fehler(monkeypatch):
    satz = _abfuhr(monkeypatch, 503)
    assert "503" in satz and "HTTPError" not in satz


def test_was_keinen_bekannten_grund_hat_behaelt_seinen_wortlaut(monkeypatch):
    """Nicht alles wegerklaeren -- sonst sucht man den Wortlaut nirgends.

    600 ist kein gueltiger HTTP-Code; er steht hier fuer alles, was die
    Deutung nicht kennt. 599 waere der falsche Fall gewesen: der liegt im
    5xx-Bereich und wird sehr wohl gedeutet.
    """
    satz = _abfuhr(monkeypatch, 600)
    assert "600" in satz and "HTTPError" in satz


def test_abbruch_ohne_code_wird_trotzdem_abgefangen(monkeypatch):
    import urllib.error
    _oeffner_ersetzen(monkeypatch, urllib.error.URLError("keine Verbindung"))
    with pytest.raises(K.Abgewiesen):
        K._hole_json("https://example.invalid/x", "http://tor:9080")


def test_kein_json_ist_kein_kurs(monkeypatch):
    _oeffner_ersetzen(monkeypatch, _Antwort(b"<html>Zugriff verweigert</html>"))
    with pytest.raises(K.Abgewiesen) as fehler:
        K._hole_json("https://example.invalid/x", "http://tor:9080")
    assert "JSON" in str(fehler.value)


def test_die_antwort_wird_gedeckelt(monkeypatch):
    """Eine Gegenstelle, die endlos sendet, darf den Arbeitsspeicher nicht
    fuellen."""
    o = _oeffner_ersetzen(monkeypatch, _Antwort(b'{"last": "1"}'))
    K._hole_json("https://example.invalid/x", "http://tor:9080")
    assert o._ergebnis.gelesen == K.HOECHSTLAENGE


def test_der_proxy_wird_wirklich_gesetzt():
    """Ohne Proxy liefe die Abfrage im Klartext hinaus und verriete, dass
    hier jemand einen Knoten betreibt. Das ist die Regel des Moduls."""
    mit = [getattr(h, "proxies", None) for h in K._oeffner(
        "http://tor:9080").handlers if hasattr(h, "proxies")]
    assert mit == [{"https": "http://tor:9080", "http": "http://tor:9080"}]

    # Ohne Proxy baut build_opener gar keinen ProxyHandler ein -- ein leerer
    # wird verworfen. Wichtig ist, was NICHT passiert: ProxyHandler() ohne
    # Argument laese HTTP_PROXY aus der Umgebung und schickte die Abfrage
    # womoeglich an einer fremden Stelle vorbei. Das leere Dict verhindert das.
    ohne = [h for h in K._oeffner(None).handlers if hasattr(h, "proxies")]
    assert ohne == []


# --------------------------------------------- kaputte Antworten fallen weiter ---

def test_unerwartete_antwortform_wirft_nicht_sondern_fragt_weiter(monkeypatch):
    """Eine Boerse, die ihr Format aendert, darf den Kasten nicht leeren."""
    _antworten(monkeypatch, {
        "bitstamp.net": {"last": {"kein": "Skalar"}},
        "kraken.com": KRAKEN_TICKER,
    })
    werte, _ = K.hole_kurs("eur", "http://tor:9080")
    assert werte["boerse"] == "Kraken"


def test_kaputter_verlauf_fuehrt_zur_naechsten_quelle(monkeypatch):
    _antworten(monkeypatch, {
        "bitstamp.net": {"data": {"ohlc": "gar keine Liste"}},
        "kraken.com": KRAKEN_OHLC,
    })
    punkte, boerse = K.hole_verlauf("eur", "24h", "http://tor:9080")
    assert boerse == "Kraken" and len(punkte) == 2


def test_ohne_jeden_verlauf_gibt_es_einen_grund(monkeypatch):
    _antworten(monkeypatch, {
        "bitstamp.net": K.Abgewiesen("HTTP 403"),
        "kraken.com": K.Abgewiesen("HTTP 403"),
    })
    with pytest.raises(K.Abgewiesen) as fehler:
        K.hole_verlauf("eur", "24h", "http://tor:9080")
    assert "403" in str(fehler.value)


def test_kurs_da_verlauf_weg_meldet_trotzdem(monkeypatch):
    """Sonst stuende ein frischer Kurs ueber einem leeren Diagramm, ohne
    dass irgendwo steht, warum."""
    tafel, _ = _tafel(monkeypatch, KURSE)

    def verlauf_weg(w, zeitraum, proxy):
        raise K.Abgewiesen("Die Boerse weist uns ab (HTTP 429).")

    monkeypatch.setattr(K, "hole_verlauf", verlauf_weg)
    tafel.einmal_holen("eur")
    d = tafel.als_dict("eur")
    assert d["kurs"] == 67830.0
    assert d["verlauf"] == []
    assert "429" in d["grund"]


def test_kraken_ueberspringt_kerzen_die_keine_sind():
    """Eine zu kurze Kerze und eine ohne lesbaren Schlusskurs -- beide
    duerfen die Reihe nicht abbrechen, sondern fallen einzeln heraus."""
    roh = {"result": {"XXBTZEUR": [
        [1757336400, "1", "2"],                                     # zu kurz
        [1757340000, "1", "2", "0.5", "keine Zahl", "1", "1", 1],   # kein Kurs
        [1757343600, "1", "2", "0.5", "67830.0", "1", "1", 1],      # gut
    ], "last": 1757343600}}
    punkte = K._kraken_verlauf(roh)
    assert len(punkte) == 1
    assert punkte[0][0] == 1757343600 and punkte[0][1] == 67830.0


def test_eine_liste_statt_eines_objekts_reisst_nichts_mit(monkeypatch):
    """Der Fund vom 08.09.2026: liefert eine Boerse eine Liste, scheitert der
    Auswerter an `.get` -- mit AttributeError, nicht TypeError. Vorher flog
    der ungebremst durch und nahm den ganzen Abruf mit."""
    _antworten(monkeypatch, {
        "bitstamp.net": [{"last": "67830.00"}],     # Liste statt Objekt
        "kraken.com": KRAKEN_TICKER,
    })
    werte, _ = K.hole_kurs("eur", "http://tor:9080")
    assert werte["boerse"] == "Kraken"
    assert werte["kurs"] == 67830.0


def test_eine_quelle_ohne_verlauf_wird_uebersprungen(monkeypatch):
    """Coinbase liefert nur einen Kurs. Beim Verlauf muss sie stillschweigend
    ausgelassen werden, statt eine Ausnahme zu erzeugen."""
    ohne_verlauf = [b for b in K.BOERSEN if not b.verlauf_adresse]
    assert ohne_verlauf, "Der Fall soll geprueft werden, nicht wegfallen"
    _antworten(monkeypatch, {
        "bitstamp.net": K.Abgewiesen("HTTP 403"),
        "kraken.com": K.Abgewiesen("HTTP 403"),
    })
    with pytest.raises(K.Abgewiesen):
        K.hole_verlauf("eur", "24h", "http://tor:9080")


def test_die_zuletzt_erfolgreiche_boerse_wird_zuerst_gefragt(monkeypatch):
    """DER BEFUND VOM 17.09.2026: Bitstamp schickte Tor-Ausgaenge im Kreis.

    Der Rueckfall trug den Kasten -- aber jeder Abruf lief zuerst in die tote
    Quelle, und das ueber Tor, wo jeder Versuch einen Kreisaufbau kostet. Eine
    feste Rangfolge aus einer einmaligen Messung veraltet genau so. Wer
    zuletzt geliefert hat, wird deshalb zuerst gefragt.
    """
    gefragt = _antworten(monkeypatch, {
        "bitstamp.net": K.Abgewiesen("302 -- im Kreis"),
        "kraken.com": KRAKEN_TICKER,
    })

    werte, _ = K.hole_kurs("usd", "http://tor:9080")
    assert werte["boerse"] == "Kraken"
    assert "bitstamp.net" in gefragt[0], "erster Versuch war nicht die Liste"

    # Zweiter Abruf: Kraken zuerst, die tote Quelle gar nicht mehr.
    gefragt.clear()
    werte, _ = K.hole_kurs("usd", "http://tor:9080")
    assert werte["boerse"] == "Kraken"
    assert "kraken.com" in gefragt[0]
    assert not any("bitstamp.net" in a for a in gefragt), \
        "die tote Quelle wurde weiterhin zuerst gefragt"


def test_faellt_die_gemerkte_boerse_aus_geht_es_die_liste_entlang(monkeypatch):
    """Gemerkt heisst nicht festgenagelt -- sonst waere der naechste Ausfall
    derselbe Fehler mit anderem Namen."""
    _antworten(monkeypatch, {"kraken.com": KRAKEN_TICKER})
    assert K.hole_kurs("usd", "http://tor:9080")[0]["boerse"] == "Kraken"

    _antworten(monkeypatch, {"bitstamp.net": BITSTAMP_TICKER})
    assert K.hole_kurs("usd", "http://tor:9080")[0]["boerse"] == "Bitstamp"
    assert K._ZULETZT["kurs"] == "Bitstamp"
