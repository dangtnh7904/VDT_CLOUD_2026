# 08 — cephadm/orchestrator, upgrade và daemon lifecycle: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **149 dòng** do owner `08-cephadm-orchestrator` sở hữu. Hai gate quan trọng nhất là (1) lần target MGR đầu tiên hoàn tất migration sẽ nâng `migration_current` từ 2 lên 5, trong khi code base không thể đi lùi từ state 5 và sẽ chặn reconciliation; (2) private/insecure registry phải được thử pull trên **mọi host**, vì endpoint target vẫn có các guard/argument không đồng nhất giữa first pull, periodic login và per-host upgrade pull.
>
> **Trạng thái kiểm chứng:** đã đọc net diff hai endpoint, symbol/caller liên quan, lịch sử commit và test/QA trong repository. Chưa khởi động cluster, chưa chạy test Ceph, chưa xác minh As-Is về NFS, số MGR, registry hay gateway/monitoring service.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; source tree dùng cho suite là non-shallow và sạch; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [08-cephadm-orchestrator.csv](./08-cephadm-orchestrator.csv). CSV có 149 dòng, giữ nguyên 21 cột nền của master inventory và nối 6 cột phân tích.
- Thống kê owner: `A50/M83/D6/R10`, `+14.639/-3.670`; `P1=41`, `P2=108`; loại file gồm 40 runtime source, 80 test/QA, 24 tài liệu, 1 config/schema và 4 zero-LOC marker.

Disposition cuối của 149 dòng:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `material` | 1 | File migration trực tiếp thay đổi persistent control state |
| `conditional` | 19 | Runtime/config chỉ kích hoạt khi dùng host/service/registry tương ứng |
| `mixed` | 11 | File chứa cả hunk finding-relevant và hunk support/trivial |
| `support` | 99 | Test, QA, docs, template hoặc fixture hỗ trợ finding |
| `trivial` | 19 | Đã sàng lọc nhưng không có causal chain upgrade độc lập |
| **Tổng** | **149** | Khớp chính xác CSV |

