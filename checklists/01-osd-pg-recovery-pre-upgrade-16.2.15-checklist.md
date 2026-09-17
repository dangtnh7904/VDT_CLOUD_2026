# Checklist bổ sung trước khi nâng cấp Ceph OSD từ 16.2.5 lên 16.2.15

> **Phạm vi:** checklist này được suy ra từ `01-osd-pg-recovery(1).md` và `01-osd-pg-recovery(1).csv`, sau đó đối chiếu thêm với tài liệu Ceph Pacific về v16.2.15 và cephadm upgrade.
>
> **Mục tiêu:** biến các finding code-level về OSD/PG/peering/recovery/backfill/scrub/replication/EC thành các bước **As-Is check → blocker → canary/mixed-version test → rollout gate → rollback/fix-forward**.
>
> **Không phải GO/NO-GO toàn cluster:** owner `01-osd-pg-recovery` chỉ bao phủ một phần của Ceph. Các thay đổi thuộc MON/OSDMap/CRUSH, BlueStore/BlueFS, config/default, cephadm/MGR, RGW/RBD... vẫn phải ghép với checklist của các owner tương ứng trước khi ra quyết định cuối cùng.

---

## 1. Kết luận cần thay đổi trong checklist hiện tại

Checklist trước upgrade **không nên chỉ dừng ở** `ceph -s`, số OSD up/in và `HEALTH_OK`.

Từ diff `16.2.5 → 16.2.15`, cần bổ sung tối thiểu 6 lớp kiểm tra:

1. **As-Is inventory theo điều kiện kích hoạt code mới**: EC/min_size, stretch mode, scrub backlog, PGLog dups, recovery/backfill config, WPQ/mClock, store legacy/SNAPMAPPER2, RBD caps, object manifest/tiering.
2. **Hard gate trước từng canary OSD**: PG khỏe, không có unfound/incomplete, không recovery/backfill ngoài kế hoạch, `ceph osd ok-to-stop <id>` phải pass.
3. **Mixed-version validation có chủ đích đổi primary**: vì nhiều hành vi mới nằm ở primary; chỉ để một OSD target chạy rồi thấy `HEALTH_OK` là chưa đủ.
4. **Test restart trong lúc recovery/scrub/backfill**: đây là nơi nhiều fix 16.2.15 được kích hoạt.
5. **Baseline và guardrail QoS**: p95/p99 client latency, recovery throughput, OSD apply/commit latency, CPU/RAM/network/disk headroom.
6. **Rollback phải tách thành `stop rollout`, `service recovery`, và `binary downgrade`**. Không được coi downgrade package/image là rollback mặc định nếu chưa có lab test round-trip.

---

## 2. Vì sao hai file này làm checklist phải thay đổi

CSV có **45 file** trong owner này:

- `A = 2`, `M = 42`, `R = 1`;
- tổng khoảng `+2,980 / -865` dòng;
- `P0 = 36`, `P1 = 1`, `P2 = 8`;
- 36 file runtime/source được đánh dấu đọc sâu.

`P0/P1/P2` trong nguồn là **thứ tự đọc**, không phải mức rủi ro. Vì vậy checklist không được dùng trực tiếp `P0 = blocker`.

Các finding upgrade-relevant chính:

