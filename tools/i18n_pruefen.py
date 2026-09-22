#!/usr/bin/env python3
"""Prueft die Uebersetzungstabelle der Oberflaeche.

Fuenf Fehler, die alle schon vorgekommen sind:

1. Ein Schluessel steht nur in einer Sprache. In der anderen erscheint dann
   der rohe Schluessel im Text -- oder gar nichts.
2. Ein Schluessel steht ZWEIMAL im selben Block. In JavaScript gewinnt
   stillschweigend der letzte. Am 29.08.2026 sind so englische Texte im
   deutschen Block gelandet und haben die deutschen ueberschrieben.
3. Die Vorlage verweist ueber data-i18n auf einen Schluessel, den es nicht
   gibt. Die Stelle bleibt dann leer.
4. Der Code holt einen Schluessel, den es nicht gibt -- dann steht der rohe
   Schluessel in der Oberflaeche. So geschehen am 31.08.2026: beim
   Herausnehmen der Diagnose fielen die b_-Texte der Beitrags-Aufschluesselung
   mit weg, und in der Oberflaeche stand "b_bloecke".
5. Ein Schluessel wird nirgends mehr geholt. Kein Fehler, aber er bleibt
   sonst ewig liegen und muss bei jeder Aenderung mitgepflegt werden.

Zu Punkt 4 und 5 gehoert eine Einsicht, die einen ersten Anlauf am 01.09.2026
unbrauchbar gemacht hat: die Oberflaeche holt Texte auf MEHR Wegen als t().
Sie stehen in data-i18n und data-i18n-html, in Datentabellen
(["8333", "n_p_btc"]), in setzeHinweis("d_note_sync"), und das Backend
schickt sie als Meldung oder als Text einer Ausnahme. Wer nur t() sucht,
erklaert vierzig lebende Schluessel fuer tot.

Daraus die Aufteilung:

* STRENG wird geprueft, was sicher ein Schluessel ist -- t("..."), die
  Vorlage, die bekannten Meldungsformen des Backends. Fehlt dazu ein Text,
  ist das ein Fehler.
* GROSSZUEGIG wird geprueft, ob ein Schluessel noch gebraucht wird: sein Name
  muss irgendwo als Zeichenkette auftauchen. Das zaehlt lieber einen zu viel
  als einen zu wenig -- ein faelschlich geloeschter Text ist teurer als ein
  faelschlich behaltener.
"""
from __future__ import annotations

import pathlib
import re
import sys

WURZEL = pathlib.Path(__file__).resolve().parents[1]
JS = WURZEL / "app" / "web" / "app.js"
HTML = WURZEL / "app" / "web" / "index.html"
BACKEND = WURZEL / "app" / "backend" / "satcortex"

# Mehrere Schluessel duerfen in einer Zeile stehen ("back: ..., next: ...").
_SCHLUESSEL = re.compile(r'(?:^|,)\s*([a-z_][a-z0-9_]*):\s*"', re.M)
# Zeichenketten wegnehmen, bevor nach Schluesseln gesucht wird. Sonst wuerde
# ein Text, in dem zufaellig ', wort: "' vorkommt, als Schluessel gezaehlt.
_TEXT = re.compile(r'"(?:[^"\\]|\\.)*"')
# Wie ein Schluessel aussieht, wenn er als Zeichenkette dasteht.
_ALS_TEXT = re.compile(r'"([a-z_][a-z0-9_]*)"')

