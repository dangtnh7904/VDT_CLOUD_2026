# 10 — RADOS/RBD clients, snapshot, fast-diff và object-map: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **474 dòng** do owner `10-rados-rbd-clients` sở hữu. Target sửa nhiều lỗi correctness/availability ở fast-diff, persistent write-back cache, journaling, mirroring và lock recovery. Gate nghiêm trọng nhất chỉ áp dụng khi dùng **RBD persistent SSD write-back cache**: cache file do base tạo có layout version 0, còn target yêu cầu version 1 và trả `-EINVAL`; không được nâng client hoặc xóa cache file trước khi xác minh cache đã sạch và có procedure chuyển đổi/khôi phục.
>
> **Trạng thái kiểm chứng:** đã đọc net diff, endpoint symbols, commit history và test/QA trong repository. Chưa chạy librbd/krbd/rbd-nbd, backup, PWL recovery hay rbd-mirror trên cluster thật; chưa có inventory image feature, client version hoặc mirror topology.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; source tree non-shallow và sạch; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [10-rados-rbd-clients.csv](./10-rados-rbd-clients.csv). CSV có 474 dòng, giữ nguyên 21 cột nền của master inventory và nối 6 cột phân tích.
- Thống kê owner: `A96/M345/D18/R15`, `+14.386/-7.854`; `P1=224`, `P2=250`; không có binary.

Disposition cuối của 474 dòng:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `conditional` | 28 | Runtime effect phụ thuộc feature/client/workload tương ứng |
| `mixed` | 51 | File có cả hunk finding-relevant và refactor/feature thường |
| `support` | 123 | Test, QA, docs hoặc helper hỗ trợ finding |
| `trivial` | 272 | Đã sàng lọc nhưng không có causal chain upgrade độc lập |
| **Tổng** | **474** | Khớp chính xác CSV |

Không có dòng `material` vô điều kiện: đây là client-side/component behavior và chỉ kích hoạt khi deployment dùng fast-diff, PWL, journaling, mirroring, self-managed snapshots hoặc gặp lock/blocklist path. Điều đó không làm các finding conditional kém nghiêm trọng.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Inventory client và image feature trước rollout.** Ghi rõ librbd/QEMU/krbd/rbd-nbd versions, `exclusive-lock`, `object-map`, `fast-diff`, `journaling`, persistent cache mode và mirroring mode. Daemon version của cluster không cho biết client nào đang thực thi code này.
2. **Gate riêng cho persistent SSD write-back cache.** Với cache file có từ 16.2.5, target không có in-place migration từ layout 0 sang 1; nó từ chối mở. Xác minh cache sạch, drain/flush theo procedure đã test và giữ recovery copy trước khi nâng client. Không xóa một cache có thể chứa dirty data.
3. **Backup/diff phải kiểm tra correctness trước performance.** So fast-diff target với một full/reference diff trên snapshot chain có grow, shrink, discard, clone/parent và “beginning of time”; so checksum/restore result, không chỉ thời gian hoặc byte count.
4. **RBD journaling cần discard regression test.** Target sửa cả journal growth/hang và một assert do event lifetime. Workload discard/TRIM phải được chạy với journal enabled và quan sát local client; chỉ nhìn health của rbd-mirror có thể bỏ sót lỗi client.
5. **Nếu dùng rbd-mirror, canary failover/failback là bắt buộc.** Target sửa primary/demotion, snapshot unlink-at-capacity, replay/resync và blocklist shutdown. Kiểm tra cả hai site, không suy ra an toàn từ trạng thái một daemon.
6. **Blocklist/lock recovery phải được thử ở client thật.** Target cải thiện propagation `EBLOCKLISTED`, kickstart exclusive-lock và tự phục hồi `rbd_support`; mixed client versions có thể phản ứng khác nhau với cùng failure.
7. **Không chạy `rados cppool` như một smoke test vô hại.** Target sửa việc xác định self-managed snapshot mode để không bỏ qua guard. Đây là thao tác dữ liệu riêng, không thuộc validation rolling upgrade thông thường.

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro khi kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| RBD-001 | Fast-diff/object-map correctness và local path | `fast-diff` + object-map; diff/export/backup | client canary/post-upgrade | Cao | High |
| RBD-002 | SSD PWL layout 0→1 | Persistent cache mode `ssd`, cache file từ base | client restart/rollback | **Cao; compatibility boundary** | High |
| RBD-003 | PWL ordering, recovery và cache-state hardening | RWL/SSD persistent cache | restart/recovery/I/O | Cao | High |
| RBD-004 | Journal event/discard hang và assert | RBD journaling + discard/multi-object I/O | client I/O | Cao | High |
| RBD-005 | Reliable self-managed-snapshot query | `rados cppool`/pool snapshot tooling | operator action | Cao theo thao tác | High |
| RBD-006 | Mirror snapshot/replay/failover lifecycle | Journal hoặc snapshot mirroring | mixed sites/failover | Cao | High |
| RBD-007 | Exclusive-lock/watch/blocklist recovery | Lock handover, reconnect, blocklist | mixed clients/failure | Trung bình-cao | High |

