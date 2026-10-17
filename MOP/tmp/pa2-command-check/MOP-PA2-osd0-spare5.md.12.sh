ceph pg dump pgs -f json > "$EVIDENCE/bind.pgs.json"
ceph osd dump -f json > "$EVIDENCE/bind.osd.json"
ceph osd crush dump -f json > "$EVIDENCE/bind.crush.json"
python3 "$HELPER" plan \
  --pgs "$EVIDENCE/bind.pgs.json" \
  --osdmap "$EVIDENCE/bind.osd.json" \
  --crush "$EVIDENCE/bind.crush.json" \
  --allow-host-colocation --out "$EVIDENCE/plan.json"
