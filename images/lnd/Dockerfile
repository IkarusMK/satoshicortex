# SatoshiCortex — LND (Lightning Network Daemon).
#
# Wie bei Bitcoin Core: kein fremdes Image. Wir laden das offizielle Release
# von GitHub und pruefen es gegen die PGP-Signaturen der Lightning-Labs-
# Freigeber, bevor ein Byte ins Laufzeit-Image kommt.
#
# LND legt jedem Release ein "manifest-<version>.txt" mit den Pruefsummen bei
# und dazu MEHRERE unabhaengige Signaturen darueber -- v0.21.2-beta traegt
# sieben (roasbeef, guggero-Kreis, ziggie1984, yyforyongyu, boris,
# georgetsagk, suheb, ViktorT-11). Wir verlangen mindestens MIN_GOOD_SIGS
# davon. Eine einzelne Signatur zu pruefen hiesse, alles an einem Schluessel
# aufzuhaengen.
#
# WORAUF DIESE PRUEFUNG WIRKLICH ANTWORTET -- und worauf nicht:
# Die Schluessel liegen im selben Repo wie die Software (scripts/keys/). Wer
# das Repo beherrscht, beherrscht damit auch die Schluessel; die Pruefung ist
# also kein Ersatz fuer Vertrauen in Lightning Labs. Was sie leistet, ist
# dreierlei:
#   1. Die Binaries muessen von mehreren Personen freigegeben sein.
#   2. Ein spaeterer Austausch der Dateien am Release vorbei faellt auf.
#   3. Ein Austausch der SCHLUESSEL faellt auf, weil der Commit unten
#      festgenagelt ist -- eine Aenderung daran steht im Diff und muss
#      begruendet werden. Ein bewegliches "master" waere kein Anker.

FROM debian:trixie-slim AS verifier

# renovate: datasource=github-releases depName=lightningnetwork/lnd
ARG LND_VERSION=v0.21.3-beta
# Docker fuellt TARGETARCH beim Bauen selbst. Nichts festverdrahten: sonst
# laeuft das Abbild nur auf der Architektur, auf der es zufaellig gebaut wurde.
ARG TARGETARCH
ARG TARGETVARIANT
# Commit hinter dem Release-Tag v0.21.2-beta (2026-08-12), aus dem die
# Freigeber-Schluessel stammen.
ARG LND_KEYS_COMMIT=29257ecc8892af0c882fa627b66a556190c84fd9
ARG MIN_GOOD_SIGS=3

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 1) Freigeber-Schluessel aus dem gepinnten Commit importieren.
#
# Als Archiv ueber codeload, NICHT ueber die GitHub-API: die begrenzt nicht
# angemeldete Abrufe auf 60 pro Stunde und IP. Auf einem gemeinsam genutzten
# Laeufer ist das schnell aufgebraucht, und der Bau bricht dann mit einem
# Fehler ab, dem man nicht ansieht, woran es lag. Genau das ist beim
# Bitcoin-Core-Abbild schon einmal passiert.
#
# Der Dateiname traegt dabei mehr als den Schluessel: "roasbeef.asc" gehoert
# zu "manifest-roasbeef-<version>.sig". Damit ist die Liste der moeglichen
# Freigeber schon bekannt, bevor irgendetwas geladen wird -- eine Abfrage der
# Release-Anhaenge eruebrigt sich, und mit ihr der zweite Weg ueber die API.
RUN export GNUPGHOME=/build/gnupg && mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME" \
    && curl -fsSL "https://codeload.github.com/lightningnetwork/lnd/tar.gz/${LND_KEYS_COMMIT}" \
       | tar -xz -C /build --wildcards "*/scripts/keys/*.asc" \
    && find /build -path "*/scripts/keys/*.asc" -exec basename {} .asc \; \
       | sort > /build/freigeber.txt \
    && anzahl=$(wc -l < /build/freigeber.txt) \
    && test "$anzahl" -ge "${MIN_GOOD_SIGS}" \
    && echo "Bekannte Freigeber: ${anzahl} -- $(tr '\n' ' ' < /build/freigeber.txt)" \
    && find /build -path "*/scripts/keys/*.asc" -exec gpg --quiet --import {} \; 2>/dev/null \
    && echo "Importierte Schluessel: $(gpg --list-keys --with-colons | grep -c '^pub')"

# 2) Zielarchitektur bestimmen und die Artefakte holen.
#
# Wer von den bekannten Freigebern DIESES Release mitgezeichnet hat, steht
# vorher nicht fest -- es sind je Release andere. Also wird jede moegliche
# Signatur versucht; ein 404 ist hier kein Fehler, sondern die Auskunft
# "hat nicht mitgezeichnet". Gezaehlt wird erst im naechsten Schritt.
RUN case "${TARGETARCH}${TARGETVARIANT}" in \
      amd64)   BOGEN=linux-amd64  ;; \
      arm64)   BOGEN=linux-arm64  ;; \
      armv7)   BOGEN=linux-armv7  ;; \
      armv6)   BOGEN=linux-armv6  ;; \
      386)     BOGEN=linux-386    ;; \
      *) echo "Fuer '${TARGETARCH}${TARGETVARIANT}' veroeffentlicht LND kein" >&2; \
         echo "Linux-Release. Unterstuetzt: amd64, arm64, armv7, armv6, 386." >&2; \
         exit 1 ;; \
    esac \
    && echo "${BOGEN}" > /build/bogen \
    && basis="https://github.com/lightningnetwork/lnd/releases/download/${LND_VERSION}" \
    && curl -fsSLO "${basis}/lnd-${BOGEN}-${LND_VERSION}.tar.gz" \
    && curl -fsSLO "${basis}/manifest-${LND_VERSION}.txt" \
    && while read -r wer; do \
         curl -fsSLO "${basis}/manifest-${wer}-${LND_VERSION}.sig" \
           && echo "  Signatur von ${wer}: geladen" \
           || echo "  Signatur von ${wer}: nicht vorhanden"; \
       done < /build/freigeber.txt \
    && echo "Geladene Signaturen: $(ls manifest-*-"${LND_VERSION}".sig 2>/dev/null | wc -l)"

