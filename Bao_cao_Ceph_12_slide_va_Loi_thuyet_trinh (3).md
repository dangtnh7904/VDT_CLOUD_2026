# Báo cáo nghiên cứu nâng cấp Ceph — nội dung 12 slide và lời thuyết trình

**Ngày cập nhật:** 28/09/2026 · **Bản hiệu chỉnh:** 1.2  
**Mạch báo cáo:** kết quả đã làm → quy trình nâng toàn cluster → PA1 ở pha OSD → H0 trước/sau nâng → web canary và kế hoạch kiểm chứng.  
**Repo đã đối chiếu:** `dangtnh7904/VDT_CLOUD_2026`, commit `9180375b279caf31943abb81541151868c4879ab`.  
**Thời lượng dự kiến:** khoảng 17 phút, chưa tính hỏi đáp.

Đây là nội dung để dựng **đúng 12 slide**. Mỗi slide có chữ đưa lên màn hình, gợi ý minh chứng và lời nói hoàn chỉnh. Phụ lục dùng chuẩn bị hỏi đáp, không tính thêm slide.

**Hiện trạng phải giữ đúng khi trình bày:** đã có nghiên cứu, các bài checksum và web kiểm thử; đã nâng thử một OSD trước MON/MGR theo xác nhận của người thực hiện. Chưa hoàn thành nâng toàn cluster và **chưa triển khai H0**.

H0 trong bản này là thiết kế lưu tham chiếu độc lập trước thay đổi và đối chiếu tại checkpoint của quy trình nâng. Không còn yêu cầu MVP sửa hook read/send/receive trong OSD như bản 1.1. Việc đổi thiết kế không biến các checksum lịch sử thành kết quả H0.

## Cấu trúc tổng thể

| Slide | Tiêu đề | Vai trò | Thời gian |
|---:|---|---|---:|
| 1 | Kết quả tháng đầu và mục tiêu tiếp theo | Nêu đúng phần đã làm và phần đề xuất | 45 giây |
| 2 | Bài toán và nền tảng nghiên cứu | Gắn quy mô, yêu cầu với công việc nghiên cứu | 75 giây |
| 3 | Lab hiện tại mới kiểm thử một OSD | Làm rõ bằng chứng và khoảng trống quy trình | 75 giây |
| 4 | Web hiện có hỗ trợ kiểm thử RBD/RGW | Trình bày sản phẩm và kết quả thật | 75 giây |
| 5 | Ba chặng nâng cấp: patch rồi major | Trả lời từ phiên bản nào đến phiên bản nào | 90 giây |
| 6 | Thứ tự daemon theo cephadm và lý do | Trả lời nâng loại nào trước, vì sao | 120 giây |
| 7 | PA1 nằm trong pha nâng OSD | Giải thích chuyển dữ liệu qua spare | 90 giây |
| 8 | H0 đối chiếu trạng thái trước/sau | Sửa lập luận checksum và chốt phạm vi | 90 giây |
| 9 | H0 gắn với các checkpoint PA1 | Làm rõ cách kết hợp và điều kiện mở rộng | 90 giây |
| 10 | Web chọn OSD, replica và coverage | Chốt phạm vi canary N=1–5 | 75 giây |
| 11 | Đánh giá dữ liệu, dịch vụ, QoS và phục hồi | Đặt tiêu chí kiểm chứng giá trị | 90 giây |
| 12 | Bước tiếp theo từ trạng thái hiện tại | Chốt thứ tự thực hiện và đầu ra | 105 giây |

**Thiết kế slide:** một bảng/hình chính mỗi slide; chữ ngắn, phần giải thích đặt trong notes. Dùng ảnh thật của repo/lab, ghi ngày và scope. Không tạo biểu đồ hiệu năng hoặc ảnh H0 PASS khi chưa có số đo. Footer dự kiến: **[Đơn vị/nhóm] | Nghiên cứu nâng cấp Ceph | [Họ tên] | n/12**.

---

## Slide 1 — Kết quả tháng đầu và mục tiêu tiếp theo

**Ý chính:** đã có nền tảng nghiên cứu và thử nghiệm; bước tiếp theo là hoàn thiện quy trình nâng toàn cluster có kiểm chứng.

### Chữ đưa lên slide

**Nghiên cứu nâng cấp Ceph và công cụ kiểm thử**

- **Nghiên cứu:** kiến trúc Ceph, RBD/RGW, thay đổi phiên bản.
- **Lab:** thử PA1 và nâng một OSD; kiểm toàn vẹn qua checksum.
- **Web:** hỗ trợ bài thử RBD/RGW và thu bằng chứng.
- **Đề xuất:** quy trình toàn cluster + PA1 + H0 theo checkpoint.

**H0 chưa triển khai; một OSD đã nâng không đồng nghĩa cluster đã nâng xong.**

### Bố cục và minh chứng

Ba khối Nghiên cứu — Lab — Web; một hàng hướng phát triển bên dưới. Dùng ảnh web thật, không đưa wireframe chọn OSD vào nhóm tính năng đã hoàn thành.

### Lời thuyết trình

Em xin trình bày kết quả nghiên cứu và thực hành tháng đầu về nâng cấp Ceph. Công việc hiện có gồm tìm hiểu kiến trúc và dịch vụ RBD, RGW; phân tích thay đổi phiên bản; thực hành trên lab; và xây dựng một công cụ web hỗ trợ kiểm thử.

Phần lab đã thử nâng một OSD và dùng checksum để kiểm tra dữ liệu. Em xin xác định rõ đây mới là thử nghiệm ở pha OSD, chưa phải hoàn thành nâng cấp toàn cluster. Các checksum đã chạy cũng chỉ là kết quả kiểm toàn vẹn, chưa có feature H0.

Hướng tiếp theo là đặt PA1 vào một quy trình đầy đủ theo từng loại daemon, rồi bổ sung thiết kế H0 để đối chiếu dữ liệu trước và sau các mốc quan trọng. Báo cáo sẽ tách rõ phần đã có bằng chứng và phần còn cần triển khai.

### Câu chuyển

Trước hết, em trình bày bài toán vận hành và những nghiên cứu đã làm để xây dựng quy trình.

---

## Slide 2 — Bài toán và nền tảng nghiên cứu

**Ý chính:** nghiên cứu phải chuyển thành yêu cầu và bài thử cụ thể cho nâng cấp.

### Chữ đưa lên slide

| Bài toán | Công việc đã làm |
|---|---|
| Dữ liệu RBD/RGW, recovery và placement | Nghiên cứu MON/MGR, OSD, PG, CRUSH và luồng I/O |
| Thay đổi Pacific 16.2.5 → 16.2.15 | Inventory **2.665 file thay đổi**, báo cáo theo **15 nhóm** |
| Nâng cấp có ảnh hưởng dịch vụ | Xây dựng checklist, MOP và bài thử lab |

**Bốn tiêu chí:** toàn vẹn dữ liệu — availability — QoS — phục hồi.

### Bố cục và minh chứng

