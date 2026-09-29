# 01 — OSD, PG, peering, recovery/backfill, scrub và EC: v16.2.15 → v17.2.7

**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./01-osd-pg-recovery.csv) có 465 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 1`, `trivial = 0`, **chưa phân loại = 464**; các số 0 không phải kết luận không có tác động.

## Phạm vi và phương pháp

Owner này phụ trách OSD, PG, peering, recovery/backfill, scrub và EC. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### OSD-001 — Queue cost và QoS/recovery path cho mClock

**CSV:** `src/osd/OSD.cc`. Endpoint diff thay `OSDService::queue_recovery_context` để dùng cost thực cho mClock, tính scrub event cost từ chunk size, và cập nhật `OSD::handle_conf_change`/QoS branch cho recovery, backfill, sleep settings. Pacific có mClock tùy chọn nhưng các đường này dùng logic cũ; Quincy mặc định dùng mClock theo [CFG-001](./06-config-defaults.md). Hunk thuộc các symbol trên ở `src/osd/OSD.cc`; commit liên quan gồm `c30f2729b4815e56229c711cf0789cb704aec5dd7`, `20fcfcb84aa39d26c6f624849beddf2926cc03e4`, `81c0ca6cdc623278f64efd1daf65887d57ece621`.

**Điều kiện:** OSD dùng scheduler mClock; khác biệt này không tự kích hoạt nếu config hiệu dụng tiếp tục là `wpq`. Trong mixed-version, OSD target và base có thể xử lý queue/recovery khác nhau theo scheduler hiệu dụng và vai trò PG; sau full upgrade, các OSD target dùng đường mới. Không có bằng chứng ở đây để định lượng IOPS, latency hay tốc độ backfill. **Evidence confidence:** high cho các nhánh code, medium cho mức tác động triển khai.

**Kiểm chứng:** lab/canary chạy client IO đồng thời recovery/backfill/scrub, ghi scheduler và effective config từng OSD, đo client latency, hàng đợi recovery và thời gian PG trở lại clean. So với baseline Pacific trong cùng workload; dừng rollout nếu vượt ngưỡng do dự án đặt trước. `src/test/test_mclock_priority_queue.cc`, `qa/standalone/misc/mclock-config.sh` và QA scheduler là bằng chứng coverage cần đọc sâu; chưa chạy.

Các hàng khác vẫn để trống `upgrade_impact` cho tới khi đọc diff/metadata; không gán `trivial` theo đường dẫn.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 465` và viết tóm tắt các cụm trivial.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
