# Cài đặt Storage Lab Console từ Docker image

README này chỉ hướng dẫn cài đặt, cấu hình và cập nhật image. Phần giải thích hệ thống nằm trong [tổng hợp.md](<tổng hợp.md>).

Không cần build lại source; các image dưới đây dùng Linux AMD64. Mục đầu cài RC `5.2.0-rc.1` cho staging HTTPS/phân quyền; hướng dẫn lab `5.1.2-rc.1` đã có được giữ ở phần sau.

Để cài vào hệ thống production, làm theo [các bước bàn giao cho quản trị viên](rgw-console/docs/PRODUCTION_HANDOFF.md): SSH/CephX riêng, domain/certificate, secret/RBAC, lịch backup/cảnh báo, ký và kiểm image. Runbook có lệnh kiểm đạt và rollback giữ dữ liệu; RC/staging PASS không tự thay nghiệm thu host đích. Các bước này không dọn dung lượng máy hiện tại.

## Cài RC 5.2.0 với HTTPS và ba tài khoản riêng

Bản `5.2.0-rc.1` dành cho staging chỉ đọc, **chưa được chấp thuận production**. Không thay bộ cài 8080 hoặc `.env` đang có. Cần Docker Linux AMD64/containerd image store, Compose 2.30+, PowerShell 7.2+, Python 3.10+ và OpenSSL trên PATH. Checker dùng thư viện chuẩn Python, không cần cài pip package. Chọn thư mục/project/cổng mới:

```powershell
git clone --branch codex/console-production-readonly https://github.com/dangtnh7904/VDT_CLOUD_2026.git storage-lab-console-staging-install
Set-Location storage-lab-console-staging-install/code/rgw-console/deploy
$ErrorActionPreference = 'Stop'
$DeployScripts = (Get-Location).Path
$AppImage = 'dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342'
docker pull --platform linux/amd64 $AppImage
if ($LASTEXITCODE -ne 0) { throw 'Không tải được image RC' }
docker run --rm --network none $AppImage version
if ($LASTEXITCODE -ne 0) { throw 'Không kiểm tra được image' }
$DeploymentDirectory = 'D:/deploy/storage-lab-console-staging-new'
./prepare-production-staging.ps1 -OutputDirectory $DeploymentDirectory -ApplicationImage $AppImage -SourceLabEnvFile 'D:/config/cluster.env' -SshPrivateKey 'C:/path/to/ssh_private_key' -PrometheusUrl 'http://mgr-active.lab.example:9283/metrics' -ProjectName storage-lab-console-staging-new -Port 8446
if (-not $?) { throw 'Không tạo được cấu hình staging' }
Set-Location $DeploymentDirectory
docker compose --env-file .env -f compose.production.yml -f compose.access-control.yml -f compose.staging.yml --profile bundled-db --profile ceph-readonly config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cấu hình Compose chưa hợp lệ' }
docker compose --env-file .env -f compose.production.yml -f compose.access-control.yml -f compose.staging.yml --profile bundled-db --profile ceph-readonly pull --policy always
if ($LASTEXITCODE -ne 0) { throw 'Không tải được dependency' }
docker compose --env-file .env -f compose.production.yml -f compose.access-control.yml -f compose.staging.yml --profile bundled-db --profile ceph-readonly up -d
if ($LASTEXITCODE -ne 0) { throw 'Không khởi động được staging' }
docker compose --env-file .env -f compose.production.yml -f compose.access-control.yml -f compose.staging.yml --profile bundled-db --profile ceph-readonly ps -a
python (Join-Path $DeployScripts 'check-staging-ready.py') --deployment-directory $DeploymentDirectory --ca-file ./client/staging-ca.crt --auth-user-file ./client/accounts.json
if ($LASTEXITCODE -ne 0) { throw 'TLS/auth/readiness chưa đạt' }
```

Thay tất cả đường dẫn/hostname mẫu trước khi chạy. `cluster.env` là cấu hình riêng có FSID, SSH host/user, fingerprint đã xác minh và allowlist; có thể dùng `.env.local-readonly` hiện tại **chỉ cho cùng cluster lab**. Với cluster khác, tạo cấu hình riêng từ mẫu, không sao chép FSID/key/secret lab. Điền URL exporter từ MGR active đã xác minh, không dùng endpoint standby cũ. SSH/helper cần được cài đúng trước bước này; quyền production theo [hướng dẫn SSH](rgw-console/docs/PRODUCTION_SSH.md).