Ảnh cây thư mục comparison hoặc mục lục báo cáo [G1]; nhấn ba nhóm OSD/BlueStore, RBD, RGW. Đưa quy mô production vào notes nếu chưa có inventory xác nhận.

### Lời thuyết trình

Em bắt đầu từ cách Ceph phân phối dữ liệu: object được ánh xạ vào PG, CRUSH quyết định tập OSD, và các replica phối hợp để ghi, đọc, phục hồi. Đây là cơ sở để hiểu tác động của việc đưa một OSD ra bảo trì và chuyển dữ liệu qua spare.

Trong repo, phần so sánh 16.2.5 với 16.2.15 có inventory hai nghìn sáu trăm sáu mươi lăm file thay đổi và báo cáo theo mười lăm nhóm thành phần. Đây là quy mô thay đổi mã nguồn, không phải số lỗi hoặc phần trăm rủi ro. Giá trị của nghiên cứu là chọn các điểm cần kiểm trong MOP và lab.

Với phạm vi production đã trao đổi khoảng một nghìn sáu trăm OSD, hai mươi bốn petabyte và backup khoảng một trăm terabyte, cần xác nhận lại inventory và xác định dữ liệu ưu tiên. Không thể coi backup này mặc nhiên bao phủ toàn hệ thống.

Vì vậy, đánh giá nâng cấp cần đồng thời xét dữ liệu, khả năng phục vụ, ảnh hưởng hiệu năng và cách phục hồi khi lỗi; chỉ nhìn cluster HEALTH_OK hoặc checksum vài mẫu là chưa đủ.

### Ghi chú người trình bày

- Quy mô production là đầu vào đã trao đổi, không phải số đo lấy từ lab.
- Inventory file/nhóm là thông tin trong hồ sơ nguồn; không tuyên bố vừa chạy lại phân tích toàn mã Ceph.
- Đích production phải xét vòng đời hỗ trợ hiện tại; ba chặng lab sẽ được nói rõ ở slide 5.

### Câu chuyển

Từ cơ sở nghiên cứu này, em đưa một phần quy trình lên lab; kết quả hiện có và giới hạn của nó như sau.

---

## Slide 3 — Lab hiện tại mới kiểm thử một OSD

**Ý chính:** bài nâng một OSD là bằng chứng cho thử nghiệm pha OSD, chưa phải bằng chứng nâng toàn cluster.

### Chữ đưa lên slide

| Mốc | Kết quả / trạng thái |
|---|---|
| Prelab ngày 23/09 | 3 MON, 4 OSD, 233 PG `active+clean` |
| Bài nâng thử được báo cáo | Một OSD: **16.2.5 → 16.2.15**; **16/16** mẫu khớp checksum |
| Trình tự đã làm | Nâng OSD trước MON/MGR |
| Phần cần bổ sung | Inventory hiện tại và quy trình đầy đủ MGR → MON → các pha còn lại |

**16/16 là checksum test, không phải H0; trạng thái hiện tại cần log mới.**

### Bố cục và minh chứng

Đặt log prelab [G2], log version của OSD và kết quả checksum cùng thời điểm nếu có. Log spare weight 0 [G3] chỉ chứng minh bước chuẩn bị; không dùng làm bằng chứng đã chuyển PG hoặc S là primary.

### Lời thuyết trình

Log prelab ngày 23 tháng 9 ghi nhận ba MON, bốn OSD và hai trăm ba mươi ba PG active clean. Đây là trạng thái tại mốc thu log, không phải trạng thái cluster tại thời điểm trình bày.

Trong báo cáo thực hành có kết quả nâng một OSD từ 16.2.5 lên 16.2.15 và mười sáu trên mười sáu mẫu khớp checksum. Khi đưa lên slide chính thức, kết quả này cần đi kèm log version, corpus và thời điểm kiểm để xác định chính xác phạm vi đã đạt.

Điểm cần sửa trong quy trình là OSD đã được nâng trước MON và MGR. Em xem phần đó là thử nghiệm riêng cho pha OSD. Nó chưa chứng minh rằng quy trình nâng toàn cluster đã đúng thứ tự hoặc các dịch vụ khác đã được nâng.

Bước tiếp theo là lấy inventory mới, xác định daemon nào đang ở bản nào, rồi hoàn thành các pha còn thiếu. Không cần mặc định hạ OSD đã nâng hoặc nâng lặp lại chỉ để làm lại sơ đồ; quyết định phải theo trạng thái thực tế và khả năng tương thích.

### Ghi chú người trình bày

- Kết quả 16/16 được ghi trong tài liệu nguồn [G4]; không gán nó cho feature H0.
- Không nói “nâng OSD trước đã được chứng minh an toàn”. Bài thử có giá trị nhưng không thay quy trình cephadm.
- Nếu chưa có log sau nâng đủ rõ, dùng nhãn **kết quả lab được báo cáo**.

### Câu chuyển

Song song với lab, em xây dựng web để việc chạy bài thử và thu bằng chứng được thuận tiện hơn.

---

## Slide 4 — Web hiện có hỗ trợ kiểm thử RBD/RGW

**Ý chính:** web đã có nền kiểm thử; chọn OSD và H0 là các phần mở rộng.

### Chữ đưa lên slide

- **RGW:** quản lý và chạy workload, pause/resume/stop, telemetry.
- **RBD:** lifecycle, file browser/terminal, baseline và verify file.
- **Validation 24/09:** 73 backend + 14 Node + 4 frontend tests.
- **Bài RBD live:** 4 file baseline → phát hiện overwrite → PASS sau phục hồi.

**Lần validation này không nâng phiên bản Ceph. H0 và chọn OSD đầy đủ chưa triển khai.**

### Bố cục và minh chứng

Hai ảnh thật: màn hình workload và baseline/verify. Chú thích ngày, tên run và phạm vi. Dùng VALIDATION [G6], API [G7] và script checksum [G8] để giải thích chức năng.

### Lời thuyết trình

Web hiện có hỗ trợ hai hướng thử nghiệm. Với RGW, công cụ quản lý bài workload, theo dõi trạng thái và cho phép pause, resume hoặc stop. Với RBD, công cụ có các thao tác lifecycle, duyệt file, terminal và kiểm baseline của file.

VALIDATION ngày 24 tháng 9 ghi nhận bảy mươi ba test backend, mười bốn test Node và bốn test frontend. Bài RBD live tạo baseline bốn file, phát hiện nội dung bị overwrite và kiểm lại đạt sau phục hồi. Đây là số liệu lịch sử được ghi trong repo, không phải số test vừa chạy lại khi soạn báo cáo.

Các kết quả này chứng minh nền tảng kiểm thử đã có một số chức năng. Tuy nhiên, bài validation đó không đổi phiên bản Ceph, và checksum hiện có chưa phải feature H0. Worker GET của RGW cũng cần bổ sung kiểm nội dung cho bài verify, thay vì chỉ đọc và đếm byte.

Phần phát triển tiếp là gắn bài thử với đúng tập OSD, đúng version dữ liệu và từng checkpoint của quy trình nâng cấp.

### Ghi chú người trình bày

