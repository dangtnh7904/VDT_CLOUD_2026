# Bản lưu implementation trước v5

Tài liệu này lưu nội dung README cũ để tra lịch sử. Các mô tả màn hình/session/dry-run/upgrade bindings phía dưới không còn là luồng sử dụng hay API nâng cấp đang hoạt động. Liên kết bên dưới dùng ngữ cảnh thư mục README cũ `code/rgw-console`; xem README hiện hành để triển khai.

# Ceph Storage Lab Console

[Plan v5.1](../plan%285%29.md) là contract hiện hành: chỉ số lấy mới khi bấm Xem/Xuất, thu As-is nhiều loại daemon, so sánh hai collection cùng loại, và mô phỏng thay đổi OSDMap cục bộ. [Hướng dẫn sử dụng tổng quan](../README.md) mô tả luồng mới. Source đang được kiểm tra tích hợp; image Docker Hub `3.0.0-rc.1` chưa chứa các thay đổi v5.

Benchmark fio/Warp và Dry-run nâng cấp đã được gỡ khỏi bề mặt API hoạt động. Database/migration lịch sử được giữ để không phá dữ liệu đã lưu. Không có hành động tự động nâng cấp daemon hoặc áp dụng map từ mô phỏng.

## Cấu hình cluster

Giữ secret trong file riêng hoặc `.env`; profile chỉ chứa định danh và allowlist:

```powershell
Copy-Item .env.example .env
Copy-Item config/profiles/lab.yaml.example config/profiles/lab.yaml
```

Đặt `CLUSTER_CONFIG_PATH=config/profiles/lab.yaml`. Giá trị cấu hình tường minh trong môi trường/`.env` ghi đè profile. Profile thực tế và `.env` được Git ignore.

Để đọc Ceph, đặt `FEATURE_UPGRADE=true`, FSID, cluster ID, executor URL/token và phạm vi OSD/host/pool. Giữ `CONSOLE_READ_ONLY=true`, `UPGRADE_MUTATIONS_ENABLED=false` và tắt công cụ cũ khi chỉ cần thu hiện trạng. [Cấu hình SSH lab](docs/LOCAL_SSH_READONLY.md) ghi kết nối và baseline đã kiểm chứng trước đây.

## API tương thích lịch sử

Các phần dưới mô tả API OSD/session cũ được giữ cho dữ liệu đã lưu; giao diện As-is mới không yêu cầu người dùng tạo Upgrade session. Bản thu cũ vẫn là dữ liệu tại thời điểm thu, không được gắn nhãn mới bằng cách mở lại.

## OSD Info Collector integration

The console now integrates the standalone `code/osd-info-collector/collect_osd.py`
contract as a point-in-time, read-only inventory source. It is separate from
the continuous capacity and performance collectors. The backend stores the
complete collector JSON as an append-only SHA-256 evidence artifact and indexes
the identity, network, device, capacity, placement and version fields needed by
later upgrade planning.

```text
GET  /api/v1/sessions
POST /api/v1/osd-inventory/collections
GET  /api/v1/osd-inventory/collections?session_id=<session UUID>
GET  /api/v1/osd-inventory/collections/compare?before_id=<UUID>&after_id=<UUID>
GET  /api/v1/osd-inventory/collections/compare-config?before_id=<UUID>&after_id=<UUID>
GET  /api/v1/osd-inventory/collections/{collection_id}
GET  /api/v1/osd-inventory/collections/{collection_id}/evidence
GET  /api/v1/osd-inventory/collections/{collection_id}/osds/{osd_id}
POST /api/v1/upgrade-runs/{run_id}/inventory-bindings
GET  /api/v1/upgrade-runs/{run_id}/inventory-readiness
POST /api/v1/upgrade-runs/{run_id}/down-set-readiness
```

The `OSD inventory` screen lists production-upgrade sessions and their
immutable collections, creates a phase-labelled snapshot, shows indexed
planning fields without converting missing values to zero, and opens redacted
views of each OSD payload and the collection-level cluster status/config
evidence. Before serving cluster evidence, FastAPI resolves only the artifact
URI registered for the collection, enforces `EVIDENCE_ROOT` containment, checks
the stored byte count and SHA-256, and validates the collector protocol again.
The append-only artifact remains unchanged. The UI accepts only a phase and
numeric OSD IDs; it cannot submit shell commands, artifact paths, collector
paths or Ceph credentials.

