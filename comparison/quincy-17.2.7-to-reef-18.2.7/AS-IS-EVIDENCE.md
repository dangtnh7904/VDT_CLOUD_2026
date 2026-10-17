# Hồ sơ thu evidence As-Is cho Quincy 17.2.7 → Reef 18.2.7

**Trạng thái ngày 12/10/2026: 24/24 nhóm evidence `NOT_CAPTURED`.** Đây là biểu mẫu read-only để xác định applicability và baseline trước khi chạy [52 gate lab/runtime](./LAB-RUNTIME-GATES.md). [Runbook capture](./AS-IS-CAPTURE-RUNBOOK.md) cung cấp collector plan-first và bundle validator cho một phần register; chưa có lệnh nào dưới đây được chạy trên cluster. Tài liệu không phải approval truy cập hay thay đổi production.

## Guardrail thu thập

- Tạo một `run_id`, thư mục archive bất biến và file `MANIFEST.sha256`; mọi output ghi UTC timestamp, hostname, user/role và exit code.
- Chỉ chạy lệnh đọc. Không thêm `--refresh`, không apply spec/config, không restart/redeploy, không set release floor và không chạy zap/repair/migrate.
- Redact tại nguồn access key, secret key, token, private key, credential registry/KMS, endpoint có embedded credential và dữ liệu người dùng. Giữ bằng chứng rằng field tồn tại nhưng không giữ giá trị thô.
- Với output lớn, lưu file thô trong kho evidence hạn chế quyền và chỉ đưa checksum/summary vào hồ sơ comparison.
- Lệnh là khung tối thiểu; operator phải xác nhận syntax trên đúng CLI 17.2.7 và quyền read-only trước khi chạy. Exit code khác 0 là evidence cần xử lý, không được bỏ qua.

## Register As-Is

