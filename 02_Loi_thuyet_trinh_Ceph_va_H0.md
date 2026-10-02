# Lời thuyết trình: nghiên cứu phương án nâng cấp Ceph

**Ngày cập nhật:** 02/10/2026  
**Dùng cùng:** [Báo cáo kết quả và kế hoạch đến 01/11/2026](./01_Bao_cao_Ceph_Ket_qua_va_Ke_hoach_den_30_11_2026.md)
**Thời lượng:** khoảng 15–16 phút trình bày, 3–4 phút hỏi đáp; tổng 17–20 phút
**Đối tượng:** hội đồng quản lý nội bộ, chưa cần biết sâu Ceph

Phần chính đi theo 15 slide. Nói rõ đâu là kết quả đã có, đâu là việc cần kiểm trong lab và đâu mới là thiết kế H0. Khi hội đồng hỏi sâu, dùng phụ lục kỹ thuật cuối file.

## Slide 1 Nghiên cứu phương án nâng cấp Ceph

**Thời gian: 20 giây**

Em xin báo cáo kết quả sau một tháng nghiên cứu phương án nâng cấp Ceph và kế hoạch thử trên lab đến 01/11. Mục tiêu của buổi này là thống nhất đường nâng, cách kiểm và đầu ra; chưa xin triển khai trên cụm production.

## Slide 2 Vì sao thử nâng lên Reef 18.2.7?

**Thời gian: 75 giây**

Điểm xuất phát của lab là Pacific 16.2.5. Nhánh Pacific đã hết hỗ trợ, nên giữ bản cũ làm khoảng cách với bản vá ngày càng lớn. Nhưng nâng hệ lưu dữ liệu không thể chỉ thay image: còn phải chứng minh ứng dụng vẫn đọc ghi được và cụm vẫn phục hồi được khi từng daemon thay phiên bản.

Lộ trình qua Quincy cho phép kiểm riêng thay đổi mClock. Profile `balanced` phân bổ tài nguyên OSD giữa client và recovery/backfill/scrub; em sẽ đo độ trễ client cùng tốc độ recovery, không mặc định profile mới tốt hơn mọi workload. Reef cập nhật RocksDB và compaction, có thể giảm write amplification ở một số bài RGW; tác động trên cụm mình phải đo lại. Reef còn có read balancer phân bố primary PG theo cách offline, chỉ nên bật sau khi kiểm tương thích client.

