"""Prueft die Konfiguration, mit der der Knoten spaeter wirklich laeuft.

Diese Tests sind die wichtigsten im Projekt: ein falscher Wert hier bedeutet
entweder einen Knoten, der nicht am Netz teilnimmt, oder einen, der die
Leitung dichtmacht.
"""
import re

import pytest

from satcortex import nodeconfig, profiles

# Zwei echte v3-Adressen (DuckDuckGo, Tor Project) -- mit stimmender
# Pruefsumme, sonst lehnt nodeconfig sie ab.
ONION_A = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion"
ONION_B = "2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion"


def _werte(text):
    """Konfigurationszeilen als dict, Kommentare ignoriert."""
    paare = {}
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        paare[k.strip()] = v.strip()
    return paare


def test_keine_platzhalter_bleiben_uebrig():
    text = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen())
    assert "{{" not in text and "}}" not in text


def test_teilnahme_ist_eingeschaltet():
    w = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=False)))
    # Ohne diese vier ist der Knoten ein blosser Mitleser.
    assert w["listen"] == "1"
    assert w["discover"] == "1"
    assert w["prune"] == "0"            # Archiv-Knoten: liefert die ganze Kette aus
    assert w["peerblockfilters"] == "1"  # bedient Leichtgewicht-Wallets


def test_indizes_erst_wenn_die_kette_steht():
    """Waehrend des Abgleichs sind txindex und Blockfilter AUS.

    Beide sind LevelDB-Datenbanken, die bei jedem Block mit Spruengen
    schreiben -- auf derselben Platte wie die Bloecke. Auf einer Festplatte
    nehmen sie genau die Zugriffe weg, auf die der Abgleich wartet. Gebraucht
    werden sie erst danach: der eine fuer die Verfolgung und fuer Wallets, der
    andere fuer Leichtgewicht-Wallets. Waehrend die Kette laedt, fragt danach
    niemand.
    """
    laeuft = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=True)))
    assert laeuft["txindex"] == "0"
    assert laeuft["blockfilterindex"] == "0"
    # peerblockfilters MUSS mit: ohne blockfilterindex bricht Core den Start
    # ab -- "Cannot set -peerblockfilters without -blockfilterindex."
    assert laeuft["peerblockfilters"] == "0"

    steht = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=False)))
    assert steht["txindex"] == "1"
    assert steht["blockfilterindex"] == "1"
    assert steht["peerblockfilters"] == "1"


def test_die_drei_schalter_gehen_immer_zusammen():
    """Der Fallstrick, an dem eine naive Umsetzung endet: wer nur zwei von
    dreien umlegt, hat einen Knoten, der nicht mehr hochkommt."""
    conf = nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=False))
    for an in (False, True):
        w = _werte(nodeconfig.setze_indizes(conf, an))
        soll = "1" if an else "0"
        assert [w[k] for k in nodeconfig.INDEX_SCHALTER] == [soll] * 3


def test_umschalten_laesst_alles_andere_stehen():
    """Die Datei wird gezielt geaendert, nicht neu gebaut -- sonst ginge die
    rpcauth-Zeile verloren, und die Anwendung waere von ihrem eigenen Knoten
    ausgesperrt."""
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(
        im_erstsync=False, externe_adressen=("1.2.3.4",)))
    aus = nodeconfig.setze_indizes(conf, False)
    for zeile in ("rpcauth=", "externalip=1.2.3.4", "zmqpubsequence=",
                  "blocksdir=/bulk/blocks", "prune=0"):
        assert any(z.strip().startswith(zeile) for z in aus.splitlines()), zeile
    # Und hin und zurueck ergibt wieder genau einen Satz Schalter.
    zurueck = nodeconfig.setze_indizes(aus, True)
    assert zurueck.count("txindex=") == 1
    assert nodeconfig.lies_indizes(zurueck) is True
    assert nodeconfig.lies_indizes(aus) is False


def test_zmq_sequence_ist_da():
    # Grundlage der First-Seen-Auswertung. Fehlt sie, ist der Kern des Projekts tot.
    w = _werte(nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen()))
    assert w["zmqpubsequence"].startswith("tcp://")


def test_rpc_ist_nicht_offen_fuer_alle():
    w = _werte(nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen()))
    assert w["rpcallowip"] != "0.0.0.0/0"
    assert "rpcpassword" not in w       # nur der Hash, nie das Klartext-Passwort
    assert w["rpcauth"].count("$") == 1


def test_upload_budget_wird_in_tageswert_umgerechnet():
    e = nodeconfig.Knoteneinstellungen(upload_gb_pro_monat=300)
    w = _werte(nodeconfig.baue_bitcoind(e))
    assert int(w["maxuploadtarget"]) == profiles.upload_gb_pro_monat_zu_mib_pro_tag(300)


def test_unbegrenzter_upload_wird_zu_null():
    e = nodeconfig.Knoteneinstellungen(upload_gb_pro_monat=0)
    w = _werte(nodeconfig.baue_bitcoind(e))
    assert w["maxuploadtarget"] == "0"


def test_tor_an_und_aus():
    an = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=True))
    assert nodeconfig.lies_tor(an)
    # Frueher stand hier "proxy=tor:9050" -- der Test hielt damit den Fehler
    # fest, statt ihn zu finden. Siehe test_tor_setzt_onion_und_nicht_proxy.
    assert "onion=tor:9050" in an

    aus = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=False))
    assert not nodeconfig.lies_tor(aus)
    assert "abgeschaltet" in aus


def test_onlynet_wird_nie_gesetzt():
    # Sonst faellt eine der drei Welten (IPv4/IPv6/Onion) weg.
    for tor in (True, False):
        w = _werte(nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=tor)))
        assert "onlynet" not in w


def test_cache_folgt_der_speichergrenze():
    klein = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(speichergrenze_mb=1500)))
    gross = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(speichergrenze_mb=4000)))
    assert int(klein["dbcache"]) < int(gross["dbcache"])
    # und beide lassen Luft
    assert int(klein["dbcache"]) < 1500
    assert int(gross["dbcache"]) < 4000


def test_cache_ist_im_betrieb_kleiner_als_im_erstsync():
    sync = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=True)))
    betrieb = _werte(nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(im_erstsync=False)))
    assert int(betrieb["dbcache"]) < int(sync["dbcache"])


def test_jeder_knoten_bekommt_eigene_zugangsdaten():
    a = _werte(nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen()))
    b = _werte(nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen()))
    assert a["rpcauth"] != b["rpcauth"]


# ── Fund vom 25.08.2026: Tor lahmgelegt und der ganze Verkehr umgeleitet ─────

def _conf_mit_tor():
    return nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=True))


def test_tor_setzt_onion_und_nicht_proxy():
    """"proxy" gilt fuer ALLE Netze -- damit liefe auch der Clearnet-Verkehr
    durch Tor, und die DNS-Seeds liefern nichts mehr. Gewollt ist der
    Hybridbetrieb: Clearnet direkt, Onion ueber Tor."""
    conf = _conf_mit_tor()
    zeilen = [z.strip() for z in conf.splitlines() if not z.strip().startswith("#")]
    assert "onion=tor:9050" in zeilen
    assert not any(z.startswith("proxy=") for z in zeilen), \
        "proxy= leitet auch IPv4/IPv6 durch Tor -- das ist nicht gewollt"


def test_bitcoind_legt_seinen_onion_dienst_nicht_mehr_selbst_an():
    """Der Befund vom 17.09.2026. Mit listenonion auf 1 bat bitcoind Tor
    ueber den Steuerport um einen Dienst -- ohne Ziel. Tor setzte 127.0.0.1
    ein, also seinen EIGENEN Container (hs_common.c), und dort horcht kein
    bitcoind. Die .onion stand im Netz und war nie erreichbar.

    Seitdem haelt Tor den Dienst selbst, und bitcoind braucht den Steuerport
    gar nicht mehr."""
    zeilen = _werte(_conf_mit_tor())
    assert zeilen["listenonion"] == "0", \
        "ohne ausdrueckliche 0 greift Cores Vorgabe und er sucht den Steuerport"
    assert "torcontrol" not in zeilen


