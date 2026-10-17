
**Có 4 lợi thế về HA và kiểm soát vận hành có cơ sở từ thiết kế, cùng 1 lợi ích QoS cần đo mới kết luận.** Bảng dưới so PA2 với **rolling trực tiếp trên OSD đang giữ PG**, chưa phải kết quả lab đã đạt.

Các lợi thế HA chỉ áp dụng sau khi bàn giao hoàn tất: đủ replica, đúng failure domain và X không còn trong `up/acting`. Rolling có thể vượt `ok-to-stop` dù một số PG tạm giảm mức dự phòng. [docs.ceph.com](https://docs.ceph.com/en/pacific/man/8/ceph/?utm_source=chatgpt.com)

| Điểm PA2 có thể hơn rolling                                                                         | Làm gì để chứng minh?                                                                                                                           | Bằng chứng cần đạt                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Giữ đủ replica trong lúc X dừng để nâng cấp**                                        | Chạy hai phương án với cùng phạm vi PG; ghi liên tục mapping, trạng thái PG và số object degraded trước/trong/sau khi dừng X         | PA2 giữ đủ replica khi X dừng; rolling có khoảng thiếu replica. Ghi rõ số PG và thời gian bị ảnh hưởng                                                                              |
| **2. Chịu thêm một lỗi liên quan tốt hơn trong cửa sổ bảo trì**                         | **Trong lab**, với `size=3, min_size=2`, khi X đang dừng, cho một OSD khác đang giữ replica của PG thử nghiệm tạm mất khả dụng | PA2 còn hai replica và có thể tiếp tục I/O sau peering; rolling còn một replica nên bị chặn. Đo thời gian gián đoạn, không chỉ nhìn trạng thái PG                             |
| **3. Ít phụ thuộc vào thời gian X nâng cấp hoặc khởi động lại**                        | Giữ X chưa trở lại trong các khoảng thời gian định trước, giống nhau giữa hai phương án; duy trì workload                           | PA2 không kéo dài tình trạng thiếu replica vì chờ X. Đo cả QoS và thời gian phục hồi dự phòng của rolling nếu nó chuyển dữ liệu sang nơi khác                              |
| **4. Kiểm soát phiên bản mới tiếp nhận dữ liệu theo từng nhóm PG**                      | Cho OSD đích chạy bản mới nhận lần lượt một nhóm nhỏ rồi tăng dần. Dừng mở rộng sau một nhóm và thử tiếp tục từ checkpoint  | Chỉ PG được duyệt đổi membership; nhóm đã bàn giao vẫn hoạt động; có thể dừng giữa các nhóm. Rolling trực tiếp đưa toàn bộ PG đang gán cho X vào lần restart đó   |
| **5. Có khả năng giảm các đợt ảnh hưởng QoS tập trung** — **chưa chắc thắng** | Chạy fio/RBD hoặc Warp/RGW xuyên suốt hai quy trình. Với PA2, thử vài kích thước nhóm và mức giới hạn backfill                       | p99 theo cửa sổ ngắn, timeout, khoảng dừng I/O hoặc tổng thời gian vượt SLO tốt hơn rolling, với cùng tải yêu cầu. Nếu không tốt hơn thì không được nhận lợi thế này |

Điểm 2 và 3 là những hệ quả thực tế của điểm 1, không nên trình bày thành ba cơ chế HA độc lập. Điểm 4 dựa trên khả năng chỉ định placement từng PG bằng `pg-upmap`. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/upmap/?utm_source=chatgpt.com)

**Để kết quả đủ sức bảo vệ trước mentor, cần làm thêm những việc sau:**

1. **Đo toàn bộ quy trình.** Tính cả chuẩn bị spare, chuyển PG, scrub, redeploy và ổn định placement cuối cùng. Đo riêng lúc X restart sẽ bỏ qua phần tốn kém nhất của PA2.
2. **Đo cả workload ngoài nhóm đang chuyển.** Bao gồm PG dùng chung OSD/host/NIC và một nhóm đối chứng phù hợp; không chỉ đo PG được drain.
3. **Thử lỗi trong lúc đang bàn giao.** Đánh giá cả khi nguồn hoặc đích gặp lỗi giữa chừng. Chỉ thử lỗi sau khi PA2 đã bàn giao sạch sẽ tạo kết quả quá thuận lợi cho PA2.
4. **So sánh từ baseline tương đương.** Cùng dữ liệu, tải, topology và phạm vi nâng cấp; rolling cũng phải có gate và canary đầy đủ. Nếu so độ toàn vẹn, áp dụng mức scrub tương đương.
5. **Ghi chi phí để đạt lợi ích:** bytes chuyển, tổng thời gian, CPU/disk/network, dung lượng spare và công quản lý mapping. Backfill có thể làm giảm hiệu năng client. [docs.ceph.com](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/?utm_source=chatgpt.com)

**Không đưa vào danh sách “PA2 hơn rolling” ở thời điểm này:** hai lần deep-scrub, ít dữ liệu di chuyển hơn, nâng cấp nhanh hơn, hay không ảnh hưởng QoS.

Tiêu chí chọn hợp lý là: **PA2 cải thiện yêu cầu HA đã đặt ra, QoS vẫn nằm trong giới hạn chấp nhận và chi phí phù hợp.** Nếu muốn tuyên bố thêm “PA2 có QoS tốt hơn rolling”, bạn cần kết quả đối chứng của mục 5, không thể suy ra chỉ từ việc drain theo nhóm.


