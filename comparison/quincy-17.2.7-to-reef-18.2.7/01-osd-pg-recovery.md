# 01 — OSD, PG, peering, recovery và scrub: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./01-osd-pg-recovery.csv) có 350 hàng và là subset đúng thứ tự của master inventory: `affect = 160`, `trivial = 190`, chưa phân loại = 0. Các finding dưới đây tách đường classic OSD và Crimson; thay đổi Crimson chỉ áp dụng khi deployment thực sự build/chạy Crimson OSD.

## Phạm vi và giới hạn bằng chứng

So sánh là endpoint net diff giữa `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) và `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor; `git log` chỉ trả commit tag đích nên không đủ lịch sử để gán commit intent. Kết luận dựa trên hunk, symbol/caller và test ở hai endpoint; gap lịch sử được giữ rõ thay vì suy từ release family.

Chưa có As-Is về scheduler, EC pools, blocked scrub, legacy peer/client floor, Crimson OSD/SeaStore, dashboard/parser hay tool automation. Chưa chạy build, unit/QA, mixed-version lab, fault injection hoặc canary. Vì vậy report này khép binary classification nhưng không cấp GO/NO-GO production.

## Finding ảnh hưởng upgrade

### OSD-001 — OSD superblock có bản sao omap và đường phục hồi mới

**Evidence.** `OSD.cc` ghi superblock vào object và omap key `OSD_SUPERBLOCK_OMAP_KEY`; khi mở store, target đọc cả hai bản, kiểm decode/current epoch và chọn bản có thể phục hồi. `osd_types.h` thêm key, còn `ceph_objectstore_tool.cc` thêm `get-superblock`/`set-superblock`.

**Before/after.** Quincy dựa vào object superblock; Reef duy trì bản sao omap và có thể chọn bản mới hơn khi một phía thiếu/hỏng. Điều này có hiệu lực theo từng OSD khi target khởi động/ghi store. Mixed fleet không chia local superblock, nhưng sau khi Reef ghi state mới, failback bằng Quincy chưa được chứng minh. Tác động activation/recovery/rollback; confidence `high` cho code path, runtime compatibility còn `UNKNOWN`.

### OSD-002 — Startup và fast shutdown thay đổi dependency/lifecycle

**Evidence.** `ceph_osd.cc` preload external-block-device plugin; `OSD.cc/.h` đổi init/start/stop, fast-shutdown timeout/cleanup và ObjectStore interaction. Target cũng đổi cách tạo daemon nonce.

**Before/after.** Reef có thể fail sớm vì plugin/dependency hoặc dừng theo ordering/timeout khác Quincy. Điều kiện extblkdev/SPDK và fast shutdown phải lấy từ As-Is. Tác động availability/delivery; confidence `high` cho branch, `medium` cho applicability.

### WIRE-001 — Bỏ legacy PGCreate/Scrub và đổi feature propagation của peering

**Evidence.** `MOSDPGCreate.h` và `MOSDScrub.h` bị xóa; callers target dùng `MOSDPGCreate2`/`MOSDScrub2`. `MOSDPeeringOp.h` và `MOSDPGNotify2.h` giữ peer feature bits cho Crimson vì connection không còn nằm trực tiếp trên message; `MOSDOp.h` đổi transaction-id/feature handling.

**Before/after.** Quincy còn decoder/handler cho legacy message dùng với release rất cũ; Reef endpoint không còn đường đó. Hop Quincy→Reef bình thường phải dùng v2, nhưng rollout chỉ an toàn khi inventory loại trừ endpoint trước Mimic/automation phụ thuộc legacy message. Tác động mixed-version/wire compatibility; confidence `high` cho removal, applicability legacy peer `UNKNOWN`.

### SCHED-001 — mClock có strict-priority queue và cost động

**Evidence.** `OSD.cc` snapshot scheduler type/cutoff lúc dựng daemon và từ chối cấu hình không hợp lệ. `mClockScheduler.*` thay immediate list bằng `high_priority` map theo priority; op trên cutoff bypass dmClock. Scrub, snaptrim và PG-delete cost lấy theo object/chunk thay vì hằng số; queue counters cũng đổi.

