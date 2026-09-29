# Phase 1 — Trước nâng cấp

[Mục lục](00-README.md) · [Phase 2](04-PHASE-2-CANARY-VA-ROLLOUT.md) · [Lệnh đọc trạng thái](14-LENH-THAM-KHAO.md)

## 1. Mục tiêu và kết quả cần có

Chứng minh cụm đủ khỏe, artifact phù hợp, canary có phạm vi rõ, baseline đo được và có đường phục hồi. Kết quả là một change manifest hoàn chỉnh và quyết định có đủ điều kiện bắt đầu canary hay chưa.

## 2. Cluster hiện tại phải ra sao?

| Phần | Trạng thái yêu cầu trước thay đổi |
| --- | --- |
| MON | Quorum ổn định; đồng hồ/network bình thường; dung lượng từng MON đủ cho cửa sổ nâng và tăng trưởng đã đo |
| MGR | Active hoạt động và có standby khỏe cho failover cephadm; module điều khiển không lỗi |
| OSD/PG | Mặc định bắt đầu ở trạng thái PG active+clean; không có degraded/undersized/incomplete/inconsistent/unfound hoặc recovery bất thường chưa xử lý |
| Host | Các host của rollout online, SSH/control path và runtime hoạt động; không có maintenance/mutation cạnh tranh |
| Capacity | Đủ headroom từng OSD/DB/WAL/MON và đích nhận dữ liệu, dưới các ngưỡng full thực tế; xét cả recovery của batch và dự phòng sự cố |
| RBD/RGW | Read/write probe đúng; error/latency đáp ứng SLO; đủ serving capacity khi drain/restart một thành phần |
| Monitoring | Có telemetry client và cluster tươi, dùng được khi MGR đổi; có đường xác định STOP |
| Sự cố tồn tại | Mọi WARN có nguyên nhân; lỗi dữ liệu/quorum/khả năng phục hồi phải đóng; cảnh báo vận hành không ảnh hưởng được ghi ngoại lệ cụ thể |

`HEALTH_WARN` do cờ vận hành đã biết không có cùng ý nghĩa với clock skew, thiếu replica hay MON sắp hết chỗ. Không mute/clear crash để biến bảng thành “đủ điều kiện”. Danh sách blocker chính xác nằm ở [G1/G2](06-GATE-VA-NGUONG.md).

## 3. Chuẩn bị hoặc thay đổi ở đâu?

1. **Manifest:** chốt base image thực tế, target digest, FSID, daemon/client scope, cohort HDD/SSD, LVM/raw, DB/WAL, encrypted và workload. Image tùy biến phải đối chiếu delta với upstream.
2. **Registry/host:** thử target trên từng cohort và bảo đảm từng host pull được image đã pin. Từ Pacific 16.2.6, hướng dẫn Ceph dùng Quay; không mặc định có tag `docker.io/ceph/ceph:v16.2.15`. [S03](13-NGUON-VA-DOI-CHIEU.md)
3. **Config/consumer:** đi qua bảng C01–C20 trong [02](02-DIEU-KIEN-VA-THAY-DOI.md). Sửa đúng hàng áp dụng; với H0 xác nhận build/capability thực, không chỉ config/UI.
4. **Control state:** lưu config, CRUSH/OSDMap/MonMap, specs, upmap, weights, affinity, flags, autoscale/balancer state; lưu đúng scope trước khi sửa.
5. **Phục hồi:** chốt fallback/forward-fix/rebuild cho từng role; diễn tập khả năng phục hồi dữ liệu canary. Export map/config không phải bản sao payload.
6. **Phạm vi canary:** chọn OSD đầu tiên đủ an toàn nhưng đại diện; ưu tiên ít PG I/O/primary, peers còn dư tài nguyên, không chung failure domain nguy hiểm. Đổi loại media/layout thì mở một cohort canary mới.
7. **PA1:** chốt S, P_X, batches và effective placement toàn cụm; giữ X online trong lúc chuyển PG. Chỉ dừng/nâng khi DR_READY: X không còn trong up/acting, P_X đủ replica trên S/peers và `ok-to-stop` PASS.
8. **H0:** chọn một policy `L1_PRIMARY_BUFFER`, `L2_REPLICA_BUFFER` hoặc `L3_PERSISTED_READBACK`; chốt H0-static và Hclient riêng. Inventory capability X và mọi peer bắt buộc; L2/L3 không chỉ cần patch X. Prototype là RADOS object mới/full-object write, không overwrite trong verify window. [11](11-PA1-H0-LEVEL-1-2-3.md)

