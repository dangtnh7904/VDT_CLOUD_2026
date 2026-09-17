# Checklist nâng cấp Ceph Pacific 16.2.5 → 16.2.15

> **Trạng thái:** Pha 1 — checklist này mới tổng hợp bằng chứng từ báo cáo 00–07.
>
> **Quyết định mặc định hiện tại:** **HOLD / chưa đủ điều kiện GO Production** cho tới khi các gate áp dụng được đánh dấu PASS và phần 08–15 được nhập vào checklist.
>
> **Giới hạn:** đây là checklist chuẩn bị, kiểm chứng và ra quyết định; không phải lệnh cho phép thay đổi cluster. Không có lệnh nâng cấp, repair, migrate, trim hay thay cấu hình nào đã được chạy khi tạo tài liệu.
>
> **Ngày lập:** 2026-09-17.

## 1. Phạm vi và cách dùng

### 1.1 Phạm vi đã có bằng chứng

- [x] Base: v16.2.5, commit đã peel tag là **0883bdea7337b95e4b611c768c0279868462204a**.
- [x] Target: v16.2.15, commit đã peel tag là **618f440892089921c3e944a991122ddc44e60516**.
- [x] Base là ancestor của target; source tree dùng để phân tích sạch và không shallow.
- [x] Inventory net diff có 2.665 file: A605, M1842, D162, R56; tổng +323.147/-176.246 dòng.
- [x] Checklist chỉ dùng finding đã kiểm chứng trong 00–07; P0/P1/P2 chỉ là ưu tiên đọc, không phải mức rủi ro hay quyết định GO/NO-GO.
- [ ] Xác nhận image/package thực tế sẽ triển khai đúng v16.2.15 nêu trên.
- [ ] Liệt kê mọi vendor patch hoặc custom backport. Nếu build triển khai khác endpoint đã so sánh, phải đánh giá delta đó trước khi dùng checklist này.

| Nguồn | Nội dung dùng trong checklist |
| --- | --- |
| [00 — File inventory](./00-file-inventory.md) | Chốt nguồn, độ phủ và giới hạn của inventory |
| [01 — OSD/PG/recovery](./01-osd-pg-recovery.md) | EC, peering, recovery/backfill, scrub, PGLog và primary-version behavior |
| [02 — BlueStore/BlueFS](./02-bluestore-bluefs.md) | Replay/durability, OMAP, fsck/repair, allocator và rollback BlueFS |
| [03 — RocksDB/block device](./03-rocksdb-block-device.md) | OMAP iterator, range delete, reshard, exclusive device open và error handling |
| [04 — MON/OSDMap/CRUSH](./04-mon-osdmap-crush.md) | Quorum, map/state gate, release flag, placement và MON store |
| [05 — Messaging/auth/common](./05-messaging-auth-common.md) | CephX, messenger lifecycle, mixed messages, platform và connectivity |
| [06 — Config/defaults](./06-config-defaults.md) | Key bị bỏ/đổi tên, default mới và điều kiện activation |
| [07 — MGR/modules/monitoring](./07-mgr-modules-monitoring.md) | MGR failover, custom modules, Prometheus, Dashboard, autoscaler và alerts |

### 1.2 Quy ước quyết định

- **PASS:** đã có bằng chứng môi trường, kết quả test và owner ký nhận.
- **FAIL/BLOCK:** không được mở rộng phase bị ảnh hưởng.
- **N/A:** chỉ được dùng khi có bằng chứng điều kiện kích hoạt không tồn tại.
- **STOP:** dừng rollout, giữ nguyên bằng chứng và phân loại sự cố trước khi quyết định forward-fix hay rollback.
- **Conditional blocker:** chỉ chặn role, dịch vụ hoặc feature tương ứng; không tự động chặn toàn bộ binary upgrade.

Mỗi checkbox khi đóng phải có tối thiểu: owner, thời điểm, kết quả, đường dẫn bằng chứng và tiêu chí PASS đã dùng. Không đánh dấu PASS chỉ dựa vào HEALTH_OK hoặc HTTP 200.

### 1.3 Thông tin change cần điền

| Trường | Giá trị |
| --- | --- |
| Cluster / môi trường | |
| Change ID | |
| Người chỉ huy thay đổi | |
| Owner MON/MGR/OSD | |
| Owner storage/network/security/monitoring | |
| Cửa sổ dự kiến | |
| Guardrail latency/error/recovery/capacity | |
| Thời gian soak tối thiểu mỗi phase | |
| Phương án rollback được chọn | |
| Nguồn telemetry độc lập khi Prometheus lỗi | |
| Trạng thái cuối | HOLD / GO LAB / GO CANARY / GO PRODUCTION / NO-GO |

## 2. Gate tổng hợp trước khi nâng cấp