Mức rủi ro là hậu quả khi điều kiện đúng; likelihood và applicability cần As-Is riêng.

## 4. Phát hiện chi tiết

### RBD-001 — Fast-diff/object-map sửa correctness và có local optimization có điều kiện

**Evidence.** Các dòng CSV `1286`, `1291`, `1294`–`1297`, `1353`, `1358`–`1359`, `1373`, `1384`–`1386` cùng test/workunit diff map vào RBD-001. Chuỗi endpoint gồm:

- `c06858d217d20bb59050d42ca53caeeadd918444`: sort/merge extents vì consumer như QEMU giả định offset order;
- ranged diff, propagate range tới parent, skip intermediate snapshots, và các fix grow/shrink/hole/`OBJECT_PENDING` trong `object_map::DiffRequest`;
- `9f7f52a88eaf5d67065909c69d1078911907f233`: dùng in-memory end object map cho diff từ đầu thời gian, nên request có thể được trả local;
- `2749dd34f1edddd33ba9b8c3d522d7df0e52eb90`: cố giữ object map của head trong memory bằng exclusive-lock trong lúc diff;
- `a92c533e56e65906e34a3a61e2af0f66c23d2954`: dùng snap context mới khi client sở hữu exclusive lock.

**Trước → sau.** Base có nhiều edge mà extent có thể sai thứ tự/range, snapshot grow/shrink hoặc parent inclusion cho kết quả không đúng mong đợi. Target có behavior xác định hơn và có thể tránh cluster-wide metadata traversal khi object map phù hợp đã ở memory.

**Điều kiện và giới hạn.** Optimization cần fast-diff/object-map hợp lệ và end version map có thể dùng; target cố acquire exclusive-lock cho head nhưng không biến mọi diff thành local. Object-map invalid hoặc feature không bật vẫn cần fallback/rebuild theo contract. Không có bằng chứng cho một mức tăng tốc cố định trên workload đích.

**Mixed-version.** Client library thực hiện diff quyết định behavior; hai backup workers base/target có thể trả timing hoặc extent sequence khác trên cùng image. Upgrade cluster daemon không tự bật image feature.

**Kiểm chứng.** Chọn image có parent, nhiều snapshots, grow/shrink, zero/discard và object-map valid/invalid. So target fast-diff với full/reference diff, kiểm checksum của export/restore và tính ổn định extent order; thử khi exclusive-lock lấy được và không lấy được. Stop rollout client backup nếu byte range hoặc restored content lệch, dù job nhanh hơn.

**Đánh giá.** Rủi ro **cao cho backup/sync correctness**, confidence **high**.

### RBD-002 — Persistent SSD cache của base không tương thích trực tiếp với target layout gate

**Evidence endpoint.** Các dòng `1305`–`1306`, `1312`, `1319`, `1323`, `1330` và PWL QA/docs. Trong base `WriteLogPoolRoot.layout_version` mặc định 0; `ssd::WriteLog::initialize_pool()` tạo root nhưng không set version. `010b0524d0f6a6a92bfbf723759b162067c8d546` đổi SSD log-entry pointers sang 64 bit và ghi rõ “on-disk format change”. `15f62d23d1a7540820ebf57bb7b41b504fdfa356` đặt `SSD_LAYOUT_VERSION=1`; target đọc existing superblock và trả `-EINVAL` nếu version khác 1.

**Trước → sau.** Một SSD PWL file tạo bởi 16.2.5 có version 0. Khi target client giữ metadata `present=true` và mở file đó, target không migrate mà đóng block device và fail init. Đây là proof trực tiếp giữa endpoints, không phải suy luận từ commit title.

