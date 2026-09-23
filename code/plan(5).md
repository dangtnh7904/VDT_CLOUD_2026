# Kế hoạch phát triển RGW/RBD Storage Lab Console

**Dự án:** PRJ GD2 — công cụ tạo tải và quản lý dữ liệu thử nghiệm cho Ceph RGW/RBD  
**Ngày lập:** 21/09/2026  
**Trạng thái:** đặc tả để phát triển; chưa phải bằng chứng đã triển khai hoặc chạy thành công trên lab  
**Code hiện có:** [`code/rgw-console`](./rgw-console/)  
**Tài liệu upgrade liên quan:** [`comparison/ceph-osd-upgrade-lab-production-plan(1)(1).md`](../comparison/ceph-osd-upgrade-lab-production-plan%281%29%281%29.md)

## 1. Mục tiêu

Mở rộng console RGW hiện có thành một **Storage Lab Console** có bốn nhóm chức năng dùng chung một cơ chế kiểm soát dung lượng:

1. **RGW Object Console**
   - Xem danh sách bucket và object.
   - Xem metadata, preview, Range GET và download.
   - Tạo object, ghi đè/update object, sửa metadata và xóa object.
   - Chạy workload liên tục gồm `PUT`, `GET`, `HEAD/LIST`, `UPDATE` và `DELETE`.

2. **RBD Volume Console**
   - Tạo RBD image thử nghiệm.
   - Map image thành block device, format `ext4`, mount và cung cấp đường truy cập riêng cho từng volume.
   - Cho phép đọc/ghi/xóa file trong volume thử nghiệm.
   - Unmount, unmap và xóa volume theo đúng thứ tự.
   - Có workload lifecycle tạo → dùng → xóa volume.

3. **Capacity Guard**
   - Không dùng phần trăm trung bình của toàn cluster làm điều kiện.
   - Theo dõi OSD đầy nhất trong tập OSD có thể phục vụ các pool RGW/RBD liên quan.
   - Mốc `70%` là **application admission ceiling/SLO**: công cụ phải dừng cấp thao tác tăng dung lượng từ trước mốc này.
   - Đây không phải invariant vật lý mà polling có thể bảo đảm khi Ceph đang recovery/backfill, OSDMap đổi hoặc có writer ngoài ledger; các trường hợp đó phải pause mutation và báo breach nếu OSD vẫn vượt 70%.
   - Khi gần hoặc vượt ngưỡng, ưu tiên thao tác đọc và cleanup đã được phân loại/đặt maintenance budget.

4. **Performance Monitor**
   - Hiển thị IOPS đọc/ghi/tổng, throughput đọc/ghi/tổng và latency hiện tại của cluster Ceph.
   - Cho phép xem lịch sử ngắn theo cluster, participating OSD và pool khi nguồn telemetry thực sự cung cấp đúng scope.
   - Hiển thị riêng số liệu workload do console tạo; không gắn nhãn số request của ứng dụng là IOPS vật lý của cluster.
   - Công bố nguồn, cửa sổ lấy mẫu, độ mới và trạng thái reset/mất mẫu trên mọi biểu đồ.

Đây là công cụ **lab-only, quyền cao**. Không triển khai hệ thống login/RBAC trong MVP. Tuy nhiên, vẫn phải giới hạn pool, bucket, image prefix và mount root để một lỗi phần mềm không format hoặc xóa nhầm tài nguyên ngoài phạm vi bài thử.

## 2. Kết quả cần đạt

MVP được coi là hoàn thành khi đáp ứng đồng thời các điều kiện sau:

- Có thể duyệt, xem, download, overwrite và xóa object trong các bucket lab được cấu hình.
- Có thể chạy một RGW CRUD job dài hạn với tỷ lệ thao tác cấu hình được và có pause/resume/stop.
- Có thể tạo một RBD image mới, map exclusive, format ext4, mount, ghi/đọc kiểm tra, unmount, unmap và xóa image từ console.
- Mỗi volume có trạng thái, device, mount path và lịch sử thao tác riêng.
- RGW và RBD dùng chung một Capacity Guard và một sổ reservation, không tự tính dung lượng riêng rẽ.
- Khi telemetry thiếu/cũ hoặc dự báo thao tác kế tiếp có thể vượt trần, thao tác tăng dung lượng bị chặn. `GET`, `HEAD`, `LIST`, hard-delete exact version/unversioned cleanup, `unmount` và `remove` được ưu tiên nhưng vẫn phải chừa maintenance metadata budget và tuân theo khả năng thực tế của cluster.
- Backend/SSH reconnect hoặc restart không làm lặp `rbd create`, format lại filesystem, map trùng hoặc xóa nhầm volume.
- Dashboard hiển thị được OSD đầy nhất, participating OSD, reservation, trạng thái guard và nguyên nhân job bị pause.
- Dashboard hiển thị IOPS/throughput đọc-ghi hiện tại, latency và lịch sử ngắn; phân biệt rõ telemetry `application`, `ceph` và `device` (nếu có).
- Không có secret/keyring/access key bị ghi vào operation log, API response hoặc tài liệu.

## 3. Phạm vi MVP và ngoài phạm vi

### 3.1. Trong phạm vi

- Mọi pool RGW/RBD mà mutation chạm tới trong MVP phải là replicated pool; cấu hình mẫu hiện tại là `size=3`, `min_size=2`. Nếu phát hiện bất kỳ affected pool nào là EC, Capacity Guard phải fail closed cho mutation cho tới khi có phép tính EC riêng.
- Ceph Pacific 16.2.5 là baseline đầu tiên; code không được giả định chỉ chạy trên output của Reef.
- RGW S3 API và RGW Admin Ops/radosgw-admin cho tài nguyên lab.
- RBD format 2, kernel RBD (`krbd`) và filesystem ext4.
- RBD được quản lý trên một Linux Ceph/client host qua SSH; host này thực hiện `rbd map`, `mkfs.ext4`, `mount` và file I/O.
- Một RBD image chỉ có một client RW tại một thời điểm.
- Bucket/versioning được phát hiện và hiển thị rõ.
- Streaming workload do chính console tạo.
- Theo dõi IOPS, throughput và latency gần thời gian thực; số liệu Ceph lấy từ endpoint metrics read-only hoặc adapter đã được capability-test trên Pacific 16.2.5.
- PostgreSQL là state store và journal của console.
- SSE cho telemetry và trạng thái job theo thời gian gần thực.

### 3.2. Ngoài phạm vi MVP

- Dùng công cụ trên bucket, pool hoặc image production không có allowlist.
- EC pool cho bất kỳ data/index/metadata path RGW hoặc RBD nào mà console sẽ mutation; phép tính `k+m`, chunk/alignment và overwrite của EC để giai đoạn sau.
- RBD snapshot, clone, flatten, mirroring, live migration và multi-writer filesystem.
- RBD resize và force-purge snapshot/clone trong MVP.
- RGW multipart workload trong MVP; nếu endpoint multipart được thêm sau này thì phải reserve toàn expected size và cleanup part trước khi bật.
- Mount một ext4 image RW đồng thời trên nhiều host.
- Multi-user terminal, terminal production hoặc cơ chế sandbox shell mạnh. MVP chỉ có một web terminal lab qua SSH vào host đã cấu hình.
- Tự sửa CRUSH map, tự reweight OSD hoặc tự đổi `nearfull/backfillfull/full` ratio.
- Cam kết physical hard cap khi OSDMap không ổn định, có recovery/backfill, hoặc còn writer ngoài controller mà không có reservation đầy đủ.
- Tự động xóa object/volume không thuộc job hoặc không nằm trong allowlist để lấy lại dung lượng.
- Thay thế công cụ benchmark chuyên dụng như Warp hoặc fio; có thể tích hợp các công cụ đó ở giai đoạn sau.

## 4. Hiện trạng console

Console hiện có các thành phần:

- React/Vite frontend và Nginx.
- FastAPI backend dùng boto3/S3.
- Một Python worker cho streaming job.
- PostgreSQL lưu operation, metrics và job.
- SSE gửi metrics mỗi giây.

Chức năng đã có:

- `GET /api/health` và `GET /api/buckets`.
- Upload từ corpus Ubuntu, upload từ browser và random upload.
- ListObjectsV2 có pagination/filter.
- HEAD object.
- Streaming/Range GET, preview và download.
- Streaming job có pause/resume/stop.

Khoảng trống cần xử lý:

- Worker hiện chỉ thực hiện `PUT`.
- Mọi upload hiện tạo key timestamp/UUID mới, chưa có overwrite cùng key.
- Chưa có object delete, bulk delete hoặc metadata update.
- Bảng `operations` chỉ chấp nhận `PUT` và `GET`.
- Chưa có migration framework.
- Chưa đọc OSD/CRUSH/pool capacity.
- Backend container không có Ceph CLI, `/dev/rbd`, keyring hoặc quyền mount.
- Chưa có RBD SSH execution layer, web terminal, file browser/SFTP và state tracking cho map/mount.
- Worker chưa có lease bền vững; không được scale worker trước khi sửa cơ chế claim job.

Các file cần đọc trước khi bắt đầu:

- [`rgw-console/backend/app/main.py`](./rgw-console/backend/app/main.py)
- [`rgw-console/backend/app/storage.py`](./rgw-console/backend/app/storage.py)
- [`rgw-console/backend/app/worker.py`](./rgw-console/backend/app/worker.py)
- [`rgw-console/backend/app/db.py`](./rgw-console/backend/app/db.py)
- [`rgw-console/backend/app/config.py`](./rgw-console/backend/app/config.py)
- [`rgw-console/frontend/src/App.tsx`](./rgw-console/frontend/src/App.tsx)
- [`rgw-console/docker-compose.yml`](./rgw-console/docker-compose.yml)

## 5. Các quyết định thiết kế bắt buộc

### 5.1. RBD chạy trên Linux host qua SSH, không chạy trong Windows/FastAPI container