`P1/P2` chỉ là ưu tiên đọc ban đầu. Disposition là kết luận sau khi đọc endpoint diff và lịch sử; một dòng có thể hỗ trợ nhiều finding nên không cộng số dòng theo ID.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Đặt rollback checkpoint trước khi target MGR làm active.** Chụp `migration_current`, cephadm module store/config-key, service specs, NFS exports/grace và registry credential location. Sau khi target đi tới state 5, code base `v16.2.5` nhìn `5 != 2` là migration còn dang dở nhưng không có transition xử lý state 5; failback MGR đơn thuần không khôi phục reconciliation.
2. **Nếu có CephFS, không dùng `upgrade stop` sau khi MDS preparation đã bắt đầu.** Target luôn chạy sequence cả cho minor upgrade, có thể hạ `max_mds`, tắt `allow_standby_replay` và bật `mon_mds_skip_sanity=1`. Endpoint chỉ restore ở đường hoàn tất MDS/toàn upgrade; `upgrade_stop()` xóa state mà không restore.
3. **Với 3 MGR trở lên, canary phải chứng minh cả image digest và `deployed_by` hội tụ.** Fix `3e122e0f1c0` nằm ở target active MGR; chỉ nhìn version/image là chưa đủ để phát hiện vòng failover/redeploy cũ.
4. **Không gửi tham số staggered khi active MGR vẫn là 16.2.5.** Base chưa có `--daemon-types/--services/--hosts/--limit`. Nếu chọn staggered, dùng đúng transition được tài liệu target mô tả: nâng standby MGR có kiểm soát, promote target code, rồi mới khởi tạo các phase và giữ thứ tự daemon.
5. **Tất cả host phải online trước rollout, đặc biệt host NFS/ingress.** Target giữ daemon trên host unreachable trong placement nói chung, nhưng NFS và HAProxy có watcher/reschedule. Mất SSH tạm thời khi target MGR active có thể kích hoạt thay đổi placement ngoài dự kiến.
6. **Private/insecure registry là preflight theo từng host.** Đảm bảo credential đã phân phối và target digest có thể pull/inspect trên mọi node. Không suy ra thành công toàn cluster từ first pull trên một host.
7. **Canary local cephadm trên daemon chưa redeploy.** Target đổi container name dấu chấm sang dấu gạch ngang và có compatibility fallback cho inspect/remove/stop, nhưng endpoint `exec_cmd()` tìm ra old name rồi vẫn truyền new name. Read-only exec trên một old-name container phải được thử trước rollout rộng.
8. **Snapshot config render của service đang dùng.** Monitoring stack có thể được redeploy sau MGR phase; ingress/iSCSI/NFS templates và post-actions cũng đổi. Đối chiếu thêm các gate monitoring trong [07-mgr-modules-monitoring.md](./07-mgr-modules-monitoring.md).

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro khi kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| ADM-001 | MDS sequence, FS flags và cleanup khi stop | Có CephFS/MDS cần nâng | MDS phase / cancel | Cao | High |
| ADM-002 | Vòng failover MGR khi có ≥3 MGR | 3+ MGR hoặc manual partial MGR rollout | MGR mixed-version | Cao | High |
| ADM-003 | Staggered filters/limit và transition từ base cũ | Dùng phased upgrade | MGR handoff / từng phase | Trung bình-cao | High |
| ADM-004 | Migration state 2→5, NFS/_admin/registry và rollback | Mọi existing cephadm cluster; NFS/registry tăng tác động | First target active MGR | **Cao; rollback boundary** | High |
| ADM-005 | Offline host watcher và action suppression | Host mất reachability; đặc biệt có NFS/HAProxy | mixed/stabilization | Trung bình-cao | High |
| ADM-006 | Daemon action/remove/redeploy và failure signal | Reconciliation hoặc operator action | toàn rollout | Trung bình | High |
| ADM-007 | Registry credentials, image inspect/pull và error paths | Private/insecure registry hoặc tag listing | preflight/per-host pull | Cao theo điều kiện | High cho code; runtime chưa chạy |
| ADM-008 | Local cephadm container/systemd compatibility | Daemon cũ còn dot-name; restart chậm | redeploy/restart | Trung bình-cao | High cho endpoint code |
| ADM-009 | Specialized service render/post-actions | Có ingress/iSCSI/NFS/monitoring tương ứng | redeploy/post-MGR | Trung bình | Medium-high |

Mức rủi ro là hậu quả khi điều kiện đúng, không phải xác suất cluster cụ thể gặp lỗi.

## 4. Phát hiện chi tiết

### ADM-001 — Minor upgrade nay luôn chạy MDS safety sequence; cancel không tự restore

**Evidence.** Dòng CSV `1663` trỏ tới [upgrade.py](../../ceph16.2.15/ceph/src/pybind/mgr/cephadm/upgrade.py); dòng `698` là QA suite link. Bốn commit quyết định behavior:

- `6697ebe2eaac4be3bf7fafa057ae98398aa115ea` bỏ check “khác major” trong `_prepare_for_mds_upgrade()`, nên minor upgrade cũng chạy sequence.
- `dcb3455fdfba83a64be3b0a030ef468acfcf6fe6` lưu/tắt `allow_standby_replay`, hạ `max_mds` về 1 và restore sau MDS phase.
- `b67f81b862fc65b9e0d239b73df6b82d898ce9e6` cho phép tiếp tục nếu không có MDS `up`, nhằm phá deadlock compat-set quanh v16.2.5.
- `753fd2fb32196d17e186152e7deaef1e0558b781` đặt `mon_mds_skip_sanity=1` trong upgrade và chỉ xóa ở cuối `_do_upgrade()`.

