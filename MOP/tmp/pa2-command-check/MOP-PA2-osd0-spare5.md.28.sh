ceph pg dump pgs -f json > "$EVIDENCE/after-upgrade.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/after-upgrade.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/after-upgrade.pgs.json" --osd 0
ceph osd dump -f json > "$EVIDENCE/after-upgrade.osd.json"
ceph osd crush dump -f json > "$EVIDENCE/after-upgrade.crush.json"
ceph orch ps --daemon_type osd --format json --refresh \
  > "$EVIDENCE/after-upgrade.daemons.json"
ceph tell osd.0 version > "$EVIDENCE/0-after.version.txt"
ceph osd metadata 0 -f json > "$EVIDENCE/0-after.metadata.json"
ceph health detail > "$EVIDENCE/after-upgrade.health.txt"

# Chi go scoped flag ma phien nay da dat.
if [[ -f "$EVIDENCE/noout.owned.txt" ]] && \
   grep -Fxq 'osd.0' "$EVIDENCE/noout.owned.txt"; then
  ceph osd unset-group noout osd.0
fi
event DURING SPARE_ROTATED
