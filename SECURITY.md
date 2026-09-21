# Security

SatoshiCortex runs a node that is reachable from the internet and, later, a
Lightning wallet holding real money. This page records how that is secured and
what has been audited.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting
(Security → Report a vulnerability) or contact the maintainer of this
repository directly.

## Principles

- **No Docker socket.** The application controls the services through files in
  the shared `config` volume. On a machine holding a wallet, a Docker socket is
  equivalent to root.
- **Every service runs as UID 1000**, without special privileges (`cap_drop:
  ALL`, `no-new-privileges`) and with a process limit. The application
  additionally runs with a read-only filesystem.
- **Third-party software is signature-checked** before it enters an image:
  Bitcoin Core against at least three independent builder signatures from a
  pinned `guix.sigs` commit,
  Tor through Debian's package signature.
- **Secrets never leave the machine.** The application generates the RPC
  password itself and stores it with mode 0600; only the hash goes into the
  service configuration.

## What is reachable from outside — and what is not

The question that comes before the first satoshi lands on the machine: who can
reach the services' interfaces? Measured against the shipped
`docker-compose.yml` and the configuration templates.

**Exactly five ports are published:**

| Port | Bound to | Who can reach it |
|---|---|---|
| Web interface (default 3333) | `LAN_BIND`, default `0.0.0.0` | your home network — behind a sign-in |
| Bitcoin P2P 8333 | all interfaces | the internet. **Intended**: this is the participation |
| Lightning P2P 9735 | all interfaces | the internet. **Intended** |
| Watchtower 9911 | all interfaces | the internet, **only if you forward it** — needed for clearnet only; over Tor the tower has its own onion address |
| bitcoind RPC 8332 | `RPC_BIND`, default **`127.0.0.1`** | the server itself only |

**Not published** — and this is the more important half of the answer:

- **LND's gRPC (10009) and REST (8080).** No port, no onion service. LND cannot
  be reached from your home network at all.
- **All ZMQ ports (28332, 28333, 28334).**
- **Tor's SOCKS ports (9050, and 9052 for the reachability check) and HTTP
  tunnel (9080).** Tor has **no control port** at all — see below.

These services do listen on `0.0.0.0`, but that is the address *inside* their
own container. They are reachable only within the compose network
`satcortex-netz`, a private /24 (`10.83.33.0/24` unless `NETWORK_PREFIX` says
otherwise) in which every service has a fixed address.

### Onion services, and why Tor has no control port

Three onion services — Bitcoin, Lightning, watchtower, each with its own
address — are defined in **Tor's own configuration** (`HiddenServiceDir`) and
point at the fixed container addresses of `bitcoind` and `lnd`. Their keys live
under `DATA_FAST/tor/`. Which services exist follows the visibility setting:
"Tor only" and "Tor and clearnet" have all three, "Announce nothing" has none.

The obvious alternative — letting bitcoind and LND create these services
themselves through Tor's **control port** — has three problems:

- **The services end up unreachable.** Neither daemon names a target, so Tor
  uses `127.0.0.1` — inside *its own* container, where nothing listens. The
  addresses get announced and lead nowhere.
- **LND's services vanish whenever Tor restarts.** The check that would
  recreate them is disabled in LND v0.21.3-beta
  (`healthcheck.torconnection.attempts` defaults to 0), and even when enabled it
  does not recreate the watchtower's service.
- **The control port was open to the whole compose network.** It was protected
  by a cookie file under `/fast/tor` — and every container mounts `/fast`,
  including the web interface. Whoever holds the control port can reconfigure
  Tor.

The control port is now **gone**. Nothing on this machine can reconfigure Tor
at runtime.

### Encrypted?

Two different answers, and both belong on the record:

- **Application → LND: yes, and verified.** TLS, and the application checks the
  certificate against LND's own `tls.cert`
  (`ssl.create_default_context(cafile=...)`) — verification is not disabled.
  For that to work over the compose name, `tlsextradomain=lnd` is set in
  `lnd.conf`. On top of that every call requires a macaroon, and the
  application holds one **without `onchain:write`**.
- **Application → bitcoind: no.** The call goes over `http://`, because Bitcoin
  Core cannot do TLS on its RPC interface at all. It is authenticated via
  `rpcauth`, but not encrypted. That path never leaves the container network.

### Who may use the RPC interface

By default exactly one network:

    rpcallowip=10.83.33.0/24

