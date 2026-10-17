# Benchmark — PA2 trước, trong, sau nâng cấp và các tool

**Cập nhật 09/10/2026. Trạng thái: kế hoạch, chưa chạy benchmark mới.** Thư mục này tập trung protocol, profile và kết quả đo của hai hop 16.2.5→16.2.15, 16.2.15→17.2.7; gồm cả công cụ được phát triển hoặc đổi phiên bản trong dự án.

[Plan tổng](../plan-tổng.md) · [Comparison](../comparison/README.md) · [Console](../code/README.md) · [Mẫu run](RUN-TEMPLATE.md).

## 1. Phạm vi và cách tổ chức

Benchmark trả lời: dịch vụ thay đổi ra sao trong PA2, mức ổn định sau nâng, chi phí deep-scrub/handoff và overhead/tool regression. Không so PA1–PA2; phương án đã chốt là rotating spare.

```text
benchmark/
  README.md                      Protocol và ma trận phép đo duy nhất
  RUN-TEMPLATE.md                Mẫu dùng cho upgrade, tool hoặc lab validation
  runs/<hop>/<run-id>/           Tạo khi thực sự chạy, không điền kết quả giả
    run.md                      Bản mẫu đã điền
    manifest.json               Profile, versions/digests, topology, policy, artifact hashes
    events.jsonl                Timeline từ controller/MOP, stage và step IDs
    raw/                        Output gốc runner/collector, PG/scrub evidence
    report.md                   Kết quả, gap, scope và kết luận
```

Raw lớn có thể ở evidence store ngoài Git; manifest lưu URI/hash/retention và quyền đọc, không chứa secret. Có thể dùng JSON/output đơn giản của lab, không bắt triển khai framework mới để bắt đầu.

## 2. Cửa sổ đo PA2

| Cửa sổ | Ranh giới | Nội dung cần tách |
|---|---|---|
| BEFORE | Warm-up xong, trước hoạt động can thiệp đầu tiên trong scope | Workload ổn định, baseline health/config/map/tool versions |
| DURING — SPARE_PREPARE | Chuẩn bị/nâng S nếu thuộc scope | Bytes/time/QoS của chuẩn bị, không bỏ khỏi tổng |
| DURING — PRE_HANDOFF_DEEP_SCRUB | Trước mỗi lượt U→D, deep-scrub toàn handoff set tại placement hiện tại | Completion mới/sạch của mọi PG trước khi bắt đầu handoff |
| DURING — HANDOFF | Chuyển PG theo group U→D, catch-up/peering/backfill | Mapping/actual roles, bytes/PG, spike/stall theo group |
| DURING — POST_HANDOFF_DEEP_SCRUB | Sau D catch-up/active+clean, deep-scrub mới từng group | Evidence sau chuyển độc lập với pre-scrub |
| DURING — HANDOFF_COMPLETE/UPGRADE/ROTATE | Restore affinity sau đủ coverage, nâng U isolated, U thành spare | Downtime/readiness/version, gate wait, lỗi/retry |
| DURING — END_STATE | Bàn giao rotated placement, restore cấu hình tạm, ổn định balancer nếu có | Mọi data movement bổ sung, ownership/gap |
| AFTER | Chỉ sau AFTER_WAVE_STABLE | Cùng profile/load, đủ sample/window đã chốt |

Plateau giữa X→S và Y→X vẫn thuộc DURING. Nếu S đã được chuẩn bị ngoài phép đo, ghi rõ phạm vi loại trừ và chi phí riêng; không báo thời gian đó như full end-to-end.

**Deep-scrub trước và sau là gate nâng cấp bắt buộc, kể cả benchmark tắt.** Pre lỗi/chưa đủ completion → không chuyển; post lỗi/chưa đủ → không mở group tiếp, restore affinity, nâng nguồn hoặc rotate. Bản ghi scrub có stage, PG/set/group revision, mapping/incarnation, request/start/completion, markers và result. Không dùng marker cũ hoặc scrub thường thay deep-scrub.

## 3. Chuẩn bị phép đo công bằng

- Pin hop, cluster/FSID, OSD hardware/class/DB-WAL/NIC, pool/CRUSH/replica policy, source/destination chain, versions/digests.
- Pin workload dataset/checksum, client/kernel/librbd/QEMU nếu áp dụng, Warp/fio và collector/controller versions.
- Ghi block/object size, operation mix, iodepth/concurrency hoặc offered rate, working-set size, duration, warm-up/cache policy và background load.
- Giữ recovery/scrub/chain/down-set budget giống nhau giữa run cần so. Mỗi thay đổi profile/runner throttle/pause tạo segment mới.
- Chốt SLO/stop thresholds, minimum sample count, steady window và repeats từ baseline/môi trường. Không dùng một ngưỡng lab mặc định cho production.
- Đồng bộ clock, ghi source/observed timestamps, sampling interval, stale/gap/counter reset và outage của observer.
- Chỉ ghi/cleanup vào asset lab thuộc run; không dùng raw-device fio trên OSD đang chứa dữ liệu.

