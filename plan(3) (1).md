# Production-grade plan — Ceph OSD Upgrade with Maintenance DR

**Ngày cập nhật:** 23/09/2026  
**Phạm vi:** Ceph Pacific `16.2.5 → 16.2.15`, cephadm, nâng từng OSD một.  
**Mục tiêu:** nâng OSD mà không tạo CRUSH rebalance diện rộng chỉ để phục vụ upgrade, không gây user-visible outage, giữ QoS trong SLO đã chốt, và vẫn có khả năng chịu thêm **một OSD failure** trong lúc OSD mục tiêu đang được nâng.

---

## 1. Mục tiêu production

Plan này có hai phương án:

1. **PA1 — Native Maintenance-DR bằng spare + upmap có kiểm soát**  
   Chỉ dùng cơ chế native Ceph. Giữ X online, chuyển đúng các PG của X sang spare S theo batch nhỏ, đợi đủ replica và QoS đạt rồi mới dừng/nâng X.

2. **PA2 — Maintenance Shadow Replica**  
   Phát triển thêm feature Ceph để tạo một temporary shadow replica `S*` cho đúng các PG thuộc X. Shadow được đồng bộ khi X vẫn online, có trạng thái sync/integrity riêng, sau đó được promote trước khi dừng X.

Hai phương án đều hướng tới trạng thái trước khi dừng X:

```text
Không được:

[X,Y,Z]
   X down
=> chỉ còn [Y,Z]
=> nếu Y/Z chết thêm một OSD thì chỉ còn 1 replica

Mục tiêu:

[S,Y,Z]
   X có thể dừng để upgrade

Nếu Y chết thêm:
[S,Z] = 2 replica
=> vẫn đáp ứng min_size=2
```

> Không hạ `min_size` chỉ để duy trì I/O trong maintenance. DR phải được tạo bằng replica hợp lệ, không bằng cách chấp nhận write với số bản sao thấp hơn mức an toàn đã chốt.

---

# 2. Điều kiện chung trước mọi phương án

## 2.1. Ký hiệu

| Ký hiệu | Ý nghĩa |
|---|---|
| `X` | OSD mục tiêu cần nâng |
| `S` | Spare OSD dùng cho Maintenance-DR |
| `S*` | Shadow replica trong PA2 |
| `Y/Z` | Các replica còn lại của PG |
| `P_X` | Toàn bộ PG có X trong `up` hoặc `acting` tại baseline |
| `B` | Batch PG đang được phép thay đổi |
| `C` | 1–2 PG canary sau nâng |
| `M0` | Baseline placement trước maintenance |

Ví dụ replicated pool:

```text
PG = [X,Y,Z]
size = 3
min_size = 2
```

## 2.2. Điều kiện bắt buộc

Trước khi bắt đầu:

- Cluster không có `inactive`, `undersized`, `degraded`, `inconsistent`, `unfound`.
- Không có recovery/backfill ngoài kế hoạch đang chạy.
- `ceph osd ok-to-stop X` phải đạt ngay trước khi dừng X.
- CRUSH rule, failure domain, pool `size/min_size`, device class và topology phải được inventory.
- X/S/Y/Z phải có đủ CPU, disk IOPS, network và capacity headroom.
- Balancer/autoscaler/topology phải được đóng băng hoặc kiểm soát trong maintenance window.
- Phải có baseline S3/RBD latency, throughput, IOPS, error rate và recovery load.
- Phải có independent manifest/checksum cho workload quan trọng.
- Mỗi thay đổi `primary-affinity`, CRUSH weight, upmap, flag phải được journal để rollback đúng ownership.
- Nếu xuất hiện thêm host/OSD failure ngoài threat model, dừng rollout và ưu tiên availability/durability.

## 2.3. QoS contract

Không dùng yêu cầu mơ hồ “QoS không đổi tuyệt đối”. Production phải chốt các ngưỡng:

```text
S3:
  p95/p99 PUT/GET <= SLO
  error rate <= SLO

RBD:
  p95/p99 read/write <= SLO
  IOPS/throughput >= floor

Infrastructure:
  disk util / latency <= threshold
  network <= threshold
  CPU <= threshold

Recovery:
  byte/batch <= budget
  no-progress timeout <= T
```

