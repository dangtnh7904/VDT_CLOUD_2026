# 04 — MON, OSDMap, CRUSH, quorum và placement: v16.2.15 → v17.2.7

**Trạng thái: binary gate owner đã hoàn tất; kiểm chứng lab còn mở.** [CSV đầy đủ của owner](./04-mon-osdmap-crush.csv) có 185 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 50`, `trivial = 135`, **chưa phân loại = 0**.

## Phạm vi và phương pháp

Owner này phụ trách MON, OSDMap, CRUSH, quorum và placement. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro. Các finding chi tiết chỉ đến từ những hàng `affect`; CSV giữ toàn bộ thay đổi.

## Findings liên quan nâng cấp

### MON-001 — Checkpoint `require-osd-release quincy`

**CSV:** `src/mon/OSDMonitor.cc`. Pacific `OSDMonitor::create_initial` mặc định mốc Pacific cho cluster mới; Quincy mặc định mốc Quincy. Quan trọng hơn cho **cluster hiện hữu**, endpoint Quincy có nhánh `osd require-osd-release quincy` tại `OSDMonitor.cc:11680`: kiểm MON feature `FEATURE_QUINCY` và các OSD **đang up** có `SERVER_QUINCY`, rồi ghi `new_require_osd_release`. Logic chung tại `:11698` cấm hạ mốc đã đặt. Nhánh Quincy không có ở endpoint Pacific. [Quincy release notes](https://docs.ceph.com/en/quincy/releases/quincy/) mô tả bước hoàn tất OSD upgrade; `qa/releases/quincy.yaml` và `qa/workunits/cephtool/test.sh` có đường test lệnh này. Repository tests đã đọc tên/recipe, chưa chạy.

**Điều kiện:** chỉ khi operator hoặc cephadm hoàn tất OSD phase và đặt mốc Quincy; chỉ thay binary không tự đặt flag ở lệnh manual. `CephadmUpgrade._complete_osd_upgrade` trong `src/pybind/mgr/cephadm/upgrade.py:942` gọi MON command sau OSD phase (method này là context, không phải hunk riêng cho finding). OSD đang offline không nằm trong phép kiểm `get_up_osd_features()`; cần kiểm kê chúng trước checkpoint. Trong giai đoạn mixed-version chưa đặt flag, mốc Pacific có thể còn hiệu lực. Sau khi đặt flag, không hạ nó về Pacific qua command thông thường; rollback binary/OSD cũ cần được xem là giới hạn chưa chứng minh an toàn.

**Tác động:** thay đổi persistent OSDMap và ràng buộc rollback/compatibility. **Evidence confidence:** high cho guard và tính one-way trong endpoint code; medium cho khả năng rollback thực tế vì chưa thử artifact, offline OSD và dữ liệu cluster. Không coi đây là GO/NO-GO riêng lẻ.

**Kiểm chứng:** trước checkpoint, đối chiếu toàn bộ OSD kể cả down với version và feature; trong lab diễn tập upgrade, ghi OSDMap trước/sau và xác nhận lệnh chỉ thành công khi các OSD up hỗ trợ Quincy. Rehearsal rollback theo snapshot phù hợp thay vì giả định hạ `require_osd_release` được.

### MON-002 — Quorum Quincy có persistent MON feature và incompat bit mới

**CSV:** `src/mon/mon_types.h`, `Monitor.h` và `Monitor.cc`. Base biết persistent feature Pacific và `CEPH_MON_FEATURE_INCOMPAT_PACIFIC`; target thêm `FEATURE_QUINCY` vào supported/persistent set, `CEPH_MON_FEATURE_INCOMPAT_QUINCY` vào compat set và `SERVER_QUINCY` vào required features khi monmap đã ghi feature này. `MonmapMonitor::apply_mon_features()` chỉ áp dụng feature từ quorum khi quorum đầy đủ, rồi có thể tăng `min_mon_release`. Đây là đường tự động của MON quorum, khác với lệnh OSD checkpoint ở MON-001. Target `Monitor.cc` cũng đổi signal SIGHUP, `sync_force` parser và một số output/health path, nên hàng này không được coi là refactor thuần.

**Điều kiện/tác động:** khi toàn bộ MON trong monmap hỗ trợ Quincy và quorum đầy đủ, persistent feature có thể được ghi; MON Pacific cũ không có incompat bit này và khả năng gia nhập lại cần được kiểm riêng. Trong mixed MON phase, thiếu full quorum hoặc còn MON cũ có thể giữ feature ở mốc trước. **Evidence confidence:** high cho guard/source và tính persistent; medium cho biểu hiện rollback với artifact cụ thể.

**Kiểm chứng:** trong lab nâng từng MON, chụp `mon dump`, quorum, monmap feature và store compat set sau từng bước; thử dừng/khởi động MON cũ trên clone trước và sau khi full Quincy quorum hình thành. Ghi rõ điểm không thể rollback MON binary cũ.

### MON-003 — Pending Cephx key rotation chỉ mở sau mốc MON Quincy

**CSV:** `src/mon/AuthMonitor.cc/.h`, `src/messages/MMonUsedPendingKeys.h` mới và `src/mon/MonCommands.h`. Base chưa có các lệnh `auth get-or-create-pending`, `auth clear-pending`, `auth commit-pending` hay thông điệp MON-to-MON về pending key đã dùng. Target thêm lệnh và xử lý incremental auth; `AuthMonitor::tick()` chỉ gửi/commit pending key khi `min_mon_release >= quincy`, và `prepare_command()` chặn ba lệnh trên trước mốc này bằng `-EPERM`. Cùng file command registry còn đổi các bề mặt vận hành khác: thêm `fs rename`, `osd set/unset noautoscale`, pool `eio`, chuyển vài flag từ `CephChoices` sang `CephBool` và bỏ command `OBSOLETE` cũ. Các thay đổi đó cần đối chiếu script quản trị, dù không phải toàn bộ đều nằm trong key rotation.

**Điều kiện/tác động:** operator dùng pending-key workflow hoặc automation gọi các lệnh MON; activation phụ thuộc mốc MON, không chỉ việc thay binary. Key được ghi trong auth store nên thử rollback trên clone; không suy client cũ có thể dùng key mới. **Evidence confidence:** high cho gate và command source, medium cho liên thông client khi mixed-version.

**Kiểm chứng:** trên lab với MON mixed rồi full Quincy, gọi ba lệnh và kiểm lỗi trước mốc, keyring/pending key sau mốc, xác thực client với key cũ/mới và restart MON. Chạy lại các script gọi command đã bỏ hoặc parser flag đổi.

### MON-004 — Crimson MonMap ưu tiên `mon_host_override`

**CSV:** `src/mon/MonMap.cc/.h`. Base hàm Seastar `MonMap::build_initial()` đọc monmap file, rồi `build_monmap()` dùng `mon_host`/config/DNS; target kiểm `mon_host_override` trước file và tách `maybe_init_with_mon_host()`. Đường classic đã có `mon_host_override` ở cả hai endpoint; thay đổi cụ thể ở đây là đường Crimson. Target cũng ghi log khi DNS SRV resolution thất bại.

**Điều kiện/tác động:** Crimson MON/client dùng cấu hình `mon_host_override`; tập MON được chọn để bootstrap có thể khác khi đồng thời có monmap file hoặc `mon_host`. **Evidence confidence:** high cho thứ tự source, low cho applicability vì chưa biết triển khai Crimson.

**Kiểm chứng:** nếu chạy Crimson, thử cấu hình đồng thời override, monmap file và DNS SRV; xác nhận địa chỉ MON được chọn, xử lý tên không resolve và khả năng join quorum sau restart.

### MON-005 — `mon feature ls --with-value` chuyển sang boolean option

**CSV:** `src/mon/MonmapMonitor.cc`. Base lấy chuỗi `with_value` và so đúng `--with-value`; target gọi `cmd_getval_compat_cephbool()`, tương ứng registry trong `MonCommands.h` chuyển option sang `CephBool`. Đường `mon dump`/`mon feature ls` cũng dùng helper lấy default mới, còn parse address chuyển sang overload `string_view`.

**Điều kiện/tác động:** CLI/script dùng `mon feature ls --with-value` hoặc gửi JSON command trực tiếp; cần kiểm cách parser chấp nhận cả dạng cũ và boolean trong giai đoạn mixed MON. **Evidence confidence:** high cho hunk/registry, medium cho CLI compatibility thực tế.

**Kiểm chứng:** gọi command bằng CLI và JSON với flag cũ, `true`, `false` trên MON mixed/full Quincy; so output feature name/value và exit code.

### MON-006 — CRUSH bỏ ruleset/min/max khỏi logic chọn rule

**CSV:** chín file `CrushCompiler.cc`, `CrushWrapper.cc/.h`, `builder.c/.h`, `crush.h`, `grammar.h`, `mapper.c/.h` dưới `src/crush/`. Base `crush_find_rule()` tìm theo ruleset, type và min/max size; target bỏ `crush_rule_mask` khỏi cấu trúc runtime, dùng rule ID trực tiếp và bỏ kiểm min/max khi chọn rule. `CrushCompiler` vẫn nhận `min_size`/`max_size` trong text cũ nhưng cảnh báo rồi bỏ qua; bản decompile target không in hai trường đó. `CrushWrapper::encode()` vẫn ghi bốn byte mask tương thích, nhưng với peer có `SERVER_QUINCY` sẽ ghi min/max `1/100`; peer cũ nhận giá trị deprecated. `decode()` từ chối map có ruleset khác rule ID. Commit tiêu biểu `d67bad8f311` và `f95eb04411c`.

**Điều kiện/tác động:** cluster có CRUSH map/rule cũ, custom rule text, hoặc pool size từng dựa vào min/max. Pacific `OSDMonitor` có đường chuẩn hóa legacy rule IDs; cần kiểm map thực đã chuẩn hóa trước khi dùng Quincy decoder. Việc bỏ min/max có thể thay đổi validation và placement cho pool/rule không chuẩn; không suy thay đổi ở mọi map. **Evidence confidence:** high cho format và code path, medium cho applicability.

**Kiểm chứng:** xuất CRUSH map và `crushtool --decompile` trước nâng cấp; kiểm rule ID = ruleset, type, min/max và pool tham chiếu. Trên clone, import/decompile bằng cả hai binary, chạy mapping cho tập PG/size mẫu và so acting/up set; thử text rule cũ có min/max, kiểm warning và output sau compile.

### MON-007 — OSDMap dùng rule ID trực tiếp và đổi tính toán PG upmap

**CSV:** `src/osd/OSDMap.cc/.h`. Base `_pg_to_raw_osds()` và `try_pg_upmap()` gọi `crush->find_rule(ruleset, type, size)`; target lấy `pool.get_crush_rule()` làm rule ID rồi chạy rule trực tiếp. `validate_crush_rules()` không còn check ruleset ID và min/max, nhưng vẫn check type. Target cũng tách nhiều phần `calc_pg_upmaps()` thành helper, cho phép seed ngẫu nhiên để tái lập test và thêm nhánh `pending_require_osd_release()` báo mốc Quincy khi OSD up có feature tương ứng. Hunk upmap lớn cần so kết quả thực, không coi việc tách helper là bằng chứng tương đương.

**Điều kiện/tác động:** OSDMap có custom CRUSH rule, PG upmap/balancer hoặc đang theo dõi mốc OSD release. Rule ID lệch ruleset hoặc min/max cũ là trường hợp cần ưu tiên; map chuẩn có thể cho cùng placement nhưng chưa được xác minh. **Evidence confidence:** high cho direct rule và release check, medium cho khác biệt upmap.

**Kiểm chứng:** trên bản clone OSDMap, chạy mapping mẫu theo pool/PG trước và sau, so up/acting set và `pg_upmap_items`; chạy balancer có seed cố định để so delta, nhất là pool dùng custom rule. Đối chiếu cảnh báo pending require-osd-release với feature OSD up.

### MON-008 — OSDMonitor đổi gate pool PG theo CRUSH rule

**CSV:** `src/mon/OSDMonitor.cc/.h`; hàng `.cc` liên kết cả MON-001 và MON-008. Base `check_pg_num()` tính dựa trên tổng OSD `in` toàn cluster; target lấy các OSD dưới root của CRUSH rule, chỉ cộng pool dùng rule đó rồi so `mon_max_pg_per_osd`. Target cũng dùng rule ID trực tiếp khi tạo pool, đổi validation từ `check_crush_rule(type,size)` sang check type và bỏ bước sửa legacy ruleset trong `create_initial()`; đường `osd crush set` phụ thuộc decoder ở MON-006. Các thay đổi khác cùng file gồm command `noautoscale`, pool `eio`, và guard `require-osd-release quincy` đã mô tả ở MON-001.

**Điều kiện/tác động:** tạo pool hoặc tăng `pg_num`/`size` trên cluster nhiều CRUSH root, đặc biệt khi một root có ít OSD hơn toàn cluster. Một thao tác từng qua gate Pacific có thể bị target từ chối `-ERANGE`; custom rule/min/max cũ cần kiểm trước. **Evidence confidence:** high cho hunk gate, medium cho số lượng pool bị ảnh hưởng.

**Kiểm chứng:** dựng lab có hai CRUSH root kích thước khác nhau, thử tạo pool và tăng PG/replica sát `mon_max_pg_per_osd`; ghi projected PG/OSD, mã lỗi và acting set ở hai endpoint. Thử import CRUSH map đã xuất từ cluster và kiểm rule ID, type cùng pool reference.

### MON-009 — LogMonitor đổi format bền vững và đường xuất cluster log

**CSV:** `src/mon/LogMonitor.cc/.h`. Base ghi `LogSummary` đầy đủ ở mỗi commit, kèm keys để dedup và log entries trong incremental; target ghi summary theo từng channel với dải sequence, recent-key LRU, mỗi `LogEntry` ở key riêng và chỉ checkpoint summary định kỳ. Target reader có nhánh `struct_v == 1` cho commit trước Quincy; đường log ra file/syslog/Graylog được tách, thêm Journald, giữ `external_log_to` trong MON store để tránh phát lặp khi replay. Source mô tả rõ migration từ pre-Quincy sang Quincy+.

**Điều kiện/tác động:** MON có lịch sử cluster log khi nâng hoặc restart; persistent format và trimming thay đổi nên phải xét khả năng đọc ngược và replay, nhất là khi rollback MON. Cấu hình xuất log ra file/Journald có thể đổi nơi nhận và số bản ghi thấy được. **Evidence confidence:** high cho format và legacy branch, medium cho rollback vì chưa dùng store clone.

**Kiểm chứng:** clone MON store trước upgrade, chạy target và so `ceph log last`, dedup, channel sequence và log file/Journald; crash/restart quanh checkpoint, kiểm không mất/phát lặp entry. Thử mở bản clone sau khi target đã ghi bằng Pacific binary để xác định ranh giới rollback.

### MON-010 — MDSMonitor đổi Paxos batching và thêm `fs rename`

**CSV:** `src/mon/MDSMonitor.cc`, `src/mon/FSCommands.cc/.h`. Base chỉ plug Paxos ở vài command có `batched_propose`; target bỏ hook này khỏi handler, plug/unplug quanh mọi `prepare_update()` và tick, ép immediate propose khi evict MDS. Target thêm `fs lsflags` và handler `fs rename`: chặn khi mirroring còn bật, đòi xác nhận, cập nhật tên CephFS trong pool application metadata rồi đổi FSMap; phản hồi cảnh báo cần cấp lại Cephx credentials theo tên mới. Base chưa có handler rename này.

**Điều kiện/tác động:** CephFS với MDS failover/eviction hoặc operator chạy rename; thay đổi batching có thể ảnh hưởng thời điểm ghi FSMap và phối hợp với OSDMap. `fs rename` là thao tác thay metadata và quyền client, chỉ thử khi có kế hoạch riêng. **Evidence confidence:** high cho hunk/caller, medium cho timing vận hành.

**Kiểm chứng:** lab gửi MDS beacon/fail trong lúc OSDMap update, so epoch và thời gian commit. Với clone CephFS, thử rename khi mirroring bật/tắt, kiểm pool application metadata, FSMap, mount client với credential cũ/mới và restart MDS/MON.

### MON-011 — MonClient thêm admin socket `rotate-key`

**CSV:** `src/mon/MonClient.cc/.h`. Base `MonClient` chưa là `AdminSocketHook`; target đăng ký `rotate-key`, decode key base64 từ input và thay key của entity trong keyring đang chạy, trả `-EINVAL` khi decode lỗi hoặc Cephx không bật. Target cũng đổi timeout authenticate từ wall clock sang monotonic clock.

**Điều kiện/tác động:** daemon/operator dùng quy trình xoay Cephx key sau khi pending key ở MON đã sẵn sàng; cập nhật live keyring có thể tránh restart nhưng cần xác thực client tiếp tục kết nối. **Evidence confidence:** high cho source, medium cho phối hợp đủ quy trình key rotation.

**Kiểm chứng:** trong lab, tạo pending key, gửi admin socket `rotate-key` cho daemon, xác thực lại với MON và thử key cũ/mới; kiểm lỗi base64 sai và restart daemon để chắc key persisted theo cách triển khai.

### MON-012 — HealthMonitor đổi xử lý mute và tick

**CSV:** `src/mon/HealthMonitor.cc`. Base bắt `invalid_argument` khi parse duration của health mute và khởi tạo `changed = false` trong tick; target dùng `parse_timespan()` rồi chỉ check duration bằng 0, và bắt đầu tick với `changed = true`. Điều này đổi đường phản hồi command và có thể đổi tần suất proposal health; chưa thấy đủ bằng chứng để coi là thuần refactor.

**Điều kiện/tác động:** automation dùng `health mute` với duration không chuẩn hoặc cluster có health check cập nhật thường xuyên. **Evidence confidence:** high cho hunk, medium cho hiệu ứng Paxos/CLI.

**Kiểm chứng:** so exit code/message của health mute với duration hợp lệ, 0 và chuỗi lỗi ở hai endpoint; đo health epoch/proposal khi check không đổi qua nhiều tick.

### MON-013 — MgrMonitor đổi tập module luôn bật và output command

**CSV:** `src/mon/MgrMonitor.cc`. Target điều chỉnh bảng `always_on_modules` theo release, đưa `orchestrator`, `pg_autoscaler`, `telemetry` vào mốc phù hợp và thêm mốc Quincy. `mgr module ls` có output dạng bảng khi plain, trong khi base chủ yếu dùng formatter JSON mặc định; `mgr module enable --force` chuyển sang boolean parser tương thích. Các thay đổi này tác động control plane/module discovery và script parse output.

**Điều kiện/tác động:** MGR upgrade hoặc automation đọc `mgr module ls`/enable module; bảng always-on phụ thuộc release của MgrMap, cần kiểm thời điểm mốc đổi. **Evidence confidence:** high cho hunk, medium cho module activation runtime.

**Kiểm chứng:** ghi `mgr module ls` ở plain/JSON trước và sau từng phase, so always-on/enabled/disabled, chạy script quản trị hiện có và thử `--force` bằng CLI/JSON.

### MON-014 — PGMap dùng rule ID trực tiếp và đổi digest/output

**CSV:** `src/mon/PGMap.cc/.h`. Base `PGMapDigest` còn encode/decode phiên bản 1–3 cho peer cũ; target assert peer có `SERVER_NAUTILUS` và digest version >=4. Các hàm tính free space theo pool chuyển từ `find_rule(ruleset,type,size)` sang rule ID trực tiếp, cùng hướng với MON-006/007. Bảng `pg dump` plain thêm log duplicate, scrub duration/schedule và số object scrubbed/trimmed; một helper stuck-count cũ bị bỏ.

**Điều kiện/tác động:** Pacific→Quincy dùng peer hiện đại, nhưng custom CRUSH map có rule ID không chuẩn có thể làm chỉ số free space theo pool khác. Script parse bảng PG plain phải cập nhật cột. **Evidence confidence:** high cho hunk, medium cho tác động thực trên map cụ thể.

**Kiểm chứng:** so `pg dump`/stats và pool free space ở hai endpoint trên cùng OSDMap, kiểm script parser; thử MON/MGR mixed-version nhận digest và map có custom rule.

### MON-015 — MON capability profile mở thêm lệnh quản trị

**CSV:** `src/mon/MonCap.cc`. Target thêm quyền `config rm` cho một số mClock/recovery option trong OSD profile; MGR profile thêm quyền `heap` và `dump_mempools` để telemetry lấy metric. Base profile không có các grant này. Đây là thay đổi quyền thực tế khi daemon dùng profile mặc định.

**Điều kiện/tác động:** OSD/MGR hoặc automation dựa vào các profile trên; tập lệnh được phép thay đổi sau upgrade. **Evidence confidence:** high cho expansion rule, medium cho đường lệnh được gọi trong deployment.

**Kiểm chứng:** lab với credential profile OSD và MGR, thử các lệnh vừa được thêm và lệnh ngoài phạm vi; so audit log/permission error trước và sau, kiểm telemetry nếu bật.

### MON-016 — `ceph-mon` đổi bind/public address và xử lý SIGHUP

**CSV:** `src/ceph_mon.cc`. Base gọi `msgr->bindv(bind_addrs)` rồi `set_addrs(public_addrs)` nếu khác nhau; target truyền cả `bind_addrs, public_addrs` vào `bindv()`. Base đăng ký SIGHUP với handler chung; target gửi SIGHUP vào `Monitor::handle_signal()`, nơi target reload cấu hình và reopen log. Đây là đường startup/reload MON, đặc biệt khi bind address khác địa chỉ công bố.

**Điều kiện/tác động:** MON có NAT/multiple network hoặc gửi SIGHUP để rotate log/config. **Evidence confidence:** high cho hunk/caller, medium cho hành vi với network topology cụ thể.

**Kiểm chứng:** trên lab dùng bind/public address khác nhau, kiểm địa chỉ MON quảng bá và khả năng peer/client kết nối; gửi SIGHUP khi có logging file, kiểm reopen và quorum ổn định.

### MON-017 — ConfigMonitor đổi tên option xuất ra và kiểu pending

**CSV:** `src/mon/ConfigMap.cc/.h`, `ConfigMonitor.cc/.h`. Base `MaskedOption` giữ `localized_name` từ key config khi dump/print; target dùng tên canonical `opt->name`. `ConfigMonitor` bỏ indent riêng theo entity khi in bảng, chuyển pending/pending_cleanup từ `boost::optional` sang `std::optional` và dùng reset tương ứng. Đường lấy format/default và giá trị daemon cũng đổi biểu thức; chưa có bằng chứng runtime cho từng option.

**Điều kiện/tác động:** operator/script đọc `ceph config dump/get` hoặc cluster có option alias/rename trong MON store. Output tên và định dạng bảng có thể khác; pending update cần thử sau restart. **Evidence confidence:** high cho output hunk, medium cho storage compatibility và trường hợp alias thực tế.

**Kiểm chứng:** trên MON store clone có config theo entity, mask và tên alias, so `config dump/get/log` plain/JSON, set/rm/reset rồi restart MON; xác nhận giá trị daemon vẫn được nạp.

### MON-018 — Crimson từ chối `crush_location_hook`

**CSV:** `src/crush/CrushLocation.cc`. Base `update_from_hook()` gọi subprocess cho hook khi option khác rỗng; target ở build `WITH_SEASTAR && !WITH_ALIEN` gọi `ceph_abort_msg()` nếu hook được cấu hình, vì đường subprocess không được hỗ trợ. Build classic tiếp tục qua nhánh hook cũ. Commit `3b17fa025d0` nêu rõ giới hạn Crimson.

**Điều kiện/tác động:** chỉ Crimson dùng `crush_location_hook` khác rỗng; OSD có thể không khởi động thành công sau khi đổi binary nếu cấu hình này tồn tại. **Evidence confidence:** high cho preprocessor và abort; applicability cần cấu hình As-Is.

**Kiểm chứng:** rà effective config của Crimson OSD trước rollout. Trong lab chạy đúng build, thử hook rỗng/khác rỗng, ghi exit code và log startup; với classic build kiểm hook vẫn trả CRUSH location đúng.

### MON-019 — MON join bỏ wire format trước Nautilus

**CSV:** `src/messages/MMonJoin.h`. Base encode bản v1 cho peer thiếu `SERVER_NAUTILUS` và decode header v1 thành legacy address; target assert peer có feature Nautilus và header version >1. Payload phiên bản mới vẫn mang address vector và CRUSH location. Commit `4a13e912619` nằm trong cụm bỏ tương thích pre-Octopus.

**Điều kiện/tác động:** một MON rất cũ cố join khi rollout Quincy; cluster đúng tiền đề Pacific 16.2.15 không đi vào nhánh này, nhưng cần đối chiếu version thực của mọi MON thay vì suy từ tag source. **Evidence confidence:** high cho wire guard, low cho applicability nếu chưa có inventory daemon.

**Kiểm chứng:** liệt kê MON version và feature trước upgrade; trong lab mixed Pacific/Quincy kiểm MON join/quorum. Chỉ nếu As-Is còn peer cũ hơn Nautilus mới thử đường legacy trên môi trường cách ly.

### MON-020 — `crushtool` yêu cầu replica range rõ ràng khi test map

**CSV:** `src/crush/CrushTester.cc/.h`, `src/tools/crushtool.cc`. Base tester có thể lấy min/max replica từ rule mask và lọc `--ruleset`; target bỏ ruleset và min/max mask, trả `-EINVAL` nếu không có `--num-rep` hoặc cặp min/max. `crushtool --check` cũng không còn gọi overlap-rule check. `OSDMonitor` vẫn dùng tester cho CRUSH smoke test nhưng đặt `num_rep` trước khi gọi. Commit `33f7619764d` bổ sung yêu cầu tham số.

**Điều kiện/tác động:** script validation/CRUSH dry run dùng cú pháp cũ có thể thất bại hoặc bỏ phép kiểm overlap. Điều này đổi mức bao phủ trước khi import map mới. **Evidence confidence:** high cho CLI và caller, medium cho script nào được dùng thực.

**Kiểm chứng:** chạy lại lệnh crushtool hiện có trên map clone, thêm replica range rõ ràng, so mapping mẫu và exit code; kiểm `--check` không còn được dùng như phép chứng minh không có overlap.

### MON-021 — Công cụ MON store đổi đường cleanup và lỗi

**CSV:** `src/tools/ceph_monstore_tool.cc`. Base nhiều nhánh `goto done` rồi đóng store; target dùng `scope_guard` để đóng store và output file khi return sớm. Hunk thay đổi cả lỗi parse, export/import, trace và `store-copy`; riêng nhánh thất bại `out_store.create_and_open()` giờ `return err`, nên exit code cần kiểm trên binary thực. Đây là công cụ phục hồi MON store, không phải daemon path.

**Điều kiện/tác động:** chỉ khi dùng `ceph-monstore-tool` để backup, export, rebuild hoặc điều tra lỗi trong upgrade/rollback. Cleanup và exit code khác có thể ảnh hưởng automation phục hồi. **Evidence confidence:** high cho control flow, medium cho biểu hiện theo từng lỗi.

**Kiểm chứng:** trên bản sao store, chạy dump/export/store-copy thành công và các lỗi có kiểm soát (output không ghi được, map/version không tồn tại); so file tạm, store lock và exit code. Không chạy trên store production đang mở.

### MON-022 — `crushdiff` mới ước lượng dữ liệu cần di chuyển

**CSV:** `src/tools/crushdiff` mới. Script `compare` kết hợp `osdmaptool --test-map-pgs-dump` trước/sau import CRUSH map với JSON PG stats, rồi in số PG, object shard và byte ước lượng cần di chuyển; còn có `export` và `import`. Có thể dùng file OSDMap/PG dump lưu sẵn để kiểm offline, nhưng `import` không truyền `--osdmap` gọi `ceph osd setcrushmap` lên cluster thật.

**Điều kiện/tác động:** operator dùng công cụ này để ước lượng rebalance hoặc kiểm CRUSH map trong kế hoạch upgrade; số liệu là ước lượng từ snapshot, không đo thời gian/thực tải. **Evidence confidence:** high cho source, medium cho độ khớp thực tế.

**Kiểm chứng:** trên bản sao OSDMap và PG dump, chạy `compare` với map giữ nguyên và map thay đổi nhỏ, so PG mapping/ước lượng với `osdmaptool`; ghi snapshot time. Chỉ lập kịch bản `import` cho lab được cho phép riêng.

### MON-023 — `monmaptool --create` đặt mốc MON tối thiểu Octopus khi chưa chỉ định

**CSV:** `src/tools/monmaptool.cc`. Base khởi tạo `min_mon_release` bằng giá trị zero; target dùng `unknown`, rồi trong nhánh create đặt Octopus nếu người dùng chưa truyền mốc. Nhánh cuối ghi giá trị này vào monmap. Tác động nằm ở monmap tạo mới hoặc tái tạo trong quy trình phục hồi, không tự sửa monmap cluster hiện có.

**Điều kiện/tác động:** script tạo monmap bằng target binary mà không nêu release; mốc implicit có thể khác base và ảnh hưởng daemon được phép join. **Evidence confidence:** high cho đường create/write.

**Kiểm chứng:** tạo monmap lab ở hai endpoint với/không có flag release, dump `min_mon_release` và thử MON Pacific join vào bản target phù hợp; ghi flag tường minh trong runbook phục hồi.

### MON-024 — `osdmaptool` thêm seed cho upmap và đổi thống kê map

**CSV:** `src/tools/osdmaptool.cc`. Target nhận `--upmap-seed` và truyền seed vào `OSDMap::calc_pg_upmaps()` để tái lập đề xuất upmap; giữa các pool seed tăng 13. Đường `--test-map-pgs-dump`/`--test-map-pgs-dump-all` còn thay cách đếm OSD trong vector acting, kể cả `CRUSH_ITEM_NONE`, nên output thống kê có thể khác khi mapping thiếu replica.

**Điều kiện/tác động:** script dry run balancer hoặc phép so CRUSH map dùng osdmaptool; seed hỗ trợ so lặp lại, nhưng bảng count trên PG undersized cần đọc đúng. **Evidence confidence:** high cho hunk, medium cho khác biệt số liệu trên map thực.

**Kiểm chứng:** dùng cùng OSDMap clone, so hai lần chạy với seed cố định và một map có PG thiếu replica; đối chiếu acting set riêng với bảng count trước khi kết luận cân bằng.

### MON-025 — Runbook phục hồi MON từ OSD sửa thứ tự `--mon-ids`

**CSV:** `doc/rados/troubleshooting/troubleshooting-mon.rst`. Base ghi `--mon-ids` chủ yếu cho tên MON dài; target bổ sung rằng các ID phải được cung cấp theo thứ tự IP nếu tên không sắp theo IP, và đưa ví dụ `b a c`. Tài liệu cũng làm rõ giới hạn của store dựng lại từ OSD: MDS keyring/map và trạng thái pool đang tạo có thể thiếu. Đây là thay đổi ở hướng dẫn khôi phục, không phải thay đổi tự động của daemon. Commit liên quan `7f9dad3eb5a` sửa thủ tục lấy lại MON quorum từ OSD.

**Điều kiện/tác động:** chỉ khi mất quorum/MON store và operator dùng thủ tục này để khôi phục trong hoặc sau upgrade. Sai thứ tự ID có thể làm monmap phục hồi khác topology mong muốn; cần kiểm script thực tế và bản sao dữ liệu. **Evidence confidence:** high cho thay đổi runbook, medium cho rủi ro trên topology cụ thể.

**Kiểm chứng:** trên lab clone với tên MON không theo thứ tự IP, xuất OSD maps và dựng MON store theo thứ tự đúng; kiểm monmap, FSID, quorum và keyring sau phục hồi. Đối chiếu đủ MDS/auth state còn thiếu trước khi tuyên bố cluster ổn định.

## Trivial changes đã sàng lọc

**135 hàng:** 16 hunk source/tool đã sàng lọc trước đó; 8 tài liệu sửa chữ, markup, URL hoặc prompt; 3 tài liệu CRUSH giải thích hành vi source ở MON-006/020/022; 14 script QA/Teuthology cập nhật fixture, feature check, test key rotation, rule ID và log recovery. Thêm 94 hàng test/fixture gồm 55 CRUSH CLI, 8 monmaptool CLI, 18 common unit, 5 CRUSH unit, 6 MON unit, một Crimson monc và một daemon config test. Những hunk này theo dõi rule ID, replica range, precision của weight và API/compiler; chưa thấy test nào là gate nghiệm thu upgrade đang được thực thi. Nhóm QA có cả ca stretch uneven-weight bị xóa, nhưng nó không tự đổi binary hay đường khôi phục. Từng lý do có trong CSV.

Toàn bộ 185 hàng owner 04 đã có nhãn binary và lý do. Kiểm chứng runtime vẫn cần monmap, CRUSH map và cấu hình cluster thực.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Duy trì liên kết từ từng hàng `affect` tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Đã đối soát binary gate: `50 affect + 135 trivial = 185` và tóm tắt các cụm trivial ở trên.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
