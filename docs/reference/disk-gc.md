# Disk GC and headroom sensor — this host's adoption (#136)

Provisioner's canonical disk GC and headroom sensor, installed and updated
only through the vendored `maintaining-host-disk` skill, from the release its
`scripts/_pin.sh` names. Never edit the installed copy under
`/usr/local/lib/cannobserv/`: a change goes to the GC's owner
(CannObserv/provisioner#61) with the operator's approval. Its procedure is
the skill's `SKILL.md`; what only this host knows:

- **Config:** `/etc/cannobserv/disk-gc/disk-gc.conf`, root, mode `0644`. It's
  hand-managed on the host, like `/etc/notifier/.env`, so no repo file
  mirrors it.
- **Tiers:** the template's, with `docker` off (purged, #92) and
  `worktrees` off: implementers keep worktrees for days between review rounds.
- **`npx_spec_files`:** this repo's `.claude/settings.json`, so the GC keeps
  the `_npx` tree for the pinned `SOCRATICODE_SPEC`, which
  `tests/deploy/test_socraticode_pin.py` asserts is warm.
- **The lines are 80/75.**
  - The baseline after the GC's first run is about 66%, and a day's VS Code
    and Claude Code builds add about 5 points.
  - Paging at 80 leaves about 4G for PostgreSQL, which shares this root.
  - pytest's basetemp is negligible here, and
    `tests/ci/test_pytest_config.py` keeps it to one run.
- **Patch runs read `alert_at_percent` as a floor** (gregoryfoster/skills#390):
  `patching-hosts` refuses any step that would take `/` to the line.
- **The sensor checks in to co-status,** as the `co-notifier-disk-headroom`
  monitor, with the key in `checkin.key` (root, `0600`). Its alerts reach the
  operator through this host's own `/dispatch`. If a full root takes notifier
  down, co-status's external `notifier-reachable` check covers it.

The install record, the report-only run and the turning-on steps are on #136.

```bash
sudo /usr/bin/python3 -I /usr/local/lib/cannobserv/disk-gc/disk-gc gc   # report-only
sudo journalctl -u cannobserv-disk-gc -u cannobserv-disk-headroom
```
