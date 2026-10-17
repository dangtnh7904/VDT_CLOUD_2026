# May quan tri: lay primary va host thuc.
PRIMARY="$(jq -er '.acting_primary' "$D/before.json")"
ceph osd find "$PRIMARY"
cat "$D/requested.txt"
# Tren host primary: dien FSID, PRIMARY va thoi diem request vua lay.
# journalctl output can duoc luu ve evidence cua PG nay.
sudo journalctl -u "ceph-${EXPECTED_FSID}@osd.${PRIMARY}.service" \
  --since 'DIEN_REQUEST_UTC' --no-pager > scrub-primary-journal.txt
