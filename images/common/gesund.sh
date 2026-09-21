#!/bin/sh
# SatoshiCortex — a health check that knows about the waiting state.
#
# After startup the services wait for their configuration from the setup
# wizard (see entrypoint.sh). During that time neither bitcoind nor tor is
# running — so a check against their port or RPC must fail. Without this
# script the container would therefore show up as "unhealthy" while doing
# exactly what it is supposed to do: wait.
#
# Practical consequences without that distinction: the NAS container overview
# turns red, "docker compose up --wait" never finishes, and anyone who hooks
# monitoring to the state gets false alarms on every restart.
#
#   gesund.sh <name> <command> [arguments...]

set -eu

NAME="$1"; shift
CONFIG_DIR="${CONFIG_DIR:-/config}"

# Not released yet? Then waiting is the healthy state.
if [ ! -f "${CONFIG_DIR}/${NAME}.conf" ] || [ ! -f "${CONFIG_DIR}/${NAME}.ready" ]; then
  exit 0
fi

exec "$@"
