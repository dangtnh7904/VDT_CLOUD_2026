
## G4 — Monitoring và API

### G4.1 — Kết quả đã hoàn thành

Hiện tại đã xác nhận:

```text
MGR active        : Ceph 16.2.15
/metrics          : reachable
Prometheus target : UP
lastError         : ""
Fresh sample      : PASS
```

`timestamp(ceph_health_status)` đã tăng từ:

```text
1790822125.93
→
1790822145.93
```

chứng minh Prometheus vẫn ingest dữ liệu mới.

Đồng thời phát hiện:

```text
ceph_pool_objects_repaired

HELP = 11
TYPE = 11
```

`promtool 2.33.4` trả:

```text
error while linting:
text format parsing error in line 919:
second HELP line for metric name
"ceph_pool_objects_repaired"

RC=1
```

Do đó:

```text
Functional Prometheus path : PASS
Fresh metric ingestion     : PASS
Format compliance          : FAIL
Known compatibility issue  : OPEN
```

Lỗi duplicate hiện **chưa gây outage monitoring trong lab**, nhưng được giữ lại như một compatibility finding.

---

# G4.2 — Kiểm Rule/Alert

Mục tiêu của bước này là xác nhận sau khi MGR lên `16.2.15`:

- Prometheus load được rule.
- Rule engine vẫn evaluation.
- Alert API hoạt động.
- Không có lỗi rule/query rõ ràng liên quan việc nâng MGR.

### Lấy rule hiện tại

```bash
mkdir -p evidence-g4

curl -fsS \
  http://10.20.20.11:9095/api/v1/rules \
  > evidence-g4/rules.json
```

Kiểm trạng thái:

```bash
jq '{
  status: .status,
  group_count: (.data.groups | length)
}' evidence-g4/rules.json
```

Điều kiện mong muốn:

```text
status      = success
group_count > 0
```

### Xem từng rule group

```bash
jq '
.data.groups[] |
{
  name,
  file,
  interval,
  lastEvaluation,
  evaluationTime
}' evidence-g4/rules.json
```

Cần thấy:

```text
lastEvaluation có timestamp mới
evaluationTime có giá trị hợp lệ
```

---

### Kiểm rule nào đang lỗi

```bash
jq '
.data.groups[].rules[] |
select(.health != "ok") |
{
  name,
  health,
  lastError
}' evidence-g4/rules.json
```

Nếu không trả gì:

```text
RULE HEALTH = PASS
```

Nếu có:

```text
health != ok
lastError != ""
```

thì phải đọc lỗi trước khi đóng G4.

---

### Kiểm Alert API

```bash
curl -fsS \
  http://10.20.20.11:9095/api/v1/alerts \
  > evidence-g4/alerts.json
```

Kiểm:

```bash
jq '{
  status: .status,
  alert_count: (.data.alerts | length)
}' evidence-g4/alerts.json
```

Không bắt buộc phải có alert đang FIRING.

Ví dụ:

```text
status      = success
alert_count = 0
```

vẫn có thể PASS.

Mục tiêu là:

```text
Alert API hoạt động
Rule evaluation hoạt động
Không có rule parser/evaluation error
```

---

## G4.3 — Kiểm một query thực tế

Ngoài freshness, kiểm một metric Ceph thực:

```bash
curl -fsSG \
  http://10.20.20.11:9095/api/v1/query \
  --data-urlencode 'query=ceph_health_status' \
  > evidence-g4/query-health.json
```

Kiểm:

```bash
jq '{
  status: .status,
  result_count: (.data.result | length)
}' evidence-g4/query-health.json
```

Điều kiện:

```text
status       = success
result_count > 0
```

Điều này chứng minh:

```text
MGR exporter
    ↓
Prometheus scrape
    ↓
Prometheus storage
    ↓
PromQL query
```

đều đang hoạt động.

---

# G4.4 — Kiểm Dashboard

Đầu tiên xác định Dashboard endpoint hiện tại:

```bash
ceph mgr services -f json-pretty \
  | tee evidence-g4/mgr-services.json
```

Xem trường:

```text
dashboard
```

Sau đó kiểm HTTP/TLS.

Ví dụ active hiện là `ceph-master`:

```bash
curl -k -sS \
  --max-time 10 \
  -o evidence-g4/dashboard-body.html \
  -w 'HTTP=%{http_code}\n' \
  https://10.20.20.11:8443/
```

Kết quả hợp lý có thể là:

```text
HTTP=200
```

hoặc redirect/authentication response phù hợp tùy Dashboard configuration.

Kiểm body:

