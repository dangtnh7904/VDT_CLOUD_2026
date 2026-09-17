# 03 — RocksDB, KV và block device: v16.2.5 → v16.2.15

> **Kết quả:** CSV bao phủ đủ 6 dòng do `03-rocksdb-block-device` sở hữu; Markdown chỉ phân tích sâu những hành vi có đường tác động tới restart, data path, phục hồi sự cố hoặc validation của upgrade. Trọng tâm là iterator/range-delete RocksDB và block-device open/error handling. Không có bằng chứng trong tập owner này về thay đổi định dạng DB/WAL, protocol trên mạng hay migration tự động.
>
> **Trạng thái kiểm chứng:** đã đọc code ở cả hai endpoint, lịch sử commit và test trong repository; chưa build, chưa chạy unit/integration test, chưa thao tác cluster hay thiết bị thật.

## 1. Phạm vi và nguồn

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Repository dùng để resolve cả hai tag: `ceph16.2.15/ceph` (working tree sạch, non-shallow; base là ancestor của target).
- Rename detection của inventory: `--find-renames`; cả 6 dòng của báo cáo này đều là `M`, không có rename, binary, mode change hay gitlink.
- Danh sách file và metadata Git nằm trong [03-rocksdb-block-device.csv](./03-rocksdb-block-device.csv). CSV giữ đúng 21 cột nền, thứ tự và giá trị của master inventory.

Phạm vi CSV gồm các inventory index `1099`, `1100`, `1272`–`1274` và `2590`: tổng `+383/-173`, tất cả là `P1`; 5 dòng `deep`, 1 dòng `conditional`. Các path chính thuộc `src/blk/`, `src/kv/` và công cụ KV. Báo cáo không lặp danh sách file thành bảng.

`review_mode` là triage đọc, không tự động biến một dòng thành finding. Dòng build-only vẫn được giữ nguyên trong CSV nhưng được hạ xuống trivial/support sau khi không tìm thấy tác động runtime với package chính thức.

Ba file có net diff nhưng do báo cáo khác sở hữu được dùng làm **ngữ cảnh**, không chèn vào CSV này:

- `src/os/bluestore/BlueStore.cc` — inventory `1561`, owner `02-bluestore-bluefs`: caller truyền OMAP lower/upper bounds.
- `src/common/legacy_config_opts.h` và `src/common/options.cc` — inventory `1235`, `1236`, owner `06-config-defaults`: định nghĩa/default của các option RocksDB liên quan.

Không có thay đổi gitlink `src/rocksdb` giữa hai endpoint. Sáu dòng owner cũng không đổi cách đặt RocksDB DB/WAL lên thiết bị, không đổi WAL format và không đổi default `max_total_wal_size`; vì vậy báo cáo không suy diễn một thay đổi DB/WAL riêng.

## 2. Kết luận nhanh

1. **Tự động sau restart:** target đổi OMAP iterator/range-delete cục bộ trên từng OSD; default threshold và on-disk format không đổi. Cần kiểm correctness ở boundary và đo tải thực tế, không suy diễn phần trăm hiệu năng.
2. **Rủi ro startup/fault path:** `KernelDevice` thêm `O_EXCL`, nên duplicate device alias tiềm ẩn có thể khiến OSD target fail sớm lúc restart thay vì cho phép hai writer; synchronous read cũng phân loại errno đúng hơn.
3. **Chỉ theo điều kiện:** reshard, compact-on-deletion và destructive repair chỉ liên quan khi As-Is/runbook thực sự dùng chúng. Chúng không tự chạy trong rolling upgrade; build `blk` static và các hunk log-only là trivial đối với package chính thức.

## 3. Phát hiện chi tiết

### KVBD-001 — Iterator OMAP có bound và tránh quét column family không liên quan

**Owner/evidence.** Inventory `1272`–`1274`: `src/kv/KeyValueDB.h`, `src/kv/RocksDBStore.{h,cc}`. Các symbol chính ở base là `KeyValueDB::get_iterator` (`KeyValueDB.h:318`), `RocksDBStore::get_iterator` (`RocksDBStore.cc:2891`) và `CFIteratorImpl` (`:2172`); ở target là `KeyValueDB::IteratorBounds`/`get_iterator` (`KeyValueDB.h:325/331`), `RocksDBStore::check_cf_handle_bounds` (`RocksDBStore.cc:674`), `CFIteratorImpl` (`:2266`), `ShardMergeIteratorImpl` và `RocksDBStore::get_iterator` (`:3019`). Caller BlueStore ở target truyền `{head, tail}` tại `BlueStore.cc:10972`, `:11057`, `:15609` và dựng bounds trong `get_omap_iterator` quanh `:11242` (context inventory `1561`).

