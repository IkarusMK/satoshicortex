"""Die Kartendaten -- aus dem, was der eigene Knoten weiss.

Kein Explorer, kein fremder Dienst: das Adressbuch des Knotens, seine
Gegenstellen, und eine Ortstabelle, die im Abbild liegt.
"""
from collections import Counter

from satcortex import karte, rpc


class Attrappe(rpc.Knoten):
    """Ein Knoten, der vorgegebene Antworten liefert."""

    def __init__(self, antworten, scheitern=()):
        super().__init__()
        self.antworten = antworten
        self.scheitern = scheitern
        self.aufrufe = []

    def ruf(self, methode, *params, zeitlimit=None):
        self.aufrufe.append((methode, params, zeitlimit))
        if methode in self.scheitern:
            raise rpc.NichtErreichbar("Attrappe")
        wert = self.antworten.get(methode)
        return wert(*params) if callable(wert) else wert


class Tabelle:
    stand = "2026-08"

    def __init__(self, zuordnung, gebiete=None):
        self.zuordnung = zuordnung
        # Wo nichts steht, gibt es kein Gebiet -- genau wie bei einer
        # Adresse, deren Regionsname der Zuordnung unbekannt ist.
        self.gebiete = gebiete or {}

    def ort(self, adresse):
        land = self.zuordnung.get(adresse)
        return land, (self.gebiete.get(adresse, 0) if land else 0)

    def land(self, adresse):
        return self.ort(adresse)[0]


ADRESSBUCH = {
    "ipv4": [{"address": "1.0.0.1", "network": "ipv4"},
             {"address": "84.134.0.1", "network": "ipv4"},
             {"address": "84.134.0.2", "network": "ipv4"},
             {"address": "9.9.9.9", "network": "ipv4"}],       # ohne Land
    "ipv6": [{"address": "2a02:8071::1", "network": "ipv6"}],
}

ORTE = Tabelle({
    "1.0.0.1": "AU", "84.134.0.1": "DE", "84.134.0.2": "DE",
    "2a02:8071::1": "DE", "203.0.113.7": "JP",
    "84.134.0.9": "DE", "198.51.100.4": "CH",
})


def _knoten(**mehr):
    antworten = {
        "getaddrmaninfo": {
            "ipv4": {"new": 40000, "tried": 8000, "total": 48000},
            "ipv6": {"new": 5000, "tried": 900, "total": 5900},
            "onion": {"new": 3000, "tried": 400, "total": 3400},
            "i2p": {"new": 10, "tried": 2, "total": 12},
            "cjdns": {"new": 1, "tried": 0, "total": 1},
            "all_networks": {"new": 48011, "tried": 9302, "total": 57313},
        },
        "getnodeaddresses": lambda anzahl, netz: ADRESSBUCH.get(netz, []),
        # Was der Knoten fuer seine eigene Adresse haelt. Die Onion-Adresse
        # steht bewusst mit dem hoechsten Wert vorn: sie hat keinen Ort, und
        # die Suche muss darueber hinweggehen statt aufzugeben.
        "getnetworkinfo": {"localaddresses": [
            {"address": "abcdef.onion", "port": 8333, "score": 12},
            {"address": "84.134.0.9", "port": 8333, "score": 7},
            {"address": "1.0.0.1", "port": 8333, "score": 2},
        ]},
        "getpeerinfo": [
            {"addr": "84.134.0.1:8333", "inbound": False, "network": "ipv4"},
            {"addr": "[2a02:8071::1]:8333", "inbound": False, "network": "ipv6"},
            {"addr": "203.0.113.7:8333", "inbound": True, "network": "ipv4"},
            {"addr": "abc.onion:8333", "inbound": True, "network": "onion"},
        ],
    }
    antworten.update(mehr)
    return Attrappe(antworten)


