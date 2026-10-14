# Vận hành và kiểm nghiệm thu production chỉ đọc

Phạm vi đầu tiên là **chỉ số trực tiếp, thu/lưu/xuất As-is và so sánh**. Không benchmark, nâng cấp Ceph, shell/RBD/terminal hay OSDMap worker trong biên bản đầu tiên. `PASS` của unit test hoặc staging không thay cho nghiệm thu hệ thống đích.

## Cấu hình và tài khoản

`prepare-production-staging.ps1` tạo thư mục mới, không ghi đè `.env`/DB localhost. CA thử nghiệm chỉ dành cho client được truyền `--ca-file`, không cài vào Windows trust store. Ba tài khoản `viewer`, `operator`, `admin` có mật khẩu ngẫu nhiên riêng; server chỉ mount hash JSON. Viewer xem/xuất/so sánh; operator thêm quyền lưu collection; admin xóa mềm/khôi phục. Mọi tài khoản đều chỉ đọc Ceph. Audit lấy username đã xác thực, không nhận `X-Actor` của client.

API dùng `storage_lab_runtime` không superuser/DDL/CREATEROLE/CREATEDB. Job migration/provisioning dùng secret riêng, không mount vào API. Audit chỉ được SELECT/INSERT; collection không được xóa vật lý hoặc sửa payload/danh tính; chỉ được UPDATE hai cột xóa mềm. Đây không phải bảo vệ khỏi DBA/root: cần hạn chế tài khoản quản trị, bảo vệ backup và audit ngoài máy theo chính sách đơn vị.

Compose giới hạn CPU/RAM/PID và xoay log 10 MiB × 3 mỗi container. File secret trên Linux phải có ownership/mode mà UID container thực sự đọc được; khai báo Compose `uid/gid/mode` không đảm bảo sửa quyền của bind-mounted file. Kiểm cả quyền host và trong container trước nghiệm thu.

## Nguồn metric

HTTP 200 rỗng khác timeout, HTTP lỗi, parser lỗi, sai kiểu nội dung hoặc redirect. Report giữ status/mã lỗi nhưng không giữ URL/token/body chẩn đoán. Endpoint phải khớp service Prometheus từ lần đọc `ceph.mgr_services` đã xác minh FSID, hoặc các series phải mang FSID đúng. Không tự follow redirect hay suy ra đúng cụm chỉ vì operator cấu hình FSID.

IOPS/bytes/s được tính từ hai counter với khoảng đo monotonic; UTC dùng cho thời điểm nguồn. Clock UTC thay đổi đáng kể sẽ không cho rate hợp lệ. `PERFORMANCE_LIVE_MIN_WINDOW_SECONDS=15` mặc định phải **ít nhất bằng** cache/scrape interval thật của exporter; mỗi view/export có thể chờ khoảng này. Cần kiểm overrides của MGR active trên môi trường đích. Thời điểm mẫu là lúc nhận HTTP, không phải timestamp nội bộ của từng OSD. Cache và độ trễ nguồn phải ghi vào giới hạn nghiệm thu; không biến dữ liệu thiếu thành 0.

Host/process/network, percentiles và các trường A0 chưa hỗ trợ vẫn là thiếu dữ liệu. Chốt danh sách chỉ số bắt buộc trước khi chạy harness. Collector định kỳ chưa có binding MGR mới cho exporter không nhãn FSID nên vẫn `PARTIAL`; không bật profile `collectors` trong staging đầu tiên. Endpoint active có thể đổi khi MGR failover; lỗi/partial phải hiển thị thay cho dữ liệu cũ gắn nhãn mới.

## Tải và lỗi

`scripts/production_acceptance.py` chỉ cho HTTPS loopback, CA xác minh và marker staging đúng project. Nó kiểm 401/403, RBAC, actor audit, nguồn mới, checksum export, phạm vi daemon, hai collection test, filter, comparison cùng loại, tải đồng thời và client abort. Report giữ HTTP/error/timing cho cả thất bại. Dữ liệu test có nhãn `VALIDATION_ONLY_NO_UPGRADE`; cleanup chỉ xóa mềm ID do đúng lượt kiểm tạo.

