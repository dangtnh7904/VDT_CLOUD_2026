# 07 — MGR, Dashboard, modules và monitoring: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **685 dòng** do owner `07-mgr-modules-monitoring` sở hữu. Có một gate ưu tiên cao: endpoint `v16.2.15` tái tạo nhiều `HELP/TYPE` cho cùng metric `ceph_pool_objects_repaired`; nếu Prometheus là nguồn tín hiệu stop/go thì phải chứng minh parser chấp nhận scrape trước khi cho target MGR làm active trong rollout.
>
> **Trạng thái kiểm chứng:** đã đọc net diff hai endpoint, code caller/callee, lịch sử commit, test và packaging trong repository. Chưa khởi động cluster, chưa chạy test Ceph, chưa scrape một MGR thật và máy phân tích không có `promtool`.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; hai source tree sạch, non-shallow; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [07-mgr-modules-monitoring.csv](./07-mgr-modules-monitoring.csv). CSV có 685 dòng, đúng thứ tự và đúng 21 cột nền của master inventory, sau đó nối 6 cột phân tích.
- Thống kê owner: `A190/M459/D30/R6`, `+216.964/-94.763`; `P1=558`, `P2=127`; không có file nhị phân.
- Riêng `src/pybind/mgr/dashboard/` chiếm 493 file và `+190.355/-82.899`. Churn này bị chi phối bởi frontend, package lock, locale, asset, test và feature work; số dòng không được dùng làm mức rủi ro.

Disposition cuối của toàn bộ 685 dòng là:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `material` | 2 | Runtime change trực tiếp và luôn đáng đưa vào kế hoạch |
| `conditional` | 19 | Chỉ ảnh hưởng khi module/workload/config tương ứng được dùng |
| `mixed` | 10 | Một file chứa cả hunk finding-relevant và hunk support/trivial |
| `support` | 183 | Test, docs, generated artifact hoặc code hỗ trợ finding |
| `trivial` | 471 | Đã sàng lọc nhưng không có causal chain upgrade độc lập |
| **Tổng** | **685** | Khớp chính xác CSV |

`P1/P2` là ưu tiên đọc ban đầu; disposition ở trên là kết luận sau phân tích. Một dòng có thể hỗ trợ nhiều finding, nên không cộng số dòng theo từng ID để suy ra tổng owner.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Gate Prometheus trước khi promote target MGR:** lấy output `/metrics` từ target active MGR và chạy qua `promtool check metrics` hoặc parser của một Prometheus staging. HTTP `200` không đủ; phải thấy scrape được parse và `up=1`. Nếu gặp duplicate `HELP/TYPE`, cần package có backport được xác minh hoặc một nguồn tín hiệu thay thế đã được phê duyệt trước khi tiếp tục dùng monitoring làm stop/go.
2. **Audit mọi module ngoài cây Ceph:** target chỉ queue event nằm trong `NOTIFY_TYPES`. Built-in modules đã được sửa, nhưng custom/third-party module kế thừa từ deployment không nằm trong repository này có thể im lặng mất callback nếu chưa khai báo.
3. **Chụp trạng thái autoscaler trước rollout:** lưu mode, flags, `target_size_ratio`, `pg_num_min/max`, recommendation và pending PG changes. Active MGR base/target có thể đưa ra hành vi khác nhau; không ghép một đợt thay đổi PG lớn vào cùng canary.
4. **Preflight TLS và đường failover Dashboard:** target đổi minimum mặc định từ TLS 1.2 lên TLS 1.3. Kiểm tra browser, reverse proxy, VIP/load balancer và automation bằng TLS 1.3 trước khi restart/promote MGR.
5. **Alert rules là một migration contract:** target thay bộ 18 alert name cũ bằng 58 alert name mới, không có tên trùng exact. Route, inhibition, silence và runbook theo `alertname` phải được map trước lần reload/redeploy monitoring stack.
6. **Nếu dùng CephFS stats/cephfs-top:** test parser với output schema version 2 và test MDS rank-0 failover. Nếu không dùng module `stats`/CephFS consumer, finding này không kích hoạt.

