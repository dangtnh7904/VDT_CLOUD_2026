# 10 — RADOS/RBD clients, snapshots và mirroring: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./10-rados-rbd-clients.csv) có 421 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 145`, `trivial = 276`, chưa phân loại = 0. Detailed findings bên dưới chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor, nên không dùng commit-range để suy diễn lịch sử/intent; kết luận dựa trên hunk, public header, caller, on-disk encode/decode và test context ở hai endpoint.

Chưa có As-Is về ứng dụng liên kết librados/librbd, ngôn ngữ/binding, image features, fast-diff/object-map, cache/journal, encrypted clone, migration, rbd-mirror mode/peer, NBD/WNBD mappings hay incremental backup chain. Chưa build ABI, chạy repository test hoặc rehearsal trên image clone. Báo cáo không cấp quyền map/unmap, flatten, migrate, resize, purge, promote/demote hoặc sửa image production.

Review không thấy thay đổi versioned encoding của `cls_rbd` snapshot namespace: chuyển `boost::variant` → `std::variant` được chốt `trivial`. Vì vậy owner này không chứng minh một on-disk format break tổng quát; rủi ro chính nằm ở binary/source API, client-side I/O/diff/encryption và tool/daemon behavior.

## Finding ảnh hưởng upgrade

### RADOSAPI-001 — Public librados/rgw_file và Asio contract đổi

**Evidence.** `librados.h` thêm `rados_stat2`, `rados_aio_stat2`, `rados_aio_write_op_operate2` và `rados_read_op_stat2` với `timespec`; API cũ vẫn còn. `librados.hpp` deprecate boolean self-managed-snapshot query và thêm hàm trả lỗi; `RadosClient.cc` chờ OSD map rồi phân biệt `-ENOENT`. `librados_asio.h` đổi completion signature để trả thêm `version_t` và dùng generic error category. `rgw_file.h` đổi callback `rgw_readdir_cb` từ `bool` sang `int`. Python RADOS cho phép OMAP key dạng bytes và chọn decoder của iterator.

**Before/after.** Binary dùng symbol cũ vẫn có đường tương thích trong reviewed diff, nhưng source consumer của Asio hoặc rgw_file phải sửa/rebuild theo header Reef; Python consumer phụ thuộc key luôn là `str` có thể đổi hành vi nếu chọn bytes. Không hot-swap shared library bên dưới process sống lâu. Tác động delivery/source compatibility; confidence `high`, inventory ứng dụng là `UNKNOWN`.

### RADOSOBS-001 — Client Objecter thêm latency và in-flight metrics

**Evidence.** `Objecter.cc` đăng ký `op_latency` và `op_inflight`, cập nhật chúng khi nhận OSD reply.

**Before/after.** Reef client có thêm signal để phát hiện queue/latency trong mixed phase; đây không phải bằng chứng hiệu năng tốt hơn. Collector/dashboard chỉ thấy chúng sau khi process dùng target client restart và exporter path thu đúng counters. Tác động observability/acceptance; confidence `high`, áp dụng khi pipeline thu client perf counters.

### RADOSCLI-001 — `rados` xử lý pool state và xattr output khác

**Evidence.** `rados.cc` decode xattr `refcount` thành references/retired references thay vì in raw bytes; `cppool` và snapshot create dùng query self-managed-snapshot trả lỗi, dừng rõ ràng khi pool lookup thất bại; error của `rmomapkey` in đúng object hiện tại.

**Before/after.** Script parse raw `getxattr ... refcount`, dựa vào boolean false khi pool chưa có trong map, hoặc match error text có thể khác sau đổi binary. Tác động maintenance automation; confidence `high`, chỉ áp dụng khi dùng các subcommand đó.

### RBDAPI-001 — Public librbd/Python contract và error propagation đổi

**Evidence.** `LIBRBD_VER_MINOR` tăng `17→18`; public API thêm clone-format, diff/encryption capability. `Operations.cc` không còn biến một số lỗi thành success cho flatten, rebuild object map, rename, snapshot create/remove/rename/protect/unprotect, metadata remove, migrate và sparsify. Group rollback từ chối snapshot incomplete hoặc membership hiện tại không khớp. Pool/namespace init tạo sẵn `rbd_trash`; missing snapshot timestamp trả `-ENOENT` thay assert. `librbd.cc` vô hiệu image handle trước khi bắt đầu close/aio_close.

