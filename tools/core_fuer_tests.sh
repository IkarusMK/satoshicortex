#!/bin/sh
# Bitcoin Core fuer die Tests gegen einen echten Knoten (Regtest) holen -- und
# pruefen, bevor es laeuft.
#
# Dieselbe Fassung und derselbe Vertrauensanker wie im Abbild: Version,
# guix.sigs-Commit und Mindestzahl stehen in images/bitcoind/Dockerfile und
# werden von dort gelesen, damit Test und Abbild nie auseinanderlaufen.
#
# Geprueft wird zweifach, unabhaengig voneinander:
#   1. die Pruefsumme gegen SHA256SUMS von bitcoincore.org,
#   2. dieselbe Pruefsumme in den Build-Bestaetigungen (all.SHA256SUMS) der
#      Builder im festgenagelten guix.sigs-Commit -- mindestens MIN_GOOD_SIGS.
#
# Braucht curl und gh (in der CI mit GH_TOKEN). Gibt auf stdout nur den Pfad
# zu bitcoind aus; alles andere geht nach stderr.
#
#   tools/core_fuer_tests.sh ZIELVERZEICHNIS [PLATTFORM]
#   PLATTFORM: x86_64-linux-gnu (Vorgabe, die CI) oder arm64-apple-darwin
set -eu

ziel="${1:?Zielverzeichnis fehlt}"
plattform="${2:-x86_64-linux-gnu}"
wurzel="$(cd "$(dirname "$0")/.." && pwd)"
vorlage="$wurzel/images/bitcoind/Dockerfile"

version=$(sed -n 's/^ARG BITCOIN_VERSION=//p' "$vorlage" | head -n 1)
anker=$(sed -n 's/^ARG GUIX_SIGS_COMMIT=//p' "$vorlage" | head -n 1)
mindestens=$(sed -n 's/^ARG MIN_GOOD_SIGS=//p' "$vorlage" | head -n 1)
if [ -z "$version" ] || [ -z "$anker" ] || [ -z "$mindestens" ]; then
    echo "Version, Anker oder Mindestzahl fehlt in $vorlage" >&2
    exit 1
fi

paket="bitcoin-$version-$plattform.tar.gz"
quelle="https://bitcoincore.org/bin/bitcoin-core-$version"
mkdir -p "$ziel"
cd "$ziel" || exit 1
[ -f "$paket" ] || curl -fsSLO "$quelle/$paket"
curl -fsSL -o SHA256SUMS "$quelle/SHA256SUMS"

if command -v sha256sum >/dev/null 2>&1; then
    summe=$(sha256sum "$paket" | cut -d' ' -f1)
else
    summe=$(shasum -a 256 "$paket" | cut -d' ' -f1)
fi
if ! grep -q "^$summe  $paket\$" SHA256SUMS; then
    echo "ABBRUCH: $paket passt nicht zu SHA256SUMS" >&2
    exit 1
fi

bestaetigt=0
for builder in $(gh api "repos/bitcoin-core/guix.sigs/contents/$version?ref=$anker" \
                   --jq '.[] | select(.type == "dir") | .name'); do
    if gh api "repos/bitcoin-core/guix.sigs/contents/$version/$builder/all.SHA256SUMS?ref=$anker" \
           --jq .content 2>/dev/null | base64 -d 2>/dev/null \
           | grep -q "^$summe  $paket\$"; then
        bestaetigt=$((bestaetigt + 1))
    fi
done
echo "$paket: $bestaetigt Builder bestaetigen die Pruefsumme (verlangt: $mindestens)" >&2
if [ "$bestaetigt" -lt "$mindestens" ]; then
    echo "ABBRUCH: zu wenige Bestaetigungen" >&2
    exit 1
fi

tar -xzf "$paket"
echo "$ziel/bitcoin-$version/bin/bitcoind"
