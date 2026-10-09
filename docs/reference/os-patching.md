# OS patching — this host's patch run (#113)

A monthly, owner-approved run under the vendored `patching-hosts` skill:
probe, recovery point, the apply in held steps, the reboot, post-boot checks.
Its procedure is the skill's `SKILL.md`; what only this host knows is the
knob, `.skills/patching-hosts`, held by `tests/deploy/test_patching_hosts_knob.py`:

- **Windows are UTC**, Tue and Wed 08:00–11:30, the hours the `dispatches`
  table shows near-silent. The `quiet` ranges are the callers' jobs whose
  `OnFailure=` handlers dispatch here: no caller retries for long, so an alert
  raised while the API is down is lost (#91).
- **A run outside the windows** adds a one-off `window` line to the working
  tree and removes it after; it is never committed.
- **The recovery point** lands in `/var/backups/patching-hosts-<UTC>/`, root
  only, with its retention date in the `recovery-point` file there. The
  owner copies each dump off the node with `ssh notifier.exe.xyz 'sudo cat
  <path>' > <file>` and attests its sha256 to the bulk step. The Fernet key
  never travels with it.
- **Tailscale is its own held step**, scoped by
  `deploy/apt-preferences.d/tailscale.pref`; its own auto-update stays off,
  on the node and for the tailnet.

Each run's record goes on its issue; the first is #113.