| Gate | Điều kiện PASS tối thiểu | FAIL/BLOCK khi | Finding |
| --- | --- | --- | --- |
| G00 — Artifact | Package/image đúng endpoint hoặc mọi patch thêm đã được review | Không truy vết được build thực tế | 00 |
| G01 — Cluster health | Mọi WARN/ERR, PG bất thường, scrub backlog và daemon down đều có baseline, owner và disposition | Có mount/replay error, checksum mismatch, unexplained inconsistent/unfound, scrub stuck, quorum bất ổn hoặc daemon restart loop | OSD-002/003/004/008/010/014, BS-002/003, MON-003 |
| G02 — Rollback storage | Có restore per-OSD đã test, hoặc forward-only/rebuild strategy được phê duyệt và diễn tập | Runbook chỉ ghi “hạ package về 16.2.5” sau khi OSD target đã ghi BlueFS | BS-001, OSD-007 |
| G03 — MON control plane | Quorum/rank ổn định; MON store, retained maps và free space đủ theo guardrail môi trường | Election loop, Paxos không catch-up, store gần cạn hoặc headroom chưa biết | MON-003/006/009 |
| G04 — Device/config safety | Device ownership duy nhất; allocator override hợp lệ; effective config đã được so | Alias cùng major:minor chưa giải thích, invalid allocation unit, stale/renamed key chưa có xử lý | BS-007, KVBD-005/006, CFG-002–007 |
| G05 — Monitoring stop/go | Target active MGR scrape parse được, up=1, golden queries có dữ liệu; hoặc có telemetry độc lập đã phê duyệt | Duplicate HELP/TYPE, scrape fail, hoặc standby body rỗng bị coi là healthy | MGR-005/006 |
| G06 — MGR/mixed consumers | ms_die_on_bad_msg giữ false/default hoặc không tạo mixed target-MON/base-MGR; custom module, Dashboard TLS/API, autoscaler và consumer schema đã qua canary | Fatal option true khi còn pairing này, unknown-message crash/reset loop, metadata không hội tụ, callback im lặng, TLS client lỗi hoặc PG action bất ngờ | MSG-009, MGR-001–008 |
| G07 — Service-specific | Mọi dịch vụ đang dùng có test theo điều kiện: CephFS, RGW Vault, RBD read-only/mirror, stretch, FIPS/AArch64 | Dịch vụ áp dụng nhưng chưa có inventory hoặc test tương ứng | MON-005/007, MSG-005/008, CFG-003/004, MGR-008 |
| G08 — Scope còn thiếu | Phần 08–15 đã được ghép và các gate mới đã xử lý | Chưa ghép 08–15 | Deferred |

**Ý nghĩa của HOLD hiện tại:** chưa có As-Is và runtime validation của cluster đích, đồng thời 08–15 chưa nằm trong tài liệu này. Đây chưa phải kết luận rằng 16.2.15 không thể nâng cấp.

## 3. Checklist As-Is bắt buộc

### 3.1 Cluster, topology và baseline chung

- [ ] Ghi deployment mode và cơ chế quản lý daemon. Chỉ inventory ở pha này; procedure cephadm/orchestrator thuộc phần 08.
- [ ] Lưu version từng MON, MGR, OSD và daemon dịch vụ; liệt kê daemon down/offline có thể rejoin.
- [ ] Lưu health summary/detail và phân loại từng cảnh báo: có từ trước, chấp nhận tạm thời, hay phải sửa trước rollout.
- [ ] Chụp MonMap, OSDMap, CRUSH map, pool properties, daemon tree và config database.
- [ ] Lưu baseline client error rate, p95/p99 latency, throughput, recovery/backfill rate, CPU/RSS, disk latency và network reset.
- [ ] Định nghĩa guardrail bằng số theo SLO/capacity của cluster. Các báo cáo không cung cấp ngưỡng Production chung, nên không tự bịa threshold.
- [ ] Chọn failure domain cho canary; không restart đồng thời nhiều daemon trong cùng failure domain khi chưa chứng minh an toàn.

### 3.2 OSD, PG, recovery và workload

- [ ] Inventory pool replicated/EC, size/min_size, EC profile và async-recovery override. [OSD-001/002]
- [ ] Ghi PG degraded, incomplete, inconsistent, unfound, peering, remapped và stuck; lưu acting set/primary baseline. [OSD-001/002/004/006/007/008]
- [ ] Ghi các cờ noout, noin, noup, nodown, norecover, nobackfill, noscrub, nodeep-scrub và lý do tồn tại.
- [ ] Ghi scrub/deep-scrub backlog, timestamp cuối, reservation và lỗi đang mở. [OSD-004]
- [ ] Đo PGLog dups, RocksDB/DB free space, OSD boot status và headroom. [OSD-003]
- [ ] Ghi recovery/backfill overrides, capacity headroom, stretch mode và lịch sử backfill interruption. [OSD-005/006]
- [ ] Ghi compat feature SNAPMAPPER2 và nguồn gốc các store rất cũ. [OSD-010]
- [ ] Xác định có profile rbd-read-only, cache tier, dedup/object manifest, set_chunk hoặc snapshot clone hay không. [OSD-013/014]

### 3.3 BlueStore, BlueFS, RocksDB và block device

- [ ] Với từng OSD, lưu media class và topology block, block.db, block.wal; dung lượng, free space, spillover và fragmentation. [BS-006/007/010]
- [ ] Ghi effective bluestore_prefer_deferred_size và layout WAL/DB/SLOW. [BS-003]
- [ ] Ghi mọi override bluefs_shared_alloc_size, allocator block size/unit và volume-selection policy. [BS-006/007]
- [ ] Ghi legacy OMAP warning/state, lịch sử fsck/repair, repair-on-open, shared-blob error, clone/snapshot density và osd_memory_target. [BS-004/005]
- [ ] Ghi kiến trúc/page size, đặc biệt AArch64 64 KiB, nếu có provisioning hoặc label/device path tương ứng. [BS-009]
- [ ] Ghi effective bluestore_rocksdb_cf/cfs, CF sharding spec, iterator-bounds, delete-range threshold và compact-on-deletion options. [KVBD-001–004]
- [ ] Đối chiếu device/LVM/symlink/container path về major:minor; chứng minh mỗi device chỉ có một writer/owner. [KVBD-005/006]
- [ ] Xác nhận runbook có hay không các thao tác reshard, compact, repair, import, migrate, set-superblock hoặc relabel.