# Schluessel, die der Code erst zur Laufzeit zusammensetzt: t("b_" + k) findet
# keine Textsuche. Links steht der Ausdruck, wie er im Code steht, rechts, was
# dabei herauskommen kann. Der Ausdruck steht mit in der Tabelle, damit eine
# NEUE solche Stelle nicht stillschweigend ungeprueft bleibt -- taucht unten
# ein t(...) auf, das hier fehlt, meldet die Pruefung das.
ZUSAMMENGESETZT = {
    # Die Kopfzeile der Wegwissen-Tafel wird ueber eine Schluesselliste
    # gebaut -- fuenf Spalten, fuenf Texte. Befund vom 22.09.2026.
    "t(k)": ["wg_von", "wg_nach", "wg_trug", "wg_fehl", "wg_wann"],
    # Was ein Geldweg meldet, wenn KEIN Bescheid kam -- der Abbruch der
    # Oberflaeche oder das 504 des Servers. Entweder nennt der Server den
    # Schluessel selbst, oder es gilt der, den der Aufrufer mitgibt: fuer
    # jede der drei Arten ein eigener, denn "in den Kanaelen nachsehen" waere
    # bei einer Ueberweisung falsch. Befund vom 22.09.2026.
    't(d.meldung || unklar, d)': [
        "zahlung_unklar", "sendung_unklar", "kanal_unklar"],
    # Uebersetzbare ATTRIBUTE. applyI18n liest den Schluessel aus
    # data-i18n-attr und schickt ihn durch dieselbe Weiche wie alles andere.
    # Welche dort ankommen, steht in der Vorlage und wird von dort auch
    # eingesammelt -- hier stehen sie, damit eine neue Stelle auffaellt.
    't(schluessel.trim())': ["nav_abschnitte", "lang_wahl"],
    # Welcher Dienst in der Erreichbarkeitspruefung gemessen wurde. Bitcoin
    # bekommt keinen eigenen Namen -- das ist der Knoten selbst.
    't("pr_dienst_" + a.dienst)': ["pr_dienst_lightning", "pr_dienst_wachturm"],
    # Die drei Wege, auf denen eine Wallet nach einem Neustart wieder aufgeht.
    # Kommt einer dazu, faellt es hier auf statt in der Oberflaeche als leerer
    # Kasten unter einer Wahl, die eine Sicherheitsentscheidung ist.
    't("wl_weg_folge_" + weg)': [
        "wl_weg_folge_aus", "wl_weg_folge_merken", "wl_weg_folge_datei"],
    't("wl_weg_folge_" + ziel)': [
        "wl_weg_folge_aus", "wl_weg_folge_merken", "wl_weg_folge_datei"],
    # Was auf diesem Geraet WIRKLICH eingerichtet ist -- im Kasten zum
    # Wechseln.
    't("ew_jetzt_" + ENTSPERRWEG)': [
        "ew_jetzt_aus", "ew_jetzt_merken", "ew_jetzt_datei"],
    # Warum unter "Deine Verbindungsadresse" nichts steht. Drei Betriebsarten,
    # drei verschiedene naechste Schritte -- plus der Fall, dass die Antwort
    # die Betriebsart (noch) nicht mitbringt.
    't(grund)': [
        "lgi_keine_still", "lgi_keine_tor", "lgi_keine_hybrid",
        "lgi_keine_unklar", "lgi_keine_beschaeftigt"],
    # Warum die Netzgebuehren gerade nicht gemessen werden konnten. Die
    # Meldung kommt aus dem Backend und wird dort auch gesetzt -- kommt eine
    # vierte dazu, faellt es hier auf statt als roher Schluessel unter der
    # Zahl, an der jemand seine Gebuehren festmacht.
    't(d.fehler)': ["graph_nicht_aktuell", "graph_leer",
                    "messung_fehlgeschlagen"],
    # Was die Gebuehrenautomatik zuletzt getan hat -- oder warum nicht.
    't(GRUENDE[rat.grund], { satz: rat.satz_ppm || 0 })': [
        "gb_a_median", "gb_a_gedeckelt", "gb_a_angehoben",
        "gb_a_unveraendert", "gb_a_sammelt", "gb_a_keine_messung",
        "gb_a_keine_kanaele"],
    # Guenstig, normal oder teuer -- gemessen an der eigenen letzten Woche.
    # Kommt eine vierte Lage dazu, faellt es hier auf statt als leerer Hinweis
    # unter einer Zahl, an der jemand seinen ersten Kanal festmacht.
    't(schluessel, werte)': [
        "kk_lage_guenstig", "kk_lage_normal", "kk_lage_teuer"],
    # Wie eine Anmeldung ueber den Ausweisdienst ausgegangen ist. Kommt als
    # Frage in der Adresse zurueck ("/?anmeldung=abgelehnt").
    't(bekannt.includes(grund) ? "g_oidc_" + grund : "g_oidc_ungueltig")': [
        "g_oidc_abgelehnt", "g_oidc_abgelaufen", "g_oidc_ungueltig"],
    # Die vier Arten von HTLC-Ereignis. Kommt eine dazu, faellt es hier auf
    # statt in der Oberflaeche als leere Zeile.
    't("ht_a_" + e.art)': [
        "ht_a_weiterleiten", "ht_a_erledigt", "ht_a_fehl", "ht_a_link_fehl"],
    # Die Fehlergruende, die wir uebersetzen. Alles andere zeigt die
    # Oberflaeche unveraendert -- LNDs Name ist besser als ein leeres Feld.
    't("ht_g_" + grund.toLowerCase())': [
        "ht_g_insufficient_balance", "ht_g_htlc_exceeds_max",
        "ht_g_fee_insufficient", "ht_g_expiry_too_soon",
        "ht_g_invalid_keysend", "ht_g_channel_disabled"],
    # Was jetzt zu tun ist -- die Faelle aus naechster_schritt() in api.py.
    # Kommt dort einer dazu, faellt es hier auf, statt in der Oberflaeche
    # als leere Zeile zu enden.
    't("tun_" + schritt.was)': [
        "tun_wallet_anlegen", "tun_wallet_entsperren", "tun_sicherungsziel",
        "tun_wachturm"],
    't("tun_" + schritt.was + "_knopf")': [
        "tun_wallet_anlegen_knopf", "tun_wallet_entsperren_knopf",
        "tun_sicherungsziel_knopf", "tun_wachturm_knopf"],
    # Assistenten-Schritte, Endungen aus SCHRITTE in app.js
    't("st_" + name)': [
        "st_" + n for n in
        # Genau die Liste SCHRITTE aus app.js. "wallet" fehlte hier, und
        # damit galt st_wallet als toter Schluessel -- wer dem Rat gefolgt
        # waere und ihn entfernt haette, haette dem Assistenten den
        # Wallet-Schritt namenlos gemacht.
        ("willkommen", "speicher", "leistung", "netz", "wallet",
         "konto", "fertig")],
    # Leistungsprofil, Endungen aus zeichneProfile()
    't("l_" + S.profil)': ["l_sparsam", "l_mittel", "l_voll"],
    # dieselben drei, einmal als Titel und einmal als Beschreibung
    "t(label)": ["l_sparsam", "l_mittel", "l_voll"],
    't(label + "_d")': ["l_sparsam_d", "l_mittel_d", "l_voll_d"],
    # Dienst-Zustaende, Endungen aus Zustand in services.py
    't("sv_" + dienst.zustand)': [
        "sv_unkonfiguriert", "sv_wartet", "sv_freigegeben"],
    't("ln_d_" + ((d.dienst || {}).zustand || "unkonfiguriert"))': [
        "ln_d_unkonfiguriert", "ln_d_wartet", "ln_d_freigegeben"],
    # Wallet-Stand, Endungen aus ZUSTAENDE in lnd.py plus "aus"/"unbekannt"
    't("ln_w_" + ((d.knoten || {}).stand || "aus"))': [
        "ln_w_" + n for n in
        ("aus", "keine_wallet", "gesperrt", "startet", "bereit", "wartet",
         "unbekannt")],
    # Beitrags-Aufschluesselung, Endungen aus BEITRAG_ARTEN in app.js
    't("b_" + k)': [
        "b_" + n for n in
        ("bloecke", "transaktionen", "filter", "kopfzeilen", "adressen",
         "rest")],
    # Grund, warum die Erreichbarkeit nicht geprueft werden kann; die drei
    # Werte stehen direkt ueber dem Aufruf in derselben Bedingung
    't("pr_" + d.grund)': [
        "pr_keine_adresse", "pr_tor_aus", "pr_nicht_aufloesbar"],
    # Sichtbarkeit, Endungen aus Literal["tor","hybrid","still"] in api.py
    't("lnsicht_" + S.sichtbarkeit)': [
        "lnsicht_tor", "lnsicht_hybrid", "lnsicht_still"],
    # Urteil ueber die Kanalkosten; die drei Schwellen stehen direkt ueber
    # dem Aufruf in derselben Zeile
    "t(schluessel, { p: nachkomma(p, 2) })": [
        "kk_teuer", "kk_spuerbar", "kk_guenstig"],
    # Schlusssatz des Wallet-Ablaufs, eine Zeile ueber dem Aufruf gesetzt
    "t(schluss.dataset.i18n)": ["wl_fertig_auto", "wl_fertig_hand"],
    # Wege zu Gegenstellen, Schluessel aus GEGENSTELLEN_WEGE in app.js
    "t(w.schluessel)": ["lgw_amboss", "lgw_lnplus", "lgw_1ml"],
    # Zeitfenster des Kursbildes, Endungen aus ZEITRAEUME in kurs.py
    't("kf_" + z)': ["kf_24h", "kf_30t", "kf_1j", "kf_5j"],
    # Warum der Tor-Weg nicht gemessen wurde; beide Werte setzt
    # erreichbarkeit_pruefen() in api.py
    't("pr_" + d.tor_hinweis)': ["pr_tor_pausiert", "pr_keine_onion"],
    # Was der Pausenschalter gerade bewirkt; die vier Werte stehen
    # unmittelbar ueber dem Aufruf in ladeEinstellungen()
    "t(folge)": ["wege_pause_laeuft", "wege_pause_fertig",
                 "wege_pause_wartet", "wege_pause_aus"],
    # Ergebnis des Erreichbarkeitstests, Gruende aus erreichbar.py.
    # ("nicht_pruefbar" fehlt mit Absicht -- der kommt immer mit
    #  geprueft=False, und dann zeigt die Oberflaeche pr_unklar.)
    't(schluessel, { adresse: a.adresse, port: a.port, kennung: a.kennung '
    '|| "", grund: a.einzelheit || "", })': [
        "pr_ja", "pr_unklar", "pr_unklar_onion", "pr_keine_antwort",
        "pr_abgelehnt", "pr_kein_handschlag", "pr_kein_knoten"],
    # Warum die Kanalsicherung zuletzt nicht abgelegt wurde. Kennt die
    # Anwendung den Fall, liegt ein Schluessel in der Ablage: die Faelle aus
    # sicherung_hochladen() in api.py und DEUTUNG_BEIM_ABLEGEN in
    # sicherung.py. Alles andere zeigt die Oberflaeche im Wortlaut des Servers.
    't(stand.fehler)': [
        "kein_ziel", "kein_passwort", "ziel_anmeldung_abgelehnt",
        "ziel_verweigert", "ziel_adresse_unbekannt", "ziel_ordner_fehlt"],
    # Die drei Sitzungsarten eines Wachturms -- PolicyType aus wtclient.proto,
    # in lnd.py als _SITZUNGSARTEN. Kommt eine vierte dazu, faellt es hier
    # auf statt als roher Schluessel neben einem Turm.
    't("wt_art_" + String(art).toLowerCase())': [
        "wt_art_legacy", "wt_art_anchor", "wt_art_taproot"],
    # Die drei Fenster der Pool-Anteile -- POOL_FENSTER in api.py.
    't("a_pa_" + fenster)': ["a_pa_144", "a_pa_1008", "a_pa_0"],
    # Wie ein Adress-Scan geendet hat, wenn nicht mit einem Ergebnis --
    # adresse_scannen() in api.py.
    't(d.fehler, { grund: d.grund || "" })': [
        "a_ad_fehler", "a_ad_abgebrochen", "scan_belegt"],
    # ---- Durchreichen: der Schluessel kommt vom Aufrufer.
    # Diese Stellen erfinden keinen Schluessel, sie geben einen weiter. Wer
    # sie aufruft, schreibt ihn hin -- und dort wird er geprueft.
    "t(key)": [],
    "t(name)": [],
    "t(m)": [],
    "t(schluessel)": [],
    "t(fehlerschluessel)": ["rq_qr_zu_lang"],
    "t(schluessel, { mindestens: PASSWORT_MIN, ...(d || {}) })": [],
    # Der allgemeine Uebersetzer fuer die Vorlage; seine Schluessel stehen in
    # den data-i18n-Attributen und werden dort geprueft.
    "t(el.dataset.i18n)": [],
    "t(el.dataset.i18nHtml)": [],
    # ---- Meldungen aus dem Backend, siehe backend_meldungen().
    "t(d.meldung)": [],
    "t(d.meldung, d)": [],
    "t(f.meldung, f)": [],
    "t(d.meldung, { mindestens: PASSWORT_MIN, ...d })": [],
    "t(d.meldung_gleiche_platte)": [],
    "t(d.meldung_upload, { upload_gb: d.upload_gb })": [],
    "t(p.meldung, p.werte)": [],
}

