DEADLINE=$((SECONDS + TIMEOUT))
READY=0
while (( SECONDS < DEADLINE )); do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  ceph pg "$PG" query -f json > "$D/query-$T.json"
  ceph pg dump pgs -f json | jq -e --arg pg "$PG" \
    '(.pg_stats // .pg_map.pg_stats)[] | select(.pgid==$pg)' \
    > "$D/after.json"
  cp "$D/after.json" "$D/stat-$T.json"
  if jq -e '(.stat_sum.num_scrub_errors // 0)>0 or
      (.stat_sum.num_deep_scrub_errors // 0)>0 or
      (.stat_sum.num_shallow_scrub_errors // 0)>0 or
      (.state|test("inconsistent|unfound|incomplete"))' \
      "$D/after.json" > /dev/null; then
    echo 'HOLD: scrub/data error'; exit 1
  fi
  if python3 "$HELPER" scrub --before "$D/before.json" \
      --after "$D/after.json" --requested "$(cat "$D/requested.txt")"; then
    READY=1; break
  else
    RC=$?
    test "$RC" = 3 || { echo 'HOLD: invalid scrub evidence'; exit 1; }
  fi
  sleep 5
done
test "$READY" = 1 || { echo 'HOLD: scrub timeout or invalid evidence'; exit 1; }
