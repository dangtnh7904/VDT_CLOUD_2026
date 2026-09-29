# Phase 2 — Đang nâng cấp: canary rồi mở rộng

[Mục lục](00-README.md) · [Phase 1](03-PHASE-1-TRUOC-NANG-CAP.md) · [Phase 3](05-PHASE-3-SAU-NANG-CAP.md)

## 1. Mục tiêu và kết quả cần có

Chứng minh từng thành phần/cohort hoạt động trong mixed-version, dữ liệu đúng và SLO giữ được. Mỗi canary/batch có manifest, kết quả gate và thời gian soak riêng. Không nâng đồng loạt trước rồi mới kiểm tra.

## 2. Điều kiện bắt đầu và giữ trong suốt phase

G0–G3 PASS; H0-G0 đạt trước protected canary run. Đọc lại G1/G2 sát thời điểm thực hiện. Thay đổi tải, PG, host hoặc daemon khiến kết quả gate cũ không còn đủ giá trị. Telemetry phải liên tục và nguồn phục hồi chưa bị batch kế tiếp làm mất.

## 3. Thực hiện theo thứ tự nào, thay đổi ở đâu?

### 3.1 MGR: bước chuyển tiếp từ 16.2.5

Cephadm 16.2.5 chưa có staggered filters/limit. Theo hướng dẫn Pacific, nâng standby MGR trước, kiểm target load được, chuyển active có kiểm soát, rồi hoàn tất nhóm MGR bằng engine target. Từ đó mới dùng filter cho các role tiếp theo. Không chạy upgrade toàn cụm rồi trông chờ bấm pause kịp để làm canary. [S03](13-NGUON-VA-DOI-CHIEU.md)

- Trước promote: lưu migration/control state và chọn đường phục hồi; không mặc định target→base MGR sẽ hoàn tác state.
- Sau promote: kiểm active version/image, module, cephadm, metrics parse/query và Dashboard/consumer có dùng. Chạy CAN-01 và G4.
- Monitoring stack có thể được refresh sau MGR trong staggered upgrade; xác nhận delta thực, không giả định mọi daemon ngoài MGR bất biến. [S03](13-NGUON-VA-DOI-CHIEU.md)

### 3.2 MON và crash

Theo cephadm Pacific: MGR → MON → crash → OSD, sau đó các dịch vụ còn lại. Mỗi MON được thay khi quorum còn đủ; xác nhận nó rejoin và ổn định trước MON kế tiếp. Không đổi topology/quorum cùng lúc. Kiểm crash collection sau nâng cohort crash. Chạy CAN-02, G4. [S03, S13](13-NGUON-VA-DOI-CHIEU.md)

### 3.3 Vòng canary cho một OSD X

| Bước | Việc phải làm | Bằng chứng / gate |
| --- | --- | --- |
| A. Chốt X | Ghi host, device/layout, image, mọi PG up/acting/primary, W0/R0/A0 và peers | Manifest X; G1/G2 tươi; chuẩn bị bằng chứng G5 |
| B. Chuẩn bị PA1 | Giữ X online, chuyển đúng P_X sang S bằng upmap từng batch; giữ weight gốc X | Không PG ngoài scope; từng batch hội tụ; không dừng X sớm |
| C. Trước stop | DR_READY cho toàn P_X: đủ replica trên S/peers, X không còn trong up/acting; `ok-to-stop` tươi; batch thì kiểm toàn tập | DR_READY + exit status/output; G2/G5 |
| D. Nâng X | Đổi đúng artifact; restart/activate đúng daemon, một bộ điều khiển thực hiện | Version/digest, container action, device identity |
| E. Rejoin | Kiểm mount/replay, up/in theo trạng thái mong muốn, PG peering và tiến độ recovery | CAN-03, phần activation của G6; G6 đầy đủ còn chờ canary dữ liệu |
| F. H0-R | Trả C về X, chờ recovery hội tụ, deep-scrub mới sau recovery, H0-static verify đúng local X/version/range | H0-GR; R01; RETURN_VERIFIED cho C |
| G. H0-W | X là actual primary đúng PG/epoch; arm L1/L2/L3 đã chọn rồi mở new-object full-write workload có Hclient | H0-GW; W01; native completion + kiểm bắt buộc của level trước success; P-06 |
| H. Soak và mở rộng return | C đạt thì trả phần P_X còn lại theo batch đã chốt, kiểm G6/G7 mỗi batch; PG mới thuộc scope H0 phải lặp F/G | Chỉ đóng X khi toàn P_X đạt mapping cuối dự kiến, test đủ và state tạm được xử lý theo 07 |

