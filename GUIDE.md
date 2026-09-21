# SatoshiCortex — Internals

Two parts. First **the path from nothing to a running node** — in the order you
actually walk it. Then the internals: what happens under the hood along the
way, for anyone who wants to know exactly or wants to change something.

One thing to get straight up front: the setup wizard in the web interface only
takes over from phase 4 onwards. Everything before that — folders, `.env`,
`docker compose up` — it cannot guide you through, because at that point it is
not running yet. That is precisely why it is written down here.

## From nothing to a running node

### Phase 1 — Prepare the NAS

**1. Create the five folders by hand.** Below your two mount points:

    <DATA_BULK>/blocks
    <DATA_BULK>/coreindex
    <DATA_FAST>/bitcoind
    <DATA_FAST>/tor
    <DATA_FAST>/config

NAS interfaces check whether every bind-mount path exists when the project is
created, and refuse to start otherwise — the wizard never gets the chance to
create them itself. **Not at the volume root**, and all of them must be owned
by **UID 1000**. Details under *Create bind mounts beforehand*.

**2. Check that the ports are free.**

    sudo ss -tlnp | grep -E ':(3333|8333|9735)\b'

**4080 is mempool.space's default port** — which is why the default here is
3333. Details under *Spotting occupied ports*.

**3. Only ONE compose file in the project folder.** Otherwise the wrong one is
deployed silently. Details in the next section.

### Phase 2 — Fill in the .env

**4.** `cp example.env .env` — a dozen values, that is all you set by hand.

**5. Service identity.** `PUID=1000`, `PGID=1000` — **on UGREEN and Synology
`PGID=10` belongs here**, because both keep users in the group `users` with
GID 10.

**6. The two storage locations.** `DATA_BULK` large and slow, `DATA_FAST` small
and fast. The defaults sit in the same folder and therefore on the same disk —
fine for a first try, but on a NAS with an HDD and an SSD you are throwing the
split away.

**7. Ports and resource limits.** `WEBUI_PORT=3333`, `BITCOIN_P2P_PORT=8333`,
`LIGHTNING_P2P_PORT=9735`. **No CPU value may exceed your core count** —
otherwise the container will not even start. Details under *CPU limits and core
count*.

**8. Leave the versions alone.** Pinned does not mean frozen: you decide when
an update is applied. Details under *Applying a new version*.

**The container network likewise.** `NETWORK_PREFIX=10.83.33` — the services
get fixed addresses inside it, and Tor forwards connections arriving at your
.onion addresses to exactly those. Change it only if `docker compose up`
reports *"Pool overlaps with other one on this address space"*: then another
network on your machine already occupies that range. Details under *The
container network*.

### Phase 3 — Start

**9.** `docker compose up -d`. All four containers start immediately — and
**wait** for their configuration. How that works is described under *How the
services are started*.

**10.** Open `http://<your-server>:3333` in a browser.

### Phase 4 — The wizard

**11. Click through it.** Seven steps, details under *The wizard, step by
step*.

**12. Step 5 needs two things**, not one: the release in the wizard **and**
`RPC_BIND=0.0.0.0` in the `.env`.

### Phase 5 — At the router

**13. Two port forwards**, IPv4 and IPv6: **8333** (Bitcoin) and **9735**
(Lightning). Without them the node only takes, and it is a dead end in the
Lightning graph. The wizard measures live whether anyone reaches you from
outside.

Optionally a third: **9911** for the watchtower. With Tor it is not needed —
Tor offers the tower under its own .onion address. Forward it only if you want
to offer the tower on the clearnet as well; either way it is only announced in
"Tor and clearnet" mode.

**Over Tor no forward is needed at all.** Anyone choosing "Tor only" is
reachable for Bitcoin, Lightning and the watchtower without a single open port
— through the three .onion addresses Tor creates.

### Phase 6 — Waiting, and afterwards

**14. The initial sync runs in the background** — days to weeks. As long as the
block height is rising, it is working; under *Log → SatoshiCortex* a line with
height, percentage and speed appears every ten minutes.

**15. Set up Lightning once the chain is there.** The overview says so by
itself. `lnd` has been running the whole time, waiting — nothing to install
afterwards. Then comes the guided procedure with the **seed on paper**. What
happens next is described under *Running Lightning*.

---

From here on, the internals.

## Only ONE compose file in the project folder

Some NAS interfaces — UGOS for one — write their **own** `docker-compose.yaml`
into the project folder when deploying. If the shipped `docker-compose.yml`
sits next to it, that one wins: Docker searches in a fixed order, and `.yml`
comes before `.yaml`. The wrong file is then deployed — no error message, no
containers, no log.