def test_bitcoind_horcht_dort_wo_tor_hinreicht():
    """Tor reicht an 8334 weiter (onion.DIENSTE). Ohne "=onion" hielte Core
    die Gegenstellen fuer Nachbarn aus dem Compose-Netz; ohne den Port
    daneben stuende 8333 nicht mehr offen -- sobald -bind gesetzt ist, horcht
    Core nur noch dort, wo es steht."""
    zeilen = [z.strip() for z in _conf_mit_tor().splitlines()
              if not z.strip().startswith("#")]
    assert "bind=0.0.0.0:8334=onion" in zeilen
    assert "bind=0.0.0.0:8333" in zeilen
    from satcortex import onion
    assert onion.DIENSTE["bitcoind"].zielport == 8334


def test_die_eigene_onion_wird_angekuendigt():
    adresse = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion"
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(
        tor_aktiv=True, onion_adresse=adresse))
    assert f"externalip={adresse}" in conf.splitlines()
    assert nodeconfig.lies_onion(conf) == adresse
    # Die Clearnet-Adressen sieht sie nicht -- sonst hielte die
    # Adressnachfuehrung sie fuer eine veraltete DNS-Antwort.
    assert nodeconfig.lies_adressen(conf) == []


def test_eine_untergeschobene_onion_kommt_nicht_in_die_datei():
    with pytest.raises(ValueError):
        nodeconfig.tor_block("xyz.onion\nrpcallowip=0.0.0.0/0")


def test_ohne_tor_steht_nichts_von_tor_drin():
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=False))
    zeilen = [z.strip() for z in conf.splitlines() if not z.strip().startswith("#")]
    assert not any(z.startswith(("onion=", "proxy=", "torcontrol=", "listenonion=",
                                 "bind="))
                   for z in zeilen)


def test_der_tor_abschnitt_laesst_sich_umlegen_ohne_reste():
    """An- und Abschalten, mit und ohne .onion, beliebig oft: am Ende steht
    genau ein Abschnitt da, und keine Zeile doppelt."""
    adresse = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion"
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(
        tor_aktiv=True, onion_adresse=adresse))
    for an, mit in ((False, ""), (True, adresse), (True, ""), (True, adresse)):
        conf = nodeconfig.setze_tor(conf, an, mit)
    zeilen = [z.strip() for z in conf.splitlines() if z.strip()
              and not z.strip().startswith("#")]
    assert zeilen.count("bind=0.0.0.0:8334=onion") == 1
    assert zeilen.count(f"externalip={adresse}") == 1
    assert zeilen.count("onion=tor:9050") == 1


def test_eine_datei_von_0_62_wird_sauber_umgestellt():
    """So sieht der Abschnitt bei jedem aus, der vor 0.63.0 eingerichtet
    hat. Nach dem Umlegen darf von der alten Art nichts uebrig sein."""
    alt = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(tor_aktiv=True))
    alt_block = ("# Tor: der Knoten ist zusaetzlich als Onion-Dienst erreichbar. "
                 "Tor-Knoten\n# brauchen Gegenstellen\nonion=tor:9050\n"
                 "torcontrol=tor:9051\nlistenonion=1")
    alt = nodeconfig.setze_tor(alt, False).replace(
        nodeconfig.TOR_AUS, alt_block)
    assert nodeconfig.tor_nach_altem_muster(alt)

    neu = nodeconfig.setze_tor(alt, True, "")
    assert not nodeconfig.tor_nach_altem_muster(neu)
    assert "torcontrol=" not in neu and "listenonion=1" not in neu.splitlines()


# ── Eigene Adresse ankuendigen (26.08.2026) ─────────────────────────────────
#
# Am Geraet stand unter "Erreichbar unter" nur die Onion-Adresse. Der Port war
# nachweislich offen -- angekuendigt wurde trotzdem nichts, weil Core im
# Container nur die Docker-interne 172.x sieht.

def test_ohne_angabe_steht_kein_externalip_drin():
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen())
    zeilen = [z.strip() for z in conf.splitlines() if not z.strip().startswith("#")]
    assert not any(z.startswith("externalip=") for z in zeilen)


def test_angegebene_adresse_wird_angekuendigt():
    conf = nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(externe_adressen=("meinhost.example",)))
    assert "externalip=meinhost.example" in conf


def test_mehrere_adressen_bekommen_je_eine_zeile():
    """IPv4 und IPv6 nebeneinander -- Core nimmt beliebig viele."""
    conf = nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen(
        externe_adressen=("203.0.113.7", "2001:db8::1")))
    zeilen = [z.strip() for z in conf.splitlines()]
    assert "externalip=203.0.113.7" in zeilen
    assert "externalip=2001:db8::1" in zeilen


def test_leere_eintraege_erzeugen_keine_kaputte_zeile():
    conf = nodeconfig.baue_bitcoind(
        nodeconfig.Knoteneinstellungen(externe_adressen=("", "  ", "gut.example")))
    zeilen = [z.strip() for z in conf.splitlines()]
    assert "externalip=" not in zeilen
    assert "externalip=gut.example" in zeilen


# ── Adresse nachtragen, ohne die uebrige Konfiguration anzufassen ────────────

BESTAND = """# Von SatoshiCortex erzeugt
server=1
txindex=1
listen=1
discover=1
maxconnections=80
rpcauth=satcortex:abc$def
dbcache=1500
"""


def test_adresse_wird_hinter_discover_eingefuegt():
    neu = nodeconfig.setze_adressen(BESTAND, ("meinhost.example",))
    zeilen = [z.strip() for z in neu.splitlines()]
    assert "externalip=meinhost.example" in zeilen
    assert zeilen.index("externalip=meinhost.example") > zeilen.index("discover=1")


def test_alles_andere_bleibt_zeichengenau_stehen():
    """Vor allem die rpcauth-Zeile: eine neue wuerde die Anwendung von ihrem
    eigenen Knoten aussperren."""
    neu = nodeconfig.setze_adressen(BESTAND, ("x.example",))
    for zeile in ("server=1", "txindex=1", "maxconnections=80",
                  "rpcauth=satcortex:abc$def", "dbcache=1500"):
        assert zeile in neu.splitlines()


def test_eine_zweite_aenderung_haeuft_keine_zeilen_an():
    einmal = nodeconfig.setze_adressen(BESTAND, ("erste.example",))
    zweimal = nodeconfig.setze_adressen(einmal, ("zweite.example",))
    zeilen = [z for z in zweimal.splitlines() if z.startswith("externalip=")]
    assert zeilen == ["externalip=zweite.example"]


def test_leere_angabe_entfernt_die_adresse_wieder():
    mit = nodeconfig.setze_adressen(BESTAND, ("weg.example",))
    ohne = nodeconfig.setze_adressen(mit, ())
    assert not any(z.startswith("externalip=") for z in ohne.splitlines())


def test_ohne_discover_kommt_der_block_ans_ende():
    """Eine von Hand bearbeitete Datei darf nicht dazu fuehren, dass die
    Adresse stillschweigend unter den Tisch faellt."""
    neu = nodeconfig.setze_adressen("server=1\ntxindex=1\n", ("x.example",))
    assert "externalip=x.example" in neu.splitlines()


# ── Datenbank-Cache nachregeln (26.08.2026) ─────────────────────────────────
#
# im_erstsync wurde beim Einrichten auf True gesetzt und nie zurueckgenommen.
# Die Logik dafuer stand da und wurde nie gerufen -- auf einem NAS blieb so
# dauerhaft rund ein Gigabyte gebunden, das niemand mehr braucht.

def test_cache_wird_ersetzt_nicht_verdoppelt():
    neu = nodeconfig.setze_dbcache(BESTAND, 375)
    zeilen = [z for z in neu.splitlines() if z.startswith("dbcache=")]
    assert zeilen == ["dbcache=375"]


