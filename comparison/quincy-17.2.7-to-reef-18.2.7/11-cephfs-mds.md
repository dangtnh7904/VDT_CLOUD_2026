# 11 — CephFS, MDS, client sessions và volumes: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./11-cephfs-mds.csv) có 573 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 186`, `trivial = 387`, chưa phân loại = 0. Detailed findings chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow/non-ancestor; evidence là endpoint hunk, encoder/decoder, caller, suite graph và persisted-schema path, không phải commit-range đầy đủ.

Chưa có CephFS As-Is: filesystem/rank/standby topology, active sessions/client kernels, FUSE/libcephfs versions, auth caps/root-squash, snapshots/fscrypt, NFS exports, subvolumes/clones/schedules, mirror peers, metadata damage hoặc artifact digest đều `UNKNOWN`. Chưa chạy teuthology, failover, journal replay hay mount/client matrix. Không có finding nào dưới đây cấp quyền `fail fs`, evict client, tăng required feature, sửa journal, purge metadata hoặc thao tác production.

## Finding ảnh hưởng upgrade

### CFSVAL-001 — Có matrix CephFS Quincy→Reef nhưng chưa có exact-tag result

**Evidence.** 59 hàng relevant dưới `qa/suites/fs/upgrade` bao phủ MDS upgrade sequence, `fail_fs` on/off, staggered MGR, FUSE/kernel clients, concurrent fsstress, final `fs.post_upgrade_checks`, no-filesystem upgrade và featureful old/upgraded-client cases. Suite client chủ động thêm `metric_collect` vào `required_client_features` rồi kiểm old client bị evict còn upgraded client vẫn sống.

**Before/after.** Đây là coverage source cho đúng major hop nhưng các task vẫn dùng branch/package selector và `$sha1`, không khóa exact `v17.2.7`/`v18.2.7`; không có run archive. Test chủ động nâng required feature không được nhầm thành hành vi tự động của upgrade. Gate phải chạy exact artifacts cho fail_fs on/off, active workloads, old/new kernel và FUSE clients, lưu session list, feature bits, MDS states, health và data checksum.

**Điều kiện, mixed/full, rollback và độ tin cậy.** Áp dụng cho mọi filesystem định rollout MDS hoặc client; test chỉ được kích hoạt khi operator chạy suite, còn required-feature injection là hành động tường minh. Pha mixed phải giữ client floor cũ và chứng minh old/new clients qua từng rank; pha full-Reef mới được đánh giá feature mới. Tác động của gap là chưa thể dùng suite source làm bằng chứng chấp nhận availability/correctness. Vì suite dùng dữ liệu disposable, rollback là hủy run/khôi phục fixture chứ không suy ra daemon downgrade an toàn. Confidence `high` cho tồn tại coverage, `none` cho kết quả exact hop; gap còn lại là archive chạy với exact digest.

### CFSWIRE-001 — Session feature negotiation và message payload đổi

**Evidence.** Target thêm `CEPHFS_FEATURE_NEW_SNAPREALM_INFO` (19), `HAS_OWNER_UIDGID` (20), `MDS_AUTH_CAPS_CHECK` (21); request/reply/session/caps messages có thêm feature-gated owner, fscrypt và snapshot fields. Client giờ refresh `session->mds_features` khi nhận session-open ngay cả session đã open, với comment nêu MDS có thể vừa được upgrade.

**Before/after.** Quincy client/MDS không quảng bá cùng feature set với Reef. Mixed-version được thiết kế qua feature gating; hunk không chứng minh wire break mặc định. Rủi ro phát sinh khi operator nâng `required_client_features`, dùng feature mới với client cũ hoặc session không renegotiate như kỳ vọng. Kiểm session reconnect/refresh qua từng rank upgrade và không nâng compatibility floor trước client inventory.

