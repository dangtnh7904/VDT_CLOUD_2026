# 08 — cephadm, orchestrator và daemon lifecycle: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./08-cephadm-orchestrator.csv) có 189 hàng, là subset đúng thứ tự của [master inventory](./00-file-inventory.csv): `affect = 33`, `trivial = 156`, chưa phân loại = 0.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor, nên không dùng `commit_count=1` hay commit-range để suy lịch sử release; kết luận dựa trên hunk, endpoint caller, template và test context.

Chưa có As-Is về cephadm options, persisted Store/spec, image digest/mirror, agent, SSH certificate, host labels, placement, MDS topology, service ingress/NFS/iSCSI/RGW hay monitoring. Chưa chạy repository test hoặc rehearsal. Báo cáo này không cấp quyền chạy upgrade, drain, fail filesystem, redeploy hay thay spec trên production.

## Finding ảnh hưởng upgrade

### ADMUPGRADE-001 — Upgrade sequencing, daemon scope và MDS availability thay đổi

**Evidence.** `upgrade.py` và `utils.py` đổi phân loại/order daemon, tách các loại dùng non-Ceph image, thêm `ceph-exporter`, và thêm tùy chọn `fail_fs`. Khi tùy chọn này bật, target có thể `fs fail` filesystem nhiều active MDS, bỏ qua `ok-to-stop`, nâng MDS rồi đặt filesystem joinable lại; khi tắt, target vẫn giảm `max_mds` theo đường cũ. Điều kiện tối thiểu hai MGR đang chạy vẫn được kiểm.

**Before/after.** Quincy không có nhánh `fail_fs`; Reef có thêm một đường nâng MDS chủ động gây gián đoạn filesystem. Thay đổi scope/order cũng quyết định daemon nào được chọn và image nào được so trong mixed phase. Chỉ áp dụng nhánh availability khi option bật và cluster có CephFS/MDS; daemon mới không tự được deploy chỉ vì upgrade. Risk cao nếu bật `fail_fs`, trung bình với selection/order; confidence `high` cho endpoint behavior, applicability `UNKNOWN`.

### ADMIMAGE-001 — Default registry và image identity đổi

**Evidence.** `cephadm.py`, `module.py`, `upgrade.py` và monitoring service đổi default registry chuẩn hóa image không qualified từ `docker.io` sang `quay.io`, đổi default Ceph image v17→v18 và nâng nhiều image phụ như Loki/Promtail/keepalived. Upgrade logic cũng xử lý tag/repository digest và non-Ceph images khác trước.

**Before/after.** Cùng một short image name có thể resolve sang registry/digest khác; service phụ hiện hữu có thể được redeploy bằng image target mới khi reconcile. Môi trường air-gapped, mirror, allowlist hoặc pin tag thay vì digest có thể pull fail hay nhận bytes khác mong đợi. Tác động delivery/rollback; confidence `high`. Gate phải dựa trên fully-qualified repo digest đã pre-pull, không dựa vào tag hoặc default registry.

### ADMMIG-001 — Persisted orchestrator state nâng migration 5→6 và rewrite RGW spec

**Evidence.** `migrations.py` tăng `LAST_MIGRATION` từ 5 lên 6; `inventory.py` queue RGW specs khi load Store; migration tách chuỗi legacy như `beast endpoint=... tcp_nodelay=1` thành `rgw_frontend_type` và `rgw_frontend_extra_args`. `cephadmservice.py` target render type/extra args theo schema mới.

**Before/after.** MGR target đầu tiên có thể ghi lại persisted service spec trước khi toàn cluster full-version. Spec sai định dạng có thể không migrate sạch và làm service unmanaged/health warning. Đây là state mutation có ranh giới rollback: binary Quincy không được giả định hiểu state đã rewrite giống trước. Áp dụng khi migration level <6 và có RGW spec legacy; confidence `high`. Phải export Store/spec và kiểm diff trước khi cho reconcile tiếp tục.

### ADMEXEC-001 — cephadm artifact và deploy/reconfigure contract đổi

**Evidence.** `build.py`/`build.sh` thêm zipapp build; `module.py` đọc/hash cephadm artifact dạng bytes; file được rename thành `cephadm.py`. Entry point target dùng atomic temp-write + fsync + rename cho nhiều config, phân biệt `DEFAULT`/`REDEPLOY`/`RECONFIG`, cho redeploy bỏ qua một số port checks, và đổi quan hệ systemd container từ `Requires` sang `Wants`.

