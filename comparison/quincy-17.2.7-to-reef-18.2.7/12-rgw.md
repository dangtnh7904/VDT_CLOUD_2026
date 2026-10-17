# 12 — RGW, S3, auth/policy và multisite: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./12-rgw.csv) có 689 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 445`, `trivial = 244`, chưa phân loại = 0. Detailed findings chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và base không là ancestor của target; evidence là endpoint hunk, encoder/decoder, caller, suite graph và persisted-state path, không phải lịch sử commit đầy đủ.

Chưa có RGW As-Is: service specs/frontends, zonegroup/realm topology, sync policy/status, bucket index generations, in-progress reshard, lifecycle queues, notification topics/endpoints, KMS/Keystone/LDAP/IAM, quota/rate limit, NFS/librgw, Lua, DBStore, ops-log consumers và artifact digest đều `UNKNOWN`. Chưa chạy teuthology, ragweed, s3tests, multisite convergence, notification replay hay rollback. Báo cáo không cấp quyền sửa period, reshard/repair bucket, trim log, rotate key, migrate backend hoặc thao tác production.

## Finding ảnh hưởng upgrade

### RGWVAL-001 — Có matrix RGW Quincy→Reef nhưng chưa có exact-tag result

**Evidence.** 18 hàng relevant dưới `qa/suites/rgw/upgrade` tạo source selector Quincy, setup hai RGW client, `install.upgrade`, ragweed `prepare/check` và hai sequence: restart OSD cohorts trước rồi RGW, hoặc RGW trước rồi OSD. Sáu selector Pacific được loại khỏi hop này.

**Before/after.** Suite source kiểm đúng hai mixed-order quan trọng, nhưng `install.yaml` dùng `branch: quincy`, target package đến từ job context và không pin `v17.2.7`/`v18.2.7`; repo không chứa run archive. Gate phải chạy exact package/image digest, giữ continuous S3 workload và lưu ragweed result, OSD/RGW versions, health, bucket/object manifests. Source tồn tại không đồng nghĩa PASS.

**Điều kiện, mixed/full, rollback và confidence.** Áp dụng cho mọi RGW rollout; suite chỉ kích hoạt khi operator chạy và không tự đổi production. Hai pha mixed là RGW-first và OSD-first; full-Reef phải lặp smoke/restart sau khi cả hai lớp đồng nhất. Tác động của gap là chưa thể chấp nhận data-plane availability/correctness chỉ từ suite source. Rollback của fixture là teardown/restore snapshot, không chứng minh binary downgrade trên persisted state. Confidence `high` cho coverage graph, `none` cho exact-hop result; gap là pinned digest, run archive và manifest so sánh.

### RGWCLS-001 — RGW object-class và persisted queue/index encodings đổi

**Evidence.** `cls_rgw_bucket_instance_entry` tăng encoding v1→v3, bỏ semantic của `new_instance_id/num_shards` nhưng v3 ghi lại hai field rỗng để tương thích decode; usage entry v3→v4 thêm S3 Select bytes; lifecycle/reshard/GC entries tăng version; bucket index/OLH và multipart-part operations đổi. FIFO class và RGW class transaction paths cũng thay đổi.

**Before/after.** Reef RGW nói chuyện với OSD class và state objects bằng payload khác trong lúc OSD/RGW có thể ở hai version. Versioned decode cho thấy intent tương thích, không chứng minh mọi downgrade/replay path an toàn. Chạy cả hai order của RGWVAL-001 với existing bucket index, usage, lifecycle, multipart và reshard state; STOP nếu class method trả `-EIO/-EINVAL`, decode warning, stuck pending entry hoặc stats lệch.

**Applicability, activation, mixed/full và rollback.** Core bucket/class payload áp dụng cho mọi RADOS-backed RGW; usage/LC/GC/reshard nhánh chỉ kích hoạt khi state tương ứng tồn tại. Encode mới được kích hoạt tự động khi target worker/request ghi object. Mixed OSD/RGW phải kiểm request hai chiều; full-Reef phải restart/replay queues. Tác động là queue/index decode, bucket stats và request correctness. First target write là rollback boundary: old reader chỉ được thử trên clone. Confidence `high` cho schema delta, runtime/downgrade `UNKNOWN`; kiểm chứng cần raw object samples, class error log và reconciliation artifact.