# Meldungen, die zwar so heissen, aber nie als Text in der Oberflaeche landen.
NICHT_ANGEZEIGT = {
    "abgeschlossen",     # Erfolgsmeldung der Einrichtung; ausgewertet wird "ok"
    "unbekannt",         # 404 auf einen unbekannten API-Pfad
    # Diese beiden bildet die Oberflaeche auf eigene, ausfuehrlichere Texte ab:
    #   t(meldung === "keine_txid" ? "a_keine_txid" : "a_tx_unbekannt")
    "keine_txid", "tx_unbekannt",
}

# Wie das Backend einen Schluessel nach vorn gibt. Drei Formen, alle im Einsatz:
#   {"meldung": "passwort_zu_kurz"}      als Feld einer Antwort
#   meldung="pfad_fehlt"                 als Argument
#   raise ValueError("benutzer_ungueltig")   der Text der Ausnahme wird in
#       api.py zu {"meldung": str(f)} -- ohne Leerzeichen ist es ein
#       Schluessel, mit Leerzeichen ein Satz fuer das Protokoll.
_MELDUNGSFORMEN = (
    re.compile(r'"(?:meldung|meldung_upload|meldung_gleiche_platte)"\s*:\s*"'
               r'([a-z_][a-z0-9_]*)"'),
    re.compile(r'\bmeldung(?:_upload|_gleiche_platte)?\s*=\s*"'
               r'([a-z_][a-z0-9_]*)"'),
    re.compile(r'raise\s+(?:ValueError|PermissionError)\(\s*"'
               r'([a-z_][a-z0-9_]*)"\s*\)'),
)