Các commit tạo endpoint cuối gồm:

- `d704e218e58dea609161397efd0f7cd03e7c5ad8` — truyền OMAP bounds và đưa chúng vào RocksDB iterator;
- `11fb62a0be67d3365ff6b46be0f15d40bf6312dc` — thêm option `osd_rocksdb_iterator_bounds_enabled`, default `true` tại target `options.cc:3797`;
- `822f5f785562efc4f9d56ba7f0c87ffa1ca814e4` — đơn giản hóa chọn CF từ bounds;
- `9cdb2c1c86b2ce5c25cc5d25145659b7d0a2b212` — không dùng bounded iterator làm `WholeSpaceIterator`, vì prefix phải được xử lý riêng;
- `f802ff8f0ba430abd2bd6baadb6a94e571b21e0c` và `79706e4e063bf7f96fa087549b65e2184463cd15` — tránh lookup prefix lặp lại và dùng default-CF iterator thay vì whole-space iterator khi prefix không có CF riêng.

Lịch sử có một chuỗi thêm rồi revert hoàn toàn (`d0b03f2`/`7d96030`/`a1f4061`, sau đó `9525347`/`e986624`/`e4a584a`) trước khi ba commit `d704e21`/`11fb62a`/`822f5f7` áp dụng lại. Kết luận ở đây dựa trên **net diff endpoint**, không tính trạng thái trung gian đã revert.

**Trước → sau.** Ở `v16.2.5`, API iterator không mang lower/upper bound; iterator của CF nhiều shard phải merge toàn bộ shard, và prefixed access có thể đi qua whole-space iterator. Ở `v16.2.15`, `CFIteratorImpl` và `ShardMergeIteratorImpl` gắn `iterate_lower_bound`/`iterate_upper_bound` vào `rocksdb::ReadOptions` khi option bật. Nếu hai bound có cùng phần chuỗi dùng để hash và sharding có `hash_l == 0`, `check_cf_handle_bounds()` chọn đúng một CF; nếu không chứng minh được, code vẫn dùng merge iterator trên các shard nhưng từng iterator bị bound. Prefix không có CF riêng được giới hạn vào default CF thay vì quét mọi CF.

**Điều kiện và tác động.** Tự có hiệu lực sau khi một OSD chạy binary target, với `osd_rocksdb_iterator_bounds_enabled=true` (default target), trên các đường OMAP truyền cả head/tail; lợi ích rõ nhất về mặt cơ chế khi có nhiều CF shard và tombstone ngoài range. Tác động thuộc **performance/availability**: giảm công việc iterator có thể giảm tail latency, nhưng repository không cung cấp benchmark cho cluster này nên không định lượng. Các kiểm tra `tail` ở BlueStore vẫn còn, nên bounds là lớp giới hạn bổ sung chứ không thay đổi định dạng key.

**Rolling/full upgrade và hành động.** Đây là hành vi local của RocksDB mỗi OSD: OSD cũ giữ đường iterator cũ, OSD đã nâng cấp dùng đường mới; không có negotiation hoặc on-disk migration. Sau full upgrade, mọi OSD target dùng hành vi mới. Không cần repair/rebuild DB. Nếu muốn tắt, cần override config; option không mang `FLAG_RUNTIME` trong `options.cc`, vì vậy nên coi thay đổi cấu hình là cần restart cho tới khi xác minh live-injection trong môi trường đích.

**Đánh giá.** Reading priority `P1`; rủi ro nâng cấp **trung bình-thấp** (đường metadata nóng nhưng không đổi format; chuỗi backport từng có revert và một follow-up sửa phạm vi WholeSpaceIterator); confidence **high** cho cơ chế, **medium** cho mức tác động hiệu năng. Chưa biết cluster có override option, CF layout nào, workload OMAP/RGW nào và mật độ tombstone ra sao.

**Test.** Commit không thêm assertion hồi quy chuyên biệt. Đã đọc các test có sẵn `KVTest.RocksDBShardingIteratorTest` (`src/test/objectstore/test_kv.cc:454`) và các test ObjectMap/BlueStore liên quan; các stub `KeyValueDBMemory` chỉ đổi signature trong lịch sử rồi không còn net diff. Chưa chạy test.

