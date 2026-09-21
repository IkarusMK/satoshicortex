# Changelog

All notable changes to SatoshiCortex. Format loosely after
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning after
[SemVer](https://semver.org/).

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
