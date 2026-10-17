# 09 — ceph-volume, inventory và activation: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./09-ceph-volume-activation.csv) có 215 hàng và là subset đúng thứ tự của master inventory: `affect = 21`, `trivial = 194`, chưa phân loại = 0. Trong đó 192 hàng nằm dưới `ceph_volume/tests/`; chúng được review theo test/fixture role dù triage nền gắn `file_type=runtime/source`.

## Phạm vi và giới hạn bằng chứng

Đây là endpoint net diff `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) → `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo shallow/non-ancestor không cung cấp lịch sử commit đủ dùng; kết luận dựa trên hunk và caller/test ở hai endpoint.

Chưa có As-Is về LVM/raw/simple activation, dm-crypt/cryptsetup version, custom ceph-volume plugins, repeated LV names, DB/WAL migration, removable/USB/HM-SMR devices hay automation gọi FileStore options. Chưa chạy ceph-volume functional suite hoặc rehearsal trên clone device. Mọi thao tác zap/migrate bên dưới chỉ là scenario lab, không phải quyền chạy trên production.

## Finding ảnh hưởng upgrade

### CVFILESTORE-001 — ceph-volume xóa prepare/activate FileStore và journal CLI

**Evidence.** `devices/lvm/activate.py`, `prepare.py`, `batch.py`, `common.py`, `create.py`, `api/lvm.py`, `util/prepare.py`, `util/arg_validators.py`, `devices/simple/activate.py` và `zap.py` bỏ `--filestore`, `--journal*`, journal tags, FileStore mkfs/mount/activate và legacy simple JSON detection.

**Before/after.** Quincy ceph-volume vẫn có thể discover, prepare và activate FileStore; Reef chỉ giữ BlueStore. Automation còn truyền FileStore/journal option sẽ fail parse hoặc không tìm activation path. Đây là companion của `FILESTORE-001` ở owner 01/02: nếu còn FileStore OSD, phải migrate/reprovision trước hop, không dựa vào ceph-volume Reef để cứu activation. Tác động delivery/availability; confidence `high`, applicability `UNKNOWN`.

### CVCRYPT-001 — dm-crypt tự chọn no-workqueue theo cryptsetup và media

**Evidence.** `util/encryption.py` chạy `cryptsetup --version`, so với `2.3.4`, và thêm `--perf-no_read_workqueue --perf-no_write_workqueue` khi thiết bị non-rotational. `DmcryptAction` gọi probe ngay khi parse `--dmcrypt`; LVM activation cũng probe khi mở OSD đã mã hóa. `setup.py` thêm dependency `packaging`.

**Before/after.** Quincy mở LUKS/plain mapping không có hai perf flag; Reef tự thêm chúng khi điều kiện đúng. Nếu cryptsetup command/version output hoặc Python dependency lỗi, encrypted prepare/activate có thể fail trước OSD start. Nếu thành công, I/O scheduling/latency của dm-crypt thay đổi. Tác động activation/performance; confidence `high`, cần test theo cryptsetup/kernel/media thực tế.

### CVINVENTORY-001 — sysfs/udev discovery thay đổi partition, USB và phantom Atari

**Evidence.** `util/disk.py` dựng parent cho partition bằng realpath, không còn bỏ mọi removable device sớm, thêm `ID_BUS`, `parent`, `devname`, `actuators`; `util/device.py` reject USB thay cho generic removable và refresh full inventory khi path thiếu. `devices/raw/list.py` lọc child partition giả nếu parent có BlueStore label.

**Before/after.** Cùng host có thể trả device set/availability khác: non-USB removable có thể xuất hiện, USB bị reject theo bus, partition parent chính xác hơn, và Atari phantom child bị loại. Vì inventory thường cấp input cho orchestration, cần diff raw JSON giữa hai binary trước khi cho target tự chọn/zap/prepare. Tác động device targeting/capacity; confidence `high`.

### CVLVM-001 — LVM lookup và partition-backed auxiliary LV được sửa

**Evidence.** `devices/lvm/listing.py` tra cả `vg_name` và `lv_name` cho đối số `VG/LV`; `prepare.py::setup_device()` chấp nhận partition hoặc whole device khi tạo LV cho BlueStore auxiliary device.

**Before/after.** Quincy có thể chọn nhầm LV nếu cùng tên ở nhiều VG và không đi cùng nhánh với partition ở setup auxiliary device; Reef phân giải VG rõ ràng và chấp nhận layout partition-backed. Tác động inventory/provisioning correctness; confidence `high`. Cần lưu `pvs/vgs/lvs --reportformat json` và symlink/UUID trước rehearsal.

