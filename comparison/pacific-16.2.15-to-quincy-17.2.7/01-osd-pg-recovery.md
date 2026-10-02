# 01 — OSD, PG, peering, recovery/backfill, scrub và EC: v16.2.15 → v17.2.7

**Trạng thái: binary gate đã hoàn tất cho owner 01; chưa chạy thử trên cluster.** [CSV đầy đủ của owner](./01-osd-pg-recovery.csv) có 465 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 352`, `trivial = 113`, **chưa phân loại = 0**.

## Phạm vi và phương pháp

Owner này phụ trách OSD, PG, peering, recovery/backfill, scrub và EC. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

## Findings liên quan nâng cấp

### OSD-001 — Queue cost và QoS/recovery path cho mClock

**CSV:** `src/osd/OSD.cc`. Endpoint diff thay `OSDService::queue_recovery_context` để dùng cost thực cho mClock, tính scrub event cost từ chunk size, và cập nhật `OSD::handle_conf_change`/QoS branch cho recovery, backfill, sleep settings. Pacific có mClock tùy chọn nhưng các đường này dùng logic cũ; Quincy mặc định dùng mClock theo [CFG-001](./06-config-defaults.md). Hunk thuộc các symbol trên ở `src/osd/OSD.cc`; commit liên quan gồm `c30f2729b4815e56229c711cf0789cb704aec5dd7`, `20fcfcb84aa39d26c6f624849beddf2926cc03e4`, `81c0ca6cdc623278f64efd1daf65887d57ece621`.

**Điều kiện:** OSD dùng scheduler mClock; khác biệt này không tự kích hoạt nếu config hiệu dụng tiếp tục là `wpq`. Trong mixed-version, OSD target và base có thể xử lý queue/recovery khác nhau theo scheduler hiệu dụng và vai trò PG; sau full upgrade, các OSD target dùng đường mới. Không có bằng chứng ở đây để định lượng IOPS, latency hay tốc độ backfill. **Evidence confidence:** high cho các nhánh code, medium cho mức tác động triển khai.

**Kiểm chứng:** lab/canary chạy client IO đồng thời recovery/backfill/scrub, ghi scheduler và effective config từng OSD, đo client latency, hàng đợi recovery và thời gian PG trở lại clean. So với baseline Pacific trong cùng workload; dừng rollout nếu vượt ngưỡng do dự án đặt trước. `src/test/test_mclock_priority_queue.cc`, `qa/standalone/misc/mclock-config.sh` và QA scheduler là bằng chứng coverage cần đọc sâu; chưa chạy.

### OSD-002 — Tách địa chỉ bind và địa chỉ công bố của OSD

**CSV:** `src/ceph_osd.cc`. Pacific gọi `ms_public->bindv(public_addrs)` và dùng `public_addrs` cho heartbeat front. Quincy chọn thêm `CEPH_PICK_ADDRESS_PUBLIC_BIND`; nếu trả `-ENOENT` thì dùng `public_addrs`, lỗi khác làm OSD thoát, rồi gọi `bindv(public_bind_addrs, public_addrs)` và dùng địa chỉ bind cho heartbeat front. Hunk `main` trong tệp này; commit `bb9eb6aa2f1` xác nhận mục đích `public_bind_addrs`.

**Điều kiện:** cụm đặt public bind address riêng hoặc cấu hình địa chỉ sai. Nếu không đặt, code fallback về public address. Trong mixed-version, OSD Quincy áp dụng cách bind mới riêng cho chính nó; sau full upgrade, mọi OSD target dùng cách này. **Evidence confidence:** high cho nhánh code, medium cho khả năng ảnh hưởng mạng thực tế.

**Kiểm chứng:** trong lab kiểm tra socket lắng nghe, địa chỉ OSD công bố trong OSDMap, kết nối client/peer và heartbeat trên host có public bind riêng; thử cả trường hợp không đặt tùy chọn.

### OSD-003 — FileStore luôn dùng WPQ

**CSV:** `src/osd/scheduler/OpScheduler.cc`, `.h`, cùng hai recipe FileStore `qa/suites/rados/objectstore/backends/alloc-hint.yaml` và `ceph_objectstore_tool.yaml`. Factory ở Pacific chọn `wpq` hoặc `mclock_scheduler` từ `osd_op_queue`. Quincy chọn WPQ khi `osd_objectstore == "filestore"` dù queue config là mClock; constructor mClock đồng thời nhận OSD ID, shard ID và MonClient. Hai recipe mới đặt `osd op queue: wpq` rõ ràng trong QA (commit `7dcede75df4`), nên cấu hình thử cũng khác endpoint base. Commit `e65c4bcd96f` nêu rõ ép WPQ cho FileStore; [tài liệu mClock Quincy](https://docs.ceph.com/en/quincy/rados/configuration/mclock-config-ref/) xác nhận ràng buộc này.

**Điều kiện:** còn FileStore OSD và cấu hình mClock. BlueStore không chịu nhánh ép WPQ này. Trong mixed-version, OSD Pacific/FileStore và OSD Quincy/FileStore có thể dùng scheduler khác nếu config là mClock; sau full upgrade, FileStore target dùng WPQ. **Evidence confidence:** high.

**Kiểm chứng:** thống kê object store của mọi OSD, đọc `osd_op_queue` hiệu dụng và kiểm tra scheduler thực tế của FileStore trong lab/canary; đo hàng đợi và client latency nếu còn FileStore.

### OSD-004 — Mô hình chi phí và cấu hình mClock đổi

**CSV:** `src/osd/scheduler/mClockScheduler.cc`, `.h`. Pacific tính capacity theo IOPS/shard và cost qua tham số thời gian mỗi IO/byte. Quincy lấy `osd_mclock_max_sequential_bandwidth_(hdd|ssd)` cùng IOPS để chuyển cost sang byte/IO và capacity sang byte/giây/shard; reservation/limit lấy tỉ lệ capacity, một client profile ID chung thay cho owner ID riêng. Bộ profile tích hợp được đặt ở mức config default; với profile không phải `custom`, thay QoS key sẽ được khôi phục, gồm lệnh `config rm` cho `osd`/`osd.<id>` từ shard 0 và xóa giá trị tạm. Hunk `set_osd_capacity_params_from_config`, `ClientRegistry::update_from_config`, `get_scheduler_id`, `set_config_defaults_from_profile`, `calc_scaled_cost`, `handle_conf_change`; commit tiêu biểu `b8a53d96608`, `846a342c0d4`, `41c903a4bf2`. [Release notes v17.2.7](https://docs.ceph.com/en/latest/releases/quincy/) và [tham chiếu mClock Quincy](https://docs.ceph.com/en/quincy/rados/configuration/mclock-config-ref/) xác nhận default/profile và việc profile tích hợp khóa QoS option.

**Điều kiện:** OSD dùng mClock. Override QoS chỉ giữ ý nghĩa thủ công với profile `custom`; cấu hình profile tích hợp cần đối soát giá trị hiệu dụng trên daemon. Trong mixed-version, cách tính QoS khác nhau theo OSD; sau full upgrade áp dụng mô hình Quincy. Không suy ra mức IOPS/latency cụ thể từ diff. **Evidence confidence:** high cho code, medium cho tác động tải.

**Kiểm chứng:** chụp cấu hình mClock hiệu dụng, profile, capacity HDD/SSD, số shard và queue dump trước/sau; chạy cùng tải client/recovery trong lab và kiểm tra việc thay QoS key ở built-in/custom profile.

### OSD-005 — Phân lớp ưu tiên recovery và thêm telemetry hàng đợi

**CSV:** `src/osd/scheduler/OpSchedulerItem.cc`, `.h`. Pacific gán `PGRecovery`, `PGRecoveryContext`, `PGRecoveryMsg` vào `background_recovery`. Quincy chuyển lớp scheduler theo priority: high thành `immediate`, degraded recovery thành `background_recovery`, phần còn lại thành `background_best_effort`; `PGRecoveryMsg::is_recovery_msg` nhận thêm PUSH/PULL/BACKFILL/SCAN theo message type. Các đường chạy ghi thêm queue latency counter. Hunk ở ba lớp queueable và `PGRecovery::run`/`PGRecoveryMsg::run`; commit `474022959ff`, `885241d1a4d`, `4b83cd20f7f`, `24225de1cb8`.

**Điều kiện:** có recovery/backfill hoặc PG degraded/undersized và scheduler phân lớp. Trong mixed-version, OSD target phân loại work theo priority mới, OSD base giữ phân lớp cũ; sau full upgrade mọi OSD target áp dụng. **Evidence confidence:** high cho phân lớp, medium cho mức tác động hiệu năng.

**Kiểm chứng:** tạo tình huống degraded và backfill có kiểm soát trong lab, xem lớp hàng đợi, queue latency và client latency cùng tiến độ recovery ở mỗi version.

### OSD-006 — Hàng đợi và điều kiện chọn PG để scrub

**CSV:** `src/osd/scrubber/osd_scrub_sched.cc`, `.h`, `src/osd/scrubber_common.h`. Ở Pacific lịch scrub nằm trong `OSD.cc`/`PG`; Quincy tách thành `ScrubQueue`, lưu job và lịch đăng ký theo primary. `select_pg_and_scrub` lập điều kiện từ thời gian cho phép và tải, chỉ chọn job quá deadline khi vượt điều kiện thường; `select_from_group` gọi `initiate_a_scrub` sau lọc. Giao diện `ScrubPgIF` thêm `get_schedule`, `on_primary_change`, `update_scrub_job`; lịch scrub được xuất cho operator. Hunk trong ba tệp và commit `adc8dfb3e5b`, `4bf07e05cea`.

**Điều kiện:** PG cần scrub, nhất là khi tải cao, ngoài khung giờ hoặc khi đổi primary. Trong mixed-version, OSD primary quyết định scrub theo code của chính nó; sau full upgrade dùng scheduler Quincy. Chỉ đọc code chưa chứng minh độ trễ scrub cụ thể. **Evidence confidence:** high cho điều kiện chọn, medium cho tác động triển khai.

**Kiểm chứng:** lab với giờ scrub/tải giả lập, kiểm tra lịch PG và độ trễ đến scrub cho job thường/quá deadline, quan sát khi đổi primary và khi recovery đồng thời; đối chiếu kết quả với health warning scrub.

### OSD-007 — Scrub abort và snap trimming bị chặn

**CSV:** `src/osd/scrubber/pg_scrubber.cc`, `.h`. Logic scrub Pacific nằm trong `PG.cc`/`PrimaryLogPG.cc`; Quincy có `PgScrubber` riêng. Ở target, `verify_against_abort` dọn trạng thái cả khi epoch bằng `m_last_aborted`, và `should_abort` cho deep scrub xử lý `nodeep_scrub` riêng với nhánh `noscrub`, sửa ca FSM mắc ở `ActiveScrubbing,PendingTimer`. `clear_queued_or_active` gọi `snap_trimmer_scrub_complete()` nếu scrub từng queued/active, kể cả scrub abort/fail; `scrub_finish` không còn khởi động trim sớm ở giữa luồng. Hunk/commit `bf8db7cdf90`, `47933f540b0`, `139af5ea197` được đối chiếu với endpoint target.

**Điều kiện:** deep scrub đi cùng cờ `noscrub`/`nodeep_scrub`, hoặc snap trimming bị scrub trì hoãn rồi scrub kết thúc/abort. Trong mixed-version, primary OSD target dùng FSM mới cho PG mà nó sở hữu; sau full upgrade mọi primary dùng đường này. **Evidence confidence:** high cho nhánh và bug fix, medium cho tần suất gặp trong cluster.

**Kiểm chứng:** lab bật/tắt cờ scrub khi deep scrub được xếp lịch, quan sát FSM có thoát và scrub được xếp lại; tạo snapshot cần trim trong lúc scrub rồi gây abort/failure có kiểm soát, xác nhận trim tiếp tục và PG quay về clean.

### OSD-008 — Chuyển đổi legacy SnapMapper key và kiểm tra tính nhất quán

**CSV:** `src/osd/SnapMapper.cc`, `.h`, `src/osd/SnapMapReaderI.h`. Pacific `convert_legacy` dựng key mới từ pool và snap, làm mất hậu tố phân biệt object của key cũ. Quincy `convert_legacy_key` giữ phần từ snap ID trở đi của legacy key và thêm prefix/pool; commit `9b5fbb8cb80` ghi rõ lỗi chỉ được sửa cho các lần chuyển đổi tiếp theo. Ngoài ra, giao diện `SnapMapReaderI` và `get_snaps_check_consistency` so `OBJ_` với các `SNA_` entry, trả trạng thái inconsistent nếu thiếu/sai mapping; `get_snaps_common` chuyển lỗi decode sang `-EIO` thay vì để exception thoát. Hunk `convert_legacy`, `get_snaps_common`, `get_snaps_check_consistency`; commit `f46fec6e79c` cho giao diện scrub mới.

**Điều kiện:** còn legacy key cần chuyển đổi, hoặc scrub clone/snapshot đi qua kiểm tra SnapMapper. Lỗi key đã bị phá bởi lần chuyển đổi trước không được commit trên tự khôi phục; cần kiểm tra dữ liệu cụm thực tế. Trong mixed-version, mỗi OSD target dùng code mới cho PG nó xử lý; sau full upgrade toàn bộ OSD target dùng đường mới. **Evidence confidence:** high cho nhánh code và giới hạn của fix, medium cho mức phơi nhiễm của cụm.

**Kiểm chứng:** trên bản sao dữ liệu hoặc lab, tạo legacy mapping có nhiều clone cùng snap để kiểm tra key mới còn object suffix; chạy scrub có mapping thiếu/sai để xem lỗi được phát hiện. Với cụm thực, rà snapshot/clone và scrub inconsistency trước khi lập phương án xử lý; không sửa metadata trực tiếp từ kết luận này.

### OSD-009 — Gán cost khi xếp lại EC recovery read

**CSV:** `src/osd/ECBackend.cc`. Pacific gọi `queue_recovery_context` cho `FinishReadOp` trong `filter_read_op` mà không truyền cost; Quincy truyền cost `1` khi read source xuống trong lúc xử lý OSDMap và recovery read phải hoàn tất sau. Hunk tại `filter_read_op`, liên hệ thay đổi API/cost ở `OSD-001` và commit `c30f2729b48`. Phần còn lại trong file chủ yếu là đổi tracing và comparator.

**Điều kiện:** EC pool có log-based recovery, read source đổi trạng thái lúc xử lý OSDMap. Đây là đường hiếm theo chú thích code; không suy ra ảnh hưởng hiệu năng đại trà. Trong mixed-version, OSD target xếp lại work theo cost mới; sau full upgrade tất cả OSD target dùng đường này. **Evidence confidence:** high cho nhánh, low cho tần suất thực tế.

**Kiểm chứng:** lab EC pool với recovery và thay đổi OSDMap có kiểm soát, theo dõi queue/recovery progress và xác nhận không kẹt PG; so với Pacific trong cùng kịch bản.

### OSD-010 — Điểm bắt đầu rollback của PG log trong replicated pool

**CSV:** `src/osd/PGLog.cc`, `.h`. Pacific khi đọc log của replicated PG không có omap key `rollback_info_trimmed_to` giữ marker rỗng. Quincy, ở cả hai đường load tương ứng, đặt `on_disk_rollback_info_trimmed_to = info.last_update` khi `info.pgid.is_no_shard()`. Commit `c5b38306d7a` giải thích marker rỗng khiến peering replay qua toàn bộ PG log dù replicated pool không cần rollback; hunk nằm tại `read_log_and_missing` và đường read async.

**Điều kiện:** replicated PG log thiếu key rollback như thiết kế và OSD load/peer PG. Trong mixed-version, OSD target xử lý log theo marker mới, OSD base giữ hành vi cũ; sau full upgrade target áp dụng ở mọi OSD. Đây là thay đổi chi phí peering, không phải bằng chứng thay đổi nội dung object. **Evidence confidence:** high cho logic, medium cho mức cải thiện peering.

**Kiểm chứng:** lab replicated pool với PG log dài, restart OSD/trigger peering có kiểm soát, đo thời gian peering và số log entry xử lý, xác nhận PG vẫn active+clean và read checksum đúng.

### OSD-011 — Ý nghĩa duration trong dump của OpRequest

**CSV:** `src/osd/OpRequest.cc`, `.h`. Pacific `_dump` gán duration của một event theo mốc event kế tiếp, còn event cuối tính từ lúc khởi tạo request. Quincy gán event đầu duration `0`, các event sau tính từ event trước. `OpRequest.h` giữ tracing span ở mọi build thay vì chỉ khi có `HAVE_JAEGER`; đây là thay đổi đường quan sát, không phải thứ tự xử lý op. Hunk `OpRequest::_dump` và trường `osd_parent_span`.

**Điều kiện:** dashboard, parser hoặc runbook đọc event duration từ dump và/hoặc dùng tracing. Trong mixed-version, cùng trường `duration` có ý nghĩa khác theo daemon; sau full upgrade áp dụng nghĩa Quincy. **Evidence confidence:** high cho schema giá trị, medium cho mức phụ thuộc của tooling bên ngoài.

**Kiểm chứng:** so dump từ request tương đương trên hai version, cập nhật parser/biểu đồ dùng duration; kiểm tra tracing span trên build đang triển khai.

### OSD-012 — Chi phí recovery theo kích thước object và điều kiện scrub của PG

**CSV:** `src/osd/PG.cc`, `.h`. Pacific `PG::queue_recovery` xếp work mà không cung cấp cost/priority theo PG; Quincy lấy `max(num_bytes,0) / max(num_objects,1)` rồi chặn cost tối thiểu `1` và truyền cùng `recovery_state.get_recovery_op_priority()`. `PG::sched_scrub` trả reason cụ thể và từ chối PG đang `SNAPTRIM`/`SNAPTRIM_WAIT`; `publish_stats_to_osd` đưa lịch scrub vào PG stats. Hunk các hàm này và commit `5132e8b0a85`, `821f0b00b99`, `4bf07e05cea`.

**Điều kiện:** recovery của PG có kích thước object không đều, hoặc scrub trùng snaptrim/đổi primary. Trong mixed-version mỗi OSD áp dụng logic cho PG nó sở hữu; sau full upgrade target áp dụng toàn bộ. **Evidence confidence:** high cho nhánh code, medium cho mức thay đổi throughput.

**Kiểm chứng:** lab tạo PG với object size khác nhau rồi chạy recovery dưới tải; ghi queue cost, class, client latency và tiến độ. Đồng thời thử scrub trong `SNAPTRIM_WAIT`, xác nhận được xếp lại và lịch hiển thị trong PG stats.

### OSD-013 — Peering bỏ giao thức trước Octopus

**CSV:** `src/osd/PeeringState.cc`, `.h`. Pacific `BufferedRecoveryMessages`/`share_pg_info` chọn `MOSDPGNotify`, `MOSDPGQuery`, `MOSDPGInfo` cũ nếu `require_osd_release` trước Octopus; Quincy luôn phát biến thể `*2` và dùng assert ở các đường lease/recovery khi thiếu `SERVER_OCTOPUS`/`SERVER_NAUTILUS`. Đây là thay đổi compatibility floor của peering, không phải bằng chứng lỗi với đúng cặp Pacific/Quincy vì Pacific đã sau Octopus. Hunk `send_notify`, `send_query`, `send_info`, `share_pg_info`, `send_lease`, `proc_lease`, `select_replicated_primary`.

**Điều kiện:** OSD/peer hoặc OSDMap bất ngờ quảng bá feature quá cũ. Mixed-version chuẩn 16.2.15/17.2.7 cần xác nhận min feature thực tế trước rollout; khi mọi OSD đã lên target, nhánh legacy không còn. **Evidence confidence:** high cho code, medium cho khả năng gặp trong As-Is chưa khảo sát.

**Kiểm chứng:** thu `ceph features`, `require-osd-release`, OSDMap và phiên bản mọi OSD; lab rolling upgrade, kiểm tra peering/lease sau restart từng OSD, không trộn daemon ngoài cặp đã định.

### OSD-014 — Lease ack và phân ưu tiên recovery theo trạng thái PG

**CSV:** `src/osd/PeeringState.cc`, `.h`. Pacific `proc_lease_ack` gọi `recheck_readable` khi `now < old_ru`; Quincy đổi thành `now >= old_ru`, giúp kiểm tra lại khi thời hạn cũ đã hết (commit `c71ee14cdbc`). Quincy đồng thời đặt recovery priority theo forced, undersized, degraded, best-effort cho mClock; WPQ dùng pool `RECOVERY_OP_PRIORITY` hoặc `osd_recovery_op_priority`. `get_recovery_op_priority` trong header và `OSD-005` là hai phía của cùng đường phân lớp.

**Điều kiện:** PG laggy nhận lease ack hoặc đang recovery/backfill dưới mClock/WPQ. Trong mixed-version hành vi tùy OSD primary; sau full upgrade logic target áp dụng cho mọi PG. **Evidence confidence:** high cho điều kiện code, medium cho thời gian PG thoát laggy/khác biệt QoS.

**Kiểm chứng:** lab gây trễ lease ack rồi xác nhận PG thoát laggy sau ack, thử forced/degraded/backfill và đối chiếu class/priority queue theo scheduler hiệu dụng.

### OSD-015 — Xử lý pool EIO ở đường client op

**CSV:** `src/osd/PrimaryLogPG.cc`. Pacific chỉ kiểm tra pool tồn tại trong nhánh write, không có xử lý `FLAG_EIO` ở đầu `do_op`. Quincy kiểm tra pool sớm hơn; nếu pool có `FLAG_EIO`, op hỗ trợ `CEPH_OSD_FLAG_SUPPORTSPOOLEIO` được bỏ để client xử lý lỗi, client cũ nhận reply `-EIO` trực tiếp. Hunk `PrimaryLogPG::do_op`, commit `5ac9f523ea2`.

**Điều kiện:** pool được đánh dấu EIO, tùy feature của client. Mixed-version có thể trả lỗi khác theo OSD nhận op; sau full upgrade hành vi Quincy đồng nhất. **Evidence confidence:** high.

**Kiểm chứng:** lab pool thử nghiệm đặt EIO flag, gửi read/write từ client có và không có feature, ghi reply/retry và kiểm tra không có write được commit; tuyệt đối không thử trên pool production.

### OSD-016 — Manifest/refcount, copy và rollback của object chunked

**CSV:** `src/osd/PrimaryLogPG.cc`, `.h`. Pacific `inc_refcount_by_set` chỉ giả định một chunk; Quincy duyệt `chunk_map`, theo dõi nhiều TID và callback rồi unblock object khi mọi refcount operation hoàn tất. Đường `get_manifest_ref_count` chờ clone chưa readable; `promote_object` phân biệt chunked manifest; rollback sang clone chunked tăng reference trước khi thay head, cập nhật manifest/flags và giảm reference cũ. Hunk `inc_refcount_by_set`, `finish_set_manifest_refcount`, `get_manifest_ref_count`, `promote_object`, `_rollback_to`/`_do_rollback_to`; commit `a8734cb7778`, `7b669e4af42` và các hunk endpoint.

**Điều kiện:** pool có dedup/chunked manifest, tiering hoặc snapshot rollback liên quan manifest; cụm không dùng tính năng này không đi qua các nhánh ấy. Mixed-version cần kiểm tra PG primary và client op trên cả hai bản; sau full upgrade target dùng đường mới. **Evidence confidence:** high cho code, medium cho toàn bộ edge case dữ liệu.

**Kiểm chứng:** lab với chunked object nhiều chunk, snapshot, rollback, promote và recovery clone; đối chiếu bytes, digest, refcount, PG log và trạng thái sạch sau restart. Dùng bản sao dữ liệu khi thử ca hỏng/lỗi.

### OSD-017 — Sparse read có truncate sequence và lỗi xattr số

**CSV:** `src/osd/PrimaryLogPG.cc`. Pacific `do_sparse_read` từ chối mọi request có `truncate_seq` khác 0; Quincy tính kích thước hiệu dụng từ `truncate_size` và chỉ đọc phần còn hợp lệ. So sánh xattr dạng số chuyển từ `strtoull` không kiểm lỗi sang `std::from_chars`, trả `-EINVAL` khi parse lỗi hoặc vượt miền. Hunk `do_sparse_read`, `do_xattr_cmp_u64`.

**Điều kiện:** client dùng sparse read cùng truncate sequence, hoặc so sánh xattr số có dữ liệu không hợp lệ. Trong mixed-version cùng request có thể nhận kết quả khác tùy primary OSD; sau full upgrade theo target. **Evidence confidence:** high cho nhánh code.

**Kiểm chứng:** lab sparse read qua truncate/rewrite, đối chiếu extent và bytes; thử xattr số hợp lệ, rỗng, không phải số và tràn `uint64`, quan sát reply code trên cả hai bản.

### OSD-018 — Cost và clean-region path của replicated recovery

**CSV:** `src/osd/ReplicatedBackend.cc`. Pacific callback sau pull response xếp recovery context mà không truyền chi phí ước lượng; Quincy cộng `num_bytes_recovered` của các push cần tiếp tục và đưa `max(cost,1)` vào `queue_recovery_context`. Các đường `calc_head_subsets`, `prepare_pull`, `prep_push` bỏ fallback trước Octopus và assert peer có `SERVER_OCTOPUS`, rồi dùng clean-region để chọn phần dữ liệu/omap cần copy. Hunk `_do_pull_response`, `C_ReplicatedBackend_OnPullComplete` và các hàm recovery; liên hệ `OSD-001`/`OSD-013`.

**Điều kiện:** replicated pool recovery/pull/push; thay đổi cost rõ nhất khi các object có kích thước khác nhau. Mixed-version mỗi OSD target tự xếp work theo cost mới; full upgrade áp dụng cho toàn bộ target. **Evidence confidence:** high cho logic, medium cho hiệu năng thực tế.

**Kiểm chứng:** lab mất rồi phục hồi replica với object lớn/nhỏ, kiểm tra queue cost, clean-region transfer, digest và PG clean; đồng thời thử rolling upgrade trên peer Pacific/Quincy.

### OSD-019 — Object-class gather từ nhiều remote object

**CSV:** `src/osd/objclass.cc`. Pacific chưa có `cls_cxx_gather` và `cls_cxx_get_gathered_data` trên classic OSD; Quincy tạo finisher, đọc các source object qua objecter, gom buffer kết quả và trả mã lỗi cho class method. `PrimaryLogPG::start_cls_gather`/`cancel_cls_gather` ở `OSD-016` là đường thực thi phía PG. Hunk hai hàm mới và commit chuỗi `caf364db5e7`, `a5b04552f88`, `87e4b9714fe`.

**Điều kiện:** object class dùng API gather mới, ví dụ test class `src/cls/test_remote_reads`. Cụm không chạy class đó không có đường dữ liệu tương ứng. Trong mixed-version, method cần được kiểm tra trên cả OSD base và target; sau full upgrade target có API. **Evidence confidence:** high cho API/code, medium cho mức sử dụng thực tế.

**Kiểm chứng:** lab gọi class method với nhiều source object, source thiếu và source lỗi; đối chiếu buffer/mã lỗi, thử op bị hủy khi PG đổi primary.

### OSD-020 — Thêm chỉ số delay và queue latency của OSD

**CSV:** `src/osd/osd_perf_counters.cc`, `.h`. Quincy thêm `op_delayed_unreadable`, `op_delayed_degraded` và các bộ đo queue latency riêng cho PUSH, PUSH_REPLY, PULL, BACKFILL, BACKFILL_REMOVE, SCAN, `PGRecovery`, `PGRecoveryContext`. Pacific chưa xuất các tên chỉ số này. Hunk `build_osd_logger`/enum counter; đường tăng counter nằm ở `PrimaryLogPG` và `OSD-005`.

**Điều kiện:** dashboard, alert hoặc phân tích canary cần phân biệt delay theo trạng thái object hay từng loại recovery message. Trong mixed-version chỉ daemon target có các series mới; sau full upgrade có thể thu đồng nhất. **Evidence confidence:** high.

**Kiểm chứng:** lấy perf dump từ OSD Pacific/Quincy trong lab có unreadable/degraded và recovery; đảm bảo collector chịu được series thiếu ở OSD cũ và kiểm tra giá trị tăng đúng tình huống.

### OSD-021 — Tracer chuyên biệt cho OSD

**CSV:** `src/osd/osd_tracer.cc`, `.h`. Quincy định nghĩa `tracing::osd::tracer` dùng bởi `OpSchedulerItem`, `PrimaryLogPG`, `ReplicatedBackend` và EC backend thay cho các nhánh Jaeger cũ ở những call site đã rà. Tệp mới chỉ cấp đối tượng tracer, nhưng các call site làm thay đổi span quan sát được; không có bằng chứng từ hai tệp này rằng xử lý IO đổi. **Evidence confidence:** high cho đường tracing, medium cho việc collector ngoài cụm nhận span.

**Điều kiện:** build/runtime bật tracing và có pipeline thu span. Trong mixed-version cấu trúc span có thể khác theo OSD; sau full upgrade các OSD target dùng tracer mới. **Kiểm chứng:** lab bật tracing, chạy client IO/recovery và so span hierarchy/name với pipeline quan sát hiện có.

### OSD-022 — Mở rộng wire format và dump của PG stats

**CSV:** `src/osd/osd_types.cc`, `.h`. Pacific `pg_stat_t` encode version 26; Quincy nâng lên 29, thêm lịch scrub, thời lượng scrub/snaptrim, số object scrubbed/trimmed và kích thước duplicate PG log. Decode target đọc có điều kiện theo version 27/28/29; dump cũng có thêm các trường. Header còn thêm `denc_coll_t` cho collection map của Crimson SeaStore và `object_info_t::encode_no_oid/decode_no_oid` cho Crimson recovery, nên phần này phụ thuộc việc dùng Crimson. Hunk `pg_stat_t::encode/decode/dump`, `denc_coll_t`, `object_info_t` helpers.

**Điều kiện:** MON/MGR/dashboard nhận PG stats từ OSD target, hoặc cụm chạy Crimson/SeaStore. Trong mixed-version có hai version PG stats trên wire; target decode ngược bằng version gate, nhưng consumer ngoài Ceph cần kiểm tra giả định schema. Sau full upgrade các OSD target xuất các trường mới. **Evidence confidence:** high cho wire/version, medium cho mức tương thích của tooling bên ngoài.

**Kiểm chứng:** lab rolling upgrade, đối soát `pg dump`/MGR metrics trước-sau, scrub schedule và trim fields; nếu dùng Crimson, thử restart/recovery trên bản sao store và kiểm tra decode dữ liệu.

### OSD-023 — Cost của PullOp và PushReplyOp theo scheduler

**CSV:** `src/osd/osd_types.cc`, `.h`. Pacific cả `PullOp` và `PushReplyOp` dùng `osd_push_per_object_cost + osd_recovery_max_chunk`. Quincy với mClock cho PushReply cost `1` và Pull cost bằng số byte ước lượng còn phải recover, chặn trong `[1, osd_recovery_max_chunk]`; nhánh WPQ giữ công thức cũ. Hunk hai hàm cost và `ObjectRecoveryProgress::estimate_remaining_data_to_recover`; commit `2e98d162f9d`, `eb57e4b53a3`.

**Điều kiện:** recovery có pull/push và OSD dùng mClock; WPQ giữ cost cũ. Trong mixed-version chi phí queue khác nhau theo daemon, sau full upgrade áp dụng theo scheduler cấu hình. **Evidence confidence:** high cho công thức, medium cho tốc độ recovery thực tế.

**Kiểm chứng:** lab recovery object nhỏ/lớn với mClock và WPQ, xem queue cost, client latency và thời gian PG clean.

### OSD-024 — Đường fast shutdown của OSD

**CSV:** `src/osd/OSD.h` (implementation ở `src/osd/OSD.cc`, đã gắn `OSD-001`). Pacific `osd_fast_shutdown` flush log rồi `_exit` sớm. Quincy khi fast shutdown và store `has_null_manager()` thực hiện stop queue mới, xóa work chưa chạy, dừng timer, drain op thread pool, umount store rồi mới `_exit`; nhánh không có null manager vẫn thoát sớm. `OSD.h` thêm cờ `m_fast_shutdown`, `stop_for_fast_shutdown` và giữ `ObjectStore` bằng `unique_ptr`. Hunk `OSD::shutdown`, `ShardedOpWQ::stop_for_fast_shutdown`, commit `5f4f59f8a2f`.

**Điều kiện:** `osd_fast_shutdown=true`, phụ thuộc loại object store/allocator. Trong mixed-version OSD base/target có trình tự dừng khác; sau full upgrade áp dụng nhánh Quincy. **Evidence confidence:** high cho code, medium cho thời gian dừng và độ bền trong môi trường thật.

**Kiểm chứng:** lab với IO và recovery đang chạy, bật fast shutdown trên OSD thử nghiệm, đo drain/umount, restart và kiểm tra store/PG sạch; thử cả điều kiện `has_null_manager()` và không có nếu môi trường hỗ trợ.

### OSD-025 — Scrub FSM theo dõi reservation, thời lượng và sự kiện bất thường

**CSV:** `src/osd/scrubber/scrub_machine.cc`, `.h`, `scrub_machine_lstnr.h`. Đối chiếu rename-aware với các tệp Pacific ở `src/osd/`: target chuyển StartScrub/AfterRepairScrub sang custom reaction để ghi thời điểm bắt đầu, đánh dấu OSD đang giữ chỗ trong `ReservingReplicas` và giải phóng khi rời state, đặt cảnh báo nếu chờ object bị block quá lâu. `WaitReplicas` không còn defer `DigestUpdate` đến state kế tiếp mà ghi cảnh báo cluster và bỏ sự kiện bất ngờ; khi scrub kết thúc, FSM ghi duration. Hunk các state/reaction và commit `2809a58411f`, `28805a80444`, `a7356b53a1f`.

**Điều kiện:** PG đang scrub, đặc biệt khi tranh reservation, object bị block hoặc nhận DigestUpdate không đúng state. Trong mixed-version primary target dùng FSM mới, primary base dùng FSM cũ; sau full upgrade target áp dụng. **Evidence confidence:** high cho state transitions, medium cho tần suất sự kiện bất thường.

**Kiểm chứng:** lab gây thiếu replica scrub slot và blocked object có kiểm soát, quan sát không có scrub chạy trùng và cảnh báo đúng hạn; gửi sự kiện stale/không đúng thứ tự qua test scrub, xác nhận FSM tiếp tục và duration được xuất.

### OSD-026 — Man page của ceph-bluestore-tool bổ sung quy trình phục hồi

**CSV:** `doc/man/8/ceph-bluestore-tool.rst`. Pacific chưa mô tả `-i`, `qfsck`, `allocmap`, `restore_cfb`; Quincy thêm chúng và cách lấy cấu hình OSD từ MON hoặc `--no-mon-config`. `allocmap` được ghi là bị tắt mặc định và cần build đặc biệt. Diff tool thực thi, build gate và lab check tương ứng đã ghi ở [BLU-004](./02-bluestore-bluefs.md), nên man page là bằng chứng quy trình đi kèm, không tự chứng minh mọi gói binary có các lệnh đó.

**Điều kiện:** runbook fsck/repair/allocation map hoặc pipeline gọi tool lúc rehearsal. Trong mixed-version phải chạy đúng binary tương ứng với OSD store được khảo sát; sau full upgrade runbook cần khớp artifact target. **Evidence confidence:** high cho tài liệu/source, medium cho packaging cụ thể.

**Kiểm chứng:** trên clone OSD, đối chiếu `ceph-bluestore-tool --help` với man page và build flags, thử `-i`/`--path`, `qfsck` và `restore_cfb` theo phạm vi build; không coi `allocmap` luôn khả dụng.

### OSD-027 — Nghiên cứu mClock/WPQ mới trong cây nhưng dùng default cũ

**CSV:** `doc/dev/osd_internals/mclock_wpq_cmp_study.rst`. Tài liệu mới và 15 biểu đồ đi kèm mô tả benchmark trên bản phát triển `17.0.0-2125-g94f550a87f`, nhiều thiết lập test không mặc định, và gọi `high_client_ops` là profile mặc định. Endpoint `v17.2.7` ở `src/common/options/osd.yaml.in` lại đặt `osd_mclock_profile=balanced`; xem [CFG-001](./06-config-defaults.md). Vì vậy kết quả benchmark là ngữ cảnh thiết kế, không phải dự báo latency/recovery cho cặp endpoint này. Biểu đồ tĩnh được phân loại `trivial` riêng vì không đổi hành vi; tệp nghiên cứu được đánh `affect` do dễ dẫn đến lựa chọn profile sai khi đọc để lập kế hoạch.

**Điều kiện:** operator dùng nghiên cứu này để chọn profile hoặc ước lượng hiệu năng nâng cấp. Mixed-version và full upgrade phải lấy effective config và đo workload của cluster, không dùng nhãn default trong nghiên cứu. **Evidence confidence:** high cho lệch version/default, low cho áp dụng số benchmark lên cluster chưa biết.

**Kiểm chứng:** lưu `ceph config show osd.N`/`ceph config get` của canary, xác nhận profile `balanced` hay override, chạy cùng tải client/recovery trong lab; ghi riêng version, media và các non-default option khi so biểu đồ.

### OSD-028 — Bỏ các nhánh message OSD đời cũ

**CSV:** chín header `MOSDBoot`, `MOSDFailure`, `MOSDMarkMeDown`, `MOSDPGInfo`, `MOSDPGLog`, `MOSDPGNotify`, `MOSDPGScan`, `MOSDRepOp`, `MOSDRepOpReply` dưới `src/messages/`. Pacific còn nhánh encode/decode cho một số peer trước Nautilus/Octopus hoặc RepOp trước Luminous. Quincy bỏ các nhánh đó: Boot/Failure/MarkMeDown/PGLog/PGScan assert feature `SERVER_NAUTILUS`; PGInfo/PGNotify assert `SERVER_OCTOPUS` và nâng `COMPAT_VERSION` lên 6/7; PGLog đòi header v6 để decode lease; RepOp assert `SERVER_OCTOPUS`, RepOpReply luôn encode `min_epoch` và trace. Hunk endpoint và commit `4a13e912619`, `6ede5733d49` là bằng chứng cho đường wire.

**Điều kiện:** chỉ phát sinh khi peer cũ hoặc message header đời cũ xuất hiện. Với cặp Pacific 16.2.15/Quincy 17.2.7, các feature đời Nautilus/Octopus được kỳ vọng có ở cả hai đầu; diff này không tự chứng minh một rolling upgrade hợp lệ sẽ lỗi. Mixed-version cần xét feature thực của MON/OSD và thành viên cũ còn trong cụm; full-version vẫn không đọc được các encoding bị bỏ. **Evidence confidence:** high cho nhánh encode/decode; medium cho phạm vi peer thực của cluster chưa biết.

**Kiểm chứng:** trong lab, xác nhận feature bit và header của message peering/replication giữa OSD Pacific và Quincy bằng log/trace; thử boot, mark-down, peering, recovery, scrub và rollback canary. Nếu có daemon trước Octopus, tách kiểm tra tương thích riêng trước khi chạy phiên bản target.

### OSD-029 — Factory và quyền sở hữu ObjectStore

**CSV:** `src/os/ObjectStore.cc`, `.h` (liên quan nhánh shutdown ở [OSD-024](#osd-024--đường-fast-shutdown-của-osd)). Pacific `ObjectStore::create()` trả raw pointer; Quincy trả `unique_ptr`, tách overload ba đối số cho đường Seastar, đưa MemStore vào factory chung và dùng BlueStore cho `random` ở overload đó. Đường classic năm đối số vẫn chọn FileStore/BlueStore cho `random`, FileStore trực tiếp và KStore khi bật experimental gate. Header thêm virtual `prepare_for_fast_shutdown()` và `has_null_manager()`; `OSD.cc` dùng hook này trong OSD-024. Hunk factory và commit `007133a6acd`, `7e8ec0c8cae`.

**Điều kiện:** chủ yếu là khởi tạo store, Crimson/Seastar hoặc build dùng loại store khác BlueStore; đường classic của OSD cần kiểm riêng ownership và shutdown. Trong mixed-version mỗi daemon sở hữu store theo binary đang chạy; sau full upgrade factory target áp dụng. **Evidence confidence:** high cho API và nhánh factory, medium cho ảnh hưởng triển khai thực vì chưa có build flags/loại store của cluster.

**Kiểm chứng:** lab khởi động OSD target trên clone store theo backend thực, kiểm mount/umount và fast shutdown rồi restart; nếu dùng Crimson/Seastar, thử factory MemStore/BlueStore và nhánh `random` trong build tương ứng.

### OSD-030 — Tạo CRUSH rule cho erasure code sau khi bỏ rule mask

**CSV:** `src/erasure-code/ErasureCode.cc`, `src/erasure-code/lrc/ErasureCodeLrc.cc`; xem [MON-006](./04-mon-osdmap-crush.md#mon-006--crush-bỏ-rulesetminmax-khỏi-logic-chọn-rule). Pacific đặt mask `max_size = chunk_count` khi tạo EC rule; LRC tránh trùng cả rule ID lẫn ruleset và truyền `min_rep=3`, `max_rep=chunk_count` vào `add_rule`. Quincy bỏ các mask/ruleset này, chọn rule ID trống và truyền type vào `add_rule`; LRC còn return ngay nếu parse `crush-device-class` lỗi trước khi xử lý `crush-steps`. Hunk endpoint và commit `f95eb04411c`, `6c4bbee7e33`, `621725ab476`.

**Điều kiện:** tạo/sửa EC profile và CRUSH rule LRC, nhất là map có legacy ruleset hoặc profile sai; rule đã có cần đánh giá theo MON-006 chứ không suy ra bị viết lại bởi hunk này. Mixed-version phải dùng rule/map mà cả hai đầu đọc được; full-version áp dụng kiểu rule ID trực tiếp. **Evidence confidence:** high cho API và parse error; medium cho placement tùy map thực.

**Kiểm chứng:** trên bản sao CRUSH map, tạo EC/LRC rule ở hai endpoint với `chunk_count` và device class mẫu; decompile rồi so rule ID, bước rule, pool mapping và lỗi khi đưa device class sai. Kiểm cả map cũ có ruleset khác rule ID trước khi thử import vào Quincy.

### OSD-031 — Thay đổi thao tác offline của ceph-objectstore-tool

**CSV:** `src/tools/ceph_objectstore_tool.cc`. Pacific cho `get-superblock`/`set-superblock`; Quincy bỏ hai lệnh khỏi help, file I/O và dispatch, vẫn giữ `dump-super`. Target nhận `--pgid meta` khi lặp object trong collection metadata; `write_pg()` đổi `require_rollback` từ luôn true sang `!info.pgid.is_no_shard()` cho PG không shard; đường FUSE gọi `umount()` sau khi `fuse.main()` kết thúc. Các đổi raw pointer sang `unique_ptr` đi cùng factory OSD-029. Hunk endpoint, commit `b296d3cd1cf`, `4fc80fe0940`, `d5445b8f113`.

**Điều kiện:** runbook/script bảo trì OSD offline dùng hai lệnh superblock đã bỏ, thao tác object của meta collection, import/write PG log hoặc mount FUSE. Mixed-version chạy đúng binary theo bước đang thực hiện; sau full upgrade script phải bỏ phụ thuộc hai lệnh cũ. **Evidence confidence:** high cho CLI và nhánh tool, medium cho hiệu quả dữ liệu của rollback flag cần lab.

**Kiểm chứng:** trên clone store đã dừng OSD, đối chiếu `--help` hai binary, chạy `dump-super`, liệt kê meta collection, thử export/import PG mẫu có và không có shard rồi so PG log/missing; thử FUSE mount và xác nhận umount sạch. Không chạy write/import trên OSD production đang mở.

### OSD-032 — CyanStore hỗ trợ thêm transaction và xattr

**CSV:** `src/crimson/os/cyanstore/cyan_object.h`, `cyan_store.cc`, `.h`. Pacific giữ xattr dưới dạng `bufferptr`; Quincy chuyển sang `bufferlist`, đổi `get_attr` và `_setattrs`, xử lý thêm `OP_SETATTRS`, `OP_RMATTRS`, chấp nhận `OP_SETALLOCHINT` như no-op thành công. Khi set omap, target dùng `insert_or_assign` thay cho `insert`, nên key đã có được ghi đè. `mount()`/`mkfs()` chuyển lỗi đọc/FSID sang errorator có kiểu; hunk endpoint và các commit `2dcb836e2db`, `b214f42d1f1`, `65d0ec3c963`, `677bce0e97c`.

**Điều kiện:** chỉ đường Crimson dùng CyanStore và transaction/xattr/omap tương ứng; không suy từ hunk này rằng BlueStore classic đổi. Trong mixed-version mỗi OSD chạy logic backend của binary mình; full-version dùng nhánh target nếu chọn CyanStore. **Evidence confidence:** high cho operation dispatch và overwrite, medium cho mức dùng CyanStore thực tế.

**Kiểm chứng:** lab CyanStore tạo object có nhiều xattr, chạy setattrs/rmattrs và lặp set cùng một omap key; so giá trị đọc lại, mã lỗi khi thiếu collection/object, mount/mkfs với FSID hợp lệ và sai. Chạy cùng test trên hai endpoint hoặc clone store tương thích.

### OSD-033 — Crimson peering chờ OSD ACTIVE qua state promise

**CSV:** `src/crimson/osd/state.h`. Pacific `OSDState` chỉ lưu enum; Quincy thêm `when_active()` trả future đã sẵn khi ACTIVE, còn lại chờ shared promise. `set_active()` đánh thức waiter, `set_stopping()` trả `system_shutdown_exception` cho waiter. Target `peering_event.cc` gọi gate mới ở các đường xử lý event; commit `0b9dbb7d6ed`. Đây là khác biệt về thời điểm peering event được tiếp tục hoặc hủy khi OSD dừng.

**Điều kiện:** Crimson OSD nhận peering event lúc khởi động/chưa ACTIVE hoặc đang stop. Mixed-version mỗi OSD tự điều phối event theo state machine của mình; full-version dùng promise target. **Evidence confidence:** high cho state/promise và call site, medium cho tần suất race trong tải thật.

**Kiểm chứng:** lab inject peering event trước ACTIVE và trong shutdown có kiểm soát; xác nhận event chờ rồi chạy đúng một lần khi ACTIVE, hoặc nhận shutdown exception và không treo khi stop.

### OSD-034 — Crimson ObjectContext thêm lock ngắt được và dọn cache

**CSV:** `src/crimson/osd/object_context.cc`, `.h`. Pacific `with_lock` và `with_promoted_lock` gọi thẳng lock theo mode, context giữ cờ `loaded`. Quincy thêm overload template bọc callback bằng interruptor, head accessor và intrusive list tracking; `pg.cc` gọi overload `IOInterruptCondition` trong đường load object. Destructor registry đặt mục tiêu LRU về 0 để giải phóng ObjectContext khi teardown (commit `9ae3774bac5`). Các thay đổi này có thể đổi cách request bị hủy khi PG interval thay đổi và vòng đời context lúc shutdown; không suy ra lỗi mất dữ liệu từ riêng hunk này.

**Điều kiện:** Crimson OSD đang truy cập object lúc interval PG đổi hoặc registry được hủy; classic OSD không dùng code path này. Mixed-version xử lý theo binary OSD sở hữu PG/request; full-version dùng lock wrapper và cleanup target. **Evidence confidence:** high cho hunk và call site, medium cho kết quả race cụ thể.

**Kiểm chứng:** lab Crimson đồng thời đọc/ghi cùng object, gây PG remap/primary change và restart; theo dõi request bị interrupt/retry, kết quả object, memory/LSan khi teardown và tình trạng PG sau khi clean.

### OSD-035 — Crimson sắp thứ tự client request và tách giai đoạn commit

**CSV:** `src/crimson/osd/osd_operation.cc/.h`, `osd_connection_priv.h`, `osd_operation_sequencer.h`, `osd_operations/client_request.cc/.h`, `client_request_common.cc/.h`, `osdop_params.h`, `common/pg_pipeline.h`. Pacific dùng `OrderedPipelinePhase` cho client request, xử lý response sau `do_osd_ops` trong một luồng future và retry khi `actingset_changed`. Quincy dùng các phase chung và `OpSequencer` theo connection/PG: khi interval đổi, request cùng session/PG chờ request trước được mở khóa theo thứ tự; khi primary mất thì hủy các request đang chờ. `ClientRequest` tách future `submitted` và `all_completed`, thêm `wait_repop`/`send_reply` và phân biệt hoàn tất theo thứ tự hoặc ngoài thứ tự; metadata params giữ `req_id`/`mtime` thay vì giữ `MOSDOp`. Commit `f7181ab2f65`, `9dcb612b93b`, `be0ba676237`, `2b14df40efe` hỗ trợ các hunk này.

**Điều kiện:** Crimson OSD có nhiều request cùng client/PG, nhất là lúc PG interval hoặc primary đổi, recovery đang chờ, hoặc reply/commit hoàn thành khác thứ tự. Mixed-version mỗi OSD điều phối request theo binary của nó; không suy ra thứ tự xuyên các OSD. Full-version target dùng sequencer mới. **Evidence confidence:** high cho phase, reset/abort và call site, medium cho latency hay lỗi nhìn thấy ở workload thực.

**Kiểm chứng:** lab Crimson gửi chuỗi write/read cùng session vào một PG, gây primary change trong khi request còn in flight; kiểm thứ tự apply/ack, số retry, kết quả object và không có request kẹt. Lặp với object degraded đang urgent recovery; so log `last_unblocked`/`last_completed` ở hai endpoint.

### OSD-036 — Crimson thêm internal client request cho thao tác watch timeout

**CSV:** `src/crimson/osd/osd_operations/internal_client_request.cc/.h`. Pacific chưa có operation nội bộ dùng cùng PG pipeline. Quincy thêm `InternalClientRequest`: đợi PG ACTIVE, recover object nếu thiếu, lấy ObjectContext lock rồi gọi `do_osd_ops`, retry khi acting set đổi và thoát khi shutdown. `WatchTimeoutRequest` trong `watch.cc` kế thừa lớp này để phát `CEPH_OSD_WATCH_OP_UNWATCH`; xem OSD-038. Commit `b5f1eb879e2`, `b5efdc6f1c9`, `4070a7d5577`.

**Điều kiện:** Crimson có watcher hết hạn; operation nội bộ đi qua PG pipeline và có thể bị ngắt bởi map/primary change. Mixed-version watcher do OSD nào quản lý sẽ dùng logic binary OSD đó; full-version target dùng operation mới. **Evidence confidence:** high cho call path, medium cho tỷ lệ timeout thực tế.

**Kiểm chứng:** lab tạo watch với timeout ngắn, ngừng ping và đổi primary gần thời điểm timeout; xác nhận UNWATCH được lưu, notifier nhận kết quả đúng và không còn watcher stale sau restart.

### OSD-037 — Crimson ngắt peering work khi PG đổi interval hoặc dừng

**CSV:** `src/crimson/osd/pg_interval_interrupt_condition.cc/.h`, `osd_operations/peering_event.cc/.h`. Pacific peering event đi qua pipeline future thường. Quincy bổ sung `IOInterruptCondition` so epoch khi bắt đầu với `get_interval_start_epoch()`, phát `actingset_changed` nếu có interval mới hoặc `system_shutdown_exception` khi PG stopping. `PeeringEvent::start()` chuyển sang stage có thể ngắt; remote event còn đợi OSD ACTIVE trước PG lookup và gửi message qua gate ở [OSD-033](#osd-033--crimson-peering-chờ-osd-active-qua-state-promise). Commit `e6d10da26ed`, `2bf9d7b0d06`, `30afadd1629`, `a8279ed7c80`.

**Điều kiện:** Crimson OSD nhận remote peering lúc chưa ACTIVE, PG đổi interval trong khi xử lý event hoặc đang shutdown. Mixed-version mỗi OSD xử lý event theo state/pipeline của binary đó; full-version target có ngắt theo interval. **Evidence confidence:** high cho điều kiện code và gate, medium cho số event bị hủy trong cluster thực.

**Kiểm chứng:** lab làm chậm peering rồi tạo OSDMap mới/primary change, đồng thời thử dừng OSD; kiểm event cũ không dispatch message sau interval mới, event mới tiếp tục và PG về clean. Gửi remote event ngay trước ACTIVE để xác nhận chỉ dispatch sau khi OSD sẵn sàng.

### OSD-038 — Crimson watch/notify có timeout và sửa encoding reply

**CSV:** `src/crimson/osd/watch.cc/.h`. Pacific `got_ping()` là no-op và `notify_reply_t` encode với `DENC_START(1,1)`; Quincy reset watch timer khi connect/ping, hết hạn thì khởi chạy internal UNWATCH (OSD-036) rồi gửi disconnect. Notify có timer riêng; khi hết hạn target đưa danh sách `(gid,cookie)` chưa trả lời vào completion và đặt `-ETIMEDOUT`. `notify_reply_t` bỏ preamble DENC khi encode danh sách reply trong payload completion. Commit `4070a7d5577`, `5db263feff3`, `0b79eba1c05`, `bf6404e2b11`, `97ff102cc6e`.

**Điều kiện:** workload RADOS watch/notify trên Crimson, nhất là client ngừng ping/ack hoặc notification quá hạn. Encoding reply có thể ảnh hưởng client đọc completion trong mixed-version; cần thử với client/version thực trước khi kết luận tương thích. Classic OSD không dùng implementation này. **Evidence confidence:** high cho timer, mã lỗi và byte layout trong source; medium cho tương thích client thực tế.

**Kiểm chứng:** lab dùng client Pacific và Quincy đăng ký watch, gửi notify có/không có ack, dừng ping để kích hoạt timeout; so completion payload, missed watcher list, return code, disconnect và persisted watch sau restart. Thử cả zero watcher và reconnect.

### OSD-039 — Crimson recovery ngắt công việc theo PG interval và có độ trễ khởi chạy

**CSV:** `src/crimson/osd/osd_operations/background_recovery.cc/.h`, `recovery_subrequest.cc`, `replicated_request.cc/.h`, `src/crimson/osd/pg_recovery.cc/.h`, `recovery_backend.cc/.h`. Pacific chạy background/urgent/backfill recovery và replica request qua future thường, với kiểm tra reset ở đầu một số nhánh. Quincy bọc các thao tác đó trong `IOInterruptCondition` của OSD-037, chuyển waiter/join sang future có thể ngắt và đưa `PglogBasedRecovery` qua `sleep` 1 ms trước khi lấy throttle. Khi interval mới xuất hiện hoặc PG dừng, công việc đang đợi có đường hủy thay vì tiếp tục xử lý trên context cũ. Hunk `BackgroundRecovery::start`, `RecoverySubRequest::start`, `RepRequest::start`, `PGRecovery::start_recovery_ops` và các future của `RecoveryBackend`; commit `fdf6d06fc3f`, `e3ad392fd04`, `bf27f409f5e`.

**Điều kiện:** Crimson OSD đang recovery/backfill hoặc xử lý replica request khi PG đổi interval, OSD dừng hay recovery PG log được khởi chạy. Mixed-version mỗi OSD áp dụng cách ngắt của binary đang chạy; sau full upgrade tất cả Crimson OSD dùng đường target. Độ trễ 1 ms là giá trị trong code, không phải ước lượng thời gian recovery của cluster. **Evidence confidence:** high cho hunk và điều kiện ngắt, medium cho ảnh hưởng thời lượng thực.

**Kiểm chứng:** trên lab Crimson, gây degraded PG rồi remap primary/stop OSD khi push/pull/backfill đang chờ; quan sát request cũ bị ngắt, PG mới tiếp tục về clean, không treo waiter. So timestamp khởi chạy PG-log recovery và số op đang chạy giữa hai endpoint; đo client latency/recovery time dưới tải thật trước khi kết luận tác động hiệu năng.

### OSD-040 — Crimson bỏ backfill và scan message thuộc interval cũ

**CSV:** `src/crimson/osd/recovery_backend.cc`. Pacific `handle_backfill` và `handle_scan` dispatch theo opcode mà chưa kiểm `old_peering_msg` ở ngay đầu; `handle_backfill_remove` chưa kiểm `can_discard_replica_op`. Quincy trả về sớm khi `map_epoch`/`query_epoch` cũ hơn `last_peering_reset`, hoặc nguồn replica/message không còn hợp lệ theo OSDMap. `PG::old_peering_msg` và `PG::can_discard_replica_op` là caller context; commit `476979a27bf`. Đây là thay đổi về xử lý message muộn sau peering, không có nghĩa mọi message giữa Pacific và Quincy bị bỏ.

**Điều kiện:** backfill/scan message đến muộn sau PG interval change, nguồn OSD down/reconnect hoặc replica bị loại khỏi acting set. Mixed-version OSD target bỏ các message ấy ở nhánh mới, OSD base dùng đường cũ; full-version target áp dụng đồng nhất. **Evidence confidence:** high cho guard và predicate, medium cho tần suất message muộn trong cluster thực.

**Kiểm chứng:** lab gây backfill rồi đổi primary/OSDMap trước khi message scan, finish hoặc remove đến nơi; so log discard, kết quả object/PG và khả năng recovery tiếp tục với interval mới. Kiểm cả message hợp lệ cùng interval vẫn được xử lý.

### OSD-041 — Crimson dừng khi gặp LOST_REVERT chưa hỗ trợ lúc recover

**CSV:** `src/crimson/osd/pg_recovery.cc` (cùng tệp với OSD-039). Pacific `on_local_recover()` gọi thẳng `recover_got()`. Quincy trước lời gọi đó kiểm object không phải delete, còn missing, `need > recovery_info.version`, PG là primary và log entry mới nhất là `LOST_REVERT`; khi đúng toàn bộ điều kiện, `ceph_abort()` với thông báo `mark_unfound_lost (LOST_REVERT) is not implemented yet`. Commit `1da5a57d081`. Đây là guard xác định đường chưa hỗ trợ, không phải bằng chứng target đã thực hiện revert dữ liệu.

**Điều kiện:** chỉ Crimson PG có chuỗi `mark_unfound_lost revert`/recovery version thỏa guard; cluster không có trạng thái này không đi vào nhánh abort. Mixed-version rủi ro nằm ở OSD Crimson target đang là primary; sau full upgrade vẫn còn guard. **Evidence confidence:** high cho điều kiện code, thấp cho khả năng xuất hiện vì chưa có PG log/As-Is cluster.

**Kiểm chứng:** kiểm PG log và lịch sử `mark_unfound_lost` trên bản sao dữ liệu trước canary; dựng ca lab LOST_REVERT với clone, xác nhận guard và log, kiểm rollback/recovery plan riêng. Không kích hoạt thao tác mất dữ liệu này trên cluster production để thử nghiệm.

### OSD-042 — Giữ vòng đời operation Crimson tới khi future hoàn tất

**CSV:** `src/crimson/osd/shard_services.cc/.h`. Pacific `ShardServices::start_operation()` trả operation và `op->start()` ngay; target gắn một continuation giữ bản sao `op` tới khi future hoàn tất, commit `00ccde23ef8` nêu lỗi dangling `ClientRequest::this`. Target cũng chuyển message gửi OSD/peering sang ownership `MessageURef`, `std::move()` khi dispatch; đây là quản lý lifetime trong tiến trình, chưa chứng minh thay đổi byte trên wire. Những lời gọi `start_operation<ClientRequest>`, `RepRequest` và `RecoverySubRequest` ở `osd.cc` cho thấy đường này áp dụng cho request đang xử lý trong OSD.

**Điều kiện:** Crimson có operation bất đồng bộ còn sống sau khi caller bỏ reference, đặc biệt khi pipeline chờ map/PG hoặc daemon đang dừng. Mixed-version mỗi OSD dùng cách giữ lifetime riêng; full-version target giữ operation qua future. **Evidence confidence:** high cho ownership và call sites, medium cho xác suất chạm lỗi lifetime ở base.

**Kiểm chứng:** lab Crimson tạo nhiều request chờ PG/map rồi remap hoặc restart canary; quan sát crash/use-after-free, request hoàn tất hoặc bị hủy sạch và không còn operation kẹt. Chạy sanitizer trên build lab nếu có; đối chiếu số operation tồn sau shutdown.

### OSD-043 — Crimson đổi nội dung `OI_ATTR` và cách đọc metadata khi recovery

**CSV:** `src/crimson/osd/pg_backend.cc`, `replicated_recovery_backend.cc`; helper context ở `src/osd/osd_types.h` thuộc owner khác. Pacific ghi `object_info_t` vào `OI_ATTR` bằng `encode()` với `soid` thật, rồi đọc bằng constructor/decode thông thường. Quincy gọi `encode_no_oid()`: trước khi encode, helper đổi `soid` sang `hobject_t::get_max()` và phục hồi object trong bộ nhớ sau encode; khi đọc, `load_metadata()` gọi `object_info_t(bl, oid)` để kiểm sentinel và gắn OID từ khóa object. Đường push/pull/recovery cũng chuyển sang `decode_no_oid()`. Commit `3aeea9b7e6f`. Đây là thay đổi **giá trị trường OID trong `OI_ATTR` được lưu**, dù helper hiện vẫn encode một trường OID sentinel; không khẳng định byte length giảm.

**Điều kiện:** Crimson OSD ghi hoặc recover object sau khi chạy Quincy rồi cùng object/store được đọc bởi binary Pacific hoặc đường decode cũ. Target `decode_no_oid()` assert nếu gặp OI cũ có OID thật; chiều ngược lại Pacific decode thường sẽ nhận OID sentinel, nhưng hậu quả thực lên mount/recovery cần thử. Mixed-version khác OSD trong cùng PG có thể trao đổi recovery attr; full-version target vẫn có vấn đề với object chưa được viết lại theo format cũ nếu tồn tại. **Evidence confidence:** high cho encode/decode và điều kiện assert, medium cho tính khả dụng của store thực và đường chuyển đổi vì chưa có thử nghiệm cross-version.

**Kiểm chứng:** trên clone Crimson store có object được Pacific tạo, thử mount và đọc bằng Quincy; tạo/ghi thêm object bằng Quincy, rồi thử đọc bằng Pacific trên bản sao thứ hai. Chạy pull/push giữa OSD hai phiên bản và kiểm `OI_ATTR`, OID, PG clean, lỗi decode/assert. Không dùng phép thử này làm thay đổi store production.

### OSD-044 — Crimson PGBackend ghi thống kê PG và bổ sung operation/error path

**CSV:** `src/crimson/osd/pg_backend.cc/.h`. Pacific nhiều nhánh read/write/create/remove/omap còn TODO cho `delta_stats`; Quincy truyền `object_stat_sum_t` vào backend, cập nhật số object, byte, read/write và whiteout. Hunk `update_size_and_usage`, `truncate_update_size_and_usage` và các nhánh OSDOp thay đổi số PG stats hiển thị; commit `7fe0fc9a576`. Target còn thêm `CEPH_OSD_OP_OMAPRMKEYS`, `cmp_xattr` và chuyển EIO trong read/sparse_read thành `object_corrupted` (commit `e816237374f`, `5313440847e`, `20668770491`). Đây là hành vi Crimson; không suy ra chỉ số của classic OSD đổi theo.

**Điều kiện:** workload Crimson có create/delete/truncate/omap, compare xattr hoặc lỗi đọc thiết bị. Khi rolling upgrade, PG stats và mã lỗi client có thể khác theo primary binary; sau full upgrade nhánh target áp dụng. **Evidence confidence:** high cho các nhánh code, medium cho mức chênh chỉ số thực và phản ứng client.

**Kiểm chứng:** lab Crimson chạy các thao tác RADOS mẫu, so object size và `num_objects/num_bytes/num_rd/num_wr` với dữ liệu thực ở hai endpoint. Thử `OMAPRMKEYS`, compare xattr string/U64 và lỗi EIO giả lập trên clone; đối chiếu mã lỗi và client retry. Kiểm số liệu trước/sau canary theo cùng workload, không dùng riêng delta stats làm kết luận mất dữ liệu.

### OSD-045 — Crimson tách submit/commit và ACK request lặp sau commit

**CSV:** `src/crimson/osd/pg_backend.h`, `replicated_backend.cc/.h`; caller ở `src/crimson/osd/pg.cc` và `client_request.cc` đã nằm trong luồng OSD-035. Pacific `_submit_transaction()` trả một future sau khi local transaction và peer ACK hoàn tất. Quincy trả cặp future `submitted`/`all_completed`; `ReplicatedBackend` giữ `at_version` theo transaction và `shared_promise` để `request_committed()` đợi commit của request đã có trong PG log. `PG::already_complete()` tra reqid trong PG log, sau đó ACK `ACK|ONDISK` cho request lặp khi commit đã xong, thay vì chạy lại OSDOp. Commit `14b322ec022`, `f7181ab2f65`.

**Điều kiện:** client gửi lại request sau timeout/reconnect, hoặc primary Crimson có nhiều write đang chờ replica ACK lúc PG remap. Mixed-version thứ tự ACK/replay tùy OSD đang là primary; full-version dùng đường target. **Evidence confidence:** high cho lookup, promise và ACK path, medium cho xác suất retry thực tế. Không suy từ diff rằng ACK luôn nhanh hơn hoặc bền hơn mọi trường hợp.

**Kiểm chứng:** lab gửi write có reqid cố định, trì hoãn replica ACK rồi gửi lại cùng reqid; kiểm object chỉ áp dụng một lần và duplicate chỉ nhận `ONDISK` sau commit. Lặp khi primary đổi, một replica down và khi PG log không còn reqid; so version/log/ACK với Pacific.

### OSD-046 — Crimson recovery dùng dirty subset và lọc pull/push message cũ

**CSV:** `src/crimson/osd/replicated_recovery_backend.cc/.h`. Pacific chỉ dùng `clean_regions` để giới hạn `copy_subset` và bỏ omap sạch khi `min_peer_features` có `SERVER_OCTOPUS`; Quincy bỏ gate này, đồng thời thêm `can_discard_replica_op()` trước xử lý pull, pull response và push. Đường `submit_push_data()` tách `prep_push_target()`, phân biệt push trọn object với push từng phần, reset xattr/omap và đặt allocation hint khi tạo target mới. Các nhánh push/pull cũng chuyển sang future có thể ngắt khi PG interval đổi. Commit endpoint liên quan `fdf6d06fc3f`, `476979a27bf` (guard tương tự ở backfill), `3aeea9b7e6f` (metadata decode); hunk endpoint của backend là bằng chứng chính.

**Điều kiện:** Crimson OSD recover object sau PG remap, nhận message recovery đến muộn, hoặc dùng dirty-region optimization; Pacific/Quincy đều có feature Octopus, nên riêng việc bỏ feature gate chưa chứng minh thay đổi với cặp peer này. Mixed-version cần thử push/pull ở cả hai hướng, nhất là OI attr ở OSD-043; full-version target dùng đường mới. **Evidence confidence:** high cho branch/message guard, medium cho kết quả dữ liệu và khả năng rollback khi store/peer thực chưa biết.

**Kiểm chứng:** lab tạo object có data, xattr, omap và allocation hint; gây missing replica, sửa một vùng nhỏ rồi recover Pacific→Quincy và Quincy→Pacific. So checksum, attrs, omap, size, PG log và acting set; chèn message cũ sau interval change để kiểm discard, sau đó xác nhận recovery mới hoàn tất.

### OSD-047 — Crimson thử sửa object sau lỗi đọc EIO

**CSV:** `src/crimson/osd/pg.cc/.h`, `ops_executer.h`; nguồn lỗi ở `pg_backend.cc` thuộc OSD-044. Pacific trả lỗi từ đường `do_osd_ops` sau khi nạp lại ObjectContext nếu operation đã sửa nó trong bộ nhớ. Quincy chuyển EIO đọc thành `object_corrupted`; `PG::do_osd_ops_execute()` gọi rollback helper, `repair_object()` đánh dấu object thiếu ở local shard và khởi chạy `UrgentRecovery`, sau đó trả `eagain` cho lớp request thực hiện lại. Commit `f76bda83fd6`, `dd6dec306ce` và hunk endpoint chứng minh đường gọi; việc phục hồi thành công còn phụ thuộc replica còn bản tốt.

**Điều kiện:** Crimson primary đọc object gặp EIO, PG có nguồn recovery dùng được. Trong mixed-version, phản ứng tùy primary chạy Pacific hay Quincy; sau full upgrade nhánh target áp dụng. Đây là thao tác tự động trong tiến trình, không phải lệnh repair toàn cluster. **Evidence confidence:** high cho đường EIO→missing→urgent recovery→retry; medium cho kết quả trên store và lỗi thật. Chưa có test runtime được chạy cho tình huống này.

**Kiểm chứng:** trên clone/lab Crimson inject EIO khi đọc object có replica tốt, so PG missing/recovery log, checksum object và phản hồi request sau retry. Thử thêm trường hợp không còn replica tốt, remap trong lúc repair và restart canary; xác nhận lỗi không tạo vòng retry vô hạn. Không inject EIO trên dữ liệu production.

### OSD-048 — Crimson lọc peering event cũ và dọn công việc khi PG dừng

**CSV:** `src/crimson/osd/pg.cc/.h`. Pacific `do_peering_event()` chỉ bỏ event nếu PG reset sau `epoch_requested`; Quincy kiểm thêm `epoch_sent`, nên event gửi từ interval cũ có thể bị bỏ dù request epoch chưa cũ. Khi `PG::stop()`, target hủy local/remote recovery reservation và hai timer readable/lease trước khi stop gate; `on_change()` còn interrupt các ObjectContext đang truy cập. `PG::with_locked_obc()` dùng `RWEXCL` cho nhánh exclusive thay vì `RWWRITE`. Commit `39f9cb81742`, `6b04b96991a`, `d6c931dc788`; interrupt lock liên quan [OSD-034](#osd-034--crimson-objectcontext-thêm-lock-ngắt-được-và-dọn-cache) và [OSD-037](#osd-037--crimson-ngắt-peering-work-khi-pg-đổi-interval-hoặc-dừng).

**Điều kiện:** Crimson PG đổi interval giữa lúc event được yêu cầu/gửi, hoặc dừng khi còn reservation, timer, request chờ lock. Mixed-version mỗi OSD quyết định discard và cleanup theo binary mình; full-version dùng guard/cleanup target. **Evidence confidence:** high cho predicate và lời gọi cancel/interrupt, medium cho race và hệ quả quan sát trong cluster thực. Chưa suy ra peering sẽ nhanh hơn.

**Kiểm chứng:** lab trì hoãn peering event qua primary remap, ghi `epoch_requested`, `epoch_sent`, `last_peering_reset` và xác nhận event cũ bị bỏ, event mới vẫn đưa PG về clean. Dừng Crimson PG đang giữ recovery reservation/timer và có request chờ ObjectContext; xác nhận waiter kết thúc, reservation trả lại và restart không kẹt.

### OSD-049 — Crimson triển khai `LIST_WATCHERS` cho object

**CSV:** `src/crimson/osd/ops_executer.cc`; API/dispatch ở `.h` có cùng row với OSD-036/038/044/045/047. Pacific không có case `CEPH_OSD_OP_LIST_WATCHERS` trong `OpsExecuter::execute_op`; Quincy tạo `obj_list_watch_response_t` từ `os.oi.watchers` và dispatch op mới. Commit `12fd597cc68`. Source target gọi `response.encode(osd_op.outdata, features)` **bên trong** vòng lặp và không gọi khi danh sách rỗng; vì thế payload với 0 hoặc nhiều watcher cần xác minh bằng client, chưa khẳng định đầu ra hợp lệ. Các test `src/test/librados/watch_notify_cxx.cc` kiểm API watcher của librados nói chung, không tự chứng minh đường Crimson này.

**Điều kiện:** client dùng RADOS list watchers trên Crimson, kể cả bước xác minh watch sau nâng cấp; classic OSD không dùng implementation này. Mixed-version kết quả tùy primary xử lý request; sau full upgrade đường target áp dụng. **Evidence confidence:** high cho dispatch/vị trí encode, medium cho khả năng client decode và tác động vì chưa chạy test Crimson end-to-end.

**Kiểm chứng:** lab gọi `list_watchers` bằng client Pacific/Quincy vào Crimson object có 0, 1, 2 watcher trước/sau canary; so return code, payload raw/decoded, số entry và cookie, rồi thử lại sau watcher timeout và PG remap. Nếu dùng lệnh này làm gate rollout, kiểm thêm cùng thao tác trên classic OSD để tách đường implementation.

### OSD-050 — Crimson bind lại heartbeat và điền IP công bố khi trống

**CSV:** `src/crimson/osd/heartbeat.cc/.h`; caller context `src/crimson/osd/osd.cc` còn trong hàng chưa phân loại và `src/crimson/net/SocketMessenger.cc` thuộc owner khác. Pacific `Heartbeat::start_messenger()` gọi `try_bind()` một lần trên dải port cấu hình rồi abort nếu thất bại. Quincy gọi `bind()`, hiện thực target lặp `try_bind()` theo `ms_bind_retry_count`/`ms_bind_retry_delay` trước khi báo lỗi. Target cũng lộ front/back messenger; `_send_boot()` gọi `set_addr_unknowns()` để thay blank IP của cluster/heartbeat bằng địa chỉ public/cluster đã biết trước khi gửi `MOSDBoot` cho MON. Hunk endpoint và commit `d5f96ce9474`, `ce1ca97f840` là bằng chứng. Phần message send đổi ownership, không có bằng chứng byte wire thay đổi trong hunk này.

**Điều kiện:** Crimson OSD khởi động với port tạm bận hoặc cấu hình không chỉ rõ public/cluster IP khiến địa chỉ công bố ban đầu trống. Mixed-version chỉ OSD target có retry/điền IP này; sau full upgrade các Crimson OSD đều dùng đường target. Nếu địa chỉ được đặt rõ và port rảnh, khác biệt có thể không lộ ra. **Evidence confidence:** high cho bind/retry và đường `_send_boot`, medium cho kết nối heartbeat thực tế tùy mạng/config cluster. Chưa chạy lab.

**Kiểm chứng:** trong lab, chiếm tạm port đầu dải và khởi động Crimson ở hai endpoint, ghi thời gian bind, số lần thử, port thực dùng và log lỗi. Lặp khi bỏ public/cluster IP trong cấu hình rồi kiểm `MOSDBoot`/OSDMap chứa front/back/cluster IP có thể kết nối; xác nhận heartbeat hai chiều và trạng thái OSD sau restart canary.

### OSD-051 — Điều kiện biên dịch làm thay đổi độ phủ test Clay/ISA

**CSV:** `src/test/erasure-code/TestErasureCodePluginClay.cc`; context build ở `src/test/erasure-code/CMakeLists.txt` thuộc owner 13. Pacific chỉ chạy nhánh `scalar_mds=isa` trong test Clay khi macro C++ `HAVE_NASM_X64_AVX2` được định nghĩa. Quincy đổi guard sang `WITH_EC_ISA_PLUGIN`; commit `bed1b32974f` đặt biến này ở CMake cache khi NASM AVX2 hoặc ARMv8 SIMD khả dụng, và dùng biến để tạo target test ISA. Trong cây `v17.2.7`, tìm kiếm `WITH_EC_ISA_PLUGIN` chỉ thấy các điều kiện CMake và `#ifdef` ở test Clay, không thấy chỗ truyền thành macro C++ mặc định. Vì vậy nhánh Clay/ISA có thể bị bỏ qua trong build test target dù plugin/test ISA vẫn được build. Đây là thay đổi **độ phủ kiểm chứng**, không chứng minh plugin ISA chạy sai trên OSD.