Windows chỉ chạy browser/web service. Mọi thao tác Ceph/RBD thực tế chạy trên **Linux Ceph/client host** đã có `ceph-common`, `rbd`, kernel RBD và keyring.

Backend RBD dùng kết nối SSH cố định tới host lab:

- `ssh2.exec()` cho lệnh có cấu trúc như `ceph -s`, `rbd ls/info/create`, `rbd device map/unmap`, `blkid`, `mkfs.ext4`, `mount`, `umount`.
- `ssh2.shell()` cho web terminal tương tác qua WebSocket + `xterm.js`.
- `ssh2.sftp()` cho file browser: list, upload, stream preview/download, mkdir và delete trong mountpoint ext4.
- Windows chỉ cần browser/Node.js cho web console; không cài Ceph client hoặc RBD block-device driver trên Windows.

SSH layer vẫn phải validate `pool`, image prefix và mount root trước destructive command. Command do REST API sinh ra phải dùng argument đã validate/escape; không ghép trực tiếp input người dùng thành shell command. Web terminal là ngoại lệ có chủ đích cho **lab-only interactive testing** và phải được hiển thị rõ là shell thật trên host.

Để giảm rủi ro credential, ưu tiên SSH key. Tài khoản SSH có thể là user lab có `sudo -n` cho tập lệnh RBD/mount cần thiết; không bắt buộc phải dùng `root` nếu sudo đã cấu hình phù hợp.

### 5.2. Không dùng cluster average cho ngưỡng 70%

Nguồn quyết định chính là `ceph osd df --format=json` theo từng OSD. `ceph df detail`, `rados df`, RGW bucket stats và `rbd du` chỉ dùng để đối chiếu hoặc hiển thị, không được dùng một mình để cấp phép ghi.

`participating_osds` của một workload là hợp của:

- OSD eligible theo CRUSH rule/device class của mọi pool workload chạm tới.
- OSD trong current `up`/`acting` set của các PG liên quan.
- OSD đang là backfill/recovery target nếu có.

Với RGW, phải inventory data pool, index pool và các metadata/log pool bị thao tác sử dụng. Với RBD, phải xét cả metadata pool và data pool nếu image dùng data pool riêng.

### 5.3. Mốc 70% là admission SLO, không phải target chính xác

Không cố giữ từng OSD đúng 70%. CRUSH, kích thước OSD, rebalance, recovery/backfill, BlueStore overhead, telemetry lag và external write khiến một controller polling không thể duy trì physical invariant tuyệt đối. Contract mạnh nhất của MVP chỉ áp dụng khi mọi writer thuộc ledger, OSDMap/placement ổn định và không có recovery/backfill. Ngoài contract này, controller phải dừng cấp mutation, chuyển sang `PAUSED_REMAP`/`RECONCILING`, và báo nếu physical usage vẫn vượt 70%; không được tuyên bố đã ngăn được breach.

Thứ tự ưu tiên state là `EMERGENCY_CAPACITY` → `PAUSED_REMAP/RECONCILING` → `BLOCKED_TELEMETRY` → `PAUSED_CAPACITY` → `THROTTLED` → `NORMAL`. Chính sách ban đầu:

| Điều kiện của OSD đầy nhất trong scope | Trạng thái | Hành động |
| --- | --- | --- |
| `< 67%` | `NORMAL` | Cho phép thao tác tăng dung lượng nếu reservation fit |
| `67% đến < 68%` | `THROTTLED` | Giảm RPS/concurrency; không tăng batch |
| `68% đến < 70%` | `PAUSED_CAPACITY` | Không cấp PUT/update/RBD create/file-write mới; multipart/resize chưa thuộc MVP bị reject |
| `>= 70%` | `EMERGENCY_CAPACITY` | Dừng producer; chỉ chạy operation nằm trong emergency maintenance policy |
| Telemetry stale/mất | `BLOCKED_TELEMETRY` | Fail closed cho thao tác tăng dung lượng |
| OSDMap epoch đổi | `RECONCILING` | Dừng cấp mới, tính lại scope và reservation |
| Degraded/remapped/recovery/backfill | `PAUSED_REMAP` | Dừng mutation tăng dung lượng; quan sát và reconcile placement |

Giá trị trên là mặc định để bắt đầu đo, phải cấu hình được. Không tự đổi `mon_osd_full_ratio` thành 0,70. Ceph full/backfillfull có thể chặn cả ghi và recovery; application guard phải dừng sớm hơn.

### 5.4. Mọi mutation phải qua một Capacity Guard dùng chung

Guard không chỉ chạy khi tạo job hoặc ở UI. Nó phải được gọi ngay trước từng operation có thể tăng raw usage:

- RGW `PUT` object mới.
- RGW overwrite/update.
- Multipart initiation/batch nếu được bổ sung sau MVP; cho tới lúc đó API/job config phải từ chối mode multipart.
- RBD create ở chế độ `reserved-logical`; reserve trước worst-case của toàn logical size.
- RBD resize tăng nếu được bổ sung sau MVP; hiện tại không expose API resize.
- File write qua SFTP/terminal bên trong volume `reserved-logical` không tạo reservation cho từng syscall; chúng tiêu thụ phần logical capacity đã reserve khi tạo volume.

Không dùng `new_size - old_size` làm reservation cho overwrite. RGW có thể phải giữ đồng thời bản mới và dữ liệu cũ chờ GC; reserve toàn bộ kích thước bản mới cộng margin.

### 5.5. Xóa không đồng nghĩa dung lượng đã được trả ngay

- RGW versioned delete có thể chỉ tạo delete marker.
- RGW overwrite/delete có dữ liệu chờ garbage collection.
- Multipart bị bỏ dở có thể còn part cần abort/cleanup.
- RBD snapshot/clone có thể giữ dữ liệu.
- Xóa file trong ext4 không trả block về RBD nếu discard/TRIM chưa chạy.

Do đó phải phân loại delete:

- DELETE không có `VersionId` trên bucket versioned có thể tạo delete marker; đây là metadata-increasing mutation, không phải cleanup thuần túy.
- Hard-delete exact version hoặc unversioned delete là cleanup intent nhưng vẫn có thể ghi bucket index/log/metadata và vẫn có thể thất bại khi cluster full.
- Cleanup chỉ được chạy khi còn **emergency maintenance budget** nhỏ, cấu hình riêng; không bypass admission vô điều kiện.
- Nếu RGW ops/usage logging được bật, cả read/delete cũng có thể phát sinh metadata/log. P0 phải inventory cấu hình này và giữ headroom tương ứng.
- Reservation không được credit ngay khi API delete trả thành công.
- Chỉ chuyển guard sang resume khi telemetry OSD thật sự giảm và ổn định qua số mẫu cấu hình được.

### 5.6. ext4 là single-writer trong MVP

Image phải bật/verify feature `exclusive-lock` và được map bằng `rbd device map --exclusive`. Tùy chọn này tắt cooperative lock transition nhưng không bảo đảm syscall map của một external client luôn thất bại ngay. RBD SSH service phải kiểm tra mapping cục bộ và `rbd status`/watcher, từ chối mapping thứ hai do console quản lý, và acceptance test phải chứng minh writer thứ hai không acquire/write được. Contract không bao phủ client ngoài controller.

Nếu cần multi-node RW trong tương lai, phải dùng clustered filesystem hoặc thiết kế khác; không dùng ext4.

## 6. Kiến trúc mục tiêu

```text
Browser
  │
  ├── RGW/Capacity/Performance UI ───────────────┐
  │                                              │
  └── RBD UI + File Browser + Web Terminal       │
                                                 ▼
Existing FastAPI backend                  Node.js RBD service
  ├── RGW router → boto3/RGW              ├── REST → ssh2.exec()
  ├── Capacity Guard / reservation        ├── Files → ssh2.sftp()
  ├── Performance collector               └── Terminal WS → ssh2.shell()
  └── PostgreSQL                                  │
                                                   │ SSH :22
                                                   ▼
                                           Linux Ceph/client host
                                             ├── ceph / rbd CLI
                                             ├── /dev/rbdX
                                             └── /mnt/rbd/<volume>/ (ext4)
                                                   │
                                                   ▼
                                               Ceph cluster
```

RBD service có thể chạy cùng máy Windows với frontend trong lab. Nếu muốn một cổng duy nhất, Nginx/dev proxy route `/api/rbd/*`, `/api/rbd-files/*` và `/ws/terminal` sang Node.js service; RGW/capacity/performance tiếp tục đi FastAPI.

Capacity Guard vẫn giữ vai trò cấp phép trước `RBD_CREATE`. Vì web terminal có thể ghi trực tiếp vào filesystem ngoài từng API write, volume dùng terminal phải chạy mode **`reserved-logical`**: reserve trước worst-case của toàn logical size. Như vậy shell/SFTP có thể ghi tự do trong dung lượng image đã được budget, thay vì giả vờ kiểm soát từng `write()`.

### 6.1. Thành phần backend đề xuất

Giữ backend RGW hiện có và thêm một RBD service nhỏ:

```text
rgw-console/
  backend/app/                  # FastAPI hiện có
    api/
      rgw.py
      jobs.py
      capacity.py
      performance.py
    services/
      rgw_service.py
      capacity_guard.py
      capacity_collector.py
      performance_collector.py
      reservation_service.py
    workers/
      rgw_crud_worker.py

  rbd-console/                  # Node.js
    src/
      server.js                 # Express + WebSocket
      ssh.js                    # connection/reconnect/exec
      rbd.js                    # create/map/mount/unmount/delete
      files.js                  # SFTP list/read/upload/delete/mkdir
      terminal.js               # ssh2.shell() ↔ WebSocket
      state.js                  # observed image/device/mount state
      validators.js             # pool/image/mount-root guard
```

### 6.2. Nguyên tắc thực thi SSH/RBD

