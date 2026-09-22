---
name: shipping-work-python-fastapi
description: "For Python/FastAPI projects (uv + ruff + pytest; Alembic migrations, systemd service restarts): finalizes work by ensuring everything is committed, pushed to the remote, and reflected on GitHub: closes issues, posts summary comments, and presents a completion table. Use when the user says 'ship it', 'push GH', 'close GH', or 'wrap up' and the project is a FastAPI service."
compatibility: Designed for Python FastAPI projects using uv, ruff, pytest. Requires git, gh, uv. pytest-cov is optional — pre-ship.sh auto-detects it and adds --no-cov when present.
metadata:
  author: gregoryfoster
  version: "1.5"
  overrides: gregoryfoster-skills/shipping-work-python-fastapi
  synced-from: "gregoryfoster-skills v1.5 (2e90414)"
  override-reason: "Sources /etc/notifier/.env and $PROJECT_ROOT/.env before delegating to upstream pre-ship; names notifier's two systemd units and dev port"
  triggers: ship it, push GH, close GH, wrap up
---

# Shipping Work — Python/FastAPI — notifier

Finalizes work: pre-ship checks, clean commit, push, GitHub issue comments, and closure. Tuned for Python FastAPI projects (uv + ruff + pytest).

## The Iron Law

```
NO PUSH WITHOUT PASSING PRE-SHIP CHECKS — VERIFIED IN THIS SESSION
NO ISSUE CLOSURE WITHOUT FULL IMPLEMENTATION — VERIFIED AGAINST ORIGINAL REQUIREMENTS
```

## Rationalization prevention

| Thought | Reality |
|---|---|
| "Checks passed earlier in this session" | Run them again. State can change. Require fresh output. |
| "It's basically done, just needs minor cleanup" | Incomplete = not done. Finish or explicitly descope before closing. |
| "The issue will track follow-up work" | Only close if the core requirement is fully met. Open a new issue for follow-up. |
| "gh push is failing, I'll skip it" | Resolve the error. Do not mark as shipped without a successful push. |
| "User is in a hurry" | A bad ship is slower than a good one. Run the checklist. |

## Parameterized invocation

Trigger phrases may include scope inline — e.g., `wrap up #19 #20`, `ship it #14`. Apply the appended issue numbers as the explicit scope (step 1 of Scope detection); skip the conversation-context fallback.

## Scope detection

Determine which GitHub issue(s) to close (priority order):
1. **Explicit scope** — user specifies issue number(s)
2. **Conversation context** — issues referenced in recent commit messages or discussion
3. **Ask** — if ambiguous, confirm before closing anything

## Procedure

### Step 1 — Run pre-ship checks

<!-- skill:required id=skill-scripts -->
```bash
N=shipping-work-python-fastapi
{ [ ! -x .skills/doctor.sh ] || bash .skills/doctor.sh; } || exit 1
for S in doc-check.sh check-status.sh push.sh comment-issue.sh close-issue.sh pre-ship.sh; do SD=
  for d in scripts ".claude/skills/$N/scripts" "$HOME/.claude/skills/$N/scripts"; do
    [ -f "$d/$S" ] && { SD="$d"; break; }
  done
  [ -n "$SD" ] || echo "$S not found in scripts/, .claude/skills/$N/scripts/, or ~/.claude/skills/$N/scripts/" >&2
  echo "<$S>=${SD:?}/$S"
done
bash "${SD:?}/$S"
```