def test_alles_andere_bleibt_beim_cachewechsel_stehen():
    neu = nodeconfig.setze_dbcache(BESTAND, 375)
    for zeile in ("server=1", "maxconnections=80", "rpcauth=satcortex:abc$def"):
        assert zeile in neu.splitlines()


def test_fehlende_zeile_wird_ergaenzt():
    neu = nodeconfig.setze_dbcache("server=1\ntxindex=1\n", 500)
    assert "dbcache=500" in neu.splitlines()


def test_eingestellten_wert_auslesen():
    assert nodeconfig.lies_dbcache(BESTAND) == 1500
    assert nodeconfig.lies_dbcache("server=1\n") is None
    assert nodeconfig.lies_dbcache("dbcache=kaputt\n") is None


def test_die_beiden_phasen_unterscheiden_sich_deutlich():
    """Sonst waere das Nachregeln die Muehe nicht wert."""
    from satcortex import profiles
    sync = profiles.dbcache_mb(2500, im_erstsync=True)
    betrieb = profiles.dbcache_mb(2500, im_erstsync=False)
    assert sync > betrieb * 2
    assert betrieb >= 150


# ── Lightning ──────────────────────────────────────────────────────────────

def test_lnd_konfiguration_ist_vollstaendig():
    # Ausdruecklich "hybrid": seit dem 04.09.2026 kuendigt nur diese
    # Betriebsart eine Clearnet-Adresse an. Die Vorgabe ist "tor" -- wer
    # nicht waehlt, soll seine Adresse nicht versehentlich preisgeben.
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        alias="MyNode", sichtbarkeit="hybrid",
        externe_adressen=("203.0.113.7:9735",)))
    assert "{{" not in conf                      # kein Platzhalter uebrig
    assert "alias=MyNode" in conf
    assert "externalip=203.0.113.7:9735" in conf
    assert "listen=0.0.0.0:9735" in conf
    assert "bitcoin.mainnet=true" in conf
    assert "bitcoind.rpchost=bitcoind:8332" in conf


def test_das_rpc_passwort_steht_nicht_in_der_lnd_konfiguration():
    """Bitcoin Core legt eine Cookie-Datei an, solange rpcpassword nicht
    gesetzt ist -- ein gesetztes rpcauth verhindert das nicht. LND nimmt sie
    als vollwertigen Ersatz. Ohne das stuende das Passwort im Klartext in
    einer zweiten Datei, auf einem Geraet mit einer Wallet darauf."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "bitcoind.rpccookie=/fast/bitcoind/.cookie" in conf
    # Auf die WIRKSAMEN Zeilen sehen, nicht auf den Fliesstext: der Kommentar
    # daneben erklaert ja gerade, warum rpcuser/rpcpass hier fehlen.
    wirksam = [z.strip() for z in conf.splitlines()
               if z.strip() and not z.strip().startswith("#")]
    assert not [z for z in wirksam if z.startswith(("bitcoind.rpcpass",
                                                    "bitcoind.rpcuser"))]


def test_die_gebuehren_zielen_nicht_auf_grossrouter():
    """Die Lightning-Labs-Vorlage nennt 2000 ppm. Der Netz-Median lag 2026 bei
    rund 143 -- mit 2000 wuerde der Knoten gemieden."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "bitcoin.feerate=100" in conf
    assert "bitcoin.basefee=0" in conf


def test_tor_laesst_sich_abschalten():
    an = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(tor_aktiv=True))
    aus = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(tor_aktiv=False))
    assert "tor.active=true" in an
    assert "tor.active" not in aus


def test_lnd_legt_keinen_onion_dienst_mehr_an():
    """Der Befund vom 17.09.2026, von der LND-Seite. tor.v3 liess LND selbst
    ueber den Steuerport einen Dienst anlegen -- mit Ziel 127.0.0.1 im
    Tor-Container, und nach jedem Neustart von Tor war er weg, weil LNDs
    Pruefung dafuer abgeschaltet ist (healthcheck.torconnection.attempts=0).
    In JEDER Betriebsart aus, und ohne Steuerport."""
    for sicht in ("tor", "hybrid", "still"):
        conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
            sichtbarkeit=sicht))
        zeilen = [z.strip() for z in conf.splitlines()
                  if not z.strip().startswith("#")]
        assert "tor.v3=false" in zeilen, sicht
        assert not any(z.startswith("tor.control") for z in zeilen), sicht


def test_ohne_adresse_steht_der_grund_dabei():
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "externalip=" not in conf
    assert "keinen Kanal zu ihm" in conf


def test_der_alias_wird_in_byte_gemessen_nicht_in_zeichen():
    """Der Alias reist im Gossip als Feld fester Groesse: 32 Byte. Wer nach
    Zeichen zaehlt, baut einen Alias, den LND beim Start ablehnt -- und der
    Fehler steht dann in einem Container-Protokoll statt im Eingabefeld."""
    gerade_noch = "A" * 32
    assert nodeconfig.pruefe_alias(gerade_noch) == gerade_noch
    with pytest.raises(ValueError):
        nodeconfig.pruefe_alias("A" * 33)
    # 32 Zeichen, aber 34 Byte -- genau die Falle.
    zu_lang = "Müllers Nachtknoten wächst sehr!"
    assert len(zu_lang) == 32 and len(zu_lang.encode("utf-8")) == 34
    with pytest.raises(ValueError):
        nodeconfig.pruefe_alias(zu_lang)
    with pytest.raises(ValueError):
        nodeconfig.pruefe_alias("   ")


def test_kein_eingabefeld_kann_eine_zeile_anhaengen():
    """Alias, Farbe und Adressen landen unveraendert in einer Datei, die LND
    Zeile fuer Zeile liest. Ein Zeilenumbruch darin waere keine
    Schoenheitsfrage -- dahinter liesse sich jede LND-Option anhaengen, etwa
    eine, die das Wallet-Passwort aus einer Datei liest."""
    boese = "Knoten\nwallet-unlock-password-file=/fast/geheim"
    with pytest.raises(ValueError):
        nodeconfig.pruefe_alias(boese)
    with pytest.raises(ValueError):
        nodeconfig.pruefe_farbe("#f7931a\nlisten=0.0.0.0:1")
    # Und als Netz: eine Adresse mit Umbruch faellt weg, statt in die Datei
    # zu wandern.
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        externe_adressen=("1.2.3.4:9735\nwallet-unlock-password-file=/x",)))
    assert "wallet-unlock-password-file" not in conf
    # Dasselbe fuer bitcoind, wo der Schutz bisher an der DNS-Aufloesung hing.
    bc = nodeconfig.adressblock(("1.2.3.4\nrpcallowip=0.0.0.0/0",))
    assert "rpcallowip" not in bc


def test_die_farbe_muss_eine_farbe_sein():
    assert nodeconfig.pruefe_farbe("#F7931A") == "#f7931a"
    for unsinn in ("rot", "#12345", "f7931a", ""):
        with pytest.raises(ValueError):
            nodeconfig.pruefe_farbe(unsinn)


# ── Das Netz wird nicht der Vorgabe ueberlassen ───────────────────────────
#
# Der Betreiber, 02.09.2026: "ich hoffe das wir uns mit dem richtigen btc netz
# verbinden wollen -- da gibt es wohl mitlerweile auch side netzwerke".
# Berechtigt: ein Knoten auf testnet4 oder signet sieht in jeder Anzeige
# genauso aus wie einer auf mainnet. Cores Vorgabe IST mainnet -- aber eine
# Vorgabe, auf die man sich verlaesst, ist eine Annahme.


def test_die_konfiguration_nennt_das_netz_ausdruecklich(tmp_path):
    from satcortex import nodeconfig

    conf = nodeconfig.lade_vorlage("bitcoin.conf.tmpl")
    assert "chain=main" in conf
    for fremd in ("testnet", "signet", "regtest", "testnet4"):
        assert f"chain={fremd}" not in conf