def test_laender_werden_gezaehlt():
    d = karte.sammle(_knoten(), ORTE)
    nach_land = {e["land"]: e for e in d["laender"]}
    assert nach_land["DE"]["adressen"] == 3          # 2x IPv4, 1x IPv6
    assert nach_land["AU"]["adressen"] == 1
    assert nach_land["DE"]["peers"] == 2


def test_ortlose_netze_werden_nicht_abgefragt():
    """Onion, I2P und CJDNS haben keinen Ort -- ihre Adressen zu holen waere
    Last fuer nichts. Ihre Anzahl steht schon in getaddrmaninfo."""
    k = _knoten()
    karte.sammle(k, ORTE)
    gefragte_netze = [p[1] for m, p, _ in k.aufrufe if m == "getnodeaddresses"]
    assert gefragte_netze == ["ipv4", "ipv6"]
    assert "onion" not in gefragte_netze


def test_ortlose_werden_gezaehlt_statt_verschwiegen():
    """Der leere Teil der Karte ist eine Aussage, kein Fehlen von Daten."""
    d = karte.sammle(_knoten(), ORTE)
    assert d["ortlos"] == 3400 + 12 + 1
    assert d["bekannt"]["all_networks"] == 57313


def test_abdeckung_wird_mitgeliefert():
    """Ohne diese Zahlen stuende auf der Karte eine Verteilung, von der
    niemand weiss, wie viel sie abdeckt."""
    d = karte.sammle(_knoten(), ORTE)
    assert d["angesehen"] == 5           # vier IPv4 plus eine IPv6
    assert d["verortet"] == 4            # 9.9.9.9 kennt die Tabelle nicht
    # Wie viele ueberhaupt einen Ort haben KOENNTEN -- ohne das laesst sich
    # "angesehen" nicht einordnen.
    assert d["verortbar"] == 48000 + 5900


def test_es_wird_gefragt_was_der_knoten_wirklich_hat():
    """Vorher stand hier ein fester Deckel von 20.000 je Netz. Am 27.08.2026
    hat er am echten Knoten gegriffen -- 42.812 Adressen, 25.870 angesehen --
    und die Anzeige sagte kein Wort dazu. Jetzt wird gefragt, was
    getaddrmaninfo meldet."""
    k = _knoten()
    karte.sammle(k, ORTE)
    gefragt = {p[1]: p[0] for m, p, _ in k.aufrufe if m == "getnodeaddresses"}
    assert gefragt == {"ipv4": 48000, "ipv6": 5900}


def test_die_obergrenze_bleibt_als_notbremse():
    """Ein Adressbuch kann nicht beliebig gross werden, aber eine kaputte
    Antwort schon. Nach oben muss eine Grenze stehen."""
    riesig = {"getaddrmaninfo": {
        "ipv4": {"new": 0, "tried": 0, "total": 999999},
        "all_networks": {"new": 0, "tried": 0, "total": 999999},
    }}
    k = _knoten(**riesig)
    karte.sammle(k, ORTE)
    gefragt = [p[0] for m, p, _ in k.aufrufe if m == "getnodeaddresses"]
    assert gefragt == [karte.OBERGRENZE_JE_NETZ]


def test_je_netz_wird_aufgeschluesselt():
    """Damit sichtbar ist, WARUM angesehen und Adressbuch auseinanderliegen --
    und nicht nur, DASS sie es tun."""
    d = karte.sammle(_knoten(), ORTE)["je_netz"]
    assert d["ipv4"] == {"bekannt": 48000, "gefragt": 48000,
                         "gesehen": 4, "verortet": 3}
    assert d["ipv6"] == {"bekannt": 5900, "gefragt": 5900,
                         "gesehen": 1, "verortet": 1}


def test_peers_nach_richtung():
    d = karte.sammle(_knoten(), ORTE)["peers"]
    assert d["gesamt"] == 4
    assert d["aufgebaut"] == 2
    assert d["angenommen"] == 2
    assert d["verortet"] == 3            # die Onion-Gegenstelle hat keinen Ort


