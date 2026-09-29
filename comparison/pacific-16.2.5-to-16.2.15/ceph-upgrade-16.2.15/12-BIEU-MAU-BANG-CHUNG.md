# Biểu mẫu As-Is, nhật ký và nghiệm thu

[Mục lục](00-README.md) · [Gate](06-GATE-VA-NGUONG.md) · [Tests](08-TEST-CHUC-NANG.md)

Sao chép các bảng cần dùng cho mỗi đợt nâng. Ô trống có nghĩa chưa có bằng chứng, không phải PASS. Không ghi keyring, token, credential hoặc nội dung nhạy cảm vào gói evidence chia sẻ.

## 1. Change manifest

| Trường | Giá trị |
| --- | --- |
| Change ID / FSID / môi trường | |
| Người điều phối / owner storage, network, application | |
| Thời gian, timezone, window tối đa | |
| Base image digest + version/build SHA, vendor delta | |
| Target image digest + version/build SHA, vendor delta | |
| Nhánh thực thi | cephadm / khác: … |
| Daemon scope / host cohort / offline inventory | |
| Scope nâng PA1 và scope H0 C/corpus/writers | Ghi riêng, không suy C = toàn P_X |
| Client scope: librbd/QEMU/krbd/SDK và version | |
| Pool/rule/class, replicated/EC, size/min_size | |
| Phương án OSD | PA1: X online khi chuyển PG → DR_READY → nâng X → return canary |
| H0-R | H0-static corpus/version/range, local-X reader, fresh deep-scrub evidence |
| H0-W level đã chọn | L1_PRIMARY_BUFFER / L2_REPLICA_BUFFER / L3_PERSISTED_READBACK; chọn một/run |
| H0 run ID / policy revision / artifact SHA | |
| H0 capability theo X và mọi required peer | Build/protocol/hook B/C/D/E, readiness, bằng chứng lab |
| H0 workload/adapter scope | RADOS new-object full-object write; giới hạn/ngoại lệ phải ghi rõ |
| Hclient reference contract | Nơi tính trước X, identity, immutable storage, access và binding |
| Restore/fallback/forward-fix đã chọn; RPO/RTO | |
| Nguồn payload phục hồi / retention | |
| Evidence root / quyền truy cập | |
| Gate decision | HOLD / GO CANARY / GO BATCH / COMPLETE |

## 2. Applicability

| Điều kiện / C-ID | YES/NO/UNKNOWN | Bằng chứng thực | Việc cần sửa hoặc “không cần sửa” | Test liên quan | Owner |
| --- | --- | --- | --- | --- | --- |
| Cephadm + cần canary filters / C06 | | | | PRE-02, CAN-01 | |
| Allocator/mClock/device overrides / C07–C09 | | | | CON-STORAGE | |
| Dashboard HTTPS/TLS / C10 | | | | CON-CONSUMER | |
| RGW Vault / C11 | | | | CON-RGW | |
| Config parser/key cũ / C12 | | | | PRE-02, CON-CONSUMER | |
| Custom MGR/alerts / C13 | | | | PRE-04, CAN-01 | |
| Browser POST / C14 | | | | CON-RGW | |
| CephFS/NFS/Manila / C15 | | | | CON-FS | |
| Client PWL/mirror/fast-diff / C16 | | | | CON-RBD, P-05 | |
| RPM/DEB/custom/platform / C17 | | | | CON-PLATFORM | |
| Store pre-Pacific/quick-fix / C18 | | | | CON-STORAGE | |
| EC / multisite / worker features | | | | CON-EC, CON-RGW-BG | |
| PA1 + H0-R / C19 | YES | | | EXT-PA1, R01…03, P-04/P-06a | |
| H0-W level/capability / C20 | YES; ghi level | | | W01…10 áp dụng, P-06b | |

Nếu một dòng gom nhiều tính năng, trả lời từng tính năng trong cột bằng chứng; không dùng một chữ NO che đi phần chưa kiểm.

## 3. Nhật ký trạng thái tạm

| Entry | Scope/owner | Giá trị ban đầu | Giá trị tạm / lý do | Điều kiện phục hồi / hạn | Giá trị cuối / thời điểm / evidence |
| --- | --- | --- | --- | --- | --- |
| Balancer | | | | | |
| Autoscale mode từng pool | | | | | |
| noout / scrub / cờ khác | | | | | |
| W0/R0/A0 của X | | | | | |
| Upmap từng PG và cặp có sẵn | | | | | |
| Managed/unmanaged, service spec | | | | | |
| LB drain / maintenance / silence | | | | | |
| Key/workaround/config mask | | | | | |
| H0-W admission / run / policy revision | | | | | |
| H0 level / capability X và peers | | | | | |
| H0-R scrub window / local-reader config | | | | | |

