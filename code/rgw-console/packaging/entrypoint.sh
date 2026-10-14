#!/bin/sh
set -eu

fail() {
  printf '%s\n' "storage-lab-console: $*" >&2
  exit 64
}

require_no_args() {
  [ "$#" -eq 0 ] || fail "role '$role' does not accept additional arguments"
}

load_executor_token() {
  token_file="${CEPH_EXECUTOR_TOKEN_FILE:-${RBD_EXECUTOR_TOKEN_FILE:-}}"
  canonical_token="${CEPH_EXECUTOR_TOKEN:-}"
  legacy_token="${RBD_EXECUTOR_TOKEN:-}"

  if [ -n "${CEPH_EXECUTOR_TOKEN_FILE:-}" ] && [ -n "${RBD_EXECUTOR_TOKEN_FILE:-}" ] \
    && [ "${CEPH_EXECUTOR_TOKEN_FILE}" != "${RBD_EXECUTOR_TOKEN_FILE}" ]; then
    fail "CEPH_EXECUTOR_TOKEN_FILE and RBD_EXECUTOR_TOKEN_FILE disagree"
  fi
  if [ -n "$canonical_token" ] && [ -n "$legacy_token" ] \
    && [ "$canonical_token" != "$legacy_token" ]; then
    fail "CEPH_EXECUTOR_TOKEN and RBD_EXECUTOR_TOKEN disagree"
  fi
  if { [ -n "$canonical_token" ] || [ -n "$legacy_token" ]; } && [ -n "$token_file" ]; then
    fail "set either an inline executor token or an executor token file, not both"
  fi
  if [ -n "$token_file" ]; then
    [ -f "$token_file" ] || fail "executor token file is not a regular file"
    [ -r "$token_file" ] || fail "executor token file is not readable"
    canonical_token="$(tr -d '\r\n' < "$token_file")"
    [ -n "$canonical_token" ] || fail "executor token file is empty"
  fi
  if [ -n "$canonical_token" ] || [ -n "$legacy_token" ]; then
    executor_token="${canonical_token:-$legacy_token}"
    CEPH_EXECUTOR_TOKEN="$executor_token"
    RBD_EXECUTOR_TOKEN="$executor_token"
    export CEPH_EXECUTOR_TOKEN RBD_EXECUTOR_TOKEN
  fi
}

role="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

# A read-only deployment must not start a legacy job consumer, even if old
# mutation jobs are still present in the database after an application upgrade.
case "${CONSOLE_READ_ONLY:-false}" in
  true|1|yes|on|TRUE|True)
    case "$role" in
      worker|rbd-lifecycle-worker) fail "role '$role' is disabled in read-only mode" ;;
    esac
    ;;
esac

case "$role" in
  api)
    require_no_args "$@"
    # The canonical backend settings consume CEPH_EXECUTOR_TOKEN_FILE, while a
    # legacy RBD route still reads RBD_EXECUTOR_TOKEN. Materialize the same
    # mounted secret for both paths until that compatibility route is removed.
    load_executor_token
    case "${PORT:-8000}" in
      *[!0-9]*|'') fail "PORT must be a decimal integer" ;;
    esac
    exec uvicorn app.main:app \
      --host "${BIND_HOST:-0.0.0.0}" \
      --port "${PORT:-8000}"
    ;;
  worker)
    exec python -m app.worker "$@"
    ;;
  performance-collector)
    exec python -m app.performance_collector "$@"
    ;;
  capacity-collector)
    load_executor_token
    exec python -m app.capacity_collector "$@"
    ;;
  rbd-lifecycle-worker)
    load_executor_token
    exec python -m app.rbd_lifecycle_worker "$@"
    ;;
  executor)
    require_no_args "$@"
    load_executor_token
    export PORT="${PORT:-3001}"
    exec node /opt/storage-lab-console/executor/src/server.js
    ;;
  migrate)
    exec python -m app.migrate "$@"
    ;;
  configure-database)
    require_no_args "$@"
    exec python -m app.platform.security.database_permissions
    ;;
  version)
    require_no_args "$@"
    exec python /opt/storage-lab-console/bin/version_info.py
    ;;
  *)
    fail "unsupported role '$role'; expected api, worker, performance-collector, capacity-collector, rbd-lifecycle-worker, executor, migrate, configure-database, or version"
    ;;
esac