| Finding | Hành vi thay đổi | Ý nghĩa cho checklist |
|---|---|---|
| `OSD-001` | EC async recovery không làm acting xuống dưới `min_size` | Nếu có EC: phải inventory `size/min_size` và fault-test degraded recovery |
| `OSD-002` | EC hinfo lỗi chuyển từ assert sang failed-pull/inconsistent/unfound | Nếu có EC: phải kiểm tra inconsistency/unfound trước upgrade và test hinfo trong lab |
| `OSD-003` | PGLog `dups` có guard/trim mới | Phải kiểm tra PGLog/RocksDB headroom; OSD đang có DB/log phình là conditional blocker |
| `OSD-004` | Scrub FSM/remap/reservation được sửa | Phải kiểm tra scrub backlog/stuck và test scrub khi remap/primary failover |
| `OSD-005` | Partial recovery clean regions được persist qua restart | Phải test restart giữa recovery, nhất là object lớn |
| `OSD-006` | Peering/backfill sửa candidate/accounting sau interruption | Phải test backfill bị interrupt + primary failover; stretch cluster cần test riêng |
| `OSD-007` | Persist `cluster_osdmap_trim_lower_bound` | Phải test restart/map-gap; downgrade về writer cũ chưa được coi là an toàn nếu chưa thử |
| `OSD-008` | OMAP range-delete/EC getattr semantics đúng hơn | Workload OMAP/EC cần recovery + scrub validation |
| `OSD-010` | Sửa legacy SnapMapper conversion | Store thiếu `SNAPMAPPER2` cần clone-test; target không tự chữa key đã hỏng lịch sử |
| `OSD-011` | mClock có init benchmark/persist capacity | Nếu mClock bật: phải inventory config và test startup/QoS; WPQ default ít liên quan |
| `OSD-012` | Lifecycle/start-stop/map delivery fail-safe hơn | Lỗi nền có thể lộ ra khi restart; phải thu log và có stop condition rõ |
| `OSD-013` | `rbd-read-only` được `metadata_list` đúng scope | Nếu dùng RBD read-only caps: phải test primary base và target |
| `OSD-014` | Manifest/tiering phục hồi adjacent clone trước refcount | Nếu dùng cache-tier/dedup/set_chunk + snapshot: phải test riêng |

---

# 3. Checklist PRE-UPGRADE cần bổ sung

## 3.1. Gate A — Xác nhận đúng phạm vi và version

- [ ] Xác nhận source version thực tế của toàn cluster: `16.2.5`.
- [ ] Xác nhận target image/package đúng `16.2.15`.
- [ ] Lưu image digest/tag target để tránh target thay đổi giữa rollout.
- [ ] Xác nhận từng daemon đang chạy version nào, không chỉ package trên host.
- [ ] Xác nhận tất cả host online trước khi bắt đầu.
- [ ] Xác nhận MGR standby sẵn sàng nếu dùng cephadm upgrade.
- [ ] Đọc release note `16.2.15` và ghi lại các thay đổi có liên quan tới cluster.
- [ ] Không ra GO/NO-GO toàn cluster chỉ từ report owner `01`; phải ghép các report owner còn lại.

### Evidence cần lưu

```bash
ceph -s
ceph versions
ceph orch ps
ceph orch upgrade status
```

> `ceph orch upgrade status` có thể chưa có upgrade active; mục đích là kiểm tra orchestrator state trước cửa sổ thay đổi.

---

## 3.2. Gate B — Health/PG state trước upgrade

### Hard gate đề xuất

- [ ] Không có PG `inactive`, `incomplete`, `stale`, `down`, `unknown`.
- [ ] Không có object `unfound` chưa xử lý.
- [ ] Không có OSD down ngoài kế hoạch.
- [ ] Không có peering loop/stuck peering chưa giải thích được.
- [ ] Không có recovery/backfill đang chạy ngoài kế hoạch canary.
- [ ] Không có scrub/repair đang stuck hoặc repair đang chạy mà chưa hiểu trạng thái.
- [ ] Không có `backfill_toofull` / capacity pressure chưa xử lý.
- [ ] Mọi cảnh báo `HEALTH_WARN` phải được phân loại: **known/accepted** hoặc **blocker**; không bỏ qua chỉ vì cluster vẫn phục vụ I/O.

### Evidence cần lưu

```bash
ceph -s
ceph health detail
ceph pg stat
ceph osd stat
ceph osd tree
ceph osd df tree
ceph osd perf
```

### Stop condition

Nếu xuất hiện một trạng thái mới như `incomplete`, `unfound`, OSD crash/assert, scrub stuck hoặc peering không hội tụ sau canary thì **dừng rollout** và điều tra trước khi nâng OSD tiếp theo.

---

## 3.3. Gate C — Inventory pool/PG theo finding `OSD-001/002/005/008`

### Bắt buộc inventory

- [ ] Liệt kê pool replicated và EC.
- [ ] Với mỗi pool ghi `size`, `min_size`, `pg_num`, `pgp_num`.
- [ ] Với EC: ghi EC profile/k/m và failure domain.
- [ ] Xác định có override recovery/backfill/async recovery nào khác default hay không.
- [ ] Xác định có workload OMAP-heavy không.
- [ ] Xác định có large-object workload dễ rơi vào partial recovery không.

### Nếu **không có EC pool**