### RGWSAL-001 — Default RADOS backend được tái cấu trúc qua SAL/Driver

**Evidence.** Active implementation chuyển vào `driver/rados`, `Store` interfaces đổi sang `Driver`, và RADOS/system-object/cache/coroutine services được nối lại qua SAL. Các hunk lớn trong `rgw_rados`, `rgw_sal_rados`, service core và common types không chỉ là đổi tên file; tám exact-content `R100 0/0` đã được tách `trivial`.

**Before/after.** On-disk RADOS objects không tự đổi backend, nhưng mọi target gateway restart đi qua construction, cache, async I/O và system-object path mới. Đây không phải tuyên bố wire break. Gate là khởi động target RGW trên cloned existing realm/buckets, đọc/ghi/list/multipart/versioning, restart/reload nhiều lần và so object manifest, attrs, bucket stats cùng error rate với baseline.

**Applicability, activation, mixed/full và rollback.** Áp dụng cho default RADOS driver; kích hoạt tự động ở mỗi target process start và request. Mixed-version canary phải chia traffic có kiểm soát giữa gateway cũ/mới trên cùng clone/realm; full-Reef phải chứng minh cache/reload/idempotent restart. Tác động trải data plane và control/system objects. Rollback binary chỉ là ứng viên trước target-only write và sau old-reader rehearsal. Confidence `high` cho refactor path, behavioral equivalence `UNKNOWN`; kiểm chứng cần startup trace, request matrix và manifests.

### RGWBUCKET-001 — Bucket layout có generation/log-layout rõ ràng hơn

**Evidence.** `BucketLayout` target lưu `resharding`, `current_index`, optional `target_index` và vector log generations; encoding v2 đọc v1 bằng cách dựng log layout từ current index. RADOS bucket/SAL/service paths dùng layout generation, index type và current shard count thay các field rời. Metadata sync tránh sao chép layout remote một cách mù quáng và dùng local placement defaults.

**Before/after.** Existing v1 bucket layout được nâng semantic khi target đọc/ghi metadata. Bucket đang indexless, versioned, multisite hoặc có untrimmed bilog có blast radius cao hơn. Inventory layout/generation/shard count từng bucket; canary create/list/delete/versioning và compare BI header/stats trước/sau restart. Reef write tạo rollback boundary cần rehearsal trên clone.

**Applicability, activation, mixed/full và confidence.** Áp dụng cho mọi bucket metadata, ưu tiên bucket resharded/versioned/multisite; conversion/write kích hoạt tự động khi target sửa layout hoặc index state. Mixed gateway phải cùng đọc bucket và không chạy reshard; full-Reef kiểm restart/list/stats. Tác động là listing/index correctness. Rollback sau v2 write `UNKNOWN`, chỉ old-reader trên clone hoặc restore metadata backup. Confidence `high` cho versioned decode, runtime compatibility `UNKNOWN`; kiểm chứng cần per-bucket layout/header snapshots.

### RGWRESHARD-001 — Dynamic reshard state và recovery/tooling đổi

**Evidence.** Reshard implementation chuyển vào RADOS driver, dùng target index/layout generation và status encoding mới; admin code bổ sung stale-instance, OLH/unlinked-index/bucket-index repair paths. Exact endpoint còn thay wait/completion and bucket-instance metadata handling.

**Before/after.** Không tự chạy reshard hay repair. Bucket đang reshard khi cohort đổi version có thể được resume/observed bằng state machine khác; repair tool có thể sửa persisted index. Gate phải chứng minh không có in-progress/stale reshard trước window hoặc rehearse pause/restart/resume trên clone, đối chiếu object count/BI log/stats. Không dùng repair command như bước nâng cấp mặc định.

**Applicability, activation, mixed/full và rollback.** Chỉ áp dụng trực tiếp khi reshard state tồn tại hoặc command explicit được gọi; binary rollout không tự khởi tạo repair. Mixed-version yêu cầu quiesce reshard hoặc một clone rehearsal qua old/new workers; full-Reef mới resume theo runbook. Tác động là bucket index/listing. Không có inverse repair đáng tin: rollback bằng immutable metadata/data snapshot và restore có phê duyệt. Confidence `high` cho code delta, state outcome `UNKNOWN`; kiểm chứng còn thiếu in-progress inventory và resume transcript.

### RGWSYNC-001 — Multisite full/incremental sync, leases và recovery được viết lại

