# 01 — OSD, PG, peering, recovery/backfill, scrub, replication và EC

> **Trạng thái:** hoàn thành phân tích code-level cho owner `01-osd-pg-recovery`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), lấy net diff trực tiếp trong `ceph16.2.15/ceph` với `--find-renames`.
>
> **Danh sách file:** [01-osd-pg-recovery.csv](./01-osd-pg-recovery.csv). Báo cáo chỉ phân tích source; không cho phép chạy `repair`, `mark_unfound_lost`, trim PGLog, thay cờ cluster, benchmark OSD hay thao tác trên cluster thật.

## 1. Phạm vi và độ phủ

CSV thành phần là tập con giữ nguyên thứ tự của inventory, gồm **45 dòng**: `A 2`, `M 42`, `R 1`, tổng `+2.980/-865`; ưu tiên đọc `P0 36`, `P1 1`, `P2 8`. Các vùng bằng chứng chính:

- QA cho backfill/EC/health và CLI: inventory `754`, `941`, `993`, `1034`, `1046`;
- runtime OSD/PG/recovery/peering/scrub/EC: `1577–1616`;
- test OSDMap, PGLog và caps: `2510–2512`.

`src/osd/OSDMap.*` và CRUSH do `04-mon-osdmap-crush` sở hữu; định nghĩa/default option do `06-config-defaults` sở hữu. `src/test/test_snap_mapper.cc` (inventory `2548`, owner `15`) và `src/tools/ceph_objectstore_tool.cc` (`2564`, owner `02`) chỉ được đọc làm ngữ cảnh test/tool, không được thêm vào CSV này.

`P0/P1/P2` là thứ tự đọc, không phải mức rủi ro. Không có test repository hay lệnh cluster nào được chạy; các test dưới đây chỉ được đọc.

CSV vẫn giữ đủ **45/45 dòng** để truy vết. Markdown chỉ nâng một hành vi thành finding khi có đường tác động cụ thể tới rolling/mixed-version, restart, recovery, dữ liệu, availability, rollback hoặc validation của nâng cấp. Loại file không phải bộ lọc tuyệt đối: thay đổi client ở `OSD-013` vẫn được giữ vì có thể đổi kết quả RBD theo primary version; ngược lại test, build, log và tối ưu runtime không chứng minh được tác động upgrade chỉ nằm trong mục trivial/support.

## 2. Kết luận điều hành

| ID | Hành vi đã xác minh | Priority | Rủi ro nâng cấp | Confidence |
| --- | --- | --- | --- | --- |
| `OSD-001` | Async recovery của EC không còn loại shard làm acting set xuống dưới `min_size` | P0 | Cao theo điều kiện degraded EC | high |
| `OSD-002` | Hinfo EC hỏng/thiếu không còn dẫn thẳng tới assert trong backfill/deep-scrub; lỗi được chuyển thành failed pull, unfound hoặc inconsistency | P0 | Cao nếu đã có metadata EC lỗi | high |
| `OSD-003` | PGLog `dups` phình được cảnh báo và trim dần theo số lượng, không còn phụ thuộc version cũ | P0 | Trung bình; cao nếu OSD đã không boot vì DB/PGLog quá lớn | high |
| `OSD-004` | Scrub sửa trạng thái bị kẹt, dùng đúng acting set khi remap và làm cứng reservation/event cũ | P0 | Trung bình; cao nếu scrub/repair đang treo | high |
| `OSD-005` | Partial-recovery clean regions được persist đúng qua restart | P0 | Trung bình; ảnh hưởng recovery bandwidth/window | high |
| `OSD-006` | Peering/backfill sửa ưu tiên acting trong stretch mode và khôi phục accounting sau khi backfill bị ngắt | P0 | Cao theo topology/điều kiện | high |
| `OSD-007` | Lower bound trim OSDMap của cluster được persist và dùng để kiểm tra past intervals/map gap | P0 | Trung bình; liên quan peering sau restart/map gap | high |
| `OSD-008` | OMAP range delete và EC getattr phân biệt đúng vùng dirty, object thiếu và attr thiếu | P0 | Cao cho correctness ở workload tương ứng | high |
| `OSD-010` | Chuyển legacy SnapMapper giữ nguyên suffix object; chỉ liên quan store cũ chưa có `SNAPMAPPER2` và không tự sửa key đã hỏng | P0 | Cao nhưng activation rất hẹp | high |
| `OSD-011` | OSD dùng mClock có thể benchmark/persist capacity khi restart; Pacific vẫn dùng WPQ mặc định | P0 | Trung bình khi đã bật mClock; thấp với WPQ mặc định | high |
| `OSD-012` | Startup/shutdown/map-delivery fail rõ hoặc an toàn hơn ở một số đường lỗi | P0 | Trung bình, phụ thuộc lỗi nền | medium |
| `OSD-013` | `rbd-read-only` được phép `metadata_list` đúng object; grant `rbd` được thu hẹp | P0 | Trung bình cho client/cap tương ứng | high |
| `OSD-014` | Object manifest/tiering phục hồi adjacent clone trước khi tính refcount và truyền đúng clone context | P0 | Cao nếu dùng `set_chunk`/dedup manifest với snapshot degraded | high |

Không có một “protocol OSD mới” duy nhất trong owner này. Phần lớn thay đổi có hiệu lực theo binary của OSD đang giữ vai trò primary hoặc đang xử lý local shard. Vì primary có thể đổi trong rolling upgrade, cùng một PG có thể lần lượt đi qua hành vi base và target; validation mixed-version phải cố ý đổi primary, gây recovery và scrub, không chỉ kiểm tra `HEALTH_OK`.