- REST action phải có timeout và command log đã redact.
- Sau timeout/reconnect, đọc observed state trước khi retry; timeout không đồng nghĩa command chưa chạy.
- Không format image cũ chỉ vì đang `MAPPED`; trước `mkfs.ext4` phải kiểm tra `wipefs -n`/`blkid` và chỉ format image vừa tạo, chưa có signature.
- Mountpoint luôn được sinh bên dưới `RBD_MOUNT_ROOT`, ví dụ `/mnt/rbd/<safe-name>`.
- File browser chỉ được truy cập bên dưới mountpoint của volume đã biết. Dùng SFTP `realpath/lstat` để chặn `..`, absolute path ngoài root và symlink escape.
- Preview file không yêu cầu copy file sang Windows: backend stream bytes từ SFTP. Ảnh dùng `Content-Type` phù hợp và `Content-Disposition: inline`; text/PDF có thể xem inline; file khác dùng download.
- Web terminal là shell thật trên Linux host. Không dùng terminal làm backend API implementation; create/mount/delete vẫn đi qua action REST có validation và audit.

## 7. Capacity Guard chi tiết

### 7.1. Cấu hình ban đầu

```yaml
capacity_policy:
  observe_only: true
  hard_ceiling_ratio: 0.70
  admission_stop_ratio: 0.68
  throttle_start_ratio: 0.67
  resume_ratio: 0.67
  collector_interval_seconds: 2
  metrics_max_age_seconds: 5
  resume_consecutive_samples: 3
  operation_lease_seconds: 30
  settlement_consecutive_samples: 3
  settlement_min_seconds: 10
  raw_overhead_factor: 1.10
  fixed_metadata_bytes_per_object: null
  safety_margin_ratio_per_osd: 0.01
  safety_margin_min_bytes_per_osd: null
  emergency_maintenance_bytes: null
  fail_closed_on_osdmap_change: true
  pause_on_degraded_or_remapped: true
  require_clean_for_rbd_format: true
  failure_reserve_mode: none   # none | one_osd | one_host
```

Các giá trị này là policy của ứng dụng, không phải config Ceph.

### 7.2. Công thức quyết định

Ledger không cộng nguyên một reservation đã được phản ánh vào `observed_used` mãi mãi. Với mỗi participating OSD `i`:

```text
projected_used_i = observed_used_i
                 + pending_unobserved_increase_i
                 + remaining_persistent_commitment_i
                 + new_operation_worst_case_i
                 + safety_margin_i

projected_ratio_i = projected_used_i / total_bytes_i
```

Operation chỉ được admit nếu:

```text
telemetry_is_fresh
AND osdmap_epoch_is_current
AND all required pools/rules are known
AND max(projected_ratio_i) < admission_stop_ratio
AND no relevant OSD is full/backfillfull
AND no relevant PG is degraded/remapped/recovering/backfilling
```

`safety_margin_i` là giá trị lớn hơn giữa `total_i × safety_margin_ratio_per_osd` và `safety_margin_min_bytes_per_osd`; không để một ký hiệu chưa cấu hình đi vào quyết định. `new_operation_worst_case_i` phải gồm replica amplification của từng affected pool, placement skew/conservative bound, object allocation rounding và fixed metadata budget đã hiệu chỉnh bằng lab. Không credit compression/dedup dự kiến vào admission.

Nếu không xác định được participating OSD, affected pools, per-pool replication, safety margin hoặc raw amplification, trả `BLOCKED_UNKNOWN_CAPACITY`, không giả định còn chỗ.

#### 7.2.1. Per-OSD bound cho MVP

Không lấy aggregate raw rồi chia đều theo số OSD. MVP dùng hai mức:

1. **Exact/known mapping:** khi biết được RADOS object/PG và acting set đúng epoch, phân bổ payload + allocation/metadata budget cho đúng OSD trong acting set.
2. **Candidate-wide conservative bound:** khi RGW chưa cho biết internal RADOS object name/PG trước PUT, charge maximum single-replica bytes của operation cộng fixed metadata budget lên **mọi** eligible OSD của affected pool; aggregate raw (`logical × replica size`) chỉ dùng báo cáo và pool-level check. Một OSD không nhận hai replica của cùng object trong topology hợp lệ, nên single-replica bound là conservative cho một operation dưới stable CRUSH. Với nhiều object/chunk, cộng toàn bộ bytes có thể rơi vào cùng OSD. Cách này có thể over-reserve mạnh nhưng không được thay bằng average share nếu chưa có simulator được kiểm chứng.

Optimization sau MVP có thể mô phỏng/object-map theo OSDMap và phân bố PG, nhưng phải so với candidate-wide bound trong test. Bất kỳ remap/recovery nào cũng làm binding cũ mất hiệu lực và chuyển controller sang `PAUSED_REMAP`.

### 7.3. Reservation

Reservation phải có:

- `reservation_id`.
- `owner_type`: request/job/volume.
- `owner_id`.
- FSID, OSDMap epoch và danh sách affected pools.
- Logical bytes và estimated raw bytes.
- Child rows `(reservation_id, pool_id, osd_id, estimated_bytes)` hoặc conservative bound cho mọi pool/OSD bị ảnh hưởng; một reservation multi-pool phải commit nguyên tử.
- `lease_owner`, `lease_generation`, `heartbeat_at` và `lease_expires_at` cho operation ngắn hạn.
- `created_at` và state.
- `PENDING`, `IN_FLIGHT`, `LEASE_EXPIRED_UNRECONCILED`, `SETTLING`, `PERSISTENT_COMMITMENT`, `RELEASED`.

Tách hai loại charge:

- **Transient operation reservation:** có lease được heartbeat khi request/upload/multipart còn chạy. Lease hết không tự release; chuyển `LEASE_EXPIRED_UNRECONCILED` và vẫn bị tính cho tới khi reconciler biết outcome.
- **Persistent volume commitment:** không có TTL tự hết. Charge bằng `max(0, worst_case_full_allocation - conservatively_attributed_actual_allocation)` trong toàn bộ lifetime volume. Nếu không đo/attribution đủ tin cậy, giữ nguyên full commitment; chấp nhận over-reserve thay vì overbook.

Flow chuẩn:

1. Đọc capacity snapshot còn mới.
2. MVP mở một advisory lock toàn FSID. Tối ưu sau này có thể khóa ordered set `FSID + OSD_ID`, nhưng mọi pool dùng chung OSD phải cùng lock domain; không khóa riêng từng pool.
3. Cộng `pending_unobserved_increase` và `remaining_persistent_commitment` trên toàn FSID theo từng OSD.
4. Tính worst-case multi-pool của operation mới.
5. Nếu fit, tạo reservation và child rows per-pool/per-OSD rồi commit nguyên tử.
6. Thực hiện operation, heartbeat kèm fencing generation.
7. Thành công operation ngắn hạn: chuyển sang `SETTLING`. Sau configured settle window và các fresh post-operation samples, chuyển phần đã phản ánh vào `observed_used` ra khỏi pending charge. Vì không thể attribution hoàn hảo từ aggregate OSD delta, giữ conservative charge nếu snapshot không đủ tin cậy.
8. Volume reserved-logical: chuyển thành `PERSISTENT_COMMITMENT`; không release khi lease request tạo volume hết hạn.
9. Thất bại/timeout/lease expiry: vẫn charge và reconcile observed state trước khi release.
10. Delete volume chỉ release commitment sau khi image ID không còn tồn tại và có fresh post-delete samples. RGW cleanup chỉ tạo headroom khi policy quan sát được headroom mới; không gán một aggregate drop bất kỳ cho owner rồi credit hai lần.

### 7.4. RBD logical reservation

RBD là thin-provisioned. Có hai mode:

#### `reserved-logical` — mặc định

- Trước khi trả volume cho người dùng ghi trực tiếp, reserve raw worst case của toàn logical size.
- Với replicated pool, ước lượng ban đầu:

```text
estimated_raw = logical_size × pool_size × raw_overhead_factor
```

- Công thức aggregate chỉ là điểm bắt đầu, không phải per-OSD proof. Reservation phải tạo child rows cho metadata/data pool với replica size riêng, cộng fixed object/index/OMAP budget và kiểm tra per-OSD headroom/placement skew; không chỉ chia đều estimated raw cho số OSD.
- Nếu không đủ bằng chứng để phân bổ per OSD, dùng conservative bound và từ chối image quá lớn.
- Khi OSDMap đổi, ngừng cấp volume mới và reconcile lại reservation.

#### `actual-use` — chỉ để thử nghiệm best-effort

- Không reserve toàn logical size.
- Theo dõi actual raw usage và dừng writer do console quản lý.
- Không cam kết application admission ceiling nếu người dùng SSH vào mountpoint và tự ghi ngoài controller.
- UI phải hiển thị nhãn `BEST EFFORT` rõ ràng.

### 7.5. Failure reserve

Cap 70% trong trạng thái bình thường không chứng minh còn đủ chỗ khi mất một OSD/host hoặc khi drain OSD. Nếu policy yêu cầu vẫn dưới 70% sau một failure, phép tính aggregate dưới đây chỉ là **điều kiện cần**, không phải PASS gate:

```text
allowed_used_raw <= 0.70 × (eligible_raw_capacity - failed_domain_capacity)
```

Admission `one_osd`/`one_host` còn phải mô phỏng hoặc lập conservative bound cho remap của từng PG theo CRUSH, heterogeneous capacity, data skew và target-specific headroom. Với lab chỉ có 3 OSD và replica theo host, mất một OSD còn không có failure domain thứ tư để phục hồi đủ `size=3`, dù phần trăm dung lượng còn thấp. Capacity Guard phải báo `NO_RECOVERY_TARGET`; không được biến phép tính aggregate thành tuyên bố cluster vẫn đủ replica.

## 8. RGW Object Console

### 8.1. Phạm vi quyền

MVP dùng một identity RGW lab có quyền quản lý toàn bộ bucket thử nghiệm. Cần phân biệt:

