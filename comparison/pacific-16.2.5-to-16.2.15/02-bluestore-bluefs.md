# 02 — BlueStore/BlueFS: data, metadata, replay, fsck/repair và allocation

> **Trạng thái:** hoàn thành phân tích code-level cho phạm vi owner `02-bluestore-bluefs`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`). Net diff được đọc từ cùng repo `ceph16.2.15/ceph` với `--find-renames`.
>
> **Danh sách file:** [02-bluestore-bluefs.csv](./02-bluestore-bluefs.csv). Báo cáo này không cho phép chạy `repair`, `quick-fix`, `bluefs-import`, migrate, ghi superblock hay thao tác trên OSD thật.

## 1. Phạm vi và độ phủ

CSV thành phần là tập con giữ nguyên thứ tự của inventory, gồm **37 dòng**: `M 35`, `A 2`, `+6.011/-1.878`; ưu tiên đọc `P0 24`, `P1 2`, `P2 11`. Các vùng evidence chính là:

- runtime BlueStore/BlueFS và allocator: inventory `1552–1575`;
- test lazy OMAP: `2426–2428`;
- test allocator, objectstore, BlueFS, deferred write và type: `2502–2509`;
- công cụ offline `ceph-objectstore-tool`: `2564–2565`.

Các option nằm ở `src/common/options.cc` và `src/common/legacy_config_opts.h` chỉ được đọc làm **ngữ cảnh**; chúng không được chèn vào CSV này vì owner của các dòng đó là báo cáo `06-config-defaults`. Phần RocksDB/KV và block-device sâu hơn thuộc `03-rocksdb-block-device`; ở đây chỉ phân tích giao diện BlueFS mà các thay đổi trong owner `02` trực tiếp tác động.

`P0/P1/P2` dưới đây là thứ tự đọc. **Rủi ro** được gán riêng theo điều kiện kích hoạt, hậu quả và khả năng phát hiện; không suy ra từ churn hoặc priority. Không có test repo nào được chạy trong lần phân tích này; các test được nêu là test đã đọc trong source.

CSV giữ đủ **37/37 dòng** để truy vết. Markdown chỉ phân tích sâu hành vi có đường tác động tới restart/replay, dữ liệu, rollback, thời lượng ổn định hoặc tín hiệu stop/go của upgrade. Các test, refactor, logging và chi tiết performance không chứng minh được liên hệ đó được gom ở mục trivial/support, không tạo finding riêng.

## 2. Kết luận điều hành

| ID | Hành vi đã xác minh | Priority | Rủi ro nâng cấp | Confidence |
| --- | --- | --- | --- | --- |
| `BS-001` | BlueFS có opcode log mới; reader `16.2.5` không hiểu, nên rollback binary theo từng OSD sau khi `16.2.15` đã ghi log là không an toàn nếu chưa test | P0 | **Cao cho rollback** | high |
| `BS-002` | Durability/replay được sửa cho data chưa stable, truncate, unlink+fsync và transaction nhiều block bị cắt bởi mất điện | P0 | Trung bình khi rollout; lỗi nền ở đầu cũ có hậu quả cao | high |
| `BS-003` | Deferred replay loại bỏ vùng đã được BlueFS tái cấp phát; quyết định deferred write cũng được sửa | P0 | **Cao nếu đúng chuỗi crash + pending deferred + BlueFS realloc**; thấp hơn ngoài điều kiện | high |
| `BS-004` | Chuyển legacy OMAP sang per-PG không còn bỏ key đầu hoặc tạo tên key sai; transaction được chia nhỏ | P0 | **Cao khi chạy quick-fix/repair trên legacy OMAP**; thấp trong mount thường | high |
| `BS-005` | Fsck/repair shared-blob dùng tracker giới hạn RAM và sửa nhiều lỗi ghi/xóa metadata repair | P0 | **Cao khi thật sự repair**; thấp cho upgrade không repair | high |
| `BS-006` | BlueFS compaction, volume selection, spillover và preallocation của RocksDB/BlueFS được sửa theo nhóm | P0 | Trung bình, phụ thuộc layout DB/WAL và compaction | high |
| `BS-007` | Shared allocation unit được chuẩn hóa; có fallback/cooldown; allocator thay đổi cách chọn offset | P0 | Trung bình, cao hơn nếu có config override sai hoặc thiết bị phân mảnh | medium |
| `BS-008` | Onode cache/refcount, small-write padding và blob-use accounting được sửa | P0 | Trung bình; tự động trên data path | medium |
| `BS-009` | Label write dùng direct I/O; công cụ import/migrate được sửa; thêm get/set superblock | P1 | **Cao cho thao tác offline ghi dữ liệu**; thấp nếu không dùng | high |
| `BS-010` | Alert/counter/metadata quan sát được sửa hoặc bổ sung, không phải bằng chứng tăng hiệu năng | P1 | Thấp | high |

Kết luận quan trọng nhất là `BS-001`: rolling upgrade không tạo một protocol BlueFS giữa các OSD, nhưng dữ liệu BlueFS là local và target bắt đầu ghi một opcode mà binary cũ không đọc được. Do đó “mixed cluster chạy được” không đồng nghĩa “có thể hạ một OSD đã kích hoạt target về `16.2.5`”.

Các finding `BS-001/002/003/006/007/008/010` có thể tác động trực tiếp tới restart, replay, data path hoặc validation trong rollout. `BS-004/005/009` chỉ áp dụng nếu runbook nâng cấp hoặc phục hồi sự cố thật sự gọi quick-fix, repair, import, migrate, provisioning hay ghi superblock; chúng không phải bước mặc định của package upgrade.

## 3. Findings chi tiết

### BS-001 — Opcode BlueFS mới tạo ranh giới rollback theo từng OSD

**Owner và evidence.** CSV `1558–1559`, `1569–1570`, `2507`. Trong `src/os/bluestore/bluefs_types.h`, `bluefs_transaction_t::op_t` của target thêm `OP_FILE_UPDATE_INC`; `bluefs_fnode_delta_t`, `bluefs_fnode_t::make_delta()` và `op_file_update_inc()` chỉ ghi phần extent mới. `src/os/bluestore/BlueFS.cc::_replay()` của target có nhánh giải mã opcode này. Commit chính là `21ac4f918cef16ec5b3d59d45077353795deadaf`; `303d0bd535224778048ddc3217c4e8e4cad9189e` reset delta sau replay để lần append tiếp theo không tính lại extent cũ.

**Trước → sau.** `v16.2.5` chỉ biết `OP_FILE_UPDATE`; nhánh `default` trong `_replay()` log `unrecognized op` rồi trả `-EIO`. `v16.2.15` dùng `OP_FILE_UPDATE_INC` trong flush log, preallocate, truncate và mở rộng log. Đây là khác biệt format của **BlueFS replay log**, dù encoding của transaction tổng vẫn giữ version hiện tại.

**Điều kiện kích hoạt và hiệu lực.** Hiệu lực là **tự động** sau khi OSD target mount và BlueFS ghi metadata/extent mới; không cần bật feature cluster hoặc đổi config. Target reader đọc được cả full update cũ và incremental update mới. Không tìm thấy converter hoặc nhánh tương thích ngược trong endpoint `16.2.5`.

**Mixed/full/rollback.** Trong rolling upgrade, OSD cũ không đọc thiết bị BlueFS của OSD mới, nên không có incompatibility qua network từ riêng finding này. Sau khi mỗi OSD đã ghi log mới, rollback binary của chính OSD đó về `16.2.5` có thể dừng mount/replay bằng `-EIO`. Clean unmount không được coi là làm log cũ-compatible: code compaction target cũng xây log mới bằng primitive incremental.

**Tác động và mức chắc chắn.** Category: compatibility/availability. Priority `P0`; rủi ro **cao cho rollback**, không phải rủi ro protocol của mixed cluster. Confidence `high` vì cả writer target và default-case reader base đều hiện rõ trong endpoint code. Chưa có test downgrade hai binary trong repo; đó là gap bắt buộc của validation.

**Test đã đọc.** `src/test/objectstore/test_bluefs.cc::test_update_ino1_delta_after_replay`, `test_replay`, `test_replay_growth`, các case compaction sync/async. Các test này chứng minh target tự replay; chúng không chứng minh old reader đọc được log target.

### BS-002 — BlueFS crash durability và replay kết thúc sạch hơn

**Owner và evidence.** CSV `1558–1559`, `2507`. Các symbol chính: `BlueFS::_flush_range_F()`, `_signal_dirty_to_log_D()`, `fsync()`, `truncate()`, `_replay()`. Nhóm commit:

- `d438f5e743747f2c3d73528d592e1498a705cb76`: chỉ báo file dirty cho replay log sau khi data device đã được đồng bộ;
- `eea0b883e7a4d7a67e1dc3cdec6cc6a07f48d15d`: flush block device trước khi log truncate metadata;
- `ccf3526b4dfb28e8113f44e26fef4ca370f1b0f1`: không log update cho file đã unlink;
- `e909e38ae6efb47a90015edbd6421ef9b0f163fe`: sau khi đã có record hợp lệ, transaction nhiều block cuối log không decode được được coi là điểm dừng do power loss thay vì lỗi mount tuyệt đối;
- `b444a9f478339e057bf9ac65f7145ba4381a92bf`: đọc BlueFS log lúc startup bằng non-buffered I/O để khớp cách ghi log.

**Trước → sau.** Ở đầu cũ, metadata size/allocation có thể vào replay log khi data trên một device khác còn chưa stable; truncate có thể công bố size mới trước khi data liên quan được flush; unlink+fsync có thể tạo `op_update` sau `op_unlink`; và tail transaction nhiều block bị ghi dở trả `-EIO`. Target đặt lại thứ tự durability, bỏ update của file đã xóa và chỉ nới lỗi decode trong trường hợp đã thấy record hợp lệ **và** transaction có phần `more` nhiều block.

**Điều kiện kích hoạt.** Tự động trên OSD dùng BlueFS. Các lỗi cũ cần crash/power loss hoặc chuỗi RocksDB unlink+fsync/truncate cụ thể; nhánh incomplete replay không bỏ qua corruption tùy ý vì record đầu hoặc transaction đơn block vẫn trả lỗi.

**Mixed/full.** Hiệu ứng local trên OSD đã nâng cấp; OSD cũ vẫn giữ hành vi cũ cho đến khi thay binary. Sau full upgrade, mọi OSD có thứ tự mới. Không có repair/migration thủ công; restart bằng target kích hoạt replay mới. Rollback vẫn chịu `BS-001`.

**Tác động và mức chắc chắn.** Category: correctness/availability. Priority `P0`; rủi ro rollout `trung bình` vì đường replay/durability thay đổi lớn, trong khi exposure correctness của base dưới các điều kiện trên là cao. Confidence `high`; intent được ghi trong commit và có test tái hiện. Chưa đo trên loại cache/flush thực tế của thiết bị Production.

**Test đã đọc.** `test_tracker_50965`, `test_truncate_stable_53129`, `broken_unlink_fsync_seq` trong `test_bluefs.cc`; commit test tương ứng `d4c33220825f16525dd035f91d81ddf0708cf5ad`, `2d4743dd58eda55e60e2bdb6ae1b90b83e23a8bf`, `a7797fabd1f51211afe46b43785937ad023cc652`.

### BS-003 — Deferred writes: tránh replay đè BlueFS và sửa điều kiện chọn deferred

**Owner và evidence.** CSV `1558`, `1561–1562`, `2503`, `2505–2506`, `2509`. `BlueStore::_deferred_replay()` ở target lấy extents của shared BlueFS device rồi gọi `_eliminate_outdated_deferred()`; commit `1d0ae5c375f7223fee8cb82ecbef0761d1b0f085`. `BlueStore::_do_alloc_write()` ở `16d6872c8933ed5445bcb8d1c5ccf591ef427c55` tách `need` khỏi `data_size` và quyết định all-or-none theo bytes thực ghi, thay vì suy ra từ một physical extent. Các commit `99e3fe642115db33c5f28a577dffe9d300719316`, `0f1c242906a43dbfb0d3f303a3c3b08cf9331b7`, `81aefaa554c44a6dc6fb46eba93930f31c7de518` làm rõ ngưỡng `<`, alignment/chunking và counter.

**Trước → sau.** Base replay mọi deferred op còn trong DB. Sau crash, extent object cũ đã được allocator coi là free; một lần mở/compact RocksDB bằng BlueFS trước deferred replay có thể lấy chính block đó, rồi deferred replay đè CURRENT/MANIFEST/SST. Target cắt phần deferred extent đang thuộc BlueFS và bỏ op rỗng. Ở write path, target dùng tổng `data_size` để tránh trường hợp đáng lẽ deferred nhưng lại đi direct hoặc quyết định không đồng nhất giữa blobs.

**Điều kiện kích hoạt.** Deferred write thật sự có trong endpoint và được test. Điều kiện runtime là `bluestore_prefer_deferred_size > 0` cùng write nhỏ/unaligned phù hợp; default ngữ cảnh ở target là `64 KiB` cho rotational media và `0` cho SSD nếu không override. Corruption cũ cần thêm crash còn pending deferred và BlueFS tái cấp phát trước replay, ví dụ offline DB compaction.

**Mixed/full.** Local theo OSD. OSD target tự áp dụng filtering khi mount; OSD base không có. Không cần migration/config để nhận fix, nhưng workload SSD với threshold `0` thường không đi nhánh này. Full upgrade chỉ đồng nhất implementation; không tự chứng minh không còn deferred transaction cũ—target xử lý chúng ở replay.

**Tác động và mức chắc chắn.** Category: correctness/durability và performance-policy. Priority `P0`; rủi ro **cao theo điều kiện** vì hậu quả có thể là RocksDB corruption, nhưng chuỗi kích hoạt hẹp. Confidence `high` cho corruption/fix; không tuyên bố target nhanh hơn vì chưa benchmark. Cần xác nhận giá trị hiệu dụng threshold theo từng OSD.

**Test đã đọc.** `src/test/objectstore/test_deferred.cc`, `run_test_deferred.sh` (commit `eaa02600bb96af3f523666d3a70fd451e438416e`), `StoreTestSpecificAUSize.ReproBug56488Test` (`093ba5fc6b68debbd9a2c6b85c7bb11f3f49c73e`) và các case `DeferredOnBigOverwrite*`, `DeferredDifferentChunks` trong `store_test.cc`. Script cố ý tạo crash và compact DB; chưa được chạy ở đây.

### BS-004 — Legacy OMAP → per-PG: bảo toàn key và giới hạn transaction repair

**Owner và evidence.** CSV `1561–1562`, `2506`. Symbol `BlueStore::_fsck_check_object_omap()`, helper `Onode::calc_omap_*()` và `BlueStoreRepairer::request_compaction()`. Các commit chính:

- `dc0a7e49434f76d97016934feed9a8ec806d1e42`: dùng user key đã decode thay vì nối raw encoded key;
- `e293295b5ecbbc6d4a7a4af2e07fcf99e1dc894a`: chỉ `it->next()` khi thực sự có header, không bỏ key dữ liệu đầu tiên của object không header;
- `d2c55356283bad64e267fc2f53ff62f6de08c7b7`: chia transaction khi cost đạt khoảng 16 MiB;
- `1bbcb466a5aeca3b965ea681f86b242d1b8e83f6`: yêu cầu compact DB sau bulk rewrite.

**Trước → sau.** Base có thể tạo tên OMAP sai trong conversion và có thể bỏ key đầu của object không có OMAP header; object OMAP rất lớn còn dồn vào một transaction/WAL/SST lớn. Target bảo toàn header/key/value trong ba case có header, không header và tập lớn, đồng thời flush transaction theo lô rồi compact.

**Điều kiện kích hoạt.** Không phải mọi OMAP trong cluster tự động rewrite khi binary đổi. Nhánh được chứng minh bởi test khi store chứa legacy `OMAP_BULK`, fsck được cấu hình báo lỗi thiếu per-pool/per-PG OMAP và operator gọi `quick_fix()`/repair. Đây là hành động ghi metadata có chủ đích; mount bình thường chỉ cảnh báo/đọc format hiện hữu.

**Mixed/full.** Local theo từng OSD và chỉ OSD đang chạy conversion bị tác động. Mixed cluster không tạo schema wire mới. Sau full upgrade, legacy data vẫn tồn tại cho tới khi quy trình kiểm tra/chuyển đổi được thực hiện. Activation cần thao tác explicit; không gộp vào bước restart nâng cấp.

**Tác động và mức chắc chắn.** Category: correctness/availability/operability. Priority `P0`; rủi ro **cao khi chạy conversion**, thấp nếu chỉ rolling restart. Confidence `high`. Chưa biết As-Is có legacy OMAP, số key/object hoặc dung lượng RocksDB cần cho rewrite/compaction.

**Test đã đọc.** `StoreTestOmapUpgrade.WithOmapHeader`, `.NoOmapHeader`, `.LargeLegacyToPG`; commits `7690f72dfa649da90276ede1907b84862b3b1e98`, `cd49a5017a6af0547b139ef687382b419de202aa`. Test lazy-omap-stats ở CSV `2426–2428` cải thiện orchestration deep-scrub của test, không tự chứng minh runtime OMAP migration.

### BS-005 — Fsck/repair shared blobs ít tốn RAM hơn và sửa đúng key/extent

**Owner và evidence.** CSV `1561–1562`, `1572–1573`, `2506`, `2508`. `BlueStore::_fsck_on_open()`, `_fsck_repair_shared_blobs()`, `shared_blob_2hash_tracker_t`, `sb_info_space_efficient_map_t`, `BlueStoreRepairer::fix_shared_blob()`.

**Trước → sau.** Commit `e483a3a2761b875ece09c9b2a98104e5ff75eee6` thay full in-memory per-shared-blob maps bằng two-hash ref counter có memory cap, xác định sbid nghi lỗi rồi quét object lần hai để dựng map chính xác cho tập đó. Target đồng thời sửa:

- offset sau khi một physical extent bị thay bằng nhiều extent: `39439d46303dc014cb8643f61593b05fc547e0d0`;
- accounting sau khi phục hồi missing shared-blob: `bd971c086b574e54c87041d2a4f8ae46563d78a5`;
- xóa stray pool-stat khỏi `PREFIX_STAT`, không nhầm `PREFIX_SHARED_BLOB`: `ea6b8decacc1829bd405c49e78e8e4f743509bc5`;
- xóa undecodable shared-blob bằng đúng prefix: `2f6e1ef085e372c6ceb294221ee4168b2b6e7954`.

**Điều kiện kích hoạt.** Scan xảy ra khi fsck chạy; mutation shared-blob được guard bởi `depth != FSCK_SHALLOW && repair`. Option ngữ cảnh `bluestore_fsck_shared_blob_tracker_size` ở target là fraction `0.03125` của `osd_memory_target`; kích thước thực phụ thuộc cấu hình OSD, không được hard-code là một lượng RAM cố định trong runbook.

**Mixed/full.** Local và offline/maintenance theo OSD. Upgrade bình thường không tự chạy repair trừ khi deployment đã bật fsck/repair-on-open tương ứng; phải kiểm kê config. Sau full upgrade, không có auto-heal lịch sử nếu operator không gọi repair. Không dùng `quick-fix` thay cho deep/non-shallow shared-blob repair.

**Tác động và mức chắc chắn.** Category: correctness/availability/resource usage. Priority `P0`; rủi ro **cao khi repair trên dữ liệu thật**, thấp nếu không chạy repair trong cửa sổ upgrade. Confidence `high`; còn thiếu dung lượng OSD, `osd_memory_target`, số clone/shared-blob và snapshot workload của cluster.

**Test đã đọc.** `BluestoreRepairSharedBlobTest`, `BluestoreBrokenNoSharedBlobRepairTest` (test bổ sung ở `4e0394ea682634f53769c9d018c266472fa5e686`), `shared_blob_2hash_tracker_t.basic_test`, `sb_info_space_efficient_map_t.*`. Không chạy test/injection.

### BS-006 — Log compaction, volume selector và BlueFS/RocksDB file placement

**Owner và evidence.** CSV `1558–1562`, `1569–1570`, `2506–2507`. Các symbol `BlueFS::_compact_log_sync_*`, `_compact_log_async_*`, `_make_initial_transaction()`, `RocksDBBlueFSVolumeSelector`, `OriginalVolumeSelector::get_paths()`, `BlueRocksWritableFile::Allocate()`.

**Trước → sau.** Nhóm thay đổi gồm:

- sync compaction cập nhật `log.seq_live`, `dirty.seq_live`, `log.t.seq` để replay không dừng ngay sau transaction đầu: `917e3807d27961b714c3b6bed9eae4961bb22f08`;
- compacted log có starter nhỏ tham chiếu metadata tail, tránh nhét toàn bộ allocation map vào superblock: `64e83f360fb398a2d6e72d07569599aa0dde61e5`;
- mount reset delta của log sau replay và khởi tạo logger trước allocator: `303d0bd535224778048ddc3217c4e8e4cad9189e`, `027d414ca2a1dcb01b78140375de908dcf8436fb`;
- selector không chọn device vắng mặt, `fit_to_fast` dùng được trên single-volume OSD, và spillover alert được tính lại từ usage: `edbdfd5002d4cf5895adbb9f87b7817b14272e19`, `4b8d87ede35688d0576e9a78b747f2f108a29ba`, `5b2eb371e5aaff28e942c40d9c409603799ed805`;
- `BlueRocksWritableFile::Allocate(uint64_t,uint64_t) override` thực sự override RocksDB API để BlueFS nhận preallocation: `10b607672227fa1e5f3af2a7a8187f2d79bba641`.

**Điều kiện kích hoạt.** Compaction tự động khi log vượt threshold/ratio; default ngữ cảnh `bluefs_compact_log_sync=false` chọn async nhưng sync path vẫn dùng bởi một số rewrite/migrate. Selector phụ thuộc layout có/không dedicated DB/WAL và `bluestore_volume_selection_policy`; spillover cần metadata tràn sang slow/shared device.

**Mixed/full.** Toàn bộ local. OSD đã nâng dùng selector/compaction mới, OSD cũ dùng logic cũ; không có shared BlueFS state. Sau full upgrade, cảnh báo và placement nhất quán hơn, nhưng dung lượng `block.db` không tự thay đổi. Activation tự động trừ migration/layout tool.

**Tác động và mức chắc chắn.** Category: availability/correctness/operability/performance-policy. Priority `P0`; rủi ro `trung bình`. Confidence `high` cho state transition và alert. Commit nói preallocation giúp giảm fragmentation, nhưng báo cáo **không khẳng định mức cải thiện hiệu năng** vì chưa benchmark và chưa biết RocksDB options/layout thực tế.

**Test đã đọc.** `test_simple_compaction_sync/async`, `test_compaction_sync/async`, `test_update_ino1_delta_after_replay`, `BluefsWriteInSingleDiskEnvTest`, `BluefsWriteInNoWalDiskEnvTest`, `SpilloverTest` và `SpilloverFixed*`.

### BS-007 — Allocation unit, fallback/cooldown và thay đổi vị trí extent

**Owner và evidence.** CSV `1552–1568`, `1574–1575`, `2502`, `2504`, cùng `1558–1559` cho BlueFS caller. `Allocator::allocate()/foreach()`, `AvlAllocator::_pick_block_after/_pick_block_fits`, `BlueFS::_init_alloc()` và `_allocate()`.

**Trước → sau.** Target:

- chuẩn hóa `bluefs_shared_alloc_size` thành ít nhất block size của shared allocator và assert phải chia hết cho unit: `c4117f3763262d462d87eade1e497750bd521d4a`;
- cho phép BlueFS fallback từ shared allocation size lớn về unit thật của main/slow allocator; sau một lần fail đặt cooldown, default ngữ cảnh `600s`, để tránh lặp search đắt: `bce817a451f5fc798c09ee6afe600d65b094c8d7`, `c6272752e78f366e0fe1744c74d541d6bdb105ee`;
- giới hạn first-fit search của AVL và fallback best-fit theo các option AVL;
- bỏ việc cưỡng bức **resulting LBA** theo requested alignment trong AVL/Stupid/fastbmap, vẫn giữ block-unit alignment: `511e7388687a8f619dcfc79db38d7864c24f7efa`.

**Điều kiện kích hoạt.** Tự động với mọi allocation; khác biệt rõ nhất khi free space phân mảnh, shared BlueFS device không còn extent lớn hoặc có override `bluefs_shared_alloc_size`. Override lớn nhưng không là bội số của `bluestore_min_alloc_size`/allocator block size có thể assert lúc init target; default chuẩn không cho thấy điều kiện này.

**Mixed/full.** Placement extent là local, không cần on-disk migration và không tạo wire incompatibility. OSD target có thể chọn offset khác OSD base cho cùng mẫu free space; đó không phải lỗi replication. Sau full upgrade, allocation policy đồng nhất nhưng fragmentation hiện hữu không tự biến mất.

**Tác động và mức chắc chắn.** Category: availability/performance/space efficiency. Priority `P0`; rủi ro `trung bình`, tăng nếu config override không hợp lệ hoặc OSD gần đầy/phân mảnh. Confidence `medium`: code/test xác định semantics, nhưng tác động latency/fragmentation là phụ thuộc workload nên chưa định lượng.

**Test đã đọc.** `Allocator_test.test_alloc_47883`, `fastbmap_allocator_test.test_l2_contiguous_alignment`, `test_4G_alloc_bug*` và `test_claim_free_l2`. Test expected offset thay đổi xác nhận semantics mới; nó không phải benchmark Production.

### BS-008 — Object metadata cache, refcount và small-write bookkeeping

**Owner và evidence.** CSV `1561–1562`, `1572–1573`, `2506`, `2508`. Các symbol `LruOnodeCacheShard::_trim_to()`, `OnodeSpace`, `BlueStore::Onode::get()/put()`, `_do_write_small()`, `bluestore_blob_use_tracker_t`.

**Trước → sau.** Commit `4a80641156c7d2d0ba7c3f9a2e68818a6103c7c7` bỏ fake reference dành cho pinned onode, chuyển pin/unpin vào cache trimming và tránh duplicate release; `695315b448ce137c2934f009ce51d277fe665cad` dọn phần increment giả còn lại. LRU trimming/touch được đơn giản hóa để pinned entry không làm vòng trim sai. `4411f0638eda2208045bc5b723da7a593e96f448` sửa `_do_write_small()` kiểm tra đúng `head_pad` thay vì cả `chunk_size`. `1d7ddafbf944897467031f9e9f74c3200fe6e3ce` tách `num_au`/`alloc_au` để mempool accounting theo số phần tử và bytes thật khi copy/split/prune.

**Điều kiện kích hoạt.** Tự động dưới object read/write/cache pressure; `head_pad` cần small unaligned write chạm vùng đã có logical extent. Blob-use tracker xuất hiện với blob có nhiều allocation unit và clone/split/GC. Không yêu cầu option mới.

**Mixed/full.** Local per OSD; PG replicas có thể chạy hai implementation trong rolling upgrade nhưng object format được đọc/ghi bằng encoding cũ tương thích trong các type này—`alloc_au` là runtime bookkeeping, không được thêm vào DENC. Sau full upgrade, mọi OSD dùng refcount/cache mới.

**Tác động và mức chắc chắn.** Category: correctness/availability/memory observability. Priority `P0`; rủi ro `trung bình`. Confidence `medium`: refcount intent và endpoint diff rõ, nhưng không có dedicated regression test cho toàn bộ concurrency của onode cache trong các file đổi.

**Test đã đọc.** Store tests gián tiếp exercise cache/write; `test_bluestore_types.cc::bluestore_blob_use_tracker_t.mempool_stats_test` (commit `8d26cb01c83ca02cac2a7a8079c0ea9130d1b9c9`) kiểm tra copy, grow, prune, split và trả mempool về baseline.

### BS-009 — Provisioning và công cụ offline: an toàn hơn nhưng quyền ghi mạnh hơn

**Owner và evidence.** CSV `1561–1562`, `1571`, `2564–2565`. Symbol `BlueStore::_write_bdev_label()`, `bluefs_import()`, `BlueFS::device_migrate_to_*()`, nhánh CLI `get-superblock`/`set-superblock`.

**Trước → sau.** `23ea3f0cb393aa3e142a52e65f8faf389a849639` mở label bằng `O_DIRECT` và rebuild buffer aligned; commit mô tả page 64 KiB trên AArch64 có thể khiến buffered label flush chồng lên superblock ở `0x2000`. Target cũng:

- thêm `bluefs-import` ở `1707e5b8a0eda74e36bbc61eb378237125dfb845`, rồi trong cùng endpoint đã có fix `a63beb3c561f6bbc073eb8845254d73e06aed477` mở toàn bộ DB environment để allocator được khởi tạo trước khi ghi, tránh overwrite block tùy ý;
- sửa DB→slow migration cung cấp path `db.slow` cho RocksDB: `1f7435094b1a4055def9361e57db1d04d7db6e82`;
- thêm export/import OSD superblock trong `ceph-objectstore-tool`: `b39ca9ec81d80fb6195bf656051aa37e5246392e`.

**Điều kiện kích hoạt.** Label path chỉ chạy khi provisioning/attach/mkfs/ghi label, không phải mọi restart. Import, migrate và `set-superblock` là hành động manual/offline; chúng không tự chạy khi nâng gói. Endpoint comparison không được hiểu là khuyến nghị dùng các command mới.

**Mixed/full.** Công cụ phải chạy cùng code target trên đúng OSD đã dừng và bản sao đã xác minh; mixed cluster không có negotiation. Target chứa cả lần thêm và fix của `bluefs-import`, nên net endpoint không mang implementation allocator-uninitialized trung gian. Rollback của OSD sau khi tool ghi BlueFS vẫn chịu `BS-001`.

**Tác động và mức chắc chắn.** Category: correctness/availability/operational safety. Priority `P1`; rủi ro **cao nếu operator thực thi sai**, thấp nếu không dùng trong upgrade. Confidence `high` cho code; thiếu repository integration test dành riêng cho import/migrate/superblock round trip. Không công cụ nào được chạy.

### BS-010 — Alert và counter thay đổi nghĩa quan sát, không chứng minh tăng tốc

**Owner và evidence.** CSV `1558–1562`, `2506`. Target khôi phục `BLUEFS_SPILLOVER` từ `bluefs->get_used(BDEV_SLOW)` (`5b2eb371e5aaff28e942c40d9c409603799ed805`), tôn trọng `bluestore_warn_on_spurious_read_errors` (`079f7146cf2f60b9f8c1210ebbe57995cfa3cd69`), ghi đúng latency vào `l_bluestore_clist_lat` thay vì remove counter (`983dcce607b8652a31ddf13b674c0ce7d3af4a80`), và expose `bluestore_min_alloc_size`, BlueFS allocation units, compaction latency/lock latency.

**Trước → sau.** Một số dashboard/alert có thể xuất hiện, biến mất hoặc đổi giá trị sau upgrade dù workload không đổi: spillover alert được khôi phục; spurious-read alert có thể bị ẩn đúng theo config; collection-list latency không còn làm bẩn remove metric. Đây là thay đổi observability, không phải bằng chứng data path nhanh hơn.

**Điều kiện, mixed/full và activation.** Tự động khi OSD target báo statfs/perf/metadata; `bluestore_warn_on_spurious_read_errors` là điều kiện cấu hình. Trong mixed phase, cùng một cluster có OSD cũ/mới báo metric khác semantics; alert aggregation cần xem daemon version. Sau full upgrade mới nên reset baseline dashboard.

**Tác động và mức chắc chắn.** Category: operability/detectability. Priority `P1`; rủi ro `thấp`, nhưng có thể gây false interpretation trong cửa sổ upgrade. Confidence `high`. Test `SpilloverTest` kiểm tra alert; các counter còn lại chủ yếu được xác minh bằng hunk, chưa chạy runtime.

## 4. Thay đổi trivial/support chỉ giữ đầy đủ trong CSV

Tất cả **37 dòng** vẫn nằm trong CSV. **11 dòng P2** là test/QA và chỉ được dùng làm evidence cho các finding; chúng không có tác động runtime độc lập. Các hunk header/refactor, logging, counter plumbing và tối ưu/preallocation không có chuỗi tác động riêng tới upgrade cũng không được nâng thành finding mới. Chi tiết provisioning AArch64/label chỉ có ý nghĩa khi rollout đồng thời tạo, thay hoặc relabel OSD; nếu không, nó thuộc phần support của `BS-009`.

Không lọc theo tên thư mục: tool hoặc test vẫn có thể chứng minh ranh giới rollback/recovery, nhưng bản thân chúng chỉ được phân tích sâu khi runbook có thể kích hoạt hành vi đó. Danh sách diff đầy đủ và quyết định triage từng dòng nằm trong [02-bluestore-bluefs.csv](./02-bluestore-bluefs.csv).

## 5. Mixed-version, fully upgraded và activation

| Trạng thái | Điều có thể kết luận từ code | Điều không được giả định |
| --- | --- | --- |
| Trước upgrade | `16.2.5` còn các đường replay/deferred/repair cũ nêu trên | Không suy ra cluster đang bị lỗi nếu chưa có đúng điều kiện/data state |
| Mixed OSD | Mỗi OSD dùng implementation BlueStore/BlueFS local của binary đang chạy; replica khác version không đọc BlueFS disk của nhau | Không suy ra rollback an toàn; OSD đã chạy target có thể đã ghi opcode mới (`BS-001`) |
| Sau full upgrade | Tất cả OSD hiểu incremental BlueFS log và có các fix target | Không tự chuyển legacy OMAP, không tự repair shared blob, không tăng kích thước DB/WAL, không tự xóa fragmentation |
| Tool/repair | Chỉ hiệu lực khi operator gọi đúng command/repair path | Không gộp `quick-fix`, `repair`, migrate, import hoặc set-superblock vào rolling restart |

Không thấy feature bit cluster cho các thay đổi này. Biên kích hoạt chủ yếu là lần daemon target ghi state local, config local và thao tác offline; vì thế kế hoạch rollback phải bảo vệ image/block device theo từng OSD, không chỉ OSDMap hoặc package version.

## 6. Repository tests đã đọc, chưa chạy

- `unittest_bluefs`: compaction sync/async, replay/growth, durability tracker, truncate, unlink+fsync, log delta continuation.
- `ceph_test_objectstore`: deferred write, bug 56488, OMAP legacy conversion, shared-blob repair, single/no-WAL layout và spillover.
- `unittest_deferred` + `run_test_deferred.sh`: crash có pending deferred, compact RocksDB rồi fsck để bắt overlap với BlueFS.
- `unittest_bluestore_types`: shared-blob tracker, space-efficient map và blob-use mempool accounting.
- `unittest_alloc`, `unittest_fastbmap_allocator`: allocation result/offset/alignment và fragmented-space cases.
- `ceph_test_lazy_omap_stats`: test cấp cluster cho OMAP stats/deep scrub; thay đổi ở đây là test orchestration, không phải runtime OMAP conversion.

Không có build artifact được xác nhận trong task này và không test nào ở trên được thực thi; vì vậy kết luận “test đã đọc” không được chuyển thành “test đã pass”.

## 7. Validation đề xuất trước Production

Các scenario dưới đây chỉ là thiết kế test trên lab hoặc snapshot/clone có thể phục hồi. Chúng **không** cho phép thực thi trên cluster thật.

| Scenario | Pha/tiền điều kiện | Hành động quan sát | Kết quả mong đợi và failure signal | Stop/rollback cho lần chạy sau |
| --- | --- | --- | --- | --- |
| `V-BS-01` rollback-format | Clone một OSD `16.2.5`; nâng clone lên target và phát sinh RocksDB metadata | Dừng sạch, thử reader/mount bằng target rồi thử old binary trên một bản clone khác; giữ log | Target replay thành công; old reader dự kiến báo `unrecognized op`/`-EIO`, qua đó xác nhận biên rollback | Không thử trên bản duy nhất; restore image clone, không “repair” để ép old mount |
| `V-BS-02` crash durability | Layout WAL/DB/SLOW giống Production | Lặp write+fsync/truncate/unlink rồi power-cut có kiểm soát; remount target | File metadata không trỏ data chưa stable; không replay error; RocksDB mở được | Dừng khi có checksum/I/O error; giữ image và log trước mọi repair |
| `V-BS-03` deferred replay | Threshold hiệu dụng >0, cùng min alloc/layout | Chạy reproducer tương đương `run_test_deferred.sh` trên scratch store | Sau compact + replay, fsck lặp lại không có RocksDB corruption; log cho thấy overlap được trim | Scratch-only; xóa/restore scratch image, không dùng OSD Production |
| `V-BS-04` legacy OMAP | Snapshot có object legacy: có header, không header, rất nhiều key | Fsck read-only trước; quick-fix chỉ trên clone; đọc lại toàn bộ key/value/header | Cardinality và checksum OMAP giữ nguyên; transaction/memory không vượt budget | Dừng nếu key count khác; restore snapshot, không chạy lần hai lên bản lỗi |
| `V-BS-05` shared-blob repair | Clone workload có clone/snapshot/shared blobs; ghi nhận `osd_memory_target` | Fsck regular/deep read-only, sau đó repair trên clone; fsck lại | Error count về 0, object checksum giữ nguyên, RSS trong budget | Nếu error tăng hoặc data mismatch: giữ image/log, restore; không chain repair |
| `V-BS-06` compaction/layout | Mỗi topology: single device, dedicated DB, dedicated WAL+DB, spillover | Ép workload metadata trên lab qua ngưỡng compaction/spillover; restart | Sync/async replay được; path `db`, `db.slow`, `db.wal` hợp lệ; alert khớp usage | Dừng ở ENOSPC/assert; restore device images |
| `V-BS-07` allocator/config | Sao chép mọi override BlueFS/BlueStore và mức fragmentation đại diện | Dry preflight giá trị divisibility; allocator tests và fill/trim lab | Không assert init; fallback/cooldown metric hợp lý; không false ENOSPC | Không thử sửa config giữa chừng trên Production; quay lại config snapshot |
| `V-BS-08` provisioning | Nếu có AArch64 page 64 KiB | Provision scratch OSD, ghi/đọc label và superblock qua nhiều restart | Superblock vẫn decode, OSD mount, không overwrite vùng `0x2000` | Scratch device duy nhất; dừng ngay khi label/superblock mismatch |
| `V-BS-09` mixed rolling | Cluster lab cùng release/config/workload | Nâng từng OSD, chạy object/OMAP/snapshot workload và theo dõi alerts/counters theo version | PG ổn định; checksum/client result đúng; khác metric được giải thích bởi version | Stop rollout khi có replay/mount error, checksum mismatch hoặc recovery bất thường |

## 8. Dữ liệu As-Is còn thiếu và câu hỏi chưa khép

1. Media class và giá trị hiệu dụng của `bluestore_prefer_deferred_size` trên từng OSD; nếu toàn SSD và threshold `0`, phần selection của `BS-003` ít áp dụng hơn nhưng rollback/các finding khác vẫn còn.
2. Topology `block`, `block.db`, `block.wal`, dung lượng/free/spillover và `bluestore_volume_selection_policy`; không thể kết luận placement/fragmentation từ source alone.
3. Có legacy OMAP hoặc health warning thiếu per-pool/per-PG OMAP hay không; không chạy conversion để “kiểm tra thử”.
4. Lịch sử fsck/repair, clone/snapshot density, shared-blob errors và `osd_memory_target`; thiếu các dữ liệu này thì không ước lượng thời gian/RSS repair.
5. Kiến trúc/page size, đặc biệt AArch64 64 KiB, và quy trình provisioning/attach DB/WAL.
6. Chính sách rollback hiện tại có restore block-device snapshot hay chỉ downgrade package. `BS-001` yêu cầu phương án thứ nhất hoặc một test chứng minh khác.
7. Không có benchmark nên không gán phần trăm cải thiện cho allocator, preallocation, lock split hay compaction.

## 9. Kết luận phạm vi

Target `16.2.15` chứa nhiều sửa lỗi correctness có bằng chứng trực tiếp cho BlueFS replay/durability, deferred writes, OMAP conversion và shared-blob repair. Tuy nhiên, nó đồng thời kích hoạt format log BlueFS mà `16.2.5` không đọc được; đây là ràng buộc rollback quan trọng nhất. Rolling upgrade nên tách rõ ba việc: thay binary/restart, validation data path, và mọi thao tác repair/migrate/import. Chỉ bước đầu là tự động; hai bước sau cần cửa sổ, bản sao phục hồi và tiêu chí dừng riêng.
