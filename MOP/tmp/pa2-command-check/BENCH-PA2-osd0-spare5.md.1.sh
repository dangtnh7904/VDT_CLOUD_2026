mkdir -p "$EVIDENCE/bench" "$EVIDENCE/collector"
event() {
  jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg phase "$1" --arg step "$2" \
    '{ts:$ts,phase:$phase,step:$step}' >> "$EVIDENCE/events.jsonl"
}
export -f event
date -u +%FT%TZ > "$EVIDENCE/bench/admin-clock.txt"
ceph --version > "$EVIDENCE/bench/ceph-cli.version.txt"
ceph versions -f json > "$EVIDENCE/bench/daemon-versions.before.json"
event PREPARE BEGIN
