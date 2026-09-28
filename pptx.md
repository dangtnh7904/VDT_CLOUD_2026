
Dưới đây là **toàn bộ prompt**, gồm **1 slide mở đầu và 12 slide nội dung**. Mình giữ nhãn nội dung **slide 7–9** cho phần PA1/H0 để bạn dễ đối chiếu. Khi ghép thành deck, footer đánh số từ **1/13 đến 13/13**.

Bạn gửi **prompt chung trước**, sau đó gửi các prompt từng slide.

**Prompt chung áp dụng cho toàn bộ slide**

Thiết kế bộ slide báo cáo tiến độ nghiên cứu nâng cấp Ceph, dành cho mentor và nhóm kỹ thuật. Bộ slide gồm một trang mở đầu và 12 trang nội dung.

Sử dụng slide mẫu Viettel đã cung cấp làm chuẩn thiết kế.

YÊU CẦU THIẾT KẾ

- Giữ nguyên footer Viettel của mẫu, gồm logo, đường kẻ, thông tin và vị trí các thành phần. Chỉ cập nhật số trang theo bộ 13 trang.
- Giữ font và màu của mẫu. Nội dung dùng nền sáng, chữ tối, màu đỏ Viettel để nhấn các điểm chính.
- Mỗi slide có một bảng, sơ đồ hoặc nhóm minh chứng chính. Bố cục thoáng, căn chỉnh thống nhất.
- Chữ trên slide ngắn và đủ lớn để trình chiếu. Chuyển giải thích dài vào speaker notes.
- Sơ đồ kỹ thuật, bảng và văn bản phải chỉnh sửa được.
- Chỉ dùng ảnh chụp thật từ lab, repository hoặc web đã triển khai. Khi thiếu ảnh, đặt placeholder có mô tả rõ.
- Không sinh ảnh minh họa AI, ảnh máy chủ trang trí hoặc biểu đồ có số liệu giả.

YÊU CẦU NỘI DUNG

- Chỉ trình bày PA1 và phần kết hợp với H0.
- Phân biệt rõ kết quả đã thực hiện, kết quả được báo cáo nhưng cần log minh chứng, và tính năng mới đề xuất.
- Các bài checksum trước đây là kiểm thử toàn vẹn dữ liệu. H0 chưa được triển khai.
- H0 gồm hai phần:
  1. H0-R kiểm chứng dữ liệu local trên OSD vừa nâng cấp sau recovery/backfill, trước khi mở workload canary.
  2. H0-W bổ sung kiểm tra integrity vào đường ghi, làm điều kiện trước khi trả success cho client.
- Ba mức lựa chọn thuộc H0-W: kiểm buffer primary, kiểm thêm buffer replica, và đọc lại sau ghi bền.
- Những thay đổi H0 trong đường xử lý OSD cần phát triển Ceph và giao thức liên quan. Web phụ trách cấu hình, điều phối và hiển thị bằng chứng.
- Giữ các cơ chế native của Ceph trong mọi phương án.

Mỗi slide có speaker notes bằng tiếng Việt, giải thích được ý nghĩa, bằng chứng và giới hạn của nội dung. Phần H0 có notes chi tiết hơn các slide khác.

Đánh số trang vật lý: trang mở đầu là 1/13, các slide nội dung 1–12 tương ứng trang 2/13–13/13.

**Prompt slide mở đầu — Trang 1/13**

Tạo slide mở đầu theo prompt chung và giữ footer Viettel.

Tiêu đề chính:
“NGHIÊN CỨU QUY TRÌNH NÂNG CẤP CEPH”

Tiêu đề phụ:
“Báo cáo tiến độ và hướng phát triển PA1 kết hợp H0”

Thông tin:

- Người thực hiện: [Họ và tên]
- Đơn vị/nhóm: [Đơn vị]
- Người hướng dẫn: [Mentor]
- Thời gian: [Ngày báo cáo]