Không thấy migration on-disk hay one-way cluster feature do riêng owner 07. Điểm chuyển hành vi chính là **MGR nào đang active**, việc module nào được enable, và monitoring config nào thực sự được deploy/reload.

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro nếu kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| MGR-001 | Race/deadlock/assert và service-map hardening | Active MGR failover, daemon reconnect/report, OSD churn | mixed/failover | Trung bình-cao | High |
| MGR-002 | Per-module finisher; lịch sử TTL-cache deadlock | Module có command/notify; hoặc đi qua package 16.2.8 | mixed/module load | Trung bình | High |
| MGR-003 | `NOTIFY_TYPES` cho custom module | Có module ngoài upstream dùng `notify()` | activation/failover | Trung bình-cao | High |
| MGR-004 | PG autoscaler `bulk`, `noautoscale`, guards và step limit | Autoscaler/bulk pool đang dùng | mixed/stabilization | Trung bình-cao | High |
| MGR-005 | Duplicate Prometheus `HELP/TYPE` ở target endpoint | `pg_dump.pool_stats` có ít nhất một pool và endpoint được scrape | canary/full | **Cao; blocker cho monitoring gate** | High cho code path; runtime chưa chạy |
| MGR-006 | Metric schema/version labels/standby behavior | Prometheus/Grafana/rules dùng output MGR | mixed/failover | Trung bình-cao | High |
| MGR-007 | Dashboard TLS 1.3, redirect và API version | Dùng Dashboard/API qua client/proxy/VIP | restart/failover | Trung bình-cao | High |
| MGR-008 | CephFS perf-stats schema v2 và MDS failover | Dùng `stats`, cephfs-top hoặc parser riêng | mixed/failover | Trung bình-cao | High |
| MGR-009 | Progress module giảm full-PG dump | Recovery/backfill, nhất là cluster nhiều PG | mixed/stabilization | Thấp-trung bình | High |
| MGR-010 | ceph-mixin alert/rule migration | Package config được thay/reload hoặc cephadm redeploy | deploy/post-upgrade | Cao theo điều kiện | High |

Mức rủi ro là mức ảnh hưởng khi điều kiện đúng, không phải xác suất cluster cụ thể gặp lỗi.

## 4. Phát hiện chi tiết

### MGR-001 — Target harden đường active-MGR, daemon report và service-map failover

**Evidence.** Các dòng CSV `1468`, `1469`, `1477` trỏ tới [DaemonServer.cc](../../ceph16.2.15/ceph/src/mgr/DaemonServer.cc), `DaemonServer.h` và [Mgr.cc](../../ceph16.2.15/ceph/src/mgr/Mgr.cc). Lịch sử đích gồm:

- `d569f22d36b9ec48002e4a7d77cdd810a6dcfae8`: sửa race `exists()`/`get()` trong `DaemonServer::handle_report()` có thể dẫn tới assert.
- `355131defb8245ee360502ee08ff5b52479fc95c`: chuyển đăng ký OSD sang `ms_handle_accept`, tránh làm việc đó trong fast-auth path đang giữ messenger lock.
- `52609db711934dddd6f5357dcc8a662721c543fb`: bỏ giả định chỉ có đúng một service-map từ active MGR trước, tránh assert khi nhận nhiều epoch hợp lệ.
- `34000975471cb6a4a4f4397fa796454271caede2`: khóa đúng đường `MetadataUpdate::finish`.
- `ebcd948155a3b0c806cda4eadd04ce5c9f1860e4`: thêm peer/throttle policy cho `DaemonServer`.
- `8af250cf2f3d2b66c3e76f139dc1754edb6be6a5`: loại OSD vừa `out` vừa `down` khỏi daemon state, đồng thời tránh giữ cảnh báo slow-op cũ.

**Trước → sau.** Base có các cửa sổ race/lock/assert nói trên. Target chịu được daemon reconnect/report, metadata completion và nhiều service-map epoch tốt hơn. Đây là hardening availability/control-plane; không phải thay đổi định dạng dữ liệu.

**Activation và mixed phase.** Cluster chỉ có một active MGR tại một thời điểm, nên binary đang active quyết định behavior. Race có xác suất tăng trong promote/failback, OSD restart/reconnect, metadata refresh hoặc service-map churn — chính là các sự kiện thường xuất hiện trong rolling upgrade.

