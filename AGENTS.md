# Working on this repository with an AI agent

This file is for coding agents. It states the conventions that are **easy to
mistake for accidents** and would be "fixed" by anyone who does not know
better.

If you change something here, read this first. It is short on purpose.

## What this is

A Bitcoin and Lightning node appliance: four containers (`app`, `bitcoind`,
`lnd`, `tor`), a setup wizard, and a web interface that explains what it does.
It holds a Lightning wallet with real money in it. That shapes every rule
below.

## Conventions that look like mistakes and are not

**The application source is German. The documentation is English.**
Identifiers (`kanaele`, `gebuehren`, `knoten`), comments and docstrings are
German; README, GUIDE, SECURITY, CHANGELOG and the user interface are English.
This is deliberate and not a migration in progress. **Do not translate the
source.** A rename touching hundreds of identifiers carries real regression
risk and buys nothing for the people who run this.

**Commit messages, tags and release notes are English. Always.** They are
public-facing like the documentation: they show up in the file list on GitHub,
in release pages and in every clone. The German of the source does not extend
to them. Until 2026-09-23 no rule said so, and the messages followed the
language of the source — that was a mistake, not a convention.

**Comments explain *why*, at length, with dates.** Many carry a finding and
the date it was made — `DER BEFUND VOM 17.09.2026: …`. They are not clutter;
they are why the code looks the way it does. **Do not condense them.** If you
change the behaviour they describe, update the comment; if you cannot explain
why a line exists, do not delete it.

**No Docker socket.** The application steers services through files in a
shared volume (`/config/<name>.conf` plus `<name>.ready`), watched by
`images/common/entrypoint.sh`. Handing the app a Docker socket would be
simpler and would be equivalent to root on a machine holding a wallet. Do not
"simplify" this.

**Every number comes from this node.** No mempool.space, no CoinGecko, no
block explorer for chain data. Price and news go over Tor and nowhere else.
If you need a figure, get it from `bitcoind`, from `lnd`, or from our own
store. Adding an external API is not an optimisation here, it is a change of
character.

**Large answers are streamed, not loaded.** `getrawmempool` and LND's channel
graph are read in chunks (`rpc.Knoten.brocken`, `mempoolstrom.paare`,
`gebuehren.elemente`). The `app` container has a 400 MB limit; a full mempool
loaded at once exceeded it and the OOM killer took the container. Keep new
large reads streaming.

**Sentinel values.** A default that is also a valid value has bitten this
project three times — `0.0` against `time.monotonic()` (which counts from
boot), `zeitlimit or self.zeitlimit`, `minchansize = 0`. Use `None` for "not
set" and check with `is None`.

## Before you change anything

Run the checks. They are the same ones CI runs:

```sh
cd app/backend
pip install -r requirements-dev.txt
pytest --cov=satcortex --cov-report=term-missing --cov-fail-under=80
bandit -r satcortex -ll
pip-audit -r requirements.txt --strict
cd ../.. && python3 tools/i18n_pruefen.py
```

Shell and Dockerfiles:

```sh
shellcheck --shell=sh --severity=style images/common/entrypoint.sh
hadolint --config .hadolint.yaml images/bitcoind/Dockerfile
```

## Tests

**Write the test first and watch it fail.** A test that has never been red
proves nothing. This is not a style preference here — several tests in this
repository were green for the wrong reason until someone checked, and the
mistakes they were supposed to catch had shipped.

The interface tests (`tests/test_oberflaeche.py`) read `app.js` and
`index.html` as text. A common trap: your assertion finds the string in the
*comment* you just wrote above the code, not in the code. Strip comment lines
before searching.

**Both languages, always.** Every user-facing string exists in German and
English. `tools/i18n_pruefen.py` enforces it and fails on orphaned keys.

## The interface

**Never claim something about the network that is not true.** Three findings
in one day came from sentences that sounded right and went past the protocol
— "without channels your node is visible" (it is absent, BOLT 7), "then a
channel would not come about anyway" (it would, with an address). If the
interface asserts a fact, that fact must be checkable.

**A field must not contradict its own label.** A placeholder saying
`02abc…@host:9735` next to a description saying the address is optional sends
people away. People read what is *in* the field.

**Do not hide a panel silently.** If something is missing, say why. A box that
vanishes leaves the person searching for it.

## Money paths

Six operations move money: sending on-chain, opening a channel, closing a
channel, paying an invoice, rebalancing, deleting the wallet. Each sits behind
the transaction PIN, and **the PIN is checked before anything else** — before
amount validation, before address parsing. Do not reorder this.

The seed is never stored. Not in a file, not in the log, not in the state.

## Screenshots and demo data

Screenshots in `assets/` use demo figures. Never replace them with captures
from a running node — balances, pubkeys and channel data are not example
material.

## Things that will waste your time

- `GUIDE.md` and `ANLEITUNG` — there is no German guide any more, only
  `GUIDE.md`.
- `images/electrs/` — electrs was removed. There is no Electrum server here;
  Bitcoin Core with `txindex` covers what wallets need.
- Version numbers below 1.0.0 — they belong to a private phase that is not in
  this repository's history.