So after uploading, either delete the shipped `docker-compose.yml` (the
interface writes its own anyway), or do not paste the contents through the
interface in the first place.

## Spotting occupied ports

If a container does not start, an occupied port is the most common reason. Some
NAS interfaces still show the port mapping even though the bind failed —
the failure then looks like a broken program.

What is really listening:

    sudo ss -tlnp | grep -E ':(3333|8333|9735)\b'

And who owns a port:

    sudo docker ps -a --filter publish=3333

Known collision: **4080** is the default port of the mempool.space interface.
That is why the default for the web interface here is 3333 and not 4080.

## CPU limits and core count

None of the CPU values in the .env may exceed the machine's core count.
Otherwise the affected container will not start, and Docker only reports
"range of CPUs is from 0.01 to X, as there are only X CPUs available" — without
saying which setting it means. The defaults run on dual-core machines; on
larger ones you may raise them.

## Create bind mounts beforehand (NAS interfaces)

Compose interfaces on NAS systems — UGOS, Synology's Container Manager and
relatives — check whether every bind-mount path already exists when a project
is created, and refuse to start otherwise. On the command line this goes
unnoticed: there Docker creates missing folders itself.

The setup wizard would create the substructure by itself. On these interfaces
it never gets that far, because the check happens earlier. So create them
beforehand, below the two mount points from the .env:

    <DATA_BULK>/blocks
    <DATA_BULK>/coreindex
    <DATA_FAST>/bitcoind
    <DATA_FAST>/tor
    <DATA_FAST>/config

Also important is where these folders live: NOT directly at the volume root.
UGOS and Synology turn a folder there into a **shared folder**, which then
becomes visible on the network. So create them below an existing shared folder,
for example /volume1/docker/... instead of /volume1/...

All of them must be owned by **UID 1000** — the services run under that
identity. If you create them through the NAS file interface with your own user
account, that is usually correct by itself; if Docker creates them as root,
bitcoind cannot get in.

## How the services are started

On `docker compose up` all containers start immediately — but they **wait**.
Their configuration does not exist yet; it is created by the wizard.

Every service runs through `images/common/entrypoint.sh`:

1. Wait until `/config/<name>.conf` **and** `/config/<name>.ready` exist.
2. Remember the configuration's checksum, start the service.
3. A watcher observes the file. If it changes, it shuts the service down in an
   orderly fashion. Because of `restart: unless-stopped`, Docker starts it
   again — with the new values.
4. If the `.ready` file disappears, the service is switched off.

**Why this detour?** The obvious route would be to hand the application the
Docker socket. On a machine holding a Lightning wallet, a Docker socket is
equivalent to root. Steering through files costs a few more lines and avoids
exactly that risk.

The application reads the services' state directly from them — bitcoind over
RPC, LND over REST, Tor through its log and its SOCKS port; Tor has had no
control port at all. That is more meaningful than raw container logs
anyway.

## The wizard, step by step

Seven steps, and none of them assumes you know Bitcoin. Each one says what it
does — nothing is decided in the background.

| | Step | What you decide |
|---|---|---|
| 1 | **Welcome** | Nothing. What the node needs (space, two port forwards, time, bandwidth) and what it gives the network. |
| 2 | **Storage** | Nothing. The application looks at your two mount points, shows the free space and warns if it gets tight. |
| 3 | **Performance** | How much the node may take — frugal, balanced, full power. Plus the upload budget. On a NAS there is usually something else running. |
| 4 | **Network** | **The most important question: how visible your node is.** Tor only (anonymous, slower), Tor and clearnet (fast, your IP is public), or announce nothing at all. Below that the details: IPv4, IPv6, pausing Tor during the sync, your own address. |
| 5 | **Wallet software** | Whether your own wallet — including one with a hardware device — may use this node, and from which network. Default: off. |
| 6 | **Account** | Username and password for the interface, or sign-in through your OIDC provider. |
| 7 | **Done** | Nothing more. A summary, then the initial sync starts. |

All of these settings can be changed later under **Settings** — the wizard is
not a one-way street. Only one thing cannot: the Lightning wallet. It is
created once the chain is there, in its own guided procedure with the seed on
paper and a read-back check. An automatically created wallet whose seed nobody
wrote down would not be convenience, it would be a trap.

### Step 5 needs two things, not one

For wallet software on your home network to actually reach the node, **both**
must be right:

1. the release in the wizard (or later under Settings), and
2. `RPC_BIND=0.0.0.0` in your `.env`.

The port alone is useless as long as `rpcallowip` does not let it through — and
the other way round. Both together is deliberate: an open RPC interface is not
something that should come about with a single click.