## 3. Findings chi tiết

### OSD-001 — EC async recovery giữ acting set không thấp hơn `min_size`

**Owner/evidence.** Inventory `1593–1594`, symbol `PeeringState::choose_async_recovery_ec` tại base `src/osd/PeeringState.cc:2183` và target `:2195`. Commit `bca977cc7e2767a641c12e42103a7cd19a118fcc`.

**Trước → sau.** Base thử bỏ từng EC shard khỏi `want` và chấp nhận nếu `recoverable(candidate_want)` đúng. Khi semantics của `recoverable` cho phép recovery dưới `min_size`, nhánh này có thể làm acting set nhỏ hơn `pool.info.min_size`; PG vẫn recoverable về mặt giải mã nhưng không phục vụ I/O. Target đếm shard thực trong `want_acting_size` và chỉ loại candidate nếu số còn lại vẫn `>= min_size` **và** còn recoverable. Nhánh replicated đã có kiểm tra `min_size` riêng; thay đổi này dành cho EC.

**Điều kiện/hiệu lực.** Tự động khi primary target chọn async recovery cho EC PG có candidate vượt `osd_async_recovery_min_cost`. Không cần migration hay repair. Trong mixed phase, version của primary quyết định lựa chọn acting; sau full upgrade mọi primary có guard mới.

**Tác động/đánh giá.** Category: availability/correctness. Rủi ro **cao theo điều kiện** vì PG có thể mất khả năng I/O trong degraded recovery ở base; confidence `high` từ guard endpoint và commit intent. Chưa biết cluster có EC pool, `min_size`, async-recovery override hoặc topology failure nào.

**Test đã đọc.** Suite ngữ cảnh `qa/suites/rados/thrash-erasure-code/…/minsize_recovery.yaml` và recovery-overrides; responsible commit không thêm regression test chuyên biệt. Cần fault-injection mixed-version.

### OSD-002 — Hinfo EC lỗi được cô lập thay vì làm OSD assert

**Owner/evidence.** Inventory `1578–1579` và QA `993`. Symbols `ECBackend::get_hash_info` (base `src/osd/ECBackend.cc:1819`, target `:1828`), `continue_recovery_op` (`:589` ở cả hai) và `be_deep_scrub` (base `:2517`, target `:2529`). Commits:

- `8b8fa0e9a43110be60392924f995e7507aa5dbc9`: không tạo/cache `HashInfo` giả khi `stat` lỗi; phân biệt `create`;
- `0f4bd5bfa1d34c25a64e10c89fe15c8d65699d83`: failed pull thay cho assert trong backfill;
- `b39d8bfe84811b35b80d05f6d9340d8e7127b67f`: deep-scrub ghi `read_error`/`ec_size_mismatch` thay vì assert.

**Trước → sau.** Base có thể biến lỗi `stat` thành `HashInfo` rỗng rồi truyền trạng thái sai sang shard khác; recovery assert khi không lấy được hinfo và deep-scrub assert nếu thiếu chunk hash. Target trả null cho lỗi không phải `ENOENT` hoặc khi `create=false`, xóa recovery op hiện tại rồi gọi `on_failed_pull` để thử shard khác/đánh dấu missing; deep-scrub hoàn thành map với cờ inconsistency.

**Điều kiện/hiệu lực.** Chỉ kích hoạt khi attr `hinfo_key` thiếu, decode lỗi, size/hash không khớp hoặc backend `stat` lỗi trên EC object. Tự có sau restart target; không sửa metadata ngay. Repair vẫn là hành động riêng sau khi xác định authoritative shard.

**Mixed/full.** OSD chạy target không còn crash ở các nhánh đã sửa; OSD base vẫn có thể assert nếu nó nhận đúng shard lỗi. Primary target điều phối failed-pull tốt hơn nhưng không thay thế dữ liệu không còn đủ shard. Full upgrade đồng nhất error handling.

**Tác động/đánh giá.** Category: availability/correctness/detectability. Rủi ro exposure **cao**, rủi ro của code mới trung bình-thấp; confidence `high`. Target ưu tiên giữ daemon sống và biểu diễn object là inconsistent/unfound, không hứa tự phục hồi khi không đủ bản đúng.

**Test đã đọc.** `qa/tasks/ec_inconsistent_hinfo.py` cố ý xóa `hinfo_key`, chạy deep-scrub/repair, backfill từ primary/non-primary và case hai shard lỗi; test kỳ vọng clean khi còn nguồn tốt và `backfill_unfound` khi không đủ. Chưa chạy.

### OSD-003 — PGLog duplicate inflation có guard runtime và công cụ offline có điều kiện

**Owner/evidence.** Inventory `1591–1592`, `2511`; symbols `PGLog::IndexedLog::trim` (`src/osd/PGLog.cc:56`) và `PGLog::read_log_and_missing`/`NUM_DUPS_WARN_THRESHOLD` (`src/osd/PGLog.h:1447` target). Commits `de987abbf3be71f3a35dc60b53bce34cb32fec75` và `c30f04091ca367b4d68bccd42a116cbcb2e0c0c7`; context tool commit `4393b743c4f7ab0717ad5085aec9671ffa82a22f`.

