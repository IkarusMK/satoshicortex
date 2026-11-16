"""Startpunkt im Container: python -m satcortex"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from typing import Optional, Tuple

import uvicorn

from . import api, settings, webtls

log = logging.getLogger("satcortex.start")


class OhneTaktrauschen(logging.Filter):
    """Die regelmaessigen Abrufe aus dem Zugriffsprotokoll heraushalten.

    Die Oberflaeche fragt alle zehn Sekunden nach, Docker prueft alle
    dreissig Sekunden die Gesundheit. Das sind rund zwanzig Zeilen je Minute,
    dauerhaft -- in einem Protokoll, in dem daneben bitcoind seinen
    Fortschritt meldet. Genau dort will man lesen koennen, und genau dort
    geht es unter.

    Gefiltert wird NUR das Erwartbare: bekannte Pfade mit einer Antwort im
    200er-Bereich. Alles andere -- Fehler, fremde Pfade, abgelehnte Zugriffe
    -- steht weiter da. Ein Protokoll, das auch Fehler verschluckt, waere
    schlimmer als eines, das rauscht.
    """

    STILL = ("/healthz", "/api/status", "/api/beitrag", "/api/lightning",
             "/api/karte", "/api/auswertung")

    def filter(self, satz: logging.LogRecord) -> bool:
        args = getattr(satz, "args", None)
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        pfad, code = args[2], args[4]
        try:
            if int(code) >= 300:
                return True
        except (TypeError, ValueError):
            return True
        return not any(str(pfad).split("?")[0] == p for p in self.STILL)


def main() -> None:
    # Uvicorn meldet gleich "running on http://0.0.0.0:8000". Das ist der Port
    # INNERHALB des Containers und stimmt -- im Protokoll neben einer
    # Aufforderung "im Browser oeffnen" fuehrt er aber in die Irre, weil man
    # von aussen den Port aus der Compose braucht. Deshalb sagen wir es selbst,
    # bevor uvicorn seine Zeile schreibt.
    aussen = os.environ.get("WEBUI_PORT")
    print(
        "[satcortex] Die Weboberflaeche laeuft im Container auf Port 8000. "
        + (f"Von aussen erreichbar unter Port {aussen}."
           if aussen else
           "Von aussen unter dem Port, den die Compose veroeffentlicht."),
        flush=True,
    )

    # Die eigenen Meldungen ueberhaupt sichtbar machen. Ohne das griff nur
    # Pythons Notnagel-Handler, und der zeigt erst ab WARNING -- alles, was
    # die Anwendung an INFO meldet (Konfiguration geschrieben, Zulauf
    # verbunden, Adresse gewechselt, Fassung geprueft), fiel unter den Tisch.
    # Genau diese Zeilen will man in der Protokoll-Ansicht lesen.
    #
    # uvicorn faellt dabei nicht doppelt an: seine eigenen Logger stehen in
    # der mitgelieferten Konfiguration auf propagate=False.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "info").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%d.%m. %H:%M:%S",
        stream=sys.stdout,
    )

    # Wer alles sehen will, setzt ZUGRIFFSPROTOKOLL=voll.
    if os.environ.get("ZUGRIFFSPROTOKOLL", "").lower() != "voll":
        logging.getLogger("uvicorn.access").addFilter(OhneTaktrauschen())

    konf = settings.laden()
    app = api.baue_app(konf)
    # nosec B104 -- im Container beabsichtigt und noetig: Docker leitet den
    # veroeffentlichten Port an das Container-Netz weiter, und das erreicht
    # man nur ueber 0.0.0.0. Nach aussen sichtbar ist ausschliesslich, was
    # die Compose freigibt; wer enger binden will, setzt BIND_HOST.
    host = os.environ.get("BIND_HOST", "0.0.0.0")  # nosec B104
    port = int(os.environ.get("BIND_PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info")

    if konf.tls_aktiv:
        print("[satcortex] Verschluesselung aktiv.", flush=True)
    elif konf.tls_cert or konf.tls_key:
        # Nur eines von beiden ist ein Konfigurationsfehler, kein Wunsch nach
        # Klartext -- das gehoert gesagt, statt still auf HTTP zu fallen.
        print("[satcortex] ACHTUNG: TLS_CERT und TLS_KEY gehoeren zusammen. "
              "Es ist nur eines gesetzt -- die Oberflaeche laeuft unverschluesselt.",
              flush=True)

    haupt, neben = baue_server(konf, app, host=host, port=port,
                               log_level=log_level)
    if neben is None:
        # Ohne zweiten Port genau der Aufruf, der hier seit jeher stand --
        # nicht "ungefaehr dasselbe". Wer WEBUI_TLS=off setzt, bekommt damit
        # den Start, den er kannte.
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            # Ein Arbeiter genuegt: die Anwendung ist I/O-gebunden und soll auf
            # einem NAS moeglichst wenig Speicher belegen.
            workers=1,
            **_tls_von(konf),
        )
        return
    asyncio.run(laufe_beide(haupt, neben))


def _tls_von(konf) -> dict:
    """Das eigene Zertifikat fuer den HTTP-Port, falls TLS_CERT/TLS_KEY gesetzt."""
    if konf.tls_aktiv:
        return {"ssl_certfile": konf.tls_cert, "ssl_keyfile": konf.tls_key}
    return {}


class _HauptServer(uvicorn.Server):
    """Der bisherige Port. Er faengt die Signale ab -- und reicht das Ende an
    den zweiten weiter."""

    neben: Optional[uvicorn.Server] = None

    def handle_exit(self, sig, frame):
        if self.neben is not None:
            self.neben.should_exit = True
        super().handle_exit(sig, frame)


class _NebenServer(uvicorn.Server):
    """Der zweite Port. Er rührt die Signale NICHT an.

    DER BEFUND VOM 16.11.2026, an uvicorn 0.52.4 gelesen: jeder Server
    installiert in serve() seine eigenen Handler fuer SIGINT und SIGTERM und
    stellt beim Verlassen die alten wieder her. Liefen beide so, haette der
    zuletzt gestartete die Signale bekommen und der andere nie ein Ende
    erfahren -- docker stop haette zehn Sekunden ins Leere gewartet und dann
    gekillt, mitten im Schreiben. Also genau ein Empfaenger (_HauptServer),
    der das Ende weitergibt.
    """

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def baue_server(konf, app, *, host: str, port: int,
                log_level: str) -> Tuple[uvicorn.Server, Optional[uvicorn.Server]]:
    """Die beiden Server -- der zweite ist None, wenn es ihn nicht geben soll.

    Der erste ist der bisherige, mit allem, was er hatte (auch dem eigenen
    Zertifikat aus TLS_CERT/TLS_KEY). Der zweite haelt dieselbe App auf dem
    verschluesselten Port, mit lifespan="off": Start- und Beendigungs-Haken der
    App (Waechter, Hintergrundfaeden, Datenbanken) laufen GENAU EINMAL, nicht
    je Port. Zwei Waechter, die in dieselben Dateien schreiben, waeren genau
    die Art Fehler, die man erst im Betrieb merkt.
    """
    haupt = _HauptServer(uvicorn.Config(
        app, host=host, port=port, log_level=log_level, **_tls_von(konf)))
    try:
        dateien = webtls.dateien_fuer(konf)
    except Exception as fehler:   # noqa: BLE001 -- jeder Grund, derselbe Ausweg
        # Ablage nicht beschreibbar, Platte voll, Bibliothek kaputt: der Zugang,
        # der heute funktioniert, darf daran nicht sterben. Die Oberflaeche
        # laeuft weiter wie bisher und der Eigentuemer erfaehrt, warum es keinen
        # verschluesselten Port gibt.
        log.error("Zertifikat fuer den verschluesselten Port nicht moeglich: "
                  "%s", fehler)
        print("[satcortex] ACHTUNG: Der verschluesselte Port steht nicht zur "
              f"Verfuegung ({fehler}). Die Oberflaeche laeuft weiter ueber "
              "HTTP.", flush=True)
        return haupt, None
    if dateien is None:
        return haupt, None
    neben = _NebenServer(uvicorn.Config(
        app, host=host, port=konf.bind_tls_port, log_level=log_level,
        ssl_certfile=dateien.zertifikat, ssl_keyfile=dateien.schluessel,
        lifespan="off"))
    haupt.neben = neben
    aussen = getattr(konf, "webui_tls_port", None)
    print(
        f"[satcortex] Verschluesselt auch auf Port {konf.bind_tls_port} im "
        "Container" + (f" (von aussen Port {aussen})" if aussen else "")
        + ". SHA-256-Fingerabdruck des Zertifikats, zum Vergleich mit dem, "
        f"was der Browser beim ersten Besuch zeigt: {webtls.fingerabdruck(dateien.zertifikat)}",
        flush=True)
    return haupt, neben


async def laufe_beide(haupt: uvicorn.Server, neben: uvicorn.Server) -> None:
    """Beide Server auf einer Ereignisschleife, bis der erste endet.

    Der zweite ist Beiwerk: scheitert er (Port belegt, Zertifikat unlesbar),
    laeuft der erste weiter. uvicorn beendet dann mit sys.exit() -- das wird
    hier aufgefangen, sonst risse es den Prozess mit. Umgekehrt: endet der
    erste, wird der zweite angehalten und abgewartet.
    """
    async def nebenher() -> None:
        try:
            await neben.serve()
        except SystemExit:
            log.error("Der verschluesselte Port konnte nicht starten -- die "
                      "Oberflaeche laeuft weiter ueber HTTP.")
        except Exception:   # noqa: BLE001
            log.exception("Der verschluesselte Port ist ausgefallen -- die "
                          "Oberflaeche laeuft weiter ueber HTTP.")

    aufgabe = asyncio.create_task(nebenher())
    try:
        await haupt.serve()
    finally:
        neben.should_exit = True
        await aufgabe


if __name__ == "__main__":
    main()
