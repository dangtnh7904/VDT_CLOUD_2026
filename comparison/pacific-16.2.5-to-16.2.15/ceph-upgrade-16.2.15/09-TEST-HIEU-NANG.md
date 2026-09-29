# Bộ đo hiệu năng trước, trong và sau nâng cấp

[Mục lục](00-README.md) · [Gate/ngưỡng](06-GATE-VA-NGUONG.md) · [Mẫu kết quả](12-BIEU-MAU-BANG-CHUNG.md)

## 1. Câu hỏi cần trả lời

1. Target có giữ SLO RBD/RGW ở cùng workload không?
2. Mỗi lần restart/drain/return làm tăng latency, error và tài nguyên bao nhiêu?
3. Khi đã ổn định, target nhanh hơn/chậm hơn ở profile nào, mức chênh so với độ biến thiên baseline ra sao?
4. Có đủ budget để tăng batch, hoàn thành fleet theo thời gian kế hoạch không?
5. H0-R làm dài bước return bao nhiêu; H0-W L1/L2/L3 làm tăng ACK latency, CPU và I/O bao nhiêu ở cùng workload?

Đây là **thiết kế bài đo**, chưa có số liệu thực. Không điền kết quả giả.

## 2. Khóa điều kiện so sánh

| Giữ cố định hoặc ghi rõ | Nội dung |
| --- | --- |
| Client path | Cùng host/VM, kernel/QEMU/librbd/SDK, network/LB/TLS, version tool; nếu nâng client thì đó là phép thử riêng |
| Data | Cùng kích cỡ working set, phân bố object/range, seed, tỷ lệ đã ghi, snapshots và metadata; prefill để tránh đọc hole |
| Pool/layout | Cùng replicated/EC, size/min_size, rule/class, PG count, placement tương đương và compression/encryption |
| Load | Cùng offered rate, concurrency, queue depth, block/object size, read/write mix và durability contract |
| Cache | Cùng chế độ warm/cold, page cache/client cache/PWL; không drop cache toàn production |
| Background | Ghi scrub, autoscaler, balancer, recovery, backup, GC/LC và user traffic; so ở trạng thái tương đương |
| Đo lường | Đồng bộ thời gian, cùng histogram/đơn vị, cửa sổ warm-up/measure, raw results và stop threshold |

Nên lặp ít nhất 3 lần trong lab, báo median các lần chạy cùng min/max hoặc độ phân tán. Với p99, cần đủ số request và histogram; không lấy trung bình các p99 khác nhau rồi gọi là p99 tổng. Workload quá ít mẫu thì tăng thời lượng hoặc ghi chưa đủ độ tin cậy.

Điểm khởi đầu cho lab có thể là 5 phút warm-up + 15 phút đo mỗi profile; điều chỉnh tới khi ổn định và đủ mẫu. Đây không phải ngưỡng bắt buộc cho production.

## 3. Ma trận bài đo

| ID | Bài | Phase 1 | Phase 2 | Phase 3 |
| --- | --- | --- | --- | --- |
| P-01 | RBD fio theo client path thật | Baseline | Tải giới hạn liên tục qua canary | Lặp profile sau hội tụ |
| P-02 | RGW S3 theo operation/size | Baseline | Probe + fixed load qua direct/LB | Lặp cùng corpus/profile |
| P-03 | CPU/RSS/disk/network/MON/DB | Chu kỳ tải đại diện | Theo dõi liên tục | So trạng thái ổn định và trend |
| P-04 | Chi phí nâng một OSD/batch | Rehearsal/counter baseline | Drain/restart/rejoin/return/soak thực | Tổng hợp chi phí mỗi cohort |
| P-05 | Fast-diff/backup RBD, nếu dùng | Client/path base | Canary client target riêng | So thời gian + correctness |
| P-06 | Overhead H0-R và H0-W L1/L2/L3 | Native-only đối chứng và từng level đã implement trên cùng workload | Đo H0-R khi return; H0-W trong protected writes | So coverage/cost theo level; không gộp với cải thiện Ceph |
| P-07 | Báo cáo regression + dự báo fleet | Khóa tiêu chí và công thức | Cập nhật batch size có căn cứ | Kết luận và dữ liệu cho hop sau |

## 4. P-01 — RBD

### Profile đề xuất

| Profile | Mẫu tải | Đo gì? |
| --- | --- | --- |
| R1 | 4 KiB random read; QD thấp và QD đại diện ứng dụng | IOPS, read latency p50/p95/p99, CPU/queue |
| R2 | 4 KiB random write | Write IOPS/latency, flush behavior, DB/WAL/disk |
| R3 | 4 KiB random mix, ví dụ 70% read / 30% write nếu phù hợp | QoS hỗn hợp, read/write latency riêng |
| R4 | 1 MiB sequential read/write | MiB/s, network/disk bottleneck |
| R5 | Write + flush/fsync theo ứng dụng | Durability latency, error/timeout |

