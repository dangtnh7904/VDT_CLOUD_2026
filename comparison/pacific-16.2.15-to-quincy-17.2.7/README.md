# So sánh Ceph Pacific v16.2.15 → Quincy v17.2.7

**Trạng thái: đã chốt nguồn, hoàn thành master inventory và phân owner cho 4.179 hàng; 15 cặp component đã tạo, binary gate và phân tích component chưa hoàn tất.**

Hai tag được resolve trong cùng repo `ceph16.2.15/ceph`: base `618f440892089921c3e944a991122ddc44e60516`, target `b12291d110049b2f35e32e0de30d70e9a4c060d2`. Base không là ancestor của target vì đây là hai release branch. Phạm vi là **net diff trực tiếp của hai endpoint**, không phải lịch sử tuyến tính hay chứng nhận tương thích khi rolling upgrade.

[Hướng dẫn Quincy chính thức](https://docs.ceph.com/en/quincy/releases/quincy/) cho phép đường nâng từ Pacific 16.2.z sang Quincy; kết luận code và điều kiện cluster cụ thể vẫn phải được kiểm riêng. Không cần cây source `ceph17.2.7` riêng để so sánh hai tag.

## Kết quả đã xác minh

- [Inventory](./00-file-inventory.md) ghi đủ **4.179 file**, `+276.334/-268.473` dòng; số liệu đối soát với `git diff --shortstat`.
- Git trả về một trạng thái `T` thật cho symlink chuyển thành file thường. Bản script trong `tools/` giữ `T` và raw mode/blob; không gộp thành `M`.
- 14 gitlink đổi pointer. Chưa kết luận hành vi bên trong các dependency từ pointer đơn thuần.
- Mỗi hàng đã có đúng một owner `01`–`15`; validator chế độ `inventory` đã qua. `P0 816`, `P1 1.285`, `P2 2.078` chỉ là thứ tự đọc.
- **871 hàng `affect`. 556 hàng `trivial`. 2.752 hàng chưa phân loại.** Các finding đã xác minh bước đầu: [BLU-001–013, SEA-001–012](./02-bluestore-bluefs.md) về allocation file, BlueFS, fsck, tool và onode format; [KV-001–006](./03-rocksdb-block-device.md) về LevelDB, block IO, zoned device, KV, chỉ số RocksDB và cache; [CFG-001–014](./06-config-defaults.md)/[OSD-001–094](./01-osd-pg-recovery.md) cho mClock, default, recipe reshard, FastCGI RGW, MDS/MGR/MON, OSD scheduler, network bind, peering, scrub, SnapMapper, message compatibility, ObjectStore, Crimson và QA RADOS; [MON-001–025](./04-mon-osdmap-crush.md) cho checkpoint Quincy, quorum feature, pending key, CRUSH rule, MON log và command; [MSG-001–074](./05-messaging-auth-common.md) cho CephX, msgr2, định danh release, timer/cache, device metadata và logging; [MGR-001–019](./07-mgr-modules-monitoring.md) cho `.mgr`/SQLite, progress event, Prometheus exporter, telemetry opt-in, crash health, Influx, Zabbix, Telegraf, MGR activation, OSD/device metadata, retry clock, reweight CLI, lỗi cấu hình module và Dashboard service/alert/CRUSH API; [ADM-001–025](./08-cephadm-orchestrator.md) cho offline host, image identity, device cache, placement, agent, OSD deployment, SSH và QA upgrade, tuned profile, maintenance, monitoring, MON CRUSH location, NFS VIP, Rook QA, runbook, Keepalived image và tox; cùng [VOL-001–003](./09-ceph-volume-activation.md) cho inventory, encrypted zap và tox gate. [Owner 01](./01-osd-pg-recovery.md), [owner 02](./02-bluestore-bluefs.md), [owner 03](./03-rocksdb-block-device.md), [owner 04](./04-mon-osdmap-crush.md), [owner 05](./05-messaging-auth-common.md), [owner 06](./06-config-defaults.md), [owner 08](./08-cephadm-orchestrator.md), [owner 09](./09-ceph-volume-activation.md) và [owner 14](./14-security-cross-reference.md) đã hoàn tất binary gate trong phạm vi hàng của mình. Chưa thể tổng hợp rủi ro toàn suite.
- Commit target ghi ngày 2023-10-25, trong khi base ghi ngày 2024-02-26. Đây là hai release branch: target major mới hơn nhưng endpoint commit cũ hơn theo lịch. Cần đối chiếu riêng các backport Pacific cuối nhánh trước khi kết luận một fix có trong target.

## Mục lục

| Phần | Markdown | CSV | Trạng thái |
| --- | --- | --- | --- |
| 00 — inventory | [Báo cáo](./00-file-inventory.md) | [Dữ liệu](./00-file-inventory.csv) | Đã tạo, đối soát Git và phân owner |
| 01 — OSD/PG | [Báo cáo](./01-osd-pg-recovery.md) | [CSV](./01-osd-pg-recovery.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 02 — BlueStore | [Báo cáo](./02-bluestore-bluefs.md) | [CSV](./02-bluestore-bluefs.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 03 — KV/block | [Báo cáo](./03-rocksdb-block-device.md) | [CSV](./03-rocksdb-block-device.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 04 — MON/CRUSH | [Báo cáo](./04-mon-osdmap-crush.md) | [CSV](./04-mon-osdmap-crush.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 05 — messaging/auth | [Báo cáo](./05-messaging-auth-common.md) | [CSV](./05-messaging-auth-common.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 06 — config | [Báo cáo](./06-config-defaults.md) | [CSV](./06-config-defaults.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 07 — MGR | [Báo cáo](./07-mgr-modules-monitoring.md) | [CSV](./07-mgr-modules-monitoring.csv) | Đang phân tích |
| 08 — cephadm | [Báo cáo](./08-cephadm-orchestrator.md) | [CSV](./08-cephadm-orchestrator.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 09 — ceph-volume | [Báo cáo](./09-ceph-volume-activation.md) | [CSV](./09-ceph-volume-activation.csv) | Binary gate owner đã hoàn tất; lab còn mở |
| 10 — RADOS/RBD | [Báo cáo](./10-rados-rbd-clients.md) | [CSV](./10-rados-rbd-clients.csv) | Đang phân tích |
| 11 — CephFS | [Báo cáo](./11-cephfs-mds.md) | [CSV](./11-cephfs-mds.csv) | Đang phân tích |
| 12 — RGW | [Báo cáo](./12-rgw.md) | [CSV](./12-rgw.csv) | Đang phân tích |
| 13 — build/package | [Báo cáo](./13-build-packaging-submodules.md) | [CSV](./13-build-packaging-submodules.csv) | Đang phân tích |
| 14 — security | [Báo cáo](./14-security-cross-reference.md) | [CSV](./14-security-cross-reference.csv) | Binary gate owner đã hoàn tất; cross-reference còn mở |
| 15 — validation | [Báo cáo](./15-upgrade-validation.md) | [CSV](./15-upgrade-validation.csv) | Đang phân tích |

[Kế hoạch và tiêu chí hoàn thành](../PLAN-pacific-16.2.15-to-quincy-17.2.7.md) ghi report map và quy trình. Đọc inventory trước, rồi các báo cáo component sau khi chúng được tạo.

## Cách đọc dữ liệu

CSV dùng dấu `;`, UTF-8 BOM, CRLF và 21 cột chuẩn. Mỗi hàng là một đường dẫn endpoint; rename giữ nguồn ở `old_path`. `binary=TRUE` để trống LOC. `0/0` có thể là rename, mode-only hoặc marker, không đồng nghĩa không đổi. Priority và review mode là triage. Nhãn tác động cuối cùng sẽ nằm ở component CSV, không ở master.

Các kết luận nâng cấp cần có hunk, symbol ở hai endpoint, commit/test liên quan và điều kiện áp dụng. Chưa có kiểm chứng runtime hay thông tin As-Is cluster. Bộ này hiện **không** cung cấp quyết định GO/NO-GO production.

Validator `--mode complete` đã qua cho layout, link và partition CSV. Gate cuối `--mode complete --require-impact binary` hiện **không qua** vì 2.752 hàng còn thiếu nhãn và lý do; đây là trạng thái có chủ đích, không phải coi các hàng ấy là `trivial`.

## Tái lập

Chạy `tools/build_inventory.py` với `--repo ceph16.2.15/ceph --base v16.2.15 --target v17.2.7 --allow-non-ancestor --find-renames=50%` (rename threshold là mặc định), rồi so với `source-summary.json`. Script chỉ khác bản skill ở việc chấp nhận Git status `T`; `tools/validate_comparison.py` cũng chấp nhận `T` và kiểm tra hai endpoint mode/blob đều hiện diện.
