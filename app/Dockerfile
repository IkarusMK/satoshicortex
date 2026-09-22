# SatoshiCortex — die Weboberflaeche: Einrichtungsassistent, Uebersicht,
# Auswertung. Sie schreibt die Konfiguration der uebrigen Dienste in das
# gemeinsame config-Volume und liest deren Zustand direkt bei ihnen aus.
#
# Bewusst OHNE Docker-Socket: auf einem Geraet, auf dem eine Lightning-Wallet
# liegt, waere ein Socket gleichbedeutend mit root-Rechten.

# ------------------------------------------------------------- Mitgeliefertes
#
# Zwei Datensaetze, die beim Bauen geholt werden statt im Betrieb: eine
# Ortstabelle fuer die Weltkarte und die Zuordnungsliste der Mining-Pools.
#
# Warum nicht zur Laufzeit nachladen: jede regelmaessige Abfrage waere ein
# weiterer Weg, auf dem dieser Knoten sich zu erkennen gibt. Genau deshalb
# laeuft schon die Versionspruefung ueber Tor. Neue Pools und neue IP-Bereiche
# kommen also mit dem naechsten Abbild -- der Tausch ist bewusst.
#
# ---------------------------------------------------------------- Ortstabelle
#
# Die Weltkarte braucht zu jeder Adresse ein Land. Der bequeme Weg waere ein
# Online-Dienst -- der bekaeme damit im Betrieb die komplette Nachbarliste des
# Knotens. Deshalb liegt die Tabelle fertig im Abbild und wird HIER gebaut,
# einmal beim Bauen, aus der freien Laenderliste von DB-IP (CC BY 4.0).
#
# BUILDPLATFORM, nicht die Zielplattform: das Ergebnis ist eine Datei mit
# festgelegter Byte-Reihenfolge und damit fuer beide Architekturen dieselbe.
# Ohne das liefe die Auswertung von 700.000 Zeilen unter QEMU nach.
FROM --platform=$BUILDPLATFORM python:3.14-slim AS orte

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /bau
COPY --chmod=0755 tools/geo_bauen.py .
# Die Zuordnung der Regionsnamen auf die Umrisse. Sie liegt im Repo,
# nicht im Netz: Regionsgrenzen aendern sich nicht monatlich, und so
# ist nachlesbar, was ausgeliefert wird. Ein Name, den sie nicht
# kennt, faellt auf das Land zurueck -- nie auf eine falsche Region.
COPY app/data/regionen.json .

# Seit 0.42.0 die STADT-Liste statt der Laender-Liste: nur sie fuehrt die
# Region mit, und die brauchen wir, um beim Klick auf ein Land die
# Bundeslaender zu fuellen. Sie ist mit 82 MB gepackt und 658 MB entpackt
# deutlich groesser -- gebaut wird daraus aber eine Tabelle von 41 MB, und
# die entpackte CSV wird gleich wieder geloescht.
#
# Kein fester Monat: die Liste erscheint monatlich unter neuem Namen, ein Pin
# waere in einem Jahr tot. Erst der laufende Monat, dann der vorige -- am
# Monatsanfang gibt es die neue Datei noch nicht. Findet sich keine von
# beiden, BRICHT DER BAU AB. Ein Abbild, das die Karte stillschweigend leer
# laesst, waere schlimmer als ein Bau, der sich meldet.
RUN set -eu; \
    jetzt="$(date -u +%Y-%m)"; \
    vorher="$(date -u -d "$(date -u +%Y-%m-01) -1 day" +%Y-%m)"; \
    gefunden=""; \
    for stand in "$jetzt" "$vorher"; do \
      if curl -fsSL --retry 3 -o liste.csv.gz \
           "https://download.db-ip.com/free/dbip-city-lite-$stand.csv.gz"; then \
        gefunden="$stand"; break; \
      fi; \
    done; \
    if [ -z "$gefunden" ]; then \
      echo "Keine DB-IP-Liste fuer $jetzt oder $vorher gefunden." >&2; exit 1; \
    fi; \
    gunzip liste.csv.gz; \
    python geo_bauen.py liste.csv /geo.dat "$gefunden" regionen.json; \
    rm -f liste.csv

# Zuordnung Coinbase-Adresse/-Kennung -> Mining-Pool. 34 kB, MIT-Lizenz,
# eigenstaendiges Datenrepository (nicht die mempool-Anwendung, die unter
# AGPL steht). Schlaegt der Abruf fehl, BRICHT DER BAU AB: ein Abbild, in dem
# jeder Block still "unbekannt" als Pool zeigt, waere schwerer zu bemerken
# als ein Bau, der sich meldet.
# Auf einen FESTEN Stand gepinnt, nicht auf master. Befund vom 22.09.2026:
# wer Schreibrecht auf diesen Zweig hat, bestimmte damit den Inhalt jedes
# gebauten Abbilds -- ohne dass hier je jemand hinsieht. Die Schluessel von
# Bitcoin Core und LND werden im selben Stapel laengst so gepinnt
# (images/bitcoind/Dockerfile, images/lnd/Dockerfile); diese Datei war die
# Ausnahme.
#
# renovate: datasource=github-refs depName=mempool/mining-pools
ARG POOLS_COMMIT=f678a4a620537ad7997a475ad0f14bfab1de3c8b
RUN curl -fsSL --retry 3 -o /pools.json \
    "https://raw.githubusercontent.com/mempool/mining-pools/${POOLS_COMMIT}/pools-v2.json" \
    && python -c "import json,sys; d=json.load(open('/pools.json')); \
assert isinstance(d, list) and len(d) > 50, 'Pool-Liste sieht falsch aus'; \
print(f'/pools.json: {len(d)} Pools')"