Chỉ dùng các profile đại diện; 70/30 hoặc 1 MiB là ví dụ, không phải yêu cầu Ceph. Đo trên RBD image riêng qua đúng path đang dùng (krbd, QEMU/librbd hoặc rbd-nbd). fio trên filesystem của krbd không đo được fix trong librbd của QEMU.

### Mẫu fio đọc trên file test đã prefill

Thay đường dẫn và rate theo tài nguyên test đã chuẩn bị. Đây là ví dụ đọc, không tự tạo/mkfs một RBD. `allow_file_create=0` tránh vô tình tạo file mới khi sai đường dẫn; phải kiểm file nằm trên đúng filesystem RBD bằng `findmnt` trước chạy.

```bash
fio --name=rbd-randread-4k \
  --filename=/mnt/rbd-upgrade-test/prefilled.bin \
  --allow_file_create=0 --readonly \
  --ioengine=libaio --direct=1 --rw=randread --bs=4k \
  --size=8G --iodepth=16 --numjobs=1 --rate_iops=200 \
  --time_based=1 --ramp_time=60 --runtime=300 \
  --randrepeat=1 --randseed=42 \
  --lat_percentiles=1 --percentile_list=50:95:99:99.9 \
  --output-format=json+ --output=pre-rbd-r1-run1.json
```

`8G`, `200 IOPS`, QD16 và thời lượng là ví dụ lab để bắt đầu, không bảo đảm an toàn trên mọi pool. Chốt trước khi chạy. R2/R3/R4 write và R5 cần job riêng trên dữ liệu disposable; khóa cùng flush/fsync policy ở cả trước/sau, không suy `direct=1` có nghĩa mỗi write đã fsync.

Tách bài fio verify/correctness khỏi bài throughput, hoặc giữ cùng verify overhead khi so sánh. Working set 8 GiB có thể vừa cache; phải ghi rõ, không gọi là tốc độ toàn bộ hệ thống đĩa. Nguồn option: [S14](13-NGUON-VA-DOI-CHIEU.md); kiểm version fio thực tế.

## 5. P-02 — RGW

Sử dụng Warp hoặc S3 harness đang có; pin version tool, lưu command/job đã bỏ secret và giữ nguyên config khi lặp. Chọn test bucket/prefix riêng và quota/budget; tool có thể tạo/xóa object trong dataset, không trỏ vào bucket nghiệp vụ. [S15](13-NGUON-VA-DOI-CHIEU.md)

| Profile | Dataset/operation | Kết quả |
| --- | --- | --- |
| S1 | GET/PUT object nhỏ, ví dụ 4 KiB–64 KiB | ops/s, p95/p99 theo GET và PUT, error/timeout |
| S2 | GET/PUT 4 MiB hoặc phân bố ứng dụng | MiB/s, latency, CPU/network |
| S3 | Multipart object lớn nếu dùng | Completion time, upload failure, read-back correctness |
| S4 | LIST/HEAD/DELETE nếu là workload chính | Operation latency, error, index/worker impact |
| S5 | Mix đại diện qua LB, cùng TLS/auth | SLO end-to-end dưới tải nền tương đương |

Test direct endpoint phục vụ chẩn đoán canary; test qua LB mới phản ánh đường người dùng. Không so trước qua LB với sau direct. Với rate cố định, báo offered request/s, achieved request/s, retry và failed attempt; concurrency cố định đơn thuần không phải offered load cố định.

## 6. P-03 / P-04 — Tài nguyên và chi phí rollout

Lấy sample đồng bộ với client, ví dụ mỗi 5–15 giây tùy monitoring có sẵn. Báo peak và trend ngoài average: CPU/RSS MGR/OSD, disk await/queue/util, DB/WAL space/latency, network TX/RX/retransmit, MON free/growth, recovery bytes/s, PG states, crash/restart và scrub backlog.

Với mỗi X/batch PA1, ghi các mốc: bắt đầu prepare, bắt đầu chuyển PG khi X online, DR_READY, stop, process start, OSD up, PG return hội tụ, fresh deep-scrub xong, local-X verify PASS, mở H0-W admission, soak xong. Tính:

- Thời gian ảnh hưởng client và số request lỗi, không chỉ thời gian daemon down.
- Byte di chuyển ra + về, byte network thực, recovery throughput và CPU/disk cost.
- `degraded PG-seconds = tổng theo thời gian (số PG degraded × độ dài sample)`; đây là chỉ số so sánh rủi ro, không phải xác suất mất dữ liệu.
- Regression p99 trong cửa sổ nâng so với baseline cùng offered load, cùng với trần SLO tuyệt đối.

