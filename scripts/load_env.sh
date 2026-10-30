# Source this; do not execute it:  . scripts/load_env.sh
#
# Loads /etc/notifier/.env (production secrets) then the repo .env (dev/agent
# secrets), exporting every assignment. Both are optional, so a fresh clone
# works. From a linked worktree with no .env of its own it reads the primary
# checkout's, the only place a git-ignored .env lives.
#
# Parses the files, never sources them (#154): sourcing runs a secrets file as
# shell code. Plain KEY=value lines load, with an optional `export ` prefix and
# matched quotes, so values with spaces or quotes survive; a `$(...)` stays
# literal, and any other line is skipped. The parser is scripts/pre-ship.sh's
# load_env(), lifted in place, so the repo holds one copy of it and
# tests/ci/test_pre_ship.py holds that copy to the vendored recipe. Exporting
# still hands every value to every child, so keep out of these files what a
# shell does not need.
#
# Resolves the repo from this script's own location, so it works when
# sourced from a subdirectory such as clients/python.
#
# NOTE: this leaves DATABASE_URL pointing at PRODUCTION. That is the intended
# target for `alembic upgrade head` and for systemctl, and wrong for anything
# else — use scripts/dev_server.sh for a server, and pytest pins its own.
# Executing this instead of sourcing it exports into a subshell that exits
# immediately, leaving the caller with nothing and no error. Fail loudly.
# ${BASH_SOURCE[0]} equals $0 only when the script is executed, never sourced.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  echo "load_env.sh must be sourced, not executed:  . scripts/load_env.sh" >&2
  exit 1
fi

# Everything lives in locals, so the caller's shell keeps only the exports.
# The names are prefixed because the parser exports into this scope: an env
# file key named like a plain local would land there instead.
_notifier_load_env() {
  local _notifier_root=$1 _notifier_etc="/etc/notifier/.env" _notifier_file _notifier_git
  local PRE_SHIP_ENV_NAMES=""   # the parser appends here; the ship gate's, not ours
  eval "$(sed -n '/^load_env() [{]/,/^[}]/p' "$_notifier_root/scripts/pre-ship.sh" 2>/dev/null)"
  if ! declare -F load_env > /dev/null; then
    echo "load_env.sh: no load_env() in $_notifier_root/scripts/pre-ship.sh; nothing loaded" >&2
    return 1
  fi
  _notifier_file="$_notifier_root/.env"
  if [ ! -r "$_notifier_file" ] &&
    _notifier_git=$(git -C "$_notifier_root" rev-parse --path-format=absolute --git-common-dir 2> /dev/null); then
    _notifier_file="$(dirname "$_notifier_git")/.env"
  fi
  load_env "$_notifier_etc"
  load_env "$_notifier_file"
}
_notifier_load_env "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || {
  unset -f _notifier_load_env load_env
  return 1
}
unset -f _notifier_load_env load_env