def sprachbloecke(text: str) -> dict:
    """Die Schluessel je Sprache, in der Reihenfolge ihres Auftretens."""
    anfang = text.index("const I18N = {")
    grenzen = {s: text.index(f"\n  {s}: {{\n", anfang) for s in ("de", "en")}
    ende = text.index("\n};", grenzen["en"])
    abschnitte = {"de": text[grenzen["de"]:grenzen["en"]],
                  "en": text[grenzen["en"]:ende]}
    return {s: _SCHLUESSEL.findall(_TEXT.sub('""', a))
            for s, a in abschnitte.items()}


# Fuenf Fehler, die die Vollstaendigkeitspruefung NICHT sieht -- sie zaehlt
# Schluessel, nicht Inhalte. Am 10.09.2026 nachgeruestet, nachdem der Betreiber um
# eine saubere Uebersetzung "in allen Kategorien und Menuefenstern" gebeten
# hat und die Suche danach genau diese Klassen zutage gefoerdert hat.
_PLATZHALTER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_UMLAUT = re.compile(r"[\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]")
_DEUTSCHE_WOERTER = re.compile(
    r"\b(der|die|das|und|nicht|wird|kann|dein|deine|einen|eine|nach|noch|"
    r"schon|auch|dann|damit|wenn|weil|aber|sich|ist|sind|hat|haben|man|mit|"
    r"von|zum|zur)\b", re.I)


