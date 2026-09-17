# 09 — ceph-volume, inventory, LVM, activation và DB/WAL: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **76 dòng** do owner `09-ceph-volume-activation` sở hữu. Target làm đường restart/activation chắc chắn hơn cho LVM và raw OSD, sửa nhiều lỗi nhận diện thiết bị, và bổ sung workflow BlueFS DB/WAL có quản lý LVM tag. Tuy nhiên, `migrate`, `new-db`, `new-wal`, `zap` và provisioning đều là thao tác operator có side effect; cài bản mới không tự chạy chúng.
>
> **Trạng thái kiểm chứng:** đã đọc net diff hai endpoint, symbol/caller, commit trong range và test/tài liệu repository. Chưa restart OSD thật, chưa chạy ceph-volume functional tests, chưa có inventory device/LVM/dm-crypt của cluster đích.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; source tree non-shallow và sạch; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [09-ceph-volume-activation.csv](./09-ceph-volume-activation.csv). CSV có 76 dòng, giữ nguyên 21 cột nền của master inventory và nối 6 cột phân tích.
- Thống kê owner: `A8/M68`, `+6.675/-1.242`; `P1=32`, `P2=44`; không có binary, rename hay delete.

Disposition cuối của 76 dòng:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `conditional` | 11 | Runtime/tooling chỉ kích hoạt theo layout hoặc lệnh tương ứng |
| `mixed` | 15 | File có cả hunk finding-relevant và hunk refactor/support |
| `support` | 39 | Test, functional fixture hoặc tài liệu hỗ trợ finding |
| `trivial` | 11 | Đã sàng lọc nhưng không có causal chain upgrade độc lập |
| **Tổng** | **76** | Khớp chính xác CSV |

`P1/P2` là ưu tiên đọc ban đầu, không phải mức rủi ro. Không có dòng nào được gọi là `material` vô điều kiện vì phần lớn thay đổi chỉ chạy khi OSD được activate/restart hoặc khi operator gọi provisioning/migration.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Canary restart phải bao phủ đúng layout đang dùng.** Ít nhất một OSD LVM, một OSD raw nếu có, và một OSD dm-crypt nếu có phải được stop/start có kiểm soát; xác nhận block, DB và WAL symlink/mapping đúng trước khi mở rộng rollout.
2. **Chạy inventory từ đúng execution context của cephadm/container.** Target cố ý chạy LVM binary trong host namespace để tránh đọc/ghi metadata LVM trong container namespace. So sánh `ceph-volume inventory/list` với `lsblk`, `pvs/vgs/lvs`, by-id và multipath trên host.
3. **Không diễn giải sai regression trung gian.** Commit `d322bb891db` sửa activation chậm do refactor `5fc104acb00` đưa vào giữa range; `v16.2.5` không chứa chính regression đó. Endpoint target có cả refactor và fix, nên cần benchmark canary nhưng không được tuyên bố đây là lỗi sẵn có ở baseline.
4. **Tách upgrade khỏi DB/WAL migration.** `lvm migrate`, `new-db` và `new-wal` là lệnh opt-in, yêu cầu OSD dừng trừ khi cố ý dùng `--no-systemd`, và thay đổi BlueFS placement/LVM tags. Không ghép chúng vào cùng cửa sổ rolling upgrade nếu chưa có backup, rollback và test riêng.
5. **Audit encryption trước restart.** Target tôn trọng `osd_dmcrypt_key_size`, ngừng log LUKS secret, đóng mapper khi deactivate và hỗ trợ target encrypted trong DB/WAL migration. Kiểm tra effective key size, config-key access và mapper lifecycle trên canary.
6. **Không dùng inventory change để tự động zap/provision.** Target nhận diện partition, multipath, symlink, removable/USB và LVM membership khác base; mọi automation chọn thiết bị phải diff kết quả và yêu cầu allowlist rõ ràng.

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro khi kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| CVOL-001 | LVM command chạy trong host namespace | ceph-volume chạy trong container/cephadm | inventory/activate/provision | Cao nếu namespace sai | High |
| CVOL-002 | Generic/LVM/raw activation và DB/WAL discovery | OSD restart/activate | rolling restart | Trung bình-cao | High |
| CVOL-003 | Inventory, lsblk, LVM, partition và multipath | Host có topology tương ứng | preflight/reconcile | Trung bình-cao | High |
| CVOL-004 | Batch sizing, prepare, rollback và zap guards | Tạo/thay/xóa OSD | provisioning riêng | Cao vì có destructive path | High |
| CVOL-005 | BlueFS `migrate/new-db/new-wal` | Operator chủ động đổi DB/WAL | ngoài rollout | Cao | High |
| CVOL-006 | dm-crypt key, secret và mapper lifecycle | OSD encrypted hoặc encrypted migration | restart/migrate | Cao | High |

