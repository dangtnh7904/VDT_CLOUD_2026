# PA1 và PA2 Lab Test — Kiểm PG đang có và so sánh hai phương án

**Mục đích.** Bài này dùng một hoặc vài PG trong cụm lab đang có để kiểm PA1 (X→S, nâng X, return về X) hoặc PA2 (X→S, nâng X; Y→X, nâng Y; chuyển vai spare), cùng read-back, scrub và write/read theo scope đã chọn. Không tạo validation pool, không dựng topology phụ, không yêu cầu helper OSD, dataset registry hoặc manifest phức tạp.

Bài test chỉ kết luận cho PG, pool, object và khoảng thời gian đã ghi trong evidence. Nó giúp kiểm quy trình và phát hiện lỗi trong fixture lab; không phải bằng chứng toàn bộ production PG sẽ có cùng kết quả.

Các mục 1–11 mô tả bài PA1 và các kiểm tra dùng lại; mục 12 bổ sung luồng PA2, mục 13 quy định so sánh trung lập. Chọn rõ phương án trước mỗi run; không có phương án mặc định. Đây là hướng dẫn kiểm thử, chưa phải kết quả đã chạy.

**Tài liệu liên quan:** [Phương án và so sánh PA1–PA2](PA1_PA2_OSD_Upgrade_Strategy.md) · [Controller](OSD_Upgrade_Data_Validation_Controller.md) · [Console](Storage_Lab_Console_OSD_Validation_and_Benchmark.md)

**Mục lục**

