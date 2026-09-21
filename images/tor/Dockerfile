# SatoshiCortex — Tor.
#
# Zweck: Bitcoin Core und LND zusaetzlich zum Clearnet ueber Onion erreichbar
# machen. Tor-only-Nodes brauchen Peers, die beide Welten sprechen — genau
# diese Bruecke ist im Netz knapp.
#
# Bewusst das Debian-Paket statt des Tor-Project-Repos: apt prueft es gegen den
# Debian-Archivschluessel, der im Basis-Image schon liegt. Das ist eine echte
# Signaturpruefung ohne einen weiteren fremden Schluessel, den wir selbst
# pinnen und pflegen muessten. Debian pflegt Sicherheitsfixes nach.

FROM debian:trixie-slim

LABEL org.opencontainers.image.title="satcortex-tor" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.source="https://github.com/IkarusMK/satoshicortex"

# UID 1000 wie in allen anderen SatoshiCortex-Images. Das Debian-Paket wuerde sonst
# als "debian-tor" laufen — und dann passt der Besitzer der gemounteten
# Datenverzeichnisse nicht mehr zu dem, was prepare-dirs.sh setzt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tor ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 tornode \
    && useradd -u 1000 -g tornode -M -s /usr/sbin/nologin tornode \
    && mkdir -p /fast \
    && chown -R tornode:tornode /fast \
    && chmod 755 /fast \
    && mkdir -p /usr/share/licenses/tor \
    && cp /usr/share/doc/tor/copyright /usr/share/licenses/tor/ 2>/dev/null || true

# --chmod ist hier Pflicht, nicht Stil: das Ausfuehrungsrecht ueberlebt weder
# ein ZIP-Archiv von GitHub noch eine Uebertragung per SMB. Ohne das Bit findet
# Dockers PATH-Suche die Datei nicht -- sie ueberspringt nicht-ausfuehrbare
# Treffer und meldet irrefuehrend "executable file not found in $PATH".
COPY --chmod=0755 images/common/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chmod=0755 images/common/gesund.sh     /usr/local/bin/gesund.sh

USER 1000:1000
# Kein VOLUME mehr: Tors Daten liegen unter /fast/tor, und /fast kommt aus
# der Compose. Eine eigene Volume-Erklaerung wuerde beim Start ein anonymes
# Volume anlegen, das niemand sichert und niemand wiederfindet.

# 9050 SOCKS, 9052 SOCKS fuer die Erreichbarkeitspruefung, 9080 HTTP-Tunnel --
# alles nur im Compose-Netz. Kein 9051 mehr: seit 0.63.0 gibt es keinen
# Steuerport, die Onion-Dienste stehen in der torrc.
EXPOSE 9050 9052 9080

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD gesund.sh tor bash -c 'exec 3<>/dev/tcp/127.0.0.1/9050' || exit 1

ENTRYPOINT ["entrypoint.sh", "tor", \
            "tor", "-f", "/fast/config/tor.conf"]
