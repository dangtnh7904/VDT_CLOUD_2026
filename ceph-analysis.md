**BÁO CÁO NGHIÊN CỨU**

**PHÂN TÍCH NÂNG CẤP CEPH
PACIFIC 16.2.5 → QUINCY → REEF 18.2.7**

Bản vá lỗi • Hiệu năng • Tính ổn định • Bảo mật • Trade-off tính năng

| **Mục tiêu**         | Đánh giá tác động đối với hạ tầng Cloud Storage và đề xuất các quyết định kỹ thuật trước nâng cấp |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Baseline**           | Ceph Pacific 16.2.5                                                                                                        |
| **Đích phân tích** | Pacific 16.2.15 → Quincy transit → Reef 18.2.7                                                                           |
| **Nguồn đầu vào**  | version_comparison.xlsx và tài liệu chính thức của Ceph                                                              |
| **Ngày tổng hợp**   | 22/08/2026                                                                                                                 |

*Tài liệu phục vụ nghiên cứu và chuẩn bị quyết định kỹ thuật; không thay thế runbook triển khai Production.*

# TÓM TẮT ĐIỀU HÀNH

> **Kết luận khuyến nghị**
>
> Không giữ 16.2.5 làm phiên bản vận hành dài hạn. Nâng trực tiếp trong nhánh Pacific lên 16.2.15, xác nhận ổn định, sau đó đi qua một mốc Quincy đã được lựa chọn theo deployment mode trước khi lên Reef 18.2.7. Với cephadm, 17.2.7 là mốc transit thực tế hơn 17.2.9 vì có official container image; 17.2.9 chỉ cân nhắc cho package-based sau khi xác minh repository và hệ điều hành.

Nâng cấp này không chỉ là thay file binary của daemon. Nó thay đổi scheduler I/O, cơ chế tự điều chỉnh bộ nhớ OSD, backend metadata được hỗ trợ, defaults của RocksDB, công cụ quan sát, hành vi RGW/CephFS/RBD và các feature bit dùng để khóa tương thích client. Vì vậy, phải đánh giá đồng thời data path, control plane, client và automation.

- Pacific 16.2.15 gom toàn bộ bản vá tích lũy từ 16.2.6-16.2.15, gồm lỗi OMAP conversion, MGR deadlock, PGLog inflation, ceph-volume activation, CVE của Manila/CephFS, ceph-crash và RGW POST policy.
- Quincy là ranh giới thay đổi hành vi lớn: mClock trở thành scheduler mặc định cho BlueStore; LevelDB bị loại; memory autotune mặc định bật; pool device_health_metrics được đổi thành .mgr.
- Reef nâng RocksDB lên 7.9.2, cho phép tuning theo column family, giảm overhead iteration/compaction và write amplification ở một số workload; nhưng không đảm bảo mọi workload đều nhanh hơn.
- Reef 18.2.5 và 18.2.6 có critical BlueStore regression; 18.2.7 sửa lỗi \_extend_log sequence và thêm các fix BlueStore/BlueFS quan trọng. Không dùng 18.2.3, không dwell ở 18.2.5/18.2.6.
- Sau QA của 18.2.8, Ceph không còn khuyến nghị nâng trực tiếp Pacific → Reef do xung đột feature bit có thể làm cảnh báo OSD_UPGRADE_FINISHED xuất hiện sớm. Đây không phải lỗi bảo mật hay bằng chứng data corruption, nhưng là lý do quản trị rủi ro để giữ hop Quincy.
- HEALTH_OK chỉ là điều kiện cần. Phải kiểm chứng latency/IOPS, recovery/backfill, scrub, log BlueStore/BlueFS, client compatibility và các luồng OpenStack trước khi GO.

Các kết luận trên dựa trên release notes, hướng dẫn upgrade và tài liệu vận hành chính thức của Ceph. **\[R1-R9\]**

# MỤC LỤC NỘI DUNG

- 1\. Mục tiêu, phạm vi và phương pháp
- 2\. Kết luận về lộ trình phiên bản
- 3\. Phân tích nhánh Pacific 16.2.5 → 16.2.15
- 4\. Phân tích nhánh Quincy và lựa chọn điểm transit
- 5\. Phân tích nhánh Reef đến 18.2.7
- 6\. Giải thích sâu các cải tiến hiệu năng
- 7\. Phân tích bản vá tính ổn định và toàn vẹn dữ liệu
- 8\. Phân tích bảo mật
- 9\. Ma trận trade-off khi bật/tắt tính năng
- 10\. Tác động đối với Cloud Storage/OpenStack
- 11\. Compatibility matrix và blocker
- 12\. Tiêu chí xác nhận lợi ích và GO/NO-GO
- 13\. Kết luận
- References
- Phụ lục A. Version ledger từ file nguồn

# 1. MỤC TIÊU, PHẠM VI VÀ PHƯƠNG PHÁP

## 1.1 Mục tiêu

Báo cáo trả lời bốn câu hỏi: (i) từ Pacific 16.2.5 đến các mốc nâng cấp đã thay đổi gì; (ii) cải tiến hoạt động theo cơ chế nào; (iii) lỗi và lỗ hổng nào đã được vá; và (iv) tính năng mới nên bật, giữ mặc định hay trì hoãn trong hạ tầng Cloud Storage.

## 1.2 Phạm vi

- Baseline: Ceph Pacific 16.2.5.
- Mốc đóng nhánh Pacific: 16.2.15.
- Hop trung gian: Quincy 17.2.x, tập trung so sánh 17.2.7 và 17.2.9.
- Đích chính: Reef 18.2.7; 18.2.8 chỉ là advisory sau target vì phát hành ngày 20/03/2026.
- Các dịch vụ chịu tác động: RADOS/OSD/BlueStore, RBD, CephFS/MDS/Manila, RGW, cephadm, monitoring và client OpenStack.

## 1.3 Phương pháp

File version_comparison.xlsx được dùng làm version ledger ban đầu. Mỗi nhận định quan trọng được đối chiếu với release notes hoặc tài liệu tính năng chính thức. Báo cáo phân biệt rõ: thay đổi code đã có sẵn; tính năng cần bật; thay đổi mặc định tự có hiệu lực; và thao tác vận hành cần quyết định riêng.

> **Cách đọc mức rủi ro**
>
> Cao = có khả năng ảnh hưởng data path, tương thích hoặc availability; Trung bình = chủ yếu ảnh hưởng vận hành, hiệu năng hoặc automation; Thấp = thay đổi quan sát/giao diện, vẫn cần regression test.

## 1.4 Giới hạn

Kết quả cuối cùng phụ thuộc hiện trạng cluster: deployment mode, OS/kernel, loại OSD, DB/WAL layout, CRUSH, pool, client kernel/librados, Manila/RGW multisite, workload và cấu hình override. Vì chưa có As-Is inventory trong tài liệu đầu vào, các đề xuất được viết dưới dạng decision gate cần xác minh trước Production.

# 2. KẾT LUẬN VỀ LỘ TRÌNH PHIÊN BẢN

| **Giai đoạn** | **Mốc**    | **Mục đích**                                     | **Quyết định**                                                            |
| --------------------- | ----------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 1                     | 16.2.5 → 16.2.15 | Đóng toàn bộ bugfix/security fix trong Pacific        | Nâng trực tiếp tới .15; không cài tuần tự từng point release              |
| 2A                    | 16.2.15 → 17.2.7 | Nhận thay đổi major, kiểm chứng mClock/memory/client | Transit ưu tiên cho cephadm                                                      |
| 2A-alt                | 16.2.15 → 17.2.9 | Nhận hotfix mới hơn trong Quincy                       | Chỉ package-based khi repo/OS đã xác minh; không có official container build |
| 2B                    | Quincy → 18.2.7  | Đạt target Reef và tránh regression .5/.6             | Rolling upgrade, pin image/package, canary và soak                                |