def test_ipv6_adressen_werden_richtig_vom_port_getrennt():
    """"[2a02::1]:8333" naiv am letzten Doppelpunkt zu trennen liefert
    "[2a02::1]" -- mit Klammern, und damit keine gueltige Adresse."""
    assert karte._nur_adresse("[2a02:8071::1]:8333") == "2a02:8071::1"
    assert karte._nur_adresse("84.134.0.1:8333") == "84.134.0.1"
    # Ohne Klammern und ohne Port: nichts abschneiden, sonst fehlt eine Gruppe.
    assert karte._nur_adresse("2a02:8071::1") == "2a02:8071::1"
    assert karte._nur_adresse("") == ""


def test_ein_nachbar_faellt_nicht_von_der_karte():
    """203.0.113.7 ist eine echte Gegenstelle, taucht aber nicht in der
    Stichprobe des Adressbuchs auf. Ohne Sonderbehandlung fehlte ausgerechnet
    Japan auf der Karte."""
    d = karte.sammle(_knoten(), ORTE)
    jp = [e for e in d["laender"] if e["land"] == "JP"]
    assert jp == [{"land": "JP", "adressen": 0, "peers": 1}]


def test_herkunft_der_ortsdaten_kommt_mit():
    """Nicht Beiwerk: DB-IP steht unter CC BY, die Herkunft MUSS genannt
    werden -- und eine alte Liste ordnet still falsch zu."""
    assert karte.sammle(_knoten(), ORTE)["orte_stand"] == "2026-08"
    assert karte.sammle(_knoten(), None)["orte_stand"] == ""


def test_ohne_ortstabelle_bleiben_die_zahlen_stehen():
    """Ein Abbild ohne Tabelle soll nicht die halbe Ansicht verlieren."""
    k = _knoten()
    d = karte.sammle(k, None)
    assert d["tabelle_da"] is False
    assert d["laender"] == []
    assert d["bekannt"]["all_networks"] == 57313      # die Zahlen gibt es weiter
    assert d["peers"]["gesamt"] == 4
    # Und: ohne Tabelle wird das Adressbuch gar nicht erst geholt.
    assert not [m for m, _, _ in k.aufrufe if m == "getnodeaddresses"]


def test_knoten_nicht_erreichbar_ist_kein_absturz():
    k = Attrappe({}, scheitern=("getaddrmaninfo", "getnodeaddresses", "getpeerinfo"))
    d = karte.sammle(k, ORTE)
    assert d["laender"] == [] and d["bekannt"] == {} and d["peers"]["gesamt"] == 0


def test_die_karte_fragt_durchweg_mit_geduld():
    """Waehrend des Erstabgleichs ist bitcoind beschaeftigt, und seine
    RPC-Arbeiter stehen in der Schlange.

    Hier stand bis zum 01.09.2026 das Gegenteil: nur das Adressbuch bekam
    eine laengere Frist, alles andere lief an "kurzer Leine, damit man einen
    abwesenden Knoten schnell erkennt". Das Betriebsprotokoll hat das widerlegt
    -- "getnetworkinfo nicht moeglich: antwortet nicht innerhalb von 5 s",
    waehrend der Knoten mit 176 Bloecken je Minute durchlief. Ein Fehlalarm.

    Die kurze Leine war ausserdem nicht die Stelle, die einen abwesenden
    Knoten erkennt: das macht lage_mit_grund() mit einer eigenen Probe von
    zwei Sekunden. Die Karte laeuft im Hintergrund und darf warten.

    Das Adressbuch behaelt seine eigene, laengere Frist -- die Antwort kann
    einige Megabyte gross sein."""
    k = _knoten()
    karte.sammle(k, ORTE)
    fristen = {m: z for m, _, z in k.aufrufe}
    assert fristen["getnodeaddresses"] == karte.ZEITLIMIT_SEKUNDEN
    assert fristen["getpeerinfo"] == rpc.GEDULD_SEKUNDEN
    assert fristen["getnetworkinfo"] == rpc.GEDULD_SEKUNDEN
    assert fristen["getaddrmaninfo"] == rpc.GEDULD_SEKUNDEN


