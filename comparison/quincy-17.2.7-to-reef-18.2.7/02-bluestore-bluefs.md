# 02 — BlueStore, BlueFS, FileStore và SeaStore: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./02-bluestore-bluefs.csv) có 220 hàng và là subset đúng thứ tự của master inventory: `affect = 176`, `trivial = 44`, chưa phân loại = 0. Tập `affect` gồm BlueStore/BlueFS production, việc loại bỏ FileStore và SeaStore có điều kiện; test và refactor tương đương vẫn được giữ trong CSV nhưng không tự trở thành finding.

## Phạm vi và giới hạn bằng chứng

So sánh là endpoint net diff giữa `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) và `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor, nên báo cáo không suy lịch sử commit từ range; kết luận dưới đây dựa trên hunk và caller ở hai endpoint.

Chưa có inventory As-Is để biết OSD nào dùng FileStore, allocator nào được chọn, có BlueFS DB/WAL tách riêng, SPDK/NVMe-oF, allocation-from-file hay Crimson SeaStore hay không. Chưa chạy repository test, mount/replay lab, crash-injection hoặc canary. SeaStore findings không áp dụng cho OSD BlueStore cổ điển, nhưng nếu có SeaStore thì thay đổi đủ rộng để chặn giả định in-place compatibility cho đến khi có lab đúng format nguồn.

## Finding ảnh hưởng upgrade

### BS-001 — Allocator đổi cách chọn extent và tính fragmentation

**Evidence.** `AvlAllocator.cc`, `BtreeAllocator.cc`, `StupidAllocator.cc` và `fastbmap_allocator_impl.cc` bỏ `p2roundup()` trên start của candidate extent; Btree còn sửa thứ tự mutate/insert để tránh iterator invalidation và tìm range chứa `start` bằng `lower_bound()`. `Allocator.cc` đổi trọng số fragmentation theo cỡ chunk và mẫu số từ từng byte sang allocation block.

**Before/after.** Quincy có thể bỏ phần đầu chưa aligned của free extent khi tìm candidate; Reef dùng đúng start đã được allocator quản lý và chỉ căn độ dài theo allocation unit ở fast bitmap. Sau restart từng OSD, allocation success, extent placement và fragmentation score có thể khác dù on-disk extents cũ không được tự sắp xếp lại. Điều kiện là allocator tương ứng được cấu hình; mixed fleet có allocation behavior khác nhau theo OSD nhưng không chia sẻ allocator state. Tác động capacity/ENOSPC/performance diagnostics; confidence `high` cho code path, workload effect chưa benchmark.

### BS-002 — BlueFS sửa replay, log runway, truncate và RocksDB close

**Evidence.** `BlueFS.cc/.h` sửa volume-selector usage khi replay, cho phép empty incremental delta, ước lượng encoded transaction bằng `bluefs_transaction_t::bound_encode()`, mở rộng log trước khi transaction vượt runway, thay log-compaction locking, và khi truncate thì cắt/release physical extents dưới dirty/log locks. `bluefs_types.h` clear `extents_index` trước rebuild. `BlueRocksEnv.cc::Close()` luôn truncate tới logical position rồi fsync.

**Before/after.** Quincy kiểm runway bằng ngưỡng cố định và truncate chủ yếu đổi logical size; Reef tính cả transaction đang chờ, ghi transaction mở rộng log riêng, và trả phần physical allocation thừa. Những thay đổi có hiệu lực ngay khi OSD Reef mount BlueFS cũ; trong mixed version mỗi OSD tự replay store của mình. Đây là đường persistence/restart và DB/WAL capacity, không phải network protocol. Tác động durability/availability/capacity; confidence `high`. Không được coi mount thành công một lần là đủ: phải kiểm clean restart và crash replay.

### BS-003 — Discard, fast shutdown và allocation-file lifecycle đổi thứ tự

**Evidence.** `BlueStore.cc::_txc_release_alloc()` dùng `BlockDevice::try_discard()` và chỉ release allocator ngay khi discard không được queue; `_close_db()` với null freelist/allocator-file chuyển queued discards trở lại allocator khi fast shutdown, drain discard rồi mới `store_allocator()`. `expand_devices()` đóng DB trước, mount read/write lại rồi mới thêm free range; metadata mới công bố `bluestore_allocation_from_file`.

**Before/after.** Quincy có nhánh sync/async discard riêng và persist allocator với ordering cũ; Reef gắn reuse extent vào completion của discard và bảo toàn queued extents khi lưu allocator file. Điều kiện gồm `bdev_enable_discard`, async discard, `osd_fast_shutdown`, null freelist/allocation-from-file hoặc device expansion. Mixed fleet không chia shared allocator state, nhưng từng OSD đổi rollback/restart boundary ngay khi chạy Reef. Tác động free-space correctness/restart/rollback; confidence `high` cho branch, chưa crash-inject.

