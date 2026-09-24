/* SatoshiCortex — Oberflaeche.
 *
 * Ohne Framework, wie bei AIcortex: das haelt das Buendel winzig und den
 * Container klein. Sprache DE/EN, im Browser gemerkt.
 *
 * SICHERHEIT: Werte, die vom Server kommen, werden ausschliesslich ueber
 * textContent gesetzt -- nie ueber innerHTML. Nur unsere eigenen, fes
 * eingebauten Texte duerfen Markup enthalten (data-i18n-html).
 */
"use strict";

/* ── Uebersetzungen ─────────────────────────────────────────────────────── */
const I18N = {
  de: {
    e_name_haengt: "Achtung: „{name}“ lässt sich seit {dauer} nicht mehr auflösen. Angekündigt bleibt darum die Adresse von vorher — nach der nächsten Zwangstrennung gehört die jemand anderem, und dein Knoten wirbt mit einer fremden. Von außen löst der Name meist einwandfrei auf; sieh zuerst beim DNS in deinem eigenen Netz nach (AdGuard, Pi-hole, Router).",
    dauer_min: "{n} Minuten",
    dauer_std: "{n} Stunden",
    dauer_tage: "{n} Tagen",
    ez_titel: "Einzahlen",
    ez_lead: "Auf diese Adresse schickst du Bitcoin an deinen Knoten. Es landet in der On-Chain-Wallet von LND — dieselbe Wallet, die an deinen vierundzwanzig Wörtern hängt. Das ist eine gewöhnliche Bitcoin-Adresse: Unterscheidet deine Börse zwischen Bitcoin und Lightning, wähle Bitcoin. Frei verfügbar, bis du daraus einen Kanal öffnest; dann ist es im Kanal gebunden, bis der wieder schließt.",
    ez_holen: "Adresse anzeigen",
    ez_neue: "Neue Adresse",
    ez_art_titel: "Andere Adressform",
    ez_art_hinweis: "Manche Börsen können bis heute nicht an Taproot senden. Sagt deine „ungültige Adresse“, nimm SegWit — es liegt dann nicht an deinem Knoten.",
    ez_art_taproot: "Taproot — beginnt mit bc1p",
    ez_art_taproot_d: "Die günstigste Form. Ein Kanal, den du daraus finanzierst, kostet weniger Gebühren.",
    ez_art_segwit: "SegWit — beginnt mit bc1q",
    ez_art_segwit_d: "Etwas teurer, dafür kann praktisch jede Börse dorthin senden.",
    ez_art_kompatibel: "Kompatibel — beginnt mit 3",
    ez_art_kompatibel_d: "Die teuerste Form, aber auch sehr alte Dienste kommen damit zurecht.",
    ez_kopieren: "Kopieren",
    ez_kopiert: "Kopiert.",
    ez_oeffnen: "In Wallet öffnen",
    ez_hinweis: "Deine Wallet hat keine Adresse — sie hat beliebig viele, und alle gehören dir. Aus deinen vierundzwanzig Wörtern rechnet sie sie aus; auf dem Zettel ändert sich dadurch nichts, und alte Adressen bleiben für immer gültig. Hier steht die aktuelle unbenutzte. Sie bleibt dieselbe, bis jemand darauf zahlt — danach bekommst du von allein eine frische. Das ist Absicht: eine wiederbenutzte Adresse zeigt jedem, der die Blockkette liest, alle Zahlungen darauf und dein Guthaben.",
    kein_macaroon: "SatoshiCortex konnte sich seine Berechtigung nicht anlegen. Läuft LND schon vollständig?",
    gb_titel: "Gebühren",
    gb_lead: "Was du fürs Weiterleiten fremder Zahlungen nimmst. Deutlich über dem Üblichen wirst du schlicht gemieden — Gebühren sind hier kein Preisschild, sondern ein Lenkungssignal. Was „üblich“ heißt, steht nicht in diesem Text, sondern misst dein Knoten selbst.",
    gb_netz_titel: "Was das Netz nimmt",
    gb_messen: "Jetzt messen",
    gb_messen_laeuft: "Der Graph wird gelesen …",
    gb_netz_zahlen: "Median {median} ppm — die Hälfte aller Richtungen nimmt weniger · Grundgebühr {basis} msat · {linien} Richtungen in {kanaele} Kanälen · gemessen am {tag}",
    gb_netz_spanne: "Die mittleren 50 % liegen zwischen {p25} und {p75} ppm.",
    gb_stufe_von_bis: "{von}–{bis}",
    gb_stufe_ab: "ab {von}",
    gb_stufe_anteil: "{anteil} % {spanne} ppm",
    gb_netz_nie: "Noch nicht gemessen. Dein Knoten liest dafür den gesamten Netzgraphen — das dauert und passiert einmal am Tag von selbst.",
    gb_netz_eigen: "Du nimmst zurzeit {eigen} ppm.",
    gb_netz_eigen_keine: "Was du zurzeit nimmst, steht noch nicht im Graphen — dafür braucht es mindestens einen öffentlichen Kanal.",
    gb_band: "Vier Wochen: {unten}–{oben} ppm, aus {tage} Messtagen. Das Fenster wandert mit; der heutige Tag zählt nicht in sein eigenes Band.",
    gb_band_sammelt: "Das Vier-Wochen-Band braucht {braucht} Messtage. Bisher: {tage}.",
    gb_uebernehmen: "Median übernehmen",
    gb_uebernommen: "In das Feld unten eingetragen — gesetzt wird erst mit „Gebühren setzen“.",
    gb_automatik: "Gebühren dem Netz nachführen",
    gb_automatik_d: "Einmal am Tag den Satz auf den Netz-Median setzen — begrenzt auf die Spanne der letzten vier Wochen. Betrifft alle Kanäle und nie die Grundgebühr.",
    gb_a_median: "Zuletzt auf {satz} ppm gesetzt — das ist der Netz-Median.",
    gb_a_gedeckelt: "Zuletzt auf {satz} ppm gesetzt — der Netz-Median lag darüber, das Vier-Wochen-Band hat gedeckelt.",
    gb_a_angehoben: "Zuletzt auf {satz} ppm gesetzt — der Netz-Median lag darunter, das Vier-Wochen-Band hat angehoben.",
    gb_a_unveraendert: "Nichts zu tun: {satz} ppm ist bereits gesetzt.",
    gb_a_sammelt: "Eingeschaltet, greift aber noch nicht — es fehlen Messtage.",
    gb_a_keine_kanaele: "Eingeschaltet, greift aber noch nicht: ohne Kanal gibt es nichts zu setzen.",
    gb_a_keine_messung: "Eingeschaltet, greift aber noch nicht — es fehlt die erste Messung.",
    gb_a_aus: "Aus. Der Satz bleibt, wo du ihn hingestellt hast.",
    gb_a_wuerde: "Würde jetzt {satz} ppm setzen.",
    graph_nicht_aktuell: "Die Netzkarte ist noch nicht vollständig — gemessen wird erst, wenn sie steht.",
    graph_leer: "Im Netzgraphen steht noch kein einziger Kanal.",
    messung_fehlgeschlagen: "Die Messung kam nicht zustande.",
    gb_kanal: "Für welchen Kanal",
    gb_kanal_d: "Der eigentliche Betriebsgriff liegt hier: teuer machen, wo ein Kanal leerläuft, billig, wo er aufgefüllt werden soll.",
    gb_alle: "Alle Kanäle",
    gb_satz: "Satz (ppm)",
    gb_satz_d: "Millionstel des weitergeleiteten Betrags. 100 ppm heißt: 100 Sats bei einer Million.",
    gb_basis: "Grundgebühr (Millisatoshi)",
    gb_basis_d: "Pro Weiterleitung, unabhängig vom Betrag. Null ist verbreitet: die Wegfindung bestraft Grundgebühren stärker als den Satz.",
    gb_setzen: "Gebühren setzen",
    gb_gesetzt_alle: "Gesetzt — für alle Kanäle. Bis es sich im Netz herumgesprochen hat, dauert es ein paar Minuten.",
    gb_gesetzt_einer: "Gesetzt — für diesen Kanal.",
    gebuehren_abgelehnt: "LND hat das abgelehnt: {einzelheit}",
    lk_ich_titel: "Dein Knoten im Netz",
    lk_alias: "Name",
    lk_kennung: "Kennung",
    lk_adressen: "Angekündigt unter",
    lk_keine_adressen: "keine — so kann niemand einen Kanal zu dir öffnen",
    lk_gegenstellen: "Verbindungen",
    lk_gegenstellen_n: "{n} Knoten",
    lk_kanaele_stand: "Kanäle",
    lk_kanaele_stand_n: "{aktiv} aktiv · {still} still · {offen} im Aufbau",
    lk_guthaben_titel: "Guthaben",
    lk_guthaben_d: "Zwei verschiedene Dinge, deshalb getrennt. Was on-chain liegt, kannst du jederzeit ausgeben. Was in einem Kanal liegt, ist gebunden, bis der Kanal geschlossen wird — und was auf der anderen Seite liegt, gehört nicht dir. Es ist aber genau das, was du empfangen kannst.",
    lk_onchain: "On-Chain",
    lk_kanal_hier: "In Kanälen, auf deiner Seite",
    lk_kanal_frei: "Davon wirklich ausgebbar",
    lk_kanal_drueben: "Auf der Gegenseite (= dein Empfangsraum)",
    lk_reserve: "{n} sat davon sind Kanalreserve und lassen sich nicht ausgeben. Jeder Kanal hält auf beiden Seiten ein Prozent seiner Kapazität zurück — das ist das Pfand, das einen Betrugsversuch teuer macht. Bei kleinen Kanälen fällt es ins Gewicht.",
    lk_kanaele_titel: "Kanäle",
    lk_kanaele_d: "Der Balken ist die eigentliche Aussage: liegt alles auf einer Seite, leitet der Kanal in eine Richtung nichts mehr weiter. Links dein Anteil, rechts der der Gegenstelle.",
    lk_erreichbar: "{p} % erreichbar",
    lk_erreichbar_titel: "Anteil der Zeit, in der deine Gegenstelle dich erreichen konnte — seit {seit}. LND führt das je Kanal mit.",
    lk_erreichbar_gesamt: "Über alle Kanäle warst du zu {p} % der Zeit erreichbar, gewichtet nach Laufzeit. Das ist die Zahl, an der andere Betreiber dich messen — und die du zusagst, wenn du dich auf einen Swap über Monate einlässt.",
    lk_keine_kanaele: "Noch keine Kanäle — und damit steht dein Knoten gar nicht im Graphen. Das Netz reicht die Namensmeldung eines Knotens erst weiter, wenn es von ihm einen angekündigten Kanal kennt (BOLT 7). Bis dahin sehen Verzeichnisse nur deinen Schlüssel, keinen Namen, keine Farbe, keine Adresse. Mit dem ersten öffentlichen Kanal ändert sich das auf einen Schlag.",
    lk_kanal_hier_kurz: "{n} hier",
    lk_kanal_drueben_kurz: "{n} drüben",
    lk_privat: "privat",
    lk_still: "still",
    lk_weiter_titel: "Weitergeleitet",
    lk_weiter_d: "Nicht deine eigenen Zahlungen, sondern fremde, die durch deinen Knoten gelaufen sind. Das ist der Moment, in dem er wirklich Teil des Netzes ist.",
    lk_weiter_keine: "Noch nichts weitergeleitet. Das kommt nicht am ersten Tag: LND wählt Wege nach vergangenen Erfolgen, und dein Knoten ist dort noch ein unbeschriebenes Blatt. Was hilft, sind Betriebszeit und Liquidität auf der richtigen Seite.",
    lk_weiter_summe: "{n} Weiterleitungen · {menge} Sats bewegt · {gebuehr} Sats verdient",
    lg_titel: "Das Netz",
    lg_lead: "Wie groß der Graph ist, den dein Knoten kennt — und wie du dich darin ausnimmst.",
    lg_graph_laedt: "Der Graph wird noch geladen. Dein Knoten kennt bisher nur einen Teil des Netzes — diese Zahlen wachsen in den nächsten Stunden noch deutlich.",
    lg_knoten: "Knoten im Graphen",
    lg_kanaele: "Öffentliche Kanäle",
    lg_kapazitaet: "Öffentliche Kapazität",
    lg_median: "Median-Kanalgröße",
    lg_grad: "Kanäle je Knoten (Mittel)",
    lg_gegen_titel: "Deine Kanalpartner",
    lg_gegen_d: "Knoten, mit denen du einen Kanal hast. Anzahl und Qualität der Kanalpartner entscheiden mehr über Weiterleitungen als die Gesamtsumme in den Kanälen.",
    lg_gegen_keine: "Noch keine. Kanalpartner hast du erst, wenn ein Kanal steht — eine Verbindung allein macht noch keinen.",
    lnsicht_folge_tor: "In dieser Betriebsart gilt kein Clearnet: dein Bitcoin-Knoten spricht ausschließlich über Tor (onlynet=onion), Lightning ebenso. Die Häkchen für IPv4 und IPv6 bleiben als deine Voreinstellung stehen und gelten wieder, sobald du zurückschaltest — jetzt haben sie keine Wirkung. Der Abgleich wird dadurch deutlich langsamer.",
    lnsicht_folge_still: "Es wird nichts angekündigt, also auch keine Adresse — niemand erreicht dich von außen. Ausgehend telefonierst du weiter über die Netze, die du unten angehakt hast.",
    wsw_titel: "Wallet-Software im Heimnetz",
    wsw_lead: "Deine eigene Wallet — auch eine mit Hardware-Gerät — kann diesen Knoten als Hintergrund benutzen, statt einen fremden Server zu fragen. Dann prüft dein Knoten deine Zahlungen, und niemand sonst erfährt, welche Adressen dir gehören.",
    wsw_schalter: "Wallet-Software aus meinem Heimnetz zulassen",
    wsw_erklaerung: "Sparrow ist der übliche Weg: Datei → Einstellungen → Server → Bitcoin Core, dann die Angaben unten eintragen. Deine Schlüssel bleiben dabei bei Sparrow beziehungsweise auf deinem Hardware-Gerät — im Knoten wird keine Wallet angelegt, das schreibt Sparrow selbst so. Weil txindex bei uns an ist, bekommst du dort auch die Funktionen, die sonst einen Electrum-Server brauchen. Was die Freigabe erlaubt: die Kette befragen und Transaktionen einreichen. Geld bewegen kann damit niemand, denn im Knoten liegen gar keine Schlüssel.",
    wsw_netz: "Dein Heimnetz",
    wsw_netz_d: "Nur aus diesem Netz wird der Zugang angenommen. Leer lassen, dann wird das Netz dieser Seite vorgeschlagen. Öffentliche Netze werden abgelehnt — das hier ist keine Freigabe ins Internet.",
    wsw_daten: "Das trägst du in deine Wallet-Software ein",
    wsw_feld: "Server:   {host}\nPort:     {port}\nBenutzer: {benutzer}\nPasswort: {passwort}",
    wsw_hinweis: "Das Passwort steht hier im Klartext, weil du es sonst nirgends herbekommst. Es gibt Zugriff auf die Kettendaten deines Knotens, nicht auf Guthaben.",
    wsw_port: "Damit das wirkt, muss der Port auch veröffentlicht sein: in deiner .env RPC_BIND=0.0.0.0 setzen und den Stapel neu bereitstellen. Ohne das bleibt die Schnittstelle auf dem Server selbst und dein Heimnetz kommt nicht daran — die Freigabe hier allein genügt nicht.",
    f_aus: "Aus",
    wsw_netz_fehlt: "Trag dein Heimnetz ein — aus der Adresse dieser Seite lässt es sich nicht ableiten. Es sieht aus wie 192.168.178.0/24.",
    wsw_danach: "Die Zugangsdaten — Benutzer und Passwort — entstehen erst mit der Konfiguration. Du findest sie danach unter Einstellungen → Wallet-Software, mit Kopierknopf.",
    wsw_spaeter: "Aus. Das lässt sich jederzeit unter Einstellungen nachholen — es ändert nichts an der Kette und nichts an Lightning.",
    wsw_gespeichert: "Freigegeben. Der Knoten startet gleich neu.",
    wsw_zu: "Zugang wieder geschlossen. Der Knoten startet gleich neu.",
    lnsicht_titel: "Wie dein Knoten von außen sichtbar ist",
    lnsicht_lead: "Gilt für beides — Bitcoin und Lightning. Die Schalter darunter sind die Feinheit innerhalb dieser Wahl. Erreichbar und am Weiterleiten beteiligt bist du in den ersten beiden Fällen; anonym heißt nicht eingeschränkt.",
    lnsicht_waehlen: "Bitte wähle eine der drei — es gibt hier bewusst keine Vorgabe. Von dieser Wahl hängt ab, ob dein Anschluss weltweit nachschlagbar ist.",
    lnsicht_folge_hybrid: "Deine IP-Adresse steht damit im Lightning-Graphen und in den Bitcoin-Adresslisten — öffentlich nachschlagbar und mit deinem Knoten verknüpft. Das ist die schnellste und am besten erreichbare Betriebsart, und dieser Preis gehört dazu.",
    lnsicht_tor: "Nur über Tor",
    lnsicht_tor_d: "Angekündigt wird ausschließlich deine .onion-Adresse, und auch ausgehend läuft alles über Tor — bei Bitcoin wie bei Lightning. Vollwertiges Mitglied: erreichbar, im Graphen, kann weiterleiten — nur weiß niemand, wo dein Knoten steht. Deutlich langsamer beim Abgleich, und du brauchst Gegenstellen, die Tor sprechen.",
    lnsicht_hybrid: "Tor und Clearnet",
    lnsicht_hybrid_d: "Zusätzlich deine Adresse aus dem Feld unten — Router-Freigabe auf 8333 und 9735 (dazu 9911 für den Wachturm), gern über DynDNS. Schneller und besser erreichbar. Deine IP wird damit öffentlich; LND warnt davor ausdrücklich.",
    lnsicht_still: "Gar nicht ankündigen",
    lnsicht_still_d: "Weder .onion noch IP. Du holst dir Blöcke und kannst Kanäle zu anderen öffnen — aber niemand erreicht dich von außen, und weiterleiten geht nicht. Im Netz bist du dann Zuschauer, nicht Teilnehmer.",
    lgi_klartext: "Achtung: Eine dieser Zeilen enthält deine öffentliche IP-Adresse — also deinen Anschluss zu Hause, dauerhaft mit deinem Knoten verknüpft und für jeden im Lightning-Graphen nachschlagbar. Das ist die Betriebsart „Tor und Clearnet“, und sie ist umstellbar. Rückgängig machen lässt sie sich nicht: die Adresse ist bereits unterwegs.",
    lgi_titel: "Deine Verbindungsadresse",
    lgi_lead: "Das ist die Zeile, die jemand braucht, um einen Kanal zu dir zu öffnen: Kennung, Adresse, Port. Gib sie weiter, wo du magst — sie ist ohnehin öffentlich, dein Knoten kündigt sie im Netz an.",
    lgi_kopieren: "Kopieren",
    lgi_kopiert: "Kopiert.",
    unt_geprueft: "Nachgerechnet: gültig, erzeugt mit deinem Knotenschlüssel.",
    unt_nicht_gueltig: "Nachgerechnet: NICHT gültig. Das sollte nicht vorkommen — melde es.",
    unt_ungeprueft: "Erzeugt, gerade nicht nachprüfbar.",
    kopieren_von_hand: "Markiert — jetzt ⌘C bzw. Strg+C drücken.",
    lgi_keine_still: "Hier steht nichts, und das ist deine Wahl: unter Einstellungen steht die Sichtbarkeit auf „Gar nicht ankündigen“. Dein Knoten kündigt weder .onion noch IP an — du kannst Kanäle zu anderen öffnen, aber niemand kann einen zu dir öffnen, und weiterleiten geht nicht. Zum Ändern: Einstellungen → Sichtbarkeit.",
    lgi_keine_tor: "Noch nichts da. Deine .onion-Adresse legt Tor an, und die Anwendung trägt sie danach bei LND ein — nach einem Neustart meist binnen einer Minute, spätestens nach zehn Minuten. Steht hier danach immer noch nichts, liegt es nicht am Warten: dann zeigt das Protokoll unter „Tor“, ob Tor die Onion-Dienste anlegen konnte.",
    lgi_keine_hybrid: "Noch nichts da. Bei „Tor und Clearnet“ braucht dein Knoten eine eigene Adresse, die er ankündigen kann — trag sie unter Einstellungen ein (gern per DynDNS) und gib Port 9735 im Router frei. Die .onion-Adresse allein braucht ein bis zwei Minuten nach dem Start.",
    lgi_keine_beschaeftigt: "Dein Knoten antwortet gerade nicht auf die Frage nach seinen Adressen — er ist mit sich selbst beschäftigt. Nach einer Wiederherstellung durchsucht er die ganze Kette nach benutzten Adressen; das dauert und ist genau das, was es soll. Die Adresse erscheint von allein, sobald er durch ist.",
    lgi_kennung_anders: "Dieser Knoten hat eine ANDERE Kennung als der, der hier zuletzt lief.\n\nVorher: {vorher}\nJetzt:  {jetzt}\n\nNach einer Wiederherstellung aus deinen vierundzwanzig Wörtern müsste dieselbe herauskommen — steht hier eine andere, gehören die Wörter zu einer anderen Wallet. Nach einer NEU angelegten Wallet ist eine andere Kennung dagegen richtig: es IST ein anderer Knoten. Dann übernimm sie hier.",
    lgi_kennung_uebernehmen: "Ja, das ist jetzt mein Knoten",
    keine_kennung: "Dein Knoten sagt gerade nicht, wie er heißt — warte, bis er antwortet.",
    lgi_veraltet: "Stand von vorhin — dein Knoten ist gerade beschäftigt und antwortet nicht auf die Frage nach seinem Zustand.",
    lgi_keine_unklar: "Dein Knoten kündigt noch keine Adresse an. Ohne angekündigte Adresse weiß niemand, wie er dich erreichen soll.",
    unt_titel: "Dich gegenüber einem Dienst ausweisen",
    unt_lead: "LightningNetwork+ und ähnliche Stellen fragen nicht nach einem Passwort, sondern lassen dich einen vorgegebenen Text mit deinem Knotenschlüssel unterschreiben. Damit ist bewiesen, dass dir der Knoten gehört. Füge den Text ein, den die Seite dir zeigt — die Unterschrift kommt zurück und geht dort wieder hinein. Das bewegt kein Geld und gibt keinen Schlüssel preis.",
    unt_knopf: "Unterschreiben",
    unt_leer: "Da steht noch kein Text.",
    unt_nicht_bereit: "Lightning läuft noch nicht — ohne Wallet gibt es keinen Schlüssel zum Unterschreiben.",
    vb_knopf: "Verbinden",
    vb_verbunden: "Verbunden — die Leitung steht jetzt in der Liste darunter. Sie ist nicht dauerhaft: reißt sie ab, baut LND sie ohne Kanal nicht von selbst wieder auf.",
    vb_hinweis: "Damit jemand einen Kanal zu DIR öffnet, musst du übrigens gar nichts tun — dein Knoten ist erreichbar und nimmt alles ab der eingestellten Mindestgröße an. Was hilft, ist ein Name, den man wiedererkennt.",
    lv_titel: "Deine Verbindungen",
    lv_lead: "Leitungen zu anderen Knoten, gerade jetzt. Sie kosten nichts und binden kein Geld. Einige hält LND von sich aus, um die Karte des Netzes aktuell zu halten — deshalb stehen hier auch Knoten, mit denen du nie etwas zu tun hattest.",
    lv_summe: "Verbindungen: {n} · davon mit Kanal: {k}",
    lv_mit_kanal: "mit Kanal",
    lv_ohne_kanal: "ohne Kanal",
    lv_ein: "eingehend",
    lv_aus: "ausgehend",
    lv_netzkarte: "gleicht die Netzkarte ab",
    lv_keine: "Gerade keine Verbindung. Sobald LND läuft, baut er von sich aus welche auf.",
    gegenstelle_abgelehnt: "Diese Adresse hat der Knoten nicht angenommen: {grund}",
    lgw_titel: "Wo du Kanalpartner findest",
    lgw_lead: "SatoshiCortex führt bewusst kein eigenes Verzeichnis: der Lightning-Graph ist längst eines, und jeder Knoten kennt ihn. Diese Stellen gehören nicht uns und sind seit Jahren etabliert.",
    lgw_amboss: "Graph-Explorer und Marktplatz. Über „Magma“ kannst du eingehende Liquidität kaufen — jemand öffnet einen Kanal zu dir, du zahlst eine Gebühr dafür.",
    lgw_lnplus: "Bringt Betreiber zusammen, die sich gegenseitig Kanäle öffnen — ringförmig, kostenlos. Für kleine Knoten oft der beste Einstieg, weil niemand Kapital verkauft.",
    lgw_1ml: "Verzeichnis und Statistik. Gut, um eine mögliche Gegenstelle vorher anzusehen: wie viele Kanäle, wie groß, wie lange schon dabei.",
    lgw_fuss: "SatoshiCortex ruft keine dieser Stellen auf — es sind Verweise, die du selbst öffnest. Geöffnet wird der Kanal dann unter „Kanäle“ — hinter derselben PIN wie das Senden.",
    sich_ohne_wallet: "Noch keine Lightning-Wallet — es gibt also noch nichts zu sichern. Das Ziel kannst du trotzdem schon eintragen: dann sichert der Knoten ab dem ersten Kanal von allein, statt erst wenn du daran denkst.",
    kk_titel: "Was ein Kanal an Gebühren kostet",
    kk_lead: "Ein Kanal zu öffnen und wieder zu schließen sind zwei ganz normale Bitcoin-Überweisungen — du zahlst also zweimal Gebühren an das Netz. Die Schätzung kommt von deinem eigenen Knoten, nicht von einer fremden Seite.",
    kk_satz: "Gebührenlage gerade",
    kk_oeffnen: "Öffnen (geschätzt)",
    kk_schliessen: "Einvernehmlich schließen (geschätzt)",
    kk_zusammen: "Zusammen",
    kk_guenstig: "Das sind {p} % deines On-Chain-Guthabens — ein guter Zeitpunkt.",
    kk_spuerbar: "Das sind {p} % deines On-Chain-Guthabens. Spürbar, aber vertretbar. Wenn es nicht eilt, lohnt sich Warten.",
    kk_teuer: "Das sind {p} % deines On-Chain-Guthabens. Jetzt einen Kanal zu öffnen wäre teuer — die Gebühren schwanken stark, warte lieber ab.",
    kk_lage_guenstig: "{satz} sat/vB — das ist günstig. In den letzten {tage} Tagen lagen die meisten Blöcke zwischen {unten} und {oben} sat/vB, in der Mitte bei {mitte}. Gemessen an deiner eigenen Kette, nicht an einer fremden Seite.",
    kk_lage_normal: "{satz} sat/vB — das ist normal. In den letzten {tage} Tagen lagen die meisten Blöcke zwischen {unten} und {oben} sat/vB, in der Mitte bei {mitte}.",
    kk_lage_teuer: "{satz} sat/vB — das ist teuer. In den letzten {tage} Tagen lagen die meisten Blöcke zwischen {unten} und {oben} sat/vB, in der Mitte bei {mitte}. Wenn es nicht eilt, warte lieber ab.",
    kkp_titel: "Was du für einen Kanal einzahlen musst",
    kkp_lead: "Die Kanalgröße ist nicht der Betrag, der auf deiner Wallet liegen muss. Trag ein, wie groß der Kanal werden soll — den Rest rechnet dein eigener Knoten.",
    kkp_ohne: "Dafür fehlt noch die Gebührenschätzung. Die gibt dein Knoten erst her, wenn die Kette steht — vorher wäre jede Zahl hier geraten.",
    kkp_groesse: "Kanalgröße (sat)",
    kkp_kanal: "Kanalgröße",
    kkp_oeffnen: "Öffnungsgebühr (geschätzt)",
    kkp_ruecklage: "Anker-Rücklage (von LND)",
    kkp_einzahlen: "On-Chain einzahlen",
    kkp_nutzbar: "Im Kanal nutzbar",
    kkp_fuss: "Die Anker-Rücklage bleibt in deiner On-Chain-Wallet liegen — sie ist nicht weg, aber gebunden: LND braucht sie, um einen erzwungenen Abschluss notfalls nachfinanzieren zu können. Die Schließgebühr musst du dagegen NICHT vorher einzahlen; sie wird beim einvernehmlichen Schließen vom Kanalguthaben abgezogen. Und rund ein Prozent der Kanalgröße bleibt als Kanal-Reserve liegen, solange der Kanal offen ist.",
    kk_erzwungen: "Achtung: Das gilt für ein einvernehmliches Schließen, bei dem beide Seiten mitmachen. Antwortet die Gegenstelle nicht, wird der Kanal erzwungen geschlossen — dann kommen zur Verpflichtungstransaktion noch die Ausgaben zum Einsammeln des eigenen Guthabens dazu, und es wird deutlich teurer. Der beste Schutz davor ist eine zuverlässige Gegenstelle.",
    sich_titel: "Kanalsicherung",
    sich_lead: "Deine vierundzwanzig Wörter stellen die On-Chain-Wallet wieder her — die Guthaben IN deinen Kanälen nicht. Ein Kanal ist eine gemeinsame Ausgabe mit einer Gegenstelle; um ihn ohne deren Mithilfe aufzulösen, braucht es seinen Zustand. Genau der steht in dieser Datei. Platte kaputt, Sicherung weg, Kanalguthaben weg — auch mit dem Zettel in der Hand.",
    sich_ohne_kanaele: "Noch keine Kanäle — also noch nichts zu sichern. Sobald der erste Kanal steht, entsteht die Datei, und ab dann zählt sie.",
    sich_aktuell: "Auf dem Stand: {kanaele} Kanäle, zuletzt abgelegt am {wann}.",
    sich_rueckstand: "Rückstand: dein Knoten hat {kanaele} Kanäle, abgelegt wurde zuletzt ein älterer Stand. Jeder Kanal, der seitdem dazukam, ist ein Kanal ohne Sicherung.",
    sich_nie: "Noch nie gesichert. {kanaele} Kanäle stehen offen — bei einem Plattenverlust wäre das Guthaben darin verloren.",
    sich_fehler_zuletzt: "Der letzte Versuch schlug fehl: {fehler}",
    sich_ziel_ist: "Ziel: {url} (als {benutzer})",
    sich_laden: "Herunterladen",
    sich_geladen: "Heruntergeladen. Leg sie irgendwohin, nur nicht auf diese NAS.",
    sich_ziel_titel: "Automatisch ablegen (WebDAV)",
    sich_ziel_d: "Nextcloud, ein Hoster, irgendein WebDAV-Ordner. Einmal einrichten, danach schiebt SatoshiCortex die Datei bei jeder Kanaländerung von allein dorthin. Das ist unbedenklich: die Sicherung ist mit einem Schlüssel aus deinem Seed verschlüsselt — wer sie ohne deine vierundzwanzig Wörter hat, hat nichts.",
    sich_url: "Ordner-Adresse",
    sich_url_d: "Der Ordner, nicht die Datei. Bei Nextcloud etwa https://cloud.example/remote.php/dav/files/DEINNAME/Sicherungen",
    sich_benutzer: "Benutzername",
    sich_passwort: "Passwort",
    sich_passwort_d: "Nimm ein App-Passwort, nicht dein Konto-Passwort. SatoshiCortex muss es speichern, um von allein ablegen zu können — ein App-Passwort lässt sich einzeln zurückziehen und kommt nicht an den Rest deines Kontos.",
    sich_einrichten: "Einrichten und jetzt ablegen",
    sich_entfernen: "Ziel entfernen",
    sich_eingerichtet: "Eingerichtet — und die erste Sicherung ist angekommen.",
    sich_entfernt: "Ziel entfernt. Es wird nichts mehr automatisch abgelegt.",
    ziel_nimmt_nichts_an: "Das Ziel hat die Sicherung nicht angenommen: {einzelheit}",
    ziel_anmeldung_abgelehnt: "Das Ziel hat die Anmeldung abgelehnt (401): Benutzername oder Passwort stimmen nicht. Bei Nextcloud mit Zwei-Faktor-Anmeldung gilt dein normales Passwort hier nicht — dafür braucht es ein App-Passwort (Persönliche Einstellungen → Sicherheit).",
    ziel_verweigert: "Das Ziel verweigert den Zugriff (403). Anders als bei 401 liegt es meist nicht am Passwort: entweder darf dieses Konto in den Ordner nicht schreiben — etwa bei einer nur lesbaren Freigabe —, oder ein vorgeschalteter Schutz wie ein Reverse-Proxy weist die Anfrage ab.",
    ziel_adresse_unbekannt: "Unter dieser Adresse kennt der Server keinen WebDAV-Ordner (404). Meist liegt das an der Adresse, nicht am Passwort. Bei Nextcloud sieht sie so aus: https://cloud.example/remote.php/dav/files/DEINNAME/Sicherungen — mit deinem Benutzernamen an der Stelle von DEINNAME. Schnellprobe: die Adresse im Browser öffnen; kommt auch dort 404, stimmt sie noch nicht.",
    ziel_ordner_fehlt: "Der Server ist der richtige, aber den Ordner gibt es dort noch nicht (409). WebDAV legt beim Hochladen keine Ordner an — leg ihn einmal von Hand an, etwa in der Nextcloud-Oberfläche, und versuch es dann noch einmal.",
    keine_kanaele: "Noch keine Kanäle — es gibt nichts zu sichern.",
    lightning_nicht_bereit: "Lightning läuft noch nicht.",
    adressart_unbekannt: "Diese Adressform kennt der Knoten nicht.",
    sicherung_unbrauchbar: "Die Sicherung ließ sich nicht prüfen. Lieber gar keine Datei als eine, auf die du dich verlässt — melde das bitte.",
    wl_weg_titel: "Wie geht deine Wallet nach einem Neustart wieder auf?",
    wl_weg_lead: "Drei Wege, und keiner ist für alle richtig. Lies die Folge darunter — sie steht da, weil alle drei Antworten vertretbar sind.",
    wl_weg_aus: "Ich tippe das Wallet-Passwort — jedes Mal",
    wl_weg_aus_d: "Nichts liegt auf der Platte, nichts bleibt im Speicher. Nach jedem Neustart wartet dein Knoten auf dich.",
    wl_weg_merken: "Für die Laufzeit merken",
    wl_weg_merken_d: "Nichts liegt auf der Platte. SatoshiCortex behält dein Passwort, solange es läuft — startet es Lightning selbst neu, macht es die Wallet wieder auf.",
    wl_weg_datei: "Von allein entsperren",
    wl_weg_datei_d: "Das Wallet-Passwort liegt im Klartext neben der Wallet. Dein Knoten läuft nach einem Stromausfall von allein weiter.",
    wl_weg_folge_aus: "Dein Wallet-Passwort liegt nirgends auf der Platte. Wer die NAS ausbaut oder ein Backup kopiert, kommt an das On-Chain-Guthaben nicht heran. Der Preis: nach jedem Neustart steht dein Knoten still, bis du hier das Passwort eingibst — auch nach einem, den SatoshiCortex selbst ausgelöst hat, etwa weil du den Namen oder die Sichtbarkeit geändert hast. Im Lightning-Netz zählt genau diese Betriebszeit für deinen Ruf.",
    wl_weg_folge_merken: "Auf der Platte liegt genauso wenig wie oben — gegen eine ausgebaute NAS oder ein kopiertes Backup ist das gleichwertig. Der Unterschied betrifft nur die Neustarts, die SatoshiCortex selbst auslöst: Name geändert, Sichtbarkeit geändert, Adresse neu aufgelöst. Die macht es dann selbst wieder auf, statt dich zu fragen. Fällt der Strom aus, fällt SatoshiCortex mit — und du tippst wieder. Ehrlich benannt: wer die laufende Anwendung übernimmt, findet das Passwort im Speicher. Er findet dort aber ohnehin den Ausweis, mit dem Lightning gesteuert wird.",
    wl_weg_folge_datei: "Dein Knoten läuft nach jedem Stromausfall von allein weiter — die beste Betriebszeit. Der Preis: wer die Platte in die Hand bekommt, hat beides, Wallet und Passwort. Und sobald diese Anwendung später Geld senden darf, hat er damit auch das. Gegen einen Einbruch in die laufende NAS hilft es ohnehin nicht.",
    wl_platte_titel: "Was liegt eigentlich auf der Platte?",
    wl_platte_d: "Deine vierundzwanzig Wörter: NIRGENDS. Sie gehen durch SatoshiCortex hindurch zu Lightning und werden nie geschrieben — eine Prüfung durchsucht bei jedem Bau jede angefasste Datei danach. Dein Wallet-Passwort: nur beim dritten Weg, und dort im Klartext. Was immer dort liegt, ist der Ausweis, mit dem SatoshiCortex Lightning steuert — den legt Lightning selbst ab, nicht wir. Seit dieser Ausweis auch senden darf, steht davor die PIN.",
    wl_entsperren_passwort: "Wallet-Passwort",
    wl_entsperren_passwort_d: "Das Passwort, mit dem du die Wallet angelegt hast.",
    wl_entsperren_gemerkt: "Danach merkt SatoshiCortex es sich, solange es läuft — du wirst erst nach einem Neustart der NAS wieder gefragt.",
    wl_passwort_titel: "Wallet-Passwort",
    wl_passwort_d: "Mindestens zehn Zeichen. Du brauchst es nach jedem Neustart — merk es dir oder leg es dorthin, wo auch die vierundzwanzig Wörter liegen. Verlierst du es, hilft nur der Seed.",
    wl_gesperrt_titel: "Wallet ist gesperrt",
    wl_gesperrt_d: "Dein Knoten läuft, aber die Wallet ist zu. Solange sie zu ist, leitet er nichts weiter und nimmt keine Zahlungen an. Gib dein Wallet-Passwort ein.",
    wl_entsperren: "Entsperren",
    wl_entsperrt: "Entsperrt. Der Knoten fährt jetzt hoch.",
    passwort_zu_kurz: "Das Passwort ist zu kurz — mindestens {mindestens} Zeichen.",
    passwort_falsch: "Das Passwort passt nicht.",
    wl_schritt1: "Schritt 1 von 3",
    wl_schritt2: "Schritt 2 von 3",
    wl_schritt3: "Schritt 3 von 3 — jetzt wird es endgültig",
    wl_noch_nichts: "Hier entsteht noch nichts. Du bekommst gleich vierundzwanzig Wörter zu sehen und wirst danach gefragt, ob du sie hast. Erst im dritten Schritt wird die Wallet wirklich angelegt.",
    wl_eine_einzige: "Ein Lightning-Knoten hat genau eine Wallet — sie ist seine Identität. Aus deinen Wörtern entsteht der Schlüssel, unter dem dieser Knoten im Netz auftritt. Es gibt deshalb keine zweite und keinen Wallet-Namen; wie dein Knoten im Netz heißt, stellst du unter Einstellungen ein.",
    wl_holen_titel: "Oder: du hast schon eine",
    tg_titel: "Wallet löschen",
    tg_lead: "Zum Ausprobieren der Einrichtung, oder wenn du diesen Knoten wirklich neu aufsetzen willst.",
    tg_warnung: "Weg sind danach: deine Wallet, die Kanal-Datenbank, alle Macaroons, das TLS-Zertifikat und der Schlüssel deines Onion-Dienstes. Dein Knoten bekommt damit eine NEUE Onion-Adresse — die alte erreicht dich nie wieder.",
    tg_seed: "Deine vierundzwanzig Wörter holen die On-Chain-Wallet zurück. Das Geld in offenen Kanälen holen sie NICHT zurück — dafür gibt es nur die Kanalsicherung. Hast du offene Kanäle und keine Sicherung, ist dieses Geld nach dem Löschen verloren.",
    tg_erst_sperren: "Zum Löschen muss deine Wallet gesperrt sein — nur dann kann LND dein Passwort überhaupt prüfen. Der Knopf startet LND einmal neu; das dauert eine knappe Minute.",
    tg_sperren_knopf: "Wallet sperren",
    tg_sperren_laeuft: "LND wird neu gestartet, gleich ist die Wallet gesperrt … (noch bis zu {rest} s)",
    tg_ist_gesperrt: "Zu. Jetzt geht es weiter.",
    tg_sperren_haengt: "LND ist auch nach zweieinhalb Minuten nicht gesperrt zurückgekommen. Sieh unter Protokoll nach, was der Dienst sagt — der Knopf lässt sich danach erneut drücken.",
    tg_passwort_d: "Dein Wallet-Passwort. LND prüft es selbst — hier wird nichts verglichen, was wir abgelegt haben.",
    tg_alias: "Zur Sicherheit: der Name deines Knotens",
    tg_alias_d: "Tippe „{alias}“ ab.",
    tg_loeschen_knopf: "Endgültig löschen",
    tg_laeuft: "Wird gelöscht. LND fährt herunter, das Verzeichnis wird geleert, danach startet es leer wieder hoch.",
    wallet_erst_sperren: "Dafür muss die Wallet gesperrt sein.",
    wallet_arbeit_laeuft: "Es läuft gerade schon ein Neustart. Warte, bis er durch ist.",
    auto_entsperren_an: "Mit eingeschaltetem Auto-Entsperren entsperrt LND sich beim Start selbst — ein Neustart würde nichts bringen. Schalte es zuerst ab.",
    alias_stimmt_nicht: "Der Name stimmt nicht. Erwartet wird „{erwartet}“.",
    wl_titel: "Lightning-Wallet anlegen",
    wl_lead: "Einmalig, und danach nie wieder. SatoshiCortex lässt LND vierundzwanzig Wörter würfeln — aus ihnen lässt sich deine Wallet vollständig wiederherstellen, auch wenn diese NAS morgen in Flammen steht.",
    wl_papier: "Die Wörter gehören auf Papier. Nicht in einen Passwortmanager, nicht in eine Notiz-App, nicht in ein Foto. Alles, was auf einer Platte liegt, liegt auf derselben Platte wie die Wallet — und schützt dann gegen nichts. SatoshiCortex speichert sie nirgends: schließt du dieses Fenster, ohne sie abzuschreiben, sind sie weg.",
    wl_erzeugen: "Wörter erzeugen",
    wl_woerter_titel: "Deine vierundzwanzig Wörter",
    wl_woerter_d: "Schreib sie in dieser Reihenfolge ab und lies sie anschließend gegen den Bildschirm zurück. Die Reihenfolge zählt genauso wie die Wörter.",
    wl_woerter_warnung: "Diese Wörter siehst du genau einmal. Sobald du weitergehst, sind sie fort — und niemand, auch ich nicht, kann sie dir zurückgeben.",
    wl_bestaetigen: "Ich habe alle vierundzwanzig Wörter auf Papier abgeschrieben",
    wl_bestaetigen_d: "Gleich frage ich vier davon ab. Ohne richtige Antwort gibt es keine Wallet — das ist keine Schikane, sondern der einzige Weg zu wissen, dass du sie wirklich hast.",
    wl_weiter: "Weiter zur Gegenprobe",
    wl_probe_titel: "Gegenprobe",
    wl_probe_d: "Vier Stellen aus deinem Zettel. Groß- und Kleinschreibung ist egal.",
    wl_wort_nr: "Wort {nr}",
    wl_anlegen: "Wallet anlegen",
    wl_fertig_titel: "Die Wallet steht",
    wl_fertig_auto: "Angelegt und entsperrt. Dein Knoten entsperrt sie ab jetzt bei jedem Start von allein — dafür liegt das Wallet-Passwort auf der Platte.",
    wl_fertig_hand: "Angelegt und entsperrt. Nach jedem Neustart des Knotens musst du sie hier von Hand entsperren: das Passwort liegt nirgends auf der Platte, also kann niemand — auch SatoshiCortex nicht — es ohne dich eingeben. Bis dahin ruht Lightning.",
    wl_fertig_merken: "Angelegt und entsperrt. SatoshiCortex merkt sich dein Passwort, solange es läuft: startet es Lightning selbst neu, macht es die Wallet wieder auf. Nach einem Stromausfall fragt es dich wieder — dein Zettel bleibt also der Weg zurück.",
    wallet_gibt_es_schon: "Es gibt bereits eine Wallet. Einen zweiten Seed dazu anzubieten, wäre die gefährlichste Verwechslung, die diese Oberfläche anrichten könnte.",
    lnd_antwortet_nicht: "Lightning antwortet gerade nicht. Läuft der Dienst schon?",
    seed_abgelaufen: "Die Wörter sind nicht mehr gültig. Fang von vorn an — du bekommst neue.",
    gegenprobe_falsch: "Mindestens eines der vier abgefragten WÖRTER stimmt nicht — es geht hier nicht um dein Passwort. Geh die Nummern auf deinem Zettel noch einmal durch; der häufigste Fehler ist eine Zeile daneben. Noch {versuche_uebrig} Versuche, dann gibt es neue Wörter und dein Zettel ist Altpapier.",
    gegenprobe_aufgegeben: "Das war der letzte Versuch. Wir fangen von vorn an — mit neuen Wörtern, damit die alten nicht halb bekannt herumliegen.",

    /* Wiederherstellen: der Weg zurück. */
    wl_oder: "Du hast diesen Knoten schon einmal betrieben?",
    wl_holen: "Gesicherten Knoten zurückholen",
    wh_titel: "Einen gesicherten Knoten zurückholen",
    wh_lead: "Du hast die vierundzwanzig Wörter und, im besten Fall, die Kanalsicherung. Damit baut LND deine Wallet neu auf und durchsucht die Kette nach allem, was dir gehört. Es ist derselbe Aufruf, mit dem eine Wallet angelegt wird — nur mit zwei Feldern mehr.",
    wh_warnung: "Das geht nur, solange es hier noch keine Wallet gibt. Läuft schon eine, ist dies der falsche Ort — eine zweite Wallet neben einer bestehenden richtet mehr Schaden an als jeder Datenverlust.",
    wh_woerter_titel: "Deine vierundzwanzig Wörter",
    wh_woerter_d: "In der Reihenfolge vom Zettel. Groß- und Kleinschreibung ist egal. Du kannst auch alle vierundzwanzig auf einmal in das erste Feld einfügen — sie verteilen sich dann selbst.",
    wh_wort_unbekannt: "Diese Wörter stehen nicht in der Wortliste, aus der ein Seed besteht — dort gibt es genau 2048, und deins ist keines davon: {liste}. Getippt, nicht falsch aufgeschrieben: geh das Feld noch einmal Buchstabe für Buchstabe durch.",
    wh_wort_vielleicht: "Nr. {nr} „{wort}“ — meintest du „{nahe}“?",
    wh_wort_nur: "Nr. {nr} „{wort}“",
    wh_erst_woerter: "Erst die markierten Wörter berichtigen — so nimmt LND den Seed gar nicht erst an.",
    wh_pass_titel: "Seed-Passphrase (nur falls du eine gesetzt hast)",
    wh_pass_d: "SatoshiCortex setzt selbst nie eine. Dieses Feld gibt es für Seeds, die anderswo entstanden sind — etwa mit „lncli create“. Im Zweifel leer lassen.",
    wh_sich_titel: "Kanalsicherung",
    wh_sich_d: "Die Wörter holen dein On-Chain-Guthaben zurück. Die Guthaben IN deinen Kanälen holen sie nicht — dafür braucht es diese Datei. Hast du sie nicht, fehlt genau dieser Teil; alles andere kommt trotzdem zurück.",
    wh_q_keine: "Keine — nur die Kette wiederherstellen",
    wh_q_datei: "Datei auswählen (channel.backup)",
    wh_q_ziel: "Vom eingerichteten Sicherungsziel holen",
    wh_datei_gewaehlt: "{name} — {bytes} Byte gelesen.",
    wh_datei_zu_gross: "Diese Datei ist zu groß für eine Kanalsicherung. Das ist nicht die richtige.",
    wh_ungeprueft: "Diese Datei kann hier NICHT geprüft werden: sie ist mit einem Schlüssel aus deinem Seed verschlüsselt, und den kennt erst die fertige Wallet. Ist es die falsche Datei, startet LND anschließend nicht — dann fängst du ohne sie noch einmal an. Prüfen lässt sie sich nur, solange ein Knoten läuft: dafür gibt es unter „Sicherung“ den Knopf „Kopie prüfen“.",
    wh_was_titel: "Was zurückkommt — und was nicht",
    wh_was_d: "Zurück kommt dein On-Chain-Guthaben, vollständig. Zurück kommen die abgerechneten Guthaben aus deinen Kanälen: LND zwingt die Kanalpartner zum Zwangsschluss und holt das Geld auf die Kette. Die Kanäle selbst sind danach zu — wiederhergestellt wird das Geld, nicht der Betrieb. NICHT zurück kommen Beträge, die im Moment des Verlusts noch unterwegs waren.",
    wh_dauer: "LND sucht danach {fenster} Adressen weit die Kette ab. Das dauert und braucht eine fertige Kette — vorher findet es nichts. Der Zwangsschluss der Kanäle braucht zusätzlich die üblichen Sperrfristen, je nach Gegenstelle Stunden bis Tage.",
    wh_starten: "Wiederherstellen",
    wh_abbrechen: "Zurück",
    wh_fertig_titel: "Wiederhergestellt",
    wh_fertig_d: "Die Wallet ist angelegt und LND sucht die Kette ab. Bis Beträge auftauchen, kann es dauern — sieh später noch einmal nach.",
    wh_fertig_kanaele: "Die Kanalsicherung ist mitgegeben. LND spricht jetzt die Kanalpartner an; das Geld erscheint on-chain, sobald die Sperrfristen abgelaufen sind.",
    seed_unvollstaendig: "Das sind {gezaehlt} Wörter, gebraucht werden {erwartet}. Zähl noch einmal nach — auch ein doppelt getipptes Wort fällt hier auf.",
    seed_nicht_angenommen: "LND hat diesen Seed nicht angenommen. Sein Wortlaut: {einzelheit} — Steht dort etwas von einer Prüfsumme („checksum“), liegt es wirklich an den Wörtern: geh den Zettel Wort für Wort durch und achte auf die Reihenfolge. Steht dort etwas von einer Passphrase, liegt es NICHT an deinem Zettel — dann klapp „Seed-Passphrase“ oben auf und leere das Feld.",
    sicherung_unlesbar: "Diese Datei ließ sich nicht einmal einlesen. Das ist keine Kanalsicherung.",
    sicherung_zu_klein: "Diese Datei hat nur {bytes} Byte — die kleinstmögliche Kanalsicherung hat 45. Vermutlich ist der Download abgebrochen oder es ist die falsche Datei.",
    kein_ziel: "Es ist kein Sicherungsziel eingerichtet — von dort kann nichts kommen.",
    kein_passwort: "Zum eingerichteten Ziel fehlt das Passwort. Trag es unten noch einmal ein.",
    ziel_gibt_nichts_her: "Vom Sicherungsziel kam nichts zurück: {einzelheit}",
    ziel_keine_sicherung_dort: "Dort liegt keine Kanalsicherung (404). Entweder wurde an dieses Ziel noch nie eine abgelegt, oder die Adresse zeigt auf einen anderen Ordner als beim Einrichten.",

    /* Die Kopie prüfen, die du in der Hand hast. */
    sipr_titel: "Kopie prüfen",
    sipr_d: "Dass dein Knoten eine heile Sicherung erzeugen kann, sagt nichts über die Kopie auf deinem Stick. Leg sie hier vor: LND schließt sie wirklich auf und sagt dir, welche Kanäle darin stehen. Das beweist zweierlei — sie ist heil, und sie gehört zu diesem Knoten. Der einzige Tag, an dem du das nicht mehr herausfinden kannst, ist der, an dem du es brauchst.",
    sipr_datei: "Datei auswählen",
    sipr_pruefen: "Vorgelegte Datei prüfen",
    sipr_ziel: "Die am Ziel abgelegte prüfen",
    sipr_laeuft: "Wird geprüft …",
    sipr_ok: "Heil, und sie gehört zu diesem Knoten: {abgedeckt} Kanäle stehen darin — genau die {offen}, die offen sind.",
    sipr_luecke: "Heil, und sie gehört zu diesem Knoten. Aber sie deckt nur {abgedeckt} von {offen} offenen Kanälen ab: sie ist älter als dein jüngster Kanal. Hol dir eine frische.",
    sipr_ohne_vergleich: "Heil, und sie gehört zu diesem Knoten: {abgedeckt} Kanäle stehen darin.",
    pr_titel: "Von außen erreichbar?",
    pr_d: "Geprüft wird über Tor — die Verbindung verlässt dein Haus, läuft über drei fremde Rechner und kommt von außen zurück. Genau den Weg nimmt auch eine echte Gegenstelle. Von innen ginge es nicht ehrlich: bei IPv6 gibt es kein NAT, eine Verbindung aus dem eigenen Netz käme auch dann an, wenn die Firewall im Router zu ist. Die Messung dauert je Adresse bis zu einer halben Minute.",
    pr_knopf: "Jetzt prüfen",
    pr_laeuft: "Wird geprüft — das dauert über Tor einen Moment …",
    pr_ja: "{adresse} — erreichbar. Es hat sich {kennung} gemeldet.",
    pr_ja_offen: "{adresse} — erreichbar. Die Verbindung kam über Tor bis zu deinem Knoten durch.",
    pr_abgelehnt_onion: "{adresse} — abgelehnt. Tor hat deinen Onion-Dienst gefunden, aber dahinter hat auf Port {port} niemand angenommen. Am Router liegt das nicht — über Tor braucht es keine Freigabe. Meist ist der Dienst dahinter gerade nicht gestartet; sonst zeigt das Protokoll unter „Tor“, wohin Tor weiterreicht.",
    pr_dienst_lightning: "Lightning",
    pr_dienst_wachturm: "Wachturm",
    pr_abgelehnt: "{adresse} — abgelehnt. Dein Router hat geantwortet, aber Port {port} zeigt nicht hierher. Das ist eine fehlende Portfreigabe.",
    pr_kein_knoten: "{adresse} — Port {port} ist offen, aber dahinter antwortet kein Bitcoin-Knoten. Die Freigabe zeigt vermutlich auf das falsche Gerät.",
    pr_kein_handschlag: "{adresse} — Port {port} ist offen: die Verbindung von außen kam zustande, deine Freigabe im Router trägt also. Der Bitcoin-Handschlag brach danach ab — dahinter antwortet etwas, aber nicht sauber.",
    pr_keine_antwort: "{adresse} — Port {port} ist offen: die Verbindung von außen kam zustande, deine Freigabe im Router trägt also. Es kam nur keine Antwort in der Frist. Über Tor ist das meistens der Weg und nicht dein Knoten — und während des Erstabgleichs ist er obendrein beschäftigt.",
    pr_unklar: "{adresse} — nicht messbar: {grund}. Das sagt nichts über deinen Knoten; der Weg über Tor kam nicht zustande. Versuch es später noch einmal.",
    pr_unklar_onion: "{adresse} — nicht messbar: {grund}. Das sagt nichts über deinen Knoten. Bei einer .onion sucht Tor zuerst das Verzeichnis deines versteckten Dienstes. Mehrere Prüfungen kurz hintereinander fragen alle zuständigen Verzeichnisse durch, und danach geht es für einige Minuten gar nicht mehr — genau die Meldung „No more HSDir available to query“ im Tor-Protokoll. Also nicht sofort wiederholen: ein paar Minuten warten.",
    pr_keine_adresse: "Dein Knoten kündigt keine Adresse an — so findet ihn von außen niemand. Trag oben einen Namen ein und schalte „Eigene Adresse ankündigen“ an.",
    pr_tor_aus: "Ohne Tor lässt sich das nicht ehrlich messen. Eine Verbindung aus dem eigenen Netz käme auch dann an, wenn der Router zu ist — die Antwort wäre immer „erreichbar“ und nie etwas wert.",
    pr_nicht_aufloesbar: "Der eingetragene Name ließ sich gerade nicht auflösen. Ohne Adresse gibt es nichts zu prüfen.",
    pr_tor_pausiert: "Tor wurde nicht geprüft — es gab nichts zu messen. Während des Erstabgleichs pausiert der Tor-Ausgang, und Bitcoin Core kündigt die .onion-Adresse dann gar nicht erst an. Dein Onion-Dienst läuft trotzdem weiter und nimmt eingehende Verbindungen an; nur erfahren neue Gegenstellen die Adresse gerade nicht. Sobald die Kette steht, kommt sie von selbst zurück — dieselbe wie vorher. Wer nicht warten will, schaltet oben „Tor pausieren, bis die Kette geladen ist“ ab.",
    pr_keine_onion: "Tor ist an, aber dein Knoten kündigt keine .onion-Adresse an — deshalb steht hier nichts dazu. Die Adresse legt Tor beim Start an, und die Anwendung trägt sie danach bei bitcoind ein. Meist heißt das, Tor oder bitcoind sind gerade erst neu gestartet. Steht nach zehn Minuten noch immer nichts da, zeigt das Protokoll unter „Tor“, ob Tor die Onion-Dienste anlegen konnte.",
    pr_fehler: "Die Prüfung ist nicht durchgelaufen.",
    kn_titel: "Der Name deines Knotens",
    kn_lead: "So heißt dein Knoten im Lightning-Graphen — auf amboss.space, auf 1ml und in der Kanalliste jeder Gegenstelle. Ein Name, den man wiedererkennt, ist die Voraussetzung dafür, dass jemand einen Kanal zu dir aufmacht.",
    kn_gespeichert_neustart: "Gespeichert. LND startet jetzt neu und meldet den Namen ans Netz.",
    kn_alias: "Alias",
    kn_alias_d: "Höchstens 32 Byte — Umlaute und Emoji zählen mehrfach. Ohne eigene Angabe heißt dein Knoten „SatoshiCortex“ wie jeder andere mit dieser Software. Nach außen sichtbar wird der Name erst mit dem ersten öffentlichen Kanal: das Netz reicht die Namensmeldung eines Knotens nur weiter, wenn es von ihm bereits einen angekündigten Kanal kennt (BOLT 7). Bis dahin zeigen Verzeichnisse wie Amboss oder LightningNetwork+ deinen Schlüssel statt deines Namens — ohne dass bei dir etwas falsch eingestellt wäre.",
    kn_farbe: "Farbe",
    kn_farbe_d: "Der Farbtupfer neben deinem Namen in den Graph-Ansichten. Reine Zier, aber sie macht dich in einer Liste auffindbar.",
    minchansize_ungueltig: "Der kleinste eingehende Kanal muss zwischen {min} und {max} Satoshi liegen.",
    kn_minchan: "Kleinster eingehender Kanal (Satoshi)",
    kn_minchan_d: "Was andere dir mindestens öffnen müssen. Alles darunter lehnt dein Knoten automatisch ab — du siehst davon nichts. Nimmst du an einem Liquiditäts-Ring teil, setze den Wert UNTER die Ringgröße: liegt er genau darauf, scheitert der Kanal, den du dir verdient hast, schon an einem Satoshi Unterschied. LNDs eigene Untergrenze ist 20.000.",
    kn_neustart: "Beim Speichern startet LND einmal neu und meldet den neuen Namen per node_announcement ans Netz. Hast du das automatische Entsperren AUS, ist deine Wallet danach gesperrt, bis du das Passwort eingibst — dein Knoten leitet solange nichts weiter.",
    name_ungueltig: "Dieser Name geht nicht. Höchstens 32 Byte, eine Zeile, keine Steuerzeichen — und die Farbe als #rrggbb.",
    wege_titel: "Wege ins Netz",
    wege_intro: "Vier Wege, und sie sind unabhängig voneinander. Keiner schaltet einen anderen ab — im Gegenteil: Knoten, die Tor und Clearnet zugleich sprechen, sind im Netz knapp. Die einzige Grenze liegt nicht zwischen den Schaltern: ganz ohne Netz geht es nicht.",
    wege_tor: "Tor (.onion)",
    wege_tor_d: "Was dabei auf deinem Gerät passiert: ein Tor-Dienst läuft mit, verbindet sich mit dem Tor-Netz und legt für deinen Knoten eine .onion-Adresse an. Er leitet KEINEN fremden Verkehr weiter — dein Gerät wird kein Relay. Beim ersten Start lädt er einmalig das Verzeichnis des Netzes, danach ist er sehr genügsam. Der Nutzen: Tor-Knoten brauchen Gegenstellen, die beide Welten sprechen, und diese Brücke ist knapp.",
    wege_pause: "Tor pausieren, bis die Kette geladen ist",
    wege_pause_d: "Tor ist um ein Vielfaches langsamer als eine gewöhnliche Verbindung, und beim Laden der Kette zählt nur der Durchsatz. Dein Knoten ruft dann über Tor niemanden von sich aus an — und kündigt in dieser Zeit auch seine .onion-Adresse nicht an. Der Onion-Dienst läuft weiter und nimmt eingehende Verbindungen an, aber neue Gegenstellen erfahren die Adresse nicht. Verschmerzbar, solange die Kette lädt: ausliefern kann dein Knoten ohnehin nichts. Die Adresse geht nicht verloren — sobald die Kette steht, endet die Pause und dieselbe .onion wird wieder angekündigt.",
    wege_ipv4: "IPv4",
    wege_ipv4_d: "Der gewöhnliche Weg. Damit dich andere erreichen, muss Port 8333 in deinem Router auf dieses Gerät zeigen.",
    wege_ipv6: "IPv6",
    wege_ipv6_d: "Getrennt schaltbar, weil längst nicht jeder Anschluss IPv6 hat — und weil ein angekündigter Weg, den niemand nehmen kann, schlechter ist als gar keiner. Auch hier gehört Port 8333 freigegeben.",
    wege_adresse: "Eigene Adresse ankündigen",
    wege_adresse_d: "Im Container sieht dein Knoten nur die interne Docker-Adresse. Ohne Angabe versucht er, seine öffentliche von den Gegenstellen zu lernen — das gelingt oft, aber nicht immer. Trägst du sie ein, kündigt er sie sofort an und wird gefunden. Ein DynDNS-Name ist hier besser als eine feste IP, weil er einen Wechsel überlebt. Mehrere Angaben mit Komma trennen.",
    wege_ruft_an: "Zurzeit ruft dein Knoten von sich aus an über: {liste}.",
    wege_pause_laeuft: "Läuft gerade: über Tor ruft dein Knoten niemanden an, und seine .onion-Adresse kündigt er solange nicht an.",
    wege_pause_fertig: "Die Kette steht — hier ist nichts mehr zu pausieren.",
    wege_pause_wartet: "Eingeschaltet. Sie greift, sobald Gegenstellen über beide Wege da sind — sonst bliebe der Knoten womöglich ganz ohne.",
    wege_pause_aus: "Aus: dein Knoten ruft auch während des Abgleichs über Tor an. Das kostet spürbar Tempo — Tor ist um ein Vielfaches langsamer, und jeder Tor-Platz ist einer weniger für eine schnelle Verbindung.",
    wege_pausiert: "Tor ist eingeschaltet, pausiert aber während des Erstabgleichs — deshalb fehlt Onion in dieser Liste, und deine .onion-Adresse wird solange nicht angekündigt.",
    kein_weg_ins_netz: "Mindestens ein Weg muss bleiben. Sonst käme dein Knoten weder hinaus, noch wäre er zu erreichen.",
    back: "Zurück", next: "Weiter", start: "Einrichtung starten",

    w_klick: "Klick auf ein Land zeigt, in welchen Bundesländern, Kantonen oder Provinzen deine Gegenstellen sitzen.",
    w_klapp_zu: "Zahlen ausblenden",
    w_klapp_auf: "Zahlen einblenden",
    wl_zurueck: "← Weltkarte",
    wl_uebersicht: "Gebiete in diesem Land",
    wl_gebiet: "Gebiet",
    wl_btc: "Bitcoin",
    wl_ln: "Lightning",
    wl_buch: "bekannt",
    wl_laedt: "Wird geholt …",
    wl_fehler: "Die Aufschlüsselung ist gerade nicht abrufbar.",
    wl_keine: "In diesem Land kennt dein Knoten niemanden — jedenfalls niemanden, dessen Gebiet sich bestimmen lässt.",
    wl_unmoeglich: "Für dieses Abbild gibt es keine Gebietsnamen. Die Weltkarte bleibt davon unberührt.",
    wl_ohne_umriss: "Für dieses Land liegen keine Umrisse der Gebiete bereit — die Zahlen daneben stimmen trotzdem.",
    wl_stand: "Ortsliste vom {stand}",
    wl_rest: "Dazu {btc} Gegenstellen, {ln} Lightning-Knoten und {buch} Adressen in diesem Land, deren Gebiet unbekannt ist.",
    wl_genauigkeit: "Das Gebiet ist die Angabe der freien DB-IP-Liste und kann danebenliegen — ein Rechenzentrum steht selten dort, wo sein Betreiber sitzt. Genauer als das Bundesland wird es hier bewusst nicht.",
    st_willkommen: "Willkommen", st_speicher: "Speicher", st_leistung: "Leistung",
    st_netz: "Netz", st_wallet: "Wallet", st_konto: "Konto", st_fertig: "Fertig",

    w_title: "Dein eigener Bitcoin-Knoten",
    w_lead: "In wenigen Minuten eingerichtet. Danach läuft er allein.",
    w_p1: "SatoshiCortex macht aus diesem Gerät einen vollwertigen Teilnehmer im Bitcoin- und Lightning-Netz — keinen Zuschauer. Dein Knoten prüft jede Transaktion selbst, liefert anderen die Blockkette aus und zeigt dir Dinge, die kein öffentlicher Dienst zeigen kann.",
    w_need_disk: "<b>Rund 1 TB Plattenplatz</b>, wachsend um etwa 85 GB im Jahr.",
    w_need_ports: "<b>Zwei Portfreigaben</b> im Router. Wir prüfen sie gleich gemeinsam.",
    w_need_time: "<b>Tage bis Wochen</b> für den ersten Abgleich. Das läuft im Hintergrund.",
    w_need_band: "<b>Upload-Bandbreite.</b> Wie viel, bestimmst du selbst.",
    w_note: "Nichts davon musst du von Hand einstellen. Die nächsten Schritte prüfen, erklären und erledigen es.",

    s_title: "Speicherplatz",
    s_lead: "Wir schauen uns an, was zur Verfügung steht.",
    s_checking: "Wird geprüft …",
    s_bulk: "Große Ablage", s_fast: "Schnelle Ablage",
    s_free: "frei", s_needed: "empfohlen",

    l_title: "Leistung",
    l_lead: "Wie viel darf sich SatoshiCortex nehmen? Auf einem NAS laufen meist noch andere Dienste — die sollen nicht stehenbleiben.",
    l_sparsam: "Sparsam", l_sparsam_d: "Für Geräte mit wenig Luft oder vielen anderen Diensten. Der erste Abgleich dauert länger, läuft aber zuverlässig durch.",
    l_mittel: "Ausgewogen", l_mittel_d: "Empfohlen. Spürbar zügig, lässt aber genug für alles andere auf dem Gerät.",
    l_voll: "Volle Leistung", l_voll_d: "Das Gerät gehört dem Knoten. Schnellster erster Abgleich.",
    l_upload: "Upload im Monat",
    l_unlimited: "unbegrenzt",
    l_cache: "Zwischenspeicher: {a} MB beim ersten Abgleich, danach {b} MB",

    n_title: "Netz und Teilnahme",
    n_lead: "Damit dein Knoten nicht nur mitliest, sondern selbst etwas beiträgt, braucht er zwei offene Türen.",
    n_p_btc: "Bitcoin — damit andere Knoten dich erreichen",
    n_p_ln: "Lightning — damit Zahlungen durch dich laufen können",
    n_p_wt: "Wachturm — nur fürs Clearnet nötig; über Tor hat er eine eigene .onion",
    e_speichern: "Änderungen übernehmen",
    e_nicht_geladen: "Deine Einstellungen konnten nicht geladen werden — was hier steht, sind Vorgabewerte. Speichern ist deshalb gesperrt: es würde deine echten Einstellungen überschreiben. Lade die Seite gleich noch einmal.",
    mehr_dazu: "Was das bedeutet",
    e_ungespeichert: "Noch nicht übernommen. Die Schalter oben wirken erst, wenn du hier klickst — der Knoten startet dann einmal neu.",
    b_lead: "Wofür die gesendeten Daten draufgingen, bei den gerade verbundenen Gegenstellen. Nur „Blöcke“ ist Beitrag.",
    b_keine_gegenstellen: "Gerade meldet der Knoten keine verbundenen Gegenstellen — deshalb steht in der Aufteilung nichts. Das ist ein Augenblicksbild: die Aufteilung zählt nur, was an die JETZT verbundenen Gegenstellen ging, nicht was seit dem Start insgesamt hinausging.",
    b_summe: "Grundlage dieser Aufteilung: {menge}, gegangen an die {n} gerade verbundenen Gegenstellen. Nicht zu verwechseln mit „Ausgeliefert seit dem Start“ darüber — das zählt über die gesamte Laufzeit und über alle Gegenstellen, die seitdem da waren.",
    b_bloecke: "Blöcke ausgeliefert",
    b_transaktionen: "Transaktionen weitergereicht",
    b_filter: "Filter für Leichtgewicht-Wallets",
    b_kopfzeilen: "Kopfzeilen",
    b_adressen: "Adressen weitergegeben",
    b_rest: "Handschlag, Ping, Anfragen",
    b_budget_erschoepft: "Dein Upload-Budget für die laufenden 24 Stunden ist aufgebraucht. Dein Knoten liefert bis zum Ende dieses Fensters KEINE alten Blöcke mehr aus — Neueinsteiger können also gerade nicht bei dir synchronisieren. Neue Blöcke und Transaktionen reicht er weiterhin normal weiter. Das Fenster läuft noch {rest}.",
    b_noch_nichts: "Noch hat niemand Blöcke geholt. Dafür braucht es eingehende Verbindungen.",
    b_noch_nichts_sync: "Noch hat niemand Blöcke geholt. Während des Abgleichs normal: dein Knoten ist zu beschäftigt zum Antworten.",
    nav_uebersicht: "Übersicht",
    nav_netz: "Netz",
    nav_mempool: "Mempool",
    nav_bloecke: "Blöcke",
    nav_kanaele: "Kanäle",
    nav_knoten: "Knoten",
    tun_wallet_anlegen: "Die Kette steht und LND läuft. Der nächste Schritt ist die Lightning-Wallet — Seed auf Papier, mit Gegenprobe. Bis dahin hat dieser Knoten keinen Schlüssel und hält keinen Satoshi.",
    tun_wallet_anlegen_knopf: "Zur Wallet",
    tun_wallet_entsperren: "Deine Wallet ist gesperrt. Solange sie zu ist, leitet dein Knoten nichts weiter und nimmt keine Zahlungen an — er läuft, aber er steht still.",
    tun_wallet_entsperren_knopf: "Jetzt entsperren",
    tun_sicherungsziel: "Noch kein Sicherungsziel eingetragen. Deine vierundzwanzig Wörter holen die On-Chain-Wallet zurück, aber NICHT das Geld in deinen Kanälen — dafür braucht es die Kanalsicherung. Trag das Ziel ein, bevor der erste Kanal steht.",
    tun_sicherungsziel_knopf: "Sicherung einrichten",
    nav_wallet: "Wallet",
    nav_einrichtung: "Einrichtung",
    nav_abschnitte: "Abschnitte",
    lang_wahl: "Sprache",
    lk_leer: "Lightning läuft noch nicht — deshalb steht hier nichts. Was gerade fehlt, sagt dir der Reiter „Wallet“ ganz oben.",
    nav_einstellungen: "Einstellungen",
    nav_karte: "Karte",
    nav_welt: "Welt",
    nav_werkzeug: "Werkzeug",
    nav_rechner: "Rechner",

    rn_titel: "Sats, Bitcoin und Geld",
    rn_lead: "Ein Bitcoin sind hundert Millionen Satoshi — und in Lightning wird in Sats gerechnet, nicht in Kommastellen von Bitcoin. Tipp in ein Feld, die anderen beiden rechnen mit.",
    rn_waehrung: "Währung",
    rn_sat: "Satoshi",
    rn_sat_d: "Die kleinste Einheit. Ganze Zahlen, keine Kommastellen.",
    rn_btc: "Bitcoin",
    rn_btc_d: "Acht Nachkommastellen — die letzte ist ein Satoshi.",
    rn_fiat: "{w}",
    rn_fiat_d: "Zum Kurs unten. Er ändert sich, deine Sats nicht.",
    rn_je_btc: "für einen Bitcoin",
    rn_je_fiat: "für {zeichen} 1,—",
    rn_unlesbar: "Das kann ich nicht als Zahl lesen. Erlaubt sind Ziffern, ein Komma und Tausenderpunkte.",
    rn_zu_gross: "Mehr Bitcoin, als es je geben wird — die Obergrenze liegt bei 21 Millionen.",
    w_btc: "Bitcoin",
    w_ln: "Lightning",
    w_legende: "Was die Linien sagen",
    w_legende_btc: "Mit wem dein Bitcoin-Knoten gerade spricht",
    w_legende_ln: "Wohin dein Kapital in Kanälen gebunden ist",
    w_naechster: "Nächster Block",
    w_naechster_wert: "{tx} Tx · {mb} MB · {von}–{bis} sat/vB",
    w_naechster_sync: "erst nach dem Abgleich",
    w_hoehe: "Höhe",
    w_gebuehren: "Gebühren",
    w_g_schnell: "schnell",
    w_g_normal: "normal",
    w_g_guenstig: "günstig",
    w_schwierigkeit: "Schwierigkeit",
    w_anpassung: "Nächste Anpassung",
    w_in_bloecken: "in {n} Blöcken",
    w_keine_daten: "noch keine Grundlage",
    w_ln_kanaele: "Kanäle",
    w_ln_partner: "Kanalpartner",
    w_ln_kapazitaet: "Kapazität",
    w_ln_laender: "Länder",
    w_ln_ohne_ort: "Kanalpartner ohne Ort",
    w_ln_ohne_ort_d: "Kanalpartner, die sich nur über Tor melden, haben keinen Ort — das Kapital liegt trotzdem dort.",
    w_ln_keine_wallet: "Noch keine Lightning-Wallet. Sobald Kanäle stehen, laufen hier orange Linien.",
    kurs_quelle: "Kurs von {boerse}, {alter}. Über Tor abgerufen.",
    kf_24h: "24 h", kf_30t: "30 T", kf_1j: "1 J", kf_5j: "5 J",
    kurs_gerade: "gerade eben",
    kurs_vor: "vor {spanne}",
    kurs_wird_geholt: "Kurs wird geholt …",
    kurs_kein_verlauf: "Noch kein Verlauf.",
    kurs_tor_aus: "Tor ist abgeschaltet — ohne Tor wird kein Kurs geholt. Eine Kursabfrage über die eigene Leitung verriete, dass hier ein Bitcoin-Knoten läuft.",
    kurs_tor_aus_kurz: "Ohne Tor kein Kurs",
    kurs_bildbeschreibung: "Kursverlauf über {fenster}, von {von} auf {bis}.",
    land_unbekannt: "Dieses Länderkürzel gibt es nicht.",
    lnd_nicht_bereit: "Lightning ist noch nicht bereit — die Wallet muss laufen und entsperrt sein.",
    news_abgewiesen: "{zahl} von {an} eingeschalteten Quellen antworten gerade nicht — meist, weil sie hinter Cloudflare stehen und Tor-Ausgangsknoten abweisen. Unter „Quellen“ steht bei jeder, was los ist.",
    news_cf: "Tor?",
    news_cf_d: "Diese Quelle steht hinter Cloudflare. Da wir ausschließlich über Tor abrufen, wird sie oft abgewiesen — abhängig vom Ausgangsknoten.",
    kurs_spanne: "Tief {tief} · Hoch {hoch}",
    news_geholt: "{zahl} Beiträge, {wann}",
    nav_lesen: "Lesen",
    nav_news: "Nachrichten",
    news_titel: "Nachrichten",
    news_lead: "Was zu Bitcoin und Lightning geschrieben wird — aus deiner Sprachregion und international. Abgerufen wird ausschließlich über Tor: sonst erführe jeder Verlag, dass hier jemand einen Knoten betreibt, und mit der Zeit auch, wann er läuft. Bilder werden nicht geladen, denn ein Vorschaubild von einem fremden Server wäre ein Zählpixel.",
    news_aus_text: "Der Nachrichten-Feed ist ausgeschaltet. Eingeschaltet ruft SatoshiCortex stündlich die ausgewählten Quellen ab — über Tor. Vorher passiert nichts.",
    news_einschalten: "Feed einschalten",
    news_tor_text: "Tor ist abgeschaltet, deshalb werden keine Nachrichten geholt. Ein Abruf über die eigene Leitung würde den Verlagen verraten, dass hier ein Bitcoin-Knoten läuft.",
    news_weit: "Auch Krypto allgemein",
    news_alle_gelesen: "Alle gelesen",
    news_quellen: "Quellen",
    news_quellen_titel: "Quellen",
    news_quellen_lead: "Fachquellen sind ungefiltert — dort ist alles Thema. Leitmedien werden nach Stichwörtern gefiltert und sind ab Werk aus: gemessen liefern sie zwischen null und zehn Prozent zum Thema.",
    news_eigene_titel: "Eigene Quelle hinzufügen",
    news_eigene_lead: "Adresse einer Webseite eintragen — wir lesen aus ihrem Kopf, ob sie einen Feed anbietet. Findet sich nichts, trägst du die Feed-Adresse direkt ein.",
    news_suchen: "Feed suchen",
    news_leer: "Noch keine Meldungen. Der erste Abruf läuft gleich nach dem Einschalten, danach stündlich.",
    news_herkunft: "Deine Region: {land} — Quellen auf {sprache} und international",
    news_herkunft_unbekannt: "Standort unbekannt — internationale Quellen auf Englisch",
    news_bezahlschranke: "Bezahlschranke",
    news_quelle_aus: "aus",
    news_kein_feed: "Dort ist kein Feed angekündigt. Trage die Feed-Adresse direkt ein, falls du sie kennst.",
    news_gefunden: "Gefunden:",
    news_fach: "Fachquelle",
    news_leit: "Leitmedium",
    news_ungeprueft: "wird gerade geholt …",
    news_speicher_fehlt: "Ohne Datenbank gibt es keinen Verlauf — die Meldungen verschwinden beim Neustart.",
    nav_logs: "Protokolle",
    log_titel: "Protokolle",
    log_lead: "Was die Dienste gerade melden. SatoshiCortex hat bewusst KEINEN Zugriff auf Docker — auf einem Gerät mit einer Wallet wäre das gleichbedeutend mit root. Gelesen wird stattdessen, was die Dienste ohnehin in dein Datenverzeichnis schreiben.",
    log_eigenes: "SatoshiCortex",
    log_neu: "Neu laden",
    log_laedt: "wird geladen …",
    log_keine_datei: "Noch keine Datei — dieser Dienst hat bisher nichts geschrieben.",
    log_zeilen_n: "{n} Zeilen",
    log_gekuerzt: "gekürzt, nur das Ende",
    log_fehler: "Konnte nicht gelesen werden.",
    protokoll_unbekannt: "Dieses Protokoll gibt es nicht.",
    ln_dienst: "Dienst",
    ln_wallet: "Wallet",
    ln_kette: "Blockkette",
    ln_d_unkonfiguriert: "wartet auf die Einrichtung",
    ln_d_wartet: "eingerichtet, noch nicht freigegeben",
    ln_d_freigegeben: "läuft",
    ln_w_aus: "LND antwortet noch nicht",
    ln_w_keine_wallet: "noch keine Wallet angelegt",
    ln_w_gesperrt: "angelegt, aber gesperrt",
    ln_w_startet: "wird gestartet",
    ln_w_bereit: "bereit",
    ln_w_wartet: "wartet auf den Start",
    ln_w_unbekannt: "unbekannter Zustand",
    ln_k_bereit: "vollständig — Lightning kann eingerichtet werden",
    ln_k_sync: "wird noch abgeglichen (Block {h})",
    ln_hinweis_sync: "Lightning braucht die vollständige Kette. Solange sie abgeglichen wird, wartet der Dienst — das ist gewollt und kostet nichts. Sobald die Kette steht, richtet SatoshiCortex ihn von allein ein; du musst nichts anstoßen.",
    tun_weg: "Nicht mehr erinnern",
    hinweis_unbekannt: "Diesen Hinweis kenne ich nicht.",
    ln_hinweis_gesperrt: "Deine Wallet ist angelegt, aber gesperrt. Solange sie zu ist, leitet dein Knoten nichts weiter und nimmt keine Zahlungen an. Unter „Wallet“ gibst du dein Wallet-Passwort ein.",
    ln_hinweis_startet: "LND fährt gerade hoch. Das dauert ein bis zwei Minuten, danach steht hier mehr.",
    ln_hinweis_laeuft: "Wallet steht, Knoten läuft, Kette aktuell. Solange du aber keinen öffentlichen Kanal hast, taucht dein Knoten NIRGENDWO im Lightning-Graphen auf — auch nicht auf amboss.space oder 1ml. Das ist keine Störung, sondern Absicht des Protokolls: ein Knoten wird erst mit seinem ersten angekündigten Kanal im Netz bekanntgemacht. Bis dahin erreicht dich nur, wem du deine Verbindungsadresse selbst gibst.",
    ln_hinweis_bereit: "Die Kette steht, und LND läuft. Der nächste Schritt ist die Wallet: Seed auf Papier, mit Gegenprobe — unter „Wallet“ in der Leiste. Bis dahin hat dieser Knoten keinen Schlüssel, meldet sich im Lightning-Netz nicht an und hält keinen Satoshi.",
    a_seit: "Sammelt seit {datum} — {tx} Transaktionen, {bloecke} Blöcke.",
    a_wartet: "Der Zulauf läuft, gesammelt wurde noch nichts.",
    a_nicht_verfuegbar: "Die Auswertung kann ihre Datenbank nicht anlegen — alles andere läuft normal weiter. Meist gehört der eingehängte Datenordner einem anderen Benutzer als dem Dienst. Grund: {grund}",
    a_luecken: "· {n} verlorene Meldungen in 24 h — dort fehlen Zeitstempel.",
    a_reorgs: "· Kettenumbauten (Reorgs) in 24 h: {n} — dabei wurde ein Block durch einen anderen ersetzt.",
    a_dia_titel: "Feerate-Diagramm",
    a_dia_d: "Was der nächste Happen Blockplatz kostet — die Kurve, gegen die Miner optimieren. Kein Explorer zeigt sie. Die senkrechte Achse ist logarithmisch: Gebühren spannen Größenordnungen, und linear läge fast alles als Strich am Boden.",
    a_dia_leer: "Noch kein Diagramm. Der erste Schnappschuss kommt innerhalb einer Minute, sobald dein Knoten Transaktionen annimmt.",
    a_dia_kein_zulauf: "Kein Diagramm, weil der Zulauf von bitcoind gerade nicht läuft. Während des Erstabgleichs ist das normal — danach deutet es auf eine gestörte Verbindung zwischen App und bitcoind (ZMQ).",
    a_dia_alt: "Stand {zeit} — seitdem kam kein neues Diagramm. Auch die kommenden Blöcke darüber sind von dann.",
    a_dia_x: "kumulativ bis {mb} MB",
    a_dia_y: "sat/vB (logarithmisch)",
    a_dia_naechster: "Kante des nächsten Blocks",
    a_dia_reinkommen: "in den nächsten Block ab {wert} sat/vB",
    a_dia_passt_alles: "Alles Wartende passt in den nächsten Block.",
    a_dia_bloecke: "{n} Blöcke",
    a_dia_block: "1 Block",
    a_grenze: "verwirft unter {wert} sat/vB",
    a_bloecke: "Blöcke",
    a_bloecke_d: "Zwei Spalten hat hier kein Explorer, weil sie DEINEM Knoten gehören: „vorher bei dir“ zählt, wie viele Transaktionen des Blocks schon bei dir lagen, und die Verweildauer sagt, wie lange sie im Mittel bei dir gewartet haben. Die Botschaft ist das, was der Miner selbst ins Feld geschrieben hat — meist seine Kennung, manchmal mehr. Im allerersten Block steht dort die Schlagzeile, mit der alles anfing.",
    a_sp_hoehe: "Höhe",
    a_sp_pool: "Pool",
    a_sp_tx: "Tx",
    a_kx_titel: "Jede wartende Transaktion",
    a_kx_d: "Eine Spalte je Block, darin jede Transaktion als Fläche nach ihrer Größe. So siehst du, was in welchen Block passt — und beim Darüberfahren, wann DEIN Knoten sie zuerst gesehen hat. Das holt der größte Aufruf, den diese Anwendung kennt, deshalb erst auf Knopfdruck.",
    a_kx_holen: "Kacheln holen",
    a_kx_laedt: "Wird geholt — bei vollem Mempool dauert das einen Moment …",
    a_kx_zu_lang: "Dein Knoten hat zu lange gebraucht, um den Mempool herauszugeben. Versuch es gleich noch einmal — ein laufender Abruf wird dabei nicht doppelt gestartet.",
    a_kx_stand: "{n} Transaktionen im Mempool, {gezeigt} davon gezeichnet.",
    a_kx_naechster: "nächster Block",
    a_kx_spaeter: "Block {n}",
    a_kb_wann: "in ~{min} min",
    a_kb_inhalt: "{n} TX · {btc} BTC",
    a_kx_tx: "Transaktion",
    a_kx_rate: "Gebühr",
    a_kx_groesse: "Größe",
    a_kx_zuerst: "zuerst bei dir",
    a_kx_ungesehen: "nicht mitgeschrieben",
    a_kx_rest: "Zusammengefasst",
    a_kx_bis: "bis herunter zu {wert} sat/vB",
    a_kx_bedienung: "Klick auf eine Spalte zeigt, was in diesem Block stehen wird. Mit der Tastatur: Pfeiltasten, Escape schließt.",
    a_kd_titel_naechster: "Der nächste Block — was voraussichtlich hineinkommt",
    a_kd_titel: "Block {n} — was voraussichtlich hineinkommt",
    a_kd_lead: "{anzahl} Transaktionen, {groesse}, zusammen {gebuehren} an Gebühren. Nach Gebühr sortiert — wer vorn steht, kommt zuerst hinein.",
    a_kd_gekuerzt: "Gezeigt werden die {n} mit der höchsten Gebühr von {gesamt}.",
    mempool_nicht_abrufbar: "Der Mempool ist gerade nicht abrufbar — dein Knoten ist beschäftigt. Versuch es gleich noch einmal.",
    mempool_zu_gross: "Die Antwort deines Knotens war größer, als ein Mempool je sein kann — dabei stimmt etwas nicht. Abgebrochen wurde absichtlich: eine Kachelansicht aus einem halben Mempool sähe richtig aus und wäre falsch. Sieh unter Protokoll → bitcoind nach.",
    a_kb_titel: "Die nächsten Blöcke",
    a_kb_d: "Was als Nächstes gefunden werden könnte — aus dem Feerate-Diagramm deines Knotens, alle 1 Mio. vByte durchgeschnitten. Nicht die Sicht eines fremden Servers, sondern das, was in DEINEM Mempool liegt.",
    a_kb_spanne: "{tief} – {hoch} sat/vB",
    a_kb_rest: "+ {n} weitere Blöcke",
    a_kb_in: "in ~{min} Minuten",
    a_kb_vor: "vor {dauer}",
    a_kb_bekannt: "{n} / {gesamt} Tx",
    a_kb_bekannt_lang: "{n} von {gesamt} Transaktionen lagen vorher bei dir",
    a_kb_nur_gesamt: "{gesamt} Tx",
    a_kb_nicht_dabei: "{gesamt} Transaktionen. Wie viele davon vorher bei dir lagen, weiß dieser Knoten nicht — der Block ist älter als seine Aufzeichnung.",
    a_nicht_dabei_kurz: "nicht dabei gewesen",
    a_bd_titel: "Block {hoehe} — was du davon gesehen hast",
    a_bd_lead: "{bekannt} von {gesamt} Transaktionen dieses Blocks lagen vorher in deinem Mempool. Die längste Wartezeit steht oben.",
    a_bd_lead_nicht_dabei: "{gesamt} Transaktionen. Dieser Block ist älter als die Aufzeichnung dieses Knotens — wie viele davon vorher in deinem Mempool lagen, lässt sich nicht nachträglich feststellen.",
    a_bd_leer: "Von diesem Block hast du keine Transaktion vorher gesehen. Entweder ist er älter als deine Aufzeichnung, oder seine Transaktionen kamen nie durch deinen Mempool.",
    a_bd_laedt: "Wird geholt …",
    a_bd_nichts: "Zu diesem Block liegt hier nichts.",
    block_unbekannt: "Diesen Block kennt deine Aufzeichnung nicht — er ist älter als der erste, den dein Knoten selbst empfangen hat.",
    a_bd_gekuerzt: "Gezeigt werden die {n} mit der längsten Wartezeit.",
    a_bd_sp_txid: "Transaktion",
    a_bd_sp_zuerst: "zuerst bei dir",
    a_bd_sp_dauer: "Verweildauer",
    a_bs_titel: "Block nachschlagen",
    a_bs_d: "Jede Höhe, nicht nur die letzten zwölf. Deine Kette ist vollständig — danach zu fragen ist der halbe Sinn eines Archiv-Knotens.",
    a_bs_suchen: "Nachschlagen",
    a_bs_null: "Block 0 — wo alles anfing",
    a_bs_kopf: "Block {hoehe}",
    a_bs_keine_hoehe: "Das ist keine Blockhöhe. Eine ganze Zahl, ab 0.",
    a_bs_zeit: "Gefunden am",
    a_bs_gewicht: "Größe",
    a_bs_hash: "Hash",
    a_bs_aus_kette: "Dieser Block ist älter als deine Aufzeichnung — er kommt direkt aus deiner Kette. „Vorher bei dir“ und die Verweildauer kann es dazu nicht geben: einen First-Seen-Zeitstempel kann man nicht nachträglich erfinden.",
    a_bs_aus_aufzeichnung: "Diesen Block hat dein Knoten selbst empfangen.",
    a_sp_botschaft: "Botschaft",
    a_sp_bekannt: "vorher bei dir",
    a_sp_dauer: "Verweildauer",
    a_sp_gebuehren: "Gebühren",
    a_pool_unbekannt: "unbekannt",
    a_pa_titel: "Wer die Blöcke findet",
    a_pa_d: "Anteile der Mining-Pools an den Blöcken, die dein Knoten selbst aufgezeichnet hat. Erkannt wird ein Pool an seiner Kennung in der Coinbase — was sich nicht zuordnen lässt, steht als „unbekannt“ da.",
    a_pa_144: "24 h",
    a_pa_1008: "7 Tage",
    a_pa_0: "Alle",
    a_pa_basis: "{n} Blöcke, Höhe {von} bis {bis}",
    a_pa_zu_wenig: "Aufgezeichnet sind erst {n} Blöcke — für diesen Zeitraum wären es {soll}. Die Anteile gelten nur für das, was da ist.",
    a_pa_leer: "Noch keine Blöcke aufgezeichnet.",
    a_pa_zeile: "{anzahl} · {anteil} %",
    pool_fenster_unbekannt: "Diesen Zeitraum gibt es hier nicht.",
    a_verfolgen: "Transaktion verfolgen",
    a_verfolgen_d: "Wann DEIN Knoten sie zuerst sah — das weiß sonst niemand.",
    a_ad_titel: "Adresse abfragen",
    a_ad_d: "Was einer Adresse JETZT gehört — die unverbrauchten Ausgaben aus dem UTXO-Satz deines Knotens. Keine Historie und keine unbestätigten Eingänge: beides steht dort nicht. Dein Knoten durchsucht dafür den ganzen Satz, das dauert einige Minuten. Die Abfrage verlässt deinen Knoten nicht.",
    a_ad_knopf: "Abfragen",
    a_ad_abbrechen: "Abbrechen",
    a_ad_laeuft: "Dein Knoten durchsucht den UTXO-Satz … {p}",
    a_ad_adresse: "Adresse",
    a_ad_bestand: "Bestand",
    a_ad_ausgaben: "Unverbrauchte Ausgaben",
    a_ad_stand: "Stand Block {hoehe} · Suche dauerte {dauer}",
    a_ad_leer: "Diese Adresse hält gerade nichts — entweder kam nie etwas an, oder alles ist schon ausgegeben. Unbestätigte Eingänge sieht diese Abfrage nicht.",
    a_ad_zeile: "Block {hoehe} · {bestaetigt} Bestätigungen",
    a_ad_weitere: "… und {n} weitere, ältere Ausgaben — der Bestand oben enthält sie.",
    a_ad_fehler: "Die Abfrage ist gescheitert: {grund}",
    a_ad_abgebrochen: "Abgebrochen.",
    a_ad_kein_bitcoind: "Dein Bitcoin-Knoten antwortet gerade nicht.",
    adresse_ungueltig: "Das ist keine gültige Bitcoin-Adresse für dieses Netz.",
    adresse_laeuft_schon: "Es läuft schon eine Abfrage — warte, bis sie fertig ist, oder brich sie ab.",
    scan_belegt: "Dein Knoten durchsucht den UTXO-Satz gerade schon für jemand anderen. Versuch es gleich noch einmal.",
    a_suchen: "Suchen",
    a_keine_txid: "Das ist keine Transaktionsnummer (txid). Eine txid hat genau 64 Zeichen aus 0–9 und a–f. Börsen wie Kraken zeigen oft eine eigene Vorgangsnummer; die echte txid steht in den Details der Auszahlung, sobald sie abgeschickt ist.",
    a_ad_ausgabe: "Ausgabe",
    lk_unterwegs: "Unbestätigt",
    lk_unterwegs_d: "Ein Teil deines On-Chain-Guthabens steht noch in keinem Block. Das ist entweder ein frischer Eingang oder dein Wechselgeld: Beim Senden wird eine ganze Münze ausgegeben, und der Rest kommt als neue, noch unbestätigte Münze zu dir zurück. Beides gehört dir schon, ausgeben lässt es sich ab der ersten Bestätigung.",
    bw_gebuehr: "Gebühr: {n} sat",
    bw_an: "An: {adresse}",
    b_budget_rest: "Vom Upload-Budget sind noch {bytes} übrig, das Fenster läuft noch {rest}. Bitcoin Core rechnet in 24 Stunden, nicht im Monat — der Regler in der Einrichtung fragt eine Monatszahl und teilt sie auf.",
    rq_titel: "Empfangen",
    rq_lead: "Stell eine Rechnung aus, damit dir jemand über Lightning Geld schickt. Sie gilt eine Stunde. Wer sie bezahlt, sieht den Betrag und den Zweck.",
    rq_betrag: "Betrag in Satoshi",
    rq_betrag_d: "Leer oder 0 lässt den Betrag offen — dann bestimmt ihn der Zahlende. Praktisch für eine Spende.",
    rq_zweck: "Wofür? Freiwillig.",
    rq_zweck_d: "Steht für den Zahlenden in der Rechnung. Schreib nichts hinein, was nicht jeder lesen soll.",
    rq_erstellen: "Rechnung erstellen",
    rq_kopiert: "Kopiert.",
    rq_gueltig: "Gültig bis {zeit}",
    rq_liste: "Deine letzten Rechnungen",
    rq_leer: "Noch keine Rechnung ausgestellt.",
    rq_offener_betrag: "Betrag offen",
    rq_zustand_offen: "offen",
    rq_zustand_bezahlt: "bezahlt",
    rq_zustand_storniert: "storniert",
    rq_zustand_unterwegs: "unterwegs",
    rq_zustand_verfallen: "abgelaufen",
    rq_weitere: "Ältere, hier nicht gezeigt: {n}",
    rq_storno: "Zurückziehen",
    rq_wartet: "Warte auf die Zahlung. Du kannst das Fenster offen lassen — sobald das Geld da ist, steht es hier.",
    rq_bezahlt: "Bezahlt. {n} sat sind angekommen.",
    rq_zurueckgezogen: "Zurückgezogen. Diese Rechnung lässt sich nicht mehr bezahlen.",
    rq_verfallen_hinweis: "Diese Rechnung ist abgelaufen. Stell eine neue aus, wenn du das Geld noch erwartest.",
    rechnung_unbekannt: "Diese Rechnung kennt dein Knoten nicht: {einzelheit}",
    rechnung_nicht_offen: "Diese Rechnung ist nicht mehr offen. Zurückziehen lässt sie sich nur, solange niemand sie bezahlt hat und sie kein Geld festhält.",
    rechnung_nicht_storniert: "Die Rechnung ließ sich nicht zurückziehen: {einzelheit}",
    rq_fehler: "Deine Rechnungen ließen sich gerade nicht abrufen.",
    rq_kein_raum: "Dir kann über Lightning gerade niemand zahlen: auf der Gegenseite deiner Kanäle liegt nichts. Empfangen kannst du nur, was dort liegt — also erst, wenn du einen Kanal hast und über ihn etwas bezahlt oder eingehende Liquidität besorgt hast.",
    rq_qr_zu_lang: "Diese Rechnung ist zu lang für einen QR-Code. Kopiere sie stattdessen.",
    rechnung_nicht_erstellt: "Die Rechnung ließ sich nicht erstellen: {einzelheit}",
    ez_qr_d: "Mit der Wallet-App scannen. Im Code steht dieselbe Adresse wie darunter — vergleiche nach dem Scannen trotzdem Anfang und Ende.",
    bw_titel: "Bewegungen",
    bw_lead: "Was in deine On-Chain-Wallet kam und was sie verlassen hat, jeweils mit der vollen Transaktionsnummer. Die Liste kommt aus deinem eigenen Knoten und frischt sich alle 30 Sekunden auf, solange diese Seite offen ist.",
    bw_leer: "Noch keine Bewegung. Eine Einzahlung erscheint hier, sobald dein Knoten sie sieht — schon vor der ersten Bestätigung.",
    bw_fehler: "Die Bewegungen ließen sich gerade nicht von LND abrufen. Beim nächsten Durchlauf wird es erneut versucht.",
    bw_bestaetigt: "Bestätigungen: {n}",
    bw_unbestaetigt: "unbestätigt, noch nicht ausgebbar",
    bw_verfolgen: "Verfolgen",
    bw_weitere: "Ältere, hier nicht gezeigt: {n}",
    bw_art_kanal_auf: "Kanal geöffnet",
    bw_art_kanal_zu: "Kanal geschlossen",
    a_tx_unbekannt: "Weder dein Knoten noch die Auswertung kennen diese Transaktion.",
    a_tx_nicht_gesehen: "Diese Transaktion lag nie in deinem Mempool — sie ist entweder älter als deine Aufzeichnung oder direkt an einen Miner gegangen.",
    a_tx_zuerst: "Zuerst gesehen von dir",
    a_tx_dauer: "Lag bei dir",
    a_tx_block: "Block",
    a_tx_entfernt: "Ohne Block aus deinem Mempool entfernt",
    a_cl_titel: "Cluster im Mempool",
    a_cl_d: "Seit Bitcoin Core 31 hängen unbestätigte Transaktionen, die aufeinander aufbauen, als Cluster zusammen. Core teilt ihn in Pakete, die nur als Ganzes in eine Blockvorlage kommen — für deine Transaktion zählt die Gebührenrate ihres Pakets, nicht ihre eigene.",
    a_cl_einzeln: "Diese Transaktion hängt an keiner anderen unbestätigten — ihr Paket ist sie selbst.",
    a_cl_umfang: "{tx} Transaktionen, {pakete} Pakete, {vb} vB",
    a_cl_paket: "Paket {nr}",
    a_cl_paket_wert: "{tx} TX · {satz} sat/vB · {vb} vB",
    a_cl_deins: "enthält deine",
    a_cl_keiner: "Kein Cluster abrufbar — die Transaktion liegt nicht (mehr) in deinem Mempool.",
    a_tx_groesse: "Größe",
    a_tx_bestaetigungen: "Bestätigungen",
    a_tx_ein_aus: "Ein- und Ausgänge",
    karte_titel: "Was dein Knoten vom Netz kennt",
    karte_lead: "Nicht „das Netz“ — eine Liste aller Bitcoin-Knoten gibt es nicht. Sondern das Adressbuch dieses Knotens: was ihm mit der Zeit zugetragen wurde. Es wächst mit ihm.",
    karte_legende: "Punkte sind Länder ohne eigenen Umriss — Singapur, Hongkong, Malta, Seychellen, Cayman. Überfahren zeigt, was wo liegt.",
    karte_marke_adressen: "{n} Adressen bekannt",
    karte_marke_nichts: "keine Adresse bekannt",
    karte_k_bekannt: "Adressen im Adressbuch",
    karte_k_ortlos: "davon ohne Ort (Tor, I2P, CJDNS)",
    karte_k_verortbar: "könnten einen Ort haben",
    karte_k_angesehen: "davon angesehen",
    karte_k_verortet: "einem Land zugeordnet",
    karte_k_ohne_form: "Länder ohne Form auf der Karte",
    karte_k_peers: "Gegenstellen gerade",
    karte_fussnote_erstsync: "0 von außen ist während des Abgleichs normal — dein Port ist offen, dein Knoten nur zu beschäftigt zum Antworten. Das gibt sich, sobald die Kette steht.",
    karte_fussnote_auswahl: "Angesehen wird, was dein Knoten anderen weiterreichen würde — Core wählt das selbst nach Güte und Alter aus.",
    karte_linien: "Die Linien laufen von deinem Knoten in {land} zu den Ländern, in denen deine Gegenstellen gerade sitzen.",
    karte_linien_ohne_ort: "Wo dein Knoten selbst steht, lässt sich nicht bestimmen — eine Tor-Adresse hat keinen Ort. Die Karte zeigt deshalb Länder, aber keine Verbindungen.",
    karte_mit_peers: "{p} deiner Gegenstellen sitzen hier",
    karte_mit_peers_1: "Eine deiner Gegenstellen sitzt hier",
    karte_wird_ausgewertet: "Das Adressbuch wird gerade ausgewertet — gleich stehen hier Länder.",
    karte_keine_tabelle: "In diesem Abbild fehlt die Ortstabelle. Die Zahlen stimmen, die Karte bleibt ohne Länder.",
    karte_quelle: "Umrisse: Natural Earth (gemeinfrei) · Orte: DB-IP Lite {stand} (CC BY 4.0), im Abbild, keine Abfrage nach außen.",
    e_updates: "Aktualisierungen",
    e_akt_aktuell: "Dein Knoten läuft auf der neuesten Fassung.",
    e_akt_abbild_aktuell: "Die ausgelieferte Fassung ist die neueste.",
    e_akt_nur_abbild: "Läuft hier noch nicht. Verglichen wird deshalb mit der Fassung, die SatoshiCortex ausliefert — ob die noch aktuell ist, zählt schon vorher.",
    e_akt_wartung: "Version {v} ist verfügbar — eine Wartungsversion im selben Zweig. Sie lässt sich gefahrlos einspielen.",
    e_akt_zweig: "Version {v} ist verfügbar — ein Zweigwechsel. Der kann Regelwerk und Datenbankformat ändern; lies vorher die Anmerkungen zur Veröffentlichung.",
    e_akt_auch: "Außerdem verfügbar: {v}.",
    e_akt_neuer: "Version {v} ist verfügbar. Was sich geändert hat, steht im Changelog des Projekts.",
    e_akt_nachgesehen: "Zuletzt nachgesehen: {zeit}",
    e_akt_eigen_latest: "Du folgst „latest“ — neu ziehen genügt, die .env bleibt, wie sie ist. In der Docker-Oberfläche deines NAS das Abbild neu laden und den Dienst neu starten, oder: „docker compose pull app“ und „docker compose up -d app“.",
    e_akt_eigen_fest: "In deiner .env steht eine feste Nummer ({folgt}). Setz die Zeile oben ein und stell den Dienst neu bereit — oder schreib „latest“ hinein, dann genügt künftig das Neuziehen.",
    e_akt_eigen_unklar: "Steht in deiner .env SATCORTEX_VERSION=latest, genügt es, das Abbild neu zu ziehen. Steht dort eine Nummer, setz sie auf {v} — oder auf „latest“, dann bleibst du künftig von selbst aktuell.",
    e_akt_wie: "In der .env die Zeile hochsetzen (BITCOIN_VERSION= bzw. LND_VERSION=), dann neu bereitstellen. Haben wir das Abbild noch nicht gebaut, findet das Ziehen nichts — dann baust du es selbst: „docker compose build lnd“ und „docker compose up -d“. Das dauert etwa eine Minute: geladen, Signatur gegen die gepinnten Herausgeberschlüssel geprüft, ausgepackt. Übersetzt wird nichts.",
    e_akt_fassung_unbekannt: "Der Dienst läuft — seine Fassungsnummer ließ sich gerade nur nicht abfragen. Sie kommt aus derselben Auskunft, die während des Erstabgleichs regelmäßig wartet. Beim nächsten Durchgang steht sie wieder da.",
    e_akt_laeuft_nicht: "Der Dienst läuft noch nicht — es gibt keine laufende Fassung, mit der sich vergleichen ließe. Sobald er läuft, wird nachgesehen.",
    e_akt_nicht_erreichbar: "Die Abfrage kam über Tor nicht durch. Das passiert — der Weg geht über drei fremde Rechner. Es wird beim nächsten Durchgang erneut versucht.",
    e_akt_tor_aus: "Ohne Tor wird nicht nachgefragt. Eine Versionsabfrage verrät sonst, dass hier ein Bitcoin-Knoten läuft — und mit der Zeit auch, wann.",
    e_akt_wartet: "Noch nicht nachgesehen. Die Abfrage läuft einmal täglich über Tor.",
    e_akt_zahlen: "Läuft: {laeuft}  ·  Neueste bekannte: {neu}",
    e_akt_unbekannt: "unbekannt",
    e_akt_kein_status: "Der Stand der Fassungsprüfung ließ sich gerade nicht abrufen — die Auskunft dazu kommt vom Knoten, und der ist während des Erstabgleichs zeitweise beschäftigt. Beim nächsten Durchgang steht sie wieder da.",
    e_adresse_beispiel: "z. B. meinknoten.example.net",
    e_adresse_aktuell: "Angekündigt wird zurzeit: {liste}",
    e_adresse_keine: "Zurzeit kündigt dein Knoten keine Adresse an — deshalb findet ihn niemand von außen.",
    e_gespeichert: "Gespeichert. Der Knoten startet gleich neu und kündigt die Adresse dann an.",
    e_fehler: "Das hat nicht geklappt.",
    konfiguration_fehlt: "Es gibt noch keine Konfiguration, die sich ändern ließe.",
    noch_nicht_eingerichtet: "Der Knoten ist noch nicht eingerichtet.",
    n_forward: "im Router weiterleiten, IPv4 und IPv6",
    n_note: "Ohne diese Freigaben läuft der Knoten trotzdem — er nimmt dann aber nur, statt auch zu geben. Du kannst das jederzeit später nachholen.",

    k_title: "Dein Konto",
    k_lead: "Damit nicht jeder im Netzwerk deine Oberfläche bedienen kann.",
    k_local: "Wird im nächsten Schritt eingerichtet.",

    f_title: "Alles bereit",
    f_lead: "Prüf noch einmal, dann legen wir los.",
    f_start: "Der Knoten beginnt danach mit dem Abgleich der Blockkette. Das dauert Tage bis Wochen und läuft im Hintergrund — du kannst dieses Fenster schließen und den Rechner neu starten.",

    d_services: "Dienste",
    d_phase_sync: "Erster Abgleich",
    d_phase_fertig: "Auf aktuellem Stand",
    d_phase_start: "Wird gestartet",
    d_phase_laedt: "Wird geladen",
    d_phase_getrennt: "Keine Verbindung",
    d_note_getrennt: "Die Oberfläche erreicht gerade ihren eigenen Dienst nicht. Das sagt nichts über deinen Knoten — der läuft im Hintergrund weiter. Meist ist es ein Netzwerkhänger; lade die Seite gleich noch einmal.",
    wl_unklar_titel: "Nicht abrufbar",
    wl_unklar_d: "Der Zustand der Wallet lässt sich gerade nicht abfragen. Hier steht deshalb nichts — insbesondere nicht der Ablauf zum Anlegen: eine Abfrage, die nicht durchkam, ist kein Beweis, dass es noch keine Wallet gibt. Versuch es in einem Moment noch einmal.",
    d_sub_laedt: "Die Zahlen werden geholt …",
    d_note_laedt: "Beim Neuladen der Seite wird alles frisch geholt. Läuft gerade ein Abgleich, kann die erste Antwort ein paar Sekunden dauern — dein Knoten läuft dabei ununterbrochen weiter.",
    d_phase_beschaeftigt: "Schreibt gerade weg",
    d_note_beschaeftigt: "bitcoind läuft, kommt aber gerade nicht zum Antworten: es schreibt den geprüften Stand auf die Platte. Die Zahlen oben sind ein paar Sekunden alt. Kein Neustart, kein Fehler — und genau der Vorgang, der den Abgleich ausbremst, wenn die Ablage langsam ist.",
    d_sub_sync: "Block {hoehe} von {kopf} ({blockanteil} % der Blöcke) · {belegt} auf der Platte",
    d_sub_fertig: "Höhe {hoehe} · {belegt} auf der Platte",
    d_sub_start: "Warte auf die erste Antwort von bitcoind …",
    d_tempo: "{bpm} Blöcke/Minute",
    d_restdauer: "noch etwa {dauer}",
    d_restdauer_unbekannt: "wird noch gemessen",
    d_mempool: "Wartende Transaktionen",
    d_k_wartend: "Im Mempool",
    d_k_belegung: "Belegt",
    d_k_purge: "Verwerfungsgrenze",
    d_k_gebuehren: "Wartende Gebühren",
    d_tx: "{n} Transaktionen",
    d_satvb: "{n} sat/vB",
    d_purge_hilfe: "Die Verwerfungsgrenze ist die Zahl, die kein öffentlicher Explorer zeigen kann: unterhalb davon wirft DEIN Knoten gerade weg. Die großen Dienste drehen ihr Limit so hoch, dass sie nie verwerfen müssen — sie sehen diese Grenze nie.",
    d_purge_ruhig: "Dein Mempool ist nicht voll — es wird nichts verworfen. Aufgenommen wird alles ab {n} sat/vB; ob es bald in einen Block kommt, zeigt das Feerate-Diagramm.",
    d_purge_voll: "Dein Mempool ist voll. Alles unter {n} sat/vB fliegt gerade raus.",
    d_teilnahme: "Teilnahme",
    d_blockzeit: "Blockzeit",
    bz_takt: "Takt",
    bz_takt_wert: "{min} min je Block",
    bz_takt_gemessen: "Takt gemessen an dieser Kette, über die letzten {n} Blöcke.",
    bz_takt_gerechnet: "Der eigene Takt ist erst nach dem Abgleich messbar — bis dahin gerechnet mit dem Zielabstand von zehn Minuten.",
    bz_halbierung: "Nächste Halbierung",
    bz_wann: "Geschätzt",
    bz_etwa: "etwa {monat}",
    bz_belohnung: "Belohnung",
    bz_belohnung_wert: "{jetzt} → {danach} BTC",
    bz_wartet: "Sobald der Knoten antwortet.",
    bz_ende: "Es wird nichts mehr ausgeschüttet — alle Bitcoin sind da.",
    d_kurs: "Bitcoin-Kurs",
    d_kurs_je_euro: "Für eine Einheit",
    d_kurs_wartet: "Der Kurs wird über Tor geholt — beim ersten Mal dauert das bis zu einer Minute.",
    d_wallet: "Dein Guthaben",
    d_lightning: "Lightning",
    d_w_keine_wallet: "Noch keine Wallet angelegt. Das geht unter Lightning → Einrichtung, sobald die Kette steht.",
    d_w_gesperrt: "Die Wallet ist gesperrt. Unter Lightning → Wallet kannst du sie entsperren — vorher sieht dein Knoten sein eigenes Guthaben nicht.",
    d_w_ohne_einrichtung: "Zuerst die Einrichtung abschließen.",
    d_index_aus: "Die Indizes sind noch abgeschaltet — sie werden nach dem Abgleich gebaut.",
    d_index_baut: "{name} wird aufgebaut: Block {hoehe} von {ziel}",
    d_netz: "Netz und Beitrag",
    d_k_netze: "Verbindungen nach Netz",
    d_k_empfangen: "Empfangen",
    d_k_gesendet: "Ausgeliefert seit dem Start",
    d_k_adressen: "Erreichbar unter",
    d_keine_adresse: "noch keine eigene Adresse bekannt",
    d_gesendet_hilfe: "Ausgeliefert misst deinen Beitrag — gezählt seit dem letzten Start von bitcoind, über alle Gegenstellen, die seitdem verbunden waren. Die Aufteilung darunter zählt etwas anderes: nur, was an die JETZT verbundenen ging. Deshalb ist sie kleiner, und deshalb passen die beiden Zahlen nicht zusammen.",
    d_gesendet_hilfe_sync: "Ausgeliefert misst deinen Beitrag — gezählt seit dem letzten Start von bitcoind. Während des Abgleichs bleibt es wenig: du lädst gerade selbst. Die Aufteilung darunter zählt nur, was an die JETZT verbundenen Gegenstellen ging, ist also kleiner.",
    d_tage: "{n} Tagen", d_tag: "einem Tag",
    d_stunden: "{n} Stunden", d_stunde: "einer Stunde",
    d_minuten: "{n} Minuten", d_minute: "einer Minute",
    d_k_peers: "Verbindungen",
    d_peers: "{aus} von mir aufgebaut · {ein} von außen angenommen",
    d_peers_unbekannt: "gerade nicht abrufbar",
    d_note_unbekannt: "Ob dich von außen jemand erreicht, ließ sich gerade nicht abfragen — dein Knoten war mit dem Abgleich beschäftigt. Das ist keine Aussage über deine Erreichbarkeit, sondern über den Zeitpunkt. Beim nächsten Abruf steht es wieder da.",
    d_peers_hilfe: "Die Richtung sagt, wer angeklopft hat — nicht, wohin die Daten fließen. Die von außen angenommenen messen deine Erreichbarkeit.",
    d_fremdes_netz: "Achtung: dein Knoten läuft auf „{netz}“, nicht auf Mainnet. Das sind getrennte Netze — Guthaben dort sind wertlos, und was du hier siehst, ist nicht die echte Bitcoin-Blockkette.",
    d_note_sync: "Die Prozentzahl zählt Prüfarbeit, nicht Blöcke — Blöcke von 2009 tragen eine Transaktion, heutige tausende. Sie zieht später steil an. Aus demselben Grund sinkt die Rate der Blöcke pro Minute, je weiter du kommst: ein Block von 2013 ist in Sekundenbruchteilen geprüft, einer von heute trägt tausende Signaturen. Vergleich sie also nicht mit der von letzter Woche — es zählt die Restdauer. Du kannst das Fenster schließen, der Abgleich läuft weiter.",
    d_note_start: "bitcoind antwortet nicht. Kurz nach einem Start oder Neustart ist das normal — er lädt dann seinen chainstate, und das dauert auf einem NAS einige Minuten. Bleibt es dabei, lohnt ein Blick ins Protokoll unter „bitcoind“.",
    d_note_zuschauer: "Port 8333 nimmt keine eingehenden Verbindungen an. Dein Knoten lädt und prüft alles selbst, aber niemand kann bei dir synchronisieren — du schaust zu, statt mitzumachen.",
    d_note_teilnehmer: "Dein Knoten ist von außen erreichbar und liefert anderen die Kette aus.",

    sv_unkonfiguriert: "wartet auf Einrichtung",
    sv_wartet: "eingerichtet, angehalten",
    sv_freigegeben: "läuft",


    // — Meldungen, die der Server als Schlüssel schickt —
    platz_genug: "{frei} GB frei — das reicht mit Puffer für die nächsten Jahre.",
    platz_knapp: "{frei} GB frei. Es läuft an, wird aber eng: die Kette wächst um rund {wachstum} GB im Jahr. Für entspannten Betrieb fehlen etwa {fehlend} GB.",
    platz_zu_wenig: "Nur {frei} GB frei, nötig sind mindestens {mindestens} GB. Beschneiden der Kette ist keine Lösung: nur ein vollständiger Knoten kann anderen die Kette ausliefern, und die Transaktionssuche braucht den ganzen Index.",
    pfad_fehlt: "Den Ort {pfad} gibt es nicht. Trage in der .env unter {variable} einen vorhandenen Pfad ein und starte neu.",
    eine_platte: "Beide Orte liegen auf demselben Datenträger. Das läuft — aber dann liegt alles dort: die rund 840 GB Blockkette samt dem kleinen Teil, der eigentlich auf eine schnelle Platte gehört. Hat dieses Gerät eine SSD und eine große Festplatte, trenne die beiden Orte: die Blöcke auf die große, der Rest (~25 GB) auf die schnelle. Sonst dauert der erste Abgleich deutlich länger, weil die Zustandsdatenbank ständig viele kleine verstreute Zugriffe macht.",
    platz_reicht_nicht: "Der Speicherplatz reicht nicht.",
    upload_unbegrenzt: "Unbegrenzt: dein Knoten liefert Neueinsteigern die ganze Kette aus. Das ist der größte Beitrag überhaupt — kostet aber mehrere hundert Gigabyte im Monat.",
    upload_begrenzt: "Rund {upload_gb} GB im Monat. Ist das Budget aufgebraucht, liefert dein Knoten keine ALTEN Blöcke mehr aus. Neue Blöcke und Transaktionen reicht er weiterhin ganz normal weiter — du bleibst also voll am laufenden Netz beteiligt.",
    g_neu_title: "Geräte-Konto anlegen",
    g_neu_lead: "Bevor es losgeht: sichere die Oberfläche ab. Ohne Konto könnte jeder in deinem Netz den Knoten umkonfigurieren.",
    g_an_title: "Anmelden",
    g_an_lead: "Willkommen zurück.",
    g_oidc_knopf: "Mit Pocket ID anmelden",
    g_oidc_d: "Du wirst zu deinem eigenen Ausweisdienst geschickt und meldest dich dort an — hier wird kein Passwort eingegeben und keines gespeichert.",
    g_oidc_trenner: "Oder mit dem lokalen Konto — das ist die Nottür für den Fall, dass der Ausweisdienst einmal nicht erreichbar ist. Sie geht nur im Heimnetz auf.",
    g_oidc_abgelehnt: "Dein Ausweisdienst hat die Anmeldung abgelehnt. Meist heißt das: dein Konto gehört keiner Gruppe an, die für SatoshiCortex freigegeben ist.",
    g_oidc_abgelaufen: "Der Anmeldevorgang ist abgelaufen oder gehört nicht hierher. Fang noch einmal an.",
    g_oidc_ungueltig: "Der Ausweis wurde nicht angenommen. Steht im Protokoll genauer.",
    oidc_aus: "Für diesen Knoten ist kein Ausweisdienst eingetragen.",
    oidc_nicht_erreichbar: "Dein Ausweisdienst antwortet gerade nicht. Solange er ausfällt, kommst du über das lokale Konto im Heimnetz herein.",
    nur_ueber_oidc: "Von außen geht die Anmeldung nur über deinen Ausweisdienst. Das lokale Konto ist die Nottür und öffnet sich nur im Heimnetz.",
    g_user: "Benutzername", g_pass: "Passwort",
    g_anlegen: "Konto anlegen", g_anmelden: "Anmelden",
    g_pass_hint: "Mindestens 10 Zeichen.",
    benutzer_ungueltig: "Der Benutzername ist ungültig.",
    konto_existiert: "Es gibt bereits ein Konto auf diesem Gerät.",

    // ── Die PIN ─────────────────────────────────────────────────────────
    keine_pin: "Auf diesem Gerät ist keine PIN eingerichtet.",
    pin_noetig: "Dafür braucht es deine PIN.",
    pin_titel: "PIN für Handgriffe mit Folgen",
    pin_lead: "Ein zweites Schloss vor allem, was sich nicht rückgängig machen lässt. Freiwillig — ohne eingerichtete PIN ändert sich nichts.",
    pin_erklaerung: "Sie schützt gegen etwas anderes als dein Entsperrweg. Der entscheidet, was jemand mit der PLATTE anfangen kann; die PIN steht gegen eine übernommene Sitzung in genau dieser Oberfläche — ein offen stehender Browser, ein fremder Zugriff auf dein Konto. Fünf Fehlversuche sperren sie fünfzehn Minuten, und der Zähler liegt in einer Datei: ein Neustart setzt ihn nicht zurück. Sie bewacht heute das Löschen der Wallet; jeder weitere Handgriff mit Folgen kommt dazu, sobald es ihn gibt.",
    pin_stand_aus: "Zurzeit keine PIN eingerichtet.",
    pin_stand_an: "PIN eingerichtet. Handgriffe mit Folgen fragen danach.",
    pin_stand_gesperrt: "Gesperrt nach zu vielen Fehlversuchen — noch {sekunden} Sekunden.",
    pin_kontopasswort: "Dein Kontopasswort",
    pin_kontopasswort_d: "Nicht das Wallet-Passwort, sondern das, mit dem du dich hier anmeldest. Ohne diese Frage könnte eine übernommene Sitzung sich selbst eine PIN geben — und danach alles freigeben.",
    pin_neu: "Deine PIN",
    pin_neu_d: "Fünf bis zwölf Ziffern. Keine Reihe, keine sechsmal dieselbe Ziffer — beides steht bei jedem Angreifer an erster Stelle.",
    pin_wdh: "Noch einmal",
    pin_alt: "Deine jetzige PIN",
    pin_stimmt_nicht: "Die beiden Eingaben sind nicht gleich.",
    pin_einrichten: "PIN einrichten",
    pin_eingerichtet: "Eingerichtet.",
    pin_aendern: "PIN ändern",
    pin_geaendert: "Geändert.",
    pin_entfernen: "PIN abschaffen",
    pin_entfernt: "Abgeschafft. Es fragt jetzt nichts mehr danach.",
    tg_pin: "Deine PIN",
    tg_pin_d: "Das Löschen ist der Handgriff, den die PIN bewacht.",
    zl_titel: "Eine Lightning-Rechnung bezahlen",
    zl_lead: "Über Lightning statt über die Kette: in Sekunden statt in Blöcken, und für einen Bruchteil der Gebühr. Voraussetzung ist ein Kanal mit Guthaben auf deiner Seite.",
    zl_rechnung: "Die Rechnung",
    zl_rechnung_d: "Die lange Zeichenkette, die mit lnbc beginnt. Ein „lightning:“ davor stört nicht, das schneide ich weg.",
    zl_betrag: "Betrag (sat)",
    zl_betrag_d: "Diese Rechnung nennt keinen Betrag — dann bestimmst du ihn.",
    zl_lesen: "Rechnung ansehen",
    zl_zahlen: "Bezahlen",
    zl_v_betrag: "Betrag",
    zl_v_gebuehr: "Weiterleitung",
    zl_v_hoechstens: "höchstens {n} sat",
    zl_v_zweck: "Wofür",
    zl_v_ziel: "An wen",
    zl_abgelaufen: "Diese Rechnung ist abgelaufen. Lass dir eine neue geben — bezahlen lässt sie sich nicht mehr.",
    zl_betrag_fehlt: "Trag einen Betrag ein, dann kannst du bezahlen.",
    zl_erst_lesen: "Erst ansehen. Der Knopf geht auf, wenn du weißt, was du bezahlst.",
    zl_unterwegs: "Unterwegs — das kann bis zu einer Minute dauern. Nicht noch einmal drücken.",
    zl_bezahlt: "Bezahlt: {betrag} sat, dazu {gebuehr} sat Weiterleitung.",
    ko_ansehen: "Knoten ansehen",
    ko_b_unbekannt: "Diesen Knoten kennt dein Graph nicht — entweder ist die Kennung falsch, oder er kündigt sich nicht an (genau wie dein eigener Knoten, solange er keinen öffentlichen Kanal hat). Ein Kanal ist trotzdem möglich, wenn du seine Adresse kennst: häng sie als „@host:9735“ an und nimm „Verbinden“. Ohne Adresse geht es nicht — dein Knoten wüsste nicht, wo er anklopfen soll.",
    ko_b_name: "Name",
    ko_b_kanaele: "Kanäle",
    ko_b_kapazitaet: "Kapazität",
    ko_b_gemeldet: "Zuletzt gemeldet",
    ko_b_vor_tagen: "vor {n} Tagen",
    ko_b_still: "Dieser Knoten hat sich seit Wochen nicht gemeldet. Das ist der teuerste Fall von allen: verschwindet die Gegenstelle, gibt es kein einvernehmliches Schließen mehr — nur noch das erzwungene, mit Gebühren und Wartezeit.",
    ko_b_ohne_adresse: "Dieser Knoten kündigt keine Adresse an. Dein Knoten kann ihn dann von sich aus nicht erreichen.",
    ko_b_wenig: "Wenige Kanäle — dieser Knoten ist kaum eingebunden. Über ihn führt fast kein Weg ins restliche Netz.",
    ko_b_nur_tor: "Nur über Tor erreichbar. Kein Mangel, aber ein Unterschied: dieser Kanal hängt dann an Tor.",
    ko_b_unauffaellig: "Nichts Auffälliges: meldet sich regelmäßig, ist erreichbar und gut eingebunden.",
    gegenstelle_unlesbar: "Die Gegenstelle ließ sich nicht ansehen: {grund}",
    ks_titel: "Einen Kanal schließen",
    ks_lead: "Das Guthaben aus dem Kanal kommt zurück auf deine On-Chain-Wallet. Einvernehmlich geht das günstig und sofort — beide Seiten unterschreiben gemeinsam.",
    ks_kanal: "Welcher Kanal",
    ks_still: "still",
    ks_erzwingen: "Erzwingen",
    ks_erzwingen_d: "Nur, wenn die Gegenstelle nicht mehr antwortet.",
    ks_warnung: "Erzwungen heißt: dein Guthaben liegt danach für eine Zeitsperre fest — meist rund einen Tag, bei hohen Gebühren länger. Und es wird teurer, weil zur Verpflichtungstransaktion noch die Ausgaben zum Einsammeln kommen. Nimm das nur, wenn das einvernehmliche Schließen wirklich scheitert.",
    ks_los: "Kanal schließen",
    ks_laeuft: "Wird geschlossen — einen Moment.",
    ks_fertig: "Der Kanal wird geschlossen. Schließtransaktion: {txid}. Sobald sie bestätigt ist, ist das Guthaben zurück auf der Wallet.",
    ks_fertig_erzwungen: "Erzwungen geschlossen. Schließtransaktion: {txid}. Dein Guthaben ist nach Ablauf der Zeitsperre verfügbar, nicht sofort.",
    schliessen_abgelehnt: "Das Schließen wurde abgelehnt: {einzelheit}",
    schliessen_unklar: "Keine Antwort innerhalb der Wartezeit. Das Schließen kann trotzdem laufen — NICHT wiederholen, sondern in der Kanalliste nachsehen.",
    tun_wachturm: "Du hast Kanäle, aber kein Wachturm bewacht sie. Läuft dein Knoten einmal nicht — Stromausfall, Update, Plattenschaden — und die Gegenstelle versucht es mit einem alten Kanalzustand, merkt es niemand.",
    tun_wachturm_knopf: "Wachturm eintragen",
    us_titel: "Zwischen deinen Kanälen umschichten",
    us_lead: "Liegt in einem Kanal alles auf deiner Seite und im anderen nichts, kannst du zwar noch zahlen, aber nicht mehr empfangen — oder umgekehrt. Umschichten schiebt Liquidität dorthin, wo sie fehlt: eine Zahlung an dich selbst, raus durch den einen Kanal, zurück herein über den anderen. Das Geld bleibt die ganze Zeit deins, es wechselt nur die Seite. Verloren gehen kann nur die Gebühr für den Rundweg.",
    us_von: "Hinaus durch",
    us_von_d: "Dieser Kanal wird leerer. Daneben steht, was gerade hinausgehen kann.",
    us_nach: "Zurück herein über",
    us_nach_d: "Über diese Gegenstelle kommt es zurück — der Kanal wird voller. Daneben steht, was drüben liegt.",
    us_betrag: "Betrag (sat)",
    us_betrag_d: "Kleine Beträge finden eher einen Weg als große. Bei einem Fehlschlag lohnt es sich, die Hälfte zu nehmen.",
    us_los: "Umschichten",
    us_laeuft: "Sucht einen Rundweg — das kann bis zu einer Minute dauern.",
    us_fertig: "Umgeschichtet: {betrag} sat, dazu {gebuehr} sat für den Rundweg.",
    us_gleicher_kanal: "Hinaus und zurück über denselben Kanal — dafür gibt es keinen Rundweg. Nimm zwei verschiedene.",
    umschichten_gescheitert: "Es ließ sich kein Rundweg finden: {einzelheit}. Das ist normal — versuch einen kleineren Betrag oder eine andere Richtung.",
    wt_eigen_titel: "Dein eigener Wachturm",
    wt_eigen_d: "Dein Knoten bewacht seit dem ersten Tag fremde Kanäle — ohne dass du etwas tun musstest. Das ist der direkteste Beitrag überhaupt: du verhinderst Betrug bei Leuten, die du nie treffen wirst. Damit dich jemand eintragen kann, braucht er diese Adresse.",
    wt_eigen_ohne: "Dein Turm läuft — aber er hat keine Adresse, unter der ihn jemand von außen erreicht. Damit kann ihn niemand eintragen, und der Beitrag verpufft. Das ändert sich, sobald dein Knoten eine Adresse ankündigt: unter Einstellungen → Sichtbarkeit. Über Tor bekommt der Turm eine eigene .onion, im Clearnet braucht er eine Router-Freigabe auf 9911.",
    wt_eigen_fuss: "Zwei Dinge dazu, damit keine falsche Erwartung entsteht: Der Turm bringt dir KEINE Gebühren ein — LND betreibt ihn ausdrücklich altruistisch, bezahlte Türme sind entworfen, aber nicht scharf. Und du erfährst nie, wen oder wie viel du bewachst: der Turm bekommt verschlüsselte Päckchen, die er erst öffnen kann, wenn die passende Transaktion in der Kette auftaucht. Das ist keine Lücke, sondern der Grund, warum man ihm vertrauen kann.",
    ht_titel: "Was durch deinen Knoten ging",
    ht_lead: "Nicht nur, was gelungen ist — vor allem, was NICHT gelungen ist und warum. Genau darin steckt der Handgriff: ein Kanal, an dem ständig das Guthaben ausgeht, gehört nachgefüllt oder teurer gemacht.",
    ht_gruende_titel: "Woran es in den letzten sieben Tagen scheiterte",
    ht_mal: "{n}× · Kanal {kanal}",
    ht_leer: "Noch nichts durchgegangen. Sobald der erste Kanal steht und jemand über dich zahlt, steht es hier.",
    ht_gebuehr: "{n} sat verdient",
    ht_a_weiterleiten: "Weiterleitung begonnen",
    ht_a_erledigt: "Durchgegangen",
    ht_a_fehl: "Weiter hinten gescheitert",
    ht_a_link_fehl: "Bei uns gescheitert",
    ht_g_insufficient_balance: "Guthaben reichte nicht — dieser Kanal ist auf deiner Seite leer",
    ht_g_htlc_exceeds_max: "Betrag über dem Kanal-Höchstwert",
    ht_g_fee_insufficient: "Angebotene Gebühr zu niedrig für deine Einstellung",
    ht_g_expiry_too_soon: "Zeitfenster zu knapp",
    ht_g_invalid_keysend: "Keysend nicht angenommen",
    ht_g_channel_disabled: "Kanal war abgeschaltet",
    wt_titel: "Wachtürme",
    wt_lead: "Veröffentlicht eine Gegenstelle einen ALTEN Kanalzustand, muss das innerhalb der Zeitsperre bestraft werden — sonst ist das Guthaben weg. Läuft dein Knoten in dem Moment gerade nicht, merkt es niemand. Genau dafür ist ein fremder Wachturm da: er kennt nur den Strafzug und kann damit selbst kein Geld bewegen.",
    wt_keiner: "Kein Wachturm eingetragen. Solange dein Knoten durchläuft, merkt er einen Betrugsversuch selbst — aber bei Stromausfall, Update oder Plattenschaden ist niemand da. Bei einer Wallet auf einem Gerät, das durchlaufen soll, ist das keine Kür.",
    wt_grenze: "Was sich prüfen lässt: ob ein Turm erreichbar ist, eine Sitzung mit deinem Knoten angenommen hat und deine Kanalstände bestätigt. Was sich nicht prüfen lässt: ob er im Ernstfall wirklich eingreift — die Päckchen sind verschlüsselt, auch für ihn, und das zeigt sich erst bei einem Betrugsversuch.",
    wt_gedeckt: "Bewacht. Für jede Kanalart, die du hast, hält ein Turm eine Sitzung mit deinem Knoten — er war erreichbar und hat zugesagt, deine Kanalstände anzunehmen.",
    wt_gedeckt_vorab: "Bereit. Ein Turm hält schon eine Sitzung mit deinem Knoten. Sobald du einen Kanal hast, gehen dessen Stände dorthin.",
    wt_ungedeckt: "Nicht bewacht — kein Turm hält eine Sitzung für: {arten}. Eingetragen heißt nicht bewacht. Meist ist der Turm nicht erreichbar (Adresse, Port, Tor) oder nimmt diese Kanalart nicht an. LND versucht es selbst weiter; direkt nach dem Eintragen kann das ein paar Minuten dauern.",
    wt_ungedeckt_vorab: "Noch keine Sitzung — bisher hat kein Turm zugesagt für: {arten}. Solange du keinen Kanal hast, ist nichts in Gefahr, aber so, wie es steht, wäre ein neuer Kanal unbewacht. Meist ist der Turm nicht erreichbar (Adresse, Port, Tor). Direkt nach dem Eintragen kann es ein paar Minuten dauern.",
    wt_art_legacy: "ältere Kanäle",
    wt_art_anchor: "Anker-Kanäle",
    wt_art_taproot: "Taproot-Kanäle",
    wt_turm_art: "{art}: Sitzung steht, bestätigte Stände: {n}",
    wt_turm_ohne: "keine Sitzung",
    wt_turm_reserve: "in Reserve — ein anderer Turm hält die Sitzung",
    wachturm_unbekannt: "Diesen Turm führt LND nicht (mehr) in seiner Liste. Lade die Seite neu.",
    wt_pruef_zu_lang: "die Messung hat zu lange gedauert. Über Tor kann das vorkommen — probier es noch einmal. Steht danach unter Protokoll → SatoshiCortex eine Zeile „Wachturm geprüft“, war der Knoten fertig und nur die Antwort kam nicht an; dann ist ein Reverse Proxy davor zu ungeduldig.",
    wt_pruef_keine_antwort: "keine Antwort vom Knoten",
    wt_pruefen: "Prüfen",
    wt_pruefen_laeuft: "wird geprüft — über Tor dauert das bis zu einer Minute",
    wt_pruef_da: "erreichbar — der Turm nimmt an. Kommt trotzdem keine Sitzung zustande, liegt es nicht an ihm.",
    wt_pruef_tot: "nicht erreichbar: {grund}. Bei einer .onion heißt das meist, dass es den Dienst nicht mehr gibt — dann gehört der Eintrag ausgetragen.",
    wt_pruef_zu: "erreicht, aber dahinter nimmt niemand an. Der Rechner ist da, der Wachturm läuft nicht.",
    wt_pruef_fehler: "Die Prüfung kam nicht zustande: {grund}",
    wt_turm_eigen: "dein eigener Turm — schützt diesen Knoten nicht",
    wt_turm_eigen_sitzung: "dein eigener Turm: Sitzung steht, schützt diesen Knoten aber nicht — er läuft auf demselben Gerät und fällt mit ihm aus",
    wt_zaehler: "Seit dem letzten Start von LND bestätigte Kanalstände: {bestaetigt}, noch ausstehend: {ausstehend}. Neue Stände entstehen bei Zahlungen, Weiterleitungen und Gebührenanpassungen im Kanal — ohne die bleibt es bei null, und das ist in Ordnung.",
    wt_zaehler_abgewiesen: "Kanalstände, die sich bei keinem Turm sichern ließen: {n}. Für diese Stände gibt es keinen Schutz.",
    wt_adresse: "Wachturm eintragen",
    wt_adresse_d: "Kennung@Adresse:Port, so wie beim Kanal. Betreiber findest du in denselben Verzeichnissen wie Kanalpartner — viele Knoten betreiben einen nebenbei.",
    wt_eintragen: "Eintragen",
    wt_entfernen: "Entfernen",
    wt_entfernen_sicher: "Wirklich entfernen?",
    wt_entfernt: "Ausgetragen. Hielt der Turm eine Sitzung, handelt LND mit dem nächsten eingetragenen eine neue aus — noch nicht bestätigte Kanalstände gehen dabei nicht verloren.",
    wachturm_nicht_entfernt: "LND hat das Austragen abgelehnt: {grund}",
    wachturm_offene_staende: "Bei diesem Turm liegen noch Kanalstände, die er noch nicht bestätigt hat. LND trägt ihn deshalb gerade nicht aus — versuch es in ein paar Minuten noch einmal.",
    wachturm_abgelehnt: "Der Wachturm wurde nicht angenommen: {grund}",
    ko_titel: "Einen Kanal öffnen",
    ko_lead: "Der Schritt, der aus deinem Knoten einen Teilnehmer macht. Danach kannst du zahlen, empfangen — und irgendwann für andere weiterleiten.",
    ko_warnung: "Das Geld ist danach GEBUNDEN. Nicht verloren, aber gebunden: es kommt erst wieder heraus, wenn der Kanal geschlossen wird, und das kostet ein zweites Mal Gebühren. Wähle eine Gegenstelle, die zuverlässig erreichbar ist — bei einer, die nicht mehr antwortet, wird das Schließen deutlich teurer.",
    ko_gegenstelle: "Mit welchem Knoten",
    ko_gegenstelle_d: "Die Kennung des Knotens, mit dem du den Kanal teilen willst — 66 Zeichen. Die Adresse dahinter („@host:9735“) darfst du mitschicken, musst du aber nicht: fehlt sie, holt dein Knoten sie aus seinem eigenen Graphen.",
    ko_knoepfe_d: "Dreierlei mit derselben Kennung. „Gegenstelle ansehen“ fragt nur deinen eigenen Graphen — niemand erfährt davon. „Verbinden“ baut eine bloße Leitung auf: kein Kanal, kein Satoshi. Für einen Kanal brauchst du es nicht, das erledigt „Kanal öffnen“ von selbst.",
    ko_betrag: "Kanalgröße (sat)",
    ko_betrag_d: "Wie viel du in den Kanal legst. Ein großer Kanal zu einer gut vernetzten, stabilen Gegenstelle nützt mehr als viele kleine.",
    ko_knapp: "Dieser Kanal ist knapp bemessen. Empfohlen werden mindestens {n} sat — und der Grund ist kein wirtschaftlicher: Steigen die Gebühren auf der Kette, kostet das Schließen irgendwann mehr, als im Kanal liegt. Wer dann nicht schließen KANN, kann auch einen Betrugsversuch der Gegenstelle nicht mehr bestrafen — und genau davon lebt die Sicherheit eines Kanals. Zum Zahlen und Empfangen reicht er trotzdem; du solltest es nur wissen.",
    ko_tempo_d: "Wie schnell die Öffnung bestätigt sein soll. Der Kanal wird erst nutzbar, wenn sie in einem Block steht.",
    ko_privat: "Privater Kanal",
    ko_privat_d: "Erscheint in keinem Graphen. Niemand routet dann durch ihn — und dein Knoten ist an dieser Stelle keine Verbindung, sondern eine Sackgasse. Nur wählen, wenn du das ausdrücklich willst.",
    ko_pruefen: "Nachrechnen",
    ko_oeffnen: "Kanal öffnen",
    ko_gebraucht: "Gebraucht wird",
    ko_guthaben: "Auf der Wallet",
    ko_reicht: "Das reicht. Nach dem Öffnen dauert es ein paar Bestätigungen, bis der Kanal nutzbar ist.",
    ko_fehlt: "Es fehlen {n} sat. Zahl erst On-Chain ein — unter „Wallet“ steht deine Einzahladresse.",
    ko_erst_pruefen: "Erst nachrechnen. Der Knopf geht auf, wenn das Guthaben reicht.",
    ko_laeuft: "Wird geöffnet — einen Moment.",
    ko_fertig: "Der Kanal wird geöffnet. Finanzierung: {txid}. Sobald sie bestätigt ist, taucht er in der Liste auf.",
    kanal_zu_klein: "Ein Kanal braucht mindestens {einzelheit} sat.",
    kanal_abgelehnt: "Dein Knoten hat das abgelehnt: {einzelheit}",
    rechnung_unlesbar: "Diese Rechnung ließ sich nicht lesen: {einzelheit}",
    zahlung_gescheitert: "Die Zahlung kam nicht durch: {einzelheit}",
    zahlung_unklar: "Keine Antwort innerhalb der Wartezeit. Die Zahlung kann trotzdem unterwegs sein — NICHT wiederholen, sondern gleich in den Kanälen nachsehen.",
    sendung_unklar: "Keine Antwort innerhalb der Wartezeit. Die Überweisung kann trotzdem unterwegs sein — NICHT noch einmal senden, sondern erst unter Bewegungen nachsehen, ob sie dort steht.",
    kanal_unklar: "Keine Antwort innerhalb der Wartezeit. Der Vorgang kann trotzdem laufen — NICHT wiederholen, sondern erst in der Kanalliste nachsehen.",
    betrag_fehlt: "Diese Rechnung nennt keinen Betrag. Trag einen ein.",
    sd_titel: "Senden",
    sd_lead: "On-Chain aus der Wallet deines Knotens heraus, an eine gewöhnliche Bitcoin-Adresse. Was in Kanälen liegt, geht so nicht — das kommt erst zurück auf die Kette, wenn ein Kanal schließt. Eine Lightning-Rechnung (lnbc…) gehört nicht hierher, sondern unter Zahlen.",
    wg_titel: "Was dein Knoten über Wege gelernt hat",
    wg_lead: "LND merkt sich je Gegenstellenpaar, bis zu welchem Betrag eine Weiterleitung getragen hat und ab welchem sie versagte — und wählt später danach aus. Liegt „versagte ab“ knapp über „trug bis“, ist der Weg nicht kaputt, sondern leer. Das ist eine Frage der Liquidität und behebbar.",
    wg_zahlen: "{paare} Paare im Gedächtnis · {fehl} mit Fehlschlag · {erfolg} mit Erfolg",
    wg_leer: "Noch nichts gelernt. Das füllt sich mit jeder Zahlung, die durch deinen Knoten läuft oder von ihm ausgeht.",
    wg_von: "von",
    wg_nach: "nach",
    wg_trug: "trug bis",
    wg_fehl: "versagte ab",
    wg_wann: "zuletzt",
    wg_nicht_abrufbar: "Dein Knoten gibt das Wegwissen gerade nicht heraus.",
    wegwissen_nicht_abrufbar: "Dein Knoten gibt das Wegwissen gerade nicht heraus.",
    nb_knopf: "Gebühr erhöhen",
    nb_laeuft: "Wird angehängt …",
    nb_erklaerung: "Diese Überweisung hängt noch. Erhöhen heißt hier: dein Knoten hängt eine zweite Transaktion an dein Wechselgeld, damit ein Miner beide nur zusammen nehmen kann. Die erste verschwindet nicht — und die zweite kostet zusätzlich.",
    nb_fertig: "Angehängt mit {satz} sat/vB. Höchstens {hoechstens} Sat Gebühr. Beide Transaktionen bestätigen sich gemeinsam.",
    nb_nicht_moeglich: "Diese Überweisung lässt sich nicht nachbessern: es ging alles raus, es liegt kein Wechselgeld dieses Knotens darin, an das sich etwas anhängen ließe.",
    nachbessern_abgelehnt: "Dein Knoten hat das Nachbessern abgelehnt: {einzelheit}",
    sd_warnung: "Eine gesendete Transaktion lässt sich nicht zurückholen. Prüfe die Adresse Zeichen für Zeichen — Anfang UND Ende. Bleibt die Antwort einmal aus, schick NICHT noch einmal: sieh erst unter Blöcke oder Mempool nach, ob sie schon unterwegs ist.",
    sd_adresse: "Empfängeradresse",
    sd_adresse_d: "Eine Bitcoin-Adresse. Am besten aus der Zwischenablage einfügen und danach beide Enden vergleichen.",
    sd_betrag: "Betrag in Satoshi",
    sd_betrag_d: "Mindestens 546 Satoshi. Darunter nimmt das Netz die Ausgabe nicht an — sie wäre weniger wert als ihr späteres Ausgeben kostet.",
    sd_alles: "Alles senden",
    sd_alles_d: "Räumt die On-Chain-Wallet leer; die Gebühr geht vom Betrag ab. Das Betragsfeld bleibt dann leer.",
    sd_tempo: "Wie eilig ist es?",
    sd_tempo_d: "Die Sätze kommen aus deinem eigenen Knoten, nicht von einem fremden Dienst.",
    sd_tempo_schnell: "Eilig",
    sd_tempo_schnell_d: "Zielt auf den nächsten Block.",
    sd_tempo_normal: "Normal",
    sd_tempo_normal_d: "Zielt auf die nächsten drei Blöcke — etwa eine halbe Stunde.",
    sd_tempo_guenstig: "Günstig",
    sd_tempo_guenstig_d: "Zielt auf die nächsten sechs Blöcke — etwa eine Stunde.",
    sd_pin_d: "Senden ist der Handgriff, den die PIN bewacht.",
    sd_schaetzen: "Was kostet das?",
    sd_senden: "Jetzt senden",
    sd_kosten: "Gebühr: {gebuehr} sat bei {satz} sat/vB. Prüfe die Adresse noch einmal, dann drück auf Senden.",
    sd_kosten_alles: "Bei {satz} sat/vB. Wie hoch die Gebühr ausfällt, weiß erst dein Knoten — bei „alles senden“ geht sie vom Betrag ab. Prüfe die Adresse noch einmal, dann drück auf Senden.",
    sd_erst_schaetzen: "Erst „Was kostet das?“ — das prüft auch gleich die Adresse.",
    sd_unterwegs: "Unterwegs. Das ist die Transaktionsnummer; unter Mempool und Blöcke kannst du ihr zusehen.",
    adresse_fehlt: "Ohne Empfängeradresse geht nichts hinaus.",
    betrag_zu_klein: "Mindestens {mindestens} Satoshi — darunter nimmt das Netz die Ausgabe nicht an.",
    alles_und_betrag: "Entweder ein Betrag oder „alles senden“. Beides zusammen wäre geraten, und geraten wird hier nicht.",
    tempo_unbekannt: "Dieses Tempo gibt es nicht.",
    keine_gebuehrenschaetzung: "Dein Knoten kann die Gebühr gerade nicht schätzen — dafür braucht er einen gefüllten Mempool. Direkt nach einem Neustart dauert das ein paar Minuten. Ohne Schätzung wird hier nichts gesendet: ein geratener Satz wäre entweder zu teuer oder die Zahlung bliebe tagelang liegen.",
    senden_abgelehnt: "Dein Knoten hat das abgelehnt: {einzelheit}",
    wallet_gesperrt: "Deine Wallet ist zu. Entsperre sie zuerst unter Einrichtung.",
    pin_existiert: "Es gibt schon eine PIN auf diesem Gerät. Ändern geht mit der alten.",
    pin_nur_ziffern: "Eine PIN besteht aus Ziffern.",
    pin_laenge: "Fünf bis zwölf Ziffern.",
    pin_zu_einfoermig: "Sechsmal dieselbe Ziffer ist keine PIN.",
    pin_ist_eine_reihe: "Eine Reihe wie 123456 steht bei jedem Angreifer an erster Stelle — vorwärts wie rückwärts.",
    pin_falsch: "Die PIN passt nicht.",
    wallet_nicht_gesperrt: "Dafür muss die Wallet zu sein — nur beim Entsperren kann LND prüfen, ob das Passwort stimmt. Sperre sie zuerst mit dem Knopf daneben.",
    entsperrweg_unbekannt: "Diesen Weg gibt es nicht.",
    entsperrdatei_fehlt: "Die Entsperrdatei ist nicht lesbar. Solange das so ist, kommt SatoshiCortex nicht an das Wallet-Passwort heran.",
    ew_titel: "Wie deine Wallet wieder aufgeht",
    ew_lead: "Hier lässt sich der Weg wechseln, ohne die Wallet neu anzulegen. Was jetzt gilt, steht unten.",
    ew_jetzt: "Zurzeit eingerichtet",
    ew_jetzt_aus: "Du tippst nach jedem Neustart das Wallet-Passwort.",
    ew_jetzt_merken: "SatoshiCortex merkt sich das Wallet-Passwort, solange es läuft.",
    ew_jetzt_datei: "Dein Knoten entsperrt sich selbst; das Wallet-Passwort liegt im Klartext neben der Wallet.",
    ew_noch_nicht_gemerkt: "Zurzeit ist nichts gemerkt — SatoshiCortex wurde seitdem neu gestartet. Beim nächsten Entsperren merkt es sich das Passwort wieder.",
    ew_wechseln: "Weg wechseln",
    ew_passwort: "Dein jetziges Wallet-Passwort",
    ew_passwort_d: "Nur für „von allein entsperren“ nötig: dabei geht dein Passwort im Klartext auf die Platte, und ein falsches würde LND beim nächsten Start hängen lassen. Geprüft wird es deshalb von LND selbst — dafür muss die Wallet einmal zu sein. Sperr sie mit dem Knopf darunter; danach kannst du sie hier gleich wieder aufmachen.",
    ew_gewechselt: "Umgestellt.",
    passwort_fehlt: "Ohne Passwort geht die Wallet nicht auf.",
    anmeldung_fehlgeschlagen: "Benutzername oder Passwort stimmt nicht.",
    zu_viele_versuche: "Zu viele Fehlversuche. Bitte in fünf Minuten erneut versuchen.",
    anmeldung_noetig: "Bitte zuerst anmelden.",
    sitzung_abgelaufen: "Die Sitzung ist abgelaufen. Bitte erneut anmelden.",
    unverschluesselt: "Diese Verbindung ist unverschlüsselt — dein Passwort geht im Klartext durchs Netz. Im eigenen Heimnetz ist das vertretbar; hängen dort fremde Geräte, richte in der .env ein Zertifikat ein.",
    ablage_nicht_bereit: "Der Ordner {pfad} ist nicht beschreibbar. Damit lässt sich kein Konto anlegen. Prüfe PUID und PGID in der .env — auf UGREEN- und Synology-Geräten gehört PGID=10 dorthin — und ob die beiden Datenordner dieser Kennung gehören.",
    einrichtung_abgeschlossen: "Die Einrichtung ist bereits abgeschlossen.",
    antwort_zu_gross: "Die Eingabe ist zu groß.",
    err_net: "Die Anwendung antwortet nicht. Läuft der Container noch?",
    err_anzeige: "Die Daten kamen an, aber die Anzeige ist daran gescheitert. Der genaue Fehler steht darunter — bitte melden.",
    nf_title: "Der Knoten antwortet nicht",
    nf_lead: "Die Oberfläche läuft, aber sie bekommt vom Dienst dahinter keine Antwort. Das passiert, während bitcoind gerade seinen Zwischenspeicher wegschreibt — dann dauert es ein paar Minuten. Bleibt es dabei, ist der Container gestoppt oder der Weg dorthin führt woanders hin.",
    nf_erneut: "Erneut versuchen",
    gb: "GB",
  },

  en: {
    e_name_haengt: "Careful: “{name}” has not resolved for {dauer}. The previously announced address therefore stays — after the next forced reconnect it belongs to somebody else, and your node advertises a stranger's. From outside the name usually resolves fine; look at the DNS inside your own network first (AdGuard, Pi-hole, router).",
    dauer_min: "{n} minutes",
    dauer_std: "{n} hours",
    dauer_tage: "{n} days",
    ez_titel: "Deposit",
    ez_lead: "Send bitcoin to your node at this address. It lands in LND's on-chain wallet — the same wallet that hangs on your twenty-four words. It is an ordinary Bitcoin address: if your exchange distinguishes Bitcoin from Lightning, choose Bitcoin. Freely available until you open a channel from it; then it is tied up in that channel until it closes again.",
    ez_holen: "Show address",
    ez_neue: "New address",
    ez_art_titel: "A different address format",
    ez_art_hinweis: "Some exchanges still cannot send to Taproot. If yours says \u201cinvalid address\u201d, pick SegWit \u2014 it is not your node's fault.",
    ez_art_taproot: "Taproot \u2014 starts with bc1p",
    ez_art_taproot_d: "The cheapest form. A channel funded from it costs less in fees.",
    ez_art_segwit: "SegWit \u2014 starts with bc1q",
    ez_art_segwit_d: "Slightly dearer, but virtually every exchange can send there.",
    ez_art_kompatibel: "Compatible \u2014 starts with 3",
    ez_art_kompatibel_d: "The dearest form, but even very old services cope with it.",
    ez_kopieren: "Copy",
    ez_kopiert: "Copied.",
    ez_oeffnen: "Open in wallet",
    ez_hinweis: "Your wallet does not have an address \u2014 it has any number of them, and they are all yours. It derives them from your twenty-four words; nothing changes on the sheet of paper, and old addresses stay valid forever. What you see here is the current unused one. It stays the same until someone pays to it \u2014 after that you get a fresh one automatically. That is deliberate: a reused address shows anyone reading the blockchain every payment made to it, and your balance.",
    kein_macaroon: "SatoshiCortex could not create its own permission. Is LND fully up yet?",
    gb_titel: "Fees",
    gb_lead: "What you charge for forwarding other people's payments. Well above what is usual and you are simply avoided — fees here are not a price tag but a steering signal. What counts as usual is not written in this text; your node measures it itself.",
    gb_netz_titel: "What the network charges",
    gb_messen: "Measure now",
    gb_messen_laeuft: "Reading the graph …",
    gb_netz_zahlen: "Median {median} ppm — half of all directions charge less · base fee {basis} msat · {linien} directions across {kanaele} channels · measured on {tag}",
    gb_netz_spanne: "The middle 50 % sit between {p25} and {p75} ppm.",
    gb_stufe_von_bis: "{von}–{bis}",
    gb_stufe_ab: "{von}+",
    gb_stufe_anteil: "{anteil} % {spanne} ppm",
    gb_netz_nie: "Not measured yet. Your node reads the entire network graph for this — it takes a while and happens once a day by itself.",
    gb_netz_eigen: "You currently charge {eigen} ppm.",
    gb_netz_eigen_keine: "What you currently charge is not in the graph yet — that needs at least one public channel.",
    gb_band: "Four weeks: {unten}–{oben} ppm, from {tage} days of measurement. The window moves along; today does not count towards its own band.",
    gb_band_sammelt: "The four-week band needs {braucht} days of measurement. So far: {tage}.",
    gb_uebernehmen: "Use the median",
    gb_uebernommen: "Filled into the field below — nothing is set until you press “Set fees”.",
    gb_automatik: "Track the network",
    gb_automatik_d: "Once a day, set the rate to the network median — bounded by the range of the last four weeks. Applies to all channels and never to the base fee.",
    gb_a_median: "Last set to {satz} ppm — that is the network median.",
    gb_a_gedeckelt: "Last set to {satz} ppm — the network median was higher, the four-week band capped it.",
    gb_a_angehoben: "Last set to {satz} ppm — the network median was lower, the four-week band raised it.",
    gb_a_unveraendert: "Nothing to do: {satz} ppm is already set.",
    gb_a_sammelt: "On, but not acting yet — days of measurement are still missing.",
    gb_a_keine_kanaele: "On, but not acting yet: without a channel there is nothing to set.",
    gb_a_keine_messung: "On, but not acting yet — the first measurement is missing.",
    gb_a_aus: "Off. The rate stays where you put it.",
    gb_a_wuerde: "Would set {satz} ppm now.",
    graph_nicht_aktuell: "The network map is not complete yet — measuring waits until it is.",
    graph_leer: "There is not a single channel in the network graph yet.",
    messung_fehlgeschlagen: "The measurement did not go through.",
    gb_kanal: "For which channel",
    gb_kanal_d: "This is where the real operating lever sits: make it expensive where a channel is draining, cheap where it should be refilled.",
    gb_alle: "All channels",
    gb_satz: "Rate (ppm)",
    gb_satz_d: "Millionths of the forwarded amount. 100 ppm means 100 sats on a million.",
    gb_basis: "Base fee (millisatoshi)",
    gb_basis_d: "Per forward, regardless of amount. Zero is common: route-finding penalises base fees more than the rate.",
    gb_setzen: "Set fees",
    gb_gesetzt_alle: "Set — for all channels. It takes a few minutes to spread through the network.",
    gb_gesetzt_einer: "Set — for this channel.",
    gebuehren_abgelehnt: "LND rejected that: {einzelheit}",
    lk_ich_titel: "Your node in the network",
    lk_alias: "Name",
    lk_kennung: "Public key",
    lk_adressen: "Announced at",
    lk_keine_adressen: "none — nobody can open a channel to you like this",
    lk_gegenstellen: "Connections",
    lk_gegenstellen_n: "{n} nodes",
    lk_kanaele_stand: "Channels",
    lk_kanaele_stand_n: "{aktiv} active · {still} idle · {offen} opening",
    lk_guthaben_titel: "Balance",
    lk_guthaben_d: "Two different things, so they are kept apart. What is on-chain you can spend at any time. What is in a channel is tied up until the channel closes — and what sits on the other side is not yours. It is, however, exactly what you can receive.",
    lk_onchain: "On-chain",
    lk_kanal_hier: "In channels, your side",
    lk_kanal_frei: "Of that, actually spendable",
    lk_kanal_drueben: "On the far side (= your inbound room)",
    lk_reserve: "{n} sat of that is channel reserve and cannot be spent. Every channel holds back one percent of its capacity on both sides — that is the stake that makes cheating expensive. On small channels it matters.",
    lk_kanaele_titel: "Channels",
    lk_kanaele_d: "The bar is the real statement: with everything on one side, the channel forwards nothing in one direction. Your share on the left, the peer's on the right.",
    lk_erreichbar: "{p} % reachable",
    lk_erreichbar_titel: "Share of the time your peer could reach you — since {seit}. LND keeps this per channel.",
    lk_erreichbar_gesamt: "Across all channels you were reachable {p} % of the time, weighted by lifetime. This is the number other operators judge you by — and the one you promise when you commit to a swap lasting months.",
    lk_keine_kanaele: "No channels yet — which means your node is not in the graph at all. The network only relays a node's name announcement once it knows an announced channel of that node (BOLT 7). Until then, directories see only your key: no name, no colour, no address. Your first public channel changes all of it at once.",
    lk_kanal_hier_kurz: "{n} here",
    lk_kanal_drueben_kurz: "{n} far side",
    lk_privat: "private",
    lk_still: "idle",
    lk_weiter_titel: "Forwarded",
    lk_weiter_d: "Not your own payments, but other people's that ran through your node. That is the moment it truly becomes part of the network.",
    lk_weiter_keine: "Nothing forwarded yet. That does not come on day one: LND picks routes by past successes, and your node is still a blank page there. What helps is uptime and liquidity on the right side.",
    lk_weiter_summe: "{n} forwards · {menge} sats moved · {gebuehr} sats earned",
    lg_titel: "The network",
    lg_lead: "How big the graph your node knows is — and how you look inside it.",
    lg_graph_laedt: "The graph is still loading. Your node knows only part of the network so far — these numbers will grow considerably over the next few hours.",
    lg_knoten: "Nodes in the graph",
    lg_kanaele: "Public channels",
    lg_kapazitaet: "Public capacity",
    lg_median: "Median channel size",
    lg_grad: "Channels per node (average)",
    lg_gegen_titel: "Your channel partners",
    lg_gegen_d: "Nodes you have a channel with. The number and quality of channel partners decide more about forwarding than the total amount in your channels.",
    lg_gegen_keine: "None yet. You only have channel partners once a channel exists — a connection alone does not make one.",
    lnsicht_folge_tor: "In this mode clearnet does not apply: your Bitcoin node speaks over Tor only (onlynet=onion), and so does Lightning. The IPv4 and IPv6 boxes stay as your preference and apply again once you switch back — right now they have no effect. Syncing becomes considerably slower.",
    lnsicht_folge_still: "Nothing is announced, so no address either — nobody reaches you from outside. Outgoing, you keep using the networks ticked below.",
    wsw_titel: "Wallet software on your home network",
    wsw_lead: "Your own wallet — including one with a hardware device — can use this node as its backend instead of asking someone else's server. Then your node checks your payments, and nobody else learns which addresses are yours.",
    wsw_schalter: "Allow wallet software from my home network",
    wsw_erklaerung: "Sparrow is the usual route: File → Preferences → Server → Bitcoin Core, then enter the details below. Your keys stay with Sparrow or on your hardware device — no wallet is created inside the node; Sparrow states this itself. Because txindex is on here, you also get the features that would otherwise need an Electrum server. What the release allows: querying the chain and submitting transactions. Nobody can move money with it, because there are no keys in the node.",
    wsw_netz: "Your home network",
    wsw_netz_d: "Access is accepted only from this network. Leave empty to use the network of this page. Public ranges are refused — this is not a release to the internet.",
    wsw_daten: "Enter this in your wallet software",
    wsw_feld: "Server:   {host}\nPort:     {port}\nUser:     {benutzer}\nPassword: {passwort}",
    wsw_hinweis: "The password is shown in the clear because there is nowhere else to get it. It grants access to your node's chain data, not to funds.",
    wsw_port: "For this to take effect the port must also be published: set RPC_BIND=0.0.0.0 in your .env and redeploy the stack. Without that the interface stays on the server itself and your home network cannot reach it — this release alone is not enough.",
    f_aus: "Off",
    wsw_netz_fehlt: "Enter your home network — it cannot be derived from this page's address. It looks like 192.168.178.0/24.",
    wsw_danach: "The credentials — user and password — are created together with the configuration. You will find them afterwards under Settings → Wallet software, with a copy button.",
    wsw_spaeter: "Off. You can turn this on later under Settings — it changes nothing about the chain and nothing about Lightning.",
    wsw_gespeichert: "Released. The node will restart shortly.",
    wsw_zu: "Access closed again. The node will restart shortly.",
    lnsicht_titel: "How visible your node is",
    lnsicht_lead: "Applies to both — Bitcoin and Lightning. The switches below are the detail within this choice. You are reachable and part of forwarding in the first two cases; anonymous does not mean limited.",
    lnsicht_waehlen: "Please pick one of the three — there is deliberately no default here. This choice decides whether your home connection can be looked up worldwide.",
    lnsicht_folge_hybrid: "Your IP address then sits in the Lightning graph and in the Bitcoin address lists — publicly searchable and tied to your node. This is the fastest and most reachable mode, and that is its price.",
    lnsicht_tor: "Tor only",
    lnsicht_tor_d: "Only your .onion address is announced, and outgoing traffic goes through Tor as well. A full member: reachable, in the graph, able to forward — but nobody knows where your node stands. Somewhat slower, and you need peers that speak Tor.",
    lnsicht_hybrid: "Tor and clearnet",
    lnsicht_hybrid_d: "Additionally the address from the field above — router forwarding on ports 8333 and 9735 (plus 9911 for the watchtower), via DynDNS if you like. Faster and better reachable. Your IP becomes public; LND warns about this explicitly.",
    lnsicht_still: "Announce nothing",
    lnsicht_still_d: "Neither .onion nor IP. You can open channels to others and pay through them — but nobody can open one to you, and forwarding is impossible. In the graph you are a dead end.",
    lgi_klartext: "Careful: one of these lines contains your public IP address — your home connection, permanently tied to your node and searchable by anyone in the Lightning graph. That is the “Tor and clearnet” mode, and you can change it. You cannot undo it: the address is already out there.",
    lgi_titel: "Your connection address",
    lgi_lead: "This is the line someone needs in order to open a channel to you: key, address, port. Share it wherever you like — it is public anyway, your node announces it on the network.",
    lgi_kopieren: "Copy",
    lgi_kopiert: "Copied.",
    unt_geprueft: "Checked: valid, made with your own node key.",
    unt_nicht_gueltig: "Checked: NOT valid. That should not happen — please report it.",
    unt_ungeprueft: "Created, but could not be checked right now.",
    kopieren_von_hand: "Selected — now press ⌘C or Ctrl+C.",
    lgi_keine_still: "Nothing here, and that is your choice: under Settings, visibility is set to \u201cAnnounce nothing\u201d. Your node announces neither .onion nor IP — you can open channels to others, but nobody can open one to you, and forwarding is impossible. To change it: Settings \u2192 Visibility.",
    lgi_keine_tor: "Nothing yet. Tor creates your .onion address, and the app then hands it to LND — after a restart usually within a minute, at the latest after ten minutes. If nothing appears after that, waiting is not the problem: the log under “Tor” shows whether Tor could create the onion services.",
    lgi_keine_hybrid: "Nothing yet. With \u201cTor and clearnet\u201d your node needs an address of its own to announce — enter it under Settings (via DynDNS if you like) and forward port 9735 on your router. The .onion address alone takes a minute or two after startup.",
    lgi_keine_beschaeftigt: "Your node is not answering the question about its addresses right now — it is busy with itself. After a restore it scans the whole chain for used addresses; that takes a while and is exactly what it should be doing. The address appears on its own once it is through.",
    lgi_kennung_anders: "This node has a DIFFERENT identity than the one that last ran here.\n\nBefore: {vorher}\nNow:    {jetzt}\n\nAfter a restore from your twenty-four words it should be the same one — if it is not, those words belong to a different wallet. After creating a NEW wallet a different identity is correct: it IS a different node. Then accept it here.",
    lgi_kennung_uebernehmen: "Yes, this is my node now",
    keine_kennung: "Your node is not saying who it is right now — wait until it answers.",
    lgi_veraltet: "As of a moment ago — your node is busy and not answering questions about its own state right now.",
    lgi_keine_unklar: "Your node does not announce an address yet. Without an announced address nobody knows how to reach you.",
    unt_titel: "Prove the node is yours",
    unt_lead: "LightningNetwork+ and similar places do not ask for a password: they have you sign a given text with your node key. That proves the node is yours. Paste the text the site shows you — the signature comes back and goes in there. This moves no money and reveals no key.",
    unt_knopf: "Sign",
    unt_leer: "There is no text yet.",
    unt_nicht_bereit: "Lightning is not running yet — without a wallet there is no key to sign with.",
    vb_knopf: "Connect",
    vb_verbunden: "Connected — the line now appears in the list below. It is not permanent: if it drops, LND will not rebuild it on its own without a channel.",
    vb_hinweis: "For someone to open a channel to YOU, by the way, you need do nothing at all — your node is reachable and accepts anything above the minimum size you set. What helps is a name people recognise.",
    lv_titel: "Your connections",
    lv_lead: "Lines to other nodes, right now. They cost nothing and tie up no money. LND keeps some of them on its own to keep its map of the network current — which is why nodes you never dealt with show up here too.",
    lv_summe: "Connections: {n} · with a channel: {k}",
    lv_mit_kanal: "with channel",
    lv_ohne_kanal: "no channel",
    lv_ein: "inbound",
    lv_aus: "outbound",
    lv_netzkarte: "syncs the network map",
    lv_keine: "No connection right now. Once LND is running it builds some on its own.",
    gegenstelle_abgelehnt: "The node did not accept this address: {grund}",
    lgw_titel: "Where to find channel partners",
    lgw_lead: "SatoshiCortex deliberately keeps no directory of its own: the Lightning graph already is one, and every node knows it. These places are not ours and have been established for years.",
    lgw_amboss: "Graph explorer and marketplace. Through “Magma” you can buy inbound liquidity — someone opens a channel to you and you pay a fee for it.",
    lgw_lnplus: "Brings operators together who open channels to each other — in rings, free of charge. Often the best start for small nodes, because nobody is selling capital.",
    lgw_1ml: "Directory and statistics. Useful to look at a possible peer beforehand: how many channels, how large, how long established.",
    lgw_fuss: "SatoshiCortex calls none of these — they are links you open yourself. Opening the channel then happens under “Channels” — behind the same PIN as sending.",
    sich_ohne_wallet: "No Lightning wallet yet — so there is nothing to back up. You can still enter the destination now: the node then backs up from the very first channel on, instead of whenever you remember.",
    kk_titel: "What a channel costs in fees",
    kk_lead: "Opening a channel and closing it again are two ordinary Bitcoin transactions — so you pay network fees twice. The estimate comes from your own node, not from some outside site.",
    kk_satz: "Fee level right now",
    kk_oeffnen: "Opening (estimated)",
    kk_schliessen: "Cooperative close (estimated)",
    kk_zusammen: "Together",
    kk_guenstig: "That is {p} % of your on-chain balance — a good moment.",
    kk_spuerbar: "That is {p} % of your on-chain balance. Noticeable but acceptable. If it is not urgent, waiting pays.",
    kk_teuer: "That is {p} % of your on-chain balance. Opening a channel now would be expensive — fees swing a lot, better wait.",
    kk_lage_guenstig: "{satz} sat/vB — that is cheap. Over the last {tage} days most blocks sat between {unten} and {oben} sat/vB, with {mitte} in the middle. Measured against your own chain, not against some outside site.",
    kk_lage_normal: "{satz} sat/vB — that is normal. Over the last {tage} days most blocks sat between {unten} and {oben} sat/vB, with {mitte} in the middle.",
    kk_lage_teuer: "{satz} sat/vB — that is expensive. Over the last {tage} days most blocks sat between {unten} and {oben} sat/vB, with {mitte} in the middle. If it is not urgent, better wait.",
    kkp_titel: "What you have to deposit for a channel",
    kkp_lead: "The channel size is not the amount that has to sit in your wallet. Enter how large the channel should be — your own node works out the rest.",
    kkp_ohne: "The fee estimate is still missing. Your node only provides it once the chain is there — before that, any number here would be a guess.",
    kkp_groesse: "Channel size (sat)",
    kkp_kanal: "Channel size",
    kkp_oeffnen: "Opening fee (estimated)",
    kkp_ruecklage: "Anchor reserve (from LND)",
    kkp_einzahlen: "Deposit on-chain",
    kkp_nutzbar: "Usable in the channel",
    kkp_fuss: "The anchor reserve stays in your on-chain wallet — it is not gone, but it is tied up: LND needs it so it can top up a force close if it comes to that. The closing fee, by contrast, does NOT have to be deposited beforehand; on a cooperative close it is taken from the channel balance. And about one percent of the channel size stays put as the channel reserve for as long as the channel is open.",
    kk_erzwungen: "Careful: this is for a cooperative close, where both sides take part. If the peer does not answer, the channel is force-closed — then the commitment transaction is followed by further transactions to sweep your own funds, and it gets substantially more expensive. The best protection is a reliable peer.",
    sich_titel: "Channel backup",
    sich_lead: "Your twenty-four words restore the on-chain wallet — not the funds IN your channels. A channel is a shared output with a peer; to settle it without their help you need its state. That state is what this file holds. Disk gone, backup gone, channel funds gone — even with the sheet of paper in your hand.",
    sich_ohne_kanaele: "No channels yet — so nothing to back up. The file comes into being with your first channel, and from then on it counts.",
    sich_aktuell: "Up to date: {kanaele} channels, last stored on {wann}.",
    sich_rueckstand: "Behind: your node has {kanaele} channels, but what was stored is an older state. Every channel added since is a channel without a backup.",
    sich_nie: "Never backed up. {kanaele} channels are open — a disk loss would take the funds in them.",
    sich_fehler_zuletzt: "The last attempt failed: {fehler}",
    sich_ziel_ist: "Target: {url} (as {benutzer})",
    sich_laden: "Download",
    sich_geladen: "Downloaded. Put it anywhere, just not on this NAS.",
    sich_ziel_titel: "Store automatically (WebDAV)",
    sich_ziel_d: "Nextcloud, a hoster, any WebDAV folder. Set it up once and SatoshiCortex pushes the file there by itself on every channel change. That is safe: the backup is encrypted with a key derived from your seed — whoever has it without your twenty-four words has nothing.",
    sich_url: "Folder address",
    sich_url_d: "The folder, not the file. On Nextcloud something like https://cloud.example/remote.php/dav/files/YOURNAME/Backups",
    sich_benutzer: "Username",
    sich_passwort: "Password",
    sich_passwort_d: "Use an app password, not your account password. SatoshiCortex has to store it to be able to upload on its own — an app password can be revoked on its own and does not reach the rest of your account.",
    sich_einrichten: "Set up and store now",
    sich_entfernen: "Remove target",
    sich_eingerichtet: "Set up — and the first backup arrived.",
    sich_entfernt: "Target removed. Nothing will be stored automatically any more.",
    ziel_nimmt_nichts_an: "The target did not accept the backup: {einzelheit}",
    ziel_anmeldung_abgelehnt: "The destination rejected the login (401): user name or password is wrong. On Nextcloud with two-factor authentication your normal password does not work here — you need an app password (Personal settings → Security).",
    ziel_verweigert: "The destination refuses access (403). Unlike a 401 this is usually not the password: either this account may not write to that folder — for example a read-only share —, or a protection in front of it, such as a reverse proxy, turns the request away.",
    ziel_adresse_unbekannt: "The server knows no WebDAV folder at this address (404). That is usually the address, not the password. On Nextcloud it looks like https://cloud.example/remote.php/dav/files/YOURNAME/Backups — with your user name in place of YOURNAME. Quick check: open the address in a browser; if that shows 404 as well, it is not right yet.",
    ziel_ordner_fehlt: "The server is the right one, but the folder does not exist there yet (409). WebDAV does not create folders on upload — create it once by hand, for example in the Nextcloud web interface, then try again.",
    keine_kanaele: "No channels yet — there is nothing to back up.",
    lightning_nicht_bereit: "Lightning is not running yet.",
    adressart_unbekannt: "The node does not know that address format.",
    sicherung_unbrauchbar: "The backup could not be verified. Better no file than one you rely on — please report this.",
    wl_weg_titel: "How does your wallet open again after a restart?",
    wl_weg_lead: "Three ways, and none is right for everyone. Read the consequence below — it is there because more than one answer is defensible.",
    wl_weg_aus: "I type the wallet password — every time",
    wl_weg_aus_d: "Nothing sits on the disk, nothing stays in memory. After every restart your node waits for you.",
    wl_weg_merken: "Remember it while running",
    wl_weg_merken_d: "Nothing sits on the disk. SatoshiCortex keeps your password for as long as it runs — when it restarts Lightning itself, it opens the wallet again.",
    wl_weg_datei: "Unlock by itself",
    wl_weg_datei_d: "The wallet password sits in plain text next to the wallet. Your node keeps running after a power cut.",
    wl_weg_folge_aus: "Your wallet password is nowhere on the disk. Someone who takes the NAS apart or copies a backup cannot reach the on-chain funds. The price: after every restart your node stands still until you enter the password here — including the restarts SatoshiCortex triggers itself, for instance when you change the name or the visibility. In the Lightning network that very uptime is what your reputation is built on.",
    wl_weg_folge_merken: "As little sits on the disk as above — against a stolen NAS or a copied backup the two are equivalent. The difference only concerns the restarts SatoshiCortex triggers itself: name changed, visibility changed, address resolved anew. Those it reopens on its own instead of asking you. If the power fails, SatoshiCortex falls with it — and you type again. Named honestly: whoever takes over the running application finds the password in memory. They also find the credential that drives Lightning there anyway.",
    wl_weg_folge_datei: "Your node keeps running after every power cut — the best uptime there is. The price: whoever gets hold of the disk has both, wallet and password. And once this application is allowed to send money, they have that too. Against a break-in on the running NAS it does not help anyway.",
    wl_platte_titel: "What actually sits on the disk?",
    wl_platte_d: "Your twenty-four words: NOWHERE. They pass through SatoshiCortex to Lightning and are never written — a check searches every file the application touches for them on every build. Your wallet password: only in the third way, and there in plain text. What does always sit there is the credential SatoshiCortex drives Lightning with — Lightning writes it itself, not us. Since that credential may also send, the PIN stands in front of it.",
    wl_entsperren_passwort: "Wallet password",
    wl_entsperren_passwort_d: "The password you created the wallet with.",
    wl_entsperren_gemerkt: "Afterwards SatoshiCortex remembers it for as long as it runs — you will only be asked again once the NAS restarts.",
    wl_passwort_titel: "Wallet password",
    wl_passwort_d: "At least ten characters. You need it after every restart — memorise it, or keep it where the twenty-four words are. Lose it and only the seed helps.",
    wl_gesperrt_titel: "The wallet is locked",
    wl_gesperrt_d: "Your node is running, but the wallet is shut. While it is, it forwards nothing and accepts no payments. Enter your wallet password.",
    wl_entsperren: "Unlock",
    wl_entsperrt: "Unlocked. The node is coming up now.",
    passwort_zu_kurz: "That password is too short — at least {mindestens} characters.",
    passwort_falsch: "That password does not match.",
    wl_schritt1: "Step 1 of 3",
    wl_schritt2: "Step 2 of 3",
    wl_schritt3: "Step 3 of 3 — this is the point of no return",
    wl_noch_nichts: "Nothing is created yet. You are about to see twenty-four words and will then be asked whether you have them. The wallet is only really created in step three.",
    wl_eine_einzige: "A Lightning node has exactly one wallet — it is its identity. Your words become the key this node appears under on the network. There is therefore no second one and no wallet name; what your node is called on the network is set under Settings.",
    wl_holen_titel: "Or: you already have one",
    tg_titel: "Delete the wallet",
    tg_lead: "For trying out the setup, or if you really want to rebuild this node from scratch.",
    tg_warnung: "Gone afterwards: your wallet, the channel database, all macaroons, the TLS certificate and your onion service key. Your node gets a NEW onion address — the old one will never reach you again.",
    tg_seed: "Your twenty-four words restore the on-chain wallet. They do NOT restore the funds in open channels — only the channel backup does. With open channels and no backup, that money is gone after deleting.",
    tg_erst_sperren: "To delete, your wallet has to be locked — only then can LND check your password at all. The button restarts LND once; it takes about a minute.",
    tg_sperren_knopf: "Lock the wallet",
    tg_sperren_laeuft: "Restarting LND — the wallet will be locked shortly … (up to {rest} s to go)",
    tg_ist_gesperrt: "Shut. Now you can go on.",
    tg_sperren_haengt: "LND has not come back locked after two and a half minutes. Look under Logs to see what the service says — you can press the button again afterwards.",
    tg_passwort_d: "Your wallet password. LND checks it itself — nothing here is compared against anything we stored.",
    tg_alias: "To be sure: your node's name",
    tg_alias_d: "Type “{alias}”.",
    tg_loeschen_knopf: "Delete for good",
    tg_laeuft: "Deleting. LND is shutting down, the directory is emptied, then it comes back up empty.",
    wallet_erst_sperren: "The wallet has to be locked for that.",
    wallet_arbeit_laeuft: "A restart is already running. Wait for it to finish.",
    auto_entsperren_an: "With automatic unlocking on, LND unlocks itself at startup — a restart would achieve nothing. Turn it off first.",
    alias_stimmt_nicht: "That name is not right. Expected “{erwartet}”.",
    wl_titel: "Create the Lightning wallet",
    wl_lead: "Once, and never again. SatoshiCortex has LND roll twenty-four words — from them your wallet can be restored completely, even if this NAS goes up in flames tomorrow.",
    wl_papier: "The words belong on paper. Not in a password manager, not in a notes app, not in a photo. Anything on a disk sits on the same disk as the wallet — and then protects against nothing. SatoshiCortex stores them nowhere: close this window without writing them down and they are gone.",
    wl_erzeugen: "Generate words",
    wl_woerter_titel: "Your twenty-four words",
    wl_woerter_d: "Write them down in this order, then read them back against the screen. The order matters as much as the words.",
    wl_woerter_warnung: "You see these words exactly once. The moment you move on they are gone — and nobody, myself included, can give them back to you.",
    wl_bestaetigen: "I have written all twenty-four words down on paper",
    wl_bestaetigen_d: "I am about to ask you for four of them. No correct answer, no wallet — that is not red tape, it is the only way to know you really have them.",
    wl_weiter: "On to the check",
    wl_probe_titel: "Check",
    wl_probe_d: "Four positions from your sheet. Capitalisation does not matter.",
    wl_wort_nr: "Word {nr}",
    wl_anlegen: "Create wallet",
    wl_fertig_titel: "The wallet is up",
    wl_fertig_auto: "Created and unlocked. From now on your node unlocks it by itself on every start — the wallet password lies on disk for that.",
    wl_fertig_hand: "Created and unlocked. After every restart of the node you have to unlock it here by hand: the password is nowhere on disk, so nobody — not even SatoshiCortex — can enter it without you. Until then Lightning rests.",
    wl_fertig_merken: "Created and unlocked. SatoshiCortex remembers your password for as long as it runs: when it restarts Lightning itself, it opens the wallet again. After a power cut it asks you once more — so your paper slip stays the way back.",
    wallet_gibt_es_schon: "A wallet already exists. Offering a second seed for it would be the most dangerous confusion this interface could cause.",
    lnd_antwortet_nicht: "Lightning is not answering right now. Is the service running yet?",
    seed_abgelaufen: "Those words are no longer valid. Start over — you will get new ones.",
    gegenprobe_falsch: "At least one of the four WORDS asked for is wrong — this is not about your password. Go through the numbers on your sheet again; the commonest mistake is being one line off. {versuche_uebrig} attempts left, then you get new words and your sheet becomes waste paper.",
    gegenprobe_aufgegeben: "That was the last attempt. We start over — with new words, so the old ones are not left half known.",

    wl_oder: "Have you run this node before?",
    wl_holen: "Restore a backed-up node",
    wh_titel: "Restore a backed-up node",
    wh_lead: "You have the twenty-four words and, at best, the channel backup. From those LND rebuilds your wallet and scans the chain for everything that belongs to you. It is the same call that creates a wallet — with two more fields.",
    wh_warnung: "This only works while no wallet exists here yet. If one is already running, this is the wrong place — a second wallet beside an existing one does more damage than any data loss.",
    wh_woerter_titel: "Your twenty-four words",
    wh_woerter_d: "In the order on your sheet. Capitalisation does not matter. You can also paste all twenty-four into the first field at once — they spread themselves out.",
    wh_wort_unbekannt: "These words are not in the word list a seed is made of — there are exactly 2048, and yours is none of them: {liste}. That is a typing slip, not a wrong sheet: go through the field letter by letter.",
    wh_wort_vielleicht: "No. {nr} “{wort}” — did you mean “{nahe}”?",
    wh_wort_nur: "No. {nr} “{wort}”",
    wh_erst_woerter: "Correct the marked words first — LND will not even accept the seed like this.",
    wh_pass_titel: "Seed passphrase (only if you set one)",
    wh_pass_d: "SatoshiCortex never sets one itself. This field exists for seeds created elsewhere — with `lncli create`, say. When in doubt, leave it empty.",
    wh_sich_titel: "Channel backup",
    wh_sich_d: "The words bring back your on-chain funds. They do not bring back the funds IN your channels — that needs this file. Without it exactly that part is missing; everything else still comes back.",
    wh_q_keine: "None — restore the chain side only",
    wh_q_datei: "Choose a file (channel.backup)",
    wh_q_ziel: "Fetch from the configured backup destination",
    wh_datei_gewaehlt: "{name} — {bytes} bytes read.",
    wh_datei_zu_gross: "This file is too large for a channel backup. It is not the right one.",
    wh_ungeprueft: "This file CANNOT be checked here: it is encrypted with a key derived from your seed, and only the finished wallet knows that key. If it is the wrong file, LND will fail to start afterwards — then you start over without it. It can only be checked while a node is running: that is what “Check a copy” under “Backup” is for.",
    wh_was_titel: "What comes back — and what does not",
    wh_was_d: "Your on-chain funds come back in full. The settled balances from your channels come back too: LND forces the channel partners to close and pulls the money onto the chain. The channels themselves are shut afterwards — what is restored is the money, not the operation. What does NOT come back are amounts that were still in flight at the moment of loss.",
    wh_dauer: "LND then scans the chain {fenster} addresses deep. That takes time and needs a complete chain — before that it finds nothing. Forcing the channels closed additionally needs the usual timelocks: hours to days, depending on the peer.",
    wh_starten: "Restore",
    wh_abbrechen: "Back",
    wh_fertig_titel: "Restored",
    wh_fertig_d: "The wallet is created and LND is scanning the chain. It may take a while before amounts show up — look again later.",
    wh_fertig_kanaele: "The channel backup was passed along. LND is now contacting the channel partners; the money appears on-chain once the timelocks have run out.",
    seed_unvollstaendig: "That is {gezaehlt} words, {erwartet} are needed. Count again — a word typed twice shows up here too.",
    seed_nicht_angenommen: "LND did not accept this seed. Its own words: {einzelheit} — If it mentions a checksum, it really is the words: go through the sheet one by one and mind the order. If it mentions a passphrase, it is NOT your sheet — open “Seed passphrase” above and clear that field.",
    sicherung_unlesbar: "This file could not even be read in. It is not a channel backup.",
    sicherung_zu_klein: "This file is only {bytes} bytes — the smallest possible channel backup is 45. The download probably broke off, or it is the wrong file.",
    kein_ziel: "No backup destination is set up — nothing can come from there.",
    kein_passwort: "The password for the configured destination is missing. Enter it below once more.",
    ziel_gibt_nichts_her: "Nothing came back from the backup destination: {einzelheit}",
    ziel_keine_sicherung_dort: "There is no channel backup there (404). Either none was ever stored at this destination, or the address points to a different folder than when it was set up.",

    sipr_titel: "Check a copy",
    sipr_d: "That your node can produce an intact backup says nothing about the copy on your stick. Put it in here: LND really unlocks it and tells you which channels are in it. That proves two things — it is intact, and it belongs to this node. The one day you can no longer find that out is the day you need it.",
    sipr_datei: "Choose a file",
    sipr_pruefen: "Check the file provided",
    sipr_ziel: "Check the one stored at the destination",
    sipr_laeuft: "Checking …",
    sipr_ok: "Intact, and it belongs to this node: {abgedeckt} channels are in it — exactly the {offen} that are open.",
    sipr_luecke: "Intact, and it belongs to this node. But it covers only {abgedeckt} of {offen} open channels: it is older than your youngest channel. Fetch a fresh one.",
    sipr_ohne_vergleich: "Intact, and it belongs to this node: {abgedeckt} channels are in it.",
    pr_titel: "Reachable from outside?",
    pr_d: "Checked over Tor — the connection leaves your house, travels over three foreign machines and comes back from outside. That is the same path a real peer takes. From inside it could not be honest: IPv6 has no NAT, so a connection from your own network would arrive even with the router firewall closed. The measurement takes up to half a minute per address.",
    pr_knopf: "Check now",
    pr_laeuft: "Checking — over Tor this takes a moment …",
    pr_ja: "{adresse} — reachable. {kennung} answered.",
    pr_ja_offen: "{adresse} — reachable. The connection came through Tor all the way to your node.",
    pr_abgelehnt_onion: "{adresse} — refused. Tor found your onion service, but nothing behind it accepted on port {port}. This is not your router — over Tor no forward is needed. Usually the service behind it is not running right now; otherwise the log under “Tor” shows where Tor forwards to.",
    pr_dienst_lightning: "Lightning",
    pr_dienst_wachturm: "Watchtower",
    pr_abgelehnt: "{adresse} — refused. Your router answered, but port {port} does not point here. That is a missing port forward.",
    pr_kein_knoten: "{adresse} — port {port} is open, but nothing behind it speaks Bitcoin. The forward probably points at the wrong machine.",
    pr_kein_handschlag: "{adresse} — port {port} is open: the connection from outside came up, so your router forward works. The Bitcoin handshake broke off afterwards — something answers behind it, but not cleanly.",
    pr_keine_antwort: "{adresse} — port {port} is open: the connection from outside came up, so your router forward works. No answer arrived in time, that is all. Over Tor that is usually the path rather than your node — and during the initial sync your node is busy on top of that.",
    pr_unklar: "{adresse} — not measurable: {grund}. That says nothing about your node; the path over Tor did not come together. Try again later.",
    pr_unklar_onion: "{adresse} — not measurable: {grund}. That says nothing about your node. For a .onion, Tor first looks up your hidden service's directory. Several checks in quick succession ask every responsible directory in turn, and after that it stops working for some minutes — exactly the “No more HSDir available to query” line in the Tor log. So do not retry right away: wait a few minutes.",
    pr_keine_adresse: "Your node announces no address — nobody outside can find it. Enter a name above and turn on “Announce your own address”.",
    pr_tor_aus: "Without Tor this cannot be measured honestly. A connection from your own network would arrive even with the router closed — the answer would always be “reachable” and never worth anything.",
    pr_nicht_aufloesbar: "The name you entered could not be resolved just now. Without an address there is nothing to check.",
    pr_tor_pausiert: "Tor was not checked — there was nothing to measure. During the initial sync the Tor exit is paused, and Bitcoin Core then does not announce the .onion address at all. Your onion service keeps running and still accepts incoming connections; new peers just do not learn the address right now. Once the chain is up to date it comes back on its own — the same one as before. If you would rather not wait, turn off “Pause Tor until the chain has loaded” above.",
    pr_keine_onion: "Tor is on, but your node announces no .onion address — that is why nothing about it appears here. Tor creates the address at startup, and the app then hands it to bitcoind. Usually this means Tor or bitcoind has only just restarted. If nothing appears after ten minutes, the log under “Tor” shows whether Tor could create the onion services.",
    pr_fehler: "The check did not complete.",
    kn_titel: "Your node's name",
    kn_lead: "This is what your node is called in the Lightning graph — on amboss.space, on 1ml and in every peer's channel list. A name people recognise is what makes someone open a channel to you.",
    kn_gespeichert_neustart: "Saved. LND is restarting now and announcing the name to the network.",
    kn_alias: "Alias",
    kn_alias_d: "At most 32 bytes — accented letters and emoji count for several. Without your own choice your node is called “SatoshiCortex”, like every other one running this software. The name only becomes visible to others with your first public channel: the network only relays a node's name announcement once it already knows an announced channel of that node (BOLT 7). Until then, directories such as Amboss or LightningNetwork+ show your key instead of your name — with nothing set up wrongly on your side.",
    kn_farbe: "Colour",
    kn_farbe_d: "The dot of colour beside your name in graph views. Pure decoration, but it makes you findable in a list.",
    minchansize_ungueltig: "The smallest incoming channel must be between {min} and {max} satoshis.",
    kn_minchan: "Smallest incoming channel (satoshis)",
    kn_minchan_d: "The least others must open to you. Anything smaller your node rejects automatically, and you never see it. If you take part in a liquidity ring, set this BELOW the ring size: sitting exactly on it means the channel you earned fails over a single satoshi. LND's own floor is 20,000.",
    kn_neustart: "Saving restarts LND once, which announces the new name to the network via node_announcement. If automatic unlocking is OFF, your wallet is locked afterwards until you enter the password — and your node forwards nothing until then.",
    name_ungueltig: "That name will not do. At most 32 bytes, one line, no control characters — and the colour as #rrggbb.",
    wege_titel: "Ways into the network",
    wege_intro: "Four ways, and they are independent of each other. None of them switches another off — quite the opposite: nodes that speak Tor and clearnet at once are scarce. The only limit is not between the switches: with no network at all, nothing works.",
    wege_tor: "Tor (.onion)",
    wege_tor_d: "What this does on your machine: a Tor service runs alongside, connects to the Tor network and creates a .onion address for your node. It relays NO third-party traffic — your machine does not become a relay. On first start it downloads the network directory once, after that it is very frugal. The benefit: Tor-only nodes need peers that speak both worlds, and that bridge is scarce.",
    wege_pause: "Pause Tor until the chain has loaded",
    wege_pause_d: "Tor is many times slower than an ordinary connection, and while the chain is loading only throughput counts. Your node then calls nobody over Tor on its own — and during that time it does not announce its .onion address either. The onion service keeps running and still accepts incoming connections, but new peers never learn the address. Bearable while the chain loads: your node has nothing to serve anyway. The address is not lost — once the chain is current the pause ends and the same .onion is announced again.",
    wege_ipv4: "IPv4",
    wege_ipv4_d: "The ordinary way. For others to reach you, port 8333 has to point at this machine in your router.",
    wege_ipv6: "IPv6",
    wege_ipv6_d: "Switchable on its own, because not every line has IPv6 — and because an announced way nobody can take is worse than none at all. Port 8333 needs forwarding here too.",
    wege_adresse: "Announce your own address",
    wege_adresse_d: "Inside the container your node only sees its internal Docker address. Without an entry it tries to learn its public one from its peers — which often works, but not always. Enter it and the node announces it right away. A DynDNS name beats a fixed IP here, because it survives a change. Separate multiple entries with commas.",
    wege_ruft_an: "Right now your node dials out over: {liste}.",
    wege_pause_laeuft: "In effect right now: your node calls nobody over Tor, and does not announce its .onion address meanwhile.",
    wege_pause_fertig: "The chain is current — there is nothing left to pause here.",
    wege_pause_wartet: "On. It takes effect as soon as peers exist on both paths — otherwise your node might end up with none at all.",
    wege_pause_aus: "Off: your node dials out over Tor during the sync as well. That costs noticeable speed — Tor is many times slower, and every Tor slot is one less for a fast connection.",
    wege_pausiert: "Tor is on, but paused during the initial sync — that is why onion is missing from this list, and your .onion address is not announced meanwhile.",
    kein_weg_ins_netz: "At least one way has to stay. Otherwise your node could neither reach out nor be reached.",
    back: "Back", next: "Continue", start: "Start setup",

    w_klick: "Click a country to see which states, cantons or provinces your peers sit in.",
    w_klapp_zu: "Hide numbers",
    w_klapp_auf: "Show numbers",
    wl_zurueck: "← World map",
    wl_uebersicht: "Regions in this country",
    wl_gebiet: "Region",
    wl_btc: "Bitcoin",
    wl_ln: "Lightning",
    wl_buch: "known",
    wl_laedt: "Loading …",
    wl_fehler: "The breakdown is not available right now.",
    wl_keine: "Your node knows nobody in this country — at least nobody whose region can be determined.",
    wl_unmoeglich: "This image carries no region names. The world map is unaffected.",
    wl_ohne_umriss: "No region outlines are available for this country — the numbers beside it still hold.",
    wl_stand: "Location list from {stand}",
    wl_rest: "Plus {btc} peers, {ln} Lightning nodes and {buch} addresses in this country whose region is unknown.",
    wl_genauigkeit: "The region comes from the free DB-IP list and can be wrong — a data centre rarely sits where its operator does. Deliberately no finer than the state.",
    st_willkommen: "Welcome", st_speicher: "Storage", st_leistung: "Performance",
    st_netz: "Network", st_wallet: "Wallet", st_konto: "Account", st_fertig: "Ready",

    w_title: "Your own Bitcoin node",
    w_lead: "Set up in a few minutes. After that it runs on its own.",
    w_p1: "SatoshiCortex turns this machine into a full participant in the Bitcoin and Lightning networks — not a spectator. Your node verifies every transaction itself, serves the block chain to others, and shows you things no public service can.",
    w_need_disk: "<b>About 1 TB of disk space</b>, growing by roughly 85 GB a year.",
    w_need_ports: "<b>Two forwarded ports</b> on your router. We'll check them together.",
    w_need_time: "<b>Days to weeks</b> for the initial sync. It runs in the background.",
    w_need_band: "<b>Upload bandwidth.</b> How much is up to you.",
    w_note: "You don't have to configure any of this by hand. The next steps check, explain and handle it.",

    s_title: "Storage",
    s_lead: "Let's look at what's available.",
    s_checking: "Checking …",
    s_bulk: "Large storage", s_fast: "Fast storage",
    s_free: "free", s_needed: "recommended",

    l_title: "Performance",
    l_lead: "How much may SatoshiCortex take? A NAS usually runs other services too — those shouldn't grind to a halt.",
    l_sparsam: "Frugal", l_sparsam_d: "For machines with little headroom or many other services. The initial sync takes longer but completes reliably.",
    l_mittel: "Balanced", l_mittel_d: "Recommended. Noticeably brisk, while leaving enough for everything else.",
    l_voll: "Full power", l_voll_d: "The machine belongs to the node. Fastest initial sync.",
    l_upload: "Upload per month",
    l_unlimited: "unlimited",
    l_cache: "Cache: {a} MB during the initial sync, {b} MB afterwards",

    n_title: "Network and participation",
    n_lead: "For your node to contribute rather than just listen, it needs two open doors.",
    n_p_btc: "Bitcoin — so other nodes can reach you",
    n_p_ln: "Lightning — so payments can route through you",
    n_p_wt: "Watchtower — clearnet only; with Tor it gets its own .onion",
    e_speichern: "Apply changes",
    e_nicht_geladen: "Your settings could not be loaded — what you see here are defaults. Saving is therefore blocked: it would overwrite your real settings. Reload the page in a moment.",
    mehr_dazu: "What this means",
    e_ungespeichert: "Not applied yet. The switches above only take effect once you click here — your node then restarts once.",
    b_lead: "What the sent data went into, across currently connected peers. Only “blocks” is contribution.",
    b_keine_gegenstellen: "Right now the node reports no connected peers, so the breakdown is empty. This is a snapshot: the breakdown only counts what went to the peers connected right NOW, not everything sent since start.",
    b_summe: "Basis of this breakdown: {menge}, sent to the {n} peers connected right now. Not the same as “Served since start” above — that counts the whole uptime and every peer connected since.",
    b_bloecke: "Blocks served",
    b_transaktionen: "Transactions relayed",
    b_filter: "Filters for light wallets",
    b_kopfzeilen: "Headers",
    b_adressen: "Addresses passed on",
    b_rest: "Handshake, ping, requests",
    b_budget_erschoepft: "Your upload budget for the running 24 hours is used up. Until that window ends your node serves NO historical blocks — newcomers cannot sync from you right now. New blocks and transactions are still relayed normally. The window runs for another {rest}.",
    b_noch_nichts: "Nobody has fetched blocks yet. That needs inbound connections.",
    b_noch_nichts_sync: "Nobody has fetched blocks yet. Normal during the sync: your node is too busy to answer.",
    nav_uebersicht: "Overview",
    nav_netz: "Network",
    nav_mempool: "Mempool",
    nav_bloecke: "Blocks",
    nav_kanaele: "Channels",
    nav_knoten: "Nodes",
    tun_wallet_anlegen: "The chain is complete and LND is running. Next comes the Lightning wallet — seed on paper, with a verification step. Until then this node holds no key and no satoshi.",
    tun_wallet_anlegen_knopf: "Go to the wallet",
    tun_wallet_entsperren: "Your wallet is locked. While it is, your node forwards nothing and accepts no payments — it is running, but standing still.",
    tun_wallet_entsperren_knopf: "Unlock now",
    tun_sicherungsziel: "No backup destination set yet. Your twenty-four words restore the on-chain wallet, but NOT the funds in your channels — that needs the channel backup. Set the destination before the first channel exists.",
    tun_sicherungsziel_knopf: "Set up the backup",
    nav_wallet: "Wallet",
    nav_einrichtung: "Setup",
    nav_abschnitte: "Sections",
    lang_wahl: "Language",
    lk_leer: "Lightning is not running yet — that is why nothing is here. What is missing is shown at the top of the “Wallet” tab.",
    nav_einstellungen: "Settings",
    nav_karte: "Map",
    nav_welt: "World",
    nav_werkzeug: "Tools",
    nav_rechner: "Converter",

    rn_titel: "Sats, bitcoin and money",
    rn_lead: "One bitcoin is a hundred million satoshi — and Lightning counts in sats, not in decimal places of bitcoin. Type into one field, the other two follow.",
    rn_waehrung: "Currency",
    rn_sat: "Satoshi",
    rn_sat_d: "The smallest unit. Whole numbers, no decimals.",
    rn_btc: "Bitcoin",
    rn_btc_d: "Eight decimal places — the last one is a satoshi.",
    rn_fiat: "{w}",
    rn_fiat_d: "At the rate below. It moves; your sats do not.",
    rn_je_btc: "for one bitcoin",
    rn_je_fiat: "for {zeichen} 1.00",
    rn_unlesbar: "I cannot read that as a number. Digits, one decimal point and thousands separators.",
    rn_zu_gross: "More bitcoin than there will ever be — the cap is 21 million.",
    w_btc: "Bitcoin",
    w_ln: "Lightning",
    w_legende: "What the lines mean",
    w_legende_btc: "Who your Bitcoin node is talking to right now",
    w_legende_ln: "Where your capital sits, tied up in channels",
    w_naechster: "Next block",
    w_naechster_wert: "{tx} tx · {mb} MB · {von}–{bis} sat/vB",
    w_naechster_sync: "not until the sync is done",
    w_hoehe: "Height",
    w_gebuehren: "Fees",
    w_g_schnell: "fast",
    w_g_normal: "normal",
    w_g_guenstig: "cheap",
    w_schwierigkeit: "Difficulty",
    w_anpassung: "Next retarget",
    w_in_bloecken: "in {n} blocks",
    w_keine_daten: "no basis yet",
    w_ln_kanaele: "Channels",
    w_ln_partner: "Channel partners",
    w_ln_kapazitaet: "Capacity",
    w_ln_laender: "Countries",
    w_ln_ohne_ort: "Channel partners without a location",
    w_ln_ohne_ort_d: "Channel partners that announce only over Tor have no location — the capital sits there all the same.",
    w_ln_keine_wallet: "No Lightning wallet yet. Once channels are open, orange lines run here.",
    kurs_quelle: "Price from {boerse}, {alter}. Fetched over Tor.",
    kf_24h: "24 H", kf_30t: "30 D", kf_1j: "1 Y", kf_5j: "5 Y",
    kurs_gerade: "just now",
    kurs_vor: "{spanne} ago",
    kurs_wird_geholt: "Fetching price …",
    kurs_kein_verlauf: "No history yet.",
    kurs_tor_aus: "Tor is switched off — no price is fetched without it. Asking over your own line would reveal that a Bitcoin node runs here.",
    kurs_tor_aus_kurz: "No price without Tor",
    kurs_bildbeschreibung: "Price over {fenster}, from {von} to {bis}.",
    land_unbekannt: "No such country code.",
    lnd_nicht_bereit: "Lightning is not ready yet — the wallet must be running and unlocked.",
    news_abgewiesen: "{zahl} of {an} enabled sources are not answering right now — usually because they sit behind Cloudflare and turn Tor exit nodes away. Under “Sources” each one says what happened.",
    news_cf: "Tor?",
    news_cf_d: "This source sits behind Cloudflare. Since we fetch exclusively over Tor it is often turned away — depending on the exit node.",
    kurs_spanne: "Low {tief} · High {hoch}",
    news_geholt: "{zahl} items, {wann}",
    nav_lesen: "Reading",
    nav_news: "News",
    news_titel: "News",
    news_lead: "What is being written about Bitcoin and Lightning — from your language region and internationally. Fetched exclusively over Tor: otherwise every publisher would learn that someone here runs a node, and over time when it is running. Images are never loaded, because a thumbnail from a foreign server would be a tracking pixel.",
    news_aus_text: "The news feed is switched off. Once on, SatoshiCortex fetches the selected sources hourly — over Tor. Until then nothing happens.",
    news_einschalten: "Switch the feed on",
    news_tor_text: "Tor is switched off, so no news is fetched. Fetching over your own line would tell the publishers that a Bitcoin node runs here.",
    news_weit: "Include crypto in general",
    news_alle_gelesen: "Mark all read",
    news_quellen: "Sources",
    news_quellen_titel: "Sources",
    news_quellen_lead: "Specialist sources are unfiltered — everything they write is on topic. General press is keyword-filtered and off by default: measured, they deliver between zero and ten percent on topic.",
    news_eigene_titel: "Add your own source",
    news_eigene_lead: "Enter a website address — we read its head to see whether it announces a feed. If it does not, enter the feed address directly.",
    news_suchen: "Find feed",
    news_leer: "No items yet. The first fetch runs right after you switch on, hourly after that.",
    news_herkunft: "Your region: {land} — sources in {sprache} and international",
    news_herkunft_unbekannt: "Location unknown — international sources in English",
    news_bezahlschranke: "Paywall",
    news_quelle_aus: "off",
    news_kein_feed: "No feed is announced there. Enter the feed address directly if you know it.",
    news_gefunden: "Found:",
    news_fach: "Specialist",
    news_leit: "General press",
    news_ungeprueft: "fetching …",
    news_speicher_fehlt: "Without a database there is no history — items vanish on restart.",
    nav_logs: "Logs",
    log_titel: "Logs",
    log_lead: "What the services are reporting. SatoshiCortex deliberately has NO access to Docker — on a machine holding a wallet that would be the same as root. Instead it reads what the services write into your data directory anyway.",
    log_eigenes: "SatoshiCortex",
    log_neu: "Reload",
    log_laedt: "loading …",
    log_keine_datei: "No file yet — this service has not written anything so far.",
    log_zeilen_n: "{n} lines",
    log_gekuerzt: "truncated, tail only",
    log_fehler: "Could not be read.",
    protokoll_unbekannt: "No such log.",
    ln_dienst: "Service",
    ln_wallet: "Wallet",
    ln_kette: "Blockchain",
    ln_d_unkonfiguriert: "waiting to be set up",
    ln_d_wartet: "configured, not released yet",
    ln_d_freigegeben: "running",
    ln_w_aus: "LND is not answering yet",
    ln_w_keine_wallet: "no wallet created yet",
    ln_w_gesperrt: "created, but locked",
    ln_w_startet: "starting up",
    ln_w_bereit: "ready",
    ln_w_wartet: "waiting to start",
    ln_w_unbekannt: "unknown state",
    ln_k_bereit: "complete — Lightning can be set up",
    ln_k_sync: "still syncing (block {h})",
    ln_hinweis_sync: "Lightning needs the complete chain. While it is syncing the service waits — that is intended and costs nothing. Once the chain is complete SatoshiCortex configures it by itself; there is nothing for you to start.",
    tun_weg: "Do not remind me",
    hinweis_unbekannt: "I do not know that hint.",
    ln_hinweis_gesperrt: "Your wallet exists but is locked. While it is, your node forwards nothing and accepts no payments. Enter your wallet password under “Wallet”.",
    ln_hinweis_startet: "LND is starting up. That takes a minute or two, and then there will be more here.",
    ln_hinweis_laeuft: "Wallet is up, node is running, chain is current. But as long as you have no public channel, your node appears NOWHERE in the Lightning graph — not on amboss.space, not on 1ml. That is not a fault but how the protocol works: a node is only announced to the network with its first announced channel. Until then, only those you hand your connection address to can reach you.",
    ln_hinweis_bereit: "The chain is complete and LND is running. Next comes the wallet: seed on paper, with a verification step — under “Wallet” in the sidebar. Until then this node holds no key, does not announce itself on the Lightning network and holds no satoshi.",
    a_seit: "Collecting since {datum} — {tx} transactions, {bloecke} blocks.",
    a_wartet: "The feed is running, nothing collected yet.",
    a_nicht_verfuegbar: "The analysis cannot create its database — everything else keeps working. Usually the mounted data folder belongs to a different user than the service. Reason: {grund}",
    a_luecken: "· {n} lost messages in 24 h — timestamps are missing there.",
    a_reorgs: "· chain reorganisations in 24 h: {n} — a block was replaced by another.",
    a_dia_titel: "Feerate diagram",
    a_dia_d: "What the next slice of block space costs — the curve miners optimise against. No explorer shows it. The vertical axis is logarithmic: fees span orders of magnitude, and on a linear axis nearly all of it would lie flat along the bottom.",
    a_dia_leer: "No diagram yet. The first snapshot arrives within a minute once your node accepts transactions.",
    a_dia_kein_zulauf: "No diagram, because the feed from bitcoind is not running right now. That is normal during the initial sync — afterwards it points to a broken connection between the app and bitcoind (ZMQ).",
    a_dia_alt: "As of {zeit} — no new diagram has arrived since. The upcoming blocks above are from then too.",
    a_dia_x: "cumulative to {mb} MB",
    a_dia_y: "sat/vB (logarithmic)",
    a_dia_naechster: "edge of the next block",
    a_dia_reinkommen: "into the next block from {wert} sat/vB",
    a_dia_passt_alles: "Everything waiting fits into the next block.",
    a_dia_bloecke: "{n} blocks",
    a_dia_block: "1 block",
    a_grenze: "evicts below {wert} sat/vB",
    a_bloecke: "Blocks",
    a_bloecke_d: "Two of these columns no explorer has, because they belong to YOUR node: “already yours” counts how many of the block's transactions were with you beforehand, and the dwell time says how long they waited with you on average. The message is what the miner wrote into the field — usually their tag, sometimes more. In the very first block it holds the headline everything started with.",
    a_sp_hoehe: "Height",
    a_sp_pool: "Pool",
    a_sp_tx: "Tx",
    a_kx_titel: "Every waiting transaction",
    a_kx_d: "One column per block, and inside it every transaction as an area sized by its weight. That shows what fits into which block — and on hover, when YOUR node first saw it. This needs the largest call this application makes, so it runs on request only.",
    a_kx_holen: "Fetch tiles",
    a_kx_laedt: "Fetching — with a full mempool this takes a moment …",
    a_kx_zu_lang: "Your node took too long to hand over the mempool. Try again in a moment — a fetch that is still running is not started twice.",
    a_kx_stand: "{n} transactions in the mempool, {gezeigt} of them drawn.",
    a_kx_naechster: "next block",
    a_kx_spaeter: "block {n}",
    a_kb_wann: "in ~{min} min",
    a_kb_inhalt: "{n} TX · {btc} BTC",
    a_kx_tx: "Transaction",
    a_kx_rate: "Fee",
    a_kx_groesse: "Size",
    a_kx_zuerst: "first seen here",
    a_kx_ungesehen: "not recorded",
    a_kx_rest: "Aggregated",
    a_kx_bis: "down to {wert} sat/vB",
    a_kx_bedienung: "Click a column to see what will go into that block. By keyboard: arrow keys, Escape closes.",
    a_kd_titel_naechster: "The next block — what is likely to go in",
    a_kd_titel: "Block {n} — what is likely to go in",
    a_kd_lead: "{anzahl} transactions, {groesse}, {gebuehren} in fees altogether. Sorted by fee — whoever is at the front goes in first.",
    a_kd_gekuerzt: "Showing the {n} with the highest fee out of {gesamt}.",
    mempool_nicht_abrufbar: "The mempool cannot be read right now — your node is busy. Try again in a moment.",
    mempool_zu_gross: "Your node's answer was larger than a mempool can ever be — something is off. The read was stopped on purpose: a tile view built from half a mempool would look right and be wrong. Check Log → bitcoind.",
    a_kb_titel: "The next blocks",
    a_kb_d: "What could be found next — from your node's own feerate diagram, sliced every 1M vBytes. Not some other server's view, but what is sitting in YOUR mempool.",
    a_kb_spanne: "{tief} – {hoch} sat/vB",
    a_kb_rest: "+ {n} more blocks",
    a_kb_in: "in ~{min} minutes",
    a_kb_vor: "{dauer} ago",
    a_kb_bekannt: "{n} / {gesamt} tx",
    a_kb_bekannt_lang: "{n} of {gesamt} transactions were already yours",
    a_kb_nur_gesamt: "{gesamt} tx",
    a_kb_nicht_dabei: "{gesamt} transactions. How many of them were already yours is something this node does not know — the block predates its records.",
    a_nicht_dabei_kurz: "was not watching",
    a_bd_titel: "Block {hoehe} — what you saw of it",
    a_bd_lead: "{bekannt} of {gesamt} transactions in this block were in your mempool beforehand. The longest wait is on top.",
    a_bd_lead_nicht_dabei: "{gesamt} transactions. This block predates this node's records — how many of them sat in your mempool beforehand cannot be established after the fact.",
    a_bd_leer: "You saw none of this block's transactions beforehand. Either it predates your records, or its transactions never passed through your mempool.",
    a_bd_laedt: "Fetching …",
    a_bd_nichts: "Nothing here for this block.",
    block_unbekannt: "Your records do not know this block — it predates the first one your node received itself.",
    a_bd_gekuerzt: "Showing the {n} with the longest wait.",
    a_bd_sp_txid: "Transaction",
    a_bd_sp_zuerst: "first seen here",
    a_bd_sp_dauer: "dwell time",
    a_bs_titel: "Look up a block",
    a_bs_d: "Any height, not just the last twelve. Your chain is complete — asking it is half the point of an archival node.",
    a_bs_suchen: "Look up",
    a_bs_null: "Block 0 — where it all began",
    a_bs_kopf: "Block {hoehe}",
    a_bs_keine_hoehe: "That is not a block height. A whole number, from 0 up.",
    a_bs_zeit: "Found at",
    a_bs_gewicht: "Size",
    a_bs_hash: "Hash",
    a_bs_aus_kette: "This block predates your records — it comes straight from your chain. “Already yours” and the dwell time cannot exist for it: a first-seen timestamp cannot be invented after the fact.",
    a_bs_aus_aufzeichnung: "Your node received this block itself.",
    a_sp_botschaft: "Message",
    a_sp_bekannt: "already yours",
    a_sp_dauer: "Dwell time",
    a_sp_gebuehren: "Fees",
    a_pool_unbekannt: "unknown",
    a_pa_titel: "Who finds the blocks",
    a_pa_d: "Mining pools' share of the blocks your node recorded itself. A pool is recognised by its tag in the coinbase — whatever cannot be attributed is listed as “unknown”.",
    a_pa_144: "24 h",
    a_pa_1008: "7 days",
    a_pa_0: "All",
    a_pa_basis: "{n} blocks, height {von} to {bis}",
    a_pa_zu_wenig: "Only {n} blocks recorded so far — this period would need {soll}. The shares cover only what is there.",
    a_pa_leer: "No blocks recorded yet.",
    a_pa_zeile: "{anzahl} · {anteil} %",
    pool_fenster_unbekannt: "This period is not available here.",
    a_verfolgen: "Track a transaction",
    a_verfolgen_d: "When YOUR node first saw it — nobody else knows that.",
    a_ad_titel: "Look up an address",
    a_ad_d: "What an address holds RIGHT NOW — the unspent outputs from your node's UTXO set. No history and no unconfirmed incoming payments: neither is stored there. Your node scans the whole set for this, which takes a few minutes. The lookup never leaves your node.",
    a_ad_knopf: "Look up",
    a_ad_abbrechen: "Cancel",
    a_ad_laeuft: "Your node is scanning the UTXO set … {p}",
    a_ad_adresse: "Address",
    a_ad_bestand: "Balance",
    a_ad_ausgaben: "Unspent outputs",
    a_ad_stand: "As of block {hoehe} · scan took {dauer}",
    a_ad_leer: "This address holds nothing right now — either nothing ever arrived or everything has been spent. Unconfirmed incoming payments do not show up here.",
    a_ad_zeile: "Block {hoehe} · {bestaetigt} confirmations",
    a_ad_weitere: "… and {n} more, older outputs — the balance above includes them.",
    a_ad_fehler: "The lookup failed: {grund}",
    a_ad_abgebrochen: "Cancelled.",
    a_ad_kein_bitcoind: "Your Bitcoin node is not responding right now.",
    adresse_ungueltig: "That is not a valid Bitcoin address for this network.",
    adresse_laeuft_schon: "A lookup is already running — wait until it finishes or cancel it.",
    scan_belegt: "Your node is already scanning the UTXO set for someone else. Try again shortly.",
    a_suchen: "Search",
    a_keine_txid: "That is not a transaction id (txid). A txid has exactly 64 characters from 0–9 and a–f. Exchanges like Kraken often show their own reference number; the real txid is in the withdrawal details once it has been sent.",
    a_ad_ausgabe: "Output",
    lk_unterwegs: "Unconfirmed",
    lk_unterwegs_d: "Part of your on-chain balance is not in a block yet. That is either a fresh incoming payment or your change: sending spends a whole coin, and the remainder comes back to you as a new, still unconfirmed coin. Both are already yours; both become spendable with the first confirmation.",
    bw_gebuehr: "Fee: {n} sat",
    bw_an: "To: {adresse}",
    b_budget_rest: "{bytes} of the upload budget are left, and the window runs for another {rest}. Bitcoin Core counts per 24 hours, not per month — the slider in setup asks for a monthly figure and divides it up.",
    rq_titel: "Receive",
    rq_lead: "Create an invoice so someone can send you money over Lightning. It is valid for one hour. Whoever pays it sees the amount and the memo.",
    rq_betrag: "Amount in satoshi",
    rq_betrag_d: "Empty or 0 leaves the amount open — then the payer decides. Handy for a donation.",
    rq_zweck: "What for? Optional.",
    rq_zweck_d: "Shown to the payer inside the invoice. Do not put anything in there that should stay private.",
    rq_erstellen: "Create invoice",
    rq_kopiert: "Copied.",
    rq_gueltig: "Valid until {zeit}",
    rq_liste: "Your recent invoices",
    rq_leer: "No invoice created yet.",
    rq_offener_betrag: "Amount open",
    rq_zustand_offen: "open",
    rq_zustand_bezahlt: "paid",
    rq_zustand_storniert: "cancelled",
    rq_zustand_unterwegs: "in flight",
    rq_zustand_verfallen: "expired",
    rq_weitere: "Older ones not shown here: {n}",
    rq_storno: "Withdraw",
    rq_wartet: "Waiting for the payment. You can leave this window open — the moment the money arrives, it says so here.",
    rq_bezahlt: "Paid. {n} sat arrived.",
    rq_zurueckgezogen: "Withdrawn. This invoice can no longer be paid.",
    rq_verfallen_hinweis: "This invoice has expired. Issue a new one if you are still expecting the money.",
    rechnung_unbekannt: "Your node does not know this invoice: {einzelheit}",
    rechnung_nicht_offen: "This invoice is no longer open. It can only be withdrawn while nobody has paid it and it is not holding any money.",
    rechnung_nicht_storniert: "The invoice could not be withdrawn: {einzelheit}",
    rq_fehler: "Your invoices could not be fetched just now.",
    rq_kein_raum: "Nobody can pay you over Lightning right now: there is nothing on the far side of your channels. You can only receive what sits there — so first you need a channel, and then either pay something through it or obtain inbound liquidity.",
    rq_qr_zu_lang: "This invoice is too long for a QR code. Copy it instead.",
    rechnung_nicht_erstellt: "The invoice could not be created: {einzelheit}",
    ez_qr_d: "Scan with your wallet app. The code holds the same address as below — still compare its start and end after scanning.",
    bw_titel: "Transactions",
    bw_lead: "What came into your on-chain wallet and what left it, each with the full transaction id. The list comes from your own node and refreshes every 30 seconds while this page is open.",
    bw_leer: "No transactions yet. A deposit shows up here as soon as your node sees it — even before the first confirmation.",
    bw_fehler: "The transactions could not be fetched from LND just now. The next refresh tries again.",
    bw_bestaetigt: "Confirmations: {n}",
    bw_unbestaetigt: "unconfirmed, not spendable yet",
    bw_verfolgen: "Track",
    bw_weitere: "Older ones not shown here: {n}",
    bw_art_kanal_auf: "Channel opened",
    bw_art_kanal_zu: "Channel closed",
    a_tx_unbekannt: "Neither your node nor the analysis knows this transaction.",
    a_tx_nicht_gesehen: "This transaction never sat in your mempool — it is either older than your records or went straight to a miner.",
    a_tx_zuerst: "First seen by you",
    a_tx_dauer: "Sat with you",
    a_tx_block: "Block",
    a_tx_entfernt: "Left your mempool without a block",
    a_cl_titel: "Cluster in the mempool",
    a_cl_d: "Since Bitcoin Core 31, unconfirmed transactions that build on each other form a cluster. Core splits it into packages that only enter a block template as a whole — what counts for your transaction is its package's feerate, not its own.",
    a_cl_einzeln: "This transaction is not linked to any other unconfirmed one — it is its own package.",
    a_cl_umfang: "{tx} transactions, {pakete} packages, {vb} vB",
    a_cl_paket: "Package {nr}",
    a_cl_paket_wert: "{tx} tx · {satz} sat/vB · {vb} vB",
    a_cl_deins: "contains yours",
    a_cl_keiner: "No cluster available — the transaction is not (or no longer) in your mempool.",
    a_tx_groesse: "Size",
    a_tx_bestaetigungen: "Confirmations",
    a_tx_ein_aus: "Inputs and outputs",
    karte_titel: "What your node knows of the network",
    karte_lead: "Not “the network” — no list of all Bitcoin nodes exists. This is your node's address book: what was passed to it over time. It grows with the node.",
    karte_legende: "Dots are countries with no outline — Singapore, Hong Kong, Malta, Seychelles, Cayman. Hover to see what sits where.",
    karte_marke_adressen: "{n} addresses known",
    karte_marke_nichts: "no address known",
    karte_k_bekannt: "Addresses in the address book",
    karte_k_ortlos: "of those without a location (Tor, I2P, CJDNS)",
    karte_k_verortbar: "could have a location",
    karte_k_angesehen: "of those looked at",
    karte_k_verortet: "placed in a country",
    karte_k_ohne_form: "Countries with no shape on the map",
    karte_k_peers: "Peers right now",
    karte_fussnote_erstsync: "0 inbound is normal during the sync — your port is open, your node just too busy to answer. It resolves once the chain is complete.",
    karte_fussnote_auswahl: "What is looked at is what your node would pass on — Core selects by quality and age itself.",
    karte_linien: "The lines run from your node in {land} to the countries your peers are currently in.",
    karte_linien_ohne_ort: "Where your own node sits cannot be determined — a Tor address has no location. The map therefore shows countries, but no connections.",
    karte_mit_peers: "{p} of your peers are here",
    karte_mit_peers_1: "One of your peers is here",
    karte_wird_ausgewertet: "The address book is being evaluated — countries will appear shortly.",
    karte_keine_tabelle: "This image has no location table. The numbers hold, the map stays without countries.",
    karte_quelle: "Outlines: Natural Earth (public domain) · Locations: DB-IP Lite {stand} (CC BY 4.0), inside the image, no outside lookup.",
    e_updates: "Updates",
    e_akt_aktuell: "Your node runs the latest version.",
    e_akt_abbild_aktuell: "The shipped version is the latest one.",
    e_akt_nur_abbild: "Not running here yet. The comparison is therefore against the version SatoshiCortex ships — whether that one is still current matters beforehand.",
    e_akt_wartung: "Version {v} is available — a maintenance release on the same branch. Safe to apply.",
    e_akt_zweig: "Version {v} is available — a branch change. It may alter consensus rules and database format; read the release notes first.",
    e_akt_auch: "Also available: {v}.",
    e_akt_neuer: "Version {v} is available. What changed is in the project's changelog.",
    e_akt_nachgesehen: "Last checked: {zeit}",
    e_akt_eigen_latest: "You follow “latest” — pulling again is enough, your .env stays as it is. Re-pull the image in your NAS's Docker interface and restart the service, or: “docker compose pull app” and “docker compose up -d app”.",
    e_akt_eigen_fest: "Your .env holds a fixed number ({folgt}). Put in the line above and redeploy — or write “latest” there, then pulling again will be enough from now on.",
    e_akt_eigen_unklar: "If your .env says SATCORTEX_VERSION=latest, pulling the image again is enough. If it holds a number, set it to {v} — or to “latest”, then you stay current on your own from now on.",
    e_akt_wie: "Raise the line in your .env (BITCOIN_VERSION= or LND_VERSION=), then redeploy. If we have not built that image yet, the pull finds nothing — then build it yourself: “docker compose build lnd” and “docker compose up -d”. That takes about a minute: downloaded, signature checked against the pinned publisher keys, unpacked. Nothing is compiled.",
    e_akt_fassung_unbekannt: "The service is running — its version number just could not be queried. It comes from the same call that regularly waits during the initial sync. It will be back on the next round.",
    e_akt_laeuft_nicht: "The service is not running yet — there is no running version to compare against. It will be checked once it runs.",
    e_akt_nicht_erreichbar: "The lookup did not get through over Tor. That happens — the route goes through three foreign machines. It will be retried on the next pass.",
    e_akt_tor_aus: "Without Tor we do not ask. A version check would otherwise reveal that a Bitcoin node runs here — and over time, when.",
    e_akt_wartet: "Not checked yet. The query runs once a day over Tor.",
    e_akt_zahlen: "Running: {laeuft}  ·  Latest known: {neu}",
    e_akt_unbekannt: "unknown",
    e_akt_kein_status: "The state of the version check could not be retrieved just now — it comes from the node, and during the initial sync the node is busy at times. It will be back on the next round.",
    e_adresse_beispiel: "e.g. mynode.example.net",
    e_adresse_aktuell: "Currently announced: {liste}",
    e_adresse_keine: "Your node currently announces no address — which is why nobody finds it from outside.",
    e_gespeichert: "Saved. The node restarts shortly and will announce the address then.",
    e_fehler: "That did not work.",
    konfiguration_fehlt: "There is no configuration yet that could be changed.",
    noch_nicht_eingerichtet: "The node is not set up yet.",
    n_forward: "forward on your router, IPv4 and IPv6",
    n_note: "Without these the node still runs — but it only takes instead of also giving. You can add them later at any time.",

    k_title: "Your account",
    k_lead: "So not everyone on your network can operate this interface.",
    k_local: "Will be set up in the next step.",

    f_title: "All set",
    f_lead: "Have a last look, then we begin.",
    f_start: "The node will then start downloading the block chain. That takes days to weeks and runs in the background — you can close this window and reboot the machine.",

    d_services: "Services",
    d_phase_sync: "Initial sync",
    d_phase_fertig: "Up to date",
    d_phase_start: "Starting",
    d_phase_laedt: "Loading",
    d_phase_getrennt: "No connection",
    d_note_getrennt: "The interface cannot reach its own service right now. That says nothing about your node — it keeps running in the background. Usually a network hiccup; reload the page in a moment.",
    wl_unklar_titel: "Not available",
    wl_unklar_d: "The wallet state cannot be queried right now. Nothing is shown here — least of all the setup flow: a query that did not get through is no proof that no wallet exists yet. Try again in a moment.",
    d_sub_laedt: "Fetching the numbers …",
    d_note_laedt: "Reloading the page fetches everything afresh. While a sync is running the first reply can take a few seconds — your node keeps running throughout.",
    d_phase_beschaeftigt: "Writing to disk",
    d_note_beschaeftigt: "bitcoind is running but not getting round to answering: it is writing the verified state to disk. The numbers above are a few seconds old. No restart, no error — and exactly the operation that slows the sync down when storage is slow.",
    d_sub_sync: "Block {hoehe} of {kopf} ({blockanteil}% of blocks) · {belegt} on disk",
    d_sub_fertig: "Height {hoehe} · {belegt} on disk",
    d_sub_start: "Waiting for the first reply from bitcoind …",
    d_tempo: "{bpm} blocks/minute",
    d_restdauer: "about {dauer} to go",
    d_restdauer_unbekannt: "still measuring",
    d_mempool: "Waiting transactions",
    d_k_wartend: "In the mempool",
    d_k_belegung: "Used",
    d_k_purge: "Eviction floor",
    d_k_gebuehren: "Waiting fees",
    d_tx: "{n} transactions",
    d_satvb: "{n} sat/vB",
    d_purge_hilfe: "The eviction floor is the number no public explorer can show you: below it YOUR node is dropping transactions right now. The big services raise their limit so high they never have to evict — so they never see this floor.",
    d_purge_ruhig: "Your mempool is not full — nothing is being dropped. Everything from {n} sat/vB is accepted; whether it makes it into a block soon is shown by the feerate diagram.",
    d_purge_voll: "Your mempool is full. Anything below {n} sat/vB is being dropped right now.",
    d_teilnahme: "Participation",
    d_blockzeit: "Block time",
    bz_takt: "Pace",
    bz_takt_wert: "{min} min per block",
    bz_takt_gemessen: "Pace measured on this chain, over the last {n} blocks.",
    bz_takt_gerechnet: "Your own pace can only be measured after the sync — until then this uses the protocol's target spacing of ten minutes.",
    bz_halbierung: "Next halving",
    bz_wann: "Estimated",
    bz_etwa: "around {monat}",
    bz_belohnung: "Reward",
    bz_belohnung_wert: "{jetzt} → {danach} BTC",
    bz_wartet: "As soon as the node answers.",
    bz_ende: "Nothing is issued any more — every bitcoin exists.",
    d_kurs: "Bitcoin price",
    d_kurs_je_euro: "Per unit",
    d_kurs_wartet: "The price is fetched over Tor — the first time that can take up to a minute.",
    d_wallet: "Your balance",
    d_lightning: "Lightning",
    d_w_keine_wallet: "No wallet yet. You can create one under Lightning → Setup once the chain is ready.",
    d_w_gesperrt: "The wallet is locked. Unlock it under Lightning → Wallet — until then your node cannot see its own balance.",
    d_w_ohne_einrichtung: "Finish the setup first.",
    d_index_aus: "The indexes are still switched off — they are built after the sync.",
    d_index_baut: "{name} is being built: block {hoehe} of {ziel}",
    d_netz: "Network and contribution",
    d_k_netze: "Connections by network",
    d_k_empfangen: "Received",
    d_k_gesendet: "Served since start",
    d_k_adressen: "Reachable at",
    d_keine_adresse: "no own address known yet",
    d_gesendet_hilfe: "Served measures your contribution — counted since bitcoind last started, across every peer connected since then. The breakdown below counts something else: only what went to the peers connected RIGHT NOW. That is why it is smaller, and why the two numbers do not add up.",
    d_gesendet_hilfe_sync: "Served measures your contribution — counted since bitcoind last started. It stays small during the sync: you are the one downloading. The breakdown below only counts what went to the peers connected right now, so it is smaller.",
    d_tage: "{n} days", d_tag: "one day",
    d_stunden: "{n} hours", d_stunde: "one hour",
    d_minuten: "{n} minutes", d_minute: "one minute",
    d_k_peers: "Connections",
    d_peers: "{aus} opened by me · {ein} accepted from outside",
    d_peers_unbekannt: "not available right now",
    d_note_unbekannt: "Whether anyone reaches you from outside could not be queried just now — your node was busy syncing. That says nothing about your reachability, only about the moment. It will be back on the next refresh.",
    d_peers_hilfe: "The direction says who knocked, not which way data flows. The ones accepted from outside measure your reachability.",
    d_fremdes_netz: "Careful: your node runs on “{netz}”, not on mainnet. These are separate networks — balances there are worthless, and what you see here is not the real Bitcoin blockchain.",
    d_note_sync: "The percentage counts verification work, not blocks — 2009 blocks hold one transaction, today's hold thousands. It climbs steeply later. For the same reason the blocks-per-minute rate falls the further you get: a block from 2013 is verified in a fraction of a second, one from today carries thousands of signatures. So do not compare it with last week's — the remaining time is what counts. You can close this window, the sync keeps running.",
    d_note_start: "bitcoind is not answering. Shortly after a start or restart that is normal — it loads its chainstate, which takes several minutes on a NAS. If it stays that way, check the log under “bitcoind”.",
    d_note_zuschauer: "Port 8333 is not accepting inbound connections. Your node downloads and verifies everything itself, but nobody can sync from you — you are watching instead of taking part.",
    d_note_teilnehmer: "Your node is reachable from outside and serves the chain to others.",

    sv_unkonfiguriert: "waiting for setup",
    sv_wartet: "configured, stopped",
    sv_freigegeben: "running",


    // — messages the server sends as keys —
    platz_genug: "{frei} GB free — that leaves room for years to come.",
    platz_knapp: "{frei} GB free. It will start, but it gets tight: the chain grows by around {wachstum} GB a year. For comfortable operation you'd want about {fehlend} GB more.",
    platz_zu_wenig: "Only {frei} GB free, at least {mindestens} GB are needed. Pruning is not a way out: only a complete node can serve the chain to others, and transaction lookup needs the full index.",
    pfad_fehlt: "The location {pfad} does not exist. Point {variable} in your .env at an existing path and start again.",
    eine_platte: "Both locations are on the same drive. That works — but then everything lives there: the roughly 840 GB block chain plus the small part that really belongs on a fast disk. If this machine has an SSD and a large hard drive, split the two: blocks on the large one, the rest (~25 GB) on the fast one. Otherwise the initial sync takes considerably longer, because the state database constantly makes many small scattered writes.",
    platz_reicht_nicht: "There isn't enough disk space.",
    upload_unbegrenzt: "Unlimited: your node serves the entire chain to newcomers. That's the single biggest contribution you can make — but it costs several hundred gigabytes a month.",
    upload_begrenzt: "Around {upload_gb} GB a month. Once the budget is used up, your node stops serving OLD blocks. New blocks and transactions are still relayed as normal — so you stay fully part of the live network.",
    g_neu_title: "Create device account",
    g_neu_lead: "Before we begin: secure this interface. Without an account, anyone on your network could reconfigure the node.",
    g_an_title: "Sign in",
    g_an_lead: "Welcome back.",
    g_oidc_knopf: "Sign in with Pocket ID",
    g_oidc_d: "You are sent to your own identity provider and sign in there — no password is entered here and none is stored.",
    g_oidc_trenner: "Or with the local account — that is the emergency door for when the identity provider is unreachable. It only opens on your home network.",
    g_oidc_abgelehnt: "Your identity provider refused the sign-in. Usually that means your account is not in a group cleared for SatoshiCortex.",
    g_oidc_abgelaufen: "The sign-in attempt expired or does not belong here. Start again.",
    g_oidc_ungueltig: "The token was not accepted. The log says more.",
    oidc_aus: "No identity provider is configured for this node.",
    oidc_nicht_erreichbar: "Your identity provider is not answering right now. While it is down, the local account on your home network still gets you in.",
    nur_ueber_oidc: "From outside, sign-in goes through your identity provider only. The local account is the emergency door and opens on your home network alone.",
    g_user: "Username", g_pass: "Password",
    g_anlegen: "Create account", g_anmelden: "Sign in",
    g_pass_hint: "At least 10 characters.",
    benutzer_ungueltig: "That username is not valid.",
    konto_existiert: "This device already has an account.",

    // ── The PIN ─────────────────────────────────────────────────────────
    keine_pin: "This device has no PIN set up.",
    pin_noetig: "That needs your PIN.",
    pin_titel: "PIN for actions with consequences",
    pin_lead: "A second lock in front of everything that cannot be undone. Optional — with no PIN set up, nothing changes.",
    pin_erklaerung: "It protects against something different from your unlock method. That one decides what someone can do with the DISK; the PIN stands against a hijacked session in this very interface — a browser left open, someone else reaching your account. Five failed attempts lock it for fifteen minutes, and the counter lives in a file: a restart does not reset it. Today it guards deleting the wallet; every further action with consequences joins it as it appears.",
    pin_stand_aus: "No PIN set up right now.",
    pin_stand_an: "PIN is set up. Actions with consequences ask for it.",
    pin_stand_gesperrt: "Locked after too many failed attempts — {sekunden} seconds to go.",
    pin_kontopasswort: "Your account password",
    pin_kontopasswort_d: "Not the wallet password, but the one you sign in here with. Without this question a hijacked session could give itself a PIN — and unlock everything afterwards.",
    pin_neu: "Your PIN",
    pin_neu_d: "Five to twelve digits. No run, no six times the same digit — both are the first thing any attacker tries.",
    pin_wdh: "Once more",
    pin_alt: "Your current PIN",
    pin_stimmt_nicht: "The two entries are not the same.",
    pin_einrichten: "Set up a PIN",
    pin_eingerichtet: "Set up.",
    pin_aendern: "Change the PIN",
    pin_geaendert: "Changed.",
    pin_entfernen: "Remove the PIN",
    pin_entfernt: "Removed. Nothing asks for it any more.",
    tg_pin: "Your PIN",
    tg_pin_d: "Deleting is the action the PIN guards.",
    zl_titel: "Pay a Lightning invoice",
    zl_lead: "Over Lightning instead of the chain: seconds instead of blocks, and a fraction of the fee. It needs a channel with balance on your side.",
    zl_rechnung: "The invoice",
    zl_rechnung_d: "The long string starting with lnbc. A leading “lightning:” does no harm, it gets cut off.",
    zl_betrag: "Amount (sat)",
    zl_betrag_d: "This invoice names no amount — so you decide it.",
    zl_lesen: "Look at the invoice",
    zl_zahlen: "Pay",
    zl_v_betrag: "Amount",
    zl_v_gebuehr: "Routing",
    zl_v_hoechstens: "at most {n} sat",
    zl_v_zweck: "What for",
    zl_v_ziel: "To whom",
    zl_abgelaufen: "This invoice has expired. Ask for a new one — this one cannot be paid any more.",
    zl_betrag_fehlt: "Enter an amount, then you can pay.",
    zl_erst_lesen: "Look at it first. The button opens once you know what you are paying.",
    zl_unterwegs: "On its way — this can take up to a minute. Do not press again.",
    zl_bezahlt: "Paid: {betrag} sat, plus {gebuehr} sat routing.",
    ko_ansehen: "Look at the node",
    ko_b_unbekannt: "Your graph does not know this node — either the pubkey is wrong, or it does not announce itself (just like your own node, as long as it has no public channel). A channel is still possible if you know its address: append it as “@host:9735” and use “Connect”. Without an address it cannot work — your node would not know where to knock.",
    ko_b_name: "Name",
    ko_b_kanaele: "Channels",
    ko_b_kapazitaet: "Capacity",
    ko_b_gemeldet: "Last announced",
    ko_b_vor_tagen: "{n} days ago",
    ko_b_still: "This node has not announced itself for weeks. That is the most expensive case of all: if the peer disappears, there is no cooperative close any more — only the forced one, with fees and a waiting period.",
    ko_b_ohne_adresse: "This node announces no address. Your node cannot reach it on its own.",
    ko_b_wenig: "Few channels — this node is barely connected. Almost no path into the rest of the network runs through it.",
    ko_b_nur_tor: "Reachable over Tor only. Not a flaw, but a difference: this channel then depends on Tor.",
    ko_b_unauffaellig: "Nothing conspicuous: announces regularly, is reachable and well connected.",
    gegenstelle_unlesbar: "The peer could not be looked up: {grund}",
    ks_titel: "Close a channel",
    ks_lead: "The balance from the channel comes back to your on-chain wallet. Cooperatively that is cheap and immediate — both sides sign together.",
    ks_kanal: "Which channel",
    ks_still: "silent",
    ks_erzwingen: "Force",
    ks_erzwingen_d: "Only if the peer no longer answers.",
    ks_warnung: "Forced means your balance is locked for a time delay afterwards — usually about a day, longer when fees are high. And it costs more, because the commitment transaction is followed by further transactions to sweep the funds. Only take this if the cooperative close genuinely fails.",
    ks_los: "Close channel",
    ks_laeuft: "Closing — one moment.",
    ks_fertig: "The channel is being closed. Closing transaction: {txid}. Once it confirms, the balance is back in the wallet.",
    ks_fertig_erzwungen: "Force-closed. Closing transaction: {txid}. Your balance becomes available after the time delay, not immediately.",
    schliessen_abgelehnt: "The close was refused: {einzelheit}",
    schliessen_unklar: "No answer within the waiting time. The close may still be running — do NOT repeat it, check the channel list instead.",
    tun_wachturm: "You have channels, but no watchtower is guarding them. If your node is down at some point — power cut, update, disk failure — and the peer tries an old channel state, nobody notices.",
    tun_wachturm_knopf: "Register a watchtower",
    us_titel: "Move liquidity between your channels",
    us_lead: "If one channel holds everything on your side and the other nothing, you can still pay but no longer receive — or the other way round. Rebalancing pushes liquidity where it is missing: a payment to yourself, out through one channel and back in through the other. The money stays yours the whole time, it only changes sides. All you can lose is the fee for the round trip.",
    us_von: "Out through",
    us_von_d: "This channel gets emptier. Next to it is what can currently go out.",
    us_nach: "Back in via",
    us_nach_d: "It comes back through this peer — that channel gets fuller. Next to it is what sits on their side.",
    us_betrag: "Amount (sat)",
    us_betrag_d: "Small amounts find a route more easily than large ones. After a failure it is worth halving it.",
    us_los: "Rebalance",
    us_laeuft: "Looking for a round trip — this can take up to a minute.",
    us_fertig: "Moved: {betrag} sat, plus {gebuehr} sat for the round trip.",
    us_gleicher_kanal: "Out and back through the same channel — there is no round trip for that. Pick two different ones.",
    umschichten_gescheitert: "No round trip could be found: {einzelheit}. That is normal — try a smaller amount or the other direction.",
    wt_eigen_titel: "Your own watchtower",
    wt_eigen_d: "Your node has been guarding other people's channels since day one — without you doing anything. It is the most direct contribution there is: you prevent fraud against people you will never meet. For anyone to register you, they need this address.",
    wt_eigen_ohne: "Your tower is running — but it has no address anyone can reach it at. So nobody can add it, and the contribution goes nowhere. That changes as soon as your node announces an address: under Settings → Visibility. Over Tor the tower gets its own .onion; on the clearnet it needs a router forward on 9911.",
    wt_eigen_fuss: "Two things so no false expectation arises: the tower earns you NO fees — LND runs it explicitly altruistically, and reward towers are designed but not live. And you never learn whom or how much you guard: the tower receives encrypted packets it can only open once the matching transaction appears on chain. That is not a gap, it is the reason it can be trusted.",
    ht_titel: "What went through your node",
    ht_lead: "Not only what succeeded — above all what did NOT, and why. That is where the actual handle is: a channel that keeps running out of balance wants topping up, or a higher fee.",
    ht_gruende_titel: "What it failed on over the last seven days",
    ht_mal: "{n}× · channel {kanal}",
    ht_leer: "Nothing has gone through yet. Once the first channel stands and someone pays through you, it shows up here.",
    ht_gebuehr: "{n} sat earned",
    ht_a_weiterleiten: "Forward started",
    ht_a_erledigt: "Went through",
    ht_a_fehl: "Failed further along",
    ht_a_link_fehl: "Failed at our end",
    ht_g_insufficient_balance: "Not enough balance — this channel is empty on your side",
    ht_g_htlc_exceeds_max: "Amount above the channel maximum",
    ht_g_fee_insufficient: "Offered fee too low for your setting",
    ht_g_expiry_too_soon: "Time window too tight",
    ht_g_invalid_keysend: "Keysend not accepted",
    ht_g_channel_disabled: "Channel was disabled",
    wt_titel: "Watchtowers",
    wt_lead: "If a peer publishes an OLD channel state, it has to be punished within the time lock — otherwise the balance is gone. If your node happens to be down at that moment, nobody notices. That is what an outside watchtower is for: it knows only the penalty transaction and cannot move any money with it.",
    wt_keiner: "No watchtower registered. As long as your node keeps running it notices a cheating attempt itself — but during a power cut, an update or a disk failure nobody is there. For a wallet on a machine meant to run continuously, this is not optional.",
    wt_grenze: "What can be checked: whether a tower is reachable, has accepted a session with your node, and acknowledges your channel states. What cannot be checked: whether it will really step in when it matters — the packets are encrypted, even for the tower, and that only shows during an actual cheating attempt.",
    wt_gedeckt: "Guarded. For every channel type you have, a tower holds a session with your node — it was reachable and agreed to accept your channel states.",
    wt_gedeckt_vorab: "Ready. A tower already holds a session with your node. As soon as you have a channel, its states go there.",
    wt_ungedeckt: "Not guarded — no tower holds a session for: {arten}. Registered does not mean guarded. Usually the tower is unreachable (address, port, Tor) or does not accept this channel type. LND keeps trying on its own; right after registering this can take a few minutes.",
    wt_ungedeckt_vorab: "No session yet — no tower has agreed so far for: {arten}. As long as you have no channel nothing is at risk, but as things stand a new channel would be unguarded. Usually the tower is unreachable (address, port, Tor). Right after registering it can take a few minutes.",
    wt_art_legacy: "older channels",
    wt_art_anchor: "anchor channels",
    wt_art_taproot: "taproot channels",
    wt_turm_art: "{art}: session in place, acknowledged states: {n}",
    wt_turm_ohne: "no session",
    wt_turm_reserve: "in reserve — another tower holds the session",
    wachturm_unbekannt: "LND no longer lists this tower. Reload the page.",
    wt_pruef_zu_lang: "the measurement took too long. Over Tor that happens — try again. If a line “Wachturm geprueft” then shows up under Logs → SatoshiCortex, the node did finish and only the answer never arrived; in that case a reverse proxy in front is too impatient.",
    wt_pruef_keine_antwort: "no answer from the node",
    wt_pruefen: "Check",
    wt_pruefen_laeuft: "checking — over Tor this can take up to a minute",
    wt_pruef_da: "reachable — the tower accepts connections. If no session forms anyway, the tower is not what is missing.",
    wt_pruef_tot: "not reachable: {grund}. For a .onion that usually means the service is gone — then the entry belongs removed.",
    wt_pruef_zu: "reached, but nobody is accepting behind it. The machine is there, the watchtower is not running.",
    wt_pruef_fehler: "The check could not be carried out: {grund}",
    wt_turm_eigen: "your own tower — does not protect this node",
    wt_turm_eigen_sitzung: "your own tower: session established, but it does not protect this node — it runs on the same machine and goes down with it",
    wt_zaehler: "Channel states acknowledged since LND last started: {bestaetigt}, still pending: {ausstehend}. New states come from payments, forwards and fee updates in the channel — without those it stays at zero, and that is fine.",
    wt_zaehler_abgewiesen: "Channel states that could not be stored with any tower: {n}. There is no protection for those states.",
    wt_adresse: "Register a watchtower",
    wt_adresse_d: "pubkey@host:port, as with a channel. Operators are listed in the same directories as channel partners — many nodes run one on the side.",
    wt_eintragen: "Register",
    wt_entfernen: "Remove",
    wt_entfernen_sicher: "Really remove?",
    wt_entfernt: "Removed. If the tower held a session, LND negotiates a new one with the next registered tower — channel states not yet acknowledged are not lost.",
    wachturm_nicht_entfernt: "LND refused the removal: {grund}",
    wachturm_offene_staende: "This tower still holds channel states it has not acknowledged yet, so LND will not remove it right now — try again in a few minutes.",
    wachturm_abgelehnt: "The watchtower was not accepted: {grund}",
    ko_titel: "Open a channel",
    ko_lead: "The step that turns your node into a participant. After it you can pay, receive — and in time forward for others.",
    ko_warnung: "The money is TIED UP afterwards. Not lost, but tied up: it only comes back out when the channel is closed, and that costs fees a second time. Pick a peer that is reliably reachable — with one that stops answering, closing gets substantially more expensive.",
    ko_gegenstelle: "With which node",
    ko_gegenstelle_d: "The pubkey of the node you want to share the channel with — 66 characters. You may add the address (“@host:9735”), but you need not: without it your node looks it up in its own graph.",
    ko_knoepfe_d: "Three things with the same pubkey. “Inspect peer” only asks your own graph — nobody finds out. “Connect” opens a plain line: no channel, no satoshi. You do not need it for a channel; “Open a channel” does that by itself.",
    ko_betrag: "Channel size (sat)",
    ko_betrag_d: "How much you put into the channel. One big channel to a well connected, stable peer is worth more than many small ones.",
    ko_knapp: "This channel is on the small side. At least {n} sat is recommended — and the reason is not economic: if on-chain fees rise, closing eventually costs more than the channel holds. Whoever cannot close can no longer punish a cheating counterparty either, and that is exactly what a channel's security rests on. For paying and receiving it is still fine; you should just know.",
    ko_tempo_d: "How quickly the opening should confirm. The channel only becomes usable once it is in a block.",
    ko_privat: "Private channel",
    ko_privat_d: "Appears in no graph. Nobody routes through it — and at that point your node is not a connection but a dead end. Only pick this if you mean it.",
    ko_pruefen: "Work it out",
    ko_oeffnen: "Open channel",
    ko_gebraucht: "Needed",
    ko_guthaben: "In the wallet",
    ko_reicht: "That is enough. After opening it takes a few confirmations until the channel is usable.",
    ko_fehlt: "{n} sat short. Deposit on-chain first — your deposit address is under “Wallet”.",
    ko_erst_pruefen: "Work it out first. The button opens once the balance is enough.",
    ko_laeuft: "Opening — one moment.",
    ko_fertig: "The channel is being opened. Funding: {txid}. Once it confirms it shows up in the list.",
    kanal_zu_klein: "A channel needs at least {einzelheit} sat.",
    kanal_abgelehnt: "Your node refused that: {einzelheit}",
    rechnung_unlesbar: "That invoice could not be read: {einzelheit}",
    zahlung_gescheitert: "The payment did not get through: {einzelheit}",
    zahlung_unklar: "No answer within the waiting time. The payment may still be on its way — do NOT repeat it, check the channels instead.",
    sendung_unklar: "No answer within the waiting time. The transfer may still be on its way — do NOT send again, check under Movements whether it is there.",
    kanal_unklar: "No answer within the waiting time. The operation may still be running — do NOT repeat it, check the channel list first.",
    betrag_fehlt: "This invoice names no amount. Enter one.",
    sd_titel: "Send",
    sd_lead: "On-chain, out of your node's wallet, to an ordinary Bitcoin address. What sits in channels cannot go this way — it returns to the chain only when a channel closes. A Lightning invoice (lnbc…) does not belong here; use Pay instead.",
    wg_titel: "What your node has learned about routes",
    wg_lead: "For each pair of peers LND remembers up to which amount a forward carried and from which amount it failed — and picks routes accordingly later. If “failed from” sits just above “carried up to”, the route is not broken but empty. That is a liquidity question, and it can be fixed.",
    wg_zahlen: "{paare} pairs remembered · {fehl} with a failure · {erfolg} with a success",
    wg_leer: "Nothing learned yet. This fills up with every payment that runs through your node or starts at it.",
    wg_von: "from",
    wg_nach: "to",
    wg_trug: "carried up to",
    wg_fehl: "failed from",
    wg_wann: "last",
    wg_nicht_abrufbar: "Your node is not handing out its route knowledge right now.",
    wegwissen_nicht_abrufbar: "Your node is not handing out its route knowledge right now.",
    nb_knopf: "Raise the fee",
    nb_laeuft: "Attaching …",
    nb_erklaerung: "This transfer is still waiting. Raising the fee here means: your node attaches a second transaction to your own change, so that a miner can only take both together. The first one does not go away — and the second one costs extra.",
    nb_fertig: "Attached at {satz} sat/vB. At most {hoechstens} sat in fees. Both transactions confirm together.",
    nb_nicht_moeglich: "This transfer cannot be bumped: everything went out, so there is no change of this node in it to attach anything to.",
    nachbessern_abgelehnt: "Your node refused to raise the fee: {einzelheit}",
    sd_warnung: "A sent transaction cannot be called back. Check the address character by character — beginning AND end. If an answer ever fails to arrive, do NOT send again: look under Blocks or Mempool first to see whether it is already on its way.",
    sd_adresse: "Recipient address",
    sd_adresse_d: "A Bitcoin address. Best pasted from the clipboard, then compare both ends.",
    sd_betrag: "Amount in satoshi",
    sd_betrag_d: "At least 546 satoshi. Below that the network will not accept the output — it would be worth less than spending it later costs.",
    sd_alles: "Send everything",
    sd_alles_d: "Empties the on-chain wallet; the fee comes off the amount. The amount field stays empty then.",
    sd_tempo: "How urgent is it?",
    sd_tempo_d: "The rates come from your own node, not from someone else's service.",
    sd_tempo_schnell: "Urgent",
    sd_tempo_schnell_d: "Aims for the next block.",
    sd_tempo_normal: "Normal",
    sd_tempo_normal_d: "Aims for the next three blocks — about half an hour.",
    sd_tempo_guenstig: "Cheap",
    sd_tempo_guenstig_d: "Aims for the next six blocks — about an hour.",
    sd_pin_d: "Sending is the action the PIN guards.",
    sd_schaetzen: "What does it cost?",
    sd_senden: "Send now",
    sd_kosten: "Fee: {gebuehr} sat at {satz} sat/vB. Check the address once more, then press Send.",
    sd_kosten_alles: "At {satz} sat/vB. Only your node knows how large the fee turns out — with “send everything” it comes off the amount. Check the address once more, then press Send.",
    sd_erst_schaetzen: "First “What does it cost?” — that also checks the address.",
    sd_unterwegs: "On its way. This is the transaction id; you can watch it under Mempool and Blocks.",
    adresse_fehlt: "Without a recipient address nothing goes out.",
    betrag_zu_klein: "At least {mindestens} satoshi — below that the network will not accept the output.",
    alles_und_betrag: "Either an amount or “send everything”. Both together would be guesswork, and nothing is guessed here.",
    tempo_unbekannt: "There is no such speed.",
    keine_gebuehrenschaetzung: "Your node cannot estimate the fee right now — it needs a filled mempool for that. Straight after a restart this takes a few minutes. Nothing is sent without an estimate: a guessed rate would either be too expensive or leave the payment sitting for days.",
    senden_abgelehnt: "Your node refused this: {einzelheit}",
    wallet_gesperrt: "Your wallet is shut. Unlock it under Setup first.",
    pin_existiert: "This device already has a PIN. Changing it needs the old one.",
    pin_nur_ziffern: "A PIN is made of digits.",
    pin_laenge: "Five to twelve digits.",
    pin_zu_einfoermig: "The same digit six times is not a PIN.",
    pin_ist_eine_reihe: "A run like 123456 is the first thing any attacker tries — forwards and backwards.",
    pin_falsch: "That PIN does not fit.",
    wallet_nicht_gesperrt: "For that the wallet has to be shut — only while unlocking can LND check whether the password is right. Lock it first with the button next to it.",
    entsperrweg_unbekannt: "There is no such way.",
    entsperrdatei_fehlt: "The unlock file cannot be read. While that is so, SatoshiCortex cannot reach the wallet password.",
    ew_titel: "How your wallet opens again",
    ew_lead: "Here you can change the way without creating the wallet anew. What applies right now is shown below.",
    ew_jetzt: "Currently set up",
    ew_jetzt_aus: "You type the wallet password after every restart.",
    ew_jetzt_merken: "SatoshiCortex remembers the wallet password for as long as it runs.",
    ew_jetzt_datei: "Your node unlocks itself; the wallet password sits in plain text next to the wallet.",
    ew_noch_nicht_gemerkt: "Nothing is remembered right now — SatoshiCortex has restarted since. The next time you unlock, it will remember the password again.",
    ew_wechseln: "Change the way",
    ew_passwort: "Your current wallet password",
    ew_passwort_d: "Only needed for “unlock by itself”: there your password goes onto the disk in plain text, and a wrong one would leave LND hanging on its next start. So LND checks it itself — and for that the wallet has to be shut once. Lock it with the button below; afterwards you can open it again right here.",
    ew_gewechselt: "Changed.",
    passwort_fehlt: "Without a password the wallet stays shut.",
    anmeldung_fehlgeschlagen: "Username or password is incorrect.",
    zu_viele_versuche: "Too many failed attempts. Please try again in five minutes.",
    anmeldung_noetig: "Please sign in first.",
    sitzung_abgelaufen: "Your session has expired. Please sign in again.",
    unverschluesselt: "This connection is not encrypted — your password travels in the clear. Acceptable on your own home network; if other devices share it, configure a certificate in your .env.",
    ablage_nicht_bereit: "The folder {pfad} is not writable, so no account can be created. Check PUID and PGID in your .env — on UGREEN and Synology devices PGID=10 belongs there — and make sure both data folders belong to that identity.",
    einrichtung_abgeschlossen: "Setup has already been completed.",
    antwort_zu_gross: "That input is too large.",
    err_net: "The application isn't responding. Is the container still running?",
    err_anzeige: "The data arrived, but rendering it failed. The exact error is below — please report it.",
    nf_title: "The node isn't answering",
    nf_lead: "The interface is running, but the service behind it isn't answering. That happens while bitcoind flushes its cache — then it takes a few minutes. If it stays that way, the container is stopped or the route to it leads somewhere else.",
    nf_erneut: "Try again",
    gb: "GB",
  },
};

let LANG = localStorage.getItem("satcortex-lang")
  || ((navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en");
if (!I18N[LANG]) LANG = "en";

const t = (k, vars) => {
  let s = (I18N[LANG] && I18N[LANG][k]) || I18N.en[k] || k;
  if (vars) for (const [n, v] of Object.entries(vars)) s = s.split("{" + n + "}").join(v);
  return s;
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function applyI18n() {
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  // Nur eigene, fest eingebaute Texte -- niemals Serverdaten.
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  // Uebersetzbare ATTRIBUTE. Bis zum 10.09.2026 gab es das nicht -- und
  // deshalb las ein Vorleser einem englischen Nutzer "Abschnitte" vor und
  // einem deutschen "Language". Texte, die niemand SIEHT und jeder HOERT,
  // der auf einen Vorleser angewiesen ist.
  //
  // Form: data-i18n-attr="aria-label=nav_abschnitte", mehrere mit ";".
  $$("[data-i18n-attr]").forEach((el) => {
    for (const paar of (el.dataset.i18nAttr || "").split(";")) {
      const [attr, schluessel] = paar.split("=");
      if (attr && schluessel) el.setAttribute(attr.trim(), t(schluessel.trim()));
    }
  });
  $$("[data-setlang]").forEach((b) => b.classList.toggle("active", b.dataset.setlang === LANG));
  document.documentElement.lang = LANG;
}

/* ── Schnittstelle ──────────────────────────────────────────────────────── */
// Pfade des Anmeldetors. Ein 401 heisst dort "Passwort falsch" und nich
// "Sitzung weg" -- die duerfen nicht in die Weiche unten laufen.
const TOR_PFADE = ["/zustand", "/anmelden", "/konto/anlegen", "/abmelden"];

// Wie lange die Oberflaeche auf eine Antwort wartet.
//
// Ohne Zeitlimit wartet fetch, bis der Browser von sich aus aufgibt -- bei
// Safari ueber eine Minute. Bei einem Takt von zehn Sekunden stapeln sich
// die Anfragen dann, und eine haengende legt die Ansicht still, die auf sie
// wartet. Das Backend deckelt seine Kettenlage auf fuenfzehn Sekunden;
// fuenfundzwanzig lassen ihr Luft und geben trotzdem irgendwann auf.
const FRIST_MS = 25000;

/* Die Frist fuer alles, was Geld bewegt.

   DER BEFUND VOM 22.09.2026, beim Audit der Geldwege: hier galt ueberall die
   25 Sekunden oben. Der Server wartet beim Zahlen aber bis zu 80 -- LNDs
   sechzig plus zwanzig Luft -- und antwortet dann mit "zahlung_unklar":
   "kann trotzdem unterwegs sein, NICHT wiederholen, sondern nachsehen".

   Dieser Text war damit unerreichbar. Was ein Mensch sah, war "Fehler", ueber
   eine Zahlung, die in diesem Augenblick lief. Ein Kommentar zwei Zeilen
   neben dem Aufruf sagte es sogar: "Eine Zahlung kann bis zu einer Minute
   unterwegs sein."

   Die Wache dazu steht in test_oberflaeche.py und vergleicht diese Zahl mit
   der des Servers. */
const FRIST_GELD_MS = 95000;

/* Die Frist fuer die Kacheln -- den groessten Abruf der Anwendung.

   DER BEFUND VOM 23.09.2026 aus dem Betrieb: "brauch ich immer 5 mal klicken
   im schnitt damit was geht". Bei 83.000 wartenden Transaktionen brauchte der
   Server laenger als die 25 Sekunden oben; Core bekommt fuer den Strom bis zu
   KACHEL_RPC_ZEITLIMIT_S (45 s) Schweigen zugestanden. Der Browser gab auf und
   zeigte den Sammeltext, der Server rechnete weiter -- und jeder neue Klick
   stellte einen zweiten Abruf daneben.

   Die Wache dazu steht in test_oberflaeche.py, neben der fuer das Geld. */
const FRIST_KACHELN_MS = 120000;

/* Was ein misslungener Geldweg anzeigt -- und ob der Knopf wieder darf.

   Gibt false zurueck, wenn NICHTS ENTSCHIEDEN ist: dann bleibt der Knopf zu.
   "Nicht wiederholen" im Text zu schreiben und das Wiederholen im selben
   Atemzug wieder anzubieten, waere eine halbe Warnung. */
function geldfehler(e, meldung, unklar) {
  if (e && e.abgemeldet) return false;
  // Zwei Wege, auf denen kein Bescheid kommt: die Oberflaeche bricht ab
  // (netzfehler), oder der Server sagt selbst, dass er es nicht weiss (504).
  if (e && (e.netzfehler || e.status === 504)) {
    const d = (e && e.detail) || {};
    meldung.textContent = t(d.meldung || unklar, d);
    return false;
  }
  const d = (e && e.detail) || {};
  meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  // Der Server verlangt eine PIN, die Oberflaeche wusste nichts davon --
  // etwa weil sie in einem anderen Reiter eingerichtet wurde. Dann den
  // Stand neu holen: das Feld erscheint, und die Meldung steht nicht vor
  // einem Formular, in das man sie gar nicht eintragen kann.
  if (d.meldung === "pin_noetig") pinLaden();
  return true;
}
// Die Erreichbarkeitsmessung baut echte Verbindungen ueber Tor auf: je
// Adresse bis zu einer halben Minute, und es koennen mehrere sein.
const FRIST_MESSUNG_MS = 180000;

async function api(pfad, methode = "GET", koerper, frist = FRIST_MS) {
  let antwort;
  try {
    antwort = await fetch("/api" + pfad, {
      method: methode,
      headers: koerper ? { "content-type": "application/json" } : undefined,
      body: koerper ? JSON.stringify(koerper) : undefined,
      // AbortSignal.timeout gibt es seit Safari 16. Fehlt es, bleibt es beim
      // bisherigen Verhalten -- kein Grund, deswegen gar nicht zu laufen.
      signal: typeof AbortSignal !== "undefined" && AbortSignal.timeout
        ? AbortSignal.timeout(frist) : undefined,
    });
  } catch (e) {
    // Abbruch und Netzfehler sehen fuer den Aufrufer gleich aus: es kam
    // keine Antwort. Nur die Beschriftung unterscheidet sich.
    const f = new Error(e && e.name === "TimeoutError"
      ? "Zeitlimit" : "Keine Verbindung");
    f.zeitlimit = !!(e && e.name === "TimeoutError");
    f.netzfehler = true;
    throw f;
  }
  const daten = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    const f = new Error(
      typeof daten.detail === "string" ? daten.detail : antwort.statusText);
    f.detail = daten.detail;
    f.status = antwort.status;
    // Die Sitzung lebte frueher nur im Arbeitsspeicher des Containers: nach
    // jedem Neustart antwortete der Server einer offenen Seite mit 401, und
    // die Oberflaeche machte daraus "die Anwendung antwortet nicht" -- die
    // Meldung, die im Speicher-Schritt in die voellig falsche Richtung zeigte.
    // Ein 401 ist keine Stoerung, sondern eine Aufforderung: zurueck ans Tor.
    if (antwort.status === 401 && !TOR_PFADE.includes(pfad)) {
      f.abgemeldet = true;
      sitzungVerloren();
    }
    throw f;
  }
  return daten;
}

let SITZUNG_VERLOREN = false;

function sitzungVerloren() {
  if (SITZUNG_VERLOREN) return;   // bei mehreren offenen Aufrufen nur einmal
  SITZUNG_VERLOREN = true;
  KONTO_VORHANDEN = true;         // ohne Konto gaebe es keine abgelaufene Sitzung
  zeigeTor();
  $("#g-err").textContent = t("sitzung_abgelaufen");
}

/* ── Zustand ────────────────────────────────────────────────────────────── */
const SCHRITTE = ["willkommen", "speicher", "leistung", "netz", "wallet",
                  "konto", "fertig"];
const PROFILE = {
  sparsam:   { mb: 1500, verbindungen: 40 },
  mittel:    { mb: 2500, verbindungen: 80 },
  voll:      { mb: 4000, verbindungen: 125 },
};

const S = {
  schritt: "willkommen",
  profil: "mittel",
  upload: 300,
  tor: true,
  ipv4: true,
  ipv6: true,
  pause: true,
  ankuendigen: true,
  // Die Hauptwahl. Vorgabe "hybrid": Tor UND Clearnet -- der Knoten, der im
  // Netz am knappsten ist, weil er beide Welten verbindet.
  // LEER, und das ist der Punkt. Bis zum 09.09.2026 stand hier "hybrid",
  // und im Markup war derselbe Knopf vorausgewaehlt: wer den Assistenten
  // durchklickte, ohne zu lesen, veroeffentlichte damit seine IP-Adresse im
  // Lightning-Graphen -- ohne je eine Entscheidung getroffen zu haben.
  // Genau das ist der Betreiber passiert. Diese Wahl bekommt keine Vorgabe.
  sichtbarkeit: "",
  rpcAn: false,
  rpcNetz: "",
  speicher: null,
  adresse: "",
  weiterErlaubt: true,
};

/* ── Darstellung ────────────────────────────────────────────────────────── */
function zeichneStepper() {
  const el = $("#stepper");
  el.textContent = "";
  const jetzt = SCHRITTE.indexOf(S.schritt);
  SCHRITTE.forEach((name, i) => {
    const d = document.createElement("div");
    d.className = "step" + (i < jetzt ? " done" : i === jetzt ? " now" : "");
    const bar = document.createElement("div"); bar.className = "bar";
    const lbl = document.createElement("div"); lbl.className = "lbl";
    lbl.textContent = t("st_" + name);
    d.append(bar, lbl); el.append(d);
  });
}

function zeigeSchritt() {
  $$(".step-body").forEach((el) =>
    el.classList.toggle("hidden", el.dataset.step !== S.schritt));
  $("#btn-back").classList.toggle("hidden", S.schritt === "willkommen");
  $("#btn-next").textContent = S.schritt === "fertig" ? t("start") : t("next");
  $("#btn-next").disabled = !S.weiterErlaubt;
  $("#err").textContent = "";
  zeichneStepper();
}

function zeile(schluessel, wert, klasse) {
  const d = document.createElement("div"); d.className = "stat";
  const k = document.createElement("span"); k.className = "k"; k.textContent = schluessel;
  const v = document.createElement("span"); v.className = "v " + (klasse || ""); v.textContent = wert;
  d.append(k, v); return d;
}

function hinweis(text, art) {
  const d = document.createElement("div");
  d.className = "note" + (art ? " " + art : "");
  d.textContent = text;                       // bewusst textContent
  return d;
}

/* ── Schritt: Speicher ──────────────────────────────────────────────────── */
async function ladeSpeicher() {
  const ziel = $("#s-result");
  ziel.textContent = "";
  ziel.append(Object.assign(document.createElement("p"),
    { className: "dim", textContent: t("s_checking") }));
  try {
    const d = await api("/speicher");
    S.speicher = d;
    ziel.textContent = "";
    for (const [rolle, name] of [["bulk", "s_bulk"], ["fast", "s_fast"]]) {
      const p = d[rolle];
      const art = p.bewertung === "genug" ? "ok" : p.bewertung === "knapp" ? "warn" : "bad";
      const box = document.createElement("div");
      box.className = "panel"; box.style.marginBottom = "12px";
      const h = document.createElement("h3"); h.textContent = t(name);
      box.append(h);
      box.append(zeile(t("s_free"), p.frei_gb + " " + t("gb")));
      box.append(zeile(t("s_needed"), p.empfohlen_gb + " " + t("gb")));
      box.append(hinweis(t(p.meldung, p.werte), art));
      ziel.append(box);
    }
    if (d.meldung_gleiche_platte)
      ziel.append(hinweis(t(d.meldung_gleiche_platte), "warn"));
    S.weiterErlaubt = d.weiter_moeglich;
  } catch (e) {
    if (e && e.abgemeldet) { S.weiterErlaubt = false; $("#btn-next").disabled = true; return; }
    // NICHT pauschal "der Server antwortet nicht" behaupten. Dieser Block
    // faengt auch Fehler beim Zeichnen -- und dann zeigt die Meldung auf den
    // Container, waehrend der Fehler in der Oberflaeche sitzt. Genau das ha
    // beim Rollout zweimal in die falsche Richtung gefuehrt.
    ziel.textContent = "";
    const netzproblem = e instanceof TypeError;   // fetch selbst gescheiter
    ziel.append(hinweis(netzproblem ? t("err_net") : t("err_anzeige"), "bad"));
    if (!netzproblem) {
      const d = document.createElement("pre");
      d.className = "dim"; d.style.cssText = "font-size:12px;overflow-x:auto;margin-top:8px";
      d.textContent = String(e && e.stack ? e.stack : e);
      ziel.append(d);
      console.error("SatoshiCortex: Fehler beim Zeichnen des Speicher-Schritts", e);
    }
    S.weiterErlaubt = false;
  }
  $("#btn-next").disabled = !S.weiterErlaubt;
}

/* ── Schritt: Leistung ──────────────────────────────────────────────────── */
function zeichneProfile() {
  const ziel = $("#l-profiles"); ziel.textContent = "";
  for (const [key, label] of [["sparsam", "l_sparsam"], ["mittel", "l_mittel"], ["voll", "l_voll"]]) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice" + (S.profil === key ? " sel" : "");
    const titel = document.createElement("div"); titel.className = "t";
    titel.textContent = t(label);
    const d = document.createElement("div"); d.className = "d";
    d.textContent = t(label + "_d");
    b.append(titel, d);
    b.addEventListener("click", () => { S.profil = key; zeichneProfile(); vorschau(); });
    ziel.append(b);
  }
}

async function vorschau() {
  $("#l-upload-val").textContent =
    S.upload === 0 ? t("l_unlimited") : S.upload + " " + t("gb");
  try {
    const d = await api("/leistung/vorschau", "POST", {
      speichergrenze_mb: PROFILE[S.profil].mb,
      upload_gb_pro_monat: S.upload,
      verbindungen: PROFILE[S.profil].verbindungen,
      tor_aktiv: S.tor,
    });
    const n = $("#l-upload-note");
    n.className = "note" + (d.upload_unbegrenzt ? " warn" : "");
    n.textContent = t(d.meldung_upload, { upload_gb: d.upload_gb }) + "  " +
      t("l_cache", { a: d.dbcache_erstsync_mb, b: d.dbcache_betrieb_mb });
  } catch (e) { /* Vorschau ist Beiwerk -- ohne sie geht es weiter */ }
}

/* ── Schritt: Netz ──────────────────────────────────────────────────────── */
function zeichneNetz() {
  const ziel = $("#n-ports"); ziel.textContent = "";
  const p = document.createElement("div"); p.className = "panel";
  for (const [port, key] of [["8333", "n_p_btc"], ["9735", "n_p_ln"],
                             ["9911", "n_p_wt"]]) {
    const d = document.createElement("div"); d.className = "stat";
    const k = document.createElement("span"); k.className = "k"; k.textContent = t(key);
    const v = document.createElement("span"); v.className = "v"; v.textContent = port;
    d.append(k, v); p.append(d);
  }
  ziel.append(p);
  ziel.append(hinweis(t("n_forward"), ""));
  const knopf = $(`input[name="n-sicht"][value="${S.sichtbarkeit}"]`);
  if (knopf) knopf.checked = true;
  $("#n-tor").checked = S.tor;
  $("#n-ipv4").checked = S.ipv4;
  $("#n-ipv6").checked = S.ipv6;
  $("#n-pause").checked = S.pause;
  $("#n-ankuendigen").checked = S.ankuendigen;
  $("#n-adresse").value = S.adresse;
  $("#n-adresse").placeholder = t("e_adresse_beispiel");
  netzwegeFolgen();
}

// Was aus den Schaltern folgt -- an EINER Stelle, damit Assistent und
// Einstellungen nicht zwei Meinungen dazu haben koennen.
function netzwegeFolgen() {
  // Die Wahl oben ist das Grobe, die Haekchen sind die Feinheit darunter --
  // und in "nur ueber Tor" gibt es nichts fein einzustellen. Gesperrt, nicht
  // abgehakt: das Haekchen ist die Voreinstellung des Nutzers, und dass sie
  // gerade nicht gilt, sagt die Zeile darunter. (In den Einstellungen kostete
  // genau dieser Unterschied einmal die IPv4-Wahl -- ein Ausflug nach "nur
  // ueber Tor" und zurueck liess den Knoten ohne sie stehen.)
  const nurTor = S.sichtbarkeit === "tor";
  const still = S.sichtbarkeit === "still";
  $("#n-ipv4").disabled = nurTor;
  $("#n-ipv6").disabled = nurTor;
  $("#n-ankuendigen").disabled = nurTor || still;
  const folge = $("#n-sicht-folge");
  folge.textContent = !S.sichtbarkeit ? t("lnsicht_waehlen")
                    : nurTor ? t("lnsicht_folge_tor")
                    : still ? t("lnsicht_folge_still")
                    : t("lnsicht_folge_hybrid");
  folge.classList.toggle("hidden", !folge.textContent);
  // Die Pause gehoert zu Tor. Ohne Tor gibt es nichts zu pausieren, also
  // wird der Schalter gesperrt statt versteckt: sonst sieht es aus, als
  // waere die Einstellung verloren.
  $("#n-pause").disabled = !S.tor;
  $("#n-pause-zeile").classList.toggle("dim", !S.tor);
  $("#n-adresse").disabled = !S.ankuendigen || nurTor || still;
  // Gezaehlt wird, was WIRKLICH gilt -- nicht, was angehakt ist. In "nur
  // ueber Tor" zaehlen IPv4 und IPv6 nicht mit, auch wenn ihre Haekchen noch
  // stehen. Wer dort zusaetzlich Tor abschaltet, haette sonst einen Knoten
  // ohne jeden Weg, und die Warnung bliebe aus.
  // Ohne getroffene Wahl geht es nicht weiter. Eine Vorauswahl waere hier
  // bequem und falsch: sie entscheidet ueber die Auffindbarkeit des eigenen
  // Anschlusses, und das darf nicht nebenbei passieren.
  const ohneWahl = !S.sichtbarkeit;
  const kein = ohneWahl || !(S.tor || (!nurTor && (S.ipv4 || S.ipv6)));
  const warnung = $("#n-warnung");
  warnung.className = "note" + (kein ? " warn" : "");
  warnung.textContent = kein ? t("kein_weg_ins_netz") : t("n_note");
  // Weitergehen mit einem Knoten ohne jeden Weg ins Netz waere kein
  // Freiheitsgrad, sondern ein Knoten, der nichts tun kann.
  S.weiterErlaubt = !kein;
  $("#btn-next").disabled = kein;
}

/* ── Schritt: Wallet-Software ───────────────────────────────────────────────
   Hier wird nur ENTSCHIEDEN. Die Zugangsdaten entstehen erst mit der
   Konfiguration, also im naechsten Schritt -- ein leeres Feld mit der
   Ueberschrift "Das traegst du in deine Wallet ein" waere eine Zusage, die
   der Assistent hier noch nicht halten kann. Stattdessen steht da, wo sie
   danach zu finden sind. */
function zeichneWallet() {
  $("#n-rpc-an").checked = S.rpcAn;
  const feld = $("#n-rpc-netz");
  feld.value = S.rpcNetz;
  feld.placeholder = heimnetzVorschlag() || "192.168.178.0/24";
  walletFolgen();
}

function walletFolgen() {
  $("#n-rpc-netz").disabled = !S.rpcAn;
  const fehlt = heimnetzFehlt("#n-rpc-an", "#n-rpc-netz");
  S.weiterErlaubt = !fehlt;
  $("#btn-next").disabled = fehlt;
  $("#n-rpc-fehlt").classList.toggle("hidden", !fehlt);
  // Der Port ist kein Nebensatz: ohne RPC_BIND in der .env bleibt die
  // Freigabe wirkungslos, und der Nutzer sucht den Fehler in der Wallet.
  $("#n-rpc-port").classList.toggle("hidden", !S.rpcAn);
  $("#n-rpc-danach").classList.toggle("hidden", !S.rpcAn);
  $("#n-rpc-aus").classList.toggle("hidden", S.rpcAn);
}

/* ── Schritt: Fertig ────────────────────────────────────────────────────── */
function zeichneZusammenfassung() {
  const ziel = $("#f-summary"); ziel.textContent = "";
  const p = document.createElement("div"); p.className = "panel";
  p.append(zeile(t("l_title"), t("l_" + S.profil)));
  p.append(zeile(t("l_upload"),
    S.upload === 0 ? t("l_unlimited") : S.upload + " " + t("gb")));
  // Frueher stand hier nur "Tor ✓". Seit die Sichtbarkeit die Hauptwahl ist,
  // waere das die Nebensache an der Stelle der Hauptsache.
  p.append(zeile(t("lnsicht_titel"), t("lnsicht_" + S.sichtbarkeit)));
  p.append(zeile("Tor", S.tor ? "✓" : "—"));
  p.append(zeile(t("wsw_titel"),
    S.rpcAn ? (S.rpcNetz.trim() || heimnetzVorschlag() || "✓") : t("f_aus")));
  if (S.speicher) {
    p.append(zeile(t("s_bulk"), S.speicher.bulk.frei_gb + " " + t("gb") + " " + t("s_free")));
    p.append(zeile(t("s_fast"), S.speicher.fast.frei_gb + " " + t("gb") + " " + t("s_free")));
  }
  ziel.append(p);
  ziel.append(hinweis(t("f_start")));
}

/* ── Uebersicht ─────────────────────────────────────────────────────────── */
function menschenBytes(b) {
  // Frueher immer in GB. Am Anfang des Erstabgleichs liegen aber erst ein paar
  // Megabyte auf der Platte, und "0.0 GB" sieht aus, als passiere nichts --
  // waehrend im Protokoll die Bloecke nur so durchlaufen.
  // "0 MB" las sich wie eine Rundung -- also wie eine kaputte Anzeige.
  // Null Bytes sind null Bytes, und die Einheit sagt das auch.
  if (!b) return "0 B";
  // Unter tausend Byte in Byte. Seit die Kacheln einzelne Transaktionen
  // zeigen, kommt genau das vor: 226 Byte standen als "0 kB" da -- also
  // dieselbe Falle, vor der der Absatz darueber warnt, eine Groessenordnung
  // tiefer.
  if (b < 1e3) return Math.round(b) + " B";
  if (b < 1e6) return Math.round(b / 1e3) + " kB";
  const mb = b / 1e6;
  if (mb < 1000) return (mb < 10 ? mb.toFixed(1) : Math.round(mb)) + " MB";
  const gb = mb / 1000;
  return gb >= 1000 ? (gb / 1000).toFixed(2) + " TB" : gb.toFixed(1) + " GB";
}

function prozent(p) {
  // verificationprogress misst PRUEFARBEIT, nicht Bloecke. Die Bloecke von
  // 2009 enthalten je eine Transaktion, die von heute mehrere tausend --
  // nach 28.000 von 964.000 Bloecken sind darum erst 0,002 % der Arbei
  // getan. "0.00 %" ist richtig gerundet und trotzdem nichtssagend.
  if (p <= 0) return "0 %";
  if (p < 0.01) return "< 0,01 %".replace(",", LANG === "de" ? "," : ".");
  return p.toFixed(2) + " %";
}

function monatJahr(sekunden) {
  if (!sekunden) return "—";
  return new Date(sekunden * 1000).toLocaleDateString(
    LANG === "de" ? "de-DE" : "en-US", { year: "numeric", month: "long" });
}

function dauer(sekunden) {
  // Grob ist hier richtig: eine Restdauer auf die Minute genau anzugeben
  // taeuscht eine Genauigkeit vor, die eine Hochrechnung nicht hat.
  if (sekunden == null) return null;
  const tage = Math.round(sekunden / 86400);
  if (tage >= 1) return t(tage === 1 ? "d_tag" : "d_tage", { n: tage });
  const std = Math.round(sekunden / 3600);
  if (std >= 1) return t(std === 1 ? "d_stunde" : "d_stunden", { n: std });
  const min = Math.max(1, Math.round(sekunden / 60));
  return t(min === 1 ? "d_minute" : "d_minuten", { n: min });
}

function zahl(n) {
  // Tausenderpunkte je nach Sprache -- 963.597 liest sich anders als 963597.
  return (n || 0).toLocaleString(LANG === "de" ? "de-DE" : "en-US");
}

/* Was die Indizes gerade machen. Leer heisst "alles fertig" -- dann gehoert
   dort nichts hin. */
function indexZeile(k) {
  const idx = k.indizes;
  if (!idx) return "";                       // nicht abrufbar, nicht geraten
  const namen = Object.keys(idx);
  if (!namen.length) return t("d_index_aus");
  const offen = namen.filter((n) => !idx[n].fertig);
  if (!offen.length) return "";              // fertig ist der Normalfall
  return offen.map((n) => t("d_index_baut", {
    name: n, hoehe: zahl(idx[n].hoehe), ziel: zahl(k.hoehe || 0),
  })).join(" \u00b7 ");
}

async function zeigeUebersicht() {
  $("#wizard").classList.add("hidden");
  $("#app").classList.remove("hidden");
  // Vor der ersten Antwort stand hier nichts -- und wenn die erste Antwort
  // "bitcoind hat nicht geantwortet" war, stand da "Wird gestartet" in
  // Warnfarbe, samt "direkt nach der Einrichtung ist das normal". Bei jedem
  // Neuladen. Aus dem Betrieb, 02.09.2026: "bei einem refresh sieht das so aus,
  // als ob der ganze app container neu startet."
  //
  // Er startet nicht -- sein Protokoll zeigt ueber zehn Minuten mit
  // mehreren Neuladungen genau EINEN Startblock. Die Oberflaeche hat es nur
  // behauptet. "Ich habe noch nicht gefragt" ist ein dritter Zustand neben
  // "laeuft" und "antwortet nicht", und er gehoert auch so beschriftet:
  // neutral, ohne Warnfarbe.
  if (!UEBERSICHT_GESEHEN) {
    $("#d-phase").textContent = t("d_phase_laedt");
    $("#d-sub").textContent = t("d_sub_laedt");
    setzeHinweis("d_note_laedt", "");
  }
  let d;
  try {
    d = await api("/status");
  } catch (e) {
    // Standen schon Zahlen da, bleiben sie stehen -- sie sind ein paar
    // Sekunden alt und damit richtiger als ein Gedankenstrich. Beim ERSTEN
    // Aufruf steht dort aber "Wird geladen", und das duerfte sonst fuer
    // immer so bleiben.
    if (!UEBERSICHT_GESEHEN) {
      $("#d-phase").textContent = t("d_phase_getrennt");
      $("#d-sub").textContent = "";
      setzeHinweis("d_note_getrennt", "warn");
    }
    return;
  }
  UEBERSICHT_GESEHEN = true;
  zeigeTunzeile(d.naechster_schritt);

  const k = d.knoten;             // null, solange bitcoind nicht antworte

  // Die Karte hat ihren eigenen Takt: die Umrisse einmal, die Daten im
  // Minutenabstand. Bewusst NICHT abgewartet -- die Uebersicht soll nicht auf
  // eine Weltkarte warten muessen. Der Abgleichszustand geht mit, weil er
  // erklaert, warum "von aussen angenommen" gerade 0 ist.
  ladeKarte(false, !!(k && k.im_erstsync));
  // DER BEFUND VOM 21.09.2026 aus dem Betrieb: "der kurs von btc laedt
  // gefuehlt garnicht auf der uebersichts seite".
  //
  // Er lud dort nie. ladeKurs() LAESST die Uebersicht ausdruecklich zu --
  // ANSICHT !== "uebersicht" steht in seiner Abbruchbedingung --, gerufen
  // wurde es aber nur beim Wechsel nach News oder Rechner. Wer neu lud und
  // auf der Uebersicht blieb, sah dauerhaft einen Gedankenstrich; erst ein
  // Ausflug in eine andere Ansicht fuellte den Kasten.
  //
  // Ebenfalls nicht abgewartet: der Endpunkt liest nur aus dem
  // Zwischenspeicher, geholt wird im Waechter. Er kostet also nichts, und
  // die Uebersicht soll auch darauf nicht warten.
  ladeKurs();
  // Die Uhr der Kette. Rein gerechnet, aus Zahlen, die schon da sind --
  // deshalb kein Aufruf und kein Warten.
  zeichneBlockzeit(d.halbierung);
  // Die Auswertung sammelt erst nach dem Abgleich -- vorher gaebe es nichts
  // zu holen, und der Abruf waere Last fuer nichts.
  if (k) ladeBeitrag(false);
  // Lightning hat seinen eigenen Takt: der Zustand aendert sich selten, und
  // in der Uebersicht steht er gar nicht.
  ladeLightning(false);
  // Die Auswertung sammelt erst nach dem Abgleich. Vorher gaebe es nichts zu
  // holen -- der Abruf waere Last fuer nichts.
  if (k && !k.im_erstsync) ladeAuswertung(false);
  const feld = $("#d-sync");
  const balken = $("#d-bar");

  if (!k && d.knoten_grund === "ungefragt") {
    // Der Sammler im Backend war noch nicht durch -- das sind die ersten
    // Sekunden nach einem Neustart der Anwendung. "Wird gestartet" waere
    // hier eine Behauptung ueber bitcoind, ueber das wir noch gar nichts
    // wissen. Also derselbe neutrale Ladezustand wie beim ersten Aufruf.
    feld.classList.add("unbekannt");
    $("#d-phase").textContent = t("d_phase_laedt");
    $("#d-sub").textContent = t("d_sub_laedt");
    $("#d-pct").textContent = "—";
    balken.style.width = "";
    setzeHinweis("d_note_laedt", "");
  } else if (!k && d.knoten_grund === "beschaeftigt") {
    // bitcoind LAEUFT -- es kommt nur gerade nicht zum Antworten, weil es den
    // chainstate wegschreibt. Vorher stand hier dasselbe wie bei "gar nich
    // da": Fortschritt auf "—", Hinweis "wird gestartet". Es sah aus, als
    // starte der Dienst im Minutentakt neu. Er startet nie neu.
    //
    // Deshalb bleiben die Zahlen STEHEN. Sie sind ein paar Sekunden alt und
    // damit richtiger als ein Gedankenstrich.
    feld.classList.remove("unbekannt");
    $("#d-phase").textContent = t("d_phase_beschaeftigt");
    setzeHinweis("d_note_beschaeftigt", "");
  } else if (!k) {
    feld.classList.add("unbekannt");
    $("#d-phase").textContent = t("d_phase_start");
    $("#d-pct").textContent = "—";
    balken.style.width = "";
    $("#d-sub").textContent = t("d_sub_start");
    setzeHinweis("d_note_start", "warn");
  } else {
    feld.classList.remove("unbekannt");
    // Prozent aus verificationprogress: die Kopfzeilen sind nach Minuten da,
    // die Pruefarbeit laeuft danach noch tagelang weiter.
    const pct = k.fortschritt * 100;
    // Nicht auf 100 aufrunden, solange der Erstsync laeuft -- sonst steht da
    // tagelang "100 %" und der Nutzer wartet auf etwas, das schon fertig
    // aussieht.
    const gezeigt = k.im_erstsync ? Math.min(pct, 99.99) : 100;
    $("#d-pct").textContent = prozent(gezeigt);
    // Der Balken zeigt bewusst den Blockanteil, nicht die Pruefarbeit: sons
    // steht er tagelang sichtbar auf null, obwohl der Knoten laeuft.
    const blockanteil = k.kopfzeilen ? (k.hoehe / k.kopfzeilen) * 100 : 0;
    balken.style.width = Math.min(blockanteil, 100).toFixed(2) + "%";
    $("#d-phase").textContent = t(k.im_erstsync ? "d_phase_sync" : "d_phase_fertig");
    $("#d-sub").textContent = t(k.im_erstsync ? "d_sub_sync" : "d_sub_fertig", {
      hoehe: zahl(k.hoehe), kopf: zahl(k.kopfzeilen), belegt: menschenBytes(k.belegt_bytes),
      blockanteil: blockanteil.toFixed(1),
    });

    // Die anschaulichste Zahl waehrend des Abgleichs: nicht ein Prozentsatz,
    // sondern in welchem Jahr der Knoten gerade angekommen ist.
    // Festes Element statt .after(): die Uebersicht laedt alle zehn Sekunden
    // nach, ein angehaengter Knoten waere nach einer Stunde 360 Zeilen lang.
    const rest = d.tempo && dauer(d.tempo.rest_sekunden);
    if (k.im_erstsync) {
      const teile = [monatJahr(k.blockzeit)];
      if (d.tempo) teile.push(t("d_tempo", { bpm: zahl(d.tempo.bloecke_pro_minute) }));
      teile.push(rest ? t("d_restdauer", { dauer: rest }) : t("d_restdauer_unbekannt"));
      $("#d-sub2").textContent = teile.join(" · ");
    } else {
      // Nach dem Abgleich stand hier NICHTS -- und genau da fehlte die
      // Auskunft, die man dann braucht. SatoshiCortex schaltet txindex und
      // Blockfilter waehrend des Abgleichs ab und danach wieder ein; Core
      // baut sie dann stundenlang nach, und in dieser Zeit findet die
      // Transaktionssuche nichts. Aus dem Betrieb, 08.09.2026: "vielleicht liegt
      // es daran, dass das nicht geklappt hat."
      $("#d-sub2").textContent = indexZeile(k);
    }

    if (k.im_erstsync) setzeHinweis("d_note_sync", "");
    // null heisst "nicht gemessen". Weder "du bist Teilnehmer" noch "du bis
    // nur Zuschauer" darf daraus werden -- die zweite Aussage steht in
    // Warnfarbe und schickt jemanden in seinen Router.
    else if (k.erreichbar === null) setzeHinweis("d_note_unbekannt", "");
    else setzeHinweis(k.erreichbar ? "d_note_teilnehmer" : "d_note_zuschauer",
                      k.erreichbar ? "ok" : "warn");
  }

  // ---- Teilnahme
  //
  // Hier stand bis zum 01.09.2026 "Blockkette" -- und darin Blockhoehe,
  // Kopfzeilen, Angekommen bei, Tempo und Belegt. Alle fuenf stehen
  // WOERTLICH schon im Streifen darueber: "Block 810.958 von 965.059 ·
  // 586,4 GB auf der Platte / Oktober 2023 · 36,8 Bloecke/Minute". Ein
  // Kasten, der seinen eigenen Kopf wiederholt, ist keine Uebersicht,
  // sondern Fuellung.
  //
  // Uebrig bleibt die Frage, die man waehrend eines Abgleichs ueber Tage
  // wirklich hat und die oben NICHT beantwortet wird: bin ich dabei?
  const kette = $("#d-chain");
  if (k) {
    const netze = k.netze || {};
    const wege = [];
    for (const [schluessel, name] of [["ipv4", "IPv4"], ["ipv6", "IPv6"],
                                      ["onion", "Tor"]])
      if (netze[schluessel]) wege.push(`${netze[schluessel]}\u00d7 ${name}`);
    // Ein Gedankenstrich, keine erfundene Null. Bis zum 02.09.2026 stand
    // hier "0 von mir aufgebaut · 0 von aussen angenommen", sobald die
    // Abfrage nicht durchkam -- und das las sich wie ein Messwert.
    kennzahl(kette, "peers", t("d_k_peers"),
      k.verbindungen_aus === null || k.verbindungen_aus === undefined
        ? t("d_peers_unbekannt")
        : t("d_peers", { aus: k.verbindungen_aus, ein: k.verbindungen_ein }));
    kennzahl(kette, "netze", t("d_k_netze"), wege.length ? wege.join(" \u00b7 ") : "\u2014");
    textZeile(kette, "peers_hilfe", t("d_peers_hilfe"));
    // Es gibt neben Mainnet mehrere Testnetze, die in jeder Anzeige gleich
    // aussehen. Die Konfiguration setzt "chain=main" ausdruecklich; hier
    // wird gegengeprueft, was der Knoten SELBST meldet. Leer heisst
    // "gerade nicht feststellbar" und ist kein Anlass fuer eine Warnung.
    if (k.kette && k.kette !== "main") {
      const warnung = textZeile(kette, "fremdes_netz",
                                t("d_fremdes_netz", { netz: k.kette }));
      warnung.className = "note warn";
    }
    // Zeilen entfernen, die dieser Durchlauf nicht mehr gesetzt hat -- beim
    // ersten Laden nach dem Update also die fuenf gedoppelten.
    raeumeAuf(kette);
  }

  // ---- Mempool: gibt es erst nach dem Abgleich
  const mp = d.mempool;
  $("#d-mempool-panel").classList.toggle("hidden", !mp);
  if (mp) {
    const ziel = $("#d-mempool");
    kennzahl(ziel, "wartend", t("d_k_wartend"), t("d_tx", { n: zahl(mp.transaktionen) }));
    kennzahl(ziel, "belegung", t("d_k_belegung"), menschenBytes(mp.belegt_bytes)
      + " / " + menschenBytes(mp.grenze_bytes)
      + " (" + prozent(mp.auslastung * 100) + ")");
    kennzahl(ziel, "purge", t("d_k_purge"), t("d_satvb", { n: mp.purge_sat_vb }));
    kennzahl(ziel, "gebuehren", t("d_k_gebuehren"), mp.gebuehren_btc + " BTC");
    const lage = textZeile(ziel, "purge",
      t(mp.verwirft_gerade ? "d_purge_voll" : "d_purge_ruhig", { n: mp.purge_sat_vb }));
    lage.className = "note " + (mp.verwirft_gerade ? "warn" : "ok");
    lage.style.cssText = "margin-top:12px";
    textZeile(ziel, "purge_hilfe", t("d_purge_hilfe"));
    raeumeAuf(ziel);
  }

  // ---- Netz und Beitrag
  const netz = $("#d-netz");
  if (k) {
    const n = k.netze || {};
    const teile = [];
    for (const [schluessel, name] of [["ipv4", "IPv4"], ["ipv6", "IPv6"], ["onion", "Tor"]])
      if (n[schluessel]) teile.push(`${n[schluessel]}\u00d7 ${name}`);
    kennzahl(netz, "netze", t("d_k_netze"), teile.length ? teile.join(" · ") : "—");
    kennzahl(netz, "empfangen", t("d_k_empfangen"), menschenBytes(k.empfangen_bytes));
    kennzahl(netz, "gesendet", t("d_k_gesendet"), menschenBytes(k.gesendet_bytes));

    // Die eigenen Adressen. Steht hier nur die Onion-Adresse, kennt der Knoten
    // seine oeffentliche IP nicht -- dann findet ihn ueber Clearnet niemand,
    // egal ob der Port im Router offen ist.
    const adressen = (k.adressen || []).map((a) => `${a.adresse}:${a.port}`);
    const zeileA = kennzahl(netz, "adressen", t("d_k_adressen"),
      adressen.length ? adressen.join("\n") : t("d_keine_adresse"));
    const feld = zeileA.querySelector(".v");
    feld.style.cssText =
      "word-break:break-all;text-align:right;max-width:60%;white-space:pre-line";

    // Der Satz "waehrend des Abgleichs bleibt es wenig" stand hier fest
    // verdrahtet -- auch Wochen nach dem Abgleich, wo er nur noch in die
    // Irre fuehrt. Und der eigentliche Grund fuer des Betreibers Rueckfrage vom
    // 17.09.2026 stand ueberhaupt nicht da: die Zahl hier gilt seit dem
    // Start von bitcoind, die Aufteilung darunter nur fuer die gerade
    // verbundenen Gegenstellen. Zwei Bezugsgroessen, untereinander, ohne
    // ein Wort dazu -- das MUSS widerspruechlich aussehen.
    textZeile(netz, "beitrag_hilfe",
              t(k.im_erstsync ? "d_gesendet_hilfe_sync" : "d_gesendet_hilfe"));
    raeumeAuf(netz);
  }

  // ---- Dienste
  const ziel = $("#d-services");
  d.dienste.forEach((dienst) => {
    const r = kennzahl(ziel, dienst.name, dienst.name, t("sv_" + dienst.zustand));
    const links = r.querySelector(".k");
    let punkt = links.querySelector(".dot");
    if (!punkt) {
      punkt = document.createElement("span");
      punkt.style.marginRight = "8px";
      links.prepend(punkt);
    }
    punkt.className = "dot " + (dienst.zustand === "freigegeben" ? "ok"
      : dienst.zustand === "wartet" ? "warn" : "idle");
  });
  raeumeAuf(ziel);
}

// Bewusst NICHT "zeile": den Namen gibt es im Assistenten schon, mit anderer
// Signatur. Eine zweite Deklaration ueberschreibt die erste stillschweigend --
// der Speicher-Schritt brach danach mit "Die Anwendung antwortet nicht" ab,
// obwohl der Server sauber mit 200 antwortete.
function kennzahl(ziel, kennung, name, wert) {
  // Die Uebersicht laedt alle zehn Sekunden nach. Wuerde sie dabei ihre
  // Elemente wegwerfen und neu bauen, verloere man alle zehn Sekunden
  // Scrollposition, Textauswahl und Tastaturfokus -- die Seite wirkt dann,
  // als lade sie staendig neu. Deshalb wird eine vorhandene Zeile
  // wiederverwendet und nur ihr Wert gesetzt.
  //
  // Die Kennung ist bewusst NICHT die Beschriftung. Frueher war sie es, und
  // beim Sprachwechsel passte damit keine vorhandene Zeile mehr: alle vier
  // Zeilen wurden neu angehaengt -- hinter den Erklaerungstext, der stehen
  // blieb -- und die alten raeumte raeumeAuf() weg. Der Kasten sortierte sich
  // dabei sichtbar um. Eine Kennung, die keine Uebersetzung kennt, kann das
  // nicht passieren.
  let r = [...ziel.children].find((k) => k.dataset && k.dataset.k === kennung);
  if (!r) {
    r = document.createElement("div");
    r.className = "stat";
    r.dataset.k = kennung;
    const a = document.createElement("span"); a.className = "k";
    const b = document.createElement("span"); b.className = "v";
    r.append(a, b);
    ziel.append(r);
  }
  // Die Beschriftung bei JEDEM Durchlauf setzen, nicht nur beim Anlegen:
  // sonst bliebe sie nach dem Sprachwechsel in der alten Sprache stehen.
  const kopf = r.querySelector(".k");
  if (kopf.textContent !== String(name)) kopf.textContent = name;
  const feld = r.querySelector(".v");
  // Nur anfassen, wenn sich wirklich etwas geaendert hat: ein Schreibzugriff
  // beendet in manchen Browsern eine laufende Textauswahl.
  if (feld.textContent !== String(wert)) feld.textContent = wert;
  r.dataset.gesehen = "1";
  return r;
}

function raeumeAuf(ziel) {
  // Zeilen, die dieser Durchlauf nicht mehr gesetzt hat -- etwa "Bekannte
  // Kopfzeilen", sobald der Abgleich durch ist.
  for (const k of [...ziel.children]) {
    if (k.dataset && k.dataset.k && k.dataset.gesehen !== "1") k.remove();
    else if (k.dataset) delete k.dataset.gesehen;
  }
}

function textZeile(ziel, schluessel, text, klasse) {
  // Erklaerungstexte ebenso stabil halten wie die Kennzahlen.
  let p = [...ziel.children].find((k) => k.dataset && k.dataset.t === schluessel);
  if (!p) {
    p = document.createElement("p");
    p.dataset.t = schluessel;
    p.className = klasse || "dim";
    p.style.cssText = "font-size:12px;line-height:1.5;margin:6px 0 0";
    ziel.append(p);
  }
  if (p.textContent !== text) p.textContent = text;
  return p;
}

function setzeHinweis(schluessel, art) {
  const n = $("#d-note");
  n.className = "note" + (art ? " " + art : "");
  n.textContent = t(schluessel);
}


/* ── Ablauf ─────────────────────────────────────────────────────────────── */
async function beimBetreten() {
  S.weiterErlaubt = true;
  if (S.schritt === "speicher") { S.weiterErlaubt = false; await ladeSpeicher(); }
  if (S.schritt === "leistung") { zeichneProfile(); await vorschau(); }
  if (S.schritt === "netz") zeichneNetz();
  if (S.schritt === "wallet") zeichneWallet();
  if (S.schritt === "konto") {
    const b = $("#k-body"); b.textContent = "";
    b.append(hinweis(t("k_local")));
  }
  if (S.schritt === "fertig") zeichneZusammenfassung();
  zeigeSchritt();
}

async function weiter() {
  if (S.schritt === "fertig") return abschliessen();
  const i = SCHRITTE.indexOf(S.schritt);
  try { await api("/einrichtung/weiter", "POST", { antworten: momentaufnahme() }); }
  catch (e) { /* Der Fortschritt auf dem Server ist Beiwerk, der Ablauf zaehlt */ }
  S.schritt = SCHRITTE[Math.min(i + 1, SCHRITTE.length - 1)];
  await beimBetreten();
}

async function zurueck() {
  const i = SCHRITTE.indexOf(S.schritt);
  if (i === 0) return;
  // Wie beim Vorwaertsgehen: der Schrittzaehler auf dem Server ist
  // Beiwerk. Scheitert er, geht der Assistent trotzdem zurueck --
  // sonst saesse man in einem Schritt fest, den man verlassen wollte.
  try { await api("/einrichtung/zurueck", "POST"); } catch (e) { /* s.o. */ }
  S.schritt = SCHRITTE[i - 1];
  await beimBetreten();
}

function momentaufnahme() {
  return { profil: S.profil, upload_gb: S.upload, tor: S.tor };
}

async function abschliessen() {
  const btn = $("#btn-next"); btn.disabled = true;
  try {
    await api("/einrichtung/abschliessen", "POST", {
      speichergrenze_mb: PROFILE[S.profil].mb,
      upload_gb_pro_monat: S.upload,
      verbindungen: PROFILE[S.profil].verbindungen,
      tor_aktiv: S.tor,
      netz_ipv4: S.ipv4,
      netz_ipv6: S.ipv6,
      tor_pause_beim_abgleich: S.pause,
      externe_adresse: S.ankuendigen ? S.adresse : "",
      sichtbarkeit: S.sichtbarkeit,
      // Leer heisst zu. Der Server prueft das Netz noch einmal -- was hier
      // durchrutscht, landet sonst in einer Zeile, die bitcoind liest.
      rpc_heimnetz: heimnetzAusFeldern("#n-rpc-an", "#n-rpc-netz"),
    });
    await zeigeUebersicht();
  } catch (e) {
    if (e && e.abgemeldet) return;
    // Der Server schickt einen Schlüssel, keinen fertigen Satz.
    const d = e.detail;
    $("#err").textContent = (d && d.meldung) ? t(d.meldung) : e.message;
    btn.disabled = false;
  }
}

/* ── Ein Land aus der Naehe ─────────────────────────────────────────────────
   Nur unter dem Reiter Welt, und nur als Auflage: die Weltansicht darunter
   wird nicht angefasst. Aus dem Betrieb, 05.09.2026: "das darf nur unter dem
   Reiter Welt als Funktion zur Verfuegung stehen und darf sonst die Ansicht,
   die wir bis jetzt haben, nicht veraendern."

   Die Umrisse liegen als eigene Datei je Land bereit (regionen/DE.svg und so
   fort) und werden erst beim Klick geholt. 241 Laender waeren zusammen 14 MB
   -- geladen wird davon immer nur das eine, das jemand sehen will. */

let LAND_OFFEN = "";
const LAND_UMRISSE = new Map();     // Kuerzel -> SVG-Text, einmal geholt

function landkuerzelAus(ziel) {
  // Die Weltkarte fuehrt Flaechen als "l-DE" und Punkte als "p-SG".
  const el = ziel && ziel.closest ? ziel.closest("path[id], circle[id]") : null;
  const kennung = el && el.id;
  if (!kennung || !/^[lp]-[A-Z]{2}$/.test(kennung)) return "";
  return kennung.slice(2);
}

async function oeffneLand(kuerzel) {
  if (!kuerzel) return;
  LAND_OFFEN = kuerzel;
  const kasten = $("#welt-land");
  kasten.classList.remove("hidden");
  $("#wl-titel").textContent = landName(kuerzel) || kuerzel;
  $("#wl-stand").textContent = "";
  $("#wl-zeilen").textContent = "";
  $("#wl-rest").textContent = "";
  $("#wl-leer").textContent = t("wl_laedt");
  $("#wl-karte").textContent = "";
  // Die Ueberschriftszeile erst zeigen, wenn es Zeilen gibt. Solange nur
  // "wird geholt" dasteht, sieht eine Tabellenkopfzeile darunter aus wie
  // eine Tabelle, die gleich noch etwas nachliefert.
  $(".wl-tabelle").classList.add("hidden");

  let umriss = LAND_UMRISSE.get(kuerzel);
  if (umriss === undefined) {
    try {
      const r = await fetch("regionen/" + kuerzel + ".svg");
      umriss = r.ok ? await r.text() : "";
    } catch (e) {
      umriss = "";
    }
    LAND_UMRISSE.set(kuerzel, umriss);
  }
  // Zwischenzeitlich weitergeklickt? Dann gehoert das Ergebnis nicht mehr
  // hierher -- sonst steht Deutschland unter der Ueberschrift Australien.
  if (LAND_OFFEN !== kuerzel) return;
  $("#wl-karte").innerHTML = umriss || "";

  let d;
  try {
    d = await api("/karte/land/" + kuerzel);
  } catch (e) {
    // Auch beim Abmelden: der Kasten gehoert zu. Sonst bleibt "wird geholt"
    // fuer immer stehen -- und wer sich neu anmeldet, findet eine Auflage
    // vor, die ueber der Karte klebt und nichts sagt.
    if (e && e.abgemeldet) { schliesseLand(); return; }
    $("#wl-leer").textContent = t("wl_fehler");
    return;
  }
  if (LAND_OFFEN !== kuerzel) return;
  zeichneLand(d, !umriss);
}

// Wo eine Linie den Kartenrand betritt, wenn sie aus Richtung "richtung"
// auf den Punkt "ziel" zulaeuft. Ohne diese Rechnung faengt sie irgendwo im
// Bild an und sieht aus wie ein Strich, nicht wie eine Verbindung von
// draussen.
function randpunkt(ziel, richtung, breite, hoehe) {
  // Rueckwaerts laufen, bis eine der vier Kanten getroffen ist. Die
  // kleinste positive Strecke gewinnt -- alles andere laege hinter dem Rand.
  let kuerzeste = Infinity;
  const proben = [
    [-ziel.x, -richtung.x], [breite - ziel.x, -richtung.x],
    [-ziel.y, -richtung.y], [hoehe - ziel.y, -richtung.y],
  ];
  for (const [weg, anteil] of proben) {
    if (Math.abs(anteil) < 1e-9) continue;
    const t = weg / anteil;
    if (t > 0 && t < kuerzeste) {
      const x = ziel.x - richtung.x * t;
      const y = ziel.y - richtung.y * t;
      // Nur zaehlen, wenn der Treffer auch auf der Kante liegt und nicht
      // auf ihrer gedachten Verlaengerung.
      if (x >= -0.5 && x <= breite + 0.5 && y >= -0.5 && y <= hoehe + 0.5) {
        kuerzeste = t;
      }
    }
  }
  if (!Number.isFinite(kuerzeste)) return null;
  return { x: ziel.x - richtung.x * kuerzeste,
           y: ziel.y - richtung.y * kuerzeste };
}

// Die Mitte eines Gebiets im Bildraum seiner Karte. Mehrere Umrisse zaehlen
// zusammen: "Auvergne-Rhone-Alpes" sind dreizehn Departements, und die Linie
// gehoert in die Mitte des Ganzen, nicht in eines davon.
//
// Die Mitte des umschliessenden Rechtecks reicht dafuer NICHT. Am 06.09.2026
// nachgezaehlt, wie oft sie ausserhalb der Flaeche liegt: Philippinen 26 von
// 118, Indonesien 10 von 33, Griechenland 5 von 14. Bei einer Inselgruppe
// oder einem gebogenen Land liegt sie im Meer -- und die Linie endete
// daneben, was schlimmer ist als gar keine Linie: sie zeigt auf etwas.
//
// Also: erst das Rechteck probieren, und wenn das danebenliegt, ein Raster
// darueberlegen und den naechstgelegenen Punkt nehmen, der WIRKLICH auf der
// Flaeche liegt. isPointInFill fragt den Browser, nicht mich.
const RASTER = 15;

function gebietsmitte(svg, pfade) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const kaesten = [];
  for (const p of pfade) {
    let k;
    try { k = p.getBBox(); } catch (e) { continue; }
    if (!k || !k.width) continue;
    kaesten.push([p, k]);
    x0 = Math.min(x0, k.x); y0 = Math.min(y0, k.y);
    x1 = Math.max(x1, k.x + k.width); y1 = Math.max(y1, k.y + k.height);
  }
  if (!Number.isFinite(x0)) return null;

  // Was der Erzeuger schon ausgerechnet hat: die Mitte der GROESSTEN
  // Teilflaeche. Sie ist der Mitte des umschliessenden Rechtecks
  // vorzuziehen, sobald ein Gebiet entlegene Inseln hat -- Tokio umfasst
  // die Ogasawara-Inseln tausend Kilometer suedlich, und die Linie endete
  // dort statt in Tokio. Am 06.09.2026 im Bild gesehen.
  let mitte = null;
  for (const [pfad] of kaesten) {
    const cx = parseFloat(pfad.dataset.cx);
    const cy = parseFloat(pfad.dataset.cy);
    if (Number.isFinite(cx) && Number.isFinite(cy)) { mitte = { x: cx, y: cy }; break; }
  }
  if (!mitte) mitte = { x: (x0 + x1) / 2, y: (y0 + y1) / 2 };
  if (!svg.createSVGPoint) return mitte;

  const punkt = svg.createSVGPoint();
  const drin = (x, y) => {
    punkt.x = x; punkt.y = y;
    for (const [pfad] of kaesten) {
      try { if (pfad.isPointInFill(punkt)) return true; } catch (e) { /* egal */ }
    }
    return false;
  };
  if (drin(mitte.x, mitte.y)) return mitte;

  let beste = null, naechste = Infinity;
  for (let i = 1; i < RASTER; i++) {
    for (let j = 1; j < RASTER; j++) {
      const x = x0 + (x1 - x0) * i / RASTER;
      const y = y0 + (y1 - y0) * j / RASTER;
      if (!drin(x, y)) continue;
      const abstand = (x - mitte.x) ** 2 + (y - mitte.y) ** 2;
      if (abstand < naechste) { naechste = abstand; beste = { x, y }; }
    }
  }
  // Findet das Raster nichts, ist die Flaeche duenner als seine Maschen.
  // Dann lieber ein Punkt auf dem Rand als einer im Meer.
  if (!beste && kaesten.length) {
    const [pfad] = kaesten[0];
    try {
      const p = pfad.getPointAtLength(pfad.getTotalLength() / 2);
      beste = { x: p.x, y: p.y };
    } catch (e) { /* dann eben das Rechteck */ }
  }
  return beste || mitte;
}

/* Die Verbindungslinien im Land.

   Aus dem Betrieb, 06.09.2026: "wenn mein Verbindungsstrich auf der Weltkarte in
   ein Land geht und ich dann diesem Strich folge und auf das Land klicke --
   zeigt der Strich dann auf die Region?"

   Ja. Die Richtung kommt aus der Weltkarte: der Vektor vom eigenen Knoten zu
   diesem Land. Sie in der Landkarte fortzusetzen heisst, dass die Linie an
   derselben Seite hereinkommt, an der sie auf der Weltkarte ankam -- wer der
   Linie folgt, verliert sie beim Klick nicht.

   Das eigene Land bekommt keine: dorthin geht auf der Weltkarte auch keine
   Linie, denn man ist ja schon da. */
function zeichneLandlinien(land, gebiete) {
  const svg = $("#wl-karte").querySelector("svg");
  if (!svg) return;
  const alt = svg.querySelector(".wl-linien");
  if (alt) alt.remove();

  const heimat = (KARTE_LETZTE || {}).heimat;
  if (!heimat || heimat === land) return;
  const von = anker(heimat);
  const nach = anker(land);
  if (!von || !nach) return;
  const dx = nach.x - von.x;
  const dy = nach.y - von.y;
  const laenge = Math.hypot(dx, dy);
  if (laenge < 1) return;
  const richtung = { x: dx / laenge, y: dy / laenge };

  const kasten = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
  if (kasten.length !== 4) return;
  const breite = kasten[2], hoehe = kasten[3];

  const NS = "http://www.w3.org/2000/svg";
  const ebene = document.createElementNS(NS, "g");
  ebene.setAttribute("class", "wl-linien");

  const meiste = gebiete.reduce(
    (m, g) => Math.max(m, g.bitcoin + g.lightning), 0) || 1;

  for (const g of gebiete) {
    const zahl = g.bitcoin + g.lightning;
    if (!zahl) continue;          // ohne Gegenstelle keine Verbindung
    const pfade = (g.iso || [])
      .map((iso) => svg.querySelector(
        '[id="r-' + (window.CSS && CSS.escape ? CSS.escape(iso) : iso) + '"]'))
      .filter(Boolean);
    const mitte = gebietsmitte(svg, pfade);
    if (!mitte) continue;
    const start = randpunkt(mitte, richtung, breite, hoehe);
    if (!start) continue;

    const linie = document.createElementNS(NS, "path");
    linie.setAttribute("d", `M${start.x.toFixed(1)},${start.y.toFixed(1)}`
                          + `L${mitte.x.toFixed(1)},${mitte.y.toFixed(1)}`);
    linie.setAttribute("class", g.lightning ? "wl-linie ln" : "wl-linie");
    linie.style.setProperty("--staerke", (zahl / meiste).toFixed(3));
    ebene.append(linie);

    const punkt = document.createElementNS(NS, "circle");
    punkt.setAttribute("cx", mitte.x.toFixed(1));
    punkt.setAttribute("cy", mitte.y.toFixed(1));
    punkt.setAttribute("r", "5");
    punkt.setAttribute("class", "wl-ziel");
    ebene.append(punkt);
  }
  if (ebene.childNodes.length) svg.append(ebene);
}

let GEWAEHLTES_GEBIET = 0;

/* Ein Gebiet auswaehlen -- von der Karte aus oder aus der Tabelle.

   Aus dem Betrieb, 06.09.2026: "ich klicke in Bild 2 auf ein leuchtendes oder
   nicht leuchtendes Bundesland, und dann wird mir in der rechten Tabelle
   die Zeile markiert, in der ich geklickt habe."

   Beides markiert dasselbe, und ein zweiter Klick nimmt es zurueck. Ohne
   das Zuruecknehmen bliebe die Markierung stehen, und es gaebe keinen Weg
   zur unmarkierten Ansicht ausser dem Verlassen des Landes. */
function waehleGebiet(nummer) {
  const gewuenscht = Number(nummer) || 0;
  GEWAEHLTES_GEBIET =
    (gewuenscht && gewuenscht === GEWAEHLTES_GEBIET) ? 0 : gewuenscht;
  const gewaehlt = GEWAEHLTES_GEBIET;

  const zeilen = $$("#wl-zeilen tr");
  for (const tr of zeilen) {
    tr.classList.toggle("gewaehlt", Number(tr.dataset.gebiet) === gewaehlt);
  }
  for (const pfad of $$("#wl-karte .regionen path")) {
    pfad.classList.toggle("gewaehlt", Number(pfad.dataset.gebiet) === gewaehlt);
  }
  if (!gewaehlt) return;
  // Bei vielen Gebieten -- Frankreich hat 26, die Philippinen 82 -- laege
  // die Zeile sonst ausserhalb des Sichtbaren, und der Klick auf die Karte
  // saehe wirkungslos aus.
  const zeile = zeilen.find((tr) => Number(tr.dataset.gebiet) === gewaehlt);
  if (zeile && zeile.scrollIntoView) {
    zeile.scrollIntoView({ block: "nearest" });
  }
}

function schliesseLand() {
  LAND_OFFEN = "";
  GEWAEHLTES_GEBIET = 0;
  $("#welt-land").classList.add("hidden");
}

function zeichneLand(d, ohneUmriss) {
  $("#wl-stand").textContent = d.stand ? t("wl_stand", { stand: d.stand }) : "";
  const zeilen = $("#wl-zeilen");
  zeilen.textContent = "";
  const gebiete = (d && d.gebiete) || [];

  const hinweis = $("#wl-leer");
  if (!d.moeglich) hinweis.textContent = t("wl_unmoeglich");
  else if (!gebiete.length) hinweis.textContent = t("wl_keine");
  else if (ohneUmriss) hinweis.textContent = t("wl_ohne_umriss");
  else hinweis.textContent = "";
  // Eine Ueberschriftszeile ueber nichts sieht aus wie eine Tabelle, die
  // gleich noch etwas nachliefert. Sie liefert nichts nach.
  $(".wl-tabelle").classList.toggle("hidden", !gebiete.length);

  // Die Faerbung richtet sich nach dem groessten Wert im Land, nicht nach
  // einer festen Schwelle: sonst waere bei drei Gegenstellen alles gleich
  // blass und die Karte sagte nichts.
  const hoechst = gebiete.reduce(
    (m, g) => Math.max(m, g.bitcoin + g.lightning, g.adressbuch / 20), 0) || 1;

  for (const g of gebiete) {
    const gewicht = Math.min(
      1, (g.bitcoin + g.lightning + g.adressbuch / 20) / hoechst);
    for (const iso of g.iso || []) {
      const pfad = $("#wl-karte").querySelector(
        '[id="r-' + (window.CSS && CSS.escape ? CSS.escape(iso) : iso) + '"]');
      if (!pfad) continue;
      pfad.style.setProperty("--hitze", gewicht.toFixed(3));
      if (g.bitcoin || g.lightning) pfad.classList.add("betont");
    }

    const tr = document.createElement("tr");
    if (g.bitcoin || g.lightning) tr.className = "betont";
    tr.dataset.gebiet = String(g.n);
    // In beide Richtungen: die Zeile findet ihr Gebiet, das Gebiet seine
    // Zeile. Ein Klick auf die Karte soll nicht in eine Liste zwingen, in
    // der man dann selbst suchen muss.
    tr.addEventListener("click", () => waehleGebiet(g.n));
    const name = document.createElement("td");
    name.textContent = LANG === "de" ? g.de : g.en;
    tr.append(name);
    for (const wert of [g.bitcoin, g.lightning, g.adressbuch]) {
      const td = document.createElement("td");
      td.className = "zahl";
      td.textContent = wert ? wert.toLocaleString(LANG) : "—";
      tr.append(td);
    }
    zeilen.append(tr);
  }

  // Jeder Umriss weiss, zu welchem Gebiet er gehoert -- auch die ohne
  // Gegenstellen. Der Betreiber ausdruecklich: "ein leuchtendes ODER NICHT
  // leuchtendes Bundesland".
  for (const g of gebiete) {
    for (const iso of g.iso || []) {
      const pfad = $("#wl-karte").querySelector(
        '[id="r-' + (window.CSS && CSS.escape ? CSS.escape(iso) : iso) + '"]');
      if (pfad) pfad.dataset.gebiet = String(g.n);
    }
  }
  GEWAEHLTES_GEBIET = 0;
  zeichneLandlinien(d.land, gebiete);

  const rest = d.ohne_gebiet || {};
  const uebrig = (rest.bitcoin || 0) + (rest.lightning || 0)
               + (rest.adressbuch || 0);
  // Was im Land liegt, aber in keinem Gebiet -- weglassen hiesse, eine
  // kleinere Summe zu zeigen als die Weltkarte, ohne zu sagen warum.
  $("#wl-rest").textContent = uebrig > 0
    ? t("wl_rest", { btc: rest.bitcoin || 0, ln: rest.lightning || 0,
                     buch: rest.adressbuch || 0 })
    : "";
}

/* ── Welt ───────────────────────────────────────────────────────────────────
   Der Streifen unter der Karte. Vier Zahlen je Seite, nicht vierzig: was
   man im Vorbeigehen liest, muss man nicht suchen.

   "Naechster Block" ist dabei die einzige Zahl hier, die kein Explorer so
   zeigen kann -- es ist die Auswahl DIESES Knotens aus SEINEM Mempool. Und
   waehrend des Abgleichs gibt es sie nicht: Core lehnt die Vorlage dann ab,
   und dann steht das da, statt einer Null. */

let WELT_STAND = 0;
const WELT_ABSTAND_MS = 30000;

async function ladeWelt(erzwingen) {
  const jetzt = Date.now();
  if (!erzwingen && jetzt - WELT_STAND < WELT_ABSTAND_MS) return;
  WELT_STAND = jetzt;
  try {
    zeichneWelt(await api("/kennzahlen"));
    // Der Streifen hat eben seine Zeilen bekommen und ist dadurch hoeher.
    // Gleich hier messen, nicht auf den ResizeObserver warten: der meldet
    // sich nur, wenn der Browser zeichnet -- in einem Hintergrundreiter also
    // nie, und die Karte behielte die Hoehe des leeren Streifens. Hier beim
    // Aufrufer und nicht am Ende der Zeichenfunktion: die steigt ohne
    // Lightning-Daten vorher aus.
    messeWeltstreifen();
  } catch (e) {
    if (e && e.abgemeldet) return;
    WELT_STAND = 0;
  }
}

// Die Einheit gehoert an die BESCHRIFTUNG, nicht an jeden Wert. "schnell 44
// sat/vB · normal 18 sat/vB · guenstig 6 sat/vB" liest niemand; einmal
// "Gebuehren sat/vB" und danach nackte Zahlen schon. Und eine Zahl ganz ohne
// Einheit ist keine Auskunft -- "Anpassung in 812" sagt gar nichts.
function paar(ziel, beschriftung, einheit, wert, stark) {
  const dt = document.createElement("dt");
  dt.append(document.createTextNode(beschriftung));
  if (einheit) {
    const e = document.createElement("span");
    e.className = "einheit"; e.textContent = einheit;
    dt.append(e);
  }
  const dd = document.createElement("dd"); dd.textContent = wert;
  if (stark) dd.className = "stark";
  ziel.append(dt, dd);
  return dd;
}

function zeichneWelt(d) {
  const btc = $("#w-btc");
  btc.textContent = "";
  if (!d || !d.eingerichtet) return;

  const nb = d.naechster_block;
  if (nb) {
    // Die Einheiten stehen hier IM Wert, weil es drei verschiedene sind.
    paar(btc, t("w_naechster"), "", t("w_naechster_wert", {
      tx: zahl(nb.transaktionen),
      // nachkomma(), nicht toFixed(): im Deutschen steht dort ein Komma.
      // "1.00 MB" liest sich sonst wie tausend.
      mb: nachkomma(nb.vbytes / 1e6, 2),
      von: nachkomma(nb.sat_vb_min, 0),
      bis: nachkomma(nb.sat_vb_max, 0),
    }), true);
  } else {
    // Waehrend des Abgleichs sagt Core ausdruecklich nein. Das gehoert
    // hingeschrieben -- eine leere Zeile saehe nach Stoerung aus.
    paar(btc, t("w_naechster"), "", t("w_naechster_sync"));
  }
  paar(btc, t("w_hoehe"), "", zahl(d.hoehe || 0));

  const g = d.gebuehren || {};
  const teile = [];
  for (const [schluessel, name] of [["schnell", "w_g_schnell"],
                                    ["normal", "w_g_normal"],
                                    ["guenstig", "w_g_guenstig"]]) {
    if (g[schluessel] != null) {
      teile.push(t(name) + " " + nachkomma(g[schluessel], 0));
    }
  }
  paar(btc, t("w_gebuehren"), "sat/vB",
       teile.length ? teile.join(" · ") : t("w_keine_daten"));

  // Zwei Zeilen statt einer: der Wert und die naechste Anpassung sind zwei
  // Auskuenfte. Zusammengeschoben stand da "142,1 T · +2,3 % · Anpassung in
  // 812" -- drei Zahlen, von denen zwei keine Einheit hatten.
  const sw = d.schwierigkeit || {};
  paar(btc, t("w_schwierigkeit"), "", sw.wert ? kurzzahl(sw.wert) : "—");
  const anpassung = [];
  if (sw.aenderung_prozent != null) {
    const pz = sw.aenderung_prozent;
    anpassung.push((pz >= 0 ? "+" : "") + nachkomma(pz, 1) + " %");
  }
  if (sw.bloecke_bis_anpassung != null) {
    anpassung.push(t("w_in_bloecken", { n: zahl(sw.bloecke_bis_anpassung) }));
  }
  paar(btc, t("w_anpassung"), "", anpassung.join(" · ") || "—");

  zeichneWeltLightning();
}

// Sehr grosse Zahlen lesbar machen: 142.100.000.000.000 sagt niemandem
// etwas, 142,1 T schon.
function kurzzahl(n) {
  const stufen = [[1e12, "T"], [1e9, "G"], [1e6, "M"], [1e3, "k"]];
  for (const [teiler, kuerzel] of stufen) {
    if (n >= teiler) return nachkomma(n / teiler, 1) + " " + kuerzel;
  }
  return nachkomma(n, 0);
}

function zeichneWeltLightning() {
  const ziel = $("#w-ln");
  const hinweis = $("#w-ln-hinweis");
  ziel.textContent = "";
  hinweis.textContent = "";

  const ln = (KARTE_LETZTE || {}).lightning;
  if (!ln) {
    // Kein Fehler: solange es keine Wallet gibt, gibt es auch keine Kanaele.
    hinweis.textContent = t("w_ln_keine_wallet");
    return;
  }
  const gegen = ln.gegenstellen || [];
  const kapazitaet = gegen.reduce((s, g) => s + (g.kapazitaet || 0), 0);
  const kanaele = gegen.reduce((s, g) => s + (g.kanaele || 0), 0);

  // Zwei Zeilen statt "3 zu 2 Gegenstellen": die Kanaele und die Knoten, mit
  // denen sie bestehen, sind zwei verschiedene Zahlen.
  paar(ziel, t("w_ln_kanaele"), "", zahl(kanaele), true);
  paar(ziel, t("w_ln_partner"), "", zahl(gegen.length));
  paar(ziel, t("w_ln_kapazitaet"), "sat", zahl(kapazitaet));
  paar(ziel, t("w_ln_laender"), "",
       zahl(Object.keys(ln.kapazitaet_je_land || {}).length));
  if (ln.ohne_ort) {
    paar(ziel, t("w_ln_ohne_ort"), "", zahl(ln.ohne_ort));
    hinweis.textContent = t("w_ln_ohne_ort_d");
  }
}

/* ── Protokolle ─────────────────────────────────────────────────────────────
   "Was ist gerade los?" ohne Docker-Socket. Der waere auf einem Geraet mit
   einer Wallet gleichbedeutend mit root -- also liest die Anwendung, was die
   Dienste ohnehin in das eingehaengte Datenverzeichnis schreiben.

   Der Text geht ueber textContent in die Seite, nie ueber innerHTML: hier
   steht fremde Ausgabe, und die darf niemals als Auszeichnung gelesen
   werden. Ein Peer, der sich mit einem <script> im Namen meldet, waere sonst
   ein Angriff und nicht nur eine Zeile im Protokoll. */

let LOG_QUELLE = "satcortex";
let LOG_QUELLEN = [];

async function ladeLogs(erzwingen) {
  if (!erzwingen && ANSICHT !== "logs") return;
  try {
    LOG_QUELLEN = (await api("/logs")).quellen || [];
  } catch (e) {
    if (e && e.abgemeldet) return;
    LOG_QUELLEN = [];
  }
  // Steht die gewaehlte Quelle nicht mehr zur Verfuegung, faellt die Anzeige
  // auf das eigene Protokoll zurueck -- das gibt es immer.
  if (!LOG_QUELLEN.some((q) => q.name === LOG_QUELLE && q.da)) {
    LOG_QUELLE = "satcortex";
  }
  zeichneLogQuellen();
  await ladeLogText();
}

function zeichneLogQuellen() {
  const ziel = $("#p-quellen");
  ziel.textContent = "";
  for (const q of LOG_QUELLEN) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = q.name === LOG_QUELLE ? "aktiv" : "";
    // Dienstnamen sind Eigennamen und werden nicht uebersetzt; nur die
    // eigene Zeile heisst in jeder Sprache anders.
    b.textContent = q.name === "satcortex" ? t("log_eigenes") : q.name;
    b.disabled = !q.da;
    if (!q.da) b.title = t("log_keine_datei");
    b.addEventListener("click", async () => {
      LOG_QUELLE = q.name;
      zeichneLogQuellen();
      await ladeLogText();
    });
    ziel.append(b);
  }
}

// Bitcoin Core schreibt sein Protokoll in UTC -- daran ist nichts falsch,
// es ist sogar vernuenftig. Tor und diese Anwendung schreiben aber in der
// eingestellten Ortszeit. In derselben Ansicht standen damit zwei Uhren.
//
// Aus dem Betrieb, 03.09.2026, mit einem Bildschirmfoto: "was ist denn jetzt hier
// los ... ist das wieder kaputt???? das bitcoin protokoll hoert bei 20:08
// auf". Es war 22:10 bei ihm, die Zeile also EINE MINUTE alt -- und sah aus
// wie zwei Stunden Stillstand. Eine Anzeige, die zwei Zeitzonen mischt und
// keine davon nennt, ist eine Falle.
//
// Umgerechnet wird nur ein Zeitstempel am ZEILENANFANG mit ausdruecklichem
// "Z". Alles andere bleibt Zeichen fuer Zeichen stehen: ein Protokoll, das
// die Anzeige umschreibt, waere schlimmer als eines mit der falschen Uhr.
const UTC_STEMPEL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z/;

function ortszeit(zeile) {
  const t2 = UTC_STEMPEL.exec(zeile);
  if (!t2) return zeile;
  const d = new Date(Date.UTC(+t2[1], +t2[2] - 1, +t2[3], +t2[4], +t2[5], +t2[6]));
  if (isNaN(d.getTime())) return zeile;      // lieber roh als falsch
  const zwei = (n) => String(n).padStart(2, "0");
  const neu = `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}. `
            + `${zwei(d.getHours())}:${zwei(d.getMinutes())}:${zwei(d.getSeconds())}`;
  return neu + zeile.slice(t2[0].length);
}

async function ladeLogText() {
  const feld = $("#p-text");
  const stand = $("#p-stand");
  feld.textContent = t("log_laedt");
  try {
    const d = await api("/logs/" + encodeURIComponent(LOG_QUELLE)
                        + "?zeilen=" + LOG_ZEILEN);
    if (!d.da) {
      feld.textContent = "";
      stand.textContent = t("log_keine_datei");
      return;
    }
    feld.textContent = (d.zeilen || []).map(ortszeit).join("\n");
    const teile = [t("log_zeilen_n", { n: zahl((d.zeilen || []).length) })];
    if (d.abgeschnitten) teile.push(t("log_gekuerzt"));
    if (d.groesse_bytes) teile.push(menschenBytes(d.groesse_bytes));
    stand.textContent = teile.join(" · ");
    // Ans Ende springen: das Neueste steht unten, und danach sucht man.
    feld.scrollTop = feld.scrollHeight;
  } catch (e) {
    if (e && e.abgemeldet) return;
    feld.textContent = "";
    stand.textContent = t("log_fehler");
  }
}

/* ── Einstellungen ──────────────────────────────────────────────────────── */
//
// Ein eigener Bereich, damit die Uebersicht Uebersicht bleibt. Was man selten
// braucht -- und spaeter alles, was zwischen den Kennzahlen nur stoeren
// wuerde -- liegt hier statt dort.

function zeigeEinstellungen() {
  // Einstellungen sind jetzt eine Ansicht wie jede andere, kein eigener
  // Bildschirm mehr, den man ueber einen Knopf in der Fusszeile erreicht.
  $("#e-adresse-meldung").textContent = "";
}

/* ── Weltkarte ──────────────────────────────────────────────────────────────
   Was dieser Knoten vom Netz kennt -- nicht, was "das Netz" ist. Es gib
   keine Liste aller Bitcoin-Knoten, und das ist Absicht. Was es gibt, ist das
   Adressbuch des eigenen Knotens: alles, was ihm ueber addr-Nachrichten
   zugetragen wurde. Die Karte waechst also mit ihm mit. */

let KARTE_GEHOLT = false;      // die Umrisse nur einmal laden
let KARTE_DA = false;          // ... aber liegen sie auch wirklich im DOM?
let KARTE_STAND = 0;           // wann zuletzt Daten geholt wurden
// Der letzte Kartenstand. Die Weltansicht braucht seine
// Lightning-Haelfte und soll sie nicht ein zweites Mal holen.
let KARTE_LETZTE = null;

// Die Umrisse aendern sich nie, die Daten selten. Alle zehn Sekunden neu zu
// fragen hiesse, bitcoind alle zehn Sekunden nach seinen Gegenstellen zu
// fragen -- fuer eine Karte, auf der sich derweil nichts bewegt.
const KARTE_ABSTAND_MS = 60000;

let KARTE_ERSTSYNC = false;
// Kuerzel -> {adressen, peers}. Die Marke braucht die Zahlen zum Zeitpunk
// des Zeigens, nicht die des letzten Zeichnens.
let KARTE_ZAHLEN = {};
let KARTE_MARKE_BEREIT = false;

async function ladeKarte(erzwingen, imErstsync) {
  const buehne = $("#d-karte");
  if (!buehne) return;
  if (imErstsync !== undefined) KARTE_ERSTSYNC = imErstsync;

  if (!KARTE_GEHOLT) {
    KARTE_GEHOLT = true;                      // auch bei Fehlschlag: nicht endlos
    try {
      const r = await fetch("welt.svg");
      if (r.ok) {
        buehne.innerHTML = await r.text();
        KARTE_DA = true;
      }
    } catch (e) { /* ohne Umrisse bleiben die Zahlen daneben stehen */ }
  }

  // Einblenden bei JEDEM Aufruf, nicht nur beim ersten.
  //
  // Aus dem Betrieb, 12.09.2026: "wenn sich die app sitzung abmeldet und ich mich
  // wieder einlogge dann laedt die welt karte nicht automatisch ich muss dann
  // erst nach dem anmelden die browser seite refreshen".
  //
  // Genau das war der Grund: das Ausblenden steht in zeigeTor(), das
  // Einblenden stand im Block darueber -- und der laeuft nur EINMAL je
  // Seitenaufruf. Nach dem Abmelden war die Karte also versteckt, und nichts
  // holte sie je wieder hervor. Ein Neuladen der Seite setzte KARTE_GEHOLT
  // zurueck, deshalb half es.
  //
  // Steht bewusst VOR der Frischesperre darunter: auch ein uebersprungener
  // Abruf muss die Karte wieder sichtbar machen. Die Umrisse liegen ja noch
  // im DOM -- es fehlte nur das Anzeigen.
  if (KARTE_DA) $("#karte-hintergrund").classList.remove("hidden");

  const jetzt = Date.now();
  if (!erzwingen && jetzt - KARTE_STAND < KARTE_ABSTAND_MS) return;
  KARTE_STAND = jetzt;

  try {
    KARTE_LETZTE = await api("/karte");
    zeichneKarte(KARTE_LETZTE);
    // Die Weltansicht liest die Lightning-Seite aus demselben Abruf. Sie
    // ein zweites Mal zu holen hiesse, den Graphen zweimal zu befragen --
    // und die Karte zeigte dann womoeglich etwas anderes als der Streifen
    // darunter.
    if (ANSICHT === "welt") {
      zeichneWeltLightning();
      messeWeltstreifen();              // siehe ladeWelt()
    }
  } catch (e) {
    if (e && e.abgemeldet) return;
    KARTE_STAND = 0;                          // beim naechsten Mal erneut
  }
}

function zeichneKarte(d) {
  if (!d || !d.eingerichtet) return;
  const laender = d.laender || [];

  // Eine leere Antwort ist KEINE Aussage ueber die Welt.
  //
  // Aus dem Betrieb, 04.09.2026: "die weltkarte verschwindet mit der zeit immer
  // mal wieder, dann ist der hintergrund unserer app schwarz und zeigt nix
  // mehr an."
  //
  // Genau hier lag es. Der Abruf gelingt, bringt aber kein Adressbuch mit --
  // das fuellt ein eigener Lauf nur alle dreissig Minuten, und bis dahin
  // (oder nach einem Aussetzer) liefert die Schnittstelle ein leeres. Ein
  // paar Zeilen weiter unten wurde dann ZUERST jede Einfaerbung entfernt und
  // danach nichts Neues gesetzt: schwarze Welt.
  //
  // Dieselbe Regel wie ueberall sonst: was dasteht, ist ein paar Minuten alt
  // und damit richtiger als eine leere Flaeche.
  if (!laender.length) {
    log_fehler("Karte ohne Laender -- alte Einfaerbung bleibt stehen",
               new Error("laender leer"));
    return;
  }

  const hoechster = laender.reduce((m, e) => Math.max(m, e.adressen), 0);

  // Alte Einfaerbung entfernen: sonst bleibt ein Land bunt, aus dem der
  // Knoten inzwischen keine Adresse mehr kennt. Das ist ab hier gefahrlos --
  // es gibt etwas Neues zu zeichnen.
  $$(".weltkarte .laender path, .weltkarte .kleine circle").forEach((el) => {
    el.style.removeProperty("--hitze");
    el.classList.remove("nachbar", "heimat");
  });

  KARTE_ZAHLEN = {};
  let ohneForm = 0;
  laender.forEach((e) => {
    KARTE_ZAHLEN[e.land] = e;
    // Erst der Umriss, sonst der Punkt: Singapur, Hongkong, Malta und
    // Verwandte haben bei dieser Aufloesung keine Flaeche. Ohne den zweiten
    // Griff fielen sie still von der Karte, waehrend die Liste daneben sie
    // auffuehrt.
    const el = document.getElementById("l-" + e.land)
            || document.getElementById("p-" + e.land);
    if (!el) { ohneForm += 1; return; }
    if (e.adressen > 0 && hoechster > 0) {
      el.style.setProperty("--hitze", hitze(e.adressen, hoechster));
    }
    if (e.peers > 0) el.classList.add("nachbar");
  });
  d.ohne_form = ohneForm;

  zeichneLinien(d, laender);
  ruesteMarke();
  zeichneKartenzahlen(d);
  zeichneKartenrang(laender, hoechster);

  const quelle = $("#d-karte-quelle");
  quelle.textContent = t("karte_quelle", { stand: d.orte_stand || "?" });
}

/* ── Die Verbindungen ───────────────────────────────────────────────────────
   Bis hierher zeigte die Karte, WO etwas ist. Sie zeigte nicht, dass etwas
   davon mit uns spricht. Genau das war der Wunsch aus dem Betrieb: die Gegenstellen als
   Netz, nicht als Farbflecken.

   Der Ursprung kommt aus dem Backend (karte.eigener_ort) und ist bewusst nur
   ein Laenderkuerzel -- die eigene Adresse gehoert nicht in die Oberflaeche.
   Ohne Ursprung bleibt die Ebene leer, statt einen zu erfinden.

   Die Boegen sind quadratische Bezierkurven, deren Kontrollpunkt senkrech
   zur Sehne nach Norden versetzt liegt. Gerade Linien saehen auf einer
   Weltkarte falsch aus; die Woelbung liest sich als Weg, nicht als Strich.
   Sie ist NICHT als Grosskreis gemeint und behauptet auch keinen. */

const WOELBUNG = 0.18;

let LINIEN_SIGNATUR = "";
let LINIEN_GEZEICHNET = false;

// Wieviel Platz der Streifen der Weltkarte unten wegnimmt.
//
// Gemessen bis zu seiner OBERKANTE, nicht seine Hoehe: er sitzt nicht am
// Fensterrand, sondern ueber dem Innenabstand des Abschnitts. Beim ersten
// Anlauf hatte ich seine Hoehe genommen -- damit blieben zweiundfuenfzig
// Punkte Ueberlappung stehen, also weiter ein Stueck Suedhalbkugel unter dem
// Kasten. Und gemessen statt geraten, weil der Streifen auf schmalen
// Geraeten umbricht und dann doppelt so hoch ist.
function messeWeltstreifen() {
  const streifen = $(".welt-streifen");
  if (!streifen) return;
  const kasten = streifen.getBoundingClientRect();
  if (!kasten.height) return;            // versteckt: nichts zu messen
  const wurzel = document.documentElement.style;
  const platz = Math.max(0, Math.round(window.innerHeight - kasten.top)) + 14;
  wurzel.setProperty("--streifen-hoehe", platz + "px");
  // Oben und links endet die Karte dort, wo der Inhalt beginnt. Bis zum
  // 14.09.2026 hing sie am Fensterrand: in 925x520 lagen 45 % der Welt unter
  // dem Kopf. Oben zaehlt, was tiefer liegt -- der Kopf klebt, die Leiste mit
  // den Abschnitten auf schmalen Geraeten rollt dagegen mit weg.
  const kopf = $(".kopf");
  const inhalt = $(".inhalt");
  if (!kopf || !inhalt) return;
  const unterKopf = kopf.getBoundingClientRect().bottom;
  const rahmen = inhalt.getBoundingClientRect();
  wurzel.setProperty("--welt-oben",
    Math.round(Math.max(unterKopf, rahmen.top, 0)) + "px");
  wurzel.setProperty("--welt-links", Math.round(Math.max(rahmen.left, 0)) + "px");
}

// Scrollen und eine neue Fenstergroesse verschieben den Streifen, ohne seine
// Groesse zu aendern -- das sieht der ResizeObserver nicht.
function weltNeuMessen() {
  if (ANSICHT === "welt") messeWeltstreifen();
}

// Die Zahlen unter der Weltkarte lassen sich einklappen. Auf kleinen
// Bildschirmen bleibt neben ihnen kaum Platz fuer die Welt -- gemessen am
// 14.09.2026 in 925x520: der Streifen nahm die halbe Hoehe. Die Wahl gilt nur
// fuer diesen Browser.
function weltStreifenKlappen(zu, merken) {
  const streifen = $(".welt-streifen");
  const knopf = $("#w-klapp");
  if (!streifen || !knopf) return;
  streifen.classList.toggle("zu", zu);
  knopf.dataset.i18n = zu ? "w_klapp_auf" : "w_klapp_zu";
  knopf.textContent = t(zu ? "w_klapp_auf" : "w_klapp_zu");
  knopf.setAttribute("aria-expanded", String(!zu));
  if (merken) {
    try { localStorage.setItem("satcortex-welt-zahlen", zu ? "aus" : "an"); } catch (e) { /* dann nur bis zum Neuladen */ }
  }
  // Die Karte bekommt den Platz sofort, nicht erst beim naechsten Zeichnen.
  weltNeuMessen();
}

function anker(kuerzel) {
  if (!kuerzel) return null;
  // Erst der Umriss, dann der Punkt -- wie bei der Einfaerbung: Singapur und
  // Verwandte haben bei dieser Aufloesung keine Flaeche.
  const el = document.getElementById("l-" + kuerzel)
          || document.getElementById("p-" + kuerzel);
  if (!el) return null;
  const x = parseFloat(el.dataset.x);
  const y = parseFloat(el.dataset.y);
  // Antarktika hat keinen Ankerpunkt: ihr Schwerpunkt liegt unter dem
  // Kartenausschnitt. Ein NaN im Pfad macht die ganze Linie unsichtbar --
  // und zwar stumm.
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y, el } : null;
}

// Der Name statt des Kuerzels: "Deutschland" sagt mehr als "DE", und die
// Namen liegen ohnehin schon am Umriss -- in beiden Sprachen.
function landName(kuerzel) {
  const el = anker(kuerzel);
  return (el && (el.el.dataset[LANG] || el.el.dataset.en)) || kuerzel;
}

function bogen(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const laenge = Math.hypot(dx, dy);
  if (laenge < 2) return null;          // Nachbarland: ein Strich waere Unsinn
  // Normale zur Sehne, immer nach Norden gedreht -- sonst woelbt sich die
  // eine Haelfte der Linien nach oben und die andere nach unten, und die
  // Karte sieht aus wie ein Knaeuel statt wie ein Netz.
  let nx = -dy / laenge;
  let ny = dx / laenge;
  if (ny > 0) { nx = -nx; ny = -ny; }
  const cx = (a.x + b.x) / 2 + nx * laenge * WOELBUNG;
  const cy = (a.y + b.y) / 2 + ny * laenge * WOELBUNG;
  return "M" + a.x + "," + a.y +
         "Q" + cx.toFixed(1) + "," + cy.toFixed(1) +
         " " + b.x + "," + b.y;
}

function zeichneLinien(d, laender) {
  const buehne = $("#d-karte");
  const svg = buehne && buehne.querySelector("svg");
  const ebene = svg && svg.querySelector(".linien");
  if (!ebene) return;

  const heim = anker(d.heimat);
  // Vor der Signaturpruefung: die Einfaerbung wird bei jedem Zeichnen
  // zurueckgesetzt, die Markierung muss also jedes Mal neu gesetzt werden --
  // auch wenn an den Linien selbst nichts zu tun ist.
  if (heim) heim.el.classList.add("heimat");

  const ziele = laender.filter((e) => e.peers > 0 && e.land !== d.heimat);
  // Nichts neu zeichnen, solange sich nichts geaendert hat. Sonst faengt die
  // Karte jede Minute von vorn an zu leuchten -- eine Bewegung ohne Anlass,
  // auf einer Flaeche, die dauerhaft im Blick liegt. Das ist keine Zier,
  // das ist Stoerung.
  const signatur = (d.heimat || "-") + "|" +
    ziele.map((e) => e.land + ":" + e.peers).join(",") + "|" +
    // Ohne die Lightning-Seite blieben die orangen Linien beim ersten Stand
    // stehen: ein neuer Kanal aendert die gelben nicht.
    JSON.stringify((d.lightning || {}).kapazitaet_je_land || {});
  if (signatur === LINIEN_SIGNATUR) return;
  LINIEN_SIGNATUR = signatur;

  ebene.textContent = "";
  // Ohne Ursprung keine Linien. Der haeufigste Grund ist ein reiner
  // Tor-Betrieb -- dann gibt es wirklich keinen Ort, und das ist die
  // richtige Antwort, nicht ein Mangel.
  if (!heim) return;

  const meiste = ziele.reduce((m, e) => Math.max(m, e.peers), 0);
  const NS = "http://www.w3.org/2000/svg";
  let i = 0;

  // Zuerst die Lightning-Linien, damit die gelben darueber liegen: welche
  // Gegenstellen der Bitcoin-Knoten gerade hat, aendert sich staendig und
  // ist die Bewegung im Bild. Wo Kapital gebunden ist, aendert sich selten
  // und darf ruhig darunter liegen.
  const ln = (d.lightning || {}).kapazitaet_je_land || {};
  const groesste = Object.values(ln).reduce((m, v) => Math.max(m, v), 0);
  for (const [land, kapazitaet] of Object.entries(ln)) {
    if (land === d.heimat) continue;
    const ziel = anker(land);
    if (!ziel) continue;
    const pfad = bogen(heim, ziel);
    if (!pfad) continue;
    const linie = document.createElementNS(NS, "path");
    linie.setAttribute("d", pfad);
    linie.setAttribute("class", "linie-ln");
    // Nach Kapazitaet, nicht nach Anzahl: zwei kleine Kanaele sind nicht
    // dasselbe wie ein grosser, und auf dieser Karte geht es um Gewicht.
    linie.style.setProperty("--staerke",
      groesste > 0 ? Math.pow(kapazitaet / groesste, 0.5).toFixed(3) : "1");
    ebene.append(linie);
  }

  ziele.forEach((e) => {
    const ziel = anker(e.land);
    if (!ziel) return;
    const pfad = bogen(heim, ziel);
    if (!pfad) return;
    const linie = document.createElementNS(NS, "path");
    linie.setAttribute("d", pfad);
    linie.setAttribute("class", "linie");
    // Mehr Gegenstellen, kraeftigere Linie. Wurzelkurve wie bei der
    // Einfaerbung, aus demselben Grund: sonst verschwinden alle Laender
    // neben dem einen, in dem die meisten sitzen.
    linie.style.setProperty("--staerke",
      meiste > 0 ? Math.pow(e.peers / meiste, 0.5).toFixed(3) : "1");
    ebene.append(linie);
    // Das Einblenden laeuft EINMAL, beim ersten Zeichnen: es zeigt die
    // Richtung -- von hier nach draussen. Danach steht die Karte still.
    // (Wer Bewegung abbestellt hat, sieht sie fertig; dafuer sorgt die
    // Regel unter prefers-reduced-motion in der Stilvorlage.)
    if (!LINIEN_GEZEICHNET) {
      linie.style.setProperty("--len", Math.ceil(linie.getTotalLength()));
      linie.style.setProperty("--i", i);
      linie.classList.add("ein");
    }
    i += 1;
  });

  const quelle = document.createElementNS(NS, "circle");
  quelle.setAttribute("class", "quelle");
  quelle.setAttribute("cx", heim.x);
  quelle.setAttribute("cy", heim.y);
  quelle.setAttribute("r", "3.5");
  ebene.append(quelle);

  LINIEN_GEZEICHNET = true;
}

// Wie stark ein Land leuchtet. Weder linear noch logarithmisch:
//
// Linear waere alles ausser den zwei groessten Laendern schwarz -- ein paar
// wenige stellen die grosse Mehrheit der Adressen. Logarithmisch schlaegt es
// ins Gegenteil um: ein Land mit fuenf Prozent der Adressen kaeme auf knapp
// siebzig Prozent Helligkeit, und die Karte waere ueberall gleich orange.
// Gemessen an einer echten Verteilung war genau das der Fall.
//
// Eine Wurzelkurve liegt dazwischen: kleine Laender bleiben sichtbar, die
// Abstaende zwischen den grossen aber auch.
const HITZE_KURVE = 0.35;

function hitze(anzahl, hoechster) {
  return Math.pow(anzahl / hoechster, HITZE_KURVE).toFixed(3);
}

/* Die Schwebemarke: sagt, was da liegt.
   Ein Punkt mitten im Ozean ist ohne Namen keine Information. Die sichtbaren
   sind Inselstaaten und Kleinstgebiete -- Seychellen, Mauritius, Cayman,
   Britische Jungferninseln, Curacao, Singapur, Hongkong. Also genau die
   Gerichtsbarkeiten, in denen viel gehostet wird. Nur sieht man ihnen das
   ohne Beschriftung nicht an. */
// Eine eigene Zeile fuer den Einzelfall. "1 deiner Gegenstellen sitzen hier"
// liest sich wie ein Uebersetzungsfehler -- und ist genau das.
function peerSatz(anzahl) {
  return anzahl === 1 ? t("karte_mit_peers_1")
                      : t("karte_mit_peers", { p: anzahl });
}

function ruesteMarke() {
  if (KARTE_MARKE_BEREIT) return;
  const buehne = $("#d-karte");
  const marke = $("#d-karte-marke");
  const svg = buehne && buehne.querySelector("svg");
  if (!buehne || !marke || !svg) return;
  KARTE_MARKE_BEREIT = true;

  const zeigen = (ziel, x, y) => {
    const kuerzel = (ziel.id || "").slice(2);
    const name = ziel.dataset[LANG] || ziel.dataset.en || kuerzel;
    const e = KARTE_ZAHLEN[kuerzel];
    marke.textContent = "";
    const b = document.createElement("b"); b.textContent = name;
    marke.append(b);
    const z = document.createElement("span"); z.className = "zahlen";
    z.textContent = e
      ? t("karte_marke_adressen", { n: zahl(e.adressen) })
      : t("karte_marke_nichts");
    marke.append(z);
    if (e && e.peers > 0) {
      const v = document.createElement("span");
      v.className = "zahlen verbunden";
      v.textContent = peerSatz(e.peers);
      marke.append(v);
    }
    // Erst sichtbar machen, DANN messen: eine versteckte Marke hat keine
    // Breite, und mit einer geschaetzten lief sie rechts aus dem Bild
    // heraus -- "sitzt hie" stand da.
    // Erst sichtbar machen, DANN messen: eine versteckte Marke hat keine
    // Breite, und mit einer geschaetzten lief sie rechts aus dem Bild heraus.
    marke.classList.remove("hidden");
    const eigen = marke.getBoundingClientRect();
    const halb = eigen.width / 2 + 6;
    // Die Karte fuellt jetzt das Fenster, die Marke liegt fix darin.
    marke.style.left =
      Math.min(Math.max(x, halb), innerWidth - halb) + "px";
    const drunter = y < eigen.height + 16;
    marke.classList.toggle("drunter", drunter);
    marke.style.top = (drunter ? y + 18 : y) + "px";
  };

  // Ein Zuhoerer auf dem SVG statt 238 einzelne. Beim Ueberfahren einer
  // Weltkarte ist das der Unterschied zwischen fluessig und zaeh.
  const treffer = (ev) => ev.target.closest(
    ".weltkarte .laender path, .weltkarte .kleine circle");

  svg.addEventListener("pointermove", (ev) => {
    const ziel = treffer(ev);
    if (ziel) zeigen(ziel, ev.clientX, ev.clientY);
    else marke.classList.add("hidden");
  });
  svg.addEventListener("pointerleave", () => marke.classList.add("hidden"));
  // Auf dem Handy gibt es kein Ueberfahren -- da zaehlt das Antippen.
  svg.addEventListener("click", (ev) => {
    const ziel = treffer(ev);
    if (ziel) zeigen(ziel, ev.clientX, ev.clientY);
    else marke.classList.add("hidden");
  });
}

function zeichneKartenzahlen(d) {
  const ziel = $("#d-karte-zahlen");
  ziel.textContent = "";
  const p = d.peers || {};
  const gesamt = (d.bekannt || {}).all_networks;

  const zeile = (k, v, klasse) => {
    const el = document.createElement("div");
    el.className = "zeile" + (klasse ? " " + klasse : "");
    const a = document.createElement("span"); a.className = "k"; a.textContent = k;
    const b = document.createElement("span"); b.className = "v"; b.textContent = v;
    el.append(a, b); ziel.append(el);
  };

  if (!d.tabelle_da) ziel.append(hinweis(t("karte_keine_tabelle"), "warn"));
  else if (d.buch_laeuft && !d.buch_stand)
    ziel.append(hinweis(t("karte_wird_ausgewertet"), ""));

  // Die Zahlen MUESSEN aufgehen. Vorher standen hier vier unabhaengige
  // Zeilen -- 42.812 im Adressbuch, 25.870 angesehen -- und dazwischen
  // klaffte eine Luecke von zehntausend, die nirgends erklaert wurde.
  // Jetzt gliedert sich alles unter das Adressbuch:
  //
  //   Adressbuch                42.812
  //     ohne Ort (Tor …)         6.660      <- haben keinen, dem Zweck nach
  //     mit Ort moeglich        36.152
  //       davon angesehen       30.140      <- Core reicht nur Gutes weiter
  //       einem Land zugeordnet 30.100
  if (gesamt != null) zeile(t("karte_k_bekannt"), zahl(gesamt), "gruppe");
  if (d.ortlos) zeile(t("karte_k_ortlos"), zahl(d.ortlos), "unter");
  if (d.verortbar) zeile(t("karte_k_verortbar"), zahl(d.verortbar), "unter");
  if (d.angesehen) {
    zeile(t("karte_k_angesehen"), zahl(d.angesehen), "unter");
    zeile(t("karte_k_verortet"), zahl(d.verortet), "unter");
  }

  // Ein paar Kuerzel haben weder Flaeche noch Punkt -- unbewohnte Inseln,
  // franzoesische Ueberseegebiete. Sie stehen in der Liste, aber nicht auf
  // der Karte. Das gehoert dazugesagt, sonst stimmen Bild und Zahlen nich
  // ueberein und niemand weiss, warum.
  if (d.ohne_form) zeile(t("karte_k_ohne_form"), zahl(d.ohne_form));
  zeile(t("karte_k_peers"), t("d_peers", {
    aus: p.aufgebaut || 0, ein: p.angenommen || 0,
  }));

  // Was die Boegen auf der Karte bedeuten. Beim letzten Mal standen die
  // Punkte unbeschriftet da, und die erste Rueckfrage war "was sollen diese
  // wirren Punkte eigentlich?". Ein Bild, das man erklaeren muss, erklaert
  // sich hier selbst -- in einem Satz.
  if (d.heimat || d.tabelle_da) {
    const f = document.createElement("p");
    f.className = "fussnote";
    f.textContent = d.heimat
      ? t("karte_linien", { land: landName(d.heimat) })
      : t("karte_linien_ohne_ort");
    ziel.append(f);
  }

  // Waehrend des Erstabgleichs steht hier fast immer 0 von aussen -- und das
  // sieht aus wie eine geschlossene Portfreigabe. Am 27.08.2026 von aussen
  // nachgemessen: der Port IST offen, der Knoten antwortet auch, nur brauch
  // er dafuer Sekunden statt Millisekunden. In Bitcoin Core verarbeite
  // derselbe Thread eingehende Nachrichten, der auch Bloecke verbindet und den
  // Chainstate wegschreibt; waehrend eines solchen Schreibvorgangs geben
  // andere Knoten den Handschlag auf, bevor er dazu kommt.
  //
  // Ohne diesen Satz sucht jeder Nutzer stundenlang den Fehler im Router.
  if (KARTE_ERSTSYNC && !(p.angenommen || 0)) {
    const f = document.createElement("p");
    f.className = "fussnote";
    f.textContent = t("karte_fussnote_erstsync");
    ziel.append(f);
  }

  // Warum "angesehen" kleiner ist als "mit Ort moeglich": Core gibt ueber
  // getnodeaddresses nur weiter, was es fuer gut und aktuell genug haelt, um
  // es anderen Knoten zu nennen. Das ist kein Mangel -- es ist genau die
  // Auswahl, die dieser Knoten dem Netz auch wirklich weiterreicht.
  if (d.angesehen && d.verortbar && d.angesehen < d.verortbar) {
    const f = document.createElement("p");
    f.className = "fussnote";
    f.textContent = t("karte_fussnote_auswahl");
    ziel.append(f);
  }
}

function zeichneKartenrang(laender, hoechster) {
  const ziel = $("#d-karte-rang");
  ziel.textContent = "";
  laender.slice(0, 8).forEach((e) => {
    const li = document.createElement("li");
    if (e.peers > 0) li.className = "nachbar";

    const kuerzel = document.createElement("span");
    kuerzel.className = "kuerzel"; kuerzel.textContent = e.land;

    const balken = document.createElement("span");
    balken.className = "balken";
    const fuellung = document.createElement("span");
    fuellung.style.width =
      (hoechster > 0 ? Math.max(3, e.adressen / hoechster * 100) : 3) + "%";
    balken.append(fuellung);

    const anzahl = document.createElement("span");
    anzahl.className = "anzahl";
    anzahl.textContent = zahl(e.adressen);
    if (e.peers > 0) li.title = peerSatz(e.peers);

    li.append(kuerzel, balken, anzahl);
    ziel.append(li);
  });
}



/* ── Bitcoin-Kurs ───────────────────────────────────────────────────────────
   Aus dem Betrieb, 06.09.2026: "könnten wir bei dem News Feed dann noch oben
   drüber noch ein Bitcoin Chart in USD haben?"

   Der Knoten kennt keinen Kurs -- ein Preis ist eine Meinung des Marktes,
   keine Eigenschaft der Kette. Er kommt also von aussen, und damit ueber Tor.

   Gezeichnet wird von Hand. Eine Diagrammbibliothek waere eine Abhaengigkeit
   fuer eine Linie und eine Flaeche; das hier sind sechzig Zeilen und kein
   Nachladen von irgendwo. */

let KURS_WAEHRUNG = localStorage.getItem("satcortex-kurs-waehrung") || "usd";
let KURS_ZEITRAUM = localStorage.getItem("satcortex-kurs-zeitraum") || "30t";
let KURS_LETZTER = null;

const KURS_ZEICHEN = { usd: "$", eur: "€", gbp: "£" };

/* ── Der Umrechner ────────────────────────────────────────────────────────

   Aus dem Betrieb, 10.09.2026: "dann brauchen wir auch noch mal nen richtigen
   waehrungs rechner .. damit mann auch klar kommt mit den sat und bitcoin
   und waehrungen".

   Vier Dinge sind hier anders als beim ueblichen Satoshi-Rechner:

   1. Satoshi steht OBEN. Wer in Lightning zu Hause sein will, rechnet in
      Sats, nicht in Kommastellen von Bitcoin.
   2. Es gibt EINE Fremdwaehrung mit Umschalter, nicht Euro und Dollar
      nebeneinander. Der Grund steht sogar beim Vorbild dabei: dessen
      direkte Umrechnung zwischen Dollar und Euro laeuft ueber den
      Bitcoin-Kurs und ist "eventuell ungenau". Mit einem Feld je Waehrung,
      jedes aus seinem eigenen Kurs, kann das gar nicht erst passieren.
   3. Die Rueckrichtung steht gross daneben: "1 € = 1.504 sat". Das ist die
      Zahl, an der man Sats zu lesen lernt.
   4. Woher der Kurs kommt und wie alt er ist, steht dabei. Ein Rechner, der
      mit einem drei Stunden alten Kurs rechnet und das verschweigt, ist
      schlimmer als keiner. */

const SAT_JE_BTC = 100000000;
// Mehr als es je geben wird. Daraus wird kein Riegel gegen Tippfehler,
// sondern der Punkt, ab dem eine Zahl nichts mehr bedeutet -- und ab dem
// JavaScripts Ganzzahlen anfangen zu runden.
const BTC_HOECHSTENS = 21000000;

/* Eine getippte Zahl lesen -- und zwar so, wie sie gemeint war.

   Der Fall, an dem sich das entscheidet: "1.000". Auf Deutsch ist das
   tausend, auf Englisch eins Komma null. Also entscheidet die Sprache --
   aber NUR bei genau drei Ziffern hinter einem einzelnen Tausendertrenner.
   "1.5" ist auch auf Deutsch eineinhalb und nicht fuenfzehntausend.

   Was nicht eindeutig zu lesen ist, wird abgelehnt statt geraten. Hier
   geht es um Betraege. */
function zahlLesen(text, sprache) {
  if (typeof text !== "string") return NaN;
  const s = text.replace(/[\s\u00a0\u202f'’_]/g, "");
  if (!s || !/^[0-9.,]+$/.test(s)) return NaN;

  const tausender = sprache === "en" ? "," : ".";
  const komma = s.indexOf(",") >= 0;
  const punkt = s.indexOf(".") >= 0;
  let dezimal = "";
  if (komma && punkt) {
    // Beide da: der hintere trennt die Nachkommastellen.
    dezimal = s.lastIndexOf(",") > s.lastIndexOf(".") ? "," : ".";
  } else if (komma || punkt) {
    const zeichen = komma ? "," : ".";
    const teile = s.split(zeichen);
    const stellen = teile[teile.length - 1].length;
    const einmal = teile.length === 2;
    // Als Tausendertrenner gelesen wird nur, was auch einer sein KANN:
    // das Zeichen der Sprache, drei Ziffern dahinter, hoechstens drei davor.
    // "1234.567" ist auf Deutsch kein sauberer Tausenderpunkt -- also war
    // ein Dezimaltrenner gemeint.
    const tausenderhaft = zeichen === tausender && stellen === 3
      && teile[0].length >= 1 && teile[0].length <= 3;
    dezimal = (einmal && !tausenderhaft) ? zeichen : "";
  }

  // Was uebrig bleibt, sind Tausendertrenner. Ohne Dezimaltrenner ist das
  // der der Sprache -- sonst genau das andere Zeichen.
  const gruppen = dezimal === "" ? tausender : (dezimal === "," ? "." : ",");
  let ganz = s, nach = "";
  if (dezimal) {
    const schnitt = s.lastIndexOf(dezimal);
    ganz = s.slice(0, schnitt);
    nach = s.slice(schnitt + 1);
    // Zwei Dezimaltrenner sind keine Zahl.
    if (nach.indexOf(dezimal) >= 0 || !/^[0-9]*$/.test(nach)) return NaN;
  }
  // Der Vorkommateil darf Tausendertrenner tragen -- aber richtig gesetzte.
  if (gruppen && ganz.indexOf(gruppen) >= 0) {
    const teile = ganz.split(gruppen);
    if (teile[0].length < 1 || teile[0].length > 3) return NaN;
    for (let i = 1; i < teile.length; i++) {
      if (teile[i].length !== 3) return NaN;
    }
    ganz = teile.join("");
  }
  if (!/^[0-9]*$/.test(ganz)) return NaN;
  if (ganz === "" && nach === "") return NaN;
  const wert = Number((ganz || "0") + "." + (nach || "0"));
  return Number.isFinite(wert) ? wert : NaN;
}

/* Eine Zahl hinschreiben -- in der Sprache, die gerade eingestellt ist. */
function zahlSchreiben(wert, stellen, sprache) {
  if (!Number.isFinite(wert)) return "";
  return wert.toLocaleString(sprache === "en" ? "en-US" : "de-DE", {
    minimumFractionDigits: stellen, maximumFractionDigits: stellen,
  });
}

/* Aus einem Feld die anderen beiden ausrechnen.

   Gibt {sat, btc, fiat} zurueck; einzelne Werte koennen NaN sein, wenn kein
   Kurs vorliegt. Ohne gueltige Eingabe kommt null zurueck -- das ist etwas
   anderes als "null Sats". */
function rechnerUmrechnen(feld, wert, kurs) {
  if (!Number.isFinite(wert) || wert < 0) return null;
  let btc;
  if (feld === "sat") btc = Math.round(wert) / SAT_JE_BTC;
  else if (feld === "btc") btc = wert;
  else if (feld === "fiat") {
    if (!Number.isFinite(kurs) || kurs <= 0) return null;
    btc = wert / kurs;
  } else return null;
  if (!Number.isFinite(btc) || btc > BTC_HOECHSTENS) return null;
  return {
    btc: btc,
    sat: Math.round(btc * SAT_JE_BTC),
    fiat: Number.isFinite(kurs) && kurs > 0 ? btc * kurs : NaN,
  };
}
const kursFenster = (z) => t("kf_" + z);

async function ladeKurs(sofort = false) {
  if (ANSICHT !== "news" && ANSICHT !== "rechner"
      && ANSICHT !== "uebersicht" && !sofort) return;
  let d;
  try {
    d = await api(`/kurs?waehrung=${encodeURIComponent(KURS_WAEHRUNG)}`
                  + `&zeitraum=${encodeURIComponent(KURS_ZEITRAUM)}`);
  } catch (e) {
    return;
  }
  KURS_LETZTER = d;
  zeichneKurs(d);
  zeichneKursKurz(d);
  zeichneRechner(d);
  // Beim ersten Oeffnen holt der Server im Hintergrund nach. Einmal
  // nachfassen, statt den Kasten bis zum naechsten Takt leer zu lassen.
  if (!d.verlauf.length && !d.grund) setTimeout(() => ladeKurs(true), 5000);
}

function kursText(wert, waehrung) {
  if (!Number.isFinite(wert)) return "—";
  const zeichen = KURS_ZEICHEN[waehrung] || "";
  return zeichen + wert.toLocaleString(LANG === "en" ? "en-US" : "de-DE",
                                       { maximumFractionDigits: 0 });
}

function zeichneKurs(d) {
  const kasten = $("#kurs-kasten");
  if (!kasten) return;
  kasten.classList.remove("hidden");

  $("#kurs-wert").textContent = kursText(d.kurs, d.waehrung);

  const wechsel = $("#kurs-wechsel");
  if (Number.isFinite(d.wechsel24)) {
    wechsel.textContent = (d.wechsel24 >= 0 ? "+" : "")
      + d.wechsel24.toFixed(2) + " %";
    wechsel.classList.toggle("hoch", d.wechsel24 >= 0);
    wechsel.classList.toggle("runter", d.wechsel24 < 0);
  } else {
    wechsel.textContent = "";
    wechsel.classList.remove("hoch", "runter");
  }

  kursSchalter("#kurs-waehrungen", d.waehrungen, d.waehrung, (w) => {
    KURS_WAEHRUNG = w;
    try { localStorage.setItem("satcortex-kurs-waehrung", w); } catch (e) {}
    ladeKurs(true);
  }, (w) => w.toUpperCase());
  kursSchalter("#kurs-zeitraeume", d.zeitraeume, d.zeitraum, (z) => {
    KURS_ZEITRAUM = z;
    try { localStorage.setItem("satcortex-kurs-zeitraum", z); } catch (e) {}
    ladeKurs(true);
  }, (z) => kursFenster(z));

  zeichneKurslinie(d);

  const fuss = $("#kurs-fuss");
  if (d.grund === "tor_aus") fuss.textContent = t("kurs_tor_aus");
  else if (d.grund) fuss.textContent = d.grund;
  else if (d.boerse) {
    fuss.textContent = t("kurs_quelle", {
      boerse: d.boerse,
      alter: d.stand ? kursAlter(d.stand) : "—",
    });
  } else fuss.textContent = t("kurs_wird_geholt");
}

function kursAlter(stand) {
  const s = Math.max(0, Date.now() / 1000 - stand);
  if (s < 90) return t("kurs_gerade");
  const spanne = s < 5400 ? Math.round(s / 60) + " min"
                          : Math.round(s / 3600) + " h";
  return t("kurs_vor", { spanne });
}

function kursSchalter(wohin, werte, aktiv, beiKlick, beschriften) {
  const ziel = $(wohin);
  if (!ziel) return;
  ziel.textContent = "";
  (werte || []).forEach((w) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "kurs-knopf" + (w === aktiv ? " aktiv" : "");
    b.textContent = beschriften(w);
    b.addEventListener("click", () => beiKlick(w));
    ziel.append(b);
  });
}

/* Die Anzeige des Umrechners.

   Ein Feld wird beim Tippen NIE neu geschrieben -- sonst springt der
   Schreibzeiger ans Ende, und aus "1.5" wird beim vierten Zeichen etwas
   anderes, als man tippen wollte. Geschrieben werden immer nur die anderen
   beiden. */
function rechnerSchreiben(ausser, werte) {
  const felder = {
    sat: [$("#rn-sat"), werte ? zahlSchreiben(werte.sat, 0, LANG) : ""],
    btc: [$("#rn-btc"), werte ? zahlSchreiben(werte.btc, 8, LANG) : ""],
    fiat: [$("#rn-fiat"), werte && Number.isFinite(werte.fiat)
           ? zahlSchreiben(werte.fiat, 2, LANG) : ""],
  };
  for (const name of Object.keys(felder)) {
    const [feld, text] = felder[name];
    if (feld && name !== ausser) feld.value = text;
  }
}

function rechnerKurs() {
  const d = KURS_LETZTER;
  return d && d.waehrung === KURS_WAEHRUNG && Number.isFinite(d.kurs)
    ? d.kurs : NaN;
}

/* Ein Feld wurde getippt. */
function rechnerRechnen(feld) {
  const eingabe = $("#" + (feld === "fiat" ? "rn-fiat" : "rn-" + feld));
  if (!eingabe) return;
  const fehler = $("#rn-fehler");
  const roh = eingabe.value.trim();
  if (!roh) {
    rechnerSchreiben(feld, null);
    fehler.classList.add("hidden");
    return;
  }
  const wert = zahlLesen(roh, LANG);
  const werte = rechnerUmrechnen(feld, wert, rechnerKurs());
  rechnerSchreiben(feld, werte);
  // Zwei verschiedene Gruende, und sie brauchen zwei verschiedene Saetze:
  // eine Zahl, die nicht zu lesen ist -- oder eine, die es nie geben wird.
  fehler.classList.toggle("hidden", !!werte);
  if (!werte) {
    fehler.textContent = Number.isFinite(wert) && wert >= 0
      ? t("rn_zu_gross") : t("rn_unlesbar");
  }
}

/* Kurs, Umschalter und die beiden Merkzahlen. */
function zeichneRechner(d) {
  if (!$("#rn-sat")) return;
  const zeichen = KURS_ZEICHEN[d.waehrung] || d.waehrung.toUpperCase();

  kursSchalter("#rn-waehrungen", d.waehrungen, d.waehrung, (w) => {
    KURS_WAEHRUNG = w;
    try { localStorage.setItem("satcortex-kurs-waehrung", w); } catch (e) {}
    ladeKurs(true);
  }, (w) => w.toUpperCase());

  $("#rn-fiat-titel").textContent = t("rn_fiat", { w: d.waehrung.toUpperCase() });
  $("#rn-je-fiat-bez").textContent = t("rn_je_fiat", { zeichen: zeichen });
  $("#rn-je-btc").textContent = Number.isFinite(d.kurs)
    ? zeichen + " " + zahlSchreiben(d.kurs, 2, LANG) : "—";
  $("#rn-je-fiat").textContent = Number.isFinite(d.kurs) && d.kurs > 0
    ? zahlSchreiben(Math.round(SAT_JE_BTC / d.kurs), 0, LANG) + " sat" : "—";

  const quelle = $("#rn-quelle");
  if (d.grund === "tor_aus") quelle.textContent = t("kurs_tor_aus");
  else if (d.grund) quelle.textContent = d.grund;
  else if (d.boerse) {
    quelle.textContent = t("kurs_quelle", {
      boerse: d.boerse, alter: d.stand ? kursAlter(d.stand) : "—" });
  } else quelle.textContent = t("kurs_wird_geholt");

  // Nach einem Waehrungswechsel oder einem neuen Kurs stimmt der Betrag in
  // der Fremdwaehrung nicht mehr. Die Sats sind der Anker: sie aendern sich
  // durch einen Kurs nicht.
  const satFeld = $("#rn-sat");
  if (satFeld && satFeld.value.trim() && document.activeElement !== satFeld) {
    rechnerRechnen("sat");
  }
  // Dasselbe gilt fuer den Kanalrechner darunter: seine Betraege stehen in
  // Satoshi UND in der Fremdwaehrung. Nach einem Waehrungswechsel stimmte
  // die zweite Haelfte sonst nicht mehr.
  if (document.activeElement !== $("#kkp-groesse")) kanalplanRechnen();
}

/* Die Zeichnung.

   ZWEIMAL NACHGEBESSERT, beide Male weil der Betreiber es im Bild gesehen hat:

   1. Ein festes viewBox="0 0 900 220" mit preserveAspectRatio="none", auf
      1850 Pixel gestreckt -- das streckt auch die SCHRIFT. Die viewBox kommt
      jetzt aus der tatsaechlichen Groesse, eine Einheit ist ein Bildpunkt.
   2. "ich will dann wie in einem richtigen chart auf nen punkt gehen koennen
      mit uhrzeit tag oder so und dann kurs". Eine Linie ohne Ablesbarkeit
      ist ein Bild, kein Werkzeug. Also Fadenkreuz und Sprechblase.

   Weiterhin ohne Diagrammbibliothek: das hier sind ein paar hundert Zeilen
   und kein Nachladen von irgendwo. */

const KURS_NS = "http://www.w3.org/2000/svg";
const KURS_RAND = { oben: 14, unten: 26, links: 8, rechts: 64 };

// Was die letzte Zeichnung hinterlaesst, damit das Fadenkreuz weiss, wo die
// Punkte liegen -- ohne bei jeder Mausbewegung neu zu rechnen.
let KURS_BILD = null;

function kursEl(name, merkmale) {
  const el = document.createElementNS(KURS_NS, name);
  for (const [k, v] of Object.entries(merkmale)) el.setAttribute(k, v);
  return el;
}

/* Eine runde Zahl in der Naehe -- 68.613 wird zu 68.500, nicht zu
   68.612,84. Ein Raster mit krummen Zahlen ist kein Raster. */
function kursStufe(spanne) {
  const roh = spanne / 3;
  const groesse = Math.pow(10, Math.floor(Math.log10(roh)));
  const rest = roh / groesse;
  return groesse * (rest >= 5 ? 5 : rest >= 2 ? 2 : 1);
}

function kursZeitmarke(sekunden, zeitraum) {
  const d = new Date(sekunden * 1000);
  const ort = LANG === "en" ? "en-GB" : "de-DE";
  if (zeitraum === "24h") {
    return d.toLocaleTimeString(ort, { hour: "2-digit", minute: "2-digit" });
  }
  if (zeitraum === "5j" || zeitraum === "1j") {
    return d.toLocaleDateString(ort, { month: "short", year: "2-digit" });
  }
  return d.toLocaleDateString(ort, { day: "2-digit", month: "2-digit" });
}

/* Die volle Angabe fuer die Sprechblase: bei einer Stundenkerze will man
   den Tag UND die Uhrzeit, bei einer Tageskerze das Datum mit Wochentag. */
function kursZeitpunkt(sekunden, zeitraum) {
  const d = new Date(sekunden * 1000);
  const ort = LANG === "en" ? "en-GB" : "de-DE";
  if (zeitraum === "24h") {
    return d.toLocaleString(ort, { weekday: "short", hour: "2-digit",
                                   minute: "2-digit" });
  }
  return d.toLocaleDateString(ort, { weekday: "short", day: "2-digit",
                                     month: "short", year: "numeric" });
}

function zeichneKurslinie(d) {
  const svg = $("#kurs-svg");
  if (!svg) return;
  svg.textContent = "";
  KURS_BILD = null;
  kursBlaseAus();
  const punkte = d.verlauf || [];
  const titel = $("#kurs-titel");

  // Die echte Groesse, nicht eine erfundene. Solange der Kasten versteckt
  // ist, hat er keine -- dann eine brauchbare Annahme, und beim naechsten
  // Zeichnen stimmt es.
  const kasten = svg.getBoundingClientRect();
  const B = Math.max(320, Math.round(kasten.width) || 900);
  const H = Math.max(140, Math.round(kasten.height) || 200);
  svg.setAttribute("viewBox", `0 0 ${B} ${H}`);

  if (punkte.length < 2) {
    if (titel) titel.textContent = t("kurs_kein_verlauf");
    const text = kursEl("text", { x: B / 2, y: H / 2, "text-anchor": "middle",
                                  class: "kurs-leer" });
    text.textContent = d.grund === "tor_aus"
      ? t("kurs_tor_aus_kurz") : t("kurs_wird_geholt");
    svg.append(text);
    return;
  }

  // [Zeit, Schluss, Hoch, Tief] -- Hoch und Tief sind seit 0.44.3 dabei.
  const werte = punkte.map((p) => p[1]);
  const hochs = punkte.map((p) => (p.length > 2 ? p[2] : p[1]));
  const tiefs = punkte.map((p) => (p.length > 3 ? p[3] : p[1]));
  const roh_min = Math.min(...tiefs);
  const roh_max = Math.max(...hochs);
  const luft = (roh_max - roh_min) * 0.10 || Math.max(1, roh_max * 0.004);
  const min = roh_min - luft;
  const max = roh_max + luft;
  const spanne = max - min;

  const x0 = KURS_RAND.links;
  const x1 = B - KURS_RAND.rechts;
  const y0 = KURS_RAND.oben;
  const y1 = H - KURS_RAND.unten;
  const x = (i) => x0 + i * (x1 - x0) / (punkte.length - 1);
  const y = (w) => y1 - (w - min) / spanne * (y1 - y0);

  // ── Raster mit Preisen. Ohne sie ist die Linie eine Form ohne Massstab.
  const stufe = kursStufe(spanne);
  for (let w = Math.ceil(min / stufe) * stufe; w < max; w += stufe) {
    const py = y(w);
    if (py < y0 - 1 || py > y1 + 1) continue;
    svg.append(kursEl("line", { x1: x0, x2: x1, y1: py, y2: py,
                                class: "kurs-raster" }));
    const beschriftung = kursEl("text", { x: x1 + 8, y: py + 4,
                                          class: "kurs-achse" });
    beschriftung.textContent = kursText(w, d.waehrung);
    svg.append(beschriftung);
  }

  // ── Zeitmarken. Bei "24 h" Uhrzeiten, bei "5 J" Jahre.
  const marken = Math.min(6, Math.max(2, Math.floor(B / 150)));
  for (let m = 0; m < marken; m++) {
    const i = Math.round(m * (punkte.length - 1) / (marken - 1));
    const px = x(i);
    const text = kursEl("text", {
      x: Math.min(x1, Math.max(x0, px)), y: H - 8, class: "kurs-achse",
      "text-anchor": m === 0 ? "start" : m === marken - 1 ? "end" : "middle",
    });
    text.textContent = kursZeitmarke(punkte[i][0], d.zeitraum);
    svg.append(text);
  }

  const steigt = werte[werte.length - 1] >= werte[0];
  const art = steigt ? "" : " runter";

  // ── Das Band zwischen Hoch und Tief. Bei einer Tageskerze ist die
  //    Tagesspanne die interessantere Zahl als der Schlusskurs allein --
  //    und ohne sie sieht ein ruhiger Monat aus wie ein zackiger.
  const spannbar = hochs.some((h, i) => h > tiefs[i]);
  if (spannbar) {
    const oben = punkte.map((p, i) => `${x(i).toFixed(1)},${y(hochs[i]).toFixed(1)}`);
    const unten = punkte.map((p, i) => `${x(i).toFixed(1)},${y(tiefs[i]).toFixed(1)}`)
      .reverse();
    svg.append(kursEl("path", {
      d: `M${oben.join(" L")} L${unten.join(" L")} Z`,
      class: "kurs-band" + art,
    }));
  }

  const linie = punkte.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`);

  // Ein weicher Verlauf statt einer flachen Fuellung -- unten laeuft die
  // Flaeche aus, damit sie sich nicht mit dem Hintergrund beisst.
  const kennung = "kursverlauf" + (steigt ? "-hoch" : "-runter");
  const defs = kursEl("defs", {});
  const farbe = kursEl("linearGradient", { id: kennung, x1: 0, y1: 0,
                                           x2: 0, y2: 1 });
  farbe.append(kursEl("stop", { offset: "0%", class: "kurs-fuell-oben" + art }));
  farbe.append(kursEl("stop", { offset: "100%",
                                class: "kurs-fuell-unten" + art }));
  defs.append(farbe);
  svg.append(defs);

  svg.append(kursEl("path", {
    d: `M${linie[0]} L${linie.join(" L")} L${x(punkte.length - 1).toFixed(1)},`
       + `${y1} L${x0.toFixed(1)},${y1} Z`,
    fill: `url(#${kennung})`, stroke: "none",
  }));
  svg.append(kursEl("path", { d: `M${linie.join(" L")}`,
                              class: "kurs-linie" + art }));

  // ── Das Fadenkreuz. Erst versteckt, es folgt dem Zeiger.
  const kreuz = kursEl("g", { class: "kurs-kreuz", visibility: "hidden" });
  kreuz.append(kursEl("line", { x1: 0, x2: 0, y1: y0, y2: y1,
                                class: "kurs-kreuz-strich" }));
  kreuz.append(kursEl("circle", { cx: 0, cy: 0, r: 4.5,
                                  class: "kurs-kreuz-punkt" + art }));
  svg.append(kreuz);

  // Der letzte Punkt bekommt einen Kopf: dort steht die Gegenwart.
  const letzter = punkte.length - 1;
  svg.append(kursEl("circle", { cx: x(letzter).toFixed(1),
                                cy: y(werte[letzter]).toFixed(1), r: 3.5,
                                class: "kurs-punkt" + art }));

  KURS_BILD = { d, punkte, x, y, x0, x1, y0, y1, B, H, kreuz, art };

  if (titel) {
    titel.textContent = t("kurs_bildbeschreibung", {
      von: kursText(werte[0], d.waehrung),
      bis: kursText(werte[letzter], d.waehrung),
      fenster: kursFenster(d.zeitraum),
    });
  }
}

/* ── Ablesen: Fadenkreuz und Sprechblase ───────────────────────────────────
   Der Betreiber: "ich will dann wie in einem richtigen chart auf nen punkt gehen
   koennen mit uhrzeit tag oder so und dann kurs". Genau das.

   Bedienbar mit Maus, mit dem Finger und mit der Tastatur -- Letzteres nicht
   aus Pflichtgefuehl: ein Bild, das nur die Maus lesen kann, ist fuer ein
   Vorleseprogramm gar nichts. */

function kursIndexBei(klientX) {
  if (!KURS_BILD) return -1;
  const svg = $("#kurs-svg");
  const kasten = svg.getBoundingClientRect();
  // Von Bildschirm- auf viewBox-Koordinaten. Beide sind hier gleich gross,
  // aber nur solange -- der Dreisatz kostet nichts und haelt.
  const px = (klientX - kasten.left) / kasten.width * KURS_BILD.B;
  const { x0, x1, punkte } = KURS_BILD;
  const anteil = (px - x0) / (x1 - x0);
  return Math.max(0, Math.min(punkte.length - 1,
                              Math.round(anteil * (punkte.length - 1))));
}

function kursZeigeBei(index) {
  if (!KURS_BILD || index < 0) return;
  const { d, punkte, x, y, y0, y1, B, kreuz } = KURS_BILD;
  const p = punkte[index];
  const px = x(index);
  const py = y(p[1]);

  kreuz.setAttribute("visibility", "visible");
  const strich = kreuz.querySelector(".kurs-kreuz-strich");
  strich.setAttribute("x1", px.toFixed(1));
  strich.setAttribute("x2", px.toFixed(1));
  strich.setAttribute("y1", y0);
  strich.setAttribute("y2", y1);
  const punkt = kreuz.querySelector(".kurs-kreuz-punkt");
  punkt.setAttribute("cx", px.toFixed(1));
  punkt.setAttribute("cy", py.toFixed(1));

  const blase = $("#kurs-blase");
  if (!blase) return;
  blase.textContent = "";

  const wann = document.createElement("div");
  wann.className = "blase-zeit";
  wann.textContent = kursZeitpunkt(p[0], d.zeitraum);
  blase.append(wann);

  const kurs = document.createElement("div");
  kurs.className = "blase-kurs";
  kurs.textContent = kursText(p[1], d.waehrung);
  blase.append(kurs);

  // Hoch und Tief nur, wenn sie sich vom Schlusskurs unterscheiden --
  // sonst stuende dort dreimal dieselbe Zahl.
  if (p.length > 3 && (p[2] > p[1] || p[3] < p[1])) {
    const spanne = document.createElement("div");
    spanne.className = "blase-spanne";
    spanne.textContent = t("kurs_spanne", {
      tief: kursText(p[3], d.waehrung), hoch: kursText(p[2], d.waehrung),
    });
    blase.append(spanne);
  }

  blase.hidden = false;
  // Nach links kippen, sobald sie sonst rechts hinausliefe.
  const breite = blase.offsetWidth || 150;
  const links = px + 14 + breite > B ? px - breite - 14 : px + 14;
  blase.style.left = Math.max(0, links).toFixed(0) + "px";
  blase.style.top = Math.max(0, Math.min(KURS_BILD.H - 70, py - 34)) + "px";
}

function kursBlaseAus() {
  const blase = $("#kurs-blase");
  if (blase) blase.hidden = true;
  if (KURS_BILD && KURS_BILD.kreuz) {
    KURS_BILD.kreuz.setAttribute("visibility", "hidden");
  }
}

let KURS_TASTENINDEX = -1;

function kursAblesenFolgen() {
  const svg = $("#kurs-svg");
  if (!svg) return;

  svg.addEventListener("pointermove", (e) => {
    if (!KURS_BILD) return;
    kursZeigeBei(kursIndexBei(e.clientX));
  });
  svg.addEventListener("pointerleave", kursBlaseAus);
  // Beim Tippen bleibt die Angabe stehen, bis man woanders hintippt --
  // ein Finger hat kein "verlassen".
  svg.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" && KURS_BILD) {
      kursZeigeBei(kursIndexBei(e.clientX));
    }
  });

  // Tastatur: links und rechts wandern, Pos1/Ende springen.
  svg.setAttribute("tabindex", "0");
  svg.addEventListener("keydown", (e) => {
    if (!KURS_BILD) return;
    const letzte = KURS_BILD.punkte.length - 1;
    if (KURS_TASTENINDEX < 0) KURS_TASTENINDEX = letzte;
    const schritt = e.shiftKey ? 10 : 1;
    let neu = KURS_TASTENINDEX;
    if (e.key === "ArrowLeft") neu -= schritt;
    else if (e.key === "ArrowRight") neu += schritt;
    else if (e.key === "Home") neu = 0;
    else if (e.key === "End") neu = letzte;
    else if (e.key === "Escape") { kursBlaseAus(); KURS_TASTENINDEX = -1; return; }
    else return;
    e.preventDefault();
    KURS_TASTENINDEX = Math.max(0, Math.min(letzte, neu));
    kursZeigeBei(KURS_TASTENINDEX);
  });
  svg.addEventListener("blur", kursBlaseAus);

  // Den eigenen Kasten beobachten. Es gibt ihn seit Safari 13.1; fehlt er,
  // bleibt es beim Fenster-Zuhoerer -- kein Grund, deswegen gar nicht zu
  // laufen.
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(kursNeuZeichnenBald).observe(svg);
  }
}

/* Neu zeichnen, wenn sich die Groesse aendert -- die viewBox haengt an der
   tatsaechlichen Breite, also muss sie mitgehen.

   Ein resize-Zuhoerer am Fenster reicht dafuer NICHT. Der Kasten kann seine
   Groesse auch ohne Fensteraenderung wechseln: beim Einblenden der Ansicht,
   beim Auf- und Zuklappen der Quellenliste, oder wenn der Browser die Seite
   gar nicht darstellt und die Breite 0 meldet. Dann zeichnet er mit der
   Notannahme von 900 und behielte sie, bis jemand das Fenster anfasst --
   beim Pruefen am 06.09.2026 genau so gemessen: Breite 0, viewBox 900.

   Ein ResizeObserver sieht den eigenen Kasten und ist genau dafuer da. */
let kursNeuzeichnen;
function kursNeuZeichnenBald() {
  clearTimeout(kursNeuzeichnen);
  kursNeuzeichnen = setTimeout(() => {
    if (!KURS_LETZTER) return;
    const svg = $("#kurs-svg");
    if (!svg) return;
    const breite = Math.round(svg.getBoundingClientRect().width);
    if (!breite) return;                    // unsichtbar -- spaeter erneut
    const gezeichnet = (svg.getAttribute("viewBox") || "").split(" ")[2];
    if (Number(gezeichnet) === breite) return;   // schon richtig
    zeichneKurslinie(KURS_LETZTER);
  }, 120);
}

addEventListener("resize", kursNeuZeichnenBald);

/* ── Nachrichten ────────────────────────────────────────────────────────────
   Aus dem Betrieb, 06.09.2026, nachdem er die Chat-Idee selbst verworfen hatte:
   "gibt ja schon viele chats und foren ... was aber vielleicht meinen Cortex
   von anderen unterscheiden wuerde waere ein Nachrichten-Feed". Und am Tag
   darauf der Zuschnitt, der alles bestimmt hat: "wenn ich in Algerien sitze
   und habe die Software am Laufen, bringt mir Blocktrainer nichts."

   Deshalb Sprache statt Land. Das Kuerzel kommt aus der Weltkarte.

   ZWEI REGELN GELTEN HIER OHNE AUSNAHME:

   1. Fremder Text wird NIE als HTML gezeichnet. Alles geht ueber
      textContent. Kein innerHTML mit etwas, das von aussen kam.
   2. Keine fremden Bilder. Der Zerleger im Backend entfernt sie bereits;
      hier entsteht auch keins. Ein Vorschaubild von einem Verlagsserver
      meldete die echte Adresse des Lesers und machte den Tor-Umweg in
      derselben Sekunde zunichte. */

let NEWS_QUELLEN_OFFEN = false;
let NEWS_LETZTE = null;

async function ladeNews(sofort = false) {
  if (ANSICHT !== "news" && !sofort) return;
  let d;
  try {
    d = await api("/nachrichten");
  } catch (e) {
    return;
  }
  NEWS_LETZTE = d;
  zeichneNews(d);
}

function zeichneNews(d) {
  const aus = $("#news-aus");
  const tor = $("#news-tor");
  const kopf = $("#news-kopf");
  aus.classList.toggle("hidden", !!d.aktiv);
  kopf.classList.toggle("hidden", !d.aktiv);

  // Eingeschaltet, aber Tor aus: der Feed holt bewusst nichts. Das gehoert
  // gesagt -- sonst sieht es aus wie "es kommt nichts an".
  const torFehlt = d.aktiv && d.quellen.some((q) => q.grund === "tor_aus");
  tor.classList.toggle("hidden", !torFehlt);

  $("#news-weit").checked = !!d.weit;

  const herkunft = $("#news-herkunft");
  herkunft.textContent = d.land
    ? t("news_herkunft", { land: landName(d.land), sprache: d.sprache })
    : t("news_herkunft_unbekannt");

  // Ein duenner Feed sieht aus wie "die schreiben nichts". Wenn Quellen
  // abgewiesen werden, gehoert das nach OBEN und nicht in einen Kasten, den
  // man erst aufklappen muss.
  const abgewiesen = $("#news-abgewiesen");
  const zahl = d.abgewiesen || 0;
  abgewiesen.classList.toggle("hidden", !d.aktiv || zahl === 0);
  if (zahl) {
    const an = (d.quellen || []).filter((q) => q.an).length;
    abgewiesen.textContent = t("news_abgewiesen", { zahl, an });
  }

  const zaehler = $("#news-zaehler");
  if (zaehler) {
    zaehler.hidden = !d.ungelesen;
    zaehler.textContent = d.ungelesen > 99 ? "99+" : String(d.ungelesen || "");
  }

  zeichneNewsListe(d.beitraege || []);
  const leer = $("#news-leer");
  leer.classList.toggle("hidden", !d.aktiv || (d.beitraege || []).length > 0);
  // Ohne Datenbank gibt es keinen Verlauf -- die Meldungen waeren nach jedem
  // Neustart weg. Das gehoert gesagt, statt dass sich jemand wundert.
  leer.textContent = d.speicher === false
    ? t("news_speicher_fehlt") : t("news_leer");
  if (NEWS_QUELLEN_OFFEN) zeichneNewsQuellen(d.quellen || []);
}

function zeichneNewsListe(beitraege) {
  const ziel = $("#news-liste");
  ziel.textContent = "";
  beitraege.forEach((b) => {
    const li = document.createElement("li");
    li.className = "news-eintrag" + (b.gelesen ? " gelesen" : "");

    const a = document.createElement("a");
    // Der Verweis wurde im Backend auf http/https geprueft. Hier kommen die
    // drei Merkmale dazu, die den Klick sauber halten:
    //   noopener/noreferrer -- die Zielseite bekommt kein Fenster-Handle
    //   referrerpolicy      -- und erfaehrt nicht, WOHER der Klick kam.
    // Ohne das letzte stuende im Referrer die interne Adresse des Knotens,
    // etwa http://192.168.178.10:3333/ -- man teilte dem Verlag also seine
    // Heimnetzadresse mit.
    a.href = b.verweis;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.referrerPolicy = "no-referrer";
    a.className = "news-titel";
    a.textContent = b.titel;                 // textContent, nicht innerHTML
    a.addEventListener("click", () => newsGelesen(b.kennung, li));

    const zeile = document.createElement("div");
    zeile.className = "news-zeile";
    const quelle = document.createElement("span");
    quelle.className = "news-quelle";
    quelle.textContent = b.quellenname;
    zeile.append(quelle);

    if (b.zeitpunkt) {
      const wann = document.createElement("span");
      wann.className = "dim";
      wann.textContent = newsZeit(b.zeitpunkt);
      zeile.append(wann);
    }
    if (b.bezahlschranke) {
      const schranke = document.createElement("span");
      schranke.className = "marke";
      schranke.textContent = t("news_bezahlschranke");
      zeile.append(schranke);
    }

    li.append(a, zeile);
    if (b.anriss) {
      const p = document.createElement("p");
      p.className = "news-anriss";
      p.textContent = b.anriss;              // ebenfalls als Text
      li.append(p);
    }
    ziel.append(li);
  });
}

function newsZeit(sekunden) {
  const d = new Date(sekunden * 1000);
  const alter = (Date.now() - d.getTime()) / 1000;
  if (alter < 3600) return Math.max(1, Math.round(alter / 60)) + " min";
  if (alter < 86400) return Math.round(alter / 3600) + " h";
  return d.toLocaleDateString(LANG === "en" ? "en-GB" : "de-DE",
                              { day: "2-digit", month: "2-digit" });
}

async function newsGelesen(kennung, li) {
  if (li) li.classList.add("gelesen");
  try {
    await api("/nachrichten/gelesen?kennung=" + encodeURIComponent(kennung),
              "POST");
  } catch (e) { /* Gelesen-Merken ist Beiwerk, kein Grund fuer eine Meldung */ }
  const z = $("#news-zaehler");
  if (!z) return;
  const offen = Math.max(0, parseInt(z.textContent, 10) - 1 || 0);
  z.hidden = !offen;
  z.textContent = offen ? String(offen) : "";
}

function zeichneNewsQuellen(quellen) {
  const ziel = $("#news-quellenliste");
  ziel.textContent = "";
  quellen.forEach((q) => {
    const zeile = document.createElement("label");
    zeile.className = "quellenzeile";

    const haken = document.createElement("input");
    haken.type = "checkbox";
    haken.checked = !!q.an;
    haken.addEventListener("change", () => newsQuelleSchalten(q.kennung,
                                                             haken.checked));

    const name = document.createElement("span");
    name.className = "quellenname";
    name.textContent = q.name;               // auch eigene Namen als Text

    const marken = document.createElement("span");
    marken.className = "quellenmarken";
    const art = document.createElement("span");
    art.className = "marke " + q.art;
    art.textContent = t(q.art === "leit" ? "news_leit" : "news_fach");
    marken.append(art);
    if (q.sprache && q.sprache !== "??") {
      const sp = document.createElement("span");
      sp.className = "marke dim";
      sp.textContent = q.sprache.toUpperCase();
      marken.append(sp);
    }
    if (q.bezahlschranke) {
      const bs = document.createElement("span");
      bs.className = "marke";
      bs.textContent = t("news_bezahlschranke");
      marken.append(bs);
    }
    // Cloudflare weist Tor-Ausgangsknoten haeufig ab, und wir fragen
    // ausschliesslich ueber Tor. Kein sicheres Nein -- aber der Unterschied
    // zwischen "kommt vermutlich an" und "kann klappen".
    if (q.hinter_cloudflare) {
      const cf = document.createElement("span");
      cf.className = "marke cf";
      cf.textContent = t("news_cf");
      cf.title = t("news_cf_d");
      marken.append(cf);
    }

    // Der Zustand. Eine stumme Quelle sieht sonst aus wie eine, die nichts
    // schreibt -- genau der Fehler, der bei der Versionsabfrage tagelang
    // "Noch nicht nachgesehen" stehen liess, obwohl jedes Mal gefragt wurde.
    const lage = document.createElement("span");
    lage.className = "quellenlage dim";
    if (!q.an) lage.textContent = t("news_quelle_aus");
    else if (q.grund) { lage.textContent = q.grund; lage.classList.add("warn"); }
    else if (q.gelungen) {
      lage.textContent = t("news_geholt", {
        zahl: q.beitraege, wann: kursAlter(q.gelungen),
      });
    } else lage.textContent = t("news_ungeprueft");

    zeile.append(haken, name, marken, lage);
    ziel.append(zeile);
  });
}

async function newsSpeichern(aenderung) {
  const d = NEWS_LETZTE || {};
  const quellen = d.quellen || [];
  // Gemerkt wird der WIDERSPRUCH zur Werksvorgabe, nicht die Auswahl. Wer
  // die eingeschalteten speichert, sperrt jede spaeter hinzugefuegte Quelle
  // fuer immer aus -- am 06.09.2026 auf dem Knoten im Betrieb genau so passiert.
  const wahl = {
    aktiv: d.aktiv || false,
    weit: d.weit || false,
    abgewaehlt: quellen.filter((q) => !q.an && q.ab_werk).map((q) => q.kennung),
    zugewaehlt: quellen.filter((q) => q.an && !q.ab_werk && !q.eigen)
      .map((q) => q.kennung),
    eigene: quellen.filter((q) => q.eigen).map((q) => ({
      adresse: q.adresse || "", name: q.name,
    })),
    ...aenderung,
  };
  try {
    await api("/nachrichten/einstellungen", "POST", wahl);
  } catch (e) {
    return;
  }
  // Nach dem Einschalten laeuft der erste Abruf im Hintergrund. Kurz warten,
  // sonst zeigt die frisch geladene Ansicht noch die leere Liste und sieht
  // aus, als haette der Schalter nichts bewirkt.
  await ladeNews(true);
  if (wahl.aktiv && !(NEWS_LETZTE.beitraege || []).length) {
    setTimeout(() => ladeNews(true), 4000);
  }
}

function newsQuelleSchalten(kennung, an) {
  const d = NEWS_LETZTE || { quellen: [] };
  // Erst den Stand im Gedaechtnis nachziehen, dann daraus die beiden Mengen
  // ableiten -- so gibt es nur EINE Wahrheit.
  const q = d.quellen.find((x) => x.kennung === kennung);
  if (q) q.an = an;
  newsSpeichern({});
}

async function newsQuelleSuchen() {
  const feld = $("#news-eigene-adresse");
  const ziel = $("#news-gefunden");
  const adresse = feld.value.trim();
  ziel.textContent = "";
  if (!adresse) return;
  let d;
  try {
    d = await api("/nachrichten/quelle-suchen", "POST", { adresse });
  } catch (e) {
    return;
  }
  if (!d.gefunden.length) {
    ziel.textContent = d.grund === "tor_aus"
      ? t("news_tor_text") : t("news_kein_feed");
    return;
  }
  const titel = document.createElement("span");
  titel.textContent = t("news_gefunden") + " ";
  ziel.append(titel);
  d.gefunden.forEach((url) => {
    const knopf = document.createElement("button");
    knopf.className = "btn ghost";
    knopf.textContent = url;                 // gefundene Adresse als Text
    knopf.addEventListener("click", () => newsEigeneNehmen(url));
    ziel.append(knopf);
  });
}

function newsEigeneNehmen(adresse) {
  const d = NEWS_LETZTE || { quellen: [] };
  const eigene = d.quellen.filter((q) => q.eigen)
    .map((q) => ({ adresse: q.adresse || "", name: q.name }));
  let name = adresse;
  try { name = new URL(adresse).hostname.replace(/^www\./, ""); } catch (e) {}
  eigene.push({ adresse, name });
  newsSpeichern({ eigene });
  $("#news-eigene-adresse").value = "";
  $("#news-gefunden").textContent = "";
}

function newsFolgen() {
  $("#news-einschalten").addEventListener("click",
    () => newsSpeichern({ aktiv: true }));
  $("#news-weit").addEventListener("change", (e) =>
    newsSpeichern({ weit: e.target.checked }));
  $("#news-alle-gelesen").addEventListener("click", async () => {
    try { await api("/nachrichten/gelesen", "POST"); } catch (e) { return; }
    ladeNews(true);
  });
  $("#news-quellen-auf").addEventListener("click", () => {
    NEWS_QUELLEN_OFFEN = !NEWS_QUELLEN_OFFEN;
    $("#news-quellen").classList.toggle("hidden", !NEWS_QUELLEN_OFFEN);
    if (NEWS_QUELLEN_OFFEN && NEWS_LETZTE) {
      zeichneNewsQuellen(NEWS_LETZTE.quellen || []);
    }
  });
  $("#news-suchen").addEventListener("click", newsQuelleSuchen);
  $("#news-eigene-adresse").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); newsQuelleSuchen(); }
  });
}

/* ── Navigation: eine Ebene ─────────────────────────────────────────────────
   Der erste Entwurf legte alles in eine Rolle untereinander -- zehn gleich
   schwere Kaesten. Der zweite trennte in Reiter oben (Bitcoin | Lightning |
   Welt) UND Abschnitte in der Seitenleiste. Das war eine Ebene zu viel: fuer
   zehn Ansichten zwei Menues, der halbe Bestand jeweils unsichtbar, und ein
   Wechsel von "Bloecke" zu "Kanaele" kostete zwei Klicks an zwei
   verschiedenen Bildschirmraendern.

   Jetzt traegt die Seitenleiste alles, nach Gruppen beschriftet. Eine
   Ansicht, ein Klick -- und man sieht auf einen Blick, was es ueberhaupt
   gibt. */

let ANSICHT = "uebersicht";
// So viele Zeilen holt die Protokoll-Ansicht. Genug, um einen
// Startvorgang ganz zu sehen, und wenig genug, dass die Seite nicht
// an der Darstellung haengt.
const LOG_ZEILEN = 400;

function zeigeAnsicht(name) {
  ANSICHT = name;
  $$(".inhalt > section").forEach((s2) =>
    s2.classList.toggle("hidden", s2.dataset.ansicht !== name));
  $$(".seitenleiste button").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.ansicht === name));
  // Der Grund weiss, ob er hervortreten soll.
  document.body.classList.toggle("ansicht-netz", name === "netz");
  document.body.classList.toggle("ansicht-welt", name === "welt");
  if (name !== "welt" && LAND_OFFEN) schliesseLand();
  // Beim Wechsel sofort holen statt bis zum naechsten Takt zu warten --
  // sonst sieht man erst einmal die Zahlen von vorhin.
  if (name === "mempool" || name === "bloecke") ladeAuswertung(true);
  if (name === "bloecke") { ladePoolAnteile(); adresseStandLaden(); }
  if (name === "netz") ladeKarte(true);
  if (name === "einstellungen") {
    ladeEinstellungen(); ladeRpcZugang(); knotennameLaden(); pinLaden();
  }
  if (name === "logs") ladeLogs(true);
  if (name === "news") { ladeNews(true); ladeKurs(true); }
  if (name === "rechner") { ladeKurs(true); ladeKanalrechner(); }
  if (name === "welt") {
    ladeKarte(true);
    ladeWelt(true);
    // Erst hier bekommt der Streifen eine Groesse. Die Beobachtung allein
    // reicht nicht: sie war beim Anmelden registriert, als er noch
    // ausgeblendet war und gar keinen Kasten hatte.
    //
    // Direkt, nicht ueber requestAnimationFrame. Der sieht verlockend
    // richtig aus, laeuft aber NICHT, solange das Fenster im Hintergrund
    // liegt -- im Pruefstand nachgestellt: visibilityState "hidden", und der
    // Rueckruf kam nie. Wer die Ansicht in einem Hintergrundreiter wechselt,
    // haette dann fuer immer den Naeherungswert behalten. Das Auslesen der
    // Kastenmasse erzwingt ohnehin einen frischen Umbruch, der Wert stimmt
    // also sofort.
    messeWeltstreifen();
  }
  // Vier Lightning-Ansichten seit dem 10.09.2026, und sie haben jetzt
  // klare Zustaendigkeiten: Wallet = das Geld, Kanaele = die Verbindungen,
  // Knoten = die Identitaet, Einrichtung = alles, was man EINMAL tut.
  if (name === "ln-wallet") {
    ladeLightning(true); ladeLightningKanaele(); ladeBewegungen();
    // Ohne das wuesste das Senden nicht, ob es nach einer PIN fragen muss.
    pinLaden();
  }
  if (name === "ln-kanaele") {
    ladeLightning(true); ladeLightningKanaele(); wachtuermeLaden();
    ladeWegwissen();
    durchgangLaden();
    // Oeffnen, Schliessen und Umschichten fragen hier nach der PIN.
    // DER BEFUND VOM 24.09.2026: dieser Aufruf fehlte. Wer nach dem
    // Anmelden direkt hierher kam, sah kein Feld und bekam trotzdem
    // "Dafuer braucht es deine PIN."
    pinLaden();
  }
  if (name === "ln-knoten") ladeLightningKanaele();
  if (name === "ln-einrichtung") {
    ladeWallet(); ladeSicherung(); ladeLightningKanaele(); entsperrwegLaden();
    // Ohne das wuesste die Loesch-Abfrage nicht, ob sie nach einer PIN
    // fragen muss -- und liesse das Feld weg, obwohl der Server sie
    // verlangt.
    pinLaden();
  }
}

/* ── "Warum dauert das so lange?" ───────────────────────────────────────────
   Die Messung laeuft NICHT im Takt mit: sie beschreibt die Ablagen wirklich.
   Ein Knopf, ein Ergebnis -- und die Bewertung kommt vom Backend, wo die
   Schwellen neben den Messwerten stehen. */

/* ── Lightning ──────────────────────────────────────────────────────────────
   Drei Zeilen, die zusammen eine Frage beantworten: kann ich jetzt anfangen?
   Getrennt betrachtet sagt keine davon etwas -- ein laufender Dienst ohne
   fertige Kette nuetzt nichts, und eine fertige Kette ohne laufenden Diens
   auch nicht. */

// Ob die Uebersicht schon einmal eine Antwort hatte. Nur beim ersten
// Mal je Seitenaufruf wird der Ladezustand gezeigt.
let UEBERSICHT_GESEHEN = false;

let LN_STAND = 0;

async function ladeLightning(erzwingen) {
  const jetzt = Date.now();
  if (!erzwingen && jetzt - LN_STAND < 30000) return;
  LN_STAND = jetzt;
  try {
    zeichneLightning(await api("/lightning"));
  } catch (e) {
    if (e && e.abgemeldet) return;
    LN_STAND = 0;                             // beim naechsten Mal erneu
  }
}

function zeichneLightning(d) {
  zeichneLightningKurz(d);
  const dienst = $("#d-ln-dienst");
  if (!dienst || !d || !d.eingerichtet) return;

  dienst.textContent = t("ln_d_" + ((d.dienst || {}).zustand || "unkonfiguriert"));
  $("#d-ln-wallet").textContent = t("ln_w_" + ((d.knoten || {}).stand || "aus"));
  // "kette_bereit", nicht "kette_berei". Das fehlende t machte den Ausdruck
  // dauerhaft undefined -- die Kopfzeile haette auch nach dem fertigen
  // Erstabgleich fuer immer "wird noch abgeglichen" gesagt, und der Hinweis
  // darunter genauso. Gefunden am 03.09.2026 im Pruefstand, an einem Knoten,
  // dessen Kette nachweislich stand.
  $("#d-ln-kette").textContent = d.kette_bereit
    ? t("ln_k_bereit")
    : t("ln_k_sync", { h: zahl(d.hoehe || 0) });

  // Der Satz darunter sagt, was als Naechstes zu tun ist -- und was gerade
  // NICHT zu tun ist. Ohne ihn liest man drei Zeilen und weiss danach immer
  // noch nicht, ob man warten soll oder etwas kaputt ist.
  // Er kannte bis zum 09.09.2026 NUR die Kette und nie den Wallet-Zustand.
  // Der Betreiber hatte seine Wallet laengst angelegt und las hier weiter "der
  // naechste Schritt ist die Wallet" -- ein Satz, der schlicht nicht mehr
  // stimmte. "das stimmt ja auch nicht habe ja alles gemacht".
  const lnstand = (d.knoten || {}).stand || "aus";
  $("#d-ln-hinweis").textContent =
      !d.kette_bereit ? t("ln_hinweis_sync")
    : lnstand === "keine_wallet" ? t("ln_hinweis_bereit")
    : lnstand === "gesperrt" ? t("ln_hinweis_gesperrt")
    : lnstand === "bereit" ? t("ln_hinweis_laeuft")
    : t("ln_hinweis_startet");
}

/* ── Lightning: Kanaele und Graph ───────────────────────────────────────── */

async function ladeLightningKanaele() {
  let d;
  try {
    d = await api("/lightning/kanaele");
  } catch (e) {
    if (e && e.abgemeldet) return;
    return;
  }
  const bereit = d.stand === "bereit";
  if (!bereit) zeichneVerbindungen(null);
  // Solange LND nicht laeuft, bleibt hier NICHTS stehen. Leere Kacheln mi
  // Nullen sehen aus wie Daten und sind keine.
  for (const id of ["#ln-ich", "#ln-guthaben", "#ln-kanalliste", "#ln-weiter",
                    "#ln-wachturm"]) {
    // ln-schliessen und ln-schichten haengen an der Kanalzahl, nicht am
    // Dienst -- die schalten sich beim Zeichnen der Liste selbst.
    $(id).classList.toggle("hidden", !bereit);
  }
  // Einzahlen steht unter "Wallet", Gebuehren unter "Kanaele" -- beide
  // haengen an denselben Daten, deshalb hier mit.
  for (const id of ["#w-bewegungen", "#w-einzahlen", "#w-senden",
                    "#w-empfangen", "#w-gebuehren",
                    "#w-zahlen", "#ln-oeffnen"]) {
    const feld = $(id);
    if (feld) feld.classList.toggle("hidden", !bereit);
  }
  // Und wenn nichts davon dasteht, sagt die Kanaele-Ansicht warum. Die
  // Kopfzeile mit Dienst/Wallet/Kette sitzt seit dem Umbau unter "Wallet";
  // ohne diesen Satz waere hier nur eine leere Seite.
  $("#ln-kanaele-leer").classList.toggle("hidden", bereit);
  // Die Gebuehrenlage haengt NICHT an LND -- sie kommt aus dem eigenen
  // bitcoind. Sie gehoert deshalb auch dann hin, wenn Lightning noch gar
  // nicht laeuft: genau dann plant man ja seinen ersten Kanal.
  zeichneKanalkosten(d.kanalkosten);
  if (!bereit) return;
  fuelleGebuehrenauswahl(d.kanaele || []);
  ladeNetzgebuehren();
  if (d.knoten) {
    zeichneLnIch(d.knoten);
    // Die Betriebsart kommt aus der Antwort, nicht aus LND -- sie ist
    // unsere Einstellung und nicht sein Zustand.
    zeichneEigeneAdresse({ ...d.knoten, sichtbarkeit: d.sichtbarkeit,
                           veraltet: !!d.knoten_veraltet });
    zeichneKennungswechsel(d.kennung_vorher, (d.knoten || {}).kennung);
  } else {
    // OHNE getinfo wurde der Adresskasten bisher gar nicht angefasst: er
    // blieb leer, ohne ein Wort dazu. Aus dem Betrieb, 11.09.2026: "aber es wird
    // mir noch keine verbindungs adresse angezeigt". Eine leere Flaeche
    // ohne Grund ist die schlechteste aller Auskuenfte.
    zeichneEigeneAdresse({ adressen: [], sichtbarkeit: d.sichtbarkeit,
                           beschaeftigt: true });
  }
  zeichneGegenstellenwege();
  if (d.guthaben) zeichneLnGuthaben(d.guthaben);
  zeichneLnKanaele(d.kanaele || []);
  if (d.weiterleitungen) zeichneLnWeiterleitungen(d.weiterleitungen);
  zeichneLnNetz(d.netz, d.kanaele || [], d.knoten);
  zeichneVerbindungen(d.verbindungen);
}

function kurz(schluessel) {
  // 66 Zeichen sind keine Auskunft, sondern eine Wand. Anfang und Ende
  // genuegen, um zwei Knoten auseinanderzuhalten.
  return schluessel.length > 20
    ? schluessel.slice(0, 10) + "…" + schluessel.slice(-6)
    : schluessel;
}

// Wo man Gegenstellen findet.
//
// Aus dem Betrieb, 04.09.2026: "meine idee war ja nicht ausgrenzen und unsere
// software user machen ihr eigenes ding, sondern eher so wie in punkt 2: wir
// zeigen auf lightning network organisationen und wir koennten dann mit der
// software auch eine werden."
//
// Also ausdruecklich KEIN eigenes Verzeichnis. Der Lightning-Graph IST schon
// ein oeffentliches Verzeichnis -- jeder Knoten kennt ihn. Was hier steht,
// sind Wegweiser zu etablierten Stellen, die uns nicht gehoeren.
//
// Die Anwendung ruft keine davon auf. Sie stehen als Verweise da, und wer
// mag, oeffnet sie im eigenen Browser -- ohne Verweiskopf, damit die
// Gegenseite nicht erfaehrt, woher der Klick kam.
const GEGENSTELLEN_WEGE = [
  { name: "Amboss", url: "https://amboss.space", schluessel: "lgw_amboss" },
  { name: "LightningNetwork+", url: "https://lightningnetwork.plus",
    schluessel: "lgw_lnplus" },
  { name: "1ML", url: "https://1ml.com", schluessel: "lgw_1ml" },
];

function zeichneGegenstellenwege() {
  const ziel = $("#lgw-liste");
  if (!ziel) return;
  // DER BEFUND VOM 22.09.2026: hier stand "if (ziel.firstChild) return --
  // einmal reicht". Einmal reicht aber nicht, denn in dieser Liste steht
  // UEBERSETZTER Text. Der Sprachumschalter loest die Nachlade-Sperren und
  // zeichnet neu -- diese Funktion stieg dabei sofort wieder aus, und
  // #lgw-liste wird nirgendwo sonst angefasst. Wer auf Englisch umschaltete,
  // behielt sie dauerhaft auf Deutsch, bis er neu lud.
  //
  // Dieselbe Falle steht seit einem frueheren Befund in kennzahl()
  // beschrieben. Die Lehre war gezogen und an dieser Stelle nicht angewandt.
  ziel.textContent = "";
  for (const w of GEGENSTELLEN_WEGE) {
    const zeile2 = document.createElement("p");
    zeile2.style.cssText = "margin:0 0 10px;line-height:1.5";
    const a = document.createElement("a");
    a.href = w.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = w.name;
    a.style.cssText = "color:var(--btc-2);font-weight:600";
    const text = document.createElement("span");
    text.className = "dim small";
    text.textContent = " — " + t(w.schluessel);
    zeile2.append(a, text);
    ziel.append(zeile2);
  }
}

/* Eine Zeile, deren Wert man WEITERGEBEN koennen muss.

   Aus dem Betrieb, 10.09.2026: "unter Kennung: solte die volle kennung stehen
   damit sie mal kopieren kann und genau das selbe gilt fuer angekuendigt".

   Er hat recht, und kurz() war hier von Anfang an falsch am Platz: es macht
   66 Zeichen lesbar, und genau das ist der Punkt -- eine gekuerzte Kennung
   ist nur noch zum ANSEHEN gut. Wer sie braucht, braucht sie ganz.

   Also vollstaendig, umbrechend, und mit einem Knopf daneben. Die Kuerzung
   bleibt, wo sie hingehoert: in Listen, in denen man zwei Knoten
   auseinanderhalten will. */
function langzeile(schluessel, wert, meldungsschluessel, kopierwert) {
  // "kopierwert" trennt, was DASTEHT, von dem, was der Knopf herausgibt.
  //
  // Gebraucht bei den angekuendigten Adressen: dort gehoert die vollstaendige
  // URI in die Zwischenablage (die gibt man weiter), auf den Bildschirm aber
  // nur die Adresse. Vorher stand die 66-stellige Kennung in jeder Zeile
  // noch einmal -- obwohl sie eine Zeile darueber schon als "Kennung"
  // steht --, und aus zwei Adressen wurde ein unlesbarer Block.
  const d = document.createElement("div");
  d.className = "stat langstat";
  const k = document.createElement("span");
  k.className = "k";
  k.textContent = schluessel;
  const rechts = document.createElement("div");
  rechts.className = "langwert";
  const v = document.createElement("span");
  v.className = "v";
  v.textContent = wert;
  const knopf = document.createElement("button");
  knopf.type = "button";
  knopf.className = "btn ghost klein";
  knopf.textContent = t("lgi_kopieren");
  const meldung = document.createElement("span");
  meldung.className = "dim small";
  // Aus dem Blickfeld, aber IM Dokument: die zweite Stufe von kopiere()
  // markiert den Knoteninhalt und kann nichts markieren, was nicht
  // dargestellt wird. "display:none" waere hier der stille Fehler.
  let quelle = v;
  if (kopierwert) {
    quelle = document.createElement("span");
    quelle.textContent = kopierwert;
    quelle.style.position = "absolute";
    quelle.style.left = "-9999px";
    rechts.append(quelle);
  }
  knopf.addEventListener("click", () => kopiere(quelle, meldung,
                                                meldungsschluessel || "lgi_kopiert"));
  rechts.append(v, knopf, meldung);
  d.append(k, rechts);
  return d;
}

function zeichneLnIch(k) {
  const ziel = $("#ln-ich-inhalt");
  ziel.textContent = "";
  ziel.append(zeile(t("lk_alias"), k.alias || "—"));
  ziel.append(langzeile(t("lk_kennung"), k.kennung || "—"));
  const adressen = (k.adressen && k.adressen.length) ? k.adressen : [];
  // Gezeigt wird nur der Teil hinter dem "@" -- die Kennung davor ist in
  // jeder URI dieselbe und steht eine Zeile hoeher unter "Kennung".
  // Kopiert wird trotzdem die vollstaendige URI: die gibt man weiter, wenn
  // jemand einen Kanal zu diesem Knoten oeffnen soll.
  const nurAdresse = (uri) => uri.slice(uri.indexOf("@") + 1);
  ziel.append(adressen.length
    ? langzeile(t("lk_adressen"), adressen.map(nurAdresse).join("\n"),
                null, adressen.join("\n"))
    : zeile(t("lk_adressen"), t("lk_keine_adressen")));
  ziel.append(zeile(t("lk_gegenstellen"),
    t("lk_gegenstellen_n", { n: zahl(k.gegenstellen) })));
  ziel.append(zeile(t("lk_kanaele_stand"), t("lk_kanaele_stand_n", {
    aktiv: k.kanaele_aktiv, still: k.kanaele_still,
    offen: k.kanaele_offen_werdend })));
}

function sats(n) { return zahl(n) + " sat"; }

function dauerGrob(sekunden) {
  // Grob genuegt: ob es zehn Minuten oder zwoelf sind, aendert nichts an dem,
  // was zu tun ist. Ob es Minuten oder Tage sind, sehr wohl.
  const m = Math.round(sekunden / 60);
  if (m < 60) return t("dauer_min", { n: m });
  const h = Math.round(m / 60);
  if (h < 48) return t("dauer_std", { n: h });
  return t("dauer_tage", { n: Math.round(h / 24) });
}

function nachkomma(n, stellen) {
  return (n || 0).toLocaleString(LANG === "de" ? "de-DE" : "en-US",
    { minimumFractionDigits: stellen, maximumFractionDigits: stellen });
}

function zeichneKanalkosten(k) {
  const kasten = $("#w-kanalkosten");
  if (!kasten) return;
  // Ohne Schaetzung steht hier NICHTS. Eine Null hiesse "umsonst", und das
  // waere an dieser Stelle die teuerste Falschauskunft von allen.
  kasten.classList.toggle("hidden", !k);
  if (!k) return;

  const zahlen = $("#kk-zahlen");
  zahlen.textContent = "";
  const zeilen = [
    [t("kk_satz"), nachkomma(k.satz_sat_vb, 1) + " sat/vB"],
    [t("kk_oeffnen"), sats(k.oeffnen_sat)],
    [t("kk_schliessen"), sats(k.schliessen_sat)],
    [t("kk_zusammen"), sats(k.zusammen_sat)],
  ];
  for (const [name, wert] of zeilen) zahlen.append(zeile(name, wert));

  // IST DAS GERADE TEUER ODER GUENSTIG?
  //
  // Aus dem Betrieb, 11.09.2026: "das mann ne orientierung hat". Eine nackte Zahl
  // wie "2,2 sat/vB" sagt einem Menschen nichts -- erst der Vergleich mit
  // der eigenen letzten Woche macht daraus eine Auskunft.
  //
  // Diese Zeile steht bewusst VOR dem Anteil am Guthaben und haengt nicht an
  // ihm: wer plant, hat noch kein Guthaben. Genau dann fehlte bisher jede
  // Orientierung -- die Einordnung verschwand ausgerechnet beim Planen.
  const lage = $("#kk-lage");
  lage.textContent = "";
  const einordnung = lagehinweis(k);
  if (einordnung) lage.append(einordnung);

  // Der Anteil ist die eigentliche Aussage: 1.540 Sats sagen einem Menschen
  // nichts, "ein Prozent deines Guthabens" sagt alles -- und "zweiundvierzig
  // Prozent" sagt es erst recht.
  const urteil = $("#kk-urteil");
  urteil.textContent = "";
  if (k.anteil_prozent === undefined || k.anteil_prozent === null) return;
  const p = k.anteil_prozent;
  const art = p >= 10 ? "bad" : p >= 3 ? "warn" : "ok";
  const schluessel = p >= 10 ? "kk_teuer" : p >= 3 ? "kk_spuerbar" : "kk_guenstig";
  urteil.append(hinweis(t(schluessel, { p: nachkomma(p, 2) }), art));
}

/* Guenstig, normal oder teuer -- als fertiger Hinweis.

   Eine Funktion fuer beide Stellen: unter "Wallet" steht sie neben den
   Gebuehren, im Rechner neben der Kanalgroesse. Zweimal derselbe Satz aus
   zwei Quellen waere der Anfang zweier verschiedener Wahrheiten. */
function lagehinweis(k) {
  if (!k || !k.lage || !k.verlauf) return null;
  const art = k.lage === "teuer" ? "bad" : k.lage === "normal" ? "warn" : "ok";
  const schluessel = "kk_lage_" + k.lage;
  const werte = {
    satz: nachkomma(k.satz_sat_vb, 1),
    tage: nachkomma(k.verlauf.tage, 0),
    unten: nachkomma(k.verlauf.unten, 1),
    oben: nachkomma(k.verlauf.oben, 1),
    mitte: nachkomma(k.verlauf.mitte, 1),
  };
  return hinweis(t(schluessel, werte), art);
}

/* ── Was ein Kanal kostet, im Rechner ──────────────────────────────────────

   Aus dem Betrieb, 11.09.2026: "wir haben ja schon ein rechner reiter kann das da
   nicht mit rein?" -- und das ist die bessere Stelle, aus einem Grund, der
   im Wallet-Kasten fehlte: hier liegt der KURS. "160.339 sat" sagt einem
   Menschen nichts, "rund 112 Euro" sagt alles. Geplant wird in Euro. */

// Der letzte Stand, damit das Tippen im Feld nicht jedesmal den Knoten fragt.
let KK_STAND = null;

async function ladeKanalrechner() {
  if (!$("#kk-plan")) return;
  let d;
  try {
    d = await api("/kanalrechner");
  } catch (e) {
    return;                       // der alte Stand bleibt stehen
  }
  zeichneKanalplan((d || {}).kanalkosten || null);
}

function zeichneKanalplan(k) {
  KK_STAND = k;
  const feld = $("#kkp-groesse");
  if (!feld) return;

  // Ohne Gebuehrenschaetzung gibt es keine Rechnung -- waehrend des
  // Abgleichs der Normalfall. Dann steht da, WARUM nichts dasteht, statt
  // einer Tabelle voller Nullen.
  const ohne = $("#kkp-ohne");
  if (ohne) ohne.classList.toggle("hidden", !!k);
  $("#kkp-lage").textContent = "";
  if (!k) {
    $("#kkp-zahlen").textContent = "";
    return;
  }
  const einordnung = lagehinweis(k);
  if (einordnung) $("#kkp-lage").append(einordnung);

  // NUR EINMAL anhaengen, und als Pfeilfunktion.
  //
  // Der Fehler vom 11.09.2026 steht noch frisch im Protokoll: eine benannte
  // Funktion mit Vorgabewerten direkt an addEventListener bekommt das
  // Ereignis als ERSTES Argument -- und dann steht es in dem Parameter, der
  // eigentlich eine Zahl sein sollte. Hier passiert das nicht.
  if (!feld.dataset.verdrahtet) {
    feld.dataset.verdrahtet = "1";
    feld.addEventListener("input", () => kanalplanRechnen());
  }
  kanalplanRechnen();
}

/* Satoshi und, wenn ein Kurs vorliegt, der Betrag daneben. */
function satsUndFiat(n) {
  const kurs = rechnerKurs();
  if (!Number.isFinite(kurs) || kurs <= 0) return sats(n);
  const zeichen = KURS_ZEICHEN[KURS_WAEHRUNG] || KURS_WAEHRUNG.toUpperCase();
  return sats(n) + "  ·  " + zeichen + " "
    + zahlSchreiben(n / SAT_JE_BTC * kurs, 2, LANG);
}

function kanalplanRechnen() {
  const ziel = $("#kkp-zahlen");
  const feld = $("#kkp-groesse");
  if (!ziel || !feld || !KK_STAND) return;
  ziel.textContent = "";

  const groesse = Math.max(0, Math.round(Number(feld.value) || 0));
  if (!groesse) return;

  const oeffnen = KK_STAND.oeffnen_sat || 0;
  // Die Ruecklage kennt nur ein laufender LND. Ohne ihn faellt die Zeile weg,
  // statt eine Null zu zeigen -- eine Null hiesse "du brauchst nichts
  // zurueckzulegen", und daran scheitert man spaeter beim Schliessen.
  const ruecklage = KK_STAND.ruecklage_sat;
  const reserve = Math.round(groesse * (KK_STAND.reserve_prozent || 0) / 100);

  const zeilen = [[t("kkp_kanal"), satsUndFiat(groesse)],
                  [t("kkp_oeffnen"), satsUndFiat(oeffnen)]];
  if (ruecklage !== undefined && ruecklage !== null) {
    zeilen.push([t("kkp_ruecklage"), satsUndFiat(ruecklage)]);
  }
  const einzahlen = groesse + oeffnen + (ruecklage || 0);
  zeilen.push([t("kkp_einzahlen"), satsUndFiat(einzahlen)]);
  zeilen.push([t("kkp_nutzbar"), satsUndFiat(Math.max(0, groesse - reserve))]);
  for (const [name, wert] of zeilen) ziel.append(zeile(name, wert));
}

function zeichneLnGuthaben(g) {
  const ziel = $("#ln-guthaben-inhalt");
  ziel.textContent = "";
  // Die Reserve gehoert dazwischen, nicht ans Ende: sie ist die Korrektur
  // der Zahl darueber. Nachgelesen bei lightningnode.info -- local_balance
  // enthaelt sie, ausgeben laesst sie sich nicht. Die Oberflaeche zeigte
  // also Geld als verfuegbar, das es nicht ist.
  // Ausgebbar ist nur, was eine Bestaetigung hat: Senden und Kanal oeffnen
  // verlangen min_confs=1. Bis zum 15.09.2026 stand hier die Summe MIT dem
  // Unbestaetigten -- eine frische Einzahlung sah ausgebbar aus, und das
  // Senden scheiterte. Das Unbestaetigte steht jetzt daneben.
  LETZTES_GUTHABEN = g;
  const unterwegs = Math.max(0, (g.kette_gesamt || 0) - (g.kette_bestaetigt || 0));
  const werte = [
    [t("lk_onchain"), g.kette_bestaetigt],
    [t("lk_kanal_hier"), g.kanal_hier],
  ];
  if (unterwegs) werte.splice(1, 0, [t("lk_unterwegs"), unterwegs]);
  // Der Satz dazu steht UNTER den Kennzahlen: im Raster wurde er zur
  // schmalen Spalte. Leer blendet .note:empty ihn aus.
  const erklaerung = $("#ln-guthaben-hinweis");
  if (erklaerung) erklaerung.textContent = unterwegs ? t("lk_unterwegs_d") : "";
  if (g.kanal_reserve) werte.push([t("lk_kanal_frei"), g.kanal_frei]);
  werte.push([t("lk_kanal_drueben"), g.kanal_drueben]);
  for (const [name, betrag] of werte) {
    const kasten = document.createElement("div");
    kasten.className = "kennzahl-gross";
    const wert = document.createElement("div");
    wert.className = "wert";
    wert.textContent = sats(betrag);
    const bez = document.createElement("div");
    bez.className = "bez";
    bez.textContent = name;
    kasten.append(wert, bez);
    ziel.append(kasten);
  }
  if (g.kanal_reserve) {
    ziel.append(hinweis(t("lk_reserve", { n: zahl(g.kanal_reserve) }), ""));
  }
}

// Anteil der Zeit, in der die Gegenstelle diesen Knoten erreichen konnte.
// null, solange es nichts zu rechnen gibt -- ein frisch geoeffneter Kanal
// hat noch keine Laufzeit, und "0 %" waere dann eine Behauptung.
function erreichbarkeit(k) {
  const dauer = k.laufzeit_s || 0;
  if (dauer < 600) return null;             // unter zehn Minuten sagt nichts
  return Math.min(1, (k.erreichbar_s || 0) / dauer);
}

// Ueber alle Kanaele, gewichtet nach ihrer Laufzeit: ein Kanal von gestern
// darf einen von vor einem Jahr nicht ueberstimmen.
function gesamterreichbarkeit(liste) {
  let dauer = 0, oben = 0;
  for (const k of liste) {
    if (erreichbarkeit(k) === null) continue;
    dauer += k.laufzeit_s;
    oben += Math.min(k.erreichbar_s || 0, k.laufzeit_s);
  }
  return dauer ? oben / dauer : null;
}

/* Die beiden Auswahlfelder fuers Umschichten.

   Sie kommen aus der Kanalliste selbst -- niemand soll eine Kanalnummer
   abtippen muessen. Und der Kasten erscheint erst ab ZWEI Kanaelen: mit
   einem gibt es nichts umzuschichten, und ein Kasten, der nie geht, ist
   schlechter als keiner. */
function fuelleUmschichten(liste) {
  const kasten = $("#ln-schichten");
  if (!kasten) return;
  const brauchbar = liste.filter((k) => k.aktiv);
  kasten.classList.toggle("hidden", brauchbar.length < 2);
  if (brauchbar.length < 2) return;

  const von = $("#us-von");
  const nach = $("#us-nach");
  const vorherVon = von.value;
  const vorherNach = nach.value;
  von.textContent = "";
  nach.textContent = "";
  for (const k of brauchbar) {
    const name = (k.gegenstelle || k.kennung.slice(0, 12));
    // "von" nennt die Kanalnummer, "nach" die Gegenstelle -- LND will beim
    // Rundweg genau diese beiden Angaben, und zwar in dieser Form.
    const a = document.createElement("option");
    a.value = k.nummer;
    a.textContent = name + " · " + sats(k.verfuegbar);
    von.append(a);

    const b = document.createElement("option");
    b.value = k.kennung;
    b.textContent = name + " · " + sats(k.drueben);
    nach.append(b);
  }
  if (vorherVon) von.value = vorherVon;
  if (vorherNach) nach.value = vorherNach;
}

async function umschichten() {
  const knopf = $("#us-los");
  const meldung = $("#us-meldung");
  const von = $("#us-von").value;
  const nach = $("#us-nach").value;
  if (!von || !nach) return;
  // Aus einem Kanal in denselben Kanal gibt es nichts zu schieben -- und LND
  // wuerde erst nach einem Rundweg suchen, den es nicht gibt.
  const gleich = (KANAELE_LETZTE || []).some(
    (k) => k.nummer === von && k.kennung === nach);
  if (gleich) {
    meldung.textContent = t("us_gleicher_kanal");
    return;
  }
  knopf.disabled = true;
  meldung.textContent = t("us_laeuft");
  $("#us-fertig").classList.add("hidden");
  let wiederFrei = true;
  try {
    const d = await api("/lightning/umschichten", "POST", {
      von, nach, betrag: Number($("#us-betrag").value || 0),
      ...mitPin("#us-pin"),
    }, FRIST_GELD_MS);
    const fertig = $("#us-fertig");
    fertig.textContent = t("us_fertig", { betrag: zahl(d.betrag),
                                          gebuehr: zahl(d.gebuehr) });
    fertig.classList.remove("hidden");
    $("#us-pin").value = "";
    meldung.textContent = "";
    ladeLightningKanaele();
  } catch (e) {
    // Umschichten ist ein Rundweg mit dem eigenen Geld -- verlieren kann man
    // nur die Gebuehr. Ohne Bescheid trotzdem nicht wiederholen: sonst
    // laeuft derselbe Rundweg ein zweites Mal und kostet ein zweites Mal.
    wiederFrei = geldfehler(e, meldung, "zahlung_unklar");
  } finally {
    if (wiederFrei) knopf.disabled = false;
  }
}

// Der letzte Stand der Kanaele -- fuers Pruefen, ob jemand aus einem Kanal
// in denselben schieben will.
let KANAELE_LETZTE = [];

/* Die Auswahl fuers Schliessen. Ein Kanal, kein Tippen -- und der Name der
   Gegenstelle davor, damit niemand den falschen erwischt. */
function fuelleSchliessen(liste) {
  const kasten = $("#ln-schliessen");
  if (!kasten) return;
  kasten.classList.toggle("hidden", !liste.length);
  if (!liste.length) return;
  const feld = $("#ks-kanal");
  const vorher = feld.value;
  feld.textContent = "";
  for (const k of liste) {
    const o = document.createElement("option");
    o.value = k.punkt;
    o.textContent = (k.gegenstelle || k.kennung.slice(0, 12))
      + " · " + sats(k.kapazitaet) + (k.aktiv ? "" : " · " + t("ks_still"));
    feld.append(o);
  }
  if (vorher) feld.value = vorher;
}

async function kanalSchliessen() {
  const knopf = $("#ks-los");
  const meldung = $("#ks-meldung");
  const punkt = $("#ks-kanal").value;
  if (!punkt) return;
  knopf.disabled = true;
  meldung.textContent = t("ks_laeuft");
  $("#ks-fertig").classList.add("hidden");
  let wiederFrei = true;
  try {
    const d = await api("/lightning/kanal/schliessen", "POST", {
      punkt, erzwingen: $("#ks-erzwingen").checked, tempo: "normal",
      ...mitPin("#ks-pin"),
    }, FRIST_GELD_MS);
    const fertig = $("#ks-fertig");
    fertig.textContent = t(d.erzwungen ? "ks_fertig_erzwungen" : "ks_fertig",
                           { txid: d.txid });
    fertig.classList.remove("hidden");
    $("#ks-pin").value = "";
    $("#ks-erzwingen").checked = false;
    $("#ks-warnung").classList.add("hidden");
    meldung.textContent = "";
    ladeLightningKanaele();
  } catch (e) {
    wiederFrei = geldfehler(e, meldung, "kanal_unklar");
  } finally {
    if (wiederFrei) knopf.disabled = false;
  }
}

function zeichneLnKanaele(liste) {
  KANAELE_LETZTE = liste;
  fuelleUmschichten(liste);
  fuelleSchliessen(liste);
  const ziel = $("#ln-kanaele-inhalt");
  ziel.textContent = "";
  if (!liste.length) {
    ziel.append(hinweis(t("lk_keine_kanaele"), ""));
    return;
  }
  const gesamt = gesamterreichbarkeit(liste);
  if (gesamt !== null) {
    ziel.append(hinweis(
      t("lk_erreichbar_gesamt", { p: nachkomma(gesamt * 100, 2) }),
      gesamt >= 0.99 ? "ok" : gesamt >= 0.95 ? "" : "warn"));
  }
  for (const k of liste) {
    const reihe = document.createElement("div");
    reihe.className = "kanal";

    const kopf = document.createElement("div");
    kopf.className = "kanal-kopf";
    const punkt = document.createElement("span");
    punkt.className = "kanal-punkt" + (k.aktiv ? "" : " still");
    const name = document.createElement("span");
    name.className = "kanal-name";
    name.textContent = k.gegenstelle || kurz(k.kennung || "");
    kopf.append(punkt, name);
    if (k.privat) kopf.append(marke(t("lk_privat")));
    if (!k.aktiv) kopf.append(marke(t("lk_still")));
    const rechts = document.createElement("span");
    rechts.className = "rechts";
    rechts.textContent = sats(k.kapazitaet);
    kopf.append(rechts);

    const balken = document.createElement("div");
    balken.className = "kanal-balken";
    const hier = document.createElement("span");
    hier.style.width = Math.round(k.anteil_hier * 100) + "%";
    balken.append(hier);

    const fuss = document.createElement("div");
    fuss.className = "kanal-fuss";
    const a = document.createElement("span");
    a.textContent = t("lk_kanal_hier_kurz", { n: zahl(k.hier) });
    const b = document.createElement("span");
    b.className = "drueben";
    b.textContent = t("lk_kanal_drueben_kurz", { n: zahl(k.drueben) });
    fuss.append(a, b);

    // Die Zahl, an der eine Zusage gemessen wird. LND fuehrt sie je Kanal
    // mit: "lifetime" ist, wie lange es ihn gibt, "uptime", wie lange die
    // Gegenstelle uns dabei erreichen konnte. Wir haben beides von Anfang an
    // gelesen und nie gezeigt.
    //
    // Aus dem Betrieb, 05.09.2026 zu den Swap-Bindungen: "dann muss unser System so
    // sauber und stabil laufen, dass wir wirklich 60 Monate am Stueck online
    // bleiben". Was man zusagt, muss man auch nachhalten koennen.
    const anteil = erreichbarkeit(k);
    if (anteil !== null) {
      const e = document.createElement("span");
      e.className = "kanal-erreichbar " + (anteil >= 0.99 ? "gut"
                                        : anteil >= 0.95 ? "mittel" : "schwach");
      e.textContent = t("lk_erreichbar", { p: nachkomma(anteil * 100, 1) });
      e.title = t("lk_erreichbar_titel", {
        seit: dauerGrob(k.laufzeit_s || 0) });
      fuss.append(e);
    }

    reihe.append(kopf, balken, fuss);
    ziel.append(reihe);
  }
}

function marke(text) {
  const m = document.createElement("span");
  m.className = "kanal-marke";
  m.textContent = text;
  return m;
}

function zeichneLnWeiterleitungen(w) {
  const ziel = $("#ln-weiter-inhalt");
  ziel.textContent = "";
  if (!w.anzahl) {
    ziel.append(hinweis(t("lk_weiter_keine"), ""));
    return;
  }
  ziel.append(hinweis(t("lk_weiter_summe", {
    n: zahl(w.anzahl), menge: zahl(w.menge),
    // Gebuehren kommen in Millisatoshi -- in Sats gerundet liest sie ein
    // Mensch, in msat sieht jede kleine Weiterleitung nach viel aus.
    gebuehr: zahl(Math.round(w.gebuehr_msat / 1000)) }), "ok"));
  for (const e of w.letzte || []) {
    // Die Gebuehr in Sats mit Nachkommastellen -- und zwar mit dem
    // Trennzeichen der Sprache. "6.300" haetten deutsche Leser als
    // sechstausenddreihundert gelesen, gemeint sind sechs Komma drei.
    ziel.append(zeile(`${e.von || "?"} → ${e.nach || "?"}`,
                      sats(e.menge) + "  (+" + nachkomma(e.gebuehr_msat / 1000, 3)
                      + " sat)"));
  }
}

async function unterschriftLeisten() {
  const knopf = $("#unt-knopf");
  const meldung = $("#unt-meldung");
  const text = $("#unt-text").value;
  meldung.textContent = "";
  if (!text.trim()) { meldung.textContent = t("unt_leer"); return; }
  knopf.disabled = true;
  try {
    const d = await api("/lightning/unterschrift", "POST", { text });
    $("#unt-feld").textContent = d.unterschrift;
    // Der Knoten hat seine eigene Unterschrift nachgerechnet und dabei den
    // Schluessel genannt, mit dem sie erzeugt wurde. Steht dort der eigene,
    // ist es nicht nur die richtige FORM, sondern richtig. null heisst:
    // unterschrieben, aber gerade nicht nachpruefbar -- das ist etwas
    // anderes als "falsch" und wird auch anders gesagt.
    $("#unt-geprueft").textContent =
      d.geprueft === true ? t("unt_geprueft")
      : d.geprueft === false ? t("unt_nicht_gueltig")
      : t("unt_ungeprueft");
    $("#unt-ergebnis").classList.remove("hidden");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const grund = (e.detail || {}).meldung;
    meldung.textContent = grund === "lnd_nicht_bereit"
      ? t("unt_nicht_bereit") : t("err_net");
  } finally {
    knopf.disabled = false;
  }
}

function zeichneEigeneAdresse(k) {
  const kasten = $("#lg-ich");
  const feld = $("#lgi-uri");
  if (!kasten || !feld) return;
  const uris = (k && k.adressen) || [];
  // Nicht gekuerzt: sie ist zum Weitergeben da, und ein "abc…xyz" kann
  // niemand verwenden. Genau daran scheiterte es bisher.
  feld.textContent = uris.length ? uris.join("\n") : "";
  $("#lgi-kopieren").disabled = !uris.length;
  // Eine .onion ist eine Adresse. Eine IP ist dein Anschluss. Der Kasten
  // nannte beides gleichrangig "ohnehin oeffentlich" -- formal richtig und
  // genau an der Stelle verharmlosend, an der es zaehlt. Gewarnt wird nur,
  // wenn wirklich eine Clearnet-Adresse dabei ist.
  const klartext = uris.some((u) => !u.split("@").pop().includes(".onion"));
  const warnkasten = $("#lgi-klartext");
  if (warnkasten) {
    warnkasten.textContent = klartext ? t("lgi_klartext") : "";
    warnkasten.classList.toggle("hidden", !klartext);
  }
  // Warum dort nichts steht, haengt an der Betriebsart -- und die kennt die
  // Anwendung. Drei Lagen, drei verschiedene naechste Schritte:
  //
  //   still   nie eine Adresse, und das ist die Wahl. Kein Fehler.
  //   tor     die Onion entsteht beim Start von LND, das dauert kurz.
  //   hybrid  dann fehlt schlicht die eigene Adresse in den Einstellungen.
  //
  // Bis zum 10.09.2026 stand fuer alle drei derselbe dimme Halbsatz neben
  // dem Kopierknopf. Der Betreiber musste fragen, ob das ewig dauert -- bei
  // "still" haette er ewig gewartet.
  const warum = $("#lgi-warum");
  if (warum) {
    // Beschaeftigt schlaegt alles andere: solange getinfo nicht antwortet,
    // wissen wir ueber die Adressen gar nichts -- und "trag deine Adresse
    // ein" waere dann ein falscher Rat.
    const grund = k && k.beschaeftigt ? "lgi_keine_beschaeftigt"
      : "lgi_keine_" + (k && k.sichtbarkeit ? k.sichtbarkeit : "unklar");
    warum.textContent = uris.length ? "" : t(grund);
    warum.classList.toggle("hidden", !!uris.length);
    warum.classList.toggle("warn", !uris.length && k
                           && !k.beschaeftigt && k.sichtbarkeit !== "still");
  }
  // Und wenn die Zahlen von vorhin sind, gehoert das dazugesagt.
  const veraltet = $("#lgi-veraltet");
  if (veraltet) {
    veraltet.textContent = k && k.veraltet ? t("lgi_veraltet") : "";
    veraltet.classList.toggle("hidden", !(k && k.veraltet));
  }
  $("#lgi-meldung").textContent = "";
}

/* Ist das noch derselbe Knoten?

   Aus dem Betrieb, 11.09.2026, nach seiner Wiederherstellung: "keine ahnung habe
   mir die kennung nicht vorher angesehen". Dass er sie sich von Hand haette
   notieren sollen, war unser Versaeumnis -- die Anwendung kennt sie ohnehin
   und kann die Frage selbst beantworten.

   Die Kennung ist kein Geheimnis: sie ist der oeffentliche Schluessel dieses
   Knotens, im ganzen Netz bekannt. */
function zeichneKennungswechsel(vorher, jetzt) {
  const kasten = $("#lgi-kennung-anders");
  if (!kasten) return;
  const anders = !!(vorher && jetzt && vorher !== jetzt);
  kasten.classList.toggle("hidden", !anders);
  if (!anders) return;
  $("#lgi-kennung-text").textContent = t("lgi_kennung_anders",
                                         { vorher, jetzt });
}

async function kennungUebernehmen() {
  const knopf = $("#lgi-kennung-ok");
  const meldung = $("#lgi-kennung-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/kennung/uebernehmen", "POST");
    $("#lgi-kennung-anders").classList.add("hidden");
    ladeLightningKanaele();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

function zeichneLnNetz(netz, kanaele, knoten) {
  const ziel = $("#lg-netz");
  ziel.textContent = "";
  // Ein frischer Knoten kennt den Graphen noch nicht. Der Betreiber sah kurz nach
  // dem Anlegen 4.393 Knoten und 231 BTC und musste das fuer die Groesse des
  // Lightning-Netzes halten -- es war knapp ein Viertel davon. getinfo sagt
  // uns laengst, ob der Abgleich durch ist (synced_to_graph); wir lasen es
  // ein und zeigten es nicht. Zahlen ohne diesen Satz sind eine Auskunft,
  // die falsch verstanden werden MUSS.
  if (knoten && knoten.graph_aktuell === false) {
    ziel.append(hinweis(t("lg_graph_laedt"), ""));
  }
  if (netz) {
    ziel.append(zeile(t("lg_knoten"), zahl(netz.knoten)));
    ziel.append(zeile(t("lg_kanaele"), zahl(netz.kanaele)));
    // Das Netz zaehlt in Tausenden von BTC. In Sats waeren das zwoelf
    // Stellen -- eine Zahl, die niemand liest, sondern nur ueberfliegt.
    ziel.append(zeile(t("lg_kapazitaet"),
                      nachkomma(netz.kapazitaet / 1e8, 0) + " BTC"));
    ziel.append(zeile(t("lg_median"), sats(netz.median_kanal)));
    ziel.append(zeile(t("lg_grad"), nachkomma(netz.grad_mittel, 1)));
  }
  const gegen = $("#lg-gegenstellen");
  gegen.textContent = "";
  if (!kanaele.length) {
    gegen.append(hinweis(t("lg_gegen_keine"), ""));
    return;
  }
  // Je Gegenstelle EINE Zeile, auch bei mehreren Kanaelen zu ihr -- gefrag
  // ist "mit wem", nicht "wie oft".
  const summen = new Map();
  for (const k of kanaele) {
    const name = k.gegenstelle || kurz(k.kennung || "");
    const bisher = summen.get(name) || { kapazitaet: 0, kanaele: 0 };
    summen.set(name, { kapazitaet: bisher.kapazitaet + k.kapazitaet,
                       kanaele: bisher.kanaele + 1 });
  }
  for (const [name, s] of [...summen].sort((a, b) => b[1].kapazitaet - a[1].kapazitaet)) {
    gegen.append(zeile(name, sats(s.kapazitaet)
      + (s.kanaele > 1 ? `  (${s.kanaele})` : "")));
  }
}

/* Leitungen, nicht Kanaele.

   Bis zum 14.09.2026 hiess beides "Gegenstellen": oben zaehlte "Verbunden
   mit" die Leitungen, unter "Knoten" stand eine Liste der Kanalpartner mit
   der Beschreibung "mit wem du direkt verbunden bist". Wer sich verband,
   fand die Verbindung danach nirgends wieder. */
function zeichneVerbindungen(verbindungen) {
  const ziel = $("#lv-liste");
  if (!ziel) return;
  ziel.textContent = "";
  if (!verbindungen) return;
  if (!verbindungen.length) {
    ziel.append(hinweis(t("lv_keine"), ""));
    return;
  }
  const mitKanal = verbindungen.filter((v) => v.mit_kanal).length;
  ziel.append(hinweis(t("lv_summe",
    { n: zahl(verbindungen.length), k: zahl(mitKanal) }), ""));
  for (const v of verbindungen) {
    const teile = [t(v.mit_kanal ? "lv_mit_kanal" : "lv_ohne_kanal"),
                   t(v.eingehend ? "lv_ein" : "lv_aus")];
    if (v.netzkarte) teile.push(t("lv_netzkarte"));
    ziel.append(zeile(v.name || kurz(v.kennung || ""), teile.join(" · ")));
  }
}

/* ── Beitrag ────────────────────────────────────────────────────────────────
   "Gesendete Bytes" allein sagt wenig: da steckt Handschlag, Ping und
   Adressgeplauder mit drin. Die Frage lautet: nimmt jemand BLOECKE von mir?
   getpeerinfo schluesselt das auf. */

const BEITRAG_ARTEN = ["bloecke", "transaktionen", "filter", "kopfzeilen",
                       "adressen", "rest"];
let BEITRAG_STAND = 0;

async function ladeBeitrag(erzwingen) {
  const jetzt = Date.now();
  if (!erzwingen && jetzt - BEITRAG_STAND < 30000) return;
  BEITRAG_STAND = jetzt;
  try {
    zeichneBeitrag(await api("/beitrag"));
  } catch (e) {
    if (e && e.abgemeldet) return;
    BEITRAG_STAND = 0;
  }
}

function zeichneBeitrag(d) {
  const ziel = $("#d-beitrag");
  ziel.textContent = "";
  if (!d || !d.eingerichtet || !d.erreichbar) return;

  const a = d.ausgeliefert || {};
  const summe = BEITRAG_ARTEN.reduce((s, k) => s + (a[k] || 0), 0);
  // Die Aufteilung zaehlt ueber die GERADE verbundenen Gegenstellen. Meldet
  // der Knoten keine, ist jede Zahl darunter eine Null ohne Grundlage --
  // und sechs Nullen sehen aus wie eine tote Tafel. Am 03.09.2026 genau so
  // aufgeschlagen: oben "150 kB ausgeliefert", darunter sechsmal null.
  const ohneGegenstellen = !(d.gegenstellen || []).length;

  const kasten = document.createElement("div");
  kasten.className = "beitrag";

  const ueber = document.createElement("p");
  ueber.className = "dim small";
  ueber.style.margin = "0 0 10px";
  ueber.textContent = t("b_lead");
  kasten.append(ueber);

  // Die Summe der Aufteilung, ausdruecklich benannt. Ohne sie stand hier
  // eine Aufschluesselung ohne sichtbare Grundlage, direkt unter einer
  // GROESSEREN Zahl mit anderem Bezugsraum ("Ausgeliefert seit dem Start").
  // Aus dem Betrieb, 17.09.2026: "in dem bild passen die daten auch nicht
  // zusammen". Sie passten auch nicht -- sie zaehlten Verschiedenes.
  if (!ohneGegenstellen) {
    const basis = document.createElement("p");
    basis.className = "dim small";
    basis.style.margin = "0 0 10px";
    basis.textContent = t("b_summe", {
      menge: menschenBytes(summe), n: (d.gegenstellen || []).length });
    kasten.append(basis);
  }

  if (summe > 0) {
    const balken = document.createElement("div");
    balken.className = "beitrag-balken";
    BEITRAG_ARTEN.forEach((k) => {
      if (!a[k]) return;
      const s2 = document.createElement("span");
      s2.className = k;
      s2.style.width = (a[k] / summe * 100) + "%";
      s2.title = t("b_" + k) + ": " + menschenBytes(a[k]);
      balken.append(s2);
    });
    kasten.append(balken);
  }

  const liste = document.createElement("div");
  liste.className = "beitrag-liste";
  BEITRAG_ARTEN.forEach((k) => {
    const zeile = document.createElement("div");
    // Bloecke sind der eigentliche Beitrag -- die Zeile traegt die Aussage.
    zeile.className = "zeile" + (k === "bloecke" ? " stark" : "");
    const punkt = document.createElement("span");
    punkt.className = "punkt " + k;
    const name = document.createElement("span");
    name.className = "k"; name.textContent = t("b_" + k);
    const wert = document.createElement("span");
    wert.className = "v";
    wert.textContent = ohneGegenstellen ? "—" : menschenBytes(a[k] || 0);
    zeile.append(punkt, name, wert);
    liste.append(zeile);
  });
  kasten.append(liste);

  // Die eine Zeile, die wirklich zaehlt: liefert der Knoten Neueinsteigern
  // noch die alten Bloecke aus? Sagt das Upload-Budget nein, ist er fuer
  // genau den Beitrag geschlossen, um den es geht.
  const b = d.budget || {};
  const restzeit = dauerKurz((b.rest_sekunden || 0) * 1000);
  if (b.liefert_alte_bloecke === false) {
    kasten.append(hinweis(t("b_budget_erschoepft", { rest: restzeit }), "warn"));
  } else if (b.grenze) {
    // Bitcoin Core rechnet in 24 Stunden (MAX_UPLOAD_TIMEFRAME), nicht im
    // Monat -- der Regler fragt nur eine Monatszahl und teilt sie auf.
    kasten.append(hinweis(t("b_budget_rest", {
      bytes: menschenBytes(b.rest_bytes || 0), rest: restzeit }), ""));
  }

  if (ohneGegenstellen) {
    // Der richtige Satz zur richtigen Lage: nicht "niemand hat Bloecke
    // geholt", sondern "es ist gerade niemand da, den wir zaehlen koennten".
    kasten.append(hinweis(t("b_keine_gegenstellen"), ""));
  } else if (!a.bloecke) {
    kasten.append(hinweis(
      KARTE_ERSTSYNC ? t("b_noch_nichts_sync") : t("b_noch_nichts"), ""));
  }
  ziel.append(kasten);
}

/* ── Auswertung ─────────────────────────────────────────────────────────────
   Was nur der eigene Knoten weiss. Der Zulauf sammelt erst, wenn die Kette
   steht -- waehrend des Abgleichs nimmt bitcoind gar keine Transaktionen in
   den Mempool auf, es gaebe also nichts zu messen. */

let AUSW_STAND = 0;
const AUSW_ABSTAND_MS = 30000;

async function ladeAuswertung(erzwingen) {
  const jetzt = Date.now();
  if (!erzwingen && jetzt - AUSW_STAND < AUSW_ABSTAND_MS) return;
  AUSW_STAND = jetzt;
  try {
    zeichneAuswertung(await api("/auswertung"));
  } catch (e) {
    if (e && e.abgemeldet) return;
    AUSW_STAND = 0;
  }
}

function zeichneAuswertung(d) {
  if (!d) return;
  // Kann die Datenbank nicht geoeffnet werden -- auf einem NAS meist, weil
  // der eingehaengte Ordner einem anderen Benutzer gehoert --, dann steht das
  // hier. Ein leerer Kasten waere schlechter: er sieht aus, als sammle die
  // Auswertung noch, und niemand kaeme auf die Rechte.
  if (d.verfuegbar === false) {
    $("#a-seit").textContent = "";
    $("#a-diagramm").textContent = "";
    $("#a-bloecke").textContent = "";
    $("#a-seit").append(hinweis(t("a_nicht_verfuegbar", { grund: d.grund || "?" }), "warn"));
    return;
  }

  const seit = $("#a-seit");
  seit.textContent = "";
  seit.append(document.createTextNode(d.sammelt_seit_ms
    ? t("a_seit", { datum: datumZeit(d.sammelt_seit_ms),
                    tx: zahl(d.transaktionen), bloecke: zahl(d.bloecke) })
    : t("a_wartet")));

  // Luecken gehoeren angezeigt, nicht verschwiegen: ab einer fehlt uns ein
  // Zeitstempel, und jeder Durchschnitt daneben ist ein Stueck weit geraten.
  if (d.luecken_24h > 0) {
    const w = document.createElement("span");
    w.className = "ausw-warnung";
    w.textContent = " " + t("a_luecken", { n: d.luecken_24h });
    seit.append(w);
  }
  // Reorgs getrennt von den Luecken: eine Reorg ist kein Verlust -- bitcoind
  // hat sie sauber gemeldet. Bis zum 15.09.2026 zaehlte sie als Luecke.
  if (d.reorgs_24h > 0) {
    const w = document.createElement("span");
    w.className = "ausw-warnung";
    w.textContent = " " + t("a_reorgs", { n: d.reorgs_24h });
    seit.append(w);
  }

  zeichneDiagramm(d.diagramm, d.mempool,
                  { zeit_s: d.diagramm_zeit_s, laeuft: d.laeuft });
  zeichneBloecke(d.bloecke_liste || []);
}

/* Das Feerate-Diagramm aus Core 31.
   getmempoolfeeratediagram liefert Punkte mit KUMULATIVEM Gewicht und
   KUMULATIVER Gebuehr -- und die Gebuehr in BTC, nicht in Satoshi. Der
   interessante Wert ist die Steigung zwischen zwei Punkten: was der naechste
   Happen Blockplatz kostet. Genau die Kurve optimieren Miner. */
function diagrammPunkte(roh) {
  if (!Array.isArray(roh) || roh.length < 2) return [];
  const punkte = [];
  for (let i = 1; i < roh.length; i++) {
    const dGewicht = roh[i].weight - roh[i - 1].weight;
    const dGebuehr = roh[i].fee - roh[i - 1].fee;
    if (!(dGewicht > 0)) continue;
    // Gebuehr: BTC -> Satoshi. Gewicht -> vByte (Gewicht durch vier).
    const satVb = (dGebuehr * 1e8) / (dGewicht / 4);
    punkte.push({ vsize: roh[i].weight / 4, satvb: satVb });
  }
  return punkte;
}

// Was zuletzt gezeichnet wurde -- der ResizeObserver braucht es, um bei
// geaenderter Breite dieselben Daten neu aufzutragen.
let DIA_DATEN = null;

// Ein Block fasst rund eine Million vByte. Das ist die Einheit, in der man
// eine Warteschlange vor dem naechsten Block liest.
const BLOCK_VB = 1e6;

// Die Y-Achse ist LOGARITHMISCH, und das ist die eigentliche Aenderung vom
// 08.09.2026. Linear war sie unbrauchbar, und der Betreiber hat es genau so
// benannt: "das feeraten diagramm ist müll".
//
// Er hatte recht, und zwar aus einem Grund, den man an seinem Bild sehen
// kann: sein Mempool war fast leer (26 von 300 MB, Verwerfungsgrenze 0,1
// sat/vB). Ein paar eilige Transaktionen zahlten 48 sat/vB, der ganze Rest
// lag unter 2. Auf einer linearen Achse von 0 bis 48 liegen damit
// neunundneunzig Prozent der Kurve in den untersten vier Prozent der Hoehe --
// eine senkrechte Nadel links, daneben ein Strich. Kein Fehler in den Daten,
// sondern die falsche Achse: Gebuehrenmaerkte spannen Groessenordnungen, und
// die traegt nur eine logarithmische Achse.
const DIA_BODEN = 0.1;          // unter 0,1 sat/vB nimmt kein Knoten mehr an
// Ab wann ein Diagramm als alt gilt. Der Zulauf nimmt jede Minute eins auf --
// fuenf Minuten ohne neues sind kein Zufall mehr.
const DIA_ALT_S = 300;
const DIA_STUFEN = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];

function zeichneDiagramm(roh, verlauf, lage) {
  if (roh !== undefined) DIA_DATEN = { roh, verlauf, lage: lage || {} };
  const daten = DIA_DATEN || { roh: null, verlauf: null, lage: {} };
  const ziel = $("#a-diagramm");
  ziel.textContent = "";

  const grenze = (daten.verlauf && daten.verlauf.length)
    ? daten.verlauf[daten.verlauf.length - 1].mindestgebuehr : null;
  $("#a-dia-grenze").textContent = grenze != null
    ? t("a_grenze", { wert: grenze.toFixed(2) }) : "";

  zeichneKommendeBloecke(daten.roh);

  const punkte = diagrammPunkte(daten.roh);
  if (!punkte.length) {
    $("#a-dia-block").textContent = "";
    // Der wahre Grund. Bis zum 15.09.2026 stand hier immer "der Mempool
    // fuellt sich erst, wenn die Kette steht" -- auch bei laengst stehender
    // Kette, wenn in Wahrheit der Zulauf nicht lief.
    ziel.append(hinweis(t((daten.lage || {}).laeuft === false
      ? "a_dia_kein_zulauf" : "a_dia_leer"), ""));
    return;
  }
  // Das Alter gehoert dazu. Angezeigt wird der juengste Schnappschuss MIT
  // Diagramm -- auch wenn danach lange keins mehr kam. Ohne diesen Satz sah
  // ein altes Diagramm aus wie eins von jetzt.
  const zeitS = (daten.lage || {}).zeit_s;
  if (zeitS && Date.now() / 1000 - zeitS > DIA_ALT_S) {
    ziel.append(hinweis(t("a_dia_alt", { zeit: datumZeit(zeitS * 1000) }), "warn"));
  }

  // Die ECHTE Groesse, nicht eine erfundene. Bis zum 07.09.2026 stand hier
  // ein festes viewBox 700x190 mit preserveAspectRatio="none" -- derselbe
  // Fehler wie im Kursbild, und dort hat der Betreiber ihn "mehr als peinlich"
  // genannt. "none" streckt naemlich nicht nur die Geometrie, sondern auch
  // die SCHRIFT: gemessen auf seinem 1850er Schirm 2,23-fach in der Breite
  // bei unveraenderter Hoehe.
  const kasten = ziel.getBoundingClientRect();
  const B = Math.round(kasten.width) || 900;
  const H = 250;
  const LI = 56, RE = 14, OB = 14, UN = 44;

  const maxX = punkte[punkte.length - 1].vsize;
  const werte = punkte.map((p) => p.satvb).filter((w) => w > 0);
  const hoch = Math.max(...werte, grenze || 0, 1);
  const tief = Math.max(DIA_BODEN, Math.min(...werte, grenze || Infinity));
  const lo = Math.log10(tief), hi = Math.log10(hoch * 1.25);

  const x = (v) => LI + (v / maxX) * (B - LI - RE);
  const y = (v) => {
    const l = Math.log10(Math.max(v, tief));
    return H - UN - ((l - lo) / (hi - lo || 1)) * (H - OB - UN);
  };

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${B} ${H}`);

  svg.insertAdjacentHTML("beforeend",
    '<defs><linearGradient id="dia-verlauf" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0" stop-color="#f7931a" stop-opacity=".55"/>'
    + '<stop offset="1" stop-color="#f7931a" stop-opacity=".04"/>'
    + "</linearGradient></defs>");

  const el = (name, attrs, klasse) => {
    const e = document.createElementNS(ns, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (klasse) e.setAttribute("class", klasse);
    svg.append(e);
    return e;
  };

  // ── Y-Achse: runde Werte je Groessenordnung, nicht gleiche Abstaende.
  for (const wert of DIA_STUFEN) {
    if (wert < tief * 0.999 || wert > hoch * 1.25) continue;
    const py = y(wert);
    el("line", { x1: LI, y1: py, x2: B - RE, y2: py }, "dia-gitter");
    const marke = el("text", { x: LI - 8, y: py + 3.5,
                               "text-anchor": "end" }, "dia-text");
    marke.textContent = wert >= 1 ? String(wert) : wert.toFixed(1);
  }
  const yname = el("text", { x: 0, y: 0,
                             transform: `translate(13,${(OB + H - UN) / 2}) rotate(-90)`,
                             "text-anchor": "middle" }, "dia-text");
  yname.textContent = t("a_dia_y");

  // ── Die Kurve als Treppe: jeder Punkt gilt bis zum naechsten.
  const boden = H - UN;
  let d = `M${x(0)},${y(punkte[0].satvb)}`;
  let vorher = punkte[0].satvb;
  punkte.forEach((p) => {
    d += `L${x(p.vsize)},${y(vorher)}L${x(p.vsize)},${y(p.satvb)}`;
    vorher = p.satvb;
  });
  el("path", { d: d + `L${x(maxX)},${boden}L${x(0)},${boden}Z` }, "dia-flaeche");
  el("path", { d: d }, "dia-linie");

  // ── Die Verwerfungsgrenze: der Wert, den grosse Explorer NICHT zeigen
  // koennen, weil sie ihre Knoten so gross fahren, dass sie nie verwerfen.
  if (grenze) {
    el("line", { x1: LI, y1: y(grenze), x2: B - RE, y2: y(grenze) }, "dia-grenze");
  }

  // ── Die Kante des naechsten Blocks. DIE Linie, um die es hier geht: was
  // links davon liegt, passt in den naechsten Block. Ohne sie ist die Kurve
  // eine Form, mit ihr eine Auskunft.
  const naechste = diaGebuehrBei(punkte, BLOCK_VB);
  if (maxX > BLOCK_VB * 1.02) {
    const px = x(BLOCK_VB);
    el("line", { x1: px, y1: OB, x2: px, y2: boden }, "dia-blockkante");
    const beschriftung = el("text", { x: px + 6, y: OB + 11 }, "dia-text");
    beschriftung.textContent = t("a_dia_naechster");
  }
  $("#a-dia-block").textContent = naechste != null
    ? t("a_dia_reinkommen", { wert: diaGebuehrText(naechste) })
    : t("a_dia_passt_alles");

  // ── X-Achse in Blockbreiten, aus einer Liste runder Stufen.
  el("line", { x1: LI, y1: boden, x2: B - RE, y2: boden }, "dia-gitter");
  const marken = Math.min(8, Math.max(1, Math.floor((B - LI - RE) / 110)));
  const STUFEN = [0.25, 0.5, 1, 2, 3, 5, 10, 20, 50].map((n) => n * BLOCK_VB);
  const stufe = STUFEN.find((n) => maxX / n <= marken) || STUFEN[STUFEN.length - 1];
  for (let v = stufe; v <= maxX + 1; v += stufe) {
    const px = x(v);
    el("line", { x1: px, y1: boden, x2: px, y2: boden + 4 }, "dia-gitter");
    const marke = el("text", { x: px, y: boden + 15,
                               "text-anchor": "middle" }, "dia-text");
    const bloecke = v / BLOCK_VB;
    marke.textContent = bloecke === 1 ? t("a_dia_block") : t("a_dia_bloecke", {
      n: bloecke % 1 ? String(bloecke) : bloecke.toFixed(0),
    });
  }
  const achse = el("text", { x: (LI + B - RE) / 2, y: H - 6,
                             "text-anchor": "middle" }, "dia-text");
  achse.textContent = t("a_dia_x", { mb: (maxX / 1e6).toFixed(1) });
  ziel.append(svg);
}

/* ── Die kommenden Bloecke ───────────────────────────────────────────────
 *
 * Aus dem Feerate-Diagramm, das ohnehin jeden Takt hereinkommt -- kein
 * zusaetzlicher Aufruf. Core liefert dort die kumulierten (Gebuehr, Gewicht)
 * je Cluster-Haeppchen; wer sie alle 1 Mio. vByte durchschneidet, bekommt
 * genau die Bloecke, die als naechstes gefunden werden koennten.
 *
 * Ein Haeppchen, das ueber eine Grenze reicht, wird anteilig geteilt --
 * innerhalb eines Haeppchens ist die Gebuehrenrate konstant, das ist also
 * exakt und nicht geschaetzt.
 *
 * Was hier bewusst FEHLT: die Zahl der Transaktionen je Block. Sie steht im
 * Diagramm nicht drin, und sie zu schaetzen waere geraten. Wer sie genau
 * will, braucht getblocktemplate -- ein eigener, grosser Aufruf.
 */
function kommendeBloecke(roh, hoechstens = 8) {
  if (!Array.isArray(roh) || roh.length < 2) return [];
  const bloecke = [];
  let eimer = null;
  const frisch = () => ({ vsize: 0, sat: 0, hoechste: null, tiefste: null });
  const schliessen = () => {
    if (eimer && eimer.vsize > 0) bloecke.push(eimer);
    eimer = frisch();
  };
  eimer = frisch();
  let uebrig_vsize = 0, uebrig_sat = 0;      // was hinter dem letzten Kasten liegt

  for (let i = 1; i < roh.length; i++) {
    let dv = (roh[i].weight - roh[i - 1].weight) / 4;
    const ds = (roh[i].fee - roh[i - 1].fee) * 1e8;
    if (!(dv > 0)) continue;
    const rate = ds / dv;
    while (dv > 0) {
      if (bloecke.length >= hoechstens) {
        // Alles Weitere nur noch zusammenzaehlen -- als EIN Kasten "+n".
        uebrig_vsize += dv;
        uebrig_sat += rate * dv;
        dv = 0;
        break;
      }
      const nimm = Math.min(dv, BLOCK_VB - eimer.vsize);
      eimer.vsize += nimm;
      eimer.sat += rate * nimm;
      eimer.hoechste = eimer.hoechste === null ? rate : Math.max(eimer.hoechste, rate);
      eimer.tiefste = eimer.tiefste === null ? rate : Math.min(eimer.tiefste, rate);
      dv -= nimm;
      if (eimer.vsize >= BLOCK_VB - 0.5) schliessen();
    }
  }
  schliessen();
  if (uebrig_vsize > 0) {
    bloecke.push({ vsize: uebrig_vsize, sat: uebrig_sat, hoechste: null, tiefste: null,
                   rest: Math.max(1, Math.round(uebrig_vsize / BLOCK_VB)) });
  }
  return bloecke;
}

function zeichneKommendeBloecke(roh) {
  const ziel = $("#a-kommend");
  if (!ziel) return;
  ziel.textContent = "";
  const bloecke = kommendeBloecke(roh);
  ziel.parentElement.classList.toggle("hidden", !bloecke.length);
  if (!bloecke.length) return;

  bloecke.forEach((b, i) => {
    const kasten = document.createElement("div");
    kasten.className = "blockkasten kommend" + (b.rest ? " rest" : "");

    const kopf = document.createElement("span");
    kopf.className = "bk-kopf";
    kopf.textContent = b.rest
      ? t("a_kb_rest", { n: zahl(b.rest) })
      : t("a_kb_spanne", { tief: diaGebuehrText(b.tiefste),
                           hoch: diaGebuehrText(b.hoechste) });

    const betrag = document.createElement("span");
    betrag.className = "bk-gross";
    betrag.textContent = btc(Math.round(b.sat));

    const groesse = document.createElement("span");
    groesse.className = "bk-zeile";
    groesse.textContent = menschenBytes(b.vsize);

    const wann = document.createElement("span");
    wann.className = "bk-fuss";
    // Rund zehn Minuten je Block -- das ist die Zielrate des Netzes und die
    // ehrlichste Auskunft, die sich ohne Wahrsagerei geben laesst.
    wann.textContent = b.rest ? "" : t("a_kb_in", { min: (i + 1) * 10 });

    kasten.append(kopf, betrag, groesse, wann);
    ziel.append(kasten);
  });
}

/* ── Die Kacheln: jede wartende Transaktion als Flaeche ──────────────────
 *
 * Eine SPALTE JE BLOCK, und darin die Transaktionen, die in diesen Block
 * passen -- als Flaechen nach ihrer Groesse. Damit beantwortet das Bild
 * woertlich die Frage, mit der es angefangen hat: welche Transaktion liegt
 * in welchem Block?
 *
 * Alles davon kommt aus dem eigenen Knoten. Kein fremder Server, keine
 * fremde Bibliothek -- der Kachelaufbau steht hier, in vierzig Zeilen.
 *
 * Auf Canvas statt aus Elementen: bei zwoelftausend Kacheln waeren das
 * zwoelftausend divs, und der Browser haette daran zu kauen. Gezeichnet wird
 * einmal, darueber liegt eine Trefferliste fuer die Maus.
 */
// 446 statt 420 seit dem 21.09.2026: der Kopf braucht 48 statt 22 Punkte,
// und die Kacheln sollen dadurch nicht kleiner werden.
const KACHEL_HOEHE = 446;
// Welche Spalte gerade aufgeklappt ist. null heisst: keine.
let KACHEL_OFFEN = null;
// Wo die Spalten liegen -- einmal beim Zeichnen gemerkt, damit der Klick
// nicht dieselbe Rechnung ein zweites Mal (und womoeglich anders) macht.
let KACHEL_SPALTEN = [];
// Schmaler wird eine Blockspalte nicht -- sonst ist nichts mehr zu erkennen.
const KACHEL_SPALTE_MIN = 150;
// Ein voller Block hat ueber tausend Transaktionen. Wer die ersten
// fuenfhundert nach Gebuehr gesehen hat, hat die Aussage.
const KACHEL_LISTE_GRENZE = 500;
let KACHEL_DATEN = null;
let KACHEL_TREFFER = [];      // {x, y, b, h, kachel} in Anzeigekoordinaten

/* Squarified Treemap: die Kacheln zeilenweise so einteilen, dass sie
   moeglichst quadratisch werden. Lange duenne Streifen kann man nicht
   vergleichen -- darum geht der Aufwand. */
function kachelnLegen(werte, x, y, breite, hoehe, raus) {
  if (!werte.length || breite <= 0 || hoehe <= 0) return;
  const summe = werte.reduce((a, w) => a + w.wert, 0);
  if (summe <= 0) return;
  let rest = werte.slice();
  let restSumme = summe;

  while (rest.length) {
    const kurz = Math.min(breite, hoehe);
    const reihe = [];
    let reiheSumme = 0;
    let bestes = Infinity;
    // So lange Kacheln in die Reihe nehmen, wie das Seitenverhaeltnis besser
    // wird. Wird es schlechter, ist die Reihe voll.
    while (rest.length) {
      const naechste = rest[0];
      const probe = reiheSumme + naechste.wert;
      // Die Reihe liegt QUER zur kurzen Seite: ihre Dicke folgt aus der
      // Flaeche, die Ausdehnung jeder Kachel aus ihrem Anteil an der kurzen
      // Seite. Ein erster Anlauf rechnete die Ausdehnung als Anteil an der
      // Dicke -- damit war das Seitenverhaeltnis immer besser, die Reihe nie
      // voll, und heraus kamen lange duenne Streifen statt Quadrate.
      const dicke = ((probe / restSumme) * breite * hoehe) / kurz;
      let schlimmstes = 0;
      for (const k of reihe.concat([naechste])) {
        const seite = (k.wert / probe) * kurz;
        schlimmstes = Math.max(schlimmstes,
                               Math.max(dicke / (seite || 1e-9),
                                        (seite || 1e-9) / dicke));
      }
      if (reihe.length && schlimmstes > bestes) break;
      reihe.push(rest.shift());
      reiheSumme = probe;
      bestes = schlimmstes;
    }

    const flaeche = (reiheSumme / restSumme) * breite * hoehe;
    const dicke = flaeche / kurz;
    let versatz = 0;
    for (const k of reihe) {
      const seite = (k.wert / reiheSumme) * kurz;
      if (breite >= hoehe) {
        raus.push({ x, y: y + versatz, b: dicke, h: seite, stueck: k.stueck });
      } else {
        raus.push({ x: x + versatz, y, b: seite, h: dicke, stueck: k.stueck });
      }
      versatz += seite;
    }
    if (breite >= hoehe) { x += dicke; breite -= dicke; }
    else { y += dicke; hoehe -= dicke; }
    restSumme -= reiheSumme;
  }
}

/* Die Farbe sagt, in welchen Block die Transaktion faellt: der naechste am
   hellsten, danach abnehmend. Bewusst in unserem Orange und nicht im
   Regenbogen -- die Reihenfolge soll man sehen, nicht raten. */
function kachelFarbe(block, gesamt) {
  const t = gesamt <= 1 ? 0 : block / (gesamt - 1);
  const h = 38 - t * 12;                 // Orange nach Braun
  const l = 62 - t * 38;                 // hell nach dunkel
  const s = 92 - t * 30;
  return `hsl(${h} ${s}% ${l}%)`;
}

function zeichneKacheln() {
  const flaeche = $("#a-kacheln");
  const d = KACHEL_DATEN;
  if (!flaeche || !d) return;
  // Eine Mindestbreite JE SPALTE. Auf 375 Pixel waeren vier Spalten je
  // siebenundachtzig Pixel breit -- darin sind zwoelfhundert Kacheln nicht
  // mehr zu unterscheiden. Dann rollt das Bild lieber seitlich, wie der
  // Blockstreifen darueber auch.
  const bl = (KACHEL_DATEN.bloecke || []).length || 1;
  const kasten = Math.round(flaeche.parentElement.getBoundingClientRect().width);
  const breite = Math.max(320, kasten, bl * KACHEL_SPALTE_MIN);
  const dichte = window.devicePixelRatio || 1;
  flaeche.width = Math.round(breite * dichte);
  flaeche.height = Math.round(KACHEL_HOEHE * dichte);
  flaeche.style.width = breite + "px";
  flaeche.style.height = KACHEL_HOEHE + "px";
  const c = flaeche.getContext("2d");
  c.setTransform(dichte, 0, 0, dichte, 0, 0);
  c.clearRect(0, 0, breite, KACHEL_HOEHE);

  const bloecke = d.bloecke || [];
  if (!bloecke.length) return;
  KACHEL_TREFFER = [];
  KACHEL_SPALTEN = [];

  // VIER Zeilen Kopf statt zwei. Der Befund vom 21.09.2026 kam als
  // Vergleich mit mempool.space: dort steht je Block, WANN er kommt, wie
  // viele Transaktionen darin stehen und was sie zusammen zahlen -- hier
  // stand nur die Gebuehrenspanne, obwohl die Anwendung anzahl und sat
  // laengst mitliefert. Sie wurden gezeichnet und weggeworfen.
  //
  // Dazu ein Zweites aus demselben Bild: die erste Spalte las sich "ock".
  // Die Beschriftung war breiter als die Spalte und lief in den Nachbarn --
  // bei acht Bloecken auf einem schmalen Fenster passt "naechster Block"
  // schlicht nicht. Gemessen wird jetzt, und was nicht passt, wird gekuerzt.
  const KOPF = 48, LUFT = 6;
  const spalte = (breite - LUFT * (bloecke.length - 1)) / bloecke.length;

  // Wie lange ein Block im Schnitt braucht. Zehn Minuten ist die Zielgroesse
  // des Protokolls; genauer waere die Zeit seit dem letzten Block, und die
  // hat diese Ansicht nicht. "~" steht davor, weil es eine Erwartung ist.
  const BLOCKMINUTEN = 10;

  // Text, der in die Spalte passt -- sonst lieber gekuerzt als ueberlappend.
  const passend = (text, platz) => {
    if (c.measureText(text).width <= platz) return text;
    let kurz = text;
    while (kurz.length > 1 && c.measureText(kurz + "…").width > platz) {
      kurz = kurz.slice(0, -1);
    }
    return kurz.length > 1 ? kurz + "…" : "";
  };

  bloecke.forEach((b, i) => {
    const x = i * (spalte + LUFT);
    KACHEL_SPALTEN.push({ x, breite: spalte, block: i });
    c.textBaseline = "top";
    c.font = '600 11px ui-monospace, "SF Mono", Menlo, monospace';
    // Der naechste Block ist der, auf den es ankommt -- er wird heller.
    c.fillStyle = i === 0 ? "rgba(255,205,130,.95)" : "rgba(255,190,105,.7)";
    c.fillText(passend(
      i === 0 ? t("a_kx_naechster") : t("a_kx_spaeter", { n: i + 1 }),
      spalte), x, 0);

    c.font = '11px ui-monospace, "SF Mono", Menlo, monospace';
    // WANN. Die Frage, die man an eine Blockliste wirklich hat -- und die
    // einzige Zeile, die auch auf der schmalsten Spalte noch hinpasst.
    c.fillStyle = "rgba(255,190,105,.55)";
    c.fillText(passend(t("a_kb_wann", { min: (i + 1) * BLOCKMINUTEN }),
                       spalte), x, 12);

    // Ab hier nach Platz. Vier halbe Zeilen sind schlechter als zwei ganze:
    // "0.11 – 2.…" beantwortet keine Frage. Also wird weggelassen, was
    // nicht vollstaendig hinpasst -- nicht gekuerzt.
    const spanne = b.tiefste != null ? t("a_kb_spanne", {
      tief: diaGebuehrText(b.tiefste), hoch: diaGebuehrText(b.hoechste),
    }) : "";
    const inhalt = t("a_kb_inhalt", {
      n: zahl(b.anzahl), btc: (b.sat / 1e8).toFixed(4),
    });
    c.fillStyle = "rgba(255,190,105,.45)";
    if (spanne && c.measureText(spanne).width <= spalte) {
      c.fillText(spanne, x, 24);
    }
    if (c.measureText(inhalt).width <= spalte) {
      c.fillText(inhalt, x, 36);
    } else {
      // Passt die lange Form nicht, wenigstens die Zahl der Transaktionen
      // -- sie ist die aussagekraeftigere Haelfte.
      const kurz = zahl(b.anzahl) + " TX";
      if (c.measureText(kurz).width <= spalte) c.fillText(kurz, x, 36);
    }

    const eigene = (d.kacheln || []).filter((k) => k.block === i);
    // Absteigend nach Groesse -- ohne das arbeitet der Algorithmus, aber
    // die Quadrate werden schlechter. Das ist seine Voraussetzung.
    //
    // Die Restkachel bleibt davon ausgenommen und kommt ans ENDE. Sie ist
    // die SUMME der kleinsten und damit flaechenmaessig gross; nach Groesse
    // einsortiert saesse sie als blasser Klotz oben links -- also genau da,
    // wo die dicksten Einzeltransaktionen hingehoeren. Unten rechts liest
    // sie sich als das, was sie ist: "und dann noch viele kleine".
    const werte = eigene.filter((k) => !k.rest)
                        .map((k) => ({ wert: k.vsize, stueck: k }))
                        .sort((a, b2) => b2.wert - a.wert);
    for (const k of eigene) {
      if (k.rest) werte.push({ wert: k.vsize, stueck: k });
    }
    // Die HOEHE folgt der Fuellung. Der letzte Block ist meist nur halb
    // voll -- ihn ueber die ganze Spalte zu ziehen behauptete, er waere so
    // gross wie die vollen davor. Genau umgekehrt ist die Aussage
    // interessant: man sieht, wo der Mempool aufhoert.
    const voll = Math.max(0.06, Math.min(1, (b.vsize || 0) / 1e6));
    const nutzbar = (KACHEL_HOEHE - KOPF) * voll;
    const gelegt = [];
    kachelnLegen(werte, x, KOPF + (KACHEL_HOEHE - KOPF - nutzbar),
                 spalte, nutzbar, gelegt);
    for (const g of gelegt) {
      c.fillStyle = kachelFarbe(i, bloecke.length);
      // Die Restkachel fasst zusammen, was einzeln kleiner als ein Pixel
      // waere. Gedaempft, damit sie nicht wie eine einzelne grosse
      // Transaktion aussieht.
      c.globalAlpha = g.stueck.rest ? 0.45 : 1;
      c.fillRect(g.x, g.y, Math.max(1, g.b - 0.6), Math.max(1, g.h - 0.6));
      c.globalAlpha = 1;
      KACHEL_TREFFER.push(g);
    }

    // Die aufgeklappte Spalte bekommt einen Rahmen. Ohne ihn weiss man nach
    // dem Klick nicht mehr, welche Liste da unten steht.
    if (KACHEL_OFFEN === i) {
      // NACH INNEN gezeichnet: bei der ersten Spalte liegt x-1 ausserhalb
      // der Flaeche, und der Rahmen war dort halb abgeschnitten.
      c.strokeStyle = "#f7931a";
      c.lineWidth = 3;
      c.strokeRect(x + 1.5, KOPF + 1.5, spalte - 3, KACHEL_HOEHE - KOPF - 3);
    }
  });
}

/* Welche Spalte liegt an dieser Stelle? */
function kachelSpalteBei(x) {
  for (const s of KACHEL_SPALTEN) {
    if (x >= s.x && x <= s.x + s.breite) return s.block;
  }
  return null;
}

function kachelKlick(e) {
  const flaeche = $("#a-kacheln");
  const kasten = flaeche.getBoundingClientRect();
  const i = kachelSpalteBei(e.clientX - kasten.left);
  if (i === null) return;
  oeffneKachelBlock(i);
}

/* Was in diesem kommenden Block stehen wird.
 *
 * Kein zusaetzlicher Aufruf: die Kacheln liegen laengst im Browser. Die
 * Liste ist damit das Gegenstueck zum geschuerften Block -- dort steht, was
 * DRIN WAR und wie lange es bei uns lag, hier, was voraussichtlich
 * hineinkommt. */
function oeffneKachelBlock(i) {
  const ziel = $("#a-kachel-detail");
  if (KACHEL_OFFEN === i) {                 // zweiter Klick schliesst
    KACHEL_OFFEN = null;
    ziel.hidden = true;
    ziel.textContent = "";
    zeichneKacheln();
    return;
  }
  KACHEL_OFFEN = i;
  zeichneKacheln();

  const d = KACHEL_DATEN || {};
  const b = (d.bloecke || [])[i] || {};
  const liste = (d.kacheln || []).filter((k) => k.block === i)
                                 .sort((x, y) => y.satvb - x.satvb);

  ziel.textContent = "";
  ziel.hidden = false;

  const kopf = document.createElement("h4");
  kopf.textContent = i === 0 ? t("a_kd_titel_naechster")
                             : t("a_kd_titel", { n: i + 1 });
  ziel.append(kopf);

  const lead = document.createElement("p");
  lead.className = "dim small";
  lead.textContent = t("a_kd_lead", {
    anzahl: zahl(b.anzahl || 0), groesse: menschenBytes(b.vsize || 0),
    gebuehren: btc(b.sat || 0),
  });
  ziel.append(lead);

  const huelle = document.createElement("div");
  huelle.className = "ausw-tabelle";
  const tabelle = document.createElement("table");
  const kopfzeile = document.createElement("tr");
  [["a_bd_sp_txid", ""], ["a_kx_rate", "zahl"], ["a_kx_groesse", "zahl"],
   ["a_bd_sp_zuerst", "zahl"]].forEach(([schluessel, klasse]) => {
    const th = document.createElement("th");
    if (klasse) th.className = klasse;
    th.textContent = t(schluessel);
    kopfzeile.append(th);
  });
  tabelle.append(kopfzeile);

  for (const k of liste.filter((x) => !x.rest).slice(0, KACHEL_LISTE_GRENZE)) {
    const tr = document.createElement("tr");
    const zelle = (text, klasse) => {
      const td = document.createElement("td");
      if (klasse) td.className = klasse;
      td.textContent = text;
      tr.append(td);
    };
    zelle(k.txid, "txid");
    zelle(diaGebuehrText(k.satvb) + " sat/vB", "zahl");
    zelle(menschenBytes(k.vsize), "zahl");
    // Die Spalte, die kein Explorer hat.
    zelle(k.zuerst_ms ? datumZeit(k.zuerst_ms) : t("a_kx_ungesehen"), "zahl");
    tabelle.append(tr);
  }
  huelle.append(tabelle);
  ziel.append(huelle);

  const einzeln = liste.filter((x) => !x.rest).length;
  const rest = liste.find((x) => x.rest);
  if (einzeln > KACHEL_LISTE_GRENZE || rest) {
    const mehr = document.createElement("p");
    mehr.className = "dim small";
    mehr.textContent = t("a_kd_gekuerzt", {
      n: zahl(Math.min(einzeln, KACHEL_LISTE_GRENZE)),
      gesamt: zahl(einzeln + (rest ? rest.anzahl : 0)),
    });
    ziel.append(mehr);
  }
  ziel.scrollIntoView({ block: "nearest" });
}

function kachelBei(x, y) {
  for (const g of KACHEL_TREFFER) {
    if (x >= g.x && x <= g.x + g.b && y >= g.y && y <= g.y + g.h) return g;
  }
  return null;
}

function kachelBlaseAus() {
  const blase = $("#a-kachel-blase");
  if (blase) blase.hidden = true;
}

function kachelZeigen(e) {
  const flaeche = $("#a-kacheln");
  const blase = $("#a-kachel-blase");
  if (!flaeche || !blase) return;
  const kasten = flaeche.getBoundingClientRect();
  const g = kachelBei(e.clientX - kasten.left, e.clientY - kasten.top);
  if (!g) { kachelBlaseAus(); return; }
  const k = g.stueck;
  blase.textContent = "";
  const zeile = (name, wert) => {
    const el = document.createElement("div");
    const a = document.createElement("span"); a.className = "k"; a.textContent = name;
    const b = document.createElement("span"); b.className = "v"; b.textContent = wert;
    el.append(a, b); blase.append(el);
  };
  if (k.rest) {
    zeile(t("a_kx_rest"), zahl(k.anzahl));
    zeile(t("a_kx_groesse"), menschenBytes(k.vsize));
    zeile(t("a_kx_rate"), t("a_kx_bis", { wert: diaGebuehrText(k.satvb) }));
  } else {
    zeile(t("a_kx_tx"), k.txid.slice(0, 16) + "…");
    zeile(t("a_kx_rate"), diaGebuehrText(k.satvb) + " sat/vB");
    zeile(t("a_kx_groesse"), menschenBytes(k.vsize));
    // Die Zeile, die kein Explorer hat.
    zeile(t("a_kx_zuerst"),
          k.zuerst_ms ? datumZeit(k.zuerst_ms) : t("a_kx_ungesehen"));
  }
  blase.hidden = false;
  const b = blase.getBoundingClientRect();
  blase.style.left = Math.min(kasten.width - b.width - 4,
                              Math.max(0, e.clientX - kasten.left + 12)) + "px";
  blase.style.top = Math.max(0, e.clientY - kasten.top - b.height - 10) + "px";
}

async function ladeKacheln() {
  const knopf = $("#a-kachel-holen");
  const meldung = $("#a-kachel-meldung");
  knopf.disabled = true;
  meldung.textContent = t("a_kx_laedt");
  try {
    KACHEL_DATEN = await api("/auswertung/mempool/kacheln", "GET", null,
                             FRIST_KACHELN_MS);
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung)
      : (e.zeitlimit || e.netzfehler) ? t("a_kx_zu_lang")
      : t("e_fehler");
    return;
  } finally {
    knopf.disabled = false;
  }
  meldung.textContent = t("a_kx_stand", {
    n: zahl(KACHEL_DATEN.gesamt),
    gezeigt: zahl((KACHEL_DATEN.kacheln || []).length),
  });
  $("#a-kachel-flaeche").hidden = false;
  zeichneKacheln();
}

/* Was zahlt man, um noch bis zu dieser Tiefe zu kommen? Die Kurve faellt,
   also ist es der Wert am letzten Punkt, der noch davor liegt. */
function diaGebuehrBei(punkte, vsize) {
  if (punkte[punkte.length - 1].vsize <= vsize) return null;   // passt alles
  let letzter = punkte[0].satvb;
  for (const p of punkte) {
    if (p.vsize > vsize) break;
    letzter = p.satvb;
  }
  return letzter;
}

function diaGebuehrText(wert) {
  return wert >= 10 ? wert.toFixed(0) : wert.toFixed(wert >= 1 ? 1 : 2);
}

/* Bei geaenderter Breite neu auftragen. Ein festes viewBox braeuchte das
   nicht -- aber ein festes viewBox war ja gerade der Fehler. */
let DIA_ZEICHNEN_BALD = 0;

function diaNeuZeichnenBald() {
  clearTimeout(DIA_ZEICHNEN_BALD);
  DIA_ZEICHNEN_BALD = setTimeout(() => {
    if (DIA_DATEN) zeichneDiagramm(undefined, undefined);
  }, 120);
}

/* ── Die geschuerften Bloecke als Streifen ────────────────────────────────
 *
 * Dieselben Daten wie die Tabelle darunter, nur als Ueberblick -- und
 * anklickbar. Denn hier liegt der Unterschied zu jedem Explorer: nicht
 * "welche Transaktionen sind in dem Block" (das weiss jeder), sondern
 * "welche davon lagen vorher bei MIR und wie lange". Einen
 * First-Seen-Zeitstempel kann man nicht nachtraeglich erfinden.
 */
let BLOCK_OFFEN = null;

function zeichneBlockstreifen(liste) {
  const ziel = $("#a-blockstreifen");
  if (!ziel) return;
  ziel.textContent = "";
  liste.forEach((b) => {
    const kasten = document.createElement("button");
    kasten.type = "button";
    kasten.className = "blockkasten geschuerft"
      + (BLOCK_OFFEN === b.hoehe ? " offen" : "");
    kasten.dataset.hoehe = String(b.hoehe);

    const kopf = document.createElement("span");
    kopf.className = "bk-kopf";
    kopf.textContent = zahl(b.hoehe);

    const pool = document.createElement("span");
    pool.className = "bk-gross" + (b.pool ? "" : " unbekannt");
    pool.textContent = b.pool || t("a_pool_unbekannt");

    const tx = document.createElement("span");
    tx.className = "bk-zeile";
    // Die Zahl, die kein Explorer hat, steht direkt daneben -- nicht die
    // Gesamtzahl allein, sondern wie viele davon vorher bei uns lagen.
    // DER BEFUND VOM 22.09.2026: hier stand zahl(b.bekannte_tx || 0). Das
    // Backend setzt dieses Feld AUSDRUECKLICH auf None, mit der Begruendung
    // "wir waren nicht dabei, und eine Null saehe aus wie eine Messung" --
    // und die Oberflaeche machte daraus genau diese Messung. Bei einem
    // Block, den dieser Knoten nie live gesehen hat, stand da "0 / 2431 Tx".
    //
    // Nebenan wurde es richtig gemacht: verweildauer_ms, aus demselben
    // Dict, wird mit "!= null ? ... : '—'" behandelt.
    if (b.bekannte_tx == null) {
      tx.textContent = t("a_kb_nur_gesamt", { gesamt: zahl(b.txzahl || 0) });
      tx.title = t("a_kb_nicht_dabei", { gesamt: zahl(b.txzahl || 0) });
    } else {
      tx.textContent = t("a_kb_bekannt", { n: zahl(b.bekannte_tx),
                                           gesamt: zahl(b.txzahl || 0) });
      tx.title = t("a_kb_bekannt_lang", { n: zahl(b.bekannte_tx),
                                          gesamt: zahl(b.txzahl || 0) });
    }

    const fuss = document.createElement("span");
    fuss.className = "bk-fuss";
    fuss.textContent = b.blockzeit
      ? t("a_kb_vor", { dauer: dauerKurz(Date.now() - b.blockzeit * 1000) })
      : "";

    kasten.append(kopf, pool, tx, fuss);
    kasten.addEventListener("click", () => oeffneBlock(b.hoehe));
    ziel.append(kasten);
  });
}

async function oeffneBlock(hoehe) {
  const ziel = $("#a-blockdetail");
  if (BLOCK_OFFEN === hoehe) {         // zweiter Klick schliesst wieder
    BLOCK_OFFEN = null;
    ziel.hidden = true;
    ziel.textContent = "";
    zeichneBlockstreifen(BLOCK_LISTE);
    return;
  }
  BLOCK_OFFEN = hoehe;
  zeichneBlockstreifen(BLOCK_LISTE);
  ziel.hidden = false;
  ziel.textContent = "";
  ziel.append(hinweis(t("a_bd_laedt"), ""));

  let d;
  try {
    d = await api("/auswertung/block/" + encodeURIComponent(hoehe));
  } catch (e) {
    if (e && e.abgemeldet) return;
    ziel.textContent = "";
    ziel.append(hinweis(t("a_bd_nichts"), "warn"));
    return;
  }
  zeichneBlockdetail(d);
}

function zeichneBlockdetail(d) {
  const ziel = $("#a-blockdetail");
  ziel.textContent = "";
  const b = d.block || {};

  const kopf = document.createElement("h4");
  kopf.textContent = t("a_bd_titel", { hoehe: zahl(b.hoehe) });
  ziel.append(kopf);

  const lead = document.createElement("p");
  lead.className = "dim small";
  lead.textContent = b.bekannte_tx == null
    ? t("a_bd_lead_nicht_dabei", { gesamt: zahl(b.txzahl || 0) })
    : t("a_bd_lead", { bekannt: zahl(b.bekannte_tx),
                       gesamt: zahl(b.txzahl || 0) });
  ziel.append(lead);

  const liste = d.transaktionen || [];
  if (!liste.length) {
    // Ehrlich benennen, statt eine leere Tabelle hinzustellen: entweder war
    // der Block vor unserer Zeit, oder wir haben seine Transaktionen nie im
    // Mempool gesehen.
    ziel.append(hinweis(t("a_bd_leer"), ""));
    return;
  }

  const huelle = document.createElement("div");
  huelle.className = "ausw-tabelle";
  const tabelle = document.createElement("table");
  const kopfzeile = document.createElement("tr");
  [["a_bd_sp_txid", ""], ["a_bd_sp_zuerst", "zahl"],
   ["a_bd_sp_dauer", "zahl"]].forEach(([schluessel, klasse]) => {
    const th = document.createElement("th");
    if (klasse) th.className = klasse;
    th.textContent = t(schluessel);
    kopfzeile.append(th);
  });
  tabelle.append(kopfzeile);

  liste.forEach((x) => {
    const tr = document.createElement("tr");
    const a = document.createElement("td");
    a.className = "txid";
    a.textContent = x.txid;
    a.title = x.txid;
    const b2 = document.createElement("td");
    b2.className = "zahl";
    b2.textContent = datumZeit(x.zuerst_ms);
    const c = document.createElement("td");
    c.className = "zahl";
    c.textContent = x.verweildauer_ms != null ? dauerKurz(x.verweildauer_ms) : "—";
    tr.append(a, b2, c);
    tabelle.append(tr);
  });
  huelle.append(tabelle);
  ziel.append(huelle);

  if (liste.length >= (d.grenze || 500)) {
    const mehr = document.createElement("p");
    mehr.className = "dim small";
    mehr.textContent = t("a_bd_gekuerzt", { n: zahl(d.grenze || 500) });
    ziel.append(mehr);
  }
}

let BLOCK_LISTE = [];

function zeichneBloecke(liste) {
  BLOCK_LISTE = liste;
  zeichneBlockstreifen(liste);
  const tabelle = $("#a-bloecke");
  tabelle.textContent = "";
  if (!liste.length) return;

  const kopf = document.createElement("tr");
  // Die Botschaft hat jetzt eine eigene Spalte. Sie stand vorher nur im
  // title-Attribut der Pool-Zelle -- also fuer niemanden sichtbar, der nicht
  // zufaellig mit der Maus darauf stehenbleibt. Aus dem Betrieb, 08.09.2026:
  // "muss man ne btc adresse haben um nachrichten ... zu lesen??" Nein.
  [["a_sp_hoehe", ""], ["a_sp_pool", ""], ["a_sp_botschaft", "botschaft"],
   ["a_sp_tx", "zahl"],
   ["a_sp_bekannt", "zahl"], ["a_sp_dauer", "zahl"], ["a_sp_gebuehren", "zahl"]]
    .forEach(([schluessel, klasse]) => {
      const th = document.createElement("th");
      if (klasse) th.className = klasse;
      th.textContent = t(schluessel);
      kopf.append(th);
    });
  tabelle.append(kopf);

  liste.forEach((b) => {
    const tr = document.createElement("tr");
    const zelle = (text, klasse, titel) => {
      const td = document.createElement("td");
      if (klasse) td.className = klasse;
      td.textContent = text;
      if (titel) td.title = titel;
      tr.append(td);
    };
    zelle(zahl(b.hoehe), "hoehe");
    zelle(b.pool || t("a_pool_unbekannt"),
          "pool" + (b.pool ? "" : " unbekannt"));
    // Was der Miner ins Feld geschrieben hat. Meistens seine Kennung,
    // manchmal mehr -- "MARA Made in USA", "Mined by ecgbtc". Im Block 0
    // steht dort die Schlagzeile, mit der alles anfing.
    zelle(b.botschaft || "", "botschaft", b.botschaft || "");
    zelle(zahl(b.txzahl || 0), "zahl");
    // Die eine Spalte, die kein Explorer hat: wie viele davon lagen VORHER
    // bei uns im Mempool.
    // Gedankenstrich wie in den Nachbarspalten -- "nicht gemessen" ist
    // etwas anderes als "keine".
    zelle(b.bekannte_tx != null ? zahl(b.bekannte_tx) : "—", "zahl",
          b.bekannte_tx == null ? t("a_nicht_dabei_kurz") : "");
    zelle(b.verweildauer_ms != null ? dauerKurz(b.verweildauer_ms) : "—", "zahl");
    zelle(b.gebuehren_sat != null ? btc(b.gebuehren_sat) : "—", "zahl");
    tabelle.append(tr);
  });
}

/* Einen Block nachschlagen -- irgendeinen, nicht nur die letzten zwoelf.
 *
 * Der Anlass, 08.09.2026: der Betreiber wollte Satoshis Schlagzeile sehen. Die
 * Blockansicht wirbt in ihrem eigenen Erklaertext damit und kannte doch nur
 * die juengsten Bloecke. Ein Versprechen, das die Oberflaeche selbst gibt
 * und nicht einloest.
 */
async function blockNachschlagen(hoehe) {
  const feld = $("#a-blockhoehe");
  const ziel = $("#a-blocksuche");
  const eingabe = hoehe === undefined ? feld.value.trim() : String(hoehe);
  ziel.textContent = "";
  if (!eingabe) return;
  if (!/^\d+$/.test(eingabe)) {
    ziel.append(hinweis(t("a_bs_keine_hoehe"), "warn"));
    return;
  }
  ziel.append(hinweis(t("a_bd_laedt"), ""));

  let d;
  try {
    d = await api("/auswertung/block/" + encodeURIComponent(eingabe));
  } catch (e) {
    if (e && e.abgemeldet) return;
    const m = (e.detail || {}).meldung;
    ziel.textContent = "";
    ziel.append(hinweis(m ? t(m) : t("e_fehler"), "warn"));
    return;
  }
  zeichneBlocksuche(d);
}

function zeichneBlocksuche(d) {
  const ziel = $("#a-blocksuche");
  const b = d.block || {};
  ziel.textContent = "";

  const kopf = document.createElement("h4");
  kopf.textContent = t("a_bs_kopf", { hoehe: zahl(b.hoehe) });
  ziel.append(kopf);

  // Die Botschaft zuerst und gross: sie ist der Grund, warum jemand einen
  // alten Block nachschlaegt.
  if (b.botschaft) {
    const zitat = document.createElement("div");
    zitat.className = "botschaft-gross";
    zitat.textContent = b.botschaft;
    ziel.append(zitat);
  }

  const zeile = (name, wert) => {
    const el = document.createElement("div");
    el.className = "treffer-zeile";
    const a = document.createElement("span"); a.className = "k"; a.textContent = name;
    const c = document.createElement("span"); c.className = "v"; c.textContent = wert;
    el.append(a, c); ziel.append(el);
  };
  if (b.blockzeit) zeile(t("a_bs_zeit"), datumZeit(b.blockzeit * 1000));
  zeile(t("a_sp_pool"), b.pool || t("a_pool_unbekannt"));
  if (b.txzahl != null) zeile(t("a_sp_tx"), zahl(b.txzahl));
  if (b.gewicht != null) zeile(t("a_bs_gewicht"), menschenBytes(b.gewicht / 4));
  if (b.gebuehren_sat != null) zeile(t("a_sp_gebuehren"), btc(b.gebuehren_sat));
  if (b.hash) zeile(t("a_bs_hash"), b.hash);

  // Ehrlich sagen, woher es kommt. Ein alter Block hat keine Verweildauer,
  // und eine Null waere hier eine Behauptung.
  const woher = document.createElement("p");
  woher.className = "dim small";
  woher.textContent = d.aus_kette ? t("a_bs_aus_kette") : t("a_bs_aus_aufzeichnung");
  ziel.append(woher);

  if (!d.aus_kette && b.bekannte_tx != null) {
    const eigen = document.createElement("p");
    eigen.className = "dim small";
    eigen.textContent = t("a_bd_lead", { bekannt: zahl(b.bekannte_tx),
                                         gesamt: zahl(b.txzahl || 0) });
    ziel.append(eigen);
  }
}

async function verfolgeTx() {
  const ziel = $("#a-treffer");
  const eingabe = $("#a-txid").value.trim().toLowerCase();
  ziel.textContent = "";
  if (!eingabe) return;

  let d;
  try {
    d = await api("/auswertung/tx/" + encodeURIComponent(eingabe));
  } catch (e) {
    if (e && e.abgemeldet) return;
    const meldung = e.detail && e.detail.meldung;
    ziel.append(hinweis(t(meldung === "keine_txid" ? "a_keine_txid"
                                                   : "a_tx_unbekannt"), "warn"));
    return;
  }

  const zeile = (k, v, hervor) => {
    const el = document.createElement("div");
    el.className = "treffer-zeile";
    const a = document.createElement("span"); a.className = "k"; a.textContent = k;
    const b = document.createElement("span");
    b.className = "v" + (hervor ? " hervor" : ""); b.textContent = v;
    el.append(a, b); ziel.append(el);
  };

  if (d.eigen) {
    // Zuerst und hervorgehoben: das ist die Zahl, die dieser Knoten exklusiv
    // hat. Alles darunter weiss auch jeder Explorer.
    zeile(t("a_tx_zuerst"), datumZeit(d.eigen.zuerst_ms), true);
    if (d.eigen.verweildauer_ms != null)
      zeile(t("a_tx_dauer"), dauerKurz(d.eigen.verweildauer_ms), true);
    if (d.eigen.hoehe) zeile(t("a_tx_block"), zahl(d.eigen.hoehe));
    if (d.eigen.entfernt_ms)
      zeile(t("a_tx_entfernt"), datumZeit(d.eigen.entfernt_ms));
  } else {
    ziel.append(hinweis(t("a_tx_nicht_gesehen"), ""));
  }

  if (d.knoten) {
    zeile(t("a_tx_groesse"), zahl(d.knoten.groesse || 0) + " vB");
    zeile(t("a_tx_bestaetigungen"), zahl(d.knoten.bestaetigungen || 0));
    zeile(t("a_tx_ein_aus"),
          `${d.knoten.eingaenge} → ${d.knoten.ausgaenge}`);
  }

  // Der Cluster -- nur, solange sie wartet.
  if (d.cluster) {
    zeichneCluster(ziel, d.cluster);
  } else if (d.knoten && !d.knoten.bestaetigungen) {
    ziel.append(hinweis(t("a_cl_keiner"), ""));
  }
}

/* Der Cluster einer wartenden Transaktion, wie Core 31 ihn sieht: Pakete in
   Mining-Reihenfolge, das eigene hervorgehoben. */
function zeichneCluster(ziel, c) {
  const kasten = document.createElement("div");
  kasten.className = "cluster";
  const titel = document.createElement("h4");
  titel.textContent = t("a_cl_titel");
  const lead = document.createElement("p");
  lead.className = "dim small";
  lead.textContent = t("a_cl_d");
  kasten.append(titel, lead);
  if ((c.txzahl || 0) <= 1) {
    kasten.append(hinweis(t("a_cl_einzeln"), ""));
    ziel.append(kasten);
    return;
  }
  kasten.append(hinweis(t("a_cl_umfang", {
    tx: zahl(c.txzahl), pakete: zahl(c.pakete.length), vb: zahl(c.vbytes) }), ""));
  for (const paket of c.pakete) {
    const eigenes = paket.nummer === c.eigenes_paket;
    kasten.append(zeile(
      t("a_cl_paket", { nr: paket.nummer }) + (eigenes ? " · " + t("a_cl_deins") : ""),
      t("a_cl_paket_wert", { tx: zahl(paket.txs.length),
                             satz: nachkomma(paket.satz_sat_vb, 2),
                             vb: zahl(paket.vbytes) }),
      eigenes ? "hervor" : ""));
  }
  ziel.append(kasten);
}

/* ── Wer die Bloecke findet ───────────────────────────────────────────────
   Nur aus dem, was dieser Knoten selbst aufgezeichnet hat. Die Zahl der
   Bloecke dahinter steht immer dabei -- ein Anteil ohne seine Grundlage waere
   eine Behauptung. */
let POOL_FENSTER = 144;
try {
  const gemerkt = localStorage.getItem("satcortex-pool-fenster");
  if (gemerkt !== null && [144, 1008, 0].includes(Number(gemerkt))) {
    POOL_FENSTER = Number(gemerkt);
  }
} catch (e) { /* ohne Speicher: ein Tag */ }

async function ladePoolAnteile() {
  let d;
  try {
    d = await api("/auswertung/pools?bloecke=" + POOL_FENSTER);
  } catch (e) {
    return;
  }
  zeichnePoolAnteile(d);
}

function zeichnePoolAnteile(d) {
  kursSchalter("#a-pool-fenster", [144, 1008, 0], d.fenster, (fenster) => {
    POOL_FENSTER = fenster;
    try { localStorage.setItem("satcortex-pool-fenster", String(fenster)); } catch (e) { /* nur bis zum Neuladen */ }
    ladePoolAnteile();
  }, (fenster) => t("a_pa_" + fenster));
  const ziel = $("#a-pools");
  ziel.textContent = "";
  if (!d.bloecke) {
    ziel.append(hinweis(t("a_pa_leer"), ""));
    return;
  }
  ziel.append(hinweis(t("a_pa_basis", {
    n: zahl(d.bloecke), von: zahl(d.von_hoehe), bis: zahl(d.bis_hoehe) }), ""));
  if (d.fenster && d.bloecke < d.fenster) {
    ziel.append(hinweis(t("a_pa_zu_wenig", {
      n: zahl(d.bloecke), soll: zahl(d.fenster) }), "warn"));
  }
  const liste = document.createElement("ol");
  liste.className = "pool-anteile";
  const hoechster = Math.max(0.0001, ...d.pools.map((pool) => pool.anteil));
  for (const pool of d.pools) {
    const eintrag = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name" + (pool.pool ? "" : " unbekannt");
    name.textContent = pool.pool || t("a_pool_unbekannt");
    const balken = document.createElement("span");
    balken.className = "balken";
    const fuellung = document.createElement("span");
    fuellung.style.width = (100 * pool.anteil / hoechster).toFixed(1) + "%";
    balken.append(fuellung);
    const wert = document.createElement("span");
    wert.className = "anzahl";
    wert.textContent = t("a_pa_zeile", {
      anzahl: zahl(pool.anzahl), anteil: nachkomma(pool.anteil * 100, 1) });
    eintrag.append(name, balken, wert);
    liste.append(eintrag);
  }
  ziel.append(liste);
}

/* ── Eine Adresse abfragen ────────────────────────────────────────────────
   Core braucht fuer den Scan Minuten. Die Anfrage startet ihn nur; danach
   fragt die Oberflaeche den Stand ab, bis er fertig ist -- und nur, solange
   jemand hinsieht. */
let ADRESS_TAKT = null;

async function adresseAbfragen() {
  const meldung = $("#a-ad-meldung");
  const adresse = $("#a-adresse").value.trim();
  meldung.textContent = "";
  if (!adresse) return;
  $("#a-ad-los").disabled = true;
  try {
    await api("/auswertung/adresse", "POST", { adresse });
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    $("#a-ad-los").disabled = false;
    meldung.append(hinweis(d.meldung ? t(d.meldung, d) : t("e_fehler"), "warn"));
    return;
  }
  adresseStandLaden();
}

async function adresseAbbrechen() {
  try {
    await api("/auswertung/adresse/abbrechen", "POST", {});
  } catch (e) { /* was daraus wurde, sagt der Stand */ }
  adresseStandLaden();
}

async function adresseStandLaden() {
  clearTimeout(ADRESS_TAKT);
  let d;
  try {
    d = await api("/auswertung/adresse");
  } catch (e) {
    return;
  }
  zeichneAdressstand(d);
  if (d.laeuft && ANSICHT === "bloecke") {
    ADRESS_TAKT = setTimeout(adresseStandLaden, 2000);
  }
}

function zeichneAdressstand(d) {
  const meldung = $("#a-ad-meldung");
  const ziel = $("#a-ad-ergebnis");
  $("#a-ad-abbrechen").classList.toggle("hidden", !d.laeuft);
  $("#a-ad-los").disabled = !!d.laeuft;
  meldung.textContent = "";
  ziel.textContent = "";
  if (!d.adresse) return;
  if (d.laeuft) {
    const fortschritt = Number.isFinite(d.fortschritt)
      ? nachkomma(d.fortschritt, 0) + " %" : "";
    meldung.append(hinweis(t("a_ad_laeuft", { p: fortschritt }), ""));
    return;
  }
  if (d.fehler) {
    meldung.append(hinweis(t(d.fehler, { grund: d.grund || "" }),
                           d.fehler === "a_ad_abgebrochen" ? "" : "warn"));
    return;
  }
  const e = d.ergebnis;
  if (!e) return;
  const reihe = (k, v, hervor) => {
    const el = document.createElement("div");
    el.className = "treffer-zeile";
    const a = document.createElement("span"); a.className = "k"; a.textContent = k;
    const b = document.createElement("span");
    b.className = "v" + (hervor ? " hervor" : ""); b.textContent = v;
    el.append(a, b); ziel.append(el);
  };
  reihe(t("a_ad_adresse"), d.adresse);
  reihe(t("a_ad_bestand"), zahl(e.bestand_sat) + " sat", true);
  reihe(t("a_ad_ausgaben"), zahl(e.anzahl));
  reihe("", t("a_ad_stand", { hoehe: zahl(e.hoehe),
                              dauer: dauerKurz((d.dauer_s || 0) * 1000) }));
  if (!e.anzahl) {
    ziel.append(hinweis(t("a_ad_leer"), ""));
    return;
  }
  for (const a of e.ausgaben) {
    // Die volle txid statt einer gekuerzten: die liess sich weder kopieren
    // noch suchen (Befund vom 15.09.2026).
    reihe(t("a_ad_ausgabe"), zahl(a.betrag_sat) + " sat · "
      + t("a_ad_zeile", { hoehe: zahl(a.hoehe), bestaetigt: zahl(a.bestaetigungen) }));
    ziel.append(txidZeile(a.txid, a.txid + ":" + a.vout));
  }
  if (e.weitere) ziel.append(hinweis(t("a_ad_weitere", { n: zahl(e.weitere) }), ""));
}

/* ── Bewegungen der On-Chain-Wallet ────────────────────────────────────────

   Befund vom 15.09.2026, bei dem ersten Einzahlung: im Guthaben stand nur
   eine Zahl. Ob etwas angekommen war, unter welcher txid und mit wie vielen
   Bestaetigungen, liess sich nirgends ablesen. */

const BEWEGUNGEN_TAKT_MS = 30000;
let BEWEGUNGEN_TAKT = null;

async function ladeBewegungen() {
  clearTimeout(BEWEGUNGEN_TAKT);
  if (ANSICHT !== "ln-wallet") return;
  let d;
  try {
    d = await api("/lightning/bewegungen");
  } catch (e) {
    if (e && e.abgemeldet) return;
    d = { bereit: true, bewegungen: [], weitere: 0, fehler: true };
  }
  zeichneBewegungen(d);
  // Solange die Wallet offen ist: eine Einzahlung soll man ankommen sehen,
  // ohne neu zu laden.
  if (ANSICHT === "ln-wallet") {
    BEWEGUNGEN_TAKT = setTimeout(ladeBewegungen, BEWEGUNGEN_TAKT_MS);
  }
}

function zeichneBewegungen(d) {
  const ziel = $("#bw-liste");
  ziel.textContent = "";
  if (!d.bereit) return;
  if (d.fehler) {
    ziel.append(hinweis(t("bw_fehler"), "warn"));
    return;
  }
  if (!d.bewegungen.length) {
    ziel.append(hinweis(t("bw_leer"), ""));
    return;
  }
  for (const b of d.bewegungen) {
    const zeile = document.createElement("div");
    zeile.className = "bewegung";
    const kopf = document.createElement("div");
    kopf.className = "bewegung-kopf";
    const betrag = document.createElement("span");
    betrag.className = "bewegung-betrag " + (b.betrag_sat >= 0 ? "ein" : "aus");
    // In sat, nicht in BTC mit vier Nachkommastellen: die machten aus
    // 2.141 sat "0.0000 BTC" -- im Browser gesehen am 15.09.2026.
    betrag.textContent = (b.betrag_sat >= 0 ? "+" : "−")
      + zahl(Math.abs(b.betrag_sat)) + " sat";
    const stand = document.createElement("span");
    stand.className = "dim small";
    const teile = [];
    if (b.zeit_s) teile.push(datumZeit(b.zeit_s * 1000));
    teile.push(b.bestaetigungen > 0
      ? t("bw_bestaetigt", { n: zahl(b.bestaetigungen) })
      : t("bw_unbestaetigt"));
    if (b.art === "kanal_auf") teile.push(t("bw_art_kanal_auf"));
    if (b.art === "kanal_zu") teile.push(t("bw_art_kanal_zu"));
    // Bei einem Ausgang gehoert die Gebuehr dazu: der Betrag oben ist
    // Zahlung PLUS Gebuehr, und ohne die Aufteilung rechnet niemand nach.
    if (b.betrag_sat < 0 && b.gebuehr_sat) {
      teile.push(t("bw_gebuehr", { n: zahl(b.gebuehr_sat) }));
    }
    stand.textContent = teile.join(" · ");
    kopf.append(betrag, stand);
    zeile.append(kopf);
    // An WEN es ging. Stand bis zum 16.09.2026 nur im Protokoll -- gebraucht,
    // als ein Empfaenger bestritt, etwas bekommen zu haben.
    if (b.ziel) {
      const an = document.createElement("div");
      an.className = "bewegung-ziel";
      an.textContent = t("bw_an", { adresse: b.ziel });
      zeile.append(an);
    }
    zeile.append(txidZeile(b.txid, b.txid));
    // Haengt sie fest? Dann der einzige Handgriff, der hilft.
    //
    // Nur bei einem AUSGANG ohne Bestaetigung, und nur wenn ein Ausgang uns
    // gehoert: LND haengt die Kind-Transaktion an unser Wechselgeld. Wurde
    // alles verschickt, gibt es keins -- dann steht hier kein Knopf, sondern
    // der Grund. Einen Knopf anzubieten, der sicher scheitert, waere
    // schlimmer als keiner.
    if (b.betrag_sat < 0 && !b.bestaetigungen) {
      zeile.append(b.eigener_ausgang == null
        ? hinweis(t("nb_nicht_moeglich"), "")
        : nachbesserZeile(b));
    }
    ziel.append(zeile);
  }
  if (d.weitere) ziel.append(hinweis(t("bw_weitere", { n: zahl(d.weitere) }), ""));
}

/* Was LND ueber Wege gelernt hat.

   Zusammengefasst kommt es schon aus dem Backend -- ein Knoten mit Verkehr
   sammelt tausende Paare, und die gehoeren nicht in einen Browser. Hier
   stehen die Zaehler und die juengsten Eintraege. */
async function ladeWegwissen() {
  const zahlen = $("#wg-zahlen");
  const liste = $("#wg-liste");
  const meldung = $("#wg-meldung");
  if (!zahlen) return;
  let d;
  try {
    d = await api("/lightning/wegwissen");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const f = e.detail || {};
    zahlen.textContent = "";
    liste.textContent = "";
    meldung.textContent = f.meldung ? t(f.meldung, f) : t("wg_nicht_abrufbar");
    return;
  }
  meldung.textContent = "";
  zahlen.textContent = t("wg_zahlen", {
    paare: zahl(d.paare), fehl: zahl(d.mit_fehlschlag),
    erfolg: zahl(d.mit_erfolg) });
  liste.textContent = "";
  if (!d.letzte.length) {
    meldung.textContent = t("wg_leer");
    return;
  }
  const kopf = document.createElement("tr");
  for (const k of ["wg_von", "wg_nach", "wg_trug", "wg_fehl", "wg_wann"]) {
    const th = document.createElement("th");
    th.textContent = t(k);
    kopf.append(th);
  }
  liste.append(kopf);
  for (const e of d.letzte) {
    const tr = document.createElement("tr");
    for (const [wert, klasse] of [
        [e.von, "pool"], [e.nach, "pool"],
        // Null heisst hier "nie getragen" bzw. "nie versagt" -- ein
        // Gedankenstrich, keine Null. Sonst liest sich "0 sat" wie eine
        // Messung, und das war es nicht.
        [e.trug_bis_sat ? zahl(e.trug_bis_sat) : "—", "zahl"],
        [e.fehl_ab_sat ? zahl(e.fehl_ab_sat) : "—", "zahl"],
        [e.zeitpunkt ? datumZeit(e.zeitpunkt * 1000) : "—", "zahl"]]) {
      const td = document.createElement("td");
      td.className = klasse;
      td.textContent = wert;
      tr.append(td);
    }
    liste.append(tr);
  }
}

/* "Gebuehr erhoehen" fuer eine haengende Ueberweisung.

   Der Knopf sagt vorher, was er tut: es entsteht eine ZWEITE Transaktion,
   die zusaetzlich kostet. Die alte verschwindet nicht -- beide werden
   gemeinsam attraktiver (Child Pays For Parent). Wer das nicht weiss,
   erwartet sonst, dass die Gebuehr der alten einfach steigt. */
function nachbesserZeile(b) {
  const kasten = document.createElement("div");
  kasten.className = "nachbessern";

  const erklaerung = document.createElement("p");
  erklaerung.className = "dim small";
  erklaerung.textContent = t("nb_erklaerung");
  kasten.append(erklaerung);

  const meldung = document.createElement("span");
  meldung.className = "dim small";

  const knopf = document.createElement("button");
  knopf.type = "button";
  knopf.className = "btn schmal";
  knopf.textContent = t("nb_knopf");

  // Die PIN-Felder der festen Formulare stehen in der Vorlage; diese Zeile
  // entsteht erst beim Zeichnen, also baut sie ihres selbst -- und nur,
  // wenn ueberhaupt eine PIN eingerichtet ist (PIN_DA). Wer keine hat, soll
  // nicht vor einem Feld stehen, das es fuer ihn nicht gibt.
  let pinEingabe = null;
  if (PIN_DA) {
    const feld = document.createElement("label");
    feld.className = "feld schmal";
    const kopf = document.createElement("b");
    kopf.textContent = t("tg_pin");
    pinEingabe = document.createElement("input");
    pinEingabe.type = "password";
    pinEingabe.inputMode = "numeric";
    pinEingabe.autocomplete = "off";
    pinEingabe.maxLength = 12;
    feld.append(kopf, pinEingabe);
    var pin = feld;
  }

  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    meldung.textContent = t("nb_laeuft");
    let wiederFrei = true;
    try {
      const d = await api("/lightning/senden/nachbessern", "POST", {
        txid: b.txid, ausgang: b.eigener_ausgang, tempo: "schnell",
        ...(pinEingabe ? { pin: pinEingabe.value } : {}),
      }, FRIST_GELD_MS);
      meldung.textContent = t("nb_fertig", {
        satz: zahl(d.satz_sat_vb), hoechstens: zahl(d.hoechstens_sat) });
      ladeBewegungen();
    } catch (e) {
      wiederFrei = geldfehler(e, meldung, "sendung_unklar");
    } finally {
      if (wiederFrei) knopf.disabled = false;
    }
  });

  const reihe = document.createElement("div");
  reihe.className = "nachbessern-reihe";
  if (pinEingabe) reihe.append(pin);
  reihe.append(knopf, meldung);
  kasten.append(reihe);
  return kasten;
}

// Eine volle txid zum Markieren, und ein Knopf, der sie unter Bloecke verfolgt.
function txidZeile(txid, anzeige) {
  const block = document.createElement("div");
  const nummer = document.createElement("div");
  nummer.className = "bewegung-txid";
  nummer.textContent = anzeige;
  const knopf = document.createElement("button");
  knopf.type = "button";
  knopf.className = "btn ghost klein";
  knopf.textContent = t("bw_verfolgen");
  knopf.addEventListener("click", () => txVerfolgenMit(txid));
  block.append(nummer, knopf);
  return block;
}

function txVerfolgenMit(txid) {
  zeigeAnsicht("bloecke");
  $("#a-txid").value = txid;
  verfolgeTx();
  $("#a-txid").scrollIntoView({ block: "center" });
}

// Der QR-Code entsteht in qr.js, hier im Browser -- kein fremder Dienst.
function zeichneQr(ziel, text, fehlerschluessel, meldungsfeld) {
  ziel.textContent = "";
  if (!window.QR) return;              // qr.js fehlt: dann eben ohne Bild
  try {
    const bild = window.QR.svg(text, document);
    bild.setAttribute("role", "img");
    bild.setAttribute("aria-label", t("ez_qr_d"));
    ziel.append(bild);
  } catch (e) {
    // Zu lang fuer diese Groesse. Schweigen waere hier falsch: der Nutzer
    // sucht sonst nach einem Bild, das nie kommt.
    ziel.textContent = "";
    if (fehlerschluessel && meldungsfeld) {
      $(meldungsfeld).textContent = t(fehlerschluessel);
    }
  }
}

/* ── Empfangen ueber Lightning ─────────────────────────────────────────────

   Aus dem Betrieb, 16.09.2026: "Rechnungen bezahlen gibt es ja schon ... solte halt
   nur auch geld rein bekommen". Eine Rechnung fordert nur; bezahlbar ist sie
   erst, wenn auf der Gegenseite eines Kanals Guthaben liegt. Genau das sagt
   der Kasten oben, statt den Nutzer auf eine Zahlung warten zu lassen, die
   nie kommen kann. */

let LETZTES_GUTHABEN = null;

async function rechnungErstellen() {
  const knopf = $("#rq-erstellen");
  const meldung = $("#rq-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    const d = await api("/lightning/rechnung/erstellen", "POST", {
      betrag: Number($("#rq-betrag").value || 0),
      zweck: $("#rq-zweck").value || "",
      gueltig_min: 60,
    });
    $("#rq-rechnung").textContent = d.rechnung;
    $("#rq-gueltig").textContent = t("rq_gueltig",
                                     { zeit: datumZeit(d.laeuft_ab_s * 1000) });
    // In Grossbuchstaben: bech32 ist gegenueber Gross- und Kleinschreibung
    // gleichgueltig, und nur so passt die Rechnung in einen QR-Code.
    zeichneQr($("#rq-qr"), d.rechnung.toUpperCase(), "rq_qr_zu_lang",
              "#rq-meldung");
    $("#rq-ergebnis").classList.remove("hidden");
    $("#rq-storno").classList.remove("hidden");
    ladeRechnungen();
    rechnungBeobachten(d.kennung);
  } catch (e) {
    if (e && e.abgemeldet) return;
    const f = e.detail || {};
    meldung.textContent = f.meldung ? t(f.meldung, f) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function rechnungKopieren() {
  return kopiere($("#rq-rechnung"), $("#rq-meldung"), "rq_kopiert");
}

/* ── Auf DIESE eine Rechnung warten ────────────────────────────────────────

   Bis zum 23.09.2026 war die einzige Antwort auf "ist sie schon bezahlt?"
   ein Nachladen der Liste der letzten zwanzig. Jetzt haengt sich der Server
   an LNDs SubscribeSingleInvoice: er sagt Bescheid, sobald sich an dieser
   einen etwas tut.

   Der Aufruf bleibt dabei stehen -- bis zu 45 Sekunden, das ist der Sinn der
   Sache. Deshalb eine eigene, laengere Frist; mit den ueblichen 25 Sekunden
   braeche der Browser jede Runde mittendrin ab.

   Gewartet wird nur, solange auch jemand hinsieht: eine andere Ansicht, eine
   neue Rechnung oder eine abgelaufene beenden die Runde. */
const FRIST_WARTEN_MS = 60000;
const RQ_ABRISS_MS = 5000;
let RQ_KENNUNG = "";

function rqSagen(text, art) {
  const ziel = $("#rq-warten");
  ziel.textContent = text;
  ziel.className = "note" + (art ? " " + art : "");
}

async function rechnungBeobachten(kennung) {
  RQ_KENNUNG = kennung;
  if (!kennung) return rqSagen("");
  rqSagen(t("rq_wartet"));
  while (RQ_KENNUNG === kennung && ANSICHT === "ln-wallet") {
    let d;
    try {
      d = await api("/lightning/rechnung/abwarten?kennung="
                    + encodeURIComponent(kennung), "GET", null,
                    FRIST_WARTEN_MS);
    } catch (e) {
      if (e && e.abgemeldet) return;
      if (!(e && e.netzfehler)) {
        // Eine richtige Absage -- LND ist zu oder die Rechnung unbekannt.
        // Weiterzufragen brächte nur dieselbe Absage.
        rqSagen("");
        return;
      }
      // Ein Abriss beendet das Warten NICHT. Sonst machte ein einziges
      // Zucken im Netz aus dem lebenden Kasten einen toten, und der Nutzer
      // saehe seine Zahlung nicht, obwohl sie ankam.
      await new Promise((r) => setTimeout(r, RQ_ABRISS_MS));
      continue;
    }
    if (RQ_KENNUNG !== kennung) return;        // inzwischen eine neue
    if (d.zustand === "bezahlt") {
      rqSagen(t("rq_bezahlt", { n: zahl(d.bezahlt_sat || d.betrag_sat) }), "ok");
      $("#rq-storno").classList.add("hidden");
      RQ_KENNUNG = "";
      ladeRechnungen();
      return;
    }
    if (d.zustand === "storniert") {
      rqSagen(t("rq_zurueckgezogen"), "warn");
      $("#rq-storno").classList.add("hidden");
      RQ_KENNUNG = "";
      ladeRechnungen();
      return;
    }
    if (d.laeuft_ab_s && d.laeuft_ab_s < Date.now() / 1000) {
      rqSagen(t("rq_verfallen_hinweis"), "warn");
      $("#rq-storno").classList.add("hidden");
      RQ_KENNUNG = "";
      ladeRechnungen();
      return;
    }
  }
}

/* Eine Rechnung zurueckziehen. Keine PIN: es bewegt kein Geld, es nimmt
   eine Forderung zurueck. Danach kann sie niemand mehr bezahlen -- auch
   nicht, wer den QR-Code noch offen hat. */
async function rechnungZurueckziehen(kennung, knopf, meldung) {
  if (!kennung) return;
  knopf.disabled = true;
  try {
    await api("/lightning/rechnung/stornieren", "POST", { kennung });
  } catch (e) {
    if (e && e.abgemeldet) return;
    const f = (e && e.detail) || {};
    knopf.disabled = false;
    meldung.textContent = f.meldung ? t(f.meldung, f) : t("e_fehler");
    return;
  }
  if (RQ_KENNUNG === kennung) {
    RQ_KENNUNG = "";
    rqSagen(t("rq_zurueckgezogen"), "warn");
    $("#rq-storno").classList.add("hidden");
  }
  ladeRechnungen();
}

async function ladeRechnungen() {
  let d;
  try {
    d = await api("/lightning/rechnungen");
  } catch (e) {
    if (e && e.abgemeldet) return;
    d = { bereit: true, rechnungen: [], weitere: 0, fehler: true };
  }
  zeichneRechnungen(d);
}

function zeichneRechnungen(d) {
  const ziel = $("#rq-liste");
  ziel.textContent = "";
  // Ohne Empfangsraum kann niemand zahlen -- das gehoert VOR die Eingabe.
  const raum = LETZTES_GUTHABEN ? (LETZTES_GUTHABEN.kanal_drueben || 0) : 0;
  const kasten = $("#rq-kein-raum");
  kasten.textContent = raum ? "" : t("rq_kein_raum");
  kasten.classList.toggle("hidden", !!raum);
  if (!d.bereit) return;
  if (d.fehler) {
    ziel.append(hinweis(t("rq_fehler"), "warn"));
    return;
  }
  if (!d.rechnungen.length) {
    ziel.append(hinweis(t("rq_leer"), ""));
    return;
  }
  const jetzt = Date.now() / 1000;
  for (const r of d.rechnungen) {
    const zeile = document.createElement("div");
    zeile.className = "bewegung";
    const kopf = document.createElement("div");
    kopf.className = "bewegung-kopf";
    const betrag = document.createElement("span");
    betrag.className = "bewegung-betrag "
      + (r.zustand === "bezahlt" ? "ein" : "aus");
    betrag.textContent = r.betrag_sat
      ? zahl(r.betrag_sat) + " sat" : t("rq_offener_betrag");
    const stand = document.createElement("span");
    stand.className = "dim small";
    const teile = [];
    let offen = false;
    if (r.zustand === "bezahlt") {
      teile.push(t("rq_zustand_bezahlt"));
      if (r.bezahlt_s) teile.push(datumZeit(r.bezahlt_s * 1000));
      if (r.bezahlt_sat) teile.push(zahl(r.bezahlt_sat) + " sat");
    } else if (r.zustand === "storniert") {
      teile.push(t("rq_zustand_storniert"));
    } else if (r.zustand === "unterwegs") {
      teile.push(t("rq_zustand_unterwegs"));
    } else if (r.laeuft_ab_s && r.laeuft_ab_s < jetzt) {
      teile.push(t("rq_zustand_verfallen"));
    } else {
      offen = true;
      teile.push(t("rq_zustand_offen"));
      if (r.laeuft_ab_s) {
        teile.push(t("rq_gueltig", { zeit: datumZeit(r.laeuft_ab_s * 1000) }));
      }
    }
    if (r.zweck) teile.push(r.zweck);
    stand.textContent = teile.join(" · ");
    kopf.append(betrag, stand);
    // Zurueckziehen gibt es nur, solange es etwas zurueckzuziehen gibt:
    // bei einer bezahlten waere der Knopf eine Luege, bei einer
    // verfallenen ueberfluessig.
    if (offen && r.kennung) {
      const weg = document.createElement("button");
      weg.type = "button";
      weg.className = "btn ghost klein";
      weg.textContent = t("rq_storno");
      weg.addEventListener("click", () => rechnungZurueckziehen(
        r.kennung, weg, $("#rq-meldung")));
      kopf.append(weg);
    }
    zeile.append(kopf);
    ziel.append(zeile);
  }
  if (d.weitere) ziel.append(hinweis(t("rq_weitere", { n: zahl(d.weitere) }), ""));
}

/* ── Die Uebersicht: Kurs, Wallet, Lightning ───────────────────────────────

   Aus dem Betrieb, 16.09.2026: "lass uns mal noch was machen mit der leeren
   uebersichts seite ... da können wir die BTC Kurs anzeigen lassen, Wallet
   guthaben, knoten, so halt wirklich mal ne uebersicht".

   Alles kommt aus Antworten, die ohnehin geholt werden: der Kurs aus dem
   Zwischenspeicher des Servers, Zustand und Guthaben aus der schlanken
   Lightning-Antwort. Kein zusaetzlicher Takt, keine teure Kanal-Abfrage. */

function zeichneKursKurz(d) {
  const wert = $("#d-kurs-wert");
  if (!wert) return;
  wert.textContent = kursText(d.kurs, d.waehrung);
  const wechsel = $("#d-kurs-wechsel");
  if (Number.isFinite(d.wechsel24)) {
    wechsel.textContent = (d.wechsel24 >= 0 ? "+" : "")
      + d.wechsel24.toFixed(2) + " %";
    wechsel.classList.toggle("hoch", d.wechsel24 >= 0);
    wechsel.classList.toggle("runter", d.wechsel24 < 0);
  } else {
    wechsel.textContent = "";
  }
  const zusatz = $("#d-kurs-zusatz");
  zusatz.textContent = "";
  // Ohne Kurs steht der Grund da -- der Abruf laeuft ueber Tor und kann
  // dauern; ein Gedankenstrich allein saehe nach Fehler aus, wo nur
  // gewartet wird. Dieselbe Unterscheidung wie im Kurskasten.
  if (!Number.isFinite(d.kurs)) {
    zusatz.append(hinweis(d.grund === "tor_aus" ? t("kurs_tor_aus")
                          : d.grund ? d.grund : t("d_kurs_wartet"), ""));
    return;
  }
  kennzahl(zusatz, "sat", t("d_kurs_je_euro"),
           zahl(Math.round(100000000 / d.kurs)) + " sat");
  raeumeAuf(zusatz);
}

/* Die Uhr, nach der Bitcoin wirklich geht.

   Auf Anregung aus dem Betrieb, 21.09.2026: "sone arte block zeit in der
   uebersicht .. anzahl der bloecke bis zum naechsten halving .. geschaetztes
   datum .. und wie hoch die revard ist beim naechsten halving".

   Kein eigener Abruf: alles steht in der Antwort, die die Uebersicht ohnehin
   holt. Und wie ueberall hier werden die Zeilen wiederverwendet statt neu
   gebaut -- die Seite laedt alle zehn Sekunden nach. */
function zeichneBlockzeit(h) {
  const ziel = $("#d-blockzeit");
  if (!ziel) return;
  if (!h) {
    textZeile(ziel, "wartet", t("bz_wartet"), "note");
    raeumeAuf(ziel);
    return;
  }

  kennzahl(ziel, "hoehe", t("w_hoehe"), zahl(h.hoehe));
  // Eine Nachkommastelle. Mehr waere bei einem Mittel ueber ein halbes Jahr
  // keine Genauigkeit, sondern Zierrat.
  kennzahl(ziel, "takt", t("bz_takt"), t("bz_takt_wert", {
    min: nachkomma((h.schnitt_sekunden || 600) / 60, 1) }));

  if (h.bloecke_bis == null) {
    // Nach der letzten Halbierung, rund im Jahr 2140. Kostet zwei Zeilen und
    // haelt die Anzeige davon ab, ein Datum zu erfinden.
    textZeile(ziel, "ende", t("bz_ende"), "note");
    raeumeAuf(ziel);
    return;
  }

  kennzahl(ziel, "halbierung", t("bz_halbierung"),
           t("w_in_bloecken", { n: zahl(h.bloecke_bis) }));
  // Monat und Jahr, kein Tagesdatum: ueber anderthalb Jahre hochgerechnet
  // waere ein Tag eine Behauptung, keine Schaetzung.
  kennzahl(ziel, "wann", t("bz_wann"),
           t("bz_etwa", { monat: monatJahr(h.geschaetzt_ts) }));
  kennzahl(ziel, "belohnung", t("bz_belohnung"), t("bz_belohnung_wert", {
    jetzt: belohnungBtc(h.belohnung_sat),
    danach: belohnungBtc(h.belohnung_danach_sat) }));

  // Woher der Takt kommt, gehoert dazu. "etwa April 2028" sieht gemessen
  // aus, auch wenn dahinter nur der Zielabstand des Protokolls steckt.
  textZeile(ziel, "quelle", h.gemessen
    ? t("bz_takt_gemessen", { n: zahl(h.rueckblick) })
    : t("bz_takt_gerechnet"), "note");
  raeumeAuf(ziel);
}

/* Die Belohnung in Bitcoin, mit so vielen Nachkommastellen wie noetig:
   3,125 statt 3,12500000 -- aber ab der neunten Halbierung braucht es
   wirklich alle acht, und dann stehen sie da. */
function belohnungBtc(sat) {
  let stellen = 0;
  while (stellen < 8 && sat % Math.pow(10, 8 - stellen) !== 0) stellen++;
  return nachkomma(sat / 1e8, stellen);
}

function zeichneLightningKurz(d) {
  const ziel = $("#d-ln-kurz");
  const geld = $("#d-wallet");
  if (!ziel || !geld || !d) return;
  const hinweisfeld = $("#d-wallet-hinweis");

  if (!d.eingerichtet) {
    hinweisfeld.textContent = t("d_w_ohne_einrichtung");
    return;
  }
  kennzahl(ziel, "dienst", t("ln_dienst"),
           t("ln_d_" + ((d.dienst || {}).zustand || "unkonfiguriert")));
  kennzahl(ziel, "wallet", t("ln_wallet"),
           t("ln_w_" + ((d.knoten || {}).stand || "aus")));
  kennzahl(ziel, "kette", t("ln_kette"),
           d.kette_bereit ? t("ln_k_bereit")
                          : t("ln_k_sync", { h: zahl(d.hoehe || 0) }));
  raeumeAuf(ziel);

  // Guthaben gibt es nur bei offener Wallet. Nullen waeren hier gelogen:
  // sie saehen aus wie "nichts da", nicht wie "kann ich nicht sehen".
  const g = d.guthaben;
  if (!g) {
    geld.textContent = "";
    hinweisfeld.textContent = t((d.knoten || {}).stand === "gesperrt"
      ? "d_w_gesperrt" : "d_w_keine_wallet");
    return;
  }
  hinweisfeld.textContent = "";
  const unbestaetigt = Math.max(0, (g.kette_gesamt || 0) - (g.kette_bestaetigt || 0));
  kennzahl(geld, "onchain", t("lk_onchain"), zahl(g.kette_bestaetigt || 0) + " sat");
  if (unbestaetigt) {
    kennzahl(geld, "unbestaetigt", t("lk_unterwegs"), zahl(unbestaetigt) + " sat");
  }
  kennzahl(geld, "kanal", t("lk_kanal_hier"), zahl(g.kanal_hier || 0) + " sat");
  kennzahl(geld, "drueben", t("lk_kanal_drueben"), zahl(g.kanal_drueben || 0) + " sat");
  raeumeAuf(geld);
}

function dauerKurz(ms) {
  const s = Math.round(ms / 1000);
  if (s < 60) return s + " s";
  if (s < 3600) return Math.round(s / 60) + " min";
  return (s / 3600).toFixed(1) + " h";
}

function btc(sat) {
  return (sat / 1e8).toFixed(4) + " BTC";
}

function datumZeit(ms) {
  const d = new Date(ms);
  return d.toLocaleString(LANG === "de" ? "de-DE" : "en-GB",
    { dateStyle: "short", timeStyle: "short" });
}

async function ladeEinstellungen() {
  zeigeEinstellungen();
  // ── Zuerst und ALLEIN: die gespeicherte Wahl ──────────────────────────
  //
  // Der teuerste Fehler dieser Woche, gefunden am 02.09.2026 an des Betreibers
  // Bildschirmfoto: alle fuenf Schalter gesetzt, Adressfeld leer -- waehrend
  // gespeichert ipv6=False und eine Adresse standen. Das waren nicht seine
  // Werte, das waren die VORGABEN AUS DEM HTML.
  //
  // Die Ursache stand eine Zeile weiter oben: geladen wurde zuerst /status,
  // und erst danach die Wahl. Faellt /status aus -- vier RPC-Aufrufe mit je
  // fuenfzehn Sekunden Frist, waehrend des Abgleichs keine Seltenheit --,
  // wird keine einzige Zuweisung mehr erreicht. Das catch schluckte es
  // stumm, das Formular zeigte Vorgaben, und der naechste Klick auf
  // "Aenderungen uebernehmen" schrieb genau diese Vorgaben ueber die
  // echte Konfiguration. Also kein Anzeigefehler, sondern Datenverlust.
  //
  // Die Wahl kommt deshalb ZUERST und aus einem eigenen Aufruf. Sie
  // braucht /status nicht.
  let w;
  try {
    w = await api("/knoten/netzwege");
  } catch (e) {
    if (e && e.abgemeldet) return;
    // WEGE_GELADEN wird hier AUSDRUECKLICH NICHT zurueckgesetzt.
    //
    // Der Wert bedeutet "im Formular stehen geladene Werte", nicht "die
    // letzte Abfrage hat geklappt". Am 03.09.2026 hat genau diese
    // Verwechslung die Einstellungen unbenutzbar gemacht: der erste Aufruf
    // gelang, die echten Werte standen da -- ein spaeterer Aufruf lief in
    // sein Zeitlimit, und die Sperre griff trotzdem. Auf dem Bildschirm
    // stand "konnten nicht geladen werden", waehrend die eigene Adresse und
    // das abgewaehlte IPv6 sichtbar daneben standen.
    //
    // Ein misslungenes AUFFRISCHEN macht aus richtigen Werten keine
    // Vorgaben. Gesperrt wird nur, solange noch nie welche ankamen.
    log_fehler("Netzwege holen", e);
    einstellungenFolgen();
    return;
  }
  WEGE_GELADEN = true;

  try {
    $("#e-tor").checked = w.tor;
    $("#e-ipv4").checked = w.ipv4;
    $("#e-ipv6").checked = w.ipv6;
    $("#e-pause").checked = w.tor_pause_beim_abgleich;
    $("#e-ankuendigen").checked = w.adresse_ankuendigen;
    $("#e-adresse").value = w.externe_adresse || "";
    const sicht = document.querySelector(
      'input[name="e-ln-sicht"][value="' + (w.sichtbarkeit || "hybrid") + '"]');
    if (sicht) sicht.checked = true;
    $("#e-adresse").placeholder = t("e_adresse_beispiel");
    WEGE_STAND = wegeAusFeldern();
    einstellungenFolgen();
    // Was aus den Schaltern GERADE folgt. Ein Schalter auf "an", waehrend
    // der Knoten ueber Tor niemanden anruft, waere eine Anzeige, die etwas
    // anderes behauptet als die Wirklichkeit.
    $("#e-ruft-an").textContent =
      t("wege_ruft_an", { liste: (w.ruft_an || []).join(", ") })
      + (w.tor_pausiert ? "  " + t("wege_pausiert") : "");
    // Und direkt am Schalter, was er GERADE bewirkt. Ohne das steht dort ein
    // Haken, aus dem man sich die Folge selbst herleiten muss -- und die
    // Herleitung ging schief: aus dem ausgeschalteten Haken wurde gelesen,
    // Tor sei waehrend des Abgleichs aus. Es ist genau umgekehrt.
    let folge = "wege_pause_aus";
    if (w.tor_pausiert) folge = "wege_pause_laeuft";
    // Ausdruecklich === false: null heisst "gerade nicht feststellbar", und
    // daraus "die Kette steht" zu machen waere eine Behauptung.
    else if (w.im_erstsync === false) folge = "wege_pause_fertig";
    else if (w.tor_pause_beim_abgleich) folge = "wege_pause_wartet";
    $("#e-pause-folge").textContent = w.tor ? t(folge) : "";

    // Ein Name, der nicht mehr aufloest, faellt sonst niemandem auf: der
    // Knoten wirbt weiter mit der Adresse von damals, und nach der naechsten
    // Zwangstrennung gehoert die jemand anderem.
    const haengt = $("#e-name-haengt");
    haengt.textContent = "";
    if (w.name_haengt_seit_s !== null && w.name_haengt_seit_s !== undefined) {
      haengt.append(hinweis(t("e_name_haengt", {
        name: w.externe_adresse,
        dauer: dauerGrob(w.name_haengt_seit_s),
      }), "warn"));
    }
  } catch (e) {
    if (e && e.abgemeldet) return;
    log_fehler("Einstellungen zeichnen", e);
  }

  // ── Danach das Beiwerk, das /status braucht ───────────────────────────
  //
  // Getrennt, weil es die Wahl NICHT tragen darf: die angekuendigten
  // Adressen und die Fassungspruefung sind Zusatz. Faellt /status aus,
  // fehlen sie -- die Schalter stehen trotzdem richtig.
  // Die Fassungspruefung zuerst und fuer sich. Sie braucht keinen Knoten --
  // die Antwort liegt im Arbeitsspeicher des Servers und kommt in
  // Millisekunden. Frueher hing sie als Beipack an /status und ging mit
  // unter, sobald der auf bitcoind wartete.
  try {
    const n = await api("/neuerungen");
    zeichneNeuerungen(n.neuerungen);
  } catch (e) {
    if (e && e.abgemeldet) return;
    log_fehler("Fassungspruefung", e);
    zeichneNeuerungen(null);
  }

  try {
    const d = await api("/status");
    const k = d.knoten;
    const jetzt = k ? (k.adressen || []).map((a) => a.adresse) : [];
    $("#e-adresse-aktuell").textContent = jetzt.length
      ? t("e_adresse_aktuell", { liste: jetzt.join(", ") })
      : t("e_adresse_keine");
  } catch (e) {
    if (e && e.abgemeldet) return;
    log_fehler("Angekuendigte Adressen", e);
    $("#e-adresse-aktuell").textContent = "";
  }
}

// Ein Fehler, den niemand sieht, ist ein Fehler, den niemand findet.
function log_fehler(was, e) {
  console.error("SatoshiCortex: " + was + " fehlgeschlagen", e);
}

function zeichneNeuerungen(alle) {
  const ziel = $("#e-neuerung");
  if (!alle) {
    // Aus dem Betrieb, 03.09.2026: "die aktualisierungs abfrage gibt auch keinen
    // ton mehr von sich -- ob ich den aktuellen stand habe oder ob da
    // nachgeguckt wird". Der Kasten wird nur aus /status gefuellt; faellt
    // der Aufruf aus, blieb hier vorher ein leeres <div> stehen und sagte
    // gar nichts. Was schon dasteht, bleibt jetzt stehen -- und ist nichts
    // da, wird wenigstens gesagt, warum nichts dasteht.
    if (!ziel.firstChild) ziel.append(hinweis(t("e_akt_kein_status"), "warn"));
    return;
  }
  ziel.textContent = "";
  // Feste Reihenfolge, und SatoshiCortex steht oben: es ist die einzige
  // Fassung, die dieser Kasten selbst betrifft.
  //
  // Nachgetragen am 21.09.2026 zusammen mit der Pruefung dahinter. Bis
  // dahin sah die Anwendung nach Neuerungen fuer bitcoind und LND und
  // schwieg ueber sich selbst -- der Knoten lief auf 0.66, 1.0.1 lag seit
  // Stunden bereit, und hier stand nichts davon. Dieselbe Falle wie beim
  // Kurs am selben Tag: die Schnittstelle liefert es, die Oberflaeche
  // zaehlt es nicht auf.
  //
  // Danach Bitcoin, dann Lightning: ohne Kette kein Lightning.
  [["satcortex", "SatoshiCortex"],
   ["bitcoind", "Bitcoin Core"],
   ["lnd", "Lightning (LND)"]].forEach(
    ([schluessel, titel]) => {
      if (alle[schluessel]) {
        ziel.append(neuerungsBlock(alle[schluessel], titel, schluessel));
      }
    });
}

function neuerungsBlock(n, titel, schluessel) {
  const block = document.createElement("div");
  block.style.cssText = "margin-bottom:18px";

  const kopf = document.createElement("h4");
  kopf.style.cssText = "margin:0 0 8px;font-size:14px;letter-spacing:.02em";
  kopf.textContent = titel;
  block.append(kopf);

  // Laeuft der Dienst noch nicht, wird mit der Fassung verglichen, die wir
  // ausliefern. Das gehoert dazugesagt -- sonst liest sich "aktuell" wie eine
  // Aussage ueber einen laufenden Knoten, den es gar nicht gibt.
  // Der Hinweis "verglichen wird mit der ausgelieferten Fassung" gehoert
  // NUR dorthin, wo auch wirklich verglichen wurde. Stand darunter dann
  // "Der Dienst laeuft noch nicht", sagten zwei Kaesten dasselbe.
  const nurAbbild = n.laeuft === false;

  // Zuerst die Tatsachen, dann die Erklaerung. Aus dem Betrieb, 03.09.2026:
  // "entweder weiss er welche version wir haben und welche bereit steht
  // oder er weiss es nicht". Beides steht jetzt immer da -- notfalls als
  // "unbekannt", was auch eine Auskunft ist, aber niemals als Leerstelle.
  const zahlen = document.createElement("p");
  zahlen.className = "dim small";
  zahlen.style.cssText = "margin:0 0 8px;font-variant-numeric:tabular-nums";
  zahlen.textContent = t("e_akt_zahlen", {
    laeuft: n.laufend || t("e_akt_unbekannt"),
    neu: n.neueste || t("e_akt_unbekannt"),
  });
  block.append(zahlen);
  // "Neueste bekannte" heisst: bekannt SEIT WANN. Ohne diese Zeile sah eine
  // Auskunft von gestern aus wie eine von eben -- genau so stand am
  // 23.09.2026 "1.0.3" da, als laengst 1.2.0 veroeffentlicht war.
  if (n.stand) {
    const wann = document.createElement("p");
    wann.className = "dim small";
    wann.style.cssText = "margin:-4px 0 8px";
    wann.textContent = t("e_akt_nachgesehen", { zeit: datumZeit(n.stand * 1000) });
    block.append(wann);
  }

  if (!n.stand && !n.grund) {
    block.append(hinweis(t("e_akt_wartet"), ""));
    return block;
  }
  if (n.grund === "tor_aus") {
    block.append(hinweis(t("e_akt_tor_aus"), ""));
    return block;
  }
  // Warum nichts dasteht. Vorher stand hier in beiden Faellen dauerhaf
  // "Noch nicht nachgesehen" -- eine Anzeige, die behauptet, es sei nichts
  // versucht worden, obwohl es jedes Mal versucht und jedes Mal nichts wurde.
  if (n.grund === "laeuft_nicht") {
    block.append(hinweis(t("e_akt_laeuft_nicht"), ""));
    return block;
  }
  if (n.grund === "fassung_unbekannt") {
    block.append(hinweis(t("e_akt_fassung_unbekannt"), ""));
    return block;
  }
  if (n.grund === "nicht_erreichbar") {
    block.append(hinweis(t("e_akt_nicht_erreichbar"), "warn"));
    return block;
  }
  if (!n.gefunden) {
    block.append(hinweis(t(nurAbbild ? "e_akt_abbild_aktuell" : "e_akt_aktuell"), "ok"));
    return block;
  }
  if (nurAbbild) block.append(hinweis(t("e_akt_nur_abbild"), ""));

  // Drei Arten, drei Saetze. "neuer" gibt es seit dem 23.09.2026, fuer
  // SatoshiCortex selbst: eine Linie, keine gepflegten Zweige. Dort war
  // "Wartungsversion, gefahrlos" eine Behauptung ueber eine Pflege, die es
  // nicht gibt, und "Zweigwechsel, kann das Regelwerk aendern" die Sprache
  // von Bitcoin Core.
  const art = n.gefunden.art;
  const v = { v: n.gefunden.version };
  const satz = art === "zweigwechsel" ? t("e_akt_zweig", v)
    : art === "neuer" ? t("e_akt_neuer", v)
    : t("e_akt_wartung", v);
  block.append(hinweis(satz, art === "zweigwechsel" ? "warn" : ""));
  if (n.gefunden.auch_verfuegbar)
    block.append(hinweis(t("e_akt_auch", { v: n.gefunden.auch_verfuegbar }), ""));

  if (schluessel === "satcortex") {
    block.append(eigeneFassungWie(n));
    return block;
  }

  // Die fertige Zeile zum Uebernehmen -- Abtippen erzeugt Tippfehler, und
  // ein Tippfehler im Abbildnamen sieht aus wie ein kaputtes Update.
  const zeile = document.createElement("pre");
  zeile.className = "dim";
  zeile.style.cssText =
    "margin-top:12px;padding:10px 12px;border-radius:8px;overflow-x:auto;"
    + "background:rgba(10,8,5,.55);border:1px solid var(--border);font-size:13px";
  // Die Zeile, die WIRKLICH geaendert wird: seit 0.30.0 steht die Version
  // in der .env, nicht mehr in der Compose. Und der Tag traegt bei LND ein
  // "v" -- ohne das nennt die Oberflaeche einen Abbildnamen, den es in der
  // Registry nicht gibt, und das Ziehen scheitert mit "manifest unknown".
  zeile.textContent = n.variable + "=" + (n.gefunden.tag || n.gefunden.version);
  block.append(zeile);

  const wie = document.createElement("p");
  wie.className = "dim";
  wie.style.cssText = "font-size:12px;line-height:1.5;margin:8px 0 0";
  wie.textContent = t("e_akt_wie");
  block.append(wie);
  return block;
}

/* Wie man an die neue SatoshiCortex-Fassung kommt -- je nachdem, welchem Tag
   die Installation folgt.

   Aus dem Betrieb, 23.09.2026: "ich will ja immer latest! und nicht gepinnt
   auf eine version!" Der Kasten reichte ihm trotzdem SATCORTEX_VERSION=1.0.3
   zum Abschreiben -- dieselbe Zeile wie fuer Core und LND. Wer latest folgt
   und sie uebernimmt, ist danach festgenagelt und bekommt nie wieder ein
   Update. Darunter stand zudem der Erklaertext fuer Core und LND, samt
   "docker compose build lnd".

   Drei Lagen:
   - "latest": neu ziehen genuegt. KEINE Zeile zum Abschreiben.
   - eine feste Nummer: die Zeile hochsetzen -- oder auf latest umstellen.
   - unbekannt (Compose-Datei von vor dem 23.09.2026): beide Wege nennen,
     aber keine Zeile, die einen davon still festlegt. */
function eigeneFassungWie(n) {
  const teil = document.createElement("div");
  const folgt = n.folgt || "";
  const v = { v: n.gefunden.version, folgt };
  const text = document.createElement("p");
  text.className = "dim";
  text.style.cssText = "font-size:12px;line-height:1.5;margin:8px 0 0";

  if (folgt === "latest") {
    text.textContent = t("e_akt_eigen_latest", v);
    teil.append(text);
    return teil;
  }
  if (folgt) {
    const zeile = document.createElement("pre");
    zeile.className = "dim";
    zeile.style.cssText =
      "margin-top:12px;padding:10px 12px;border-radius:8px;overflow-x:auto;"
      + "background:rgba(10,8,5,.55);border:1px solid var(--border);font-size:13px";
    zeile.textContent = n.variable + "=" + (n.gefunden.tag || n.gefunden.version);
    teil.append(zeile);
    text.textContent = t("e_akt_eigen_fest", v);
    teil.append(text);
    return teil;
  }
  text.textContent = t("e_akt_eigen_unklar", v);
  teil.append(text);
  return teil;
}

// Was beim Laden in den Feldern stand. Ohne diesen Vergleich laesst sich
// "geaendert" nicht von "so war es schon" unterscheiden -- und genau daran
// haengt, ob der Knopf sich meldet.
let WEGE_STAND = null;
// Ob die gespeicherte Wahl ueberhaupt angekommen ist. Steht sie nicht,
// zeigt das Formular Vorgaben -- und Speichern wuerde sie festschreiben.
let WEGE_GELADEN = false;

// ── Wallet-Software im Heimnetz ────────────────────────────────────────────

// Ein Vorschlag fuer das eigene Netz, aus der Adresse dieser Seite. Wer den
// Knoten unter 192.168.178.10 aufruft, meint mit "mein Heimnetz" mit grosser
// Sicherheit 192.168.178.0/24. Abtippen ist die haeufigste Fehlerquelle bei
// so einer Angabe -- und ein Tippfehler bedeutet hier "Sparrow kommt nicht
// durch", ohne dass irgendwo etwas danebenstuende.
function heimnetzVorschlag() {
  const teile = location.hostname.split(".");
  if (teile.length !== 4 || teile.some((t) => !/^\d+$/.test(t))) return "";
  return teile[0] + "." + teile[1] + "." + teile[2] + ".0/24";
}

// Was tatsaechlich freigegeben wuerde -- leer heisst: gar nichts.
//
// Der Vorschlag greift nur, wenn die Seite ueber eine IPv4-Adresse geoeffnet
// wurde. Wer sie ueber einen Namen aufruft (satcortex.fritz.box), bekommt
// keinen -- und dann stand der Schalter auf AN, das Feld war leer, und
// abgeschickt wurde eine leere Freigabe. Also: Schalter an, nichts passiert,
// und die Meldung sagte auch noch "Zugang wieder geschlossen". Gefunden am
// 05.09.2026 im Pruefstand, wo die Seite auf 127.0.0.1 laeuft.
function heimnetzAusFeldern(anId, netzId) {
  if (!$(anId).checked) return "";
  return $(netzId).value.trim() || heimnetzVorschlag();
}

// Ist der Schalter an, aber nichts einzutragen da? Dann fehlt eine Angabe,
// und das gehoert gesagt -- nicht stillschweigend als "aus" verbucht.
function heimnetzFehlt(anId, netzId) {
  return $(anId).checked && !heimnetzAusFeldern(anId, netzId);
}

async function ladeRpcZugang() {
  let d;
  try {
    d = await api("/knoten/rpc-zugang");
  } catch (e) {
    if (e && e.abgemeldet) return;
    log_fehler("RPC-Zugang", e);
    return;
  }
  if (!d.eingerichtet) return;
  RPC_DATEN = d;
  $("#e-rpc-an").checked = !!d.heimnetz;
  $("#e-rpc-netz").value = d.heimnetz || "";
  $("#e-rpc-netz").placeholder = heimnetzVorschlag() || "192.168.178.0/24";
  zeichneRpcZugang();
}

function zeichneRpcZugang() {
  const an = $("#e-rpc-an").checked;
  $("#e-rpc-netz").disabled = !an;
  $("#e-rpc-daten").classList.toggle("hidden", !an || !RPC_DATEN);
  $("#e-rpc-port").classList.toggle("hidden", !an);
  if (!an || !RPC_DATEN) return;
  // Genau die vier Angaben, die Sparrow abfragt -- in der Reihenfolge, in
  // der sie dort stehen.
  $("#e-rpc-feld").textContent =
    t("wsw_feld", { host: location.hostname, port: RPC_DATEN.port,
                    benutzer: RPC_DATEN.benutzer, passwort: RPC_DATEN.passwort });
}

async function rpcFreigabeSpeichern() {
  const knopf = $("#e-rpc-speichern");
  const status = $("#e-rpc-status");
  knopf.disabled = true;
  status.textContent = "";
  if (heimnetzFehlt("#e-rpc-an", "#e-rpc-netz")) {
    status.textContent = t("wsw_netz_fehlt");
    knopf.disabled = false;
    $("#e-rpc-netz").focus();
    return;
  }
  const netz = heimnetzAusFeldern("#e-rpc-an", "#e-rpc-netz");
  try {
    await api("/knoten/netzwege", "POST", {
      tor: $("#e-tor").checked,
      ipv4: $("#e-ipv4").checked,
      ipv6: $("#e-ipv6").checked,
      externe_adresse: $("#e-adresse").value.trim(),
      adresse_ankuendigen: $("#e-ankuendigen").checked,
      tor_pause_beim_abgleich: $("#e-pause").checked,
      sichtbarkeit: lnSichtAusFeldern(),
      rpc_heimnetz: netz,
    });
    $("#e-rpc-netz").value = netz;
    status.textContent = netz ? t("wsw_gespeichert") : t("wsw_zu");
    await ladeRpcZugang();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail;
    // Pydantic meldet eine ungueltige Angabe als Liste -- der Grund steht
    // darin und gehoert dem Menschen gesagt, nicht verschluckt.
    status.textContent = Array.isArray(d) && d[0] && d[0].msg
      ? d[0].msg.replace(/^Value error, /, "")
      : ((d && d.meldung) ? t(d.meldung) : t("err_net"));
  } finally {
    knopf.disabled = false;
  }
}

let RPC_DATEN = null;

function lnSichtAusFeldern() {
  const gewaehlt = document.querySelector('input[name="e-ln-sicht"]:checked');
  return gewaehlt ? gewaehlt.value : "tor";
}

function wegeAusFeldern() {
  return JSON.stringify([
    $("#e-tor").checked, $("#e-pause").checked, $("#e-ipv4").checked,
    $("#e-ipv6").checked, $("#e-ankuendigen").checked,
    $("#e-adresse").value.trim(), lnSichtAusFeldern(),
  ]);
}

function einstellungenFolgen() {
  // Dieselben Regeln wie im Assistenten, nur auf den anderen Feldern: das
  // Eingabefeld sperren statt verstecken (der Name bleibt sichtbar, dami
  // klar ist, was beim Zurueckschalten wieder gilt), die Pause an Tor
  // binden, und ohne jeden Weg gar nicht erst speichern lassen.
  // Die Wahl oben ist das Grobe, die Haekchen sind die Feinheit darunter --
  // und in "nur ueber Tor" gibt es nichts fein einzustellen. Statt die
  // Schalter stillschweigend zu uebergehen (dann waere die Wahl eine
  // Behauptung ohne Folge), werden sie gesperrt und die Folge steht daneben.
  const sicht = lnSichtAusFeldern();
  const nurTor = sicht === "tor";
  const still = sicht === "still";
  // Nur SPERREN, nicht abhaken. Beim ersten Anlauf wurden die Haekchen
  // geloescht -- und nach einem Ausflug nach "nur ueber Tor" und zurueck
  // stand der Knoten ohne IPv4 da, ohne dass jemand das gewaehlt haette.
  // Das Haekchen ist die Voreinstellung des Nutzers; dass sie gerade nicht
  // gilt, sagt die Zeile darunter.
  for (const id of ["#e-ipv4", "#e-ipv6"]) $(id).disabled = nurTor;
  $("#e-ankuendigen").disabled = nurTor || still;
  const folge = $("#e-sicht-folge");
  folge.textContent = nurTor ? t("lnsicht_folge_tor")
                    : still ? t("lnsicht_folge_still") : "";
  folge.classList.toggle("hidden", !folge.textContent);

  const kein = !($("#e-tor").checked || $("#e-ipv4").checked
                 || $("#e-ipv6").checked);
  $("#e-adresse").disabled = !$("#e-ankuendigen").checked;
  $("#e-pause").disabled = !$("#e-tor").checked;
  $("#e-adresse-speichern").disabled = kein || !WEGE_GELADEN;
  $("#e-adresse-meldung").textContent =
    !WEGE_GELADEN ? t("e_nicht_geladen") : (kein ? t("kein_weg_ins_netz") : "");
  const offen = WEGE_STAND !== null && wegeAusFeldern() !== WEGE_STAND;
  $("#e-ungespeichert").classList.toggle("hidden", !offen);
  $("#e-adresse-speichern").classList.toggle("offen", offen);
  // Die Folgenzeile beschreibt, was GERADE laeuft -- nicht, was der Schalter
  // gleich bewirken wird. Steht sie neben einem umgelegten, noch nicht
  // uebernommenen Schalter, widerspricht sie ihm sichtbar. Dann lieber weg:
  // was ansteht, sagt der Kasten darunter.
  $("#e-pause-folge").classList.toggle("hidden", offen);
}

async function pruefeErreichbarkeit() {
  const knopf = $("#e-pruefen");
  const lauft = $("#e-pruefen-lauft");
  const ziel = $("#e-pruefen-ergebnis");
  knopf.disabled = true;
  ziel.textContent = "";
  lauft.textContent = t("pr_laeuft");
  try {
    zeichneErreichbarkeit(await api("/knoten/erreichbarkeit", "POST",
                                    undefined, FRIST_MESSUNG_MS));
  } catch (e) {
    if (e && e.abgemeldet) return;
    ziel.append(hinweis(t("pr_fehler"), "warn"));
  } finally {
    lauft.textContent = "";
    knopf.disabled = false;
  }
}

// Drei Ausgaenge, nicht zwei: erreichbar, nachweislich nicht erreichbar, und
// nicht gemessen. Den dritten mit dem zweiten zu verwechseln hiesse, jemanden
// in seinen Router zu schicken, um dort etwas zu reparieren, das nie kapu
// war.
function zeichneErreichbarkeit(d) {
  const ziel = $("#e-pruefen-ergebnis");
  ziel.textContent = "";
  if (!d.eingerichtet) return;
  // Zuerst, was NICHT gemessen wurde. Steht das hinter drei gruenen
  // IPv4-Zeilen, liest es niemand mehr -- und genau dort fehlte es: die
  // Pruefung sah vollstaendig aus und liess Tor stillschweigend aus.
  // Die Pause ist eine Einstellung, die tut was sie soll: keine Warnfarbe.
  // Eine fehlende Onion bei laufendem Tor ist eine: die gehoert angesehen.
  if (d.tor_hinweis) {
    ziel.append(hinweis(t("pr_" + d.tor_hinweis),
                        d.tor_hinweis === "keine_onion" ? "warn" : ""));
  }
  if (d.grund === "keine_adresse" || d.grund === "tor_aus"
      || d.grund === "nicht_aufloesbar") {
    ziel.append(hinweis(t("pr_" + d.grund), d.grund === "tor_aus" ? "" : "warn"));
    return;
  }
  for (const a of d.adressen || []) {
    let schluessel = "pr_ja";
    let art = "ok";
    if (a.geprueft === false) {
      // Nicht gemessen ist weder gut noch schlecht -- also auch keine Farbe,
      // die eines von beidem behauptet.
      art = "";
      // Drei Lagen, drei Saetze: der Port stand und es kam nur nichts
      // zurueck; eine .onion, bei der Wiederholen aktiv SCHADET; alles
      // andere.
      if (a.grund === "keine_antwort") schluessel = "pr_keine_antwort";
      else if (a.netz === "onion") schluessel = "pr_unklar_onion";
      else schluessel = "pr_unklar";
    } else if (a.erreichbar === false) {
      schluessel = "pr_" + (a.grund || "abgelehnt");
      // Bei einer .onion heisst "abgelehnt" etwas anderes als im Clearnet:
      // Tor HAT den Dienst gefunden, dahinter nahm niemand an. Mit einer
      // Portfreigabe hat das nichts zu tun -- genau das stuende sonst da.
      if (a.netz === "onion" && schluessel === "pr_abgelehnt") {
        schluessel = "pr_abgelehnt_onion";
      }
      art = "bad";
    } else if (!a.kennung) {
      // Lightning und Wachturm sprechen kein Bitcoin -- es gibt keinen
      // Handschlag und damit keine Kennung, die sich melden koennte.
      schluessel = "pr_ja_offen";
    }
    // Der Weg gehoert dazu: "erreichbar" ueber IPv4 heisst etwas anderes als
    // ueber die .onion, und wer beides hat, will wissen welcher ging. Und
    // welcher Dienst: Knoten, Lightning und Wachturm haben je eine eigene.
    const wegname = { onion: "Tor", ipv4: "IPv4", ipv6: "IPv6" }[a.netz] || "";
    const dienst = a.dienst && a.dienst !== "bitcoin"
      ? t("pr_dienst_" + a.dienst) : "";
    const kopf = [wegname, dienst].filter(Boolean).join(" · ");
    ziel.append(hinweis((kopf ? kopf + " · " : "") + t(schluessel, {
      adresse: a.adresse, port: a.port,
      kennung: a.kennung || "", grund: a.einzelheit || "",
    }), art));
  }
}

async function speichereAdresse() {
  const knopf = $("#e-adresse-speichern");
  const meldung = $("#e-adresse-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/knoten/netzwege", "POST", {
      tor: $("#e-tor").checked,
      ipv4: $("#e-ipv4").checked,
      ipv6: $("#e-ipv6").checked,
      externe_adresse: $("#e-adresse").value.trim(),
      adresse_ankuendigen: $("#e-ankuendigen").checked,
      tor_pause_beim_abgleich: $("#e-pause").checked,
      sichtbarkeit: lnSichtAusFeldern(),
    });
    meldung.textContent = t("e_gespeichert");
    await ladeEinstellungen();       // setzt WEGE_STAND neu
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail;
    meldung.textContent = (d && d.meldung) ? t(d.meldung) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Senden ───────────────────────────────────────────────────────────────

   Die Bedingung des Betreibers vom 30.08.2026: "ich werde nix dahin ueberweisen solange
   ich es nicht zurueck schicken kann". Eine Wallet, aus der man nicht wieder
   herauskommt, ist keine Wallet.

   ZWEI SCHRITTE, und der erste ist nicht ueberspringbar: erst "was kostet
   das", dann "jetzt senden". Das ist nicht Zierrat, sondern der Grund, warum
   der zweite Knopf ueberhaupt gesperrt anfaengt -- die Schaetzung laeuft an
   der wirklichen Wallet und prueft dabei die Adresse gleich mit.

   Und sobald sich danach IRGENDEIN Feld aendert, faellt die Freigabe wieder
   weg. Sonst schaetzte man das eine und schickte das andere. */

let SD_FREI = false;

function sendenFelder() {
  return [$("#sd-adresse"), $("#sd-betrag"), $("#sd-alles"), $("#sd-pin"),
          ...$$('input[name="sd-tempo"]')];
}

function sendenTempo() {
  const g = document.querySelector('input[name="sd-tempo"]:checked');
  return g ? g.value : "normal";
}

/* Die Freigabe zuruecknehmen. Wird an JEDER Aenderung aufgerufen. */
function sendenSperren() {
  SD_FREI = false;
  $("#sd-senden").disabled = true;
  $("#sd-kosten").classList.add("hidden");
  $("#sd-fertig").classList.add("hidden");
}

function sendenLeib() {
  const alles = $("#sd-alles").checked;
  return {
    adresse: $("#sd-adresse").value.trim(),
    // Bei "alles" KEIN Betrag -- der Server weist beides zusammen ab, und
    // das zu Recht: was von zweien gaelte, waere geraten.
    betrag: alles ? 0 : Number($("#sd-betrag").value || 0),
    alles,
    tempo: sendenTempo(),
  };
}

async function sendenSchaetzen() {
  const knopf = $("#sd-schaetzen");
  const meldung = $("#sd-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  sendenSperren();
  try {
    const d = await api("/lightning/senden/schaetzen", "POST", sendenLeib());
    const kasten = $("#sd-kosten");
    kasten.textContent = d.alles
      ? t("sd_kosten_alles", { satz: d.satz_sat_vb })
      : t("sd_kosten", { gebuehr: zahl(d.gebuehr_sat),
                         satz: d.satz_sat_vb });
    kasten.classList.remove("hidden");
    // ERST JETZT. Der Knopf, der Geld aus der Hand gibt, geht nur nach einer
    // Schaetzung auf -- und die hat die Adresse mitgeprueft.
    SD_FREI = true;
    $("#sd-senden").disabled = false;
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function sendenAusloesen() {
  if (!SD_FREI) {
    $("#sd-meldung").textContent = t("sd_erst_schaetzen");
    return;
  }
  const knopf = $("#sd-senden");
  const meldung = $("#sd-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  // Ob der Knopf danach wieder darf. Bei einem Abbruch OHNE Bescheid nicht:
  // die Ueberweisung kann unterwegs sein, und ein zweiter Versuch waere eine
  // zweite Transaktion. On-Chain schuetzt kein Protokoll davor.
  let wiederFrei = true;
  try {
    const d = await api("/lightning/senden", "POST",
                        { ...sendenLeib(), ...mitPin("#sd-pin") },
                        FRIST_GELD_MS);
    $("#sd-txid").textContent = d.txid || "";
    $("#sd-fertig").classList.remove("hidden");
    $("#sd-kosten").classList.add("hidden");
    // Die Felder leeren, damit niemand zweimal auf denselben Knopf drueckt
    // und dabei glaubt, der erste habe nicht gezaehlt.
    $("#sd-adresse").value = "";
    $("#sd-betrag").value = "";
    $("#sd-alles").checked = false;
    $("#sd-pin").value = "";
    SD_FREI = false;
    ladeLightningKanaele();          // das Guthaben stimmt jetzt nicht mehr
    ladeBewegungen();                // und die neue Ausgabe gehoert in die Liste
  } catch (e) {
    wiederFrei = geldfehler(e, meldung, "sendung_unklar");
    // Nach einer Abfuhr wieder zu -- was abgelehnt wurde, ist nicht
    // geschaetzt. Nach einem Abbruch erst recht.
    sendenSperren();
  } finally {
    if (wiederFrei) knopf.disabled = false;
  }
}

/* ── Die PIN: das Schloss vor Handgriffen mit Folgen ──────────────────────

   Aus dem Betrieb, 08.09.2026: "eine art: PIN. fuer Zahlungen ansich also knoten
   oeffnen oder schliessen geld transferieren".

   Sie schuetzt gegen etwas anderes als der Entsperrweg: der entscheidet, was
   jemand mit der PLATTE anfangen kann, die PIN steht gegen eine uebernommene
   SITZUNG in dieser Oberflaeche. Deshalb sitzt sie in den Einstellungen bei
   "wer darf diesen Knoten benutzen" und nicht bei der Wallet.

   Ob sie eingerichtet ist, weiss nur der Server -- die Oberflaeche fragt und
   raet nicht. Ohne eingerichtete PIN erscheint nirgends eine Abfrage: wer
   keine will, soll nicht ploetzlich vor einem Feld stehen, das es fuer ihn
   gar nicht gibt. */

let PIN_DA = false;

async function pinLaden() {
  let d;
  try {
    d = await api("/freigabe");
  } catch (e) {
    if (e && e.abgemeldet) return;
    return;
  }
  PIN_DA = !!d.eingerichtet;
  const stand = $("#pin-stand");
  if (stand) {
    // Die Sperre zuerst: sie erklaert ein Feld, das nichts annimmt. Ohne
    // die Zahl weiss niemand, ob es an ihm liegt.
    stand.textContent = d.wartet_noch > 0
      ? t("pin_stand_gesperrt", { sekunden: d.wartet_noch })
      : t(PIN_DA ? "pin_stand_an" : "pin_stand_aus");
    stand.className = "note" + (d.wartet_noch > 0 ? " warn" : "");
  }
  const ein = $("#pin-einrichten-block");
  const aendern = $("#pin-aendern-block");
  if (ein) ein.classList.toggle("hidden", PIN_DA);
  if (aendern) aendern.classList.toggle("hidden", !PIN_DA);
  // Und dort, wo sie tatsaechlich gebraucht wird.
  for (const id of ["#tg-pin-zeile", "#sd-pin-zeile", "#zl-pin-zeile",
                    "#ko-pin-zeile", "#us-pin-zeile", "#ks-pin-zeile"]) {
    const zeile = $(id);
    if (zeile) zeile.classList.toggle("hidden", !PIN_DA);
  }
}

/* Ein Aufruf, der eine PIN braucht -- oder eben keine.

   Er gibt ein Objekt zurueck, das man in den Anfragekoerper streut. Ohne
   eingerichtete PIN ist es leer, und der Server fragt dann auch nicht. */
/* ── Eine Lightning-Rechnung bezahlen ──────────────────────────────────────

   Dieselbe Reihenfolge wie beim On-Chain-Senden, und aus demselben Grund:
   erst ansehen, dann freigeben. Der Knopf, der zahlt, geht NUR nach dem
   Lesen auf -- und beim Lesen hat LND die Rechnung schon aufgeschluesselt.
   Wer eine Zeichenkette bezahlt, die er nie gesehen hat, zahlt blind. */

let ZL_FREI = false;
let ZL_GELESEN = null;

function zahlenSperren() {
  ZL_FREI = false;
  ZL_GELESEN = null;
  $("#zl-zahlen").disabled = true;
  $("#zl-vorschau").classList.add("hidden");
  $("#zl-fertig").classList.add("hidden");
}

function zahlenLeib() {
  return {
    rechnung: $("#zl-rechnung").value.trim(),
    betrag: Number($("#zl-betrag").value || 0),
  };
}

async function rechnungLesen() {
  const knopf = $("#zl-lesen");
  const meldung = $("#zl-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  zahlenSperren();
  try {
    const d = await api("/lightning/rechnung/lesen", "POST", zahlenLeib());
    ZL_GELESEN = d;
    // Eine Rechnung ohne Betrag braucht einen -- sonst geht es gar nicht.
    $("#zl-betrag-zeile").classList.toggle("hidden", !d.offener_betrag);

    const kasten = $("#zl-vorschau");
    kasten.textContent = "";
    const betrag = d.offener_betrag ? Number($("#zl-betrag").value || 0)
                                    : d.betrag;
    kasten.append(zeile(t("zl_v_betrag"), betrag ? sats(betrag) : "—"));
    kasten.append(zeile(t("zl_v_gebuehr"), t("zl_v_hoechstens",
                                             { n: zahl(d.gebuehrengrenze) })));
    if (d.zweck) kasten.append(zeile(t("zl_v_zweck"), d.zweck));
    kasten.append(zeile(t("zl_v_ziel"), (d.ziel || "").slice(0, 20) + "…"));
    if (d.abgelaufen) kasten.append(hinweis(t("zl_abgelaufen"), "bad"));
    kasten.classList.remove("hidden");

    // ERST JETZT, und nur wenn ein Betrag feststeht.
    if (betrag > 0 && !d.abgelaufen) {
      ZL_FREI = true;
      $("#zl-zahlen").disabled = false;
    } else if (!betrag) {
      meldung.textContent = t("zl_betrag_fehlt");
    }
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function rechnungZahlen() {
  if (!ZL_FREI) {
    $("#zl-meldung").textContent = t("zl_erst_lesen");
    return;
  }
  const knopf = $("#zl-zahlen");
  const meldung = $("#zl-meldung");
  knopf.disabled = true;
  // Eine Zahlung kann bis zu einer Minute unterwegs sein. Ohne ein Wort
  // dazu sieht das aus, als haette der Knopf nichts getan -- und der
  // naechste Griff waere, ihn noch einmal zu druecken.
  meldung.textContent = t("zl_unterwegs");
  let wiederFrei = true;
  try {
    const d = await api("/lightning/rechnung/zahlen", "POST",
                        { ...zahlenLeib(), ...mitPin("#zl-pin") },
                        FRIST_GELD_MS);
    const fertig = $("#zl-fertig");
    fertig.textContent = t("zl_bezahlt", { betrag: zahl(d.betrag),
                                           gebuehr: zahl(d.gebuehr) });
    fertig.classList.remove("hidden");
    $("#zl-vorschau").classList.add("hidden");
    $("#zl-rechnung").value = "";
    $("#zl-betrag").value = "";
    $("#zl-pin").value = "";
    meldung.textContent = "";
    zahlenSperren();
    ladeLightningKanaele();
  } catch (e) {
    wiederFrei = geldfehler(e, meldung, "zahlung_unklar");
    // Ohne Bescheid auch die Rechnung sperren: wer sie erneut einliest,
    // sieht in der Vorschau, ob sie inzwischen bezahlt ist.
    if (!wiederFrei) zahlenSperren();
  } finally {
    if (wiederFrei) knopf.disabled = false;
  }
}

/* Die Gegenstelle ansehen, bevor ein Kanal steht.

   Aus dem EIGENEN Graphen -- keine fremde Seite, kein Konto, und niemand
   erfaehrt, mit wem wir einen Kanal erwaegen.

   Bewusst KEINE Note und kein Vertrauenswert: das waere erfundene
   Genauigkeit. Es stehen Tatsachen da, und die Befunde einzeln daneben --
   wer einen davon hinnehmen will, soll wissen, welchen. */
async function gegenstelleAnsehen() {
  const knopf = $("#ko-ansehen");
  const kasten = $("#ko-befund");
  knopf.disabled = true;
  $("#ko-meldung").textContent = "";
  try {
    const d = await api("/lightning/gegenstelle/ansehen", "POST",
                        { gegenstelle: $("#ko-gegenstelle").value.trim() });
    kasten.textContent = "";
    if (!d.bekannt) {
      kasten.append(hinweis(t("ko_b_unbekannt"), "warn"));
      kasten.classList.remove("hidden");
      return;
    }
    if (d.alias) kasten.append(zeile(t("ko_b_name"), d.alias));
    kasten.append(zeile(t("ko_b_kanaele"), zahl(d.kanaele)));
    kasten.append(zeile(t("ko_b_kapazitaet"), sats(d.kapazitaet)));
    if (d.still_seit_tagen !== null && d.still_seit_tagen !== undefined) {
      kasten.append(zeile(t("ko_b_gemeldet"),
                          t("ko_b_vor_tagen", { n: d.still_seit_tagen })));
    }
    // Die Befunde. Der erste ist der teuerste Fall von allen.
    const befunde = [
      [d.still, "ko_b_still", "bad"],
      [d.ohne_adresse, "ko_b_ohne_adresse", "bad"],
      [d.wenig_verbunden, "ko_b_wenig", "warn"],
      [d.nur_tor, "ko_b_nur_tor", ""],
    ];
    let etwas = false;
    for (const [gilt, schluessel, art] of befunde) {
      if (!gilt) continue;
      etwas = true;
      kasten.append(hinweis(t(schluessel), art));
    }
    if (!etwas) kasten.append(hinweis(t("ko_b_unauffaellig"), "ok"));
    kasten.classList.remove("hidden");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    $("#ko-meldung").textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Wachtuerme ────────────────────────────────────────────────────────────

   Der Befund vom 12.09.2026: wtclient.active=true stand in der
   Konfiguration, eingetragen war kein einziger Turm. Deshalb steht die Zahl
   jetzt HIER und nicht in einer Datei, die niemand aufmacht. */
/* ── Was durch den Knoten ging -- und was nicht ────────────────────────────

   Die Fehlschlaege stehen ZUERST und getrennt. Eine Liste, in der Gelungenes
   und Gescheitertes durcheinanderlaufen, beantwortet die Frage nicht, die man
   hier hat: welcher Kanal macht Aerger?

   Und "INSUFFICIENT_BALANCE" heisst nicht "es ging etwas schief", sondern
   "dieser Kanal ist leer und gehoert nachgefuellt". Das uebersetzen wir,
   statt LNDs Grossbuchstaben auszustellen. */
const HTLC_GRUENDE_BEKANNT = ["INSUFFICIENT_BALANCE", "HTLC_EXCEEDS_MAX",
                              "FEE_INSUFFICIENT", "EXPIRY_TOO_SOON",
                              "INVALID_KEYSEND", "CHANNEL_DISABLED"];

function htlcGrundText(grund) {
  return HTLC_GRUENDE_BEKANNT.includes(grund)
    ? t("ht_g_" + grund.toLowerCase()) : grund;
}

async function durchgangLaden() {
  const kasten = $("#ln-durchgang");
  if (!kasten) return;
  let d;
  try {
    d = await api("/lightning/htlc");
  } catch (e) {
    return;
  }
  const ereignisse = d.ereignisse || [];
  const gruende = d.gruende || [];
  kasten.classList.toggle("hidden", !ereignisse.length && !gruende.length);

  const oben = $("#ht-gruende");
  oben.textContent = "";
  if (gruende.length) {
    oben.append(hinweis(t("ht_gruende_titel"), "warn"));
    for (const g of gruende) {
      const kanal = g.raus_kanal || g.rein_kanal || "—";
      oben.append(zeile(htlcGrundText(g.grund),
                        t("ht_mal", { n: g.anzahl, kanal })));
    }
  }

  const liste = $("#ht-liste");
  liste.textContent = "";
  if (!ereignisse.length) {
    liste.append(hinweis(t("ht_leer"), ""));
    return;
  }
  for (const e of ereignisse.slice(0, 25)) {
    const wert = e.art === "link_fehl"
      ? htlcGrundText(e.grund)
      : sats(e.betrag) + (e.gebuehr ? " · " + t("ht_gebuehr",
                                                { n: zahl(e.gebuehr) }) : "");
    liste.append(zeile(t("ht_a_" + e.art), wert,
                       e.art === "erledigt" ? "ok"
                       : e.art === "link_fehl" ? "bad" : ""));
  }
}

async function wachtuermeLaden() {
  const kasten = $("#wt-stand");
  if (!kasten) return;
  let d;
  try {
    d = await api("/lightning/wachtuerme");
  } catch (e) {
    return;
  }
  kasten.textContent = "";
  zeichneEigenenTurm(d.eigener);
  // Ausgetragene Tuerme fuehrt LND weiter, solange sie Sitzungen hatten --
  // in der Liste haben sie nichts mehr zu suchen, und als Schutz zaehlen sie
  // schon im Backend nicht.
  const tuerme = (d.tuerme || []).filter((turm) => turm.aktiv !== false);
  if (!tuerme.length) {
    // Das ist die wichtige Meldung, nicht die Liste.
    kasten.append(hinweis(t("wt_keiner"), "warn"));
    return;
  }
  // Erst das Urteil, dann die Einzelheiten. Eingetragen heisst nicht
  // bewacht -- bis zum 14.09.2026 stand hier gruen "eingetragen" und bei
  // jedem Turm "0 Sitzungen", egal wie es wirklich stand.
  const ungedeckt = d.ungedeckt || [];
  if (ungedeckt.length) {
    const arten = ungedeckt.map(wtArt).join(", ");
    kasten.append(hinweis(
      t(d.kanaele ? "wt_ungedeckt" : "wt_ungedeckt_vorab", { arten }),
      d.kanaele ? "bad" : "warn"));
  } else {
    kasten.append(hinweis(t(d.kanaele ? "wt_gedeckt" : "wt_gedeckt_vorab"), "ok"));
  }
  for (const turm of tuerme) {
    const teile = Object.entries(turm.arten || {})
      .filter(([, a]) => a.sitzungen > 0)
      .map(([art, a]) => t("wt_turm_art", { art: wtArt(art), n: a.bestaetigt }));
    // Ohne Sitzung ist ein Turm nur dann ein Problem, wenn auch sonst
    // keiner eine haelt. LND handelt je Kanalart mit genau einem Turm --
    // die anderen warten in Reserve.
    //
    // Der EIGENE Turm ist ein Fall fuer sich: er kann Sitzungen halten und
    // schuetzt trotzdem nicht, weil er mit dem Knoten zusammen ausfaellt.
    // Am 17.09.2026 stand er hier wie jeder andere in der Liste, und weil
    // er alle Kanalarten bediente, meldete der Kasten darueber gruen
    // "Bereit". Zaehlen tut er seit dem Befund nicht mehr (ungedeckte_arten)
    // -- benannt werden muss er trotzdem, sonst sucht man den Grund fuer
    // die gelbe Meldung bei den anderen.
    const wert = turm.eigen
      ? t(teile.length ? "wt_turm_eigen_sitzung" : "wt_turm_eigen")
      : (teile.length ? teile.join(" · ")
         : t(ungedeckt.length ? "wt_turm_ohne" : "wt_turm_reserve"));
    const reihe = zeile(turm.adressen[0] || turm.kennung.slice(0, 16), wert);
    // Der eigene Turm braucht keine Messung -- er ist offensichtlich da, und
    // genau das ist ja das Problem an ihm.
    if (!turm.eigen) reihe.append(turmPruefenKnopf(turm.kennung, reihe));
    reihe.append(turmEntfernenKnopf(turm.kennung));
    kasten.append(reihe);
  }
  const z = d.zaehler;
  if (z) {
    kasten.append(hinweis(t("wt_zaehler",
      { bestaetigt: z.bestaetigt, ausstehend: z.ausstehend }), ""));
    if (z.abgewiesen) {
      kasten.append(hinweis(t("wt_zaehler_abgewiesen", { n: z.abgewiesen }), "bad"));
    }
  }
}

// Antwortet dieser Turm ueberhaupt noch?
//
// DER BEFUND VOM 17.09.2026: in der Liste standen vier Tuerme, bei allen
// "keine Sitzung" -- und zwei davon waren tot, ihre .onion gab es nicht mehr.
// Die Oberflaeche konnte den Unterschied nicht zeigen, weil sie ihn nie
// gemessen hat. Gemessen wird auf Klick und nicht beim Zeichnen: ueber Tor
// dauert eine Messung bis zu einer Minute, und vier Tuerme beim Oeffnen der
// Seite hiessen vier Minuten Stillstand.
function turmPruefenKnopf(kennung, reihe) {
  const knopf = document.createElement("button");
  knopf.type = "button";
  knopf.className = "btn ghost klein";
  knopf.textContent = t("wt_pruefen");
  const meldung = document.createElement("span");
  meldung.className = "dim turm-befund";
  knopf.addEventListener("click", async () => {
    knopf.disabled = true;
    meldung.className = "dim turm-befund";
    meldung.textContent = t("wt_pruefen_laeuft");
    try {
      // FRIST_MESSUNG_MS, nicht die Vorgabe: eine Messung ueber Tor
      // dauert je Adresse bis zu einer halben Minute. Mit der
      // 25-Sekunden-Vorgabe brach der Browser ab, bevor der Server
      // antworten konnte -- am 18.09.2026 an dem Knoten im Betrieb so
      // aufgeschlagen, beim allerersten Klick auf diesen Knopf.
      const d = await api("/lightning/wachtuerme/pruefen", "POST",
                          { kennung }, FRIST_MESSUNG_MS);
      // Der erste Befund, der etwas aussagt, gewinnt: "erreichbar" schlaegt
      // alles, danach "abgelehnt" (der Rechner ist da), zuletzt der Fall,
      // in dem gar nicht gemessen werden konnte.
      const abgelehnt = (d.adressen || []).some((a) => a.grund === "abgelehnt");
      const stumm = (d.adressen || []).find((a) => !a.geprueft);
      if (d.erreichbar) {
        meldung.className = "turm-befund da";
        meldung.textContent = t("wt_pruef_da");
      } else if (abgelehnt) {
        meldung.className = "turm-befund zu";
        meldung.textContent = t("wt_pruef_zu");
      } else {
        meldung.className = "turm-befund tot";
        meldung.textContent = t("wt_pruef_tot", {
          grund: (stumm && stumm.einzelheit) || t("wt_turm_ohne") });
      }
    } catch (e) {
      if (e && e.abgemeldet) return;
      // Drei verschiedene Faelle, und sie bedeuten Verschiedenes. Der
      // Sammelgriff auf e_fehler ("Konnte nicht gespeichert werden") war
      // hier schlicht falsch -- gespeichert wird bei einer Messung nichts.
      const d = e.detail || {};
      meldung.className = "turm-befund tot";
      meldung.textContent = t("wt_pruef_fehler", {
        grund: d.meldung ? t(d.meldung, d)
             : e.zeitlimit ? t("wt_pruef_zu_lang")
             : e.netzfehler ? t("wt_pruef_keine_antwort")
             : (e.message || t("e_fehler")) });
    } finally {
      knopf.disabled = false;
    }
  });
  reihe.append(meldung);
  return knopf;
}

// Austragen in zwei Schritten. Ein Turm kann der einzige gewesen sein, der
// die Kanaele bewacht -- das soll nicht an einem verrutschten Klick haengen.
function turmEntfernenKnopf(kennung) {
  const knopf = document.createElement("button");
  knopf.type = "button";
  knopf.className = "btn ghost klein";
  knopf.textContent = t("wt_entfernen");
  let scharf = null;
  knopf.addEventListener("click", async () => {
    const meldung = $("#wt-meldung");
    if (!scharf) {
      knopf.textContent = t("wt_entfernen_sicher");
      scharf = setTimeout(() => {
        scharf = null;
        knopf.textContent = t("wt_entfernen");
      }, 4000);
      return;
    }
    clearTimeout(scharf);
    scharf = null;
    knopf.disabled = true;
    meldung.textContent = "";
    try {
      await api("/lightning/wachtuerme/entfernen", "POST", { kennung });
      meldung.textContent = t("wt_entfernt");
      await wachtuermeLaden();
    } catch (e) {
      if (e && e.abgemeldet) return;
      const d = e.detail || {};
      meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
      knopf.disabled = false;
      knopf.textContent = t("wt_entfernen");
    }
  });
  return knopf;
}

function wtArt(art) {
  return t("wt_art_" + String(art).toLowerCase());
}

/* Die Adresse des EIGENEN Turms -- die andere Richtung.

   Unser Knoten bewacht fremde Kanaele seit Tag eins, ohne dass jemand etwas
   tun musste. Nur stand seine Adresse nirgends, und ohne die kann ihn
   niemand eintragen. */
function zeichneEigenenTurm(d) {
  const kasten = $("#wt-eigener");
  if (!kasten) return;
  const turm = d || {};
  const uri = (turm.uris || [])[0] || "";
  // Der Kasten haengt am TURM, nicht an seiner Adresse. Bis zum 19.09.2026
  // haengte er an der Adresse -- und verschwand damit wortlos in genau der
  // Lage, in der jemand ihn sucht: Turm laeuft, kuendigt aber nichts an, also
  // kann ihn niemand eintragen. Der Regtest-Durchlauf lieferte genau das:
  // { aktiv: true, uris: [], lauscht: ["127.0.0.1:19775"] }.
  kasten.classList.toggle("hidden", !turm.aktiv);
  if (!turm.aktiv) return;
  $("#wt-eigen-uri").textContent = uri;
  $("#wt-eigen-uri").classList.toggle("hidden", !uri);
  $("#wt-eigen-knoepfe").classList.toggle("hidden", !uri);
  $("#wt-eigen-ohne").classList.toggle("hidden", !!uri);
}

async function wachturmEintragen() {
  const knopf = $("#wt-eintragen");
  const meldung = $("#wt-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/wachtuerme", "POST",
              { adresse: $("#wt-adresse").value.trim() });
    $("#wt-adresse").value = "";
    await wachtuermeLaden();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Einen Kanal oeffnen ───────────────────────────────────────────────────

   Auch hier: erst rechnen, dann freigeben. Die Rechnung ist hier sogar der
   halbe Zweck -- sie sagt, ob das Guthaben ueberhaupt reicht, BEVOR LND es
   mit einer Fehlermeldung sagt. */

let KO_FREI = false;

function kanalSperren() {
  KO_FREI = false;
  $("#ko-oeffnen").disabled = true;
  $("#ko-vorschau").classList.add("hidden");
  $("#ko-fertig").classList.add("hidden");
}

function kanalTempo() {
  const g = document.querySelector('input[name="ko-tempo"]:checked');
  return g ? g.value : "normal";
}

function kanalLeib() {
  return {
    gegenstelle: $("#ko-gegenstelle").value.trim(),
    betrag: Number($("#ko-betrag").value || 0),
    tempo: kanalTempo(),
    privat: $("#ko-privat").checked,
  };
}

async function kanalPruefen() {
  const knopf = $("#ko-pruefen");
  const meldung = $("#ko-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  kanalSperren();
  try {
    const d = await api("/lightning/kanal/schaetzen", "POST", kanalLeib());
    const kasten = $("#ko-vorschau");
    kasten.textContent = "";
    kasten.append(zeile(t("kkp_kanal"), sats(d.betrag)));
    kasten.append(zeile(t("kkp_oeffnen"), sats(d.oeffnen_sat)));
    if (d.ruecklage_sat !== null && d.ruecklage_sat !== undefined) {
      kasten.append(zeile(t("kkp_ruecklage"), sats(d.ruecklage_sat)));
    }
    kasten.append(zeile(t("ko_gebraucht"), sats(d.gebraucht_sat)));
    kasten.append(zeile(t("ko_guthaben"), sats(d.guthaben_sat)));
    kasten.append(hinweis(d.reicht ? t("ko_reicht")
                                   : t("ko_fehlt", { n: zahl(d.fehlt_sat) }),
                          d.reicht ? "ok" : "bad"));
    // Kein Riegel, eine Warnung mit Begruendung. Die Entscheidung gehoert
    // dem Betreiber -- aber er soll sie kennen, bevor Geld drin liegt.
    if (d.knapp) {
      kasten.append(hinweis(t("ko_knapp", { n: zahl(d.ratsam_ab_sat) }),
                            "warn"));
    }
    kasten.classList.remove("hidden");
    // Nur wenn es auch reicht. LND wuerde sonst ablehnen -- aber erst
    // nachdem der Nutzer den gefaehrlichen Knopf gedrueckt hat.
    if (d.reicht) {
      KO_FREI = true;
      $("#ko-oeffnen").disabled = false;
    }
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function kanalOeffnen() {
  if (!KO_FREI) {
    $("#ko-meldung").textContent = t("ko_erst_pruefen");
    return;
  }
  const knopf = $("#ko-oeffnen");
  const meldung = $("#ko-meldung");
  knopf.disabled = true;
  meldung.textContent = t("ko_laeuft");
  let wiederFrei = true;
  try {
    const d = await api("/lightning/kanal/oeffnen", "POST",
                        { ...kanalLeib(), ...mitPin("#ko-pin") },
                        FRIST_GELD_MS);
    const fertig = $("#ko-fertig");
    fertig.textContent = t("ko_fertig", { txid: d.txid });
    fertig.classList.remove("hidden");
    $("#ko-gegenstelle").value = "";
    $("#ko-betrag").value = "";
    $("#ko-pin").value = "";
    meldung.textContent = "";
    kanalSperren();
    ladeLightningKanaele();
  } catch (e) {
    wiederFrei = geldfehler(e, meldung, "kanal_unklar");
    if (!wiederFrei) kanalSperren();
  } finally {
    if (wiederFrei) knopf.disabled = false;
  }
}

function mitPin(feld) {
  return PIN_DA ? { pin: $(feld).value } : {};
}

async function pinEinrichten() {
  const knopf = $("#pin-einrichten");
  const meldung = $("#pin-meldung");
  meldung.className = "dim small";
  if ($("#pin-neu").value !== $("#pin-wdh").value) {
    // Vor dem Server, denn er kann es gar nicht wissen -- er bekommt nur
    // eine der beiden Eingaben zu sehen.
    meldung.textContent = t("pin_stimmt_nicht");
    return;
  }
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/freigabe", "POST", {
      passwort: $("#pin-konto").value,
      pin: $("#pin-neu").value,
    });
    for (const id of ["#pin-konto", "#pin-neu", "#pin-wdh"]) $(id).value = "";
    meldung.textContent = t("pin_eingerichtet");
    await pinLaden();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function pinAendern() {
  const knopf = $("#pin-aendern");
  const meldung = $("#pin-meldung2");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/freigabe/aendern", "POST", {
      alt: $("#pin-alt").value,
      neu: $("#pin-neu2").value,
    });
    for (const id of ["#pin-alt", "#pin-neu2"]) $(id).value = "";
    meldung.textContent = t("pin_geaendert");
    await pinLaden();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function pinEntfernen() {
  const knopf = $("#pin-entfernen");
  const meldung = $("#pin-meldung2");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/freigabe/entfernen", "POST", { pin: $("#pin-alt").value });
    $("#pin-alt").value = "";
    meldung.textContent = t("pin_entfernt");
    await pinLaden();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Lightning: die Wallet anlegen ──────────────────────────────────────── */
//
// Drei Schritte, und keiner laesst sich ueberspringen. Der zweite blendet die
// Woerter WIEDER AUS, bevor der dritte kommt -- eine Gegenprobe, bei der die
// Antwort noch am Bildschirm steht, prueft nichts.

const WALLET_SCHRITTE = ["start", "woerter", "probe", "gesperrt",
                         "fertig", "unklar", "wiederherstellen", "zurueck"];

function walletSchritt(name) {
  for (const s of WALLET_SCHRITTE) {
    $("#w-schritt-" + s).classList.toggle("hidden", s !== name);
  }
}

async function walletSeedErzeugen() {
  const knopf = $("#w-erzeugen");
  const meldung = $("#w-start-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    const d = await api("/lightning/seed", "POST");
    const liste = $("#w-woerter");
    liste.textContent = "";
    for (const wort of d.woerter) {
      const li = document.createElement("li");
      li.textContent = wort;                    // bewusst textContent
      liste.append(li);
    }
    walletStellen = d.stellen;
    $("#w-abgeschrieben").checked = false;
    $("#w-weiter").disabled = true;
    walletSchritt("woerter");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail;
    meldung.textContent = (d && d.meldung) ? t(d.meldung) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

let walletStellen = [];

function walletZurGegenprobe() {
  // Die Woerter verschwinden HIER, nicht erst nach der Antwort. Sons
  // koennte man sie abschreiben, waehrend man gefragt wird.
  $("#w-woerter").textContent = "";
  const ziel = $("#w-probe-felder");
  ziel.textContent = "";
  for (const nr of walletStellen) {
    const zeile = document.createElement("div");
    zeile.className = "probe-feld";
    const kopf = document.createElement("span");
    kopf.className = "nr";
    kopf.textContent = t("wl_wort_nr", { nr });
    const feld = document.createElement("input");
    feld.type = "text";
    feld.autocomplete = "off";
    feld.spellcheck = false;
    feld.dataset.nr = nr;
    zeile.append(kopf, feld);
    ziel.append(zeile);
  }
  walletSchritt("probe");
  const erstes = ziel.querySelector("input");
  if (erstes) erstes.focus();
}

async function walletAnlegen() {
  const knopf = $("#w-anlegen");
  const meldung = $("#w-probe-meldung");
  const probefehler = $("#w-probe-fehler");
  knopf.disabled = true;
  meldung.textContent = "";
  probefehler.textContent = "";
  probefehler.classList.add("hidden");
  const antworten = {};
  for (const feld of $$("#w-probe-felder input")) {
    antworten[feld.dataset.nr] = feld.value;
  }
  try {
    await api("/lightning/wallet", "POST", {
      antworten,
      entsperrweg: entsperrweg("w"),
      passwort: $("#w-passwort").value,
    });
    // Der Schlusssatz beschreibt eine SICHERHEITSENTSCHEIDUNG, und es gab
    // ihn nur in einer Fassung: "Dein Knoten entsperrt sie ab jetzt bei
    // jedem Start von allein." Wer ein eigenes Passwort gesetzt hat, bekam
    // damit das Gegenteil dessen gesagt, was gilt -- und stuende beim
    // naechsten Neustart vor einem ruhenden Lightning, ohne zu wissen,
    // warum. Gefunden am 03.09.2026 im Pruefstand, vor dem ersten echten
    // Durchlauf.
    //
    // Ueber data-i18n gesetzt, nicht als fester Text: sonst stuende nach
    // einem Sprachwechsel wieder der falsche Satz da.
    const weg = entsperrweg("w");
    const schluss = $("#w-fertig-text");
    schluss.dataset.i18n = weg === "datei" ? "wl_fertig_auto"
      : weg === "merken" ? "wl_fertig_merken" : "wl_fertig_hand";
    schluss.textContent = t(schluss.dataset.i18n);
    $("#w-passwort").value = "";
    await entsperrwegLaden();
    walletSchritt("fertig");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    const text = d.meldung
      ? t(d.meldung, { mindestens: PASSWORT_MIN, ...d })
      : t("e_fehler");
    // Ein Fehler an den WÖRTERN gehört an die Wörter. Er stand unten neben
    // dem Knopf, also direkt unter dem Passwortfeld — der Betreiber las dort
    // "das stimmt so nicht, noch 3 Versuche" und bezog es auf sein
    // Passwort. Bei fünf Versuchen und einem frisch beschriebenen Zettel
    // ist das keine Kleinigkeit.
    if (d.meldung === "gegenprobe_falsch") {
      probefehler.textContent = text;
      probefehler.classList.remove("hidden");
    } else {
      meldung.textContent = text;
    }
    // Bei aufgegeben oder abgelaufen gibt es neue Woerter -- zurueck an den
    // Anfang, statt ein Formular stehen zu lassen, das nichts mehr bewirkt.
    if (d.meldung === "gegenprobe_aufgegeben" || d.meldung === "seed_abgelaufen") {
      walletStellen = [];
      $("#w-start-meldung").textContent = t(d.meldung);
      walletSchritt("start");
    }
  } finally {
    knopf.disabled = false;
  }
}

// Von vorn anfangen. Sichtbar nur, wenn es ueberhaupt eine Wallet gibt --
// und das Formular erst, wenn sie gesperrt ist: LND kann sein Passwort nur
// beim Entsperren pruefen, also nur an einer gesperrten Wallet. Ein
// Passwortfeld, das nichts prueft, waere eine Attrappe.
async function zeigeTilgung(stand) {
  const kasten = $("#w-tilgen");
  if (!kasten) return;
  const gibtsWallet = stand === "gesperrt" || stand === "bereit"
                      || stand === "startet";
  kasten.classList.toggle("hidden", !gibtsWallet);
  if (!gibtsWallet) return;
  const gesperrt = stand === "gesperrt";
  $("#tg-sperren-block").classList.toggle("hidden", gesperrt);
  $("#tg-formular").classList.toggle("hidden", !gesperrt);
  if (gesperrt) {
    try {
      const d = await api("/lightning/name");
      $("#tg-alias-d").textContent = t("tg_alias_d", { alias: d.alias });
    } catch (e) { /* der Hinweis ist Beiwerk, das Feld bleibt benutzbar */ }
  }
}

/* Die Wallet zusperren. Zwei Stellen brauchen es -- der Loesch-Kasten und
   der Kasten zum Wechseln auf "von allein entsperren". Beide, weil LND sein
   Passwort NUR beim Entsperren pruefen kann, also nur an einer gesperrten
   Wallet.

   Bis zum 10.09.2026 gab es den Knopf nur beim Loeschen, und die Meldung
   "sperre sie zuerst mit dem Knopf darueber" zeigte im anderen Kasten ins
   Leere. */
/* Nach dem Sperren warten, bis die Wallet WIRKLICH zu ist -- und es
   solange sagen.

   DER BEFUND VOM 11.09.2026. Der Betreiber: "dazu steht hier wallet sperren .. da
   drueck ich drauf passiert nix". Es passierte sehr wohl etwas: LND wurde
   beendet und neu gestartet, was bis zu neunzig Sekunden dauert. Nur sah
   man davon nichts -- der einzige Takt dieser Oberflaeche frischt die
   Uebersicht auf, nicht die Wallet-Ansicht. Der Kasten blieb also stehen,
   wie er war, und das Loeschformular kam nie.

   Ein Knopf, der eine Minute lang arbeitet und dabei schweigt, ist von
   einem kaputten Knopf nicht zu unterscheiden. */
const SPERR_TAKT_MS = 2000;
const SPERR_FRIST_MS = 150000;     // LNDs Neustart darf 90 s brauchen

async function warteBisGesperrt(meldungId) {
  const meldung = $(meldungId);
  meldung.classList.remove("hidden");
  const ende = Date.now() + SPERR_FRIST_MS;
  while (Date.now() < ende) {
    await new Promise((r) => setTimeout(r, SPERR_TAKT_MS));
    let d;
    try {
      d = await api("/lightning");
    } catch (e) {
      if (e && e.abgemeldet) return;
      continue;               // waehrend des Neustarts sind Aussetzer normal
    }
    const stand = (d.knoten || {}).stand;
    if (stand === "gesperrt") {
      meldung.textContent = t("tg_ist_gesperrt");
      // Beide Kaesten haengen daran: das Loeschformular und die Wahl des
      // Entsperrwegs.
      await ladeWallet();
      await entsperrwegLaden();
      return;
    }
    // Solange es laeuft, die Sekunden mitzaehlen -- eine Anzeige, die sich
    // nicht ruehrt, sieht aus wie eine haengende.
    const uebrig = Math.round((ende - Date.now()) / 1000);
    meldung.textContent = t("tg_sperren_laeuft", { rest: uebrig });
  }
  meldung.textContent = t("tg_sperren_haengt");
}

async function walletSperren(knopfId = "#tg-sperren",
                             meldungId = "#tg-sperr-meldung") {
  const knopf = $(knopfId);
  const meldung = $(meldungId);
  knopf.disabled = true;
  // Der Kasten faengt versteckt an -- ohne diese Zeile bliebe er es auch,
  // und der Knopf schwiege wieder.
  meldung.classList.remove("hidden");
  meldung.textContent = "";
  try {
    await api("/lightning/wallet/sperren", "POST");
    meldung.textContent = t("tg_sperren_laeuft", { rest: SPERR_FRIST_MS / 1000 });
    await warteBisGesperrt(meldungId);
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function walletTilgen() {
  const knopf = $("#tg-loeschen");
  const meldung = $("#tg-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/wallet/loeschen", "POST", {
      passwort: $("#tg-passwort").value,
      alias: $("#tg-alias").value,
      ...mitPin("#tg-pin"),
    });
    $("#tg-passwort").value = "";
    $("#tg-alias").value = "";
    $("#tg-pin").value = "";
    meldung.textContent = t("tg_laeuft");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function ladeWallet() {
  // Die Abfrage steht VOR der Auswertung, und ihr Fehlschlag fuehrt nicht
  // weiter. Vorher fiel er durch bis ans Ende der Funktion -- und dort steht
  // walletSchritt("start"), also der Ablauf, der eine WALLET ANLEGT.
  //
  // Eine Abfrage, die nicht durchkam, ist kein Beweis, dass es keine Wallet
  // gibt. Waehrend des Erstabgleichs kommen Abfragen regelmaessig nicht
  // durch. Jemandem, der laengst eine Wallet hat, den Anlege-Ablauf
  // hinzustellen, ist die gefaehrlichste Verwechslung in diesem Projekt:
  // am Ende steht ein Seed, den man abschreiben soll, und die Frage, welcher
  // von beiden jetzt gilt.
  let d;
  try {
    d = await api("/lightning");
  } catch (e) {
    if (e && e.abgemeldet) return;
    walletSchritt("unklar");
    return;
  }
  {
    const stand = (d.knoten || {}).stand;
    zeigeTilgung(stand);
    // Gesperrt ist der Normalzustand nach jedem Neustart, wenn nich
    // automatisch entsperrt wird. Dann gehoert hier das Passwortfeld hin und
    // nicht ein Ablauf, der eine zweite Wallet anlegen wollte.
    if (stand === "gesperrt") { walletSchritt("gesperrt"); return; }
    // "Die Wallet steht -- angelegt und entsperrt" ist nach dem Anlegen
    // richtig und stand danach fuer immer da: ein Glueckwunsch als Kopfzeile
    // einer Ansicht, in der gearbeitet wird. Beim Anlegen und nach dem
    // Entsperren zeigen ihn die beiden anderen Aufrufer weiterhin.
    if (stand === "bereit") { walletSchritt(""); return; }
    if (stand && stand !== "keine_wallet" && stand !== "aus") {
      walletSchritt("fertig");
      return;
    }
  }
  walletAutoFolge();
  walletSchritt("start");
}

// Was der Schalter bedeutet, steht darunter -- und zwar der ganze Satz, nich
// nur "an" oder "aus". Es ist die einzige Entscheidung in diesem Ablauf, bei
// der beide Antworten vertretbar sind.
/* Welcher der drei Wege gewaehlt ist. */
function entsperrweg(vorsilbe) {
  const gewaehlt = document.querySelector(
    `input[name="${vorsilbe}-weg"]:checked`);
  return gewaehlt ? gewaehlt.value : "aus";
}

/* Was der Weg bedeutet, steht darunter -- und zwar der ganze Satz.

   Bis zum 10.09.2026 war das ein Haekchen mit zwei Saetzen, und der Satz
   fuer "an" stimmte nicht mehr: er versprach, SatoshiCortex wuerfele das
   Passwort selbst. Das tat es seit dem 09.09. nicht mehr -- seit des Betreibers
   Einwand waehlt der Nutzer es. Schlimmer noch: das Passwortfeld wurde bei
   "an" AUSGEBLENDET, und ohne Passwort lehnt der Server das Anlegen ab. Wer
   automatisch entsperren wollte, kam gar nicht durch. */
function entsperrwegFolge(vorsilbe) {
  const weg = entsperrweg(vorsilbe);
  const n = $(`#${vorsilbe}-weg-folge`);
  n.className = "note" + (weg === "datei" ? " warn" : "");
  n.textContent = t("wl_weg_folge_" + weg);
  // Getippt wird das Wallet-Passwort in JEDEM der drei Wege. Das Feld
  // auszublenden war der Fehler vom 09.09.2026: ohne Passwort lehnt der
  // Server das Anlegen ab, und wer es nicht sieht, kommt gar nicht durch.
}

function walletAutoFolge() { entsperrwegFolge("w"); }

/* ── Den Entsperrweg an einer bestehenden Wallet wechseln ─────────────────

   Waehlbar war der Weg bisher nur beim Anlegen. Wer schon eine Wallet
   hatte, kam nie daran -- und "dann leg sie halt neu an" ist keine Antwort,
   sobald Geld darin liegt.

   Ob getippt werden muss, haengt daran, woher das heutige Passwort kommt:
   liegt es in der Klartextdatei oder im Speicher dieser Anwendung, holt sie
   es sich dort. Liegt es nirgends, muss es getippt und von LND geprueft
   werden. */
function zeichneEntsperrwegWahl() {
  const kasten = $("#w-entsperrweg");
  if (!kasten) return;
  kasten.classList.remove("hidden");
  // Im Weg "merken" ist nach einem Neustart DIESER Anwendung nichts mehr
  // gemerkt. Das zu verschweigen hiesse zu behaupten, es kuemmere sich
  // jemand darum -- und der Knoten stuende still.
  $("#ew-jetzt").textContent = t("ew_jetzt") + ": "
    + t("ew_jetzt_" + ENTSPERRWEG)
    + (ENTSPERRWEG === "merken" && !GEMERKT
       ? " " + t("ew_noch_nicht_gemerkt") : "");
  const gewaehlt = document.querySelector('input[name="ew-weg"]:checked');
  if (!gewaehlt) {
    const passend = document.querySelector(
      `input[name="ew-weg"][value="${ENTSPERRWEG}"]`);
    if (passend) passend.checked = true;
  }
  entsperrwegWahlFolge();
}

function entsperrwegWahlFolge() {
  const gewaehlt = document.querySelector('input[name="ew-weg"]:checked');
  const ziel = gewaehlt ? gewaehlt.value : ENTSPERRWEG;
  const n = $("#ew-weg-folge");
  n.className = "note" + (ziel === "datei" ? " warn" : "");
  n.textContent = t("wl_weg_folge_" + ziel);
  // Das heutige Passwort liegt schon vor, wenn es in der Klartextdatei
  // steht oder im Speicher -- solange die Anwendung seit dem letzten
  // Entsperren nicht neu gestartet ist.
  const liegt_vor = ENTSPERRWEG === "datei"
    || (ENTSPERRWEG === "merken" && GEMERKT);
  // Getippt werden muss es nur fuer EINEN Weg: "datei" schreibt Klartext auf
  // die Platte, und ein falsches Passwort dort haengt LND beim naechsten
  // Start auf. "aus" und aus "merken" schreiben nichts -- dort waere die
  // Abfrage eine Huerde ohne Zweck.
  //
  // Aus dem Betrieb, 10.09.2026: "habe aber gerade den Haken gesetzt bei fuer die
  // Laufzeit merken aber das wird noch nicht uebernommen". Genau deshalb:
  // die Oberflaeche verlangte ein Passwort und eine gesperrte Wallet, um auf
  // einen Weg zu wechseln, der gar nichts ablegt.
  $("#ew-probe").classList.toggle("hidden", !(ziel === "datei" && !liegt_vor));
}

async function entsperrwegWechseln() {
  const knopf = $("#ew-wechseln");
  const meldung = $("#ew-meldung");
  const gewaehlt = document.querySelector('input[name="ew-weg"]:checked');
  if (!gewaehlt) return;
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/entsperrweg", "POST", {
      weg: gewaehlt.value,
      passwort: $("#ew-passwort").value,
    });
    $("#ew-passwort").value = "";       // nicht im Formular stehen lassen
    meldung.textContent = t("ew_gewechselt");
    await entsperrwegLaden();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

// Welcher Weg auf diesem Geraet WIRKLICH eingerichtet ist -- gelesen aus dem
// Bestand, nicht aus einer Wahl von vorhin.
let ENTSPERRWEG = "aus";
// Und ob gerade wirklich etwas gemerkt ist. Der Weg "merken" ueberlebt einen
// Neustart der Anwendung, das gemerkte Passwort nicht.
let GEMERKT = false;

async function entsperrwegLaden() {
  try {
    const d = await api("/lightning/entsperrweg");
    ENTSPERRWEG = d.weg || "aus";
    GEMERKT = !!(d && d.gemerkt);
  } catch (e) {
    if (e && e.abgemeldet) return;
    ENTSPERRWEG = "aus";
    GEMERKT = false;
  }
  zeichneEntsperrwegWahl();
  const titel = $("#w-entsperren-titel");
  if (titel) {
    titel.textContent = t("wl_entsperren_passwort");
    // Im Weg "merken" gehoert der Zusatz daneben, dass es das letzte Mal
    // fuer diesen Lauf war. Ohne ihn sieht die Eingabe aus wie die von
    // "aus", und der Unterschied waere nirgends zu sehen.
    $("#w-entsperren-d").textContent = t("wl_entsperren_passwort_d")
      + (ENTSPERRWEG === "merken" ? " " + t("wl_entsperren_gemerkt") : "");
  }
}

async function walletEntsperren() {
  const knopf = $("#w-entsperren");
  const feld = $("#w-entsperren-passwort");
  const meldung = $("#w-entsperren-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    // Ein Geheimnis, ein Feld. Der Tresor stellte hier ein zweites daneben,
    // das dasselbe tat -- genau der Tausch, den Aus dem Betrieb, 10.09.2026
    // zerlegt hat.
    await api("/lightning/entsperren", "POST", { passwort: feld.value });
    feld.value = "";                    // nicht im Formular stehen lassen
    meldung.textContent = t("wl_entsperrt");
    // Ob ab jetzt gemerkt wird, weiss nur der Server -- also nachfragen
    // statt raten.
    await entsperrwegLaden();
    walletSchritt("fertig");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Lightning: einen gesicherten Knoten zurueckholen ───────────────────── */
//
// Der Gegenweg. Beim Anlegen beweist der Nutzer, dass er die Woerter HAT --
// hier legt er sie vor. Sie gehen durch dieses Formular zu LND und sonst
// nirgendwohin: kein localStorage, kein Zustand, kein Protokoll.
//
// EINE EIGENHEIT, die hier sichtbar bleiben muss: die Kanalsicherung laesst
// sich an dieser Stelle NICHT pruefen. Sie ist mit einem Schluessel aus dem
// Seed verschluesselt, und den kennt erst die fertige Wallet. Ist es die
// falsche Datei, startet LND anschliessend nicht. Deshalb steht der Hinweis
// darauf im Formular, und deshalb gibt es unter "Sicherung" die Kopie-Probe
// fuer den Tag, an dem der Knoten noch laeuft.

// Was die Datei hoechstens gross sein darf, bevor der Browser sie gar nicht
// erst einliest. Dieselbe Grenze wie im Backend.
const SICHERUNG_HOECHSTGROESSE = 1024 * 1024;

let whSicherung = "";        // base64, nur im Arbeitsspeicher

/* ── Die Wortliste: die Frage, die LND auch stellt -- nur frueher ────────

   LND rechnet die Pruefsumme erst, wenn ALLE vierundzwanzig Woerter bekannt
   sind. Ein vertipptes Wort scheitert davor, und die Meldung dazu landete
   bisher nur im Protokoll.

   Aus dem Betrieb, 11.09.2026, nach einer Stunde Suche:

       word mopth isn't a part of default word list (index=7)

   Gemeint war "month" -- das EINZIGE Wort der Liste, das einen Buchstaben
   davon entfernt liegt. Genau das gehoert ans Feld, waehrend man tippt. */

/* Woerter der Liste, die sich um genau einen Buchstaben unterscheiden.
   Mehr Naehe braucht es nicht: ein Tippfehler ist fast immer einer. */
function bip39Nahe(wort) {
  const nahe = [];
  for (const kandidat of BIP39) {
    if (Math.abs(kandidat.length - wort.length) > 1) continue;
    if (kandidat.length === wort.length) {
      let anders = 0;
      for (let i = 0; i < wort.length; i++) {
        if (wort[i] !== kandidat[i] && ++anders > 1) break;
      }
      if (anders === 1) nahe.push(kandidat);
      continue;
    }
    // Ein Zeichen zu viel oder zu wenig.
    const [kurz, lang] = wort.length < kandidat.length
      ? [wort, kandidat] : [kandidat, wort];
    for (let i = 0; i < lang.length; i++) {
      if (lang.slice(0, i) + lang.slice(i + 1) === kurz) { nahe.push(kandidat); break; }
    }
  }
  return nahe;
}

/* Welche Felder ein Wort tragen, das es nicht gibt. Leere Felder zaehlen
   nicht -- die faengt die Zaehlung ab, und zwar mit einer eigenen Meldung. */
function whUnbekannteWoerter() {
  const schlecht = [];
  $$("#wh-woerter input").forEach((feld, i) => {
    const wort = feld.value.trim().toLowerCase();
    const unbekannt = wort !== "" && !BIP39_SATZ.has(wort);
    feld.classList.toggle("unbekannt", unbekannt);
    if (unbekannt) schlecht.push({ nr: i + 1, wort, nahe: bip39Nahe(wort) });
  });
  return schlecht;
}

/* Die Meldung dazu -- mit Vorschlag, wo es einen eindeutigen gibt. */
function whWortfehlerZeigen(schlecht) {
  const kasten = $("#wh-wortfehler");
  kasten.classList.toggle("hidden", !schlecht.length);
  if (!schlecht.length) return;
  kasten.textContent = t("wh_wort_unbekannt", {
    liste: schlecht.map((s) => s.nahe.length === 1
      ? t("wh_wort_vielleicht", { nr: s.nr, wort: s.wort, nahe: s.nahe[0] })
      : t("wh_wort_nur", { nr: s.nr, wort: s.wort })).join("; "),
  });
}

/* Die aria-label der 24 Felder nachziehen.

   Dieselbe Sache wie bei den Gegenstellenwegen, nur unsichtbar: die Felder
   werden bewusst nur EINMAL gebaut (wer schon getippt hat, soll seine
   Eingabe behalten), ihre Beschriftung ist aber uebersetzt. Nach einem
   Sprachwechsel las ein Vorlesewerkzeug sie in der alten Sprache vor.
   Befund vom 22.09.2026. */
function whBeschriften() {
  const ziel = $("#wh-woerter");
  if (!ziel) return;
  [...ziel.querySelectorAll("input")].forEach((feld, i) => {
    feld.setAttribute("aria-label", t("wl_wort_nr", { nr: i + 1 }));
  });
}

function whFelderBauen() {
  const ziel = $("#wh-woerter");
  // Vorhandene Felder bleiben stehen -- nur ihre Beschriftung wird
  // nachgezogen, falls inzwischen die Sprache gewechselt wurde.
  if (ziel.children.length) return whBeschriften();
  // Die Vorschlagsliste des Browsers einmal fuellen -- damit ein falsches
  // Wort gar nicht erst hineinkommt.
  const liste = $("#bip39-liste");
  if (liste && !liste.children.length) {
    const teil = document.createDocumentFragment();
    for (const wort of BIP39) {
      const eintrag = document.createElement("option");
      eintrag.value = wort;
      teil.append(eintrag);
    }
    liste.append(teil);
  }
  for (let nr = 1; nr <= 24; nr++) {
    const label = document.createElement("label");
    const kopf = document.createElement("span");
    kopf.className = "nr";
    kopf.textContent = String(nr);
    const feld = document.createElement("input");
    feld.type = "text";
    feld.autocomplete = "off";
    feld.spellcheck = false;
    feld.dataset.nr = String(nr);
    feld.setAttribute("list", "bip39-liste");
    feld.setAttribute("aria-label", t("wl_wort_nr", { nr }));
    // Beim Verlassen des Feldes pruefen, nicht bei jedem Tastendruck: waehrend
    // man "month" tippt, ist "mont" nun einmal kein Wort der Liste.
    feld.addEventListener("blur", () => whWortfehlerZeigen(whUnbekannteWoerter()));
    // Alle vierundzwanzig auf einmal einfuegen zu koennen ist kein Luxus:
    // wer sie aus einem Passwortmanager holt, hat sie als eine Zeile, und
    // vierundzwanzigmal umschalten waere die Stelle, an der man verrutscht.
    feld.addEventListener("paste", (e) => {
      const roh = (e.clipboardData || window.clipboardData).getData("text");
      const woerter = (roh || "").trim().toLowerCase().split(/\s+/);
      if (woerter.length < 2) return;         // ein einzelnes Wort: normal
      e.preventDefault();
      const start = Number(feld.dataset.nr) - 1;
      const felder = $$("#wh-woerter input");
      woerter.forEach((w, i) => {
        if (felder[start + i]) felder[start + i].value = w;
      });
    });
    label.append(kopf, feld);
    ziel.append(label);
  }
}

function whQuelle() {
  const gewaehlt = $$("input[name=wh-quelle]").find((r) => r.checked);
  return gewaehlt ? gewaehlt.value : "keine";
}

function whQuelleFolge() {
  const q = whQuelle();
  $("#wh-datei-zeile").classList.toggle("hidden", q !== "datei");
  $("#wh-ungeprueft").classList.toggle("hidden", q === "keine");
  if (q !== "datei") { whSicherung = ""; $("#wh-datei-meldung").textContent = ""; }
}

function whAutoFolge() { entsperrwegFolge("wh"); }

function whDateiGewaehlt() {
  const datei = ($("#wh-datei").files || [])[0];
  const meldung = $("#wh-datei-meldung");
  whSicherung = "";
  if (!datei) { meldung.textContent = ""; return; }
  if (datei.size > SICHERUNG_HOECHSTGROESSE) {
    meldung.textContent = t("wh_datei_zu_gross");
    return;
  }
  const leser = new FileReader();
  leser.onload = () => {
    whSicherung = base64AusPuffer(leser.result);
    meldung.textContent = t("wh_datei_gewaehlt",
                            { name: datei.name, bytes: datei.size });
  };
  leser.onerror = () => { meldung.textContent = t("e_fehler"); };
  leser.readAsArrayBuffer(datei);
}

// Eine Kanalsicherung ist ein paar Kilobyte gross -- Byte fuer Byte ist hier
// also unbedenklich. btoa(String.fromCharCode(...bytes)) waere kuerzer und
// wuerde bei grossen Dateien am Argumentlimit scheitern.
function base64AusPuffer(puffer) {
  const bytes = new Uint8Array(puffer);
  let roh = "";
  for (let i = 0; i < bytes.length; i++) roh += String.fromCharCode(bytes[i]);
  return btoa(roh);
}

function walletZurueckholen() {
  whFelderBauen();
  $("#wh-dauer").textContent = t("wh_dauer", { fenster: 2500 });
  whAutoFolge();
  whQuelleFolge();
  walletSchritt("wiederherstellen");
  const erstes = $("#wh-woerter input");
  if (erstes) erstes.focus();
}

function whWoerterLeeren() {
  for (const feld of $$("#wh-woerter input")) feld.value = "";
  $("#wh-passphrase").value = "";
  $("#wh-passwort").value = "";
  whSicherung = "";
}

/* Die Seed-Passphrase -- und zwar nur, wenn sie jemand absichtlich
   eingetragen hat.

   SatoshiCortex setzt selbst nie eine. Das Feld gibt es fuer Seeds, die
   anderswo entstanden sind. Es steckt deshalb in einem zugeklappten
   Abschnitt -- und genau solche Felder fuellen Browser und
   Passwortverwaltungen gern von allein aus. */
function whPassphrase() {
  const block = $("#wh-pass-block");
  return block && block.open ? $("#wh-passphrase").value : "";
}

async function walletWiederherstellen() {
  const knopf = $("#wh-starten");
  const meldung = $("#wh-meldung");
  // VOR dem Senden. LND wuerde dasselbe sagen, aber erst nach einem
  // Rundlauf und nur mit EINEM Wort -- hier stehen gleich alle, mit
  // Vorschlag und am Feld markiert.
  const schlecht = whUnbekannteWoerter();
  whWortfehlerZeigen(schlecht);
  if (schlecht.length) {
    meldung.textContent = t("wh_erst_woerter");
    return;
  }
  knopf.disabled = true;
  meldung.textContent = "";
  const quelle = whQuelle();
  const leib = {
    woerter: $$("#wh-woerter input").map((f) => f.value),
    // NUR aus einem aufgeklappten Abschnitt. Siehe die Begruendung in der
    // Vorlage: ein automatisch ausgefuelltes Passwortfeld, das niemand
    // sieht, laesst LND den richtigen Seed ablehnen.
    passphrase: whPassphrase(),
    entsperrweg: entsperrweg("wh"),
    passwort: $("#wh-passwort").value,
    kanalsicherung: quelle === "datei" ? whSicherung : "",
    vom_ziel: quelle === "ziel",
  };
  try {
    const d = await api("/lightning/wiederherstellen", "POST", leib);
    // Erst jetzt loeschen. Waeren die Felder vorher leer, muesste jemand
    // nach einem Fehlschlag alles noch einmal tippen.
    whWoerterLeeren();
    $("#wh-fertig-kanaele").classList.toggle("hidden", !d.mit_kanaelen);
    walletSchritt("zurueck");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung
      ? t(d.meldung, { mindestens: PASSWORT_MIN, ...d })
      : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Die Kopie pruefen, die man in der Hand hat ─────────────────────────── */
//
// Dass der Knoten eine heile Sicherung erzeugen KANN, sagt nichts ueber die
// Kopie auf dem Stick. LND schliesst die vorgelegte Datei wirklich auf --
// damit ist zweierlei bewiesen: sie ist heil, und sie gehoert zu DIESEM
// Knoten. Braucht offchain:read, also kein Recht, das etwas bewegen koennte.

async function sicherungKopiePruefen(vomZiel) {
  const meldung = $("#sipr-meldung");
  const knoepfe = [$("#sipr-pruefen"), $("#sipr-ziel")];
  const leib = { vom_ziel: !!vomZiel, blob: "" };
  if (!vomZiel) {
    const datei = ($("#sipr-datei").files || [])[0];
    if (datei) {
      if (datei.size > SICHERUNG_HOECHSTGROESSE) {
        meldung.className = "note warn";
        meldung.classList.remove("hidden");
        meldung.textContent = t("wh_datei_zu_gross");
        return;
      }
      leib.blob = await new Promise((fertig, schief) => {
        const leser = new FileReader();
        leser.onload = () => fertig(base64AusPuffer(leser.result));
        leser.onerror = schief;
        leser.readAsArrayBuffer(datei);
      }).catch(() => "");
      if (!leib.blob) {
        meldung.className = "note warn";
        meldung.classList.remove("hidden");
        meldung.textContent = t("e_fehler");
        return;
      }
    }
  }
  knoepfe.forEach((k) => { k.disabled = true; });
  meldung.className = "note";
  meldung.classList.remove("hidden");
  meldung.textContent = t("sipr_laeuft");
  try {
    const d = await api("/lightning/sicherung/pruefen", "POST", leib);
    // Heil ist nicht dasselbe wie aktuell. Eine tadellose Sicherung von
    // vorgestern deckt den Kanal von gestern nicht ab -- und das ist der
    // Fehler, den man sonst erst hinterher bemerkt.
    if (d.offen === null || d.offen === undefined) {
      meldung.className = "note ok";
      meldung.textContent = t("sipr_ohne_vergleich", d);
    } else if (d.vollstaendig) {
      meldung.className = "note ok";
      meldung.textContent = t("sipr_ok", d);
    } else {
      meldung.className = "note warn";
      meldung.textContent = t("sipr_luecke", d);
    }
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.className = "note warn";
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knoepfe.forEach((k) => { k.disabled = false; });
  }
}

/* ── Einzahlen und Gebuehren ────────────────────────────────────────────── */
//
// Einzahlen braucht address:write, Gebuehren offchain:write. Kanaele oeffnen
// und schliessen sowie Lightning zahlen gibt es seit dem 12.09.2026 -- alle
// hinter derselben PIN wie das Senden.

function einzahlAdressform() {
  const gewaehlt = document.querySelector('input[name="ez-art"]:checked');
  return gewaehlt ? gewaehlt.value : "taproot";
}

// `neu` MUSS ausdruecklich uebergeben werden. Haengt man die Funktion direkt
// als Zuhoerer an einen Knopf, bekaeme sie das Klick-Ereignis als erstes
// Argument -- und ein Ereignis ist wahr. Jeder Klick auf "anzeigen" haette
// dann eine neue Adresse verbraucht, also genau das, was hier abgestellt
// werden soll.
// Was jetzt zu tun ist -- oder nichts.
//
// Des Betreibers Befunde 1, 12 und 13: der Zustand stand dort, wo man nicht
// handeln kann, und das Handeln dort, wo man nicht hinsieht. Die Uebersicht
// meldete "LND laeuft", waehrend der Knoten mit gesperrter Wallet stillstand;
// die Kanalseite sagte "angelegt, aber gesperrt" ohne einen Weg zum
// Entsperren; und dass ueberhaupt zuerst eine Wallet noetig ist, stand in
// genau einem Satz unter Lightning -> Knoten.
//
// Entschieden wird im Backend (naechster_schritt), damit es EINE Stelle
// gibt. Hier steht nur, wie es aussieht.
function zeigeTunzeile(schritt) {
  const zeile = $("#tunzeile");
  if (!zeile) return;
  if (!schritt) {
    // Steht nichts an, verschwindet sie ganz. "wenn alles da, muss man ja
    // nicht mehr sehen was zu tun ist" -- der Betreiber, 09.09.2026.
    zeile.classList.add("hidden");
    return;
  }
  $("#tunzeile-text").textContent = t("tun_" + schritt.was);
  const knopf = $("#tunzeile-knopf");
  knopf.textContent = t("tun_" + schritt.was + "_knopf");
  knopf.onclick = () => zeigeAnsicht(schritt.ansicht);
  // Hinweise, die eine WAHL beschreiben, lassen sich dauerhaft wegnehmen.
  // Die anderen nicht: eine gesperrte Wallet verschwindet, wenn man sie
  // entsperrt, nicht wenn man den Hinweis wegklickt.
  const weg = $("#tunzeile-weg");
  weg.classList.toggle("hidden", !schritt.abweisbar);
  weg.textContent = t("tun_weg");
  weg.onclick = async () => {
    try {
      await api("/hinweis/abweisen", "POST", { was: schritt.was });
      zeile.classList.add("hidden");
    } catch (e) { /* beim naechsten Durchgang steht er halt noch da */ }
  };
  zeile.classList.toggle("dringend", !!schritt.dringend);
  zeile.classList.remove("hidden");
}

// Der Name des Knotens. Bis zum 09.09.2026 gab es dafuer nichts -- weder
// Feld noch Endpunkt -- und jeder Knoten dieser Software hiess gleich.
// Befund 20: das Recht lag im Macaroon, die Funktion fehlte.
async function gegenstelleVerbinden() {
  const knopf = $("#ko-verbinden");
  const meldung = $("#ko-verbindmeldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/verbinden", "POST",
              { adresse: $("#ko-gegenstelle").value });
    meldung.textContent = t("vb_verbunden");
    // Das Feld NICHT leeren: wer gerade verbunden hat, will meistens als
    // Naechstes den Kanal oeffnen -- und dafuer steht dieselbe Kennung
    // eine Zeile tiefer schon im richtigen Feld.
    ladeLightningKanaele();          // die Leitung taucht gleich in der Liste auf
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function knotennameLaden() {
  try {
    const d = await api("/lightning/name");
    $("#kn-alias").value = d.alias || "";
    $("#kn-farbe").value = d.farbe || "#f7931a";
    if (d.minchansize) $("#kn-minchan").value = d.minchansize;
  } catch (e) { /* Einstellungen bleiben benutzbar, auch ohne Lightning */ }
}

async function knotennameSpeichern() {
  const knopf = $("#kn-speichern");
  const meldung = $("#kn-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    const d = await api("/lightning/name", "POST", {
      alias: $("#kn-alias").value,
      farbe: $("#kn-farbe").value,
      minchansize: Number($("#kn-minchan").value || 0),
    });
    meldung.textContent = t(d.lightning_neustart
      ? "kn_gespeichert_neustart" : "e_gespeichert");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function einzahladresseHolen(neu) {
  const knopf = $("#ez-holen");
  const meldung = $("#ez-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    const d = await api("/lightning/einzahladresse?art="
      + encodeURIComponent(einzahlAdressform())
      + "&neu=" + (neu === true ? "true" : "false"), "POST");
    $("#ez-feld").textContent = d.adresse;
    $("#ez-oeffnen").href = "bitcoin:" + d.adresse;
    zeichneQr($("#ez-qr"), "bitcoin:" + d.adresse);
    $("#ez-adresse").classList.remove("hidden");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

async function adresseKopieren() {
  return kopiere($("#ez-feld"), $("#ez-meldung"), "ez_kopiert");
}

// Zweimal gebraucht, seit die eigene Verbindungsadresse dazugekommen ist:
// einmal fuer die Einzahladresse, einmal fuer die Knotenadresse.
async function kopiere(feld, meldung, schluessel) {
  // Drei Stufen, und die erste allein war der Fehler.
  //
  // navigator.clipboard gibt es NUR in einem sicheren Kontext -- HTTPS oder
  // localhost. Im Heimnetz über http://192.168.x.x ist es schlicht
  // undefiniert, der Aufruf wirft, und der alte Auffangzweig markierte
  // stumm etwas, ohne eine Meldung zu setzen. Für der Betreiber sah der Knopf
  // deshalb tot aus — alle vier.
  //
  // Und warum es nie auffiel: beim Entwickeln läuft man auf localhost, und
  // das IST ein sicherer Kontext. Der Knopf funktionierte überall außer
  // dort, wo er benutzt wird.
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(feld.textContent);
      meldung.textContent = t(schluessel);
      return;
    } catch (e) { /* weiter zur zweiten Stufe */ }
  }

  // Zweite Stufe: markieren und den alten Befehl. Veraltet, aber er
  // funktioniert auch über einfaches HTTP — und genau darum geht es hier.
  const bereich = document.createRange();
  bereich.selectNodeContents(feld);
  const auswahl = window.getSelection();
  auswahl.removeAllRanges();
  auswahl.addRange(bereich);
  let geklappt = false;
  try { geklappt = document.execCommand("copy"); } catch (e) { geklappt = false; }

  // Dritte Stufe: markiert lassen UND es sagen. Ein Knopf darf nie stumm
  // nichts tun — dann sucht der Nutzer den Fehler bei sich.
  meldung.textContent = t(geklappt ? schluessel : "kopieren_von_hand");
}

/* ── Was das Netz nimmt ──────────────────────────────────────────────────
 *
 * Aus dem Betrieb, 18.09.2026: „könnten wir hier im gebüren feld irgendwie immer
 * mal so den durchschnitt anzeigen lassen der letzten 4 wochen .. oder das
 * ganze irgendwie automatisieren“. Und auf die Rückfrage: „wenn dann 100%
 * und alle 3 Stufen gemeinsam! Obergrenze ist max wert der letzten 4 wochen
 * und untergrenze ist dann min wert der letzten 4 wochen für die automatik“.
 *
 * Alles drei sitzt hier: die gemessene Zahl, das wandernde Band, und der
 * Schalter. Der Vorschlag steht auch dann da, wenn der Schalter aus ist —
 * man soll sehen können, was die Automatik täte, bevor man sie einschaltet.
 */
let NETZGEBUEHREN = null;

function gbVerlaufBild(verlauf, band) {
  const punkte = (verlauf || [])
    .filter((z) => z.median_ppm !== null && z.median_ppm !== undefined)
    .slice().reverse();
  const kasten = $("#gb-verlauf");
  kasten.textContent = "";
  if (punkte.length < 2) return;

  const NS = "http://www.w3.org/2000/svg";
  // Den Kasten MESSEN und die viewBox daraus bauen, statt eine feste Zeichnung
  // auf die Breite zu ziehen. Dann ist der Massstab 1:1 und es braucht kein
  // preserveAspectRatio -- dieselbe Falle wie beim Kursbild am 06.09.2026 und
  // beim Feerate-Diagramm am 07.09.2026.
  const B = Math.max(160, Math.round(kasten.clientWidth) || 320), H = 48;
  const werte = punkte.map((z) => Number(z.median_ppm));
  const oben = Math.max(...werte), unten = Math.min(...werte);
  const spanne = (oben - unten) || 1;
  const x = (i) => (i / (punkte.length - 1)) * B;
  const y = (w) => H - 4 - ((w - unten) / spanne) * (H - 8);

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${B} ${H}`);
  svg.setAttribute("width", String(B));
  svg.setAttribute("height", String(H));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", t("gb_netz_titel"));

  // Das Band als Fläche — es ist die Aussage, nicht Zierrat.
  if (band && band.unten_ppm !== null && band.oben_ppm !== null) {
    const flaeche = document.createElementNS(NS, "rect");
    const o = Math.min(y(band.oben_ppm), y(band.unten_ppm));
    flaeche.setAttribute("x", "0");
    flaeche.setAttribute("y", String(o));
    flaeche.setAttribute("width", String(B));
    flaeche.setAttribute("height",
      String(Math.max(1, Math.abs(y(band.unten_ppm) - y(band.oben_ppm)))));
    flaeche.setAttribute("class", "gb-band");
    svg.append(flaeche);
  }

  const linie = document.createElementNS(NS, "polyline");
  linie.setAttribute("points",
    punkte.map((z, i) => `${x(i)},${y(Number(z.median_ppm))}`).join(" "));
  linie.setAttribute("class", "gb-linie");
  svg.append(linie);
  kasten.append(svg);
}

/* Wie sich die Gebuehrensaetze des Netzes verteilen -- als Leiste und als
   Zeile darunter.

   Der Betreiber am 21.09.2026: "kann mann nicht einfach machen: 50% 0-100 die
   anderen 50% 100-600". Kann man, und es ist die bessere Auskunft: der Absatz,
   der vorher hier stand, ERKLAERTE fuenf Zeilen lang, dass die Verteilung
   schief ist. Die Leiste zeigt das und sagt zusaetzlich, wo die Masse liegt.

   Das feste Element wird bei JEDEM Aufruf zuerst geleert. Genau daran ist die
   alte Fassung gescheitert: sie haengte per .after() ein neues Geschwister an,
   und nach neun Durchlaeufen stand der Absatz neunmal da. */
function zeichneVerteilung(heute) {
  const kasten = $("#gb-netz-verteilung");
  if (!kasten) return;
  kasten.textContent = "";
  if (!heute) return;

  const stufen = heute.stufen;
  if (!Array.isArray(stufen) || !stufen.length) {
    // Jede Messung von vor dem 21.09.2026 hat keine Verteilung -- dann die
    // Spanne, wie sie vorher dort stand. Eine leere Leiste waere schlechter
    // als die aeltere Auskunft.
    if (heute.p25_ppm != null && heute.p75_ppm != null) {
      const zeile = document.createElement("div");
      zeile.className = "dim small";
      zeile.textContent = t("gb_netz_spanne",
        { p25: zahl(heute.p25_ppm), p75: zahl(heute.p75_ppm) });
      kasten.append(zeile);
    }
    return;
  }

  const balken = document.createElement("div");
  balken.className = "gb-vt-balken";
  const legende = document.createElement("div");
  legende.className = "gb-vt-legende";

  stufen.forEach((stufe, i) => {
    // Leere Stufen bleiben draussen -- fuenfmal "0 %" ist keine Auskunft.
    if (!stufe.anteil) return;
    const text = t("gb_stufe_anteil",
                   { anteil: stufe.anteil, spanne: spanneText(stufe) });

    const teil = document.createElement("span");
    teil.className = "gb-vt-teil gb-vt-" + i;
    teil.style.width = stufe.anteil + "%";
    teil.title = text;
    balken.append(teil);

    const eintrag = document.createElement("span");
    eintrag.className = "gb-vt-eintrag gb-vt-" + i;
    eintrag.textContent = text;
    legende.append(eintrag);
  });
  kasten.append(balken, legende);
}

/* Die Spanne einer Stufe als Text. Oben offen, weil es nach oben im
   Lightning-Netz keine Grenze gibt. */
function spanneText(stufe) {
  if (stufe.bis == null) return t("gb_stufe_ab", { von: zahl(stufe.von) });
  if (stufe.von === stufe.bis) return zahl(stufe.von);
  return t("gb_stufe_von_bis",
           { von: zahl(stufe.von), bis: zahl(stufe.bis) });
}

function zeichneNetzgebuehren(d) {
  NETZGEBUEHREN = d;
  const zahlen = $("#gb-netz-zahlen");
  const bandzeile = $("#gb-netz-band");
  const stand = $("#gb-automatik-stand");
  const heute = d.heute;

  if (d.misst_gerade) {
    zahlen.textContent = t("gb_messen_laeuft");
    zeichneVerteilung(null);
  } else if (heute && heute.median_ppm !== null) {
    zahlen.textContent = t("gb_netz_zahlen", {
      median: heute.median_ppm, basis: heute.basis_median_msat,
      linien: heute.linien, kanaele: heute.kanaele, tag: heute.tag,
    });
    // DER BEFUND VOM 21.09.2026 aus dem Betrieb, mit Bild: hier stand ein
    // fuenfzeiliger Absatz, der ERKLAERTE, warum der Median nicht in der
    // Mitte der Spanne liegt -- und er stand NEUNMAL untereinander, weil er
    // per zahlen.after() angehaengt und nie entfernt wurde. Dazu der
    // Betreiber: "was das den bitte fuer ein riesen text ?? ... kann mann
    // nicht einfach machen: 50% 0-100 die anderen 50% 100-600".
    //
    // Beides ist damit erledigt: die Verteilung wird GEZEIGT statt erklaert,
    // und sie geht in ein festes Element, das jedes Mal geleert wird. Sie
    // sagt zusaetzlich, WO die Masse liegt -- das stand in dem Absatz nie.
    zeichneVerteilung(heute);
  } else {
    zahlen.textContent = d.fehler ? t(d.fehler) : t("gb_netz_nie");
    zeichneVerteilung(null);
  }

  // Was WIR nehmen, aus dem Graphen gelesen — nicht aus unserer Erinnerung.
  const eigen = document.createElement("div");
  eigen.className = "dim small";
  eigen.textContent = (d.jetzt_ppm === null || d.jetzt_ppm === undefined)
    ? t("gb_netz_eigen_keine")
    : t("gb_netz_eigen", { eigen: d.jetzt_ppm });
  zahlen.append(document.createElement("br"), eigen);

  const band = d.band || {};
  bandzeile.textContent = (band.tage >= d.braucht_tage)
    ? t("gb_band", { unten: band.unten_ppm, oben: band.oben_ppm,
                     tage: band.tage })
    : t("gb_band_sammelt", { braucht: d.braucht_tage, tage: band.tage || 0 });

  gbVerlaufBild(d.verlauf, band);

  $("#gb-automatik").checked = !!d.automatik;
  $("#gb-uebernehmen").disabled = !(heute && heute.median_ppm !== null);
  $("#gb-messen").disabled = !!d.misst_gerade;

  // Was die Automatik gerade tut -- oder warum nicht.
  //
  // Der Vorschlag steht AUCH dann da, wenn sie aus ist. Ein Schalter, hinter
  // dem eine Überraschung wartet, gehört nicht an einen Knoten, auf dem Geld
  // liegt.
  const rat = d.vorschlag || {};
  const GRUENDE = {
    median: "gb_a_median", gedeckelt: "gb_a_gedeckelt",
    angehoben: "gb_a_angehoben", unveraendert: "gb_a_unveraendert",
    sammelt_noch: "gb_a_sammelt", keine_messung: "gb_a_keine_messung",
    keine_kanaele: "gb_a_keine_kanaele",
  };
  if (!d.automatik) {
    stand.textContent = t("gb_a_aus")
      + (rat.handeln ? " " + t("gb_a_wuerde", { satz: rat.satz_ppm }) : "");
  } else if (rat.grund === "unveraendert") {
    // Nichts zu tun — und der Satz, der steht, ist der, den sie gesetzt hat.
    stand.textContent = t("gb_a_unveraendert", { satz: d.jetzt_ppm });
  } else if (GRUENDE[rat.grund] && !rat.handeln) {
    // Eingeschaltet, greift aber noch nicht: fehlende Messtage, keine
    // Messung, keine Kanäle. Das gehört gesagt und nicht von einer älteren
    // Erfolgsmeldung überdeckt.
    stand.textContent = t(GRUENDE[rat.grund], { satz: rat.satz_ppm || 0 });
  } else {
    stand.textContent = t("gb_a_wuerde", { satz: rat.satz_ppm || 0 });
  }
}

async function ladeNetzgebuehren() {
  try {
    zeichneNetzgebuehren(await api("/lightning/netzgebuehren"));
  } catch (e) {
    if (e && e.abgemeldet) return;
    // Eine fehlende Netzmessung darf die Gebührenansicht nicht mitnehmen —
    // das Formular darunter funktioniert ohne sie vollständig.
    $("#gb-netz-zahlen").textContent = t("gb_netz_nie");
  }
}

async function netzgebuehrenMessen() {
  const knopf = $("#gb-messen");
  const meldung = $("#gb-netz-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  $("#gb-netz-zahlen").textContent = t("gb_messen_laeuft");
  try {
    await api("/lightning/netzgebuehren/messen", "POST", {}, FRIST_MESSUNG_MS);
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  }
  // Der Graph wird im Hintergrund gelesen. Nachfragen, bis er durch ist —
  // eine Anfrage so lange offenzuhalten wäre der falsche Weg.
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    let d;
    try { d = await api("/lightning/netzgebuehren"); } catch (e) { break; }
    zeichneNetzgebuehren(d);
    if (!d.misst_gerade) break;
  }
  knopf.disabled = false;
}

function medianUebernehmen() {
  const heute = (NETZGEBUEHREN || {}).heute;
  if (!heute || heute.median_ppm === null) return;
  $("#gb-satz").value = heute.median_ppm;
  $("#gb-netz-meldung").textContent = t("gb_uebernommen");
}

async function gebuehrenautomatikUmschalten() {
  const schalter = $("#gb-automatik");
  const meldung = $("#gb-netz-meldung");
  schalter.disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/gebuehrenautomatik", "POST",
              { automatik: schalter.checked });
    await ladeNetzgebuehren();
  } catch (e) {
    if (e && e.abgemeldet) return;
    schalter.checked = !schalter.checked;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    schalter.disabled = false;
  }
}

function fuelleGebuehrenauswahl(kanaele) {
  const feld = $("#gb-kanal");
  const vorher = feld.value;
  feld.textContent = "";
  const alle = document.createElement("option");
  alle.value = "";
  alle.textContent = t("gb_alle");
  feld.append(alle);
  for (const k of kanaele || []) {
    // Ohne Kanalpunkt laesst sich der Kanal nicht ansprechen -- und ein
    // Eintrag mit leerem Wert wuerde beim Absenden als "alle Kanaele"
    // gelesen. Wer einen einzelnen Kanal teurer machen wollte, haette
    // stattdessen den ganzen Knoten umgestellt.
    if (!k.punkt) continue;
    const o = document.createElement("option");
    o.value = k.punkt;
    // Der Anteil steht bewusst dabei: er ist der Grund, aus dem man an
    // diesem Kanal ueberhaupt drehen will.
    o.textContent = (k.gegenstelle || kurz(k.kennung || ""))
      + "  ·  " + Math.round(k.anteil_hier * 100) + "%";
    feld.append(o);
  }
  if (vorher) feld.value = vorher;
}

async function gebuehrenSetzen() {
  const knopf = $("#gb-setzen");
  const meldung = $("#gb-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  const kanalpunkt = $("#gb-kanal").value;
  try {
    const d = await api("/lightning/gebuehren", "POST", {
      basis_msat: Number($("#gb-basis").value || 0),
      satz_ppm: Number($("#gb-satz").value || 0),
      kanalpunkt,
    });
    meldung.textContent = t(d.fuer_alle ? "gb_gesetzt_alle" : "gb_gesetzt_einer");
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    knopf.disabled = false;
  }
}

/* ── Kanalsicherung ─────────────────────────────────────────────────────── */

async function ladeSicherung() {
  const feld = $("#w-sicherung");
  let d;
  try {
    d = await api("/lightning/sicherung");
  } catch (e) {
    if (e && e.abgemeldet) return;
    feld.classList.add("hidden");
    return;
  }
  feld.classList.remove("hidden");
  $("#sich-url").value = d.ziel.url || "";
  $("#sich-benutzer").value = d.ziel.benutzer || "";
  zeichneSicherungsstand(d);
}

function zeichneSicherungsstand(d) {
  const ziel = $("#sich-stand");
  ziel.textContent = "";
  const stand = d.stand || {};
  const kanaele = d.kanaele;

  if (kanaele === null || kanaele === undefined) {
    // Lightning laeuft noch nicht -- frueher stand hier gar nichts, und der
    // Kasten sah aus wie einer, der nicht laedt. Das Ziel schon jetzt
    // einzutragen ist ausdruecklich sinnvoll: dann sichert der Knoten vom
    // ersten Kanal an, statt erst wenn jemand daran denkt.
    ziel.append(hinweis(t("sich_ohne_wallet"), ""));
    $("#sich-laden").disabled = true;
    return;
  }
  $("#sich-laden").disabled = false;
  if (kanaele === 0) {
    ziel.append(hinweis(t("sich_ohne_kanaele"), ""));
  } else if (d.aktuell) {
    ziel.append(hinweis(t("sich_aktuell", {
      kanaele, wann: datumZeit((stand.zeitpunkt || 0) * 1000) }), "ok"));
  } else if (!stand.zeitpunkt) {
    // Nie gesichert bei offenen Kanaelen ist der schlimmste Fall und
    // gehoert auch so gefaerbt.
    ziel.append(hinweis(t("sich_nie", { kanaele }), "bad"));
  } else {
    ziel.append(hinweis(t("sich_rueckstand", { kanaele }), "bad"));
  }
  if (stand.fehler) {
    // Kennt die Anwendung den Fall, liegt hier ein Schluessel -- und daraus
    // wird ein Satz, der sagt, was zu tun ist. Sonst der Wortlaut des
    // Servers; aeltere Staende sehen ohnehin so aus.
    const fehler = Object.prototype.hasOwnProperty.call(I18N.en, stand.fehler)
      ? t(stand.fehler) : stand.fehler;
    ziel.append(hinweis(t("sich_fehler_zuletzt", { fehler }), "warn"));
  }
  if (d.ziel.url) {
    ziel.append(hinweis(t("sich_ziel_ist", d.ziel), ""));
  }
}

async function ladeSicherungHerunter() {
  const knopf = $("#sich-laden");
  const meldung = $("#sich-lade-meldung");
  knopf.disabled = true;
  meldung.textContent = "";
  try {
    // Bewusst ueber fetch statt ueber einen Link: sonst zeigt der Browser bei
    // einem Fehler die rohe JSON-Antwort an, statt dass hier ein Satz steht.
    const antwort = await fetch("/api/lightning/sicherung/datei",
                                { credentials: "same-origin" });
    if (!antwort.ok) {
      const d = await antwort.json().catch(() => ({}));
      const m = (d.detail && d.detail.meldung) || "";
      meldung.textContent = m ? t(m) : t("e_fehler");
      return;
    }
    const blob = await antwort.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "channel.backup";
    a.click();
    URL.revokeObjectURL(url);
    meldung.textContent = t("sich_geladen");
  } catch (e) {
    meldung.textContent = t("err_net");
  } finally {
    knopf.disabled = false;
  }
}

async function sicherungszielSetzen(entfernen) {
  const meldung = $("#sich-ziel-meldung");
  $("#sich-einrichten").disabled = true;
  $("#sich-entfernen").disabled = true;
  meldung.textContent = "";
  try {
    await api("/lightning/sicherung/ziel", "POST", entfernen
      ? { url: "", benutzer: "", passwort: "" }
      : { url: $("#sich-url").value.trim(),
          benutzer: $("#sich-benutzer").value.trim(),
          passwort: $("#sich-passwort").value });
    $("#sich-passwort").value = "";
    if (entfernen) { $("#sich-url").value = ""; $("#sich-benutzer").value = ""; }
    meldung.textContent = t(entfernen ? "sich_entfernt" : "sich_eingerichtet");
    await ladeSicherung();
  } catch (e) {
    if (e && e.abgemeldet) return;
    const d = e.detail || {};
    meldung.textContent = d.meldung ? t(d.meldung, d) : t("e_fehler");
  } finally {
    $("#sich-einrichten").disabled = false;
    $("#sich-entfernen").disabled = false;
  }
}

/* ── Anmeldung ──────────────────────────────────────────────────────────── */
let KONTO_VORHANDEN = false;
// Ob ein Ausweisdienst eingerichtet ist -- und ob DIESER Aufruf sich auch
// noch oertlich mit Passwort anmelden darf. Beides kommt aus /api/zustand;
// die Oberflaeche raet es nicht.
let OIDC_DA = false;
let LOKAL_MOEGLICH = true;
// Kommt aus /api/zustand. Vorbelegt, damit die Meldung auch dann einen Satz
// ergibt, wenn der Abruf gerade nicht durchkam.
let PASSWORT_MIN = 10;

function zeigeTor() {
  $("#gate").classList.remove("hidden");
  $("#wizard").classList.add("hidden");
  $("#app").classList.add("hidden");
  $("#karte-hintergrund").classList.add("hidden");
  // Der Ausweisdienst oben, das Passwortfeld darunter -- und Letzteres nur
  // dort, wo der Server es auch annimmt. Ein Anmeldefenster, das immer
  // abgewiesen wird, ist schlimmer als gar keines.
  $("#g-oidc").classList.toggle("hidden", !OIDC_DA);
  $("#g-oidc-trenner").classList.toggle("hidden", !OIDC_DA || !LOKAL_MOEGLICH);
  $("#g-form").classList.toggle("hidden", OIDC_DA && !LOKAL_MOEGLICH);

  const neu = !KONTO_VORHANDEN;
  $("#g-title").textContent = t(neu ? "g_neu_title" : "g_an_title");
  $("#g-lead").textContent = t(neu ? "g_neu_lead" : "g_an_lead");
  $("#g-submit").textContent = t(neu ? "g_anlegen" : "g_anmelden");
  $("#g-pass").autocomplete = neu ? "new-password" : "current-password";
  $("#g-pass").placeholder = neu ? t("g_pass_hint") : "";
  $("#g-err").textContent = "";
  anmeldungsergebnisZeigen();
  // Nur im Klartext und nur ausserhalb von localhost: wer ueber 127.0.0.1
  // zugreift, hat kein Netz dazwischen, das mitlesen koennte.
  const lokal = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
  const warnen = location.protocol !== "https:" && !lokal;
  $("#g-tls").textContent = warnen ? t("unverschluesselt") : "";
}

// Sichtbar ist genau eine der grossen Sektionen -- oder eben keine. Der
// zweite Fall ist der schwarze Bildschirm und darf nie stehen bleiben.
function nichtsSichtbar() {
  return ["#gate", "#wizard", "#app", "#notfall"].every((wahl) => {
    const el = $(wahl);
    return !el || el.classList.contains("hidden");
  });
}

function zeigeNotfall(einzelheit) {
  $("#gate").classList.add("hidden");
  $("#wizard").classList.add("hidden");
  $("#app").classList.add("hidden");
  const karte = $("#karte-hintergrund");
  if (karte) karte.classList.add("hidden");
  $("#notfall").classList.remove("hidden");
  $("#nf-title").textContent = t("nf_title");
  $("#nf-lead").textContent = t("nf_lead");
  $("#nf-detail").textContent = einzelheit || "";
  $("#nf-erneut").textContent = t("nf_erneut");
}

// Der Rueckhalt fuer alles, was ich nicht vorhergesehen habe. Er greift nur,
// wenn wirklich nichts zu sehen ist -- ein Fehler mitten im laufenden Betrieb
// soll die Ansicht nicht wegreissen, die gerade brauchbare Zahlen zeigt.
function notfallWennLeer(was, grund) {
  log_fehler(was, grund);
  if (!nichtsSichtbar()) return;
  try {
    zeigeNotfall(String((grund && grund.message) || grund || ""));
  } catch (e) {
    // Selbst das ging schief: dann wenigstens irgendein Wort auf der Seite.
    document.body.textContent = "SatoshiCortex: " + String(grund);
  }
}

window.addEventListener("unhandledrejection", (e) => {
  notfallWennLeer("unbehandelte Zusage", e.reason);
});
window.addEventListener("error", (e) => {
  notfallWennLeer("unbehandelter Fehler", e.error || e.message);
});

/* Was nach der Rueckkehr vom Ausweisdienst zu sagen ist.

   Der Rueckweg landet auf "/?anmeldung=<grund>". Ohne diese Auswertung saehe
   jemand, den Pocket ID abgelehnt hat, einfach wieder die Anmeldeseite --
   ohne ein Wort dazu, und wuerde es fuer kaputt halten. */
function anmeldungsergebnisZeigen() {
  let grund = "";
  try {
    grund = new URLSearchParams(location.search).get("anmeldung") || "";
  } catch (e) { return; }
  if (!grund) return;
  const bekannt = ["abgelehnt", "abgelaufen", "ungueltig"];
  $("#g-err").textContent = t(bekannt.includes(grund)
    ? "g_oidc_" + grund : "g_oidc_ungueltig");
  // Die Frage wieder aus der Adresse nehmen, sonst steht die Meldung nach
  // jedem Neuladen wieder da.
  try {
    history.replaceState(null, "", location.pathname);
  } catch (e) { /* ohne Verlauf eben nicht -- die Meldung stimmt trotzdem */ }
}

async function torAbsenden(ereignis) {
  ereignis.preventDefault();
  const benutzer = $("#g-user").value.trim();
  const passwort = $("#g-pass").value;
  $("#g-err").textContent = "";
  try {
    await api(KONTO_VORHANDEN ? "/anmelden" : "/konto/anlegen", "POST",
              { benutzer, passwort });
    $("#g-pass").value = "";
    SITZUNG_VERLOREN = false;
    await nachAnmeldung();
  } catch (e) {
    const d = e.detail;
    // Zu kurze Passwörter fängt schon die Prüfung im Server ab (422).
    const schluessel = (d && d.meldung) ? d.meldung
      : (Array.isArray(d) ? "passwort_zu_kurz" : null);
    $("#g-err").textContent = schluessel
      ? t(schluessel, { mindestens: PASSWORT_MIN, ...(d || {}) })
      : t("err_net");
  }
}

async function nachAnmeldung() {
  $("#gate").classList.add("hidden");
  const status = await api("/status");
  if (status.eingerichtet) {
    // Die Frischesperren loesen und die Ansicht neu aufbauen, auf der der
    // Nutzer wirklich steht.
    //
    // Ohne das kam er nach einer abgelaufenen Sitzung auf eine Seite mit
    // Zahlen von vor zwoelf Stunden zurueck -- die Lader ueberspringen einen
    // Abruf, solange ihre Daten "frisch" sind, und frisch heisst hier nur
    // "juenger als der Abstand", nicht "aus dieser Sitzung". Derselbe Griff
    // steht beim Sprachwechsel, aus demselben Grund.
    KARTE_STAND = LN_STAND = BEITRAG_STAND = AUSW_STAND = 0;
    await zeigeUebersicht();
    return zeigeAnsicht(ANSICHT);
  }
  const bekannt = status.einrichtung && status.einrichtung.schritt;
  if (bekannt && SCHRITTE.includes(bekannt)) S.schritt = bekannt;
  $("#app").classList.add("hidden");
  $("#wizard").classList.remove("hidden");
  await beimBetreten();
}

/* ── Start ──────────────────────────────────────────────────────────────── */
async function start() {
  applyI18n();

  $("#nf-erneut").addEventListener("click", () => location.reload());
  $("#lgi-kennung-ok").addEventListener("click", kennungUebernehmen);
  $("#lgi-kopieren").addEventListener("click", () => kopiere(
    $("#lgi-uri"), $("#lgi-meldung"), "lgi_kopiert"));
  $("#sd-schaetzen").addEventListener("click", sendenSchaetzen);
  $("#sd-senden").addEventListener("click", sendenAusloesen);
  $("#rq-erstellen").addEventListener("click", rechnungErstellen);
  $("#rq-kopieren").addEventListener("click", rechnungKopieren);
  $("#rq-storno").addEventListener("click", () => rechnungZurueckziehen(
    RQ_KENNUNG, $("#rq-storno"), $("#rq-meldung")));
  $("#sd-kopieren").addEventListener("click", () => kopiere(
    $("#sd-txid"), $("#sd-kopiert"), "lgi_kopiert"));
  // Jede Aenderung nimmt die Freigabe zurueck. Sonst schaetzte man das eine
  // und schickte das andere.
  for (const feld of sendenFelder()) {
    feld.addEventListener("input", sendenSperren);
    feld.addEventListener("change", sendenSperren);
  }
  // Lightning zahlen und Kanal oeffnen -- durchgehend Pfeilfunktionen,
  // siehe die Falle vom 11.09.2026.
  $("#zl-lesen").addEventListener("click", () => rechnungLesen());
  $("#zl-zahlen").addEventListener("click", () => rechnungZahlen());
  $("#ko-pruefen").addEventListener("click", () => kanalPruefen());
  $("#ko-ansehen").addEventListener("click", () => gegenstelleAnsehen());
  $("#wt-eintragen").addEventListener("click", () => wachturmEintragen());
  $("#us-los").addEventListener("click", () => umschichten());
  $("#ks-los").addEventListener("click", () => kanalSchliessen());
  $("#wt-eigen-kopieren").addEventListener("click", () => kopiere(
    $("#wt-eigen-uri"), $("#wt-eigen-kopiert"), "lgi_kopiert"));
  // Das Erzwingen zeigt sofort, was es bedeutet -- nicht erst hinterher.
  $("#ks-erzwingen").addEventListener("change", (e) => {
    $("#ks-warnung").classList.toggle("hidden", !e.target.checked);
  });
  $("#ko-oeffnen").addEventListener("click", () => kanalOeffnen());
  // Jede Aenderung nimmt die Freigabe zurueck. Sonst liest man das eine und
  // bezahlt das andere -- derselbe Griff wie beim On-Chain-Senden.
  for (const feld of [$("#zl-rechnung"), $("#zl-betrag")]) {
    feld.addEventListener("input", () => zahlenSperren());
    feld.addEventListener("change", () => zahlenSperren());
  }
  for (const feld of [$("#ko-gegenstelle"), $("#ko-betrag"), $("#ko-privat"),
                      ...$$('input[name="ko-tempo"]')]) {
    feld.addEventListener("input", () => kanalSperren());
    feld.addEventListener("change", () => kanalSperren());
  }
  $("#pin-einrichten").addEventListener("click", pinEinrichten);
  $("#pin-aendern").addEventListener("click", pinAendern);
  $("#pin-entfernen").addEventListener("click", pinEntfernen);
  $("#unt-knopf").addEventListener("click", unterschriftLeisten);
  $("#unt-kopieren").addEventListener("click", () => kopiere(
    $("#unt-feld"), $("#unt-meldung"), "lgi_kopiert"));

  const streifen = $(".welt-streifen");
  const diaKasten = $("#a-diagramm");
  if (diaKasten && window.ResizeObserver) {
    new ResizeObserver(diaNeuZeichnenBald).observe(diaKasten);
  }
  if (streifen && window.ResizeObserver) {
    new ResizeObserver(messeWeltstreifen).observe(streifen);
  }
  addEventListener("resize", weltNeuMessen);
  addEventListener("scroll", weltNeuMessen, { passive: true });
  const klapp = $("#w-klapp");
  if (klapp) {
    let zu = false;
    try { zu = localStorage.getItem("satcortex-welt-zahlen") === "aus"; } catch (e) { /* ohne Speicher: offen */ }
    weltStreifenKlappen(zu, false);
    klapp.addEventListener("click", () =>
      weltStreifenKlappen(!$(".welt-streifen").classList.contains("zu"), true));
  }

  $$("[data-setlang]").forEach((b) => b.addEventListener("click", async () => {
    LANG = b.dataset.setlang;
    localStorage.setItem("satcortex-lang", LANG);
    applyI18n();
    if (!$("#gate").classList.contains("hidden")) return zeigeTor();
    await beimBetreten();
    if ($("#app").classList.contains("hidden")) return;
    // applyI18n() erreicht nur, was fest in der Vorlage steht. Alles, was
    // gezeichnet wird -- Netz, Beitrag, Karte, Mempool, Bloecke, Lightning --
    // entsteht in JavaScript und traegt seine Sprache aus dem Augenblick des
    // Zeichnens. Die vier Lader haben zudem eine Nachlade-Sperre und
    // ueberspringen den Aufruf, wenn ihre Daten noch frisch sind. Beides
    // zusammen sorgte dafuer, dass nach dem Umschalten der groessere Teil der
    // Oberflaeche deutsch blieb -- bis zu einer Minute lang, und die Ansicht,
    // auf der man gerade stand, sogar dauerhaft.
    //
    // Also: Sperren loesen und die Ansicht neu zeichnen, auf der der Nutzer
    // wirklich steht. Frische Daten sind hier Nebenwirkung, nicht Zweck --
    // gewollt ist der Text in der neuen Sprache.
    KARTE_STAND = LN_STAND = BEITRAG_STAND = AUSW_STAND = 0;
    // Die Seed-Felder werden bewusst nicht neu gebaut -- wer schon getippt
    // hat, soll seine Woerter behalten. Ihre Beschriftung muss trotzdem mit.
    whBeschriften();
    await zeigeUebersicht();
    zeigeAnsicht(ANSICHT);
  }));

  $("#btn-next").addEventListener("click", weiter);
  $("#btn-back").addEventListener("click", zurueck);
  for (const [id, feld] of [["#n-tor", "tor"], ["#n-ipv4", "ipv4"],
                            ["#n-ipv6", "ipv6"], ["#n-pause", "pause"],
                            ["#n-ankuendigen", "ankuendigen"]]) {
    $(id).addEventListener("change", (e) => {
      S[feld] = e.target.checked;
      netzwegeFolgen();
    });
  }
  $("#l-upload").addEventListener("input", (e) => {
    S.upload = parseInt(e.target.value, 10);
    vorschau();
  });

  $("#g-form").addEventListener("submit", torAbsenden);
  // Als Pfeilfunktion, wie jeder Zuhoerer hier -- siehe den Fehler vom
  // 11.09.2026 bei walletSperren.
  $("#g-oidc-knopf").addEventListener("click", () => {
    // Ein gewoehnlicher Seitenwechsel, kein fetch: der Ausweisdienst will den
    // Browser sehen, nicht unser JavaScript. Ueber fetch endete die Umleitung
    // im Nichts.
    location.href = "/api/anmeldung/oidc/start";
  });
  $("#n-adresse").addEventListener("input", (e) => { S.adresse = e.target.value; });
  $$('input[name="n-sicht"]').forEach((r) =>
    r.addEventListener("change", (e) => {
      S.sichtbarkeit = e.target.value;
      netzwegeFolgen();
    }));
  $("#n-rpc-an").addEventListener("change", (e) => {
    S.rpcAn = e.target.checked;
    walletFolgen();
  });
  $("#n-rpc-netz").addEventListener("input", (e) => {
    S.rpcNetz = e.target.value;
    walletFolgen();
  });
  newsFolgen();
  kursAblesenFolgen();
  // Einmal beim Start, damit der Zaehler an der Seitenleiste stimmt, ohne
  // dass man den Reiter geoeffnet haben muss. Danach nur noch beim Wechsel
  // dorthin -- ein Feed, der sich im Minutentakt selbst nachlaedt, waere
  // Verkehr fuer nichts: geholt wird ohnehin nur stuendlich.
  ladeNews(true);

  // Kopf und Seitenleiste. Ein Zuhoerer je Leiste statt einer je Knopf.
  $$(".seitenleiste button").forEach((b) =>
    b.addEventListener("click", () => zeigeAnsicht(b.dataset.ansicht)));
  // Ein Klick auf die Karte -- aber NUR in der Weltansicht. In allen anderen
  // ist sie Hintergrund, und ein Hintergrund, der sich anklicken laesst,
  // waere eine Falle.
  $("#karte-hintergrund").addEventListener("click", (e) => {
    if (ANSICHT !== "welt") return;
    const kuerzel = landkuerzelAus(e.target);
    if (kuerzel) oeffneLand(kuerzel);
  });
  $("#wl-zurueck").addEventListener("click", schliesseLand);
  $("#wl-karte").addEventListener("click", (e) => {
    const pfad = e.target.closest && e.target.closest("path[data-gebiet]");
    // Auf die leere Flaeche geklickt heisst: Auswahl aufheben.
    waehleGebiet(pfad ? pfad.dataset.gebiet : 0);
  });
  // Weg mit Escape. Wer eine Auflage oeffnet, erwartet das.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && LAND_OFFEN) schliesseLand();
  });
  $("#e-adresse-speichern").addEventListener("click", speichereAdresse);
  $("#e-pruefen").addEventListener("click", pruefeErreichbarkeit);
  $("#p-neu").addEventListener("click", () => ladeLogs(true));
  $("#w-erzeugen").addEventListener("click", walletSeedErzeugen);
  $("#w-weiter").addEventListener("click", walletZurGegenprobe);
  $("#w-anlegen").addEventListener("click", walletAnlegen);
  $("#kn-speichern").addEventListener("click", knotennameSpeichern);
  $("#ko-verbinden").addEventListener("click", gegenstelleVerbinden);
  // In einer Pfeilfunktion, NICHT direkt. walletSperren hat seit dem
  // 10.09.2026 Parameter -- direkt angehaengt bekaeme es das Klick-Ereignis
  // als erstes Argument, und $(ereignis) wirft einen SyntaxError, weil
  // "[object PointerEvent]" kein gueltiger Selektor ist. Der Knopf tat dann
  // gar nichts, ohne ein Wort.
  //
  // Aus dem Betrieb, 11.09.2026: "also hier passiert nix wenn ich auf wallet
  // sperren druecke". Genau das.
  $("#tg-sperren").addEventListener("click", () => walletSperren());
  $("#tg-loeschen").addEventListener("click", walletTilgen);
  $("#ez-holen").addEventListener("click", () => einzahladresseHolen(false));
  $("#ez-neue").addEventListener("click", () => einzahladresseHolen(true));
  // Eine andere Adressform heisst eine andere Adresse -- sofort, nicht erst
  // nach einem zweiten Klick, den niemand erwartet.
  document.querySelectorAll('input[name="ez-art"]').forEach((feld) => {
    feld.addEventListener("change", () => {
      if (!$("#ez-adresse").classList.contains("hidden")) {
        einzahladresseHolen(false);
      }
    });
  });
  $("#ez-kopieren").addEventListener("click", adresseKopieren);
  $("#gb-setzen").addEventListener("click", gebuehrenSetzen);
  $("#gb-messen").addEventListener("click", netzgebuehrenMessen);
  $("#gb-uebernehmen").addEventListener("click", medianUebernehmen);
  $("#gb-automatik").addEventListener("change", gebuehrenautomatikUmschalten);
  $("#sich-laden").addEventListener("click", ladeSicherungHerunter);
  $("#sich-einrichten").addEventListener("click", () => sicherungszielSetzen(false));
  $("#sich-entfernen").addEventListener("click", () => sicherungszielSetzen(true));
  for (const feld of $$('input[name="w-weg"]')) {
    feld.addEventListener("change", walletAutoFolge);
  }
  for (const feld of $$('input[name="wh-weg"]')) {
    feld.addEventListener("change", whAutoFolge);
  }
  for (const feld of $$('input[name="ew-weg"]')) {
    feld.addEventListener("change", entsperrwegWahlFolge);
  }
  $("#ew-wechseln").addEventListener("click", entsperrwegWechseln);
  $("#ew-sperren").addEventListener("click",
    () => walletSperren("#ew-sperren", "#ew-sperr-meldung"));
  $("#w-zurueckholen").addEventListener("click", walletZurueckholen);
  $("#wh-abbrechen").addEventListener("click", () => {
    // Die Woerter bleiben nicht im Formular stehen, wenn jemand weggeht.
    whWoerterLeeren();
    walletSchritt("start");
  });
  $("#wh-starten").addEventListener("click", walletWiederherstellen);
  $("#wh-datei").addEventListener("change", whDateiGewaehlt);
  for (const feld of $$("input[name=wh-quelle]")) {
    feld.addEventListener("change", whQuelleFolge);
  }
  $("#a-block-suchen").addEventListener("click", () => blockNachschlagen());
  $("#a-block-null").addEventListener("click", () => blockNachschlagen(0));
  $("#a-blockhoehe").addEventListener("keydown", (e) => {
    if (e.key === "Enter") blockNachschlagen();
  });
  for (const feld of ["sat", "btc", "fiat"]) {
    const e = $("#rn-" + feld);
    if (e) e.addEventListener("input", () => rechnerRechnen(feld));
  }
  $("#a-kachel-holen").addEventListener("click", ladeKacheln);
  const kachelflaeche = $("#a-kacheln");
  if (kachelflaeche) {
    kachelflaeche.addEventListener("pointermove", kachelZeigen);
    kachelflaeche.addEventListener("pointerleave", kachelBlaseAus);
    kachelflaeche.addEventListener("click", kachelKlick);
    // Ein Canvas ist ohne Zutun nicht mit der Tastatur bedienbar. Pfeile
    // waehlen die Spalte, Eingabe klappt sie auf -- sonst waere diese
    // Ansicht nur mit der Maus zu haben.
    kachelflaeche.addEventListener("keydown", (e) => {
      const n = (KACHEL_DATEN && KACHEL_DATEN.bloecke || []).length;
      if (!n) return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const schritt = e.key === "ArrowRight" ? 1 : -1;
        const jetzt = KACHEL_OFFEN === null ? -1 : KACHEL_OFFEN;
        const neu = Math.max(0, Math.min(n - 1, jetzt + schritt));
        if (neu !== KACHEL_OFFEN) { KACHEL_OFFEN = null; oeffneKachelBlock(neu); }
      } else if (e.key === "Escape" && KACHEL_OFFEN !== null) {
        oeffneKachelBlock(KACHEL_OFFEN);      // schliesst
      }
    });
    if (window.ResizeObserver) {
      new ResizeObserver(() => { if (KACHEL_DATEN) zeichneKacheln(); })
        .observe(kachelflaeche.parentElement);
    }
  }
  $("#sipr-pruefen").addEventListener("click", () => sicherungKopiePruefen(false));
  $("#sipr-ziel").addEventListener("click", () => sicherungKopiePruefen(true));
  $("#w-entsperren").addEventListener("click", walletEntsperren);
  $("#w-entsperren-passwort").addEventListener("keydown", (e) => {
    if (e.key === "Enter") walletEntsperren();
  });
  $("#w-abgeschrieben").addEventListener("change", (e) => {
    // Der Haken ist keine Formalie: er ist der Moment, in dem jemand sag
    // "ich habe sie". Danach sind sie weg.
    $("#w-weiter").disabled = !e.target.checked;
  });
  for (const id of ["#e-tor", "#e-pause", "#e-ipv4", "#e-ipv6",
                    "#e-ankuendigen"]) {
    $(id).addEventListener("change", einstellungenFolgen);
  }
  $("#e-adresse").addEventListener("input", einstellungenFolgen);
  $("#e-rpc-an").addEventListener("change", zeichneRpcZugang);
  $("#e-rpc-speichern").addEventListener("click", rpcFreigabeSpeichern);
  $("#e-rpc-kopieren").addEventListener("click", () => kopiere(
    $("#e-rpc-feld"), $("#e-rpc-meldung"), "lgi_kopiert"));
  // Die Wahl oben wirkt auf die Haekchen darunter -- sofort sichtbar, nicht
  // erst beim Speichern.
  $$('input[name="e-ln-sicht"]').forEach(
    (r) => r.addEventListener("change", einstellungenFolgen));
  $("#a-suchen").addEventListener("click", verfolgeTx);
  $("#a-txid").addEventListener("keydown", (e) => {
    if (e.key === "Enter") verfolgeTx();
  });
  $("#a-ad-los").addEventListener("click", adresseAbfragen);
  $("#a-adresse").addEventListener("keydown", (e) => {
    if (e.key === "Enter") adresseAbfragen();
  });
  $("#a-ad-abbrechen").addEventListener("click", adresseAbbrechen);
  // Der Fortschritt aendert sich staendig. Eine Anzeige, die man von Hand neu
  // laden muss, ist bei einem Vorgang ueber Tage keine Anzeige.
  let laeuftSchon = false;
  setInterval(async () => {
    // Nur, wenn die Anwendung sichtbar ist und nicht gerade jemand in den
    // Einstellungen tippt -- ein Nachladen wuerde sonst mitten im Feld
    // dazwischenfunken.
    if ($("#app").classList.contains("hidden") || ANSICHT === "einstellungen")
      return;
    // Und nur einer zur Zeit. Waehrend des Abgleichs braucht /status bis zu
    // fuenfzehn Sekunden; ohne diese Sperre liefen bei einem Takt von zehn
    // Sekunden mehrere gleichzeitig und drueckten den Knoten weiter.
    if (laeuftSchon) return;
    laeuftSchon = true;
    try { await zeigeUebersicht(); } finally { laeuftSchon = false; }
  }, 10000);

  // Wer angemeldet ist, hat kein Anmeldeproblem. Ihm nach einem Aussetzer die
  // Anmeldemaske hinzustellen waere schlicht gelogen -- deshalb wird das hier
  // festgehalten, bevor es schiefgehen kann.
  let war_angemeldet = false;

  try {
    const z = await api("/zustand");
    KONTO_VORHANDEN = z.konto_vorhanden;
    OIDC_DA = !!z.oidc;
    LOKAL_MOEGLICH = z.lokal_moeglich !== false;
    if (z.passwort_mindestlaenge) PASSWORT_MIN = z.passwort_mindestlaenge;
    if (z.ablage_bereit === false) {
      zeigeTor();
      $("#g-err").textContent = t("ablage_nicht_bereit", { pfad: z.ablage_pfad });
      $("#g-submit").disabled = true;
      return;
    }
    // Immer sichtbar, auch vor der Anmeldung: sonst ist die Frage "welche
    // Fassung laeuft hier eigentlich?" nur ueber Dateigroessen zu beantworten.
    if (z.version) $("#version").textContent = z.version;
    war_angemeldet = !!z.angemeldet;
    // "return await", nicht "return". Ohne das await verlaesst die abgelehnte
    // Zusage die try-Klammer, BEVOR sie ausgewertet wird -- der catch unten
    // greift dann nicht. Am 03.09.2026 war das der schwarze Bildschirm:
    // nachAnmeldung() blendet zuerst die Anmeldeseite aus und faellt dann
    // beim Aufruf von /status hin. Ausgeblendet war ausgeblendet, eingeblendet
    // wurde nichts mehr, und die Seite blieb leer.
    if (z.angemeldet) return await nachAnmeldung();
  } catch (e) {
    log_fehler("start", e);
    if (war_angemeldet)
      return zeigeNotfall(String((e && e.message) || e || ""));
    $("#g-err").textContent = t("err_net");
  }
  zeigeTor();
}

document.addEventListener("DOMContentLoaded", start);