**Kích hoạt, rollback và kiểm chứng.** Refresh feature là tự động khi session-open/reconnect tới MDS mới; nâng floor hoặc dùng snaprealm/fscrypt field mới là explicit. Trong mixed-version phải so advertised/required bits và request decode ở cả hai chiều; full-Reef phải reconnect toàn bộ session ít nhất một lần. Rollback binary chỉ còn ứng viên trước khi target ghi metadata/feature mới và phải được chứng minh trên clone; nếu đã nâng floor thì hạ floor có kiểm soát trước failback. Confidence `high` ở wire gating, runtime `UNKNOWN`; chưa có packet/session trace exact-tag.

### CFSSESSION-001 — Root-squash, client refusal và laggy-OSD eviction đổi

**Evidence.** Target phát hiện client thiếu `MDS_AUTH_CAPS_CHECK` khi auth cap có `root_squash`, ghi health error “broken root_squash” và libcephfs có compatibility handling. MDSMap thêm `refuse_client_session`; open/reconnect trả lỗi khi flag bật. `defer_client_eviction_on_laggy_osds` giữ client laggy thay vì evict khi OSD laggy, đồng thời phát health warning; session/cap sequence/release logic cũng đổi.

**Before/after.** Old client dưới root-squash có thể bị cảnh báo/hạn chế khác; client không phản hồi có thể được giữ lại trong OSD incident thay vì blocklist/evict ngay; flag từ chối session chặn mount mới/reconnect. Tác động mixed client availability và security conditional; confidence `high`, applicability `UNKNOWN`. Test root/non-root, root-squash, reconnect, OSD lag và recovery; inventory config/flags trước rollout.

**Kích hoạt và rollback.** Root-squash compatibility chạy tự động khi caps/session được kiểm; `refuse_client_session` và eviction deferral chỉ đổi khi operator/config bật hoặc OSD thực sự laggy. Mixed-version phải kiểm cùng client qua rank cũ/mới; full-Reef phải quan sát health clear sau recovery. Rollback là trả flag/config về baseline và xác minh session reconnect; blocklist/eviction đã xảy ra không tự hoàn tác. Gap còn lại là As-Is caps, flag và client-feature inventory.

### CFSFAIL-001 — Rank/standby/failover và shutdown control path đổi

**Evidence.** `FSMap`, `MDSMap`, `MDSRank`, beacon/server dispatch và migration paths đổi standby selection, stop/erase behavior, admin commands, shutdown/purge waits, rank messaging và client reconnect. Health output bỏ misleading cache counters trên standby-replay. Exact-hop suite có fail_fs and restart sequences nhưng chưa chạy ở đây.

**Before/after.** Failover timing và rank/standby eligibility có thể khác trong mixed MDS fleet; MDS upgrade order phải giữ availability theo actual `max_mds`/standby topology. Không gọi `fail_fs` trên production như một upgrade shortcut. Canary phải kill/restart một rank có workload, đo replay/reconnect time, standby takeover, client errors và post-failback health.

**Applicability, confidence và rollback.** Áp dụng khi filesystem có active/standby rank; mức độ ảnh hưởng phụ thuộc `max_mds`, standby-replay và failure domain thực tế. Kích hoạt là tự động khi daemon stop/crash/failover. Rollback canary là đưa rank cũ đã giữ lại trở về service chỉ khi metadata compatibility gate cho phép; không dùng `fail fs` để ép. Confidence `high` cho changed paths, runtime outcome `UNKNOWN`; cần lưu MDSMap trước/sau, replay duration, session reconnect và namespace checksum.

### CFSJOURNAL-001 — Journal replay/cache recovery và metadata cleanup đổi

**Evidence.** `MDLog` đổi empty-journal replay termination, replay thread/name and segment handling; `MDCache` đổi imported caps, undefined dirfrags, truncate logging and trim; journal expiration, open-file table, purge queue, damage/scrub and stray reintegration paths đều đổi. `MDSRank` chuyển journal flush admin command sang asynchronous response path.