### 3.4 MON, maps, placement và auth/messaging

- [ ] Lưu MON quorum, rank, leader, election epoch/history, quorum age, connection score và clock/network health. [MON-003]
- [ ] Lưu dung lượng/free space và trend của MON store, retained OSDMap epochs, health-store/mute state. [MON-006/009]
- [ ] Lưu require_osd_release, feature bits và mọi OSD pre-Pacific, kể cả OSD đang offline. [MON-001/002]
- [ ] Xác định có CIDR/range blocklist state hoặc automation gọi feature này hay không. [MON-001, MSG-007]
- [ ] Ghi pending PG merge, pg_temp, upmap exception và balancer/pool automation. [MON-006/008]
- [ ] Nếu stretch: lưu tiebreaker, MonMap, CRUSH rules/buckets/weights và site recovery state; nếu không, ghi N/A có bằng chứng. [MON-007]
- [ ] Inventory config mask theo location, host và device class; lấy effective config trên OSD đại diện mỗi nhóm. [MON-011]
- [ ] Ghi msgr1/msgr2 usage, ms_die_on_bad_msg, reconnect/reset baseline, fast-shutdown flags và MON priority/weight. [MSG-002/003/009]
- [ ] Ghi explicit/auto public_addr và cluster_addr, interface state và crush_location_hook. [MSG-006]
- [ ] Lưu CephX rotating-key version, auth retry/session reopen và MON↔MGR reconnect baseline. [MON-004, MSG-001/009]

### 3.5 Config và dịch vụ có điều kiện

- [ ] Export cả stored config database và effective config theo từng daemon/role; không chỉ lưu config dump thô. [CFG-001–007, MON-011]
- [ ] Tìm sáu key cũ nêu ở bảng mục 4.1 và ghi scope/owner của từng occurrence.
- [ ] Ghi effective OSD defaults đổi ở mục 4.2 và mọi override tương ứng.
- [ ] Nếu dùng mClock: lưu scheduler, media classification, capacity HDD/SSD, skip/force benchmark, thời gian boot và I/O baseline. [OSD-011, CFG-002]
- [ ] Nếu dùng CephFS: lưu fs dump, compat flags, active/standby-replay, MDS/client config, client type/version và consumer perf-stat. [MON-005, MSG-008, CFG-003, MGR-008]
- [ ] Nếu dùng RGW Vault: lưu CA, certificate policy, rgw_verify_ssl và rgw_crypt_vault_*; ghi FIPS/OpenSSL mode nếu áp dụng. [MSG-005, CFG-004]
- [ ] Nếu dùng RBD mirror/PWL: lưu mirror snapshot count/backlog và telemetry hiện tại. [CFG-004/007]
- [ ] Inventory CPU architecture và compiler/package trên fleet; đánh dấu host AArch64. [MSG-005]

### 3.6 MGR, Dashboard và monitoring

- [ ] Lưu active/standby MGR, enabled modules, service URI và failover baseline. [MGR-001/002]
- [ ] Liệt kê mọi custom/third-party MGR module, package/site path, method notify() và NOTIFY_TYPES. [MGR-003]
- [ ] Lưu autoscaler mode/flags, target_size_ratio, pg_num_min/max, bulk/noautoscale và pending recommendation. [MGR-004]
- [ ] Export golden Prometheus exposition: metric names, types, labels, cardinality và representative queries. [MGR-005/006]
- [ ] Ghi discovery/LB/scraper target; xác định liệu scraper có thể chạm MGR standby hay không. [MGR-006]
- [ ] Export runtime rules, checksum, Alertmanager routes/inhibitions/silences, ticket automation và notification destinations. [MGR-010]
- [ ] Inventory browser, API client, reverse proxy, VIP/LB, certificate chain và SNI; xác nhận TLS capability. [MGR-007]
- [ ] Nếu dùng stats/cephfs-top/parser riêng, lưu golden schema và rank-0 failover baseline. [MGR-008]

## 4. Thay đổi hoặc sửa đổi cần chuẩn bị

### 4.1 Sáu key cấu hình cũ phải audit

| Key ở base | Target | Việc cần làm trước restart role liên quan |
| --- | --- | --- |
| osd_mclock_max_capacity_iops | Bị bỏ; target dùng key theo media _hdd hoặc _ssd | Nếu dùng mClock, map theo media thật, quyết định skip/force benchmark và canary; không copy mù |
| mds_max_retries_on_remount_failure | Đổi thành client_max_retries_on_remount_failure | Nếu dùng CephFS, chuyển có kiểm soát và test remount; giữ mapping rollback |
| ms_async_max_op_threads | Bị bỏ | Không map sang ms_async_reap_threshold vì khác nghĩa; test config thực và log unknown key |
| rgw_rados_pool_pg_num_min | Bị bỏ | Sửa automation tạo pool; không giả định pool hiện hữu tự thay |
| rgw_bucket_quota_soft_threshold | Bị bỏ | Xác nhận quota semantics và sửa automation/runbook phụ thuộc key |
| rbd_persistent_cache_log_periodic_stats | Bị bỏ | Không coi việc bỏ key là tắt cập nhật state; cập nhật monitoring/runbook và giữ rollback mapping |

- [ ] Chụp config snapshot trước khi sửa.
- [ ] Mỗi key có owner, decision giữ/chuyển/bỏ và test trên binary target.
- [ ] Không xóa stale key trước khi rollback rehearsal hoàn tất.
- [ ] Binary base phải được test với config dự kiến dùng khi failback.

