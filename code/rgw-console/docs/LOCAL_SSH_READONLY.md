# Localhost nối Ceph bằng SSH key — read-only

Hồ sơ cấu hình và kiểm tra baseline ngày 12/10/2026, trước phiên bản v5. Mở http://127.0.0.1:8080/.
Đây là cấu hình lab cục bộ, không phải chứng nhận production hoặc quyền chạy nâng cấp.

## Kết nối đang dùng

- Cluster ID: `ceph-master-lab`; FSID: `17c77e12-a16a-11f1-838e-cf68e9c001d8`.
- SSH: `dangg@10.20.20.11:22` (`ceph-master`). Key hiện có: `C:\Users\Dang\.ssh\openstack_lab`.
- Host key được pin: `SHA256:RFJqFlOzZUR40hQuPg1uWZ2btXfKZ/2+yFtITWZwVTY`. Không tắt kiểm tra host key.
- Collector `1.0.4`: `/home/dangg/.local/share/storage-lab-console/collect_osd.py`.
- SHA-256 collector: `1a5a127bd285fc1e32fe17137948f78d8ba38baaf7311145c7219b17f10558a5`.
- Python chạy bằng user SSH; các lệnh Ceph cố định chạy qua `sudo -n ceph`. Không mở sudo Python hoặc sửa sudoers.
- Metrics Ceph: `http://10.20.20.11:9283/metrics`, từ endpoint MGR của cluster đã đối chiếu FSID. Có IOPS/throughput cluster và từng OSD; latency không có thì giữ null.

Key không được chép vào source/image. Executor mount key read-only; token executor nằm trong file secret riêng, không nằm trong `.env` hoặc tài liệu.

## File cấu hình và dịch vụ

`deploy/.env.local-readonly` và `deploy/config/profiles/local-lab-readonly.yaml` là file riêng của máy này, đã bị Git ignore.
Token: `deploy/secrets/local_executor_token`, cũng bị ignore. Không commit/upload các file secret hoặc key.

Các container đang chạy:

- `storage-lab-console-local-api`: chỉ publish `127.0.0.1:8080`.
- `storage-lab-console-local-executor`: không publish port ra host.
- `storage-lab-console-local-capacity`: thu capacity mỗi 10 giây, observe-only.
- `storage-lab-console-local-performance`: thu metrics mỗi 15 giây.

Cả bốn dùng `storage-lab-console:3.0.0-ssh-readonly-preview.1`, root filesystem read-only, không capability, no-new-privileges và restart unless-stopped. PostgreSQL/evidence volume cũ được giữ nguyên; các container trước thay đổi được giữ ở trạng thái stopped. Không xóa volume để cập nhật image.

Các khóa bảo vệ vẫn giữ:

```dotenv
CONSOLE_READ_ONLY=true
FEATURE_UPGRADE=true
UPGRADE_MUTATIONS_ENABLED=false
CAPACITY_OBSERVE_ONLY=true
OSD_INFO_COLLECTOR_RUN_AS_SSH_USER=true
```

`FEATURE_UPGRADE=true` mở khả năng đọc inventory, không cho phép thay đổi cluster. Source v5 đã gỡ Dry-run và cấu hình workload cũ. Capacity observe-only hiện chưa có protected-pool scope được chứng minh đầy đủ; NORMAL/FRESH không phải admission PASS.

Nếu Docker đã chạy, không cần tạo `.env` mới: cấu hình trên đã được áp dụng. Khi khởi động lại máy, mở Docker Desktop; restart policy sẽ khởi động lại các container. Có thể kiểm tra bằng `docker ps` và `Invoke-RestMethod http://127.0.0.1:8080/api/ready`.

`deploy/start-local-readonly.ps1` là script chuyển preview ban đầu sang cấu hình SSH này; nó yêu cầu API/DB/evidence preview có sẵn và cố ý từ chối khi executor/collector đã tồn tại. Không chạy lại như một script cập nhật hoặc xóa container/volume để né kiểm tra đó.

## Baseline lịch sử đã kiểm chứng

1. **OSD inventory**: chọn session `SSH baseline 2026-10-12`, mở collection BEFORE `18d94d48-7588-443f-bfd5-37ba0cff044a` (`VALID`, collector 1.0.4).
2. Chọn JSON/CSV/ZIP/MD rồi **Export snapshot**. **Collect & export** tạo snapshot mới và tải bản mới xuống máy; để trống OSD IDs nghĩa là cả allowlist 0–5.
3. **Cluster & Metrics**: snapshot `c934ab33-6fb6-50d1-ba6b-470130c9e229` gồm cluster, MON, MGR, OSD, host và pool. Có 1 cluster, 3 MON, 2 MGR, 6 OSD, 3 host và 12 pool.
4. Xem live performance với nguồn Ceph, không dùng application metrics để suy luận tải cluster.

Baseline lúc thu: HEALTH_OK, epoch 3812, 267 PG, 6 OSD up/in. `osd.2`: 267 PG / 67 primary; `osd.5`: 0 PG / 0 primary. Đây là quan sát tại thời điểm thu, không phải điều kiện cố định hoặc kết luận drain an toàn.

OSD nguồn vẫn đang trộn Pacific 16.2.5 và 16.2.15; cấu hình này không nâng cấp daemon, không đổi weight/primary-affinity/CRUSH/flags và không thay đổi dữ liệu pool.

ZIP đã tải và kiểm tra trên máy:

```text
C:\Users\Dang\Downloads\storage-lab_ceph-master-lab_osd_collection_20261012T092144_416e51c2-a372-40c7-ba66-c1fd1c4d395b.zip
SHA-256: 5c01f2d26137f3e0fed4484b7cafe1da0e213c53ff85735cf3b22763b88c3ad3
```

ZIP chứa manifest, SHA256SUMS, JSON, CSV, Markdown và raw-redacted; 5 checksum thành viên đã xác minh. Các lần thử FAILED/INCONCLUSIVE trước sửa lỗi vẫn được giữ trong journal, không xóa hoặc ghi đè.

## Giới hạn còn lại

- Chưa có gói A0.1–A0.8 đầy đủ: full CRUSH map/compat choose_args, full PG up/acting/override, orchestration spec/upgrade status và clock/crash/scrub PASS/HOLD vẫn cần triển khai theo plan.
- DB/WAL device hoặc image ID không được Ceph báo thì giữ UNKNOWN; không bịa số liệu.
- Cấu hình này dùng SSH account sẵn có với quyền Ceph rộng, transport nội bộ HTTP và lab secret; trước production cần account least-privilege, TLS/auth/access controls và nghiệm thu cluster đích theo hướng dẫn production riêng.
- Image mới chỉ ở local Docker, không cập nhật Docker Hub rc.1.
