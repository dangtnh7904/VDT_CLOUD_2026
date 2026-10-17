# PA1 và PA2 — Nâng cấp OSD và so sánh tác động

**Cập nhật 07/10/2026.** Phạm vi: Ceph Pacific, replicated pool. Đây là phương án thiết kế và yêu cầu triển khai; các trạng thái PASS trong tài liệu không phải kết quả đã chạy trên cluster.

**Tài liệu liên quan:** [Controller](OSD_Upgrade_Data_Validation_Controller.md) · [Console](Storage_Lab_Console_OSD_Validation_and_Benchmark.md) · [Bài kiểm lab](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md)

**Mục lục**

- [1. Phạm vi và tổ chức tài liệu](#1-phạm-vi-và-tổ-chức-tài-liệu)
- [2. Định nghĩa](#2-định-nghĩa)
- [3. Nguyên tắc vận hành](#3-nguyên-tắc-vận-hành)
- [4. PA1 — Luồng nâng cấp một OSD](#4-pa1--luồng-nâng-cấp-một-osd)
- [5. Baseline, controlled drain và redeploy](#5-baseline-controlled-drain-và-redeploy)
- [6. Return theo nhóm và deep-scrub](#6-return-theo-nhóm-và-deep-scrub)
- [7. Khôi phục primary-affinity và kết thúc run](#7-khôi-phục-primary-affinity-và-kết-thúc-run)
- [8. Benchmark phụ trợ: chứng minh tác động QoS](#8-benchmark-phụ-trợ-chứng-minh-tác-động-qos)
- [9. Batch và giới hạn đồng thời](#9-batch-và-giới-hạn-đồng-thời)
- [10. Rollback bằng OSD sạch chạy bản cũ](#10-rollback-bằng-osd-sạch-chạy-bản-cũ)
- [11. Gate và cách đọc kết quả](#11-gate-và-cách-đọc-kết-quả)
- [12. Evidence và bài lab bổ sung](#12-evidence-và-bài-lab-bổ-sung)
- [13. PA2 — Rotating spare](#13-pa2--rotating-spare)
- [14. So sánh PA1 và PA2](#14-so-sánh-pa1-và-pa2)
- [15. Tài liệu kỹ thuật đối chiếu](#15-tài-liệu-kỹ-thuật-đối-chiếu)

## 1. Phạm vi và tổ chức tài liệu

PA1 chuyển toàn bộ PG phục vụ dịch vụ khỏi OSD X, nâng cấp X, trả PG về theo nhóm nhỏ ở vai trò replica, deep-scrub rồi khôi phục primary-affinity và cấu hình vận hành.

PA2 dùng **rotating spare**: chuyển PG X→S, nâng X, rồi dùng X để nhận PG từ Y; Y sau nâng trở thành spare cho lượt kế tiếp. Dữ liệu đã chuyển sang S không bắt buộc quay lại X.

Hai phương án được trình bày song song, không đặt phương án ưu tiên hoặc mặc định. Mục 4–7 mô tả luồng PA1; mục 13 mô tả PA2; mục 14 so sánh hai phương án. Các yêu cầu về an toàn, kiểm replica, QoS và replacement dùng chung, với phạm vi admission/placement riêng của từng phương án. Quy trình sử dụng các cơ chế Ceph hiện có.

| Thành phần | Vai trò |
|---|---|
| `PA1_PRODUCTION` | PA1: drain, nâng cấp, return, deep-scrub, restore |
| `PA2_ROTATING_SPARE` | PA2: handoff theo nhóm, nâng nguồn đã drain, chuyển vai spare, bàn giao placement cuối chuỗi |
| `QOS_OBSERVER` | Luồng phụ tùy chọn: đo BEFORE/DURING/AFTER và đối chiếu với sự kiện nâng cấp |
| `REPLACE_WITH_OLD_VERSION` | Rollback: loại OSD X, thêm OSD sạch R chạy bản cũ tương thích |

Ba tài liệu chính lần lượt mô tả hai phương án PA1–PA2, Controller và Console. Toàn bộ bài kiểm bổ sung trong lab nằm tại [PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md); bài lab dùng trực tiếp PG và dữ liệu test đang có. Kết quả lab được báo riêng, không trở thành checklist bắt buộc cho từng OSD production.

Benchmark không phải điều kiện bắt buộc để bắt đầu hoặc kết thúc nâng cấp. Giám sát health, dung lượng và QoS vận hành vẫn được duy trì khi benchmark tắt. EC cần phương án riêng và nằm ngoài phạm vi bộ tài liệu này.

## 2. Định nghĩa

| Ký hiệu | Ý nghĩa |
|---|---|
| X / Xi | OSD mục tiêu của một lần nâng cấp / một batch |
| S / Si | OSD hoặc tập OSD nhận PG khi drain X; không mặc định một S đủ chứa cả X |
| R | OSD sạch chạy bản cũ, thay X khi rollback |
| Return group | Nhóm PG được đưa về X trong một lần thay mapping |
| Return set | Toàn bộ PG dự kiến trả về X trong run, có revision khi plan thay đổi |
| Run / session | Một workflow / nhóm workflow có chung timeline và evidence |
| Incarnation | Định danh lần tạo OSD, gắn OSD FSID và thiết bị; khác với OSD ID đơn thuần |
| U / D | Nguồn sắp nâng / đích nhận đã chạy bản đích trong một lượt PA2; lượt đầu U=X, D=S; lượt sau U=Y, D=X |
| Handoff group / handoff set | Nhóm PG / toàn bộ PG chuyển từ U sang D trong một lượt PA2 |
| Chain / wave | Chuỗi xoay spare có thứ tự / đợt nâng gồm một hoặc nhiều chuỗi |
| Spare candidate | OSD đã nâng và chưa phục vụ PG trong scope; còn phải đạt admission gate cho từng nguồn kế tiếp |
| Desired end state | Placement, affinity, version và vai trò spare đích đã chốt cho run/wave |

Trong production, scope isolation gồm toàn bộ pool/PG có thể đặt dữ liệu lên nguồn X/U. Nếu còn PG ngoài phạm vi đã chọn trên nguồn đó thì chưa được gọi là drain 100%. Khi thực hiện PA1 hoặc PA2 trong lab, dùng cùng tiêu chí này đối với PG của cụm lab.

## 3. Nguyên tắc vận hành

1. **Drain membership:** trước redeploy, X của PA1 hoặc U của PA2 phải vắng trong cả `up[]` và `acting[]` của toàn bộ PG trong scope. Chỉ giảm số primary không đủ.
2. **Nhận PG làm replica:** PA1 áp dụng cho return về X; PA2 áp dụng cho handoff vào D. Giữ affinity OSD nhận ở 0 theo plan và xác nhận actual primary khác OSD đó. Affinity không điều khiển membership; upmap/CRUSH mới quyết định placement.
3. **Kiểm sau hội tụ:** deep-scrub theo PG sau khi nhóm return/handoff đã catch-up; ghi nhận completion mới và kết quả sạch.
4. **Khôi phục theo OSD:** affinity áp dụng cho cả OSD. Hoàn tất kiểm toàn bộ PG trong return/handoff set và đối chiếu membership thực trước khi khôi phục affinity; không mở sau riêng nhóm đầu.
5. **Dừng an toàn:** kiểm `ok-to-stop` cho cả tập sẽ dừng đồng thời, cùng capacity và failure-domain/N+1 policy. OSD đang nhận/giữ các PG đã bàn giao không nằm trong tập sẽ dừng.
6. **Có đường khôi phục:** mọi cấu hình tạm có baseline và change ledger; phương án replacement và image cũ được chốt trước run.

Không dùng `norebalance` làm cơ chế khóa PG hoặc chọn primary. Các flag đang chặn recovery/backfill/scrub phải được xử lý theo plan để các bước tương ứng có thể hoàn thành. Không hạ `min_size` để vượt gate.

## 4. PA1 — Luồng nâng cấp một OSD

| Bước | Thao tác | Điều kiện chuyển tiếp |
|---|---|---|
| 1. Baseline và plan | Lưu config/flags/affinity/upmap, health, version/image; chọn X/S và rollback plan | Baseline đầy đủ, placement và capacity hợp lệ |
| 2. Giảm primary duty | Đặt affinity tạm theo plan, kiểm vai trò thực tế | Không còn primary trên X trong scope cần drain |
| 3. Drain X→S | Chuyển PG theo nhóm nhỏ, theo dõi recovery/backfill | Mapping từng nhóm hội tụ |
| 4. Isolation | Kiểm toàn inventory hiện tại | X không thuộc up/acting của bất kỳ PG trong scope |
| 5. Maintenance gate | Kiểm N+1, capacity và ok-to-stop của cả down set | Gate còn hiệu lực ngay trước redeploy |
| 6. Nâng cấp X | Redeploy bằng image digest đã chốt | Daemon lên bình thường |
| 7. Daemon ready | Kiểm up/in, version/digest, health và isolation | `RETURN_ALLOWED` |
| 8. Return nhóm PG | X nhận lại PG ở vai trò replica | Actual mapping hội tụ, PG active+clean |
| 9. Deep-scrub nhóm | Chạy và xác nhận lượt scrub mới hoàn tất | `REPLICA_ACCEPTED`; lặp bước 8–9 nếu còn nhóm |
| 10. Sẵn sàng restore affinity | Đối chiếu toàn return set và PG thực đang có X | `PRIMARY_RESTORE_READY` |
| 11. Restore affinity | Khôi phục giá trị baseline/policy, quan sát vai trò thực tế | Cấu hình đúng, không lỗi mới liên quan |
| 12. Restore và ổn định | Khôi phục cấu hình tạm còn lại theo ledger, đợi hệ thống ổn định | `COMPLETE` |

Khi đã drain 100%, mọi I/O trong thời gian X down được xử lý bởi các OSD còn lại. Không có bước tạo một bộ dữ liệu riêng trong khoảng X down.

Nếu bật benchmark, observer lấy BEFORE trước thay đổi affinity đầu tiên, tiếp tục đo xuyên suốt DURING và lấy AFTER khi return/restore đã ổn định. Nó chạy bên cạnh bảng trên và không điều khiển tiến trình nâng cấp.

## 5. Baseline, controlled drain và redeploy

Baseline gồm health/PG states, OSD versions/digests, OSDMap/CRUSH, affinity, flags, upmap/upmap-items, balancer, autoscaler, service specs, dung lượng và mapping. Chốt ngưỡng tải, timeout, thời gian ổn định cùng phương án xử lý khi không đủ cửa sổ bảo trì.

Với từng PG, ghi mapping trước, cặp X→S, primary dự kiến, failure domain, lượng dữ liệu ước tính và các override đã tồn tại. Nếu PG đã có upmap, tính thay đổi từ toàn bộ giá trị hiện tại; không ghi đè mù hoặc xóa toàn bộ override của cụm.

Giữ placement ổn định theo plan trong cửa sổ can thiệp; mọi thay đổi balancer/autoscaler/config phải có ledger. Inventory được cập nhật khi map hoặc pool đổi, không chỉ kiểm danh sách PG đã chụp ban đầu. PG mới làm phá isolation thì dừng và cập nhật plan.

Upmap chỉ tạo placement mong muốn. Phải chờ `up[]` và `acting[]` hội tụ, đủ bản sao và không còn X rồi mới kết luận drain xong. Recovery/backfill do drain có thể ảnh hưởng cả PG dùng chung tài nguyên.

Lệnh minh họa; giá trị thực lấy từ MOP đã chốt:

```bash
ceph osd ok-to-stop <X1> <X2>
ceph orch daemon redeploy osd.<X> --image <TARGET_IMAGE_DIGEST>
```

Không mặc định bật noout toàn cụm. Nếu plan dùng noout theo OSD, lưu và khôi phục đúng trạng thái cũ. Kiểm image thực tế của daemon sau redeploy, không suy từ image chỉ định trong lệnh.

## 6. Return theo nhóm và deep-scrub

Sau `RETURN_ALLOWED`, thực hiện từng nhóm:

1. Ghi danh sách PG được phép trả về; cập nhật mapping theo plan.
2. Giữ X làm replica, đợi catch-up và active+clean; kiểm actual role.
3. Chụp marker/history trước scrub, yêu cầu deep-scrub và thu bằng chứng hoàn tất mới.
4. Kiểm inconsistency, scrub/checksum/I/O error, crash và repair event liên quan.
5. Ghi `REPLICA_ACCEPTED` cho nhóm rồi mở nhóm tiếp theo.

Đơn vị scrub là PG, bao gồm các OSD tham gia PG; đây không phải phép đọc riêng ổ X. Request thành công hoặc một marker scrub cũ không đủ để PASS. Với production đang ghi, kết quả là kiểm nhất quán của lượt scrub đó.

Plan mặc định kiểm mọi PG được trả về trong run, theo giới hạn `scrub_concurrency`. Việc chọn ít PG để kiểm thêm trong lab không làm giảm coverage native của quy trình PA1. Thay mapping/incarnation liên quan hoặc xuất hiện lỗi mới thì đánh giá lại evidence trước chuyển bước.

Nếu scrub lỗi hoặc thiếu bằng chứng hoàn tất, giữ HOLD/BLOCKED và không mở rộng return. Không tự chạy `pg repair` để biến lỗi thành PASS. Nếu hết cửa sổ bảo trì, giữ trạng thái replica đã xác nhận an toàn hoặc xử lý theo rollback plan; ghi rõ các nhóm chưa hoàn tất.

## 7. Khôi phục primary-affinity và kết thúc run

`PRIMARY_RESTORE_READY` yêu cầu toàn return set đã hội tụ và scrub đạt, đồng thời không có PG ngoài plan đang chứa X mà chưa được đánh giá. Trước thao tác, kiểm lại health, dung lượng, QoS và độ mới của evidence theo policy.

Khôi phục **đúng giá trị affinity ban đầu hoặc policy đích đã chốt**, không mặc định 1.0. Ceph lựa chọn primary theo mapping và affinity; khôi phục affinity không có nghĩa X chắc chắn làm primary của một PG cụ thể. Baseline affinity bằng 0 thì kết thúc với 0, trừ khi plan có thay đổi rõ ràng.

Sau đó khôi phục các cấu hình tạm còn lại theo ledger. Các thay đổi placement đã biết trước cần được tính vào return plan. Bật lại balancer/autoscaler có thể tạo chuyển động dữ liệu mới; ghi event, theo dõi convergence và đợi đạt điều kiện ổn định trước `COMPLETE`.

Kết quả scrub gắn với PG và lượt kiểm trong run. Khi đã bàn giao về chế độ vận hành bình thường, Ceph tiếp tục placement và lịch scrub theo policy thường ngày; không yêu cầu mọi PG mới trong tương lai phải chạy lại workflow nâng cấp.

`COMPLETE` cần đúng version/image, các gate trong run đạt, cấu hình về đúng đích, không còn thay đổi tạm chưa xử lý và đủ cửa sổ ổn định. Sau replacement, ledger ghi X→R và policy mới thay cho việc khôi phục vào thiết bị đã loại bỏ.

## 8. Benchmark phụ trợ: chứng minh tác động QoS

### 8.1. Quan hệ với upgrade

Observer dùng Warp cho RGW/S3 hoặc fio cho RBD/file nằm trên Ceph. Nó không tự drain, đổi acting, restart OSD hoặc chọn primary. Run nâng cấp phát event; observer ghép vào log client và telemetry. Benchmark độc lập cũng có thể chạy không cần target OSD, bài kiểm dữ liệu lab.

Ba cửa sổ chính: **BEFORE → DURING → AFTER**. BEFORE kết thúc trước thay đổi affinity/mapping đầu tiên; DURING của PA1 có các mốc giảm primary, X→S, restart, S→X, deep-scrub, mở primary, restore; AFTER chỉ bắt đầu khi return/restore xong và các điều kiện ổn định đạt. Nếu có plateau tạm thời thì lưu như một cửa sổ con của DURING.

Với PA2, DURING bao gồm chuẩn bị S nếu thuộc phạm vi đo, các lượt U→D, nâng U, chuyển vai spare và bàn giao placement cuối wave. AFTER của PA2 bắt đầu tại `AFTER_WAVE_STABLE`; một lượt giữa chuỗi ổn định chỉ là plateau của DURING. Chốt phạm vi đo trước khi chạy để không bỏ chi phí chuẩn bị spare hoặc chi phí reconcile cuối đợt.

### 8.2. Phải đo các PG thực sự đổi acting

| Nhóm đo | Tiêu chí | Câu hỏi cần trả lời |
|---|---|---|
| `REMAP` | PG thực tế thay X bằng S trong PA1 hoặc U bằng D trong PA2; lưu cả quá trình up/acting hội tụ | Latency/throughput/error thay đổi bao nhiêu khi dữ liệu phải chuyển? |
| `NEIGHBOR` | Không thuộc REMAP nhưng chung OSD, host, DB/WAL, NIC hoặc miền tài nguyên có bằng chứng | Các workload dùng chung tài nguyên bị ảnh hưởng ra sao? |
| `CONTROL` | Mapping không đổi và không có giao nhau tài nguyên đã quan sát trong phạm vi so sánh | Có xu hướng chung của dịch vụ/tải nền không? |

Nhóm CONTROL vẫn có thể chung switch, gateway hoặc tài nguyên toàn cụm; không gọi là “chắc chắn không ảnh hưởng”. Membership được cập nhật theo thời gian, không chỉ dựa vào inventory trước nâng cấp.

Ví dụ PG đang có primary A, các bản sao X/B: drain thay X bằng S trong khi A vẫn primary. Client write vẫn có thể chậm vì replication tới S, peering hoặc tranh tài nguyên recovery; không chỉ những PG từng có X làm primary mới cần đo. Đây là giả thuyết cần đo, không phải mức suy giảm đã biết.

### 8.3. Bằng chứng workload đi qua PG

Để kết luận riêng cho REMAP, cần chứng minh đối tượng/range mà workload truy cập ánh xạ tới PG đó và PG thực sự chuyển membership theo plan PA1 hoặc PA2. Chọn nguồn phù hợp với benchmark asset đã map, hoặc chọn trực tiếp PG có sẵn trong lab với CRUSH/failure domain phù hợp. Không sửa customer object để ép placement.

RADOS có object→PG evidence; fio/RBD cần resolver offset→RADOS object theo layout; Warp/RGW cần resolver object/manifest và các phần dữ liệu liên quan. Một operation service có thể chạm nhiều PG/metadata, nên mức proof phải ghi rõ. Nếu adapter chỉ có số đo endpoint, báo `SERVICE_ONLY`; không gọi là số đo REMAP đã chứng minh. Bài RADOS hỗ trợ kiểm PG path có thể bổ sung, nhưng không thay số đo QoS RGW/RBD.

### 8.4. Thử nghiệm batch và báo cáo

Thử canary rồi các batch đại diện, ví dụ 1/3/6/9/12; đây là các mức thử cấu hình được. Giữ workload, dữ liệu và cách cấp tải tương đương giữa các lần; ghi cả PG/bytes di chuyển, primary shift, recovery rate, destination overlap và topology. Batch 9 chạy tuần tự không được báo như 9 OSD down đồng thời.

Bài đo tối thiểu cho một batch PA1: chuẩn bị workload có mapping được chứng minh trên các PG sẽ rời Xi; lấy BEFORE; giữ workload chạy trong khi MOP drain thực sự Xi→Si, nâng cấp và return; lấy AFTER ổn định; so sánh riêng từng cohort và từng loại I/O. Ghi mốc remap của từng PG để thấy spike ngắn bị che khi lấy trung bình cả batch. Các workload thuộc NEIGHBOR/CONTROL chạy với tải tương đương để đối chiếu. Đây là kế hoạch thử, chưa phải số đo suy giảm.

Mỗi nhóm và mỗi phase báo: offered/completed IOPS, MiB/s, p50/p95/p99, timeout/error, khoảng dừng I/O, thời gian vi phạm SLO và thời gian trở lại ổn định. Ghi load model: concurrency cố định hay rate cố định; latency tăng có thể làm offered load giảm với mô hình chờ phản hồi. Không dùng một p99 trung bình toàn session để che các đợt gián đoạn ngắn.

So sánh DURING–BEFORE lượng hóa tác động bảo trì với workload kiểm soát; AFTER–BEFORE chỉ kết luận regression khi profile, dữ liệu, cache, client, topology và tải nền đủ tương đương. Thiếu proof/mẫu/baseline thì giới hạn kết luận, không gán 0. Kết quả QoS được báo riêng với kết quả vận hành và kiểm dữ liệu.

SLO được cấu hình có thể làm HOLD bước tiếp theo; không vì vậy biến benchmark thành điều kiện luôn bắt buộc. Tắt benchmark không tắt giám sát QoS vận hành. Khi runner bị throttle/pause để giữ budget, mở segment mới và giữ khoảng trống trong báo cáo.

## 9. Batch và giới hạn đồng thời

Các tham số độc lập: `batch_size`, `drain_parallelism`, `max_simultaneous_down`, `return_parallelism`, `scrub_concurrency`, `promotion_parallelism`. Warp/fio có concurrency/iodepth riêng.

PA2 dùng thêm `chain_parallelism` và `handoff_parallelism`; một chain tuân thủ thứ tự handoff → nâng nguồn → chuyển vai spare. Handoff groups vẫn bị giới hạn PG/bytes và ngân sách QoS.

Planner xét cả PG overlap giữa Xi, failure domain, S dùng chung, headroom, recovery bandwidth, scrub và QoS. Không để việc drain một target chuyển bản sao sang target sắp bị dừng. Recheck toàn maintenance set trước từng hành động; không suy “từng OSD ok-to-stop” thành “cả batch an toàn”.

Quy mô 1.600 OSD/24 PB cần ước lượng từ số liệu canary: bytes drain/return của PA1 hoặc handoff và reconcile của PA2, thời gian scrub tất cả PG bắt buộc, số destination có thể phục vụ đồng thời và tải nền. Các bài lab bổ sung chạy trên PG có sẵn để kiểm thử quy trình và chọn cấu hình batch trước rollout.

## 10. Rollback bằng OSD sạch chạy bản cũ

Rollback thực hiện bằng cách loại OSD X gặp vấn đề và thêm OSD sạch R chạy image cũ tương thích. Không mở BlueStore đã được bản mới sử dụng bằng binary cũ như một thao tác downgrade mặc định.

| Giai đoạn | Thực hiện |
|---|---|
| HOLD | Dừng mở rộng batch/return, ghi tình trạng X và các PG liên quan |
| Giữ dịch vụ | Giữ PG trên S/các replica còn lại; stop hoặc cô lập X theo mức độ sự cố và safety plan |
| Kiểm khả năng thay | Xác nhận bản sao còn lại, capacity, image cũ, thiết bị R và feature/release compatibility |
| Loại X | Drain nếu còn cần và dữ liệu đọc được; chỉ destroy/purge/zap hoặc tháo vĩnh viễn khi safe-to-destroy và điều kiện dữ liệu đạt |
| Thêm R | Prepare/activate trên thiết bị sạch và chạy daemon bằng digest bản cũ đã chốt |
| Phục hồi | R nhận PG theo nhóm ở vai trò replica, hội tụ, deep-scrub rồi restore affinity |
| Kết thúc | Đủ replication/capacity, dịch vụ ổn định, mapping và ledger cập nhật X→R |

`ok-to-stop` và `safe-to-destroy` phục vụ hai quyết định khác nhau. Nếu còn thiếu bản sao hoặc inconsistency chưa được xử lý thì chưa hủy thiết bị. Không dùng `--force` hoặc `osd lost` để ép qua các điều kiện này.

Phải kiểm cơ chế chọn image cho cả prepare/activate và daemon; lệnh thêm OSD không tự bảo đảm dùng bản cũ. Chốt phương thức provision cụ thể trong MOP theo phiên bản cephadm và thử trước trong lab. Nếu release floor/features hiện tại không cho bản cũ tham gia thì `BLOCKED_ROLLBACK_VERSION_INCOMPATIBLE`.

Kiểm soát service spec để cephadm không tự tạo OSD ngoài kế hoạch khi ổ mới xuất hiện. R có thể dùng ID mới; nếu dùng lại ID X, phải quản lý incarnation mới và không tái dùng evidence cũ. Quy trình cephadm `--replace` giữ ID có yêu cầu host tương ứng; phương án chuyển host cần được lập riêng.

## 11. Gate và cách đọc kết quả

| Gate | Ý nghĩa |
|---|---|
| `RETURN_ALLOWED` | PA1: X sẵn sàng nhận lại PG ở vai trò replica |
| `REPLICA_ACCEPTED` | Nhóm PG đã hội tụ và deep-scrub mới đạt |
| `PRIMARY_RESTORE_READY` | Toàn return set PA1 hoặc handoff set PA2 đã kiểm, có thể khôi phục affinity theo plan |
| `COMPLETE` | PA1: nâng cấp, return, restore và quan sát ổn định hoàn tất |
| `SPARE_ADMISSION_ALLOWED` | PA2: đúng cặp U/D và revision; được bắt đầu nhóm canary |
| `HANDOFF_GROUP_ACCEPTED` | PA2: nhóm handoff đạt kiểm replica, không cấp gate cho nhóm khác |
| `HANDOFF_COMPLETE` | PA2: toàn handoff set đạt, U isolated, D đã restore affinity và ổn định |
| `SPARE_ROTATED` | PA2: U đã nâng, healthy/isolated; là spare candidate cho lượt kế tiếp |
| `WAVE_COMPLETE` | PA2: version coverage, end-state policy, ledger và stable window hoàn tất |
| `QOS_RESULT` | Kết quả của workload và các cửa sổ đã đo; tùy chọn |

HOLD khi có lỗi thực hoặc vượt stop policy; BLOCKED khi thiếu điều kiện thực hiện; INCONCLUSIVE khi bằng chứng không đủ để kết luận. Benchmark không bật thì `NOT_REQUESTED`. Mỗi PASS giới hạn trong scope và thời gian đã quan sát.

## 12. Evidence và bài lab bổ sung

Báo cáo production gồm baseline, X/S/R, version/digest, mapping trước/trong/sau, down-set gate, nhóm return/handoff, scrub coverage, affinity, ledger, cửa sổ ổn định và rollback nếu có.

Báo cáo QoS nếu bật gồm workload/asset, profile, BEFORE/DURING/AFTER, REMAP/NEIGHBOR/CONTROL, proof level, raw client logs, telemetry, mức thay đổi và giới hạn phép đo.

PA2 bổ sung strategy/chain/rotation-step ID, U/D và incarnation, initial/final spare, handoff groups, placement đích, ownership của override và version coverage toàn wave. So sánh hai phương án theo cùng workload và phạm vi nâng; không coi tải trên cùng một OSD là cùng workload khi PA2 đã đổi dữ liệu mà OSD giữ. AFTER dùng `AFTER_RETURN_STABLE` cho PA1 hoặc `AFTER_WAVE_STABLE` cho PA2 khi đã đáp ứng stable-window policy.

Hướng dẫn kiểm đọc/ghi và so checksum trực tiếp trên PG lab nằm riêng tại [PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md). Ba tài liệu chính chỉ tham chiếu kết quả nếu bài lab được chạy; không yêu cầu chuẩn bị hạ tầng kiểm thử riêng để vận hành PA1 hoặc PA2.

## 13. PA2 — Rotating spare

### 13.1. Phạm vi và luồng

PA2 là quy trình điều phối trên placement và recovery/backfill của Ceph, không phải một lệnh swap OSD có sẵn. Mỗi chuỗi nằm trong **một hop phiên bản**; phải hoàn tất điều kiện của hop trước khi chuyển sang bản đích tiếp theo.

| Lượt | Handoff dữ liệu | OSD được nâng sau khi drain | Spare candidate mới |
|---|---|---|---|
| Khởi tạo | Chuẩn bị S và kiểm bản đích, health, capacity, placement | S nếu chưa chạy bản đích và không phục vụ PG | S |
| 1 | X→S | X | X |
| 2 | Y→X | Y | Y |
| Tiếp theo | Z→Y | Z | Z |

Sau lượt 2, S tiếp tục giữ các PG nhận từ X; X giữ các PG nhận từ Y. Mỗi OSD giữ ID/incarnation riêng, không đổi tên hoặc giả danh OSD nguồn. Spare mới nghĩa là không còn PG phục vụ trong scope; vẫn kiểm dung lượng thực và không giả định thiết bị đã được xóa sạch.

### 13.2. Điều kiện chọn nguồn và đích

- D phải chạy đúng version/digest đích, daemon khỏe và được giữ ngoài production placement chưa admit. Nếu S ban đầu chưa ở bản đích, chuẩn bị/nâng S trước handoff đầu và tính vào version coverage.
- D đủ dung lượng, DB/WAL, CPU, disk/network headroom và thuộc CRUSH root/device class phù hợp của từng pool. Kiểm đủ failure domain và dự phòng N+1 cho toàn maintenance set.
- Từng PG chuyển phải có placement hợp lệ sau thay U bằng D; không tạo bản sao trùng OSD hoặc trùng failure domain. Một OSD trống không mặc nhiên thay được bất kỳ OSD nào.
- Kiểm mọi pool/PG liên quan, các override đang tồn tại, dịch vụ balancer/autoscaler và thay đổi topology. Primary-affinity bằng 0 không ngăn nhận PG.
- Nếu một D không đáp ứng toàn bộ nguồn, lập tập đích/chuỗi khả thi khác hoặc ghi BLOCKED; không nới CRUSH/min_size để hoàn thành chuỗi vẽ trước.

Danh sách X, Y, Z là plan có revision, không phải thứ tự cố định bất chấp inventory. Với nhiều chuỗi, reserve OSD và tài nguyên; đích đang nhận dữ liệu không đồng thời được chọn để nâng ở chuỗi khác.

### 13.3. Một lượt U→D

| Bước | Thực hiện | Điều kiện chuyển tiếp |
|---|---|---|
| 1. Plan lượt | Chốt U/D, handoff set, mapping, version, affinity và nguồn phục hồi | `SPARE_ADMISSION_ALLOWED` cho đúng cặp U/D và revision |
| 2. Canary handoff | Giữ D không làm primary, giảm primary duty U theo plan, chuyển một nhóm nhỏ PG U→D | Mapping thực hội tụ; D replica; PG active+clean |
| 3. Kiểm nhóm | Deep-scrub mới sau catch-up, kiểm lỗi và QoS vận hành | `HANDOFF_GROUP_ACCEPTED`; lỗi/thiếu evidence thì HOLD/BLOCKED |
| 4. Mở rộng | Lặp handoff và kiểm theo nhóm đến hết set | Tất cả nhóm đạt; U vắng trong up/acting của toàn inventory scope |
| 5. Bàn giao D | Kiểm toàn membership D; khôi phục affinity về policy đích và quan sát ổn định | `HANDOFF_COMPLETE`; không chỉ dựa vào nhóm canary đầu |
| 6. Nâng U | Recheck down set, N+1, capacity, ok-to-stop rồi redeploy U | U lên đúng digest, không lỗi liên quan, isolation còn đúng |
| 7. Chuyển vai | Ghi U thành spare candidate; D tiếp tục phục vụ PG đã nhận | `SPARE_ROTATED`; lượt kế tiếp phải kiểm admission lại với nguồn mới |

Các PG bàn giao vẫn phục vụ client trong giới hạn khả dụng của Ceph; chuyển membership có thể gây peering, backfill và I/O stall. Không cam kết zero pause hoặc QoS không đổi.

`SPARE_ADMISSION_ALLOWED` chỉ cho phép bắt đầu nhận nhóm canary. Nó không xác nhận D đã được kiểm với toàn bộ dữ liệu. X sau nâng có thể được kiểm bằng PG từ Y; không cần trả PG cũ từ S về X để tạo bước kiểm replica.

Deep-scrub bao phủ mọi PG trong handoff set theo policy chung, không dùng PASS của nhóm đầu cho các nhóm sau. Khi lỗi xuất hiện sau một nhóm đã đạt, đánh giá lại nhóm bị ảnh hưởng trước hành động tiếp theo.

### 13.4. Mapping, pause/resume và kết thúc wave

Lưu mapping trước/hiện tại/đích của **từng PG**, incarnation, owner và chặng phụ thuộc. Khi cùng PG xuất hiện ở nhiều lượt, tính lại toàn mapping hợp lệ từ trạng thái thực; không nối chuỗi thay thế ID hoặc xóa override của lượt trước một cách máy móc.

Mỗi thay đổi được phân loại: cấu hình tạm cần restore; placement sẽ giữ và bàn giao; hoặc thay đổi phải reconcile theo end-state plan. Với PA2, baseline lịch sử có thể khác desired end state. Bật lại balancer/autoscaler có thể tạo chuyển động dữ liệu; phải ghi nhận và theo dõi hội tụ.

Wave chốt một trong hai chính sách, không chọn sẵn:

- `KEEP_ROTATED_PLACEMENT`: giữ placement sau xoay đã được kiểm hợp lệ; bàn giao owner và cấu hình vận hành, không xóa các override cần thiết để giữ placement đó.
- `RECONCILE_TO_POLICY`: đưa placement về policy đích đã chốt, có thể gồm placement cũ; lập kế hoạch chuyển động bổ sung và tính đầy đủ vào chi phí/thời gian đo.

Pause/HOLD dừng mutation tiếp theo, giữ các nhóm đã bàn giao trên các OSD hiện đang phục vụ. Resume đọc lại mapping, version, incarnation, ownership và evidence; không chạy tiếp chỉ dựa vào con trỏ lượt.

`WAVE_COMPLETE` yêu cầu mọi OSD trong scope, gồm S ban đầu và spare cuối, đúng bản đích; mọi handoff set đã được kiểm; end state/ownership/cấu hình đã bàn giao; PG/health/QoS đạt stable-window policy. Spare cuối chưa nhận PG sau nâng phải ghi `replica_validation=NOT_EXERCISED`; không cấp REPLICA_ACCEPTED cho dữ liệu chưa từng kiểm.

### 13.5. Xử lý lỗi và phục hồi

Lỗi D hoặc U làm HOLD chuỗi liên quan; xác định PG và bản sao còn lành từ trạng thái hiện tại. Không mặc định U vẫn giữ bản sao đầy đủ sau drain, và không coi S ban đầu là backup cho mọi lượt sau.

Nếu cần quay về binary cũ, áp dụng replacement bằng R sạch và điều kiện tương thích ở mục 10 cho OSD thực sự bị lỗi. Không tự đảo toàn chuỗi, nạp OSDMap cũ hoặc mở store đã nâng bằng binary cũ. Các chặng không bị ảnh hưởng chỉ tiếp tục sau khi maintenance set và QoS được đánh giá lại.

Nếu hết cửa sổ bảo trì hoặc chưa chọn được nguồn tiếp theo, giữ checkpoint hợp lệ và ghi rõ phần wave chưa hoàn tất. Không cần trả PG về vị trí cũ chỉ để báo dừng.

## 14. So sánh PA1 và PA2

| Tiêu chí | PA1 — Drain và return | PA2 — Rotating spare |
|---|---|---|
| Luồng dữ liệu | X→S; nâng X; S→X | X→S; nâng X; Y→X; nâng Y; tiếp tục xoay |
| PG kiểm trên OSD vừa nâng | PG thuộc return set, thường là PG trước đó của X | PG của nguồn kế tiếp được admit vào X |
| Điều kiện kiểm replica | Catch-up, actual replica, deep-scrub mới cho mọi PG được admit trước restore affinity | Cùng điều kiện; áp dụng cho handoff set |
| Sử dụng spare | S được giải phóng sau return và có thể dùng cho run tiếp theo | Vai spare chuyển sang nguồn vừa drain và nâng |
| Di chuyển dữ liệu cơ bản | Có lượt chuyển đi và chuyển về cho mỗi OSD | Không bắt buộc lượt trả lại ngay; có thể phát sinh reconcile cuối wave |
| Placement cuối đợt | Return/restore theo baseline hoặc plan của từng run | Thường khác baseline; phải chốt và bàn giao end-state policy |
| Ràng buộc topology/capacity | Cặp X/S và đường return phải khả thi | Mỗi cặp nguồn/đích liên tiếp phải khả thi; spare thay đổi theo chuỗi |
| Quản lý trạng thái | Theo từng run X, vẫn kiểm tương tác giữa các batch | Theo từng lượt và cả chuỗi; lưu dependency/ownership lâu hơn |
| Pause và xử lý lỗi | Dừng tại drain/return group, giữ nguồn phục hồi hợp lệ | Dừng tại handoff checkpoint, đánh giá mapping hiện tại của các lượt đã bàn giao |
| Song song | Bị giới hạn bởi spare, PG overlap, down set và QoS | Bị giới hạn tương tự và thêm dependency trong từng chuỗi; nhiều chuỗi cần spare/tài nguyên riêng |
| Ảnh hưởng QoS | Do drain, return, peering, scrub và tranh tài nguyên | Do handoff, peering, scrub và reconcile; cần đo, không suy tốt hơn chỉ từ số lượt |
| Phạm vi áp dụng tài liệu | Replicated pool trên Pacific | Cùng phạm vi; EC chưa được đặc tả/kiểm chứng trong bộ này |

Ước lượng đơn giản: nếu tổng dung lượng các bản PG cần chuyển khỏi các OSD nguồn là D, PA1 có thể khoảng 2D cho đi/về, PA2 khoảng D khi giữ placement sau xoay. Đây là mô hình lập kế hoạch với dung lượng tương đương và không có chuyển động bổ sung; không phải số đo hoặc cam kết giảm 50% thời gian/QoS. Ghi mới, retry, recovery, balancer và reconcile làm số thực tế khác đi. Nếu trả toàn bộ placement cũ ở cuối PA2, phải cộng phần di chuyển đó.

So sánh thực nghiệm dùng cùng phạm vi phiên bản/OSD/dữ liệu, workload, failure-domain policy và budget. Báo riêng: bytes thực chuyển, PG/member/primary changes, thời gian backfill, scrub, thời gian toàn run/wave, p50/p95/p99, offered/completed IOPS, error/timeout, I/O stall, SLO violation và thời gian phục hồi ổn định. Dữ liệu không tương đương thì ghi giới hạn hoặc NOT_COMPARABLE; không xếp hạng hai phương án từ số đo thiếu.

Bảng này mô tả đánh đổi, không chỉ định phương án mặc định. Việc chọn PA1 hoặc PA2 là trường cấu hình của kế hoạch cụ thể.

## 15. Tài liệu kỹ thuật đối chiếu

Các gate, state và thuật ngữ workflow trong bộ tài liệu là quy ước của ứng dụng. Adapter cần kiểm khả năng CLI/schema trên đúng phiên bản triển khai.

- [Ceph Pacific — Primary affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity).
- [Ceph Pacific — PG upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/).
- [Ceph Pacific — Scrubbing](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/).
- [Ceph Pacific — PG consistency và repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/).
- [Ceph Pacific — OSD service và replacement](https://docs.ceph.com/en/pacific/cephadm/services/osd/).
- [Ceph Pacific — Safe-to-destroy](https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/#replacing-an-osd).

- [Ceph Pacific — PG states](https://docs.ceph.com/en/pacific/rados/operations/pg-states/).
- [Ceph Pacific — CRUSH và failure domain](https://docs.ceph.com/en/pacific/rados/operations/crush-map/).
