# 07 — MGR, Dashboard, modules và monitoring: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./07-mgr-modules-monitoring.csv) có 670 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 78`, `trivial = 592`, chưa phân loại = 0. Detailed findings bên dưới chỉ được promote từ hàng `affect`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor, nên commit-range không đủ để chứng minh lịch sử/intent; kết luận dựa trên hunk, endpoint symbol/caller, generated outputs và test context.

Chưa có As-Is về enabled MGR modules, `.mgr` pool/libcephsqlite state, Dashboard usage, Rook, RBD schedules, balancer/autoscaler, Prometheus/ceph-exporter, Grafana/Alertmanager/SNMP hay external collectors. Chưa chạy repository test hoặc lab. Báo cáo không cấp quyền failover MGR, drain/zap host, redeploy monitoring hay điều khiển upgrade production.

## Finding ảnh hưởng upgrade

### MGRCORE-001 — Active MGR locking, daemon state và connection identity đổi

**Evidence.** `ActivePyModules.cc` snapshot `ConfigProxy` trước khi Python formatter có thể thả/lấy GIL, tránh giữ global config lock qua đường có thể deadlock. `Mgr.cc` bỏ qua OSD không tồn tại hoặc vừa out+down và xóa health metric stale; `DaemonServer.cc` đổi report/auth handling, RGW daemon lookup và chỉ gửi `MOSDScrub2`. Active/standby messenger dùng random nonce thay process-derived nonce.

**Before/after.** MGR Reef có failure/telemetry behavior khác khi config reload đồng thời, OSD out/down, RGW perf lookup hoặc MGR restart/failover. Việc bỏ legacy scrub message không gây incompatibility cho Quincy OSD có feature `SERVER_MIMIC`; nó chỉ là blocker nếu As-Is phát hiện OSD cũ hơn support matrix. Tác động control-plane availability/observability; confidence `high`, deployment applicability chưa biết.

### MGRDB-001 — MGR SQLite chuyển transaction/reconnect contract và DeviceHealth recovery

**Evidence.** `mgr_module.py` đổi schema từ script string thành danh sách statement, dùng explicit `BEGIN`, `isolation_level=None`, thêm close/reopen retry tối đa ba lần và đăng ký lại address của `libcephsqlite`. `ActivePyModules`/`BaseMgrModule`/`PyModuleRegistry` hỗ trợ named client replace. `devicehealth/module.py` chuyển schema/ghi metrics sang transaction và bọc command/serve bằng database recovery.

**Before/after.** Khi `.mgr` pool/PG tạm thời unavailable hoặc active MGR failover, Reef đóng/mở DB và cập nhật client address thay vì tiếp tục với connection mất lock. Existing DB phải mở, đọc đúng schema/version và không mất SMART history qua failover. Tác động persisted module state/availability; confidence `high`. Custom MGR module dùng API schema cũ là applicability riêng cần inventory.

### MGRMETRIC-001 — Perf counter mặc định tách khỏi MGR Prometheus sang ceph-exporter

**Evidence.** `MgrClient.cc` không gửi labeled counter qua manager report. `prometheus/module.py` thêm `exclude_perf_counters=true` mặc định và chỉ gọi `get_perf_counters()` khi tắt option. `DaemonMetricCollector` chuyển từ `perf dump/schema` sang labeled `counter dump/schema`, đổi labels, RGW instance identity, long-running-average type và metric-name normalization. Dashboard, REST, Influx, Telegraf dùng API `get_unlabeled_perf_counters()`.

**Before/after.** Quincy Prometheus MGR thường xuất perf counters tập trung; Reef mặc định kỳ vọng ceph-exporter trên host thu counter trực tiếp. Trong mixed phase, nếu exporter/service discovery/scrape chưa sẵn sàng mà MGR target đã áp default, series có thể mất, đổi label/name hoặc tạm duplicate. Đây là thay đổi stop/go quan trọng, không phải bằng chứng performance improvement. Confidence `high`; áp dụng khi pipeline dùng perf counters/recording rules.

### MGRMON-001 — Alert, dashboard, TLS và SNMP contract đổi cùng telemetry split

**Evidence.** Ceph mixin source và 13 generated Grafana dashboard đổi queries/panels; Prometheus rules sửa `CephPoolGrowthWarning` match theo `instance`, thêm bond/hardware/RBD-mirror và target-only NVMe-oF alerts. Prometheus MGR có secure endpoint tùy chọn; Dashboard proxy lấy credential/CA từ cephadm. `CEPH-MIB.txt` thêm OID trong khi legacy `CEPH-PROMETHEUS-ALERT-MIB.txt` bị xóa.

