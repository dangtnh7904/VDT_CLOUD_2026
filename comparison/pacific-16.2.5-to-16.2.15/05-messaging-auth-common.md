# 05 — Messaging, auth, common runtime và encode/decode: v16.2.5 → v16.2.15

> **Trạng thái:** hoàn thành phân tích code-level cho owner `05-messaging-auth-common`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), dựa trên endpoint net diff trực tiếp trong `ceph16.2.15/ceph` và lịch sử commit nằm giữa hai tag.
>
> **Danh sách file đầy đủ:** [05-messaging-auth-common.csv](./05-messaging-auth-common.csv). Báo cáo này chỉ đọc source/test; không chạy unit test, daemon, cluster command, fault injection hay workload.

## 1. Phạm vi, phương pháp và độ phủ

CSV của component giữ nguyên thứ tự inventory và có **92 dòng**: `A 3`, `M 89`, tổng `+1.508/-652`; theo reading priority có `P0 8`, `P1 73`, `P2 11`; theo loại có `runtime/source 77`, `test/QA 11`, `build/package 4`. `P0/P1/P2` chỉ là thứ tự đọc, không phải risk rating.

Phạm vi gồm CephX/keyring; common runtime; message definitions và encode/decode; AsyncMessenger/ProtocolV1/ProtocolV2/network stack; logging; cùng test trực tiếp của các vùng đó. Các owner khác vẫn là nguồn ngữ cảnh, không được nhập lại vào CSV:

- `AuthMonitor`, quorum và MON state thuộc report `04-mon-osdmap-crush`;
- OSD restart, PG/map handling thuộc `01-osd-pg-recovery`;
- định nghĩa/default option thuộc `06-config-defaults`;
- CephFS, MGR, RGW behavior phía service thuộc report tương ứng; report này chỉ sở hữu message/common-runtime contract.

Markdown áp dụng upgrade-relevance gate: chỉ nâng thành finding khi code có đường nhân quả cụ thể tới rolling mixed-version, restart, protocol/encoding, authentication, data correctness, availability, rollback hoặc tín hiệu validation. Client/frontend, build portability, refactor, logging và test-only vẫn còn đầy đủ trong CSV nhưng chỉ được tổng hợp nếu không vượt gate. Mỗi dòng CSV được gán đúng một final disposition ở mục 7; tổng phải khớp `92/92`.

## 2. Kết luận điều hành

| ID | Hành vi có liên quan nâng cấp | Rủi ro/hậu quả | Khả năng áp dụng | Evidence confidence |
| --- | --- | --- | --- | --- |
| `MSG-001` | CephX chỉ đưa rotating keys vào live state sau khi proposal Paxos đã commit | Cao nếu trúng cửa sổ rotation/leader change | Có điều kiện; phụ thuộc timing rotation và MON leader đang chạy version nào | `high` |
| `MSG-002` | AsyncMessenger/ProtocolV2 sửa shutdown wait, connection unregister, deadlock và frame-assembler race | Cao về availability khi reconnect/shutdown đồng thời | Trung bình trong rolling vì restart tạo connection churn; đường race vẫn phụ thuộc timing | `high` |
| `MSG-003` | OSD restart/fast-shutdown tránh OpTracker coredump, truyền “down and dead”, và giảm timeout giả khi map | Cao cho crash; trung bình cho liveness/validation | Có điều kiện theo inflight op, fast-shutdown và map remap | `high` |
| `MSG-004` | Buffer alignment và RGW file-handle LRU bỏ hai đường SIGABRT/double-unlock | Cao nếu kích hoạt, không phải migration | Thấp–trung bình; phụ thuộc hình dạng buffer hoặc RGW file/NFS workload | `high` |
| `MSG-005` | AArch64 CRC clobber và FIPS/OpenSSL MD5 path sửa lỗi nền tảng | Cao cho checksum/service continuity ở đúng nền tảng | Chỉ AArch64 GCC 8.3 path hoặc RGW + FIPS/OpenSSL tương ứng | `high` |
| `MSG-006` | Chọn địa chỉ, CRUSH location hook và MON weighted shuffle tránh startup/connect sai hoặc abort | Trung bình–cao theo cấu hình | Chỉ auto-address, custom hook hoặc MON weight có số 0 | `high` |
| `MSG-007` | CIDR range-blocklist có type/feature mới và gate theo MON quorum + OSD đang up | Cao nếu kích hoạt quá sớm hoặc giả định rollback | Chỉ khi operator dùng blocklist dạng CIDR | `high` cho code; `medium` cho rejoin/rollback chưa test |
| `MSG-008` | CephFS request retry/forward mở rộng 8→32 bit nhưng giữ legacy encoding; session reject thêm versioned flag | Trung bình cho mixed client/MDS continuity | Chỉ deployment CephFS, rõ nhất khi retry/fwd hoặc recover-session | `high` cho encoding; `medium` cho matrix client thực |
| `MSG-009` | Target MON có message `MMgrUpdate` mà MGR base không biết | Thấp mặc định; cao nếu bật `ms_die_on_bad_msg=true` | Mixed MON-target/MGR-base khi metadata version cần cập nhật | `high` cho decode path; `medium` cho tần suất ngoài lab |