**Before/after.** Target restart/replay trên metadata tạo bởi Quincy đi qua code khác, đặc biệt sau unclean rank loss, pending truncate/purge, damaged dirfrag hoặc cap reconnect. Hunk không chứng minh persisted corruption; confidence `high` cho code path, outcome `UNKNOWN`. Clone metadata pool, inject controlled crash at journaled operations, replay Reef, compare scrub/damage/purge/open-file state and checksum namespace before considering rollback.

**Applicability, mixed/full và rollback.** Áp dụng cho mọi active MDS vì journal/replay là đường recovery nền; các nhánh damage/purge chỉ kích hoạt khi state tương ứng tồn tại. Mixed-version phải failover giữa rank cũ/mới trên clone; full-Reef phải replay sạch sau controlled crash. Tác động là recovery availability và metadata/namespace correctness. First target replay/write là rollback boundary: chỉ thử Quincy failback trên clone và dừng nếu decoder, scrub hoặc namespace lệch. Kiểm chứng gồm journal event count, damage table, purge queue, scrub và checksum; chưa có runtime artifact exact-tag.

### CFSMETA-001 — Persisted inode/dentry/snaprealm metadata được mở rộng

**Evidence.** `sr_t` encoding tăng v6→v7 và append `last_modified`/`change_attr` while compat remains 4; inode metadata gains fscrypt auth/file/last-block fields. Directory fetch/dentry key, snapshot trace, damage cleanup, remote dentry and journal metablog replay change. Common CephFS types move into `include/cephfs/types.h` and retain versioned decode paths.

**Before/after.** Reef can persist fields Quincy never populated. Appended/versioned encodings show an intended compatibility path, but endpoint diff alone does not prove rollback-safe behavior after Reef writes metadata. Treat first target MDS write/replay as rollback boundary until clone rehearsal shows Quincy decoder/replay semantics remain acceptable for the actual metadata and enabled features.

**Applicability, mixed/full và kiểm chứng.** Core inode/dentry fields áp dụng rộng; fscrypt/snaprealm extensions chỉ áp dụng khi object tương ứng được tạo hoặc sửa. Mixed-version phải đọc metadata cũ bằng Reef và tránh cho rank cũ consume target-only semantics chưa chứng minh; full-Reef phải scrub và replay sau write. Confidence `high` cho schema delta, rollback compatibility `UNKNOWN`. Lưu raw object/version samples, inode/snap inventories, scrub result và namespace checksum; gap còn lại là decode/failback artifact trên clone.

### CFSSNAP-001 — Snapshot realm semantics và public snapdiff path được thêm

**Evidence.** Target builds legacy/new snap traces per negotiated client feature, carries realm `last_modified/change_attr`, changes realm split/merge, snapshot remove/replay and adds `CEPH_MDS_OP_READDIR_SNAPDIFF`. libcephfs exposes `ceph_open_snapdiff`, `ceph_readdir_snapdiff`, `ceph_close_snapdiff`; server/client implement throttled paginated directory delta.

**Before/after.** Existing snapshots traverse changed trace and removal code after MDS upgrade; snapdiff is opt-in new API and does not affect clients that never call it. Test create/rename/delete across nested snapshot realms, old/new clients, failover mid-operation and large delta pagination. Preserve snapshot inventory and do not infer rollback safety from successful list alone.

**Applicability, activation và confidence.** Existing snapshot realms làm phần trace/replay tự động áp dụng; `READDIR_SNAPDIFF` chỉ kích hoạt khi client gọi API. Mixed-version phải giữ legacy trace cho client cũ, còn full-Reef mới kiểm new trace/snapdiff pagination. Tác động chính là correctness của snapshot view/delta, không chỉ availability. Rollback sau target snapshot mutation là `UNKNOWN` và phải thử trên clone. Confidence `high` cho source path, runtime `UNKNOWN`; cần realm dump, delta manifest và failover trace.

### CFSCRYPT-001 — Reef thêm CephFS fscrypt metadata handling

