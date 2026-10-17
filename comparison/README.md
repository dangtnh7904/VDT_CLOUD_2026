# Comparison tổng — Thay đổi phiên bản và việc cần làm trước nâng cấp

**Cập nhật 13/10/2026.** Đầu mối comparison của dự án. Mục tiêu là trả lời **bản mới thay đổi gì; điều gì phải sửa, thay thế hoặc bỏ trước khi lên; điều gì tự có hiệu lực khi restart; cần kiểm gì lúc mixed-version và sau nâng**. Các cặp MD/CSV giữ bằng chứng chi tiết, không gom mất inventory đã review.

[Plan tổng PA2](../plan-tổng.md) · [Console](../code/README.md) · [Benchmark](../benchmark/README.md).

## 1. Các hop đang xử lý

| Hop | Nguồn chính | Trạng thái sử dụng |
|---|---|---|
| H1: 16.2.5 → 16.2.15 | [README H1](pacific-16.2.5-to-16.2.15/README.md), [quality 127/127](pacific-16.2.5-to-16.2.15/FINDING-QUALITY-STATUS.md), [20 As-Is](pacific-16.2.5-to-16.2.15/AS-IS-EVIDENCE.md), [20 actions](pacific-16.2.5-to-16.2.15/UPGRADE-ACTION-REGISTER.md), [16 test packs](pacific-16.2.5-to-16.2.15/RUNTIME-TEST-SELECTION.md), [decision](pacific-16.2.5-to-16.2.15/GO-NO-GO-REGISTER.md) | Source/binary `2.665/2.665`; 85 gate phủ đủ; finding quality strict 127/127; As-Is/pins/actions/test/runtime còn mở; decision `NOT_READY_FOR_DECISION` |
| H2: 16.2.15 → 17.2.7 | [README H2](pacific-16.2.15-to-quincy-17.2.7/README.md), [quality 44/441](pacific-16.2.15-to-quincy-17.2.7/FINDING-QUALITY-STATUS.md), [20 As-Is](pacific-16.2.15-to-quincy-17.2.7/AS-IS-EVIDENCE.md), [20 actions](pacific-16.2.15-to-quincy-17.2.7/UPGRADE-ACTION-REGISTER.md), [15 test packs](pacific-16.2.15-to-quincy-17.2.7/RUNTIME-TEST-SELECTION.md), [decision](pacific-16.2.15-to-quincy-17.2.7/GO-NO-GO-REGISTER.md) | Source/binary 4.179/4.179; 43 gate phủ đủ; quality còn 397 gap; As-Is/pins/actions/test/runtime còn mở; decision `NOT_READY_FOR_DECISION` |
| H3: 17.2.7 → 18.2.7 | [README H3](quincy-17.2.7-to-reef-18.2.7/README.md), [plan](PLAN-quincy-17.2.7-to-reef-18.2.7.md), [24 nhóm As-Is](quincy-17.2.7-to-reef-18.2.7/AS-IS-EVIDENCE.md), [52 runtime gates](quincy-17.2.7-to-reef-18.2.7/LAB-RUNTIME-GATES.md), [runtime evidence template](quincy-17.2.7-to-reef-18.2.7/RUNTIME-EVIDENCE-MANIFEST.template.json), [19 test packs](quincy-17.2.7-to-reef-18.2.7/RUNTIME-TEST-SELECTION.md), [12 pins](quincy-17.2.7-to-reef-18.2.7/EXACT-HOP-PINS.md), [34 actions](quincy-17.2.7-to-reef-18.2.7/UPGRADE-ACTION-REGISTER.md), [decision](quincy-17.2.7-to-reef-18.2.7/GO-NO-GO-REGISTER.md) | Source/binary 4.434/4.434; finding quality 188/188; native graph 33 YAML + 17 symlink sạch; As-Is `NOT_CAPTURED`; pins/actions `PENDING_INPUT`; test/runtime `NOT_RUN`; decision `NOT_READY_FOR_DECISION` |

Không chép verdict giữa các hop. H2 và H3 đều là net diff giữa hai release branch; base không là ancestor của target. Giữ exact endpoint SHAs/provenance tại README từng hop; major mới hơn không tự bảo đảm chứa mọi backport cuối nhánh của release trước.

