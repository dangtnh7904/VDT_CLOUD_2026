# Benchmark kèm MOP PA2 osd 0 sang osd 5

**Ngày 11/10/2026 — NOT_RUN.** Phụ lục của [MOP chính](MOP-PA2-osd0-spare5.md). Đo tác động của đổi rule lab, hai lượt deep-scrub, handoff, nâng 0 và giữ rotated placement. Không có bước trả PG về 0.

Chạy RGW theo workload console đang có; nếu lab có RBD đã mount thì có thêm profile fio. Chọn `RGW`, `RBD`, hoặc `RGW+RBD` **trước BEFORE** và giữ nguyên suốt run. Không tạo benchmark giả khi dịch vụ chưa triển khai. Dùng cùng client/runner/version/dataset/profile giữa các phase.

## 1 Cửa sổ đo và ngưỡng lab

| Phase | Bắt đầu và kết thúc | Nội dung |
|---|---|---|
| PREPARE | Trước phép đo | Chuẩn bị asset, kiểm corpus/mount, warm-up |
| BEFORE | Workload đã ổn định, trước freeze/đổi rule/nâng S | 600 giây, chưa mutation của MOP |
| DURING RULE_SWITCH | Đổi failure domain host sang osd và chờ clean | Tính toàn movement của pool, không giấu trong baseline |
| DURING RULE_BASELINE_STABLE | Sau rule mới ổn định, trước affinity/PRE | Plateau bổ sung 300 giây để so riêng với handoff |
| DURING PRE_HANDOFF | PRE deep-scrub toàn set | Queue/start/completion và tác động workload |
| DURING HANDOFF và POST | Từng PG 0 → 5 rồi POST scrub mới | Recovery, tail latency, bytes, sai dữ liệu |
| DURING UPGRADE và ROTATE | Promote 5, redeploy 0, bàn giao và chờ stable | Downtime daemon/readiness và dịch vụ |
| AFTER ITERATION | Sau stable window cuối, cùng workload | 600 giây, sau đó mới dừng workload |

Weight-set/weight nhỏ của 5 đã chuẩn bị trước run: `SPARE_WEIGHTSET_PREPARE=OUT_OF_MEASUREMENT`. Nếu phải nâng 5 trong MOP, bước đó thuộc DURING. Đây là phép đo **một lượt**; không gán AFTER của lượt này thành AFTER toàn wave.

Profile khởi đầu để lab dễ chạy: RGW target 2 request/giây, concurrency 2; fio 4 KiB random read/write 70/30, depth 8, một job, file 512 MiB. Chốt trước khi chạy, không coi đây là SLO production.

**Stop policy đề xuất cho bài lab, ghi lại trước mutation:** bất kỳ checksum mismatch/unfound/inconsistent thì HOLD ngay; service error/timeout mới thì HOLD để điều tra; không có completion trong 30 giây trong khi runner còn phát tải thì HOLD. Sau BEFORE, ghi latency và throughput theo operation; với tải RGW mặc định, HOLD nếu p95 của GET/PUT/UPDATE trong cửa sổ 300 giây vượt 2 lần mốc BEFORE ở 2 cửa sổ đủ sample liên tiếp. Mỗi cửa sổ cần ít nhất 100 completion successful của operation; ít hơn thì `LOW_SAMPLE`, không tự PASS latency. p99 vẫn báo để mô tả, nhưng dưới 1.000 sample successful thì chưa dùng làm gate tail latency đáng tin cậy. Với fio, chốt gate theo fio baseline riêng, không dùng ngưỡng millisecond của RGW. Thiếu telemetry bắt buộc quá 30 giây là HOLD, không thay bằng số 0.

Các ngưỡng này có thể chỉnh **trước DURING** theo baseline lab. Nếu BEFORE có lỗi, cap throttle hoặc không ổn định thì sửa workload/môi trường rồi đo BEFORE lại. Không thay profile giữa run rồi so như điều kiện tương đương.

## 2 Timeline và collector Ceph

Dùng `EVIDENCE`, `RUN_ID` và FSID của MOP chính. Đồng bộ NTP trên client, máy quản trị, OSD host và server console/DB; lưu `date -u`/trạng thái đồng bộ. Nếu khác host, các thư mục evidence phải được gom sau run; không giả chúng tự dùng chung filesystem.