### BS-004 — BlueStore sửa listing, shared-blob/cache accounting và local I/O behavior

**Evidence.** `BlueStore::_collection_list()` chuyển sang các temp/normal ranges với bounded KV iterators; cache stats lấy shard lock và cache-ratio validation tính cả `bluestore_cache_kv_onode_ratio`. `bluestore_types.h` sửa phạm vi tìm auxiliary shared-blob info; shared blobs/buffers/extents chuyển sang mempool riêng được target cache accounting đọc. Target còn sửa deferred-stable list handling, BlueFS extent iteration trong replay/fsck và physical capacity từ extended-block-device state.

**Before/after.** Reef có thể liệt kê temp/normal objects, tính memory budget, pool/shared-blob stats và capacity khác Quincy; dữ liệu cũ không được rewrite hàng loạt, nhưng được đọc qua implementation mới sau restart. Mixed-version behavior nằm theo primary/OSD thực thi operation, vì vậy cần xoay workload qua cả OSD cũ và mới. Tác động correctness/capacity/memory; confidence `high` cho code delta, `medium` cho applicability của extblkdev/shared-blob edge cases.

### BS-005 — Command, counter và health signal của BlueStore/BlueFS đổi

**Evidence.** allocator thêm admin-socket `fragmentation histogram`; `ceph-bluestore-tool` đổi action `fragmentation` thành `free-fragmentation` và ép volume policy cho `bluefs-stats`. BlueStore thêm allocator latency, open omap iterator, rmkeys và slow-operation counters/health queue; BlueFS đổi `alloc_unit_main` thành `alloc_unit_slow` và thêm latency/max-latency theo WAL/DB/slow device.

**Before/after.** Script dùng tên action/key Quincy có thể lỗi hoặc đọc sai sau khi binary được thay; Reef cũng có health warning dựa trên threshold/lifetime slow-op mới. Mixed fleet phát hai schema cùng lúc. Cần cập nhật collector/dashboard trước khi dùng chúng làm stop condition, và giữ raw output theo version. Tác động observability/validation; confidence `high`.

### FILESTORE-001 — Reef loại bỏ FileStore backend

**Evidence.** Toàn bộ các implementation được owner này giữ cho `src/os/filestore/` đều bị xóa: `FileStore`, file journal, journaling object store, Btrfs/XFS/ZFS backend, collection/index, writeback throttle và xattr helpers. Các unit/fixture FileStore liên quan cũng bị loại khỏi target test tree.

**Before/after.** Quincy source vẫn có FileStore; Reef endpoint không còn backend để mở một FileStore OSD. Đây là prerequisite tuyệt đối theo applicability: nếu inventory phát hiện `type=filestore`, không khởi động binary Reef trên store đó. OSD phải được thay thế/reprovision theo redundancy và data-movement plan riêng trước hop; không gộp chuyển backend vào một restart PA2. Mixed-version chỉ hợp lệ khi mọi OSD còn tham gia đều dùng backend target hỗ trợ. Tác động delivery/data availability/rollback; confidence `high` cho removal, applicability đang `UNKNOWN`.

### SS-001 — SeaStore đổi device model và persisted address/layout

**Evidence.** Reef thêm `device.*`, `SegmentManagerGroup`, random-block managers/allocators và device grouping; đổi ZNS implementation sang ZBD; `seastore_types.*`, segment manager và NVMe/RBM code đổi address, segment/device metadata và block/segment abstractions.

**Before/after.** SeaStore Quincy có device/segment model cũ; Reef có grouped devices và cả segmented/random-block journal backends. Nếu có Crimson SeaStore, mkfs/mount target đọc state qua layout mới và không được giả định tương thích chỉ vì cùng data path. Classic BlueStore không đi qua nhánh này. Tác động activation/on-disk compatibility; confidence `high` cho architecture delta, `low` cho khả năng in-place vì chưa có fixture store nguồn và lab replay.

### SS-002 — SeaStore thay journal, scan/replay và trim ownership

**Evidence.** Reef thêm segmented journal, circular-bounded journal, record submitter, circular journal space, segment allocator và record scanner; `transaction_manager.*`, `journal.*`, `transaction.h` và `ordering_handle.h` đổi mkfs/mount, replay delta, commit ordering, journal head/tails và trim callbacks.