**Before/after.** Automation Quincy coi lệnh lặp/idempotent là success có thể nhận `-EEXIST`, `-ENOENT`, `-EINVAL` hoặc lỗi thật trên Reef. API mới là additive trong reviewed header, nhưng process dùng library mới phải được contract-test và restart có kiểm soát. Mixed cluster không tự kích hoạt finding này; version của client/tool đang chạy mới quyết định semantics. Tác động automation/availability; confidence `high`.

### RBDDIFF-001 — Fast-diff, snapshot-set diff và object-map range đổi

**Evidence.** `snap_set_diff.cc` sửa boundary khi truncate, missing end clone và running diff. `DiffIterate.cc` chuyển từ snapshot name nội bộ sang snapshot ID, validate ID/range, thử lấy exclusive lock có throttle, chỉ tải object-map range cần thiết và tính parent extents theo image area. `object_map/DiffRequest.cc` nhận start/end object, giữ object-map lock qua phép đọc và trả vector đã cắt range. Public C/Python API thêm diff-by-ID; trash purge/deep-copy dùng engine mới.

**Before/after.** Cùng snapshot chain có thể trả tập extent khác, đặc biệt sau shrink/truncate, clone parent và fast-diff. Đây là correctness risk cho incremental backup, replication/copy validation và accounting; không được xem output khác là regression cho đến khi đối chiếu full read, nhưng cũng không được nối mù một incremental chain qua đổi client. Confidence `high`; áp dụng khi image có snapshot/diff/fast-diff/object-map.

### RBDCRYPT-001 — Encryption hỗ trợ auto-detect, nhiều ancestor và flatten clone

**Evidence.** API thêm generic `LUKS`, `rbd_encryption_load2` và danh sách spec; target load path detect LUKS1/LUKS2 magic, nhận credential riêng cho image/ancestor và giữ crypto header thành một `ImageArea` tách biệt. Encryption format không còn cấm clone; `FlattenRequest` gọi handler format-specific để materialize crypto header. Resize, trim, sparsify, copyup, deep-copy, cache, journal và diff đều chuyển raw/data/crypto-header offsets rõ ràng. `rbd-nbd` nhận nhiều format/passphrase và mặc định auto-detect.

**Before/after.** Quincy chủ yếu load một format/passphrase và không format cloned image; Reef có thể mở/flatten encrypted clone chain với nhiều header size. Sai thứ tự/số credential hoặc regression offset có thể làm open fail hoặc đọc sai vùng; non-encrypted image đi qua area mapping với crypto-header size bằng zero nhưng vẫn cần smoke test. Không chạy flatten/migration encrypted image trong rollout đầu tiên. Tác động data access/integrity; confidence `high`, applicability phụ thuộc encrypted image/clone inventory.

### RBDIO-001 — Core I/O, parent overlap và journal chuyển sang multi-extent/image-area

**Evidence.** `ImageCtx` thay effective-size remap bằng `DATA`/`CRYPTO_HEADER` area, giảm parent overlap theo cả parent và child. Public I/O gắn `ImageArea::DATA`; dispatcher/object request/copyup chuyển đổi area↔object extents. Journal write/write-same/discard giữ danh sách extents thay một offset/length. Trim/sparsify và object-cache writeback dùng parent overlap mới. `Operations.cc` tính raw resize size trước object-map compatibility và request.

**Before/after.** Existing read/write/discard/resize/copyup/flatten/journal replay đi qua code target khác ngay khi client Reef mở image, kể cả OSD còn mixed-version. Không có wire/on-disk break tổng quát được chứng minh, nhưng blast radius là data path nên cần image clone và checksum, không chỉ CLI success. Confidence `high` cho code path, correctness runtime chưa được xác nhận.

### RBDCACHE-001 — Parent cache, persistent write log và immutable cache lifecycle đổi

