# Common Commands

## Setup

```bash
# Install dependencies (creates .venv automatically)
uv sync
```

## Environment

Two env files, loaded in order:

```bash
# Production secrets (DATABASE_URL, NOTIFIER_SECRET_KEY) — persistent, survives repo resets
/etc/notifier/.env

# Dev/agent secrets (GH_TOKEN, TEST_DATABASE_URL, DEV_DATABASE_URL) — repo root, git-ignored
.env

# Load both for shell commands. Source them; do not word-split through xargs,
# which corrupts values containing spaces or quotes.
. scripts/load_env.sh
```

The systemd service loads both automatically (see `deploy/notifier.service`).

**Loading these leaves `DATABASE_URL` pointing at production.** That is the
intended target for `alembic upgrade head` — on this single-VM setup `main`
*is* the deployed code — and wrong for everything else:

| Want | Use | Database |
|---|---|---|
| Dev endpoint (:9001) | `sudo systemctl restart notifier-dev` | `notifier_dev` |
| Dev server by hand | `./scripts/dev_server.sh` | `notifier_dev` |
| Tests | `uv run pytest` | `notifier_test` (pinned by `tests/conftest.py`) |
| Migrations | `uv run alembic upgrade head` | production, deliberately |

`src/core/db_safety.py` refuses any database whose name does not end in
`_test` or `_dev`. The opt-in `NOTIFIER_ALLOW_PROD_DB=1` lives in
`deploy/notifier.service` and must never be added to an env file — every
process that sources the file would inherit it.

## Service Management

The notifier service runs via systemd. **Always use systemctl** — never start uvicorn manually on port 9000.

```bash
# Restart after code changes (migrations are NOT auto-run)
sudo systemctl restart notifier

# Check status
sudo systemctl status notifier

# Follow logs
sudo journalctl -u notifier -f

# Reload systemd after editing either unit in deploy/
sudo systemctl daemon-reload && sudo systemctl restart notifier notifier-dev
```

