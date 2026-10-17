# Chi chay neu osd.5 chua dung target; planned down set luc nay chi co 5.
event DURING SPARE_UPGRADE
ceph pg dump pgs -f json > "$EVIDENCE/S-before-upgrade.pgs.json"
python3 "$HELPER" isolate \
  --pgs "$EVIDENCE/S-before-upgrade.pgs.json" --osd 5
ceph osd ok-to-stop 5
ceph orch daemon redeploy osd.5 --image "$TARGET_IMAGE"