## 4. Ma trận benchmark dịch vụ/nâng cấp

| ID | Bài đo | Chỉ số chính | Điều kiện kết luận |
|---|---|---|---|
| B01 | RBD: fio trên image/file lab, random/sequential, read/write/mixed theo tải thực | IOPS, MiB/s, latency histogram, errors, stall | Profile/asset/client và load model tương đương; giữ output gốc |
| B02 | RGW: Warp hoặc workload S3, PUT/GET/LIST/multipart theo feature dùng | Completed ops, throughput, p95/p99, error/retry/timeouts, checksum | Ghi endpoint/LB, credentials bằng reference, object layout/size |
| B03 | Một chain PA2 ít nhất hai lượt | Thời gian từng phase, total/time-to-stable, bytes recovery/backfill, handoff/PG count | X→S rồi Y→X; X sau nâng thực sự nhận PG |
| B04 | Deep-scrub trước/sau và recovery cạnh workload | Scrub queue/start/completion/duration, client latency, disk/DB/NIC/CPU | Tách PRE/POST và handoff; tính cả thời gian chờ scheduler |
| B05 | Tăng batch/chain theo các cohort đại diện | Peak capacity/resource usage, PG overlap, SLO violation, HOLD, completion rate | Batch size khác mức handoff/down/scrub đồng thời |
| B06 | Sau wave/hop ổn định | AFTER−BEFORE của dịch vụ, config/version/placement diff | Rotated layout được ghi là biến thay đổi; không quy mọi khác biệt cho binary |
| B07 | Fault/recovery của controller trong lab | Thời gian phát hiện/resume, duplicate/missing events, mutation duplication | Controlled fault scope, timeline; không fault production để đo |

Giám sát thêm quorum/health, slow ops, disk latency/utilization, CPU/memory, NIC, DB/WAL, fullness, recovery/backfill throughput và crash. Client throughput không đồng nghĩa disk IOPS.

## 5. Đo các tool được nâng cấp

Danh sách version thực điền từ inventory; không mặc định mọi tool đều cần nâng cùng Ceph. Đo trước/sau mỗi tool change và giữ Ceph/workload cố định khi có thể.

| ID | Tool/thành phần | Bài đo | Correctness đi kèm |
|---|---|---|---|
| T01 | OSD Info Collector và Ceph CLI adapter | Thời gian collect theo scope, command count/output bytes, CPU/RAM, freshness và timeout | Đủ OSD/PG, config/device/topology đúng, PARTIAL/UNKNOWN không thành 0 |
| T02 | Planner/readiness | Plan trên snapshot cùng topology, tăng số OSD/PG/chains | Mapping hợp CRUSH, full scope, không conflict/thiếu reservation |
| T03 | PA2 controller/worker/lease | Event lag, queue depth, gate latency, reconciliation và DB transaction cost | Không double mutation, timeout reconcile, pre/post scrub evidence không dùng chéo |
| T04 | API/UI/report | Response/render/report time theo số OSD/events/artifacts | Saved selection đúng, query/pagination đầy đủ, không mất evidence/hash |
| T05 | Evidence/DB/storage | Write/read/hash/export throughput, storage growth, recovery sau restart | Durable outbox/ledger, ordering, không mất dữ liệu khi queue/backpressure |
| T06 | Warp/fio/client libraries | Cùng Ceph + dataset/profile với tool cũ/mới | Output/unit/parser/latency semantics và checksum tương đương |
| T07 | cephadm/ceph-common/ceph-volume, exporter/Prometheus | Compatibility/action/collect/scrape duration trên đúng artifact | Dry/read-only trước; provisioning/destructive test chỉ lab riêng; parser và labels không mất |
| T08 | Console container image | Startup/readiness, idle/load CPU/RAM, image size và thời gian cài online/offline | Cùng digest trên hai profile được hỗ trợ; persistence/config/secrets đúng |

Đo overhead **tool OFF → ON** trên cùng cluster/version/load; sau đó mới so tool cũ → mới. Khi có thể, dùng ma trận Ceph nguồn/đích × tool cũ/mới; ô không tương thích ghi UNSUPPORTED. Nếu nhiều yếu tố cùng đổi mà không tách được, chỉ báo chênh lệch tổng hệ thống, không gán nguyên nhân cho tool hay Ceph.

Simulator/planner fixture lớn chỉ chứng minh chi phí xử lý dữ liệu đầu vào, không chứng minh thời gian drain hoặc QoS của cụm 1.600 OSD.

## 6. Cohort và bằng chứng đường dữ liệu

| Cohort | Bằng chứng cần có |
|---|---|
| REMAP | Object/range workload ánh xạ tới PG, PG thực sự thay membership U→D theo thời gian |
| NEIGHBOR | Không REMAP nhưng có giao nhau OSD/host/DB-WAL/NIC hoặc tài nguyên đã chứng minh |
| CONTROL | Mapping không đổi và không có giao nhau tài nguyên đã quan sát; vẫn có thể chung tài nguyên toàn cụm |
| UNATTRIBUTED/SERVICE_ONLY | Chỉ có endpoint/client metrics hoặc thiếu object→PG proof |