### KVBD-002 — Xóa range đọc threshold hiện thời, có fast path và iterator có bound

**Owner/evidence.** Inventory `1273`, `1274` và phần API ở `1272`; symbol `RocksDBTransactionImpl::rmkeys_by_prefix`, `RocksDBTransactionImpl::rm_range_keys`, `get_delete_range_threshold` và `new_shard_iterator`. Ở base, threshold là member `const` chụp lúc dựng `RocksDBStore` (`RocksDBStore.h:185/231`) và `rm_range_keys` bắt đầu ở `RocksDBStore.cc:1685`. Target đọc option qua `get_delete_range_threshold()` (`RocksDBStore.h:204`) ở mỗi thao tác, với `rm_range_keys` tại `RocksDBStore.cc:1754`. Commit chính: `659e9b2702f40049d9548e36322bc497fc391c40` và `3226ee52ae059552d3e5da3fe1057356b68ca653`; logging hỗ trợ đến từ `ba50fc87869719fd531cd32b85b32d78113c84de`.

**Trước → sau.** Base dùng threshold đã cache từ lúc mở DB; với CF sharded, code tạo raw RocksDB iterator cho từng CF, seek từ `start`, tự so sánh với `end`, rồi chuyển sang `DeleteRange` nếu vượt threshold. Target:

- lấy giá trị cấu hình tại lần gọi;
- nếu prefix có CF và threshold bằng `0`, phát `DeleteRange(start,end)` trực tiếp cho từng shard, không quét đếm key;
- nếu threshold khác `0`, tạo `CFIteratorImpl` với `{start,end}` nên iterator bị bound; chỉ rollback các delete riêng lẻ và dùng `DeleteRange` khi chạm ngưỡng;
- giữ ngữ nghĩa range `[start,end)` trong code và test hiện hữu.

Default `rocksdb_delete_range_threshold=1048576` không đổi giữa hai endpoint. Vì vậy fast path threshold `0` chỉ kích hoạt khi có override; bounded-iterator path vẫn áp dụng cho cấu hình mặc định khi xóa range trên CF sharded.

**Điều kiện và tác động.** Kích hoạt khi BlueStore/KV transaction gọi `rmkeys_by_prefix` hoặc `rm_range_keys`; đáng chú ý với cleanup range lớn và CF sharded. Đây là thay đổi **correctness/performance** trong cách tạo tombstone và lượng key phải duyệt, không phải thay đổi WAL format. Nếu giá trị mới thực sự được đưa vào config context của daemon đang chạy, target sẽ dùng nó ở thao tác kế tiếp; do option không có `FLAG_RUNTIME`, cần xác minh cơ chế áp config live trước khi khẳng định không cần restart.

**Rolling/full upgrade và hành động.** Local theo OSD, không có mixed-version protocol. Upgrade tự mang code mới; không cần migration. Thay threshold là hành động cấu hình riêng, không phải yêu cầu của upgrade.

**Đánh giá.** Priority `P1`; rủi ro **trung bình** nếu dùng override nhỏ/`0` hoặc workload xóa range lớn, **thấp** nếu không đi qua đường này; confidence **high** về nhánh code, **medium** về workload thực tế. Cần quan sát compaction debt, tombstone và latency thay vì suy ra cải thiện từ commit title.

**Test.** `KVTest.RMRange` (`test_kv.cc:262`) và `KVTest.ShardingRMRange` (`:315`) kiểm tra boundary/correctness cơ bản; chúng có trước thay đổi và responsible commits không thêm case threshold `0` hay assertion rằng iterator không vượt bound. Chưa chạy `ceph_test_keyvaluedb`.

### KVBD-003 — Reshard column family hiểu `block_cache` nhất quán

**Owner/evidence.** Inventory `1273`, `1274`; commit `7be3940b9c61b5b77b60a86bc8a4cc5cbcb0a059`. Base có `extract_block_cache_options` (`RocksDBStore.cc:855`) nhưng `prepare_for_reshard` (`:2934`) dùng trực tiếp parser RocksDB cho options. Target tách thành `split_column_family_options` (`:880`), `update_column_family_options` (`:910`) và `apply_block_cache_options` (`:952`), rồi gọi helper chung từ create, verify và hai nhánh open/create của `prepare_for_reshard` (`:3087`, call sites quanh `:3170/:3227`). Default target `bluestore_rocksdb_cfs` tại context `options.cc:4745` chứa `O(3,0-13)=block_cache={type=binned_lru}`.

