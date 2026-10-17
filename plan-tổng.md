# Plan tổng — Nâng cấp Ceph bằng PA2 luân chuyển spare

**Cập nhật: 12/10/2026.** Kế hoạch hiện hành thay các phương án tổng cũ. Phạm vi đầu tiên: cephadm, RGW/RBD và replicated pool. EC/topology chưa kiểm chứng cần thiết kế và capability riêng trước khi đưa vào scope. Quy mô 1.600 OSD/24 PB là bối cảnh trong tài liệu nguồn, chưa phải inventory hiện tại đã xác nhận.

Liên quan: [README](README.md) · [Comparison](comparison/README.md) · [Console](code/README.md) · [Plan console](code/plan%285%29.md) · [Benchmark](benchmark/README.md).

## 1. Quyết định và đầu ra

1. Chỉ dùng `PA2_ROTATING_SPARE`: **X → S, nâng X; Y → X, nâng Y; Z → Y…** Kế thừa controlled drain, replica validation, gate và canary; bỏ bước trả dữ liệu về nguồn cũ.
2. `KEEP_ROTATED_PLACEMENT` là end state chuẩn. Restore cấu hình tạm theo ledger, giữ mapping cần cho placement đã xoay. Không tự trả về baseline placement.
3. Hoàn tất và ổn định từng hop trước hop kế tiếp. Một chain không trộn target release.
4. Mỗi hop có gói quyết định: comparison → việc cần sửa trước → MOP/gate → execution evidence → benchmark nếu bật → closeout.
5. Console đang phát triển; simulator và dữ liệu mock không đóng gate cluster.

Nếu placement sau xoay không đạt policy, HOLD và lập revision khắc phục (`RECONCILE_TO_POLICY`) với PG/bytes, ownership, gate và chi phí riêng. Đây không phải bước return mặc định.

## 2. Lộ trình và hiện trạng

| Hop | Phạm vi | Bằng chứng hiện có | Điều kiện chuyển tiếp |
|---|---|---|---|
| H1 | 16.2.5 → 16.2.15 | Source/binary, coverage và finding quality strict 127/127 đã validate; runtime `NOT_RUN`; decision `NOT_READY_FOR_DECISION` | Khóa artifact/harness, capture As-Is, chạy lab/canary/rollback |
| H2 | 16.2.15 → 17.2.7 | Source/binary và coverage đã validate; quality 44/441, còn 397 gap; 12 pin `PENDING_INPUT`, runtime `NOT_RUN`; decision `NOT_READY_FOR_DECISION` | Bổ sung finding evidence, capture As-Is, khóa artifacts, chạy lab/canary/rollback sau H1 closeout |
| H3 | 17.2.7 → 18.2.7 | Source/binary 4.434/4.434, 188/188 finding đạt quality audit; 24 As-Is group, 52 runtime gate, 19 test pack, 12 exact-hop pin và 34 action đã thiết kế | Hiện `NOT_READY_FOR_DECISION`: cần gán owner, capture As-Is, khóa artifact/harness, chạy gate/rollback và phê duyệt GO/NO-GO |

Tài liệu H1 hoàn thành không có nghĩa mọi daemon production đã nâng. Snapshot `as-is-base/` và hồ sơ `test/` phải gắn ngày/FSID/scope, không dùng như trạng thái trực tiếp.

## 3. Luồng công việc

| Luồng | Đầu ra bàn giao | Phụ thuộc |
|---|---|---|
| As-Is | Version/digest, client, topology, pool/CRUSH/PG, capacity, DB/WAL, config, SLO | Thu mới trước rollout |
| Comparison | Finding áp dụng, activation, key/API cần sửa/bỏ, boundary và test | Đúng hai endpoint + artifact thực |
| MOP PA2 | Chain/group, lệnh theo capability, timeout/gate, pause/resume, phục hồi | Applicability, planner và dry-run |
| Console | Inventory → plan → observed-state gate → ledger/evidence → report | Lát cắt trong plan console |
| Benchmark | BEFORE/DURING/AFTER, tool/overhead, giới hạn so sánh | Profile/ngưỡng chốt trước run |
| Closeout | Version coverage, placement bàn giao, stable window, gap và owner | Evidence cho mọi phần áp dụng |

Owner, cửa sổ, timeout, headroom và SLO điền trong change record. Không lấy số minh họa của lab thành ngưỡng production.

## 4. Trước mỗi hop

