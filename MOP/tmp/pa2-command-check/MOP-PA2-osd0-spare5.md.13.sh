# Chot danh sach tu toan up/acting, sau khi tat autoscale va doi rule.
jq -r '(.pg_stats // .pg_map.pg_stats)[]
  | select((.up|index(0))!=null or (.acting|index(0))!=null)
  | .pgid' "$EVIDENCE/bind.pgs.json" \
  | sort -V > "$EVIDENCE/handoff.txt"
test -s "$EVIDENCE/handoff.txt"
wc -l "$EVIDENCE/handoff.txt"
: > "$EVIDENCE/pre.accepted.txt"
: > "$EVIDENCE/post.accepted.txt"
: > "$EVIDENCE/upmaps.intent.tsv"
sha256sum "$EVIDENCE"/bind.*.json "$EVIDENCE/plan.json" \
  "$EVIDENCE/handoff.txt" > "$EVIDENCE/bind.sha256"
