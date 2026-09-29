# Bộ kế hoạch nâng cấp Ceph 16.2.5 → 16.2.15 — PA1 + H0

**Phiên bản tài liệu:** 2.1 · **Ngày:** 28/09/2026 · **Trạng thái thực thi:** chưa chạy; H0-R/H0-W trong nguồn hiện là thiết kế chưa triển khai.

Bộ này biên soạn lại từ `UPGRADE-CHECKLIST(1)(6).md`, cập nhật theo PA1 và H0 feature v2.1 trong repo `dangtnh7904/VDT_CLOUD_2026` tại commit `c29c4272c2c3b69ceb1d68aac234731fe2f07f01`. Tất cả file Markdown nằm cùng một thư mục và dùng liên kết tương đối; tải ZIP và giữ cấu trúc khi đưa vào Git/VS Code. Chỉ dùng PA1 trong kế hoạch này.

## 1. Đọc file nào?

| Cần làm gì? | Tài liệu |
| --- | --- |
| Giải thích vì sao chọn 16.2.15, lợi ích và tác động hiệu năng | [01 — Lý do nâng cấp](01-LY-DO-NANG-CAP.md) |
| Xác định điều gì thực sự phải sửa, sửa ở đâu và khi nào | [02 — Điều kiện và thay đổi](02-DIEU-KIEN-VA-THAY-DOI.md) |
| Chuẩn bị trước thay đổi | [03 — Phase 1: Trước nâng cấp](03-PHASE-1-TRUOC-NANG-CAP.md) |
| Nâng từng thành phần, canary từng OSD rồi mở rộng | [04 — Phase 2: Đang nâng cấp](04-PHASE-2-CANARY-VA-ROLLOUT.md) |
| Hoàn nguyên trạng thái tạm, đo lại và nghiệm thu | [05 — Phase 3: Sau nâng cấp](05-PHASE-3-SAU-NANG-CAP.md) |
| Quyết định GO / HOLD / STOP ở mỗi checkpoint | [06 — Gate và ngưỡng](06-GATE-VA-NGUONG.md) |
| Biết lúc nào tạm dừng, giữ nguyên hoặc bật lại một chức năng | [07 — Bật/tắt và khôi phục](07-BAT-TAT-VA-KHOI-PHUC.md) |
| Chọn test chức năng, dữ liệu, khả năng phục hồi theo ba phase | [08 — Test chức năng](08-TEST-CHUC-NANG.md) |
| Đo RBD, RGW, chi phí recovery và so sánh trước/sau | [09 — Test hiệu năng](09-TEST-HIEU-NANG.md) |
| Xử lý lỗi, fallback, rollback hoặc rebuild | [10 — Xử lý sự cố](10-STOP-FALLBACK-ROLLBACK.md) |
| Theo luồng PA1, H0-R và H0-W Level 1/2/3 | [11 — PA1 + H0](11-PA1-H0-LEVEL-1-2-3.md) |
| Điền As-Is, nhật ký từng OSD, kết quả test và nghiệm thu | [12 — Biểu mẫu bằng chứng](12-BIEU-MAU-BANG-CHUNG.md) |
| Kiểm nguồn, điểm sửa so với bản cũ, nhóm test chuyên sâu | [13 — Nguồn và đối chiếu](13-NGUON-VA-DOI-CHIEU.md) |
| Lấy lệnh đọc trạng thái và mẫu lệnh cephadm đã phân nhánh | [14 — Lệnh tham khảo](14-LENH-THAM-KHAO.md) |
| Test riêng Recovery Gate và ba level Write ACK Gate | [15 — Test H0 theo level](15-TEST-H0-LEVEL-1-2-3.md) |

## 2. Luồng sử dụng

