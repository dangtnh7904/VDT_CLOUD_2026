# Báo cáo kết quả nghiên cứu và kế hoạch lab nâng cấp Ceph đến cuối tháng 11 năm 2026

**Ngày cập nhật:** 02/10/2026  
**Đối tượng:** lãnh đạo và quản lý kỹ thuật nội bộ  
**Phạm vi:** kết quả đã thực hiện, tiến độ diff Quincy, kế hoạch MOP lab đến Reef 18.2.7 và prototype H0  
**Thời lượng:** 18 slide, khoảng 15–16 phút trình bày và 3–4 phút hỏi đáp  
**Lời thuyết trình:** [02_Loi_thuyet_trinh_Ceph_va_H0.md](./02_Loi_thuyet_trinh_Ceph_va_H0.md)

Đến cuối tháng 11/2026, mục tiêu bàn giao gồm bộ MOP đã chạy kiểm chứng trên lab qua từng chặng đến **18.2.7**, hồ sơ nghiệm thu nâng cấp và **lab H0 có demo, mã nguồn cùng bằng chứng kiểm thử**. Phạm vi H0 đầu tiên đề xuất là replicated RADOS, object bất biến và full-object write. H0-W L1 và H0-R là hai hạng mục prototype cần kiểm chứng. L2/L3 cùng tích hợp tổng quát RGW/RBD/EC thuộc phần mở rộng sau prototype.

Trạng thái hiện tại lấy từ hồ sơ trong workspace: phân tích Pacific đã hoàn tất acceptance của bộ báo cáo, diff Quincy đang tiếp tục, hồ sơ ngày 01/10 ghi MGR và một OSD đã lên 16.2.15. MON cùng các pha còn lại cần chạy và nghiệm thu. H0 hiện là thiết kế nghiên cứu trong `h0-new.md`, chưa có kết quả triển khai.

## Mục lục trình bày

| Slide | Nội dung | Thời gian |
| ---: | --- | ---: |
| 1 | Tiến độ hiện tại và đầu ra cuối tháng 11 | 30 giây |
| 2 | Kết quả phân tích Pacific | 40 giây |
| 3 | Tiến độ phân tích Quincy | 45 giây |
| 4 | Kết quả lab và vấn đề monitoring | 50 giây |
| 5 | Công cụ web kiểm thử RBD và RGW | 40 giây |
| 6 | Hồ sơ MOP hiện có và phần cần hoàn thành | 35 giây |
| 7 | Lộ trình lab đến 18.2.7 | 40 giây |
| 8 | Trình tự và gate trong MOP | 45 giây |
| 9 | PA1 trong pha nâng OSD | 55 giây |
| 10 | Bài toán kiểm chứng của H0 | 55 giây |
| 11 | Reference và thành phần H0 | 65 giây |
| 12 | H0-W L1 L2 L3 và điều kiện ACK | 80 giây |
| 13 | H0-R tại checkpoint PA1 | 70 giây |
| 14 | Phạm vi lab H0 cuối tháng 11 | 65 giây |
| 15 | Kiểm thử và đo chi phí H0 | 45 giây |
| 16 | Kế hoạch tháng 10 và tháng 11 | 55 giây |
| 17 | Phụ thuộc và xử lý khi gate không đạt | 45 giây |
| 18 | Bộ đầu ra và tiêu chí bàn giao | 40 giây |

## Phần I Kết quả đã thực hiện và công việc đang triển khai

### Slide 1 Tiến độ hiện tại và đầu ra cuối tháng 11

**Nội dung trên slide**

**Nghiên cứu và lab nâng cấp Ceph**

- Đã hoàn thành bộ phân tích Pacific 16.2.5 đến 16.2.15.
- Đang diff Pacific 16.2.15 với Quincy 17.2.7.
- Hồ sơ lab ghi MGR và một OSD đã ở 16.2.15.
- Đã có web kiểm thử RBD/RGW và hồ sơ MOP từng thành phần.

**Mục tiêu 30/11/2026:** MOP lab đã kiểm chứng đến **18.2.7** và **lab prototype H0**.

**Minh chứng dùng khi trình bày:** mục lục comparison, hồ sơ MOP ngày 01/10 và màn hình web hiện có. Nguồn [N1], [N2], [N3], [N4].

