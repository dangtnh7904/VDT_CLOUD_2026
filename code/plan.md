# Kế hoạch phát triển RGW/RBD Storage Lab Console

**Dự án:** PRJ GD2 — công cụ tạo tải và quản lý dữ liệu thử nghiệm cho Ceph RGW/RBD  
**Ngày lập:** 21/09/2026  
**Trạng thái:** đặc tả để phát triển; chưa phải bằng chứng đã triển khai hoặc chạy thành công trên lab  
**Code hiện có:** [`code/rgw-console`](./rgw-console/)  
**Tài liệu upgrade liên quan:** [`comparison/ceph-osd-upgrade-lab-production-plan(1)(1).md`](../comparison/ceph-osd-upgrade-lab-production-plan%281%29%281%29.md)

## 1. Mục tiêu

Mở rộng console RGW hiện có thành một **Storage Lab Console** có ba nhóm chức năng dùng chung một cơ chế kiểm soát dung lượng:

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

Đây là công cụ **lab-only, quyền cao**. Không triển khai hệ thống login/RBAC trong MVP. Tuy nhiên, vẫn phải giới hạn pool, bucket, image prefix và mount root để một lỗi phần mềm không format hoặc xóa nhầm tài nguyên ngoài phạm vi bài thử.

## 2. Kết quả cần đạt

MVP được coi là hoàn thành khi đáp ứng đồng thời các điều kiện sau:

- Có thể duyệt, xem, download, overwrite và xóa object trong các bucket lab được cấu hình.
- Có thể chạy một RGW CRUD job dài hạn với tỷ lệ thao tác cấu hình được và có pause/resume/stop.
- Có thể tạo một RBD image mới, map exclusive, format ext4, mount, ghi/đọc kiểm tra, unmount, unmap và xóa image từ console.
- Mỗi volume có trạng thái, device, mount path và lịch sử thao tác riêng.
- RGW và RBD dùng chung một Capacity Guard và một sổ reservation, không tự tính dung lượng riêng rẽ.
- Khi telemetry thiếu/cũ hoặc dự báo thao tác kế tiếp có thể vượt trần, thao tác tăng dung lượng bị chặn. `GET`, `HEAD`, `LIST`, hard-delete exact version/unversioned cleanup, `unmount` và `remove` được ưu tiên nhưng vẫn phải chừa maintenance metadata budget và tuân theo khả năng thực tế của cluster.
- Worker/agent restart không làm lặp `rbd create`, format lại filesystem, map trùng hoặc xóa nhầm volume.
- Dashboard hiển thị được OSD đầy nhất, participating OSD, reservation, trạng thái guard và nguyên nhân job bị pause.
- Không có secret/keyring/access key bị ghi vào operation log, API response hoặc tài liệu.

## 3. Phạm vi MVP và ngoài phạm vi

### 3.1. Trong phạm vi

- Mọi pool RGW/RBD mà mutation chạm tới trong MVP phải là replicated pool; cấu hình mẫu hiện tại là `size=3`, `min_size=2`. Nếu phát hiện bất kỳ affected pool nào là EC, Capacity Guard phải fail closed cho mutation cho tới khi có phép tính EC riêng.
- Ceph Pacific 16.2.5 là baseline đầu tiên; code không được giả định chỉ chạy trên output của Reef.
- RGW S3 API và RGW Admin Ops/radosgw-admin cho tài nguyên lab.
- RBD format 2, kernel RBD (`krbd`) và filesystem ext4.
- Một host agent quản lý map/mount RBD.
- Một RBD image chỉ có một client RW tại một thời điểm.
- Bucket/versioning được phát hiện và hiển thị rõ.
- Streaming workload do chính console tạo.
- PostgreSQL là state store và journal của console.
- SSE cho telemetry và trạng thái job theo thời gian gần thực.

### 3.2. Ngoài phạm vi MVP

- Dùng công cụ trên bucket, pool hoặc image production không có allowlist.
- EC pool cho bất kỳ data/index/metadata path RGW hoặc RBD nào mà console sẽ mutation; phép tính `k+m`, chunk/alignment và overwrite của EC để giai đoạn sau.
- RBD snapshot, clone, flatten, mirroring, live migration và multi-writer filesystem.
- RBD resize và force-purge snapshot/clone trong MVP.
- RGW multipart workload trong MVP; nếu endpoint multipart được thêm sau này thì phải reserve toàn expected size và cleanup part trước khi bật.
- Mount một ext4 image RW đồng thời trên nhiều host.
- Arbitrary shell/root terminal từ browser.
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
- Chưa có RBD state machine và reconciler.
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