- `OSD-001`, `OSD-002` và phần EC của `OSD-008` được đánh dấu **N/A** cho Production.
- Vẫn giữ replicated recovery/backfill/scrub tests.

### Conditional blocker

Nếu cluster có EC và đang tồn tại degraded/inconsistent/unfound hoặc chưa biết `min_size` thực tế thì **không canary trước khi làm rõ**.

---

## 3.4. Gate D — Scrub/deep-scrub state theo `OSD-004`

- [ ] Kiểm tra có PG nào scrub/deep-scrub bị overdue/stuck không.
- [ ] Kiểm tra `noscrub`, `nodeep-scrub` hoặc flag liên quan đang bật vì lý do gì.
- [ ] Ghi thời điểm scrub/deep-scrub gần nhất cho PG nằm trên OSD canary.
- [ ] Không chạy `repair` hàng loạt như một bước “chuẩn bị upgrade”.
- [ ] Nếu có inconsistency, xác định authoritative copy trước khi repair.
- [ ] Không bật/tắt flag một cách tự động chỉ để làm dashboard xanh.

### Blocker

- Scrub FSM đã stuck trước upgrade nhưng chưa có nguyên nhân.
- Có `inconsistent` nhưng chưa xác định source/replica đúng.
- Đang có repair có khả năng mutate data/metadata trên PG canary.

---

## 3.5. Gate E — PGLog/RocksDB theo `OSD-003`

- [ ] Kiểm tra OSD canary có dấu hiệu RocksDB/PGLog bất thường: DB lớn, startup chậm, compaction/tombstone pressure, log cảnh báo dups.
- [ ] Đảm bảo filesystem/DB/WAL có headroom đủ trước restart.
- [ ] Nếu có PGLog `dups` lớn, lập runbook riêng; **không** coi upgrade tự động chữa OSD đã không boot.
- [ ] `ceph-objectstore-tool --op trim-pg-log-dups` chỉ được thử trên clone/OSD dừng theo runbook; không đưa thành pre-upgrade command mặc định.

### Blocker

- OSD canary đang không boot ổn định vì DB/PGLog.
- Không đủ local free space để restart/compaction an toàn.
- Có kế hoạch chạy offline PGLog mutation nhưng chưa có clone/backup và chưa test reopen store.

---

## 3.6. Gate F — Peering/backfill/stretch theo `OSD-006/007`

- [ ] Xác định cluster có dùng stretch mode hay không.
- [ ] Nếu có stretch: test riêng acting selection và failover; không suy từ replicated cluster thường.
- [ ] Kiểm tra recovery/backfill capacity guard và `backfill_toofull` history.
- [ ] Ghi OSD/PG đang làm primary trước canary.
- [ ] Chọn canary có phạm vi ảnh hưởng thấp, nhưng **vẫn phải test đổi primary có chủ đích**.
- [ ] Sau restart, xác nhận peering hội tụ và không có map-gap/past-interval warning mới.

### Per-OSD hard gate

```bash
ceph osd ok-to-stop <OSD_ID>
```

Nếu command không kết luận được hoặc trả failure thì OSD đó **không được nâng trong lượt hiện tại**.

> `ok-to-stop` kiểm tra immediate data availability; nó không chứng minh QoS sẽ không giảm và cũng không thay thế kiểm tra headroom của các replica còn lại.

---

## 3.7. Gate G — Scheduler WPQ/mClock theo `OSD-011`

- [ ] Ghi `osd_op_queue` hiện tại.
- [ ] Nếu WPQ: đánh dấu nhánh mClock benchmark là N/A cho production test chính, nhưng vẫn đo QoS restart/recovery.
- [ ] Nếu mClock: inventory capacity override/historical IOPS/force-run/skip behavior.
- [ ] Không force benchmark đồng loạt trong cửa sổ upgrade nếu chưa đo tác động.
- [ ] Ghi baseline p95/p99 client latency và recovery throughput trước canary.

### Conditional blocker

mClock đang bật nhưng operator không biết capacity được lấy từ config nào hoặc startup benchmark có chạy hay không.

---

## 3.8. Gate H — Legacy store/SnapMapper theo `OSD-010`

- [ ] Kiểm tra lịch sử OSD/store: có OSD rất cũ được mang qua nhiều major release không.
- [ ] Xác định store có thiếu feature `SNAPMAPPER2` hay không nếu lịch sử cho thấy có khả năng.
- [ ] Nếu thiếu: clone store và test conversion bằng 16.2.15 trước Production.
- [ ] So sánh key count/cardinality/suffix trước-sau trên clone.