**Evidence.** Client, MDS, wire messages and inode encodings add fscrypt auth/file contexts and last-block handling; target rejects down-rev clients mutating encrypted inodes and bounds last-block metadata. QA adds fscrypt suites/workunit, but no result is present.

**Before/after.** Không áp dụng nếu filesystem không có encrypted directory/inode và không bật feature. Khi áp dụng, old client may read-only/fail mutations and target writes new metadata. Inventory encrypted paths/client support, then test create/read/write/truncate/rename/snapshot/failover with kernel and supported user client; never enable fscrypt as part of an unrelated upgrade rehearsal.

**Kích hoạt, mixed/full và rollback.** Đây là opt-in explicit qua encrypted inode/directory và compatible client; upgrade binary đơn thuần không bật mã hóa. Mixed-version phải giữ old clients khỏi mutation path không hỗ trợ và chứng minh error code rõ; full-Reef kiểm metadata last-block/auth context qua restart. Tác động là data-access/correctness và client compatibility. First Reef write vào encrypted metadata là rollback boundary; binary failback không được coi an toàn nếu chưa decode trên clone. Confidence `high` cho gating, applicability/runtime `UNKNOWN`; cần inventory và test artifact.

### CFSCLIENT-001 — libcephfs/FUSE client cache, quota, error và API behavior đổi

**Evidence.** `Client.cc` changes readdir caching, request routing, session open, caps/auth, quota-root selection, rename constraints, vxattrs and many disconnected-state checks. `libcephfs.cc` normalizes validation/errors and adds snapdiff; Cython bindings expose target APIs. FUSE rejects unsupported rename flags and updates multithread loop configuration.

**Before/after.** In-process consumers and FUSE clients can observe return-code or cache/permission behavior differences independently of daemon order. ABI headers add APIs without evidence here of removed exported symbols, but custom bindings must be rebuilt/tested. Run old/new client against old/new MDS combinations with readdir, quota, ACL/caps, flock/delegation, rename and disconnect/reconnect.

**Applicability, activation, mixed/full và rollback.** Áp dụng cho host nâng `ceph-fuse`/libcephfs hoặc ứng dụng nhúng; behavior kích hoạt ngay khi process restart/load thư viện mới, không chờ full cluster. Mixed matrix phải gồm old/new client × old/new MDS; full-Reef kiểm lại bindings được rebuild. Tác động là errno/API/cache correctness. Rollback khả thi bằng package/process failback chỉ trước khi ứng dụng dùng target-only API/state và sau smoke test; confidence `medium-high` cho source delta, ABI/runtime `UNKNOWN`. Cần symbol diff, binary consumer list và recorded calls.

### CFSMOUNT-001 — Mount helper option/device handling đổi

**Evidence.** `mount.ceph` and `mount.fuse.ceph` change argument/option handling and mount construction; adjacent config cleanup does not alter monitor address selection and is classified trivial.

**Before/after.** Existing systemd/fstab/container mount strings can parse differently under target helpers even while MDS remains old. Replay exact production mount units in a disposable namespace, validate secret/keyring handling, ms_mode/monitor addresses, remount/unmount and error propagation before upgrading client hosts.

**Applicability, mixed/full và rollback.** Chỉ áp dụng trên host thay helper/package; kích hoạt tự động ở lần mount/remount kế tiếp. Mixed-version là target helper với old/new MDS và exact production option strings; full-Reef lặp lại sau daemon rollout. Tác động là mount availability và option correctness. Rollback bằng package/helper cũ và unmount/remount trong cửa sổ kiểm soát, nhưng active mount không tự đổi parser. Confidence `medium`; chưa có inventory fstab/unit/container hay captured stdout/errno.

### CFSBAL-001 — Rank-mask và dynamic balancing logic đổi

**Evidence.** MDSMap encoding extends to `bal_rank_mask` and `max_xattr_size`; parser supports all/none/hex rank masks. MDBalancer changes split/merge/rebalance selection, config refresh and rank eligibility; FSMap/Migrator paths change placement/exports.