- S3 `ListBuckets` có scope theo account/owner; không dùng kết quả này để tuyên bố đã liệt kê mọi bucket được policy grant hoặc mọi bucket trong cluster.
- Inventory cluster-wide dùng RGW Admin Ops. Đọc/ghi/xóa object qua S3 phải dùng RGW system/admin identity lab hoặc explicit owner credential có data access phù hợp; admin inventory cap và S3 data access là hai contract cần test riêng.
- Không log access key/secret key.
- Không đọc secret từ biến `VITE_*` hoặc gửi secret xuống browser.

Nếu chưa cấu hình admin identity, console phải ghi rõ scope là `CURRENT_S3_IDENTITY`, không được gắn nhãn “toàn cluster”.

### 8.2. API object đề xuất

Giữ API đang có và bổ sung:

```text
GET    /api/buckets
GET    /api/objects
GET    /api/objects/head
GET    /api/objects/content

PUT    /api/objects/content
PATCH  /api/objects/metadata
DELETE /api/objects
POST   /api/objects/bulk-delete
GET    /api/objects/versions
```

Quy ước:

- Tất cả endpoint kiểm tra bucket allowlist, kể cả read/list; không chỉ kiểm tra delete.
- `GET /objects` và `GET /objects/versions` dùng continuation marker/token opaque, limit có trần và trả `next_token`.
- `PUT /objects/content` nhận bucket, exact key, Content-Type, Content-Length bắt buộc và optional checksum/`If-Match`; đây là create hoặc overwrite. Nếu không biết trước kích thước thì upload vào staging bounded hoặc từ chối, không stream vô hạn rồi mới admission.
- `PATCH /objects/metadata` thực hiện copy object lên chính nó với metadata mới khi backend/S3 API hỗ trợ.
- `DELETE /objects` nhận optional `version_id`.
- Bulk delete giới hạn batch và trả kết quả từng object; không trả success chung nếu một phần thất bại.
- API manual delete được phép xóa object trong bucket allowlist.
- Auto streaming delete mặc định chỉ xóa object có trong catalog của chính job.
- Mutation hỗ trợ `Idempotency-Key`; response ghi `request_id`, bucket/key/version/result và capacity decision. HEAD/GET/metadata response phải phân biệt version ID/current head/delete marker khi RGW trả được thông tin đó.

### 8.3. Semantics cần hiển thị trên UI

- `UPDATE` content là `PUT` lại cùng key, không phải PATCH byte-range.
- Metadata update có thể là self-copy và phát sinh I/O tương đương object mới.
- Bucket versioned: delete không có `VersionId` có thể tạo delete marker.
- Hard delete phải list và xóa đúng version/delete marker.
- ETag không được coi là SHA-256 payload trong mọi trường hợp, đặc biệt multipart.
- Preview binary không tin cậy tiếp tục bị chặn như console hiện tại.

### 8.4. RGW CRUD streaming job

Payload đề xuất:

```json
{
  "schema_version": 2,
  "job_type": "rgw_crud",
  "client_id": "loadgen-01",
  "bucket": "rgw-lab-data",
  "prefix": "console-jobs/run-001/",
  "payload_source": {
    "corpus_ids": ["mixed"],
    "category_weights": {
      "images": 35,
      "data": 25,
      "documents": 20,
      "media": 10,
      "archives": 10
    },
    "min_bytes": 4096,
    "max_bytes": 1048576,
    "naming_strategy": "generated"
  },
  "operation_weights": {
    "PUT": 28,
    "GET": 28,
    "HEAD": 3,
    "LIST": 2,
    "UPDATE": 20,
    "DELETE": 19
  },
  "requests_per_second": 5,
  "concurrency": 4,
  "duration_seconds": 3600,
  "object_limit": null,
  "max_live_objects": 10000,
  "max_live_logical_bytes": 10737418240,
  "delete_scope": "job_owned",
  "auto_drain": true,
  "version_policy": "detect",
  "capacity_policy_id": "default-70"
}
```

Worker behavior:

1. Claim job bằng lease có `lease_generation` fencing token; mọi heartbeat, counter update, reservation và pre-operation admission phải so owner + generation. Worker cũ mất lease không được tiếp tục mutation.
2. Chọn operation theo weight và inventory hiện tại.
3. Capacity Guard có quyền override operation mix.
4. Nếu không có object để GET/UPDATE/DELETE, chọn một operation hợp lệ khác và ghi lý do.
5. `PUT` tạo key mới trong prefix job.
6. `UPDATE` chỉ chọn object/version job-owned, tạo payload/version mới và reserve toàn kích thước mới.
7. `GET/HEAD/LIST` không làm tăng capacity reservation.
8. `DELETE` phân biệt delete-marker creation và hard-delete. Auto cleanup chỉ xóa version/delete marker job-owned, đánh dấu catalog là deleting và chỉ chuyển deleted sau khi S3/ListObjectVersions xác nhận.
9. Không credit raw capacity từ DELETE cho đến khi collector quan sát thấy dung lượng giảm.
10. Ghi per-operation counters, bytes, latency, error và capacity decision.

Khi `PAUSED_CAPACITY`:

- Dừng `PUT`, `UPDATE`; multipart chưa thuộc MVP tiếp tục bị reject.
- Tiếp tục `GET`, `HEAD`, `LIST`.
- Có thể tăng tỷ lệ DELETE trên object job-owned nếu job bật `auto_drain=true`.
- Nếu không có object được phép xóa, chuyển job sang pause; không mở rộng delete scope.

Job config phải là discriminated/versioned union. `job_type=legacy_put` giữ nguyên các trường hiện có (`client_id`, `corpus_ids`, category weights, naming strategy); migration không được biến job cũ thành `rgw_crud` thiếu payload source.

Catalog versioned không dùng một mutable row duy nhất cho mỗi key. Lưu row bất biến theo `(bucket, key, version_id hoặc synthetic_unversioned_id)`, cờ `is_delete_marker`, owner job và một head pointer riêng. Bucket ở trạng thái `Suspended` phải có test riêng. Cleanup của job phải list/reconcile versions rồi hard-delete toàn bộ version/marker do job tạo; không được xóa version của owner khác.

## 9. RBD Volume Console

### 9.1. Pool, host và naming

- Dùng pool lab riêng, mặc định `rbd-lab`; `rbd pool init` chỉ chạy một lần ở provisioning.
- Chọn một Linux Ceph/client host cố định, ví dụ `10.20.20.12`, đã có `ceph-common`, `rbd`, keyring, SSH server và kernel RBD.
- Image do console tạo dùng prefix cố định, ví dụ `lab-<name>` hoặc `lab-<uuid>`.
- Mount root cố định, ví dụ `/mnt/rbd`; mỗi image mount vào `/mnt/rbd/<safe-image-name>`.
- Windows không map RBD và không format filesystem; `ext4` chỉ tồn tại/mount trên Linux host.

### 9.2. State đơn giản cần theo dõi

```text
NOT_FOUND
  → CREATED
  → MAPPED
  → FORMATTED
  → MOUNTED
  → UNMOUNTED
  → UNMAPPED
  → DELETED
```

Không cần daemon đặc quyền riêng chạy trên Linux host. Node.js RBD service xác định **observed state** bằng các lệnh read-only qua SSH như `rbd info`, `rbd device list`, `blkid` và `findmnt` trước/sau mỗi action. Nếu SSH rớt hoặc command timeout, trạng thái chuyển `UNKNOWN` và phải probe lại trước retry.

### 9.3. Create + map + ext4 + mount

Flow mặc định:

1. Validate pool, image name, size và mount root.
2. Capacity preflight/reservation nếu Capacity Guard đang bật.
3. `rbd create <pool>/<image> --size <MiB>`.
4. `rbd device map <pool>/<image> --exclusive`; lấy device thực từ `rbd device list --format=json`.
5. Kiểm tra `wipefs -n` và `blkid`. Chỉ image vừa tạo, chưa có signature mới được `mkfs.ext4 -m 0 <device>`.
6. `mkdir -p /mnt/rbd/<image>` và `mount <device> <mountpoint>`.
7. Probe bằng cách ghi file nhỏ, `sync`, đọc lại và xóa probe.
8. Trả về `image`, `device`, `mount_path`, filesystem và observed state.

Ví dụ lệnh trên Linux host:

```bash
rbd create rbd-lab/test01 --size 1024
rbd device map rbd-lab/test01 --exclusive
# ví dụ /dev/rbd0
wipefs -n /dev/rbd0
blkid /dev/rbd0 || true
mkfs.ext4 -m 0 /dev/rbd0
mkdir -p /mnt/rbd/test01
mount /dev/rbd0 /mnt/rbd/test01
```

### 9.4. Web terminal

- Frontend dùng `xterm.js`; backend Node.js dùng `ssh2.shell()` và pipe qua WebSocket.
- Terminal mở shell trực tiếp trên Linux host, nên có thể chạy `ls`, `cat`, `dd`, `fio` hoặc thao tác file trong `/mnt/rbd/<image>`.
- Đóng tab/session thì SSH shell đóng; RBD mount **không** tự unmount chỉ vì terminal đóng.
- Terminal là công cụ lab để test RBD sau upgrade, không phải sandbox production.

### 9.5. File browser và preview nội dung ext4

Sau khi volume ở trạng thái `MOUNTED`, file trong ext4 là file Linux bình thường. Console đọc chúng qua **SFTP**, nên vẫn duyệt và xem được nội dung mà không cần mount RBD trên Windows.

API đề xuất:

```text
GET    /api/rbd/images
POST   /api/rbd/images
GET    /api/rbd/images/:name
POST   /api/rbd/images/:name/mount
POST   /api/rbd/images/:name/unmount
DELETE /api/rbd/images/:name
GET    /api/rbd/devices

GET    /api/rbd/images/:name/files?path=/
GET    /api/rbd/images/:name/files/content?path=/photos/a.jpg
PUT    /api/rbd/images/:name/files/content?path=/docs/test.txt
POST   /api/rbd/images/:name/directories
DELETE /api/rbd/images/:name/files?path=/tmp/a.bin

WS     /ws/terminal
```

File browser hỗ trợ:

- List folder: name, type, size, mtime.
- Upload file từ browser vào ext4 qua SFTP.
- Download file.
- Preview text (`txt`, `log`, `json`, `yaml`, `md`, source code) với giới hạn kích thước.
- Preview ảnh phổ biến (`jpg`, `jpeg`, `png`, `gif`, `webp`, `svg`) bằng endpoint stream `inline`.
- Preview PDF inline khi browser hỗ trợ.
- Các binary khác chỉ hiển thị metadata + nút download.
- Tạo directory và xóa file/directory trong mount root.

Không tin extension một mình; backend cần xác định/whitelist MIME hợp lý và luôn đặt `X-Content-Type-Options: nosniff`. Với file lớn, stream theo chunk; không load toàn bộ file vào RAM.

### 9.6. Unmount, unmap và delete

```bash
sync
umount /mnt/rbd/test01
rbd device unmap /dev/rbd0
rbd rm rbd-lab/test01   # chỉ khi người dùng chọn Delete
```

Quy tắc:

- Unmount khi busy trả conflict; không dùng lazy unmount mặc định.
- Unmap đúng device đang map tới image đã xác minh.
- Delete image chỉ sau khi đã unmount/unmap; snapshot/dependency còn tồn tại thì báo lỗi, không force purge.
- `Unmount`/`Unmap` không làm mất dữ liệu. Re-map + mount lại image cũ phải thấy nguyên file đã ghi trước đó.

### 9.7. API action và idempotency tối thiểu

Create/mount/unmount/delete nên có `action_id` + `Idempotency-Key` để tránh double-click hoặc HTTP retry gây duplicate destructive action. Không cần state machine/reconciler phức tạp ở host, nhưng vẫn cần probe observed state trước khi chạy:

- `mount` khi đã mounted → trả current state, không mount lần hai.
- `unmount` khi đã unmounted → idempotent success.
- `create` cùng idempotency key → trả image/action cũ.
- Không bao giờ tự `mkfs` một image có filesystem signature đã tồn tại.

### 9.8. RBD lifecycle test sau upgrade

Mục tiêu RBD của MVP là xác nhận dữ liệu vẫn hoạt động sau upgrade:

1. Create 1–3 image test.
2. Map + ext4 + mount.
3. Upload một tập file gồm text + ảnh + binary; lưu SHA-256.
4. Đọc/preview ảnh và text từ web; đọc lại qua terminal.
5. Ghi thêm file lớn bằng terminal (`dd`/`fio` nếu cần).
6. Unmount + unmap.
7. Re-map + mount lại cùng image.
8. Verify file list + SHA-256 + preview ảnh vẫn đúng.
9. Sau khi xác nhận xong mới delete image nếu muốn cleanup.

Nếu sau này cần job tự động create/use/delete nhiều vòng, bổ sung sau; không bắt buộc cho MVP 2–3 ngày.

## 10. Database và migration

### 10.1. Migration framework

Thêm Alembic hoặc một migration runner có version rõ ràng. Không tiếp tục chỉ dựa vào một chuỗi `CREATE TABLE IF NOT EXISTS` vì cần thay CHECK constraint và schema qua nhiều phiên bản.

Tạo one-shot service/command `migrate` chạy trước backend và worker. Nó phải fingerprint schema legacy, stamp revision ban đầu sau khi xác minh, rồi apply migration trong transaction phù hợp. Backend/worker/RBD Node.js service đợi migration hoàn tất và không chạy runtime DDL. Backup PostgreSQL trước migration lab có dữ liệu cần giữ; không cho hai process bootstrap schema đồng thời.

### 10.2. Bảng `operations`

Mở rộng hoặc thay CHECK constraint để hỗ trợ ít nhất:

```text
PUT, GET, HEAD, LIST, UPDATE, DELETE,
RBD_CREATE, RBD_MAP, RBD_FORMAT, RBD_MOUNT,
RBD_FILE_READ, RBD_FILE_WRITE, RBD_FILE_DELETE,
RBD_UNMOUNT, RBD_UNMAP, RBD_DELETE
```

Schema hiện tại bắt buộc `bucket` và `object_key`, nên không thể chỉ thêm RBD kind. Migration phải:

- Backfill row cũ thành `target_type='RGW_OBJECT'` và `target_id` ổn định.
- Cho `bucket`/`object_key` nullable với row không phải RGW.
- Thêm `target_type` và `target_id` NOT NULL sau backfill.
- Thêm conditional CHECK: RGW object operation phải có bucket/key; RBD operation phải có volume ID/action tương ứng.
- Giữ chi tiết command lifecycle ở `rbd_actions`; `operations` là audit/metric record chung, không thay state store RBD.

Thêm các trường:

- `request_id`, `job_id`, `volume_id`.
- `target_type`, `target_id`.
- `bytes_delta_logical`, `estimated_bytes_delta_raw`.
- `capacity_decision_id`, `osdmap_epoch`.
- `error_code`, `error`.

### 10.3. Bảng mới

#### `stream_objects`

- Job, bucket, key, immutable version ID hoặc synthetic ID cho unversioned object.
- `is_delete_marker`, owner job, head pointer riêng, size, ETag và checksum nếu có.
- State: LIVE/UPDATING/DELETING/DELETED/UNKNOWN.
- Created/updated/deleted timestamps.

#### `capacity_snapshots`

- FSID, OSDMap epoch, timestamp.
- Collector version và freshness.
- Cluster health summary.

#### `capacity_osds`

- Snapshot ID, OSD ID.
- Total/used/available bytes, used ratio.
- Up/in state, host/device class.
- Pool/rule scope metadata.

#### `capacity_reservations`

- Owner, affected pools, logical/raw estimate, reservation class và remaining commitment.
- Lease owner/generation/heartbeat cho transient operation; persistent volume commitment không tự expire.
- State và epoch binding.

#### `capacity_reservation_allocations`

- Reservation ID, pool ID, OSD ID và estimated bytes.
- Unique theo reservation/pool/OSD; dùng để cộng atomically trên toàn FSID.

#### `capacity_decisions`

- Request/job/action, policy version, input snapshot và OSDMap epoch.
- State/reason, participating OSD, projected ratios và decision ADMIT/THROTTLE/BLOCK.
- Liên kết các reservation tạo ra bởi decision.

#### `performance_samples`

- `fsid`, `source`, `scope_type`, `scope_id`, `captured_at`, `window_seconds` và collector version.
- Read/write/total IOPS; read/write/total bytes-per-second; latency fields chỉ lưu khi nguồn cung cấp đúng semantics.
- `fresh`, `reset_detected`, `partial` và metadata/capability để UI không biến mất mẫu thành số 0.
- Unique theo source/scope/timestamp/window; index theo `(fsid, source, scope_type, scope_id, captured_at)`.
- Raw sample giữ mặc định 24 giờ; rollup 1 phút giữ mặc định 30 ngày. Retention phải cấu hình được và cleanup theo batch.

#### `idempotency_requests`

- Scope/actor, `Idempotency-Key`, HTTP method/resource và canonical request fingerprint.
- State `CLAIMED/IN_PROGRESS/SUCCEEDED/FAILED_RETRYABLE/FAILED_FINAL`, owner/fencing generation, request/action ID và response/result đã redact.
- Unique theo `(scope, idempotency_key)`; claim trong transaction trước mutation.
- Retry cùng key + cùng fingerprint replay kết quả hoặc trạng thái hiện có. Cùng key nhưng khác fingerprint trả conflict; không phát lại versioned PUT/self-copy/delete.
- Áp dụng chung cho RGW và RBD; `rbd_actions.idempotency_key` tham chiếu record này thay vì tạo contract riêng không đồng bộ.

#### `rbd_volumes`

- Volume UUID, pool, namespace, image name và immutable image ID.
- Logical size, actual allocation quan sát được, capacity mode.
- Feature set, state, device, FS UUID và mountpoint.
- Created/updated/deleted timestamps và last error.

#### `rbd_actions`

- Action ID/idempotency key.
- Volume, action type, intended state và observed state.
- Start/end, timeout, exit code, redacted result.

### 10.4. Job lease

Thêm các trường:

- `job_type`.
- `lease_owner`.
- `lease_generation`/fencing token.
- `lease_expires_at`.
- `heartbeat_at`.
- `paused_reason`.
- Per-operation counters/bytes.

Claim job phải atomic. Worker khác chỉ được takeover khi lease hết hạn và sau bước reconcile. Mọi heartbeat, state/counter update, reservation và pre-operation admission phải kèm đúng `lease_owner + lease_generation`; worker cũ bị fence không được tiếp tục mutation.

## 11. API telemetry và response contract

### 11.1. Capacity snapshot

```text
GET /api/capacity?scope_type=pool&scope=rbd-lab
GET /api/capacity/stream
```

Response tối thiểu:

```json
{
  "fsid": "redacted-id",
  "osdmap_epoch": 123,
  "captured_at": "2026-09-21T10:00:00Z",
  "fresh": true,
  "policy": {
    "hard_ceiling_ratio": 0.70,
    "admission_stop_ratio": 0.68,
    "resume_ratio": 0.67
  },
  "state": "NORMAL",
  "most_full_osd": 2,
  "most_full_ratio": 0.641,
  "participating_osds": [0, 1, 2],
  "pending_unobserved_raw_bytes": 268435456,
  "remaining_persistent_commitment_raw_bytes": 805306368,
  "contract": "STABLE_EPOCH_CONTROLLED_WRITERS",
  "reasons": []
}
```

### 11.2. Lỗi chuẩn

| HTTP | Code | Ý nghĩa |
| --- | --- | --- |
| 409 | `CAPACITY_LIMIT` | Operation không fit policy |
| 409 | `VOLUME_BUSY` | Volume đang được dùng/mount busy |
| 409 | `DEPENDENCY_EXISTS` | Snapshot/clone/dependency chặn delete |
| 409 | `STATE_CONFLICT` | DB intent và observed state không khớp |
| 422 | `INVALID_SCOPE` | Pool/bucket/image/path ngoài allowlist |
| 423 | `RECONCILING` | RBD service/controller đang đối chiếu observed state |
| 503 | `TELEMETRY_STALE` | Không có capacity evidence đủ mới |
| 503 | `CEPH_UNAVAILABLE` | Không truy cập được Ceph/RGW |

