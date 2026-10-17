# Decision register GO/NO-GO cho Quincy 17.2.7 → Reef 18.2.7

**Kết luận hiện tại ngày 12/10/2026: `NOT_READY_FOR_DECISION`.** Source analysis và thiết kế kiểm chứng đã hoàn tất, nhưng chưa có exact-artifact run, As-Is capture, lab/canary result hay rollback rehearsal. `OPEN` không có nghĩa là thất bại; nó có nghĩa là chưa đủ evidence để quyết định production.

## Quy tắc quyết định

- `GO`: mọi criterion bắt buộc là `COMPLETE` hoặc có `NOT_APPLICABLE` bằng evidence; không còn `OPEN`, `BLOCKED`, `FAILED`; owner vận hành và người phê duyệt ký decision record.
- `NO_GO`: có `FAILED` chưa remediation/waiver hợp lệ, hoặc stop condition/data-integrity/rollback criterion không đạt.
- `NOT_READY_FOR_DECISION`: còn `OPEN` hoặc `BLOCKED`, kể cả khi source analysis đã hoàn tất.
- `COMPLETE` chỉ có giá trị trong phạm vi criterion. `COMPLETE` cho source/design không phải runtime PASS.

## Decision criteria

| ID | Criterion | Điều kiện để đóng | Evidence hiện có | Trạng thái | Owner | Blocker hoặc bước tiếp theo |
| --- | --- | --- | --- | --- | --- | --- |
| GNG-01 | Endpoint provenance và net diff | Hai refs peel đúng SHA; ngoại lệ shallow/non-ancestor được công bố; inventory đối soát Git | README/plan và master inventory: 4.434 rows, exact endpoint SHAs, rename setting | COMPLETE | ANALYSIS | Không còn blocker source; không diễn giải commit count thành release history |
| GNG-02 | Binary impact classification | Mọi component row có `affect` hoặc `trivial`; partition và counts khớp | 1.671 affect + 2.763 trivial = 4.434; strict validator pass | COMPLETE | ANALYSIS | Reopen nếu endpoint/inventory thay đổi |
| GNG-03 | Finding và validation design coverage | Mọi affect trỏ finding; mọi unique finding có đủ quality dimensions và runtime gate; mọi gate có As-Is/action mapping | 15 owner closed; strict quality audit 188/188; 52 gates, 24 As-Is groups, 34 actions; validators pass | COMPLETE | ANALYSIS | Design complete không thay runtime execution |
| GNG-04 | Exact delivery artifacts | Package/image/cephadm/plugin/SBOM được pin và truy nguyên tới hai endpoint | 12 pin đã định nghĩa và selector source đã audit; 12/12 vẫn `PENDING_INPUT`, chưa có deployment artifact manifest | OPEN | UNASSIGNED | Hoàn tất `AS-001`, H3-B01, PIN-01→12 và `LAB-001` |
| GNG-05 | As-Is cluster và client inventory | Capture đủ topology, versions, backends, config, services, clients, integrations, SLO và snapshots | 24 nhóm đã thiết kế nhưng 24/24 `NOT_CAPTURED` | OPEN | UNASSIGNED | Capture `AS-001`→`AS-024` bằng quyền read-only và redaction review |
| GNG-06 | Applicability và unsupported backend | FileStore, optional backends/features và external consumers có disposition có bằng chứng | Applicability còn unknown; chưa chứng minh zero FileStore hoặc optional feature usage | OPEN | UNASSIGNED | Đóng H3-B03, H3-B14→B18; dùng `NOT_APPLICABLE` chỉ khi có artifact |
| GNG-07 | Ownership, window và thresholds | Mỗi action/gate applicable có owner, deadline, stop threshold, run ID và evidence location | 34/34 actions `PENDING_INPUT`; owner hiện `UNASSIGNED` | OPEN | UNASSIGNED | Gán owner và phê duyệt latency/recovery/scrub/service thresholds |
| GNG-08 | Exact-hop lab P0 | Mọi P0 applicable chạy bằng exact artifacts, có workload, failure injection và raw evidence | 19 test pack đã chọn, 45 target source asset đã xác minh; runtime evidence manifest/validator đã có nhưng 19/19 pack cùng 52/52 gate vẫn `NOT_RUN` | OPEN | UNASSIGNED | Chạy prerequisites rồi P0 theo thứ tự TP-01→19 và LAB-001→054; validate evidence index ở complete mode |
| GNG-09 | Mixed-version và client compatibility | MON/MGR/OSD/MDS/RGW cùng client-old/new đạt matrix, failover và state convergence | Chỉ có source finding và scenario design; chưa có mixed cohort result | OPEN | UNASSIGNED | Hoàn tất H3-M01→M06, đặc biệt `LAB-005`, `LAB-010`→047 applicable |
| GNG-10 | Canary và stable window | Canary đúng topology/artifact đạt SLO, health/data/service convergence trong window định trước | Chưa có canary topology, threshold hoặc runtime archive | OPEN | UNASSIGNED | Chốt canary cohort, stable-window duration và stop/escalation policy |
| GNG-11 | Rollback rehearsal | Package/container, control-state và data clone rollback đạt trước irreversible point | Có thiết kế H3-R01→R04; chưa rehearsal | OPEN | UNASSIGNED | Chạy `LAB-051`, `LAB-053` và restore tests; không dùng production làm fixture |
| GNG-12 | Security và external integration continuity | Auth/TLS/KMS/registry/LB/broker/NFS/SIEM contracts và secret handling đã test | Findings/design có sẵn; inventory và negative tests chưa chạy | OPEN | UNASSIGNED | Hoàn tất H3-B17, `LAB-017`, `LAB-046`, `LAB-047`, `LAB-049` |
| GNG-13 | Evidence closure và waivers | Không thiếu P0 evidence; blocker/waiver có owner, expiry, scope và approval | Đã có schema/validator chặn PASS thiếu raw output/oracle/timeline; chưa có runtime archive và action/gate status chưa đóng | OPEN | UNASSIGNED | Hoàn tất `AS-024`, H3-A01, `LAB-054` và manifest `RUNTIME_EVIDENCE_COMPLETE` |
| GNG-14 | Irreversible boundary và final floor | Full Reef inventory, old-client negative test, rollback sign-off và approval riêng trước release/client floor | Source xác định boundary; `LAB-052` chưa chạy và chưa có approval | OPEN | UNASSIGNED | Giữ nguyên floor trong mixed phase; chỉ xét sau stable window |

## Snapshot quyết định hiện tại

| Trạng thái criterion | Số lượng | Ý nghĩa |
| --- | ---: | --- |
| COMPLETE | 3 | Source provenance, binary classification và coverage design đã đóng |
| OPEN | 11 | Cần artifact, As-Is, owner hoặc runtime evidence |
| BLOCKED | 0 | Chưa ghi blocker cụ thể vì đầu vào chưa được cấp |
| FAILED | 0 | Chưa chạy nên không có runtime failure result |
| NOT_APPLICABLE | 0 | Chưa có As-Is evidence để loại trừ criterion |

Không được đổi kết luận sang `GO` chỉ bằng cách sửa bảng trạng thái. Decision record cuối phải trỏ tới exact artifact manifest, As-Is archive, từng runtime result, rollback rehearsal và chữ ký owner/approver.