- Capacity guard được ghi nhận ở OBSERVE_ONLY; mẫu performance còn stale tại lần validation. Chưa dùng làm bằng chứng QoS đạt SLO.
- Không trình bày wireframe OSD selector như ảnh chức năng đã chạy.

### Câu chuyển

Để gắn công cụ vào quy trình, trước tiên phải chốt rõ các chặng phiên bản cần nâng.

---

## Slide 5 — Ba chặng nâng cấp: patch rồi major

**Ý chính:** nâng xong và nghiệm thu toàn cluster ở mỗi chặng trước khi sang chặng sau.

### Chữ đưa lên slide

| Chặng lab | Từ → đến | Loại |
|---|---|---|
| U1 | 16.2.5 → 16.2.15 | Patch, cùng Pacific |
| U2 | 16.2.15 → 17.2.7 | Major, Pacific → Quincy |
| U3 | 17.2.7 → 18.2.7 | Major, Quincy → Reef |

**Cách thực hiện:** rolling bằng cephadm, chia đợt để kiểm chứng.  
**Qua chặng:** daemon đúng bản + dịch vụ/dữ liệu/QoS đạt.  
**Các mốc trên dành cho lab; đích production cần chọn lại theo hỗ trợ hiện tại.**

### Bố cục và minh chứng

Ba hàng cùng một cột gate hoàn tất. Không vẽ một OSD đi xuyên ba major trong khi phần còn lại giữ nguyên. Nguồn release/upgrade [C1][C9][C10][C11].

### Lời thuyết trình

Lộ trình lab gồm ba chặng. Đầu tiên là nâng bản vá trong Pacific từ 16.2.5 lên 16.2.15. Sau đó là hai lần đổi major: sang Quincy 17.2.7 rồi Reef 18.2.7.

Đây là hai cách phân loại khác nhau: patch hay major nói về mức thay đổi phiên bản; rolling và staggered nói về cách tổ chức nâng. Em đề xuất dùng rolling upgrade của cephadm, chia thành các đợt theo loại daemon và phạm vi để kiểm tra trước khi tiếp tục.

Mỗi chặng phải hoàn thành trên toàn cluster theo inventory, sau đó kiểm dịch vụ, dữ liệu, hiệu năng và các điều kiện riêng của release. Em không đưa một OSD lên major tiếp theo khi cluster chưa nghiệm thu xong chặng hiện tại. Cách này giúp tách biến số và xác định lỗi xuất hiện ở chặng nào.

Các version trên được giữ làm mốc thực nghiệm. Tại thời điểm cập nhật tài liệu, cả Pacific, Quincy và Reef đều đã hết hỗ trợ upstream, nên không dùng lộ trình lab làm khuyến nghị production nguyên xi. Đích triển khai thực tế cần được chọn lại theo hỗ trợ, bản vá, image và tương thích client.

### Ghi chú người trình bày

- Trước Quincy cần kiểm store backend, trong đó có yêu cầu loại bỏ LevelDB. Không khẳng định cluster đang dùng LevelDB nếu chưa inventory.
- Sau major, kiểm release floor/feature flags đúng thời điểm, không chặn OSD cũ trước khi nâng xong.
- Tài liệu Reef hiện không khuyến nghị nâng trực tiếp Pacific → Reef; chọn đi qua Quincy phù hợp cách chia chặng này. [C11]
- `--limit` là giới hạn số daemon được xử lý, không phải mức song song.

### Câu chuyển

Trong mỗi chặng, thứ tự nâng theo loại daemon được tổ chức như sau.

---

## Slide 6 — Thứ tự daemon theo cephadm và lý do

**Ý chính:** nâng bộ điều phối và control plane trước, rồi xử lý storage cùng các dịch vụ theo thứ tự công cụ hỗ trợ.

### Chữ đưa lên slide

| Thứ tự | Thành phần | Điểm cần giữ |
|---:|---|---|
| 0 | Preflight và baseline | Biết điểm xuất phát, nguồn dữ liệu tham chiếu |
| 1 | MGR | Standby khỏe, failover, orchestration hoạt động |
| 2 | MON | Nâng theo lượt, giữ quorum |
| 3 | crash | Theo thứ tự cephadm, duy trì thu sự cố |
| 4 | OSD — áp dụng PA1 | Replica, placement, dữ liệu và QoS |
| 5 | MDS nếu có → RGW → dịch vụ còn lại | Kiểm đúng dịch vụ trong inventory |

**16.2.5:** cần bước MGR trước để dùng staggered options từ 16.2.11.  
**Cuối mỗi chặng:** kiểm toàn cluster trước khi đi tiếp.

### Bố cục và minh chứng

Bảng thứ tự với hàng OSD được tô nhấn. Ghi footer “Thứ tự cho cephadm”. Danh sách đủ mười loại daemon nằm trong notes, không ép chữ nhỏ trên slide.

### Lời thuyết trình

Với cluster dùng cephadm, thứ tự bắt đầu bằng MGR rồi MON, tiếp theo là crash và OSD. Nếu có CephFS thì đến MDS, sau đó là RGW và các dịch vụ còn lại. Em chỉ đưa các daemon thực sự đang triển khai vào MOP.

MGR đi trước vì đây là nơi chạy các chức năng quản trị và orchestration; cần bộ điều phối hoạt động đúng trước khi điều khiển các bước tiếp. Cách tổ chức là có standby khỏe, nâng standby, chuyển active sang bản mới rồi hoàn tất MGR còn lại. MON được nâng theo lượt để giữ quorum, vì MON duy trì cluster map và đồng thuận.

Sau các pha đó mới đến OSD. PA1 được đặt ở đây để kiểm soát dịch chuyển dữ liệu và tác động của từng lượt nâng. Việc crash đứng trước OSD là thứ tự của cephadm, không có nghĩa crash là thành phần trên đường ghi dữ liệu.

Điểm riêng của lab là active MGR có thể vẫn ở 16.2.5. Các tùy chọn chia đợt như daemon-types, hosts và limit chỉ có từ 16.2.11 trong Pacific. Vì vậy cần bước chuyển MGR theo hướng dẫn chính thức trước khi dùng chúng; không thể viết một lệnh mới rồi giả định MGR cũ hiểu.

Monitoring được quản lý theo lifecycle của cephadm và cần được theo dõi suốt quá trình. Không đặt mặc định mọi monitoring daemon vào bước nâng cuối cùng.

### Ghi chú người trình bày

- Thứ tự đầy đủ của tài liệu Pacific: `mgr → mon → crash → osd → mds → rgw → rbd-mirror → cephfs-mirror → iscsi → nfs`. [C9]
- Đây là cephadm; hướng dẫn nâng package ngoài cephadm có thể đưa MON trước MGR. Không giải thích như quy luật bắt buộc chung cho mọi cách triển khai. [C10][C11]
- Bước đầu U1 cần nhiều MGR đang chạy, nâng standby bằng image đã xác minh, failover, kiểm active mới rồi hoàn tất nhóm MGR. Thiếu standby thì xử lý trước khi tiếp tục.
- Staggered upgrade có thể refresh monitoring sau MGR; version monitoring không nhất thiết đổi cùng Ceph. [C9]
- RBD không có daemon chung tên “RBD”; rbd-mirror chỉ có nếu đang dùng mirroring. Client librbd/kernel cần ma trận tương thích riêng.
- Nếu có MDS/multisite/gateway bổ sung, áp dụng hướng dẫn riêng của đúng release; không coi bảng này là MOP chi tiết cho mọi dịch vụ.

