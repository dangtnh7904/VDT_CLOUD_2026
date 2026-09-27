# Báo cáo tháng đầu với Ceph — Nội dung 7 slide và lời thuyết trình

**Người trình bày:** [Họ tên]  
**Buổi báo cáo:** [Ngày báo cáo]  
**Thời lượng mục tiêu:** khoảng 10 phút, chưa tính hỏi đáp.

Tài liệu này gồm phần chữ đưa lên màn hình, lời nói hoàn chỉnh và câu chuyển cho từng slide. Phần giải thích cuối tài liệu phục vụ trao đổi sâu hơn, không làm tăng số slide.

**Mạch trình bày:** kết quả tháng đầu → hiện trạng và lý do nâng cấp → yêu cầu → hai phương án → kiểm chứng H0/QoS → khôi phục khi lỗi → kế hoạch tháng tới.

**Cách dùng:** chỉ chép mục “Chữ đưa lên slide” lên slide; đưa lời thuyết trình vào phần ghi chú. Thay thông tin trong ngoặc vuông bằng thông tin thực tế. Các kết quả chưa đo được ghi rõ là kế hoạch kiểm chứng, không tự điền số liệu.

## Slide 1 — Kết quả sau một tháng làm việc

**Thời lượng gợi ý:** 1 phút 10 giây.  
**Ý chính:** đã chuyển kiến thức Ceph thành thao tác lab, công cụ hỗ trợ và một thử nghiệm nâng cấp có bằng chứng.

### Chữ đưa lên slide

**BÁO CÁO KẾT QUẢ THÁNG ĐẦU VỚI CEPH**  
[Họ tên] · [Tháng/năm]

- **Đã học:** kiến trúc Ceph, pool/PG/CRUSH; RBD và RGW/S3.
- **Đã thực hành:** tạo, mount RBD và chạy fio; cấu hình S3, thử PUT/GET.
- **Đã xây dựng:** website hỗ trợ kiểm thử và thử nghiệm nâng cấp.
- **Kết quả lab:** nâng một OSD từ **16.2.5 → 16.2.15**; **16/16 đối tượng kiểm tra khớp checksum**.

**Phạm vi:** một OSD trên lab và tập dữ liệu đã kiểm tra.

### Lời thuyết trình

Em chào anh chị. Trong buổi hôm nay, em xin báo cáo những nội dung đã học, những việc đã thực hiện trong tháng đầu và hướng em sẽ làm tiếp.

Về kiến thức, em đã tìm hiểu kiến trúc Ceph và hai dịch vụ chính là RBD cho lưu trữ dạng khối, RGW cho lưu trữ đối tượng qua S3. Em đã thực hành tạo và mount RBD, chạy fio để đọc các chỉ số IOPS, băng thông và độ trễ; với RGW, em đã thử các thao tác tải lên và đọc lại đối tượng.

Em cũng đã xây dựng một website hỗ trợ quá trình kiểm thử và thử nghiệm nâng cấp. Đây là công cụ để em tiếp tục hoàn thiện việc theo dõi và tổng hợp kết quả.

Về nâng cấp, em đã thử chuyển PG sang OSD dự phòng, nâng một OSD từ 16.2.5 lên 16.2.15 rồi trả PG về. Kết quả kiểm tra dữ liệu qua client có 16 trên 16 đối tượng khớp checksum. Đây là kết quả bước đầu trên lab, là cơ sở để em xây dựng các bài kiểm thử tiếp theo.

### Minh chứng nên đặt

Một ảnh website thể hiện chức năng đã chạy thực tế; bên cạnh là ảnh phiên bản OSD hoặc dòng kết quả **checked=16, failed=0, listed=16**. Không cần đưa nhiều màn hình terminal lên cùng một slide.

### Câu chuyển sang slide 2

Từ kết quả đó, em xin trình bày hiện trạng của bài toán và lý do cần nghiên cứu phương án nâng cấp.

## Slide 2 — Hiện trạng và lý do cần nâng cấp

**Thời lượng gợi ý:** 1 phút.  
**Ý chính:** cần nâng cấp vì vòng đời phần mềm và nhu cầu cập nhật, nhưng quy mô hệ thống khiến việc triển khai phải có kiểm soát.

### Chữ đưa lên slide

**Hiện trạng**

- Lab xuất phát từ **Ceph Pacific 16.2.5**.
- Quy mô production đã trao đổi: khoảng **1.600 OSD, 24 PB**, phục vụ RBD và RGW.
- Kho backup khoảng **100 TB**: cần ưu tiên phạm vi dữ liệu được bảo vệ.

**Lý do cần nâng cấp**

- Pacific đã hết bảo trì upstream từ **04/03/2024**.
- Cần cập nhật bản sửa lỗi, bảo mật và rà soát đích phiên bản còn hỗ trợ.
- Cần kiểm soát tải dịch chuyển dữ liệu, ảnh hưởng dịch vụ và khả năng khôi phục.

*Nguồn vòng đời: Ceph Releases, đối chiếu ngày 27/09/2026.*

### Lời thuyết trình

Phiên bản em đã xác minh trên lab là Ceph Pacific 16.2.5. Với production, phạm vi bài toán đã trao đổi là khoảng 1.600 OSD, tổng dung lượng khoảng 24 PB, phục vụ cả RBD và RGW. Các số liệu này cần đối chiếu lại với inventory thực tế trước khi lập kế hoạch triển khai.