Ngưỡng ban đầu **đề xuất, chưa phê duyệt**: 2 client × 2 lượt, p95 ≤ 60 giây cho view/xuất nông, lỗi và 429 bằng 0 ở tải này. Không áp ngưỡng view cho deep OSD collection. Sau smoke đo 2 client × 20 lượt, rồi thống nhất tải đỉnh, queue/busy budget và thời gian đo dài hơn. Fault test chỉ stop/restart API, DB hoặc executor của **project staging riêng**; không dừng MON/MGR/OSD Ceph. Cần đối chiếu ID/hash/audit trước/sau restart và kiểm queue phục hồi. Unit test cancellation không chứng minh process remote đã dừng.

## Backup, phục hồi và cảnh báo

SSH exec của tất cả lượt xem/xuất/collector dùng chung admission: mặc định 4 lệnh đồng thời, tối đa 32 lệnh chờ, FIFO, deadline bao gồm chờ + mở kênh + output. Không mặc định exit 0 nếu SSH đóng mà thiếu exit status. Phải đặt giới hạn phù hợp MaxSessions thực của account đích; admission không chứng minh process remote đã bị kill. Bài kiểm áp lực 12 caller trước sửa đã tái hiện SSH channel-open failure; không tự gán nguyên nhân đó cho hai kết quả thiếu nguồn lịch sử chưa lưu đủ chi tiết.

`production_fault_drill.py` cần marker HTTPS production/staging, flag cho phép lỗi và đúng container ID/nhãn project trước mỗi stop/start. Nó không thao tác Ceph, localhost lab hoặc container khác; `finally` phục hồi đúng ID và kiểm hash collection/audit. DB mất kết nối trả JSON 503 `DATABASE_UNAVAILABLE`, `retryable=true`, request ID và `Retry-After: 2`; pool acquire/connect được giới hạn 5 giây, không rút ngắn thời gian chạy truy vấn SQL. Lỗi schema/lập trình không bị đổi thành lỗi kết nối. Proxy khi API dừng có thể trả HTTP 502/504 HTML; report vẫn giữ mã HTTP và `NON_JSON_RESPONSE`, không ghi thành thành công/empty history.

`backup-production.ps1` quiesce đúng project, backup DB/evidence/executor-state, checksum payload và lưu audit checkpoint. Trong lúc backup ứng dụng tạm ngừng nhận yêu cầu; phải có maintenance window. `verify-production-backup.ps1` restore vào DB/volume mới không network, kiểm migration, collection/soft-delete/hash, audit actor/history và DB-evidence linkage; chỉ xóa các đối tượng rehearsal do chính lượt đó tạo. Nó lưu cả report FAIL và thời gian restore. Config, secret, role DB và khả năng chạy lại API trên host khác còn phải diễn tập riêng.

Đề xuất ban đầu: backup mỗi ngày 02:00, kiểm vận hành mỗi 5 phút, alert dung lượng host ≥85%, checkpoint backup quá 26 giờ; RPO ≤24 giờ và RTO ≤30 phút chỉ là mục tiêu đề xuất. Thời gian restore đo được và tuổi checkpoint không tự chứng minh toàn bộ RPO/RTO. Chưa tự xóa backup cũ; cần chốt dung lượng/retention và encryption/offsite.

`run-production-maintenance.ps1` khóa chống hai lượt đồng thời, chọn Backup hoặc Check. `scripts/production_ops.py` kiểm HTTPS/auth/marker, trạng thái container, readiness, ổ chứa deployment/backup, tuổi backup đúng `source_project` và tùy chọn một fresh-read. Tuổi backup chỉ xét metadata format 1/COMPLETE; không thay kiểm checksum archive hoặc restore. Chỉ xuất JSON/exit code, không tự restart hoặc sửa Ceph.

Probe filesystem xác minh project/container ID và nhãn named-volume `postgres-data`, `evidence`, `executor-state`, rồi chỉ chạy `df -Pk` tại đường dẫn cố định trong đúng container ID. Thiếu/sai nhãn/bind mount/đọc lỗi trả `UNAVAILABLE`, không coi như 0%/PASS. PostgreSQL và evidence bắt buộc; executor-state là NOT_RUN nếu chưa bật executor. Phần trăm báo cáo của `df` được giữ riêng; alert dùng giá trị lớn hơn giữa phần trăm đó và `ceil(used/(used+available)×100)` để không bỏ qua reserved blocks. Các volume có thể chung filesystem: không cộng tổng/free của các hàng.

