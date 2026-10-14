# Trạng thái nghiệm thu core production — 14/10/2026

Kết luận: **CHƯA ĐẠT NGHIỆM THU; mới hoàn thiện source và chuẩn bị staging.** Người dùng chọn kiểm staging trên máy hiện tại trước, chưa có SLO/RPO/RTO được duyệt. Không cấp quyền hoặc nâng cấp daemon Ceph trong lượt này; không xóa DB/.env hoặc reset Docker.

| Nhóm | Đã làm và kiểm | Gate chưa đạt |
| --- | --- | --- |
| 1. Metric | Chẩn đoán HTTP/empty/parser/redirect; binding FSID hoặc service MGR mới; chống tổng cluster sai; window monotonic và clock-shift; endpoint active thật có 6 OSD, cache config 15 giây | Chốt metric bắt buộc, cache overrides/độ trễ, nguồn host/process/network/percentile, TLS hoặc network trust của exporter, kiểm trên môi trường đích |
| 2. Staging production | Config riêng, CA/leaf hostname đã verify, ba account/secret DB riêng, UID non-root/read-only, CPU/RAM/PID/log rotation; Compose config merge PASS | Docker Engine chưa chạy; HTTPS/auth/secret readability/DB role trong container chưa đo; chưa có cert được môi trường đích tin cậy |
| 3. Quyền | Unit RBAC/actor spoof/role rotation; audit grants append-only và collection chỉ xóa mềm; forced-command guard deny shell/write/RBD, FSID/helper hash/output/time budget | SQL integration và 3 Linux process tests chưa chạy; guard/account/key/CephX caps chưa cài hoặc kiểm trên host; staging còn dùng authority SSH lab |
| 4. Tải/lỗi | Harness xác minh marker/HTTPS trước khi ghi, HTTP/error/timing/checksum/history/comparison/load/abort; unit cancellation/deadline | Lượt staging đầu FAIL network vì Docker; không có collection test; chưa kiểm restart DB/API/executor, SSH thật chậm/mất kết nối hoặc tải dài |
| 5. Phục hồi | Backup thêm audit checkpoint; restore đối chiếu lịch sử/actor/checksum và đo thời gian; checker/khóa maintenance/scheduler opt-in đã có code | Backup/restore mới chưa chạy, task chưa đăng ký, chưa thử alert delivery, offsite/encryption/retention và config/secret/role recovery |
| 6. Release | Script build OCI AMD64 yêu cầu commit đúng input, yêu cầu SBOM/provenance; script ký/verify digest và public key | Chưa build/push/scan/sign image mới hoặc kiểm attestations thực; chưa chốt signer/trust policy/biên bản môi trường đích |

## Bằng chứng lượt này

- Backend: 389 tests, **364 PASS, 25 SKIP**; skip không tính PASS. Frontend 33 PASS, executor 31 PASS; TypeScript/build PASS (bundle-size warning còn có), PowerShell production scripts parse PASS, Compose staging merge PASS.
- CA thử nghiệm và certificate localhost ký đúng CA/hostname; không cài vào trust store toàn máy.
- Harness thật `CORE_READONLY_STAGING_ACCEPTANCE`: **FAIL** ở `staging_target_and_readiness`, HTTP không nhận response, mã `NETWORK_UNAVAILABLE`. `created_collection_ids=[]`.
- Nguyên nhân cản runtime: Docker Desktop 4.72.0 lỗi inference socket; Engine Linux chưa có pipe. Không factory reset, không xóa socket/disk/volume để thử.
- File `.env.local-readonly` gốc SHA256 giữ `bf0dc234a25e155b54b91b3aaf79e4b2b8a505ef3755e3a0644a040cadb354fb`. Secret/CA/accounts/report ở runtime private và không nằm trong Git/image.
- Image Hub đang phát hành vẫn **5.1.2-rc.1**. Source mới chưa phải binary đang chạy; không dùng image cũ cho overlay multi-account mới.

## Tiếp tục khi Engine sẵn sàng

1. Build image staging từ source mới, chạy toàn bộ PostgreSQL và Linux guard tests trong container; không dùng 25 skip như bằng chứng production.
2. Khởi động project staging riêng với production + access-control + staging overlays, profiles `bundled-db,ceph-readonly`; không bật worker hay periodic performance collector.
3. Kiểm HTTPS bằng CA được truyền rõ, auth/RBAC/actor/DB role và fresh view/export; chạy harness 2 client × 2 lượt trước, sau đó 2 × 20 lượt.
4. Diễn tập lỗi/restart chỉ với container của đúng project staging, lưu HTTP/error và hash/audit trước/sau. Không dừng Ceph daemons.
5. Backup/restore vào DB/volume riêng; kiểm cả collection, audit và evidence. Sau khi có kết quả mới xét đăng ký lịch và thử kênh cảnh báo.
6. Chốt source/digest, attestations/scan/signature và report. Cert/SSH caps/metric nguồn/SLO của môi trường đích vẫn cần nghiệm thu riêng.

Ngưỡng đề xuất: view/export nông p95 ≤60 giây tại 2 client, lỗi/429=0; deep OSD đo riêng; backup mỗi ngày, checkpoint alert >26 giờ; host disk alert ≥85%; RPO ≤24 giờ, RTO ≤30 phút. Những số này **chưa được người phụ trách nghiệm thu phê duyệt**.

Quy trình và giới hạn: [vận hành production](PRODUCTION_OPERATIONS.md), [SSH/CephX](PRODUCTION_SSH.md).
