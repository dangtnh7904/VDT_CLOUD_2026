export PG='DIEN_PG_CANARY_HOAC_PG_KE'
grep -Fxq "$PG" "$EVIDENCE/handoff.txt"
grep -Fxq "$PG" "$EVIDENCE/pre.accepted.txt"
if grep -Fxq "$PG" "$EVIDENCE/post.accepted.txt"; then
  echo 'HOLD: PG da accepted'; exit 1
fi
ceph pg dump pgs -f json > "$EVIDENCE/before-$PG.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/before-$PG.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
ceph osd dump -f json > "$EVIDENCE/before-$PG.osd.json"
ceph pg map "$PG"