**Trước → sau.** Base bỏ qua scale-down cho cùng major khi MDS metadata đã cùng major. Target luôn chuẩn hóa mỗi filesystem về một active rank, không standby-replay, rồi nâng MDS và restore giá trị đã lưu. Đây là thay đổi availability thật trong chính upgrade 16.2.5→16.2.15.

**Cancel boundary.** `upgrade_pause()` giữ state nên có thể resume. Ngược lại, `upgrade_stop()` hoàn tất progress rồi xóa `upgrade_state`; nó không gọi `_complete_mds_upgrade()` và không xóa `mon_mds_skip_sanity`. Nếu stop sau preparation, `max_mds=1`, standby-replay off hoặc sanity skip có thể còn lại, còn giá trị gốc đã mất khỏi state.

**Hành động/kiểm chứng.** Trước MDS phase lưu `max_mds`, `allow_standby_replay`, MDS ranks/states và effective `mon_mds_skip_sanity`. Chạy workload CephFS qua rank reduction, trường hợp zero-up và restore; xác nhận mọi FS trở về giá trị gốc và config sanity bị gỡ. Nếu cần dừng để điều tra, ưu tiên pause; stop chỉ sau khi có runbook restore thủ công đã thử.

**Đánh giá.** Rủi ro **cao khi có CephFS**, confidence **high**. QA suite `mds_upgrade_sequence` có biến thể rank/standby-replay, nhưng chưa được chạy trong môi trường này.

### ADM-002 — Target sửa vòng failover/redeploy khi có ba MGR trở lên

**Evidence.** Commit `3e122e0f1c031b366cde562af938103f5463de38` đổi điều kiện trong `_do_upgrade()`: target chỉ hoãn các daemon “đúng image nhưng sai `deployed_by`” khi active MGR chưa chạy target digest; không còn hoãn chỉ vì active MGR tự cần redeploy.

**Trước → sau.** Với A/B/C, old active A có thể nâng B/C lên image mới nhưng metadata vẫn cho biết chúng do old cephadm deploy. Sau failover, B và C có thể lần lượt coi chính mình cần xử lý rồi failover mà không redeploy peer, tạo vòng lặp. Target active MGR đã ở đúng digest có thể sửa `deployed_by` của peer trước khi failover tiếp.

**Mixed phase.** Fix chỉ có hiệu lực khi target code đang active. Hai-MGR topology thông thường ít lộ lỗi hơn, nhưng commit cũng ghi nhận manual partial upgrade có thể tạo trạng thái tương tự.

**Hành động/kiểm chứng.** Với topology 3+, ghi active/standby trước canary; sau mỗi failover kiểm tra từng MGR có target image digest **và** target `deployed_by`. Stop condition là active role quay vòng mà hai metadata không hội tụ. Không có regression unit test chuyên biệt cho topology 3+ trong file test endpoint; staged failover là bằng chứng môi trường cần bổ sung.

**Đánh giá.** Rủi ro **cao theo topology**, confidence **high** từ endpoint code và commit rationale.

### ADM-003 — Staggered upgrade là state machine mới, không phải CLI có thể gọi ngay từ base

**Evidence.** `07ccf07a2853d4f93e83f38da5c54fda2a534376` thêm validation cho `daemon_types`, `services`, `hosts`; `6b61f35b73fe17fb4cb36b22838bdc71bf22a6d6` lưu filters/`limit` vào `UpgradeState` và áp dụng chúng trong progress, selection và completion. Các dòng `735`–`740`, `1662`, `1663`, `2184`, `2185` là QA/unit/API support.

**Contract target.**

- Thứ tự vẫn bị cưỡng chế: MGR → MON → CRASH → OSD → MDS → gateway.
- `services` chỉ nhận cùng một service type; `hosts` có thể kết hợp; `limit` chỉ giảm cho actual image change, không giảm cho redeploy-only.
- Validation có thể pull target image trước khi trả kết quả.
- Monitoring daemons có thể được redeploy sau MGR phase dù image version không đổi.