Trên Docker Desktop, filesystem Linux có thể là thin-provisioned: còn nhiều GB ảo không chứng minh ổ vật lý chứa VHD còn đủ chỗ. Thêm đường dẫn thư mục chứa đĩa Docker **đã xác minh trên máy** vào `-AdditionalHostStoragePath` của lượt Check, hoặc `--host-storage-path` của Python (có thể lặp, tối đa 8). Probe chỉ đọc dung lượng filesystem chứa thư mục; không di chuyển/compact/xóa VHD. Ví dụ kiểm riêng, không đăng ký scheduler:

```powershell
& ./run-production-maintenance.ps1 -Mode Check -DeploymentDirectory 'D:/deploy/storage-lab-console-staging-new' -BackupRoot 'D:/deploy/storage-lab-console-staging-new/backups' -Python 'C:/path/to/python.exe' -CaFile 'D:/deploy/storage-lab-console-staging-new/client/staging-ca.crt' -AuthUserFile 'D:/deploy/storage-lab-console-staging-new/client/accounts.json' -AdditionalHostStoragePath 'C:/path/to/verified/docker-disk-directory'
```

Task wrapper nhận alert và trả lỗi/nonzero có chủ đích; không hạ ngưỡng hoặc bỏ kiểm để tạo PASS. Chưa đo quota riêng của volume/inode, không tự tìm được mọi đĩa Docker ở host khác. Scheduler hiện không tự thêm đường dẫn storage bổ sung; phải cấu hình và kiểm thực đường dẫn trên host đích trước nghiệm thu.

Windows: `register-production-maintenance.ps1` mặc định chỉ chuẩn bị; chỉ `-Install` mới đăng ký task current-user limited, không ghi password vào command line. Cần Docker Desktop và user đang đăng nhập. Trên Linux dùng scheduler của đơn vị gọi `pwsh -NoProfile -NonInteractive -File run-production-maintenance.ps1` với đường dẫn private config; service account chỉ cần quyền vận hành deployment riêng. Docker socket tương đương quyền mạnh trên host, không cấp cho tài khoản web. Kênh email/webhook/monitoring nhận JSON/exit code phải được chọn và thử gửi cảnh báo; chưa có kênh thì gate cảnh báo còn mở.

## Bản phát hành

`build-production-candidate.ps1` build từ clone sparse sạch, detached đúng Git commit được chỉ định; giữ nguyên checkout/index chính. Label `VCS_REF` không tự sửa provenance BuildKit nếu build từ checkout khác. Script xuất OCI Linux AMD64 với `--sbom=true --provenance=mode=max`; `-Load -ImageTag` chỉ load local khi containerd store giữ được attestations, không tự push. `scripts/verify_oci_candidate.py` kiểm checksum blobs, descriptor, Linux AMD64, subject binding, SPDX và revision provenance/OCI; không tự tuyên bố đạt SLSA hay chữ ký. Cần scan, pull đúng digest rồi chạy staging/restore trước phát hành. [Docker attestations](https://docs.docker.com/build/metadata/attestations/)

`sign-production-image.ps1` chỉ nhận digest repo của người dùng, ký rồi verify bằng public key riêng; password/key ở file private, không trong `.env`/Git/image. Phải dùng Cosign đã được đơn vị kiểm nguồn/checksum và public key đã duyệt. Script không bật `--insecure-ignore-*` hay bỏ qua transparency verification. [Cosign signing](https://docs.sigstore.dev/cosign/signing/signing_with_containers/), [Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/)

Biên bản cuối cần ghi digest/source commit, config hash không secret, certificate/domain, role/caps, tải/p95/error, restore/audit/hash, RPO/RTO, giới hạn metric, image signature/attestations và người duyệt. Worker OSDMap vẫn có gate riêng; không nhập kết quả lab worker vào kết luận core production.
