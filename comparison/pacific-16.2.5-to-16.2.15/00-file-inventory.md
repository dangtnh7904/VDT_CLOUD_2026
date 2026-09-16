# Inventory file thay đổi: Ceph Pacific v16.2.5 → v16.2.15

> **Trạng thái:** Hoàn thành inventory net diff ở hai đầu tag. Phân nhóm và P0/P1/P2 là ưu tiên đọc ban đầu, **không phải** kết luận rủi ro nâng cấp.
>
> **Dữ liệu chi tiết:** [00-file-inventory.csv](./00-file-inventory.csv)
>
> **Phạm vi:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), `git diff --find-renames` trực tiếp giữa hai tag.

## 1. Kiểm soát nguồn và tổng số

| Mốc         | SHA commit                                   | Source tree           | Trạng thái khi chốt inventory                 |
| ------------ | -------------------------------------------- | --------------------- | ------------------------------------------------ |
| `v16.2.5`  | `0883bdea7337b95e4b611c768c0279868462204a` | `ceph16.2.5/ceph/`  | HEAD đúng tag; working tree sạch; non-shallow |
| `v16.2.15` | `618f440892089921c3e944a991122ddc44e60516` | `ceph16.2.15/ceph/` | HEAD đúng tag; working tree sạch; non-shallow |

| Chỉ tiêu                                      |       Kết quả |
| ----------------------------------------------- | --------------: |
| Tổng bản ghi file                             | **2,665** |
| Added (`A`)                                   |             605 |
| Modified (`M`)                                |           1,842 |
| Deleted (`D`)                                 |             162 |
| Renamed (`R`)                                 |              56 |
| Dòng thêm                                     |         323,147 |
| Dòng xóa                                      |         176,246 |
| File nhị phân không có LOC từ`--numstat` |               7 |
| Bản ghi`0/0`                                 |              71 |
| Bản ghi đổi mode                             |               2 |

Đối soát: `A + M + D + R` bằng tổng bản ghi; tổng `+/-` khớp `git diff --shortstat --find-renames`. File nhị phân có `additions` và `deletions` để trống, không bị đổi thành `0/0`. Rename giữ `old_path`, path đích và similarity trong `status_detail`. File chỉ đọc làm ngữ cảnh nhưng không có net diff **không** xuất hiện trong CSV.

Lưu ý rename: 34/56 bản ghi `R` có numstat `0/0`. Nhiều path là marker rỗng nên Git có thể ghép rename giữa hai tên không cùng ý nghĩa nghiệp vụ. Inventory giữ nguyên kết quả `--find-renames`, nhưng **không suy diễn** đây là một lần di chuyển logic nếu chưa kiểm tra nội dung và vị trí dùng.

### Phân bố top-level

| Top-level               |  File |
| ----------------------- | ----: |
| `src`                 | 1,569 |
| `qa`                  |   736 |
| `doc`                 |   232 |
| `monitoring`          |    86 |
| `cmake`               |    11 |
| `debian`              |     9 |
| `.github`             |     4 |
| `admin`               |     3 |
| `.readthedocs.yml`    |     1 |
| `CMakeLists.txt`      |     1 |
| `PendingReleaseNotes` |     1 |
| `README.aix`          |     1 |
| `ceph.spec.in`        |     1 |
| `do_cmake.sh`         |     1 |
| `doc_deps.deb.txt`    |     1 |
| `examples`            |     1 |
| `install-deps.sh`     |     1 |
| `make-debs.sh`        |     1 |
| `make-dist`           |     1 |
| `run-make-check.sh`   |     1 |
| `sudoers.d`           |     1 |
| `systemd`             |     1 |
| `win32_deps_build.sh` |     1 |

## 2. Quy ước phân loại

- `A/M/D/R`: thêm/sửa/xóa/đổi tên trong net diff hai đầu. `R` không có nghĩa nội dung chắc chắn giữ nguyên; xem similarity và `+/-`.
- `P0`: đọc trước vì đường runtime lõi, trạng thái bền vững, cluster state, protocol/auth có thể liên quan correctness/availability/compatibility.
- `P1`: đọc sâu hoặc theo điều kiện cho runtime/client/orchestration/config/activation/build/package/dependency.
- `P2`: bằng chứng hỗ trợ hoặc thay đổi ít trực tiếp tới runtime như test/QA, tài liệu, generated asset và thay đổi cơ học.
- Ưu tiên là bộ lọc đọc ban đầu dựa trên đường dẫn/loại file; mức rủi ro cuối cùng chỉ được gán sau khi đọc hunk, commit, caller/callee và test.

### Nhóm sở hữu chính

Mỗi file có đúng một nhóm sở hữu chính; báo cáo khác chỉ tham chiếu chéo.

