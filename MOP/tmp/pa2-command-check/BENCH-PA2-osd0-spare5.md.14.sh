export PHASE=BEFORE
export FROM="$(cat "$EVIDENCE/bench/before.start")"
export TO="$(cat "$EVIDENCE/bench/before.end")"
curl --fail-with-body -sS --get "$API/api/performance/history" \
  --data-urlencode source=application \
  --data-urlencode scope_type=cluster --data-urlencode scope=console \
  --data-urlencode step=10 --data-urlencode "from=$FROM" \
  --data-urlencode "to=$TO" \
  > "$EVIDENCE/bench/rgw-$PHASE.history.json"
