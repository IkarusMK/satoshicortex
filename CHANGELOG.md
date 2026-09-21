# Changelog

All notable changes to SatoshiCortex. Format loosely after
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning after
[SemVer](https://semver.org/).

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