**Data/rollback boundary.** Cache file có thể chứa dirty user data chỉ tồn tại local trước khi writeback hoàn tất. Xóa/recreate file để vượt gate có thể mất dữ liệu. Chiều ngược lại cũng không được code chứng minh an toàn: base không có version gate cho cấu trúc target đã đổi pointer width. Vì vậy không reopen cache layout 1 bằng base như một rollback thử nghiệm tùy ý.

**Applicability.** Chỉ áp dụng cho RBD persistent cache mode `ssd` với cache file hiện hữu. RWL/pmem không dùng chính SSD layout transition này, dù vẫn cần RBD-003.

**Kiểm chứng/hành động.** Inventory image/client có PWL, mode, file path, cache state `present/clean/empty` và exclusive-lock owner. Thiết kế drain/flush/invalidate bằng procedure upstream/vendor đã test; giữ recovery copy và chứng minh data đã tới cluster trước client switch. Trong lab, mở bản sao cache base bằng target và xác nhận failure signal dự kiến; không thử trên cache dirty duy nhất.

**Đánh giá.** Rủi ro **cao, compatibility/rollback boundary**, confidence **high**.

### RBD-003 — Target sửa nhiều lỗi PWL có thể ảnh hưởng durability, ordering và restart

**Evidence.** Các dòng `1303`–`1331`, CLI/status `2617/2619`, test `2456/2457/2486` và QA PWL. Các commit tiêu biểu:

- `24a30a83491b2002914806a29a2a26448d1e4a4e`: persist đúng `write_data_pos`; base behavior có thể làm recovery không thể thực hiện;
- `c5b13b73c596c0e0219ef087f8cc164c0ceff6f0`: tránh ghi `first_free_entry` rác ra media, commit mô tả cache corruption và dirty-data loss;
- `17791d999fa9161c574e9333053cfff34e1beab0`: giữ write order khi async-read cache trả completion đảo thứ tự;
- `b388a34470d27f7cc7965b467f554741c52cc766`: chặn retire/overwrite trong lúc SSD async read;
- `311bcf17d5fca40edd07b04d847434ade3e29410`: tránh deadlock khi PWL init thất bại;
- `9df3cf82346491d758f2a0b4df4bfc2328216bff`: sửa encoding endianness của flags.

**Trước → sau.** Target harden cả media metadata, recovery scan, ordering và failure cleanup. Đây không phải một migration tự động và cũng không chứng minh mọi cache cũ recover được; RBD-002 có thể chặn target trước khi load entries.

**Mixed-version.** PWL là cache local của client đang giữ exclusive-lock. Handover VM/QEMU hoặc worker giữa base và target mà không drain rõ ràng có thể đổi code đọc/ghi cùng cache metadata. Cluster HEALTH_OK không quan sát đầy đủ dirty local cache.

**Kiểm chứng.** Trên disposable image, chạy overlapping writes, flush, discard, crash/restart và lock handover cho mode thực dùng; kiểm checksum sau recovery, cache clean/empty state, journal/cache metrics và client latency. Mọi client upgrade phải có stop condition nếu cache init lỗi, dirty count không về 0 hoặc checksum lệch.

**Đánh giá.** Rủi ro **cao khi PWL bật**, confidence **high**.

### RBD-004 — Journaled discard có thể treo/phình journal hoặc assert ở base path

**Evidence.** Các dòng `1288`–`1289`, `1358`–`1359`, test `2472`, `2474`, `2475` và workunit `1075`. `336204670b7a64b4014c55c35ac9217812343d27` sửa aligned discard chỉ cập nhật object extents mà không cập nhật image extents: local client chờ journal commit vô hạn và journal tăng mãi, trong khi rbd-mirror có thể không báo health. `2d6f6a115036078060b4eff0c56bb46b83bbd78a` phục hồi quan hệ một journal event trên một image request để tránh event bị cleanup khi object request khác còn tham chiếu, gây assert.

**Điều kiện.** RBD journaling phải bật; edge nổi bật ở discard bị align/chia qua nhiều object hoặc overlap. Đây là client-side data path, không phải OSD format change.

**Mixed-version.** Client base/target phát journal events khác nhau. Nếu VM/QEMU/rbd-nbd worker được nâng từng phần, cùng image workload có thể chỉ treo ở worker cũ; health của mirror daemon không thay thế client telemetry.