# 3) Signaturen zaehlen -- nicht "irgendeine ist gut", sondern mindestens N.
RUN export GNUPGHOME=/build/gnupg \
    && : > /build/verify.log \
    && for sig in manifest-*-"${LND_VERSION}".sig; do \
         [ -e "$sig" ] || continue; \
         gpg --verify "$sig" "manifest-${LND_VERSION}.txt" 2>&1 | tee -a /build/verify.log; \
       done ; \
    gut=$(grep -c '^gpg: Good signature' /build/verify.log || true) \
    && echo "Gute Signaturen: ${gut} (verlangt: ${MIN_GOOD_SIGS})" \
    && if [ "${gut}" -lt "${MIN_GOOD_SIGS}" ]; then \
         echo "ABBRUCH: zu wenige gueltige Freigeber-Signaturen." >&2; exit 1; \
       fi

# 4) Pruefsumme des Tarballs gegen das eben signaturgeprueften Manifest.
RUN BOGEN="$(cat /build/bogen)" \
    && grep " lnd-${BOGEN}-${LND_VERSION}.tar.gz\$" "manifest-${LND_VERSION}.txt" \
       | sha256sum -c -

# 5) Auspacken -- und die beiden Binaries EINZELN gegen das Manifest pruefen.
#    Das Manifest fuehrt sie mit eigenen Pruefsummen; die zu ueberspringen
#    hiesse, dem Entpacken zu vertrauen, obwohl der Beleg danebenliegt.
RUN BOGEN="$(cat /build/bogen)" \
    && tar -xzf "lnd-${BOGEN}-${LND_VERSION}.tar.gz" \
    && grep -E " lnd-${BOGEN}-${LND_VERSION}/(lnd|lncli)\$" "manifest-${LND_VERSION}.txt" \
       | sha256sum -c - \
    && mkdir -p /out/bin \
    && cp "lnd-${BOGEN}-${LND_VERSION}/lnd"   /out/bin/ \
    && cp "lnd-${BOGEN}-${LND_VERSION}/lncli" /out/bin/ \
    && /out/bin/lnd --version

# 6) Der Lizenztext gehoert mit ins Abbild -- LND steht unter MIT, und wer
#    Binaries weiterverteilt, legt den Hinweis bei. Der Release-Tarball
#    enthaelt ihn nicht, also aus demselben gepinnten Commit.
RUN curl -fsSL "https://raw.githubusercontent.com/lightningnetwork/lnd/${LND_KEYS_COMMIT}/LICENSE" \
      -o /out/LICENSE \
    && test -s /out/LICENSE


FROM debian:trixie-slim

ARG LND_VERSION=v0.21.3-beta
LABEL org.opencontainers.image.title="satcortex-lnd" \
      org.opencontainers.image.description="LND ${LND_VERSION}, signaturgeprueft aus dem offiziellen Release" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/IkarusMK/satoshicortex"

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 lightning \
    && useradd -u 1000 -g lightning -m -s /usr/sbin/nologin lightning \
    && mkdir -p /fast && chown lightning:lightning /fast

COPY --from=verifier /out/bin/ /usr/local/bin/
COPY --from=verifier --chmod=0644 /out/LICENSE /usr/share/licenses/lnd/LICENSE
# Baukontext ist das Repo-Wurzelverzeichnis.
# --chmod ist hier Pflicht, nicht Stil: das Ausfuehrungsrecht ueberlebt weder
# ein ZIP-Archiv von GitHub noch eine Uebertragung per SMB. Ohne das Bit findet
# Dockers PATH-Suche die Datei nicht.
COPY --chmod=0755 images/common/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chmod=0755 images/common/gesund.sh     /usr/local/bin/gesund.sh
# Das Lizenzverzeichnis muss betretbar sein. --chmod oben setzt den Modus auch
# auf die dabei angelegten VERZEICHNISSE, und 0644 auf einem Verzeichnis
# heisst: nicht betretbar. Genau daran ist das App-Abbild schon einmal
# gescheitert, und die Pruefung log ueber die Ursache.
RUN chmod 0755 /usr/share/licenses /usr/share/licenses/lnd

USER 1000:1000

# 9735 P2P (nach aussen), 10009 gRPC und 8080 REST (nur im Compose-Netz)
EXPOSE 9735 10009 8080

# "lncli state" ist der richtige Griff: der State-Dienst antwortet ab
# NON_EXISTING, also schon BEVOR eine Wallet angelegt ist. Ein Aufruf, der
# eine entsperrte Wallet braucht, wuerde den Container faelschlich krank
# melden, solange der Seed noch nicht auf Papier steht -- und das kann Tage
# dauern, weil erst die Kette fertig sein muss.
HEALTHCHECK --interval=60s --timeout=15s --start-period=5m --retries=5 \
  CMD gesund.sh lnd lncli --lnddir=/fast/lnd --network=mainnet state || exit 1

ENTRYPOINT ["entrypoint.sh", "lnd", \
            "lnd", "--lnddir=/fast/lnd", "--configfile=/fast/config/lnd.conf"]