Kết quả cần checker `status=PASS`, version `5.2.0-rc.1`, schema 21, `migrate`/`database-permissions` exit 0 và API/executor healthy. Checker xác minh CA/hostname, viewer, marker staging và `ready=true`; lỗi HTTP, sai cluster deployment/version/schema hoặc TLS đều trả nonzero. Nó chỉ đọc hai endpoint, không tạo collection. Tài khoản: `staging-viewer`, `staging-operator`, `staging-admin`; mật khẩu trong `client/viewer.password`, `client/operator.password`, `client/admin.password`. Checker đọc file viewer riêng, không đưa mật khẩu vào command line/log. Xem mật khẩu bằng editor, không gửi lên chat/Git. CA chỉ thử localhost, không được script cài vào trust store; browser/máy đích cần certificate được quản trị viên tin cậy, không bỏ kiểm TLS. Checker staging không kiểm chính sách CRL/OCSP của production. Không bật profile `collectors` hoặc OSDMap worker trong bộ cài RC này.

Lệnh `pull --policy always` tải cả application, PostgreSQL và Nginx đã pin; giữ `RELEASE_PULL_POLICY=never` cho bước khởi động. Checker tự lấy cổng từ deployment `.env`. `curl.exe` mặc định Windows có thể dừng với `schannel: the revocation status is unknown` khi dùng CA thử; quy trình staging trên dùng checker xác minh CA rõ ràng, không tắt kiểm chứng TLS của curl/trình duyệt. Docker Linux containers trên Windows khác với Docker Engine trên host Linux; với host Linux, phải làm [bước quyền file secret](rgw-console/deploy/README.md#quyền-file-trên-host-linux) trước khi `up`.

Trước cập nhật, gọi script từ thư mục repo đã lưu (script không được chép vào deployment):

```powershell
$BackupDirectory = Join-Path $DeploymentDirectory ('backups/backup-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
& (Join-Path $DeployScripts 'backup-production.ps1') -DeploymentDirectory $DeploymentDirectory -OutputDirectory $BackupDirectory
if (-not $?) { throw 'Backup chưa đạt; không cập nhật image' }
& (Join-Path $DeployScripts 'verify-production-backup.ps1') -BackupDirectory $BackupDirectory -OutputDirectory ($BackupDirectory + '-restore-check')
if (-not $?) { throw 'Diễn tập restore chưa đạt; không cập nhật image' }
```

Chỉ đổi digest trong `.env` sau khi backup/diễn tập restore đạt. `verify-production-backup.ps1` kiểm phục hồi vào DB/volume tạm riêng rồi dọn các đối tượng do nó tạo; **không phục hồi vào production**. Config/secret/role DB phải được sao lưu và phục hồi theo quy trình riêng. Dừng bằng đúng lệnh Compose ở trên với `down`, **không thêm `--volumes`**. File `client`/`secrets`, backup và `.env` phải giữ private. Lý thuyết và giới hạn nghiệm thu nằm ngoài README, trong [tổng hợp.md](<tổng hợp.md>) và [biên bản nghiệm thu](rgw-console/docs/PRODUCTION_ACCEPTANCE_STATUS.md).

## Cài localhost bằng cấu hình đã giữ

Cần Docker Linux containers, Compose **2.30+**, PowerShell **7.2+**, cổng 8080 trống và SSH/helper Ceph đã được cấu hình. Lấy các file triển khai từ repo:

```powershell
git clone --branch codex/console-5.1.2-rc.1 https://github.com/dangtnh7904/VDT_CLOUD_2026.git storage-lab-console-install
Set-Location storage-lab-console-install/code/rgw-console/deploy
```

Trong thư mục `deploy`, giữ hoặc chép lại bộ cấu hình riêng của chính cluster:

- `.env.local-readonly`: cấu hình đang dùng, không ghi đè bằng file mẫu.
- `config/profiles/local-lab-readonly.yaml`: profile/FSID/allowlist của cluster.
- `secrets/local_preview_database_url`: URL `postgresql://storage_lab_console:<password-URL-encoded>@storage-lab-console-local-postgres:5432/storage_lab_console`.
- `secrets/local_executor_token`: token executor tối thiểu 32 ký tự.
- SSH private key: giữ tại đường dẫn riêng trên máy, truyền vào tham số bên dưới.

Nếu đây là máy mới chưa có cấu hình, tạo `.env.local-readonly` từ [.env.local-readonly.example](rgw-console/deploy/.env.local-readonly.example), profile từ [mẫu YAML](rgw-console/deploy/config/profiles/lab.yaml.example), rồi điền FSID, SSH host/user, fingerprint đã xác minh và allowlist. Tạo password DB ngẫu nhiên tối thiểu 16 ký tự và token riêng; giữ trong secret file, không đưa lên Git. Cách chuẩn bị SSH/helper nằm trong [hướng dẫn kết nối](rgw-console/deploy/README.md#kết-nối-ceph-chỉ-đọc).

Chạy trong `deploy`; thay đường dẫn key bằng file thật của máy:

```powershell
$ErrorActionPreference = 'Stop'
$AppImage = 'dang7904/storage-lab-console@sha256:35dd7b3d32b05ae6d726b1fe6b5875d47edbcf94f0481aebc25f83d81c9f79ee'
$SshKeyFile = 'C:/path/to/your/ssh_private_key'
./start-image-readonly.ps1 -Image $AppImage -SshKeyFile $SshKeyFile -ValidateOnly
./start-image-readonly.ps1 -Image $AppImage -SshKeyFile $SshKeyFile
Invoke-RestMethod http://127.0.0.1:8080/api/ready
docker run --rm --network none $AppImage version
```

Script tự tải image và dependency, tạo database, chạy migration rồi khởi động sáu role. Nó giữ nguyên `.env`, key và các secret gốc; tạo thêm `secrets/local_postgres_password` từ URL DB. Script từ chối chạy nếu container localhost cũ vẫn tồn tại, không tự xóa dữ liệu. Không dùng script cài mới để cập nhật một deployment đang có.

Kết quả cần `ready=true`, schema **21**, phiên bản **5.1.2-rc.1**. Mở [http://127.0.0.1:8080](http://127.0.0.1:8080/), chọn daemon rồi bấm xem dữ liệu mới. Database mới có lịch sử As-is rỗng; bấm lưu As-is để tạo bộ đầu tiên. “Dữ liệu một phần” kèm cảnh báo nguồn thiếu không đồng nghĩa cài đặt thất bại.

Worker OSDMap mặc định dùng image lab/offline riêng đã pin digest, chưa được chấp thuận production. Thêm `-WithoutOsdMap` nếu không cần. Localhost chỉ bind loopback, không dùng cổng HTTP này làm public endpoint.

Nếu cài lỗi, dừng tại lỗi đầu và kiểm `docker logs storage-lab-console-local-api`, `docker logs storage-lab-console-local-executor` cùng `docker ps -a`; không xóa volume hoặc bỏ kiểm SSH fingerprint để thử lại. Không đưa log chứa thông tin kết nối lên nơi công khai.

## Cài bộ riêng có TLS

## 1. Chuẩn bị

- Docker Engine hoặc Docker Desktop ở chế độ Linux containers, Docker Compose v2.
- Với hướng dẫn Windows bên dưới: PowerShell 7.2+ và OpenSSL trên PATH.
- Thư mục [rgw-console/deploy](rgw-console/deploy/) chứa Compose, script chuẩn bị, mẫu cấu hình và Nginx.
- Chọn thư mục triển khai, tên project và cổng riêng. Không ghi đè `.env`, secret hoặc volume của hệ thống đang chạy.

## 2. Tải image

Chạy từ thư mục `code`:

```powershell
$ErrorActionPreference = 'Stop'
$AppImage = 'dang7904/storage-lab-console@sha256:35dd7b3d32b05ae6d726b1fe6b5875d47edbcf94f0481aebc25f83d81c9f79ee'
docker pull --platform linux/amd64 $AppImage
if ($LASTEXITCODE -ne 0) { throw 'Không tải được image' }
docker run --rm --network none $AppImage version
if ($LASTEXITCODE -ne 0) { throw 'Không kiểm tra được phiên bản image' }
```

Kết quả phải là `5.1.2-rc.1`. Dùng ref phát hành đã kiểm; không thay bằng `latest`.

## 3. Tạo bộ cài thử riêng

Ví dụ dùng project mới, thư mục mới và cổng 8445; không thay localhost 8080 đang có:

```powershell
Set-Location ./rgw-console/deploy
$DeploymentDirectory = 'D:/deploy/storage-lab-console-demo'
./prepare-production-test.ps1 -ApplicationImage $AppImage -OutputDirectory $DeploymentDirectory -ProjectName storage-lab-console-demo -Port 8445
if ($LASTEXITCODE -ne 0) { throw 'Không tạo được bộ cài thử' }
Set-Location $DeploymentDirectory
```

Script tạo `.env`, profile, secret, Compose và certificate tự ký 14 ngày. Nó từ chối ghi đè thư mục đã có. Certificate này chỉ dành cho thử localhost; khi cài vào hệ thống thật phải thay bằng certificate tin cậy, domain/CORS và cấu hình riêng theo [hướng dẫn triển khai](rgw-console/deploy/README.md#cài-vào-hệ-thống-thật).

## 4. Tải dependency và khởi động

Trong thư mục triển khai vừa tạo:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose không hợp lệ' }
$RequiredImages = docker compose --env-file .env -f compose.production.yml --profile bundled-db config --images | Sort-Object -Unique
foreach ($RequiredImage in $RequiredImages) {
    docker pull --platform linux/amd64 $RequiredImage
    if ($LASTEXITCODE -ne 0) { throw "Không tải được dependency: $RequiredImage" }
}
docker compose --env-file .env -f compose.production.yml --profile bundled-db up -d
if ($LASTEXITCODE -ne 0) { throw 'Không khởi động được bộ cài' }
docker compose --env-file .env -f compose.production.yml --profile bundled-db ps -a
```

`migrate` và `database-permissions` kết thúc exit 0 là bình thường. API phải healthy. Bộ cài mới ở bước này chưa kết nối Ceph.

## 5. Đăng nhập và kiểm tra cài đặt

Mở [https://localhost:8445](https://localhost:8445/). Tài khoản là `console-admin`; lấy mật khẩu tại `secrets/console_password` trong thư mục triển khai bằng trình soạn thảo riêng. Không gửi file secret, không đưa mật khẩu vào Git hoặc ảnh chụp.

Kiểm readiness với certificate của đúng bộ cài; `curl` hỏi mật khẩu nên không đưa secret vào command line:

```powershell
curl.exe --cacert ./secrets/tls_certificate.pem --user console-admin https://localhost:8445/api/ready
if ($LASTEXITCODE -ne 0) { throw 'TLS hoặc readiness chưa đạt; dừng cài đặt và kiểm cấu hình' }
```

Kết quả cần `ready=true`. Không bỏ kiểm certificate. Với certificate do CA của hệ thống tin cậy cấp, dùng trust store hoặc CA đã được quản trị viên xác minh.

## 6. Kết nối cluster Ceph

Làm theo [cấu hình SSH/profile/helper](rgw-console/deploy/README.md#kết-nối-ceph-chỉ-đọc), rồi bật các role đọc:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors config --quiet
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors up -d
```

Giữ `CONSOLE_READ_ONLY=true` và `UPGRADE_MUTATIONS_ENABLED=false`. Không sao chép SSH key/FSID/profile của localhost hiện có sang cluster khác. Worker OSDMap không thuộc bộ cài cơ bản; nếu cần cho lab, xem [hướng dẫn worker riêng](rgw-console/docs/OSDMAP_PREVIEW.md).

## 7. Cập nhật hoặc dừng

Trước cập nhật, [backup DB/evidence/state và kiểm phục hồi](rgw-console/deploy/README.md#backup-cập-nhật-và-dừng). Đổi digest trong `.env`, tải image mới, chạy lại Compose và kiểm readiness. Không xóa database hoặc volume để cập nhật.

Dừng bộ cài mà giữ dữ liệu:

```powershell
docker compose --env-file .env -f compose.production.yml --profile bundled-db --profile ceph-readonly --profile collectors down
```

Không thêm `--volumes`. Cài Linux, database ngoài, TLS thật hoặc chuyển image offline: xem [README triển khai chi tiết](rgw-console/deploy/README.md).
