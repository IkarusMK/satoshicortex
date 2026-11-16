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
  ALL`, `no-new-privileges`) and with a process limit on all four. The
  application additionally runs with a read-only filesystem.

  Since 2026-09-22 this holds for **all four**: `bitcoind`, `lnd` and `tor`
  ran with a writable root until then, `lnd` included — the container holding
  the wallet. Their own data lives in mounted volumes; what they need beyond
  that is a `/tmp`, and they get it as a `tmpfs`.
- **Third-party software is signature-checked** before it enters an image:
  Bitcoin Core against at least three builder signatures from a pinned
  `guix.sigs` commit, **LND** against a pinned Lightning Labs key set with its
  extracted binaries re-checked against the signed manifest, and Tor through
  Debian's package signature. Every one of these fails the build closed.

  **The Python tree is hash-locked** (`app/backend/requirements.lock`,
  generated against the image's own Python version). `pip install
  --require-hashes` accepts only those exact files — for the whole tree, not
  just the names listed in `requirements.txt`. Until 2026-09-22 everything
  behind the direct dependencies resolved fresh on every build, which made
  the "same result in half a year" claim in that file untrue.

  **What remains unverified, stated plainly:** the GeoIP city list from DB-IP
  is an unauthenticated download whose filename is derived from the current
  month and therefore cannot be pinned. The mining-pool list used to come
  from a moving branch and is now pinned to a commit.
- **Secrets never leave the machine.** The application generates the RPC
  password itself and stores it with mode 0600; only the hash goes into the
  service configuration.
- **Our own images can be verified, not just trusted.** Since 2026-09-23 every
  image built from a release carries a signed SLSA build provenance
  (`actions/attest`, pinned to a commit), stored next to the image in the
  registry. `gh attestation verify oci://ghcr.io/ikarusmk/satcortex:<version>
  --owner IkarusMK` checks it. Only the job that pushes images may mint the
  signing token; a test enforces that, and that every third-party action in
  both workflows is pinned to a full commit hash.

## What is reachable from outside — and what is not

The question that comes before the first satoshi lands on the machine: who can
reach the services' interfaces? Measured against the shipped
`docker-compose.yml` and the configuration templates.

**These ports are published:**

| Port | Bound to | Who can reach it |
|---|---|---|
| Web interface (default 3333) | `LAN_BIND`, default `0.0.0.0` | your home network — behind a sign-in |
| Web interface over HTTPS (default 3334) | `LAN_BIND`, default `0.0.0.0` | your home network — the same interface, encrypted with the node's own certificate. `WEBUI_TLS=off` switches the listener off |
| Bitcoin P2P 8333 | all interfaces | the internet. **Intended**: this is the participation |
| Lightning P2P 9735 | all interfaces | the internet. **Intended** |
| Watchtower 9911 | all interfaces | the internet, **only if you forward it** — needed for clearnet only; over Tor the tower has its own onion address |
| bitcoind RPC 8332 | `RPC_BIND`, default **`127.0.0.1`** | the server itself only |
| LND REST 8080 | `LND_REST_BIND`, default **`127.0.0.1`**, and **no fixed port** unless `LND_REST_LAN_PORT` is set | nobody by default — Docker picks a random port on the server itself. Set both for the VPN route to external wallets; then your home network |
| Electrum service 50001 | `ELECTRUM_BIND`, default **`127.0.0.1`**, and **no fixed port** unless `ELECTRUM_LAN_PORT` is set | nobody by default. Set both for hardware-wallet apps at home; then your home network, and over Tor whoever knows its onion address. The Electrum protocol has **no sign-in**: whoever reaches the port can ask about addresses — and so can test whether one belongs to an account registered here |

**Not published** — and this is the more important half of the answer:

- **LND's gRPC (10009)** — no port, no onion service. **LND's REST (8080)**
  only as described in the table: by default nobody outside the compose network
  reaches it. An onion service for it exists only while at least one device is
  connected over Tor under *External wallets*; its address is announced
  nowhere.

  When REST is reachable (VPN route or that onion service), every call that does
  anything needs a macaroon — with one exception that belongs on the record:
  LND's wallet-unlocker calls (`/v1/state`, `/v1/unlockwallet` and its
  siblings) take no macaroon. They reveal whether the wallet is locked and
  accept unlock attempts, which only succeed with the wallet password.
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
  `lnd.conf`. On top of that every call requires a macaroon. The application
  bakes its own with exactly the rights it uses (`EIGENE_RECHTE` in `lnd.py`);
  since sending on-chain arrived on 2026-09-10 that includes `onchain:write`,
  and every endpoint that moves money checks the PIN first — or, when no PIN
  is set, the account password (since 2026-11-15; before that, no PIN meant
  no second check at all). It does **not**
  include the right to issue keys: keys for external wallets are baked with
  LND's `admin.macaroon`, only on an explicit request behind the PIN.
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
scrypt (n=2^15), session cookie `HttpOnly` and `SameSite=Strict` (today
`Lax` — see finding 8), throttling after eight failed attempts.

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

*Later:* the cookie is `SameSite=Lax` since the sign-in through an identity
provider arrived — the return from the provider is a navigation from another
site, and under `Strict` the browser drops the cookie there, so the sign-in
silently started over. `Lax` still keeps the cookie off writing calls from
other sites. Since 2026-11-15 there is a second layer that does not depend on
the cookie: writing calls whose `Sec-Fetch-Site` says `cross-site` or
`same-site` (another port on the same host counts) are refused. It reads only
what the browser itself reports, so it works unchanged behind a reverse proxy.

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

  Since 2026-11-15 the detection fails **closed**. Until then a request counted
  as "not through a proxy" when none of four forwarding headers was present —
  a proxy that adds none of them let the internet reach the password form.
  Now any of the common proxy headers (even empty), a caller inside the
  container network (its gateway is the host itself, where a host-network
  proxy sits) and, with an identity provider configured, a `Host` equal to the
  provider's callback host all close the door. A browser at home reaching the
  published port keeps its own address, so the door stays usable from the
  home network — by IP, not by the public name. Creating the first account
  follows the same rule.

  **Who may enter is the provider's decision alone:** the application checks
  no group or claim of its own. Restrict the client to your group in the
  provider; an unrestricted client lets every user of the provider in.
- **HTTPS** — since 2026-11-15 the interface also answers on a second port
  (default 3334) with a certificate the node makes for itself: EC P-256, the
  key created with mode 0600 under the configuration directory, kept across
  restarts. The browser warns on the first visit, because nobody it knows
  signed it; the interface shows the certificate's SHA-256 fingerprint to
  compare. The plain port stays exactly as it was, so a reverse proxy in front
  keeps working. Over HTTPS the session cookie is `__Host-satcortex_sitzung`
  (`Secure`, bound to the host); both names are accepted, so nobody is signed
  out by the update.
- **Changes during operation** go through one narrow path, and only that one.
  `/knoten/netzwege` writes network visibility (Tor, clearnet, the announced
  addresses) in a single write, because every configuration change restarts
  bitcoind. It deliberately does **not** touch the upload budget, the peer
  count or the RPC line: pushing the peer count down makes an eclipse attack
  considerably easier, which was finding 2 of the audit above. Everything else
  decided during setup stays decided — completing the setup a second time is
  refused with 409.

  (Until 2026-09-22 this section claimed "the setup is final". That was no
  longer true, and it undersold the work: the narrow path exists precisely so
  that the dangerous fields cannot be reached.)

## Keeping it that way

Every finding has a test in `app/backend/tests/test_sicherheit.py`. They fail
if the protection is ever removed again. CI runs the unit tests, `pip-audit
--strict` and `bandit` before every image build; the image-level checks (the
container starts, refuses access without a sign-in, ships its licence texts)
run on pull requests and on pushes to `main`.

## Audit of 2026-09-22 — the build path

Carried out on the repository's own CI, because everything above is only worth
as much as the pipeline that ships it.

- **Every GitHub Action is now pinned to a commit hash.** They were on mutable
  major tags (`@v5`). A moved tag in an unattended nightly build that holds a
  registry token would have reached every operator through `:latest`.
- **`packages: write` now belongs to the publishing job alone.** It used to
  apply to the whole workflow, including the job that runs `pip install` and
  therefore executes third-party install hooks.
- **`actions/checkout` no longer leaves the token in `.git/config`**
  (`persist-credentials: false`), which is what made the point above reachable.
- **Upstream version strings no longer reach a shell.** The nightly build
  takes release tag names from `bitcoin/bitcoin` and `lightningnetwork/lnd`
  and used to interpolate them into a `run:` block. Git permits backticks and
  `$` in tag names. They now travel through the environment.
- **`renovate.json` was not valid JSON** — a trailing comma — so the component
  that watches for new third-party versions could not read its configuration.

- **The dependency tree is hash-locked and the last three containers got a
  read-only root.** Both were held back from the first round because the only
  honest proof is a full build and a stack coming up — neither can be shown on
  a laptop without Docker. They went in once CI could be watched.

## Audit of 2026-11-15 — the application

A full pass over the application itself (sign-in and web layer, money paths
and LND, the Electrum service, configuration writing, outbound fetches), with
every finding reproduced against the real code before it was fixed and every
fix proven by a test that failed on the old code. Bitcoin Core, LND and Tor
themselves were out of scope. The aim was set by the owner: nobody from
outside gets in or changes anything — and handling stays as easy as before,
no new prompts for settings.

### High

**1 — A session could write its own lines into `bitcoin.conf` and
`lnd.conf`.** The single-line check rejected `\n` and control characters but
not the Unicode line separators U+2028, U+2029 and U+0085. The files were
re-read with `splitlines()`, which honours them, and written back with `\n`
— so the next write turned the separator into a real line break. An alias
`x⟨U+2028⟩no-macaroons=true` produced a line `no-macaroons=true` in
`lnd.conf`; an announced address `fe80::1%x⟨U+2028⟩startupnotify=…` produced
a `startupnotify=` line in `bitcoin.conf`, which Bitcoin Core runs through a
shell. A signed-in session was enough; the PIN did not help. *Fixed:* every
single-line value must be printable, addresses are parsed and written in
their normalised form (no scope ids), the files are split on `\n` only, and
the writer itself refuses any content with a separator other than `\n`.

**2 — The Electrum service could be driven out of memory without a sign-in.**
One 9 KB line with 100 header requests made a 32 MB answer; four connections
took the server to 310 MB against the container's 400 MB. *Fixed:* a shared
header budget per line, a cap on the answer, answers written piece by piece.
Measured afterwards: 35 MB.

**3 — Without a PIN, a session alone could move money.** The PIN was optional
and, when not set, nothing else was asked. *Fixed, by the owner's choice:* the
PIN stays optional; without one, every money path asks for the account
password in the same field.

### Medium

- **Emergency door failed open** behind a proxy that sends no forwarding
  header, and the first account could be created through the proxy. Now fails
  closed (see the OIDC section above).
- **Sign-in lock-out:** one counter for everyone — eight wrong passwords from
  any device locked the owner out. Now counted per device, with a global
  ceiling that slows guessing without shutting the owner out.
- **PIN lock-out:** one counter for all sessions — a stolen session could keep
  the owner from closing a channel. Now counted per session, under both cookie
  names.
- **Electrum:** no brake on the load it puts on Bitcoin Core (now a token
  bucket and its own small thread pool), every new connection forced a full
  re-read of the accounts (now at most every 10 s, or on a real change), and
  running out of file handles stopped the accept loop for good (now it logs
  and carries on). Connections count from the moment they are accepted.
- **`time_lock_delta`** could be set down to LND's protocol minimum of 18 on
  every channel. Floor now 40; nothing the application sets itself is lower.
- **Seed words, keys and the PIN over plain HTTP** on the home network — the
  built-in HTTPS port above.

### Low

- The backup target accepted any URL (fragment, query, internal hosts), and
  fetching it followed redirects to other hosts with the credentials. Now
  `http(s)` only, no internal targets, redirects only on the same host.
- Peer and watchtower addresses could point at internal ports (a port-scan
  oracle). Internal targets are refused before dialling.
- Secret files were briefly visible with mode 0644 before `chmod`; the comments
  claimed the opposite. Now created with 0600 from the first byte — wallet and
  backup passwords, PIN, account, sessions, failed sign-ins, state.
- The log said the application's macaroon lacked `onchain:write`; it has it,
  deliberately. The text is true now.
- Sending and opening a channel twice at once both ran. The second now gets
  "already running".
- A flood of identity-provider starts cleared all open sign-ins; the oldest
  are evicted now, and starts are rate-limited per device.
- `/openapi.json`, `/api/doku` and `/redoc` answered without a sign-in. They
  still exist, behind it.
- The news-feed guard against DTDs only looked at UTF-8; UTF-16 slipped past
  (expat's own limit still stopped it). Foreign encodings are refused now.
- Renovate merged patch updates of GitHub Actions on its own — actions that
  run in the job holding `packages: write` and `id-token: write`. They are
  merged by hand now, and every update waits seven days before it is proposed.
- Smaller things: deeply nested JSON on the Electrum port, a NUL byte in a
  path and an invalid channel point each ended in an unhandled error; the
  `rpcallowip` check accepted IPv4-mapped and reserved ranges; subscriptions
  and silent connections on the Electrum port were unbounded; log lines for
  rejected Electrum connections were not throttled.

### Checked and sound

Passwords and sessions (scrypt, only token hashes stored, a new token per
sign-in), no script injection anywhere in the interface (server data only via
`textContent`, a strict CSP), the identity-provider flow (PKCE, pinned
algorithms, issuer, audience, nonce), PIN storage and comparison, TLS to LND,
the seed never stored or logged, input checks of the Electrum service, size
and time limits on every outbound fetch, the hash-locked dependency tree.
