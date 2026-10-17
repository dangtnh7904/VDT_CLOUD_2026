
**Plan nâng cấp tổng quát của bạn là: nâng theo từng chặng phiên bản; trong mỗi chặng nâng lần lượt từng loại daemon; riêng OSD triển khai từ canary nhỏ rồi mở rộng theo từng đợt.**

Dưới đây là **MOP ở mức trình tự thực hiện**, áp dụng cho cụm **cephadm, phục vụ RGW + RBD** của bạn.

1. **Chia toàn bộ quá trình thành ba chặng phiên bản**

   Giữ các mốc trong lộ trình bạn đã chọn:

   | Chặng | Phiên bản nguồn → đích | Cách thực hiện                                           |
   | ------ | ---------------------------- | ----------------------------------------------------------- |
   | 1      | **16.2.5 → 16.2.15**  | Hoàn thành nâng các thành phần của cụm lên 16.2.15 |
   | 2      | **16.2.15 → 17.2.7**  | Lặp lại quy trình nâng theo từng loại daemon          |
   | 3      | **17.2.7 → 18.2.7**   | Lặp lại quy trình và hoàn tất tại phiên bản đích |

   **Hoàn thành và theo dõi ổn định một chặng rồi mới bắt đầu chặng tiếp theo.** Ví dụ, khi đang nâng các OSD từ 16.2.15 lên 17.2.7, chưa đưa một nhóm OSD đi tiếp lên 18.2.7.

   Các mốc trên là lộ trình dự án hiện tại; việc chốt bản vá cụ thể để triển khai production là quyết định riêng.
2. **Kết hợp rolling upgrade, staggered upgrade và canary**

   Ba cách này kết hợp với nhau trong cùng một quy trình:

   | Cách triển khai           | Áp dụng trong plan                                                                                                             |
   | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
   | **Rolling upgrade**   | Thay phiên bản và khởi động lại từng daemon hoặc nhóm nhỏ, trong khi các thành phần còn lại tiếp tục phục vụ |
   | **Staggered upgrade** | Chia việc nâng thành các đợt có giới hạn phạm vi và có khoảng dừng giữa các đợt                                |
   | **Canary**            | Nâng một phạm vi nhỏ trước để quan sát hoạt động thực tế, sau đó mới mở rộng                                  |

   Trong mỗi chặng, thứ tự cephadm đối với các thành phần chính của bạn là:

   **MGR → MON → crash → OSD → RGW → rbd-mirror nếu có.**

   Nếu cụm có CephFS, **MDS nằm sau OSD và trước RGW**. Thứ tự daemon vẫn được cephadm áp dụng khi dùng staggered upgrade. :chatgpt-content-reference{index="0"}
3. **Bắt đầu bằng MGR: nâng standby rồi chuyển vai trò active**

   Trình tự đề xuất:

   - Nâng MGR standby lên phiên bản đích.
   - Chuyển vai trò active sang một MGR đã nâng.
   - Nâng MGR active cũ và các MGR còn lại.
   - Để MGR mới vận hành ổn định trước khi chuyển sang MON.

   Cách này đưa phần quản lý và điều phối nâng cấp lên phiên bản mới trước. MGR hỗ trợ mô hình một active và các standby tiếp quản khi failover. :chatgpt-content-reference{index="1"}

   **Riêng chặng 16.2.5 → 16.2.15:** các bộ lọc staggered upgrade chỉ có từ Pacific **16.2.11**. Vì vậy cần nâng MGR trước bằng quy trình chuyển tiếp được Ceph hướng dẫn; sau khi MGR mới điều hành, tiếp tục chia phạm vi nâng bằng các bộ lọc. :chatgpt-content-reference{index="2"}
4. **Nâng MON lần lượt, sau đó hoàn thành nhóm crash**

   Với MON, thực hiện từng daemon:

   **Nâng MON thứ nhất → đợi MON đó trở lại quorum → nâng MON tiếp theo.**

   Nếu có ba MON thì đi lần lượt qua cả ba; duy trì quorum trong suốt quá trình. Kết thúc bước này, toàn bộ MON của chặng đang thực hiện đã chạy phiên bản đích.

   Tiếp theo nâng các daemon **crash** theo thứ tự của cephadm, rồi mới chuyển sang OSD.

   Trong plan này, bạn hoàn thành phần **MGR, MON và crash trước khi bắt đầu canary OSD**.