**Before/after.** Cùng workload/config có thể được admit và sắp thứ tự khác sau restart target, đặc biệt client high-priority cạnh tranh recovery/scrub. Mixed fleet có scheduler behavior theo OSD đang xử lý request. Cần chốt scheduler/effective config, baseline client latency và recovery budget trước canary. Tác động performance/availability; confidence `high`.

### PEERING-001 — Peering bounds và điều kiện async EC recovery đổi

**Evidence.** `PeeringState.cc/.h` cho phép bypass kiểm tra past-interval bounds bằng `osd_skip_check_past_interval_bounds`; khi chọn async EC recovery, target giữ đủ shard để không vi phạm pool `min_size`.

**Before/after.** Quincy có thể assert/fail peering khi bounds không hợp lệ và có thể loại expensive EC shard mà không áp cùng guard; Reef có đường override và guard min_size. Override không phải mặc định để bật hàng loạt: chỉ dùng sau chẩn đoán, vì nó bỏ một invariant. Tác động peering/recovery availability; confidence `high`.

### RECOVERY-001 — PG log, missing set và recovery/repair được sửa

**Evidence.** `PGLog.*` thêm đường rebuild missing set có delete và paged omap read; `PG.*`, `PGBackend.*` và `ECBackend.*` đổi activation/recovery integration và repaired-object accounting. Peering lựa chọn EC shard được guard bởi min_size.

**Before/after.** Khi restart/peering, Reef có thể dựng missing state và chọn recovery source khác Quincy; EC repair counters cũng phản ánh propagated repair state. Mixed-version cần xoay primary và gây degraded/recovery thật, không chỉ kiểm `active+clean`. Tác động correctness/availability; confidence `high` cho source behavior, chưa fault-inject.

### SCRUB-001 — Scrub backend và correctness/repair path được viết lại

**Evidence.** Target thêm `scrub_backend.cc/.h`, rút logic khỏi `PGBackend`, và thay đáng kể `PrimaryLogScrub`, `pg_scrubber`, scrub state machine/store. `ScrubMap::swap()` nay swap cả `has_large_omap_object_errors` và `has_omap_keys`; EC deep scrub dùng `BYPASS_CLEAN_CACHE` và sửa repair accounting.

**Before/after.** Reef có backend/state ownership mới và giữ đúng các summary flags khi swap map; finding/repair có thể khác ngay trên dữ liệu cũ. Tác động data correctness; confidence `high`. Phải so inconsistent set/digest trên clone và hoàn tất deep scrub mới cho từng handoff set, không suy từ lịch test trong source.

### SCRUB-002 — Lập lịch scrub, blocked state và health signal đổi

**Evidence.** `osd_scrub_sched.*`, `pg_scrubber.*`, `scrub_machine.*` đổi reservation/schedule và cost; object lock bị chặn được ghi thành scrub status `blocked`, và OSD công bố warning/counter liên quan.

**Before/after.** Scrub target có thể đợi, tốn cost và báo health khác base; alert parser cũ có thể coi signal mới là failure không mong đợi hoặc bỏ sót blocked PG. Mixed fleet phát behavior/schema theo daemon. Tác động observability/maintenance latency; confidence `high`.

### IO-001 — Ordering của op đọc dữ liệu và kết quả extent/truncate đổi

**Evidence.** `osd_op_util.*` thêm `may_read_data()` để flush write trước watch/read-capable op. `PrimaryLogPG::finish_extent_cmp()` đổi iterator; truncate xóa data digest/flag cũ khi size đổi.

**Before/after.** Reef cưỡng chế ordering cho các op có thể đọc và tránh giữ digest không còn hợp lệ sau truncate; kết quả compare/read-after-write có thể khác Quincy ở cạnh tranh. Tác động client-visible correctness; confidence `high`.

### SNAP-001 — SnapMapper và purged-snap persistence đổi

