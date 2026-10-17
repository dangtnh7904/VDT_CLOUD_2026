ceph health detail > "$D/health.txt"
printf '%s\n' "$PG" >> "$EVIDENCE/pre.accepted.txt"
event DURING "PRE_HANDOFF:$PG:ACCEPTED"
