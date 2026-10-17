# 05 — messaging, auth, wire format và shared runtime: v17.2.7 → v18.2.7

**Trạng thái: binary gate hoàn tất.** [CSV đầy đủ của owner](./05-messaging-auth-common.csv) có 195 hàng và là subset đúng thứ tự của master inventory: `affect = 105`, `trivial = 90`, chưa phân loại = 0. Phân tích sâu dưới đây chỉ lấy từ tập `affect`; test và refactor hỗ trợ vẫn nằm trong CSV nhưng không tự trở thành finding.

## Phạm vi và giới hạn bằng chứng

Owner này bao phủ messenger cổ điển, Crimson msgr2, release/feature bits, định dạng dùng chung, perf/logging runtime và một gitlink crypto. So sánh là endpoint net diff giữa `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) và `v18.2.7` (`6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`). Repo nguồn shallow và hai endpoint non-ancestor, nên không có commit-range history đáng tin cậy; kết luận dựa trên hunk và caller ở hai endpoint.

Không có cluster production, As-Is network, Crimson, Windows, VDO, Jaeger hay dashboard schema để xác nhận applicability. Chưa chạy repository test hoặc lab/runtime. Riêng hai object của submodule ISA-L Crypto không có trong clone, vì vậy chỉ pointer change được chứng minh.

## Finding ảnh hưởng upgrade

### MSG-001 — Reef trở thành release/peer feature được quảng bá

**Evidence.** `src/include/ceph_features.h` định nghĩa `SERVER_REEF` trên bit 31/slot 3 và thêm mask này vào `CEPH_FEATURES_ALL`; `src/include/rados.h`, `src/common/ceph_releases.h` và `src/common/ceph_strings.cc` thêm release 18/`reef` và ánh xạ release→feature.

**Before/after.** Quincy để slot Reef chưa dùng; Reef quảng bá feature mới và có thể suy ra release floor khác. Trong rolling upgrade, kết quả feature intersection phụ thuộc peer nào đã lên Reef; sau khi toàn bộ daemon liên quan lên Reef, Reef feature có thể được dùng bởi các đường target như primary upmap. Đây là automatic peer behavior, không phải option. Tác động là compatibility/rollback boundary; confidence `high` cho code path, nhưng thời điểm feature được persist/require thuộc owner MON/OSDMap.

### MSG-002 — Dispatcher có priority và fast-auth dùng hợp đồng boolean

**Evidence.** `src/msg/Dispatcher.h::priority_t` thêm ba mức priority và đổi `ms_handle_fast_authentication()` từ `int` sang `bool`; `src/msg/Messenger.h::add_dispatcher_{head,tail}` sắp dispatcher bằng priority.

**Before/after.** Quincy quyết định thứ tự bằng vị trí push head/tail; Reef có thứ tự ưu tiên tường minh. MON client target dùng priority cao và fast-auth chỉ còn success/failure. Trong mixed version, mỗi process tự áp dụng thứ tự của binary đang chạy; wire bytes không đổi, nhưng consumer xử lý event/auth đầu tiên có thể khác. Tác động là authentication/dispatch continuity; confidence `high`. Chi tiết MON-client failure mapping được phân tích thêm ở `MON-008` trong owner 04.

### MSG-003 — AsyncMessenger sửa resend/partial send, shutdown wait và thêm timeout/encryption signals

**Evidence.** `src/msg/Messenger.cc::get_random_nonce()` bỏ PID-based nonce; `AsyncConnection::_try_send()` giữ queued bytes khi send chưa tiến triển; `ProtocolV1::out_q_entry_t` và `ProtocolV2::send_message()` theo dõi payload đã encode; cả hai `write_event()` xả queued bytes trước frame mới. `AsyncMessenger::wait()` dùng vòng `while`, MON-to-MON có thể đặt minimum-delay socket priority, và `Stack.h` thêm encrypted-byte cùng labeled timeout counters.

**Before/after.** Target tránh reuse nonce theo PID/container, tránh encode/scheduling sai khi feature chưa ổn định hoặc socket partial-send, và chống spurious wakeup khi dừng messenger. Khi rolling upgrade, thay đổi nằm ở endpoint đã nâng cấp và tương tác với cả peer Quincy/Reef qua protocol v1/v2; sau full upgrade mọi connection dùng đường mới. `mon_use_min_delay_socket`, RDMA và congestion injection là điều kiện riêng. Tác động availability/compatibility/observability; confidence `high` từ state-machine diff, performance benefit chưa được tuyên bố.

### MSG-004 — Windows chuyển sang backend poll/WSAPoll

**Evidence.** `src/msg/async/Event.{h,cc}` chọn `PollDriver` khi `_WIN32`; `EventPoll.{h,cc}` triển khai registration, resize tới 8192 FD và `WSAPoll`.

**Before/after.** Windows trước đó rơi về select backend; target dùng poll semantics và có hard FD limit riêng. Chỉ `affect` khi rollout có Windows-built Ceph process; Linux daemon không đi qua nhánh này. Mixed version không có shared state, nhưng endpoint Windows mới có event delivery khác ngay sau restart. Tác động delivery/platform availability; confidence `high` cho condition, applicability chưa xác minh.

### MSG-005 — Crimson msgr2 tách frame assembly và cross-shard I/O state machine

**Evidence.** Reef xóa `crimson/net/Protocol.{h,cc}`, thêm `FrameAssemblerV2` và `io_handler`, và sửa đồng bộ `ProtocolV2`, `SocketConnection`, `SocketMessenger`, dispatcher, connection, buffer ownership, gating và cross-core pointer helpers. Các đường được thay gồm banner/feature negotiation, auth frames, CRC/secure handlers, reconnect/replacement, resend/ack, keepalive, reset, socket shutdown và chuyển dispatch shard.

**Before/after.** Quincy giữ read/write and connection state trong Protocol base; Reef tách handshake khỏi I/O dispatch, có sequence cho cross-core transition và đợi in/out dispatch thoát trước replace/close. Đây là thay đổi runtime lớn nhưng chỉ áp dụng khi dùng Crimson/Seastar messenger. Trong mixed peer version, wire msgr2 vẫn negotiation bằng banner/features nhưng state ownership và fault recovery ở peer Reef khác; sau full upgrade toàn bộ Crimson endpoints dùng state machine mới. Tác động availability/compatibility; confidence `high` cho code delta, `medium` cho deployment risk vì chưa biết có Crimson OSD trong As-Is.

### MSG-006 — CommandTable theo dõi multi-target CephFS command

**Evidence.** `src/common/CommandTable.h` thêm `multi_target_id`, tập tid theo target và count/erase logic; target `Client.cc` dùng nó khi gửi command tới nhiều MDS rank.

**Before/after.** Quincy theo dõi từng tid độc lập; Reef có thể chờ/ghép các reply của một lệnh multi-rank. Điều kiện là CephFS có nhiều rank và operator dùng command fan-out. Trong rolling upgrade, hành vi nằm ở client/tool binary; sau full upgrade output/completion phản ánh toàn bộ target. Tác động validation correctness; confidence `high`.

### FS-001 — CephFS request-head v3 và snapshot realm có metadata versioned

**Evidence.** `src/include/ceph_fs.h` tăng `CEPH_MDS_REQUEST_HEAD_VERSION` từ 2 lên 3, thêm `struct_len`, owner uid/gid, snapdiff/quiesce op và skip phần extension chưa hiểu; `SnapRealmInfoNew` mang `last_modified`/`change_attr`; `encoding.h` thêm round-trip chrono encoding.

**Before/after.** Decoder cũ không có owner/length extension; decoder Reef có fallback caller uid/gid cho request cũ và bỏ qua tail mới dựa trên `struct_len`. Snapshot realm target có thêm state để client/MDS theo dõi thay đổi. Đây là wire/state compatibility path tự động khi CephFS client/MDS nâng cấp; mixed version cần kiểm tra request cũ→MDS mới và client mới→MDS theo thứ tự rollout được hỗ trợ. Tác động compatibility/correctness; confidence `high`, còn validation multi-rank/snapshot chưa chạy.

### DATA-001 — BitVector post-increment được sửa cho RBD object map

**Evidence.** `src/common/bit_vector.hpp::IteratorImpl::operator++(int)` ở base tăng iterator tạm; target tăng `*this`. Caller chính nằm trong `src/cls/rbd/cls_rbd.cc` cho object-map operations.

**Before/after.** Vòng lặp dùng post-increment có thể không tiến ở Quincy; target tiến đúng entry. Không có wire-version gate: hành vi đổi khi cls/client code Reef thực thi object-map path. Mixed version phụ thuộc OSD/client nào thực hiện method; sau full upgrade dùng iterator sửa. Tác động data correctness/availability có điều kiện với RBD object map; confidence `high` cho lỗi iterator, `medium` cho workload applicability.

### NET-001 — OSDMap có helper kiểm tra public address thuộc subnet

**Evidence.** `src/common/pick_address.{h,cc}::is_addr_in_subnet()` parse IPv4/IPv6 và kiểm tra danh sách network; target `OSDMap.cc` gọi helper cho public addresses trong topology/stretch validation.

**Before/after.** Base không có shared check này; target có thể từ chối hoặc báo địa chỉ không thuộc `public_network`. Điều kiện là đường OSDMap/stretch có cấu hình network được kiểm; tác động xuất hiện khi MON/OSDMap target chạy, không phải thay đổi wire độc lập. Tác động configuration/topology correctness; confidence `high`; cross-reference owner 04 (`MON-003`).

### STOR-001 — VDO accounting rời common blkdev sang extblkdev plugin

**Evidence.** `src/common/blkdev.{h,cc}` xóa `get_vdo_stats_handle/get_vdo_stat/get_vdo_utilization`; target có cây `src/extblkdev/vdo/*` do owner 13 quản lý và `global_init.cc` liên kết plugin interface.

**Before/after.** Quincy có helper VDO trực tiếp trong common block-device code; Reef dựa vào plugin extended block device. Chỉ áp dụng khi OSD đặt trên VDO/compressed block device. Trong rolling upgrade, OSD Reef cần plugin target để capacity/accounting đồng nhất; OSD Quincy vẫn dùng helper cũ. Tác động capacity headroom/delivery; confidence `medium` vì nửa target plugin thuộc owner 13 và chưa chạy VDO lab.

### CRIMSON-001 — Crimson config propagation và operation pipeline đổi cross-shard semantics

**Evidence.** `ConfigProxy::do_change()` dựng presence map rồi notify observer trên từng shard; `operation.{h,cc}` đổi ID thành core-qualified, track blocking/time event, submit exit barrier về owner core và thay registry shutdown semantics.

**Before/after.** Target phân biệt option có/không tồn tại khi phát change và không unlock cross-core pipeline trực tiếp. Điều kiện là Crimson OSD; thay đổi có hiệu lực sau daemon restart lên target và khi live config/pipeline operations chạy. Mixed version không chia sẻ in-memory pipeline nhưng có thể cho hành vi config/latency khác giữa OSD Quincy và Reef. Tác động availability/configuration/diagnostics; confidence `high` cho implementation, `medium` cho applicability.

### OBS-001 — Schema formatter/perf counter đổi, có labeled counters mới

**Evidence.** Formatter target có `dump_null`, bool JSON native, non-finite double→`null`, buffer động cho formatted output; `CephContext` giữ `perf dump/schema` cho counter không label và thêm `counter dump/schema` cho cả hai; perf counter key mã hóa label; TrackedOp thêm slow-op count/count-only; mempool names được chuẩn hóa; Crimson throttle export pending count.

**Before/after.** Parser từng thấy boolean dạng string, formatted value có thể bị cắt ở fixed buffer và mọi counter nằm dưới logger name; target có JSON type/schema mới và tách labeled counters khỏi lệnh `perf dump`. Sau khi từng daemon nâng cấp, dashboard/automation phải chọn đúng command/key; mixed fleet có hai schema đồng thời. Tác động stop/go observability; confidence `high`. Đây là schema migration cho monitoring, không phải bằng chứng rằng metric value tốt hơn.

### OBS-002 — Thread/crash log và subsystem names thay đổi

**Evidence.** wrapper thread-name chỉ thao tác current thread và cache tên; `Entry` chụp tên lúc tạo; `Log` giữ lịch sử tên theo pthread id, sửa circular-buffer capacity và max_new output; `subsys.h` thêm/bỏ các category RGW/Seastore/civetweb/memdb.

**Before/after.** Quincy tra thread name muộn lúc crash dump nên có thể sai khi pthread id tái sử dụng; Reef giữ tên tại thời điểm log. Các key `debug_<subsys>` và crash-dump fields có thể khác sau restart. Mixed fleet tạo log schema khác nhau; sau full upgrade parser/filter phải nhận bộ category Reef. Tác động diagnostics/observability; confidence `high`, cấu hình debug hiện hữu chưa được inventory.

### OBS-003 — Jaeger dùng configured port và batch span processor

**Evidence.** `Tracer::init()` target đọc `jaeger_agent_port`, dùng `BatchSpanProcessor`, set global provider và dùng shared noop span.

**Before/after.** Base dùng exporter defaults và simple processor; target batch/export endpoint theo config. Chỉ áp dụng khi build `HAVE_JAEGER` và tracing được dùng cho validation. Mixed fleet có flush/timing khác nhau; sau full upgrade phải tính đến batching trước khi coi thiếu span là failure. Tác động observability; confidence `high` cho code, applicability chưa biết.

### RUNTIME-001 — Child-FD cleanup và daemon restart/privilege path thay đổi

**Evidence.** `SubProcess::spawn()` và `fork_function()` dùng Linux `close_range` với fallback; `global_init.cc` tăng group lookup buffer, hỗ trợ `set_keepcaps`, mở `/dev/null` read/write và đặt stderr level nhất quán; `CephContext::notify_post_fork()` đổi locking.

**Before/after.** Base đóng lần lượt tới `_SC_OPEN_MAX` và có post-fork/stdio assumptions cũ; target có fast close, privilege-retention option và explicit fd redirection. Điều kiện gồm Linux kernel có syscall, nhiều open FD, privilege drop hoặc daemonize. Đây là local restart behavior, không tạo mixed wire format; mỗi daemon đổi ngay khi chạy target. Tác động delivery/availability; confidence `high` cho branches, chưa benchmark high-FD restart.

### DEP-001 — ISA-L Crypto gitlink đổi nhưng nội dung dependency chưa có

**Evidence.** gitlink `src/crypto/isa-l/isa-l_crypto` đổi `603529a4e06a...` → `a6dc869666fc...`; cả hai object không resolve trong shallow source.

**Before/after.** Pointer chắc chắn đổi, nhưng không thể khẳng định algorithm, ABI, CVE hay performance change nếu chưa fetch hai dependency commits. Tác động tiềm năng nằm ở build/runtime crypto dùng ISA-L, không phải thay đổi live state. Confidence `high` cho pointer, `low` cho nội dung; phải fetch/compare submodule trước khi dùng finding này cho quyết định security/performance.

**Activation và kiểm chứng:** gitlink được dùng explicit khi pipeline checkout/build ISA-L crypto; host cài artifact không tự fetch dependency lúc restart. Với SBOM dùng plugin ISAL::Crypto, cần khóa hai full commit, fetch dependency trong source mirror, so ABI/algorithm rồi chạy known-answer test, cross-decode và lỗi init trên đúng architecture. Nếu feature không dùng, ghi scope exception theo build/link manifest; không suy pointer đổi là CVE hay cải thiện performance. Hai objects vẫn chưa resolve trong repo đã kiểm nên internal behavior và kết quả test còn UNKNOWN.

## Operational closure addenda

#### MSG-001 — Closure

Kiểm chứng exact-tag cần capture advertised release/feature qua Quincy↔Reef peers, reconnect và full-Reef, với decode/error logs. Source constant không tự chứng minh negotiation thành công; artifact digest và runtime trace còn thiếu.

#### MSG-002 — Closure

Priority/fast-auth behavior tự động kích hoạt ở dispatch/auth; không phải config migration. Rollback bằng route/restart old endpoint sau quiesce và giữ auth DB unchanged. Chưa có handler-order/auth-negative trace; mixed/full lab phải kiểm success, rejection, reconnect và không rơi nhầm dispatcher.

#### MSG-003 — Closure

Resend/shutdown/encryption path tự động chạy khi connection partial/reconnect/stop. Rollback canary là drain endpoint, restore old binary/config và reconcile request IDs; packet đã gửi không thể thu hồi. Validation phải inject partial send/reset, kiểm no duplicate/drop, queue convergence, shutdown timeout và counters.

#### MSG-004 — Closure

Rollback Windows endpoint bằng restore pinned artifact/backend after connection drain; outstanding I/O cần request ledger. Kiểm chứng trên supported Windows build phải chạy connect/read/write/wakeup/close under load và compare error codes; Linux daemon result không thay thế.

#### MSG-005 — Closure

Frame/cross-shard path tự động theo mỗi Crimson connection. Rollback sau in-flight traffic cần drain, close và reconcile sequence IDs trước old binary; không hot-switch shard state. Validation mixed/full phải inject simultaneous connect/reset/resend/keepalive và kiểm frame/order/no leak.

#### MSG-006 — Closure

Multi-target aggregation tự động khi command nhắm nhiều rank; command mutation là explicit. Rollback là pin old CLI/dispatcher hoặc retry idempotent after state observation, không giả success từ partial replies. Chưa có multi-rank command inventory/result; cần validate target sets, reply aggregation, timeout và duplicate mutation.

#### FS-001 — Closure

First Reef write của request-head/snaprealm metadata là rollback boundary; old MDS/client failback chỉ trên clone with versioned decode proof. Mixed/full phải test old/new client/MDS, snapshot mutation/replay và namespace checksum; không nâng feature floor trước PASS.

#### DATA-001 — Closure

Fix tự động áp dụng khi target iterator xử lý RBD object map. Rollback của object-map mutation cần image snapshot/copy và old-reader verification; không sửa bits thủ công. Chưa có affected workload reproduction; validation phải compare map, diff, read/write/discard and image checksum across mixed clients.

#### NET-001 — Closure

Helper tự động được caller dùng khi target đánh giá address/subnet; applicability phụ thuộc multi-network/config path. Mixed/full phải test IPv4/IPv6/CIDR/invalid addresses on old/new OSDMap consumers. Rollback bằng restore network config/binary before address-map mutation. Chưa có caller/config inventory hay runtime result.

#### STOR-001 — Closure

Plugin detection tự động ở device open; packaging/install là explicit. Rollback bằng drain OSD, restore exact plugin+binary and reopen cloned store; no blind fallback. Mixed/full validation so utilization/state metadata and missing/wrong plugin behavior.

#### CRIMSON-001 — Closure

Nếu Crimson hiện diện, rollback sau cross-shard operation/store write là clone-only until compatibility proof; drain alone không đảm bảo. Chưa có runtime/applicability evidence. Validation phải cover config propagation, gate migration, reset/reconnect, operation completion and checksum in mixed/full Crimson lane.

#### OBS-001 — Closure

Rollback bằng dual-schema parser/dashboard và old endpoint query; counters history không rewrite. Chưa có consumer/label inventory; validation phải capture raw formatter/perf output, units/cardinality and alert replay across mixed/full.

#### OBS-002 — Closure

Rollback là restore parser/filter/debug config, không sửa crash log đã sinh. Validation cần golden crash/recent-log fixtures, pthread-id reuse case, subsystem-key inventory and full-Reef parser acceptance.

#### OBS-003 — Closure

Rollback tracing bằng restore exporter/port/processor config and restart canary; batched spans already buffered may be lost/duplicated, so use trace IDs. Mixed/full validate flush latency, endpoint outage/recovery and applicability build flags.

#### RUNTIME-001 — Closure

Rollback local daemon bằng drain, restore old artifact/capability config and restart; privilege/FD state is process-local but in-flight child work needs reconciliation. Validation must exercise high FD, syscall fallback, daemonize, keepcaps and stdout/stderr behavior.

#### DEP-001 — Closure

Rollback delivery means pin the prior resolved submodule/artifact digest; live-state rollback is not relevant until crypto output compatibility is proven. Mixed/full package use is forbidden while dependency contents remain unresolved. Fetch both commits, diff ABI/algorithms, build and run known-answer/performance tests before closing.

## Trivial changes

90 hàng `trivial` đã được đọc theo cụm. Chúng gồm CephX `0`→`false`, dead legacy message declarations, Boost→`std::optional`, fmt/C++20 comparison/concept migrations, header/include cleanup, helper/API mới chưa có causal path upgrade, Windows portability không thuộc Linux daemon rollout, và bốn test/benchmark messenger chỉ hỗ trợ evidence. Các ngoại lệ có runtime, wire, state, lifecycle hoặc validation path đều đã được tách vào 105 hàng `affect`; enumeration đầy đủ nằm trong CSV.

## Validation đề xuất

Các scenario dưới đây là thiết kế kiểm chứng, chưa được thực thi và không cấp quyền thao tác cluster production.

1. **Mixed messenger v1/v2:** giữ traffic client/OSD/MON trong lúc lần lượt restart một endpoint Reef; inject partial-send/reconnect trong lab; kỳ vọng không duplicate/drop, resend queue hội tụ và timeout/encrypted counters tăng đúng command schema.
2. **MON auth/dispatch:** thử fast-auth thành công/thất bại và reconnect leader; kỳ vọng dispatcher ưu tiên MON client và lỗi auth rõ ràng, không rơi vào handler thấp hơn.
3. **CephFS mixed MDS/client:** chạy request v2→MDS Reef, client Reef→MDS được hỗ trợ, multi-rank command và snapshot update; quan sát owner uid/gid fallback, reply aggregation và snapshot change_attr.
4. **Crimson-only gate:** nếu As-Is có Crimson, chạy banner/auth, simultaneous connect, connection replacement, shard migration, keepalive, reset và resend với peer Quincy/Reef; stop nếu có stuck gate, lost reset hoặc out-seq divergence.
5. **Monitoring schema:** capture cùng `perf dump`, `counter dump`, JSON/XML command và crash/recent-log output trước/sau; cập nhật parser/dashboard trước khi dùng metric absence làm stop condition.
6. **VDO/extblkdev:** chỉ khi có VDO, xác nhận package/plugin tồn tại và reported total/available khớp base trước khi tiếp tục OSD rollout.
7. **High-FD restart:** trong lab mở nhiều FD rồi restart daemon/subprocess path; kỳ vọng thời gian đóng FD hữu hạn, stdio đúng `/dev/null`, privilege/capability đúng cấu hình.
8. **Dependency closure:** fetch chính xác hai ISA-L Crypto commits, so ABI/algorithm/tests và target build flags; không gắn nhãn security/performance trước bước này.

## Kết luận owner

Owner 05 đã khép binary gate nhưng chưa phải GO/NO-GO production. Điểm cần đưa vào runbook là: dual monitoring schema trong mixed fleet, test reconnect/partial send, CephFS request/snapshot compatibility, điều kiện Crimson/Windows/VDO/Jaeger, và dependency gap của ISA-L Crypto. Không có bằng chứng endpoint nào trong owner này tự yêu cầu thao tác migration/repair trên cluster.
