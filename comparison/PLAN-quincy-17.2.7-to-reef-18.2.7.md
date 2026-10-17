# Kế hoạch so sánh Ceph Quincy 17.2.7 → Reef 18.2.7

## Phạm vi và nguồn

- Base ref: `v17.2.7`, peeled commit `b12291d110049b2f35e32e0de30d70e9a4c060d2`.
- Target ref: `v18.2.7`, peeled commit `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`.
- Worktree nguồn: `D:\career\VDT\GD2\upgrade_Ceph\ceph17.2.7`; Git `2.49.0.windows.1`; worktree sạch tại preflight ngày 10/10/2026.
- Rename detection: `--find-renames=50%`; inventory là net diff trực tiếp giữa hai endpoint.
- Repo là shallow clone và base không là ancestor của target. Hai ngoại lệ này đã được cho phép có chủ đích để lập endpoint inventory; vì vậy `commit_count=1` không được dùng làm lịch sử thay đổi. Khi cần commit/PR/test context, phải fetch object liên quan hoặc ghi evidence gap.

Net diff có 4.434 hàng: `A 984`, `D 365`, `M 2.667`, `R 417`, `T 1`; 401.909 dòng thêm, 197.647 dòng xóa, 7 binary, 3 mode change và 7 gitlink. Trạng thái `T` được giữ nguyên cho một file thường chuyển thành symlink; không ép thành `M`.

## Cấu trúc đầu ra

Suite ở [quincy-17.2.7-to-reef-18.2.7](./quincy-17.2.7-to-reef-18.2.7/) gồm `README.md`, [hồ sơ evidence As-Is](./quincy-17.2.7-to-reef-18.2.7/AS-IS-EVIDENCE.md), [runbook capture As-Is](./quincy-17.2.7-to-reef-18.2.7/AS-IS-CAPTURE-RUNBOOK.md), [ma trận runtime](./quincy-17.2.7-to-reef-18.2.7/LAB-RUNTIME-GATES.md), [runtime evidence manifest](./quincy-17.2.7-to-reef-18.2.7/RUNTIME-EVIDENCE-MANIFEST.template.json), [test-selection manifest](./quincy-17.2.7-to-reef-18.2.7/RUNTIME-TEST-SELECTION.md), [exact-hop pins](./quincy-17.2.7-to-reef-18.2.7/EXACT-HOP-PINS.md), [action register](./quincy-17.2.7-to-reef-18.2.7/UPGRADE-ACTION-REGISTER.md), [decision register](./quincy-17.2.7-to-reef-18.2.7/GO-NO-GO-REGISTER.md), cặp inventory `00` và 15 cặp component Markdown/CSV:

1. `01-osd-pg-recovery`
2. `02-bluestore-bluefs`
3. `03-rocksdb-block-device`
4. `04-mon-osdmap-crush`
5. `05-messaging-auth-common`
6. `06-config-defaults`
7. `07-mgr-modules-monitoring`
8. `08-cephadm-orchestrator`
9. `09-ceph-volume-activation`
10. `10-rados-rbd-clients`
11. `11-cephfs-mds`
12. `12-rgw`
13. `13-build-packaging-submodules`
14. `14-security-cross-reference`
15. `15-upgrade-validation`

Mỗi changed-file row có đúng một owner. Danh sách file đầy đủ chỉ nằm trong CSV; Markdown không lặp bảng raw diff theo file.

## Schema và binary gate

Master inventory giữ nguyên 21 cột cơ sở. Component CSV là subset đúng thứ tự và thêm `upgrade_impact`, `finding_id`, `impact_reason` ở bên phải.

- `affect`: có causal path đã chứng minh tới chuẩn bị, rollout, mixed-version, restart/replay/recovery, dữ liệu, compatibility, rollback, observability hoặc validation của hop này.
- `trivial`: đã đọc hunk/metadata, commit intent và context cần thiết nhưng không có causal path như trên.

Không suy nhãn từ path, priority, churn, file type hoặc commit title. Hàng điều kiện vẫn là `affect`; điều kiện áp dụng nằm trong finding. Mọi `affect` phải có finding ID ổn định xuất hiện trong Markdown.

## Trình tự bằng chứng

1. Đọc raw endpoint diff và symbol ở cả hai tag.
2. Trace caller/callee, format/schema/config và state ownership khi cần.
3. Fetch/đọc commit hoặc test liên quan; shallow clone không được giả là có đủ history.
4. Chỉ dùng tài liệu, issue, PR, release note hoặc advisory chính thức để làm rõ intent/phạm vi.
5. Viết before/after, điều kiện kích hoạt, mixed/full-version, confidence, unresolved evidence và scenario kiểm chứng.

## Tiến độ