Base 16.2.5 không parse các tham số này. Tài liệu target vì thế yêu cầu upgrade MGR bootstrap trước cho nguồn không hỗ trợ staggered, rồi mới gọi filtered upgrade.

**Hành động/kiểm chứng.** Chọn một strategy duy nhất trước rollout. Nếu staggered, ghi phase manifest (filter, host/service set, limit, expected count), verify phase status và `upgrade_state` sau mỗi lần active MGR đổi. Test rejection khi chọn type out-of-order và test một `limit` nhỏ; không dùng completion của một phase làm bằng chứng toàn cluster đã target.

**Đánh giá.** Rủi ro **trung bình-cao**, confidence **high**.

### ADM-004 — `migration_current=5` là rollback boundary; NFS migration có side effect service/data

**Evidence endpoint.** Dòng `1634` là [migrations.py](../../ceph16.2.15/ceph/src/pybind/mgr/cephadm/migrations.py). Base có `LAST_MIGRATION=2`; target có `LAST_MIGRATION=5`:

- 2→3: tạo pool `.nfs`, đọc legacy exports, copy grace, có thể rename `nfs.ganesha-*`, remove NFS daemons cũ, re-save spec và apply exports.
- 3→4: bảo đảm `client.admin` được quản lý với placement `label:_admin`.
- 4→5: chuyển registry URL/user/password từ module options sang config-key `registry_credentials`, rồi xóa ba option cũ.

Commits chính là `a181dd28b20792c23eb1606cc2953fb643609ee1`, `161692011c81733d374b57b2047592d59100b8ee`, `b0affad4408feb6b7a5a7dd2ca64f8ab401313fc`, `48fb4dab3cae3a4138c0c7a7d6e6d53331c0c720` và `b48853cbc49805e6d60e39cce09ff06308671695`.

**Rollback proof.** Sau target completion, state là 5. Base `is_migration_ongoing()` kiểm tra `migration_current != LAST_MIGRATION`, tức `5 != 2` là true; base `migrate()` chỉ có 0→1 và 1→2 nên không thay đổi 5. `verify_no_migration()` vì vậy tiếp tục chặn apply service. Đây là incompatibility trực tiếp giữa endpoint, không phải suy đoán từ commit title.

**NFS nuance.** Target constructor gọi `migrate(startup=True)` và cố ý chưa chạy 2→3 ở startup; serve loop chạy migration rồi bỏ qua reconciliation cho tới khi xong. Trong `migrate_nfs_spec()`, lỗi `nfs export apply` được log warning nhưng không làm migration fail/retry, nên phải đối chiếu số export thay vì chỉ nhìn state=5.

**Hành động/kiểm chứng.** Trước promote target active MGR, export service specs, NFS export objects/grace và cephadm store/options; xác định rõ có service `nfs.ganesha-*` hay pool/namespace legacy. Sau migration, so khớp export count/content, grace, service name, daemon/client I/O và `client.admin` distribution. Không coi failback binary về 16.2.5 là rollback hoàn chỉnh; cần một procedure phục hồi metadata/config đã thử nghiệm hoặc kế hoạch forward-fix.

**Đánh giá.** Rollback risk **cao và áp dụng cho existing cephadm control state**; phần NFS/registry là **conditional**. Confidence **high**.

### ADM-005 — Target phân biệt unreachable/maintenance và chủ động reschedule NFS/HAProxy

**Evidence.** `b509163076499d705dae596b3e24e24a62f34789` đưa unreachable hosts vào `HostAssignment` để daemon trên đó vẫn được tính và không bị remove tự động. `84a650d3f581f5c94cf3eb6d39ad3bfbca719044` loại offline, non-maintenance host khỏi candidate riêng cho NFS; `0f46165a0eb37a49b95c699ae9137798b8023b89` mở cùng policy cho HAProxy; `2f58f78ddb11643bf9bff277840eeee326e84235` thêm `OfflineHostWatcher` polling 20 giây; `79333c0390905771d4c6891192520a172ee7e00e` bỏ qua daemon action trên offline host.