The first line is a preflight: when `.skills/doctor.sh` is present, it heals any dangling vendor symlinks (or reports an actionable error); when absent, the group is a no-op. `|| exit 1` skips `pre-ship.sh` if the doctor reports unrecoverable state so the original "No such file or directory" noise doesn't drown out the doctor's message. The loop then resolves each script against the skill directory rather than the cwd — a bare `scripts/` path resolves relative to the project root, where the script does not exist ([#63](https://github.com/gregoryfoster/skills/issues/63)). A project-local `scripts/<name>` still wins, for that script alone: a `scripts/pre-ship.sh` wrapper must not send the other five looking beside it ([#301](https://github.com/gregoryfoster/skills/issues/301)). A script found nowhere stops the block here, by name. `pre-ship.sh` is listed last, so the final line runs it. Resolution runs *after* the doctor so a freshly healed symlink chain is visible to it.

In every later step a `<name.sh>` is a **placeholder** for the path printed for that script — substitute it literally (same convention as `init-project-fastapi` Phase 0). Each Bash invocation runs in a fresh shell, so nothing the block set is inherited.

```
NO CONTINUATION IF CHECKS FAIL
```

If checks fail: stop, report the failure, fix before proceeding. Do not push failing code under any circumstances.

`pre-ship.sh` runs ruff, then `uv run pytest -x` with `integration`-marked tests deselected on top of the project's own `addopts` marker expression — never by passing `-m`, which would replace it ([#304](https://github.com/gregoryfoster/skills/issues/304)). A project whose own hook adds `uv run` arguments (`--group seed`) commits them to `.skills/pre-ship-uv-args` (whitespace-separated, `#`-comments ignored); every uv call in the gate gets them.

### Step 1.5 — Documentation spot-check

```bash
bash "<doc-check.sh>"
```

`doc-check.sh` lists files changed on this branch vs the upstream default branch and flags any that match the project's sensitive-path list; when a sensitive path changes, the matching doc sections may need updating too. Entries match path *segments*, so `pyproject.toml` covers `clients/python/`'s as well as the root one, and `CHANGELOG.md` covers `clients/python/CHANGELOG.md`, the only one this repo tracks. notifier commits **both** halves, each of which **replaces** the script's generic FastAPI defaults rather than extending them: `.skills/doc-sensitive-paths` (#47) says what the gate watches, and `.skills/doc-sections` (#65) is the advice printed on a hit — read each file for what it carries and why. Tailoring only one is what upstream's half-tailoring note reports; both are tailored here, so a hit prints neither note. `tests/ci/test_doc_sensitive_paths.py` fails on a watched path that matches no tracked file, and `tests/ci/test_doc_sections.py` fails on advice naming a doc that is gone or on a watched path no line routes — so both dead-entry cases are caught in CI rather than here.

If the script exits 1: review the listed files, decide whether each requires a doc update, and either commit the docs now or note them as deliberate skips. If the script exits 2 — or any code not named here, such as 127 when its path did not resolve — the doc check did not run: investigate the underlying error rather than proceeding. One exit-2 case is worth naming: when no entry in the list matches any tracked file, the script says so instead of passing, because a list that cannot hit anything would otherwise print the same clean green as a genuinely doc-neutral branch. Fix the list; do not wave the step through. The same goes for anything the project committed under `.skills/` that the script cannot use, the directory included: a tailoring never silently reverts to the built-in defaults, so an exit 2 there means the override is unusable, not absent.

### Step 2 — Ensure a clean working tree

```bash
bash "<check-status.sh>"
```

If the script exits 2, `git status` itself failed: the tree state is **unknown**, which is not the same as clean. Any code but 0 or 1 is no verdict either (127: the script was not found). Investigate the error rather than proceeding ([#257](https://github.com/gregoryfoster/skills/issues/257)).

If uncommitted changes exist, commit them following the project convention. notifier's commit format:

```
#<number> [type]: <description>       # with GH issue
[type]: <description>                 # without GH issue
```

Common `[type]` values: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.

Multiple issues: `#19, #20 [type]: <description>`

### Step 2.5 — Worktree-aware merge (if applicable)

If this checkout is a worktree (test: `git rev-parse --show-toplevel` differs from the main checkout, listed first in `git worktree list`):

1. Commit current changes inside the worktree (Step 2 above)
2. Invoke `using-git-worktrees` Phase 4 to merge the branch back into the main checkout before continuing
3. The remaining steps (push, GH comments, close) run from the main checkout

If this is a single (non-worktree) checkout, skip this step.

### Step 3 — Ensure on main

If Step 2.5 applied, the merge already happened — you're on `main` in the main checkout; continue.
If Step 2.5 did not apply (single checkout) and you're on a feature branch, merge to `main` first.

### Step 4 — Push

```bash
bash "<push.sh>"
```

Confirm push succeeded before proceeding.

### Step 5 — Comment on GitHub issues

For each issue in scope:

```bash
bash "<comment-issue.sh>" <number> "<summary>"
```

Comment must include:
- What was implemented (2–4 bullets)
- Key commit SHAs or commit range
- Any follow-up items or known limitations

### Step 6 — Close GitHub issues

<HARD-GATE>
Before closing any issue, verify the original requirements against what was implemented:
1. Re-read the issue body
2. Confirm each stated requirement is addressed in commits
3. If any requirement is missing: do NOT close — ask the user whether to descope or continue
</HARD-GATE>

```bash
bash "<close-issue.sh>" <number>
```

### Step 7 — Report

Present a summary table:

| Issue | Title | Status | Comment |
|---|---|---|---|
| #19 | ... | ✅ Closed | Summary posted |

### Step 8 — Next-steps notification

After the summary table, review commits and changes shipped to identify any post-deploy work the user may need to perform. Common categories for Python/FastAPI:

| Category | Trigger | Example action |
|---|---|---|
| DB migration (alembic) | `alembic/versions/` changed | `uv run alembic upgrade head`, then the same against `DEV_DATABASE_URL`, then `sudo systemctl restart notifier notifier-dev` |
| Service restart | Code change (no auto-reload in prod) | `sudo systemctl restart notifier notifier-dev` — both units serve one working tree |
| Integration tests | New `@pytest.mark.integration` tests | `uv run pytest -m integration` on a real env |
| Env var / secret | New config key | Add to `/etc/notifier/.env` and restart |
| Dev-server cleanup | Worktree shutdown | `fuser -k 9001/tcp` |

Present only the items that apply. Be specific — name the file, command, or path. Then **offer to execute** any item within your capabilities. Ask once — don't nag.

If nothing applies, omit this step entirely.

## Notes

- If `gh` CLI hits errors (e.g., Projects API changes), use `--json` flag workarounds as needed
- The project's AGENTS.md is authoritative for commit conventions — read it before committing
- `pre-ship.sh` auto-derives its per-SHA stamp prefix from `$(basename "$(git rev-parse --show-toplevel)")` — resolves to `notifier-tests-clean-<sha>` automatically
- notifier's `scripts/pre-ship.sh` is a thin wrapper: it sources `/etc/notifier/.env` then
  `$PROJECT_ROOT/.env` with `set -a; source` — never `export $(cat | xargs)`, which mangles any value
  holding a space or quote — and `exec`s the vendor copy. So the gate's own behaviour is upstream's by
  delegation: the gate deselects `integration` on top of this repo's own `addopts` expression rather
  than replacing it (#304), with no tailoring needed here. `.skills/pre-ship-uv-args` is a separate
  half of #304 — extra arguments for every `uv run` in the gate — and notifier commits no such file
  because it declares only a `dev` group, which `uv run` installs without being asked.
- This is a **local override**, re-synced from vendor `2e90414` (v1.5). `scripts/pre-ship.sh`
  and this `SKILL.md` are the only real files; the other five scripts are per-script symlinks into
  `skills-vendor/`, so they track upstream automatically. `SKILL.md` cannot be symlinked — it carries
  the notifier deltas — so it is the one file that drifts. It has drifted four times: v1.2 against
  vendor v1.4 (Step 1's script-resolution loop, so Step 1 failed); a Step 1.5 paragraph describing a
  `SENSITIVE_PATHS` array after upstream had moved to segment matching and `.skills/doc-sensitive-paths`
  (#47); then five un-bumped upstream edits at an unchanged v1.4, `.skills/doc-sections` among them (#69);
  then v1.4 against vendor v1.5, holding open the single-resolution Step 1 block after upstream had
  split it per script (#80, #81). The last two are the ones the tooling can see: since
  gregoryfoster/skills#286 `.skills/doctor.sh`
  diffs the `synced-from:` commit above against the vendor's HEAD for versioned vendors too, so a
  change at an unchanged `version:` reports. **Re-diff this file against vendor whenever the submodule
  moves** — `skills-vendor/` is in the path list above, so Step 1.5 says when that is, and it says so
  on the branch that moves the pointer, which is the earlier of the two signals. **Bump both stamps on
  every re-sync** — a `synced-from:` left behind re-reports drift already paid down.
  Upstream's self-budget note is dropped here: the gate it cites
  (`tests/structural/test_skill_self_budget.py`) lives in the vendor repo, not this one