# ------------------------------------------------------------------- Laufzeit
FROM python:3.14-slim AS laufzeit

# Damit die Anwendung sagen kann, welche Fassung sie ist. Am 25.08.2026 lief
# auf dem Geraet stundenlang 0.2.3, waehrend wir ueber 0.2.6 sprachen -- ohne
# eine sichtbare Versionsangabe war das nur ueber Dateigroessen zu erkennen.
ARG SATCORTEX_VERSION=dev
ENV SATCORTEX_VERSION=${SATCORTEX_VERSION}

LABEL org.opencontainers.image.title="satcortex" \
      org.opencontainers.image.description="SatoshiCortex — eigener Bitcoin- und Lightning-Knoten" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/IkarusMK/satoshicortex"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 satcortex \
    && useradd -u 1000 -g satcortex -M -s /usr/sbin/nologin satcortex

WORKDIR /opt/satcortex

# --chmod ueberall, wo aus dem Baukontext kopiert wird: COPY uebernimmt sonst
# die Rechte der Quelldateien. Kommen die aus einem ZIP von GitHub oder ueber
# SMB von einem Mac, sind sie im Zweifel nur fuer den Eigentuemer lesbar -- im
# Abbild also nur fuer root. Der Dienst laeuft als 1000 und scheitert dann beim
# Import seines eigenen Codes:
#   PermissionError: [Errno 13] Permission denied: '/opt/satcortex/satcortex/__init__.py'
# Ein git clone legt 0644 an, deshalb faellt es in der CI nicht auf.
COPY --chmod=0644 app/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chmod=0755 app/backend/satcortex ./satcortex
COPY --chmod=0755 app/templates /opt/templates
COPY --chmod=0755 app/web /opt/web
COPY --from=orte --chmod=0644 /geo.dat /opt/satcortex/geo.dat
# Die Namen der Gebiete -- 3.839 Stueck, deutsch und englisch, plus die
# ISO-Kennungen ihrer Umrisse. Ohne sie traegt die Tabelle Nummern, die
# niemand lesen kann.
COPY --chmod=0644 app/data/regionen.json /opt/satcortex/regionen.json
COPY --from=orte --chmod=0644 /pools.json /opt/satcortex/pools.json

# Die Lizenzen reisen mit. Solange nur der Autor zieht, ist das Formsache --
# sobald fertige Abbilder an Fremde gehen, sind sie Pflicht: das Abbild
# enthaelt dann fremde Werke. Bitcoin Core und die Pool-Liste stehen unter
# MIT, Tor unter BSD, die Ortstabelle von DB-IP unter CC BY -- und CC BY
# verlangt die Nennung ausdruecklich. Bei bitcoind und tor liegen sie schon
# unter /usr/share/licenses; hier fehlten sie bisher.
COPY --chmod=0644 LICENSE /usr/share/licenses/satcortex/LICENSE
COPY --chmod=0644 THIRD-PARTY-LICENSES.md /usr/share/licenses/satcortex/
# Das chmod aus dem COPY gilt AUCH fuer die Verzeichnisse, die dabei entstehen
# -- und 0644 heisst bei einem Verzeichnis: nicht betretbar. Der Dienst laeuft
# als 1000 und kam an seine eigenen Lizenztexte nicht heran:
#   ls: cannot access '/usr/share/licenses/satcortex/': Permission denied
# Dieselbe Falle wie damals beim Quelltext, nur eine Ebene hoeher.
RUN chmod 0755 /usr/share/licenses /usr/share/licenses/satcortex

# Die Anwendung schreibt in /config und liest die Mountpunkte /bulk und /fast.
#
# /config wird per Bind-Mount hereingereicht -- bewusst KEIN benanntes Volume:
# dessen Eigentuemer wird einmalig beim Anlegen festgelegt und ist danach nicht
# mehr zu korrigieren, es ist im Dateimanager unsichtbar und laesst sich schlecht
# sichern. Der Einhaengepunkt wird hier trotzdem angelegt, damit das Abbild auch
# ohne Mount startet. Die Gruppe bleibt schreibberechtigt, weil manche
# NAS-Systeme eine andere GID vorgeben (UGREEN und Synology: 1000:10).
RUN mkdir -p /fast/config /bulk \
    && chown -R 1000:1000 /fast /bulk \
    && chmod -R 0775 /fast /bulk
EXPOSE 8000

USER 1000:1000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["python", "-m", "satcortex"]
