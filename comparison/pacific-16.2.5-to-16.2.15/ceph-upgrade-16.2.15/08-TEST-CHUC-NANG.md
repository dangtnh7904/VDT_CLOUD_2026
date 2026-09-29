# Bộ test chức năng theo ba phase

[Mục lục](00-README.md) · [Test hiệu năng](09-TEST-HIEU-NANG.md) · [Mẫu kết quả](12-BIEU-MAU-BANG-CHUNG.md)

## 1. Phạm vi và cách chọn bài

Mọi kết quả ban đầu là **NOT_RUN**. Bài Core phải chạy trong scope tương ứng; bài Conditional chỉ chạy khi điều kiện có mặt; bài Lab dùng fixture/clone disposable, không inject corruption/power-cut hoặc repair trên dữ liệu production.

| Bộ | Khi chạy | Mục tiêu |
| --- | --- | --- |
| PRE-01…06 | Phase 1 | Baseline đúng, đường nâng đã diễn tập, có khả năng quan sát và phục hồi |
| CAN-01…06 | Phase 2 | MGR/MON/OSD/service hoạt động khi mixed-version; gate mỗi batch |
| POST-01…05 | Phase 3 | Dữ liệu đúng, cấu hình cuối đúng, dịch vụ ổn định |
| CON-* | Trước/sau thành phần có feature tương ứng | Kiểm khác biệt thực sự áp dụng |
| EXT-PA1 + H0-R/W/P | Theo scope PA1 + H0 đã chọn | Kiểm PA1 tại §6; H0 Level 1–2–3 ở [15](15-TEST-H0-LEVEL-1-2-3.md) |

Không phải tái chạy mọi unit/fault-injection test của Ceph trước từng OSD. Rehearsal được tái sử dụng nếu đúng artifact, topology, config và đường thực thi; runtime health/data/SLO gate vẫn phải lặp từng batch.

## 2. Phase 1 — Trước nâng cấp

| ID / mức | Tiền điều kiện và thao tác | PASS / bằng chứng | Khi không đạt |
| --- | --- | --- | --- |
| PRE-01 · Core | Thu As-Is, versions từng daemon/host/client, target digest, config, pools/rules, device mapping; điền C01–C20 | Manifest đủ, không UNKNOWN ảnh hưởng canary; snapshot có timestamp | HOLD G0/G1/G2 và H0-G0 |
| PRE-02 · Core, Lab/staging | Dùng đúng base image thực → target trên topology đại diện; thử config parse, MGR promotion/migration, một MON, OSD activation và client path | Đúng đường trực tiếp; không hidden mutation; logs/version/state đúng; mọi issue có disposition | HOLD G3 cho cohort thất bại |
| PRE-03 · Core | Tạo dataset riêng: RGW PUT/multipart nếu dùng; RBD write + flush. Lưu manifest expected bên ngoài đường dữ liệu thử; đọc lại trước nâng | Byte/hash, length, version/snapshot/range và metadata đúng; có dữ liệu cũ làm oracle | Sửa fixture hoặc điều tra hệ thống; không lấy dữ liệu sai làm baseline |
| PRE-04 · Core | Kiểm client probe + cluster telemetry; trên target staging thử `/metrics` bằng parser/scraper thật, golden queries và alert thử đúng kênh test | Freshness/parse/query đạt; có nguồn độc lập đủ signal khi MGR đổi; nhận được alert thử | HOLD G3 nếu không có đường quan sát phù hợp |
| PRE-05 · Core, Lab | Diễn tập đường phục hồi đã chọn: restore checkpoint hoặc rebuild replica từ nguồn còn tốt; xác minh hash và đo RPO/RTO | Phục hồi thật và đọc lại đúng; hiểu giới hạn dữ liệu sau checkpoint; artefact/source còn sẵn | HOLD G2; snapshot tạo được riêng lẻ chưa đủ |
| PRE-06 · Core | Chọn X/batch theo PG/failure domain/resources; PA1 dự báo map/byte toàn cụm từ snapshot, kể cả tác động tăng weight S, và rehearsal trên lab | Không overlap nguy hiểm; capacity từng đích đủ; gate cho whole set; manifest state đủ | HOLD G5; chọn lại batch hoặc giảm phạm vi |