Nếu vượt budget:

1. Không cấp batch mới.
2. Giữ batch hiện tại hội tụ nếu vẫn an toàn.
3. Giảm concurrency/recovery rate theo scheduler/version đã test.
4. Nếu SLO vẫn vượt: rollback batch hoặc dừng maintenance.

---

# 3. PA1 — Native Maintenance-DR bằng spare + upmap

## 3.1. Mục tiêu

Giữ X online trong suốt quá trình tạo DR. Chỉ chuyển đúng các PG thuộc X sang S theo từng batch nhỏ bằng `pg-upmap-items`.

Trước khi dừng X:

```text
Ban đầu:
PG A = [X,Y,Z]

Sau migration:
PG A = [S,Y,Z]

X vẫn online nhưng không còn PG phục vụ.

Sau đó mới:
stop X
upgrade X
```

Nếu trong lúc X đang upgrade một peer khác chết:

```text
[S,Y,Z]
Y down
=> [S,Z]
=> còn 2 replica
```

Đây là phương án có thể triển khai bằng Ceph native mà không cần sửa code.

## 3.2. Nguyên tắc

- Không drain X bằng CRUSH weight `0`.
- Không add S full weight rồi để CRUSH tự chia PG.
- Không dùng `norebalance` như allowlist.
- `balancer off` chỉ tắt balancer; CRUSH vẫn hoạt động.
- S chỉ được nhận PG sau khi mapping toàn cụm đã được kiểm chứng.
- Batch nhỏ giới hạn **tải đồng thời**, không làm mất nhu cầu copy dữ liệu.
- Tổng dữ liệu phải copy có thể gần bằng một replica của toàn bộ dữ liệu trên X.

---

## 3.3. Phase A0 — Baseline và freeze placement

Lưu:

```bash
ceph -s
ceph health detail
ceph versions
ceph osd tree
ceph osd df tree
ceph osd dump
ceph osd pool ls detail
ceph pg dump pgs
ceph balancer status
ceph osd getmap
ceph osd getcrushmap
```

Xác định chính xác:

```text
P_X = tất cả PG có X trong up/acting
```

Tắt các tác nhân tự thay đổi placement trong window:

```bash
ceph balancer off
```

Autoscaler chỉ tắt trên các pool liên quan sau khi đã lưu mode cũ.

**Gate A0**

- Cluster sạch.
- M0 đã lưu.
- P_X đã inventory đầy đủ.
- QoS baseline hợp lệ.
- Không có automation ngoài phiên thay CRUSH/upmap/weight.

---

## 3.4. Phase A1 — Chuẩn bị spare S mà không tạo remap rộng

### Bước 1 — Park S

Ưu tiên provision S với initial CRUSH weight `0`.

Trạng thái mong muốn:

```text
S:
  up/in hoặc trạng thái provision đã kiểm soát
  CRUSH weight = 0
  PG = 0
```

Weight `0` chỉ dùng để **park** S. Chưa dùng S làm đích upmap.

### Bước 2 — Chuẩn bị weight dương rất nhỏ

Vì `pg-upmap-items` tới một OSD có effective weight bằng 0 có thể bị MON coi là mapping không hợp lệ, S phải có weight dương khi thật sự nhận PG.

Không tăng full weight.

Ví dụ lab:

```bash
SPARE_WEIGHT=0.0001
```

Đây không phải quota dung lượng. Nó chỉ giảm xác suất CRUSH tự chọn S.

### Bước 3 — Mô phỏng trước

Dùng OSDMap snapshot + `osdmaptool` để mô phỏng S với weight dương.

Phải so sánh **toàn bộ PG**, không chỉ PG trên S.

Nếu raw CRUSH map muốn đưa PG ngoài kế hoạch sang S:

```text
M0:      [U,Y,Z]
raw:     [S,Y,Z]

=> tạo pin/upmap giữ:
[S -> U]

effective:
[U,Y,Z]
```

Tập pin này gọi là `G`.

### Bước 4 — Start S chỉ sau khi placement đã pin

Điều kiện:

```text
S up/in
REWEIGHT = 1
CRUSH weight = small positive
S có 0 PG
Toàn cluster effective placement == M0
```

**Gate A1**

Không một PG nào ngoài kế hoạch được nằm trên S.

---

## 3.5. Phase A2 — Chuyển primary khỏi X

Chỉ thực hiện nếu baseline cho thấy cần giảm client workload trên X.

```bash
ceph osd primary-affinity "$X" 0
ceph osd primary-affinity "$S" 0
```

Đợi:

- X/S không còn primary trong phạm vi maintenance.
- Peer Y/Z vẫn trong SLO.
- Không có peering/recovery ngoài kế hoạch.

Primary-affinity không thay thế DR; X vẫn giữ replica cho tới lúc batch được chuyển.

---

## 3.6. Phase A3 — Chuyển PG X → S theo batch

Batch đầu:

```text
1 PG ít tải
```

Sau khi đo được impact:

```text
1–2 PG/batch hoặc theo byte budget
```

Ví dụ khi effective mapping là:

```text
[X,Y,Z]
```

thì:

```bash
ceph osd pg-upmap-items <PG_ID> "$X" "$S"
```

Nếu PG đang có pin `S -> X` từ phase chuẩn bị thì phải sửa **toàn bộ entry** đúng checkpoint; không mặc định append thêm `X -> S`.

### Gate trước mỗi batch

- Chỉ PG trong `A + B` được phép vào S.
- PG ngoài batch không đổi membership.
- Y/Z không đổi ngoài kế hoạch.
- X vẫn online.
- Không có host/OSD failure.
- QoS còn dưới threshold.

### Cho batch copy

Không giữ `norebalance` nếu chính flag đó chặn batch upmap khỏe mạnh.

Không bật:

```text
nobackfill
norecover
```

trong normal path.

Theo dõi đến khi từng PG:

```text
active+clean
up == acting
X không còn trong PG đã chuyển
S đã có replica hợp lệ
```

Sau đó mới cấp batch tiếp theo.

---

## 3.7. Phase A4 — DR READY trước khi upgrade

Chỉ được dừng X khi:

```text
count(PG có X trong up/acting) = 0

tất cả P_X:
  active+clean
  đủ replica
  không inconsistent
  không unfound

placement = [S,Y,Z]
```

Kiểm tra:

```bash
ceph osd ok-to-stop "$X"
```

**Gate DR-A**

```text
DR_READY = YES
```

khi toàn bộ PG của X đã ở `{S,Y,Z}` và QoS vẫn trong SLO.

---

## 3.8. Phase A5 — Upgrade X

Giữ:

```text
X in
CRUSH weight gốc
primary-affinity = 0
mapping vẫn giữ workload trên S
```

Dùng per-OSD `noout`:

```bash
ceph osd set-group noout "osd.${X}"
ceph osd ok-to-stop "$X"
ceph orch daemon stop "osd.${X}"
```

Nâng đúng daemon/store theo MOP `16.2.5 → 16.2.15`.

Không zap/recreate X trong normal upgrade.

X khởi động lại phải xác minh:

- image/digest/version đúng;
- BlueStore/BlueFS/RocksDB open/replay không lỗi;
- daemon stable;
- chưa nhận PG ngoài canary.

---

## 3.9. DR scenario trong lúc X đang nâng

Baseline maintenance:

```text
[S,Y,Z]
X offline
```

Nếu Y chết:

```text
[S,Z]
```

Nếu pool `min_size=2`, service vẫn có 2 replica.

Hành động:

1. Dừng rollout.
2. Không nâng OSD tiếp theo.
3. Ưu tiên restore Y hoặc X.
4. Không rollback placement chỉ để đạt KPI maintenance.
5. Chỉ resume khi PG trở lại đủ replica và SLO ổn định.

Nếu tiếp tục mất thêm một replica nữa thì phải theo DR cấp cluster/site, không còn là maintenance fault đơn.

---

## 3.10. Phase A6 — Canary trả X vào data path

Chọn:

```text
C = 1–2 PG ít critical
```

Khôi phục mapping của C từ S về X.

Đợi:

```text
active+clean
```

Kiểm:

- application checksum/H0;
- deep-scrub có mục tiêu;
- BlueStore errors;
- p95/p99;
- recovery load;
- primary test nếu cần.

Nếu canary PASS:

```text
trả batch tiếp theo
```

Nếu FAIL:

```text
giữ workload trên S/Y/Z
cô lập X
không nhận thêm PG
```

---

## 3.11. Ưu/nhược điểm PA1

### Ưu điểm

- Native Ceph.
- Có thể triển khai trước khi feature mới hoàn thiện.
- Có DR thật trước khi stop X.
- Không cần CRUSH drain toàn X một lần.
- Có thể giới hạn concurrent backfill theo batch.
- Có rollback theo từng PG.

### Nhược điểm

- Vẫn phải copy gần một replica của X.
- Upmap/journal phức tạp.
- Không có native allowlist tuyệt đối cho S.
- Topology change/OSD failure trong lúc chuẩn bị buộc phải reconcile mapping.
- Store cũ trên X có thể cleanup các PG đã chuyển; không bảo đảm chỉ cần delta khi trả PG về.

---

# 4. PA2 — Maintenance Shadow Replica

## 4.1. Mục tiêu

Phát triển feature Ceph để tạo temporary fourth copy **chỉ cho P_X**, không tăng pool `size=4` toàn cluster và không để CRUSH tự rebalance.

Normal:

```text
[X,Y,Z]
```

Maintenance preparation:

```text
[X,Y,Z] + S*
```

Trong đó:

```text
S* = shadow replica
```

Shadow không nằm trong normal acting set và không tham gia normal client ACK quorum.

Mục tiêu:

1. Bulk sync S* khi X/Y/Z vẫn khỏe.
2. Theo dõi chính xác shadow còn thiếu dữ liệu gì.
3. Khi shadow đã đồng bộ và integrity PASS, tạo maintenance barrier.
4. Promote S* thành normal replica **trước khi stop X**.
5. Sau đó mới nâng X.

Kết quả trước stop X:

```text
[S,Y,Z]
```

nhưng phần lớn dữ liệu của S đã được pre-stage từ trước, nên promotion không cần full backfill tại thời điểm maintenance.

---

## 4.2. Tại sao không cho S* vào normal ACK path ngay

Nếu client write phải chờ thêm S*:

```text
primary
  -> X
  -> Z
  -> S*
  -> ACK
```

p99 latency có nguy cơ tăng, trái mục tiêu QoS.

Do đó shadow path:

```text
normal commit:
primary -> normal replicas -> client ACK

shadow:
primary -> S* asynchronously
```

Nhưng vì S* không nằm trong ACK quorum nên phải có **sync state + barrier** trước khi được phép promote.

---

## 4.3. Metadata mới

Không sửa CRUSH thành “replication 3.5”.

Đề xuất thêm OSDMap/monitor metadata riêng:

```text
maintenance_shadow:
  pgid:
    source_set
    shadow_osd
    state
    target_version
    shadow_last_update
    shadow_last_complete
    missing_objects
    missing_bytes
    barrier_version
    integrity_state
```

CLI conceptual:

```bash
ceph osd maintenance-shadow add <pgid> <shadow_osd>
ceph osd maintenance-shadow status <pgid>
ceph osd maintenance-shadow promote <pgid>
ceph osd maintenance-shadow remove <pgid>
```

Cấp OSD:

```bash
ceph osd maintenance-shadow status-osd <X>
```

---

## 4.4. State machine

```text
EMPTY
  |
  v
BASE_SYNC
  |
  v
CATCHING_UP
  |
  v
READY
  |
  v
PROMOTABLE
  |
  v
PROMOTED
```

Lỗi:

```text
STALE
FAILED
INTEGRITY_FAILED
```

### Điều kiện READY

Ví dụ:

```text
authoritative_version = 845'19328

shadow_last_update    = 845'19328
shadow_last_complete  = 845'19328
missing_objects       = 0
missing_bytes         = 0
```

Không đánh giá chỉ bằng:

```text
8 TB / 10 TB
```

mà đánh giá bằng PG version/log + missing set.

---

## 4.5. Shadow progress

Per-PG status:

```text
PG                     2.a
shadow                 osd.40

authoritative_version  845'19328
shadow_last_update     845'19328
shadow_last_complete   845'19328

version_lag            0
missing_objects        0
missing_bytes          0 B

state                  READY
```

Nếu lag:

```text
authoritative_version  845'19328
shadow_last_complete   845'19280

version_lag            48
state                  CATCHING_UP
```

Controller không được cho maintenance nếu bất kỳ PG nào chưa READY.

---

## 4.6. Integrity gate

Sync complete không đồng nghĩa chắc chắn byte vật lý không corruption.

Cần hai gate:

### Sync gate

```text
last_update == target
last_complete == target
missing_set == empty
```

### Integrity gate

Tối thiểu:

- BlueStore checksum không lỗi;
- application manifest/H0 nếu có;
- targeted deep verification/scrub cho PG theo policy;
- không `inconsistent`.

Chỉ:

```text
SYNC_PASS
AND
INTEGRITY_PASS
```

mới cho `PROMOTABLE`.

---

## 4.7. Maintenance barrier

Client vẫn ghi liên tục nên `READY` ở một thời điểm chưa đủ.

Tạo barrier:

```text
V_barrier = authoritative version tại thời điểm chuẩn bị promote
```

Chờ:

```text
S*.last_update    >= V_barrier
S*.last_complete  >= V_barrier
missing = 0
integrity = PASS
```

Trong lúc đó shadow vẫn nhận write mới.

Trước promotion thực hiện final fence rất ngắn:

```text
1. Freeze membership transition.
2. Capture V_final.
3. Wait S* complete >= V_final.
4. Verify lag = 0.
5. Promote S* into normal acting membership.
6. Verify PG active+clean as [S,Y,Z].
7. Only then allow stop X.
```

Bulk copy đã thực hiện trước đó. Final fence chỉ xử lý delta cuối và state transition.

---

## 4.8. DR READY gate của PA2

Cấp OSD:

```text
X=osd.10
P_X total       120

PROMOTED/READY  120
CATCHING_UP       0
STALE             0
FAILED            0

max_lag           0
missing_bytes      0
integrity_fail     0
```

Sau final promotion:

```text
count(PG có X trong active membership) = 0
count(PG đã thay X bằng S) = |P_X|
```

Khi đó:

```text
DR_READY = YES
```

và mới được chạy:

```bash
ceph osd ok-to-stop "$X"
```

---

## 4.9. Write path đề xuất

### Trước barrier

```text
Client
  |
  v
Primary
  |----> normal replicas (commit quorum)
  |
  `----> S* async shadow stream
```

S* không quyết định client ACK.

### Khi shadow lag vượt threshold

```text
shadow_lag > L
```

controller:

```text
PAUSE new maintenance preparation
```

Không stop X.

Nếu lag kéo dài:

```text
abort maintenance
remove/rebuild shadow state theo runbook
```

---

## 4.10. Upgrade X

Sau khi mọi PG đã được promote thành:

```text
[S,Y,Z]
```

dừng X:

```bash
ceph osd ok-to-stop "$X"
ceph osd set-group noout "osd.${X}"
ceph orch daemon stop "osd.${X}"
```

Upgrade same store.

Nếu Y/Z chết thêm một OSD:

```text
[S,Z] hoặc [S,Y]
```

vẫn còn 2 replica.

Không nâng OSD khác cho tới khi failure được xử lý.

---

## 4.11. Canary X sau nâng

Sau khi X chạy version mới:

```text
1–2 PG:
[S,Y,Z]
  ->
