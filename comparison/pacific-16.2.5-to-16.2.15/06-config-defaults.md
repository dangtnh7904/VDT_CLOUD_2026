# 06 — Cấu hình, default và schema: v16.2.5 → v16.2.15

> **Kết quả:** CSV giữ đủ 20 dòng do `06-config-defaults` sở hữu. Báo cáo chỉ đào sâu những thay đổi cấu hình có thể làm khác hành vi khi daemon khởi động lại, làm một override cũ mất hiệu lực, hoặc thay đổi cách kiểm tra cấu hình trong quá trình nâng cấp. Các chỉnh sửa tài liệu thuần biên tập được giữ trong CSV nhưng chỉ kết luận `trivial/support`.
>
> **Trạng thái kiểm chứng:** đã đối chiếu net diff hai endpoint, code sử dụng option, lịch sử commit và tài liệu trong repository; chưa build, chưa chạy test và chưa thay đổi cấu hình/cluster.

## 1. Phạm vi, nguồn và nguyên tắc đọc

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Repository: `ceph16.2.15/ceph`; base là ancestor của target, working tree nguồn sạch và repository không shallow.
- Inventory chi tiết: [06-config-defaults.csv](./06-config-defaults.csv), đúng 21 cột nền và đúng thứ tự master inventory.
- Owner set: 20 dòng, đều `M`, tổng `+1481/-998`; 5 dòng `P1/deep`, 15 dòng `P2/reference-only`.

Các inventory index `159`–`173`, `1225`–`1227`, `1235`, `1236` được sàng lọc. Một option mới có default `false` không tự động trở thành rủi ro upgrade; ngược lại, một rename/remove chỉ một dòng vẫn được giữ nếu có thể làm override hiện hữu bị bỏ qua sau restart.

Phần lớn hành vi runtime nằm ở owner report khác. Báo cáo này dùng các caller đó làm bằng chứng ngữ cảnh nhưng không đưa file của chúng vào CSV, nổi bật là `src/osd/OSD.cc`, `src/os/bluestore/*`, `src/kv/RocksDBStore.cc`, MDS/client, RGW và RBD mirror.

## 2. Kết luận nhanh cho kế hoạch nâng cấp

1. **Cần audit cấu hình trước rolling restart:** tìm ít nhất sáu key cũ `osd_mclock_max_capacity_iops`, `mds_max_retries_on_remount_failure`, `ms_async_max_op_threads`, `rgw_rados_pool_pg_num_min`, `rgw_bucket_quota_soft_threshold` và `rbd_persistent_cache_log_periodic_stats`. Ở target, các key này bị remove/rename hoặc không còn consumer cũ.
2. **OSD target có default mới ngay khi restart:** giới hạn số client request đang bay là `256`, monitor notification khi fast shutdown được bật, payload RETURNVEC tối đa mỗi op tăng `32` → `64` byte và aggregated slow-op cluster logging mặc định bật. Không có bằng chứng về migration on-disk, nhưng mixed phase có thể cho hành vi và áp lực log khác nhau giữa OSD cũ và mới.
3. **mClock cần chú ý đặc biệt:** generic capacity key bị bỏ; target chọn key HDD/SSD và có thể chạy benchmark khi OSD khởi động nếu dùng `mclock_scheduler`. Đây là thay đổi có thể kéo dài/tăng I/O ở restart dù chỉ áp dụng cho cluster bật mClock.
4. **CephFS, RGW và RBD có default/rename đáng kiểm tra theo dịch vụ:** MDS đổi throttle/prefetch, thêm grace/eviction/session guards; RGW tăng retry, tách Vault TLS verification và bỏ quota threshold; RBD mirror tăng giới hạn snapshot. Chúng không ảnh hưởng cluster không dùng các dịch vụ/đường code đó.
5. **Các option storage mới chủ yếu opt-in hoặc thuộc report 02/03:** iterator bounds mặc định bật là ngoại lệ đáng test; compact-on-deletion mặc định tắt. Không suy diễn thay đổi format từ riêng schema option.

## 3. Ma trận finding

