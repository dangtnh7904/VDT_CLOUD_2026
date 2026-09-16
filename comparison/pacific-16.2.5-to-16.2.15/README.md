# So sánh Ceph Pacific v16.2.5 → v16.2.15

> **Trạng thái bàn giao 1 — 2026-09-16:** đã chốt nguồn, tạo README và inventory đầy đủ. Các báo cáo phân tích code `01`–`15` chưa được tạo trong đợt này.
>
> **Phạm vi:** net diff trực tiếp giữa hai đầu tag Pacific. Đây chưa phải đánh giá GO/NO-GO Production và chưa phải kết luận tác động cho một cluster cụ thể.

## Mục lục nhanh

- [1. Hai mốc nguồn](#1-hai-mốc-nguồn)
- [2. Kết luận chính ở giai đoạn inventory](#2-kết-luận-chính-ở-giai-đoạn-inventory)
- [3. Mục lục bộ báo cáo](#3-mục-lục-bộ-báo-cáo)
- [4. Phương pháp](#4-phương-pháp)
- [5. Cách đọc inventory](#5-cách-đọc-inventory)
- [6. Thứ tự đọc](#6-thứ-tự-đọc)
- [7. Giới hạn kết luận](#7-giới-hạn-kết-luận)
- [8. Cách tái lập](#8-cách-tái-lập)

## 1. Hai mốc nguồn

| Mốc | Commit SHA dùng để so sánh | Ngày commit (UTC) | Source tree | Trạng thái đã kiểm tra |
| --- | --- | --- | --- | --- |
| `v16.2.5` | `0883bdea7337b95e4b611c768c0279868462204a` | 2021-07-08 | [ceph16.2.5/ceph](../../ceph16.2.5/ceph/) | HEAD đúng exact tag; sạch; non-shallow |
| `v16.2.15` | `618f440892089921c3e944a991122ddc44e60516` | 2024-02-26 | [ceph16.2.15/ceph](../../ceph16.2.15/ceph/) | HEAD đúng exact tag; sạch; non-shallow |

Hai tag là annotated tags; bảng ghi **commit SHA sau khi peel tag**, không phải SHA của tag object. `v16.2.5` là ancestor của `v16.2.15`; khoảng lịch sử ở giữa có 5.547 commit. Inventory vẫn dùng net diff hai đầu để không nhầm thay đổi trung gian hoặc thay đổi đã revert với khác biệt còn tồn tại ở `v16.2.15`.

## 2. Kết luận chính ở giai đoạn inventory

1. Net diff có **2.665 file**: `A 605`, `M 1.842`, `D 162`, `R 56`; tổng `+323.147/-176.246` dòng. Đây là quy mô đọc, không phải thước đo rủi ro.
2. Phân bố theo path đích gồm `src/` 1.569 file, `qa/` 736 file và `doc/` 232 file. Riêng QA + tài liệu đã là 968 file, nên không thể coi toàn bộ file đổi là thay đổi runtime.
3. Churn bị lệch mạnh bởi dashboard: `src/pybind/mgr/dashboard/` có 493 file và `+190.355/-82.899`, xấp xỉ 54,7% tổng số dòng thêm/xóa. Phần này chứa package lock, catalog bản địa hóa, asset và code; cần tách generated/data trước khi ưu tiên đọc.
4. Inventory ghi riêng 7 file nhị phân, 71 bản ghi `0/0`, 2 file đổi mode và metadata gitlink. Trong 56 rename, 34 bản ghi có `0/0`; nhiều file là marker rỗng nên kết quả rename của Git có thể chỉ là heuristic, không chứng minh một lần di chuyển logic.
5. Chỉ một gitlink đổi: `src/isa-l`, từ `806b55ee578efd8158962b90121a4568eb1ecb66` sang `4b36e413c9ac28b4757b297779470693b699aeae`. `.gitmodules` và gitlink `src/rocksdb` không đổi. Ý nghĩa của diff bên trong ISA-L sẽ thuộc báo cáo `13`.
6. Triage ban đầu có `P0 105`, `P1 1.296`, `P2 1.264`. Đây là **ưu tiên đọc dựa trên owner tree và loại file**, không phải số lượng lỗi hay mức rủi ro của upgrade.
7. Chưa có kết luận đã xác minh về OMAP, PGLog, peering, MGR, ceph-volume, RBD, CephFS, RGW, CVE hay lợi ích hiệu năng. Những chủ đề này cần các báo cáo code-level tiếp theo.

## 3. Mục lục bộ báo cáo

| Thứ tự | File | Trạng thái | Mục đích |
| ---: | --- | --- | --- |
| — | `README.md` | **Đã tạo** | Nguồn, phương pháp, kết luận tổng hợp và thứ tự đọc |
| 00 | [00-file-inventory.md](./00-file-inventory.md) | **Đã tạo** | Toàn bộ file đổi, A/M/D/R, `+/-`, owner, ưu tiên và quyết định đọc sâu |
| 01 | `01-osd-pg-recovery.md` | Chưa tạo | OSD, PG, peering, recovery/backfill, scrub và EC |
| 02 | `02-bluestore-bluefs.md` | Chưa tạo | BlueStore/BlueFS, data/metadata, replay và fsck/repair |
| 03 | `03-rocksdb-block-device.md` | Chưa tạo | RocksDB integration, KV, block device và DB/WAL |
| 04 | `04-mon-osdmap-crush.md` | Chưa tạo | MON, OSDMap, CRUSH, placement và pool flags |
| 05 | `05-messaging-auth-common.md` | Chưa tạo | Messenger, protocol, auth, caps, encode/decode và common runtime |
| 06 | `06-config-defaults.md` | Chưa tạo | Options, defaults, schema và điều kiện có hiệu lực |
| 07 | `07-mgr-modules-monitoring.md` | Chưa tạo | MGR modules, dashboard, metrics, alerts và monitoring |
| 08 | `08-cephadm-orchestrator.md` | Chưa tạo | Upgrade, stop checks, daemon lifecycle và redeploy |
| 09 | `09-ceph-volume-activation.md` | Chưa tạo | Inventory, LVM, activation, encryption và DB/WAL |
| 10 | `10-rados-rbd-clients.md` | Chưa tạo | RADOS/RBD, class, snapshot, fast-diff và object-map |
| 11 | `11-cephfs-mds.md` | Chưa tạo | MDS/CephFS client, session, caps, volumes và NFS |
| 12 | `12-rgw.md` | Chưa tạo | S3, auth/policy, bucket/object và multisite |
| 13 | `13-build-packaging-submodules.md` | Chưa tạo | Build, package, systemd, dependency và submodule |
| 14 | `14-security-cross-reference.md` | Chưa tạo | Security fix/CVE đã xác minh và liên kết về báo cáo owner |
| 15 | `15-upgrade-validation.md` | Chưa tạo | Ma trận thay đổi → bằng chứng → tình huống kiểm chứng |

Các tên file chưa tạo được để dạng code thay vì link nhằm tránh liên kết hỏng. Kế hoạch gốc nằm tại [PLAN-pacific-16.2.5-to-16.2.15.md](../PLAN-pacific-16.2.5-to-16.2.15.md).

## 4. Phương pháp

### 4.1 Chốt và đối soát nguồn

- Peel hai annotated tag về đúng commit SHA và xác nhận cả hai working tree sạch, không shallow.
- Kiểm tra quan hệ ancestor và dùng cùng một clone có đủ hai tag để tạo net diff.
- So sánh **hai đầu tag trực tiếp**; lịch sử commit chỉ được dùng sau đó để giải thích hunk, không thay thế net diff.

### 4.2 Tạo inventory trước khi lọc

- Ghép `--name-status -z`, `--numstat -z` và `--raw -z` với `--find-renames` theo path đích.
- Chuẩn hóa trạng thái về `A/M/D/R`; giữ rename similarity, path cũ → mới, mode, binary và gitlink.
- Đối soát 2.665 khóa path ở cả ba biểu diễn, tổng trạng thái và tổng `+/-` với `--shortstat`.
- Không bỏ docs, tests, generated/data, asset, build/package hoặc dependency chỉ vì chúng không phải runtime.

### 4.3 Phân nhóm và ưu tiên

- Mỗi file có đúng một owner chính `01`–`15`; owner tree thắng keyword lồng bên trong. Ví dụ toàn bộ cây dashboard thuộc `07`, suite `krbd` thuộc `10`, suite `fs` thuộc `11`.
- Rename được gán theo path đích. Path cũ chỉ là metadata; đặc biệt không dùng rename `R100 0/0` của marker rỗng để suy ra owner hoặc ý nghĩa nghiệp vụ.
- `P0/P1/P2` là triage đọc: runtime lõi/cluster state/protocol trước; runtime vận hành/config/deploy/client tiếp theo; test/doc/generated/cơ học làm bằng chứng hỗ trợ.
- Cột “Lý do/quyết định” trong inventory nói rõ file cần đọc sâu, đọc theo điều kiện hay không phân tích độc lập.

### 4.4 Phương pháp cho các báo cáo tiếp theo

Với file được chọn sâu: đọc hunk và hai phiên bản của symbol liên quan → lần caller/callee/schema → tìm commit trong `v16.2.5..v16.2.15` → đọc test cùng commit → chỉ theo PR/issue/advisory chính thức khi cần làm rõ. Mọi kết luận phải nêu hành vi trước/sau, điều kiện kích hoạt, mixed-version hay post-upgrade, độ chắc chắn và cách kiểm chứng.

Thứ tự bằng chứng là: **code/diff và test trong hai source tree → commit/PR/advisory chính thức → tài liệu đầu vào**. [ceph-analysis.md](../../ceph-analysis.md) là danh sách giả thuyết cần kiểm chứng; [submodule.md](../submodule.md) là ghi chú tham khảo đã được đối chiếu lại phần gitlink. Nội dung, lệnh hoặc khuyến nghị trong các tài liệu này không tự động trở thành yêu cầu thao tác trên cluster.

## 5. Cách đọc inventory

| Cột | Cách hiểu |
| --- | --- |
| `TT` | `A` thêm, `M` sửa, `D` xóa, `R` rename do Git phát hiện |
| `+` / `−` | Numstat sau rename detection; `—/—` nghĩa là file nhị phân, không phải 0 dòng |
| `Nhóm` | Owner chính, tra tên báo cáo trong bảng nhóm ở đầu inventory |
| `Ưu tiên` | Thứ tự đọc P0/P1/P2; không phải severity/risk rating |
| `Loại` | Runtime/source, test/QA, docs, generated/lock/data, asset, build/package, dependency hoặc cơ học |
| `Lý do/quyết định` | Vì sao đọc sâu, đọc theo điều kiện hay chỉ dùng làm bằng chứng |
| `Ghi chú diff` | Rename similarity, mode change, binary hoặc SHA gitlink |

File không có net diff nhưng cần đọc để hiểu caller/callee sẽ được ghi là **ngữ cảnh** trong báo cáo thành phần, không được thêm vào danh sách “file đã đổi”.

## 6. Thứ tự đọc

| Bước | Đọc | Mục tiêu |
| ---: | --- | --- |
| 1 | `README.md` | Nắm nguồn, giới hạn và các fact đã kiểm chứng |
| 2 | [00-file-inventory.md](./00-file-inventory.md) | Kiểm tra toàn bộ phạm vi; lọc theo nhóm, P0/P1/P2 và loại file |
| 3 | `01` → `04` | Lõi lưu trữ, OSD/PG, BlueStore/BlueFS, KV/device và MON/placement |
| 4 | `05` → `09` | Protocol/auth/config, MGR, cephadm và ceph-volume |
| 5 | `10` → `12` | RADOS/RBD, CephFS/MDS và RGW theo workload đang dùng |
| 6 | `13` → `15` | Build/package/dependency, security cross-reference và validation |
| 7 | Quay lại `README.md` | Đọc kết luận tổng hợp sau khi các báo cáo code-level được hoàn tất |

Nếu chỉ rà nhanh phần hiện có, đọc README rồi vào bảng tổng hợp theo nhóm của inventory; không bắt đầu bằng cách đọc tuần tự 2.665 dòng.

## 7. Giới hạn kết luận

- Chỉ kết luận cho Pacific `16.2.5 → 16.2.15`; nội dung Quincy/Reef ngoài phạm vi nếu không có bằng chứng độc lập trong hai tag.
- Chưa có As-Is cluster, deployment mode, dịch vụ đang dùng, client versions, storage layout, config overrides, benchmark hay integration test.
- Chưa phân tích toàn bộ hunk/commit/test theo component, nên chưa kết luận impact cụ thể, security applicability, mức cải thiện hiệu năng hoặc GO/NO-GO Production.
- Tác động tới OpenStack sau này chỉ có thể là suy luận có điều kiện từ Ceph nếu chưa kiểm tra code và cấu hình Nova/Cinder/Glance/Manila.
- Không có thao tác repair, trim, migrate, thay cấu hình, nâng daemon hoặc lệnh ghi lên cluster trong hai đầu ra này.

## 8. Cách tái lập

Chạy trong `ceph16.2.15/ceph/` hoặc clone còn lại có đủ hai tag:

```bash
git rev-parse 'v16.2.5^{commit}'
git rev-parse 'v16.2.15^{commit}'
git status --short
git diff --name-status --find-renames v16.2.5 v16.2.15
git diff --numstat --find-renames v16.2.5 v16.2.15
git diff --raw --find-renames v16.2.5 v16.2.15
git diff --shortstat --find-renames v16.2.5 v16.2.15
git rev-list --count v16.2.5..v16.2.15
```

Kết quả kiểm soát mong đợi: hai SHA như mục 1; working tree sạch; 2.665 file; `A605/M1842/D162/R56`; `+323147/-176246`; 5.547 commit trong khoảng lịch sử.