**Evidence.** Target full sync chuyển từ per-shard registration sang bucket-wide registration, đăng ký một shard để bao phủ bucket kể cả shard count thay đổi. Data-sync status/markers, full→incremental transition, continuous leases, obligation coalescing, error repository/backoff/retry, async wakeup, bilog/datalog/mdlog trimming và generation compatibility đều đổi. Code vẫn có remote-log polling khi notification không đánh thức worker.

**Before/after.** Existing sync status objects và buckets có reshard generations đi qua compatibility conversion; mixed zones/gateways có thể tiến marker và trim ở timing khác. Confidence cao cho code path, outcome `UNKNOWN`. Freeze period edits, snapshot `sync status`, markers/error repo/log generations, upgrade secondary canary, inject writes/deletes/versioning/reshard, mất notification và restart; yêu cầu convergence cùng checksum trước khi nâng tiếp hoặc trim.

**Activation, rollback và kiểm chứng.** Áp dụng khi realm multisite; workers/leases tự động kích hoạt khi gateway target chạy, còn period commit/log trim là explicit và phải khóa. Mixed-version phải canary secondary trước và giữ source zone baseline; full-Reef phải hội tụ sau restart/notification loss. First target marker/log-generation write là rollback boundary; failback chỉ trên clone hoặc với exported sync state và no-trim guarantee. Kiểm chứng gồm marker monotonicity, error repo, lag và object/version checksum; chưa có exact artifact.

### RGWMETA-001 — Realm/zone/period/config-store và metadata reload đổi

**Evidence.** Target tách RADOS config store cho realm, zonegroup, zone, period và period config; thêm immutable/JSON store implementations; metadata/user/zone services và realm watcher/reloader chuyển qua Driver. Zone feature/type structs được tách và period push/pull/reload paths thay đổi.

**Before/after.** Gateway target có thể đọc/render/reload cùng persisted period theo path khác; first target MGR còn có thể migrate RGW spec theo `ADMMIG-001`. Export realm/zonegroup/zone/period JSON và cephadm spec, validate epoch/master zone/placement/endpoints, restart target without committing a new period, then test controlled period update only in lab. Do not assume old binary can consume state rewritten by a new config store.

**Applicability, activation, mixed/full và rollback.** Áp dụng cho mọi realm/zone config; read/reload tự động ở startup/SIGHUP, còn period update/commit là explicit. Mixed gateway phải chỉ đọc cùng epoch và cấm concurrent period mutation; full-Reef mới thử commit lab. Tác động là routing/placement/control-plane correctness. Config-store hoặc period write là rollback boundary; giữ JSON/spec/epoch backup và old-reader clone. Confidence `high` cho path, runtime `UNKNOWN`; cần before/after export và reload transcript.

### RGWLC-001 — Lifecycle shard traversal/locking và cloud transition đổi

**Evidence.** Lifecycle processor thay head/marker traversal, lock retry/backoff, stale/complete entry handling and shard rollover date. Lifecycle head encoding adds `shard_rollover_date`; filters add flags. Cloud-S3 tier adds multipart transition with persisted upload status, resume/abort/HEAD checks and target-bucket creation.

**Before/after.** Existing LC queues may resume at a different marker after restart; cloud transition can leave/resume multipart state unknown to Quincy. Applies when lifecycle or cloud tiering is enabled. Snapshot policies/head/entries and cloud targets, run expiration/transition/noncurrent/multipart cases across restart, ensure one-pass/no duplicate/no skipped object. Treat target-created multipart status as rollback boundary until clone proof.

**Activation, mixed/full, impact và kiểm chứng.** LC worker tự động chạy theo schedule khi enabled; cloud transition chỉ áp dụng rule/tier configured. Mixed-version phải canary một worker/zone và tránh duplicate ownership; full-Reef phải restart giữa multipart transition. Tác động là retention/data movement và chi phí. Rollback bằng pause worker, restore queue/status backup và reconcile remote/local objects; không xóa marker mù. Confidence `high` cho changed paths, outcome `UNKNOWN`; cần policy/head/entry snapshots và object manifest.

### RGWNOTIFY-001 — Persistent bucket notifications thêm 2PC queue và failover ownership

