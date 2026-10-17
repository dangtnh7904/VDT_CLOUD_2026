printf '%s\t%s\t0\t5\n' "$(date -u +%FT%TZ)" "$PG" \
  >> "$EVIDENCE/upmaps.intent.tsv"
event DURING "HANDOFF:$PG:BEGIN"
ceph osd pg-upmap-items "$PG" 0 5
