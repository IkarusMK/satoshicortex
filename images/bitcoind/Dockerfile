# SatoshiCortex — Bitcoin Core.
#
# Kein fremdes Image: wir laden das offizielle Release von bitcoincore.org und
# pruefen es gegen die PGP-Signaturen der Bitcoin-Core-Builder, bevor auch nur
# ein Byte ins Laufzeit-Image kommt.
#
# Vertrauensanker ist bitcoin-core/guix.sigs, auf einen Commit festgenagelt --
# ein bewegliches Ziel waere kein Anker. Verlangt werden mindestens
# MIN_GOOD_SIGS unabhaengige gute Signaturen; das Release 31.1 traegt 11.

FROM debian:trixie-slim AS verifier

ARG BITCOIN_VERSION=31.1
# Docker fuellt TARGETARCH beim Bauen selbst -- daraus ergibt sich, welches
# Release gebraucht wird. Nichts festverdrahten: sonst laeuft das Image nur auf
# der Architektur, auf der es zufaellig gebaut wurde.
ARG TARGETARCH
# Commit von bitcoin-core/guix.sigs, aus dem die Builder-Keys stammen (2026-08-03)
ARG GUIX_SIGS_COMMIT=3b667ee3ebb3dcd9e1990cf03e38a0935eec1683
ARG MIN_GOOD_SIGS=3

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 1) Zielarchitektur bestimmen und die passenden Artefakte holen.
RUN case "${TARGETARCH}" in \
      amd64) BOGEN=x86_64-linux-gnu   ;; \
      arm64) BOGEN=aarch64-linux-gnu  ;; \
      riscv64) BOGEN=riscv64-linux-gnu ;; \
      ppc64le) BOGEN=powerpc64-linux-gnu ;; \
      *) echo "Fuer die Architektur '${TARGETARCH}' veroeffentlicht Bitcoin Core" >&2; \
         echo "kein Release. Unterstuetzt: amd64, arm64, riscv64, ppc64le." >&2; \
         exit 1 ;; \
    esac \
    && echo "${BOGEN}" > /build/bogen \
    && base="https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}" \
    && curl -fsSLO "${base}/bitcoin-${BITCOIN_VERSION}-${BOGEN}.tar.gz" \
    && curl -fsSLO "${base}/SHA256SUMS" \
    && curl -fsSLO "${base}/SHA256SUMS.asc"

# 2) Builder-Keys aus dem gepinnten guix.sigs-Commit importieren.
#
# Als Archiv, NICHT ueber die GitHub-API. Die API begrenzt nicht angemeldete
# Abrufe auf 60 pro Stunde und IP -- auf einem gemeinsam genutzten Laeufer ist
# das schnell aufgebraucht, und der Bau bricht dann mit "exit code 22" ab, ohne
# dass man dem Fehler ansieht, woran es lag. Genau das ist uns passiert.
# codeload liefert dieselben Dateien als Tarball, ohne Kontingent, und der
# Commit bleibt exakt derselbe.
RUN export GNUPGHOME=/build/gnupg && mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME" \
    && curl -fsSL "https://codeload.github.com/bitcoin-core/guix.sigs/tar.gz/${GUIX_SIGS_COMMIT}" \
       | tar -xz -C /build --wildcards "*/builder-keys/*.gpg" \
    && anzahl=$(find /build -path "*/builder-keys/*.gpg" | wc -l) \
    && test "$anzahl" -gt 0 \
    && echo "Gefundene Schluesseldateien: ${anzahl}" \
    && find /build -path "*/builder-keys/*.gpg" -exec gpg --quiet --import {} \; 2>/dev/null \
    && echo "Importierte Schluessel: $(gpg --list-keys --with-colons | grep -c '^pub')"

# 3) Signaturen zaehlen -- nicht "irgendeine ist gut", sondern mindestens N
RUN export GNUPGHOME=/build/gnupg \
    && gpg --verify SHA256SUMS.asc SHA256SUMS 2>&1 | tee /build/verify.log ; \
    good=$(grep -c '^gpg: Good signature' /build/verify.log || true) \
    && echo "Gute Signaturen: ${good} (verlangt: ${MIN_GOOD_SIGS})" \
    && if [ "${good}" -lt "${MIN_GOOD_SIGS}" ]; then \
         echo "ABBRUCH: zu wenige gueltige Builder-Signaturen." >&2; exit 1; \
       fi