**Evidence.** Target persistent topics use `cls_2pc_queue` reservation/commit/abort, a queue-list object, per-queue lock ownership, stale reservation cleanup, worker failover and retry. Event assembly/topic filtering and HTTP/AMQP/Kafka endpoint code change; AMQP connection identity includes exchange and reconnect/idle behavior changes.

**Before/after.** In-flight events can sit in a new persisted queue format while old/new gateways overlap; endpoint outage and RGW failover determine duplicate/loss/backpressure behavior. Applies only to configured topics, especially persistent endpoints. Inventory topics/ARNs/secrets/TLS/queue depth, then test endpoint down/up, RGW kill/restart, queue full and ack/retry with unique event IDs; reconcile delivered plus queued events, not only HTTP success.

**Activation, mixed/full, rollback và confidence.** Event enqueue/delivery tự động khi matching operation xảy ra; topic/config changes là explicit. Mixed-version phải giữ một persistent queue owner và canary failover có kiểm soát; full-Reef phải drain/replay sau endpoint outage. Tác động là at-least-once delivery, duplicate/loss và backpressure. Rollback bằng pause producers/workers, preserve queue objects và replay/reconcile IDs; old binary consumption of new 2PC state là `UNKNOWN`. Confidence `high`; gap là topic/queue inventory và delivery ledger.

### RGWAUTH-001 — S3 signatures, policy validation, Keystone service tokens và IAM/STS đổi

**Evidence.** S3 auth adds unsigned streaming payload/trailer verification. Keystone supports service-token roles, expired user token only with valid service token, admin-token invalidation/retry and cache rules. IAM parser can reject invalid principals, renames `ModifyRoleTrustPolicy`, adds `UpdateRole`, improves annotated errors; STS/role paths and Swift TempURL support broader signature formats.

**Before/after.** Existing clients may see different accept/reject results for chunked upload, invalid policy principals, expired Keystone token, role action or Swift TempURL. `CFG-010` confirms strict invalid-principal default applies to new policy parse, not a bulk rewrite. Run positive/negative SigV2/V4 streaming/trailer, policy/IAM/STS, Keystone cache/service-token and Swift signatures against old/new gateway; preserve auth decision logs without exposing secrets.

**Applicability, activation, mixed/full và rollback.** Chỉ các configured auth backends/client modes liên quan mới áp dụng; parser/verification tự động chạy theo request, policy mutation vẫn explicit. Mixed-version phải gửi cùng signed corpus tới old/new gateway; full-Reef kiểm cache expiry/restart. Tác động là access-control availability/security. Rollback binary/config chỉ sau khi xác minh không có policy rewrite và không log secret; auth decision đã cấp không thể “undo”. Confidence `high` cho source behavior, actual client compatibility `UNKNOWN`; cần backend/client inventory và redacted decision matrix.

### RGWAPI-001 — S3/Swift/admin request dispatch và error contract đổi

**Evidence.** REST/op layers change dispatch, argument parsing, request state, errors, S3/Swift operations and website behavior. This cluster includes real endpoint hunks, not docs or tests; exact-content moves are excluded.

**Before/after.** SDKs, gateways/proxies and automation can observe status code/body/header differences even without persisted-state mutation. Replay production-shaped HEAD/GET/PUT/COPY/DELETE, range/conditional, multipart, versioning, website and Swift cases through the actual proxy/TLS chain; diff status, headers, XML/JSON and idempotency on retry.

**Applicability, activation, mixed/full và rollback.** Áp dụng theo protocol/features thực dùng; behavior tự động kích hoạt trên target request path. Mixed-version cần deterministic corpus qua load balancer tới từng gateway version; full-Reef chạy lại retries/timeouts. Tác động là client contract và có thể tạo object nếu mutation request. Rollback cho read-only/API presentation là route traffic về old cohort; writes cần object/version manifest để reconcile. Confidence `medium-high`; exact endpoint deltas và consumer tolerance còn `UNKNOWN`. Kiểm chứng phải lưu golden response, headers, body và exit data.

### RGWOBJ-001 — Object ingest, multipart, manifest và S3 Select path đổi

**Evidence.** Put-object processor, manifests/object types, compression, multipart metadata/deletion and ETag logic move/change under RADOS SAL. S3 Select parser/execution grows and usage encoding adds bytes processed/returned.

