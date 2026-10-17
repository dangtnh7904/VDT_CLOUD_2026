event DURING AFTER_ITERATION_STABLE
event AFTER BEGIN
# Giu cung workload, dataset, runner va profile trong AFTER 600 giay.
# Ket thuc theo phu luc benchmark, sau do ghi:
event AFTER END
ceph -s > "$EVIDENCE/final.status.txt"
ceph health detail > "$EVIDENCE/final.health.txt"
ceph osd dump -f json > "$EVIDENCE/final.osd.json"
ceph pg dump pgs -f json > "$EVIDENCE/final.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/final.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/final.pgs.json" --osd 0