**Trước → sau.** `block_cache` là pseudo-option của Ceph, không phải option CF gốc của RocksDB. Base xử lý nó khi create/verify nhưng bỏ qua đường xử lý riêng khi chuẩn bị reshard, nên một sharding spec hợp lệ theo Ceph — kể cả dạng default — có thể bị parser RocksDB từ chối. Target dùng một helper ở mọi đường, bỏ pseudo-option trước khi gọi parser RocksDB, dựng cache riêng nếu cần, rồi gắn `table_factory` đúng vào CF.

**Điều kiện và tác động.** Chỉ liên quan khi thực hiện RocksDB CF reshard, đặc biệt spec có `block_cache={...}`. Đây là **reshard nội bộ BlueStore**, không phải RGW bucket reshard. Hành động được gọi từ `ceph-bluestore-tool ... reshard` trên store local; không tự chạy khi nâng cấp. Tác động chính là khả năng hoàn tất bảo trì và mở lại DB với option đúng; không chứng minh cải thiện hiệu năng runtime nếu không thực hiện reshard.

**Rolling/full upgrade và hành động.** Không có tương tác mixed-version: mỗi OSD phải dừng và được xử lý riêng bằng tool phù hợp. Nếu không có kế hoạch reshard thì finding không kích hoạt. Nếu có, dùng binary target trên bản sao/OSD dừng, kiểm tra `fsck` và reopen trước khi đưa OSD lại; báo cáo này không ủy quyền chạy thao tác đó.

**Đánh giá.** Priority `P1`; rủi ro upgrade **thấp khi không reshard**, **trung bình khi có quy trình reshard** vì đây là thao tác ghi metadata DB; confidence **high**. As-Is còn thiếu: sharding spec lưu trên từng OSD và kế hoạch có dùng `ceph-bluestore-tool reshard` hay không.

**Test.** Repository có `RocksDBResharding.basic`, `all_to_shards`, resume/interruption và hash-change cases (`test_kv.cc:1135`–`:1239`) cùng QA `CephManager.test_bluestore_reshard_action`; responsible commit không thêm case chứa pseudo-option `block_cache`. Chưa chạy test.

### KVBD-004 — Compact-on-deletion là tính năng opt-in, không phải default upgrade

**Owner/evidence.** Inventory `1273`; context option ở inventory `1235/1236`; commit `317eb8f69834fa08dbb17b19656db2359dbdcbd0`. Target `RocksDBStore::update_column_family_options` gọi `rocksdb::NewCompactOnDeletionCollectorFactory` tại `RocksDBStore.cc:943`–`:947`. Ba option target tại `options.cc:3971`–`:3985` là:

- `rocksdb_cf_compact_on_deletion=false`;
- sliding window `32768`;
- trigger `16384`.

**Trước → sau.** Base không cài collector này. Target, chỉ khi option boolean bật, gắn factory vào `table_properties_collector_factories` của CF khi options được dựng. Theo commit, collector kích compaction sau khi thấy đủ tombstone trong cửa sổ lúc duyệt SST; nó không xử lý tombstone còn trong memtable.

**Điều kiện và tác động.** Mặc định tắt nên upgrade thuần túy không thay đổi compaction. Khi bật và DB/CF được mở lại, tác động là **performance/maintainability** hai chiều: có thể dọn tombstone sớm hơn, nhưng tăng compaction I/O và write amplification. Không có dữ liệu benchmark để chọn threshold cho cluster cụ thể.

**Rolling/full upgrade và hành động.** Local theo OSD; OSD nào target và mở DB với option bật mới có collector. Cần cấu hình rõ ràng và restart/reopen để dựng lại CF options; không cần format migration. Không nên bật đồng loạt trong rolling upgrade nếu chưa đo compaction debt, device latency và recovery load.

**Đánh giá.** Priority `P1`; rủi ro mặc định **thấp** vì tắt, rủi ro khi bật **trung bình** do I/O nền; confidence **high** về activation, **medium** về tác động. Không có test Ceph chuyên biệt được thêm cùng commit.

### KVBD-005/006 — Block-device restart chặn alias trùng và phân loại lỗi đọc đúng hơn

