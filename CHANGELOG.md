# Changelog

All notable changes to SatoshiCortex. Format loosely after
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning after
[SemVer](https://semver.org/).

## [1.0.4] — 2026-09-22

The two findings from the audit that could not be proved on a laptop. Both
needed a real build and a stack coming up, so they waited until CI could be
watched. It could: the image built with `--require-hashes`, and the stack came
up with every container read-only.

### Added: the dependency tree is hash-locked

`requirements.txt` pins its direct dependencies with `==` and said so —
"so that a build today gives the same result in half a year". It did not.
Everything *behind* those names — `pydantic-core`, `h11`, `anyio` and a dozen
more — resolved fresh on every build.

`requirements.lock` now holds the whole resolved tree, twenty-three packages,
each with its checksums, resolved against **the image's** Python version
rather than whatever the maintainer happens to run. `pip install
--require-hashes` accepts only those exact files.

This covers what `pip-audit` structurally cannot: for a package that was
malicious when it was uploaded there is no advisory yet. `h11` sits in the
path of every request to the wallet interface.

The lock is generated, not maintained, so two guards keep it honest: every
pinned package must appear in it at the same version, and every package must
carry at least one checksum.

### Changed: all four containers run with a read-only root

Only the application did. `bitcoind`, `lnd` and `tor` had a writable root
filesystem — `lnd` above all, being the container that holds the wallet. Their
data lives in mounted volumes; what they need beyond that is a `/tmp`, and
they now get it as a `tmpfs`.

## [1.0.3] — 2026-09-22

### Audit of 2026-09-22 — the money paths

A deliberate audit of the six operations that move money, plus the claims the
interface makes. Seven findings, all fixed. The most expensive one first.

#### Fixed: a payment without an answer was reported as a failure

The backend was careful here. When LND does not answer in time it raises
`Beschaeftigt`, the endpoint turns that into HTTP 504, and the text for it
exists in both languages:

> "No answer within the waiting time. The payment may still be on its way —
> do NOT repeat it, check the channels instead."

That text was unreachable. The numbers did not line up:

| | |
|---|---|
| LND payment timeout | 60 s |
| plus slack | 20 s |
| **server answers after at most** | **80 s** |
| **interface gave up after** | **25 s** |

On abort there is no `detail`, so the handler fell through to a generic
"Error" — and the `finally` block re-enabled the button. The interface said
"that failed" about a payment that was in flight, and offered to repeat it.
A comment two lines from the call even said "a payment can be on its way for
up to a minute".

Money paths now use their own timeout, longer than the server's, and a shared
`geldfehler()` decides what a failure means. When nothing is decided — a
client abort *or* the server's own 504 — the panel says so and the button
stays locked. A guard test compares the two timeouts across the file boundary,
so they cannot drift apart again.

#### Fixed: two irreversible on-chain paths could not tell "timeout" from "gone"

`Beschaeftigt` inherits from `NichtErreichbar`. Paying an invoice and
rebalancing caught it separately; sending on-chain and opening a channel did
not, so a timeout became "LND is not answering" — which reads as "nothing
happened".

It matters more here than anywhere else: a Lightning invoice cannot be paid
twice, the payment hash prevents it. A second on-chain send is simply a second
transaction.

#### Fixed: the fee limit could not express "only if free"

`int(wunsch.gebuehrengrenze) or lnd.gebuehrgrenze(betrag)` — a zero, which is
a valid instruction ("pay only if the route costs nothing"), was replaced by
the computed default. The field is now `Optional[int]` defaulting to `None`.
The interface never sent the field at all, so nothing changes for it.

#### Fixed: one of the six PIN checks was not first

Deleting the wallet asked whether wallet work was running *before* checking
the PIN — while the comment directly below that line read "the PIN FIRST,
before any other check". The line contradicted the sentence explaining it.

#### Fixed: opening a channel did not check the minimum size

The estimate did; the open did not. Calling the endpoint directly went around
it.

#### Fixed: a language switch left two places in the old language

`zeichneGegenstellenwege()` built its list once ("once is enough") and the
list holds translated text. The switch clears four caches and redraws — this
function returned immediately, and nothing else touches that element. Whoever
switched to English kept that list in German until they reloaded. The same
applied to the `aria-label`s of the twenty-four seed fields, where only a
screen reader would ever have noticed.

The trap is documented in this repository, in `kennzahl()`. The lesson had
been learned in one place and not applied in two others.

### Audit of 2026-09-22 — what the interface claims

#### Fixed: "not measured" was displayed as a measurement

For a block this node did not witness, the backend deliberately sends `None`:

```python
# Explicitly None instead of zero: we were not there,
# and a zero would look like a measurement.
"bekannte_tx": None,
```

Four places in the interface rendered `bekannte_tx || 0` and showed
"0 / 2431 tx" — exactly the measurement the backend had refused to invent,
and for the one number a private node exists to produce. In the same table
row, `verweildauer_ms` from the same dict was handled correctly.

The strip now shows the total alone and explains in its tooltip why the other
number is missing; the table shows a dash like its neighbouring columns.

#### Fixed: two numbers the interface did not own

The dust limit (546 sat) and the restore scan window (2500 addresses) were
literals in the translations while the backend owned the real values. Rather
than plumbing a constant through an endpoint, a guard test now compares them
across files — both were verified to fail when the backend constant is changed.

### Checked and sound

- All 89 messages the backend can send have a text in both languages, so a raw
  key can never reach a user.
- Every message text containing a placeholder always gets that field filled.
- Of 400 element ids the interface looks up, none is missing from the markup.
- Of 286 interface functions, only two guarded themselves with "once is
  enough"; both are covered above.
- The five interface sentences that state a hard number about the network are
  correct: the ppm arithmetic, Core's 24-hour upload window, and that an
  exhausted budget stops only *historical* blocks.

### Audit of 2026-09-22 — sign-in, the PIN, and stored data

#### Fixed: the lockout counters could be outrun by running in parallel

Checking the lockout and recording the attempt were two separate steps with no
lock between them — and scrypt sits in that gap, which makes it a long moment.
Measured with forced interleaving rather than assumed:

| | allowed | actually got through |
|---|---|---|
| Sign-in, 6 simultaneous attempts | 1 | **6** |
| Transaction PIN, 5 simultaneous attempts | 5 counted | **3 counted, 2 lost** |

This is the counter standing between a hijacked session and the six operations
that move money. Both counters are now taken under one lock, and the attempt is
recorded *before* the expensive comparison rather than after it.

#### Fixed: failed sign-ins were counted under the name the attacker types

The dictionary grew without limit — one request per made-up name, no sign-in
required, on a container with a 400 MB limit that has already been killed once
for exactly this reason.

A simple cap would have been the wrong fix: entries could then be pushed out
deliberately, which would clear the lockout on the real account. There is
exactly one account here, so there are now two buckets — that account, and
everything else. A test covers the eviction attack specifically.

#### Fixed: the sign-in lockout did not survive a restart

Sessions are deliberately written to disk, with the reasoning that "a restart
can be triggered from the interface". The lockout was memory-only, so the same
restart cleared it. It is now persisted the same way.

#### Fixed: the HTLC table was never cleaned up

`htlc_aufraeumen()` existed and nothing ever called it, while its sibling has
been wired into the daily watcher all along. On a node that forwards payments a
row is written for every HTLC event — so the table grew without bound precisely
on the node doing what the software is for.

#### Fixed: a write transaction was held open across two RPC calls

Recording a block opened a write transaction and then computed the values for
the next call — including a fee lookup (30 s timeout) and a pool lookup (20 s).
The transaction could therefore stay open for up to fifty seconds while every
other writer gives up after twenty ("database is locked"). The lookups now
happen before the write.

#### Fixed: valid JSON that is not an object crashed the state load

`laden()` catches malformed JSON and starts over, which is the documented
policy. A file containing `null`, `42` or `[]` parses fine and then raised an
uncaught `AttributeError` — at startup, on the file whose loss costs the entire
setup.

Also: two cleanup functions lacked the `max(1, ...)` clamp their sibling has,
where a zero would have emptied the table.

### Audit of 2026-09-22 — the stack, setup and recovery

Both came through largely clean, which is worth recording as plainly as the
findings.

The **seed** has no leak path: the twenty-four words live only in an in-memory
holder, never reach the log, the state file or a response, expire after thirty
minutes, and the read-back check cannot be walked around — the four positions
are fixed before the question is asked, and wallet creation cannot reach the
words without that holder.

The **eclipse-attack gate** from the 2026-08-23 audit still holds, and more
strictly than "once": the one path that changes anything after setup
deliberately excludes the peer count, the upload budget and the RPC line.

`entrypoint.sh` targets the real service PID (it captures `$$` before `exec`,
which does not change the PID), the config file is swapped atomically so a
half-read is not reachable, and `.ready` is always written after `.conf`.
Every free-text value entering a config file is rejected if it contains a line
break, and `rpcallowip` cannot be widened to `0.0.0.0/0`.

Two things came out of it:

- The one writer in `nodeconfig.py` that did not defend itself like its
  neighbours now does. Not reachable today — every caller passes an internally
  computed path — but it was the exception in a file whose rule is the point.
- **`SECURITY.md` claimed "the setup is final".** That was no longer true, and
  it undersold the work: the narrow path exists precisely so the dangerous
  fields cannot be reached. Corrected.

### Audit of 2026-09-22 — the build path

See SECURITY.md for the detail. In short: every GitHub Action is now pinned to
a commit hash instead of a movable tag; `packages: write` belongs to the
publishing job alone rather than to the job that runs `pip install`;
`actions/checkout` no longer leaves the token in `.git/config`; upstream release
tag names no longer reach a shell (git permits backticks and `$` in tag names);
the mining-pool list is pinned to a commit instead of a moving branch; and
`renovate.json` was not valid JSON, so the component watching for new
third-party versions could not read its own configuration.

## [1.0.2] — 2026-09-21

### Fixed: an explanation that printed itself nine times

Reported from operation, with a screenshot: the paragraph under the network
fee median stood **nine times** in a row, filling most of the panel.

`zeichneNetzgebuehren()` runs on every refresh and attached that paragraph
with `zahlen.after()` — as a new sibling. Nothing ever removed it. The same
trap had already been hit once before in this project, which is why
`zeigeUebersicht()` carries the note "a fixed element instead of `.after()`".

### Changed: the fee spread is shown, not explained

The paragraph existed to explain why the median does not sit in the centre of
the interquartile range. The reaction to it was fair: *"what on earth is that
huge text? … couldn't you just do: 50 % 0–100, the other 50 % 100–600?"*

You can, and it is the better answer. The panel now carries a distribution
across five round steps — 0 · 1–9 · 10–99 · 100–999 · 1000+ ppm — as a slim
bar with the shares written beside it. It shows the skew at a glance and adds
what the paragraph never said: **where the mass actually sits.**

The shares are whole percentages that add up to exactly 100 (largest
remainder). Three thirds rounded separately would read 33 + 33 + 33, and
under a line that claims to be a distribution a reader who adds them up
deserves to be right.

Measurements taken before this version have no distribution stored; those
days keep the old interquartile sentence rather than showing an empty bar.

### Added: block time on the overview

On request from operation: how many blocks until the next halving, the
estimated date, and what the reward becomes.

All of it is arithmetic on numbers the overview already fetches, so the panel
costs no extra call. Three details are deliberate:

- **It counts from the header height**, not from our own verified height.
  During the initial sync the latter is years behind, and counting from it
  would describe a halving that happened long ago.
- **The pace is measured on this chain** — the real spacing over the last
  26,280 blocks (about half a year), not the textbook ten minutes. Why not
  the current difficulty period: this projects over more than a year, and
  retargeting pulls the two-week pace back to ten minutes every 2016 blocks.
  What half a year measures is the lasting deviation, and that is the figure
  this projection needs.
- **It says which of the two it used.** Before the sync completes no own pace
  is measurable; the panel then states that it is computing with the
  protocol's target spacing instead of claiming a measurement.

The estimate is given as month and year. Over more than a year, a day would
be a claim, not an estimate.

The reward is computed by integer shifting, the same way Core's
`GetBlockSubsidy` does it — 3.125 BTC is not representable in floating point,
312,500,000 satoshi is.

### Added: the application reports its own new versions

The version panel checked Bitcoin Core and LND but never SatoshiCortex
itself. A node could sit on an old version with a newer one published and the
interface would not mention it.

### Changed: the block view now shows what the application already knew

Each block in the strip carries its time, transaction count and fee total.
The header measures its own text and drops to a shorter form rather than
running into the neighbouring column.

### Added: `AGENTS.md`

Working conventions for coding agents, stating the decisions that look like
accidents: the source is German on purpose, there is no Docker socket, every
figure comes from your own node, large answers are streamed. All check
commands in it were executed before it was written.

## [1.0.1] — 2026-09-21

### Fixed: the price was never fetched on the overview

Reported from operation: the BTC price on the overview page seemed never to
load.

It never did. The panel (`#d-kurs-wert`, default "—") is filled by
`zeichneKursKurz()`, which is only ever called from `ladeKurs()`. And
`ladeKurs()` only ran when switching to the news or calculator view —
although its own guard clause explicitly permits the overview:

```js
if (ANSICHT !== "news" && ANSICHT !== "rechner"
    && ANSICHT !== "uebersicht" && !sofort) return;
```

A half-finished rebuild: the condition was widened, the call forgotten.
Anyone reloading and staying on the overview saw a dash forever; only a
detour into another view filled the panel.

`zeigeUebersicht()` now triggers it itself — not awaited, like the world map
beside it: the endpoint only reads from the cache.

Related question answered along the way — *"do I have to wait 4:30 min to see
the price?"* No. The five-minute cycle is the *refresh*. On startup the
application fetches once immediately, and a browser reload does not touch the
server's cache at all.

### Fixed: "middle of the network" was a label that contradicted itself

The fee panel showed `Median 100 ppm · middle of the network 1–600 ppm`, and
the question came promptly: reading "middle", you compute (1+600)/2 = 300 and
find 100 next to it.

Both numbers are right. 100 is the **median** — half of all directions charge
less — and 1–600 is the interquartile range. The median does not sit in its
centre because of the shape of the network: a great many directions stand at
zero or one ppm, and there is barely a ceiling at the top.

So the number was never wrong, its name was. The range now says *what* lies
in it ("the middle 50 %"), and where the median falls noticeably off centre,
a sentence below explains why — only then.

## [1.0.0] — 2026-09-19

### Fixed: a full mempool took the whole interface down

Reported from operation: with a full or nearly full mempool, the tile view
would not load any more.

It was not the tiles. The endpoint fetched `getrawmempool True` in one go —
the entire answer at once, and in three forms simultaneously: as bytes from
`read()`, as a string from `decode()`, and as objects from `json.loads()`.
Measured against Core's own field list (`rpc/mempool.cpp`, `entryToJSON`):

| Transactions | JSON | Peak while reading |
|---|---|---|
| 10,000 | 4.8 MB | 26 MB |
| 50,000 | 23.8 MB | 134 MB |
| 150,000 | 71.4 MB | **397 MB** |

The `app` container's memory limit is 400M. A full mempool was enough for the
OOM killer to take it — and because it carries `restart: unless-stopped`, the
whole web interface went away and came back. Not just the tiles.

The mempool is now read as a **stream**, the same way the LND network graph
already was: `rpc.Knoten.brocken()` reads the answer in chunks, and
`mempoolstrom.paare()` hands out one transaction at a time. What stays in
memory is the *output* — four numbers per transaction — not the input.

Measured after the change: **0.20 MB, whether the answer holds 500
transactions or 32,000.** Flat, not linear.

Two things that are deliberately not silent: an answer larger than any
plausible mempool (256 MB) aborts rather than being truncated, and a
connection that ends mid-document raises instead of returning a short list. A
tile view built from half a mempool would look right and be wrong.

While writing the test for this I first measured my own test harness — it
encoded the whole document inside the measurement, which made the parser look
like it was leaking. The fix was in the test; the note is here because the
mistake is easy to repeat.

### The release itself

First public release. Everything before this date happened in a private
repository and is not carried over — this is day one.

What the release contains:

### The stack

Four containers, all images built from source in this repository, no
third-party images, no `:latest` tags:

- **bitcoind** — Bitcoin Core, built from the official release. The build
  imports the builder keys from a pinned `guix.sigs` commit and requires at
  least three valid signatures.
- **lnd** — Lightning Network Daemon, GitHub release verified against the
  pinned Lightning Labs key.
- **tor** — Debian package, verified by apt against the Debian archive key.
- **app** — SatoshiCortex itself: setup wizard, dashboard, node operation.

No Docker socket. The application steers the services through files in a shared
volume; on a machine holding a Lightning wallet, a Docker socket would be
equivalent to root.

### Setting it up

`cp example.env .env`, `docker compose up -d`, open the web interface. A
seven-step wizard handles the rest: storage, performance limits, network
visibility, wallet software access, account. Everything it decides can be
changed later.

The chain syncs in the background — days to weeks. `lnd` runs from the start
and waits; nothing has to be installed afterwards.

### Running a node

- **Full archival node**, un-pruned, serving the whole chain to newcomers.
- **Reachable**, over clearnet and/or Tor. Tor-only needs no port forward at
  all: Bitcoin, Lightning and the watchtower each get their own .onion address.
- **Block filters** (BIP158) for light wallets.
- **Your own wallet software** — Sparrow and others — can use the node without
  a key ever entering it.

### Lightning

- Create a wallet with the seed on paper and a read-back check, or restore one
  from twenty-four words and a channel backup.
- Open and close channels, public or private, with an on-chain fee estimate
  beforehand.
- Pay and receive, issue invoices, rebalance liquidity between your own
  channels.
- Set fees per channel, or let the node measure the network median itself once
  a day and follow it inside a four-week band.
- Run a watchtower for other people's channels, and have your own watched.
- Channel backup pushed to a WebDAV target on every channel change.

### Safety

- Everything behind a sign-in, optionally through your own OIDC provider.
- A transaction PIN in front of the six operations that move money — and only
  those. Wrong attempts lock out with a waiting period.
- Deleting the wallet takes three things: PIN, wallet password, and typing the
  node alias.
- The seed is never stored — not in a file, not in the log, not in the state.

### Verified

Before this release the Lightning side was run against **real software in
regtest**: a real `bitcoind` and three real LND nodes, not mocks. All 38
Lightning endpoints were exercised, with the results checked against expected
values rather than just status codes.

The test that matters: the data directory was deleted outright, then restored
from the twenty-four words plus the channel backup. Same node pubkey, on-chain
balance exact, 563,459 of 566,527 sat recovered from the channel — a total loss
of 3,068 sat in closing fees.

The automated suite runs on every push: unit, integration and interface tests
with a coverage floor of 80 %.
