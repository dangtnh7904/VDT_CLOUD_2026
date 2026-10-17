# 15 — cross-component validation, QA và release claims: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./15-upgrade-validation.csv) có 529 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 102`, `trivial = 427`, chưa phân loại = 0. Detailed findings chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow/non-ancestor, nên báo cáo chỉ dùng endpoint tree/hunk, suite topology, symlink selector và caller context; không suy lịch sử commit còn thiếu.

Quan trọng nhất: **test source không phải test result**. Không có teuthology run ID, archive, console log, image digest, package manifest, hardware topology hay kết quả lab cho đúng hai tag. Các suite `quincy-x` dùng `branch: quincy`, image `latest-quincy` hoặc biến `$sha1`; chúng có đúng ý nghĩa major-hop nhưng không tự chứng minh đã chạy đúng `v17.2.7→v18.2.7`. Báo cáo không cấp quyền upgrade, restart, pause/resume, thrash, đổi compatibility floor hay thao tác cluster production.

[Test-selection manifest](./RUNTIME-TEST-SELECTION.md) đã chọn 19 pack bao phủ đủ 52 runtime gate và kiểm trực tiếp 45 source path tại target SHA. [Exact-hop pin register](./EXACT-HOP-PINS.md) audit tiếp 16 base branch selector, 3 cephadm branch selector, 3 base image tag nổi, 3 target image `$sha1`, 7 version check `$sha1` và 3 distro selector. Manifest phân biệt native-hop, reusable, hybrid và custom; 19/19 pack vẫn `NOT_RUN`, 12/12 pin vẫn `PENDING_INPUT`.

## Finding ảnh hưởng upgrade

### VALDAEMON-001 — Có suite daemon Quincy→Reef với rolling và mixed-version stress

**Evidence.** 40 hàng dưới `qa/suites/upgrade/quincy-x` (ngoài case FileStore) dựng hai topology chính. `parallel` cài Quincy bằng cephadm, chạy RADOS/RBD/read-write/snapshot workloads, gọi `ceph orch upgrade --image ...:$sha1`, poll trạng thái/versions rồi yêu cầu chỉ còn một target version. `stress-split` nâng MON theo minority/majority/all, pause/resume giữa các pha, nâng một nửa OSD, chạy thrash/workload khi mixed-version, sau đó resume và kiểm full target.

**Before/after.** Coverage source của target tốt hơn Quincy: nó kiểm đường orchestrated upgrade, maintenance interruption và I/O trong trạng thái hỗn hợp. Tuy nhiên selector không khóa hai audited tag/digest và không có run archive; vì vậy confidence `high` cho topology, `UNKNOWN` cho kết quả. Gate cần chạy lại cả parallel lẫn stress-split trên artifact sắp rollout, lưu per-daemon version, health timeline và workload errors.

### VALFILE-001 — Suite có negative gate chặn FileStore trước Reef

**Evidence.** 12 hàng `filestore-remove-check` tạo cluster Quincy với FileStore rồi chạy upgrade, đặt `require-osd-release quincy`, restart daemon và yêu cầu lỗi chứa `FileStore has been deprecated and is no longer supported`.

**Before/after.** Đây là executable evidence bổ sung cho `FILESTORE-001`: target không coi FileStore là topology được nâng trực tiếp. Nhưng suite chỉ tồn tại trong source, chưa có exact-tag result. Inventory production phải chứng minh `0` FileStore OSD trước khi rehearsal; case negative phải fail đúng lý do và BlueStore control case phải pass.

### VALDISTRO-001 — Exact-hop suite đổi container-host matrix

**Evidence.** Target thêm selector cho CentOS Stream 9, CentOS Stream 9 với runc và Ubuntu 22.04 dưới `qa/distros/supported-container-hosts`; `quincy-x` trỏ vào tập supported container hosts.