## 2. Kế thừa checklist đúng phần

Kế thừa từ checklist H1: applicability → As-Is → changes/actions → gates/tests → rollout/STOP → rollback boundary → evidence/sign-off. Giữ finding IDs, nguồn code và test để trace.

**Phần bị thay thế:** checklist cũ định nghĩa PA2 bằng drain weight và có nhánh PA1/H0. Luồng hiện hành là X→S, nâng X; Y→X, nâng Y theo plan tổng, có deep-scrub toàn set trước chuyển và deep-scrub lại sau hội tụ từng group. G14–G16, T30–T38, R3A/R3B/R3H và yêu cầu H0/100 TB cũ là thiết kế lịch sử; không tự trở thành gate PA2 hiện tại. H0-guided repair/enforcement không phải chức năng native đã kiểm chứng. G00–G13/T00–T29 cũng chỉ được áp dụng sau khi xác định điều kiện và artifact của H1; không tự PASS hoặc áp sang H2.

## 3. Mỗi finding phải trả lời

| Trường | Câu hỏi cần đóng |
|---|---|
| Identity/evidence | Hop, owner report, finding ID, endpoint SHA, symbol/hunk/commit/test nào chứng minh? |
| Before → after | Hành vi nguồn khác đích ở đâu, có phải fix còn tồn tại ở endpoint hay đã revert? |
| Applicability | Pool/client/feature/config/deployment nào kích hoạt? YES/NO/UNKNOWN và bằng chứng As-Is? |
| Activation | Tự đổi khi deploy/restart, chỉ khi explicit override, đổi feature/release floor hoặc chạy tool? |
| Chuẩn bị | Cần sửa/bỏ/chuyển key, API, automation, client, dependency hoặc artifact gì trước first target process? |
| Mixed-version | Old/new primary, MGR/MON, client/daemon hoặc persisted state cùng tồn tại gây khác biệt gì? |
| Sau nâng | Có việc opt-in/aftercare nào; điều gì không tự sửa dữ liệu cũ? |
| Boundary | Last reversible point, store/control-state/features ảnh hưởng recovery thế nào? |
| Test/bench | Scenario/expected/fail signal, gate, profile, evidence và owner nào? |
| Closure | PENDING/READY/BLOCKED/N_A/VERIFIED; evidence của bước nào, thời gian/scope nào? |

READY chỉ là đủ chuẩn bị cho phase, không runtime PASS. N_A cần bằng chứng không áp dụng. UNKNOWN ở prerequisite chặn phase tương ứng. Các nhãn action khác với `upgrade_impact=affect|trivial` của CSV.

## 4. Những việc H1 phải audit trước nâng

Danh sách dưới **kế thừa finding/checklist đã có**, không phải review source mới hoặc lệnh xóa config. Chỉ thực hiện khi applicability đúng; giữ snapshot/config cũ để phục hồi và kiểm cả binary nguồn/đích trong mixed phase.

### 4.1. Key cũ cần sửa hoặc bỏ

| Key nguồn | Target/action cần chuẩn bị | Bằng chứng |
|---|---|---|
| `osd_mclock_max_capacity_iops` | Bỏ key generic; map sang key _hdd/_ssd theo media nếu dùng mClock; kiểm benchmark policy | [Config H1](pacific-16.2.5-to-16.2.15/06-config-defaults.md), checklist §4.1 |
| `mds_max_retries_on_remount_failure` | Chuyển sang `client_max_retries_on_remount_failure` khi dùng CephFS; test remount | Cùng nguồn |
| `ms_async_max_op_threads` | Target bỏ; sửa automation, không map mù sang `ms_async_reap_threshold` | Cùng nguồn |
| `rgw_rados_pool_pg_num_min` | Bỏ phụ thuộc trong automation tạo pool; không suy pool hiện hữu tự đổi | Cùng nguồn |
| `rgw_bucket_quota_soft_threshold` | Audit quota semantics/runbook, bỏ key không còn được hỗ trợ đúng thời điểm | Cùng nguồn |
| `rbd_persistent_cache_log_periodic_stats` | Sửa monitoring/runbook; bỏ key không đồng nghĩa tắt cập nhật cache state | Cùng nguồn |