Mức rủi ro là hậu quả khi điều kiện đúng; applicability cho cluster cụ thể chưa biết vì chưa có As-Is.

## 4. Phát hiện chi tiết

### CVOL-001 — LVM phải chạy trong host namespace khi ceph-volume ở trong container

**Evidence.** Các dòng CSV `1105`, `1124`, `1166` và test `1125`/`1160` bao phủ `api/lvm.py`, process wrapper và executable lookup. Commit `9f3cc0c42086675c77b5262c6db2546f422b933b` thêm LVM wrapper chạy `pv/vg/lv` trong host namespace; commit ghi rõ mục tiêu là tránh corruption metadata LVM khi command chạy trong container. Các follow-up sửa executable lookup và wrapper behavior.

**Trước → sau.** Base gọi LVM tool theo execution namespace hiện tại. Target định tuyến các LVM command qua host context khi cần, để inventory, tag lookup và mutation nhìn cùng device namespace với host. Đây là behavior quan trọng cho cephadm vì ceph-volume thường được gọi qua container.

**Activation/mixed phase.** Binary ceph-volume nào được cephadm gọi quyết định behavior; OSD data format không tự đổi. Sai bind mount, executable path hoặc host/container namespace có thể làm inventory trống/sai, activation thất bại hoặc — ở provisioning path — thao tác nhầm LVM metadata.

**Kiểm chứng.** Trên mỗi kiểu host, chạy read-only inventory/list từ đúng cephadm context và đối chiếu host `lsblk -f`, `pvs`, `vgs`, `lvs`, LV tags và symlink. Stop rollout nếu cùng thiết bị có identity/availability khác giữa host và container.

**Đánh giá.** Rủi ro **cao khi containerized**, confidence **high**. Không có runtime test trên host đích trong báo cáo này.

### CVOL-002 — Target hợp nhất activation và nhận DB/WAL cho raw OSD

**Evidence.** Các dòng `1103`, `1104`, `1108`, `1117`, `1119`, `1121`, `1123` cùng test activation/raw. `ec946328149fe2c7f9347116ce73732ab60f3e89` thêm top-level `ceph-volume activate`, thử raw rồi LVM; `afc1db288d25a45cb16c8e977c1809fd0bb0b62c` thêm legacy simple fallback. LVM activation nạp config từ LV tag, suy luận objectstore và hỗ trợ `--no-tmpfs`. `8242ec16e5dd0bdabbb4bb6f39dbc0fa1e515713` cho raw list/activate nhận block DB/WAL để dựng lại symlink.

**Endpoint/history nuance.** Refactor `5fc104acb007c8eaa4be350031da61be2c695bda` gom inventory calls nhưng làm `_get_bluestore_info()` bị gọi theo cấp số nhân ở một trạng thái trung gian; `d322bb891dbaf420dd1d1d32d4ce3e8582bd715b` sửa trước endpoint. Tương tự, generic activation được thêm rồi sửa argument mismatch bởi `6beba5055c4a4befd94afd446eacec54e8448beb`. Vì vậy target không mang hai regression đó, còn base chưa có chính feature/refactor gây regression.

**Tác động upgrade.** OSD đang chạy không bị activate lại chỉ vì package/image đổi; edge xuất hiện ở restart/redeploy/host reboot. Raw OSD có separate DB/WAL, LVM tag không hoàn chỉnh hoặc legacy simple deployment là các nhánh cần test riêng.

**Kiểm chứng.** Chụp OSD ID/FSID, objectstore, block/DB/WAL device và symlink trước restart. Canary một OSD cho mỗi layout; sau start xác nhận đúng device identity, systemd/container state, BlueStore mount và client I/O. Đo thời gian inventory/activation nhưng không áp số benchmark trong commit cho hardware đích.

**Đánh giá.** Rủi ro **trung bình-cao**, confidence **high**.

### CVOL-003 — Device discovery đổi đáng kể; kết quả inventory có thể khác base

**Evidence.** Các dòng `1105`, `1112`, `1116`, `1119`, `1161`–`1163`, `1166` và 10+ test liên quan. Target gom `lsblk/pvs/vgs/lvs` thay vì gọi lặp cho từng device; bổ sung/fix partition support, symlink, device slaves, multipath membership, non-existing device filter, RBD-device exclusion, logical partition và phantom Atari partition. Các commit tiêu biểu gồm `5fc104acb00`, `65847261403`, `259a3d554f5`, `85670b4c6b7`, `ec2ab61d2e4`, `b8e21e5ca2e` và `f41b55722eb`.