What does NOT happen: no wallet is created inside the node and no key is handed
to it. Sparrow states this itself — *"Sparrow does not use Bitcoin Core's
internal wallet"*. The release allows querying the chain and submitting
transactions. Nobody can move money with it, because there are no keys in the
node.

## What the wizard writes

| File in the `config` volume | Contents |
|---|---|
| `bitcoind.conf` | from `app/templates/bitcoin.conf.tmpl`, with generated `rpcauth`, performance and network values |
| `tor.conf` | from `torrc.tmpl`, with the onion services your visibility choice calls for |
| `lnd.conf` | alias, colour, announced addresses, fees |
| `<name>.ready` | the release — only with it does a service start |

The application generates the RPC password itself and puts only the hash into
the configuration. You never have to enter it anywhere for normal operation.

You get to see it in exactly one place: under **Settings → Wallet
software**, when you allow your own machine to use the node. Without that
release it is shown nowhere.

## The container network

The four containers live in their own network with **fixed addresses**:

| Service | Address (default) |
|---|---|
| app | `10.83.33.10` |
| bitcoind | `10.83.33.11` |
| lnd | `10.83.33.12` |
| tor | `10.83.33.13` |

**Why fixed.** Tor runs in its own container and forwards connections arriving
at your .onion addresses to bitcoind and LND. For that it needs a target that
is correct — always:

- Without a target Tor uses `127.0.0.1`, meaning its own container. Neither
  bitcoind nor LND listens there — the .onion addresses would be out on the
  network with nobody arriving at them.
- A name like `lnd` will not do: Tor resolves it only at startup. If LND gets a
  different address afterwards — after an update, after a restart of the
  machine in a different order — the service points into the void.

**Tor holds the onion services itself**, in its own configuration. The obvious
alternative — letting bitcoind and LND create them through Tor's control port —
loses LND's services on every restart of Tor. Here Tor creates them on every
start by itself, and **there is no control port at all**. The keys live under
`DATA_FAST/tor/onion-bitcoind`, `onion-lnd` and `onion-wachturm` — as long as
those stay, your addresses stay.

**If the network collides.** `docker compose up` then aborts with *"Pool
overlaps with other one on this address space"*. Set `NETWORK_PREFIX` in the
`.env` to a different free private /24 (for example `10.84.33`) and start
again. The application switches rpcallowip and Tor over by itself.

## Resource limits

The `.env` holds **hard upper bounds** for CPU and memory per service. Within
those bounds the application regulates itself: during the initial setup the
database cache may be large, afterwards it winds it back down.

Three presets sit as comments in `example.env`: **frugal**, **balanced**
(default) and **full power**. The reasoning: on a NAS there are usually other
services running, and they should not stall just because the chain is being
verified here.

## Storage split

Two mount points are enough, the application creates the substructure:

| | What | Size |
|---|---|---|
| `DATA_BULK` | blocks and core indexes | ~840 GB |
| `DATA_FAST` | chainstate, `blocks/index`, SQLite, LND, Tor | ~25 GB |

Bitcoin Core's data directory is split three ways for this. One detail makes it
possible: `blocks/index/` stays in the data directory even with `-blocksdir` —
a small random-access database that belongs exactly there.

## The images

All built ourselves, no third-party images, no `:latest` tags:

- **bitcoind** — official release from bitcoincore.org. The build imports the
  builder keys from a pinned `guix.sigs` commit and requires **at least three
  valid signatures**. Otherwise it aborts.
- **lnd** — GitHub release, `manifest-*.sig` against the pinned Lightning Labs
  key.
- **tor** — Debian package, verified by apt against the Debian archive key.

### Building yourself instead of pulling

Normally the compose pulls the finished images from the GitHub registry. Every
service also has a `build:` section, though — so you can build directly on the
machine without waiting for a build in the cloud:

```sh
docker compose build app
docker compose up -d app
```

For the web interface this is particularly worthwhile: the `app` image is two
Python-slim stages without Rust and without Node, it is done in a few minutes,
and most of that is downloads. `bitcoind`, `lnd` and `tor` build just as well
but take longer — they verify signatures along the way.

What you need is the project folder on the machine (`git pull`) and Docker with
buildx. Afterwards the sidebar footer shows the new version.

## What an update costs — and what it does not

The most common worry when running real channels: does the node have to go
offline for this all the time? No. It depends on WHAT is being updated.