**Trước → sau.** Base dừng trim `dups` khi version đạt `earliest_dup_version`, nên một tập duplicate đã phình có thể không giảm theo giới hạn số lượng. Target giữ tối đa `osd_pg_log_dups_tracked` (default context `3000`) và trong mỗi lần trim loại tối đa `osd_pg_log_trim_max` (default `10000`), bất kể version; việc xóa được trộn với write PGLog để tránh một transaction/tombstone burst quá lớn. Khi quá trình load đã đạt ngưỡng `2 * osd_pg_log_dups_tracked` và gặp thêm entry, target log cảnh báo và chỉ dẫn `ceph-objectstore-tool --op trim-pg-log-dups`.

Lịch sử có lần thêm size-based trim/tool (`d49ff13c80b`/`1f3fede173c`) rồi revert (`ea7429d37fb`/`0b5a13bf982`); kết luận dựa trên endpoint cuối là hai commit nêu trên cộng tool `4393b743c4f`, không coi trạng thái trung gian là target.

**Điều kiện/hiệu lực.** Automatic trim chỉ tiến triển khi PGLog tiếp tục đi qua đường trim/write. OSD đã quá phình đến mức không boot không thể nhận lợi ích runtime; offline tool là recovery chuyên biệt trên OSD dừng, không phải bước bảo trì hàng loạt. Upgrade không tự chạy tool.

**Mixed/full.** Primary/base và target có policy trim khác nhau; khi primary chuyển version, tốc độ hội tụ `dups` có thể đổi. Format dup hiện hữu không phải migration mới trong finding này. Sau full upgrade, warning/trim mới áp dụng nhất quán.

**Tác động/đánh giá.** Category: availability/space/performance. Rủi ro nâng cấp trung bình; exposure cao nếu RocksDB/PGLog đã quá lớn. Confidence `high` cho code, `medium` cho applicability vì chưa có số `dups`/PG, DB free space và boot status.

**Test đã đọc.** `src/test/osd/TestPGLog.cc::PGLogTrimTest` có expectations size-based nhưng net diff của test chủ yếu đi qua chuỗi add/revert; không có test endpoint mô phỏng OSD không boot. Tool commit có quy trình thử thủ công trong commit message, chưa chạy ở đây.

### OSD-004 — Scrub không còn kẹt ở các đường abort/remap/reservation

**Owner/evidence.** Inventory `1597–1598`, `1606–1607`, `1613–1616`. Các symbols chính: `PgScrubber::verify_against_abort` (base/target `src/osd/pg_scrubber.cc:111`), `should_abort`, `get_replicas_maps` (base `:696`, target `:779`), `scrub_compare_maps` và scrub FSM/listener. Commits trọng tâm:

- `73950d303d752899b3954ed1620926bb695cfb87`: clear state cả khi epoch abort bằng `m_last_aborted` và tách `noscrub` khỏi `nodeep-scrub`;
- `8f330ae6aba9a7b05346b155b19371f5a95caf8a`: yêu cầu/so sánh map từ actual acting set, không dùng `acting_recovery_backfill` khi remapped;
- `15d0fdbe81e9aef4e61e7533e1ce96304e7c15c1`: late reservation grant là event trễ hợp lệ, không phải lỗi;
- `0b615587ec899834612fb8c89322e0625ac06ba1`, `3632e8c470bd6f726d169f0ed03690d4ea9d3bcd` và `643715be74d0e6ec412eb7a3f239622a64dc0d8b`: nhận diện stale replica message, bỏ digest-update giả và buộc repair scrub đi qua resource acquisition.

**Trước → sau.** Base có thể bỏ reschedule mà không clear state khi deep-scrub gặp `noscrub`, để FSM kẹt ở `ActiveScrubbing/PendingTimer`; trong remap, nó có thể hỏi tập recovery/backfill thay vì các replica đang active. Target clear đúng state, dùng đúng acting set, bỏ/giảm severity event trễ và giữ reservation discipline cho repair.

**Điều kiện/hiệu lực.** Tự động khi scrub/deep-scrub/repair gặp flag, remap hoặc delayed message. Không cần migration. Việc **bật/tắt flag hay gọi repair** không được coi là phần tự động của upgrade.

**Mixed/full.** Primary điều phối scrub; primary target mang phần lớn fix, nhưng replica base vẫn xử lý protocol cũ của nó. Các hunk giữ message generation/versioning hiện hữu, song repository không có matrix mixed `16.2.5/16.2.15` cho mọi stale event; phải test. Sau full upgrade FSM đồng nhất.

**Tác động/đánh giá.** Category: availability/correctness/operability. Rủi ro `trung bình`, tăng nếu scrub backlog, remap liên tục hoặc PG đã stuck; confidence `high` từ state transition và commit reproduction. Không suy ra rằng upgrade tự làm sạch mọi scrub backlog.

**Test đã đọc.** `src/test/osd/TestOSDScrub.cc`, `qa/tasks/scrub_test.py` và các standalone scrub scripts làm context; responsible commits không thêm một test duy nhất bao phủ toàn bộ chuỗi flag/remap/reservation. Chưa chạy.

### OSD-005 — Partial recovery giữ được clean regions qua restart

**Owner/evidence.** Inventory `1591` và type context `1604–1605`. Symbol `PGLog::_write_log_and_missing` tại `src/osd/PGLog.cc:933` trong hunk; `pg_missing_item::encode/decode` ở target `src/osd/osd_types.h:4597`. Commit `a4ccd4970b3b17f289953c439f73cd4ab1295ef4`.

**Trước → sau.** Base encode missing item với feature chỉ dựa vào `may_include_deletes`; khi feature mask bằng 0, `clean_regions` không được persist và decode cũ đánh dấu toàn object dirty. Target luôn encode với `CEPH_FEATUREMASK_SERVER_OCTOPUS`, ghi cả `clean_regions`. Vì vậy restart giữa partial recovery không biến phần còn thiếu thành whole-object recovery chỉ do mất metadata progress.