**Before/after.** Hệ điều hành/container runtime ảnh hưởng cephadm, systemd, podman/runc, package và network behavior. Ba selector không bao phủ tự động distro/architecture production khác. Gate phải chọn ít nhất một lane khớp từng cohort thực và ghi kernel, runtime, storage/network driver; confidence `high` cho matrix source, applicability phụ thuộc As-Is.

### VALCLIENT-001 — Native client suite của exact hop bị repurpose sang Reef→Squid

**Evidence.** Các file openstack/start/install/workload của `client-upgrade-quincy-reef/quincy-client-x/rbd` được rename/repurpose dưới `client-upgrade-reef-squid/.../reef-client-x/rbd`; Ubuntu 20.04 selector cũ bị xóa và target thêm CentOS selector cho suite mới. Một `.qa` root cũ còn được dùng lại cho telemetry topology.

**Before/after.** Target tree không giữ một suite độc lập, hoàn chỉnh có thể chạy nguyên trạng cho client binaries Quincy→Reef. Daemon suite vẫn chạy một số RBD workloads nhưng không thay thế matrix client cũ/new daemon và new client/old daemon. Đây là coverage gap, không phải bằng chứng client incompatibility. Phải dựng lại exact-pair client lanes và kiểm connect, image open/read/write, notification/watch, map/unmap và retry qua từng daemon phase.

### VALTELEM-001 — Telemetry opt-in và collection continuity có coverage major-hop

**Evidence.** `telemetry-upgrade/quincy-x` cài `latest-quincy`, chạy `test_telemetry_quincy.sh`, nâng tới `$sha1`, kiểm single version rồi chạy `test_telemetry_quincy_x.sh`. Workunit kiểm `last_opt_revision == 1`, preview/show và các collection `perf_perf`, `basic_mds_metadata`, `basic_pool_usage`, `basic_rook_v01`, `perf_memory_metrics`, sau đó opt-out.

**Before/after.** Coverage bảo vệ consent/collection continuity qua MGR upgrade, nhưng không khóa image/tag và không chứng minh endpoint đã pass. Cần chạy với telemetry endpoint giả/lab, không gửi dữ liệu production ngoài ý muốn; đồng thời kiểm exporter/Prometheus path của `MGRMETRIC-001` vì suite này không thay thế metric-scrape acceptance.

### VALHARNESS-001 — Kết quả phụ thuộc target suite graph và helper version

**Evidence.** `.qa` suite roots cùng `qa/tasks/ceph.py`, `ceph_manager.py`, `thrasher.py` đổi discovery, cluster command/lifecycle, RBD pool init và thrasher interface. Exact-hop suites gọi các helper này trực tiếp hoặc qua standard teuthology tasks.

**Before/after.** Chạy YAML target với harness Quincy, hoặc harness target với selector cũ, có thể thay command, timeout và cleanup semantics. Run record phải pin Ceph tree, teuthology tree, suite commit, job config và all overrides; rerun failure bằng cùng pins trước khi coi là product regression.

### VALFINAL-001 — Fixture có thể nâng compatibility floor lên Reef

**Evidence.** `qa/releases/reef.yaml` chạy `ceph osd require-osd-release reef` và `ceph osd set-require-min-compat-client reef`, sau đó đợi healthy.

**Before/after.** Đây là post-upgrade feature gate, không phải bước vô hại trong rolling phase. Khi đã nâng min-compatible client, Quincy/older client eligibility thay đổi và rollback assumptions phải được xét lại. Chỉ invoke sau full-version, client inventory và rollback decision; file tồn tại không chứng minh production đã sẵn sàng.

### VALDENC-001 — Dencoder/corpus coverage đổi nhưng chưa khóa exact pair

**Evidence.** Target đổi plugin discovery của `ceph-dencoder`, bỏ legacy FileStore/message types, thêm nhiều RGW cls/usage/lifecycle types và cập nhật OSD/MDS registrations. QA thêm task clone branch `main` và mặc định `branch_N-2: quincy`, cùng readable/corpus workunits.