**Kiểm chứng/hành động.** Canary target standby rồi promote có kiểm soát; theo dõi MGR restart/assert, daemon reconnect, service-map epoch, stale slow-op health và thời gian API/module hồi phục. Thử failback về base trước khi rollout rộng nếu rollback MGR nằm trong runbook.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**. Target chủ yếu giảm lỗi; rủi ro vận hành nằm ở việc failover làm lộ path này và ở tín hiệu health thay đổi.

### MGR-002 — Mỗi module có finisher riêng; đừng diễn giải sai lịch sử TTL-cache

**Evidence.** Commit `39c5772e667b272f66ceff8e46151167a9dc5b39` tạo một finisher cho mỗi active Python module thay vì để command/notify cùng đi qua một queue tổng. Workunit `qa/workunits/mgr/test_per_module_finisher.sh` được thêm ở `2e8adcd7c8322d33a6eb45f3696c3c390f0d633b`. Các dòng chính là `1462`–`1465`, `1468`, `1485`; build/GIL/formatter/cache/perf support nằm ở `1466`, `1470`, `1481`–`1489`.

**Trước → sau.** Ở base, một callback module chậm có thể tạo head-of-line blocking cho module khác. Target queue command/notify vào finisher của đúng module, giảm coupling và lock-cycle surface. `config_notify()` cũng dùng per-module finisher.

**TTL-cache nuance.** Commit `a356bac1a8789fd3da2b071cb4cb801bc941244e` đưa TTL cache vào một bản Pacific trung gian và từng tạo lock/GIL deadlock. Backport Pacific `99de9e0215e4c7e860ab29f993606565a257e76d` sửa lỗi đó; fix có trong `v16.2.9` và endpoint `v16.2.15`. Base `v16.2.5` chưa chứa feature/regression, nên không được viết rằng target sửa một lỗi tồn tại ở baseline. `mgr_ttl_cache_expire_seconds` ở target mặc định `0`, tức cache tắt nếu operator không bật.

**Activation và mixed phase.** Per-module finisher có hiệu lực khi target MGR làm active và module xử lý command/notify. TTL path chỉ đáng chú ý nếu operator bật cache hoặc quy trình package đi qua `v16.2.8`; một bước nhảy trực tiếp tới endpoint đã chứa fix không mang regression trung gian đó vào trạng thái cuối.

**Kiểm chứng/hành động.** Chọn ít nhất hai module, cố tình làm một callback chậm trong staging và xác nhận module khác vẫn phản hồi; theo dõi finisher backlog/thread. Pin đúng endpoint package và tránh dừng rollout ở `16.2.8`. Nếu muốn bật TTL cache vì cluster lớn, benchmark riêng sau upgrade thay vì thay knob đồng thời với canary.

**Đánh giá.** Rủi ro **trung bình**, confidence **high**. Đây chủ yếu là availability improvement; historical deadlock là release-selection guard, không phải lỗi còn lại ở target.

### MGR-003 — Custom/third-party module phải khai báo `NOTIFY_TYPES`

**Evidence.** `900c502a996a13b00634e3753fb964bbbab3c01b` thêm enum `NotifyType`; `896ad0093124a8619f0dc4c4ce66796de9587365` annotate các built-in module; `7a8d07117e146d5123fb47ebb20a23c4a34bae89` chỉ queue event module yêu cầu; `5a93dba4257033abf700b0a82550debf2f2bd970` ngừng phát loại event không module nào tiêu thụ. Code nằm ở `PyModule::load_notify_types()`, `PyModuleRegistry::should_notify()` và `ActivePyModules::notify_all()`; API Python được mô tả trong [mgr_module.py](../../ceph16.2.15/ceph/src/pybind/mgr/mgr_module.py).

Target upstream đã thêm declaration cho Dashboard, devicehealth, insights, k8sevents, localpool, mds_autoscaler, restful, stats và các module thuộc owner khác. `NotifyType` kế thừa `str`, nên callback đã được gọi vẫn tương thích tốt với phần lớn so sánh chuỗi.

**Trước → sau.** Base fan-out notification rộng hơn. Target gọi `notify()` chỉ khi loại event có trong `NOTIFY_TYPES`. Module custom có method `notify()` nhưng không có declaration có thể load với notify set rỗng/log lỗi và không còn nhận event; đây là silent behavior change nguy hiểm hơn một lỗi import rõ ràng.

