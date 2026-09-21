"""Startpunkt im Container: python -m satcortex"""
from __future__ import annotations

import logging
import os
import sys

import uvicorn

from . import api, settings


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
    tls = {}
    if konf.tls_aktiv:
        tls = {"ssl_certfile": konf.tls_cert, "ssl_keyfile": konf.tls_key}
        print("[satcortex] Verschluesselung aktiv.", flush=True)
    elif konf.tls_cert or konf.tls_key:
        # Nur eines von beiden ist ein Konfigurationsfehler, kein Wunsch nach
        # Klartext -- das gehoert gesagt, statt still auf HTTP zu fallen.
        print("[satcortex] ACHTUNG: TLS_CERT und TLS_KEY gehoeren zusammen. "
              "Es ist nur eines gesetzt -- die Oberflaeche laeuft unverschluesselt.",
              flush=True)

    uvicorn.run(
        api.baue_app(konf),
        # nosec B104 -- im Container beabsichtigt und noetig: Docker leitet den
        # veroeffentlichten Port an das Container-Netz weiter, und das erreicht
        # man nur ueber 0.0.0.0. Nach aussen sichtbar ist ausschliesslich, was
        # die Compose freigibt; wer enger binden will, setzt BIND_HOST.
        host=os.environ.get("BIND_HOST", "0.0.0.0"),  # nosec B104
        port=int(os.environ.get("BIND_PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
        # Ein Arbeiter genuegt: die Anwendung ist I/O-gebunden und soll auf
        # einem NAS moeglichst wenig Speicher belegen.
        workers=1,
        **tls,
    )


if __name__ == "__main__":
    main()
