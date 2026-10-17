# 06 — option, default và schema cấu hình: v16.2.15 → v17.2.7

**Binary gate owner 06 đã hoàn tất; lab còn mở.** [CSV đầy đủ của owner](./06-config-defaults.csv) có 46 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv): `affect = 20`, `trivial = 26`, chưa phân loại = 0. Các finding dưới đây chỉ lấy từ hàng `affect`; gate liên quan đã được đưa vào [ma trận lab/runtime](./LAB-RUNTIME-GATES.md).

## Phạm vi và phương pháp

Owner này phụ trách option, default và schema cấu hình. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### CFG-001 — Default OSD scheduler thay đổi khi restart

**CSV:** `src/common/options.cc`, `src/common/options/osd.yaml.in`. Pacific định nghĩa `osd_op_queue=wpq` và `osd_mclock_profile=high_client_ops` ở `src/common/options.cc:3026,3164`. Quincy chuyển schema sang `src/common/options/osd.yaml.in:819,1070` với `mclock_scheduler` và `balanced`. Hunk thay đổi default có trong commit `8537dff175b25e2f0e20aa252bee6fa79def2a33` (scheduler) và `4f2bebaefbdf4e0d5cf48756cd80259a1ed6063a` (profile). [Release notes Quincy 17.2.7](https://ceph.io/en/news/blog/2023/v17-2-7-quincy-released/) xác nhận mClock là default và profile balanced ở endpoint.

**Điều kiện:** OSD Quincy được restart mà không có override `osd_op_queue` hoặc `osd_mclock_profile` tương ứng. OSD còn ở Pacific giữ default cũ, tạo khác biệt scheduler trong giai đoạn mixed-version; sau khi tất cả OSD đã lên Quincy và restart, default mới áp dụng đồng nhất. Đây là thay đổi tự động theo config hiệu dụng, không phải thao tác bật mClock riêng. Nếu có override, phải đọc config hiệu dụng trên từng OSD; không suy từ default.

**Tác động:** khác cách xếp client IO, recovery, scrub; vì vậy thời gian hồi phục và latency trong cửa sổ rollout có thể khác. Không suy ra mức tăng/giảm hiệu năng từ code. Cần đo theo workload và thiết bị. Đọc cùng [OSD-001](./01-osd-pg-recovery.md) để thấy các nhánh xử lý queue và QoS thực tế. **Evidence confidence:** high cho default, medium cho áp dụng trên cluster vì chưa có config As-Is.

**Ranh giới rollback:** snapshot MON config và effective per-OSD values trước canary. Hạ package đưa default về WPQ/high-client-ops nhưng không hoàn tác latency/recovery đã xảy ra; nếu đã pin mClock/profile trong config store thì binary downgrade cũng không tự xóa override. Rollback phải đặt explicit policy đã phê duyệt, restart từng OSD và đo lại, không đổi scheduler giữa recovery đang chạy.

**Kiểm chứng:** trước canary lấy `config dump`/effective config của từng OSD; trong lab/canary restart một OSD target, đối chiếu `osd_op_queue`, `osd_mclock_profile`, recovery/backfill và client latency với baseline. Không đổi policy trước khi có giới hạn latency/recovery chấp nhận. Repository có `qa/standalone/misc/mclock-config.sh`, `src/test/test_mclock_priority_queue.cc` và suite scheduler perf; chưa chạy các test này.

### CFG-002 — Dải cổng bind mặc định mở rộng

**CSV:** `src/common/options/global.yaml.in` (cùng hàng với CFG-003/004); định nghĩa Pacific ở `src/common/options.cc`. `ms_bind_port_max` đổi từ `7300` sang `7568`, còn `ms_bind_port_min` là `6800`. `AsyncMessenger.cc` lặp tới giá trị max khi chọn cổng. Commit `89a709da8d9e` ghi rõ thay đổi giới hạn. **Điều kiện:** daemon OSD/MDS dùng default, có nhiều daemon trên host hoặc các cổng thấp đang bận; network/firewall chỉ cho một phần dải. Trong mixed-version, daemon mới có thể bind cổng mà chính sách mạng hiện tại chưa mở. **Evidence confidence:** high cho default/caller, medium cho applicability.

**Tác động và rollback:** impact là availability/connectivity khi target bind cổng ngoài ACL cũ. Không có data migration; có thể failback daemon sau drain, nhưng hạ binary không sửa firewall hay connection đã rớt. Boundary là config/firewall snapshot trước restart; rollback an toàn hơn là pin dải cũ explicit hoặc mở dải target theo policy rồi retest peer connectivity.

**Kiểm chứng:** so effective config và firewall rules từng host trước restart; trên canary nhiều daemon, ghi port bind thực tế và thử kết nối public/cluster từ peer.

### CFG-003 — Blob nén tối thiểu trên SSD tăng

**CSV:** cùng hàng `src/common/options/global.yaml.in`. `bluestore_compression_min_blob_size_ssd` đổi `8_K` → `64_K`; `BlueStore.cc` đọc option này khi chọn `comp_min_blob_size`. Commit `7c7b6f4ed6bc` nêu tăng ngưỡng. **Điều kiện:** BlueStore dùng SSD và compression policy có hiệu lực, không override option. Sau restart trên target, tập blob đủ điều kiện nén khác trước; ảnh hưởng dung lượng và IO trong giai đoạn ổn định, không phải chuyển đổi dữ liệu cũ tự động. **Evidence confidence:** high cho code, medium cho hiệu ứng thực tế.

**Impact, mixed/full và rollback:** OSD target ghi blob mới theo threshold 64 KiB, OSD base vẫn dùng 8 KiB; full rollout chỉ đồng nhất policy, không rewrite blob cũ. Impact là capacity, write amplification và latency. Hạ binary không nén lại/giải nén blob đã ghi; lưu effective config và chỉ failback sau PG ổn định. Chưa biết media class, compression mode/ratio và fullness headroom thực tế, nên không định lượng lợi/hại trước canary.

**Kiểm chứng:** thu effective compression config và media class; trên canary đo bytes written, compression ratio, fullness và latency với workload đại diện. Đối chiếu OSD target và base trong cùng điều kiện.

### CFG-004 — RocksDB compact-on-deletion bật mặc định

**CSV:** cùng hàng `src/common/options/global.yaml.in`. `rocksdb_cf_compact_on_deletion` đổi `false` → `true`. Target `RocksDBStore.cc` dùng option để đặt sliding window/trigger trên column family; commit `d91dff3e3418` triển khai đường này. **Điều kiện:** store có tombstone do xóa nhiều và không override option. Compaction nền có thể đổi IO/cpu, dung lượng và thời gian hồi phục sau restart; không khẳng định tác động với mọi cluster. **Evidence confidence:** high cho default/caller, medium cho mức tác động.

**Mixed/full và rollback:** từng target store bật trigger sau restart còn base store giữ default false; full rollout đồng nhất policy nhưng compaction đã chạy là mutation RocksDB local. Hạ binary hoặc tắt option không dựng lại SST/tombstone trước đó; chỉ ngăn trigger tiếp theo. Chụp DB size/compaction stats, dừng canary khi latency vượt guardrail. Chưa có delete rate, tombstone/SST distribution và I/O headroom của môi trường đích.

**Kiểm chứng:** trước/sau canary theo dõi RocksDB compaction, write amplification, OSD latency và recovery rate với workload xóa phù hợp; ghi rõ override nếu có.

### CFG-005 — Option chuyển từ C++ sang YAML được sinh khi build

**CSV:** `src/common/legacy_config_opts.h`, `src/common/config.cc`, `src/common/config_values.h`, `src/common/options.h`, `src/common/options/build_options.cc/.h`, `src/common/options/legacy_config_opts.h`, `src/common/options/y2c.py`, `src/common/options/validate-options.py`. Base giữ danh sách legacy option trong header tĩnh và phần lớn option trong `options.cc`; target CMake (`src/common/options/CMakeLists.txt`, owner 13) cấu hình từng `.yaml.in`, dùng Python/PyYAML `y2c.py` sinh C++ và legacy header, sau đó `build_options()` gộp chúng và gắn service tag. Target test `validate-options` kiểm tham chiếu `see_also`. Commit `5505fc0051a`, `5ddda38da4f`, `11ba501a56e`, `6cfdd40cad0` cung cấp lịch sử cụm này.

**Điều kiện/tác động:** quan trọng nếu build target từ source hoặc mang downstream patch/config option qua nhánh. Source build mới cần Python/PyYAML và file YAML đã qua CMake substitution; option thiếu `with_legacy` có thể không được sinh vào `ConfigValues` dù định nghĩa YAML còn tồn tại. Không suy rằng binary release chính thức thiếu option; phải kiểm artifact thực tế. Service tag được thêm khi `build_options()` gộp option nên phạm vi `ceph config` có thể khác nếu option được chuyển nhóm. **Evidence confidence:** high cho đường build, medium cho tác động downstream vì chưa biết pipeline/artifact.

**Mixed/full và rollback:** config schema được nhúng vào từng binary artifact; mixed nodes có thể expose/validate option khác nhau, còn full chỉ an toàn khi toàn cohort dùng cùng generated manifest. Không có data migration, nhưng downgrade phải thay nguyên package/artifact set và restart service; không copy generated header/module riêng lẻ. Giữ build provenance và `ceph config ls/help` snapshot để rollback contract atomically.

**Kiểm chứng:** trong pipeline target chạy CMake generation, build và `validate-options`, so `ceph config ls`/`ceph config help` và effective values của option custom/legacy trên artifact thật; giữ generated headers để điều tra nếu build hoặc startup thất bại. Các YAML theo service còn đang được đối chiếu từng giá trị, vì vậy CFG-005 chưa thay thế review semantic của chúng.

### CFG-006 — Ví dụ reshard BlueStore đổi prefix column family

**CSV:** `doc/rados/configuration/bluestore-config-ref.rst`. Hunk đổi lệnh `ceph-bluestore-tool ... reshard` từ `O(3,0-13) ... L P` thành `o(3,0-13) ... l p`, đồng thời sửa ví dụ SPDK path. `RocksDBStore::parse_sharding_def()` dùng tên prefix để tạo tên column family, có phân biệt chữ hoa/thường; target default trong `global.yaml.in` vẫn dùng `O/L/P`. Đây là **lệnh thao tác offline có thể thay đổi layout store** nếu copy từ tài liệu, không phải migration tự động. Điều kiện: operator thực sự chạy reshard hoặc lấy ví dụ SPDK trong rehearsal/recovery. **Evidence confidence:** high cho khác biệt chuỗi/caller, medium cho tính đúng của hai recipe vì chưa chạy lab.

**Impact, mixed/full và rollback:** impact là availability/correctness của local store nếu recipe tạo sai column family. Version mix của daemon không kích hoạt; tool binary và store copy quyết định behavior, và chỉ OSD đã reshard mang layout mới. Snapshot/checksum trước tool là rollback boundary; hạ package không đảo reshard, phải restore clone nếu reopen/fsck thất bại.

**Kiểm chứng:** trước khi reshard, ghi nhận sharding hiện tại bằng tool trên bản sao store; xác định prefix đúng với dữ liệu của OSD, thử lệnh trên clone và mở lại OSD; không áp dụng mù ví dụ tài liệu. Với SPDK, đối chiếu đúng cú pháp device được artifact target chấp nhận.

### CFG-007 — Hướng dẫn kiểm soát mClock trong giai đoạn ổn định

**CSV:** `doc/rados/configuration/mclock-config-ref.rst`. Target bổ sung quy trình đổi giữa built-in/custom profile, gỡ các giá trị custom khỏi MON config DB khi quay lại built-in, phân biệt override tạm qua `ceph tell`/`ceph daemon` với giá trị sống qua restart, và gate `osd_mclock_override_recovery_settings` cho `osd_max_backfills`/recovery limits. Cụm commit `86a255a049b`, `41c903a4bf2` nêu profile và reset ephemeral changes. Vì CFG-001 đổi default sang mClock, hướng dẫn này có thể quyết định cách xử lý canary bị chậm recovery. **Điều kiện:** rollout áp dụng mClock và operator định chỉnh QoS/recovery. **Evidence confidence:** high cho recipe, medium cho kết quả nếu chưa đo workload.

**Tác động:** impact nằm ở latency/recovery availability và tính bền vững của config: override tạm mất sau restart còn MON config tiếp tục áp dụng cho cohort khác. Vì vậy mọi thử nghiệm phải ghi rõ scope/lifetime và có giá trị trước đó để hoàn nguyên, không coi command accepted là thay đổi đã có hiệu lực.

**Kiểm chứng:** trên canary đối chiếu `ceph config dump` với `ceph config show osd.N` trước/sau restart; thử chuyển profile và override trong lab, xác nhận limits hiệu dụng và thời gian recovery. Không coi `config set` thành công là bằng chứng limit mClock đã đổi.

### CFG-008 — Option FastCGI RGW biến mất

**CSV:** `src/common/options/rgw.yaml.in`. Base `options.cc` định nghĩa `rgw_host`, `rgw_port`, `rgw_socket_path`, `rgw_fcgi_socket_backlog`; `src/rgw/rgw_fcgi_process.cc` đọc các option này. Target không còn các định nghĩa trong YAML và xóa đường FastCGI: bảy hàng source/frontend/request/process ở [owner 12](./12-rgw.md) và CMake option, finder, source/link ở [owner 13](./13-build-packaging-submodules.md) được đối chiếu cùng finding. **Điều kiện:** chỉ deployment dùng RGW FastCGI hoặc còn cấu hình các khóa đó; RGW dùng frontend khác không bị suy ra ảnh hưởng. Sau thay binary, đường khởi động/listener cũ không còn trong source target. Mặc định `rgw_frontends` ở cả hai endpoint là `beast port=7480`, nên phải đọc cấu hình thực tế trước khi xác định áp dụng. **Evidence confidence:** high cho source/build removal, applicability chưa biết.

**Kiểm chứng:** inventory `rgw_frontends`, `rgw_host/port/socket_path`, packaging và reverse proxy từng RGW; trong lab start đúng target artifact với cấu hình hiện có, kiểm listener/health endpoint và client request trước khi rollout RGW.

Cùng hàng `src/common/options/rgw.yaml.in` còn thêm tùy chọn SSE-S3 Vault và mẫu tên key theo bucket, liên quan [RGW-002](./12-rgw.md). Option `rgw_data_notify_interval_msec` vẫn mặc định 200 nhưng mô tả mới nêu 0 sẽ tắt thông báo multisite; mã RGW đổi tương ứng trong [RGW-003](./12-rgw.md). Đây là các hunk ảnh hưởng khác trong file đã gắn `affect` cho CFG-008.

**Tác động:** impact là RGW startup/listener availability và compatibility với reverse proxy/client; nếu còn FastCGI, target không có đường code để phục vụ cấu hình cũ. Việc chuyển frontend là change riêng cần bind/health/request validation, không chỉ xóa option rồi restart.

### CFG-009 — MDS lưu thêm symlink target để phục hồi

**CSV:** `src/common/options/mds.yaml.in`. Target thêm `mds_symlink_recovery=true`; `MDCache.cc` đọc option và `CInode.cc` dùng `get_symlink_recovery()` trong đường symlink. Base không có option/caller này. **Điều kiện:** CephFS có symlink mới/được ghi sau khi MDS target chạy; đổi option hoặc rollback có thể làm dữ liệu bổ sung khác nhau giữa MDS cũ/mới. Chưa suy rằng wire/on-disk compatibility hỏng; cần kiểm reader cũ và journal replay riêng ở owner 11. **Evidence confidence:** high cho default/caller, medium cho tác động rollback.

**Mixed/full:** active MDS version quyết định metadata bổ sung khi symlink được ghi; standby/base reader trong rolling phase phải được kiểm replay, còn full target đồng nhất writer. Không coi option mới là one-way gate nếu chưa chạy target→base→target trên bản sao; đóng rollback theo test owner 11.

**Kiểm chứng:** lab tạo symlink trước/sau nâng MDS, failover/replay rồi kiểm `readlink` và recovery tool; thử downgrade trên bản sao khi quy trình cho phép. Thu effective `mds_symlink_recovery`.

### CFG-010 — MGR mở đường dùng pool `.mgr`

**CSV:** `src/common/options/mgr.yaml.in`. Target thêm `mgr_pool=true`; `mgr_module.py` kiểm giá trị trước `open_db()` và tạo `.mgr` pool. Đây là một điều kiện của [MGR-001](./07-mgr-modules-monitoring.md) về pool/SQLite. **Điều kiện:** module MGR dùng persistent DB hoặc có override `mgr_pool=false`; trong mixed-version cần xét daemon MGR active đang chạy bản nào. **Evidence confidence:** high cho gate, applicability chưa biết.

**Tác động:** impact là availability/correctness của module DB và việc tạo pool persistent mới. Package failback không xóa `.mgr` pool hoặc import state; rollback phải theo MGR-001 và không remove pool chỉ vì base không dùng cùng đường mặc định.

**Kiểm chứng:** thu config và pool list trước rollout, thử active MGR switch/canary, xác nhận `.mgr` pool, mở DB và import legacy OMAP theo MGR-001; kiểm rollback trên lab nếu cần.

### CFG-011 — MON cảnh báo FileStore OSD

**CSV:** `src/common/options/mon.yaml.in`. Target thêm `mon_warn_on_filestore_osds=true`; `OSDMonitor::check_for_filestore_osds()` phát `OSD_FILESTORE` với `HEALTH_WARN` nếu còn OSD FileStore. **Điều kiện:** cluster còn FileStore; một cảnh báo mới sau MON restart có thể đổi tiêu chí dừng rollout dù trạng thái OSD chưa đổi. **Evidence confidence:** high cho code/health key, applicability chưa biết.

**Tác động và rollback:** impact là observability/decision gate, không phải data mutation. Hạ MON hoặc tắt config có thể bỏ warning nhưng không migrate FileStore và có thể che technical debt; lưu baseline và chỉ suppress bằng policy explicit. Package rollback không biến backend cũ thành an toàn.

**Kiểm chứng:** inventory OSD backend trước nâng MON, chụp `ceph health detail` trước/sau canary và phân biệt cảnh báo mới với hỏng hóc mới; đưa FileStore vào tiêu chí chấp nhận rõ ràng.

### CFG-012 — Config SeaStore/Crimson mới

**CSV:** `src/common/options/crimson.yaml.in`. Target thêm các option cho segment size, device size/create, journal batching và cache; `crimson/os/seastore/segment_manager/block.cc` và `zns.cc` đọc `seastore_segment_size`. **Điều kiện:** chỉ khi triển khai Crimson/SeaStore hoặc custom build dùng backend này; không suy áp dụng cho OSD BlueStore thường. Các default mới có thể thay kích thước thiết bị giả lập, memory và replay/activation trong thử nghiệm upgrade. **Evidence confidence:** high cho schema/caller, applicability chưa biết.

**Mixed/full và rollback:** BlueStore cohort không bị ảnh hưởng; với Crimson/SeaStore, từng target daemon dùng schema mới và full rollout mới đồng nhất default. Device/create/segment choices có thể ghi layout persistent, nên hạ binary không hoàn tác; snapshot/disposable device trước activation là boundary và rollback phải restore image, không chỉ đổi option.

**Kiểm chứng:** xác nhận backend từng OSD; nếu có Crimson/SeaStore, chạy lab trên artifact target với config/thiết bị tương ứng, thử restart, journal replay, capacity và cache; nếu không dùng, ghi rõ không áp dụng.

### CFG-013 — Endpoint ceph-exporter mới cho validation

**CSV:** `src/common/options/ceph-exporter.yaml.in`. Target thêm sáu option; `ceph_exporter.cc` và `http_server.cc` dùng `exporter_http_port` (default `9926`), socket directory, priority limit và polling period. **Điều kiện:** rollout hoặc hệ thống giám sát triển khai `ceph-exporter`; đây là một đường metrics mới, không chứng minh rằng metrics cũ sẽ biến mất. **Evidence confidence:** high cho schema/caller, applicability chưa biết.

**Activation, impact và rollback:** exporter chỉ kích hoạt explicit khi service được deploy/start; daemon Ceph upgrade không tự mở port. Impact là observability và host network exposure. Package/service failback có thể đóng endpoint nhưng không lấp telemetry gap; lưu firewall/service spec trước deploy và rollback bằng remove/apply spec có kiểm soát, không để orphan listener.

**Kiểm chứng:** nếu dùng exporter, kiểm port/firewall, scrape, counter set và quyền đọc daemon socket trên đúng target artifact; đối chiếu tín hiệu stop/go với baseline hiện tại.

### CFG-014 — Mặc định bật allocation file của BlueStore

**CSV:** `src/common/options/global.yaml.in` (cùng hàng với CFG-002/003/004). Target thêm `bluestore_allocation_from_file=true`; base không có option này. `BlueStore::_open_db_and_around()` chỉ chuyển sang null freelist manager khi DB không rotational, store mở read-write, không ở repair mode và option bật. Khi đã dùng null manager, `_init_alloc()` cần option bật để restore allocator. Đây là default kích hoạt đường [BLU-001](./02-bluestore-bluefs.md), không suy rằng mọi OSD chuyển representation ngay cùng một lúc. Commit `272160ab5e4` thêm đường allocation-file. **Evidence confidence:** high cho default/code, applicability cần As-Is device/config.

**Kiểm chứng:** inventory DB device, FM type và effective config từng OSD; lab clean/unclean restart trên bản sao trước khi quyết định rollout/rollback. Không tắt option trên store đã chuyển null FM nếu chưa xác minh recovery path.

**Tác động và ranh giới:** persistent compatibility, activation/recovery duration và rollback đổi tự động khi store target đủ điều kiện mở read-write. Guard `HAVE_LIBZBD` còn loại SMR khỏi conversion; full version string không thay inventory media/FM. Giữ checkpoint nhất quán block+DB+WAL trước mở target; khi đã ghi null FM, tắt option hoặc hạ binary không khôi phục bitmap. Chưa có clone/fault result, đối chiếu BLU-001 trước cho phép failback.

## Trivial changes

**26 hàng.** Các cụm đã sàng lọc gồm trang tài liệu chỉ chuyển bảng option sang `confval`, sửa URL/heading/prose và mẫu không được triển khai; `ConfigProxy`/`config.h` đổi cú pháp C++ không đổi giá trị; YAML cho cephfs-mirror, immutable-object-cache, mds-client, rbd-mirror giữ option/default tương ứng ở hai endpoint; RBD thêm `rbd_qos_exclude_ops` không có default kích hoạt và cần cấu hình chủ động. Lý do theo từng hàng nằm trong CSV. Hai recipe tài liệu có khả năng đổi thao tác được giữ ở CFG-006/007.

## Hàng chờ so sánh default

[`config-default-candidates.tsv`](./config-default-candidates.tsv) là **hàng chờ đối soát**, được tạo bằng [`tools/audit_config_defaults.py`](./tools/audit_config_defaults.py). Script trích 1.744 option Pacific C++ và 1.813 option Quincy YAML, chuẩn hóa một số literal đơn giản rồi liệt kê khác biệt còn lại. File chứa cả false positive do macro, string rỗng, biểu thức C++, biến CMake và chuyển vị trí định nghĩa. Nó hỗ trợ review từng YAML row nhưng không thay thế hunk/caller review, không phải danh sách tác động đã xác minh.

## Kiểm chứng cần hoàn thành

- Đối soát `20 + 26 = 46` bằng validator và giữ các finding điều kiện tách khỏi kết luận áp dụng cho cluster thật.
- Thu config hiệu dụng, backend, build artifact và thử lab/canary; kiểm riêng rollback MDS/RGW và recipe reshard trước khi dùng để quyết định rollout.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
