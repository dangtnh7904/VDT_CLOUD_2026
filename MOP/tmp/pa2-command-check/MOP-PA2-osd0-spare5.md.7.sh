ceph pg dump pgs -f json > "$EVIDENCE/pre-rule.pgs.json"
jq -r '(.pg_stats // .pg_map.pg_stats)[]
  | select((.up|index(0))!=null or (.acting|index(0))!=null)
  | .pgid | split(".")[0]' "$EVIDENCE/pre-rule.pgs.json" \
  | sort -nu > "$EVIDENCE/pool-ids.txt"
ceph osd dump -f json > "$EVIDENCE/pre-rule.osd.json"
while read -r PID; do
  jq -r --argjson id "$PID" '.pools[] | select(.pool==$id)
    | [.pool,.pool_name,.crush_rule,.type,.size,.min_size] | @tsv' \
    "$EVIDENCE/pre-rule.osd.json"
done < "$EVIDENCE/pool-ids.txt" | tee "$EVIDENCE/rule-scope.tsv"