| What is updated | What restarts | What that means for your channels |
|---|---|---|
| **SatoshiCortex** (`SATCORTEX_VERSION`) | only `app` | **Nothing.** LND and bitcoind keep running, channels stay online, forwards keep going. The web interface is away for a few seconds. |
| **Bitcoin Core** (`BITCOIN_VERSION`) | `bitcoind` | LND briefly loses its chain source and reconnects. Channels stay open. The stop gets a 10-minute grace period so Core closes its database cleanly. |
| **LND** (`LND_VERSION`) | `lnd` | The only case with a real outage: during the restart your node is offline for its peers and forwards nothing. One to two minutes is usual, longer with a database migration. |

This follows from the compose: `app` depends on no other service. A
`docker compose pull && docker compose up -d` swaps only what has a changed
image.

**Before an LND update**, once capital is in channels:

1. Verify the channel backup (interface: *Lightning → Setup*), so that a
   corrupted file is not the only one you have.
2. Change the version line in the `.env`, then `docker compose up -d lnd`.
3. After the start, check that the channels are **active** again and the
   watchtower counter keeps running.

**What a restart does NOT require:** any arrangement with your peers. A channel
survives outages — that is part of the design. Only longer absence costs
reputation: Lightning nodes prefer peers that are reachable.

## Applying a new version of Bitcoin Core, LND or Tor

The third-party versions live in your `.env`, **once** each:

```
BITCOIN_VERSION=31.1
LND_VERSION=v0.21.3-beta
TOR_VERSION=latest
```

The compose takes them from there — for the image name and for the build
argument. There are no two numbers that can drift apart.

**Applying an update is therefore:**

```
docker compose pull && docker compose up -d
```

Nothing more. No building, no repository, no detour.

### Where the image comes from, without you doing anything

The images are BUILT from the official release — the Dockerfile verifies the
signatures against pinned publisher keys along the way (for LND at least three
must check out). They therefore exist only in versions that have passed through
CI once.

So that you do not have to wait for that, the pipeline **checks daily by
itself**: if Bitcoin Core or LND has a new release that is not yet in the
registry, it is built and stored. Nobody has to touch the project for it — no
proposal, no merge, no new version.

Tor has no fixed number here (the image takes the current Debian package); it
is therefore rebuilt weekly so that `latest` carries the security updates.

The **highest** version is taken, not the most recently published one. Bitcoin
Core maintains several branches in parallel: on 2026-09-02 `v29.4` (10 July)
came before `v31.1` (8 July) in the list sorted by date. Taking the first entry
would "update" from 31.1 to 29.4.

### When it is applied is your decision

An image being ready does not mean it is running. What runs is what is in YOUR
`.env`. The web interface shows under **Settings → Updates** what is new (the
query goes over Tor, so it does not reveal that a node is standing here).

### When a pull comes up empty

`manifest unknown` means: this version has not been built yet — for instance
because the release is only a few hours old. Two options:

* Wait. The next check is the following morning, and you can also trigger it
  immediately in the Actions interface under **"Build images" → "Run
  workflow"**, for exactly one image and exactly one version.
* Put the number in the `.env` back. Then everything carries on as before.

*(Building yourself would work too — `docker compose build lnd` — but for that
the Dockerfiles have to sit next to the compose. If only `docker-compose.yml`
and `.env` are there, it fails with `lstat .../images: no such file or
directory`. For normal operation you do not need this.)*

**What to keep in mind.** With LND a database migration is **irreversible** —
LND explicitly refuses to go back to an older version. As long as no wallet
exists, that is moot. Once capital is in channels, a backup belongs beforehand.

An older Bitcoin Core version, by the way, does not fall out of the network:
the consensus rules are backwards compatible.

## Running Lightning

Up to here it was about the node. This section is about operating it: getting
money in, opening and closing channels, staying reachable. It assumes the chain
is there and the wallet has been created — before that LND permits none of it,
and that is LND's condition, not ours.

### Four tabs, four responsibilities

| Tab | For what |
|---|---|
| **Wallet** | The MONEY. On-chain balance, channel balance, transactions, depositing, sending, receiving, paying. |
| **Channels** | The CONNECTIONS. Open channels, opening and closing, fees per channel, watchtowers, forwards. |
| **Node** | The IDENTITY. Pubkey, alias, announced addresses, reachability, proof of ownership. |
| **Setup** | Everything you do ONCE. Create or restore a wallet, backup, unlock method, delete the wallet. |

The split is deliberate: setup used to live under *Wallet*, and what you went
looking for there — the contents — was not to be found.

### Two locks, and they protect different things

These get confused constantly, so once, properly separated:

| | Wallet password | Transaction PIN |
|---|---|---|
| **Whose is it** | LND's | SatoshiCortex's |
| **What it does** | Decrypts the wallet at startup | Releases individual operations |
| **When asked** | After every restart of LND | Before every operation that moves money |
| **Without it** | The node runs, but the wallet stays closed | Everything readable, nothing movable |

