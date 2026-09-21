import sys
from pathlib import Path

# Das Paket liegt unter app/backend/, die Tests darunter.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Kein Test telefoniert nach draussen ────────────────────────────────────
#
# Gefunden am 10.09.2026: die Pruefung schlug fehl, weil in
# test_nachrichten.py zwei Abrufe gezaehlt wurden statt einem. Der zweite
# gehoerte gar nicht dazu -- er kam aus einem Hintergrundfaden eines FRUEHER
# gelaufenen Testfalls, der die Attrappe des spaeteren traf. Im Protokoll
# stand daneben, was noch schlimmer ist:
#
#   Nachrichten (Blockmedia): URLError: <urlopen error [Errno -3]
#   Temporary failure in name resolution>
#
# Also ein echter Abruf ins Internet, mitten in der Pruefung. Auf einem
# Rechner mit Netz waere er geglueckt und niemandem aufgefallen -- die
# Pruefung haette dann das Wetter mitgeprueft. In test_nachrichten.py steht
# der Satz sogar schon: "Ein Test, der nach draussen telefoniert, prueft das
# Wetter mit."
#
# Diese Sperre macht daraus einen lauten Fehlschlag statt einer stillen
# Abhaengigkeit. Wer eine Verbindung BRAUCHT, ersetzt sie selbst -- das
# gewinnt, weil monkeypatch spaeter greift.
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402

import pytest  # noqa: E402

# Der eigene Rechner ist nicht "draussen". Zwei Testdateien starten mit gutem
# Grund einen echten kleinen Server und reden ueber einen echten Socket mit
# ihm -- test_sicherung.py sagt selbst warum: "geprueft wird, was ueber die
# Leitung geht. Eine Attrappe bestaetigt, was ich mir beim Schreiben gedacht
# habe."
EIGENER_RECHNER = ("127.0.0.1", "::1", "localhost")

# Die Namen aus dem Compose-Netz. Im Pruefstand gibt es sie nicht, und die
# Anwendung MUSS damit umgehen koennen: "bitcoind antwortet nicht" ist der
# Normalzustand, solange der Container nicht laeuft.
INTERNE_NAMEN = ("bitcoind", "lnd", "tor")

# Wohin die Pruefung ueberall hinauswollte. Am 10.09.2026 waren das GitHub
# (Versionsabgleich), Bitstamp und Kraken (Kurs) und saemtliche
# Nachrichtenquellen -- bei jedem Lauf, auf jedem Rechner mit Netz.
NACH_DRAUSSEN = []


@pytest.fixture(autouse=True)
def kein_netz(monkeypatch):
    """Keine einzige Verbindung verlaesst diesen Rechner.

    Gefunden am 10.09.2026: die Pruefung schlug in der CI fehl, weil in
    test_nachrichten.py zwei Abrufe gezaehlt wurden statt einem. Der zweite
    gehoerte nicht dazu -- er kam aus einem Hintergrundfaden eines FRUEHER
    gelaufenen Testfalls und landete in der Attrappe des spaeteren. Daneben
    stand im Protokoll, was schwerer wiegt:

      Nachrichten (Blockmedia): URLError: <urlopen error [Errno -3]
      Temporary failure in name resolution>

    Ein echter Abruf ins Internet, mitten in der Pruefung. Hier auf dem Mac
    glueckte er und fiel niemandem auf; in der CI ohne DNS nicht. Damit sah
    dieselbe Pruefung auf zwei Rechnern verschieden aus -- und genau das hat
    einen gruenen Lauf hier und einen roten dort erzeugt.

    Gescheitert wird deshalb mit dem Fehler, den das Betriebssystem schickt,
    wenn niemand da ist: den fangen die Aufrufer ab, und genau dieser Fall
    gehoert geprueft. Zwei Wege muessen zu -- urlopen UND der Oeffner mit
    eigenem Proxy. Den benutzt nachrichten.hole(), und genau der war es.

    Wer eine Attrappe braucht, setzt sie selbst; das gewinnt, weil
    monkeypatch spaeter greift.
    """
    echtes_urlopen = urllib.request.urlopen
    echtes_open = urllib.request.OpenerDirector.open

    def entscheide(ziel):
        adresse = str(getattr(ziel, "full_url", ziel))
        name = urllib.parse.urlsplit(adresse).hostname or ""
        if name in EIGENER_RECHNER:
            return None                       # darf wirklich laufen
        if name not in INTERNE_NAMEN:
            NACH_DRAUSSEN.append(adresse)
        raise urllib.error.URLError(
            "kein Dienst im Pruefstand" if name in INTERNE_NAMEN
            else "Attrappe statt Leitung")

    def kein_urlopen(ziel, *args, **kwargs):
        entscheide(ziel)
        return echtes_urlopen(ziel, *args, **kwargs)

    def kein_oeffner(self, ziel, *args, **kwargs):
        entscheide(ziel)
        return echtes_open(self, ziel, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", kein_urlopen)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", kein_oeffner)