### 4.2 Default mới cần chấp nhận hoặc override có chủ đích

| Default/behavior target | Điều cần xác nhận |
| --- | --- |
| osd_client_message_cap: 0 → 256 | Backpressure, memory và client latency trong canary |
| osd_fast_shutdown_notify_mon: false → true | OSD/MON shutdown/down signal không tạo false alarm |
| osd_max_write_op_reply_len: 32 → 64 | Workload RETURNVEC/client tương ứng và PGLog behavior |
| osd_aggregated_slow_ops_logging: true | Log parser, cluster-log rate và MON DB pressure |
| osd_pg_max_concurrent_snap_trims minimum 1 | Override 0 cũ và snap-trim behavior |
| log_max_recent minimum 1 | Override 0 cũ và config validation |
| osd_rocksdb_iterator_bounds_enabled: true | OMAP correctness/boundary test |
| Dashboard minimum TLS 1.3 | Client/proxy/VIP/LB/API tương thích |
| RGW Vault verify key riêng mặc định true | CA hợp lệ hoặc policy riêng đã duyệt |

- [ ] Không override hàng loạt chỉ vì default đổi; mọi override phải có mục tiêu, owner, benchmark và rollback.
- [ ] So effective config sau restart/reconnect, vì target có thể áp dụng đúng location mask mà base từng bỏ qua. [MON-011]

### 4.3 Sửa bắt buộc theo điều kiện

- [ ] **Device mapping:** sửa alias/ownership không rõ trước first target OSD. Target dùng O_EXCL và có thể fail sớm; mở được hai writer là lỗi nghiêm trọng. [KVBD-005/006]
- [ ] **Allocator:** mọi bluefs_shared_alloc_size phải không nhỏ hơn block size và chia hết cho allocation unit; unresolved/invalid override chặn OSD rollout. [BS-007]
- [ ] **mClock:** chuyển generic capacity sang đúng _hdd/_ssd; không để cả failure domain benchmark đồng thời; WPQ không cần bị đổi sang mClock. [OSD-011, CFG-002]
- [ ] **Custom MGR module:** module có notify() phải khai báo đúng subset mon_map, pg_summary, health, clog, osd_map, fs_map hoặc command. service_map không có ở endpoint này. [MGR-003]
- [ ] **Target MON → base MGR:** nếu tổ hợp mixed này có thể tồn tại, giữ ms_die_on_bad_msg ở false/default hoặc tránh tổ hợp đó cho tới khi rehearsal PASS. ms_die_on_bad_msg=true, MGR abort/reset loop hoặc metadata version không hội tụ là blocker mở rộng MON/MGR. [MSG-009]
- [ ] **Prometheus:** chuẩn bị package/backport đã verify parser hoặc telemetry độc lập đã được phê duyệt. Không có config workaround an toàn được chứng minh trong report. [MGR-005]
- [ ] **Dashboard:** nâng client/proxy/LB lên TLS 1.3. UNSAFE_TLS_v1_2 chỉ là escape hatch có security approval, restart và retest. [MGR-007]
- [ ] **Alerts:** map 18 alertname cũ sang 58 tên target hoặc quyết định deprecate; intersection exact bằng 0. Sửa route, inhibition, silence, ticket và runbook trước runtime reload. [MGR-010]
- [ ] **CephFS:** chuẩn bị key remount mới, schema perf v2 và expectation cho throttle/prefetch/grace/eviction/session guards. [CFG-003, MGR-008]
- [ ] **RGW Vault:** nếu base dựa vào rgw_verify_ssl=false hoặc self-signed certificate, cài CA đúng hoặc thiết lập policy riêng đã duyệt trước RGW restart. [CFG-004]
- [ ] **Config automation:** parser phải hỗ trợ output/name target và phải so effective values, không chỉ stored values. [MON-011, CFG-007]
- [ ] **Package selection:** đi thẳng tới endpoint 16.2.15 theo plan; không dừng ở 16.2.8 vì regression TTL-cache trung gian đã được sửa ở endpoint target. [MGR-002]

### 4.4 Guardrail: không gộp vào rolling binary upgrade

- [ ] Không chạy offline PGLog trim hoặc mark_unfound_lost như bước preventive.
- [ ] Không chạy quick-fix legacy OMAP, fsck repair, shared-blob repair hoặc repair-on-open mới chưa test.
- [ ] Không chạy BlueFS import/migrate/new DB/WAL, set-superblock, relabel hoặc provisioning trong cùng change.
- [ ] Không reshard RocksDB, bật compact-on-deletion hoặc destructive repair trong cùng change.
- [ ] Không tạo CIDR range-blocklist trong mixed phase.
- [ ] Không nâng require_osd_release chỉ để xóa health warning.
- [ ] Không đổi stretch topology, remove/replace MON, merge/expand PG hoặc chạy balancer lớn đồng thời nếu không phải change riêng đã test.
- [ ] Không rotate/import auth key thủ công hoặc rebuild monstore/viết lại OSDMap như bước upgrade thường lệ.
- [ ] Không reload/redeploy bộ alert target trước khi Prometheus parser gate và alert mapping đã PASS.

Các thao tác trên cần change riêng, backup/clone phục hồi được, peer review, tiêu chí dừng và test chuyên biệt.

## 5. Activation: điều gì tự xảy ra, điều gì không