**Before/after.** Khi monitoring assets được redeploy, firing set, labels, Grafana signal và SNMP decoding có thể khác; secure stack còn đổi HTTP→HTTPS/auth trust path. NVMe-oF-only rules không áp dụng nếu chưa opt-in, nhưng các rule/dashboards hiện hữu vẫn thay đổi. Tác động acceptance/observability; confidence `high`. Cross-reference service discovery/image/template tại [owner 08](./08-cephadm-orchestrator.md).

### MGRAUTO-001 — Balancer window và PG autoscaler behavior đổi trong maintenance

**Evidence.** Balancer đổi `end_time 2400→2359`, weekday range `0..7→0..6`, default end weekday `7→0`, và coi begin=end là cho phép cả ngày. PG autoscaler không adjust khi cluster có `norecover`, đồng thời đổi pool/root lookup và progress update.

**Before/after.** Sau active MGR target restart, module đang enabled có thể tự chạy ở window khác; `norecover` giờ đồng thời pause autoscale PG. Điều này đổi background data movement và thời gian stabilization dù daemon data plane chưa full-version. Tác động capacity/performance/maintenance duration; confidence `high`, chỉ áp dụng khi module/flags tương ứng được dùng.

### MGROCH-001 — Orchestrator CLI/interface mở rộng maintenance actions

**Evidence.** `_interface.py` đổi signatures/fields dùng chung giữa cephadm, Rook và Dashboard. `orchestrator/module.py` thêm `keep_conf_keyring`/`zap_osd_devices` cho host drain, `rm_crush_entry` cho host removal, hardware actions, secure-monitoring credentials, input validation và upgrade/service-discovery commands.

**Before/after.** Existing command mặc định phần lớn giữ hướng cũ, nhưng runbook/automation dùng positional args, `-i`, host drain/remove hoặc JSON fields có thể parse/action khác. `zap_osd_devices` là explicit destructive opt-in, không được phép chạy từ báo cáo này. Tác động maintenance control/API compatibility; confidence `high`; implementation cephadm tương ứng ở owner 08.

### MGRROOK-001 — Rook backend đổi namespace, storage class, inventory và reconciliation

**Evidence.** `rook/module.py` và `rook_cluster.py` rework Kubernetes API/backend, operator namespace, multiple configured storage classes, device fetcher, placement và namespaced service removal; một số direct OSD add/remove paths bị loại khỏi backend này.

**Before/after.** Nếu cluster do Rook quản lý, active MGR Reef có thể discover device/host hoặc patch CR khác Quincy, nhất là custom namespace/storageClassDeviceSets. Không áp dụng cho cephadm-only cluster. Tác động orchestration/provisioning; confidence `high` cho code, applicability `UNKNOWN`. Phải diff Kubernetes/CR plan read-only trước mọi reconcile.

### MGRRBD-001 — RBD schedule/perf state không còn dùng class-level singleton

**Evidence.** Mirror snapshot, trash purge và perf handlers chuyển lock, condition, query/cache state từ class scope sang từng module instance; asynchronous callback coi `None` là failure thay vì chỉ dựa return code.

**Before/after.** Module reload/failover trong cùng process không còn dùng chung stale scheduler/cache state theo class; pending snapshot/trash/perf query lifecycle có thể khác. Chỉ áp dụng khi có RBD mirror snapshot schedule, trash purge schedule hoặc RBD perf consumers. Tác động scheduled work/observability; confidence `high`.

### MGRDEP-001 — Required Python dependency và optional Kubernetes module import đổi

**Evidence.** `requirements-required.txt` thêm `bcrypt`; `mgr_util.py` import module này ở top level để cung cấp password hashing. `k8sevents` hỗ trợ model import mới/cũ của Kubernetes client.

**Before/after.** Target artifact thiếu `bcrypt` có thể fail import chung trước khi MGR Python modules active. Với `k8sevents`, client package/model version quyết định module load và event delivery. Tác động delivery/module availability; confidence `high`, Kubernetes path conditional. Phải kiểm trên RPM/DEB/container thực, không chỉ virtualenv phát triển.

### MGRCLI-001 — Một số output/retention contract của MGR automation đổi

**Evidence.** `object_format.py` thêm status string vào command response (được NFS response dùng); status module đổi standby-replay rank thành chuỗi dạng `0-s` và thêm OSD JSON. RESTful module giới hạn 500 request, có thể trim request hoàn tất hoặc request oldest chưa hoàn tất.

**Before/after.** Parser kỳ vọng rank số, stderr rỗng hay lịch sử REST request vô hạn có thể cho kết quả khác sau active MGR upgrade. Không áp dụng nếu không dùng các command/API đó trong gate automation. Tác động validation/automation compatibility; confidence `high`, applicability `UNKNOWN`.

