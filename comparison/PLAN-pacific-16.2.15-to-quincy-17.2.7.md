> **Điều hướng 13/10/2026:** [comparison tổng](README.md) thống nhất cách chuyển finding thành việc cần sửa/bỏ trước nâng, test và evidence. Kế hoạch phân tích H2 dưới đây tiếp tục giữ tiến độ và bằng chứng của bộ đang làm; workflow OSD theo [plan tổng PA2](../plan-tổng.md).

# Kế hoạch so sánh Ceph Pacific 16.2.15 → Quincy 17.2.7

## Phạm vi và nguồn

- Base: `v16.2.15`, commit `618f440892089921c3e944a991122ddc44e60516`.
- Target: `v17.2.7`, commit `b12291d110049b2f35e32e0de30d70e9a4c060d2`.
- Cùng một Git worktree: `ceph16.2.15/ceph`; HEAD ở base, worktree sạch, không shallow, cả hai commit hiện diện. Git `2.49.0.windows.1`; rename detection `--find-renames=50%`.
- Base **không** là ancestor của target. Đây là so sánh endpoint giữa hai release branch, được chạy với `--allow-non-ancestor`. `v16.2.15..v17.2.7` gồm 14.759 commit chỉ nằm phía target; đó không phải chuỗi commit tuần tự của một lần upgrade.
- Commit base mang ngày 2024-02-26, target mang ngày 2023-10-25. Target major mới hơn nhưng endpoint lịch sử cũ hơn; cần kiểm các backport chỉ nằm ở cuối nhánh Pacific.
- Cây `ceph17.2.7` riêng là shallow và không có object của base; không dùng để sinh diff, không cần chỉnh sửa hay tải lại.

## Số liệu net diff đã đối soát

`git diff --shortstat --find-renames=50%` và ba biểu diễn NUL-delimited của Git cùng cho **4.179 file**, `+276.334/-268.473` dòng; trạng thái `A 665`, `D 306`, `M 2.934`, `R 273`, `T 1`. Có 26 binary, 173 text record `0/0`, 9 mode change và 14 gitlink. `T` là một đường dẫn từ symlink sang file thường; bản sao script trong `tools/` hỗ trợ thêm trạng thái Git này mà không ép thành `M`.

## Cấu trúc và ownership

Thư mục suite là [pacific-16.2.15-to-quincy-17.2.7](./pacific-16.2.15-to-quincy-17.2.7/). `00` là master inventory; `01`–`15` theo [component map](../skills/ceph-version-comparison/references/component-map.md): OSD/PG, BlueStore, KV/block, MON/OSDMap, messaging/auth, config, MGR, cephadm, ceph-volume, RADOS/RBD, CephFS, RGW, build/package, security cross-reference, upgrade validation. Mỗi file đổi có đúng một owner; component CSV là subset theo owner. Danh sách file chỉ nằm trong CSV, không đặt thành bảng Markdown.

## Quy trình tiếp theo

1. **Đã làm:** gán group, owner, priority, file type và review mode cho toàn bộ 4.179 hàng bằng quy tắc trong `tools/classify_inventory.py`; validator `inventory` đã qua. Ownership này là triage cần được rà lại khi đọc hunk, không phải điểm rủi ro.
2. **Đã làm:** tạo 15 cặp CSV/Markdown cùng basename. CSV giữ nguyên 21 cột inventory và thêm `upgrade_impact`, `finding_id`, `impact_reason`; các nhãn tác động còn trống cho tới khi đọc bằng chứng.
3. **Đã làm:** đọc hunk/metadata, commit và caller để gắn đủ mọi hàng `affect` hoặc `trivial`. Cả 15 owner đã hoàn tất binary gate; toàn suite có `affect 1.736`, `trivial 2.443`, **0 hàng chưa phân loại**. Owner 15 chốt `75 affect`, `553 trivial`, `0` chưa phân loại. Không suy `trivial` chỉ từ đường dẫn, churn hay loại file; mỗi `affect` trỏ tới finding có bằng chứng, điều kiện và kịch bản kiểm chứng.
4. **Đã thiết kế, chờ dữ liệu:** [ma trận gate lab/runtime](./pacific-16.2.15-to-quincy-17.2.7/LAB-RUNTIME-GATES.md) có 43 scenario `NOT_RUN`; [runtime evidence template](./pacific-16.2.15-to-quincy-17.2.7/RUNTIME-EVIDENCE-MANIFEST.template.json) khớp chính xác 43 ID; [test selection](./pacific-16.2.15-to-quincy-17.2.7/RUNTIME-TEST-SELECTION.md) có 15 pack `NOT_RUN` và 28 source asset xác minh tại target; [exact-hop register](./pacific-16.2.15-to-quincy-17.2.7/EXACT-HOP-PINS.md) có 12 pin `PENDING_INPUT`. [As-Is register](./pacific-16.2.15-to-quincy-17.2.7/AS-IS-EVIDENCE.md) có 20 nhóm `NOT_CAPTURED`; [action register](./pacific-16.2.15-to-quincy-17.2.7/UPGRADE-ACTION-REGISTER.md) có 20 việc `PENDING_INPUT`; [GO/NO-GO register](./pacific-16.2.15-to-quincy-17.2.7/GO-NO-GO-REGISTER.md) là `NOT_READY_FOR_DECISION`. Native graph có 38 entry, 25 YAML sạch và 9/9 symlink resolve, nhưng selector nổi vẫn phải khóa theo run.
5. **Đã làm:** mười một kiểm tra offline qua layout, schema, partition, links, binary impact, native graph, manifest, test-pack assets, As-Is/action coverage, decision arithmetic và finding-quality baseline. [Quality audit](./pacific-16.2.15-to-quincy-17.2.7/FINDING-QUALITY-STATUS.md) đạt 44/441 và khóa không cho 397 gap tăng thêm. Gate quality strict-zero, lab/canary, rollback rehearsal và artifact provenance vẫn mở; source completion không đồng nghĩa GO/NO-GO production.

## Giới hạn

Net diff endpoint không mô tả mọi thay đổi trung gian hoặc revert. Git rename là heuristic, đặc biệt với file `0/0`. Gitlink chỉ chứng minh pointer đổi; cần đọc object dependency trước khi kết luận hành vi. Chưa có As-Is cluster, artifact triển khai, kết quả lab/canary hoặc rollback rehearsal; không đưa khuyến nghị GO/NO-GO. Mọi thao tác ở đây chỉ đọc mã nguồn, không tác động cluster.
