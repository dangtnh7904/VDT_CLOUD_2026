#!/usr/bin/env bash
# Timestamped current-state check. Run on ceph-master host with sudo.
# This checks MON quorum, cluster status, fresh CephX connections, and isolated
# RBD/S3 data probes for at least 30 minutes. It does not replace 01/10 evidence.
set -Eeuo pipefail
umask 077

if [[ $(id -u) -ne 0 ]]; then
  echo 'Run from the ceph-master HOST shell: sudo bash /home/dangg/mon_current_soak_20261002.sh' >&2
  exit 2
fi

expected_fsid='17c77e12-a16a-11f1-838e-cf68e9c001d8'
expected_names='["ceph-master","ceph-node2","ceph-node3"]'
conf='/etc/ceph/ceph.conf'
keyring='/etc/ceph/ceph.client.admin.keyring'
for file in "$conf" "$keyring"; do
  if [[ ! -r "$file" ]]; then
    echo "Required Ceph file is not readable: $file" >&2
    exit 2
  fi
done
for executable in ceph jq timeout mktemp python3 ps; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "Missing executable: $executable" >&2
    exit 2
  fi
done
client_script='/home/dangg/mon_current_clients_20261002.py'
if [[ ! -r "$client_script" ]]; then
  echo "Missing client probe: $client_script" >&2
  exit 2
fi
if ! python3 -c 'import sys; assert sys.version_info >= (3, 10); import boto3, botocore, rados, rbd' >/dev/null 2>&1; then
  echo 'Host Python needs version >=3.10 and boto3, botocore, rados, rbd' >&2
  exit 2
fi

c() {
  timeout --kill-after=5s 25s ceph --conf "$conf" --keyring "$keyring" \
    --name client.admin "$@"
}

actual_fsid=$(c fsid 2>/dev/null) || {
  echo 'Ceph CLI preflight failed; no soak was started.' >&2
  exit 3
}
if [[ "$actual_fsid" != "$expected_fsid" ]]; then
  echo "FSID mismatch: expected $expected_fsid, got $actual_fsid" >&2
  exit 3
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
out=$(mktemp -d "/home/dangg/mon-current-${stamp}-XXXXXX") || exit 3
case "$out" in
  /home/dangg/mon-current-*) ;;
  *) echo 'Unexpected output path' >&2; exit 3 ;;
esac
finish() {
  if [[ -n "${client_pid:-}" ]] && kill -0 "$client_pid" 2>/dev/null; then
    kill "$client_pid" 2>/dev/null || true
    for ((stop_wait=0; stop_wait<90; stop_wait++)); do
      state=$(ps -o stat= -p "$client_pid" 2>/dev/null || true)
      [[ -z "$state" || "$state" == Z* ]] && break
      sleep 1
    done
    state=$(ps -o stat= -p "$client_pid" 2>/dev/null || true)
    if [[ -n "$state" && "$state" != Z* ]]; then
      echo 'Client did not stop in 90s; cleanup needs manual review.' >&2
      kill -KILL "$client_pid" 2>/dev/null || true
    fi
    wait "$client_pid" 2>/dev/null || true
  fi
  chown -R dangg:dangg "$out" || true
}
trap finish EXIT
mkdir "$out/raw"
printf '%s\n' "$expected_fsid" > "$out/fsid.txt"
printf '%s\n' "$(hostname)" > "$out/host.txt"
printf '%s\n' "$(date -u +%FT%TZ)" > "$out/start-utc.txt"
printf '%s\n' 'Scope: current MON quorum, status, fresh CephX, isolated RBD and S3 data probes.' > "$out/scope.txt"
c --version > "$out/ceph-client-version.txt" 2> "$out/ceph-client-version.err" || true
c versions --format json > "$out/versions-before.json" 2> "$out/versions-before.err" || true
c orch ps --daemon_type mon --format json > "$out/mon-orch-before.json" 2> "$out/mon-orch-before.err" || true

python3 "$client_script" "$out" > "$out/client-run.log" 2>&1 &
client_pid=$!
for ((ready_wait=0; ready_wait<120; ready_wait++)); do
  if [[ -f "$out/client-ready.json" ]]; then
    break
  fi
  if [[ -f "$out/client-failed.json" ]] || ! kill -0 "$client_pid" 2>/dev/null; then
    echo "Client preflight failed; see $out/client-failed.json or client-run.log" >&2
    exit 4
  fi
  sleep 1
done
if [[ ! -f "$out/client-ready.json" ]]; then
  echo 'Client preflight did not finish within 120 seconds' >&2
  exit 4
fi