**Before/after.** Artifact bytes/hash và command semantics mà MGR phân phối khác Quincy; reconfig/redeploy có precondition và failure boundary khác, còn atomic replace có thể đổi inode/observer behavior. Đây là thay đổi mọi cephadm-managed cluster, không phải wire-protocol proof. Tác động daemon continuity/delivery; confidence `high`. Cần smoke đúng artifact đóng gói và thử idempotent deploy/reconfig/redeploy trên canary.

### ADMHOST-001 — Host drain, reachability và offline decision đổi

**Evidence.** `inventory.py`/`utils.py` tách `_no_schedule` (drain daemon) và `_no_conf_keyring` (không phân phối config/keyring), duy trì eligible/draining set riêng. `serve.py`, `agent.py` và `ssh.py` đổi refresh, timeout/error classification và host-offline handling.

**Before/after.** Label cũ/thiếu có thể để config/keyring tiếp tục hiện diện dù daemon đã drain, hoặc loại host khỏi placement theo tập khác. SSH/agent timeout có thể đánh dấu offline theo failure path mới, làm reconcile bị hoãn hay chuyển placement. Áp dụng cho host có special label, lỗi kết nối hoặc agent; confidence `high`, blast radius phụ thuộc placement. Inventory label/status và files còn lại trên host phải được đối chiếu trước/sau drain canary.

### ADMAGENT-001 — Agent transport chuyển sang HTTPS/certificate path mới

**Evidence.** `agent.py`, `exchange.py`, `http_server.py`, `ssl_cert_utils.py`, `module.py` và `cephadmservice.py` thay message exchange, endpoint HTTPS, certificate generation và metadata refresh. HTTP server mới đồng thời phục vụ service discovery.

**Before/after.** Khi `use_agent` bật, Reef dùng endpoint/certificate lifecycle khác và phụ thuộc bind address, port, CA/cert cùng reachability hai chiều; lỗi làm host metadata stale hoặc reconcile mất tín hiệu. Khi agent tắt, phần finding này không áp dụng. Tác động control-plane availability/security; confidence `high`. Phải kiểm SAN/CA, expiry, port, reconnect sau MGR failover và behavior khi cert/endpoint hỏng.

### ADMSSH-001 — Signed SSH certificate, transfer và timeout handling đổi

**Evidence.** `ssh.py` và `cephadm.py` thêm private-key + SSH certificate bootstrap, chuyển file transfer sang SFTP `put`, phân biệt channel/process/generic errors và xử lý concurrent timeout. Một số lỗi dẫn tới host offline.

**Before/after.** Quincy chủ yếu dựa key pair; Reef có thể dùng CA-signed credential và phân loại failure khác. Host policy chỉ cho SCP, cert principal/SAN sai, hoặc timeout biên có thể làm deployment/refresh fail khác trước. Chỉ áp dụng signed-cert path khi cấu hình; SFTP/error handling áp dụng rộng hơn. Tác động host access; confidence `high`.

### ADMSCHED-001 — `label` và `host_pattern` trở thành phép giao

**Evidence.** `schedule.py` truyền full spec vào filter và khi placement có cả label lẫn host pattern, target yêu cầu host thỏa cả hai thay vì để một selector che selector kia; `serve.py` dùng kết quả này trong reconcile.

**Before/after.** Một spec hiện hữu chứa đồng thời hai selector có thể nhận eligible host set nhỏ hơn, dẫn tới add/remove/move daemon sau khi MGR target active. Không áp dụng cho spec chỉ có một selector hoặc explicit hosts. Tác động placement/availability; confidence `high`. Phải tính expected host set offline và pause nếu target diff ngoài allowlist.

### ADMOSD-001 — Managed OSD reconcile đổi DriveGroup và ceph-volume path

**Evidence.** `services/osd.py`, `serve.py`, `inventory.py` và `cephadm.py` đổi cách truyền DriveGroup, lọc host/drain và gọi ceph-volume khi deploy/reconcile managed OSD. Đây là consumer orchestration của các thay đổi inventory/activation ở [owner 09](./09-ceph-volume-activation.md).