# ── Der eigene Ort: Ursprung der Linien ───────────────────────────────────

def test_eigener_ort_kommt_aus_der_hoechsten_eigenen_adresse():
    """Core zaehlt im "score" mit, wie oft ihm eine Adresse als die eigene
    gemeldet wurde. Die hoechste zuerst -- und ueber die Onion-Adresse
    hinweg, die davor steht und keinen Ort hat."""
    assert karte.sammle(_knoten(), ORTE)["heimat"] == "DE"


def test_ohne_eigene_adresse_zaehlen_die_gegenstellen():
    """Bei discover=0 oder reinem Tor-Betrieb bleibt localaddresses leer.
    Dann sagen die Gegenstellen, wofuer sie uns halten -- und zwar die
    Mehrheit, nicht ein einzelner Zeuge, denn die Angabe koennte gelogen
    sein."""
    k = _knoten(**{
        "getnetworkinfo": {"localaddresses": []},
        "getpeerinfo": [
            {"addr": "84.134.0.1:8333", "inbound": False,
             "addrlocal": "198.51.100.4:8333"},
            {"addr": "203.0.113.7:8333", "inbound": True,
             "addrlocal": "198.51.100.4:8333"},
            # Ein einzelner Widerspruch darf das Ergebnis nicht kippen.
            {"addr": "1.0.0.1:8333", "inbound": True,
             "addrlocal": "203.0.113.7:8333"},
        ],
    })
    assert karte.sammle(k, ORTE)["heimat"] == "CH"


def test_ohne_jede_quelle_gibt_es_keine_heimat():
    """Kein Ort heisst kein Ort -- die Karte zeigt dann Laender, aber keine
    Verbindungen. Einen Ursprung zu raten waere schlimmer als keiner."""
    k = _knoten(**{
        "getnetworkinfo": {"localaddresses": [
            {"address": "abcdef.onion", "port": 8333, "score": 4}]},
        "getpeerinfo": [{"addr": "abc.onion:8333", "inbound": True}],
    })
    assert karte.sammle(k, ORTE)["heimat"] is None


def test_unerreichbarer_knoten_hat_keine_heimat():
    k = Attrappe({}, scheitern=("getnetworkinfo", "getpeerinfo"))
    assert karte.sammle(k, ORTE)["heimat"] is None


def test_die_eigene_adresse_verlaesst_den_knoten_nicht():
    """Nur das Laenderkuerzel gehoert in die Antwort. Die eigene Adresse hat
    in einer Weboberflaeche nichts zu suchen -- auch nicht in einer
    geschuetzten, und auch nicht als Nebenprodukt."""
    d = karte.sammle(_knoten(), ORTE)
    text = repr(d)
    for geheim in ("84.134.0.9", "abcdef.onion"):
        assert geheim not in text
    # Auch die Zaehlung der Fremdmeldungen bleibt drinnen.
    assert "gesehen_als" not in d["peers"]


# ── Nicht zweimal nach demselben fragen ───────────────────────────────────
#
# Aus das Betriebsprotokoll, tagelang: "satcortex.karte  getnetworkinfo nicht
# moeglich: antwortet nicht innerhalb von 15 s". Eine laengere Leine war die
# falsche Antwort. Geprueft gegen Bitcoin Core v31.1, src/rpc/net.cpp:
# getnetworkinfo nimmt LOCK(cs_main) -- getaddrmaninfo, getnodeaddresses und
# getpeerinfo nicht. Es ist also der einzige Aufruf der Karte, der waehrend
# eines chainstate-Schreibvorgangs zwangslaeufig wartet. Die Kettenlage holt
# ihn ohnehin und legt ihn beiseite; die Karte bekommt ihn gereicht.