Tôi nghĩ PA2 (pre-drain PG sang OSD dự phòng → nâng cấp X → đưa X trở lại phục vụ theo từng nhóm PG) còn 3 lợi thế đáng nghiên cứu, ngoài 5 điểm bạn đã nêu.
Nhưng phải phân biệt lợi thế thực sự của kiến trúc với những lợi thế rolling upgrade cũng có thể đạt được.
1. Những lợi thế bổ sung
Lợi thế	Tại sao PA2 có thể hơn rolling?	Mức độ
6. Tách thời điểm restart OSD khỏi thời điểm PG bị ảnh hưởng	Rolling restart OSD đang giữ PG có thể gây peering và chuyển primary ngay lúc restart. PA2 chuyển PG trước, nên khi X restart, các PG đã drain không phải peering vì X down.	Mạnh
7. Khoanh vùng và xử lý lỗi phiên bản mới	Nếu phiên bản mới gặp lỗi khi nhận PG, PA2 có thể ngừng cấp PG tiếp theo và chuyển nhóm bị ảnh hưởng ra khỏi X. Rolling trực tiếp đã đưa toàn bộ PG thuộc X vào phạm vi chịu tác động ngay khi X khởi động lại.	Mạnh
8. Phân tách kiểm thử daemon và kiểm thử data path	PA2 có thể nâng cấp, khởi động và kiểm tra daemon mới khi nó chưa giữ PG, rồi mới kiểm thử read/write thực tế bằng nhóm PG nhỏ.	Có điều kiện
Điểm 6 là lợi thế về độ ổn định I/O tại thời điểm restart, khác với việc giữ đủ replica ở điểm 1.
Điểm 7 và 8 có liên quan đến khả năng triển khai canary ở điểm 4, nhưng tập trung vào phát hiện lỗi, cô lập lỗi và phục hồi sau lỗi. Không nên đếm cả ba là ba cơ chế HA độc lập.
2. Điểm tôi đánh giá có giá trị nhất: tách restart và peering
Rolling upgrade trực tiếp

PA2 — Pre-drain trước khi restart

Đây là khác biệt về cơ chế có thể kiểm chứng: trong PA2, nếu X thực sự không còn nằm trong up/acting của bất kỳ PG nào, việc dừng riêng X sẽ không khiến các PG đó phải peering do mất X. Ngược lại, rolling phải xử lý thay đổi tính khả dụng của OSD đang giữ PG. 


Ceph Documentation
+1



Tuy nhiên, PA2 đã phải thực hiện peering/backfill trong giai đoạn drain. Vì vậy không được kết luận PA2 có tổng thời gian gián đoạn ít hơn rolling nếu chưa đo cả quy trình.
3. Một lợi ích mở rộng: bảo trì sâu hơn rolling
PA2 còn có thể sử dụng chung quy trình drain cho những công việc ngoài nâng cấp container:
- Thay ổ đĩa OSD.
- Tạo lại BlueStore hoặc triển khai lại OSD khi cần.
- Thực hiện bảo trì kéo dài mà không phụ thuộc vào thời gian OSD X quay lại.
Ceph có cơ chế safe-to-destroy để hỗ trợ những thao tác thay thế OSD như vậy. 


Ceph Documentation



Nhưng đây là lợi thế mở rộng phạm vi sử dụng, không phải bằng chứng PA2 tốt hơn khi chỉ nâng cấp Pacific 16.2.5 → 16.2.15.
4. Điểm yếu phải giải quyết trước khi bảo vệ PA2
Bạn cần tính đến một phản biện rất mạnh từ mentor:
Rolling upgrade với noout thường không phải chuyển toàn bộ dữ liệu sang OSD khác, còn PA2 chủ động tạo ra backfill trước khi nâng cấp.
Điều đó có nghĩa là PA2 đang đánh đổi chi phí data movement lấy khả năng duy trì redundancy và kiểm soát thời điểm xảy ra thay đổi PG.
Nếu tài nguyên spare không đủ, failure domain không hợp lệ, hoặc chi phí drain quá lớn, PA2 có thể kém hiệu quả hơn rolling.
Đặc biệt với lab 3 OSD, size=3, bạn không thể drain một OSD mà vẫn giữ 3 replica trên 3 OSD ban đầu. Phải bổ sung OSD đích thích hợp.
Kết luận
Nếu làm đề tài nghiên cứu, tôi sẽ tập trung vào ba mục tiêu chính:
HA: Giữ đủ replica trước khi OSD phải dừng.
I/O continuity: Chuyển tác động peering/backfill sang giai đoạn có kiểm soát, thay vì để nó xảy ra đồng thời với restart.
Failure containment: Giới hạn số PG tiếp xúc với phiên bản mới và có đường xử lý lỗi từng nhóm.
Đây là ba góc độ đủ khác nhau để xây dựng luận điểm kỹ thuật. Nhưng phần I/O continuity và khả năng rollback vẫn phải được xác nhận bằng thực nghiệm.
Một câu hỏi quan trọng hơn nữa: Nếu rolling vốn chỉ restart OSD trong thời gian ngắn, không rebalance nhờ noout, thì liệu chi phí full pre-drain của PA2 có đáng để đổi lấy những lợi ích này?
Đó mới là câu hỏi quyết định PA2 có thực sự đáng triển khai trong production hay không.
