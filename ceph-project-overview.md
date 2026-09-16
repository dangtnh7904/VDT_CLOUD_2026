# Tổng quan project: Nâng cấp Ceph theo từng OSD kết hợp trợ lý vận hành

**Hướng chính:** canary/staggered từng OSD, kết hợp chuyển primary và drain có kiểm soát sang OSD dự phòng; dùng cụm 100 TB làm backup độc lập cho dữ liệu ưu tiên. Xây thêm công cụ đánh giá điều kiện nâng, theo dõi QoS và dùng model để giải thích cảnh báo, hỗ trợ vận hành.

Mục tiêu là giảm phạm vi ảnh hưởng, phát hiện vấn đề sớm và có đường phục hồi đã kiểm thử. Mức độ an toàn được chứng minh bằng kết quả kiểm thử và khả năng khôi phục; chưa có cơ sở để gán xác suất 99% hoặc 100%.

**Bối cảnh và phạm vi**

- Production khoảng 24 PB, sử dụng RGW và RBD; nhiều ổ 15 TB đã chứa khoảng 10–12 TB.
- Lộ trình đang nghiên cứu: `16.2.5 → 16.2.15 → 17.2.7 → 18.2.7`. Chốt bản đích và điều kiện tương thích của từng bước trước triển khai thực tế.
- Tập trung nghiên cứu sâu vào OSD; toàn bộ đợt nâng vẫn phải theo thứ tự daemon được Ceph hỗ trợ. Với cephadm, MGR/MON đi trước OSD và RGW đi sau OSD. Bản 16.2.5 cần bước chuẩn bị để dùng khả năng giới hạn từng đợt nâng vốn có từ 16.2.11. [Cephadm upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/).

**Phương án nâng OSD chính**

1. **Chuẩn bị:** đo QoS trước nâng, kiểm tra backup ưu tiên, chọn OSD ít ảnh hưởng và lập danh sách toàn bộ PG liên quan. Kiểm tra bản sao, dung lượng, tải và failure domain của OSD dự phòng.
2. **Lập mapping mục tiêu:** dùng cơ chế như `pg-upmap`/`pg-upmap-items` để chuyển vị trí bản sao trên OSD cần nâng sang OSD dự phòng. So sánh mapping trước/sau và kiểm tra các thay đổi ngoài danh sách dự kiến. Ưu tiên primary trên OSD đã kiểm chứng; xác nhận primary thực tế.
3. **Drain theo nhóm PG:** giữ OSD nguồn hoạt động trong lúc chuyển dữ liệu, giới hạn lượng backfill đồng thời. Chỉ chuyển sang bước tháo/nâng khi dữ liệu đã chuyển xong, các PG đủ bản sao và các kiểm tra an toàn tương ứng đã đạt.
4. **Nâng OSD canary:** nâng một OSD, sau đó đưa dữ liệu trở lại theo nhóm PG. Hạn chế vai trò primary trong thời gian kiểm chứng ban đầu bằng cơ chế phù hợp với phiên bản.
5. **Kiểm chứng rồi tiếp tục:** theo dõi checksum, PG, lỗi client và QoS; đạt điều kiện ổn định mới chuyển sang OSD tiếp theo. Khi OSD dự phòng đã hết nhiệm vụ, xử lý mapping tạm và khôi phục cấu hình cân bằng theo kế hoạch đã kiểm tra.