1. **Đã làm:** fetch target tag, chốt SHA/preflight và sinh lossless inventory 4.434 hàng.
2. **Đã làm:** phân owner, priority, file type và review mode cho toàn bộ inventory; tạo đủ 15 component CSV với binary fields để trống.
3. **Đã làm:** screen toàn bộ owner thành `affect|trivial`: 01 `160/190`, 02 `176/44`, 03 `18/3`, 04 `40/64`, 05 `105/90`, 06 `10/19`, 07 `78/592`, 08 `33/156`, 09 `21/194`, 10 `145/276`, 11 `186/387`, 12 `445/244`, 13 `152/75`, 14 `0/2`, 15 `102/427`. Toàn suite `1.671 affect / 2.763 trivial / 0` chưa phân loại, khớp 4.434/4.434.
4. **Đã làm:** đóng finding source cho toàn bộ `affect`, chạy strict complete validation và strict quality audit. Toàn bộ 188/188 finding đều có evidence anchor, before/after, applicability/activation, mixed/full behavior, impact, rollback boundary, confidence, validation và unresolved gap; 0 incomplete.
5. **Đã làm:** thiết kế 24 nhóm evidence As-Is read-only bao phủ đủ 52 runtime gate; validator xác nhận toàn bộ mapping. Đã thêm collector plan-first cho 23 core commands, redaction, immutable bundle và integrity validator. **Chưa thu:** collector chưa chạy với cluster và 24/24 nhóm vẫn `NOT_CAPTURED`.
6. **Đã làm:** thiết kế 52 gate exact-artifact lab/canary, failure injection và rollback; validator xác nhận 52 scenario bao phủ toàn bộ 188 finding ID duy nhất trong các report source. **Chưa chạy:** 52/52 gate đang `NOT_RUN`.
7. **Đã làm:** chọn 19 test pack bao phủ đủ 52 gate; kiểm 45 source assets tồn tại ở target SHA. Phân loại `3 NATIVE_HOP`, `4 REUSABLE`, `9 HYBRID`, `3 CUSTOM`; 19/19 vẫn `NOT_RUN`. Audit hai native subtree xác nhận 57 entry, 33 YAML parse sạch và 17/17 symlink resolve tới đích hợp lệ, kể cả chuỗi `.qa` lồng nhau; đây là source integrity, không phải runtime result.
8. **Đã làm:** audit floating selectors trong native suites và lập 12 exact-hop pins. Đã kiểm source counts/distro symlinks trực tiếp tại target; audit còn thấy 16 `branch: quincy`, 3 `cephadm_branch: quincy`, 3 base image tag nổi, 3 target image `$sha1` và 7 version check `$sha1`. Đã thêm JSON manifest template và validator `template|locked` để chặn nhãn `EXACT_HOP_VALID` khi thiếu artifact/digest/distro/harness/client/floor/archive evidence. 12/12 pin vẫn `PENDING_INPUT` vì chưa có artifact/harness runtime identity.
9. **Đã làm:** tạo runtime evidence manifest template liệt kê đúng 52 gate và validator `template|complete`. Complete mode yêu cầu exact-hop manifest hợp lệ, run-set/archive metadata, SHA-256 cho từng artifact và evidence theo status; self-test chứng minh validator từ chối `PASS` thiếu oracle/timeline. 52/52 vẫn `NOT_RUN`.
10. **Đã làm:** lập 34 action theo 18 BEFORE, 7 MIXED, 5 AFTER và 4 ROLLBACK; mapping bao phủ đủ 52 gate. **Chưa gán/chưa chạy:** 34/34 `PENDING_INPUT`, owner `UNASSIGNED`.
11. **Đã làm:** lập 14 decision criteria và validator tính trạng thái; hiện 3 source/design `COMPLETE`, 11 runtime/ownership `OPEN`, kết luận `NOT_READY_FOR_DECISION`.
12. **Còn mở:** gán owner, thu inventory As-Is, cấp exact artifact/topology/harness pins, adapt/implement test packs, chạy gate applicable, rehearsal rollback và xin phê duyệt GO/NO-GO production.

## Kiểm tra và tiêu chí hoàn thành

Trong giai đoạn khởi tạo, validator phải qua layout, schema, link, owner subset và partition ở `--mode complete` nhưng chưa yêu cầu binary verdict. Suite chỉ hoàn tất source analysis khi strict `--require-impact binary` qua, `affect + trivial = 4.434`, mọi `affect` map tới finding có evidence, không còn hàng trống và `audit_finding_quality.py --strict` đạt 188/188.

Lab/canary, As-Is applicability và rollback rehearsal là gate riêng trong `LAB-RUNTIME-GATES.md`; việc theo pha nằm ở `UPGRADE-ACTION-REGISTER.md`. Các validator chỉ xác nhận cấu trúc, coverage, cross-reference và status hợp lệ; chúng không chứng nhận evidence đã capture, action đã làm hay kết quả runtime. Hoàn tất source analysis hoặc gate design không tự tạo quyết định GO/NO-GO production và không cấp quyền chạy lệnh thay đổi cluster.
