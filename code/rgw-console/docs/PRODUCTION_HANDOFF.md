# Bàn giao để nghiệm thu production — Console chỉ đọc

Cập nhật ngày 15/10/2026 (UTC+7). Tài liệu này chỉ dẫn các việc cần người vận hành/quản trị viên thực hiện; không phải chứng nhận production. Các lệnh có giá trị `REPLACE_*` hoặc đường dẫn mẫu phải được thay và rà soát trước khi chạy. Không gửi private key, password, token, keyring, `.env` hay dump DB lên chat/Git.

Phạm vi nghiệm thu đầu tiên: xem/xuất chỉ số mới, thu/lưu/xuất As-is, lịch sử, xóa mềm/khôi phục và so sánh cùng loại daemon. Không benchmark, nâng cấp/restart daemon Ceph, terminal/RBD/ghi object hoặc nghiệm thu OSDMap worker.

Các lệnh có đường dẫn tương đối `./deploy/` hoặc `./scripts/` bên dưới chạy từ **`code/rgw-console` của repo được duyệt**. Lệnh Compose chạy từ deployment directory riêng như từng mục ghi; SSH/curl chạy từ máy triển khai có key/trust đã xác minh. Không chạy command có placeholder nguyên trạng.

## 1. Phần đã làm và phần bạn cần làm

| Hạng mục | Bằng chứng hiện có | Điều còn phải làm trên hệ thống đích |
| --- | --- | --- |
| Core Console | 446 backend, 42 executor, 33 frontend; staging 40/40 yêu cầu, p95 25,781 giây; kiểm quyền viewer/operator/admin | UAT bằng trình duyệt, tải đỉnh và thời gian kiểm do đơn vị duyệt |
| Phục hồi lỗi | API/DB/executor staging phục hồi; SSH trên socket kiểm riêng đã thử inbound stall/drop và reconnect; collection/audit không đổi | Chậm xử lý Ceph, fault qua toàn API, hủy/remote process và tải dài trên host thực |
| Backup/restore | 6 As-is/audit; fixture evidence không rỗng có checksum/liên kết DB–tệp; 49 ca kiểm manifest/recovery | Restore dữ liệu thật, cấu hình, secret và role trên môi trường riêng; đo toàn bộ RPO/RTO |
| Đóng gói | RC Linux AMD64 đã lên Docker Hub; SBOM/provenance khớp source/subject; lần scan RC có 0 finding | Chính sách signer, chữ ký, kiểm lại lỗ hổng theo thời điểm nhận và phê duyệt |
| SSH/CephX | Guard/source và hướng dẫn cài có sẵn | Admin cài account/key/CephX riêng; kiểm mọi action và restriction trên cluster đích |
| HTTPS/secret | Staging kiểm CA/hostname riêng; DB runtime role hạn chế | Domain/certificate tin cậy, firewall, quyền secret trên Linux, chính sách CRL/OCSP |
| Vận hành | Domain/readiness checker, manifest bản sao cấu hình; HTTPS sender nội bộ thử ALERT/RECOVERY 204 + dedup/CA sai; scheduler templates | Scheduler host thực, thông báo tới người nhận, offsite/encryption/retention được duyệt và kiểm đầu-cuối |

Biên bản chi tiết: [PRODUCTION_ACCEPTANCE_STATUS.md](PRODUCTION_ACCEPTANCE_STATUS.md). Quy trình: [PRODUCTION_OPERATIONS.md](PRODUCTION_OPERATIONS.md). Mỗi kết quả staging vẫn là bằng chứng staging, không chuyển thành PASS của host đích.

Bạn đã yêu cầu không xử lý dung lượng máy hiện tại: giữ nguyên image/container/DB/volume/`.env`; không prune, compact, xóa hoặc di chuyển đĩa. Cảnh báo đo trước đó C 90,40% và D 86,26% so với ngưỡng đề xuất 85% được giữ trong biên bản, không hạ ngưỡng để tạo PASS. Đơn vị phải quyết định đủ dung lượng trên host đích hoặc chấp nhận ngoại lệ có thời hạn; chưa có quyết định thì gate dung lượng còn HOLD.

## 2. Chốt bộ phát hành và đầu vào không bí mật

```text
Application: 5.2.0-rc.1, Linux AMD64, schema 21
Image: dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342
AMD64 manifest: sha256:38609eb1c2dc9a83390d347139a8d3de2179556f644ccad721568faf5b407526
Application source: d1d43a28a644f8d079dec48d3c280d8377525ea8
Repository branch: codex/console-production-readonly
```

Commit `233339f` là mốc tài liệu/công cụ vận hành trước tài liệu này, không phải source binary của RC. Khi bàn giao, ghi full commit mới thực tế lấy bằng `git rev-parse HEAD`; không sửa source label của image thành commit tài liệu mới. Release hiện tại chưa có chữ ký được nghiệm thu.

Người phụ trách ghi vào biên bản: host Linux AMD64; Docker/Compose/Python/PowerShell/OpenSSH/Ceph version; domain/cổng/IP management; FSID; daemon/OSD allowlist; endpoint Prometheus đã xác minh; chủ vận hành/DBA/SSH admin/signer/người nhận cảnh báo; maintenance window. Chọn một thư mục deployment và `COMPOSE_PROJECT_NAME` mới, không trùng localhost 8080 hoặc staging hiện có.

