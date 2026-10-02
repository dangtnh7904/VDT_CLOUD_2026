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
3. **Đang làm:** đọc hunk/metadata, commit liên quan và context để gắn **mọi** hàng `affect` hoặc `trivial`. Owner 01, 02, 03, 04, 05, 06, 08, 09, 14 đã hoàn tất binary gate; Tại lần đối soát gần nhất: `affect 871`. `trivial 556`. còn **2.752 hàng chưa phân loại**. Owner 08 đã chốt `95 affect`, `39 trivial`, `0` chưa phân loại. Không suy ra `trivial` chỉ từ đường dẫn, churn hay loại file. Mỗi `affect` phải có finding ID, bằng chứng trước/sau, điều kiện kích hoạt, mixed-version/full-version và kịch bản kiểm chứng.
4. **Hàng chờ ưu tiên:** rà owner 07 MGR theo đường restart, mixed-version; tiếp tục client, CephFS, RGW, build và validation. [`config-default-candidates.tsv`](./pacific-16.2.15-to-quincy-17.2.7/config-default-candidates.tsv) vẫn là dữ liệu hỗ trợ đối soát và cross-reference, không phải nhãn tác động.
5. Kiểm tra partition, số lượng, link, và chạy validator ở chế độ `complete --require-impact binary`. `--mode complete` hiện qua cấu trúc/partition; strict binary hiện thất bại đúng vì các hàng chưa phân loại. Trước khi xong bước này, suite là **đang phân tích**, không phải kết luận đủ để GO/NO-GO production.

## Giới hạn

Net diff endpoint không mô tả mọi thay đổi trung gian hoặc revert. Git rename là heuristic, đặc biệt với file `0/0`. Gitlink chỉ chứng minh pointer đổi; cần đọc object dependency trước khi kết luận hành vi. Chưa có As-Is cluster, artifact triển khai, kết quả lab/canary hoặc rollback rehearsal; không đưa khuyến nghị GO/NO-GO. Mọi thao tác ở đây chỉ đọc mã nguồn, không tác động cluster.
