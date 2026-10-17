# Cài đặt Storage Lab Console từ Docker image

README này chỉ hướng dẫn cài đặt, cấu hình và cập nhật image. Phần giải thích hệ thống nằm trong [tổng hợp.md](<tổng hợp.md>).

Hướng dẫn dùng bản Docker Hub `5.1.1-rc.1`, Linux AMD64. Bản `5.1.2-preview.1` trên localhost hiện tại chưa được đăng Hub; không dùng tag preview đó để cài máy khác. Không cần build lại source.

## 1. Chuẩn bị

- Docker Engine hoặc Docker Desktop ở chế độ Linux containers, Docker Compose v2.
- Với hướng dẫn Windows bên dưới: PowerShell 7.2+ và OpenSSL trên PATH.
- Thư mục [rgw-console/deploy](rgw-console/deploy/) chứa Compose, script chuẩn bị, mẫu cấu hình và Nginx.
- Chọn thư mục triển khai, tên project và cổng riêng. Không ghi đè `.env`, secret hoặc volume của hệ thống đang chạy.

## 2. Tải image

Chạy từ thư mục `code`:

```powershell
$ErrorActionPreference = 'Stop'
$AppImage = 'dang7904/storage-lab-console@sha256:49f5284d27fd4defe2e2804e3b4eb06eaa3ac19352026622de3eae6c417fbe1f'
docker pull --platform linux/amd64 $AppImage
if ($LASTEXITCODE -ne 0) { throw 'Không tải được image' }
docker run --rm --network none $AppImage version
if ($LASTEXITCODE -ne 0) { throw 'Không kiểm tra được phiên bản image' }
```

Kết quả phải là `5.1.1-rc.1`. Luôn pin digest; không thay bằng `latest`.

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

Kiểm readiness bằng PowerShell; bỏ kiểm certificate chỉ trong bộ cài thử tự ký này:

```powershell
$DemoPassword = (Get-Content -LiteralPath secrets/console_password -Raw).Trim()
$DemoCredential = [PSCredential]::new('console-admin', (ConvertTo-SecureString $DemoPassword -AsPlainText -Force))
try {
    Invoke-RestMethod -Uri https://localhost:8445/api/ready -Authentication Basic -Credential $DemoCredential -SkipCertificateCheck
} finally {
    Remove-Variable DemoPassword, DemoCredential
}
```

Kết quả cần `ready=true`. Với certificate tin cậy, bỏ `-SkipCertificateCheck`.

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