**Điều kiện/hiệu lực.** Kích hoạt khi partial recovery đã ghi state rồi OSD restart trước khi hoàn tất. Tự động trên target; không đổi object data format hay cần repair.

**Mixed/full.** Đây là state local trong PG metadata. Decoder ở cả hai endpoint Pacific hiểu form có sentinel Octopus; không thấy feature negotiation mới trong hunk. Tuy vậy, nếu primary/base tiếp tục ghi form cũ, progress mới vẫn có thể bị mất ở lần persist đó; full upgrade mới đồng nhất writer.

**Tác động/đánh giá.** Category: recovery efficiency/availability window. Rủi ro `trung bình` vì whole-object fallback vẫn đúng về dữ liệu nhưng kéo dài recovery và I/O; confidence `high`. Chưa có số object lớn/partial recovery hoặc restart frequency của cluster.

**Test.** Các suite partial-recovery trong `qa/suites/rados/thrash/2-recovery-overrides` là context; responsible commit không thêm regression test trực tiếp cho restart + encoded clean regions.

### OSD-006 — Peering/backfill giữ đúng candidate và accounting sau gián đoạn

**Owner/evidence.** Inventory `1593–1594`. Commits:

- `7f99d8997abe24232e96464eb7b47091e13a5e03` sửa `bucket_candidates_t::pop_osd/get_ord` trong `calc_replicated_acting_stretch` để ưu tiên acting hiện tại thay vì đảo thứ tự;
- `2a0451af54173d92c8292686c370ea1b06a4730a` recache `peer_bytes` ở mọi lần `PeeringState::activate`, trước nhánh log, để backfill reservation sau interruption có số byte;
- `eb463199daf55bf5c34310de13ef93d9163cd2fa` loại peer down khỏi `peer_purged` trước khi ra quyết định;
- `b010892d30750e48810a64a87cb9ef542006d293` chỉ restart snap trim sau khi scrub thật sự kết thúc.

**Trước → sau.** Base stretch selection lấy candidate từ cuối danh sách đã sort, vô tình giảm ưu tiên OSD đang acting. Base cũng chỉ cache `peer_bytes` trong một nhánh, nên backfill bị ngắt có thể gửi lại reservation với accounting đã reset. Target giữ existing acting candidate đúng thứ tự và tái lập accounting mỗi lần activate.

**Điều kiện/hiệu lực.** Stretch fix chỉ áp dụng pool/topology stretch tương ứng; `peer_bytes` áp dụng backfill bị interrupt/reactivate. Tự động theo primary target; không có config migration.

**Mixed/full.** Primary version quyết định candidate/reservation. Khi primary đổi trong mixed phase, kết quả có thể khác nhưng vẫn dùng OSDMap/PG protocol hiện hữu. Cần thử primary failover giữa backfill, không chỉ nâng OSD không-primary.

**Tác động/đánh giá.** Category: availability/correctness/capacity safety. Rủi ro **cao theo topology/gián đoạn**, thấp hơn nếu không dùng stretch và backfill ổn định; confidence `high`. `qa/tasks/backfill_toofull.py` kiểm tra `backfill_toofull` và resume, nhưng không trực tiếp kiểm stretch ordering.

### OSD-007 — Cluster OSDMap trim lower bound được persist cho past intervals

**Owner/evidence.** Inventory `1580–1581`, `1588–1589`, `1593–1594`, `1604–1605`. Symbols `OSDService::build_incremental_map_msg` (base `src/osd/OSD.cc:1412`, target `:1413`), `OSD::handle_osd_map`, `PeeringState::check_past_interval_bounds` (base `:944`, target `:954`), `OSDSuperblock::encode/decode` (base `src/osd/osd_types.cc:5552`, target `:5568`). Commit chain:

- `0f03ee9410413fb9921f2642149bc858d35c0528` persist field mới vào superblock;
- `74e2bcccd5e2be04ba0387f555ce7c2fe32f34eb` dùng maximum lower bound nhận từ peers thay cho `oldest_map` local có thể lag;
- `336a3438aff7e59954070d114497bd802661fc2e` dùng bound này cho map-gap logic;
- `05e7a0693281b441bd7472b6860d552138cb1b37` đổi tên thành `cluster_osdmap_trim_lower_bound`;
- `45fae668dd189ff57999230d3ab3858629823c36` expose field trong admin-socket `status`;
- `0c78649033486f59f670e74889e8061540a0266a` tránh use-after-move khi tính `max_bytes` lúc build map message.

**Trước → sau.** Base giữ maximum oldest map ở biến service không bền vững và kiểm past-interval bound bằng `superblock.oldest_map` local, vốn có thể tụt sau cluster để giảm workload trim. Target ghi cluster lower bound vào OSDSuperblock version `10` (compat version vẫn `5`), tăng nó theo `MOSDMap` nhận được và dùng nó để nhận diện map gap/past intervals sau restart.

**Điều kiện/hiệu lực.** Tự động khi OSD nhận map target và ghi superblock. Có ý nghĩa khi local stored maps lag so với lower bound cluster hoặc OSD restart/peer sau trim. Không cần operator set field.

**Mixed/full/rollback.** MOSDMap rename/field nằm trong chain rộng hơn có code ngoài owner `01`; mixed-version phải được kiểm tra cùng report `04`. Superblock target dùng compat `5` nên base decoder có thể chấp nhận version mới theo cơ chế encoding, nhưng việc downgrade rồi ghi lại superblock có bảo toàn field target hay không chưa có test. Không tuyên bố rollback package an toàn từ code này.