Bố cục:
Đặt tiêu đề lớn ở vùng trung tâm hoặc lệch trái theo mẫu. Thông tin người trình bày ở bên dưới. Giữ nhiều khoảng trắng, không đưa bảng kỹ thuật hoặc sơ đồ vào trang mở đầu.

Speaker notes:
Giới thiệu phạm vi báo cáo gồm nền tảng nghiên cứu, thử nghiệm đã thực hiện, quy trình nâng toàn cluster, PA1 trong pha OSD và thiết kế H0 để kiểm chứng dữ liệu tại các thời điểm cụ thể.

Footer: 1/13.

**Prompt slide 1 — Kết quả tháng đầu và mục tiêu tiếp theo**

Tạo slide nội dung 1, tiêu đề:
“Kết quả tháng đầu và mục tiêu tiếp theo”

Bố cục:
Một bảng ngắn gồm hai cột “Đã thực hiện” và “Hướng phát triển”.

Nội dung cột “Đã thực hiện”:

- Nghiên cứu kiến trúc Ceph, placement, replication và nâng cấp bằng cephadm.
- Xây dựng lab, thu thập baseline và thử nghiệm PA1.
- Nâng thử một OSD, kiểm tra toàn vẹn bằng checksum.
- Phát triển nền web kiểm thử RBD/RGW.

Nội dung cột “Hướng phát triển”:

- Hoàn thiện quy trình nâng toàn cluster theo từng loại daemon.
- Tích hợp PA1 vào pha nâng OSD.
- Phát triển H0-R và ba mức H0-W.
- Bổ sung lựa chọn OSD/PG canary và đánh giá bằng số đo.

Đặt một dòng nhấn phía dưới:
“H0 đang ở giai đoạn thiết kế. Checksum test hiện có là bằng chứng kiểm thử trong phạm vi đã chạy.”

Speaker notes:
Giải thích kết quả hiện tại mới tạo nền tảng cho quy trình nâng cấp. Một OSD đã nâng chưa đại diện cho toàn cluster. Các tính năng H0 và bộ chọn scope canary cần được phát triển, kiểm thử và nghiệm thu riêng.

Footer: 2/13.

**Prompt slide 2 — Bài toán nâng cấp và yêu cầu vận hành**

Tạo slide nội dung 2, tiêu đề:
“Bài toán nâng cấp và yêu cầu vận hành”

Bố cục:
Phía trên là một dòng bối cảnh. Phía dưới là bảng hai cột “Yêu cầu” và “Cách đánh giá”.

Bối cảnh:
“Quy mô production đã trao đổi: khoảng 1.600 OSD, 24 PB dữ liệu, dịch vụ RGW và RBD.”

Ghi chú nhỏ:
“Đầu vào lập kế hoạch, cần xác nhận bằng inventory.”

Bảng yêu cầu:

1. Toàn vẹn dữ liệu
   Đánh giá bằng kiểm tra native, reference độc lập và phạm vi dữ liệu đã kiểm.
2. Khả năng phục vụ
   Theo dõi quorum, trạng thái PG, lỗi và timeout của client.
3. Ảnh hưởng hiệu năng
   Đo p95/p99, throughput và tải CPU, disk, network.
4. Kiểm soát di chuyển dữ liệu
   Giới hạn scope, dung lượng và số đợt recovery/backfill.
5. Phục hồi khi lỗi
   Xác định nguồn dữ liệu tốt, phương án giữ dịch vụ và restore.
6. Khả năng thực hiện lại
   Lưu cấu hình, phiên bản, mapping, log và kết quả từng đợt.

Speaker notes:
Trình bày nhu cầu xây dựng quy trình nâng có kiểm chứng cho hệ thống lớn và phiên bản đang sử dụng. Dung lượng backup khoảng 100 TB đã trao đổi chỉ bao phủ một phần dữ liệu, nên phải chọn dữ liệu ưu tiên và kiểm thử restore.

Mục tiêu tiến độ khoảng sáu tháng cần được đánh giá từ tốc độ migration và tài nguyên thực đo. PA1 có thể nghiên cứu thực hiện theo nhóm OSD, nhưng phải kiểm tra an toàn của cả nhóm và ngân sách tài nguyên.