**The wallet password** you choose when creating the wallet. It encrypts LND's
key store on disk — without this password LND does start, but the wallet stays
locked: no channels, no payments, no balance.

It is **not** the same as the twenty-four words. The words restore the wallet
on a new machine; the password opens it on this one. Whoever loses the password
but has the words gets to their money. Whoever loses the words is not helped by
the password either.

**The PIN** is our own barrier and has nothing to do with LND. Five to twelve
digits, set up under *Settings*. It stands in front of exactly six operations —
and only those:

1. Sending on-chain
2. Opening a channel
3. Closing a channel
4. Paying an invoice
5. Rebalancing
6. Deleting the wallet

Anything that merely looks is **not** behind it: a fee estimate, viewing an
invoice, querying the graph, reading the balance. A lock in front of a query
that does nothing makes the lock annoying and nothing safer.

Without a configured PIN the server does not ask for one — then signing in to
the interface is the only hurdle. On a machine with channel capital that is
thin: whoever finds your browser open can send without further ado.

### How the wallet opens again after a restart

Three ways, and the choice is yours. It lives under *Lightning → Setup*:

| Way | What happens | What it costs |
|---|---|---|
| **off** | Nothing is remembered. After **every** restart you type the wallet password. | The node stands still until you are there — including at three in the morning |
| **remember** | Nothing goes to disk. The application keeps the password **as long as it runs**. If it restarts LND, it opens the wallet itself. | After a power cut you type again |
| **file** | The wallet password in plain text next to the wallet. The node carries on by itself after a power cut. | **Whoever has the disk has both** |

For a routing node that should stay reachable, **remember** is usually the
sensible middle ground: application updates and planned restarts pass through,
a real power cut asks for your hand once.

A fourth way — a vault with its own password — stood here until 2026-09-10 and
has been dropped. It only traded one secret for another without gaining
anything.

### Getting money in

Two ways, and they are different:

**Depositing on-chain.** Under *Wallet → Deposit* the node generates an address
together with a QR image. The money then sits in the node's on-chain wallet and
is the basis for channels. It needs confirmations: only what is confirmed can
be spent.

**Receiving over Lightning.** Under *Wallet → Receive* you issue an invoice:
amount, purpose, validity. Out comes a BOLT11 invoice with a QR image that you
pass on. Below it are the most recently issued invoices with their state —
open, paid, cancelled.

**What this requires and what is often overlooked:** an invoice can only be paid
if there is enough balance on the FAR SIDE of your channels. A freshly opened
channel has everything on your side — you can pay, but not receive. The
interface says so, instead of issuing an invoice nobody can pay.

You get inbound liquidity when someone opens a channel TO you, when you pay
through your channels (that moves balance to the other side), or through swap
groups such as LightningNetwork+.

### Channels

**Look first.** Under *Channels* you can inspect a peer before opening a
channel to it. The information comes from your OWN graph — every node announces
itself, and yours heard it. Nobody is asked and nobody is told whom you are
considering a channel with.

Three findings stand separately instead of being averaged into a grade: how
long the peer has been silent, how thinly it is connected, and whether it
announces an address at all. Whoever wants to accept one of them should know
which.

**Opening.** Amount, peer, speed. Beforehand the interface works out what the
on-chain fee costs and what stays free afterwards — including the reserve LND
holds back for a force close. A channel below roughly one million satoshis
forwards practically nothing; that is there as a warning, not as a bar.

Publicly announced channels are the default. A private channel appears in no
graph — then nobody can route through you.

**Closing.** Amicably it takes one confirmation, in dispute the agreed lock
period. Both are stated.

**Fees.** Settable per channel: base fee and rate in ppm. Steering during
operation is simple: make it expensive where a channel is draining, cheap where
it should be refilled.

### What the network charges — and the automatic mode

The obvious thing would be to put a number in the fee field — *"the network
median is around 143 ppm"* — looked up once and then written down. Such a
number ages silently: you cannot tell by looking at it when it was last
correct.

**Your node knows the answer itself.** It holds the network map in memory
anyway: every public edge with both directional policies, and each policy says
what its operator charges for forwarding. Once a day the application reads that
out and files the result. No foreign source, no explorer, no service — the same
line as everywhere else here.

The panel then shows:

- **Median** — the honest middle. Not the average: there are policies with
  fantasy prices in the millions that nobody ever routes through, and they drag
  any average into the absurd.
- **The middle of the network** (lower to upper quartile) — the range the large
  majority actually sits in.
- **What you charge yourself** — read from the graph, so the way the network
  sees you. Not from a note of ours.