> **Sau target 18.2.7**
>
> Đánh giá 18.2.8 bằng một CAB/change riêng sau khi 18.2.7 đã ổn định; không tự thay target trong change hiện tại.

## 2.1 Vì sao không phải đi qua từng point release?

Point release trong cùng một nhánh stable là cumulative: 16.2.15 đã chứa các backport của .6 đến .15. Do đó, ý nghĩa của các version trung gian là cung cấp lịch sử regression và risk gate, không phải bắt buộc cài từng bản. Điều cần kiểm tra là cluster có từng chạy một bản lỗi hoặc bật trigger gây lỗi hay không.

## 2.2 Vì sao giữ hop Quincy?

Về lịch sử, tài liệu Reef từng cho phép nâng từ Pacific hoặc Quincy. Tuy nhiên release notes 18.2.8 ghi nhận Pacific còn dùng một deprecated connection feature bit trùng với bit dùng để nhận diện Reef OSD, làm cảnh báo OSD_UPGRADE_FINISHED có thể xuất hiện trước khi mọi OSD thực sự lên Reef. Ceph hiện không còn khuyến nghị direct Pacific → Reef. Vì vậy dự án nên coi hop Quincy là control bắt buộc, dù đây không phải khẳng định rằng direct path chắc chắn gây mất dữ liệu.

Cephadm thực hiện nâng tuần tự daemon và có thể pause khi host unavailable; nhưng dừng upgrade không đồng nghĩa downgrade. Rolling upgrade giảm gián đoạn, không biến thay đổi thành thao tác có rollback binary an toàn. **\[R3-R5\]**

# 3. PHÂN TÍCH NHÁNH PACIFIC 16.2.5 → 16.2.15

## 3.1 Baseline 16.2.5

16.2.5 thay đổi quản trị NFS: module nfs được tách khỏi volumes plugin; muốn dùng ceph nfs phải enable mgr/nfs. Gói ceph-mgr-modules-core không còn tự kéo ceph-mgr-rook qua Recommends. Tác động chính là automation hoặc playbook từng ngầm dựa vào dependency này có thể không còn đúng sau redeploy.

> **Ý nghĩa**
>
> 16.2.5 là baseline cần đo, không phải mốc an toàn để giữ. Khoảng cách .5 → .15 chứa cả data-integrity fix, availability fix và security fix.

## 3.2 BlueStore deferred writes và regression OMAP

16.2.6 sửa regression trong quyết định deferred write. Khi ngưỡng prefer_deferred_size_hdd bằng hoặc lớn hơn max_blob_size_hdd, quá nhiều write bị đưa vào deferred-write column family trong RocksDB; hậu quả là metadata tăng nhanh, flush và compaction xảy ra nhiều, làm tăng write amplification và latency. Bản vá điều chỉnh điều kiện chọn đường ghi để tránh mọi dữ liệu nhỏ đều dồn vào deferred path.

Cũng trong 16.2.6 xuất hiện lỗi \#53062: khi cluster được nâng từ pre-Pacific, thao tác BlueStore quick-fix/repair có thể chuyển đổi OMAP key sai định dạng và gây corruption. Cluster cài mới Pacific không bị điều kiện lịch sử này. Trigger là chạy repair/quick-fix thủ công hoặc bật bluestore_fsck_quick_fix_on_mount. 16.2.7 sửa lỗi; vì vậy 16.2.6 phải được ghi như historical hazard, không phải điểm dừng.

Điểm quan trọng: 'feature bit' của advisory 18.2.8 không phải lỗi OMAP \#53062. \#53062 là lỗi chuyển đổi key trong BlueStore; feature-bit issue là lỗi báo nhận diện trạng thái upgrade trong mixed-version path. **\[R1, R15\]**

## 3.3 PG autoscaler: scale-down, scale-up, --bulk và noautoscale

16.2.6 thử dùng profile scale-down cho cluster mới nhằm cấp nhiều PG sớm hơn cho pool dữ liệu. 16.2.7 quay về scale-up vì device_health_metrics có thể chiếm quá nhiều PG, gây overhead. 16.2.8 bổ sung --bulk để operator chủ động đánh dấu pool sẽ chứa nhiều dữ liệu và noautoscale để đóng băng hoạt động split/merge PG trong maintenance.

Cải tiến ở đây không phải 'nhiều PG luôn nhanh hơn'. Quá ít PG có thể gây phân phối không đều; quá nhiều PG làm tăng memory/CPU/peering overhead. --bulk có ích khi biết trước pool là data-heavy. noautoscale có ích trong upgrade vì tránh phát sinh rebalancing ngoài dự kiến, nhưng phải unset sau change và theo dõi split/merge phát sinh.

## 3.4 MGR, PGLog, ceph-volume và MDS

- 16.2.8 có MGR deadlock; 16.2.9 là hotfix. Vì vậy .8 không được dùng làm dwell target.
- 16.2.11 sửa PGLog duplicate inflation sau PG split và cung cấp trim-pg-log-dups offline cho trường hợp OSD không boot. Đây là recovery tool chuyên biệt, không phải lệnh bảo trì chạy đại trà.
- 16.2.12 sửa nhiều lỗi ceph-volume/lsblk/LVM và activation chậm. Lợi ích thấy rõ nhất khi restart/activate OSD trong rolling maintenance.
- 16.2.15 giới hạn session metadata để tránh MDS chuyển read-only khi client không tăng request tid; quan trọng với CephFS/Manila có nhiều session lâu sống.

## 3.5 RBD fast-diff

16.2.15 cải thiện diff-iterate khi so từ 'beginning of time': nếu fast-diff hợp lệ và exclusive-lock khả dụng, phép diff được đảm bảo chạy local thay vì buộc truy vấn rộng qua cluster. Với QEMU live disk synchronization và backup incremental, điều này có thể giảm lượng metadata traversal và I/O mạng.

Trade-off: fast-diff chỉ đem lại lợi ích khi image feature được bật và trạng thái object-map/fast-diff hợp lệ. Feature làm tăng metadata cần duy trì; nếu object-map bị invalid, phải rebuild trước khi tin kết quả backup. Không bật hàng loạt chỉ dựa trên release note; cần benchmark chu kỳ backup thực tế.

## 3.6 Kết luận Pacific

> **Quyết định**
>
> Nâng 16.2.5 trực tiếp lên 16.2.15. Trước nâng: kiểm tra lịch sử #53062, quick-fix/repair, NFS/Rook automation và CephFS deployment mode. Sau nâng: xác nhận all-daemon version, OSD activation, PGLog, MDS session, RBD backup và client I/O.

# 4. PHÂN TÍCH NHÁNH QUINCY VÀ LỰA CHỌN ĐIỂM TRANSIT

## 4.1 mClock trở thành scheduler mặc định

Từ Quincy, BlueStore OSD dùng mClock làm osd_op_queue mặc định. mClock chia request thành ba lớp: client I/O, background recovery và background best-effort (backfill, scrub, snap trim, PG deletion). Mỗi lớp có reservation, weight và limit. Mục tiêu là kiểm soát QoS có dự đoán hơn so với WeightedPriorityQueue (WPQ), đặc biệt khi client I/O cạnh tranh với recovery.

17.2.7 sửa thiết kế mClock đáng kể: balanced trở thành mặc định; reservation/limit biểu diễn theo tỷ lệ năng lực IOPS; cost được tính từ random IOPS và sequential bandwidth của thiết bị; degraded recovery được ưu tiên hơn misplaced recovery. Đây là cải tiến tính an toàn dữ liệu nhưng có thể khiến backfill chậm hơn WPQ khi dùng balanced hoặc high_client_ops.

mClock tự benchmark năng lực OSD lúc khởi tạo. Kết quả benchmark có thể cao bất thường trong một số topology; tài liệu Ceph có threshold/fallback và khuyến nghị dùng benchmark bổ sung trước khi override. **\[R2, R6\]**

## 4.2 Memory autotune