The dev endpoint on 9001 is a second unit, `notifier-dev.service`, serving
`notifier_dev`. It is the base URL consumers point their non-production
processes at (#24) — 9000 refuses `development`-marked keys.

```bash
sudo systemctl restart notifier-dev
sudo systemctl status notifier-dev
sudo journalctl -u notifier-dev -f
curl "http://$(tailscale ip -4):9001/health"   # this VM: loopback is NOT bound
```

### The dead-man's-timer sweep

Two systemd *timers* fire `scripts/sweep.sh` every 60 seconds — one against
production, one against `notifier_dev`. Between them they are the only thing
watching for consumer silence (#56), so a stopped timer is a silent outage of
the outage detector.

```bash
systemctl list-timers 'notifier-sweep*'        # is it firing? when next?
sudo journalctl -u notifier-sweep -f           # checked / alerted / undeliverable
sudo systemctl start notifier-sweep.service    # force one pass now
sudo systemctl restart notifier-sweep.timer    # after editing the timer

# Same, dev database
systemctl status notifier-sweep-dev.timer
sudo journalctl -u notifier-sweep-dev -f
```

It launches `scripts/dev_server.sh`, so it inherits every guard that script
carries: the production opt-in is unset, `DATABASE_URL` comes from
`DEV_DATABASE_URL`, the URL check is `src.core.db_safety`, and an unmigrated
dev database refuses to start rather than 500 on every request (#23). If the
unit will not come up, that last one is the usual reason — the journal names
it:

```bash
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
```

## Development

**Dev server workflow:** `scripts/dev_server.sh` is the one launch path, for
the unit and by hand alike — it swaps in `DEV_DATABASE_URL`, runs the
production-database guard, checks the dev database is migrated, then starts
uvicorn on 9001, leaving the live service up:

```bash
# Dev server by hand — same script the notifier-dev unit runs, with --reload
# on. The unit holds port 9001, so stop it first and hand it back after.
# Never hand-run uvicorn; see issue #22.
sudo systemctl stop notifier-dev
./scripts/dev_server.sh
sudo systemctl start notifier-dev
```

`deploy/notifier-dev.service` runs it with `NOTIFIER_DEV_RELOAD=0`: a wedged
reloader keeps *running* after a syntax error, so the unit looks active while
the endpoint is dead. Reasoning and the restart bounds:
[docs/DEPLOYMENT.md](DEPLOYMENT.md).

First-time setup of the dev database:

```bash
sudo -u postgres psql -c "CREATE DATABASE notifier_dev OWNER notifier;"
echo 'DEV_DATABASE_URL=postgresql+asyncpg://notifier:PASSWORD@localhost:5432/notifier_dev' >> .env
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
```

## Migrations

```bash
uv run alembic upgrade head                              # apply all migrations
uv run alembic revision --autogenerate -m "description"  # generate new migration
uv run alembic downgrade -1                              # roll back one
```

## Testing

```bash
uv run pytest                          # default: -m 'not integration'
uv run pytest -m integration           # integration tests (require live DB)
uv run pytest --no-cov                 # skip coverage
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run ruff format --check .           # format gate (CI's lint job + pre-ship.sh)
```

## Lint & format gates

`ruff check` and `ruff format --check` run as separate steps in CI's `lint`
job, again in `pre-ship.sh` before pytest, and are wired into pre-commit — so
a plain `git commit` enforces them locally too:

```bash
uv run pre-commit install              # one-time, per clone
uv run pre-commit run --all-files      # run both gates over the whole repo
git commit --no-verify                 # escape hatch — gates still fail at ship time
```

The hooks shell out to `uv run ruff`, so they use the exact ruff pinned in
`uv.lock` — the same binary CI installs with `uv sync --locked`. No version
skew. Note the hooks stop there: **pre-commit runs no tests**. The suite runs
in CI, and in `pre-ship.sh` — which lives in the
`shipping-work-python-fastapi` skill (`.claude/skills/…/scripts/`), not in
this repo's `scripts/`, which is why grepping the repo for it comes up empty.


## Generating a Fernet key

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Installing the shared Qdrant API key

The SocratiCode store on `co-index` is gated by a **single global** Qdrant
`service.api_key` (#57). There is no key list, no per-client identity and no
per-collection scope, so every cohort VM holds the same secret and a leak
anywhere is a rotation everywhere.

`scripts/install_qdrant_key.sh` merges it into a repo's git-ignored
`.claude/settings.local.json`. **The key arrives on stdin** — never argv, which
is visible in `ps` to every other process for the life of the call and lands in
the caller's shell history.

**It refuses any target git would commit** (#68). Check the repo first:

```bash
git -C <repo> check-ignore -v .claude/settings.local.json   # must print a rule
```

Do not assume the rule is there because a sibling repo has it. CannObserv/broker
had none, is public, and four of the five cohort repos carrying the rule made
the assertion read as true right up to the exception. The script distinguishes
three failures because they have three remedies: **not a work tree** (the check
cannot be made), **tracked** (`.gitignore` does not apply to tracked paths, so
the key may already be in history — untrack *and* rotate), and **not ignored**
(add the rule). It asks `git check-ignore` whatever the rule's source, since a
global `core.excludesfile` genuinely does prevent a commit from that VM. Run from an operator machine, which is the only host
able to reach both ends (exe.dev VMs are isolated from each other, and D13's
`tag:index:22` edge was retired after Phase 6):

```bash
# 1. put the installer on the target (contains no secret)
scp scripts/install_qdrant_key.sh <vm>.exe.xyz:~/

# 2. pipe the key across, host to host — it touches no disk on the way
ssh co-index.exe.xyz \
    "sudo sed -n 's/^QDRANT__SERVICE__API_KEY=//p' /etc/socraticode/qdrant.env" \
  | ssh <vm>.exe.xyz 'bash ~/install_qdrant_key.sh ~/<repo>'
```

Expect `installed 64 chars`. **Any other length is a truncated transfer**, which
401s exactly like a wrong key — the length is the only cheap discriminator.

Verify on the target with `codebase_health`, which must name the external Qdrant
and Ollama rather than a container. `000` on both a keyed and unkeyed probe is
the ACL, not the key, and presents as DNS failure.

**Never run the installer under `bash -x`.** Tracing a script that touches a
credential writes the value to stdout; that is how two were leaked during #57.

Rotation has no overlap window — Qdrant holds one `api_key`, so every client
401s from the restart until it is updated. Sequence: mint, write
`/etc/socraticode/qdrant.env`, `systemctl restart qdrant`, then step 2 against
every VM. Not while an index is running: a half-written collection outlives the
outage.

## Releasing

Full runbook: [RELEASING.md](RELEASING.md). The service and the SDK share one
version, mirrored across several files; `tests/ci/` fails a mismatch and fails a release
whose tag was never cut.

```bash
# Verify every version site agrees and the current version is tagged
uv run pytest --no-cov tests/ci/test_version_lockstep.py tests/ci/test_release_tags.py

# Cut a release (after bumping every version site, rolling the CHANGELOG,
# and refreshing both lockfiles)
git commit -am "release: vX.Y.Z" && git tag vX.Y.Z && git push --follow-tags
```

## SDK regeneration

```bash
# Regenerate the Python SDK from notifier's OpenAPI schema
clients/python/scripts/regen.sh

# Verify SDK is not stale (mirrors CI)
git diff --exit-code clients/python/src/notifier_client/generated/
```

## SDK integration tests

Gated on `TEST_DATABASE_URL`. The fixture creates the schema in that DB,
spawns a uvicorn on an ephemeral port wired to it, seeds a tenant, and drops
the schema on teardown. Every subprocess receives `DATABASE_URL=$TEST_DATABASE_URL`,
so production cannot be polluted.

```bash
. scripts/load_env.sh
cd clients/python && uv run pytest -m integration
```

Skips with a message if `TEST_DATABASE_URL` is unset.

## Generating a tenant + API key (until admin UI exists)

Use `scripts/seed_tenant.py`. The third argument marks which deployment the
key is for — `production` (default) or `development`. **A production
deployment refuses `development` keys at the auth layer** (403), which is the
layer that catches a consumer's test suite calling production over HTTP; no
database guard can see that vector (issue #22, finding 3).

```bash
. scripts/load_env.sh

# Dev tenant, on the dev database (served by notifier-dev.service on :9001)
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/seed_tenant.py acme acme-dev development

# Production tenant — deliberate, opt-in, on the command line only
NOTIFIER_ALLOW_PROD_DB=1 \
  uv run python scripts/seed_tenant.py acme acme-prod production
```

Prints `tenant_id`, `key_id`, `raw_key`, and `environment`. **The raw key is
shown once** — only its SHA-256 hash is stored. Keep the `key_id`: it is what
`rotate_key.py --revoke` takes when this credential is eventually retired.

Those four lines are all that reaches stdout, so piping and copying stay safe.
The mint itself is recorded to journald as `notifier-keys` — `journalctl -t
notifier-keys` — naming the key and never its secret (#67).

This VM already has a `dev` tenant with a `development` key in `notifier_dev`;
the key is in the repo `.env` as `DEV_TENANT_API_KEY`. It also has a `watcher`
tenant there, minted for watcher's non-production processes (watcher#278 step
2); that key lives in watcher's own `.env` as `WATCHER_DEV_NOTIFIER_API_KEY`,
not in this repo.

**Hand a consumer both halves, never just the key:** base URL
`http://notifier:9001` from any node on the tailnet, and a key minted
`development`. The pair only works together — a development key against
`http://notifier:9000` is rejected, which is the point.

### Seeding the dev tenant's sink channels

A dev tenant with a key and no channels can authenticate but cannot dispatch
(#26). `scripts/seed_dev_channels.py` gives one two sinks, neither of which
reaches a real recipient:

```bash
. scripts/load_env.sh
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/seed_dev_channels.py watcher
```

| Channel | Apprise URL | Outcome | Why |
|---|---|---|---|
| `dev-sink` | `syslog://local7` | succeeds | Lands in this VM's journal — `sudo journalctl -t Notifier` shows the rendered payload, so a consumer can read back what it sent |
| `dev-sink-failing` | `json://127.0.0.1:1/sink` | fails | Port 1 is privileged and unroutable, so the refusal is structural. Lets a consumer exercise error handling without waiting for a real outage |

Safe to re-run; existing channels are left alone. It refuses any database whose
name does not end in `_dev` — **including with `NOTIFIER_ALLOW_PROD_DB=1` set**,
which is deliberate: seeding fixture rows is never a production operation, and
fixture channels in the production tenant is the shape of the incident behind
watcher#278.

### Dev channels are sink channels by construction

`notifier_dev` is a separate database from `notifier`, so the production Slack
and Mailgun channel rows do not exist in it. A dev dispatch has nothing real
to reach unless someone deliberately seeds a live Apprise URL into the dev
database. Do not "helpfully" copy production channels across — that recreates
the exact failure watcher#278 documents, where ~1289 fixture notifications
were delivered to real recipients.

## Copying channels to a new tenant

How a new consumer gets the cohort's existing Slack and Mailgun destinations
(#70). `scripts/copy_channels.py` copies the stored ciphertext, so the Apprise
URL is never decrypted, printed or pasted. The API only returns a masked URL,
so re-creating the channel through `POST /channels` would mean somebody
handling the secret.

```bash
. scripts/load_env.sh

# Rehearse: every refusal fires, nothing is written
NOTIFIER_ALLOW_PROD_DB=1 uv run python scripts/copy_channels.py \
  --to-tenant <target id> --expect-name <target name> \
  --channel <source channel id>=<new name> \
  --channel <source channel id>=<new name> \
  --dry-run

# Then the same command line without --dry-run
```

Prints each new `channel_id`, which is what the consumer puts in
`channel_ids`. `--expect-name` is always required: the target id decides who
receives the grant, and a typo naming another consumer would hand it the
destination. A name the target already has is refused, so re-running is safe.
Every copy is recorded (`journalctl -t notifier-keys`) naming both ends,
never the URL.

This copies **between tenants in one database**. Copying a production channel
into `notifier_dev` is the operation the section above forbids, and this
script cannot reach it.

## Attaching, revoking, and rotating a key

`seed_tenant.py` always creates a **new** tenant. To give a tenant that already
exists a second credential, to retire one, or to rotate — `scripts/rotate_key.py`
(#62). Keeping the two apart is deliberate: a script named `seed_tenant` that
sometimes deletes credentials is the wrong thing to find during an incident.

```bash
. scripts/load_env.sh

# Read first. --revoke needs a key id, and this is where you get it.
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/rotate_key.py --tenant-id <id> --list

# Attach a second key to an existing tenant
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/rotate_key.py --tenant-id <id> --new-label backup

# Rotate: mint the replacement and delete the old key in ONE transaction
NOTIFIER_ALLOW_PROD_DB=1 \
  uv run python scripts/rotate_key.py \
    --tenant-id <id> --new-label <new-label> --revoke <old-key-id> \
    --verify "http://$(tailscale ip -4):9000" --verify-old <old-raw-key>
```

Production carries the same opt-in as every other script here — on the command
line, for the single invocation, never in an env file.

Both halves land on the credential audit channel — `journalctl -t
notifier-keys` — naming the key and never its secret. The revoke half is the
one that matters: it is a DELETE, so once the run ends that record is the only
thing that will ever say which key went, or when (#62, #67).

| Flag | What it does |
|---|---|
| `--list` | Print the tenant's keys and exit — including the `key_id` that `--revoke` takes. Read-only, and refuses to be combined with any other flag, so a read never doubles as a write |
| `--new-label` | Mint a key with this label |
| `--environment` | `production` (default) or `development`, for the key being minted. Rejected without `--new-label` — it does not retag an existing key |
| `--revoke <key-id>` | Delete this key, named explicitly. Never "the other one" |
| `--force` | Permit revoking a tenant's **last** key. Requires `--revoke`; unreachable on a rotation, since the replacement is flushed before the count is read |
| `--dry-run` | Rehearse everything, refusals included, and roll back |
| `--yes` | Skip the confirmation prompt. Required when stdin is not a terminal |
| `--verify <base-url>` | After committing, prove the new key gets a 200 |
| `--verify-old <raw>` | Also prove the old key now gets a 401. On a run that mints nothing the check is labelled `(uncontrolled)`: with no new key to get a 200, nothing establishes the endpoint would accept a good one |

Exit codes: `0` done, `1` committed but not proven — the checks failed, or
there was nothing to check — `2` refused (nothing written), `3` aborted at the
prompt.

`--verify` on a revoke with no replacement is that second case: the script
holds no raw key to present, so it reports that nothing could be checked and
exits `1` rather than exiting `0` in silence.

**Verification is asymmetric, and that is not an oversight.** The script holds
the raw key it just minted, so it can always prove that one works. It only ever
held the *hash* of the key it revoked, so proving the old one is dead needs you
to supply it — which you have during an exposure, and do not during a routine
rotation. Without `--verify-old` the script says the old key went unchecked
rather than passing over it.

**A 403 on the old key is not proof of revocation.** 403 is what a production
deployment returns for a `development` key — a perfectly valid credential being
turned away. Only **401** means the row is gone. `--verify-old` insists on 401
for that reason.

**Revocation is a `DELETE`, and there is no `revoked_at`.** A column would leave
an audit trail but would require every present and future key lookup to filter
on it; forgetting that filter anywhere means a revoked credential that still
authenticates. `DELETE` fails closed. The audit trail is taken as a log line on
every mint and revoke — tenant, key id, prefix, label, never the raw key.

**What this deliberately will not do: delete a tenant.** That cascades channels,
monitors and dispatch history, and is not an incident-time operation. It has its
own script, below.

## Deleting a tenant

`scripts/delete_tenant.py` (#79). Deleting a tenant destroys every credential
that consumer holds, plus its channels, templates, monitors and dispatch
history — and until this script there was no sanctioned path for it at all:
`seed_tenant.py` only creates and `rotate_key.py` only works on keys, so a
tenant delete meant ad-hoc SQL against production, the failure `rotate_key.py`
exists to retire, still live for the larger operation.

```bash
. scripts/load_env.sh

# Read first. A rehearsal names every key and counts everything else.
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/delete_tenant.py --tenant-id <id> --dry-run

# Then do it, naming the tenant you believe that id belongs to
NOTIFIER_ALLOW_PROD_DB=1 \
  uv run python scripts/delete_tenant.py --tenant-id <id> --expect-name <name>

# Unattended, and its own rehearsal — the same command line plus one flag
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/delete_tenant.py --tenant-id <id> \
    --expect-name <name> --yes --dry-run
```

| Flag | What it does |
|---|---|
| `--tenant-id` | The tenant to destroy. Its id, never its name |
| `--expect-name <name>` | The name you believe that id belongs to; refuses if it does not match. **Required with `--yes`** |
| `--dry-run` | Rehearse everything, refusals included, and roll back. Records nothing |
| `--yes` | Skip the confirmation prompt. Required when stdin is not a terminal. Accepted with `--dry-run`, which has no prompt to skip, so an unattended run can be rehearsed as itself plus one flag |

Exit codes: `0` done, `2` refused (nothing written), `3` aborted at the prompt.
`1` is unused here — it is `rotate_key.py`'s "committed but not proven", and a
deleted tenant has no key left to prove anything with.

**`--expect-name` is required with `--yes`, and that is the point of it.** A
revoke names one key on one tenant, and a mistyped ULID is caught by the
ownership check. Here the ULID *is* the whole target: a typo that happens to
name another consumer deletes that consumer instead. The prompt prints the name
and asks you to type it back; `--yes` removes the prompt, so it has to supply
the name in its place.

**Every destroyed key lands on the credential audit channel** — `journalctl -t
notifier-keys` — as one `api key destroyed with tenant` record naming the key
and never its secret, followed by a `tenant deleted` summary. Before #79 the
keys went by `ON DELETE CASCADE`, never through `revoke()`, so the operation
that destroys the most left the least: nothing at all.

**A hand-written `DELETE FROM tenants` does not work**, quite apart from
recording nothing. `dispatch_attempts.channel_id` is `ON DELETE RESTRICT`, and
Postgres checks it the moment the cascade reaches `channels` — deleting the
attempt rows in the same statement does not excuse it, since `RESTRICT` is
immediate where `NO ACTION` is deferred. So the bare statement raises a
foreign-key violation for any tenant that has ever dispatched, which is every
tenant worth deleting. `src/core/tenants.py` clears those rows first.

The deletion and its records are one function there, and it owns its
transaction — unlike `mint` and `revoke`, which flush and leave the commit to
the caller. The records follow the commit: a rehearsal that left "api key
destroyed with tenant" in the journal would be a live credential recorded dead,
which is worse than no record, because someone will trust it.