Footer: 3/13.

**Prompt slide 3 — Hiện trạng lab và bằng chứng đã có**

Tạo slide nội dung 3, tiêu đề:
“Hiện trạng lab và bằng chứng đã có”

Bố cục:
Nửa trái là bảng hiện trạng. Nửa phải là vùng minh chứng với placeholder cho log thật.

Bảng hiện trạng:

- Môi trường: Ceph triển khai bằng cephadm.
- Công việc PA1: thu baseline, chuẩn bị spare và thử điều khiển mapping.
- Bài nâng được báo cáo: một OSD từ 16.2.5 lên 16.2.15.
- Kiểm tra dữ liệu được báo cáo: 16/16 mẫu khớp checksum.
- Trình tự đã thử: nâng OSD trước MON/MGR.
- H0: chưa triển khai.

Placeholder minh chứng:
[Ảnh version của OSD trước và sau nâng]
[Ảnh kết quả checksum, kèm run ID và thời điểm]
[Ảnh mapping PG hoặc log PA1 tương ứng]

Dòng nhấn:
“Kết quả thuộc phạm vi thử nghiệm một OSD.”

Speaker notes:
Giải thích việc nâng OSD trước MON/MGR được ghi nhận như một bài thử riêng cho pha OSD. Quy trình toàn cluster phải được bổ sung theo thứ tự cephadm.

Kết quả 16/16 cần đi cùng danh sách mẫu và log thực tế. Không dùng nó để kết luận toàn cluster đã được kiểm chứng hoặc H0 đã hoạt động.

Trước lượt tiếp theo cần lấy inventory mới. Không suy ra trạng thái hiện tại từ log cũ và không mặc định hạ phiên bản OSD đã nâng.

Footer: 4/13.

**Prompt slide 4 — Web kiểm thử RBD/RGW hiện có**

Tạo slide nội dung 4, tiêu đề:
“Web kiểm thử RBD/RGW hiện có”

Bố cục:
Ưu tiên hai ảnh chụp web thật. Bên cạnh mỗi ảnh là một nhóm chức năng ngắn.

Nhóm RGW:

- Quản lý và chạy workload.
- Pause, resume, stop.
- Thu thập telemetry và kết quả chạy.

Nhóm RBD:

- Quản lý vòng đời tài nguyên.
- File browser và terminal.
- Tạo baseline và verify dữ liệu file.

Dòng bằng chứng:
“Validation 24/09: 73 backend tests, 14 Node tests, 4 frontend tests.”

Dòng kết quả kiểm thử:
“Bài RBD live: baseline 4 file, phát hiện overwrite, verify đạt sau phục hồi.”

Chú thích:
“Thông tin theo bản validation đã ghi nhận.”

Nếu thiếu ảnh:
[Ảnh màn hình workload RGW]
[Ảnh màn hình baseline/verify RBD]

Speaker notes:
Nêu rõ đợt validation này kiểm tra chức năng web, không thực hiện nâng phiên bản Ceph. Baseline/verify hiện tại chưa phải H0-R hoặc H0-W.

Phần chọn OSD/PG, kiểm tra capability của các peer và điều phối H0 là phạm vi mở rộng. Việc RGW GET thành công hoặc đếm đủ byte cũng cần phân biệt với việc đối chiếu nội dung.

Footer: 5/13.

**Prompt slide 5 — Lộ trình phiên bản và cách tổ chức nâng**

Tạo slide nội dung 5, tiêu đề:
“Lộ trình phiên bản và cách tổ chức nâng”

Bố cục:
Một bảng ba chặng ở trung tâm, phía dưới là điều kiện hoàn tất chặng.

Bảng:

- U1: 16.2.5 lên 16.2.15
  Loại: bản vá trong Pacific.
- U2: 16.2.15 lên 17.2.7
  Loại: đổi major từ Pacific sang Quincy.