### Câu chuyển

Sau khi đã đặt đúng vị trí của pha OSD, em trình bày cơ chế PA1 trong pha này.

---

## Slide 7 — PA1 nằm trong pha nâng OSD

**Ý chính:** chuyển dữ liệu hoàn tất trước khi dừng X, kiểm canary trước khi mở rộng trả dữ liệu về.

### Chữ đưa lên slide

| Bước | Hành động | Điều kiện |
|---|---|---|
| 1 | Giữ X online, chuyển PG từ X sang S theo batch | Mapping hợp lệ, đủ bản, QoS đạt |
| 2 | Chờ hội tụ, kiểm an toàn rồi nâng X | Drain đủ scope, `ok-to-stop`, đúng image |
| 3 | Cho một phần dữ liệu về X, chạy canary | Đọc/ghi, dữ liệu, coverage và QoS đạt |
| 4 | Trả phần còn lại và hoàn nguyên override thuộc run | Đủ bằng chứng cuối lượt |

**X:** OSD nâng · **S:** spare · **S không phải backup cố định.**

### Bố cục và minh chứng

Dùng hai ảnh mapping cùng PG: trước X/Y/Z, sau S/Y/Z; thêm bản sau trả về X. Phải ghi epoch và dữ liệu thật nếu dùng bằng chứng lab. Không minh họa S ở weight 0 như thể đã nhận đủ dữ liệu.

### Lời thuyết trình

Trong PA1, X là OSD cần nâng và S là spare. Trình tự đề xuất giữ X online trong khi điều chỉnh placement để chuyển các PG sang S theo từng batch. Em chờ dữ liệu hội tụ, đủ số bản và đạt các gate trước khi dừng X.

Điều này khác với việc dừng X trước rồi mới bắt đầu chuyển. Nếu MOP cũ còn trình tự đó thì phải sửa cho nhất quán với phương án đang đánh giá. Spare cũng phải đủ dung lượng, đúng failure domain và thực sự được chấp nhận trong mapping; có một OSD tên S chưa đủ.

Sau khi X chạy image mới, em đưa một phạm vi nhỏ về X để canary, kiểm cả dữ liệu cũ và ghi đọc mới. Chỉ khi dữ liệu, dịch vụ và QoS đạt mới mở rộng trả PG và hoàn nguyên các override thuộc run.

Nếu X không khởi động nhưng PG còn phục vụ trên S và các peer, có thể giữ chúng ở đó để xử lý X. Tuy nhiên, sau khi dữ liệu đã trả về X, S có thể không còn cập nhật. Vì vậy không gọi S là backup cố định hoặc mặc định có thể copy ngược từ S bất cứ lúc nào.

### Ghi chú người trình bày

- PA1 không thay thứ tự nâng cluster; chỉ áp dụng trong pha OSD của mỗi U.
- Kiểm `ok-to-stop` trên cả tập nếu dừng nhiều OSD. Chọn năm OSD để test không cho phép dừng năm OSD cùng lúc.
- Byte và thời gian phải tính cả chiều X→S và S→X; không chỉ đo restart daemon.
- Log/MOP nguồn [G10] cần reconcile với trình tự mới trước vận hành.

### Câu chuyển

PA1 có các lần chuyển và ghi dữ liệu, nên em đặt thêm câu hỏi: payload sau toàn bộ quy trình có còn giống trạng thái trước đó không?

---

## Slide 8 — H0 đối chiếu trạng thái trước/sau

**Ý chính:** H0 giữ tham chiếu trước thay đổi; đổi binary không mặc định tính lại checksum toàn bộ object.

### Chữ đưa lên slide

| BlueStore checksum | H0 đề xuất |
|---|---|
| Kiểm dữ liệu đọc với checksum đã lưu | Kiểm payload sau nâng với reference trước nâng |
| Gắn với dữ liệu được ghi tại store | Manifest độc lập, đúng version/snapshot |

**Trước:** chốt H0 → **sau checkpoint:** đọc cùng dữ liệu, tính Ht → **so Ht với H0 gốc**.

- Đổi binary không mặc định đọc/hash lại mọi payload.
- PA1 có copy/backfill/ghi lại: cần kiểm kết quả cả workflow.
- **H0 chưa triển khai; MVP không bắt buộc sửa core Ceph.**

### Bố cục và minh chứng

Bảng hai cột và công thức `Ht == H0`. Dùng một ví dụ nhỏ ABC/AXC trong notes, không đặt quá nhiều chi tiết về CRC trên màn hình. Nguồn nền [C2][C12]; thiết kế H0 là đề xuất của đề tài.

### Lời thuyết trình

Em điều chỉnh cách giải thích H0. Việc đổi binary OSD không tự có nghĩa Ceph đọc lại toàn bộ object rồi tính checksum mới. BlueStore tạo checksum cho dữ liệu ghi xuống disk và dùng checksum lưu đó khi đọc từ disk.

Nhưng workflow PA1 có thể khiến dữ liệu được copy hoặc ghi tại OSD đích. Nếu một lỗi logic làm payload thay đổi trước điểm tạo checksum của lần ghi mới, payload sai vẫn có thể đi kèm checksum tự khớp. Đây là mô hình lỗi cần thử, không phải lỗi Ceph đã được chứng minh trong lab.

H0 đặt một tham chiếu độc lập trước quy trình. Sau từng checkpoint, công cụ đọc đúng object version hoặc snapshot range và so với tham chiếu gốc. Khác biệt nằm ở nguồn và thời điểm của reference, không phải chỉ vì dùng SHA-256 thay CRC.

Theo phạm vi mới, em có thể triển khai feature này ở công cụ kiểm thử và controller, chưa cần sửa core OSD. Hiện chưa có implementation H0; checksum cũ vẫn được ghi là kiểm thử toàn vẹn. Đây là lớp bằng chứng bổ sung cho nâng cấp, không phải điều kiện bắt buộc để Ceph vận hành đúng.

### Ghi chú người trình bày

- Nếu baseline lấy sau khi dữ liệu đã sai thì H0 không chứng minh dữ liệu đúng ban đầu.
- H0 theo checkpoint không chặn mỗi I/O và không thay native checksum/scrub/recovery.
- Upmap điều chỉnh placement; backfill/recovery phát sinh sau đó mới thực hiện chuyển/ghi dữ liệu.
- Không quảng bá “checksum mới”. Giá trị đề xuất là reference có quản lý, checkpoint, gate, coverage và truy vết.

### Câu chuyển

Để tham chiếu này có ích, nó phải được gắn vào các mốc cụ thể của PA1 và giữ nguyên trong suốt bài thử.

---