**Điều kiện:** pipeline rehearsal/acceptance dùng unit test này và build có ISA plugin; trên môi trường không có ISA plugin, nhánh vốn đã không chạy. Mixed-version không có tương tác wire do chính tệp test này; sau full upgrade, kết quả test target có thể thiếu kiểm tra Clay `scalar_mds=isa`. **Evidence confidence:** high cho guard/CMake endpoint, medium cho command line biên dịch cụ thể của pipeline chưa biết.

**Kiểm chứng:** với build config dùng để nghiệm thu, đọc compile command hoặc preprocessor output của `unittest_erasure_code_plugin_clay` để xác nhận macro; chạy `--gtest_list_tests` và test trên hai endpoint với ISA khả dụng, kiểm nhánh `scalar_mds=isa` thực sự được thực thi. Nếu pipeline không dùng test này làm gate thì finding chỉ là cảnh báo về coverage repository.

### OSD-052 — QA recovery đổi scheduler, giới hạn và thời gian chờ

**CSV:** `qa/standalone/erasure-code/test-erasure-eio.sh`, `qa/standalone/osd/osd-recovery-prio.sh`, `osd-recovery-space.sh`, `osd-recovery-stats.sh`, `osd-rep-recov-eio.sh`, cùng bốn script `qa/standalone/osd-backfill/osd-backfill-{prio,recovery-log,space,stats}.sh` được chuyển từ `qa/standalone/osd/`. Pacific chạy các script với config cũ: priority test không ép WPQ, các test giới hạn backfill không bật override mClock, và vòng chờ recovery/backfill ngắn hơn. Quincy ép `osd-op-queue=wpq` trong cả priority test recovery/backfill; bốn script EC EIO, recovery-space, backfill-recovery-log và backfill-space bật `osd_mclock_override_recovery_settings=true`; các vòng poll/timeout đổi `100→240`, `60→300`, `100→360`, `240→1200` và `60→240` tùy test. Option target trong `src/common/options/osd.yaml.in` mặc định false và mô tả rằng mClock sẽ reset giới hạn recovery/backfill nếu không bật override. Commit liên quan `f658ff35112`, `2c577040cbc`, `bdf36cf045b`, `7f023b06a16` và commit chuyển thư mục `0f65e5cffa2`. Đây là thay đổi **cách chạy và tiêu chí đỗ test**, không tự chứng minh recovery runtime nhanh/chậm hơn.

