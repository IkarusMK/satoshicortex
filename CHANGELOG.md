# Changelog

All notable changes to SatoshiCortex. Format loosely after
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning after
[SemVer](https://semver.org/).

## [Unreleased]

### Added: signed build provenance for every image

Until now, whoever pulled `ghcr.io/ikarusmk/satcortex` had to trust that it was
built from this repository — there was no way to check. That sat oddly with a
project that verifies the signatures of Bitcoin Core and LND before using them.

Every image built from a release now carries a signed SLSA build provenance
("built by this workflow, from this commit"), created with `actions/attest`
v4.2.2 and signed through Sigstore — no long-lived key to manage or leak. It is
stored next to the image in the registry:

```sh
gh attestation verify oci://ghcr.io/ikarusmk/satcortex:<version> --owner IkarusMK
```

What is attested is the image **digest**, not a tag — a tag can move, a digest
cannot. Only the job that pushes images may mint the signing token. Storage
records are left off: GitHub offers them only for organization-owned
repositories, and asking for one would mean granting a permission that
achieves nothing here.

Three new tests guard it: the provenance step exists, follows the build and
attests its digest; no other job may mint a signing token; and every
third-party action in both workflows is pinned to a full commit hash. The
pinning came in with the audit of 2026-09-22, but nothing checked it until
now. Each test was shown to fail against a deliberately broken workflow first.

### Fixed: fetching the mempool tiles took five clicks

Reported from operation: "Fetch tiles" under *Mempool* needed five clicks on
average before anything appeared, and each failure said "Could not be saved".

With 83,000 waiting transactions and an app container capped at one CPU, the
fetch took longer than the 25 seconds the browser waited — the server allows
Bitcoin Core 45 seconds of silence in the stream. The browser gave up, the
server kept working, and every new click started a **second** full fetch next
to the first, so they slowed each other down. Only when one finished and
cached its result for 20 seconds did a click land in that window and "work".

- The server now runs **one** fetch at a time; a second request waits for the
  running one and gets its result.
- The browser waits two minutes for this one call, not 25 seconds. A test
  keeps that at least twice the server's limit, like the one for payments.
- If it still takes too long, the message says so — instead of claiming that
  something could not be saved.

### Fixed: the generic error message claimed that saving had failed

"Could not be saved" was the fallback text for every error without a message
of its own — used in 36 places, almost all of them fetching, measuring or
withdrawing, where nothing is saved. It was patched in one place on
2026-09-13, but the text itself stayed. It now reads "That did not work."

### Changed: commit messages are English

Commit messages, tags and release notes are English from now on, like the rest
of the public-facing project. `AGENTS.md` fixed the language of the source and
of the documentation, but said nothing about commits, and they followed the
German of the source. The GitHub releases for 1.0.0 to 1.2.1 were created on
2026-09-23 from this changelog.

## [1.2.1] — 2026-09-23

### Fixed: the update box offered an old version — and a line that pins you to it

Reported from operation: the box under *Settings* offered **1.0.3** while
**1.2.0** had been out for hours. Three faults added up.

**It recommended the newest version of your own branch, not the newest.** For
Bitcoin Core and LND that is right: older branches are maintained there, and a
maintenance release in your branch is the safer step. SatoshiCortex has no such
branches — 1.0.3 and 1.0.4 are simply older steps on the way to 1.2.0, nothing
is carried back to them. A node on 1.0.2 was told "1.0.4, a maintenance
release, safe to apply", with 1.2.0 pushed into an "also available" below.
Core and LND keep their branch logic; only SatoshiCortex now always names the
newest.

**It handed out a line that pins you.** Under the number stood
`SATCORTEX_VERSION=1.0.x` to copy into the `.env`. Whoever follows `latest` —
the default — and copies it is pinned from then on and never gets another
update. The box now knows which tag the installation follows (the compose file
passes it on as `SATCORTEX_ABBILD_TAG`): with `latest` it says "pull again" and
shows no number to copy; with a fixed number it shows the line; if it cannot
know, it names both ways. The explanation below it was also the one for Core
and LND, including "docker compose build lnd" — SatoshiCortex now has its own.

**Its answer was up to a day old and did not say so.** "Once a day is enough"
was written for two projects that release a few times a year. SatoshiCortex had
four releases in nineteen hours. It is now checked every six hours, and the box
shows when it last looked.

### Fixed: an older tag pushed again would have moved `latest` backwards

The image workflow claimed to set `latest` "only when it really is the newest".
Only the manual start was guarded. A tag push set `latest` every time — also for
an older tag that was merely moved or rebuilt. Every installation following
`latest` would have been downgraded on its next pull, silently; that concerned
every image in such a run, Tor included. On a tag push, `latest` now goes only
to the highest release tag, and if the list of tags cannot be read the build
fails loudly instead of quietly leaving `latest` where it was.

The tests for it do not read the workflow text — they **execute** the real step
from the YAML file, in the same shell GitHub uses, against a stand-in `gh`.
Against the old workflow they fail; against the new one they pass.

## [1.2.0] — 2026-09-23

The last of the three gaps from that measurement. LND has a second invoice
interface, `invoicesrpc`, with six REST routes — and we used **none** of them.
Invoices were issued through `/v1/invoices` and the answer to "has it been
paid?" came from reloading the list of the last twenty.

That answers the wrong question. Someone holding out a QR code does not want
to know whether one of their last twenty invoices is paid. They want to know
whether **this one** just was, at the moment it happens.

### Added: the invoice tells you itself when it is paid

After you create an invoice, the panel now waits on it. The server attaches to
LND's `SubscribeSingleInvoice`; LND reports by itself the moment anything
changes, and the line under the QR code turns into "Paid. 1,500 sat arrived."
No polling, no switching views and back.

The request deliberately stands still for up to 45 seconds and then returns
with the state as it is — an expired deadline here is the normal case, not a
fault, and the interface does not flash an error every round. A torn
connection does not end the wait either: it pauses five seconds and reattaches,
because a single twitch in the network must not make a live panel look dead.

### Added: look up a single invoice

`LookupInvoiceV2`, for the invoice that has already dropped out of the list of
the last twenty.

### Added: withdraw an invoice

`CancelInvoice`, on the freshly created one and on every open one in the list.
A mistyped amount, a wrong purpose, or a deal that fell through — an invoice
otherwise stays payable until it expires, including by someone who still has
the QR code on screen.

No PIN, for the same reason as issuing one: it moves no money, it withdraws a
claim. But **only while the invoice is open**. One that is already holding the
payer's money is left alone — cancelling that would hand the money back, which
is how a hold invoice is meant to work and not a decision anyone should make in
passing.

### Not built, on purpose

Three of the six routes stay out, and the reasons are in the source next to the
ones that are in:

- **`AddHoldInvoice` / `SettleInvoice`** — a hold invoice accepts the payer's
  money and holds it without taking it. Whoever fails to settle holds someone
  else's money in an HTLC until its timelock runs out, and then the peer force
  closes the channel. A button for that in an interface with no shop behind it
  is a trap, not a tool.
- **`HtlcModifier`** — an interceptor for incoming HTLCs, as a bidirectional
  stream. It only works while something is listening at the other end: if it
  attaches and dies, incoming payments stall. A service that occasionally
  restarts would break receiving rather than improve it.

### Verified, not assumed

The payment hash travels as **base64** on these routes, not as hex the way it
does everywhere else in this codebase — they take it as a `bytes` field, and
LND's REST gateway decodes those with base64. Read out of the source for the
pinned versions rather than remembered: lnd v0.21.3-beta pins
grpc-gateway/v2 v2.16.0, whose `runtime/convert.go` tries standard base64 and
then the URL-safe alphabet, both **with** padding. The URL-safe form is
mandatory in the path — a `/` from the standard alphabet would cut
`/v2/invoices/subscribe/{r_hash}` in two, and writing it as `%2F` saves
nothing, because Go decodes the path before splitting it.

That is a class of defect the route guard cannot see: right path, right method,
unusable content — the same shape as the failure of 2026-09-15. There are
tests against the content now, each one proven red against a deliberately
broken version first.

## [1.1.0] — 2026-09-22

Two gaps found by measuring our own interface against what Bitcoin Core and
LND actually offer in their containers. Of LND's 141 REST routes we used 36;
`walletrpc` had 29 of 30 untouched and `routerrpc` 17 of 19.

### Added: raise the fee on a transfer that is stuck

The natural next question after "your transfer may be on its way" is "it is
stuck, now what". LND has had the answer all along in `BumpFee`; we never
offered it.

What it really does, and the interface says so before you press: your node
attaches a **second** transaction to your own change, so a miner can only take
both together (child pays for parent). The first one does not go away, and the
second one costs extra.

Three decisions worth stating:

- **The fee cap is mandatory**, with no default — the same call as the fee
  limit on a Lightning payment, for the same reason. Without one, LND takes
  what it considers necessary, which its own documentation puts at up to half
  the output.
- **The button only appears when it can work.** Bumping needs an output that
  belongs to us. If everything went out there is no change to attach to, so
  the panel states the reason instead of offering a button that is certain to
  fail.
- The field names come from LND's own interface description at the pinned tag,
  not from memory.

Behind the transaction PIN, checked first, like every other path that spends.

### Added: what your node has learned about routes

LND remembers, per pair of peers, up to which amount a forward carried and
from which amount it failed — and picks routes by that afterwards. The
original plan for this project called this "the real bottleneck" for routing,
and we had never once asked for it.

The useful part is not the list but the two amounts side by side: if "failed
from" sits just above "carried up to", the route is not broken but **empty**.
That is a liquidity question and it can be fixed.

The summary is computed on the node, not in the browser — an active node
remembers thousands of pairs. Read-only, so no PIN: a PIN you type for a piece
of information is one you will eventually type without thinking.

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
