#!/bin/sh
# SatoshiCortex — the shared entry point of every service.
#
# The user starts everything at once with "docker compose up -d". The services
# cannot run yet at that point: their configuration is only created by the
# setup wizard in the web interface.
#
# So they wait here. As soon as the application has written and released the
# configuration, the service starts. If the configuration changes later, the
# service shuts down cleanly — Docker restarts it because of
# "restart: unless-stopped", and it comes back with the new values.
#
# This way the application drives the services through files and needs NO
# access to the Docker socket. On a machine that holds a wallet, that small
# detour is worth it: a socket would be equivalent to root.
#
#   entrypoint.sh <name> <command> [arguments...]

set -eu

NAME="$1"; shift
CONFIG_DIR="${CONFIG_DIR:-/config}"
CONF="${CONFIG_DIR}/${NAME}.conf"
READY="${CONFIG_DIR}/${NAME}.ready"
# Two seconds, not ten. It is a test for two files — it costs nothing, and the
# ten seconds were added in full to every start and every restart, times four
# services.
INTERVAL="${CONFIG_POLL_SECONDS:-2}"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

# --- 0. React to shutdown ---------------------------------------------------
# Without this the container hangs while waiting: this shell is PID 1, and
# PID 1 ignores SIGTERM as long as no handler is set. Docker then waits out the
# full grace period and only kills afterwards — for bitcoind that is ten
# minutes during which the container cannot be stopped.
# Once the service takes over via exec, it handles its own signals.
beenden() {
  log "Shutdown requested — stopping ${NAME}."
  exit 0
}
trap beenden TERM INT

# --- 1. Wait for the web interface to release us ----------------------------
if [ ! -f "$READY" ]; then
  log "Waiting for setup in the web interface."
  # Do NOT guess the port: which one is published on the outside lives in the
  # Compose file, not in here. A hard-coded number inside the container is
  # wrong for everyone who changes WEBUI_PORT — and it promptly contradicted
  # what was actually running next to it. The Compose file passes the value in;
  # if it is missing we would rather say nothing than something wrong.
  if [ -n "${WEBUI_PORT:-}" ]; then
    log "Open port ${WEBUI_PORT} of your server in a browser to do that."
  else
    log "Open the web interface in a browser to do that."
  fi
fi
# sleep in the background and wait for it: a signal arriving during a
# FOREGROUND sleep would only be delivered after it expires — the shell does
# not run traps while it is waiting for a command.
while [ ! -f "$CONF" ] || [ ! -f "$READY" ]; do
  sleep "$INTERVAL" &
  wait "$!" || true
done


SUM="$(sha256sum "$CONF" | cut -d' ' -f1)"

# Remember our own PID. In a moment the service takes over exactly this process
# via exec — so the watcher can address it specifically later. A hard-wired
# "kill 1" would be brittle: it is only correct as long as this container
# really runs the service as PID 1.
DIENST_PID=$$
log "Configuration found (${SUM%"${SUM#????????}"}...), starting ${NAME}."

# --- 2. Watcher: configuration changed -> clean restart ---------------------
# What matters is the TERM to PID 1: it lets the service shut down in an
# orderly fashion. For bitcoind that decides whether the chainstate survives
# intact — which is why the Compose file also sets stop_grace_period: 10m.
(
  while sleep "$INTERVAL"; do
    [ -f "$CONF" ] || continue
    NEU="$(sha256sum "$CONF" | cut -d' ' -f1)"
    if [ "$NEU" != "$SUM" ]; then
      log "Configuration changed — stopping ${NAME} for a restart."
      kill -TERM "$DIENST_PID" 2>/dev/null || true
      exit 0
    fi
    # Release withdrawn (e.g. service switched off in the web interface)
    if [ ! -f "$READY" ]; then
      log "Release withdrawn — stopping ${NAME}."
      kill -TERM "$DIENST_PID" 2>/dev/null || true
      exit 0
    fi
  done
) &

# --- 3. The service takes over PID 1 ----------------------------------------
# exec, so that Docker sends its signals straight to the service and not to
# this shell.
exec "$@"