`pg-upmap` hỗ trợ chỉ định placement cho từng PG và yêu cầu client tương thích. Ceph cũng lưu ý có thể tạm tắt balancer để tránh xung đột với mapping do người vận hành quản lý. [Using pg-upmap](https://docs.ceph.com/en/reef/rados/operations/upmap/).

**OSD “3.5” và cụm backup 100 TB**

| Thành phần           | Vai trò trong project                                                                                                                                                                                                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OSD dự phòng “3.5” | OSD thế chỗ trong**cùng cụm production**, có dung lượng và vị trí phù hợp để nhận bản sao của các PG mục tiêu. Với pool replicated `size=3`, đây là chuyển vị trí một bản sao; không tạo chính sách replica/quorum “3.5”.<br />dự phòng cho DR |
| Cụm 100 TB            | **Backup riêng**, lưu dữ liệu ưu tiên theo bucket/object hoặc RBD image/snapshot, có phiên bản giữ lại và kiểm thử restore. Không dùng dung lượng này để nhận PG native của production.                                                                       |

Ví dụ tập OSD giữ một PG chuyển từ `{X, Y, Z}` sang `{S, Y, Z}`, trong đó X cần nâng và S là dự phòng. Bảng này mô tả thành viên, không mô tả thứ tự primary. Chỉ rút X sau khi quá trình đồng bộ sang tập đích hoàn tất.

Dung lượng backup phải tính theo **usable thực tế**, số phiên bản lưu giữ và tăng trưởng dữ liệu. Chọn bộ dữ liệu có thể khôi phục dịch vụ hoàn chỉnh, gồm dữ liệu và thông tin cấu hình/metadata cần thiết. Xác định RPO — lượng dữ liệu mới có thể mất — và RTO — thời gian khôi phục — cho nhóm khách hàng được bảo vệ.

RBD mirroring hoặc RGW multisite có thể bổ sung cho nhóm dữ liệu chọn lọc khi cần đồng bộ thường xuyên, sau khi kiểm tra tương thích và dung lượng. Vẫn cần các điểm khôi phục giữ lại: bản đồng bộ mới nhất có thể chứa cả thay đổi sai hoặc xóa nhầm. [RBD mirroring](https://docs.ceph.com/en/reef/rbd/rbd-mirroring/), [RGW multisite](https://docs.ceph.com/en/reef/radosgw/multisite/).

**Kiểm soát rebalance và chi phí QoS**

Tạm tắt **balancer** giúp tránh những điều chỉnh cân bằng tự động xung đột với kế hoạch. Tuy nhiên, việc thêm OSD hoặc đổi CRUSH weight vẫn có thể đổi placement. Vì vậy, cách đưa OSD dự phòng vào cụm và phạm vi mapping phải được kiểm thử trước; không thể chỉ tắt balancer rồi kết luận chỉ các PG mục tiêu sẽ di chuyển. [Balancer](https://docs.ceph.com/en/reef/rados/operations/balancer/), [CRUSH maps](https://docs.ceph.com/en/reef/rados/operations/crush-map/).

Không giữ các cờ chặn backfill/recovery trong giai đoạn cần chuyển dữ liệu, vì chúng có thể chặn chính luồng drain. [Ceph health checks — OSDMAP_FLAGS](https://docs.ceph.com/en/reef/rados/operations/health-checks/#osdmap-flags).

Lợi ích kỳ vọng của OSD dự phòng là kiểm soát đích nhận và giảm áp lực dung lượng lên những OSD đang đầy. Vẫn phải đọc và truyền dữ liệu từ các OSD hiện hữu; một OSD dự phòng có thể thành điểm nghẽn. Drain thông thường cũng chủ yếu di chuyển dữ liệu liên quan OSD bị rút, không đồng nghĩa sao chép lại toàn bộ 24 PB.

Đánh đổi lớn là thời gian và I/O: chuyển ra rồi chuyển lại có thể cần hai lượt truyền dữ liệu đáng kể. Chọn khung ít tải theo số liệu lịch sử, hạn chế concurrency và phân bổ băng thông cho backfill, backup, kiểm chứng; tăng số thread chỉ hữu ích khi còn tài nguyên. So sánh thực nghiệm với rolling không drain để xác định phương án nào đáp ứng QoS tốt hơn.

**Các lớp kiểm chứng dữ liệu**

| Lớp kiểm chứng                    | Phạm vi                                                                                                                                                                                                                                                                                            |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BlueStore checksum và deep-scrub    | Tận dụng cơ chế Ceph để phát hiện lỗi lưu trữ và bất nhất giữa các bản sao.[BlueStore checksums](https://docs.ceph.com/en/reef/rados/configuration/bluestore-config-ref/#checksums), [Scrub errors](https://docs.ceph.com/en/reef/rados/operations/health-checks/#osd-scrub-errors). |
| Checksum tại client                 | Với dữ liệu test/được tích hợp: tính`H0` trước ghi, lưu tham chiếu riêng; đọc lại đúng phiên bản rồi tính `H1` và so sánh. Dữ liệu cũ có thể tạo mốc trước nâng, nhưng mốc đó không chứng minh dữ liệu vốn đã đúng từ lúc tạo.               |
| Checksum primary–replica đề xuất | Nghiên cứu so sánh dữ liệu thực đọc từ từng bản sao tại cùng phiên bản và phạm vi byte. Đây là phần cần phát triển/kiểm thử; kiểm tra bất đồng bộ không chặn ACK.                                                                                                  |

Hai hash khác nhau chỉ chứng minh có bất nhất, chưa xác định bản nào đúng. Nếu tất cả bản sao cùng chứa dữ liệu sai nhưng checksum hợp lệ, cần tham chiếu độc lập hoặc backup tốt để đối chiếu và phục hồi. Trong MVP, ưu tiên kiểm chứng phía client và cơ chế Ceph hiện có; giữ phần can thiệp checksum vào OSD ở nhánh thử nghiệm riêng.

**Luồng dự phòng và phương án thay thế**

| Tình huống                                                                 | Hướng xử lý                                                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OSD dự phòng không đủ chỗ hoặc không phù hợp failure domain        | Chọn spare phù hợp; nếu chưa có, đánh giá rolling không drain với kiểm tra an toàn và thời gian dừng phù hợp, hoặc hoãn để bổ sung tài nguyên.                                                                                      |
| QoS xấu đi hoặc backfill quá tải                                        | Dừng mở rộng sang PG/OSD tiếp theo, giảm tác vụ nền theo chính sách đã thử nghiệm và đánh giá lại tải.                                                                                                                                   |
| OSD canary lỗi phần cứng hoặc lỗi cục bộ                              | Cô lập theo điều kiện an toàn, giữ bằng chứng lỗi, thay/tạo lại OSD và phục hồi từ bản sao đã xác minh; không mặc định primary luôn là nguồn đúng.                                                                              |
| Nghi bug ở phiên bản mới B                                               | Dừng mở rộng, xác định lỗi và ưu tiên fix-forward. Chỉ cân nhắc tạo OSD sạch chạy A khi cụm còn chấp nhận A, đường mixed-version phù hợp và kịch bản đã được thử nghiệm; kiểm soát cả phiên bản cephadm triển khai. |
| Dữ liệu sai trên nhiều bản hoặc không xác định được nguồn tốt | Giới hạn thao tác ghi trong phạm vi bị ảnh hưởng nếu cần, chọn điểm backup tốt trên cụm 100 TB và khôi phục theo RPO/RTO đã thống nhất.                                                                                               |

Format ổ không hạ yêu cầu phiên bản của cụm. `require_osd_release` đặt phiên bản OSD tối thiểu được tham gia; vì vậy tạo lại OSD A là nhánh có điều kiện, không phải cam kết rollback toàn cụm. [Ceph command reference](https://docs.ceph.com/en/reef/api/mon_command_api/#osd-require-osd-release).

**Phạm vi triển khai đầu tiên — MVP**

| Hạng mục                    | Đầu ra cần có                                                                                                                                         |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab nâng OSD và spare       | Thử luồng mapping mục tiêu → backfill → nâng → đưa dữ liệu về; đo phạm vi PG thay đổi, thời gian và QoS.                               |
| Bộ đánh giá trước nâng | Thu trạng thái OSD/PG, tải, dung lượng, phiên bản, backup; xếp hạng ứng viên và giải thích điều kiện đạt/chưa đạt/thiếu dữ liệu. |
| Giám sát trước/sau        | Liên kết sự kiện nâng với metrics, log, lỗi, kết quả checksum và restore; cảnh báo khi chưa nên tiếp tục.                                 |
| Trợ lý dùng model          | Giải thích cảnh báo, tìm runbook đúng phiên bản, gợi ý bước kiểm tra có nguồn và tạo báo cáo từ bằng chứng đã thu.               |

Triển khai trước ở lab, sau đó thu thập chỉ đọc trên production và thử nghiệm một phạm vi canary được chọn. Công cụ hỗ trợ quyết định; các thao tác thay đổi cụm trong MVP đi theo runbook do người vận hành thực hiện. API của Ceph và hệ thống metrics có thể làm nguồn dữ liệu, với bộ tích hợp kiểm thử theo phiên bản. [Ceph API](https://docs.ceph.com/en/reef/mgr/ceph_api/), [Prometheus module](https://docs.ceph.com/en/reef/mgr/prometheus/).

**Model cần dùng**

- **MVP:** một LLM có sẵn để đọc tiếng Việt/Anh, log và viết giải thích. Kết hợp tra cứu tài liệu/runbook nội bộ theo phiên bản — RAG; dùng embedding nếu triển khai tìm kiếm ngữ nghĩa. Chọn triển khai nội bộ hoặc API theo yêu cầu dữ liệu và ngân sách, rồi đánh giá trên tập sự cố thực tế.
- **Code và quy tắc:** kiểm tra PG, dung lượng, mapping, điều kiện dừng, phiên bản và checksum. Model không được thay kết quả kiểm tra hoặc kết luận dữ liệu đúng chỉ từ log.
- **Dữ liệu đầu vào:** metrics, log đã xử lý thông tin nhạy cảm, lịch sử thay đổi, tài liệu Ceph và runbook. Gọi model ngoài luồng I/O của khách hàng; chưa cần huấn luyện LLM từ đầu.

**Further work**

- Dự báo cửa sổ ít tải, nguy cơ vượt ngưỡng dung lượng và thời gian backfill bằng mô hình chuỗi thời gian; so với cách thống kê đơn giản.
- Phát hiện bất thường và hồi quy QoS có xét loại workload, khung giờ và OSD đối chứng.
- Tự động hóa từng bước đã kiểm chứng, có kiểm tra điều kiện trước/sau và cơ chế tạm dừng theo quy tắc; model hỗ trợ giải thích.
- Phát triển kiểm chứng primary–replica; chỉ nghiên cứu chặn ACK sau khi chứng minh đúng về phiên bản dữ liệu, ghi đồng thời và chi phí latency.
- Mở rộng kế hoạch nhiều OSD không xung đột failure domain, quản lý nhiều cụm và tích hợp DR chọn lọc nếu dung lượng cho phép.

**Cách đánh giá kết quả project**

Đối chiếu rolling thông thường với phương án spare trên workload tương đương: số PG/OSD bị tác động, byte di chuyển, thời gian nâng và backfill, throughput, p95/p99 phía client và tỷ lệ lỗi. Kiểm thử restore, phát hiện checksum sai, thiếu dữ liệu giám sát và lỗi canary; đo thêm thời gian phân tích cảnh báo, số nhận định sai của model và tải do công cụ tạo ra. Ngưỡng chấp nhận dựa trên baseline/SLO thực tế trước khi triển khai production.