- **The four-week band**, once enough measurement days exist.

**The band moves along.** It is the minimum and maximum of the daily medians
from the last four weeks, and every new measurement day pushes the oldest one
out.

**The automatic mode** sets the rate once a day to today's network median —
bounded by that band. Four things matter here:

1. **Today does not count towards its own band.** Otherwise today's measurement
   would always lie within its own bounds: an outlier would open its own limit
   and strike through unchecked. Guarding against exactly that is the point of
   the band.
2. **It touches nothing before a band exists.** Below seven measurement days
   nothing happens — a band made of two points is not a safeguard, it is a
   costume.
3. **It only touches the rate, never the base fee, and applies to all
   channels.** Steering individual channels by liquidity direction is something
   else and stays manual — that needs the HTLC stream, not the network median.
4. **It leaves trivia alone.** Every change is an announcement to the whole
   network; whoever broadcasts daily over two ppm falls foul of the peers' rate
   limiting and in the end reaches fewer of them than someone who keeps still.
   Below five ppm difference the rate stays put.

What the automatic mode *would* do is shown even when it is **off**. A switch
with a surprise behind it does not belong on a node holding money. And turning
it off leaves the rate where it is — nothing springs back.

**"Adopt median"** only writes the number into the field. It is applied with
*Set fees*. That is deliberate too.

**Without channels nothing happens**, and the interface says so: there is then
simply no channel policy to set anything on.

**Measurement only starts once the network map is there.** A freshly started
node knows a few hundred channels instead of thirty thousand; a median from
that would be a number without backing — and it would then sit in the band for
four weeks. Until then the panel says it is still waiting.

### One node address, three things you can do with it

Under *Channels* there is ONE field for the peer and three buttons below it:

- **Look at the peer** — queries only your own graph. Nobody learns that you
  looked. You get: how long it has been silent, how thinly it is connected,
  whether it announces an address at all.
- **Connect** — establishes a bare connection. No channel, no satoshi. Useful
  to see in advance whether a node is reachable. The connection is NOT
  permanent: if it drops, LND will not rebuild it without a channel.
- **Open channel** — connects by itself. You do not need the middle button for
  it.

**The pubkey alone is enough everywhere.** 66 characters, exactly as they
appear in any explorer. The address behind it (`@host:9735`) you may send
along, but you do not have to — if it is missing, your node fetches it from its
own graph.

You should send it along in exactly one case: when the peer is not in the graph
at all yet, because it has no public channel. Then nobody knows it, and the
address has to come by hand. That is the same case in which others cannot find
YOU — see below.

### Who may open a channel to you

You confirm nothing. **Anyone can open a channel to you** without asking — as
long as they meet your rule. And that is a single number: `minchansize` in the
`lnd.conf`. LND's own description (`sample-lnd.conf`, v0.21.3-beta):

> "The smallest channel size (in satoshis) that we should accept. Incoming
> channels smaller than this will be rejected."

Anything below that your node rejects silently and automatically. You see
nothing of it — no notice, no log entry in the interface.

**That is not cause for concern, it is the normal case.** Whoever opens a
channel to you commits THEIR money, not yours. You get inbound liquidity for
free, and that is exactly the scarce part. What it does cost you: every extra
channel raises the on-chain reserve LND keeps for a force close — negligible
with one channel, not with twenty.

**Settable** under *Node → Lightning*, next to name and colour.
Default 100,000 sat, range 20,000 to 16,777,215. All three values land in the
same file, so a change costs ONE restart of LND — and afterwards the wallet is
closed if you have not set up auto-unlock.

**The trap the setting exists for:** if you take part in a liquidity ring, set
`minchansize` BELOW the ring size. If it sits exactly on it, the channel you
earned fails over a single satoshi of difference — and it looks as though the
peer did not deliver. Found on 2026-09-18 on a real ring of 100,000 sat, with a
lower bound of exactly 100,000.

### Your name on the network — and why directories do not show it

A finding from 2026-09-18, and it is **not a bug in this software**.

Whoever enters an alias under *Node → Lightning* will still not find it at
Amboss or LightningNetwork+ afterwards — the public key is shown there instead.
The reason is in BOLT 7, the gossip rulebook, in the section on
`node_announcement`:

> if `node_id` is NOT previously known from a `channel_announcement` message
> [...] SHOULD ignore the message.

A node WITHOUT an announced channel is not a known node on the network. Its
name announcement is neither accepted nor relayed — regardless of what its
configuration says. Directories therefore cannot know the name at all and fall
back to the key.