### DASHUP-001 — Dashboard thêm control path start/pause/resume/stop upgrade

**Evidence.** Backend `ClusterUpgrade` và orchestrator bridge expose list/status/start/pause/resume/stop; Angular route/service/components thêm chọn version/image, progress và controls. UI yêu cầu cephadm backend, config permission và tối thiểu hai MGR theo health response.

**Before/after.** Pure Quincy endpoint không có UI này; nó chỉ xuất hiện sau khi một MGR target active, nên không thể thay thế pre-upgrade runbook. Frontend còn lọc registry versions theo cùng first version component, vì vậy hop `17→18` có thể không hiện trong normal list và chỉ còn custom-image path. UI start chỉ gửi version/image, không expose đầy đủ daemon/service/host/limit selectors của backend. Tác động control/rollback thao tác; confidence `high`. Không trộn CLI và Dashboard làm hai controller song song trong rehearsal.

### DASHOBS-001 — Dashboard stop/go signal và secure monitoring access đổi

**Evidence.** Health view đổi threshold/chart handling; Prometheus service đổi polling window; alert service tính count trên current input rồi reorder; Grafana coi HTTP 401 là dashboard tồn tại và đổi Explore URL. Backend Prometheus proxy thêm basic auth/CA cho secure monitoring.

**Before/after.** Operator dùng Dashboard có thể thấy capacity color, alert count/order, time-series window hoặc embedded Grafana availability khác sau MGR target restart. Đây là presentation/decision risk conditional, không chứng minh cluster health đổi. Tác động observability; confidence `high`, chỉ áp dụng nếu Dashboard là stop/go surface.

**Kiểm chứng và phần chưa biết:** chưa có endpoint monitoring/CA/auth, Dashboard assets, browser result hay SLO threshold của estate. Lab cần raw CLI/Prometheus đối chiếu alert count/order, polling window và Grafana 401/TLS bằng account thử; kiểm metric/label không coi màu UI là cluster health. Hunk HealthComponent target gán cả nearfullRatio và fullRatio từ nearfull_ratio, nên nhánh yellow sau red có cùng predicate và không tới khi ratio hợp lệ; base đã có thứ tự nearfull trước full, vì vậy không suy đây là regression mới trên mọi cấu hình. Thử dưới/giữa/trên hai threshold và ratio âm; dừng dùng UI làm stop/go nếu color/count không reconcile. Restore presentation assets/auth riêng; hạ MGR phải qua persisted-state gate.

## Operational closure addenda

#### MGRCORE-001 — Closure

Mixed-version phải failover active/standby MGR cũ↔mới và kiểm connection identity/state ownership; full-Reef lặp reload/restart. Rollback bằng promote standby cũ only before target state migration and after quiescing module work. Validation cần lock/deadlock trace, daemon state and service-map consistency.

#### MGRMETRIC-001 — Closure

Exporter split tự động có hiệu lực theo effective config/restart; enabling `exclude_perf_counters` là explicit. Rollback bằng dual scrape, restore MGR metric config and restart canary; series history is not rewritten. Validate coverage, labels/cardinality, duplicate/missing series and alert replay.

#### MGRMON-001 — Closure

Mixed/full must validate Prometheus/Grafana/Alertmanager/SNMP endpoints per active MGR version. Rollback is restore cert/auth/rules/images and promote known-good MGR; alerts already missed cannot be recovered, so keep parallel source-of-truth. Validation includes CA/SAN/basic-auth, rule queries and delivery IDs.

#### MGRAUTO-001 — Closure

Rollback automation means pause module, restore saved config/policy and reconcile PG/data movement; PG changes already committed are not undone by disabling. Validation mixed/full must test window boundaries, `norecover`, active failover and no unexpected PG-count mutation.

#### MGROCH-001 — Closure

Applicability depends orchestrator backend and commands actually used. Mixed/full must replay read-only CLI/API on old/new active MGR; mutations need isolated MOP. Rollback is command-specific state/spec backup, not generic inverse. Chưa có As-Is backend/parser inventory.

#### MGRROOK-001 — Closure

Rook reconciliation tự động activates when backend/module runs; CR mutations remain controller-driven. Mixed/full canary requires namespace/CR/storage-class snapshot and plan diff. Rollback through restored CR/spec and paused reconcile, not blind deletion. Validate inventory and no unintended device/CR changes.

#### MGRRBD-001 — Closure

Schedule/perf state reloads automatically at module start/failover. Mixed/full must create pending schedule/mirror/perf work then rotate active MGR. Rollback by restore module config/state backup and promote old standby before target-only state write. Applicability and duplicate/skip behavior remain `UNKNOWN`; validate ledgers.