**Before/after.** Tool có thể kiểm target decoder đọc corpus cũ, nhưng branch defaults không phải `v17.2.7`/`v18.2.7`; không có corpus hash hay result. Gate phải sinh/khóa Quincy corpus trước, chạy Reef decoder trên bản sao, lưu type coverage và phân biệt “type không đăng ký trong tool” với “daemon không decode được persisted/wire object”.

### OPSCLI-001 — Python CLI address validation không còn chấp nhận cùng input

**Evidence.** `CephIPAddr.valid()` bỏ bước strip prefix `v1:`, `v2:` và `any:`; PG parse error cũng được sửa để báo input string thay vì biến chưa khởi tạo.

**Before/after.** Script/operator input truyền prefixed address vào command schema dùng `CephIPAddr` có thể được Quincy chấp nhận nhưng Reef từ chối trước khi gửi command. Không phải mọi `v1:`/`v2:` address trong config đều đi qua class này. Inventory automation arguments, replay dry-run và sửa về schema target; confidence `high` cho parser, applicability `UNKNOWN`.

### ADMOSD-001 / CVINVENTORY-001 — Residual review xác nhận DriveGroup selection đổi

**Evidence.** Python common thêm filter `actuators`, sửa size matcher, không tính device đã là Ceph device hai lần khi áp `limit`, normalize service-id comparison và đổi command generation. `translate.py` bỏ toàn bộ FileStore rendering, đổi raw/LVM/crush-device-class output.

**Before/after.** Cùng persisted OSD spec + inventory có thể cho preview/command khác sau MGR target takeover. Đây là cross-evidence cho `ADMOSD-001`, `CVINVENTORY-001`, `CVFILESTORE-001` và `FILESTORE-001`, không phải finding độc lập mới. Freeze auto-apply, lưu spec/inventory và diff dry-run command trước khi reconcile.

### ADMMIG-001 / ADMSCHED-001 / ADMSVC-001 — Shared persisted service schema đổi

**Evidence.** `service_spec.py` thêm typed host pattern (glob/regex), đổi serialization của container/entrypoint arguments, mở rộng existing RGW/NFS/ingress fields và service types. `hostspec.py` thêm out-of-band credential block; `rgwam_core.py` đổi secondary-zone endpoint/token field và retry period update.

**Before/after.** Target MGR có thể parse, serialize và render persisted specs khác trước khi toàn cluster full-version. Cross-owner finding ở owner 08 vẫn là source of truth; owner này xác nhận shared schema nằm ngoài module directory. Export/round-trip specs trên clone Store, diff canonical JSON/rendered args và kiểm idempotent second load trước reconcile.

### ADMAGENT-001 / NODEPROXY-001 — Shared HTTP/TLS helper đi vào agent control path

**Evidence.** `ceph.utils.http_req()` được thêm với TLS context, certificate verification toggle, timeout và HTTP error propagation; target callers gồm cephadm agent và node-proxy. Host address validator cũng đổi thứ tự reject bracketed IPv4.

**Before/after.** Certificate/name/timeout mismatch có thể làm target mark agent/node-proxy communication failed. Đây là cross-evidence cho owner 08/13; node-proxy chỉ áp dụng khi opt-in. Test trusted/untrusted CA, hostname/IP, timeout và retry trên management network lab.

### RADOSDEDUP-001 — Optional dedup tool đổi CLI và thêm daemonized sample dedup

**Evidence.** `ceph-dedup-tool` chuyển option parser/defaults, thêm `sample-dedup`, fingerprint/chunk threshold store, daemon/loop, snapshot-aware object dedup và tier flush/evict flow. QA task mới kiểm chunk references và repair.

