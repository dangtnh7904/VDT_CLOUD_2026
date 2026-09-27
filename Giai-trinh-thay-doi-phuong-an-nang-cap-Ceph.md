# Giải trình thay đổi phương án nâng cấp Ceph theo yêu cầu production

Em điều chỉnh hai phương án trong kế hoạch theo hướng **duy trì đủ replica trước khi dừng OSD và kiểm soát phạm vi di chuyển dữ liệu**. Với bối cảnh dự án khoảng **1.600 OSD, 24 PB dữ liệu, phục vụ RGW/RBD**, cụm backup khoảng 100 TB không đủ chứa toàn bộ dữ liệu. Vì vậy, phương án nâng cấp cần bảo vệ khả năng phục vụ và mức dự phòng ngay trên cụm production, đồng thời kiểm soát tải phát sinh để đáp ứng mục tiêu triển khai trong khoảng sáu tháng.

Trong phần dưới, **X** là OSD cần nâng, **S** là spare và **Y/Z** là các replica còn lại. Ví dụ sử dụng replicated pool `size=3`, `min_size=2`; cần đánh giá riêng nếu production dùng cấu hình khác hoặc erasure coding.

| Phương án | Cách thực hiện chính | Đánh đổi khi áp dụng production |
|---|---|---|
| **PA1 cũ: giữ store cũ** | Chuyển primary khỏi X, dừng X để giữ dữ liệu cũ, rồi chuyển các PG sang S trước khi nâng. | Có khoảng thời gian toàn bộ PG liên quan thiếu một replica hoạt động trong lúc tạo bản sao thay thế. |
| **PA2 cũ: drain bằng weight** | Giữ X chạy, đưa CRUSH weight về 0, đợi drain hoàn tất, nâng rồi tăng weight trở lại. | Chờ đủ replica trước khi dừng được, nhưng một lần đổi weight có thể tạo nhiều PG chờ di chuyển. |
| **PA1 mới: Native Maintenance-DR** | Giữ X chạy, dùng upmap chuyển từng batch PG sang S; chỉ dừng X khi toàn bộ PG đã đủ replica tại đích. | Dùng cơ chế Ceph sẵn có; cần quản lý mapping, tài nguyên và nhật ký thay đổi chặt chẽ. |
| **PA2 mới: Maintenance Shadow Replica** | Tạo bản sao tạm S*, đồng bộ khi X còn chạy, kiểm chứng và promote thành replica chính thức trước khi dừng X. | Chủ động chuẩn bị bản sao; cần phát triển và kiểm thử tính năng mới trong Ceph. |

**Lý do điều chỉnh PA1: tránh chủ động kéo dài khoảng giảm dự phòng.** PA1 cũ ưu tiên giữ store có dữ liệu lịch sử bằng cách dừng X trước khi dữ liệu được chuyển hết sang S. Trong khoảng này, các PG ban đầu có `[X,Y,Z]` chỉ còn Y/Z hoạt động. Nếu một peer tiếp tục lỗi trước khi S hoàn tất, PG có thể chỉ còn một replica khả dụng và không đáp ứng `min_size=2` để tiếp tục ghi.[1] Canary 1–2 PG sau nâng không thu hẹp khoảng rủi ro này, vì thao tác dừng X ảnh hưởng toàn bộ PG đang phụ thuộc X. Với lượng dữ liệu lớn, thời gian tạo bản sao có thể dài và phải cạnh tranh tài nguyên với workload thực tế.

PA1 mới đổi thứ tự: **giữ X online → chuyển từng batch sang S → xác nhận `[S,Y,Z]` đủ replica, `active+clean` → kiểm tra `ok-to-stop` → dừng/nâng X**. Sau nâng, trả 1–2 PG canary về X, kiểm chứng rồi mở rộng theo batch. Khi X offline, nếu một replica còn lại lỗi thì vẫn còn hai bản sao hợp lệ theo giả định trên. Đánh đổi được chấp nhận là X có thể cleanup các PG đã chuyển, nên không cam kết giữ nguyên payload cũ hoặc chỉ đồng bộ delta khi trả PG về. Bài kiểm thử nâng store chứa dữ liệu lịch sử vẫn cần được duy trì riêng.