**Activation và mixed phase.** Chỉ target active MGR áp dụng gate. Failover base ↔ target có thể làm cùng module lúc nhận, lúc mất event. Module polling-only hoặc không override `notify()` không bị ảnh hưởng.

**Kiểm chứng/hành động.** Inventory toàn bộ `mgr module ls`, package/site path và module được mount/copy ngoài source Ceph. Với mỗi override `notify()`, khai báo đúng subset enum target: `NotifyType.mon_map`, `pg_summary`, `health`, `clog`, `osd_map`, `fs_map` hoặc `command`; test một event thật và log callback sau promote/failback. `service_map` không phải member khả dụng ở endpoint này. Không dùng một danh sách “all” tự chế vì mục tiêu thay đổi là giảm fan-out.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high** cho API/gating; applicability chưa biết vì chưa có inventory module của cluster.

### MGR-004 — Endpoint autoscaler dùng `bulk`/`noautoscale` và thêm nhiều guard

**Evidence.** Dòng `2188` là [pg_autoscaler/module.py](../../ceph16.2.15/ceph/src/pybind/mgr/pg_autoscaler/module.py); `2187`, `2189`–`2192` là support/tests. Endpoint target có:

- `d41ef37be9be70d242296d8b6b83ed3af4b4b588`: pool mới có cờ `--bulk`; default `osd_pool_default_flag_bulk=false`.
- `6589dee8ca64cd0287a0028c0d5afdef43509d33`: global `noautoscale` control, mặc định không bật.
- `a29565511b206f67975c266e7a9ec5b8d00cd5e3`: không scale pool có CRUSH roots chồng lấn.
- `8d83b6746ac07aa8770f4aa8d911d5635db31ead`: tôn trọng `pg_num_max`.
- `b5edb374605c02a670d8c627bc9b5bb2b66ca340`: giới hạn một bước đổi PG theo `mgr_max_pg_num_change=128`.
- Các commit tiếp theo sửa warning/order/report để không hiện `NEW PG_NUM` khi mode không thực thi.

Một ý tưởng `autoscale-profile` từng xuất hiện giữa lịch sử rồi bị loại; nó **không phải API endpoint `v16.2.15`**. Kế hoạch chỉ nên dựa trên `bulk`, `noautoscale`, pool autoscale mode và các giới hạn cuối cùng.

**Trước → sau.** Target có thêm cách đánh dấu pool dự kiến lớn, một maintenance control toàn cục và guard tránh proposal không hợp lệ/quá lớn. Điều này có thể đổi recommendation hoặc nhịp hội tụ, nhưng upgrade tự nó không buộc mọi pool đổi `pg_num` nếu mode/flags không cho phép action.

**Activation và mixed phase.** Active MGR tính recommendation/action. Sau failover base ↔ target, cùng OSDMap có thể được diễn giải khác ở các edge mới. Tác động tăng khi pool ở `on`, có target ratio/bulk flag, đang gần `pg_num_max`, hoặc topology có overlapping roots.

**Kiểm chứng/hành động.** Trước rollout lưu `ceph osd pool autoscale-status`, pool flags/mode, target ratio, `pg_num_min/max` và pending recommendation. Trong canary, freeze các thay đổi PG không cần thiết hoặc dùng maintenance control theo runbook đã test; sau rollout phải unset/verify rõ ràng. So sánh recommendation trước/sau từng lần active MGR đổi, không dùng riêng Dashboard display làm nguồn quyết định.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**.

### MGR-005 — `v16.2.15` tái tạo duplicate `HELP/TYPE` cho `ceph_pool_objects_repaired`

**Evidence endpoint.** Dòng CSV `2195` là [prometheus/module.py](../../ceph16.2.15/ceph/src/pybind/mgr/prometheus/module.py):

1. `_setup_static_metrics()` ở target tạo key `metrics['pool_objects_repaired']` với exposition name `pool_objects_repaired` và label `pool_id`.
2. `get_pool_repaired_objects()` lặp `pg_dump['pool_stats']`, tạo thêm key dictionary `pool_objects_repaired<poolid>` cho **mỗi pool**, nhưng mọi object lại có cùng exposition name `pool_objects_repaired` và label `poolid`.
3. `Metric.str_expfmt()` luôn sinh `# HELP` và `# TYPE`, kể cả object chưa có sample.
4. `collect()` gọi `get_pool_repaired_objects()` rồi format **mọi** `self.metrics.values()`.

