# Storage Lab Console — Kế hoạch hợp nhất và đóng gói container image

**Phiên bản kế hoạch:** 3.0

**Cập nhật:** 09/10/2026

**Phạm vi:** kiến trúc, UI, OSD Info Collector, PA1/PA2, QoS/Lab và phát hành container image portable; không phải bằng chứng đã build image hoặc chạy thành công trên cluster

**Code hiện có:** [`rgw-console`](./rgw-console/)

**Nguồn kế hoạch duy nhất:** tài liệu này hợp nhất `plan(5).md` v2.0 và `Storage_Lab_Console_OSD_Validation_and_Benchmark.md` ngày 08/10/2026. File đặc tả cũ chỉ giữ liên kết chuyển tiếp, không còn backlog/DoD riêng.

**Đầu ra mục tiêu:** một OCI image ứng dụng Storage Lab Console, chạy ở lab và hệ thống khác bằng cấu hình runtime; PostgreSQL, secrets và dữ liệu bền vững nằm ngoài image.

**Đọc nhanh:** [Hiện trạng](#3-hiện-trạng-code-và-khoảng-trống) · [Inventory/chọn OSD](#7-inventory-capability-và-batch-planning) · [UI](#18-frontend) · [Lộ trình](#21-kế-hoạch-triển-khai-theo-pha) · [Test/DoD](#22-test-matrix-bắt-buộc) · [Hợp đồng image và triển khai](#28-container-image-và-triển-khai-portable)

Quyết định hợp nhất: dùng API mới dưới `/api/v1`; QoS dùng tên `qos-runs` thay tên dự kiến `benchmark-runs`; giữ API legacy đang có. Phạm vi Ceph đầu tiên là Pacific replicated pool; các release/topology khác chỉ được công bố hỗ trợ sau capability và acceptance test tương ứng. “Portable” không có nghĩa mọi hệ thống/Ceph release tự động tương thích.

---

## 1. Mục tiêu của lần sửa kế hoạch

Kế hoạch mới chuyển trọng tâm từ một console RGW/RBD gắn với một lab sang một **Storage Lab Console có thể mang sang nhiều cụm Ceph lab bằng cách thay cấu hình**, đồng thời bổ sung workflow nâng cấp OSD PA1/PA2, QoS Observer, Lab Test, evidence và rollback.

Các mục tiêu bắt buộc:

1. Không xóa chức năng RGW/RBD hiện có. Chức năng cũ được giữ dưới nhóm `legacy`, có regression test và API tương thích.
2. Production upgrade workflow không phụ thuộc vào Legacy Tools, QoS hoặc Lab Test. Một session chỉ bật production workflow vẫn hợp lệ.
3. Thiết kế theo nguyên tắc **liên kết lỏng, kết tụ cao**: domain core không gọi trực tiếp SSH, Ceph CLI, S3, Prometheus, Warp hoặc fio.
4. Mọi giá trị phụ thuộc lab được đưa ra khỏi source code. Việc đổi cluster thực hiện qua `.env`/cluster profile và restart, không sửa code.
5. Mọi mutation fail closed khi sai FSID, thiếu capability, evidence cũ, state không khớp hoặc resource lease không hợp lệ.
6. Kết quả production, QoS và Lab được đánh giá độc lập; không dùng PASS của helper workload để thay gate mapping/scrub của production.
7. PA1 và PA2 là hai profile ngang hàng. Console không chọn mặc định, không tự chấm điểm và không gắn nhãn phương án thắng.
8. Build một application OCI image có version/digest; cùng image chạy nhiều container theo role. Máy đích không cần source checkout hoặc build lại. Gói phát hành hỗ trợ registry và cài offline theo mục 28.
9. Tách readiness của gói triển khai khỏi readiness của tính năng: phát hành bản read-only/dry-run không được coi là PA1/PA2 live đã hoàn thành.

### 1.1. Quyết định scope để tránh over-design

MVP portable dùng mô hình:

- **Một deployment kết nối một cluster tại một thời điểm.**
- Chuyển sang lab khác bằng `LAB_PROFILE`/`.env` rồi restart service.
- Chưa làm cluster selector hoặc điều khiển đồng thời nhiều cluster trong một UI.
- Mọi row, lease, idempotency scope, event và evidence vẫn chứa `cluster_id` và `fsid` để không khóa đường mở rộng multi-cluster.
- Run luôn giữ config snapshot. Đổi `.env` không được làm thay đổi ý nghĩa của run cũ hoặc cho phép resume trên cluster khác.

---

## 2. Nguyên tắc kiến trúc bắt buộc

### 2.1. Liên kết lỏng, kết tụ cao

- Mỗi module sở hữu domain model, use case, repository port và API của chính nó.
- Domain không import FastAPI, psycopg, boto3, SSH client, HTTP client hoặc command string.
- Adapter triển khai port; core chỉ biết interface và typed result.
- Module không đọc/ghi trực tiếp bảng của module khác. Giao tiếp qua application service, query contract hoặc domain event.
- Shared code chỉ chứa primitive thật sự dùng chung: ID, clock, transaction, idempotency, lease, event envelope, config snapshot và error contract.
- Không tạo một `utils.py` hoặc `services.py` chung chứa nghiệp vụ của nhiều domain.
- QoS và Lab chỉ subscribe event/evidence của upgrade. Chúng không được tự đổi placement, stop OSD hoặc gửi PASS vào production state machine.
- Legacy RGW/RBD không được ghi trực tiếp state của upgrade run.

### 2.2. Evidence-first và actual-state-first

- UI chỉ yêu cầu action; backend tự đọc actual state và quyết gate.
- UI không gửi `PASS`, actual role, scrub completion hoặc state đích để mở bước.
- Timeout không đồng nghĩa command chưa chạy. Retry phải reconcile actual state trước.
- Request command thành công không đồng nghĩa state đã hội tụ.
- `HEALTH_OK` không thay thế mapping evidence, replica role hoặc deep-scrub completion.
- Evidence thiếu, stale hoặc có gap không được biến thành `0`, `false` hay PASS.

### 2.3. Fail closed cho mutation

Mutation bị chặn khi:

- FSID thực không khớp `CEPH_EXPECTED_FSID`.
- Cluster profile/capability chưa resolve hoặc config snapshot không hợp lệ.
- Plan revision, expected state hoặc resource lease không khớp.
- Inventory, mapping, health, capacity hoặc telemetry bắt buộc đã stale.
- Adapter trả output/schema không được hỗ trợ ở release hiện tại.
- Resource nằm ngoài allowlist của deployment/run.
- Có active run khác sở hữu cùng resource hoặc down-set/budget xung đột.

### 2.4. Không hard-code cluster

Application logic không được chứa IP, hostname, FSID, OSD ID, pool, bucket, image prefix, mount root, target version/image digest hoặc đường dẫn evidence của một lab cụ thể. Giá trị ví dụ chỉ được nằm trong file `.example`, fixture hoặc test.

---

## 3. Hiện trạng code và khoảng trống

Đối chiếu cây source ngày 09/10/2026. “Có code” không đồng nghĩa đã deploy, đã áp migration trên DB đích hoặc đã kiểm chứng live. Các pha dưới đây là lộ trình/exit gate, không phải checklist đã hoàn tất.

### 3.1. Thành phần đã có

| Thành phần | Hiện trạng trong repository |
|---|---|
| Legacy RGW/RBD | FastAPI API, worker, capacity/performance collectors, RBD lifecycle, file/validation và frontend; phải giữ regression contract |
| Config/session | Có cluster profile, feature flags, config snapshot, session và FSID/allowlist checks |
| Common foundation | Evidence/outbox/leases, upgrade dry-run, capability/phase events và plan/run persistence |
| Upgrade domain | Có PA1, PA2 spare-chain/ledger, replica/rollback domain và simulator/tests; chưa phải bộ điều khiển live hoàn chỉnh |
| QoS | Có foundation/model/API/test; không suy ra Warp/fio live provider đã được kiểm chứng đầy đủ |
| OSD Info Collector | Có tool độc lập, adapter/executor read-only, artifact/index, bind vào plan, freshness/readiness/down-set assessment, before/after và config diff |
| Inventory UI | Có danh sách OSD nguồn/đích đã lưu trong plan, chi tiết topology/device/cluster context; giữ khi hợp nhất UI |
| Database | Có file migration `0001`–`0019`; không khẳng định DB lab đã áp tất cả |
| Packaging | Có 3 application Dockerfiles: Python backend, frontend Nginx, Node executor; Compose dùng lại backend image cho workers/migrate |
| Validation | [VALIDATION.md](./rgw-console/VALIDATION.md) ghi evidence và giới hạn PASS/PARTIAL/NOT_RUN; không nâng claim khi sửa kế hoạch |

### 3.2. Khoảng trống kiến trúc và đóng gói

- Còn các file API/UI/service lớn cần tách dần; không rewrite hoặc xóa chức năng legacy.
- Python/Node chưa đồng nhất hoàn toàn token/default/path và validation theo feature; profile upgrade-only không được bắt có credential RGW.
- Packaging chưa có một release image chung, manifest/digest, role entrypoint và bộ cài không cần source/build trên máy đích. Base image/dependency policy cần khóa và kiểm chứng ở release pipeline.
- Compose hiện thiếu persistent evidence volume; artifact nằm trong writable layer không đạt điều kiện release. Phải giữ DB, evidence và executor state qua recreate.
- `/api/health` hiện gắn kiểm tra RGW; cần tách liveness/readiness/dependency health theo profile.
- SSH executor cần host-key verification được cấu hình và test; chưa coi SSH pinning là xong.
- Remote collector dùng path cố định nhưng chưa có gói cài/version-hash attestation hoàn chỉnh; chứa script trong image chưa làm remote host sẵn sàng.
- Cần test auth/TLS, secret redaction, role isolation, migration/backup/restore và offline deployment theo mục 28.

### 3.3. Chức năng còn cần hoàn thiện/kiểm chứng

- Hoàn thiện live adapters/controller PA1/PA2, placement/admission, maintenance/down-set safety, replica deep-scrub và stable-window gates.
- Read-only inventory/down-set assessment không cấp quyền mutation; khi thiếu live safety evidence phải giữ `BLOCKED`.
- Operational replacement rollback, recovery theo current mapping, Warp/fio providers và Lab Test đầy đủ phải có acceptance evidence riêng.
- Hoàn thiện UI stepper, timeline và comparison theo mục 18–20; preserve danh sách OSD đã lưu, không suy vai trò tương lai từ inventory hiện tại.
- Chưa có evidence trong lần sửa tài liệu này cho one-image build, hai hệ thống đích, offline install hoặc live PA1/PA2.

### 3.4. Cách đọc validation hiện tại

- PASS của unit/simulator/contract test chứng minh đúng scope test, không thay live evidence.
- PASS của RBD checksum/remount chỉ chứng minh helper RBD workflow đã chạy trong scope đó, không chứng minh production replica/upgrade/rollback.
- Giữ `PARTIAL`, `NOT_RUN`, `NOT_EXERCISED` cho phần chưa chạy. Cập nhật release matrix bằng kết quả mới khi thực sự thực thi, không dùng ngày sửa plan làm ngày validation.

---

## 4. Phạm vi sản phẩm mục tiêu

### 4.1. Các workspace độc lập

| Workspace | Trách nhiệm | Có thể tắt độc lập |
|---|---|---|
| Upgrade Production | PA1 drain–upgrade–return và PA2 rotating spare | Có, qua `FEATURE_UPGRADE`; mutation mặc định tắt |
| QoS Observer | Warp/fio hoặc provider khác, correlation BEFORE/DURING/AFTER | Có |
| Lab Test | Kiểm PG/object test đã chọn trong lab | Có |
| Rollback | Containment, removal gate, replacement sạch và rebuild | Chỉ bật khi cần |
| Evidence & Comparison | Timeline, artifacts, report và so sánh PA1–PA2 | Report production luôn có |
| Legacy Tools | RGW, RBD, workload, Capacity Guard và dashboard cũ | Có, không ảnh hưởng core |

Một session có thể gắn nhiều production, QoS, Lab hoặc rollback run; mỗi run có state, lease, event sequence, evidence và verdict riêng. Session chỉ làm nhiệm vụ liên kết timeline/report, không gộp các state machine thành một trạng thái chung.

### 4.2. Trong phạm vi bản đầu

- Baseline Ceph Pacific replicated pool; EC trả `UNSUPPORTED` cho gate chưa có phép tính/validation riêng.
- Linux container deployment bằng một OCI image ứng dụng (amd64 trước); hệ thống khác dùng profile/adapter tương thích, không sửa source hoặc bake lại image chỉ để đổi lab.
- Ceph release được nhận diện qua capability probe, không suy hành vi chỉ từ tên release.
- PA1 và PA2 theo invariant của tài liệu controller.
- Một deployment/cluster tại một thời điểm.
- SSH/HTTP adapter tới Linux executor; browser/backend không cần block device Ceph cục bộ.
- PostgreSQL làm state store; evidence payload lớn lưu ngoài DB với checksum và URI.
- Read-only/dry-run hoàn thành trước khi mở mutation.
- Legacy RGW/RBD tiếp tục hoạt động trong allowlist hiện tại.

### 4.3. Ngoài phạm vi bản đầu

- Multi-cluster concurrent control.
- EC production upgrade gate được tuyên bố tương đương replicated pool.
- Tự chọn PA1 hay PA2.
- Tự repair inconsistency, tự hạ `min_size`, force removal hoặc mở rộng allowlist để vượt gate.
- Tự sửa CRUSH policy ngoài placement plan đã được operator duyệt.
- Thay thế Ceph orchestrator; controller chỉ điều phối qua adapter và lưu evidence.
- Dùng terminal legacy làm implementation cho production action.
- Xóa legacy feature hoặc legacy data.

---

## 5. Kiến trúc module mục tiêu

### 5.1. Sơ đồ logic

```text
React workspaces
    │
    ▼
FastAPI API / application layer
    │
    ├── Sessions & Config Snapshot
    ├── Cluster Inventory
    ├── Upgrade Common / Safety Gates
    ├── PA1 Workflow
    ├── PA2 Workflow
    ├── Replica Validation
    ├── Operational Rollback
    ├── QoS Observer                 (optional)
    ├── Lab Validation               (optional)
    ├── Evidence / Report / Compare
    ├── Legacy RGW                   (optional)
    └── Legacy RBD                   (optional)
            │
            ▼ ports
    ┌──────────────────────────────────────────────┐
    │ Ceph CLI/cephadm SSH │ Prometheus │ Warp/fio│
    │ RGW S3/Admin         │ RBD executor│ Storage │
    └──────────────────────────────────────────────┘
            │
            ▼
        Target Ceph lab
```

### 5.2. Bounded modules

| Module | Sở hữu | Không được sở hữu |
|---|---|---|
| `cluster_profiles` | Profile, capability, config snapshot, FSID binding | Run state |
| `sessions` | Session lifecycle và workflow links | Logic PA1/PA2 |
| `cluster_inventory` | OSD/pool/PG/topology/version observations | Mutation |
| `upgrade_common` | Batch, lease, ledger, shared gate result | Strategy-specific transition |
| `upgrade_pa1` | PA1 run/state/return groups | PA2 chain |
| `upgrade_pa2` | Wave/chain/rotation/handoff/end state | PA1 return semantics |
| `replica_validation` | PG role, scrub request/completion, evidence validity | Placement mutation |
| `rollback` | Containment/removal/replacement/rebuild | Feature rollback |
| `qos_observer` | Runner, phase, cohort, metric, comparison segment | Production mutation |
| `lab_validation` | Selected lab PG/object read/write/scrub result | Production PASS |
| `evidence_reporting` | Event timeline, artifact, report, comparison | Command execution |
| `legacy_rgw` | RGW object/workload hiện có | Upgrade state |
| `legacy_rbd` | RBD volume/file/terminal/validation hiện có | Upgrade state |

### 5.3. Ports bắt buộc

Core sử dụng các interface sau; tên cuối có thể đổi nhưng ranh giới không được mất:

```text
ClusterIdentityPort
ClusterInventoryPort
PlacementQueryPort
PlacementMutationPort
UpgradeExecutorPort
MaintenanceGatePort
ScrubEvidencePort
HealthTelemetryPort
CapacitySnapshotPort
BenchmarkRunnerPort
ObjectMappingPort
EvidenceStorePort
ArtifactStorePort
ClockPort
LeaseRepositoryPort
EventPublisherPort
```

Adapter ban đầu:

- `ceph_cli_ssh`: inventory, PG query, mapping, scrub và read-only health.
- `cephadm_ssh`: redeploy/service image action khi capability phù hợp.
- `prometheus`: telemetry/counter read-only.
- `warp`: RGW benchmark.
- `fio`: RBD/file benchmark.
- `rgw_s3`: Legacy RGW và optional QoS asset.
- `rbd_executor`: Legacy RBD và optional fio asset.
- `filesystem_artifact_store`: lab-only evidence store; có thể thay S3-compatible store qua port.

### 5.4. Dependency rule

```text
API -> application use case -> domain -> port
adapter ------------------------------^ implements
```

- Domain test được mà không cần FastAPI, PostgreSQL, SSH hoặc Ceph.
- Adapter normalization biến output theo release thành canonical model.
- Domain và API nghiệp vụ dùng model canonical, không phụ thuộc raw Ceph JSON. Raw evidence chỉ truy cập qua endpoint chuyên biệt có kiểm hash/size/quyền và redaction; UI detail drawer không được bỏ qua các kiểm tra này.
- Unsupported capability trả `UNSUPPORTED`/`BLOCKED`, không đoán default.

### 5.5. Event contract

Mọi event có envelope tối thiểu:

```json
{
  "schema_version": 1,
  "event_id": "<uuid>",
  "event_type": "upgrade.return_group.converged",
  "cluster_id": "<logical-id>",
  "fsid": "<uuid>",
  "session_id": "<uuid>",
  "run_id": "<uuid>",
  "sequence": 42,
  "occurred_at": "<source-time>",
  "observed_at": "<collector-time>",
  "producer": "upgrade_pa1",
  "correlation_id": "<uuid>",
  "payload": {}
}
```

Event ghi qua transactional outbox trong cùng transaction với state change. QoS/report đọc event theo sequence; không dựa vào thời điểm browser nhận SSE.

---

## 6. Cluster profile và cấu hình `.env`

### 6.1. Ba lớp cấu hình

| Lớp | Chứa | Không chứa |
|---|---|---|
| Deployment `.env` | Kết nối DB, cluster identity, transport, endpoint, secret reference, feature flag, allowlist tối đa | OSD X/U/D của một run |
| Versioned policy | Threshold, stable window, parallelism ceiling, freshness, evidence retention, stop policy | Secret |
| Run config | PA1/PA2, OSD cụ thể, target digest, nhóm PG, end-state policy, optional QoS/Lab | Credential hoặc global default ngầm |

Không đẩy toàn bộ run config vào `.env`; nếu làm vậy run không có revision bền vững và đổi file có thể làm sai resume.

### 6.2. Artifact cấu hình phải có ở pha triển khai

- `.env.example`: commit, chỉ placeholder và mô tả biến.
- `.env`: operator điền giá trị, luôn nằm trong `.gitignore`, không commit.
- `config/policies/default.yaml`: default an toàn, version hóa, không có secret.
- `config/profiles/<lab>.yaml.example`: optional non-secret profile mẫu; `.env` chọn bằng `LAB_PROFILE` hoặc `CLUSTER_CONFIG_PATH`.
- Config snapshot đã resolve và redact được lưu trong DB khi tạo session/run.

**Trong bước hiện tại chỉ sửa kế hoạch; chưa tạo hoặc thay `.env`.**

### 6.3. Nhóm biến canonical dự kiến

```dotenv
# Application
APP_ENV=lab
APP_INSTANCE_ID=
LAB_PROFILE=
CLUSTER_CONFIG_PATH=
LOG_LEVEL=INFO

# Feature flags; mutation luôn tắt mặc định
FEATURE_UPGRADE=true
FEATURE_QOS=false
FEATURE_LAB=false
FEATURE_LEGACY_RGW=true
FEATURE_LEGACY_RBD=true
UPGRADE_MUTATIONS_ENABLED=false

# Database
DATABASE_URL=
DATABASE_URL_FILE=

# Cluster identity and transport
CLUSTER_ID=
CEPH_EXPECTED_FSID=
CEPH_CLUSTER_NAME=ceph
CEPH_TRANSPORT=ssh
CEPH_EXECUTOR_URL=
CEPH_EXECUTOR_TOKEN=
CEPH_EXECUTOR_TOKEN_FILE=
CEPH_SSH_HOST=
CEPH_SSH_PORT=22
CEPH_SSH_USER=
CEPH_SSH_PRIVATE_KEY_FILE=
CEPH_SSH_KNOWN_HOSTS_FILE=
CEPH_SSH_HOST_KEY_SHA256=

# Maximum deployment scope
UPGRADE_ALLOWED_OSDS=
UPGRADE_ALLOWED_HOSTS=
UPGRADE_ALLOWED_POOLS=
UPGRADE_ALLOWED_DEVICE_CLASSES=

# Telemetry
TELEMETRY_PROVIDER=prometheus
TELEMETRY_PROMETHEUS_URL=
TELEMETRY_PROMETHEUS_BEARER_TOKEN_FILE=
TELEMETRY_MAX_AGE_SECONDS=
TELEMETRY_CLOCK_SKEW_MAX_SECONDS=

# Optional benchmark adapters
WARP_ENABLED=false
WARP_EXECUTOR_URL=
WARP_BINARY_PATH=
FIO_ENABLED=false
FIO_EXECUTOR_URL=
FIO_BINARY_PATH=

# Optional lab validation scope
LAB_VALIDATION_ENABLED=false
LAB_ALLOWED_POOLS=
LAB_ALLOWED_PG_PREFIXES=
LAB_ALLOWED_OBJECT_PREFIXES=
LAB_ALLOW_WRITE=false

# Evidence
EVIDENCE_STORE=filesystem
EVIDENCE_ROOT=
EVIDENCE_RETENTION_DAYS=
EVIDENCE_MAX_ARTIFACT_BYTES=
```

Các biến legacy `RGW_*`, `RBD_*`, `CAPACITY_*` và `PERFORMANCE_*` tiếp tục được giữ trong `.env.example`. Giai đoạn đầu có compatibility mapping từ biến cũ sang canonical config; chỉ bỏ alias trong một kế hoạch migration riêng được duyệt.

### 6.4. Precedence và validation

```text
safe code defaults
< non-secret cluster profile
< .env
< process/secret-file override
< versioned run policy đối với trường run-specific
```

Startup phải validate:

- ID/FSID đúng format; actual FSID khớp expected FSID trước mutation.
- URL không chứa credential; SSH host key pin/known_hosts được cấu hình.
- Ratio, timeout, parallelism và freshness nằm trong range hợp lệ.
- Allowlist không chứa wildcard `*` hoặc entry rỗng.
- Path nằm dưới root cho phép; secret file không được trả qua API.
- Feature dependency hợp lệ. Ví dụ bật Warp nhưng thiếu adapter thì QoS `BLOCKED`, không làm production service crash.

### 6.5. Config snapshot và đổi lab

Khi tạo session:

1. Resolve profile + `.env` + policy.
2. Probe actual FSID/capabilities.
3. Redact secret, canonicalize config và tính `config_hash`.
4. Lưu `cluster_profile_revision`, `policy_revision`, `config_snapshot_id`, `fsid` vào session/run.
5. Resume chỉ được phép khi deployment khớp snapshot hoặc có explicit reconcile/migration được audit.

Nếu đổi `.env` sang lab khác khi còn run chưa hoàn tất, startup chỉ cho read/report run cũ; mutation/resume bị chặn với `CLUSTER_PROFILE_MISMATCH`.

---

## 7. Inventory, capability và batch planning

### 7.1. Cluster inventory canonical

Inventory tối thiểu:

- FSID, Ceph release/version, orchestrator và command capabilities.
- OSD ID + incarnation, host/rack/failure domain/device class.
- up/in, service image/version/digest, daemon health và crash evidence.
- Pool type/size/min_size/CRUSH rule và PG scope.
- PG up/acting/actual primary, interval/epoch và bytes estimate.
- Primary-affinity, upmap/upmap-items, balancer/autoscaler và maintenance flags.
- Per-OSD capacity, PG/primary count, recovery/backfill/scrub và telemetry freshness.
- Spare registry, resource reservation, planned/already-down set.

### 7.2. Capability matrix

| Capability | Trạng thái |
|---|---|
| Query OSD image digest | SUPPORTED / DEGRADED / UNSUPPORTED |
| Query PG up/acting/primary | SUPPORTED / UNSUPPORTED |
| New deep-scrub completion marker | SUPPORTED / FALLBACK_LOG_EVIDENCE / UNSUPPORTED |
| cephadm redeploy target image | SUPPORTED / UNSUPPORTED |
| safe-to-destroy | SUPPORTED / UNSUPPORTED |
| Prometheus client counters | SUPPORTED / STALE / UNSUPPORTED |
| Warp/fio runner | SUPPORTED / DISABLED / UNSUPPORTED |

Capability probe là read-only. Không dùng branch kiểu “Pacific luôn có field X”; adapter fixture phải chứng minh schema thực.

### 7.3. Batch parameters độc lập

```text
batch_size
drain_parallelism
max_simultaneous_down
return_parallelism
scrub_concurrency
promotion_parallelism
chain_parallelism
handoff_parallelism
max_pg_per_handoff_group
max_bytes_per_handoff_group
```

UI hiển thị cả cấu hình và số thực tế. `batch_size=9` không được diễn giải thành chín OSD down đồng thời.

Suggestion có thể xét PG overlap, failure domain, bytes, primary duty, capacity và tải nền; operator vẫn xác nhận plan. Inventory được recheck ngay trước drain, admission, down và restore.

### 7.4. OSD Info Collector và contract hiển thị

Inventory dùng artifact từ [OSD Info Collector](./osd-info-collector/README.md). Bảng OSD có tối thiểu các cột sau:

| Nhóm | Trường hiển thị |
|---|---|
| Danh tính | `osd.N`, OSD FSID, version/image, host, rack và CRUSH location |
| Mạng | public IP, cluster IP; giữ danh sách address khi daemon quảng bá cả v1/v2 |
| Thiết bị | data/DB/WAL path, physical device như `/dev/sdb`, device ID/serial nếu metadata có |
| Dung lượng | total, used, available và used percent; phân biệt capacity OSD với kích thước DB/WAL |
| Placement | tổng PG chứa OSD, số PG OSD làm primary, up/in, weight, reweight và primary-affinity |
| Chất lượng | thời điểm collect, `VALID/PARTIAL/INCONCLUSIVE`, warning và link raw evidence |

Mỗi hàng mở detail drawer để xem raw command output, config database và effective config. Nếu BlueStore dùng LVM, Console hiển thị cả LV/`/dev/dm-*` và physical device do metadata báo; không tự thay path bằng `/dev/sdX`. Không có device path thì hiển thị `UNKNOWN` cùng lý do.

Nút `Collect inventory` tạo job read-only cho các OSD đã chọn hoặc toàn allowlist. Plan lưu `osd_inventory_artifact_id`, hash và timestamp. Trước drain và trước từng down-set, Console yêu cầu snapshot mới; snapshot cũ vẫn bất biến để phục vụ audit và so sánh trước/sau.

Collector chỉ chạy argv/schema cố định trên host allowlist, xác minh FSID, timeout, size và phiên bản/hash artifact. Không nhận command tùy ý từ UI; browser không SSH trực tiếp. JSON gốc được giữ bất biến trong evidence store; API detail chỉ trả projection đã xác minh/redact theo quyền.

Phải giữ topology/device và cluster context đã index trong migration `0018`–`0019`, cũng như API compare/config-diff hiện có. Missing/unsupported không được thay bằng 0, IP/device suy đoán hoặc capacity mặc định.

### 7.5. Danh sách OSD đã chọn trong plan

- Trang OSD & Batch/run detail hiển thị **danh sách đã lưu trong plan**, gồm thứ tự chọn, source/destination, PA1 X/S/R hoặc PA2 U/D, wave/chain/step nếu có; không chỉ hiển thị selection tạm trong form.
- Hiển thị inventory binding (collection/artifact/hash/timestamp), coverage đủ/thiếu, version/digest, isolation, reservation, eligibility và freshness cho mỗi OSD.
- Phân biệt planned role với actual role/membership hiện tại. Trong PA2 lượt đầu X→S, lượt sau Y→X; nâng cấp daemon giữ ID/incarnation khi không replacement, còn replacement phải có incarnation mới.
- D đúng image/healthy/isolated mới là spare candidate, chưa phải replica PASS. Không tự suy danh sách đích ở lượt sau hoặc ghi lại plan khi người dùng chỉ xem/refresh inventory.
- Reopen/reload plan phải giữ selection; refresh snapshot tạo binding/revision mới có audit theo API, không ghi đè snapshot lịch sử. Read-only readiness/down-set chỉ là assessment, không tự mở mutation.
- Suggestion xét cả shared spare và PG/failure-domain overlap; operator vẫn chọn/xác nhận. Một chain tuần tự, nhiều chain chỉ song song khi không xung đột PG, destination, lease, capacity, down-set hay recovery/QoS budget.

---

## 8. Domain result và invariant chung

Mỗi production run bind tối thiểu `session_id`, `cluster_id`, `fsid`, `execution_environment`, profile PA1/PA2, target/source incarnation, source/target version và image digest, `cluster_profile_revision`, `policy_revision`, `config_snapshot_id`, rollback plan và stable-window policy. Không trường strategy hoặc PA2 end state nào được ngầm chọn từ UI default.

### 8.1. Result taxonomy

| Result | Nghĩa |
|---|---|
| `PASS` | Điều kiện đúng trong scope/thời gian có evidence hợp lệ |
| `HOLD` | Trạng thái thực không an toàn hoặc stop policy đã kích hoạt |
| `BLOCKED` | Thiếu prerequisite/capability bắt buộc |
| `INCONCLUSIVE` | Evidence thiếu, stale, gap hoặc không đủ liên tục |
| `NOT_REQUESTED` | Workflow tùy chọn không bật |
| `NOT_EXERCISED` | Đường dữ liệu/chức năng chưa được kiểm; không đồng nghĩa PASS |
| `UNSUPPORTED` | Adapter/release/scope chưa được hỗ trợ |
| `NOT_COMPARABLE` | Hai run không đủ điều kiện so sánh |

### 8.2. Invariant chung

- Isolation kiểm cả `up[]` và `acting[]` trên toàn scope hiện tại.
- OSD nhận chỉ chứa PG đã admit ở bước hiện tại và giữ vai trò replica tới gate restore.
- `primary-affinity` không điều khiển membership; upmap không phải lệnh đặt primary.
- `norebalance` không phải admission barrier.
- Deep-scrub là lượt mới sau convergence, có completion evidence và result.
- Restore chỉ thay đổi resource run sở hữu và chỉ sau coverage đầy đủ.
- Mọi mutation có idempotency key, expected state, plan revision, lease/fence và before/after observation.
- PG/mapping/incarnation thay đổi có thể invalidate evidence liên quan; epoch tăng đơn thuần không tự invalidate nếu mapping không đổi.
- Không nâng source PA2 khi handoff set chưa hoàn tất hoặc source còn trong actual up/acting.

### 8.3. Tách hai loại guard

`UpgradeSafetyGate` và `WorkloadCapacityGuard` là hai domain khác nhau:

- `UpgradeSafetyGate`: down set, failure domain, capacity/recovery headroom, placement, health, mapping, version, evidence và stable window.
- `WorkloadCapacityGuard`: admission cho RGW PUT/update, RBD create/file write và legacy workload theo ceiling/reservation hiện tại.
- Hai guard dùng chung `CapacitySnapshotPort` nếu cần, nhưng không gọi lẫn nghiệp vụ hoặc dùng chung verdict.
- Thiếu legacy workload telemetry không làm production-only run lỗi nếu production policy không yêu cầu nguồn đó.
- Benchmark có thể bị throttle/pause; production chỉ HOLD khi run đã chọn rõ stop policy liên quan.

---

## 9. PA1 — Drain, upgrade và return

### 9.1. State machine

```text
CREATED
  -> PREFLIGHT_READY
  -> BASELINE_READY
  -> DRAINING
  -> DRAINED
  -> MAINTENANCE_APPROVED
  -> UPGRADING
  -> DAEMON_READY
  -> REPLICA_RETURN
  -> REPLICA_CONVERGING
  -> REPLICA_SCRUBBING
  -> REPLICA_ACCEPTED       (lặp theo return group)
  -> PRIMARY_RESTORE_READY
  -> PRIMARY_RESTORED
  -> RESTORING
  -> STABILIZING
  -> COMPLETE
```

`HOLD`, `BLOCKED` và `INCONCLUSIVE` là trạng thái có reason/evidence, không phải con trỏ bước. Resume luôn reconcile actual state.

### 9.2. Flow

1. Tạo run với X, S, target version/image digest, rollback plan và policy revision.
2. Probe capability, scope, compatibility, quyền, capacity/down set và evidence sources.
3. Lưu baseline health, versions, PG mappings, affinity, overrides, flags, service specs và capacity.
4. Giảm primary duty theo plan.
5. Drain X→S theo nhóm và theo budget.
6. Chứng minh X vắng trong up/acting của toàn scope.
7. Recheck maintenance gate ngay trước stop/redeploy.
8. Redeploy X qua adapter với digest đã chốt.
9. X up/in, đúng version/digest/incarnation và vẫn isolated.
10. Admit từng return group; X là actual replica, không là primary.
11. Chờ active+clean, yêu cầu deep-scrub mới và thu completion/result.
12. Chỉ khi toàn return set đạt mới mở affinity restore.
13. Restore config thuộc ownership của run, quan sát actual primary/placement.
14. Chờ stable window rồi complete.

### 9.3. Gate bắt buộc

| Gate | Điều kiện chính |
|---|---|
| `RETURN_ALLOWED` | X daemon ready, đúng digest, isolation đúng, plan/capacity/safety hiện tại đạt |
| `REPLICA_ACCEPTED` | Nhóm hội tụ, X actual replica, active+clean, deep-scrub mới hoàn tất sạch |
| `PRIMARY_RESTORE_READY` | Toàn return set đủ coverage và actual membership khớp plan |
| `COMPLETE` | Restore thuộc ownership xong, ledger sạch, stable window đạt |

PG ngoài allowlist xuất hiện trên X tạo `HOLD_ADMISSION_BROKEN`. X thành primary trước restore tạo `HOLD_UNEXPECTED_PRIMARY`.

---

## 10. PA2 — Rotating spare

### 10.1. State machine wave/rotation

```text
WAVE_PLANNED
  -> CHAIN_READY
  -> SPARE_CANDIDATE
  -> SPARE_ADMISSION_ALLOWED
  -> HANDOFF_GROUP_CONVERGING
  -> HANDOFF_GROUP_SCRUBBING
  -> HANDOFF_GROUP_ACCEPTED  (lặp theo handoff group)
  -> HANDOFF_COMPLETE
  -> SOURCE_UPGRADING
  -> SPARE_ROTATED           (replan U/D kế tiếp)
  -> WAVE_RECONCILING
  -> WAVE_STABILIZING
  -> WAVE_COMPLETE
```

`HANDOFF_COMPLETE` không phải `WAVE_COMPLETE`. `SPARE_ROTATED` chỉ chứng minh source cũ đã thành candidate đúng image/isolation; chưa chứng minh đường dữ liệu nếu nó chưa nhận PG.

### 10.2. Flow một lượt U→D

1. Resolve U/D với incarnation, handoff-set revision và dependency hiện tại.
2. D đúng target digest, healthy, reserved và isolated ngoài admission.
3. Recheck capacity, failure domain, down set, chain conflict và mapping.
4. Admit canary group U→D; D phải là actual replica.
5. Chờ convergence, active+clean và deep-scrub completion mới.
6. Mở các group tiếp theo theo budget; PASS nhóm trước không cấp PASS nhóm sau.
7. Khi toàn handoff set đạt, U vắng toàn scope và D membership đúng plan mới restore affinity D theo policy.
8. Stable checkpoint và maintenance recheck.
9. Redeploy U lên target digest.
10. U healthy/isolated đúng incarnation thì trở thành spare candidate kế tiếp.
11. Replan cặp mới; không reuse gate của lượt cũ.

### 10.3. Chain, ownership và pause/resume

- Một chain chạy tuần tự; nhiều chain chỉ chạy đồng thời khi không xung đột PG, OSD, failure domain, capacity, down set, lease hoặc QoS budget.
- D đã nhận PG không còn là spare trống.
- Không xóa override/mapping của lượt trước nếu lượt sau còn phụ thuộc.
- Pause chặn mutation tiếp theo; recovery đã chạy có thể tiếp tục.
- Resume đọc actual mapping, command outcome, ledger, lease và evidence trước khi quyết bước.
- Không có nút tự đảo ngược toàn chuỗi PA2.

### 10.4. End state

Operator bắt buộc chọn, không có default:

- `KEEP_ROTATED_PLACEMENT`.
- `RECONCILE_TO_POLICY`.

`WAVE_COMPLETE` yêu cầu version coverage, end-state revision, ownership handoff, actual placement và stable window. Reconcile cuối wave gây data movement thì bytes/time/QoS phải được tính vào PA2.

Spare cuối chưa nhận dữ liệu sau nâng ghi `replica_validation=NOT_EXERCISED`; daemon/version/isolation được đánh giá riêng.

---

## 11. Placement, replica validation và affinity restore

### 11.1. Placement plan

Mỗi PG entry lưu:

```text
pgid
before/current/desired up[]
before/current/desired acting[]
actual_primary
mapping_interval + osdmap_epoch
source_osd/incarnation
destination_osd/incarnation
expected_destination_role
owner_run + plan_revision
dependent_steps
disposition
estimated_bytes
```

`disposition` phân biệt thay đổi tạm cần restore, placement giữ theo end state và ownership đã bàn giao.

### 11.2. Production Replica Checker

Với mỗi PG vừa admit:

1. Chứng minh mapping đã hội tụ.
2. Chứng minh target là actual replica.
3. Chứng minh active+clean.
4. Chốt pre-scrub marker sau convergence.
5. Request deep-scrub mới.
6. Chứng minh started/completed bằng adapter phù hợp release.
7. Thu inconsistency, I/O error, repair event, crash/log và freshness.
8. Ghi PASS/HOLD/BLOCKED/INCONCLUSIVE cho đúng PG/group/incarnation.

Request `rc=0`, marker cũ hoặc không bắt gặp cờ scrubbing không đủ để kết luận. Repair event tạo HOLD để đánh giá; không tự repair rồi xóa dấu vết.

### 11.3. Affinity restore

Restore chỉ mở khi:

- Toàn return/handoff set đạt.
- Actual PG membership của target khớp plan hoặc phần phát sinh đã được bổ sung/kiểm.
- Target vẫn là replica trong cửa sổ kiểm.
- Health/capacity/telemetry và stop policy đạt.
- Baseline/current/desired revision chưa xung đột.

Sau restore, controller ghi actual primary và theo dõi data movement/stable window. Restore affinity không cam kết một PG cụ thể sẽ chọn target làm primary.

---

## 12. Operational OSD rollback

Phân biệt:

- **Operational OSD rollback:** workflow phục hồi khi upgrade gặp lỗi.
- **Feature rollback/disable:** tắt feature flag hoặc deploy lại app; không tự xóa dữ liệu.

```text
HOLD
  -> CONTAINED
  -> SOURCES_READY
  -> SAFE_TO_REMOVE
  -> R_PROVISIONED
  -> R_REBUILT
  -> ROLLBACK_COMPLETE
```

Yêu cầu:

- Xác định X, nguồn replica hiện tại, old image digest/version, R/device, compatibility floor và service spec.
- `ok-to-stop` không thay `safe-to-destroy`.
- Stop/fence không đồng nghĩa được zap/remove.
- R là thiết bị sạch; ID mới hoặc ID cũ đã destroyed đều có incarnation/evidence mới.
- Không mở BlueStore đã nâng bằng binary cũ.
- Cephadm reconciliation phải được kiểm soát để R không tự chạy sai image.
- Với PA2, nguồn phục hồi lấy từ current mapping; không giả U đã drain hoặc initial S còn đủ mọi bản sao.
- Chain khác chỉ tiếp tục sau khi safety/resource gate được đánh giá lại.

---

## 13. QoS Observer

### 13.1. Tính độc lập

- QoS là optional workflow gắn `session_id` và optional `upgrade_run_id`/`wave_id`.
- Runner không đổi placement, stop OSD, restore affinity hoặc quyết production PASS.
- Tắt QoS không làm production run lỗi.
- QoS failure không đổi `operation_result`; nếu run đã chọn SLO stop policy, nó có thể HOLD mutation tiếp theo nhưng vẫn có verdict riêng.

### 13.2. Provider

- Warp cho RGW/S3.
- fio cho RBD/file.
- Legacy console workload có thể làm `application` provider tương thích, nhưng không gắn nhãn Warp/fio hoặc physical IOPS.
- Provider khác thêm qua `BenchmarkRunnerPort`, không sửa PA1/PA2 core.

### 13.3. Phase

| Phase | Ranh giới |
|---|---|
| BEFORE | Sau warm-up, trước mutation đầu tiên ảnh hưởng QoS |
| DURING PA1 | Từ affinity/drain đầu tiên qua return/scrub/restore |
| DURING PA2 | Từ spare preparation trong scope qua handoff/source upgrade/end-state reconcile |
| AFTER PA1 | Sau `AFTER_RETURN_STABLE` |
| AFTER PA2 | Sau `AFTER_WAVE_STABLE` |

AFTER không được dùng làm prerequisite cho return/handoff vì nó xảy ra sau các bước đó.

PA2 phát event `spare_prepare`, `handoff_group_start`, `handoff_group_converged`, `handoff_group_accepted`, `handoff_complete`, `source_upgrade`, `spare_rotated`, `wave_reconcile` và `wave_end_state_handed_over` trên envelope chung. Ổn định giữa hai lượt chỉ là checkpoint, không phải AFTER toàn wave.

Tắt workload benchmark không tắt health/client-QoS observation và safety gate bắt buộc; nguồn telemetry chưa cấu hình được ghi quality/capability tương ứng, không giả có metric.

### 13.4. Cohort và proof level

| Cohort | Điều kiện |
|---|---|
| `REMAP` | Actual membership đổi X→S/S→X hoặc U→D trong interval |
| `NEIGHBOR` | Không remap nhưng có overlap OSD/host/DB-WAL/NIC đã quan sát |
| `CONTROL` | Mapping không đổi và không có overlap đã quan sát |
| `UNATTRIBUTED` | Không đủ mapping/request evidence |

Proof level: `PG_ATTRIBUTED`, `PARTIAL_ATTRIBUTION`, `SERVICE_ONLY`. Endpoint metric không được trình bày như hiệu năng riêng của một OSD/PG khi không có mapping proof.

Asset read-only có thể dùng object test đã có. Workload ghi/xóa chỉ dùng bucket/image/vùng test được duyệt riêng, cleanup theo ownership của run. Cache hit, thiếu request trace hoặc không resolve object→PG phải hạ proof level; không tạo số liệu per-PG giả.

### 13.5. Metric/report

- Offered/completed IOPS, throughput, p50/p95/p99, errors/timeouts.
- Longest observed stall, SLO violation duration và time-to-stable.
- Bytes/PG moved, recovery rate, primary shifts, load model và gaps.
- Source, unit, sample window, observed/collected time, freshness, counter reset và config hash.
- Không tính phần trăm khi baseline 0 hoặc thiếu mẫu.
- Pause/throttle/change profile tạo segment mới; có thể làm comparison `NOT_COMPARABLE`.

---

## 14. Lab Test workspace

### 14.1. Nguyên tắc

- Dùng pool, PG, object/object prefix và OSD target đã được operator chọn trong lab.
- Không bắt tạo helper OSD, topology, pool hoặc dataset mới.
- Write test chỉ mở khi scope allowlist và operator xác nhận.
- Lab PASS không đại diện toàn cluster và không cấp production gate.

### 14.2. Kiểm tra

- Baseline PG active+clean, up/acting/primary.
- Hash/read trước thao tác.
- Read-back sau return PA1 hoặc handoff PA2.
- Optional write/read object mới đúng PG; kiểm primary chỉ PASS khi target thực sự là primary.
- Deep-scrub PG đã chọn.
- Error/crash/log evidence.

Kết quả: `PASS`, `HOLD`, `BLOCKED`, `INCONCLUSIVE`, `NOT_REQUESTED`, `NOT_EXERCISED`.

PA2 cần ít nhất hai lượt nếu mục tiêu là kiểm chuyển vai spare. Fixture mỗi lượt dựa trên PG/object thực của nguồn tương ứng; không suy PG của X cũng là PG của Y. Write test trong chế độ read-only hiển thị `NOT_REQUESTED`; spare cuối chưa nhận dữ liệu hiển thị `NOT_EXERCISED`.

---

## 15. Giữ chức năng cũ dưới Legacy Tools

`legacy` trong kế hoạch này nghĩa là **được giữ và bảo trì**, không có nghĩa unsafe, bỏ test hoặc chuẩn bị xóa.

### 15.1. Retention matrix

| Chức năng hiện có | Đích kiến trúc | Quyết định |
|---|---|---|
| Corpus browser và upload | `legacy_rgw` | Giữ |
| Random/browser upload | `legacy_rgw` | Giữ |
| Object list/head/range/preview/download | `legacy_rgw` | Giữ |
| Exact PUT/overwrite/metadata/delete/version list/bulk delete | `legacy_rgw` | Giữ |
| Legacy PUT job và RGW CRUD stream | `legacy_rgw` | Giữ cả hai job type |
| RBD volume lifecycle | `legacy_rbd` | Giữ |
| RBD SFTP file browser/preview | `legacy_rbd` | Giữ |
| RBD terminal | `legacy_rbd` | Giữ, tiếp tục ghi rõ shell thật lab-only |
| RBD checksum baseline/verify | `legacy_rbd` | Giữ như helper evidence, không đổi thành production PASS |
| Capacity collector snapshot | Shared adapter + legacy dashboard | Tái sử dụng |
| Workload Capacity Guard/reservation | `legacy_workload_capacity` | Giữ, tách khỏi UpgradeSafetyGate |
| Performance collector/dashboard | Shared telemetry + legacy view | Tái sử dụng |
| PowerShell setup/fill/verify scripts | `legacy/scripts` hoặc path tương thích | Giữ tới khi replacement đã test |
| Existing `/api/*` routes | Compatibility facade | Không breaking change trong đợt này |

### 15.2. Legacy safety contract

- RGW/RBD allowlist, prefix/mount containment, idempotency và capacity admission không bị bỏ vì chuyển vào legacy.
- Terminal không được dùng để bypass production executor policy.
- Legacy feature flag off không làm startup core upgrade thất bại.
- Core upgrade feature flag off không làm legacy regression.
- Legacy schema/data không bị rename/drop trong migration đầu.
- Existing API response giữ tương thích hoặc có versioned compatibility adapter/test.

### 15.3. Capacity contract giữ lại

- Mốc 70% tiếp tục là application admission ceiling của workload legacy, không phải physical invariant hoặc target chính xác.
- Quyết định theo participating OSD/per-OSD bound, không dùng cluster average một mình.
- Stale telemetry/OSDMap change/recovery-remap fail closed cho mutation tăng dung lượng.
- Delete thành công không đồng nghĩa raw capacity đã được trả ngay.
- RBD terminal/file write chỉ hợp lệ với `reserved-logical` hoặc nhãn best-effort rõ ràng.
- Reservation hết lease không tự release nếu outcome chưa reconcile.

### 15.4. Performance contract giữ lại

- `application`, `ceph` và `device` là ba source khác nhau.
- Rate tính từ counter delta theo cửa sổ; reset/gap không tạo spike hoặc số 0 giả.
- Pool/image scope chỉ hiển thị khi source hỗ trợ đúng semantics.
- Ceph average latency không được đổi nhãn thành p99.

---

## 16. API và command contract

### 16.1. API mới được version hóa

Danh sách là **contract đích**, không khẳng định mọi route đã implement/live-ready. Các route inventory, session và dry-run đã có phải giữ tương thích; đối chiếu source/OpenAPI và contract tests ở mỗi release. Chuẩn hóa prefix `/api/v1` và tên `qos-runs`; không tạo alias từ các route chỉ từng xuất hiện trong bản đặc tả cũ nếu không có client thật.

```text
GET  /api/v1/cluster/profile
GET  /api/v1/cluster/capabilities
GET  /api/v1/cluster/inventory

POST /api/v1/osd-inventory/collections
GET  /api/v1/osd-inventory/collections
GET  /api/v1/osd-inventory/collections/compare
GET  /api/v1/osd-inventory/collections/compare-config
GET  /api/v1/osd-inventory/collections/:id
GET  /api/v1/osd-inventory/collections/:id/osds/:osd_id
GET  /api/v1/osd-inventory/collections/:id/evidence

POST /api/v1/sessions
GET  /api/v1/sessions
GET  /api/v1/sessions/:id
GET  /api/v1/sessions/:id/timeline
GET  /api/v1/sessions/:id/report

POST /api/v1/upgrade-batches
GET  /api/v1/upgrade-batches/:id
POST /api/v1/upgrade-batches/:id/maintenance-gate

POST /api/v1/upgrade-runs
GET  /api/v1/upgrade-runs/:id
POST /api/v1/upgrade-runs/:id/inventory-bindings
GET  /api/v1/upgrade-runs/:id/inventory-readiness
POST /api/v1/upgrade-runs/:id/down-set-readiness
POST /api/v1/upgrade-runs/:id/preflight
POST /api/v1/upgrade-runs/:id/baseline
POST /api/v1/upgrade-runs/:id/drain/next
POST /api/v1/upgrade-runs/:id/isolation/verify
POST /api/v1/upgrade-runs/:id/redeploy
POST /api/v1/upgrade-runs/:id/return/next
POST /api/v1/upgrade-runs/:id/replica-check/:group_id
POST /api/v1/upgrade-runs/:id/affinity/restore
POST /api/v1/upgrade-runs/:id/restore
POST /api/v1/upgrade-runs/:id/pause
POST /api/v1/upgrade-runs/:id/resume

POST /api/v1/upgrade-waves
POST /api/v1/upgrade-waves/:id/plan
GET  /api/v1/upgrade-waves/:id/end-state
POST /api/v1/upgrade-waves/:id/pause
POST /api/v1/upgrade-waves/:id/resume
POST /api/v1/upgrade-waves/:id/reconcile
POST /api/v1/upgrade-waves/:id/complete
POST /api/v1/spare-chains/:id/next-target
POST /api/v1/rotation-steps/:id/admission/precheck
POST /api/v1/rotation-steps/:id/handoff/next
POST /api/v1/rotation-steps/:id/replica-check/:group_id
POST /api/v1/rotation-steps/:id/affinity/restore
POST /api/v1/rotation-steps/:id/handoff/commit
POST /api/v1/rotation-steps/:id/source/redeploy

POST /api/v1/rollback-runs
POST /api/v1/rollback-runs/:id/contain
POST /api/v1/rollback-runs/:id/removal-gate
POST /api/v1/rollback-runs/:id/replace

POST /api/v1/qos-runs
POST /api/v1/qos-runs/:id/start
POST /api/v1/qos-runs/:id/pause
POST /api/v1/qos-runs/:id/resume
POST /api/v1/qos-runs/:id/stop
GET  /api/v1/qos-runs/:id/results

POST /api/v1/lab-runs
POST /api/v1/lab-runs/:id/prepare
POST /api/v1/lab-runs/:id/read-check
POST /api/v1/lab-runs/:id/write-check
POST /api/v1/lab-runs/:id/deep-scrub
GET  /api/v1/lab-runs/:id/report

POST /api/v1/comparisons
GET  /api/v1/comparisons/:id
GET  /api/v1/evidence/:id
```

### 16.2. Mutation envelope

Mỗi mutation nhận:

```text
Idempotency-Key
expected_state
plan_revision
config_snapshot_id
resource_version / If-Match
operator reason
```

Backend claim resource lease/fence trong transaction và trả `202 + job_id` cho action dài. Retry cùng key + cùng fingerprint replay state/result; cùng key khác fingerprint trả conflict.

### 16.3. Error contract

Lỗi chuẩn có `request_id`, `code`, `message`, `retryable`, `observed_state`, `evidence_refs` và không chứa secret/raw command.

```text
CLUSTER_PROFILE_MISMATCH
FSID_MISMATCH
CAPABILITY_UNSUPPORTED
STALE_INVENTORY
STATE_CONFLICT
PLAN_REVISION_CONFLICT
LEASE_CONFLICT
ADMISSION_BROKEN
UNEXPECTED_PRIMARY
SCRUB_EVIDENCE_INCOMPLETE
MAINTENANCE_GATE_FAILED
ROLLBACK_VERSION_INCOMPATIBLE
NOT_COMPARABLE
```

### 16.4. API legacy

- Existing `/api/buckets`, `/api/objects*`, `/api/jobs*`, `/api/rbd*`, `/api/capacity*`, `/api/performance*` tiếp tục hoạt động.
- Refactor bên trong không đổi contract âm thầm.
- Nếu cần contract mới, thêm `/api/v1/legacy/...` và giữ facade cũ trong ít nhất một migration window có contract tests.

---

## 17. Data model và migration

### 17.1. Nguyên tắc migration

- Giữ nguyên mọi migration đã phát hành/đã áp dụng, gồm file `0001`–`0019` hiện có; không sửa checksum hoặc tái dùng số migration.
- Chỉ thêm forward migration.
- Không drop/rename destructive bảng/cột legacy trong các pha đầu.
- Backfill `cluster_id`/`fsid` theo config snapshot đã xác minh; không đoán nếu thiếu evidence.
- Row không xác định cluster giữ `LEGACY_UNSCOPED` và read-only tới khi operator reconcile.

### 17.2. Entity mới

| Nhóm | Entity chính |
|---|---|
| Cluster/config | `cluster_profiles`, `cluster_capabilities`, `config_snapshots`, `policy_revisions` |
| Session | `sessions`, `session_workflows`, `upgrade_batches` |
| PA1 | `upgrade_runs`, `return_groups`, `affinity_restores` |
| PA2 | `upgrade_waves`, `spare_chains`, `rotation_steps`, `spare_registry`, `handoff_groups`, `end_state_handoffs` |
| Placement | `placement_plans`, `placement_entries`, `pg_role_observations`, `maintenance_sets` |
| Evidence | `scrub_runs`, `evidence_artifacts`, `phase_events`, `telemetry_windows` |
| Mutation | `run_changes`, `resource_leases`, `action_jobs`, `outbox_events` |
| Rollback | `rollback_runs`, `replacement_sources`, `replacement_rebuild_groups` |
| QoS | `benchmark_profiles`, `benchmark_runs`, `benchmark_segments`, `benchmark_metrics`, `benchmark_cohorts`, `workload_pg_bindings` |
| Lab | `lab_runs`, `lab_targets`, `lab_checks` |
| Report | `reports`, `comparisons`, `comparison_inputs` |

### 17.3. Scope và uniqueness

- Mọi entity runtime có `cluster_id`, `fsid` và `config_snapshot_id` phù hợp.
- Unique key gồm run/checkpoint/resource/attempt/incarnation khi cần.
- Retry append attempt/evidence; không ghi đè artifact lịch sử.
- Event sequence monotonic trong từng session/run.
- Artifact có SHA-256, size, MIME, producer, timestamps, access policy và retention.

### 17.4. Migration hiện có và bước tiếp theo

| Migration | Nội dung trong source |
|---|---|
| `0001`–`0008` | Legacy baseline, jobs/fencing, performance và RBD validation |
| `0009` | Cluster profiles và sessions |
| `0010` | Evidence, outbox và leases |
| `0011` | Upgrade dry-run |
| `0012` | Capability và phase events |
| `0013` | PA1, replica và rollback |
| `0014` | PA2 spare-chain ledger |
| `0015` | QoS observer |
| `0016` | OSD Info Collector |
| `0017` | Upgrade inventory bindings |
| `0018` | OSD inventory topology fields |
| `0019` | OSD inventory cluster context |

Thay đổi tiếp theo bắt đầu từ số chưa dùng (`0020+` tại thời điểm này), sau khi kiểm repository/schema thực. Image đóng gói nguyên bộ migration; role `migrate` chạy one-shot có lock trước app/worker. Release manifest ghi schema range tương thích; rollback app không tự downgrade schema hoặc xóa evidence.

---

## 18. Frontend

### 18.1. Navigation

```text
Overview
OSD & Batch
Upgrade Operation
QoS Observer
Lab Test
Rollback
Evidence & Comparison
Legacy Tools
  ├── RGW Object Console
  ├── RBD Volumes
  ├── Workload Capacity
  └── Performance (legacy/shared telemetry view)
```

Feature disabled hiển thị `NOT_REQUESTED`/not configured phù hợp, không gây lỗi toàn app.

| Màn hình | Nội dung |
|---|---|
| Overview | Health, capacity, recovery/scrub, run đang chạy và lý do HOLD |
| OSD & Batch | Inventory, X/S/R hoặc U/D, overlap PG, failure domain, down set, spare registry |
| Upgrade Operation | Stepper PA1 hoặc PA2; wave, chain, lượt U→D và điểm HOLD |
| QoS Observer | Asset, workload, phase, cohort, so sánh và raw result |
| Lab Test | PG/pool/object test, checksum và scrub result; mở tài liệu lab |
| Rollback | Containment, nguồn phục hồi, removal gate, R bản cũ |
| Evidence & Comparison | Timeline, command output, logs, ledger, kết quả và so sánh PA1–PA2 |

Một session có thể gắn nhiều run nhưng mỗi run có state và evidence riêng. Chỉ production cũng là một session hợp lệ.

### 18.2. Tách frontend theo feature

```text
frontend/src/
  app/                 # shell, routing, error boundary
  shared/              # API client, contracts, formatting
  features/
    overview/
    inventory/
    upgrade-pa1/
    upgrade-pa2/
    qos/
    lab/
    rollback/
    evidence/
    legacy-rgw/
    legacy-rbd/
```

Không tiếp tục dồn tất cả view vào `App.tsx`. Mỗi feature có route, API contract và tests riêng.

### 18.3. UI production

- Run form bắt buộc chọn `PA1_PRODUCTION` hoặc `PA2_ROTATING_SPARE`; không default.
- PA2 end-state không default.
- Hiển thị config/profile revision và actual FSID.
- Mapping table có before/current/desired up/acting, actual primary, convergence, owner và dependency.
- Stepper chỉ mở action backend cho phép.
- Pause, HOLD, BLOCKED, INCONCLUSIVE và NOT_EXERCISED có semantics riêng.
- OSD/Batch hiển thị số actual đang drain/down/return/scrub, không chỉ config.
- QoS, Lab và operation có verdict riêng trên report.
- Comparison không dùng màu thắng/thua, score tổng hợp hoặc recommendation tự động.

### 18.4. Form tạo run

| Nhóm | Trường |
|---|---|
| Chung | FSID, môi trường, tên session, policy revision, profile bắt buộc chọn: `PA1_PRODUCTION` hoặc `PA2_ROTATING_SPARE` |
| PA1 | X, S, target image/version/digest, drain/return plan, rollback plan |
| PA2 | Wave/chain, initial spare S, danh sách nguồn, target digest, handoff groups, end-state policy, rollback plan |
| PA2 end state | Chọn `KEEP_ROTATED_PLACEMENT` hoặc `RECONCILE_TO_POLICY`; không có giá trị mặc định |
| Batch | Các giới hạn đồng thời và stable-window policy |
| QoS tùy chọn | Engine, asset, endpoint/client, load model, thời lượng, budget |
| Lab tùy chọn | Test pool, PG đã chọn, object hoặc object prefix, X/S, read/write mode, scrub policy |
| Evidence | Telemetry source, freshness, output retention, quyền |

Lab form không bắt tạo pool/PG phụ, helper OSD, dataset manifest hay topology riêng. Chỉ cho chọn tài nguyên test đã được xác định trong lab và yêu cầu xác nhận scope trước khi ghi.

`target image/version/digest` trong form là **Ceph OSD image**, không phải image Storage Lab Console. Digest ứng dụng thuộc thông tin deployment/release, không được dùng thay target OSD.

### 18.5. Stepper và detail panel

#### PA1. PA1 — Drain, nâng cấp và return

1. Baseline và plan.
2. Giảm primary duty theo plan.
3. Drain toàn bộ production PG khỏi X theo nhóm.
4. Kiểm production isolation.
5. Maintenance gate cho down set.
6. Stop/redeploy X.
7. X up/in, đúng version/image, chưa có production PG ngoài admission.
8. Return nhóm PG về X ở vai trò replica.
9. Chờ active+clean và deep-scrub mới hoàn tất.
10. Lặp return/scrub đến hết return set.
11. Khôi phục primary-affinity theo baseline/policy.
12. Restore cấu hình và đợi `AFTER_RETURN_STABLE`.

QoS observer nằm cạnh stepper và nhận event từ các bước trên. Lab test mở workspace riêng; không chen vào điều kiện return của production.

#### PA2. PA2 — Rotating spare

1. Baseline toàn wave, kiểm thứ tự upgrade/hop và lập desired end state.
2. Chuẩn bị initial spare S đúng target digest, không phục vụ PG ngoài admission.
3. Chọn U/D; precheck capacity, CRUSH/failure domain, mapping và reservation.
4. `SPARE_ADMISSION_ALLOWED`: cho nhóm canary U→D, D phải là replica thực tế.
5. Chờ active+clean và deep-scrub mới hoàn tất → `HANDOFF_GROUP_ACCEPTED`.
6. Lặp từng handoff group; nhóm đã đạt không cấp PASS cho nhóm chưa kiểm.
7. Toàn handoff set đạt, U vắng mặt ở up/acting của toàn scope; restore affinity D theo policy và chờ ổn định → `HANDOFF_COMPLETE`.
8. Recheck maintenance/down set, redeploy U lên target image.
9. U đúng digest, healthy và vẫn isolated → `SPARE_ROTATED`; U là spare candidate cho nguồn kế tiếp.
10. Recheck cặp nguồn/đích mới rồi lặp; cuối wave áp dụng end-state policy và chờ `AFTER_WAVE_STABLE` → `WAVE_COMPLETE`.

Timeline hiển thị từng lượt, ví dụ X→S rồi Y→X, cùng trạng thái dữ liệu, phiên bản và vai trò của từng OSD. Không thêm bước trả S→X bắt buộc. Nút pause ngăn mutation tiếp theo; recovery đã chạy có thể tiếp tục. Resume phải reconcile trạng thái thực và ledger.

Spare cuối wave chưa từng nhận dữ liệu sau nâng hiển thị `replica_validation=NOT_EXERCISED`, tách khỏi gate image/isolation. Console không biến trạng thái này thành bằng chứng kiểm replica thành công.

Mỗi return/handoff group hiển thị PG count, bytes, convergence, actual role, scrub requested/started/completed, inconsistency, I/O errors, repair events và freshness. Mapping detail có before/current/desired, epoch/interval, owner, revision, disposition và dependent steps; conflict phải được báo trước khi ghi toàn mapping của PG.

Rollback wizard hiển thị nguồn replica còn lại theo current mapping, old digest, R/device, compatibility/release floor, removal gate, service spec và incarnation; không có nút tự đảo ngược PA2 chain. Nút mở Lab chỉ liên kết workspace riêng, không thêm prerequisite helper vào production.

---

## 19. Security, safety và audit

- `.env`, private key, token, keyring và credential không commit.
- Ưu tiên secret file/mount; secret trực tiếp trong `.env` chỉ dành local lab và vẫn redact.
- SSH host key phải pin bằng known_hosts/fingerprint; không auto-accept host mới cho mutation.
- Node/executor không publish public port; chỉ backend gọi bằng token/mTLS tùy deployment.
- Command protocol là action schema đóng; không nhận raw command từ browser.
- Command arg validate theo type/allowlist; không nối input vào shell string.
- Production action không dùng interactive terminal.
- Actor/reason/request/config revision/expected/observed result được audit.
- Emergency stop chặn mutation mới nhưng không kill command/recovery mù; phải reconcile action đang bay.
- Cleanup chỉ tác động resource có ownership evidence.
- `UPGRADE_MUTATIONS_ENABLED=false` là default; bật cần explicit deployment change và preflight PASS.

---

## 20. Telemetry, evidence và report

### 20.1. Telemetry record

```text
metric_name
source + source_version
unit + metric_type + labels
scope_type + scope_id
observed_at + collected_at
window_start/end
freshness + quality
counter_reset + gap_reason
artifact/query reference
```

Quality: `VALID`, `STALE`, `GAP`, `UNSUPPORTED`.

### 20.2. Evidence production

- Baseline, inventory và capability snapshot.
- Before/current/desired mappings và interval.
- Version/image digest/incarnation.
- Down-set/maintenance gate.
- Return/handoff group observations.
- Scrub start/completion/result.
- Affinity restore và stable window.
- Change ledger, lease/fence, command outcome.
- Rollback evidence nếu có.

### 20.3. Report contract

```json
{
  "operation_result": {},
  "qos_result": {"status": "NOT_REQUESTED"},
  "lab_result": {"status": "NOT_REQUESTED"},
  "rollback_result": null,
  "evidence_summary": {},
  "limitations": []
}
```

Không merge ba verdict thành một PASS chung.

### 20.4. PA1–PA2 comparison

Chỉ so khi tương đương về:

- Cluster/topology/hardware và upgrade hop.
- Tập OSD/source scope.
- Asset/workload/load model/client/cache.
- Recovery/scrub/concurrency budget.
- Mốc BEFORE/DURING/AFTER và proof level.
- Chi phí bootstrap spare và end-state reconcile.

Nếu không tương đương, trả `NOT_COMPARABLE` kèm lý do nhưng vẫn hiển thị raw result. Không suy ước lượng 2D/D thành cam kết giảm 50% thời gian hoặc giữ nguyên IOPS.

Hiển thị hai phương án cạnh nhau, cùng đơn vị đo và phạm vi; không gán màu thắng/thua hoặc đề xuất chọn phương án.

| Trục so sánh | PA1 | PA2 |
|---|---|---|
| Luồng | X→S, nâng X, return về X | X→S, nâng X; Y→X, nâng Y; tiếp tục chuyển vai |
| Đối tượng kiểm dữ liệu bản mới | X nhận lại các PG sau nâng | D nhận PG nguồn hiện tại; X được kiểm dữ liệu khi làm D ở lượt sau |
| Phạm vi hoàn tất | Run/batch đã return và restore | Wave đã hoàn tất các nguồn, spare và end-state policy |
| Placement cuối | Theo return plan/baseline | Theo rotated layout hoặc reconcile policy đã chọn |
| Dữ liệu phải chuyển | Drain, return và phát sinh thực tế | Handoff, chuẩn bị S, reconcile và phát sinh thực tế |
| Tài nguyên | Reservation S và down set theo run | Reservation U/D, chain dependency và tính hợp lệ của spare kế tiếp |
| Rủi ro vận hành | Return/scrub/restore và tải hai chiều | Handoff/scrub, chuyển vai và dependency của mapping |
| Phục hồi | Nguồn replica hiện tại, replacement sạch tương thích | Cùng nguyên tắc; xác định lại nguồn theo trạng thái chuỗi hiện tại |
| QoS | IOPS/latency/errors/stall trong toàn phạm vi | Cùng bộ đo, gồm cả reconcile nếu có |

So sánh thực nghiệm cần cùng tập OSD được nâng, upgrade hop, payload/workload, topology và ngân sách recovery/scrub. Báo tổng bytes, tổng thời gian, time-to-stable, QoS, lỗi và công vận hành; nêu rõ chi phí chuẩn bị spare. Thiếu phạm vi tương đương hiển thị `NOT_COMPARABLE` và lý do.

Ước lượng ~2D của PA1 so với ~D của PA2 chỉ áp dụng cho tổng payload D của một chuỗi handoff lý tưởng giữ rotated placement, chưa cộng các phát sinh. Không chuyển tỷ lệ bytes này thành cam kết giảm một nửa thời gian hoặc giữ nguyên IOPS.

### 20.5. Snapshot collector và report trước/sau

OSD Info Collector tạo snapshot cấu hình/trạng thái, không thay continuous metrics collector. Baseline chuẩn gồm `BEFORE`, `AFTER_START`, `AFTER_STABLE`; `DURING` tùy policy hoặc sự cố. Mỗi snapshot mang FSID, OSD ID/incarnation, collector version/hash, phase/run/step, observed/collected time, artifact/hash và quality.

Report so host/IP/device/version, capacity/usage, PG/primary count, up/in/weight và effective config giữa các phase. Counter hiệu năng chỉ so theo process epoch hợp lệ; restart/counter reset/gap không thành chênh lệch tải giả. Inventory quality `VALID/PARTIAL/INCONCLUSIVE` và metric quality `VALID/STALE/GAP/UNSUPPORTED` là hai contract riêng, không ép cùng enum.

Evidence QoS gồm raw client logs/histograms, assets/profile, phases/cohorts/samples/gaps; evidence Lab gồm PG query, object map, hashes, read/write, scrub và logs. PA2 lưu wave/chain/rotation step, initial/final spare, version coverage, dependency ledger và desired end-state revision. `HANDOFF_COMPLETE`/`SPARE_ROTATED` không tự đóng report toàn wave.

---

## 21. Kế hoạch triển khai theo pha

Mỗi pha phải giữ build/test xanh và có rollback feature flag. Không làm big-bang rewrite. Các foundation P1–P3 và một phần domain P4–P6 đã có code (mục 3); kiểm gap/exit gate trước khi làm tiếp, không viết lại từ đầu.

**Ưu tiên tiếp theo:** chốt baseline hiện có → I0 → I1 → I2 để đưa bản read-only/dry-run vào lab bằng image. P4–P7 tiếp tục trên nền đó; I3/P8 kiểm chứng phạm vi của từng release. Không bắt chờ toàn bộ live PA1/PA2 mới đóng gói, và không bật mutation chỉ vì image khởi động được.

### P0 — Freeze baseline và bảo vệ legacy

- Chạy/ghi lại backend, Node, frontend, migration và compose tests hiện có.
- Lập API snapshot/contract test cho route cũ.
- Inventory schema `0001`–`0019`, trạng thái áp dụng thực trên DB đích và fixture legacy.
- Xác nhận `.env` bị ignore; không đưa secret vào report.
- Giữ trạng thái PASS/PARTIAL/NOT_RUN theo `VALIDATION.md`, không nâng claim.

**Exit gate:** baseline reproducible; không file legacy nào bị xóa; có danh sách behavior/API cần giữ.

### P1 — Config foundation và modular seams, không đổi behavior

- Mở rộng `.env.example`; tạo quy trình copy `.env.example` → `.env` cho từng lab.
- Thêm `ClusterProfile`, typed config, secret reference, config snapshot/hash.
- Canonicalize Python/Node config; giữ alias `RBD_*`/`RGW_*`.
- Tách `main.py`, `api/rbd.py`, `App.tsx` theo feature mà không đổi API.
- Di chuyển chức năng cũ vào `legacy_rgw`/`legacy_rbd` theo strangler pattern.
- Thêm feature flags và startup dependency validation.

**Exit gate:** legacy regression không đổi; cùng artifact khởi động với hai config giả khác nhau; wrong/missing FSID/allowlist fail closed.

### P2 — Read-only inventory, capability và evidence foundation

- Implement `ClusterIdentityPort`, `ClusterInventoryPort`, `PlacementQueryPort`, `HealthTelemetryPort`.
- Adapter Ceph CLI/SSH normalize output theo capability fixture.
- Migrations cho profile/session/outbox/evidence.
- UI Overview và OSD & Batch read-only.
- Config snapshot + inventory artifact + capability matrix.

**Exit gate:** hai lab profile khác topology/pool/host trả canonical inventory; không có cluster-specific constant trong application logic; stale/unsupported không thành 0.

### P3 — Common upgrade engine và dry-run

- Session/batch/run lifecycle.
- Common action job, idempotency, expected state, lease/fencing và ledger.
- Placement plan before/current/desired.
- `UpgradeSafetyGate`, maintenance/down-set gate và pause/resume reconcile.
- Dry-run command plan và fake adapter/simulator.
- Evidence timeline/report skeleton.

**Exit gate:** dry-run PA1/PA2 không gọi mutation adapter; duplicate/retry/crash không tạo double mutation; QoS/Lab disabled vẫn tạo session hợp lệ.

### I0 — Chốt release contract và dependency

- Chọn baseline `linux/amd64`, một OCI application image và các role tại mục 28.
- Lập bảng feature/capability đã có, chưa có và default disabled; chốt config schema, health contract, schema compatibility.
- Chuẩn hóa Python/Node env/secret-file/SSH identity và đường dẫn data; kiểm dependency khi feature tắt.
- Xác định registry/release naming, runtime prerequisites, external/bundled PostgreSQL và remote collector installation.

**Exit gate:** release scope không vượt evidence; không còn giá trị lab bắt buộc trong source/default; cấu hình tối thiểu upgrade-only được validate mà không cần RGW.

### I1 — Build một image và tách service theo role

- Multi-stage build frontend/assets và dependency pinned; đóng gói backend, executor, migration, collector từ build context chung.
- Role entrypoint whitelist, non-root runtime, graceful shutdown, health endpoints và runtime version info.
- Test legacy API/SSE/WebSocket/upload/static routing và workers với cùng image.
- Build exclusions/security checks ngăn `.env`, keyring, SSH keys, corpus/evidence/runtime data lọt vào layer.

**Exit gate:** tất cả role ứng dụng chạy cùng digest; không cài dependency lúc startup; test container thật đạt scope của release.

### I2 — Bộ triển khai online/offline

- Compose release dùng `image:` và digest, không `build:`; profiles cho optional roles và bundled DB.
- Mount config/secrets theo role; persistence DB/evidence/executor state; migrate one-shot và readiness dependency-aware.
- Remote collector version/hash install package; kiểm read-only inventory end-to-end, saved OSD list và evidence qua recreate.
- Bundle archive/manifest/checksums/config examples/runbook và quy trình restore nhất quán.

**Exit gate:** máy Linux sạch có runtime triển khai không cần source/build; offline từ bundle không pull/cài package; DB/evidence không mất khi recreate; chưa có authority thì chỉ read-only/dry-run.

### P4 — PA1 và operational rollback

- PA1 state machine và return groups.
- Isolation/admission manager.
- Production Replica Checker.
- Affinity restore/stable-window.
- Operational replacement rollback.
- PA1 UI stepper và evidence report.

**Exit gate:** fake integration đạt PA1 acceptance matrix; read-only shadow run đối chiếu live state; live canary chỉ mở sau operator duyệt và rollback rehearsal.

### P5 — PA2 rotating spare

- Wave, chain, rotation step, spare registry và reservation.
- Handoff group/admission/replica check.
- Dependency-aware ledger và ownership handoff.
- End-state policy/reconcile/version coverage.
- Pause/resume/failure handling theo current mapping.
- PA2 UI/timeline/report.

**Exit gate:** ít nhất hai lượt rotation trong simulator; không nâng U trước toàn handoff set; final spare chưa nhận PG ghi NOT_EXERCISED; cleanup không xóa mapping còn dependency.

### P6 — QoS Observer

- `BenchmarkRunnerPort`, Warp/fio adapter và capability probe.
- Event correlation, phase, segment, cohort, proof level.
- Metrics/raw artifact/result API và UI.
- Legacy application workload adapter.

**Exit gate:** production PASS độc lập khi QoS disabled; endpoint-only ghi SERVICE_ONLY; runner failure không ghi production FAIL; segment mismatch tạo NOT_COMPARABLE khi cần.

### P7 — Lab Test và comparison

- Lab run/target/check model.
- Existing PG/object selection, read/write/scrub flow.
- Lab report riêng và link vào session.
- PA1–PA2 comparison eligibility và side-by-side UI.

**Exit gate:** Lab disabled không ảnh hưởng production; một PG PASS không thành cluster PASS; scope mismatch trả NOT_COMPARABLE; không winner/default/score.

### P8 / I3 — Portability, release acceptance, fault test và hardening

- Chạy cùng application image digest trên ít nhất hai hệ thống/lab profile khác nhau, cùng kiến trúc hỗ trợ, không rebuild; lưu manifest/config hash và evidence install.
- Fault test DB/backend/worker/executor/SSH/Prometheus restart, timeout, counter reset và stale evidence.
- Secret/redaction/path/command injection tests.
- Recovery/backfill/external-change conflict tests.
- Runbook switch lab, emergency stop, resume/reconcile, cleanup và backup/restore DB/evidence.

**Exit gate:** đổi lab chỉ cần config + restart; không rò state/evidence/lease giữa cluster; unfinished run không resume trên profile khác. I3 đạt ma trận I01–I14 cho feature scope đã phát hành; release live PA1/PA2 còn phải đạt P4/P5/P8 và emergency/operational rollback rehearsal. Release read-only không được đánh các gate live chưa chạy là PASS.

---

## 22. Test matrix bắt buộc

### 22.1. Architecture/config/portability

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| A01 | Domain unit test không có DB/SSH/Ceph | Chạy với fake ports |
| A02 | Source application có IP/FSID/pool/path lab cụ thể | Không có; chỉ fixture/example |
| A03 | Python/Node nhận cùng canonical config | Không drift default/allowlist |
| A04 | Actual FSID khác expected | Mutation bị block trước command |
| A05 | Chuyển lab A sang lab B bằng config | Same artifact khởi động, capability đổi đúng |
| A06 | Run A active rồi startup profile B | Read/report được, resume/mutation bị block |
| A07 | Capability field không có trên release | UNSUPPORTED/BLOCKED; không crash/đoán |

### 22.2. Legacy regression

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| L01 | Existing RGW API contract | Không breaking change |
| L02 | Legacy PUT và CRUD job | Cả hai job type còn chạy |
| L03 | RBD create→mount→file→remount→delete | Behavior/evidence giữ nguyên |
| L04 | Terminal/file containment | Không path/symlink escape; terminal lab-only |
| L05 | Legacy flag off | Upgrade core khởi động bình thường |
| L06 | Upgrade flag off | Legacy stack khởi động bình thường |
| L07 | Migration từ legacy 0001–0008 và bản gần nhất đến schema release | Dữ liệu/API cũ, inventory bindings/evidence 0016–0019 vẫn đọc được |

### 22.3. PA1

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| P101 | X còn trong up hoặc acting của một PG scope | Chưa DRAINED/redeploy |
| P102 | X lên sai digest | Chưa DAEMON_READY/RETURN_ALLOWED |
| P103 | Return canary và X actual replica | Cho converge/scrub |
| P104 | X thành primary trong return | HOLD_UNEXPECTED_PRIMARY |
| P105 | PG ngoài allowlist xuất hiện trên X | HOLD_ADMISSION_BROKEN |
| P106 | Scrub request thành công, chưa completion | Chưa REPLICA_ACCEPTED |
| P107 | Một return group chưa đạt | Chưa restore affinity |
| P108 | Restore gây rebalance | Theo dõi tới stable window trước COMPLETE |
| P109 | Pause/crash rồi resume | Reconcile actual state/ledger trước action |

### 22.4. PA2

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| P201 | D đúng image nhưng chưa nhận PG | SPARE_CANDIDATE, không replica PASS |
| P202 | D trùng failure domain/down set/lease | Block trước mutation |
| P203 | Group đầu PASS, nhóm sau chưa kiểm | Không restore D/nâng U |
| P204 | U còn PG ngoài baseline snapshot | Chưa HANDOFF_COMPLETE; reconcile |
| P205 | Timeout handoff | Probe actual mapping trước retry |
| P206 | Cleanup xóa override còn dependency | Block và giữ/bàn giao ownership |
| P207 | Final spare chưa nhận PG | NOT_EXERCISED |
| P208 | End-state reconcile tạo backfill | Tính bytes/time/QoS, chờ stable window |
| P209 | D lỗi sau khi U drain | HOLD, lấy source từ current mapping |

### 22.5. Evidence/QoS/Lab/comparison

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| E01 | Metric stale/gap | Không đổi thành 0/PASS |
| E02 | Mapping/incarnation đổi sau scrub | Re-evaluate/invalidate evidence |
| E03 | QoS/Lab disabled | Production vẫn complete được |
| E04 | Warp/fio chỉ có endpoint metric | SERVICE_ONLY |
| E05 | QoS runner fail | Verdict riêng; không ghi đè operation_result |
| E06 | Lab một PG PASS | Ghi đúng scope, không cluster PASS |
| E07 | PA2 Lab chỉ có một lượt | INCOMPLETE/NOT_EXERCISED theo mục tiêu |
| E08 | Hai run khác workload/topology/budget | NOT_COMPARABLE có reason |
| E09 | UI cố gửi PASS/role | Backend từ chối/bỏ qua và tự tính |

### 22.6. Fault/security

- PostgreSQL restart giữa transaction/outbox publish.
- Backend/worker restart giữa action.
- Executor/SSH disconnect sau khi command đã gửi.
- OSDMap đổi giữa plan và execute.
- Recovery/backfill bắt đầu trong admission.
- Prometheus counter reset hoặc mất scrape.
- External operator đổi mapping/affinity/service spec.
- Duplicate idempotency key cùng/khác fingerprint.
- Lease hết nhưng old worker vẫn chạy.
- Command/path/header injection và oversized artifact.
- Secret xuất hiện trong command output/error; redaction loại bỏ trước persist/response.

### 22.7. Image và deployment acceptance

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| I01 | Build từ release source/lockfiles trên platform được hỗ trợ | Có image digest, version/commit, SBOM, manifest/checksums và test evidence |
| I02 | Chạy từng role; role sai; gửi SIGTERM/restart | Whitelist role, role sai fail; graceful stop, lease/fence/reconcile ngăn double action |
| I03 | Cài trên máy Linux chỉ có runtime và release bundle | Không cần source checkout, compiler, pip/npm/apt hoặc build ở đích |
| I04 | Deploy lab A và hệ thống B khác FSID/topology/profile | Cùng application digest trên cùng architecture; inventory/list OSD đúng scope, không rebuild |
| I05 | Upgrade-only không RGW/QoS/Lab; legacy-only | Role chỉ đòi dependency của feature bật; disabled hiển thị rõ, readiness không gọi RGW bắt buộc |
| I06 | Fresh DB và upgrade từ các schema được manifest hỗ trợ | Migrate one-shot có lock; API/worker chỉ ready khi schema tương thích, giữ dữ liệu cũ |
| I07 | Recreate app/executor và restart DB | DB, evidence/hash/plan binding và executor state vẫn tồn tại, không reset |
| I08 | Backup/restore DB + evidence; quay về app cũ | Restore nhất quán; app chỉ chạy với schema tương thích; không auto downgrade DB/Ceph |
| I09 | FSID sai, host key đổi, collector thiếu/sai hash/version | Block truy cập/mutation liên quan với reason; không nhận snapshot như hợp lệ |
| I10 | Kiểm image layers/history, logs và API evidence | Không secrets/lab state; non-root, role isolation, không Docker socket/privileged/host-root mount |
| I11 | Offline sau khi đã load đủ image/bundle; chặn Internet | Startup/migrate/read-only collection qua mạng lab được phép; không pull/runtime install |
| I12 | DB unavailable, optional metrics down, disk evidence đầy | Health theo dependency/feature; evidence-write failure chặn action cần audit; không ghi PASS giả |
| I13 | UI route refresh, API, SSE/WebSocket, upload/download | Same-origin routing hoạt động; limits/timeouts/auth giữ contract legacy |
| I14 | External DB/executor hoặc platform chưa hỗ trợ | Endpoint/protocol/capability được kiểm; unsupported trả rõ, không quảng cáo tương thích chung |

### 22.8. Inventory/UI hợp nhất

- Collect OSD subset/toàn allowlist; wrong FSID, output quá lớn, timeout, stale/missing fields fail theo contract.
- Reopen/reload plan giữ đúng source/destination/order; xem inventory không tự đổi plan hoặc OSD role.
- Snapshot bind hash/time/coverage và refresh trước drain/từng down-set; artifact cũ bất biến.
- Verify LVM/physical paths, v1/v2 addresses, available/used%, config-diff và cluster-context projection; UNKNOWN không thành 0.
- Compare BEFORE/AFTER_START/AFTER_STABLE đúng OSD/incarnation/process epoch; counter reset/gap không thành hiệu năng giả.
- Raw evidence chỉ qua endpoint verified/redacted; mutation vẫn BLOCKED khi chỉ có read-only down-set assessment.

---

## 23. Definition of Done

### 23.1. Kiến trúc và portability

- [ ] Module boundaries/ports được enforce bằng import/contract tests.
- [ ] Core domain chạy với fake adapters.
- [ ] Một build artifact chạy trên ít nhất hai lab profile chỉ bằng config.
- [ ] Wrong FSID/profile mismatch chặn mutation.
- [ ] Run giữ config/policy/profile snapshot đã redact và hash.
- [ ] Không có lab-specific constant trong application logic.

### 23.2. Production PA1/PA2

- [ ] PA1 kiểm isolation up/acting, digest, return replica, deep-scrub coverage, restore và stable window.
- [ ] PA2 kiểm U/D, chain dependency, từng handoff group, source upgrade, spare rotation, end state và version coverage.
- [ ] Pause/resume/retry luôn reconcile actual state.
- [ ] UI không quyết PASS.
- [ ] Operational rollback có safe-to-destroy và replacement evidence riêng.
- [ ] Không mở BlueStore mới bằng binary cũ.

### 23.3. QoS/Lab/report

- [ ] QoS và Lab bật/tắt độc lập.
- [ ] Phase/cohort/proof/freshness/gap được lưu đúng.
- [ ] Report tách operation/QoS/Lab/rollback result.
- [ ] Spare cuối chưa kiểm ghi NOT_EXERCISED.
- [ ] Comparison không default/winner/score và trả NOT_COMPARABLE khi scope lệch.

### 23.4. Legacy

- [ ] RGW/RBD/API/schema hiện có không regression.
- [ ] Legacy functions được tổ chức dưới module/nav rõ ràng, không bị xóa.
- [ ] Legacy Capacity Guard vẫn enforce workload safety.
- [ ] Legacy helper PASS không được dùng làm production gate.
- [ ] Tắt legacy không làm core lỗi và ngược lại.

### 23.5. Operations/security

- [ ] `.env.example` đầy đủ; `.env` ignored và không có secret trong git/log/API/evidence thường.
- [ ] SSH host identity và FSID được pin/check.
- [ ] Mutation disabled mặc định, có explicit rollout gate.
- [ ] Idempotency, lease/fencing, outbox và crash recovery tests đạt.
- [ ] Emergency stop, cleanup, DB/evidence backup và operational rollback đã rehearsal.
- [ ] Mục chưa chạy ghi `NOT_RUN`/`NOT_EXERCISED`, không tự đánh PASS.

### 23.6. Image release và triển khai lại

- [ ] Một application OCI image immutable; cùng digest cho các role, tách khỏi Ceph target image.
- [ ] Bản release không cần source/build ở đích, có registry artifact và offline bundle.
- [ ] Config/profiles/secrets nằm ngoài image; schema/feature validation fail closed.
- [ ] DB, evidence, executor state bền vững; migrate/backup/restore/app rollback có evidence.
- [ ] Remote collector cài path được duyệt, version/hash và SSH host identity được xác minh.
- [ ] Cùng image được kiểm trên hai môi trường thực thuộc support matrix; fixture test không thay nghiệm thu triển khai.
- [ ] Image/container/config/health/security tests I01–I14 đạt trong phạm vi feature/platform công bố; case chưa chạy ghi NOT_RUN.
- [ ] Manifest công bố rõ read-only/dry-run/live feature status, known limits và evidence path.

### 23.7. OSD Info Collector và UI

- [ ] Giữ đủ host/IP/device/capacity/PG/primary/config/quality, không suy missing thành 0.
- [ ] Snapshot/hash/FSID bind vào plan; refresh và coverage trước drain/từng down-set.
- [ ] Danh sách OSD nguồn/đích đã lưu có role/order/binding, survive reload và container recreate.
- [ ] Before/after/config diff và raw evidence verified/redacted truy cập được theo quyền.

**Hai mức nghiệm thu:** release packaging read-only/dry-run được đóng khi đạt DoD áp dụng và công bố phần live chưa sẵn sàng. Toàn bộ sản phẩm chỉ hoàn tất khi cả DoD production, QoS/Lab, legacy và operations thuộc phạm vi đã cam kết đều có evidence; không đánh dấu toàn plan DONE vì image build thành công.

---

## 24. Cấu trúc thư mục đích đề xuất

Đây là hướng refactor, không yêu cầu di chuyển toàn bộ trong một PR:

```text
rgw-console/
  backend/app/
    platform/
      config/
      db/
      events/
      idempotency/
      leases/
    modules/
      cluster_profiles/
      sessions/
      cluster_inventory/
      upgrade_common/
      upgrade_pa1/
      upgrade_pa2/
      replica_validation/
      rollback/
      qos_observer/
      lab_validation/
      evidence_reporting/
      legacy_rgw/
      legacy_rbd/
      legacy_workload_capacity/
    adapters/
      ceph_cli_ssh/
      cephadm_ssh/
      prometheus/
      warp/
      fio/
      rgw_s3/
      rbd_executor/
      artifact_store/
  frontend/src/
    app/
    shared/
    features/
  rbd-console/              # executor hiện có; refactor tương thích
  config/
    policies/
    profiles/
  .env.example
  packaging/
    Dockerfile             # application image; build context là code/
    entrypoint.sh          # allowlist role, exec đúng process
  deploy/
    compose.release.yml    # image/digest only; DB tùy chọn
    env/
      console.env.example
    profiles/
      lab-a.yaml.example
      lab-b.yaml.example
    collector/             # install/verify assets, không chứa secrets
  release/
    manifest.example.json
    bundle/                # output generated/ignored, không commit runtime data
  docs/
    deployment.md
    offline-install.md
    backup-restore.md
  tests/container/
```

Sibling `code/osd-info-collector/` tiếp tục là source canonical của collector, không chép thành một bản source độc lập trong executor. Build context `code/` chỉ COPY các path allowlist; Docker ignore tương ứng loại dữ liệu/secrets ngoài scope.

---

## 25. Thứ tự PR/lát cắt tiếp theo

Các PR dưới đây là đề xuất công việc, không phải PR đã tạo. Bỏ qua phần đã có evidence đạt; không viết lại foundation đang hoạt động.

1. **Baseline/gap lock:** đối chiếu code/tests/migrations `0001`–`0019`, giữ legacy và saved OSD plan list; cập nhật status matrix.
2. **I0 — Deployment config contract:** canonical Python/Node config, feature-aware dependencies/health, secrets, supported targets và remote collector verification.
3. **I1 — Unified image:** build stages, role entrypoint, static routing, non-root, version info và container contract tests.
4. **I2 — Release deployment:** image-only Compose, storage/migrate sequencing, registry/offline bundle, examples/runbooks, persistence/restore tests.
5. **I3-readonly — Two-system acceptance:** cùng digest trên hai profile/môi trường, offline/read-only inventory/dry-run/legacy scope có evidence; có thể phát hành restricted release tại đây.
6. **P4 — PA1 live gates và operational rollback:** hoàn thiện adapter/controller/replica/restore sau shadow/canary approval.
7. **P5 — PA2 live wave/chain/end-state:** giữ ownership/dependency, current-mapping recovery và version coverage.
8. **P6/P7 — QoS providers, Lab và comparison:** hoàn thiện phần còn thiếu, từng feature có acceptance riêng.
9. **P8/I3-live — Fault/security và full release:** test safety/recovery/rollback trong lab được duyệt, công bố support matrix thực tế.

Mỗi PR có compatibility test riêng. Thay đổi kiến trúc/packaging không đi kèm bật live mutation mặc định; triển khai tại lab hoặc publish registry sẽ là hành động riêng sau khi người vận hành cung cấp cấu hình và chấp thuận scope.

---

## 26. Rủi ro và biện pháp kiểm soát

| Rủi ro | Kiểm soát |
|---|---|
| Adapter phụ thuộc output Ceph release | Capability probe + normalized model + fixture theo release |
| Monolith tiếp tục phình | Module boundary/import test; không thêm endpoint mới vào `main.py` monolith |
| Config Python/Node drift | Canonical schema + shared contract + startup comparison |
| Resume trên sai cluster | FSID/profile/config snapshot binding |
| Double mutation sau timeout/crash | Idempotency + lease/fence + actual-state reconcile |
| Evidence PASS giả | Append-only evidence, freshness/quality, backend-computed gate |
| QoS/Lab làm core mong manh | Optional subscriber, circuit breaker, verdict riêng |
| Legacy hỏng trong refactor | Strangler pattern + API/schema/behavior regression suite |
| PA2 cleanup phá dependency | Ownership/disposition/dependent-step ledger |
| Secret lộ qua log/artifact | Secret ref, redaction trước persist/response, security tests |
| Bake IP/FSID/credential vào image | Config runtime + COPY allowlist + scan layers/history; test cùng digest hai profile |
| Recreate làm mất evidence hoặc binding trỏ artifact mất | Persistent volumes + DB/evidence backup cùng checkpoint + hash verification |
| App rollback không tương thích schema | Manifest schema range, expand/contract, backup/restore rehearsal; không auto down migration |
| Một image bị hiểu là một container privileged | Role process riêng, secrets per-role, private executor, không Docker socket/host-root mount |
| Remote collector khác bản trong release | Installer/manifest/hash verification và fail closed |
| Tuyên bố portable cho mọi Ceph/CPU | Support matrix capability/platform dựa trên test, unsupported rõ ràng |

---

## 27. Tài liệu đối chiếu

- [`Storage_Lab_Console_OSD_Validation_and_Benchmark.md`](../Storage_Lab_Console_OSD_Validation_and_Benchmark.md): liên kết chuyển tiếp sau hợp nhất, không còn đặc tả song song.
- [`osd-info-collector/README.md`](./osd-info-collector/README.md): collector độc lập, artifact/schema và giới hạn thực thi.
- [`OSD_Upgrade_Data_Validation_Controller.md`](../OSD_Upgrade_Data_Validation_Controller.md): invariant, state machine, ledger, API và acceptance scenarios.
- [`PA1_PA2_OSD_Upgrade_Strategy.md`](../PA1_PA2_OSD_Upgrade_Strategy.md): semantics PA1/PA2 và so sánh tác động.
- [`PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md`](../PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md): Lab Test trên PG/object hiện có.
- [`rgw-console/README.md`](./rgw-console/README.md): cách chạy và chức năng hiện có.
- [`rgw-console/VALIDATION.md`](./rgw-console/VALIDATION.md): evidence hiện tại và các mục PARTIAL/NOT_RUN.


Các liên kết Ceph dưới đây được giữ từ đặc tả nguồn để đối chiếu thiết kế Pacific; không phải kết quả xác minh live hoặc công bố hỗ trợ release khác:

- [Ceph Pacific — Primary affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity).
- [Ceph Pacific — PG upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/).
- [Ceph Pacific — Scrubbing](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/).
- [Ceph Pacific — PG consistency và repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/).
- [Ceph Pacific — OSD service và replacement](https://docs.ceph.com/en/pacific/cephadm/services/osd/).
- [Ceph Pacific — Safe-to-destroy](https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/#replacing-an-osd).

---

## 28. Container image và triển khai portable

### 28.1. Hợp đồng sản phẩm phát hành

Mục tiêu là **một application OCI image Storage Lab Console**, không phải ảnh minh họa, VM image hoặc Ceph OSD image. Image chứa phần mềm ứng dụng; dữ liệu và danh tính môi trường được cấp lúc chạy.

- Ví dụ tham chiếu release: `<registry>/storage-lab-console:<app-version>@sha256:<digest>`. Đây là placeholder, không phải registry/image đã tồn tại.
- Một image được dùng lại cho nhiều container role; không gom API, workers, executor và PostgreSQL vào một process/container.
- Cùng platform phải dùng đúng một application digest ở lab A và hệ thống B. Không build lại để thay IP/FSID/OSD/pool/credential.
- Nếu sau này phát hành multi-arch, manifest/index digest chung và digest theo platform phải được ghi riêng; không đòi digest amd64 bằng arm64.
- **Console image digest** xác định bản ứng dụng. **Ceph target/rollback image digest** thuộc run policy và chỉ dùng ở workflow OSD tương ứng.
- Release đầu có thể chỉ công bố read-only inventory/dry-run và legacy đã kiểm. PA1/PA2 mutation mặc định tắt; chỉ mở tính năng khi gate/adapter/live acceptance của tính năng đã đạt.

### 28.2. Một image, nhiều role có boundary rõ

MVP chọn API phục vụ frontend assets đã build theo same origin; không cần một frontend image riêng. Không chạy Vite dev server trong release.

| Role trong cùng image | Process/trách nhiệm | Quyền và dữ liệu |
|---|---|---|
| `api` | FastAPI API, static frontend, SPA fallback; giữ API/SSE/WebSocket contract | DB, evidence theo quyền; không SSH key hoặc Docker socket |
| `worker` | Legacy RGW/application jobs hiện có | DB và credential/asset của feature bật |
| `performance-collector` | Metric adapter/aggregation hiện có | DB và telemetry endpoint cấu hình |
| `capacity-collector` | Capacity snapshots/guard input | DB và adapter endpoint được duyệt |
| `rbd-lifecycle-worker` | Điều phối lifecycle job qua executor | DB, executor endpoint/token; không SSH key |
| `executor` | Node service, fixed action schema/SSH adapter | SSH secret + known-host binding, FSID/allowlist, persistent fence/state; network nội bộ |
| `migrate` | One-shot migration tới schema release | DB migration credential riêng; chạy trước API/workers |
| Role mới khi có implementation | Upgrade/QoS/Lab background processing | Thêm whitelist và tests trước khi enable, không map tạm vào shell tùy ý |

Entrypoint nhận role đã whitelist qua argument/typed config, validate rồi `exec` process tương ứng. Role lạ fail ngay; không `eval` command từ env/API. Một process chính/container; graceful shutdown ngừng claim job mới, xử lý lease/fence và reconcile khi restart.

Image có collector script/version manifest để phân phối; collector **thực thi trên host Ceph có CLI/config/quyền phù hợp**, không đòi container API truy cập block device. Chỉ role executor nhận SSH credential. External executor chỉ được thay bằng endpoint cấu hình khi protocol/action schema/version/FSID checks tương thích.

Reverse proxy/TLS ingress của lab là hạ tầng tùy môi trường, không tính là image ứng dụng thứ hai. Khi không có ingress, chỉ bind loopback hoặc mạng quản trị tin cậy theo policy; không publish dashboard không xác thực ra Internet.

### 28.3. Thành phần build và chuỗi cung ứng

Build context là `code/` để lấy được cả `rgw-console/` và `osd-info-collector/`; dùng COPY allowlist và ignore đúng context. Không lấy toàn bộ workspace/corpus làm layer.

1. Frontend build stage dùng lockfile để tạo production assets.
2. Dependency stages dựng Python/Node dependencies theo lock/pin; base images pin digest tại release.
3. Runtime stage chứa Python, Node và thư viện runtime thực sự cần; copy backend, assets, Node executor, nguyên bộ migrations và collector canonical.
4. Không bắt buộc đóng gói Ceph daemon hoặc một Ceph CLI cố định để dùng cho mọi cluster; adapter/remote execution theo capability của môi trường đích.
5. Warp/fio chỉ được bật khi provider và binary/remote runner tương ứng có version/hash được manifest công bố và kiểm thử. Không download/cài thêm khi startup; thiếu runner thì feature `UNSUPPORTED`/disabled.
6. Chạy non-root với UID/GID/volume permissions có contract; root filesystem read-only khi role cho phép, dùng tmpfs hoặc mount riêng cho tmp/runtime.
7. Build tạo SBOM, vulnerability scan/report, image labels version/commit/build time và collector version/hash. Release policy phải xử lý finding trước phát hành, không mặc định scan thành công.
8. Không đưa `.env`, secrets, SSH key, keyring, database dump, log, evidence, corpus hoặc lab profile thật vào image/build context export. Secret build cần thiết dùng cơ chế ephemeral, không ARG/ENV layer.
9. Ghi version info qua API/diagnostic command: app version, commit, config schema, DB schema và collector compatibility; không trả secret/config chưa redact.

Không yêu cầu runtime có compiler, git hoặc package manager để khởi động. Build offline là phạm vi khác: nếu cần phải có dependency mirror/cache riêng; offline deployment chỉ cần bundle đã được build và kiểm chứng.

### 28.4. Runtime config và secrets

Contract mục 6 áp dụng cho mọi role; bổ sung deployment settings được validate/version hóa:

| Nhóm | Giá trị bên ngoài image |
|---|---|
| Release/runtime | Application image reference/digest, service role, ports/base URL, feature flags |
| Cluster | Profile path/revision, cluster ID/expected FSID, executor endpoint, allowed host/OSD/pool/device scope |
| Database | DB endpoint/name/user, TLS mode/CA, secret-file reference; schema compatibility |
| Storage | Evidence root/store endpoint, executor state path, temp path, optional read-only corpus path |
| Identity/security | Authentication/authorization, TLS/ingress, SSH user/key/known-hosts, API/executor tokens |
| Optional providers | RGW/RBD/Prometheus/Warp/fio endpoints, assets, runtime policy và secret refs |

Ví dụ mới dùng placeholder hoặc fixture, không chứa thông tin lab thật. File secrets nằm ngoài git và ngoài image; mount chỉ vào role cần dùng. Chuẩn hóa alias cũ `RBD_*`/`RGW_*` có cảnh báo deprecation và conflict check, không để Python/Node resolve hai token/default khác nhau.

- Không nhét OSD đã chọn vào Dockerfile; selection/binding nằm trong DB theo session/plan/config snapshot.
- Profile upgrade-only phải khởi động không cần RGW access/secret. Optional component hỏng không kéo sập core nhưng phải hiển thị degraded/unavailable rõ.
- Đổi môi trường ưu tiên deployment/DB-volume namespace riêng. Nếu switch profile trên deployment hiện có, run cũ chỉ read/report theo mục 6.5; không resume/mutate sang FSID mới.
- Snapshot và báo cáo chỉ lưu config đã redact/hash; secret rotation không làm mất audit về phiên bản cấu hình.

### 28.5. Persistent storage và network

| Dữ liệu | Nơi giữ | Quy tắc |
|---|---|---|
| PostgreSQL | DB ngoài hệ thống hoặc volume riêng của PostgreSQL container | Không nằm trong application image; backup và retention riêng |
| Evidence/artifacts | Persistent filesystem volume hoặc artifact store đã cấu hình | Writer có quyền ghi; reader theo quyền; giữ hash và liên kết DB |
| Executor state/fencing | Persistent volume riêng | Không reset khi recreate; tránh old worker thực thi trùng sau restart |
| Cluster/policy config | File mount read-only hoặc config service tương thích | Version/hash, không thay đổi âm thầm giữa run |
| Secrets/known-hosts | Secret manager/file mounts với permission hạn chế | Per-role, không copy sang evidence hoặc layer |
| Corpus/test assets | Optional read-only mount hoặc scoped test store | Ghi/xóa chỉ qua feature/run ownership được duyệt |

Backup/restore DB và evidence theo checkpoint nhất quán; kiểm artifact hashes và tham chiếu sau restore. Không có hướng dẫn mặc định xóa volumes khi upgrade/recreate. Evidence disk-full hoặc lỗi persist phải chặn bước yêu cầu audit, không tiếp tục rồi ghi PASS thiếu artifact.

Compose release dùng network riêng/service DNS, không bắt `network: host` hoặc host alias đặc thù máy phát triển. Chỉ publish cổng web cần thiết; executor và DB không publish công khai. Mở outbound tối thiểu tới DB, SSH/HTTP executor, cluster/telemetry/asset endpoints của profile.

Application containers không cần `privileged`, Docker socket hoặc mount host root/block device. Thao tác Ceph/Linux có quyền cao chỉ qua adapter remote đã duyệt, action schema đóng và credential tối thiểu phù hợp; terminal legacy vẫn lab-only với auth/audit/containment.

### 28.6. Remote collector installation và preflight

Bundle phải cung cấp collector từ source canonical, version/schema, SHA-256 và quy trình install/verify. Cài trên host quản trị Ceph được operator duyệt vào fixed path (hiện tại `/opt/storage-lab/collect_osd.py`) hoặc fixed wrapper hỗ trợ môi trường cephadm; không nhận path/command tùy ý từ browser.

Trước collection:

1. Xác minh SSH host key/identity, executor protocol, target host allowlist và expected FSID.
2. Kiểm Python/Ceph CLI/runtime context, quyền read-only cần thiết và collector version/hash.
3. Resolve explicit selected OSD hoặc toàn allowlist, giới hạn timeout/output size.
4. Chạy fixed argv, thu artifact/version/quality và index; không ghi nhận thành công khi script thiếu/sai schema/FSID.
5. Expose diagnostics đã redact để operator xử lý; không tự cài bằng quyền root, overwrite file khác hoặc đổi trust policy trong request collect.

Cài script/credential là bước onboarding riêng, không tự thực thi khi image startup. Upgrade collector phải giữ compatibility và artifact lịch sử; gói image mới không ngầm sửa remote host.

### 28.7. Startup, health, upgrade và rollback ứng dụng

Trình tự release deployment:

1. Validate manifest/checksum/platform, chuẩn bị config/secrets/volumes và network tới các dependency.
2. DB sẵn sàng; chạy role `migrate` one-shot có lock, ghi schema/exit result.
3. API/executor khởi động và kiểm config/schema/identity. Workers chỉ bắt đầu khi dependency thực sự cần đã ready.
4. Chạy preflight read-only, collect inventory, kiểm saved OSD plans/evidence và dry-run trước khi bật workflow đã được release cho phép.
5. Live mutation chỉ mở bằng feature policy + operator scope/approval + đầy đủ safety gates; startup không tự tiếp tục action trên cluster.

Health endpoints là contract mới cần implement/test, không coi `/api/health` gắn S3 hiện tại là đủ:

- Liveness: process/event loop hoạt động; không restart app chỉ vì optional endpoint mất.
- Readiness: config/schema/persistence và dependency bắt buộc theo role/feature hợp lệ.
- Dependency/capability status: phân biệt disabled, degraded, stale, unsupported; UI đọc được lý do HOLD/BLOCKED.
- Executor identity/FSID mismatch chặn action tương ứng; không được dùng readiness xanh để bỏ qua per-action recheck.

Nâng bản app: dừng nhận action mới/pause run → chờ hoặc reconcile in-flight jobs → backup nhất quán → migrate tương thích → thay image bằng digest mới → smoke test → operator resume. Không stop OSD chỉ vì nâng phiên bản Console.

Rollback app chỉ dùng image nằm trong schema compatibility range của release. Migration theo expand/contract, ưu tiên forward fix; khôi phục backup cần quy trình riêng được duyệt và phải reconcile actual Ceph state sau restore. Không tự down-migrate, xóa data hoặc chạy lại ledger cũ. App rollback không phải Ceph rollback và không cho phép chạy binary Ceph cũ trên BlueStore đã nâng.

### 28.8. Release artifacts và offline bundle

Mỗi bản release cần:

- Application image tag immutable/digest, source revision, build/platform metadata; publication vào registry là bước riêng.
- Manifest có config schema, min/max compatible DB schema, collector/executor protocol/hash, supported feature/capability matrix và known limitations.
- SBOM, security scan outcome, checksum của archive/assets, hướng dẫn xác minh digest/chữ ký theo trust policy của nơi nhận.
- `compose.release.yml` chỉ dùng `image:` cùng application digest cho mọi role; profiles/scale cho optional workers. Development Compose có thể giữ build nhưng không dùng làm bộ cài release.
- Env/profile examples và secrets inventory không có credential thật; runbooks install/upgrade/offline/backup-restore/health/troubleshooting.
- Collector install/verify assets và acceptance report có PASS/PARTIAL/NOT_RUN theo từng môi trường.
- Archive ứng dụng ở định dạng loader của runtime hỗ trợ, manifest và lệnh import/load đã kiểm; load xong xác minh image/content digest trước chạy.

Nếu nơi nhận có PostgreSQL phù hợp, dùng endpoint ngoài. Nếu cần DB bundled, release bundle thêm **image PostgreSQL riêng** pin version/digest đã test, volume và health configuration; đây là dependency, không làm thành application image thứ hai. Pin/tải sẵn mọi image hạ tầng được deployment profile chọn.

Offline nghĩa là không cần Internet/registry/package repository lúc cài/chạy, **vẫn cần kết nối mạng lab** tới DB/executor/cluster/telemetry liên quan. Bundle không chứa secret hay dữ liệu cluster. Sau load phải có đường start không tự pull kể cả khi profile gọi digest; kiểm behavior của runtime thực trong I11.

### 28.9. Support matrix và nghiệm thu tái sử dụng

| Lớp | Baseline cần xác nhận | Điều kiện mở rộng |
|---|---|---|
| Host/runtime | Linux amd64, Docker Engine + Compose phiên bản ghi trong release manifest sau test | Podman/Kubernetes/air-gap policy khác có adapter/runbook và acceptance riêng; không mặc định đã hỗ trợ |
| CPU | `linux/amd64` đầu tiên | `linux/arm64` chỉ công bố khi tất cả role/dependencies build và chạy test thực |
| Ceph | Pacific replicated baseline của hai tài liệu gốc | Release/topology khác phải có capability fixture, upgrade-hop và safety/live test tương ứng |
| DB | PostgreSQL version/schema/TLS mode đã test và pin | External DB cùng supported range; không suy mọi PostgreSQL version tương thích |
| Executor/collector | Protocol/schema/version/hash trong manifest | External service chỉ khi compatibility preflight đạt |
| Feature | Read-only/dry-run/legacy và live capabilities được ghi riêng | Feature chưa kiểm giữ disabled/UNSUPPORTED/NOT_RUN, không hứa full production |

Nghiệm thu portable bắt buộc dùng hai môi trường khác cấu hình (FSID/hosts/pools/topology) với cùng application digest trên cùng platform, không sửa source và không rebuild. Ghi lại: manifest/digest, config hash đã redact, startup/migration/health, remote collector verification, inventory và danh sách OSD plan, evidence persistence/recreate, backup/restore và phạm vi smoke tests.

Một môi trường mô phỏng thứ hai có ích cho CI nhưng không đủ thay nghiệm thu triển khai trên hệ thống thứ hai. Khi chưa có quyền truy cập lab/hệ thống đích, ghi `NOT_RUN` và liệt kê điều kiện cần; không chạy live mutation hoặc publish image thay người vận hành.

---

Tài liệu này là kế hoạch triển khai. Mọi command, threshold, target image, OSD selection và estimate phải được resolve từ cluster profile, run policy và inventory thực trước mutation. Unit/integration test không được trình bày như live evidence PA1/PA2 nếu chưa chạy đúng workflow trên cluster lab được phê duyệt.
