# Gate, ngưỡng và quyết định chuyển bước

[Mục lục](00-README.md) · [Nhật ký](12-BIEU-MAU-BANG-CHUNG.md) · [Khi STOP](10-STOP-FALLBACK-ROLLBACK.md)

## 1. Gate theo ba phase

Đây là ID **mới của bộ v2**; không đồng nhất với G00–G16 của checklist cũ. Đối chiếu ở [13](13-NGUON-VA-DOI-CHIEU.md).

| Gate | Checkpoint | PASS tối thiểu | HOLD/STOP nếu |
| --- | --- | --- | --- |
| G0 | Phase 1: khóa phạm vi | Base/target image/digest và delta đã hiểu; inventory điều kiện; owner và manifest có đủ | Sai/không xác định artifact hoặc phạm vi |
| G1 | Phase 1 và lặp trước batch | Quorum/MGR/service khỏe; PG ở baseline sạch; telemetry/client probes tươi; WARN có disposition | Mất quorum, lỗi dữ liệu, crash loop, thiếu replica ngoài kế hoạch hoặc monitoring mù |
| G2 | Phase 1 và lặp trước batch | Headroom từng đích; replica/EC đủ; nguồn phục hồi còn sẵn; rollback/forward-fix đã thử | Chỉ biết %free toàn cụm, PG unsafe hoặc không có đường phục hồi đã chọn |
| G3 | Trước first target process | PRE tests bắt buộc và CON áp dụng PASS; baseline/ngưỡng/cửa sổ đã khóa | Test bắt buộc NOT_RUN; config/consumer critical chưa tương thích |
| G4 | Sau MGR promote/MON rejoin | Active/quorum ổn định; cephadm/metrics/consumer áp dụng đúng; scope action không lệch | Migration/action loop, parse fail không có telemetry thay thế, MON không catch-up |
| G5 | Trước stop/nâng X hoặc batch | PA1 đạt **DR_READY**: X còn online khi chuyển PG; mọi PG liên quan đã ở S/peers, `up=acting`, clean/đủ replica; X không còn trong up/acting; `ok-to-stop` tươi cho **cả tập** | Dừng X khi copy chưa xong; chỉ kiểm vài PG canary; unexpected remap/capacity thiếu; chỉ có kết quả từng OSD riêng |
| G6 | Sau restart/rejoin/canary | Đúng image/device; mount/replay sạch; data-path PASS; PG tiến rồi hội tụ; SLO trong ngưỡng | Mismatch, data lost, replay error, timeout/recovery không tiến hoặc target sai |
| G7 | Trước mở rộng | Soak và test batch trước đủ; G1/G2 còn đúng; không backlog/rủi ro cộng dồn ngoài budget | Giảm replica tích lũy, đụng headroom/SLO, chưa đủ coverage cohort |
| G8 | Vào Phase 3 | Toàn bộ daemon trong scope target; action terminal; offline/ngoài scope có record | Bỏ sót daemon/client theo manifest hoặc service chưa ổn định |
| G9 | Nghiệm thu | POST + benchmark đạt; state tạm khôi phục có kiểm soát; aftercare và evidence hoàn chỉnh | Dữ liệu/chức năng sai; regression quá ngưỡng; chưa xử lý state tạm |

`ok-to-stop` đánh giá khả năng dừng theo trạng thái Ceph nhìn thấy; nó không đo SLO, tốc độ phục hồi, dung lượng spare dự kiến hay khả năng H0 chặn dữ liệu. Vì vậy G5 luôn kết hợp G2 và quan sát client.

## 2. Gate PA1 + H0 theo đúng Level 1–2–3

Đây là gate của thiết kế/pilot [11](11-PA1-H0-LEVEL-1-2-3.md), không phải tính năng đã có sẵn trong image Ceph upstream. **H0-R áp dụng cho cả ba level; cả ba level H0-W đều nằm trước SUCCESS_ACK.**

| Gate | Khi kiểm | PASS | HOLD/STOP |
| --- | --- | --- | --- |
| H0-G0 | Phase 1, trước nhận protected writes | Chọn một level/run; đúng artifact và hooks; reference contract, policy revision, fixture và test lab đạt; L2/L3 có protocol/capability ở mọi replica bắt buộc | Chỉ patch X nhưng cần C/D ở peer chưa hỗ trợ; thiếu immutable reference; chưa chứng minh reader L3; test bắt buộc NOT_RUN |
| H0-GR | Phase 2, sau **mỗi batch return trong scope H0** và trước workload primary | Recovery/backfill đã hội tụ đủ replica; deep-scrub **mới sau recovery** đã hoàn tất cho PG scope; local-X verify khớp H0-static đúng object/version/range → `RETURN_VERIFIED` | Dùng scrub cũ; chỉ GET qua peer/cache; mismatch, chưa hội tụ hoặc không chứng minh đọc bản của X |
| H0-GW | Trước mở admission và trên từng protected write | Actual X/PG/epoch đúng policy; A/B/E ở L1, thêm C mọi replica bắt buộc ở L2, thêm D trên X và mọi replica bắt buộc ở L3; native durable completion cùng toàn bộ kết quả integrity cần thiết đều đạt | Mismatch, thiếu reference/capability, timeout, stale proof, policy/epoch đổi chưa xử lý; không tự hạ level để cho ACK |
| H0-GC | Phase 3, đóng run | Request/attempt được đối soát; không còn trạng thái commit/verify mơ hồ chưa xử lý; đủ coverage và số đo của level; admission/policy và evidence có trạng thái cuối rõ | Đếm native committed như integrity PASS; bỏ qua request retry/timeout; claim mức bảo đảm vượt coverage thực |