# ── Eine Quelle je Version ────────────────────────────────────────────────
#
# Die Fremdversionen standen bis zum 02.09.2026 ZWEIMAL in der Compose: im
# Abbildnamen und im Bauargument daneben. Die CI liest den einen Wert, ein
# lokales "docker compose build" den anderen -- laufen sie auseinander, baut
# die CI etwas anderes als der Nutzer, und das Abbild traegt eine Nummer,
# die nicht drinsteckt. Renovate pflegte die beiden Zeilen ausserdem
# getrennt (Docker-Manager und Regex-Manager) und erzeugte die Luecke damit
# von selbst.
#
# Jetzt steht die Zahl in example.env, und die Compose zeigt zweimal
# dorthin. Genau so, wie es der Text in example.env schon immer versprach:
# "Zahl hier hochsetzen, docker compose up -d".


def _wurzel():
    from pathlib import Path

    import satcortex

    return Path(satcortex.__file__).resolve().parents[3]


def _lies(name):
    return (_wurzel() / name).read_text(encoding="utf-8")


VERSIONIERT = [("satcortex-bitcoind", "BITCOIN_VERSION"),
               ("satcortex-lnd", "LND_VERSION")]


def test_die_version_steht_nur_in_der_env():
    """In der Compose darf keine feste Fremdversion mehr stehen."""
    import re

    compose = _lies("docker-compose.yml")
    for abbild, argument in VERSIONIERT:
        treffer = re.search(rf"{abbild}:(\S+)", compose)
        assert treffer, f"{abbild} steht nicht in der Compose"
        assert treffer.group(1).startswith("${" + argument), (
            f"{abbild} traegt eine feste Version ({treffer.group(1)}) statt "
            f"auf ${{{argument}}} zu zeigen")


def test_abbildname_und_bauargument_zeigen_auf_dieselbe_stelle():
    import re

    compose = _lies("docker-compose.yml")
    for abbild, argument in VERSIONIERT:
        im_namen = re.search(rf"{abbild}:\$\{{(\w+)", compose)
        im_argument = re.search(rf"^\s+{argument}: \$\{{(\w+)",
                                compose, re.MULTILINE)
        assert im_namen and im_argument, f"{abbild}: eine der Zeilen fehlt"
        assert im_namen.group(1) == im_argument.group(1) == argument


def test_die_env_nennt_jede_version_die_die_compose_braucht():
    """Ohne den Eintrag griffe die Vorgabe hinter ":-" -- still und
    moeglicherweise mit einer anderen Zahl."""
    import re

    env = _lies("example.env")
    for _abbild, argument in VERSIONIERT:
        assert re.search(rf"^{argument}=\S+", env, re.MULTILINE), (
            f"{argument} fehlt in example.env")


def test_die_ci_liest_dieselbe_datei():
    """Sonst baut sie eine andere Version, als die Compose zieht."""
    ablauf = _lies(".github/workflows/images.yml")
    for _abbild, argument in VERSIONIERT:
        assert f"^{argument}=" in ablauf and "example.env" in ablauf, (
            f"die CI holt {argument} nicht aus example.env")
    # Und eine neue Zahl dort muss den Bau ausloesen.
    assert ablauf.count("example\\.env$") >= 2 or ablauf.count(
        "example\.env$") >= 2, (
        "eine geaenderte Version in example.env loest keinen Bau aus")


def test_die_ausgelieferte_lnd_fassung_steht_ueberall_gleich():
    """Sie steht an drei Stellen: example.env, das Dockerfile und die
    Konstante in updates.py. Der bisherige Test verglich nur die letzten
    beiden -- und weil die GEMEINSAM veralteten, blieb er gruen. Im
    Update-Kasten stand daraufhin "0.21.3-beta ist verfuegbar", waehrend
    genau die Fassung lief."""
    import re

    from satcortex import updates

    aus_env = re.search(r"^LND_VERSION=(\S+)", _lies("example.env"),
                        re.MULTILINE)
    aus_datei = re.search(r"^ARG LND_VERSION=(\S+)",
                          _lies("images/lnd/Dockerfile"), re.MULTILINE)
    assert aus_env and aus_datei
    lesbar = "v%d.%d.%d-beta" % updates.LND_AUSGELIEFERT
    assert aus_env.group(1) == aus_datei.group(1) == lesbar, (
        f"example.env sagt {aus_env.group(1)}, das Dockerfile "
        f"{aus_datei.group(1)}, updates.LND_AUSGELIEFERT {lesbar}")


def test_die_ausgelieferte_core_fassung_steht_ueberall_gleich():
    import re

    aus_env = re.search(r"^BITCOIN_VERSION=(\S+)", _lies("example.env"),
                        re.MULTILINE)
    aus_datei = re.search(r"^ARG BITCOIN_VERSION=(\S+)",
                          _lies("images/bitcoind/Dockerfile"), re.MULTILINE)
    assert aus_env and aus_datei
    assert aus_env.group(1) == aus_datei.group(1)


# ── Die Kanal-Untergrenze passt zur Groesse des Knotens (04.09.2026) ────────
#
# Der Betreiber: "wollte so'n lnd knoten eigentlich klein betreiben in
# btc ... pass das auf eine kleine Grenze an, drueber geht dann immer."
#
# Bis dahin stand dort eine Million Sats -- rund 680 Euro, uebernommen aus der
# Routing-Knoten-Planung. Die Einstellung betrifft laut LNDs eigener
# Beschreibung ausschliesslich EINGEHENDE Kanaele, und ein eingehender Kanal
# ist geschenkte Empfangs-Liquiditaet: die Gegenstelle zahlt die On-Chain-
# Gebuehr und bindet ihr eigenes Geld. Einen von 500.000 sat abzulehnen, weil
# er fuer einen Grossrouter zu klein waere, war das Gegenteil von hilfreich.

def test_die_kanal_untergrenze_passt_zu_hundert_euro():
    """100 Euro sind rund 146.000 sat. Die Untergrenze muss deutlich darunter
    liegen -- sonst lehnt der Knoten Kanaele ab, die groesser sind als sein
    eigener."""
    grenze = nodeconfig.Lightningeinstellungen().minchansize
    assert grenze <= 146_000, (
        f"{grenze} sat waeren mehr als der eigene Kanal bei 100 Euro")
    # Und nicht ins Bodenlose: unter LNDs eigener Vorgabe von 20.000 waere es
    # kaum noch ein Kanal.
    assert grenze >= 20_000, grenze


def test_die_untergrenze_landet_auch_in_der_konfiguration():
    """Ein Wert, der nur in der Datenklasse steht, wirkt nicht."""
    text = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert f"minchansize={nodeconfig.Lightningeinstellungen().minchansize}" in text


# ── Wie der Knoten im Lightning-Netz auftritt (04.09.2026) ──────────────────
#
# Der Betreiber: "das sollte aber jeder nutzer unter einstellungen immer selber
# entscheiden koennen ob er das moechte oder nicht ... gibt ja vieleicht
# politische restrektiven die das nicht wollen ... da solte man die
# moeglichkeit haben anonym zu bleiben."
#
# Bis dahin war der Hybrid-Betrieb fest verdrahtet, mit einem Kommentar, der
# behauptete, die Onion-Adresse allein mache anonym. LNDs eigene Beschreibung
# sagt das Gegenteil: "This option will reveal the source IP address of the
# node, and should be used only if privacy is not a concern."