### Slide 2 Kết quả phân tích Pacific

**Nội dung trên slide**

| Hạng mục | Kết quả |
| --- | --- |
| Cặp phiên bản | 16.2.5 và 16.2.15 |
| Net diff | 2.665 file thay đổi |
| Hồ sơ phân tích | Inventory và 15 cặp báo cáo Markdown/CSV |
| Kiểm tra hồ sơ | Partition, ledger và cross-reference qua acceptance |
| Đầu ra phục vụ nâng cấp | Checklist và kịch bản kiểm theo thành phần |

**Các điểm đưa vào MOP:** mixed-version, monitoring, migration state, config, client và artifact.

**Minh chứng:** cây thư mục và một finding có đường dẫn mã nguồn, điều kiện kích hoạt, bài kiểm tương ứng. Số file biểu thị phạm vi nghiên cứu. Acceptance ở đây áp dụng cho hồ sơ phân tích. Nguồn [N1].

### Slide 3 Tiến độ phân tích Quincy

**Nội dung trên slide**

**16.2.15 và 17.2.7: đã có inventory 4.179 file và 15 cặp báo cáo**

| Nhãn hiện tại | Số file |
| --- | ---: |
| `affect` | 852 |
| `trivial` | 522 |
| Chưa phân loại tác động | 2.805 |

- Tiếp tục rà MGR, client, CephFS, RGW, build và validation.
- Kiểm backport riêng của Pacific vì hai endpoint thuộc release branch khác nhau.
- Đóng binary gate toàn suite trước khi chốt checklist U2.

**Trạng thái:** đang phân tích, strict binary gate chưa đạt.

**Minh chứng:** PLAN/README và ledger component. Số liệu là snapshot hồ sơ ngày 02/10, không dùng làm số lỗi của Ceph. Nguồn [N2].

### Slide 4 Kết quả lab và vấn đề monitoring

**Nội dung trên slide**

| Hạng mục | Kết quả trong hồ sơ |
| --- | --- |
| OSD thử nghiệm | osd.1 lên 16.2.15, báo cáo 16/16 mẫu khớp checksum |
| MGR | Hồ sơ 01/10 ghi đã lên 16.2.15 |
| Prometheus | Target UP, nhận sample mới |
| Format metrics | Duplicate `HELP/TYPE`, `promtool` trả lỗi |
| MON và toàn cluster | Có MOP/gate, cần chạy và nghiệm thu |

**Việc tiếp theo:** xác nhận inventory mới, hoàn tất gate MGR, xử lý monitoring và chạy MOP MON.

**Minh chứng:** log version/image, checksum corpus và kết quả parser. `test-gate.md` mới ghi kết quả G4.1 và hướng dẫn cho các gate sau, chưa chứng minh toàn bộ MGR acceptance đã PASS. Nguồn [N3], [N5], [N6].

### Slide 5 Công cụ web kiểm thử RBD và RGW

**Nội dung trên slide**

- RGW: workload, điều khiển job và telemetry.
- RBD: lifecycle, file browser/terminal, baseline và verify.
- Validation 24/09: **73 backend, 14 Node, 4 frontend tests PASS**.
- RBD live: baseline **4 file**, phát hiện overwrite, khớp lại sau restore.

**Phần tiếp tục phát triển:** scope OSD/PG, capability H0, receipt và coverage.

**Minh chứng:** ảnh web thật và một validation run. Validation 24/09 kiểm lifecycle/remount, chưa chạy nâng phiên bản Ceph. Các ma trận RGW và telemetry có phần còn PARTIAL/NOT_RUN. Nguồn [N4].

### Slide 6 Hồ sơ MOP hiện có và phần cần hoàn thành

**Nội dung trên slide**

| Đã có trong workspace | Phần cần hoàn thành |
| --- | --- |
| PRE-MOP MGR, MOP MGR/OSD/PA1 | Thống nhất MOP điều hành, baseline và evidence |
| MOP MON v2, gate MG0–MG8 | Chạy canary, rolling và nghiệm thu MON |
| Checklist Pacific theo component | Chuyển findings thành gate cho đúng lab |
| Khung nâng theo từng chặng | Hoàn thiện MOP Quincy và Reef |

**Đầu ra tiếp theo:** MOP có thao tác, expected result, gate, xử lý lỗi và evidence của từng bước.

