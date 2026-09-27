# Cấu trúc báo cáo kết quả sau một tháng làm việc với Ceph

- **Số lượng:** 7 slide, gộp phần mở đầu vào slide tổng quan.
- **Thời lượng dự kiến:** 8–10 phút.
- **Bố cục:** gộp phần mở đầu, kiến thức và thực hành Ceph RBD/RGW vào slide 1. Dành hai slide riêng cho H0 và kiểm thử ảnh hưởng tới QoS.
- **Trọng tâm:** những việc đã làm được, sản phẩm hỗ trợ, kết quả lab và kế hoạch tháng tới.

## Slide 1 Kết quả tháng đầu và kiến thức đã áp dụng

**Người trình bày:** [Họ tên] — **Thời gian báo cáo:** [Tháng/năm]

| Nội dung | Đã học và áp dụng |
|---|---|
| Ceph | Hiểu vai trò MON/MGR/OSD, quan hệ object–PG–OSD và CRUSH. Thực hành kiểm tra trạng thái cụm, phiên bản và log. |
| RBD | Tạo image 10 GB, map và mount trên Linux. Chạy `fio`, đọc IOPS, throughput và latency. |
| RGW | Tìm hiểu S3 API, bucket/object và placement. Cấu hình truy cập, thử PUT/GET, chạy workload và phân tích lỗi. |

**Điểm nhấn khi nói:** nêu những thao tác hiện tại đã tự thực hiện được và kết quả đã biết cách phân tích so với lúc mới vào.

**Minh chứng:** [Chèn một ảnh kết quả fio và một ảnh kiểm thử S3, cắt gọn phần quan trọng.]

## Slide 2 Website hỗ trợ kiểm thử và nâng cấp

- Đã xây dựng website để hỗ trợ quá trình kiểm thử và thử nghiệm nâng cấp Ceph.
- Minh họa 2–3 chức năng đã hoạt động thực tế bằng một ca kiểm thử cụ thể.
- Phần hoàn thiện tiếp: tích hợp hoặc hoàn thiện theo dõi checksum/H0 và số liệu QoS theo từng lần chạy.

**Minh chứng:** [Chèn ảnh giao diện chính và ảnh kết quả của một lần kiểm thử.]

## Slide 3 Hai ý tưởng nâng cấp OSD

**Mục tiêu chung:** chuẩn bị đủ bản sao phục vụ trước khi dừng OSD mục tiêu, đồng thời kiểm soát ảnh hưởng của việc sao chép dữ liệu.

| Phương án | Ý tưởng | Trạng thái |
|---|---|---|
| **PA1 dùng spare và upmap** | Dùng cơ chế có sẵn của Ceph để chuyển các PG thuộc OSD mục tiêu sang spare theo từng batch, kiểm tra hội tụ rồi mới nâng cấp. | Đã thử nghiệm lab với một OSD. |
| **PA2 Maintenance Shadow Replica** | Phát triển bản sao tạm, đồng bộ trước và chuyển thành replica hợp lệ trước khi dừng OSD mục tiêu. | Đề xuất thiết kế, cần phát triển và kiểm chứng. |

Cả hai phương án vẫn cần truyền dữ liệu. Hiệu quả kiểm soát tải cần được đo bằng thực nghiệm.

**Minh họa:** [Chèn sơ đồ ngắn cho PA1 và PA2.]

## Slide 4 Kết quả thử nghiệm PA1 trên một OSD

- Đã chuyển PG sang spare, kiểm tra `ok-to-stop`, nâng một OSD từ **16.2.5 lên 16.2.15**, sau đó trả PG về.
- Kết quả kiểm tra dữ liệu trong MOP: **16/16 đối tượng khớp checksum, 0 lỗi**.
- Đây là kết quả bước đầu trên lab và trên tập đối tượng đã kiểm tra. Cần bổ sung đo QoS, diễn tập rollback và tình huống lỗi.

**Minh chứng:** [Chèn ảnh phiên bản OSD và dòng tổng kết checksum từ MOP(2).docx.]

## Slide 5 H0 kiểm chứng dữ liệu so với bản gốc

- **H0 là gì:** mã SHA-256 tính từ dữ liệu gốc tin cậy phía client trước khi gửi, lưu làm mốc tham chiếu độc lập. Khi đọc lại đúng dữ liệu và phiên bản, tính H1 để đối chiếu với H0.
- **Vì sao thêm H0:** bổ sung phép kiểm tra với dữ liệu gốc bên cạnh checksum BlueStore và deep-scrub. Việc các replica giống nhau chưa đủ để kết luận chúng khớp dữ liệu đầu vào nếu cùng nhận dữ liệu đã bị sai.
- **Ưu điểm:** phát hiện sai khác so với bản gốc, tạo bằng chứng trước/sau nâng cấp và cung cấp tiêu chí dừng mở rộng canary khi phát hiện mismatch. H0 có thể bắt đầu ở phía client, phối hợp với kiểm tra sẵn có của Ceph.

**Điều kiện đối chiếu:** manifest gắn checksum với object/version hoặc RBD snapshot/write generation và offset/length, kèm thuật toán. Lưu tham chiếu độc lập với phạm vi nâng cấp, chẳng hạn trên máy kiểm thử. Đọc đúng phiên bản hoặc vùng dữ liệu bất biến để tránh nhầm một lần ghi hợp lệ thành lỗi toàn vẹn.