When an upgrade run is selected, the screen reads its persisted batch context
and lists the selected source and destination OSDs using PA1 (`X`, `S/R`) or
PA2 (`U`, `D`) role labels. Opening an inventory snapshot marks which planned
OSDs are covered and which are missing; this display does not edit the plan.

The separate config-evidence comparator reads two verified artifacts and
normalizes cluster `config dump` plus each OSD's effective configuration. It
reports added, removed and changed options without treating the result as an
upgrade verdict. Row ordering is ignored, unavailable command evidence makes
the result `INCONCLUSIVE`, and sensitive changes are detected from the source
artifacts while both displayed values remain `[REDACTED]`.

`POST` requires an `Idempotency-Key`, a session ID, a phase (`MANUAL`,
`BEFORE`, `DURING`, `AFTER_START` or `AFTER_STABLE`), and optionally an OSD ID
list. Omitting the list means every OSD in `UPGRADE_ALLOWED_OSDS`, not every OSD
in the cluster. Both FastAPI and the Node executor reject IDs outside that
allowlist. Missing capacity/PG/up-in fields stay `null` and make the indexed
record `INCONCLUSIVE`; a missing device is never guessed and is reported as
`PARTIAL` with warnings.

Install the versioned collector on the SSH target at the fixed
`OSD_INFO_COLLECTOR_PATH` (default example:
`/opt/storage-lab/collect_osd.py`) and confirm `python3 <path> --version`
returns `1.0.2`. The executor invokes only this fixed path with repeated numeric
`--osd` arguments and bounded command timeout/output; no API accepts a command,
shell fragment, config path or keyring path from the browser.

Example request:

```json
{
  "session_id": "<session UUID>",
  "phase": "BEFORE",
  "osd_ids": [0, 4]
}
```

Migration `0016_osd_info_collector.sql` adds collection/job state and immutable
per-OSD snapshot rows. Migration `0017_upgrade_inventory_bindings.sql` adds an
append-only link from a `BEFORE` collection to a run/plan revision and stores the
artifact hash, FSID, config snapshot and freshness decision. Binding is accepted
only when the collection is complete, `VALID`, fresh, from the same
cluster/session/config snapshot and contains every source/destination OSD in the
plan. Preflight embeds the binding in its evidence and placement plan; an absent
or stale binding forces `execution_readiness=BLOCKED` without turning the dry-run
operation into a production result.

Migration `0018_osd_inventory_topology_fields.sql` additively indexes CRUSH
location, device class, all public/cluster addresses, BlueStore data/DB/WAL
paths and physical devices, daemon status, Ceph short version, and container
image/digest. The raw collector record remains preserved; missing topology is
`PARTIAL` with an explicit warning and is never synthesized.

Migration `0019_osd_inventory_cluster_context.sql` additively projects the
collection-level health status/checks, OSDMap epoch, cluster flags, pool
size/min_size/PG/CRUSH policy, daemon version summary and cluster OSD/PG counts.
Missing commands remain `null` or empty evidence containers; numeric zero is
preserved and the projection is observational rather than a safety verdict.

`UPGRADE_INVENTORY_MAX_AGE_SECONDS` defaults to 45 seconds and is captured in
the resolved config snapshot. The readiness endpoint recalculates age on every
read. The down-set readiness endpoint is also read-only: it binds a persisted
`BEFORE`/`DURING` collection to the current run tokens, requires a full
allowlist snapshot, counts already unavailable OSDs, and applies
`max_simultaneous_down`. Even when its `inventory_result` is `READY`, its
`mutation_readiness` remains `BLOCKED` with explicit PG up/acting, cluster
health, lease/fence and live-mutation limitations. It is not a live down-set
endpoint and does not claim that a production mutation was executed.

The phase comparison API and UI compare a `BEFORE` snapshot with
`AFTER_START` or `AFTER_STABLE`. They return raw per-field changes while
preserving `null` as unknown. A different cluster, FSID, session, config
snapshot or OSD scope returns `NOT_COMPARABLE` with reasons; partial evidence
returns `INCONCLUSIVE`. The comparison is descriptive evidence only and never
sets the production operation result.

Web console để tạo workload, quản lý dữ liệu thử nghiệm RGW/RBD và quan sát
capacity/performance của Ceph. React không nhận AWS/RGW credential; mọi thao
tác S3 hoặc đặc quyền Ceph nằm trong FastAPI, worker hoặc Node SSH executor nội
bộ.