### PRE-03 — Oracle dữ liệu tối thiểu

- RGW: lưu bucket/key, version ID nếu bật versioning, kích thước, SHA-256 tính từ payload gốc và metadata cần bảo toàn. Multipart/SSE có semantics ETag riêng; không dùng ETag như checksum độc lập chung cho mọi object.
- RBD: dùng image test riêng, ghi dữ liệu xác định vào range biết trước, flush theo contract rồi lưu expected bytes/hash/range cùng checkpoint hoặc snapshot. Dữ liệu đang thay đổi phải có sequence/version, không đối chiếu head mới với hash head cũ.
- Bao phủ old-data và new-data, overwrite, object/file rỗng, vài kích cỡ/range boundary đại diện, snapshot/delete-recreate nếu ứng dụng dùng. Định nghĩa số lượng và byte theo budget; ghi sample coverage.
- GET qua RGW hoặc read RBD bình thường chứng minh kết quả client nhận được. Nó không tự chứng minh replica cục bộ trên X đã được đọc; muốn kết luận đó phải dùng verifier/hook riêng được kiểm.

Các thao tác overwrite/snapshot ở trên là fixture kiểm native/application. Prototype H0-W hiện chỉ nhận **RADOS new-object full-object write** có reference từ generator trước primary; không tự gắn coverage H0 cho toàn bộ RGW/RBD. H0-static và Hclient có manifest riêng theo [15](15-TEST-H0-LEVEL-1-2-3.md).

## 3. Phase 2 — Trong canary và rollout

| ID / mức | Tiền điều kiện và thao tác | PASS / bằng chứng | STOP/HOLD |
| --- | --- | --- | --- |
| CAN-01 · Core MGR | Nâng standby/promote theo kế hoạch; đọc lại module, orch, actual digest và migration state; scrape/query qua đường thật; test Dashboard/custom consumers nếu có | Active target ổn định, không action ngoài scope chưa giải thích, telemetry đủ; G4 | Restart/migration loop hoặc mất control/observability |
| CAN-02 · Core MON/crash | Nâng từng MON, theo dõi quorum/rejoin/store/network/clock; xác nhận crash service thu thập đúng sau nâng | Quorum liên tục, không election loop, MON catch-up; crash evidence dùng được | Mất quorum hoặc không hội tụ; không nâng MON tiếp |
| CAN-03 · Core OSD | `ok-to-stop` sát thao tác; nâng đúng X; xem logs mount/replay/activation, block/DB/WAL, up/acting, recovery và client probe | Target image/identity đúng, không assert; PG tiến và trở về trạng thái dự kiến trong budget | Mount/replay fail, PG incomplete/unfound mới, data error hoặc SLO breach |
| CAN-04 · Core data | Khi actual mapping phù hợp, đọc old-data; ghi mới + flush/ACK theo client contract; read-back, overwrite và snapshot có dùng; ghi primary/epoch | Expected version/bytes đúng; không mất acknowledged write; phân biệt phép đọc client với local-X | Mismatch là STOP; giữ evidence trước mọi sửa |
| CAN-05 · Core service | RBD I/O liên tục; với RGW restart/drain từng endpoint, test direct rồi LB, PUT/GET/LIST/DELETE trên prefix test; POST negative nếu áp dụng | Dịch vụ đáp ứng contract và SLO; policy đúng; không bị retry che mất outage | Timeout/error/security fail quá ngưỡng; endpoint lỗi không nhận thêm traffic |
| CAN-06 · Core batch | Sau soak, so expected/actual count, state journal, resource/recovery trend và scope coverage | G6/G7 PASS, nguồn phục hồi còn tốt; đủ điều kiện thêm batch | Chưa đủ evidence, backlog/rủi ro tích lũy hoặc scope drift |

