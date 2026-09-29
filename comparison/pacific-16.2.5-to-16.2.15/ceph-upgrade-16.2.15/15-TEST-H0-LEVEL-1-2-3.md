# Test H0-R và H0-W Level 1 / 2 / 3

[Mục lục](00-README.md) · [Đặc tả rút gọn](11-PA1-H0-LEVEL-1-2-3.md) · [Đo overhead](09-TEST-HIEU-NANG.md)

**Nguồn:** giữ ID R01–R03, W01–W10 và P01 của H0 feature v2.1 tại [S17](13-NGUON-VA-DOI-CHIEU.md). **Trạng thái mọi bài:** NOT_RUN. Fault injection chỉ trên lab/corpus disposable có đúng build H0; không gọi bài checksum ứng dụng cũ là test ACK gate.

## 1. Chọn bài theo phase

| Phase | Bắt buộc cho run đã chọn | Bằng chứng |
| --- | --- | --- |
| Trước production canary | Rehearsal H0-R; happy/error/retry/failover cases của level; native đối chứng; đo budget | Build/capability, không success sai, profile/corpus chuẩn |
| Trong PA1 canary | R01 trên mỗi tập PG return, kiểm actual X/epoch, W01 và quan sát mọi write theo policy, P01 | RETURN_VERIFIED trước arm; trace commit/verify/reply từng write |
| Sau nâng | Kiểm corpus đúng checkpoint, reconcile request dở; chạy lại regression liên quan nếu build/config đổi; P01/P-06 | Không unresolved committed-unverified; đúng level/coverage và SLO |

R02/R03 và W02–W10 là bài lỗi/negative trên lab hoặc canary disposable phù hợp; không inject lỗi storage trên production. Runtime production vẫn giám sát những điều kiện lỗi này, nhưng không chủ động gây ra chúng để đủ bảng test.

## 2. Fixture bắt buộc

- Replicated PG khỏe, đủ bản; ghi size/min_size và acting set. Không dùng size=1 để nghiệm thu replica verification Level 2/3.
- RADOS object mới, một full-object write, payload cố định trước hash; không overwrite/delete trong cửa sổ verify. Khóa seed/representation/range và operation identity.
- H0-static tạo trước lượt chuyển cho corpus recovery; Hclient riêng cho write mới. Target không được sửa reference để đạt MATCH.
- X có primary verifier/success gate. L2/L3 cần mọi peer bắt buộc có protocol/verifier; L3 thêm local reader sau commit ở X và peer.
- Instrumentation xác định điểm lỗi A/B/C/D/E, actual OSD, policy/epoch, commit/verify/reply. Phân biệt native phát hiện trước H0 với H0 thật sự phát hiện.
- Có budget timeout/rate/concurrency/read amplification/p99 và recovery/scrub; điền từ số đo, không tự đặt ngưỡng an toàn chung.

## 3. H0-R dùng chung mọi level

| ID | Kịch bản | PASS | FAIL/STOP |
| --- | --- | --- | --- |
| R01 | PA1 trả corpus đúng về X, PG hội tụ | RETURN_VERIFIED sau deep-scrub mới sau recovery và H0-static local-X verify đúng version/range | Dùng scrub cũ hoặc chỉ active+clean để mở gate |
| R02 | Local X sai, peer cùng version còn đúng | Gate đóng; lưu native/H0 evidence riêng, xác định bản/byte đã kiểm | Mở gate dù mismatch hoặc tự repair/rebaseline để che lỗi |
| R03 | GET/client read MATCH nhưng chưa chứng minh đọc X | Không RETURN_VERIFIED; báo thiếu local evidence | Coi client read qua peer/cache là X PASS |

Ghi coverage corpus, metadata ngoài scope và tuổi reference. H0-R không tự chọn nguồn repair; thiếu payload đúng phải xử lý theo [10](10-STOP-FALLBACK-ROLLBACK.md).

## 4. H0-W theo level

“Không có bảo đảm” không có nghĩa buộc L1/L2 trả success khi lỗi. Native checks có thể bắt; ghi đúng lớp phát hiện, không gán năng lực chưa implement cho level đó.

