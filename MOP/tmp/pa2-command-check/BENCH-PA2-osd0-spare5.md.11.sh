export PHASE='AFTER_HANDOFF'  # doi ten theo checkpoint
dd if="$BENCH_DIR/sentinel.bin" bs=1M iflag=direct status=none \
  | sha256sum > "$EVIDENCE/bench/rbd-sentinel.$PHASE.sha256"
test "$(awk '{print $1}' "$EVIDENCE/bench/rbd-sentinel.before.sha256")" = \
     "$(awk '{print $1}' "$EVIDENCE/bench/rbd-sentinel.$PHASE.sha256")"
