# Phase 3 — Sau nâng cấp và nghiệm thu

[Mục lục](00-README.md) · [Phase 2](04-PHASE-2-CANARY-VA-ROLLOUT.md) · [Test sau nâng](08-TEST-CHUC-NANG.md)

## 1. Mục tiêu và kết quả cần có

Chứng minh hệ thống ổn định ở target, trả đúng trạng thái vận hành, so sánh hiệu năng công bằng và bàn giao aftercare. Phase này kết thúc bằng kết luận theo evidence, không chỉ bằng trạng thái upgrade complete.

## 2. Cluster cần đạt trạng thái nào?

- Daemon trong scope đúng version/digest; danh sách offline/ngoài scope có disposition rõ.
- Quorum/MGR/service ổn định; mọi PG trở lại trạng thái dự kiến, không có dữ liệu inconsistent/unfound hoặc recovery kẹt.
- Không còn mount/replay/activation failure, restart loop hoặc tăng trưởng resource chưa giải thích.
- Queue cephadm đã hoàn tất hành động dự kiến; không bỏ lại MDS preparation/traffic drain/maintenance sai ý định.
- Nguồn phục hồi và artifact trước nâng vẫn được giữ đến hết retention đã chốt.
- Các PG thuộc scope H0 đã trả về X có `RETURN_VERIFIED` của H0-R; mỗi run H0-W ghi đúng level, policy revision, primary/acting set và coverage. PG ngoài scope có native test riêng, không được ghi H0 PASS. Không còn request `COMMITTED_UNVERIFIED` hoặc trạng thái không rõ chưa có disposition.

## 3. Thay đổi hoặc hoàn nguyên ở đâu?

| Việc | Điều kiện thực hiện | Cách xác nhận |
| --- | --- | --- |
| Khôi phục flags/weight/affinity/upmap | PG và coverage canary đạt; chỉ entry do change tạo | So change journal, OSDMap và actual PG; giữ nguyên ngoại lệ tồn tại trước |
| Khôi phục scrub/deep-scrub | Đủ headroom/QoS | Theo dõi backlog, cho chạy dần để tránh dồn tải |
| Khôi phục balancer | Xem trước tác động và đạt ngưỡng | Theo dõi remap/recovery sau bật; không bật đồng thời mọi automation |
| Khôi phục autoscaler | Recommendation/split/merge đã review | Trả đúng mode từng pool; baseline `off`/`warn` không tự chuyển thành `on` |
| Khôi phục endpoint/service management | Smoke/direct/LB test đạt; không còn tác động ngoài manifest | Session/request continuity và service spec đúng |
| Dọn key hoặc workaround tạm | Không còn base consumer cần key, đã hết nhu cầu và có snapshot | Effective config từng role; không chỉ config dump |
| Cập nhật công cụ quản trị host | CLI/cephadm host cần phiên bản tương thích target | Phiên bản thực của `cephadm shell` và `ceph-common`; không suy từ image daemon |
| Rules/query/alert | Parser và rule test đạt trước reload | Runtime rules + test notification; file trên disk không đủ |
| H0-W và admission của workload canary | Giữ level đã chọn đến hết run; muốn kết thúc/đổi level phải đóng admission và đối soát request đang chạy | Không mất gate của request đã nhận; request chưa xác minh không được đổi thành SUCCESS_ACK |
| H0-R và corpus H0-static | Lưu kết quả fresh deep-scrub, local-X verify và version/range đã kiểm | Có bằng chứng cho từng batch return; không dùng lại PASS của batch trước |

Lệnh và thứ tự hoàn nguyên xem [07](07-BAT-TAT-VA-KHOI-PHUC.md). Công cụ host cần tương thích theo [S03](13-NGUON-VA-DOI-CHIEU.md); không mặc định phải thay mọi client thành 16.2.15 nếu chúng ngoài scope và còn được hỗ trợ.

Không tự chạy `require-osd-release` chỉ để xóa cảnh báo: nếu đã `pacific` thì hop patch không cần đổi; nếu còn thấp, phải kiểm OSD cũ/offline và xử lý như quyết định feature-floor riêng.

## 4. Bật lại vào lúc nào?

1. Gỡ cờ bảo vệ tạm của từng OSD đã hoàn tất khi gate cho phép; không đợi cuối cả fleet nếu không cần.
2. Sau rollout, phục hồi integrity scheduling theo budget, rồi placement automation từng mục; quan sát giữa hai thay đổi.
3. Chờ các công việc khôi phục hội tụ trước benchmark “after steady-state”. Nếu đo lúc còn backlog thì gắn nhãn “post-upgrade catch-up”.
4. Lấy thêm quan sát ở chế độ vận hành bình thường sau khi các automation trở lại baseline.

Không có mốc “sau nâng bật hết”. Mỗi dòng cần giá trị cũ, người sở hữu, điều kiện phục hồi và kết quả kiểm.

## 5. Gate sau nâng

- [ ] **G8:** đủ scope target và trạng thái ổn định để bắt đầu nghiệm thu.
- [ ] **G9:** dữ liệu, chức năng, performance, cleanup và soak đạt; ngoại lệ còn lại có owner/thời hạn.
- [ ] **H0-GC:** run đã đối soát, kết quả đúng contract của level, chi phí đo được và trạng thái giữ/kết thúc H0 được ghi rõ.

Gate G9 không đòi IOPS phải tăng. Nó đòi kết quả đúng và performance không vi phạm ngưỡng đã thống nhất; những cải thiện riêng được chứng minh bằng bài đo phù hợp.

## 6. Test cần chạy

| Nhóm | Test |
| --- | --- |
| Toàn vẹn | POST-02: old-data và new-data checksum/metadata đúng phiên bản; scrub có phạm vi và bằng chứng |
| Dịch vụ | POST-01/POST-04 và CON-* có dùng, gồm RGW policy, RBD snapshot/lock/diff theo scope |
| Control/config | POST-03: flags/config/specs/rules đúng trạng thái cuối |
| Hiệu năng | Lặp P-01/P-02/P-03 cùng profile; P-05 chỉ khi có fast-diff client path; báo P-07 |
| Theo dõi ổn định | POST-05: chu kỳ tải đại diện, restart/error/backlog/resource trend |
| PA1 + H0 | EXT-PA1 cleanup; tổng hợp R01…03, các H0-W test áp dụng và P01 tại [15](15-TEST-H0-LEVEL-1-2-3.md); P-06 đo chi phí từng level |

Chi tiết tại [08](08-TEST-CHUC-NANG.md) và [09](09-TEST-HIEU-NANG.md). Không chạy fault injection/power-cut trên production để hoàn thành phase.

## 7. Tiêu chí kết thúc và aftercare

Lưu so sánh trước/sau, tổng thời gian/byte recovery, danh sách còn ngoài scope, kết quả restore rehearsal, cấu hình cuối và những việc để change sau. Chốt người theo dõi, thời gian theo dõi tiếp, retention và điều kiện mở lại incident.

Chỉ đóng đợt nâng sau G9 và H0-GC trong scope PA1 + H0 này. PASS cần đúng custom H0 build đã thử; không suy từ PASS image upstream, không chuyển kết luận sang Quincy/Reef hoặc adapter RBD/RGW chưa implement.