**Minh chứng:** mục lục MOP và một cặp bước thao tác/gate. MOP MON v2 cùng gate hiện ở trạng thái chưa chạy trong tài liệu. MOP PA1 DOCX dùng drain khi X online, còn MOP Pacific Markdown cũ dùng trình tự stop-first. Cần chốt bản điều hành trước thực thi. Nguồn [N3], [N6], [N7].

## Phần II Kế hoạch đến cuối tháng 11 và lab H0

### Slide 7 Lộ trình lab đến 18.2.7

**Nội dung trên slide**

| Chặng | Phiên bản | Đầu ra nghiệm thu |
| --- | --- | --- |
| U1 | 16.2.5 đến 16.2.15 | Hoàn thành các pha còn lại của Pacific |
| U2 | 16.2.15 đến 17.2.7 | MOP và kết quả lab Quincy |
| U3 | 17.2.7 đến 18.2.7 | MOP và kết quả lab Reef |

- Nghiệm thu toàn cluster của một chặng trước chặng kế tiếp.
- Mỗi chặng giữ corpus, baseline và evidence riêng.
- Pin image digest và kiểm tương thích host/client trước chạy.

**18.2.7 là đích lab của kế hoạch này.**

**Ghi chú kỹ thuật:** kiểm RocksDB trước Quincy và BlueStore trước Reef. Pacific/Quincy/Reef đều đã EOL upstream tại ngày cập nhật. Reef đã có 18.2.8. Mốc production cần đánh giá riêng theo hỗ trợ và artifact thực tế. [Quincy upgrade notes](https://docs.ceph.com/en/latest/releases/quincy/), [Reef release notes](https://docs.ceph.com/en/latest/releases/reef/), [Ceph release lifecycle](https://docs.ceph.com/en/latest/releases/).

### Slide 8 Trình tự và gate trong MOP

**Nội dung trên slide**

| Pha cho cephadm | Gate chính |
| --- | --- |
| Preflight và baseline | FSID, runtime version, image, config, corpus, capacity |
| MGR | Active/standby, failover, module, API và monitoring |
| MON | Nâng theo lượt, giữ quorum và kiểm auth/client |
| crash và OSD | Đúng daemon, PA1/canary, native safety và QoS |
| Dịch vụ đang dùng | RGW, MDS, mirroring theo inventory |
| Cuối chặng | Version toàn cụm, dữ liệu, soak và cleanup |

**Đi tiếp khi gate đạt. Thiếu evidence thì HOLD.**

**Ghi chú kỹ thuật:** thứ tự này theo cephadm. Với MON-only ở baseline hiện tại, MOP v2 chọn redeploy từng daemon và tự áp gate. Phải kiểm đúng đường thao tác của từng chặng. `--limit` giới hạn số daemon của lượt upgrade, không đặt mức dừng đồng thời. Nguồn [N6], [N7] và [Cephadm upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/).

### Slide 9 PA1 trong pha nâng OSD

**Nội dung trên slide**

**X:** OSD cần nâng. **S:** spare nhận dữ liệu.

| Bước | Thực hiện và điều kiện |
| --- | --- |
| 1 | Giữ X online, chuyển placement sang S theo batch |
| 2 | Chờ hội tụ, đủ bản, capacity/QoS và `ok-to-stop` đạt |
| 3 | Đổi image đúng X, kiểm runtime và daemon |
| 4 | Trả batch nhỏ về X, kiểm replica rồi primary canary |
| 5 | Mở rộng return, nghiệm thu và hoàn nguyên override của run |

**Đo cả hai chiều migration và thời gian canary.**

**Minh chứng dự kiến:** mapping của cùng PG trước drain, trên S và sau return. Ghi OSDMap epoch và acting set. Trình tự ở đây theo MOP PA1 DOCX, cần đồng bộ bản MOP điều hành và xử lý bản stop-first cũ trước run. S giữ vai trò theo mapping thực tế, không mặc định còn bản mới nhất sau return. PA1 cần rehearsal riêng cho override và failure domain. Nguồn [N7].

### Slide 10 Bài toán kiểm chứng của H0

**Nội dung trên slide**

| Cơ chế hiện có | Câu hỏi H0 cần kiểm chứng |
| --- | --- |
| BlueStore checksum | Payload có khớp reference từ trước đường xử lý? |
| Scrub/deep-scrub | Đúng object, generation và participant đã kiểm? |
| Recovery/backfill | Bản local trên target sau movement có khớp reference? |
| Native completion | Đủ điều kiện integrity trước protected success? |

**Mô hình lab:** reference cho `ABC`, lỗi sau reference làm buffer thành `AXC`.

**Mục tiêu đo:** phát hiện thêm tại ranh giới nào, với chi phí bao nhiêu.

**Ghi chú kỹ thuật:** đây là mô hình lỗi để nghiên cứu. Hồ sơ chưa có bằng chứng cụm đã gặp đúng lỗi này. Reference sai từ đầu làm mất cơ sở kết luận. Native checksum/scrub vẫn hoạt động trong các bài đối chứng. Nguồn [N8] và [BlueStore checksums](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/#checksums).

### Slide 11 Reference và thành phần H0

**Nội dung trên slide**

| Thành phần | Trách nhiệm đề xuất |
| --- | --- |
| Client/adapter | Tạo `Hclient` trước primary, giữ payload/reference nhất quán |
| Descriptor/manifest | Gắn digest với object, generation, range, request và policy |
| Verifier trong Ceph | Kiểm đúng buffer, participant và operation |
| Operation state/receipt | Giữ native state, kết quả kiểm, retry và reconcile |
| Web/controller | Chọn scope, kiểm capability, hiển thị evidence |

**So sánh phải cùng representation. Digest khớp nhưng sai generation vẫn FAIL.**

**Ghi chú kỹ thuật:** H0-W cần tích hợp data path trong build Ceph thử nghiệm. Web quản lý policy và bằng chứng. Descriptor phải được bảo vệ tính toàn vẹn/quyền thay đổi. Hook minh họa trên Pacific cần rà lại đúng source tag 18.2.7 trước implementation. Nguồn [N8], mục 8 và 20.

### Slide 12 H0-W L1 L2 L3 và điều kiện ACK

**Nội dung trên slide**

| Level đề xuất | Điều kiện bổ sung trên đường ghi |
| --- | --- |
| L1 | Final buffer tại primary khớp `Hclient` trước submit |
| L2 | L1 và buffer của mọi replica bắt buộc khớp reference |
| L3 | L2 và local read-back sau commit tại primary cùng replica bắt buộc |

**Protected success = native durable completion đạt + hợp đồng hợp lệ + đủ check của level.**

- Thiếu capability/evidence: giữ trạng thái lỗi hoặc chưa xác định.
- Đã commit, chưa verify: cần reconcile.
- ACK gate và quyền read generation mới là hai hợp đồng riêng.

**Ghi chú kỹ thuật:** `min_size` không thay tập participant của H0. L3 yêu cầu reader đúng generation/range và có hợp đồng cache rõ ràng. L2/L3 cần capability trên mọi participant bắt buộc. Request đã nhận ở một level không được âm thầm hạ level. Tên level, trạng thái và receipt là thiết kế dự án. Nguồn [N8], mục 9, 12, 17–19.

### Slide 13 H0-R tại checkpoint PA1

**Nội dung trên slide**

| Mốc | Bằng chứng cần có |
| --- | --- |
| Trước movement | Corpus bất biến, generation và `H0-static` |
| Sau X sang S | Mapping và native recovery/backfill hội tụ |
| Sau batch return về X | Mapping hội tụ, đọc local đúng X, so reference |
| Trước primary canary/mở rộng | Receipt đủ scope và gate dịch vụ/QoS đạt |

**`RETURN_VERIFIED` là nhãn receipt đề xuất, chỉ áp dụng cho object/generation/target đã kiểm.**

**`active+clean` cần đi cùng bằng chứng local.**

**Ghi chú kỹ thuật:** prototype nghiệm thu H0-R tại X sau return. Chứng nhận S sau drain cần receipt local S riêng. Client GET có thể đọc peer khác, nên không chứng nhận bản local X bằng một GET khớp checksum. Baseline từ dữ liệu đã lưu chỉ chứng minh tính không đổi từ checkpoint. Local reader là phụ thuộc phải nghiệm thu. Nguồn [N8], mục 8, 14, 20 và F19/F20.

### Slide 14 Phạm vi lab H0 cuối tháng 11

**Nội dung trên slide**

| Hạng mục | Phạm vi prototype đề xuất |
| --- | --- |
| Nền tảng | Build thử nghiệm từ tag 18.2.7, lab/clone riêng |
| Dữ liệu | Replicated RADOS, object ID mới, full-object write, khóa writer trong cửa sổ kiểm |
| H0-W | L1 tại primary và protected ACK gate |
| H0-R | Corpus tĩnh, đọc local X sau return PA1 |
| Bằng chứng | Reference, receipt, ca đúng/ca lỗi và số đo overhead |

**Gate 25/10:** build chạy được, chốt descriptor transport, hook/gate và phương án reader trên tag 18.2.7.

**Mở rộng sau prototype:** L2/L3, H0-READ, RGW/RBD, EC và partial write.

**Ghi chú kỹ thuật:** lab H0 có artifact riêng với upstream image dùng chạy MOP. Pool/namespace dành riêng có writer được kiểm soát và object ID mới cho mỗi logical write. Trong protected scope, từ chối overwrite/delete/partial write và profile chưa hỗ trợ. Retry cùng operation được xử lý theo identity. Client đến OSD phải có transport/descriptor contract, capability negotiation và phản hồi rõ cho protected request không hỗ trợ. Bản đầu cần lưu hoặc phục hồi verification state, xử lý retry/failover theo hợp đồng đã công bố. Nguồn thiết kế [N8]. Phạm vi và deadline là đề xuất kế hoạch.

### Slide 15 Kiểm thử và đo chi phí H0

**Nội dung trên slide**

| Nhóm bài thử | Điều kiện đạt |
| --- | --- |
| Write đúng/sai, identity sai | Đúng stage phát hiện, không false success trong bộ test |
| Native failure, timeout, retry/crash | Không trả protected success khi chưa đủ điều kiện |
| H0-R target sai, đọc nhầm peer | Không cấp `RETURN_VERIFIED` sai scope |
| Đối chứng | Upstream, build H0-off và L1 cùng workload |
| Chi phí | p95/p99, throughput, CPU, I/O, network và headroom |

**Chốt budget trước run, giữ native checks và mọi failed attempt.**

**Ghi chú kỹ thuật:** L2/L3 chỉ thêm vào đối chứng khi có implementation đủ capability. Fault injection ghi vị trí so với native/H0 verifier và lớp nào phát hiện trước. Chưa có số đo để kết luận overhead thấp. Nguồn [N8], mục 23–25.

### Slide 16 Kế hoạch tháng 10 và tháng 11

**Nội dung trên slide**

| Mốc dự kiến | MOP và lab nâng cấp | Prototype H0 |
| --- | --- | --- |
| 02–11/10 | Inventory mới, gate MGR, MON và hoàn tất U1 | Chốt scope, source review 18.2.7 |
| 12–25/10 | Đóng diff Quincy, checklist U2, preflight Reef | Build thử nghiệm, descriptor, hook L1, reader |
| 26/10–08/11 | Chạy U2, nghiệm thu Quincy, hoàn thiện MOP U3 | Tích hợp L1, state/receipt và H0-R |
| 09–18/11 | Chạy U3, kiểm dịch vụ/dữ liệu trên 18.2.7 | Kiểm ACK, retry/crash và local X sau return |
| 19–25/11 | Rehearsal xử lý lỗi, chạy lại, chốt MOP | Fault matrix, đo overhead, đóng lỗi |
| 26–30/11 | Bàn giao MOP và evidence nâng cấp | Bàn giao lab/demo H0 và kết quả đánh giá |

**Điều kiện:** lab, spare, artifact và môi trường build sẵn sàng. Gate không đạt được xử lý trước khi mở rộng.

**Ghi chú kế hoạch:** đây là lịch đề xuất để đạt mốc 30/11. Công việc source/build và phân tích có thể thực hiện trong thời gian chờ lab. Mỗi cluster chỉ có một luồng thay đổi tại một thời điểm. H0 thử trên clone/lab riêng.

**Gate review kỹ thuật:**

| Mốc | Điều kiện review |
| --- | --- |
| 25/10 | Quincy strict binary gate đạt mới mở U2. H0 build chạy từ tag đích, chốt descriptor transport/capability, PoC hook và đường local reader |
| 08/11 | U2 đạt acceptance. L1 có trace reference/buffer/ACK, native failure không success, reader X được qualification |
| 18/11 | U3 đạt acceptance. H0 F10–F14 xử lý crash/retry/failover trong scope, F19/F20 không chứng nhận nhầm target |
| 25/11 | Demo chạy lại được, số đo đối chứng, state/evidence và lỗi còn mở có disposition |

Diff/checklist, artifact và nghiệm thu từng chặng là critical path của MOP. Build/transport, ACK gate và reader là critical path của H0. Người thực hiện chịu trách nhiệm tổng hợp tiến độ, người review kỹ thuật kiểm evidence tại từng gate. Nếu gate 25/10 chưa đạt, giữ HOLD cho phần phụ thuộc và điều chỉnh lịch trong review trước khi mở U2 hoặc mở rộng H0. Patch/PoC chưa đủ điều kiện vẫn ghi đúng trạng thái. Chỉ nghiệm thu lab H0 khi đủ scope đã chốt.

### Slide 17 Phụ thuộc và xử lý khi gate không đạt

**Nội dung trên slide**

| Phụ thuộc/rủi ro | Cách xử lý trong kế hoạch |
| --- | --- |
| 2.805 file Quincy chưa phân loại | Đóng owner còn lại, findings và strict gate trước U2 |
| Monitoring format issue | Giữ finding mở, sửa/mitigate hoặc có observer thay thế đã kiểm |
| Spare/host/image không phù hợp | Kiểm capacity, failure domain, kernel và image digest trước run |
| H0 hook/reader chưa đủ hợp đồng | Rà source, kiểm riêng, giữ verdict chưa đủ evidence |
| Fault/retry chưa đạt | HOLD mở rộng, giữ state/reference và điều tra |

**Nguồn lực cần bố trí:** lab ổn định, máy build, clone/snapshot phục hồi và review kỹ thuật tại các gate.

**Ghi chú kỹ thuật:** dừng rollout, giữ dịch vụ trên mapping còn tốt, restore dữ liệu và downgrade image là các thao tác khác nhau. Recovery phải theo rehearsal và ranh giới migration của đúng chặng. Nguồn [N1], [N2], [N6], [N8].

### Slide 18 Bộ đầu ra và tiêu chí bàn giao

**Nội dung trên slide**

**Mục tiêu bàn giao ngày 30/11/2026**

| Đầu ra | Tiêu chí hoàn thành |
| --- | --- |
| MOP lab đến 18.2.7 | Đủ ba chặng, thao tác/gate và hồ sơ run |
| Kết quả nâng lab | Runtime version/image đúng, dịch vụ/dữ liệu và soak đạt |
| Lab H0 | Demo L1 và H0-R đúng scope, mã nguồn/build, receipt và test report |
| Báo cáo đánh giá | Chi phí, failure handling, coverage và phần còn mở |

**Đề xuất chốt:** phạm vi lab, nguồn lực và mốc review **25/10, 08/11, 25/11**.

**Minh chứng khi bàn giao:** log thực thi và artifact. Tại thời điểm báo cáo, các đầu ra cuối tháng 11 là mục tiêu triển khai.

## Phụ lục A Tiêu chí nghiệm thu chi tiết

### MOP và lab nâng cấp

1. Mỗi chặng có inventory đầu/cuối, version runtime, image digest và service inventory. Daemon đã đúng target được kiểm lại theo baseline thực tế.
2. MOP ghi thao tác, expected result, timeout, gate PASS/HOLD/FAIL/N/A, người thực hiện và đường dẫn evidence. Mỗi N/A có lý do theo inventory.
3. Quorum, PG, native safety, client I/O và integrity đạt theo gate đã chốt trước run. Warning cũ có disposition, warning mới có điều tra.
4. Kiểm dữ liệu cũ bằng corpus/version cố định và kiểm ghi/đọc mới trên release đích. Kết quả giữ đúng scope đã quan sát.
5. PA1 có mapping/epoch, capacity/QoS, drain, restart, return canary và cleanup. Coverage ghi cả chiều X sang S và chiều trả về X.
6. Có rehearsal xử lý daemon lỗi và phục hồi lab. Chỉ nghiệm thu restore/downgrade đã thực sự thử trong đúng ranh giới dữ liệu/migration.
7. Chặng sau chỉ bắt đầu sau nghiệm thu chặng trước. Cuối U3, toàn bộ daemon trong phạm vi nâng chạy artifact 18.2.7 đã xác minh.

### Lab prototype H0

1. Pin source tag 18.2.7, commit patch, build và container digest. Phân biệt build H0 với upstream image của MOP.
2. Công bố operation profile: new immutable RADOS object, full-object write, replicated pool healthy với tập participant xác định. Dùng pool/namespace dành riêng, object ID mới cho mỗi logical write và kiểm soát writer. Từ chối protected operation overwrite/delete/partial write hoặc profile ngoài phạm vi; retry giữ identity riêng. Corpus bất biến trong cửa sổ H0-R.
3. Reference tạo trước primary, gắn object/generation/range/request/policy. Có transport/descriptor contract và capability từ client đến OSD, phản hồi rõ khi protected request không được hỗ trợ. Chứng minh buffer được hash là buffer của mutation được submit.
4. L1 có verifier tại final primary buffer và gate tích hợp native completion. Receipt giữ requested/satisfied level, stage/result, native state và client result.
5. Retry cùng identity/payload có hành vi xác định. Retry cùng identity nhưng khác payload bị phát hiện. Duplicate/native commit không tự tạo H0 success.
6. Crash/failover giữ hoặc khôi phục verification state. Khi chưa xác định được kết quả thì reconcile hoặc trả trạng thái chưa giải quyết, không false success.
7. H0-R có reader đọc local đúng X sau return, đúng generation và reference bất biến. Target mismatch hoặc client đọc peer khác không được cấp nhãn receipt `RETURN_VERIFIED` cho X. Kiểm S sau drain, nếu thêm, có scope và receipt riêng.
8. Giữ evidence mismatch đầu tiên. Bộ test có ca đúng, fault injection tại ranh giới khai báo, native failure, thiếu reference/capability và các ca retry/crash trong phạm vi.
9. Đo upstream, H0-off và L1 ở cùng workload/topology. Budget, số mẫu, warm-up và coverage được ghi trước run. Báo lỗi/timeout và achieved throughput cùng latency.
10. Bàn giao demo chạy lại được, mã nguồn, image, manifest/receipt, hướng dẫn lab và báo cáo phần chưa hỗ trợ.

## Phụ lục B Phạm vi nghiên cứu H0 sau prototype

| Hạng mục | Điều kiện bổ sung trước nghiệm thu |
| --- | --- |
| L2 | Protocol/reference/result binding, verifier mọi replica bắt buộc, participant đổi và failover |
| L3 | Local read-back sau commit, generation/range, reader/cache qualification, state sau crash |
| H0-READ | Reference được giữ theo vòng đời dữ liệu và đúng hợp đồng full/range/streaming |
| RGW | Mapping head/tail/multipart, version ID, API completion và publication |
| RBD | Extent/snapshot, write cache, flush/durability, ordering và concurrent overwrite |
| EC | Logical reference, codeword/shard identity, parity, reconstruction và partial/RMW contract |
| Production | Nhu cầu workload, lợi ích bổ sung, overhead, availability, hỗ trợ và bảo trì |

H0-R, H0-W và H0-READ có hợp đồng kiểm riêng. Hash file qua RBD hoặc GET object qua RGW có giá trị ở lớp client, cần thêm bằng chứng để chứng nhận một OSD/replica cụ thể.

## Phụ lục C Nguồn và phạm vi bằng chứng

| Mã | Nguồn trong workspace | Nội dung dùng trong báo cáo |
| --- | --- | --- |
| N1 | [Pacific comparison README](./comparison/pacific-16.2.5-to-16.2.15/README.md) | 2.665 file, 15 component, acceptance hồ sơ và các finding |
| N2 | [PLAN Quincy](./comparison/PLAN-pacific-16.2.15-to-quincy-17.2.7.md), [README Quincy](./comparison/pacific-16.2.15-to-quincy-17.2.7/README.md) | 4.179 file, 852 affect, 522 trivial, 2.805 chưa phân loại |
| N3 | [MOP MON v2](./MOP/MOP-MON-16.2.5-to-16.2.15-v2.md), mục 1 | Hồ sơ 01/10 ghi MGR và một OSD đã nâng, tiếp nối ở MON |
| N4 | [Web VALIDATION](./code/rgw-console/VALIDATION.md), [Web README](./code/rgw-console/README.md) | Validation 24/09, chức năng, số test và giới hạn live |
| N5 | [MOP PA1 Canary 1 OSD Lab](./MOP/MOP_PA1_Canary_1_OSD_Lab.docx), [Báo cáo 12 slide gốc](./Bao_cao_Ceph_12_slide_va_Loi_thuyet_trinh%20%283%29.md), slide 3 | osd.1 lên 16.2.15 và `checked=16 failed=0 listed=16` trong hồ sơ thực hành |
| N6 | [test-gate.md](./test-gate.md), [Gate MON v2](./test/GATE-MON-16.2.5-to-16.2.15-v2.md) | Kết quả G4.1 monitoring và gate MON chưa chạy |
| N7 | [Plan tổng](./plan-tổng.md), [MOP PA1 Canary](./MOP/MOP_PA1_Canary_1_OSD_Lab.docx), [MOP Pacific cũ](./MOP/MOP-Ceph-Pacific-16.2.5-to-16.2.15.md), thư mục MOP | Khung U1/U2/U3, PA1 online-drain và bản stop-first cần đồng bộ |
| N8 | [h0-new.md](./h0-new.md), bản Việt v3.0 đầu tài liệu | Reference, L1/L2/L3, ACK, H0-R, capability, tests và evidence |

Số liệu Quincy khớp nhãn `upgrade_impact` của 15 CSV component tại ngày cập nhật. Hồ sơ Pacific ghi acceptance từ 17/09. Kết quả live giữ ngày và phạm vi của từng run trong nguồn.

Kết quả một OSD/16 mẫu có trong MOP PA1 DOCX và báo cáo thực hành. MOP ghi X là osd.1, S là osd.3. Lần lab đồng thời đổi phiên bản và nguồn image từ `trangtran97/ceph` sang `quay.io/ceph/ceph`, cần giữ điều kiện này khi đánh giá kết quả. Khi nghiệm thu, kèm log runtime/image và corpus/thời điểm của run. Các snapshot prelab 23/09 và web validation 24/09 có số OSD/PG khác nhau, nên không dùng chúng thay inventory mới.

Thiết kế H0 dùng phần Việt v3.0 đầu `h0-new.md`. H0-W trong kế hoạch này cần tích hợp data path của build thử nghiệm, với phạm vi prototype đã nêu ở trên.

Nguồn Ceph chính thức đã đối chiếu ngày 02/10/2026:

- [Cephadm upgrade và staggered upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/) cho thứ tự daemon và bước chuyển MGR của bản cũ.
- [Quincy release và upgrade notes](https://docs.ceph.com/en/latest/releases/quincy/) cho chuyển Pacific sang Quincy và yêu cầu RocksDB.
- [Reef release và upgrade notes](https://docs.ceph.com/en/latest/releases/reef/) cho 18.2.7, FileStore, artifact/host và cảnh báo nâng trực tiếp Pacific sang Reef.
- [Ceph release lifecycle](https://docs.ceph.com/en/latest/releases/) cho trạng thái hỗ trợ upstream.
- [BlueStore checksums](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/#checksums) cho cơ chế checksum native.

## Phụ lục D Hình và bảng minh chứng

| Slide | Minh chứng phù hợp |
| --- | --- |
| 2–3 | Mục lục suite, inventory, finding và trạng thái ledger |
| 4 | Runtime version/digest, checksum corpus, target/sample mới và lỗi promtool |
| 5 | Ảnh web RBD/RGW và validation run |
| 6–8 | Cặp thao tác/gate trong MOP, inventory từng daemon |
| 9 | Mapping cùng PG trước drain, trên S, sau return |
| 10–13 | Bảng reference, level, native state và receipt theo thiết kế |
| 14–15 | Khi lab hoàn thành: build ID, trace ACK, ca fault và số đo đối chứng |
| 16–18 | Lịch, gate review và danh sách artifact bàn giao |

Slide kết quả dùng log/ảnh thật có ngày và scope. Slide H0 hiện dùng bảng thiết kế. Biểu đồ hiệu năng và H0 PASS chỉ bổ sung sau khi có run tương ứng.