Kết quả đã chạy và các mục Ceph/RBD chưa thể chạy trên máy hiện tại được ghi
tách bạch trong [`VALIDATION.md`](VALIDATION.md).

## Nguồn file Ubuntu

Backend chỉ cho phép đọc hai root được cấu hình:

- `mixed` → `/home/dangg/code/data/mix-file-corpus`
- `size` → `/home/dangg/code/data/size-file-corpus`

Trong Docker hai thư mục này được mount read-only ở `/data`. UI gửi `corpus_id` và relative path, backend resolve path thật rồi kiểm tra nó vẫn nằm trong root allowlist. Absolute path và `../` không thể thoát khỏi allowlist.

Lưu ý: native file dialog của browser luôn đọc filesystem của **máy đang chạy browser**. Vì thế lựa chọn “Ubuntu filesystem” dùng modal duyệt file do backend cung cấp; lựa chọn “Máy đang mở browser” dùng native dialog bình thường.

## PostgreSQL

Database `rgw_console` phải tồn tại trước khi chạy migration. Migration quản lý
schema bên trong database, không tự tạo database server hay database mới.

Trên Windows/PowerShell, có thể kiểm tra hoặc tạo database theo cách idempotent.
Password chỉ được đặt trong environment của process hiện tại, không truyền
trên command line và không ghi vào repository:

```powershell
Set-Location code/rgw-console
$env:PGPASSWORD = Read-Host "PostgreSQL password" -MaskInput
try {
  .\scripts\setup-postgres.ps1 -Server 127.0.0.1 -User postgres -Database rgw_console -WhatIf
  .\scripts\setup-postgres.ps1 -Server 127.0.0.1 -User postgres -Database rgw_console
  .\scripts\check-postgres.ps1 -Server 127.0.0.1 -User postgres -Database rgw_console
} finally {
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
```

`setup-postgres.ps1` không thay đổi gì nếu database đã tồn tại. Script
`check-postgres.ps1` ép session sang read-only. Hãy URL-encode password nếu nó có
ký tự dành riêng như `@`, `:`, `/` hoặc `%`.

## Unified image và bộ triển khai release

Application release dùng một OCI image cho các role `api`, `worker`,
`performance-collector`, `capacity-collector`, `rbd-lifecycle-worker`,
`executor`, `migrate` và `version`. Frontend production được API phục vụ cùng
origin. PostgreSQL vẫn là dependency/volume riêng; profile, secrets, evidence và
executor fencing state không được bake vào image.

- Dockerfile: [`packaging/Dockerfile`](packaging/Dockerfile).
- Image-only Compose, manifest mẫu và hướng dẫn online/offline:
  [`deploy/README.md`](deploy/README.md).
- Checkpoint build/test mới nhất: [`VALIDATION.md`](VALIDATION.md).

Build từ thư mục `code/` để deny-all `.dockerignore` chỉ đưa source cần thiết
vào context:

```powershell
Set-Location ..
$buildDate = (Get-Date).ToUniversalTime().ToString("o")
docker build -f rgw-console/packaging/Dockerfile `
  --build-arg APP_VERSION=3.0.0-dev `
  --build-arg VCS_REF=workspace `
  --build-arg "BUILD_DATE=$buildDate" `
  -t storage-lab-console:3.0.0-dev .
docker run --rm --network none storage-lab-console:3.0.0-dev version
```

Tag trên chỉ là candidate cục bộ. Khi phát hành phải dùng version/revision/time
thật, tạo SBOM và vulnerability report, push/ký theo trust policy rồi điền digest
bất biến vào manifest và `.env.release`. Không bật live mutation chỉ vì image
build hoặc healthcheck đạt.

## Chạy development bằng Docker

Cần Docker Compose v2 (`docker compose version`). Mặc định Compose không
khởi tạo PostgreSQL container. `migrate`, `backend` và `worker` kết nối tới
PostgreSQL đã cài trên host qua `host.docker.internal` và
`DOCKER_DATABASE_URL`.