def test_die_karte_fragt_getnetworkinfo_nicht_selbst(monkeypatch):
    from satcortex import karte

    gefragt = []

    class Knoten:
        def ruf(self, methode, *p, **kw):
            gefragt.append(methode)
            if methode == "getaddrmaninfo":
                return {"ipv4": {"total": 0}}
            return []

    class Tabelle:
        def ort(self, adresse):
            return "DE" if adresse.startswith("203.") else None, 0

        def land(self, adresse):
            return self.ort(adresse)[0]

    karte.sammle(Knoten(), Tabelle(), karte.LEERES_BUCH,
                 [{"adresse": "203.0.113.7", "port": 8333, "score": 4}])
    assert "getnetworkinfo" not in gefragt


def test_ohne_gereichte_adressen_fragt_sie_weiterhin_selbst(monkeypatch):
    """Der Weg bleibt offen -- sonst waere die Funktion allein nicht mehr
    benutzbar."""
    from satcortex import karte

    gefragt = []

    class Knoten:
        def ruf(self, methode, *p, **kw):
            gefragt.append(methode)
            if methode == "getnetworkinfo":
                return {"localaddresses": [{"address": "79.1.2.3", "score": 1}]}
            return []

    class Tabelle:
        def ort(self, adresse):
            return "DE", 0

        def land(self, adresse):
            return self.ort(adresse)[0]

    assert karte.eigener_ort(Knoten(), Tabelle()) == "DE"
    assert "getnetworkinfo" in gefragt


def test_ein_aussetzer_bei_getaddrmaninfo_leert_nicht_die_karte():
    """Vorher: bekannt={} liess jedes Netz ueberspringen, das Buch blieb leer
    und wurde weggeworfen -- die Weltkarte war fuer eine halbe Stunde leer."""
    from satcortex import karte, rpc

    gefragt = []

    class Knoten:
        def ruf(self, methode, *p, **kw):
            gefragt.append((methode, p))
            if methode == "getaddrmaninfo":
                raise rpc.Beschaeftigt("antwortet nicht innerhalb von 15 s")
            if methode == "getnodeaddresses":
                return [{"address": "203.0.113.7"}]
            return []

    class Tabelle:
        def ort(self, adresse):
            return "DE", 0

        def land(self, adresse):
            return self.ort(adresse)[0]

    buch = karte.adressbuch(Knoten(), Tabelle())
    assert buch["bekannt"], "ohne bekannt wirft der Waechter das Buch weg"
    assert buch["laender"]["DE"] > 0
    mengen = [p[0] for m, p in gefragt if m == "getnodeaddresses"]
    assert mengen and all(m == karte.ERSATZMENGE_JE_NETZ for m in mengen)


def test_bei_unbekannter_lage_wird_getnetworkinfo_nicht_nachgeholt():
    """Der unvollstaendige Fix vom 01.09.2026: /api/karte reichte
    "(lage or {}).get('adressen')" weiter -- also None, wenn die Lage
    ausgefallen war. None heisst fuer sammle() "hol sie dir selbst", und
    genau dann ist bitcoind beschaeftigt. Am 02.09. um 07:08 stand die
    Meldung wieder im Protokoll."""
    from satcortex import karte

    gefragt = []

    class Knoten:
        def ruf(self, methode, *p, **kw):
            gefragt.append(methode)
            if methode == "getaddrmaninfo":
                return {"ipv4": {"total": 0}}
            return []

    class Tabelle:
        def ort(self, adresse):
            return None, 0

        def land(self, adresse):
            return self.ort(adresse)[0]

    # So reicht der Endpunkt es weiter, wenn die Lage fehlt: leere Liste.
    karte.sammle(Knoten(), Tabelle(), karte.LEERES_BUCH, [])
    assert "getnetworkinfo" not in gefragt