**Điều kiện:** pipeline lab/acceptance thật sự chạy các script này. Nếu không, các hunk QA không tác động trực tiếp cluster. Trong mixed-version, test với script target có thể chạy WPQ hoặc override mClock dù cấu hình production khác; sau full upgrade, kết quả test target vẫn chịu cấu hình và timeout mới. **Evidence confidence:** high cho diff/config option, medium cho mức dùng script của dự án chưa biết.

**Kiểm chứng:** ghi lệnh và environment khi chạy test, scheduler/profile và `osd_max_backfills` hiệu dụng của từng OSD. Chạy lại priority test với WPQ đúng như script và một ca mClock riêng; ghi thời điểm xuất hiện `backfill_unfound`, thời gian recovery, PG state và pass/fail theo timeout hai endpoint. Không lấy kết quả WPQ thay cho kiểm chứng mClock của cụm nếu mClock là scheduler dự kiến.

### OSD-053 — QA scrub đổi scheduler và mẫu kiểm tra kết quả

**CSV:** `qa/standalone/scrub/osd-scrub-dump.sh`, `osd-scrub-repair.sh`, `osd-scrub-snaps.sh`. Pacific chạy dump/auto-repair scrub với scheduler hiệu dụng của test và kiểm chuỗi `scrubbing` hoặc số cảnh báo scrub cụ thể. Quincy ép WPQ trong dump và ca auto-repair, đổi grep thành `+scrubbing`, cho phép hai cách đếm cảnh báo thường/deep trong `TEST_scrub_warning`, và đổi hai regex snap mapper sang dạng tập `{1, 2, ...}`. `osd-scrub-repair.sh` còn đổi setup/teardown của ca auto-repair; hunk này cần kiểm trong harness khi chạy lại. Commit `33d2a2c93b5`, `9dda986bd52`, `20dd0227151`, `1ec46515765`. Các thay đổi này tác động kết quả QA nếu script được dùng làm gate, không tự chứng minh sửa lỗi scrub runtime.

