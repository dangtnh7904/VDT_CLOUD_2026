date -u +%FT%TZ > "$EVIDENCE/bench/before.end"
event BEFORE END
ceph -s > "$EVIDENCE/bench/before.status.txt"
ceph pg dump pgs -f json > "$EVIDENCE/bench/before.pgs.json"