Response lỗi phải có `request_id`, stable error code, message, retryable và observed state; không trả command string chứa secret.

### 11.3. Control plane và RBD SSH service

Các control bắt buộc:

```text
GET  /api/control/state
POST /api/control/emergency-stop
POST /api/control/resume

GET  /api/rbd/ssh/health
GET  /api/rbd/ssh/capabilities
GET  /api/capacity/decisions/{decision_id}
```

- `GET /api/rbd/ssh/health` kiểm tra SSH connect, host identity, `ceph fsid`, `rbd --version`, mount root và quyền cần thiết; không trả private key/password/keyring.
- Capability response cho biết `rbd`, `mkfs.ext4`, `mount`, `umount`, SFTP và interactive shell có sẵn hay không.
- Emergency stop ngừng action tạo/tăng dung lượng mới từ API. Terminal đang mở không thể bị coi là fully controlled writer; volume dùng terminal phải được reserved-logical từ trước.
- Resume chỉ được chấp nhận khi capacity/telemetry gate đạt.

### 11.4. API hiệu năng hiện tại

```text
GET /api/performance/current?source=ceph&scope_type=cluster&scope=<fsid>
GET /api/performance/history?source=ceph&scope_type=osd&scope=2&from=...&to=...&step=15s
GET /api/performance/stream?source=ceph&scope_type=cluster&scope=<fsid>
```

Response tối thiểu:

```json
{
  "schema_version": 1,
  "source": "ceph",
  "scope_type": "cluster",
  "scope": "redacted-fsid",
  "captured_at": "2026-09-21T10:00:00Z",
  "window_seconds": 15,
  "fresh": true,
  "reset_detected": false,
  "iops": {"read": 120.0, "write": 80.0, "total": 200.0},
  "throughput_bps": {"read": 10485760.0, "write": 5242880.0, "total": 15728640.0},
  "latency_ms": {"read_avg": 2.1, "write_avg": 3.4},
  "context": {"recovery_active": false, "osdmap_epoch": 123},
  "reasons": []
}
```

Contract đo lường:

- `application`: tính từ operation journal/job của console, gồm request/s, payload byte/s, success/error và p50/p95/p99. Đây là tải do console quan sát, không phải tổng IOPS Ceph.
- `ceph`: lấy counter client read/write từ Ceph mgr/Prometheus hoặc adapter read-only tương đương, rồi tính rate bằng `delta(counter) / delta(time)`. Đây là nguồn mặc định cho thẻ “IOPS/throughput hệ thống”.
- `device` là tùy chọn từ node exporter/iostat và chỉ bật khi ánh xạ OSD ↔ device ↔ host đã được xác minh; không trộn device I/O với Ceph client I/O.
- Tách read/write và client/recovery/replication nếu nguồn có counter tương ứng. Không cộng recovery/backfill vào client throughput rồi gắn nhãn là workload.
- Scope pool/RBD image chỉ xuất hiện khi metric có label/counter đáng tin cậy. Không suy ra per-pool bằng cách chia cluster total hoặc cộng các OSD dùng chung nhiều pool.
- “Hiện tại” là rate của cửa sổ hoàn chỉnh gần nhất, mặc định 15 giây; API luôn trả `window_seconds`, unit và timestamp. Có thêm cửa sổ 1 phút/5 phút để làm mượt.
- Counter giảm do daemon restart/wrap hoặc đổi identity phải tạo `reset_detected=true` và sample `UNKNOWN/PARTIAL`; không phát spike âm/dương giả. Mất mẫu hoặc quá `stale_after` phải trả `fresh=false`, không điền 0.
- Performance Monitor chỉ dùng quan sát/cảnh báo. Không được dùng sample IOPS/throughput để cấp phép Capacity Guard nếu chưa có một contract admission riêng được kiểm chứng.

## 12. Frontend

### 12.1. Navigation mới

```text
Live dashboard
Performance
Upload objects
Random object
RGW CRUD stream
Object explorer
RBD volumes
Capacity
```

### 12.2. Global capacity banner

Mọi view có banner nhỏ hiển thị:

- Guard state.
- OSD đầy nhất và phần trăm.
- Application admission ceiling/admission stop và contract hiện tại.
- Telemetry age.
- Active reservation.
- Lý do pause/block.

Không cho nút thao tác tăng dung lượng chỉ dựa vào disabled UI; backend/worker vẫn phải enforce.

### 12.3. Object Explorer

Drawer object bổ sung:

- Exact bucket/key/version.
- Overwrite content.
- Edit metadata.
- Delete current head.
- Hard delete version khi bật advanced mode.
- Bulk select/delete.
- Kết quả từng action và operation ID.

### 12.4. RBD Volumes

Danh sách volume hiển thị:

- Display name, pool/image ID.
- Logical size, actual allocated và reserved raw.
- Lifecycle state.
- Device/mount path.
- Filesystem/FS UUID.
- Capacity mode.
- Các action hợp lệ ở state hiện tại.

Volume detail gồm file browser, preview pane (text/ảnh/PDF), event/command timeline, nút mở web terminal và nút mount/unmount/delete. Destructive action vẫn cần modal xác nhận tên volume; đây là guard chống thao tác nhầm, không phải RBAC.

### 12.5. Performance

- Thẻ hiện tại: read/write/total IOPS, read/write/total throughput theo MiB/s và latency có sẵn.
- Biểu đồ time-series có range 5 phút, 1 giờ, 24 giờ; chọn source/scope và cửa sổ 15 giây, 1 phút, 5 phút.
- Mỗi thẻ/biểu đồ phải hiện `source`, scope, thời điểm mẫu, tuổi mẫu và cửa sổ tính rate; stale/reset/partial dùng trạng thái trực quan riêng, không vẽ về 0.
- Có overlay OSD down, recovery/backfill, job start/stop và upgrade event để đối chiếu nguyên nhân biến động.
- Khi xem `application`, UI ghi rõ “console workload”; khi xem `ceph`, ghi rõ “Ceph client counters”; `device` ghi rõ “physical device I/O”.

## 13. Cấu hình

Không ghi giá trị secret vào file plan. Các biến dự kiến:

Backend/worker env:

```text
CEPH_EXPECTED_FSID
CEPH_CLUSTER_NAME
RBD_SSH_SERVICE_URL

RBD_ALLOWED_POOLS
RBD_ALLOWED_NAMESPACES
RBD_IMAGE_PREFIX
RBD_MOUNT_ROOT
RBD_DEFAULT_CAPACITY_MODE

RGW_ADMIN_MODE
RGW_ALLOWED_BUCKETS
RGW_STREAM_PREFIX_ROOT

CAPACITY_OBSERVE_ONLY
CAPACITY_HARD_CEILING_RATIO
CAPACITY_ADMISSION_STOP_RATIO
CAPACITY_THROTTLE_START_RATIO
CAPACITY_RESUME_RATIO
CAPACITY_COLLECTOR_INTERVAL_SECONDS
CAPACITY_METRICS_MAX_AGE_SECONDS
CAPACITY_RESUME_CONSECUTIVE_SAMPLES
CAPACITY_OPERATION_LEASE_SECONDS
CAPACITY_SETTLEMENT_CONSECUTIVE_SAMPLES
CAPACITY_SETTLEMENT_MIN_SECONDS
CAPACITY_RAW_OVERHEAD_FACTOR
CAPACITY_FIXED_METADATA_BYTES_PER_OBJECT
CAPACITY_SAFETY_MARGIN_RATIO_PER_OSD
CAPACITY_SAFETY_MARGIN_MIN_BYTES_PER_OSD
CAPACITY_EMERGENCY_MAINTENANCE_BYTES
CAPACITY_FAIL_CLOSED_ON_OSDMAP_CHANGE
CAPACITY_PAUSE_ON_DEGRADED_OR_REMAPPED
CAPACITY_REQUIRE_CLEAN_FOR_RBD_FORMAT
CAPACITY_FAILURE_RESERVE_MODE

PERFORMANCE_ENABLED
PERFORMANCE_SOURCE
PERFORMANCE_PROMETHEUS_URL
PERFORMANCE_PROMETHEUS_BEARER_TOKEN
PERFORMANCE_COLLECTOR_INTERVAL_SECONDS
PERFORMANCE_CURRENT_WINDOW_SECONDS
PERFORMANCE_STALE_AFTER_SECONDS
PERFORMANCE_RAW_RETENTION_HOURS
PERFORMANCE_ROLLUP_RETENTION_DAYS
PERFORMANCE_ALLOWED_SCOPES
```

RBD Node.js/SSH service env:

```text
RBD_HOST
RBD_SSH_PORT
RBD_SSH_USER
RBD_SSH_KEY_PATH
RBD_SSH_PASSWORD            # optional; ưu tiên key
RBD_POOL
RBD_MOUNT_ROOT
RBD_IMAGE_PREFIX
RBD_COMMAND_TIMEOUT_MS
RBD_FILE_PREVIEW_MAX_BYTES
RBD_ALLOWED_PREVIEW_MIME
```

SSH credential chỉ nằm ở Node.js service env/secret store và không trả ra browser. `RBD_SSH_KEY_PATH` phải trỏ tới private key chỉ process service đọc được.

MVP có thể dùng CephX `client.admin` trên Linux SSH host vì yêu cầu lab quyền cao. RGW không dùng CephX key này; RGW dùng access/secret của một RGW system/admin identity riêng. Production hóa sau này phải thay bằng caps tối thiểu; việc đó không nằm trong MVP này.

Thông tin xác thực của Prometheus (nếu endpoint có auth) chỉ nằm ở backend secret store/env, không trả ra frontend. Không tự bật/thay cấu hình module Ceph trong runtime; P0 phải inventory endpoint, metric names, labels và scrape interval trước.

