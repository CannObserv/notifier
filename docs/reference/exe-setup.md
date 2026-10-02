# exe.dev's setup unit — a creation-time script that keeps coming back

Why `exe-setup.service` is disabled on this host and `/exe.dev/setup` is
left on disk at 0600 (#93, #99). Companion to
[DEPLOYMENT.md](../DEPLOYMENT.md).

## What it is

This VM's creation-time `--setup-script` lives at `/exe.dev/setup`, and
exe.dev's `exe-setup.service` runs it as `exedev`. The script holds an inline
Tailscale key (expired, per the operator) and still provisions things: the
Tailscale installer, `apt-get install` PostgreSQL 16, and
`systemctl enable --now postgresql`. It fails at line 3, writing a log
`exedev` can't create, so the unit's `ExecStartPost=` `rm` never runs.

**The platform delivers the script again at any boot that finds it missing.**
#93 shredded it on 2026-09-28, and it was back at the next boot, with an mtime
equal to that boot's start. exe.dev calls the re-delivery a bug (2026-10-01).

## The fix

From CannObserv/provisioner#4, applied 2026-10-01:

```bash
sudo systemctl disable exe-setup.service     # a delivered file no longer means a run
sudo systemctl reset-failed exe-setup.service
sudo chmod 600 /exe.dev/setup                # never print it
```

- **Don't shred it.** The platform leaves a present copy alone, mode included,
  but delivers a missing one at 0755, and with the unit disabled nothing would
  then remove it.
- **Don't run `systemctl preset` or `preset-all`.** The unit's preset is
  `enabled`.
- **A present file doesn't mean a run.** Read the journal, or
  `ConditionTimestamp`.
- **When exe.dev ships a fix, re-check this.** It may touch a disabled unit
  (CannObserv/provisioner#17).

`tests/deploy/test_exe_setup.py` checks it all on this host: the unit is
disabled, not failed and never started this boot, and the script is root-only.

## Verified across a reboot (2026-10-02)

In-guest `sudo systemctl reboot` at 04:07:11Z. `ssh exe.dev restart` is a hard
reset, so don't use it for this.

```bash
systemctl show exe-setup.service -p UnitFileState --value   # disabled
sudo journalctl -b -u exe-setup.service | grep -c Starting  # 0
sudo stat -c '%a %U:%G' /exe.dev/setup                      # 600 root:root
```

All three read as expected. The file kept its inode (524318) and its mtime
(2026-09-29 12:27:10), so the platform didn't touch it, and
`systemctl --failed` was empty.

## Long term

A VM on the cohort base image, which runs a setup script exactly once
(CannObserv/provisioner#16).