Mỗi key ghi current stored/effective value, nơi sử dụng, owner, replacement, thời điểm áp dụng, restart cần thiết và test. Không xóa hàng loạt trước khi thử config mixed/failback.

### 4.2. Thay đổi hành vi và chuẩn bị có điều kiện

| Chủ đề | Việc trước restart/rollout liên quan | Kiểm trong/sau và nguồn |
|---|---|---|
| Default/backpressure/mClock | Chốt scheduler/media, override chủ đích, recovery/client budget; không đổi WPQ chỉ vì có mClock | Latency/memory/recovery và effective config; [01](pacific-16.2.5-to-16.2.15/01-osd-pg-recovery.md), [06](pacific-16.2.5-to-16.2.15/06-config-defaults.md) |
| BlueFS/DB-WAL/device | Audit alloc size/alignment, device ownership/alias và activation; chốt boundary store trước dùng target | Replay/restart, I/O errors, nguồn phục hồi; [02](pacific-16.2.5-to-16.2.15/02-bluestore-bluefs.md), [03](pacific-16.2.5-to-16.2.15/03-rocksdb-block-device.md), [09](pacific-16.2.5-to-16.2.15/09-ceph-volume-activation.md) |
| MGR/monitoring | Custom notify subscriptions, parser Prometheus, alert routes, Dashboard TLS/client phải tương thích | Failover/scrape/parser/alerts thực; report nêu duplicate HELP/TYPE cần disposition, không giả có workaround config; [07](pacific-16.2.5-to-16.2.15/07-mgr-modules-monitoring.md) |
| Cephadm/control state | Chốt migration_current 2→5 và rollback trước target active; MGR bridge cho staggered; verify registry từng host | Orchestrator reconciliation, đúng daemon/count, MDS prep/cleanup nếu dùng; [08](pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md) |
| Package/tool delivery | Nếu direct RPM, rehearsal scriptlet base có thể xóa cephadm user/home/key; custom build/DEB kiểm dependencies; CLI/dencoder đồng bộ | Artifact/privilege/service startup thật; [13](pacific-16.2.5-to-16.2.15/13-build-packaging-submodules.md), [15](pacific-16.2.5-to-16.2.15/15-upgrade-validation.md) |
| RBD/PWL/client | Cache SSD layout cũ không tự compatible; xác minh clean/empty và procedure đã thử trước nâng client | Fast-diff/journal/mirror/lock theo feature; không tự discard dirty cache; [10](pacific-16.2.5-to-16.2.15/10-rados-rbd-clients.md) |
| RGW/auth/TLS/Vault | Audit client/proxy TLS, CephX/secure MON, CA Vault; Browser POST closure theo từng serving daemon | PUT/GET/checksum/multipart/auth, negative policy test, multisite nếu dùng; [12](pacific-16.2.5-to-16.2.15/12-rgw.md), [14](pacific-16.2.5-to-16.2.15/14-security-cross-reference.md) |
| CephFS/Manila nếu dùng | Key remount, perf schema, rank/standby-replay; path-cap audit theo lịch sử cluster | Session/remount/replay/eviction và caps, không suy nâng binary thu hồi cap cũ; [11](pacific-16.2.5-to-16.2.15/11-cephfs-mds.md) |

Chi tiết đầy đủ ở checklist §3–6 và report owner. Bảng tổng chỉ hướng tới hành động, không thay bằng chứng code hoặc runbook chuyên biệt.

## 5. Cách hoàn thiện H2

