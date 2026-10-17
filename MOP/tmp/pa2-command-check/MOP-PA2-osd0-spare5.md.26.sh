# Chi chay neu scoped noout cua 0 chua ton tai.
ceph osd set-group noout osd.0
printf 'osd.0\n' > "$EVIDENCE/noout.owned.txt"

# Recheck ngay truoc redeploy; lenh chi dinh chinh xac osd.0.
ceph osd ok-to-stop 0
ceph orch daemon redeploy osd.0 --image "$TARGET_IMAGE"