That is the compose network the application itself speaks from — and nothing
else. A range like `172.16.0.0/12` would not do: Docker assigns addresses
inside it freely, and it would admit any peer coming from 172.16/12, which
some home networks use. With fixed addresses it is exactly the /24 of the
stack. Your home
network is added **only** if you switch on the release under *Settings →
Wallet software* — then a second line with your specific network appears, and
`RPC_BIND=0.0.0.0` must additionally be set in your `.env`. Two conditions, not
one.

`rpcallowip=0.0.0.0/0` is never produced; there is a dedicated test against it.

### The one gap that remains

`satcortex-netz` is an ordinary bridge network, **not** `internal`. Another
container on the same machine, deliberately attached to that network, can reach
LND's REST interface and the ZMQ ports — and ZMQ has no authentication
whatsoever. This is not possible from outside or from your home network; it
takes a container you attach yourself.

Anyone running untrusted containers on the same machine should not give them
this network.

## Audit of 2026-08-23

Carried out before the first build, because otherwise a user would be left
exposed. Eleven findings, all fixed.

### Critical

**1 — No authentication.** Every endpoint was open. Anyone who knew the address
on the home network could configure the node. *Fixed:* account creation now
comes BEFORE the wizard; everything else sits behind a sign-in. Passwords with
scrypt (n=2^15), session cookie `HttpOnly` and `SameSite=Strict`, throttling
after eight failed attempts.

**2 — A running node could be reconfigured.** Completing the setup could be
invoked arbitrarily often. That allowed switching Tor off, unleashing the
upload and pushing connections down to 8 — the last of which makes an **eclipse
attack** considerably easier. Because the watcher in the container reacts to
the changed checksum, the change took effect immediately. *Fixed:* possible
only once (409 afterwards), and only while signed in. Since 2026-09-14 the
wizard refuses fewer than 12 connections at all: only from there does the node
have its two block-only peers.

**3 — Five known vulnerabilities in Starlette 0.49.3**, among them a remotely
triggerable unauthenticated denial of service (PYSEC-2026-249) and a missing
Host header check that defeats path-based security checks (PYSEC-2026-161) —
exactly what this application does. *Fixed:* fastapi 0.141.1 with starlette
1.6.0. `pip-audit` reports nothing any more.

### Medium

**4 — RPC credentials were thrown away.** New ones were created every time the
configuration was written; the plaintext password was never stored. The
application could never have talked to bitcoind. *Fixed:* generated once,
stored with mode 0600, reused afterwards.

**5 — Unbounded payload.** A single unauthenticated call wrote 195 kB to disk,
repeatable at will. *Fixed:* capped at 4 kB, and behind the sign-in.

**6 — Containers without privilege dropping.** No `cap_drop`, no process limit,
no read-only filesystem. *Fixed.*

### Low

**7 — Unknown API paths returned the start page** (HTTP 200 with HTML instead
of 404). *Fixed.*

**8 — CSRF without its own defence.** Form POSTs from foreign pages already
failed on the JSON requirement, and without a CORS release browsers block the
rest. *Improved:* session cookie with `SameSite=Strict`.

### Checked and sound

- **Path traversal** via `../`, percent-encoded and double-encoded variants:
  all rejected, the start page is returned instead of a file.
- **Configuration injection:** every value that flows into `bitcoin.conf` is a
  numeric field with an upper and lower bound. This matters because Bitcoin
  Core executes shell commands for its `*notify` directives — anyone able to
  write the configuration would have code execution.
- **Error messages** reveal no internals.
- **Script injection:** the interface sets server data exclusively via
  `textContent`, never via `innerHTML`.

### Open

- **OIDC** (Pocket ID, Authentik, Keycloak) is implemented: authorization code
  with PKCE — and PKCE is not optional here, it is what carries the exchange:
  Pocket ID no longer issues secrets for its clients at all ("only public
  clients are supported"). A configured secret is sent along; a missing one is
  omitted entirely rather than sent empty.
  Further: addresses from the provider's discovery document, ID token with a
  verified signature (RS256/ES256 against the provider's JWKS), plus issuer,
  audience, expiry and nonce. Who may enter is decided by the identity provider
  through its group release.
  The local account remains as an **emergency door** and then accepts passwords
  only from requests that did not come through a reverse proxy. That assumes
  the interface port is not forwarded to the internet — what goes out are 8333,
  9735 and optionally 9911, nothing else. Over Tor, not even those.
- **HTTPS** is not supplied by SatoshiCortex itself. On a home network that is
  defensible; anyone exposing the interface belongs behind a reverse proxy with
  TLS.
- **Changes during operation** need their own explicit path with confirmation.
  At present the setup is final.

## Keeping it that way

Every finding has a test in `app/backend/tests/test_sicherheit.py`. They fail
if the protection is ever removed again. CI runs the tests before every image
build.