Vì vậy, ngay khi `pool_stats` có ít nhất một pool, output có static metric cộng một dynamic metric cùng tên `ceph_pool_objects_repaired`: ít nhất hai `HELP` và hai `TYPE`, đồng thời label spelling cũng lệch `pool_id`/`poolid`.

**Lịch sử chứng minh đây là regression endpoint.** `d3b4d7cbb4a01f58f257cc09c41c2c8e7984901c` từng sửa tracker 59505 bằng cách gom sample vào một static metric; commit message ghi chính lỗi parser “second HELP line”. Commit muộn hơn `df692c44c6b8ce3e77631e1d9170ffc00245b5c1` lại tạo per-pool `Metric` khi rename `pg_repaired_objects` → `pool_repaired_objects`. Cả hai commit đều là ancestor của target, và code cuối target mang lại pattern đã được commit trước đó sửa. Base `v16.2.5` chưa export metric này, nên đây là khác biệt thật giữa hai endpoint chứ không phải lỗi chỉ tồn tại ở bản trung gian.

**Tác động.** MGR HTTP handler có thể vẫn trả `200`, nhưng Prometheus text parser có thể từ chối toàn scrape. Khi đó alert, recording rule và Dashboard dựa vào target MGR mất dữ liệu đúng lúc rollout cần quan sát nhất. Test `src/pybind/mgr/prometheus/test_module.py` không có regression case cho `pool_objects_repaired`/duplicate metadata.

**Gate bắt buộc nếu dùng Prometheus.** Sau khi target MGR active trên staging/canary:

```bash
curl -fsS http://TARGET_MGR:9283/metrics | promtool check metrics
```

Đồng thời kiểm tra Prometheus target state, `up`, scrape error log và một tập golden queries. Nếu parser lỗi, không dùng endpoint đó làm stop/go. Yêu cầu vendor package/backport có code endpoint được đối chiếu và test parser; hoặc dùng nguồn tín hiệu độc lập đã được phê duyệt. Báo cáo không xác nhận một config workaround an toàn cho lỗi format này.

**Đánh giá.** Rủi ro **cao** và là **blocker cho monitoring gate**, confidence **high** về code path/lịch sử. Chưa chạy runtime parser nên kết luận hệ thống cụ thể vẫn cần gate trên.

### MGR-006 — Metric/schema và standby contract thay đổi trong mixed version

**Evidence.** `45a8604232bd772a8da88c45c4f9934e063db0e4` và bản áp dụng cuối `f4e16fd0b89c9ffc69787f776727c3c0c63159ee` sửa việc daemon trên cùng host bị gán nhãn `ceph_version` của service khác: target đưa version vào từng service trong `ActivePyModules::dump_server()`, rồi Prometheus đọc từng service. Đây là sửa quan trọng khi host chứa daemon base và target trong partial upgrade.

Các net changes khác gồm pool read/write gauge → counter (`46ae4d7e91c76be675811c1194c8d983aa092719`), method stats, health-detail history, human disk occupation, zero-valued PG-state series (`8586514ab0c433f078ff2651c6b6bb7f9068445b`), RBD pool de-duplication và daemon slow-op health (`2b32cc3c3d6fac572f5e5c0183f519527011d9ce`). Generated ceph-mixin/Grafana files trong CSV là support cho query contract này.

Target cũng làm standby Prometheus discoverable (`24e843a075a74daf4708f51e2a2f050d2f8c1a47`) và thêm option (`305648a2a13ec94fa5dc0b55bd6166f975360de9`): với default, `/` trên standby trỏ người đọc tới active URI còn `/metrics` trả body rỗng. `standby_behaviour=error` chỉ làm route `/` trả HTTP error có code cấu hình; route `/metrics` trên standby vẫn trả `200` với body rỗng.