def test_nur_ueber_tor_kuendigt_keine_clearnet_adresse_an():
    """Der Fehler, der beim Durchsehen der drei erzeugten Dateien auffiel:
    "nur ueber Tor" kuendigte den eingetragenen Hostnamen weiter an. Der
    Ausgang lief sauber durch Tor -- und die IP stand trotzdem fuer jeden im
    Graphen. Eine Einstellung, die Anonymitaet verspricht und sie nicht
    liefert, ist schlimmer als gar keine."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="tor", externe_adressen=("meinknoten.example",)))
    assert "meinknoten.example" not in conf
    assert "externalip" not in conf
    # Angekuendigt wird trotzdem -- als Onion. Sonst waere es nicht
    # "anonym teilnehmen", sondern "gar nicht teilnehmen".
    mit = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="tor", externe_adressen=("meinknoten.example",),
        onion_adresse=ONION_A, wachturm_onion=ONION_B))
    angekuendigt = [z.split("=", 1)[1] for z in mit.splitlines()
                    if "externalip=" in z and not z.startswith("#")]
    assert angekuendigt == [f"{ONION_A}:9735", f"{ONION_B}:9911"]


def test_still_kuendigt_auch_keine_onion_an():
    """Sonst waere "still" nicht still: die Onion-Adresse ist genauso eine
    Ankuendigung im Graphen wie eine IP. Auch dann nicht, wenn noch eine aus
    einer frueheren Betriebsart bekannt ist."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="still", onion_adresse=ONION_A, wachturm_onion=ONION_B))
    assert not any(".onion" in z for z in nodeconfig.wirksam(conf))
    assert "tor.v3=false" in conf


def test_nur_ueber_tor_verraet_die_eigene_adresse_nicht():
    """Der Kern: ausgehend NICHTS am Tor vorbei."""
    conf = nodeconfig.baue_lnd(
        nodeconfig.Lightningeinstellungen(sichtbarkeit="tor"))
    assert "tor.skip-proxy-for-clearnet-targets=false" in conf
    # Vollwertig heisst: eingehende Verbindungen bleiben moeglich.
    assert "listen=0.0.0.0:9735" in conf


def test_hybrid_sagt_offen_was_es_kostet():
    conf = nodeconfig.baue_lnd(
        nodeconfig.Lightningeinstellungen(sichtbarkeit="hybrid"))
    assert "tor.skip-proxy-for-clearnet-targets=true" in conf
    assert "verraet die eigene IP" in conf, "die Folge gehoert in die Datei"


def test_still_kuendigt_auch_eine_eingetragene_adresse_nicht_an():
    """Sonst waere die Wahl folgenlos -- der schlimmste Fall bei einer
    Einstellung, die Anonymitaet verspricht."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="still", externe_adressen=("meinknoten.example",)))
    assert "meinknoten.example" not in conf
    assert "externalip" not in conf
    # Und ausgehend trotzdem ueber Tor.
    assert "tor.skip-proxy-for-clearnet-targets=false" in conf


def test_die_vorgabe_gibt_nichts_preis():
    """Wer nicht ausdruecklich waehlt, soll nicht versehentlich seine
    Adresse preisgeben."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "tor.skip-proxy-for-clearnet-targets=false" in conf


def test_stromtrennung_nur_ohne_direkte_verbindungen():
    """LND-Doku: streamisolation "may not be used while direct connections
    are enabled". Beides zusammen waere ein Startfehler."""
    for art in ("tor", "hybrid", "still"):
        conf = nodeconfig.baue_lnd(
            nodeconfig.Lightningeinstellungen(sichtbarkeit=art))
        if "tor.streamisolation=true" in conf:
            assert "tor.skip-proxy-for-clearnet-targets=false" in conf, art


def test_die_selbstentsperrung_ueberlebt_einen_neubau():
    """Bis zum 05.09.2026 kannte die Vorlage die Zeile nicht -- sie wurde nur
    nachtraeglich in die bestehende Datei gesetzt. Wer Monate spaeter eine
    Einstellung aendert und die Datei damit neu bauen laesst, haette sie
    stillschweigend verloren: der Knoten bliebe nach dem naechsten Neustart
    gesperrt und damit offline. Bei Kanaelen, die auf zwoelf Monate
    zugesagt sind, ist das der teuerste Fehler ueberhaupt -- weil ihn
    niemand bemerkt."""
    mit = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        entsperrdatei="/fast/lnd/wallet.pass"))
    assert "wallet-unlock-password-file=/fast/lnd/wallet.pass" in mit

    ohne = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "wallet-unlock-password-file" not in ohne, (
        "wer von Hand entsperren will, bekommt die Zeile nicht untergeschoben")


def test_die_konfiguration_widerspricht_sich_nicht_selbst():
    """Gefunden am 05.09.2026 an einer erzeugten Datei aus dem Pruefstand.

    Der Tor-Block trug den Satz "onlynet wird bewusst NICHT gesetzt". Das
    stimmte, solange es keine Sichtbarkeitswahl gab. Seit es sie gibt, stand
    bei "nur ueber Tor" wenige Zeilen ueber der Zeile onlynet=onion die
    Behauptung, es werde nicht gesetzt.

    Eine Konfiguration ist kein Aufsatz: wer sie liest, muss ihr glauben
    koennen.
    """
    knoten = nodeconfig.Knoteneinstellungen(tor_aktiv=True)
    conf = nodeconfig.setze_netze(nodeconfig.baue_bitcoind(knoten), ["onion"])
    assert "onlynet=onion" in conf
    for zeile in conf.splitlines():
        if not zeile.startswith("#"):
            continue
        klein = zeile.lower()
        assert not ("onlynet" in klein and "nicht gesetzt" in klein), zeile


# ═══════════════════════════════════════════════ lnd.conf nachziehen ═══
#
# Bis zum 09.09.2026 wurde lnd.conf GENAU EINMAL geschrieben. Danach war
# jede Einstellung wirkungslos: Sichtbarkeit, Alias, Farbe. Der Betreiber fragte
# "wenn ich spaeter mal sage ich will nur noch tor, funktioniert das dann
# alles noch?" -- nein, tat es nicht. Der Schalter stand auf "nur Tor" und
# der Knoten kuendigte weiter die Wohnadresse an.
#
# Hier steht der Erbauer, der aus dem heutigen Zustand die richtige Datei
# baut -- und die zwei Fallen, die dabei zuerst auffielen.

def _lnd(**kw):
    grund = dict(alias="Knoten", sichtbarkeit="tor", externe_adressen=(),
                 entsperrdatei="")
    grund.update(kw)
    return nodeconfig.Lightningeinstellungen(**grund)


# ── Falle 1: der Zeitstempel ──────────────────────────────────────────

def test_der_vergleich_uebersieht_den_zeitstempel():
    """baue_lnd stempelt jede Fassung mit dem Erzeugungszeitpunkt.

    Ein naiver Vergleich waere damit IMMER verschieden. Der Waechter haette
    LND alle zehn Minuten neu gestartet -- und bei abgeschaltetem
    Auto-Entsperren jedes Mal die Wallet zugesperrt. Aus einem Abgleich
    waere ein Dauerausfall geworden.
    """
    a = nodeconfig.baue_lnd(_lnd())
    b = nodeconfig.baue_lnd(_lnd())
    b = b.replace("# Erzeugt am", "# Erzeugt am spaeter,")
    assert a != b                                  # der Text unterscheidet sich
    assert not nodeconfig.lnd_muss_neu(a, b)                # die WIRKUNG nicht


def test_eine_echte_aenderung_faellt_sehr_wohl_auf():
    tor = nodeconfig.baue_lnd(_lnd(sichtbarkeit="tor"))
    hybrid = nodeconfig.baue_lnd(_lnd(sichtbarkeit="hybrid",
                             externe_adressen=("203.0.113.7:9735",)))
    assert nodeconfig.lnd_muss_neu(tor, hybrid)
    assert nodeconfig.lnd_muss_neu(hybrid, tor)


def test_wirksam_laesst_kommentare_und_leerzeilen_weg():
    zeilen = nodeconfig.lnd_wirksam(nodeconfig.baue_lnd(_lnd()))
    assert zeilen
    assert all(z and not z.startswith("#") for z in zeilen)
    assert "tor.active=true" in zeilen


# ── Falle 2: der DNS-Aussetzer ────────────────────────────────────────