**Kiểm chứng.** Chạy discard/TRIM aligned, misaligned và cross-object trên image journaling; quan sát I/O completion, journal object growth, client stack/timeout, mirror replay lag và data after reopen. Stop nếu request không complete hoặc journal tăng không hội tụ.

**Đánh giá.** Rủi ro **cao theo feature/workload**, confidence **high**.

### RBD-005 — `rados cppool` không còn nhầm “chưa có map/lỗi pool” với “không dùng self-managed snapshots”

**Evidence.** Các dòng `1259`, `1279`, `1280`, `1282`, `2442`, `2592` map duy nhất tới commit `319ada6774d5e6f4fdf0b06eace63da7f82941b7`. Base API boolean có thể trả `false` khi RADOS client mới chưa có OSDMap hoặc pool không tồn tại, giống kết quả pool không ở self-managed snapshot mode. Caller `rados cppool` vì thế có thể không in warning/không yêu cầu confirmation guard.

**Trước → sau.** Target query chờ/refresh map và tách error khỏi false; CLI không tiếp tục dựa trên một negative giả. Đây là correctness/safety cho operator tool, không tác động steady-state RBD I/O.

**Kiểm chứng/hành động.** Không dùng copy pool trong upgrade trừ change riêng. Trong lab, thử existing normal pool, self-managed snapshot pool và nonexistent pool bằng fresh client; xác nhận target phân biệt return/error và guard. Xác minh dữ liệu copy trước khi xóa nguồn bất kể CLI warning.

**Đánh giá.** Rủi ro **cao nếu thao tác `cppool` được dùng**, confidence **high**.

### RBD-006 — Target harden mirror demotion, snapshot lifecycle và blocklist shutdown

**Evidence.** Các dòng `1196`, `1298`, `1379`–`1383`, `2625`–`2656` cùng mirror tests/workunits. Bốn commit chính:

- `3885255ea0ccc56a6c55bcef26729301fd6f787b` localize mirror-snapshot remove về primary cluster để tránh race lấy exclusive-lock giữa site;
- `ba5364196433a54368532b0ae6ac2f58e568f65f` bỏ replay/resync khi remote không primary; commit mô tả một livelock và một đường có thể trash image vừa demote, gây data loss;
- `7d63ab5f97192b2bde876f6d0acd818d4789e612` đổi unlink-at-capacity sang newest snapshot và nâng capacity 5 như workaround cho race producer/replayer;
- `8d242edf1c61410461b05570d7968dad0b67f118` resume pending shutdown khi snapshot replayer gặp error/blocklist, tránh treo toàn daemon với mirror lock giữ lâu.

**Trước → sau.** Target giảm các race trong failover/failback và snapshot queue. Capacity change là mitigation được commit mô tả là workaround, không phải proof mọi concurrency edge đã biến mất.

**Mixed sites.** Version của rbd-mirror và librbd ở từng site quyết định behavior. Demote/promote trong lúc hai site hoặc workers chạy code khác nhau là đúng phase cần canary; image feature/state được chia sẻ nhưng state machine local khác.

**Kiểm chứng.** Chụp peer/image primary state, mirror snapshot queue, replay/resync lag và schedule. Trên staging chạy failover/failback loop, demote giữa snapshot sync, capacity pressure, blocklist/restart và deletion. Pass khi chỉ một primary, snapshot links/base hợp lệ, lag hội tụ, không split-brain/livelock và checksum hai site khớp.

**Đánh giá.** Rủi ro **cao nếu mirroring bật**, confidence **high**.

### RBD-007 — Lock/watch/blocklist path tiến bộ nhưng cần fault injection ở client thật

**Evidence.** Các dòng `1271`, `1287`, `1290`, `1342`–`1343`, `1347`–`1351`, `2197`–`2202`, `2659` và test/workunit liên quan. `ba3871568a8224a2b19c17e09d772eb2e427f765` trả `EBLOCKLISTED` thay vì để lock request chờ vô hạn; `97b3d05d44c5bed76ef311231015342c5ed50c4c` kickstart exclusive-lock state machine khi rewatch/reacquire; `ea3e1f47e400644e7a2b65fefa2af35ec68cdb6c` dùng `ERESTART` cho internal shutdown race để không lẫn với alias đặc biệt `EBLOCKLISTED`; `5bc2d002e70959f177543ba72946d60e6d2ce4ab` cho `rbd_support` tự dựng lại RADOS client/handlers sau blocklist thay vì restart toàn MGR.