| Mã | Cặp báo cáo sở hữu                    | Phạm vi                                                       | Số file |
| --- | ------------------------------------------ | -------------------------------------------------------------- | -------: |
| 01  | `01-osd-pg-recovery.{md,csv}`            | OSD, PG, peering, recovery/backfill, scrub, replication và EC |       45 |
| 02  | `02-bluestore-bluefs.{md,csv}`           | BlueStore/BlueFS, object data, metadata, replay, fsck/repair   |       37 |
| 03  | `03-rocksdb-block-device.{md,csv}`       | RocksDB integration, KV, block device, DB/WAL và I/O          |        6 |
| 04  | `04-mon-osdmap-crush.{md,csv}`           | MON/quorum, OSDMap, CRUSH, placement và pool flags            |       52 |
| 05  | `05-messaging-auth-common.{md,csv}`      | messenger, messages, auth, encode/decode và common runtime    |       92 |
| 06  | `06-config-defaults.{md,csv}`            | options, defaults, schema/config và điều kiện hiệu lực   |       20 |
| 07  | `07-mgr-modules-monitoring.{md,csv}`     | MGR, dashboard, module, metrics, alerts và monitoring         |      685 |
| 08  | `08-cephadm-orchestrator.{md,csv}`       | cephadm/orchestrator, upgrade và daemon lifecycle             |      149 |
| 09  | `09-ceph-volume-activation.{md,csv}`     | ceph-volume, inventory, LVM, activation và DB/WAL             |       76 |
| 10  | `10-rados-rbd-clients.{md,csv}`          | RADOS/RBD/client/class, snapshot, diff và object-map          |      474 |
| 11  | `11-cephfs-mds.{md,csv}`                 | CephFS/MDS/client, session, caps, volumes và NFS              |      467 |
| 12  | `12-rgw.{md,csv}`                        | RGW, S3, auth/policy, bucket/object và multisite              |      237 |
| 13  | `13-build-packaging-submodules.{md,csv}` | build, packaging, systemd, dependency và submodule            |       51 |
| 14  | `14-security-cross-reference.{md,csv}`   | security advisory/CVE và đối chiếu chéo                   |        8 |
| 15  | `15-upgrade-validation.{md,csv}`         | QA/test/release note và validation liên thành phần         |      266 |

### Tổng hợp theo nhóm

| Nhóm           |            File |             A |               M |             D |            R |                 + |                − |            P0 |              P1 |              P2 |
| --------------- | --------------: | ------------: | --------------: | ------------: | -----------: | ----------------: | ----------------: | ------------: | --------------: | --------------: |
| 01              |              45 |             2 |              42 |             0 |            1 |             2,980 |               865 |            36 |               1 |               8 |
| 02              |              37 |             2 |              35 |             0 |            0 |             6,011 |             1,878 |            24 |               2 |              11 |
| 03              |               6 |             0 |               6 |             0 |            0 |               383 |               173 |             0 |               6 |               0 |
| 04              |              52 |             1 |              51 |             0 |            0 |             1,990 |               554 |            37 |               3 |              12 |
| 05              |              92 |             3 |              89 |             0 |            0 |             1,508 |               652 |             8 |              73 |              11 |
| 06              |              20 |             0 |              20 |             0 |            0 |             1,481 |               998 |             0 |               5 |              15 |
| 07              |             685 |           190 |             459 |            30 |            6 |           216,964 |            94,763 |             0 |             558 |             127 |
| 08              |             149 |            50 |              83 |             6 |           10 |            14,639 |             3,670 |             0 |              41 |             108 |
| 09              |              76 |             8 |              68 |             0 |            0 |             6,675 |             1,242 |             0 |              32 |              44 |
| 10              |             474 |            96 |             345 |            18 |           15 |            14,386 |             7,854 |             0 |             224 |             250 |
| 11              |             467 |           165 |             224 |            64 |           14 |            22,152 |             6,375 |             0 |             129 |             338 |
| 12              |             237 |            21 |             203 |            10 |            3 |            10,433 |             9,658 |             0 |             141 |              96 |
| 13              |              51 |             1 |              49 |             0 |            1 |               802 |               282 |             0 |              45 |               6 |
| 14              |               8 |             8 |               0 |             0 |            0 |               518 |                 0 |             0 |               8 |               0 |
| 15              |             266 |            58 |             168 |            34 |            6 |            22,225 |            47,282 |             0 |              28 |             238 |
| **Tổng** | **2,665** | **605** | **1,842** | **162** | **56** | **323,147** | **176,246** | **105** | **1,296** | **1,264** |

### Tổng hợp theo loại file

| Loại                   |  File |
| ----------------------- | ----: |
| `runtime/source`      | 1,170 |
| `test/QA`             |   929 |
| `documentation`       |   215 |
| `tool/script`         |   116 |
| `mechanical/zero-LOC` |    71 |
| `build/package`       |    67 |
| `monitoring`          |    28 |
| `generated/lock/data` |    27 |
| `release-note`        |    20 |
| `config/schema`       |    11 |
| `binary/asset`        |     7 |
| `test/fixture-data`   |     2 |
| `asset/data`          |     1 |
| `dependency`          |     1 |

## 3. Danh mục file thay đổi (CSV)

Danh sách chi tiết **2.665 file** đã được chuyển sang [00-file-inventory.csv](./00-file-inventory.csv). Markdown này chỉ giữ thống kê, quy ước và hướng dẫn; từ phần 00 trở đi, danh sách file thay đổi không lặp lại dưới dạng bảng Markdown.

CSV dùng UTF-8, có một header và 2.665 dòng dữ liệu. Các cột gồm:

- Nguồn và định danh: `index`, `base_tag`, `target_tag`, `path`, `old_path`.
- Diff: `status`, `status_detail`, `additions`, `deletions`, `binary`, `old_mode`, `new_mode`, `old_blob`, `new_blob`.
- Phân tích: `group`, `owner_report`, `priority`, `file_type`, `review_mode`, `analysis_decision`, `diff_note`.

`additions` và `deletions` để trống với file nhị phân. `old_path` chỉ có giá trị với rename. `review_mode` có các giá trị `deep`, `conditional`, `support` hoặc `reference-only`.

## 4. Cách tái lập và kiểm tra toàn vẹn

Chạy trong một trong hai clone có đủ hai tag:

```bash
git diff --name-status --find-renames v16.2.5 v16.2.15
git diff --numstat --find-renames v16.2.5 v16.2.15
git diff --raw --find-renames v16.2.5 v16.2.15
git diff --shortstat --find-renames v16.2.5 v16.2.15
```

CSV inventory ghép ba biểu diễn theo path đích, đối soát cùng tập khóa và giữ metadata mode/gitlink. Ngày tạo inventory: 2026-09-16.