**Before/after.** Existing striped/compressed/multipart objects and new uploads can traverse different manifest/ETag/accounting logic; no data corruption is asserted. Build representative legacy fixtures, read range/full/checksum, copy/rewrite, complete/abort multipart and restart mid-upload; compare manifests, ETag, data hash and usage. Keep rollback copy until Reef-written objects pass old-reader rehearsal where rollback is required.

**Applicability, activation, mixed/full và confidence.** Core object path áp dụng rộng; compression/S3 Select/multipart chỉ khi configured/requested. Target behavior tự động ở read/write. Mixed gateway phải đọc fixture cũ và đọc chéo object do mỗi version tạo; full-Reef kiểm restart mid-upload. Tác động là data integrity, ETag và accounting. Rollback sau Reef write chỉ với immutable copy/versioning hoặc proven old-reader. Confidence `high` cho paths, corruption outcome không được suy đoán; cần data/manifest/hash/usage artifacts.

### RGWENC-001 — SSE/KMS/KMIP và object-lock handling đổi

**Evidence.** Target SSE-S3 explicitly rejects unsupported backend rather than falling through; Vault/Barbican/KMIP client and sanitize paths change. Object-lock/retention integration and encrypted request paths are touched; crypto suites exist but are not executed here.

**Before/after.** Conditional on encryption/key backend or retention. Gate must inventory backend/URI/cert/key IDs and locked buckets, then read old ciphertext, write/read target ciphertext, rotate/restart on a test key, test unavailable KMS and retention/legal-hold denial. Never rotate/delete key or bypass retention as part of binary rollout.

**Activation, mixed/full, rollback và confidence.** Crypto/lock path tự động kích hoạt theo bucket/request metadata; key rotation và retention mutation là explicit, bị cấm trong binary canary. Mixed-version phải đọc ciphertext/locked object bằng cả gateway versions; full-Reef kiểm KMS outage/restart. Tác động là data availability, confidentiality và compliance. Rollback yêu cầu giữ key/material/config và immutable test objects; target ciphertext chỉ được failback sau old-reader proof. Confidence `high` cho conditional path, environment compatibility `UNKNOWN`; cần backend/cert/key-ID inventory và redacted test log.

### RGWQUOTA-001 — Quota/rate-limit/usage persistence và observability đổi

**Evidence.** Quota cache/async refresh and user/bucket stats move through Driver; rate-limit REST reads/writes period config; usage v4 includes S3 Select counters. Service wiring and admin output change.

**Before/after.** Near-limit clients can be admitted/rejected differently if cache refresh or period config is stale; usage consumers see added fields. Snapshot effective realm/user/bucket settings and stats, test boundary ±1 object/byte/op, cache expiry/restart and multi-RGW consistency, then validate dashboards/parsers accept the target schema.

**Applicability, activation, mixed/full và rollback.** Áp dụng khi quota/rate limit/usage accounting enabled hoặc consumed; enforcement/cache tự động theo request, setting changes explicit. Mixed-version phải dùng cùng limits trên old/new gateways và chờ cache expiry; full-Reef kiểm restart. Tác động là admission/fairness/billing observability. Rollback bằng restore exported settings/config và route traffic về baseline; usage v4 persisted fields cần consumer compatibility, không xóa counters. Confidence `high` cho paths, boundary behavior `UNKNOWN`; cần setting/stats snapshots và ±1 matrix.

### RGWGC-001 — GC, object-expirer và orphan handling đổi

**Evidence.** RADOS GC/log backing, object-expirer and orphan paths change alongside versioned GC/lifecycle class entries. Tools and workers operate on existing manifests/queues after restart.

**Before/after.** Conditional on pending GC/expiration/orphan work. Capture queue age/count and sample manifests, stop workload on clone, restart target workers, prove eligible objects removed once and referenced objects retained. Queue drain is not proof of correctness without object and bucket-index reconciliation.

**Activation, mixed/full, rollback và confidence.** GC/expirer worker tự động chạy khi enabled; orphan tooling là explicit. Mixed-version phải tránh hai worker owners tranh cùng fixture và canary trên clone; full-Reef kiểm restart/idempotency. Tác động là storage leak hoặc xóa nhầm data. Deletion không có inverse: rollback dựa trên immutable pool snapshot/object versions và stop worker ngay khi reconciliation lệch. Confidence `high` cho changed paths, outcome `UNKNOWN`; cần queue samples, manifest/reference set và deletion ledger.

