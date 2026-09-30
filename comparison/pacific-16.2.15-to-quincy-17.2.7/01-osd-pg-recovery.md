# 01 — OSD, PG, peering, recovery/backfill, scrub và EC: v16.2.15 → v17.2.7

**Trạng thái: đang phân tích.** [CSV đầy đủ của owner](./01-osd-pg-recovery.csv) có 465 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 37`, `trivial = 13`, **chưa phân loại = 415**.

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

**CSV:** `src/osd/scheduler/OpScheduler.cc`, `.h`. Factory ở Pacific chọn `wpq` hoặc `mclock_scheduler` từ `osd_op_queue`. Quincy chọn WPQ khi `osd_objectstore == "filestore"` dù queue config là mClock; constructor mClock đồng thời nhận OSD ID, shard ID và MonClient. Commit `e65c4bcd96f` nêu rõ ép WPQ cho FileStore; [tài liệu mClock Quincy](https://docs.ceph.com/en/quincy/rados/configuration/mclock-config-ref/) xác nhận ràng buộc này.

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

## Các hàng đã xác nhận trivial

Mười ba hunk đã được đối chiếu: `ECBackend.h`, `ECMsgTypes.h`, `ECTransaction.cc`, `osd_internal_types.h`, `ReplicatedBackend.h`, `PGBackend.cc`, `PGTransaction.h` đổi comparator map khóa chuỗi hoặc cách lặp nhưng giữ thứ tự/dữ liệu; `Watch.cc` đổi list sang vector với cùng wire encoding độ dài/phần tử trong `encoding.h`; `Watch.h` bỏ getter không có caller; `recovery_types.cc` thêm `std::` cho stream operator; `osd_op_util.cc/.h` tách classifier sang overload nhận vector và bỏ READ_DATA flag không còn consumer trong source target; `osd_types_fmt.h` chỉ thêm formatter cho thông báo chẩn đoán. Lý do từng hàng nằm ở CSV.

Các hàng khác vẫn để trống `upgrade_impact` cho tới khi đọc diff/metadata; không gán `trivial` theo đường dẫn.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 465` và viết tóm tắt các cụm trivial.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