Cài cơ bản theo [deploy/README.md](../deploy/README.md), dùng `compose.production.yml` cùng `compose.access-control.yml` để phân quyền. Template [.env.production.example](../deploy/.env.production.example) và [.env.release.example](../deploy/.env.release.example) hiện đã pin application bằng digest RC ở trên; việc có digest đúng không tự bật phân quyền/TLS hoặc nghiệm thu quyền trên cluster. Dùng bộ production + access-control cho phạm vi này, không thay bằng Compose release/lab cũ. Đối chiếu ref với release manifest khi cài; không dùng `latest`, không bật profile `collectors` hoặc worker OSDMap trong nghiệm thu core này.

## 3. Admin cluster: cài SSH/CephX quyền tối thiểu

Thực hiện đầy đủ [PRODUCTION_SSH.md](PRODUCTION_SSH.md), theo thứ tự dưới đây. Đây là các bước admin phải làm, không phải kết quả đã được Console tự cài:

1. Giữ một phiên quản trị độc lập; kiểm account/group/path đã tồn tại. Nếu đã có consumer, dừng để rà soát, không ghi đè hoặc sửa quyền/caps đệ quy.
2. Tạo Unix account/group riêng `storage-lab-console`, không thuộc sudo/wheel/docker/lxd; tạo key SSH riêng bằng quy trình secret của đơn vị. Executor chưa hỗ trợ passphrase/SSH agent: dùng phương án được duyệt, không bỏ passphrase của key admin đang có.
3. Tạo identity mới `client.storage-lab-console`, MON `allow r` và các MGR command đọc đúng phiên bản theo guide. Lưu keyring thẳng vào file private bằng `ceph ... -o`, không in secret. Không cấp `allow *`, `rw/rwx`, auth/upgrade/pool/object-write hoặc fallback `client.admin`. Mẫu caps MGR chưa được nghiệm thu trên cluster đích.
4. Cài guard, helper, conf, policy và authorized keys root-owned vào đúng đường dẫn trong guide. Policy chứa FSID, OSD cho phép và SHA-256 helper; đối chiếu helper với source/image được duyệt, không lấy helper writable trong home tài khoản lab.
5. Cài forced-command SSH restriction, chặn password/TTY/SFTP/forwarding/user-rc/môi trường loader. Chạy `sshd -t` và `sshd -T -C ...`; chỉ reload khi cấu hình hiệu lực đạt và còn phiên admin để phục hồi. Không dùng sudo-Ceph/file-output để vượt quyền hệ điều hành.
6. Pin fingerprint SSH qua kênh tin cậy. Tạo secret riêng của deployment mới; đặt `RBD_SSH_USER=storage-lab-console`, FSID/allowlist/path helper khớp policy, giữ `CONSOLE_READ_ONLY=true`, `UPGRADE_MUTATIONS_ENABLED=false`, `RBD_TERMINAL_ENABLED=false`, `LAB_ALLOW_WRITE=false`.

Từ máy triển khai, thay key/host/OSD mẫu và dùng known-hosts đã xác minh:

```sh
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'ceph fsid'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'sudo -n ceph status --format=json'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'python3 /opt/storage-lab/collect_osd.py --osd 2 --sudo-ceph --timeout 45'
ssh -T -i /secure/path/storage-lab-console-production -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes storage-lab-console@REPLACE_HOST 'true'
```

Ba lượt đầu phải đọc FSID/dữ liệu đúng và OSD nằm trong policy. Guard bỏ framing `sudo -n`/`--sudo-ceph`, không chạy sudo. Lượt `true` phải trả exit 126/`SSH_COMMAND_REJECTED`. Tiếp tục kiểm tất cả fixed inventory actions, caps, SFTP/PTY/forwarding và quyền file theo guide; chỉ dùng negative command vô hại, không gửi lệnh ghi Ceph thật. Fault FSID/checksum/output/deadline chạy trên fixture/host staging riêng, không sửa FSID của cluster thật. Lưu mã lỗi, checksum và fingerprint, không lưu keyring.

Chỉ đánh dấu gate SSH PASS sau các kiểm trên host đích. Nếu một action bắt buộc thiếu caps hoặc restriction chưa đạt, giữ BLOCKED và chưa mở executor production; không đổi sang key/account lab để đạt PASS.

## 4. Admin host: domain, TLS, firewall và secret

1. Cấp domain quản trị riêng trỏ đúng ingress, certificate có SAN domain và chain tin cậy trên máy người dùng. Thay hai secret TLS trong deployment mới; giữ private key private, không copy CA thử `localhost` vào production. Chốt gia hạn/cảnh báo hết hạn và chính sách revocation với PKI của đơn vị.
2. Điền `CORS_ORIGINS=https://REPLACE_DOMAIN:REPLACE_PORT` đúng origin thực; đặt `APP_DEPLOYMENT_SCOPE=production` cho deployment cuối. Giữ bind loopback nếu đi qua reverse proxy quản trị; nếu mở IP management thì chỉ mở IP/cổng đã được firewall phê duyệt, không mở internet chung.
3. Firewall chỉ cho CIDR quản trị tới ingress; SSH tới management host từ nguồn executor đã xác minh; DB chỉ cho network/consumer cần thiết; outbound exporter/PKI/registry theo chính sách. Không publish cổng API/executor/PostgreSQL ra mạng người dùng. Thử từ máy được phép và một máy không được phép; lưu kết quả, không chỉ xem rules.
4. Kiểm quyền file host và khả năng `test -r` trong container, không `cat` secret. Quy trình numeric UID chỉ áp dụng Docker rootful không remap; rootless/user-namespace/Windows phải kiểm mapping thực, không dùng `chmod 777`.