| ID | Chủ đề | Khi nào kích hoạt | Pha đáng chú ý | Mức rủi ro | Confidence |
|---|---|---|---|---|---|
| CFG-001 | Default OSD và slow-op logging đổi sau restart | OSD dùng default, không override | mixed/full | Trung bình | High |
| CFG-002 | Di trú cấu hình mClock và benchmark lúc boot | `osd_op_queue=mclock_scheduler` | restart/mixed | Trung bình-cao theo điều kiện | High |
| CFG-003 | CephFS/MDS grace, eviction, session, type và rename | Có CephFS client/MDS liên quan | mixed/full | Trung bình-cao theo điều kiện | High |
| CFG-004 | RGW Vault TLS, retry/quota và RBD defaults | Có RGW Vault/cache/quota/pool-create hoặc RBD mirror | mixed/full | Cao với Vault self-signed; trung bình ở nhánh khác | High |
| CFG-005 | Storage/KV option mới | BlueStore/RocksDB đi qua đường tương ứng | restart/stabilization | Trung bình-thấp | High |
| CFG-006 | Pool/autoscaler/monitor controls | Tạo pool hoặc autoscaler thay đổi PG | mixed/full | Trung bình theo điều kiện | High |
| CFG-007 | Validation/type và các key runtime cũ | Có override bất hợp lệ/cũ | preflight/restart | Thấp-trung bình | Medium-high |

Mức rủi ro là mức ảnh hưởng **nếu điều kiện kích hoạt đúng**, không phải xác suất cluster hiện tại gặp vấn đề. Confidence chỉ phản ánh độ chắc của bằng chứng code/commit.

## 4. Phát hiện chi tiết

### CFG-001 — Default OSD và cluster logging đổi ngay sau khi binary target khởi động

**Evidence.** Inventory `1235`–`1236`, `src/common/legacy_config_opts.h` và `src/common/options.cc`:

- `6ce3062a28c2c08592cd182f5cc3f3025a8eba88`: `osd_client_message_cap` đổi `0` → `256`; target mô tả đây là số client request in-flight tối đa.
- `e3bf1a787f600e2cc46568fd025c799e2ec2c7a4`: `osd_fast_shutdown_notify_mon` đổi `false` → `true`; target báo monitor khi immediate shutdown.
- `2613f639794af8475e76f3ba2e16eb93a7e1068c`: `osd_max_write_op_reply_len` đổi `32` → `64`; option giới hạn payload RETURNVEC mỗi op được gửi lại client và ghi vào PG log.
- `7a453da2600dd36c730187ad6803563001843ef7`: thêm minimum `1` cho `osd_pg_max_concurrent_snap_trims`.
- `a1156c922a470f05052fe63236eb82324d57b54e`: thêm `osd_aggregated_slow_ops_logging=true`; OSD target gửi chi tiết slow op đã aggregate vào cluster log.

**Trước → sau và ảnh hưởng upgrade.** Nếu không có override, từng OSD nhận giá trị mới khi restart sang target. Trong rolling phase, request được phục vụ bởi acting primary cũ hoặc mới có thể gặp giới hạn request/reply khác nhau; fast-shutdown notification cũng chỉ có ở OSD đã nâng cấp. Đây là thay đổi runtime/local, không phải thay đổi OSDMap hay format PG log được chứng minh bởi owner set này.

Giới hạn `256` có thể làm OSD target backpressure sớm hơn cluster base dùng `0`; ngược lại nó chặn lượng request đang bay tăng không giới hạn theo count. Reply cap lớn hơn cho phép thêm dữ liệu RETURNVEC, nhưng không bảo đảm client workload thực tế dùng flag đó. Notification mặc định mới chủ yếu làm monitor nhận trạng thái shutdown rõ hơn trong vòng restart và giảm báo cáo lỗi kết nối gây nhiễu. Aggregated slow-op logging thay nhiều entry chi tiết bằng bản tổng hợp, nhờ đó giảm cluster-log/MON DB pressure khi có nhiều slow op; đổi lại parser/runbook không nên chờ từng dòng per-op như base.