- U3: 17.2.7 lên 18.2.7
  Loại: đổi major từ Quincy sang Reef.

Thông tin bổ sung:

- Cách tổ chức: rolling upgrade, chia đợt để kiểm chứng.
- Pha OSD: áp dụng PA1 và canary theo scope.
- Sau mỗi chặng: nghiệm thu toàn cluster trước khi sang chặng tiếp theo.

Điều kiện qua chặng:
“Phiên bản đúng, dịch vụ hoạt động, dữ liệu và QoS đạt tiêu chí.”

Ghi chú:
“Các phiên bản trên là mốc thực nghiệm của lab. Đích production cần đánh giá riêng theo hỗ trợ và tương thích.”

Speaker notes:
Phân biệt patch/major là loại thay đổi phiên bản, còn rolling/chia đợt là cách tổ chức thực hiện.

Mỗi chặng bao gồm các daemon thuộc inventory và các kiểm tra riêng của release. Không mô tả việc đưa riêng một OSD xuyên nhiều major khi cluster chưa hoàn tất chặng trước.

Kiểm tra trước các yêu cầu về image, backend lưu trữ, client và feature flags. Việc bật điều kiện tương thích mới phải theo đúng thời điểm của từng release.

Footer: 6/13.

**Prompt slide 6 — Thứ tự nâng daemon bằng cephadm**

Tạo slide nội dung 6, tiêu đề:
“Thứ tự nâng daemon bằng cephadm”

Bố cục:
Một bảng theo thứ tự. Tô nhấn hàng OSD để nối sang PA1.

Bảng:

- Preflight: inventory, health, baseline.
- MGR: bộ điều phối cephadm, standby và failover.
- MON: giữ quorum khi nâng lần lượt.
- crash: tiếp tục theo thứ tự công cụ.
- OSD: kiểm placement, availability và áp dụng PA1.
- MDS nếu có, RGW và dịch vụ còn lại: theo inventory.

Dòng nhấn:
“Xuất phát từ 16.2.5 cần xử lý bước MGR trước khi dùng các tùy chọn staggered có từ 16.2.11.”

Speaker notes:
Ghi thứ tự đầy đủ:
mgr, mon, crash, osd, mds, rgw, rbd-mirror, cephfs-mirror, iscsi, nfs.

Giải thích đây là thứ tự cephadm thực thi. Với bản cũ chưa hỗ trợ staggered, tài liệu hướng dẫn nâng standby MGR, failover và hoàn tất nhóm MGR trước.

Monitoring stack có thể được refresh sau MGR trong staggered upgrade. Tham số limit giới hạn số daemon trong lượt nâng, không biểu thị mức song song.

Nguồn trong notes:
https://docs.ceph.com/en/pacific/cephadm/upgrade/

Footer: 7/13.

Thứ tự daemon, mốc hỗ trợ staggered và bước chuyển MGR đã được đối chiếu với tài liệu Ceph Pacific. :chatgpt-content-reference{index="0"}

**Prompt slide 7 — PA1 kết hợp H0-R tại pha nâng OSD**

Tạo slide nội dung 7, tiêu đề:
“PA1 kết hợp H0-R tại pha nâng OSD”

Bố cục:
Một sơ đồ quy trình chính, chia thành hai hàng để chữ dễ đọc. Làm nổi bật bước H0-R bằng màu nhấn riêng nhưng vẫn theo mẫu Viettel.

Chú giải:

- X: OSD cần nâng cấp.
- S: spare nhận dữ liệu theo placement đã chọn.
- Y/Z: các peer của PG.
- H0-static: tham chiếu của tập dữ liệu cố định.

Quy trình:

1. Chọn X và các PG phù hợp
   Kiểm health, placement, dung lượng và tải.
2. Lưu tham chiếu của corpus cố định
   Giữ H0-static cùng danh tính và phiên bản dữ liệu trước thay đổi.
3. Chuyển placement từ X sang S
   Ceph thực hiện recovery/backfill.
   X tiếp tục hoạt động trong giai đoạn di chuyển.