@pytest.fixture
def netzversuche():
    """Wohin die Pruefung hinauswollte -- fuer den Waechter in
    test_pruefstand.py. Als Fixture und nicht per Import: pytest laedt diese
    Datei unter einem eigenen Modulnamen, ein "from tests import conftest"
    haette eine ZWEITE, leere Liste geliefert."""
    return NACH_DRAUSSEN


# ── Kein Faden ueberlebt seinen Testfall ───────────────────────────────────
#
# Dieselbe Fehlerklasse wie die Netzsperre oben, nur mit einem anderen Faden.
# Am 11.09.2026 schlug die Pruefung einmal fehl und lief danach sechzehnmal
# sauber durch -- ohne dass jemand den Fehlschlag festgehalten haette. Am
# 12.09.2026 nachgemessen: am Ende eines Testlaufs lebten 35 Faeden namens
# "htlc-strom" noch. Sie stammten aus 35 verschiedenen Testfaellen, liefen
# alle gleichzeitig weiter und schrieben in SQLite-Dateien, die pytest ihnen
# gerade wegraeumte.
#
# Der Grund ist der TestClient ohne "with": ohne ihn laeuft der Lebenszyklus
# der App nicht, und damit auch nicht das Einholen der Faeden beim
# Herunterfahren. Statt das in dreissig Testdateien einzeln nachzuruesten,
# steht es hier einmal -- so wie die Netzsperre auch.
@pytest.fixture(autouse=True)
def _faeden_einholen():
    from satcortex import api

    gebaut = []
    echtes_baue_app = api.baue_app

    def merkend(*args, **kwargs):
        app = echtes_baue_app(*args, **kwargs)
        gebaut.append(app)
        return app

    api.baue_app = merkend
    try:
        yield
    finally:
        api.baue_app = echtes_baue_app
        for app in gebaut:
            stoppen = getattr(app.state, "hintergrund_stoppen", None)
            if stoppen is not None:
                stoppen(2.0)


# ── Kein Test wartet auf ein Tor, das es hier nicht gibt ───────────────────
#
# Die Anwendung wartet nach dem Schreiben der torrc ein paar Sekunden, bis Tor
# die Adressen seiner Onion-Dienste hinterlegt hat (api.py,
# ONION_FRIST_*). Im Pruefstand laeuft kein Tor -- jeder Test, der den
# Assistenten durchlaeuft, stuende sonst zwoelf Sekunden still. Wer das
# Warten selbst prueft, setzt die Frist ausdruecklich.
@pytest.fixture(autouse=True)
def kein_warten_auf_tor(monkeypatch):
    from satcortex import api
    monkeypatch.setattr(api, "ONION_FRIST_ANFRAGE_SEKUNDEN", 0.0)
    monkeypatch.setattr(api, "ONION_FRIST_WAECHTER_SEKUNDEN", 0.0)