Không có một lần “migrate messenger format” chung cho toàn component. Phần lớn fix có hiệu lực ngay khi process target restart. Hai ngoại lệ cần chủ động coi là mixed-version contract là `MSG-007` (feature-gated OSDMap data) và `MSG-008`/`MSG-009` (message version/type khác giữa peer).

## 3. Findings chi tiết

### MSG-001 — Rotating CephX keys chỉ thành live state sau Paxos commit

**Owner/evidence.** Inventory `1097–1098` (disposition `mixed`), `KeyServer::updated_rotating` ở base `src/auth/cephx/CephxKeyServer.cc:359` và `KeyServer::prepare_rotating_update` ở target `:344`; commit `6619e2052580ca372899c942b122c524fd6686b9`. `src/mon/AuthMonitor.cc` là context của owner `04`.

**Trước → sau.** Base gọi `_check_rotating_secrets()` trên chính `KeyServer::data`, tăng `rotating_ver`, rồi mới nhét state vừa mutate vào proposal. Vì live state đã đổi trước khi Paxos commit, leader/quorum transition hoặc proposal không được commit có thể để key được phát cho daemon lệch với committed state. Target clone `data.rotating_secrets` sang `pending_data`, rotate và encode bản clone; live `KeyServer::data` chỉ đổi qua đường apply incremental đã commit. Commit mô tả trực tiếp failure mode là stale/divergent keys giữa MON và daemon.

**Kích hoạt và hiệu lực.** Tự động khi MON leader thấy secret đến kỳ rotate; không cần config migration hay regenerate keyring. Hunk không đổi format của `KeyServerData::Incremental`, nên đây là state-ordering fix chứ không phải on-disk/wire migration.

**Mixed/full/rollback.** Khi leader còn là `16.2.5`, semantics cũ vẫn tồn tại; khi target làm leader, proposal mới an toàn. Vì vậy nên hoàn tất/canary quorum MON và quan sát leader/rotation trước khi kết luận fix đã bao phủ. Sau khi toàn MON ở target, mọi leader dùng pending-copy path. Code không cho bằng chứng rằng cần rollback dữ liệu auth, nhưng một incident key divergence có sẵn vẫn cần chẩn đoán riêng, không được coi là tự chữa chỉ bằng package upgrade.

**Tác động và độ chắc chắn.** Category: authentication/correctness/availability. Hậu quả tiềm năng cao (ticket/key không đồng bộ), likelihood chưa biết vì thiếu lịch rotation và election của cluster. Evidence confidence `high` từ endpoint, caller và commit intent; applicability confidence `medium` vì không có As-Is timing.

**Test đã đọc.** Không tìm thấy regression test chuyên biệt cho proposal/leader-change trong changed test inventory hay repository search. Cần lab ép rotation quanh election và xác nhận các MON chỉ phát key version đã commit; chưa chạy.

### MSG-002 — Messenger reconnect và shutdown bỏ deadlock/race tại đúng ownership thread

**Owner/evidence.** Inventory `1533` (`material`), `1534` và `1537` (`mixed`). Symbols: `AsyncMessenger::wait` base/target `src/msg/async/AsyncMessenger.cc:548`, `AsyncMessenger::unregister_conn`/`reap_dead`, `ProtocolV2::handle_existing_connection` base `:2527` → target `:2523`, và `ProtocolV2::reuse_connection` base `:2628` → target `:2626`. Commits:

- `45882632a172f3800360740af1dc3ff0b94030a0`: không đọc `accepting_conns`/`anon_conns` khi chỉ giữ `deleted_lock`; dời decrement active-connection counter sang các điểm thật sự remove;
- `c09a9a25668753dbb89377fb08c43006264f1681`: đổi `if (!stopped) wait` thành `while (!stopped) wait`, chịu được spurious wakeup;
- `244b6a161ce62fc05431f772ee71c3386b791667`: dùng `unique_lock` và nhả connection lock trước `send_server_ident()` ở existing connection đã closed/lossy, cắt lock inversion với `shutdown_connections`;
- `d05861d831f864ff33cd34e2a0f844ee056dc0f7`: reset tx/rx frame assembler trong lambda chạy ở event-center/write thread thay vì thread hiện tại;
- `afbe64650dcdca5ce8ce13988efb0fcf2e75ac89`: expose reap threshold; default endpoint vẫn `5`, phần option thuộc report `06`.

**Trước → sau.** Base có bốn failure mode độc lập nhưng cùng activation: accounting đọc collection không được bảo vệ đúng lock; `wait()` có thể tiếp tục teardown khi chưa thật sự stopped; v2 reconnect giữ connection lock rồi đợi messenger lock trong khi shutdown giữ thứ tự ngược; và `set_is_rev1()` clear internal assembler state ngoài thread đang write. Target sửa lock ownership, condition-loop và thread affinity mà không đổi frame encoding hay feature negotiation.

**Kích hoạt và hiệu lực.** Tự động sau restart target. Deadlock/frame race cần msgr2, existing connection reuse/reconnect và timing đồng thời; shutdown-wait/unregister áp dụng rộng hơn cho AsyncMessenger. Rolling upgrade tự tạo peer restarts và reconnect nên đường nhân quả với cửa sổ upgrade là trực tiếp, dù race không tất định.

