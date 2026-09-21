#!/bin/sh
# Alles pruefen, was ohne Docker geht -- auf dem eigenen Rechner.
#
# Warum es das gibt: bis zum 01.09.2026 war der einzige Weg, eine Aenderung
# zu pruefen, sie zu pushen. Jeder Versuch kostete damit Actions-Minuten, und
# die sind begrenzt. Das meiste laesst sich hier genauso gut feststellen.
#
# Was hier NICHT geprueft werden kann, sagt der Bericht am Ende ausdruecklich:
# Dockerfiles (hadolint), Compose (dclint), die Image-Builds und der
# Stapel-Test brauchen Docker. Wer die auch lokal will, installiert Docker
# Desktop -- bis dahin macht das die CI, und dieses Skript sorgt dafuer, dass
# sie nicht an Kleinigkeiten scheitert.
#
# Aufruf:  sh tools/pruefen.sh
set -eu

WURZEL=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$WURZEL"

ROT=$(printf '\033[31m'); GRUEN=$(printf '\033[32m')
GELB=$(printf '\033[33m'); AUS=$(printf '\033[0m')

fehler=0
uebersprungen=""

schritt() {
  name=$1; shift
  printf '\n%s── %s %s\n' "$GELB" "$name" "$AUS"
  if "$@"; then
    printf '%s✓ %s%s\n' "$GRUEN" "$name" "$AUS"
  else
    printf '%s✗ %s%s\n' "$ROT" "$name" "$AUS"
    fehler=$((fehler + 1))
  fi
}

ueberspringen() {
  uebersprungen="$uebersprungen
  - $1 ($2)"
  printf '\n%s── %s: uebersprungen -- %s%s\n' "$GELB" "$1" "$2" "$AUS"
}

# ---------------------------------------------------------------- Python
# uv holt sich Python und die Abhaengigkeiten selbst; es muss nichts
# vorbereitet werden und nichts im System liegen bleiben.
if command -v uv >/dev/null 2>&1; then
  py() { (cd app/backend && uv run --quiet --python 3.14 \
            --with-requirements requirements-dev.txt "$@"); }
  schritt "Tests und Abdeckung" py pytest -q \
      --cov=satcortex --cov-report=term-missing --cov-fail-under=80
  # pip-audit prueft hier die INSTALLIERTE Umgebung, nicht die Datei. Die
  # CI nimmt "pip-audit -r requirements.txt"; das legt sich dafuer eine
  # eigene Umgebung an, und genau das scheitert auf diesem Mac beim
  # ensurepip mit SIGABRT. Da die Datei durchgehend festgenagelt ist, enthaelt
  # die Umgebung dieselben Fassungen -- plus die von pip-audit selbst, was
  # hoechstens eine Warnung zu viel bringt, nie eine zu wenig.
  schwachstellen() {
    (cd app/backend && uv run --quiet --python 3.14 \
       --with-requirements requirements.txt --with pip-audit \
       pip-audit --strict 2>&1 | grep -v '^WARNING:cachecontrol')
  }
  schritt "Bekannte Schwachstellen" schwachstellen
  schritt "Statische Pruefung" py bandit -r satcortex -ll -q
else
  ueberspringen "Tests, pip-audit, bandit" "uv fehlt"
fi

# ---------------------------------------------------------------- Oberflaeche
if command -v node >/dev/null 2>&1; then
  schritt "Oberflaeche: Syntax" sh -c 'node --check app/web/app.js && node --check app/web/qr.js'
else
  ueberspringen "Oberflaeche: Syntax" "node fehlt"
fi

doppelte_funktionen() {
  doppelte=$(grep -oE '^(async )?function [A-Za-z0-9_$]+' app/web/app.js \
             | awk '{print $NF}' | sort | uniq -d)
  [ -z "$doppelte" ] || { echo "doppelt vergeben: $doppelte"; return 1; }
  echo "keine doppelten Funktionsnamen"
}
schritt "Oberflaeche: doppelte Funktionsnamen" doppelte_funktionen
schritt "Uebersetzungen" python3 tools/i18n_pruefen.py

# ---------------------------------------------------------------- Skripte
if command -v shellcheck >/dev/null 2>&1; then
  schritt "Startskripte" shellcheck --shell=sh --severity=style \
      images/common/entrypoint.sh images/common/gesund.sh
else
  ueberspringen "Startskripte (shellcheck)" "shellcheck fehlt -- brew install shellcheck"
fi

# ---------------------------------------------------------------- Docker
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  hadolint_alle() {
    for f in app/Dockerfile images/*/Dockerfile; do
      echo "── $f"
      docker run --rm -i -v "$PWD/.hadolint.yaml:/.hadolint.yaml" \
        hadolint/hadolint:latest-alpine hadolint --config /.hadolint.yaml - < "$f" || return 1
    done
  }
  schritt "Dockerfiles" hadolint_alle
  compose_pruefen() {
    [ -f .env ] || cp example.env .env
    docker compose config --quiet
    docker run --rm -v "$PWD:/app" zavoloklom/dclint /app -f compact
  }
  schritt "Compose" compose_pruefen
else
  ueberspringen "Dockerfiles, Compose, Image-Builds, Stapel-Test" \
      "Docker laeuft nicht -- das macht die CI"
fi

# ---------------------------------------------------------------- Bericht
printf '\n────────────────────────────────────────\n'
if [ -n "$uebersprungen" ]; then
  printf 'Nicht hier pruefbar:%s\n\n' "$uebersprungen"
fi
if [ "$fehler" -eq 0 ]; then
  printf '%sAlles gruen, was hier pruefbar war.%s\n' "$GRUEN" "$AUS"
else
  printf '%s%d Pruefung(en) fehlgeschlagen.%s\n' "$ROT" "$fehler" "$AUS"
fi
exit "$fehler"