RADOS có object→PG map; RBD cần offset/layout→object resolver; RGW cần object/manifest/chunks và metadata liên quan. Read-back thường đi qua primary, không tự đọc riêng bản vật lý trên D. Không gọi S3-only/fio-only là số đo từng PG nếu chưa có resolver proof.

## 7. Bài kiểm dữ liệu PA2 trên PG lab đang có

Không bắt tạo pool hoặc cluster riêng nếu PG/asset lab hiện tại đáp ứng topology/capacity. Chọn ít nhất X, Y, S với hai handoff khả thi; không hạ size/min_size để ép test.

1. Chọn object lab trên PG của từng nguồn, xác nhận map/acting/primary và lưu hash bên ngoài OSD. Dataset đang ghi phải có generation/version/quiesce policy rõ, không so hai phiên bản hợp lệ khác nhau như corruption.
2. Lấy BEFORE, chốt toàn handoff set, chuẩn bị affinity/flags theo plan và chờ ổn định. Deep-scrub **mọi PG trong set** trước X→S và chờ completion sạch; read-back/hash mẫu là evidence bổ sung.
3. X→S theo group; S actual replica, hội tụ; read-back object không đổi, deep-scrub mới sau chuyển. Đủ toàn set mới restore affinity và handoff complete.
4. X isolated toàn up/acting scope, maintenance/down-set đạt, nâng X, kiểm digest/readiness; X thành spare.
5. Lặp pre-deep-scrub toàn set của Y trước Y→X. Sau chuyển kiểm read-back và post-deep-scrub; bước này kiểm đường dữ liệu của X sau nâng.
6. Nếu cần kiểm write/read-primary, tạo object lab generation mới đúng PG, xác minh actual primary D sau restore rồi ghi/đọc/hash. Nếu D không primary thì ghi NOT_EXERCISED, không gán PASS.
7. Nâng Y sau handoff complete; spare cuối chưa nhận PG ghi NOT_EXERCISED. Kết thúc rotated placement/stable window, lấy AFTER.
8. Cleanup chỉ asset của run; giữ baseline/report/evidence tới khi đóng. Mapping giữ theo desired end state, không xóa override còn dependency.

Pre-scrub chưa đủ coverage, post-scrub lỗi, unexpected primary, PG ngoài plan, stale marker và pause/resume giữa hai lượt phải có negative tests trong lab/simulator. Không cố gây hỏng dữ liệu customer. Một PG/object mẫu PASS chỉ kết luận cho mẫu đó; không giảm yêu cầu scrub toàn handoff set.

## 8. Báo cáo và cách đọc số liệu

Mỗi phase/cohort/operation báo offered/completed load, throughput, histogram/percentiles, failures/timeouts, stall dài nhất, thời gian vi phạm SLO, time-to-stable, PG/bytes và chi phí tool. Không lấy trung bình các p99; tính từ histogram/raw đủ chất lượng hoặc giữ từng window riêng.

- DURING−BEFORE: tác động bảo trì với workload đã kiểm soát.
- AFTER−BEFORE: khác biệt sau nâng; chỉ kết luận regression khi điều kiện đủ tương đương. PA2 đổi placement nên phải nêu confounder.
- Baseline 0/missing: giữ raw, không chia phần trăm. Gap không thành 0.
- Run chưa chạy = NOT_RUN; tùy chọn tắt = NOT_REQUESTED; đường dữ liệu chưa thử = NOT_EXERCISED; thiếu evidence = INCONCLUSIVE; điều kiện không tương đương = NOT_COMPARABLE.
- QoS/tool result tách operation/replica result. SLO đã chọn có thể HOLD bước tiếp theo; tắt benchmark không bỏ monitoring/gate scrub.
- Không công bố nhanh gấp đôi hoặc ETA 24 PB từ mô hình bytes lý tưởng hay OSD lab ít dữ liệu.

## 9. Nguồn và evidence lịch sử

- [MON closeout 01/10](../test/MON-20261001-QUORUM-VA-GATE-CLOSEOUT.md): MON target 3/3 nhưng gate HOLD, observer gaps và thiếu evidence; không phải baseline PA2.
- [S3 summary 02/10](../test/evidence-s3-20261002/summary.json): smoke ngắn, không thay gate MON/RBD/PA2 hoặc benchmark đầy đủ.
- [Validation console](../code/rgw-console/VALIDATION.md): test phần mềm và live helper theo scope; Warp/fio lifecycle và PA2 live chưa được công bố đạt.
- [Bản lab cũ](../docs/archive/2026-10-09/PA1_PA2_Lab_Test_Tren_PG_Hien_Co.md): nguồn kỹ thuật đã hợp nhất; workflow hiện hành là mục 7, không chạy PA1.