### RGWSTART-001 — Daemon startup/shutdown/frontend lifecycle được tách vào AppMain

**Evidence.** `rgw_main` delegates initialization to new `AppMain`: frontend parsing/default Beast, storage Driver, auth/ratelimit, ops log, realm watcher, notification endpoints, Lua, signals and ordered shutdown. Beast frontend changes config prefix, request/environment lifetime and pause/unpause on config reload.

**Before/after.** Every restarted target gateway goes through different initialization and teardown ordering. Validate exact cephadm-rendered frontend args, bind/TLS/prefix/service-map, SIGHUP realm reload, graceful TERM with keepalive/in-flight multipart and repeated restart. Cross-reference `ADMMIG-001` and `ADMSVC-001` for spec migration/rendering; do not let unreviewed reconcile change all RGWs at once.

**Applicability, activation, mixed/full và rollback.** Áp dụng cho mọi target daemon; kích hoạt tự động khi process start/stop/reload. Mixed-version phải canary đúng một gateway sau khi freeze service spec; full-Reef mới rolling remaining cohorts. Tác động là availability, dropped requests và config rendering. Rollback bằng drain canary, restore verified spec/image digest và start old daemon nếu persisted-state gates còn cho phép. Confidence `high` cho lifecycle refactor, deployed args/runtime `UNKNOWN`; cần rendered unit/spec, bind/TLS checks, in-flight request ledger và shutdown timing.

### RGWOBS-001 — Ops log/counters/tracing đổi

**Evidence.** Runtime log, perf-counter and tracer paths change, while `CFG-010` changes the default ops-log sink. Target startup explicitly initializes file/RADOS/socket sinks according to effective config.

**Before/after.** A healthy data plane can still lose audit/stop-go signals or fill local disk. Validate effective `rgw_enable_ops_log`, sink/path/rotation/ownership/SELinux, parser schema, counter labels and traces before accepting a cohort; monitor disk growth and audit completeness under load.

**Applicability, activation, mixed/full và rollback.** Áp dụng khi ops-log/counters/tracing được consume; sink mặc định thay đổi tự động theo effective config ở startup, override là explicit. Mixed-version phải dual-read old/new sinks và phân tách labels; full-Reef xác nhận rotation/disk. Tác động là audit compliance và khả năng phát hiện STOP. Rollback bằng pin lại sink/config, drain/rotate an toàn và route collector; không xóa log. Confidence `high` cho default/path, actual consumer mapping `UNKNOWN`; cần effective config, file/RADOS/socket sample và completeness count.

### CFG-010 — Cross-owner default tắt data notify và đổi ops-log sink

Owner 06 proves `rgw_ops_log_rados true→false` with file sink default, and `rgw_data_notify_interval_msec 200→0`. Multisite polling remains, but low-latency wakeup is disabled unless overridden. Pin intended values explicitly, test polling convergence under notification loss and verify the audit consumer follows the new sink before rollout.

**Applicability, activation, mixed/full và rollback.** Áp dụng cho multisite data sync và mọi ops-log consumer; defaults có hiệu lực tự động khi config không override và daemon target restart. Mixed-version phải ghi rõ effective value từng gateway; full-Reef đo convergence/audit end-to-end. Tác động là sync latency và audit visibility. Rollback bằng explicit config restore và daemon canary restart, không trim log trong gate. Confidence `high` cho default delta, site behavior `UNKNOWN`; cần config dump, lag series và sink-delivery evidence.

### RGWADMIN-001 — radosgw-admin command/output path đổi

**Evidence.** Admin code grows across realm/period, bucket layout/reshard, user, sync status/error and metadata operations. Automation parsing text or JSON may observe different fields and defaults.

**Before/after.** Export exact commands/output used by runbooks, replay read-only variants against clone and parse machine-readable formats. Mutating subcommands require separate approval, pre/post manifests and rollback; source review does not authorize them.

**Applicability, activation, mixed/full và confidence.** Chỉ commands/runbooks thực dùng mới áp dụng; thay đổi kích hoạt khi target CLI chạy, độc lập với daemon rollout đối với nhiều read-only calls. Mixed-version phải chạy target admin client trên old/new endpoints và ngược lại khi supported; full-Reef dùng JSON golden files. Tác động là automation correctness, còn mutating command có thể đổi persisted state. Rollback read-only là pin old tool/parser; mutation cần command-specific backup/inverse đã rehearsal. Confidence `medium-high`; command inventory/output contracts còn `UNKNOWN`. Kiểm chứng phải lưu argv, stdout/stderr, exit code và parsed result.