**Before/after.** Cùng DriveGroup/spec và inventory có thể tạo target list hoặc command ceph-volume khác; nguy cơ cao nhất là spec rộng tự nhận device sau refresh. Binary upgrade không tự cho phép zap/prepare, nhưng active reconcile có thể thực thi spec đã lưu. Tác động provisioning/data safety; confidence `high`, applicability phụ thuộc managed OSD spec. Cần freeze/dry-run plan và diff device identity trước khi unpause reconcile.

### ADMSVC-001 — Reconcile thay config của RGW, ingress, NFS và iSCSI hiện hữu

**Evidence.** `cephadmservice.py`, `services/ingress.py`, `iscsi.py`, `nfs.py` và template tương ứng đổi RGW frontend args; HAProxy health check/bind/TCP defaults; keepalived interface/VIP/script security; Ganesha NLM/idmap/ingress settings; và iSCSI tcmu-runner supervision/container identity.

**Before/after.** Existing specs có thể render config khác và restart/redeploy với dependency mới (`idmap.conf` cho NFS là một ví dụ). Mỗi service chỉ áp dụng khi tồn tại; Jaeger/NVMe-oF/node-proxy target-only không bị promote thành rollout risk nếu chưa opt-in. Tác động service continuity/config compatibility; confidence `high`. Phải lưu rendered config, endpoint/VIP/session state và thử failover/reconnect từng service class.

### ADMMON-001 — Monitoring chuyển discovery, security, image và storage schema

**Evidence.** `services/monitoring.py`, `service_discovery.py`, `http_server.py`, `ssl_cert_utils.py` và template Prometheus/Alertmanager/Grafana/Loki/node-exporter đổi image, static target sang HTTP service discovery, thêm TLS/basic auth và thay config. Loki template thêm schema TSDB v13 theo mốc ngày `2024-05-03`.

**Before/after.** Existing monitoring stack có thể restart bằng image/config mới; Prometheus phụ thuộc cephadm discovery endpoint, secure stack phụ thuộc cert/credentials, và Loki có storage schema theo thời gian. Mất telemetry trong maintenance làm yếu stop/go dù data plane còn chạy. Áp dụng theo service đang deploy và secure mode; confidence `high`. Gate phải kiểm scrape targets, alerts, dashboards, logs lịch sử/mới và rollback image/config cùng credentials.

**Closure.** Discovery/TLS/schema tự động kích hoạt khi target monitoring services reconcile/restart. Mixed-version phải giữ old/new scrape discovery và log readers song song; full-Reef mới chuyển toàn bộ rules/storage writers. Rollback là restore pinned images/config/credentials/schema-compatible reader; Loki writes sau schema date cần clone/restore rehearsal. Chưa có service/image/digest inventory; validation cần target list, alerts, dashboards and historical/new log queries.

## Operational closure addenda

#### ADMUPGRADE-001 — Closure

State machine tự động advances only after operator starts upgrade; pause/resume/stop are explicit and stop is not binary rollback. Failback requires pinned old digest, allowed daemon state and service-specific persisted-state gates. Validate selectors/limits, MGR failover, both CephFS paths and cohort health before next step.

#### ADMIMAGE-001 — Closure

Image resolution/pull occurs automatically during deploy/redeploy; registry/mirror change is config. Mixed/full must use resolved digests, never floating tags. Chưa có exact image/digest or mirror proof; validate pre-pull, signature/architecture, start and rollback digest availability.

#### ADMMIG-001 — Closure

Migration có tác động tới persisted Store/spec and rendered RGW args. First target MGR load is the boundary; rollback only via cloned Store/spec restore or proven old-reader. Chưa có As-Is migration level/spec snapshot. Validate exact diff, malformed case, idempotent second load and rendered output.

#### ADMEXEC-001 — Closure

Applicability covers hosts using cephadm artifact/deploy/reconfigure. Mixed/full must run exact artifact across host OS/arch and canary one daemon. Rollback by drain, restore pinned artifact/image/unit and verify service state. Validation keeps argv, rendered unit/config, exit/status and repeated reconfigure result.

#### ADMHOST-001 — Closure

Impact is placement/service availability when reachability or drain classification changes. Mixed/full must test reachable/unreachable host and labels before reconcile. Rollback via restore host labels/status/spec and redeploy only after plan diff; removed keyring/config residue needs explicit reconciliation. Validate eligible sets and daemon moves.

#### ADMAGENT-001 — Closure