def _werte(text: str, sprache: str) -> dict:
    """Die Texte einer Sprache -- Schluessel auf Zeichenkette.

    Bewusst mit einer groben Zerlegung statt mit node: die Pruefung soll
    ohne node laufen, und fuer die Fragen hier genuegt der Rohtext.
    """
    anfang = text.index("const I18N = {")
    grenzen = {s: text.index(f"\n  {s}: {{\n", anfang) for s in ("de", "en")}
    ende = text.index("\n};", grenzen["en"])
    block = (text[grenzen["de"]:grenzen["en"]] if sprache == "de"
             else text[grenzen["en"]:ende])
    raus = {}
    for zeile in block.split("\n"):
        treffer = re.match(r'\s*([a-z_][a-z0-9_]*):\s*"(.*)",?\s*$', zeile)
        if treffer:
            raus[treffer.group(1)] = treffer.group(2)
    return raus


def inhaltliche_fehler(text: str) -> list:
    """Was die Zaehlung uebersieht: Inhalte, die nicht zueinander passen."""
    de, en = _werte(text, "de"), _werte(text, "en")
    fehler = []

    # 1. Platzhalter, die auseinanderlaufen. Der teuerste Fall: eine Sprache
    #    setzt einen Wert ein, die andere zeigt schlicht nichts.
    drift = []
    for k in sorted(set(de) & set(en)):
        a = set(_PLATZHALTER.findall(de[k]))
        b = set(_PLATZHALTER.findall(en[k]))
        if a != b:
            drift.append(f"{k} (de={sorted(a)}, en={sorted(b)})")
    if drift:
        fehler.append("Platzhalter laufen auseinander: " + ", ".join(drift))

    # 2. Deutsch im englischen Block. Kam vor, als englische Texte in den
    #    falschen Block gerieten -- und faellt sonst niemandem auf, der die
    #    Oberflaeche auf Deutsch benutzt.
    deutsch = [k for k in sorted(en)
               if _UMLAUT.search(en[k])
               or len(_DEUTSCHE_WOERTER.findall(en[k])) >= 2]
    if deutsch:
        fehler.append("englischer Text sieht deutsch aus: "
                      + ", ".join(deutsch))

    # 3. Gerade Anfuehrungszeichen. Das Haus schreibt typografisch --
    #    \u201e...\u201c im Deutschen, \u201c...\u201d im Englischen. Gemischt sieht
    #    schlampig aus, und in JavaScript muss das gerade Zeichen ausserdem
    #    maskiert werden.
    gerade = [k for k, w in list(de.items()) + list(en.items()) if '\\"' in w]
    if gerade:
        fehler.append("gerade Anfuehrungszeichen statt typografischer: "
                      + ", ".join(sorted(set(gerade))))

    # 4. Der Apostroph. Dreissig englische Texte schreiben ihn gerade, einer
    #    schrieb ihn typografisch -- das faellt niemandem auf und sieht doch
    #    aus wie zwei verschiedene Haende. Eine Form, und zwar die haeufigere.
    # Beide Schreibweisen: das Zeichen selbst und seine maskierte Form.
    # Genau daran ist ein erster Anlauf gescheitert -- der eine Ausreisser
    # stand als \\u2019 in der Datei und blieb dadurch unsichtbar.
    schief = [k for k, w in list(de.items()) + list(en.items())
              if "\u2019" in w or "\\u2019" in w]
    if schief:
        fehler.append("typografischer Apostroph statt geradem: "
                      + ", ".join(sorted(set(schief))))
    return fehler