### 5.1. Không chạy lệnh RBD trong FastAPI container

Tạo một tiến trình riêng tên tạm là `ceph-host-agent`, chạy bằng systemd trên một Ceph client host. Agent có:

- Quyền root trên host lab.
- `ceph-common`, `rbd`, `e2fsprogs`, `util-linux` và kernel module RBD.
- `/etc/ceph/ceph.conf` và keyring lab.
- Quyền đọc `/dev`, map RBD và mount filesystem.
- Mount root cố định, ví dụ `/srv/ceph-lab/rbd`.

Backend giao tiếp với agent qua Unix domain socket bind-mounted vào backend container, ví dụ:

```text
/run/rgw-console/ceph-agent.sock
```

Không publish agent bằng TCP ra mạng. Agent không nhận arbitrary command; mỗi request phải là một action đã định nghĩa với trường dữ liệu đã validate.

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
- RBD create ở chế độ reserved-logical.
- RBD resize tăng nếu được bổ sung sau MVP; hiện tại không expose API resize.
- RBD/file workload ghi dữ liệu mới.

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

Image phải bật/verify feature `exclusive-lock` và được map bằng `rbd device map --exclusive`. Tùy chọn này tắt cooperative lock transition nhưng không bảo đảm syscall map của một external client luôn thất bại ngay. Agent phải kiểm tra mapping cục bộ và `rbd status`/watcher, từ chối mapping thứ hai do console quản lý, và acceptance test phải chứng minh writer thứ hai không acquire/write được. Contract không bao phủ client ngoài controller.

Nếu cần multi-node RW trong tương lai, phải dùng clustered filesystem hoặc thiết kế khác; không dùng ext4.

## 6. Kiến trúc mục tiêu

```text
Browser
  │
  ▼
React UI ─────────────────────────────────────────────────────────┐
  │                                                               │ SSE
  ▼                                                               │
FastAPI API                                                       │
  ├── RGW router ─── boto3/Admin adapter ─── Ceph RGW             │
  ├── RBD router ─── Unix socket ─── ceph-host-agent ─── RBD/ext4 │
  ├── Capacity API ────────────────────────┐                       │
  ├── Job API                              │                       │
  └── Metrics/Event API                    │                       │
          │                                │                       │
          ▼                                ▼                       │
      PostgreSQL ◄── CRUD worker     Capacity collector ── Ceph CLI
```

### 6.1. Thành phần backend đề xuất

Tách `main.py` thành các module nhỏ; tên dưới đây là đề xuất, có thể điều chỉnh nhưng trách nhiệm phải được giữ riêng:

```text
backend/app/
  api/
    health.py
    rgw.py
    jobs.py
    capacity.py
    rbd.py
  services/
    rgw_service.py
    capacity_guard.py
    capacity_collector.py
    reservation_service.py
    rbd_agent_client.py
    job_service.py
  workers/
    rgw_crud_worker.py
    rbd_lifecycle_worker.py
  models/
    api.py
    domain.py
  migrations/
  main.py
```

### 6.2. Thành phần host agent đề xuất

```text
rgw-console/agent/
  app.py
  protocol.py
  ceph_cli.py
  rbd.py
  filesystem.py
  reconciler.py
  config.py
  systemd/rgw-console-agent.service
```

Yêu cầu thực thi lệnh:

- Dùng argv list, không dùng `shell=True`.
- Có timeout cho mọi lệnh.
- Lưu exit code/stdout/stderr đã redact và giới hạn kích thước.
- Validate cluster, pool, namespace, image, device và mountpoint trước/sau action.
- Không dùng path do client truyền trực tiếp làm device hoặc mount path.
- Mỗi action có idempotency key.
- Trước retry sau timeout, đọc observed state; timeout không đồng nghĩa command chưa chạy.

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

### 9.1. Pool và naming

- Dùng pool lab riêng, tên mặc định đề xuất `rbd-lab`.
- Chạy `rbd pool init` trong bước provisioning, không chạy lặp ở mỗi request.
- Image do console tạo dùng prefix cố định, ví dụ `lab-<uuid>`.
- Display name người dùng nhập được lưu trong metadata/DB, không dùng trực tiếp làm shell/device path.
- Namespace RBD nếu dùng phải nằm trong allowlist.

