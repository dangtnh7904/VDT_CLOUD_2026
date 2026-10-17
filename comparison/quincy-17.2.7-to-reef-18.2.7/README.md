# So sánh Ceph Quincy v17.2.7 → Reef v18.2.7

**Trạng thái ngày 12/10/2026: source analysis và binary impact gate đã hoàn tất cho toàn bộ owner 01–15. Strict finding-quality audit đạt 188/188 finding; ma trận As-Is/lab/rollback đã thiết kế đủ 52 gate nhưng 52/52 vẫn `NOT_RUN`; GO/NO-GO production còn mở.**

Hai endpoint được resolve trong cùng repo `ceph17.2.7`: base `b12291d110049b2f35e32e0de30d70e9a4c060d2`, target `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`. Đây là net diff trực tiếp; repo nguồn là shallow clone và base không là ancestor của target, nên không được diễn giải `commit_count=1` thành lịch sử release.

## Số liệu nguồn

- 4.434 changed-file rows: `A 984`, `D 365`, `M 2.667`, `R 417`, `T 1`.
- 401.909 additions, 197.647 deletions; 7 binary, 3 mode change, 7 gitlink.
- Phân owner: `P0 742`, `P1 1.513`, `P2 2.179`; các mức này chỉ là thứ tự đọc.
- Toàn bộ 4.434 hàng đã có một owner, file type, review mode và analysis decision.
- `affect 1.671`, `trivial 2.763`, **0 hàng chưa phân loại**; tổng khớp 4.434/4.434.

Một record `T` là `qa/suites/orch/rook/smoke/0-distro/ubuntu_20.04.yaml` chuyển từ file thường sang symlink. Inventory giữ raw mode/blob thay vì ép trạng thái. Bảy gitlink chỉ chứng minh pointer dependency đổi; nội dung dependency cần object/evidence riêng.

## Mục lục

| Nhóm | Báo cáo | CSV | Trạng thái |
| --- | --- | --- | --- |
| 00 — inventory | [Tổng quan](./00-file-inventory.md) | [CSV](./00-file-inventory.csv) | Hoàn tất inventory và triage |
| 01 — OSD/PG/recovery | [Báo cáo](./01-osd-pg-recovery.md) | [CSV](./01-osd-pg-recovery.csv) | Binary gate hoàn tất: 160 affect / 190 trivial |
| 02 — BlueStore/BlueFS | [Báo cáo](./02-bluestore-bluefs.md) | [CSV](./02-bluestore-bluefs.csv) | Binary gate hoàn tất: 176 affect / 44 trivial |
| 03 — KV/block device | [Báo cáo](./03-rocksdb-block-device.md) | [CSV](./03-rocksdb-block-device.csv) | Binary gate hoàn tất: 18 affect / 3 trivial |
| 04 — MON/CRUSH | [Báo cáo](./04-mon-osdmap-crush.md) | [CSV](./04-mon-osdmap-crush.csv) | Binary gate hoàn tất: 40 affect / 64 trivial |
| 05 — messaging/auth | [Báo cáo](./05-messaging-auth-common.md) | [CSV](./05-messaging-auth-common.csv) | Binary gate hoàn tất: 105 affect / 90 trivial |
| 06 — config/default | [Báo cáo](./06-config-defaults.md) | [CSV](./06-config-defaults.csv) | Binary gate hoàn tất: 10 affect / 19 trivial |
| 07 — MGR/monitoring | [Báo cáo](./07-mgr-modules-monitoring.md) | [CSV](./07-mgr-modules-monitoring.csv) | Binary gate hoàn tất: 78 affect / 592 trivial |
| 08 — cephadm/orchestrator | [Báo cáo](./08-cephadm-orchestrator.md) | [CSV](./08-cephadm-orchestrator.csv) | Binary gate hoàn tất: 33 affect / 156 trivial |
| 09 — ceph-volume | [Báo cáo](./09-ceph-volume-activation.md) | [CSV](./09-ceph-volume-activation.csv) | Binary gate hoàn tất: 21 affect / 194 trivial |
| 10 — RADOS/RBD | [Báo cáo](./10-rados-rbd-clients.md) | [CSV](./10-rados-rbd-clients.csv) | Binary gate hoàn tất: 145 affect / 276 trivial |
| 11 — CephFS/MDS | [Báo cáo](./11-cephfs-mds.md) | [CSV](./11-cephfs-mds.csv) | Binary gate hoàn tất: 186 affect / 387 trivial |
| 12 — RGW | [Báo cáo](./12-rgw.md) | [CSV](./12-rgw.csv) | Binary gate hoàn tất: 445 affect / 244 trivial |
| 13 — build/package | [Báo cáo](./13-build-packaging-submodules.md) | [CSV](./13-build-packaging-submodules.csv) | Binary gate hoàn tất: 152 affect / 75 trivial |
| 14 — security cross-reference | [Báo cáo](./14-security-cross-reference.md) | [CSV](./14-security-cross-reference.csv) | Binary gate hoàn tất: 0 affect / 2 trivial |
| 15 — upgrade validation | [Báo cáo](./15-upgrade-validation.md) | [CSV](./15-upgrade-validation.csv) | Binary gate hoàn tất: 102 affect / 427 trivial |