**Tác động/mixed phase.** Active MGR quyết định schema và value. Query/rule giả định series luôn tồn tại, kiểu cũ hoặc host-level version có thể cho kết quả khác khi active đổi. Scraper trỏ vòng qua mọi MGR mà không phân biệt active có thể nhận body rỗng từ standby và tạo tín hiệu sai. Tuy nhiên phải xử lý MGR-005 trước: schema đúng không có ý nghĩa nếu toàn scrape bị parser loại.

**Kiểm chứng/hành động.** Chụp golden set metric names/types/labels ở base; canary target rồi diff exposition schema, query output, missing series và cardinality. Kiểm tra riêng mixed host để nhãn version đúng từng daemon. Nếu dùng `standby_behaviour=error`, load balancer phải health-check route `/`; scrape/health-check riêng `/metrics` không tự loại standby vì vẫn nhận `200`. Không chỉ nhìn HTTP status: xác nhận target được chọn là active và body có series mong đợi.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**.

### MGR-007 — Dashboard mặc định TLS 1.3; redirect/API compatibility được harden

**Evidence.** Base đặt `SSLContext.minimum_version=TLSv1_2`. Commit `755f33a94ae0e88474b2adff1964a627c0139599` đổi target mặc định thành TLS 1.3; `cfe4a6e4aff5f91ddbc28d655d37235f52a3f969` thêm `UNSAFE_TLS_v1_2=false` để cho phép hạ lại minimum khi có chấp thuận rủi ro. Target code nằm ở [dashboard/module.py](../../ceph16.2.15/ceph/src/pybind/mgr/dashboard/module.py):183–188 và [dashboard/settings.py](../../ceph16.2.15/ceph/src/pybind/mgr/dashboard/settings.py):121.

`badc70bb11fc...` sửa redirect từ standby tới active bằng URL builder; các thay đổi wildcard bind/IPv6/hostname giảm URI lỗi sau failover. API version framework (`c3152...`) đưa MIME version về object rõ ràng; `1eb908...` cho minor version mới phục vụ client minor cũ cùng major. Controller split, `test_versioning.py`, frontend `HostService`, `CdHelperClass` và interceptor trong CSV là evidence support, không phải một rủi ro mới cho từng controller.

**Trước → sau.** Client/proxy chỉ hỗ trợ TLS 1.2 có thể kết nối base nhưng thất bại sau khi Dashboard target khởi động. Ngược lại, version negotiation và redirect target được làm rõ hơn. Option TLS 1.2 mang tên `UNSAFE`; nó là compatibility escape hatch, không phải default khuyến nghị.

**Activation và mixed phase.** SSL context được tạo khi server khởi động, nên thay đổi lộ ra ở restart/promote target MGR. Active flip có thể luân phiên TLS minimum và URL behavior nếu VIP/LB đi thẳng tới MGR instances.

**Kiểm chứng/hành động.** Trước rollout kiểm tra TLS 1.3 từ browser, reverse proxy, API client, certificate chain/SNI và VIP. Trong canary test direct active, direct standby và qua LB; test login/session, redirect sau failover và API `Accept` version. Chỉ bật TLS 1.2 sau đánh giá security và phải restart/retest endpoint.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**. Owner set không có direct test chứng minh minimum TLS 1.3 end-to-end.

### MGR-008 — CephFS perf stats đổi schema v2 và bền hơn qua MDS failover

**Evidence.** Các dòng `1471`–`1476`, `1631`, `2169`, `2212`, `2213` bao phủ MDS/metric collectors và [stats/fs/perf_stats.py](../../ceph16.2.15/ceph/src/pybind/mgr/stats/fs/perf_stats.py). Target đặt `PERF_STATS_VERSION = 2`; `402c8cda8038a62fe2ee24e4d02db9b94025e646` đổi cấu trúc output, các commit tiếp theo thêm filesystem/client metadata và counters. `3c5fe2d1e3985775c7cb4697658169831765f7dc` đăng ký lại query khi rank-0 MDS offline/failover; `f7b1f7d4392...` tránh crash ở `limit=null`.

**Trước → sau.** Consumer mong JSON v1/shape phẳng có thể parse sai hoặc mất field khi active MGR target phục vụ schema v2. Target lại cải thiện freshness sau rank-0 failover vì query được dựng lại. Built-in tooling cùng target có thể tương thích, nhưng script/collector ngoài repository phải được kiểm tra riêng.