**Mixed/full/rollback.** Fix bảo vệ endpoint đang chạy target; peer base vẫn có implementation/race local của nó. Một connection target↔base vì vậy không đồng nghĩa cả hai phía đã an toàn. Full upgrade mới đồng nhất lifecycle. Không có persistent state hay migration, nên package rollback không cần chuyển đổi frame do finding này; rollback chỉ đưa race cũ trở lại.

**Tác động và độ chắc chắn.** Category: availability/concurrency/compatibility. Consequence cao (daemon hang, reconnect fault hoặc teardown sai), likelihood trung bình-thấp theo timing, applicability cao nếu dùng msgr2. Evidence confidence `high`; chưa có số reconnect/reset thực tế của cluster.

**Test đã đọc.** `src/test/msgr/test_msgr.cc` có `ConnectionRaceTest`, `ConnectionRaceReuseBannerTest`, `ReconnectTest`, `ReconnectRaceTest` và synthetic stress/inject cases. Các responsible commits trên không thêm một regression test cô lập đúng deadlock/frame reset; cần lab mixed-version với peer restart, network flap và concurrent daemon shutdown. Không chạy test.

### MSG-003 — OSD lifecycle: reboot không coredump, fast shutdown báo đúng, timeout map không còn giả

**Owner/evidence.** Inventory `1215` và `1460` (`material`), `1216` (`conditional`). Symbols `OpTracker::~OpTracker` base/target `src/common/TrackedOp.cc:171`, `ThreadPool::worker` `src/common/WorkQueue.cc:81`, `MOSDMarkMeDown::HEAD_VERSION` base `3` → target `4` tại `src/messages/MOSDMarkMeDown.h:22`. Commits `0c2bdd7dc81dcdb4a95189576daa04f76d8e7ca9`, `b6f0324b157da99846a5cfd0ca11fabe2b51f99d`, `d07efdf464e814ec710798ecb34ce8b360481daf`. OSD/MON callers thuộc reports `01`/`04`.

**Trước → sau.** Base destructor assert danh sách shard trống nhưng không drain outstanding tracked ops, đúng failure được commit gọi là “osd reboot optracker coredump”; target khóa từng shard và pop trước delete. Fast-shutdown message tăng version `3→4`, giữ `COMPAT_VERSION=3`, thêm `down_and_dead`; target OSD gửi `true`, target MON ghi `dead_epoch` thay vì chỉ mark down. Riêng temporary `ParallelPGMapper::WQ`, base dùng grace `0` khiến heartbeat phát `cpu_tp timeout`; target dùng `threadpool_default_timeout`, tránh tín hiệu lỗi giả khi map worker đang chờ.

**Kích hoạt và hiệu lực.** OpTracker tự động khi OSD teardown còn tracked op. `down_and_dead` chỉ áp dụng khi fast-shutdown/notify-MON path được bật và OSD đang up. WorkQueue signal xuất hiện khi OSD map mapping/remap bận trong restart. Không có data migration hay repair.

**Mixed/full/rollback.** Target OSD + target MON nhận full semantics. Từ `COMPAT_VERSION=3`, target decoder có guard `header.version >= 4`; generic message compatibility cho phép receiver chỉ hỗ trợ v3 nhận message compat3 và bỏ tail, nên target OSD + base MON suy ra vẫn down được nhưng không hiểu `down_and_dead`. Đây là inference code-level, chưa có matrix test. MON-first làm semantics mới sẵn sàng trước OSD rollout. Base OSD vẫn có destructor cũ cho tới khi chính nó được nâng.

**Tác động và độ chắc chắn.** Category: availability/liveness/detectability. Crash consequence cao nhưng timing conditional; liveness và timeout giả có consequence trung bình vì ảnh hưởng failover/recovery timing hoặc quyết định stop/go. Evidence confidence `high`; mixed decoder behavior `medium-high` do chưa chạy wire test.

**Test đã đọc.** Không tìm thấy test trực tiếp cho ba responsible commits. Lab cần restart OSD dưới inflight I/O, xác nhận không coredump; bắt `MOSDMarkMeDown` ở base/target MON; và theo dõi heartbeat khi consume map lớn. Chưa chạy.

### MSG-004 — Hai lỗi memory/lock safety có thể làm daemon abort

**Owner/evidence.** Inventory `1219`, `1224` (`conditional`) và regression-test support `2398`. Symbols `buffer::list::rebuild_aligned_size_and_memory` base/target `src/common/buffer.cc:1206`, `cohort::lru::LRU::evict_block` base/target `src/common/cohort_lru.h:137`. Commits `ae7366f7bd363c178dd8d9eb1a0a5c1f3c91cbb3` và `b25e48805fe0fa8d0dcb3e73c411f68d03d518ac`.

