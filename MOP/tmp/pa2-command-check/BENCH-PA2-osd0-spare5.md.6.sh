mkdir -p "$EVIDENCE/bench/job-state"
while [[ ! -f "$EVIDENCE/bench/job-observer.stop" ]]; do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  RC=0
  curl --fail-with-body -sS --max-time 10 "$API/api/jobs" \
    > "$EVIDENCE/bench/job-state/$T.all.json" \
    2> "$EVIDENCE/bench/job-state/$T.stderr" || RC=$?
  if [[ "$RC" = 0 ]]; then
    jq -e --arg id "$RGW_JOB" '.[] | select(.id==$id)' \
      "$EVIDENCE/bench/job-state/$T.all.json" \
      > "$EVIDENCE/bench/job-state/$T.job.json" || RC=$?
  fi
  printf '%s\t%s\n' "$T" "$RC" \
    >> "$EVIDENCE/bench/job-state/observer.tsv"
  sleep 10
done