## Slide 9 — H0 gắn với các checkpoint PA1

**Ý chính:** mỗi lần kiểm so với cùng H0, kết quả quyết định có mở rộng bước nâng tiếp hay không.

### Chữ đưa lên slide

| Mốc | Kiểm chứng đề xuất |
|---|---|
| Trước workflow | Chốt corpus, version/snapshot và H0 độc lập |
| Sau X → S | Kiểm dữ liệu bị ảnh hưởng; chưa đạt thì chưa dừng/nâng X |
| Sau canary/trả về X | Kiểm payload cũ và bài ghi/đọc mới có reference riêng |
| Cuối chặng và sau soak | Kiểm đủ scope, giữ toàn bộ attempts |

**MISMATCH/thiếu bằng chứng → dừng mở rộng và điều tra.**  
**Live head đang ghi không được so mù với baseline cũ.**

### Bố cục và minh chứng

Bảng checkpoint, một ô “H0 gốc — giữ nguyên” và các kết quả quan sát tại từng mốc. Không dùng mũi tên thay H0 bằng hash mới sau mỗi bước. Chi tiết G0–G6 ở file feature mục 9.

### Lời thuyết trình

Trước workflow, em chọn corpus và chốt trạng thái dữ liệu. Với S3 có thể dùng key bất biến hoặc version ID cụ thể. Với RBD cần snapshot hoặc cơ chế quiesce phù hợp. Nếu chỉ so cùng tên file nhưng file đang được ứng dụng ghi hợp lệ thì mismatch chưa có nghĩa là corruption.

Sau khi chuyển X sang S, công cụ đọc kiểm corpus liên quan và so với H0 gốc. Nếu sai, thiếu reference hoặc chưa đủ bằng chứng, controller dừng việc mở rộng hoặc chuyển sang bước tiếp để điều tra. Nó không chặn mọi I/O bên trong Ceph.

Sau khi đưa dữ liệu về X, em kiểm lại cùng reference và chạy thêm corpus ghi đọc mới có expected state riêng. Snapshot cũ còn nguyên không đủ chứng minh mọi ghi mới trên phiên bản mới đều đúng.

Cuối chặng, em kiểm đủ scope bắt buộc và lưu mọi attempt. Lần sau PASS không xóa mismatch trước. Đồng thời, H0 MATCH chỉ nói về dữ liệu đã đọc qua đường kiểm đã ghi nhận; nó không tự chứng minh từng replica đều được đọc và hash riêng.

### Ghi chú người trình bày

- Native health/PG/quorum/`ok-to-stop` và SLO vẫn là gate riêng.
- H0 tạo hôm nay không hồi tố chứng minh lần nâng OSD đã diễn ra trước đó.
- Kết quả từng object MATCH khác verdict toàn run PASS; corpus rỗng/coverage thiếu không được PASS.
- Nếu phát hiện lỗi, giữ S/peer theo mapping hiện hành; H0 không chứa payload để restore.

### Câu chuyển

Để biết bằng chứng đó phủ tới đâu, web phải kiểm soát được tập OSD và placement thật của bài canary.

---

## Slide 10 — Web chọn OSD, replica và coverage

**Ý chính:** số replica phụ thuộc số OSD chọn, nhưng kết quả phải gắn với placement và độ bao phủ thực tế.

### Chữ đưa lên slide

**Pool test riêng: `size = min(N, 3)`**

| OSD được chọn | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| Tổng số bản | 1 | 2 | 3 | 3 | 3 |

- Kiểm đủ host/failure domain và PG nằm trong allowlist.
- N=4/5: mỗi PG chỉ có ba bản; phải chứng minh workload phủ đủ OSD.
- N=1: không dự phòng, không dùng để chứng minh chịu lỗi khi chính OSD dừng.
- Phân biệt **tập test**, **OSD nâng** và **tập nguồn/đích PA1**.

### Bố cục và minh chứng

Wireframe đề xuất gồm danh sách OSD/host/version, replica, mapping và bảng coverage. Ghi rõ “thiết kế đề xuất”. Screenshot web hiện có không chứng minh chức năng OSD selector đã hoàn thành.

### Lời thuyết trình

Web sẽ cho chọn một OSD hoặc một tập OSD để kiểm thử. Một OSD thì pool test có một bản, hai OSD thì hai bản, từ ba trở lên thì tối đa ba bản. Công thức này chỉ áp dụng cho replicated pool test riêng, không hạ replica của pool production.

Số lượng OSD chưa đủ quyết định cấu hình hợp lệ. Nếu rule dùng failure domain là host thì phải đủ host khác nhau. Đồng thời, sau hội tụ, PG của pool test phải thật sự nằm trong tập đã chọn; checkbox trên giao diện không phải bằng chứng placement.

Với bốn hoặc năm OSD và size bằng ba, một object chỉ có ba bản. Công cụ cần chọn đủ dữ liệu và PG để các OSD đều có workload, đồng thời báo rõ việc kiểm mới qua client hay đã đọc riêng từng replica.

Có một điểm cần tách: pool chỉ được nằm trên X không thể vừa giữ scope đó vừa chuyển sang S. Bài test một OSD sau nâng là profile riêng. Bài PA1 phải khai báo trước X, S và các peer có thể tham gia để không âm thầm đưa dữ liệu ra ngoài allowlist.

### Ghi chú người trình bày

- `size` tính cả primary. Policy test đề xuất: N=1 dùng 1/1; N=2 dùng 2/2; N≥3 dùng 3/2 cho size/min_size. Một profile size=2/min_size=1 phải ghi riêng.
- Size=1 có guard trong Pacific; không âm thầm sửa default cluster. [C3][C4]
- RGW có data/index/data-extra và pool hệ thống; nếu chỉ payload nằm trong scope, báo đúng là kiểm phạm vi payload. [C5]
- RBD image/snapshot và mapping file→RADOS→PG cần khai báo giới hạn. EC dùng k+m, không theo bảng replica này.

### Câu chuyển

Khi phạm vi đã rõ, em dùng bộ tiêu chí sau để đánh giá PA1 và H0 có đem lại giá trị thực tế hay không.

---

## Slide 11 — Đánh giá dữ liệu, dịch vụ, QoS và phục hồi

**Ý chính:** giá trị của phương án cần được đo trong cả trường hợp bình thường và có lỗi.

### Chữ đưa lên slide

| Nhóm tiêu chí | Bằng chứng |
|---|---|
| Dữ liệu / coverage | Đúng version, đủ byte, đủ scope; giữ mismatch và attempts |
| Availability | Quorum, PG, lỗi/timeout, thời gian gián đoạn |
| QoS / tài nguyên | p95/p99, throughput, CPU/I/O/network; chi phí hai chiều migration và verify |
| Phục hồi / truy vết | X không boot, peer lỗi, restore; RTO/RPO và nguồn dữ liệu tốt |

**Đối chứng:** A workload · B +H0 · C +PA1 · D +PA1+H0.  
**B/D chưa có kết quả vì H0 chưa triển khai.**

### Bố cục và minh chứng