| Nhóm | Activation | Lưu ý |
| --- | --- | --- |
| OSD/PG fixes | Tự động theo binary OSD/primary target | Trong mixed phase, đổi primary có thể đổi outcome; phải test primary base và target |
| BlueFS replay/durability và opcode mới | Local theo OSD target khi mount/ghi metadata | Không phải wire incompatibility, nhưng tạo rollback boundary per-OSD |
| OMAP iterator/range delete và O_EXCL | Tự động sau OSD target restart/data path | Compact-on-deletion vẫn mặc định tắt |
| MON election/auth/map/config mask fixes | Theo MON leader/session target | Leader base vẫn giữ behavior cũ trong mixed phase |
| Messenger/lifecycle fixes | Local theo process target | Peer base vẫn có race cũ ở phía của nó |
| Default/config changes | Khi role target restart hoặc đi qua code path tương ứng | Stored config giống nhau không bảo đảm effective behavior giống nhau |
| mClock benchmark | Chỉ khi scheduler là mclock_scheduler và điều kiện skip/force/capacity đúng | Có thể tăng boot time/I/O và ghi capacity vào MON config |
| MGR behavior | Theo MGR đang active | Failover base ↔ target có thể đổi metrics, events và recommendation |
| Prometheus duplicate metadata | Target MGR active, module được scrape và có ít nhất một pool | HTTP 200 không chứng minh parser chấp nhận |
| Dashboard TLS 1.3 | Khi target Dashboard server khởi động/promote | Client TLS 1.2-only có thể mất kết nối |
| CIDR range-blocklist, pool/bulk controls, repair/tools | Opt-in/operator action | Không cần kích hoạt để hoàn tất patch upgrade |
| Alert rules mới | Chỉ khi runtime file được thay và Prometheus reload/redeploy | File package đổi không chứng minh runtime rules đã đổi |

## 6. Kế hoạch test bắt buộc

Tất cả test fault injection, corruption, power-cut, repair, map trim, device mutation hoặc old-reader mount phải chạy trên lab/fixture/clone disposable. Checklist này không cho phép chạy chúng trên Production.

### 6.1 Pre-upgrade / lab

| Test | Tiền điều kiện và hành động | PASS | FAIL/STOP | Finding |
| --- | --- | --- | --- | --- |
| T00 — Artifact/config | Kiểm package SHA/version và nạp config thực bằng binary target trong môi trường an toàn | Không có delta chưa review; unknown/type/minimum issue đã có disposition | Build không truy vết hoặc config critical không parse | 00, CFG-007 |
| T01 — BlueFS rollback | Clone OSD 16.2.5, mount target và phát sinh đủ metadata để xác nhận target đã ghi opcode log mới; thử target replay và old reader trên clone khác | Target replay sạch; old reader chạm đúng unrecognized op/-EIO dự kiến; restore pre-upgrade image đã được chứng minh | Không chứng minh được opcode/biên downgrade, restore thất bại, hoặc runbook vẫn dựa vào package downgrade trên cùng store | BS-001 |
| T02 — Device alias | Dùng block aliases cùng major:minor trên device disposable | Target chặn writer thứ hai; ownership Production rõ | Hai writer mở được hoặc mapping Production chưa giải thích | KVBD-005/006 |
| T03 — Allocator config | Kiểm divisibility và khởi động scratch store với override thực | Không assert/false ENOSPC | Assert, init fail hoặc value không hợp lệ | BS-007 |
| T04 — Prometheus parser | Cho target MGR active trên staging/canary; parse toàn bộ /metrics bằng parser thật | Parse pass, target up=1, golden queries có data | Duplicate HELP/TYPE, scrape error hoặc body standby rỗng bị coi healthy | MGR-005/006 |
| T05 — Platform | Nếu áp dụng, chạy CRC vectors trên AArch64 build thật và RGW paths với FIPS/OpenSSL thật | Vector/request/ETag đúng, không abort | Checksum/request mismatch hoặc abort | MSG-005 |
| T05A — Buffer/LRU fault paths | Nếu workload áp dụng, chạy fixture zero-length-tail buffer và concurrency của RGW file/NFS LRU | Không SIGABRT, double-unlock hoặc deadlock | Abort, lock fault hoặc data-path lỗi | MSG-004 |
| T06 — Conditional storage fixtures | Nếu áp dụng: legacy SnapMapper/OMAP, shared blobs, reshard, compact, repair, AArch64 label | Cardinality/checksum/reopen/fsck đúng trên clone | Data mismatch, memory vượt budget, repair/reshard lỗi | OSD-010, BS-004/005/009, KVBD-003/004/007 |
| T07 — PGLog duplicate inflation | Fixture PGLog có dups vượt ngưỡng; tạo thêm activity để quan sát warning và bounded auto-trim; chỉ thử offline trim trên stopped clone khi thật sự cần, rồi reopen DB | Warning đúng ngưỡng, auto-trim tiến có giới hạn; clone sau offline trim reopen được; RSS/DB/tombstone trong guardrail | OSD không boot/mount, PGLog decode lỗi, DB không reopen hoặc resource vượt guardrail | OSD-003 |

### 6.2 Mixed-version / canary