```bash
mkdir -p "$EVIDENCE/bench" "$EVIDENCE/collector"
event() {
  jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg phase "$1" --arg step "$2" \
    '{ts:$ts,phase:$phase,step:$step}' >> "$EVIDENCE/events.jsonl"
}
export -f event
date -u +%FT%TZ > "$EVIDENCE/bench/admin-clock.txt"
ceph --version > "$EVIDENCE/bench/ceph-cli.version.txt"
ceph versions -f json > "$EVIDENCE/bench/daemon-versions.before.json"
event PREPARE BEGIN
```

Trong terminal quản trị thứ hai, source đúng `run.env`, rồi chạy collector dưới. Nó chỉ đọc Ceph, chạy mỗi khoảng 10 giây cộng thời gian query; `manifest.tsv` ghi timestamp và exit code. `timeout`/file lỗi là gap. Không parse file lỗi thành 0. Kiểm observer không tạo tải đáng kể, giữ cùng interval suốt run.

```bash
# Terminal collector: EVIDENCE da tro dung run.
mkdir -p "$EVIDENCE/collector"
while [[ ! -f "$EVIDENCE/collector.stop" ]]; do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  for KIND in status osd_perf osd_df pg_stat; do
    case "$KIND" in
      status) CMD=(ceph -s -f json) ;;
      osd_perf) CMD=(ceph osd perf -f json) ;;
      osd_df) CMD=(ceph osd df -f json) ;;
      pg_stat) CMD=(ceph pg stat -f json) ;;
    esac
    RC=0
    timeout 15 "${CMD[@]}" \
      > "$EVIDENCE/collector/$T.$KIND.json" \
      2> "$EVIDENCE/collector/$T.$KIND.stderr" || RC=$?
    printf '%s\t%s\t%s\t%s\n' "$T" "$KIND" "$RC" \
      "$(date -u +%FT%TZ)" >> "$EVIDENCE/collector/manifest.tsv"
  done
  sleep 10
done
```

Trên host của 0 và host chung của 2/5, nếu có `sysstat`, ghi riêng disk/CPU/NIC. Chạy trong các terminal riêng, dừng Ctrl-C sau AFTER; lưu clock/hostname cùng log. Không `killall` collector hoặc workload khác.

```bash
hostname
date -u +%FT%TZ
iostat -x -t 5 > pa2-iostat.txt
# Terminal rieng khac:
sar -n DEV 5 > pa2-network.txt
```

`ceph osd perf` là chỉ số OSD, không phải p99 latency client. Nếu không có counter backfill tích lũy, có thể ước lượng bytes từ tích phân rate recovery theo timestamp; phải ghi `ESTIMATED` và coverage, không gọi đó là bytes đo chính xác. Không lấy tổng used-bytes tăng làm bytes handoff vì workload vẫn đang ghi.

## 3 RGW workload dùng console hiện có

Lệnh chạy trên máy truy cập backend console, có `curl` và `jq`. Nếu khác máy quản trị, tạo thư mục benchmark theo cùng RUN_ID rồi gom kết quả sau. `API` là backend thật; sửa địa chỉ nếu không ở localhost. Bucket phải được allowlist và corpus đã mount. API hiện không có endpoint khởi chạy Warp/fio; không dùng QoS observer API như runner.

```bash
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
```

Cap 512 MiB là logical live payload của job, **không phải raw storage**. Versioning/UPDATE có thể giữ old versions; ghi trạng thái versioning và theo dõi capacity thực. Điều chỉnh cap/corpus trước chạy cho vừa spare; không dùng capacity-fill tool để benchmark. Nếu cap/admission khiến worker đổi mix hoặc pause, ghi segment thay đổi và đánh giá comparability lại. Ghi hash/manifest corpus thực và source revision/container digest của backend/worker.

Chờ job running, có đủ object để GET/UPDATE không phải fallback sang PUT, rate/mix ổn định và cluster clean rồi mới mở BEFORE. GET của runner này đọc/count bytes, chưa checksum; mục 6 có sentinel riêng. Target 2 req/s là pacing cấu hình, **không phải offered rate đã đo**; báo achieved rate từ raw operations và giữ offered load là `UNMEASURED` nếu không có event phát request.

```bash
curl --fail-with-body -sS "$API/api/jobs" | jq --arg id "$RGW_JOB" \
  '.[] | select(.id==$id)'
curl --fail-with-body -sS --get "$API/api/performance/current" \
  --data-urlencode source=application \
  --data-urlencode scope_type=cluster --data-urlencode scope=console
```