**This is how you check that everything is right on your side:** under
*Lightning → Channels*, panel **"Your node on the network"**, line *Name*. What
stands there comes from LND's own `getinfo` — from the node itself, not from
our settings file. If the name is correct there, everything is set correctly;
all that is missing is the first public channel. With it the name appears
everywhere within minutes.

Measured exactly that way on 2026-09-18: LND reported the chosen alias, the
node had zero channels, and LightningNetwork+ showed the key. All three
observations together are precisely what BOLT 7 predicts.

### Staying reachable

Under *Node → Reachability* the application builds a real connection from the
outside — over Tor, to the addresses your node ANNOUNCES. That is the right
question: does somebody who only knows the announcement actually find a way
here? The measurement takes up to half a minute per address.

All routes are measured: your clearnet address, bitcoind's .onion
**and** Lightning's and the watchtower's. If an .onion reports *"refused"*, Tor
found your service but nobody accepted behind it — that has nothing to do with
the router.

On the clearnet: without a forwarded port 9735 you only open outbound channels
and are a dead end in the graph. Without an announced address likewise — even
with the port open. Over Tor no forward is needed.

### Watchtowers

Two directions, both switched on:

- **You watch other people's channels.** The most direct contribution there is:
  you prevent fraud against people you will never meet. Your tower address is
  under *Channels* — without it nobody can add your tower. **With Tor**, Tor
  offers it under its own .onion address, separate from the node's, and it is
  reachable without a port forward. **On the clearnet** it needs port 9911 in
  the router.
- **Your own channels are watched.** You add foreign towers there too, and
  remove them again.

**Adding your own tower to yourself protects nothing.** It runs on the same
machine, behind the same power supply, on the same disk — and a watchtower
exists for exactly one case: that THIS node is not running. If it is not
running, your own tower is not running either. The application therefore does
not count it as protection and marks it in the list.

**And foreign towers disappear silently.** Public tower lists age quickly; a
tower whose .onion no longer exists stays in the list as an entry. There is a
**Check** button per row for that: it builds a connection over Tor to
exactly that tower and says whether anyone accepts there. That finally makes
"no session" distinguishable — either the tower does not answer, or there is
simply nothing to back up yet. Add several and check whether one really holds a
session: added is not watched. The risk is small: a tower cannot move money and
does not see your channels. It learns your node pubkey and how often new
channel states arise, nothing else.

What a tower CANNOT say: how many channels it watches. It receives encrypted
packets and can only open them once the matching transaction appears in the
chain. It does not know itself what it is watching — and that is exactly what
makes it trustworthy.

### Proof of ownership

Places like LightningNetwork+ give you a text to sign with your node key. That
proves the node is yours. Under *Node → Proof* the application does it — and
verifies its own signature straight away: the key LND names in doing so must be
your own. It moves no money and reveals no key.

### What does not exist (yet)

**No remote access from a phone.** LND's REST and gRPC ports are NOT published
outside by the compose, and there is no hidden service for them. A phone wallet
such as Zeus therefore cannot attach to this node today. That is a deliberate
intermediate stage, not an oversight: whoever may move money may move
EVERYTHING with LND — macaroons know no amount limit. As long as that is open,
the interface stays inside the compose network.

## What needs backing up — and what does not

Three things, three different answers. Confusing them costs money.

**The twenty-four words (seed).** On paper, nowhere else. They restore the
on-chain wallet. SatoshiCortex does not store them — not in a file, not in the
log, not in the state. Whoever does not write them down at creation time has
lost them.

**The channel backup (`channel.backup`).** Off-site, and automatically. The
words do NOT restore the balances IN the channels: that needs the state of each
channel, and it is in this file. It is encrypted with a key derived from the
seed and may therefore go anywhere — someone else's cloud, a USB stick, email.
Without the words it is worth nothing to anybody.

Set up under *Lightning → Wallet*: either download it and file it yourself, or
enter a WebDAV folder into which SatoshiCortex pushes it by itself on every
channel change. For the WebDAV route an **app password** belongs in there, not
an account password: the application has to store it in order to file it
unattended, and an app password can be revoked individually.

**The blockchain.** Not at all. It can be downloaded again at any time — it
costs days, but nothing that could be lost.

### Verifying the backup while the node is still running

That your node can produce an intact backup says nothing about the copy on your
stick. Under *Lightning → Wallet → Check copy* you present the file you
actually hold; LND opens it and names the channels it contains. That proves two
things: it is intact, and it belongs to **this** node — the key comes from the
seed, and another node's backup fails here.

In addition the application compares the number of covered channels with the
open ones. A flawless backup from the day before yesterday does not cover
yesterday's channel — and that is exactly what otherwise only comes to light
afterwards.

