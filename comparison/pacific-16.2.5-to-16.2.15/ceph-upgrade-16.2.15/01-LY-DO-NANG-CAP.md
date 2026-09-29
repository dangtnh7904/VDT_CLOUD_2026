# Vì sao nâng lên 16.2.15?

[Mục lục](00-README.md) · [Điều kiện thay đổi](02-DIEU-KIEN-VA-THAY-DOI.md) · [Cách đo hiệu năng](09-TEST-HIEU-NANG.md)

## 1. Mục tiêu của hop này

Chọn 16.2.15 để đưa cụm 16.2.5 lên bản vá cuối của cùng nhánh Pacific, nhận các bản sửa tích lũy và tạo một mốc vận hành đã được kiểm chứng trước hop tiếp theo. Không cần đi qua từng bản 16.2.6, 16.2.7… như các lần triển khai riêng; phải diễn tập đúng đường đi trực tiếp và đúng image thực tế.

Đây là lựa chọn của kế hoạch, **không phải khẳng định mọi đường nâng lên major sau đều bắt buộc qua đúng 16.2.15**. Mỗi hop sau cần đọc lại yêu cầu của phiên bản đích.

Pacific đã hết vòng đời upstream; bảng phát hành ghi mốc 04/03/2024. Vì vậy, trong kế hoạch năm 2026, 16.2.15 là điểm trung gian, không phải đích dài hạn còn được upstream bảo trì. Nếu dùng bản vendor, đối chiếu hợp đồng và backport của vendor. [S01](13-NGUON-VA-DOI-CHIEU.md)

## 2. Lợi ích cụ thể và thời điểm có hiệu lực

| Nhóm | Lợi ích có cơ sở | Có hiệu lực khi nào? | Cách chứng minh trên hệ thống |
| --- | --- | --- | --- |
| RGW security | 16.2.15 sửa kiểm tra bucket trong Browser POST policy, CVE-2023-43040 | RGW phục vụ request đã chạy bản có fix | Test POST hợp lệ và trường hợp bucket trái policy trên từng endpoint; không chỉ kiểm HTTP 200 |
| RBD fast-diff | Tối ưu diff từ đầu image, whole-object, fast-diff hợp lệ và lấy được exclusive lock; liên quan QEMU live disk sync/backup | Đường client/librbd có fix thực sự được dùng | Đo thời gian diff + tính đúng kết quả; nâng OSD riêng không kích hoạt lợi ích này |
| MON/OSD | Có bản sửa health store tăng không giới hạn và bảo vệ min_size trong async recovery | MON/OSD đi qua code path liên quan | Theo dõi MON disk growth, recovery, PG và availability; không coi patch là cách tự giải phóng ổ MON đã đầy |
| BlueStore và lịch sử store cũ | Nhận các bản vá tích lũy; ví dụ sửa lỗi chuyển OMAP của store nâng từ trước Pacific | Đúng lịch sử store và đường thao tác liên quan | Kiểm history, thử clone khi cần; không tự chạy repair để “kích hoạt fix” |
| Quản lý rollout | Target MGR hỗ trợ bộ lọc staggered upgrade, có từ 16.2.11 | MGR điều khiển đã được nâng và kiểm tra | Canary phạm vi nhỏ, so manifest thực tế với dự kiến |
| Vận hành | Có các sửa lỗi activation, metrics và hành vi module trong khoảng phiên bản | Tùy daemon, client hoặc package được nâng | Đo thời gian restart, xác nhận scraper/alert và activation từng topology |

Nguồn cụ thể: [S02–S05 và S10–S13](13-NGUON-VA-DOI-CHIEU.md). Lợi ích trong bảng chỉ áp dụng khi artifact triển khai chứa fix và workload chạm đúng đường đó.

## 3. Tác động tới hiệu năng cần trình bày thế nào?

### 3.1 Điều có thể kỳ vọng

- Giảm gián đoạn do những lỗi đã sửa nếu cụm đang chịu đúng loại lỗi đó; đây chủ yếu là lợi ích ổn định và khả năng phục hồi.
- Rút ngắn tác vụ diff/backup trong trường hợp RBD nêu trên.
- Quản lý rollout nhỏ hơn giúp kiểm soát chi phí restart và recovery. Đây là lợi ích quy trình, không phải tốc độ đĩa tăng lên.

### 3.2 Điều chưa được phép kết luận

- Chưa có số liệu để nói “IOPS tăng X%”, “latency giảm Y%” hoặc toàn cụm nhanh hơn.
- Chỉ sửa perf counter có thể làm số đo khác đi mà hiệu năng thật không đổi.
- Fix có thể đổi backpressure: `osd_client_message_cap` upstream chuyển từ 0 sang 256. Phải đo queueing, latency và memory theo tải thật. `osd_op_queue` của cả hai tag vẫn mặc định `wpq`; hop này không buộc đổi sang mClock. [S08](13-NGUON-VA-DOI-CHIEU.md)

### 3.3 Chi phí tạm thời khi đang nâng

Restart làm thay đổi khả năng phục vụ trong thời gian ngắn; peering/recovery/backfill có thể tranh chấp disk, CPU, DB/WAL và network. PA1 còn có chi phí di chuyển dữ liệu ra/về. Vì vậy phải đo riêng ba trạng thái: trước nâng, trong rollout và sau hội tụ; không lấy benchmark đang backfill làm hiệu năng ổn định của phiên bản mới.

Với quy mô kế hoạch khoảng 1.600 OSD / 24 PB, quyết định batch size phải dựa vào byte di chuyển, PG giao nhau, failure domain và SLO. Dung lượng dự phòng tổng của cụm không chứng minh từng đích backfill còn đủ chỗ.

### 3.4 PA1 và H0 bổ sung gì cho đợt nâng này?

PA1 chuyển dữ liệu sang S/peers khi X còn online, đạt DR_READY rồi mới dừng X; đổi lại phải trả chi phí copy ra/về và quản lý map. H0-R thêm bằng chứng dữ liệu nhận lại trên X trước primary canary. H0-W thêm điều kiện toàn vẹn trước success: L1 kiểm buffer primary, L2 thêm buffer replica, L3 thêm persisted read-back trên mọi bản bắt buộc.

Đây là bảo đảm/chi phí của phương án dự án, **không phải feature tự xuất hiện khi cài 16.2.15**. H0 chưa triển khai trong nguồn hiện tại; không có số đo để kết luận level nào đạt SLO. Chi tiết tại [11](11-PA1-H0-LEVEL-1-2-3.md), chi phí tách riêng tại P-06 trong [09](09-TEST-HIEU-NANG.md).

## 4. Tiêu chí thành công của đề xuất

1. Đường dữ liệu RBD/RGW đúng, không mất dữ liệu đã xác nhận theo durability contract.
2. Không có suy giảm vượt SLO và ngưỡng chênh lệch đã chốt tại [06](06-GATE-VA-NGUONG.md).
3. Xác nhận các lợi ích theo workload thực; trường hợp không dùng tính năng được ghi N/A.
4. Có số đo thời gian và chi phí từng batch để ước lượng lộ trình còn lại.
5. Có phương án phục hồi khả thi; không coi đổi lại image OSD là rollback chắc chắn.

Mục tiêu nghiệm thu tối thiểu là **tính đúng, độ ổn định và không suy giảm vượt ngưỡng**. Tăng hiệu năng là kết quả cần đo, không là lời hứa của kế hoạch.