- Giữ master inventory và các classification/finding đã review; tiếp tục phần còn thiếu theo plan H2, gồm packaging/submodule, validation/cross-reference và closure còn mở.
- Chốt đủ mỗi component: `affect + trivial = total`; mọi affect có finding, applicability và action/test; không dùng churn/P0 làm mức rủi ro.
- Rà theo chủ đề đang có: scheduler/mClock và config, BlueStore/BlueFS/format, MON feature/release checkpoints, MGR/metrics/SQLite, cephadm/activation, RBD/client/cache/ABI/backport, RGW/auth/backend/multisite, CephFS và delivery.
- Với removed option/API/backend, chỉ điền thay thế sau khi xác minh endpoint và deployment đang dùng. Không dùng danh sách removed H1 như danh sách của Quincy.
- Xuất checklist H2 theo cấu trúc mục 3/6/7, map finding H2 → action trước nâng → mixed/post tests → benchmark → evidence. Mục chưa review ghi PENDING/UNKNOWN.
- Đường H2 cần lab/canary riêng trên đúng 16.2.15→17.2.7; không lấy kết quả H1 thay thế.

## 6. Action register dùng chung

Mẫu này được điền trong hồ sơ từng hop/change; không có PASS mặc định.

| Action ID | Hop/finding/link | Điều kiện + evidence As-Is | Việc sửa/bỏ/chấp nhận | Deadline phase | Test/gate/bench | Owner | Status + evidence |
|---|---|---|---|---|---|---|---|
| H1-CFG-01 | CFG finding theo report 06 | UNKNOWN — kiểm mClock/media/key thực | Quyết replacement generic capacity | Trước first target OSD | Config/canary/scheduler profile | Chưa gán | PENDING |
| H1-OBS-01 | MGR-005 | UNKNOWN — kiểm exporter/parser đang dùng | Disposition artifact/telemetry | Trước gate dùng Prometheus | Parser + scrape thực | Chưa gán | PENDING |
| H2-ACT-… | Finding H2 đã verify | YES/NO/UNKNOWN có nguồn | Điền sau review | BEFORE/MIXED/AFTER | Scenario ID | Chưa gán | PENDING |

Ba hàng là mẫu chuẩn bị, chưa khẳng định applicability. Console lưu các ID đó cùng plan revision; benchmark lưu finding/tool/profile để truy ngược kết quả.

## 7. Gate theo phase

| Phase | Điều kiện tối thiểu | Evidence |
|---|---|---|
| BEFORE | Artifact/config/client/tool compatibility, applicability, topology/capacity, rollback boundary, telemetry | Snapshot/provenance, action register, config diff, rehearsal và profile benchmark |
| MIXED | Đúng daemon/primary/version, quorum/peering, deep-scrub trước/sau từng lượt PA2 và stop policy | Map/role history, digest, scrub PRE_HANDOFF/POST_HANDOFF có completion riêng, errors, client timeline |
| AFTER | Đủ target coverage, rotated placement/owner, config tạm đã xử lý, stable window, aftercare áp dụng | Version/config inventory mới, ledger closeout, workload/benchmark và exceptions |

Không gộp repair, store migration, reshard/trim, feature-floor promotion hoặc thay topology vào binary rollout chỉ để “hoàn tất checklist”. Những việc thật sự cần có action riêng với prerequisites và phạm vi ảnh hưởng đã kiểm.

## 8. Cấu trúc và kiểm tra bộ phân tích

Mỗi hop giữ README, plan và các cặp `00`–`15` MD/CSV. CSV là ledger đủ mọi file đổi; Markdown nhóm theo hành vi ảnh hưởng upgrade. Master giữ schema cơ sở; component append impact/evidence, không regenerate làm mất review. Các view làm việc không thay canonical CSV.

Dùng `tools/validate_all.py` trong từng hop ở mức đang đạt. H1 hiện có 11 kiểm tra offline, H2 có 11 và H3 có 14; chúng kiểm source/binary gate, tham chiếu, manifest/native-suite, test-pack assets, As-Is/action coverage, decision arithmetic và finding-quality tương ứng. H1/H3 đã dùng strict-zero; H2 còn dùng `max_incomplete=397` để ngăn quality hồi quy, nên runner H2 PASS không đồng nghĩa mọi finding hoàn chỉnh. Validator runtime cũng không biến `NOT_RUN` thành PASS hoặc `PENDING_INPUT` thành artifact đã khóa.

Đầu ra comparison hoàn chỉnh là **danh sách thay đổi có bằng chứng và action áp dụng được**, cùng các gap còn mở; quyết định rollout dựa thêm As-Is và runtime validation.
