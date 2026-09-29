# 00 — Inventory thay đổi file

[CSV master đầy đủ](./00-file-inventory.csv) là danh sách đường dẫn chuẩn của net diff `v16.2.15` → `v17.2.7`. Markdown này chỉ giữ số liệu tổng hợp.

| Chỉ số | Giá trị |
| --- | ---: |
| File đổi | 4.179 |
| Thêm / xóa dòng text | 276.334 / 268.473 |
| A / D / M / R / T | 665 / 306 / 2.934 / 273 / 1 |
| Binary | 26 |
| Text `0/0` | 173 |
| Mode change | 9 |
| Gitlink | 14 |

Theo top-level path: `src/` 2.712, `qa/` 1.033, `doc/` 318; phần còn lại 116. Đây là quy mô diff, không phải thước đo rủi ro.

**Nguồn:** repo `ceph16.2.15/ceph`, sạch và không shallow; Git `2.49.0.windows.1`, `--find-renames=50%`. Base SHA `618f440892089921c3e944a991122ddc44e60516`; target SHA `b12291d110049b2f35e32e0de30d70e9a4c060d2`. Base không phải ancestor target; so sánh này cố ý lấy hai endpoint khác nhánh. Chi tiết máy đọc được nằm trong [source-summary.json](./source-summary.json).

`T` thuộc `qa/distros/container-hosts/centos_8.stream_container_tools.yaml`, với mode `120000 → 100644`; đây là type change, không phải file sửa text thông thường. Rename là kết quả heuristic của Git, đặc biệt ở các record `0/0`; cần kiểm tra trước khi gọi đó là di chuyển logic. Binary LOC để trống. Gitlink lưu pointer, chưa chứng minh nội dung dependency.

**Trạng thái phân loại:** sáu cột triage đã được gán cho 4.179 hàng; `P0 816`, `P1 1.285`, `P2 2.078`. Có đúng một owner mỗi hàng. Đây là định tuyến để đọc; binary `affect|trivial` chưa hoàn tất. Không được dùng inventory riêng để suy ra an toàn nâng cấp.

| Owner | Hàng | Owner | Hàng | Owner | Hàng |
| --- | ---: | --- | ---: | --- | ---: |
| 01 OSD/PG | 465 | 02 BlueStore | 206 | 03 KV/block | 38 |
| 04 MON/CRUSH | 185 | 05 messaging/auth | 227 | 06 config | 46 |
| 07 MGR | 726 | 08 cephadm | 134 | 09 ceph-volume | 21 |
| 10 RADOS/RBD | 320 | 11 CephFS | 427 | 12 RGW | 546 |
| 13 build/package | 207 | 14 security | 3 | 15 validation | 628 |

## Tái lập và integrity

Từ root workspace, chạy `python comparison/pacific-16.2.15-to-quincy-17.2.7/tools/build_inventory.py --repo ceph16.2.15/ceph --base v16.2.15 --target v17.2.7 --output <đường-dẫn-mới>.csv --allow-non-ancestor`, rồi chạy `tools/classify_inventory.py` trên CSV được chọn (script hiện trỏ mặc định vào master của suite). So sánh summary với `git -C ceph16.2.15/ceph diff --shortstat --find-renames=50% v16.2.15 v17.2.7`. Ba nguồn `--name-status`, `--numstat`, `--raw` được script đối soát theo endpoint path.