| Secret | Consumer/UID trong bộ image đã pin | Quyền cần kiểm |
| --- | --- | --- |
| `database_url`, `console_users.json`, `executor_token` | API/role đọc, UID 10001 | File private, chỉ đọc; API không mount migration/admin password |
| `migration_database_url`, `database_runtime_password` | Job migrate/provision, UID 10001 | Secret riêng, không cấp cho API |
| `ssh_private_key`, `ssh_known_hosts` | Executor, UID 10001 | SSH key chỉ vào executor; fingerprint/FSID bắt buộc |
| `tls_private_key.pem`, certificate chain | Ingress, UID 101 | Key không world-readable; chain đọc được |
| `postgres_password` | PostgreSQL Alpine đã pin, UID 70 | File private; khác password role runtime |

Lệnh metadata/khởi động/kiểm secret có trong [quyền file Linux](../deploy/README.md#quyền-file-trên-host-linux). Compose khai báo uid/gid/mode không tự sửa quyền bind-mounted file. Không dùng kết quả mode 0777 trên Windows staging làm bằng chứng quyền Linux production.

Kiểm HTTPS trên domain bằng curl của host có trust store/certificate đã được PKI duyệt, mật khẩu được hỏi tương tác:

```sh
curl --fail --show-error --user REPLACE_PERSONAL_VIEWER https://REPLACE_DOMAIN:REPLACE_PORT/api/runtime-config
curl --fail --show-error --user REPLACE_PERSONAL_VIEWER https://REPLACE_DOMAIN:REPLACE_PORT/api/ready
```

Với CA nội bộ, dùng `--cacert /secure/path/approved-ca-chain.pem`. Nếu thử ingress loopback với certificate chỉ có SAN domain, dùng `--resolve REPLACE_DOMAIN:REPLACE_PORT:127.0.0.1` cùng URL domain: vẫn kiểm hostname/CA thật. Không dùng `-k`, bỏ revocation, chấp nhận cảnh báo browser hay tắt kiểm hostname. Readiness cần schema 21, frontend/executor/DB ready; `migrate` và `database-permissions` exit 0.

`check-staging-ready.py` chỉ kiểm localhost + marker staging; không dùng để chứng nhận domain/PKI đích. Browser UAT vẫn cần đăng nhập và tải file trên máy người dùng thật.

Checker [check-production-ready.py](../deploy/check-production-ready.py) riêng kiểm domain khai báo trong `CORS_ORIGINS`, marker production, viewer, read-only/features và readiness, dùng CA/hostname thật và không proxy/redirect:

```powershell
python ./deploy/check-production-ready.py --deployment-directory 'REPLACE_DEPLOYMENT_DIRECTORY' --base-url https://REPLACE_DOMAIN:REPLACE_PORT --ca-file 'REPLACE_APPROVED_CA_CHAIN_FILE' --auth-user-file 'REPLACE_PRIVATE_VIEWER_ACCOUNTS_FILE' --expected-version 5.2.0-rc.1 --expected-schema 21 --report 'REPLACE_NEW_PRIVATE_READINESS_REPORT.json'
```

Chạy từ `code/rgw-console`; CA file là chain được đơn vị duyệt. Tài khoản client giữ username và `password_file` private, không phải server JSON chứa hash. Kết quả `status=PASS` của checker không kiểm chữ ký image/quyền SSH/revocation policy và không thay biên bản cuối.

## 5. Người vận hành: tài khoản cá nhân và rotation

Mỗi người dùng một username; không dùng chung `staging-admin` ở production. File `secrets/console_users.json` có schema version 1, tối đa 128 username duy nhất, chỉ các trường `username`, `role`, `password_hash`. Hash theo `pbkdf2_sha256`, 600.000–2.000.000 iterations, salt 16–64 byte, digest 32 byte; generator staging hiện dùng 600.000/32/32. Username dùng ký tự chữ/số và `_.@-`.

| Vai trò | Cho phép |
| --- | --- |
| viewer | Xem/xuất mới, đọc lịch sử, so sánh/xuất |
| operator | Thêm quyền lưu As-is |
| admin | Thêm quyền xóa mềm/khôi phục collection |

Tất cả role vẫn chỉ đọc Ceph. Web admin không có Docker socket, SSH admin hoặc DB superuser. Audit phải nhận diện username thực; không lấy actor từ header client.

Quy trình rotation do người quản lý secret thực hiện:

1. Trong maintenance window, giữ bản trước private và một admin còn hiệu lực; tạo password mới trong password manager của đơn vị, sinh hash theo định dạng trên bằng công cụ được duyệt. Không nhập password vào command line, Git hoặc ticket.
2. Tạo bản `console_users.json` tiếp theo ở khu vực private; giữ tài khoản/role còn dùng, thay hash của đúng username. Thu hồi user bằng bỏ đúng record, không để file rỗng hoặc chỉ còn record sai định dạng. Không đổi audit username của dữ liệu cũ.
3. Kiểm JSON/schema, permission/mapping và cập nhật đúng secret file của deployment trong cửa sổ được duyệt. App đọc file khi khởi tạo settings, không hot-reload: recreate các service đang chạy có mount account file bằng đúng Compose overlays/profiles, không xóa volume.
4. Kiểm password cũ bị 401, password mới đúng role; viewer không lưu/xóa, operator không xóa, admin xóa mềm/khôi phục được một collection test đã định danh. Kiểm audit đúng người thao tác. Nếu có failure, quay về bản secret trước và recreate consumer, không nới quyền/hash validation.
5. Với executor token, đổi đồng bộ API/executor/capacity consumer trong maintenance window; với SSH key, admin cài public key mới có restriction trước, kiểm key mới rồi mới thu hồi đúng key cũ. Không chỉ đổi `.env` hoặc tái dùng secret giữa các môi trường.

Nếu chưa có công cụ tạo hash của đơn vị, admin có thể tạo **bản JSON mới, chưa áp dụng** bằng PowerShell 7.2+ sau khi rà đoạn dưới. Chạy trong thư mục private; nó hỏi password tương tác và chỉ ghi hash, không xuất password. Đây là ví dụ rotate đúng một account đã có, không tạo/đổi role hay ghi đè file đang chạy:

```powershell
$ErrorActionPreference = 'Stop'
$CurrentUsers = '/secure/REPLACE_PRIVATE_COPY/console_users.json'
$NextUsers = '/secure/REPLACE_PRIVATE_COPY/console_users.next.json'
$Username = 'REPLACE_EXISTING_PERSONAL_USERNAME'
if (Test-Path -LiteralPath $NextUsers) { throw 'File tiếp theo đã tồn tại; không ghi đè' }
$Document = Get-Content -LiteralPath $CurrentUsers -Raw | ConvertFrom-Json
$Record = @($Document.users | Where-Object { $_.username -ceq $Username })
if ($Document.version -ne 1 -or $Record.Count -ne 1) { throw 'Không tìm được đúng một account version 1' }
$SecurePassword = Read-Host 'Password mới từ password manager (không hiện)' -AsSecureString
$Password = ([pscredential]::new($Username, $SecurePassword)).GetNetworkCredential().Password
try {
    if ($Password.Length -lt 32 -or $Password.Length -gt 1024 -or $Password -match '[\r\n]') { throw 'Dùng secret mới 32–1024 ký tự, một dòng' }
    $Salt = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    $Hash = [Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2([Text.Encoding]::UTF8.GetBytes($Password), $Salt, 600000, [Security.Cryptography.HashAlgorithmName]::SHA256, 32)
    $Record[0].password_hash = 'pbkdf2_sha256$600000$' + [Convert]::ToBase64String($Salt) + '$' + [Convert]::ToBase64String($Hash)
    $Bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Document | ConvertTo-Json -Depth 10) + "`n")
    $Stream = [IO.File]::Open($NextUsers, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $Stream.Write($Bytes, 0, $Bytes.Length) } finally { $Stream.Dispose() }
} finally { $Password = $null; $SecurePassword = $null }
```

Đặt quyền file mới theo mapping đã kiểm, rà toàn bộ JSON/role trước khi quản trị viên cập nhật secret thật. Từ đúng deployment directory của core, recreate consumer trong maintenance window (không chạy migration lại để rotate web password):

```sh
docker compose --env-file .env -f compose.production.yml -f compose.access-control.yml --profile bundled-db --profile ceph-readonly up -d --force-recreate --no-deps api capacity-collector
```

Nếu deployment có overlay riêng hoặc DB ngoài, phải dùng đúng overlays/profiles đã duyệt thay ví dụ; nếu bật consumer khác có `console_users` thì recreate consumer đó nữa. Kiểm credential cũ/mới và readiness trước mở lại truy cập. Đoạn tạo hash không tự kiểm full schema/permission, không thay quy trình secret manager hay thao tác activate của admin.

Đổi password của PostgreSQL đã có không thực hiện bằng cách chỉ sửa `postgres_password`: Docker init chỉ dùng file này khi tạo DB mới. DBA phải rotate đúng role qua quy trình DB riêng rồi đồng bộ secret consumer; không recreate/xóa data volume để buộc password mới có hiệu lực.

## 6. Chốt metric, tải và bài kiểm nghiệm thu

Chủ hệ thống ký phạm vi gồm: FSID, daemon ID/loại/pool, metric ID bắt buộc, nguồn/đơn vị, cache/scrape interval, cửa sổ đo, metric chưa hỗ trợ và giới hạn được chấp nhận. Hiện staging đã kiểm `osd.total_iops` và `osd.utilization_percent`; không tự gọi CPU/RAM/process/network/percentile thiếu là đạt.

Exporter phải khớp MGR service đọc từ cluster đã xác minh FSID hoặc có series FSID đúng. Xác minh overrides của MGR active/failover; giữ `PERFORMANCE_LIVE_MIN_WINDOW_SECONDS` ít nhất bằng interval exporter thực (mẫu hiện 15 giây). Mỗi nút xem/xuất đọc lại nguồn; partial/timeout/HTTP lỗi/sai scope không được biến thành số 0 hoặc gắn timestamp mới cho dữ liệu cũ.

Chỉ chạy harness tải ở deployment **staging loopback riêng** đã có marker, CA và account file; không sửa code bỏ rào target để đánh vào production:

```powershell
python ./scripts/production_acceptance.py --base-url https://localhost:REPLACE_STAGING_PORT --ca-file 'REPLACE_PRIVATE_CA_FILE' --staging-project REPLACE_STAGING_PROJECT --auth-user-file 'REPLACE_PRIVATE_ACCOUNTS_FILE' --expected-fsid REPLACE_FSID --daemon-key mon.REPLACE_MON_ID --daemon-key osd.REPLACE_OSD_ID --required-metric osd.total_iops --required-metric osd.utilization_percent --comparison-daemon-type osd --load-workers 2 --load-iterations 20 --max-p95-seconds 60 --max-error-ratio 0 --max-busy-ratio 0 --allow-staging-metadata-writes --test-client-abort --report 'REPLACE_NEW_PRIVATE_REPORT.json'
```

Chạy từ `code/rgw-console`, thay toàn bộ mẫu bằng giá trị được duyệt. Flag metadata writes tạo hai As-is ghi chú validation-only, không nâng Ceph; nếu không cho tạo, bỏ flag nhưng kết quả chủ đích là PARTIAL do phần lưu/so sánh NOT_RUN. Các ngưỡng trong ví dụ là đề xuất, không tự thành SLO được ký. Biên bản cần tải đỉnh/ngày, thời gian soak, p95/p99, error/429 budget, deep OSD budget và thời gian phục hồi do đơn vị chốt.

Fault API/DB/executor theo [operations](PRODUCTION_OPERATIONS.md) chỉ đúng ID project staging. SSH chậm/mất kết nối chạy trên host/fixture riêng có deadline, số process và tài nguyên đo thực. App trả fresh sau client abort chưa chứng minh process remote đã bị kill; giữ gate này mở tới khi có bằng chứng.

UAT tại domain đích: chọn nhiều daemon, xem/xuất mới với timestamp/scope; lưu trước/trong/sau nhưng không kích hoạt upgrade; filter ngày/loại trong bộ mixed-daemon; so sánh hai As-is cùng loại, từ chối khác loại; xóa mềm/khôi phục; tải JSON và đối chiếu checksum/schema. Không dùng HTTP API export thay cho xác nhận browser tải tệp thành công.

## 7. Backup, cấu hình/role recovery và RPO/RTO

Đơn vị quyết định tần suất, maintenance window, nơi lưu offsite, encryption/khóa recovery, retention, owner và RPO/RTO. Đề xuất ban đầu daily 02:00, backup age 26 giờ, RPO 24 giờ, RTO 30 phút chưa được duyệt. Restore tệp/DB khoảng 11–13 giây ở staging không phải RTO toàn hệ thống.

Backup/rehearsal hiện có (PowerShell 7.2+, dùng đường dẫn mới):

```powershell
./deploy/backup-production.ps1 -DeploymentDirectory 'REPLACE_DEPLOYMENT_DIRECTORY' -OutputDirectory 'REPLACE_NEW_PRIVATE_BACKUP_DIRECTORY'
if (-not $?) { throw 'Backup chưa đạt' }
./deploy/verify-production-backup.ps1 -BackupDirectory 'REPLACE_PRIVATE_BACKUP_DIRECTORY' -OutputDirectory 'REPLACE_NEW_PRIVATE_RESTORE_REPORT_DIRECTORY'
if (-not $?) { throw 'Restore/checksum chưa đạt' }
```

Backup tạm dừng writer đúng project, cần maintenance window. Rehearsal tạo DB/volume riêng rồi dọn đúng đối tượng do lượt kiểm tạo; không restore đè production. Chỉ thêm `-RequireEvidence` khi bộ backup thật có evidence registered/non-empty cần buộc kiểm; core As-is mới có payload trong DB nhưng evidence filesystem có thể rỗng hợp lệ.

Phục hồi **cả dịch vụ** trên host/project riêng còn cần admin/DBA:

1. Giữ cấu hình non-secret đúng revision (Compose/nginx/profile/`.env` đã rà không secret), image/dependency digest, schema, mapping UID/GID, fingerprint/FSID và inventory secret/DB role. Secret thật nằm trong secret manager/backup mã hóa riêng; lưu phiên bản để đồng bộ, không ghép secret vào bundle công khai.
2. Trên host riêng, provision database và migration/runtime role từ quy trình DBA; restore dump bằng role được phép, áp lại runtime grants theo `configure-database` của image/schema đã duyệt. Không cấp owner/superuser hoặc sửa PUBLIC của DB dùng chung; chỉ database riêng cho Console.
3. Restore evidence/executor-state vào volume mới đúng ownership và checksum; phục hồi secret bằng kênh private, kiểm conf/profile/FSID và TLS trước khi bật API/executor. Tên project/cổng mới, không nối nhầm volume live. Script rehearsal hiện không tự giữ lại một deployment sẵn để phục vụ người dùng.
4. Khởi động API và đọc history/export/audit qua HTTPS bằng runtime role; đối chiếu ID, canonical payload SHA-256, soft-delete, actor/count, artifact checksum và linkage. Tạo thêm một collection validation riêng để kiểm quyền lưu sau recovery nếu bài kiểm được duyệt.
5. Đo từ thời điểm sự cố đến lúc dịch vụ thực dùng được (RTO), đối chiếu checkpoint cuối và lượng dữ liệu mất (RPO). Ghi phần không khôi phục được; không kết luận từ tuổi backup/checksum đơn lẻ.

Công cụ [production_recovery_config.py](../scripts/production_recovery_config.py) tạo manifest/checksum từ **bản sao private** đã được người vận hành chuẩn bị, không backup/copy/encrypt secret, không gọi Docker/Ceph và không restore role. Không trỏ vào deployment live. Nó kiểm tập file cố định, template Compose/nginx đã rà và đối chiếu bản phục hồi riêng với manifest đã pin hash:

```powershell
python ./scripts/production_recovery_config.py --deployment-directory 'REPLACE_PRIVATE_SOURCE_COPY' --confirm-private-copy --expected-project REPLACE_PROJECT --expected-instance REPLACE_INSTANCE --expected-image 'dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342' --report 'REPLACE_NEW_PRIVATE_SOURCE_MANIFEST.json'
Get-FileHash -LiteralPath 'REPLACE_PRIVATE_SOURCE_MANIFEST.json' -Algorithm SHA256
python ./scripts/production_recovery_config.py --restored-directory 'REPLACE_SEPARATE_PRIVATE_RESTORED_COPY' --confirm-private-copy --expected-project REPLACE_PROJECT --expected-instance REPLACE_INSTANCE --expected-image 'dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342' --reference-manifest 'REPLACE_PRIVATE_SOURCE_MANIFEST.json' --reference-manifest-sha256 REPLACE_TRUSTED_LOWERCASE_SHA256 --report 'REPLACE_NEW_PRIVATE_RESTORED_MANIFEST_REPORT.json'
```

Report nằm **ngoài** cả hai bản sao, thư mục cha phải tồn tại, file chưa có; lưu hash manifest qua kênh tin cậy độc lập. Cả bản source và bản restored phải cùng identity/file content khi kiểm; chỉ chỉnh project/cổng cho diễn tập chạy riêng sau checkpoint này, ghi change đã duyệt. Có thêm overlay/custom nginx ngoài template thì cần rà và công cụ tương ứng, không ép qua bằng bỏ file quan trọng. Hash metadata cũng giữ private; nó không là chữ ký, không xác minh chain/key-match/TLS expiry, secret UID/ACL, role hay RPO/RTO. Không có mật khẩu/khóa offsite recoverable thì gate recovery vẫn BLOCKED.

## 8. Scheduler và cảnh báo — chỉ bật sau phê duyệt

Wrapper [run-production-maintenance.ps1](../deploy/run-production-maintenance.ps1) hỗ trợ domain thật bằng `-BaseUrl`, config receiver đã duyệt bằng `-AlertConfigFile` và private state bằng `-AlertStateFile`. Chạy lượt riêng trước khi đăng ký lịch; hai ví dụ dưới gửi thông báo thật, chỉ thực hiện sau khi được phép:

```powershell
./deploy/run-production-maintenance.ps1 -Mode Check -DeploymentDirectory 'REPLACE_DEPLOYMENT_DIRECTORY' -BackupRoot 'REPLACE_BACKUP_ROOT' -Python 'REPLACE_PYTHON_EXECUTABLE' -BaseUrl https://REPLACE_DOMAIN:REPLACE_PORT -CaFile 'REPLACE_APPROVED_CA_CHAIN_FILE' -AuthUserFile 'REPLACE_PRIVATE_VIEWER_ACCOUNTS_FILE' -AlertConfigFile 'REPLACE_PRIVATE_ALERT_CONFIG.json' -AlertStateFile 'REPLACE_PRIVATE_ALERT_STATE_BASE.json'
./deploy/run-production-maintenance.ps1 -Mode Backup -DeploymentDirectory 'REPLACE_DEPLOYMENT_DIRECTORY' -BackupRoot 'REPLACE_BACKUP_ROOT' -Python 'REPLACE_PYTHON_EXECUTABLE' -AlertConfigFile 'REPLACE_PRIVATE_ALERT_CONFIG.json' -AlertStateFile 'REPLACE_PRIVATE_ALERT_STATE_BASE.json'
```

Muốn chỉ kiểm local report/chưa gửi, bỏ cả hai `-AlertConfigFile`/`-AlertStateFile`. Check lưu JSON và vẫn gọi sender nếu probe trả exit 2; Backup tạo report `PRODUCTION_MAINTENANCE_BACKUP` PASS/ALERT và gọi cùng sender. Sau gửi, wrapper vẫn trả lỗi/nonzero khi check/backup có alert hoặc delivery thất bại; không đổi alert thành PASS. Tham số `-AlertStateFile` là tên nền: wrapper tạo state riêng `<tên-nền>.check.json` và `<tên-nền>.backup.json` trong cùng thư mục private để backup PASS không recover nhầm cảnh báo dung lượng của Check. Không dùng flag demo/loopback-test trong wrapper production.

Probe [production_ops.py](../scripts/production_ops.py) không sửa/restart Ceph. Nó nhận diện named-volume/container rồi đo filesystem; trên Docker Desktop cần thêm `-AdditionalHostStoragePath 'REPLACE_VERIFIED_DOCKER_DISK_PARENT'` để kiểm đĩa vật lý chứa VHD. Không đo inode/quota riêng và không cộng dung lượng các volume chung filesystem.

Với certificate chỉ có SAN domain, sử dụng `--base-url` của probe production, origin phải nằm trong `CORS_ORIGINS` của đúng deployment. Không tắt TLS hoặc thêm SAN localhost tùy tiện để đạt PASS. Probe vẫn kiểm domain/CA, không proxy/redirect; default localhost dành cho staging/CA phù hợp:

```powershell
python ./scripts/production_ops.py --deployment-directory 'REPLACE_DEPLOYMENT_DIRECTORY' --base-url https://REPLACE_DOMAIN:REPLACE_PORT --ca-file 'REPLACE_APPROVED_CA_CHAIN_FILE' --auth-user-file 'REPLACE_PRIVATE_VIEWER_ACCOUNTS_FILE' --backup-root 'REPLACE_BACKUP_ROOT' --report 'REPLACE_NEW_PRIVATE_OPS_REPORT.json'
```

Không đăng ký job Check trước khi lệnh riêng đạt kết quả xác định với domain/secret thật; checker staging không thay monitor production.

Windows có [register-production-maintenance.ps1](../deploy/register-production-maintenance.ps1): nhận domain/alert config/state cùng tối đa một đường storage bổ sung; mặc định chỉ chuẩn bị, chỉ `-Install` mới đăng ký. Nó không ghi đè task đã có; current-user limited/interactive cần user đăng nhập và Docker Desktop. Docker socket là quyền mạnh trên host, không cấp cho web account. Không dùng Windows interactive schedule làm bằng chứng daemon production liên tục.

Linux có [hướng dẫn systemd](../deploy/systemd/README.md) và các [service](../deploy/systemd/storage-lab-console-maintenance@.service.example), [Check timer](../deploy/systemd/storage-lab-console-check.timer.example), [Backup timer](../deploy/systemd/storage-lab-console-backup.timer.example), [environment file](../deploy/systemd/maintenance.env.example) mẫu. **Chưa cài/chưa nghiệm thu trên systemd host thực**; đây là đầu vào admin phải rà, không phải scheduler đã vận hành:

1. Chọn service account vận hành Docker riêng (mẫu `slc-ops`), không dùng web user hoặc SSH collector. Thay mọi path/user/group; CA/viewer/alert config đọc được, deployment lock/backup/state/receipt ghi được và Docker Engine đúng host. Environment file chỉ chứa đường dẫn/URL non-secret, không chứa key/password/token.
2. Rà `ProtectHome`, `ReadWritePaths` và mapping quyền trên host: mẫu chặn home directory và chỉ mở các thư mục vận hành được chỉ định. Không nới quyền thư mục guard SSH hoặc thêm ops account vào group collector để đọc CA; chọn CA ở thư mục ops phù hợp hay ACL chỉ đọc đã được admin duyệt.
3. Chạy Check/Backup/restore và delivery riêng đạt trước. Admin cài đúng các file đã rà, chạy `systemd-analyze verify` trên phiên bản đích rồi chỉ bật timer sau phê duyệt. Theo guide kiểm `list-timers`, lần chạy service, private journal/report/receipt, backup thực và người nhận.
4. Backup timer mẫu 19:00 UTC = 02:00 UTC+7 ngày kế tiếp; `Persistent=yes` có thể chạy bù khi host lên lại và quiesce ứng dụng. Check mẫu mỗi 5 phút sau lượt trước hoàn tất; lock có thể làm Check trùng Backup thất bại có chủ đích. Cần chốt maintenance/overlap/retry policy, không tự đổi nonzero thành PASS.
5. Rollback scheduler theo guide chỉ disable đúng hai timer; chờ backup đang chạy hoàn tất, kiểm writer phục hồi. Không xóa DB/volume/config/backup hoặc tự restart Ceph.

Ví dụ Windows **chỉ chuẩn bị, chưa đăng ký**; chỉ thêm `-Install` sau khi các lượt riêng và delivery đạt, owner đồng ý lịch và đã kiểm timezone của host:

```powershell
./deploy/register-production-maintenance.ps1 -DeploymentDirectory 'REPLACE_DEPLOYMENT_DIRECTORY' -BackupRoot 'REPLACE_BACKUP_ROOT' -Python 'REPLACE_PYTHON_EXECUTABLE' -BaseUrl https://REPLACE_DOMAIN:REPLACE_PORT -CaFile 'REPLACE_APPROVED_CA_CHAIN_FILE' -AuthUserFile 'REPLACE_PRIVATE_VIEWER_ACCOUNTS_FILE' -AlertConfigFile 'REPLACE_PRIVATE_ALERT_CONFIG.json' -AlertStateFile 'REPLACE_PRIVATE_ALERT_STATE_BASE.json'
```

Mẫu script tạo Backup 02:00 theo giờ host và Check mỗi 5 phút; nếu đơn vị duyệt lịch khác thì rà/cấu hình scheduler tương ứng trước cài. Kiểm task đã đăng ký chạy cả Check và Backup thực tế, report/receipt và hành vi khi logout/reboot; hai task ở trạng thái có tên không chứng minh lịch chạy thành công.

Đơn vị duyệt endpoint/channel/owner, auth/token/key từ file private, TLS/domain và retry/dedup policy. Sender [production_alert.py](../scripts/production_alert.py) chỉ gửi các trường redacted (status/thời điểm/mã alert), không raw payload/key/token/URL credential; receiver HTTPS phải trả 2xx. JSON endpoint riêng, không thêm token trong URL:

```json
{
  "format_version": 1,
  "endpoint": "https://alerts.REPLACE_DOMAIN/console-events",
  "allowed_origin": "https://alerts.REPLACE_DOMAIN",
  "bearer_token_file": "/secure/path/console-alert.token",
  "ca_file": "/secure/path/approved-alert-ca-chain.pem",
  "timeout_seconds": 5
}
```

Lưu config/token/state và thư mục receipt bằng permission private (Linux file 0600, thư mục 0700; Windows ACL riêng), không vào repo/image. `ca_file` có thể bỏ khi receiver dùng CA đã tin trong trust store; `bearer_token_file` có thể bỏ chỉ nếu policy receiver cho phép. HTTPS origin phải khớp chính xác config; không redirect/proxy. Receiver phải hiểu JSON event `TEST`/`ALERT`/`RECOVERY`, không phải endpoint chat chỉ nhận `text` nếu chưa có adapter đã duyệt.

Sau khi đã được phép gửi **TEST** tới endpoint của đơn vị, dùng report ops mới (tuổi tối đa 10 phút), state/receipt riêng:

```powershell
python ./scripts/production_alert.py --config 'REPLACE_PRIVATE_ALERT_CONFIG.json' --report 'REPLACE_FRESH_OPS_REPORT.json' --state 'REPLACE_PRIVATE_ALERT_STATE.json' --receipt 'REPLACE_NEW_PRIVATE_TEST_RECEIPT.json' --test-delivery
```

`--test-delivery` không đổi dedup state. Bỏ flag để gửi ALERT thật theo report; cùng tập mã alert sẽ bị dedup, PASS sau ALERT gửi RECOVERY; state chỉ cập nhật sau receiver 2xx. Receipt `DELIVERED`/2xx chỉ chứng minh receiver đã nhận HTTP, cần người nhận xác nhận thông báo tới kênh/ca trực. Không dùng `--allow-loopback-test` cho production: đó chỉ là demo HTTP loopback, không bằng chứng TLS/receiver thật.

Thử mất ready/backup stale và phục hồi trên fixture/deployment riêng; không tạo sự cố production để kiểm alert. Lưu receipt người nhận và cách xử lý failure/nonzero. Sender không tự scheduler/retry; đơn vị phải chọn retry/backoff phù hợp event ID/dedup và retention state/report, không thay bằng gửi lặp liên tục. Wrapper gọi sender sau Check/Backup và phải giữ report ALERT khi probe trả nonzero; không bỏ sender vì exit 2. Không tự đăng ký task/webhook/khóa hoặc chỉnh firewall để đóng checklist khi chưa duyệt.

## 9. Signer và đơn vị nhận: ký/verify đúng digest

Signer/chủ Docker Hub phải chọn chính sách key hoặc KMS và đơn vị nhận phải duyệt public-key fingerprint, nơi giữ khóa, người có quyền ký, rotation/revocation và transparency-log/offline policy. Không tự sinh key tạm rồi coi đó là trust của production. Cosign chưa được cài/ký trên máy hiện tại.

Tải Cosign từ nguồn chính thức và kiểm nguồn/checksum theo quy trình đơn vị trước khi chạy: [cài Cosign](https://docs.sigstore.dev/cosign/system_config/installation/), [ký](https://docs.sigstore.dev/cosign/signing/signing_with_containers/), [verify](https://docs.sigstore.dev/cosign/verifying/verify/). Đăng nhập registry bằng quy trình CLI/token private đã duyệt; không ghi token vào lệnh mẫu hoặc file `.env`. Ký có thể publish chữ ký/transparency record ra bên ngoài, cần chấp thuận của chủ registry/signer.

Với key-file đã được duyệt, script có sẵn nhận đường dẫn, không inline password:

```powershell
./deploy/sign-production-image.ps1 -ImageDigest 'dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342' -PrivateKey 'REPLACE_PRIVATE_SIGNING_KEY' -PublicKey 'REPLACE_APPROVED_PUBLIC_KEY' -PasswordFile 'REPLACE_PRIVATE_PASSWORD_FILE' -Cosign 'REPLACE_VERIFIED_COSIGN_EXECUTABLE' -OutputDirectory 'REPLACE_NEW_PRIVATE_SIGNATURE_RECEIPT_DIRECTORY'
```

Script hiện hỗ trợ key-file, không giả lập KMS/keyless. Chọn KMS/keyless thì signer dùng quy trình Cosign được đơn vị duyệt và bổ sung verifier identity/issuer cụ thể; không tự đổi sang key-file cho nhanh. Nếu ký/verify lỗi TLS/log/auth, dừng, không `--insecure-ignore-*`, không `--tlog-upload=false`, không bỏ certificate/transparency verification. Receipt script ghi `production_approved=false`; chữ ký đúng chưa thay approval của người nhận.

Trên máy nhận độc lập, lấy public key qua kênh đã duyệt, đối chiếu fingerprint ngoài registry rồi verify trước chạy:

```sh
cosign verify --key /approved/path/console-release.pub dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342
docker pull --platform linux/amd64 dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342
docker run --rm --network none dang7904/storage-lab-console@sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342 version
```

Verify cần exit 0 và subject đúng digest, trusted key đúng chính sách; `version` phải source `d1d43a2...`, app `5.2.0-rc.1`, schema 21. Kiểm SBOM/provenance subject/revision và scan theo policy tại thời điểm nhận; scan 0 finding trước đó không bảo đảm future-zero. Không chỉ verify tag `5.2.0-rc.1` rồi chạy `latest`. SBOM/provenance hiện có không tự đạt SLSA level hay chữ ký nhà phát hành.

## 10. Rollback và ký biên bản

Trước thay release/config/secret: checkpoint đã restore được, ghi digest/schema/config revision trước, maintenance window và người chịu trách nhiệm. Dừng nhận yêu cầu mới/chờ lượt đang chạy; không xóa DB/evidence/executor-state.

Rollback binary chỉ được dùng digest đã duyệt tương thích schema hiện có; sửa đúng `STORAGE_LAB_CONSOLE_IMAGE` của deployment rồi Compose `up -d` bằng đúng overlays/profiles. Không downgrade schema tự động. Nếu schema không tương thích, giữ gate BLOCKED, DBA phục hồi checkpoint vào deployment/volume mới rồi kiểm và chuyển ingress theo change đã duyệt; không restore đè live hoặc `down --volumes`/prune/reset.

Rollback SSH chỉ phục hồi đúng file/block vừa thay từ bản quản trị đã kiểm, `sshd -t/-T` rồi reload; không bật admin key/shell/password/forwarding cho Console, không xóa identity/keyring khi chưa biết consumer. Rollback secret/accounts cần recreate consumer và kiểm password/role cả mới lẫn cũ; giữ audit cũ.

Chỉ nghiệm thu khi các gate dưới đây có người phê duyệt và bằng chứng:

- Đúng Linux AMD64/domain/TLS/revocation/firewall/secret mapping và fresh-host install/UAT.
- SSH forced-command + CephX hạn chế: mọi action bắt buộc PASS, negative restriction PASS.
- Metric/source/scope/window và phần không hỗ trợ được ký; tải/soak/SSH fault đạt SLO đã duyệt.
- Backup lịch chạy thật, cảnh báo tới người nhận, offsite/encryption/retention; restore full service đạt RPO/RTO.
- Registry digest/source/SBOM/provenance/scan/chữ ký + receiver trust policy khớp.
- Dung lượng host đích đủ hoặc ngoại lệ được phê duyệt; cảnh báo hiện tại không bị che.

Ghi mỗi gate `PASS`, `HOLD/BLOCKED` hoặc `NOT_RUN`, ngày giờ, report checksum, owner và người duyệt. Một gate còn mở thì release vẫn RC/không được gọi là production đã nghiệm thu. Core nghiệm thu xong không tự bao gồm OSDMap worker hay khả năng nâng cấp/ghi Ceph.
