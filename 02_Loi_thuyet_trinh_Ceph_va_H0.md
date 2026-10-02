# Lời thuyết trình báo cáo Ceph và kế hoạch lab H0

**Ngày cập nhật:** 02/10/2026  
**Dùng cùng:** [Báo cáo kết quả và kế hoạch đến 30/11/2026](./01_Bao_cao_Ceph_Ket_qua_va_Ke_hoach_den_30_11_2026.md)  
**Thời lượng:** khoảng 15–16 phút trình bày, dành 3–4 phút hỏi đáp  
**Đối tượng:** lãnh đạo và quản lý kỹ thuật nội bộ

Phần lời nói chính đi theo 18 slide. Phần giải thích kỹ thuật và hỏi đáp phía sau dùng khi cần trao đổi sâu. Các mốc tháng 10–11 là kế hoạch triển khai đề xuất. Trạng thái đã làm lấy từ hồ sơ trong workspace đến ngày cập nhật.

## Slide 1 Tiến độ hiện tại và đầu ra cuối tháng 11

**Thời gian: 30 giây**

Em báo cáo tiến độ nghiên cứu và lab nâng cấp Ceph, cùng kế hoạch đến cuối tháng 11. Hiện đã có bộ phân tích Pacific, đang tiếp tục diff lên Quincy, đã thực hiện một phần nâng lab và xây dựng web hỗ trợ kiểm thử RBD, RGW.

Mục tiêu cuối tháng 11 là bàn giao MOP đã kiểm chứng trên lab qua các chặng đến 18.2.7, kèm hồ sơ kết quả và lab prototype H0. Em trình bày phần đã làm trước, sau đó đi vào trình tự nâng, phạm vi H0 và các mốc nghiệm thu.

## Slide 2 Kết quả phân tích Pacific

**Thời gian: 40 giây**

Với Pacific 16.2.5 đến 16.2.15, em đã hoàn thành inventory 2.665 file thay đổi và bộ báo cáo theo 15 nhóm thành phần. Bộ hồ sơ đã qua acceptance về partition, ledger và cross-reference.

Kết quả sử dụng cho MOP là các finding có điều kiện kích hoạt và bài kiểm tương ứng. Ví dụ, cần kiểm mixed-version, migration state của cephadm, định dạng metrics, config thay đổi và tương thích client. Em đưa các điểm này vào preflight hoặc acceptance của đúng pha nâng.

Số file cho biết phạm vi nghiên cứu. Kết luận vận hành còn phụ thuộc inventory, artifact và kết quả lab của cụm thực tế.

## Slide 3 Tiến độ phân tích Quincy

**Thời gian: 45 giây**

Hiện em đang diff Pacific 16.2.15 với Quincy 17.2.7. Inventory có 4.179 file và đã tạo 15 cặp báo cáo. Ledger hiện có 852 file affect, 522 trivial, còn 2.805 file cần đọc và phân loại tác động. Strict binary gate chưa đạt.

Phần tiếp theo tập trung vào các owner còn mở, gồm MGR, client, CephFS, RGW, build và validation. Mỗi affect phải có finding, bằng chứng và test case phục vụ nâng cấp.

Hai tag thuộc hai release branch khác nhau. Vì vậy em kiểm thêm các backport chỉ nằm ở Pacific, tránh suy rằng đổi major sẽ giữ toàn bộ bản sửa của endpoint cũ. Đầu ra của công việc này là checklist U2 đủ bằng chứng để chạy lab.

## Slide 4 Kết quả lab và vấn đề monitoring

**Thời gian: 50 giây**

Phần lab đã nâng osd.1 lên 16.2.15 sau khi chuyển PG sang osd.3, có kết quả 16 trên 16 mẫu khớp checksum trong MOP PA1. Hồ sơ ngày 01/10 cập nhật thêm MGR đã lên 16.2.15, nên tiến độ đã đi tiếp so với bản báo cáo trước.

Ở monitoring, Prometheus target UP và timestamp của sample tăng, cho thấy vẫn nhận dữ liệu mới. Tuy nhiên metrics còn duplicate HELP và TYPE của ceph_pool_objects_repaired, promtool trả lỗi định dạng. Em giữ finding này mở dù chưa quan sát outage monitoring trong bài lab đó.