**Điều kiện:** pipeline lab/acceptance chạy ba script; ca WPQ không bao phủ scheduler mClock mặc định của Quincy. Mixed-version không có wire change từ script; sau full upgrade, tiêu chí pass/fail target khác Pacific. **Evidence confidence:** high cho diff test, medium cho thực thi pipeline và hành vi scrub dưới config cụ thể chưa biết.

**Kiểm chứng:** chạy script trên lab với scheduler và config đã ghi lại; xác nhận `+scrubbing` xuất hiện đúng lúc, các cảnh báo scrub trong `ceph health detail` khớp trường hợp thường/deep, log snap mapper khớp regex target, và auto-repair setup/teardown không để lại daemon/tệp. Chạy một ca mClock riêng nếu cluster sẽ dùng mClock.

### OSD-054 — `ceph_test_rados` mở rộng bài thử dedup và refcount

**CSV:** `src/test/osd/Object.h`, `RadosModel.h`, `TestRados.cc`, `qa/tasks/rados.py`, cùng hai recipe mới `qa/suites/rados/thrash/workloads/dedup-io-mixed.yaml` và `dedup-io-snaps.yaml`. Pacific có `SetChunkOp` với offset/length/target được chọn trước, nhưng chưa có chuỗi op dedup đầy đủ trong test driver và chưa kiểm refcount chunk cuối bài. Quincy thêm `flushed` vào `ObjectDesc`, cấu hình pool `dedup_tier`, `dedup_chunk_algorithm`, `dedup_cdc_chunk_size`, chọn set-chunk range/snapshot trong op, tạo chunk theo SHA256 ở trường hợp target rỗng, thêm `TierEvictOp` và trạng thái flush. Driver nhận `--dedup_chunk_algo`/`--dedup_chunk_size`, thêm weight `set_chunk`/`tier_evict`, rồi gọi `check_chunks_refcount()` và trả lỗi nếu kiểm tra thất bại. `qa/tasks/rados.py` chuyển các khóa chunk và op weight mới thành tham số CLI; hai recipe target gọi các op/cấu hình này, ca `dedup-io-snaps` thêm tạo/xóa snapshot và rollback. Commit tiêu biểu `cc3c26997df`, `788fddc7960`, `dd7b5029518`, `0c971cb3d3c`, `9e8601ddf54`, `dfce69e995c`. Đây là mở rộng bài thử dữ liệu/refcount, không tự chứng minh runtime dedup của OSD đã đổi theo cùng cách.