**Evidence.** `SnapMapper.*` được tách theo driver để dùng cả classic/Crimson, thêm traversal next-or-current và thay đường ghi purged snaps; `PG.*`/PrimaryLogPG cập nhật caller và snaptrim interaction.

**Before/after.** Target tìm/ghi snap mapping và purged-snap metadata theo contract mới. Áp dụng khi pool dùng snapshots/clones hoặc đang có snaptrim backlog; mixed fleet cần xoay primary trên PG có snap activity. Tác động metadata cleanup/recovery; confidence `high`.

### WATCH-001 — Watch timeout vẫn được đăng ký khi session đã mất

**Evidence.** `Watch.cc` đăng ký timeout cả khi connection session đã null thay vì bỏ qua cleanup.

**Before/after.** Stale watch có thể được dọn đúng hạn ở Reef trong case disconnect race mà Quincy giữ lâu hơn. Tác động client reconnect/notification; confidence `high`, applicability phụ thuộc workload watch/notify.

### OSDOBS-001 — Timestamp và metric visibility của OSD đổi

**Evidence.** `OpRequest.*` bắt đầu latency từ receive stamp thay cho throttle stamp; `osd_perf_counters.cc` đưa `op_before_queue_op_lat` ra khỏi nhóm debug-only.

**Before/after.** Series latency và metric set target không hoàn toàn so trực tiếp với Quincy. Dashboard/alert phải gắn version/schema; không dùng discontinuity này một mình để kết luận regression. Tác động validation/observability; confidence `high`.

### CRIMSONCTRL-001 — Crimson đổi startup, auth, CRUSH location và control plane

**Evidence.** `crimson/auth/*`, `mon/MonClient.*` và `mgr/client.*` đổi connection/auth, rotating keys và config exchange. `crimson/crush/CrushLocation.*` mới đọc config/hook/default hostname. `crimson/osd/main*`, heartbeat, osdmap gate/service, shard manager và state đổi đáng kể.

**Before/after.** Crimson Reef có bootstrap, placement identity, mon/mgr reconnect và shard lifecycle khác Quincy. Finding chỉ áp dụng nếu có Crimson OSD; classic OSD không đi qua code này. Tác động activation/placement/control-plane; confidence `high` cho code, applicability `UNKNOWN`.

### CRIMSONSTORE-001 — AlienStore/CyanStore/FuturizedStore contract đổi

**Evidence.** `crimson/os/alienstore/*`, `cyanstore/*` và `futurized_store.*` đổi lifecycle, collection access, thread-pool và transaction interface mà Crimson OSD gọi.

**Before/after.** Backend Crimson được start/mount/submit qua contract mới; behavior khác classic BlueStore và phải kiểm cùng backend thực tế. Liên hệ owner 02 cho thay đổi SeaStore format sâu hơn. Tác động store activation/I/O; confidence `high`, compatibility in-place chưa chứng minh.

### CRIMSONIO-001 — Crimson client request/object pipeline đổi

**Evidence.** `object_context*`, `ops_executer*`, `osd_operation*`, client/internal request, pg backend, watch và Crimson mClock scheduler đổi sequencing, interruption và completion.

**Before/after.** Client request trên Crimson target có ordering/cancellation/lock/response khác source. Cần workload read/write/omap/cls/watch chạy qua primary Crimson cũ và mới. Tác động correctness/latency; confidence `high` cho branch, chưa runtime-test.

### CRIMSONRECOVERY-001 — Crimson peering/recovery/backfill pipeline đổi rộng

**Evidence.** `backfill_state`, EC/replicated recovery backend, PG recovery/meta/map, background recovery, logmissing, peering event, PG map advance, replicated request và snaptrim operation đều đổi.

**Before/after.** Reef điều phối PG convergence, missing exchange, recovery subrequest và snaptrim qua pipeline mới. Chỉ áp dụng Crimson; nếu có thì không thể đóng bằng clean-start smoke test. Tác động degraded recovery/data availability; confidence `high`.