Quincy bật osd_memory_target_autotune mặc định trong cephadm. Cơ chế lấy một tỷ lệ RAM khả dụng của host, trừ phần của daemon không autotune rồi chia cho OSD còn lại. Điều này giúp dedicated storage node tận dụng cache tốt hơn và tự thích ứng khi thay đổi số OSD/RAM.

Trade-off quan trọng: tỷ lệ mặc định 0.7 không phù hợp hyperconverged host nơi Nova compute, VM, network agent hoặc dịch vụ khác dùng chung RAM. Nếu giữ 0.7, OSD cache có thể cạnh tranh với compute và gây swap/OOM/latency spike. Với hyperconverged, phải tính budget theo host; tài liệu release gợi ý cân nhắc 0.2, nhưng giá trị thực tế phải dựa trên RAM, số OSD và workload.

Tắt autotune và đặt osd_memory_target thủ công đem lại predictability nhưng mất khả năng tự phân phối lại khi thêm/bớt OSD. Đây là lựa chọn vận hành, không phải càng thấp càng an toàn vì cache quá nhỏ có thể tăng miss và RocksDB/BlueStore I/O. **\[R2, R8\]**

## 4.3 Backend và compatibility

- LevelDB bị loại khỏi Quincy: MON/OSD còn LevelDB phải migrate sang RocksDB trước upgrade.
- FileStore bị deprecate; mClock không hỗ trợ FileStore và OSD FileStore bị ép dùng WPQ. Reef sẽ loại FileStore hoàn toàn, nên đây là blocker phải xử lý trước.
- device_health_metrics được đổi thành .mgr và trở thành common store cho mgr modules. Monitoring, backup pool list hoặc automation dựa tên pool cũ phải được kiểm tra.
- On-wire OSD compression có sẵn nhưng mặc định off. Không nên đồng nhất 'có feature' với 'nên bật'.

## 4.4 Vì sao chọn 17.2.7 cho cephadm?

17.2.7 đã chứa các sửa mClock quan trọng và có official container image. 17.2.8 chuyển base image sang CentOS 9, có rủi ro pthread_create trên kernel cũ và còn critical BlueStore regression. 17.2.9 sửa regression nhưng được phát hành sau EOL, test hạn chế, không có container build và repo EL8 chính thức không đầy đủ.

> **Quyết định theo deployment mode**
>
> Cephadm: ưu tiên 17.2.7, pin digest và soak. Package-based: có thể cân nhắc 17.2.9 nếu OS/repository đã được kiểm chứng trong lab; không dùng 17.2.8 làm điểm dừng.

# 5. PHÂN TÍCH NHÁNH REEF ĐẾN 18.2.7

## 5.1 RocksDB 7.9.2 và tuning theo column family

Reef nâng RocksDB lên 7.9.2 và lần đầu cho phép Ceph tuning RocksDB theo column family. BlueStore không chỉ có một loại metadata: onode, allocator, OMAP, deferred writes và các nhóm key có pattern truy cập khác nhau. Tuning per-column-family cho phép áp dụng cache/compaction/table options phù hợp hơn cho từng nhóm thay vì một cấu hình chung.

Cải tiến iteration làm giảm overhead khi BlueStore quét dải key liên tiếp; cải tiến compaction giảm lượng dữ liệu phải đọc/ghi lại; giảm write amplification nghĩa là một lượng logical write tạo ra ít physical write hơn. Ceph công bố mức tăng đo được tới 13.59% IOPS cho workload RGW 4K random write, nhưng đồng thời nói rõ defaults mới có penalty nhẹ ở một số use case. Con số này là kết quả workload cụ thể, không phải cam kết cho RBD/CephFS hay mọi thiết bị.

> **Trade-off**
>
> Giữ default Reef là lựa chọn an toàn ban đầu. Custom per-CF tuning có thể tốt hơn cho workload đặc thù nhưng làm tăng độ phức tạp, nguy cơ cấu hình sai và chi phí regression test. Chỉ custom sau khi có baseline, trace/metrics và benchmark lặp lại.

## 5.2 Read balancer

Read balancer tối ưu số primary PG trên mỗi OSD để giảm tình trạng một số OSD gánh quá nhiều read. Trong Reef, công cụ là offline optimizer trong osdmaptool: lấy OSD map, sinh đề xuất pg-upmap-primary rồi áp dụng. Mappings đổi primary, không di chuyển data như capacity rebalance, nhưng vẫn thay đường đọc chính.

Trade-off: Reef chưa có online automatic read balancing. pg-upmap-primary yêu cầu client compatibility và có các corner case khi mixed-version. Kernel client chưa hỗ trợ mapping này theo tài liệu Reef hiện tại; bật có thể làm krbd/CephFS kernel mount lỗi feature mismatch. Vì vậy nên trì hoãn đến sau upgrade, inventory client và thử lab.

Không tạo pg-upmap-primary trong cửa sổ rolling upgrade. Nếu phải rollback feature, chuyển balancer về mode không dùng primary mapping và xóa mappings bằng lệnh tương ứng. **\[R3, R7, R18\]**

## 5.3 RGW, RBD, monitoring và bảo mật dữ liệu

- RGW hỗ trợ bucket resharding cho multisite, cải thiện consistency/stability replication và hỗ trợ compression cho object dùng Server-Side Encryption. Mọi zone phải lên Reef trước khi bật compress-encrypted để tránh replication sai với zone cũ.
- RBD bổ sung layered client-side encryption và tiếp tục nhận cải tiến fast-diff. Tính năng encryption không tự mã hóa image cũ; key management, client support và overhead CPU/latency phải được thiết kế riêng.
- perf dump/perf schema bị deprecate, thay bằng counter dump/counter schema. Ceph-exporter tách việc thu metrics khỏi mgr Prometheus path để giảm bottleneck; dashboard/alerting stack cũng thay đổi.

## 5.4 Vì sao 18.2.7 là target hợp lý trong phạm vi hiện tại?

18.2.3 là package gắn nhầm tag và Ceph ghi rõ không được dùng. 18.2.4 là retag chính thức nhưng còn corner case pg-upmap-primary trong mixed-version. 18.2.5 và 18.2.6 chứa critical BlueStore regression ở \_extend_log sequence. 18.2.7 sửa regression này và thêm fix race BlueFS truncate/remove, partial extent decoder và phối hợp discard/kernel device.

> **Không tuyệt đối hóa target**
>
> 18.2.7 tránh được lỗi nghiêm trọng của .5/.6, nhưng 18.2.8 hiện mới hơn và được Ceph khuyến nghị. Vì phạm vi đề tài đặt đích .7, giữ .7 cho change hiện tại; tạo quyết định CAB riêng cho .8 sau khi .7 đã soak và có delta analysis.

# 6. GIẢI THÍCH SÂU CÁC CẢI TIẾN HIỆU NĂNG

| **Cơ chế**             | **Trước thay đổi**                                     | **Sau thay đổi**                                     | **KPI cần đo**                                     |
| ------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------- |
| BlueStore deferred writes      | Nhiều write nhỏ dồn vào deferred CF, tăng flush/compaction  | Quyết định deferred hợp lý hơn                         | commit/apply latency, RocksDB compaction, DB bytes written |
| RocksDB iteration              | Quét key có overhead cao hơn                                  | Iterator/readahead/prefetch và engine mới giảm overhead   | collection_list/OMAP latency, CPU/IO wait                  |
| Compaction/write amplification | Metadata bị rewrite nhiều                                      | Default/per-CF tuning giảm compaction ở workload phù hợp | write amplification, compaction time, DB/WAL utilization   |
| mClock                         | WPQ ưu tiên theo trọng số, khó kiểm soát QoS tuyệt đối | Chia reservation/weight/limit theo năng lực OSD            | client p95/p99, recovery throughput, time degraded         |
| RBD fast-diff                  | Diff có thể đi qua nhiều metadata/object                     | Local diff khi exclusive-lock + fast-diff hợp lệ           | backup duration, bytes read, cluster traffic               |
| Read balancer                  | Primary PG lệch làm read hotspot                               | Đổi primary mapping để cân bằng read                   | read_balance_score, per-OSD read IOPS/latency              |