def ohne_tabelle(text: str) -> str:
    """Der Code ohne die Uebersetzungstabelle."""
    anfang = text.index("const I18N = {")
    ende = text.index("\n};", text.index("\n  en: {\n", anfang))
    return text[:anfang] + text[ende:]


def _ausserhalb(ausdruck: str, zeichen: str):
    """Stellen, an denen `zeichen` weder geklammert noch in einem Text steht."""
    tiefe, i = 0, 0
    while i < len(ausdruck):
        z = ausdruck[i]
        if z in "\"'`":
            i += 1
            while i < len(ausdruck) and ausdruck[i] != z:
                i += 2 if ausdruck[i] == "\\" else 1
        elif z in "({[":
            tiefe += 1
        elif z in ")}]":
            tiefe -= 1
        elif z == zeichen and tiefe == 0:
            yield i
        i += 1


def _erstes_argument(ausdruck: str) -> str:
    for stelle in _ausserhalb(ausdruck, ","):
        return ausdruck[:stelle]
    return ausdruck


def _nach_frage(ausdruck: str) -> str:
    """Bei "bedingung ? a : b" zaehlen nur die Zweige.

    Sonst wuerde die Zeichenkette in der BEDINGUNG als Schluessel gelesen --
    etwa "keine_txid" in t(meldung === "keine_txid" ? "a_keine_txid" : ...).
    """
    for stelle in _ausserhalb(ausdruck, "?"):
        return ausdruck[stelle + 1:]
    return ausdruck