4. Nâng X khi đủ điều kiện
   Xác nhận dữ liệu đã chuyển theo kế hoạch và kiểm tra ok-to-stop.
5. Trả một số PG canary về X
   Chờ recovery/backfill hoàn tất và kiểm tra native đạt yêu cầu.
6. H0-R kiểm dữ liệu local trên X
   Đọc đúng phiên bản, so với H0-static.
   Đạt thì mở workload canary và theo dõi trước khi mở rộng.

Ở cạnh bước cuối đặt hai nhánh:

- PASS: tiếp tục canary có H0-W khi X thực sự là primary.
- FAIL hoặc thiếu bằng chứng: dừng mở rộng, giữ log và điều tra.

Dòng nhấn:
“H0-R là điều kiện kiểm chứng sau recovery/backfill trong quy trình PA1.”

Speaker notes:
Giải thích thay đổi mapping làm Ceph di chuyển dữ liệu. Không khẳng định đường copy luôn đi trực tiếp từ X sang S.

H0-R dùng tham chiếu cho dữ liệu cố định. Đọc qua client có thể lấy bản tốt từ OSD khác, vì vậy phải có bằng chứng đọc local trên X để kết luận về bản sao tại X.

Deep-scrub thuộc cơ chế native và thực hiện theo PG. Phần H0 bổ sung là tham chiếu độc lập cùng điều kiện cho phép tiếp tục thử nghiệm.

Controller có thể giữ workload canary chưa chạy. Nếu muốn chặn mọi writer trên PG thì cần cơ chế admission trong OSD. primary-affinity không tự bảo đảm tuyệt đối vai trò primary.

Nếu X lỗi trong lúc dữ liệu còn được phục vụ trên S và peer, giữ placement đó để xử lý X. Sau khi trả dữ liệu về X, S không mặc nhiên còn là bản dữ liệu cập nhật để phục hồi.

Footer: 8/13.

**Prompt slide 8 — Luồng ghi dữ liệu và các điểm H0-W**

Tạo slide nội dung 8, tiêu đề:
“Luồng ghi dữ liệu và các điểm H0-W”

Bố cục:
Dành phần lớn slide cho sơ đồ phân nhánh. Dùng nhãn A–E để phân biệt các điểm H0.
Các bước native dùng màu trung tính, các điểm H0 dùng màu nhấn.
Ghi rõ: “Thiết kế đề xuất, minh họa mức 3”.

Bối cảnh:
X là primary vừa nâng cấp.
Y và Z là hai replica.
Ứng dụng đi qua RGW, RBD hoặc librados để tạo thao tác RADOS.

Sơ đồ cần thể hiện các quan hệ sau:

A. Client tạo payload và Hclient
Hclient = SHA256(payload).
Client xác định PG/primary rồi gửi request qua Messenger.

Primary X nhận và xử lý write.

B. Kiểm buffer cuối tại X
So với Hclient trước local submit và replication.

Sau B, tách hai nhánh:

- Nhánh local: BlueStore X tạo checksum local và ghi bền.
- Nhánh replication: gửi dữ liệu cùng Hclient gốc tới Y/Z.

C. Kiểm buffer tại từng replica
Mỗi replica so với Hclient gốc trước khi đưa dữ liệu xuống BlueStore.
Sau đó mỗi replica tự tạo checksum local và ghi bền.

D. Đọc lại local sau ghi bền
Thực hiện trên X và từng replica bắt buộc.
So đúng dữ liệu của request với Hclient.

E. Tổng hợp kết quả tại primary
Chỉ trả SUCCESS khi native commit và mọi kiểm tra H0 bắt buộc đều đạt.
Nếu mismatch, thiếu kết quả hoặc hết thời gian chờ thì không trả SUCCESS.

Yêu cầu sơ đồ:

- Nhánh ghi local và nhánh replication xuất phát từ primary, không vẽ thành một chuỗi ghi tuần tự X rồi Y rồi Z.
- Nhãn Y/Z đại diện cho kiểm tra riêng tại từng replica.
- Đặt chú thích: “B/C mismatch thì không tiếp tục nhánh ghi tương ứng”.
- Giữ nhãn trong mỗi nút ngắn. Chi tiết đưa vào notes.

Dòng nhấn:
“Hclient giữ tham chiếu từ trước vùng xử lý đang được kiểm thử.”

Speaker notes:
Mỗi BlueStore tạo checksum cho dữ liệu mà nó nhận để lưu. Trong mô hình lỗi giả định, ABC có thể biến thành AXC trước điểm tạo checksum, khiến AXC vẫn khớp checksum local. H0 đối chiếu với Hclient ban đầu để kiểm tra trường hợp này.

Điểm B phải nằm sau phần xử lý cần kiểm thử. Kiểm ngay lúc nhận request chưa bao phủ lỗi xuất hiện ở các bước sau.

Hclient phải gắn với đúng object, request và vùng dữ liệu. Không cho primary tự thay tham chiếu bằng hash của dữ liệu đã xử lý.

MVP dùng thao tác ghi toàn bộ object RADOS mới. RGW/RBD cần ánh xạ payload, object và range trước khi mở rộng.

op_commit biểu thị commit tại primary. Cần xét thông báo commit từ replica và kết quả phản hồi riêng. commit_sent chỉ cho biết đã gửi phản hồi.

Nguồn trong notes:
https://docs.ceph.com/en/quincy/rados/configuration/bluestore-config-ref/
https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-osd/

Footer: 9/13.

Cách mô tả checksum local và các sự kiện commit giữ đúng phạm vi của cơ chế native; các điểm A–E là phần thiết kế H0 bổ sung. :chatgpt-content-reference{index="1"}

**Prompt slide 9 — Ba mức H0-W có thể lựa chọn**

Tạo slide nội dung 9, tiêu đề:
“Ba mức H0-W có thể lựa chọn”

Bố cục:
Một bảng so sánh ba hàng, sử dụng cùng nhãn A–E của slide trước.
Phía dưới bảng đặt một ghi chú ngắn về điều kiện triển khai.

Bảng gồm các cột:
“Mức”, “Điểm kiểm”, “Điều kiện trước SUCCESS”, “Đánh đổi”.

Hàng 1:

- Mức 1: Primary buffer.
- Điểm kiểm: A + B + E.
- Điều kiện: buffer cuối tại primary khớp Hclient.
- Đánh đổi: phạm vi hẹp nhất, chưa kiểm chứng sai lệch xuất hiện sau B.

Hàng 2:

- Mức 2: Primary và replica buffer.
- Điểm kiểm: A + B + C + E.
- Điều kiện: primary và mọi replica bắt buộc đều xác nhận buffer khớp.
- Đánh đổi: thêm kiểm tra tại peer, chưa đọc lại dữ liệu sau ghi.

Hàng 3:

- Mức 3: Đọc lại sau ghi bền.
- Điểm kiểm: A + B + C + D + E.
- Điều kiện: dữ liệu đọc lại local trên primary và các replica bắt buộc khớp Hclient.
- Đánh đổi: thêm I/O đọc và độ trễ trước success.

Dòng điều kiện:
“Mức 2–3 yêu cầu peer hỗ trợ. Thiếu capability thì báo không đủ điều kiện, không tự hạ mức.”

Ghi chú:
“H0-R là gate của PA1. Ba mức trên thuộc H0-W.”

Speaker notes:
Các mức có tính cộng dồn. Mức 2 giữ kiểm tra primary của mức 1. Mức 3 giữ kiểm tra buffer và bổ sung đọc lại.

Một OSD canary có thể nằm trong pool replica 3. Số OSD nâng cấp không đồng nghĩa số bản sao dữ liệu. Pool size 1 không kiểm chứng được nhánh replica.

Mức 3 cần chứng minh đọc đúng bản local, đúng version/range và xác định ảnh hưởng của cache. Một GET thông thường chưa đủ để tuyên bố đã kiểm tra dữ liệu trên thiết bị lưu trữ.

