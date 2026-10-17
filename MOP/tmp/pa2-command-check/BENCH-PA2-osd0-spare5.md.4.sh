export API='http://127.0.0.1:8000'
export BUCKET='rgw-lab-data'
export RGW_MAX_BYTES=536870912
export RGW_MAX_OBJECTS=1000
mkdir -p "$EVIDENCE/bench"
curl --fail-with-body -sS "$API/api/jobs" \
  > "$EVIDENCE/bench/jobs.before.json"

jq -n --arg bucket "$BUCKET" --arg run "$RUN_ID" \
  --argjson cap "$RGW_MAX_BYTES" --argjson objects "$RGW_MAX_OBJECTS" '{
  schema_version:2, job_type:"rgw_crud",
  client_id:("pa2-"+$run), bucket:$bucket, prefix:("pa2/"+$run),
  corpus_ids:["mixed"],
  requests_per_second:2, concurrency:2,
  duration_seconds:null, object_limit:null,
  operation_weights:{PUT:28,GET:28,HEAD:3,LIST:2,UPDATE:20,DELETE:19},
  max_live_objects:$objects, max_live_logical_bytes:$cap,
  delete_scope:"job_owned", auto_drain:false, version_policy:"detect"
}' > "$EVIDENCE/bench/rgw-profile.json"

curl --fail-with-body -sS -X POST "$API/api/jobs" \
  -H 'Content-Type: application/json' \
  --data-binary @"$EVIDENCE/bench/rgw-profile.json" \
  > "$EVIDENCE/bench/rgw-job.json"
export RGW_JOB="$(jq -er '.id' "$EVIDENCE/bench/rgw-job.json")"
printf '%s\n' "$RGW_JOB" > "$EVIDENCE/bench/rgw-job.id"
sha256sum "$EVIDENCE/bench/rgw-profile.json" \
  > "$EVIDENCE/bench/rgw-profile.sha256"