| ID | Kịch bản | Level 1 | Level 2 | Level 3 |
| --- | --- | --- | --- | --- |
| W01 | Payload/reference đúng | Success sau native + B | Success sau native + B/C | Success sau native + B/C/D ở mọi OSD bắt buộc |
| W02 | Đổi ABC→AXC trước B, reference còn ABC | B bắt, không success | Như L1 | Như L1 |
| W03 | Đổi replica buffer trước C, native transport checks tương ứng vẫn hợp lệ | Không có bảo đảm replica verifier | C bắt, không success | C bắt, không success |
| W04 | Store đổi bytes sau buffer checks, checksum nội bộ tự khớp bytes sai | Không có bảo đảm read-back | Không có bảo đảm read-back | D bắt trên X/peer lỗi, không success |
| W05 | Reader trả cache/buffer đúng cũ, backing store sai | N/A read-back gate | N/A read-back gate | Không nghiệm thu reader này là persisted read-back |
| W06 | Thiếu/sai reference/identity/range hoặc capability | Không bypass; kiểm capability L1 | Kiểm peer; không hạ L1 | Kiểm reader; không hạ L1/L2 |
| W07 | Commit xong, verify chưa xong rồi crash/retry | Không success chỉ từ commit nếu policy evidence thiếu | Giữ peer result binding | Xử lý COMMITTED_UNVERIFIED/read-back state |
| W08 | Verify đạt, reply mất, client retry | Kết quả đúng operation/policy, không mutation thừa | Tương tự | Tương tự |
| W09 | Đổi level/primary/acting set/epoch giữa run | Không dùng policy/evidence stale | Kiểm lại peer capability/binding | Kiểm lại reader/version/binding |
| W10 | Native commit lỗi dù H0 MATCH | Không success | Không success | Không success |

### Điểm kiểm thêm trong W04–W07

- W04 inject tại local store X và peer đại diện; chỉ đọc lại X chưa đủ L3. PUT hợp lệ với Hclient mới không mô phỏng “sai nhưng checksum tự khớp”.
- W05 cần bằng chứng reader/cache/durable completion; cờ “no-cache” hoặc GET sau success không đủ.
- W07 thử crash trước commit, sau commit và trước reply; phân biệt `not_submitted / submitted / committed / uncertain`. Không gọi lỗi sau commit là write đã rollback.
- Duplicate không được bypass vì native history đã commit. Primary mới phải có capability, policy và verification state hợp lệ trước success.

## 5. P01 — Soak, tăng PG và đổi level

1. So cùng corpus/topology/offered load cho native-only đối chứng và từng level đã có build; native-only không là level H0.
2. Đo gate wait, p95/p99 write latency, IOPS, timeout/error, CPU hash, metadata, read-back bytes/IOPS, in-flight queue/RSS và recovery/scrub impact.
3. Tăng C theo PG/byte budget; lặp H0-R và capability trên PG mới trước primary workload.
4. Kiểm mất web/controller không làm operation đã nhận bỏ gate; mất capability/failover thì đóng admission đúng scope.
5. Đổi level bằng đóng admission → reconcile request dở → policy revision/run mới; không tự fallback khi chậm.

PASS khi invariant đúng, coverage đủ, không incident chưa xử lý và performance trong budget. Level chưa implement là NOT_RUN/CAPABILITY_MISSING, không kế thừa PASS level thấp.

## 6. Evidence và nghiệm thu

Mỗi attempt lưu run/policy revision/level yêu cầu và thực tế; object/request/op/generation/range; expected/observed digest; verifier stage; OSD/role/build/capability; PG interval/epoch; commit/verify status; reply result/flags/time; latency/timeout. Giữ mismatch đầu dù retry sau thành công.

| Kết luận | Điều kiện |
| --- | --- |
| H0-R PASS | R01–R03 nghiệm thu lab; runtime scope có fresh scrub và local-X static verification |
| H0-W Level 1 PASS | A/B/E đúng, native completion giữ nguyên; ref/error/retry/failover áp dụng đã thử |
| H0-W Level 2 PASS | L1 + C/protocol và binding ở mọi replica bắt buộc |
| H0-W Level 3 PASS | L2 + D ở X và mọi peer; reader/cache/version/commit/retry được chứng minh |

Kết luận chỉ dành cho artifact/profile/scope đã thử; không tự kế thừa sang EC, partial write hoặc adapter RBD/RGW chưa nghiệm thu.