**Hành động.** Trước canary, ghi lại effective values từ config database/daemon, đặc biệt nếu cluster từng tune client cap hoặc reply cap. Theo dõi client latency/backpressure, OSD memory, PG log, cluster-log rate/MON DB và thời gian monitor đánh dấu OSD trong mỗi restart. Không cần migrate dữ liệu từ riêng các default này.

**Đánh giá.** `P1`; rủi ro **trung bình**, confidence **high**. Chưa biết override và profile workload của cluster.

### CFG-002 — mClock bỏ key capacity chung và có thể benchmark thiết bị lúc OSD boot

**Evidence.** Inventory `1225`–`1227`, `1235`–`1236`; caller target `OSD::maybe_override_max_osd_capacity_for_qos()` trong `src/osd/OSD.cc`:

- `e36fb7f3c8f85f1c751adcba196d97d407581e39` bỏ `osd_mclock_max_capacity_iops`.
- Target dùng `osd_mclock_max_capacity_iops_hdd` hoặc `_ssd` tùy thiết bị.
- `12b6d42770032b6c53737368cad2f0427c56c1ed` thêm `md_config_t::get_val_default()` và proxy; caller so effective capacity với default để quyết định có cần benchmark.
- `b48d709d30d8514d9bc9242772f4b56f6bc3534e` thêm `osd_mclock_force_run_benchmark_on_init=false`; `69d3d5903550a4b30d341dfb3fbd39396df56763` thêm `osd_mclock_skip_benchmark=false`.

**Activation.** Code chỉ đi vào nhánh này khi `osd_op_queue == "mclock_scheduler"` và `osd_mclock_skip_benchmark == false`. Nếu capacity hiện tại vẫn bằng default, hoặc `force_run_benchmark_on_init=true`, OSD chạy benchmark lúc boot rồi ghi IOPS vào MON config store. Nếu operator đã đặt giá trị HDD/SSD khác default, code bỏ benchmark.

**Tác động.** Override cũ cho generic key không còn điều khiển capacity target; để nguyên key cũ có thể tạo cảm giác đã tune nhưng thực tế OSD dùng key theo media. Benchmark boot có I/O và kéo dài startup, nên có thể cộng hưởng với recovery/backfill trong rolling upgrade. Kết quả capacity mới cũng đổi QoS mClock của OSD target trong khi OSD base còn hành vi cũ.

**Hành động.** Nếu dùng mClock: chuyển override sang đúng key `_hdd`/`_ssd`, quyết định rõ `skip`/`force`, kiểm tra media classification và canary một OSD trước. Không bật `force` trên cả failure domain cùng lúc. Nếu không dùng `mclock_scheduler`, finding này không kích hoạt.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**. API config mới tự nó là support code; tác động đến upgrade đến từ caller mClock.

### CFG-003 — CephFS/MDS đổi throttle/prefetch và rename một client key

**Evidence.** Inventory `1235`–`1236`:

- `3ce222d89c816239ebd757583851079c66174f6d`: `mds_session_cap_acquisition_decay_rate` `10` → `30`, `mds_session_cap_acquisition_throttle` `500000` → `100000`.
- `988bc127e3818a8c74f8df57f7c6ba005dadb6bc`: `mds_oft_prefetch_dirfrags` `true` → `false`; option mang `FLAG_STARTUP`.
- `13404cdeda7c92f28b130560531e3f69f1926612`: rename `mds_max_retries_on_remount_failure` → `client_max_retries_on_remount_failure`, default vẫn `5`.
- `client_mount_timeout` đổi schema `TYPE_FLOAT` → `TYPE_SECS`, `client_caps_release_delay` đổi `TYPE_INT` → `TYPE_SECS`; giá trị default số không đổi.
- `fa3ef523844824ec8c924a610f53fae2091de39d`: `client_use_faked_inos` trở thành startup/no-monitor-update, nên không nên coi là live-tunable sau upgrade.
- `e518f0808a924aae4666c77fb054285633c8f214`: thêm `mds_beacon_mon_down_grace=60s`; MON target trì hoãn đánh dấu MDS laggy trong MON_DOWN/quorum mới.
- `7aebd406d15deed45e8426f2e0d0a7e4dac7b704` thêm `defer_client_eviction_on_laggy_osds=true`; consumer behavior nằm ở `6168e621f68728f066f1c7a41058a4dd2bda7370`, nơi MDS target tránh evict client khi OSD laggy có thể là nguyên nhân.
- `45a9bfd3055343ba6cad4d296e664d166b4e1a92`: thêm runtime threshold `mds_session_metadata_threshold=16_M`; session không tiến client-tid và vượt kích thước metadata có thể bị blocklist/evict.

