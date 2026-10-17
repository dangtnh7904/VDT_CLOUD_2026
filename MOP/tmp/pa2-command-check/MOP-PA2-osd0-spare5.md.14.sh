export PG='DIEN_PG_TRONG_handoff.txt'
grep -Fxq "$PG" "$EVIDENCE/handoff.txt"
export STAGE=PRE_HANDOFF
export D="$EVIDENCE/scrub/$STAGE/$PG"
mkdir -p "$D"
ceph pg "$PG" query -f json > "$D/before.query.json"
ceph pg dump pgs -f json | jq -e --arg pg "$PG" \
  '(.pg_stats // .pg_map.pg_stats)[] | select(.pgid==$pg)' \
  > "$D/before.json"
date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$D/requested.txt"
event DURING "$STAGE:$PG:REQUEST"
ceph pg deep-scrub "$PG" | tee "$D/request.out.txt"