**Trước → sau.** Target dùng snapshot device/LVM rộng hơn và nhiều guard topology hơn. Đây vừa giảm subprocess overhead vừa thay cách một device được gắn `available`, `ceph_device`, parent/slave hoặc LVM member. Churn/performance commit không tự chứng minh thời gian canary trên host thật.

**Activation/mixed phase.** Inventory read-only không đổi disk, nhưng cephadm drive-group và operator automation có thể dùng chính output đó để chọn candidate. Một device đổi classification giữa active MGR/ceph-volume versions có thể làm plan tạo OSD khác nhau.

**Kiểm chứng.** Export inventory JSON ở base và target trên host có NVMe/SATA, partition, multipath, symlink/by-id và LVM. Diff theo stable identity, không chỉ `/dev/sdX`; mọi candidate mới phải được operator xác nhận trước apply. Theo dõi runtime và số subprocess trên host nhiều device nếu maintenance window nhạy cảm.

**Đánh giá.** Rủi ro **trung bình-cao theo topology/automation**, confidence **high**.

### CVOL-004 — Provisioning và zap được harden nhưng vẫn là thao tác destructive riêng

**Evidence.** `batch.py`, `common.py`, `prepare.py`, `zap.py`, `drive_group/main.py`, validators/device/disk utilities và các functional tests map vào CVOL-004. Target sửa chia fast-device allocation, multi-PV VG và ZeroDivision edge; từ chối một số thiết bị có partition; cải thiện multipath/holder cleanup; rollback OSD và OSD-ID reuse; đồng thời sửa raw/LVM argument validation.

**Trước → sau.** Target có thể lập batch plan khác và dọn failure tốt hơn. Không hunk nào làm upgrade tự động repartition, zap hoặc tạo DB/WAL; các path chỉ chạy khi cephadm reconciliation có OSD spec cần apply hoặc operator gọi lệnh.

**Ranh giới an toàn.** `zap --destroy`, prepare và rollback có side effect không thể xem là validation read-only. Vì discovery semantics đổi theo CVOL-003, một automation dựa trên `available=true` mà không pin device ID là rủi ro lớn hơn bản thân code fix.

**Kiểm chứng.** Trước rollout đóng băng thay đổi OSD spec nếu không cần thiết. Trong lab, chạy batch report/dry-run với cùng inventory, so số OSD, data/DB/WAL allocation và VG free extents; thử failure rollback trên disposable devices. Production chỉ apply sau review allowlist theo serial/WWN.

**Đánh giá.** Rủi ro **cao khi provisioning/zap được kích hoạt**, confidence **high**.

### CVOL-005 — BlueFS DB/WAL migration là workflow mới, explicit và không atomic như package rollback

**Evidence.** Dòng `1114` là [migrate.py](../../ceph16.2.15/ceph/src/ceph-volume/ceph_volume/devices/lvm/migrate.py), với API/helper ở `1105`, command mapper `1113`, docs `37/40`–`43` và unit test `1132`. Commit `9851ed039fced73d248d6ad80e382d431b4889a1` bọc `ceph-bluestore-tool bluefs-bdev-migrate`, thêm `migrate`, `new-db`, `new-wal` và quản lý LVM tags; `80c211ffa5a7c621a3cbdfadb3733bf1a32c0f5c` mở rộng cho encrypted target.

**Contract endpoint.** Code kiểm tra OSD đã dừng bằng systemd trừ khi operator chủ động dùng `--no-systemd`; target phải là LV; source/target type phải khớp rule. Nó cập nhật tags, gọi `ceph-bluestore-tool`, dọn source DB/WAL trên success và cố `undo()` tags trên exception.

**Tác động/rollback.** Đây là mutation BlueFS placement và LVM metadata, không phải bước tự động của nâng 16.2.5→16.2.15. Undo tag không chứng minh mọi partial write/device mutation của tool đã được đảo ngược; package downgrade cũng không hoàn tác device layout.

**Kiểm chứng.** Tách change riêng sau khi cluster ổn định. Chụp LV tags, symlink, BlueFS device labels/usage và backup/DR prerequisite; stop đúng OSD, chạy trên canary, rồi activate, kiểm tra mount, DB/WAL mapping, spillover/space và scrub/workload. Stop condition là tool non-zero, tag/symlink lệch hoặc OSD không mount; không thử lại mù trước khi kiểm tra state.

**Đánh giá.** Rủi ro **cao nhưng hoàn toàn opt-in**, confidence **high**.