```bash
test -s evidence-g4/dashboard-body.html \
  && echo "DASHBOARD BODY: PASS"
```

Tuy nhiên HTTP response riêng lẻ chưa đủ để kết luận toàn bộ Dashboard hoạt động.

PRE-MOP yêu cầu nếu Dashboard nằm trong acceptance thì cần kiểm chức năng thật, đặc biệt vì target `16.2.15` có thay đổi liên quan TLS.

---

## G4.5 — Functional Dashboard/API test

Nếu Dashboard được sử dụng thực tế, thực hiện ít nhất:

```text
1. Mở Dashboard.
2. Login thành công.
3. Mở Cluster / Hosts / OSD hoặc trang đang sử dụng.
4. Dữ liệu hiện tại load được.
5. Không có backend/API error.
```

Nếu web hỗ trợ upgrade của hệ thống đang gọi API từ MGR/Dashboard, nên gọi lại **đúng API mà web đang dùng**.

Điều này có giá trị hơn chỉ:

```text
curl /
```

vì nó chứng minh:

```text
Frontend
   ↓
Dashboard/API
   ↓
MGR module
   ↓
Cluster data
```

đều hoạt động.

---

# G4.6 — Kiểm module MGR

Lưu module state:

```bash
ceph mgr module ls -f json-pretty \
  > evidence-g4/mgr-modules.json
```

Kiểm:

```bash
ceph mgr services
ceph orch status
```

Các module dùng trong bài lab cần phản hồi bình thường, đặc biệt:

```text
cephadm
dashboard
prometheus
```

Nếu có module custom thì phải kiểm chức năng thực tế của module đó.

PRE-MOP cũng lưu ý standby chạy được chưa chứng minh module active đã thực thi đúng; cần test sau khi target trở thành active.

---

# G4.7 — Kết luận G4

Sau khi chạy hết các bước trên, dùng bảng:

| Hạng mục | Kết quả |
|---|---|
| `/metrics` reachable | PASS |
| Metrics body | PASS |
| Prometheus target | PASS |
| `lastError=""` | PASS |
| Fresh sample | PASS |
| PromQL query | PASS / FAIL |
| Rule load | PASS / FAIL |
| Rule evaluation | PASS / FAIL |
| Alert API | PASS / FAIL |
| Dashboard access | PASS / FAIL |
| Dashboard functional/API | PASS / FAIL |
| MGR modules | PASS / FAIL |
| Prometheus format compliance | **FAIL — Known issue** |

Nếu tất cả phần functional đạt:

```text
G4 = PASS WITH KNOWN ISSUE
```

Known issue:

```text
G4-MON-01

ceph_pool_objects_repaired emits duplicate
HELP/TYPE metadata.

promtool 2.33.4 rejects the exposition format,
but current Prometheus target remains UP and
fresh Ceph metrics continue to be ingested.
```

---

# G6 — HA sau nâng cấp MGR

G6 chỉ thực hiện sau khi G4 functional test đã đạt.

## G6.1 — Baseline

```bash
mkdir -p evidence-g6

ACTIVE_BEFORE=$(ceph mgr dump -f json | jq -r '.active_name')
STANDBY_BEFORE=$(ceph mgr dump -f json | jq -r '.standbys[0].name')

echo "ACTIVE=$ACTIVE_BEFORE"
echo "STANDBY=$STANDBY_BEFORE"

ceph -s > evidence-g6/01-ceph-before.txt

ceph mgr dump -f json-pretty \
  > evidence-g6/02-mgr-before.json

ceph orch ps --daemon_type mgr --refresh \
  > evidence-g6/03-mgr-before.txt
```

Điều kiện:

```text
2 MGR = 16.2.15
1 active
1 standby
PG stable
MON quorum healthy
```

---

## G6.2 — Baseline monitoring

```bash
curl -fsS \
  http://10.20.20.11:9095/api/v1/targets \
  > evidence-g6/04-targets-before.json
```

Freshness:

```bash
curl -fsSG \
  http://10.20.20.11:9095/api/v1/query \
  --data-urlencode 'query=timestamp(ceph_health_status)' \
  > evidence-g6/05-freshness-before.json
```

---

## G6.3 — Bắt đầu workload probe

Trong lúc failover nên có ít nhất một probe:

```text
RGW PUT → GET → checksum
```

hoặc:

```text
RBD/RADOS write → read → verify
```

Mục tiêu:

```text
MGR failover không làm data path ngừng hoạt động.
```

---

## G6.4 — Fail active có kiểm soát

Kiểm lại:

```bash
ceph mgr dump
echo "$ACTIVE_BEFORE"
```

Sau đó:

```bash
ceph mgr fail "$ACTIVE_BEFORE"
```

Không chạy fail lần hai.

---

## G6.5 — Kiểm standby takeover

```bash
ACTIVE_AFTER=$(ceph mgr dump -f json | jq -r '.active_name')

echo "BEFORE=$ACTIVE_BEFORE"
echo "AFTER=$ACTIVE_AFTER"
```

Yêu cầu:

```text
ACTIVE_AFTER != ACTIVE_BEFORE
```

---

## G6.6 — Kiểm old active quay lại standby

```bash
ceph mgr dump -f json |
jq --arg old "$ACTIVE_BEFORE" '
  .standbys[] |
  select(.name==$old)
'
```

Kết quả cuối:

```text
new MGR = active 16.2.15
old MGR = standby 16.2.15
```

---

## G6.7 — Cluster health

```bash
ceph -s
ceph pg stat
ceph quorum_status
ceph crash ls-new
```

Yêu cầu:

```text
MON quorum stable
OSD stable
PG stable
không có MGR crash mới
```

---

## G6.8 — Cephadm/module

```bash
ceph orch status
ceph mgr module ls
ceph mgr services
```

Yêu cầu:

```text
orchestrator usable
cephadm usable
dashboard/prometheus module hoạt động
```

---

## G6.9 — Monitoring trên active mới

Lấy IP:

```bash
ACTIVE_IP_AFTER=$(
  ceph mgr metadata -f json |
  jq -r --arg a "$ACTIVE_AFTER" \
  '.[] | select(.name==$a) | .addr'
)
```

Metrics:

```bash
curl -fsS \
  "http://${ACTIVE_IP_AFTER}:9283/metrics" \
  -o evidence-g6/06-metrics-after.txt
```

---

## G6.10 — Kiểm duplicate known issue

```bash
grep -c '^# HELP ceph_pool_objects_repaired ' \
  evidence-g6/06-metrics-after.txt

grep -c '^# TYPE ceph_pool_objects_repaired ' \
  evidence-g6/06-metrics-after.txt
```

Và:

```bash
cat evidence-g6/06-metrics-after.txt |
sudo docker exec -i "$PROM_CID" \
  promtool check metrics
```

Nếu lỗi giống G4:

```text
Known issue reproduced.
```

Không coi đây là HA regression mới nếu functional monitoring vẫn phục hồi.

---

## G6.11 — Prometheus recovery

```bash
curl -fsS \
  http://10.20.20.11:9095/api/v1/targets \
  > evidence-g6/07-targets-after.json
```

Yêu cầu sau vài scrape cycle:

```text
health = up
lastError = ""
lastScrape cập nhật
```

---

## G6.12 — Fresh sample sau failover

```bash
curl -fsSG \
  http://10.20.20.11:9095/api/v1/query \
  --data-urlencode 'query=timestamp(ceph_health_status)' \
  > evidence-g6/08-freshness-after.json
```

Điều kiện:

```text
timestamp AFTER > timestamp BEFORE
```

Đây là bằng chứng monitoring thực sự phục hồi chứ không chỉ đang hiển thị sample cũ.

---

## G6.13 — Chạy lại Rule/Alert

```bash
curl -fsS \
  http://10.20.20.11:9095/api/v1/rules \
  > evidence-g6/09-rules-after.json

curl -fsS \
  http://10.20.20.11:9095/api/v1/alerts \
  > evidence-g6/10-alerts-after.json
```

Rule engine phải tiếp tục evaluation sau failover.

---

## G6.14 — Dashboard/API trên active mới

Chạy:

```bash
ceph mgr services
```

Xác nhận Dashboard endpoint chuyển theo active mới.

Sau đó:

```text
login Dashboard
→ mở trang cluster
→ lấy dữ liệu
→ test API/web đang sử dụng
```

Phải hoạt động lại sau failover.

---

## G6.15 — Workload sau failover

Lặp lại cùng probe trước failover:

```text
RGW PUT/GET
hoặc
RBD/RADOS read/write
```

Kết quả phải giống baseline.

---

# Kết luận G6

Nếu:

```text
standby takeover          PASS
old active return standby PASS
MON/PG/OSD                PASS
cephadm/module            PASS
Prometheus recover        PASS
fresh metrics             PASS
rules/alerts              PASS
Dashboard/API             PASS
workload                  PASS
```

thì:

```text
G6 = PASS
```

Known issue `G4-MON-01` vẫn được giữ riêng:

```text
Duplicate HELP/TYPE remains reproducible,
but no loss of HA functionality or fresh
monitoring data was observed during failover.
```