**Trạng thái:** lab đã có kiểm tra checksum sau nâng. Cơ chế kiểm H0 trực tiếp trên từng replica trước khi primary sử dụng vẫn là hướng phát triển; kiểm tra qua client chưa xác nhận riêng từng replica.

**Minh chứng:** [Chèn ví dụ một bản ghi manifest và kết quả đối chiếu H0/H1.]

## Slide 6 Kiểm thử ảnh hưởng lên QoS

**Mục tiêu:** đo riêng tác động của nâng cấp và phần tải tăng thêm do tính hash, đọc lại và đối chiếu H0.

| Kịch bản | Tải chạy đồng thời | Mục đích |
|---|---|---|
| **A** | Workload RBD/S3 thông thường | Lấy baseline. |
| **B** | Workload và kiểm H0, không nâng cấp | Đo overhead H0 so với A. |
| **C** | Workload và quy trình PA1, không chạy kiểm H0 đồng thời | Đo tác động của PA1 so với A. |
| **D** | Workload, quy trình PA1 và kiểm H0 | Đo tác động tổng thể; so với C để đánh giá phần tải tăng thêm do H0 trong lúc nâng cấp. |

- **Đo ở phía ứng dụng:** p95/p99 riêng cho read/write RBD và PUT/GET S3, IOPS/throughput, error rate và timeout. Ghi thêm CPU client/OSD, disk latency/utilization, network, lượng dữ liệu kiểm tra và thời gian kiểm tra.
- **Cách chạy:** giữ cùng cấu hình tải, tập dữ liệu, batch và điều kiện cache. Chuẩn bị cùng trạng thái ban đầu, có warm-up và lặp lại các lượt đối chứng. So sánh C/D theo cùng giai đoạn di chuyển, nâng cấp và trả PG. Tách số đo bước tạo H0 khỏi bước đọc lại xác minh.
- **Tiêu chí đánh giá:** chốt trước SLO latency/error rate và mức IOPS/throughput tối thiểu. Thử giới hạn tốc độ đọc và số luồng H0. Khi vượt ngưỡng, giảm hoặc tạm dừng kiểm tra, không mở batch mới; chỉ cho qua gate toàn vẹn khi phần kiểm tra bắt buộc đã hoàn tất.

**Phạm vi kiểm thử:** dùng object version/snapshot hoặc dữ liệu cố định để kiểm H0, tách khỏi vùng đang bị workload ghi đè. Giữ cấu hình checksum/scrub của Ceph nhất quán giữa các lượt; việc không chạy H0 trong C chỉ áp dụng cho tác vụ kiểm tra của ứng dụng.

**Trạng thái:** đây là kế hoạch đo. Hiện chưa có số liệu đối chứng để kết luận mức overhead H0 hoặc mức ảnh hưởng QoS.

**Minh chứng dự kiến:** [Chèn bảng hoặc biểu đồ p99, throughput và error rate của A/B/C/D sau khi có số liệu.]

## Slide 7 Kế hoạch tháng tới

| Công việc | Đầu ra dự kiến |
|---|---|
| Hoàn thiện kiểm thử PA1 | Kết quả lặp lại có tải, diễn tập rollback và tình huống lỗi trên lab. |
| Chuẩn hóa H0 và đo QoS | Manifest gắn đúng phiên bản, kết quả đối chiếu, báo cáo A/B/C/D và giới hạn tốc độ kiểm tra phù hợp. |
| Hoàn thiện website | Theo dõi từng lần chạy, kết quả H0/QoS và lưu bằng chứng kiểm thử; ưu tiên các chức năng còn thiếu. |
| Nghiên cứu PA2 | Rà soát mã nguồn, đánh giá tính khả thi và thử nghiệm nhỏ cho shadow sync/promotion. |

**Đầu ra trọng tâm:** quy trình PA1 có số liệu kiểm chứng về toàn vẹn dữ liệu và QoS, cùng công cụ hỗ trợ chạy lại và đối chiếu kết quả.

## Ghi chú khi dựng slide

- Phần mở đầu và kiến thức đã tìm hiểu gộp trong slide 1. Dành thời gian cho sản phẩm và kết quả đã làm được.
- Slide 5 giữ ba ý chính: H0 là gì, lý do thêm và ưu điểm. Phần điều kiện đối chiếu dùng làm ghi chú thuyết trình.
- Slide 6 trình bày bảng A/B/C/D và chỉ số chính. Các điều kiện chạy thử dùng làm ghi chú thuyết trình.
- Phân biệt rõ kết quả đã có, thiết kế đề xuất và kiểm thử dự kiến.

## Nguồn đối chiếu

- **RBD(2).docx:** thực hành RBD, mount và fio.
- **MOP(2).docx:** thử nghiệm PA1, phiên bản OSD và kết quả checksum 16/16 đối tượng.
- **plan(3) (1)(4).md:** thiết kế PA1/PA2, integrity gate và QoS contract.
- [Ceph Pacific BlueStore Configuration Reference](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/#checksums): cơ chế checksum dữ liệu và metadata của BlueStore.
- [Ceph Pacific OSD Config Reference](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/#scrubbing): scrub, deep-scrub và ảnh hưởng tới hiệu năng.

H0 và ma trận A/B/C/D trong báo cáo là thiết kế kiểm chứng của đề tài, bổ sung cho các cơ chế Ceph nêu trên.