H0-W không bảo đảm dữ liệu sẽ không hỏng sau khi hoàn tất kiểm tra.

Không trả success không đồng nghĩa chưa ghi dữ liệu. Đặc biệt mức 3 kiểm tra sau commit, nên thiết kế cần xử lý retry, failover và trạng thái request để tránh báo thành công cho một thao tác chưa hoàn tất kiểm chứng.

Footer: 10/13.

**Prompt slide 10 — Web lựa chọn phạm vi canary và mức H0**

Tạo slide nội dung 10, tiêu đề:
“Web lựa chọn phạm vi canary và mức H0”

Bố cục:
Bên trái là sơ đồ cấu hình phiên kiểm thử.
Bên phải là bảng số OSD và replica của pool test riêng.
Gắn nhãn rõ: “Chức năng đề xuất”.

Các thông tin cấu hình cần thể hiện:

- OSD cần kiểm thử.
- Pool, PG và tập dữ liệu.
- Số bản sao của pool test.
- Bật kiểm tra H0-R khi trả dữ liệu về X.
- Chọn H0-W mức 1, 2 hoặc 3.
- Giới hạn workload, thời gian chạy và điều kiện dừng.

Bảng cho pool test chỉ sử dụng tập OSD đã chọn:

- 1 OSD: size 1.
- 2 OSD: size 2.
- 3 OSD: size 3.
- 4 OSD: size 3.
- 5 OSD: size 3.

Ghi dưới bảng:
“size đề xuất = min(N, 3), với điều kiện placement và failure domain hợp lệ.”

Phần kết quả cần có:

- PG và acting set thực tế.
- OSD nào làm primary hoặc replica.
- Capability của peer.
- Số object/byte đã kiểm.
- PASS, FAIL hoặc chưa đủ bằng chứng.
- Chi phí latency và I/O.

Speaker notes:
Bảng replica chỉ áp dụng cho pool test riêng, không tự giảm size của pool production.

Với pool test size 1, bài thử không có dư thừa dữ liệu và không chứng minh khả năng phục vụ khi OSD đó dừng.

Khi chọn bốn hoặc năm OSD nhưng size ba, mỗi object chỉ có ba bản sao. Phải phân bố đủ PG/object và kiểm tra mapping để biết các OSD đã chọn có thực sự tham gia hay không.

CRUSH rule và failure domain có thể khiến placement không hợp lệ dù đủ số OSD. Web phải kiểm tra điều này.

Phân biệt kiểm thử trong một pool riêng với kiểm thử một OSD mới nâng đang tham gia pool replica ba hiện có. Số OSD nâng cấp và số bản sao là hai lựa chọn riêng.

Footer: 11/13.

**Prompt slide 11 — Kế hoạch đánh giá và diễn tập lỗi**

Tạo slide nội dung 11, tiêu đề:
“Kế hoạch đánh giá và diễn tập lỗi”

Bố cục:
Một bảng “Kịch bản” và “Bằng chứng cần thu”.
Bên dưới là một dòng cấu hình đối chứng.
Gắn nhãn: “Kế hoạch kiểm thử, chưa có kết quả H0”.

Các hàng trong bảng:

1. Recovery/backfill về X
   Kiểm local X, đúng version và H0-static.
2. Sai lệch trước điểm B
   Kiểm khả năng phát hiện tại primary.
3. Sai lệch sau B, trước C
   So sánh phạm vi phát hiện của mức 1 và mức 2.
4. Sai lệch sau kiểm buffer
   Đánh giá kiểm tra đọc lại của mức 3 tại vị trí tiêm lỗi đã xác định.
5. OSD lỗi, timeout hoặc retry
   Kiểm kết quả request, trạng thái commit và hành vi khi chạy lại.
6. Phục hồi dịch vụ và dữ liệu
   Kiểm khả năng giữ placement đang phục vụ và restore từ nguồn tốt.