Trong một terminal trên host truy cập API, theo dõi đúng job mỗi 10 giây qua toàn run; `last_error`, `paused_reason`, `failed_count` là evidence bổ sung. Preflight/admission/lease có thể lỗi trước khi tạo record operations, nên không kết luận không lỗi chỉ từ SQL `errors=0`.

```bash
mkdir -p "$EVIDENCE/bench/job-state"
while [[ ! -f "$EVIDENCE/bench/job-observer.stop" ]]; do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  RC=0
  curl --fail-with-body -sS --max-time 10 "$API/api/jobs" \
    > "$EVIDENCE/bench/job-state/$T.all.json" \
    2> "$EVIDENCE/bench/job-state/$T.stderr" || RC=$?
  if [[ "$RC" = 0 ]]; then
    jq -e --arg id "$RGW_JOB" '.[] | select(.id==$id)' \
      "$EVIDENCE/bench/job-state/$T.all.json" \
      > "$EVIDENCE/bench/job-state/$T.job.json" || RC=$?
  fi
  printf '%s\t%s\n' "$T" "$RC" \
    >> "$EVIDENCE/bench/job-state/observer.tsv"
  sleep 10
done
```

Application telemetry là toàn console. Giữ các workload khác cố định và ghi vào manifest; dùng raw job_id ở mục 7 khi muốn thống kê riêng job. Không dùng `/api/metrics` (tổng toàn lịch sử) làm p99 riêng một phase.

## 4 Fio trên RBD nếu RBD thuộc scope

Chạy trên client Linux có **volume RBD lab đã mount và đã xác minh**. File load và sentinel nằm trong thư mục mới thuộc run. Không đặt filename là OSD raw device, DB/WAL device hoặc image đang phục vụ ứng dụng thật. Giữ fio/librbd/kernel/cache settings không đổi giữa các phase.

```bash
export RBD_MOUNT='/DIEN_MOUNT_RBD_LAB'
test "$RBD_MOUNT" != '/DIEN_MOUNT_RBD_LAB'
mountpoint -q "$RBD_MOUNT"
findmnt -T "$RBD_MOUNT" | tee "$EVIDENCE/bench/rbd-mount.txt"
rbd device list --format json > "$EVIDENCE/bench/rbd-devices.json"
df -h "$RBD_MOUNT"
export BENCH_DIR="$RBD_MOUNT/pa2-$RUN_ID"
test ! -e "$BENCH_DIR"
mkdir -p "$BENCH_DIR"
fio --version > "$EVIDENCE/bench/fio.version.txt"
uname -a > "$EVIDENCE/bench/client-kernel.txt"

fio --name=seed --filename="$BENCH_DIR/load.bin" \
  --rw=write --bs=1M --size=512M --ioengine=libaio \
  --direct=1 --iodepth=4 --refill_buffers=1 --end_fsync=1 \
  --output-format=json --output="$EVIDENCE/bench/fio-seed.json"
dd if=/dev/urandom of="$BENCH_DIR/sentinel.bin" \
  bs=1M count=4 conv=fsync status=none
sha256sum "$BENCH_DIR/sentinel.bin" \
  > "$EVIDENCE/bench/rbd-sentinel.before.sha256"
```

Đối chiếu source mount với `rbd device list` trước khi seed; có mountpoint không tự chứng minh đó là RBD. Dung lượng 512 MiB cần tính thêm replica/headroom. Seed và tạo sentinel nằm ngoài cửa sổ đo, phải chờ recovery xong.

Chạy workload liên tục trong terminal fio riêng. `runtime=21600` là trần 6 giờ; nếu run vượt trần phải ghi gap/restart, không giả continuous. Chờ warm-up ít nhất 60 giây và ổn định rồi mới bắt đầu BEFORE.

```bash
fio --name=pa2-rbd --filename="$BENCH_DIR/load.bin" \
  --rw=randrw --rwmixread=70 --bs=4k --size=512M \
  --ioengine=libaio --direct=1 --iodepth=8 --numjobs=1 \
  --time_based=1 --runtime=21600 --ramp_time=60 \
  --group_reporting=1 --percentile_list=50:95:99 \
  --write_bw_log="$EVIDENCE/bench/fio" \
  --write_iops_log="$EVIDENCE/bench/fio" \
  --write_hist_log="$EVIDENCE/bench/fio" \
  --log_avg_msec=1000 --log_hist_msec=1000 --log_unix_epoch=1 \
  --output-format=json+ --output="$EVIDENCE/bench/fio-total.json"
```