| ID | Phạm vi | Thu thập read-only đề xuất | Artifact/tiêu chí tối thiểu | Mở khóa gate | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| AS-001 | Exact artifacts | Ghi package repository snapshot, NEVRA/version, container image digest, cephadm binary checksum, SBOM và build flags | Manifest base/target truy ngược tới `b12291d110049b2f35e32e0de30d70e9a4c060d2` và `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`; không dùng floating tag | `LAB-001`, `LAB-004`, `LAB-006`, `LAB-051` | NOT_CAPTURED |
| AS-002 | Cluster baseline | `ceph status -f json-pretty`<br>`ceph health detail -f json-pretty`<br>`ceph df detail -f json-pretty` | Health, capacity, pool/PG counts và warning baseline cùng timestamp | `LAB-004`, `LAB-023`, `LAB-030`, `LAB-054` | NOT_CAPTURED |
| AS-003 | Version coverage | `ceph versions -f json-pretty`<br>`ceph orch ps -f json-pretty` | Version, host, daemon ID, status, container image ID/digest của mọi daemon | `LAB-004`, `LAB-012`, `LAB-052` | NOT_CAPTURED |
| AS-004 | MON/quorum | `ceph quorum_status -f json-pretty`<br>`ceph mon dump -f json-pretty` | Quorum members, rank, election epoch, feature/release state và MON addresses | `LAB-010`, `LAB-011`, `LAB-052`, `LAB-053` | NOT_CAPTURED |
| AS-005 | OSD/CRUSH topology | `ceph osd dump -f json-pretty`<br>`ceph osd tree -f json-pretty`<br>`ceph osd crush dump -f json-pretty` | OSD in/up state, release flags, CRUSH class/rule/failure domain và pool mapping | `LAB-015`, `LAB-020`, `LAB-021`, `LAB-053` | NOT_CAPTURED |
| AS-006 | OSD backend/device | `ceph osd metadata -f json-pretty`<br>`ceph device ls -f json-pretty` | Backend, BlueStore DB/WAL paths, device IDs/classes, rotational/encryption signals; FileStore count rõ ràng | `LAB-002`, `LAB-007`, `LAB-025`, `LAB-026`, `LAB-027`, `LAB-028` | NOT_CAPTURED |
| AS-007 | Effective configuration | `ceph config dump -f json-pretty`<br>`ceph config show-with-defaults <representative-daemon> -f json-pretty` | Stored overrides và effective values cho daemon đại diện từng role/device class; secret redacted | `LAB-010`, `LAB-022`, `LAB-042`, `LAB-047` | NOT_CAPTURED |
| AS-008 | Orchestrator hosts/specs | `ceph orch host ls --detail -f json-pretty`<br>`ceph orch ls --export` | Host labels/status, placement, unmanaged/managed state và service specs có checksum | `LAB-003`, `LAB-012`, `LAB-014`, `LAB-015`, `LAB-019` | NOT_CAPTURED |
| AS-009 | Container provenance | `ceph orch ps -f json-pretty` và inspect read-only trên từng container runtime host | Runtime, image ID/digest, command, mounts và package payload của từng daemon cohort | `LAB-001`, `LAB-012`, `LAB-017`, `LAB-019` | NOT_CAPTURED |
| AS-010 | MGR state/modules | `ceph mgr dump -f json-pretty`<br>`ceph mgr module ls -f json-pretty`<br>`ceph mgr services -f json-pretty` | Active/standby, enabled/always-on modules, endpoints và persisted-state backup reference | `LAB-003`, `LAB-013`, `LAB-016`, `LAB-018` | NOT_CAPTURED |
| AS-011 | Monitoring | Export Prometheus target/rule status, Grafana dashboard revisions và Alertmanager routes bằng API read-only | Target health, scrape gaps, required series/labels, alert route và dashboard checksums | `LAB-016`, `LAB-017`, `LAB-022`, `LAB-048` | NOT_CAPTURED |
| AS-012 | PG/recovery/scrub baseline | `ceph pg stat -f json-pretty`<br>`ceph osd perf -f json-pretty`<br>`ceph osd df tree -f json-pretty` | PG state, recovery/backfill, scrub schedule/history, per-OSD latency/utilization và existing outliers | `LAB-021`, `LAB-022`, `LAB-023`, `LAB-024` | NOT_CAPTURED |
| AS-013 | ceph-volume inventory | Trên từng OSD host chạy `ceph-volume inventory --format json` trong đúng Quincy container/package | Raw device/LV/mapper/multipath inventory có host mapping; tuyệt đối không thêm zap/prepare/activate | `LAB-015`, `LAB-028`, `LAB-029` | NOT_CAPTURED |
| AS-014 | RADOS/RBD footprint | `ceph osd pool ls detail -f json-pretty`<br>`rbd pool stats --format json` trên từng pool RBD đã xác định | Pool type/features, namespace, image/snapshot/mirror/cache/encryption applicability và consumer owner | `LAB-031`, `LAB-032`, `LAB-033`, `LAB-034`, `LAB-035` | NOT_CAPTURED |
| AS-015 | Client estate | Inventory package/kernel/SDK và mount/map method từ CMDB hoặc host read-only query | Cohort matrix client version, OS/kernel, library/binding, workload owner và compatibility deadline | `LAB-005`, `LAB-031`, `LAB-035`, `LAB-036` | NOT_CAPTURED |
| AS-016 | CephFS/MDS | `ceph fs dump -f json-pretty`<br>`ceph fs status -f json-pretty`<br>`ceph mds stat -f json-pretty` | Filesystem/rank/standby, client feature/session summary, subvolume/NFS/mirror/schedule applicability | `LAB-036`, `LAB-037`, `LAB-038`, `LAB-039`, `LAB-040`, `LAB-041` | NOT_CAPTURED |
| AS-017 | RGW topology | Dùng `radosgw-admin` read-only để lấy realm, period, zonegroup, zone và service placement; redact system keys ngay khi capture | Realm/zone IDs, endpoints, master roles, sync policy, frontend và resolved topology không chứa credential thô | `LAB-019`, `LAB-042`, `LAB-044`, `LAB-047` | NOT_CAPTURED |
| AS-018 | RGW data features | Inventory bucket versioning/lock/encryption/quota/lifecycle/notification/multisite theo sampling plan đã duyệt | Feature/applicability matrix, volume/cardinality và owner; không archive object payload người dùng | `LAB-043`, `LAB-045`, `LAB-046`, `LAB-048`, `LAB-050` | NOT_CAPTURED |
| AS-019 | External integrations | Inventory load balancer, DNS/TLS, KMS/Vault, LDAP/Keystone, Kafka/AMQP/webhook, NFS và SIEM contracts | Endpoint/schema/SLO/owner/certificate expiry; credential chỉ ghi reference và trạng thái redaction | `LAB-017`, `LAB-019`, `LAB-046`, `LAB-047`, `LAB-049` | NOT_CAPTURED |
| AS-020 | Host/runtime compatibility | Thu OS release, kernel, CPU arch/features, container runtime, time sync, free space/inode và package repo state từng host | Host matrix và incompatibility/blocker rõ; command output có hostname/timestamp | `LAB-001`, `LAB-002`, `LAB-014`, `LAB-051` | NOT_CAPTURED |
| AS-021 | Snapshot/restore capability | Ghi loại snapshot/backup hiện có cho MON/MGR, OSD clone, CephFS metadata, RGW metadata và host VM | Restore owner, RPO/RTO, checksum, retention và lần restore test gần nhất; không coi backup chưa restore là đủ | `LAB-003`, `LAB-025`, `LAB-037`, `LAB-050`, `LAB-053` | NOT_CAPTURED |
| AS-022 | Workload/SLO baseline | Thu workload mix, throughput, latency percentile, error rate, recovery budget và maintenance window từ nguồn hiện có | Baseline có khoảng thời gian/nguồn query và stop threshold được owner phê duyệt | `LAB-022`, `LAB-023`, `LAB-033`, `LAB-042`, `LAB-054` | NOT_CAPTURED |
| AS-023 | Existing incidents/exceptions | Export read-only active health mute, known issue, capacity risk, failed daemon/device và waiver còn hiệu lực | Mỗi pre-existing issue có owner, expiry và cách phân biệt với regression do upgrade | `LAB-002`, `LAB-004`, `LAB-054` | NOT_CAPTURED |
| AS-024 | Evidence index/sign-off | Lập index file gồm run ID, artifact path, SHA-256, collector, timestamp, redaction review và owner approval | Không thiếu evidence P0, checksum kiểm được và quyền truy cập archive đã thử | `LAB-054` | NOT_CAPTURED |

## Điều kiện chuyển sang lab/canary

Không bắt đầu exact-hop run cho đến khi AS-001→007, AS-020→024 được capture hoặc có blocker/waiver do đúng owner ký. Các mục dịch vụ AS-014→019 chỉ có thể `NOT_APPLICABLE` sau khi evidence As-Is chứng minh không dùng; thiếu quyền hoặc không tìm thấy owner là `BLOCKED`, không phải `NOT_APPLICABLE`.

Sau khi capture, cập nhật status thành `CAPTURED`, `BLOCKED` hoặc `NOT_APPLICABLE`, thêm đường dẫn evidence/checksum bên cạnh register hoặc trong evidence index. Không đổi trạng thái runtime gate trong `LAB-RUNTIME-GATES.md` nếu mới chỉ thu inventory.