Target còn sửa RefreshRequest retry/ENOENT, pool-validation lockup và một số rbd-nbd/krbd reconnect edges. Các feature/schedule/perf hunk khác trong cùng file được giữ `mixed/trivial`, không được coi là finding độc lập.

**Mixed-version.** Mỗi librbd/krbd/rbd-nbd client tự xử lý watch và lock. Target client có thể trả lỗi rõ rồi recover trong khi base client treo; MGR active version quyết định recovery của module `rbd_support`.

**Kiểm chứng.** Trên canary tạo controlled lock contention, watch disconnect, client blocklist và MGR failover; quan sát error code, request completion, exclusive-lock owner, rewatch, task/schedule recovery và ảnh hưởng module MGR khác. Stop nếu I/O treo, lock không có owner hợp lệ hoặc phải restart toàn MGR để module phục hồi.

**Đánh giá.** Rủi ro **trung bình-cao theo failure path**, confidence **high**.

## 5. Trivial/support changes

- **123 support rows** gồm unit/integration tests, RBD/krbd/rados QA suites, mirror workunits, docs và helper dùng để chứng minh bảy finding; chúng chưa phải 123 rủi ro riêng và chưa được chạy ở đây.
- **272 trivial rows** chủ yếu là suite topology/marker rename, test maintenance, CLI formatting/convenience, crypto/migration feature work không có upgrade edge đã chứng minh, refactor và ancillary tools.
- **28 conditional + 51 mixed rows** được map tới RBD-001…RBD-007 trong CSV. Một file có thể hỗ trợ nhiều finding nên không cộng row theo ID để suy ra tổng.

Tổng `28 conditional + 51 mixed + 123 support + 272 trivial = 474`; mọi owner row đã qua relevance screen.

## 6. Validation matrix đề xuất

| Scenario | Tiền điều kiện / pha | Quan sát bắt buộc | Stop condition |
| --- | --- | --- | --- |
| Client/feature inventory | Trước rollout | client binary, image features, cache/mirror mode | Còn client hoặc feature owner không xác định |
| Fast-diff golden test | Snapshot chain + clone/grow/shrink/discard | extent set/order, full-diff parity, restore checksum | Missing/extra range hoặc checksum lệch |
| SSD PWL compatibility | Bản sao cache base, state đã chụp | layout/version, init result, clean/empty/dirty state | Target không mở hoặc recovery không được chứng minh |
| PWL crash/recovery | Disposable image, mode thực dùng | ordering, checksum, dirty drain, reopen | Init deadlock/error, dirty data mất/lệch |
| Journaled discard | Journaling bật | completion, journal growth, client/mirror status | Hang/assert hoặc journal không hội tụ |
| Mirror failover/failback | Hai site staging | primary, snapshot links, replay/resync, checksum | Split-brain, livelock, unexpected trash/data mismatch |
| Lock/blocklist recovery | Client canary + controlled fault | error propagation, lock owner, rewatch, module recovery | I/O treo hoặc cần MGR-wide restart |
| Selfmanaged snap query | Lab pools | true/false/error và CLI confirmation guard | Nonexistent/error bị coi là normal false |

Các scenario là thiết kế kiểm chứng; chúng không ủy quyền xóa cache, copy/xóa pool, blocklist client hay failover production.

## 7. Giới hạn và kết luận

- Chưa có As-Is client/image inventory nên chưa biết PWL, journaling, fast-diff hay mirroring finding nào áp dụng.
- Không tuyên bố mức tăng backup/IOPS/latency: local fast-diff path và PWL fixes phải được benchmark trên workload thật sau correctness gate.
- RBD-002 là compatibility boundary có bằng chứng endpoint trực tiếp, nhưng procedure chuyển cache cụ thể còn phụ thuộc integration/vendor; báo cáo không đề xuất xóa cache file.
- Các tests/QA trong repository đã được đọc nhưng chưa chạy. OpenStack impact chỉ là conditional nếu QEMU/librbd/Cinder/backup stack thực dùng các path này.
- Chưa đủ bằng chứng môi trường để đưa GO/NO-GO Production; gate tối thiểu là client/feature inventory, fast-diff golden test và — nếu dùng — PWL/mirror/blocklist canary.