**Tác động/đánh giá.** Category: peering correctness/availability/compatibility. Rủi ro `trung bình`; confidence `high` cho endpoint behavior, `medium` cho downgrade vì thiếu round-trip old-writer test.

### OSD-008 — OMAP range delete và EC getattr giữ đúng semantics recovery

**Owner/evidence.** Inventory `1595–1596`. Commits:

- `f8691d0f07fbd805282921d0c148f5f3602c0d7b` thêm `ctx->clean_regions.mark_omap_dirty()` trong `CEPH_OSD_OP_OMAPRMKEYRANGE` (base `src/osd/PrimaryLogPG.cc:7810`, target `:7837`);
- `8960b8530df5e0a8a39d8b226a11f3a4fa57c0ad` làm `getattr_maybe_cache` trả `-ENOENT` khi EC object không tồn tại, giữ `-ENODATA` khi object có nhưng attr thiếu (base `:15366`, target `:15412`).

**Trước → sau.** Base range-delete không đánh dấu OMAP dirty, nên partial recovery có thể coi OMAP là clean và tạo object/PG inconsistent sau scrub. Với EC copy target không tồn tại, base trả `ENODATA` như thể chỉ thiếu attr, có thể đưa refcount về wildcard tag và làm PGLog tăng. Target phân biệt hai trạng thái và persist dirty region đúng.

**Điều kiện/hiệu lực.** Tự động khi client/class gọi range-delete hoặc copy/getattr chạm object EC không tồn tại. Không cần migration; dữ liệu/PG đã inconsistent không tự được sửa chỉ nhờ upgrade.

**Mixed/full.** Primary version xử lý op và tạo PGLog/clean-regions. Mixed primary failover có thể đổi semantics; full upgrade đồng nhất. Không thấy wire-format mới riêng ngoài `OSD-005`.

**Tác động/đánh giá.** Category: correctness/availability. Rủi ro exposure **cao** ở workload tương ứng; confidence `high`. Cần scrub/read-only validation trước mọi repair.

### OSD-010 — Ngoại lệ legacy: SnapMapper conversion không còn làm mất suffix object

**Owner/evidence.** Inventory `1599–1600`; context test inventory `2548`. Symbol `SnapMapper::convert_legacy_key` target `src/osd/SnapMapper.cc:684` và `convert_legacy` `:695`. Commit `0af27423a981959e42dc76d3b68b537d3d411b08`.

**Trước → sau.** Base dựng key mới chỉ bằng prefix pool/snap và có thể bỏ phần `shardid + hobject`, làm nhiều legacy mapping va chạm. Target decode pool từ value nhưng giữ toàn bộ suffix của old key sau `LEGACY_MAPPING_PREFIX`, nên key mới đúng format `<pool>_<snap>_<shard>_<object>`.

**Điều kiện/hiệu lực.** `OSD::init` chỉ gọi conversion khi thêm incompat feature `SNAPMAPPER2`, tức store rất cũ lần đầu được mở qua đường Octopus/Pacific. Một OSD đã chạy `16.2.5` bình thường thường đã có feature và không rerun conversion khi lên `16.2.15`. Commit nói rõ fix “going forward”; nó **không sửa mapping đã bị conversion cũ phá hỏng**.

**Mixed/full/rollback.** Local theo OSD/store, không phải protocol. Chỉ target được dùng làm binary đầu tiên chuyển store cũ mới nhận fix. Không được suy ra rằng rolling upgrade `16.2.5 → .15` tự chữa lịch sử.

**Tác động/đánh giá.** Category: correctness/data metadata. Rủi ro **cao nhưng activation hẹp**; confidence `high`. Cần inventory compat feature và nguồn gốc từng OSD trước khi coi áp dụng.

**Test đã đọc.** `src/test/test_snap_mapper.cc::SnapMapperTest.LegacyKeyConvertion` so key converted với key chuẩn; chưa chạy.

### OSD-011 — Restart OSD dùng mClock có thêm benchmark/persist capacity

**Owner/evidence.** Inventory `1580–1581`, `1608–1612`. Target option context vẫn đặt `osd_op_queue=wpq` và mô tả `mclock_scheduler` là experimental. Upgrade-relevant commit chain:

- `cf876406d876ad35d9adc985814a22be908db42c` tách `OSD::run_osd_bench_test` và dùng kết quả để update capacity;
- `433793a78239f0d1c38faa17f3cd22ba027dcc65` persist IOPS vào MON config store, tránh benchmark lại khi value khác default;
- `b48d709d30d8514d9bc9242772f4b56f6bc3534e` thêm force-run startup option; `69d3d5903550a4b30d341dfb3fbd39396df56763` thêm skip option;
- `9f3937d98150f6d3afef04fe95b3914428e91e3f` clear heartbeat timeout khi worker chờ future item rồi reset khi thức;
- `8662711a63b6dc714ec0c703fff0f78e317302e6` đánh thức nhiều shard workers khi consume map requeue nhiều peering ops; hai hunk này là evidence hỗ trợ cho ổn định sau restart, không phải finding riêng.

**Trước → sau.** Base `16.2.5` chưa có init-time capacity workflow này. Target, **chỉ khi cấu hình mClock**, có thể benchmark random 4 KiB writes vào 100 object, persist IOPS, cập nhật scheduler shards; historical value giúp skip lần sau. Scheduler wait không còn phát heartbeat timeout giả chỉ vì item chưa đến thời điểm, và map consume gọi `notify_all` khi requeue nhiều item.