## 6.1 Cách chứng minh 'cải tiến'

Một thay đổi chỉ được coi là cải tiến cho hạ tầng của doanh nghiệp khi cùng workload, cùng data set, cùng concurrency và cùng trạng thái recovery cho kết quả tốt hơn hoặc ổn định hơn. Release note là giả thuyết kỹ thuật; benchmark và soak mới là bằng chứng chấp nhận.

- Đo steady-state và trong degraded/recovery; không chỉ đo cluster rảnh.
- Tách RBD random read/write, sequential throughput, RGW 4K object, CephFS metadata và backup fast-diff.
- So sánh median và p95/p99 latency; throughput trung bình có thể che tail latency xấu.
- Ghi lại CPU, memory, disk utilization, BlueStore/RocksDB counters và network; tránh quy kết mọi thay đổi cho RocksDB.

## 6.2 Hiệu năng và durability có thể xung đột

high_client_ops có thể giữ client latency tốt nhưng kéo dài thời gian degraded; high_recovery_ops rút ngắn cửa sổ thiếu replica nhưng tăng client latency. Read balancer cải thiện phân phối read nhưng tăng yêu cầu client compatibility. Memory target cao tăng cache hit nhưng có thể gây pressure cho compute. Vì vậy trade-off phải được chọn theo SLO và failure scenario, không chỉ theo IOPS peak.

# 7. PHÂN TÍCH BẢN VÁ TÍNH ỔN ĐỊNH VÀ TOÀN VẸN DỮ LIỆU

| **Nhóm lỗi**       | **Biểu hiện**                                                                  | **Bản sửa** | **Ý nghĩa vận hành**                              |
| -------------------------- | -------------------------------------------------------------------------------------- | ------------------- | ----------------------------------------------------------- |
| OMAP conversion\#53062     | OMAP key sai định dạng sau repair/quick-fix trên cluster có lịch sử pre-Pacific | 16.2.7+             | Điều tra lịch sử exposure; không chạy repair trên .6 |
| MGR deadlock\#55687        | MGR treo ở 16.2.8                                                                     | 16.2.9+             | Không dwell ở .8; test mgr failover/module                |
| PGLog duplicate inflation  | PGLog phình, OSD có thể không boot                                                 | 16.2.11+ / Quincy   | Theo dõi warning; trim offline chỉ khi có chỉ định    |
| ceph-volume activation     | OSD activate rất chậm hoặc lỗi mapping                                             | 16.2.12+, 17.2.5+   | Canary restart và kiểm tra LVM/by-id                      |
| MDS session metadata       | MDS read-only do encoded session metadata vượt ngưỡng                              | 16.2.15 / 17.2.7    | Theo dõi session, client tid và MDS failover              |
| BlueStore\_extend_log      | Critical regression trong 17.2.8 và 18.2.5/.6                                         | 17.2.9 / 18.2.7     | Loại version lỗi khỏi registry/repo policy               |
| BlueFS race/partial extent | Race truncate/remove hoặc decode extent không đầy đủ                             | 18.2.7              | Soak, scrub và kiểm tra BlueFS/BlueStore log              |

## 7.1 Vì sao vá lỗi không đồng nghĩa rollback được?

Rolling upgrade giữ dịch vụ bằng cách nâng từng daemon, nhưng sau khi MON/OSD map và require-osd-release được nâng, cluster có thể dùng feature hoặc format không tương thích ngược. Cephadm stop chỉ dừng tiến trình upgrade; không thực hiện downgrade. Cơ chế phục hồi thực tế là pause ở gate, sửa nguyên nhân, redeploy cùng/newer version hoặc khôi phục theo kế hoạch DR đã chuẩn bị.

## 7.2 Soak cần tìm gì?

- Crash loop, slow ops, heartbeat, peering hoặc recovery bất thường.
- BlueStore/BlueFS/RocksDB assert, corruption warning, DB full/spillover và compaction kéo dài.
- Tail latency xấu hơn dưới scrub/recovery dù HEALTH_OK.
- MDS session growth, RGW multisite lag, RBD mirror/backup inconsistency.

# 8. PHÂN TÍCH BẢO MẬT

| **Vấn đề**            | **Cơ chế rủi ro**                                                                                                                  | **Bản vá liên quan**                       | **Việc cần làm ngoài cài patch**                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| CVE-2022-0670                  | Manila native CephFS có thể tạo path restriction sai sau lịch sử nâng từ Nautilus/cũ hơn; user có thể truy cập ngoài subvolume | Pacific 16.2.10+, Quincy 17.2.2+                    | Audit CephX key/caps và path restriction; patch không tự chứng minh key cũ đúng                 |
| CVE-2022-3650                  | ceph-crash chạy quyền root làm tăng blast radius nếu service bị khai thác                                                            | Pacific 16.2.13+                                    | Kiểm tra quyền file/socket/log và việc gửi crash report sau hạ quyền                            |
| CVE-2023-43040                 | RGW POST policy validation không chặt                                                                                                     | Pacific 16.2.15                                     | Regression-test upload POST policy và access logging                                                  |
| RGW s3website null dereference | Request không gắn bucket có thể làm RGW segfault/DoS                                                                                   | Pacific 16.2.10+, Quincy 17.2.2+                    | Test malformed request, HA/failover và rate limiting/WAF nếu có                                     |
| Cephx global_id                | Client đã xác thực có thể reclaim global_id không an toàn và gây disruption                                                       | Đã có từ Pacific 16.2.1; vẫn cần client audit | Nâng client, xử lý health alerts và chỉ khóa insecure reclaim sau khi mọi client tương thích |
| msgr2 secure/compression       | Secure mã hóa traffic; compression cùng encryption có thể làm giảm mức an toàn và mặc định bị bỏ qua                         | Feature cấu hình                                  | Đánh giá threat model, CPU, latency và giữ ms_compress_secure=false trừ khi có lý do rõ       |

## 8.1 Bản vá và remediation khác nhau

Cài bản vá ngăn tạo mới hoặc khai thác theo đường code đã sửa, nhưng không luôn sửa trạng thái tồn tại trước đó. Ví dụ CVE-2022-0670 yêu cầu audit CephX caps đã được tạo; hạ quyền ceph-crash cần kiểm tra ownership; đổi command/JSON schema cần cập nhật automation để không mất monitoring. Do đó security acceptance gồm package/version, cấu hình, credential và log evidence.

Feature-bit advisory 18.2.8 không được phân loại là lỗ hổng bảo mật: nó ảnh hưởng tính chính xác của tín hiệu hoàn tất upgrade. Tuy nhiên tín hiệu sai có thể làm operator mở feature hoặc chốt change sớm, nên vẫn là control-plane risk cần quản lý. **\[R3, R11-R13\]**

# 9. MA TRẬN TRADE-OFF KHI BẬT/TẮT TÍNH NĂNG