### Blocker

Không mở trực tiếp bản store duy nhất bằng target nếu chưa biết nó sẽ chạy legacy conversion.

> Fix 16.2.15 chỉ làm conversion **đúng về sau**; nó không chứng minh tự sửa mapping đã bị conversion cũ làm hỏng.

---

## 3.9. Gate I — RBD caps theo `OSD-013`

Nếu dùng RBD:

- [ ] Inventory auth entities có `profile rbd-read-only` hoặc `profile rbd`.
- [ ] Chọn ít nhất một image test đại diện.
- [ ] Test open/read/list metadata khi primary ở OSD 16.2.5.
- [ ] Test lại khi primary ở OSD 16.2.15.
- [ ] Xác nhận target cho đúng `metadata_list` nhưng không mở rộng method/object ngoài scope.

### Blocker

RBD read-only là luồng production quan trọng nhưng chưa có test mixed-primary.

---

## 3.10. Gate J — Object manifest/tiering theo `OSD-014`

- [ ] Xác định có dùng cache tier, dedup/chunk manifest, `set_chunk`, snapshot clone hay không.
- [ ] Nếu không dùng: đánh dấu `OSD-014 = N/A`.
- [ ] Nếu có: dựng fixture lab với adjacent clone unreadable/degraded và test recovery/refcount.

### Blocker

Có workload manifest/tiering production nhưng chưa biết có snapshot/degraded clone path hay không và chưa có lab test.

---

# 4. Những gì cần sửa trong runbook nâng cấp

## 4.1. Sửa tiêu chí “cluster healthy”

### Không đủ

```text
HEALTH_OK => upgrade được
```

### Nên đổi thành

```text
Cluster health acceptable
AND không có PG state blocker
AND không có unfound/inconsistent chưa xử lý
AND canary OSD pass ok-to-stop
AND headroom/QoS trong guardrail
AND các feature-specific checks đã PASS hoặc N/A
```

---

## 4.2. Sửa canary từ “upgrade một OSD rồi chờ” thành “mixed-primary canary”

Một canary hoàn chỉnh cần ít nhất các phase:

1. Chụp baseline.
2. Chọn OSD canary.
3. `ok-to-stop` pass.
4. Upgrade/restart OSD canary lên 16.2.15.
5. Xác nhận daemon join cluster/peering clean.
6. Chạy client I/O khi canary là **replica**.
7. Cho một tập PG test có canary làm **primary**.
8. Chạy read/write + scrub/recovery/backfill scenario phù hợp.
9. Đổi primary lại sang OSD 16.2.5 và lặp I/O.
10. Đưa primary sang 16.2.15 và lặp lại.
11. Restart canary thêm một lần sau khi đã phát sinh PGLog/map/recovery state.
12. Chỉ PASS nếu health, correctness và QoS đều nằm trong guardrail.

**Lý do:** nhiều behavior trong source được quyết định bởi version của primary; nếu chỉ test canary ở vai trò replica thì bỏ sót mixed-version risk.

---

## 4.3. Sửa rollout thành từng gate nhỏ

Đề xuất:

```text
Baseline
  -> 1 OSD canary
  -> observe + mixed-primary tests
  -> nhóm nhỏ OSD cùng failure-domain policy
  -> observe
  -> tiếp tục staggered rollout
```

Không tăng batch khi:

- PG chưa về trạng thái chấp nhận được;
- latency vượt guardrail;
- recovery/backfill chưa hội tụ;
- có crash/assert mới;
- có inconsistency/unfound mới;
- chưa hiểu warning mới xuất hiện.

> Ceph Pacific cephadm có staggered upgrade parameters từ 16.2.11. Vì source đang ở 16.2.5, phải xác nhận trong lab cách orchestrator/mgr hiện tại của bạn nhận các tham số `--daemon-types`, `--hosts`, `--limit` trước khi dựa vào chúng trong MOP.

---

# 5. Blocker matrix trước Production rollout