```powershell
Set-Location code/rgw-console
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Sửa RGW endpoint, key, secret, bucket và hai DATABASE_URL. Không commit .env.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Compose chạy `python -m app.migrate` một lần. `backend`, `worker` và
`performance-collector` chỉ
khởi động sau khi migration thành công. `extra_hosts` dùng
`host-gateway` để cùng cấu hình hoạt động với Docker Desktop và Docker
Engine hiện đại.

Profile `ceph-ssh` không được bật mặc định. Khai báo chính xác FSID, SSH target,
private-key path, executor token, pool/namespace allowlist rồi bật Node executor,
capacity collector và RBD worker cùng lúc:

```bash
docker compose --profile ceph-ssh up --build -d
docker compose --profile ceph-ssh ps
```

Nếu thiếu FSID, allowlist, executor token hoặc SSH, API/UI RBD fail closed. Node
executor không publish port ra host/browser và chỉ nhận action schema đóng qua
`POST /internal/v1/execute`. Không bật
`CAPACITY_OBSERVE_ONLY=false` cho tới khi inventory mọi affected pool, tham số
metadata/safety margin và chuỗi fresh stable samples đã được kiểm chứng.

Nếu cần database container tách biệt cho lab, profile `bundled-db` là tùy
chọn và không được bật bởi `docker compose up` thông thường. Khởi
động database trước, chờ healthcheck, rồi chạy stack với URL nội bộ:

```powershell
$env:BUNDLED_POSTGRES_PASSWORD = Read-Host "Bundled PostgreSQL password" -MaskInput
$encodedPassword = [Uri]::EscapeDataString($env:BUNDLED_POSTGRES_PASSWORD)
$env:DOCKER_DATABASE_URL = "postgresql://rgw:$encodedPassword@postgres:5432/rgw_console"
try {
  docker compose --profile bundled-db up -d --wait postgres
  docker compose --profile bundled-db up --build -d
} finally {
  Remove-Item Env:BUNDLED_POSTGRES_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:DOCKER_DATABASE_URL -ErrorAction SilentlyContinue
}
```

Các image dùng `build.network: host` để pip/npm dùng DNS của máy build.
Khi cần xem log tải dependency đầy đủ, chạy
`docker compose build --no-cache --progress=plain`.

## Chạy backend native

Từ thư mục `code/rgw-console`, tạo `.env` và đặt `DATABASE_URL` dùng
`127.0.0.1` (không dùng `host.docker.internal`). Sau đó:

```powershell
python -m venv .\backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m app.migrate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Chạy `python -m app.worker` trong terminal thứ hai với cùng virtualenv,
`PYTHONPATH` và working directory. Frontend native chạy bằng `npm ci` rồi
`npm run dev` trong thư mục `frontend`.

Khi chạy native, Node executor SSH tới Linux Ceph client; chạy thêm `python -m
app.capacity_collector` và `python -m app.rbd_lifecycle_worker`. Private key chỉ
được mount read-only vào executor. Không chạy lệnh Ceph/RBD trực tiếp trong
FastAPI hoặc nhận command tùy ý từ frontend.

Chạy `python -m app.performance_collector` trong một terminal khác trên mọi
nền tảng. Collector này luôn ghi request IOPS/throughput của console. Để thêm
toàn cluster Ceph, đặt `PERFORMANCE_SOURCE=prometheus`,
`PERFORMANCE_PROMETHEUS_URL` và `CEPH_EXPECTED_FSID` sau khi đã kiểm tra endpoint
mgr/Prometheus đúng cluster. Sample đầu tiên chỉ dùng làm baseline và được báo
`PARTIAL/WARMING_UP`; collector không biến nó thành 0 IOPS.
Nếu endpoint dùng bearer auth, đặt token ở
`PERFORMANCE_PROMETHEUS_BEARER_TOKEN`; không nhúng credential vào URL và không
đưa biến này sang frontend.

Mở `http://localhost:5173`. Frontend được publish trên mọi interface; API là `http://localhost:8000` và Swagger là `http://localhost:8000/docs`.