**Điều kiện/hiệu lực.** Không áp dụng cho cluster giữ WPQ default. Với mClock opt-in, benchmark chạy ở startup trừ khi historical/default/skip logic ngăn nó; force/skip và capacity overrides thuộc report config `06`. Benchmark tạo tải local và không nên được bật cưỡng bức đại trà trong cùng cửa sổ upgrade nếu chưa đo.

**Mixed/full.** Queue/scheduler local theo OSD; recovery/client latency của PG có thể khác theo primary/device version. Full upgrade không tự chuyển WPQ sang mClock. Không được lẫn finding Pacific này với việc mClock thành default ở Quincy.

**Tác động/đánh giá.** Category: performance/availability/operability. Rủi ro `trung bình` nếu mClock đang bật, thấp với WPQ; confidence `high` cho activation, `low` cho hiệu năng thực tế. Cần config dump và baseline p95/p99 + recovery throughput.

**Test đã đọc.** `src/test/osd/TestMClockScheduler.cc` và các `qa/suites/rados/perf/scheduler/dmclock_*` làm context; không chạy benchmark.

### OSD-012 — Startup/shutdown và map-delivery fail an toàn hơn

**Owner/evidence.** Inventory `1580–1581`, `1590`. Các commit chính:

- `6e62b209d3620b3d13d50e6582d6c3f152e1e6ca` flush collection sau khi ghi superblock trong `OSD::mkfs`;
- `fc0fe263d7da25a1cdebbe1c8bbd698df864172b` trả `-ENOENT` nếu mount xong nhưng không mở được meta collection;
- `0c78649033486f59f670e74889e8061540a0266a` không đọc length từ bufferlist sau `std::move` khi build incremental maps;
- `daa2b54bcc334497dfa6dd5748d6762da9da3d80` bỏ `put()` thừa trên smart-pointer recovery-delete reply;
- `52b8ec639006001cba668d76e83da5ee9e4a30f4` honor admin stop cả khi OSD không active;
- `b6f0324b157da99846a5cfd0ca11fabe2b51f99d` gửi “down and dead” trong fast shutdown khi option yêu cầu (phần MON/message thuộc owners khác).

**Trước → sau.** Target chờ mkfs transaction hoàn tất trước exit, fail rõ thay vì dereference meta collection rỗng, tránh use-after-move/double-put và làm stop state machine đầy đủ hơn. Đây là nhiều đường lifecycle nhỏ cùng mục tiêu fail-fast/resource safety, không phải một thay đổi data format.

**Điều kiện/hiệu lực.** Object-store corruption/missing meta, map sharing, recovery-delete race hoặc explicit stop/fast shutdown có thể xuất hiện khi thay binary và restart. Upgrade OSD hiện hữu không tự chạy mkfs; hunk flush trong `mkfs` chỉ là support, trừ khi runbook đồng thời provision/thay OSD. Một lỗi nền có thể làm target fail sớm nơi base đi tiếp rồi crash/hành xử không xác định.

**Mixed/full/đánh giá.** Chủ yếu local; fast-shutdown có message/monitor side nên phải kiểm với report `04/05`. Category: availability/correctness/maintainability. Rủi ro `trung bình` theo lỗi nền, confidence `medium` vì nhóm đường hiếm chưa được chạy end-to-end.

### OSD-013 — RBD read-only có đúng quyền list metadata

**Owner/evidence.** Inventory `1582` và test `2512`. Symbol `OSDCapGrant::expand_profile` tại base/target `src/osd/OSDCap.cc:320`. Commit `877ca0da145c22527b60169f687826fe19fbdf0f`.

**Trước → sau.** Base profile `rbd-read-only` thiếu grant class method `rbd.metadata_list`, dù việc mở image cần list metadata. Target cho phép method này trên object `rbd_info` ở global namespace của đúng pool; đồng thời grant tương tự của profile `rbd` được thu hẹp từ mọi object trong pool xuống đúng `rbd_info`. Đây vừa là compatibility fix cho read-only client vừa giảm scope grant read-write.

**Điều kiện/hiệu lực.** Áp dụng khi auth entity dùng profile `rbd-read-only` hoặc `rbd` và client gọi `metadata_list`. Có hiệu lực ngay trên OSD target sau restart, không cần thay caps text. Trong mixed phase, request tới primary base có thể vẫn bị từ chối; cần thử primary trên cả version.

Đây là ngoại lệ client-facing được giữ trong Markdown vì version của OSD primary có thể thay đổi service continuity ngay trong rolling upgrade; không phải vì mọi thay đổi RBD/client đều mặc nhiên quan trọng.

**Tác động/đánh giá.** Category: compatibility/security least-privilege. Rủi ro `trung bình` nếu deployment dùng read-only RBD; confidence `high`. Không gọi đây là CVE vì commit/advisory không ánh xạ CVE.

**Test đã đọc.** `src/test/osd/osdcap.cc::OSDCap.AllowProfile` thêm positive/negative cases cho pool, namespace, object và method; chưa chạy.

### OSD-014 — Manifest/tiering phục hồi đúng adjacent clone trước khi tính refcount

**Owner/evidence.** Inventory `1595–1596` và `1601`. Symbols `PrimaryLogPG::get_manifest_ref_count` (base `src/osd/PrimaryLogPG.cc:3342`, target `:3347`), `recover_adjacent_clones` (base `:3384`, target `:3392`) và `cls_get_manifest_ref_count` trong `src/osd/objclass.cc:685`. Commits:

- `022a44462562ef0fc46e97fcd1bb37ca3df1fc37` nhận diện `CEPH_OSD_OP_SET_CHUNK` ngay cả khi head chưa là chunked manifest, để recovery adjacent clone xảy ra trước mutation;
- `0d79b1ee42be7caf8fbedad9d61e6f69f4f4ffd1` truyền `OpRequestRef` vào refcount path và chờ clone unreadable được recover trước khi đọc manifest refs;
- `061589f7c5b2112c1a5a9f6469f2a110f7771e3b` gọi recovery bằng `clone_obc` đang được duyệt, không nhầm head `obc`;
- `fee8115dfd18042e8845a8452026a611e4517976` trả `-ENOENT` khi tier-flush không còn pool info thay vì tiếp tục với state không hợp lệ.

**Trước → sau.** Base có thể bỏ qua adjacent-clone recovery ở lần `set_chunk` đầu, đọc refcount khi clone còn unreadable, hoặc kiểm nhầm object context trong vòng lặp clone. Target requeue bằng `-EAGAIN` sau khi kick recovery và chỉ tính refcount trên clone context đúng; invalid pool information fail rõ bằng `ENOENT`.

**Điều kiện/hiệu lực.** Chỉ áp dụng object manifest/chunk reference, cache tier/dedup path có snapshot clone và degraded/unreadable adjacent object. Tự có khi primary target xử lý op; không chuyển đổi object đã có và không tự repair refcount lịch sử.

**Mixed/full.** Primary version quyết định precondition/requeue. Replica chỉ nhận kết quả transaction/PGLog; không có feature bit mới trong nhóm hunk này. Khi primary failover về base trong mixed phase, đường cũ có thể lại xuất hiện; full upgrade mới đồng nhất.

**Tác động/đánh giá.** Category: correctness/availability. Rủi ro **cao theo feature/workload**, thấp nếu không dùng object manifest/tiering; confidence `high` về code, `medium` về applicability vì chưa có inventory cache-tier/dedup/snapshot. Không coi cache tier phổ biến mặc định.

**Test đã đọc.** `src/test/librados/tier_cxx.cc` có `TierFlushDuringFlush` và nhiều case `manifest_set_chunk`; `src/test/osd/TestRados.cc` có workload `--set_chunk`. Commit `1610a624f2ba564d1aa90a132d3b3a4f411012da` sửa đồng bộ test tier-flush. Chưa chạy.

## 4. Thay đổi trivial/support chỉ giữ đầy đủ trong CSV

Tất cả vẫn có diff và metadata trong CSV. **8 dòng P2** (test/QA/marker) chỉ làm evidence; chúng không có tác động upgrade độc lập. Một hunk trivial có thể nằm cùng file P0 với hunk quan trọng, nên không ép số lượng hunk trivial thành số dòng CSV.

- Debug/log wording, slow-op detail và metadata `created_ceph_version`/`created_at` hỗ trợ chẩn đoán nhưng không đổi placement, I/O hay quyết định rollout.
- Private link `fmt::fmt`, hunk `mkfs` khi không provision OSD, và rename marker `R100 0/0` không đổi hành vi rolling upgrade chuẩn.
- Thay đổi lock cho compound `stat+write` (`79bf6fcea7244b999c7ee2d5f718c034c8a7742b`) là tối ưu concurrency thực, nhưng chưa có bằng chứng rằng nó thay đổi an toàn, thời lượng hoặc tiêu chí chấp nhận của upgrade này; vì vậy không còn là finding và không có validation scenario riêng.

## 5. Hành vi rolling upgrade và sau full upgrade

| Nhóm finding | Trong mixed `16.2.5/16.2.15` | Sau khi tất cả OSD ở `16.2.15` | Activation/action |
| --- | --- | --- | --- |
| EC recovery (`001–002`) | Primary/participant base vẫn có đường cũ; đổi primary có thể đổi outcome | Guard `min_size` và hinfo error handling đồng nhất | Tự động; repair/unfound action vẫn thủ công |
| PGLog (`003`) | Primary version quyết định trim policy; warning chỉ trên target | Mọi PG khi được xử lý sẽ hội tụ theo giới hạn mới | Auto trim theo hoạt động; offline tool chỉ có runbook |
| Scrub/peering (`004–007`) | Primary target mang FSM/selection mới nhưng replica có thể còn base | Coordinator và participant đồng nhất | Tự động; flags/repair không tự đổi |
| Object ops (`008`) | Primary version quyết định dirty regions và errno | Semantics đồng nhất | Tự động sau restart |
| SnapMapper (`010`) | Chỉ store chưa có `SNAPMAPPER2` mới convert | Không tự sửa conversion hỏng lịch sử | Conversion tự động theo compat feature; repair riêng |
| mClock/lifecycle (`011–012`) | Local theo OSD; tải/latency có thể lệch theo queue/version | Đồng nhất code, nhưng WPQ vẫn default | mClock chỉ khi cấu hình; mkfs/tool/stop theo hành động |
| Caps (`013`) | Client result có thể phụ thuộc primary version | Read-only metadata open đồng nhất | Tự động với caps/profile hiện hữu |
| Manifest/tiering (`014`) | Primary base/target có precondition recovery khác nhau | Adjacent clone/refcount handling đồng nhất | Tự động trên op; không auto-repair state cũ |

## 6. Test repository và validation đề xuất

### Test đã đọc

