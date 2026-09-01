# SDK release and propagation

**Status:** approved design, not yet implemented
**Supersedes:** [#49](https://github.com/CannObserv/notifier/issues/49)
**Related:** [#44](https://github.com/CannObserv/notifier/issues/44) (Observo provisioning)

## Problem

Generation is sound. Propagation does not exist.

`clients/python/` regenerates from `app.openapi()` via `scripts/regen.sh`, and
`sdk-staleness.yml` fails any push to main or PR that leaves `generated/`
stale, then runs the SDK unit suite against the regenerated client. Schema and
client cannot drift silently.

Nothing carries a release to a consumer. There is no `RELEASING.md`, no tag
step, and no gate. The consequences are live:

- **0.3.0 and 0.3.1 were never tagged.** `git ls-remote --tags origin` returns
  `v0.2.0` and `v0.2.1` and nothing else. Both versions exist in the SDK's
  `pyproject.toml` and CHANGELOG; neither is installable by the documented
  `@vX.Y.Z` line. The staleness gate proves the SDK matches the schema; nothing
  proves a consumer can obtain it.
- **Watcher is two releases behind and cannot move.** Its pin is
  `rev = "v0.2.1"`, SHA-frozen at `c6b36b2` in `uv.lock`. Adopting 0.3.1 today
  would require a raw SHA or a branch. It is also still carrying
  `python-dateutil` transitively — the exact break 0.3.1's CHANGELOG documents,
  unmet only because the pin is stale.
- **The SSH alias is dead weight.** Watcher's source is
  `ssh://git@github-notifier/CannObserv/notifier.git`, a host alias that exists
  only on the watcher VM, forcing its CI to `git config url.insteadOf`-rewrite
  to HTTPS. `CannObserv/notifier` is public; no credential is required. Left
  alone, Observo inherits the workaround by copy-paste.
- **The version claim is false** (#49). Three files state the SDK is pinned 1:1
  with the server. Server is 0.1.0 (`pyproject.toml:3`, `src/api/main.py:21`);
  SDK is 0.3.1. `clients/python/tests/test_version_lockstep.py` checks the SDK's
  three copies of its own version against each other and never reads the
  server's.

## Decisions taken

Two forks were decided by the owner of the version promise:

1. **Real lockstep.** The SDK version and the server version move together;
   #49's option (2). The cost is symmetric and accepted: a generator upgrade
   forces a server bump (that was 0.3.1), and a server-only endpoint addition
   forces an SDK release whose public surface is unchanged. The SDK CHANGELOG's
   existing "Unchanged" sections already absorb this — it is a documentation
   habit, not new machinery.
2. **Manual tag, gated by CI** — cannobserv's shape, not an auto-tagging
   workflow. Every workflow in this repo stays at `permissions: contents: read`.

A third decision framed both: **design so that neither the private-index nor
the public-PyPI transport is foreclosed.** Version discipline, changelog, and
tag semantics are identical under all three transports; only the consumer's
dependency line differs.

## Design

### 1 · One version, five sites

| Site | Today | After |
|---|---|---|
| `pyproject.toml:3` | 0.1.0 | 0.3.1 |
| `src/api/main.py:21` (FastAPI `version=`) | 0.1.0 | 0.3.1 |
| `clients/python/pyproject.toml` | 0.3.1 | 0.3.1 |
| `notifier_client.__version__` | 0.3.1 | 0.3.1 |
| SDK `CHANGELOG.md` top heading | 0.3.1 | 0.3.1 |

The server jumps 0.1.0 → 0.3.1 and never had a 0.2.x. Deliberate, and recorded
as such in `docs/RELEASING.md`: the SDK's line is the one that survives, because
it is the line consumers have been reading.

**A server version bump does not dirty `generated/`.** Verified: `regen.sh`
runs `openapi-python-client` with `--meta none`, and no file under
`generated/` carries a version string — the spec's `info.version` is not
consumed by the generator. The five sites can therefore be bumped in one commit
in any order, with no regen-ordering constraint in the runbook.

### 2 · Where the lockstep assertion lives

New `tests/ci/test_version_lockstep.py` asserts all five sites agree.
`src/api/main.py`'s literal is read by AST, so the module stays a plain literal
with no `importlib.metadata` runtime coupling.

It goes in `tests/ci/`, **not** the SDK suite. `clients/python` ships to
consumers as a standalone package; its tests must not read files above its own
root. `tests/ci/` is already this repo's home for drift tests that reach into
`clients/python/` — `test_dependencies.py` covers both dependency tables from
there.

`clients/python/tests/test_version_lockstep.py` is unchanged: it keeps checking
the SDK's three internal copies against each other, which is exactly what a
shipped package should assert about itself.

### 3 · Release procedure

New `docs/RELEASING.md`, cannobserv's runbook shape: bump the five sites, roll
the SDK CHANGELOG, sync both trees, run the gates, commit `release: v0.X.Y`,
tag, push.

Two deliberate divergences from cannobserv:

- **`git push --follow-tags`, one command.** cannobserv's runbook is
  `git push && git push --tags` and then has to warn that a failed second
  command leaves an unvalidated release commit on main. One command removes the
  hazard instead of documenting it.
- **A tag-presence gate.** On push to main, fail if the current version has no
  tag anywhere in history — with exactly one exception: HEAD is the
  version-bump commit itself. One commit of grace. Under this rule 0.3.0 would
  have failed at the very next merge rather than going unnoticed through 0.3.1.
  Lives in `tests/ci/`, so `contents: read` is preserved everywhere.

Tags stay plain `vX.Y.Z`. Lockstep collapses the two version streams, so no
`sdk-` prefix is needed. `v0.2.0` and `v0.2.1` keep their historical meaning
(SDK 0.2.x against server 0.1.0) and are noted in the runbook as pre-policy;
tags are immutable and are not re-pointed.

### 4 · Transport

The documented install becomes:

```bash
uv add "notifier-client @ git+https://github.com/CannObserv/notifier.git@v0.3.1#subdirectory=clients/python"
```

Public repo, no credential, no SSH alias, nothing for a new consumer to copy
wrongly. `clients/python/README.md`'s install line (currently `git+ssh` at the
stale `v0.2.1`) is updated to match.

The consumer adoption procedure — edit the tag, `uv sync` — is documented
alongside it, mirroring cannobserv's Path A so the cohort reads one workflow
across both libraries.

### 5 · Keeping the other transports open

Nothing above assumes a git source. `uv build` from `clients/python` already
emits a wheel; hatchling is configured. Graduating means appending a publish
step to the tag trigger and swapping the consumer's `tool.uv.sources` entry for
a plain floor.

`docs/RELEASING.md` records the trigger explicitly: **graduate when a third
consumer exists, or when a consumer needs enforced floors.** Git sources ignore
floors — uv treats the source as authoritative, which cannobserv verified and
documented — so a floor is advisory under the current transport and becomes
load-bearing under either published one.

Noted, not acted on: `notifier-client` is too generic a distribution name for
public PyPI, and would likely need to be `cannobserv-notifier-client` there.
No index carries the name today, so renaming costs nothing until that path is
chosen.

**Why not the cannobserv wheelhouse now.** `gs://co-gcs-pypi` exists to
distribute a *private* library. Notifier is public. Paying Workload Identity
Federation, bucket IAM, and a consumer-side sync script to hand over a public
artifact inverts the reason that machinery was built, and it would give notifier
the cloud-auth dependency whose absence currently keeps its CI and Dependabot
working where the sibling repos' break. Normalize the contract — tag is the pin,
changelog is the compatibility record, one adoption procedure — not the
transport.

### 6 · Not doing

**No root CHANGELOG.** The SDK's is shipped and consumer-facing; the server has
no external release audience, and a second changelog under a single version is
one more place to forget.

## Testing

- `tests/ci/test_version_lockstep.py` — the five sites agree.
- `tests/ci/` tag-presence gate — the current version has a tag, unless HEAD is
  the bump commit.
- `clients/python/tests/test_version_lockstep.py` — unchanged.
- Existing `sdk-staleness.yml` — unchanged; it covers a different failure.

TDD applies: each gate is written failing first. The lockstep test fails today
against 0.1.0 vs 0.3.1, and the tag gate fails today against the missing
`v0.3.1` tag — both are red before any fix, which is the intended starting
state.

Two mechanics found while implementing, both now in `docs/RELEASING.md`:

- **The tag gate needs a non-shallow checkout with tags.**
  `actions/checkout` defaults to `fetch-depth: 1`, under which the gate finds
  no tag, finds no `HEAD~1` to compare against, and passes vacuously. `ci.yml`'s
  test job sets `fetch-depth: 0`; `test_workflows.py` asserts it keeps doing so;
  and the test refuses a shallow checkout rather than reporting green from one.
- **A version bump touches both `uv.lock` files.** Each records the project's
  own version, and every CI job installs with `uv sync --locked` — so a bump
  without a lock refresh is a red run that reads like a dependency problem.

## Cross-repo follow-ups

Issues only, never commits — sibling repos own their own review and release
cadence.

- **watcher:** switch `tool.uv.sources` to `git+https`, drop the CI
  `url.insteadOf` rewrite step, adopt v0.3.1, and declare `python-dateutil`
  directly if anything still imports it (0.3.1 removed it from the SDK's
  dependencies).
- **Observo:** add the SDK adoption line to #44, alongside the ACL, tenant, and
  credential-placement work already scoped there.

## Sequencing

1. Red: `tests/ci/test_version_lockstep.py` and the tag-presence gate.
2. Green: bump the two server sites to 0.3.1; reword the 1:1 prose in the three
   files #49 names.

   **Corrected during implementation.** This step originally read "drop the 1:1
   prose", carried over from #49's option (1). Under option (2) — the decision
   actually taken — the claim becomes *true and enforced*, so deleting it would
   remove an accurate statement consumers depend on. The three files keep the
   claim, reworded to name the gate that holds it up.
3. `docs/RELEASING.md`, plus the README install line.
4. Cut and push `v0.3.1` per the new runbook — the first release to exercise it.
5. File the two cross-repo issues.

#49 closes when step 2 lands.
