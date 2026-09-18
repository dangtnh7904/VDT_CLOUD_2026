# 11 — CephFS/MDS, client, session, caps, volumes và NFS: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **467 dòng** do owner `11-cephfs-mds` sở hữu. Target harden MDS failover/replay, session metadata, mixed-version client requests, volume clone/purge, NFS export và CephFS mirror. Gate security quan trọng nhất chỉ áp dụng cho OpenStack Manila dùng native CephFS trên cluster có lịch sử nâng từ Nautilus hoặc cũ hơn: CVE-2022-0670 được sửa từ Pacific 16.2.10, nhưng nâng binary không tự audit hoặc sửa mọi CephX key đã cấp sai path.
>
> **Trạng thái kiểm chứng:** đã đọc endpoint diff, symbols, commit history, advisory và test/QA trong repository. Chưa chạy rolling MDS, client reconnect, clone/purge, Ganesha hay cephfs-mirror trên cluster thật; chưa có inventory filesystem, rank/standby-replay, client kernel/FUSE, Manila, NFS hoặc mirror topology.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; source tree non-shallow và sạch; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [11-cephfs-mds.csv](./11-cephfs-mds.csv). CSV có 467 dòng, giữ nguyên 21 cột nền của master inventory và nối 6 cột phân tích.
- Thống kê owner: `A165/D64/M224/R14`, `+22.152/-6.375`; `P1=129`, `P2=338`; một binary asset.

Disposition cuối của 467 dòng:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `conditional` | 12 | Runtime/tool effect chỉ xuất hiện khi dùng CephFS mirror hoặc feature tương ứng |
| `mixed` | 59 | File có cả hunk finding-relevant và thay đổi chức năng/refactor khác |
| `support` | 129 | Test, QA hoặc docs trực tiếp hỗ trợ finding |
| `trivial` | 267 | Đã sàng lọc nhưng không có causal chain nâng cấp độc lập |
| **Tổng** | **467** | Khớp chính xác CSV |

Không có dòng `material` vô điều kiện: các thay đổi chỉ kích hoạt theo MDS failover/replay, client behavior, lịch sử Manila, volume/NFS operation hoặc mirroring. Một finding conditional vẫn có thể có hậu quả cao khi điều kiện đúng.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Chụp topology CephFS trước rollout.** Lưu FSMap/MDSMap, active ranks, standby và standby-replay, damaged/failed ranks, client session count, laggy state, health detail, mirror peers và các MGR module volumes/NFS đang active.
2. **Tuân theo sequence CephFS của orchestrator.** Target cho phép thêm một số transition khi không còn MDS `in`, nhưng không biến thứ tự rolling upgrade thành tùy ý. Báo cáo [08-cephadm-orchestrator.md](./08-cephadm-orchestrator.md) vẫn là nguồn quyết định cách cephadm giảm rank/tắt standby-replay và khôi phục cấu hình.
3. **Canary mixed clients.** Target có negotiation cho retry/forward counter 32 bit, refresh feature bits mỗi session open và nhiều cap/session fixes. Kiểm cả base client ↔ target MDS và target client ↔ base MDS; không suy ra kernel client behavior từ libcephfs/FUSE test.
4. **Gate CVE-2022-0670 theo lịch sử, không chỉ current version.** Nếu từng nâng từ Nautilus hoặc cũ hơn và dùng Manila native CephFS, audit toàn bộ CephX path caps. Target sửa discovery logic nhưng không chứng minh các key đã phát hành trước đây đã an toàn.
5. **Volumes clone/cancel/purge cần canary MGR failover.** Target sửa stale clone index, cancel race, metadata lock và OSD-full paths. Không dùng force remove hoặc OSD-full injection trên production như smoke test.
6. **NFS export cần kiểm hai lớp quyền.** Path restriction nằm trong CephX caps; thay đổi RO/RW động còn dựa vào Ganesha enforcement. Sau update/import, kiểm config object, Ganesha reload/restart, CephX caps và negative write.
7. **CephFS mirror cần fault test riêng.** Chỉ khi feature đang dùng, thử blocklist/restart replayer và so mode/data/snapshot ở hai phía. Không coi việc daemon chạy là bằng chứng replication đã hội tụ.

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro khi kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| CEPHFS-001 | Giới hạn session metadata và eviction | Client không advance request tid, `completed_requests` phình lớn | steady-state/post-upgrade | Cao | High |
| CEPHFS-002 | FSMap compat, standby-replay và damaged rank | Rolling MDS/failover, đặc biệt có standby-replay hoặc daemon quá cũ | pre/during upgrade | Cao | High |
| CEPHFS-003 | MDLog/sessionmap replay và blocklist timing | MDS restart/failover/replay | during/post-upgrade | Cao | High |
| CEPHFS-004 | Mixed client request/session/caps | Base/target clients và MDS cùng tồn tại; reconnect/cap revoke | mixed-version window | Trung bình-cao | High |
| CEPHFS-005 | CVE-2022-0670 legacy subvolume discovery | Manila native CephFS và lịch sử từ Nautilus hoặc cũ hơn | pre-upgrade audit | **Cao; security** | High |
| CEPHFS-006 | Volume clone/cancel/purge/metadata races | MGR volumes operations, failover hoặc OSD-full | canary/post-upgrade | Cao theo workflow | High |
| CEPHFS-007 | NFS export validation, caps và dynamic update | CephFS/RGW exports qua Ganesha | post-upgrade management | Cao theo quyền truy cập | High |
| CEPHFS-008 | Mirror replayer restart và permission parity | CephFS snapshot mirroring bật | post-upgrade/failure | Cao theo feature | Medium-high |

