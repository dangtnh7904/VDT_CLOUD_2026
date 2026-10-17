# 09 — ceph-volume, device discovery, LVM và activation: v16.2.15 → v17.2.7

**Trạng thái: binary gate owner 09 đã hoàn tất; chưa chạy lab.** [CSV đầy đủ của owner](./09-ceph-volume-activation.csv) có 21 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Đã đối soát `affect = 6`, `trivial = 15`, **chưa phân loại = 0** trên 21 hàng owner này. Các finding dưới đây chỉ phân tích 6 hàng `affect`; 15 hàng còn lại vẫn có trong CSV.

## Phạm vi và phương pháp

Owner này phụ trách ceph-volume, device discovery, LVM và activation. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### VOL-001 — Device inventory và mapper/LV path thay đổi

**CSV:** `api/lvm.py`, `inventory/main.py`, `util/device.py`, `util/disk.py` dưới `src/ceph-volume/ceph_volume/`. Base `Devices` dựng report từ toàn bộ `sys_info.devices`; target thêm `--list-all`, mặc định lọc LV và partition khỏi report, thêm đường chuyển `/dev/mapper` sang `/dev/VG/LV`, sửa nhận diện qua `lsblk`/sysfs và multipath. Các commit trong target range gồm `e1020fdd3a3f4d69dddd9052df43a46cd94f7dc4`, `b39a1b8df97e2c7ee7beeef837fc68da65b1efaa`, `3fafe47f8811c15291a6e582e30a6c4fe9421d6b`, `c6485e2c70d5f6070c1d83e8a3d0048b96a21fb4`. `CephadmServe._refresh_host_devices` ở `src/pybind/mgr/cephadm/serve.py:334` gọi `ceph-volume inventory --filter-for-batch`, thêm `--list-all` nếu option MGR được bật; đây là caller context ở owner 08.

**Điều kiện:** cephadm hoặc operator refresh inventory trên host dùng LVM/partition/multipath; host khác có thể không thấy khác biệt. Trong rollout mixed-version, output phụ thuộc phiên bản ceph-volume/image chạy trên host và option `inventory_list_all`; sau full upgrade, target filtering áp dụng đồng nhất theo option. Đây là thay đổi observability/drive selection, không phải bằng chứng OSD cũ tự đổi layout hay bị zapped. **Evidence confidence:** high cho code path, medium cho mức độ ảnh hưởng cluster vì chưa có device topology.

**Kiểm chứng:** thu JSON inventory base theo từng host, nhất là mapper/partition/multipath; canary target image trên cùng host và đối chiếu path, `available`, LVM membership, device count. Quan sát `ceph orch device ls` và drive selection trước khi cho phép provisioning; không chạy zap hoặc tạo OSD trong bước so sánh. Test `test_lvm.py`, `test_device.py`, `test_disk.py` đã đọc ở mức hunk nhưng chưa chạy.

**Activation và rollback:** filtering chạy tự động mỗi lần caller thực thi inventory target; `--list-all` là lựa chọn explicit. Hunk `Inventory.main/get_report` chỉ dựng report, không ghi LVM/partition, nên có thể chạy lại tool base để đối chiếu. Nhưng drive selection dùng report đó để provision là bước ghi riêng: sau prepare/create, đổi tool không hoàn nguyên OSD/device. Ranh giới để dừng là trước khi approve drivegroup; lưu cả JSON inventory, đường mapper chuẩn hóa và spec đã chọn để tránh retry provisioning trên một device chỉ bị lọc khỏi output.

### VOL-002 — Cleanup encrypted partition khi gọi zap

**CSV:** `src/ceph-volume/ceph_volume/devices/lvm/zap.py`. `Zap.zap_partition()` trước đây tìm mapper holder qua `parent_device.sys_api['partitions'][devname]['holders']`; target dùng `device.sys_api['holders']` trực tiếp, rồi `dmcrypt_close()` trước unmount/wipe. Commit `90401ffd3ded129ad6085cb7a23635e2284fd624` và `956f9599010dc1f8ef7c639b16360280ddf08a96` liên quan đến holder/mapper handling.