**Before/after.** Không áp dụng cho cluster không dùng dedup tier/tool. Khi đang dùng, lệnh/flags/defaults và mutation behavior khác, nên không chạy trực tiếp trên production data để “test upgrade”. Clone/synthetic pools phải kiểm estimate, chunk boundaries, reference consistency, snapshot behavior, restart và cleanup trước; confidence `high`, applicability `UNKNOWN`.

**Impact và mixed/full:** correctness/durability của optional tool và validation coverage đổi khi explicit chạy dedup; upgrade binary không tự dedup pool. Mixed clients/tools phải được pin theo từng job, không đổi executable trong crawler đang chạy; full Reef không chứng minh refcount graph/flush-evict kết quả đã đúng. Giữ synthetic/cloned base+chunk pools, snapshots, refcount manifest và bytes trước sample/object dedup, dừng trên hash/refcount mismatch hoặc daemon không kết thúc. Hạ package không undo manifests/chunks/snapshot mutation; restore/cleanup phải được rehearsal, runtime vẫn NOT_RUN.

## Operational closure addenda

#### VALDAEMON-001 — Closure

Suite only activates by explicit lab/job invocation; no production action is implied. Impact of missing exact run is inability to accept daemon availability/correctness. Mixed/full lanes are already modeled. Rollback is restore disposable fixture/snapshot and pinned old images, not proof of live downgrade. Retain checksums, health and version timeline.

#### VALFILE-001 — Closure

Mixed/full rollout is blocked unless inventory proves zero FileStore; the negative suite itself runs only on disposable fixture. Impact is absolute activation/data availability failure for FileStore. Rollback is keep/rebuild Quincy fixture, not start Reef then revert store. Confidence `high` for source gate, result `UNKNOWN`; validation needs exact-tag negative and BlueStore control archives.

#### VALDISTRO-001 — Closure

Impact is artifact/cephadm/systemd/network compatibility per host cohort. Rollback by restore prior image/package/runtime snapshot on disposable host after service drain. Chưa có production distro/architecture mapping or exact result. Validate each real kernel/runtime/storage/network lane and record deviations from provided selectors.

#### VALCLIENT-001 — Closure

Applicability covers every external client cohort; exact client matrix is missing. Custom lanes activate only by explicit test job. Mixed-version must cover old-client/new-daemon and new-client/old-daemon; full-Reef retest after reconnect. Impact is API/I/O compatibility and data correctness. Rollback by pinned client process/package plus image/data snapshot. Confidence `high` for coverage gap, runtime `UNKNOWN`; cần exact artifacts and result archive.

#### VALTELEM-001 — Closure

Áp dụng only when telemetry is enabled/being validated; opt-in/out is explicit and must use lab sink. Mixed/full must preserve consent/revision while MGR/exporter changes. Impact is privacy/observability continuity. Rollback by opt-out/restore config and pinned MGR only after collection state capture. Confidence `high` for source coverage, result `UNKNOWN`.

#### VALHARNESS-001 — Closure

Harness behavior activates automatically when the pinned job executes helpers. Mixed/full results are valid only with identical recorded Ceph/teuthology/suite/helper pins. Impact is false pass/fail, cleanup and timeout semantics. Rollback is recreate fixture and rerun with same pins, not mutate failed environment. Confidence `high` for source drift, unresolved exact result; validation retains configs/logs/overrides.

#### VALFINAL-001 — Closure

Confidence `high` that fixture issues irreversible compatibility-floor commands, but runtime readiness remains `UNKNOWN`. Only explicit post-full-Reef invocation is allowed after client inventory and rollback decision. Removal is not rollback because floors cannot be lowered. Record maps/features and keep this step outside binary acceptance.

#### VALDENC-001 — Closure

Applicability covers encoded types actually persisted/exchanged by As-Is; corpus generation/decoder run are explicit. Mixed/full must lock Quincy corpus, run Reef decode, then service-specific reopen; tool registration alone is not daemon proof. Impact is persistence/wire compatibility. Rollback is immutable corpus/store clone and old-reader test. Confidence `high` for graph delta, result `UNKNOWN`; validation needs type coverage and hashes.

