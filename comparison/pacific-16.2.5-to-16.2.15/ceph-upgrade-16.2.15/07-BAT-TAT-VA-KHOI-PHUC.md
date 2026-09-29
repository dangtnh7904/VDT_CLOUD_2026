# Tạm dừng, giữ nguyên và khôi phục theo phase

[Mục lục](00-README.md) · [Điều kiện áp dụng](02-DIEU-KIEN-VA-THAY-DOI.md) · [Nhật ký state](12-BIEU-MAU-BANG-CHUNG.md)

## 1. Nguyên tắc sở hữu trạng thái

Mỗi thay đổi phải ghi `giá trị trước → giá trị tạm → điều kiện trả lại → giá trị cuối`, scope, owner và thời hạn. Chỉ hoàn nguyên state do đợt nâng tạo ra. Nếu ban đầu balancer off thì cuối change không tự bật on; nếu đã có upmap riêng thì không xóa hàng loạt.

## 2. Bảng thao tác theo ba phase

| Cơ chế | Trước nâng | Trong nâng | Sau nâng | Mức cần thiết |
| --- | --- | --- | --- | --- |
| Balancer | Lưu trạng thái/plan; tạm off trong window điều phối PA1 | Không chạy plan cạnh tranh | Review lượng remap rồi trả baseline, theo dõi QoS | Yêu cầu của window PA1 đã chọn |
| PG autoscaler | Lưu mode từng pool; tạm `warn`/`off` cho scope có nguy cơ split/merge | Chặn action PG ngoài manifest | Review recommendation; trả mode từng pool theo đợt | Khuyến nghị vận hành |
| CRUSH/topology/auto-provision | Chốt manifest, hoãn mutation cạnh tranh | Chỉ thay map thuộc PA đã kiểm | Khôi phục policy quản lý đúng nguồn spec | Cần kiểm soát phạm vi |
| `noout` | Không bật sớm cho cả fleet; chọn OSD/batch cần tránh out tự động khi restart ngắn | Theo dõi TTL và sức khỏe; cờ không bảo vệ khỏi lỗi dữ liệu | Bỏ cờ do change tạo sau khi OSD sẵn sàng và PG ổn định | Có điều kiện |
| `norecover` / `nobackfill` | Không bật mặc định | Cần recovery/backfill cho hội tụ; cờ đang chặn phải có disposition | Không để sót cờ tạm | Giữ recovery hoạt động |
| `norebalance` | Chỉ dùng khi nhánh đã thử tác động | Có thể làm backfill chờ; không là PG allowlist, không ngăn map đổi | Trả baseline sau kiểm map và QoS | Không là prerequisite |
| `noscrub` / `nodeep-scrub` | Xem lịch/backlog; chỉ hoãn nếu xung đột window | Giới hạn thời gian; không để kéo dài qua nhiều tháng | Trả lịch có kiểm soát, tránh dồn backlog | Có điều kiện |
| Primary-affinity | Lưu A0; điều chỉnh khi cần chuyển primary, kiểm actual primary | Chưa mở workload H0 trước H0-GR/GW; affinity không là write fence | Trả A0 khi PG đủ điều kiện, xác nhận primary thực | Công cụ PA1; admission là cơ chế riêng |
| CRUSH weight / override reweight | Lưu W0/R0 của X và S; S park 0 rồi weight dương nhỏ đã mô phỏng toàn map | Giữ X `in` và CRUSH weight gốc; chuyển bằng upmap; không drain X bằng weight=0 | Dọn state S và map từng bước theo journal; xem trước mọi remap | Đúng PA1; weight nhỏ không là quota/allowlist |
| Upmap | Lưu toàn bộ entry liên quan, kể cả cặp có sẵn | Chỉ sửa entry thuộc manifest | Phục hồi entry cũ; không `rm` mọi upmap của PG | Chỉ PA/balancer plan |
| OSD service `unmanaged` | Chỉ đặt nếu cần tránh reconcile/provision cạnh tranh và đã hiểu spec | Không coi nó là pause toàn bộ upgrade engine | Diff candidate/spec trước trả managed; tránh tự tạo OSD ngoài ý muốn | Không bắt buộc chung |
| RGW traffic drain | Lưu LB/endpoint và capacity | Nâng từng endpoint, direct test trước trả tải | Trả traffic theo nấc sau smoke/policy PASS | Cần theo khả năng HA |
| Alert silence | Chỉ silence alert dự kiến đúng scope/TTL | Giữ integrity, availability, capacity và client SLO hoạt động | Hết hạn/gỡ đúng silence của change | Không tắt toàn bộ alert |
| Scheduler/recovery tuning | Giữ effective baseline | Chỉ điều chỉnh có mục tiêu nếu gate yêu cầu; ghi hiệu quả | Trả baseline hoặc chốt cấu hình mới sau test riêng | Không đổi hàng loạt |
| H0-R | Tạo H0-static, kiểm local-X reader, lập budget deep-scrub cho PG return | Mỗi batch return trong scope H0: clean/đủ replica → fresh deep-scrub hoàn tất → local-X verify → `RETURN_VERIFIED` | Giữ evidence; return mới phải kiểm mới | Bắt buộc trong scope H0, cả ba level |
| H0-W admission | Đóng protected workload cho đến khi hooks/capability/reference sẵn sàng | Chỉ mở sau H0-GR/GW; lỗi thì chặn admission mới theo scope, không chặn peering/recovery cần thiết | Giữ hoặc đóng theo run; đối soát in-flight trước kết thúc | Bắt buộc; không dùng affinity thay admission |
| H0-W level/policy | Chọn L1/L2/L3 và pin policy revision/run; kiểm peer nếu L2/L3 | Không tắt verifier hoặc tự hạ level khi timeout; request đã nhận vẫn theo contract | Đổi/tắt chỉ sau đóng admission, đối soát và tạo run/policy mới | Cả ba level đều chặn trước SUCCESS_ACK |