**Before/after.** Existing multi-rank filesystem may redistribute metadata differently after target ranks take over, especially if rank mask is set/invalid or config defaults differ. Snapshot MDSMap/config, validate parsed mask and observe exports/fragmentation/load without changing rank count during the binary rollout.

**Applicability, activation và rollback.** Chỉ đáng kể với multi-rank hoặc khi `bal_rank_mask`/balancer được cấu hình; rebalance tự động chạy theo workload/config sau target rank active. Mixed-version phải giữ rank count/mask cố định và theo dõi exports giữa old/new ranks; full-Reef mới cân nhắc tuning. Tác động là placement/latency. Rollback là restore verified config/mask và failback rank theo topology, không xóa migration đang chạy. Confidence `high` cho path, outcome `UNKNOWN`; cần MDSMap/config diff và load/export time series.

### CFSNFS-001 — NFS export/cluster CLI contract và ingress rendering đổi

**Evidence.** NFS module methods move from `(rc,out,err)` strings toward typed/list/dict/object-format results and per-export apply results. Cluster discovery falls back to RADOS namespaces without orchestrator. Ingress canonicalization distinguishes keepalive-only and HAProxy PROXY protocol, changing frontend/ganesha ports and service-spec flags; config changes can explicitly require manual pod restart.

**Before/after.** Scripts/Dashboard parsing old CLI text can break; existing NFS service may render different ingress ports/protocol on reconcile. Export RADOS objects and service specs, test list/info/apply partial failure, keepalive/PROXY connectivity and controlled restart. Cross-reference `ADMSVC-001`; no automatic export mutation was executed here.

**Applicability, activation, mixed/full và rollback.** Áp dụng khi dùng NFS module/ganesha ingress hoặc parser CLI; typed output xuất hiện ngay khi command chạy, còn rendered config chỉ đổi khi reconcile/redeploy/restart explicit. Mixed control plane phải kiểm old/new MGR CLI consumers và không reconcile hàng loạt; full-Reef kiểm client I/O qua VIP/PROXY. Tác động là automation contract và NFS reachability. Rollback bằng restore service spec/RADOS export backup và redeploy canary; confidence `high` cho source delta, runtime `UNKNOWN`. Gap là exact As-Is exports/specs và canary logs.

### CFSSCHED-001 — Snap-schedule SQLite schema được nâng và hỗ trợ subvolume group

**Evidence.** Module creates `SnapScheduleModuleKV`, migrates DB version 1→2 with `group_name`, resolves subvolume/group paths through volumes module, and changes schedule/retention validation including minute-unit handling.

**Before/after.** First target module load can mutate persisted schedule DB; commands may address a different absolute subvolume path or reject formerly accepted schedule text. Backup DB/RADOS object, migrate clone, verify all schedules/retentions and idempotent second load; then create/prune snapshots on test subvolumes before active MGR rollout.

**Applicability, activation và rollback.** Chỉ áp dụng khi snap-schedule module có DB/schedules; migration tự động ở lần target module load, còn create/prune là timer/command-driven. Mixed MGR phải pin active owner và tránh failover lặp trong lúc schema chuyển; full-Reef phải chứng minh second load idempotent. Tác động là schedule correctness và retained snapshots. Schema write là rollback boundary: restore backup/clone, không mở DB v2 bằng Quincy khi chưa chứng minh. Confidence `high`; gap còn lại là DB version/dump và migration transcript.

### CFSVOL-001 — Subvolume metadata/version, clone queue và deletion behavior đổi

**Evidence.** Volumes code adds `allow_subvolume_upgrade` metadata gate, changes v1/v2 state handling, clone source/detach/failure paths and optional `snapshot_clone_no_wait` (`-EAGAIN` when workers busy). Group removal now rejects retained/deleted subvolume snapshots; purge locks, clone index/count and info flavor output change.