Bảng tiêu chí và bốn cấu hình đối chứng. Chỉ dựng biểu đồ khi có dữ liệu thật và ghi cùng workload/corpus/topology. Trước mắt ghi “kế hoạch đo”.

### Lời thuyết trình

Em không đánh giá phương án chỉ bằng một lần checksum khớp. Với dữ liệu, phải kiểm đúng version và đủ scope. Với dịch vụ, cần biết có mất quorum, PG không phục vụ được hoặc client timeout hay không. Với QoS, cần đo latency, throughput và tài nguyên cả khi chuyển sang S lẫn khi trả về X.

Kế hoạch đối chứng gồm bốn lượt: workload cơ sở; workload có H0; workload có PA1; và kết hợp cả hai. Hai lượt có H0 chỉ thực hiện khi feature đã triển khai. Các checksum test cũ không cung cấp sẵn số đo overhead cho feature mới.

H0 bên ngoài phải đọc và hash dữ liệu, nên chi phí có thể lớn nếu corpus lớn hoặc kiểm quá nhiều lần. Có thể dùng corpus canary đầy đủ và lấy mẫu phạm vi rộng hơn, nhưng phải công bố phần chưa đọc, không tuyên bố toàn cluster đã nguyên vẹn.

Em cũng cần thử X không khởi động, peer lỗi và restore dữ liệu. Giữ dịch vụ trên S, dừng nâng cấp, restore và hạ phiên bản là các hành động khác nhau. Chỉ nên triển khai H0 tiếp nếu nó giúp kiểm chứng hoặc chặn mở rộng đúng mốc với chi phí chấp nhận được.

### Ghi chú người trình bày

- Giữ native checksum/scrub hoạt động trong các lượt. Kiểm soát chi phí script đối chứng và chính sách cache.
- Không gọi một ghi hợp lệ thay payload test là lỗi BlueStore. Bài này kiểm detector khác reference, không chứng minh native checksum bỏ lọt bit rot.
- SLO, soak, RTO/RPO là ngưỡng cần chốt trước run; không điền số kết quả giả.
- Sáu yêu cầu vẫn được giữ trong đánh giá: toàn vẹn; availability; QoS; phạm vi/dung lượng; phục hồi; lặp lại và truy vết.

### Câu chuyển

Từ trạng thái lab hiện tại, em đề xuất thứ tự công việc tiếp theo như sau.

---

## Slide 12 — Bước tiếp theo từ trạng thái hiện tại

**Ý chính:** hoàn thành quy trình cluster và triển khai H0 theo phạm vi đã thu gọn, rồi đánh giá bằng số đo.

### Chữ đưa lên slide

1. **Chụp lại inventory:** version/image từng daemon, quorum, PG, upmap và trạng thái upgrade.
2. **Hoàn thành U1:** MGR → MON → crash → OSD/PA1 → dịch vụ → nghiệm thu.
3. **Phát triển H0 và web scope:** manifest bất biến, checkpoint, gate, attempts, coverage.
4. **Đánh giá kết hợp:** lỗi, QoS, restore; sau đó lặp toàn quy trình cho U2/U3.

**Bàn giao:** MOP từng chặng + bộ kiểm có truy vết + báo cáo bằng chứng.  
**OSD đã đúng target được kiểm lại; không mặc định downgrade hay nâng lặp.**

### Bố cục và minh chứng

Bốn hàng công việc, mỗi hàng có điều kiện hoàn thành. Không đánh dấu toàn bộ PA1, web hoặc H0 là đã xong bằng một dấu tick chung.

### Lời thuyết trình

Bước đầu tiên là lấy lại inventory vì cluster đã có một OSD được nâng trước. Em cần biết version và image thật của từng daemon, active MGR, quorum MON, mapping PG và các override còn lại từ lab.

Nếu xác nhận chỉ một OSD ở 16.2.15 và các thành phần còn lại ở 16.2.5, đồng thời cluster đủ điều kiện, em hoàn thành pha MGR theo cách chuyển standby và failover, sau đó MON, crash và phần OSD còn lại. OSD đã đúng target được kiểm lại, không cần mặc định hạ xuống hoặc nâng lặp. Nếu trạng thái khác, đặc biệt đã có OSD major mới hoặc lỗi health, phải điều chỉnh theo evidence thực tế.

H0 và web chọn scope có thể được phát triển song song ở phía công cụ. Tuy nhiên, chưa có H0 thì các lượt nâng vẫn được báo là PA1 kèm checksum test. Baseline được lập sau lần nâng đầu chỉ có giá trị cho khoảng thời gian từ đó về sau.

Khi feature mới tồn tại và đạt nghiệm thu, em tích hợp vào các gate PA1, đo đối chứng và diễn tập phục hồi. Mỗi chặng phải hoàn tất toàn cluster trước khi sang chặng tiếp. Kết quả bàn giao là quy trình có thể thực hiện lại và bộ bằng chứng cho thấy đã kiểm gì, chưa kiểm gì và xử lý thế nào khi có lỗi.

### Ghi chú người trình bày

- “Phát triển song song” ở đây là tổ chức công việc, không cho phép hai công cụ cùng mutation cluster.
- Không cam kết mốc thời gian triển khai H0 hoặc phần trăm cải thiện khi chưa ước lượng/test.
- Đầu ra tháng đầu vẫn là nghiên cứu, lab một OSD và nền web. Quy trình toàn cluster, OSD selector hoàn chỉnh và H0 là hạng mục tiếp theo.

---

## Phụ lục A — Bản đồ bằng chứng

| Nhận định | Nguồn | Cách ghi đúng |
|---|---|---|
| Nghiên cứu 15 nhóm, 2.665 file | Comparison [G1] | Kết quả hồ sơ nghiên cứu; không phải số lỗi |
| 3 MON, 4 OSD, 233 PG clean | Log prelab [G2] | Trạng thái 23/09, không phải inventory hiện tại |
| Spare ở weight 0 | Log [G3] | Chuẩn bị spare; chưa chứng minh có payload/primary |
| Một OSD 16.2.5→16.2.15, 16/16 checksum | Báo cáo nguồn [G4] và xác nhận người thực hiện | Kết quả lab được báo cáo; cần log gốc, không phải H0 |
| OSD đã nâng trước MON/MGR | Xác nhận mới của người thực hiện | Khoảng trống trình tự phải xử lý, không hợp thức hóa thành flow chuẩn |
| Web baseline/verify và 73/14/4 tests | [G5][G6][G7] | Chức năng/số test lịch sử, chưa chạy lại khi sửa tài liệu |
| Detect overwrite, PASS sau restore | VALIDATION [G6] | Bài kiểm RBD không đổi phiên bản Ceph |
| H0 hoặc hook trong OSD đã chạy | Không có implementation được xác nhận | Không dùng làm kết quả; H0 bản 1.2 là thiết kế mới bên ngoài Ceph |
| Web chọn N OSD với placement riêng | Chưa có planner/provisioner hoàn chỉnh | Hướng mở rộng |
| QoS/restore đạt yêu cầu | Chưa có đủ số đo đối chứng | Kế hoạch kiểm, chưa kết luận |