Mức rủi ro là hậu quả khi điều kiện đúng; applicability cần xác minh bằng As-Is.

## 4. Phát hiện chi tiết

### CEPHFS-001 — Target evict session metadata quá lớn trước khi MDS bị đẩy read-only

**Evidence.** Các dòng CSV của `src/mds/MDSRank.cc`, `SessionMap.cc/.h`, `qa/tasks/cephfs/test_client_limits.py` và docs health/config map tới CEPHFS-001. Commit `45a9bfd3055343ba6cad4d296e664d166b4e1a92` thêm kiểm tra encoded session metadata; `f5b106c2c86c8238fdc2fb61de6b466878072eda` thêm counter `mdthresh_evicted`. Target có option runtime `mds_session_metadata_threshold`, mặc định 16 MiB.

**Trước → sau.** Ở base, client không advance transaction id có thể làm `completed_requests` của session phình đến mức RADOS write thất bại và MDS chuyển read-only. Target không đưa oversized session vào OMAP update và blocklist/evict client đó.

**Điều kiện và giới hạn.** Chỉ kích hoạt khi encoded session vượt threshold; đây là client-visible eviction chứ không phải sửa trong suốt. Hạ threshold tùy tiện có thể tự tạo reconnect storm. Target giảm một failure mode cụ thể, không chứng minh mọi nguyên nhân MDS read-only đã biến mất.

**Mixed-version.** Active MDS version quyết định enforcement. Client base hoặc target đều có thể bị evict nếu không advance; reconnect behavior lại do client version quyết định.

**Kiểm chứng.** Chụp `session ls`, client metadata/completed requests và perf counter trước rollout. Trong lab hạ threshold có kiểm soát, tạo non-advancing request, xác nhận `mdthresh_evicted`, client reconnect và MDS không read-only. Stop production rollout nếu eviction tăng bất thường, session churn hoặc client I/O không hồi phục.

**Đánh giá.** Rủi ro **cao theo pathological client**, confidence **high**.

### CEPHFS-002 — FSMap xử lý thêm các transition upgrade nhưng sequence vẫn là gate