- [ ] Chốt FSID/môi trường, daemon/client/pool scope và source/target digest; đánh giá downstream/vendor delta.
- [ ] Đối chiếu config database, effective config và file; lập action cho removed/renamed/default mới, API/script cũ và dependency/tool.
- [ ] Điền applicability YES/NO/UNKNOWN; giải quyết UNKNOWN ở phase chịu ảnh hưởng. N/A cần bằng chứng không dùng.
- [ ] Kiểm MGR standby, MON quorum, host, registry/pull, package/container runtime và telemetry độc lập.
- [ ] Chốt size/min_size, release/features, client support cho upmap, CRUSH, override, balancer/autoscaler và flags cản recovery/scrub.
- [ ] Đánh giá toàn maintenance set và thêm một failure theo policy N+1; capacity/replica headroom đủ suốt handoff.
- [ ] Baseline có hash/timestamp; nguồn khôi phục và rehearsal phù hợp boundary của hop.
- [ ] Chốt benchmark profile nếu bật; health/QoS vận hành vẫn bắt buộc.
- [ ] Review MOP theo PA2 mới; không dùng nguyên MOP OSD/H0 drain-return cũ.

Chi tiết tại [comparison tổng](comparison/README.md). Chỉ xử lý mục áp dụng; sự xuất hiện của repair/trim/migrate/feature trong báo cáo không tự tạo yêu cầu chạy chúng.

## 5. Trình tự daemon

Cephadm đi theo **MGR → MON → crash → OSD → MDS nếu có → RGW → rbd-mirror nếu có**, tiếp các service thực dùng. Staggered filters có từ Pacific 16.2.11; H1 phải chuyển tiếp MGR từ 16.2.5 trước khi dựa vào filters. `--limit` giới hạn tổng daemon nâng trong lần chạy, không quyết số OSD down đồng thời. [Ceph Pacific upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/).

| Thành phần | Thực hiện | Gate chuyển tiếp |
|---|---|---|
| MGR | Nâng standby, xác minh, chuyển active, hoàn tất MGR còn lại | Active/standby, module, orchestrator migration, metrics/parser, digest |
| MON | Từng MON, đợi trở lại quorum trước MON kế | Quorum/sync/election, auth, logs và workload |
| crash | Hoàn tất theo orchestrator | Collection/submission và quyền |
| OSD | PA2 mục 6–8, đổi image đúng OSD đã chuẩn bị | Isolation, replica/scrub, down set, version, ledger |
| MDS nếu có | MOP riêng rank/standby-replay/client theo hop | Metadata/workload, restore state, compatibility |
| RGW | Drain traffic theo LB/endpoint, canary rồi rolling | S3/checksum, auth/TLS, multipart và feature đang dùng |
| Mirror/client/tool | Kế hoạch dịch vụ và compatibility riêng | Backlog/failover/cache, cephadm/ceph-common, monitoring |

Không để upgrade toàn cụm tự nâng OSD chưa qua PA2 gate. Controller, manual MOP và orchestrator phải có quyền điều phối rõ, không có hai tác nhân mutation độc lập.

## 6. Chuẩn bị chain

U = nguồn sắp nâng; D = đích ở bản đích; S = spare đầu; R = thiết bị replacement. Chain có thứ tự; wave gồm một/nhiều chain trong cùng hop. Handoff set bao phủ toàn PG cần bàn giao khỏi nguồn, chia group có revision.

| Lượt | Handoff | Trạng thái sau lượt |
|---|---|---|
| Chuẩn bị | S chưa nhận dữ liệu production | S đúng digest, khỏe, đủ capacity, isolate; chỉ là spare candidate |
| 1 | X → S, nâng X | S giữ PG của X; X thành spare candidate |
| 2 | Y → X, nâng Y | X giữ PG của Y; Y thành spare candidate |
| 3 | Z → Y, nâng Z | Y giữ PG của Z; Z thành spare candidate |
| Cuối | Hoàn tất nguồn trong scope | Giữ placement sau xoay, bàn giao spare cuối |

S cũng phải nâng nếu chưa ở bản đích, sau isolation/maintenance gate. Spare không có nghĩa thiết bị đã zap hoặc bytes cũ đã biến mất. Nâng daemon giữ ID/incarnation; replacement mới đổi incarnation.

Mỗi cặp kiểm lại toàn mapping từng PG, không trùng replica/failure domain, CRUSH root/class/rule, capacity/DB/WAL, QoS, digest và reservation. D không thuộc down set của chain khác. Nếu một D không đủ, lập tập đích/chain khả thi hoặc BLOCKED; không hạ size/min_size hay nới CRUSH.