Phạm vi repo dùng trong báo cáo cố định ở commit đầu file. Bản sửa giữ các bằng chứng đã rà soát và dùng xác nhận mới để sửa tiến độ; không khẳng định đã chạy lại lab hoặc kiểm toàn bộ thay đổi mới hơn trên main.

## Phụ lục B — Câu hỏi và câu trả lời chuẩn bị

### “Tại sao lại MGR trước MON? MON không quan trọng hơn sao?”

Đây là thứ tự cephadm hỗ trợ, không phải xếp hạng mức quan trọng. MGR chạy chức năng quản trị/orchestration nên cần bộ điều phối hoạt động đúng; MON sau đó vẫn phải nâng từng lượt và giữ quorum. Cách nâng package ngoài cephadm có hướng dẫn MON trước MGR, nên phải nói rõ phương thức triển khai. [C9][C10][C11]

### “Ở 16.2.5 thì bắt đầu cụ thể thế nào?”

Chốt inventory và có nhiều MGR khỏe; nâng standby lên image U1, kiểm version, failover sang MGR mới rồi hoàn tất nhóm MGR. Sau khi active MGR có staggered support mới dùng các tham số giới hạn. Chi tiết daemon/image phải lấy từ cluster, không chép tên ví dụ vào lệnh thật. [C9]

### “Đã lỡ nâng một OSD trước rồi có phải làm lại không?”

Không tự làm lại hoặc downgrade. Nếu chỉ một OSD đã ở 16.2.15 và cluster đủ điều kiện, ghi nhận bài canary rồi hoàn tất MGR/MON/crash và các phần còn thiếu của U1. Nếu OSD đã ở major khác hoặc có lỗi, cần phân tích trạng thái thực tế. Không giả định trạng thái hiện tại từ log prelab.

### “Monitoring nâng ở cuối có đúng không?”

Không cố định như vậy. Trong staggered upgrade, cephadm có thể refresh monitoring sau MGR; các image monitoring không mang cùng version Ceph. Metrics được kiểm suốt run và nghiệm thu tổng thể ở cuối chặng. [C9]

### “Nâng daemon có làm Ceph tính lại checksum của mọi object không?”

Không mặc định. Cần tách việc thay binary khỏi các thao tác copy/ghi dữ liệu trong workflow. Dữ liệu ghi mới ở BlueStore có checksum cho lần ghi đó; upmap thay placement có thể dẫn tới backfill/recovery, không tự là lệnh hash lại toàn store. Các thay đổi format/metadata cụ thể vẫn phải đọc theo release. [C2][C8][C12]

### “Các checksum đã chạy có phải H0 không?”

Không. Chúng là kết quả kiểm toàn vẹn đã có. H0 bản 1.2 là feature đề xuất mới với reference bất biến, consistency/version, checkpoint, gate, coverage và lịch sử bằng chứng. Có thể tái sử dụng mã hash, nhưng chỉ sau khi triển khai và nghiệm thu các thành phần đó mới báo feature đã có.

### “H0 có cần sửa Ceph như bản trước không?”

Theo yêu cầu đã điều chỉnh, không bắt buộc. MVP chạy ở công cụ kiểm thử/controller và quyết định có tiếp tục mở rộng quy trình nâng hay không. Hook kiểm trước từng read/send/receive là phạm vi nghiên cứu khác, không còn là điều kiện triển khai bản này.

### “Ceph có checksum rồi, H0 thực sự cần khi nào?”

Khi cần bằng chứng độc lập về trạng thái payload trước/sau toàn workflow và muốn tự động dùng bằng chứng đó ở gate nâng. Tham chiếu trước thay đổi có thể phát hiện khác trạng thái kỳ vọng dù dữ liệu mới ghi tự khớp checksum nội bộ. Đây là giá trị cần thử; H0 không bắt buộc để Ceph nâng đúng, và nếu native checks cùng test hiện có đã đủ mục tiêu thì không cần kiến trúc H0 phức tạp.

### “Replica sai từ trước hoặc sai khi đang chạy thì H0 giải quyết được không?”

H0 qua client có thể đọc một bản tốt khác, nên không tự phát hiện lỗi ở mọi replica. Native checksum/read/scrub có vai trò riêng tùy lỗi và đường thực thi. Muốn kết luận theo từng replica cần bài đọc/kiểm riêng có bằng chứng. H0 bản này chỉ cam kết phạm vi và checkpoint đã quan sát, không tự sửa replica. [C12][C15]

### “Lên primary rồi, sai trước hay sau thời gian hoạt động thì sao?”

Chuyển primary/peering không phải scan H0 toàn dữ liệu. Lần kiểm canary có thể phát hiện payload sai đã đọc; lỗi xuất hiện sau đó chỉ có thể được quan sát ở lần kiểm tiếp theo hoặc qua cơ chế native phù hợp. H0 bên ngoài không chặn mọi lần ứng dụng nhận dữ liệu sai và không chứng minh tất cả byte trên primary đã tốt. [C16]

### “Dữ liệu đang ghi thì so trước/sau thế nào?”

Cố định corpus bằng key bất biến/version ID hoặc snapshot/quiesce. Tách bài bảo toàn dữ liệu cũ khỏi bài ghi mới có reference theo generation. Không so live head đã đổi hợp lệ với baseline cũ rồi kết luận corruption. RBD snapshot không phối hợp ứng dụng chưa tự bảo đảm application consistency. [C6]

### “Một OSD thì replica một có an toàn không?”

Đó là profile chức năng trên pool test riêng, có dữ liệu tái tạo được và không có dự phòng. Khi chính OSD dừng, bài này có thể mất khả năng phục vụ. Không dùng nó để nghiệm thu khả năng chịu lỗi của pool production.

### “Chọn năm OSD nhưng replica ba có kiểm được cả năm không?”

Cần đủ object/PG để từng OSD thực sự tham gia. Size ba không đặt một object trên cả năm OSD. Báo coverage theo mapping/workload và mức đọc kiểm; có mặt trong acting set không đồng nghĩa đã hash riêng bản local.

### “Nếu pool test chỉ ở X thì PA1 chuyển sang S có vi phạm scope không?”

Có, nếu vẫn giữ allowlist chỉ gồm X. Vì vậy profile test X sau nâng và profile PA1 phải tách rõ. Bài PA1 khai báo trước X/S/peer như tập có thể tham gia; không thêm S vào scope âm thầm.

### “Nếu các bản đều sai hoặc X không khởi động thì sao?”

Nếu reference còn đúng, H0 có thể phát hiện khác payload kỳ vọng; muốn sửa phải có bản tốt đúng version hoặc backup/source. Nếu PG hiện còn ở S/peer và đang phục vụ đúng, có thể giữ tại đó để xử lý X. Sau khi đã trả về X, S không mặc nhiên là nguồn cập nhật.

### “Dừng nâng có phải rollback không?”

Không. Dừng orchestrator chỉ ngừng các bước tiếp; giữ PG trên peer, restore dữ liệu và downgrade daemon là những hành động riêng. Quincy/Reef release notes không cung cấp đường downgrade về major trước bằng việc cancel upgrade. [C10][C11]

