
# Tiêu chí chọn osd

| Nhóm                        | Tiêu chí                                       | OSD nên chọn                                                                                                           |
| ---------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| **Điều kiện chọn** | PG đang khỏe                                   | Các PG liên quan đang`active+clean`, không thiếu bản sao, không recovery/backfill                               |
| **Điều kiện chọn** | Dừng được mà vẫn phục vụ dữ liệu       | Vượt qua`ceph osd ok-to-stop <id>`                                                                                   |
| **Ưu tiên cao**      | Tải trên các PG thấp                         | Tổng IOPS/throughput của các PG liên quan thấp, ít PG đang chịu tải lớn                                        |
| **Ưu tiên cao**      | Các OSD còn lại của PG còn dư tài nguyên | OSD giữ các bản sao còn lại còn dư CPU, disk IOPS và network                                                     |
| **Ưu tiên**          | Ít primary PG                                   | Đặc biệt ít làm primary cho những PG nhiều I/O hoặc nhạy latency                                                |
| **Ưu tiên**          | Tổng số PG ít                                 | Ít PG tham gia, tính cả primary và replica, để giới hạn phạm vi ảnh hưởng                                    |
| **Ưu tiên**          | Ít liên quan dịch vụ quan trọng             | Ít PG thuộc pool phục vụ khách hàng ưu tiên hoặc dịch vụ nhạy latency, nếu đã xác định được mapping |

**Tải PG nên đo trong một khoảng thời gian đại diện**