18.2.7 là tag cố định của lab. Bản này sửa BlueStore regression nghiêm trọng của Reef 18.2.5/18.2.6; không phải nói Pacific mắc lỗi đó. Reef đã hết hỗ trợ và 18.2.8 đã phát hành. Kết quả lab .7 phục vụ MOP; bản production cần quyết định riêng. [Phân tích thay đổi](./ceph-analysis.md), [vòng đời Ceph](https://docs.ceph.com/en/latest/releases/), [release note 18.2.7](https://ceph.io/en/news/blog/2025/v18-2-7-reef-released/).

## Slide 3 Cách xây phương án: 5 bước

**Thời gian: 65 giây**

Em chia công việc thành năm bước. Một là khảo sát phiên bản, thành phần và đường dùng dữ liệu của RBD, S3; từ source diff rút ra tình huống có thể ảnh hưởng khi nâng. Hai là chụp trạng thái lab và tạo dữ liệu mẫu có thể kiểm lại. Ba là viết MOP, tức trình tự thao tác kèm điều kiện dừng và bài kiểm. Bốn là chạy thử từng chặng, từ daemon hoặc canary nhỏ rồi mới mở toàn cụm. Năm là đối chiếu log, dữ liệu và tải với tiêu chí đã chốt để ghi PASS, HOLD hoặc FAIL.

Đầu ra của mỗi bước phải dùng được cho bước tiếp. Một daemon hiện `running` mới chứng minh nó khởi động; chưa chứng minh dữ liệu đúng hay workload S3/RBD đã chịu được chặng nâng.

## Slide 4 Cụm Ceph lab

**Thời gian: 65 giây**

Sơ đồ này là lab ba host, không phải production. Ba MON giữ thông tin cụm và quorum; hai MGR vận hành, quan sát; năm OSD giữ dữ liệu; ba RGW nhận yêu cầu S3. Bài RBD đi từ client block storage, bài S3 đi qua RGW, rồi cuối cùng đều tới các OSD lưu dữ liệu.

Ảnh trước nâng MON ngày 01/10 cho thấy cụm đang pha phiên bản: hai MGR và một OSD canary đã lên 16.2.15, các thành phần còn lại vẫn 16.2.5. Ảnh cuối run MON ghi ba MON chạy 16.2.15. Đây là ảnh của đúng thời điểm đó; trước run mới phải chụp lại inventory, image digest, health, PG — nhóm dữ liệu Ceph phân bố lên OSD — và đường client. Chưa thể gọi toàn cụm hoàn tất U1 chỉ vì MON đã lên bản đích.

Nếu cần giải thích nhanh: MON giữ bản đồ và thành viên; MGR quản trị; OSD giữ các bản dữ liệu. Payload của một write bình thường không đi qua MON.

## Slide 5 Kế hoạch nâng toàn cụm

**Thời gian: 80 giây**

Kế hoạch có ba hop: U1 từ 16.2.5 lên 16.2.15, U2 sang Quincy 17.2.7, U3 tới Reef 18.2.7 trên lab. Mỗi hop bắt đầu bằng preflight: version và image thực chạy, backend store, dung lượng, PG, quorum và baseline dữ liệu/tải. Sau đó nâng theo vai trò của cephadm: MGR, MON, OSD rồi RGW; crash và MDS được xử lý theo inventory nếu triển khai.

Ở MON, nâng từng daemon và kiểm quorum giữa các lần. Ở OSD, dùng canary PA1: chuyển một ít PG khỏi OSD X sang spare S, nâng X, trả một batch về X và quan sát recovery, dữ liệu, QoS trước khi mở rộng. Sau từng hop, chạy RBD và S3: thao tác thực, checksum hoặc reopen dữ liệu mẫu. Nếu đo tải, em sẽ lập bài fio/Warp mới với cùng profile trước và sau nâng; các lượt thực hành tháng qua không thuộc bài kiểm này. `HEALTH_OK` hoặc version đúng chỉ là một phần gate.

U2 chỉ mở sau acceptance U1 và strict gate Quincy; U3 chỉ mở khi U2 đạt. Thiếu bằng chứng thì HOLD chặng kế tiếp. Đây là plan toàn cụm, không lấy kết quả MON làm kết quả cuối. [Cephadm upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/).

## Slide 6 Sau một tháng, em học được gì?

**Thời gian: 65 giây**

Điều thứ nhất em rút ra là thay đổi release phải dịch thành bài kiểm cụ thể. mClock liên quan độ trễ client khi cụm recovery; RocksDB/BlueStore liên quan đường ghi và metadata. Số file thay đổi không nói được workload sẽ ra sao.

Điều thứ hai là Ceph có nhiều lớp bằng chứng. Quorum cho biết MON còn điều phối, PG và recovery cho biết các bản dữ liệu đang hội tụ, còn RBD/S3 cho biết client thật vẫn làm việc. Bài kiểm phải đi qua cả ba lớp với timestamp và run ID nối được sự kiện.

Điều thứ ba là canary và gate giúp khoanh lỗi. Thử một OSD, một nhóm PG và một workload trước; không đạt thì giữ phạm vi để điều tra. Lỗi công cụ quan sát cũng phải tách khỏi lỗi dịch vụ bằng log gốc và tín hiệu độc lập.

## Slide 7 Sau một tháng, em đã làm được gì?

**Thời gian: 65 giây**

Về phân tích, em hoàn thành bộ so sánh Pacific 16.2.5 lên 16.2.15 theo 15 nhóm thành phần, và đang tiếp tục diff 16.2.15 lên Quincy 17.2.7. Phần Quincy chưa đóng strict gate nên chưa được xem là điều kiện đã đạt để mở U2.

Về lab, hai MGR và một OSD canary đã lên 16.2.15. Bài PA1 với OSD canary có 16/16 mẫu checksum khớp. Ba MON cũng chạy 16.2.15 sau phiên ngày 01/10. Các OSD và RGW còn lại cùng bài kiểm toàn cụm vẫn là phần việc của chặng đầu, nên em chưa gọi chặng 16.2.5 lên 16.2.15 là hoàn tất.

Web kiểm thử RBD/RGW và bài validation đã có, dùng làm nền chạy workload và thu log. Đến thời điểm này U1 chưa hoàn tất; U2/U3 chưa có kết quả lab để công bố.

## Slide 8 Thử tải RBD và RGW để học cách đo

**Thời gian: 65 giây**

Em chạy fio trên RBD và thử Warp trên RGW để học cách tạo workload, thu số đo và nhận diện tham số cần cố định. Đây là bài làm quen công cụ **trước kế hoạch nâng**, không phải phép đo nghiệm thu U1/U2/U3. Với RBD, bài fio ngày 01/09 chạy `4K randrw`, 70% read, `iodepth=4`, 60 giây. Run ghi khoảng 1.510 read IOPS và 645 write IOPS, lỗi bằng 0.

Hồ sơ trình bày hiện chưa kèm raw log và tham số Warp, nên em chưa đưa con số RGW lên slide. Kinh nghiệm rút ra là khi làm benchmark phục vụ gate nâng cấp sau này, phải giữ cùng workload, tool version, số client, bucket/image test và thời lượng giữa baseline với sau nâng. Em sẽ nhìn IOPS/throughput cùng latency p95/p99, lỗi và recovery throughput. Số fio 01/09 và lần thử Warp này **không dùng làm kết quả before/after hoặc bằng chứng upgrade**.

## Slide 9 Luồng ghi dữ liệu bình thường của Ceph

**Thời gian: 65 giây**

Ứng dụng gửi write qua RBD, S3/RGW hoặc librados. Client dùng bản đồ cụm để tìm PG và primary OSD hiện tại; MON cung cấp bản đồ nhưng không nằm giữa đường payload. Primary kiểm operation và điều phối ghi local cùng các replica. Mỗi OSD dùng BlueStore, có checksum ở local store. Các nhánh local và replica có thể tiến triển đồng thời, nên sơ đồ là luồng logic chứ không cam kết thứ tự callback cố định.

Primary chỉ trả kết quả thành công khi điều kiện hoàn tất bền của native path đã đạt cho operation. Ceph đã bảo vệ nhiều loại lỗi; không nên mô tả nó như hệ thống chưa kiểm dữ liệu. Sơ đồ này là nền để đặt câu hỏi H0 ở slide sau. [Kiến trúc Ceph](https://docs.ceph.com/en/reef/architecture/), [luồng PA1–H0](./H0_Feature_Ket_hop_PA1_va_Web_Canary%20%283%29.md).

## Slide 10 Luồng đọc và phục hồi dữ liệu của Ceph

**Thời gian: 65 giây**

Ở đường đọc, client tìm PG và nhận dữ liệu từ OSD phục vụ request; BlueStore kiểm checksum local theo đường đọc của nó. Nếu một OSD vắng mặt hoặc placement đổi, Ceph dùng các bản còn lại để recovery/backfill sang nơi cần có bản sao. Sau hội tụ, PG có thể về `active+clean`; scrub/deep-scrub kiểm thêm tính nhất quán theo cơ chế native.

Trong PA1, em gọi OSD cần nâng là X và spare là S. PG chuyển khỏi X sang S; X được nâng; sau đó trả một batch nhỏ về X. Một GET từ client có thể do peer khác trả lời, nên dù GET khớp cũng chưa chứng minh chính bản local X sau return đã được đọc. Khác biệt này là lý do ý tưởng H0-R đặt sau recovery, trước khi mở primary canary của X.

## Slide 11 Ý tưởng H0: ba mức kiểm trên đường ghi

**Thời gian: 80 giây**

H0-W là **thiết kế đề xuất**. Trước khi write vào OSD, client hoặc adapter tạo `Hclient` từ payload dự định ghi, gắn với object, generation, range và request. Đây là reference từ trước ranh giới xử lý để so ở các điểm sau.

Mức 1 so `Hclient` với final buffer ở primary ngay trước submit. Mức 2 thêm phép so ở buffer của từng replica bắt buộc. Mức 3 kế thừa hai mức trước, chờ native durable completion rồi đọc lại đúng bản local ở primary và replica bắt buộc **trước success ACK**. Mức cao hơn đòi hỏi nhiều điểm kiểm và chi phí hơn; không thể chỉ bật tùy chọn web là có L2/L3.

Ở cả ba mức, success của request được bảo vệ chỉ trả khi native completion và các phép kiểm của mức đã chọn đều đạt. Timeout hoặc thiếu evidence thì không báo success giả; operation có thể đã commit nên cần state và reconcile. Web/controller chọn scope, policy và thu evidence; ACK gate phải ở data path. [Ba mức và ACK](./H0_Feature_Ket_hop_PA1_va_Web_Canary%20%283%29.md).

## Slide 12 Ceph hiện có gì, phần kiểm thêm nhằm làm gì?

**Thời gian: 70 giây**

Ceph đã có replication, BlueStore checksum, recovery và scrub. H0 không thay các cơ chế này. Câu hỏi nghiên cứu là: nếu payload đổi sau khi client xác định nội dung mong muốn nhưng trước khi một điểm kiểm native tạo checksum, ta có thể đối chiếu nó với reference ban đầu ở đúng operation hay không?

H0 đề xuất reference xuyên ranh giới client–primary–replica và receipt ghi rõ đã kiểm object/generation nào ở đâu. Đây là **giả thuyết coverage bổ sung**, chưa có bằng chứng cụm từng gặp đúng kiểu lỗi ấy và chưa có số đo lợi ích/chi phí. Lab cần fault injection ở vị trí khai báo, đối chiếu detector native với H0 và đo overhead. Nếu native phát hiện trước thì ghi native detection; không lấy kết quả đó làm thành tích H0.

## Slide 13 Kiểm dữ liệu sau khi OSD hồi phục

**Thời gian: 70 giây**

H0-R là nhánh khác H0-W. Nó kiểm corpus cũ sau khi PG recovery/backfill về OSD X trong PA1. Trước movement, controller chốt object, generation và `H0-static` của corpus ổn định. Sau return, đợi mapping và recovery hội tụ, chạy native scrub phù hợp rồi đọc **đúng bản local trên X** để so reference. Kết quả chỉ chứng nhận object/generation/target đã kiểm, không tự chứng nhận cả pool.

Nếu chỉ chạy client GET, request có thể do peer phục vụ nên không được cấp nhầm receipt cho X. Nếu checksum không khớp hoặc reader không chứng minh local target, giữ gate return HOLD để điều tra. H0-R là ý tưởng bổ sung bằng chứng tại checkpoint PA1; nó không thay native recovery, không giữ payload tốt để tự repair. Đây là thiết kế cần kiểm chứng. [H0-R tại PA1](./H0_Feature_Ket_hop_PA1_va_Web_Canary%20%283%29.md).

## Slide 14 Kế hoạch đến 01/11 và đầu ra

**Thời gian: 75 giây**

Từ 02–11/10, em chốt inventory và phần thiếu gate U1, hoàn thiện phân loại Quincy và MOP. Chỉ khi U1 cùng strict gate Quincy đạt mới mở U2 trong 12–18/10. Nếu U2 nghiệm thu được thì 19–25/10 chạy U3 tới 18.2.7. Từ 26–31/10, chạy lại RBD/S3, recovery, checksum, fio/Warp và thu log, số đo theo đúng profile. Ngày 01/11 review kết quả và demo; mốc này không biến hạng mục thiếu evidence thành PASS.

Đầu ra đề nghị là MOP lab ba hop có gate, inventory/version/image, log và bài kiểm dữ liệu/tải, cùng demo hướng H0 tại PA1 trên build thử nghiệm: H0-W L1, H0-R và Web/controller thu evidence. H0 là track thiết kế và thử nghiệm song song; L2/L3 chỉ mở khi có implementation và gate riêng. Để giữ lịch cần lab ổn định, máy build, clone hoặc snapshot phục hồi và người review mốc 11, 18, 25, 31/10. Em xin phê duyệt **phạm vi lab và nguồn lực**; chọn release production sẽ quyết định sau khi có evidence và đánh giá vòng đời hỗ trợ.

## Slide 15 Cảm ơn các anh chị đã lắng nghe

**Thời gian: 15 giây**

Em xin hết. Em mong hội đồng góp ý vào gate toàn cụm và phạm vi demo cần đạt ngày 01/11. Phần nào chưa đủ kết quả, em sẽ giữ đúng trạng thái HOLD trong hồ sơ bàn giao.

## Phụ lục A — Các điểm cần nói chính xác khi hỏi sâu

### Gate MON hiện tại

Run 01/10 đã đưa ba MON lên 16.2.15; raw timeline có các mẫu quorum hợp lệ 3/3. Bốn `rc=1` xảy ra trước redeploy đầu tiên và traceback chỉ tới `cephadm` parse memusage `--` khi observer gọi CLI. Kết luận này không đóng MG0–MG8: còn thiếu preflight, journal và digest từng host, auth/S3 không đủ 30 phút sau MON cuối, cùng reopen/checksum và cleanup. Không dùng trạng thái hiện tại để điền lại evidence còn thiếu của run cũ. [MOP MON](./MOP/MOP-MON-16.2.5-to-16.2.15%20%281%29.md), [GATE MON](./test/GATE-MON-16.2.5-to-16.2.15%20%281%29.md), [đối chiếu observer](./test/MON-20261001-QUORUM-VA-GATE-CLOSEOUT.md).

### Bản chất kết quả fio/Warp

Bài fio 01/09 và lần thử Warp là để học cách chạy công cụ và dựng workload, không phải test/evidence của quá trình nâng cấp. Fio chạy RBD 4K randrw, 70% read, iodepth 4, 60 giây, 1.510 read IOPS, 645 write IOPS, error 0. Chưa có cặp số cùng workload trước/sau nâng nên không suy ra cải thiện hiệu năng. Warp đã được thử theo thông tin người thực hiện; raw log và tham số run chưa nằm trong bộ evidence hiện có, vì vậy không nêu throughput hoặc latency RGW. Bài acceptance tương lai phải pin tool version, command, topology, dataset/bucket test, thời lượng và cửa sổ so sánh.

### H0-W: điều kiện success theo mức

`Hclient` phải tạo trước primary và bind đúng operation, object, generation, range, policy. Native durable completion luôn bắt buộc. L1 thêm final primary buffer match; L2 thêm replica buffer match ở mọi participant bắt buộc; L3 thêm local read-back sau durable completion ở primary và các replica bắt buộc. Reader phải chứng minh target/generation và công bố cache path. Client PUT/GET không đủ làm L3. Timeout/duplicate/failover cần trạng thái có thể reconcile; lỗi trả client không chứng minh mutation chưa commit. Các mức hiện là thiết kế, không gắn PASS khi chưa có build và test đúng điểm kiểm.

### H0-R: reference và local target

`H0-static` dùng cho corpus ổn định trước movement; nó không thay `Hclient` của write mới. Receipt sau return chỉ có giá trị cho object/generation/range và OSD X mà reader đã kiểm. Nếu baseline được tạo bằng cách đọc bản đã lưu, nó chứng nhận trạng thái quan sát ở thời điểm tạo, không chứng minh dữ liệu nghiệp vụ vốn đúng. Native scrub và local verify phải ghi riêng. H0 không chứa payload nguồn để tự khôi phục; mismatch cần xác định peer/backup tốt theo evidence và dùng runbook phục hồi đã thử.

### Vì sao giữ hop Quincy và tag lab 18.2.7?

Release note 18.2.8 không còn khuyến nghị nâng trực tiếp Pacific lên Reef do xung đột feature bit có thể báo `OSD_UPGRADE_FINISHED` sớm; tài liệu không coi đó là bằng chứng data corruption. Quincy 17.2.7 là hop lab để quan sát riêng mClock, memory, backend và mixed-version compatibility. Reef 18.2.7 sửa BlueStore regression của Reef .5/.6, nhưng Reef đã EOL và .8 mới hơn. Đích 18.2.7 phục vụ bài lab tái lập, không mặc nhiên là version production. [Reef 18.2.8](https://ceph.io/en/news/blog/2026/v18-2-8-reef-released/), [vòng đời Ceph](https://docs.ceph.com/en/latest/releases/).

## Phụ lục B — Nguồn kỹ thuật

- [Báo cáo trạng thái và kế hoạch](./01_Bao_cao_Ceph_Ket_qua_va_Ke_hoach_den_30_11_2026.md) — số liệu nội bộ và mốc đề xuất.
- [Phân tích thay đổi phiên bản](./ceph-analysis.md) — mClock, RocksDB, BlueStore, read balancer, lựa chọn tag.
- [Thiết kế H0-W/H0-R kết hợp PA1](./H0_Feature_Ket_hop_PA1_va_Web_Canary%20%283%29.md) — ba mức, ACK gate và local return gate.
- [Ceph Reef release notes](https://docs.ceph.com/en/latest/releases/reef/), [Ceph architecture](https://docs.ceph.com/en/reef/architecture/) và [Cephadm upgrade](https://docs.ceph.com/en/reef/cephadm/upgrade/) — cơ chế nền.