**Trước → sau.** Với bufferlist có tổng mọi ptr trước cuối đã 4 KiB-aligned và ptr cuối dài 0, base rebuild tạo `unaligned` không có buffer nhưng vẫn lấy `front()`, gây stack corruption/SIGABRT. Target chỉ insert khi `get_num_buffers()>0`. Callers target gồm kernel/zoned block device, BlueStore label và EC alignment; finding không khẳng định mọi caller đều tạo shape đặc biệt này. Trong `cohort_lru`, base manual unlock sau reclaim thành công rồi lại đi qua unlock cuối scope; target dùng `std::unique_lock`, tránh double `pthread_mutex_unlock`. Caller thực tế là RGW file-handle LRU (`src/rgw/rgw_file.h`).

**Kích hoạt và hiệu lực.** Tự động ở binary target; không đổi wire/disk format. Buffer bug cần shape zero-tail chính xác; LRU bug cần reclaim thành công ở RGW file/NFS path. Dữ liệu đã ghi không được “migrate”; target chỉ tránh crash ở lần thực thi kế tiếp.

**Mixed/full/rollback.** Hoàn toàn local theo process/caller, không cần peer đồng phiên bản. Nâng OSD chứa buffer fix; nâng RGW/NFS process chứa LRU fix. Rollback khôi phục code path cũ, không đòi downgrade metadata.

**Tác động và độ chắc chắn.** Category: availability/correctness. Consequence cao nếu SIGABRT/double-unlock; likelihood/applicability thấp–trung bình và cần workload inventory. Evidence confidence `high` từ hunk và reproducer; chưa chứng minh cluster hiện tại từng tạo input này.

**Test đã đọc.** `src/test/bufferlist.cc::BufferList.rebuild_aligned_size_and_memory` thêm reproducer zero-length tail. Không có test mới cho `cohort_lru` double-unlock; test LRU hiện hữu chỉ là context. Chưa chạy.

### MSG-005 — Điều kiện nền tảng: AArch64 CRC và RGW FIPS/OpenSSL

**Owner/evidence.** Inventory `1228`, `1220–1221` (`conditional`). Symbols `ceph_crc32c_aarch64` base/target `src/common/crc32c_aarch64.c:93`, `ssl::OpenSSLDigest::SetFlags` chỉ có ở target `src/common/ceph_crypto.cc:208`. Commits `c94c76bb6ac57576e014d6d394a710dc08482812`, `07fe774e8947656662fa524567d42d5992552646`, `aa150d876693559ee0d3737def0ebd0cddd4735c`.

**Trước → sau.** Trên CentOS 8.2 AArch64/GCC 8.3, inline asm base không khai báo vector registers `v0–v3` là clobber, cho phép compiler tái dùng và làm CRC unittest sai; target khai báo đầy đủ. Với RGW chạy FIPS, target thêm `EVP_MD_CTX_FLAG_NON_FIPS_ALLOW` path cho OpenSSL 1.x và, ở OpenSSL 3.x, fetch MD5 với property `fips=no` cho các MD5 dùng không nhằm mục đích mật mã (ETag, bucket/crypto helper và các RGW paths). Base thiếu hai cơ chế này.

**Kích hoạt và hiệu lực.** CRC chỉ áp dụng AArch64 build dùng nhánh asm/crypto tương ứng; không suy rộng sang x86. FIPS chỉ áp dụng RGW + FIPS, và OpenSSL 3 branch thường đi cùng OS/library refresh. Cả hai tự có sau binary restart, không đổi Ceph protocol. RGW behavior phía service thuộc report RGW; common crypto implementation do report này sở hữu.

**Mixed/full/rollback.** Local theo process/CPU/library. Một fleet mixed architecture có thể cho kết quả CRC path khác; cần compare known vectors, không suy luận silent corruption từ commit duy nhất. RGW instances base vẫn có failure cũ tới khi từng instance được nâng. Rollback không cần data conversion nhưng có thể làm FIPS request fail trở lại.

**Tác động và độ chắc chắn.** Category: correctness/integrity/availability. Consequence cao ở đúng nền tảng; applicability thấp nếu x86/non-FIPS, chưa biết vì thiếu inventory. Evidence confidence `high`; confidence về hậu quả production của CRC là `medium` vì commit chứng minh unittest failure chứ không chứng minh một corruption incident.

**Test đã đọc.** `src/test/common/test_crc32c.cc` có known vectors và direct `ceph_crc32c_aarch64`; `src/test/ceph_crypto.cc` có MD5 tests nhưng không dựng FIPS/OpenSSL matrix. Chưa chạy.

### MSG-006 — Startup/binding và MON hunt an toàn hơn ở cấu hình biên

**Owner/evidence.** Inventory `1230–1231`, `1237–1238`, `1240` (`conditional`); support `1234`, `1257`, `2547`. Symbols `find_ip_in_subnet_list` base `src/common/pick_address.cc:40` → target `:147`, `EntityName::get_type_str` base/target `src/common/entity_name.cc:110`, `weighted_shuffle` base/target `src/common/weighted_shuffle.h:11`. Commits `a61d71dcc868a1100aab1572a8a039e077cad3dd`, `dcb4107c0959320e82e67937cc9176bee52cecf1`, `a64443aaeec78ebd53e41e646d65d30232b5b68f`; direct weighted test commit `c8eabba6cd09891fcabd91c52a4f0cf20fffc062` nằm ngoài owner CSV.

