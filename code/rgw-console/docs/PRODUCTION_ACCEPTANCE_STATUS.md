# Trạng thái nghiệm thu core production — 14/10/2026

Kết luận hiện tại: **STAGING ĐÃ CHẠY, CHƯA NGHIỆM THU PRODUCTION.** Project riêng `storage-lab-console-staging-20261014`, HTTPS localhost 8446, Docker Linux AMD64. SLO/RPO/RTO vẫn chưa được duyệt. Không thay deployment 8080, ghi/nâng cấp Ceph, factory reset Docker hoặc xóa DB/volume cũ.

## Kiểm sau khi người dùng khởi động lại Docker

- Image local `storage-lab-console:5.2.0-staging-fixed`, version `5.2.0-rc.1`, index `sha256:91c1540deb28447ef88b73059ce2017f3ea63ef0b2709934597f51867ff0e1c0`; source `f5a573bfe7f2c50fde9a06552791972891c75ebb` từ clone sạch.
- Backend đóng gói **444/444 PASS, 0 skip** trên Linux + PostgreSQL schema 21. Frontend 33 PASS, executor 31 PASS, TypeScript/build PASS; SSR 10 assertion là contract, không phải Browser UAT. Bundle-size warning còn có.
- HTTPS CA/hostname, ba account/RBAC/actor spoof đã kiểm thật. API dùng `storage_lab_runtime`, không superuser/DDL/membership/owner; audit SELECT/INSERT; collection chỉ UPDATE deleted_at/deleted_by, không physical DELETE/sửa payload. UID 10001/read-only/cap-drop/resource limits đạt. Windows file secret hiện 0777/mount RO/host ACL, chưa chứng minh ownership 0400 Linux.
- Smoke 8/8 đạt: view/export mới đúng MON+OSD, bắt buộc IOPS/utilization có đơn vị/thời gian; mixed history/exact filter, so sánh và SHA export đạt. Bốn request ở hai client: p95 17.922s, error/429=0. Tải 2×20 đang chạy.
- Ba fault executor/DB/API đạt, phục hồi đúng container ID, collection/audit SHA không đổi. Lỗi thật trước sửa: DB outage history 500 plaintext sau 31.969s do `psycopg_pool.PoolTimeout` 30s. Sau sửa: JSON 503 `DATABASE_UNAVAILABLE` trong 7.109s, ready 503, phục hồi/fresh read 200. API dừng có 502/504 HTML proxy; report giữ `NON_JSON_RESPONSE`.
- Backup 11.680s, restore riêng 11.854s: schema 21, hai payload As-is/audit và 9 checksum artifact khớp. Volume evidence/executor-state rỗng: không dùng để tuyên bố đã kiểm non-empty DB/evidence linkage. Lỗi restore ban đầu tại receipt do PowerShell 7.5 typed DateTime/locale đã sửa và chạy lại đạt; ops Python 3.10 đọc ISO `Z`/7 chữ số đã có regression.
- Candidate đầu bị loại vì provenance ghi HEAD main cũ. Rebuild sạch: 26 blobs checksum, subject AMD64, SPDX/provenance cùng revision đạt; không tuyên bố SLSA level. Scout 167 packages/0 findings; còn warning cleanup temp archive bị Windows lock. Chưa push/pull/sign RC mới.
- Monitor báo `HOST_DISK_HIGH` (~86.24% ổ D), backup mới healthy. Không tự xóa dữ liệu hoặc hạ threshold. Chỉ đo host disk, không đo Docker VM disk.

Gate còn mở: dedicated SSH/CephX/root-owned guard cần admin root (lab authority rộng); MGR caps trên đích, metric bắt buộc/host/process/network/percentile/cache/nguồn TLS; certificate/domain/Browser UAT đích; SSH thực chậm/mất kết nối/tải dài/SLO; config/secret/role recovery, scheduler/alert delivery, encryption/offsite/retention; signer/trust policy và biên bản nhận. Worker OSDMap không thuộc core gate.

`.env.local-readonly` gốc SHA256 `bf0dc234a25e155b54b91b3aaf79e4b2b8a505ef3755e3a0644a040cadb354fb` không đổi; DB lab giữ hai collection/hai event. Reports lỗi Engine, fault/restore trước sửa và provenance sai giữ nguyên. API export/checksum không thay cho tải tệp Browser bị từ chối. Hai thư mục IPC socket cũ đổi tên recoverable; không xóa VHD hoặc tuyên bố Docker đã sửa vĩnh viễn.

## Bằng chứng chuẩn bị ban đầu — giữ làm lịch sử

