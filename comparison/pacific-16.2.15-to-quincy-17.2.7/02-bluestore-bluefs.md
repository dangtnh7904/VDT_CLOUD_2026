# 02 — BlueStore, BlueFS, SeaStore, replay và dữ liệu bền vững: v16.2.15 → v17.2.7

**Trạng thái: binary gate owner đã hoàn tất; kiểm chứng lab còn mở.** [CSV đầy đủ của owner](./02-bluestore-bluefs.csv) có 206 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 130`, `trivial = 76`, **chưa phân loại = 0**.

## Phạm vi và phương pháp

Owner này phụ trách BlueStore, BlueFS, SeaStore, replay và dữ liệu bền vững. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### BLU-001 — Allocation map có thể chuyển khỏi RocksDB

**CSV:** `BlueStore.cc/.h`, `FreelistManager.cc/.h`, `BitmapFreelistManager.cc/.h`, `BlueFS.h` và `simple_bitmap.cc/.h` (đều dưới `src/os/bluestore/`). Pacific lưu bitmap freelist trong RocksDB và nạp từ FM khi mở store. Quincy thêm `null` freelist manager; `allocate/release` không ghi XOR bitmap vào RocksDB khi dùng mode này. `_init_alloc()` có nhánh restore allocator từ file BlueFS; nếu file không dùng được sau shutdown bất thường, nhánh này dựng lại từ ONodes qua `SimpleBitmap`, báo `-ENOTRECOVERABLE` khi không thể phục hồi. `_open_db_and_around()` vô hiệu file allocation khi store đã dùng null manager và mở read-write ngoài repair, sau đó chuyển sang null manager nếu DB không rotational, không read-only/repair và `bluestore_allocation_from_file` bật (target default `true`, xem CFG-014); build `HAVE_LIBZBD` còn loại thiết bị SMR khỏi nhánh chuyển đổi này. Commit `272160ab5e4` mô tả việc dời allocation khỏi RocksDB; `daaec4e2c6a` sửa boundary cho `SimpleBitmap`. `BlueFS::db_is_rotational()` cung cấp kiểm tra media.

**Điều kiện/tác động:** áp dụng cho OSD BlueStore đủ điều kiện sau restart target; cũng phụ thuộc freelist đã lưu, cấu hình và DB device thực tế. Chuyển representation của free-space làm đường mount, clean shutdown, crash recovery và rollback khác trước. Nếu store đã ở null manager mà tắt `bluestore_allocation_from_file`, `_init_alloc()` trả `-ENOTSUP`; đây là ranh giới config cần kiểm trên artifact/cluster, không suy rằng đổi option về `false` sẽ rollback dữ liệu. **Evidence confidence:** high cho code/default, medium cho áp dụng và thời gian recovery vì chưa có lab.

**Kiểm chứng:** inventory backend/FМ/DB rotational và effective option; trên clone OSD target chạy clean restart rồi crash/restart, đo thời gian restore/reconstruct, allocator free extents và fsck. Thử đọc store trên binary Pacific ở lab nếu rollback là yêu cầu; không thử trên dữ liệu production chưa có bản sao. Kiểm log `restore_allocator`, `read_allocation_from_drive_on_startup`, `invalidate_allocation_file_on_bluefs`.

**Mixed/full và rollback boundary:** allocation state thuộc từng OSD store; mixed cluster có thể có OSD vẫn bitmap và OSD đã null, nên một flag cluster không mô tả đủ từng disk. Full Quincy cũng không bảo đảm mọi store chuyển nếu DB media/config khác. Pacific `FreelistManager::create()` chỉ biết bitmap/zoned và trả NULL cho `null`; `_open_fm()` assert FM tồn tại. Vì vậy failback trực tiếp store đã ghi `freelist_type=null` có chướng ngại cụ thể từ source, không chỉ thiếu test. Chụp block+DB+WAL nhất quán trước lần mở read-write target; cả tool gọi `_open_db_and_around(false,...)` ngoài repair cũng cần xét. `restore_cfb` chỉ có khi build bật macro phục hồi, phải kiểm artifact và diễn tập clone; tắt option riêng lẻ không khôi phục bitmap.

### BLU-002 — Truncate BlueFS đánh dấu metadata dirty

**CSV:** `src/os/bluestore/BlueFS.cc`. Target đặt `h->file->is_dirty = true` trong `BlueFS::truncate()` trước khi `fsync()` có thể gọi `_signal_dirty_to_log_D()` và clear cờ. Base truncate cập nhật fnode/log transaction nhưng không đặt cờ này. Commit `08100332574` nêu lỗi thiếu metadata sync cho truncate; `643123348b5`/`72e286a6587` sửa quanh dirty file và duplicate dir link. **Điều kiện/tác động:** đường truncate file BlueFS khi RocksDB SST/WAL thay đổi và có flush/fsync, đặc biệt sát crash; có thể ảnh hưởng khả năng replay metadata sau restart. Không khẳng định dữ liệu base đã hỏng hay target sửa mọi tình huống. **Evidence confidence:** high cho hunk, medium cho failure manifestation.

**Kiểm chứng:** test fault injection trên clone: ghi, truncate, fsync, kill OSD ở nhiều điểm; mount/replay và so nội dung/size file BlueFS cùng RocksDB consistency. Chưa chạy lab.

**Mixed/full và rollback:** dirty marking tự động ở truncate target; OSD base trong mixed phase vẫn có đường fsync cũ, full target không hồi metadata đã bị mất bởi crash trước nâng. Điểm khôi phục là trước thử truncate/crash, bằng snapshot nhất quán của cả BlueFS devices và RocksDB. Hạ binary tái đưa cửa sổ sync cũ vào vận hành và không hoàn nguyên truncate đã commit; sửa size/log bằng tay chưa có chứng cứ an toàn. Dừng canary nếu replay/open hoặc size/hash lệch, giữ image lỗi để đối chiếu cùng allocation gate BLU-001.

### BLU-003 — Allocation unit và tín hiệu BlueFS đổi

**CSV:** `src/os/bluestore/BlueFS.cc/.h`. Trong `_init_alloc()`, target lấy `bluefs_shared_alloc_size` trực tiếp cho shared/slow device và assert `alloc_size[id]`, trong khi base nâng shared alloc size tối thiểu theo block size của shared allocator; target thêm counters đọc/ghi theo WAL/DB/slow và đưa `_init_logger()` lên trước `_open_super()` khi mount. Đường `BlueFS::_drain_writer()` xóa IOContext trực tiếp sau `aio_wait()` thay cho queue reap; xem [KV-002](./03-rocksdb-block-device.md). Commit `80b3fa467eb`, `4e437c206e5` hỗ trợ cụm allocation/metrics.

**Điều kiện/tác động:** shared BlueFS allocation và OSD restart; nếu configured unit không tương thích allocator/block size, hành vi activation có thể khác. Metrics mới thay tín hiệu quan sát read/write trong canary, không chứng minh hiệu năng tăng. **Evidence confidence:** high cho code, medium cho áp dụng vì chưa có config/device inventory.

**Kiểm chứng:** thu `bluefs_alloc_size`, `bluefs_shared_alloc_size`, block/min alloc size, topology WAL/DB/main; lab mount OSD với cấu hình hiện có, theo dõi assert/open failure, BlueFS free-space và counters trước/sau. Thử writer drain dưới AIO và SPDK nếu dùng.

**Mixed/full và rollback:** unit được chọn tự động khi BlueFS init trên từng OSD; mixed phase có thể có cách chọn unit và counter khác dù cùng config. Full target vẫn cần unit tương thích min/block geometry, không được coi counter mới là throughput cải thiện. Giữ effective config, device topology và allocator dump trước restart; nếu open/assert thất bại thì giữ store và khôi phục config/artifact đã kiểm trong boundary BLU-001. Đổi unit lại không undo extent đã phân bổ, đổi binary không đổi dữ liệu đã ghi; chỉ dùng cấu hình cũ làm failback sau khi clone chứng minh mở được store.

### BLU-004 — Công cụ phục hồi BlueStore đổi cách khởi tạo và lệnh

**CSV:** `src/os/bluestore/bluestore_tool.cc` và `BlueStore.h`. Target thêm `-i` để lấy OSD config/identity, các action `allocmap`, `qfsck`, `restore_cfb`, `free-fragmentation`, và đổi xử lý tham số khi attach DB/WAL từ `realpath()` sang `weakly_canonical()`. Các action allocation có guard compile-time (`CEPH_BLUESTORE_TOOL_RESTORE_ALLOCATION`, `CEPH_BLUESTORE_TOOL_DISABLE_ALLOCMAP`) và gọi hàm trên BlueStore. **Điều kiện/tác động:** chỉ khi dùng tool trong rehearsal, fsck/repair hoặc khôi phục allocation map; CLI cũ và script tự động cần kiểm trên target artifact. **Evidence confidence:** high cho source, applicability tùy pipeline.

**Kiểm chứng:** trên clone store chạy `--help`, thử `-i`/`--path`, fsck, allocmap/qfsck theo đúng build flags; so exit code và log; thử attach DB/WAL với đường dẫn và size thật trước khi cập nhật runbook.

**Mixed/full và rollback:** tool là lựa chọn explicit theo workstation/artifact; daemon full Quincy không làm tool Pacific có action mới hoặc macro restore tồn tại. Trước attach/repair/restore phải giữ toàn bộ device set và identity/config snapshot; các action này có thể ghi store, nên rollback executable không undo DB/WAL attachment hoặc freelist chuyển đổi. Chạy probe/help trước, xác nhận build macro rồi dùng clone riêng; nếu unsupported, path/identity sai hoặc fsck không đạt thì dừng, không thay action bằng một lệnh repair khác để vượt gate.

### BLU-005 — Fsck/repair so statfs và zone reference khác trước

**CSV:** `src/os/bluestore/BlueStore.cc/.h`. Base `_fsck_check_pool_statfs()` duyệt record `PREFIX_STAT` và so với expected; target đối chiếu với `osd_pools`, cho phép thiếu record rỗng, sửa thiếu record từ expected khi ở repair mode và cập nhật global statfs. Target deep fsck trên SMR còn kiểm zone reference của onode với extent đầu tiên, báo lỗi nếu thiếu reference; có FIXME về repair chưa được thêm. `_fsck()` thay cleanup `goto` bằng scope guards và mở collection sớm cho null FM. **Điều kiện:** chạy fsck/repair trong rehearsal hoặc OSD mở với quick-fix; kiểm zone-ref chỉ với HM-SMR. Số lỗi và hành động sửa có thể khác giữa tool Pacific và Quincy, nên không so raw error count mà thiếu ngữ cảnh. **Evidence confidence:** high cho hunk, medium cho kết quả trên store thật.

**Kiểm chứng:** trên clone store có per-pool statfs và store zoned (nếu dùng), chạy fsck shallow/deep và repair theo quy trình; lưu log/exit code, so record trước/sau và khởi động lại OSD. Không chạy repair trực tiếp trên bản duy nhất.

**Impact, mixed/full và rollback:** correctness/statfs, recovery và tín hiệu acceptance chịu ảnh hưởng; fsck target có thể đếm/sửa khác fsck base trong mixed toolchain. Full rollout không biến số lỗi giảm thành bằng chứng data sạch, nhất là zone-ref chưa có repair. Activation là explicit fsck/repair hoặc open có quick-fix config phù hợp. Trước repair giữ store/device clone và record statfs/zone refs; repair ghi record mới, hạ tool không hoàn nguyên. Nếu thiếu zone reference, hash sai hoặc global/per-pool statfs không reconcile, giữ failure và dừng tự động repair/restart đến khi có phương án phục hồi được kiểm.

### BLU-006 — Onode thêm zone references và đổi cờ OMAP

**CSV:** `src/os/bluestore/bluestore_types.h` và hunk dùng onode trong `BlueStore.cc/.h`. Target thêm `zone_offset_refs` vào `bluestore_onode_t`, tăng DENC version từ `1` lên `2` nhưng giữ compat `1`; nhánh decode/encode của field mới có guard `struct_v >= 2`. `clear_omap_flag()` cũng clear các cờ subtype `PGMETA_OMAP`, `PERPOOL_OMAP`, `PERPG_OMAP` ngoài `FLAG_OMAP`. Commit `22b06298f1d` và `74635b5aa31` tương ứng. **Điều kiện:** zone refs liên quan OSD SMR; cờ OMAP liên quan đối tượng có OMAP. Format change là một ranh giới cần kiểm khi định rollback, nhưng `compat 1` không tự chứng minh binary Pacific đọc/ghi lại v2 an toàn. **Evidence confidence:** high cho source format, medium cho khả năng tương thích downgrade chưa thử.

**Kiểm chứng:** clone store chứa onode v1/v2 và các loại OMAP, thử mở bằng target, fsck và replay; nếu rollback là yêu cầu, thử đọc bằng base binary trên clone đã được target ghi, so metadata/OMAP và zone refs. Không suy rollback chỉ từ macro compat version.

**Impact và mixed/full:** persistent encoding/OMAP correctness đổi tự động khi target encode onode hay clear OMAP; field zone-ref chỉ có ý nghĩa cho SMR nhưng DENC v2 là contract của type. Mixed OSD có metadata local v1/v2 và cờ subtype được clear khác nhau; full target không phục hồi zone refs/cờ đã bị writer cũ bỏ qua. Compat1 chỉ là cơ chế decoder, không chứng minh base rewrite giữ field mới. Giữ clone onode/OMAP trước target write, kiểm cross-read rồi write/remount nếu failback bắt buộc; allocation/release gates vẫn áp dụng cả store.

### BLU-007 — Thuật toán chọn free extent và backend allocator thay đổi

**CSV:** `Allocator.cc/.h`, `AvlAllocator.cc`, `BtreeAllocator.cc/.h`, `StupidAllocator.cc/.h`, `fastbmap_allocator_impl.cc` dưới `src/os/bluestore/`. Ở base, AVL lấy trực tiếp đầu free range khi tìm block; target `p2roundup(start, align)` trước khi xét range có đủ chỗ. Stupid allocator ở base xét độ dài raw range rồi trả về offset đầu range; target tính chiều dài sau alignment và chọn offset đã căn. Bitmap `_align2units()` cũng căn lại offset ở target, còn base giữ offset gốc. Đây là **khác biệt giữa hai release branch**: commit Pacific-only `511e7388687` sau tag Quincy đã bỏ alignment kết quả ở AVL/Stupid/bitmap; vì vậy không được coi target là bản có mọi fix của base. Factory của target thêm backend `btree`, đồng thời truyền `zone_size` và `first_sequential_zone` vào zoned allocator; `BlueStore::_create_alloc()` gọi factory với geometry thiết bị, còn BlueFS gọi factory theo option allocator riêng. `HybridAllocator` kế thừa AVL, nên thay đổi AVL có thể áp dụng với default `hybrid`. Trong YAML target, cả `bluestore_allocator` và `bluefs_allocator` vẫn mặc định `hybrid`; `btree` có trong factory nhưng không nằm trong danh sách enum option ở endpoint này, nên cần kiểm khả năng chọn bằng artifact thật trước khi dựa vào nó. Commit target liên quan: `0eed13a4969` (unexpected ENOSPC), `acc04d103f7` (BtreeAllocator), `b185fb2b69f` (SMR factory arguments).

**Điều kiện/tác động:** allocation/recovery sau khi OSD chạy target, nhất là free extent không thẳng hàng với allocation unit, không gian gần đầy, hoặc SMR. Kết quả chọn offset và `ENOSPC` có thể khác; đây không tự chứng minh sức chứa hay hiệu năng tốt hơn trên cụm cụ thể. **Evidence confidence:** high cho code/caller/default; medium cho biểu hiện thực tế vì chưa có free-map/geometry của cluster.

**Kiểm chứng:** trên clone hoặc lab mô phỏng các free range lệch alignment và mức đầy cao; so số extent, offset alignment, `ENOSPC`, thời gian mở OSD và allocator stats trước/sau. Ghi effective `bluestore_allocator`, `bluefs_allocator`, `min_alloc_size`, geometry SMR; không thay backend trên production để thử.

**Activation, mixed/full và rollback:** alignment/extent selection tự động khi allocator target nhận request, còn chọn backend bằng option là explicit nếu artifact cho phép. Mixed OSD có thể phân bổ hoặc báo ENOSPC khác nhau ở cùng mức đầy; full target vẫn chịu phân mảnh và geometry của từng disk. Allocator chạy trong memory nhưng offsets đã dùng là persistent qua onode, nên thay option/binary không undo layout hoặc tăng dung lượng trống. Giữ dump/free-map và byte checksum trước canary, dừng nếu unaligned extent, ENOSPC bất thường hoặc fsck lỗi; việc đọc lại map khi failback phải đi cùng BLU-001/012 và không được recreate disk để thử.

### BLU-008 — RocksDB gọi sync metadata BlueFS sau thao tác file

**CSV:** `src/os/bluestore/BlueRocksEnv.cc`. Ở base, `ReuseWritableFile`, `DeleteFile`, `RenameFile` trả về sau thao tác file BlueFS; target gọi thêm `fs->sync_metadata(false)` trước khi báo thành công. Hàm này flush device và BlueFS log nếu còn pending log/dirty file, rồi có thể compact log. Commit `227184651a7` và `03ac53f7d4c` mô tả việc buộc metadata sync và tránh replay log chứa file chưa có dữ liệu. Test `test_bluefs.cc` bổ sung các ca compaction/replay, truncate/fsync và unlink/fsync.

**Điều kiện/tác động:** thao tác file RocksDB trên BlueFS khi OSD chạy target; độ bền metadata lúc crash/replay và số lần flush/log compact có thể đổi. Chưa có đo latency hay xác nhận lỗi trên cluster này. **Evidence confidence:** high cho hunk/callee, medium cho tác động hiệu năng.

**Kiểm chứng:** lab trên clone với RocksDB SST/WAL rotation, rename/delete/reuse rồi fault injection; kiểm BlueFS replay, danh sách file và RocksDB open sau restart; đo p95/p99 write/compaction cùng BlueFS sync counters trước/sau.

**Mixed/full và rollback:** sync thêm tự động trên RocksDB file operation của mỗi OSD target; OSD base trong mixed phase vẫn khác độ bền/latency và peer replication không thay sync local. Full target không sửa file đã thiếu metadata sau crash cũ. Lưu store clone trước fault injection; hạ artifact không undo rename/delete/reuse hay flush đã phát sinh và có thể phục hồi cửa sổ lỗi cũ. Dừng nếu RocksDB/BlueFS open sai hoặc latency vượt ngưỡng canary, giữ log/manifest file để phân biệt correctness với performance và xem BLU-001 trước binary failback.

### BLU-009 — Công cụ kiểm chứng allocator và SMR đổi giao diện

**CSV:** `src/test/objectstore/allocator_replay_test.cc`, `run_smr_bluestore_test.sh` và `store_test.cc`. Replay tool ở base đọc khóa JSON `allocator_type`/`allocator_name`; target đọc `alloc_type`/`alloc_name` và thêm action `try_alloc count want alloc_unit` để thử cấp phát từ dump. Target thêm script SMR dùng `targetcli` dựng thiết bị zbc, gọi `ceph_test_objectstore --gtest_filter=*/2`, rồi dọn thiết bị; không thấy caller của script này trong cây target ngoài chính script, nên đây là quy trình kiểm chứng thủ công có điều kiện, không mặc định là CI gate. `store_test.cc` thêm `--smr`, bỏ qua một số case trên SMR và thêm `FixSMRWritePointer`; đây là thay đổi coverage thực của runner khi dùng mode đó. Commit `f4d1ef9a95e`, `1fcefbe23ff`, `389facfd438`, `f893d11d1d7`, `d723f65938f`.

**Điều kiện/tác động:** chỉ khi runbook/lab sử dụng replay tool hoặc script SMR. Dump key cũ sẽ làm replay tool target không đọc đúng; test filter giới hạn tập ca được chạy. **Evidence confidence:** high cho CLI/script, low cho mức áp dụng vì chưa có pipeline kiểm chứng của người dùng.

**Kiểm chứng:** xác định dump schema và lệnh đang dùng, chạy replay trên dump mẫu; liệt kê số test với filter `*/2` và tập test cần acceptance. Chạy script SMR chỉ trên lab có thiết bị mô phỏng và quyền `targetcli`, không chạy trên OSD hay block device production.

**Mixed/full và rollback:** chọn replay/script SMR là explicit; dump schema và filter phải được pin theo version tool, daemon mixed/full không bảo đảm job có đủ coverage. `targetcli` tạo/dọn thiết bị mô phỏng là mutation của lab host, cần snapshot config/topology và dùng tên thiết bị riêng. Rollback coverage là phục hồi fixture/schema/args rồi rerun, không giữ PASS của filter chỉ chạy `*/2`; rollback script không undo writes/test formatting. Dừng khi target dump không parse, selected test thiếu hoặc topology không đúng disposable fixture.

### BLU-010 — FileStore nhận thay đổi timeout khi đang chạy

**CSV:** `src/os/filestore/FileStore.cc`. Base không đăng ký `filestore_op_thread_timeout` và `filestore_op_thread_suicide_timeout` trong `get_tracked_conf_keys()`; target đăng ký cả hai và gọi `op_wq.set_timeout()`/`set_suicide_timeout()` trong `handle_conf_change()`. Target cũng đổi cập nhật `l_filestore_sync_pause_max_lat` từ `tinc` sang `tset`, nên số liệu max pause có ý nghĩa khác trước. Commit `eab63a640dd` và `2b2d1228ad7`. Các đổi `getattrs`/backtrace trong cùng file không phải cơ sở của finding này.

**Điều kiện/tác động:** chỉ khi deployment thật còn dùng FileStore và cập nhật timeout động; nếu dùng BlueStore thì không áp dụng. Timeout/suicide mới có thể đổi việc phát hiện op treo; dashboard nào dùng max sync pause cần chú ý cách diễn giải. **Evidence confidence:** high cho hunk và config callback, low cho applicability vì chưa có inventory backend.

**Kiểm chứng:** kiểm backend OSD và effective timeout; nếu FileStore còn tồn tại, trên lab đổi config runtime rồi đọc workqueue timeout và đo max sync pause; kiểm alert đang dựa vào metric đó. Không áp dụng thay đổi timeout trực tiếp trên cluster để xác nhận finding.

**Mixed/full và rollback:** cập nhật timeout explicit có hiệu lực tự động qua callback target; base OSD có thể cần restart để nhận cùng thay đổi. Full target vẫn cần ngưỡng theo workload FileStore thực, max-pause metric mới không so trực tiếp raw delta với counter cũ. Giữ config/timeout và metric fixture trước canary; phục hồi giá trị config có thể đổi lần phát hiện tiếp theo nhưng không undo daemon suicide hoặc I/O đã commit. Nếu còn op treo/replay lỗi, dừng cập nhật và kiểm journal/store bằng artifact đã pin; báo cáo chưa chứng minh binary downgrade.

### BLU-011 — MemStore thêm đường OMAP cho Seastar và atomic capacity

**CSV:** `src/os/memstore/MemStore.cc/.h`. Base `MemStore` không có overload `omap_get_values(start_after)` bọc `WITH_SEASTAR`; target thêm overload duyệt `omap.upper_bound(*start_after)` dưới lock, dùng cho đường AlienStore/Crimson. `used_bytes` chuyển từ `uint64_t` sang `std::atomic<uint64_t>`. Commit `d0b8aeeea4d` và `02cf1816bcf` tương ứng. Thay đổi transparent comparator của xattr là API adaptation trong cùng hunk, không tự suy thay đổi định dạng lưu trữ.

**Điều kiện/tác động:** chỉ khi build `WITH_SEASTAR` và sử dụng MemStore/AlienStore cho Crimson hoặc test; không phải đường BlueStore thường. OMAP iteration và thống kê bytes có thể khác khi chạy path này. **Evidence confidence:** high cho code guard/implementation, low cho deployment applicability.

**Kiểm chứng:** kiểm build flags và backend thực tế; nếu có Crimson/AlienStore, chạy OMAP `start_after` qua nhiều key dưới concurrent reads/writes và so statfs/used bytes sau restart thử nghiệm. Không lấy kết quả MemStore làm bằng chứng cho BlueStore nếu không chạy cùng path.

**Mixed/full và rollback:** implementation tự động theo build/backend khi caller OMAP dùng overload mới; mixed Crimson/AlienStore có thể có iterator/capacity khác, full target không làm backend memory trở thành bền vững. Overload target assert `start_after` có giá trị, nên cần test optional rỗng qua caller trước xác nhận contract. Trước đổi artifact giữ fixture/object/OMAP nguồn; process rollback không khôi phục memory state bị mất khi dừng, và không lấy clone file của BlueStore làm backup MemStore. Chưa biết backend/caller hoặc hành vi persistence thực của triển khai này.

### BLU-012 — SMR zone-state đổi định dạng lưu trong RocksDB

**CSV:** `src/os/bluestore/zoned_types.cc/.h`, `ZonedFreelistManager.cc/.h`, `ZonedAllocator.cc/.h`. Base `zone_state_t::encode()` ghép `num_dead_bytes` và `write_pointer` dạng 32 bit vào **một** `uint64_t`; target xóa encoder cũ và ghi hai `uint64_t` tuần tự trong header, mở rộng cả hai field trong memory thành 64 bit. `ZonedFreelistManager::load_zone_state_from_db()` vẫn gọi `zone_state.decode(p)` khi đọc RocksDB. Trong các hunk đã xem không có nhánh decode format cũ; vì vậy khả năng mở store SMR base trực tiếp bằng target hoặc quay lui sau khi target ghi cần thử trên clone, chưa kết luận tương thích. Target cũng truyền zone geometry thành tham số riêng và khởi tạo allocator từ zone pointers trên device trong `BlueStore::_init_alloc()` thay vì trừ free range theo logic cũ. Commit `a826836dcec`, `b185fb2b69f`, `7f74551b7bd`.

**Điều kiện/tác động:** chỉ OSD BlueStore dùng HM-SMR/zoned freelist. Đây là ranh giới dữ liệu bền vững và restart/replay; nghi vấn format không được áp dụng cho OSD SSD/HDD thông thường. **Evidence confidence:** high cho format và caller, medium cho khả năng tương thích thực tế vì chưa thử store được tạo ở base.

**Kiểm chứng:** kiểm inventory backend, `zfm_*` metadata và build `HAVE_LIBZBD`; clone OSD SMR ở base, sao lưu nguyên block+DB, mở bằng target rồi kiểm zone-state records/write pointers/fsck/deep fsck. Nếu rollback cần thiết, thử mở bản clone đã ghi bởi target bằng base. Đối chiếu số byte encoding và lỗi decode; không thử chuyển đổi trực tiếp trên bản production duy nhất.

**Mixed/full và rollback boundary:** encode mới tự động khi zoned FM target ghi state; mixed cluster không chia chung zone-state giữa OSD nên replication health không chứng minh từng SMR store đọc được. Một record base dài8 byte đối chiếu target decode cần16 byte theo thứ tự write-pointer/dead-bytes; cần lưu raw record và decode failure thay vì giả định schema có version envelope. Full target chỉ đồng nhất writer, không chuyển record cũ một cách được chứng minh. Giữ block+DB+zone pointer snapshot trước target open/write; khi chưa có cross-open/repair được kiểm, xem SMR upgrade/failback là gate mở riêng.

### BLU-013 — Cleaner và accounting của zoned allocator đổi

**CSV:** `ZonedAllocator.cc/.h` và `ZonedFreelistManager.cc/.h` dưới `src/os/bluestore/`. Base zoned allocator còn đường `zoned_get_zones_to_clean()` dạng TODO; target tính `num_sequential_free`, duyệt vòng qua sequential zones, bỏ qua zone đang cleaning, ghi dead bytes theo từng zone khi release, và chọn zone để clean theo tỉ số dead/live cùng ngưỡng `min_saved`. Freelist manager tách allocation/release đi qua biên zone thành delta từng zone, và reset state bằng `txn->set()` đồng bộ trước khi bắt đầu ghi lại zone. Caller `BlueStore::_zoned_cleaner_thread()` dùng `pick_zone_to_clean()` rồi `mark_zone_to_clean_free()`. Commit `6917b2f8db8`, `8b072af0116`, `cf2c533cd83`, `09c27531754`, `63b8f2f3ff0`.

**Điều kiện/tác động:** OSD HM-SMR khi vùng sequential ít chỗ hoặc cleaner chạy. Cách tính free space, chọn vùng và replay sau reset có thể khác; không suy mức hiệu năng chỉ từ logic này. **Evidence confidence:** high cho code/caller, medium cho biểu hiện thiết bị cụ thể.

**Kiểm chứng:** trên thiết bị SMR mô phỏng/clone, tạo live/dead bytes qua nhiều zone và chạm ngưỡng low-space; đo free counter, zone chọn, write pointer, fsck sau crash ở trước/sau reset. Đối chiếu với BLU-012 vì định dạng zone-state cũng đổi.

**Mixed/full và rollback:** cleaner/accounting tự động trên OSD zoned theo low-space/workload; OSD base/target có thể reset/chọn zone khác nhau, full target không undo GC đã reclaim. Trước canary giữ live/dead accounting, zone pointers và image nhất quán; reset zone là boundary bền vững, hạ binary không tái tạo data bị reclaim hoặc state trước reset. Dừng nếu pointer lệch, free counter không reconcile hoặc live object checksum sai; khôi phục bằng backup đã kiểm và áp BLU-012, không sửa write pointer để ép mount.

### SEA-001 — SeaStore chuyển từ stub sang đường mount/mkfs thực

**CSV:** `src/crimson/os/seastore/seastore.cc/.h`. Base `SeaStore::mount()`, `umount()`, `mkfs()` chỉ trả `seastar::now()`, và `read()` trả buffer rỗng; constructor dùng ephemeral segment manager. Target `mount()` mở segment manager chính và secondary devices, kiểm magic, rồi gọi `transaction_manager->mount()`; `umount()` đóng transaction manager và devices; `mkfs()` tạo layout, metadata và roots rồi submit transaction. Target cũng thêm đường đọc object/OMAP. Các commit liên quan gồm `4554f3e3ff7` (multi-device), `c423abaf0f0` (mkfs_done check), `0f0e5993a9c` (OSD metadata files).

**Điều kiện/tác động:** chỉ khi chạy Crimson với SeaStore; BlueStore thường không đi qua đây. Đây là khác biệt activation và dữ liệu bền vững rất lớn; source hiện có không chứng minh một store SeaStore base có thể được target mở trực tiếp. **Evidence confidence:** high cho stub→implementation; low cho applicability vì chưa biết deployment có Crimson/SeaStore hay không.

**Kiểm chứng:** kiểm binary/build flags và backend thật. Nếu có SeaStore, trước hết xác định base có store bền vững thật hay chỉ stub; nếu có image base thì clone để thử mount bằng target, rồi verify fsid, collections, object/OMAP và umount/restart. Tách thử nghiệm multi-device nếu topology dùng secondary devices; không suy kết quả từ OSD BlueStore.

**Mixed/full và rollback:** backend SeaStore là opt-in qua deployment/build; mount target tự động mở persistent devices và mkfs là explicit tạo layout. Mixed daemon versions không đồng nghĩa một SeaStore device có thể thay phiên mở bằng hai endpoints: base production path ở đây là stub. Full target cần device/root metadata hợp lệ, không biến image thử nghiệm Pacific thành image có migration được hỗ trợ. Giữ image/FSID/topology trước mkfs hoặc target mount, dừng nếu không xác định nguồn image; binary rollback không undo layout/roots và base stub không phải công cụ phục hồi object.

### SEA-002 — SeaStore journal đổi record layout và replay

**CSV:** `journal.cc/.h`, `seastore_types.cc/.h`, `transaction_manager.cc/.h` dưới `src/crimson/os/seastore/`. Base `Journal::encode_record()` và replay đọc từng `record_header_t` từ journal; target chuyển encode/decode sang `seastore_types`, thêm `record_group_header_t` và `record_group_t`, metadata/data CRC, `try_decode_deltas()` cho một nhóm record. `Journal::replay_segment()` dùng `ExtentReader` quét record groups; submitter có batching và theo dõi committed boundary. `TransactionManager::mount()` replay journal rồi mở write; `submit_transaction_direct()` ghi record và cập nhật head/tail. Commit target `310ed9ee811` (record/group), `ba454780f19` (submitter/batch), `28fec462610` (scan từ record locator), `9fbc6957af2` (journal head/target fix).

**Điều kiện/tác động:** chỉ Crimson/SeaStore, đặc biệt restart sau write và crash replay. Dạng record/metadata khác trước nên tương thích forward/downgrade phải thử; không suy rằng mọi record base decode được từ kiểu mới. **Evidence confidence:** high cho hunk và caller, medium cho tính tương thích vì chưa có image/lab.

**Kiểm chứng:** lab ghi bằng base rồi clone device để mount bằng target; thử sạch và crash ở ranh giới submit/commit, so object/OMAP, journal head/tail, CRC và số record replay. Nếu rollback cần, clone đã ghi bằng target để thử đọc bằng base. Ghi log lỗi decode và thời gian replay; không dùng dữ liệu production duy nhất.

**Mixed/full và rollback:** record group writer/replayer tự động khi transaction/mount target chạy, journal format local từng store. Mixed replication không kiểm cross-decode của file journal; full target vẫn phải thử crash ở committed boundary và CRC. Trước writer target giữ toàn bộ device/journal/root checkpoint; group records/deltas đã ghi không được trở về record base bằng hạ executable. Với endpoint Pacific stub, cần phân biệt unit-test image do TransactionManager tạo và production SeaStore image trước thiết kế cross-open, rồi dừng nếu reader không nhận record hoặc checksum khác.

### SEA-003 — SeaStore thêm B-tree OMAP và xattr

**CSV:** chín file mới dưới `src/crimson/os/seastore/omap_manager*`. Base chưa có manager B-tree này, và đường SeaStore object/OMAP ở `seastore.cc` còn stub hoặc trả lỗi; target `SeaStore` gọi `BtreeOMapManager` cho OMAP/xattr get/set/list/clear. `omap_manager.h` định nghĩa interface, các file `btree/*` cài node layout, split/merge và key/value encoding; test `test_omap_manager.cc` thêm ca replay và split/merge. Commit `18991d8aa98` cùng các sửa `7d56e0e3422`, `6c3297d497c`. **Điều kiện:** Crimson dùng SeaStore; OMAP/xattr của BlueStore không chạy qua đây. **Evidence confidence:** high cho file mới và caller, low cho mức áp dụng.

**Kiểm chứng:** nếu SeaStore có trong deployment, lab tạo OMAP/xattr, ép split/merge rồi clean/crash restart; so key/value, thứ tự iterator và root metadata trước/sau. Đánh giá trên clone khi cần thử rollback; không suy tương thích B-tree chỉ từ tên class.

**Impact và mixed/full:** compatibility/correctness của OMAP/xattr mới được kích hoạt tự động khi SeaStore target xử lý operation, còn dùng backend là opt-in. Mixed nodes có implementation khác và base stub chưa có B-tree production này; full target không chứng minh old client/backend contract được đáp ứng ngoài case đã thử. Giữ root/OMAP fixture trước lần write/split đầu; hạ binary không giải mã hay chuyển B-tree về cấu trúc chưa có ở base. Nếu key order/value/root không giữ sau replay, dừng workload và giữ clone để kiểm, chưa có image/runtime kết quả.

### SEA-004 — SeaStore thêm collection manager và root bền vững

**CSV:** sáu file mới dưới `src/crimson/os/seastore/collection_manager*`. Base `SeaStore::list_collections()` trả danh sách rỗng và `create_new_collection()` chỉ tạo handle; target thêm `FlatCollectionManager` và flat node layout, `mkfs()` lấy collection root rồi `TransactionManager::write_collection_root()`, các operation list/create/remove qua manager. Commit `4fdd451edd7`, `9f22ca124e2`. **Điều kiện:** Crimson/SeaStore với collections; rủi ro liên quan init, restart và nhận diện collection, không áp dụng BlueStore. **Evidence confidence:** high cho đường gọi source, low cho applicability.

**Kiểm chứng:** lab tạo/xóa nhiều collection, remount, so root/collection listing và object membership; thử mất điện giữa cập nhật root và journal commit. Kiểm image base trước khi suy bất kỳ compatibility nào.

**Mixed/full và rollback:** create/remove collection explicit, root update/journal tự động trong transaction target; base stub có list rỗng không được dùng làm oracle dữ liệu target. Full target cần root và object membership đúng sau restart, mixed fleet không chứng minh local root backward-compatible. Trước create/remove/mkfs giữ device checkpoint và collection manifest; hạ package không khôi phục root đã đổi hay collection đã xóa. Dừng nếu root/list/object membership lệch; chưa có base image hoặc fault-injection log để xác định cửa sổ khôi phục.

### SEA-005 — SeaStore thêm đường dữ liệu object

**CSV:** `src/crimson/os/seastore/object_data_handler.cc/.h` là hai file mới. Base `SeaStore::read()` trả buffer rỗng; target `SeaStore::read()`/`_write()`/`_truncate()` gọi `ObjectDataHandler` để đọc, ghi, overwrite và truncate qua transaction manager. Test `test_object_data_handler.cc` có ca unaligned write, overwrite, hole và truncate. Commit `2b50b23cc15`, `7594b618260`. **Điều kiện:** Crimson/SeaStore; đây là đường object data trực tiếp. **Evidence confidence:** high cho hunk/caller, low cho cluster applicability.

**Kiểm chứng:** nếu dùng SeaStore, lab ghi/đọc object có hole, partial overwrite, unaligned boundary và truncate; so checksum sau restart và crash ở ranh giới transaction. Tách riêng khỏi test BlueStore thông thường.

**Impact, mixed/full và rollback:** object-data correctness/durability thay theo backend target trong read/write/truncate tự động, còn workload là explicit. Base read trả buffer rỗng nên không thể dựa phép đọc base làm chứng minh hash sau target write; mixed/full phải quan sát byte qua backend đúng và cả restart/replay. Giữ source byte fixture/checkpoint trước overwrite/truncate, dừng ngay trên hash/size/hole mismatch. Hạ binary không khôi phục byte đã overwritten hoặc layout target, chưa có dữ liệu lab hoặc artifact cross-open nên rollback là phục hồi checkpoint đã kiểm.

### SEA-006 — SeaStore chọn block/ZNS segment manager theo thiết bị

**CSV:** `segment_manager.cc/.h`, `segment_manager/block.cc/.h`, `segment_manager/zns.cc/.h` dưới `src/crimson/os/seastore/`. Base SeaStore constructor dùng `create_test_ephemeral()`; target `make_seastore()` gọi `SegmentManager::get_segment_manager(device)`, chọn `ZNSSegmentManager` khi build `HAVE_ZNS` và device báo zones, còn lại dùng `BlockSegmentManager`. Target có đường mount/mkfs/read/write/release thật cho block và ZNS, thêm device ID và secondary device metadata. `SeaStore::mount()` kiểm magic và mount các device phụ. Commit `84b040ba7d4` (ZNS), `4554f3e3ff7` (multi-device), `d7413341119` (block open với dsync) cùng các sửa validation.

**Điều kiện/tác động:** Crimson dùng SeaStore trên block device; nhánh ZNS chỉ khi `HAVE_ZNS` và phần cứng tương ứng. Chọn sai backend, metadata/magic khác hoặc secondary device thiếu có thể làm mount thất bại; chưa có thiết bị thực để đo. **Evidence confidence:** high cho factory/caller, medium cho biểu hiện cụ thể.

**Kiểm chứng:** trên lab với đúng image thiết bị, ghi device ID, magic, block/segment size và danh sách secondary; clean/crash mount, đọc/ghi, release segment và đối chiếu log. Thử ZNS chỉ nếu build/hardware hỗ trợ. `NVMeManager` random-block ở endpoint này có unit test và được compile nhưng chưa thấy production instantiation, nên không dùng nó làm bằng chứng cho backend SeaStore đang hoạt động.

**Activation, mixed/full và rollback:** chọn segment manager tự động qua factory khi deployment opt-in SeaStore; `HAVE_ZNS`/device zones quyết định backend, mkfs và attach device là explicit. Mixed nodes có thể chạy block/ZNS hoặc version khác với local layout riêng; full target không loại lỗi thiếu secondary/magic/geometry. Trước mkfs/mount giữ primary+mọi secondary và device IDs/magic nhất quán; đổi executable hoặc factory không chuyển ZNS/block layout. Dừng khi backend chọn khác manifest, secondary thiếu hay magic mismatch, giữ devices nguyên và không mkfs lại để vượt mount.

### SEA-007 — SeaStore root và LBA B-tree đổi cấu trúc

**CSV:** `root_block.h`, `lba_manager.h` và 10 file dưới `src/crimson/os/seastore/lba_manager/btree/`. Base `root_t` trong `root_block.h` có `lba_depth`, `segment_depth`, địa chỉ root LBA/segment và `onode_root`; `BtreeLBAManager::mkfs()` tạo `LBALeafNode`, ghi depth và địa chỉ vào root. Target chuyển `root_t` sang `seastore_types.h`, thay bằng `lba_root_t`, `onode_root`, `collection_root` và vùng `meta[1024]`; `BtreeLBAManager::mkfs()` gọi `LBABtree::mkfs()` và gán `lba_root`. Target thêm `lba_btree.cc/.h`, node mới và bỏ implementation node cũ; TransactionManager dùng mapping/pin trong alloc/read/replay. Commit `dc4fe22f6b9` (thay B-tree), `49affebfa5f` (pin), cùng các sửa split/merge như `74ae71ddb84`.

**Điều kiện/tác động:** Crimson/SeaStore có dữ liệu bền vững; root delta và LBA mapping quyết định khả năng tìm object sau restart. Vì layout khác rõ rệt, không suy target đọc root base hay base đọc root target; cần thử image thực. **Evidence confidence:** high cho format/source, medium cho compatibility vì chưa có image.

**Kiểm chứng:** trên clone, tạo object ở các offset và độ sâu B-tree khác nhau, ép split/merge, clean/crash restart, so LBA lookup, collection/object checksum và root delta replay. Nếu có image base, thử mount target trước khi chấp nhận nâng cấp SeaStore; thử rollback trên bản clone riêng.

**Mixed/full và rollback:** root/LBA layout mới được ghi tự động bởi mkfs/transaction target và nằm local trên store. Mixed fleet không cung cấp reader cho root target từ base; full target vẫn phải kiểm mapping ở mọi tree depth. LBA/root checkpoint phải bao phủ journal và data extents trước lần target mutation; hạ artifact không đổi `lba_root_t` hay collection root về struct Pacific. Dừng khi lookup/root delta replay lỗi; giữ image riêng cho cross-open để không làm hỏng bản checkpoint dùng khôi phục.

### SEA-008 — Onode SeaStore có layout thật và manager xử lý object

**CSV:** `onode.cc/.h`, `onode_manager.h`, `staged-fltree/fltree_onode_manager.cc/.h` và `value.cc/.h`. Base `Onode` chỉ chứa dummy string payload và `OnodeManager` trả future rỗng; `create_ephemeral()` còn trả pointer null cho SeaStore stub. Target định nghĩa `onode_layout_t` packed với size, object-info/snapset, OMAP/xattr roots và object-data metadata; `FLTreeOnodeManager` triển khai `mkfs`, find/create/erase/list và ghi dirty onode. Target `make_seastore()` thực sự tạo `FLTreeOnodeManager` và `SeaStore` dùng manager này khi xử lý object. Commit `23693c10103` đổi hint theo object hash; `d2235ba3b97` làm dải data/metadata reservation cấu hình được.

**Điều kiện/tác động:** Crimson/SeaStore; đường ghi/đọc metadata object và tìm root sau restart khác base stub. Layout mới là dữ liệu bền vững nên rollback phải kiểm image; không áp dụng BlueStore. **Evidence confidence:** high cho hunk/caller, low cho việc cluster có dùng backend này.

**Kiểm chứng:** nếu có SeaStore, lab tạo object có object-info, snapset, OMAP và xattr; restart, tìm/list/erase object, so metadata/checksum. Kiểm khả năng đọc image base trên clone và kiểm root tree cùng transaction replay.

**Mixed/full và phần chưa biết:** tạo/ghi onode layout tự động khi backend target nhận object mutation; base dummy payload/manager không có khả năng đọc lại production metadata này chỉ từ common version string. Full Quincy phải kiểm object-info/snapset/OMAP/xattr và data roots sau replay, mixed fleet chỉ là môi trường workload chứ không chứng minh decode. Chưa có build/backend inventory, persistent image hoặc exact-client test; nếu cần rollback giữ root/onode/data checkpoint và kiểm restore, không suy low applicability là low confidence về layout change.

### SEA-009 — Cây onode staged FL-tree đổi layout, split/merge và replay

**CSV:** 34 file thay đổi hoặc thêm/bỏ dưới `src/crimson/os/seastore/onode_manager/staged-fltree/`, ngoại trừ manager/value ở SEA-008 và dummy test-only. Target `FLTreeOnodeManager` dùng staged tree này; `NodeLayoutT::allocate()` lấy leaf/internal size động và hint logical address thay cho extent size cố định ở base. Các stage/key/value và node extent accessor đổi cách ghi delta, load node, split/merge; `TestReplayExtent` được gọi trong đường replayable mutation để so delta với extent kết quả. Target chuyển implementation `tree.cc` sang `tree.h`, thêm `value.cc/.h` và bỏ `tree_types.h` cũ. Commit tiêu biểu: `860ddba0f00` (validate header), `e11c1773961` (encode/decode stage size), `d2454022f0d` (root sau lookup), `53248f6a36f` (onode lifetime).

**Điều kiện/tác động:** chỉ Crimson/SeaStore với tree onode bền vững. Node layout và delta replay khác trước có thể ảnh hưởng mount, tra object và crash recovery; không khẳng định format hai endpoint tương thích. **Evidence confidence:** high cho hunk/caller, medium cho compatibility.

**Kiểm chứng:** lab insert/erase nhiều object để ép split/merge leaf và internal, crash tại điểm ghi delta, mount lại rồi so object list, root, key order và checksum. Thử old/new image theo cả chiều cần hỗ trợ trên clone; ghi decode/assert và replay timing.

**Mixed/full và rollback:** split/merge/delta mutation tự động theo object tree workload target; debug/replay checks không tự biến mọi node Pacific thành node target. Mixed OSD store layouts cần kiểm riêng, full target vẫn chịu depth/key boundaries và crash window. Giữ image, key/object manifest và root trước tree mutation; hạ binary không undo staged node encoding/deltas. Dừng khi header/decode/assert, key order, list hoặc hash sai; khôi phục snapshot đã kiểm, không chỉnh root pointer hay bỏ bad delta để ép PASS.

### SEA-010 — Cache và transaction đổi quản lý extent cùng thứ tự ghi

**CSV:** bảy file `cache.cc/.h`, `cached_extent.cc/.h`, `transaction.cc/.h` và `ordering_handle.h` dưới `src/crimson/os/seastore/`. Base đã có cache/transaction cho SeaStore thử nghiệm nhưng chưa có `OrderingHandle` và `WritePipeline` này. Target thêm các pha reserve projected usage, out-of-line writes, prepare, device submission và finalize; cache phân biệt extent hiện hữu, retired và placeholder trong transaction, cập nhật LRU/metric và xử lý conflict. `TransactionManager` cùng `Journal` dùng các đường mới khi submit và replay. Các commit liên quan gồm `277e573e4a3` (LRU), `c32300258d2` (logical pin), `0ad74ec0269` (journal ordering) và `bf9f669e06e` (conflict metrics).

**Điều kiện/tác động:** Crimson/SeaStore có nhiều transaction, đặc biệt khi có ghi đồng thời, retry hoặc crash trong lúc journal submit. Khác biệt ở ordering và lifetime extent có thể ảnh hưởng kết quả sau replay; chưa có dữ liệu lab để định lượng. **Evidence confidence:** high cho hunk/caller, medium cho biểu hiện runtime.

**Kiểm chứng:** chạy ghi đồng thời trên cùng và khác object, gây conflict/retry, ép segment roll rồi crash trước và sau journal submission; mount lại, so checksum và trạng thái retired extent. Theo dõi phase order, latency và conflict metrics.

**Mixed/full và rollback:** phases/cache/lifetime tự động khi transaction target chạy; mixed peers có thể thấy latency/retry khác nhưng committed byte correctness còn phải kiểm local replay. Full target không loại conflict của workload đồng thời. Quiesce và checkpoint journal head/tail, roots/data trước canary; hạ binary không undo transaction đã finalize/retired extent hay phục hồi ordering handle đang chạy. Dừng trên checksum mismatch, conflict loop hoặc replay boundary lệch, giữ crash image và trace phase để tách commit đã ack khỏi I/O chưa được bảo đảm.

### SEA-011 — Placement và segment cleaner thay đổi ghi ngoài journal, GC và space accounting

**CSV:** `extent_placement_manager.cc/.h` mới cùng `segment_cleaner.cc/.h`. Base chưa có `ExtentPlacementManager`; target `make_seastore()` tạo manager này và đưa vào `TransactionManager`. `SegmentedAllocator` ghi out-of-line extent, sau ghi cập nhật LBA mapping và cache; `SegmentCleaner` dùng projected usage khi chọn trim/reclaim và quản lý segment. Các commit liên quan gồm `9aad0454f4a` (placement/rewrite), `6d142533ae8` (available space) và `fbd30a4b0b7` (projected usage).

**Điều kiện/tác động:** Crimson/SeaStore với ghi dữ liệu lớn hoặc áp lực dung lượng. Space accounting và GC khác có thể đổi thời điểm báo đầy, trim journal và thu hồi extent; cần đo trên thiết bị thật hoặc image clone. **Evidence confidence:** high cho source/caller, medium cho mức tác động vận hành.

**Kiểm chứng:** lab ghi vượt nhiều segment, overwrite/delete để tạo extent chết, tăng tải tới gần đầy; đo free/projected space, segment roll, GC và journal trim. Crash trong lúc reclaim rồi mount lại, so dữ liệu và khả năng tiếp tục ghi.

**Activation, mixed/full và rollback:** placement/out-of-line write và cleaner được gọi tự động trong target transaction/low-space; lựa chọn SeaStore là explicit deployment. Mixed nodes có capacity/GC khác, full target vẫn cần headroom của từng device. Ranh giới trước reclaim/trim giữ checkpoint journal+live extent mapping+devices; package rollback không tái tạo segment đã reset/extent đã reclaim. Dừng nếu projected/free space không reconcile, GC không tiến triển hoặc live checksum sai; giữ image để replay kiểm chứng rồi chỉ khôi phục bằng checkpoint đã thử.

### SEA-012 — ExtentReader mới quét record cho replay và reclaim

**CSV:** `extent_reader.cc/.h` mới. Base đặt logic quét valid records trực tiếp trong `Journal`; target chuyển phần quét sang `ExtentReader`, kiểm header, metadata và data trước khi trả record, đồng thời cung cấp cursor quét extent cho `SegmentCleaner::gc_reclaim_space()`. `Journal::replay_segment()` dùng reader này. Commit liên quan gồm `0f3fc5af096` (tách scanner) và `28fec462610` (record locator).

**Điều kiện/tác động:** Crimson/SeaStore khi restart sau ghi hoặc chạy reclaim. Record bị cắt dở, CRC lỗi và boundary segment có thể làm replay dừng ở vị trí khác; cần thử trên image clone, không suy tương thích dữ liệu từ việc tách class. **Evidence confidence:** high cho hunk/caller, medium cho kết quả với dữ liệu hỏng.

**Kiểm chứng:** tạo journal qua nhiều segment, crash ở header/metadata/data boundary; sửa bản clone để có record lỗi checksum, so tập record được replay và object checksum. Chạy GC sau restart và xác nhận không thu hồi live extent.

**Mixed/full và rollback:** reader mới tự động dùng khi mount/replay hoặc GC target chạy, mỗi device có local journal/CRC riêng; peer khỏe trong mixed/full cluster không chứng minh scanner không bỏ record live. Trước corruption/reclaim test giữ clone input và committed sequence/object manifest. Hạ scanner không undo GC đã reclaim hay journal đã trim; dừng khi valid record tập khác expected, mất committed object hoặc live extent bị thu hồi. Chưa có crash/CRC runtime result, giữ requirement thử boundary trên đúng record-group format.

## Trivial changes đã sàng lọc

**76 hàng:** 16 test/benchmark đã sàng lọc trước đó ở `src/test/objectstore`, `src/test/filestore` và `src/test/os`; thêm ba test BlueFS/types/fast bitmap làm bằng chứng cho BLU-002/007/008 nhưng không là gate triển khai; năm hunk chỉ đổi constructor sang `string_view` hoặc thông điệp log trong allocator; ba hunk include/API signature thuần ở FileStore/JournalingObjectStore; tám test harness FileStore/objectstore chỉ đổi std/fixture hoặc thêm case allocator; một source header chỉ đổi Git mode `100755→100644`; 18 test SeaStore thêm/bỏ ca onode, journal, RBM, OMAP và transaction manager làm bằng chứng cho source SeaStore, không tự đổi đường OSD; hai file ephemeral segment manager chỉ còn được gọi từ fixture test; năm file random-block/NVMe manager mới được compile và unit test nhưng chưa có production instantiation trong endpoint target; bảy file extent-map manager cũ không có caller ngoài cụm của nó ở base và đã rời target CMake; sáu file simple FL-tree cũ bị bỏ và base không có OnodeManager production sử dụng; một file dummy node extent chỉ dùng test; một header mới chỉ định tuyến thông điệp log SeaStore. Từng hunk và commit của nhóm này đã được đối chiếu; CSV ghi lý do theo từng hàng. Replay tool, script SMR và `store_test.cc` đổi coverage kiểm chứng nên được giữ ở BLU-009.

Toàn bộ 206 hàng owner 02 đã có nhãn binary và lý do. Kiểm chứng runtime trên SeaStore vẫn cần image và cấu hình cluster thực.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Kiểm chứng các finding trên image clone và cấu hình backend thực; duy trì liên kết từ từng hàng `affect` tới finding ID.
- Đã đối soát binary gate: `130 affect + 76 trivial = 206` và tóm tắt các cụm trivial ở trên.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