### CRIMSONOBS-001 — Crimson admin/PG commands và output đổi

**Evidence.** `crimson/admin/admin_socket.*`, `osd_admin.*` và `pg_commands.cc` đổi registration, validation và output của command.

**Before/after.** Script/runbook dùng admin socket có thể nhận field/error khác sau upgrade. Cần capture raw output theo version trước khi dùng làm stop condition. Tác động observability/operations; confidence `high`.

### FILESTORE-001 — Reef không còn đường kích hoạt FileStore

**Evidence.** `ObjectStore.cc` trả null/không probe `filestore`; helper `os/fs/btrfs_ioctl.h` bị xóa. Đây là cùng finding đã chứng minh đầy đủ ở [owner 02](./02-bluestore-bluefs.md).

**Before/after.** Nếu inventory còn OSD FileStore, binary Reef không có backend để mở store. Phải migrate/reprovision theo data-movement plan riêng trước hop; không thử khởi động Reef rồi mới xử lý. Tác động delivery/data availability; confidence `high`, applicability `UNKNOWN`.

## Operational closure addenda

Các addendum dưới đây làm rõ gate còn thiếu của từng finding; chúng không thay đổi trạng thái `NOT_RUN` và không cấp quyền chạy trên production.

#### OSD-001 — Closure

Kích hoạt tự động ở target OSD startup và mỗi lần superblock được ghi. Kiểm chứng trên clone phải fault-inject từng bản object/omap, so epoch được chọn, restart lần hai và thử failback Quincy chỉ trên copy; rollback sau Reef write vẫn `UNKNOWN`.

#### OSD-002 — Closure

Applicability phụ thuộc plugin/fast-shutdown config; path tự động chạy ở restart/TERM. Mixed cohort phải drain/restart đúng một OSD, full-Reef mới kiểm shutdown đồng loạt theo failure domain. Rollback là khôi phục artifact/plugin/config rồi start old binary khi local-store gate còn cho phép. Chưa có dependency inventory hay startup/shutdown trace; lab phải giữ exit code, timeout và PG availability.

#### WIRE-001 — Closure

Legacy/v2 selection tự động theo peer feature negotiation; không có operator toggle để cứu peer không còn decoder. Mixed-version phải xoay primary và capture message/decode logs; full-Reef xác nhận không còn endpoint dưới floor. Rollback là giữ old cohort cho tới khi peer inventory sạch; sau khi nâng compatibility floor thì phải hạ floor có kiểm soát trước failback. Kiểm chứng exact-tag chưa chạy.

#### SCHED-001 — Closure

Áp dụng khi OSD dùng mClock hoặc workload đi qua strict-priority cutoff; scheduler được chọn tự động ở daemon start, tuning là explicit config. Rollback canary bằng restore effective profile/cutoff và restart một OSD sau drain; không trộn metric schema khi so. Cần lab client+recovery+scrub để đóng latency/starvation gap.

#### PEERING-001 — Closure

Guard recovery chạy tự động khi peering/EC recovery; past-interval bypass chỉ là explicit diagnostic action. Mixed/full phải xoay primary và fault shard trên replicated/EC pools, không bật override mặc định. Rollback là bỏ override/restore config và quay primary về cohort cũ nếu PG state cho phép. Chưa có As-Is EC/min_size hay fault-injection artifact; validation phải chứng minh convergence và invariant min_size.

#### RECOVERY-001 — Closure

Recovery/rebuild missing set tự động khi PG activate/degrade. Mixed cohort phải gây log gap/delete và đổi primary; full-Reef lặp restart/backfill. Rollback chỉ trước target recovery mutation hoặc qua clone/snapshot; không đảo ngược repair bằng counter. Kiểm chứng cần object manifest, missing set, repaired-object counters và checksum sau convergence.

#### SCRUB-001 — Closure

Mixed-version phải scrub/deep-scrub cùng fixture khi primary lần lượt ở Quincy/Reef; full-Reef kiểm restart state machine. Repair có thể mutate object nên rollback boundary là trước target repair: giữ immutable clone và không repair production trong gate. Kiểm chứng so inconsistent set, digest, repair ledger và post-scrub checksum.