start_epoch=$(date -u +%s)
deadline=$((start_epoch + 1860))
sample=0
echo "Started MON and isolated client soak: $out"
while :; do
  at=$(date -u +%FT%TZ)
  sample_id=$(date -u +%Y%m%dT%H%M%S.%NZ)
  raw="$out/raw/$sample_id"
  quorum_rc=0
  status_rc=0
  c quorum_status --format json > "$raw.quorum.json" 2> "$raw.quorum.err" || quorum_rc=$?
  c -s --format json > "$raw.status.json" 2> "$raw.status.err" || status_rc=$?
  end_at=$(date -u +%FT%TZ)

  quorum_count=$(jq -r '.quorum_names | if type == "array" then length else 0 end' "$raw.quorum.json" 2>/dev/null) || quorum_count=0
  quorum_names=$(jq -c '.quorum_names | if type == "array" then . else [] end' "$raw.quorum.json" 2>/dev/null) || quorum_names='[]'
  leader=$(jq -r '.quorum_leader_name // ""' "$raw.quorum.json" 2>/dev/null) || leader=''
  epoch=$(jq -r '.election_epoch // 0' "$raw.quorum.json" 2>/dev/null) || epoch=0
  health=$(jq -r '.health.status // .health.overall_status // "UNKNOWN"' "$raw.status.json" 2>/dev/null) || health='UNKNOWN'
  [[ "$quorum_count" =~ ^[0-9]+$ ]] || quorum_count=0
  [[ "$epoch" =~ ^[0-9]+$ ]] || epoch=0

  jq -nc --arg at "$at" --arg end_at "$end_at" --arg sample_id "$sample_id" \
    --arg leader "$leader" --arg health "$health" \
    --argjson quorum_rc "$quorum_rc" --argjson status_rc "$status_rc" \
    --argjson quorum_count "$quorum_count" --argjson election_epoch "$epoch" \
    --argjson quorum_names "$quorum_names" \
    '{at:$at,end_at:$end_at,sample_id:$sample_id,quorum_rc:$quorum_rc,
      status_rc:$status_rc,quorum_count:$quorum_count,quorum_names:$quorum_names,leader:$leader,
      election_epoch:$election_epoch,health:$health}' \
    >> "$out/timeline.jsonl"
  if (( quorum_rc != 0 || status_rc != 0 || quorum_count != 3 )) || \
     ! jq -e --argjson expected "$expected_names" '(.quorum_names | sort) == ($expected | sort) and (.quorum_leader_name as $leader | .quorum_names | index($leader) != null)' "$raw.quorum.json" >/dev/null 2>&1; then
    printf '%s sample=%s quorum_rc=%s status_rc=%s count=%s\n' \
      "$at" "$sample_id" "$quorum_rc" "$status_rc" "$quorum_count" >> "$out/findings.log"
  fi

  sample=$((sample + 1))
  if (( sample % 6 == 0 )); then
    echo "$end_at samples=$sample quorum=$quorum_count status=$status_rc health=$health"
  fi
  now=$(date -u +%s)
  if (( now >= deadline )); then
    break
  fi
  sleep 10
done

printf '%s\n' "$(date -u +%FT%TZ)" > "$out/end-utc.txt"
c versions --format json > "$out/versions-after.json" 2> "$out/versions-after.err" || true
c health detail --format json > "$out/health-after.json" 2> "$out/health-after.err" || true
c orch ps --daemon_type mon --format json > "$out/mon-orch-after.json" 2> "$out/mon-orch-after.err" || true
client_rc=0
wait "$client_pid" || client_rc=$?
client_pid=''
printf '%s\n' "$client_rc" > "$out/client-process.rc"
if [[ ! -f "$out/client-summary.json" ]]; then
  echo '{"workers":{},"verification":{}}' > "$out/client-summary.json"
fi
python3 - "$out" "$expected_names" <<'PY'
import datetime
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
expected = sorted(json.loads(sys.argv[2]))

def seconds(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

try:
    rows = [json.loads(line) for line in (out / 'timeline.jsonl').read_text().splitlines()]
    workers = json.loads((out / 'client-summary.json').read_text()).get('workers', {})
    streams = [workers.get(name, {}) for name in ('auth', 'rbd', 's3')]
    duration = seconds(rows[-1]['end_at']) - seconds(rows[0]['at']) if rows else 0
    gaps = [seconds(b['at']) - seconds(a['end_at']) for a, b in zip(rows, rows[1:])]
    sample_durations = [seconds(row['end_at']) - seconds(row['at']) for row in rows]
    if rows and all(item.get('first') and item.get('last') for item in streams):
        overlap = max(0, min([seconds(rows[-1]['end_at'])] +
                             [seconds(item['last']) for item in streams]) -
                      max([seconds(rows[0]['at'])] +
                          [seconds(item['first']) for item in streams]))
    else:
        overlap = 0
    quorum_failures = sum(
        row.get('quorum_rc') != 0 or row.get('quorum_count') != 3 or
        sorted(row.get('quorum_names', [])) != expected or
        row.get('leader') not in row.get('quorum_names', []) or
        row.get('election_epoch', 0) <= 0 for row in rows
    )
    status_failures = sum(row.get('status_rc') != 0 for row in rows)
    epochs = sorted({row.get('election_epoch') for row in rows})
    leaders = sorted({row.get('leader') for row in rows})
    health = sorted({row.get('health') for row in rows})
    summary = dict(samples=len(rows), first=rows[0]['at'] if rows else None,
                   last=rows[-1]['end_at'] if rows else None,
                   duration_seconds=duration, overlap_seconds=overlap,
                   max_sample_gap_seconds=max(gaps, default=0),
                   max_sample_duration_seconds=max(sample_durations, default=0),
                   clock_regressions=sum(gap < 0 for gap in gaps) +
                                     sum(item < 0 for item in sample_durations),
                   quorum_failures=quorum_failures,
                   status_failures=status_failures,
                   election_epochs=epochs, leaders=leaders, health_states=health)
    summary['mon_pass'] = (
        len(rows) >= 2 and duration >= 1800 and overlap >= 1800 and
        summary['clock_regressions'] == 0 and summary['max_sample_gap_seconds'] <= 30 and
        summary['max_sample_duration_seconds'] <= 30 and
        quorum_failures == 0 and status_failures == 0 and len(epochs) == 1 and
        len(leaders) == 1 and health == ['HEALTH_OK']
    )
except Exception as exc:
    summary = {'mon_pass': False, 'summary_error': type(exc).__name__}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
PY
echo "Completed MON and isolated client soak: $out"
cat "$out/summary.json"
echo "Client probe exit code: $client_rc"
if (( client_rc != 0 )) || ! jq -e '.mon_pass' "$out/summary.json" >/dev/null; then
  echo 'Current-state soak verdict: HOLD (see summary and per-sample evidence).' >&2
  exit 5
fi
echo 'Current-state soak verdict: PASS for this isolated observation only.'