Bước tiếp theo là lấy inventory mới, xác nhận đủ active và standby MGR cùng gate còn thiếu, xử lý đường quan sát, rồi chạy MOP MON. Hiện chưa có hồ sơ nghiệm thu toàn bộ cluster.

## Slide 5 Công cụ web kiểm thử RBD và RGW

**Thời gian: 40 giây**

Web hiện hỗ trợ workload RGW, điều khiển job và thu telemetry. Với RBD, đã có lifecycle, file browser, terminal, baseline và verify.

Validation ngày 24/09 ghi 73 backend, 14 Node và 4 frontend tests PASS. Bài RBD live tạo baseline cho bốn file, phát hiện overwrite, sau khi phục hồi thì checksum khớp lại. Bài này đã kiểm lifecycle và remount, chưa đổi phiên bản Ceph.

Phần em phát triển tiếp là chọn scope OSD và PG, capability H0, receipt và coverage. Web sẽ giúp điều khiển bài lab và tập hợp evidence cho từng gate.

## Slide 6 Hồ sơ MOP hiện có và phần cần hoàn thành

**Thời gian: 35 giây**

Workspace hiện có PRE-MOP MGR, các MOP MGR, OSD, PA1 và MOP MON v2 đi cùng bộ gate MG0 đến MG8. Đây là cơ sở để hoàn thiện quy trình từng chặng.

Công việc còn lại là thống nhất bản MOP điều hành, đồng bộ baseline, chạy các bước chưa thực hiện và thu evidence. Sau đó em hoàn thiện MOP Quincy và Reef từ findings của từng cặp phiên bản.

Một bước MOP cần có thao tác, expected result, điều kiện đi tiếp và cách xử lý khi lỗi. Khi bàn giao, từng gate phải truy được về log của run.

## Slide 7 Lộ trình lab đến 18.2.7

**Thời gian: 40 giây**

Lộ trình lab giữ ba chặng: hoàn tất Pacific 16.2.15, nâng sang Quincy 17.2.7, rồi Reef 18.2.7. Sau mỗi chặng, em nghiệm thu toàn cluster, dữ liệu và dịch vụ trước khi mở chặng tiếp theo.

Preflight kiểm backend store, image digest và tương thích host/client. Các yêu cầu RocksDB trước Quincy và BlueStore trước Reef cần xác nhận trên inventory.

