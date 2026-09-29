# 03 — KV/RocksDB, block device, DB/WAL và compaction: v16.2.15 → v17.2.7

**Binary gate owner 03 đã hoàn tất.** [CSV đầy đủ của owner](./03-rocksdb-block-device.csv) có 38 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv): `affect = 23`, `trivial = 15`, chưa phân loại = 0. Các finding chi tiết dưới đây chỉ lấy từ hàng `affect`. Suite tổng thể vẫn đang phân tích các owner khác.

## Phạm vi và phương pháp

Owner này phụ trách KV/RocksDB, block device, DB/WAL và compaction. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### KV-001 — LevelDB backend không còn trong target

**CSV:** `src/kv/KeyValueDB.cc`, `src/kv/LevelDBStore.cc`, `src/kv/LevelDBStore.h`; build hunk cùng hành vi thuộc owner 13 tại `src/kv/CMakeLists.txt`. Pacific `KeyValueDB::create()` có nhánh `type == "leveldb"` khi build `WITH_LEVELDB`; Quincy bỏ nhánh đó và xóa toàn bộ `LevelDBStore`, đồng thời CMake không còn compile/link LevelDB. Commit `447564e4db680157c72a3f090e2c73cc35cfe700` ghi rõ remove support. `MonitorDBStore::open()` đọc `kv_backend` metadata, còn fallback `leveldb` cho MON rất cũ không có metadata; `_open()` gọi factory và abort nếu null. BlueStore đọc `kv_backend` rồi gọi cùng factory trong `_open_db()`, trả `-EIO` nếu null. Các caller này là context target ở `src/mon/MonitorDBStore.h:627,664` và `src/os/bluestore/BlueStore.cc:6653`; không thêm chúng vào CSV owner 03 nếu hunk tương ứng chưa được gán finding. [Tài liệu nâng cấp Quincy](https://docs.ceph.com/en/quincy/releases/quincy/) yêu cầu migrate OSD và MON sang RocksDB trước khi upgrade.

**Điều kiện:** chỉ áp dụng nếu bất kỳ MON/OSD store còn metadata `kv_backend=leveldb` hoặc MON rất cũ không có marker backend; default MON ở cả hai endpoint là RocksDB nên không suy rằng mọi cluster bị ảnh hưởng. Trong mixed-version, daemon Pacific có thể vẫn mở LevelDB nếu artifact được build với hỗ trợ đó, còn daemon Quincy không thể dùng factory này. Sau full upgrade, store LevelDB chưa migrate sẽ không mở được bằng đường code trên. Migration là thao tác riêng, không tự xảy ra khi thay binary. **Evidence confidence:** high cho code, medium cho applicability vì chưa đọc metadata cluster/artifact.

**Tác động:** khởi động MON/OSD và đường rollback/recovery của store cũ. Đáng chú ý, `mon_keyvaluedb` target vẫn liệt kê `leveldb` trong schema option và `ceph-kvstore-tool` help vẫn nhắc LevelDB; những chuỗi đó không khôi phục factory đã xóa. Không dùng config/help text làm bằng chứng store sẽ mở được.

**Kiểm chứng:** trước rollout, thu `kv_backend` metadata từng MON/OSD và xác minh tất cả là RocksDB; kiểm đặc biệt store không có marker. Nếu còn LevelDB, lập migration/rehearsal riêng theo tài liệu chính thức và snapshot phù hợp trước khi cài Quincy. Trong lab, thử khởi động một bản sao store trên đúng target artifact; failure signal là MON abort ở `_open()` hoặc BlueStore `-EIO`. Chưa chạy repository test hay lab.

### KV-002 — Đường đọc block, vòng đời IOContext và bộ đệm lớn

**CSV:** `src/blk/BlockDevice.cc/.h`, `src/blk/kernel/KernelDevice.cc/.h`, `src/blk/spdk/NVMEDevice.cc/.h`. Endpoint diff thêm `create_custom_aligned()` vào đường đọc đồng bộ và AIO của KernelDevice, dùng pool hugepage cấu hình qua `bdev_read_preallocated_huge_buffers`, fallback sang `bdev_read_buffer_alignment`, và đặt `IOContext::FLAG_DONT_CACHE` khi lấy buffer từ pool. `BlockDevice::detect_device_type()` trả `unknown` nếu build thiếu cả libaio và POSIX AIO, thay vì trả `aio`. `choose_fd()` và báo lỗi đọc cũng thay đổi. Commit về buffer/alignment và `ee33b3f19c6` hỗ trợ ngữ cảnh. Đồng thời base BlueFS gọi `queue_reap_ioc()` sau `aio_wait()`, target BlueFS xóa trực tiếp `iocv[i]`; vì vậy các hàm reap và trạng thái SPDK tương ứng bị bỏ. Caller đối chiếu: `src/os/bluestore/BlueFS.cc` hunk `_drain_writer()` (owner 02), không gán lại owner tại đây.

**Điều kiện/tác động:** áp dụng cho OSD dùng KernelDevice; nhánh hugepage chỉ hoạt động khi cấu hình pool và hệ điều hành cấp phát được. SPDK phụ thuộc backend thực tế; build thiếu AIO là trường hợp riêng. Đường đọc và đóng writer khi restart/recovery có thể khác về allocation, lỗi mở thiết bị, memory pressure và vòng đời I/O. Chưa suy ra tăng/giảm hiệu năng hay rò bộ nhớ từ diff. **Evidence confidence:** high cho đường code, medium cho tác động tài nguyên vì chưa có lab và As-Is config.

**Kiểm chứng:** thu `bdev_read_preallocated_huge_buffers`, `bdev_read_buffer_alignment`, backend block, hugepage availability và build options; chạy restart/canary OSD với read/AIO, BlueFS flush/drain và theo dõi memory, read error, crash. Nếu dùng SPDK hoặc custom no-AIO build, thử đúng artifact đó.

### KV-003 — SMR/zoned device đổi cách mở và quản lý zone

**CSV:** `src/blk/zoned/HMSMRDevice.cc/.h`; các interface chung trong `BlockDevice.h` và hook trong `KernelDevice.h` được ghi KV-002 ở CSV nhưng cũng hỗ trợ finding này. Base HMSMRDevice tự triển khai phần lớn KernelDevice; target kế thừa KernelDevice, mở `libzbd` ở `_post_open()`, đóng ở `_pre_close()`, bổ sung `reset_zone()`, `reset_all_zones()` và `get_zones()`. Commit `ca905ab05ad`, `590f826f908`, `59763171c5c` chỉ ra cụm refactor/zone handling; hunk cho thấy đường activation và thao tác zone thực tế thay đổi.

**Điều kiện/tác động:** chỉ cluster dùng HM-SMR/zoned BlueStore. Khởi động lại OSD, báo write pointer và reset zone trong cleanup/recovery có thể khác; không suy rộng sang thiết bị thông thường. **Evidence confidence:** high cho code, applicability chưa biết. **Kiểm chứng:** inventory thiết bị zoned, chạy lab với clone/thiết bị tương đương: open/close, zone report, append/reset, restart sau crash; đối chiếu `zbd_open`/`zbd_report_zones` failure signal.

### KV-004 — Duyệt KV với prefix rỗng và công cụ histogram

**CSV:** `src/kv/KeyValueDB.h`, `src/kv/KeyValueHistogram.cc/.h`, `src/tools/ceph_kvstore_tool.cc`, `src/tools/kvstore_tool.cc/.h`. `PrefixIteratorImpl` ở target chuyển `seek_to_first/last()` khi prefix rỗng sang iterator toàn DB; lệnh `ceph-kvstore-tool histogram [prefix]` mới duyệt và thống kê key/value. Commit `c50b1412009` mô tả tái sử dụng histogram của BlueStore. Đây là khả năng kiểm tra một bản sao offline store trong rehearsal/recovery, không phải bước migration tự động. Hunk help test xác nhận giao diện nhưng test row là `trivial`.

**Điều kiện/tác động:** ảnh hưởng khi dùng iterator prefix rỗng hoặc chủ động dùng công cụ chẩn đoán để kiểm tra store. Histogram quét toàn DB nên thời gian và I/O phụ thuộc kích thước store; không chạy tùy tiện trên daemon đang phục vụ. **Evidence confidence:** high cho code, medium cho lợi ích vận hành. **Kiểm chứng:** trên bản sao store, chạy histogram với prefix cụ thể và rỗng, đối chiếu số record và thời gian; giữ nguyên quy trình dừng daemon trước khi mở KV store offline.

### KV-005 — Ước lượng dung lượng RocksDB và chỉ số đọc

**CSV:** `src/kv/RocksDBStore.cc/.h`. Trong `estimate_prefix_size()`, target gọi `GetApproximateSizes()` không truyền cờ `INCLUDE_FILES` như base; target cũng bỏ perf counter `l_rocksdb_gets` và các lần tăng counter, trong khi latency vẫn còn. Caller `BlueStore.cc` dùng `estimate_prefix_size()` cho thống kê dung lượng OMAP. Đây là thay đổi tín hiệu capacity/monitoring có thể ảnh hưởng tiêu chí ổn định sau rollout; diff chưa đủ để định lượng sai khác khi RocksDB áp dụng default flag. **Evidence confidence:** high cho API/perf schema, medium cho trị số thực tế.

**Kiểm chứng:** trước/sau canary so sánh OMAP allocated, RocksDB approximate size, metric `rocksdb.get` và latency; sửa dashboard/alert nếu đang phụ thuộc counter đã bỏ. Không dùng một counter biến mất làm bằng chứng giảm tải.

### KV-006 — RocksDB cache theo age bins

**CSV:** `src/kv/rocksdb_cache/BinnedLRUCache.cc/.h`, `ShardedCache.cc/.h`. Target thêm age-bin accounting, `sum_bins`, `shift_bins`, thay cách `request_cache_bytes()` chia priority; BlueStore target gọi `import_bins()` cho KV/onode/meta/data cache. Các hunk còn đổi interface `rocksdb::Cache` để hợp bản thư viện mới (`GetDeleter`, `ApplyToAllEntries`). Commit `56351838337`, `2c445598ce5`, `be3ca10e60a` tương ứng cache binning và tương thích RocksDB. Khi OSD restart trong cửa sổ nâng cấp, phân bổ cache và memory pressure có thể đổi. Không kết luận rằng on-disk format thay đổi. **Evidence confidence:** high cho đường code, medium cho tác động hiệu năng/memory.

**Kiểm chứng:** trên canary so cache occupancy theo priority, OSD RSS, RocksDB cache miss, latency và recovery throughput trước/sau restart; kiểm đúng bản RocksDB của binary target và không trộn build artifact khác.

## Trivial changes

**15 hàng.** Đã kiểm endpoint hunk và commit/context theo cụm `T03-namespace`, `T03-namespace-log`, `T03-stdlib`, `T03-comparator`, `T03-test`. Chúng gồm qualification `std::` không đổi thuật toán, newline log PMEM, dev-only MemDB chuyển sang `std::filesystem`, comparator `std::less<>` giữ thứ tự khóa string, và fixture/benchmark/help test không tự thay đổi đường nâng cấp. CSV ghi lý do riêng cho từng hàng. Không suy ra toàn bộ file cùng thư mục là trivial.

## Kiểm chứng cần hoàn thành

- Đối soát `23 + 15 = 38` bằng validator; giữ các finding điều kiện tách khỏi kết luận áp dụng cho cluster thật.
- Thu As-Is backend, cấu hình cache/block và thử lab/canary trước khi dùng các finding để quyết định rollout.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ riêng báo cáo này.
