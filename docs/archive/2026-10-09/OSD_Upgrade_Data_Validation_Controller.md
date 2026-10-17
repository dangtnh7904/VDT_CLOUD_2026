# OSD Upgrade Controller — PA1, PA2 và QoS Observer

**Cập nhật 08/10/2026.** Contract triển khai cho Ceph Pacific replicated pool. API, schema và trạng thái bên dưới là thiết kế ứng dụng, chưa phải xác nhận phần mềm đã triển khai.

**Tài liệu liên quan:** [Phương án và so sánh PA1–PA2](PA1_PA2_OSD_Upgrade_Strategy.md) · [Console](Storage_Lab_Console_OSD_Validation_and_Benchmark.md) · [OSD Info Collector](code/osd-info-collector/README.md) · [Bài kiểm lab](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md)

**Mục lục**

- [1. Workflow và trách nhiệm](#1-workflow-và-trách-nhiệm)
- [2. Invariant](#2-invariant)
- [3. State machine](#3-state-machine)
- [4. Run config và preflight](#4-run-config-và-preflight)
- [5. Change ledger và concurrency control](#5-change-ledger-và-concurrency-control)
- [6. Placement và admission manager](#6-placement-và-admission-manager)
- [7. Production Replica Checker](#7-production-replica-checker)
- [8. Affinity restore và handoff](#8-affinity-restore-và-handoff)
- [9. Replacement rollback coordinator](#9-replacement-rollback-coordinator)
- [10. Batch planner và scheduler](#10-batch-planner-và-scheduler)
- [11. QoS Observer contract](#11-qos-observer-contract)
- [12. Telemetry, gate result và stop conditions](#12-telemetry-gate-result-và-stop-conditions)
- [13. Data model](#13-data-model)
- [14. API contract](#14-api-contract)
- [15. UI và report contract](#15-ui-và-report-contract)
- [16. Acceptance scenarios](#16-acceptance-scenarios)
- [17. Phần mở rộng lab](#17-phần-mở-rộng-lab)
- [18. Contract so sánh PA1–PA2](#18-contract-so-sánh-pa1pa2)
- [19. Nguồn đối chiếu](#19-nguồn-đối-chiếu)

## 1. Workflow và trách nhiệm

| Workflow | Trách nhiệm |
|---|---|
| `PA1_PRODUCTION` | Baseline, drain, isolation, redeploy, return làm replica, deep-scrub và restore |
| `PA2_ROTATING_SPARE` | Điều phối wave/chuỗi spare, handoff, kiểm replica, nâng nguồn đã drain và bàn giao placement cuối wave |
| `QOS_OBSERVER` | Chạy workload phụ, nhận event nâng cấp, đo và so QoS |
| `REPLACE_WITH_OLD_VERSION` | Thay X bằng OSD sạch R chạy bản cũ tương thích |

Session liên kết các workflow bằng ID và timeline; mỗi workflow có lifecycle riêng. Production chạy được khi benchmark không bật.

Plan chọn rõ profile PA1 hoặc PA2; không có profile mặc định hoặc cơ chế tự ưu tiên một phương án. PA2 trong tài liệu này chỉ có nghĩa rotating spare. Telemetry an toàn vẫn bắt buộc theo policy của run.

Bài kiểm bổ sung trên PG lab, gồm UI/API tối thiểu, nằm tại [PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md). Core Controller không phụ thuộc vào dữ liệu hoặc checkpoint lab. Plan nhập từ phiên bản cũ phải tạo revision và đối chiếu contract hiện tại; giữ nguyên evidence lịch sử. EC chưa thuộc scope triển khai này.

## 2. Invariant

### I1 — Isolation và admission

- Trước redeploy, nguồn X của PA1 hoặc U của PA2 vắng trong up/acting của toàn inventory PG trong scope, không chỉ PG của baseline.
- PA1 kiểm X trước return; PA2 kiểm spare D trước nhóm handoff đầu. OSD nhận phải giữ isolation ngoài các PG được admit.
- Trong return/handoff, OSD nhận chỉ có trong `admitted_pg_set` và giữ vai trò replica; nhóm chưa admit tiếp tục ở ngoài OSD đó.
- Khôi phục affinity sau khi toàn return/handoff set đạt kiểm replica và mọi PG thực đang chứa OSD nhận đã được đối chiếu với plan.
- Sau handoff cuối, mapping theo policy đích đã chốt. Với PA2, policy đích có thể giữ placement sau xoay; không tự restore mapping lịch sử.

Map/pool thay đổi kích hoạt resolve lại. Nếu không còn bảo đảm điều kiện của bước hiện tại thì dừng mutation tiếp theo và reconcile.

### I2 — Evidence đúng đối tượng

Evidence gắn run, PG, mapping/interval, OSD incarnation, thời gian và nguồn. Epoch tăng mà mapping liên quan không đổi không tự làm kết quả mất hiệu lực. Thay role/membership/incarnation liên quan cần đánh giá lại; gap không đủ chứng minh thì INCONCLUSIVE.

Deep-scrub đạt phải là lượt mới sau hội tụ return/handoff và có kết quả hoàn tất. Không suy từ request rc=0 hoặc HEALTH_OK.

### I3 — Maintenance safety

Kiểm planned down set cùng OSD đã down, capacity và failure domain. Đích đang nhận hoặc phục vụ PG đã bàn giao không nằm trong tập sắp dừng. Không hạ min_size hoặc force removal để vượt gate.

### I4 — Ledger và quyền sở hữu

Mỗi mutation có baseline, plan revision, observed result và restore target. Chỉ restore cấu hình run sở hữu; xung đột với thay đổi ngoài run phải reconcile. Replacement dùng identity mới và đích X→R.

### I5 — Kết quả độc lập

Trạng thái PA1/PA2, QoS và bài lab bổ sung được đánh giá riêng. SLO policy có thể HOLD bước nâng cấp tiếp theo; việc không yêu cầu benchmark hoặc lab không tạo lỗi gate production.

### I6 — Chuỗi spare

- Một OSD không đồng thời là spare/đích của chuỗi này và nguồn chuẩn bị dừng của chuỗi khác.
- `DAEMON_READY` hoặc `SPARE_CANDIDATE` không chứng minh khả năng xử lý toàn handoff set; nhóm nhận dữ liệu phải có evidence riêng.
- Chỉ nâng U khi mọi handoff group đã đạt, U drain toàn scope, D bàn giao ổn định và maintenance gate được kiểm lại.
- Chỉ chuyển vai spare sau khi U đúng version/digest đích, incarnation đúng và isolation còn hợp lệ; nguồn kế tiếp vẫn cần admission gate riêng.
- Kết thúc lượt không xóa các mapping mà PG của chuỗi còn phụ thuộc. Kết thúc wave phân biệt end state đã bàn giao với baseline lịch sử.

## 3. State machine

### 3.1. PA1

| State | Hoạt động / điều kiện |
|---|---|
| `CREATED` | Scope, target image, X/S, policy và rollback plan |
| `PREFLIGHT_READY` | Compatibility, nguồn evidence, quyền và safety prerequisites đủ |
| `BASELINE_READY` | Baseline/ledger đầy đủ |
| `DRAINING` | Giảm primary duty, chuyển X→S theo nhóm |
| `DRAINED` | X không còn trong up/acting của scope |
| `MAINTENANCE_APPROVED` | Gate down set còn hiệu lực ngay trước redeploy |
| `UPGRADING` | Redeploy X bằng digest đã chốt |
| `DAEMON_READY` | Up/in, đúng version/image, isolation còn đúng; cấp RETURN_ALLOWED |
| `REPLICA_RETURN` | Admit nhóm PG, đổi placement |
| `REPLICA_CONVERGING` | Chờ active+clean, X replica |
| `REPLICA_SCRUBBING` | Yêu cầu và theo dõi deep-scrub mới |
| `REPLICA_ACCEPTED` | Nhóm đạt; lặp return nếu còn nhóm |
| `PRIMARY_RESTORE_READY` | Đủ coverage return set và kiểm actual membership hiện tại |
| `PRIMARY_RESTORED` | Affinity về baseline/policy, vai trò thực tế được ghi nhận |
| `RESTORING` | Khôi phục cấu hình tạm còn lại, kiểm kết quả |
| `STABILIZING` | Đợi stable-window policy |
| `COMPLETE` | Gate, evidence và ledger hoàn tất |

Benchmark không nằm trong state machine này. Không có bước test dữ liệu riêng khi X down. HOLD/BLOCKED/INCONCLUSIVE lưu reason và evidence; resume đọc lại actual state, không chỉ tăng con trỏ bước.

### 3.2. Lifecycle phụ

| Workflow | Lifecycle |
|---|---|
| QoS | PLANNED → PREPARING → WARMUP → RUNNING → COMPLETE / FAILED / STOPPED |
| Replacement | HOLD → CONTAINED → SOURCES_READY → SAFE_TO_REMOVE → R_PROVISIONED → R_REBUILT → ROLLBACK_COMPLETE |
| Session | PLANNED → RUNNING → REPORT_READY / INCOMPLETE |

STOP benchmark chỉ dừng workload runner. HOLD PA1/PA2 dừng hành động rollout tiếp theo; không tự tắt recovery hoặc stop tất cả OSD. Cô lập OSD gặp lỗi là hành động riêng theo rollback/emergency plan.

### 3.3. PA2 — Wave, lượt handoff và chuyển vai spare

| State / gate | Hoạt động hoặc điều kiện |
|---|---|
| `WAVE_PLANNED` | Chốt bản đích cho một hop phiên bản, nguồn cần nâng, S ban đầu, các chuỗi và end-state policy |
| `CHAIN_READY` | Baseline đủ, ownership/reservation hợp lệ, S đã ở bản đích; chuẩn bị S nếu cần |
| `SPARE_CANDIDATE` | D đúng digest, không có PG ngoài admission, đủ điều kiện daemon; chưa được coi là replica đã kiểm |
| `SPARE_ADMISSION_ALLOWED` | Cặp U/D, toàn handoff set, capacity, CRUSH/failure domain và down set đã kiểm; cho phép nhóm canary |
| `HANDOFF_GROUP_CONVERGING` | Chuyển nhóm U→D, theo dõi actual up/acting/primary; D replica |
| `HANDOFF_GROUP_SCRUBBING` | Sau active+clean, yêu cầu và thu completion của deep-scrub mới |
| `HANDOFF_GROUP_ACCEPTED` | Nhóm đủ evidence; có thể mở nhóm tiếp theo theo budget |
| `HANDOFF_COMPLETE` | Toàn set đạt, U vắng toàn scope, affinity D về policy đích sau đủ coverage, D ổn định |
| `SOURCE_UPGRADING` | Maintenance gate mới cho down set; redeploy U, D tiếp tục phục vụ |
| `SPARE_ROTATED` | U đúng version/incarnation và isolation; U thành candidate, D thành OSD phục vụ đã bàn giao |
| `WAVE_RECONCILING` | Hết danh sách nguồn; thực hiện end-state plan và bàn giao ownership |
| `WAVE_STABILIZING` | Quan sát version coverage, PG/health/QoS và ổn định placement cuối |
| `WAVE_COMPLETE` | Mọi gate cần thiết đạt và end state khớp plan; đánh dấu spare cuối chưa kiểm dữ liệu nếu không nhận PG |

`HANDOFF_COMPLETE` là checkpoint trước nâng nguồn, không phải kết thúc wave. Chặng tiếp theo được tạo sau `SPARE_ROTATED` và replan cặp nguồn/đích mới. Affinity D chỉ khôi phục sau toàn set, không sau riêng canary.

Pause/HOLD giữ các PG đã bàn giao trên đích hiện tại và chặn mutation kế tiếp của chuỗi bị ảnh hưởng. Resume reconcile actual state và evidence; không tự reverse các lượt trước. Chuỗi khác chỉ tiếp tục khi không chia sẻ rủi ro/lease/budget bị ảnh hưởng.

## 4. Run config và preflight

### 4.1. Ví dụ cấu hình PA1

Đây là cấu hình theo profile được chọn, không phải profile mặc định.

```yaml
profile: PA1_PRODUCTION
execution_environment: <PRODUCTION-or-LAB>
session_id: <id>
run_id: <id>
fsid: <cluster-id>
target_osd: <X>
target_incarnation: <osd-fsid-device-identity>
drain_destinations: [<S>]
source_version: <version>
source_image_digest: <digest>
target_version: <version>
target_image_digest: <digest>
rollback_plan_id: <id>
policy_revision: <revision>
baseline_artifact_id: <id>
osd_inventory_artifact_id: <id>
pool_inventory_revision: <revision>
placement_plan_revision: <revision>
return_set_revision: <revision>
scrub_evidence_max_age: <deployment-policy>
stable_window_policy: <policy-id>
```

Baseline chứa health, PG states, versions/digests, OSDMap/CRUSH, affinity, flags, upmap/upmap-items, balancer/autoscaler, service specs, capacity và actual placement. `osd_inventory_artifact_id` tham chiếu artifact bất biến do [OSD Info Collector](code/osd-info-collector/README.md) tạo; không copy riêng vài giá trị từ màn hình vào plan rồi bỏ raw evidence.

Với mỗi OSD nguồn/đích/spare/replacement, inventory baseline tối thiểu phải có host, public/cluster IP, data/DB/WAL path và physical device nếu Ceph metadata cung cấp, dung lượng/used/free/used%, tổng PG, số primary PG, up/in, weight/reweight/primary-affinity, OSD FSID, version/image và CRUSH location. Dữ liệu thiếu giữ `null` cùng warning/quality, không suy đoán `/dev/*` hoặc đổi thành 0.

Preflight kiểm CLI/schema đúng phiên bản, nguồn scrub completion, quyền thao tác, khả năng giữ placement/role theo plan, image đích và đường provision rollback tương thích. Mọi timeout/ngưỡng là cấu hình triển khai, không tự gán thành ngưỡng chuẩn Ceph.

### 4.2. Cấu hình PA2

`PA2_ROTATING_SPARE` dùng các trường chung của session/version/policy/evidence và bổ sung:

```yaml
profile: PA2_ROTATING_SPARE
wave_id: <id>
upgrade_stage_id: <one-version-hop>
initial_spares: [<S>]
pending_upgrade_osds: [<X>, <Y>, <Z>]
chains:
  - chain_id: <id>
    initial_spare: <S>
    planned_sources: [<X>, <Y>, <Z>]
    current_rotation_step_id: <id>
end_placement_policy: <KEEP_ROTATED_PLACEMENT-or-RECONCILE_TO_POLICY>
desired_end_state_revision: <revision>
chain_parallelism: <limit>
handoff_parallelism: <limit>
max_simultaneous_down: <limit>
scrub_concurrency: <limit>
promotion_parallelism: <limit>
```

Mỗi rotation step chốt `source_osd`, `destination_osd` cùng incarnation, handoff-set revision, PG mappings, affinity đích, byte estimate, reservations và rollback plan. Sau đổi inventory phải replan; không tự suy D nhận được mọi PG của U vì nó đang trống.

Version coverage bao gồm S ban đầu, nguồn trong chuỗi và spare cuối. S chưa đúng bản đích cần bước chuẩn bị riêng trước handoff đầu; ghi event và chi phí. Không đưa nguyên cấu hình PA1 vào PA2 chỉ bằng cách đổi tên profile.

## 5. Change ledger và concurrency control

Mỗi entry có change_id, run, resource, baseline/desired/observed value, reason, timestamps, actor, plan revision, restore target và result. Resource gồm affinity, upmap, flags, balancer/autoscaler, CRUSH, service spec/image và thiết bị replacement.

Mutation dùng resource lease, idempotency key và expected state. Nếu operator/balancer khác đã sửa resource, reconcile trước khi tiếp tục. Timeout không tự chứng minh thao tác cũ chưa chạy; retry phải đối chiếu actual state.

Restore chỉ phần run đã thay.

PA2 bổ sung `wave_id`, `chain_id`, `rotation_step_id`, `dependent_steps`, `desired_end_state_revision` và `disposition` vào ledger. Disposition phân biệt cấu hình tạm cần restore, placement được giữ/bàn giao và thay đổi cần reconcile. Baseline lịch sử không tự trở thành restore target.

Kết thúc lượt chỉ bàn giao ownership của thay đổi còn được dùng; không gọi cleanup PA1 để xóa mapping của cả chuỗi. Thay đổi một PG phải đọc/so toàn giá trị upmap/upmap-items hiện có và kiểm mapping kết quả, không nối cặp ID bằng thay chuỗi văn bản. Sau crash, đối chiếu job/mapping đã thực thi trước retry. R dùng ID mới thì cập nhật placement; R dùng lại ID cũ vẫn có incarnation mới, không kế thừa scrub/version evidence của X.

## 6. Placement và admission manager

### 6.1. PA1 — Return

Planner tạo mapping X→S cùng return groups. Mỗi group lưu pgids, before/current/desired mapping, actual primary, expected target role, failure domains, bytes estimate, ledger IDs và plan revision.

`RETURN_ALLOWED` yêu cầu DAEMON_READY, isolation còn đúng, capacity/safety hiện tại đạt và plan return khả thi. Cập nhật admitted_pg_set trước mutation đã được cho phép; chỉ xác nhận nhóm khi actual placement hội tụ.

Giữ affinity X=0 trong return, kiểm actual primary từng PG. Affinity không điều khiển membership; norebalance không thay placement plan. PG ngoài allowlist xuất hiện trên X → HOLD_ADMISSION_BROKEN; X làm primary trước bước restore → HOLD_UNEXPECTED_PRIMARY.

Không coi pg-upmap-items là lệnh đặt primary. `up[]` đã đổi nhưng `acting[]` chưa đổi thì còn đang chuyển tiếp. Adapter dùng PG query/mapping thực theo phiên bản để chuẩn hóa role.

### 6.2. PA2 — Handoff

Planner chuẩn bị toàn handoff set của U, các nhóm canary/mở rộng và đích D hợp lệ theo từng PG. Một PG có thể xuất hiện ở nhiều lượt nếu các replica khác nhau được nâng; group/evidence gắn cả PG lẫn rotation step và incarnation.

`SPARE_ADMISSION_ALLOWED` yêu cầu D đúng bản đích, isolation ngoài admission, capacity/QoS/failure-domain policy đạt và không thuộc down set/reservation xung đột. Cập nhật allowlist của D trước mutation được cấp phép.

Mỗi nhóm dùng Replica Checker với `target_osd=D`. Sau khi nhận một nhóm, D đã có dữ liệu phục vụ và không còn là spare trống; không đưa D vào danh sách available spare. U còn giữ các PG chưa handoff và không được stop.

Chỉ commit handoff khi mọi nhóm đã đạt, inventory không còn U trong up/acting, actual membership D khớp plan, affinity D được xử lý sau đủ coverage và stable-window đạt. Sau đó recheck maintenance gate mới trước nâng U.

Không có nguồn kế tiếp phù hợp → `BLOCKED_NEXT_TARGET`. Kết thúc wave theo `KEEP_ROTATED_PLACEMENT` hoặc `RECONCILE_TO_POLICY`; mọi chuyển động do reconcile/bật lại balancer phải được theo dõi, không coi như biến mất khỏi chi phí PA2.

## 7. Production Replica Checker

### 7.1. Trình tự và phạm vi

Mỗi PG vừa được admit: hội tụ → OSD nhận là replica thực tế (X của PA1 hoặc D của PA2) → active+clean → chốt pre-scrub marker → request mới → chứng minh lượt scrub đã bắt đầu/hoàn tất → thu result. Vòng scrub bắt đầu trước khi OSD nhận catch-up xong không được tái sử dụng.

Lệnh minh họa theo PG:

```bash
ceph pg deep-scrub <pgid>
```

Controller không bắt production có bộ dữ liệu test bổ sung. Scope là các production PG đã admit; đây là native consistency check, không phải đối chiếu toàn dữ liệu với SHA gốc bên ngoài.

### 7.2. Schema scrub evidence

```text
scrub_id, run_id, strategy, admission_kind, admission_group_id, pgid
wave_id, chain_id, rotation_step_id, return_group_id, handoff_group_id
target_osd, target_incarnation, expected_role=replica
converged_at, requested_at, started_at, completed_at
pre_marker, post_marker, completion_source
mapping_interval, actual_up, actual_acting, actual_primary
continuity_result, evidence_quality
inconsistency_count, scrub_error_count, repair_event
result, invalidated_at, invalidation_reason
```

Adapter theo version dùng marker/history/log/PG query để chứng minh một lượt mới hoàn tất; polling không bắt gặp cờ scrubbing không tự nghĩa là lượt không chạy nếu có evidence lịch sử đủ mạnh. Ngược lại, request rc=0 hoặc marker cũ không đủ. Không hard-code field chưa có trên Pacific.

PASS chỉ khi required PG coverage đủ, target đúng replica, result sạch và evidence đủ mới/liên tục. Repair event làm HOLD để đánh giá nguồn đúng; không tự chạy repair rồi xóa dấu vết. Nếu auto-repair đã bật, baseline phải ghi rõ và result phải phát hiện tác động của nó.

Production write có thể tiếp diễn trong scrub. Không yêu cầu khóa ghi toàn PG; kết quả được ghi theo cửa sổ scrub thực tế. Chốt `scrub_evidence_max_age` theo policy; mapping/incarnation thay đổi hoặc có lỗi mới buộc đánh giá lại. Scrub toàn return/handoff set theo nhóm; sample không cấp PASS cho phần chưa kiểm.

## 8. Affinity restore và handoff

Trong mục này target là X đối với PA1 hoặc D đối với PA2; return set của PA1 tương ứng handoff set của PA2. Các kiểm tra áp dụng cho toàn actual membership của target.

Lưu affinity baseline/current/desired. `PRIMARY_RESTORE_READY` yêu cầu:

1. Tất cả return groups PA1 hoặc handoff groups PA2 đã hội tụ và có kiểm replica còn hợp lệ; PA2 ghi HANDOFF_GROUP_ACCEPTED cho từng nhóm.
2. Danh sách PG thực đang chứa target khớp plan; phần mới phát sinh đã được đánh giá và kiểm nếu bổ sung vào return/handoff set.
3. Target đang replica trong cửa sổ kiểm; health, capacity, telemetry và QoS policy đạt.
4. Giá trị affinity đích đúng baseline hoặc revision đã chốt; recheck ngay trước mutation.

Affinity áp dụng cho toàn OSD, vì vậy không khôi phục sau riêng nhóm đầu khi các nhóm khác chưa kiểm. Backend khôi phục cấu hình và ghi actual primary; không yêu cầu X phải trở thành primary của một PG chỉ định để COMPLETE.

Khôi phục các thay đổi tạm khác theo ledger. Placement change đã biết trước phải được tính trong return plan. Nếu restore tạo chuyển động dữ liệu, ghi event và theo dõi tới khi ổn định. Bàn giao về policy Ceph bình thường sau COMPLETE; không giữ một admission gate nâng cấp cho mọi PG tương lai.

Với PA2, bàn giao end-state ownership ở cấp wave. `WAVE_COMPLETE` không yêu cầu xóa mapping còn cần cho placement đích. Spare cuối chưa nhận PG có `replica_validation=NOT_EXERCISED`, không được gắn REPLICA_ACCEPTED; việc nâng daemon và việc kiểm dữ liệu là hai kết quả riêng.

## 9. Replacement rollback coordinator

Plan chốt X, S/các replica còn lại, R/device, old image digest, compatibility, phương thức prepare/activate, service spec và placement đích trước rollout.

| Stage | Điều kiện |
|---|---|
| HOLD | Dừng mở rộng rollout và ghi các PG bị ảnh hưởng |
| CONTAINED | X được hạn chế hoặc dừng theo safety/emergency plan |
| SOURCES_READY | Các bản sao còn lại đủ và đọc được; capacity và kế hoạch khôi phục hợp lệ |
| SAFE_TO_REMOVE | Safe-to-destroy và điều kiện dữ liệu đạt; khác với ok-to-stop |
| R_PROVISIONED | Store sạch, device/incarnation đúng, image cũ dùng cho prepare/activate và daemon |
| R_REBUILT | PG được phục hồi, hội tụ, kiểm replica và affinity restore theo cùng quy trình |
| ROLLBACK_COMPLETE | Dịch vụ ổn định, đủ replication/capacity và ledger X→R hoàn tất |

Nếu nguồn phục hồi không rõ hoặc có inconsistency chưa xử lý, HOLD_DATA_RECOVERY. Không force removal để vượt gate. Stop/fence khi khẩn cấp không có nghĩa được destroy/zap thiết bị ngay.

Không mở store đã nâng cấp bằng binary cũ. Old version phải đáp ứng feature/release floor; thiếu tương thích → BLOCKED_ROLLBACK_VERSION_INCOMPATIBLE. Phương thức provision phải được kiểm trong lab trước khi đưa vào MOP production.

Kiểm soát cephadm reconciliation để không tự tạo R bằng image ngoài plan. Same-ID replacement có incarnation mới; new-ID replacement có mapping mới. Với quy trình cephadm giữ ID qua --replace, tuân thủ yêu cầu host của phiên bản đó.

Trong PA2, target replacement có thể là D đã nhận PG hoặc U vừa nâng; resolve nguồn dữ liệu theo current mapping. Không giả định U còn đủ bản sao sau drain hoặc S ban đầu chứa dữ liệu của mọi lượt. HOLD chuỗi, khóa reservation liên quan và tạo recovery plan có revision; không khôi phục OSDMap cũ hoặc đảo toàn chuỗi như rollback dữ liệu.

## 10. Batch planner và scheduler

Production có các giới hạn độc lập:

```text
batch_size
drain_parallelism
max_simultaneous_down
return_parallelism
scrub_concurrency
promotion_parallelism
```

Benchmark dùng concurrency/numjobs/iodepth hoặc rate policy riêng.

PA2 có thêm `chain_parallelism` và `handoff_parallelism`. Dependency nội bộ chuỗi là handoff hoàn tất → nâng nguồn → spare candidate mới → recheck nguồn tiếp theo. Nhiều chuỗi phải kiểm PG overlap, failure domains và tài nguyên dùng chung cùng một maintenance set; không cấp spare cho hai chuỗi.

Chọn OSD bằng manual IDs hoặc suggestion có inventory revision và lý do: health, version, PG/primary count, I/O, capacity, failure domain, PG overlap và S overlap. Re-evaluate trước mỗi down set và return/handoff group. `batch_size=9` không nghĩa 9 OSD down đồng thời.

Tổng budget tính recovery/backfill + deep-scrub + tải dịch vụ + benchmark + bài kiểm bổ sung trong lab nếu đang chạy. Scheduler ưu tiên an toàn, throttle/pause workload phụ theo capability; mọi đổi tải benchmark mở segment mới. Không giả giữ profile baseline sau khi đã giảm tải.

## 11. QoS Observer contract

### 11.1. Luồng độc lập

Benchmark nhận session và optional upgrade run/batch ID, asset/version, engine/version, rendered config hash, client/endpoint, cache/preconditioning, load model, budget và telemetry policy. Không phụ thuộc bài kiểm dữ liệu lab.

Runner không mutate Ceph placement. Để đo tác động X→S, planner chuẩn bị workload asset và xác minh mapping; MOP upgrade mới thực hiện remap. Có thể chọn X từ placement sẵn có hoặc dùng PG và dữ liệu test có sẵn trong lab. Workload có ghi chạy trên tài nguyên test được cho phép, không ghi vào customer data.

### 11.2. Phase và event

- BEFORE: sau warm-up, trước mutation đầu tiên có thể tác động QoS, gồm cả giảm primary duty.
- DURING PA1: từ mutation đầu tiên qua drain X→S, X down/up, return S→X, scrub, promotion và restore.
- DURING PA2: từ mutation đầu tiên trong scope đo qua bootstrap spare, các handoff, nâng nguồn, chuyển vai spare, scrub và reconcile cuối wave.
- AFTER: PA1 sau return/restore; PA2 sau end-state handoff/reconcile của wave; lưu điều kiện ổn định và actual timestamps.

Event tối thiểu: affinity_change, drain_start/end, pg_up_changed, pg_acting_changed, primary_changed, target_down/up, return_group_start/converged, scrub_start/end, promotion_start/end, restore_end, stable_window_start/end. Có event rollback và runner throttle/pause nếu xảy ra. Mốc AFTER là AFTER_RETURN_STABLE cho PA1 hoặc AFTER_WAVE_STABLE cho PA2; không cộng lặp các cửa sổ con DURING.

Operation băng ranh giới giữ nhãn và quy tắc attribution.

PA2 bổ sung event `spare_prepare`, `handoff_group_start/converged/accepted`, `handoff_complete`, `source_upgrade`, `spare_rotated`, `wave_reconcile`, `wave_end_state_handed_over`. Event có chain/rotation-step ID và from/to OSD/incarnation. Plateau giữa các lượt không tự trở thành AFTER toàn wave. Continuous mode ưu tiên nhìn được gián đoạn; segmented mode phải giữ tải/dữ liệu khởi đầu tương đương và ghi khoảng trống. Đồng hồ/timestamp lệch quá policy làm mất độ tin cậy của correlation.

### 11.3. PG cohorts và mức proof

| Cohort | Contract |
|---|---|
| REMAP | Có evidence actual membership chuyển X→S trong PA1 hoặc U→D trong PA2; có timestamps bắt đầu/hội tụ; tách primary-change-only khỏi membership change |
| NEIGHBOR | Ngoài REMAP, có cạnh dùng chung tài nguyên với footprint bị tác động: OSD/host/DB-WAL/NIC… |
| CONTROL | Mapping không đổi, không giao nhau footprint đã quan sát; vẫn công bố tài nguyên toàn cụm có thể dùng chung |
| UNATTRIBUTED | Không đủ mapping/request proof để gán nhóm |

Cohort được tính theo interval, ưu tiên REMAP rồi NEIGHBOR rồi CONTROL để không double count trong cùng phân tích. Giữ baseline cohort và transition history để so trước/sau; PG control trở thành neighbor phải được ghi lại, không giữ nhãn control cũ. Theo dõi cả return, mọi handoff, reconcile và replacement, không chỉ drain đầu tiên.

Schema:

```text
cohort_id, benchmark_run_id, pgid, interval_start/end
cohort_type, membership_reason, resource_overlap_edges
baseline_up/acting/primary, current_up/acting/primary
from_osd, to_osd, transition_status, map_epochs
asset_item_or_range, request_mapping_artifact
proof_level, mapped_ops, mapped_bytes, unmapped_ops
```

`proof_level` gồm `PG_ATTRIBUTED`, `PARTIAL_ATTRIBUTION`, `SERVICE_ONLY`. Không dùng bộ lọc OSD trên dashboard để tạo proof. RBD cần offset/layout/object→PG; RGW cần manifest/tail/data/metadata scope phù hợp; request có nhiều PG phải ghi multi-PG và cách gán. Cache hit không đủ proof request chạm OSD; report phải ghi cache policy và tỷ lệ request được quy thuộc nếu đo được. Aggregate service latency không tự tách thành latency của từng PG.

### 11.4. Kết quả QoS

Metric theo phase/cohort/op/size: offered/completed IOPS, throughput, latency histogram/p50/p95/p99, errors/timeouts, longest observed I/O stall, SLO violation duration và time-to-stable. Ghi bytes/PG moved, recovery rate và primary shifts để diễn giải khác biệt giữa batch.

Percentile từ request hoặc histogram có định nghĩa/unit tương ứng. Không lấy trung bình các p99; không suy p99 từ Ceph mean latency. Ghi closed-loop/concurrency hay open-loop/rate model; offered load giảm do chờ response phải được thấy trong report.

So sánh DURING–BEFORE là maintenance impact, không phải tự chứng minh bug version mới. AFTER–BEFORE cần asset/profile/client/cache/topology/tải nền tương đương. Baseline 0, thiếu mẫu hoặc đổi load model → không tính phần trăm không hợp lệ. Đổi cấu hình/runner pause tạo segment và có thể làm NOT_COMPARABLE.

Benchmark PASS không thay các gate PA1/PA2. SLO/stop policy đã chọn có thể HOLD hành động upgrade kế tiếp, nhưng tắt benchmark không tự chặn production. Bài so sánh batch yêu cầu QoS evidence mà thiếu thì phần so sánh INCOMPLETE; không biến yêu cầu riêng đó thành gate của mọi run production.

## 12. Telemetry, gate result và stop conditions

Một collector chung theo session/batch; cache inventory theo epoch để tránh mỗi worker quét toàn cụm. Nguồn gồm Prometheus, CLI/API và log đúng phiên bản. Theo dõi client/service, OSD/host/disk/network, PG state/role, recovery/backfill, scrub/errors, capacity và crash.

`code/osd-info-collector/` là collector snapshot độc lập đầu tiên cho phần OSD inventory. Nó lưu cluster evidence chung một lần và evidence riêng từng OSD từ `ceph osd metadata/find/df/tree/dump`, `ceph pg ls-by-osd`, `ceph pg ls-by-primary`, config database và effective config. Artifact dùng schema `CEPH_OSD_BASELINE` v1, có `collection_id`, UTC timestamp, FSID và quality. Tool chỉ đọc; Console sẽ gọi qua adapter/job có allowlist thay vì cho UI chạy shell trực tiếp.

Controller thu ít nhất `BEFORE`, `AFTER_START` và `AFTER_STABLE`; `DURING` được thu khi policy yêu cầu hoặc khi có sự cố. Trước từng down-set phải refresh inventory và gắn snapshot mới với plan revision vì host/IP thường ổn định nhưng PG count, primary count, usage và up/in có thể đổi. Counter/time-series vẫn do telemetry collector đảm nhiệm; OSD Info Collector không thay Prometheus hoặc QoS Observer.

Metric record có tên nguồn, unit/type/labels, observed/collected time, freshness, source artifact, quality và counter reset. Quality là VALID/STALE/GAP/UNSUPPORTED; dữ liệu thiếu không được thay bằng 0. Metric mean của Ceph không phải p99 client.

PG query/history cung cấp role và scrub evidence. Trạng thái active+clean+scrubbing+deep là trạng thái dự kiến khi scrub; không đánh fail chỉ vì xuất hiện cờ này. Theo dõi counter reset sau restart khi tính rate.

| Result | Nghĩa |
|---|---|
| PASS | Điều kiện đúng trong scope/time đã quan sát |
| HOLD | Lỗi thực, trạng thái không an toàn hoặc stop policy kích hoạt |
| BLOCKED | Thiếu điều kiện/capability bắt buộc để chạy bước |
| INCONCLUSIVE | Bằng chứng thiếu hoặc không đủ liên tục để kết luận |
| NOT_REQUESTED | Workflow tùy chọn không bật |
| NOT_EXERCISED | Chưa kiểm đường dữ liệu, ví dụ spare cuối chưa nhận PG sau nâng; không đồng nghĩa PASS |

Gate PA1: RETURN_ALLOWED, REPLICA_ACCEPTED, PRIMARY_RESTORE_READY và COMPLETE. Gate PA2: SPARE_ADMISSION_ALLOWED, HANDOFF_GROUP_ACCEPTED, HANDOFF_COMPLETE và WAVE_COMPLETE; dùng cùng kiểm replica/coverage/affinity trước handoff. QoS result: PASS/WARN/HOLD/NOT_COMPARABLE theo policy bài đo.

HOLD khi isolation/return/handoff scope bị phá, unexpected primary trong return/handoff, inconsistency/I/O error/crash liên quan, capacity/down-set mất an toàn hoặc SLO vượt stop policy. Scrub chưa đủ completion/coverage thì BLOCKED; mất bằng chứng giữa run thì INCONCLUSIVE.

HOLD không tự hủy thiết bị hoặc đổi sang rollback. Replacement dùng plan và removal gate riêng. Kết quả AFTER không là prerequisite cho return vì AFTER được đo sau return.

## 13. Data model

| Entity | Nội dung |
|---|---|
| sessions | FSID, môi trường, workflow bật, policy revision |
| osd_inventory_snapshots | Collection/schema/tool version, FSID, phase, quality, artifact URI/hash và plan revision |
| osd_inventory_items | Snapshot, OSD/incarnation, host/IP/device, capacity/usage, PG/primary count, state/version và warning |
| upgrade_batches | Target IDs và các concurrency độc lập |
| upgrade_runs | Strategy, X hoặc U/incarnation, versions/images, plan revisions, state, rollback link |
| upgrade_waves | Hop phiên bản, strategy, version coverage, initial/final spares, end-state revision |
| spare_chains / rotation_steps | Thứ tự nguồn, U/D, dependency, checkpoint và state từng lượt |
| spare_registry | OSD/incarnation, candidate/receiving/serving role, reservation và validation scope |
| handoff_groups | PG allowlist, U/D, mapping revision, convergence, scrub coverage và result |
| end_state_handoffs | Desired/observed placement, ownership/disposition, reconciliation bytes và completion |
| maintenance_sets | Planned/already-down IDs, gate và timestamps |
| placement_plans | X→S/S→X hoặc U→D, before/current/desired mappings, epoch, dependency và ownership |
| return_groups | PG allowlist, convergence, scrub coverage, result |
| pg_role_observations | PG/target/incarnation, actual mapping/primary, thời gian |
| scrub_runs | Group/PG, markers, timing, role, errors/repair và result |
| affinity_restores | Baseline/current/desired, return/handoff coverage, gate và actual result |
| run_changes | Baseline/change/restore, lease, result, replacement target |
| rollback_runs | X/R, old digest, nguồn khôi phục, removal gate, rebuild result |
| benchmark_assets/profiles/runs | Asset/version, runner, load model, optional upgrade link |
| benchmark_segments/metrics | Phase/time, config hash, raw samples/histograms, gaps |
| benchmark_cohorts | REMAP/NEIGHBOR/CONTROL/UNATTRIBUTED và interval |
| workload_pg_bindings | Item/range/request→PG, proof level, coverage |
| phase_events | Source, sequence, UTC/monotonic time và run links |
| telemetry_windows | Source/query, unit/schema, quality/freshness |
| evidence_artifacts/resource_leases | Artifact identity, access, lease và attempt |

Unique key gồm run/checkpoint/resource/attempt/incarnation phù hợp. Retry append evidence, không ghi đè kết quả cũ. Plan/policy snapshot lưu cùng report. Module lab riêng có thể tham chiếu run_id, không tạo phụ thuộc bắt buộc trong core schema.

## 14. API contract

```text
POST /api/sessions
GET  /api/sessions/:id/timeline
GET  /api/sessions/:id/telemetry
GET  /api/sessions/:id/report
POST /api/target-plans
POST /api/osd-inventory/collections
GET  /api/osd-inventory/collections/:id
GET  /api/osd-inventory/collections/:id/osds/:osd_id
POST /api/upgrade-batches
POST /api/upgrade-batches/:id/maintenance-gate
POST /api/upgrade-runs
POST /api/upgrade-runs/:id/preflight
POST /api/upgrade-runs/:id/baseline
GET  /api/upgrade-runs/:id/return-scope
POST /api/upgrade-runs/:id/drain/next
POST /api/upgrade-runs/:id/isolation/verify
POST /api/upgrade-runs/:id/redeploy
POST /api/upgrade-runs/:id/return/plan
POST /api/upgrade-runs/:id/return/next
POST /api/upgrade-runs/:id/replica-check/:group_id
GET  /api/upgrade-runs/:id/scrub/:pgid
POST /api/upgrade-runs/:id/affinity/precheck
POST /api/upgrade-runs/:id/affinity/restore
POST /api/upgrade-runs/:id/restore
POST /api/rollback-runs
POST /api/rollback-runs/:id/contain
POST /api/rollback-runs/:id/check-sources
POST /api/rollback-runs/:id/removal-gate
POST /api/rollback-runs/:id/replace
GET  /api/rollback-runs/:id/evidence
GET  /api/benchmark/profiles
POST /api/benchmark-runs
POST /api/benchmark-runs/:id/start
POST /api/benchmark-runs/:id/pause
POST /api/benchmark-runs/:id/resume
POST /api/benchmark-runs/:id/stop
GET  /api/benchmark-runs/:id/cohorts
GET  /api/benchmark-runs/:id/results
GET  /api/benchmark-runs/:id/compare
POST /api/upgrade-waves
POST /api/upgrade-waves/:id/plan
GET  /api/upgrade-waves/:id/end-state
POST /api/upgrade-waves/:id/pause
POST /api/upgrade-waves/:id/resume
POST /api/upgrade-waves/:id/reconcile
POST /api/upgrade-waves/:id/complete
POST /api/spare-chains/:id/next-target
POST /api/rotation-steps/:id/admission/precheck
POST /api/rotation-steps/:id/handoff/next
POST /api/rotation-steps/:id/replica-check/:group_id
POST /api/rotation-steps/:id/affinity/restore
POST /api/rotation-steps/:id/handoff/commit
POST /api/rotation-steps/:id/source/redeploy
```

Mutation nhận idempotency key, expected state, plan revision và resource lease; trả job ID. Backend quyết gate từ actual state/evidence. UI không tự gửi PASS hoặc role để mở bước. Timeout/cancel phải đối chiếu job thực trước retry.

## 15. UI và report contract

Production card gồm X/S/R, version/image, current state, PG drain/return, scrub coverage, affinity baseline/current/target, maintenance gate, lỗi và ledger.

OSD detail drawer hiển thị host, public/cluster IP, `/dev/*` data/DB/WAL, physical devices, dung lượng/used%, tổng PG/primary PG và nguồn từng trường. UI hiển thị `PARTIAL/INCONCLUSIVE` cùng warning khi metadata không cho biết path hoặc command không được hỗ trợ; không dựng giá trị giả. Plan giữ `osd_inventory_artifact_id`, collection timestamp và hash để reviewer mở lại đúng evidence đã dùng.

PA2 card bổ sung wave/chain/rotation step, U/D, candidate/receiving/serving role, handoff coverage, dependency, initial/final spare, end-placement policy và version coverage. Hiển thị DAEMON_READY tách khỏi replica acceptance; không gắn spare trống là đã PASS dữ liệu. Không có form hoặc gate test dữ liệu bổ sung trong luồng này.

Benchmark card độc lập gồm asset/profile, offered/completed load, phase, cohort/proof, latency/throughput/errors, sample count, gaps và comparison. Khi không bật, hiển thị NOT_REQUESTED.

Comparison view đặt PA1 và PA2 cạnh nhau với scope, phương pháp đo và điều kiện tương đương; không có nhãn đề xuất, phương án thắng hoặc lựa chọn mặc định.

Report có operation_result, optional qos_result, restore_result và rollback_result nếu xảy ra. Báo cáo lab được liên kết theo run ID khi có. Kết quả không đủ evidence phải được giữ nguyên trạng thái, không chuyển thành 0 lỗi để PASS.

## 16. Acceptance scenarios

| Tình huống | Kết quả yêu cầu |
|---|---|
| PA1 không bật benchmark hoặc bài lab | Chạy đủ luồng production |
| Collector không trả device path | Snapshot PARTIAL với warning; UI không đoán `/dev/sdX` |
| PG/primary count đổi sau khi tạo plan | Refresh snapshot và đánh giá lại plan/down-set |
| Snapshot thuộc FSID khác | Từ chối gắn vào run |
| Nhóm đầu return làm replica | Cho chạy sau RETURN_ALLOWED |
| Request scrub thành công nhưng chưa có completion | Chưa REPLICA_ACCEPTED |
| Khôi phục affinity khi còn nhóm chưa kiểm | BLOCKED_RETURN_COVERAGE |
| PG ngoài allowlist có X | HOLD_ADMISSION_BROKEN |
| X làm primary trong replica return | HOLD_UNEXPECTED_PRIMARY |
| Affinity baseline bằng 0 | Restore 0; không ép X thành primary |
| Mapping/incarnation đổi sau scrub | Đánh giá lại evidence, không tái dùng mù |
| Restore kích hoạt rebalance | Theo dõi và đợi stable window trước COMPLETE |
| PG mới sau handoff | Theo policy Ceph thường ngày, không kế thừa scrub PASS cũ |
| Batch 9, down đồng thời 2 | Kiểm down set thực; report cả hai số |
| X là replica và bị thay bằng S | PG vẫn thuộc REMAP |
| Warp/fio chỉ có số đo endpoint | SERVICE_ONLY |
| CONTROL thành NEIGHBOR | Cập nhật interval và giữ history |
| Benchmark pause hoặc thay profile | Tách segment; đánh giá tính so sánh |
| Old version không tương thích | BLOCKED_ROLLBACK_VERSION_INCOMPATIBLE |
| Ok-to-stop đạt, safe-to-destroy chưa đạt | Chưa cho hủy/tháo vĩnh viễn |
| R dùng lại ID X | Incarnation mới, evidence mới |
| PA2 không bật benchmark/lab | Vẫn chạy các gate production của PA2 |
| D vừa lên đúng image nhưng chưa nhận PG | SPARE_CANDIDATE; không báo replica PASS |
| S ban đầu chưa đúng version đích | Chuẩn bị S trước handoff, đưa vào version coverage |
| Handoff đầu đạt nhưng các nhóm sau chưa kiểm | Không restore affinity hoặc nâng U |
| Handoff set hết nhưng U còn PG ngoài snapshot ban đầu | Chưa HANDOFF_COMPLETE; reconcile inventory |
| D trùng failure domain/capacity thiếu | BLOCKED trước mutation |
| D là đích chuỗi khác hoặc thuộc planned down set | BLOCKED reservation/maintenance conflict |
| Resume sau timeout/crash | Đọc actual mapping/job/ledger trước retry |
| Cleanup lượt định xóa mapping vẫn được dùng | Chặn xóa và giữ/bàn giao ownership |
| Spare cuối chưa nhận PG sau nâng | NOT_EXERCISED cho replica validation; kiểm daemon/version/isolation riêng |
| Reconcile cuối wave gây backfill | Tính vào bytes/time/QoS, chờ stable window |
| D lỗi sau khi U đã drain | HOLD; tìm nguồn phục hồi từ current mapping, không giả U giữ bản sao |

Đây là yêu cầu nghiệm thu phần mềm, chưa phải kết quả test thực tế.

## 17. Phần mở rộng lab

Đọc [PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md](PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md) để triển khai bài test đơn giản trên PG lab hiện có và liên kết kết quả vào session. Module này tái sử dụng mapping/telemetry/evidence, không sửa điều kiện của luồng PA1/PA2 và không là dependency để release core Controller.

## 18. Contract so sánh PA1–PA2

| Thành phần | PA1 | PA2 |
|---|---|---|
| Đơn vị điều phối | Run trên X và batch | Wave, chuỗi và rotation step U/D |
| Admission | Return PG vào X sau nâng | Handoff PG từ nguồn kế tiếp vào spare vừa nâng |
| Bằng chứng replica | Return group và toàn return set | Handoff group và toàn handoff set |
| Checkpoint kết thúc | COMPLETE của run, sau restore/ổn định | HANDOFF_COMPLETE trước nâng U; SPARE_ROTATED sau nâng U; WAVE_COMPLETE sau bàn giao end state |
| Ownership placement | Quản lý thay đổi của run và tương tác batch | Giữ dependency giữa các lượt; bàn giao mapping còn dùng ở cuối wave |
| QoS AFTER | AFTER_RETURN_STABLE | AFTER_WAVE_STABLE |

Comparison record lưu `comparison_id`, hai run/wave ID, scope phiên bản/OSD/PG, workload/asset, load model, cache/client/hardware, ngân sách migration/scrub, initial spare và end-state policy. Lưu bytes migration thực, số PG/member/primary changes, thời gian từng phase, toàn scope đo và metric client.

Không so một lượt handoff chưa hoàn tất với một PA1 run đầy đủ. Không bỏ bootstrap/reconcile khỏi một phương án nhưng tính vào phương án kia. Nếu scope hoặc workload không tương đương, ghi NOT_COMPARABLE và lý do; vẫn trình bày số liệu thô theo phạm vi đã đo.

Số 2D/D là ước lượng lý tưởng của phương án, không phải acceptance criterion hay cam kết giảm 50% thời gian. Controller không xếp hạng hoặc tự chọn phương án; người lập plan chọn profile rõ ràng.

## 19. Nguồn đối chiếu

- [Ceph Pacific — Primary affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity).
- [Ceph Pacific — PG upmap](https://docs.ceph.com/en/pacific/rados/operations/upmap/).
- [Ceph Pacific — Scrubbing](https://docs.ceph.com/en/pacific/rados/configuration/osd-config-ref/).
- [Ceph Pacific — PG consistency và repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/).
- [Ceph Pacific — OSD service và replacement](https://docs.ceph.com/en/pacific/cephadm/services/osd/).
- [Ceph Pacific — Safe-to-destroy](https://docs.ceph.com/en/pacific/rados/operations/add-or-rm-osds/#replacing-an-osd).