Profile fio này là **closed-loop, depth cố định**: khi storage chậm, achieved IOPS giảm. Không gọi nó là fixed offered IOPS. Histogram là completion latency `clat`; không đánh đồng với latency do runner RGW ghi cho từng operation. File JSON cuối là tổng toàn run, không phải từng phase; chia log/histogram theo timestamp timeline, tính percentile từ histogram gộp đúng operation, không lấy trung bình p99. Nếu phiên bản fio không hỗ trợ option log, HOLD setup để chốt profile tương thích trước BEFORE [B1].

## 5 Chạy BEFORE và gắn mốc vào MOP

Sau warm-up và gate ổn định, ở terminal quản trị:

```bash
event BEFORE BEGIN
date -u +%FT%TZ > "$EVIDENCE/bench/before.start"
```

Giữ workload 600 giây, quan sát health, mix, throughput và lỗi. Không chạy mutation Ceph trong window này. Sau 600 giây:

```bash
date -u +%FT%TZ > "$EVIDENCE/bench/before.end"
event BEFORE END
ceph -s > "$EVIDENCE/bench/before.status.txt"
ceph pg dump pgs -f json > "$EVIDENCE/bench/before.pgs.json"
```

Thu raw/telemetry BEFORE ở mục 7, xác định mốc latency/throughput và xác nhận stop policy. Sau đó mới bắt đầu mục 4 của MOP chính. Workload không dừng ở ranh giới phase.

Trong DURING, MOP chính đã có `event` ở freeze, nâng S nếu cần, đổi rule, affinity, PRE, handoff, POST, promote, redeploy và rotate. Bổ sung event `HOLD`, `RESUME`, đổi profile, mất collector hoặc thay đổi workload nếu xảy ra. Gate chờ và thời gian pause vẫn thuộc tổng thời gian bài thử; báo riêng active time và elapsed time.

Sau `RULE_BASELINE_STABLE`, giữ plateau 300 giây trước affinity để có số đo phụ. Đây vẫn là DURING vì rule đã đổi. AFTER chỉ mở sau điều kiện stable cuối MOP; giữ 600 giây rồi mới dừng runner.

## 6 Checksum bổ sung không ghi đè dữ liệu benchmark

**RBD:** sentinel bất biến; load.bin vẫn được fio ghi. Check tại BEFORE, sau toàn handoff, sau nâng 0 và cuối AFTER; ghi event để nhận diện tải đọc bổ sung.

```bash
export PHASE='AFTER_HANDOFF'  # doi ten theo checkpoint
dd if="$BENCH_DIR/sentinel.bin" bs=1M iflag=direct status=none \
  | sha256sum > "$EVIDENCE/bench/rbd-sentinel.$PHASE.sha256"
test "$(awk '{print $1}' "$EVIDENCE/bench/rbd-sentinel.before.sha256")" = \
     "$(awk '{print $1}' "$EVIDENCE/bench/rbd-sentinel.$PHASE.sha256")"
```

**RGW:** nếu dùng AWS CLI đã cấu hình profile cho lab, tạo sentinel ở prefix riêng trước warm-up. Không ghi secret vào command log hoặc manifest. Bucket/prefix phải thuộc quyền lab, nằm ngoài tập object của CRUD worker. Giữ cùng object/version không bị UPDATE/lifecycle xóa.

```bash
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
```

Tại từng checkpoint, GET lại. Nếu PUT trả VersionId, truyền đúng version đó; không so ETag với SHA256:

```bash
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
```

Sentinel nên được chuẩn bị trước BEFORE. Nếu chỉ thêm sentinel giữa run thì ghi rõ checkpoint baseline mới; không gọi nó là dữ liệu đã có trước nâng.

Đọc qua S3/RBD thường qua primary, không tự chứng minh đã đọc bản vật lý trên 5. Ghi `SERVICE_ONLY` nếu chưa có object/range → PG proof. Deep-scrub toàn handoff set trước và sau vẫn bắt buộc. Một sentinel PASS không chứng minh toàn payload hoặc OSD 0 sau nâng đã phục vụ replica mới.

## 7 Thu số liệu RGW theo phase và raw job

### 7.1 Telemetry cửa sổ để quan sát