def test_ein_dns_aussetzer_nimmt_die_adresse_nicht_weg():
    """Ein Netzwackler darf keinen Knoten anhalten.

    Ohne diese Regel wuerde eine voruebergehend gescheiterte Aufloesung die
    angekuendigte Adresse entfernen, LND neu starten und die Wallet
    zusperren -- wegen eines Aussetzers von Sekunden.
    """
    vorhanden = nodeconfig.baue_lnd(_lnd(sichtbarkeit="hybrid",
                                externe_adressen=("203.0.113.7:9735",)))
    behalten = nodeconfig.lnd_adressen_halten(vorhanden, [], ankuendigen=True)
    assert behalten == ("203.0.113.7:9735",)


def test_abgeschaltet_heisst_wirklich_weg():
    """Der Unterschied zum Aussetzer: hier hat jemand entschieden."""
    vorhanden = nodeconfig.baue_lnd(_lnd(sichtbarkeit="hybrid",
                                externe_adressen=("203.0.113.7:9735",)))
    assert nodeconfig.lnd_adressen_halten(vorhanden, [], ankuendigen=False) == ()
    assert nodeconfig.lnd_adressen_halten(vorhanden, ["198.51.100.9"],
                                 ankuendigen=False) == ()


def test_eine_neue_adresse_ersetzt_die_alte():
    vorhanden = nodeconfig.baue_lnd(_lnd(sichtbarkeit="hybrid",
                                externe_adressen=("203.0.113.7:9735",)))
    assert nodeconfig.lnd_adressen_halten(
        vorhanden, ["198.51.100.9"], ankuendigen=True) == ("198.51.100.9:9735",)


def test_der_port_kommt_immer_dazu():
    """Beim ERSTEN Schreiben fehlte er: lightning_bereitstellen reichte die
    blanken IPs durch, waehrend das Nachfuehren sie mit Port schrieb. Es fiel
    nur nicht auf, weil LND ohne Port 9735 annimmt -- also genau die Vorgabe.
    Mit einem abweichenden LIGHTNING_P2P_PORT waere die angekuendigte Adresse
    schlicht falsch gewesen."""
    leer = nodeconfig.baue_lnd(_lnd())
    assert nodeconfig.lnd_adressen_halten(leer, ["198.51.100.9"], ankuendigen=True,
                                 port=9999) == ("198.51.100.9:9999",)
    # IPv6 gehoert in eckige Klammern, sonst frisst der Doppelpunkt den Port.
    assert nodeconfig.lnd_adressen_halten(leer, ["2001:db8::1"], ankuendigen=True,
                                 port=9735) == ("[2001:db8::1]:9735",)


def test_eine_adresse_mit_port_bekommt_keinen_zweiten():
    leer = nodeconfig.baue_lnd(_lnd())
    assert nodeconfig.lnd_adressen_halten(
        leer, ["198.51.100.9:9735"], ankuendigen=True) == ("198.51.100.9:9735",)


# ── Der Erbauer selbst ────────────────────────────────────────────────

def test_der_entsperrweg_ueberlebt_einen_umbau():
    """Er haengt an der Wallet, nicht an der Sichtbarkeit. Wer die
    Betriebsart wechselt, darf nicht nebenbei sein Auto-Entsperren
    verlieren -- der Knoten stuende nach dem naechsten Neustart still."""
    vorhanden = nodeconfig.setze_entsperrdatei(
        nodeconfig.baue_lnd(_lnd(sichtbarkeit="hybrid",
                        externe_adressen=("203.0.113.7:9735",))),
        "/fast/lnd/wallet.pass")
    soll = nodeconfig.lnd_soll(vorhanden, _lnd(sichtbarkeit="tor"))
    assert nodeconfig.lies_entsperrdatei(soll) == "/fast/lnd/wallet.pass"
    assert "externalip=" not in soll
    assert "tor.streamisolation=true" in soll


def test_ohne_entsperrweg_bleibt_es_dabei():
    vorhanden = nodeconfig.baue_lnd(_lnd(sichtbarkeit="tor"))
    soll = nodeconfig.lnd_soll(vorhanden, _lnd(sichtbarkeit="hybrid",
                                      externe_adressen=("203.0.113.7:9735",)))
    assert nodeconfig.lies_entsperrdatei(soll) == ""


def test_alias_und_farbe_kommen_wirklich_an():
    """Befund 14: alias stand als Vorgabe in der Datenklasse und wurde beim
    Einrichten NIE uebergeben. Jeder Knoten dieser Software hiess damit
    SatoshiCortex."""
    soll = nodeconfig.lnd_soll(nodeconfig.baue_lnd(_lnd()),
                      _lnd(alias="dem Knoten im Betrieb", farbe="#3355ff"))
    assert "alias=dem Knoten im Betrieb" in soll
    assert "color=#3355ff" in soll


def test_der_umbau_ist_in_beide_richtungen_wirksam():
    """Der Rueckweg war genauso kaputt wie der Hinweg."""
    tor = nodeconfig.baue_lnd(_lnd(sichtbarkeit="tor"))
    nach_hybrid = nodeconfig.lnd_soll(tor, _lnd(sichtbarkeit="hybrid",
                                       externe_adressen=("203.0.113.7:9735",)))
    assert "externalip=203.0.113.7:9735" in nach_hybrid
    zurueck = nodeconfig.lnd_soll(nach_hybrid, _lnd(sichtbarkeit="tor"))
    assert "externalip=" not in zurueck
    assert "tor.skip-proxy-for-clearnet-targets=false" in zurueck


def test_die_aussetzer_regel_gilt_fuer_bitcoind_genauso():
    """Der Waechter war dagegen laengst geschuetzt, der Speichern-Weg nicht.
    Wer zufaellig in einer Aussetzer-Sekunde auf Speichern drueckte, stand
    danach ohne angekuendigte Adresse da -- und nichts sagte es ihm."""
    conf = nodeconfig.setze_adressen(
        nodeconfig.baue_bitcoind(nodeconfig.Knoteneinstellungen()),
        ["203.0.113.7"])
    assert nodeconfig.lies_adressen(conf) == ["203.0.113.7"]
    assert nodeconfig.adressen_halten(conf, [], True) == ("203.0.113.7",)
    assert nodeconfig.adressen_halten(conf, [], False) == ()
    assert nodeconfig.adressen_halten(
        conf, ["198.51.100.9"], True) == ("198.51.100.9",)
    # Bitcoind schreibt seine externalip OHNE Port -- anders als LND.
    assert all(":" not in a
               for a in nodeconfig.adressen_halten(conf, ["198.51.100.9"], True))


def test_ipv6_in_klammern_bekommt_seinen_port():
    """Eine Adresse, die schon in eckigen Klammern steht, aber ohne Port --
    so kommt sie aus mancher Quelle."""
    leer = nodeconfig.baue_lnd(_lnd())
    assert nodeconfig.lnd_adressen_halten(
        leer, ["[2001:db8::1]"], ankuendigen=True) == ("[2001:db8::1]:9735",)
    assert nodeconfig.lnd_adressen_halten(
        leer, ["[2001:db8::1]:9999"], ankuendigen=True) == ("[2001:db8::1]:9999",)


# ── Die Reihenfolge beim Herunterfahren (11.09.2026) ───────────────────────
#
# Der Betreiber: "ich kann den docker stack garnicht beenden .. der lnd container
# laeuft einfach weiter". Er lief nicht weiter, er raeumte auf -- bis zu drei
# Minuten lang. Waehrenddessen stand in seinem Protokoll:
#
#   [ERR] GetInfo: lookup bitcoind on 127.0.0.11:53: no such host
#
# bitcoind war schon weg, LND noch nicht. Ohne depends_on kennt Compose keine
# Reihenfolge; LND verliert dann mitten im Herunterfahren seinen Knoten und
# schreibt Fehler, die wie ein Schaden aussehen und keiner sind.