[X,Y,Z]
```

Nhưng chỉ sau:

- X version/digest đúng;
- BlueStore open/replay PASS;
- H0/integrity PASS;
- QoS PASS.

Nếu canary fail:

```text
[S,Y,Z] giữ nguyên
X bị cô lập
không mở rộng
```

Nếu PASS:

```text
return PG theo batch
```

Cuối cùng shadow metadata được remove.

---

## 4.12. Các vùng code dự kiến phải phát triển

Đây là định hướng thiết kế, phải xác nhận bằng source review trước khi coding.

### Control plane

- OSDMap: metadata maintenance shadow.
- OSDMonitor: validate/add/remove/promote shadow mapping.
- MON command/CLI: `maintenance-shadow add/status/promote/remove`.
- Persistence/encoding compatibility cho mixed `16.2.5/16.2.15` nếu feature đi vào hop đang mixed-version.

### PG/OSD data plane

- Peering/PG state: nhận biết shadow peer.
- Recovery/backfill path hoặc một shadow-sync path riêng để seed S*.
- Continuous PG log/update forwarding tới S*.
- Track `last_update`, `last_complete`, missing set của shadow.
- Promotion path từ shadow → normal replica mà không full-copy lại.

### Safety

- Shadow không được tự thành primary.
- Shadow không được dùng làm recovery source trước `PROMOTABLE`.
- Promotion phải validate epoch/interval/history.
- Mất shadow không được làm normal PG unavailable.
- Failure của normal replica trong lúc shadow chưa READY phải ưu tiên native recovery, không giữ maintenance objective bằng mọi giá.

### Observability

Per-PG metrics:

```text
shadow_state
version_lag
missing_objects
missing_bytes
sync_rate
shadow_write_latency
barrier_version
integrity_state
```

Per-OSD summary:

```text
total_shadow_pgs
ready
catching_up
stale
failed
max_lag
total_missing_bytes
DR_READY
```

---

# 5. Failure matrix

| Tình huống | PA1 | PA2 |
|---|---|---|
| X upgrade bình thường | `[S,Y,Z]` giữ service | `[S,Y,Z]` sau shadow promotion |
| Y chết khi X offline | `[S,Z]`, còn 2 replica | `[S,Z]`, còn 2 replica |
| S chết trước khi X stop | Không stop X; rebuild DR | Không stop X; shadow FAILED |
| S chết khi X đang upgrade | Dừng rollout, ưu tiên đưa X về hoặc recovery | Dừng rollout, ưu tiên X/recovery |
| QoS tăng lúc pre-copy | Pause batch | Throttle/pause shadow sync |
| PG ngoài scope remap | Stop rollout, reconcile map | Không promote; investigate |
| Integrity S fail | Không dùng S cho DR | Shadow `INTEGRITY_FAILED` |
| X không boot sau upgrade | Workload vẫn trên S/Y/Z | Workload vẫn trên S/Y/Z |
| Peer thứ hai chết | Maintenance-DR chịu được 1 peer failure | Maintenance-DR chịu được 1 peer failure |
| Host/site failure ngoài thiết kế | Chuyển sang DR cấp cluster/site | Chuyển sang DR cấp cluster/site |

---

# 6. Điều kiện chọn production

## 6.1. PA1 được coi là production-ready khi

Lab phải chứng minh lặp lại:

1. S được đưa vào nhưng không có PG ngoài allowlist.
2. Batch X→S không làm PG ngoài phạm vi đổi membership.
3. QoS không vượt SLO ở batch size đã chọn.
4. Tất cả P_X chuyển sang `{S,Y,Z}` và trở lại `active+clean`.
5. Trong trạng thái X offline, mô phỏng/chaos thêm một OSD peer failure vẫn duy trì I/O theo `min_size`.
6. Upgrade X thành công.
7. Canary X PASS.
8. Rollback một batch đã được diễn tập.
9. Topology/OSD failure giữa maintenance được detect và rollout dừng đúng.
10. Tổng thời gian và tổng byte copy nằm trong maintenance budget.

## 6.2. PA2 được coi là production-ready khi

Ngoài các test của PA1, phải chứng minh:

1. Shadow không nằm trong normal ACK path.
2. Shadow sync không phá SLO.
3. `last_update/last_complete/missing` phản ánh chính xác tiến độ.
4. Barrier không cho false `DR_READY`.
5. Shadow lag/stale được detect.
6. Promotion không full-copy lại dữ liệu đã seed.
7. Promotion tạo normal replica hợp lệ qua peering.
8. Shadow không bao giờ được dùng làm primary/source khi chưa được cấp quyền.
9. Double-failure test sau promotion vẫn giữ I/O.
10. Mixed-version behavior và encoding của feature an toàn hoặc feature chỉ được bật khi tất cả daemon prerequisite đã lên version hỗ trợ.
11. Restart MON/MGR/OSD không làm mất shadow state.
12. Abort/remove shadow không làm ảnh hưởng normal placement.

---

# 7. So sánh hai phương án

| Tiêu chí | PA1 Native Maintenance-DR | PA2 Maintenance Shadow Replica |
|---|---|---|
| Cần sửa Ceph | Không | Có |
| Production sớm | Cao hơn | Sau development + soak test |
| Kiểm soát PG | Upmap + journal | Feature riêng |
| Bulk data copy | Có | Có, nhưng pre-stage |
| Copy tại thời điểm stop X | Đã hoàn tất trước đó | Gần như chỉ final delta/promotion |
| Client ACK impact | Không đổi replication ACK path | Shadow không nằm ACK path |
| DR thêm 1 OSD failure | Có sau khi P_X chuyển xong | Có sau khi shadow promote |
| Complexity vận hành | Cao | Complexity chuyển vào code/controller |
| Dependency vào upmap | Cao | Thấp hơn sau khi feature hoàn thiện |
| Rủi ro mapping drift | Phải reconcile | Controller/OSDMap feature enforce |
| Giá trị R&D | Trung bình | Cao |

---

# 8. Quyết định triển khai đề xuất

## Giai đoạn 1 — Production candidate bằng native Ceph

Dùng **PA1**:

```text
prepare S
  ->