```bash
export PHASE=BEFORE
export FROM="$(cat "$EVIDENCE/bench/before.start")"
export TO="$(cat "$EVIDENCE/bench/before.end")"
curl --fail-with-body -sS --get "$API/api/performance/history" \
  --data-urlencode source=application \
  --data-urlencode scope_type=cluster --data-urlencode scope=console \
  --data-urlencode step=10 --data-urlencode "from=$FROM" \
  --data-urlencode "to=$TO" \
  > "$EVIDENCE/bench/rgw-$PHASE.history.json"
```

Kiểm `state`, `sample_kind`, số sample, freshness/gap; HTTP 200 không bảo đảm dữ liệu đủ. `step>=60` có thể dùng rollup p95/p99 trung bình trong implementation hiện tại; không dùng số đó làm percentile gộp phase. Ngay cả sample 10 giây cũng không được lấy trung bình p99 để tạo p99 toàn phase.

### 7.2 Export raw đúng job và tính percentile từ từng operation

Trên host chạy console Docker Compose, vào thư mục chứa compose của deployment thật. Bản dev dùng service `backend`; bản release có thể dùng `api`, phải xác nhận bằng `docker compose config --services` rồi thay tên trong command. Script dùng kết nối DB đã cấu hình bên trong container, không in DSN/secret. Nếu deployment không dùng compose này, chạy cùng đoạn Python trong môi trường backend tương đương. Export là read-only.

Đặt `RGW_JOB`, `FROM`, `TO`, `PHASE`, `EVIDENCE` đúng run trên host đó. Lấy FROM/TO từ timeline, không từ đồng hồ nhớ lại. Với AFTER, lấy event BEGIN/END của AFTER; các subphase DURING cũng dùng cặp event chính xác.

```bash
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
```

Thống kê riêng operation, lỗi và phân phối latency successful requests; giữ raw lỗi riêng. Timer GET gồm GET và đọc body; timer PUT của implementation không gồm mọi bước chọn payload, admission và HEAD preflight. Vì vậy đây là latency theo ranh giới timer của runner, không phải toàn chu trình logic phía client. Giới hạn `created_at` phân loại theo thời điểm ghi record kết quả vào DB, không phải request issue time; request qua ranh giới phase có thể nằm ở phase sau. Với phase ngắn cần xem log request bổ sung.

```bash
python3 - "$EVIDENCE/bench/rgw-$PHASE.raw.jsonl" "$FROM" "$TO" \
  > "$EVIDENCE/bench/rgw-$PHASE.summary.json" <<'PY'
import collections, datetime as dt, json, math, re, sys
path, begin, end = sys.argv[1:]
def stamp(value):
    m=re.fullmatch(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})'
                  r'(?:\.(\d{1,6}))?(Z|[+-]\d{2}:?\d{2})',value)
    if m is None: raise ValueError('Timestamp needs date/time and timezone')
    base,fraction,offset=m.groups()
    offset='+0000' if offset=='Z' else offset.replace(':','')
    value=base.replace(' ','T')+'.'+(fraction or '0').ljust(6,'0')+offset
    return dt.datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%f%z')
seconds=(stamp(end)-stamp(begin)).total_seconds()
assert seconds > 0
rows=[json.loads(line) for line in open(path) if line.strip()]
assert rows, 'INCONCLUSIVE: no raw operations'
groups=collections.defaultdict(list)
for row in rows: groups[row['kind']].append(row)
result={'window_seconds':seconds,'boundary':'DB_RESULT_TIMESTAMP',
        'offered_load':'UNMEASURED','operations':{}}
for kind, items in sorted(groups.items()):
    good=[r for r in items if r['success'] is True]
    lat=sorted(float(r['latency_ms']) for r in good)
    def pct(q):
        return lat[max(0,math.ceil(q*len(lat))-1)] if lat else None
    times=sorted([stamp(begin),stamp(end)]+
                 [stamp(r['created_at']) for r in items])
    result['operations'][kind]={
      'completed':len(items),'success':len(good),
      'errors':len(items)-len(good),'completed_rps':len(items)/seconds,
      'success_rps':len(good)/seconds,
      'payload_MiB_s':(sum(int(r['bytes_count']) for r in good)
          /seconds/1048576 if kind in ('PUT','UPDATE','GET') else None),
      'p50_success_ms':pct(.50),'p95_success_ms':pct(.95),
      'p99_success_ms':pct(.99),'percentile_method':'nearest_rank',
      'max_result_gap_s':max((b-a).total_seconds()
          for a,b in zip(times,times[1:])),
      'quality':'LOW_SAMPLE' if len(good)<1000 else 'DESCRIPTIVE'}
print(json.dumps(result,indent=2))
PY
```

