sort -Vu "$EVIDENCE/post.accepted.txt" > "$EVIDENCE/post.sorted"
diff -u "$EVIDENCE/need.sorted" "$EVIDENCE/post.sorted"
ceph pg dump pgs -f json > "$EVIDENCE/handoff-complete.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/handoff-complete.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
python3 "$HELPER" isolate \
  --pgs "$EVIDENCE/handoff-complete.pgs.json" --osd 0
ceph osd dump -f json > "$EVIDENCE/handoff-complete.osd.json"
ceph -s
ceph health detail
ceph osd df tree