**Before/after.** Quincy tập trung recovery qua journal/segment cleaner cũ; Reef tách submit/scan/trim và hỗ trợ journal theo backend. Crash recovery, record boundaries và trim safety vì vậy khác ngay khi target mount. Không có bằng chứng trong suite rằng Reef có thể downgrade/mount lại bằng Quincy sau khi ghi journal mới. Tác động durability/rollback; confidence `high` cho state-machine delta, compatibility conclusion giữ ở `UNKNOWN` cho đến khi lab.

### SS-003 — SeaStore thêm persistent backref và thay metadata trees

**Evidence.** Reef thêm `backref_manager` và backref B-tree, refactor fixed KV/LBA/omap trees, thay root-block links và sửa staged-fltree onode layout/replay/mutation. Collection manager và object metadata callers đổi theo transaction mutability mới.

**Before/after.** Base quản lý live mappings chủ yếu qua LBA/segment scan; target persist/merge backrefs và gắn chúng vào root/transaction lifecycle. Đây là format + replay change, không phải refactor thuần. Nếu SeaStore được dùng, phải coi lần target ghi metadata là rollback boundary chưa chứng minh. Tác động metadata correctness/recovery; confidence `high` cho implementation, `low` cho cross-version compatibility vì chưa có fixture test.

### SS-004 — SeaStore thay cleaner, cache, placement và object-data lifecycle

**Evidence.** `async_cleaner.*`, `extent_placement_manager.*`, cache/cached-extent, object-data handler và segment-cleaner code được thêm hoặc viết lại; extent reader cũ bị xóa. `seastore.cc/.h` wiring mới kết nối journal trimmer, backref manager, grouped devices và segment providers.

**Before/after.** Reef chọn/rewrite extent và thu hồi segment qua ownership mới, với accounting dirty/backref/live space khác Quincy. Điều kiện chỉ là Crimson SeaStore thực sự được build và chạy. Mixed fleet không chia local store state, nhưng canary SeaStore target phải chịu fill/rewrite/clean + restart trước rollout; downgrade sau target writes chưa được chứng minh. Tác động availability/capacity/recovery; confidence `high` cho code delta, applicability `UNKNOWN`.

### SS-005 — SeaStore log schema thêm transaction identity

**Evidence.** `src/crimson/os/seastore/logging.h` bỏ macro non-transaction cũ và thêm pointer cùng transaction ID vào các macro `LOGT/SUBLOGT`.

**Before/after.** Parser/runbook dựa vào prefix log Quincy sẽ không khớp hoàn toàn với Reef, trong khi target cung cấp identity tốt hơn để nối replay/commit. Chỉ áp dụng khi SeaStore chạy và log được dùng làm gate. Tác động observability; confidence `high`.

**Closure.** Schema tự động đổi khi SeaStore target phát log. Mixed-version và full-Reef phải tag parser theo version, lưu transaction identity và đối chiếu replay/commit correlation. Rollback là pin collector/parser cũ hoặc dual-schema, không sửa log history. Chưa có consumer inventory; kiểm chứng cần raw log fixture, parse success/error và stop/go result. Nếu SeaStore không hiện diện, đóng `N_A` bằng As-Is evidence.

## Operational closure addenda

#### BS-001 — Closure

Rollback canary là drain OSD, restore exact config/artifact và chỉ failback khi local-store compatibility gate còn mở; extents Reef đã cấp không được “đảo” bằng tay. Giữ clone/manifest và replay allocate/free trace bằng old reader trước khi coi downgrade an toàn. Gap runtime vẫn là fragmentation/ENOSPC/latency benchmark trên allocator thực.

#### BS-002 — Closure

First Reef mount/replay/truncate là rollback boundary vì có thể ghi log/extents khác; Quincy failback chỉ thử trên clone. Chưa có crash-replay artifact hay dedicated DB/WAL inventory. Kiểm chứng phải inject quanh log extension/compaction/Close, so extent allocation, DB/WAL usage, fsck và restart lần hai.

#### BS-003 — Closure

Kiểm chứng bắt buộc gồm sync/async discard × fast/normal shutdown × allocation-from-file, với crash giữa queue swap/drain. So free-space, overlap, double allocation, discard completion và clean restart; chưa có lab result nên source behavior không phải PASS.

#### BS-004 — Closure

Object/cache/accounting writes là rollback boundary: giữ immutable clone và chỉ old-mount/failback sau fsck, object manifest và checksum. Không dùng manual shared-blob edit. Mixed canary phải xoay primary rồi so listing/omap/compressed/shared blob và statfs.

#### BS-005 — Closure

Schema/health changes tự động kích hoạt khi target daemon/tool chạy; admin mutations là explicit. Rollback bằng parser/collector dual-version và restore old artifact/config, không sửa counter history. Validation lưu raw command/perf/health output, unit/labels và replay alert trước khi dùng làm stop condition.