def _dienstblock(name: str) -> str:
    """Der Abschnitt eines Dienstes aus der Compose.

    Bewusst ohne YAML-Bibliothek: die steht in keiner unserer
    Anforderungsdateien und waere nur ueber eine fremde Abhaengigkeit da.
    Eine Pruefung, die still verschwindet, wenn jemand bandit austauscht,
    ist keine.
    """
    text = _lies("docker-compose.yml")
    anfang = text.index(f"\n  {name}:\n")
    rest = text[anfang + 1:]
    naechster = [rest.index(f"\n  {d}:\n") for d in
                 ("app", "bitcoind", "lnd", "tor") if f"\n  {d}:\n" in rest]
    return rest[:min(naechster)] if naechster else rest


def test_lnd_stoppt_vor_seinem_knoten():
    """depends_on heisst beim Starten "nach bitcoind" und beim Stoppen
    "vor bitcoind". Der zweite Teil ist hier der wichtigere."""
    block = _dienstblock("lnd")
    assert "depends_on:" in block, (
        "ohne diese Zeile stoppen beide gleichzeitig, und LND verliert "
        "mitten im Herunterfahren seinen Knoten")
    haengt_an = block[block.index("depends_on:"):]
    haengt_an = haengt_an[:haengt_an.index("\n    container_name")] \
        if "\n    container_name" in haengt_an else haengt_an[:400]
    assert "bitcoind:" in haengt_an
    assert "tor:" in haengt_an, "die Onion-Adresse haengt an Tor"


def test_die_dienste_bekommen_zeit_zum_aufraeumen():
    """Drei Minuten sind kein Zufallswert: LND baut beim Herunterfahren den
    halb fertigen Netzabgleich ab, und das dauert bei tausend Kanaelen je
    Minute. Wer hier kuerzt, schiesst mitten in die Kanal-Datenbank --
    und bitcoind braucht noch mehr, es schreibt den chainstate weg."""
    assert "stop_grace_period: 3m" in _dienstblock("lnd")
    assert "stop_grace_period: 10m" in _dienstblock("bitcoind")


# ── Eine Einstellung, die den Container nie erreicht (12.09.2026) ──────────
#
# Der Betreiber: "also das andere was ich da vorher drin stehen hatte in der env
# brauch ich dann nicht mehr?" -- und beim Nachsehen fiel auf, dass die NEUEN
# Werte gar nicht angekommen waeren: sie standen in settings.py und in der
# example.env, aber nicht im environment-Block der Compose.
#
# Das ist genau der Fehler, den dieses Projekt am 01.09.2026 schon einmal
# behoben hat, als die alten OIDC-Variablen flogen: eine Einstellung, die man
# setzen kann, ohne dass sich etwas aendert. Bei einer SICHERHEITS-Einstellung
# ist das die schlimmste Sorte -- man glaubt, man habe abgeschlossen.

ANMELDUNG_DURCHREICHEN = ["OIDC_ISSUER", "OIDC_CLIENT_ID",
                          "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URL",
                          "TLS_EXTERN"]


@pytest.mark.parametrize("name", ANMELDUNG_DURCHREICHEN)
def test_die_anmeldewerte_erreichen_den_container(name):
    """Was die Anwendung liest, muss die Compose auch hineinreichen."""
    block = _dienstblock("app")
    assert f"{name}: ${{{name}:-" in block, (
        f"{name} steht in settings.py, kommt aber nie im Container an")


@pytest.mark.parametrize("name", ANMELDUNG_DURCHREICHEN)
def test_die_anmeldewerte_stehen_auch_in_der_vorlage(name):
    """Und wer sie setzen soll, muss sie auch finden."""
    assert name in _lies("example.env"), (
        f"{name} wird gelesen und durchgereicht, aber in der example.env "
        "erwaehnt es niemand")


def test_die_anmeldung_ist_ab_werk_aus():
    """Leer heisst aus. Ein Stapel, der frisch ausgerollt nach einem
    Ausweisdienst verlangt, den es noch nicht gibt, waere unbenutzbar."""
    block = _dienstblock("app")
    for name in ANMELDUNG_DURCHREICHEN:
        assert f"{name}: ${{{name}:-}}" in block, (
            f"{name} braucht eine leere Vorgabe, sonst haengt der Start an "
            "einer Variablen, die niemand gesetzt hat")


# ══════════ Der Wachturm muss erreichbar sein (17.09.2026) ═════════════════
#
# Eingeschaltet war er seit dem ersten Tag, und die Oberflaeche zeigte seine
# Adresse zum Weitergeben. Erreichen konnte ihn trotzdem niemand: kein Port in
# der Compose, keine Clearnet-Adresse. Mit Tor legt LND dem Turm von selbst
# einen Onion-Dienst an (watchtower/standalone.go, v0.21.3-beta) -- im
# Clearnet braucht er Port und Adresse.

def test_der_wachturm_bleibt_auf_lnds_vorgabeport():
    """KEINE ausdrueckliche listen-Zeile. LND horcht ohne sie auf :9911 --
    dem Port, den die Compose abbildet. Die Zeile aenderte nichts, zwaenge
    aber jeden bestehenden Knoten beim Einspielen zu einem LND-Neustart."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert "watchtower.active=true" in conf
    assert "watchtower.listen" not in conf


def test_ohne_hybrid_aendert_der_turm_nichts_an_der_wirksamen_konfiguration():
    """Wer nur ueber Tor betreibt, soll durch den Turm keinen zweiten
    LND-Neustart bekommen: die Turm-Zeilen sind dort reine Kommentare, und
    der Waechter vergleicht nur, was LND wirklich liest."""
    for sicht in ("tor", "still"):
        conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
            sichtbarkeit=sicht, externe_adressen=("meinknoten.example:9735",)))
        turm = [z for z in nodeconfig.lnd_wirksam(conf)
                if z.startswith("watchtower.")]
        assert turm == ["watchtower.active=true"], (sicht, turm)


def test_hybrid_kuendigt_den_turm_unter_seinem_eigenen_port_an():
    """Die Adressen tragen schon den Kanal-Port. Haengte man den Turm-Port
    einfach an, stuende der Turm unter host:9735 -- dort ist er nie."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="hybrid", externe_adressen=("meinknoten.example:9735",)))
    assert "watchtower.externalip=meinknoten.example:9911" in conf
    assert "watchtower.externalip=meinknoten.example:9735" not in conf


def test_ein_geaenderter_turmport_wird_angekuendigt():
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="hybrid", externe_adressen=("203.0.113.7:9735",),
        wachturm_port=19911))
    assert "watchtower.externalip=203.0.113.7:19911" in conf


def test_ipv6_behaelt_beim_turm_seine_klammern():
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="hybrid", externe_adressen=("[2001:db8::7]:9735",)))
    assert "watchtower.externalip=[2001:db8::7]:9911" in conf


def test_nur_tor_verraet_auch_ueber_den_turm_keine_adresse():
    """Dieselbe Regel wie bei den Kanal-Adressen, aus demselben Grund: sonst
    verspricht die Wahl Anonymitaet und liefert sie nicht."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="tor", externe_adressen=("meinknoten.example:9735",)))
    assert "meinknoten.example" not in conf
    assert "externalip" not in conf
    # Mit bekannter .onion steht GENAU die da -- und sonst nichts.
    mit = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="tor", externe_adressen=("meinknoten.example:9735",),
        wachturm_onion=ONION_B))
    turm = [z for z in mit.splitlines() if z.startswith("watchtower.externalip=")]
    assert turm == [f"watchtower.externalip={ONION_B}:9911"]


def test_still_verraet_auch_ueber_den_turm_keine_adresse():
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="still", externe_adressen=("meinknoten.example:9735",),
        wachturm_onion=ONION_B))
    assert "meinknoten.example" not in conf
    assert "externalip" not in conf


def test_hybrid_nennt_den_turm_ueber_tor_und_im_clearnet():
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="hybrid", externe_adressen=("203.0.113.7:9735",),
        onion_adresse=ONION_A, wachturm_onion=ONION_B))
    zeilen = conf.splitlines()
    assert f"watchtower.externalip={ONION_B}:9911" in zeilen
    assert "watchtower.externalip=203.0.113.7:9911" in zeilen
    assert f"externalip={ONION_A}:9735" in zeilen
    assert "externalip=203.0.113.7:9735" in zeilen


def test_knoten_und_turm_bleiben_getrennte_adressen():
    """Ueber die Turm-Adresse soll niemand auf den Knoten schliessen. Eine
    verwechselte Zuordnung waere genau das."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="tor", onion_adresse=ONION_A, wachturm_onion=ONION_B))
    assert nodeconfig.lies_lnd_onion(conf) == ONION_A
    assert nodeconfig.lies_wachturm_onion(conf) == ONION_B
    # Und die Clearnet-Liste bleibt leer: sonst setzte ein DNS-Aussetzer die
    # .onion als Clearnet-Adresse wieder ein.
    assert nodeconfig.lies_lnd_adressen(conf) == []