**Owner/evidence.** Inventory `1100`, `src/blk/kernel/KernelDevice.cc`; commit `59f6535b1780d142a84117d4199b30cb596d080e`. Symbol `KernelDevice::open` ở cả hai endpoint bắt đầu tại dòng `123`. Target `stat()` path, nhận diện `S_IFBLK`, và thêm `O_EXCL` cho direct fd đầu tiên khi `lock_exclusive` bật; `_lock()`/`flock()` vẫn được giữ cho regular file và để hiện trong `/proc/locks`.

**Trước → sau.** Base chỉ dựa vào OFD lock/`flock`; hai inode/alias khác nhau trỏ tới cùng major/minor có thể nhận hai file lock riêng. Target yêu cầu exclusive block-device open, nên tiến trình thứ hai không thể cùng claim thiết bị theo đường này. Regular-file test backend vẫn dùng soft lock.

**Điều kiện và tác động.** Tự kích hoạt lúc OSD/BlueStore mở raw block device với exclusive locking. Với mapping đúng, không cần cấu hình hay migration. Với duplicate alias, mount/claim xung đột hoặc một process khác giữ thiết bị, target có thể fail open sớm — tác động **availability** tức thời nhưng tránh nguy cơ hai writer và **correctness/data safety** nghiêm trọng hơn.

Một gap đáng lưu ý từ endpoint code: nếu `stat()` thất bại, target giữ `r == -1`, log `cpp_strerror(r)` và trả `-1`, thay vì chuyển `errno` thành `-errno` như nhánh `open()` phía sau. Vì vậy path thiếu/không stat được có thể báo `(1) Operation not permitted` thay cho errno thật. Đây là suy luận trực tiếp từ code, không phải mục tiêu của commit; cần test lỗi path để xác nhận hành vi quan sát được.

**Rolling/full upgrade và hành động.** Local theo daemon. Trong mixed phase, chỉ OSD target có hard exclusion; không có protocol/format change. Không cần action nếu inventory thiết bị sạch. Trước upgrade nên kiểm tra symlink/LVM/container mapping để phát hiện hai OSD trỏ cùng major/minor.

**Error-path evidence.** Cùng inventory `1100`, commit `25664452919d360bd37fa3a9eb62202a58ac72e7` sửa `KernelDevice::read`: POSIX `pread()` trả `-1` và đặt `errno`, nhưng base truyền `-1` vào `is_expected_ioerr`; target truyền `-errno`. Khi `IOContext::allow_eio=true`, lỗi thuộc tập dự kiến mới được chuẩn hóa đúng thành `-EIO`. Đây là fault path local, tự có sau restart và không thay đổi dữ liệu hay format.

**Đánh giá.** Priority `P1`; rủi ro upgrade **thấp với mapping/device khỏe**, **trung bình về availability nếu đang có conflict alias tiềm ẩn**; confidence **high** cho O_EXCL và error mapping, **medium** cho biểu hiện lỗi `stat` vì chưa chạy. `unittest_bdev` chỉ có `KernelDevice.Ticket45337` trên regular temp file (`src/test/objectstore/test_bdev.cc:45`), không phủ block alias/O_EXCL hay `allow_eio` fault injection.

### KVBD-007 — Công cụ repair giữ được DB handle thay vì segfault

**Owner/evidence.** Inventory `2590`, `src/tools/kvstore_tool.cc`; commit `98d067a1b7246f3e64fc91b894f77571d7dcb38b`. Symbol `StoreTool::StoreTool` ở dòng `13` và `StoreTool::destructive_repair` ở target `:313`.

**Trước → sau.** Với type khác `bluestore-kv` và `to_repair=true`, base bỏ qua `open()` nhưng cũng chỉ `db.reset(db_ptr)` bên trong nhánh `!to_repair`; `destructive_repair()` sau đó dereference `db == nullptr`. Target đưa `db.reset(db_ptr)` ra ngoài nhánh, nên backend object tồn tại để gọi `repair()`.

**Điều kiện và tác động.** Chỉ khi người vận hành chủ động gọi đường destructive repair cho backend trực tiếp như `rocksdb`/`leveldb`; đường `bluestore-kv` dùng `load_bluestore` riêng. Không tự kích hoạt khi upgrade, start OSD hay replay WAL. Tác động là **maintainability/availability during repair**.