18.2.7 là đích thực nghiệm đã chọn cho kế hoạch này. Reef hiện đã hết hỗ trợ upstream và có bản 18.2.8. Khi đề xuất production, em sẽ đánh giá lại release được hỗ trợ và artifact phù hợp. [Nguồn release](https://docs.ceph.com/en/latest/releases/), [Quincy](https://docs.ceph.com/en/latest/releases/quincy/), [Reef](https://docs.ceph.com/en/latest/releases/reef/).

## Slide 8 Trình tự và gate trong MOP

**Thời gian: 45 giây**

Với cephadm, khung nâng đi từ MGR, MON, crash, OSD, rồi các dịch vụ có trong inventory. MGR cần giữ active/standby và failover. MON nâng theo lượt, kiểm quorum và auth/client trước daemon kế tiếp. Trong pha OSD, em áp dụng PA1 và canary.

MOP MON v2 hiện chọn redeploy từng MON để giới hạn đúng daemon và tự áp gate. Các chặng sau cũng cần kiểm hành vi thật của đường thao tác đã chọn.

Gate bao gồm native safety, client I/O, dữ liệu và QoS. Thiếu evidence thì HOLD. Kết thúc chặng còn phải kiểm runtime version, soak và hoàn nguyên cấu hình thuộc run. [Nguồn cephadm](https://docs.ceph.com/en/pacific/cephadm/upgrade/) và MOP MON v2.

## Slide 9 PA1 trong pha nâng OSD

**Thời gian: 55 giây**

Trong PA1 theo MOP DOCX, X là OSD cần nâng và S là spare. Em giữ X online khi chuyển placement sang S theo batch. Bản Markdown cũ còn dùng stop-first, nên cần đồng bộ MOP trước chạy. Trước khi dừng X, phải xác nhận mapping hội tụ, đủ bản, capacity/QoS và native ok-to-stop đạt.

Sau khi X chạy đúng image mới, em trả một batch nhỏ về X, kiểm dữ liệu và dịch vụ khi X tham gia replica, sau đó kiểm primary canary. Chỉ mở rộng return khi đủ gate, rồi hoàn nguyên các override của run.

Thời gian PA1 gồm cả drain, restart và return. Spare phải đúng failure domain và mapping. Sau khi trả dữ liệu về X, S có thể không còn giữ bản cập nhật. Khi X lỗi, quyết định giữ dịch vụ hay phục hồi phải dựa vào acting set và dữ liệu đang có tại thời điểm đó.

## Slide 10 Bài toán kiểm chứng của H0

**Thời gian: 55 giây**

H0 bắt đầu từ câu hỏi về nguồn reference và ranh giới kiểm. BlueStore đã có checksum, Ceph có scrub và recovery. Phần em muốn kiểm chứng thêm là payload tại một điểm trong đường xử lý có còn khớp nội dung mà client dự định ghi, và bản local trên target sau movement có đúng generation hay không.

Ví dụ lab tạo reference cho ABC. Sau đó fault injection làm buffer thành AXC ở một ranh giới xác định. Em kiểm lớp native hoặc H0 nào phát hiện trước và protected success có bị chặn đúng hay không.

Hồ sơ chưa có bằng chứng cụm đã gặp đúng lỗi này. Lab cần chứng minh coverage bổ sung và đo chi phí. Reference cũng phải đủ tin cậy, vì dữ liệu sai trước khi tạo reference vẫn có thể tự khớp digest. [Thiết kế H0](./h0-new.md), [BlueStore checksums](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/#checksums).

## Slide 11 Reference và thành phần H0

**Thời gian: 65 giây**

Với H0-W, client hoặc adapter tạo Hclient trước primary. Digest đi cùng descriptor gắn với cluster, pool, object, generation, offset, length, request và policy revision. Như vậy, digest khớp nhưng gắn nhầm object hoặc generation vẫn bị loại.

Primary verifier kiểm final buffer của operation. Implementation phải giữ binding từ buffer đã hash đến mutation được submit. Nếu hash một bản sao rồi submit một buffer khác thì phép kiểm mất ý nghĩa. Descriptor cũng cần bảo vệ tính toàn vẹn và quyền thay đổi reference.

Operation state và receipt ghi native completion, verification stage và client result để xử lý retry/crash. Web chọn policy, kiểm capability và hiển thị evidence. Gate H0-W nằm trong data path của build Ceph thử nghiệm.

Tài liệu đang có ví dụ source Pacific. Em sẽ rà lại đúng tag 18.2.7 để chọn hook, completion và duplicate path cho prototype. Các thành phần này hiện là thiết kế, chưa có kết quả implementation.

## Slide 12 H0-W L1 L2 L3 và điều kiện ACK

**Thời gian: 80 giây**

Ba level mở rộng phạm vi kiểm trên đường ghi.

L1 so final buffer tại primary với Hclient trước submit. Khi buffer khớp, operation tiếp tục theo native path. Protected success chỉ được trả sau native durable completion và các điều kiện của hợp đồng đã đạt.

L2 thêm verifier tại mọi replica bắt buộc. Tập participant phải được xác định và có capability phù hợp. min_size của pool không thay số participant cần evidence theo hợp đồng H0.

L3 thêm local read-back sau commit ở primary và các replica bắt buộc. Reader phải đọc đúng generation/range và có bằng chứng về cache path. Một lượt PUT rồi GET qua client chưa đủ để chứng nhận L3.

Nếu timeout hoặc thiếu evidence, request giữ trạng thái lỗi hoặc cần reconcile. Một operation có thể đã commit nhưng chưa verify, nên mã lỗi không chứng minh chưa ghi gì. Retry cũng phải giữ identity, reference và kết quả kiểm.

Cuối cùng, ACK gate chỉ kiểm soát protected success. Nếu yêu cầu read khác không nhìn thấy generation chưa verified thì cần publication contract riêng. Prototype phải công bố rõ ranh giới này.

## Slide 13 H0-R tại checkpoint PA1

**Thời gian: 70 giây**

H0-R kiểm dữ liệu sau recovery hoặc backfill. Trước movement, em chốt corpus bất biến, generation và H0-static. Baseline lấy từ dữ liệu đã lưu chứng minh tính không đổi từ checkpoint. Bài đầu kiểm soát writer để reference không stale.

Sau movement, em thu mapping, acting set và native evidence mới. Prototype kiểm local X sau return. Reader phải chứng minh thực sự đọc bản trên X. Client GET có thể được peer khác phục vụ, dù checksum khớp vẫn chưa chứng nhận local X. Nếu kiểm thêm S sau drain thì cần receipt local S riêng.

RETURN_VERIFIED là nhãn receipt đề xuất của H0, chỉ cấp cho object, generation và target đã kiểm. Với PA1, gate này kết hợp native safety và QoS để quyết định mở primary canary hoặc mở rộng return.

H0-R kiểm corpus cũ sau movement. H0-W kiểm các ghi mới thuộc protected workload. Hai kết quả cần receipt riêng. Local reader là phần phải nghiệm thu trong lab H0, trước khi công bố target đã được kiểm.

## Slide 14 Phạm vi lab H0 cuối tháng 11

**Thời gian: 65 giây**

Để có lab chạy được đến cuối tháng 11, em đề xuất replicated RADOS và full-object write, dùng object ID mới cùng pool/namespace riêng. Em kiểm soát writer, từ chối overwrite/delete/partial write trong protected scope. Build thử nghiệm lấy từ tag 18.2.7, có commit patch và image digest riêng.

Prototype gồm L1 tại primary với protected ACK gate, cùng H0-R tại X sau return PA1. Scope này khóa generation để kiểm reference binding, final buffer, native completion và local target.

Gate 25/10 kiểm build, descriptor transport/capability, hook và reader trên đúng tag. Ngày 08/11 cần trace ACK và reader qualification. Đến 18/11, các ca crash/retry/failover và đọc nhầm target phải có kết quả. Gate chưa đạt giữ HOLD để review cách xử lý.

L2/L3, H0-READ, RGW/RBD tổng quát, EC và partial write được giữ trong thiết kế mở rộng. Lab dùng operation/profile đã khai báo, có admission và receipt để thấy chính xác đã kiểm tới đâu.

## Slide 15 Kiểm thử và đo chi phí H0

**Thời gian: 45 giây**

Bộ test gồm write đúng, fault trước primary verifier, identity sai, native failure, timeout, retry/crash và H0-R đọc sai target. Mỗi ca phải xác nhận đúng stage phát hiện và client result, giữ mọi failed attempt.

Đối chứng gồm upstream, build H0-off và L1, cùng workload và topology. Em giữ native checks hoạt động, ghi lớp nào phát hiện trước, rồi đo latency, throughput, CPU, I/O, network và headroom.

Budget được chốt trước run. Hiện chưa có số đo overhead H0, nên báo cáo tháng 11 sẽ đưa số liệu cùng coverage và giới hạn của bài thử.

## Slide 16 Kế hoạch tháng 10 và tháng 11

**Thời gian: 55 giây**

Đầu tháng 10, em xác nhận baseline, hoàn tất các gate MGR và phần còn lại của U1. Đến 25/10, mục tiêu là đóng diff Quincy, chuẩn bị checklist và artifact, đồng thời có build H0 cùng phương án transport/hook/reader. Nếu strict gate Quincy chưa đạt, U2 giữ HOLD để review và điều chỉnh lịch.

Từ cuối tháng 10 đến 08/11, em chạy U2 và nghiệm thu Quincy. Từ 09 đến 18/11, chạy U3 lên 18.2.7 và hoàn thiện demo H0 trên lab riêng.

Tuần 19 đến 25/11 dành cho rehearsal, fault matrix, số đo và sửa lỗi. Từ 26 đến 30/11 chốt MOP, evidence và demo bàn giao.

Source review và build có thể làm trong thời gian chờ lab. Trên mỗi cluster, em giữ một luồng thay đổi và chỉ mở rộng khi gate đạt.

## Slide 17 Phụ thuộc và xử lý khi gate không đạt

**Thời gian: 45 giây**

Các phụ thuộc ảnh hưởng tiến độ gồm phần Quincy chưa phân loại, monitoring còn finding, capacity/failure domain của spare và môi trường build H0. Em đặt chúng vào gate sớm để xử lý trước lượt nâng hoặc demo.

Nếu hook, reader hoặc fault test H0 chưa đạt, em giữ verdict chưa đủ evidence, lưu state/reference và điều tra. Với nâng cấp, khi gate không đạt thì HOLD mở rộng và xử lý theo mapping, dữ liệu cùng rehearsal đã có.

Nguồn lực cần bố trí là lab ổn định, máy build, clone hoặc snapshot phục hồi và review kỹ thuật ở các mốc. Các điều kiện này quyết định khả năng giữ lịch cuối tháng 11.

## Slide 18 Bộ đầu ra và tiêu chí bàn giao

**Thời gian: 40 giây**

Đến 30/11, em đặt mục tiêu bàn giao bốn nhóm đầu ra: MOP lab đủ ba chặng đến 18.2.7, kết quả nâng lab, prototype H0 chạy lại được và báo cáo đánh giá.

MOP đi cùng log version/image, gate dịch vụ/dữ liệu, soak và xử lý lỗi. Lab H0 đi cùng mã nguồn, build, reference/receipt, demo L1 và H0-R trong scope đã chốt, cùng số đo đối chứng.

Em đề xuất thống nhất phạm vi lab và nguồn lực, review tại 25/10, 08/11 và 25/11. Mỗi mốc review kiểm artifact và evidence để quyết định công việc kế tiếp.

## Phụ lục A Giải thích kỹ thuật H0

### Reference từ client và baseline của dữ liệu cũ

`Hclient` là digest của payload dự định ghi, tạo trước primary. Nó giúp kiểm sai lệch sau điểm tạo reference. Nếu client đã tạo payload sai theo nghiệp vụ rồi mới hash, digest không xác nhận được nội dung nghiệp vụ đúng.

`H0-static` dùng cho corpus ổn định trước movement. Nếu baseline lấy bằng cách đọc dữ liệu đã lưu, nó chứng nhận trạng thái quan sát tại thời điểm lấy baseline. Receipt cần ghi rõ `reference_origin`, object/generation/range và thời điểm. Trạng thái dữ liệu cũ chưa có reference phải được hiển thị riêng.

Điểm cần kiểm ở implementation là binding: reference, mutation identity và buffer được submit phải thuộc cùng operation. Digest đúng cho object A không xác nhận object B. Reference của generation cũ không chứng nhận generation mới. Một partial write chỉ có scope range đã khai báo, trừ khi hợp đồng kiểm còn bao gồm trạng thái kết quả toàn object.

### Điều kiện protected success

Theo thiết kế [h0-new.md, mục 9](./h0-new.md):

```text
C = reference, identity, policy, capability và recoverable state hợp lệ
N = native durable completion đạt
B = final primary buffer khớp reference
V = buffer của mỗi replica bắt buộc khớp reference
D = local read-back sau commit khớp reference, đúng generation/range

L1 success: C AND N AND B
L2 success: C AND N AND B AND V tại mọi replica bắt buộc
L3 success: C AND N AND B AND V AND D tại primary và replica bắt buộc
```

Các nhánh có thể tiến triển đồng thời. Gate không giả định primary luôn commit trước replica. Implementation phải gắn evidence với participant/PG interval và giữ các điều kiện native. H0 error sau khi một nhánh tiến triển không đồng nghĩa mutation đã bị hủy ở mọi participant.

### Coverage và chi phí của từng level

| Level | Điểm kiểm | Phần cần nghiên cứu tiếp | Chi phí dự kiến cần đo |
| --- | --- | --- | --- |
| L1 | Final buffer primary so reference trước submit | Sai lệch sau điểm kiểm, replica/store và metadata ngoài scope | Hash, descriptor, state và gate |
| L2 | Thêm buffer từng replica bắt buộc | Sai lệch store sau buffer check | Hash ở peer, protocol/result và coordination |
| L3 | Thêm local read-back sau commit | Reader/cache contract, lỗi xuất hiện sau lần kiểm | Read I/O, hash, queue/memory và thời gian chờ |

Một bài fault cần khai báo vị trí so với cả native checks và H0 verifier. Nếu native đã phát hiện trước thì kết quả phải ghi native detection. Để chứng minh giá trị thêm của L2 hoặc L3, cần chỉ ra coverage riêng so với level thấp hơn và số đo chi phí tương ứng.

### Read-back đủ điều kiện cho L3

Reader phải chứng minh native durable completion đã đạt, đọc đúng local participant, đúng object/generation/range và không chỉ lấy lại buffer của request vừa kiểm. Phải công bố đường cache được dùng, cách ngăn kiểm nhầm generation khi overwrite và giới hạn quan sát của store/hardware.

Một GET qua client có thể đọc primary/peer phù hợp theo native path. Nó kiểm dữ liệu tại ranh giới client nhưng thiếu chứng cứ local read-back của từng participant. L3 cần evidence riêng tại primary và mọi replica bắt buộc. Reader chưa đủ hợp đồng thì giữ `READBACK_UNSUPPORTED` hoặc trạng thái thiếu evidence theo schema prototype.

### Commit verification visibility và ACK

| Trạng thái | Điều phải biết |
| --- | --- |
| Commit | Native storage completion đã xảy ra chưa? |
| Verification | Các check của level đã đủ và match chưa? |
| Visibility | Read khác có thể quan sát generation mới chưa? |
| ACK | Client đã nhận kết quả operation nào? |

ACK gate của H0-W giữ protected success đến khi đủ điều kiện. Dữ liệu đã commit có thể đã visible theo native semantics trong thời gian chờ verify. Nếu workload yêu cầu chỉ phục vụ generation đã verified thì cần verified publication với version pointer có thể phục hồi và mọi read path tuân thủ. RBD ghi đè tại chỗ sẽ cần hợp đồng khác với object bất biến.

Prototype tháng 11 công bố success gate của operation được hỗ trợ. Mọi tuyên bố về visibility cần evidence riêng. Nếu fault xảy ra sau commit, có thể phải giữ `COMMITTED_UNVERIFIED` hoặc `COMMITTED_MISMATCH` và reconcile, tùy kết quả đã biết.

### Retry crash và failover

Điểm khó của H0 nằm cả ở duplicate/completion path. Nếu request đã commit, mất reply rồi client retry, native duplicate state chưa đủ chứng nhận các check H0 đã đạt. Primary mới cần receipt bền hợp lệ, khả năng tiếp tục verification hoặc reverify đúng generation còn được giữ.

Retry phải giữ logical request identity và expected payload. Cùng identity nhưng khác payload là xung đột cần phát hiện. Evidence từ acting set cũ không tự chứng nhận participant mới. Admission, deadline, maximum in-flight và reconcile budget cần được chốt để tránh giữ operation không giới hạn.

Nếu prototype chưa hỗ trợ một nhánh retry/failover, phải fence protected workload hoặc trả trạng thái chưa giải quyết theo hợp đồng. Bài lab vẫn phải chứng minh không false success trong nhánh đó. Chỉ có happy-path ACK chưa đủ nghiệm thu L1.

### H0-R trong PA1

Trình tự đề xuất cho corpus bất biến:

1. Lưu manifest/reference, generation, object range và scope nguồn/đích.
2. Thực hiện PA1/native movement theo MOP.
3. Chờ mapping và native state phù hợp, thu evidence sau movement.
4. Dùng reader đã nghiệm thu đọc local target.
5. So với reference, ghi participant, PG interval, số byte và kết quả.
6. Cấp `RETURN_VERIFIED` cho đúng scope nếu đủ điều kiện.
7. Kết hợp gate dịch vụ/QoS trước canary hoặc mở rộng return.

H0-R mismatch làm dừng mở rộng và điều tra. Reference chỉ có digest/metadata nên nguồn phục hồi vẫn phải là payload tốt từ peer hoặc backup theo evidence. Repair/downgrade cần quyết định và rehearsal riêng.

### Capability policy và web

Ceph version và H0 capability là hai thuộc tính cần inventory riêng. Một primary chạy build H0 không khiến replica upstream tự có verifier. L2/L3 cần capability phù hợp trên toàn bộ participant bắt buộc. Request đã nhận L3 không được tự chuyển thành L1 success vì chậm hoặc thiếu peer.

Policy revision áp dụng cho admission mới, còn operation đang dở giữ hợp đồng đã nhận. Web có thể hiển thị trạng thái chưa triển khai, có capability, đã cấu hình, đang kiểm, PASS, mismatch hoặc thiếu evidence. Đóng tab không được làm data path bỏ verification của request đã nhận.

### Receipt và coverage

Receipt tối thiểu giữ policy/revision, requested/satisfied level, reference origin/ID, request/attempt, object/generation/range, participant/role, PG interval, native state, stage/result, client result, build và timestamp. Với reader, thêm qualification. Payload nghiệp vụ không cần nằm trong log thường.

Coverage phải ghi số operation/byte, participant, generation, khoảng thời gian, operation bị từ chối hoặc ngoài scope. Một lần verify sau đó PASS vẫn giữ mismatch và lịch sử attempt trước. Sampling cần thể hiện phần đã đọc và phần chưa đọc.

### Lý do thu hẹp prototype

RADOS object mặc định có thể bị overwrite. Prototype áp dụng pool/namespace riêng, object ID mới cho mỗi logical write và writer được kiểm soát. Protected scope từ chối overwrite/delete/partial write, retry giữ logical identity. Trong cửa sổ H0-R, corpus/generation được giữ bất biến. Phạm vi full-object write giúp nghiệm thu source hook, reference binding, native completion và trạng thái lỗi trước khi tích hợp các operation khác.

RGW cần mapping logical object sang head/tail, multipart và version ID. RBD cần cache/flush, extent/snapshot và ordering. EC cần reference logical cùng shard/codeword, gồm cả parity, profile và reconstruction. Hash trực tiếp các representation khác nhau không tạo ra một hợp đồng kiểm đúng.

Phạm vi tháng 11 là đề xuất kỹ thuật cho prototype. Kết quả của nó dùng quyết định mở rộng level/workload và đánh giá production sau này.

## Phụ lục B Câu hỏi kỹ thuật dự kiến

### Cuối tháng 11 sẽ nhận được những gì

MOP lab đủ ba chặng đến 18.2.7, log và gate nghiệm thu, demo H0-W L1 và H0-R trong scope replicated RADOS đã chốt, cùng source/build/test report. Báo cáo ghi coverage, overhead, cách xử lý lỗi và các phần chưa hỗ trợ. Các đầu ra này có mốc review trước bàn giao để kiểm chứng tiến độ.

### Tại sao vẫn chọn 18.2.7 khi Reef đã có 18.2.8

18.2.7 là mốc lab đã chọn trong phạm vi dự án. Hồ sơ giữ nguyên mốc để nghiên cứu và tái lập. Quyết định production cần kiểm release được hỗ trợ, bản vá và tương thích thực tế. Reef hiện EOL upstream từ 20/03/2026. [Ceph release lifecycle](https://docs.ceph.com/en/latest/releases/).

### Vì sao đi qua Quincy

Chia chặng giúp kiểm tương thích và xác định lỗi theo từng release. Tài liệu Reef hiện cũng không còn khuyến nghị nâng trực tiếp Pacific sang Reef. Trước U2/U3, kiểm các điều kiện backend, client và artifact của đúng release. [Quincy upgrade](https://docs.ceph.com/en/latest/releases/quincy/), [Reef upgrade](https://docs.ceph.com/en/latest/releases/reef/).

### Đã nâng MGR thì đã xong U1 chưa

Hồ sơ 01/10 ghi MGR và một OSD đã nâng. U1 còn cần hoàn tất MON, crash, các OSD còn lại và dịch vụ trong inventory, rồi acceptance cuối chặng. Active MGR ở target cũng chưa thay bằng chứng đủ active/standby, module, failover và monitoring gate.

### Monitoring đang UP thì có cần giữ finding mở

Có. Mẫu mới chứng minh functional ingestion trong lần kiểm. promtool vẫn báo lỗi duplicate HELP/TYPE nên format compliance còn FAIL. MOP phải giữ lỗi này và kiểm parser/observer thực tế. Nếu dùng đường quan sát thay thế để tiếp tục lab, đường đó cần đủ signal, có evidence và guardrail. Nguồn: [test-gate.md](./test-gate.md), [MOP MON v2](./MOP/MOP-MON-16.2.5-to-16.2.15-v2.md).

### Ceph đã có checksum thì H0 bổ sung gì

H0 đề xuất mang reference từ trước ranh giới cần bảo vệ vào phép kiểm đúng operation/generation. Lab phải chứng minh coverage thêm ở primary, replica hoặc local target mà native evidence hiện tại chưa trả lời được cho workload đó. Giá trị nằm ở ranh giới, nguồn reference và evidence. Việc đổi thuật toán hash tự nó chưa chứng minh lợi ích.

### Có bằng chứng cụm đã gặp payload sai nhưng checksum nội bộ vẫn khớp chưa

Chưa có trong hồ sơ được cung cấp. Đây là mô hình lỗi nghiên cứu. Fault injection chỉ chứng minh detector và gate hoạt động trong điều kiện thử. Cần thêm pain point, nhu cầu workload và số đo để quyết định có nên mở rộng H0.

### 16 trên 16 checksum có phải kết quả H0 không

Đó là kết quả kiểm toàn vẹn của bài lab trước. H0-W cần reference binding, verifier trong data path, ACK gate và receipt của implementation. H0-R cần thêm bằng chứng local target. Kết quả checksum cũ vẫn giữ đúng giá trị trong phạm vi bài kiểm đã chạy.

### Chỉ xây web có đủ làm H0-W không

Web hỗ trợ cấu hình, capability và evidence. H0-W theo thiết kế mới cần tích hợp client/adapter, verifier, native completion và retry/duplicate path. Một công cụ ngoài Ceph làm PUT/GET có thể kiểm ở lớp client nhưng chưa chứng nhận primary/replica buffer gate.

### L3 có chứng minh bytes đã nằm đúng trên media vật lý không

L3 theo thiết kế kiểm local read-back dưới reader, cache, durability và phần cứng đã công bố. Tuyên bố chỉ đến mức đường đọc đó quan sát được. Phải có evidence về generation/range và cache path, không suy một kết quả read-back thành bảo đảm mọi tầng media hoặc lỗi tương lai.

### H0 báo lỗi sau commit thì rollback dữ liệu được ngay không

Commit và verification có thể khác trạng thái. Sau commit, mismatch cần giữ generation/reference, áp dụng visibility policy và reconcile. H0 không lưu payload để tự restore. Phục hồi phải chọn nguồn tốt bằng evidence và dùng runbook đã thử.

### L1 đã ACK thì dữ liệu được bảo vệ mãi về sau không

Receipt L1 chứng nhận các check tại operation đó. Lỗi sau lần kiểm cần cơ chế native, H0-READ hoặc H0-R theo reference còn được giữ. Mỗi hợp đồng phải công bố ranh giới thời gian và scope.

### Làm thế nào chứng minh đúng OSD X sau PA1

Giữ mapping/PG interval, generation và local-reader evidence của X. Bài F20 kiểm trường hợp client đọc peer khác và match để chắc chắn hệ thống không cấp nhầm RETURN_VERIFIED cho X. active+clean hoặc client checksum khớp là một phần evidence, chưa đủ target-local certification.

### H0 có thể làm availability thấp đi không

Có thể. Hash, read-back, coordination và reference dependency tăng tài nguyên và thời gian chờ. Strict participant policy có thể từ chối protected operation khi peer/verifier thiếu capability. Bài đo phải ghi timeout/rejection, throughput và headroom, cùng latency. Level chỉ được mở rộng khi lợi ích phù hợp chi phí workload.

### Nếu tiến độ H0 trượt thì xử lý mốc cuối tháng 11 thế nào

Gate 25/10 kiểm sớm build, descriptor transport/capability, hook và reader. Khi một hạng mục chưa đạt, em giữ HOLD, ghi dependency, patch/PoC đã có và phương án xử lý để review lịch. Track MOP upstream có gate riêng. Mục tiêu lab H0 giữ scope prototype đã chốt, các phần RGW/RBD/EC tổng quát nằm trong giai đoạn mở rộng.

## Phụ lục C Chuẩn bị trước buổi trình bày

- Cập nhật snapshot ledger Quincy nếu công việc diff tiến thêm sau ngày 02/10.
- Lấy inventory mới: runtime version, image digest từng daemon, MGR active/standby, quorum, PG và upgrade status.
- Chuẩn bị log version của OSD/MGR đã nâng, corpus và thời điểm của checksum run.
- Mang evidence Prometheus target/sample mới và lỗi parser cùng lần kiểm.
- Dùng ảnh web thật, giữ ngày validation và phạm vi chức năng đã chạy.
- Thống nhất workload/budget lab, nguồn lực build/clone và người review kỹ thuật tại từng mốc.

## Phụ lục D Nguồn sử dụng

Trạng thái công việc và số liệu xem bản đồ nguồn trong [file báo cáo, Phụ lục C](./01_Bao_cao_Ceph_Ket_qua_va_Ke_hoach_den_30_11_2026.md). Thiết kế H0 dùng [h0-new.md](./h0-new.md), phần Việt v3.0 đầu tài liệu. Lịch triển khai, scope prototype và mốc review là đề xuất của bản báo cáo này.
