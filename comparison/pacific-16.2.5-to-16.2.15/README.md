# So sánh Ceph Pacific v16.2.5 → v16.2.15

> **Trạng thái bàn giao 5 — 2026-09-17:** đã chốt nguồn, hoàn thành inventory và mười cặp phân tích `01`–`10`. Các cặp `11`–`15` chưa được tạo.
>
> **Phạm vi:** net diff trực tiếp giữa hai đầu tag Pacific. Đây chưa phải đánh giá GO/NO-GO Production và chưa phải kết luận tác động cho một cluster cụ thể.

## Mục lục nhanh

- [1. Hai mốc nguồn](#1-hai-mốc-nguồn)
- [2. Kết luận đã kiểm chứng đến phần 10](#2-kết-luận-đã-kiểm-chứng-đến-phần-10)
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

## 2. Kết luận đã kiểm chứng đến phần 10

1. Net diff có **2.665 file**: `A 605`, `M 1.842`, `D 162`, `R 56`; tổng `+323.147/-176.246` dòng. Đây là quy mô đọc, không phải thước đo rủi ro.
2. Phân bố theo path đích gồm `src/` 1.569 file, `qa/` 736 file và `doc/` 232 file. Riêng QA + tài liệu đã là 968 file, nên không thể coi toàn bộ file đổi là thay đổi runtime.
3. Churn bị lệch mạnh bởi dashboard: `src/pybind/mgr/dashboard/` có 493 file và `+190.355/-82.899`, xấp xỉ 54,7% tổng số dòng thêm/xóa. Phần này chứa package lock, catalog bản địa hóa, asset và code; cần tách generated/data trước khi ưu tiên đọc.
4. Inventory ghi riêng 7 file nhị phân, 71 bản ghi `0/0`, 2 file đổi mode và metadata gitlink. Trong 56 rename, 34 bản ghi có `0/0`; nhiều file là marker rỗng nên kết quả rename của Git có thể chỉ là heuristic, không chứng minh một lần di chuyển logic.
5. Chỉ một gitlink đổi: `src/isa-l`, từ `806b55ee578efd8158962b90121a4568eb1ecb66` sang `4b36e413c9ac28b4757b297779470693b699aeae`. `.gitmodules` và gitlink `src/rocksdb` không đổi. Ý nghĩa của diff bên trong ISA-L sẽ thuộc báo cáo `13`.
6. Triage ban đầu có `P0 105`, `P1 1.296`, `P2 1.264`. Đây là **ưu tiên đọc dựa trên owner tree và loại file**, không phải số lượng lỗi hay mức rủi ro của upgrade.
7. [OSD/PG](./01-osd-pg-recovery.md) xác nhận target giữ EC async recovery không xuống dưới `min_size`, xử lý hinfo lỗi mà không assert ở các đường đã sửa, giới hạn dần PGLog `dups` và sửa nhiều trạng thái scrub/peering. Tác động mixed-version phụ thuộc OSD giữ vai trò primary; upgrade không tự cho phép repair hay offline trim.
8. [BlueStore/BlueFS](./02-bluestore-bluefs.md) xác nhận các sửa crash-durability, deferred replay, legacy OMAP conversion và fsck/repair. Target cũng có opcode BlueFS log mà reader base không hiểu; vì vậy rollback một OSD đã ghi log mới cần test/restore device snapshot, không chỉ hạ package.
9. [RocksDB/KV/block device](./03-rocksdb-block-device.md) xác nhận bounded iterator/range-delete, reshard option handling, `O_EXCL` và errno mapping. Gitlink `src/rocksdb` không đổi, không thấy DB/WAL format migration trong sáu dòng owner, và compact-on-deletion mặc định tắt.
10. [MON/OSDMap/CRUSH](./04-mon-osdmap-crush.md) xác nhận range blocklist dùng OSDMap state/encoding mới nhưng có cluster feature gate. `require-osd-release=pacific` chỉ one-way đối với OSD pre-Pacific, không chặn rollback `16.2.15` → `16.2.5`; target còn sửa election/rank-removal, CephX proposal, old FSMap, PG-merge map trimming, masked config theo CRUSH location và health-store trimming.
11. [Messenger/auth/common](./05-messaging-auth-common.md) tập trung vào continuity của messenger/auth và compatibility message: ProtocolV2/AsyncMessenger sửa deadlock, teardown và wait race; CephX chỉ publish rotating key sau Paxos commit; các extension message giữ decode path cũ hoặc có gate, với một edge `MMgrUpdate` cần test khi MON mới nói chuyện với MGR base.
12. [Config/defaults](./06-config-defaults.md) xác nhận các default OSD/MDS/RGW/RBD chỉ đổi khi role liên quan restart hoặc đi qua đường code tương ứng; sáu key remove/rename cần audit. mClock cần xử lý trước OSD restart; RGW Vault có key TLS verify mới mặc định `true`; CephFS có grace/eviction/session guards mới cần test nếu dịch vụ được dùng.
13. [MGR/modules/monitoring](./07-mgr-modules-monitoring.md) xác nhận target harden active-MGR failover, tách finisher theo module, thêm notification subscription và autoscaler guards. Tuy nhiên endpoint `v16.2.15` tái tạo duplicate Prometheus `HELP/TYPE` cho `ceph_pool_objects_repaired`; đây là blocker cho monitoring gate cho tới khi scrape target được parser thật chấp nhận. Dashboard mặc định TLS 1.3, CephFS perf stats dùng schema v2, và alert rules đổi từ 18 sang 58 tên không trùng exact nên đều cần preflight có điều kiện.
14. Không báo cáo nào tuyên bố mức tăng IOPS/latency: các thay đổi hiệu năng phụ thuộc workload, layout DB/WAL, option và thiết bị; test repository đã đọc nhưng chưa chạy.
15. [Cephadm/orchestrator](./08-cephadm-orchestrator.md) xác nhận `migration_current` đổi 2→5 là rollback boundary đối với MGR base: sau khi target hoàn tất migration, code 16.2.5 không có transition xử lý state 5 và có thể chặn reconciliation. MDS minor upgrade luôn chạy sequence giảm rank/tắt standby-replay; `upgrade stop` không tự restore preparation state. Private/insecure registry cần gate pull theo từng host.
16. [Ceph-volume/activation](./09-ceph-volume-activation.md) xác nhận target dùng host namespace cho LVM, hợp nhất raw/LVM activation và sửa device discovery. Regression activation chậm được thêm rồi sửa hoàn toàn trong range, không tồn tại ở baseline 16.2.5. BlueFS `migrate/new-db/new-wal`, zap và provisioning vẫn là thao tác opt-in, không tự chạy khi upgrade; dm-crypt cần canary restart riêng.
17. [RADOS/RBD clients](./10-rados-rbd-clients.md) xác nhận nhiều sửa correctness cho fast-diff/object-map, journal/discard, mirroring và blocklist recovery. Riêng persistent SSD write-back cache có boundary trực tiếp: base tạo layout version 0, target yêu cầu version 1 và từ chối existing cache; phải chứng minh cache sạch và có procedure chuyển đổi trước khi nâng client.
18. CephFS/MDS, RGW, packaging/submodules, security cross-reference và validation tổng hợp vẫn chờ các báo cáo `11`–`15`; chưa có kết luận GO/NO-GO Production.

## 3. Mục lục bộ báo cáo

| Thứ tự | Markdown | CSV thay đổi liên quan | Trạng thái | Mục đích |
| ---: | --- | --- | --- | --- |
| — | `README.md` | — | **Đã tạo** | Nguồn, phương pháp, kết luận tổng hợp và thứ tự đọc |
| 00 | [00-file-inventory.md](./00-file-inventory.md) | [00-file-inventory.csv](./00-file-inventory.csv) | **Đã tạo** | Markdown giữ thống kê/quy ước; CSV giữ toàn bộ 2.665 file đổi |
| 01 | [01-osd-pg-recovery.md](./01-osd-pg-recovery.md) | [01-osd-pg-recovery.csv](./01-osd-pg-recovery.csv) | **Đã phân tích** | OSD, PG, peering, recovery/backfill, scrub và EC |
| 02 | [02-bluestore-bluefs.md](./02-bluestore-bluefs.md) | [02-bluestore-bluefs.csv](./02-bluestore-bluefs.csv) | **Đã phân tích** | BlueStore/BlueFS, data/metadata, replay và fsck/repair |
| 03 | [03-rocksdb-block-device.md](./03-rocksdb-block-device.md) | [03-rocksdb-block-device.csv](./03-rocksdb-block-device.csv) | **Đã phân tích** | RocksDB integration, KV, block device và DB/WAL |
| 04 | [04-mon-osdmap-crush.md](./04-mon-osdmap-crush.md) | [04-mon-osdmap-crush.csv](./04-mon-osdmap-crush.csv) | **Đã phân tích** | MON, OSDMap, CRUSH, placement và pool flags |
| 05 | [05-messaging-auth-common.md](./05-messaging-auth-common.md) | [05-messaging-auth-common.csv](./05-messaging-auth-common.csv) | **Đã phân tích** | Messenger, protocol, auth, caps, encode/decode và common runtime |
| 06 | [06-config-defaults.md](./06-config-defaults.md) | [06-config-defaults.csv](./06-config-defaults.csv) | **Đã phân tích** | Options, defaults, schema và điều kiện có hiệu lực |
| 07 | [07-mgr-modules-monitoring.md](./07-mgr-modules-monitoring.md) | [07-mgr-modules-monitoring.csv](./07-mgr-modules-monitoring.csv) | **Đã phân tích** | MGR modules, dashboard, metrics, alerts và monitoring |
| 08 | [08-cephadm-orchestrator.md](./08-cephadm-orchestrator.md) | [08-cephadm-orchestrator.csv](./08-cephadm-orchestrator.csv) | **Đã phân tích** | Upgrade, stop checks, daemon lifecycle và redeploy |
| 09 | [09-ceph-volume-activation.md](./09-ceph-volume-activation.md) | [09-ceph-volume-activation.csv](./09-ceph-volume-activation.csv) | **Đã phân tích** | Inventory, LVM, activation, encryption và DB/WAL |
| 10 | [10-rados-rbd-clients.md](./10-rados-rbd-clients.md) | [10-rados-rbd-clients.csv](./10-rados-rbd-clients.csv) | **Đã phân tích** | RADOS/RBD, class, snapshot, fast-diff và object-map |
| 11 | `11-cephfs-mds.md` | `11-cephfs-mds.csv` | Chưa tạo | MDS/CephFS client, session, caps, volumes và NFS |
| 12 | `12-rgw.md` | `12-rgw.csv` | Chưa tạo | S3, auth/policy, bucket/object và multisite |
| 13 | `13-build-packaging-submodules.md` | `13-build-packaging-submodules.csv` | Chưa tạo | Build, package, systemd, dependency và submodule |
| 14 | `14-security-cross-reference.md` | `14-security-cross-reference.csv` | Chưa tạo | Security fix/CVE đã xác minh và liên kết về báo cáo owner |
| 15 | `15-upgrade-validation.md` | `15-upgrade-validation.csv` | Chưa tạo | Ma trận thay đổi → bằng chứng → tình huống kiểm chứng |

Các tên file chưa tạo được để dạng code thay vì link nhằm tránh liên kết hỏng. Từ phần `00` trở đi, mỗi phần dùng Markdown cho phân tích và CSV cùng basename cho danh sách file thay đổi liên quan. Kế hoạch gốc nằm tại [PLAN-pacific-16.2.5-to-16.2.15.md](../PLAN-pacific-16.2.5-to-16.2.15.md).

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
- Ghi chi tiết **mọi file** vào CSV UTF-8. Markdown chỉ giữ thống kê, phương pháp và kết luận; không lặp bảng file thay đổi.

### 4.3 Phân nhóm và ưu tiên

- Mỗi file có đúng một owner chính `01`–`15`; owner tree thắng keyword lồng bên trong. Ví dụ toàn bộ cây dashboard thuộc `07`, suite `krbd` thuộc `10`, suite `fs` thuộc `11`.
- Rename được gán theo path đích. Path cũ chỉ là metadata; đặc biệt không dùng rename `R100 0/0` của marker rỗng để suy ra owner hoặc ý nghĩa nghiệp vụ.
- `P0/P1/P2` là triage đọc: runtime lõi/cluster state/protocol trước; runtime vận hành/config/deploy/client tiếp theo; test/doc/generated/cơ học làm bằng chứng hỗ trợ.
- Các cột `review_mode` và `analysis_decision` trong inventory là triage ban đầu. Khi hoàn tất một component, disposition cuối (`material`, `conditional`, `support`, `trivial` hoặc `mixed`) cần được đối soát với toàn bộ dòng CSV thay vì suy ra từ path/P-level.

### 4.4 Phương pháp cho các báo cáo tiếp theo

Với file được chọn sâu: đọc hunk và hai phiên bản của symbol liên quan → lần caller/callee/schema → tìm commit trong `v16.2.5..v16.2.15` → đọc test cùng commit → chỉ theo PR/issue/advisory chính thức khi cần làm rõ. Mọi kết luận phải nêu hành vi trước/sau, điều kiện kích hoạt, mixed-version hay post-upgrade, độ chắc chắn và cách kiểm chứng.

Chỉ đưa vào finding chi tiết khi có chuỗi tác động đáng tin cậy tới chuẩn bị rollout, mixed-version, restart/replay, compatibility, dữ liệu, availability, rollback, thời lượng ổn định hoặc tín hiệu validation. Xác suất thấp vẫn được giữ nếu chuỗi tác động có bằng chứng và được ghi `conditional`; client/frontend/test/build không bị loại theo tên thư mục, nhưng nếu không có chuỗi này thì chỉ được tổng hợp là **trivial/support** trong Markdown và vẫn giữ đầy đủ trong CSV.

Thứ tự bằng chứng là: **code/diff và test trong hai source tree → commit/PR/advisory chính thức → tài liệu đầu vào**. [ceph-analysis.md](../../ceph-analysis.md) là danh sách giả thuyết cần kiểm chứng; [submodule.md](../submodule.md) là ghi chú tham khảo đã được đối chiếu lại phần gitlink. Nội dung, lệnh hoặc khuyến nghị trong các tài liệu này không tự động trở thành yêu cầu thao tác trên cluster.

## 5. Cách đọc inventory

Chi tiết từng file nằm trong [00-file-inventory.csv](./00-file-inventory.csv):

- `path`, `old_path`, `status`, `status_detail`: path đích, path cũ nếu rename và trạng thái Git.
- `additions`, `deletions`, `binary`: numstat; hai cột số dòng để trống khi `binary=true`.
- `old_mode`, `new_mode`, `old_blob`, `new_blob`: mode và object SHA để nhận diện mode change/gitlink.
- `group`, `owner_report`, `priority`, `file_type`: owner chính, thứ tự đọc và loại file.
- `review_mode`, `analysis_decision`, `diff_note`: cách xử lý khi phân tích và ghi chú diff.

File không có net diff nhưng cần đọc để hiểu caller/callee sẽ được ghi là **ngữ cảnh** trong báo cáo thành phần, không được thêm vào danh sách “file đã đổi”.

## 6. Thứ tự đọc

| Bước | Đọc | Mục tiêu |
| ---: | --- | --- |
| 1 | `README.md` | Nắm nguồn, giới hạn và các fact đã kiểm chứng |
| 2 | [00-file-inventory.md](./00-file-inventory.md) và [00-file-inventory.csv](./00-file-inventory.csv) | Đọc thống kê trong Markdown, rồi lọc CSV theo nhóm, P0/P1/P2 và loại file |
| 3 | [01](./01-osd-pg-recovery.md) → [04](./04-mon-osdmap-crush.md) | Lõi lưu trữ, OSD/PG, BlueStore/BlueFS, KV/device và MON/placement |
| 4 | [05](./05-messaging-auth-common.md) → [09](./09-ceph-volume-activation.md) | Protocol/auth/config, MGR, cephadm và ceph-volume |
| 5 | [10](./10-rados-rbd-clients.md) → `12` | RADOS/RBD đã hoàn tất; CephFS/MDS và RGW theo workload khi có báo cáo |
| 6 | `13` → `15` | Build/package/dependency, security cross-reference và validation |
| 7 | Quay lại `README.md` | Đọc kết luận tổng hợp sau khi các báo cáo code-level được hoàn tất |

Nếu chỉ rà nhanh phần hiện có, đọc README rồi vào bảng tổng hợp theo nhóm trong `00.md`; chỉ mở CSV khi cần lọc hoặc truy một file cụ thể.

## 7. Giới hạn kết luận

- Chỉ kết luận cho Pacific `16.2.5 → 16.2.15`; nội dung Quincy/Reef ngoài phạm vi nếu không có bằng chứng độc lập trong hai tag.
- Chưa có As-Is cluster, deployment mode, dịch vụ đang dùng, client versions, storage layout, config overrides, benchmark hay integration test.
- Đã phân tích code-level các owner `01`–`10`; `11`–`15` chưa hoàn tất. Chưa có test runtime nên chưa kết luận security applicability toàn suite, mức cải thiện hiệu năng hoặc GO/NO-GO Production.
- Tác động tới OpenStack sau này chỉ có thể là suy luận có điều kiện từ Ceph nếu chưa kiểm tra code và cấu hình Nova/Cinder/Glance/Manila.
- Không có thao tác repair, trim, migrate, thay cấu hình, nâng daemon hoặc lệnh ghi lên cluster trong bộ đầu ra hiện tại.

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