**Evidence.** Parent-cache miss tôn trọng `READ_FLAG_DISABLE_READ_FROM_PARENT`; persistent write log deep-copy buffer có assert length và crypto-header bypass; object cacher tính parent overlap theo image area. `immutable_object_cache` sửa exit code bị đảo ngược để trả failure khi run thất bại.

**Before/after.** Cache miss/fallback, encrypted header access và service restart signal có thể khác. Nếu immutable-object-cache/PWL không được bật thì phần lớn không áp dụng; nếu bật, phải kiểm warm/cold read, restart và recovery trước khi cho target client phục vụ write. Tác động availability/data-path; confidence `high`, applicability `UNKNOWN`.

### RBDMIG-001 — Migration/deep-copy đổi source dispatch và clone policy

**Evidence.** Native/QCOW/raw/HTTP source handlers, `OpenSourceImageRequest` và migration dispatch được rework; deep-copy/object-copy dùng range-aware diff và image areas. Python API thêm `clone_format`/`flatten` cho migration prepare và deep copy. Encrypted clone flatten được nối vào operation path.

**Before/after.** Migration/import/deep-copy chạy bằng target client có thể giữ parent bằng clone format mới hoặc flatten theo option, và materialize extents khác với Quincy. Đây là explicit operation risk, không tự xảy ra chỉ vì nâng daemon. Tác động data movement/rollback; confidence `high`. Freeze các job này trong daemon rollout và chỉ mở lại sau rehearsal source-format + snapshot + parent + checksum.

### RBDMIRROR-001 — Peer reconciliation, namespace handling, replay metrics và lock scope đổi

**Evidence.** `rbd-mirror` recreate PoolReplayer khi cùng peer UUID nhưng cấu hình peer đổi; đọc mirror mode bằng đúng namespace; dọn callout ở destructor. `ImageReplayer` thu hẹp lock scope trước reschedule status. Journal/snapshot replay đổi perf-counter family, thêm namespace label, remote/local timestamps và last-sync metrics. Snapshot replay/copy dùng target extent logic; CLI status sửa namespace context.

**Before/after.** Peer update có thể restart replayer thay vì giữ instance stale; namespaced pool có state đúng hơn. Đồng thời metric name/label đổi có thể làm alert/dashboard cũ mất series. Trong mixed deployment, chỉ một active ownership path cho mỗi image/peer và phải tránh promote/demote đồng thời với daemon replacement. Tác động replication availability/observability; confidence `high`, mode/peer applicability `UNKNOWN`.

### RBDCLI-001 — `rbd` actions và validation behavior đổi

**Evidence.** Argument/utility layer và actions cho children, encryption, flatten, group, mirror, resize, rename và bench thay đổi. `rbd bench` seed random trước khi dựng helper; group rollback và operation errors bên dưới được truyền ra thay vì luôn success; encryption CLI dùng generic/multi-spec load path.

**Before/after.** Runbook parse output/return code hoặc retry command có thể dừng khác trên target. Lệnh read-only vẫn cần golden-output contract; lệnh mutate không được thử trên production để “xem có chạy không”. Tác động operator automation; confidence `high`, command-specific applicability.

### RBDMAP-001 — Linux NBD và Windows WNBD lifecycle/resize đổi

**Evidence.** `rbd-nbd` dùng netlink mặc định (giữ option cũ để compatibility), gắn backend cookie khi resize, chuyển image notification sang worker, invalidate cache/rescan partition và hỗ trợ nhiều encryption passphrase. WNBD sửa sign của error code, dùng atomic state khi remount/unmap, theo dõi resize qua image watch và thêm optional WMI adapter monitor/remount. GGATE rows chỉ đổi modeline và được chốt trivial.

**Before/after.** Existing mapped device có thể resize/reconnect và báo lỗi khác sau process/service target restart; Linux kernel/netlink hoặc Windows driver/WMI là dependency ngoài repo. Không in-place đổi mapping quan trọng nếu chưa chứng minh reconnect, partition rescan, cache coherence và unmap cleanup trên OS/driver thật. Tác động client availability; confidence `high`, applicability theo inventory mapping.

### RBDPKG-001 — Python binding build cần `packaging` và tương thích Cython 3