**Tác động.** MDS target dùng cap-acquisition throttle thấp hơn và decay chậm hơn theo giá trị số mới; điều này có thể thay đổi latency/retry của workload readdir/cap-heavy sau restart. Việc tắt OFT dirfrag prefetch mặc định đổi startup warm-up của MDS: giảm công việc prefetch nhưng có thể chuyển latency sang lần truy cập sau. Trong mixed MDS failover/standby, rank chạy target và rank base có thể biểu hiện khác cho tới full upgrade.

Ba guard mới thay failure behavior trong cửa sổ upgrade: MON target cho MDS thêm grace sau quorum disruption; MDS target có thể giữ client lâu hơn khi OSD laggy, nhưng blocklist một session phình quá `16 MiB` và không tiến. Đây là trade-off availability/protection tự có theo default, không phải operator action. Trong mixed MON/MDS set, node/leader đang xử lý event quyết định behavior.

Rename client key là vấn đề migration cấu hình: override cũ không còn gắn với option target. Hai thay đổi type seconds chủ yếu làm schema rõ nghĩa hơn; chúng đáng kiểm nếu deployment sinh giá trị có suffix/float, nhưng net diff không tự chứng minh mọi giá trị cũ sẽ bị từ chối.

**Hành động.** Audit key cũ, chuyển sang `client_max_retries_on_remount_failure`; ghi nhận effective MDS/client values trước và sau canary. Test mount/remount, readdir lớn, MON election + MDS beacon grace, laggy-OSD client eviction, oversized/non-advancing session, active/standby failover và thời gian warm-up. Cluster không dùng CephFS có thể đánh dấu finding này không áp dụng.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện** vì có client blocklist/eviction semantics; confidence **high** cho default/branch, **medium** cho tần suất và mức latency thực tế.

### CFG-004 — RGW/RBD có retry/default mới và hai override RGW bị loại

**Evidence.** Inventory `1235`–`1236`:

- `a29cd656e4e9d94af190a68933463e916646a62a`: `rgw_max_notify_retries` `3` → `10`.
- `14e393444f27c13ee43bc0abe0e25eb9a3ba0554`: bỏ `rgw_bucket_quota_soft_threshold` và consumer quota tương ứng.
- `8942101535cdea788b8c08c30c6dad53f1aa31a8`: bỏ `rgw_rados_pool_pg_num_min` và việc dùng nó khi tạo pool.
- `666e6013275b0f0d4788b717bb116a2fb68a6bd2`/`016ebcfdb988eca8477a3d692a76e5ca9864d01e`: thêm giới hạn AIO cho RGW multi-object delete.
- `7d63ab5f97192b2bde876f6d0acd818d4789e612`: `rbd_mirroring_max_mirroring_snapshots` `3` → `5`, minimum vẫn `3`.
- `2f0910fd6814447f3d8e281f115f5d05d356d67b`: Vault KMS chuyển sang key riêng `rgw_crypt_vault_verify_ssl=true`; target caller không còn lấy quyết định verify từ `rgw_verify_ssl`. `8ffb21d88fdb8245168615626437255c49d91010` thêm CA riêng cho Vault.