| Nhóm | Đã làm và kiểm | Gate chưa đạt |
| --- | --- | --- |
| 1. Metric | Chẩn đoán HTTP/empty/parser/redirect; binding FSID hoặc service MGR mới; chống tổng cluster sai; window monotonic và clock-shift; endpoint active thật có 6 OSD, cache config 15 giây | Chốt metric bắt buộc, cache overrides/độ trễ, nguồn host/process/network/percentile, TLS hoặc network trust của exporter, kiểm trên môi trường đích |
| 2. Staging production | Config riêng, CA/leaf hostname đã verify, ba account/secret DB riêng, UID non-root/read-only, CPU/RAM/PID/log rotation; Compose config merge PASS | Docker Engine chưa chạy; HTTPS/auth/secret readability/DB role trong container chưa đo; chưa có cert được môi trường đích tin cậy |
| 3. Quyền | Unit RBAC/actor spoof/role rotation; audit grants append-only và collection chỉ xóa mềm; forced-command guard deny shell/write/RBD, FSID/helper hash/output/time budget | SQL integration và 3 Linux process tests chưa chạy; guard/account/key/CephX caps chưa cài hoặc kiểm trên host; staging còn dùng authority SSH lab |
| 4. Tải/lỗi | Harness xác minh marker/HTTPS trước khi ghi, HTTP/error/timing/checksum/history/comparison/load/abort; unit cancellation/deadline | Lượt staging đầu FAIL network vì Docker; không có collection test; chưa kiểm restart DB/API/executor, SSH thật chậm/mất kết nối hoặc tải dài |
| 5. Phục hồi | Backup thêm audit checkpoint; restore đối chiếu lịch sử/actor/checksum và đo thời gian; checker/khóa maintenance/scheduler opt-in đã có code | Backup/restore mới chưa chạy, task chưa đăng ký, chưa thử alert delivery, offsite/encryption/retention và config/secret/role recovery |
| 6. Release | Script build OCI AMD64 yêu cầu commit đúng input, yêu cầu SBOM/provenance; script ký/verify digest và public key | Chưa build/push/scan/sign image mới hoặc kiểm attestations thực; chưa chốt signer/trust policy/biên bản môi trường đích |

## Bằng chứng ban đầu trước khi Engine hoạt động

- Backend: 389 tests, **364 PASS, 25 SKIP**; skip không tính PASS. Frontend 33 PASS, executor 31 PASS; TypeScript/build PASS (bundle-size warning còn có), PowerShell production scripts parse PASS, Compose staging merge PASS.
- CA thử nghiệm và certificate localhost ký đúng CA/hostname; không cài vào trust store toàn máy.
- Harness thật `CORE_READONLY_STAGING_ACCEPTANCE`: **FAIL** ở `staging_target_and_readiness`, HTTP không nhận response, mã `NETWORK_UNAVAILABLE`. `created_collection_ids=[]`.
- Nguyên nhân cản runtime: Docker Desktop 4.72.0 lỗi inference socket; Engine Linux chưa có pipe. Không factory reset, không xóa socket/disk/volume để thử.
- File `.env.local-readonly` gốc SHA256 giữ `bf0dc234a25e155b54b91b3aaf79e4b2b8a505ef3755e3a0644a040cadb354fb`. Secret/CA/accounts/report ở runtime private và không nằm trong Git/image.
- Image Hub đang phát hành vẫn **5.1.2-rc.1**. Source mới chưa phải binary đang chạy; không dùng image cũ cho overlay multi-account mới.

## Kế hoạch ban đầu — hiện đã triển khai một phần ở trên

1. Build image staging từ source mới, chạy toàn bộ PostgreSQL và Linux guard tests trong container; không dùng 25 skip như bằng chứng production.
2. Khởi động project staging riêng với production + access-control + staging overlays, profiles `bundled-db,ceph-readonly`; không bật worker hay periodic performance collector.
3. Kiểm HTTPS bằng CA được truyền rõ, auth/RBAC/actor/DB role và fresh view/export; chạy harness 2 client × 2 lượt trước, sau đó 2 × 20 lượt.
4. Diễn tập lỗi/restart chỉ với container của đúng project staging, lưu HTTP/error và hash/audit trước/sau. Không dừng Ceph daemons.
5. Backup/restore vào DB/volume riêng; kiểm cả collection, audit và evidence. Sau khi có kết quả mới xét đăng ký lịch và thử kênh cảnh báo.
6. Chốt source/digest, attestations/scan/signature và report. Cert/SSH caps/metric nguồn/SLO của môi trường đích vẫn cần nghiệm thu riêng.

Ngưỡng đề xuất: view/export nông p95 ≤60 giây tại 2 client, lỗi/429=0; deep OSD đo riêng; backup mỗi ngày, checkpoint alert >26 giờ; host disk alert ≥85%; RPO ≤24 giờ, RTO ≤30 phút. Những số này **chưa được người phụ trách nghiệm thu phê duyệt**.

Quy trình và giới hạn: [vận hành production](PRODUCTION_OPERATIONS.md), [SSH/CephX](PRODUCTION_SSH.md).