### “Có gì mới đủ để triển khai?”

Đóng góp có thể là bộ điều phối kiểm chứng cho nâng cấp: chọn đúng scope, reference có quản lý, checkpoint PA1, gate dừng mở rộng, attempts và báo cáo coverage/QoS. Không gọi hash trước/sau là thuật toán mới. Cần chứng minh tính lặp lại, phát hiện đúng, thời gian chẩn đoán hoặc giảm bước thao tác thủ công cùng chi phí đo được; chưa có số liệu thì chỉ ghi giá trị kỳ vọng.

## Phụ lục C — Mẫu bằng chứng một run

| Nhóm | Thông tin cần lưu |
|---|---|
| Danh tính | Run ID, FSID, người chạy, chặng U, profile, thời gian |
| Phiên bản | Inventory daemon/host/version/image trước và sau; trạng thái active/standby/quorum |
| Scope | test/upgrade/migration OSD sets, pool/rule, size/min_size, failure domain, ownership |
| Dữ liệu | Corpus không rỗng, S3 version hoặc RBD snapshot/range, nguồn expected state |
| H0 | NOT_IMPLEMENTED nếu chưa có; khi có: manifest revision/hash, nguồn, consistency và tool build |
| Checkpoint | Pha P/gate G, mọi attempts, số byte, expected/observed hash, lỗi và quyết định |
| Coverage | Object/byte cần kiểm và đã kiểm, PG/OSD/primary/epoch, giới hạn client/local |
| Native/QoS | Health, mapping, ok-to-stop, SLO, freshness của metrics, migration/verify bytes |
| Incident | Lần sai đầu, hành động, nguồn phục hồi, RTO/RPO, lý do kết thúc sự cố |
| Cleanup | Tài nguyên và override đã hoàn nguyên, evidence giữ lại, điều kiện đóng chặng |

Không điền H0 PASS từ checksum cũ; không coi tập test rỗng, metrics stale hoặc mất reference là đạt.

## Phụ lục D — Hình cần chuẩn bị khi dựng PPT

| Hình | Slide | Lưu ý |
|---|---:|---|
| Repo comparison/mục lục 15 nhóm | 2 | Nhãn số file là thay đổi, không phải lỗi |
| Prelab ceph -s, version OSD, checksum | 3 | Cùng mốc hợp lệ; không lấy log cũ làm hiện trạng |
| Web workload và RBD baseline/verify | 4 | Ảnh thật, ghi rõ không nâng version trong bài này |
| Bảng U1/U2/U3 và trạng thái đóng chặng | 5 | Nhãn lộ trình lab |
| Bảng daemon order | 6 | Scope cephadm; highlight pha OSD |
| PG mapping trước/sau PA1 | 7 | Ghi epoch và acting set thật |
| Bảng BlueStore/H0 và checkpoints | 8–9 | Nhãn đề xuất, không gắn ảnh 16/16 như H0 |
| Wireframe chọn OSD/coverage | 10 | Nhãn chưa triển khai |
| Biểu đồ đối chứng và phục hồi | 11 | Chỉ tạo sau khi có số liệu thật |

## Phụ lục E — Nguồn dự án

Các liên kết cố định vào commit đã đọc, tránh thay đổi nội dung khi nhánh main cập nhật.

- [G1 — Phân tích Pacific 16.2.5 → 16.2.15](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/comparison/pacific-16.2.5-to-16.2.15/README.md).
- [G2 — Trạng thái prelab](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/as-is-base/pa1-prelab-20260923-090845/01-ceph-s.txt).
- [G3 — Cây OSD sau chuẩn bị S](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/as-is-base/pa1-prelab-20260923-090845/22-after-S-tree.txt).
- [G4 — Báo cáo lab nguồn trong repo](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/Noi_dung_va_loi_thuyet_trinh_Ceph_7_slide.md).
- [G5 — Web README](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/code/rgw-console/README.md).
- [G6 — Web VALIDATION](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/code/rgw-console/VALIDATION.md).
- [G7 — RBD baseline/verify API](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/code/rgw-console/backend/app/api/rbd.py).
- [G8 — S3 PUT/GET checksum](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/code/s3_put_get_test.py).
- [G9 — RGW worker](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/code/rgw-console/backend/app/worker.py).
- [G10 — MOP nguồn](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/MOP/MOP-Ceph-Pacific-16.2.5-to-16.2.15.md).
- [G11 — Tài liệu ý tưởng H0 V2, chưa triển khai](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/9180375b279caf31943abb81541151868c4879ab/features/ceph-v2-h0-verifier.md).


Tài liệu ý tưởng G11 là nguồn bối cảnh, không phải bằng chứng implementation. Bản 1.2 điều chỉnh phạm vi theo yêu cầu mới và xác nhận người thực hiện: H0 chưa triển khai, checksum cũ chỉ là bài test. Những số liệu cần log gốc được đánh dấu trong phụ lục A.

## Phụ lục F — Tài liệu Ceph chính thức

- [C1 — Vòng đời các nhánh Ceph](https://docs.ceph.com/en/latest/releases/).
- [C2 — BlueStore checksums](https://docs.ceph.com/en/quincy/rados/configuration/bluestore-config-ref/#checksums).
- [C3 — Pool size/min_size](https://docs.ceph.com/en/pacific/rados/operations/pools/).
- [C4 — Pacific release notes](https://docs.ceph.com/en/latest/releases/pacific/).
- [C5 — RGW placement targets và pools](https://docs.ceph.com/en/pacific/radosgw/placement/).
- [C6 — RBD snapshots](https://docs.ceph.com/en/pacific/rbd/rbd-snapshot/).
- [C7 — CRUSH map](https://docs.ceph.com/en/pacific/rados/operations/crush-map/).
- [C8 — Upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/).
- [C9 — Cephadm upgrade và staggered workaround](https://docs.ceph.com/en/pacific/cephadm/upgrade/).
- [C10 — Quincy release notes và upgrade](https://docs.ceph.com/en/latest/releases/quincy/).
- [C11 — Reef release notes và upgrade](https://docs.ceph.com/en/latest/releases/reef/).
- [C12 — BlueStore kiểm checksum khi đọc disk](https://ceph.io/en/news/blog/2017/new-luminous-bluestore/).
- [C13 — Ceph Manager administrator guide](https://docs.ceph.com/en/pacific/mgr/administrator/).
- [C14 — MON quorum](https://docs.ceph.com/en/pacific/rados/configuration/mon-config-ref/#monitor-quorum).
- [C15 — Kiểm và sửa PG inconsistency](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/).
- [C16 — Peering và PG history](https://docs.ceph.com/en/pacific/dev/peering/).

Chi tiết H0, consistency/version, thứ tự nâng, gate G0–G6, schema/API và ma trận nghiệm thu nằm trong file đi kèm **H0_Feature_Ket_hop_PA1_va_Web_Canary.md**, bản 1.2. Số hiệu nguồn C/G được quản lý riêng trong mỗi file.
