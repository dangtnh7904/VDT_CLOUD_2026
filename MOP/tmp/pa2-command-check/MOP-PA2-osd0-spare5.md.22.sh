# Chi sau POST scrub va QoS gate da dat.
printf '%s\n' "$PG" >> "$EVIDENCE/post.accepted.txt"
event DURING "POST_HANDOFF:$PG:ACCEPTED"
