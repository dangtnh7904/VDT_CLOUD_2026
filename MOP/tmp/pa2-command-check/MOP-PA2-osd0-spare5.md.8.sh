export POOL='DIEN_POOL_TU_rule-scope.tsv'
test "$POOL" != 'DIEN_POOL_TU_rule-scope.tsv'
export OLD_RULE_NAME="$(ceph osd pool get "$POOL" crush_rule -f json \
  | jq -r '.crush_rule')"
ceph osd crush rule dump "$OLD_RULE_NAME" -f json \
  > "$EVIDENCE/rule-$POOL.before.json"
cat "$EVIDENCE/rule-$POOL.before.json"