F phải đạt trước mở workload G ở cả ba level. Nếu X thành primary sớm, harness vẫn đóng; `primary-affinity` không là fence cứng. Prototype chỉ bảo vệ writer/profile đã kiểm soát; operation ngoài profile không được âm thầm bypass. Xem [11](11-PA1-H0-LEVEL-1-2-3.md).

Scope H0 C là một phần của scope PA1 P_X. Với PG ngoài C, chạy native data/SLO gates theo manifest và ghi rõ **ngoài coverage H0**. Không tự đưa workload RBD/RGW nghiệp vụ vào prototype H0-W để mở rộng; phải có adapter/contract và nghiệm thu trước. Việc chốt mở rộng rollout dựa trên canary không biến dữ liệu chưa được H0 kiểm thành H0 PASS.

`--limit 1` giới hạn số daemon được nâng trong một lệnh; **không chọn đích danh X**, không là số restart song song. Nếu engine chọn daemon khác với manifest PA1, không dùng nó cho X; dùng đường redeploy một daemon đã rehearsal, không để engine nâng song song ngoài kiểm soát. [14](14-LENH-THAM-KHAO.md)

### 3.4 Mở rộng OSD theo cohort

1. Canary đầu tiên PASS → thêm canary cho các layout/media/host khác biệt → mới tăng batch.
2. Chọn batch theo PG giao nhau, failure domain, replica/EC headroom, byte recovery và tài nguyên peers; không chỉ theo số OSD.
3. Tập OSD riêng lẻ đều `ok-to-stop` không chứng minh cả tập cùng dừng an toàn. Recheck toàn tập cùng với sự cố đang có.
4. Sau mỗi batch, đợi G7; PG mới đưa vào scope H0 phải lặp H0-R và capability/arm level. Tăng số lượng có bằng chứng; khi đụng SLO giảm tải/batch, không tự giảm level.
5. Lập dự báo thời gian toàn fleet từ số đo P-04/P-07, tách thời gian drain, restart, return, verify và soak.

### 3.5 Dịch vụ và client còn lại

Đi theo thứ tự role của cephadm target cho các dịch vụ tồn tại: MDS, RGW, rbd-mirror, cephfs-mirror, iSCSI/NFS; xác nhận monitoring được xử lý đúng engine. Client librbd/QEMU/krbd/SDK là scope riêng, không tự nâng theo OSD.

Với RGW: drain một endpoint qua LB theo cơ chế đang dùng, đợi request đang xử lý theo timeout, nâng, kiểm direct, đưa traffic trở lại từng phần; chạy CAN-05. Với RBD client upgrade: kiểm cache/lock/durability trước cutover; chạy CON-RBD. Không tự bật lại endpoint vi phạm policy để đạt chỉ tiêu tốc độ.

## 4. Tạm dừng hoặc giữ nguyên gì?

Giữ freeze placement/PG và mutation cạnh tranh theo [07](07-BAT-TAT-VA-KHOI-PHUC.md). Không dùng cờ chặn recovery trong lúc chờ chuyển PG/backfill. Không hoàn nguyên rộng affinity/upmap của X khi mới xác minh vài PG; CRUSH weight X vẫn giữ baseline trong PA1. Khi STOP, dừng mở rộng; việc giữ/dỡ từng cờ do trạng thái dữ liệu quyết định.

L2/L3 phải chờ verifier của mọi peer bắt buộc; native commit không thay kết quả H0. L3 chờ read-back sau commit ở X và peers. Timeout/mismatch sau commit có thể để lại write đã tồn tại: ghi COMMITTED_UNVERIFIED/uncertain và reconcile retry, không nói “đã rollback write”.

## 5. Gate trong khi nâng

| Checkpoint | Gate |
| --- | --- |
| MGR target active / MON rejoin | G4 |
| Trước mỗi OSD/batch | G1/G2 tươi + G5 |
| Trước workload H0 mới | H0-G0 + H0-GR + H0-GW |
| Sau restart và canary dữ liệu | G6 |
| Trước batch/cohort kế tiếp | G7 |
| Sau tất cả role trong scope | G8 để vào Phase 3 |

## 6. Test cần chạy

CAN-01…CAN-06 và CON-* áp dụng trong [08](08-TEST-CHUC-NANG.md); R/W/P theo level tại [15](15-TEST-H0-LEVEL-1-2-3.md). Đo P-04 và P-06 dưới offered load đã khóa; theo dõi per-write commit/verify/reply, timeout/queue, p95/p99, CPU và read-back I/O. Fault injection chỉ ở lab; native RBD/RGW smoke không tự là H0 adapter acceptance.

## 7. Tiêu chí ra khỏi phase

Các daemon trong scope đúng target, service health/data tests đạt, không action pending ngoài dự kiến, không mất nguồn phục hồi và G8 PASS. OSD/client offline phải được đối chiếu, không biến mất khỏi manifest chỉ vì `ceph versions` không nhìn thấy nó.