| ID | Điều kiện | Mức | Hành động |
|---|---|---:|---|
| `B01` | Có `inactive/incomplete/stale/down/unknown` PG | **HARD BLOCKER** | Khôi phục PG health trước |
| `B02` | Có `unfound` chưa xử lý | **HARD BLOCKER** | Xác định source/restore plan; không `mark_unfound_lost` như bước upgrade |
| `B03` | OSD canary không pass `ok-to-stop` | **HARD BLOCKER** | Chọn OSD khác hoặc khôi phục redundancy |
| `B04` | Host/daemon quan trọng offline ngoài kế hoạch | **HARD BLOCKER** | Khôi phục trước rollout |
| `B05` | OSD crash/assert/startup bất ổn trước upgrade | **HARD BLOCKER** | Điều tra lỗi nền trước |
| `B06` | RocksDB/PGLog phình tới mức boot/space bất ổn | **HARD/CONDITIONAL** | Xử lý runbook riêng trên clone/offline |
| `B07` | EC pool có degraded/inconsistent/unfound và chưa hiểu hinfo/min_size | **HARD/CONDITIONAL** | Không dùng canary để “thử chữa” |
| `B08` | Scrub/repair đang stuck hoặc inconsistency chưa xác định authoritative shard | **CONDITIONAL BLOCKER** | Điều tra trước |
| `B09` | `backfill_toofull` / thiếu capacity headroom | **HARD/CONDITIONAL** | Bổ sung headroom/giảm batch |
| `B10` | mClock bật nhưng startup/capacity behavior chưa biết | **CONDITIONAL BLOCKER** | Lab test + baseline |
| `B11` | Store legacy có khả năng thiếu `SNAPMAPPER2` nhưng chưa clone-test | **CONDITIONAL BLOCKER** | Clone test conversion |
| `B12` | RBD read-only critical nhưng chưa test mixed primary | **CONDITIONAL BLOCKER** | Test `metadata_list` base/target |
| `B13` | Manifest/tiering critical nhưng chưa test degraded snapshot clone | **CONDITIONAL BLOCKER** | Lab fixture hoặc mark feature N/A |
| `B14` | Không có rollback/fix-forward owner và stop criteria | **PROCESS BLOCKER** | Hoàn thiện MOP trước Production |
| `B15` | Rollback yêu cầu downgrade 16.2.15→16.2.5 nhưng chưa lab-test same-store round-trip | **PROCESS/TECH BLOCKER** | Không coi binary downgrade là guaranteed rollback |

---

# 6. Test matrix bắt buộc trước rollout

## Tier 0 — Bắt buộc với mọi cluster

### T0-01 — Canary restart + basic service

- [ ] Upgrade 1 OSD canary.
- [ ] OSD trở lại `up/in` như dự kiến.
- [ ] PG peering hội tụ.
- [ ] Không có crash/assert mới.
- [ ] Client RBD/RGW/RADOS representative read/write thành công.
- [ ] Checksum test data trước-sau khớp.
- [ ] Baseline vs after-upgrade latency không vượt guardrail.

### T0-02 — Mixed-primary I/O

- [ ] Test I/O khi primary = 16.2.5.
- [ ] Test I/O khi primary = 16.2.15.
- [ ] Failover primary trong lúc workload chạy.
- [ ] Không có error rate/correctness regression.

### T0-03 — Recovery/backfill interruption

- [ ] Tạo controlled degraded/recovery trong lab.
- [ ] Restart/failover primary giữa recovery/backfill.
- [ ] Resume hoàn chỉnh.
- [ ] Không stuck peering/reservation.
- [ ] Dữ liệu checksum đúng sau recovery.

### T0-04 — Scrub/deep-scrub mixed-version

- [ ] Scrub PG có primary target và replica base.
- [ ] Đổi primary rồi chạy lại.
- [ ] Test remap/stale/delayed event nếu lab cho phép.
- [ ] Scrub FSM kết thúc, không stuck.
- [ ] Không xuất hiện inconsistency mới.

### T0-05 — Restart sau khi state đã thay đổi

- [ ] Để target nhận OSDMap mới, có PGLog activity và recovery state.
- [ ] Restart target.
- [ ] Xác nhận peering/map-gap xử lý bình thường.
- [ ] Đây là test quan trọng cho `OSD-005/007`, không chỉ restart ngay sau upgrade.

---

## Tier 1 — Bắt buộc nếu có EC

### T1-EC-01 — Async recovery và `min_size`

Theo scenario `V01-01` của source:

- [ ] EC pool lab có `min_size` giống Production.
- [ ] Kích hoạt async recovery condition.
- [ ] Primary target không làm acting set xuống dưới `min_size`.
- [ ] Client I/O còn/không còn đúng theo pool policy.

### T1-EC-02 — Corrupt/missing hinfo fixture

Theo `V01-02`:

- [ ] Chỉ phá attr trên scratch object/fixture.
- [ ] Target không assert.
- [ ] Deep-scrub báo inconsistency phù hợp.
- [ ] Có source tốt → repair lab về clean.
- [ ] Thiếu source → dừng ở `unfound`; **không** dùng `mark_unfound_lost` để “PASS test”.

---

## Tier 2 — Bắt buộc theo feature

### T2-PGLOG — PGLog dups

- Fixture PGLog dups vượt ngưỡng.
- Kiểm tra warning/trim có giới hạn.
- Offline tool chỉ trên clone OSD dừng.
- Reopen DB/store sau tool.

### T2-PARTIAL — Large object partial recovery

- Ngắt/restart primary giữa partial recovery.
- So recovery bytes/time base vs target.
- Checksum object sau hoàn tất.

### T2-STRETCH — Stretch mode

- Interrupt backfill.
- Failover primary.
- Resume và kiểm acting candidate/accounting.
- Không bypass full/backfill guard.

### T2-RBD-CAPS — RBD read-only

- `metadata_list` trên đúng `rbd_info` được phép ở target.
- Method/object ngoài scope vẫn denied.
- Lặp với primary base/target.

### T2-MCLOCK — mClock

- Restart OSD.
- Xác định startup benchmark có chạy không.
- Kiểm historical/persisted capacity.
- Đo p99 + recovery throughput.
- Không heartbeat timeout giả.

### T2-SNAPMAPPER — Legacy store

- Chỉ trên clone thiếu `SNAPMAPPER2`.
- So old/new keys và cardinality.
- Không collision/mất suffix.

### T2-MANIFEST — tiering/manifest

- Fixture `set_chunk` + snapshot clone degraded/unreadable.
- Target requeue cho tới khi clone readable.
- Refcount/checksum đúng.

---

# 7. Production canary acceptance criteria

Canary chỉ được PASS khi **tất cả điều kiện áp dụng** đạt:

- [ ] OSD target chạy ổn định, không crash/assert.
- [ ] PGs liên quan hội tụ về state mong đợi.
- [ ] Không có `unfound`/`inconsistent` mới.
- [ ] Client error rate không tăng bất thường.
- [ ] Checksum test objects/images đúng.
- [ ] p95/p99 latency nằm trong guardrail đã định trước.
- [ ] Recovery/backfill throughput trong khoảng chấp nhận được.
- [ ] CPU/RAM/disk/network của các replica còn lại còn headroom.
- [ ] Scrub/deep-scrub scenario áp dụng PASS.
- [ ] Primary base↔target failover PASS.
- [ ] Restart target lần hai sau khi đã phát sinh state PASS.
- [ ] Không có warning mới mà team chưa giải thích được.

**Không dùng một mình `HEALTH_OK` làm acceptance criterion.**

---

# 8. Rollback / Fix-forward

## 8.1. Phải tách 3 khái niệm

### A. Stop rollout — **có thể làm ngay**

Nếu cephadm upgrade đang chạy:

```bash
ceph orch upgrade stop
```

Điều này **chỉ dừng quá trình nâng thêm daemon**. Nó không tự hạ các daemon đã lên 16.2.15.

### B. Service recovery — **rollback vận hành ưu tiên**

Nếu canary 16.2.15 gặp lỗi nhưng cluster vẫn còn replica tốt:

1. Dừng rollout.
2. Không nâng thêm OSD.
3. Giảm/loại traffic khỏi canary nếu cần.
4. Chuyển primary workload nhạy cảm sang OSD khỏe nếu runbook của bạn hỗ trợ.
5. Nếu canary không ổn định, giữ nó out/down theo kế hoạch an toàn và để dữ liệu được phục vụ từ replica còn lại.
6. Khôi phục redundancy trên OSD khác nếu cần/có capacity.
7. Thu log/store evidence trước khi làm mutation/repair.
8. Chọn **fix-forward lên 16.2.15** hoặc restore/rebuild OSD từ replica tốt thay vì mặc định downgrade same store.