### CVMIGRATE-001 — DB/WAL migration tự zap LV nguồn sau thành công

**Evidence.** `devices/lvm/migrate.py` trả danh sách source LVs bị thay/remove; sau khi `ceph-bluestore-tool bluefs-bdev-migrate/new-db/new-wal` thành công và đóng encrypted source, target gọi `Zap(...).main()` cho từng LV nguồn.

**Before/after.** Quincy dọn tag nhưng không thực hiện cùng bước zap tự động này; Reef xóa signature/LV source sau migration thành công. Last reversible point vì vậy nằm trước migrate/zap, không phải sau khi tool trả success. Chỉ dùng khi runbook thật sự migrate DB/WAL, không phải mỗi binary restart. Tác động destructive cleanup/rollback; confidence `high`.

### CVZAP-001 — Zap encrypted partition và mapper targeting đổi

**Evidence.** `zap.py` lấy holder của encrypted partition qua metadata parent/partition mới; mapper device chỉ bị từ chối khi không phải multipath và không phải partition. `disk.py` thay partition detection bằng sysfs inventory.

**Before/after.** Reef có thể đóng dm-crypt mapping và chọn zap path khác Quincy trên partition/multipath. Sai inventory ở đây có blast radius trực tiếp. Trước mọi zap phải resolve canonical path, parent, LV tags, OSD FSID và giữ `--report`/dry-run evidence nơi có thể. Tác động destructive device operation; confidence `high`.

### CVPLUGIN-001 — Plugin discovery chuyển sang importlib.metadata

**Evidence.** `ceph_volume/main.py` dùng `importlib.metadata.entry_points()` và fallback `pkg_resources.iter_entry_points()` thay vì luôn dùng pkg_resources.

**Before/after.** Custom handler trong group `ceph_volume_handlers` có thể được discover khác theo Python/importlib metadata version và packaging format. Không ảnh hưởng khi deployment không có plugin; nếu có, phải import/list subcommand trên artifact Reef thật trước rollout. Tác động extensibility/delivery; confidence `high`, applicability `UNKNOWN`.

### CVACTIVATE-001 — mkdir_p tạo recursive parent

**Evidence.** `util/system.py` đổi `os.mkdir()` thành `os.makedirs()` trong helper vẫn chown path đích.

**Before/after.** Reef có thể tạo activation/preparation directory khi parent component chưa có, trong khi Quincy fail. Đây là behavior activation thật nhưng hẹp; cần kiểm owner/mode và không dùng việc tự tạo parent để che package/mount layout sai. Tác động activation reliability; confidence `high`.

### CVPKG-001 — ceph-volume có dependency Python `packaging` mới

**Evidence.** `setup.py` thêm `packaging` vào `install_requires`; `util/encryption.py` import `packaging.version` ở module load.

**Before/after.** Artifact target thiếu dependency có thể làm ceph-volume import fail, kể cả trước khi chạy encrypted subcommand. Package/image validation phải import tool và chạy help/inventory bằng đúng runtime Python trên host. Tác động delivery; confidence `high`.

**Closure.** Import dependency tự động kích hoạt at process/module load. Mixed-version hosts must use one resolved artifact/dependency set per ceph-volume invocation; full-Reef only after every host class smoke passes. Rollback is restore pinned package/Python environment, not install an untracked library in place. Chưa có artifact digest; validate import, help, inventory, plugin list and encrypted-path version parsing.

## Operational closure addenda

#### CVFILESTORE-001 — Closure

Mixed-version is allowed only after every active store and automation path is BlueStore-compatible; full-Reef cannot activate FileStore. Rollback is not target activation: replace/reprovision by redundancy plan or retain Quincy host until migrated. Validate metadata and absence of `--filestore`/journal flags before invocation.

#### CVCRYPT-001 — Closure

No-workqueue choice activates automatically from cryptsetup version/media during mapping; config override is explicit. Mixed/full must test each host class. Rollback requires close mapping, restore prior command/config and reopen on disposable clone; never remap live OSD blindly. Validate exact argv, reboot reopen, checksum and CPU/latency.

#### CVINVENTORY-001 — Closure

Discovery tự động runs on inventory/prepare/reconcile. Mixed/full must diff canonical devices across tool versions before action. Rollback for read-only inventory is pin old tool; any action selected from wrong inventory needs device recovery plan. Validate whole/partition/multipath/USB/phantom fixtures and zero unexpected target.