### CVOL-006 — Encrypted OSD lifecycle sửa key handling và hỗ trợ encrypted migration

**Evidence.** Các dòng `1106`, `1111`, `1114`–`1116`, `1120`, `1164`, `1165` và test/docs dm-crypt. `f69339e00f582ec64b843ff58b66817975fca0d7` làm ceph-volume tôn trọng `osd_dmcrypt_key_size` 256/512; `e3d626cd53d917a0e977e3c60509bb995f21e737` ngừng log LUKS key; `604756cbf04701c38caaaf0cb19a84a2018313a4` đóng encrypted mapper khi deactivate; `80c211ffa5a...` chuẩn bị/đóng mapper cho DB/WAL migration encrypted.

**Trước → sau.** Base có thể dùng default key size thay vì effective option và lộ secret qua process stdout log ở activation path. Target redacts secret tốt hơn và khép lifecycle mapper. Existing LUKS header không tự được re-encrypt khi nâng; key-size behavior chủ yếu áp dụng lúc tạo/mở theo path tương ứng.

**Activation/mixed phase.** OSD encrypted phụ thuộc config-key/lockbox access, mapper UUID, cryptsetup và correct device identity. Restart là thời điểm khác biệt lộ ra. Migration encrypted chỉ áp dụng khi operator gọi CVOL-005.

**Kiểm chứng.** Inventory OSD encrypted, key-size setting, mapper/device mapping và key access trước rollout. Canary deactivate/activate; xác nhận mapper đóng/mở đúng, OSD I/O phục hồi và log không chứa secret. Không đưa raw log có key vào ticket; rotate credential theo security process nếu đã có lịch sử log exposure.

**Đánh giá.** Rủi ro **cao khi dùng dm-crypt**, confidence **high**.

## 5. Trivial/support changes

- **39 support rows** là unit/functional tests, playbook, fixture và tài liệu cho activation, inventory, provisioning, migration và encryption. Chúng hỗ trợ sáu finding nhưng chưa được chạy trong môi trường này.
- **11 trivial rows** là tox/build plumbing, test-only root escape, help/import/refactor và tài liệu nhỏ không có upgrade edge độc lập.
- **11 conditional + 15 mixed rows** được map rõ tới CVOL-001…CVOL-006 trong CSV.

Tổng `11 conditional + 15 mixed + 39 support + 11 trivial = 76`; không có file owner nào bị bỏ khỏi screening.

## 6. Validation matrix đề xuất

| Scenario | Tiền điều kiện / pha | Quan sát bắt buộc | Stop condition |
| --- | --- | --- | --- |
| Host/container inventory | Mỗi topology device, trước rollout | stable ID, lsblk/LVM/tag parity, candidate list | Device identity/availability lệch không giải thích được |
| LVM OSD restart | Canary LVM có block/DB/WAL | activation duration, symlink, mount, I/O | Sai device, timeout hoặc OSD không up/in |
| Raw OSD restart | Có raw layout, nhất là separate DB/WAL | label discovery, reconstructed links, BlueStore mount | DB/WAL bị bỏ sót hoặc nhầm OSD |
| dm-crypt restart | OSD encrypted | mapper close/open, key-size/config access, secret-free log | Mapper/key lỗi hoặc secret xuất hiện |
| Multipath/partition inventory | Host có multipath/partition/by-id | parent/slave/LVM membership và allowlist | New false-positive candidate |
| Batch/provisioning lab | Disposable devices, ngoài rollout | dry-run allocation, VG extents, rollback cleanup | Plan khác expected hoặc chạm device ngoài allowlist |
| BlueFS migration lab | OSD stopped, backup/state capture | tags, labels, symlink, mount, space, workload | Non-zero, partial state, mount/I/O fail |

Các scenario này là thiết kế kiểm chứng, không phải ủy quyền chạy lệnh mutating trên cluster.

## 7. Giới hạn và kết luận

- Chưa có As-Is device map nên chưa biết raw/LVM, separate DB/WAL, multipath hay dm-crypt finding nào áp dụng.
- Repository tests được đọc nhưng chưa chạy; số liệu timing trong commit không phải benchmark của cluster đích.
- Hai regression activation chậm/argument mismatch được thêm và sửa hoàn toàn trong range; endpoint target chứa fix, baseline không chứa chính regression trung gian.
- Không có bằng chứng rằng upgrade tự chạy BlueFS migration, zap hoặc provisioning. Các thao tác đó phải có change riêng và authorization riêng.
- Chưa đủ dữ liệu để kết luận GO/NO-GO Production; gate tối thiểu là inventory parity và canary restart cho từng layout OSD thực tế.