**Evidence.** `a84a3b5a61ade029568a4165aa7fa40c8b1c38aa` cho `Filesystem::is_upgradeable()` trả true khi standby-replay được cho phép nhưng không còn MDS `in`, đồng thời merge compat trước khi rank được insert. `aea19718eb2111fa2f5abec20367b38b1f41e2d4` xử lý standby-replay báo damaged bằng cách loại daemon/rank holder thích hợp và blocklist. QA `mds_upgrade_sequence` và test `a90b3da879c284445bdd248e0f8dda861d42f9de` bao phủ các transition liên quan.

`0c3026b3f65dd1c28a60df0a05bff42f6a96267b` còn gán compat v16.2.4 cho boot beacon rỗng của daemon pre-v16.2.5. Với đúng base v16.2.5, nhánh này chủ yếu là safety net nếu inventory còn straggler cũ hơn; nó không phải lý do bỏ preflight version audit.

**Trước → sau.** Base có thể chặn promotion/upgrade hoặc gặp assertion trong một số FSMap cũ/standby-replay transition. Target chấp nhận các state hợp lệ hơn và phân loại damaged rank rõ hơn.

**Mixed-version.** Monitor target quản lý FSMap transition; active/standby MDS version và compat set quyết định promotion. Việc có code compatibility không bảo đảm mọi thứ tự rollout đều an toàn.

**Kiểm chứng.** Trước rollout xác nhận không có MDS pre-v16.2.5, không rank damaged, đủ standby và topology khớp plan. Canary failover một rank theo đúng orchestrator sequence; quan sát state `replay → resolve/reconnect → active`, client reconnect và FS health. Stop nếu rank vào `damaged`, compat không merge như dự kiến hoặc filesystem unavailable.

**Đánh giá.** Rủi ro **cao trong rolling/failover window**, confidence **high**.

### CEPHFS-003 — Journal/sessionmap replay được harden cho failover và blocklist races

**Evidence.** Các dòng `MDLog.*`, `journal.cc`, `SessionMap.*`, `Server.*`, journal helpers và QA failover/recovery map tới CEPHFS-003. Chuỗi chính:

- `5987e4d994101f1ff6a9573d2673a6d68ec97497`: sửa replay thread có thể block chờ wakeup;
- `261c5de3a1fab444275712d5c220621ccf76bade`: force replay sessionmap version khi log segment threshold chưa buộc persist;
- `c9ec50a3ead622b033cc2f8d2a9f9575bd1517a9`: xử lý JournalPointer save error khi daemon đang stop/blocklisted thay vì assert;
- `8a97339963680e46ea6a411323a69f733dfbdeef` và `0117f97e365e3e143a0831209efb23b1e229a9b1`: tránh journal/blocklist client sai thời điểm trong replay;
- `2465a7cb9d80de66adf06d72bd54ddba0d77603e` và `7243b680526f585e54df3ebe0e4a5f17b062f9b6`: sửa segment accounting và queue replay tiếp theo.

**Trước → sau.** Base có các đường hang/assert hoặc standby không thấy sessionmap version mới sau failover. Target đổi lock/wakeup, persistence và handling của request/client trong replay.

**Điều kiện.** Không phải on-disk format migration; tác động lộ ra khi active MDS restart/fail, standby replay journal và OSDMap blocklist thay đổi xen kẽ.

**Mixed-version.** Version của daemon đang replay quyết định behavior. Failover từ target sang base standby có thể quay lại base behavior, nên canary phải kiểm cả direction được phép trong rollout plan.

**Kiểm chứng.** Chạy workload metadata liên tục, fail active MDS có kiểm soát, xác nhận sessionmap version, journal replay progress, rank state và client request completion. Thu thập MDS log/stack nếu replay không tiến. Stop khi replay treo, rank damaged, session mất hoặc client request không hội tụ.

**Đánh giá.** Rủi ro **cao theo failover path**, confidence **high**.

### CEPHFS-004 — Request retry/forward 32 bit được feature-negotiate; session/caps vẫn cần mixed-client test