Nếu S cùng host X, đo host NIC/ToR và disk/HBA/CPU riêng. Không giả định toàn bộ recovery đi X→S nội bộ: ghi actual source/destination; same-host không đảm bảo nguồn copy.

## 7. P-05 / P-06 — Đo lợi ích và overhead riêng

**P-05:** dùng đúng ứng dụng backup/live-sync hoặc harness `diff-iterate` với điều kiện đã nêu ở [01](01-LY-DO-NANG-CAP.md). Ghi fast-diff/object-map hợp lệ, whole-object, from-snapshot và lock state; so kết quả diff với oracle. Chạy client base/target trên cùng backend đã ổn định để tách lợi ích client khỏi OSD. Nếu chỉ dùng krbd hoặc path không chạm optimization, ghi N/A; không ép bật feature trên image production để lấy điểm benchmark.

**P-06a — H0-R:** đo thời gian chờ và chạy fresh deep-scrub, thời gian local-X verify, byte đọc, CPU/disk/network và ảnh hưởng client. Tách chi phí recovery/backfill khỏi chi phí xác minh. Báo số PG/object/byte thực sự được H0-static bao phủ; không chia tổng thời gian cho toàn dataset nếu chỉ kiểm mẫu.

**P-06b — H0-W:** so các run độc lập dưới đây, dùng RADOS new-object full-object writes với cùng size distribution, byte coverage, offered load và durability contract. Pin Ceph build/delta; nếu baseline và target khác version, tách so sánh version khỏi so sánh bật level. Native-only là **đối chứng**, không là Level 0 hay một bảo đảm H0.

| Run | Hook phải hoạt động | Chi phí cần tách |
| --- | --- | --- |
| Native-only | Native write completion, H0-W không tham gia | Latency/throughput nền của cùng đường I/O |
| L1_PRIMARY_BUFFER | A/B/E | Tính reference ở client, hash buffer primary, thời gian chờ ACK |
| L2_REPLICA_BUFFER | A/B/C/E | L1 + hash mọi replica bắt buộc, trả kết quả và chờ peer chậm nhất |
| L3_PERSISTED_READBACK | A/B/C/D/E | L2 + local readback sau durable completion trên X và mọi replica bắt buộc, queue/read amplification |

Mỗi run báo offered/achieved ops/s, success/error/timeout, p50/p95/p99 end-to-end và gate-wait latency, CPU/hash time theo node, disk read/write bytes, network, queue depth và số/tuổi request `COMMITTED_UNVERIFIED`. Level 3 không được đo bằng đọc lại ở client sau SUCCESS_ACK. Reader phải đạt W05 trước khi gọi kết quả là persisted-readback overhead.

Thay level phải đóng admission, đối soát in-flight, đổi run/policy revision rồi mở lại. L2/L3 cần đúng capability trên các peer; thiếu implementation thì NOT_RUN. Không dùng chi phí ước lượng thay thực đo, không chuyển kết quả test RADOS thành bảo đảm H0 cho RBD/RGW. Tải RBD/RGW P-01/P-02 chạy song song chỉ để đo ảnh hưởng lên SLO dịch vụ.

Thiết kế dự kiến L2 thêm chi phí hash/protocol và L3 thêm chi phí readback; **mức tăng thực và level phù hợp chỉ kết luận sau đo**, không hứa tỷ lệ phần trăm. Correctness và tình huống lỗi theo [15](15-TEST-H0-LEVEL-1-2-3.md).

## 8. P-07 — Tính kết quả và dự báo thời gian

- `Δ throughput (%) = (after / before − 1) × 100`.
- `Δ latency (%) = (after / before − 1) × 100`; số dương là chậm hơn.
- Báo cả số tuyệt đối, độ phân tán, số mẫu, throughput achieved và điều kiện nền. Nếu throughput giảm, latency thấp hơn có thể chỉ vì xử lý ít tải hơn.
- PASS theo cả SLO và regression budget đã khóa tại [06](06-GATE-VA-NGUONG.md). Correctness fail luôn chặn dù performance tốt.

Ước lượng thô cho cohort: `ceil(số OSD / batch size) × thời gian một batch đã đo + thời gian control/service + dự phòng`. Chỉ dùng sau khi chứng minh batch đó an toàn; cùng chia sẻ network/disk có thể làm batch lớn chậm hơn tỷ lệ tuyến tính. Cửa sổ đêm 3 giờ phải trừ phần verify/soak/xử lý sự cố; không dùng cả 3 giờ làm thời gian restart thuần.

Kết quả cuối phải phân biệt: **baseline steady-state / mixed canary / catch-up sau nâng / target steady-state**. Dùng bảng tại [12](12-BIEU-MAU-BANG-CHUNG.md).