### C. Binary downgrade 16.2.15 → 16.2.5 — **không coi là guaranteed rollback**

Cephadm Pacific documentation có syntax target một version cụ thể và mô tả cả upgrade/downgrade. Tuy nhiên report code-level này chỉ ra ít nhất một state mới (`cluster_osdmap_trim_lower_bound` trong OSD superblock) mà downgrade round-trip với old writer **chưa được test** trong phân tích.

Vì vậy, đối với Production:

> **Không ghi trong MOP rằng “rollback = đổi image về 16.2.5” trừ khi chính lab của bạn đã chứng minh same-store downgrade sau khi target thực sự ghi state mới.**

---

## 8.2. Lab test bắt buộc nếu tổ chức yêu cầu binary rollback

Dùng một OSD lab/clone:

1. Boot bằng 16.2.5 và ghi baseline.
2. Upgrade lên 16.2.15.
3. Cho OSD nhận map mới.
4. Tạo PGLog activity.
5. Chạy scrub/deep-scrub.
6. Tạo recovery/partial recovery phù hợp.
7. Restart 16.2.15 để chắc state mới đã persist.
8. Dừng OSD sạch.
9. Thử boot **cùng store** bằng 16.2.5.
10. Kiểm mount/startup, peering, read/write, checksum, PGLog decode, scrub.
11. Restart thêm một lần ở 16.2.5.
12. Sau đó đưa về 16.2.15 và kiểm lại.

### PASS chỉ khi

- old binary mount/start được;
- không crash/assert/decode error;
- PG peering hoàn chỉnh;
- data checksum đúng;
- không tạo inconsistency/unfound;
- re-upgrade lên target vẫn sạch.

Nếu chưa test được chuỗi này thì **binary downgrade = unsupported by your runbook**, dù command orchestration có thể cho phép chọn version cũ.

---

# 9. Những thao tác KHÔNG được biến thành bước pre-upgrade mặc định

Các source files nhấn mạnh rằng một số action chỉ dành cho fixture/clone/troubleshooting. Không đưa các thao tác sau vào checklist kiểu “cứ chạy trước upgrade”:

- `repair` hàng loạt;
- `mark_unfound_lost`;
- trim PGLog offline hàng loạt;
- phá/xóa EC hinfo;
- trim map để thử trên Production;
- mutate device/store để kiểm conversion;
- force mClock benchmark toàn cụm;
- thay cluster flags chỉ để làm health xanh;
- chạy `ceph-objectstore-tool` mutation trên OSD đang phục vụ dữ liệu.

---

# 10. Mẫu checklist ngắn dùng trong MOP

## PRE-CHECK — Cluster

- [ ] Target = `16.2.15`, image digest recorded.
- [ ] All hosts online.
- [ ] Required mgr standby available.
- [ ] `ceph -s` / `ceph health detail` reviewed.
- [ ] No PG hard-blocker state.
- [ ] No unfound.
- [ ] No unexplained OSD crash.
- [ ] Capacity/backfill headroom OK.
- [ ] Pool inventory complete: replicated/EC, size/min_size.
- [ ] Scrub backlog/flags reviewed.
- [ ] PGLog/RocksDB risk reviewed.
- [ ] WPQ/mClock known.
- [ ] Legacy store/SNAPMAPPER2 applicability known.
- [ ] RBD read-only caps applicability known.
- [ ] Manifest/tiering applicability known.
- [ ] Rollback/fix-forward owner assigned.

## PRE-CHECK — Canary OSD

- [ ] OSD selected with acceptable PG/workload impact.
- [ ] Relevant PGs healthy.
- [ ] Replica hosts/OSDs have resource headroom.
- [ ] `ceph osd ok-to-stop <id>` PASS.
- [ ] Baseline p95/p99 recorded.
- [ ] Baseline recovery throughput recorded.
- [ ] Client checksum fixture prepared.
- [ ] Primary PG list captured.
- [ ] Stop criteria agreed.

## CANARY — Mixed version

- [ ] Upgrade/restart target OSD.
- [ ] OSD rejoins/peers cleanly.
- [ ] Client I/O PASS with target as replica.
- [ ] Client I/O PASS with target as primary.
- [ ] Primary target→base failover PASS.
- [ ] Primary base→target failover PASS.
- [ ] Recovery/backfill interruption PASS.
- [ ] Scrub/deep-scrub PASS.
- [ ] Restart-after-state-change PASS.
- [ ] Feature-specific tests PASS/N/A.
- [ ] QoS guardrails PASS.