| Test | Tiền điều kiện và hành động | PASS | FAIL/STOP | Finding |
| --- | --- | --- | --- | --- |
| T10 — MON transition | Canary follower, rồi leader transition có kiểm soát trong lab; quan sát quorum/election/Paxos | Quorum hội tụ, rank/age/session hợp lệ, no loop | Mất quorum, election loop, Paxos không catch-up | MON-003 |
| T11 — CephX/MON↔MGR | Ép auth rotation quanh leader change; target MON nói chuyện base MGR | Chỉ key committed được publish; MGR không restart, metadata hội tụ | Auth loop, key divergence, unknown-message fatal/reset loop | MON-004, MSG-001/009 |
| T12 — MGR promote/failback | Target standby → active → base failback; test module/service-map/cache/event rebuild | Không assert/deadlock; custom callbacks đến; service URI đúng | Module im lặng, restart loop, callback mất hoặc state không hội tụ | MGR-001–003 |
| T13 — Metrics/LB | Direct active, direct standby và qua LB; diff schema/types/labels/version/cardinality | Scraper chọn active, parser pass, queries đúng | Chọn standby 200/body rỗng, parse fail hoặc schema consumer hỏng | MGR-005/006 |
| T14 — Dashboard | Direct/LB login, session, redirect, API Accept và TLS 1.3 | Tất cả client path/cert/SNI pass | Client/proxy/LB mất kết nối hoặc redirect/API sai | MGR-007 |
| T15 — Autoscaler | So recommendation quanh active flip; giữ PG changes không cần thiết ở trạng thái freeze theo runbook | Không có PG action bất ngờ; guards/min/max đúng | Tự thay PG ngoài expectation hoặc recommendation không giải thích được | MON-008, CFG-006, MGR-004 |
| T16 — EC/hinfo | EC pool lab, đổi primary base/target, async recovery và fixture hinfo lỗi | Acting không xuống dưới min_size; target không assert; inconsistent/unfound được báo đúng | Mất I/O ngoài policy, assert, checksum mismatch | OSD-001/002 |
| T17 — Scrub/peering/backfill | Remap, delayed reservation, primary failover và interrupted backfill | Scrub FSM thoát, đúng acting, accounting đúng, không bypass full guard | Stuck/incomplete/stale PG hoặc vượt capacity guard | OSD-004/006/007 |
| T18 — Partial recovery/OMAP | Restart giữa partial recovery; range delete và missing EC copy trên fixture | Checksum/key cardinality/errno đúng; scrub clean | Checksum mismatch, inconsistent hoặc boundary sai | OSD-005/008, KVBD-001/002 |
| T19 — BlueStore mixed workload | Object/OMAP/snapshot workload qua từng target OSD canary | PG ổn định, mount/replay sạch, client checksum đúng | Replay/mount error, corruption, ENOSPC/assert hoặc recovery bất thường | BS-001/002/003/006–008 |
| T20 — mClock/effective config | Một OSD mỗi media/host/class; so WPQ/mClock boot và location mask | Benchmark đúng policy, capacity/effective values đúng, latency trong guardrail | Unexpected benchmark, boot timeout, wrong config hoặc guardrail breach | OSD-011, CFG-002, MON-011 |
| T21 — Messenger lifecycle | Representative traffic, peer restart/network flap/shutdown trong lab | Reconnect hội tụ, no coredump/stuck thread/reset storm | Hang, abort, reset storm hoặc false timeout không giải thích được | MSG-002/003 |
| T21A — Address/hook/MON-weight edge | Nếu áp dụng, test auto-address selection, crush_location_hook và MonClient với MON weight bằng 0 | Advertised address/location đúng; client hunt không abort và hội tụ | Bind/advertise sai, hook sai hoặc client abort/không kết nối | MSG-006 |
| T22 — RBD caps/manifest | Primary base/target với rbd-read-only; manifest/snapshot fixture nếu dùng | Target chỉ cho metadata_list đúng scope; refcount/checksum đúng | Quyền ngoài scope, denial sai, crash hoặc data/refcount mismatch | OSD-013/014 |
| T23 — CephFS conditional | Base client↔target MDS và ngược lại; failover/retry/remount/session/perf v2 | Decode/session/failover hội tụ; consumer v2 đúng và fresh | Client stuck, decode fault, eviction sai hoặc parser hỏng | MON-005, MSG-008, CFG-003, MGR-008 |
| T24 — RGW/RBD conditional | Vault encrypt/decrypt với cert thật; notify/quota/pool-create/multi-delete; mirror backlog | Request thành công và telemetry/backlog trong guardrail | Vault TLS fail, timeout/retry bất thường hoặc backlog tăng ngoài guardrail | CFG-004 |
| T25 — Stretch conditional | Site degrade/recover và tiebreaker/rule validation trong lab | Quorum/placement/failback đúng | Topology/weight/rule sai hoặc recovery không hội tụ | MON-007 |

### 6.3 Full target / stabilization

- [ ] Mọi daemon trong scope đã ở target và service-map/quorum ổn định.
- [ ] Đối chiếu OSD offline trước khi xử lý OSD_UPGRADE_FINISHED; không tự nâng release flag để clear WARN. [MON-002]
- [ ] Xác minh OSDMap trim tiến, pg_temp/upmap cleanup không tạo recovery spike và MON store/free space ổn định. [MON-006/009]
- [ ] Chạy correctness test OMAP iterator/range-delete trên fixture đại diện; tập key/header phải giống và range phải đúng [start,end). [KVBD-001/002]
- [ ] Trong lab tương đồng Production, test BlueFS crash durability, deferred replay và DB/WAL topology; replay, fsck, checksum và DB reopen phải sạch. [BS-002/003/006]
- [ ] So effective config theo role/location, xử lý stale key chỉ sau khi rollback mapping đã PASS. [MON-011, CFG-007]
- [ ] Đối chiếu autoscaler recommendation/action, progress output và PG/OSD recovery counters; không dùng ceph progress làm tín hiệu duy nhất. [MGR-004/009]
- [ ] Chỉ sau Prometheus gate mới reload bộ rules target; xác nhận runtime checksum, reload success, pending/firing và notification destination. [MGR-005/006/010]
- [ ] Nếu dự định dùng CIDR range blocklist, test add/list/enforce/expire/remove, offline-OSD rejoin và rollback trên disposable lab; nếu thiếu bằng chứng, tiếp tục để feature unused. [MON-001, MSG-007]
- [ ] So baseline trước/sau cho latency, error, recovery, CPU/RSS, disk, network, MON DB, MGR và monitoring theo guardrail đã định.
- [ ] Hoàn thành soak time, không có sự cố mới hoặc trend xấu chưa giải thích.