| **Tính năng**          | **Trạng thái đề xuất** | **Lợi ích**                                             | **Trade-off/rủi ro**                                                                    | **Quyết định vận hành**                                              |
| ------------------------------ | --------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| noautoscale trong upgrade      | Bật tạm                         | Tránh PG split/merge và rebalancing chen vào upgrade         | PG distribution không tự điều chỉnh trong cửa sổ; unset có thể phát sinh split/merge | Bật theo runbook; lưu mode cũ; unset sau health gate                         |
| Pool --bulk                    | Theo pool                         | Cấp PG sớm cho pool data-heavy, giảm giai đoạn thiếu PG   | Nhiều PG hơn làm tăng memory/CPU/peering overhead                                          | Chỉ bật cho pool có growth model rõ; không đổi hàng loạt trong upgrade |
| mClock balanced                | Giữ mặc định                  | Cân bằng client và recovery; ưu tiên degraded recovery     | Backfill có thể chậm hơn WPQ                                                               | Baseline mặc định; đo p99 và time-to-recover                               |
| mClock high_client_ops         | Chỉ khi SLO yêu cầu            | Giữ client latency/throughput khi background work              | Kéo dài degraded/misplaced window                                                            | Dùng có thời hạn, kèm maximum degraded duration                            |
| mClock high_recovery_ops       | Bật tạm ngoài peak             | Rút ngắn recovery window                                      | Client latency tăng                                                                           | Chỉ dùng trong incident/maintenance có giám sát                            |
| mClock custom                  | Chưa bật Production             | Kiểm soát chi tiết reservation/weight/limit                  | Dễ cấu hình tổng reservation sai; nhiều option bị profile khóa                          | Lab-only đến khi có mô hình capacity và rollback config                   |
| OSD memory autotune            | Tùy topology                     | Tự chia RAM và tận dụng BlueStore cache                     | 0.7 không phù hợp hyperconverged; có thể tranh RAM với VM                                | Dedicated: thử default; HCI: tính ratio thấp hơn hoặc manual target        |
| BlueStore zero-block detection | Giữ tắt                         | Có ích chủ yếu cho synthetic testing                        | Tương tác không tốt với một số feature RBD/CephFS                                      | Không bật Production nếu không có use case đã test                       |
| msgr2 secure                   | Bật theo threat model            | Mã hóa và integrity cho traffic                              | CPU/latency; cần client compatibility                                                         | Ưu tiên mạng không tin cậy/compliance; benchmark AES-GCM                   |
| OSD on-wire compression        | Giữ none ban đầu               | Giảm băng thông/chi phí inter-AZ khi network là bottleneck | Tốn CPU; dữ liệu khó nén có thể chậm; compression+encryption có caveat                | Chỉ bật khi chứng minh network-bound và dữ liệu compressible              |
| RocksDB per-CF custom          | Giữ default Reef                 | Tối ưu từng loại metadata                                   | Complexity, regression và khó support                                                        | Chỉ custom sau benchmark/telemetry đủ dài                                   |
| Read balancer pg-upmap-primary | Trì hoãn                        | Cân primary, giảm read hotspot mà không move data           | Reef chỉ offline; kernel client compatibility; mixed-version corner case                      | Chỉ đánh giá sau upgrade và client inventory                               |
| RBD fast-diff                  | Theo workload                     | Giảm thời gian live sync/backup incremental                   | Metadata overhead; cần exclusive-lock/object-map hợp lệ                                     | Bật trên image class có backup; test rebuild và restore                     |
| RGW compress-encrypted         | Trì hoãn đến all-zone Reef    | Tiết kiệm dung lượng trước encryption                     | Zone cũ replicate không đúng; CPU overhead                                                 | Chỉ bật sau multisite compatibility gate                                      |
| Telemetry perf channel         | Opt-in có kiểm soát            | Thêm dữ liệu hiệu năng cho upstream/operator               | Privacy/governance và thời gian tạo report ở cluster lớn                                  | Preview dữ liệu, phê duyệt policy trước khi gửi                          |

Ma trận này là baseline cho CAB. Quyết định cuối phải gắn owner, metric, ngưỡng rollback và thời điểm review. Không bật tính năng mới chỉ vì version mới hỗ trợ. **\[R3, R4, R6-R10\]**

# 10. TÁC ĐỘNG ĐỐI VỚI CLOUD STORAGE/OPENSTACK

| **Miền dịch vụ** | **Tác động chính**                                         | **Rủi ro cần kiểm chứng**                             | **Test đại diện**                                                |
| ------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Cinder/Nova + RBD         | mClock, RocksDB, fast-diff và RBD feature thay đổi latency/backup | krbd/librbd version, exclusive-lock, object-map, live migration | Boot VM, attach/detach, snapshot/clone, live migration, backup/restore    |
| Manila + CephFS           | CVE path restriction, MDS session fix, MDS rolling behavior          | CephX caps cũ, max_mds, standby-replay, client reconnect       | Create/share/mount, isolation negative test, MDS failover, metadata storm |
| RGW/S3/Swift              | POST policy fix, multisite/SSE/compression, resharding               | mixed-zone version, malformed request, replication lag          | PUT/GET/multipart, POST policy, SSE, resync, bucket index repair          |
| OSD/BlueStore             | Deferred writes, RocksDB 7.9.2, critical regression fixes            | DB/WAL sizing, spillover, compaction, discard, BlueFS race      | fio/rados bench, recovery, scrub/deep-scrub, OSD restart                  |
| cephadm/orchestrator      | Automatic order/pause, image lifecycle, memory autotune              | image availability/digest, host offline, HCI RAM pressure       | Canary daemon, pause/resume, image pull, host failure during upgrade      |
| Monitoring/automation     | counter commands, mgr dump fields, ceph-exporter                     | parser/schema, dashboards, alerts, log rotation                 | Golden JSON diff, alert injection, exporter scrape, log rotate            |

## 10.1 Tác động gián đoạn

Trong rolling upgrade, một daemon được restart tại một thời điểm theo safety gate. RBD/RGW/CephFS có thể tiếp tục phục vụ nếu redundancy và client retry đúng; tuy nhiên latency spike, MDS failover, degraded PG hoặc reconnect vẫn có thể xảy ra. 'Minimal Downtime' phải đo theo SLO dịch vụ, không chỉ theo trạng thái daemon.

## 10.2 Tác động capacity và recovery

mClock và autoscaler có thể thay đổi tốc độ recovery, trong khi RocksDB/BlueStore thay đổi write path. Phải đảm bảo headroom dung lượng, DB/WAL và network để cluster chịu được một OSD/host failure trong lúc upgrade. Nếu cluster đang nearfull hoặc scrub backlog lớn, không nên dùng upgrade để 'hy vọng' cải thiện tình hình.

# 11. COMPATIBILITY MATRIX VÀ BLOCKER

Compatibility matrix là danh sách quan hệ phải đúng đồng thời giữa Ceph version, OS/kernel/container, daemon, client, storage format và dịch vụ. Nó cần thiết vì cùng một version Ceph có thể hoạt động khác nhau tùy lịch sử cluster, feature đã bật và client còn kết nối.

| **Hạng mục** | **Cần thu thập**                    | **Blocker/điều kiện**                             | **Bằng chứng chấp nhận**                                  |
| -------------------- | ------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------- |
| Deployment mode      | cephadm/package/Rook, image/repo            | Không có image/repo phù hợp với target                | Pin image digest/package repo; lab pull/install thành công        |
| OS/kernel/container  | Distro, kernel, glibc, Podman/Docker        | Kernel cũ + CentOS 9 container pthread_create             | Daemon canary chạy ổn, không crash thread creation               |
| ObjectStore/KV       | BlueStore/FileStore; RocksDB/LevelDB        | FileStore trước Reef; LevelDB trước Quincy             | 100% OSD BlueStore; MON/OSD RocksDB                                 |
| BlueStore layout     | block, block.db, block.wal, dm-crypt        | DB/WAL mapping lỗi, spillover, cryptsetup incompatibility | ceph-volume inventory và mapping by-id nhất quán                 |
| Clients              | krbd, ceph-fuse, librbd, QEMU, CSI          | Pre-Reef client với pg-upmap-primary                      | ceph features/client inventory; feature chưa bật trong mixed mode |
| CephFS               | max_mds, standby-replay, Manila caps        | MDS sanity/rolling rule, CVE caps lịch sử                | Failover pass, isolation negative test pass                         |
| RGW                  | multisite, SSE/KMS, frontend, bucket index  | All-zone version không đồng nhất                       | Replication/resync và SSE multipart pass                           |
| Automation           | Parser ceph mgr/config/perf output          | Schema/field/command deprecated                            | Golden-output regression test pass                                  |
| Capacity/health      | nearfull, PG state, scrub backlog, recovery | Down/recovering OSD, insufficient headroom                 | Healthy/stable baseline và failure headroom được phê duyệt    |