def t_aufrufe(text: str) -> tuple:
    """Jedes t(...) im Code, getrennt nach lesbar und undurchsichtig.

    Klammern von Hand zaehlen statt mit einem regulaeren Ausdruck: die
    Argumente enthalten selbst Klammern und Zeichenketten, und daran scheitert
    jede Suche, die nur bis zur naechsten schliessenden Klammer liest.
    """
    lesbar, undurchsichtig = set(), set()
    for treffer in re.finditer(r"(?<![\w.$])t\(", text):
        i = treffer.end()
        tiefe, anfang = 1, i
        while i < len(text) and tiefe:
            z = text[i]
            if z in "\"'`":
                i += 1
                while i < len(text) and text[i] != z:
                    i += 2 if text[i] == "\\" else 1
            elif z == "(":
                tiefe += 1
            elif z == ")":
                tiefe -= 1
            i += 1
        ausdruck = text[anfang:i - 1].strip()
        erstes = _nach_frage(_erstes_argument(ausdruck))
        # Ein "+" heisst zusammengesetzt: aus "b_" und k wird erst zur Laufzeit
        # ein Schluessel; das Bruchstueck "b_" ist keiner.
        gefunden = [] if any(True for _ in _ausserhalb(erstes, "+")) \
            else _ALS_TEXT.findall(erstes)
        if gefunden:
            lesbar.update(gefunden)
        else:
            undurchsichtig.add("t(%s)" % " ".join(ausdruck.split()))
    return lesbar, undurchsichtig


def backend_meldungen() -> set:
    gefunden = set()
    for datei in sorted(BACKEND.glob("*.py")):
        quelle = datei.read_text(encoding="utf-8")
        for form in _MELDUNGSFORMEN:
            gefunden.update(form.findall(quelle))
    return gefunden - NICHT_ANGEZEIGT


def irgendwo_erwaehnt(js_ohne_tabelle: str) -> set:
    """Jeder Name, der IRGENDWO als Zeichenkette dasteht.

    Grob mit Absicht. Fuer die Frage "wird der Text noch gebraucht?" ist ein
    faelschlich behaltener Schluessel harmlos, ein faelschlich geloeschter
    nicht -- und die Oberflaeche holt Texte auf zu vielen Wegen, als dass eine
    genaue Suche sie alle faende.
    """
    namen = set(_ALS_TEXT.findall(js_ohne_tabelle))
    namen.update(re.findall(r'data-i18n-attr="[^"]*?=\s*([a-z_][a-z0-9_]*)',
                            HTML.read_text(encoding="utf-8")))
    namen.update(re.findall(r'data-i18n(?:-html)?="([a-z_][a-z0-9_]*)"',
                            HTML.read_text(encoding="utf-8")))
    for datei in sorted(BACKEND.glob("*.py")):
        namen.update(_ALS_TEXT.findall(datei.read_text(encoding="utf-8")))
    return namen


