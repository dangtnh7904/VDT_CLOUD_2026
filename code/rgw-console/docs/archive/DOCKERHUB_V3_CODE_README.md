# Lưu trữ lịch sử — hướng dẫn Docker Hub v3 trước RC v5

Không dùng các tag, schema, luồng session hoặc hướng dẫn cài collector ở đây cho bản hiện tại. Đường dẫn tương đối giữ nguyên theo vị trí README gốc `code/README.md`, có thể không còn mở đúng từ thư mục archive. Hướng dẫn hiện tại ở [README deployment](../../deploy/README.md).

# Storage Lab Console — Thu thập và so sánh hiện trạng

**Cập nhật 12/10/2026.** Phạm vi hiện tại được quy định trong [plan console v5.1](plan%285%29.md): đọc dữ liệu Ceph theo yêu cầu, lưu các lần thu As-is và so sánh hai lần thu cùng loại daemon. [README dự án](../README.md) · [Hướng dẫn cấu hình](rgw-console/README.md).

## 1. Luồng sử dụng

1. Cấu hình cluster ID, FSID, SSH key, host key và phạm vi daemon/pool trong profile riêng của môi trường.
2. Mở **Chỉ số cụm và daemon**. Danh sách hiển thị 10 daemon mỗi trang. **Xem** và **Xuất** yêu cầu đọc nguồn mới; mỗi kết quả ghi thời điểm thu thực tế.
3. Mở **Thu thập hiện trạng**, chọn một hoặc nhiều daemon, gắn nhãn **Trước / Trong / Sau nâng cấp**, rồi thu As-is. Nhãn này mô tả thời điểm, không thực thi nâng cấp.
4. Mở **So sánh**, lọc ngày và loại daemon, chọn hai collection cùng FSID và cùng loại. Hai collection không cần cùng nhãn hoặc session.
5. Xuất collection đã lưu khi cần bản lịch sử bất biến. Xóa mềm/khôi phục collection quản lý dữ liệu của console, không xóa daemon hoặc dữ liệu Ceph.
6. Với OSD, **Xem trước thay đổi OSDMap** mô phỏng CRUSH weight trên map mới thu. Kết quả phải mang nhãn **Dự đoán — chưa áp dụng**, không thay đổi cluster.