**Trước → sau.** Target tránh cố remove/redeploy trên host không truy cập được, nhưng đối với NFS và HAProxy lại có đường availability chủ động: phát hiện host mất kết nối, đánh thức serve loop và đặt replacement ở host khác. Maintenance host được xử lý khác một host bất ngờ offline.

**Explicit destructive path.** `orch host rm --offline --force` mới có thể purge OSD metadata và service state mà không liên lạc host. Đây là lệnh operator, không phải tác động tự động của upgrade; sự tồn tại của nó yêu cầu runbook không dùng nhầm để “xử lý nhanh” một host chỉ mất SSH tạm thời.

**Hành động/kiểm chứng.** Làm sạch host health/SSH trước rollout. Nếu có NFS HA hoặc ingress, thử mất management connectivity trong staging và quan sát thời điểm replacement, VIP/client continuity, daemon cũ khi host trở lại và absence of unintended remove actions. Không trộn host drain/maintenance/offline removal với canary trừ khi đó là scenario đã phê duyệt.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**.

### ADM-006 — Action/redeploy an toàn hơn nhưng failure signal và runbook đổi

**Evidence.**

- `4df6c4a7b583b452fa2a9f7b319a6ea53742687b`: `service_action('stop')` từ chối stop toàn service MGR/MON/OSD.
- `6cc1b8142f87e8d4f05fb96540dcf590abd10c50`: exception trong placement đánh dấu progress `fail` thay vì để indicator treo.
- `cc33d089ccff92780fd196b84f9fe7e1f79a824f`: remove daemon truyền TCP ports để đóng firewall.
- `0cbc806d68eb2078e7a078ee0e9b62cca668582b`: daemon mới vào cache với status `starting` thay vì giả định `running`.
- Target còn thêm guard last-`_admin`, moved-OSD detection, OSD reactivate/replacement và async iSCSI post-remove.

**Tác động upgrade.** Đây phần lớn là hardening, nhưng automation cũ có thể thấy return message/status/progress khác. Một redeploy thành công ở process level chưa đồng nghĩa daemon đã `running`; stop toàn service critical không còn được schedule.

**Hành động/kiểm chứng.** Đổi rollout gate sang trạng thái daemon thực, health/event và progress terminal; không parse chuỗi cũ làm success duy nhất. Thử một redeploy failure và xác nhận progress fail/event đủ rõ để stop rollout. Kiểm tra firewall port sau remove/recreate và OSD replacement mapping nếu các path đó nằm trong maintenance window.

**Đánh giá.** Rủi ro **trung bình**, confidence **high**.

### ADM-007 — Registry migration/error handling tốt hơn, nhưng endpoint còn hai edge cần gate

**Evidence tốt lên.** Target lưu credential dưới config-key thay vì module option; standalone cephadm phân biệt unauthorized pull (`5fd3b523e8661ba267077dc3dea5656fcf76fd31`), dùng `Error` đúng CLI path khi pull fail (`ea3289f0f69645b138121e6d14fc8bbdfd70b50d`) và hỗ trợ `--insecure` cho Podman (`1e4461f42d48559927947cca59e6db81316dd4cd`). `Registry.get_tags()` chuyển connection failure thành lỗi orchestrator ở `f17151ee5f66a0b68e9d7f1455812e4f73c208aa`. `_get_container_image_info()` có thể inspect local trước khi pull khi `use_repo_digest=false`.

**Edge 1 — credential guard.** Periodic host refresh kiểm tra config-key mới, nhưng endpoint `_create_daemon()` và `_get_container_image_info()` vẫn guard login bằng `self.mgr.registry_url`. Migration 4→5 lại xóa chính option này. Vì vậy host còn `needs_registry_login` có thể bỏ qua immediate login ở deploy/first-image path và chỉ được sửa khi periodic distribution chạy.

