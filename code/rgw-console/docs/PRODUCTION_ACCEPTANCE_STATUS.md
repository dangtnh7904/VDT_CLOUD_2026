# Trạng thái nghiệm thu core production — 14/10/2026

Kết luận hiện tại: **CORE STAGING ĐÃ QUA KIỂM, RC ĐÃ PHÁT HÀNH; CHƯA NGHIỆM THU PRODUCTION.** Project riêng `storage-lab-console-staging-20261014`, HTTPS localhost 8446, Docker Linux AMD64. SLO/RPO/RTO vẫn chưa được duyệt. Không thay deployment 8080, ghi/nâng cấp Ceph, factory reset Docker hoặc xóa DB/volume cũ.

## Kiểm sau khi người dùng khởi động lại Docker

- Docker Hub `dang7904/storage-lab-console:5.2.0-rc.1`, index `sha256:98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342`; source `d1d43a28a644f8d079dec48d3c280d8377525ea8` từ clone sạch. Staging đã pin/pull đúng digest này; không thay `latest` hoặc tag cũ. Pull có cache layers, không gọi là lượt wipe/cài mới.
- Backend đóng gói **446/446 PASS, 0 skip** trên Linux + PostgreSQL schema 21. Executor **42/42 PASS, 0 skip** trên Node 22 Linux với module thật của image (chỉ mount tests). Frontend 33 PASS, TypeScript/build PASS; SSR 10 assertion là contract, không phải Browser UAT. Bundle-size warning còn có.
- HTTPS CA/hostname, ba account/RBAC/actor spoof đã kiểm thật. API dùng `storage_lab_runtime`, không superuser/DDL/membership/owner; audit SELECT/INSERT; collection chỉ UPDATE deleted_at/deleted_by, không physical DELETE/sửa payload. UID 10001/read-only/cap-drop/resource limits đạt. Windows file secret hiện 0777/mount RO/host ACL, chưa chứng minh ownership 0400 Linux.
- Lượt cuối 8/8 đạt: view/export mới đúng MON+OSD, IOPS/utilization bắt buộc có đơn vị/thời gian; mixed history/exact filter, so sánh OSD và SHA export đạt. Tải **2×20: 40/40**, p95 **25.781s**, error/429=0; client abort/phục hồi đạt. Chất lượng toàn payload có thể PARTIAL do nguồn tùy chọn còn thiếu/cũ; không giả thành 0/VALID. Smoke sau pin Hub: 7 check PASS, 1 NOT_RUN vì không tạo thêm collection; report tổng PARTIAL có chủ đích, không dùng thay lượt 8/8.
- Lượt tải đầu 38/40 thiếu một metric/daemon dù HTTP 200; chưa đủ chi tiết để khẳng định nguyên nhân chính xác của hai kết quả ấy. Bài kiểm riêng 12 caller tái hiện 15/48 SSH channel-open failures. Đã thêm admission chung 4 lệnh/32 chờ, FIFO/deadline gồm mở kênh và không nhận thiếu exit status như exit 0; kiểm áp lực lại **48/48 PASS** và lượt tải cuối đạt. Giữ report FAIL đầu; không retroactively gán mọi lỗi lịch sử cho SSH pressure.
- Ba fault executor/DB/API trên binary cuối đạt trong 166.031s, phục hồi đúng container ID, collection/audit SHA không đổi. Lỗi trước sửa: DB outage history 500 plaintext sau 31.969s do PoolTimeout 30s. Sau sửa: JSON 503 `DATABASE_UNAVAILABLE` trong **7.093s**, ready 503, phục hồi/fresh read 200. API dừng có HTTP 502 HTML proxy; report giữ `NON_JSON_RESPONSE`.
- Backup cuối **12.509s**, restore riêng **11.466s**: schema 21, **6 payload As-is/audit**, 21 migration và 9 checksum artifact khớp. Volume evidence/executor-state rỗng: không dùng để tuyên bố đã kiểm non-empty linkage. Lỗi receipt PowerShell DateTime/locale và ops Python 3.10 ISO `Z`/7 chữ số đã sửa, có regression và kiểm lại đạt.
- Candidate đầu bị loại vì provenance ghi HEAD main cũ. Rebuild sạch: 26 blobs checksum/subject AMD64/revision đạt. Hub đã kiểm SPDX 157 packages và SLSA VCS/build-arg cùng revision; không tuyên bố SLSA level. Scout 167 packages/0 findings; còn warning cleanup temp archive Windows lock. **Chưa ký image** vì chưa chốt signer/trust policy.
- Monitor đã bổ sung filesystem của DB/evidence/executor-state, kiểm ID/nhãn project, chống số liệu `df` sai và backup khác project. Kiểm 21/21 unit trên Python 3.10 Windows và Python 3.12 Linux đạt. Lượt thật mới nhất báo **HOST_DISK_HIGH**: ổ D chứa deployment/backup **86.26%**; ổ C chứa VHD Docker **90.40%**, cùng vượt ngưỡng đề xuất 85%. Filesystem volume chung báo `df` 6%, alert bảo thủ 7%; không cộng các hàng hoặc lấy free ảo làm bằng chứng đủ dung lượng vật lý. Readiness/fresh metric vẫn HTTP 200/VALID, backup metadata đúng project còn mới. Không xóa/di chuyển/compact dữ liệu hoặc hạ threshold; gate dung lượng vận hành còn HOLD.
- Đã sửa hướng dẫn cài RC: `pull --policy always` không bỏ qua dependency khi `pull_policy=never`; `curl --fail` không coi HTTP lỗi là đạt; gọi backup/restore rehearsal qua đường dẫn script trong repo. Kiểm Compose dry-run trước sửa tái hiện tất cả image bị skip, sau sửa có application/PostgreSQL/Nginx trong kế hoạch pull. Đây chưa phải chứng minh cài sạch trên host Linux mới; ownership numeric UID/CA/SSH vẫn phải kiểm trên host đích.

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