Mixed/full must test old/new agents against active target MGR, then full certificate path. Rollback by disable/drain agent channel and restore known-good transport/certs; issued/revoked cert state needs inventory. Chưa có agent/certificate applicability or timeout result; validate TLS identity, metadata convergence and MGR failover.

#### ADMSSH-001 — Closure

Signed-cert/SFTP/timeout paths activate automatically when configured transfer/connect runs. Mixed/full must test key and cert modes per host. Rollback by restore pinned key/cert/SSH config and retry idempotently; remote partial copy needs checksum cleanup. Chưa có host policy inventory; validate bad cert, timeout and transfer digest.

#### ADMSCHED-001 — Closure

Intersection semantics can automatically alter eligibility at next reconcile. Rollback by pause reconcile, restore exported spec/labels and confirm plan before resume; moved daemons are not undone merely by editing selector. Chưa có actual label/host_pattern set. Validate expected/actual hosts and zero unintended placements.

#### ADMOSD-001 — Closure

DriveGroup planning/reconcile activates automatically when managed spec runs; prepare/zap are destructive explicit actions. Mixed/full must plan against disposable inventory only. Rollback after prepare/zap requires device/data recovery plan, not inverse command. Validate allowlist, ceph-volume argv, device IDs and no out-of-scope mutation.

#### ADMSVC-001 — Closure

Rendered config may change at reconcile/redeploy; rollback is restore exported spec/config/image/credentials and canary redeploy with client continuity checks. Validate RGW/NFS/ingress/iSCSI separately, including VIP, session, mount and endpoint state. Do not bulk reconcile before per-service PASS.

## Trivial changes

156 hàng `trivial` gồm 16 trang docs, 95 hàng QA/workunit/suite chưa được chạy, unit tests/fixtures, cephadm dev-box, sample/example, tox/Vagrant/README metadata, helper cleanup không đổi contract, và implementation thuần target-only của Jaeger, node-proxy, NVMe-oF. Các hàng opt-in này không được coi là rủi ro rollout của service kế thừa; việc đăng ký chúng nằm trong file production đã được review riêng. Lý do từng hàng có trong CSV.

## Validation đề xuất

1. **Snapshot control plane:** export `ceph orch ls --export`, host/label/status, daemon inventory, MGR module options, migration level và relevant config-key/Store; hash và giữ bản chỉ đọc trước MGR target đầu tiên.
2. **Artifact/image gate:** build/import/smoke cephadm artifact thật, resolve mọi Ceph và service image thành repo digest, pre-pull qua registry/mirror production-equivalent và chứng minh rollback digest vẫn khả dụng.
3. **Upgrade state machine:** lab pause/resume/limit/selectors, MGR failover, old/new daemon cohorts và non-Ceph image types. Chạy CephFS hai nhánh `fail_fs=false/true`; nhánh true phải đo rõ planned outage và joinable recovery.
4. **Migration 5→6:** clone Store/spec có RGW frontend legacy và malformed case; khởi động MGR target, lưu exact spec diff, rendered args, idempotent second load và thử rollback trên clone.
5. **Agent/SSH/host:** ma trận agent off/on, key pair/signed cert, SFTP policy, timeout, bad cert, MGR failover; kiểm host không bị offline sai và metadata hội tụ trong SLA.
6. **Drain/placement:** test `_no_schedule`, `_no_conf_keyring`, label + host pattern và unreachable host; so expected/actual eligible set, daemon moves và config/keyring residue.
7. **OSD safety:** với inventory disposable/clone, diff DriveGroup plan và ceph-volume target; fail nếu có device ngoài allowlist. Không đưa zap/prepare production vào binary rollout mặc định.
8. **Service continuity:** canary RGW/NFS/ingress/iSCSI, lưu config trước/sau, kiểm VIP/health check/NFS mount/iSCSI session và client reconnect qua restart/failover.
9. **Observability:** kiểm Prometheus discovery, TLS/auth, all targets, alert delivery, Grafana datasource/dashboard và Loki read/write qua schema date; mất signal stop/go phải dừng rollout.

## Kết luận owner

Owner 08 đã khép binary gate. Ba gate có blast radius lớn nhất là: snapshot và rehearsal migration Store/spec trước MGR target đầu tiên; pin artifact/image bằng digest; và chứng minh reconcile không tạo placement/device/service diff ngoài dự kiến. `fail_fs`, OSD preparation, host drain và service redeploy là hành động vận hành riêng, không được suy là đã được phê duyệt từ source review này.

