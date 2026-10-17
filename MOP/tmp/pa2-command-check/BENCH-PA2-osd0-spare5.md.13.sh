export PHASE='AFTER_HANDOFF'
GET_ARGS=(--bucket "$BUCKET" --key "$SENTINEL_KEY")
VID="$(jq -r '.VersionId // empty' "$EVIDENCE/bench/s3-sentinel.put.json")"
if [[ -n "$VID" ]]; then GET_ARGS+=(--version-id "$VID"); fi
aws --endpoint-url "$S3_ENDPOINT" s3api get-object "${GET_ARGS[@]}" \
  "$EVIDENCE/bench/s3-sentinel.$PHASE.bin" \
  > "$EVIDENCE/bench/s3-sentinel.$PHASE.get.json"
sha256sum "$EVIDENCE/bench/s3-sentinel.$PHASE.bin" \
  > "$EVIDENCE/bench/s3-sentinel.$PHASE.sha256"
test "$(awk '{print $1}' "$EVIDENCE/bench/s3-sentinel.before.sha256")" = \
     "$(awk '{print $1}' "$EVIDENCE/bench/s3-sentinel.$PHASE.sha256")"
