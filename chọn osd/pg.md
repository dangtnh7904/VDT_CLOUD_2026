Với bước **canary drain từ X sang spare S**, mình đề xuất chọn **1 PG có dữ liệu, tải thấp, X đang là replica, và thay X bằng S vẫn đúng quy tắc placement**. Đơn vị cần đánh giá là **bộ ba `(PG, X, S)`**.

Bảng trong note của bạn chọn OSD trước; ở bước này cần bổ sung kiểm tra riêng cho từng PG và đích S.

**Trước hết, lọc PG theo các điều kiện sau.** Đây là tiêu chí vận hành mình đề xuất cho canary đầu:

| Điều kiện                                      | Cách kiểm tra                                                                                                                                                       |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PG ổn định, đủ replica**             | `active+clean`, `up = acting`; không degraded, remapped, recovery/backfill hoặc lỗi scrub. Chờ scrub/snaptrim đang chạy hoàn tất.                         |
| **Đúng nguồn và đích**                | X có trong PG; S chưa có trong cả`up` lẫn `acting`.                                                                                                          |
| **Thay X bằng S vẫn đúng CRUSH rule**   | Kiểm tra root, device class và failure domain. Nếu rule tách theo**host**, host của S không được trùng host của các replica giữ lại.              |
| **Giữ nguyên primary trong canary đầu** | Chọn`acting_primary != X`; kiểm tra mapping dự kiến vẫn giữ primary hiện tại. Dù đã đặt `primary-affinity=0`, vẫn kiểm tra trạng thái thực tế. |
| **S và các peer đủ tài nguyên**       | Đủ dung lượng sau khi nhận PG, còn dư disk IOPS, CPU và network; tính cả những backfill khác đang dùng chung tài nguyên.                              |
| **Mapping dễ kiểm soát**                 | Ưu tiên PG chưa có`pg_upmap`/`pg_upmap_items` cũ. PG có override cần xử lý riêng để giữ đúng các thay đổi trước đó.                         |

Ceph phân biệt `up` là mapping đích và `acting` là nhóm đang phục vụ PG; vì vậy thấy S xuất hiện trong `up` **chưa chứng minh S đã đồng bộ xong**. Placement cũng phải xét failure domain, không chỉ ID OSD. ([Ceph Documentation][1])

Trong các PG đã qua bộ lọc, **xếp thứ tự ưu tiên như sau**:

| Ưu tiên | PG nên chọn                                     | Lý do                                                                                                              |
| --------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1         | Workload đã xác định là ít critical        | Giới hạn ảnh hưởng nếu canary gặp lỗi. PG ít byte không đồng nghĩa ít quan trọng.                    |
| 2         | Tải đọc/ghi thấp, đặc biệt tải ghi thấp  | Giảm cạnh tranh giữa client I/O và quá trình đồng bộ sang S.                                               |
| 3         | Ít dữ liệu**và** ít object             | Backfill thường hoàn tất nhanh hơn, dễ quan sát và giới hạn thời gian thử.                              |
| 4         | Ít OMAP, không có backlog snaptrim lớn        | Tránh chọn PG nhìn nhỏ theo byte nhưng xử lý metadata nặng.                                                 |
| 5         | Có dữ liệu và có thể kiểm chứng đọc/ghi | Canary phải kiểm tra được việc di chuyển dữ liệu thực tế. PG rỗng chỉ giúp kiểm tra mapping/peering. |

Với RGW + RBD của bạn, lượt đầu nên ưu tiên PG thuộc workload test hoặc ít critical đã xác minh. **Đừng tự động chọn PG của RGW index/metadata chỉ vì nó nhỏ.** Ceph cũng phân biệt RGW index và RGW data khi đánh giá các pool có đặc tính sử dụng tương đồng. Thống kê OMAP được thu thập lúc deep-scrub nên cần xét độ mới của số liệu. ([Ceph Documentation][2])

Để đo tải, lấy nhiều mẫu thống kê PG và tính chênh lệch counter:

```text
Read IOPS  ≈ Δnum_read  / Δthời_gian
Write IOPS ≈ Δnum_write / Δthời_gian
```

Ví dụ trong lab, lấy mẫu mỗi 30–60 giây trong 10–15 phút để sàng lọc ban đầu. Production cần thêm cửa sổ đại diện cho workload. Counter tích lũy lớn không có nghĩa PG đang nóng; thiếu số liệu cũng chưa thể kết luận PG nhàn.

Bạn có thể bắt đầu lấy dữ liệu bằng các lệnh đọc sau:

```bash
X=1

ceph pg ls-by-osd "$X" -f json-pretty
ceph osd pool ls detail -f json-pretty
ceph osd tree -f json-pretty
ceph osd crush rule dump -f json-pretty
ceph osd df tree -f json-pretty
ceph osd dump -f json-pretty
```

Sau khi có PG ứng viên, xem riêng mapping và trạng thái:

```bash
ceph pg map <PG_ID>
ceph pg <PG_ID> query
```

Các lệnh `ls-by-osd`, `pg map` và xuất JSON có trong Pacific. Khi xây bộ chọn cho nhiều OSD, nên lấy **một snapshot `ceph pg dump pgs -f json` dùng chung**, rồi lọc các PG có X trong `up` hoặc `acting`. ([Ceph Documentation][3])

Ví dụ với pool replicated size=3, giả sử placement hợp lệ:

| Thời điểm                  | Mapping     | Primary   |
| ----------------------------- | ----------- | --------- |
| Trước drain                 | `[0,1,2]` | `osd.0` |
| Đích sau thay X=1 bằng S=3 | `[0,3,2]` | `osd.0` |

Canary này giữ primary tại `osd.0` để quan sát riêng ảnh hưởng của thay replica. **S vẫn tham gia xử lý ghi khi trở thành replica phục vụ**, nên cần theo dõi latency ghi của client dù primary không đổi. ([Ceph Documentation][4])

Với mỗi cặp X–S, mình đề xuất chạy như sau:

1. **Chuyển 1 PG nhỏ có dữ liệu**, giữ X online trong quá trình đồng bộ.
2. Chờ PG trở lại `active+clean`, `up = acting`, S đã thay X đúng dự kiến; kiểm tra dữ liệu test thuộc PG và kết quả deep-scrub.
3. Chỉ mở rộng khi client latency/error, tải S và các peer nằm trong ngưỡng đã đặt; không phát sinh migration ngoài kế hoạch.
4. Chọn thêm PG có tải và kích thước đại diện hơn, rồi tăng batch theo **tổng byte, số object và tài nguyên peer**, không chỉ số lượng PG.

Nếu drain nhiều OSD đồng thời, **không để hai lượt cùng thay hai thành viên của một PG**; đồng thời giới hạn tải cộng dồn trên S, primary và host dùng chung.

Nếu bạn đang giữ `norebalance`, cần kiểm tra trước khi chạy: cờ này có thể chặn migration của chính PG canary; nó không tạo danh sách PG được phép backfill. ([Ceph Documentation][5])

[1]: https://docs.ceph.com/en/pacific/rados/operations/monitoring-osd-pg/?utm_source=chatgpt.com
[2]: https://docs.ceph.com/en/pacific/rados/operations/upmap/?utm_source=chatgpt.com
[3]: https://docs.ceph.com/en/pacific/api/mon_command_api/?utm_source=chatgpt.com
[4]: https://docs.ceph.com/en/pacific/architecture/?utm_source=chatgpt.com
[5]: https://docs.ceph.com/en/pacific/rados/operations/health-checks/?utm_source=chatgpt.com