**Activation và mixed phase.** Chỉ áp dụng khi module `stats`/CephFS perf query được dùng. Active MGR base/target quyết định schema; MDS rank failover kích hoạt re-registration path.

**Kiểm chứng/hành động.** Lưu golden JSON base, chạy parser/cephfs-top thực tế với target, kiểm tra `version=2`, nhiều filesystem/client và counters. Sau đó failover rank 0, xác nhận metric tiếp tục cập nhật, không chỉ command trả thành công.

**Đánh giá.** Rủi ro **trung bình-cao theo điều kiện**, confidence **high**.

### MGR-009 — Progress module giảm tải khi recovery nhưng không nên là tín hiệu duy nhất

**Evidence.** Dòng `2193`/`2194`: `f8f4c40275ae22aa3177ef693f26ef804a498ddd` tối ưu global recovery event; `2cdf2950e84f91c014e96e72ce2b08bd78aebbad` tránh dump toàn bộ PG stats; các commit sau thêm interval 5 giây và sửa race trên event dictionary. Target dùng `active_clean_pgs`/`pg_progress` compact inputs thay vì phản ứng bằng full dump ở mỗi notification.

**Trước → sau.** Trên cluster nhiều PG hoặc đang recovery, target giảm CPU/data-copy pressure lên MGR. Đổi polling/event timing có thể làm display tiến độ khác nhịp với base; nó không đổi recovery correctness của OSD.

**Activation và mixed phase.** Module `progress` phải bật và cluster có recovery/backfill. Active MGR version quyết định cách tổng hợp; sau failover event cache được dựng lại.

**Kiểm chứng/hành động.** Trong canary recovery an toàn, so `ceph progress` với PG-state/OSD recovery counters và MGR CPU/RSS; test active-MGR failover giữa event. Không dùng `ceph progress` một mình làm tiêu chí hoàn tất recovery.

**Đánh giá.** Rủi ro **thấp-trung bình**, confidence **high**; thay đổi chủ yếu là scalability improvement.

### MGR-010 — ceph-mixin thay toàn bộ alert-name contract đang ship

**Evidence.** Base `monitoring/prometheus/alerts/ceph_default_alerts.yml` có **18** giá trị `alertname`; target `monitoring/ceph-mixin/prometheus_alerts.yml` có **58** và intersection exact bằng **0**. Ví dụ target có `CephMgrModuleCrash`, `CephMgrPrometheusModuleInactive`, `CephPGUnavilableBlockingIO` (giữ đúng spelling trong file), `CephDaemonSlowOps` và `CephadmUpgradeFailed`; base dùng các tên dạng `health error`, `OSD down`, `Slow OSD Ops`.

Target package vẫn đưa generated file về cùng path `/etc/prometheus/ceph/ceph_default_alerts.yml`: `debian/rules:64`, `ceph.spec.in:1437`; RPM đánh dấu `%config` ở `ceph.spec.in:2490`. Cephadm bind-mount source mới vào cùng path ở `src/cephadm/cephadm:2769`, và module dùng path đó làm default. Vì vậy source đổi không đồng nghĩa rule đang chạy đã đổi: package manager có thể giữ local config, còn cephadm cần redeploy/reconfig và Prometheus cần reload.

**Tác động.** Alertmanager route/inhibition/silence, ticket automation và runbook match exact `alertname` có thể ngừng match hoặc match sai sau activation. Bộ rule target rộng hơn, nên threshold/for-duration/cardinality và notification volume cũng cần baseline lại. Tests `monitoring/ceph-mixin/tests_alerts` kiểm tra syntax/unit fixtures, không biết route/silence riêng của deployment.

**Activation và cross-report.** Finding chỉ kích hoạt khi file runtime thực sự được thay rồi reload. Với cephadm, thời điểm redeploy monitoring stack thuộc report 08; report này chỉ chốt rule contract. MGR-005 phải pass trước khi kỳ vọng các rule Ceph đánh giá được target scrape.

**Kiểm chứng/hành động.** Export running rules và Alertmanager config trước upgrade; lập map 18 tên cũ → rule target hoặc quyết định deprecate. Chạy rule syntax/unit check, staging rule evaluation, route/inhibition simulation và một alert injection có kiểm soát. Sau deploy xác nhận checksum/runtime rule, reload success, pending/firing behavior và notification destination — không chỉ kiểm tra file trên disk.