Kiểm tra:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/corpora
curl "http://127.0.0.1:8000/api/performance/current?source=application"
curl "http://127.0.0.1:8000/api/performance/history?source=application&step=15"
```

## RBD file browser, checksum validation và terminal

Volume ở trạng thái `MOUNTED`/`READY` có nút mở detail. File browser dùng SFTP
qua Node executor để list, upload dạng stream, download, tạo directory và xóa
file/directory rỗng. Text, ảnh và PDF chỉ được preview khi MIME sniff thực tế
nằm trong `RBD_ALLOWED_PREVIEW_MIME` và file không vượt
`RBD_FILE_PREVIEW_MAX_BYTES`; response luôn có `nosniff`. Path được resolve bằng
SFTP `realpath`/`lstat`, từ chối `..`, special file và symlink để không thoát
mountpoint của volume.

Tab kiểm chứng upgrade lưu baseline SHA-256 của tối đa 100 file vào migration
`0008_rbd_validation_runs.sql`. Sau unmount/remap/mount, nút `Verify now` đọc
lại đúng image ID và filesystem UUID rồi ghi `PASS`, `FAIL` hoặc `ERROR`; đây
là evidence workflow, không tự đánh dấu live upgrade PASS.

Web terminal lấy vé ngẫu nhiên dùng một lần, hết hạn nhanh từ FastAPI. Browser
kết nối `/ws/terminal`; FastAPI bridge tới Node và Node mở `ssh2.shell()` trên
đúng Linux host, bắt đầu tại mountpoint. Đây là shell thật dành riêng cho lab,
không phải sandbox: tài khoản SSH và `sudo -n` vẫn quyết định phạm vi quyền.
Session idle/max-duration được giới hạn; đóng terminal chỉ đóng shell, không
unmount volume. Unmount/unmap/delete bị từ chối khi còn file transfer hoặc
terminal session do console quản lý.

Các API chính:

```text
GET    /api/rbd/volumes/{id}/files?path=/
GET    /api/rbd/volumes/{id}/files/metadata?path=/docs/a.txt
GET    /api/rbd/volumes/{id}/files/content?path=/docs/a.txt&preview=true
PUT    /api/rbd/volumes/{id}/files/content?path=/docs/a.txt
POST   /api/rbd/volumes/{id}/directories
DELETE /api/rbd/volumes/{id}/files?path=/docs/a.txt
POST   /api/rbd/volumes/{id}/validation-runs
POST   /api/rbd/volumes/{id}/validation-runs/{run_id}/verify
POST   /api/rbd/volumes/{id}/terminal-ticket
WS     /ws/terminal?ticket=<single-use-ticket>
```

## Forward port về máy host

Nếu Ubuntu/Ceph master là máy remote:

```bash
ssh -N -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 USER@IP_CEPH_MASTER
```

Sau đó mở `http://localhost:5173` trên host. Với VS Code Remote SSH, forward port `5173`; browser chỉ cần port này vì Nginx proxy `/api` nội bộ sang backend.

Không publish PostgreSQL bundled và không đặt credential trong biến
`VITE_*`. Khi chuyển RGW node, sửa duy nhất `RGW_ENDPOINT_URL` trong `.env`,
sau đó:

```bash
docker compose restart backend worker performance-collector
```

## Thành phần

- `frontend`: React/Vite, capacity banner, Performance dashboard, Object Explorer và manual RBD lifecycle UI.
- `backend`: FastAPI + boto3, RGW/RBD allowlist, idempotency, capacity admission và telemetry APIs.
- `worker`: process Python riêng, lấy streaming job từ PostgreSQL, hỗ trợ pause/resume/stop.
- `performance-collector`: ghi application I/O, tùy chọn tính Ceph client IOPS/throughput từ counter mgr/Prometheus, tạo rollup 1 phút và dọn retention.
- `rbd-console` (profile `ceph-ssh`): Node executor nội bộ, giữ SSH key read-only; action Ceph/RBD dùng allowlist + FSID binding, file I/O dùng SFTP containment và terminal dùng vé một lần.
- `capacity-collector` (profile `ceph-ssh`): lấy inventory Ceph chỉ đọc qua Node executor và lưu snapshot theo OSD/pool scope.
- `rbd-lifecycle-worker` (profile `ceph-ssh`): state machine create/map/format/mount/unmount/unmap/delete có fence và reconcile.
- PostgreSQL host: lưu operations, capacity ledger, idempotency, volume/action và trạng thái job.
- `postgres` (profile `bundled-db`, tùy chọn): database container riêng cho lab.

Object tạo bởi hệ thống dùng key:

```text
clients/{client_id}/{mode}/{category}/{yyyy-mm-dd}/[prefix/]{timestamp}-{uuid}.{ext}
```

Upload folder giữ các subdirectory giữa phần ngày và filename sinh tự động. Metadata S3 lưu `original-name`, `client-id`, `category` và `source`.