## 4. Nhật ký một OSD/batch

| Trường | Giá trị |
| --- | --- |
| Batch ID / danh sách X / host / failure domains | |
| Layout/media/device identity, DB/WAL/dm-crypt | |
| Expected PG up/acting/primary và map epoch | |
| P_X đầy đủ và PG canary C; map diff ngoài scope | |
| Peers/spare, byte dự kiến từng đích, headroom | |
| W0/R0/A0 và entry map liên quan | |
| `ok-to-stop` cho toàn tập: timestamp, exit code, raw output | |
| G1/G2/G5 trước thao tác | |
| Image/digest trước → sau | |
| Mốc prepare / chuyển PG / DR_READY / stop / start / up / return clean | |
| Fresh deep-scrub request + completed evidence: PG/epoch/participants/time | |
| Local-X verify: corpus/version/range, reader proof, RETURN_VERIFIED | |
| Mở protected workload: actual primary/acting epoch, level, policy revision | |
| Mốc H0-W arm / admission open / soak done / admission close | |
| Client p99, errors, offered/achieved load | |
| Byte ra/về, recovery rate, degraded PG-seconds, resource peak | |
| CAN/CON/EXT test IDs + kết quả | |
| Boundary đã vượt; nguồn phục hồi còn lại | |
| State tạm đã hoàn nguyên / còn giữ với lý do | |
| G6/G7: GO / HOLD / STOP; người xác nhận | |
| H0-G0/GR/GW/GC: kết quả + evidence riêng từng checkpoint | |

## 5. Kết quả test

| Run ID | Test/profile | Phase/cohort | Artifact + tool version | Expected | Actual | PASS/FAIL/N/A/NOT_RUN | Evidence | Owner/time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

Với H0, gắn thêm manifest theo [15](15-TEST-H0-LEVEL-1-2-3.md): request/attempt identity, Hclient và hash B/C/D theo level, required peers, native commit, integrity completion và SUCCESS_ACK timestamps; fault point nếu test lab. Chỉ ghi reference/hash được phép chia sẻ, không kèm payload nghiệp vụ.

| Request / attempt | Level / policy / epoch | Submit/commit state theo node | Verify còn thiếu hoặc lỗi | SUCCESS_ACK có/không + thời điểm | Quyết định đối soát / evidence / owner |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

## 6. Báo cáo hiệu năng

| Profile | Phase/state | Offered load | Achieved IOPS/ops/s hoặc MiB/s | p95/p99 + đơn vị | Error/retry | Resource/catch-up | Số mẫu/run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | Before steady | | | | | | |
| | Mixed canary | | | | | | |
| | After catch-up | | | | | | |
| | After steady | | | | | | |

| Profile | Before median + độ phân tán | After median + độ phân tán | Δ% | SLO / regression budget | Kết luận, nhiễu hoặc giới hạn |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

P-06 ghi riêng H0-R và từng run native-only/L1/L2/L3: cùng offered load/coverage, overhead hash, gate wait, read amplification và trạng thái committed-unverified. Không gộp số liệu khác level vào cùng một dòng “after”.

## 7. Gate, exception và nghiệm thu

| Gate | Scope | PASS/FAIL/HOLD/N/A | Evidence + thời điểm | Ngoại lệ/expiry | Người xác nhận |
| --- | --- | --- | --- | --- | --- |
| G0–G9: tạo một dòng từng gate | | | | | |
| H0-G0 / H0-GR / H0-GW / H0-GC: tạo từng dòng theo scope | | | | | |

Ngoại lệ ghi rõ ảnh hưởng, biện pháp thay thế và thời hạn; không dùng ngoại lệ để biến dữ liệu sai, sai artifact hay thiếu bằng chứng phục hồi thành PASS.

- [ ] Scope target hoàn tất; danh sách ngoài scope/offline đã đối chiếu.
- [ ] Data/functional tests đạt; regression và SLO đã đánh giá.
- [ ] H0-R có evidence mỗi batch return thuộc scope; H0-W đạt đúng level công bố và không có silent downgrade; PG ngoài H0 được ghi rõ.
- [ ] Mọi request commit/verify chưa rõ đã được đối soát; policy/admission cuối run đúng ý định.
- [ ] Cấu hình và state tạm được xử lý theo journal.
- [ ] Soak đủ; aftercare owner và thời gian theo dõi đã chốt.
- [ ] Nguồn phục hồi và evidence còn đúng retention.
- [ ] Quyết định cuối, hạn chế và công việc cho change tiếp theo đã ghi.