**Evidence.** `1c2334b778b18719fd259d44d60fc3cd8e19a2a4` thêm feature `CEPHFS_FEATURE_32BITS_RETRY_FWD`; `de4eba597007cae7bbdd7d2eca93d7e9db6d0242` và `2644fbdba5a10038f242f1bf55906eca9805acc7` chuyển client sang extended counters; `Client::build_client_request(request, mds)` chọn wire fields theo feature của session. `798cb2c306ec648d10cf14296de28f903df27e9d` refresh MDS feature bits mỗi session open và `9284c7aaa9a973b0be1cc6585b077371d98b49b6` notify client nếu session đã open.

Target cũng sửa cap/session correctness: delayed flush cho dirty caps/snapcaps (`10124022411a787cda8dd183a188f09784fb7355`), luôn gửi cap-revoke ack (`088543639362ba3773cb460fa967a771487b9423`) và giữ revoke trong list (`980ae9021a7308641a6276d4e24c557808782a75`). Unmount flush MDLog trước unsafe requests và chỉ chờ write MDS ops (`32b7d2794cceea1e628dcadd627d25072f59a26a`, `4667cb8b99ecb4eb1f71205f338931cba4460755`).

**Trước → sau.** Base bị giới hạn counter 8 bit và có nhiều reconnect/cap edge. Target quảng bá/đàm phán feature để giữ wire compatibility với MDS cũ, đồng thời harden cap flush/revoke.

**Giới hạn.** Đây là bằng chứng protocol negotiation, không phải tuyên bố mọi kernel/FUSE release đều tương thích. Các commit chặn retry/forward vượt 256 là guard cho pathological routing, không phải workload bình thường.

**Kiểm chứng.** Lập matrix kernel mount, ceph-fuse và libcephfs thực tế; kiểm base client ↔ target MDS và target client ↔ base MDS qua reconnect/failover, fsync, cap revoke và clean unmount. Stop nếu session feature không refresh, request loop/hang, dirty data không flush hoặc cap revoke không hoàn tất.

**Đánh giá.** Rủi ro **trung bình-cao trong mixed-client window**, confidence **high**.

### CEPHFS-005 — CVE-2022-0670 phụ thuộc lịch sử Manila và cần audit CephX riêng

**Evidence.** Advisory repository [CVE-2022-0670](../../ceph16.2.15/ceph/doc/security/CVE-2022-0670.rst) giới hạn phạm vi ở OpenStack Manila cung cấp native CephFS trên cluster đã nâng từ Nautilus hoặc cũ hơn; Pacific 16.2.10+ là fixed version. `1d7e95ba3a34436ea0dee4042dc41db884a283b4` sửa legacy subvolume discovery để không nhận nhầm/fabricate metadata path; `cf41172621f7462aef745ad72fb1a9b0512f11ad` sửa follow-up state; `5250508f45675b2552928bcef896ee4a8676c38b` thêm QA upgrade/import legacy.

**Trước → sau.** Trong deployment đúng điều kiện, base 16.2.5 có thể discover legacy subvolume sai và Manila user nhận CephX path restriction không đúng, cho phép truy cập phần khác của hierarchy. Target sửa discovery/metadata validation.

**Security boundary.** Nâng target không chứng minh key/caps đã cấp trước đây được thu hồi hoặc sửa. Advisory yêu cầu audit CephX keys. Không mở rộng kết luận sang NFS-Ganesha hoặc Manila dùng protocol khác nếu không có cùng native-CephFS path.

**Kiểm chứng/hành động.** Xác minh upgrade history và Manila share protocol. Nếu áp dụng, inventory auth entities do Manila tạo, so `allow rw path=...` với subvolume path canonical, rotate/revoke key sai theo runbook và chạy negative mount/read/write ngoài subvolume. Stop rollout/GO nếu còn key không map được owner/path hoặc negative access thành công.

**Đánh giá.** Rủi ro **cao, security**, confidence **high**.

### CEPHFS-006 — Volumes clone/purge có nhiều race và OSD-full edge được sửa