**Điều kiện:** pipeline validation chạy `ceph_test_rados` với `enable_dedup` và các recipe dedup mới; cluster không dùng dedup hoặc không chạy ca này thì không có hiệu ứng từ riêng tệp test. Mixed-version cần biết OSD nào xử lý op và pool feature/config hiệu dụng; sau full upgrade test target có thêm ca và tiêu chí refcount. **Evidence confidence:** high cho hunk/recipe, medium cho kết quả test và tính dùng dedup của cluster chưa biết. Test chưa được chạy.

**Kiểm chứng:** trong lab tạo tier/chunk pool theo recipe, chạy mixed-version và full-version với seed/weight được ghi lại; so dữ liệu đọc, snapshot, `TierFlush`/`TierEvict`, xattr refcount chunk và return code của `ceph_test_rados`. Ghi rõ nếu test fail do CLI/config test thay vì do dữ liệu. Nếu đây là gate rollout, lặp cả pool không bật dedup để tách tác động của feature.

### OSD-055 — Bộ lọc log thay đổi tiêu chí đỗ QA của bài thử RADOS

**CSV:** `qa/suites/rados/thrash/workloads/set-chunks-read.yaml`, hai recipe dedup ở OSD-054, 20 recipe khác trong cùng thư mục, 28 recipe dưới `qa/suites/rados/singleton/all/`, 10 recipe dưới `qa/suites/rados/singleton-nomsgr/all/`, ba recipe `qa/suites/rados/multimon/tasks/`, 16 recipe thuộc các nhóm `basic/tasks`, `mgr/tasks`, `objectstore/backends`, 14 recipe `thrash-erasure-code*/thrashers/`, năm recipe `monthrash/thrashers/`, và các recipe `perf/ceph.yaml`, `rest/mgr-restful.yaml`, `valgrind-leaks/1-start.yaml`. Pacific các recipe này chưa lọc cảnh báo `POOL_APP_NOT_ENABLED`; Quincy thêm nó vào `ceph.log-ignorelist` trong task hoặc `overrides`. Ở endpoint target `qa/tasks/ceph.py`, `log-ignorelist` được truyền vào `cluster()`; cuối task, `first_in_ceph_log()` loại các dòng khớp pattern trước khi đánh dấu lỗi `[ERR]`, `[WRN]` hoặc `[SEC]` trong cluster log. Commit `13507e85615` liên quan cảnh báo ứng dụng pool. Bởi vậy cùng một cảnh báo có thể không còn làm bài thử thất bại, nhưng bộ lọc không có tác dụng đổi trạng thái runtime của pool. Tệp `pool-snaps-few-objects.yaml` trong cụm thrash còn đặt filter dưới khóa `override` số ít thay vì `overrides`; hàng này chưa được phân loại vì chưa xác nhận teuthology có đọc khóa đó. Các hunk khác trong một số recipe được ghi riêng ở OSD-003/062/063/065–070/084.

**Điều kiện:** teuthology chạy một trong các recipe đã phân loại và phát cảnh báo `POOL_APP_NOT_ENABLED` trong cluster log. Trong mixed-version hoặc full-version, kết quả test phụ thuộc recipe/filter được chạy, không chỉ binary OSD. **Evidence confidence:** high cho cấu hình recipe và mã quét log, medium cho việc pipeline dự án có chạy recipe này hay không. Chưa chạy test.

**Kiểm chứng:** trên lab chạy recipe với/không có filter khi pool tạo chưa bật application; ghi cluster log, health detail và kết quả `ctx.summary`. Xác nhận các cảnh báo/lỗi khác vẫn làm test fail. Nếu recipe là gate nâng cấp, giữ thêm một kiểm tra riêng cho trạng thái application của pool thay vì suy từ kết quả test đã lọc.

### OSD-056 — Bài thử divergent PG đợi primary hợp lệ trước khi chọn OSD

**CSV:** `qa/standalone/osd/divergent-priors.sh`. Trong `TEST_divergent_3`, Pacific gọi `flush_pg_stats`/`wait_for_clean` một lần rồi lấy `up_primary` của phần tử PG đầu tiên; giá trị có thể là `-1` nếu PG đầu tiên còn `unknown`. Quincy lặp các bước đó đến khi `up_primary >= 0`, với giới hạn 300 giây, rồi mới dùng OSD đó làm `divergent`. Commit `5ec51044ef7` mô tả chính ca chọn `-1`; hunk endpoint cho thấy điều kiện vòng lặp và lỗi timeout. Đây là khác biệt về chọn mục tiêu và pass/fail của bài thử, không phải thay đổi trực tiếp peering runtime.

**Điều kiện:** pipeline chạy bài thử divergent-priors trong lúc autoscaler tạo PG khiến phần tử đầu tiên chưa có primary. Trong mixed-version hoặc full-version, kết quả còn tùy script Pacific/Quincy được dùng; target tránh chọn `-1` nhưng có thể fail sau 300 giây. **Evidence confidence:** high cho logic script, medium cho tần suất trạng thái `unknown` trong lab cụ thể. Chưa chạy bài thử.

**Kiểm chứng:** trong lab tạo pool autoscale và giữ PG đầu tiên ở trạng thái chưa có primary có kiểm soát; ghi `up_primary`, thời gian chờ và OSD được chọn. Xác nhận bài thử tiếp tục khi primary hợp lệ, fail rõ ràng khi quá 300 giây, rồi kiểm divergent PG trở lại clean theo mục tiêu test.

### OSD-057 — Bài thử PG log kiểm thêm duplicate và thay ngưỡng trim