Dòng cấu hình đối chứng:
“Workload cơ sở / Workload + PA1 / Workload + H0 / Workload + PA1 + H0”

Nhóm số đo:

- Khả năng phát hiện và lỗi báo nhầm.
- p95/p99, throughput, CPU, disk và network.
- Thời gian migration và thời gian kiểm chứng.
- Gián đoạn dịch vụ, RTO/RPO và phạm vi phục hồi.

Speaker notes:
Các lượt so sánh phải giữ workload, corpus, topology và cấu hình native tương đương. Với lượt có H0, ghi rõ mức 1, 2 hay 3.

Fault injection phải nêu vị trí và thời điểm. Một lần overwrite hợp lệ làm dữ liệu khác baseline chưa chứng minh BlueStore bỏ lọt lỗi vật lý.

Duy trì native checksum và scrub trong các lượt. Ghi nhận cả lỗi native phát hiện và phần H0 bổ sung, không mặc định native sẽ bỏ sót mọi kịch bản.

Nếu X không khởi động và dữ liệu vẫn được phục vụ trên S/peer, có thể giữ placement đó. Nếu cần khôi phục dữ liệu thì phải có nguồn tốt đúng phiên bản hoặc backup.

Dừng nâng, giữ dịch vụ, restore dữ liệu và downgrade là các hành động khác nhau. Chỉ đặt ngưỡng nghiệm thu trước run, không điền số kết quả giả.

Footer: 12/13.

**Prompt slide 12 — Lộ trình triển khai và tiêu chí nghiệm thu**

Tạo slide nội dung 12, tiêu đề:
“Lộ trình triển khai và tiêu chí nghiệm thu”

Bố cục:
Một bảng bốn giai đoạn, mỗi giai đoạn có đầu ra rõ ràng.
Phía dưới là tiêu chí quyết định tiếp tục phát triển H0.

Giai đoạn 1: Xác nhận hiện trạng

- Chụp inventory mới.
- Kiểm version/image, quorum, PG và các override.
- Hoàn thiện các bước còn thiếu trong chặng U1.

Giai đoạn 2: Hoàn thiện PA1

- Làm rõ gate trước di chuyển, trước stop và khi trả PG.
- Chọn PG canary theo tải và placement.
- Đo chi phí migration hai chiều.
- Diễn tập giữ dịch vụ khi X lỗi.

Giai đoạn 3: Prototype H0

- Corpus RADOS cố định cho H0-R.
- Ghi toàn bộ object mới cho H0-W.
- Triển khai lần lượt mức 1, mức 2, mức 3.
- Kiểm retry, timeout, failover và bằng chứng đọc local.

Giai đoạn 4: Tích hợp và đánh giá

- Web chọn scope và mức H0.
- Chạy đối chứng, fault injection và restore.
- Nghiệm thu từng chặng trước khi thực hiện U2/U3.

Tiêu chí quyết định:
“H0 cần chứng minh giá trị phát hiện hoặc kiểm soát bổ sung với chi phí chấp nhận được.”

Speaker notes:
Ưu tiên hoàn thiện quy trình native và PA1 có thể thực hiện lại. Phát triển H0 theo từng mức giúp xác định chính xác lợi ích và độ phức tạp tăng thêm.

MVP giới hạn ở corpus và thao tác RADOS dễ kiểm chứng. Tích hợp RGW/RBD đầy đủ thực hiện sau khi làm rõ quan hệ giữa payload ứng dụng và dữ liệu RADOS.

Chỉ mở rộng nhiều OSD đồng thời sau khi đã đo tài nguyên và kiểm tra an toàn của cả nhóm. Tham số limit không thay thế bộ điều phối nâng song song.

Đầu ra bàn giao gồm quy trình nâng, tiêu chí dừng, phương án phục hồi và bộ bằng chứng từng run. Quyết định áp dụng H0 dựa trên số đo, chưa mặc định H0 là điều kiện bắt buộc để Ceph nâng cấp an toàn.

Footer: 13/13.