**Đánh giá.** Rủi ro **cao theo điều kiện**, confidence **high**.

## 5. Gate theo pha rollout

| Pha | Gate tối thiểu | Tín hiệu pass |
| --- | --- | --- |
| Preflight | Inventory custom MGR modules; TLS clients/proxies; autoscaler state; running rules/routes; golden metrics/API/CephFS output | Có owner và rollback cho từng dependency; không còn module `notify()` chưa audit |
| Target standby | Module load/can-run, service URI, config parity, no restart loop | Standby ổn định; module custom import/load; active base không bị nhiễu |
| Promote target canary | Prometheus parser trước tiên; Dashboard TLS/API/redirect; notify callback; autoscaler diff; progress | `promtool`/staging scrape pass, `up=1`; UI/API và event delivery pass; không có PG action bất ngờ |
| Failover/failback rehearsal | Đổi active target ↔ base và kiểm tra service-map, endpoint, schema, cache/event rebuilding | Không assert/deadlock; LB tìm đúng active; operator biết schema nào đang phục vụ |
| Full target | Monitoring rule deploy/reload có kiểm soát; CephFS rank failover nếu dùng; baseline MGR load | Runtime rules đúng checksum, routes/silences đã map; queries và alerts hoạt động |

Nếu gate Prometheus fail, các Dashboard panel/alert dựa trên cùng scrape không được dùng để “chứng minh” rollout khỏe.

## 6. Test đã đọc và khoảng trống bằng chứng

Đã đọc test/workunit liên quan per-module finisher, TTL cache, autoscaler ratio/overlapping roots, progress, Dashboard API version/settings, Prometheus module và ceph-mixin rules/dashboards. Chúng được ghi `support` trong CSV, không được diễn giải như runtime validation đã chạy.

Các khoảng trống quan trọng:

- Không có test owner 07 bắt duplicate `HELP/TYPE` cho `pool_objects_repaired`; chưa chạy `promtool` vì binary không có trên máy phân tích.
- Không có end-to-end test direct cho default Dashboard TLS 1.3 với proxy/client thật.
- Upstream tests không thể bao phủ custom/third-party MGR modules của deployment.
- Chưa có mixed-version cluster thật để đo active failover, notification delivery, Prometheus cardinality, MGR CPU/RSS hoặc progress timing.
- Chưa có running Alertmanager routes/silences, autoscaler state hay CephFS consumers của cluster đích.

Do đó báo cáo đủ để tạo gate và kịch bản test, chưa đủ để kết luận cluster cụ thể GO/NO-GO.

## 7. Phần diff không được nâng thành finding

471 dòng `trivial` chủ yếu là Dashboard frontend feature/UI, Angular/package-lock, locale, style, fixture, test feature, CLI API phụ, module feature không có activation edge, docs biên tập và SNMP artifact mới. Chúng vẫn ở CSV với reason/evidence status từng dòng.

183 dòng `support` bao gồm controller split cho API versioning, test/docs, generated ceph-mixin/Grafana dashboards, rule generators và built-in module annotations. Chúng hỗ trợ 10 finding nhưng không phải 183 rủi ro riêng. Hai dòng `MgrClient.cc/.h` map `MSG-009` để cross-reference message edge đã phân tích ở report 05, tránh nhân đôi kết luận.

Không có dòng nào bị bỏ khỏi owner set; `material 2 + conditional 19 + mixed 10 + support 183 + trivial 471 = 685`.

## 8. Kết luận

Target MGR có nhiều hardening đáng giá cho failover, module isolation, autoscaler guards, progress scalability và CephFS metrics. Tuy nhiên, monitoring không thể mặc định coi là “nâng cấp xong sẽ tốt hơn”: endpoint code cuối `v16.2.15` có một regression format Prometheus có bằng chứng lịch sử trực tiếp, alert-name contract được thay toàn bộ, Dashboard nâng TLS minimum và custom module notification trở thành opt-in.

Kế hoạch an toàn là promote một target MGR canary, **parse scrape trước**, rồi lần lượt kiểm chứng module events, TLS/API, autoscaler và consumer-specific schemas. Chỉ sau đó mới reload/redeploy alert rules và mở rộng rollout.