Lõi các luồng trên đã build và kiểm tra trên localhost với bản `5.1.0-preview.4`. Hỗ trợ MON/MGR/OSD/RGW/MDS, thêm môi trường SSH client A0.1 và lịch sử phân trang máy chủ 10 collection/trang. Phần A0/telemetry còn thiếu được ghi trong [plan mục 21](plan%285%29.md#21-trạng-thái-triển-khai-và-giới-hạn-bản-preview). Image Docker Hub ở mục 7 là bản cũ.

Tính năng mới dùng tại **Thu thập hiện trạng → Xem trước thay đổi OSDMap**. [Hướng dẫn mô phỏng và đóng gói worker](rgw-console/docs/OSDMAP_PREVIEW.md) giải thích CRUSH reweight native Pacific, effective weight, đồng bộ weight-set, epoch và cách chạy worker offline. Bản local đang dùng hai image `storage-lab-console:5.1.0-preview.4` và `storage-lab-osdmap:16.2.15-preview.2`; các tag này chưa được đẩy lên Docker Hub.

## 2. Thay đổi phạm vi

Benchmark fio/Warp, API chạy/dừng, runner và cấu hình riêng đã được loại khỏi source console. Dry-run nâng cấp cũng đã được gỡ khỏi router hoạt động. Không còn hướng dẫn tạo workload hoặc thay đổi placement thật trong luồng mới.

Migrations đã áp dụng, dữ liệu lịch sử và các tài nguyên Ceph vẫn được giữ. Những module tương thích được giữ cho hồ sơ cũ không phải tính năng nâng cấp đang hoạt động. Công cụ RGW/RBD cũ nằm ở **Công cụ cũ** khi được bật.

## 3. Cấu hình và triển khai

- Backend: [app](rgw-console/backend/app/), PostgreSQL và evidence store.
- Frontend: [src](rgw-console/frontend/src/).
- SSH executor: [rbd-console](rgw-console/rbd-console/), hành động có schema và argv cố định.
- Collector OSD chuyên sâu: [collect_osd.py](osd-info-collector/collect_osd.py).
- Image theo role và hướng dẫn phát hành: [deploy](rgw-console/deploy/README.md).
- Cấu hình SSH lab và bản thu đã kiểm chứng trước đây: [LOCAL_SSH_READONLY.md](rgw-console/docs/LOCAL_SSH_READONLY.md).

Không đóng gói key, token hoặc cấu hình cluster vào image. Mỗi hệ thống dùng profile/secret riêng, xác minh FSID và host key của chính hệ thống đó. Không xóa volume để cập nhật.

## 4. Giới hạn của dữ liệu

Metric tốc độ cần cửa sổ đo thật; giá trị không được nguồn cung cấp giữ trạng thái thiếu, không đổi thành 0. Collection lưu lại là lịch sử tại thời điểm thu. So sánh As-is không tự kết luận nâng cấp thành công. Mô phỏng OSDMap dự đoán placement/primary, không dự đoán IOPS, latency hay thời gian recovery.

[VALIDATION.md](rgw-console/VALIDATION.md) giữ nhật ký kiểm chứng theo phiên bản. Các kết quả kiểm thử cũ không chứng minh v5 đã chạy thành công trên cluster đích.

## 7. Cài và sử dụng image Docker Hub

Image ứng dụng: [`dang7904/storage-lab-console:3.0.0-rc.1`](https://hub.docker.com/r/dang7904/storage-lab-console), đã đăng public và kiểm pull ngày **12/10/2026**. Digest cố định: `sha256:2b2ca753cde297b4d00d013d2c249c5a9a7d6bcdb9a2e2dac70a39c5c2a9d0b5`; [release manifest](rgw-console/deploy/releases/3.0.0-rc.1.yaml) ghi thông tin image và phạm vi kiểm chứng. Bản candidate này dùng **Linux AMD64**, gồm giao diện, API, migration, các worker, SSH executor và collector OSD. Mỗi container chọn một role từ cùng image; PostgreSQL chạy riêng. Máy đích cần Docker Engine/Docker Desktop ở chế độ Linux containers và Docker Compose v2. Chỉ cần các file trong [thư mục deploy](rgw-console/deploy/), không cần build lại source.

RC dùng cho kiểm thử lab. Scan 271 packages còn **85 findings**, gồm **2 Critical và 16 High**; [báo cáo đầy đủ](rgw-console/deploy/dist/dockerhub-3.0.0-rc.1/vulnerabilities.md) ghi package/CVE. Security gate chưa đạt; publication chưa thay thế nghiệm thu production hoặc live PA2.

### 7.1. Tải image và xem phiên bản

Các lệnh PowerShell dưới đây bắt đầu tại thư mục `code`:

```powershell
Set-Location .\rgw-console\deploy
$AppTag = 'dang7904/storage-lab-console:3.0.0-rc.1'
$AppImage = 'dang7904/storage-lab-console@sha256:2b2ca753cde297b4d00d013d2c249c5a9a7d6bcdb9a2e2dac70a39c5c2a9d0b5'
docker pull --platform linux/amd64 $AppImage
if ($LASTEXITCODE -ne 0) { throw 'Không tải được application image' }
docker tag $AppImage $AppTag
docker run --rm --network none $AppImage version

docker pull --platform linux/amd64 postgres:16-alpine
if ($LASTEXITCODE -ne 0) { throw 'Không tải được PostgreSQL image' }
$PostgresImage = (docker image inspect postgres:16-alpine --format '{{index .RepoDigests 0}}').Trim()
```

Role `version` trả về phiên bản ứng dụng, schema DB và version/SHA-256 của collector. `$AppImage` cố định theo release đã đăng, còn `$PostgresImage` là digest dependency lấy sau khi pull; lưu chúng vào cấu hình để các role luôn chạy cùng nội dung image. Tag local `$AppTag` dùng khi xuất archive offline. PostgreSQL 16 là baseline đã kiểm cục bộ. Không trỏ database hiện có của ứng dụng khác vào deployment mới.

### 7.2. Chạy giao diện local lần đầu

Ví dụ này tạo deployment `storage-lab-console-preview` riêng tại `http://127.0.0.1:8080`, chưa nối cluster Ceph. Các lệnh tạo secret mới trong file, không in giá trị ra terminal. Thực hiện trên bản deploy mới; nếu đã có cấu hình/secret, dùng cấu hình đó thay vì chạy lại phần tạo file.

```powershell
$RequiredNewFiles = @('.env.release', 'config/profiles/lab.yaml',
  'secrets/database_url', 'secrets/executor_token', 'secrets/postgres_password')
foreach ($File in $RequiredNewFiles) {
  if (Test-Path -LiteralPath $File) { throw "Đã tồn tại $File; hãy dùng deployment mới" }
}
$Utf8 = [Text.UTF8Encoding]::new($false)
$DeployDirectory = (Get-Location).Path
function Write-RuntimeFile([string]$RelativePath, [string]$Content) {
  [IO.File]::WriteAllText((Join-Path $DeployDirectory $RelativePath), $Content + "`n", $Utf8)
}
function New-SecretHex {
  $Bytes = [byte[]]::new(32)
  $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
  ([BitConverter]::ToString($Bytes)).Replace('-', '').ToLowerInvariant()
}
$DatabasePassword = New-SecretHex
Write-RuntimeFile 'secrets/postgres_password' $DatabasePassword
Write-RuntimeFile 'secrets/database_url' "postgresql://storage_lab_console:${DatabasePassword}@postgres:5432/storage_lab_console"
Write-RuntimeFile 'secrets/executor_token' (New-SecretHex)

$Runtime = Get-Content -LiteralPath .env.release.example -Raw
$Overrides = @{
  STORAGE_LAB_CONSOLE_IMAGE = $AppImage
  POSTGRES_IMAGE = $PostgresImage
  COMPOSE_PROJECT_NAME = 'storage-lab-console-preview'
  APP_INSTANCE_ID = 'storage-lab-console-preview'
  LAB_PROFILE = 'local-preview'
  CLUSTER_ID = 'local-preview'
  CLUSTER_PROFILE_REVISION = 'local-preview-v1'
  CONSOLE_PORT = '8080'
  FEATURE_UPGRADE = 'false'
  CEPH_EXPECTED_FSID = ''
  RBD_HOST = ''
  UPGRADE_ALLOWED_OSDS = ''
  UPGRADE_ALLOWED_HOSTS = ''
  UPGRADE_ALLOWED_POOLS = ''
  UPGRADE_ALLOWED_DEVICE_CLASSES = ''
}
foreach ($Name in $Overrides.Keys) {
  $Runtime = [regex]::Replace($Runtime, "(?m)^$Name=.*$", "$Name=$($Overrides[$Name])")
}
Write-RuntimeFile '.env.release' $Runtime.TrimEnd()
Write-RuntimeFile 'config/profiles/lab.yaml' '{}'
Remove-Variable DatabasePassword

docker compose --env-file .env.release -f compose.release.yml --profile bundled-db config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration không hợp lệ' }
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db up -d postgres migrate api
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db ps -a
```

`migrate` là job một lần, kết thúc với exit code `0`; API chỉ khởi động sau khi migration thành công. `postgres` và `api` cần ở trạng thái healthy. Nếu cổng 8080 đã được deployment khác dùng, sửa `CONSOLE_PORT` trong `.env.release` trước khi `up`.

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/live
Invoke-RestMethod http://127.0.0.1:8080/api/ready
Start-Process http://127.0.0.1:8080
```

`/api/live` trả `status=ok`; `/api/ready` cần trả `ready=true`, schema DB `19`, frontend ready. Với preview, RGW và Ceph executor đều disabled; trạng thái thiếu telemetry/inventory trong giao diện là do chưa nối cluster. File `.env.release`, profile thực và toàn bộ secret chỉ thuộc deployment đang chạy, không đưa vào Git hoặc image.

Trên **Linux lab**, dùng Bash thay cho bước PowerShell 7.1–7.2; cần `openssl`, `curl`, quyền dùng Docker và quyền `sudo chown`. Chạy tại thư mục `deploy` mới và đổi cổng nếu 8080 đang được dùng:

```bash
set -euo pipefail
APP_IMAGE='dang7904/storage-lab-console@sha256:2b2ca753cde297b4d00d013d2c249c5a9a7d6bcdb9a2e2dac70a39c5c2a9d0b5'
docker pull --platform linux/amd64 "$APP_IMAGE"
docker run --rm --network none "$APP_IMAGE" version
docker pull --platform linux/amd64 postgres:16-alpine
POSTGRES_IMAGE=$(docker image inspect postgres:16-alpine --format '{{index .RepoDigests 0}}')

for file in .env.release config/profiles/lab.yaml secrets/database_url secrets/executor_token secrets/postgres_password; do
  if [ -e "$file" ]; then printf 'Đã tồn tại %s; dùng deployment mới\n' "$file" >&2; exit 1; fi
done
umask 077
DB_PASSWORD=$(openssl rand -hex 32)
printf '%s\n' "$DB_PASSWORD" > secrets/postgres_password
printf 'postgresql://storage_lab_console:%s@postgres:5432/storage_lab_console\n' "$DB_PASSWORD" > secrets/database_url
openssl rand -hex 32 > secrets/executor_token
unset DB_PASSWORD
printf '{}\n' > config/profiles/lab.yaml
cp .env.release.example .env.release
sed -i \
  -e "s|^STORAGE_LAB_CONSOLE_IMAGE=.*|STORAGE_LAB_CONSOLE_IMAGE=$APP_IMAGE|" \
  -e "s|^POSTGRES_IMAGE=.*|POSTGRES_IMAGE=$POSTGRES_IMAGE|" \
  -e 's|^COMPOSE_PROJECT_NAME=.*|COMPOSE_PROJECT_NAME=storage-lab-console-preview|' \
  -e 's|^APP_INSTANCE_ID=.*|APP_INSTANCE_ID=storage-lab-console-preview|' \
  -e 's|^LAB_PROFILE=.*|LAB_PROFILE=local-preview|' \
  -e 's|^CLUSTER_ID=.*|CLUSTER_ID=local-preview|' \
  -e 's|^CLUSTER_PROFILE_REVISION=.*|CLUSTER_PROFILE_REVISION=local-preview-v1|' \
  -e 's|^CONSOLE_PORT=.*|CONSOLE_PORT=8080|' \
  -e 's|^FEATURE_UPGRADE=.*|FEATURE_UPGRADE=false|' \
  -e 's|^CEPH_EXPECTED_FSID=.*|CEPH_EXPECTED_FSID=|' \
  -e 's|^RBD_HOST=.*|RBD_HOST=|' \
  -e 's|^UPGRADE_ALLOWED_OSDS=.*|UPGRADE_ALLOWED_OSDS=|' \
  -e 's|^UPGRADE_ALLOWED_HOSTS=.*|UPGRADE_ALLOWED_HOSTS=|' \
  -e 's|^UPGRADE_ALLOWED_POOLS=.*|UPGRADE_ALLOWED_POOLS=|' \
  -e 's|^UPGRADE_ALLOWED_DEVICE_CLASSES=.*|UPGRADE_ALLOWED_DEVICE_CLASSES=|' .env.release
sudo chown 10001:10001 secrets/database_url secrets/executor_token
chmod 0644 config/profiles/lab.yaml
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db config --quiet
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db up -d postgres migrate api
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db ps -a
# Chạy sau khi API healthy.
curl --fail http://127.0.0.1:8080/api/ready
```

Nếu triển khai trên Docker rootless/user namespace, ánh xạ quyền UID của secret theo daemon đó. Khi nối Ceph, profile YAML tiếp tục cần quyền đọc cho UID ứng dụng.

### 7.3. Kết nối cluster lab hoặc hệ thống khác

Tạo một deployment riêng cho mỗi cluster, đổi `COMPOSE_PROJECT_NAME`, `APP_INSTANCE_ID`, `CLUSTER_ID` và `CONSOLE_PORT` nếu cùng máy. Sao chép `config/profiles/lab.yaml.example` thành `config/profiles/lab.yaml`; thay FSID, revision và scope host/OSD/pool/device class bằng inventory của cluster đích. Các giá trị tương ứng trong `.env.release` phải khớp profile; giá trị env được ưu tiên khi tạo snapshot.

Điền `RBD_HOST`, `RBD_SSH_PORT`, `RBD_SSH_USER`, `CEPH_EXPECTED_FSID` và các allowlist `UPGRADE_ALLOWED_*`. Cấp `secrets/ssh_private_key` cho management host đã chọn và `secrets/ssh_known_hosts` chứa host key đã xác minh qua kênh tin cậy. Giữ `UPGRADE_MUTATIONS_ENABLED=false`, `LAB_ALLOW_WRITE=false` và các legacy feature chưa dùng ở `false`. [Danh mục secret](rgw-console/deploy/secrets/README.md) mô tả file nào được mount vào từng role. Trên Linux, các secret của ứng dụng phải đọc được bởi UID/GID `10001:10001`; Docker Compose local dùng bind mount nên không nên chỉ dựa vào trường `uid/gid/mode` của Compose để đổi quyền file trên host.

Collector có sẵn **trong image**, nhưng action inventory chạy qua SSH trên management host. Chép đúng collector từ image vừa pull lên host đó; ví dụ dùng OpenSSH/scp trên máy triển khai:

```powershell
$CollectorContainer = docker create $AppImage version
docker cp "${CollectorContainer}:/opt/storage-lab-console/collector/collect_osd.py" .\collect_osd.py
docker cp "${CollectorContainer}:/opt/storage-lab-console/collector/SHA256SUMS" .\collector-SHA256SUMS
docker rm $CollectorContainer
Get-FileHash .\collect_osd.py -Algorithm SHA256

# Thay SSH_USER và CEPH_ADMIN_HOST bằng giá trị của deployment.
scp .\collect_osd.py SSH_USER@CEPH_ADMIN_HOST:collect_osd.py
ssh SSH_USER@CEPH_ADMIN_HOST 'sudo -n install -d -m 0755 /opt/storage-lab; sudo -n install -m 0644 collect_osd.py /opt/storage-lab/collect_osd.py; sha256sum /opt/storage-lab/collect_osd.py; sudo -n python3 /opt/storage-lab/collect_osd.py --version; sudo -n ceph fsid'
```

So sánh SHA-256 trên host với file đã lấy từ image và kết quả role `version`. `OSD_INFO_COLLECTOR_PATH=/opt/storage-lab/collect_osd.py` là đường dẫn **remote**. SSH user cần quyền chạy không tương tác các lệnh đã cho phép (`sudo -n`), Python 3.6+ và Ceph CLI với config/keyring đọc cluster. Executor hiện gọi `ceph`, `rbd` và `python3` trực tiếp trên host; nếu cluster chỉ có CLI trong `cephadm shell`, phải provision management CLI/config phù hợp trước khi dùng integration. Hướng dẫn [collector độc lập](osd-info-collector/README.md) có cách thu evidence qua `cephadm shell`.

Sau khi FSID/SSH/collector đã xác minh, đặt `FEATURE_UPGRADE=true` rồi khởi động các role cần thiết:

```powershell
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db --profile ceph-ssh --profile collectors config --quiet
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db --profile ceph-ssh --profile collectors up -d
Invoke-RestMethod http://127.0.0.1:8080/api/ready
```

Nếu dùng PostgreSQL bên ngoài, điền URL/TLS vào `secrets/database_url` và bỏ `--profile bundled-db`; `POSTGRES_IMAGE` vẫn cần một ref hợp lệ vì model Compose khai báo service tùy chọn. Sau readiness, tạo profile/session trong Console, kiểm FSID và capabilities, thu snapshot OSD mới, rồi xem inventory/readiness/plan. `ready=true` chỉ xác nhận dependency đang hoạt động; live PA2, backup/restore và nghiệm thu môi trường vẫn có verdict riêng theo [VALIDATION.md](rgw-console/VALIDATION.md). Bật `collectors` để tổng hợp performance; bật `legacy-workers` chỉ khi đã cấu hình riêng RGW/corpus và scope cần thiết.

### 7.4. Dừng, cập nhật và chuyển vào môi trường offline

Xem lỗi của API/migration và dừng deployment mà giữ dữ liệu:

```powershell
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db --profile ceph-ssh --profile collectors logs --tail 100 api migrate executor
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db --profile ceph-ssh --profile collectors down
```

Named volumes giữ PostgreSQL, evidence và executor state qua recreate. Không thêm `--volumes` khi dừng/cập nhật. Trước khi đổi digest, backup DB và evidence, pause/reconcile công việc đang chạy, rồi migration bằng image mới và kiểm readiness. Chỉ quay về image cũ khi nó hỗ trợ schema DB hiện tại; xem [runbook triển khai](rgw-console/deploy/README.md).

Để chuyển image cùng PostgreSQL vào lab không có Internet, chạy trong PowerShell 7 với Docker Scout đã cài:

```powershell
.\export-offline-bundle.ps1 -ApplicationImage $AppTag `
  -DependencyImages postgres:16-alpine `
  -OutputDirectory .\dist\storage-lab-console-3.0.0-rc.1
```

Chuyển bundle qua kênh đã chọn, đối chiếu `SHA256SUMS` rồi trên máy đích chạy `docker load --input images/storage-lab-console-images.tar`. Dùng ref/tag có trong `docker image ls` và metadata của bundle, giữ `RELEASE_PULL_POLICY=never`, provision secret/profile tại máy đích, rồi thực hiện bước start/readiness bên trên. Khi xuất cho release, bổ sung báo cáo quét đã duyệt bằng `-VulnerabilityReportPath`; exporter không có báo cáo này sẽ ghi rõ candidate. Image được đăng lên registry hoặc load offline vẫn cần nghiệm thu cluster đích trước khi bật mutation.