**CAN-04 khi X làm primary:** bài cần nhìn thấy X thực sự là primary của PG chứa dữ liệu thử. Ghi mới đúng ở client chỉ là test end-to-end. Để chứng minh H0 pre-ACK, chạy bộ H0-W ở [15](15-TEST-H0-LEVEL-1-2-3.md) với hook/evidence đúng level; PUT/GET sau SUCCESS_ACK không chứng minh bất kỳ level nào.

**Không dùng HTTP 200 hay process running làm kết quả PASS tổng hợp.** Ghi retry, failed attempt, outage duration và lỗi ứng dụng, kể cả request cuối cùng đã thành công.

## 4. Phase 3 — Sau nâng cấp

| ID / mức | Thao tác | PASS / bằng chứng | Không đạt |
| --- | --- | --- | --- |
| POST-01 · Core | Đối chiếu daemon/host/offline/client scope với manifest; kiểm quorum/services/action queue | G8: không bỏ sót đối tượng trong scope; ngoài scope có record | HOLD nghiệm thu |
| POST-02 · Core | Đọc lại old-data PRE và new-data CAN đúng checkpoint; chạy kiểm metadata và scrub/deep-scrub trong phạm vi đã chốt | Hash/version/metadata đúng; scrub không inconsistent; báo coverage thực | STOP phạm vi lỗi; không tự repair để đổi kết quả thành PASS |
| POST-03 · Core | So config/specs/flags/upmap/weight/affinity/autoscaler/balancer với journal; kiểm metrics/rules sau reload | State cuối đúng ý định, không cờ tạm bị bỏ quên, alert/query hoạt động | Hoàn nguyên có kiểm soát rồi test lại |
| POST-04 · Core service | Lặp RBD/RGW smoke và CON áp dụng qua đường client thật, qua LB và endpoint theo nhu cầu | Chức năng, auth và dữ liệu đúng trong full-target scope | HOLD G9 |
| POST-05 · Core soak | Quan sát qua chu kỳ tải đã chốt; xem restart/error/MON DB/DB-WAL/recovery/worker backlog | Không trend xấu chưa giải thích; benchmark 09 đạt và aftercare có owner | Mở incident/điều tra; chưa đóng change |

## 5. Bài có điều kiện

| ID / áp dụng | Trước nâng | Trong nâng | Sau nâng / PASS |
| --- | --- | --- | --- |
| CON-EC · Có EC pool trong scope | Lab đúng k+m/profile/plugin; read/write và rebuild; lỗi có kiểm soát chỉ trên fixture | Kiểm PG/min_size/recovery và end-to-end hash | Dữ liệu tái dựng đúng; không suy oracle replica đơn giản sang fragment EC |
| CON-RBD · Nâng client/feature dùng fast-diff, PWL, mirror, journal | Matrix client/kernel/QEMU; cache clean/dirty/layout; diff oracle; lock/mirror recovery trên lab | Kiểm đúng path có dùng; không đồng thời thêm feature | Diff khớp oracle; không dirty-cache loss, stale lock hay split-brain; mirror backlog hội tụ |
| CON-RGW · Vault, Browser POST, IAM/STS, TLS, multipart | Positive/negative auth; CA/encrypt/decrypt; payload multipart/timeout; đúng client matrix | Pin request từng endpoint để không che lỗi sau LB | Auth nhất quán; hash/version đúng; endpoint chưa có fix không được tính đóng security |
| CON-RGW-BG · Multisite, reshard, GC/LC/notification | Lab bucket riêng; ghi marker/expiry/delivery contract; không force reshard prod | Quan sát worker/sync backlog; mutation test chỉ fixture | Index/list/version/hashes hội tụ; event/expiry đúng contract, không yêu cầu repair để pass |
| CON-FS · Có CephFS/NFS/Manila | Clients, caps, rank/standby, export và state migration; session/replay/restore trên lab | Kiểm remount, MDS replay/session, export quyền và availability | Không damaged/read-only/replay kẹt; ranks/flags/caps/export đúng; không key vượt quyền |
| CON-PLATFORM · RPM/DEB/custom/AArch64/FIPS | Đúng transaction/artifact: user/key/unit/dependency/crypto/CRC/ISA-L nếu dùng | Activation đúng topology; log không lộ secret | Service/key/quyền đúng; không loader/crypto/data error |
| CON-STORAGE · Store legacy, allocator override, mClock, DB/WAL/dm-crypt | Clone/replay/activation với topology thực; OMAP/allocator chỉ test phần áp dụng | Theo dõi boot, correct mapping, capacity và effective config | Reopen/read-back đúng; không assert, false ENOSPC, checksum/metadata lỗi |
| CON-CONSUMER · Custom MGR/parser/alert/CLI | Test trên target API/schema/metric và rules runtime dự định dùng | Failover active và reload đúng checkpoint | Callback/query/parser/alert delivery đúng; không bắt sửa consumer vốn đã tương thích |