### 9.2. State machine

```text
REQUESTED → CAPACITY_RESERVED → CREATED
CREATED → MAPPING → MAPPED
MAPPED (new, no signature) → FORMATTED → MOUNTING → MOUNTED → READY
MAPPED (known FS UUID) → MOUNTING → MOUNTED → READY
READY → UNMOUNTING → UNMOUNTED
UNMOUNTED → MOUNTING → MOUNTED → READY
UNMOUNTED → UNMAPPING → UNMAPPED
UNMAPPED → MAPPING → MAPPED
CREATED hoặc UNMAPPED → DELETING → DELETED
```

Trạng thái lỗi bổ sung:

- `BLOCKED_CAPACITY`
- `BLOCKED_CLUSTER_HEALTH`
- `MAP_FAILED`
- `FORMAT_FAILED`
- `MOUNT_FAILED`
- `BUSY`
- `DELETE_BLOCKED_DEPENDENCY`
- `RECONCILING`
- `UNKNOWN`

Lưu riêng `desired_state` và `observed_state`; bảng valid-action theo state phải từ chối transition không hợp lệ. Không nhảy trạng thái chỉ vì command trả timeout. Agent phải quan sát image/device/mount thực tế rồi mới quyết định retry hoặc chuyển lỗi.

### 9.3. Create flow

1. Validate request, allowlist, logical size và capacity mode.
2. Collector phải có telemetry mới, FSID/OSDMap epoch đúng và pool tồn tại.
3. Tạo capacity reservation.
4. Tạo RBD image format 2 với feature tương thích kernel của host.
5. Đọc lại `rbd info` và lưu immutable image ID.
6. Verify feature `exclusive-lock`, kiểm tra watcher/mapping và map bằng `rbd device map ... --exclusive`.
7. Chờ udev và đọc `rbd device list --format=json` để lấy device thực.
8. Giữ per-volume lock; ngay trước format, đối chiếu pool/namespace/image ID bằng `rbd device list`, sysfs và major:minor; xác nhận device không mount và không có holder ngoài dự kiến.
9. Chạy `wipefs -n` và `blkid`; chỉ format nếu đây là image do request hiện tại vừa tạo, identity còn khớp và hoàn toàn chưa có signature. Chạy `mkfs.ext4 -m 0` trên block device mới; không dùng `-F` để vượt guard.
10. Tạo mountpoint từ volume UUID bên dưới mount root cố định.
11. Mount RW; lưu FS UUID, device, mountpoint và mount options.
12. Gán quyền lab trong filesystem, ví dụ root directory mode `0777` nếu yêu cầu quyền cao nhất.
13. Ghi probe file, `fsync`, đọc lại rồi xóa probe để xác nhận path hoạt động.
14. Chuyển volume sang `READY`.

Không tự format một image đã tồn tại trước request hoặc image có filesystem signature/identity không khớp state DB. Bất kỳ race, reuse device number hoặc mismatch major:minor nào cũng chuyển `RECONCILING`, không retry format.

### 9.4. Access flow

Hai cách truy cập:

1. **Trực tiếp trên host lab**
   - UI hiển thị mount path.
   - Người dùng SSH vào host và thao tác trong đúng mountpoint.
   - Chỉ được gọi là `RESERVED_LOGICAL` controlled mode khi volume đã reserve toàn logical size; vẫn không quảng bá physical invariant nếu placement/recovery thay đổi.

2. **File browser qua console**
   - Agent cung cấp list/upload/download/delete/mkdir trong mountpoint.
   - Backend proxy stream qua Unix socket.
   - Không dùng mô hình check-then-open bằng path string. Trên Linux hỗ trợ, dùng dirfd + `openat2(RESOLVE_BENEATH|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS)`; fallback chỉ dùng `openat` từng component với `O_NOFOLLOW` đã review/test. Nếu kernel không cung cấp primitive an toàn thì disable file browser và chỉ cho direct host access.
   - Không cho symlink hoặc race đổi path thoát khỏi volume root.
   - Không cung cấp arbitrary command execution.

API đề xuất:

```text
GET    /api/rbd/pools
GET    /api/rbd/volumes
POST   /api/rbd/volumes
GET    /api/rbd/volumes/{volume_id}
POST   /api/rbd/volumes/{volume_id}/mount
POST   /api/rbd/volumes/{volume_id}/unmount
DELETE /api/rbd/volumes/{volume_id}
GET    /api/rbd/actions/{action_id}

GET    /api/rbd/volumes/{volume_id}/files?path=...
PUT    /api/rbd/volumes/{volume_id}/files?path=...
GET    /api/rbd/volumes/{volume_id}/files/content?path=...
DELETE /api/rbd/volumes/{volume_id}/files?path=...
POST   /api/rbd/volumes/{volume_id}/directories
```

Mọi mutation RBD nhận `Idempotency-Key`, trả `202 Accepted` cùng `action_id`, `desired_state` và URL status; không giữ HTTP request mở suốt `mkfs`/mount/delete. List API có cursor/limit. Create request bắt buộc có pool, logical size, capacity mode, `filesystem=ext4`, auto-mount và optional display name; response không coi volume `READY` cho tới khi action status hoàn tất.

### 9.5. Delete flow

1. Khóa volume và ngừng job/file operation mới.
2. Xác minh image ID, device và mountpoint đúng với DB.
3. Nếu mount busy, trả `409 BUSY`; không dùng lazy unmount làm mặc định.
4. `sync` và unmount thật.
5. Xác nhận device không còn mount.
6. Unmap đúng device đã xác minh.
7. Kiểm tra snapshot/clone/dependency.
8. Delete trả conflict nếu còn dependency; MVP không force-purge snapshot hoặc clone.
9. Dùng `rbd rm` cho hard delete. `rbd trash mv` không được coi là đã trả capacity.
10. Đánh dấu `DELETED`, nhưng capacity chỉ được credit sau khi OSD telemetry xác nhận.
11. Không tự xóa mount directory nếu nó còn file hoặc không resolve đúng mount root.

### 9.6. RBD lifecycle streaming

Job type `rbd_lifecycle` có thể hỗ trợ sau khi manual flow ổn định:

```json
{
  "job_type": "rbd_lifecycle",
  "pool": "rbd-lab",
  "logical_size_min_mib": 1024,
  "logical_size_max_mib": 4096,
  "capacity_mode": "reserved-logical",
  "max_live_volumes": 4,
  "filesystem": "ext4",
  "write_bytes_per_volume": 268435456,
  "dwell_seconds": 60,
  "auto_delete": true,
  "duration_seconds": 3600
}
```

Mỗi vòng:

1. Capacity preflight và reserve.
2. Create/map/format/mount.
3. Ghi dữ liệu pattern/corpus, `fsync`, đọc lại và checksum.
4. Giữ volume trong dwell period.
5. Unmount/unmap/delete.
6. Đợi telemetry hội tụ trước khi dùng lại capacity budget.

Auto-delete chỉ áp dụng volume do chính job tạo.

## 10. Database và migration

### 10.1. Migration framework

Thêm Alembic hoặc một migration runner có version rõ ràng. Không tiếp tục chỉ dựa vào một chuỗi `CREATE TABLE IF NOT EXISTS` vì cần thay CHECK constraint và schema qua nhiều phiên bản.

Tạo one-shot service/command `migrate` chạy trước backend và worker. Nó phải fingerprint schema legacy, stamp revision ban đầu sau khi xác minh, rồi apply migration trong transaction phù hợp. Backend/worker/agent đợi migration hoàn tất và không chạy runtime DDL. Backup PostgreSQL trước migration lab có dữ liệu cần giữ; không cho hai process bootstrap schema đồng thời.

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

## 11. API capacity và response contract

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
| 423 | `RECONCILING` | Agent/controller đang reconcile |
| 503 | `TELEMETRY_STALE` | Không có capacity evidence đủ mới |
| 503 | `CEPH_UNAVAILABLE` | Không truy cập được Ceph/RGW |

Response lỗi phải có `request_id`, stable error code, message, retryable và observed state; không trả command string chứa secret.

### 11.3. Control plane và agent

Các control bắt buộc:

```text
GET  /api/control/state
POST /api/control/emergency-stop
POST /api/control/resume

GET  /api/agent/health
POST /api/agent/reconcile
GET  /api/agent/reconcile/{action_id}

GET  /api/capacity/decisions/{decision_id}
```