**Trước → sau.** Base loại interface theo tên `lo`/`lo:*` rồi lấy match đầu; target grade address, ưu tiên interface `IFF_UP` và non-loopback theo địa chỉ IPv4/IPv6. Tùy chọn trung gian `ms_bind_exclude_lo_iface` được thêm rồi loại trong chính range, nên **không** phải target option. Base trả `std::string_view` từ `EntityName::get_type_str()` nhưng truyền qua varargs `SubProcess::add_cmd_args`; custom `crush_location_hook` có thể đọc length như `char*` và SIGSEGV. Target trả `const char*`. Cuối cùng, recursive weighted shuffle có thể còn toàn weight 0 sau khi chọn phần tử nonzero và làm `std::discrete_distribution` assert; target dừng recursion khi tổng còn lại bằng 0. Caller quan trọng là `MonClient::_add_conns()` khi chọn MON cùng priority.

**Kích hoạt và hiệu lực.** Address selection chỉ đổi khi address còn blank và daemon tự chọn từ network/interface list. Hook fix chỉ khi cấu hình `crush_location_hook`. Shuffle fix cần nhiều MON cùng priority và weight distribution có zero remainder (đặc biệt một weight dương, còn lại 0). Tất cả local/automatic sau restart, không đổi map format.

**Mixed/full/rollback.** Daemon/client target tự chọn/bind/hunt theo rule mới; peer không cần target. Trong rolling, từng daemon có thể quảng bá address được chọn khác nếu config mơ hồ, nên phải so advertised `public_addr/cluster_addr` trước và sau canary. MON weight fix bảo vệ từng MonClient target; base clients/daemons vẫn có thể abort trên cùng map weights.

**Tác động và độ chắc chắn.** Category: availability/connectivity/configuration. Consequence trung bình–cao, likelihood conditional; evidence confidence `high`. Applicability chưa biết vì thiếu interface state, explicit addresses, hook và MON weight inventory.

**Test đã đọc.** `src/test/test_ipaddr.cc` kiểm IPv4/IPv6 ưu tiên non-loopback và chọn loopback `UP` khi subnet chỉ còn lựa chọn đó. `src/test/test_weighted_shuffle.cc::{ZeroedWeights,SingleNonZeroWeight}` chạm đúng recursive zero remainder. Không có test hook trực tiếp. Chưa chạy.

### MSG-007 — Range-blocklist là feature mới; command gate không thay thế full-fleet audit

**Owner/evidence.** Inventory `1246` (`material`) và `1545` (`mixed`). `CEPH_FEATURE_RANGE_BLOCKLIST` chỉ có ở target `src/include/ceph_features.h:135`; `entity_addr_t::TYPE_CIDR` ở target `src/msg/msg_types.h:261`. Commits `4ce530be32c73f6cc0bff917a59ce5ffddc8255c`, `fd4a577317b7bb84168afca2a574513c0d823aac`. `OSDMonitor::check_cluster_features` và OSDMap range storage/enforcement thuộc owner `04`.

**Trước → sau.** Base không có address type CIDR hay feature bit. Target dùng `TYPE_CIDR=4`, tái dùng `nonce` để giữ prefix length, và thêm feature vào supported set. Khi command add blocklist nhận CIDR, target OSDMonitor gọi `check_cluster_features(CEPH_FEATUREMASK_RANGE_BLOCKLIST)`: code kiểm toàn MON quorum, mọi OSD **đang up**, và pending OSD xinfo; nếu thiếu trả `-ENOTSUP`/`-EAGAIN` thay vì publish range entry.

**Kích hoạt và hiệu lực.** Không tự kích hoạt do upgrade. Chỉ có hiệu lực khi operator thêm blocklist dạng CIDR; blocklist địa chỉ đơn vẫn theo path cũ. Đây là wire/map capability, không phải một migration bắt buộc khi lên `16.2.15`.

**Mixed/full/rollback.** Trong rolling bình thường có OSD base đang up, command CIDR phải bị gate. Gate code không chứng minh coverage của OSD base đang down/maintenance, mọi client consumer, hoặc rollback sau khi range entry đã xuất hiện. Vì thế chỉ enable sau khi audit **toàn bộ** daemon kể cả offline và test rejoin; không được coi “command đã thành công” là bằng chứng rollback-safe. Sau full target, MON/OSD hiểu feature; semantics map chi tiết và cleanup/expiry xem report `04`.

**Tác động và độ chắc chắn.** Category: compatibility/security/availability. Consequence cao nếu một consumer không enforce hoặc không decode; likelihood bằng 0 nếu không dùng CIDR command. Evidence confidence `high` cho gate và type, `medium` cho full consumer/rollback vì chưa có live matrix.

**Test đã đọc.** `src/test/osd/TestOSDMap.cc` có range add/remove/swap và IPv4/IPv6, gồm `/0`; đây là context owner `04`, không phải mixed `16.2.5↔16.2.15` test. Chưa chạy.

### MSG-008 — CephFS retry/forward counter mở rộng nhưng giữ đường legacy

**Owner/evidence.** Inventory `1454` (`material`), `1247` (`mixed`), `1455` (`conditional`). `CEPH_MDS_REQUEST_HEAD_VERSION` base `1` tại `src/include/ceph_fs.h:617` → target `2` tại `:625`; `MClientRequest::encode_payload` base `src/messages/MClientRequest.h:245` → target `:252`; `MClientSession::HEAD_VERSION` base `4` → target `5` tại `src/messages/MClientSession.h:23`. Commits:

- `2f1fb9d14cdb6f4dbc508aae1277e4e11714ae11`: tách encode/decode helper làm tiền đề;
- `1c2334b778b18719fd259d44d60fc3cd8e19a2a4`: thêm `ext_num_retry/ext_num_fwd` 32 bit và peer-old path;
- `6143404acb92e5075ebfc6e33b3a50fdfc86d02e`: zero-init request head, sửa regression được đưa vào giữa hai endpoint;
- `a8a5530243a5eb8a4c92787b1cb51f2d1102906a`: khi decode legacy head, copy 8-bit counters sang extended fields;
- `80e16e3bbd4991b5f698c299301dafe4216443dc`: thêm versioned `SESSION_BLOCKLISTED` flag.

**Trước → sau.** Base chỉ có 8-bit retry/fwd. Target luôn điền legacy byte từ extended counter, chỉ append hai field 32-bit khi peer quảng bá `CEPHFS_FEATURE_32BITS_RETRY_FWD`; decoder v1 copy byte cũ sang extended. Follow-up target còn xử lý `ceph_mds_request_head_legacy` và zero-init default constructor, nên không được báo cáo regression trung gian như lỗi của endpoint `16.2.15`. Với session reject, target v5 append `flags`; decoder chỉ đọc khi version `>=5`, trong khi sender vẫn hạ header về v1 khi không gửi metadata/features để tránh làm old kernel client khó chịu.

**Kích hoạt và hiệu lực.** Tự động cho CephFS client/MDS. Extended value có ý nghĩa khi request đã retry/forward nhiều; blocklisted flag có ý nghĩa với kernel client `recover_session=clean`. Không cần on-disk migration hay operator enable.

**Mixed/full/rollback.** Target client gửi v1/no tail cho MDS không quảng bá feature; target MDS map request base/legacy vào extended fields. Vì vậy design có mixed path rõ ràng. Old client tiếp tục dùng error string/versioned prefix, new client có flag máy-đọc được. Full target cho counter 32-bit end-to-end. Rollback chỉ mất extended semantics, không thấy persistent format trong owner này.

**Tác động và độ chắc chắn.** Category: compatibility/correctness/availability. Consequence trung bình (miscount retry/fwd hoặc không tự recover session), likelihood thấp cho counter overflow nhưng cao hơn cho mixed legacy decode; applicability chỉ CephFS. Evidence confidence `high`; matrix client/kernel thực tế `medium`.

**Test đã đọc.** Không có direct unit test cho request-head mixed versions trong responsible commits. `qa/tasks/cephfs/test_client_recovery.py::test_reconnect_after_blocklisted` kiểm kernel/FUSE recovery behavior và ghi rõ kclient dựa vào session reject. Cần matrix base/target client↔MDS, forced forward/retry và blocklist; chưa chạy.

### MSG-009 — `MMgrUpdate` mới tạo một edge MON-target → MGR-base

**Owner/evidence.** Inventory `1458`, `1530`, `1532` (`conditional`) và `1531` (`mixed`). Message type `0x70b` ở target `src/msg/Message.h:239`, decoder case `src/msg/Message.cc:897`, `MMgrUpdate` constructor `src/messages/MMgrUpdate.h:75`; base không có type/case/class. Commits `9f3a6fd1c9919ba7d0d6be2066ca5b2f828b238c` và endpoint cleanup `5fb33b8beea7c915afe3052ca338d1888ce12ee4`. Sender/caller context: target `MgrClient::_send_update` `src/mgr/MgrClient.cc:252` và `Monitor::update_pending_metadata` `src/mon/Monitor.cc:2982`, gọi từ `MonmapMonitor::on_active`.

**Trước → sau.** Target MON dùng message mới để cập nhật metadata/version của MON tại active MGR. MGR base đi vào default branch của `decode_message`, log unknown type và trả null; cả ProtocolV1 lẫn ProtocolV2 đều chuyển decode failure sang `_fault()`, nên kết nối bị reset. Mặc định `ms_die_on_bad_msg=false`, vì vậy đây thường là một reconnect/transient metadata gap: sender clear `need_metadata_update` sau send và không lặp liên tục trên connection mới. Nếu deployment đã đổi option dev `ms_die_on_bad_msg=true`, base receiver gọi `ceph_abort()` ngay trong unknown-message branch.

**Kích hoạt và hiệu lực.** Có thể xảy ra trong order MON-first thông thường khi target MON thấy stored metadata version khác và active MGR vẫn `16.2.5`. Không phải mọi tick; path gắn với `on_active`/metadata mismatch. Không có feature negotiation trong message hunk.

**Mixed/full/rollback.** Target MON + base MGR là tổ hợp cần canary; giữ option fatal ở default và nâng MGR sát sau MON làm giảm exposure. Không nên đảo toàn bộ upgrade order chỉ từ finding này nếu chưa kiểm dependency khác. Target MGR decode message và cập nhật state; full target không còn unknown type. Persistent effect chỉ là metadata có thể tạm stale, không thấy schema migration.