- `qa/tasks/ec_inconsistent_hinfo.py` và suite EC tương ứng.
- `qa/tasks/backfill_toofull.py`; standalone `osd-backfill-*`/`osd-recovery-*` làm context.
- `src/test/osd/TestPGLog.cc`, `TestOSDScrub.cc`, `TestMClockScheduler.cc` và `osdcap.cc`.
- `src/test/test_snap_mapper.cc::LegacyKeyConvertion` (context owner `15`).
- Các suite partial/async recovery, min-size recovery và dmClock perf.

Không test nào được chạy trong lần phân tích này.

### Ma trận validation môi trường

| ID | Tiền điều kiện/pha | Hành động trong lab | Kết quả mong đợi và tín hiệu lỗi | Quan sát/stop condition |
| --- | --- | --- | --- | --- |
| `V01-01` | EC pool với `min_size` giống Production; mixed phase | Làm một shard đủ “costly” cho async recovery rồi đổi primary base/target | Primary target không giảm acting dưới `min_size`; client I/O còn theo policy | PG state/acting/query latency; dừng nếu PG mất I/O ngoài dự kiến |
| `V01-02` | Scratch EC object có thể phá attr | Chạy flow tương đương `ec_inconsistent_hinfo.py` | OSD không assert; deep-scrub báo inconsistent; có nguồn tốt thì repair sạch, thiếu nguồn thì unfound | Dừng trước `mark_unfound_lost`; giữ store image/log |
| `V01-03` | Fixture PGLog có `dups` vượt ngưỡng | Khởi động target, tạo thêm log activity; thử tool chỉ trên clone OSD dừng | Warning đúng một ngưỡng; auto trim có giới hạn; tool giảm tới target và DB reopen | RSS/DB bytes/tombstone; dừng nếu OSD không mount hoặc PGLog decode lỗi |
| `V01-04` | PG remapped; có `noscrub/nodeep-scrub` cases | Scrub/deep-scrub, delay reservation message, đổi primary | FSM thoát abort; request đúng acting set; không spam/error giả | Scrub state/timestamps/reservations; dừng nếu stuck quá timeout |
| `V01-05` | Large object partial recovery | Ngắt/restart primary giữa partial recovery, lặp trên base và target | Target tiếp tục vùng thiếu thay vì đọc lại whole object; checksum đúng | Recovery bytes/time; dừng khi checksum mismatch |
| `V01-06` | Stretch lab và backfill capacity guard | Interrupt backfill, failover primary rồi resume | Existing acting được ưu tiên; reservation bytes không reset sai; không bypass full ratio | Acting set, reservation, `backfill_toofull`; dừng nếu headroom guard bị vượt |
| `V01-07` | OSD có local map lag và restart | Trim map trong lab, restart/failover, xem admin status | Lower bound không lùi; past intervals/peering hoàn tất không warning giả | `cluster_osdmap_trim_lower_bound`, peering logs; dừng nếu incomplete/stale PG |
| `V01-08` | Replicated + EC pool; OMAP range và missing copy target | Range-delete rồi recovery/scrub; chạy copy case object thiếu | OMAP recovery đầy đủ; attr errno đúng; scrub clean sau recovery | Key cardinality/checksum/PGLog size; dừng nếu inconsistent |
| `V01-10` | Clone của store thật sự thiếu `SNAPMAPPER2` | Mở clone bằng target và so toàn bộ old/new keys | Mỗi object suffix/cardinality được giữ; không collision | Không thử trên bản duy nhất; dừng nếu key count/checksum khác |
| `V01-11` | Hai cấu hình riêng WPQ và mClock | Restart OSD, ghi nhận benchmark/IOPS; chạy client + recovery | WPQ không benchmark mClock; mClock dùng/persist capacity đúng, không heartbeat giả | Startup latency, config source, p99/recovery; dừng nếu tải benchmark vi phạm guardrail |
| `V01-12` | Auth `profile rbd-read-only` | Mở/list metadata image với primary lần lượt base/target | Base có thể fail đúng exposure; target chỉ cho `metadata_list` trên đúng `rbd_info`/pool | Audit denied/allowed ops; dừng nếu method/object ngoài scope được phép |
| `V01-13` | Lab có object manifest, snapshot clone và một adjacent clone unreadable | Chạy `set_chunk`/refcount, đổi primary giữa base/target rồi phục hồi clone | Target requeue đến khi clone readable, refcount/checksum đúng; không crash hoặc wildcard ref | Dừng nếu refcount/data mismatch; giữ fixture, không dùng cache tier Production |

Các scenario là thiết kế kiểm chứng, không phải lệnh được phép chạy trên Production. Repair, offline trim, phá hinfo, map trim và device/store mutation chỉ được thực hiện trên fixture/clone có rollback.

## 7. Khoảng trống và kết luận áp dụng

Cần As-Is tối thiểu: pool replicated/EC và `size/min_size`; stretch mode; flags `no*`; scrub backlog; số `dups`/PG và RocksDB headroom; recovery/backfill overrides; `osd_op_queue`/mClock options; lịch sử store pre-Octopus/SNAPMAPPER2; RBD caps đang dùng; cache-tier/dedup object manifest và snapshot usage; tần suất primary failover và restart.

Kết luận code-level có confidence cao: target đóng các đường crash/correctness cụ thể trong EC, scrub, PGLog và object metadata. Hai điểm ưu tiên kiểm chứng trước rollout là EC degraded recovery (`OSD-001/002`) và mixed-primary scrub/peering (`OSD-004/006/007`). Không đủ dữ liệu để tuyên bố GO/NO-GO, mức tăng hiệu năng hay nhu cầu chạy repair/trim trên cluster.
