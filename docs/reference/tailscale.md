# Tailscale — the notifier host's network

How consumers reach this service now that it has its own VM (#43). Companion
to [DEPLOYMENT.md](../DEPLOYMENT.md).

exe.dev VMs are **isolated from each other** — "there is not a private network
which connects them." Until #43 watcher reached notifier over `localhost`
because they shared a host; they no longer do. A tailnet replaces that hop.

The cluster-wide primer lives in `CannObserv/observo`
`docs/reference/tailscale.md` (what a tailnet is, WireGuard, MagicDNS, the
coordination server not being in the data path). This file covers only what is
specific to notifier.

## This deployment

- **Tailnet:** `cannobserv.org.github`, tied to the CannObserv GitHub org — so
  nodes are org-owned rather than owned by one person's login.
- **This node:** `notifier`, tag `tag:notifier`, address `100.98.9.17`.
  **Non-ephemeral and tagged**, so it never expires. That matters more here
  than for a fleet worker: an expiring node key would take every dispatch with
  it, silently.
- **Consumer node:** `watcher`, tag `tag:watcher`, `100.120.218.69` — the
  `watcher` VM, which also hosts archiver and replicator.
- **Also on the tailnet:** `observo-primary`, a *user-owned* node (not tagged),
  reached by a `hosts` entry in the ACL rather than by tag. Relevant when the
  Observo → Notifier path is provisioned: that rule needs `observo-primary` as
  a source, not `tag:observo-*`.

### ACL

```jsonc
{
  "tagOwners": {
    "tag:notifier": ["autogroup:admin"],
    "tag:watcher":  ["autogroup:admin"]
  },
  "acls": [
    // Consumer host -> notifier's two API ports, and nothing else. Nothing
    // lists tag:notifier as a *source*: notifier initiates nothing across the
    // tailnet. Its Apprise egress goes straight to the internet.
    { "action": "accept", "src": ["tag:watcher"], "dst": ["tag:notifier:9000,9001"] },
    { "action": "accept", "src": ["autogroup:member"], "dst": ["*:*"] }
  ]
}
```

> **ACL granularity is per-VM, not per-service.** One node is one VM, so
> `tag:watcher` today grants tailnet access to watcher *and* archiver *and*
> replicator. Acceptable because notifier's `X-API-Key` still partitions
> tenants — but per-service rules only become possible once those three split
> onto their own hosts.

Note the ACL does **not** open port 22. Administering this host goes over the
public `ssh notifier.exe.xyz`, not the tailnet.

## The bind, and the boot race it buys

Both units bind **this host's tailnet address alone** — never `0.0.0.0`. The
API is therefore unreachable from exe.dev's internal `10.42.0.0/16`, from the
exe.dev HTTPS proxy, and from the internet. `https://notifier.exe.xyz:9000/`
reaches the exe.dev login gate and stops there, because nothing listens on the
interface the proxy forwards to. That is the design, not a fault.

The cost is a startup race. `After=tailscaled.service` orders the two but does
**not** wait for an address to be *assigned*, and unlike Redis 7 — whose `-`
bind prefix makes an address optional — uvicorn cannot bind an address that is
not there yet. It exits non-zero, `Restart=on-failure` fires, and a tight
`StartLimitBurst` converts a transient into a unit that stays failed until
someone runs `systemctl reset-failed`.

That is not hypothetical. **observo#473** is this exact race against
redis-server and left that project's broker down for two weeks of silently
starved jobs.

[`scripts/tailnet_bind.sh`](../../scripts/tailnet_bind.sh) is the wait. Two
rules it exists to hold, both learned there:

1. **Probe `/proc/net/fib_trie`, never a netlink client.** observo#479 found
   their wait used `ip addr`, which the stock unit's sandbox SIGSYS-kills while
   blocking `AF_NETLINK` — *silently*, so the probe still exited 0. The wait
   detected nothing and every start paid a blind 30-second sleep, boot
   included, while appearing to work. Reading a proc file needs no socket.
2. **Time out non-zero.** Redis could fall back to a local-only bind because a
   local-only broker still serves local pipelines. Notifier has no half
   service — an unreachable API is the whole outage — so exhausting the wait
   fails the start rather than quietly binding something reachable from
   somewhere it should not be.

It also matches only addresses the kernel marks `LOCAL`, so a *peer's* tailnet
route can never be read as this host's own address.

`ExecStart` on `notifier.service` is [`scripts/serve.sh`](../../scripts/serve.sh),
not a uvicorn line. Besides the one-spelling rule `notifier-dev.service` has
held since #24, **systemd reads every `EnvironmentFile=` before `ExecStartPre`
runs** — so no `ExecStartPre` can resolve the address into the environment
`ExecStart` would see. Resolving and binding have to share a process.

`tests/deploy/test_tailnet_bind.py` and `test_systemd_unit.py` guard all of it.

## Reaching the service

| From | Live | Dev |
|---|---|---|
| Another tailnet node | `http://notifier:9000` | `http://notifier:9001` |
| **This VM itself** | `http://$(tailscale ip -4):9000` | same, `:9001` |

On this VM, **both `127.0.0.1:9000` and `http://notifier:9000` fail.** Ubuntu's
`/etc/hosts` maps the hostname `notifier` to `127.0.1.1`, which nothing binds,
so the short name resolves locally instead of through MagicDNS. Use the tailnet
address:

```bash
curl "http://$(tailscale ip -4):9000/health"
```

## Joining or re-joining this host

```bash
# Key staged in a 0600 file, never in argv — PAM audits argv into journald
# (observo#264). Generate it Pre-approved + Tagged + NOT Ephemeral.
sudo install -m 600 /dev/null /run/ts.key
sudo tee /run/ts.key >/dev/null <<< 'tskey-auth-...'
sudo systemctl enable --now tailscaled
sudo tailscale up --auth-key=file:/run/ts.key --hostname=notifier
sudo shred -u /run/ts.key
```

**Tags bind at device registration.** Re-authenticating an existing node with a
differently-tagged key does *not* retag it — `tailscale up --reset` leaves the
old tags in place. Changing them takes `tailscale logout` followed by a fresh
`tailscale up`, which re-registers. Cheap on a new host; disruptive on one
peers already depend on, so **get the tag right before the first join.**

A key scoped to more than one tag applies *all* of them and cannot be narrowed
with `--advertise-tags` — that fails with `requested tags are invalid or not
permitted`. Generate one single-tag key per node.

## DNS

`tailscale up` takes over `/etc/resolv.conf`, pointing it at MagicDNS
(`100.100.100.100`); the previous file is preserved at
`/etc/resolv.pre-tailscale-backup.conf`. Kept deliberately (#43 D8) so short
names resolve with nothing to maintain.

**Accepted cost:** `tailscaled` is now in the DNS path for everything on the
host, including Apprise egress to Slack and Mailgun. If DNS turns flaky,
observo hardened theirs to dual nameservers with `options timeout:2 attempts:2`
after transient exe.dev failures (observo#2, `infra/resolv.conf`) — that
hardening is **not** in effect here, because Tailscale's resolver replaced it.
The alternative, rejected at the time, was `--accept-dns=false` plus an
`/etc/hosts` pin.

## Token vocabulary

| Token | Direction | Where |
|---|---|---|
| Tailscale **auth key** (`tskey-auth-…`, pre-approved + tagged + non-ephemeral) | this VM → joins the tailnet | admin console → staged 0600, shredded after join |
| exe.dev **API token** (`exe1.…`) | agent → `POST https://exe.dev/exec` | operator's `.env`; default `cmds` scope is `new`/`ls`/`whoami` — **no `rm`** |
| `X-API-Key` (`nk_…`) | consumer → notifier | consumer-side; for watcher, `/etc/watcher/notifier.env` on the watcher VM |

Independent secrets for independent hops. A tailnet key never authenticates an
API call, and the API key is not what gets a host onto the tailnet.