Lý do cần nâng cấp trước hết là vòng đời hỗ trợ. Pacific đã hết bảo trì upstream; vì vậy cần rà soát các bản sửa lỗi, bảo mật và phiên bản đích phù hợp. Bước lên 16.2.15 hiện tại giúp kiểm chứng quy trình, còn đích production cần được đánh giá riêng.

Ở quy mô lớn, việc chuyển dữ liệu khi nâng cấp có thể tranh chấp tài nguyên với ứng dụng. Đồng thời, kho backup khoảng 100 TB không thể bao phủ toàn bộ 24 PB. Do đó, phương án cần xác định rõ dữ liệu ưu tiên, mức ảnh hưởng chấp nhận được và cách khôi phục khi có lỗi.

### Minh chứng nên đặt

Ba con số lớn **1.600 OSD · 24 PB · 100 TB backup**, kèm dòng “Phạm vi đã trao đổi; cần xác nhận inventory”. Chân slide đặt liên kết [Ceph Releases](https://docs.ceph.com/en/latest/releases/).

### Câu chuyển sang slide 3

Vì vậy, trước khi lựa chọn cách nâng cấp, em đề xuất các tiêu chí mà phương án phải đáp ứng.

## Slide 3 — Các yêu cầu phải bảo đảm khi nâng cấp

**Thời lượng gợi ý:** 1 phút.  
**Ý chính:** đánh giá phương án bằng yêu cầu cụ thể và bằng chứng kiểm thử.

### Chữ đưa lên slide

| Yêu cầu | Bằng chứng cần có |
|---|---|
| **R1 — Toàn vẹn dữ liệu** | Đúng dữ liệu, đúng phiên bản; H0/H1 khớp trong phạm vi kiểm chứng. |
| **R2 — Duy trì dịch vụ** | Đủ replica hợp lệ trước khi dừng OSD; thử thêm lỗi theo kịch bản. |
| **R3 — QoS** | p95/p99, lỗi, IOPS/throughput trong ngưỡng thống nhất. |
| **R4 — Kiểm soát tài nguyên** | Theo dõi PG, dung lượng spare, byte copy, CPU/disk/network. |
| **R5 — Khôi phục được** | Thử backup/restore, fallback, rollback; đo điểm và thời gian phục hồi. |
| **R6 — Triển khai khả thi** | Đúng phiên bản, tương thích, trình tự và mức song song phù hợp. |

**Cần chốt trước:** phạm vi kiểm thử, ngưỡng QoS, RPO/RTO và điều kiện dừng.

### Lời thuyết trình

Em chia yêu cầu thành sáu nhóm.

Đầu tiên là toàn vẹn dữ liệu: dữ liệu đọc lại phải đúng với mốc tham chiếu và đúng phiên bản. Thứ hai là duy trì dịch vụ: trước khi dừng OSD cần đủ replica hợp lệ, đồng thời phải thử tình huống phát sinh thêm lỗi trong phạm vi thiết kế.

Thứ ba là QoS, tức chất lượng dịch vụ mà ứng dụng thực sự nhận được. Em sẽ theo dõi độ trễ, tốc độ xử lý và lỗi. Thứ tư là kiểm soát lượng dữ liệu dịch chuyển cùng tài nguyên của spare và các OSD liên quan.

Hai yêu cầu còn lại là khôi phục được khi có lỗi và có thể triển khai theo lịch trình thực tế. Mỗi yêu cầu phải gắn với một bài test và bằng chứng. Các ngưỡng QoS, thời gian phục hồi và mức mất dữ liệu chấp nhận được cần thống nhất với đơn vị vận hành trước khi kết luận đạt.

### Ghi chú cho người trình bày

Không cần đọc nguyên văn từng ô của bảng. Nhấn vào ba câu hỏi quản lý thường quan tâm: **dữ liệu có đúng không, dịch vụ bị ảnh hưởng bao nhiêu, lỗi thì khôi phục thế nào**.

### Câu chuyển sang slide 4

Dựa trên các yêu cầu này, em đang xem xét hai hướng nâng cấp với mức độ sẵn sàng khác nhau.

## Slide 4 — Hai phương án và ưu nhược điểm

**Thời lượng gợi ý:** 1 phút 40 giây.  
**Ý chính:** PA1 có thể tiếp tục kiểm chứng ngay; PA2 là hướng phát triển cần prototype.

### Chữ đưa lên slide

| Nội dung | PA1 — Spare và upmap | PA2 — Maintenance Shadow Replica |
|---|---|---|
| **Cách làm** | Chuyển PG sang spare theo batch; đủ replica rồi dừng OSD cần nâng. | Đồng bộ bản shadow; kiểm tra và promote thành replica hợp lệ trước khi dừng OSD. |
| **Ưu điểm** | Dùng cơ chế Ceph sẵn có; chia nhỏ từng batch; đã có thử nghiệm lab. | Chủ động chuẩn bị dữ liệu; thiết kế trạng thái sync, kiểm chứng và promotion rõ ràng. |
| **Hạn chế** | Tốn copy; quản lý upmap/journal; chiều trả về có thể phải copy lại. | Cần phát triển Ceph; phức tạp về peering và tương thích; vẫn tiêu thụ tài nguyên. |
| **Hiện tại** | Đã nâng một OSD trên lab. | Đề xuất thiết kế, chưa triển khai. |

**Hướng đáp ứng:** R2/R4; cần kiểm chứng bổ sung H0, QoS và khôi phục.  
**Ưu tiên:** hoàn thiện PA1, nghiên cứu PA2 ở phạm vi nhỏ.

### Lời thuyết trình

Phương án thứ nhất dùng OSD dự phòng, gọi là spare, kết hợp upmap. Em gọi OSD cần nâng là X và spare là S. Khi X vẫn hoạt động, các PG được chuyển sang S theo từng batch. Chỉ sau khi dữ liệu đã hội tụ, đủ replica hợp lệ và đạt điều kiện dừng, em mới dừng X để nâng cấp.

Ưu điểm là tận dụng cơ chế sẵn có của Ceph và có thể tiếp tục thử nghiệm ngay. Nhược điểm là vẫn phải sao chép dữ liệu; việc quản lý upmap và nhật ký thay đổi khá phức tạp. Khi trả PG về X, có thể phải copy lại, nên cần tính cả hai chiều vào thời gian và tải phát sinh.

Phương án thứ hai là Maintenance Shadow Replica. Ý tưởng là chuẩn bị một bản shadow trong lúc các replica bình thường vẫn phục vụ. Sau khi đồng bộ và kiểm chứng đạt, bản này mới được chuyển thành replica phục vụ hợp lệ trước khi dừng X.

Ưu điểm kỳ vọng là kiểm soát rõ hơn quá trình chuẩn bị và chuyển trạng thái. Tuy nhiên, đây là hướng cần phát triển thêm trong Ceph, đặc biệt ở peering và promotion. Shadow vẫn sử dụng CPU, đĩa và mạng, nên chưa thể kết luận ít ảnh hưởng QoS hơn khi chưa đo.

Với tiến độ hiện tại, em ưu tiên hoàn thiện bằng chứng của PA1; PA2 được nghiên cứu và thử prototype ở phạm vi nhỏ.

### Minh họa nên đặt

Nếu cần sơ đồ, chỉ thể hiện một thay đổi: **trước bảo trì, replica phục vụ gồm X/Y/Z; sau khi chuyển và xác minh hoàn tất, gồm S/Y/Z; lúc đó mới dừng X**.

Sơ đồ này minh họa pool replicated đã xác nhận cấu hình; cần đối chiếu size/min_size, failure domain và trạng thái thực tế. PA2 chỉ đạt trạng thái S/Y/Z sau khi promotion thành công.

### Câu chuyển sang slide 5

Để đánh giá các phương án, em cần chứng minh dữ liệu vẫn đúng và đo được mức ảnh hưởng lên ứng dụng.

## Slide 5 — Kiểm chứng toàn vẹn dữ liệu và tác động QoS

**Thời lượng gợi ý:** 1 phút 40 giây.  
**Ý chính:** H0 bổ sung mốc dữ liệu gốc; đo đối chứng để biết chi phí kiểm tra và nâng cấp.

### Chữ đưa lên slide

**H0 — Mốc kiểm chứng dữ liệu gốc**

- Lưu SHA-256 từ nguồn tin cậy; đối chiếu H1 khi đọc lại **đúng phiên bản**.
- Ưu điểm: tham chiếu độc lập, truy vết trước/sau, phát hiện canary không đạt.
- Bổ sung cho checksum/scrub của Ceph; **H0 không thay thế backup**.

**Kiểm thử ảnh hưởng QoS**

| A | B | C | D |
|---|---|---|---|
| Workload | Workload + H0 | Workload + PA1 | Workload + PA1 + H0 |

**Đo:** p95/p99, IOPS/throughput, lỗi, CPU/disk/network, byte copy và thời gian.  
**Hiện có:** 16/16 đối tượng khớp checksum qua client; **chưa có số liệu đối chứng QoS**.

### Lời thuyết trình

H0 là giá trị hash lấy từ dữ liệu gốc tin cậy, làm mốc để so sánh với dữ liệu đọc lại. Em bổ sung H0 vì việc các bản sao giống nhau chưa đủ để chứng minh chúng đúng với dữ liệu đầu vào. Ceph đã có checksum và scrub; H0 bổ sung một điểm đối chiếu ở phía dữ liệu ứng dụng.

Ưu điểm là có bằng chứng trước và sau thử nghiệm, đồng thời nhận biết canary không đạt. Khi so sánh phải gắn với đúng object version hoặc snapshot và vùng dữ liệu, tránh nhầm một thay đổi hợp lệ thành lỗi. H0 chỉ lưu dấu kiểm tra, không chứa dữ liệu để khôi phục.

Về tác động hiệu năng, em dự kiến bốn lượt đo. A là tải ứng dụng bình thường. B bổ sung H0 để đo riêng chi phí kiểm chứng. C chạy tải cùng PA1, còn D bổ sung H0 trong lúc chạy PA1.

So sánh B với A cho biết chi phí H0; C với A cho biết ảnh hưởng nâng cấp; D với C cho biết chi phí kiểm H0 trong lúc nâng. Các lượt phải giữ điều kiện tương đương và được chạy lặp lại.

Hiện em có kết quả 16 trên 16 đối tượng khớp checksum qua client. Các số liệu về độ trễ, băng thông và overhead H0 vẫn cần đo, nên em chưa kết luận mức ảnh hưởng cụ thể.

### Ghi chú cho người trình bày

Trong C, chỉ không chạy tác vụ H0 của ứng dụng **đồng thời trong cửa sổ đo**. Giữ cơ chế bảo vệ dữ liệu của Ceph nhất quán; vẫn phải hoàn tất các kiểm tra bắt buộc trước khi chấp nhận canary.

Ảnh checksum hiện có minh chứng cho tập đối tượng đọc qua client; không tự chứng minh từng replica đã được kiểm tra riêng hoặc toàn bộ quy trình H0 đã hoàn thiện.

### Câu chuyển sang slide 6

Ngoài kết quả ở trạng thái bình thường, phương án còn phải được kiểm tra khi nâng cấp hoặc phục hồi gặp lỗi.

## Slide 6 — Backup, fallback, rollback và kiểm thử lỗi

**Thời lượng gợi ý:** 1 phút 45 giây.  
**Ý chính:** phải có cách giữ dịch vụ, hoàn nguyên thay đổi và phục hồi dữ liệu phù hợp từng tình huống.

### Chữ đưa lên slide

| Cơ chế | Cách sử dụng |
|---|---|
| **Backup** | Sao lưu độc lập theo phạm vi ưu tiên; restore thử và kiểm dữ liệu. |
| **Fallback** | X lỗi sau khi chuyển hoàn tất: giữ dịch vụ trên S/Y/Z còn hợp lệ, dừng rollout. |
| **Rollback** | Hoàn nguyên placement/cấu hình theo journal, từng batch và đủ điều kiện an toàn. |

**Diễn tập:** X không khởi động; spare/peer lỗi; H0 mismatch; QoS vượt ngưỡng; restore backup.

**Bằng chứng:** đọc/ghi ứng dụng, H0, thời gian gián đoạn, thời gian và điểm dữ liệu phục hồi.

**Lưu ý:** rollback placement và quay về image cũ cần được kiểm chứng riêng.  
**Trạng thái:** kế hoạch kiểm thử, chưa kết luận đã đạt.

### Lời thuyết trình

Em phân biệt ba cơ chế để tránh dùng chung một phương án cho mọi loại lỗi.

Backup là bản dữ liệu độc lập để phục hồi. Với dung lượng kho hiện có, cần chọn phạm vi ưu tiên và thử restore thực tế. Em dự kiến khôi phục dữ liệu S3 vào bucket riêng và RBD vào image riêng, sau đó kiểm tra bằng ứng dụng và đối chiếu dữ liệu. Snapshot nằm trong cùng cụm vẫn phụ thuộc cụm, nên chưa thay thế bản backup độc lập.

Fallback là giữ dịch vụ trên tập replica đang hợp lệ. Ví dụ, nếu đã chuyển hoàn tất sang S, Y, Z mà X không khởi động sau nâng, em sẽ dừng rollout, giữ workload trên tập còn tốt và xử lý X trước khi tiếp tục.

Rollback là hoàn nguyên những thay đổi placement hoặc cấu hình theo nhật ký. Việc này chỉ thực hiện khi đích quay về còn an toàn và có thể phát sinh backfill. Đổi daemon về image cũ cần kiểm tra tương thích riêng, không mặc định cứ có lỗi là đổi lại được.

Các bài diễn tập sẽ bao gồm lỗi OSD, checksum không khớp, QoS vượt ngưỡng và phục hồi từ backup. Em sẽ đo thời gian phục hồi và xác định điểm dữ liệu khôi phục được để đối chiếu mục tiêu RTO, RPO. Đây là phần cần hoàn thiện bằng chứng trong tháng tới.

### Ghi chú cho người trình bày

Khi X đang lỗi, không đưa PG trở lại X chỉ để khôi phục sơ đồ ban đầu. Nếu có thêm peer lỗi, ưu tiên phục hồi replica/dịch vụ và dừng nâng các OSD tiếp theo.

“Backup thành công” phải có bằng chứng restore và đọc ứng dụng, không chỉ có log sao chép xong. Kết quả checksum sau nâng hiện có không thay cho kết quả restore.

### Câu chuyển sang slide 7

Từ các phần đã làm và các bằng chứng còn thiếu, em sắp xếp công việc tháng tới theo thứ tự ưu tiên sau.

## Slide 7 — Kế hoạch tháng tới và điều kiện lựa chọn

**Thời lượng gợi ý:** 1 phút.  
**Ý chính:** hoàn thiện PA1 có số liệu và khả năng khôi phục; tiếp tục PA2 ở mức nghiên cứu.

### Chữ đưa lên slide

| Ưu tiên | Công việc | Đầu ra |
|---|---|---|
| **1** | Xác nhận hiện trạng và lộ trình phiên bản | Inventory, tương thích, vòng đời hỗ trợ, trình tự nâng. |
| **2** | Hoàn thiện PA1 dưới tải | H0, QoS, byte copy, thời gian/batch và mức song song. |
| **3** | Diễn tập backup/restore và các tình huống lỗi | Log, kết quả phục hồi, đối chiếu RTO/RPO. |
| **4** | Hoàn thiện website; nghiên cứu PA2 | Bằng chứng theo từng lần chạy; prototype nhỏ. |

**Sản phẩm cuối tháng:** MOP, ma trận yêu cầu–bằng chứng, báo cáo kiểm thử.

**Điều kiện đề xuất mở rộng:** đạt tiêu chí bắt buộc; các giới hạn và ngoại lệ đã được thống nhất.

### Lời thuyết trình

Trong tháng tới, em ưu tiên xác nhận lại hiện trạng và lộ trình phiên bản trước. Sau đó, em sẽ hoàn thiện PA1 dưới tải, bổ sung H0, đo QoS, lượng dữ liệu copy và thời gian từng batch.

Song song, em sẽ diễn tập các tình huống lỗi cùng backup, restore và rollback. Website sẽ được hoàn thiện để lưu bằng chứng theo từng lần chạy. Với PA2, mục tiêu là làm rõ thiết kế và thử prototype nhỏ.

Đầu ra em hướng tới là một MOP kèm báo cáo kiểm thử, thể hiện rõ tiêu chí nào đã đạt và phần nào còn thiếu. Em chỉ đề xuất mở rộng khi có đủ bằng chứng cho phạm vi đó.

Qua tháng đầu, em đã có nền tảng RBD, RGW, công cụ hỗ trợ và một thử nghiệm nâng cấp trên lab. Em mong anh chị góp ý về phạm vi ưu tiên và các ngưỡng nghiệm thu để em hoàn thiện trong tháng tới. Em cảm ơn anh chị.

### Cách kết thúc

Dừng ở bảng kế hoạch để tiếp nhận câu hỏi. Khi trao đổi về một kết quả, nêu rõ phạm vi đã kiểm chứng và bài kiểm thử tiếp theo cần bổ sung.

---

# Phần giải thích chi tiết để trả lời câu hỏi

Phần này không đưa thêm lên slide và không nằm trong thời lượng trình bày chính.

## 1. Từ yêu cầu đến bằng chứng

| Yêu cầu | Phương án hoặc công cụ hướng tới đáp ứng | Bằng chứng hiện có | Phần cần bổ sung |
|---|---|---|---|
| **R1 — Toàn vẹn** | H0/H1 đúng phiên bản; kiểm tra của Ceph; điều kiện chấp nhận canary. | 16/16 đối tượng kiểm tra qua client khớp checksum. | Manifest chuẩn hóa; độ bao phủ; dữ liệu ghi được xác nhận thành công; phát hiện mismatch. |
| **R2 — Dịch vụ** | Chuẩn bị S thành replica hợp lệ trước khi dừng X. | Đã thực hiện nâng một OSD trên lab; có bước kiểm tra điều kiện dừng. | Số đo I/O trong từng giai đoạn; lỗi bổ sung trong lúc bảo trì; peering và phục hồi. |
| **R3 — QoS** | Batch, giới hạn tải kiểm tra, điều kiện dừng mở batch. | Chưa có bộ số liệu đối chứng. | A/B/C/D, p95/p99, lỗi và mức IOPS/throughput tối thiểu theo workload. |
| **R4 — Tài nguyên** | Theo dõi placement, spare và peer; journal thay đổi. | Có thao tác PA1 trong lab. | Byte copy hai chiều, tài nguyên, remap ngoài kế hoạch, dung lượng dự phòng và mức song song. |
| **R5 — Khôi phục** | Backup độc lập; fallback; rollback theo journal. | Chưa có bằng chứng nghiệm thu các ca khôi phục trong đợt nâng. | Restore S3/RBD, thử backup lỗi, rollback khi lỗi, số đo phục hồi. |
| **R6 — Khả thi** | Lộ trình phiên bản, trình tự daemon, canary và các batch tăng dần. | PA1 mới thử một OSD; PA2 ở mức thiết kế. | Inventory production, tương thích client/daemon, phiên bản đích, lịch trình từ số đo thực tế. |

PA2 chưa có kết quả triển khai để ghi “đạt” ở bất kỳ yêu cầu nào. Bảng đánh giá PA2 sau prototype cần sử dụng cùng tiêu chí và điều kiện so sánh phù hợp.

## 2. Diễn giải H0 và cách kiểm chứng

**H0 được thêm vào để giải quyết câu hỏi:** dữ liệu client đọc được sau các bước thử nghiệm có còn đúng với dữ liệu gốc tin cậy hay không?

Quy trình dự kiến:

1. Chọn tập dữ liệu và điểm phiên bản cố định; tính SHA-256 từ nguồn tin cậy trước đoạn xử lý cần kiểm chứng.
2. Lưu manifest gồm định danh dữ liệu, phiên bản hoặc snapshot, phạm vi byte khi cần, kích thước và hash tham chiếu.
3. Sau thao tác cần kiểm tra, đọc lại đúng dữ liệu đó để tính H1.
4. So sánh H0/H1, số lượng và phạm vi đã kiểm tra; lưu kết quả theo lần chạy.
5. Nếu mismatch, dừng mở rộng canary, giữ bằng chứng và xác minh nguồn hợp lệ trước khi phục hồi hoặc ghi đè.

| Dịch vụ | Cần cố định điều gì? | Kiểm tra gì? |
|---|---|---|
| **RGW/S3** | Object và version cụ thể, hoặc tập object bất biến nếu chưa dùng versioning. | Định danh, số lượng, kích thước, checksum; metadata trong phạm vi yêu cầu. |
| **RBD** | Snapshot/điểm ghi nhất quán và offset/length, hoặc tập file đã cố định. | Đúng vùng dữ liệu/file, checksum và khả năng đọc ở cấp ứng dụng. |

**Ưu điểm:** có mốc độc lập với việc các replica đồng ý với nhau; hỗ trợ truy vết trước/sau; tạo điều kiện chấp nhận hoặc dừng canary.

**Chi phí và giới hạn:** tốn CPU tính hash, I/O đọc lại và lưu manifest; phải quản lý phiên bản chính xác. Kiểm qua client không chứng minh riêng từng replica. H0 không lưu nội dung nên không thể dùng để tái tạo dữ liệu đã mất.

## 3. Đo QoS sao cho có thể kết luận

### Các lượt đo

| Lượt | Điều kiện | Mục đích |
|---|---|---|
| **A** | Workload RBD/S3, không có đợt nâng trong cửa sổ đo. | Lấy baseline. |
| **B** | Như A, thêm tác vụ H0. | So B/A để đo chi phí H0. |
| **C** | Workload và PA1; không chạy H0 của ứng dụng đồng thời trong cửa sổ đo. | So C/A để đo ảnh hưởng nâng cấp. |
| **D** | Như C, thêm H0 đồng thời. | So D/C để đo chi phí H0 trong lúc nâng. |
| **Bổ sung** | Workload cùng backup hoặc restore. | Xác định mức tải sao lưu/phục hồi phù hợp. |

Kết quả C chỉ phục vụ đối chứng hiệu năng; các kiểm tra toàn vẹn bắt buộc vẫn phải hoàn tất trước khi chấp nhận canary. Không thay đổi tùy tiện checksum/scrub của Ceph giữa các lượt.

### Điều kiện so sánh

- Cùng tập dữ liệu, loại thao tác, kích thước I/O/object và mức đồng thời của workload.
- Cùng trạng thái đầu vào, điều kiện cache, thời gian warm-up và cấu hình kiểm tra nền.
- Cùng batch và cùng giai đoạn khi so C/D: chuyển PG, nâng daemon hoặc trả PG.
- Chạy lặp lại; tách chi phí tạo H0 khỏi chi phí đọc lại xác minh.
- Ghi số đo ở client và trên cụm; tránh quy toàn bộ ảnh hưởng thành lỗi của OSD nếu máy sinh tải đã bão hòa.

### Số liệu báo cáo và phản ứng

| Nhóm | Số đo | Khi không đạt |
|---|---|---|
| **Trải nghiệm ứng dụng** | p95/p99 riêng read/write hoặc PUT/GET, error/timeout rate. | Không mở batch mới; giảm tác vụ H0/concurrency phù hợp; theo dõi phục hồi. |
| **Năng lực xử lý** | IOPS, throughput và lượng dữ liệu thực sự hoàn tất. | Kiểm tra bottleneck, tải nền và mức song song. |
| **Tài nguyên** | CPU client/OSD, disk latency/utilization, network, headroom spare. | Điều chỉnh tốc độ/batch theo tài nguyên và trạng thái replica. |
| **Chi phí nâng** | Byte copy đi/về, thời gian từng giai đoạn, thời gian hội tụ. | Cập nhật dự tính thời gian và lựa chọn quy mô batch. |

Các ngưỡng cụ thể hiện **cần thống nhất**. Khi có sự cố thật, dừng rollout và ưu tiên recovery cần thiết cho dữ liệu/dịch vụ. Việc giảm tải kiểm chứng không có nghĩa được bỏ qua điều kiện kiểm tra toàn vẹn.

Nếu cần chứng minh PA1 tốt hơn quy trình nâng cấp đang dùng, phải bổ sung một lượt chạy quy trình đó trên cùng lab, tải và phạm vi lỗi. A/B/C/D hiện giúp phân tách các nguồn ảnh hưởng; chưa tự chứng minh PA1 tốt hơn mọi cách nâng cấp khác.

## 4. Backup và diễn tập phục hồi

### Phạm vi backup

- **Dữ liệu:** lựa chọn theo mức quan trọng, dung lượng và mục tiêu phục hồi. Lưu bản sao ngoài cụm hoặc ngoài phạm vi lỗi cần bảo vệ; ghi rõ phần được và chưa được bảo vệ.
- **RGW/S3:** sao lưu tập object/version đã chọn, kèm manifest và metadata cần phục hồi. Khi restore vào đích riêng, lưu quan hệ giữa bản gốc và đối tượng được phục hồi.
- **RBD:** nếu cần nhất quán ứng dụng, phối hợp flush/quiesce ứng dụng hoặc filesystem, tạo điểm snapshot phù hợp rồi export ra nơi độc lập. Restore bằng import vào image thử nghiệm mới.
- **Cấu hình và thay đổi:** lưu cấu hình, trạng thái CRUSH/OSDMap làm bằng chứng, upmap và các thay đổi thuộc đợt bảo trì. Khi hoàn nguyên phải đối chiếu hiện trạng, không nạp lại máy móc một map cũ.
- **Nghiệm thu:** restore được, kiểm dữ liệu đúng và ứng dụng đọc được. Tách kết quả “sao lưu xong” khỏi kết quả “phục hồi đạt”.

**RTO** là mục tiêu thời gian phục hồi dịch vụ. **RPO** là mục tiêu mức mất dữ liệu chấp nhận được tính theo thời gian. Bài test cần đo thời gian phục hồi thực tế và xác định điểm dữ liệu phục hồi được để so sánh với hai mục tiêu này.

### Các bài diễn tập dự kiến

Mỗi ca chạy riêng trên lab; đưa môi trường về trạng thái ổn định trước ca tiếp theo. Bảng dưới đây là kế hoạch, chưa phải kết quả PASS.

| Tình huống | Phản ứng cần kiểm chứng | Bằng chứng đạt |
|---|---|---|
| **X không khởi động sau nâng** | Chỉ khi đã chuyển hoàn tất: giữ workload trên S/Y/Z còn hợp lệ, dừng nâng tiếp và xử lý X. | I/O, lỗi/gián đoạn và H0 trong giới hạn đã chốt; không tự mở batch mới. |
| **Spare S lỗi trước khi dừng X** | Không dừng X; dừng mở batch và phục hồi đủ replica trước khi thử lại. | Không vượt qua điều kiện cho phép dừng X khi chưa đủ bản sao hợp lệ. |
| **Một peer lỗi khi X đang offline** | Dừng rollout; ưu tiên phục hồi peer hoặc X theo trạng thái thực tế. | Quan sát peering, I/O, lỗi, thời gian gián đoạn, H0 và quá trình khôi phục. |
| **H0 không khớp** | Dừng mở rộng canary, xác minh version và tìm nguồn dữ liệu còn đúng. | Không báo PASS; chỉ phục hồi từ nguồn đã xác minh phù hợp. |
| **QoS vượt ngưỡng** | Không mở batch mới; giảm tải kiểm tra hoặc concurrency; để phần đang chạy hội tụ khi an toàn. | Log phát hiện ngưỡng, thời gian phản ứng và QoS sau điều chỉnh. |
| **Rollback placement** | Hoàn nguyên từng thay đổi trong journal khi đích còn lành mạnh; giữ các override ngoài phạm vi phiên bảo trì. | PG hội tụ, dữ liệu đúng, ghi lượng copy và thời gian phát sinh. |
| **Restore RGW/S3** | Phục hồi tập object vào bucket/prefix riêng từ backup độc lập. | Đủ đối tượng, đúng kích thước/checksum/metadata đã chốt và đọc được qua S3. |
| **Restore RBD** | Import dữ liệu đã export vào image thử nghiệm mới. | Mount/đọc được, dữ liệu khớp manifest và kiểm tra ứng dụng đạt. |
| **Backup bị thiếu hoặc hỏng** | Dùng bản sao dành riêng cho test để tạo tình huống thiếu thành phần hoặc sai hash. | Bộ kiểm tra nhận ra lỗi; không ghi nhận backup/restore PASS. |

Với bài thêm một peer lỗi, phải xác nhận pool replicated, size/min_size, replica còn hợp lệ và failure domain. Ví dụ size=3/min_size=2 chỉ là một cấu hình cần đối chiếu; không đồng nghĩa cam kết I/O không gián đoạn trong lúc peering. Không hạ min_size để đạt bài test.

Mô phỏng H0 mismatch bằng bộ kiểm thử hoặc bản sao riêng; không cần sửa trực tiếp dữ liệu BlueStore đang phục vụ.

### Mẫu ghi kết quả

| Ca kiểm thử | Phạm vi/phiên bản dữ liệu | Điểm backup | Thời gian phục hồi | Điểm dữ liệu phục hồi | H0/đọc ứng dụng | Kết luận |
|---|---|---|---|---|---|---|
| [Mã ca] | [Object/version hoặc image/snapshot] | [Thời điểm] | [Số đo] | [Mốc phục hồi, ghi bị thiếu nếu có] | [Kết quả và độ bao phủ] | [Chưa chạy/PASS/FAIL] |

## 5. Câu hỏi có thể gặp và câu trả lời gợi ý

### “Sau một tháng, em làm được gì cụ thể?”

Em đã thực hành RBD và RGW, xây dựng website hỗ trợ kiểm thử, và thực hiện một thử nghiệm nâng cấp OSD trên lab. Em có bằng chứng về phiên bản sau nâng và 16/16 đối tượng kiểm tra khớp checksum. Phần tiếp theo là bổ sung số đo QoS và các bài lỗi, phục hồi để đánh giá phạm vi áp dụng.

### “Tại sao thêm H0 khi Ceph đã có checksum?”

Checksum và scrub của Ceph bảo vệ, kiểm tra dữ liệu ở bên trong hệ thống. H0 bổ sung mốc lấy từ dữ liệu gốc tin cậy để đối chiếu dữ liệu ứng dụng đọc lại. Giá trị chính là có thêm điểm kiểm chứng độc lập và bằng chứng trước/sau. Chi phí CPU, đọc dữ liệu và quản lý manifest cần được đo.

### “16/16 đối tượng đúng đã đủ kết luận an toàn chưa?”

Kết quả đó xác nhận tập đối tượng đã kiểm tra qua client khớp checksum. Để kết luận cho phạm vi lớn hơn, em cần mở rộng tập dữ liệu, phiên bản và workload; kiểm thử trong từng giai đoạn và khi có lỗi. Kết quả hiện tại cũng chưa chứng minh từng replica riêng lẻ hoặc khả năng restore backup.

### “Spare có phải backup không?”

Spare trong phương án này trở thành replica phục vụ của cụm. Backup là bản dữ liệu có điểm phục hồi xác định, được giữ ngoài phạm vi lỗi cần bảo vệ và phải thử restore. Em cần cả cơ chế giữ dịch vụ lẫn cơ chế phục hồi phù hợp với phạm vi đã chốt.

### “Nếu lỗi thì quay lại image cũ có được không?”

Em sẽ tách rollback placement/cấu hình khỏi việc quay lại phiên bản phần mềm. Quay về image cũ phải kiểm tra tương thích phiên bản, feature và trạng thái lưu trữ cho đúng bước nâng đó. Khi chưa có bằng chứng, em ưu tiên giữ workload trên tập replica còn hợp lệ, dừng rollout và xử lý nguyên nhân.

### “PA2 có chắc nhanh hơn hoặc ít ảnh hưởng hơn PA1 không?”

Chưa có số đo để kết luận. PA2 kỳ vọng chủ động chuẩn bị dữ liệu và kiểm soát trạng thái tốt hơn, nhưng vẫn phải copy dữ liệu và tiêu thụ tài nguyên. Em cần prototype và đo trên cùng điều kiện với PA1 trước khi khẳng định lợi ích hiệu năng.

### “Kho backup 100 TB thì bảo vệ 24 PB thế nào?”

Với dung lượng đã trao đổi, em chưa thể đề xuất backup đầy đủ toàn bộ 24 PB vào kho này. Cần phân loại dữ liệu, chốt phạm vi ưu tiên và chỉ rõ phần chưa được backup. Nếu yêu cầu bảo vệ toàn bộ vượt khả năng hiện có, phải bổ sung năng lực hoặc thống nhất lại mục tiêu phục hồi.

### “Đã có thể áp dụng production chưa?”

Hiện em mới có canary một OSD trên lab. Để đề xuất production, cần hoàn thiện ma trận yêu cầu và bằng chứng, nhất là QoS, lỗi bổ sung, backup/restore và tương thích. Phạm vi canary tiếp theo cũng phải được chọn từ kết quả kiểm thử và điều kiện hệ thống thực tế.

### “Khoảng 1.600 OSD có nâng xong trong sáu tháng không?”

Em chưa đủ số liệu để cam kết. Em sẽ đo thời gian một batch, lượng copy cả hai chiều, các cửa sổ bảo trì và giới hạn số OSD có thể làm đồng thời. Khi đó mới ước tính tiến độ có tính đến spare, failure domain và tài nguyên các peer, thay vì nhân trực tiếp thời gian của một OSD lab.

### “Phiên bản cuối cùng sẽ là phiên bản nào?”

Em cần rà soát lại trước khi chốt. Theo bảng vòng đời upstream đã đối chiếu, cả Pacific và Reef đều đã hết bảo trì tại thời điểm báo cáo. Lộ trình cũ tới 18.2.7 vì vậy cần xem lại thời gian hỗ trợ, các bước nâng và tương thích thực tế. Nếu dùng bản phân phối có hỗ trợ riêng thì cần kiểm tra thêm chính sách của nhà cung cấp.

## 6. Minh chứng cần gắn với lời nói

| Vị trí | Minh chứng | Dùng để chứng minh |
|---|---|---|
| **Slide 1** | Ảnh thao tác RBD/fio hoặc RGW; ảnh website thực tế. | Phần học và công cụ đã thực hiện. |
| **Slide 1 hoặc 4** | Phiên bản OSD trước/sau, log chuyển PG và điều kiện dừng trong MOP. | Thử nghiệm PA1 một OSD trên lab. |
| **Slide 5** | Dòng checked=16, failed=0, listed=16 và phạm vi tập kiểm tra. | Kết quả checksum qua client của tập đã kiểm. |
| **Slide 5** | Bảng kết quả A/B/C/D sau khi đo. | Tác động QoS; hiện chưa có kết quả thì ghi “chưa đo”. |
| **Slide 6** | Log diễn tập và kết quả restore sau khi hoàn thành. | Khả năng khôi phục; hiện ghi “kế hoạch kiểm thử”. |

Website nên được giới thiệu qua một ca sử dụng đã hoạt động thực tế. Chỉ mô tả chức năng tự động hóa, điều khiển nâng cấp hoặc thu thập bằng chứng là “đã có” nếu đúng với phiên bản công cụ đang chạy; các chức năng còn lại đưa vào kế hoạch tháng tới.

## 7. Căn cứ nội dung và nguồn kỹ thuật

Bản thuyết trình này phát triển từ **Cau_truc_bao_cao_thang_dau_Ceph.md**, giữ cấu trúc 7 slide đã thống nhất.

**Tài liệu nội bộ đã dùng để đối chiếu**

- **RBD(2).docx:** thao tác RBD, filesystem/mount và fio.
- **MOP(2).docx:** PA1 trên lab, phiên bản OSD và kết quả checksum 16/16 đối tượng.
- **plan(3) (1)(4).md:** hướng PA1/PA2, điều kiện kiểm chứng dữ liệu, QoS và lỗi bảo trì.
- **present.pptx:** kiến thức nền Ceph; không thay thế bằng chứng backup/restore hoặc lỗi bổ sung trong lúc nâng cấp.

**Nguồn chính thức**

- [Ceph Releases](https://docs.ceph.com/en/latest/releases/): vòng đời các nhánh; đối chiếu ngày 27/09/2026.
- [Ceph v16.2.15 Pacific released](https://ceph.io/en/news/blog/2024/v16-2-15-pacific-released/): các sửa đổi của phiên bản đã thử trên lab.
- [RBD Snapshots](https://docs.ceph.com/en/pacific/rbd/rbd-snapshot/) và [rbd manual](https://docs.ceph.com/en/pacific/man/8/rbd/): snapshot, export/import và phục hồi.
- [Ceph Pools](https://docs.ceph.com/en/pacific/rados/operations/pools/): replica size/min_size.
- [Upgrading Ceph](https://docs.ceph.com/en/pacific/cephadm/upgrade/): trình tự và điều kiện nâng cấp với cephadm.
- [BlueStore Checksums](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/#checksums) và [OSD Scrubbing](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/#scrubbing): cơ chế kiểm tra dữ liệu của Ceph.

H0, PA2 và các ma trận thử nghiệm trong tài liệu là thiết kế/đề xuất của bài toán; không mô tả PA2 như tính năng Ceph đã có sẵn.