**Evidence.** `d49120cd5a8da516a8157ff58d2627198cc045a5` xóa stale clone index khi source snapshot không còn, tránh cloner loop/hang các clone sau; `ef373d8aea3133a15bb22ae62d97886b75eaca0c` khóa/check job để cancel không race rồi tiếp tục copy; `6016a9173221b550c7523d88a931c66b77a437f8` từ chối remove subvolume đang có operation. `3616d9284dd801838c3c38c298087155e0639739` serialize metadata read/write; `00f875794d44790ba1036a09dcac84d867436376` và `0a748bb10535a2858b97d6253a6277f38be7daa3` harden OSD-full paths; `baa82975a32c30a66df1a568989ec64b266429a0` dùng dedicated libcephfs handles cho async jobs.

**Trước → sau.** Base có thể giữ stale work item, tiếp tục clone sau cancel hoặc race metadata/config. Target cleanup/locking tốt hơn và trả lỗi rõ hơn trong failure paths.

**Activation/mixed-version.** MGR active chạy volumes module quyết định code path. Failover MGR giữa base/target trong lúc clone/purge là trạng thái cần kiểm, nhưng report không chứng minh operation đang chạy có thể migrate giữa versions mà không retry.

**Kiểm chứng.** Chọn disposable subvolume: clone, cancel ở nhiều timing, xóa source snapshot, failover active MGR và xác nhận job/index hội tụ; kiểm quota, snapshot retain và data checksum. OSD-full/force removal chỉ chạy trong lab. Stop nếu job treo, stale index tái xuất hiện, cancel vẫn copy hoặc metadata state không nhất quán.

**Đánh giá.** Rủi ro **cao theo volumes workflow**, confidence **high**.

### CEPHFS-007 — NFS export validation/caps thay đổi; RO động phụ thuộc Ganesha

**Evidence.** `5253e1b7fb899b50911f4d1578768323629e5d34` không cho tạo CephFS export tới path không tồn tại; `7fd370881287852788ec8e2177902d0456050a52` map exception khi kiểm directory. `e80b0b8e11e6be9ba125e796c4dde1b011374796` điều chỉnh caps của export cũ khi lệch. `62869f4c0972f366b1d7c70729459d6e7738142c` cho update động và tránh restart Ganesha trừ các field cần thiết; code giữ CephX FSAL cap `allow rw path=...` và dựa vào Ganesha để enforce read-only động. `5a5189163ca050c1823c1145fd9be36cdc0bb250` ngăn log FSAL keys.

**Trước → sau.** Base có thể tạo invalid export, giữ stale caps hoặc restart daemon cho nhiều update. Target validate path và update có chọn lọc hơn.

**Security/availability boundary.** Dynamic RO không đồng nghĩa CephX key đổi sang read-only; path restriction vẫn ở CephX, còn RO do Ganesha request layer. Vì vậy phải kiểm cả hai. Existing export chỉ đổi khi operation/import/apply tương ứng chạy; không tuyên bố cài binary tự rewrite mọi export.

**Kiểm chứng.** Export inventory gồm pseudo, backend path, FSAL user, access type và config RADOS object. Trên canary tạo invalid path (phải fail), đổi RW→RO, kiểm negative write qua NFS, kiểm direct CephX path scope và session continuity/reload. Stop nếu caps rộng hơn path, write qua RO thành công hoặc update gây outage ngoài dự kiến.

**Đánh giá.** Rủi ro **cao theo NFS quyền và update workflow**, confidence **high**.

### CEPHFS-008 — Mirror replayer restart/permission parity được harden

**Evidence.** `679a2e36cb0aac737203323f0a999b6b67ec1eb1` ngăn nhiều restart contexts chạy đồng thời; `6fc530dc42e3fed1396d8bf9979d89364e2b2b76` thay đổi restart handling cho failed/blocklisted replayer instances; `80f7f4e96ab06a0d0e8c1202d34cd407d0734771` đồng bộ mode của remote root trước snapshot sync. Mirror HA suites, `test_mirroring.py` và workunits map vào finding này.