#### SS-001 — Closure

Nếu SeaStore hiện diện, mixed daemon fleet vẫn có local format riêng nhưng rollout phải giữ exact source-format fixture; full-Reef chỉ sau mount/write/restart sạch. Target metadata write là rollback boundary, old mount chỉ trên copy. Applicability và in-place compatibility còn `UNKNOWN`.

#### SS-002 — Closure

Mixed-version phải canary từng SeaStore device fixture, crash ở submit/scan/trim và không cho two-version writers cùng store; full-Reef kiểm repeated replay/clean. Rollback conclusion vẫn `UNKNOWN` sau target journal write, vì vậy preserve source image và thử Quincy mount trên duplicate trước rollout.

#### SS-003 — Closure

Mixed canary phải mở metadata cũ bằng Reef, tạo/mutate backrefs rồi restart; full-Reef kiểm tree scan/repair consistency. First target backref/root write là rollback boundary; old reader chỉ chạy trên copy. Validation cần root/tree dump, live mapping, object checksum và replay transcript.

#### SS-004 — Closure

Kiểm chứng cần fill/rewrite/clean workload, crash trong reclaim, restart và so live/backref/dirty accounting, capacity và checksum. Chưa có exact SeaStore artifact/fixture; nếu inventory chứng minh không dùng SeaStore thì đóng `N_A`, nếu có thì rollback vẫn clone-only sau target write.

## Trivial changes

44 hàng `trivial` đã được đọc theo cụm: 39 test/fixture/benchmark rows chưa được chạy và không phải runtime acceptance; hai MemStore rows chỉ đổi debug failure injection/log subsystem và perf-interface no-op; ba BlueStore rows (`BitmapFreelistManager.cc`, `HybridAllocator.cc`, `fastbmap_allocator_impl.h`) chỉ chuyển power-of-two helper/include sang C++20 tương đương. Các companion implementation có thay đổi allocation, persistence hoặc validation thật đã được promote riêng.

## Validation đề xuất

Các scenario dưới đây là thiết kế kiểm chứng, chưa được thực thi và không cấp quyền thao tác cluster production.

1. **Backend inventory gate:** thu backend của mọi OSD từ metadata/data-dir evidence. Kỳ vọng không còn `filestore`; nếu có thì `BLOCKED`, lập replacement/reprovision plan riêng trước Reef.
2. **BlueFS replay:** clone một OSD Quincy đại diện trong lab, chạy clean mount/umount rồi crash-inject quanh log extension, compaction, truncate và RocksDB close bằng Reef; kỳ vọng replay hội tụ, không assert/CRC error, DB/WAL used/free hợp lý và lần restart kế tiếp sạch.
3. **Discard/allocation-file:** tách ma trận sync/async discard × fast/normal shutdown × allocation-from-file; kiểm không double-allocate, allocator restore không overlap BlueFS, free-space hội tụ sau restart.
4. **Allocator/capacity:** với allocator thực tế, replay cùng allocate/free trace trên hai endpoint; so ENOSPC, returned extents, fragmentation score/histogram và latency. Không dùng score cũ/mới như cùng một metric series.
5. **Object correctness:** trong mixed OSD canary, xoay primary rồi test collection listing qua temp/normal range, omap rmkeys/ranges, compressed/shared blobs, scrub và fsck read-only; kỳ vọng object set/digest/statfs không đổi ngoài schema đã biết.
6. **DB/WAL and expansion:** nếu có dedicated devices, fill tới spillover boundary, chạy `bluefs-stats`, migrate/expand rehearsal và restart; kiểm volume-selector usage, allocation unit, no overlap và action/tool names target.
7. **Monitoring dual schema:** capture admin-socket/perf/health outputs theo version; cập nhật parser cho renamed/new metrics trước khi slow-op/fragmentation trở thành rollout gate.
8. **SeaStore applicability:** nếu không có SeaStore, lưu bằng chứng build/runtime/config và đóng SS findings `N_A`. Nếu có, giữ exact source-format fixture, chạy target mount/write/clean/crash replay và thử rollback trên copy; không nâng production trước khi format compatibility được chứng minh.

## Kết luận owner

Owner 02 đã khép binary gate nhưng chưa tạo quyết định GO/NO-GO production. Hai checkpoint lớn nhất là loại trừ FileStore trước hop và chứng minh BlueFS replay/discard/allocation-file trên đúng cấu hình. SeaStore là nhánh điều kiện: có thể đóng `N_A` bằng inventory đáng tin cậy, còn nếu hiện diện thì phải coi target write là rollback boundary chưa chứng minh và cần lab riêng.