#### OPSCLI-001 — Closure

Parser change tự động applies when target CLI validates matching arguments; command mutation remains explicit. Mixed/full must replay real automation argv against old/new CLI/endpoints. Impact is automation refusal or wrong remediation. Rollback by pin old CLI/parser and normalize inputs; mutation commands require state manifest. Keep stdout/stderr/exit and observed state.

#### RADOSDEDUP-001 — Closure

Dedup mutation has no generic inverse: rollback requires cloned/synthetic pool snapshot, reference manifest and cleanup rehearsal. Never mix tool versions within a running dedup job. Validate estimate/sample/daemon restart, snapshots, chunk references and flush/evict before marking applicable lane PASS.

## Trivial changes

427 hàng `trivial` gồm 217 generic/older/newer-release QA rows không thuộc exact hop, 106 documentation/release-note rows, 55 unit/performance-test rows chưa chạy, 47 examples và 2 typing/standalone perf-tool rows. Chúng vẫn có thể là context hoặc test candidate nhưng không tự thay đổi production rollout và không phải acceptance evidence. Lý do ổn định từng hàng nằm trong CSV.

## Ma trận validation bắt buộc

1. **Pin exact endpoints:** build/pull artifact từ đúng `v17.2.7` và `v18.2.7`; lưu package NEVRA/version, image digest, architecture, source SHA, SBOM và config overrides. Không dùng `latest-quincy` hay floating branch.
2. **Preflight clone:** snapshot config/spec/auth/CRUSH/OSD metadata; chứng minh không có FileStore; inventory client versions, features và compatibility floor. Fail closed nếu As-Is còn unknown quan trọng.
3. **Parallel lane:** chạy exact-tag `quincy-x/parallel`, giữ workloads xuyên upgrade, thu orch status, daemon versions, health/detail, crash, slow ops và data checksums.
4. **Stress-split lane:** pause/resume tại minority/majority/all MON và half OSD; chạy read/write, snapshots, RADOS/RBD workloads và controlled thrasher trong mixed-version. Không cho test fault injection chạm production.
5. **Negative FileStore lane:** case FileStore phải fail trước mutation target đúng message; BlueStore control case phải tiếp tục. Đây là test disposable-only.
6. **Client matrix:** tối thiểu old client/new daemon và new client/old daemon cho từng client cohort thực; RADOS/RBD/CephFS/RGW theo inventory, kèm reconnect/retry và protocol capture khi cần.
7. **MGR/orchestrator state:** clone Store, load target MGR, diff migration level, service/host/DriveGroup JSON, placement, rendered commands/config; second load phải idempotent và không tạo daemon/device mutation ngoài allowlist.
8. **Telemetry/observability:** consent/revision/collections, ceph-exporter/Prometheus scrape, alert continuity và dashboard secure access; dùng lab sink, lưu metric/label diff.
9. **Encoding/persistence:** khóa Quincy object corpus và representative monitor/MGR/RGW/OSD metadata clone; chạy target dencoder/readability và service-specific reopen/restart checks.
10. **Artifact/result retention:** lưu teuthology job config, suite/harness commit, console/archive links, timestamps, failure triage và rerun. PASS chỉ hợp lệ cho exact pins; không chuyển source-suite existence thành PASS.

## Kết luận owner

Owner 15 đã khép binary gate và test-selection source audit. Repository có coverage source khá tốt cho daemon rolling/mixed-version và FileStore negative gate, nhưng còn ba gap quyết định: chưa có kết quả cho exact tags/artifacts, native client suite của exact hop đã bị repurpose, và persisted MGR/service state chưa được rehearsal trên clone. Vì vậy owner này **không phát hành GO/NO-GO production**; nó định nghĩa các phép kiểm phải có trước quyết định đó.