**Trước → sau.** Target giảm duplicate recovery context và bổ sung permission parity. Đây không phải proof mọi replication lag/failover edge được giải quyết; restart logic chỉ được đánh giá từ endpoint/history, chưa fault-test tại đây.

**Mixed-version.** Daemon cephfs-mirror thực thi code local; MGR/FSMap giữ peer assignment. Khi hai cluster hoặc nhiều instances khác version, chọn một canary instance/peer và tránh simultaneous uncontrolled failover.

**Kiểm chứng.** Chụp peers, directory assignment, last synced snapshot và daemon perf/status; blocklist/restart canary trong lab, xác nhận chỉ một active replayer cho directory, lag hội tụ và data/mode/snapshot parity ở remote. Stop nếu duplicate replayer, failed instance không restart hoặc permission/data mismatch.

**Đánh giá.** Rủi ro **cao nếu mirroring bật**, confidence **medium-high**.

## 5. Trivial/support changes

- **129 support rows** gồm MDS/client/volume/NFS/mirror tests, upgrade suites và docs dùng để chứng minh tám finding; chúng chưa được chạy trong môi trường này.
- **267 trivial rows** gồm suite topology, marker/ignorelist rename, docs/feature maintenance, cephfs-top/shell/data-scan tooling, refactor và hunk không có causal chain upgrade riêng.
- **12 conditional + 59 mixed rows** được map tới CEPHFS-001…CEPHFS-008 trong CSV. Một file có thể map nhiều finding nên không cộng số occurrence ID để suy ra row total.

Tổng `12 conditional + 59 mixed + 129 support + 267 trivial = 467`; mọi owner row đã có disposition và reason.

## 6. Validation matrix đề xuất

| Scenario | Tiền điều kiện / pha | Quan sát bắt buộc | Stop condition |
| --- | --- | --- | --- |
| Topology/version inventory | Trước rollout | FSMap/MDSMap, rank, standby/replay, daemon/client versions | Có daemon quá cũ, rank damaged hoặc owner không rõ |
| Rolling MDS canary | Theo sequence report 08 | state transition, compat, replay progress, client reconnect | Rank damaged, FS unavailable hoặc replay không tiến |
| Session threshold | Lab/canary | session bytes, completed requests, eviction counter | Eviction storm hoặc MDS read-only |
| Mixed client/caps | Base/target kernel/FUSE/libcephfs | feature bits, retry, fsync, revoke, unmount | Hang, stale caps hoặc dirty data không flush |
| Manila/CephX audit | Chỉ khi CEPHFS-005 áp dụng | entity→subvolume path, negative access | Key không truy vết được hoặc path bypass |
| Volumes clone/cancel | Disposable subvolume | job/index, MGR failover, checksum | Clone/purge treo hoặc stale metadata/index |
| NFS export update | Ganesha canary | RADOS config, reload, CephX path, RW→RO negative write | Path cap rộng hoặc RO vẫn ghi được |
| Mirror fault recovery | Mirror canary | one replayer, restart, lag, data/mode parity | Duplicate/stuck replayer hoặc mismatch |

Các scenario là thiết kế kiểm chứng; chúng không ủy quyền blocklist production client, fail active rank tùy ý, force-remove subvolume hoặc rotate key ngoài change window.

## 7. Giới hạn và kết luận

- Chưa có As-Is nên chưa biết Manila native CephFS, NFS, volumes clone, standby-replay hoặc mirroring finding nào áp dụng.
- Tests/QA và advisory trong source tree đã được đọc nhưng chưa chạy; không có benchmark latency/throughput và không tuyên bố performance gain.
- CEPHFS-005 là historical security gate: current version alone không đủ kết luận an toàn.
- FSMap compatibility và replay fixes không thay thế orchestrator sequence, backup metadata hoặc tested rollback/abort criteria.
- Chưa đủ bằng chứng môi trường để đưa GO/NO-GO Production; gate tối thiểu là topology/version inventory, rolling MDS + mixed-client canary và các audit feature-specific nêu trên.