- Emergency stop/resume là persistent desired state trong DB, có `Idempotency-Key`, action ID, reason và audit; không chỉ là biến trong RAM.
- Resume chỉ được chấp nhận khi telemetry/freshness/hysteresis/reconcile gates đạt; không có endpoint “force resume bỏ qua guard” trong MVP.
- Agent health trả identity/FSID/version/capability, không trả keyring/secret.
- Reconcile là async action, có fencing và status endpoint; retry phải dùng cùng idempotency key.

## 12. Frontend

### 12.1. Navigation mới

```text
Live dashboard
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

Volume detail gồm file browser, event timeline và nút mount/unmount/delete. Destructive action vẫn cần modal xác nhận tên volume; đây là guard chống thao tác nhầm, không phải RBAC.

## 13. Cấu hình

Không ghi giá trị secret vào file plan. Các biến dự kiến:

Backend/worker env:

```text
CEPH_EXPECTED_FSID
CEPH_CLUSTER_NAME
CEPH_AGENT_SOCKET

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
```

Host-agent-only env/file config:

```text
CEPH_EXPECTED_FSID
CEPH_CLUSTER_NAME
CEPH_CONF_PATH
CEPH_KEYRING_PATH
CEPH_CLIENT_ID
CEPH_AGENT_SOCKET_PATH
RBD_MOUNT_ROOT
RBD_ALLOWED_POOLS
RBD_ALLOWED_NAMESPACES
RBD_IMAGE_PREFIX
```

MVP có thể dùng CephX `client.admin` cho Ceph CLI/RBD host agent vì yêu cầu lab quyền cao. RGW không dùng CephX key này; RGW dùng access/secret của một RGW system/admin identity riêng. Production hóa sau này phải thay bằng caps tối thiểu; việc đó không nằm trong MVP này.

## 14. Kế hoạch triển khai theo pha

### P0 — Inventory chỉ đọc

Việc cần làm:

- Xác nhận FSID, version daemon/client và actual topology.
- Xác nhận số OSD, host/failure domain, device class và dung lượng từng OSD.
- Inventory CRUSH rule, replicated size/min_size và pool application.
- Inventory RGW zone/placement/data/index pools.
- Inventory đầy đủ RGW metadata, log/control và mọi pool mà placement/storage class/bucket index chạm tới; ghi rõ pool nào chỉ phục vụ control path.
- Inventory `rgw_enable_ops_log`, usage logging, notification log và RGW GC settings/backlog có thể làm read/delete phát sinh hoặc giữ thêm dữ liệu.
- Xác nhận bucket versioning và scope của access key hiện tại.
- Xác nhận endpoint thực tế là direct RGW hay VIP.
- Inventory kernel version, krbd feature support và package trên host agent.
- Chốt dedicated `rbd-lab` pool, RGW bucket/prefix lab và mount root.

Lệnh đọc tham khảo:

```bash
ceph -s --format=json
ceph fsid
ceph versions --format=json
ceph osd df --format=json
ceph osd tree --format=json
ceph osd pool ls detail --format=json
ceph osd crush rule dump --format=json
rbd device list --format=json
radosgw-admin zone get | jq '{id,name,placement_pools}'
```

Không lưu raw output của `radosgw-admin zone get`: output có thể chứa `system_key.access_key/secret_key`. Nếu schema/version không khớp filter `jq`, dừng và viết filter/redaction mới trước khi lưu inventory.

Điều kiện hoàn thành:

- Có inventory lưu lại, không thay cluster.
- Xác định được participating OSD cho **mọi** affected RGW/RBD data/index/metadata/log/control pool; nếu còn pool/path UNKNOWN thì P0 chưa PASS.
- Không còn trường cấu hình bắt buộc ở trạng thái UNKNOWN.

### P1 — Refactor, migration và test harness

Việc cần làm:

- Tách router/service khỏi `main.py`.
- Thêm migration framework.
- Thêm one-shot `migrate` service; backend/worker phụ thuộc migration hoàn tất và bỏ runtime DDL.
- Migrate `operations` và `stream_jobs` không mất dữ liệu hiện có.
- Thêm job lease/heartbeat/fencing generation.
- Thêm `idempotency_requests`, atomic claim/fingerprint/result replay cho mọi RGW/RBD mutation.
- Thêm central scope validator và enforce RGW bucket/prefix allowlist trên mọi endpoint hiện có trước khi bật thêm mutation; host agent enforce pool/namespace/image/mount allowlist độc lập với backend.
- Tạo host agent skeleton read-only, Unix socket, health/capability/FSID check và systemd unit; chưa bật action RBD mutation.
- Tạo unit tests cho config, DB và state transitions.

Điều kiện hoàn thành:

- Backend khởi động với DB cũ và DB mới.
- Existing upload/list/preview/stream PUT vẫn hoạt động.
- Hai worker không chạy đồng thời cùng job.
- Read/write/list ngoài allowlist bị từ chối ở backend; request trực tiếp tới agent ngoài allowlist cũng bị từ chối.

### P1A — Provisioning tài nguyên lab có kiểm soát

Việc cần làm:

- Tạo/duyệt RGW bucket/prefix lab và identity RGW admin riêng.
- Tạo `rbd-lab` replicated pool đúng CRUSH rule/failure domain và chạy `rbd pool init` một lần, hoặc ghi nhận pool đã tồn tại đúng cấu hình.
- Cài package/kernel capability cần thiết trên host agent.
- Ghi mọi mutation provisioning và đối chiếu lại inventory.

Điều kiện hoàn thành:

- Không chạm pool/bucket production ngoài change đã duyệt.
- Agent expected FSID khớp cluster.
- Affected pools đều replicated; phát hiện EC phải HOLD MVP.

### P2 — Capacity observe-only

Việc cần làm:

- Viết collector/adapter parse JSON cho Pacific.
- Chạy collector qua read-only host agent từ P1, không cài Ceph CLI/quyền root vào FastAPI container.
- Lưu snapshot và per-OSD samples.
- Xác định pool → CRUSH rule → OSD scope.
- Expose REST/SSE và dashboard.
- Chạy ở `observe_only=true`, chưa chặn operation.

Điều kiện hoàn thành:

- So sánh kết quả UI với `ceph osd df` thủ công khớp.
- Metrics stale/CLI error được báo UNKNOWN, không biến thành 0%.
- OSD ngoài scope không xuất hiện trong max của pool đó.

### P3 — Capacity enforcement và reservation

Việc cần làm:

- Thêm admission algorithm, transaction/advisory lock và reservation lease.
- Chèn guard vào mọi upload path và worker PUT hiện có.
- Thêm throttle/pause/resume hysteresis.
- Thử concurrent requests sát ngưỡng bằng fake collector trước khi chạy lab.

Điều kiện hoàn thành:

- Không overbook trong concurrency test.
- OSDMap epoch đổi làm pause/reconcile.
- Existing GET/HEAD/LIST không bị chặn nhầm; cleanup classification và emergency metadata budget có unit/integration test. Manual DELETE được kiểm sau P4.

### P4 — RGW manual CRUD

Việc cần làm:

- Exact-key PUT/overwrite.
- Metadata update.
- Single/bulk delete.
- Version listing và version-aware delete.
- Operation journal và UI action.
- Enforce bucket allowlist trên mọi read/write/list/job endpoint, không chỉ delete.

Điều kiện hoàn thành:

- Unversioned và versioned cases đúng semantics.
- List hơn 1.000 object không mất/nhân bản record qua pagination.
- Preview/range/download checksum đúng.
- Delete ngoài bucket allowlist bị từ chối.

### P5 — RGW CRUD streaming

Việc cần làm:

- `stream_objects` catalog.
- Weighted operation selector.
- PUT/GET/HEAD/LIST/UPDATE/DELETE counters.
- Capacity override và auto-drain job-owned objects.
- Resume/reconcile sau worker restart.

Điều kiện hoàn thành:

- Với ít nhất 10.000 operation thành công và mỗi weight >0 có ít nhất 100 mẫu, tỷ lệ từng operation nằm trong ±3 điểm phần trăm so với cấu hình; nếu selector phải fallback vì inventory không đủ thì báo riêng và không tính cửa đó là PASS.
- Job không xóa object ngoài catalog/prefix của nó.
- Khi guard pause, không còn mutation tăng dung lượng mới được admit.

### P6 — Mở rộng host agent cho manual RBD lifecycle

Việc cần làm:

- Mở capability RBD đặc quyền trên Unix socket/systemd skeleton đã chạy read-only từ P1.
- Ceph/RBD CLI wrapper.
- State machine, idempotency và reconciler.
- Create/map/format/mount/file access/unmount/unmap/delete.
- RBD UI và audit timeline.

Điều kiện hoàn thành:

- Round-trip create → write/checksum → delete đạt.
- Restart backend/agent ở từng state không gây duplicate/destructive retry.
- Second console mapping bị từ chối và second writer không acquire/write được; không đòi hỏi external map syscall luôn fail ngay.
- Image có signature không rõ nguồn không bị format.

### P7 — RBD lifecycle streaming

Việc cần làm:

- `rbd_lifecycle` job.
- Reserved-logical capacity flow.
- Pattern/corpus write và verify.
- Auto-delete chỉ với volume job-owned.
- Theo dõi actual allocated/reserved/logical riêng biệt.

Điều kiện hoàn thành:

- Chạy ít nhất 50 vòng create/use/delete liên tiếp; sau reconcile, chênh lệch image/device/mount/reservation so với baseline bằng 0.
- Job dừng cấp mutation trước admission stop; nếu recovery/external write vẫn làm physical usage vượt 70%, ghi breach đúng thay vì tuyên bố invariant.
- Delete không làm resume sớm trước telemetry.

### P8 — Tích hợp bài upgrade và đóng gói

Việc cần làm:

- Chạy RGW + RBD đồng thời trong lab.
- Thử collector/guard khi PG remap, recovery/backfill và OSD down.
- Ghi baseline/latency/error/capacity theo run.
- Viết runbook cài agent, cấu hình console, emergency stop và cleanup.
- Liên kết kết quả vào plan upgrade; không tự đánh dấu PASS nếu chưa chạy.

Điều kiện hoàn thành:

- Có báo cáo test và known limitations.
- Không dùng cap 70% thay cho kiểm tra failure headroom/spare của bài upgrade.
- Có cleanup checklist chứng minh không còn job, mount, mapped image và reservation mồ côi.

Ước lượng ban đầu cho một kỹ sư khi lab luôn sẵn sàng: khoảng **13–17 ngày công**. Sau P0 phải ước lượng lại theo topology, versioning, kernel và cách cấp RGW admin access thực tế.

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
| R01 | Tạo image thin 10 GiB, size=3 | Logical 10 GiB; reservation raw phản ánh replica + overhead |
| R02 | Image không fit dưới admission stop | Reject trước khi giao volume cho writer |
| R03 | Create/map/format/mount/write/remount | Checksum đúng, state đúng |
| R04 | Second console mapping và external second writer | Console mapping bị từ chối; external writer không acquire/write được dù map syscall có thể thành công |
| R05 | Agent restart ở từng state | Không duplicate map/mount/format |
| R06 | Delete khi mount busy | Trả conflict; không lazy unmount/rm |
| R07 | Snapshot/clone dependency | Normal delete bị chặn và báo dependency |
| R08 | Image có filesystem signature ngoài DB | Không format tự động |
| R09 | Path `..`, absolute path, symlink escape | Không thoát volume root |
| R10 | Auto lifecycle nhiều vòng | Không rò image/device/mount/reservation |
| R11 | Xóa file trong ext4 rồi trim | Xác minh discard được hỗ trợ và `notrim` không bật; ghi telemetry quan sát được nhưng không yêu cầu exact raw decrease và không credit trước fresh OSD evidence |
| R12 | OSDMap đổi khi volume active | Không tạo volume mới; existing reserved volume được reconcile |

### 15.4. Upgrade/fault

- RGW/RBD workload đang chạy khi recovery/backfill bắt đầu.
- Collector mất kết nối với MON/MGR.
- PostgreSQL restart.
- Backend restart.
- Worker restart giữa request.
- Host agent restart giữa map/format/mount và unmount/delete.
- Một OSD down; sau đó up lại.
- Metrics bị trễ hoặc timestamp lệch.
- Disk chứa PostgreSQL/agent log gần đầy.
- RGW GC backlog tăng.
- Capacity vượt ngưỡng bởi external writer.

Mỗi fault test phải ghi thời gian phát hiện, action bị chặn, operation đang bay, thời gian hội tụ và tài nguyên mồ côi còn lại.

## 16. Observability và audit

Metrics tối thiểu:

- Per operation count/error/latency/bytes.
- RGW live object count/logical bytes.
- RBD logical size/actual allocation/reserved raw.
- OSD used ratio từng participating OSD và max.
- Capacity state, reason, snapshot age và OSDMap epoch.
- Active/lease-expired-unreconciled reservation và persistent commitment.
- Job state, lease owner, last heartbeat và paused reason.
- Agent command/action latency, timeout và reconcile count.
- RGW GC/version backlog nếu thu thập được.

Mỗi mutation lưu:

- Request/action ID.
- Actor/job/volume.
- Intended state và observed state trước/sau.
- Capacity snapshot/decision binding.
- Result/error đã redact.

Không lưu secret, raw keyring hoặc payload người dùng vào log thông thường.

## 17. Emergency stop và cleanup

### 17.1. Emergency stop

Console cần một control chuyển toàn hệ thống sang `READ_CLEANUP_ONLY`:

- Không admit PUT/update/RBD create/file-write mới; multipart/resize chưa thuộc MVP vẫn bị reject.
- Stop/pause producer jobs.
- Không kill mù command đang chạy; agent reconcile sau timeout.
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
2. Bật capacity enforcement cho upload hiện tại.
3. Bật manual RGW delete/update.
4. Bật RGW CRUD streaming.
5. Nâng host agent read-only đã cài từ P1 lên capability RBD inventory/mutation theo từng flag.
6. Bật manual RBD create/map/format/mount.
7. Bật RBD file access.
8. Bật RBD lifecycle streaming.

Rollback feature không được đồng nghĩa xóa dữ liệu:

- Disable job creation và pause producer.
- Unmount/unmap volume do agent quản lý nếu operator yêu cầu và state cho phép.
- Giữ image/object còn lại để điều tra; xóa là action riêng.
- Disable agent socket/service sau khi không còn mount/mapping.
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
2. **PR2 — Read-only host agent + capacity collector observe-only + dashboard**
3. **PR3 — Capacity reservation/enforcement cho upload hiện tại**
4. **PR4 — RGW manual CRUD/version-aware delete**
5. **PR5 — RGW CRUD streaming + catalog**
6. **PR6 — Mở capability RBD trên host agent + inventory/reconcile**
7. **PR7 — RBD create/map/ext4/mount/delete**
8. **PR8 — RBD file browser + lifecycle streaming**
9. **PR9 — Integrated fault tests, runbook và upgrade-plan references**

Mỗi PR phải giữ console build/chạy được và có migration/test tương ứng. Không gộp capacity enforcement, privileged agent và UI RBD vào một thay đổi duy nhất khó rollback.

## 21. Definition of Done

- [ ] Inventory P0 đã được lưu và review.
- [ ] Dedicated RGW/RBD lab scope được xác nhận.
- [ ] Migration chạy được từ schema console hiện tại.
- [ ] Existing feature không regression.
- [ ] Capacity collector khớp số liệu Ceph CLI.
- [ ] Reservation/concurrency/stale-metrics tests đạt.
- [ ] RGW CRUD manual và streaming tests đạt.
- [ ] RBD lifecycle và restart/reconcile tests đạt.
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
- [Ceph Pacific — RGW S3 object operations](https://docs.ceph.com/en/pacific/radosgw/s3/objectops/): GET/HEAD/DELETE semantics.
- [Ceph Pacific — RGW bucket index/versioning](https://docs.ceph.com/en/pacific/dev/radosgw/bucket_index/): object version và delete marker/index behavior.
- [Ceph Pacific — RGW notifications](https://docs.ceph.com/en/pacific/radosgw/notifications/): lựa chọn mở rộng nếu sau này cần event từ client ngoài console.
- [`features/ceph-v2-qos-controller.md`](../features/ceph-v2-qos-controller.md): policy/gate/QoS controller của dự án.
- [`comparison/ceph-osd-upgrade-lab-production-plan(1)(1).md`](../comparison/ceph-osd-upgrade-lab-production-plan%281%29%281%29.md): topology, workload, metrics và gate upgrade hiện tại.

---

Tài liệu này là đặc tả phát triển. Các command, threshold và ước lượng phải được xác nhận lại từ inventory thực trước khi cho phép mutation lên cluster lab.

Baseline capability phải được đối chiếu trước hết với tài liệu/output Pacific 16.2.5. Tài liệu release mới hơn chỉ dùng tham khảo; adapter phải có capability matrix và test theo từng hop trước khi dùng hành vi mới.