> **Blocker tối thiểu**
>
> Không GO nếu còn FileStore/LevelDB, daemon/client không inventory được, thiếu image/repo target, OSD down/recovering, nearfull không đủ headroom, hoặc không có phương án phục hồi cấu hình/credential/monitoring.

# 12. TIÊU CHÍ XÁC NHẬN LỢI ÍCH VÀ GO/NO-GO

## 12.1 Gate sau Pacific 16.2.15

- ceph versions cho thấy mọi daemon đã ở đúng version; không có mixed version ngoài cửa sổ cho phép.
- HEALTH_OK hoặc warning đã được phân loại và phê duyệt; không có down/recovering OSD.
- OSD canary restart/activation đúng thời gian; LVM/by-id/DB-WAL mapping đúng.
- RBD, CephFS/Manila, RGW smoke test và backup/restore đạt.
- Không xuất hiện dấu hiệu \#53062, PGLog inflation, MGR deadlock hoặc MDS read-only.

## 12.2 Gate sau Quincy transit

- mClock profile và capacity được xác nhận; đo client p95/p99 cùng recovery throughput.
- Memory autotune không gây pressure/OOM trên host; ratio phù hợp dedicated hay hyperconverged.
- Không còn LevelDB; FileStore đã loại khỏi path trước Reef.
- Pool .mgr, cephadm modules, monitoring và parser automation hoạt động.
- Soak đủ để quan sát scrub, recovery, backup, MDS/RGW ổn định trước major hop tiếp theo.

## 12.3 Gate sau Reef 18.2.7

- Không có BlueStore/BlueFS assert/corruption warning; deep-scrub được lên lịch sau soak phù hợp.
- KPI workload đại diện không vượt ngưỡng regression đã phê duyệt; tail latency được so với baseline.
- Không có pg-upmap-primary được tạo trong mixed-version window; client compatibility được xác nhận trước khi đánh giá read balancer.
- RGW multisite/SSE, CephFS/Manila isolation, RBD live migration/backup/restore đạt.
- Monitoring sử dụng counter/exporter path mới; alert và log rotation được xác nhận.

## 12.4 Ngưỡng NO-GO gợi ý

NO-GO nếu xuất hiện data-integrity warning, repeated daemon crash, PG stuck, MDS read-only, RGW replication divergence, client feature mismatch, p99 latency vượt ngưỡng SLO kéo dài, hoặc recovery time vượt maximum degraded window. Với lỗi hiệu năng nhỏ nhưng không có integrity/availability impact, có thể pause để điều chỉnh profile/tuning thay vì rollback binary.

# 13. KẾT LUẬN

Nâng từ Pacific 16.2.5 lên Reef không phải chuỗi cập nhật daemon đơn giản. Giá trị chính đến từ việc đóng các lỗi tích lũy, thay scheduler và memory management, nâng RocksDB, cải thiện RBD/RGW/CephFS và loại bỏ backend cũ. Rủi ro chính nằm ở lịch sử cluster, mixed-version compatibility, defaults mới và việc bật tính năng trước khi client/workload sẵn sàng.

Lộ trình được khuyến nghị là 16.2.5 → 16.2.15 → Quincy transit → 18.2.7, với gate và soak giữa các chặng. 17.2.7 phù hợp cephadm; 17.2.9 chỉ phù hợp package-based có điều kiện. 18.2.8 cần delta assessment riêng sau khi target 18.2.7 đã ổn định.

> **Thông điệp cuối**
>
> Bật tính năng mới phải là một quyết định có giả thuyết, metric, ngưỡng chấp nhận và đường quay lại cấu hình. Không dùng release note thay cho benchmark; không dùng HEALTH_OK thay cho kiểm thử dịch vụ.

# REFERENCES

Ngày truy cập: 22/08/2026. Ưu tiên đường dẫn version-pinned khi có thể. Các trang 'latest' có thể thay đổi theo release mới.