`max_result_gap_s` là khoảng không có record completion của operation đó, chỉ là chỉ báo stall khi biết runner còn phát loại request đó; với LIST thưa thì gap tự nhiên có thể dài. Timeout phải phân loại từ trường `error`/client logs, không tự gọi mọi error là timeout. Script không tính thời gian vi phạm SLO; dùng raw timestamps chia cửa sổ 300 giây cho gate RGW trên và áp đúng policy đã chốt. Với quá ít sample, tăng window/repeats ở run sau, không làm đẹp p99 bằng averaging.

## 8 Kết thúc runner sau AFTER và bàn giao

Sau đủ AFTER 600 giây và đã ghi event END, dừng **đúng job của run**:

```bash
curl --fail-with-body -sS -X POST "$API/api/jobs/$RGW_JOB/stop" \
  > "$EVIDENCE/bench/rgw-stop.json"
curl --fail-with-body -sS "$API/api/jobs" | jq --arg id "$RGW_JOB" \
  '.[] | select(.id==$id)' > "$EVIDENCE/bench/rgw-final-job.json"
```

`stopping` chưa phải đã dừng; poll tới terminal state và lưu reason/counters. Nếu fio bật, Ctrl-C trong đúng terminal fio sau AFTER, chờ ghi JSON/log xong; ghi stop có chủ ý và kiểm errors/output. Không dừng toàn bộ process fio trên host.

```bash
touch "$EVIDENCE/collector.stop"
touch "$EVIDENCE/bench/job-observer.stop"
event END BENCH_STOPPED
ceph versions -f json > "$EVIDENCE/bench/daemon-versions.after.json"
```

Gom raw trên các host, lưu profile/version/digest/clock, timeline, plan và scrub evidence. Cleanup asset riêng thuộc run **sau** báo cáo; không xóa bucket/image hoặc corpus dùng chung. Giữ upmap/rule lab/weight-set theo MOP chính, cleanup benchmark không bao gồm cleanup placement.

## 9 Bảng kết quả điền sau chạy

| Phase và operation | N | Completed/s | MiB/s | p50/p95/p99 | Error/timeout | Gap và SLO | Kết quả |
|---|---:|---:|---:|---|---|---|---|
| BEFORE | — | — | — | — | — | — | NOT_RUN |
| RULE_SWITCH | — | — | — | — | — | — | NOT_RUN |
| RULE_BASELINE_STABLE | — | — | — | — | — | — | NOT_RUN |
| PRE_HANDOFF | — | — | — | — | — | — | NOT_RUN |
| HANDOFF từng PG | — | — | — | — | — | — | NOT_RUN |
| POST_HANDOFF từng PG | — | — | — | — | — | — | NOT_RUN |
| SOURCE_UPGRADE | — | — | — | — | — | — | NOT_RUN |
| AFTER_ITERATION | — | — | — | — | — | — | NOT_RUN |

Tách các hàng GET/PUT/UPDATE và fio read/write. Báo thêm số PG, handoff bytes hoặc ước lượng có nguồn, thời gian PRE/POST (gồm queue), recovery, redeploy/readiness, stable wait và tổng elapsed. Báo client IOPS khác disk IOPS.

So `DURING−BEFORE` cho tổng tác động bài bảo trì; so với `RULE_BASELINE_STABLE` để tham khảo tác động handoff khi rule đã đổi. `AFTER−BEFORE` là chênh lệch tổng hệ thống có thay rule/placement/binary, không là benchmark thuần phiên bản Ceph. Baseline bằng 0/missing thì không chia phần trăm. Một run ít sample chỉ kết luận mô tả lab, không ngoại suy cụm lớn hay HA.

**Verdict riêng:** operation PA2; pre/post scrub coverage; checksum service; QoS; HA ngoại lệ; `osd.0 replica_validation=NOT_EXERCISED`. Không có kết quả thật cho tới khi chạy và thu raw.

Nguồn: [protocol benchmark dự án](../benchmark/README.md), [schema và route RGW job](../code/rgw-console/backend/app/main.py), [RGW worker](../code/rgw-console/backend/app/worker.py), [performance API](../code/rgw-console/backend/app/api/performance.py). B1: [tài liệu fio về histogram, log và workload](https://fio.readthedocs.io/en/latest/fio_doc.html).
