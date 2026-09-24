# The memory reservation — production on a shared 3.8 GiB host

What keeps the live service up when an agent session on the same kernel runs
the host out of memory (#74, #85, #88). Companion to
[DEPLOYMENT.md](../DEPLOYMENT.md), whose first-time setup installs all of it.

Measured on this host 2026-09-18 (#74): **3.8 GiB, no swap, 2 cores**, running the
live service, the dev endpoint, PostgreSQL *and* interactive agent sessions on
one kernel. Live peaks: `notifier.service` 90 MiB, `notifier-dev.service`
69 MiB, PostgreSQL 121 MiB. The agent sessions dwarf all three.

The failure this guards against is not an OOM kill — it is the **absence** of
one. Past the ceiling the kernel fails *atomic* allocations in whatever asks
next (`tailscaled`, `ksoftirqd`) and the production service is what goes down.
That is how `CannObserv/broker` lost its bus for 57m 48s on 2026-09-16 with
nothing killed at all (gregoryfoster/skills#295, `references/troubleshooting.md`
row U).

Four settings, none of which substitutes for another:

| Setting | Where | What it does |
|---|---|---|
| `MemoryLow=192M`, granted on every slice above | `notifier.service`; `postgresql@16-main.service.d/`; `system.slice.d/`, `system-postgresql.slice.d/` | Soft floor the kernel will not reclaim below. Protects the working set, which is what a stall eats — the API's and its database's |
| `OOMScoreAdjust=-500` | `notifier.service`, `notifier-sweep.service` | Puts production last in line for the killer. PostgreSQL's own unit already sets -900 |
| `vm.min_free_kbytes=65536` | `deploy/99-notifier-memory.conf` | The reserve *atomic* allocations draw on. The two above are per-cgroup and cannot help `ksoftirqd` |
| `-m 12,6` + `--prefer`/`--avoid` | `deploy/earlyoom.default` | Acts while the host is still responsive; the kernel's own killer is too late on a no-swap host |

Four things are deliberate and easy to get wrong:

- **`MemoryLow=`, never `MemoryMax=`, on the service.** A cap bounds the
  victim rather than the cause, and on a process the killer will not pick it
  *stalls* instead of killing. The cap belongs on the
  [SocratiCode pre-install](../SOCRATICODE.md#both-servers-are-pinned-not-installed-at-launch)
  — a deliberate one-off run — never on the always-on service.
- **Every slice above a floor grants it, exactly.** Without the grant the
  floor is inert, and nothing that reads the unit says so — below.
- **`-500`, never `-1000`.** Unkillable turns a leak in the service into a
  wedged host with no kill and no report.
- **The dev units carry none of it.** A reservation everything holds is a
  reservation nobody holds; under pressure dev is what loses, on purpose.

**No spaces inside the earlyoom regexes.** `earlyoom.service` is
`ExecStart=/usr/bin/earlyoom $EARLYOOM_ARGS`, unquoted, so systemd splits on
whitespace with no shell quoting — a space would silently become a second
argument, earlyoom would exit on it, and the host would be left with no early
killer and an `active`-looking unit. The SocratiCode server's `comm` is
literally `npm exec socrat`, so match it start-anchored as `^npm`.

## A floor is only as high as the slices above it (#85)

cgroup v2 caps a unit's effective protection at what every ancestor grants
(`effective_protection()` in `mm/page_counter.c`), and `system.slice` ships
`memory.low` 0. So from #74 to #85 `notifier.service` claimed 192M and kept 0,
while `systemctl show -p MemoryLow`, the unit's own `memory.low`, a clean
`daemon-reload` and this repo's drift test all read 192M.
`memory_recursiveprot` would not have helped: it shares a parent's *unclaimed*
grant, and a parent at 0 has none. This host's cgroup2 mount lacks it anyway.

The chain as installed:

| cgroup | `memory.low` | Set by `deploy/` |
|---|---|---|
| `system.slice` | 384M | `system.slice.d/10-memory-protection.conf` |
| `├ notifier.service` | 192M | `notifier.service` |
| `└ system-postgresql.slice` | 192M | `system-postgresql.slice.d/10-memory-protection.conf` |
| `  └ postgresql@16-main.service` | 192M | `postgresql@16-main.service.d/10-memory.conf` |

- **Each slice grants exactly what its children claim.** Less and each child
  keeps only a usage-proportional share; more is protection nothing claims.
- **The template instance needs its own slice link.** `system-postgresql.slice`
  is implicit, created with no settings, and clamps its unit at 0 under any
  `system.slice` grant — measured on address-validator.
- **PostgreSQL is reserved because the API is only as protected as its
  database.** Its floor clears the 121 MiB peak with the same margin as the
  service's. The cluster also serves `notifier_dev` and `notifier_test`; one
  cluster, one floor.
- **A floor is not an allocation.** It protects only what its unit actually
  uses, so 384M bounds what the sessions can lose to it; at today's usage
  that is ~150 MiB. The sessions run in `/init.scope`, beside `system.slice`,
  so no grant here covers them.

`daemon-reload` applies every link to the running units, with no restart
(PostgreSQL's floor included, verified 2026-09-24).

## Verify live

**Only the effective value is evidence.** Walk `memory.low` up from each unit's
real `ControlGroup`; the smallest link is what the unit keeps:

```bash
for unit in notifier postgresql@16-main; do
  cg=$(systemctl show "$unit" -p ControlGroup --value) low=
  while [ -n "$cg" ] && [ "$cg" != / ]; do
    v=$(cat "/sys/fs/cgroup$cg/memory.low")
    if [ -z "$low" ] || [ "$v" -lt "$low" ]; then low=$v; fi
    cg=${cg%/*}
  done
  echo "$unit keeps at most $((low / 1048576)) MiB"
done
systemctl show notifier -p OOMScoreAdjust
cat /proc/sys/vm/min_free_kbytes
tr '\0' '\n' < /proc/$(systemctl show earlyoom -p MainPID --value)/cmdline
```

`tests/deploy/test_memory_reservation.py` asserts the files everywhere, and on
this host (hostname `notifier`) also reads the same chain live: each floor's
effective value, the cgroup systemd actually chose, and that no slice's
children claim past its grant. That last check catches a unit that was
installed from outside `deploy/`. The live tests skip in CI.

## Sessions sit at adj 0 here, pinned live (#88)

Row U attributes half its severity to exe.dev session processes inheriting
`oom_score_adj` **-1000** from `exe-init` and `sshd`, which would make them
unkillable. **That does not hold here.** Measured on this host 2026-09-18 (#74)
and again 2026-09-24 (#88): only `sshd` and `exe-init` carry -1000. The
session root beneath `sshd` (`sshd-session`) and every `claude`, `MainThread`
and `npm exec socrat` under it sit at **0**. So the killer *can* pick them,
and `OOMScoreAdjust=-500` is what makes it prefer them over production.

That makes notifier's earlyoom the only one of three cohort installs that works
as intended (CannObserv/replicator#112). Elsewhere, sessions sit at -1000, and
earlyoom 1.7 skips those outright, whether they match `--prefer` or not. What
decides the score is exe.dev's setup, and it is still undetermined. Whether
`exe-init` is present does not decide it: address-validator has no `exe-init`
and its sessions still sit at -1000. If the score changes here, earlyoom
silently becomes a killer of small daemons with no config drift, so the premise
is pinned. `test_sessions_here_sit_at_adj_zero` walks from the test process to
the child of `sshd` or `exe-init` and asserts that it is at 0. That child is the
session root, which a `choom`'d leaf cannot distort. The test skips in CI and
outside a session. If it fails, launch sessions under `choom -n 500 --`
(gregoryfoster/skills `host-memory.md` § 1).