## DECISION

- [ ] **GO** — no new unexplained warning, correctness/QoS PASS.
- [ ] **HOLD** — warning/regression exists but service stable; investigate before next OSD.
- [ ] **STOP/FIX-FORWARD** — data correctness, peering, crash, unfound/inconsistent or QoS stop threshold violated.

---

# 11. Nâng cấp checklist từ hai file: phần nào là bắt buộc, phần nào conditional

| Check | Mọi cluster | Chỉ khi áp dụng |
|---|---:|---:|
| Health/PG hard gate | ✅ | |
| `ok-to-stop` từng canary | ✅ | |
| Mixed-primary read/write | ✅ | |
| Recovery/backfill interruption | ✅ | |
| Scrub mixed-version | ✅ | |
| Restart sau state change | ✅ | |
| QoS baseline/guardrail | ✅ | |
| EC min_size + hinfo | | ✅ EC |
| PGLog dups offline fixture | | ✅ nếu có dấu hiệu PGLog/DB phình |
| Stretch ordering | | ✅ stretch mode |
| mClock benchmark/capacity | | ✅ mClock |
| SnapMapper conversion | | ✅ legacy store thiếu `SNAPMAPPER2` |
| RBD read-only metadata | | ✅ dùng profile tương ứng |
| Manifest/tiering clone recovery | | ✅ dùng feature |
| Binary downgrade same-store | | ✅ nếu MOP tuyên bố hỗ trợ rollback bằng downgrade |

---

# 12. Điểm cần phối hợp với các report khác

Report này **không đủ** để kết luận toàn bộ upgrade. Trước GO Production cần ghép ít nhất:

- **BlueStore/BlueFS:** disk/store format, mount/replay, allocator, fsck/repair risks.
- **MON/OSDMap/CRUSH:** map compatibility, require release, CRUSH/PG placement behavior.
- **Config/defaults:** option rename/default changes; recovery/backfill/scrub/mClock config.
- **cephadm/MGR:** orchestration order, image pull, staggered parameters, pause/stop behavior.
- **RBD/RGW:** client/service continuity, auth/caps, workload-specific smoke test.

`OSD-007` đặc biệt phải cross-check với report MON/OSDMap/CRUSH vì field/map semantics không nằm hoàn toàn trong owner `01`.

---

# 13. Kết luận áp dụng

Với riêng hai file `01-osd-pg-recovery`, **không có bằng chứng về một protocol OSD mới duy nhất bắt buộc migration trước khi lên 16.2.15**. Rủi ro chính là các đường hành vi thay đổi theo **version của primary**, restart và trạng thái degraded/recovery/scrub.

Vì vậy thay đổi quan trọng nhất cho checklist là:

> **Từ health-check tĩnh → chuyển sang canary mixed-version có fault/restart/primary-failover validation và stop condition rõ ràng.**

Hai nhóm cần ưu tiên cao nhất từ report nguồn là:

1. **EC degraded recovery / hinfo (`OSD-001/002`)** nếu cluster có EC.
2. **Mixed-primary scrub/peering/map-gap (`OSD-004/006/007`)** cho canary rollout.

Về rollback:

> **Có thể dừng rollout; không nên mặc định coi downgrade image/package là rollback dữ liệu an toàn.** Nếu Production MOP yêu cầu downgrade 16.2.15 → 16.2.5 trên cùng OSD store thì phải có lab test round-trip riêng trước.

---

# 14. Nguồn đối chiếu

## Source nội bộ được cung cấp

- `01-osd-pg-recovery(1).md` — phân tích code-level `v16.2.5 → v16.2.15`.
- `01-osd-pg-recovery(1).csv` — 45 file inventory của owner `01-osd-pg-recovery`.

## Ceph documentation đối chiếu

- Pacific v16.2.15 release notes: <https://docs.ceph.com/en/latest/releases/pacific/>
- Pacific cephadm upgrade: <https://docs.ceph.com/en/pacific/cephadm/upgrade/>
- Pacific `ceph` command / `osd ok-to-stop`: <https://docs.ceph.com/en/pacific/man/8/ceph/>
- Pacific OSD troubleshooting / scoped `noout`: <https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-osd/>