**Rolling/full upgrade và hành động.** Dùng phiên bản tool nào thì có hành vi phiên bản đó; không phụ thuộc cluster mixed-version. Rủi ro **của thay đổi** thấp, nhưng rủi ro **của thao tác destructive repair** cao và có thể làm hỏng dữ liệu khỏe mạnh, đúng như help text cảnh báo. Chỉ dùng trên bản sao/OSD dừng theo runbook được phê duyệt; không phải khuyến nghị thực thi từ báo cáo này.

**Đánh giá/test.** Priority `P1`; confidence **high**. `qa/workunits/cephtool/test_kvstore_tool.sh:63` chỉ gọi destructive repair qua `bluestore-kv`, nên không bắt đúng null-handle của backend `rocksdb`; responsible commit không thêm test trực tiếp. Chưa chạy tool.

## 4. Thay đổi trivial/support không ảnh hưởng upgrade chuẩn

CSV vẫn giữ đủ **6/6 dòng**. Dòng `src/blk/CMakeLists.txt` ép thư viện nội bộ `blk` thành `STATIC`; nó chỉ đáng xem lại với custom source build dùng `BUILD_SHARED_LIBS=ON`, không đổi runtime của package chính thức nên không còn là finding hay validation mặc định.

- `b44541a519a4c4e1af7d5237ffbd2f76d4558294` bổ sung RocksDB status vào log khi `ListColumnFamilies()` thất bại (`verify_sharding`); hỗ trợ chẩn đoán KVBD-003, không đổi return `-EIO`.
- `ba50fc87869719fd531cd32b85b32d78113c84de` thêm debug quanh `rm_range_keys`; các log này được giữ và mở rộng trong KVBD-002, không tự đổi semantics.
- `1e2df10bb8a7aee49fb0a3e31b2370a8e251c868` chỉ làm rõ chuỗi log `rotational/non-rotational device, discard ...`; không đổi phát hiện media hay discard.

## 5. Hành vi khi rolling upgrade và sau full upgrade

| Finding | Trong mixed `16.2.5/16.2.15` | Sau khi tất cả OSD liên quan ở `16.2.15` | Cấu hình/restart/action |
| --- | --- | --- | --- |
| KVBD-001 | Mỗi OSD dùng iterator của chính binary; không có negotiation | Bounds mặc định áp dụng nhất quán | Tự động sau restart; override option cần được kiểm chứng về live update |
| KVBD-002 | Delete/range behavior khác theo OSD local | Mọi OSD dùng getter/fast path/bounded iterator mới | Tự động; chỉ đổi threshold khi có quyết định cấu hình |
| KVBD-003 | Không phụ thuộc daemon khác | Tool target xử lý `block_cache` đúng khi reshard từng store | **Thao tác offline thủ công**, không tự chạy |
| KVBD-004 | Chỉ OSD target mở DB với option bật có collector | Nhất quán nếu cấu hình được rollout và OSD reopen | Mặc định tắt; bật cần config + restart/reopen |
| KVBD-005/006 | Khóa/open và error mapping local theo OSD | Tất cả OSD có hard exclusion và errno mapping mới | Tự động sau restart; kiểm tra device mapping trước |
| KVBD-007 | Phiên bản tool quyết định hành vi | Không có trạng thái cluster cần hội tụ | Chỉ hành động repair có chủ đích |

Không finding nào trong owner 03 yêu cầu đồng thời nâng MON/MGR/client, đổi feature bit hoặc chuyển đổi on-disk format. Điều đó không loại trừ phụ thuộc nâng cấp khác ngoài phạm vi báo cáo này.

## 6. Test repository và validation đề xuất

### Test đã đọc

- `src/test/objectstore/test_kv.cc`: `KVTest.RMRange`, `KVTest.ShardingRMRange`, `KVTest.RocksDBShardingIteratorTest` và nhóm `RocksDBResharding.*`.
- `qa/tasks/ceph_manager.py`: `test_bluestore_reshard_action`, sau reshard chạy fsck rồi revive OSD.
- `src/test/objectstore/test_bdev.cc`: `KernelDevice.Ticket45337`, chỉ dùng regular sparse file.
- `qa/workunits/cephtool/test_kvstore_tool.sh`: list/get/set/rm/compact/destructive-repair cho `bluestore-kv`.