**Tác động và độ chắc chắn.** Category: compatibility/availability/detectability. Default consequence thấp–trung bình (connection reset và metadata validation chậm); custom fatal option consequence cao. Evidence confidence `high` từ sender/decoder/fault path; observed frequency confidence `medium` vì chưa chạy mixed lab.

**Test đã đọc.** Không tìm thấy repository test ghép target MON với base MGR hay unknown `MSG_MGR_UPDATE`. Lab cần capture reconnect count, MGR uptime và `ceph versions`/MON metadata convergence với option default, đồng thời chỉ kiểm tra config inventory cho fatal option—không bật nó trong production để thử. Chưa chạy.

## 4. Mixed-version và activation matrix

| Giai đoạn/kịch bản | Hành vi kỳ vọng từ code | Failure signal cần quan sát | Stop/điều tra trước khi đi tiếp |
| --- | --- | --- | --- |
| MON canary target, MON còn base | Chỉ leader target có proposal-copy CephX; leader base vẫn semantics cũ | auth/ticket lỗi, rotating version khác nhau, election lặp | Dừng rollout MON nếu có key divergence hoặc auth failure |
| Bất kỳ daemon target reconnect peer base | Fix local messenger có hiệu lực phía target; phía base vẫn race local | stuck shutdown, connection reset storm, daemon không join lại | Dừng nếu restart vượt timeout baseline hoặc reset không hội tụ |
| MON target, active MGR base | Có thể một unknown `MMgrUpdate` làm fault/reconnect; default không abort | MGR restart, MON↔MGR reconnect lặp, metadata/version stale | Không tiếp tục nếu `ms_die_on_bad_msg=true` hoặc MGR crash/lặp reconnect |
| OSD target shutdown với MON base/target | Base MON suy ra chỉ hiểu prefix v3; target MON hiểu `down_and_dead` v4 | OSD vẫn up/dead state sai, wait shutdown hết timeout | Xác minh MON-first và OSDMap state trước OSD kế tiếp |
| CephFS client/MDS mixed | Target chọn v1 cho peer không có 32-bit feature; target decoder map legacy counters | decode fault, request retry loop, session recovery fail | Dừng CephFS phase nếu request/session không hội tụ |
| Thử CIDR range blocklist trong rolling | Command phải bị `ENOTSUP/EAGAIN` khi quorum hoặc OSD đang up thiếu feature | Command thành công khi còn old up OSD, old/offline OSD không rejoin, client bypass | Không enable cho tới full inventory + rejoin test; xem report `04` |
| OSD/RGW target trên nền tảng đặc thù | AArch64 CRC vectors và RGW FIPS request phải thành công | checksum mismatch, request MD5/ETag fail, daemon abort | Dừng theo node/instance; không suy rộng kết quả x86 sang ARM |

## 5. Validation đề xuất (chưa thực thi)

1. **Baseline cấu hình/As-Is.** Thu thập `msgr2` usage, `ms_die_on_bad_msg`, explicit/auto public+cluster address, interface state, `crush_location_hook`, MON priority/weight, fast-shutdown flags, CPU architecture/compiler package, OpenSSL/FIPS mode, RGW/NFS use, CephFS client loại/version và OSD đang offline. Đây là điều kiện áp dụng, không phải checklist tùy chọn.
2. **MON/MGR canary.** Nâng một MON theo procedure của suite, quan sát auth version/election và MON↔MGR reconnect; xác nhận MGR không restart và metadata cuối cùng phản ánh version target. Không kích hoạt CIDR range-blocklist trong phase này.
3. **Messenger churn.** Trong lab, chạy traffic có baseline rồi restart một peer, tạo network flap có kiểm soát và shutdown đồng thời; đo reconnect convergence, daemon exit latency, stuck threads và reset rate cho cả msgr1/msgr2, ưu tiên msgr2.
4. **OSD lifecycle.** Với OSD lab có inflight op, restart và kiểm tra coredump; kiểm OSDMap chuyển down/dead đúng khi fast shutdown; phân biệt heartbeat timeout thật với warning từ map mapping.
5. **CephFS matrix.** Base client→target MDS, target client→base MDS, rồi full target; ép forward/retry và blocklisted-session recovery. Expected: không decode fault, counters giữ giá trị legacy hoặc extended đúng capability, client hội tụ.
6. **Platform matrix.** Chạy known CRC vectors trên chính AArch64 build/compiler production và RGW ETag/multipart/encryption paths dưới đúng FIPS/OpenSSL packages. Test ở nền tảng khác không thay thế.
7. **Range feature.** Chỉ trong disposable lab sau full daemon upgrade: xác minh CIDR add/remove/expiry, OSD từng offline rejoin, client cũ mới và rollback rehearsal. Nếu chưa có bằng chứng này, giữ feature chưa sử dụng.

Các scenario trên là thiết kế kiểm thử, không phải ủy quyền chạy trên cluster thật.

## 6. Thay đổi support/trivial không được nâng thành finding

