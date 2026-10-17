# 00 — Master file inventory: Quincy 17.2.7 → Reef 18.2.7

[CSV master đầy đủ](./00-file-inventory.csv) có 4.434 hàng, một hàng cho mỗi endpoint path từ net diff `v17.2.7` tới `v18.2.7`. Danh sách file không được lặp trong Markdown này.

## Provenance

- Repo: `D:\career\VDT\GD2\upgrade_Ceph\ceph17.2.7`.
- Base: `b12291d110049b2f35e32e0de30d70e9a4c060d2`.
- Target: `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`.
- Git: `2.49.0.windows.1`; rename detection `--find-renames=50%`.
- Worktree sạch tại preflight; repo shallow; base không là ancestor của target.

## Tổng hợp

| Chiều đo | Phân bố |
| --- | --- |
| Git status | `A 984`, `D 365`, `M 2.667`, `R 417`, `T 1` |
| Reading priority | `P0 742`, `P1 1.513`, `P2 2.179` |
| Review mode | `deep 1.184`, `conditional 1.071`, `support 1.834`, `reference-only 345` |
| File type | runtime/source 2.058; test/QA 1.529; generated/lock/data 344; documentation 305; build/package 190; dependency/gitlink 7; binary/asset 1 |
| Diff volume | 401.909 additions; 197.647 deletions; 7 binary; 3 mode change; 7 gitlink |

Priority, type và review mode là triage, không phải severity hoặc binary impact. Component CSV giữ đủ mọi hàng và sẽ nhận đúng một nhãn `affect|trivial` sau khi screen.

## Quy ước đặc biệt

Rename là heuristic Git, đặc biệt các hàng 0/0 phải đọc metadata/context trước khi gọi logical move. Binary LOC để trống. Gitlink giữ SHA pointer nhưng chưa khẳng định nội dung dependency. Status `T` giữ nguyên cho type change file→symlink cùng raw mode/blob.

Repo shallow và non-ancestor vẫn đủ để so endpoint object đã fetch, nhưng không đủ chứng minh lịch sử commit. Finding dùng lịch sử phải fetch object/commit cụ thể hoặc ghi rõ giới hạn.

## Integrity và tái lập

Ba biểu diễn `--name-status -z`, `--numstat -z` và `--raw -z` đã được hợp nhất theo cùng rename option; endpoint key set và shortstat được đối soát trước khi ghi CSV. Dùng [validator cục bộ](./tools/validate_comparison.py) ở `--mode inventory` cho master và `--mode complete` cho partition hiện có.
