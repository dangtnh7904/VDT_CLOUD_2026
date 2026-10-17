curl --fail-with-body -sS -X POST "$API/api/jobs/$RGW_JOB/stop" \
  > "$EVIDENCE/bench/rgw-stop.json"
curl --fail-with-body -sS "$API/api/jobs" | jq --arg id "$RGW_JOB" \
  '.[] | select(.id==$id)' > "$EVIDENCE/bench/rgw-final-job.json"
