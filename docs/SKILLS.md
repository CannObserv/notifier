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

The semantic index skips vendored skill prose — see `.socraticodeignore`.

`curating-context` installs a second hook: a `PostToolUse` write guard (`.claude/hooks/context-budget-guard.sh`) that warns when an edit pushes `AGENTS.md` past 6,000 tokens or a live reference doc past 10,000 (`.skills/context-budget`, `.skills/context-doc-budget`). It never blocks and stays silent when an edit reduces the count; it logs to `.git/context-budget.log`. Remove with `bash skills/curating-context/scripts/install-guard.sh --uninstall`. That path resolves through the vendor submodule, so on a checkout where submodules are uninitialized — a fresh clone, a new worktree, a shallow CI clone — it fails, and so does the guard itself. Run `bash .skills/doctor.sh` first: it is a real file for exactly this reason and heals the chain.

To add a new external skill repo: follow the `managing-skills` skill.

## Skills Inventory

| Skill | Source | Notes |
|---|---|---|
| `brainstorming` | Local override (obra-superpowers) | Project-specific conventions |
| `curating-context` | gregoryfoster-skills symlink | Triggers: `curate context`, `context budget`, `trim AGENTS.md`. Tracks the vendored pointer; the wave-A hold at v1.2 was lifted 2026-08-14 (#20) |
| `dispatching-parallel-agents` | obra-superpowers symlink | |
| `enforcing-architecture` | gregoryfoster-skills symlink | Triggers: `add a fitness function`, `enforce this contract`, `lock this rule`. `reviewing-architecture` delegates here on a `fix + fitness` / `fitness` directive |
| `managing-skills` | gregoryfoster-skills symlink | |
| `orchestrating-issue-backlog` | gregoryfoster-skills symlink | |
| `reviewing-architecture` | gregoryfoster-skills symlink | |
| `reviewing-code-python-fastapi` | gregoryfoster-skills symlink | |
| `shipping-work-python-fastapi` | Thin override (gregoryfoster-skills) | Loads `/etc/notifier/.env` before delegating |
| `subagent-driven-development` | obra-superpowers symlink | |
| `systematic-debugging` | obra-superpowers symlink | |
| `test-driven-development` | obra-superpowers symlink | |
| `using-git-worktrees` | gregoryfoster-skills symlink | |
| `verification-before-completion` | obra-superpowers symlink | |
| `writing-plans` | gregoryfoster-skills symlink | |
| `writing-skills` | obra-superpowers symlink | |
