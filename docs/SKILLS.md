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

`.skills/doctor.sh` (a real file, not a symlink — it diagnoses broken vendor symlinks) is installed and re-synced by that hook, and re-syncs itself on every run. Check the symlink chain by hand with `bash .skills/doctor.sh`.

The semantic index skips vendored skill prose — see `.socraticodeignore`.

To add a new external skill repo: follow the `managing-skills` skill.

## Available Skills

See the Skills Inventory table in [AGENTS.md](../AGENTS.md#skills-inventory) for the current list, sources, and override notes.