## 14. Kế hoạch triển khai theo pha

### P0 — Inventory chỉ đọc

- Xác nhận FSID, version, OSD topology, pool/CRUSH rule, RGW pools, bucket versioning và telemetry source.
- Chốt `rbd-lab`, Linux SSH host, `RBD_MOUNT_ROOT` và SSH account.
- Trên SSH host kiểm tra `ceph -s`, `rbd --version`, `rbd device list`, `mkfs.ext4`, `mount`, `umount`, SFTP và quyền `sudo` nếu dùng.
- Không thay cluster ngoài provisioning đã duyệt.

### P1 — Giữ RGW backend + dựng RBD SSH service

- Giữ FastAPI/worker hiện có cho RGW, capacity và performance.
- Tạo `rbd-console` Node.js với Express + `ssh2` + WebSocket.
- Tạo `/api/rbd/ssh/health`, `GET /api/rbd/images`, `GET /api/rbd/devices` read-only trước.
- Tạo validator cho pool, image prefix, mount root và safe path.
- Thêm command timeout, reconnect và redacted command log.

Điều kiện hoàn thành: web service connect được host, FSID đúng, đọc được image/device state và không cần cài Ceph/driver trên Windows.

### P2 — Capacity/performance observe-only

- Giữ Capacity Guard và Performance Monitor như thiết kế hiện tại.
- Collector có thể chạy qua SSH read-only tới Linux host thay vì Linux SSH host.
- Xác minh UI với `ceph osd df` và counter nguồn thực tế.
- Chưa dùng terminal/file write cho tới khi dedicated RBD pool/mount root đã chốt.

### P3 — RGW CRUD và capacity enforcement

- Thực hiện các hạng mục RGW/capacity như plan hiện tại: migration, reservation, exact-key PUT/overwrite, delete/versioning, CRUD stream, pause/resume.
- Phần này độc lập với việc RBD bỏ Linux SSH host.

### P4 — RBD create/map/ext4/mount qua SSH

- Thêm create/info/map/mount/unmount/unmap/delete API.
- Probe state trước/sau action; không retry mù sau timeout.
- Chỉ `mkfs.ext4` image vừa tạo và chưa có signature.
- Tích hợp reserved-logical capacity preflight trước create nếu guard đang enforce.

Điều kiện hoàn thành: create → map → ext4 → mount → write/read → unmount → remap → dữ liệu còn nguyên.

### P5 — File browser + preview qua SFTP

- List folder, upload, download, mkdir, delete.
- Preview text, ảnh và PDF inline; binary khác download.
- Stream file lớn; giới hạn preview size; chặn path escape/symlink escape.
- UI volume detail có file tree + preview pane.

Điều kiện hoàn thành: upload một ảnh vào ext4, unmount/remap/mount lại, vẫn list và preview đúng ảnh; SHA-256 file không đổi.

### P6 — Web terminal

- `xterm.js` + WebSocket + `ssh2.shell()`.
- Mở shell trên đúng Linux host; hiển thị host/mount context rõ trên UI.
- Đóng terminal chỉ đóng SSH shell, không tự unmount volume.

Điều kiện hoàn thành: chạy `ls`, `cat`, `dd` trong mountpoint từ browser và quan sát file xuất hiện ngay trong file browser.

### P7 — Tích hợp bài upgrade

- Chạy baseline trước upgrade: create/mount, upload text + ảnh + binary, lưu checksum.
- Trong/sau upgrade theo dõi RGW/RBD IOPS, throughput, latency và error.
- Sau upgrade: remap/mount, verify checksum, preview ảnh/text và thử ghi mới.
- Cleanup chỉ sau khi evidence đã lưu.

**Phần RBD SSH console riêng** dự kiến khoảng **2–3 ngày công** cho MVP create/map/mount + terminal + file browser/preview. Toàn bộ RGW + Capacity Guard + Performance Monitor vẫn là scope lớn hơn và có estimate riêng.

## 15. Test matrix bắt buộc

### 15.1. Capacity

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| C01 | Cluster average 60%, một participating OSD 69,5% | Mutation dự kiến vượt cap bị từ chối |
| C02 | OSD ngoài CRUSH scope >70% | Không chặn pool không liên quan |
| C03 | 32 worker thực hiện tổng 1.000 reservation attempt tại 67–68% | Tổng per-OSD charge không overbook; không có hai fencing generation cùng mutate một job |
| C04 | Telemetry stale/CLI timeout | PUT/update/RBD create bị block; read còn hoạt động khi cluster cho phép; cleanup chỉ chạy trong emergency metadata budget |
| C05 | OSDMap epoch đổi giữa reserve và execute | Hủy/recompute trước mutation; chuyển `PAUSED_REMAP/RECONCILING` |
| C06 | OSD down/reweight/backfill | Dừng cấp mới, tính lại scope; báo thiếu failure reserve nếu có |
| C07 | RGW và RBD cùng ghi | Dùng chung capacity ledger |
| C08 | DELETE thành công nhưng raw chưa giảm | Không credit/resume sớm |
| C09 | Controller restart có reservation active | Reconcile, không mất hoặc cộng trùng reservation |
| C10 | RGW và RBD dùng hai pool khác nhau nhưng chung OSD | FSID/per-OSD lock ngăn cross-pool overbook |
| C11 | Lease operation hết khi upload còn chạy | Vẫn charge `LEASE_EXPIRED_UNRECONCILED`; không auto-release |
| C12 | Reservation đã phản ánh vào observed usage | Không double-count vô hạn; settlement có evidence/audit |

### 15.2. RGW

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| G01 | List >1.000 object | Pagination đủ, không lặp/mất |
| G02 | Preview/range/download | Byte/checksum đúng |
| G03 | Overwrite exact key | GET sau đó trả bản mới; operation ghi UPDATE |
| G04 | Metadata self-copy | Metadata mới đúng; capacity accounting không coi miễn phí |
| G05 | Delete unversioned | Object biến mất; raw release chờ telemetry |
| G06 | Delete versioned không VersionId | Hiển thị delete marker, không báo hard-delete |
| G07 | Hard-delete đúng VersionId | Xóa đúng version/marker được chọn |
| G08 | Bulk delete partial failure | Trả kết quả từng key; retry idempotent |
| G09 | CRUD mix | Tỷ lệ gần cấu hình khi đủ mẫu |
| G10 | Auto-delete | Chỉ xóa object job-owned/prefix-owned |
| G11 | Bucket versioning `Suspended` | Current/null version và delete marker được catalog/reconcile đúng |
| G12 | Worker crash/restart | Catalog/job counters reconcile, fencing chặn worker cũ double mutation |
| G13 | Nhiều UPDATE trên bucket versioned | Giữ immutable row cho từng version; cleanup chỉ hard-delete version/marker job-owned |

### 15.3. RBD

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| R01 | SSH health + FSID | Kết nối đúng Linux host/cluster; không lộ credential |
| R02 | Tạo image 1 GiB | `rbd info` trả đúng size |
| R03 | Map + ext4 + mount | Có device và mountpoint đúng dưới `RBD_MOUNT_ROOT` |
| R04 | Upload text + ảnh qua file browser | File xuất hiện trong ext4; text/ảnh preview được |
| R05 | Ghi file qua terminal | File xuất hiện ngay trong file browser |
| R06 | Unmount + unmap | Device/mount biến mất, image vẫn còn |
| R07 | Re-map + mount image cũ | File và SHA-256 còn nguyên; ảnh vẫn preview đúng |
| R08 | Image có filesystem signature | Không tự `mkfs` lại |
| R09 | Mount busy | Unmount trả conflict; không lazy unmount mặc định |
| R10 | Path `..`/absolute/symlink escape | File API không thoát mount root |
| R11 | SSH rớt giữa action | Reconnect rồi probe observed state trước retry |
| R12 | Delete image | Chỉ xóa sau unmount/unmap; dependency thì báo lỗi |
| R13 | 3 image đồng thời | Mount path riêng, list/read/write không lẫn dữ liệu |
| R14 | Preview file lớn/binary | Không load toàn bộ vào RAM; unsupported type chuyển download |

### 15.4. Performance

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| P01 | Không có job console trong một cửa sổ hoàn chỉnh | `application` IOPS/throughput bằng 0; `ceph` vẫn có thể khác 0 do client/background khác |
| P02 | Console hoàn thành số request và payload biết trước trong 60 giây | `application` count/bytes khớp journal; rate khớp theo đúng window/step |
| P03 | RGW và RBD chạy đồng thời | Tách được series ứng dụng theo job/type; cluster series không bị cộng lặp ở API |
| P04 | OSD/mgr restart làm counter giảm | Sample đánh dấu reset/unknown; không có IOPS hoặc throughput âm/spike giả |
| P05 | Bỏ lỡ scrape hoặc endpoint timeout | Giữ last-known có age nhưng `fresh=false`; UI không vẽ thành 0 |
| P06 | Recovery/backfill chạy cùng client workload | UI có context/overlay và không gắn recovery traffic thành client throughput |
| P07 | Yêu cầu pool/image scope không có metric phù hợp | Trả `UNAVAILABLE` có lý do; không nội suy từ cluster/OSD total |
| P08 | So sánh API với counter delta gốc trong cùng timestamp/window | Read/write/total và bytes/s đúng công thức, unit và sai số làm tròn đã công bố |

### 15.5. Upgrade/fault

- RGW/RBD workload đang chạy khi recovery/backfill bắt đầu.
- Collector mất kết nối với MON/MGR.
- PostgreSQL restart.
- Backend restart.
- Worker restart giữa request.
- Node.js RBD service restart hoặc SSH rớt giữa map/format/mount và unmount/delete.
- Một OSD down; sau đó up lại.
- Metrics bị trễ hoặc timestamp lệch.
- Disk chứa PostgreSQL/RBD service log gần đầy.
- RGW GC backlog tăng.
- Capacity vượt ngưỡng bởi external writer.