\[R1\] Ceph Pacific release notes (16.2.5-16.2.15). [<u>https://docs.ceph.com/en/pacific/releases/pacific/</u>](https://docs.ceph.com/en/pacific/releases/pacific/)

\[R2\] Ceph Quincy release notes (17.2.0-17.2.9). [<u>https://docs.ceph.com/en/quincy/releases/quincy/</u>](https://docs.ceph.com/en/quincy/releases/quincy/)

\[R3\] Ceph Reef release notes (18.2.0-18.2.8). [<u>https://docs.ceph.com/en/reef/releases/reef/</u>](https://docs.ceph.com/en/reef/releases/reef/)

\[R4\] Cephadm - Upgrading Ceph. [<u>https://docs.ceph.com/en/latest/cephadm/upgrade/</u>](https://docs.ceph.com/en/latest/cephadm/upgrade/)

\[R5\] Ceph Reef - Upgrading from Pacific or Quincy. [<u>https://docs.ceph.com/en/reef/releases/reef/</u>](https://docs.ceph.com/en/reef/releases/reef/#upgrading-from-pacific-or-quincy)

\[R6\] mClock configuration reference (Reef). [<u>https://docs.ceph.com/en/reef/rados/configuration/mclock-config-ref/</u>](https://docs.ceph.com/en/reef/rados/configuration/mclock-config-ref/)

\[R7\] Operating the Read (Primary) Balancer (Reef). [<u>https://docs.ceph.com/en/reef/rados/operations/read-balancer/</u>](https://docs.ceph.com/en/reef/rados/operations/read-balancer/)

\[R8\] Cephadm OSD service - automatic memory tuning. [<u>https://docs.ceph.com/en/reef/cephadm/services/osd/</u>](https://docs.ceph.com/en/reef/cephadm/services/osd/#automatically-tuning-osd-memory)

\[R9\] Messenger v2 and compression modes (Reef). [<u>https://docs.ceph.com/en/reef/rados/configuration/msgr2/</u>](https://docs.ceph.com/en/reef/rados/configuration/msgr2/#compression-modes)

\[R10\] Placement groups and PG autoscaler. [<u>https://docs.ceph.com/en/reef/rados/operations/placement-groups/</u>](https://docs.ceph.com/en/reef/rados/operations/placement-groups/)

\[R11\] CVE-2022-0670 - Native CephFS Manila path-restriction bypass. [<u>https://docs.ceph.com/en/latest/security/CVE-2022-0670/</u>](https://docs.ceph.com/en/latest/security/CVE-2022-0670/)

\[R12\] CVE-2021-20288 - Unauthorized global_id reuse in cephx. [<u>https://docs.ceph.com/en/latest/security/CVE-2021-20288/</u>](https://docs.ceph.com/en/latest/security/CVE-2021-20288/)

\[R13\] Ceph past vulnerabilities index. [<u>https://docs.ceph.com/en/reef/security/cves/</u>](https://docs.ceph.com/en/reef/security/cves/)

\[R14\] Ceph stable-release lifecycle and rolling-upgrade policy. [<u>https://docs.ceph.com/en/latest/releases/general/</u>](https://docs.ceph.com/en/latest/releases/general/)

\[R15\] Ceph tracker \#53062 - BlueStore OMAP format conversion. [<u>https://tracker.ceph.com/issues/53062</u>](https://tracker.ceph.com/issues/53062)

\[R16\] Ceph tracker \#53729 - PGLog duplicate inflation. [<u>https://tracker.ceph.com/issues/53729</u>](https://tracker.ceph.com/issues/53729)

\[R17\] Ceph tracker \#55687 - Pacific 16.2.8 MGR deadlock. [<u>https://tracker.ceph.com/issues/55687</u>](https://tracker.ceph.com/issues/55687)

\[R18\] Ceph tracker \#61948 - pg-upmap-primary compatibility. [<u>https://tracker.ceph.com/issues/61948</u>](https://tracker.ceph.com/issues/61948)

\[R19\] Ceph PR \#61653 - Reef BlueStore \_extend_log fix. [<u>https://github.com/ceph/ceph/pull/61653</u>](https://github.com/ceph/ceph/pull/61653)

\[R20\] Ceph PR \#62840 - BlueFS truncate/remove race fix. [<u>https://github.com/ceph/ceph/pull/62840</u>](https://github.com/ceph/ceph/pull/62840)

\[N1\] Nguồn nội bộ: version_comparison.xlsx (3 sheet: Pacific 16.2.x, Quincy 17.2.x, Reef 18.2.x).

## Link release note theo từng phiên bản trong file nguồn

**Pacific 16.2.x**

- Ceph 16.2.5: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-5-pacific)
- Ceph 16.2.6: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-6-pacific)
- Ceph 16.2.7: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-7-pacific)
- Ceph 16.2.8: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-8-pacific)
- Ceph 16.2.9: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-9-pacific)
- Ceph 16.2.10: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-10-pacific)
- Ceph 16.2.11: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-11-pacific)
- Ceph 16.2.12: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-12-pacific)
- Ceph 16.2.13: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-13-pacific)
- Ceph 16.2.14: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-14-pacific)
- Ceph 16.2.15: [<u>https://docs.ceph.com/en/latest/releases/pacific/</u>](https://docs.ceph.com/en/latest/releases/pacific/#v16-2-15-pacific)

**Quincy 17.2.x**

- Ceph 17.2.0: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-0-quincy)
- Ceph 17.2.1: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-1-quincy)
- Ceph 17.2.2: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-2-quincy)
- Ceph 17.2.3: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-3-quincy)
- Ceph 17.2.4: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-4-quincy)
- Ceph 17.2.5: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-5-quincy)
- Ceph 17.2.6: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-6-quincy)
- Ceph 17.2.7: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-7-quincy)
- Ceph 17.2.8: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-8-quincy)
- Ceph 17.2.9: [<u>https://docs.ceph.com/en/latest/releases/quincy/</u>](https://docs.ceph.com/en/latest/releases/quincy/#v17-2-9-quincy)

**Reef 18.2.x**

- Ceph 18.2.0: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-0-reef)
- Ceph 18.2.1: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-1-reef)
- Ceph 18.2.2: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-2-reef)
- Ceph 18.2.3: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-3-reef)
- Ceph 18.2.4: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-4-reef)
- Ceph 18.2.5: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-5-reef)
- Ceph 18.2.6: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-6-reef)
- Ceph 18.2.7: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-7-reef)
- Ceph 18.2.8: [<u>https://docs.ceph.com/en/latest/releases/reef/</u>](https://docs.ceph.com/en/latest/releases/reef/#v18-2-8-reef)

# PHỤ LỤC A. VERSION LEDGER TỪ FILE NGUỒN

Phụ lục giữ lại vai trò của từng point release để truy vết regression và quyết định dwell. Nội dung đã được biên tập gọn, nhưng không làm thay đổi kết luận của bảng nguồn.

## Pacific 16.2.x

| **Version** | **Vai trò**               | **Cải tiến/sửa lỗi**                                                                                                                                                                           | **Trade-off/cảnh báo**                                                                                                                                                                        | **Rủi ro / quyết định**  |
| ----------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| 16.2.5            | Baseline hiện tại              | Tái cấu trúc quản trị NFS sang mgr/nfs; sửa tương thích msgr v2 giữa client/server 32-bit và 64-bit.                                                                                          | ceph-mgr-rook không còn được cài theo Recommends; một số lệnh NFS đổi hoặc bị deprecate, cần rà lại automation.                                                                       | Trung bình / Baseline             |
| 16.2.6            | Bản lịch sử rủi ro           | Bổ sung profile pg_autoscaler scale-down cho cluster mới; cải thiện BlueStore deferred writes, giảm flush/compaction RocksDB quá mức; đơn giản hoá rolling MDS.                               | LỖI\#53062: OMAP conversion có thể gây corrupt dữ liệu khi cluster nâng từ bản cũ và chạy BlueStore repair/quick-fix. Không bật quick-fix, không chạy repair trên phiên bản này.  | Cao / Không dùng / lịch sử     |
| 16.2.7            | Bản vá bắt buộc (cumulative) | Sửa lỗi OMAP\#53062; mClock có tự động benchmark IOPS thiết bị; pg_autoscaler mặc định quay lại scale-up; quản trị NFS chuyển sang mgr/nfs.                                               | Non-cephadm CephFS cần tạm đặt\`mon_mds_skip_sanity=true\` trong lúc nâng; scale-down bị rút vì tạo quá nhiều PG ở pool device_health_metrics; NFS cũ có thể cần migrate thủ công. | Cao / Không cần dừng            |
| 16.2.8            | Feature + regression             | Thêm pool\`--bulk\`, cờ global \`noautoscale\`, cảnh báo \`require-osd-release\`; bổ sung điều kiện an toàn cho upgrade nhiều active MDS.                                                      | Giới thiệu regression khiến MGR có thể deadlock; được hotfix ở 16.2.9. Không chọn .8 làm điểm dừng.                                                                                    | Cao / Không dừng                 |
| 16.2.9            | Hotfix                           | Sửa MGR deadlock được đưa vào 16.2.8.                                                                                                                                                             | Phạm vi hotfix hẹp; không bổ sung giá trị để làm điểm trung chuyển độc lập.                                                                                                            | Trung bình / Không dừng         |
| 16.2.10           | Security hotfix                  | Khắc phục hai lỗ hổng: path restriction CephFS/Manila và RGW s3website null-pointer crash.                                                                                                          | CephFS flaw đặc biệt liên quan cluster đã nâng từ Nautilus hoặc cũ hơn; có thể phải audit CephX caps/keys chứ không chỉ cài patch.                                                  | Cao / Không dừng                 |
| 16.2.11           | Bugfix                           | Sửa PGLog dup tăng không giới hạn và thêm thao tác trim offline; hỗ trợ RBD unmap theo namespace; tiếp tục tối ưu deferred writes BlueStore.                                               | PGLog trim offline là thao tác phục hồi chuyên biệt, không nên chạy đại trà; cải thiện hiệu năng phụ thuộc workload.                                                                | Trung bình / Không dừng         |
| 16.2.12           | Hotfix vận hành                | Khắc phục nhiều lỗi hiệu năng ceph-volume, đặc biệt chậm khi kích hoạt OSD; sửa lsblk/LVM và các regression activate.                                                                     | Tác động chính ở provision/activate OSD; không thay thế kiểm tra device mapping trước và sau nâng.                                                                                        | Trung bình / Không dừng         |
| 16.2.13           | Security + bugfix                | ceph-crash hạ quyền từ root xuống user ceph (CVE); thêm nhiều sửa lỗi ceph-volume và thay đổi layout một số field\`mgr dump\`.                                                              | Automation parse JSON/output\`mgr dump\` có thể bị ảnh hưởng; quyền file/log của ceph-crash cần được kiểm tra.                                                                           | Trung bình / Không dừng         |
| 16.2.14           | Bugfix + tooling                 | Cho phép xoá CephFS\`lost+found\` sau DR; hỗ trợ encrypted volumes cho ceph-volume new-db/new-wal/migrate; bổ sung field mgr active_clients.                                                        | Các lệnh migrate DB/WAL vẫn là thao tác nhạy cảm; thay đổi output mgr có thể ảnh hưởng parser.                                                                                          | Trung bình / Không dừng         |
| 16.2.15           | Đích giai đoạn 1             | Bản backport Pacific dự kiến cuối: ngăn MDS read-only do session metadata phình; RBD fast-diff cải thiện mạnh live sync/backup; vá RGW POST-policy; nhiều sửa BlueStore/ceph-volume/cephadm. | Pacific đã hết vòng đời và .15 không phải đích dài hạn. Cần soak/validate trước khi sang major release; không nên gộp hai major hop trong một lần quan sát.                     | Trung bình / Target giai đoạn 1 |

## Quincy 17.2.x

| **Version** | **Vai trò**        | **Cải tiến/sửa lỗi**                                                                                                                                                                       | **Trade-off/cảnh báo**                                                                                                                                                                      | **Rủi ro / quyết định**          |
| ----------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| 17.2.0            | Major baseline            | mClock trở thành scheduler mặc định cho BlueStore; LevelDB bị loại bỏ; pool device_health_metrics đổi thành\`.mgr\`; cephadm memory autotune và observability được mở rộng.         | FileStore chỉ còn WPQ và đã deprecate; phải migrate MON/OSD LevelDB→RocksDB trước. Memory ratio 0.7 không hợp hyperconverged; custom mClock profile có hạn chế runtime ở bản đầu. | Cao / Không dừng                         |
| 17.2.1            | Bugfix                    | Tắt zero-block detection mặc định vì tương tác bất lợi với RBD/CephFS; bổ sung PGLog trim offline và sửa log rotation.                                                                 | Có thể giảm một tối ưu ghi zero nhưng ưu tiên tính đúng; log-to-file có known issue cần kiểm tra lại sau rotation.                                                                  | Trung bình / Không dừng                 |
| 17.2.2            | Security hotfix           | Vá path restriction CephFS/Manila và RGW crash tương tự nhánh Pacific.                                                                                                                         | Một số build/toolchain có thể gặp ceph-mgr/libcephsqlite crash, được sửa ngay ở 17.2.3.                                                                                                   | Cao / Không dừng                         |
| 17.2.3            | Hotfix                    | Sửa ceph-mgr crash lặp lại trong libcephsqlite khi build bằng gcc12.                                                                                                                             | Phạm vi hẹp; chưa có các cải tiến mClock và nhiều bugfix về sau.                                                                                                                          | Trung bình / Không dừng                 |
| 17.2.4            | Bugfix                    | Sửa recovery/backfill tiêu thụ CPU cao, PGLog dup inflation và lỗi chuyển đổi SnapMapper.                                                                                                    | Bản .4 bị thiếu một số commit khi phát hành; .5 là hotfix bổ sung, vì vậy không dwell ở .4.                                                                                            | Cao / Không dừng                         |
| 17.2.5            | Hotfix                    | Bổ sung các commit thiếu của .4; sửa ceph-volume activation chậm và crash trong Rook NFS/telemetry.                                                                                           | Vẫn thiếu các cải tiến scheduler .7; không tạo lợi ích để dừng riêng.                                                                                                                  | Trung bình / Không dừng                 |
| 17.2.6            | Bugfix                    | Cải thiện quyết định deferred-write của BlueStore; hỗ trợ crush_device_class theo OSD; nhiều sửa cephadm/ceph-volume.                                                                      | Lợi ích deferred write phụ thuộc workload; thay đổi device class có thể tác động CRUSH nếu vận hành sai.                                                                              | Trung bình / Không dừng                 |
| 17.2.7            | Điểm transit đề xuất | mClock được làm lại: balanced mặc định, QoS phân số, cost theo capacity thiết bị và degraded recovery ưu tiên hơn misplaced; thêm nhiều fix RGW/CephFS và container fallback EL8. | Backfill có thể chậm hơn WPQ trong balanced/high_client profile; phải đo client latency và recovery. Vẫn là Quincy đã EOL, chỉ dùng để transit/soak.                                 | Trung bình / Transit đề xuất (cephadm) |
| 17.2.8            | Không chọn làm transit | RBD fast-diff cải thiện live sync/backup; image chuyển sang CentOS 9.                                                                                                                             | Có critical BlueStore regression được sửa ở .9; container CentOS 9 có thể crash\`pthread_create\` trên kernel cũ; không còn RPM EL8.                                                    | Cao / Không dùng làm transit            |
| 17.2.9            | Transit có điều kiện  | Sửa critical BlueStore regression của .8 và bổ sung tương thích OpenSSL mới.                                                                                                                 | Phát hành sau EOL với mức test hạn chế; không có container build, repo EL8 trống/có thể làm dnf fail. Không phải lựa chọn cephadm mặc định.                                      | Cao / Chỉ cân nhắc package              |

## Reef 18.2.x

| **Version** | **Vai trò**                 | **Cải tiến/sửa lỗi**                                                                                                                                     | **Trade-off/cảnh báo**                                                                                                                                                                                                                                              | **Rủi ro / quyết định**    |
| ----------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| 18.2.0            | Major baseline                     | RocksDB 7.9.2, iteration/per-column-family tuning và defaults mới; mClock cải tiến; read balancer; RGW multisite/SSE; FileStore không còn được hỗ trợ.  | Một số workload chịu penalty nhẹ dù RGW 4K random-write có thể tăng tới 13.59%; Bookworm chưa có package ở .0; perf dump/schema và cache tiering bị deprecate; read balancer chỉ offline.                                                                    | Cao / Không dừng                   |
| 18.2.1            | Bugfix + packaging                 | Bản Reef đầu tiên có Debian Bookworm packages; sửa RGW multisite SSE multipart và CephFS session metadata; thêm bucket repair tooling.                     | Sau fix RGW SSE multisite có thể cần resync/recovery command; POOL_APP_NOT_ENABLED đòi hỏi gắn application metadata đúng.                                                                                                                                          | Trung bình / Không dừng           |
| 18.2.2            | Hotfix                             | Sửa Prometheus module crash lúc startup và lỗi OSDMap encoder.                                                                                                 | Hotfix hẹp; không giải quyết các vấn đề package/image/kernel của các bản sau.                                                                                                                                                                                    | Trung bình / Không dừng           |
| 18.2.3            | Bản package lỗi                  | Không phải release an toàn chính thức: một early build của 18.2.4 bị Debian đóng gói nhầm thành 18.2.3.                                               | Ceph ghi rõ 18.2.3 không nên được sử dụng.                                                                                                                                                                                                                          | Cao / Không dùng                   |
| 18.2.4            | Retag chính thức                 | Bản chính thức thay thế .3; sửa việc cho phép pre-Reef client khi có pg-upmap-primary và có RBD fast-diff improvement.                                   | Container CentOS 9 có thể crash pthread_create trên kernel cũ; fix pg-upmap-primary còn corner case, cần tránh mappings khi cluster/client đang mixed-version.                                                                                                      | Cao / Không dừng                   |
| 18.2.5            | Feature + regression               | Thêm\`rm-pg-upmap-primary-all\`; RBD-NBD dùng netlink mặc định với fallback; nhiều cải thiện BlueStore/KernelDevice.                                      | Có critical BlueStore regression được sửa ở 18.2.7. Không chọn .5 làm dwell target.                                                                                                                                                                                | Cao / Không dừng                   |
| 18.2.6            | Hotfix + regression còn tồn tại | Sửa nhận diện cryptsetup cho dmcrypt và lỗi IPv6 subnet/address selection.                                                                                    | Vẫn bị critical BlueStore regression của .5; được sửa ở .7.                                                                                                                                                                                                         | Cao / Không dừng                   |
| 18.2.7            | Đích giai đoạn 2               | Sửa critical BlueStore regression ở .5/.6 (\`\_extend_log\` sequence), race BlueFS truncate/remove, partial extent decoder và phối hợp discard/kernel device. | Là target theo yêu cầu nhưng không còn là bản Reef mới nhất; 18.2.8 đã phát hành sau đó. Vẫn cần soak, scrub và workload validation—không xem HEALTH_OK là đủ.                                                                                      | Trung bình / Target giai đoạn 2   |
| 18.2.8            | Advisory sau target                | Bản Reef dự kiến cuối (20-03-2026) và được Ceph khuyến nghị; bổ sung nhiều backport sau .7.                                                            | QA phát hiện Pacific dùng lại feature bit được Reef dùng để nhận diện OSD, có thể báo OSD_UPGRADE_FINISHED sớm; Ceph không còn khuyến nghị direct Pacific→Reef. Đây không phải lý do bỏ hop Quincy—ngược lại, xác nhận thiết kế hai hop. | Trung bình / Đánh giá sau target |