**Evidence.** `src/pybind/rbd/setup.py` import `packaging.version` và chọn `legacy_implicit_noexcept` theo Cython version.

**Before/after.** Image/RPM/DEB build environment thiếu `packaging`, hoặc generated extension không khớp Cython/runtime, có thể fail trước khi Python automation dùng RBD. Tác động delivery; confidence `high`. Cần test artifact thực, không suy từ source tree.

**Closure.** Dependency/extension import tự động kích hoạt at Python module load. Mixed-version clients must keep pinned wheel/RPM plus matching runtime; full-Reef only after every supported Python/Cython lane passes. Rollback is restore prior artifact/environment and restart consumer, while image mutations still follow RBD data rollback gates. Chưa có exact artifact digest; validate import, create/open/read/diff/async-close and exception ABI.

## Operational closure addenda

#### RADOSAPI-001 — Closure

API behavior tự động activates when consumer restarts/links target library. Mixed/full must rebuild and run representative consumers without hot-swap. Rollback by restore pinned library/process after draining callbacks; writes need object manifest. Validate ABI symbols, async completion/error and data checksum.

#### RADOSOBS-001 — Closure

Rollback metrics by dual-schema collector or old client process; time-series history is not rewritten. Chưa có consumer/baseline inventory. Validate raw counters/labels/in-flight lifecycle and alert replay through reconnect in mixed/full.

#### RADOSCLI-001 — Closure

CLI contract activates when target tool runs; mutation remains explicit. Mixed/full replay same read-only corpus on old/new pool states. Rollback by pin old CLI/parser; xattr/object mutations require snapshot/version manifest. Validate stdout/stderr/exit code and bytes-safe xattr output.

#### RBDAPI-001 — Closure

Chưa có external consumer and binding inventory, so applicability/error tolerance remains `UNKNOWN`. Mixed/full must rebuild C/C++/Python users and run async close/error cases. Rollback by pinned process/library before target-only writes; preserve image snapshot and checksum.

#### RBDDIFF-001 — Closure

Diff logic activates automatically for fast-diff/snapshot-set calls; object-map rebuild is explicit. Mixed/full must compare extents against full byte oracle. Rollback incremental chain by restore full baseline/image snapshot; do not continue backup chain after mismatch. Validate grow/shrink/discard/clone cases.

#### RBDCRYPT-001 — Closure

First target encrypted write/flatten is rollback boundary; credentials alone do not make old-reader safe. Keep disposable clone and old-client reopen/checksum proof. Mixed/full matrix must cover LUKS1/2, auto-detect, parent formats and wrong/missing keys without logging secrets.

#### RBDIO-001 — Closure

Rollback after target multi-extent/journal writes requires image snapshot/version and old-reader verification; no inverse I/O transform. Mixed/full validation must exercise unaligned/striped I/O, copyup, resize, replay and parent isolation with checksums.

#### RBDCACHE-001 — Closure

Mixed/full must test target cache daemon/client against warm/cold/error fixtures and encrypted header bypass. Rollback by flush/drain, disable cache, restore pinned service and verify image checksum; cache journal/state may require discard only on disposable copy. Validate fallback and exit codes.

#### RBDMIG-001 — Closure

Applicability depends active migration/deep-copy jobs and source types; chưa có inventory. Do not mix client versions within one job. Rollback point is before commit/execute; after that use source/image snapshots and documented abort semantics. Validate raw/QCOW/native/HTTP, clone policy and encryption.

#### RBDMIRROR-001 — Closure

Rollback mirror canary by pause/drain daemon, restore peer config/binary and reconcile image state; resync already triggered is not undone by restart. Validate journal/snapshot modes, namespaces, peer UUID edit, failover, lag and metrics with checksum.

#### RBDCLI-001 — Closure

CLI action behavior activates when target tool runs; destructive commands remain explicit. Mixed/full contract tests must separate desired-state idempotent errors from failure. Mutation rollback requires disposable image/snapshot and command ledger; read-only can pin old CLI/parser.

#### RBDMAP-001 — Closure