# 4) Pruefsumme des Tarballs gegen die eben signaturgeprueften SHA256SUMS.
#    Bewusst KEINE zusaetzlich festverdrahtete Pruefsumme mehr: die galt nur fuer
#    eine Architektur, und die signaturgepruefte Liste ist ohnehin der staerkere
#    Anker -- sie deckt alle Architekturen ab und haengt an drei unabhaengigen
#    Builder-Schluesseln statt an einem Wert in einer Datei.
RUN BOGEN="$(cat /build/bogen)" \
    && grep " bitcoin-${BITCOIN_VERSION}-${BOGEN}.tar.gz\$" SHA256SUMS | sha256sum -c -

# 5) Nur die Binaries auspacken, die wir wirklich brauchen
RUN tar -xzf "bitcoin-${BITCOIN_VERSION}-$(cat /build/bogen).tar.gz" \
    && mkdir -p /out/bin \
    && cp "bitcoin-${BITCOIN_VERSION}/bin/bitcoind"    /out/bin/ \
    && cp "bitcoin-${BITCOIN_VERSION}/bin/bitcoin-cli" /out/bin/ \
    && mkdir -p /out/licenses \
    && cp "bitcoin-${BITCOIN_VERSION}/share/doc/bitcoin/"* /out/licenses/ 2>/dev/null || true \
    && /out/bin/bitcoind -version | head -1


FROM debian:trixie-slim

ARG BITCOIN_VERSION=31.1
LABEL org.opencontainers.image.title="satcortex-bitcoind" \
      org.opencontainers.image.description="Bitcoin Core ${BITCOIN_VERSION}, signaturgeprueft aus dem offiziellen Release" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/IkarusMK/satoshicortex"

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 bitcoin \
    && useradd -u 1000 -g bitcoin -m -s /usr/sbin/nologin bitcoin \
    && mkdir -p /fast /bulk && chown bitcoin:bitcoin /fast /bulk

COPY --from=verifier /out/bin/      /usr/local/bin/
COPY --from=verifier /out/licenses/ /usr/share/licenses/bitcoin-core/
# Baukontext ist das Repo-Wurzelverzeichnis.
# --chmod ist hier Pflicht, nicht Stil: das Ausfuehrungsrecht ueberlebt weder
# ein ZIP-Archiv von GitHub noch eine Uebertragung per SMB. Ohne das Bit findet
# Dockers PATH-Suche die Datei nicht -- sie ueberspringt nicht-ausfuehrbare
# Treffer und meldet irrefuehrend "executable file not found in $PATH".
COPY --chmod=0755 images/common/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chmod=0755 images/common/gesund.sh     /usr/local/bin/gesund.sh

USER 1000:1000
# Kein VOLUME: die Daten liegen unter /fast und /bulk, und die kommen aus der
# Compose. Eine Volume-Erklaerung wuerde bei jedem Start ein anonymes Volume
# anlegen, das niemand sichert und niemand wiederfindet.

# 8333 P2P (nach aussen), 8332 RPC + 28332-28334 ZMQ (nur im Compose-Netz)
EXPOSE 8333 8332 28332 28333 28334

# start-period grosszuegig: der Dienst wartet erst auf die Einrichtung in der
# Weboberflaeche und faengt danach mit dem Erstsync an.
HEALTHCHECK --interval=60s --timeout=15s --start-period=10m --retries=5 \
  CMD gesund.sh bitcoind bitcoin-cli -datadir=/fast/bitcoind -rpcwait -rpcwaittimeout=10 getblockchaininfo || exit 1

ENTRYPOINT ["entrypoint.sh", "bitcoind", \
            "bitcoind", "-datadir=/fast/bitcoind", "-conf=/fast/config/bitcoind.conf"]
