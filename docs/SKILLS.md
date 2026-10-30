# Agent Skills

This project follows the [agentskills.io](https://agentskills.io) spec.

## Directory Layout

Two directories serve different discovery systems:

| Directory | Discovery system | Contents |
|---|---|---|
| `skills/` | agentskills.io | Symlinks → `skills-vendor/`; no committed override since #153 |
| `.claude/skills/` | Claude Code | Symlinks → `../../skills/<name>` |

Local overrides in `skills/` automatically shadow vendor skills in both systems. When adding a skill, always create both the `skills/<name>` entry and `.claude/skills/<name>` symlink.

## External Skill Repos (Git Submodules)

| Repo | Submodule path |
|---|---|
| [`gregoryfoster/skills`](https://github.com/gregoryfoster/skills) | `skills-vendor/gregoryfoster-skills/` |
| [`obra/superpowers`](https://github.com/obra/superpowers) | `skills-vendor/obra-superpowers/` |

Init after cloning: `git submodule update --init --recursive`

Submodule freshness auto-enforced by the `SessionStart` hook in `.claude/settings.json` (`.claude/hooks/skills-submodule-update.sh` → the vendored `managing-skills` script). Runs once per UTC day, on `main` only; stages just `skills-vendor/` and `.skills/doctor.sh`, and logs to `.git/skills-update.log`. Force-refresh: `git submodule update --remote --merge -- skills-vendor/`

That entry carries an explicit `"timeout": 120` — the hook's constant from [gregoryfoster/skills#259](https://github.com/gregoryfoster/skills/issues/259), one network round trip per vendored repo plus the `git push` that [gregoryfoster/skills#293](https://github.com/gregoryfoster/skills/issues/293) added. It was `60` until #71: the kill that budget produces lands *between* the commit and the push, leaving `main` ahead of `origin/main` on this VM alone, where nothing reachable through the GitHub API can see it. **Re-running `install-refresh.sh` will not repair a wrong value** — skills#259 made preserve beat prescribe, so a timeout already on the entry wins over `--timeout` and the run only reports the disagreement. Edit `.claude/settings.json` by hand; `tests/deploy/test_skills_refresh_hook.py` pins it.

A second `SessionStart` entry runs `bash .skills/doctor.sh` on every session and branch: it repairs with `--init --recursive` and never `--remote`, so fresh clones and new worktrees stay populated — and the write-guard symlink below keeps resolving — without moving the pointer. (The auto-refresh was paused 2026-08-06 → 2026-08-14 to hold `curating-context` at v1.2 as the wave-A control arm — #16; wave B resolved and the hold was lifted in #20. The pause predated per-submodule pin support: `submodule.<name>.update = none` can't express a pin because `--merge` overrides it, and the fix for [gregoryfoster/skills#100](https://github.com/gregoryfoster/skills/issues/100) — a pin file the hook honours — landed only with v1.9. A future hold is now one committed line in `.skills/skills-pin` (`<submodule-path> <commit-ish>`; `SKILLS_PIN_FILE` env override), which excludes that submodule from both the update and the auto-commit — not a de-registered hook.)

`.skills/doctor.sh` (a real file, not a symlink — it diagnoses broken vendor symlinks) is installed and re-synced by the refresh hook's `install-doctor.sh` step, and re-syncs itself on every run. Check the symlink chain by hand with `bash .skills/doctor.sh`.

`.skills/` also holds committed configuration the skills read: the `curating-context` budgets and
telemetry, and **both halves** of `doc-check.sh`'s Step 1.5 gate, each replacing its built-in
defaults wholesale rather than extending them — a default upstream adds later has to be added here
by hand.

`.skills/doc-sensitive-paths` (#47) is what the gate watches. Beyond the defaults it names
`scripts/`, `.github/workflows/`, `skills/`, `skills-vendor/` and `.skills/`: a submodule bump
reaches `git diff` as the single gitlink path `skills-vendor/<name>`, so without that entry the one
event that stales an override would flag nothing. `tests/ci/test_doc_sensitive_paths.py` fails on
any entry that matches no tracked file.

`.skills/doc-sections` (#65) is the advice printed on a hit — which docs to spot-check. Tailoring
one half and not the other is its own defect, and since
[gregoryfoster/skills#284](https://github.com/gregoryfoster/skills/issues/284) a hit says so,
naming the half still running the skill's defaults; this repo ran that way from #47 until #65, with
every hit advising a doc set written for a generic FastAPI layout. Upstream checks nothing about
the sections, because upstream's are prose. This repo's are not: each line opens `<doc path>: ` and
names the sensitive paths it routes, so `tests/ci/test_doc_sections.py` can fail on a doc that is
gone **and** on a watched path no line routes — which is what keeps a new entry in the path list
from arriving with no doc attached.

The semantic index skips vendored skill prose — see `.socraticodeignore`.

### Override drift

No override remains: `shipping-work-python-fastapi`, the last, became a whole-directory link in
#153. This section is the record of why, and the rules for the next one.

Overrides are the one thing the refresh machinery does not keep current: the daily hook only
moves the submodule pointer, which by definition never touches a forked file, and nothing is ever
auto-merged, because upstream text cannot be applied blindly over a fork. That drift used to be
**silent** — `.skills/doctor.sh` walks *symlinks* and deliberately skips override directories.
Since [gregoryfoster/skills#286](https://github.com/gregoryfoster/skills/issues/286) it is
reported: the doctor diffs each override's recorded `synced-from:` commit against the vendor's
HEAD — for a **versioned** vendor too, not only an unversioned one — and names the override's own
real files when they changed. It is not a diff of the override against the vendor, which would fire
forever on the deltas an override exists to carry; it compares the vendor with itself. Paying the
drift down is still manual and the direction matters: local deltas onto the newer upstream text,
never the reverse, then diff the pre-merge copy and account for every removed line
(`skills/managing-skills/references/local-overrides.md` § "Re-syncing a drifted override").

`shipping-work-python-fastapi` showed both the mitigation and the residue. Its five unchanged
scripts were **per-script symlinks** into `skills-vendor/`, so they tracked upstream for free — a
pattern thinner than `managing-skills`' documented "complete replacement" rule, and worth
preferring. But `SKILL.md` carried the local deltas and could not be symlinked, so it was the one
file that drifted. `shipping-work`'s sat at v1.2 while
vendor reached v1.4, missing the Step 1 script-resolution loop upstream added for
[gregoryfoster/skills#63](https://github.com/gregoryfoster/skills/issues/63); Step 1 failed
until it was re-synced. It drifted a second time without the version moving at all: vendor
rewrote Step 1.5 for [gregoryfoster/skills#252](https://github.com/gregoryfoster/skills/issues/252)
— segment matching, `.skills/doc-sensitive-paths`, exit 2 on a list that matches nothing — and
shipped it under the same `version: "1.4"`. The symlinked script updated on the ordinary submodule
refresh while the committed paragraph went on describing a `SENSITIVE_PATHS` array (#47). So the
trigger for re-diffing an override is the **submodule pointer moving**, not the vendor version
changing; the pin below records the commit for that reason. It drifted a third time the same way
and this is the one the tooling caught: five `SKILL.md` commits landed between `91db31b` and
`d04cebf` at an unchanged `version: "1.4"` — `.skills/doc-sections`, the idded `skill:required`
marker, and the rule that a committed-but-unusable `.skills/` override is exit 2 rather than a
silent fallback — reported by the #286 comparison and re-synced in #69. (The issue counted four;
a fifth landed before the pointer reached `d04cebf`.) `brainstorming`'s had fallen a full
restructure behind — 128 lines against vendor's 250, predating upstream's Spike/Bounded/Architectural
model.

`shipping-work`'s drifted a fourth time when the pointer moved to vendor v1.5 (#80, #81), and this one is the
clearest case for re-syncing promptly rather than letting the advisory scroll past: upstream had
split Step 1's single `SKILL_SCRIPTS` resolution into a per-script loop
([gregoryfoster/skills#301](https://github.com/gregoryfoster/skills/issues/301)), and the doctor
reported the override as *omitting* the `skill:required id=skill-scripts` fragment rather than
merely trailing it — a second signal the version pin alone cannot raise. The same bump moved
`brainstorming` to v6.4.1, whose rewritten `<HARD-GATE>` mandates `writing-plans` on the
architectural path; notifier's standing delta makes that plan a judgement call, so the gate was
re-synced with the delta reapplied onto the new text rather than the new text dropped. Both
re-syncs were 3-way merges against the previously pinned commit, which is what `synced-from:` is
for: without it there is no merge base and the choice degrades to diffing two divergent files.

`brainstorming` was the other override until #133, and the reason it stopped is the strongest case
against forking a fast-moving upstream: it was re-synced at v6.4.1 and again at v7.0.0, and was
behind again at v7.0.1 — 243 lines against vendor's 294, with two new sections — each time a
3-way merge of the same handful of deltas onto restructured text. Its deltas were preferences,
not changes to the skill's mechanics, so they moved to AGENTS.md (§ Skill preferences, below) and
`skills/brainstorming` became a whole-directory link. That also retired the last file symlinks
under `skills/` that ruff reads, and with them every `skills/` entry in `[tool.ruff]
extend-exclude` (#45, #124, #126). `tests/ci/test_skills.py` held the fork set to
`shipping-work-python-fastapi` alone, so a new fork was added on purpose.

`shipping-work-python-fastapi` followed in #153, after a fifth drift: `SKILL.md` and
`scripts/pre-ship.sh` changed upstream at an unchanged `version: "1.5"`. None of its deltas needed
a fork by then. The commit format and the Step 8 rows (both units, both databases,
`/etc/notifier/.env`, port 9001) are AGENTS.md § Conventions and § Server Lifecycle. Vendor
Step 2 defers to AGENTS.md by name, and Step 8's rows are examples with `<project>` placeholders
that AGENTS.md fills in. The Step 1.5 tailoring is `.skills/doc-sensitive-paths` and
`.skills/doc-sections`, which the vendor text already describes. The one functional delta, the env
wrapper, moved to a repo-root `scripts/pre-ship.sh`, which Step 1 resolves ahead of the skill's
own copy for that script alone ([gregoryfoster/skills#301](https://github.com/gregoryfoster/skills/issues/301)).
It is upstream's "Project-local env loading" recipe, which parses the env files instead of sourcing
them, falls back to the primary checkout's `.env` from a linked worktree, and exports
`PRE_SHIP_ENV_NAMES` so the gate's stamp is keyed on the env it ran with. It carries one extra
guard, for a key with a leading digit, which the recipe's filter lets through to a fatal `export`.
`OVERRIDES` is now empty.

**One caveat on the per-script symlink pattern**, for the next override that uses it. `doctor.sh` globs `"$dir"/*` exactly one level deep under
`skills` and `.claude/hooks`, so symlinks nested inside an override directory sit below its scan
depth and are never checked. A fresh clone is still covered — `scan_uninit()` catches an
uninitialized submodule by a separate path — but if upstream *renames or deletes* a script, the
dangling symlink is invisible and surfaces only as `No such file or directory` mid-run. Raised
upstream alongside the pattern in
[gregoryfoster/skills#238](https://github.com/gregoryfoster/skills/issues/238).

To re-sync one: diff its `SKILL.md` against the vendor copy, reapply the local deltas
onto the newer upstream text (not the reverse), and update the pin in the table below.

**What the pin means.** Every override carries `synced-from:` — the submodule commit its `SKILL.md`
was last reconciled against — because that is the only pin that answers *is this current?*. Vendor
shipped the whole #252 rewrite under an unchanged `version: "1.4"`, so a version pin cannot tell a
synced override from a stale one, and `git log` in the submodule can: anything after the recorded
commit that touches the skill's directory is unreviewed here. Keep `metadata.version` alongside it as
the human-readable vendor version this file was last synced from — not a version of the local file,
so bump it on every re-sync even when the local deltas are unchanged. Where upstream ships no
`version:` (obra-superpowers), `synced-from:` carries the submodule tag and is the authoritative
pin; `version:` there is the one exception to the rule above — a local counter of re-syncs, not a
vendor version, carried because `doctor.sh` prints it ("last synced at version 1.1") and a stamp
that never moves reads as an override nobody has touched. Bump it too, and take the release tag
from `synced-from:` when you need to know what upstream text is in the file. No obra-superpowers
override remains since #133; the rule stands for the next one.

`init-socraticode` installs its own `SessionStart` entry: `.claude/hooks/socraticode-health.sh`, a symlink into the vendor tree wired by `managing-skills`' shared `install-hook.sh` (`--hook socraticode-health.sh --skill init-socraticode --marker socraticode-health --copy-fallback`; add `--check` to verify without writing). It reports and never repairs — a stopped container, a FAILED last index operation, a degraded graph yield, and since [gregoryfoster/skills#214](https://github.com/gregoryfoster/skills/issues/214) a context artifact declared in `.socraticodecontextartifacts.json` but never indexed, named in the finding. Silent when clean, at most one report per UTC day per project (`.git/socraticode-health.lock` / `.log`), exits 0 on every path. Since [gregoryfoster/skills#330](https://github.com/gregoryfoster/skills/issues/330) it caps its own launch: where `systemd-run` and a user manager that accounts memory exist — both do here — the driver and its server run in a transient `--user --scope` (`MemoryHigh=1200M MemoryMax=1536M CPUQuota=100%`) under `choom -n 500`, so on this 3.8 GiB no-swap host it is killed rather than allowed to starve the live service; a check the cap stopped is reported as such, never re-run uncapped. Observed capped here 2026-09-24 (`capped: scope socraticode-health-….scope` in the log). Override with `SOCRATICODE_HEALTH_CAP` (space-separated properties, or `off`) in `.claude/settings.local.json` — the cap lives in the hook, not the settings command, because an installer re-run rebuilds that command and keeps only the timeout. The entry carries an explicit `"timeout": 120`, the manifest's constant: the hook's own 60 s driver ceiling (`HEALTH_TIMEOUT_MS`) plus process start. The lock is stamped before the check, so a kill consumes the day's only attempt and reports nothing. The pinned server (#74) makes a cold `npx` download a fallback only; 120 covers it when it happens. `tests/deploy/test_socraticode_health_hook.py` pins the value (#75). Force a run with `SOCRATICODE_HEALTH_FORCE=1 bash .claude/hooks/socraticode-health.sh`.

Its sibling `.claude/hooks/socraticode-reminder.sh` — the `ToolSearch` prefetch line — is the same installer with `--marker socraticode-prefetch --marker socraticode-reminder`, and was a hand-typed copy until #21 symlinked it, so upstream edits to the prefetch query now arrive on the normal submodule refresh. **Both entries are hand-customized after install and the installer preserves only half of that:** it strips its marked entry and appends a canonical one at the end of the array, so the reminder entry's **first position** is lost on every re-run and has to be re-applied by hand. The `timeout` survives — since gregoryfoster/skills#259 a value already on the entry beats `--timeout`, as described above, which is why a wrong value has to be edited rather than re-installed. Neither hook resolves on a checkout with uninitialized submodules — both are vendor symlinks, so a fresh clone or new worktree fails them with rc=127 until `bash .skills/doctor.sh` has run once ([gregoryfoster/skills#228](https://github.com/gregoryfoster/skills/issues/228)).

`curating-context` installs a second hook: a `PostToolUse` write guard (`.claude/hooks/context-budget-guard.sh`) that warns when an edit pushes `AGENTS.md` past 6,000 tokens or a live reference doc past 10,000 (`.skills/context-budget`, `.skills/context-doc-budget`). It never blocks and stays silent when an edit reduces the count; it logs to `.git/context-budget.log`. Remove with `bash skills/curating-context/scripts/install-guard.sh --uninstall`. That path resolves through the vendor submodule, so on a checkout where submodules are uninitialized — a fresh clone, a new worktree, a shallow CI clone — it fails, and so does the guard itself. Run `bash .skills/doctor.sh` first: it is a real file for exactly this reason and heals the chain.

To add a new external skill repo: follow the `managing-skills` skill.

## Skill preferences

AGENTS.md § Agent Skills carries notifier's preferences as rules that beat any skill's own text,
in place of forking a `SKILL.md` to say them (#133). They are the deltas the `brainstorming`
override carried, and they apply to whatever skill reaches the same decision:

- **Trigger.** Vendor's `description` is "You MUST use this before any creative work", which
  fires on nearly every feature request. Ours was "brainstorm", "design this", "let's design", or
  a new feature with no prior design discussion; the AGENTS.md line keeps that scope. The harness
  still lists the skill under vendor's text — only the rule narrows it.
- **Spec path.** `docs/plans/`, which `writing-plans` also resolves to, rather than upstream's
  `docs/superpowers/specs/`. `[tool.ruff] extend-exclude` already skips it as dated snapshots.
- **`writing-plans` optional.** Upstream's `<HARD-GATE>` mandates a plan after every approved
  design. Here a design whose steps follow from it may go straight to implementation. When a plan
  is warranted it is gregoryfoster-skills' `writing-plans`; `superpowers:writing-plans` is not
  vendored, so the gate's literal instruction names a skill that does not exist here.
- **Worktrees.** Multi-step work lands on its own branch via `using-git-worktrees` once the design
  is approved.

Commit format and stack context needed no entry: § Conventions and § Environment & Tooling already
say them, and a skill defers to AGENTS.md.

## Skills Inventory

| Skill | Source | Notes |
|---|---|---|
| `brainstorming` | obra-superpowers symlink | An override until #133. Its preferences — trigger scope, `docs/plans/` spec path, `writing-plans` optional and gregoryfoster-skills', worktrees for multi-step work — live in AGENTS.md; see [§ Skill preferences](#skill-preferences) |
| `coordinating-epics` | gregoryfoster-skills symlink | Triggers: `coordinate the epic`, `burn down`, `check-in`, `I finished #N`, `next issue`. Serial, operator-paced; the coordinator thread writes no code — parallel agent teams go to `orchestrating-issue-backlog`. Needs an authenticated `gh` and python3 ≥3.9 |
| `curating-context` | gregoryfoster-skills symlink | Triggers: `curate context`, `context budget`, `trim AGENTS.md`. Tracks the vendored pointer; the wave-A hold at v1.2 was lifted 2026-08-14 (#20) |
| `dispatching-parallel-agents` | obra-superpowers symlink | |
| `enforcing-architecture` | gregoryfoster-skills symlink | Triggers: `add a fitness function`, `enforce this contract`, `lock this rule`. `reviewing-architecture` delegates here on a `fix + fitness` / `fitness` directive |
| `init-socraticode` | gregoryfoster-skills symlink | Installs/audits SocratiCode: preflight, policy, the prefetch + once-per-day health hooks, context-artifact manifest, index. Vendors the health hook this repo wires (#21) |
| `managing-skills` | gregoryfoster-skills symlink | |
| `orchestrating-issue-backlog` | gregoryfoster-skills symlink | |
| `patching-hosts` | gregoryfoster-skills symlink | Triggers: `patch the host`, `OS updates`, `apply updates`, `needrestart`. Reads the committed knob `.skills/patching-hosts` (#113); never edit the vendored copy, and file what it gets wrong upstream with the owner's approval |
| `reviewing-architecture` | gregoryfoster-skills symlink | |
| `reviewing-code-python-fastapi` | gregoryfoster-skills symlink | |
| `shipping-work-python-fastapi` | gregoryfoster-skills symlink | An override until #153. Step 1 runs repo-root `scripts/pre-ship.sh`, which loads `/etc/notifier/.env` and the `.env` (the primary checkout's, from a worktree) and execs the vendored gate; see [Override drift](#override-drift). Step 1.5 is tailored in both halves — `.skills/doc-sensitive-paths` (#47) and `.skills/doc-sections` (#65), guarded by `tests/ci/test_doc_sensitive_paths.py` and `tests/ci/test_doc_sections.py`. Units, databases and dev port come from AGENTS.md § Server Lifecycle |
| `subagent-driven-development` | obra-superpowers symlink | |
| `systematic-debugging` | obra-superpowers symlink | |
| `test-driven-development` | obra-superpowers symlink | |
| `using-git-worktrees` | gregoryfoster-skills symlink | |
| `using-mayfly-chat` | gregoryfoster-skills symlink | Triggers: `mayfly`, `open a channel`, `join the channel`, `chat with <repo>`, `agent chat`. Needs Node ≥18 (#89). **Never commit a channel URL** — upstream's structural test guards only its own tree, so `tests/ci/test_no_channel_urls.py` ports it here; still run the leak check in its `references/security.md` before committing session output, since CI catches a URL only after it is pushed |
| `verification-before-completion` | obra-superpowers symlink | |
| `writing-plans` | gregoryfoster-skills symlink | |
| `writing-skills` | obra-superpowers symlink | |