[Plan và tiêu chí hoàn thành](../PLAN-quincy-17.2.7-to-reef-18.2.7.md) ghi rõ provenance, ngoại lệ shallow/non-ancestor, schema và evidence workflow.

[Hồ sơ evidence As-Is](./AS-IS-EVIDENCE.md) chia đầu vào read-only thành 24 nhóm, bao phủ đủ 52 runtime gate; hiện 24/24 là `NOT_CAPTURED`. [Runbook capture](./AS-IS-CAPTURE-RUNBOOK.md) có collector plan-first, redaction, per-command metadata và SHA-256 bundle validator; chưa chạy với cluster. [Ma trận As-Is, lab/canary và rollback](./LAB-RUNTIME-GATES.md) ánh xạ 52 scenario tới toàn bộ 188 finding ID duy nhất trong các report source; [runtime evidence manifest](./RUNTIME-EVIDENCE-MANIFEST.template.json) giữ 52/52 `NOT_RUN` và validator complete-mode chặn PASS thiếu raw output/oracle/timeline. [Test-selection manifest](./RUNTIME-TEST-SELECTION.md) nhóm chúng thành 19 pack và đã xác minh 45 source asset tồn tại ở tag target; audit thêm hai native subtree có 57 entry, 33 YAML parse sạch và 17/17 symlink resolve hợp lệ; 19/19 pack vẫn `NOT_RUN`. [Exact-hop pin register](./EXACT-HOP-PINS.md) và [manifest template](./EXACT-HOP-PIN-MANIFEST.template.json) khóa 12 nhóm selector/artifact/distro/harness/archive bằng validator hai chế độ; 12/12 đang `PENDING_INPUT`. [Action register](./UPGRADE-ACTION-REGISTER.md) chuyển chúng thành 34 việc theo BEFORE/MIXED/AFTER/ROLLBACK; 34/34 đang `PENDING_INPUT`, owner chưa gán. [Decision register](./GO-NO-GO-REGISTER.md) có 3/14 criterion source/design `COMPLETE`, 11/14 `OPEN` và kết luận `NOT_READY_FOR_DECISION`. Các validator khóa coverage, ID, cross-reference, schema và status; thiết kế/capture gate không được diễn giải thành runtime PASS.

`tools/audit_finding_quality.py --strict` kiểm từng finding có đủ evidence anchor, before/after, applicability/activation, mixed/full behavior, impact, rollback boundary, confidence, validation và unresolved gap. Kết quả hiện tại: `188 complete / 0 incomplete`; đây là quality gate của tài liệu nguồn, không phải kết quả lab.

## Cách đọc và phương pháp

CSV dùng dấu `;`, UTF-8 BOM và CRLF. Master giữ 21 cột nguồn; component CSV thêm binary verdict fields. Mỗi changed-file row xuất hiện đúng một lần trong component partition. Markdown chỉ nhóm các behavior được promote thành finding, không chép lại raw file list.

Thứ tự đề xuất: đọc inventory và plan, sau đó các owner 06/03/14 nhỏ để khóa default/KV/security claim, tiếp theo control-plane 04/08/07, persistent data 01/02/09, client/service 05/10/11/12, rồi delivery và validation 13/15.

Mọi verdict cần hunk hoặc special Git metadata, endpoint symbol, context và khi cần commit/test. Shallow history là evidence gap phải được bù bằng fetch có mục tiêu; không suy từ commit title hoặc release family.

## Giới hạn và tái lập

Chưa có inventory As-Is, test repository hay lab/runtime result. Toàn bộ 52 scenario trong ma trận runtime đang `NOT_RUN`; bộ này chưa cung cấp quyết định GO/NO-GO production.

Tái lập inventory bằng `tools/build_inventory.py` với `--find-renames=50%`, `--allow-shallow` và `--allow-non-ancestor`; chạy `tools/classify_inventory.py` để tái tạo triage trên master mới. Không chạy lại classifier trên inventory đã có review thủ công vì sẽ ghi đè sáu cột triage cơ sở. Chạy toàn bộ 14 kiểm tra offline bằng `python tools/validate_all.py --repo ../../ceph17.2.7`; runner này gồm strict comparison/finding audit, mapping As-Is/runtime/test/action/decision, native-suite graph/link/YAML audit, source pins, exact-hop và runtime-evidence manifest self-test. Bundle As-Is thực tế vẫn phải kiểm riêng bằng `validate_as_is_bundle.py --bundle <path> --require-success`; manifest job thực tế phải kiểm bằng `validate_exact_hop_manifest.py --manifest <path> --mode locked`; evidence index hoàn tất phải kiểm bằng `validate_runtime_evidence_manifest.py --manifest <path> --mode complete`.
