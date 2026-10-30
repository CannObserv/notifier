#!/usr/bin/env bash
# pre-ship.sh — the ship gate's env-loading wrapper (#153).
#
# shipping-work-python-fastapi's Step 1 probes this repo's scripts/ first, so
# this file is what every ship runs. It loads /etc/notifier/.env, then the
# repo .env (the primary checkout's, from a linked worktree that has none),
# and execs the vendored gate through the skill symlink. It is upstream's
# "Project-local env loading" recipe, verbatim but for ETC_ENV and one guard:
# upstream's key filter lets a leading digit through, and `export 9K=v` then
# kills this wrapper under set -e before the gate runs. The reason for every
# other line is in the header of the gate it delegates to. Re-diff it against
# that recipe when the submodule moves.
#
# Parses the env files, never sources them — the gate must not execute a
# secrets file. scripts/load_env.sh lifts load_env() from here (#154), so keep
# its `load_env() {` and `}` lines at column 0. PRE_SHIP_ENV_NAMES (names,
# never values) keys the gate's per-SHA stamp; an empty list writes no stamp.
#
# Usage: bash scripts/pre-ship.sh [--help]
set -euo pipefail
PROJECT_ROOT=$(git rev-parse --show-toplevel); cd "$PROJECT_ROOT"
DELEGATE="skills/shipping-work-python-fastapi/scripts/pre-ship.sh"
[[ -f "$DELEGATE" ]] || {
  echo "ERROR: vendored gate missing at $DELEGATE" >&2
  echo "       fix: git submodule update --init --recursive" >&2
  exit 2
}
load_env() {                                  # parse, never source
  local line key val
  [ -r "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line#"${line%%[![:space:]]*}"}       # drop leading blanks
    case $line in ''|\#*) continue ;; esac       # blank or comment
    line=${line#export }                        # tolerate `export K=v`
    case $line in *=*) ;; *) continue ;; esac
    key=${line%%=*} val=${line#*=}
    key=${key%"${key##*[![:space:]]}"}
    case $key in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac  # [0-9]*: ours
    case $val in                                # strip matched quotes
      \"*\") val=${val#\"} val=${val%\"} ;;
      \'*\') val=${val#\'} val=${val%\'} ;;
    esac
    export "$key=$val"
    PRE_SHIP_ENV_NAMES="${PRE_SHIP_ENV_NAMES:+$PRE_SHIP_ENV_NAMES }$key"
  done < "$1"
}
export PRE_SHIP_ENV_NAMES=""                  # names only: the stamp's key
ETC_ENV="/etc/notifier/.env" LOCAL_ENV="$PROJECT_ROOT/.env"
ENV_FILE=$LOCAL_ENV                           # a linked worktree has none,
[ -r "$ENV_FILE" ] ||                         # so use the primary checkout's
  ENV_FILE="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.env"
[ -r "$ETC_ENV" ] || [ -r "$ENV_FILE" ] || {  # neither: say so, loudly
  [ "$ENV_FILE" = "$LOCAL_ENV" ] || LOCAL_ENV="$LOCAL_ENV or $ENV_FILE"
  echo "WARN: no env file at $ETC_ENV or $LOCAL_ENV;" >&2
  echo "      tests that need one will skip, and no stamp is written" >&2
}
for f in "$ETC_ENV" "$ENV_FILE"; do load_env "$f"; done  # paths fixed first
exec bash "$DELEGATE" "$@"