**Support/observability.** `MMgrBeacon` v10→v11 ở `9baa469a05e31a304903b197646723e80fcf8217` encode address vector trước rồi mới append module names, chủ đích để MON cũ vẫn nhận danh sách địa chỉ phục vụ blocklist; phần tên chỉ cải thiện debug. Logging commits `97ff0480ace914573f315c37fe7037c45435d592`, `d2e81ac46963601c858034f8907b8a52c761bdd2`, `847972f9b21b3a8213952512e287d1e4bff16801` làm FIFO stderr atomic, invalidate fd khi reopen và khiến custom `log_max_recent` có hiệu lực. `OutputDataSocket` commit `4ca4577f0041a8bde3153a8789c9017a55087720` đánh thức reader khi RGW ops-log backlog đầy. Các thay đổi này giúp log/audit/diagnostics, nhưng endpoint code không chứng minh thay đổi daemon restart protocol hay service availability chung; vì vậy chúng là support, không thành finding sâu. Custom `log_max_recent` vẫn cần capacity check ở report `06`.

**Cross-owner support.** Rename/lower-bound trong `MOSDMap` và Crimson (`1242–1243`, `1459`) là context cho findings map/peering ở reports `01`/`04`; MDS beacon health metric (`1456`) thuộc health/MDS report. ProtocolV1 throttle change (`1536`), perf counter naming (`1212`), debug level (`1239`) và cpu-profiler admin-socket crash fix (`1623`) cải thiện detectability nhưng không tự đổi outcome của rolling upgrade.

**Trivial aggregate.** CMake/header/include fixes, Windows-only portability, formatting, fair-mutex/Timer scaffolding, bit-vector API chưa dùng, CompatSet dump, helper operators, test tolerance, authentication-dispatch annotation và perf messenger sources không có causal path upgrade đã chứng minh. Chuỗi Posix/DPDK/RDMA worker refactor có một regression trung gian được sửa bởi `9df11e889b037aa967f08d28dd8b272b8ad3a29d`; endpoint target hoàn chỉnh không cho thấy behavior delta cần operator action, nên không biến lịch sử trung gian thành risk endpoint. IPv6 mount string helper ở `1544` là client utility, không phải daemon binding fix của `MSG-006`.

## 7. Row-to-disposition ledger — 92/92

Disposition dùng ở đây:

- `material`: dòng trực tiếp triển khai một finding có tác động nâng cấp rõ;
- `conditional`: có đường tác động thật nhưng chỉ khi deployment/config/workload thỏa điều kiện;
- `mixed`: cùng file có hunk material/conditional lẫn refactor/log/client/support;
- `support`: test, observability hoặc context/cross-owner hỗ trợ nhưng không là finding độc lập;
- `trivial`: không chứng minh được causal path tới nâng cấp ở endpoint.

| Disposition | Số dòng | Inventory indices |
| --- | ---: | --- |
| `material` | 5 | `1215`, `1246`, `1454`, `1460`, `1533` |
| `conditional` | 15 | `1216`, `1219–1221`, `1224`, `1228`, `1230–1231`, `1237–1238`, `1240`, `1455`, `1458`, `1530`, `1532` |
| `mixed` | 7 | `1097–1098`, `1247`, `1531`, `1534`, `1537`, `1545` |
| `support` | 19 | `1096`, `1211–1212`, `1234`, `1239`, `1242–1243`, `1257`, `1389–1392`, `1456–1457`, `1459`, `1536`, `1623`, `2398`, `2547` |
| `trivial` | 46 | `1208–1210`, `1213–1214`, `1217–1218`, `1222–1223`, `1229`, `1232–1233`, `1241`, `1244–1245`, `1251–1256`, `1261–1262`, `1452–1453`, `1461`, `1528–1529`, `1535`, `1538–1544`, `2416–2419`, `2421–2422`, `2499–2501`, `2661` |
| **Tổng** | **92** | **Khớp 92 dòng CSV; không trùng, không thiếu** |

Lưu ý range chỉ là inventory index, không phải path range; index `2420` không thuộc CSV này nên ledger tách `2416–2419` và `2421–2422`.

## 8. Khoảng trống bằng chứng và kết luận sử dụng

- Chưa có As-Is về config, architecture, FIPS/OpenSSL, CephFS client, MON weights, offline OSD hay historical reconnect/coredump; do đó applicability/likelihood không được suy từ code.
- Không chạy repository test hay mixed cluster. Những chỗ evidence confidence `high` là confidence về semantics code, không phải xác suất production.
- `MSG-007` chưa chứng minh offline-old-OSD/client/rollback safety; không enable CIDR range-blocklist chỉ vì target hỗ trợ.
- `MSG-009` có đường unknown-message/fault rõ, nhưng số lần reconnect thực tế cần canary; custom fatal option phải được inventory trước MON rollout.
- Không có căn cứ để đưa GO/NO-GO production chỉ từ component này. Stop/go phải ghép với reports `01`, `04`, `06`, As-Is và kết quả validation theo phase.

Kết luận code-level: ưu tiên cao nhất trong cửa sổ nâng cấp là MON CephX state consistency, messenger reconnect/shutdown, OSD teardown, và ba mixed contracts `range-blocklist`, `MClientRequest`, `MMgrUpdate`. Các thay đổi còn lại vẫn truy vết đủ trong CSV/ledger nhưng không được thổi phồng thành risk nếu thiếu causal path.
