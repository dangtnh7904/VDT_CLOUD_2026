# 08 — cephadm/orchestrator, lifecycle và upgrade workflow: v16.2.15 → v17.2.7

**Trạng thái: đã hoàn tất binary gate của owner; lab/canary còn mở.** [CSV đầy đủ của owner](./08-cephadm-orchestrator.csv) có 134 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 95`, `trivial = 39`, **chưa phân loại = 0**; `95 + 39 = 134`, không còn hàng trống.

## Phạm vi và phương pháp

Owner này phụ trách cephadm/orchestrator, lifecycle và upgrade workflow. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### ADM-001 — Offline host làm upgrade dừng với health signal riêng

**CSV:** `src/pybind/mgr/cephadm/upgrade.py`. Base `_do_upgrade()` chưa kiểm `offline_hosts` ở đầu và `upgrade_tick()` bắt lỗi chung; target kiểm tập offline trước khi tiến hành, ném `HostConnectionError` và `upgrade_tick()` chuyển thành `UPGRADE_OFFLINE_HOST` với host/address. `upgrade_resume()` còn xóa upgrade health warning cũ. Commit liên quan `3787501849be5a9ce72c3df2f9ad536e21780684`, `a5f6cdef4bce7295a8a1f7a032ae92fca0ae52cf`. `src/pybind/mgr/cephadm/tests/test_upgrade.py` có tests start/do-upgrade khi host offline và resume warning; đã đọc nhưng chưa chạy.

**Điều kiện:** cluster dùng cephadm và host được đánh dấu offline hoặc SSH lỗi trong lúc rollout. Trong mixed-version MGR Pacific điều phối theo đường cũ; khi MGR target active, lỗi có signal riêng và upgrade dừng sớm để operator xử lý host. Sau full upgrade behavior target đồng nhất. Không tự suy host offline có hay không từ repo. **Evidence confidence:** high cho code/test, medium cho applicability cluster. **Kiểm chứng:** trong lab có host giả lập offline, xác nhận `UPGRADE_OFFLINE_HOST`, trạng thái pause/fail và `resume` sau khi khôi phục kết nối; quan sát `ceph orch upgrade status`, health, host cache. Không gây mất kết nối production để thử.

### ADM-002 — Cách xác định daemon đã ở target image phụ thuộc `use_repo_digest`

**CSV:** cùng `upgrade.py`. Base `_detect_need_upgrade()` so container digest với target digest. Target phân nhánh: khi `use_repo_digest=true` (default ở hai endpoint), so digest; khi false, so `container_image_name` với target name. `target_image` cũng trả digest hoặc name theo option. Commit `bf8820d449d1076fd3b0fb4c10c50823ed4d0f85`. `test_upgrade_run` trong `tests/test_upgrade.py` parametrizes cả hai giá trị option, nhưng chưa chạy trên môi trường này.

**Điều kiện:** cephadm upgrade và option `use_repo_digest` được đặt; đặc biệt nếu false, tag/name có thể là mutable, vì vậy kết quả `need_upgrade`/completion dựa theo tên chứ không xác minh nội dung qua digest ở nhánh đó. Trong mixed rollout active MGR phiên bản khác nhau có thể phân loại daemon theo logic khác; sau full target MGR logic theo option target. **Evidence confidence:** high cho branch code, medium cho artifact thực tế. **Kiểm chứng:** pin target artifact bằng digest khi cần tính tái lập; trong lab so `ceph orch ps` image name, repo digest, deployed_by trên từng cohort và trạng thái complete theo cả hai mode. Không kết luận image là đúng chỉ từ tag trùng.

**Cross-reference:** cephadm sau OSD phase có `_complete_osd_upgrade` gọi `osd require-osd-release`; guard/rollback checkpoint thuộc [MON-001](./04-mon-osdmap-crush.md). Method này có ở cả hai endpoint, nên không dùng nó làm bằng chứng riêng cho một hunk `upgrade.py`.

### ADM-003 — Device inventory chuyển sang các config-key riêng

**CSV:** `src/pybind/mgr/cephadm/inventory.py`. Pacific `HostCache.load()` đọc `devices` trong `host.<hostname>`, còn `save_host()` ghi danh sách vào cùng bản ghi. Quincy đọc cả danh sách cũ lẫn `host.<hostname>.devices.<index>`, rồi ghi device inventory ở các key riêng; `save_host_devices()` chia danh sách theo `mon_config_key_max_entry_size`. `HostCache.load()` giữ các key device hợp lệ thay vì xóa như stray host. Commit liên quan `f9cf5f1316e` (store device info separately). Đây là đổi định dạng trạng thái persisted của MGR, không chỉ đổi cách tổ chức code.

**Điều kiện:** cluster quản lý OSD bằng cephadm, nhất là host có inventory lớn hoặc MGR failover/restart trong rollout. MGR Quincy đọc cache Pacific khi lần đầu lên target; trong mixed MGR, MGR Pacific không đọc key device mới nên sau rollback/failover về Pacific có thể phải refresh inventory và cần kiểm chứng trước khi chạy drive-group. Sau full Quincy, cache mới được đọc theo nhiều key. Khả năng rollback nêu ở đây là suy luận từ hai hàm đọc, không phải kết quả lab. **Evidence confidence:** high cho định dạng code, medium cho hậu quả rollback thực tế. **Kiểm chứng:** lab lưu cache với Pacific, bật MGR Quincy rồi failover về Pacific; so `ceph orch device ls`, số device/key và OSD preview trước/sau, đặc biệt host có inventory vượt giới hạn một config-key. Không chạy apply drive-group trên thiết bị production để thử.

### ADM-004 — Host đang drain không còn là lỗi unknown trong explicit placement

**CSV:** `src/pybind/mgr/cephadm/schedule.py`, `migrations.py`, `inventory.py`. Pacific `HostAssignment` chỉ nhận unreachable hosts và kiểm danh sách explicit với host có thể chọn; Quincy nhận thêm `draining_hosts`, coi chúng là host đã biết khi validate nhưng loại khỏi candidate placement. `Migrations.migrate_0_1()` truyền danh sách draining khi chuyển spec sang explicit placement cho scheduler mới. Unit test `tests/test_scheduling.py` thêm case host `_no_schedule` trong explicit placement. Commit `ccdc075ad97` mô tả fix cho trường hợp này; `4c1d47ee06d` thêm ưu tiên host đã có related-service daemon khi cần chọn host tùy ý. Hunk loopback trong cùng file cho phép subnet loopback khi tìm IP placement.

**Điều kiện:** spec liệt kê tường minh host có `_no_schedule`, hoặc migration scheduler 0→1 gặp host đang drain; các nhánh related-service/loopback chỉ áp dụng cho spec tương ứng. Khi MGR Pacific active, scheduler dùng logic Pacific; khi MGR Quincy active, host drain được giữ trong known set nhưng không nhận daemon mới. Sau full upgrade, logic target dùng nhất quán. **Evidence confidence:** high cho nhánh code/test, medium cho tác động trên topology thực tế. **Kiểm chứng:** lab đặt `_no_schedule` trên một host có trong explicit placement rồi so `ceph orch ls`, `ceph orch ps`, placement preview và daemon move khi chuyển active MGR; chạy migration scheduler trên spec mẫu và xác nhận không triển khai lên host drain.

### ADM-005 — Agent tùy chọn thay đường thu thập host metadata

**CSV:** `src/pybind/mgr/cephadm/agent.py`, `inventory.py`; context `module.py` và `serve.py` vẫn ở hàng chờ phân loại. Pacific không có endpoint `agent.py`. Quincy có endpoint HTTPS nhận metadata từ agent theo hostname/keyring/counter, `AgentCache` persist trạng thái qua MGR failover, và `HostCache` giữ cờ `metadata_up_to_date`. `CephadmServe` dùng agent khi `use_agent=true` và hoãn apply các spec khác agent nếu metadata của host reachable chưa cập nhật. `module.py` đặt default `use_agent=false`; do đó điều kiện bật option quyết định khả năng áp dụng. Các commit liên quan gồm `78983ad0d0c` (agent 2.0), `256ff1fb1cf` (agent cache), `e2643798a96` (upgrade to version with agent).

**Điều kiện:** chỉ cluster bật `mgr/cephadm/use_agent` hoặc thay option đó khi rollout; default false không kích hoạt luồng agent. Trong mixed rollout, active MGR Quincy có thể dùng agent và chờ metadata; active MGR Pacific không có luồng này. Sau full Quincy, nếu vẫn bật option, daemon agent và metadata freshness là điều kiện trước khi áp dụng service spec. **Evidence confidence:** high cho luồng code/default, medium cho tác động cluster. **Kiểm chứng:** lab với option bật/tắt, nâng active MGR, quan sát agent daemon, health và thời điểm spec được apply sau khi agent báo metadata; thử failover MGR và kiểm tra counter/cache tiếp tục hoạt động.

### ADM-006 — Tạo OSD qua cephadm chuyển sang async với timeout bao ngoài

**CSV:** `src/pybind/mgr/cephadm/services/osd.py`. Pacific chạy `create_from_spec_one()` qua `forall_hosts` và gọi ceph-volume đồng bộ; Quincy gom coroutine từng host bằng `asyncio.gather`, dùng `wait_async()` trong `async_timeout_handler`, và chuyển create/list/zap ceph-volume sang đường async. Commit `b97894f4cd6` và `2048eaac80f` nêu chuyển async/parallelization; `cb2b1f24d3c` nêu timeout chung cho SSH/cephadm. Đây là thay đổi đường triển khai OSD, không chứng minh tốc độ sẽ tốt hơn trong mọi cluster.

**Điều kiện:** apply OSDSpec, OSD replacement, preview hoặc zap khi MGR Quincy active. Trong mixed rollout, phiên bản active MGR quyết định đường orchestration; OSD daemon cũ không tự đổi chỉ vì đường điều phối mới. Sau full Quincy, thao tác OSD dùng timeout/exception của target. **Evidence confidence:** high cho đường code, medium cho latency/failure behavior trên hạ tầng. **Kiểm chứng:** lab dùng nhiều host và một host SSH chậm, xác nhận kết quả từng host, timeout, trạng thái `ceph orch osd rm`/OSD preview và không tạo trùng OSD sau retry; không dùng thiết bị production cho zap test.

### ADM-007 — Cephadm chuyển remote command sang asyncssh

**CSV:** `src/pybind/mgr/cephadm/ssh.py`, `offline_watcher.py`. Pacific watcher mở remoto connection qua `CephadmServe` rồi chạy `true`; Quincy gọi `SSHManager.check_execute_command()`. `SSHManager` mới tạo/cached asyncssh connection, chạy lệnh với `sudo` nếu cần, SCP file, reset kết nối lỗi và ném `HostConnectionError` kèm host/address. `module.py` khởi tạo manager này; `tests/test_ssh.py` mô phỏng các lỗi kết nối. `upgrade.py` dùng `HostConnectionError` để phát `UPGRADE_OFFLINE_HOST` như ADM-001. Đường remote deployment tổng thể trong `serve.py` còn chờ phân loại riêng.

**Điều kiện:** cephadm điều phối host qua SSH khi active MGR Quincy, gồm kiểm tra host offline và upgrade. Trong mixed rollout, chuyển active MGR thay transport; sau full target đường asyncssh áp dụng nhất quán. **Evidence confidence:** high cho code/call site, medium cho tính tương thích với SSH config cụ thể. **Kiểm chứng:** lab kiểm root và non-root SSH, custom config/key, host unreachable/reconnect, check-host và trạng thái `ceph orch host ls`/upgrade health; xác nhận timeout và log đủ để chẩn đoán, không dựa riêng vào ping.

### ADM-008 — QA cephadm đổi điều kiện chấp nhận upgrade và OSD workflow

**CSV:** các selector/recipe trong `qa/suites/orch/cephadm/upgrade`, `smoke/agent`, `smoke/start.yaml` và `osds/2-ops`. Pacific `upgrade/5-upgrade-ls.yaml` tìm bản 16.2.0 từ lệnh `ceph orch upgrade ls --image` mặc định; Quincy thêm `--show-all-versions`. `upgrade/3-upgrade/simple.yaml` đặt `log_to_journald false` trước `upgrade start`; `upgrade/agent` mới đưa hai biến thể `use_agent` vào suite. Các recipe wait, smoke start và năm OSD operation xóa `log-ignorelist` cho MON/OSD/PG (một case còn có stray daemon), nên bộ test không còn bỏ qua những dòng health tương ứng. Đây là thay đổi **validation coverage/acceptance**, không phải bằng chứng rằng cluster production sẽ không phát health warning.

**Điều kiện:** chạy đúng cephadm QA suite trên target hoặc dùng nó làm chuẩn canary/acceptance. Trong mixed-version, matrix agent on/off có thể phát hiện đường metadata của active MGR Quincy và đường SSH fallback; sau full upgrade, lệnh `upgrade ls` và thao tác OSD được kiểm theo target recipe. **Evidence confidence:** high cho YAML/selector diff, medium cho tác động tới kết quả QA vì chưa chạy suite. **Kiểm chứng:** chạy matrix agent on/off cùng upgrade/OSD recipes ở lab, giữ artifact health/log và kết quả từng case; xác nhận `--show-all-versions` thật sự liệt kê bản cũ cần assertion. Khi so baseline Pacific với Quincy, ghi rõ `log-ignorelist` và logging đã đổi để không nhầm khác biệt test harness với khác biệt daemon.

### ADM-009 — Tuned profile mới ghi và áp dụng sysctl ở cấp host

**CSV:** `src/pybind/mgr/cephadm/tuned_profiles.py`, `inventory.py`, `module.py`, `serve.py`, `doc/cephadm/host-management.rst`. Pacific không có `TunedProfileStore`/`TunedProfileUtils` hoặc lệnh tuned-profile. Quincy lưu profile trong MGR store; `apply_tuned_profiles()` kiểm spec, `serve._apply_all_services()` gọi reconciler, reconciler ghi hoặc xóa các file `<profile>-cephadm-tuned-profile.conf` trong `/etc/sysctl.d` rồi chạy `sysctl --system`. Nó bỏ qua host unreachable/maintenance. `tests/test_tuned_profiles.py` dùng mock để kiểm đường ghi, xóa và skip unreachable; chưa chạy trên máy này. Commit liên quan `26d5f9230b5`, `7966240c56d`, `343c29e024d`.

**Điều kiện:** operator áp dụng tuned-profile bằng Quincy hoặc cluster đã lưu profile trong giai đoạn rollout. Đây là thay đổi cấu hình kernel của **host**, nên phải so giá trị `sysctl` thực tế với baseline trước khi áp dụng. Trong mixed-version, active MGR Quincy có thể reconcile profile; nếu failover về Pacific, file và giá trị đã ghi trên host không tự được Pacific quản lý, một suy luận cần kiểm chứng lab. Sau full Quincy, reconciler tiếp tục dùng placement và metadata host target. **Evidence confidence:** high cho code/định dạng file, medium cho ảnh hưởng rollback thực tế. **Kiểm chứng:** lab dùng profile với một tùy chọn sysctl không nhạy cảm, xác nhận file, giá trị và thời điểm `sysctl --system`; thử add/rm profile, host maintenance/offline và failover MGR. Không áp dụng profile thử nghiệm trên host production.

### ADM-010 — Đường cephadm-exporter biến mất; monitoring thêm Loki/Promtail

**CSV:** `src/pybind/mgr/cephadm/services/exporter.py`, `services/monitoring.py`, `module.py`, `src/cephadm/cephadm`, ba template Grafana/Loki/Promtail và `doc/cephadm/services/monitoring.rst`. Pacific có `CephadmExporter` với TLS/token config, service type và bootstrap `--with-exporter`/`--exporter-config`. Quincy không còn service/command/flag đó trong endpoint net diff; `src/cephadm/cephadm` vẫn còn một tham chiếu tên cũ ở `is_container_running`, không phải bằng chứng còn hỗ trợ triển khai. Target thêm service `loki` và `promtail` cùng image option, template log shipping, dependency trong orchestrator và datasource Loki trong Grafana. Loki/Promtail gom log; chúng **không được coi là thay thế tương đương cho metadata exporter**. Commit liên quan `35f895aa45c`, `dbe8d0716c5`, `55414caa6be`, `f5ad92d96f0`.

**Điều kiện:** cluster Pacific có `cephadm-exporter` hoặc runbook dùng flag exporter; hoặc cluster dự định dùng tập trung log với Loki/Promtail. Trong mixed-version, active MGR Pacific và Quincy có danh sách service/CLI khác nhau; trạng thái daemon exporter cũ sau chuyển active MGR chưa được chứng minh từ code diff. Sau full Quincy, triển khai Loki/Promtail phải được yêu cầu và kiểm tra độc lập; tài liệu nói hai service không bật mặc định. **Evidence confidence:** high cho service/CLI/template endpoint, medium cho cách xử lý daemon exporter đã tồn tại. **Kiểm chứng:** trong lab có exporter từ Pacific, chuyển active MGR và xem `ceph orch ls`, `ceph orch ps`, health/stray daemon, CLI exporter; với Loki/Promtail, triển khai trên topology mẫu, kiểm scrape/log delivery và Grafana datasource. Không suy rằng log tập trung có sẵn chỉ vì upgrade xong.

### ADM-011 — Maintenance có cờ vượt các safety gate

**CSV:** `src/pybind/mgr/cephadm/module.py`, `doc/cephadm/host-management.rst`. Pacific `enter_host_maintenance()` từ chối single-node, upgrade active, lỗi `ok-to-stop`, lỗi `host-maintenance` và lỗi set `noout`; `--force` chỉ đi vào `ok-to-stop`. Quincy thêm `yes_i_really_mean_it`, yêu cầu đi cùng `--force`, và khi bật cho phép đi qua các kiểm tra đó. Tài liệu target nêu rủi ro mất availability/quorum. Đây là đường lệnh thủ công, không phải hành vi maintenance tự động khi nâng cấp.

**Điều kiện:** operator chủ động gọi `ceph orch host maintenance enter ... --force --yes-i-really-mean-it`, nhất là khi đang upgrade hoặc host giữ MON/OSD quan trọng. Trong mixed-version, active MGR Pacific chưa có override này; active MGR Quincy có. Sau full Quincy, cờ vẫn là lựa chọn thủ công. **Evidence confidence:** high cho nhánh code và tài liệu, medium cho hậu quả từng topology. **Kiểm chứng:** lab thử thiếu cờ, chỉ `--force`, và đủ hai cờ trên topology giả lập; xác nhận error, trạng thái daemon, quorum và `noout` trước/sau. Runbook production phải kiểm điều kiện cluster riêng trước khi quyết định sử dụng.

### ADM-012 — Grafana cho phép tắt anonymous viewer qua spec

**CSV:** `src/pybind/mgr/cephadm/services/monitoring.py`, `templates/services/grafana/grafana.ini.j2`, `doc/cephadm/services/monitoring.rst`. Pacific template luôn ghi `[auth.anonymous] enabled = true`. Quincy render đoạn đó chỉ khi `GrafanaSpec.anonymous_access` là true; target default vẫn true, còn false yêu cầu `initial_admin_password` trong `GrafanaSpec`. Template target cũng đặt `snapshots.external_enabled = false`. `tests/test_services.py` có case false, nhưng chưa chạy. Commit `4dcfc07929f` thêm tùy chọn anonymous access.

**Điều kiện:** cấu hình Grafana spec với `anonymous_access: false` rồi reconfigure/redeploy; default không đổi chế độ anonymous viewer. Trong mixed-version, active MGR Pacific không biết tùy chọn mới trong spec nên phải kiểm đường failover/rollback trước khi đưa vào runbook; sau full Quincy, file `grafana.ini` phản ánh giá trị target khi được render lại. **Evidence confidence:** high cho spec/template/test, medium cho tác động session/login đang hoạt động. **Kiểm chứng:** lab so `grafana.ini` và truy cập không đăng nhập trước/sau đổi spec; xác nhận admin login, custom template nếu có, và hành vi sau failover MGR.

### ADM-013 — Cephadm đặt MON CRUSH location từ service spec

**CSV:** `src/pybind/mgr/cephadm/services/cephadmservice.py`, `doc/cephadm/services/mon.rst`, `qa/suites/orch/cephadm/workunits/task/test_set_mon_crush_locations.yaml`. Pacific `MonService` không đọc `crush_locations` từ spec. Quincy đưa cặp location đầu tiên của host vào daemon config khi deploy MON và gọi `mon set_location` cho MON đã có khi cấu hình spec; code kiểm MON đã xuất hiện trong monmap. Tài liệu lưu ý có thể phải re-apply spec nếu thời điểm gia nhập quorum làm set location chưa thành công, còn MON đang chạy có thể cần redeploy để nhận flag lúc khởi động. Workunit mới áp spec, re-apply rồi so `ceph mon dump`. Commit liên quan `dc4b3ee8e21`, `67386cc4524`.

**Điều kiện:** MON service spec có `crush_locations`, đặc biệt topology stretch có tiebreaker hoặc thay MON trong rollout. Nếu active MGR Pacific, spec mới chưa có đường apply này; khi active MGR Quincy, đường config và `mon set_location` có thể chạy. Sau full Quincy, cần xác nhận từng MON location thay vì chỉ xác nhận spec đã lưu. **Evidence confidence:** high cho code/tài liệu/workunit, medium cho thời điểm location được cập nhật trong cluster cụ thể. **Kiểm chứng:** lab MON 3 host với nhiều bucket, so `ceph mon dump --format json`, `ceph orch ps`, re-apply và redeploy khi MON vừa gia nhập quorum; kiểm quorum trước/sau, không thử bằng cách phá quorum production.

### ADM-014 — NFS VIP với keepalive-only ingress và tham số VRRP mới

**CSV:** `src/pybind/mgr/cephadm/services/ingress.py`, `services/nfs.py`, `templates/services/ingress/keepalived.conf.j2`, `doc/cephadm/services/nfs.rst`, `qa/suites/orch/cephadm/smoke-roleless/2-services/nfs-keepalive-only.yaml`. Pacific ingress coi HAProxy là daemon chính và Ganesha chỉ bind theo daemon IP; Quincy cho `keepalive_only` dùng keepalived mà không deploy HAProxy và cho NFS `virtual_ip` ưu tiên làm bind address. Template keepalived dùng `vrrp_interface_network`, `first_virtual_router_id` và nhánh multicast/unicast theo spec; password tự sinh cho keepalived rút từ 20 xuống 8 ký tự. Smoke recipe mới kiểm mount và ghi qua VIP. Commit liên quan `9ad04d3b83f`, `92f9d89b68d`, `12cf0067cb5`, `570ea39c25a`.

**Điều kiện:** cluster dùng ingress cho NFS, cấu hình VIP/VRRP tùy chỉnh, hoặc tái apply spec ingress cũ khi MGR Quincy active. Trong mixed-version, active MGR quyết định cách render keepalived và Ganesha; đã thay config/daemon thì failover về Pacific không tự khôi phục cấu hình cũ. Sau full Quincy, keepalive-only cần NFS count 1 như runbook target vì một VIP chỉ một NFS daemon bind trực tiếp. **Evidence confidence:** high cho code/template/smoke recipe, medium cho tương tác mạng thực tế. **Kiểm chứng:** lab deploy hai mode HAProxy và keepalive-only, kiểm VIP ownership, VRRP interface/router ID, NFS bind address, mount/ghi qua VIP và failover host; giữ cấu hình cũ để so sau chuyển active MGR.

### ADM-015 — QA harness và distro/agent matrix của cephadm thay đổi

**CSV:** `qa/tasks/cephadm.py`, `qa/tasks/cephadm.conf`, `qa/tasks/cephadm_cases/test_cli.py` và các selector `0-distro`, `0-random-distro`, `agent`, `.qa` trong suite cephadm. Pacific dùng nhiều symlink distro cục bộ; Quincy chuyển nhiều suite sang `.qa/distros/container-hosts`, thêm biến thể `use_agent` và thay phần setup teuthology: pull image trước bootstrap, host-add qua bootstrap remote, CephFS/iSCSI setup và chờ trạng thái OSD trong CLI test. Config QA cũng đổi EC profile và đặt `osd mclock profile = high_recovery_ops`. Hai hàng `R100` marker rỗng được kiểm bằng `old_path`: `smoke-singlehost/.qa` ghép với `workunits/0-distro/.qa`, còn selector `mgr-nfs-upgrade` ghép với selector dashboard; đây là ghép blob của Git, không chứng minh một test đã được chuyển logic nguyên vẹn.

**Điều kiện:** chạy suite QA cephadm hoặc dùng kết quả cũ làm baseline cho Pacific→Quincy. Trong mixed-version, lựa chọn image và agent variant của test phải khớp thực tế rollout; sau full upgrade, target harness tạo topology và workload theo cách mới. Các hunk này không đổi daemon production. **Evidence confidence:** high cho diff task/selector, medium cho danh sách job thực chạy trên CI vì chưa xem lịch chạy. **Kiểm chứng:** tạo manifest các job/suite trước và sau, chạy cùng topology ở lab; lưu image tag, distro, `use_agent`, config mClock/EC và log setup trước khi so tỷ lệ pass/fail. Riêng các `R100`, xem cả đường cũ và mới trong manifest.

### ADM-016 — Điều kiện chấp nhận và dashboard E2E QA thay đổi

**CSV:** `qa/suites/orch/cephadm/dashboard/task/test_e2e.yaml`, selector ignorelist dashboard, recipe `mgr-nfs-upgrade`, `thrash`, `orchestrator_cli`, ba workunit CLI/NFS và `qa/workunits/cephadm/test_dashboard_e2e.sh`, `test_cephadm.sh`. Pacific có task dashboard E2E trong suite này; target xóa task và ignorelist tương ứng, còn script E2E đổi tên option Cypress và bỏ bước tắt device monitoring/xóa metrics pool. Nhiều recipe target gỡ `log-ignorelist` MON/OSD/PG/MDS, trong khi CLI recipe thêm `POOL_APP_NOT_ENABLED`. Workunit `test_cephadm.sh` chuyển `IMAGE_DEFAULT` từ Pacific sang Quincy, bỏ `--with-exporter` và các assertion exporter. Điều này đổi phép so kết quả QA, không chứng minh các cảnh báo đã biến mất khỏi cluster.

**Điều kiện:** sử dụng bộ job cephadm QA như acceptance gate hoặc so với lịch sử CI. Trong mixed-version, phải ghi image thực tế của từng daemon và job vì workunit giờ mặc định Quincy; sau full target, nếu E2E dashboard vẫn cần cho tổ chức, phải xác nhận nó được chạy bởi suite khác trước khi coi gate còn bao phủ. **Evidence confidence:** high cho YAML/script diff, medium cho phạm vi CI ngoài repo. **Kiểm chứng:** chạy job chọn lọc trong lab, đối chiếu log health không còn ignore, Cypress config, trạng thái device monitoring và danh sách test dashboard được schedule; không suy kết quả pass/fail từ việc xóa file YAML.

### ADM-017 — QA thêm kiểm chứng rotate-key và RGW multisite

**CSV:** `qa/suites/orch/cephadm/with-work/tasks/rotate-keys.yaml` và `workunits/task/test_rgw_multisite.yaml`. Target thêm recipe quay khóa OSD/MGR rồi đợi auth key thực sự đổi; recipe RGW multisite mới bật module RGW, apply realm/zonegroup/zone và kiểm token JSON, endpoint, credential. Đây là **validation coverage** bổ sung cho orchestration và gateway; không phải bằng chứng các đường code production đã vượt qua test.

**Điều kiện:** job có chọn các recipe này và môi trường có topology/service đáp ứng. Trong mixed-version, chạy rotate-key trên daemon Pacific cần tách riêng kết quả theo active MGR và daemon cohort; sau full target, có thể dùng recipe để kiểm hồi quy. **Evidence confidence:** high cho nội dung recipe, medium cho độ ổn định/kết quả thực thi vì chưa chạy. **Kiểm chứng:** chạy lab với đủ daemon/realm, ghi thời gian chờ, giá trị key trước/sau (chỉ so hash hoặc presence, không lưu secret), token field và trạng thái RGW; đối chiếu job được scheduler chọn.

### ADM-018 — Cephadm thrash bỏ biến thể client Luminous/Mimic

**CSV:** bốn recipe `qa/suites/orch/cephadm/thrash-old-clients/1-install/{luminous,mimic}*.yaml` và selector Ubuntu 18.04 cùng suite. Pacific định nghĩa các biến thể Luminous/Mimic, gồm chế độ msgr1-only và gói client cũ; target xóa chúng khỏi suite này. Việc xóa test giảm bằng chứng hồi quy cho tổ hợp client đó, **không chứng minh client cũ không tương thích** với Quincy. Net diff endpoint cũng xóa các recipe Nautilus/Octopus khác khỏi cùng cây, nhưng chúng không thuộc CSV owner 08; cần xem owner tương ứng khi tổng hợp validation.

**Điều kiện:** deployment còn client Luminous/Mimic hoặc cần chứng cứ tương thích protocol cũ trong rollout Pacific→Quincy. Trong mixed-version, sự có mặt của client cũ phải lấy từ As-Is cluster; sau full target, suite này không còn cung cấp kết quả cho bốn biến thể đã xóa. **Evidence confidence:** high cho thay đổi coverage, unknown cho khả năng tương thích runtime. **Kiểm chứng:** kiểm inventory version client thực tế; nếu còn client cũ, dựng lab với msgr1/msgr2 như cấu hình cũ và chạy workload trực tiếp trên target, thay vì dùng việc xóa recipe làm kết luận.

Bốn hàng test agent, migration, scheduling và SSH được gắn `trivial` sau khi đọc hunk: chúng thêm hoặc sửa regression coverage cho các hành vi trên, không đổi code triển khai hay selector chấp nhận nâng cấp. Test tuned-profile cũng chỉ thêm unit coverage mock. Mười một hàng tài liệu đã phân loại `trivial` gồm sửa chính tả/markup, cross-reference iSCSI, developer toctree, hai SVG mockup, bản thiết kế OSD chưa triển khai và developer design của exporter đã bị xóa; chúng không đổi runbook nâng cấp hay code triển khai. Mười hai hàng `src/cephadm/box/` là sandbox Docker Compose/CLI riêng cho developer, không được code cephadm/MGR production import. Trong đó hai hàng `R100` là Git ghép file rỗng mới với marker `+` của suite Nautilus-X đã bị xóa; đã kiểm `old_path` và không coi đó là logic được di chuyển. Bảy hàng unit test/fixture còn lại và tài liệu developer/MDS, license, README image keepalived được gắn `trivial` sau khi đọc hunk: chúng bổ sung regression mock hoặc ví dụ không đổi đường upgrade độc lập. Tox gate được giữ `affect` ở ADM-025 vì thay dependency validation.

### ADM-019 — Rook smoke QA đổi matrix và kiểm tra OSD replacement

**CSV:** mười selector/recipe `qa/suites/orch/rook/smoke/`. Pacific chọn Ubuntu 18.04 và Rook 1.6.2, chưa có NVMe loop hoặc hai biến thể mạng. Quincy bỏ hai selector cũ, thêm Rook 1.7.2, NVMe loop, flannel và host networking. Recipe mới kiểm `ceph orch device ls`, host label add/list/remove, OSD remove/zap/reapply rồi đợi số OSD phục hồi; bước cuối thêm apply RGW, MDS, RBD mirror và NFS. Topology một node đặt `osd crush chooseleaf type: 0`. Đây là đổi matrix và acceptance của Rook smoke, không chứng minh một phiên bản Rook chạy thành công.

**Điều kiện:** job chọn suite Rook smoke hoặc dùng kết quả suite làm bằng chứng acceptance. Trong mixed-version, cần ghi riêng Rook image, Ceph daemon cohort và network selector; sau full Quincy, so kết quả với matrix mới thay vì pass rate cũ. **Evidence confidence:** high cho diff YAML, unknown cho kết quả chạy. **Kiểm chứng:** lab chạy từng selector cần dùng, giữ artifact device/OSD/PV trước sau và thời gian OSD quay lại; xác minh job scheduler thực sự chọn biến thể dự kiến.

### ADM-020 — Runbook cephadm đổi chuẩn bị host, log và thao tác daemon

**CSV:** `doc/cephadm/install.rst`, `operations.rst`. Ví dụ CentOS chuyển gói release cố định Pacific sang `centos-release-ceph-|stable-release|`, nêu SSH là prerequisite bootstrap. Tài liệu vận hành thêm daemon stop/start/restart, redeploy/reconfig/rotate-key; mô tả log Quincy ở journald và bổ sung `log_to_journald false` khi chọn file log. Công thức purge đổi `ceph orch pause` thành `ceph mgr module disable cephadm`; purge là thao tác phá dữ liệu, nên phải kiểm FSID theo chính runbook trước khi dùng. Đoạn `/var/lib/ceph/<fsid>/config` chỉ làm rõ chức năng đã có từ Pacific 16.2.10, không ghi là thay đổi endpoint.

**Điều kiện:** operator dùng tài liệu này để chuẩn bị host target, chẩn đoán log hoặc điều khiển daemon. Trong mixed-version, lệnh phải được kiểm trên active MGR hiện tại; sau full Quincy, kiểm log thực tế trong journald và file nếu cấu hình đã đổi. **Evidence confidence:** high cho thay đổi tài liệu, medium cho applicability từng cluster. **Kiểm chứng:** lab đối chiếu gói release/SSH, chạy daemon reconfig/redeploy/rotate-key trên daemon thử nghiệm và kiểm journal; không dùng purge trên production để xác nhận tài liệu.

### ADM-021 — Lệnh managed/unmanaged mới trong runbook service

**CSV:** `doc/cephadm/services/index.rst`. Pacific chỉ hướng dẫn đổi `unmanaged` qua service spec YAML; Quincy thêm `ceph orch set-unmanaged <service>` và `set-managed <service>`, kèm caveat service `osd` mặc định là ngoại lệ. Các sửa `orch` thành `ceph orch` làm ví dụ có thể chạy được, nhưng finding chính là đường thao tác trạng thái quản lý service mới.

**Điều kiện:** operator tạm dừng/re-enable reconciliation của service khi rollout. Trong mixed-version, active MGR Pacific có thể không nhận hai lệnh mới; sau full Quincy, trạng thái spec phải được đối chiếu với `ceph orch ls`. **Evidence confidence:** high cho runbook, medium cho kết quả CLI trên topology cụ thể. **Kiểm chứng:** lab chạy hai lệnh cho service thử nghiệm và `osd`, kiểm spec trước/sau và có daemon được deploy lại đúng lúc chuyển managed hay không.

### ADM-022 — Runbook DriveGroup cho phép gán CRUSH class theo từng path

**CSV:** `doc/cephadm/services/osd.rst`. Pacific minh họa path device; Quincy thêm cú pháp `crush_device_class` toàn spec hoặc trong từng entry `data_devices.paths`, ví dụ `/dev/sdb` là `ssd` và `/dev/sdc` là `nvme`. Tài liệu này là bằng chứng đường khai báo mới; không suy từ riêng tài liệu rằng OSD đang tồn tại sẽ đổi class khi reapply.

**Điều kiện:** tạo OSD mới hoặc thay OSD bằng DriveGroup dùng path cụ thể. Trong mixed-version, active MGR và ceph-volume thực thi phải cùng hiểu spec; sau full Quincy, class của OSD mới cần khớp khai báo. **Evidence confidence:** high cho cú pháp tài liệu, medium cho behavior runtime. **Kiểm chứng:** lab preview/apply spec trên disk dùng thử và so `ceph osd crush tree` cùng metadata device; kiểm rollback spec trước khi dùng thiết bị production.

### ADM-023 — Hướng dẫn RGW multisite thay realm/zonegroup/zone recipe

**CSV:** `doc/cephadm/services/rgw.rst`. Ví dụ `ceph orch apply rgw` của Quincy thêm `--zonegroup`; ví dụ tạo realm, zonegroup, zone bỏ `--default`, giữ `--master`. Tài liệu nói cephadm chỉ deploy RGW, không tạo hoặc cập nhật multisite topology. Cùng hunk còn mô tả `use_keepalived_multicast`, `vrrp_interface_network` và `first_virtual_router_id`, được cross-reference ở ADM-014.

**Điều kiện:** cluster RGW multisite dùng runbook khi chuyển sang target hoặc dựng zone mới. Trong mixed-version, realm metadata và daemon deployment là hai bước riêng; sau full Quincy, phải kiểm zonegroup/zone/default thực tế thay vì suy từ lệnh ví dụ. **Evidence confidence:** high cho diff tài liệu, medium cho topology thực tế. **Kiểm chứng:** lab áp dụng spec vào realm thử nghiệm, so `radosgw-admin realm/zonegroup/zone get` và `ceph orch ls/ps`; kiểm traffic sync riêng.

### ADM-024 — Nguồn image keepalived cho ingress thay đổi

**CSV:** `src/cephadm/containers/keepalived/Dockerfile`, `skel/init.sh`. Pacific mặc định dùng `docker.io/arcts/keepalived` trong cephadm và MGR; Quincy mặc định `quay.io/ceph/keepalived:2.1.5`. Target thêm recipe UBI8 minimal cài keepalived 2.1.5 và entrypoint chạy `keepalived -n -l -f` với tùy chọn debug. Repo không chứng minh digest của image registry được build từ chính Dockerfile này, nên liên hệ artifact là điều kiện cần xác minh, không phải kết luận provenance.

**Điều kiện:** ingress dùng keepalived và image mặc định hoặc image tự build từ recipe này; custom image có đường riêng. Trong mixed-version, active MGR quyết định image khi redeploy, còn daemon đang chạy giữ image cũ cho tới khi thay. Sau full Quincy, xác nhận image/digest và VIP failover. **Evidence confidence:** high cho source/default string, medium cho image provenance và network behavior. **Kiểm chứng:** lab ghi image digest thực chạy trước/sau redeploy, kiểm entrypoint/config, VRRP và failover với spec ADM-014; tra build provenance của artifact registry nếu cần chứng nhận.

### ADM-025 — Tox gate cephadm đổi nguồn ràng buộc mypy

**CSV:** `src/cephadm/tox.ini`. Pacific pin trực tiếp `mypy==0.790`; Quincy dùng `mypy` qua `-c{toxinidir}/../mypy-constrains.txt`. Lệnh chạy mypy vẫn nhắm `cephadm`; phép kiểm đếm `docker.io` trong flake8 env giữ nguyên và thêm ghi chú downstream. Đây là thay đổi dependency của gate phát triển/đóng gói, không đổi daemon production.

**Điều kiện:** CI hoặc downstream chạy `tox -e mypy` cho cephadm. Trong mixed-version không có đường runtime; khi validate bản target, constraint file phải có sẵn và version mypy được resolve theo nó. **Evidence confidence:** high cho tox diff, unknown cho CI ngoài repo. **Kiểm chứng:** chạy tox gate trong môi trường build phù hợp hoặc xem log CI target, ghi mypy version được cài và kết quả; không dùng một pass cũ với mypy 0.790 làm bằng chứng cho gate target.

## Kiểm chứng cần hoàn thành

- Đã đọc hunk/context và gắn `affect|trivial` cùng lý do cho cả 134 hàng; mọi `affect` trỏ đến finding ID.
- Đã đối soát `95 affect + 39 trivial = 134` và mô tả các cụm trivial.
- Còn cần lab/canary cho SSH, failover, OSD, ingress, monitoring và acceptance QA; đối chiếu commit/tài liệu chính thức bổ sung khi áp vào As-Is cluster.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