**Balancer off không đóng băng CRUSH.** Đổi weight, add/remove OSD hay sửa upmap vẫn có thể đổi mapping và tạo recovery. Cần xem cả map dự báo lẫn map thực sau mỗi epoch. [S06](13-NGUON-VA-DOI-CHIEU.md)

Nếu đã hoãn scrub/deep-scrub để tránh tranh I/O, phải bố trí chạy kiểm targeted của H0-R trước khi cho PG đó qua H0-GR. Không đợi cuối fleet mới bật lại rồi dùng scrub cũ làm PASS; cách yêu cầu/cho phép scrub phải xác minh trên CLI/config thực. Deep-scrub là theo PG, không phải lệnh bảo đảm chỉ đọc một OSD.

## 3. Cách xử lý autoscaler trong đúng hop này

Để tương thích base 16.2.5, có thể dùng mode **từng pool** đã được CLI base hỗ trợ, lưu mode cũ rồi đặt `warn` hoặc `off` theo quyết định. Không copy lệnh/auto-pause behavior của Ceph mới nhất sang Pacific khi chưa kiểm binary.

Giữ freeze chỉ trong window hoạt động cần thiết. Một chương trình nâng kéo dài nhiều tháng không có nghĩa tắt autoscaler/balancer/integrity checks suốt nhiều tháng. Giữa các window phải có trạng thái vận hành và lịch xử lý backlog rõ ràng.

## 4. Thứ tự hoàn nguyên đề xuất

1. Với từng batch return trong scope H0, hoàn tất H0-GR rồi mới mở protected primary workload qua H0-GW. Mọi batch PA1 vẫn cần native gate; sửa từng entry tạm theo journal, không xóa hàng loạt upmap.
2. Bỏ `noout` tạm của batch đã hoàn tất khi điều kiện đạt.
3. Cho scrub/deep-scrub tiếp tục theo budget và kiểm backlog.
4. Review rồi phục hồi balancer; đợi tác động ổn định.
5. Review autoscaler từng pool và phục hồi mode; đợi split/merge nếu có kết thúc.
6. Dọn silence/maintenance/drain/temporary config theo journal và re-run client probes.
7. Nếu kết thúc pilot H0, đóng admission mới, đối soát in-flight và lưu kết quả; chỉ thay policy/hook sau khi không còn request phụ thuộc bảo đảm cũ.

Thứ tự 3–5 có thể thay theo tải và nhu cầu integrity thực tế; phải ghi lý do. Không làm tất cả cùng lúc vì sẽ khó phân biệt nguyên nhân regression.