**Before/after.** Persisted subvolume metadata may be upgraded/read under new rules; pending/failed clones and retained snapshots can yield different command results after MGR failover. Inventory every flavor/state/pending clone/trash entry, rehearse module restart and metadata upgrade on clone, and block rollout if queue/index/state diverges.

**Applicability, activation, rollback và kiểm chứng.** Áp dụng khi volumes/subvolumes hoặc clone queue tồn tại; metadata conversion có thể tự động khi target module opens state, còn clone operations là explicit/worker-driven. Mixed MGR phải tránh concurrent module ownership và record queue before/after; full-Reef kiểm restart/idempotency. Tác động là control-plane correctness và khả năng truy cập subvolume. First metadata upgrade là rollback boundary; chỉ restore backup hoặc failback sau clone rehearsal. Confidence `high` cho paths, outcome `UNKNOWN`; cần metadata/version dump, clone-index/queue diff và data checksum.

### CFSMIRROR-001 — Mirror restart/failure propagation và metrics đổi

**Evidence.** Mirror/instance watchers centralize monotonic blocklist timestamps; restart-on-blocklist/failure timing changes. Peer replay returns sync errors, records failure reasons/bytes and adds per-filesystem/peer counters for synced/deleted/renamed snapshots, failures and durations.

**Before/after.** A blocklisted or failing mirror can restart on different timing and now exposes richer failure status; source/destination data path still needs validation. Pause/observe peer queues, upgrade one mirror daemon in lab, test blocklist/restart and snapshot create/rename/delete, compare remote contents before enabling automatic failover assumptions.

**Applicability, activation, mixed/full và rollback.** Chỉ áp dụng khi CephFS mirroring/peer configured; restart path tự động khi blocklist/failure xảy ra, metric changes xuất hiện khi daemon mới chạy. Mixed-version phải canary một instance/peer và giữ remaining peers baseline; full-Reef kiểm backlog drain và resync. Tác động là replication lag/correctness. Rollback bằng dừng target instance, khôi phục binary/config và resync từ verified snapshot; không xóa peer state để “sửa” lỗi. Confidence `high` cho path, runtime `UNKNOWN`; cần peer inventory, queue/metric series và remote manifest.

### CFSMETRIC-001 — MDS metric aggregation và beacon schema đổi

**Evidence.** MetricAggregator changes rank metric refresh/removal and dispatch priority; MDS beacons add metric names. Metrics consumers must verify rank labels, disappearance on failover and time-series continuity.

**Before/after, applicability và kích hoạt.** Quincy consumers thấy schema/refresh behavior cũ; Reef daemon tự động phát/aggregate metric mới ngay khi active. Áp dụng cho mọi MDS, nhưng operational impact chỉ có khi alert/dashboard/SLO phụ thuộc label hoặc lifecycle cũ. Mixed-version phải phân biệt series theo daemon/rank version; full-Reef phải xác nhận stale series biến mất sau failover.

**Tác động, rollback, confidence và kiểm chứng.** Rủi ro chính là observability/alert correctness, không phải metadata path. Rollback bằng giữ dashboard/query tương thích hai schema và khôi phục rule cũ; metric đã ghi không cần state rollback. Confidence `high` cho schema path, consumer compatibility `UNKNOWN`. Chưa có Prometheus scrape/dashboard inventory; cần beacon dump, label/cardinality diff và alert replay.

### CFSADMIN-001 — cephfs-top và cephfs-shell output/command path đổi

**Evidence.** Operator shell/top code changes command handling and observability output. Any parser or rollout dashboard consuming these tools needs a target-version smoke test.

**Before/after, applicability và kích hoạt.** Chỉ áp dụng cho operator/automation gọi `cephfs-top` hoặc `cephfs-shell`; thay đổi tự động được kích hoạt ngay khi tool target chạy, độc lập với thứ tự daemon, còn command mutation là operator action explicit. Mixed-version phải chạy tool mới trên MDS cũ/mới và tool cũ trên endpoint còn hỗ trợ; full-Reef kiểm lại exact commands/parsers.