#### SCRUB-002 — Closure

Áp dụng khi scrub schedule/reservation gặp contention hoặc locked object; scheduling tự động, forced scrub là explicit. Mixed cohort phát schema khác nên dashboard phải version-aware; full-Reef kiểm blocked→clear. Rollback bằng restore schedule/config và parser, không xóa state mù. Chưa có blocked fixture; lab phải lưu reservation, status, health và completion timestamps.

#### IO-001 — Closure

Ordering/digest behavior tự động trên relevant read/write/truncate requests. Mixed-version phải route cùng concurrency fixture tới primary cũ/mới; full-Reef lặp sau restart. Rollback của Reef-written/truncated object cần immutable version/copy và old-reader proof. Chưa có race reproduction; kiểm chứng bằng operation trace, return codes, digest flags và data checksum.

#### SNAP-001 — Closure

Áp dụng khi snap/clone/snaptrim state tồn tại; mapper/persistence tự động chạy khi primary xử lý snapshot activity. Mixed/full phải đổi primary với backlog thật. Rollback sau purged-snap write chỉ trên clone hoặc từ metadata backup. Kiểm chứng cần mapper entries, purged-snap state, object listing và checksum trước/sau trim.

#### WATCH-001 — Closure

Timeout registration tự động trong disconnect race; áp dụng cho watch/notify workloads. Mixed cohort phải reconnect qua primary cũ/mới, full-Reef kiểm cleanup sau restart. Rollback đơn giản là route/restart old cohort trước target-side mutation, nhưng notification đã mất/đã giao cần event-ledger reconciliation. Chưa có workload inventory; validation lưu cookie, timeout, callback và duplicate/loss result.

#### OSDOBS-001 — Closure

Áp dụng cho dashboards/alerts tiêu thụ latency/perf counters; schema mới tự động xuất hiện khi OSD target chạy. Mixed/full phải tag series theo version và giữ dual queries. Rollback là restore collector/rule, không sửa lịch sử metric. Chưa có consumer inventory và baseline; kiểm chứng so raw admin-socket output, labels, units và alert replay.

#### CRIMSONCTRL-001 — Closure

Nếu inventory xác nhận Crimson, path tự động chạy ở bootstrap/reconnect/config exchange. Mixed-version phải canary một shard/OSD và giữ placement identity; full-Reef kiểm repeated reconnect. Rollback bằng drain và old artifact chỉ sau SeaStore/local-state compatibility proof. Chưa biết applicability; validation cần build/runtime evidence, CRUSH location, auth rotation và mon/mgr reconnect trace.

#### CRIMSONSTORE-001 — Closure

Chỉ áp dụng cho configured Alien/Cyan/FuturizedStore; mount/start/transaction contract tự động kích hoạt ở restart. Mixed/full phải dùng exact backend fixture, không thay bằng classic BlueStore. Target write là rollback boundary; old mount chỉ thử trên copy. Kiểm chứng cần mkfs-format evidence, mount/write/restart/crash-replay và checksum.

#### CRIMSONIO-001 — Closure

Chỉ áp dụng cho Crimson request path; sequencing tự động theo mỗi request. Mixed-version phải xoay primary giữa old/new Crimson, full-Reef kiểm cancel/restart. Rollback Reef-written state cần clone/version and old-reader proof. Lab phải replay read/write/omap/cls/watch với trace, errno, latency và hash; runtime result hiện chưa có.

#### CRIMSONRECOVERY-001 — Closure

Recovery pipeline tự động kích hoạt khi degraded/backfill/snaptrim; clean-start smoke không đủ. Mixed/full phải fault shard, đổi primary và restart giữa recovery. Rollback sau target journal/recovery write là `UNKNOWN`, chỉ thử trên copy. Chưa có Crimson topology/fixture; validation cần missing/log exchange, progress, convergence và checksum.

