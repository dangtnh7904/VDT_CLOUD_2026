sort -Vu "$EVIDENCE/handoff.txt" > "$EVIDENCE/need.sorted"
sort -Vu "$EVIDENCE/pre.accepted.txt" > "$EVIDENCE/pre.sorted"
diff -u "$EVIDENCE/need.sorted" "$EVIDENCE/pre.sorted"
ceph pg dump pgs -f json > "$EVIDENCE/pre-complete.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/pre-complete.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
ceph osd dump -f json > "$EVIDENCE/pre-complete.osd.json"