Không cần deep-scrub đồng loạt 24 PB ngay trước change. Kiểm backlog và kết quả gần nhất; ưu tiên PG candidate theo budget. Lần scrub trước nâng không thay **lần deep-scrub mới sau recovery** mà H0-R yêu cầu ở Phase 2.

## 4. Tạm dừng hoặc giữ nguyên gì?

- Tạm dừng thay topology/CRUSH, auto-provision và jobs thay PG có thể xung đột với manifest; chọn phạm vi và thời hạn theo [07](07-BAT-TAT-VA-KHOI-PHUC.md).
- Chốt chính sách balancer/autoscaler cho window. Không để một kế hoạch remap khác chạy đồng thời với PA1.
- Giữ recovery cần thiết hoạt động. Không bật `norecover`/`nobackfill` toàn cụm làm mặc định.
- Nếu cần tránh đụng scrub trong window, chỉ tạm hoãn theo policy có hạn; không tắt integrity checks nhiều tháng.
- Không thay scheduler, bật feature mới hoặc repair/provision để ghép thêm vào change.

## 5. Gate trước nâng

- [ ] **G0:** phạm vi/artifact/điều kiện áp dụng đã chốt.
- [ ] **G1:** cluster, dịch vụ và telemetry đạt điều kiện.
- [ ] **G2:** capacity, redundancy và đường phục hồi đạt yêu cầu.
- [ ] **G3:** preflight compatibility và test chuẩn bị đã PASS ở phạm vi canary.
- [ ] **H0-G0:** level/profile/reference/capability và lỗi/retry/failover tests tương ứng đã được nghiệm thu trên lab trước production H0 run.

G3 trước first MGR không đòi target đã chạy production; dùng rehearsal đúng artifact/path và test trên staging/clone. Ngay sau target promotion phải kiểm lại ở môi trường thật bằng G4.

## 6. Test cần chạy

| Nhóm | Test / đầu ra |
| --- | --- |
| Chức năng | PRE-01…PRE-06 tại [08](08-TEST-CHUC-NANG.md); test điều kiện CON-* nếu feature có dùng |
| Baseline tải ổn định | P-01 RBD, P-02 RGW, P-03 tài nguyên theo [09](09-TEST-HIEU-NANG.md) |
| Diễn tập rollout | Restart/activation, control-plane promotion và phục hồi trên môi trường phù hợp |
| PA1/H0 | EXT-PA1; H0 R01–R03/W01–W10 theo level tại [15](15-TEST-H0-LEVEL-1-2-3.md); chi phí P-04/P-06 |

Nên lưu quan sát sản xuất bao phủ chu kỳ tải cao/thấp; thời lượng chính xác được chốt theo workload. Benchmark tổng hợp chạy trên tài nguyên test riêng, với tải giới hạn và stop threshold.

## 7. Tiêu chí ra khỏi phase

G0–G3 và H0-G0 PASS ở phạm vi production canary; baseline/ngưỡng đã khóa, nguồn phục hồi còn sẵn. Nếu đang phát triển H0 trên lab disposable, có thể chạy test để tìm lỗi nhưng ghi đúng NOT_RUN/FAIL, chưa tuyên bố GO cho protected production run. Lưu quyết định tại [12](12-BIEU-MAU-BANG-CHUNG.md).