Primary-affinity là đầu vào chọn primary, không ngăn nhận PG. Phải kiểm trạng thái thực sau thay đổi. [CRUSH/primary-affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity), [upmap/client requirements](https://docs.ceph.com/en/pacific/rados/operations/upmap/).

## 7. Một lượt U → D

| Bước | Hành động | Evidence/gate |
|---|---|---|
| 1. Bind | U/D/incarnation, map epoch, groups, before/current/desired, digest, owner | Plan revision, reservation/lease khớp thực tế |
| 2a. Kiểm trước chuyển | Hoàn tất chuẩn bị affinity/flags theo plan và chờ ổn định; deep-scrub mới toàn handoff set tại placement hiện tại; chờ completion và kết quả sạch | `PRE_HANDOFF_SCRUB_ACCEPTED` gắn PG/set revision, mapping, incarnation và timestamp |
| 2b. Admission | Recheck kết quả scrub trước chuyển, đích đúng bản, isolation, topology, headroom và down set | `SPARE_ADMISSION_ALLOWED` chỉ cho canary U/D này |
| 3. Canary | Recheck actual role, D nhận group đầu làm replica | Mapping hội tụ, actual primary khác D, active+clean |
| 4. Kiểm sau chuyển | Deep-scrub mới lần thứ hai sau catch-up; thu completion/lỗi | `HANDOFF_GROUP_ACCEPTED` đúng group |
| 5. Mở rộng | Lặp chuyển → hội tụ → kiểm theo budget | Mọi PG có coverage; không truyền PASS nhóm đầu |
| 6. Bàn giao | Đối chiếu toàn membership, restore affinity D đúng policy, quan sát | `HANDOFF_COMPLETE`: U vắng toàn scope, D đã kiểm/ổn định |
| 7. Nâng U | Recheck isolation, capacity/N+1, `ok-to-stop` toàn down set, redeploy | Đúng daemon/digest, không PG phát sinh phá isolation |
| 8. Rotate | U khỏe, đúng version, còn isolate; ghi ledger | `SPARE_ROTATED`, chưa tự đạt replica PASS |
| 9. Lượt kế | Inventory/map mới, admission nguồn kế → U | Không tái dùng gate cũ |

Isolation kiểm cả `up[]`/`acting[]` trên **mọi pool/PG có thể dùng U**, kể cả PG mới. Không còn primary chưa đủ. Affinity áp dụng toàn OSD, chỉ restore khi mọi PG trong handoff set và membership phát sinh đều được kiểm.

**Hai lượt deep-scrub bắt buộc:** lượt trước bao phủ toàn handoff set và hoàn tất sau chuẩn bị affinity/flags và trước thay membership PG đầu tiên của lượt U→D; lượt sau chạy cho từng group sau khi D catch-up/active+clean. Không tái dùng marker trước chuyển cho lượt sau hoặc thay deep-scrub bằng scrub thường. Mỗi PG lưu stage PRE_HANDOFF/POST_HANDOFF, request/start/completion mới, mapping/incarnation, errors và evidence.

Nếu pre-scrub lỗi, thiếu completion hoặc còn PG chưa kiểm thì không handoff; post-scrub chưa đạt thì không mở group tiếp, restore affinity, nâng U hay rotate. Mapping/incarnation/set thay đổi liên quan hoặc có lỗi mới thì re-evaluate/invalidate evidence bị ảnh hưởng trước hành động tiếp; không vô hiệu chỉ vì epoch tăng không liên quan. Với workload đang ghi, đây là kiểm nhất quán ở thời điểm scrub, không phải snapshot bất biến.

Deep-scrub cần completion mới; command thành công/marker cũ không đủ. Thiếu evidence → BLOCKED/INCONCLUSIVE, lỗi thật → HOLD. Không tự repair để biến lỗi thành PASS. Đây là acceptance policy của dự án, cần adapter/lab chứng minh trên từng hop.

## 8. Canary và hoàn thành wave

Canary tối thiểu **X → S, nâng X, Y → X, nâng Y**, để X sau nâng thực sự nhận dữ liệu. Bổ sung cohort thiết bị, DB/WAL, class/pool, host/tải khác. Mở rộng theo evidence hành vi, phục hồi và QoS, không theo số OSD lab.

Các giới hạn độc lập: `batch_size`, `chain_parallelism`, `handoff_parallelism`, `max_simultaneous_down`, `scrub_concurrency`, `promotion_parallelism`, `max_pg_per_handoff_group`, `max_bytes_per_handoff_group`. Runner có concurrency/iodepth riêng.

`WAVE_COMPLETE` yêu cầu:

- [ ] Mọi OSD trong scope, kể cả S đầu/spare cuối, đúng target digest/version.
- [ ] Tất cả handoff set có đủ coverage deep-scrub trước và sau chuyển, hội tụ và replica evidence đạt; dịch vụ đủ stable window.
- [ ] Placement sau xoay được bàn giao; override/dependency có owner; cấu hình tạm được restore đúng ledger.
- [ ] Bật lại balancer/autoscaler nếu đã đổi, ghi data movement và chờ ổn định; tính chi phí vào report.
- [ ] Spare cuối chưa nhận PG sau nâng ghi `replica_validation=NOT_EXERCISED`, không replica PASS. Nếu policy yêu cầu kiểm đường dữ liệu của spare này, thêm bài admission/lab riêng hoặc giữ phần đó chưa đóng.
- [ ] Báo HOLD/exception/gap, evidence và QoS riêng.

## 9. Pause, resume và phục hồi

HOLD khi mapping/replica sai, inconsistency, quorum/daemon lỗi, vượt stop policy QoS, thiếu capacity, mất gate/telemetry bắt buộc hoặc resource bị tác nhân khác sửa. Pause chặn mutation mới; recovery đã chạy có thể tiếp tục.

Resume đọc FSID, U/D/incarnation, mapping, digest, lease, command outcome và dependency. Timeout không chứng minh lệnh chưa chạy. State khác plan cần revision/recheck, không chỉ tăng con trỏ chain.

Giữ dữ liệu trên OSD đang phục vụ; không giả U sau drain còn đủ replica, không coi S đầu là backup cả chuỗi, không đảo toàn chain/nạp map cũ.

Ưu tiên containment và forward-fix phù hợp lỗi. R sạch chạy bản cũ chỉ là lựa chọn **có điều kiện**: floor/features còn tương thích, replica lành/headroom đủ, provision/activation/image đã kiểm. `ok-to-stop` không thay `safe-to-destroy`; destroy/purge/zap có quyết định riêng. Không mở store đã được bản mới ghi bằng binary cũ. Nếu không tương thích, ghi `BLOCKED_ROLLBACK_VERSION_INCOMPATIBLE` và dùng recovery cho target. [BlueFS boundary H1](comparison/pacific-16.2.5-to-16.2.15/02-bluestore-bluefs.md), [cephadm boundary H1](comparison/pacific-16.2.5-to-16.2.15/08-cephadm-orchestrator.md).

## 10. Benchmark và kiểm dữ liệu

Theo [protocol benchmark](benchmark/README.md): BEFORE trước hoạt động can thiệp đầu (kể cả deep-scrub trước chuyển hoặc chuẩn bị S trong scope); DURING gồm chuẩn bị S, pre-deep-scrub, handoff, post-deep-scrub, redeploy/rotate/end-state; AFTER sau `AFTER_WAVE_STABLE`. Plateau giữa chain vẫn là DURING.

So RBD/RGW theo cùng dataset/profile/client/load model. Đo IOPS offered/completed, MiB/s, p50/p95/p99, error/timeout, stall, SLO violation, bytes backfill và thời gian ổn định. Cohort REMAP/NEIGHBOR/CONTROL cần proof; endpoint-only ghi `SERVICE_ONLY`.

Bench tool gồm collector/planner/controller/API/UI/evidence store và Warp/fio/client/tool đổi version. Tách đổi Ceph khỏi đổi tool. Benchmark tùy chọn; monitoring vận hành bắt buộc. Không hứa giảm 50% thời gian từ việc bỏ chiều return.

## 11. Kế hoạch thực hiện

| Mốc | Công việc | Điều kiện hoàn thành |
|---|---|---|
| P0 | As-Is/action register H1, reconcile hồ sơ MGR/MON với hiện tại | Không UNKNOWN trong scope canary; biết artifact/boundary |
| P1 | MOP OSD PA2 thay drain-return; chain trên topology snapshot; ngưỡng/window | Review/dry-run full scope và recovery đạt |
| P2 | Console inventory/evidence/portable, bỏ PA1 khỏi tạo run mới | Regression đúng scope, chạy từ config sạch |
| P3 | PA2 live lab: handoff/scrub/redeploy, lease/reconcile | Hai lượt; đủ pre/post scrub, stale evidence, timeout, restart, double-worker, tail spare đúng |
| P4 | Bench/lab đại diện, tool overhead và topology/load cohorts | Profile tái lập, concurrency có số đo |
| P5 | Canary H1 → batch → closeout wave/service | Runtime gate/evidence đủ, temporary state có disposition |
| P6 | Hoàn thiện comparison H2 song song P0–P4 | Action/checklist riêng đầy đủ, H1 closeout trước runtime H2 |
| P7 | Baseline mới 16.2.15, canary mới, rollout H2 | Target coverage 17.2.7 và aftercare đạt |

Chưa đặt ETA toàn cụm. Chốt 24 PB là logical/used/raw; tính traffic gồm chuẩn bị, ghi mới, retry, scrub và cân bằng cuối wave. Không nhân tuyến tính thời gian một OSD lab lên cả cụm.

## 12. Bàn giao

Tài liệu thống nhất PA2; finding → action → test/gate → evidence trace được hai chiều. Console hiển thị chain, U/D, gate/coverage đúng. Mỗi wave có config snapshot, ledger/map/events/raw evidence, version coverage, stable window; benchmark có raw samples/profile hoặc NOT_REQUESTED. Production acceptance cần evidence của chính môi trường đó.