Không responsible commit nào ở trên bổ sung test trực tiếp cho `block_cache` reshard, threshold `0`, compact-on-deletion, O_EXCL alias, synchronous `allow_eio` hoặc direct-RocksDB repair. Các test nêu trên được **đọc, chưa chạy**.

### Ma trận validation môi trường

`V03-01/02/05/06` kiểm tra behavior tự động có thể xuất hiện khi restart OSD. `V03-03/04/07` chỉ cần đưa vào runbook nếu deployment thật sự reshard, bật compact-on-deletion hoặc dự kiến dùng destructive repair.

| ID | Tiền điều kiện và pha | Workload/hành động trong lab | Kết quả mong đợi và tín hiệu lỗi | Quan sát/điều kiện dừng |
| --- | --- | --- | --- | --- |
| V03-01 | OSD target, CF sharded, OMAP có nhiều key và tombstone; post-upgrade | Đọc/list/clone OMAP với bounds bật, rồi lặp lại trên dữ liệu tương đương với bounds tắt | Tập key/header giống nhau; không vượt tail; không có RocksDB iterator error | So sánh checksum/key count và latency; dừng nếu thiếu/thừa key hoặc OSD assert |
| V03-02 | DB test có boundary key trên nhiều shard | Chạy range delete với default threshold và override `0` trên cùng fixture | Chỉ `[start,end)` bị xóa; key ngay trước/sau còn nguyên | Kiểm tra từng key, log `DeleteRange`, compaction/tombstone; dừng khi boundary sai |
| V03-03 | Bản sao disposable của OSD đã dừng, sharding spec có `block_cache={type=binned_lru}` | Reshard bằng tool target, sau đó fsck và reopen | Không lỗi parse block cache; sharding lưu đúng; DB mở và dữ liệu kiểm tra được | Giữ backup; không thử trên OSD duy nhất; dừng trước cleanup nếu prepare/processing lỗi |
| V03-04 | OSD/lab target, SST đã flush, compact-on-deletion bật với ngưỡng nhỏ có kiểm soát | Tạo rồi xóa nhiều key, iterate range để collector quan sát tombstone | Compaction chỉ kích khi đủ window/trigger; correctness không đổi | RocksDB compaction stats, disk latency, write amplification; dừng nếu latency/recovery vượt guardrail |
| V03-05 | Hai path block alias cùng major/minor trong lab, thêm case regular file và path thiếu | Mở path thứ nhất exclusive, thử path thứ hai; thử path không tồn tại | Lần hai bị từ chối; regular-file soft lock còn hoạt động; errno path thiếu được ghi nhận | Không dùng device có dữ liệu; dừng ngay nếu cả hai writer mở được |
| V03-06 | Fault-injection/mock `pread`, không dùng production device | Trả từng errno dự kiến với `allow_eio=true/false` | `true` nhận `-EIO`; `false` theo policy/error gốc | Assert return code và log; không inject lỗi trên OSD thật |
| V03-07 | RocksDB fixture hỏng có thể bỏ, tool target | Gọi direct-backend destructive repair trong sandbox | Không segfault/null dereference; có status rõ và DB được kiểm tra sau đó | Chỉ fixture; dừng và bỏ bản sao nếu repair báo lỗi |

Các scenario trên là thiết kế kiểm chứng, không phải ủy quyền chạy trên cluster. Với thao tác reshard/repair/compaction, cần runbook, backup và stop condition cụ thể của môi trường trước khi thực thi.

## 7. Khoảng trống và kết luận áp dụng

Cần As-Is để quyết định mức áp dụng: giá trị `bluestore_rocksdb_cf/cfs`, `osd_rocksdb_iterator_bounds_enabled`, `rocksdb_delete_range_threshold`, ba option compact-on-deletion; số lượng/tình trạng OMAP tombstone; device/LVM/symlink/container mapping; kế hoạch dùng reshard/repair; và layout DB/WAL thực tế. Không có các dữ liệu đó nên báo cáo không đưa ra GO/NO-GO hay con số cải thiện latency/IOPS.

Kết luận code-level có confidence cao: target thay đổi iterator/range-delete và harden block-device open đúng như mô tả. Hai điểm cần kiểm chứng ưu tiên là correctness/boundary của bounded iterator trên workload OMAP thực tế và việc `stat()` failure trong `KernelDevice::open` trả/log sai errno. Compact-on-deletion và reshard chỉ nên đánh giá khi cluster thực sự dùng các tính năng tương ứng.