def main() -> int:
    text = JS.read_text(encoding="utf-8")
    je_sprache = sprachbloecke(text)
    fehler = []

    for sprache, schluessel in je_sprache.items():
        doppelt = sorted({k for k in schluessel if schluessel.count(k) > 1})
        if doppelt:
            fehler.append(f"{sprache}: doppelt vergeben -- {', '.join(doppelt)}")

    fehler.extend(inhaltliche_fehler(text))

    de, en = set(je_sprache["de"]), set(je_sprache["en"])
    if de - en:
        fehler.append("fehlt in en: " + ", ".join(sorted(de - en)))
    if en - de:
        fehler.append("fehlt in de: " + ", ".join(sorted(en - de)))

    # data-i18n, data-i18n-html UND data-i18n-attr. Der dritte kam am
    # 10.09.2026 dazu: aria-label stand in beiden Sprachen fest verdrahtet
    # da, und ein Vorleser las einem englischen Nutzer "Abschnitte" vor.
    aus_vorlage = set(re.findall(
        r'data-i18n-attr="[^"]*?=\s*([a-z_][a-z0-9_]*)',
        HTML.read_text(encoding="utf-8")))
    aus_vorlage |= set(re.findall(r'data-i18n(?:-html)?="([a-z_][a-z0-9_]*)"',
                                 HTML.read_text(encoding="utf-8")))
    if aus_vorlage - de:
        fehler.append("in der Vorlage benutzt, aber nirgends uebersetzt: "
                      + ", ".join(sorted(aus_vorlage - de)))

    rumpf = ohne_tabelle(text)
    fest, undurchsichtig = t_aufrufe(rumpf)
    if fest - de:
        fehler.append("im Code mit t() geholt, aber nirgends uebersetzt: "
                      + ", ".join(sorted(fest - de)))

    unbekannt = undurchsichtig - set(ZUSAMMENGESETZT)
    if unbekannt:
        fehler.append(
            "zusammengesetzte Schluessel ohne Eintrag in ZUSAMMENGESETZT "
            "(dort die moeglichen Schluessel eintragen): "
            + " | ".join(sorted(unbekannt)))
    verschwunden = set(ZUSAMMENGESETZT) - undurchsichtig
    if verschwunden:
        fehler.append("steht in ZUSAMMENGESETZT, aber nicht mehr im Code -- "
                      "Eintrag entfernen: " + " | ".join(sorted(verschwunden)))

    aus_tabelle = {k for liste in ZUSAMMENGESETZT.values() for k in liste}
    if aus_tabelle - de:
        fehler.append("zur Laufzeit zusammengesetzt, aber nirgends "
                      "uebersetzt: " + ", ".join(sorted(aus_tabelle - de)))

    aus_backend = backend_meldungen()
    if aus_backend - de:
        fehler.append("vom Backend als Meldung geschickt, aber nirgends "
                      "uebersetzt: " + ", ".join(sorted(aus_backend - de)))

    if fehler:
        print("Uebersetzungstabelle:")
        for f in fehler:
            print("  FEHLER:", f)
        return 1

    benutzt = fest | aus_vorlage | aus_tabelle | aus_backend
    # Zur Laufzeit zusammengesetzte Schluessel stehen NIRGENDS als
    # ganze Zeichenkette -- aus "b_" und k wird erst im Browser
    # "b_bloecke". Ohne diese Zeile erklaerte die Suche sie fuer tot.
    ungenutzt = sorted(de - irgendwo_erwaehnt(rumpf) - aus_tabelle)
    print(f"Uebersetzungstabelle in Ordnung: {len(de)} Schluessel, "
          "beide Sprachen vollstaendig, keine Doppelten, "
          f"alle {len(benutzt)} sicher benutzten vorhanden.")
    if ungenutzt:
        print(f"  FEHLER: {len(ungenutzt)} Schluessel kommen im ganzen "
              "Projekt nicht mehr vor -- entfernen: " + ", ".join(ungenutzt))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