## 7. Gate rollout theo role

> Thứ tự dưới đây là **gate logic từ 00–07**, chưa phải procedure cephadm hay thứ tự daemon cuối cùng. Lệnh/orchestration, stop/resume và lifecycle sẽ được bổ sung từ phần 08.

### R0 — Trước first target daemon

- [ ] G00–G07 áp dụng đã PASS hoặc có exception được đúng owner ký.
- [ ] T02 device alias đã PASS. Với rollback OSD, T01 đã PASS **hoặc** forward-only/rebuild strategy đã được phê duyệt và rehearsal; với monitoring, T04 đã PASS **hoặc** Prometheus không phải stop/go và telemetry độc lập đã được verify.
- [ ] Backup/snapshot/config/map artifacts có checksum và đã thử restore ở mức phù hợp.
- [ ] Change freeze và stop conditions đã được truyền đạt.

### R1 — MON canary

- [ ] Quorum, rank, leader, MON store và network/clock ổn định.
- [ ] Target follower ổn định trước leader transition trong rehearsal.
- [ ] CephX rotation, MonClient reconnect và MON↔MGR edge đã PASS.
- [ ] Nếu còn base MGR, ms_die_on_bad_msg là false/default và canary không có abort/reset loop hoặc metadata stale không hội tụ.
- [ ] Không bật CIDR range state, không thay MonMap topology và không nâng release flag trong canary.

### R2 — MGR standby và controlled promotion

- [ ] Target standby load/can-run, service URI và config parity ổn định.
- [ ] Prometheus parser được kiểm **trước tiên** sau target promotion.
- [ ] Custom notify, Dashboard TLS/API, metric schema/LB và autoscaler diff đã PASS.
- [ ] Failback target ↔ base đã được rehearsal nếu MGR rollback nằm trong runbook.

### R3 — OSD canary

- [ ] Chọn một OSD đại diện mỗi media/layout/host/class mà không phá failure-domain safety.
- [ ] Device ownership, allocator config, mClock policy và effective location mask đã PASS.
- [ ] Mount/replay sạch; PG peering/recovery/scrub và client workload trong guardrail.
- [ ] Không dùng package-only downgrade nếu OSD đã ghi BlueFS target.

### R4 — Mở rộng mixed fleet

- [ ] Mỗi batch chỉ mở sau soak và review evidence của batch trước.
- [ ] Cố ý quan sát primary base và target, không chỉ nhìn cluster health tổng.
- [ ] Không có unexplained PG state, checksum mismatch, daemon loop, reset storm hoặc recovery spike.
- [ ] Monitoring stop/go vẫn độc lập và đáng tin cậy.

### R5 — Full target và stabilization

- [ ] Hoàn thành mục 6.3.
- [ ] Mọi external consumer/rule/runbook đã chuyển đổi hoặc được giữ ở phiên bản tương thích có chủ đích.
- [ ] Chỉ kích hoạt capability mới sau checkpoint rollback riêng.
- [ ] Chưa tuyên bố GO Production cuối cho tới khi 08–15 được ghép.

## 8. STOP conditions và phạm vi bị chặn

Dừng batch hiện tại ngay khi có một trong các dấu hiệu sau:

- Mất quorum, election loop, Paxos không catch-up hoặc MON store chạm guardrail.
- OSD mount/replay fail, unrecognized BlueFS op ở đường rollback, assert/coredump hoặc restart loop.
- Checksum/data/refcount/key-cardinality mismatch.
- PG mới chuyển incomplete/inconsistent/unfound, peering/scrub stuck hoặc recovery vượt guardrail mà chưa giải thích.
- Hai writer có thể mở cùng block device, hoặc ownership device không còn chắc chắn.
- mClock benchmark ngoài kế hoạch, boot time/I/O vượt guardrail hoặc capacity bị persist sai.
- Messenger hang, stuck thread, reset storm, auth loop hoặc MGR unknown-message fatal.
- MGR/module callback im lặng, service-map không hội tụ hoặc autoscaler tạo PG action bất ngờ.
- Prometheus parse/scrape fail mà không còn nguồn telemetry độc lập đã duyệt.
- Dashboard/API, CephFS, RGW Vault hoặc business-critical consumer fail ở path đang được nâng.
- Alert route/silence/notification sai sau reload.

Khi STOP:

1. Không mở rộng sang batch/role tiếp theo.
2. Giữ log, map/config dump, metrics và image/clone liên quan; không repair để “thử”.
3. So với baseline và xác định lỗi đã có trước hay do phase vừa thực hiện.
4. Chọn forward-fix, failback role hoặc restore state theo ma trận rollback; không mặc định hạ package OSD.
5. Chỉ resume sau khi owner tương ứng ký PASS mới.

## 9. Rollback: có thể hay không?

**Trả lời ngắn:** có thể rollback một số role/config, nhưng **không có một rollback package-only chung cho toàn cluster**. BlueFS tạo ranh giới theo từng OSD; state mới, config ngoài Ceph và external monitoring cần rollback riêng.

