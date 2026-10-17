# Mẫu run benchmark / kiểm dữ liệu

**Trạng thái mặc định: NOT_RUN.** Sao mẫu khi thực sự chuẩn bị run, không đổi thành PASS khi mới điền kế hoạch.

## Nhận diện và scope

| Trường | Giá trị |
|---|---|
| Run ID / ngày / owner | Chưa điền |
| Loại | UPGRADE / TOOL / LAB_VALIDATION |
| Cluster/FSID/môi trường | Chưa điền |
| Hop + source/target version/digest | Chưa điền |
| Comparison finding/action ID | Chưa điền |
| Console/collector/CLI/client/runner versions + hashes | Chưa điền |
| Wave/chain/rotation U→D, initial/final spare | Chưa điền |
| Inventory artifact/hash, plan/config/policy revision | Chưa điền |
| End state | KEEP_ROTATED_PLACEMENT |
| Dataset/object generation/hash, PG scope/proof | Chưa điền |
| Hardware/topology/CRUSH/pool/DB-WAL | Chưa điền |
| Profile: size/mix/iodepth/concurrency/rate/duration/cache | Chưa điền |
| Recovery/scrub/handoff/down/chain budgets | Chưa điền |
| SLO/stop criteria, window/min samples/repeats | Chưa điền |
| Chuẩn bị S nằm trong/ngoài phép đo | Chưa điền |
| Tool comparator: OFF/ON hoặc version cũ/mới | Chưa điền |
| Raw evidence URI/hash/retention, time sync | Chưa điền |

## Timeline và scrub coverage

| Stage | Step/PG/set revision | Mapping/incarnation | Request/start/completed | Result + artifact |
|---|---|---|---|---|
| BEFORE | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |
| PRE_HANDOFF deep-scrub toàn set | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |
| HANDOFF group | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |
| POST_HANDOFF deep-scrub group | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |
| SOURCE_UPGRADE / SPARE_ROTATED | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |
| END_STATE / AFTER_WAVE_STABLE | Chưa điền | Chưa điền | Chưa điền | NOT_RUN |

Lặp các dòng theo từng lượt và từng PG/group. Pre phải hoàn tất trên toàn set trước handoff; post mới sau catch-up, không tái dùng marker. Ghi errors/inconsistency/repair và evidence invalidated khi mapping/scope đổi.

## Kết quả đo

| Phase/cohort/operation | Offered/completed IOPS | MiB/s | p50/p95/p99 + sample count | Errors/timeouts/stall/SLO time | Quality + raw |
|---|---|---|---|---|---|
| Chưa đo | — | — | — | — | NOT_RUN |

| Tool/phase | Runtime/latency | CPU/RAM/IO/network | Queue/freshness/storage | Correctness | Comparator/limitations |
|---|---|---|---|---|---|
| Chưa đo | — | — | — | NOT_RUN | — |

Ghi riêng bytes chuyển, scrub time (queue + execution), handoff/redeploy/gate waits, retry, extra balancing và total time-to-stable.

## Verdict và cleanup

- Operation result / scope: NOT_RUN.
- Pre-scrub coverage + post-scrub coverage: NOT_RUN.
- Replica validation / spare cuối: NOT_RUN (NOT_EXERCISED nếu cuối run không nhận PG).
- QoS result / tool result / lab result: NOT_RUN.
- Comparability, gap/stale/reset/throttle, confounders: chưa đánh giá.
- HOLD/incident/resume và current mapping/evidence: chưa có.
- Cleanup asset của run, config tạm, mapping/owner bàn giao: chưa thực hiện.
- Kết luận, phần chưa chứng minh, owner xác nhận và timestamp: chưa có.

Thực hiện theo [protocol](README.md); kết quả mẫu hoặc thông số kế hoạch không phải số đo.
