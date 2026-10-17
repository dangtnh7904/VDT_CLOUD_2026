DEADLINE=$((SECONDS + TIMEOUT))
READY=0
while (( SECONDS < DEADLINE )); do
  ceph pg map "$PG"
  ceph pg dump pgs -f json > "$EVIDENCE/after-$PG.pgs.json"
  if python3 "$HELPER" progress --pgs "$EVIDENCE/after-$PG.pgs.json" \
      --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
      --pending "$PG"; then
    READY=1; break
  else
    RC=$?
    test "$RC" = 3 || { echo 'HOLD: unexpected mapping/state'; exit 1; }
  fi
  ceph health detail
  sleep 5
done
test "$READY" = 1 || { echo 'HOLD: handoff timeout or invalid mapping'; exit 1; }
ceph osd dump -f json | jq --arg pg "$PG" \
  '.pg_upmap_items[]? | select(.pgid==$pg)'
ceph health detail