- [1. Thông tin cần điền trước khi chạy](#1-thông-tin-cần-điền-trước-khi-chạy)
- [2. Chọn PG và object test](#2-chọn-pg-và-object-test)
- [3. Baseline trước nâng cấp](#3-baseline-trước-nâng-cấp)
- [4. Drain X và nâng cấp](#4-drain-x-và-nâng-cấp)
- [5. Return X làm replica và kiểm read-back](#5-return-x-làm-replica-và-kiểm-read-back)
- [6. Deep-scrub PG đã chọn](#6-deep-scrub-pg-đã-chọn)
- [7. Khôi phục primary và kiểm read/write](#7-khôi-phục-primary-và-kiểm-readwrite)
- [8. Kết luận run](#8-kết-luận-run)
- [9. Chạy nhiều PG hoặc nhiều OSD trong lab](#9-chạy-nhiều-pg-hoặc-nhiều-osd-trong-lab)
- [10. Dọn dẹp](#10-dọn-dẹp)
- [11. Evidence tối thiểu](#11-evidence-tối-thiểu)
- [12. PA2 — Bài kiểm rotating spare](#12-pa2--bài-kiểm-rotating-spare)
- [13. So sánh PA1 và PA2 trong lab](#13-so-sánh-pa1-và-pa2-trong-lab)

## 1. Thông tin cần điền trước khi chạy

```yaml
run_id: <lab-run-id>
profile: PA1_PRODUCTION
fsid: <cluster-fsid>
target_osd: <X>
drain_osd: <S>
test_pool: <pool-lab>
test_pgid: <pgid-da-chon>
test_object: <object-test>
test_object_new: <object-test-generation-2>
target_image_digest: <digest>
old_image_digest: <digest-rollback>
read_write_mode: <read-only|read-write>
```

Chỉ dùng pool và object dành cho lab. Không ghi đè object customer hoặc object mà bài khác đang sử dụng.

## 2. Chọn PG và object test

Chọn PG đang `active+clean`, có X trong acting set hoặc có thể đưa X vào theo plan lab. Chọn object test đang có và dùng `ceph osd map` xác nhận nó rơi vào PG mục tiêu. Đổi tên object không làm X trở thành thành viên PG; nếu X chưa thuộc PG, chọn PG phù hợp hoặc thực hiện placement plan lab đã duyệt trước khi lấy baseline. Không thay CRUSH production chỉ để tạo test.

```bash
ceph -s
ceph osd tree
ceph pg <PGID> query -f json-pretty > evidence/pg-pre.json
ceph osd map <POOL> <OBJECT> -f json-pretty > evidence/object-map-pre.json
rados -p <POOL> stat <OBJECT>
rados -p <POOL> get <OBJECT> evidence/object-pre.bin
sha256sum evidence/object-pre.bin | cut -d ' ' -f 1 > evidence/object-pre.sha256
```

Ghi lại `up[]`, `acting[]`, primary thực tế, epoch, object locator và thời điểm. Nếu object map không trỏ đúng PG đã chọn, dừng và chọn object khác.

## 3. Baseline trước nâng cấp

Kiểm health, PG state, version/image của X/S, flags, affinity và mapping. Object baseline phải đọc được; hash được lưu bên ngoài OSD test.

```bash
ceph health detail > evidence/health-pre.txt
ceph osd versions > evidence/osd-versions-pre.txt
ceph osd dump -f json > evidence/osd-dump-pre.json
ceph osd crush tree > evidence/crush-pre.txt
ceph pg <PGID> query -f json-pretty > evidence/pg-baseline.json
```

Điều kiện: PG `active+clean`, không `inconsistent`, không missing/unfound, X/S không nằm trong down set của một bài khác, và có đủ capacity cho drain. Nếu không đạt, ghi `BLOCKED_PRECONDITION`.

Đọc baseline primary-affinity từ `evidence/osd-dump-pre.json`. Lệnh `ceph osd primary-affinity <id> <value>` là thao tác đặt giá trị, không phải lệnh truy vấn khi thiếu value.

## 4. Drain X và nâng cấp

Thực hiện theo MOP PA1: giảm primary duty, chuyển PG khỏi X sang S bằng mapping đã lập, chờ recovery/backfill và kiểm X không còn trong `up[]`/`acting[]` của scope. Thu output sau mỗi nhóm.

Dù chỉ đọc/checksum một PG mẫu, isolation phải kiểm toàn bộ PG thuộc scope hiện tại của X ở cả up và acting. Không dừng X dựa riêng vào việc PG mẫu đã chuyển xong; `ok-to-stop` phải xét cả maintenance/down set đang tồn tại.

```bash
ceph osd ok-to-stop <X>
ceph pg <PGID> query -f json-pretty > evidence/pg-drained.json
ceph -s > evidence/status-drained.txt
```

Chỉ khi isolation và maintenance gate đạt mới stop/redeploy X. Trong cửa sổ X down, bài lab không bắt tạo workload hoặc corpus mới; ghi lại thời gian down và trạng thái PG.

```bash
ceph orch daemon redeploy osd.<X> --image <TARGET_IMAGE_DIGEST>
ceph orch ps --daemon-type osd --refresh
ceph osd versions
```

X phải up/in, đúng version/digest, không có crash mới liên quan và vẫn chưa nhận PG ngoài admission.

## 5. Return X làm replica và kiểm read-back

Cho đúng PG đã chọn quay lại X theo mapping lab. Chờ PG active+clean, X trong acting và actual primary vẫn là OSD khác.

```bash
ceph pg <PGID> query -f json-pretty > evidence/pg-replica.json
rados -p <POOL> get <OBJECT> evidence/object-replica.bin
sha256sum evidence/object-replica.bin | cut -d ' ' -f 1 > evidence/object-replica.sha256
diff -u evidence/object-pre.sha256 evidence/object-replica.sha256
```

Hash giống nhau cho object giữ nguyên là điều kiện của bài read-back. Hash này không thay cho deep-scrub và không chứng minh các object khác trong PG.

Read-back thông thường đi qua primary; nó không tự chứng minh bản sao vật lý trên X. Kết luận replica cần ghép actual role, hội tụ và deep-scrub mới sau admission.

## 6. Deep-scrub PG đã chọn

Chỉ request sau khi X đã catch-up. Lưu marker/query trước, request mới, rồi quan sát tới khi lượt scrub hoàn tất; request trả mã 0 không đủ.

```bash
ceph pg <PGID> query -f json-pretty > evidence/pg-pre-scrub.json
ceph pg deep-scrub <PGID>
ceph pg <PGID> query -f json-pretty > evidence/pg-post-scrub.json
ceph health detail > evidence/health-post-scrub.txt
```

Ghi `requested_at`, `started_at`, `completed_at`, target role, inconsistency, scrub error, repair event và evidence nguồn. Nếu không chứng minh được completion, kết quả là `BLOCKED_SCRUB_EVIDENCE`.

## 7. Khôi phục primary và kiểm read/write

Sau khi toàn return set đạt gate replica/scrub theo MOP, khôi phục affinity theo baseline hoặc policy lab đã ghi. PG mẫu đạt không mở gate cho các PG chưa kiểm. X trở thành primary chỉ khi mapping thực tế xác nhận điều đó; không suy từ giá trị affinity.

```bash
ceph osd primary-affinity <X> <BASELINE_OR_TARGET_VALUE>
ceph pg <PGID> query -f json-pretty > evidence/pg-primary.json
```

Nếu `read_write_mode=read-write` và bước kiểm primary được thực hiện, chỉ ghi object test mới/generation riêng sau khi object map trỏ đúng PG và X thực sự là primary. Nếu chưa đúng role, bước kiểm primary chưa đạt; có thể ghi `NOT_EXERCISED` cho riêng bước này nhưng không báo PASS toàn bài yêu cầu primary. Chế độ read-only bỏ qua ghi và ghi `write_validation=NOT_REQUESTED`.

Khối dưới là mẫu cho bước primary; kiểm output map/query trước khi chạy `put`:

```bash
ceph osd map <POOL> <OBJECT_NEW> -f json-pretty > evidence/object-map-new.json
ceph pg <PGID> query -f json-pretty > evidence/pg-before-write.json
# Chi tiep tuc khi OBJECT_NEW thuoc PGID va actual primary la X.
dd if=/dev/urandom of=evidence/object-post.bin bs=1M count=4 status=none
sha256sum evidence/object-post.bin | cut -d ' ' -f 1 > evidence/object-post.sha256
rados -p <POOL> put <OBJECT_NEW> evidence/object-post.bin
rados -p <POOL> get <OBJECT_NEW> evidence/object-post-readback.bin
sha256sum evidence/object-post-readback.bin | cut -d ' ' -f 1 > evidence/object-post-readback.sha256
diff -u evidence/object-post.sha256 evidence/object-post-readback.sha256
ceph pg <PGID> query -f json-pretty > evidence/pg-after-write.json
```

Bài write/read chỉ chứng minh đường client tới object test ở PG được chọn trong thời điểm đó. `diff` sai, write/read error, unexpected primary, PG không active+clean hoặc crash mới → `HOLD`.

## 8. Kết luận run

`PASS` khi tất cả điều kiện sau đúng:

- PG đã chọn active+clean trước và sau các mốc;
- X đúng image/version, return đúng vai trò và primary sau restore đúng plan;
- object baseline đọc lại có hash khớp;
- nếu đã yêu cầu write/read: object generation mới đúng PG, đúng role yêu cầu và có hash khớp; read-only ghi NOT_REQUESTED cho bước ghi;
- deep-scrub mới hoàn tất và không có inconsistency/scrub error/repair bất thường;
- không có write/read error hoặc crash liên quan;
- evidence đủ timestamp, mapping, command output và checksum.

`HOLD` khi có lỗi hoặc unexpected role. `BLOCKED` khi thiếu precondition hoặc scrub completion. `INCONCLUSIVE` khi có gap khiến không biết role/mapping trong critical window.

Kết quả phải ghi rõ `tested_pgid`, pool, object names, X/S, actual acting/primary, image digest, start/end time và phạm vi kết luận.

Ghi thêm mode và các bước đã kiểm/chưa kiểm; PASS chỉ áp dụng cho phạm vi đã yêu cầu và có evidence. Không dùng chữ “toàn cluster an toàn” cho một bài chỉ chạy trên một PG.

## 9. Chạy nhiều PG hoặc nhiều OSD trong lab

Có thể lặp bài trên một danh sách PG đã chọn, mỗi lần giữ `pgid`, object và evidence riêng. Nếu thử batch OSD, ghi `batch_size` và `max_simultaneous_down` riêng; không gọi batch tuần tự là nhiều OSD down đồng thời. Dừng khi PG overlap, capacity, recovery hoặc QoS vượt policy.

## 10. Dọn dẹp

Xóa chỉ object tạo bởi run. Với PA1, khôi phục affinity/flags/upmap theo ledger và chờ PG ổn định. Với PA2, xử lý theo desired end state của wave: giữ rotated mapping hợp lệ hoặc reconcile theo policy; không xóa override còn được lượt sau sử dụng. Không xóa object baseline trước khi report đóng. Nếu rollback, theo MOP thay OSD: R là device sạch chạy old image; không mở store X đã nâng cấp bằng binary cũ.

## 11. Evidence tối thiểu

```text
health-pre.txt / health-post-scrub.txt
osd-versions-pre.txt / osd-versions-post.txt
object-map-pre.json / object-map-new.json
pg-pre.json / pg-drained.json / pg-replica.json / pg-primary.json / pg-before-write.json / pg-after-write.json
object-pre.sha256 / object-replica.sha256
object-post.sha256 / object-post-readback.sha256
pg-pre-scrub.json / pg-post-scrub.json
command.log / run.json / result.md
```

Đây là bài kiểm lab bổ sung cho PA1 và PA2. Nó không thay thế gate production hoặc deep-scrub trên toàn bộ các PG cần admission, cũng không mở rộng kết luận từ PG đã chọn sang các PG khác.

## 12. PA2 — Bài kiểm rotating spare

### 12.1. Chuẩn bị phạm vi

Để kiểm được việc chuyển vai, chọn tối thiểu hai nguồn X, Y và một spare ban đầu S hợp lệ trong cụm lab đang có. Không cần dựng cụm mirror riêng. Nếu tài nguyên hiện tại không đáp ứng capacity, CRUSH/device class/failure domain hoặc redundancy của pool thì ghi BLOCKED; không hạ size/min_size để ép bài chạy.

```yaml
profile: PA2_ROTATING_SPARE
wave_id: <lab-wave-id>
chain_id: <chain-id>
initial_spare: <S>
planned_sources: [<X>, <Y>]
target_image_digest: <digest>
end_placement_policy: <KEEP_ROTATED_PLACEMENT|RECONCILE_TO_POLICY>
read_write_mode: <read-only|read-write>
fixtures:
  - source_osd: <X>
    pgid: <PG_X>
    object: <existing-lab-object-in-PG_X>
  - source_osd: <Y>
    pgid: <PG_Y>
    object: <existing-lab-object-in-PG_Y>
```

Chuẩn bị S đúng target image trước lượt X→S và tính riêng thời gian/bytes/QoS phát sinh khi chuẩn bị. Mỗi fixture phải có object map, actual acting/primary và hash baseline như mục 2; lưu dưới thư mục evidence của từng lượt để không ghi đè. Không giả định PG của Y giống PG của X. PG có overlap cần kế hoạch mapping đầy đủ qua từng lượt.

### 12.2. Hai lượt tối thiểu

| Bước | Thao tác | Bằng chứng cần giữ |
|---|---|---|
| 1. Admission S | S đúng digest, không phục vụ PG ngoài allowlist; kiểm cặp U=X, D=S | Inventory, capacity, topology, mapping plan, SPARE_ADMISSION_ALLOWED |
| 2. X→S | Chuyển nhóm canary, S là replica; active+clean; read-back object PG_X và deep-scrub mới | Hash so với baseline của PG_X, actual role, scrub completion; HANDOFF_GROUP_ACCEPTED |
| 3. Hoàn tất handoff X | Lặp hết handoff set; X vắng mặt trong up/acting của toàn scope; restore affinity S và chờ ổn định | Coverage toàn set, isolation X, HANDOFF_COMPLETE |
| 4. Nâng X | Recheck maintenance/down set rồi redeploy X; giữ X isolated | Digest/version, health, incarnation, SPARE_ROTATED; X là spare candidate |
| 5. Admission X | Kiểm lại cặp U=Y, D=X, capacity và CRUSH của nguồn mới | Kế hoạch Y→X, reservation mới; không tái dùng PASS của cặp X/S |
| 6. Y→X | Chuyển nhóm PG của Y; X là replica, active+clean, read-back PG_Y và deep-scrub mới | Hash baseline của PG_Y, actual role và scrub completion trên X sau nâng |
| 7. Hoàn tất handoff Y | Hết handoff set, Y isolated; restore affinity X, stable; sau đó nâng Y | HANDOFF_COMPLETE, maintenance gate, digest/health/isolation của Y |
| 8. Kết thúc wave | Y là spare cuối; xử lý desired end state, kiểm version coverage và stable window | WAVE_COMPLETE, AFTER_WAVE_STABLE, ledger đã xử lý đúng policy |

OSD giữ nguyên ID; đây là chuyển membership/dữ liệu qua placement của Ceph, không clone store hay đổi ID X thành S. Không có bước trả S→X bắt buộc. Bước 6 kiểm X bằng dữ liệu nhận từ Y sau khi X được nâng ở bước 4.

Dùng lại các lệnh read-back/checksum và deep-scrub ở mục 5–6 với PG/object của từng lượt; thay target bằng D hiện tại. Nếu kiểm write/read, chọn object mới đúng PG, ghi role tại thời điểm ghi và tách evidence từng lượt. Bước kiểm primary chỉ chạy sau khi toàn handoff set đạt, affinity được restore và D thực sự là primary.

Ở cuối bài hai lượt, Y có thể chưa nhận PG sau nâng: ghi `replica_validation=NOT_EXERCISED`. Image/health/isolation của Y vẫn phải đạt; không báo Y đã qua kiểm dữ liệu. Một PG mẫu PASS không thay thế gate admission cho toàn handoff set.

### 12.3. Pause, lỗi và cleanup

- Pause sau nhóm canary hoặc giữa hai lượt: không phát thêm mutation; ghi recovery đang chạy. Resume đối chiếu cluster và ledger, không mặc định lặp lệnh cũ.
- Thử điều kiện không hợp lệ trong lab: đích thiếu capacity, placement vi phạm failure domain, unexpected primary, thiếu scrub completion hoặc conflict mapping phải làm HOLD/BLOCKED.
- Khi lỗi, ghi nguồn replica còn lành theo mapping hiện tại và HOLD chain. Không tự đảo cả chuỗi hoặc mở store đã nâng bằng image cũ; nếu phải thay OSD thì dùng quy trình replacement sạch, tương thích.
- Cleanup theo end-state policy đã chọn. Nếu reconcile tạo thêm migration, tiếp tục đo QoS/bytes và đợi ổn định trước AFTER; không dừng đồng hồ ở lượt handoff cuối.

Evidence PA2 bổ sung `wave.json`, `chain.json`, mapping trước/sau mỗi lượt, handoff groups, version coverage, spare registry, dependency ledger và desired end state. Đây có thể là các JSON/output đơn giản của bài lab, không bắt dựng một framework riêng.

## 13. So sánh PA1 và PA2 trong lab

| Nội dung | PA1 | PA2 |
|---|---|---|
| Bài tối thiểu kiểm đủ đặc trưng | Drain X, nâng X, return về X | Hai lượt X→S và Y→X, kiểm việc X chuyển thành đích sau nâng |
| Replica được kiểm sau nâng | X nhận lại PG theo return plan | S nhận PG_X; X nhận PG_Y sau khi được nâng |
| Điểm kết thúc | Return/restore xong, AFTER_RETURN_STABLE | Cả wave và end-state policy xong, AFTER_WAVE_STABLE |
| Spare sau bài | S theo kế hoạch PA1 | Y ở cuối chuỗi ví dụ, có thể NOT_EXERCISED đường dữ liệu |
| Mapping cần theo dõi | Drain và return của từng run | Handoff từng lượt, dependency và end state của wave |
| Dữ liệu di chuyển | Cả drain lẫn return | Handoff và mọi chi phí chuẩn bị/reconcile/phát sinh |
| Phục hồi khi lỗi | Replica còn lành hiện tại, replacement sạch tương thích | Cùng nguyên tắc, tra mapping hiện tại của chuỗi |

Để so sánh số liệu, chạy PA1 và PA2 với **cùng tập nguồn được nâng** (ví dụ X và Y), cùng dữ liệu/workload, phiên bản đầu–đích, topology và budget recovery/scrub. Ghi phiên bản và chi phí chuẩn bị S. Không so một lượt PA2 với toàn bài PA1; không dùng downgrade store đã chuyển đổi để tạo lại baseline. Nếu không thể tái tạo trạng thái lab tương đương, báo `NOT_COMPARABLE` và giữ kết quả mô tả riêng.

Thu tổng bytes di chuyển, PG bị remap, thời gian toàn đợt, time-to-stable, offered/completed IOPS, p95/p99, errors/timeouts, I/O stall và số lần HOLD/can thiệp. Ghi rõ PG/OSD hàng xóm dùng chung tài nguyên; benchmark tắt không có nghĩa bỏ theo dõi QoS vận hành.

Ước lượng lý tưởng với cùng payload D là PA1 ~2D và PA2 ~D khi giữ rotated placement, trước mọi phát sinh. Báo số đo thực tế riêng; không suy ra PA2 nhanh gấp đôi hoặc không ảnh hưởng IOPS. Bảng kết quả không xếp hạng, không chọn phương án ưu tiên.