#### MGRDEP-001 — Closure

Dependency import occurs automatically at target module load; install/enable optional Kubernetes module is explicit. Mixed/full should compare module availability on every MGR host. Rollback by restore pinned package/venv and promote old MGR. Validate imports, versions, disabled-module error and package digest.

#### MGRCLI-001 — Closure

Mixed/full must contract-test same commands/API on old/new active MGR. Rollback is pin old CLI/parser or promote known-good MGR; mutating commands require separate state manifest. Keep stdout/stderr/JSON/retention golden artifacts.

#### DASHUP-001 — Closure

Do not use Dashboard controller in mixed control-plane alongside CLI; full-Reef UI testing follows backend exact-hop proof. Rollback control is pause/stop then observe backend status and continue with one controller, not assume UI stop downgrades daemons. Chưa có 17→18 list/filter/custom-image result; validate permissions, two-MGR gate and command ledger.

#### DASHOBS-001 — Closure

Rollback presentation by pinning Dashboard assets/rules/auth config or promoting old MGR; lost telemetry/alerts require source reconciliation. Mixed/full compare UI against raw CLI/Prometheus and keep secure endpoint tests before using Dashboard as GO/STOP surface.

## Trivial changes

592 hàng `trivial` gồm 524 Dashboard UI/backend/generated/type/i18n/test/support rows ngoài control path nâng cấp và stop/go telemetry đã tách; 13 QA rows chưa chạy; 10 docs rows; 5 mixin build/lint/test/README rows; và 40 MGR/module/source support rows là normal target feature, type/refactor/output hoặc optional convenience path không có causal path cho hop này. Test/docs vẫn được dùng làm context nhưng không phải acceptance result. Lý do từng hàng nằm trong CSV.

## Validation đề xuất

1. **As-Is MGR:** lưu `mgr dump`, active/standby, enabled/always-on modules, module options, service URIs, `.mgr` pool health và custom modules; hash exact target package/image và Python dependency set.
2. **MGR failover/DB:** trên lab clone, inject transient `.mgr` unavailability, failover active MGR, reload DeviceHealth; yêu cầu DB reopen trong giới hạn, schema/history giữ nguyên, không deadlock config callback và không blocklist client address mới.
3. **Metric continuity:** trước target MGR, inventory expected series/labels/rules. Trong mixed phase theo dõi song song MGR `:9283` và ceph-exporter `:9926`; fail nếu required series mất/duplicate hoặc label join hỏng. Chỉ bật `exclude_perf_counters=true` khi exporter coverage đủ.
4. **Monitoring acceptance:** validate Prometheus rules, all scrape targets, recording-rule queries, Grafana panels, Alertmanager delivery và SNMP trap/OID trên asset target. Secure mode phải kiểm CA/SAN/basic-auth và MGR failover; mất telemetry là stop condition.
5. **Automation isolation:** disable hoặc pin balancer/autoscaler policy theo MOP; thử begin=end, weekday boundary và `norecover`; ghi PG count/data movement trước-sau active MGR failover.
6. **Orchestrator CLI:** replay read-only parser/API contract cho host drain/remove/apply/upgrade; xác minh `-i`, JSON, positional args. Không test zap trên production; destructive case chỉ dùng disposable lab device.
7. **Rook conditional:** nếu dùng Rook, snapshot CRs/namespaces/storage classes/device inventory; compare target plan and ensure no unexpected CR/device mutation before enabling reconcile.
8. **RBD conditional:** tạo pending mirror snapshot/trash schedule/perf query, reload/failover MGR và yêu cầu không duplicate, skip hay purge ngoài schedule.
9. **Dashboard control:** từ pure Quincy chứng minh UI chưa tồn tại; sau target MGR active, kiểm list/filter/custom image, permission, two-MGR gate, start/pause/resume/stop/status. Chỉ một controller được phép điều khiển một rehearsal.
10. **Dashboard/CLI signals:** contract-test status JSON/stderr/REST retention và compare Dashboard capacity, alerts, Prometheus/Grafana data với raw CLI/Prometheus source of truth.

## Kết luận owner

Owner 07 đã khép binary gate. Gate lớn nhất trước rollout là chứng minh telemetry handoff MGR→ceph-exporter không tạo blind spot; sau đó là MGR SQLite/failover và background automation. Dashboard upgrade là control path mới xuất hiện giữa hop, không phải bằng chứng rằng hop 17→18 có thể được khởi động/an toàn chỉ bằng UI. Chưa có lab/As-Is nên chưa có GO/NO-GO production.

