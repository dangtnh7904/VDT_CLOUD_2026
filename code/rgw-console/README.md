# RGW Object Lab

Web console để PUT/GET object qua Ceph RGW. React không nhận AWS/RGW credential; mọi thao tác S3 nằm trong FastAPI hoặc worker.

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

Compose chạy `python -m app.migrate` một lần. `backend` và `worker` chỉ
khởi động sau khi migration thành công. `extra_hosts` dùng
`host-gateway` để cùng cấu hình hoạt động với Docker Desktop và Docker
Engine hiện đại.

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

Mở `http://localhost:5173`. Frontend được publish trên mọi interface; API là `http://localhost:8000` và Swagger là `http://localhost:8000/docs`.

Kiểm tra:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/corpora
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
docker compose restart backend worker
```

## Thành phần

- `frontend`: React/Vite, modal corpus picker, upload progress riêng cho file local, dashboard SSE.
- `backend`: FastAPI + boto3, allowlist, ListObjectsV2 pagination, streamed/range GET.
- `worker`: process Python riêng, lấy streaming job từ PostgreSQL, hỗ trợ pause/resume/stop.
- PostgreSQL host: lưu operations, live metrics và trạng thái job.
- `postgres` (profile `bundled-db`, tùy chọn): database container riêng cho lab.

Object tạo bởi hệ thống dùng key:

```text
clients/{client_id}/{mode}/{category}/{yyyy-mm-dd}/[prefix/]{timestamp}-{uuid}.{ext}
```

Upload folder giữ các subdirectory giữa phần ngày và filename sinh tự động. Metadata S3 lưu `original-name`, `client-id`, `category` và `source`.