`H0-GW` gồm điều kiện mở workload và invariant trong từng request; một lần test PASS không thay việc kiểm từng write. `min_size` không định nghĩa số peer phải H0-verify trong prototype: scope là replicated PG khỏe, đủ replica, xác định đầy đủ tập bắt buộc. Chi tiết A–E và xử lý commit-but-unverified ở [11](11-PA1-H0-LEVEL-1-2-3.md); bài chứng minh ở [15](15-TEST-H0-LEVEL-1-2-3.md).

Khi đang phát triển trong lab, có thể ghi NOT_RUN để theo dõi phần chưa implement. Trạng thái đó **không cho GO protected canary production**. Kiểm tra native chỉ chứng minh phần native, không thay H0-G0/GR/GW.

## 3. Ngưỡng phải điền trước canary production

Không có bộ số an toàn chung cho 1.600 OSD. Bảng này bắt buộc **điền**, không bắt buộc một tỷ lệ do tài liệu tự đặt.

| Signal | Baseline/cửa sổ | Warning | STOP | Cửa sổ xác nhận / resume | Owner |
| --- | --- | --- | --- | --- | --- |
| RBD p95/p99 theo read/write và profile | Chưa điền | Chưa điền | SLO tuyệt đối + regression budget | Chưa điền | |
| RGW p95/p99, timeout/5xx theo operation | Chưa điền | Chưa điền | Chưa điền | Chưa điền | |
| Client throughput / offered load | Chưa điền | Chưa điền | Chưa điền | Chưa điền | |
| PG peering/degraded/remapped và thời gian | Chưa điền | Chưa điền | Giới hạn cho batch | Chưa điền | |
| Recovery bytes/s, backlog, ETA, stall | Chưa điền | Chưa điền | Chưa điền | Chưa điền | |
| Mỗi OSD/DB/WAL/MON free và tăng trưởng | Chưa điền | Chưa điền | Theo ngưỡng thực + dự phòng | Chưa điền | |
| CPU/RSS, disk await/queue, network | Chưa điền | Chưa điền | Chưa điền | Chưa điền | |
| Telemetry age / mất probe | Chưa điền | Chưa điền | Tối đa mất quan sát | Chưa điền | |
| Thời gian restart, soak, window còn lại | Chưa điền | Chưa điền | Deadline chuyển recovery | Chưa điền | |
| H0 hash/verify queue, ACK p99, readback I/O, verify timeout | Theo từng level | Chưa điền | Budget đã chốt cho level; mismatch/no-proof không được SUCCESS_ACK | Chưa điền | |
| H0 request committed nhưng chưa verified | Số lượng, tuổi và identity | Chưa điền | Dừng admission khi vượt budget; không tự xác nhận thành công | Quy trình đối soát | |

Mất quorum, checksum mismatch, acknowledged-data loss, `inconsistent`/`unfound` mới, sai artifact/device hoặc vi phạm quyền truy cập là STOP ngay cho phạm vi bị ảnh hưởng; không chờ đủ cửa sổ p99.

Ví dụ cách điền **chỉ để minh họa phép đo**: nếu baseline p99=20 ms, SLO=40 ms, regression budget=20%, trần so sánh là `min(40, 20×1,2)=24 ms`. Không lấy 20% làm mặc định production. Nếu baseline đã sát hoặc vượt SLO, xử lý trước, không dùng baseline xấu để hợp thức hóa target.

## 4. Capacity và thời gian batch

- Tính byte sẽ nhận ở **từng** đích theo PG/data thực, cộng tăng trưởng ghi trong window, dự phòng recovery do sự cố và metadata/DB/WAL.
- Không suy `24 PB / 1.600` là lượng byte mỗi OSD phải chuyển: phải biết 24 PB là logical hay raw, pool replica/EC, tỷ lệ sử dụng và phân bố.
- Thời gian window phải chứa chuẩn bị + thay daemon + hội tụ + verify + soak + khoảng dành cho xử lý sự cố. Đến mốc hết thời gian dự phòng thì không mở batch mới.
- Giá trị ngưỡng full/backfillfull/nearfull đọc từ cụm. Không nâng chúng để vượt gate dung lượng.

## 5. PASS, N/A và resume

PASS cần timestamp, scope, artifact, kết quả, evidence và người xác nhận. N/A cần chứng minh điều kiện không tồn tại; “chưa kiểm” là NOT_RUN.

STOP = dừng mở rộng và xử lý phạm vi nguy hiểm, không mặc định tắt cả cluster. Resume chỉ khi nguyên nhân có cách xử lý, gate bị lỗi được chạy lại và signal ổn định qua cửa sổ đã chốt. Thay scope/cohort/artifact phải đánh giá lại những gate bị tác động.