Mỗi fault test phải ghi thời gian phát hiện, action bị chặn, operation đang bay, thời gian hội tụ và tài nguyên mồ côi còn lại.

## 16. Observability và audit

Metrics tối thiểu:

- Per operation count/error/latency/bytes và application request/s, byte/s, p50/p95/p99.
- Ceph client read/write/total IOPS và throughput byte/s theo cluster/OSD; pool/image chỉ khi source hỗ trợ đúng scope.
- Ceph read/write latency từ sum/count hoặc counter tương đương khi có; không gán percentile nếu nguồn chỉ cung cấp average.
- Source, scope, sample window, timestamp, freshness, reset/gap và collector error cho từng series.
- Recovery/backfill/client traffic tách riêng nếu metric có sẵn; physical device I/O nằm trong namespace/source riêng.
- RGW live object count/logical bytes.
- RBD logical size/actual allocation/reserved raw.
- OSD used ratio từng participating OSD và max.
- Capacity state, reason, snapshot age và OSDMap epoch.
- Active/lease-expired-unreconciled reservation và persistent commitment.
- Job state, lease owner, last heartbeat và paused reason.
- SSH/RBD command latency, timeout, reconnect và state-probe count.
- RGW GC/version backlog nếu thu thập được.

Mỗi mutation lưu:

- Request/action ID.
- Actor/job/volume.
- Intended state và observed state trước/sau.
- Capacity snapshot/decision binding.
- Result/error đã redact.

Không lưu secret, raw keyring hoặc payload người dùng vào log thông thường.

Giá trị IOPS/throughput phải được tính từ counter monotonic ở backend hoặc Prometheus query đã version hóa. Không lấy hai lần tốc độ, không cộng series trùng label, không dùng timestamp trình duyệt làm sample time. Dashboard mặc định hiển thị cửa sổ hoàn chỉnh 15 giây gần nhất và đánh dấu stale thay vì giữ số cũ như thể còn hiện tại.

## 17. Emergency stop và cleanup

### 17.1. Emergency stop

Console cần một control chuyển toàn hệ thống sang `READ_CLEANUP_ONLY`:

- Không admit PUT/update/RBD create/file-write mới; multipart/resize chưa thuộc MVP vẫn bị reject.
- Stop/pause producer jobs.
- Không retry/kill mù command đang chạy; sau timeout hoặc SSH disconnect phải probe observed state trước action tiếp theo.
- Giữ GET/HEAD/LIST nếu RGW còn phục vụ được. Chỉ chạy hard-delete/cleanup trong emergency maintenance budget; delete-marker creation không được coi là cleanup. Cho phép unmount/remove khi state và Ceph cho phép.
- Ghi action ID và lý do.

### 17.2. Cleanup cuối run

- Không còn job `running/pending/stopping` ngoài dự kiến.
- Không còn reservation hết lease chưa reconcile.
- `rbd device list` không còn mapping mồ côi.
- Mount table không còn mountpoint mồ côi.
- Image/volume còn lại được inventory và có owner rõ ràng.
- Không có multipart upload do MVP job tạo; nếu inventory thấy multipart bên ngoài thì chỉ báo cáo, không tự abort ngoài ownership evidence.
- Object/volume auto-delete chỉ nằm trong scope run.
- Capacity và cluster health đã hội tụ.

Cleanup không tự xóa volume/object không có ownership evidence.

## 18. Rollout và rollback

Rollout theo capability flag:

1. `capacity.observe_only=true`.
2. Bật `performance.enabled=true` ở observe-only, xác minh source/window/freshness.
3. Bật capacity enforcement cho upload hiện tại.
4. Bật manual RGW delete/update.
5. Bật RGW CRUD streaming.
6. Bật RBD SSH service read-only và xác minh FSID/capability.
7. Bật manual RBD create/map/ext4/mount.
8. Bật file browser/SFTP preview.
9. Bật web terminal SSH.

Rollback feature không được đồng nghĩa xóa dữ liệu:

- Disable job creation và pause producer.
- Unmount/unmap volume do console tạo nếu operator yêu cầu và observed state cho phép.
- Giữ image/object còn lại để điều tra; xóa là action riêng.
- Disable RBD Node.js service/SSH credential sau khi không còn mount/mapping nếu cần rollback.
- Không downgrade DB migration nếu chưa có procedure và backup đã thử.

## 19. Liên kết với kế hoạch upgrade OSD

Console này là workload generator, data browser và capacity controller hỗ trợ lab; nó không thay thế các gate upgrade.

Khi đưa vào tài liệu upgrade hiện tại, liên kết tại:

- Mục 3.2: workload RGW/RBD và dữ liệu canary.
- Mục 5: preflight/capacity evidence.
- Mục 8.4: metrics bắt buộc.
- Mục 8.5: threshold lab.
- Mục 9: test matrix và fault injection.
- Mục 12: đầu ra/biên bản run.

Không dùng câu “mọi OSD dưới 70%” để kết luận đủ headroom drain một OSD. Với topology chỉ 3 host × 1 OSD và `size=3`, cần thêm failure domain/spare hợp lệ trước bài yêu cầu phục hồi đủ replica. Nếu chạy upgrade ở mức fill cao, phải dùng `failure_reserve_mode=one_osd` hoặc `one_host` và chứng minh placement/recovery thực tế.

## 20. Chia PR/đầu việc đề xuất

1. **PR1 — Backend refactor + migrations + job lease**
2. **PR2 — Capacity collector observe-only + dashboard**
3. **PR2A — Performance collector + current/history/SSE + dashboard**
4. **PR3 — Capacity reservation/enforcement cho upload hiện tại**
5. **PR4 — RGW manual CRUD/version-aware delete**
6. **PR5 — RGW CRUD streaming + catalog**
7. **PR6 — RBD Node.js SSH service + health + image/device inventory**
8. **PR7 — RBD create/map/ext4/mount/unmount/delete**
9. **PR8 — RBD SFTP file browser + text/image/PDF preview**
10. **PR9 — Web terminal (`xterm.js` + `ssh2.shell`) + integrated upgrade tests**

Không có service Unix-socket/systemd riêng trên Linux host. RBD privileged operation được thực thi qua SSH, còn Windows chỉ chạy web service/browser.

## 21. Definition of Done

- [ ] Inventory P0 đã được lưu và review.
- [ ] Dedicated RGW/RBD lab scope được xác nhận.
- [ ] Migration chạy được từ schema console hiện tại.
- [ ] Existing feature không regression.
- [ ] Capacity collector khớp số liệu Ceph CLI.
- [ ] IOPS/throughput dashboard có source/scope/window/freshness rõ ràng; application series khớp journal và Ceph series được đối chiếu bằng counter delta cùng cửa sổ.
- [ ] Reset, missing sample và unsupported scope không tạo số 0/spike/per-pool estimate giả.
- [ ] Reservation/concurrency/stale-metrics tests đạt.
- [ ] RGW CRUD manual và streaming tests đạt.
- [ ] RBD create/map/ext4/mount/remount tests đạt; SSH reconnect không gây duplicate destructive action.
- [ ] File browser đọc được ext4 qua SFTP; text/ảnh/PDF preview được và checksum giữ nguyên sau unmount/remap.
- [ ] Application admission SLO, stable-epoch contract và giới hạn với recovery/backfill/external writer được ghi rõ trên UI/runbook.
- [ ] Không có secret trong log, response, screenshot hoặc tài liệu.
- [ ] Emergency stop và cleanup đã rehearsal.
- [ ] Có báo cáo lab; chưa chạy thì ghi `NOT_RUN`, không tự đánh dấu PASS.
- [ ] Plan upgrade chỉ tham chiếu kết quả đã kiểm chứng, không suy rộng từ unit test.

## 22. Nguồn kỹ thuật

- [Ceph Pacific — Block Device Quick Start](https://docs.ceph.com/en/pacific/start/quick-rbd/): create, map, ext4 và mount.
- [Ceph Pacific — RBD commands](https://docs.ceph.com/en/pacific/rbd/rados-rbd-cmds/): thin provisioning, remove và trash.
- [Ceph Pacific — RBD exclusive locks](https://docs.ceph.com/en/pacific/rbd/rbd-exclusive-locks/): exclusive lock và `--exclusive` map.
- [Ceph Pacific — Troubleshooting OSD fullness](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-osd/): per-OSD fullness, nearfull/backfillfull/full.
- [Ceph Pacific — Prometheus manager module](https://docs.ceph.com/en/pacific/mgr/prometheus/): endpoint metrics, metric/label semantics, scrape interval và RBD I/O statistics.
- [Ceph Pacific — Influx manager module counters](https://docs.ceph.com/en/pacific/mgr/influx/): ý nghĩa counter pool/OSD như client read/write operation, byte và latency.
- [Ceph Pacific — RGW S3 object operations](https://docs.ceph.com/en/pacific/radosgw/s3/objectops/): GET/HEAD/DELETE semantics.
- [Ceph Pacific — RGW bucket index/versioning](https://docs.ceph.com/en/pacific/dev/radosgw/bucket_index/): object version và delete marker/index behavior.
- [Ceph Pacific — RGW notifications](https://docs.ceph.com/en/pacific/radosgw/notifications/): lựa chọn mở rộng nếu sau này cần event từ client ngoài console.
- [`features/ceph-v2-qos-controller.md`](../features/ceph-v2-qos-controller.md): policy/gate/QoS controller của dự án.
- [`comparison/ceph-osd-upgrade-lab-production-plan(1)(1).md`](../comparison/ceph-osd-upgrade-lab-production-plan%281%29%281%29.md): topology, workload, metrics và gate upgrade hiện tại.



---

Tài liệu này là đặc tả phát triển. Các command, threshold và ước lượng phải được xác nhận lại từ inventory thực trước khi cho phép mutation lên cluster lab.

Baseline capability phải được đối chiếu trước hết với tài liệu/output Pacific 16.2.5. Tài liệu release mới hơn chỉ dùng tham khảo; adapter phải có capability matrix và test theo từng hop trước khi dùng hành vi mới.