pin placement
  ->
X online
  ->
move PG X→S theo batch
  ->
active+clean + QoS gate
  ->
DR_READY
  ->
stop/upgrade X
  ->
canary X
  ->
return batches
```

Đây là phương án thực tế để lab ngay và có thể đưa production nếu toàn bộ gate đạt.

## Giai đoạn 2 — Phát triển feature

Phát triển **PA2 Maintenance Shadow Replica**:

```text
[X,Y,Z]
  +
S* shadow

sync + integrity
  ->
barrier
  ->
promote S
  ->
[S,Y,Z]
  ->
upgrade X
```

Mục tiêu PA2 không phải “không copy dữ liệu”, mà là:

- pre-stage copy khi cluster còn đầy đủ;
- kiểm soát chính xác trạng thái DR;
- không cần một tập upmap lớn làm hàng rào production;
- giảm thao tác placement thủ công;
- tạo enforcement rõ ràng trước khi `ok-to-stop X`.

---

# 9. Kết luận

Nếu cần một phương án triển khai trước:

> **PA1 là production candidate gần nhất:** dùng native Ceph, chuyển P_X sang S theo batch có QoS gate, chỉ dừng X sau khi `{S,Y,Z}` đã đủ replica.

Nếu project cho phép sửa Ceph:

> **PA2 là hướng production dài hạn tốt hơn:** tạo `Maintenance Shadow Replica`, theo dõi bằng PG version/missing set, dùng sync + integrity gate + maintenance barrier, promote S trước khi dừng X, rồi mới upgrade.

Điểm chung bắt buộc của cả hai:

```text
Không stop X khi chỉ còn [Y,Z] mà chưa có DR replica S hợp lệ.
```

Trước maintenance thật sự phải đạt:

```text
[S,Y,Z] active+clean
```

hoặc trạng thái feature tương đương đã được promote/verify.

---

# 10. Nguồn kỹ thuật đang dùng làm baseline

Tài liệu PA1 hiện tại đã đối chiếu các cơ chế sau trên Pacific `16.2.5`/`16.2.15`:

- Ceph Pacific — `pg-upmap`.
- `OSDMap::check_pg_upmaps()`, `_apply_upmap()`, `clean_pg_upmaps()`.
- `OSDMonitor` validation/cleanup của upmap.
- `PrimaryLogPG` và hành vi `NOREBALANCE`.
- `osdmaptool`.
- CRUSH Maps / weight / weight-set.
- OSD initial CRUSH weight.
- Health checks.

Đối với PA2, các nội dung shadow replica, barrier, promotion và enforcement là **đề xuất feature mới**; phải source-review, thiết kế protocol/state encoding, coding và test fault-injection trước khi gọi production-ready.
