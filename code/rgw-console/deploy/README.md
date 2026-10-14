# Hướng dẫn cài đặt image

Cài thử nhanh trên Windows: xem [code/README.md](../../README.md). Lý thuyết: [tổng hợp.md](<../../tổng hợp.md>). Tài liệu này chỉ gồm các bước triển khai và cấu hình.

## Image sử dụng

Bản RC staging chỉ đọc hiện tại là `5.2.0-rc.1`, Linux AMD64, **chưa được chấp thuận production**:

```text
dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342
```

Dependency đã pin trong [.env.production.example](.env.production.example):

```text
postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
```

Không dùng `latest`, không tự thay digest khi cài đặt. Kiểm image bằng `docker run --rm --network none <image-ref> version`. Cài sạch localhost với `.env` đã giữ dùng `start-image-readonly.ps1` theo [README chính](../../README.md#cài-localhost-bằng-cấu-hình-đã-giữ); script không phụ thuộc container cũ.

Bộ cài localhost cũ `5.1.2-rc.1`/digest `35dd7b…` vẫn được giữ riêng, không tự cập nhật. Khi tạo deployment mới từ `.env.production.example`, thay `STORAGE_LAB_CONSOLE_IMAGE` bằng digest RC ở trên; không dùng binary cũ cho overlay ba tài khoản. Để cài staging ba tài khoản, làm theo [mục RC trong README chính](../../README.md#cài-rc-520-với-https-và-ba-tài-khoản-riêng); ví dụ cấu hình thủ công bên dưới là một tài khoản nếu chưa thêm `compose.access-control.yml` và `console_users.json`.

## Cài vào hệ thống thật

Cần Docker Linux AMD64, Compose v2, thư mục/project riêng, PostgreSQL và certificate tin cậy. Không chạy script tạo bộ cài thử lên thư mục đang có. Bộ cài không mặc nhiên được chấp thuận production.

Chuẩn bị các file sau; chỉ sao chép mẫu không bí mật, không sao chép thư mục `secrets` hoặc `.env` của máy khác:

```text
deployment/
├── compose.production.yml
├── .env
├── nginx/production.conf
├── config/profiles/production.yaml
└── secrets/
```

1. Sao chép [compose.production.yml](compose.production.yml) và [nginx/production.conf](nginx/production.conf).
2. Sao chép [.env.production.example](.env.production.example) thành `.env`. Giữ ref application/dependency theo digest đã chọn; đặt `RELEASE_PULL_POLICY=never` sau khi tải đủ image.
3. Đặt `COMPOSE_PROJECT_NAME`, `APP_INSTANCE_ID`, domain, `CONSOLE_HTTPS_PORT` và `CORS_ORIGINS`. Mặc định giữ `CONSOLE_BIND_ADDRESS=127.0.0.1`; chỉ mở management network khi đã cấu hình TLS/auth/firewall phù hợp.
4. Tạo `config/profiles/production.yaml` từ [profile mẫu](config/profiles/lab.yaml.example). Đổi `execution_environment` thành `production`; thay cluster ID, FSID, revision và allowlist theo cluster đích. Khi chưa nối Ceph, giữ `FEATURE_UPGRADE=false`; có thể dùng profile rỗng như bộ cài thử.
5. Provision các secret bên dưới bằng quy trình quản lý secret của hệ thống. Không lưu password/key/token trong `.env`, image hoặc Git.

| File trong `secrets/` | Cần chuẩn bị |
|---|---|
| `postgres_password` | Password PostgreSQL khi dùng profile bundled-db |
| `migration_database_url` | URL role migration/setup DB |
| `database_runtime_password` | Password riêng cho role runtime, ít nhất 32 ký tự |
| `database_url` | URL role `storage_lab_runtime`; không dùng role migration |
| `console_password_hash` | Hash `pbkdf2_sha256$iterations$base64salt$base64digest` |
| `executor_token` | Token ngẫu nhiên ít nhất 32 ký tự |
| `tls_certificate.pem`, `tls_private_key.pem` | Certificate/key tin cậy cho domain đích |
| `ssh_private_key`, `ssh_known_hosts` | Chỉ thêm khi bật profile ceph-readonly |

Với bundled DB, URL migration trỏ tới database `storage_lab_console` tại host Compose `postgres:5432`; URL runtime dùng role `storage_lab_runtime`. Password trong URL phải được URL-encode nếu có ký tự đặc biệt.

Trên Linux, bind-mounted secret phải đọc được bởi UID/GID app `10001:10001`, TLS key bởi ingress `101:101`, nhưng không world-readable. Trường `uid/gid/mode` của Compose không tự đổi quyền file host. Kiểm ánh xạ quyền nếu dùng rootless/user namespace. Trên Windows, giới hạn ACL thư mục secret. SSH private key chỉ mount vào executor.

### Quyền file trên host Linux

Chỉ áp dụng cho **deployment mới** do `prepare-production-staging.ps1` tạo, Docker Engine rootful không remap UID. Script chỉ giới hạn thư mục ngoài; quản trị viên phải đặt quyền file thật trước `up`. Từ đúng thư mục deployment đã xác minh, chạy các đường dẫn cố định sau; không dùng chmod/chown đệ quy hoặc áp lên thư mục source/DB đang chạy:

```bash
chmod 700 ./client ./secrets
chmod 600 ./.env ./client/accounts.json ./client/viewer.password ./client/operator.password ./client/admin.password ./client/staging-ca.key
chmod 755 ./config ./config/profiles ./nginx
chmod 644 ./config/profiles/production.yaml ./nginx/production.conf
sudo chown 10001:10001 ./secrets/database_url ./secrets/migration_database_url ./secrets/database_runtime_password ./secrets/console_users.json ./secrets/console_password_hash ./secrets/executor_token ./secrets/ssh_private_key ./secrets/ssh_known_hosts
sudo chmod 400 ./secrets/database_url ./secrets/migration_database_url ./secrets/database_runtime_password ./secrets/console_users.json ./secrets/console_password_hash ./secrets/executor_token ./secrets/ssh_private_key ./secrets/ssh_known_hosts
sudo chown 101:101 ./secrets/tls_private_key.pem ./secrets/tls_certificate.pem
sudo chmod 400 ./secrets/tls_private_key.pem
sudo chmod 444 ./secrets/tls_certificate.pem
sudo chown 70:70 ./secrets/postgres_password
sudo chmod 400 ./secrets/postgres_password
```

UID 70 dành cho image PostgreSQL Alpine đã pin ở trên; kiểm lại nếu thay image. Không áp numeric UID trên rootless/user namespace hoặc Windows bind mounts; phải có ánh xạ đã kiểm riêng. Trước khởi động, dùng đúng image/overlay để thử `test -r` từng secret trong container theo UID thực, không `cat` secret; mọi file bắt buộc phải đọc được, không world-readable trên host Linux. Nếu một bước thất bại, dừng cài đặt, không nới thành `chmod 777`. CA thử nghiệm không phải certificate production tin cậy. [Giới hạn quyền file secret của Compose](https://docs.docker.com/reference/compose-file/services/#secrets).

Chạy từ thư mục deployment:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cấu hình Compose không hợp lệ' }
$RequiredImages = docker compose --env-file .env -f compose.production.yml --profile bundled-db config --images | Sort-Object -Unique
foreach ($RequiredImage in $RequiredImages) {
    docker pull --platform linux/amd64 $RequiredImage
    if ($LASTEXITCODE -ne 0) { throw "Không tải được image: $RequiredImage" }
}
docker compose --env-file .env -f compose.production.yml --profile bundled-db up -d
docker compose --env-file .env -f compose.production.yml --profile bundled-db ps -a
```

Nếu dùng PostgreSQL ngoài, bỏ `--profile bundled-db`, thay URL/role/TLS và provision **database riêng dành cho console** trước. Không trỏ vào database/schema đang dùng chung với ứng dụng khác: bước `configure-database` điều chỉnh quyền PUBLIC trên database và các đối tượng trong schema public. Không sửa volume/database của deployment khác.

Kiểm `/api/ready` qua HTTPS có xác thực: `ready=true`, schema 21 và frontend sẵn sàng. Giữ kiểm TLS bằng trust store/CA đã xác minh. `/api/live` chỉ kiểm tiến trình và không thay cho readiness có xác thực. `migrate` và `database-permissions` phải kết thúc exit 0.

## Kết nối Ceph chỉ đọc

Chỉ bật luồng đọc sau khi chuẩn bị đủ SSH, FSID, profile, allowlist và helper. Biến `FEATURE_UPGRADE=true` là tên tương thích nội bộ để bật inventory/As-is, không bật quyền nâng cấp.

Trong `.env` và profile:

- Điền `CEPH_EXPECTED_FSID`, `CLUSTER_ID`, `CLUSTER_PROFILE_REVISION` và `POLICY_REVISION` nhất quán.
- Điền `RBD_HOST`, `RBD_SSH_PORT`, `RBD_SSH_USER`.
- Điền `UPGRADE_ALLOWED_OSDS/HOSTS/POOLS/DEVICE_CLASSES`, `RBD_ALLOWED_POOLS` và namespace cần đọc; không dùng wildcard.
- Giữ `CONSOLE_READ_ONLY=true`, `UPGRADE_MUTATIONS_ENABLED=false`, `LAB_ALLOW_WRITE=false`; tắt legacy RGW/RBD, terminal và Lab.
- Sau preflight, đặt `FEATURE_UPGRADE=true`.

Với RC staging/production, quản trị viên cài tài khoản/key/CephX riêng, forced-command guard và helper root-owned theo [PRODUCTION_SSH.md](../docs/PRODUCTION_SSH.md), cần Python 3.10+. Không dùng helper do SSH user sửa được, sudo Ceph rộng hoặc key lab làm bằng chứng quyền tối thiểu. Xác minh host key qua kênh tin cậy; không coi `ssh-keyscan` chưa đối chiếu là xác minh.

Các bước helper trong home và profile `collectors` bên dưới là **luồng lab cũ**, không thay quy trình quyền production ở trên. Lab helper cần Python 3.6+ và quyền đọc Ceph phù hợp.

Lấy helper từ chính image đã pin, từ thư mục deployment:

```powershell
$AppImage = 'dang7904/storage-lab-console@sha256:35dd7b3d32b05ae6d726b1fe6b5875d47edbcf94f0481aebc25f83d81c9f79ee'
$CollectorContainer = docker create $AppImage version
if ($LASTEXITCODE -ne 0) { throw 'Không tạo được container tạm' }
try {
    docker cp ($CollectorContainer + ':/opt/storage-lab-console/collector/collect_osd.py') ./collect_osd.py
    docker cp ($CollectorContainer + ':/opt/storage-lab-console/collector/SHA256SUMS') ./collector-SHA256SUMS
    Get-FileHash -LiteralPath ./collect_osd.py -Algorithm SHA256
} finally {
    docker rm $CollectorContainer
}
```

Đối chiếu SHA-256 với `collector-SHA256SUMS` và metadata `version`, rồi sao chép qua SSH đã pin tới đường dẫn thuộc SSH user, ví dụ `/home/storage-lab/.local/share/storage-lab-console/collect_osd.py`. Không ghi đè helper đang chạy khi chưa backup/đối chiếu hash.

Đặt `OSD_INFO_COLLECTOR_PATH` đúng đường dẫn remote và `OSD_INFO_COLLECTOR_RUN_AS_SSH_USER=true`. Helper chạy dưới tài khoản SSH; chỉ cấp quyền đọc cho các lệnh Ceph cố định cần thiết. Không cần cấp `sudo python`, không tự cấp sudo toàn phần. Nếu CLI chỉ có trong cephadm shell, chuẩn bị management CLI/config chỉ đọc trước.

Khởi động các role đọc:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors config --quiet
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors up -d
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors ps -a
```

Nếu dùng DB ngoài, bỏ profile bundled-db. Kiểm readiness có xác thực, FSID mới trên giao diện và quyền SSH. Nếu sai FSID/allowlist/host key, sửa cấu hình; không bỏ cơ chế kiểm tra.

## Worker OSDMap tùy chọn cho lab

Không bật worker trong bộ cài cơ bản. Nếu cần cho lab/offline, dùng [runbook cài worker](../docs/OSDMAP_PREVIEW.md) và [compose.osdmap.yml](compose.osdmap.yml). Worker chưa đạt production; chỉ bật sau khi chấp nhận giới hạn được ghi trong [tổng hợp.md](<../../tổng hợp.md>).

Ref worker đã phát hành:

```text
dang7904/storage-lab-osdmap@sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893
```

## Backup, cập nhật và dừng

Trước thay image, ngừng nhận yêu cầu mới, chờ công việc đang chạy kết thúc, backup DB/evidence/executor state và kiểm phục hồi.

Với bundled PostgreSQL, từ thư mục chứa script triển khai:

```powershell
./backup-production.ps1 -DeploymentDirectory 'D:/deploy/storage-lab-console' -OutputDirectory 'D:/backups/slc-checkpoint'
./verify-production-backup.ps1 -BackupDirectory 'D:/backups/slc-checkpoint' -OutputDirectory 'D:/backups/slc-restore-check'
```

Dùng thư mục backup/report mới; script từ chối ghi đè. Với DB ngoài, dùng quy trình backup/restore tương ứng của hệ thống.

Sau backup, đổi `STORAGE_LAB_CONSOLE_IMAGE` trong `.env`, pull ref mới rồi chạy lại Compose với đúng profile đã dùng. Xác nhận migration, readiness, checksum/lịch sử và restore. Chỉ rollback image nếu tương thích schema hiện tại.

Dừng mà giữ dữ liệu:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors down
```

Không thêm `--volumes`, không dùng prune để cập nhật.

## Máy không có Internet

Dùng [export-offline-bundle.ps1](export-offline-bundle.ps1) để xuất image/metadata/SBOM/checksum đã có tại máy nguồn. Không đưa secret hoặc profile thật vào bundle chia sẻ. Máy đích đối chiếu `SHA256SUMS`, chạy `docker load`, kiểm image ref rồi giữ `RELEASE_PULL_POLICY=never`.

## Localhost đã có sẵn

Không dùng updater local làm bootstrap máy mới. Với stack local đã xác minh, backup bằng [backup-local-readonly.ps1](backup-local-readonly.ps1), đọc [local-images.preview.json](local-images.preview.json) rồi truyền **cả hai** ref vào updater:

```powershell
$LocalImages = Get-Content -LiteralPath ./local-images.preview.json -Raw | ConvertFrom-Json
./update-local-v5.ps1 -Image $LocalImages.application_image -OsdMapImage $LocalImages.osdmap_worker_image
```

Các image phải có sẵn trong Docker Engine. Updater không tự rollback hoặc chờ readiness; sau chạy phải kiểm lại `/api/ready`, phiên bản, FSID và lịch sử. Không ghi đè `.env.local-readonly` hoặc secret đã cấu hình.