### RGWREPAIR-001 — Gap/orphan/index restore tools đổi

**Evidence.** `rgw-gap-list`, `rgw-orphan-list` and new `rgw-restore-bucket-index` alter how suspected unlinked data and index state are enumerated/repaired.

**Before/after.** These tools apply only to an independently diagnosed inconsistency. Rehearse read-only discovery and any restore on cloned pools, verify data hash, versions, index/listing and stats. Do not run them simply because the binary version changed.

**Applicability, activation, mixed/full và rollback.** Mặc định `NON_APPLICABLE` cho healthy rollout; chỉ operator command explicit sau diagnosis mới kích hoạt. Không chạy mutating repair trong mixed production; full-Reef cũng cần phê duyệt riêng. Tác động có thể là destructive index/data mutation. Không giả định inverse command: rollback bằng immutable cloned pools/snapshot và independent manifest. Confidence `high` cho tool delta, repair outcome `UNKNOWN`; kiểm chứng cần damage-specific reproduction, transcript và post-repair hash/index/stats.

### RGWNFS-001 — librgw/RGWFile path đổi

**Evidence.** `librgw` is reorganized through `rgw_lib`/AppMain and RGWFile namespace/metadata/I/O code changes; library tests are supporting source only and were not run.

**Before/after.** Applies to NFS-Ganesha/embedded librgw consumers, not ordinary HTTP-only RGW. Test mount, lookup/readdir, xattr, create/write/rename/unlink, restart and stale-handle behavior with the exact Ganesha/librgw pair; coordinate rendered NFS service changes under `ADMSVC-001`.

**Activation, mixed/full, impact và rollback.** Path kích hoạt khi librgw consumer process load target library/start; không áp dụng cho HTTP-only site sau khi có As-Is proof. Mixed-version phải tránh unsupported library/daemon mix và canary một export; full-Reef kiểm restart/stale handles. Tác động là filesystem namespace/I/O correctness. Rollback bằng drain/unmount, restore pinned Ganesha+librgw pair và remount sau manifest check; open handles không tự chuyển. Confidence `high` cho path, deployed pair/runtime `UNKNOWN`; cần consumer/export inventory và file-tree/hash transcript.

### RGWLUA-001 — Lua có background/data-filter execution mới

**Evidence.** Target changes request hooks/package utilities and adds background/data-filter managers initialized from AppMain for the RADOS driver.

**Before/after.** Conditional on deployed scripts/packages. Inventory script contexts and package hashes, execute each hook with success/error/timeout, restart/reload and verify side effects once. If Lua is unused, do not enable it during this upgrade.

**Activation, mixed/full, impact và rollback.** Lua hooks/background filters chỉ kích hoạt khi config/package/script tồn tại; binary upgrade không được dùng để enable. Mixed-version canary phải route deterministic events tới một target gateway và ledger side effects; full-Reef kiểm reload/restart/timeout. Tác động là request mutation hoặc external side effects. Rollback bằng disable verified hook/package và restore pinned scripts; external side effect cần idempotency/reconciliation, không thể luôn undo. Confidence `medium-high`; applicability và behavior `UNKNOWN` tới khi có inventory. Kiểm chứng cần script hash, context, result/error/time và side-effect IDs.

### RGWDBSTORE-001 — DBStore/SQLite schema và SAL đổi (conditional)

**Evidence.** Opt-in DBStore moves under driver, adds connection pool and SQLite config schema/store, and substantially changes SAL/database operations. A new DBStore QA suite exists but is unexecuted.

**Before/after.** Existing default RADOS RGW is not migrated automatically. If `rgw_backend_store=dbstore` is absent, this finding is non-applicable; if present, artifact/schema backup, clone-open, migration/idempotent restart and CRUD/multipart/list verification are mandatory. Do not switch backend as part of the major-version rollout.

**Activation, mixed/full, impact và rollback.** Kích hoạt chỉ khi explicit backend config chọn DBStore và target process mở database; không chạy mixed writers khác schema nếu chưa supported. Full-Reef phải chứng minh second open idempotent và data CRUD/list đúng. Tác động là toàn bộ data/control path của opt-in backend. Schema write là rollback boundary; giữ file/database snapshot và thử old-reader trên clone. Confidence `high` cho conditional refactor, actual applicability/runtime `UNKNOWN`; cần effective config, schema version, backup digest và test transcript.