**Tác động, rollback, confidence và kiểm chứng.** Rủi ro là output/exit-code/command contract khiến runbook hoặc dashboard sai, không phải on-disk data. Rollback bằng dùng pinned old tool/container hoặc cập nhật parser dual-format; không có persisted-state boundary trừ khi command được dùng để mutate state, trường hợp đó phải gate riêng. Confidence `medium`; exact affected command/output và consumer inventory còn `UNKNOWN`. Lưu stdout/stderr/exit code golden files cho commands production dùng.

### CFSREPAIR-001 — Journal/data-scan/first-damage tools đổi

**Evidence.** JournalTool, DataScan and first-damage alter scan/reset/recovery behavior, including Python replacement of the first-damage helper. These tools are conditional and unsafe as routine upgrade steps; test only on cloned metadata with recorded commands/output and independent verification. A source change does not authorize repair.

**Applicability, activation, rollback và confidence.** Không áp dụng cho rollout khỏe mạnh; chỉ kích hoạt bằng command explicit khi recovery/repair được phê duyệt. Không chạy repair trong mixed production; full-Reef cũng chỉ dùng sau diagnosis và backup. Tác động có thể phá hủy metadata nên rollback dựa trên immutable clone/pool snapshot, không dựa vào inverse command. Confidence `high` cho tool delta, repair outcome `UNKNOWN`; gap là damage-specific rehearsal, command transcript, scrub và namespace manifest độc lập.

## Trivial changes

387 hàng `trivial` gồm 311 non-exact-hop QA rows, 41 documentation rows, 24 unit/integration-test rows chưa chạy và 11 runtime cleanup/type/thread-name/debug-only rows. Các suite fscrypt, mirror, NFS và functional vẫn là test candidate nhưng không tự là PASS. Lý do từng hàng nằm trong CSV.

## Validation đề xuất

1. **As-Is:** lưu `fs dump/status`, MDSMap/required features/flags, ranks/standbys, sessions/client metadata, auth caps, snapshots, fscrypt paths, volumes/clones/trash/schedules, NFS exports/specs and mirror peer status.
2. **Exact artifact matrix:** pin package/image digest and run Quincy→Reef MDS suite with `fail_fs=no` and disposable `fail_fs=yes`, kernel + FUSE/libcephfs clients and continuous fsstress/checksum.
3. **Rolling MDS:** upgrade standby then ranks one by one; capture session feature refresh, reconnect, cap recall, health, rank state and latency. STOP on unexpected eviction, damaged rank, replay loop or namespace mismatch.
4. **Client skew:** old/new kernel, FUSE and custom libcephfs bindings against old/new MDS. Do not add required features until all unsupported clients are removed by an explicit plan.
5. **Replay/rollback boundary:** clone metadata pools, crash around rename/snapshot/truncate/purge, replay Reef, then evaluate rollback on clone after Reef writes v7/fscrypt fields.
6. **Stateful MGR modules:** backup and clone-rehearse snap-schedule DB, subvolume metadata/index/clone queue, NFS RADOS config and rendered service specs; second target load must be idempotent.
7. **Snapshot/fscrypt/mirror:** nested snapshot realm deltas, fscrypt mutation/truncate/failover and mirror blocklist/restart/snapshot lifecycle on representative data.
8. **Observability:** verify MDS/mirror counters, health alerts, cephfs-top/Dashboard parsers and baseline latency before each cohort.
9. **Repair isolation:** JournalTool/DataScan/first-damage only against disposable clone with pre/post scrub and namespace manifests; never as an implicit rollout action.

## Kết luận owner

Owner 11 đã khép binary gate. Ba gate quan trọng nhất là: exact-artifact MDS/client mixed-version run; clone rehearsal cho journal/snaprealm/subvolume schedule state; và client inventory trước mọi thay đổi `required_client_features`. Source có compatibility gating rõ, nhưng chưa có lab result nên chưa có GO/NO-GO production.