5. **Nâng một OSD canary theo PA1**

   Đây là vòng nâng đầu tiên để chứng minh toàn bộ quy trình OSD hoạt động được.

   Gọi **X** là OSD cần nâng và **S** là OSD hoặc nhóm spare nhận vị trí thay thế phù hợp. Trình tự PA1 đề xuất:

   | Bước | Thực hiện                                                                                  | Vai trò của X                                            |
   | ------ | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
   | 5.1    | Hạ ưu tiên primary của X, xác nhận các PG đã chuyển primary như dự kiến         | Giảm trách nhiệm xử lý yêu cầu ở vai trò primary  |
   | 5.2    | Điều chuyển các PG khỏi X sang S theo từng nhóm nhỏ                                  | Dần rút khỏi các PG đang phục vụ                    |
   | 5.3    | Chờ việc điều chuyển hoàn tất, rồi đổi image và khởi động lại đúng daemon X | Chạy phiên bản mới                                     |
   | 5.4    | Đưa một nhóm PG canary trở lại X, trước tiên cho X tham gia ở vai trò replica     | Nhận dữ liệu và tham gia phục vụ trong phạm vi nhỏ |
   | 5.5    | Cho X đảm nhiệm primary trong phạm vi canary đã xác định                            | Thử hoạt động primary trên phiên bản mới           |
   | 5.6    | Đưa các PG còn lại trở về theo từng nhóm, khôi phục vai trò bình thường       | Trở lại vận hành đầy đủ                            |

   `primary-affinity` điều chỉnh việc chọn primary; `pg-upmap` điều chỉnh vị trí PG. PA1 kết hợp hai cơ chế này thành quy trình điều phối của dự án. :chatgpt-content-reference{index="3"}

   **Canary chỉ hoàn thành sau khi X đã quay lại phục vụ dữ liệu và được theo dõi ổn định**, không dừng ở việc container mới khởi động thành công.

   Phần điều chuyển PG có thể phát sinh backfill. Vì vậy, thời gian một vòng PA1 bao gồm cả **đưa PG ra, nâng daemon và đưa PG trở lại**. Cephadm đảm nhiệm thay image/redeploy; việc điều phối PA1 cần được thực hiện riêng.
6. **Mở rộng từ một OSD sang nhóm nhỏ, rồi nâng các OSD còn lại theo đợt**

   Sau canary đầu tiên, mở rộng theo trình tự:

   | Đợt                   | Phạm vi đề xuất                                                    | Mục đích                                                       |
   | ----------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------- |
   | Canary đầu tiên      | 1 OSD                                                                  | Chứng minh một vòng nâng hoàn chỉnh                         |
   | Canary bổ sung         | OSD đại diện cho nhóm phần cứng hoặc cấu hình khác, nếu có | Tránh kết luận cho cả cụm từ một loại OSD                 |
   | Nhóm nhỏ              | Một nhóm vài OSD được chọn trước                              | Đánh giá tác động khi có nhiều vòng nâng cùng diễn ra |
   | Triển khai diện rộng | Các batch với quy mô đã được chứng minh                       | Hoàn thành phần OSD của chặng                                |

   Với khoảng **1.600 OSD**, quy trình sau canary sẽ lặp theo batch. Có thể tổ chức nhiều OSD cùng tiến hành PA1, nhưng phải chọn chúng theo quan hệ PG, failure domain và khả năng đáp ứng của spare, mạng, đĩa.

   Cần phân biệt:


   - **Kích thước batch:** số OSD thuộc một đợt.
   - **Mức song song:** số OSD đang được điều chuyển dữ liệu hoặc restart cùng lúc.

   `--limit N` của staggered upgrade giới hạn tổng số daemon được nâng trong lần chạy đó; nó không có nghĩa là cho phép dừng đồng thời N daemon. :chatgpt-content-reference{index="4"}

   Với PA1, mỗi lần đổi image phải nhắm đúng OSD đã được chuẩn bị. Sau mỗi batch, dành một khoảng theo dõi rồi mới tiếp tục hoặc tăng phạm vi.
7. **Hoàn thành OSD rồi nâng RGW theo kiểu canary và rolling**

   Khi toàn bộ OSD của chặng đã lên phiên bản đích, chuyển sang RGW.

   Nếu production có nhiều RGW sau load balancer, trình tự đề xuất là:

   - Rút một RGW khỏi luồng request mới và xử lý các kết nối đang tồn tại theo cơ chế của hệ thống.
   - Nâng RGW đó lên phiên bản đích.
   - Đưa nó trở lại với phạm vi lưu lượng nhỏ để làm canary.
   - Theo dõi hoạt động S3.
   - Tiếp tục lần lượt với các RGW còn lại.

   Nếu ứng dụng truy cập trực tiếp từng RGW, cần tổ chức chuyển endpoint hoặc lịch gián đoạn tương ứng; khả năng rolling liên tục phụ thuộc vào cách cung cấp endpoint.

   Nếu có **rbd-mirror**, nâng dịch vụ này sau RGW theo thứ tự cephadm. Còn các máy sử dụng RBD qua `librbd`, QEMU hoặc kernel client cần một kế hoạch cập nhật client riêng, theo khả năng tương thích của phiên bản đích.
8. **Khép lại chặng hiện tại rồi lặp quy trình cho chặng tiếp theo**

   Kết thúc mỗi chặng:

   - Hoàn tất các thao tác nâng còn lại của orchestrator và ghi nhận các mốc release đã được chuyển.
   - Hoàn trả các điều chỉnh tạm thời của PA1, giữ lại các mapping vốn có trước đó.
   - Đưa cụm vào một khoảng vận hành bình thường để quan sát với workload RGW và RBD thực tế.
   - Sau đó bắt đầu chặng tiếp theo từ **MGR**, và lặp lại toàn bộ trình tự.

   Ở mỗi lần chuyển major, tổ chức lại canary; kết quả canary của 16.2.15 không thay thế cho canary của 17.2.7 hoặc 18.2.7.

   Nếu phát sinh vấn đề trong một đợt, **dừng mở rộng tại đợt đó và xử lý trước khi tiếp tục**. Việc pause/stop upgrade không tự đưa daemon về phiên bản cũ; tài liệu Quincy và Reef cũng nêu rõ dừng quá trình nâng không cung cấp khả năng downgrade về major trước. :chatgpt-content-reference{index="5"}
