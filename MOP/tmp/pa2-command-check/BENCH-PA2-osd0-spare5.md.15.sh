docker compose exec -T backend python - "$RGW_JOB" "$FROM" "$TO" \
  > "$EVIDENCE/bench/rgw-$PHASE.raw.jsonl" <<'PY'
import json, sys
from app.db import connection
job, begin, end = sys.argv[1:]
with connection() as conn:
    rows = conn.execute('''
      SELECT created_at,kind,success,latency_ms,bytes_count,error
      FROM operations
      WHERE job_id=%s AND created_at >= %s::timestamptz
        AND created_at < %s::timestamptz
      ORDER BY created_at
    ''', (job,begin,end)).fetchall()
for row in rows:
    print(json.dumps(dict(row), default=str))
PY
