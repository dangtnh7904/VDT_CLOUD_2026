# 06 — option, default và schema cấu hình: v17.2.7 → v18.2.7

**Binary gate owner 06 đã hoàn tất; applicability và lab còn mở.** [CSV đầy đủ của owner](./06-config-defaults.csv) có 29 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 10`, `trivial = 19`, chưa phân loại = 0. Finding dưới đây chỉ lấy từ hàng `affect`.

## Phạm vi và bằng chứng

Owner này bao phủ config observer, option schema và default dùng chung. Net diff được đọc trực tiếp giữa base `b12291d110049b2f35e32e0de30d70e9a4c060d2` và target `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`; caller và test được đối chiếu ở cả hai endpoint. Repo shallow và hai tag non-ancestor nên commit-range intent không đầy đủ; `PendingReleaseNotes` trong target chỉ được dùng khi khớp với endpoint code. Priority trong CSV là thứ tự đọc, không phải risk.

## Finding ảnh hưởng upgrade

### CFG-001 — Config observer đổi contract khóa và vòng đời callback

**CSV:** `src/common/config_obs_mgr.h`, `src/common/config_proxy.h`; `config_cacher.h` là supporting trivial row. Quincy giữ raw observer pointer, `recursive_mutex` và một `CallGate` riêng; `remove_observer()` chờ gate trong khi giữ config lock. Reef gom callback dưới lock nhưng gọi chúng ngoài lock, giữ observer bằng shared lifetime token, rồi để removal chờ weak token hết hạn qua condition variable; các getter/schema access cũng được khóa rõ ràng hơn.

**Điều kiện và tác động:** áp dụng cho mọi daemon/client có config observer khi monitor config, `injectargs`, meta expansion hoặc shutdown diễn ra đồng thời. Mỗi process chỉ dùng contract của binary hiện tại, nên mixed-version không đổi wire format nhưng old/new daemon có failure mode teardown/reload khác nhau. Rủi ro vận hành ở mức trung bình trong path đồng thời; confidence high cho endpoint concurrency contract, nhưng không có commit history hay dedicated regression test trong clone.

**Kiểm chứng:** stress thay runtime option có observer trong lúc restart/shutdown và unregister; yêu cầu không deadlock, không use-after-free, callback nhận đúng key, process thoát đúng timeout. Repository tests được đọc nhưng chưa chạy; `src/test/common/test_config.cc` và `src/test/daemon_config.cc` bao phủ config cơ bản, chưa trực tiếp đóng race này.

### CFG-002 — CephFS mirror có bộ perf counter mới với priority mặc định 5

**CSV:** `src/common/options/cephfs-mirror.yaml.in`. Reef thêm `cephfs_mirror_perf_stats_prio=5`; `FSMirror`, `Mirror` và `PeerReplayer` dùng key này khi đăng ký counter cho filesystem/peer, số snapshot, bytes, latency và failure. Quincy không có cụm counter tương ứng.

**Điều kiện và tác động:** chỉ áp dụng khi triển khai CephFS snapshot mirroring và pipeline thu counter theo `mgr_stats_threshold`. Sau restart target, monitoring có thêm signal; trong mixed cohort, mirror daemon cũ không xuất cùng schema. Đây là đổi observability, không chứng minh tốc độ mirror thay đổi. Risk thấp đến trung bình tùy stop/go có dựa vào mirror metrics hay không; confidence high cho code, applicability chưa biết.

**Kiểm chứng:** inventory mirror daemon và threshold; so `perf dump`/service telemetry trước-sau, xác minh counter tăng khi sync thành công/thất bại và parser không coi counter thiếu ở old daemon là lỗi.

### CFG-003 — Crimson/SeaStore nhận default tạo device và concurrency mới

**CSV:** `src/common/options/crimson.yaml.in`. Reef đổi `seastore_device_size` từ `100_G` xuống `50_G`, thêm `crimson_seastar_smp=1` ở startup, `seastore_max_concurrent_transactions=8`, device type, circular journal và tier-eviction controls. Target caller đọc device size khi `seastore_block_create` tạo backing file, đọc SMP trong bootstrap và dùng concurrency/tiering trong SeaStore.

**Điều kiện và tác động:** chỉ áp dụng cho artifact/OSD Crimson hoặc SeaStore, vốn vẫn là nhánh điều kiện/experimental trong phạm vi này. Existing physical device không tự co từ 100 GiB xuống 50 GiB; create/recreate fixture và process restart có thể nhận layout/concurrency khác. Không suy performance improvement hoặc on-disk compatibility chỉ từ option diff. Risk cao nếu deployment thật dùng SeaStore, không áp dụng với BlueStore thường; confidence high cho code, applicability unknown.

**Kiểm chứng:** xác định artifact flags, objectstore và `seastore_block_create`; nếu dùng, pin explicit size/SMP, thử create-open-restart-replay với đúng shard count và kiểm superblock/segment metadata trước rollout.

### CFG-004 — Default BlueStore/RocksDB, discard và device-health đổi khi OSD target khởi động

**CSV:** `src/common/options/global.yaml.in`; runtime tương ứng được phân tích thêm tại `KV-002`, `KV-003`, `KV-004`, `KV-008` và `KV-009` trong [owner 03](./03-rocksdb-block-device.md). Reef thay `bdev_async_discard` bằng `bdev_async_discard_threads=0`, thêm stalled-read/slow-op health thresholds và async DB compaction. `bluestore_rocksdb_options` đổi từ no-compression/ít write buffer sang LZ4, 64 write buffers, 16 MiB buffer và level-compaction settings; BlueStore đọc string này khi mở DB. `bluestore_rocksdb_cfs` cũng đổi nhưng chỉ dùng khi mkfs/reshard, không tự rewrite OSD hiện hữu.

**Điều kiện và tác động:** OSD không có explicit override nhận target RocksDB behavior sau restart; cluster từng bật discard bằng hai boolean cũ cần map chủ đích sang worker count. Health warning mới có thể đổi stop/go mà không có hardware change. Trong mixed phase, OSD old/new có compaction, discard và signal khác nhau nhưng chưa có bằng chứng wire/on-disk incompatibility. Risk trung bình-cao với OSD có custom RocksDB/discard policy; confidence high cho default/caller, performance outcome chưa đo.

**Kiểm chứng:** snapshot stored/effective keys, config assimilated từ legacy file và artifact source; trên clone/canary đo DB open/replay, compaction, memory/write amplification, discard latency và health alert lifetime. Không chạy reshard hoặc bật discard lần đầu như một phần mặc định của binary rollout.

### CFG-005 — OSD compression method và requested-scrub priority đổi default

**CSV:** cùng hàng `src/common/options/global.yaml.in`. `ms_osd_compression_algorithm` đổi từ danh sách `snappy zlib zstd lz4` thành `snappy`; `CompressorRegistry::_refresh_config()` parse danh sách này để chọn allowed methods. `osd_requested_scrub_priority` đổi từ `120` xuống `5` và được `PGScrubber` dùng cho scrub được yêu cầu thủ công.

**Điều kiện và tác động:** compression chỉ có hiệu lực khi mode/size/security cho phép; target mặc định không còn fallback sang ba thuật toán sau trong danh sách, nên negotiation ở mixed-version cần được quan sát nếu compression đang bật. Manual scrub trên target dùng priority thấp hơn theo thang hiện hành, có thể đổi thời lượng maintenance/acceptance. Risk trung bình khi dùng messenger compression hoặc manual scrub làm gate; confidence high cho schema/caller, workload impact unknown.

**Kiểm chứng:** lấy effective `ms_osd_compress_*` và scrub priority; thử old↔new OSD connection với từng peer capability, kiểm negotiated algorithm/fallback, rồi đo manual scrub completion và client latency với đúng scheduler/profile.

### CFG-006 — `client_dirsize_rbytes` trở thành startup-only

**CSV:** `src/common/options/mds-client.yaml.in`. Giá trị mặc định vẫn `true`, nhưng Reef thêm flag `startup`; `Option::can_update_at_runtime()` vì vậy trả false. CephFS client tiếp tục dùng key này trong `Client.cc` để chọn recursive bytes cho directory `st_size`.

**Điều kiện và tác động:** chỉ quan trọng nếu central config/launcher thay key trong maintenance window hoặc các client được nâng/restart không đồng thời. Client Quincy có thể nhận thay đổi live trong khi client Reef chỉ nhận khi khởi động, làm semantics `stat` khác nhau giữa cohort. Không có protocol change khi key giữ nguyên. Risk thấp-trung bình và conditional; confidence high cho schema/caller.

**Kiểm chứng:** inventory client type/version và override; thử config change với client old/new đang mount, xác minh reported directory size trước/sau client restart và không dùng live toggle làm rollback giả định.

### CFG-007 — Giới hạn xattr CephFS chuyển từ per-MDS config sang MDSMap

**CSV:** `src/common/options/mds.yaml.in`. Reef xóa `mds_max_xattr_pairs_size`; `Server.cc` và `Locker.cc` đọc `MDSMap::get_max_xattr_size()` mặc định 64 KiB, còn `FSCommands.cc` cho phép đặt `fs set ... max_xattr_size`. Target `PendingReleaseNotes` xác nhận MDSMap field này thay thế setting per-MDS cũ. Reef còn thêm `mds_dir_prefetch=true` và `defer_client_eviction_on_laggy_osds=false`; các default đó giữ gần hành vi cũ nhưng mở control mới.

**Điều kiện và tác động:** cluster có override `mds_max_xattr_pairs_size` khác 64 KiB phải chuyển giá trị sang từng filesystem trước khi target rank active. Trong rolling upgrade/failover, MDS Quincy dùng local config còn MDS Reef dùng MDSMap; nếu hai giá trị lệch, setxattr/readdir/lssnap acceptance có thể đổi theo rank. Risk cao khi có override hoặc xattr lớn, thấp nếu As-Is chứng minh mặc định; confidence high.

**Kiểm chứng:** lưu stored/effective old key và `ceph fs get`/MDSMap cho từng filesystem; thử xattr ngay dưới/trên boundary qua old rank, target standby-replay promotion và failback. Việc viết MDSMap production cần MOP riêng, báo cáo này không cấp quyền thực hiện.

### CFG-008 — Hai key log-level MON được hợp nhất thành một key

**CSV:** `src/common/options/mon.yaml.in`. Reef bỏ `mon_cluster_log_file_level` (default debug) và `mon_cluster_log_to_syslog_level` (default info), thêm runtime `mon_cluster_log_level=debug`. `LogMonitor` target đọc và observe key mới cho file lẫn external entity; `PendingReleaseNotes` nêu migration này.

**Điều kiện và tác động:** cluster có override hai key cũ hoặc parser/alert dựa vào độ chi tiết syslog. Target MON bỏ tác dụng override cũ và dùng một mức chung, nên log volume và stop/go signal có thể đổi sau từng MON restart; quorum/wire behavior không được suy là đổi. Risk trung bình với logging pipeline, confidence high.

**Kiểm chứng:** inventory central config và ceph.conf cho cả ba key; trên canary MON kiểm cluster log file, syslog/external sink ở mức debug/info/warn bằng `qa/standalone/mon/mon-cluster-log.sh` tương ứng. Chưa chạy test.

### CFG-009 — HDD mClock và scrub dùng default target khác ngay sau OSD restart

**CSV:** `src/common/options/osd.yaml.in`; hai trang tài liệu mClock/OSD là supporting trivial rows. Reef đổi `osd_op_num_shards_hdd 5→1`, `osd_op_num_threads_per_shard_hdd 1→5`; target release note giải thích mục tiêu là ổn định client/recovery throughput với mClock. Đồng thời `osd_max_scrubs 1→3`, deep-scrub chunk max `25→15`, thêm shallow-scrub chunk, reservation timeout và low-IOPS capacity threshold.

**Điều kiện và tác động:** default shard/thread áp dụng cho HDD OSD không override sau process restart; scrub defaults áp dụng khi không pin giá trị. Mixed cohort có queue topology và concurrent scrub khác nhau, có thể đổi latency, recovery/stabilization time và gate deep-scrub. Không tuyên bố nhanh hơn trên topology hiện tại nếu chưa benchmark. Risk trung bình-cao trong maintenance window; confidence high cho code/release evidence, applicability và capacity chưa biết.

**Kiểm chứng:** phân loại media/scheduler, lấy effective override từng OSD; benchmark client+recovery trên HDD canary với 1×5 so 5×1, theo dõi slow requests/fairness. Chạy scrub scenario với 1 và 3 concurrent sessions, deep/shallow chunk, reservation timeout, completion time và client tail latency. Repository scrub/mClock tests đã được xác định nhưng chưa chạy.

### CFG-010 — RGW đổi nơi ghi ops log và tắt data-change notification mặc định

**CSV:** `src/common/options/rgw.yaml.in`. Reef đổi `rgw_ops_log_rados true→false`, thêm daemon default `/var/log/ceph/ops-log-$cluster-$name.log`; release note xác nhận backend mặc định chuyển từ RADOS sang file. `rgw_data_notify_interval_msec 200→0`; target `RGWDataChangesLog::mark_modified()` return ngay khi giá trị bằng 0. `rgw_ldap_uri` bỏ placeholder thành empty và policy parser thêm default reject invalid principals cho policy mới.

**Điều kiện và tác động:** chỉ ops logging khi `rgw_enable_ops_log` bật; filesystem logging cần writable path/rotation và consumer mới. Multisite vẫn có polling, nhưng notification ưu tiên recent changes bị tắt mặc định nên convergence/observability cần đo. LDAP chỉ kích hoạt khi auth LDAP được cấu hình; policy strictness áp dụng policy mới, không rewrite policy cũ. Mixed RGW có log sink/notification/policy acceptance khác nhau. Risk trung bình-cao với RGW/multisite/audit; confidence high cho defaults/caller, environment delivery chưa biết.

**Kiểm chứng:** inventory RGW roles, ops-log consumers, path/rotation/SELinux, multisite và LDAP/policy overrides; canary kiểm log sink, disk growth, sync lag/poll recovery và positive/negative policy/LDAP cases trên cả old/new endpoint.

## Operational closure addenda

#### CFG-001 — Closure

Rollback config-observer canary bằng drain/restart old binary với stored config unchanged; callback đã thực thi không có generic inverse nên phải verify component state. Mixed/full lab cần concurrent config update/start-stop, deadlock/race detection và effective-value snapshots.

#### CFG-002 — Closure

Rollback bằng dual-schema dashboard/collector hoặc restore old mirror daemon after queue drain; counter history không rewrite. Mixed/full phải tag metrics theo daemon version và validate labels/priority/cardinality before alerts.

#### CFG-003 — Closure

Crimson/SeaStore defaults tự động có hiệu lực khi unset ở startup. Rollback chỉ bằng explicit pin old values plus restart on cloned store; target-created device/state may be irreversible for Quincy. Applicability cần build/runtime inventory and format rehearsal.

#### CFG-004 — Closure

Defaults tự động activate at OSD restart; rollback requires explicit baseline values, drain, old artifact and store/checksum validation. Discard/DB/health behavior already exercised cannot be undone by changing config alone. Mixed/full canary must capture effective config and device state.

#### CFG-005 — Closure

Compression/scrub defaults tự động áp dụng khi key unset; enabling/forcing operations remains explicit. Rollback by pinning Quincy values and restarting/draining before new writes/scrubs; compressed objects or repair side effects need data copy/manifest, not config inverse.

#### CFG-006 — Closure

Chưa có client/override inventory. Since Reef treats the key startup-only, rollback semantics are restart with prior value; live toggle cannot restore a running target client. Mixed/full validation must distinguish process state from central config and record directory-size output around restart.

#### CFG-008 — Closure

Rollback bằng explicit target key/old-key baseline, quorum-safe restart and collector routing; log messages omitted during wrong level cannot be recovered. Mixed/full validate every sink, volume and parser before accepting monitoring gate.

#### CFG-009 — Closure

Rollback by pinning old shard/thread/scrub values and restarting one drained OSD at a time; in-flight scrub must finish/cancel safely before failback. Mixed/full benchmark must retain effective config, client tail latency, recovery and scrub completion evidence.

## Trivial changes

**19 hàng.** Mười sáu file documentation đã được đọc đầy đủ; chúng sửa prose, ví dụ, cảnh báo Filestore, port-range và giải thích mClock nhưng không tự thay đổi binary hay executable acceptance path. `config_cacher.h` là support cho CFG-001 nhưng exact tree không có hai cacher cùng template type để tạo key collision. `options.h` thêm helper chưa có caller ở endpoint; `rbd.yaml.in` đổi validator tương đương và mức hiển thị option. Toàn bộ enumeration và lý do nằm trong CSV.

## Validation và giới hạn

Chưa chạy build, repository test, lab hay cluster command. Gate trước rollout ưu tiên: migrate CephFS xattr override, MON log keys, RGW log/multisite defaults, OSD HDD mClock/scrub defaults, BlueStore/RocksDB/discard và config-observer stress. Crimson, CephFS mirror metrics, messenger compression và client live-config chỉ chạy khi As-Is xác nhận áp dụng. Source review này không tự tạo GO/NO-GO và không cấp quyền sửa config production.

