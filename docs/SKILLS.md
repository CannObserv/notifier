# Agent Skills

This project follows the [agentskills.io](https://agentskills.io) spec.

## Directory Layout

Two directories serve different discovery systems:

| Directory | Discovery system | Contents |
|---|---|---|
| `skills/` | agentskills.io | Committed overrides + symlinks → `skills-vendor/` |
| `.claude/skills/` | Claude Code | Symlinks → `../../skills/<name>` |

Local overrides in `skills/` automatically shadow vendor skills in both systems. When adding a skill, always create both the `skills/<name>` entry and `.claude/skills/<name>` symlink.

## External Skill Repos (Git Submodules)

| Repo | Submodule path |
|---|---|
| [`gregoryfoster/skills`](https://github.com/gregoryfoster/skills) | `skills-vendor/gregoryfoster-skills/` |
| [`obra/superpowers`](https://github.com/obra/superpowers) | `skills-vendor/obra-superpowers/` |

Init after cloning: `git submodule update --init --recursive`

Submodule freshness auto-enforced by the `SessionStart` hook in `.claude/settings.json` (`.claude/hooks/skills-submodule-update.sh` → the vendored `managing-skills` script). Runs once per UTC day, on `main` only; stages just `skills-vendor/` and `.skills/doctor.sh`, and logs to `.git/skills-update.log`. Force-refresh: `git submodule update --remote --merge -- skills-vendor/`

A second `SessionStart` entry runs `bash .skills/doctor.sh` on every session and branch: it repairs with `--init --recursive` and never `--remote`, so fresh clones and new worktrees stay populated — and the write-guard symlink below keeps resolving — without moving the pointer. (The auto-refresh was paused 2026-08-06 → 2026-08-14 to hold `curating-context` at v1.2 as the wave-A control arm — #16; wave B resolved and the hold was lifted in #20. The pause predated per-submodule pin support: `submodule.<name>.update = none` can't express a pin because `--merge` overrides it, and the fix for [gregoryfoster/skills#100](https://github.com/gregoryfoster/skills/issues/100) — a pin file the hook honours — landed only with v1.9. A future hold is now one committed line in `.skills/skills-pin` (`<submodule-path> <commit-ish>`; `SKILLS_PIN_FILE` env override), which excludes that submodule from both the update and the auto-commit — not a de-registered hook.)

`.skills/doctor.sh` (a real file, not a symlink — it diagnoses broken vendor symlinks) is installed and re-synced by the refresh hook's `install-doctor.sh` step, and re-syncs itself on every run. Check the symlink chain by hand with `bash .skills/doctor.sh`.

`.skills/` also holds committed configuration the skills read: the `curating-context` budgets and
telemetry, and `.skills/doc-sensitive-paths`, which replaces `doc-check.sh`'s built-in path list for
this repo (#47). Replacing is wholesale, not additive — a default upstream adds later has to be added
there by hand — and `tests/ci/test_doc_sensitive_paths.py` fails on any entry that matches no tracked
file. Beyond the defaults it names `scripts/`, `.github/workflows/`, `skills/`, `skills-vendor/` and
`.skills/`: a submodule bump reaches `git diff` as the single gitlink path `skills-vendor/<name>`, so
without that entry the one event that stales an override would flag nothing.

The semantic index skips vendored skill prose — see `.socraticodeignore`.

### Override drift

Overrides are the one thing the refresh machinery does not keep current. `.skills/doctor.sh`
walks *symlinks* and deliberately skips override directories; the daily hook only moves the
submodule pointer, which by definition never touches a forked file. So an override falls
further behind on every vendor release, silently.

`shipping-work-python-fastapi` shows both the mitigation and the residue. Its five unchanged
scripts are **per-script symlinks** into `skills-vendor/`, so they track upstream for free — a
pattern thinner than `managing-skills`' documented "complete replacement" rule, and worth
preferring. `brainstorming` now follows it too. But `SKILL.md` carries the local deltas and
cannot be symlinked, so it is the one file that drifts. `shipping-work`'s sat at v1.2 while
vendor reached v1.4, missing the Step 1 script-resolution loop upstream added for
[gregoryfoster/skills#63](https://github.com/gregoryfoster/skills/issues/63); Step 1 failed
until it was re-synced. It drifted a second time without the version moving at all: vendor
rewrote Step 1.5 for [gregoryfoster/skills#252](https://github.com/gregoryfoster/skills/issues/252)
— segment matching, `.skills/doc-sensitive-paths`, exit 2 on a list that matches nothing — and
shipped it under the same `version: "1.4"`. The symlinked script updated on the ordinary submodule
refresh while the committed paragraph went on describing a `SENSITIVE_PATHS` array (#47). So the
trigger for re-diffing an override is the **submodule pointer moving**, not the vendor version
changing; the pin below records the commit for that reason. `brainstorming`'s had fallen a full
restructure behind — 128 lines against vendor's 250, predating upstream's Spike/Bounded/Architectural
model.

**One caveat on the symlink pattern.** `doctor.sh` globs `"$dir"/*` exactly one level deep under
`skills` and `.claude/hooks`, so symlinks nested inside an override directory sit below its scan
depth and are never checked. A fresh clone is still covered — `scan_uninit()` catches an
uninitialized submodule by a separate path — but if upstream *renames or deletes* a script, the
dangling symlink is invisible and surfaces only as `No such file or directory` mid-run. Raised
upstream alongside the pattern in
[gregoryfoster/skills#238](https://github.com/gregoryfoster/skills/issues/238).

To re-sync an override: diff its `SKILL.md` against the vendor copy, reapply the local deltas
onto the newer upstream text (not the reverse), and update the pin in the table below.

**What the pin means.** Every override carries `synced-from:` — the submodule commit its `SKILL.md`
was last reconciled against — because that is the only pin that answers *is this current?*. Vendor
shipped the whole #252 rewrite under an unchanged `version: "1.4"`, so a version pin cannot tell a
synced override from a stale one, and `git log` in the submodule can: anything after the recorded
commit that touches the skill's directory is unreviewed here. Keep `metadata.version` alongside it as
the human-readable vendor version this file was last synced from — not a version of the local file,
so bump it on every re-sync even when the local deltas are unchanged. Where upstream ships no
`version:` (obra-superpowers), `synced-from:` carries the submodule tag and stands alone.

`init-socraticode` installs its own `SessionStart` entry: `.claude/hooks/socraticode-health.sh`, a symlink into the vendor tree wired by `managing-skills`' shared `install-hook.sh` (`--hook socraticode-health.sh --skill init-socraticode --marker socraticode-health --copy-fallback`; add `--check` to verify without writing). It reports and never repairs — a stopped container, a FAILED last index operation, a degraded graph yield, and since [gregoryfoster/skills#214](https://github.com/gregoryfoster/skills/issues/214) a context artifact declared in `.socraticodecontextartifacts.json` but never indexed, named in the finding. Silent when clean, at most one report per UTC day per project (`.git/socraticode-health.lock` / `.log`), exits 0 on every path. The entry carries an explicit `"timeout": 90` — above the hook's own 60 s driver ceiling (`HEALTH_TIMEOUT_MS`), so a slow check is not killed mid-run. Force a run with `SOCRATICODE_HEALTH_FORCE=1 bash .claude/hooks/socraticode-health.sh`.

Its sibling `.claude/hooks/socraticode-reminder.sh` — the `ToolSearch` prefetch line — is the same installer with `--marker socraticode-prefetch --marker socraticode-reminder`, and was a hand-typed copy until #21 symlinked it, so upstream edits to the prefetch query now arrive on the normal submodule refresh. **Both entries are hand-customized after install and the installer does not preserve that:** it strips its marked entry and appends a canonical one at the end of the array, with no `timeout` key. After any re-run, re-add the health entry's `"timeout": 90`, and the reminder entry's `"timeout": 5` and first position. Neither hook resolves on a checkout with uninitialized submodules — both are vendor symlinks, so a fresh clone or new worktree fails them with rc=127 until `bash .skills/doctor.sh` has run once ([gregoryfoster/skills#228](https://github.com/gregoryfoster/skills/issues/228)).

`curating-context` installs a second hook: a `PostToolUse` write guard (`.claude/hooks/context-budget-guard.sh`) that warns when an edit pushes `AGENTS.md` past 6,000 tokens or a live reference doc past 10,000 (`.skills/context-budget`, `.skills/context-doc-budget`). It never blocks and stays silent when an edit reduces the count; it logs to `.git/context-budget.log`. Remove with `bash skills/curating-context/scripts/install-guard.sh --uninstall`. That path resolves through the vendor submodule, so on a checkout where submodules are uninitialized — a fresh clone, a new worktree, a shallow CI clone — it fails, and so does the guard itself. Run `bash .skills/doctor.sh` first: it is a real file for exactly this reason and heals the chain.

To add a new external skill repo: follow the `managing-skills` skill.

## Skills Inventory

| Skill | Source | Notes |
|---|---|---|
| `brainstorming` | Thin override (obra-superpowers), **synced from v6.3.0** | Project-specific conventions: `docs/plans/` spec path, notifier commit format, `writing-plans` optional rather than mandatory, `using-git-worktrees` for multi-step work. `SKILL.md` is the only real file; `visual-companion.md` and `scripts/` symlink into `skills-vendor/`. Upstream carries no `version:`, so the pin is the submodule tag in `synced-from:` |
| `curating-context` | gregoryfoster-skills symlink | Triggers: `curate context`, `context budget`, `trim AGENTS.md`. Tracks the vendored pointer; the wave-A hold at v1.2 was lifted 2026-08-14 (#20) |
| `dispatching-parallel-agents` | obra-superpowers symlink | |
| `enforcing-architecture` | gregoryfoster-skills symlink | Triggers: `add a fitness function`, `enforce this contract`, `lock this rule`. `reviewing-architecture` delegates here on a `fix + fitness` / `fitness` directive |
| `init-socraticode` | gregoryfoster-skills symlink | Installs/audits SocratiCode: preflight, policy, the prefetch + once-per-day health hooks, context-artifact manifest, index. Vendors the health hook this repo wires (#21) |
| `managing-skills` | gregoryfoster-skills symlink | |
| `orchestrating-issue-backlog` | gregoryfoster-skills symlink | |
| `reviewing-architecture` | gregoryfoster-skills symlink | |
| `reviewing-code-python-fastapi` | gregoryfoster-skills symlink | |
| `shipping-work-python-fastapi` | Thin override (gregoryfoster-skills), **synced from v1.4 (`91db31b`)** | Loads `/etc/notifier/.env` before delegating; names notifier's two units and dev port. Only `SKILL.md` and `scripts/pre-ship.sh` are real files; the other five scripts symlink into `skills-vendor/`. Step 1.5's path list is committed at `.skills/doc-sensitive-paths` (#47), guarded by `tests/ci/test_doc_sensitive_paths.py`; it flags `skills-vendor/`, so the pointer move that stales this file trips the gate. See [Override drift](#override-drift) — bump the recorded commit whenever you re-sync |
| `subagent-driven-development` | obra-superpowers symlink | |
| `systematic-debugging` | obra-superpowers symlink | |
| `test-driven-development` | obra-superpowers symlink | |
| `using-git-worktrees` | gregoryfoster-skills symlink | |
| `verification-before-completion` | obra-superpowers symlink | |
| `writing-plans` | gregoryfoster-skills symlink | |
| `writing-skills` | obra-superpowers symlink | |