**Lý do thay PA2 drain weight làm hướng chính: cần điều phối chính xác hơn ở quy mô lớn.** PA2 cũ đã giữ X online và đợi đích đủ replica trước khi dừng; đây vẫn là một phương án hợp lệ nếu đủ dung lượng và chấp nhận ngân sách di chuyển. Hạn chế là đưa CRUSH weight về 0 làm thay đổi placement và trọng số bucket liên quan.[2] Dữ liệu có thể được phân phối tới nhiều OSD, còn tăng weight sau nâng tạo thêm một lượt di chuyển. Giới hạn tốc độ backfill giúp giảm tải, nhưng không tự giới hạn tập PG bị remap xuống đúng một batch nhỏ.

PA1 mới vì thế **kết hợp khả năng chọn PG của PA1 cũ với nguyên tắc giữ X online của PA2 cũ**. Upmap cho phép điều chỉnh placement theo PG.[3] Mỗi batch được xét theo byte, tải disk/network và p95/p99 của RGW/RBD; chỉ cấp batch tiếp theo sau khi hội tụ. Tuy nhiên, tắt balancer không đóng băng CRUSH, weight nhỏ không phải quota, và mapping phải được đối chiếu lại khi topology thay đổi hoặc có OSD lỗi.

**PA2 mới là hướng phát triển để quản lý bản sao bảo trì bằng trạng thái rõ ràng.** S* được đồng bộ bất đồng bộ khi `[X,Y,Z]` còn hoạt động, chưa tham gia đường xác nhận ghi thông thường. Trước khi promote, thiết kế yêu cầu kiểm tra PG version, dữ liệu còn thiếu, integrity và barrier để xử lý các ghi phát sinh trong lúc đồng bộ. Chỉ sau khi S trở thành replica hợp lệ và PG hội tụ mới cho phép dừng X. Cách này hướng tới giảm thao tác upmap thủ công; vẫn phải copy dữ liệu và tiêu thụ disk/network. Không chờ S* trong ACK cũng không bảo đảm latency không tăng do tranh chấp tài nguyên. Barrier, promotion, restart và tương thích mixed-version cần được chứng minh bằng kiểm thử lỗi; **PA2 hiện là đề xuất tính năng, chưa phải giải pháp production đã hoàn thiện**.

**Đề xuất triển khai và tiêu chí đánh giá.** Em ưu tiên PA1 mới làm ứng viên triển khai trước, đồng thời phát triển PA2 mới theo nhánh R&D. Việc chấp nhận production cần dựa trên:

- **Dự phòng thực tế:** spare đủ dung lượng và đúng failure domain; diễn tập thêm một OSD lỗi khi X offline. Mục tiêu này là dự phòng trong cụm khi bảo trì, không thay thế backup hoặc DR cấp site; thời gian peering và ảnh hưởng I/O phải được đo.
- **Chi phí và tiến độ:** đo tổng byte copy ra/về, thời gian hội tụ, kiểm chứng và QoS. Batch nhỏ giới hạn tải đồng thời, không giảm mặc nhiên tổng dữ liệu phải copy. Plan hiện mới mô tả từng OSD cho hop `16.2.5 → 16.2.15`; chưa đủ căn cứ cam kết tiến độ toàn cụm hoặc nâng nhiều OSD song song.
- **Khả năng kiểm soát lỗi:** canary, checksum/deep-scrub, ngưỡng dừng và phục hồi placement phải có bằng chứng. Khôi phục mapping không đồng nghĩa binary cũ luôn mở lại được store sau nâng. Quy trình này phải nằm trong thứ tự nâng daemon và điều kiện tương thích của từng hop.[4]

*Căn cứ đối chiếu: `Pasted markdown(6).md`, mục 6–7; `plan(3) (1)(1).md`, mục 1–9. Nhận định về production là đánh giá thiết kế, chưa thay thế kết quả thử nghiệm trên cụm thực tế.*

[1]: https://docs.ceph.com/en/pacific/rados/configuration/pool-pg-config-ref/ "Ceph Pacific: size và min_size"
[2]: https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/ "Ceph Pacific: di chuyển dữ liệu và CRUSH reweight"
[3]: https://docs.ceph.com/en/pacific/rados/operations/upmap/ "Ceph Pacific: pg-upmap"
[4]: https://docs.ceph.com/en/pacific/cephadm/upgrade/ "Ceph Pacific: thứ tự và điều kiện nâng cấp"