| Đối tượng | Mức | Điều kiện và giới hạn |
| --- | --- | --- |
| Messenger/local runtime fixes | Có điều kiện | Không có migration bền vững được chứng minh; failback trả lại race/default cũ |
| MGR binary active ↔ standby | Có điều kiện | Phải rehearsal service-map, module events, metrics/schema, Dashboard và consumer behavior |
| MON 16.2.15 → 16.2.5 | Có điều kiện | Quorum-safe failback và state decode phải test; FSMap/state mới cần kiểm riêng |
| require_osd_release=pacific | Không chặn cặp patch này | Cả hai endpoint là Pacific; flag vẫn one-way đối với OSD pre-Pacific và command không cho hạ |
| OSD sau target mount/BlueFS write | **Không an toàn bằng package-only downgrade** | Base reader không hiểu opcode mới và có thể -EIO; cần restore image/device snapshot đã test hoặc forward-only/rebuild plan |
| OSD superblock lower bound | Có điều kiện, cần rehearsal | Target persist cluster_osdmap_trim_lower_bound trong OSDSuperblock v10 với compat 5; base có thể decode nhưng old-writer round-trip sau downgrade chưa được chứng minh. Test clone theo chuỗi downgrade → ghi lại → re-upgrade trước khi coi an toàn |
| CIDR range-blocklist đã tạo | Boundary mạnh | OSDMap có state/encoding mới; giữ unused cho tới khi rollback rehearsal chứng minh procedure |
| Config rename/default | Có điều kiện | Cần snapshot config DB và mapping old↔new; base có thể không hiểu target-only key hoặc lại cần key cũ |
| Alert/Prometheus/Dashboard config | Có thể nếu có artifact | Binary rollback không tự phục hồi 18 rule cũ, routes, silences, query schema hoặc LB selection |
| Repair/quick-fix/migrate/import/reshard/set-superblock | Không phải rollback thường lệ | Restore pre-action image; không chain repair trên state lỗi |

### 9.1 Checklist rollback readiness

- [ ] Chọn một trong hai strategy cho OSD: restoreable snapshot/image **hoặc** forward-only/rebuild được phê duyệt.
- [ ] Chứng minh restore trên clone, không chỉ chứng minh snapshot tạo thành công.
- [ ] Lưu MonMap, OSDMap, CRUSH map, FSMap nếu dùng CephFS, config DB và effective config baseline.
- [ ] Lưu package/image repository cần cho failback và xác minh artifact.
- [ ] Lưu rules, routes, silences, Dashboard/LB và custom module artifact tương thích base.
- [ ] Định nghĩa role nào được failback, role nào chỉ forward-fix và ai có quyền quyết định.
- [ ] Không tạo CIDR range state hoặc state/tool mutation mới trước rollback checkpoint.
- [ ] Sau rollback, chạy lại health/quorum/PG/data-path/client/monitoring acceptance; rollback command thành công chưa phải rollback hoàn tất.

## 10. Gói bằng chứng và sign-off

| Hạng mục | Owner | Kết quả | Bằng chứng | Ký/ngày |
| --- | --- | --- | --- | --- |
| Artifact/source | | | | |
| As-Is health/topology | | | | |
| MON quorum/store/maps | | | | |
| OSD/PG/recovery/scrub | | | | |
| BlueStore/BlueFS/RocksDB/device | | | | |
| Config migration/effective values | | | | |
| MGR/custom modules/autoscaler | | | | |
| Prometheus parser + independent telemetry | | | | |
| Dashboard/TLS/API | | | | |
| CephFS conditional | | | | |
| RGW/RBD conditional | | | | |
| Lab test matrix | | | | |
| Canary/soak evidence | | | | |
| Rollback rehearsal | | | | |
| Exception/risk acceptance | | | | |

## 11. Gợi ý thu thập read-only

Các lệnh dưới đây chỉ là ví dụ thu thập trạng thái; phải review quyền truy cập, output chứa thông tin nhạy cảm và cách lưu bằng chứng của môi trường. Chúng không bao phủ device/LVM activation hay cephadm workflow của phần 08–09.

    ceph -s
    ceph health detail
    ceph versions
    ceph quorum_status -f json-pretty
    ceph mon dump -f json-pretty
    ceph osd dump -f json-pretty
    ceph osd tree -f json-pretty
    ceph osd df tree -f json-pretty
    ceph pg stat
    ceph config dump -f json-pretty
    ceph mgr dump -f json-pretty
    ceph mgr module ls -f json-pretty
    ceph osd pool autoscale-status
    ceph fs dump -f json-pretty

Không đưa lệnh repair, trim, mark-lost, map rewrite, config set, feature enable hay daemon upgrade vào phần này.

## 12. Phần còn thiếu sẽ bổ sung ở lần 2

Các mục sau cố ý chưa được dùng để đưa ra GO/NO-GO trong phiên bản checklist này:

- 08 — cephadm/orchestrator: thứ tự và cơ chế upgrade, stop/resume, daemon lifecycle, registry/image và rollback orchestration.
- 09 — ceph-volume/activation: inventory thiết bị, LVM/raw activation, dm-crypt, DB/WAL và restart activation.
- 10 — RADOS/RBD clients: client matrix, snapshot/diff/object-map, cache và compatibility.
- 11 — CephFS/MDS đầy đủ.
- 12 — RGW đầy đủ.
- 13 — build/package/submodule/dependency.
- 14 — security/CVE cross-reference.
- 15 — validation tổng hợp và quyết định release cuối.

Khi bổ sung lần 2, giữ nguyên ID gate/test hiện có, thêm dependency và blocker mới, rồi cập nhật trạng thái G08. Không được diễn giải checklist 00–07 này là phê duyệt Production trước bước đó.