1. Đọc 01; điền phạm vi và As-Is trong 12.
2. Đánh dấu điều kiện áp dụng trong 02; chốt ngưỡng tại 06.
3. Đọc 11, chọn một level H0-W cho run, chốt capability và corpus; chạy Phase 1, PRE tests, test H0 tại 15 và baseline hiệu năng.
4. Qua gate vào Phase 2: MGR → MON → crash → OSD → các dịch vụ còn lại theo cephadm. Với X: PA1 chuyển PG sang S khi X online → DR_READY → nâng X → trả PG canary → H0-R → arm H0-W level đã chọn → primary canary → mở rộng theo gate.
5. Qua Phase 3; trả trạng thái tạm theo 07, chạy POST và benchmark lại.
6. Khi có lỗi, dùng 10; không tự giảm level hoặc bỏ H0 gate để tiếp tục run.

## 3. Phạm vi mặc định

- Hop duy nhất: **16.2.5 → 16.2.15**, cephadm containerized, dịch vụ trọng tâm RBD + RGW. Những thông tin này là phạm vi thiết kế; phải đối chiếu cluster đích.
- Các nhánh CephFS, EC, multisite, mirror, PWL, Vault, RPM và custom module chỉ áp dụng khi inventory xác nhận có dùng.
- PA1 giữ X online, đưa đủ PG sang S rồi mới dừng X; giữ CRUSH weight gốc của X, dùng upmap theo batch.
- H0-R là return gate dùng chung: recovery hội tụ + deep-scrub mới sau recovery + H0-static verify đúng bản local X. H0-W chọn một trong ba level dưới đây cho mỗi run; không có level thứ tư.
- Prototype H0 tập trung RADOS full-object write vào object mới trong replicated pool ít I/O, kiểm soát writer. RBD/RGW vẫn phải đo native service SLO; chưa được tuyên bố H0 bảo vệ chúng nếu adapter chưa được nghiệm thu.
- Ghi riêng scope nâng cấp PA1 và scope H0 canary. PASS vài PG/corpus không bảo đảm H0 cho toàn bộ PG trên X; muốn mở rộng scope H0 phải lặp chuẩn bị, capability và gate tương ứng.
- Không lấy trạng thái lab trước đây làm trạng thái production hiện tại. Repo có thư mục comparison nhưng lần chỉnh này không tái kiểm toàn bộ source-comparison `00`–`15`; không kế thừa PASS của tài liệu thành bằng chứng thực thi.

| H0-W | Mã policy | Điều kiện bổ sung trước success, luôn giữ native durable completion |
| --- | --- | --- |
| Level 1 | `L1_PRIMARY_BUFFER` | Final logical buffer ở primary khớp Hclient |
| Level 2 | `L2_REPLICA_BUFFER` | Level 1 + buffer ở mọi replica bắt buộc khớp Hclient gốc |
| Level 3 | `L3_PERSISTED_READBACK` | Level 2 + read-back sau commit ở X và mọi replica bắt buộc khớp Hclient |

Các mức này là thiết kế gate trước success; không đổi tên thành static/observe/enforce. Native-only chỉ là cấu hình đối chứng khi đo.

## 4. Quy ước xuyên suốt

| Nhãn | Ý nghĩa |
| --- | --- |
| Bắt buộc kiểm tra | Phải có bằng chứng; kết quả có thể cho thấy không cần sửa |
| Bắt buộc sửa khi áp dụng | Có điều kiện cụ thể và cấu hình/luồng hiện tại không tương thích hoặc không an toàn |
| Khuyến nghị vận hành | Có ích để giảm rủi ro; không phải yêu cầu kỹ thuật chung của 16.2.15 |
| Tách change | Tuning, migration, repair hoặc tính năng mới có quy trình riêng |
| N/A | Có bằng chứng không dùng tính năng/không thuộc phạm vi |
| NOT_RUN / UNKNOWN | Chưa kiểm; không được ghi thành PASS hoặc N/A |

**Điều kiện hoàn tất:** đúng artifact, dịch vụ và dữ liệu đạt yêu cầu, các gate có bằng chứng, hiệu năng đạt ngưỡng đã chốt, trạng thái tạm đã được xử lý. `HEALTH_OK` hoặc nâng xong một OSD chưa đủ đại diện cho toàn bộ fleet.