**CSV:** `qa/standalone/osd/repro_long_log.sh`. Pacific `test_log_size()` chỉ so `log_size`; Quincy đọc thêm `info.stats.log_dups_size`, đặt `osd_pg_log_dups_tracked=20` trong setup, truyền giới hạn duplicate khác khi gọi `ceph-objectstore-tool --op trim-pg-log`, đổi kỳ vọng test offline từ `2` thành `21` entry chính và `18` duplicate, rồi thêm `TEST_trim_max_entries_with_dups`. Các commit `8f0fb8da372`, `8ecd12f8390` và hunk endpoint cho thấy tiêu chí mới. Trường `log_dups_size` là một phần PG stats target ở [OSD-022](#osd-022--mở-rộng-wire-format-và-dump-của-pg-stats); test không chứng minh mọi PG production sẽ có các số đó.

**Điều kiện:** runbook/lab dùng script để xác nhận PG log trimming hoặc khả năng đọc stats sau nâng cấp. Mixed-version nên chạy công cụ và query theo phiên bản phù hợp vì Pacific không có cùng output `log_dups_size`; sau full upgrade, bài thử target đòi cả hai chỉ số. **Evidence confidence:** high cho test input/expected output, medium cho kết quả trên store thật chưa thử.

**Kiểm chứng:** trên cluster lab hoặc clone OSD store, chạy bài thử với pool/PG mẫu; ghi `log_size`, `log_dups_size`, cấu hình `osd_pg_log_dups_tracked`, return code của objectstore tool và trạng thái PG sau OSD restart. So bản Pacific/Quincy theo đúng cấu hình mỗi test; nếu dùng offline trim, chỉ thao tác trên store đã dừng trong lab.

### OSD-058 — QA BlueFS thêm đường mở rộng thiết bị và kiểm tra offline

**CSV:** `qa/standalone/osd/osd-bluefs-volume-ops.sh`. Pacific `TEST_bluestore2` ghi một lượt để tạo spillover rồi kiểm `slow_used_bytes`; Quincy thử ghi lại tối đa vài lượt trước khi kiểm. Target còn thêm `TEST_bluestore_expand`: tạo OSD BlueStore có DB riêng, ghi dữ liệu, dừng OSD, chạy `ceph-bluestore-tool allocmap`/`fsck`, mở rộng file block, gọi `bluefs-bdev-expand`, chạy `fsck`/`qfsck`, khởi động lại rồi so thông tin dung lượng. Commit `efb67445c24`, `a39b1f3cf7b` và hunk endpoint là bằng chứng. Runtime target `BlueStore::expand_devices()` ghi thêm vùng free vào allocation file khi dùng null manager; phạm vi/guard của `allocmap` xem [BLU-001](./02-bluestore-bluefs.md#blu-001--allocation-map-có-thể-chuyển-khỏi-rocksdb) và [BLU-004](./02-bluestore-bluefs.md#blu-004--công-cụ-phục-hồi-bluestore-đổi-cách-khởi-tạo-và-lệnh).

**Điều kiện:** chỉ liên quan nếu dự án định dùng bài thử hoặc thao tác mở rộng BlueFS/BlueStore offline trong rehearsal/upgrade. Code test target có `retry = 0` và `if [$total_space_after != $requested_space]` thiếu khoảng trắng quanh cú pháp shell, nên cần xác nhận nhánh kiểm dung lượng thực sự chạy; riêng diff không chứng minh test đã pass hoặc expansion an toàn. Mixed-version cần dùng đúng binary tool cho store đang thử và thử rollback trên clone; sau full upgrade đường target áp dụng khi operator gọi tool. **Evidence confidence:** high cho chuỗi lệnh trong script và nhánh `expand_devices`, medium cho giá trị bài thử vì chưa chạy script/build cụ thể.

**Kiểm chứng:** trên clone store hoặc lab, trước tiên xác nhận build hỗ trợ `allocmap`/`qfsck` và kiểm shell exit code ở các nhánh test; sau đó đo kích thước slow/DB, free space, trạng thái allocation file và `fsck`/`qfsck` trước/sau `bluefs-bdev-expand`. Restart OSD, đọc lại object và xác nhận PG clean. Không dùng script này trên store production đang hoạt động.

### OSD-059 — QA yêu cầu scrub xảy ra đồng thời với recovery

**CSV:** `qa/standalone/scrub/osd-recovery-scrub.sh`. Pacific `TEST_recovery_scrub_2` dùng 4 object, phát hiện recovery từ log hoặc PG state và chờ các scrub background; chưa đòi chứng minh một scrub xảy ra trong lúc PG đang recover. Quincy tăng lên 40 object, đặt `osd_recovery_sleep=10` trong lab, chờ ít nhất hai PG có state `recovering` rồi `pg_scrub_mod()` trả mã 2 nếu đã quan sát recovery ngay sau lệnh scrub. `wait_background_check()` đếm mã 2 và bài thử fail nếu count bằng 0. Commit `eec821b6e51`, `dd63577ab37`, `b8045f7b183` cần được đọc theo endpoint vì có thay đổi trung gian được revert. Đây là thay đổi điều kiện nghiệm thu cho concurrency, không chứng minh scrub production luôn chạy khi recovery.

**Điều kiện:** pipeline chạy standalone recovery/scrub test với config làm chậm recovery. Mixed-version hay full-version đều phải ghi script/config thực dùng vì timeout và concurrency được tạo bởi bài thử; sau full upgrade target áp dụng gate mới. **Evidence confidence:** high cho điều kiện script, medium cho tính tái lập và thời điểm PG state quan sát được. Chưa chạy test.

**Kiểm chứng:** lab tạo 32 PG/40 object như script, giữ `osd_recovery_sleep=10`, ghi PG state, thời điểm scrub request và kết quả từng background PID. Xác nhận ít nhất một PG được scrub khi recovery đang diễn ra và mọi PG về clean; lặp với workload mClock/WPQ dự kiến để tách ảnh hưởng scheduler.

### OSD-060 — QA mới làm hỏng SnapMapper rồi kiểm deep-scrub sửa lại

**CSV:** `qa/standalone/scrub/osd-mapper.sh`, helper `scrub-helpers.sh`. Pacific không có bài thử này. Quincy tạo clone/snapshot, dừng OSD lab, sửa khóa `SNA_` trong BlueStore KV thành dạng bị cắt, khởi động lại, deep-scrub để phát hiện lỗi, deep-scrub lần nữa để kiểm không thêm lỗi, rồi đếm khóa SnapMapper có dạng đầy đủ. `standard_scrub_cluster()` và `set_query_debug()` ở helper chuẩn bị môi trường. Commit `16f23ca1732`, `53f1440a090`. Bài thử mới tăng độ phủ repair SnapMapper nhưng có thao tác cố ý làm hỏng KV, chỉ phù hợp dữ liệu lab/clone.

**Điều kiện:** pipeline chạy bài thử và build có `ceph-kvstore-tool`; không áp dụng trực tiếp trên cluster đang phục vụ dữ liệu. Mixed-version phải nêu binary dùng để đọc/sửa KV và OSD đang primary; sau full upgrade test target có thêm ca này. **Evidence confidence:** high cho trình tự script, medium cho kết quả repair vì chưa chạy trong môi trường dự án.

**Kiểm chứng:** trên clone, ghi key `SNA_`/snapshot trước test, chạy ca hỏng được kiểm soát, đối chiếu log `ERR` lần deep-scrub đầu với lần hai và số key đầy đủ trước/sau. Kiểm `rados listsnaps`, object data và PG clean sau restart; dừng ngay nếu bài thử thao tác sai đường dẫn lab.

### OSD-061 — QA lịch scrub mới dùng `pg query` và `pg dump`

**CSV:** `qa/standalone/scrub/osd-scrub-test.sh`, `scrub-helpers.sh`. Pacific test scrub có setup/teardown tại từng ca. Quincy chuyển phần lớn setup/teardown vào `run()`, thêm helper đọc schedule/active/duration từ `pg query` và `pg dump`, tạo ca `noscrub`/deep-scrub cho bug #52901, ca kiểm lịch, duration và `objects_scrubbed`, đồng thời ép WPQ cho một số ca timing. Commit `7008b85fc56`, `10909c3cba6`, `91885f1a877`, `33d2a2c93b5`. `wait_any_cond()` trong helper trả thành công nếu **bất kỳ** predicate nào khớp, không bắt tất cả; `TEST_pg_dump_objects_scrubbed` ở endpoint vẫn gọi setup/teardown riêng bên trong dù runner đã gọi, nên độ mạnh và vòng đời bài thử cần xác minh. Các hunk thay đổi tín hiệu nghiệm thu scrub, không tự chứng minh mClock production có lịch tương tự.

**Điều kiện:** pipeline sử dụng các standalone scrub tests; một số ca chọn WPQ khác default mClock Quincy. Mixed-version phải ghi scheduler và format `pg query`/`pg dump` của OSD đang xử lý PG; sau full upgrade ca target kiểm các trường stats mới. **Evidence confidence:** high cho cấu trúc helper/script, medium cho kết quả test thực và tác động setup lặp. Chưa chạy test.

**Kiểm chứng:** trên lab, chạy từng test riêng với log setup/teardown, xác nhận ca `noscrub` không chạy deep scrub trước khi unset rồi chạy sau unset; so `last_scrub_duration`, `objects_scrubbed`, schedule ở `pg query`/`pg dump` với event thực. Với ca cần hai điều kiện đồng thời, kiểm cả hai độc lập vì `wait_any_cond()` chỉ đòi một; thử riêng mClock nếu là scheduler triển khai.

### OSD-062 — Recipe RADOS API mở nạp object class cho test

**CSV:** `qa/suites/rados/thrash/workloads/rados_api_tests.yaml`, `qa/suites/rados/basic/tasks/rados_api_tests.yaml`, `qa/suites/rados/monthrash/workloads/rados_api_tests.yaml`, `qa/suites/powercycle/osd/tasks/rados_api_tests.yaml` và `qa/workunits/rados/test.sh`. Pacific các recipe `rados/test.sh` không override danh sách class của OSD. Quincy thêm `osd class load list: "*"` và `osd class default list: "*"` dưới `overrides.ceph.conf.osd`; `ClassHandler::open_all_classes()` trong target đi qua các class trong thư mục và chỉ bỏ class không nằm trong load list. Workunit target thêm `api_cls_remote_reads` vào tập bài chạy. Commit `7d0ea1b8617` nêu mục đích cho các test remote-read nạp object class. Recipe `basic` đồng thời bỏ nhiều mẫu ignorelog cũ ở OSD-067; recipe `monthrash` bỏ một filter ở OSD-083. Đây là thay đổi cấu hình/độ phủ của workload QA, không suy ra production OSD tự động mở mọi class.

**Điều kiện:** pipeline chạy recipe RADOS API này; nếu production dùng class allowlist chặt hơn, kết quả test với `"*"` không đại diện hoàn toàn cho production. Mixed-version mỗi OSD có danh sách class hiệu dụng riêng; sau full upgrade script target vẫn ghi đè danh sách trong lab. **Evidence confidence:** high cho recipe và call site, medium cho class thực sự được gọi trong pipeline chưa chạy.

**Kiểm chứng:** lab chạy `rados/test.sh` với recipe target, ghi `osd class load list`/`default list` hiệu dụng và các class đã load trên OSD. Lặp với allowlist dự kiến của cluster để xác nhận các op class cần thiết vẫn chạy; giữ riêng kết quả của test với wildcard và test với cấu hình production.

### OSD-063 — Recipe singleton chặn tạo pool `.mgr` trước khi chạy bài thử

**CSV:** 33 recipe dưới `qa/suites/rados/singleton/all/`, 17 recipe dưới `qa/suites/rados/singleton-nomsgr/all/`, `qa/suites/rados/multimon/no_pools.yaml` và `qa/suites/rados/thrash-erasure-code/thrashers/minsize_recovery.yaml` đặt `mgr_pool false` trong `pre-mgr-commands`; 51 recipe đổi từ `ceph config set mgr mgr/devicehealth/enable_monitoring false --force`, còn `crushdiff.yaml` mới dùng lệnh này ngay từ đầu. Hunk endpoint và commit `d6c66f3fa61` cho thấy mục tiêu giữ môi trường test không có pool MGR: cách cũ chỉ tắt devicehealth monitoring, còn `mgr_pool` của Quincy mặc định `true` và chặn `MgrModule.db` mở/tạo `.mgr` khi đặt `false`. `qa/tasks/ceph.py` chạy danh sách `pre-mgr-commands` lúc khởi động MON, trước daemon MGR. Tệp `.disabled` trong suite thứ nhất cũng đổi lệnh nhưng vẫn chưa được gắn nhãn vì chưa xác nhận đường thực thi. Đây là thay đổi setup QA, có liên hệ [MGR-001](./07-mgr-modules-monitoring.md) về pool `.mgr`, không phải chỉ dẫn tắt pool này trên cluster sản xuất.

**Điều kiện:** pipeline chọn một recipe đã phân loại và chạy lệnh trước MGR. Trong mixed-version, cần kiểm lệnh và tùy chọn được daemon thực dùng chấp nhận; không thể suy từ recipe target rằng MGR Pacific cũng có `mgr_pool`. Sau full upgrade, recipe target có thể giữ baseline không có `.mgr` khi module dùng DB. **Evidence confidence:** high cho lệnh, thứ tự task và guard tạo DB ở endpoint Quincy; medium cho pool thực tế trong từng bài test vì chưa chạy pipeline.

**Kiểm chứng:** trên lab chạy recipe với bản MGR và MON tương ứng, lưu effective config `mgr_pool`, `mgr/devicehealth/enable_monitoring`, danh sách pool trước/sau MGR khởi động và kết quả workunit. Lặp với recipe Pacific cùng điều kiện để xác nhận bài thử về số pool không bị pool nền làm sai. Với mixed-version, ghi riêng kết quả lệnh `ceph config set` và trạng thái MGR; không áp dụng cấu hình này cho production từ kết quả QA.

### OSD-064 — Admin socket QA cho phép lệnh dự phòng `dump_metrics memory`

**CSV:** `qa/suites/rados/singleton/all/admin-socket.yaml`. Pacific yêu cầu ba lệnh `get_heap_property`/`set_heap_property` trên admin socket OSD. Quincy thêm `|| dump_metrics memory` cho từng lệnh; task `qa/tasks/admin_socket.py` ở endpoint target tách chuỗi tại `||`, thử lần lượt và nhận JSON từ lệnh đầu thành công. Commit `cec7c15f196` đổi recipe, `83e4edcd80b` thêm khả năng thử lệnh dự phòng trong task. Cùng tệp còn thêm lọc `POOL_APP_NOT_ENABLED` ở OSD-055. Lệnh dự phòng có thể làm QA đỗ khi lệnh tcmalloc gốc thất bại, nên kết quả đỗ không tự xác nhận ba thao tác heap đã chạy.

**Điều kiện:** pipeline dùng recipe admin socket, đặc biệt binary/allocator không hỗ trợ lệnh tcmalloc. Trong mixed-version, đường được thực thi phụ thuộc admin socket của OSD được chọn và phiên bản task QA; sau full upgrade, recipe target có fallback. **Evidence confidence:** high cho fallback trong code/recipe, medium cho trường hợp allocator và binary cụ thể chưa được kiểm.

**Kiểm chứng:** lab chạy cùng recipe với OSD có và không có các lệnh heap, ghi lệnh nào trả lỗi, lệnh nào tạo JSON hợp lệ và kết quả task; xác nhận phép thử riêng nếu cần bảo đảm chức năng chỉnh heap của tcmalloc, vì recipe target có thể đi qua fallback.

### OSD-065 — Recipe MON auth bổ sung bài thử xoay khóa pending

**CSV:** `qa/suites/rados/singleton/all/mon-auth-caps.yaml` thêm `mon/auth_key_rotation.sh` vào danh sách workunit; script mới ở target xuất auth, tạo/xóa pending key, commit pending key, thử xác thực với khóa cũ và mới cho tới khi khóa cũ hết hiệu lực. Commit `80ca209c553` thêm cả script và lệnh gọi. Recipe này đồng thời có hunk OSD-055 và OSD-063. Đây là độ phủ validation cho đường xác thực khi xoay khóa, chưa chứng minh riêng việc triển khai production đang dùng pending-key rotation.

**Điều kiện:** pipeline chạy recipe `mon-auth-caps` với MON/CLI hỗ trợ các lệnh pending-key. Trong mixed-version, cần ghi MON leader và CLI nào xử lý từng lệnh; sau full upgrade, target recipe bắt thêm các lỗi xoay khóa có thể đã qua bài `auth_caps` trước đây. **Evidence confidence:** high cho script và lệnh gọi, medium cho tính tương thích của tổ hợp mixed-version và kết quả lab chưa chạy.

**Kiểm chứng:** trên lab chạy workunit với MON target, ghi kết quả từng bước `get-or-create-pending`, `clear-pending`, `commit-pending` và thời điểm khóa cũ bị từ chối; lặp với MON leader base/target nếu rollout có pha mixed-version. Kiểm trạng thái auth và quyền truy cập sau bài thử, chỉ dùng identity lab được tạo cho ca này.

### OSD-066 — Recipe mới kiểm ước lượng di chuyển khi đổi CRUSH map

**CSV:** `qa/suites/rados/singleton-nomsgr/all/crushdiff.yaml` là recipe mới gọi `rados/test_crushdiff.sh` (tệp script thuộc owner 04 và đã được dùng làm bằng chứng cho [MON-022](./04-mon-osdmap-crush.md)). Script tạo pool replicated, thêm pool EC nếu có trên ba OSD, ghi dữ liệu benchmark, rồi export/compare/import CRUSH map dạng text, binary và với OSDMap/PG dump offline. Với map không đổi, script đòi số PG, object và byte ước lượng dịch chuyển bằng 0; với map đã sửa trọng số, đòi giá trị khác 0. Commit `7311f6656fb` thêm recipe và workunit. Recipe còn đặt `mgr_pool false` và lọc `POOL_APP_NOT_ENABLED`/`PG_DEGRADED`; đây là gate QA mới, không phải chứng cứ rằng một CRUSH map cụ thể trong production an toàn để import.

**Điều kiện:** pipeline chọn recipe mới, có `crushdiff`, OSDMap/PG dump và pool thử trên lab; nhánh EC cần hơn ba OSD. Trong mixed-version, kết quả phụ thuộc binary `crushdiff`, CLI và daemon đang phục vụ pool; sau full upgrade, target recipe mở thêm tiêu chí kiểm tra ước lượng CRUSH. **Evidence confidence:** high cho recipe/script/điều kiện, medium cho tính chính xác của ước lượng với dữ liệu dự án vì chưa chạy lab.

**Kiểm chứng:** trên lab cô lập chạy recipe với map không đổi và map sửa trọng số, lưu OSDMap/PG dump, output `crushdiff`, PG state và object count trước/sau. Xác nhận `import` trong script chỉ tác động cluster lab, đối chiếu ước lượng với dịch chuyển quan sát được; không chạy script này trên cluster sản xuất chỉ để lấy kết quả phân tích.

### OSD-067 — Hai recipe RADOS cơ bản bỏ bộ lọc lỗi MON và pool quá rộng

**CSV:** `qa/suites/rados/basic/tasks/rados_api_tests.yaml` và `rados_python.yaml`. Endpoint Pacific có các mẫu `MON_DOWN`, `mons down`, `out of quorum`, cảnh báo application pool và thiếu hit-set trong `overrides.ceph.log-ignorelist`. Endpoint Quincy bỏ các mẫu đó; `rados_api_tests.yaml` còn bỏ `CEPHADM_STRAY_DAEMON`, `rados_python.yaml` giữ các mẫu khác như `POOL_APP_NOT_ENABLED`. `qa/tasks/ceph.py` chỉ đánh dấu bài thử thất bại khi dòng `[ERR]`, `[WRN]` hoặc `[SEC]` còn lại sau lọc. Do đó cùng một cảnh báo MON/quorum có thể làm bài test target thất bại dù từng được bỏ qua ở recipe base. `rados_api_tests.yaml` có thêm hunk mở class ở OSD-062. Không dùng lịch sử commit đơn tuyến để suy chiều thay đổi vì hai endpoint thuộc hai release branch.

**Điều kiện:** pipeline chạy một trong hai recipe, cảnh báo bị bỏ khỏi ignorelist xuất hiện trong cluster log và không khớp mẫu còn lại. Trong mixed-version, tín hiệu đỗ phụ thuộc recipe/teuthology đang dùng và log của các daemon thực chạy; sau full upgrade recipe target có gate chặt hơn với các mẫu nêu trên. **Evidence confidence:** high cho hunk và mã quét log, medium cho tần suất cảnh báo thực tế chưa được đo.

**Kiểm chứng:** trong lab chạy từng recipe với cùng workload, giữ cluster log đầy đủ, ghi mẫu nào bị loại và dòng nào làm `ctx.summary['success']` thành false. Với cảnh báo MON/quorum, kiểm thêm trạng thái MON và client IO để phân biệt lỗi thật với nhiễu do test setup.

### OSD-068 — Gate counter MGR yêu cầu thêm một lần hoàn thành finisher telemetry

**CSV:** `qa/suites/rados/mgr/tasks/per_module_finisher_stats.yaml`. Quincy đổi `finisher-telemetry.complete_latency.avgcount` từ `min: 1` sang `min: 2`, đồng thời thêm filter `POOL_APP_NOT_ENABLED` ở OSD-055. `qa/tasks/check_counter.py` đọc `perf dump`, so `val >= minval`, và ném `RuntimeError` khi counter chưa đạt. Bài thử target vì thế có thể thất bại khi count bằng 1 dù bài base đỗ; đây là đổi tiêu chí QA của module MGR, không chứng minh runtime finisher tự đổi. Commit `0c29d10426a` liên quan bộ test per-module finisher.

**Điều kiện:** pipeline chạy `per_module_finisher_stats.yaml`, active MGR trả counter telemetry với count bằng 1. Trong mixed-version, đối chiếu schema/counter từ active MGR được chọn; sau full upgrade, gate target yêu cầu tối thiểu 2. **Evidence confidence:** high cho recipe và phép so trong task, medium cho count thực khi chạy test.

**Kiểm chứng:** lab chạy workunit `mgr/test_per_module_finisher.sh`, lưu `perf dump` của active MGR trước/sau, xác nhận count đạt 2 hoặc ghi failure từ `check-counter`; lặp khi active MGR failover nếu rollout cần kiểm giai đoạn mixed-version.

### OSD-069 — Bài thử progress dùng profile mClock ưu tiên recovery

**CSV:** `qa/suites/rados/mgr/tasks/progress.yaml`. Pacific recipe không đặt profile mClock; Quincy thêm `overrides.ceph.conf.osd.osd mclock profile: high_recovery_ops` (commit `cc1fc98ea4a`) và lọc `POOL_APP_NOT_ENABLED` ở OSD-055. Option `osd_mclock_profile` trong target chỉ được xét khi `osd_op_queue = mclock_scheduler`; profile mới đổi cách phân bổ QoS cho recovery/scrub/client, nên thời gian PG trở lại clean và tín hiệu progress trong chính bài thử có thể khác. Đây là cấu hình lab, không phải default sản xuất.

**Điều kiện:** pipeline chạy bài progress với OSD dùng mClock. Với WPQ, option này không được scheduler xét. Trong mixed-version, ghi scheduler/profile hiệu dụng từng OSD; sau full upgrade recipe target vẫn dùng profile lab thay vì mặc định nếu override được áp dụng. **Evidence confidence:** high cho recipe và điều kiện option, medium cho thời gian phục hồi thực tế chưa chạy.

**Kiểm chứng:** lab chạy `tasks.mgr.test_progress` với profile target và profile mặc định, lưu config hiệu dụng, PG state, event progress và thời gian recovery; nếu gate rollout dùng recipe này, đối chiếu thêm cấu hình scheduler/profile dự kiến của cluster.

### OSD-070 — Selftest MGR bỏ qua cảnh báo module crash trong cluster log

**CSV:** `qa/suites/rados/mgr/tasks/module_selftest.yaml`. Quincy thêm mẫu `1 mgr modules have recently crashed (RECENT_MGR_MODULE_CRASH)` vào `ceph.log-ignorelist` bên cạnh `POOL_APP_NOT_ENABLED`; commit `3edc04a46bf` mô tả việc whitelist crash trong selftest. `qa/tasks/ceph.py` loại dòng khớp trước khi đánh dấu lỗi cluster log. Vì vậy bài tự thử có thể vẫn đỗ sau một module crash đúng mẫu, dù cảnh báo còn trong log/health; bộ lọc không sửa crash hay trạng thái runtime.

**Điều kiện:** pipeline chạy `tasks.mgr.test_module_selftest` và log phát đúng cảnh báo này. Trong mixed-version/full-version, kết quả phụ thuộc recipe/filter được dùng, số crash và định dạng log của MGR/MON; áp dụng thực tế cần biết pipeline có dùng selftest làm stop/go hay không. **Evidence confidence:** high cho hunk và mã lọc, medium cho việc cảnh báo xuất hiện trong môi trường dự án.

**Kiểm chứng:** lab chạy selftest, lưu cluster log, `ceph health detail`, danh sách crash và kết quả test; xác nhận mẫu bị bỏ qua còn các lỗi khác vẫn fail. Nếu dùng làm gate rollout, kiểm crash MGR riêng thay vì suy từ trạng thái đỗ của recipe.

### OSD-071 — Tách bài ObjectStore QA theo backend và nhóm test dài

**CSV:** Git ghép `qa/suites/rados/objectstore/backends/objectstore.yaml` với `objectstore-bluestore-a.yaml` ở trạng thái `R067`, đồng thời thêm `objectstore-bluestore-b.yaml` và `objectstore-filestore-memstore.yaml`. Pacific chạy `ceph_test_objectstore --gtest_filter=-*/3`, tức loại tham số `/3` của các suite parameterized; Quincy chia thành `*/2:-*SyntheticMatrixC*`, `*SyntheticMatrixC*/2` và `*/1:*/0`. Trong `src/test/objectstore/store_test.cc`, ba `StoreTest` chính đăng ký thứ tự memstore `/0`, filestore `/1`, bluestore `/2`, kstore `/3`; các suite khác có thể có thứ tự riêng. Commit `d4ac4f3b788` nêu mục đích tách ca dài, đặc biệt nhóm SyntheticMatrixC, nhưng ghép rename của Git khác đường rename trong commit nên không suy nó là một dịch chuyển logic thuần túy. Bộ lọc và phân chia job QA thay đổi thời lượng, điểm fail và khả năng bỏ sót ca nếu pipeline không chạy đủ ba recipe. Không có dữ liệu thời gian thực tế ở hai endpoint để định lượng mức giảm.

**Điều kiện:** pipeline chọn các recipe ObjectStore làm gate; phạm vi kiểm còn tùy bản build có backend nào và `gtest_list_tests` thực tế. Trong mixed-version, binary test và backend library cần được ghi rõ, vì bộ lọc target không chứng minh binary base có cùng tập test; sau full upgrade cần chạy đủ ba phần để đối chiếu độ phủ. **Evidence confidence:** high cho hunk/filter và thứ tự `StoreTest` chính, medium cho toàn bộ test inventory và thời gian chạy chưa đo.

**Kiểm chứng:** trên build lab, xuất `ceph_test_objectstore --gtest_list_tests`, áp ba filter target và filter base vào danh sách tên thực, kiểm phần hợp/thiếu/trùng; chạy ba recipe riêng, lưu thời lượng, exit code và log backend. Nếu chỉ một recipe được pipeline chọn, đánh dấu rõ phần backend chưa được thử trước khi dùng kết quả làm gate rollout.

### OSD-072 — Cấu hình chung của QA RADOS đổi điều kiện kiểm thử OSD

**CSV:** `qa/config/rados.yaml`. Endpoint Pacific đặt `osd op queue: debug_random`, `osd op queue cut off: debug_random` và hai tùy chọn kiểm tra OSD. Endpoint Quincy giữ các dòng ấy và thêm `bluestore zero block detection: true`, `osd mclock override recovery settings: true`, `osd mclock profile: high_recovery_ops`. Các commit liên quan `3b588be86f7`, `7f023b06a16`, `3bfc1392642` giải thích từng phần bổ sung; tác động của profile lên scheduler được phân tích thêm ở OSD-004 và OSD-069. Đây là thay đổi baseline của những bài QA nạp config này, không phải bằng chứng default production đổi theo recipe.

**Điều kiện:** pipeline chọn cấu hình `qa/config/rados.yaml`; nhánh mClock chỉ có ý nghĩa nếu OSD đang dùng scheduler mClock, còn phát hiện zero block phụ thuộc đường BlueStore được chạy. Trong lab mixed-version, OSD base và target có thể nhận cùng override nhưng xử lý theo code endpoint riêng; sau full upgrade, bài QA với recipe target không còn cùng cấu hình hiệu dụng như bài Pacific. **Evidence confidence:** high cho diff và phạm vi recipe, medium cho ảnh hưởng lên kết quả test vì chưa chạy pipeline.

**Kiểm chứng:** ở lab, lưu effective config từng OSD và danh sách recipe được chọn; chạy cùng workload RADOS với baseline của hai endpoint, đối chiếu kết quả test, PG recovery và lỗi BlueStore. Nếu dùng QA này làm gate rollout, tách lỗi do code khỏi lỗi do cấu hình test đổi.

### OSD-073 — Lối vào suite upgrade của RADOS chuyển sang Pacific parallel

**CSV:** `qa/suites/rados/upgrade/nautilus-x-singleton` bị xóa, còn `qa/suites/rados/upgrade/parallel` là symlink mới tới `../../upgrade/pacific-x/parallel/`. Base có suite Nautilus singleton ở đường cũ; target có `qa/suites/upgrade/pacific-x/parallel/0-start.yaml`, `1-tasks.yaml`, `upgrade-sequence.yaml` và workload tương ứng. Trong target, `0-start.yaml` cài Pacific; `1-tasks.yaml` chạy `parallel` giữa workload và upgrade; `upgrade-sequence.yaml` gọi `ceph orch upgrade start` rồi đợi hết `in_progress`, kiểm tra `ceph versions` còn một overall version và chứa SHA mục tiêu. Commit `a9c4d1f1e71` bỏ đường Nautilus, `b6c84d56216` trỏ lối vào tới suite parallel. Đây là thay đổi tập ca có thể được pipeline chọn, không chứng minh một pipeline cụ thể đã chạy ca này hoặc rolling upgrade production đã được kiểm chứng.

**Điều kiện:** pipeline khám phá và chọn `qa/suites/rados/upgrade/`; cần biết nó có đi theo symlink mới và chạy đủ workload hay không. Pha mixed-version được suite mô phỏng khi workload chạy song song với orchestrator; kiểm tra cuối cùng chỉ xác nhận số version overall và SHA theo recipe, chưa tự chứng minh tính toàn vẹn dữ liệu hay mọi cảnh báo health đã được xử lý. **Evidence confidence:** high cho endpoint symlink/recipe, medium cho độ phủ gate triển khai chưa biết.

**Kiểm chứng:** trong lab, liệt kê job thực tế từ pipeline và resolve symlink; chạy suite với artifact 16.2.15/17.2.7 đã pin rõ, lưu `ceph versions`, trạng thái orchestrator, kết quả từng workload, PG/health và checksum dữ liệu trước/sau. Không coi recipe có `pacific` branch chung là bằng chứng nó đã dùng đúng tag 16.2.15 nếu artifact chưa được khóa.

### OSD-074 — Bài thrash giảm danh sách cảnh báo health được bỏ qua

**CSV:** `qa/tasks/thrashosds-health.yaml`. Endpoint Pacific lọc thêm `MON_DOWN`, `osds down`, `mons down`, `out of quorum`, các mẫu `PG_`, `backfill_toofull`, `stuck peering` và một số thông báo tương tự; endpoint Quincy bỏ các mẫu đó, giữ nhóm filter khác. `qa/tasks/ceph.py` nạp `log-ignorelist` khi khởi chạy bài thử và chỉ xét lỗi còn lại sau lọc. Vì vậy nếu recipe này được chọn, cùng một cảnh báo MON/OSD/PG có thể làm QA target thất bại trong khi bài base bỏ qua. Không suy từ đây rằng daemon target tự tạo thêm cảnh báo.

**Điều kiện:** pipeline dùng `thrashosds-health.yaml` và phát sinh dòng health/log khớp mẫu đã bỏ. Trong mixed-version hoặc sau full upgrade, kết quả gate phụ thuộc recipe target/base và log thực phát, không chỉ version daemon. **Evidence confidence:** high cho diff/filter, medium cho cảnh báo và cách pipeline chọn recipe chưa được kiểm.

**Kiểm chứng:** chạy bài thrash trong lab với cùng workload, lưu log thô, tập mẫu filter và kết quả job. Phân biệt fail vì cảnh báo availability thật với fail do kỳ vọng QA đổi; kiểm thêm quorum, OSD/PG state và client IO tại thời điểm cảnh báo.

### OSD-075 — Suite thrash với client cũ đổi nơi chọn và bổ sung client Pacific

**CSV:** 45 hàng dưới `qa/suites/rados/thrash-old-clients/`. Ở endpoint base, suite tương ứng nằm dưới `qa/suites/orch/cephadm/thrash-old-clients/`; endpoint target đặt nó dưới nhánh RADOS và thêm `1-install/pacific.yaml`. Các recipe cài Nautilus/Octopus nay loại thêm gói `ceph-volume`; các nhánh thrasher thêm lọc `POOL_APP_NOT_ENABLED`. Suite vẫn ghép các lựa chọn version client, backoff, thrasher, lỗi messenger, cấu hình cluster và workload RADOS/RBD, nên đường dẫn chọn job cùng ma trận thử tương thích client có thể đổi. Commit `c8e1f4c2b54` chuyển suite, `b7237c9e2d8` bỏ Luminous/Mimic khỏi ma trận, `0b361fc8b94` đổi danh sách gói cài, và `7ca74183226` bổ sung cấu hình auth của cephadm trong suite. Git ghi 44 hàng `R` và một hàng `A`, nhưng một số `R100` của symlink/marker được ghép từ đường dẫn không liên quan; đây là heuristic và không chứng minh từng file có một “logical move” tương ứng.

**Điều kiện:** pipeline có khám phá và chạy suite mới tại đường RADOS, với client Pacific hoặc cũ hơn kết nối tới daemon target; chỉ khi đó thay đổi này là gate validation của rollout. Recipe `1-install/pacific.yaml` dùng branch `pacific` chung, không khóa chính xác `v16.2.15`, nên kết quả mặc định không chứng nhận cặp tag của báo cáo. Trong mixed-version, kết quả còn tùy version client được chọn, daemon đang phục vụ request và biến thể msgr/backoff; sau full upgrade, cùng workload kiểm tương thích client với cluster target. **Evidence confidence:** high cho endpoint path/recipe và các hunk được đối chiếu, medium cho độ phủ pipeline và kết quả runtime chưa có.

**Kiểm chứng:** liệt kê job thực được pipeline chọn trước/sau và phiên bản package/image của từng client; chạy ma trận có pin client 16.2.15 và daemon 17.2.7 trong lab, lưu lỗi auth, kết quả workload RADOS/RBD, OSD/PG state và log lọc thrasher. Nếu cần đánh giá client Nautilus/Octopus, ghi rõ đó là ca riêng ngoài cặp endpoint chính.

### OSD-076 — Suite RADOS thrash cỡ lớn đổi phương thức triển khai và workload

**CSV:** bảy hàng trong `qa/suites/big/rados-thrash/`. Base có `ceph/ceph.yaml` gọi `install` rồi `ceph`, các recipe `clusters/{small,medium,big}.yaml` khai báo trực tiếp MON/MGR/OSD trên từng máy, và `thrashers/default.yaml` gọi `thrashosds`. Target bỏ hai recipe `ceph.yaml`/thrasher ấy, thêm `ceph/cephadm.yaml` với `nvme_loop`, `cephadm roleless: true`, yêu cầu kernel HWE; ba cluster recipe nay khai báo host/client thay cho daemon role; thêm workload `radosbench` 300 giây. Commit `0514b0a323d` đổi suite sang cephadm, `9559fea8b26` bỏ thrasher. Do đó tập job và môi trường kiểm thử có thể đổi đáng kể nếu suite này là gate, dù đây không phải thay đổi trong production OSD.

**Điều kiện:** pipeline chọn `qa/suites/big/rados-thrash/` và khả năng của máy lab đáp ứng cephadm/NVMe loop/HWE. Trong pha mixed-version, cần biết pipeline có dùng suite này và image/daemon nào được khởi chạy; sau full upgrade, kết quả vẫn phụ thuộc topologies và workload target. Việc không còn `thrashers/default.yaml` ở đường này không chứng minh toàn pipeline hết kiểm tra thrashing qua suite khác. **Evidence confidence:** high cho diff recipe, medium cho độ phủ pipeline và runtime chưa chạy.

**Kiểm chứng:** trên lab đối chiếu danh sách job được sinh từ hai endpoint, số daemon thực triển khai, lựa chọn thrasher và thời lượng radosbench; chạy ca target, lưu health/PG, client IO, lỗi cephadm/NVMe loop và kết quả test. Không so pass/fail hai endpoint mà bỏ qua khác biệt topology và phương thức triển khai.

### OSD-077 — Crimson MON client bỏ msgr1 và đổi đường phục hồi phiên

**CSV:** `src/crimson/mon/MonClient.cc`, `.h`. Base có `Connection::authenticate_v1()` và chọn v1/v2 theo địa chỉ MON; target bỏ v1, `choose_client_addr()` chỉ lấy địa chỉ msgr2 rồi gọi `authenticate_v2()`. `Client::reopen_session()` nay trả `bool`, dọn connection cũ và gọi `on_session_opened()` để renew key/subscription, gửi hàng đợi và gửi lại MON command; `tick()` thử xác thực lại khi đang hunt. Mã target còn đợi config từ MON tại `src/crimson/osd/main.cc`. Commit `b682a0c2d87`, `26f205dbead`, `f5cf1a36ad4`, `44e45cfc762` giải thích các cụm đổi này. Đây là đường Crimson OSD, không suy rộng sang OSD classic.

**Điều kiện:** chạy Crimson OSD; MON phải công bố và cho kết nối msgr2 khả dụng. Với MON chỉ có v1, Crimson target không có đường fallback như base. Trong mixed-version, Crimson base/target có thể khác nhau về khả năng kết nối và phục hồi phiên khi MON đổi leader/reset; sau full upgrade mọi Crimson OSD target dùng đường mới. **Evidence confidence:** high cho nhánh endpoint, medium cho mức phơi nhiễm vì chưa có cấu hình MON/Crimson của cluster.

**Kiểm chứng:** trong lab có Crimson, ghi MON address vector, thử MON v2 khả dụng và ca chỉ v1, rồi reset/failover MON khi PG peering và MON command đang chờ. Kiểm OSD tiếp tục nhận map/config, hàng đợi command được hoàn tất một lần, PG trở lại clean; ghi rõ daemon nào dùng code base/target.

### OSD-078 — Crimson không assert khi mất kết nối MGR lúc gửi thống kê

**CSV:** `src/crimson/mgr/client.cc`, `.h`. Base `Client::report()` gọi `assert(conn)` trước khi lấy stats; target ghi warning và bỏ lượt gửi nếu `conn` rỗng. `ms_handle_reset()` hủy timer rồi gọi `reconnect()`, còn `handle_mgr_conf()` đặt lại timer theo `stats_period`; thay đổi `MessageURef` đi cùng đường gửi move-only. Commit `728be14cd9d` mô tả ca không có connection. Không thấy hàng đợi lưu bản report bị bỏ, nên không khẳng định telemetry của lượt đó được gửi bù.

**Điều kiện:** Crimson OSD có MGR connection rơi đúng lúc timer/report được gọi. Trong mixed-version, OSD base có thể assert ở đường này, OSD target bỏ report; sau full upgrade Crimson target dùng guard. **Evidence confidence:** high cho nhánh code, medium cho tần suất race và mức thiếu số liệu thực tế.

**Kiểm chứng:** lab làm MGR failover/reset khi Crimson đang báo PG stats, kiểm daemon không thoát, warning `report: no conn available`, và report kế tiếp sau reconnect; so PG stats/MGR view trước và sau.

### OSD-079 — Radosbench QA mặc định chạy trên mọi client role

**CSV:** `qa/tasks/radosbench.py`. Base mặc định `clients: ['client.0']`; target lấy `teuthology.all_roles_of_type(ctx.cluster, 'client')` và thêm prefix `client.`, rồi chạy vòng lặp theo các role ấy. Commit `e1e173876d` nêu mục đích đổi mặc định. Recipe ghi rõ `clients` không bị đổi bởi nhánh mặc định. Đây là thay đổi tải và độ phủ QA, không phải chính sách client của cluster.

**Điều kiện:** bài RADOS benchmark không đặt `clients` và topology có hơn một client. Trong mixed-version/full-version, cường độ tải của recipe target có thể cao hơn base và làm kết quả pass/fail hoặc latency khác; cần pin cùng danh sách client trước khi gán khác biệt cho daemon. **Evidence confidence:** high cho task code, medium cho số client thực của pipeline.

**Kiểm chứng:** xuất job/config đã merge, số client role, số tiến trình benchmark và kết quả từng client trên hai endpoint; chạy lại cùng danh sách client cố định để so daemon.

### OSD-080 — Scrub QA chỉ chọn PG từ pool bị sửa lỗi có chủ đích

**CSV:** `qa/tasks/scrub_test.py`. Base `wait_for_victim_pg()` nhận PG có dữ liệu đầu tiên, không xét pool; sau khi ghi vào `rbd`, test có thể chọn PG thuộc pool khác. Target đọc pool ID của `rbd` từ OSD dump, lọc `pgid` theo pool trước khi chọn victim rồi mới tìm object để gây lỗi. Commit `b24608daa22` nêu ca chọn victim. Đây là sửa độ tin cậy của bài QA corruption/scrub, không phải thay đổi scrub runtime.

**Điều kiện:** lab có nhiều pool với PG chứa dữ liệu và chạy task này. Trong mixed-version hoặc sau full upgrade, script target nhắm đúng pool `rbd`; script base có thể fail vì chọn PG không chứa object vừa ghi. **Evidence confidence:** high cho hunk, medium cho tần suất trong topology cụ thể.

**Kiểm chứng:** lab nhiều pool, lưu `pgid`, pool ID và object victim trước khi inject lỗi, xác nhận scrub phát hiện đúng PG/object và không tác động pool khác.

### OSD-081 — Workunit dedup thêm ca scrub/repair và đổi điều kiện estimate

**CSV:** `qa/workunits/rados/test_dedup_tool.sh`. Base kiểm estimate bằng các giá trị chunk size; target tạo mẫu 50 chunk dữ liệu + 50 chunk zero, đọc `chunk_size_average`/`examined_bytes`, rồi gọi thêm `test_dedup_chunk_scrub`, `test_dedup_chunk_repair`, `test_dedup_object`. Script mới dựng chunk pool lab, thao tác refcount sai có chủ đích, đòi báo damaged object và kiểm kết quả repair/chunk SHA. Các commit `ed24df159cd`, `c1d2119d5e6`, `e7e875c5474`, `16e7d5578c4` nằm trong lịch sử liên quan; endpoint script là bằng chứng về tiêu chí test cuối cùng. Những lệnh xóa pool trong script là cleanup của workunit, không phải hướng dẫn chạy trên cluster thực.

**Điều kiện:** pipeline chạy workunit dedup trên cluster lab có hỗ trợ dedup tier/chunk. Trong mixed-version, kết quả phụ thuộc daemon xử lý chunk op và phiên bản tool; sau full upgrade, target workunit bắt thêm lỗi refcount/repair mà base không kiểm. **Evidence confidence:** high cho script, medium cho kết quả runtime chưa chạy.

**Kiểm chứng:** chạy chỉ trên lab cô lập, pin version tool/daemon, giữ output estimate, damaged count, refs trước/sau repair và checksum chunk; xác nhận cleanup không xóa dữ liệu ngoài pool thử.

### OSD-082 — Suite RADOS thu hẹp tập kiểm thử cephadm

**CSV:** sáu hàng ở `qa/suites/rados/cephadm`. Base có symlink `cephadm -> ../orch/cephadm`, có thể kéo toàn bộ suite orchestration vào nhánh RADOS. Target bỏ symlink rộng và đặt các selector `osds`, `smoke`, `smoke-singlehost`, `workunits` dưới thư mục mới. Commit `b6e8dee22c7` ghi rõ mục đích giảm số bài cephadm chạy trong RADOS suite; một `.qa` được Git ghép `R100` từ marker khác, chỉ là heuristic. Mức giảm cụ thể phụ thuộc cách pipeline triển khai symlink và chọn job.

**Điều kiện:** pipeline lấy `qa/suites/rados/cephadm` làm gate của bản target. Trong mixed-version/full-version, một job không còn được chọn sẽ không cung cấp bằng chứng đỗ/thất bại cho rollout, dù suite orchestration gốc vẫn có thể chạy riêng. **Evidence confidence:** high cho endpoint selector/commit, medium cho job matrix thực chưa liệt kê.

**Kiểm chứng:** dùng đúng phiên bản teuthology của pipeline để xuất danh sách job từ hai endpoint, so tập bài còn/mất, rồi chạy các ca cephadm liên quan activation/redeploy trên lab với image đã pin.

### OSD-083 — Monthrash bỏ lọc cảnh báo pool ở ba workload

**CSV:** `qa/suites/rados/monthrash/workloads/{pool-create-delete,rados_5925,rados_api_tests}.yaml`. Base bỏ qua `POOL_APP_NOT_ENABLED`; target xóa mẫu lọc này. Nếu cảnh báo xuất hiện, cùng workload có thể fail ở target thay vì được bỏ qua, trái chiều với năm thrasher monthrash bổ sung filter ở OSD-055. Recipe RADOS API còn mở class wildcard ở OSD-062. Không suy chiều từ commit đơn tuyến vì hai endpoint thuộc hai release branch.

**Điều kiện:** pipeline chọn một trong ba workload và log có cảnh báo này. Trong mixed-version/full-version, pass/fail phụ thuộc filter của recipe đang chạy và daemon phát log. **Evidence confidence:** high cho diff và cơ chế quét log, medium cho cảnh báo thực tế chưa đo.

**Kiểm chứng:** lab chạy cùng workload với log thô và hai bộ filter, ghi dòng làm job fail; kiểm riêng pool application metadata để phân biệt lỗi test với cấu hình pool.

### OSD-084 — Bài perf QA tăng giới hạn request client đang bay

**CSV:** `qa/suites/rados/perf/ceph.yaml`. Base không override `osd_client_message_cap`, target đặt `5000` dưới config global thay vì default `256`; đồng thời thêm filter `POOL_APP_NOT_ENABLED` ở OSD-055. Option target mô tả giới hạn số client request đang bay, `ceph_osd.cc` gắn nó với `osd_client_messages` throttler, và `OSD::handle_conf_change()` có thể cập nhật giới hạn. Commit `fb8b4e9727c` đặt override. Bài perf target do đó chạy với backpressure khác, không chứng minh default production đổi hay throughput tăng.

**Điều kiện:** pipeline chạy recipe perf này, override được áp dụng, workload đủ concurrency để chạm cap. Trong mixed-version/full-version, benchmark cần so với cùng cap hiệu dụng trên mọi OSD; nếu không, khác biệt có thể do cấu hình test. **Evidence confidence:** high cho option và recipe, medium cho tác động đo được chưa chạy.

**Kiểm chứng:** lab ghi cap hiệu dụng, counter/throttle client, concurrency và latency/throughput khi chạy cùng tải ở 256 và 5000; giữ riêng kết quả filter cảnh báo pool.

### OSD-085 — Admin socket Crimson đổi đăng ký hook và thêm `config help`

**CSV:** `src/crimson/admin/admin_socket.cc`, `.h`. Base `register_command()`/`register_admin_commands()` trả future và dùng shared lock khi execute; target đăng ký đồng bộ, bỏ lock này và thêm `ConfigHelpHook` xuất schema options. Vòng nhận kết nối đổi từ `do_until` sang `keep_doing` với `try_with_gate`; `OSD::start_asok_admin()` gọi đăng ký hook sau khi socket start. Commit `47a5447bdc6`, `e023bf4a546`, `1c45d3ae025` giải thích các thay đổi. Không đủ bằng chứng từ diff để kết luận có race hoặc lỗi khởi động mới.

**Điều kiện:** sử dụng admin socket của Crimson khi daemon start/stop hoặc runbook cần `config help`. Trong mixed-version, lệnh mới chỉ có ở daemon target và vòng đời trả lời có thể khác; sau full upgrade tất cả Crimson target dùng API mới. **Evidence confidence:** high cho code path, medium cho khác biệt timing thực tế.

**Kiểm chứng:** lab gọi `help`, `config help`, `config show` trong lúc start/stop/restart Crimson; kiểm JSON và exit status, xác nhận socket được dọn sau shutdown và không mất phản hồi đang chờ.

### OSD-086 — Crimson thêm metric và fault-injection qua admin socket

**CSV:** `src/crimson/admin/osd_admin.cc`, `.h`. Base có hook metric Seastar cũ; target thêm `DumpMetricsHook` có label/type, `DumpPerfCountersHook` và hai lệnh `injectdataerr`/`injectmdataerr`. `OSD::start_asok_admin()` đăng ký chúng; hook lỗi ánh xạ pool/object qua OSDMap rồi gọi `ShardServices::get_store().inject_data_error()` hoặc `inject_mdata_error()`. `qa/tasks/repair_test.py` target có đường gọi hai lệnh này. Các commit liên quan gồm `1ccb04e7e25`, `87effa76fdd`, `e4ec9c53421`; endpoint code là nguồn chính cho kết luận. Đây là khả năng chẩn đoán/kiểm repair của Crimson, không tự chứng minh dữ liệu production bị sửa.

**Điều kiện:** Crimson OSD được triển khai và công cụ operator/QA gọi các lệnh mới; fault injection chỉ phát sinh khi được gọi rõ ràng. Trong mixed-version, schema/lệnh asok khác theo daemon; sau full upgrade dùng output target. **Evidence confidence:** high cho hook và call site, medium cho việc tooling dự án có dùng các lệnh này chưa biết.

**Kiểm chứng:** trong lab cô lập, đối chiếu output `dump_metrics`/`perfcounters_dump` với counter có sẵn; dùng object thử riêng để inject lỗi và xác nhận bài repair nhận đúng failure signal. Không gọi fault-injection trên cluster sản xuất từ phân tích này.

### OSD-087 — Dashboard QA đổi topology và thêm bài e2e cephadm

**CSV:** năm hàng ở `qa/suites/rados/dashboard`. Base dùng selector CentOS container tools và `2-node-mgr`; target bỏ chúng, thêm `single-container-host`, đặt rõ hai host/role trong `tasks/dashboard.yaml`, bật override `osd mclock override recovery settings` và thêm `tasks/e2e.yaml` chạy `cephadm/create_iscsi_disks.sh` cùng `cephadm/test_dashboard_e2e.sh`. Thay đổi này tác động môi trường và độ phủ bài QA Dashboard/OSD, không trực tiếp thay default daemon sản xuất.

**Điều kiện:** pipeline chọn nhánh dashboard; workload e2e cần topology/device của cephadm. Trong mixed-version và sau nâng cấp, kết quả có thể khác do host, role và override lab, nên không gán khác biệt cho riêng mã OSD. **Evidence confidence:** high cho recipe và selector; medium cho job thực tế chưa xuất từ pipeline.

**Kiểm chứng:** xuất ma trận job đã merge, role thực, effective mClock config và kết quả từng workunit; so sánh cùng topology trước/sau nếu dùng bài này làm gate.

### OSD-088 — Selector MGR objectstore đổi tên chọn ngẫu nhiên

**CSV:** `qa/suites/rados/mgr/objectstore` được Git nhận là rename 100% sang `qa/suites/rados/mgr/random-objectstore$`; nội dung symlink không đổi. Hành vi backend được kiểm trong một job có thể thay đổi khi suite generator diễn giải tiền tố `random-` và dấu `$`; bản thân đường target khác đường base nên pipeline lọc theo path cũng có thể thay đổi tập job.

**Điều kiện:** pipeline chọn suite `rados/mgr` và áp quy tắc selector của teuthology. **Evidence confidence:** high cho rename, medium cho job được chọn vì chưa có manifest đã expand.

**Kiểm chứng:** xuất ma trận suite hai endpoint, đếm backend được chọn mỗi run và chạy đủ backend cần làm gate nâng cấp.

### OSD-089 — Suite standalone thêm bài kiểm backfill

**CSV:** `qa/suites/rados/standalone/workloads/osd-backfill.yaml` mới đặt ba OSD, một client và `workunit` trỏ `qa/standalone/osd-backfill`. Đây là đường vào mới cho các kịch bản backfill đã chuyển vào thư mục standalone; thay đổi độ phủ QA nếu selector chạy recipe này, không phải default backfill runtime.

**Điều kiện:** pipeline chọn workload standalone và có môi trường lab đủ volume/OSD. **Evidence confidence:** high cho recipe và đường workunit; medium cho kết quả chưa chạy.

**Kiểm chứng:** kiểm danh sách script trong `qa/standalone/osd-backfill`, chạy trên lab, lưu PG state, recovery/backfill progress và exit code của từng script.

### OSD-090 — Crimson đổi cách chọn và khởi tạo ObjectStore

**CSV:** `src/crimson/os/futurized_store.cc`, `.h`, `src/crimson/os/alienstore/alien_store.cc`, `.h`. Base factory ánh xạ `memstore` sang `CyanStore`, `bluestore` sang `AlienStore`; target chọn rõ `cyanstore` hoặc `seastore`, còn backend khác đi qua `AlienStore(type,...)` khi build có BlueStore. `AlienStore` tạo backend qua `ObjectStore::create`; `FuturizedStore::create` trả future, `mount`/`mkfs` truyền stateful error, và `main.cc` tạo store trước khi khởi động OSD. Chỉ Crimson chịu đường này; không suy rằng classic ceph-osd đổi backend theo factory này.

**Điều kiện:** triển khai Crimson, đặc biệt cấu hình `osd_objectstore` hoặc build khác nhau. Trong mixed-version, daemon base/target diễn giải type theo factory tương ứng; sau full upgrade cần xác nhận type được hỗ trợ và dữ liệu store mount thành công. **Evidence confidence:** high cho factory/code path, medium cho compatibility của dữ liệu thực chưa mount thử.

**Kiểm chứng:** trên bản sao OSD data ở lab, pin type/build flag, thử `mkfs`, restart/mount và đọc object với backend dự kiến; lưu lỗi activation và tuyệt đối không dùng data production để thử type mới.

### OSD-091 — AlienStore phân luồng theo collection và bảo vệ shutdown

**CSV:** sáu hàng ở `src/crimson/os/alienstore` gồm `alien_collection.h`, `alien_store.cc/.h`, `semaphore.h`, `thread_pool.cc/.h`. Base có một worker/queue chính; target dùng `crimson_alien_op_num_threads`, hàng đợi theo worker và `cid.hash_to_shard(tp->size())`, khóa collection, `op_gate` và CPU affinity, đồng thời chặn SIGHUP trên alien threads. Hunk `get_attr` kéo dài đời chuỗi tên trước khi chuyển thread, `get_attrs` bỏ ép kiểu map không an toàn; commit `5a7fc07933c` sửa race lúc shutdown. Đây là đường IO và lifecycle thực của Crimson qua AlienStore.

**Điều kiện:** Crimson dùng backend qua AlienStore và có IO đồng thời hoặc restart/shutdown trong khi còn request. Trong mixed-version, độ song song/latency có thể khác theo daemon, không có số đo để khẳng định nhanh hơn. **Evidence confidence:** high cho concurrency/code, medium cho hiệu năng.

**Kiểm chứng:** lab chạy IO nhiều collection và cùng collection, fault/restart khi còn IO, theo dõi completion, data checksum, hang/crash và queue latency; lặp với thread count/CPU set hiệu dụng.

### OSD-092 — Crimson đổi mkfs, địa chỉ khởi động và vòng đời daemon

**CSV:** `src/crimson/osd/main.cc`, `osd.cc`, `osd.h`. Target đọc environment/CEPH_ARGS, mặc định `--smp 1`, tùy chọn lấy MON config, tạo store trước OSD và dọn qua deferred stop. `OSD::mkfs` ghi tuần tự `ceph_fsid`, `magic`, `whoami`, `osd_key`, `ready` sau khi kiểm superblock; startup chọn địa chỉ messenger v2, đổi `try_bind` sang `bind`, sửa các địa chỉ chưa biết trước `MOSDBoot`, gửi thêm `boot_epoch` và nối cluster log client. Các commit endpoint liên quan gồm `c7f2056f741`, `5b70488bf3c`, `b3b35dba971`, `ce1ca97f840`.

**Điều kiện:** Crimson được dùng cho init/restart và MON/messenger v2. Trong mixed-version, khả năng boot/advertise phụ thuộc MON, address và key metadata thực; sau full upgrade các Crimson target theo chuỗi mới. **Evidence confidence:** high cho code, medium cho tương tác cluster chưa chạy.

**Kiểm chứng:** lab thử mkfs mới, restart data cũ, keyfile/key config, lỗi FSID/OSD ID, bind public/cluster, MON config và shutdown có request; lưu metadata, `ceph osd tree`, OSDMap address, cluster log và health.

### OSD-093 — Crimson thực thi thêm helper object class dùng bởi RGW

**CSV:** `src/crimson/osd/objclass.cc`. Base trả thành công giả cho `cls_cxx_stat2`, `cls_cxx_getxattrs`, `cls_cxx_map_clear`, `cls_cxx_map_remove_key` và version bằng 0; target gọi `OpsExecuter` cho STAT/GETXATTRS/OMAPCLEAR/OMAPRMKEYS, decode kết quả và lấy `get_last_user_version()`. Commit `b51f2e04e72` nêu các helper dùng bởi `cls_rgw`. Hai hàm gather mới vẫn là stub, nên không suy object class RGW đã đầy đủ.

**Điều kiện:** RGW hoặc object class khác chạy qua Crimson OSD và gọi các helper này. Trong mixed-version, kết quả class op tùy OSD phục vụ object; sau full upgrade có đường target. **Evidence confidence:** high cho hunk, medium cho tập RGW workload thực tế.

**Kiểm chứng:** lab RGW trên Crimson thử stat/xattr/omap và version trước/sau, kiểm dữ liệu và lỗi trả về; xác nhận tính tương thích khi object chuyển primary giữa base/target.

### OSD-094 — Compound peering Crimson dùng completion có thể bị ngắt

**CSV:** `src/crimson/osd/osd_operations/compound_peering_request.cc`. Base `PeeringSubEvent::complete_rctx` trả future thường và khởi `BufferedRecoveryMessages` với release Octopus; target trả `PeeringEvent::interruptible_future`, dùng constructor mặc định của API buffer mới. Đường này gom message từ các subevent PG-create/peering trước khi gửi. Hunk chuyển namespace chỉ là thích ứng API; khác biệt cần kiểm là completion/cancellation khi peering bị thay thế.

**Điều kiện:** Crimson xử lý compound peering trong lúc PG create hoặc map đổi. Trong mixed-version, peer base/target có thể gặp cùng sự kiện nhưng scheduling/cancellation riêng; chưa có bằng chứng wire incompatibility. **Evidence confidence:** high cho type/code, medium cho tác động race runtime.

**Kiểm chứng:** lab tạo PG rồi thay map/fail peer liên tục, đo peering completion, stuck PG và số recovery message, so với base trên cùng topology.

## Các hàng đã xác nhận trivial

113 hàng trivial gồm 43 hàng source, 42 QA/test và 28 tài liệu/ảnh. Ở source, comparator map khóa chuỗi, cách lặp, formatter, include/rename và classifier refactor không làm đổi workflow trong chính các hunk đã rà; `Watch.cc` của đường classic giữ cùng wire encoding độ dài/phần tử (khác với Crimson watch ở OSD-038). Hunk mới ở `Transaction`, `FuseStore`, hai CLI helper, Clay và `MRemoveSnaps` chỉ đổi kiểu comparator, biến không đọc, cách nhận argv hoặc quyền truy cập constructor. Ba hunk Crimson nhỏ chỉ thêm/định danh `std::make_pair`; sáu hunk metadata/include/handle giữ nguyên key và operation trong chính tệp đã rà; hai hunk `ECBackend` chỉ đổi API của stub vẫn trả dữ liệu rỗng/chưa thực hiện EC. Bốn tệp `PrimaryLogScrub.cc/.h`, `ScrubStore.cc/.h` đã được so theo rename-aware diff với đường Pacific cũ. Tám hàng `crimson-store-nbd` thuộc executable profiling fio riêng theo tài liệu/CMake, không phải đường OSD daemon; `object_cacher_stress.cc` chỉ thích ứng chữ ký `argv_to_vec`. Năm QA Crimson thay recipe test, một tệp `.disabled` ở mỗi suite; hai workunit librados chỉ đổi gói cài thử nghiệm theo distro, một recipe monthrash chỉ tăng debug log. Thêm 16 tệp test erasure-code và 11 tệp unit test OSD chỉ đổi namespace, tên biến, API test fixture hoặc chữ ký `argv_to_vec` với cùng đầu vào/assertion; ngoại lệ đổi test guard nằm ở OSD-051 và bài thử dedup ở OSD-054. Hai transcript `osdmaptool` chỉ cập nhật output kỳ vọng của CRUSH; feature Behave OSD mới không có đường chọn suite nâng cấp đã xác lập. Recipe `pool-snaps-few-objects.yaml` đặt `log-ignorelist` dưới khóa `override` số ít, trong khi [cấu hình teuthology](https://docs.ceph.com/projects/teuthology/en/latest/detailed_test_config.html) dùng `overrides`; cần kiểm job đã merge trước khi tin filter này có hiệu lực. Ở tài liệu, phần lớn là biên tập câu chữ/URL, cập nhật ví dụ chẩn đoán, 15 biểu đồ tĩnh của nghiên cứu bản phát triển và ảnh Jaeger; không đổi runtime hay lệnh upgrade. Lý do từng hàng nằm ở CSV.

Không còn hàng trống trong owner 01. Các hàng `trivial` được gắn sau khi đọc hunk/context, không suy từ đuôi tệp.

## Kiểm chứng tiếp theo

- Chạy các kịch bản lab trong từng finding trên binary và cấu hình thực tế của dự án; ưu tiên mClock, peering/recovery, scrub, BlueStore/EC và đường Crimson nếu được triển khai.
- Xuất ma trận QA/teuthology đã merge để xác nhận selector, role và override; đối chiếu với pipeline dùng làm gate rollout.
- Lập As-Is cluster rồi mới chọn ngưỡng dừng rollout và đánh giá GO/NO-GO.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Binary gate của owner 01 chỉ là phân loại tác động có chứng cứ từ source và recipe; không đưa GO/NO-GO production từ đây.