**Edge 2 — insecure per-host pull.** First image lookup thêm `--insecure` khi option bật. Nhưng `_upgrade_daemons()` pull image trên từng host với args rỗng, nên endpoint code không chứng minh TLS bypass được truyền cho các pull còn lại.

**Hành động/kiểm chứng.** Trước upgrade, xác nhận config-key mới tồn tại mà không in secret, mọi host báo registry login complete, và pull/inspect cùng digest thành công từ từng node. Với insecure registry, chạy đúng per-host path của upgrade trong staging; nếu bất kỳ host nào cần `--tls-verify=false`, không dựa vào first pull thành công. Theo dõi `UPGRADE_FAILED_PULL`, host detail và registry auth log; resume chỉ sau khi nguyên nhân được sửa.

**Đánh giá.** Rủi ro **cao theo điều kiện private/insecure registry**, confidence **high về code path**, runtime applicability chưa được kiểm chứng.

### ADM-008 — Container-name transition có fallback chưa trọn vẹn; systemd stop/start được harden

**Evidence.** `00cc31d254520fc66f183d6eba23e3f049b75832` đổi container name từ dấu chấm sang dấu gạch ngang để tránh FQDN side effect; `979e9febdd7addcb21e023a408ea3d0c0001d8df` và `725f729de8506f9c02ae69c801c24bb22e9049c8` thử cả old/new name cho inspect/remove/stop. `64bc43d06663077a540c54395fcf990ca8dedb31` thêm stop fallback vào post-stop và tăng `TimeoutStartSec` 120→200 giây.

**Endpoint gap.** Trong target, `CephContainer.exec_cmd()` gọi `get_running_container_name()` và lưu kết quả vào local `cname`, nhưng command trả về vẫn dùng `self.cname` (new dash-name). Nếu chỉ old dot-name đang chạy, detection thành công nhưng exec vẫn nhắm sai tên. Inspect/remove/stop không có cùng lỗi này.

**Mixed phase.** Daemon base chưa redeploy vẫn có old name; daemon được target redeploy dùng new name/unit files. Read-only admin exec/shell hoặc helper dựa vào `exec_cmd` có thể khác nhau theo từng host cho tới khi redeploy hoàn tất.

**Hành động/kiểm chứng.** Trên canary, inventory old/new container names trước redeploy; thử một read-only exec vào old-name daemon, rồi restart/redeploy và kiểm tra unit stop, post-stop fallback, startup dưới ngưỡng 200 giây và không còn orphan container. Không dùng forced rename/remove làm workaround trong production khi chưa kiểm chứng unit/data-dir ownership.

**Đánh giá.** Rủi ro **trung bình-cao theo trạng thái**, confidence **high** từ endpoint code.

### ADM-009 — Redeploy target có thể render config mới cho gateway/monitoring services

**Evidence.** Các dòng `1642`–`1653`, `1660`, `2246` bao phủ service classes, templates và schema:

- iSCSI bổ sung MGR addresses vào `trusted_ip_list` và chuyển post-remove sang async serve-loop path;
- ingress thêm/fix multiple VIP, RGW SSL/backend address và timeout;
- monitoring thay đổi enable/config, per-node Grafana cert/key, Alertmanager TLS option và Prometheus retention;
- NFS bỏ legacy pool/namespace khỏi spec và dùng fixed `.nfs`, là phần triển khai của ADM-004.

**Activation.** Thay đổi chỉ đi vào daemon khi target MGR reconcile/reconfig/redeploy service tương ứng. Staggered MGR phase có logic redeploy monitoring stack ngay cả khi image của Prometheus/Grafana không đổi, nên “không đổi version container” không đồng nghĩa “không đổi config”.

**Hành động/kiểm chứng.** Inventory service đang deploy; render/diff config trước và sau canary, rồi kiểm tra endpoint/VIP/TLS, iSCSI sessions, NFS mounts và monitoring scrape/rules. Với monitoring, áp dụng thêm parser/alert migration gate của report 07.