### RGWCORE-001 — Residual active request/scheduler/helper changes remain conservatively gated

**Evidence.** 26 active helpers cover request scheduling, formats/XML/string/tag handling, OPA/IDP/user types, resolver/OS helpers and error mapping. They are not promoted as separate compatibility breaks, but their endpoint hunks are executed by configured request paths, so they remain `affect` rather than being guessed trivial.

**Before/after.** Applicability follows enabled scheduler/auth/integration. Representative client replay, malformed-input negatives, cancellation/timeouts and tail-latency comparison close this residual gate; unsupported/unused integrations may be marked non-applicable only after As-Is evidence.

**Activation, mixed/full, impact và rollback.** Các helper tự động chạy theo request/configured integration; không gán N/A chỉ từ tên file. Mixed-version phải replay cùng corpus vào old/new cohort; full-Reef so latency/error/cancellation sau restart. Tác động có thể là request correctness hoặc performance, nhưng không có bằng chứng standalone on-disk migration. Rollback bằng route traffic về old cohort và restore scheduler/integration config, subject to object-write gates khác. Confidence `medium`; unresolved gap là exact enabled-path mapping. Kiểm chứng cần config/caller inventory, golden malformed inputs và p95/p99/error diff.

## Trivial changes

244 hàng `trivial` gồm 122 non-exact-hop QA/harness rows, 59 unit/integration/benchmark rows chưa chạy, 38 documentation và 3 README rows, 6 Pacific selectors, 8 exact-content rename rows và 8 target-only DAOS/Motr/Arrow-Flight rows không tự activate. Những file này vẫn có thể là test/documentation support; chúng không tự tạo runtime PASS hay deployment effect. Lý do từng hàng nằm trong CSV.

## Validation đề xuất

1. **As-Is:** lưu service spec/rendered frontend, image/package digest, realm/zonegroup/zone/period, placement, users/roles, sync status/markers/errors, bucket layout/reshard, LC queues, notification topics/queues, quotas/rate limits, encryption/KMS and ops-log sinks.
2. **Exact artifact run:** pin `v17.2.7` and `v18.2.7` artifacts, run both RGWVAL sequences with continuous S3/ragweed and capture daemon versions, health, failures, latency, object/index/stats manifests.
3. **Mixed OSD/RGW class gate:** existing usage/LC/GC/reshard/multipart state under both orders; watch class decode/errors and forbid uncontrolled trim/repair.
4. **Multisite:** upgrade one secondary gateway/zone first; writes/deletes/versioning/reshard, lost notification, endpoint partition, restart and full checksum convergence before period commit or log trim.
5. **Bucket/object:** fixtures for legacy layout, striped/compressed/encrypted/versioned/multipart/locked objects; full/range/copy/rewrite plus bucket BI/stats comparison.
6. **Lifecycle/notification:** restart during LC/cloud multipart and persistent notification delivery; reconcile markers, remote objects, unique event IDs and queues after failover.
7. **Auth/API:** positive and negative S3 streaming/trailer, IAM/STS/policy, Keystone service-token/cache, Swift TempURL and SDK/proxy contract matrix.
8. **Startup/control plane:** export cephadm Store/spec before target MGR, diff migration/rendering, canary one RGW, SIGHUP/reload and graceful TERM with active connections.
9. **Observability/STOP:** audit sink completeness, disk, sync lag, queue age, class errors, 4xx/5xx, latency and checksums. STOP on missing audit, non-converging marker, decode error, duplicate/lost persistent event, object/index mismatch or unrecoverable auth regression.
10. **Rollback boundary:** rehearse old binary against cloned state after Reef writes bucket layout, LC/notification/usage/reshard metadata and new objects; preserve exported metadata and immutable data manifests until proven.

## Kết luận owner

Owner 12 đã khép binary gate. Ba gate quan trọng nhất là: exact-artifact two-order RGW/OSD run; multisite + bucket-layout/CLS convergence on existing state; và auth/lifecycle/notification replay across target restart. Source contains explicit backward-decode/compatibility paths, but no runtime result exists, so owner này không đưa ra GO/NO-GO production.
