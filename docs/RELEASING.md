# Releasing notifier

The service and its Python SDK carry **one version**. A release is one version
bump, one CHANGELOG entry, one git tag — and the tag is what a consumer pins.

Design: [`docs/plans/2026-09-01-sdk-release-propagation-design.md`](plans/2026-09-01-sdk-release-propagation-design.md)
([#50](https://github.com/CannObserv/notifier/issues/50)).

## Versioning policy

**SemVer, 0.x line.** Breaking change to the API surface or the SDK's public
surface → MINOR (`0.3.x` → `0.4.0`); additive or fix → PATCH.

**One version, mirrored in several files.** All of them move together, in one commit:

| Site | What reads it |
|---|---|
| `pyproject.toml` `[project] version` | the service distribution |
| `src/api/main.py` — `FastAPI(version=)` | the OpenAPI spec's `info.version`; the only copy a consumer sees at runtime |
| `clients/python/pyproject.toml` | what a consumer resolves |
| `clients/python/src/notifier_client/__init__.py` — `__version__` | what a consumer introspects |
| `clients/python/CHANGELOG.md` — top heading | the compatibility record |

`tests/ci/test_version_lockstep.py` fails if any pair disagrees. It reads the
files rather than importing them: `notifier_client` is not a dependency of the
service and is not installed in its venv, and `main.py` stays a plain literal
rather than acquiring an `importlib.metadata` lookup to satisfy a test.

**Both directions cost a release.** A schema change bumps the version because
the SDK regenerates; a change confined to `clients/python/` bumps it because
the versions are locked. The latter is the common case — 0.3.1 was a generator
upgrade with no server change at all. Say which in the CHANGELOG: an
`Unchanged` section stating the public API did not move is what makes an
SDK-only release cheap for a consumer to read.

**A server version bump does not dirty `generated/`.** `regen.sh` runs
`openapi-python-client` with `--meta none`, and no generated file carries a
version string — the spec's `info.version` is not consumed by the generator.
So the sites bump in any order in one commit, with no regen step wedged
between them.

## Cutting a release

From a clean `main`, CI green:

1. **Choose the bump** from what merged since the last tag.

2. **Bump every site in the table above** to `X.Y.Z`.

3. **Roll `clients/python/CHANGELOG.md`.** New `## X.Y.Z — YYYY-MM-DD` heading
   at the top, entries grouped Breaking / Added / Changed / Removed /
   Unchanged. Downstream-facing impact only; the reasoning belongs in the issue
   and the design doc.

4. **Refresh both lockfiles**, or CI fails at install:

   ```bash
   uv sync && (cd clients/python && uv sync)
   ```

   Both `uv.lock` files record the project's own version, and every CI job
   installs with `uv sync --locked`. A bump without this is a red run that
   reads like a dependency problem.

5. **Run the gates:**

   ```bash
   . scripts/load_env.sh
   uv run pytest
   uv run pre-commit run --all-files
   clients/python/scripts/regen.sh && git diff --exit-code clients/python/src/notifier_client/generated/
   (cd clients/python && uv run pytest)
   ```

6. **Commit, tag, push — one push:**

   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push --follow-tags
   ```

   `--follow-tags` is deliberate. The two-command form (`git push && git push
   --tags`) leaves `main` carrying an untagged release commit whenever the
   second command fails, which is exactly how `v0.3.0` and `v0.3.1` were lost.
   One command cannot half-succeed that way.

7. **Confirm the run is green.** `main` is the deployed code.

8. **Restart the services** to pick up the release:

   ```bash
   sudo systemctl restart notifier notifier-dev
   ```

## The gates

Two tests in `tests/ci/` enforce the above. Neither needs a workflow of its
own, which is why every workflow in this repo still takes
`permissions: contents: read` — an auto-tagging job would need `contents:
write`, one privileged grant in the one place that also holds the release
decision, to save step 6 a line.

- **`test_version_lockstep.py`** — every version site agrees.
- **`test_release_tags.py`** — the current version has a tag, *unless* HEAD is
  the commit that introduced it. That single commit of grace is the release
  commit before its tag is pushed; anything past it fails. Under this rule
  `v0.3.0` would have failed at the very next merge to `main` rather than going
  unnoticed through a further release.

  It needs tags and history: `ci.yml`'s test job checks out with
  `fetch-depth: 0`, and `test_workflows.py` asserts it keeps doing so. Under
  `actions/checkout`'s default the gate would find no tag, find no `HEAD~1`,
  and pass vacuously. The test refuses a shallow checkout rather than reporting
  green from one.

## Tags

Plain `vX.Y.Z`. The lockstep collapses the service and SDK into one version, so
there is no `sdk-` prefix and no second series.

**Tags are immutable.** A botched release gets a new patch tag, never a moved
one.

**`v0.2.0` and `v0.2.1` predate this policy.** They name SDK versions cut while
the server declared 0.1.0. `v0.3.1` is the first release where the two agree;
the server's version jumps 0.1.0 → 0.3.1 to meet the SDK, and no server 0.2.x
exists. The old tags were not re-pointed.

## Adopting a release in a consumer

The SDK is consumed as a **pinned git-tag source**. `CannObserv/notifier` is
public, so this needs no credential — no SSH key, no deploy token, no index:

```toml
[project]
dependencies = ["notifier-client"]

[tool.uv.sources]
notifier-client = { git = "https://github.com/CannObserv/notifier.git", subdirectory = "clients/python", tag = "v0.3.1" }
```

To adopt a later release, change the tag and `uv sync` — which refreshes the
consumer's own lockfile, freezing the resolved commit. **To stay put, do
nothing:** the consumer keeps building against the tag it last adopted, which
is the point of the decoupling.

Do not use an SSH host alias. Watcher's pin is
`ssh://git@github-notifier/CannObserv/notifier.git`, an alias that exists only
on the watcher VM, and its CI has to `git config url.insteadOf`-rewrite the URL
back to HTTPS to install at all. That workaround predates the repo going
public and should not be copied into a new consumer.

## Graduating to a published package

The current transport is a git source. uv treats a git source as authoritative
and **does not enforce a version floor against it**, so a floor beside a
`tool.uv.sources` entry documents intent and nothing more — the tag is the pin.
That is the one thing a published package would buy.

Graduate when either becomes true:

- **A third consumer exists.** Two consumers can each carry a `tool.uv.sources`
  entry; a growing set makes the published artifact cheaper than the ceremony.
- **A consumer needs enforced floors** — a resolve that fails on
  `notifier-client>=0.4` when only 0.3.x is published, rather than silently
  resolving whatever the tag holds.

Two destinations, and the choice is open:

- **The cohort's private index** (`gs://co-gcs-pypi`, as `cannobserv` publishes
  `co-core`). Costs notifier a Workload Identity Federation setup, bucket IAM,
  and a consumer-side wheelhouse sync. Note what that buys and what it costs:
  the index exists to distribute a *private* library, and this repo is public,
  so it would add a cloud-auth dependency — the absence of which is currently
  why notifier's CI and Dependabot work where the sibling repos' arrangements
  break.
- **Public PyPI**, via trusted publishing (OIDC, no stored secret). No auth for
  any consumer, floors enforced, Dependabot native. `notifier-client` is far
  too generic a distribution name to claim there; it would need to be something
  like `cannobserv-notifier-client`. No index carries the name today, so the
  rename costs nothing until this path is chosen.

Either way, only the consumer's dependency line changes. `uv build` from
`clients/python/` already emits a wheel, and the version discipline, CHANGELOG,
and tag semantics above are identical under all three transports.
