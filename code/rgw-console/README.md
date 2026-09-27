# Ceph Storage Lab Console

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

## Chạy bằng Docker

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