**Điều kiện:** chỉ có tác động khi operator/tool gọi zap cho encrypted partition, chẳng hạn cleanup sau một lần reprovision thất bại trong cửa sổ bảo trì; nâng binary không tự gọi zap. Mixed-version dùng phiên bản tool tương ứng; sau full upgrade, target path được dùng. Thay đổi có thể quyết định mapper được đóng trước thao tác wipe; không suy ra phương án zap an toàn cho một OSD chứa dữ liệu. **Evidence confidence:** high cho nhánh code, medium cho applicability thực tế.

**Kiểm chứng:** chỉ trong lab với device disposable đã mã hóa, so sánh holder discovery/close behavior và error signal; không dùng device production. Ghi rõ quy trình recovery nếu OSD provisioning fail.

**Activation và rollback:** `Zap.zap_partition()` chỉ chạy explicit trong zap/cleanup; code target lấy holders của partition rồi tìm mapper để đóng trước wipe. Snapshot partition/LVM, mapper identity và key material theo policy trước thao tác là ranh giới recovery. Sau unmount/wipe, downgrade ceph-volume không khôi phục dữ liệu hay mapper state; một holder list rỗng cũng không chứng minh device an toàn để xóa. Trong lab, stop ngay nếu còn holder đang dùng hoặc identity không khớp disposable device đã chọn.

### VOL-003 — Tox mặc định kiểm ít hơn ở một số mục

**CSV:** `src/ceph-volume/tox.ini`. Base default envlist gồm `py36, py3, py3-flake8` và flake8 chạy toàn bộ rule mặc định; target bỏ `py36` và thêm `--select F,E9,W291`. Đây là hunk thay đổi **đường acceptance** nếu đội dùng `tox` mặc định làm gate trước rollout; không đổi runtime ceph-volume khi package đã chạy. Commit liên quan `1589b4799d30e67fbef6dd50e17b9443c1ceeb05` cùng các thay đổi tox trong range.

**Điều kiện:** áp dụng khi lab/CI chạy default tox theo repo này; nếu gate dự án dùng lệnh khác thì không áp dụng. Không có mixed-daemon effect; chỉ thay đổi validation coverage của target source. **Evidence confidence:** high cho tox config, medium cho applicability vì chưa biết gate dự án. **Kiểm chứng:** ghi lệnh CI/lab thực tế, chạy test phù hợp cả Python runtime đã triển khai và rule lint dự án yêu cầu; không dùng pass của tox target làm bằng chứng đã kiểm py36.

**Tác động và rollback:** impact là validation coverage: `skip_missing_interpreters=true` và envlist target không kiểm Python 3.6, còn `--select F,E9,W291` thu hẹp lint oracle. Không có mutation cluster; muốn hoàn nguyên coverage phải pin envlist/rule set explicit và rerun job trong clean environment. Giữ test inventory, interpreter version, skipped count và exit status; đổi tox file sau khi job đã PASS không bổ sung bằng chứng cho job cũ.

## Trivial changes

**15/21** hàng còn lại đã screen theo hunk/commit context: nhánh Luminous được bỏ nhưng Pacific và Quincy đều đi cùng nhánh command (`--no-mon-config`, `--keyfile -`); `__release__` đổi nhãn; ZFS/LSM/common chỉ sửa whitespace; unit tests/fixture chỉ hỗ trợ chứng cứ; dev-only ZFS pip pin không thuộc delivery/acceptance hiện có. Mỗi hàng và lý do nằm trong [CSV owner](./09-ceph-volume-activation.csv). Không có kết luận rằng toàn bộ ceph-volume không đổi: sáu hàng trên được giữ `affect`.


## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Đối chiếu host topology, cephadm drive selection và CI gate thực tế để xác định applicability của ba finding.
- Chạy lab/canary read-only inventory; zap chỉ được phép trên device disposable trong lab riêng.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