Mixed/full must canary exact kernel NBD or WNBD driver/client pair; mapping lifecycle cannot be inferred from librbd tests. Rollback by quiesce/unmap, restore old service/driver and remap after checksum; live resize/partition state needs reconciliation. Validate reconnect, resize, restart and secret handling.

## Trivial changes

276 hàng `trivial` gồm 25 docs, 126 QA/workunit, 86 hàng dưới `src/test/` chưa chạy và 39 runtime/support rows là std::variant/C++ modernization giữ nguyên encoding, editor modeline, log/help/comment, test mock, equivalent flag spelling hoặc compile-only cleanup. Test/docs được dùng làm context cho findings nhưng không phải acceptance result. Lý do ổn định từng hàng nằm trong CSV.

## Validation đề xuất

1. **As-Is client matrix:** inventory package/container và process link tới librados/librbd; ngôn ngữ/binding; restart owner; image features, snapshots, parent chain, encryption, cache/journal, mirror mode và mappings. Ghi exact SONAME/package/build ID.
2. **ABI/source gate:** build representative C/C++/Asio/rgw_file consumers bằng header target; kiểm exported symbols cũ/mới và chạy process target trên pool lab. Python test phải bao phủ OMAP `str`/`bytes`, close/aio-close và async error path.
3. **Mixed-client policy:** không hot-swap library. Restart client theo cohort, giữ canary Quincy và Reef đọc cùng non-production image; so read/checksum/error contract. Chỉ nâng cohort tiếp theo khi không có disconnect/retry storm.
4. **Diff/backup oracle:** clone image có parent, object-map/fast-diff, writes, discard, grow/shrink và nhiều snapshot. So Quincy/Reef extent output với full byte comparison. Sau đổi client, tạo full baseline mới trước khi tiếp tục incremental chain nếu công cụ không chứng minh cross-version continuity.
5. **Encryption matrix:** LUKS1/LUKS2, auto-detect, non-clone, same/different-format parent-child, đúng/sai/missing credential; read/write/resize/snapshot/diff/flatten trên disposable clone và checksum cả trước/sau reopen.
6. **Core I/O:** fio/rbd bench chỉ trên lab image, bao phủ unaligned/striped I/O, discard/write-zeroes, copyup, shrink/grow, object-map rebuild, journal replay và restart. Fail nếu checksum, snapshot read hoặc parent isolation khác expected.
7. **Cache conditional:** PWL/immutable parent cache warm/cold/miss/recovery, service failure exit code và encrypted header bypass; verify fallback không đọc parent khi flag cấm.
8. **Migration/deep-copy:** freeze production jobs trong daemon rollout. Rehearse raw/QCOW/native/HTTP source, snapshot chain, clone-format 1/2, flatten true/false và encrypted parent; xác nhận rollback point trước commit/execute.
9. **Mirroring:** snapshot và journal mode, default + named namespace, peer edit cùng UUID, daemon restart và failover. So image state, lag, callout cleanup và metric names/labels; mất mirror telemetry hoặc unexpected resync là stop condition.
10. **CLI contracts:** replay read-only golden tests cho `rados`/`rbd`; riêng idempotent errors phải được automation xử lý theo desired state thay vì giả định return 0. Mutation case chỉ chạy trên disposable pool/image.
11. **NBD/WNBD:** kernel/driver-specific map, reconnect, live resize, partition rescan, cache invalidation, service restart và clean unmap. Encrypted parent chain phải kiểm số/thứ tự passphrase và không lộ secret trong argv/log.
12. **Packaging:** import Python bindings từ đúng target artifact, xác nhận `packaging`/Cython-generated ABI và chạy minimal create/open/read/diff/close smoke trước rollout client cohort.

## Kết luận owner

Owner 10 đã khép binary gate. Ba gate lớn nhất là: chứng minh diff/incremental-backup correctness qua truncate/clone; rehearsal encrypted clone và image-area I/O; và inventory/restart có kiểm soát mọi external client/mapping/mirror daemon. Reviewed diff không cho bằng chứng về một on-disk `cls_rbd` encoding break tổng quát, nhưng client target đổi đủ nhiều đường I/O và error contract để không thể chỉ dựa vào cluster health. Chưa có lab/As-Is nên chưa có GO/NO-GO production.