The only day on which you can no longer find this out is the day you need it.
So beforehand.

## Restoring a backed-up node

Under *Lightning → Wallet*, next to creating one, stands the second route:
**Restore a backed-up node**. It only works while no wallet exists on this
machine yet.

You need:

1. **The twenty-four words.** From the slip of paper, in this order. Upper and
   lower case does not matter; you can also paste them all at once into the
   first field. A single wrong word is noticed — the seed carries a checksum.
2. **The channel backup**, if you have it: as a file, or straight from the
   configured WebDAV folder.

**What comes back.** Your on-chain balance in full; LND searches the chain 2500
addresses deep for it (LND's own default). Plus the settled balances from your
channels: LND forces the peers into a force close and brings the money onto the
chain. **The channels themselves are closed afterwards** — what is restored is
the money, not the operation. Amounts that were still in flight at the moment
of the loss do not come back; that is LND's own statement about this procedure.

**This needs a finished chain.** Before that the search finds nothing. The force
close additionally needs the usual lock periods — hours to days depending on the
peer.

**A warning that belongs with it.** The channel backup cannot be verified during
a restore: it is encrypted with a key from the seed, and only the finished
wallet knows that key. If it is the wrong file, LND will not start afterwards —
then you start again without it. Hence the section above: verify while the node
is still running.

## What is in the log

Four sources under **Log**, and none of them needs the Docker socket:

| Source | Contents |
|---|---|
| **SatoshiCortex** | What the application itself does. Transitions immediately (node gone, node back, chain finished), plus a progress line every ten minutes during the sync and one per hour in normal operation. |
| **bitcoind** | Core's own `debug.log`. **Careful: in UTC**, while the other sources show local time — the interface converts it. |
| **lnd** | Lightning, once it is set up. |
| **tor** | The onion service. |

Our own source is a ring buffer in memory, not a file: the last 2000 lines,
then the front falls off. At around 150 lines a day that carries over a
weekend. After a restart of the application it starts fresh — whatever should
persist is in the services' own files.

### Three lines in the Tor log that look like errors and are not

**`Your application (using socks5 to port 8333) is giving Tor only an IP
address.`**
That is this application's reachability check. To test your clearnet address
"from outside", it goes through Tor and hands over exactly the IP in question —
not a name. Tor warns here in general terms that an application might resolve
names itself and send DNS queries around the Tor network. Here no name is
involved at all, so there is nothing to leak. The line appears after every
check of your clearnet address.

**`Closed 1 streams for service [scrubbed].onion for reason resolve failed.`**
Single streams, every few minutes: bitcoind works through onion addresses from
its peer list, and some of the nodes behind them no longer exist. Normal
operation of any Tor-capable Bitcoin node.

**The same message, but FOUR at once, or
`Tried for 120 seconds to get a connection to [scrubbed]:9911`**
That is something else: LND's watchtower client failing to reach a configured
tower. It always appears in fours, because LND keeps its own client per channel
type. `resolve failed` here does not mean "busy" but: this .onion has no
descriptor in the directory at all — the service no longer exists. Look under
**Lightning → Watchtowers** to see which entry it is, and remove it.

Deliberately NOT logged is *"bitcoind is busy"*. Core holds a lock while writing
out the chainstate, and queries then wait; measured on 2026-08-28 this affected
roughly one in five calls during the sync. That is the normal state of a
working machine. If it were in the log, the real outages would drown in it.

## When something is stuck

**A service does not start**
It is probably still waiting for its configuration — that is normal as long as
the wizard has not been completed. `docker compose logs <service>` shows it.

**The web interface is unreachable**
Check `WEBUI_PORT` in the `.env` and whether the port is already occupied.

**The initial setup seems to hang**
Progress grows very slowly towards the end, which is deceptive. The overview
shows the block height — as long as that is rising, it is working. Safer still:
under **Log → SatoshiCortex** a line with height, percentage and speed appears
every ten minutes. If it says *"no progress for N minutes"*, it really is
stuck.

**`docker compose up` reports "Pool overlaps with other one on this address space"**
Another network on your machine already occupies `10.83.33.0/24`. In the `.env`
set `NETWORK_PREFIX` to a different free private /24 (for example `10.84.33`)
and start again. See *The container network*.

**An .onion reports "refused" under *Reachability***
Tor found the service, nobody accepts behind it. Usually the service is simply
not started (LND before unlocking accepts no connections yet). Otherwise look
under *Log → Tor* to see whether Tor was able to create the onion services.

**The disk is filling up**
The chain grows ~85 GB per year. The overview warns in good time; after that,
move `DATA_BULK` to a larger location.
