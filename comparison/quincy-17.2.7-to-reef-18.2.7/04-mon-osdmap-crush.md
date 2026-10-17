# 04 — MON, quorum, OSDMap, CRUSH và placement: v17.2.7 → v18.2.7

**Binary gate owner 04 đã hoàn tất; applicability và lab còn mở.** [CSV đầy đủ của owner](./04-mon-osdmap-crush.csv) có 104 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 40`, `trivial = 64`, chưa phân loại = 0. Finding dưới đây chỉ lấy từ hàng `affect`.

## Phạm vi và bằng chứng

Owner này bao phủ MON services, quorum/election, MonMap, MgrMap, FSMap command path, OSDMap/CRUSH placement và các mon tools. Net diff được đọc trực tiếp giữa base `b12291d110049b2f35e32e0de30d70e9a4c060d2` và target `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`; caller, encoding gate, command registration và test được đối chiếu ở hai endpoint. Repo shallow và hai tag non-ancestor, nên không dùng `commit_count=1` làm lịch sử release. `PendingReleaseNotes` target chỉ được dùng khi khớp với code endpoint.

## Finding ảnh hưởng upgrade

### MON-001 — Full quorum Reef tự ghi persistent MON feature và tạo mốc không rollback về Quincy

**CSV:** `src/mon/mon_types.h`, `src/mon/Monitor.cc`, `src/mon/Monitor.h`, `src/mon/MonmapMonitor.cc`; `qa/standalone/mon/misc.sh` và monmaptool feature test là supporting trivial rows. Reef thêm `FEATURE_REEF` vào cả supported lẫn persistent feature set và thêm `CEPH_MON_FEATURE_INCOMPAT_REEF`. `MonmapMonitor::apply_mon_features()` chỉ áp dụng khi có full quorum; khi mọi MON trong quorum hỗ trợ Reef, nó OR feature mới vào MonMap và tăng `min_mon_release`. `Monitor::apply_monmap_to_compatset_features()` sau đó ghi incompat feature vào monitor store.

**Điều kiện và tác động:** mốc kích hoạt không phải lúc cài package đầu tiên mà là khi full quorum đã hội tụ trên binary hỗ trợ Reef. Trước mốc đó còn mixed MON; sau khi feature/incompat được commit, MON Quincy không đáp ứng requirement của quorum/store. Đây là rollback boundary có rủi ro cao và confidence high từ code + test endpoint. Không suy rằng backup store cũ tự đủ để failback nếu MonMap/control state mới đã tiếp tục tiến.

**Kiểm chứng:** trong lab nâng từng MON, lưu `ceph mon dump`, `ceph mon feature ls`, quorum feature và compatset trước/sau mỗi restart. Chứng minh feature Reef chưa persistent khi quorum chưa đủ, được commit đúng một lần khi full quorum, và thử quy trình failback chỉ trước boundary. Không cố khởi động MON Quincy vào store đã có Reef incompat trên production.

### MON-002 — Lệnh ghi MON trả lời sau commit thay vì chỉ sau khi proposal kết thúc

**CSV:** `src/mon/PaxosService.cc`, `src/mon/PaxosService.h`, `src/mon/AuthMonitor.cc`, `src/mon/ConfigMonitor.cc`, `src/mon/KVMonitor.cc`, `src/mon/HealthMonitor.cc`, `src/mon/LogMonitor.cc`, `src/mon/MDSMonitor.cc`, `src/mon/MgrMonitor.cc`, `src/mon/MonmapMonitor.cc`, `src/mon/OSDMonitor.cc`. Reef tách `waiting_for_commit` khỏi `waiting_for_finished_proposal`; callback commit chỉ hoàn tất khi `last_committed` tăng. Khi MON thành peon, election/restart/shutdown xảy ra, callback chưa commit nhận `-EAGAIN` thay vì có thể trả thành công theo trạng thái proposal/active cũ.

**Điều kiện và tác động:** áp dụng cho nhiều lệnh mutating như auth/config/MDS/MGR/OSDMap/MonMap/log. Trong mixed MON, semantics phụ thuộc binary đang giữ leader và service xử lý lệnh; automation phải chấp nhận retry idempotent khi election chen giữa request và commit. Đây là thay đổi correctness tích cực nhưng có thể làm script cũ thấy thêm EAGAIN/timeout. Confidence high cho callback path; chưa chạy fault-injection.

**Kiểm chứng:** dùng `src/test/mon/bench_commit.py`, config parallel workunit và một harness fault-injection: gửi lệnh idempotent, buộc leader election trước/sau Paxos commit, kiểm không có success trước state quan sát được, retry không nhân đôi mutation, và acknowledgement version đúng committed epoch.

### MON-003 — Connectivity election và stretch recovery loại state/rank không hợp lệ chặt hơn

**CSV:** `src/mon/ConnectionTracker.cc`, `src/mon/ElectionLogic.cc`, `src/mon/ElectionLogic.h`, `src/mon/Elector.cc`, `src/mon/Elector.h`, `src/mon/MonmapMonitor.cc`, `src/mon/Monitor.cc`, cùng stretch checks trong `src/osd/OSDMap.cc`. Reef bỏ report có rank âm, không tăng epoch/version khi local rank chưa hợp lệ, và để tiebreaker bỏ qua proposal từ MON nằm trong `stretch_marked_down_mons`. Disallowed leader được dựng lại từ MonMap, marked-down set và tiebreaker; OSDMap thêm health warning khi stretch bucket không đúng hai bucket hoặc có weight lệch.

**Điều kiện và tác động:** chỉ có ý nghĩa lớn với election strategy `connectivity`, đặc biệt stretch cluster trong failure/recovery. Cluster classic không chịu nhánh tiebreaker nhưng admin-socket connection-score schema vẫn đổi object→array. Mixed behavior do leader/elector target quyết định; không nên thay election strategy hay stretch topology cùng lúc với rolling MON. Risk cao nếu đang dùng stretch, thấp nếu As-Is chứng minh không dùng; confidence high cho code, topology thực unknown.

**Kiểm chứng:** dựng 5 MON/2-site+tiebreaker theo `qa/workunits/mon/setup_stretch_cluster.sh`; lần lượt cô lập site, đánh dấu/recover MON, restart khi rank chưa ổn định, và kiểm không bầu marked-down MON. Chạy uneven-weight test, xác minh `INCORRECT_NUM_BUCKETS_STRETCH_MODE`/`UNEVEN_WEIGHTS_STRETCH_MODE` xuất hiện rồi biến mất đúng điều kiện, đồng thời parser connection scores đọc array mới.

### MON-004 — `ceph config dump` giữ spelling của key đã lưu thay vì luôn in tên chuẩn hóa

**CSV:** `src/mon/ConfigMap.cc`, `src/mon/ConfigMap.h`, `src/mon/ConfigMonitor.cc`; `qa/workunits/mon/config.sh` là supporting trivial row. Reef lưu `localized_name` từ key trong config DB và dùng nó ở text/JSON dump; Quincy in `Option::name` đã chuẩn hóa. Vì vậy underscore/dash hoặc alias mà người dùng đã nhập có thể được phản chiếu khác trong output, dù option đích là cùng một schema entry.

**Điều kiện và tác động:** áp dụng khi config store chứa spelling không canonical hoặc parser so sánh literal field `name`. Không đổi effective value; ảnh hưởng là audit/export/diff và automation. Trong mixed MON, output có thể phụ thuộc MON/leader phục vụ command. Risk thấp-trung bình; confidence high.

**Kiểm chứng:** set cùng option qua các spelling được chấp nhận trên lab, lấy plain/JSON `config dump` từ old và target MON, rồi kiểm exporter/config-diff map theo canonical identity thay vì coi spelling đổi là add/remove.

### MON-005 — FSMap có control mới và lệnh failover CephFS thêm guard

**CSV:** `src/mon/FSCommands.cc`, `src/mon/FSCommands.h`, `src/mon/MDSMonitor.cc`, `src/mon/MDSMonitor.h`, `src/mon/MonCommands.h`. Reef thêm `balance_automate`, `bal_rank_mask`, `max_xattr_size`, `refuse_client_session`, `refuse_standby_for_another_fs` và `fs swap`; một số thao tác phối hợp FSMap với OSD pool application metadata bằng batched proposal. `fs fail`/`mds fail` từ chối khi có `MDS_HEALTH_TRIM` hoặc `MDS_HEALTH_CACHE_OVERSIZED`, trừ khi xác nhận cưỡng bức. `PendingReleaseNotes` khớp code rằng automatic metadata balancing mặc định tắt và xattr limit chuyển vào MDSMap.

**Điều kiện và tác động:** cluster có CephFS, đặc biệt có override `mds_max_xattr_pairs_size`, automation failover, metadata balancer hoặc quy trình rename/swap. Giới hạn xattr được phân tích thêm tại `CFG-007`; runtime MDS sẽ được đóng ở owner 11. Trong mixed MDS/MON, không dùng control mới chỉ vì CLI target đã nhận lệnh: old MDS interpretation và failback phải được test riêng. Risk cao khi CephFS áp dụng, N/A khi không có CephFS; confidence high cho MON command path.

**Kiểm chứng:** inventory FSMap flags và old xattr override; thử xattr boundary qua old/target rank, balancer on/off, standby selection và client-session refusal. Tạo health warning trim/cache, xác minh fail bị chặn, confirmation hoạt động và no-confirm không làm đổi FSMap. Với `fs swap`, dùng filesystem rỗng đã offline/refuse client, kiểm pool application tag, name/FSCID và rollback rehearsal.

### MON-006 — Health/stop-go của MON đổi sau restart

**CSV:** `src/mon/HealthMonitor.cc`, `src/mon/Monitor.cc`, `src/mon/Monitor.h`. Reef chỉ phát `MON_DOWN` khi vừa qua `mon_down_mkfs_grace` tính từ MonMap creation vừa qua `mon_down_uptime_grace` tính từ process start. Mute TTL parse exception rõ hơn và expiry chỉ propose khi thật sự có thay đổi. `mon status` thêm uptime; `mon ok-to-stop` trả `r=0` kèm chuỗi `invalid mon(s) specified` khi input có ID không tồn tại.

**Điều kiện và tác động:** sau mỗi target MON restart, thiếu MON có thể chưa phát cảnh báo trong uptime grace; watchdog chỉ dựa vào exit code của `ok-to-stop` có thể bỏ sót typo. Mixed output phụ thuộc MON phục vụ query. Risk trung bình nếu rollout/alert automation dùng các signal này; confidence high.

**Kiểm chứng:** restart target MON trong cluster cố ý thiếu một peer, đo thời điểm `MON_DOWN` so với cả hai grace. Test sticky/non-sticky mute với TTL hợp lệ, zero và malformed. Gọi `ok-to-stop` với ID đúng/sai và buộc parser kiểm cả JSON/message, không chỉ process exit code.

### MON-007 — MgrMap có persistent `FLAG_DOWN` và lệnh giữ toàn bộ MGR ở trạng thái down

**CSV:** `src/mon/MgrMap.h`, `src/mon/MgrMonitor.cc`, `src/mon/MgrMonitor.h`, `src/mon/MonCommands.h`. MgrMap encoding tăng 12→13, thêm/dump `flags`; `mgr set down true` đặt `FLAG_DOWN`, bỏ active hiện tại và chặn cả beacon activation lẫn standby promotion. Bỏ flag cho phép promote lại.

**Điều kiện và tác động:** chỉ kích hoạt khi operator/automation dùng lệnh mới; upgrade không tự hạ MGR. Đây là control hữu ích cho maintenance nhưng có thể làm orchestrator/dashboard/metrics mất active MGR có chủ đích. Suy luận thận trọng cho mixed MON: decoder cũ có thể bỏ qua tail field nhưng code Quincy không biết enforce/preserve flag trên proposal mới, nên chỉ dùng sau khi MON hội tụ và đã test failover. Risk trung bình-cao nếu dùng; confidence high cho target behavior.

**Kiểm chứng:** sau full MON target, đặt down với active+standby, kiểm không promote qua beacon/restart/election; unset và kiểm promotion/service map hồi phục. Lưu MgrMap epoch/flags và thử leader rotation để chứng minh flag không mất.

### MON-008 — MON client/address/auth path chặt hơn nhưng giữ fallback cho client cũ

**CSV:** `src/mon/MonMap.cc`, `src/mon/MonClient.cc`, `src/mon/Monitor.cc`, `src/mon/Monitor.h`, `src/messages/MMonCommand.h`. Khi encode MonMap cho peer thiếu MONENC/Nautilus, Reef tạo legacy address từ addrvec nếu không có v1 address rõ ràng. MonClient dùng dispatcher priority cao và `mon_client_target_rank` khi reconnect. Fast-auth chỉ thành công nếu session/caps thật sự được thiết lập; caps rỗng/hỏng trả `EACCES`. Crimson MON client copy command giữ tid/data để retry đúng request.

**Điều kiện và tác động:** legacy fallback áp dụng cho old client/monitor gặp v2-only MonMap; auth hardening lộ ra key/caps hỏng mà đường cũ có thể xử lý lỏng hơn; copy/retry chỉ liên quan Crimson. Trong mixed phase cần test cả old client→target MON và target client→old MON. Risk trung bình với legacy clients hoặc auth DB không sạch, cao nếu Crimson thật sự dùng; confidence high cho code, inventory client unknown.

**Kiểm chứng:** kết nối client Quincy qua v2-only MON addresses và xác minh discovery; thử valid/empty/corrupt cap payload phải có positive/negative result rõ. Buộc reconnect tới rank chỉ định; nếu có Crimson, ngắt kết nối giữa send/reply và kiểm retry giữ tid/data, không tạo hai mutation.

### MON-009 — MON store/tool thêm provenance nhưng không backfill store hiện hữu

**CSV:** `src/mon/MonitorDBStore.h`, `src/tools/monmaptool.cc`. `MonitorDBStore::create_and_open()` của Reef ghi `ceph_version_when_created` và `created_at`; `Monitor::collect_metadata()` xuất hai giá trị này. Store được tạo từ Quincy không tự nhận metadata vì open thường không chạy create path. Ngoài ra, `monmaptool --create` không truyền floor đổi default `min_mon_release` từ Octopus sang Pacific.

**Điều kiện và tác động:** store metadata chỉ có trên MON mới bootstrap/rebuild sau target; dashboard/inventory phải chấp nhận rỗng ở MON nâng tại chỗ. Default monmaptool chỉ tác động artifact mới/recovery, không rewrite MonMap hiện hữu. Risk thấp-trung bình nhưng quan trọng với provenance và disaster-recovery procedure; confidence high.

**Kiểm chứng:** so MON upgrade-in-place với MON target mới và store rebuild; xác minh metadata rỗng/có giá trị đúng, không giả thời điểm tạo từ thời điểm nâng. Tạo monmap target có/không explicit `--set-min-mon-release`, kiểm floor và bảo đảm runbook recovery luôn pin giá trị thay vì dựa default tool.

### MON-010 — Admin/health schema thêm signal mới; parser và stop/go cần chịu được

**CSV:** `src/mon/ConnectionTracker.cc`, `src/mon/MgrStatMonitor.h`, `src/mon/PGMap.cc`, `src/mon/PGMap.h`, `src/mon/Monitor.cc`, `src/osd/OSDMap.cc`. Reef đổi connection score `reports`/`peer_scores` thành JSON array, thêm monitor uptime và committed ranges, cho `pg dump_stuck` lọc `peering`, tổng hợp các alert BlueStore/block/DB/WAL stalled read, và thêm read-balance/primary-upmap fields vào OSDMap dump. Các signal này có thể làm health-based gate đổi dù dữ liệu/topology không đổi.

**Điều kiện và tác động:** áp dụng với parser JSON cứng schema, monitoring mới từ target OSD, hoặc automation dùng health/stuck output. Mixed cohort có thể thiếu alert từ OSD cũ và MON output phụ thuộc endpoint. Risk trung bình với custom tooling; confidence high cho schema, alert threshold/capacity được owner 01/02/06 đóng tiếp.

**Kiểm chứng:** replay golden JSON cũ/mới qua parser; tạo PG peering-stuck có kiểm soát và inject/giả lập device alert trong lab. Gate phải phân biệt signal mới với regression, đồng thời không coi field thiếu ở old daemon là lỗi dữ liệu.

### CFG-008 (cross-owner) — Runtime MON dùng một `mon_cluster_log_level` cho mọi external sink

**CSV owner 04:** `src/mon/LogMonitor.cc`, `src/mon/LogMonitor.h`; option schema thuộc [owner 06](./06-config-defaults.md#cfg-008--hai-key-log-level-mon-được-hợp-nhất-thành-một-key). Reef bỏ level riêng cho file/syslog ở runtime và lọc file, stderr, syslog, Graylog/Journald theo key chung trước khi gửi.

**Điều kiện và tác động:** MON có override hai key cũ hoặc pipeline trông đợi syslog `info` nhưng file `debug`. Sau từng target restart, old overrides không còn quyết định output; mixed MON có volume khác nhau. Confidence high. Kiểm bằng `qa/standalone/mon/mon-cluster-log.sh` trên file, syslog/Journald và alert consumer với mức debug/info/warn.

### MON-011 — Hoàn tất OSD rollout phát health gate Reef; nâng release floor là hành động một chiều

**CSV:** `src/mon/OSDMonitor.cc`, `src/mon/OSDMonitor.h`, `src/osd/OSDMap.cc`, `src/osd/OSDMap.h`, `src/mon/MonCommands.h`. Reef thêm `SERVER_REEF` vào OSDMap encoding/release inference. Khi mọi OSD đang up có feature Reef nhưng `require_osd_release < reef`, `OSDMap::check_health()` phát `OSD_UPGRADE_FINISHED`. Operator phải nâng `require_osd_release` bằng lệnh riêng; code không tự nâng và không cho hạ floor. Lệnh Reef kiểm cả persistent MON Reef feature và feature của up OSD. Target MON cũng từ chối OSD cũ hơn Pacific; cluster tạo mới mặc định require Reef.

**Điều kiện và tác động:** health warning xuất hiện sau toàn bộ **up OSD** target, nhưng OSD down/out cũ và rollback artifact vẫn phải inventory riêng. Nâng floor mở encoding Reef và kết thúc khả năng đưa OSD Quincy trở lại theo đường được hỗ trợ. Đây là boundary cao nhất của owner cùng MON-001; risk cao, confidence high.

**Kiểm chứng:** trong mixed OSD xác minh warning chưa xuất hiện sớm; sau hội tụ, đối chiếu version của cả up/down/out OSD, recovery media và MON persistent feature. Chỉ trong lab mới nâng floor, kiểm OSDMap encode/decode, OSD restart/map subscription và chứng minh floor không thể hạ. Production cần change riêng, không gộp vào binary rollout.

### MON-012 — Reef thêm `pg_upmap_primary` và read balancer, nhưng chỉ là opt-in sau compatibility floor

**CSV:** `src/osd/OSDMap.cc`, `src/osd/OSDMap.h`, `src/mon/OSDMonitor.cc`, `src/mon/OSDMonitor.h`, `src/mon/MonCommands.h`, `src/tools/osdmaptool.cc`. OSDMap thêm persisted `pg_upmap_primaries`, encoding Reef, command set/remove và thuật toán `balance_primaries()`/read-balance score. Mapping chỉ chọn primary mới trong acting set hợp lệ; `osdmaptool --read` sinh command để áp dụng. Command yêu cầu `require_min_compat_client >= reef` và cluster có `SERVER_REEF`; chỉ replicated pool được hỗ trợ.

**Điều kiện và tác động:** không tự bật khi upgrade. Opt-in này nâng client compatibility floor và tạo state Quincy không hiểu, nên chỉ xem xét sau full daemon/client inventory và sau khi rollback boundary được chấp nhận. Nó đổi phân bố read-primary, không được suy là tự cải thiện workload. Risk trung bình-cao khi dùng; confidence high cho gate/encoding, performance unknown.

**Kiểm chứng:** trên snapshot OSDMap, chạy osdmaptool offline để review proposal; trước gate phải bị từ chối. Sau full target lab, áp ít mapping, kiểm acting set/CRUSH legality, read-balance score, primary distribution, client I/O và remove-all rollback. Benchmark read-heavy và recovery, không lấy score nội bộ thay latency/throughput thật.

### MON-013 — OSD/pool command thêm safety contract và nhánh Crimson experimental

**CSV:** `src/mon/OSDMonitor.cc`, `src/mon/OSDMonitor.h`, `src/mon/MonCommands.h`. Reef yêu cầu cả `--force` và `--yes-i-really-mean-it` khi ghi đè erasure-code profile; chặn tạo/rename pool bắt đầu bằng `.` nếu không có internal confirmation; thêm `osd pool force-remove-snap` có dry-run; tôn trọng `nopgchange` khi đổi PG count. `osd set-allow-crimson` là flag không đảo ngược, cần experimental feature; Crimson pool phải replicated, autoscale off, giữ `nopgchange`, và Crimson OSD không boot nếu flag chưa đặt.

**Điều kiện và tác động:** automation cũ ghi đè EC profile hoặc dùng dot-prefixed pool có thể đổi từ success sang refusal. Snapshot repair là thao tác phá state có phạm vi riêng, không phải aftercare mặc định. Crimson không áp dụng cho BlueStore/classic OSD và không được bật chỉ để hoàn thành upgrade. Mixed semantics phụ thuộc target MON leader. Risk cao với destructive commands/Crimson, thấp nếu không dùng; confidence high.

**Kiểm chứng:** negative-test automation EC/dot-pool/nopgchange và xác minh không có mutation khi thiếu confirmation. Với leaked snap chỉ dùng fixture, chạy dry-run rồi đối chiếu snap range/epoch. Crimson chỉ test trong môi trường disposable với explicit experimental config, replicated static pool, boot gate và không tuyên bố production support.

## Operational closure addenda

#### MON-002 — Closure

Rollback không đảo Paxos commit: canary chỉ failback leader/binary sau khi xác nhận `last_committed` và retry ledger không có mutation treo/nhân đôi. Giữ old quorum majority cho tới fault-injection PASS; nếu command trả EAGAIN thì retry idempotent, không suy thất bại hay success từ timeout.

#### MON-003 — Closure

Rollback stretch/election là restore verified MonMap/election config và binary trước topology mutation, không tự bỏ marked-down state. Mixed leader rotation phải được rehearsal; full-Reef chỉ sau partition/recovery PASS. Nếu topology thực chưa biết thì giữ `UNKNOWN`, không đổi strategy trong window.

#### MON-004 — Closure

Rollback là pin exporter/parser canonicalization hoặc old CLI, không rewrite config DB chỉ để lấy spelling cũ. Chưa có inventory alias/non-canonical keys hay consumers; mixed/full validation phải diff effective values riêng với presentation names và lưu golden JSON.

#### MON-005 — Closure

Chưa có CephFS As-Is nên flags/xattr/failover applicability còn `UNKNOWN`. Rollback của command mutation cần exported FSMap/pool tags và command-specific rehearsal; `fs swap`/forced fail không có generic inverse. Mixed MDS/MON không dùng control mới; validation phải giữ pre/post epoch, health và client access.

#### MON-006 — Closure

Rollback bằng restore alert/parser/runbook hoặc old MON sau quorum-safe restart; không chỉnh grace chỉ để che warning. Mixed/full phải version-tag JSON/message and time-to-alert. Gate lưu process/MonMap timestamps, mute state và invalid-ID results.

#### MON-007 — Closure

Flag chỉ kích hoạt bằng explicit command sau full MON target. Rollback là `mgr set down false` rồi chứng minh promotion/service-map hồi phục; nếu active đã bị bỏ thì không giả định immediate failback. Lưu MgrMap epoch/flags qua leader rotation.

#### MON-008 — Closure

Legacy fallback/auth checks tự động chạy khi connect/reconnect; target-rank selection là config. Rollback canary bằng route client về old MON và restore config only before auth/control-state mutation; không sửa caps mù. Mixed/full validation cần positive/negative credential corpus, tid/data replay và inventory legacy clients.

#### MON-009 — Closure

Mixed fleet phải chấp nhận metadata chỉ có trên MON mới tạo; full-Reef không được backfill giả. Rollback recovery tooling bằng pinned monmaptool and explicit floor, còn store rebuild yêu cầu snapshot/restore rehearsal. Chưa có DR artifact/store provenance inventory; validation so in-place/new/rebuilt store.

#### MON-010 — Closure

Rollback là dual-schema parser/collector và old query endpoint; health fields đã phát không cần state rollback. Mixed/full gate phải replay golden JSON và alert fixtures trước khi dùng signal mới làm STOP. Không suppress unknown field để che parse failure.

#### CFG-008 — Closure

Rollback bằng pin explicit `mon_cluster_log_level`, restore collector routing và restart từng MON quorum-safe; log đã mất/đã phát không thể tái tạo. Mixed/full phải kiểm volume từng sink và audit completeness trước khi bỏ hai-key compatibility.

#### MON-012 — Closure

Không dùng trong mixed-version; chỉ full-Reef sau client floor inventory và chấp nhận boundary. Rollback feature là remove mappings, nhưng compatibility floor đã nâng không thể hạ, nên mapping removal không phải binary failback. Benchmark thật và OSDMap snapshot là bắt buộc.

#### MON-013 — Closure

Rollback phụ thuộc command: refusal không mutate; EC/pool/snap mutation cần pre-state manifest/snapshot và inverse riêng đã rehearsal. Crimson allow flag là irreversible theo source nên không bật trong upgrade lane. Mixed/full command automation phải kiểm cả confirmations, exit code và observed epoch.

## Trivial changes

**64 hàng:** 8 documentation, 45 test/QA và 11 runtime/source. Documentation thêm/chỉnh runbook, manpage, CRUSH/monitor prose nhưng không thay binary hay executable acceptance path của suite. Test/QA cung cấp bằng chứng cho feature Reef, commit timing, stretch health, log level, command confirmations và formatter schema; chúng không phải artifact cluster. Mười một runtime row còn lại là namespace/include/signature/RAII/sample cleanup hoặc print-call adaptation không có causal path độc lập tới rollout. Lý do từng hàng và cross-finding support nằm trong CSV.

## Validation và giới hạn

Chưa chạy build, repository test, lab hay cluster command. Gate ưu tiên theo thứ tự: (1) xác định/diễn tập MON-001 trước full Reef quorum; (2) test MON-002 dưới election; (3) inventory toàn bộ OSD và chốt MON-011 trước khi nâng release floor; (4) migration CephFS/log key nếu áp dụng; (5) parser health/admin schema; (6) chỉ sau đó mới xem xét pg-upmap-primary hoặc command mới. Stretch, CephFS, legacy client và Crimson phải có applicability từ As-Is; UNKNOWN không được đổi thành N/A bằng suy đoán. Báo cáo này không cấp quyền thay feature floor, MonMap/OSDMap, pool, snap, auth hay production config.

