"""Was aus der .env kommt. Bewusst wenig -- alles andere macht der Assistent."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from . import netz

log = logging.getLogger(__name__)


def _int(name: str, standard: int) -> int:
    try:
        return int(os.environ.get(name, standard))
    except ValueError:
        return standard


def _praefix(name: str) -> str:
    """Das Netz-Praefix aus der Compose -- geprueft, mit Vorgabe.

    Ein ungueltiger Wert kommt bis hierher praktisch nicht: Docker legt das
    Netz dann gar nicht erst an, und der Stapel startet nicht. Falls doch,
    gilt die Vorgabe, und das Protokoll sagt es.
    """
    wert = os.environ.get(name, netz.PRAEFIX_VORGABE)
    try:
        return netz.pruefe_praefix(wert)
    except ValueError as fehler:
        log.error("%s ist ungueltig (%s) -- es gilt %s.", name, fehler,
                  netz.PRAEFIX_VORGABE)
        return netz.PRAEFIX_VORGABE


@dataclass(frozen=True)
class Einstellungen:
    bulk: str = os.environ.get("DATA_BULK_MOUNT", "/bulk")
    fast: str = os.environ.get("DATA_FAST_MOUNT", "/fast")
    config_dir: str = os.environ.get("CONFIG_DIR", "/fast/config")
    # Wo bitcoind erreichbar ist. Der Name ist der Dienstname aus der Compose;
    # das Compose-Netz loest ihn auf. Der Port steht so in der bitcoin.conf.
    bitcoind_host: str = os.environ.get("BITCOIND_HOST", "bitcoind")
    bitcoind_rpc_port: int = _int("BITCOIND_RPC_PORT", 8332)
    # LND, ueber sein REST-Gateway. Der Port wird in der Compose bewusst NICHT
    # nach aussen veroeffentlicht -- er ist nur im Compose-Netz erreichbar.
    lnd_host: str = os.environ.get("LND_HOST", "lnd")
    lnd_rest_port: int = _int("LND_REST_PORT", 8080)
    # Der sequence-Strom: jede Aufnahme in den Mempool, jedes Entfernen, jeder
    # Block. Er verlaesst das Compose-Netz nie -- bitcoind veroeffentlicht ihn
    # auf 0.0.0.0, aber die Compose gibt den Port nicht nach aussen frei.
    zmq_sequence_port: int = _int("ZMQ_SEQUENCE_PORT", 28334)
    # Tors HTTP-Tunnel im Compose-Netz. Ueber ihn laeuft die Versionsabfrage,
    # damit sie nicht die eigene Adresse preisgibt.
    tor_host: str = os.environ.get("TOR_HOST", "tor")
    tor_http_port: int = _int("TOR_HTTP_PORT", 9080)
    # Derselbe Tor, andere Tuer: SOCKS5 statt HTTP-Tunnel. Ueber ihn laeuft
    # der Erreichbarkeitstest -- er braucht eine rohe TCP-Verbindung nach
    # aussen, keinen HTTP-Verkehr.
    tor_socks_port: int = _int("TOR_SOCKS_PORT", 9050)
    # Und eine dritte, allein fuer die Erreichbarkeitspruefung: SOCKS mit
    # Tors erweiterten Fehlercodes. Warum getrennt: siehe torrc.tmpl.
    tor_pruef_port: int = _int("TOR_PRUEF_PORT", 9052)
    zeitzone: str = os.environ.get("TZ", "UTC")
    # Setzt das Abbild beim Bauen. "dev" heisst: aus dem Arbeitsverzeichnis
    # gestartet, nicht aus einem veroeffentlichten Abbild.
    version: str = os.environ.get("SATCORTEX_VERSION", "dev")
    # Welchem Abbild-Tag diese Installation FOLGT -- "latest" oder eine feste
    # Nummer. Kommt aus der Compose. Leer heisst: unbekannt, etwa bei einer
    # Compose-Datei von vor dem 23.09.2026. Dann nennt der Fassungskasten
    # beide Wege, statt einen zu raten.
    abbild_tag: str = os.environ.get("SATCORTEX_ABBILD_TAG", "").strip()
    # Verschluesselung ist FREIWILLIG und ausdruecklich nicht die Vorgabe.
    # Ein selbstsigniertes Zertifikat wuerde beim ersten Aufruf eine
    # Sicherheitswarnung erzeugen -- ausgerechnet auf der Seite, auf der man
    # gleich sein Passwort eingibt. Das erzieht dazu, solche Warnungen
    # wegzuklicken, und macht die Sache unterm Strich unsicherer. Wer
    # Zertifikate hat -- aus einem Reverse Proxy, von Let's Encrypt --, haengt
    # sie hier ein.
    tls_cert: str = os.environ.get("TLS_CERT", "")
    tls_key: str = os.environ.get("TLS_KEY", "")

    @property
    def tls_aktiv(self) -> bool:
        return bool(self.tls_cert and self.tls_key)

    # Steht ein Reverse Proxy davor, der TLS beendet? Dann spricht die
    # Anwendung selbst Klartext -- der BROWSER aber https. Ohne diesen
    # Schalter bekaeme das Sitzungs-Cookie ausgerechnet im Internet-Betrieb
    # kein "Secure" und duerfte damit auch ueber Klartext mitgeschickt werden.
    # tls_aktiv taugt dafuer nicht: das beschreibt, ob WIR das Zertifikat
    # halten, nicht ob die Strecke zum Browser verschluesselt ist.
    tls_extern: bool = os.environ.get("TLS_EXTERN", "").strip().lower() in (
        "1", "true", "yes", "ja")

    # ------------------------------------------------------------------ OIDC
    # Anmeldung ueber einen eigenen Ausweisdienst -- Pocket ID, Authentik,
    # Keycloak. Hier standen bis zum 01.09.2026 schon einmal Variablen, hinter
    # denen KEIN Anmeldeweg lag; sie sind damals zu Recht geflogen. Diesmal
    # gibt es den Weg zuerst (satcortex/oidc.py) und die Einstellung danach.
    #
    # Kein eigener EIN/AUS-Schalter: eingeschaltet ist, was vollstaendig
    # eingetragen ist. Ein Schalter, den man umlegen kann, ohne dass sich
    # etwas aendert, war genau der alte Fehler.
    oidc_issuer: str = os.environ.get("OIDC_ISSUER", "").strip().rstrip("/")
    oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "").strip()
    oidc_client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "").strip()
    oidc_rueckweg: str = os.environ.get("OIDC_REDIRECT_URL", "").strip()

    @property
    def oidc_aktiv(self) -> bool:
        # OHNE das Secret. Pocket ID vergibt fuer seine Clients keins mehr --
        # aus der eigenen Doku: "Only public clients are supported, so
        # token_endpoint_auth_method must be none. PKCE is enabled
        # automatically." Ein Pflichtfeld dafuer haette den Weg unbenutzbar
        # gemacht, und zwar genau fuer den Anbieter, fuer den er gebaut ist.
        #
        # Wer einen Anbieter hat, der noch Secrets vergibt (Authentik,
        # Keycloak), traegt es ein und es wird mitgeschickt. Beides geht.
        return bool(self.oidc_issuer and self.oidc_client_id
                    and self.oidc_rueckweg)

    webui_port: int = _int("WEBUI_PORT", 4080)
    bitcoin_p2p_port: int = _int("BITCOIN_P2P_PORT", 8333)
    lightning_p2p_port: int = _int("LIGHTNING_P2P_PORT", 9735)
    # Der Port, unter dem der Wachturm VON AUSSEN angesprochen wird. Im
    # Container horcht er immer auf 9911 -- die Compose bildet ihn ab.
    wachturm_port: int = _int("WATCHTOWER_PORT", 9911)
    # Die ersten drei Stellen des Compose-Netzes. Dieselbe Zahl steht in der
    # Compose; die Anwendung braucht sie fuer Tors Weiterleitungen und fuer
    # rpcallowip. Warum feste Adressen: siehe netz.py.
    netz_praefix: str = _praefix("NETWORK_PREFIX")

    @property
    def compose_netz(self) -> str:
        return netz.subnetz(self.netz_praefix)


def laden() -> Einstellungen:
    return Einstellungen()