**Đánh giá.** Rủi ro **trung bình theo service**, confidence **medium-high** vì code/template rõ nhưng As-Is chưa có.

## 5. Trivial/support changes

- **99 support rows** là docs, QA suites, unit tests, fixtures và templates gắn vào ADM-001…ADM-009; chúng chứng minh intent/coverage nhưng không tự tạo behavior độc lập.
- **19 trivial rows** gồm navigation/rename marker, distro/dashboard/Rook fixture, config/refactor nhỏ và feature thông thường không có đường nhân quả tới rolling compatibility, restart, rollback hoặc acceptance.
- **19 conditional rows** và **11 mixed rows** đã được giữ trong finding tương ứng; CSV ghi symbol, commit và lý do từng dòng.

Tổng `1 material + 19 conditional + 11 mixed + 99 support + 19 trivial = 149`.

## 6. Validation matrix đề xuất

| Scenario | Tiền điều kiện / pha | Quan sát bắt buộc | Stop condition |
| --- | --- | --- | --- |
| Migration/rollback checkpoint | Trước và sau first target active MGR | `migration_current`, service apply, store/options, state 2→5 | State advance nhưng reconciliation/NFS verification không hoàn tất |
| Legacy NFS migration | Có legacy pool/ns hoặc `ganesha-*`; workload đang chạy | Export count/content, grace, `.nfs` namespace, daemon/client continuity | Thiếu export, apply warning, mount/I/O fail |
| MDS sequence | Có multi-rank hoặc standby-replay | max_mds/flag transition, zero-up handling, restore, sanity option removal | FS không active hoặc config không restore |
| MGR ≥3 convergence | Ba target/base MGR lẫn nhau | active changes, image digest, `deployed_by`, restart count | Failover loop hoặc metadata không hội tụ |
| Staggered phase | Target MGR active, filter/limit nhỏ | selected set, enforced order, remaining count, phase completion | Daemon ngoài manifest đổi ngoài expected monitoring redeploy |
| Offline NFS/HAProxy host | Staging, NFS HA hoặc ingress, mất SSH có kiểm soát | watcher detection, replacement, VIP/client, return of old host | Duplicate serving/conflict hoặc action trên offline host |
| Private/insecure registry | Mỗi host, target digest cố định | login state, inspect/pull digest, auth/TLS error, `UPGRADE_FAILED_PULL` | Một host không pull đúng digest |
| Old/new container name | Old daemon trước target redeploy | inspect, read-only exec, stop/restart, orphan container | Exec nhắm sai name hoặc unit không dừng container |
| Gateway/monitoring render | Service tương ứng đang deploy | Config diff, ports/VIP/TLS/session/scrape | Endpoint/session/scrape mất hoặc config không parse |

Các scenario trên là thiết kế kiểm chứng, không phải ủy quyền chạy trên cluster.

## 7. Giới hạn và kết luận

- Chưa có As-Is nên không thể kết luận NFS migration, topology 3+ MGR, private registry hay specialized services có áp dụng cho cluster cụ thể hay không.
- Repository tests/QA đã được đọc nhưng chưa chạy; không có runtime proof cho registry edge, old-name exec hoặc thời gian failover.
- Báo cáo phân biệt endpoint net diff với lịch sử: các commit được dùng để giải thích behavior cuối, không coi mọi regression trung gian là lỗi của endpoint.
- Không có thay đổi on-disk OSD/RADOS do owner 08 trực tiếp sở hữu; persistent boundary ở đây là cephadm/MGR control state, service specs, NFS export migration và credential storage.
- Chưa đủ bằng chứng môi trường để đưa GO/NO-GO production. Các gate tối thiểu trước rollout là rollback checkpoint, host online, registry per-host pull, MGR convergence và — nếu có CephFS/NFS — validation ADM-001/ADM-004.
