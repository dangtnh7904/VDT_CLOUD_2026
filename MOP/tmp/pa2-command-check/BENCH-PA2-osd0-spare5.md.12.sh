export S3_ENDPOINT='https://DIEN_ENDPOINT_RGW'
export AWS_PROFILE='DIEN_PROFILE_LAB'
export SENTINEL_KEY="pa2-sentinel/$RUN_ID/immutable.bin"
test "$S3_ENDPOINT" != 'https://DIEN_ENDPOINT_RGW'
test "$AWS_PROFILE" != 'DIEN_PROFILE_LAB'
dd if=/dev/urandom of="$EVIDENCE/bench/s3-sentinel.bin" \
  bs=1M count=4 status=none
sha256sum "$EVIDENCE/bench/s3-sentinel.bin" \
  > "$EVIDENCE/bench/s3-sentinel.before.sha256"
aws --endpoint-url "$S3_ENDPOINT" s3api put-object \
  --bucket "$BUCKET" --key "$SENTINEL_KEY" \
  --body "$EVIDENCE/bench/s3-sentinel.bin" \
  > "$EVIDENCE/bench/s3-sentinel.put.json"