#### CRIMSONOBS-001 — Closure

Admin output tự động đổi khi target command handler chạy; mutation command vẫn explicit. Mixed/full phải lưu golden output cho old/new daemon và parser dual-schema. Rollback bằng pin old tool/parser; command side effect cần gate riêng. Chưa có runbook consumer inventory; kiểm chứng phải giữ stdout/stderr, exit code và parsed stop/go result.

## Trivial changes

190 hàng `trivial` đã được đọc và giữ trong CSV: 15 tài liệu; 155 test/QA/suite/workload rows chưa được chạy nên chỉ là evidence hỗ trợ; 20 runtime rows là formatter/include/log-only, additive object-class API, DBObjectMap/SequencerPosition relocation cho diagnostic, `ceph_osdomap_tool` include update, leak-sanitizer suppression và Crimson benchmark/NBD development tools. Không hàng nào được hạ chỉ vì diff nhỏ; companion runtime có state/wire/scheduling behavior thật đã được promote riêng.

## Validation đề xuất

Các scenario sau là thiết kế kiểm chứng, chưa được thực thi và không cấp quyền thao tác production.

1. **Prerequisite inventory:** xác nhận mọi OSD backend, classic/Crimson, scheduler/effective config, EC/min_size, pool snap/watch usage và oldest daemon/client. FileStore còn tồn tại là `BLOCKED`; Crimson không có bằng chứng đáng tin cậy thì các CRIMSON finding vẫn `UNKNOWN`, không tự `N_A`.
2. **Superblock/restart:** trên clone OSD Quincy, clean restart Reef rồi fault-inject object/omap superblock từng phía; xác nhận target chọn đúng epoch, `ceph-objectstore-tool get/set-superblock` thao tác đúng copy và restart lần hai sạch. Thử rollback chỉ trên copy.
3. **Mixed wire/peering:** dựng Quincy/Reef OSD, xoay primary, PG create/scrub/notify; xác nhận dùng message v2, không decode error và không có peer dưới release floor.
4. **Scheduler profile:** replay cùng client + recovery + scrub workload trên WPQ/mClock thực tế; thu queue/cost, p95/p99 latency, recovery throughput và starvation. Giữ metric schema theo version.
5. **Peering/recovery fault matrix:** replicated và EC pool; down/out shard, missing/delete, log gap, backfill và EIO injection. Kỳ vọng không vi phạm min_size, PG hội tụ và repaired-object counters hợp lý. Không bật past-interval bypass nếu chưa có case tái hiện và phê duyệt riêng.
6. **Scrub correctness:** dữ liệu gồm omap lớn, clone/snap, EC corruption và locked object; so inconsistent set/digest, repair result, blocked status và health warning. Deep scrub PRE_HANDOFF và POST_HANDOFF phải có completion evidence riêng.
7. **I/O/watch/snap:** cạnh tranh write→read/extent-compare/truncate, watch disconnect/reconnect và snaptrim backlog khi primary đổi version; kiểm checksum, digest invalidation, callback và purged-snap state.
8. **Crimson conditional lane:** nếu dùng Crimson, chạy riêng bootstrap/auth/CRUSH hook, mon/mgr reconnect, backend mount/write/restart, client/cls/watch và degraded recovery/backfill. Không dùng kết quả classic OSD thay thế.
9. **Operational tools:** rehearsal parser cho `ceph-objectstore-tool`, classic/Crimson admin socket và perf counters; version-tag raw output trước khi biến chúng thành STOP/GO gate.

## Kết luận owner

Owner 01 đã khép binary gate nhưng còn các prerequisite chặn quyết định rollout: loại trừ FileStore/legacy peers, xác định classic hay Crimson, chốt scheduler và chứng minh superblock/recovery/scrub trên clone đúng cấu hình. Với classic BlueStore, trọng tâm canary là restart + mixed peering/recovery/scrub; nếu Crimson hiện diện, cần lane compatibility và recovery riêng vì thay đổi control/store/operation pipeline đủ rộng để không suy từ classic OSD.

