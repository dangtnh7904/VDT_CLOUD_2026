# 03 — KV/RocksDB, block device, DB/WAL và compaction: v17.2.7 → v18.2.7

**Binary gate owner 03 đã hoàn tất; applicability và lab còn mở.** [CSV đầy đủ của owner](./03-rocksdb-block-device.csv) có 21 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 18`, `trivial = 3`, chưa phân loại = 0. Finding dưới đây chỉ lấy từ hàng `affect`.

## Phạm vi và phương pháp

Owner này bao phủ KV backend, KernelDevice/AIO, PMEM, SPDK và KStore. Nguồn chính là full endpoint hunk, symbol ở hai tag, caller BlueStore/BlueFS/ObjectStore và option schema. Repo shallow nên chưa có commit-range history đủ dùng; các kết luận dưới đây giới hạn ở behavior hiện diện trong exact endpoints, không gắn commit intent khi object chưa được fetch.

## Finding ảnh hưởng upgrade

### KV-001 — AIO batching mới và nhánh POSIX AIO của target không build được như source hiện tại

**CSV:** `src/blk/aio/aio.cc/.h`, `src/blk/kernel/KernelDevice.cc/.h`, `src/blk/kernel/io_uring.cc/.h`. Quincy truyền `uint16_t aios_size`, dựng toàn bộ array rồi submit theo `max_iodepth`. Reef bỏ size, tự gom từng batch tối đa `max_iodepth` và retry partial `io_submit`; vì vậy Linux libaio có thể xử lý queue lớn mà không phụ thuộc cast `uint16_t`. Tuy nhiên exact `v18.2.7` trong nhánh `HAVE_POSIXAIO` có `if ((cur->n_aiocb == 1)` thiếu dấu đóng và đổi single-entry call từ `aio_read()` sang `aio_write()`.

**Điều kiện và tác động:** Linux/libaio và io_uring nhận contract batching mới sau restart OSD. Build dùng POSIX AIO, điển hình FreeBSD/custom artifact, có source-level compile blocker trước khi tới runtime; nếu downstream đã patch thì phải chứng minh bằng digest/source package. Không có wire/on-disk format change từ cụm này. **Confidence:** high cho endpoint code, medium cho artifact applicability.

**Kiểm chứng:** build đúng target options trên mọi distro/architecture được hỗ trợ; với libaio chạy queue vượt `max_iodepth`, partial-submit/error injection và restart under load. Gate artifact phải kiểm source patch nếu dùng POSIX AIO.

### KV-002 — `bdev_async_discard` được thay bằng số worker runtime và đường discard đổi contract

**CSV:** `BlockDevice.h`, `KernelDevice.cc/.h`; `HMSMRDevice.h` là supporting trivial row. Quincy dùng `bdev_enable_discard` cùng boolean `bdev_async_discard`: async tạo một discard thread, sync gọi discard trực tiếp. Reef bỏ boolean cũ, thêm `bdev_async_discard_threads` mặc định `0`, quản lý vector worker qua config observer và dùng `try_discard()`/`swap_discard_queued()` từ BlueStore/BlueFS. Khi enable discard nhưng worker count bằng 0, target chạy discard đồng bộ; số lớn hơn 0 cho phép nhiều worker.

**Điều kiện và tác động:** chỉ áp dụng khi `bdev_enable_discard=true` hoặc automation còn set `bdev_async_discard`. Một cluster từng bật hai boolean cũ sẽ không tự giữ async behavior sau target restart nếu chưa map sang worker count; latency/release ordering và drain time có thể đổi. Mỗi OSD dùng behavior của binary/config hiện tại, nên mixed cohort có thể discard khác nhau. **Confidence:** high cho code/default, applicability chưa biết.

**Kiểm chứng:** inventory stored/effective keys, device discard support và expected async policy; lab đo write/delete/reclaim, restart/config-change, discard drain và latency với worker `0`, `1`, `>1`. Không bật discard lần đầu chỉ để thử upgrade.

### KV-003 — Reef phát health alert mới từ stalled block reads

**CSV:** `BlockDevice.cc/.h`, `KernelDevice.cc/.h`. Reef ghi timestamp khi kernel read trả `-ETIMEDOUT`, giữ queue theo `bdev_stalled_read_warn_lifetime` và phát `<device>_DEVICE_STALLED_READ_ALERT` khi đạt threshold. BlueStore/BlueFS gọi `collect_alerts()`; threshold target mặc định `1`, lifetime `86400` giây. Quincy không có queue/alert này.

**Điều kiện và tác động:** cần stalled read thực trên BLOCK/DB/WAL. Target có thể xuất hiện health warning mới sau canary dù thiết bị chưa đổi, ảnh hưởng stop/go và alert routing; OSD Quincy trong mixed phase không phát cùng signal. Đây là đổi observability, không chứng minh target gây thêm I/O timeout. **Confidence:** high cho signal, medium cho khả năng xảy ra.

**Kiểm chứng:** ghi baseline device timeout/log/health, inject timeout chỉ trong lab hoặc dùng fault fixture, xác minh key, lifetime/threshold, clear behavior và monitoring parser.

### KV-004 — VDO/thin utilization chuyển sang external block-device plugin

**CSV:** `BlockDevice.h`, `KernelDevice.cc/.h`. Quincy tự gọi VDO helpers và trả `get_thin_utilization(total, avail)`. Reef gọi `extblkdev::detect_device()`, giữ `ExtBlkDevInterfaceRef`, lấy state/metadata qua plugin rồi release khi close. Build/package của plugin thuộc owner 13 nhưng runtime dispatch nằm ở owner này.

**Điều kiện và tác động:** chỉ cluster có VDO/extended compressed block device hoặc dùng utilization cho capacity/alert. Target artifact thiếu plugin có thể vẫn mở device nhưng mất state/metadata cần cho capacity reasoning; mixed OSD báo metadata khác schema. **Confidence:** high cho dispatch, medium cho delivery/applicability.

**Kiểm chứng:** inventory device mapper/VDO, package/plugin path và metadata hiện dùng; start target artifact trên clone/device fixture, đối chiếu physical/available state và behavior khi plugin thiếu/sai phiên bản.

### KV-005 — PMEM backend thêm devdax và DML-dependent copy path

**CSV:** `src/blk/pmem/PMEMDevice.cc/.h`. Reef nhận diện character device qua `/sys/dev/char/.../subsystem=dax`, đọc size từ sysfs, map devdax không dùng `PMEM_FILE_EXCL`, đánh dấu non-rotational và không hỗ trợ bdev label. Khi build `HAVE_LIBDML`, read/write/aio-read dùng DML `mem_move`; Quincy không có các nhánh này.

**Điều kiện và tác động:** chỉ custom build bật PMEM, đặc biệt devdax/libdml. Device activation, label expectation, copy/persistence path và metadata có thể đổi sau binary replacement. Không suy performance improvement. **Confidence:** high cho code, applicability chưa biết.

**Kiểm chứng:** pin build flags/library version và loại PMEM; lab open/mount/restart, read/write/checksum, crash/replay và activation với fsdax/devdax tách riêng.

### KV-006 — SPDK target chấp nhận non-PCIe transport và thêm keep-alive processing

**CSV:** `src/blk/spdk/NVMEDevice.cc`. Quincy từ chối transport không phải PCIe và yêu cầu parse PCI address. Reef probe bằng supplied transport ID cho non-PCIe, đặt queue requests/keep-alive 10 giây và chạy thread xử lý admin completions. PCIe local vẫn dùng whitelist.

**Điều kiện và tác động:** chỉ artifact `WITH_SPDK` và OSD dùng remote/non-PCIe NVMe hoặc custom SPDK config. Target mở một activation path hoàn toàn mới; local PCIe cũng nhận queue-option changes. Không có bằng chứng trong endpoint rằng deployment hiện dùng path này. **Confidence:** high cho code, medium cho lifecycle/operational applicability.

**Kiểm chứng:** inventory SPDK transport/config/build; thử attach, sustained I/O, keep-alive loss/reconnect, close/restart và process exit trên fixture remote NVMe, đồng thời regression local PCIe.

### KV-007 — Experimental MemDB backend bị xóa khỏi factory và source

**CSV:** `src/kv/KeyValueDB.cc`, `MemDB.cc/.h`. Quincy tạo `MemDB` khi type `memdb` và experimental feature được bật, đồng thời có `_test_init`; Reef xóa factory branch và toàn bộ implementation. Target vì vậy không thể mở/tạo backend này qua `KeyValueDB::create()`.

**Điều kiện và tác động:** default production backend không phải MemDB; finding chỉ áp dụng nếu custom/test deployment thật dùng `memdb` hoặc acceptance suite còn dựa vào backend đó. Thay binary không migrate store. Một process target chọn type cũ sẽ không có factory; mixed behavior phụ thuộc process nào mở store. **Confidence:** high cho removal, applicability low/unknown.

**Kiểm chứng:** search stored config, custom launchers và QA selectors; nếu có, loại dependency hoặc chuyển fixture trước target. Không coi việc xóa backend crash-unsafe là tự động migration.

### KV-008 — Compact-on-deletion đổi scope và metric compaction đổi schema

**CSV:** `RocksDBStore.cc/.h`. Cả hai endpoint giữ `rocksdb_cf_compact_on_deletion=true`, nhưng Quincy gắn collector vào `ColumnFamilyOptions` trong `update_column_family_options()`, còn Reef gắn vào DB `Options` trong `load_rocksdb_options()`. Reef đồng thời thay counter `compact_range` bằng `compact_running`, `compact_completed`, `compact_lasted`.

**Điều kiện và tác động:** RocksDB store có tombstone/column family và monitoring đọc metric cũ. Sau restart, collector scope/timing có thể khác và metric query cũ có thể false-green; mixed OSD expose schema khác. Chưa có benchmark nên không tuyên bố nhanh/chậm hơn. **Confidence:** high cho placement/schema, medium cho compaction outcome.

**Kiểm chứng:** workload delete/tombstone trên clone, đo compaction, space amplification và latency trước/sau; kiểm Prometheus/perf consumers với cả schema và dashboard/alert fallback.

### KV-009 — KStore có failure-injection path mới thay abort bằng throw/unqueue

**CSV:** `src/os/kstore/KStore.cc/.h`. Quincy abort khi transaction chứa lỗi bất ngờ. Reef, khi `objectstore_debug_throw_on_failed_txc=true`, bỏ `TransContext` cuối khỏi sequencer, xóa context rồi throw error; mặc định option mới là false nên production-like behavior vẫn abort. Store tests target dùng option này ở ObjectStore layer.

**Điều kiện và tác động:** chỉ KStore/test fixture bật dev option. Đây là thay đổi validation/error-injection, không phải automatic recovery cho production KStore. Nó có thể đổi acceptance result và cleanup state của test khi đánh giá target. **Confidence:** high cho guarded path, applicability thấp.

**Kiểm chứng:** chạy objectstore failed-txc tests với option false/true, kiểm queue empty, exception/error và teardown; không bật option trên cluster production.

## Operational closure addenda

#### KV-001 — Closure

Mixed-version phải build và chạy cùng queue fixture trên từng distro/artifact, vì behavior là local theo OSD; full-Reef chỉ sau khi POSIX-AIO lane compile sạch hoặc được chứng minh không áp dụng. Không có on-disk migration trực tiếp, nhưng rollback canary vẫn là drain/restore artifact cũ sau I/O quiesce và checksum; không dùng artifact downstream chưa có digest/source proof.

#### KV-002 — Closure

Discard config có hiệu lực tự động sau restart/config observer; first target discard có thể giải phóng blocks nên rollback không phải đảo queue. Failback bằng restore explicit worker mapping và old binary sau drain, với free-space/overlap/fsck proof. Chưa bật async policy mới trên production chỉ để test.

#### KV-003 — Closure

Alert tự động được tạo khi target quan sát timeout và clear theo lifetime/queue logic; không phải lỗi mới do upgrade tự thân. Rollback là restore threshold/parser hoặc old daemon sau drain, không xóa evidence. Mixed/full phải tag health schema theo version và kiểm alert inject→clear với raw logs.

#### KV-004 — Closure

Plugin detection/load tự động ở device open; install/remove plugin là explicit packaging action. Rollback canary bằng drain, restore exact plugin+binary and reopen clone/device, subject to BlueStore gate. Mixed/full phải so physical/available metadata and missing-plugin failure; inventory còn thiếu nên applicability `UNKNOWN`.

#### KV-005 — Closure

Mixed-version chỉ khác local OSD/device path; test fsdax/devdax và DML/non-DML theo artifact, full-Reef sau repeated mount/restart. First target write/persist là rollback boundary cho fixture; preserve device image và old-reader checksum. Không suy compatibility/performance khi build flags chưa biết.

#### KV-006 — Closure

Mixed cohort phải canary một SPDK transport/device và giữ local PCIe baseline; full-Reef kiểm keep-alive loss/reconnect và repeated close. Rollback bằng quiesce, detach target, restore pinned SPDK/binary và reattach only after checksum. Chưa có build/transport inventory hay lifecycle result; remote path không được tự coi applicable hoặc safe.

#### KV-007 — Closure

Removal kích hoạt explicit khi config chọn `memdb`; không có migration tự động. Rollback là giữ/pin Quincy test fixture hoặc đổi test backend bằng kế hoạch tạo lại dữ liệu, không fail open target trên store cũ. Mixed/full production chỉ hợp lệ sau inventory chứng minh backend không dùng.

#### KV-008 — Closure

Collector placement/metric schema tự động đổi ở DB open; compaction mutation không có inverse trực tiếp. Rollback canary bằng restore old binary/options trên cloned store sau flush/checksum, đồng thời giữ dual dashboards. Validate tombstone/space amplification, compaction completion và latency trước/sau restart.

#### KV-009 — Closure

Path chỉ kích hoạt bằng explicit debug config; mixed/full production phải giữ option false. Rollback test là teardown/recreate fixture hoặc restore option/binary, vì failed transaction state không được dùng làm production recovery proof. Validation cần chạy cả false/true và xác minh sequencer queue, exception và cleanup.

## Trivial changes

**3 hàng.** `HMSMRDevice.h` bỏ override discard no-op nhưng base target `try_discard()` vẫn trả false cho backend này, nên outcome không đổi và hàng chỉ support KV-002. Hai file `kv_store_bench` chuyển `using namespace` sang qualification tường minh, không đổi workload hay acceptance behavior.

## Validation và giới hạn

Chưa chạy build, repository test hay lab/runtime. Ưu tiên gate artifact POSIX AIO, mapping discard key, stalled-read alert, VDO plugin, PMEM/SPDK backend và RocksDB compaction/metrics. Repo shallow nên commit/PR intent còn là evidence gap; endpoint behavior và caller đã được kiểm nhưng chưa đủ cho GO/NO-GO production.

