event DURING SOURCE_UPGRADE_BEGIN
ceph pg dump pgs -f json > "$EVIDENCE/upgrade-ready.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/upgrade-ready.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/upgrade-ready.pgs.json" --osd 0
ceph osd ok-to-stop 0
ceph orch upgrade status
ceph osd find 0
ceph osd metadata 0 -f json > "$EVIDENCE/0-before.metadata.json"
ceph orch ps --daemon_type osd --daemon_id 0 \
  --format json --refresh > "$EVIDENCE/0-before.daemon.json"
