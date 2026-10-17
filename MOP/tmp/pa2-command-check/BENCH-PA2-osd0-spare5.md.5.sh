curl --fail-with-body -sS "$API/api/jobs" | jq --arg id "$RGW_JOB" \
  '.[] | select(.id==$id)'
curl --fail-with-body -sS --get "$API/api/performance/current" \
  --data-urlencode source=application \
  --data-urlencode scope_type=cluster --data-urlencode scope=console