#### CVLVM-001 — Closure

Lookup/activation tự động applies when target ceph-volume resolves LVs. Mixed/full must test duplicate LV names, auxiliary partition DB/WAL and repeated activation. Rollback by stop OSD, restore old tool/symlinks only before metadata mutation; preserve tags/FSID manifest. Validation includes idempotency and exact resolved VG/LV/device.

#### CVMIGRATE-001 — Closure

Mixed tool versions must not concurrently manage one OSD migration; full-Reef only after clone rehearsal. Source-LV zap after success is destructive and defines last reversible point. Chưa có migration transcript. Validate failure before/after success, metadata snapshots, restart/checksum and confirmed source target IDs.

#### CVZAP-001 — Closure

Target resolution/mapping cleanup runs automatically after explicit zap command; never include zap in binary rollout. Mixed/full tooling does not make operation safer. No generic rollback after wipe: require disposable clone/snapshot and allowlisted canonical device. Chưa có dry-run evidence; validate parent/siblings/holders/tags unchanged outside scope.

#### CVPLUGIN-001 — Closure

Plugin discovery tự động runs at import/list/command dispatch. Rollback by restore pinned package/entry points/Python env; plugin side-effect commands need their own rollback. Validate import, plugin enumeration, duplicate/missing entry point and command smoke on exact artifact.

#### CVACTIVATE-001 — Closure

Recursive directory creation automatically occurs during target activation. Mixed/full must activate/re-activate on correct package/mount layout and check owner/mode. Rollback by stop daemon and remove only verified empty target-created directories or restore old artifact; never mask missing mount. Validation needs idempotent restart and path manifest.

## Trivial changes

194 hàng `trivial` gồm 192 unit/functional fixtures, Vagrant inventory, distro rename/removal và playbook chưa được chạy; một help-message capitalization fix trong `activate/main.py`; một comment-only edit trong raw prepare. Các test xóa FileStore và thêm coverage cho discovery/dm-crypt là evidence hỗ trợ findings, nhưng không phải kết quả acceptance của suite này.

## Validation đề xuất

1. **As-Is:** thu `ceph-volume inventory/list --format json`, `lsblk`, `blkid`, `pvs/vgs/lvs`, cryptsetup/kernel/Python/package version, objectstore type và custom entry points trên từng host class.
2. **Artifact smoke:** trên image/RPM/DEB đích, chạy import, `ceph-volume --help`, plugin list và inventory; fail nếu thiếu `packaging`, entry point hoặc subcommand dùng trong automation.
3. **Inventory diff:** cùng host fixture có whole disk, partition, multipath, USB/removable, HM-SMR và raw BlueStore parent/phantom child; so canonical device/parent/availability và không cho target action nếu set ngoài expected diff.
4. **Encrypted activation:** ma trận cryptsetup `<2.3.4`/`>=2.3.4`, HDD/SSD/NVMe, LUKS/plain; kiểm exact command, mapping reopen sau reboot, OSD start và latency/CPU. Lỗi version probe phải dừng trước thay đổi device.
5. **LVM activation:** repeated LV names ở hai VG, separate DB/WAL, partition-backed fast device và `--no-systemd`; kiểm tags/symlinks/FSID và idempotent reactivation.
6. **Migration rollback:** chỉ trên clone, snapshot metadata trước `new-db/new-wal/migrate`; xác nhận data sau restart rồi kiểm LV nguồn đã zap. Rehearse failure trước/sau tool success và định nghĩa rõ last reversible point.
7. **Zap safety:** encrypted partition + multipath fixture; ghi canonical target/parent/holders/tags, chạy dry-run/report nếu có, rồi zap disposable device. Fail nếu sibling/parent ngoài scope thay đổi.
8. **FileStore gate:** mọi host phải có bằng chứng không còn FileStore và automation không còn `--filestore`, `--journal*`; nếu không đạt thì `BLOCKED` trước first Reef ceph-volume invocation.

## Kết luận owner

Owner 09 đã khép binary gate. Ba gate thực tế trước rollout là: loại trừ FileStore/legacy journal automation; chứng minh encrypted activation với cryptsetup và dependency thật; và diff inventory/target resolution trước mọi prepare, migrate hoặc zap. `CVMIGRATE-001` và `CVZAP-001` là thao tác có thể phá hủy dữ liệu, nên chỉ đóng bằng rehearsal trên device clone/disposable cùng evidence target chính xác.