Các bài source-level sâu hơn như `cmpomap` U64, range-delete boundary, old FSMap, buffer fault hoặc PGLog inflation được định tuyến ở [13](13-NGUON-VA-DOI-CHIEU.md). Chỉ kéo vào test plan khi workload/history/custom delta hoặc recovery runbook làm chúng có ý nghĩa.

## 6. PA1 + H0

| ID | Phạm vi test | PASS |
| --- | --- | --- |
| EXT-PA1 | X online suốt lúc chuyển PG sang S/peers; kiểm toàn bộ P_X theo up/acting, raw/effective map ngoài scope, nguồn copy, dung lượng và DR_READY; sau nâng return từng batch và cleanup | Trước stop: mọi PG liên quan clean/đủ replica, up=acting, X không còn up/acting và whole-set ok-to-stop PASS; không remap ngoài manifest; mỗi batch có native gate, scope H0 thêm H0-GR/GW; journal khôi phục đúng |
| R01…03 | Sau recovery/backfill vào X: fresh deep-scrub và local-X đối chiếu H0-static | Chỉ mở gate khi đúng version/range và đọc bản X; không dùng GET từ peer hay scrub cũ thay bằng chứng |
| W01…10 | Kiểm write path A–E, fault point và retry/failover theo level | Native durable completion và mọi verify bắt buộc đều có trước SUCCESS_ACK; không silent downgrade, không false PASS do committed-only |
| P01 | Soak và tăng số PG/byte/IOPS theo từng gate | Correctness còn đạt, tài nguyên/ACK latency trong budget và đủ bằng chứng trước mở rộng |

Chi tiết setup, expected result theo từng level và phân bố ba phase nằm riêng tại [15](15-TEST-H0-LEVEL-1-2-3.md). H0-R là gate chung, không phải Level 1. Các bài H0-W kiểm B/C/D tương ứng Level 1/2/3; hook D ở Level 3 phải có trên X **và mọi replica bắt buộc**.

Trong lab replicated `size=3, min_size=2`, EXT-PA1 bổ sung mất thêm một OSD thuộc acting set **sau DR_READY** để kiểm giả thiết duy trì dịch vụ. Không inject production, không suy kết quả này sang mất host/rack/site hoặc EC. Không có bài “dừng X sớm để copy sau” trong PA1 đã chọn.

## 7. Bằng chứng tối thiểu cho mỗi bài

`test_id`, scope, prerequisite, base/target digest, tool/client version, seed/profile, start/end, expected, actual, PASS/FAIL/N/A/NOT_RUN, raw logs/JSON/hashes, gate liên quan và owner. Ghi riêng lỗi setup test với lỗi hệ thống; không thay thế kết quả cũ bằng lần retry đã PASS.

Các test viết trên test bucket/image riêng có ngân sách; các lệnh destructive/recovery nội bộ không được chạy trên production chỉ để tạo ảnh minh chứng.