**Tác động.** RGW target có thể giữ operation lâu hơn trong tình huống cache notify lỗi vì thử lại nhiều hơn; chính mô tả option cảnh báo trường hợp hiếm có thể kéo dài tới client timeout. Override quota soft-threshold cũ không còn hiệu lực, nên phải xác nhận semantics quota target thay vì chỉ copy cấu hình. Việc bỏ `rgw_rados_pool_pg_num_min` ảnh hưởng **pool mới được RGW tạo sau upgrade**, không tự thay `pg_num` của pool đã tồn tại.

Vault TLS là compatibility edge rõ: deployment base dựa vào `rgw_verify_ssl=false` để dùng Vault với certificate self-signed sẽ không tự kế thừa sang key mới; target mặc định verify `true`, nên KMS request có thể fail sau RGW restart nếu chưa đặt `rgw_crypt_vault_verify_ssl=false` hoặc CA phù hợp. Ưu tiên CA đúng hơn là tắt verify.

RBD mirror target cho phép thêm snapshot trước khi chạm giới hạn; điều này có thể làm usage/cleanup khác trong mixed daemon set, nhưng không phải format migration. Multi-delete AIO là option mới và chỉ đáng chú ý nếu workload dùng bulk delete hoặc operator override.

**Hành động.** Với RGW: kiểm tra config dump cho hai key bị bỏ và cả `rgw_verify_ssl`/`rgw_crypt_vault_*`; test Vault decrypt/encrypt bằng certificate production sau canary, tạo pool staging nếu automation còn dựa vào PG-min, rồi test cache notify/quota/multi-delete. Với RBD mirror: theo dõi snapshot count/backlog qua failover và rollback rehearsal. Không dùng RGW Vault/RBD mirror thì nhánh tương ứng không áp dụng.

**Đánh giá.** Rủi ro **cao theo điều kiện Vault self-signed/inherited override**, **trung bình** ở các nhánh còn lại; confidence **high**.

### CFG-005 — Storage/KV: một default bật, phần còn lại chủ yếu opt-in

**Evidence.** Inventory `1235`–`1236`; runtime được phân tích sâu ở báo cáo 02/03:

- `11fb62a0be67d3365ff6b46be0f15d40bf6312dc` thêm `osd_rocksdb_iterator_bounds_enabled=true`.
- `317eb8f69834fa08dbb17b19656db2359dbdcbd0` thêm compact-on-deletion; `c7fd52f207a72c3ac1bb1b83354fd5bd6a44bd13` chốt `rocksdb_cf_compact_on_deletion=false` theo default.
- `c6272752e78f366e0fe1744c74d541d6bdb105ee` thêm `bluefs_failed_shared_alloc_cooldown=600` giây.
- `e483a3a2761b875ece09c9b2a98104e5ff75eee6`, `e72d85e760c42cac103e544ba7d8ef6581b93ce7` và `793e5ade8c92d5d8b9327c100c647619f02a04c4` thêm controls cho fsck memory và AVL allocator search.

**Tác động.** Iterator bounds tự bật trên OSD target và thay đường quét OMAP/RocksDB; xem `03-rocksdb-block-device.md` để biết boundary/test gap. Cooldown BlueFS tham gia sau allocation failure, nên chỉ biểu hiện trên store chạm nhánh ENOSPC/fallback; xem `02-bluestore-bluefs.md`. Compact-on-deletion và một số fsck/allocator controls không đổi hành vi mặc định hoặc chỉ kích hoạt khi operator/tool đi qua đường tương ứng.

**Hành động.** Không đồng loạt override các knob mới chỉ vì chúng xuất hiện. Canary OMAP-heavy workload với iterator bounds mặc định; giám sát BlueFS allocation/ENOSPC; chỉ tune compaction/allocator sau benchmark. Không có bằng chứng từ owner set này về thay đổi DB/WAL format.

**Đánh giá.** Rủi ro **trung bình-thấp**, tăng lên khi workload OMAP nặng hoặc store đang sát dung lượng; confidence **high** cho activation, **medium** cho tác động hiệu năng.

### CFG-006 — Pool/autoscaler có controls mới, không tự đổi pool hiện hữu chỉ vì upgrade

**Evidence.** Inventory `1235`–`1236`:

- `d41ef37be9be70d242296d8b6b83ed3af4b4b588`: thêm `osd_pool_default_flag_bulk=false` và đường tạo pool `--bulk`.
- `b5edb374605c02a670d8c627bc9b5bb2b66ca340`: thêm `mgr_max_pg_num_change=128` để giới hạn mức thay đổi PG mỗi lần.
- `7a453da2600dd36c730187ad6803563001843ef7`: ràng buộc snap-trim concurrency tối thiểu `1`.
- Tài liệu owner `172` bổ sung ngữ cảnh pool/PG; code điều khiển thực nằm ở MON/MGR/OSD report tương ứng.

**Tác động.** Default bulk là `false`, nên pool mới giữ hành vi không-bulk trừ khi command/automation yêu cầu. Giới hạn thay đổi PG có thể làm autoscaler hội tụ qua nhiều bước hơn, đáng chú ý trong stabilization sau upgrade nhưng giảm bước nhảy lớn. Không có bằng chứng các option này tự mutate pool hiện hữu ngay lúc nâng cấp nếu không có proposal/autoscaler action.

**Hành động.** Soát automation tạo pool để không vô tình phụ thuộc default, ghi lại autoscaler mode và pending recommendations trước rolling upgrade, không thực hiện rebalance/PG expansion lớn đồng thời nếu không cần. Cross-check chi tiết command/OSDMap ở `04-mon-osdmap-crush.md`.

**Đánh giá.** Rủi ro **trung bình theo điều kiện**, confidence **high**.

### CFG-007 — Schema chặt hơn và các key runtime cũ có thể làm preflight/override lệch kỳ vọng

**Evidence.** Inventory `1235`–`1236`:

- `847972f9b21b3a8213952512e287d1e4bff16801`: `log_max_recent` có minimum `1` và code logging dùng lại giá trị này.
- `7a453da2600dd36c730187ad6803563001843ef7`: `osd_pg_max_concurrent_snap_trims` có minimum `1`.
- `2dd94f2d9316b5b11b5b7a994810f54c539d01d3`: bỏ `ms_async_max_op_threads`; code DPDK cũ dùng nó cũng được refactor. `afbe64650dcdca5ce8ce13988efb0fcf2e75ac89` thêm `ms_async_reap_threshold`, nhưng đây không phải rename tương đương.
- `3c419206efa4bb80a93d26abbe53d66f31f9c54a`: bỏ `rbd_persistent_cache_log_periodic_stats`; target luôn cập nhật PWL cache state định kỳ và chuyển dòng stats sang debug level `5`, nên key cũ không còn bật/tắt hành vi đó.

**Tác động.** Override `0` cho hai option có minimum mới hoặc key messenger/PWL đã bỏ có thể bị validation/báo unknown hoặc đơn giản không còn tạo hiệu ứng như base, tùy đường nạp config và policy cảnh báo. Không nên khẳng định daemon chắc chắn fail startup chỉ từ schema; cần chạy chính binary target với config thực. Với DPDK/ms_async tuning, việc map `ms_async_max_op_threads` sang `ms_async_reap_threshold` là sai nghĩa. Với RBD PWL, target vẫn cập nhật state định kỳ; thay đổi là control/visibility và stale override, không phải mất data hay format migration từ riêng option removal.

**Hành động.** Dùng preflight config-assimilate/config-check tương ứng với quy trình triển khai, tìm unknown/deprecated keys trong log canary, và xác minh effective values sau restart. Giữ bản chụp config database để rollback cấu hình; không tự xóa key trước khi xác nhận consumer và rollback plan.

**Đánh giá.** Rủi ro **thấp-trung bình**, confidence **medium-high** vì outcome validation cụ thể phụ thuộc cách cluster inject cấu hình.

## 5. Coverage/disposition ledger

Mỗi dòng CSV đã được sàng lọc đúng một lần; các nhóm dưới đây không chồng lặp và tổng bằng 20:

- `conditional` — 3 dòng: `1225`–`1227`. API lấy default chỉ có ý nghĩa upgrade khi caller mClock/daemon tương ứng chạy.
- `mixed` — 2 dòng: `1235`–`1236`. Hai registry option chứa cả thay đổi quan trọng, opt-in và hunk không liên quan; không thể gắn một disposition duy nhất cho mọi hunk.
- `support` — 6 dòng: `160`, `165`, `166`, `169`, `171`, `172`. Tài liệu giúp xác nhận semantics/operation nhưng không trực tiếp đổi binary runtime.
- `trivial` — 9 dòng: `159`, `161`–`164`, `167`–`168`, `170`, `173`. Net diff trong owner này là biên tập, tổ chức tài liệu, wording hoặc nội dung không tạo đường tác động upgrade độc lập sau khi đối chiếu code.
- `material` — 0 dòng độc lập. Các thay đổi material nằm trong hai file registry `mixed` và được tách thành finding ở trên.

Tổng: `3 + 2 + 6 + 9 = 20`. `review_mode` trong CSV là routing ban đầu; ledger này là kết luận sau phân tích.

## 6. Mixed-version, full-upgrade và rollback

- **Mixed phase:** default được resolve theo binary đang chạy, nên OSD/MDS/RGW cũ và mới có thể khác hành vi dù cùng config database nếu không có override. Ưu tiên canary theo daemon role và so effective config, không chỉ so stored key.
- **Full upgrade:** khi mọi daemon dùng target, các default mới trở nên đồng nhất; stale keys vẫn cần dọn có kiểm soát vì chúng có thể gây cảnh báo hoặc đánh lừa runbook.
- **Rollback binary:** các option mới không chứng minh tạo format không tương thích, nhưng config mới/key rename có thể không được binary base hiểu. Trước rollback, phục hồi mapping key cũ và bỏ/ẩn key chỉ target hiểu theo runbook đã test.
- **Không tự động kết luận:** không có bằng chứng ở owner set này rằng một schema type/min mới chắc chắn chặn startup trong mọi deployment, hoặc một default mới làm thay đổi dữ liệu on-disk.

## 7. Validation đề xuất — chưa chạy

1. Xuất config database và effective config theo từng role; tìm sáu key remove/rename nêu ở mục 2 cùng mọi override cho các default thay đổi.
2. Khởi động một OSD canary, kiểm tra mClock scheduler/media, xem benchmark có chạy hay không, thời gian boot, I/O latency và config capacity được ghi vào MON.
3. Trong mixed OSD phase, test client burst/RETURNVEC đại diện và quan sát memory/backpressure, shutdown notification, peering/recovery sau restart.
4. Nếu có CephFS, test MDS restart/failover, OFT warm-up, readdir/cap throttle, MON_DOWN grace, laggy-OSD eviction, oversized session và client remount với key mới.
5. Nếu có RGW/RBD mirror, test Vault TLS với CA/self-signed policy thật, inject lỗi cache notify ở lab, test quota/pool-create/multi-delete và theo dõi mirror snapshot/PWL telemetry.
6. Chạy test OMAP iterator/BlueFS fault path theo báo cáo 02/03; không bật compact-on-deletion hàng loạt trong cùng cửa sổ upgrade.
7. Rehearse rollback với bản chụp config: binary base phải khởi động mà không phụ thuộc các key chỉ target hiểu.

## 8. Giới hạn và kết luận

Không có As-Is config dump, daemon inventory, scheduler profile, pool automation, CephFS/RGW/RBD usage hoặc telemetry nên applicability thực tế còn phải xác nhận. Báo cáo không gán mức ảnh hưởng chỉ từ số dòng diff và không coi tài liệu frontend/client thuần túy là finding nếu không có causal path.

Điểm cần đưa thẳng vào runbook là: **audit key cũ, chụp effective config, canary từng role, xử lý mClock trước OSD restart, và kiểm Vault TLS/CephFS guard defaults nếu các dịch vụ đó được dùng**. Phần còn lại của 20 dòng đã được giữ trong CSV để bảo toàn inventory, nhưng chỉ các finding trên có bằng chứng về khả năng ảnh hưởng quá trình nâng cấp.