def test_eine_lnd_conf_von_0_62_faellt_auf():
    alt = "[Tor]\ntor.active=true\ntor.control=tor:9051\ntor.v3=true\n"
    assert nodeconfig.lnd_nach_altem_muster(alt)
    neu = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen())
    assert not nodeconfig.lnd_nach_altem_muster(neu)


def test_die_turmzeile_verfaelscht_die_kanal_adressen_nicht():
    """lies_lnd_adressen liest Zeilen, die mit externalip= BEGINNEN. Eine
    watchtower.externalip-Zeile darf dort nicht als Kanal-Adresse auftauchen
    -- sonst kuendigte der Knoten beim naechsten Nachziehen host:9911 als
    Lightning-Adresse an."""
    conf = nodeconfig.baue_lnd(nodeconfig.Lightningeinstellungen(
        sichtbarkeit="hybrid", externe_adressen=("meinknoten.example:9735",)))
    assert nodeconfig.lies_lnd_adressen(conf) == ["meinknoten.example:9735"]


def test_die_compose_veroeffentlicht_den_wachturm():
    assert "${WATCHTOWER_PORT:-9911}:9911" in _dienstblock("lnd")


def test_die_env_nennt_den_turmport():
    import re
    assert re.search(r"^WATCHTOWER_PORT=9911$", _lies("example.env"), re.M)


# ── Das feste Netz: Compose und Anwendung sprechen dieselben Zahlen ────────
#
# Der Befund vom 17.09.2026: Tor reichte an 127.0.0.1 in seinem eigenen
# Container weiter. Seitdem stehen die Ziele als feste Adressen in der torrc
# -- und die muessen mit dem uebereinstimmen, was Docker den Containern gibt.
# Stuende in der Compose .21 und in netz.py .12, liefe Tor wieder ins Leere,
# und nichts an der Oberflaeche wuerde es sagen.

def test_jeder_dienst_hat_in_der_compose_die_adresse_aus_netz_py():
    from satcortex import netz
    for dienst, teil in netz.HOSTTEIL.items():
        erwartet = (f"ipv4_address: ${{NETWORK_PREFIX:-{netz.PRAEFIX_VORGABE}}}"
                    f".{teil}")
        assert erwartet in _dienstblock(dienst), dienst


def test_das_netz_hat_ein_festes_adressband():
    from satcortex import netz
    text = _lies("docker-compose.yml")
    netzblock = text[text.index("\nnetworks:\n"):]
    vorgabe = f"${{NETWORK_PREFIX:-{netz.PRAEFIX_VORGABE}}}"
    assert f"subnet: {vorgabe}.0/24" in netzblock
    assert f"gateway: {vorgabe}.1" in netzblock
    # Frei vergeben wird nur oberhalb der festen Adressen.
    assert f"ip_range: {vorgabe}.128/25" in netzblock
    # Unter NEUEM Namen: das alte Netz hat ein Adressband, das Docker selbst
    # vergeben hat, und auf dem lehnt Docker feste Adressen ab.
    assert "name: satcortex-netz" in netzblock


def test_die_anwendung_bekommt_dasselbe_praefix_wie_das_netz():
    from satcortex import netz
    assert (f"NETWORK_PREFIX: ${{NETWORK_PREFIX:-{netz.PRAEFIX_VORGABE}}}"
            in _dienstblock("app"))
    assert re.search(rf"^NETWORK_PREFIX={re.escape(netz.PRAEFIX_VORGABE)}$",
                     _lies("example.env"), re.M)


def test_die_einstellungen_nehmen_die_vorgabe_aus_netz_py(monkeypatch):
    from satcortex import netz, settings
    monkeypatch.delenv("NETWORK_PREFIX", raising=False)
    assert settings._praefix("NETWORK_PREFIX") == netz.PRAEFIX_VORGABE


def test_ein_kaputtes_praefix_legt_die_anwendung_nicht_lahm(monkeypatch):
    from satcortex import netz, settings
    monkeypatch.setenv("NETWORK_PREFIX", "10.83.33.0")
    assert settings._praefix("NETWORK_PREFIX") == netz.PRAEFIX_VORGABE


def test_tor_hat_keinen_steuerport_mehr():
    """Die Cookie-Datei, die ihn schuetzen sollte, lag unter /fast/tor --
    und /fast sieht jeder Container, die Weboberflaeche eingeschlossen."""
    torrc = nodeconfig.baue_tor(("bitcoind", "lnd", "wachturm"))
    wirksam = nodeconfig.wirksam(torrc)
    assert not any(z.startswith(("ControlPort", "CookieAuthentication",
                                 "HashedControlPassword")) for z in wirksam)
    assert "9051" not in _lies("images/tor/Dockerfile").split("EXPOSE", 1)[1] \
        .splitlines()[0]
    assert "9051" not in _dienstblock("tor")


def test_die_torrc_hat_keinen_zeitstempel():
    """Der Waechter vergleicht sie im Ganzen. Ein Stempel machte jede Fassung
    "neu", und Tor startete bei jedem Durchgang ohne Anlass neu."""
    assert nodeconfig.baue_tor(("lnd",)) == nodeconfig.baue_tor(("lnd",))
    assert "{{" not in nodeconfig.baue_tor(())


def test_die_pruefung_hat_ihren_eigenen_socks_port_mit_erweiterten_codes():
    """ExtendedErrors nur dort: bitcoind und LND bekommen auf 9050 weiter die
    Codes, die sie kennen."""
    from satcortex import settings
    wirksam = nodeconfig.wirksam(nodeconfig.baue_tor(()))
    assert "SocksPort 0.0.0.0:9050" in wirksam
    assert "SocksPort 0.0.0.0:9052 ExtendedErrors" in wirksam
    assert settings.Einstellungen().tor_pruef_port == 9052


def test_jeder_dienst_laeuft_mit_schreibgeschuetzter_wurzel():
    """Befund vom 22.09.2026: nur die Anwendung hatte read_only, waehrend
    bitcoind, lnd und tor mit schreibbarem Wurzeldateisystem liefen -- allen
    voran LND, der Behaelter, in dem die Wallet liegt.

    Ihre eigenen Daten liegen in eingehaengten Bereichen; die Wurzel braucht
    keiner von ihnen. Was sie brauchen, ist ein /tmp, und das bekommen sie
    als tmpfs.
    """
    import re
    compose = _lies("docker-compose.yml")
    # Jeder Dienstblock -- zwei Leerzeichen Einrueckung, Doppelpunkt.
    bloecke = re.split(r"\n  (?=[a-z][\w-]*:\n)", compose)
    gefunden = {}
    for b in bloecke:
        m = re.match(r"([a-z][\w-]*):\n", b)
        if not m or "image:" not in b:
            continue
        gefunden[m.group(1)] = ("read_only: true" in b, "tmpfs:" in b)

    assert set(gefunden) == {"app", "bitcoind", "lnd", "tor"}, gefunden
    ohne = [n for n, (ro, tm) in gefunden.items() if not (ro and tm)]
    assert not ohne, ohne
