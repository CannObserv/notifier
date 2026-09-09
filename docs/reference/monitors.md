# Monitors — the dead-man's timer

How notifier alerts on the **absence** of a report, not only on its contents.
Added in #56 for the broker (CannObserv/broker#1, #3); consumer-agnostic, so
any node with an API key can use it.

## Why absence

A findings-only push is silent in exactly the cases that matter most. A dead
probe, a stopped timer, a wedged `uv run`, and a dead node all produce zero
findings and zero traffic — indistinguishable, from the outside, from a
perfectly healthy consumer.

CannObserv/observo#473 is what that costs: a tailnet-bound Redis crash-looped
and the cluster ran starved for two weeks, because the only thing that would
have said so was a process that had itself stopped.

So a consumer checks in **every tick regardless of findings**, and notifier
alerts when a check-in fails to arrive.

## The model

| Field | Meaning |
|---|---|
| `interval_seconds` | The cadence the consumer promises |
| `grace_seconds` | Slack on top of it before silence is an outage |
| `renotify_seconds` | `null` alerts once per outage; a value repeats every N seconds while missing |
| `channel_ids` | Where alerts go |
| `template_id` / `title_template` + `body_template` | Renders a check-in that reports findings |
| `enabled` | `false` pauses the timer for planned downtime without deleting the configuration |
| `state` | `pending` → `ok` → `missing`, and back |

The deadline is `(last_checkin_at or created_at) + interval + grace`. Anchoring
on `created_at` before the first check-in is deliberate: a monitor configured
here but never wired up on the consumer's side is the most likely
misconfiguration of all, and anchoring on `last_checkin_at` alone would make
it the one case the timer stays silent about forever.

## The API

```bash
# One-time setup
curl -sX POST "http://notifier:9000/api/v1/monitors" \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{
    "name": "co-broker",
    "interval_seconds": 600,
    "grace_seconds": 1200,
    "channel_ids": ["<channel id>"],
    "title_template": "{{ source }}: {{ finding_count }} finding(s)",
    "body_template": "{% for f in findings %}- {{ f.check }} {{ f.subject }}: {{ f.message }}\n{% endfor %}"
  }'

# Every tick, findings or not
curl -sX POST "http://notifier:9000/api/v1/monitors/$ID/checkin" \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{
    "status": "ok",
    "variables": {"source": "co-broker", "finding_count": 0, "findings": []}
  }'
```

Three things a consumer should know:

- **`variables` is opaque.** Notifier stores it verbatim in `last_variables`
  and renders it through your template. `finding_count` and `findings` are the
  broker's vocabulary, not notifier's — nothing here reads inside the bag.
- **`status` is the consumer's judgement.** Two values: `ok` records the
  check-in and sends nothing; `alert` also renders and dispatches. A broker
  maps its own `finding_count > 0` onto it. Notifier learning a consumer's
  taxonomy is the thing AGENTS.md's API Boundary Principles forbid.
- **An `ok` check-in is never schema-checked.** Nothing is rendered, so
  nothing needs validating — rejecting a heartbeat over its payload would
  silence the timer to protect a notification that was never going to be sent.

Responses carry `next_deadline_at`, so a consumer never re-derives
`interval + grace` to know where it stands.

### What gets sent

| Event | Notification |
|---|---|
| `status: "alert"` check-in | The monitor's own template, rendered against `variables` |
| Deadline passes | Built-in: *"{name} has stopped reporting"*, quoting the silence, the cadence, and the missed deadline |
| First check-in after an outage | Built-in: *"{name} has recovered"*, quoting the silence that just ended |

The missing and recovery wording is built in rather than configurable: a
consumer that has stopped reporting cannot supply a template for the fact that
it stopped reporting. A recovery notice exists so the outage alert is not left
as the last word on a problem that is over, which is how a real alert comes to
be read as noise.

A check-in that both ends an outage *and* carries findings produces two
dispatches, not one. "It is back" and "here is what it found" are different
facts.

## The sweep

`deploy/notifier-sweep.timer` runs `scripts/sweep.sh` every 60 seconds, which
runs `scripts/sweep_monitors.py`, which calls `sweep_monitors()`. A dev pair
(`notifier-sweep-dev.*`) does the same against `notifier_dev` for the `:9001`
endpoint.

```bash
systemctl list-timers 'notifier-sweep*'      # is it firing?
journalctl -u notifier-sweep -f              # what did it find?
sudo systemctl start notifier-sweep.service  # force a pass now
```

Three decisions worth knowing rather than rediscovering:

**A systemd timer, not a task inside the API process.** An alerter that rides
the thing it watches stops reporting exactly when it is needed — the same
argument #56 makes against the broker's in-process alternatives. The sweep
needs Postgres and outbound network and no part of the API to be up. It also
avoids two uvicorn workers each running their own copy against different
databases.

**A monitor is marked `missing` whether or not the alert was delivered.** The
state describes the consumer, not our luck reaching Slack. Leaving it `ok`
after a bounced alert would re-alert on every pass forever *and* would keep
reporting a dead consumer as healthy.

**`TimeoutStartSec` is not decoration.** systemd skips a firing while the
previous run is still going, so an unbounded sweep held open by a wedged
delivery endpoint stops every subsequent check — the timer still looks alive
and nothing is being swept.

## The limit: nothing watches the watcher

If `notifier-sweep.timer` stops, every dead-man's timer in the service stops
with it, and nothing says so. That is the failure mode this feature exists to
prevent, one level up.

It is not closed here, and pretending otherwise would be worse than saying so.
What exists today:

- The timer is `WantedBy=timers.target`, so it comes back after a reboot.
- `systemctl list-timers 'notifier-sweep*'` shows the last and next firing.
- A failed pass leaves a failed unit in `systemctl --failed`.

What would close it is an external observer — a monitor on another host, or a
consumer that checks notifier's own liveness — and it needs a decision about
where that observer lives before it can be built.

## Mapping the broker's report

CannObserv/broker#1 specified a flat payload. It maps without loss:

| Broker field | Where it goes |
|---|---|
| `source`, `finding_count`, `findings`, `timestamp` | `variables`, verbatim |
| `finding_count > 0` | `status: "alert"` |
| `finding_count == 0` | `status: "ok"` — still sent, still resets the timer |

One extra field on the broker's side, in exchange for `findings` and
`finding_count` never appearing in notifier's OpenAPI document.

## Related

- [AGENTS.md § API Boundary Principles](../../AGENTS.md#api-boundary-principles) — why the check-in is shaped this way
- [DEPLOYMENT.md](../DEPLOYMENT.md) — installing and enabling the timers
- [tailscale.md](tailscale.md) — the ACL rule a reporting node needs first
