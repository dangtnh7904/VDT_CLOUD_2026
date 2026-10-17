# 05 — messenger, CephX, encoding và common runtime: v16.2.15 → v17.2.7

**Trạng thái: binary gate của owner đã hoàn tất; lab còn mở.** [CSV đầy đủ của owner](./05-messaging-auth-common.csv) có 227 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Hiện `affect = 156`, `trivial = 71`, **chưa phân loại = 0**.

## Phạm vi và phương pháp

Owner này phụ trách messenger, CephX, encoding và common runtime. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

Các finding chi tiết dưới đây chỉ xuất phát từ hàng `affect`. Hàng `trivial` vẫn có đầy đủ trong CSV và được tóm tắt cuối báo cáo; nhãn là mức liên quan nâng cấp, không phải mức độ nghiêm trọng.

## Findings liên quan nâng cấp

### MSG-001 — CephX chấp nhận pending key trong giai đoạn xoay khóa

**CSV:** `src/auth/Auth.h`, `Crypto.h`, `KeyRing.cc/.h`, `cephx/CephxKeyServer.cc/.h`, `cephx/CephxServiceHandler.cc`, `src/msg/Message.cc/.h`. Base `EntityAuth` encode version 2 chỉ gồm key và caps; target version 3 thêm `pending_key`. `CephxServiceHandler::handle_request` thử active key trước, rồi thử pending key khi challenge không khớp; ticket reply dùng key thực sự được chấp nhận. `KeyServer` ghi nhận pending key đã dùng, để `AuthMonitor` đưa vào quy trình commit ở [MON-003](./04-mon-osdmap-crush.md). `Message.cc/.h` đăng ký type/decode `MMonUsedPendingKeys` cho MON-to-MON; `KeyRing` có thể chứa/in pending key, `CryptoKey::clear` phục vụ xóa pending key sau commit. Commit liên quan `99d3e0ec67e`, `34a0ef8fb34`, `370cb849255`; mã hai endpoint là bằng chứng chính.

**Điều kiện:** operator dùng workflow pending-key và MON đã đạt `min_mon_release >= quincy` như gate ở MON-003. Trong mixed-version, không suy mọi MON/daemon base chấp nhận pending key; thao tác tạo/commit bị MON target chặn trước mốc release. Sau full upgrade, key cũ và pending key có giai đoạn chồng lấn trước khi commit; hành vi rollback của auth store cần thử trên clone. **Evidence confidence:** high cho encode, challenge và MON gate; medium cho interoperability thực tế vì chưa có lab.

**Kiểm chứng:** trên lab clone, tạo pending key, thử client bằng key cũ/mới qua từng MON trong giai đoạn mixed và full Quincy, kiểm ticket và log xác thực, dùng `auth commit-pending` rồi restart MON/daemon. Ghi keyring xuất/nhập, kiểm rollback với bản sao auth DB và xác nhận không mất quyền truy cập.

**Tác động và ranh giới:** compatibility/availability của xác thực đổi khi tạo và dùng pending key explicit; việc cài binary chỉ cung cấp khả năng này. Trước commit cần giữ auth export và keyring tương ứng với trạng thái quorum. Sau commit, hạ client không làm key cũ hoạt động lại nếu auth DB đã đổi active key; phục hồi phải đối soát key đang được MON chấp nhận với credential trên từng daemon. Chưa có evidence cho phép phục hồi auth DB riêng lẻ lệch với quorum đang phục vụ.

### MSG-002 — KeyRing chỉ parse plaintext ở đường decode

**CSV:** `src/auth/KeyRing.cc`, `.h`. Base `KeyRing::decode` thử đọc version và binary map, sau lỗi `buffer::error` mới gọi `decode_plaintext` trên iterator ban đầu. Target đổi `decode` thành parser plaintext trực tiếp và bỏ nhánh thử binary; commit `1bfd7853076` ghi rõ ý định. Đường `load` đọc nội dung keyring rồi gọi decoder này, nên một keyring dạng binary từng được parser base chấp nhận có thể không được target nạp; không khẳng định file triển khai hiện tại dùng dạng ấy.

**Điều kiện:** artifact keyring hoặc automation xuất dạng binary cũ thay vì văn bản `[entity]`. Trong mixed-version, binary artifact có thể được daemon base nạp nhưng target không; sau full upgrade cần mọi keyring dùng định dạng plaintext mà target nhận. **Evidence confidence:** high cho parser, medium cho khả năng gặp định dạng này trong môi trường dự án.

**Kiểm chứng:** kiểm định dạng các keyring thực tế trước rollout, thử `ceph-authtool` và daemon start trên bản sao plaintext/binary; lưu lỗi parser và quyền file. Không chuyển định dạng trực tiếp trên keyring sản xuất khi chưa có bản sao/rollback.

**Activation và tác động:** decoder plaintext tự động chạy lúc load/reload keyring bằng target; rủi ro availability là daemon không khởi động/xác thực được với artifact binary cũ. Ranh giới rollback là trước khi thay artifact keyring: giữ bản gốc và bản plaintext đã thử load cùng caps/quyền file. Đổi parser không xoay key trên MON, và phục hồi file cũ chỉ có ích nếu key trong đó vẫn là key active; workflow pending-key MSG-001 là checkpoint riêng.

### MSG-003 — Messenger v2 thương lượng nén dữ liệu trên dây

**CSV:** `src/include/msgr.h`, `src/msg/Messenger.cc/.h`, `src/msg/async/ProtocolV2.cc/.h`, `frames_v2.cc/.h`, `compression_meta.h`, `compression_onwire.cc/.h`, `src/msg/compressor_registry.cc/.h`. Base chỉ khai báo feature `REVISION_1`; target thêm `COMPRESSION` vào supported mask nhưng required mask vẫn 0. Sau auth, `ProtocolV2` chỉ trao `CompressionRequest`/`CompressionDone` khi peer có bit này; registry chọn mode/algorithm theo peer OSD, `ms_osd_compress_mode`, `ms_osd_compression_algorithm`, `ms_osd_compress_min_size` và `ms_compress_secure`. Frame assembler đặt cờ khi nén thành công, giải nén trước decode message, và reset/carry handler qua reconnect. Commit `2e46894f31e` thêm on-wire compression; endpoint code quyết định phạm vi thực tế.

**Điều kiện:** dùng msgr2, cả hai peer hỗ trợ feature và cấu hình nén hiệu dụng cho peer OSD; secure mode còn phụ thuộc `ms_compress_secure`. Với peer Pacific không có bit COMPRESSION, target đi thẳng tới session connect, nên đây là fallback theo feature, không phải bằng chứng mọi traffic đều nén. Trong mixed-version, ghi từng connection có nén hay không; sau full upgrade, CPU/băng thông có thể đổi tùy payload và ngưỡng, chưa có benchmark để định lượng. **Evidence confidence:** high cho handshake và frame path, medium cho hiệu năng/khả năng tương tác chưa chạy.

**Kiểm chứng:** lab dựng OSD/client peer 16.2.15↔17.2.7 và 17.2.7↔17.2.7 ở msgr2 secure/crc, bật/tắt config nén, chạy payload nhỏ/lớn và reconnect. Lưu negotiated feature/method, cờ frame, checksum dữ liệu, CPU, bandwidth và lỗi decode; thử một peer thiếu algorithm chung.

**Tác động và rollback:** compatibility, CPU và bandwidth đổi theo negotiation; config là opt-in, nhưng kết nối mới tự áp profile hiệu dụng. Để quay lại đường không nén cần phục hồi compression mode/algorithm rồi xác minh session được tái thương lượng; hunk registry cập nhật config không chứng minh mọi connection hiện hữu bỏ handler ngay. Payload đã được peer nhận không cần giải nén lại trên disk do đây là lớp transport, còn op đang bay cần đối soát completion/resend khi reconnect. Chưa có đo tải để dùng nén làm cơ sở rút ngắn maintenance window.

### MSG-004 — CRC dữ liệu của frame msgr2 theo `ms_crc_data`

**CSV:** `src/msg/async/ProtocolV2.cc`, `frames_v2.cc/.h`. Base frame CRC path luôn tính/kiểm CRC segment; target truyền `ms_crc_data` vào cả tx/rx assembler, ghi CRC 0 khi tắt và bỏ kiểm khi nhận. Nhánh secure dùng auth tag riêng; claim này nhắm đường CRC. Commit `f86c146cda2` nêu việc hỗ trợ tắt data CRC cho protocol v2. Nếu sender và receiver có cấu hình khác nhau trong đường CRC, cùng một frame có thể được hai đầu xử lý khác nhau; cần thử thay vì suy tương thích tự động.

**Điều kiện:** connection msgr2 dùng đường CRC và config `ms_crc_data` khác baseline. Trong mixed-version, peer Pacific vẫn có logic CRC cũ, nên phải kiểm tình huống một đầu tắt CRC trên target; sau full upgrade cần thống nhất cấu hình hiệu dụng và đánh giá mức bảo vệ dữ liệu. **Evidence confidence:** high cho hunk, medium cho kết quả tương tác thực tế.

**Kiểm chứng:** lab tạo đủ tổ hợp 16/17 và `ms_crc_data=true/false`, gửi message có payload rồi gây lỗi byte trong môi trường thử; lưu kết quả kết nối, CRC failure/acceptance và checksum application. Không tắt CRC production chỉ để thử tính năng.

**Activation, tác động và rollback:** cấu hình CRC được lấy khi tạo frame assembler, nên availability/integrity phụ thuộc tổ hợp peer và session thực tế; không coi đổi config là bằng chứng connection cũ đã đổi cách kiểm. Ranh giới phục hồi là khôi phục `ms_crc_data=true` ở peer liên quan và tái lập session đã kiểm, giữ log/checksum của workload trong giai đoạn CRC khác baseline. Bật lại CRC không phát hiện hồi tố byte sai mà ứng dụng đã chấp nhận; secure auth tag là nhánh khác, không thay thế kiểm chứng CRC-mode.

### MSG-005 — Messenger giữ riêng địa chỉ bind và địa chỉ công bố

**CSV:** `src/common/pick_address.cc/.h`, `src/msg/Messenger.cc/.h`, `src/msg/async/AsyncMessenger.cc/.h`. Base `bindv(addrs)` dùng một vector để bind và công bố; target thêm flag `CEPH_PICK_ADDRESS_PUBLIC_BIND` và tham số `public_addrs`, lưu vector này qua bind chậm/rebind, điền port được chọn nếu public port bằng 0 rồi gọi `set_myaddrs(newaddrs)`. Picker đọc `public_bind_addr`, trả `-ENOENT` khi không đặt, kiểm các mode public/public-bind/cluster loại trừ nhau và sắp thứ tự IPv4/IPv6 theo cờ ưu tiên. `set_addrs` cũ bị bỏ. Đường gọi OSD cụ thể ở [OSD-002](./01-osd-pg-recovery.md) chọn public bind riêng; finding này ghi cơ chế chung trong AsyncMessenger. Commit `bb9eb6aa2f1` liên quan đường OSD bind/public.

**Điều kiện:** cấu hình bind address khác địa chỉ peer cần dùng, hoặc messenger rebind sau khi NetworkStack chưa sẵn sàng. Trong mixed-version, daemon target có thể công bố địa chỉ khác nơi socket lắng nghe; sau full upgrade cần bảo đảm địa chỉ công bố truy cập được từ client/peer. **Evidence confidence:** high cho bind/rebind code, medium cho mạng triển khai chưa đo.

**Kiểm chứng:** lab có NIC/public bind tách biệt, kiểm socket lắng nghe, địa chỉ trong OSDMap/monmap khi phù hợp, port/nonce, kết nối từ peer khác subnet và rebind/restart; thử fallback không đặt public address riêng.

**Activation, tác động và rollback:** bind/public split áp khi daemon target bind hoặc rebind bằng cấu hình explicit, ảnh hưởng reachability/availability. Trước đổi cần lưu cả địa chỉ lắng nghe, public addrvec và routing/NAT liên quan. Nếu địa chỉ đã công bố vào map, hạ binary không tự khôi phục map hay route; phải phục hồi cấu hình hợp lệ, restart/rebind theo MOP và kiểm peer nhận địa chỉ mới trước tiếp tục. Port/nonce có thể đổi khi reconnect nên không chỉ so IP.

### MSG-006 — Định danh release và feature `SERVER_QUINCY`

**CSV:** `src/common/ceph_releases.h`, `ceph_strings.cc`, `src/include/ceph_features.h`. Base enum release dừng ở Pacific, formatter không có tên Quincy và feature mask chưa có `SERVER_QUINCY`; target thêm enum/tên/feature này, đồng thời chuyển `MON_SINGLE_PAXOS` sang retired và bỏ nó khỏi bộ feature đang quảng bá. `SERVER_QUINCY` là đầu vào của guard `require-osd-release quincy` ở [MON-001](./04-mon-osdmap-crush.md); `ceph_release_t::quincy` được dùng ở gate `min_mon_release` cho pending key ở [MON-003](./04-mon-osdmap-crush.md). Các định nghĩa này tự chúng không đặt checkpoint cluster.

**Điều kiện:** MON/OSD target quảng bá feature và quorum/OSDMap đi tới mốc Quincy. Trong mixed-version, chỉ các peer target có bit mới; sau khi persistent MON/OSD checkpoint được ghi, việc quay lại binary cũ cần thử riêng như MON-001/002. **Evidence confidence:** high cho định nghĩa và call site, medium cho kết quả rollback chưa diễn tập.

**Kiểm chứng:** lab ghi `ceph versions`, quorum feature, `ceph osd dump` và feature của từng OSD trước/sau các checkpoint; thử MON/OSD Pacific trên bản sao cluster ở từng mốc, không suy từ chuỗi tên release đơn thuần.

**Activation và tác động:** quảng bá feature tự động theo binary, còn mốc `require-osd-release` và release quorum là thay đổi state với điều kiện riêng tại MON-001/003. Tác động compatibility nằm ở gate chấp nhận daemon cũ và encode theo feature; enum/tên release không tự chuyển store. Rollback phải xác định đã vượt checkpoint MON/OSD nào; hạ package hay sửa chuỗi hiển thị không xóa feature requirement đã persist. Chưa diễn tập store clone nên không khẳng định quay lại Pacific sau full Quincy.

### MSG-007 — Decoder nhận ACK mới cho replica dentry unlink của MDS

**CSV:** `src/msg/Message.cc/.h`. Base không có type `MSG_MDS_DENTRYUNLINK_ACK`; target gán ID `0x213` và decoder tạo `MDentryUnlinkAck`. Đường gọi trong `MDCache::handle_dentry_unlink` target gửi ACK khi replica nhận thông báo `unlinking` và không còn dirfrag/dentry hoặc đã đánh dấu `STATE_UNLINKING`; phía gửi `handle_dentry_unlink_ack` giảm `replica_unlinking_ref` và giải phóng waiter. Đây là wire message/flow control mới cho MDS, không chỉ tên class. Cùng hai file còn có `MMonUsedPendingKeys` ở MSG-001; `get_data_len()` đổi kiểu trả và factory Crimson được ghi trong CSV nhưng chưa có bằng chứng về đổi payload/wire từ hai hunk đó.

**Điều kiện:** có nhiều MDS rank với replica dentry và unlink trong lúc MDS ở hai version. Endpoint diff chưa cho thấy guard theo peer version tại lệnh gửi ACK, nên không thể tự kết luận mọi tổ hợp mixed-version đều xử lý được message mới. Sau full upgrade, sender/receiver target đều có decoder. **Evidence confidence:** high cho ID/decoder/call site, medium cho interoperability MDS mixed-version.

**Kiểm chứng:** lab CephFS nhiều rank, thực hiện unlink/rename có replica trong từng tổ hợp MDS 16.2.15/17.2.7, lưu MDSMap, message decode errors, số `replica_unlinking_ref`, waiter và trạng thái client; thử failover khi ACK đang chờ.

**Activation, tác động và rollback:** ACK mới phát tự động trong đường replica unlink, ảnh hưởng continuity/correctness của MDS waiter và khả năng decode peer. Trước thay MDS cần giữ snapshot metadata và trạng thái rank theo MOP CephFS; khi unlink/ACK đã thay state, hạ messenger không tái tạo dentry hay waiter đã giải phóng. Việc full target cùng có decoder chỉ khép khoảng trống type message, không chứng minh replay metadata/downgrade MDS; phải dùng gate của owner CephFS và dừng rollout khi waiter kẹt hoặc lỗi decode.

### MSG-008 — Crash dump MGR nhận traceback Python, C backtrace ngắn hơn

**CSV:** `src/common/BackTrace.cc/.h`, `assert.cc`. Base `BackTrace` cụ thể lấy tối đa 100 frame từ C library; target tách interface đa hình, `ClibBackTrace` lấy tối đa 32 frame và `PyBackTrace` in/dump các dòng traceback Python. `src/mgr/PyModule.cc` target dùng `PyBackTrace` khi tạo crash dump cho exception module MGR; `assert.cc` target gọi `ClibBackTrace` ở các đường assert/abort. Đường C backtrace của assert/signal vẫn còn nhưng số frame tối đa giảm; đây là thay đổi tín hiệu điều tra lỗi và gate sau nâng cấp, không phải bằng chứng crash ít hơn.

**Điều kiện:** MGR Python module lỗi hoặc daemon phát sinh crash cần phân tích. Trong mixed-version, crash dump khác theo binary xử lý; sau full upgrade, operator cần đọc traceback Python từ crash record và biết C trace có thể ngắn hơn. **Evidence confidence:** high cho source và call site, medium cho giá trị chẩn đoán thực tế chưa có lỗi lab.

**Kiểm chứng:** lab gây exception có kiểm soát trong module MGR thử nghiệm và một crash C riêng, xuất crash JSON trước/sau, so số frame, tên module/caller và khả năng parser giám sát đọc được định dạng mới.

**Activation, tác động và rollback:** capture tự động khi assert/fatal signal hoặc MGR exception đi qua caller đã nêu; tác động observability là nội dung evidence thay đổi ngay ở lần crash tiếp theo. Rollback collector/parser có thể phục hồi khả năng đọc record, nhưng hạ binary không tái tạo những frame C bị cắt khỏi dump đã ghi. Giữ crash JSON/raw core cùng debug symbols đúng build trước restart; thiếu frame không đủ để kết luận lỗi không nằm sâu hơn stack.

### MSG-009 — PriorityCache thêm age bins cho cân bằng cache BlueStore

**CSV:** `src/common/PriorityCache.cc/.h`. Target thêm API `shift_bins`, `import_bins`, `set_bins`, `get_bins`; `PriorityCache::Manager::shift_bins` gọi từng cache. `BlueStore.cc` target nhập các bin KV/onode/meta/data và gọi `pcm->shift_bins()` khi `cache_age_bin_interval > 0` và tới thời điểm xoay bin. Base interface/đường gọi này không có. Do đó lịch sử truy cập theo tuổi có thể tham gia điều chỉnh dung lượng cache, nhưng diff không đủ để dự báo hit rate hay latency.

**Điều kiện:** BlueStore dùng cơ chế age-bin và bộ quản lý cache; `cache_age_bin_interval` có hiệu lực. Trong mixed-version, từng OSD quản lý cache cục bộ theo binary của nó; sau full upgrade, hành vi cân bằng này áp dụng ở OSD target có điều kiện. **Evidence confidence:** high cho call path, medium cho tác động hiệu năng.

**Kiểm chứng:** lab với cùng RAM/IO, ghi effective cache options, kích thước các bin, cache allocation/hit rate, RSS và client latency trước/sau; thử tải đọc/ghi theo tuổi dữ liệu và tình huống OSD memory target thấp.

**Activation và rollback:** age-bin chạy tự động theo chu kỳ khi cấu hình cache đang bật cơ chế đó; tác động performance/capacity cần đo với cùng RAM và workload. Ranh giới phục hồi là config cache trước thử nghiệm và baseline hit rate/RSS; thay binary làm mất lịch sử cache cục bộ và có warm-up, không đưa cache về đúng trạng thái đo trước đó. Chưa có effective options hay đường tải thực tế để khẳng định lợi/hại; nếu cần thay daemon, khả năng mở store vẫn phải qua BlueStore gate riêng.

### MSG-010 — CommonSafeTimer dùng đồng hồ monotonic

**CSV:** `src/common/Timer.cc/.h`, `condition_variable_debug.h`. Base `CommonSafeTimer` đặt `clock_t = ceph::real_clock`; target đổi sang `ceph::mono_clock`, giữ overload nhận thời điểm real clock rồi quy đổi theo hiệu hai đồng hồ tại lúc đăng ký. Ở build bật debug mutex, `condition_variable_debug::wait_until` target đổi deadline steady clock sang realtime trước `pthread_cond_timedwait`; base chuyển thẳng bằng clock của caller. Deadline tương đối trong hàng đợi không còn đi theo bước nhảy của wall clock; phép quy đổi vẫn chịu sai số lúc lấy mẫu. Đây là đường hẹn giờ chung được nhiều daemon dùng, không chứng minh mọi timeout đều đổi vì còn các timer khác.

**Điều kiện:** host chỉnh giờ/NTP step trong khi daemon có callback đang chờ. Trong mixed-version, daemon base/target có thể kích hoạt callback tại thời điểm khác nhau khi wall clock nhảy; sau full upgrade, timer này dùng monotonic. **Evidence confidence:** high cho kiểu clock/convert, medium cho tình huống production chưa đo.

**Kiểm chứng:** lab cô lập đặt callback real/relative, mô phỏng bước nhảy wall clock tiến/lùi, ghi thời gian monotonic thực đến callback và quan sát các daemon dùng `CommonSafeTimer`; không chỉnh đồng hồ cluster production.

**Activation, tác động và rollback:** timer target tự động dùng monotonic khi đăng ký callback; tác động availability là thời điểm timeout/retry sau clock step có thể đổi. Hàng đợi timer là state trong process, nên restart/hạ binary hủy lịch đang chạy theo lifecycle daemon chứ không chuyển deadline target thành deadline Pacific tương đương. Cần quiesce tác vụ, ghi callback đang chờ và kiểm phục hồi/retry sau restart; side effect callback đã chạy không được undo khi đổi clock implementation.

### MSG-011 — Đọc optimal IO size cho đường cấp phát BlueStore

**CSV:** `src/common/blkdev.cc/.h`. Target `BlkDev::get_optimal_io_size()` đọc `queue/optimal_io_size` trên Linux; các nhánh platform không hỗ trợ trả 0. `KernelDevice` nạp giá trị này, `BlueStore::_open_bdev` lưu lại; khi `bluestore_use_optimal_io_size_for_min_alloc_size` bật và giá trị khác 0, BlueStore dùng nó làm `min_alloc_size`. Base không có API/call path này. Đây là thay đổi alignment/cấp phát có điều kiện; không suy layout on-disk đã đổi với mọi OSD chỉ từ hunk common.

**Điều kiện:** OSD BlueStore trên block device báo optimal IO size khác 0 và option trên được bật. Trong mixed-version, OSD target có thể chọn granularity khác base trên cùng loại device; sau full upgrade cần kiểm giá trị hiệu dụng và khả năng restart/rollback trên bản sao store. **Evidence confidence:** high cho sysfs/call path, medium cho ảnh hưởng thực tế chưa có geometry dự án.

**Kiểm chứng:** ghi `queue/optimal_io_size`, effective option và `min_alloc_size` ở từng OSD; lab trên clone thử mkfs, ghi/đọc, fsck và restart với device geometry tương ứng, so số extent/space amplification. Không đổi option trên production trước khi có kết quả lab.

**Activation và tác động:** caller chọn `min_alloc_size` thuộc đường mkfs BlueStore; điều kiện đầy đủ là tạo/recreate store bằng target, option được bật và device báo geometry hợp lệ. Restart OSD đang có store không tự áp lại lựa chọn mkfs này. Tác động space amplification/correctness phải đánh giá trên store tạo ra; điểm rollback nằm trước mkfs và trước ghi dữ liệu mới, vì tắt option hoặc hạ binary không đổi granularity đã lưu. Cần giữ geometry, metadata store và kiểm BlueStore format gate trước bất kỳ failback nào.

### MSG-012 — Chuẩn hóa model trong device ID metadata

**CSV:** `src/common/blkdev.cc`. Hàm `_decode_model_enc` target gộp mọi cặp `__` trong model thành `_` sau khi đổi khoảng trắng, rồi `get_device_id()` tạo ID. `get_device_metadata()` ghi các ID này vào trường `device_ids` của metadata daemon; base giữ `__`. Thay đổi chỉ hiện với model có chuỗi đó, không đổi serial hay thiết bị thực. Hunk sửa chuỗi lỗi fallback chỉ đổi câu chữ.

**Điều kiện:** host có device model chứa double underscore và tooling đối chiếu `device_ids` theo chuỗi. Trong mixed-version, cùng device có thể được báo bằng hai ID khác nhau theo binary đang chạy; sau full upgrade ID metadata target ổn định theo normalization mới. **Evidence confidence:** high cho hàm/call site, medium cho host thực tế và automation chưa biết.

**Kiểm chứng:** inventory read-only trên host/canary, đối chiếu `device_ids` trước/sau với `/sys` và serial, kiểm dashboard/automation có khóa theo chuỗi này không; xác nhận OSD vẫn trỏ đúng device path.

**Activation, tác động và rollback:** normalization tự động lúc lấy device metadata, ảnh hưởng observability/identity trong inventory thay vì đổi block-device identity. Trước cập nhật collector cần lưu mapping ID cũ↔serial/path↔ID mới và kiểm collision do gộp underscore. Hạ daemon có thể báo lại chuỗi cũ nhưng không hoàn tác record/association mà database giám sát đã lưu; reconcile inventory phải theo serial/path đã xác thực, không xóa hoặc thay device chỉ vì chuỗi ID khác.

### MSG-013 — LogSummary v4 lưu channel và khóa chống lặp

**CSV:** `src/common/LogEntry.cc/.h`, `LRUSet.h`. Base `LogSummary` encode v3 gồm `version`, `seq`, `tail_by_channel`; target encode v4 thêm `channel_info` và `recent_keys` trong một LRU set có encode/decode. `LogEntry::encode` target bỏ nhánh cho peer trước Nautilus; `LogSummary::encode` đòi `SERVER_MIMIC`, decoder vẫn khai báo legacy compat nhưng đọc trực tiếp `seq`/`tail_by_channel` rồi thêm hai trường khi v4. `src/mon/LogMonitor.cc/.h` sử dụng format/store mới theo [MON-009](./04-mon-osdmap-crush.md). Đây là thay đổi persisted cluster log và dedup; không coi `compat 3` là chứng minh rollback Pacific an toàn.

**Điều kiện:** MON có cluster log lịch sử, đặc biệt restart/replay hoặc rollback trên store đã được Quincy ghi. Trong mixed-version, MON cũ/mới có thể nhìn các bản ghi khác theo quorum/store; sau full upgrade summary v4 được ghi. **Evidence confidence:** high cho encode/decode/call path, medium cho tương thích store thực tế chưa thử.

**Kiểm chứng:** trên clone MON store, nâng và restart quanh checkpoint, đối chiếu `ceph log last`, dải sequence từng channel, khóa chống lặp và số entry; thử Pacific binary trên bản sao sau khi target đã ghi để xác định ranh giới rollback.

**Tác động và ranh giới:** correctness/observability của cluster log phụ thuộc summary persist và dedup sau replay. Format mới được ghi tự động qua LogMonitor target khi tiến triển log; điểm rollback cần snapshot MON store nhất quán trước đó, không chỉ export vài dòng log. Hạ binary không tái tạo entry đã trim và không được suy compat=3 bảo toàn toàn bộ `channel_info`/`recent_keys` khi re-encode. So seq từng channel và duplicate trên clone trước quyết định phục hồi quorum.

### MSG-014 — Thêm đích Journald cho log local và cluster

**CSV:** `src/common/Journald.cc/.h`, `Graylog.cc`, `ceph_context.cc`, `common_init.cc`, `src/log/Log.cc/.h`. Target có `JournaldLogger` cho local log và `JournaldClusterLogger` cho MON cluster log, gửi qua Unix datagram và dùng fd tạm khi entry lớn; nếu build không có `WITH_SYSTEMD`, class là no-op. `Log::_flush` chỉ gửi khi level và logger bật; `ceph_context.cc` theo dõi `log_to_journald`/`err_to_journald`, còn `LogMonitor` dùng `mon_cluster_log_to_journald`. `start_graylog` target nhận host/fsid trước khi phát; `Graylog::set_hostname` assert host không rỗng. `common_preinit` target điền `host` từ short hostname khi config còn rỗng, nên metadata/đường Graylog có giá trị host ở trường hợp đó. Đây là thay đổi vị trí và metadata của tín hiệu vận hành, tùy build/config.

**Điều kiện:** build có Systemd và cấu hình chọn Journald/Graylog. Trong mixed-version, các daemon có thể ghi sang đích khác nhau theo binary/config; sau full upgrade cần xác nhận collector và retention đọc đủ local, crash và cluster log. **Evidence confidence:** high cho code, medium cho hệ thống thu thập log của dự án chưa biết.

**Kiểm chứng:** lab/canary ghi effective config, build flag và một log local/cluster thử, đối chiếu file/syslog/Journald/Graylog về timestamp, fsid, channel, severity và bản ghi trùng/thiếu; thử entry lớn để xác nhận nhánh fd.

**Activation, tác động và rollback:** routing opt-in theo build/config, tác động observability là log có thể tới đích mới hoặc mất nếu socket journal không sẵn; `JournaldClient::send` có nhánh ENOENT im lặng. Trước chuyển collector cần giữ route file/syslog hiện tại và policy retention. Rollback config đưa log tương lai về đích cũ nhưng không chuyển các record chỉ nằm trong journal/Graylog hoặc phục hồi record đã không gửi thành công. Giữ raw log theo fsid/host/time để đối soát gap trước tiếp tục rollout.

### MSG-015 — Parser chuỗi cấu hình có thể đổi route `clog_*`

**CSV:** `src/common/LogClient.cc/.h`, `str_map.cc`, `src/include/str_map.h`. Base parse các `clog_to_monitors`, `clog_to_syslog`, facility/level và Graylog thành map rồi `get_str_map_key` lấy giá trị theo channel hoặc `default`. Target gọi `get_value_via_strmap(conf_string, log_channel, default)` cho từng channel. Trong endpoint target, overload này trả rỗng khi map có hơn một mục; với đúng một mục `k=channel`, nó trả `k` thay vì `v`. Chẳng hạn `cluster=true` cho channel `cluster` cho ra `cluster`, nên phép so với `"true"` trong `LogChannel::update_config` là false; map `default=true,cluster=false` cho ra rỗng. `get_str_map` còn đổi gán key lặp từ overwrite sang `emplace`, nên key đầu thắng. Đây là kết luận trực tiếp từ code về các dạng input ấy, chưa phải bằng chứng cluster hiện dùng chúng.

**Điều kiện:** cấu hình `clog_*` có giá trị riêng theo channel hoặc nhiều mục, hay có key lặp. Dạng mặc định một mục `default=true` và channel khác `default` vẫn có thể trả `true`; không suy toàn bộ cluster logging bị tắt. Trong mixed-version, daemon target/base có thể route cùng log khác nhau; sau full upgrade cần kiểm đường MON/syslog/Graylog hiệu dụng. **Evidence confidence:** high cho nhánh parser, medium cho applicability và kết quả end-to-end chưa chạy.

**Kiểm chứng:** lab thử ba dạng `default=true`, `cluster=true`, `default=true,cluster=false` cho từng `clog_*`, ghi `ceph config show`, output ở MON/syslog/Graylog và log channel thực; giữ baseline Pacific cùng input. Nếu pipeline dùng cluster log làm gate, xác nhận nó không bị mất do route.

**Activation, tác động và rollback:** regression tự động khi target parse config channel hiện có, không cần operator bật tính năng mới. Tác động observability/availability của acceptance gate là warning có thể không tới MON hoặc sink dự kiến. Ranh giới phục hồi là lưu input config và route test đã xác nhận trước thay binary; chỉ phục hồi cùng chuỗi multi-entry trên target vẫn đi qua nhánh lỗi. Phải chọn config được probe chứng minh hoặc artifact đã kiểm; log mất trong khoảng route sai không được replay tự động chỉ bằng config rollback.

### MSG-016 — `set_max_recent` không còn đổi capacity của vòng log gần đây

**CSV:** `src/log/Log.cc/.h`. Base `Log::set_max_recent(n)` gọi `m_recent.set_capacity(n)`; target chỉ gán `m_max_recent = n`, còn `EntryRing m_recent` vẫn được dựng bằng `DEFAULT_MAX_RECENT` và không có call site target khác đổi capacity. `dump_recent()` cũng in `max_new` bằng `m_max_recent` thay vì `m_max_new`. Vì vậy cấu hình `log_max_recent` có thể hiển thị giá trị mới mà số entry giữ lại không đổi theo nó; đây là giới hạn quan sát khi điều tra sự cố rollout.

**Điều kiện:** operator đặt `log_max_recent` khác default và dùng recent/crash dump để chẩn đoán. Trong mixed-version, daemon base/target có thể giữ số log khác nhau dù effective config giống nhau; sau full upgrade cần đo thực tế vì code không điều chỉnh ring. **Evidence confidence:** high cho setter và khởi tạo, medium cho tình huống log/crash thực tế chưa đo.

**Kiểm chứng:** lab đặt `log_max_recent` thấp/cao, phát hơn ngưỡng entry, gọi `dump_recent` và đếm bản ghi cùng dòng metadata; so hai endpoint, kiểm các parser/gate không tin dòng `max_new` target là giá trị thực.

**Rollback:** đây là giới hạn observability tự động khi setter target nhận `log_max_recent`; tăng giá trị không chứng minh ring đã tăng. Trước canary cần lưu log ra sink ngoài và đo số entry thật. Hạ binary/restart có thể khôi phục cách set capacity cho lần chạy sau nhưng xóa ring trong process và không tái tạo entry đã bị evict. Thu dump/core trước restart khi đang điều tra lỗi, rồi kiểm số entry thay vì tin metadata `max_new`.

### MSG-017 — FileStore đổi timeout WorkQueue tại runtime

**CSV:** `src/common/WorkQueue.h`. Target thêm `set_timeout` và `set_suicide_timeout` để gán lại hai khoảng timeout của queue. `FileStore::handle_conf_change` target gọi chúng khi `filestore_op_thread_timeout` hoặc `filestore_op_thread_suicide_timeout` đổi; base không có hai setter. Đường FileStore cụ thể cũng được ghi ở [BLU-010](./02-bluestore-bluefs.md). Hunk common này có call site production nên là `affect`, dù hai phương thức chỉ gồm phép gán.

**Điều kiện:** còn FileStore OSD và operator thay hai option trong lúc daemon chạy. Trong mixed-version, OSD base/target phản ứng với thay đổi config theo code riêng; sau full upgrade, timeout queue target cập nhật mà không cần restart. **Evidence confidence:** high cho setter và call site, medium cho tác động khi queue đang kẹt chưa chạy lab.

**Kiểm chứng:** trên FileStore lab, đổi timeout hiệu dụng khi queue đang có tải, theo dõi heartbeat/timeout của worker, log suicide và tiến độ IO; lặp với giá trị cũ/mới trên cùng workload.

**Rollback:** tác động availability phát sinh khi operator đổi timeout explicit; phục hồi option cũ chỉ điều chỉnh quyết định timeout về sau. Callback heartbeat/suicide đã kích hoạt, daemon đã dừng hoặc I/O đã trả lỗi không được hoàn tác bằng set lại giá trị. Giữ baseline timeout và workload progress trước thử; nếu đã có OSD restart cần đối soát peering/recovery và FileStore journal trước tiếp tục. Chưa có lab để xác nhận hành vi đúng lúc queue đang xử lý khi setter đổi.

### MSG-018 — Admin socket chuyển payload vào hook đồng bộ

**CSV:** `src/common/admin_socket.cc/.h`. Cả hai endpoint đã nhận `inbl` ở `execute_command` và `call_async`; base default `call_async` bỏ buffer này khi gọi `call`, target truyền tiếp vào chữ ký `AdminSocketHook::call`. Các hook đồng bộ trong hai hunk này không đọc payload. Khả năng mới có ý nghĩa với hook tùy biến nhận dữ liệu `ceph --in-file`/`tell` qua đường đồng bộ; mã C++ hook ngoài cây cũng cần biên dịch lại theo chữ ký target. Chưa có bằng chứng một hook trong hai file dùng payload để thay đổi trạng thái.

**Điều kiện:** có hook đồng bộ tự viết hoặc command gửi payload tới hook ấy. Trong mixed-version, cùng payload có thể tới `call` ở daemon target nhưng bị default adapter base bỏ qua; sau full upgrade đường truyền payload hiện diện. **Evidence confidence:** high cho forwarding/chữ ký, medium cho ứng dụng thực tế vì chưa xác định hook tùy biến của cluster.

**Kiểm chứng:** liệt kê plugin/hook tùy biến và lệnh `--in-file`; lab gửi payload định danh qua admin socket và `tell` ở hai endpoint, xác nhận hook nhận byte đúng, kết quả và lỗi; biên dịch lại hook trước khi rollout.

**Activation, tác động và rollback:** forwarding payload tự động trong adapter target, nhưng ảnh hưởng thực tế conditional vào hook ngoài cây; compatibility gồm cả chữ ký C++ và semantic input. Trước triển khai giữ binary daemon/hook đồng bộ và fixture request-response. Rollback hook riêng không đủ nếu vtable/chữ ký khác; phải phục hồi artifact pair rồi restart theo gate daemon. Nếu hook có mutation và đã nhận payload target, hạ API không undo tác vụ đó; chưa có inventory hook để xác định điểm commit.

### MSG-019 — CephContext Crimson phơi bày plugin registry chưa khởi tạo trong constructor

**CSV:** `src/common/ceph_context.h`. Target thêm `_plugin_registry` và getter trong nhánh `WITH_SEASTAR && !WITH_ALIEN`; constructor Crimson ở `ceph_context.cc` chỉ khởi tạo config, perf collection và random, không đặt pointer mới. `Compressor::create` target dereference kết quả `get_plugin_registry()` qua `get_with_load`. Endpoint này cho thấy một rủi ro nếu đường plugin ấy được gọi với Crimson context; không khẳng định OSD Crimson mặc định gọi nó, hay binary đã lỗi trong triển khai.

**Điều kiện:** build Crimson và có call site dùng plugin registry qua context này. Trong mixed-version, chỉ binary target có getter này; sau full upgrade classic CephContext vẫn khởi tạo registry riêng, nên rủi ro giới hạn ở nhánh Crimson. **Evidence confidence:** high cho trạng thái khởi tạo/đọc source; medium cho reachability runtime chưa chạy build/lab.

**Kiểm chứng:** build Crimson với compiler diagnostics/sanitizer, truy call path compressor/crypto từ Crimson, thử tạo compressor/plugin trong lab và xác nhận pointer hợp lệ; nếu không reachable thì ghi rõ giới hạn này trước khi kết luận mức rủi ro.

**Tác động và rollback:** availability chỉ là rủi ro conditional khi Crimson thực sự gọi getter/plugin path; presence của pointer chưa khởi tạo không chứng minh mọi startup crash. Activation là tự động trong process đã build đúng nhánh và đi vào caller đó. Trước thử giữ artifact/config và clone SeaStore; nếu sanitizer phát hiện truy cập không hợp lệ, dừng đường plugin để điều tra reachability. Hạ executable không sửa state mà operation trước crash đã ghi và không bỏ qua gate SeaStore/replay.

### MSG-020 — Crimson OSD chỉ còn msgr2

**CSV:** `src/crimson/net/ProtocolV1.cc/.h`, `SocketConnection.cc`. Base tạo `ProtocolV1` hoặc `ProtocolV2` theo loại địa chỉ và có implementation msgr1; target xóa hai file v1, constructor chỉ tạo `ProtocolV2`. `SocketMessenger::connect` target gọi abort khi peer address không phải msgr2; `try_bind` đòi đúng một địa chỉ v2 và `start` assert v2. Đây là thay đổi riêng của Crimson messenger, không suy msgr1 bị bỏ trong classic OSD.

**Điều kiện:** dùng `crimson-osd` và có peer/config chỉ đưa địa chỉ legacy. Trong mixed-version, Crimson target cần nhìn thấy msgr2 address của Pacific peer; sau full upgrade mọi peer mà Crimson kết nối vẫn cần v2. **Evidence confidence:** high cho nhánh construct/connect/bind; medium cho khả năng dùng legacy address trong cluster chưa có inventory.

**Kiểm chứng:** lab dùng `crimson-osd` target với MON/OSD/client Pacific và Quincy, ghi address vector, connection attempt và log khi có cả v1/v2 hoặc chỉ v1; kiểm failure có kiểm soát ở cấu hình thiếu msgr2 trước rollout.

**Activation, tác động và rollback:** giới hạn protocol tự động khi target Crimson bind/connect, ảnh hưởng availability với địa chỉ v1-only ngay cả khi peer vẫn hỗ trợ v2 ở nơi khác. Trước rollout cần có v2 addrvec/port thực sự reachable; thêm config kiểu msgr1 trên target không khôi phục implementation đã xóa. Rollback artifact Crimson phải đồng bộ dependency và store gate, còn addrvec đã công bố và session peer cần kiểm lại; không hạ toàn cluster chỉ từ lỗi transport này.

### MSG-021 — Crimson bind retry và học địa chỉ cho OSD boot

**CSV:** `src/crimson/net/Messenger.h`, `Socket.cc/.h`, `SocketMessenger.cc/.h`. Base `bind` gọi `do_bind` một lần; target `try_bind` dò port rồi `bind` thử lại theo `ms_bind_retry_count`/`ms_bind_retry_delay`, phân biệt `address_in_use` và `address_not_available`. `set_addr_unknowns` điền IP trống từ địa chỉ cùng family; `crimson/osd/osd.cc::_send_boot` dùng nó cho cluster và heartbeat address trước khi gửi `MOSDBoot`. `learned_addr` target chọn địa chỉ peer báo hoặc địa chỉ socket local theo `ms_learn_addr_from_peer`. `Socket::read_exactly` còn xem short read là EOF thay vì chỉ buffer rỗng.

**Điều kiện:** dùng Crimson OSD, bind port bận/địa chỉ chưa có trên host, IP trống hoặc `ms_learn_addr_from_peer` khác baseline. Trong mixed-version, MON và peer nhận địa chỉ boot do binary Crimson target tính; sau full upgrade cần xác nhận địa chỉ public/cluster/heartbeat có thể kết nối. **Evidence confidence:** high cho call path và retry/error branch, medium cho topology host thực tế.

**Kiểm chứng:** lab bind vào port bận và IP chưa sẵn sàng, ghi số lần thử/delay và lỗi cuối; với nhiều NIC/family, so địa chỉ `MOSDBoot`, OSDMap, heartbeat và kết nối thực tế khi bật/tắt `ms_learn_addr_from_peer`. Thử peer đóng socket giữa read để xác nhận EOF.

**Activation, tác động và rollback:** retry/học địa chỉ tự động khi Crimson target khởi động, kết nối hoặc xử lý boot; tác động availability nằm ở thời gian chờ bind và địa chỉ peer thực sự dùng. Trước đổi giữ retry options, NIC/IP và addrvec đã công bố. Rollback config không xóa địa chỉ đã gửi vào OSDMap, và restart để đổi binary cần chờ peer học địa chỉ/nonce hiện hành. Nếu EOF đến giữa message, đối soát completion/resend trước retry ứng dụng; read ngắn không chứng minh op chưa được peer thực thi.

### MSG-022 — Crimson đổi sở hữu message trong hàng gửi và ACK

**CSV:** `src/crimson/net/Connection.h`, `Protocol.cc/.h`, `SocketConnection.h`, `src/common/RefCountedObj.h`, `src/msg/MessageRef.h`. Base giữ `MessageRef` trong `out_q`, `pending_q`, `sent`; target thêm `MessageURef` với `UniquePtrDeleter` gọi `put()`, encode batch từ `out_q`, chuyển message reliable trực tiếp sang `sent` rồi xóa `out_q`. `requeue_sent` reset payload/seq và chuyển lại khi reconnect; `ack_writes` xóa đến ACK seq. Đây là thay đổi thời điểm sở hữu/lifetime của message; diff chưa chứng minh có mất/trùng bản tin trong vận hành.

**Điều kiện:** Crimson OSD gửi message và gặp ACK, reconnect hoặc fault khi còn batch chờ. Trong mixed-version, wire format vẫn do protocol v2 quyết định, nhưng resend behavior phía Crimson target có thể khác; sau full upgrade cần kiểm ranh giới ACK. **Evidence confidence:** high cho queue transitions, medium cho race/tác động runtime chưa thử.

**Kiểm chứng:** lab dùng breakpoint/fault injection ở trước/sau `socket->write`, ngắt peer trước ACK, đếm sequence, `out_q`/`sent`, duplicate và loss cho policy reliable/lossy; so với Crimson base cùng workload.

**Activation và rollback:** ownership mới tự động áp cho mọi send của Crimson target; tác động correctness/availability phải kiểm tại ranh giới write và ACK. `sent`/`out_q` là bộ nhớ process, nên hạ binary không mang queue cũ sang implementation Pacific. Quiesce đường gửi và ghi sequence/completion trước thay process; sau fault cần để protocol/application reconcile reliable resend, không diễn giải ACK mất như bằng chứng write chưa commit. Rollback store sau I/O đã commit vẫn bị chi phối bởi backend Crimson riêng.

### MSG-023 — Crimson msgr2 giữ compression feature tắt trong banner

**CSV:** `src/crimson/net/ProtocolV2.cc/.h`. Macro chung `CEPH_MSGR2_SUPPORTED_FEATURES` ở target có COMPRESSION như MSG-003, nhưng Crimson target dùng mask riêng chỉ có `REVISION_1` và chú thích COMPRESSION chưa bật. Frame assembler Crimson target nhận `ms_crc_data` và pointer compression handler; handshake reset handler, nhưng không thương lượng compression qua banner hiện tại. Target cũng đổi hàm disassemble frame và nới kiểm địa chỉ peer ở `server_connect`. Do đó không dùng finding MSG-003 để khẳng định traffic Crimson được nén.

**Điều kiện:** kết nối từ/to Crimson OSD qua msgr2, đặc biệt khi option CRC thay đổi hoặc peer quảng bá compression. Trong mixed-version, peer classic target có thể có compression feature nhưng Crimson target không quảng bá; sau full upgrade Crimson vẫn không tham gia negotiation theo code endpoint này. **Evidence confidence:** high cho mask/assembler, medium cho kết quả liên thông và CRC chưa có lab.

**Kiểm chứng:** lab ghép Crimson với classic OSD Pacific/Quincy, đọc banner negotiated bits, thử `ms_crc_data` hai đầu và payload có thể nén, xác nhận không có compression frame ở Crimson, message decode/CRC và reconnect.

**Activation, tác động và rollback:** mask không quảng bá compression là tự động và không thể đổi chỉ bằng option classic compression; tác động compatibility là phải giữ nhánh transport không nén khi có Crimson. CRC config vẫn tác động assembler như MSG-004. Nếu liên thông lỗi, phục hồi CRC/config baseline và tạo lại connection để kiểm banner; hạ một peer không tự xóa session state của peer kia. Full target không mở gate compression Crimson ở endpoint này, nên benchmark không được gộp link Crimson vào nhóm đã nén.

### MSG-024 — Fatal signal handler xử lý một lần và bổ sung crash metadata MGR

**CSV:** `src/global/signal_handler.cc/.h`. Base `handle_fatal_signal` đăng ký `SA_RESETHAND | SA_NODEFER`; target dùng `handle_oneshot_fatal_signal`, atomic `handler_tid` chặn thread khác vào cùng đường crash, đặt `SIG_DFL` trước khi raise lại. Logic ghi dump được tách thành `generate_crash_dump`, nhận map `extra`; `mgr/PyModule.cc` dùng nó đưa thông tin Python exception vào crash JSON. C backtrace ở signal path chuyển sang `ClibBackTrace` theo MSG-008. Hành vi này đổi tín hiệu điều tra sự cố, không chứng minh daemon ổn định hơn.

**Điều kiện:** daemon/MGR gặp fatal signal hoặc Python module error. Trong mixed-version, crash record do daemon target/base tạo khác nhau; sau full upgrade, parser giám sát cần chấp nhận các trường bổ sung, và core dump vẫn phụ thuộc OS limit/handler. **Evidence confidence:** high cho handler/call site, medium cho kết quả crash thực tế.

**Kiểm chứng:** lab cô lập tạo một lỗi fatal và lỗi Python module, so crash JSON, backtrace/core file, log và behavior khi hai thread lỗi gần đồng thời; kiểm parser thu thập crash vẫn nhận bản ghi mới.

**Activation, tác động và rollback:** handler tự động được dùng khi fatal signal xảy ra; tác động observability/availability là một thread ghi dump còn thread lỗi đồng thời chờ đường xử lý kết thúc. Đổi config collector không thay handler trong process. Trước restart/failback phải giữ crash JSON, signal, core và symbols của đúng binary; hạ binary chỉ thay crash tiếp theo, không bổ sung metadata đã thiếu hoặc phục hồi state trước fatal signal. Chưa kiểm core policy của service manager nên việc handler reraise không bảo đảm file core được lưu.

### MSG-025 — Build từ source đòi `std::filesystem` ở hai đường khởi tạo

**CSV:** `src/common/ConfUtils.cc`, `src/global/global_init.cc`. Base chọn `std::filesystem` nếu header có sẵn, rồi fallback sang `std::experimental::filesystem`; target include `<filesystem>` và đặt alias `std::filesystem` trực tiếp ở cả hai file. `global_init` còn thêm `std::` cho `ostringstream` mà không đổi nhánh runtime. Tác động là yêu cầu toolchain khi build từ source, không phải thay đổi nội dung config file hay đường khởi tạo của binary đã build thành công.

**Điều kiện:** pipeline tự build Quincy với compiler/standard library cũ chỉ có `experimental/filesystem`. Trong mixed-version, binary Pacific đã build không bị đổi; binary target cần build thành công trước khi rollout. Sau full upgrade, host chỉ chạy package có sẵn không trực tiếp chịu điều kiện compile này. **Evidence confidence:** high cho include/alias hai endpoint, medium cho toolchain của dự án chưa có inventory.

**Kiểm chứng:** ghi compiler, C++ standard library và CMake flags của CI/package builder; thử compile hai translation unit bằng toolchain hiện dùng và toolchain dự định cho Quincy, lưu lỗi link/include nếu có. Nâng toolchain trước khi đóng gói nếu fallback cũ là điều kiện build của dự án.

**Rollback artifact:** activation ở compile/link explicit, tác động compatibility/delivery xuất hiện trước rollout nếu standard library thiếu filesystem. Giữ builder image/toolchain và package Pacific đã kiểm trước nâng CI; hạ compiler đơn lẻ không làm source Quincy có lại nhánh experimental. Nếu target build thất bại thì chưa có thay đổi cluster từ hai hunk này; nếu đã phát hành binary, failback phải dùng package cùng dependency đã pin và vẫn xét gate daemon đã chạy.

### MSG-026 — `BitVector` đổi hậu tố tăng của iterator RBD

**CSV:** `src/common/bit_vector.hpp`. Base `IteratorImpl::operator++(int)` sao chép iterator cũ, tăng `*this`, rồi trả bản sao; target tăng bản sao và trả nó, để iterator gốc đứng yên. Template này là kiểu iterator của `BitVector<2>` dùng cho RBD object map trong `librbd/ObjectMap`, request object map và `cls/rbd`. Các vòng lặp production đã xem dùng tiền tố `++it`, nên diff chưa chứng minh một thao tác RBD hiện tại bị kẹt; nếu có caller dùng `it++`, nó không tiến như hợp đồng iterator thông thường.

**Điều kiện:** code hoặc plugin thao tác RBD object map dùng hậu tố `it++` trên iterator này. Trong mixed-version, binary chứa caller target có hành vi khác base, còn wire/object-map encoding không đổi từ hunk này; sau full upgrade cần xác nhận không có vòng lặp phụ thuộc hậu tố. **Evidence confidence:** high cho khác biệt operator, medium cho reachability vì chưa thấy call site production trong cây hiện tại.

**Kiểm chứng:** rà toàn bộ caller và extension nội bộ dùng `BitVector`, chạy test nhỏ so `auto old = it++` với offset của `it` ở hai tag; thêm workload RBD object-map resize/update/diff vào lab nếu có caller liên quan.

**Activation, tác động và rollback:** lỗi iterator tự động xuất hiện trong binary đã instantiate caller dùng hậu tố; correctness/availability hiện còn conditional vì các vòng production đã đọc dùng tiền tố. Full Quincy không làm postfix tự đúng trở lại. Rollback phải rebuild hoặc phục hồi cả consumer chứa template, không chỉ shared library vì code có thể inline. Nếu caller đã sửa object map sai trước khi dừng, đổi binary không phục hồi các bit persist; cần giữ object-map/image checkpoint và kiểm map rebuild theo owner RBD thay vì suy có thể undo bằng iterator.

### MSG-027 — Bloom filter đổi bộ nhớ bảng bit và đường encode

**CSV:** `src/common/bloom_filter.cc/.hpp`, `src/include/intarith.h`. Base giữ bảng bit bằng vùng mempool cấp phát thủ công, encode qua `bufferptr`, decode từ `bufferlist`; target giữ trong `mempool::bloom_filter::vector`, encode/decode vector và đổi `compress()` sang vector tạm. Header target thêm `popcount()` được `density()` gọi khi đếm bit; đồng thời bỏ `round_down_to` nhưng không thấy caller trong cây target. `BloomHitSet` dùng filter cho OSD HitSet, còn BlueStore dùng trong fsck. Với bảng rỗng, base `density()` trả `0.0`, target tính `0/0` vì không có guard; đường `BloomHitSet::seal` lấy density để chọn nén. Version encode ngoài vẫn là 2, nhưng chỉ từ code không coi đó là chứng minh mọi dữ liệu cũ/mới đọc qua lại thành công.

**Điều kiện:** OSD có Bloom HitSet đã lưu/replay hoặc BlueStore fsck dùng filter, đặc biệt filter rỗng hay lúc seal/compress. Trong mixed-version, OSD ở hai binary có thể encode/decode hoặc tính density khác nhau; sau full upgrade cần kiểm dữ liệu HitSet cũ và thống kê fsck. **Evidence confidence:** high cho cấu trúc/density và call path, medium cho tương thích byte thực tế chưa chạy roundtrip.

**Kiểm chứng:** lab tạo filter rỗng, không rỗng và đã nén ở Pacific; encode rồi decode bằng Quincy và ngược lại, so bit table, `contains`, `density`, HitSet seal và fsck BlueStore trên bản sao. Ghi payload bytes và lỗi decoder nếu có.

**Activation, tác động và rollback:** encode/decode/density tự động theo binary khi HitSet/fsck dùng filter; tác động compatibility/correctness nằm ở payload và giá trị NaN của filter rỗng. Trước target ghi HitSet giữ payload Pacific cùng metadata object; sau target ghi, chỉ test đọc chéo trên clone mới xác định failback consumer có bảo toàn bit table. Xóa HitSet để né decode sẽ mất history, còn hạ binary không sửa filter đã ghi hoặc kết quả fsck đã được operator dùng cho repair. Chưa có byte-roundtrip nên giữ gate này mở.

### MSG-028 — Bufferlist đổi tăng trưởng bộ đệm và gom iovec cho Crimson

**CSV:** `src/common/buffer.cc`, `buffer_instrumentation.h`, `src/include/buffer.h`. Base `refill_append_space` cấp một đơn vị theo nhu cầu; target có thể nhân đôi vùng append hiện tại tới ngưỡng 256 KiB, đổi `c_str()` để khỏi rebuild khi chỉ có một buffer có dữ liệu và buffer rỗng kèm theo. Target thêm `prepare_iovs()` trong source/header để chia danh sách buffer theo `IOV_MAX`; `crimson/os/seastore/segment_manager/block.cc` dùng nó ở `do_writev`. Header cũng tách C++17 if-initializer thành cú pháp C++11 để giữ khả năng build librados. Mã cấp `_num / IOV_MAX + 1` phần tử nên trường hợp đúng bội số `IOV_MAX` có thêm phần tử iovec rỗng; kết quả DMA cần kiểm bằng lab. `buffer_instrumentation.h` định nghĩa raw marker dùng bởi pool hugepage trong `KernelDevice`; helper kiểm marker chủ yếu có call site test.

**Điều kiện:** daemon append bufferlist nhiều lần, Crimson SeaStore ghi nhiều phân đoạn, hoặc KernelDevice dùng hugepage pool. Trong mixed-version, mỗi OSD tự quản lý buffer/IO theo binary, còn payload application cần giữ nguyên; sau full upgrade cần xem RSS, phân mảnh, độ dài iovec và kết quả ghi. **Evidence confidence:** high cho nhánh cấp phát/call site, medium cho hiệu năng và tác động iovec biên chưa chạy.

**Kiểm chứng:** lab append nhiều kích thước và đo allocation/RSS; kiểm `c_str()` với buffer rỗng cuối; ghi SeaStore với số segment `IOV_MAX-1`, `IOV_MAX`, `IOV_MAX+1`, so checksum, offset, số DMA write/error và thiết bị clone. Thử pool hugepage khi cấu hình sử dụng.

**Activation và rollback:** tăng trưởng buffer và gom iovec tự động khi caller target chạy; tác động capacity/performance hoặc correctness của SeaStore DMA phải đo ở biên segment. Bộ đệm RAM không được chuyển sang binary cũ khi restart, nhưng write đã gửi device tồn tại độc lập với lifetime buffer. Trước failback cần drain I/O và đối soát checksum/replay trên clone; nếu boundary iovec tạo short/failed write, giữ offset/length/log thay vì coi restart là đã phục hồi dữ liệu. Chưa có runtime để kết luận vector rỗng cuối chắc chắn gây lỗi.

### MSG-029 — Parser entity name và địa chỉ đổi API

**CSV:** `src/msg/msg_types.cc/.h`. Base `entity_name_t::parse` nhận `std::string` hoặc C string rồi dùng `strtoll`; target nhận `std::string_view` và kiểm đã tiêu thụ toàn bộ view. Với view không kết thúc null hoặc là lát cắt của chuỗi lớn, `strtoll` vẫn đọc theo C string nên cần kiểm input biên; các caller production đã xem thường truyền `std::string`. `entity_addr_t::parse` target đưa `default_type` vào overload nhận view; MON gọi nó với `TYPE_ANY` khi nhận bootstrap hint. Đây là đường nhận dạng peer/địa chỉ, không đổi wire encoding từ các hunk này.

**Điều kiện:** automation cấp entity name/address biên hoặc MON nhận bootstrap hint không có tiền tố v1/v2. Trong mixed-version, parser chạy tại daemon xử lý lệnh, nên cùng chuỗi có thể được diễn giải theo type mặc định khác; sau full upgrade cần chuẩn hóa address vector đã lưu/công bố. **Evidence confidence:** high cho API/call site, medium cho input không null-terminated và behavior thực tế chưa chạy.

**Kiểm chứng:** lab thử entity name chuẩn, có suffix, view lát cắt, chuỗi thiếu chữ số; thử địa chỉ có/không tiền tố và bootstrap hint ở hai tag, ghi type/port trả về, log lỗi và monmap trước/sau.

**Activation, tác động và rollback:** parser mới tự động áp lúc parse request/bootstrap input; compatibility/availability chỉ đổi với input chạm nhánh khác. Giữ chuỗi đầu vào nguyên bản và giá trị type/port trước khi nhận config; sau địa chỉ được persist/công bố, rollback binary không sửa monmap hoặc bootstrap hints đã lưu. Lỗi view không null-terminated cần probe bộ nhớ có biên rõ, chưa có căn cứ gán crash cho input production thông thường. Failback wrapper/extension phải cùng API `string_view` của binary đã build.

### MSG-030 — Đọc tên tiến trình qua pthread ở nền tảng hỗ trợ

**CSV:** `src/common/code_environment.cc`. Base `get_process_name` dùng Linux `prctl(PR_GET_NAME)` khi có header/constant; target chọn `pthread_getname_np(pthread_self())` khi build có `HAVE_PTHREAD_GETNAME_NP` và không phải Windows. `global_init` dùng kết quả cho `g_process_name`; đây là metadata chẩn đoán, không đổi identity CephX hoặc daemon ID.

**Điều kiện:** nền tảng build chọn nhánh pthread và tooling đọc tên tiến trình từ log/crash/metric. Trong mixed-version, tên được ghi bởi từng daemon theo binary; sau full upgrade cần xem parser vận hành có nhận giá trị target. **Evidence confidence:** high cho nhánh/call site, medium cho khác biệt chuỗi trên host triển khai.

**Kiểm chứng:** trên host thử có cùng process/thread name, chạy binary hai tag, ghi `g_process_name`, crash record và log; kiểm đặc biệt tên dài hoặc buffer gần giới hạn 16 byte.

**Activation, tác động và rollback:** hàm tự động chạy khi global init lấy tên theo platform probe, ảnh hưởng observability thay vì CephX identity. Trước rollout collector giữ mẫu process-name và label mapping của hai build; rollback parser có thể khôi phục ingest nhưng không đổi label trong log/crash lịch sử. Hạ package không thay tên trong process đang chạy, và restart để đổi tên có chi phí availability riêng. Chưa biết platform dự án trả chuỗi khác hay tương đương.

### MSG-031 — Chọn hàm xóa dữ liệu nhạy cảm theo kết quả build

**CSV:** `src/common/compat.cc`. Base `ceph_memzero_s` chọn `memset_s` khi có `__STDC_LIB_EXT1__`, target chọn theo `HAVE_MEMSET_S` và khai báo `__STDC_WANT_LIB_EXT1__` trước `<string.h>`; nhánh Windows còn `SecureZeroMemory`, Unix fallback còn `explicit_bzero`. Các caller target trong RBD LUKS/OpenSSL và `rbd`/`rbd-nbd` dùng hàm này để xóa key/passphrase. Mỗi nhánh đều có chủ đích xóa bộ nhớ; chưa có bằng chứng nhánh target xóa yếu hơn hay mạnh hơn trên platform cụ thể.

**Điều kiện:** build trên platform có/không có `memset_s`, đặc biệt dùng RBD encryption. Trong mixed-version, client thực hiện xóa key theo binary và config build của nó; sau full upgrade cần xác nhận CMake probe khớp thư viện C của package. **Evidence confidence:** high cho tiền xử lý và caller, medium cho codegen/hiệu quả zeroization chưa thử.

**Kiểm chứng:** ghi `HAVE_MEMSET_S` và platform của gói Quincy; test `ceph_memzero_s` trên buffer chứa mẫu key với từng nhánh, kiểm return code và bản build tối ưu hóa, đồng thời chạy luồng mở/đóng RBD encrypted trên lab.

**Tác động và rollback:** nhánh zeroization được chọn ở build rồi tự động dùng lúc caller xóa key; đây là thuộc tính security của artifact, chưa phải claim CVE hay mức bảo vệ tăng. Ranh giới failback là trước phát hành package có probe/dependency chưa kiểm. Hạ thư viện không hồi tố xóa bản sao secret còn trong process/core đã tạo trước đó; phải kiểm lifecycle key và policy core riêng. Nếu probe sai khiến build/link hỏng thì sửa builder, không thay thuật toán dữ liệu mã hóa để né lỗi.

### MSG-032 — Đồng hồ coarse của bản Windows phụ thuộc platform

**CSV:** `src/common/ceph_time.h`. Base định nghĩa `CLOCK_REALTIME_COARSE`/`CLOCK_MONOTONIC_COARSE` thành clock thường vô điều kiện dưới `_WIN32`; target chỉ định nghĩa fallback khi platform header chưa có hai constant. Vì vậy MinGW mới có coarse clock riêng có thể giữ độ phân giải/hành vi của nó; Linux không đi qua hunk này.

**Điều kiện:** build client/utility Ceph trên Windows với MinGW cung cấp coarse clock constants. Trong mixed-version, client Windows hai binary có thể lấy mốc coarse khác nhau; sau full upgrade cần thử timeout/diagnostic time của client trên toolchain ấy. **Evidence confidence:** high cho guard, medium cho precision runtime và mức áp dụng trong dự án.

**Kiểm chứng:** build hai tag với MinGW cũ/mới trên lab, in macro effective, so `clock_gettime` coarse/normal, thời gian hẹn timer của client và lỗi compile.

**Activation, tác động và rollback:** chọn clock tự động ở compile theo MinGW/header; tác động observability và timeout conditional trên client Windows, không đổi timer Linux từ hunk này. Lưu toolchain và clock constants hiệu dụng để phục hồi artifact pair; đổi macro trong config runtime không đổi binary đã build. Restart client xóa timer RAM đang chờ, vì vậy failback cần ghi trạng thái request và retry theo contract ứng dụng. Chưa có số đo resolution nên không xem timestamp thô hơn là bằng chứng storage chậm hơn.

### MSG-033 — Bỏ allocator fallback tcmalloc cũ của RBD

**CSV:** `src/common/allocator.h`. Base định nghĩa `ceph::allocator` có nhánh `LIBTCMALLOC_MISSING_ALIGNED_ALLOC` gọi `memalign` cho allocation cần alignment cao; `librbd/ImageCtx.h` và `librbd/crypto/CryptoContextPool.h` dùng nó trong Boost lockfree queue. Target xóa header và hai queue chuyển sang allocator mặc định của Boost. Đây là thay đổi khả năng build/cấp phát có điều kiện với tcmalloc cũ; không suy tự động latency RBD thay đổi.

**Điều kiện:** build client RBD với phiên bản tcmalloc thiếu `aligned_alloc` hoặc workload gây cấp phát alignment cao trong queue. Trong mixed-version, mỗi client binary quản lý allocation cục bộ; sau full upgrade phải xác nhận cả `librbd` và crypto queue chạy ổn với allocator mặc định. **Evidence confidence:** high cho source/call site, medium cho library/hiệu năng thực tế chưa đo.

**Kiểm chứng:** inventory gperftools/tcmalloc của builder/client, build target với cấu hình cũ và mới, chạy RBD asynchronous completion cùng LUKS context pool ở sanitizer/lab; ghi lỗi allocation/alignment, RSS và latency.

**Tác động và rollback:** allocator mặc định hoạt động tự động khi queue target cấp phát; compatibility/delivery phụ thuộc tcmalloc thực sự link hoặc preload trên host. Trước rollout giữ cặp librbd/dependency cùng builder manifest; thay allocator shared library riêng có thể không đưa template queue về code Pacific. Quiesce completion/crypto context trước thay process; allocation lỗi đã làm I/O không hoàn tất cần đối soát return/completion. Không có chuyển format riêng trong hunk, nhưng dữ liệu đã ghi không được undo khi phục hồi allocator.

### MSG-034 — Worker `io_context_pool` bỏ `noexcept`

**CSV:** `src/common/async/context_pool.h`. Base lambda worker chạy `ioctx.run()` được khai báo `noexcept` để exception chưa xử lý gọi terminate ngay tại điểm throw theo chú thích source; target bỏ qualifier. `io_context_pool` được dùng trong global init, MGR standby và OSD. Hunk không đổi scheduling bình thường, nhưng đường chẩn đoán exception của worker có thể khác tùy libstdc++ thread wrapper.

**Điều kiện:** callback trong `ioctx.run()` ném exception không được bắt. Trong mixed-version, chỉ daemon gặp tình huống ấy thấy đường termination khác; sau full upgrade cần đọc log/core tương ứng nếu rollout vấp lỗi callback. **Evidence confidence:** high cho khai báo/call site, medium cho stack unwinding thực tế chưa đo.

**Kiểm chứng:** lab cô lập đăng ký callback ném exception vào pool của hai tag, so terminate handler, backtrace/core và khả năng ghi crash; không gây exception trên cluster production.

**Activation, tác động và rollback:** thay đổi tự động trong worker target khi callback ném exception chưa bắt, tác động availability và độ đầy đủ backtrace. Bỏ `noexcept` không tạo error recovery cho ứng dụng: exception thoát thread vẫn cần xử lý termination theo runtime. Failback chỉ thay lần chạy sau; trước restart giữ core cùng exception/log và xác minh op callback đã commit hay chưa. Chưa có unwind test trên libstdc++ triển khai nên không khẳng định stack luôn khác.

### MSG-035 — API gom argv đổi ở đường khởi động

**CSV:** `src/common/ceph_argparse.cc/.h`. Base `argv_to_vec(argc, argv, args)` nối `argv[1..]` vào vector có sẵn; target trả một vector mới và assert `argc > 0`. Entry point MON, OSD, MGR, MDS, RGW và client trong cây đã chuyển sang `auto args = argv_to_vec(argc, argv)`. Với process bình thường có `argc >= 1`, nội dung argv vẫn cùng dải; code ngoài cây gọi chữ ký cũ cần biên dịch lại. Trường hợp khởi chạy với argv rỗng sẽ gặp assert ở target trước phần init.

**Điều kiện:** tự build plugin/utility dựa trên helper C++ này, hoặc môi trường khởi chạy daemon có `argc == 0`. Trong mixed-version, daemon base/target dùng API nội bộ riêng; sau full upgrade cần bảo đảm wrapper tạo argv hợp lệ. **Evidence confidence:** high cho chữ ký/entry point/assert, medium cho trường hợp argv rỗng trong triển khai.

**Kiểm chứng:** build các wrapper/utility nội bộ với header Quincy; lab chạy entry point với argv thông thường và launcher mô phỏng argv rỗng, ghi exit code/core/log. Không áp dụng thử argv rỗng trên daemon production.

**Activation, tác động và rollback:** helper mới tự động chạy ở startup, còn consumer ngoài cây cần rebuild explicit; tác động compatibility/delivery là wrapper không build hoặc assert trước init với argv rỗng. Ranh giới phục hồi là bộ launcher/executable cùng headers đúng phiên bản và manifest argv đã kiểm. Sửa launcher để cung cấp argv hợp lệ có thể xử lý trigger mà không thay format cluster; nếu daemon đã chạy rồi mới rollback package, vẫn cần xét các checkpoint state do daemon đó tạo.

### MSG-036 — Command descriptor và `CephBool` có gate Quincy

**CSV:** `src/common/cmdparse.cc/.h`. Base xuất `req` dưới dạng string và không có metadata `positional`; target nhận dấu `--` trong chữ ký, đánh dấu các tham số sau đó `positional=false`, nhưng chỉ xuất thuộc tính này cho peer có `SERVER_QUINCY`. Với peer Quincy, `req` được xuất thành JSON bool; với peer cũ vẫn là string. `validate_cmd` target xử lý `CephBool` riêng và `cmd_getval_compat_cephbool` nhận kiểu bool hoặc chuỗi `--foo-bar` của client cũ; các handler MON/MGR dùng helper tương thích này. `cmd_getval`/`cmd_putval` cũng chuyển key sang `string_view` và thêm API default/optional.

**Điều kiện:** CLI, dashboard hoặc automation lấy command descriptions và gửi các flag `CephBool`, nhất là khi client/daemon khác version. Trong mixed-version, định dạng JSON mô tả phụ thuộc feature của peer; sau full upgrade parser mới nhận bool và positional metadata. **Evidence confidence:** high cho branch feature và call site, medium cho từng client/tool chưa chạy.

**Kiểm chứng:** lab lấy command descriptions bằng client Pacific/Quincy từ MON/MGR target; so kiểu `req`, sự có mặt `positional`, thử flag JSON bool và chuỗi legacy trên lệnh an toàn, ghi validation error và kết quả. Rà parser automation nào đang giả định mọi `req` là string.

**Activation, tác động và rollback:** JSON descriptor tự chọn theo feature peer, không cần bật riêng; compatibility của parser/automation đổi ngay khi client quảng bá Quincy. Trước nâng client giữ response fixture và schema parser cũ/mới; nếu rollback consumer phải reset cache command-description để không tiếp tục dùng metadata của peer khác version. Request đã vượt validate và commit ở MON/MGR không được undo khi phục hồi descriptor hoặc CLI. Gate release persist của server tách biệt với nhánh xuất JSON này.

**Thời điểm hiệu lực:** nhánh descriptor được kích hoạt tự động cho mỗi response dựa trên feature connection; không cần restart để bật metadata cho request mới. Cache ở consumer quyết định lúc automation thực sự thấy schema mới, nên bài kiểm phải bao gồm cả cache cũ và lần fetch mới.

### MSG-037 — ISO timestamp không dấu phân cách cho yêu cầu RGW ký v4

**CSV:** `src/common/iso_8601.cc/.h`. Base `to_iso_8601` dùng dấu `-` ở ngày và `:` ở giờ; target nhận separator tùy chọn, default vẫn là hai dấu cũ, và thêm `to_iso_8601_no_separators`. `src/rgw/rgw_rest_s3.cc` target dùng helper mới tạo `x-amz-date` cho outbound request ký v4. Đây là đường ký yêu cầu RGW, không phải bằng chứng mọi timestamp API đổi format.

**Điều kiện:** RGW tạo outbound S3 v4 request qua đường gọi này. Trong mixed-version, request phát từ từng RGW theo binary của nó; sau full upgrade cần xác nhận header date, canonical request và server đích chấp nhận chữ ký. **Evidence confidence:** high cho formatter/call site, medium cho tương tác với endpoint ngoài chưa thử.

**Kiểm chứng:** lab gửi cùng loại request từ hai tag tới endpoint thử, ghi `x-amz-date`, canonical string, signature, response và clock skew; giữ secret/test bucket riêng.

**Activation, tác động và rollback:** helper không separator tự động được outbound S3 v4 caller target chọn, ảnh hưởng compatibility/availability khi server đích xác minh chữ ký. Trước đổi RGW giữ loại request, endpoint và fixture canonical input không chứa secret thật. Hạ formatter không làm request đã bị từ chối được chấp nhận lại; retry phải tạo timestamp/signature mới và đối soát object state nếu response trước đó không rõ. Không replay nguyên signed request cũ để kiểm failback vì expiry/clock skew có thể làm sai kết luận.

### MSG-038 — Numeric parser bỏ fallback và overload C string

**CSV:** `src/common/strtol.cc/.h`. Base `ceph::parse`/`consume` dùng `std::from_chars` nếu có `<charconv>`, fallback sang `strtoimax`/`strtoumax` nếu không; target yêu cầu `<charconv>` và chỉ giữ nhánh `from_chars`. Các hàm strict số nguyên/double/IEC bỏ overload nhận `const char*` và dùng `string_view`/template; các caller MON, RGW và config target vẫn gọi parser. Với input thường, implicit conversion từ C string có thể giữ kết quả, nhưng symbol/API C++ cũ và toolchain thiếu charconv không còn đường fallback.

**Điều kiện:** tự build Quincy bằng standard library cũ, hoặc extension C++ liên kết vào overload strict cũ; input numeric biên cũng nên kiểm trong command/config parser. Trong mixed-version, từng daemon parse input tại phía nhận, còn binary target phải build được trước rollout. **Evidence confidence:** high cho header/overload và call site, medium cho trường hợp build/ABI cụ thể.

**Kiểm chứng:** build bằng toolchain dự định, kiểm `<charconv>` và link extension nội bộ; lab đưa số hợp lệ, overflow, dấu âm, whitespace, prefix IEC/SI vào lệnh/config trên hai tag, so giá trị và lỗi.

**Rollback và tác động:** compile/API path ảnh hưởng delivery/compatibility; parse số tự động chạy tại daemon/client nhận input. Giữ toolchain, extension binary và config gốc trước rollout; source mới không có fallback nên hạ standard library đơn lẻ không phục hồi build. Với giá trị đã được parse rồi persist vào config/map, rollback parser chỉ tác động lần nhập tiếp theo, không sửa giá trị đã lưu. Full Quincy vẫn cần thử corpus numeric biên để tránh nhầm thay đổi parser với lỗi vận hành.

### MSG-039 — Object identity của Crimson SeaStore dùng reversed hash

**CSV:** `src/common/hobject.cc/.h`, `hobject_fmt.h`. Base constructor `ghobject_t` từ `(shard,pool,hash,nspace,oid,snap,gen)` truyền `hash` trực tiếp vào `hobject_t`; target coi tham số là `reversed_hash`, gọi constructor mới và `set_bitwise_key_u32`, đảo bit để đặt hash gốc và cập nhật cache. `crimson/os/seastore/.../key_layout.h` giải mã trường crush từ key rồi gọi constructor này khi dựng `ghobject_t`. `hobject.cc` đổi escape string sang `to_chars`; formatter fmt mới được kéo vào OSD type formatting, nên object ID trong log cần đối chiếu. Đây là đường nhận dạng/index object ở SeaStore, không suy dữ liệu on-disk đã migrate từ hunk common.

**Điều kiện:** dùng Crimson SeaStore và đọc key đã lưu/replay, hoặc automation parse object ID từ log. Trong mixed-version, mỗi OSD diễn giải object key bằng code binary riêng; sau full upgrade cần thử trên bản sao store, nhất là restart/rollback. **Evidence confidence:** high cho reverse-bit setter và call site decode, medium cho nội dung store thực tế chưa so.

**Kiểm chứng:** lab tạo object có hash không đối xứng bit, dump raw SeaStore key và `ghobject_t` trước/sau, so lookup/read/restart, fsck và log string; kiểm bản sao store với binary Pacific sau khi target đã ghi.

**Tác động và activation:** reverse-hash constructor tự động chạy khi SeaStore decode key, ảnh hưởng correctness của lookup/order object conditional vào backend này. Điểm rollback là clone store trước target mount/ghi và bộ key/hash fixture đã kiểm; việc constructor mới đảo bit không chứng minh binary cũ diễn giải đúng key mà các lớp khác của target đã ghi. Nếu lookup lệch, dừng write trên bản thử và so raw key trước khi xem xét repair. Các log object ID đã xuất cũng cần parser nhận đúng kiểu, không dùng khác biệt text để kết luận object biến mất.

### MSG-040 — Lockdep đổi giới hạn và chỉ có ở build debug mutex

**CSV:** `src/common/lockdep.cc/.h`. Base có 4.096 lock ID và ma trận cố định; target tăng tối đa 131.072 ID, dùng `bitset`/vector map cấp dần và tạo `ClibBackTrace` cho cycle. Header target đổi các call lockdep thành no-op khi không có `CEPH_DEBUG_MUTEX`, còn CMake target chỉ biên dịch `lockdep.cc` khi `WITH_CEPH_DEBUG_MUTEX`. `ceph_context.cc` cũng chỉ đăng ký observer lockdep trong build tương ứng. Đây là khác biệt khả năng chẩn đoán và footprint của build debug, không đổi lock ordering của workload tự thân.

**Điều kiện:** chạy build có debug mutex/lockdep hoặc dùng lockdep như gate khi canary. Trong mixed-version, số ID/trace có thể khác theo binary/build; sau full upgrade cần chắc build canary thật sự bật instrumentation. **Evidence confidence:** high cho macro/CMake/ma trận, medium cho RSS/hiệu quả phát hiện trên workload thực tế.

**Kiểm chứng:** build hai biến thể bật/tắt debug mutex, xác nhận symbol/counter lockdep, tạo thứ tự lock đảo ở lab và nhiều lock ID, đo log/backtrace, RSS và thời gian khởi tạo.

**Activation, tác động và rollback:** instrumentation được chọn lúc build và bật theo lockdep config phù hợp, tác động observability/capacity của canary. Tắt runtime flag không bổ sung code lockdep vào package build no-op; rollback binary cần giữ build flags và symbols để so cycle thật. Dependency graph chỉ trong RAM nên restart làm mất evidence chuỗi lock đã thu, không sửa deadlock nguyên nhân. Giữ dump/backtrace trước restart và chưa kết luận workload hết deadlock chỉ vì bản release không báo lockdep.

### MSG-041 — Bỏ qua DPDK lcore worker khi gán CPU affinity

**CSV:** `src/common/numa.cc`. Base `set_cpu_affinity_all_threads` gọi `sched_setaffinity` cho mọi TID tìm được; target, khi `HAVE_DPDK`, đọc `/proc/self/task/<tid>/comm` và bỏ qua tên bắt đầu `lcore-worker`. DPDK reactor do nó tự chọn NUMA/CPU, nên affinity tổng của daemon không còn ép worker này. Helper có nhánh `safe_read` và tên 16 byte; kết quả với tên/đọc lỗi biên cần test, không suy mọi DPDK worker đều được bỏ qua.

**Điều kiện:** build/use DPDK và daemon bật đường gán affinity toàn thread. Trong mixed-version, DPDK worker base/target có thể nằm ở CPU khác dù cấu hình chung giống nhau; sau full upgrade cần so mapping thực tế với NUMA device/network. **Evidence confidence:** high cho filter/call site, medium cho latency và thread-name thực tế chưa đo.

**Kiểm chứng:** lab bật DPDK, ghi TID, `/proc/.../comm`, CPU affinity trước/sau hàm và vị trí NUMA của NIC, thử tên dài/đọc lỗi; đo packet latency và throughput trên cùng pinning.


**Activation, tác động và rollback:** filter tự động chạy khi daemon target gọi gán affinity trong build DPDK; compatibility của pinning và performance phụ thuộc tên lcore mà thư viện thực sự đặt. Commit `6411cbe2dd9` liên kết cơ chế với MSG-051. Ranh giới phục hồi là cấu hình coremask/NUMA và cpuset của process đang chạy: hạ binary chỉ đổi lần gọi sau, không tự đưa TID hiện hữu về mask cũ. Khi throughput hoặc drop lệch, giữ TID/mask trước restart rồi khôi phục pinning đã thử; không dùng thay tên thread đơn lẻ làm bằng chứng affinity đúng. `get_task_comm` còn cần probe với read trả 0 hoặc buffer không có newline vì code dùng `name[n-1]`/`name[n]`; chưa chạy tình huống biên này.

### MSG-042 — Bỏ virtual query mode trong AuthServer

**CSV:** `src/auth/AuthServer.h`. Base có virtual `get_supported_con_modes` chuyển tiếp vào auth registry; target bỏ nó, còn `get_supported_methods` và `pick_con_mode`. Hunk không chứng minh wire negotiation đổi, nhưng subclass/caller C++ ngoài cây dùng API cũ phải sửa và build lại. **Điều kiện:** có auth extension nội bộ; mixed-version là khác biệt ABI trong từng process, full upgrade phải đồng bộ extension. **Confidence:** high cho API, medium cho mức sử dụng ngoài cây. **Kiểm chứng:** tìm subclass/caller nội bộ, build với header Quincy, thử auth msgr2 hai version và so mode được chọn.

**Activation, tác động và rollback:** loại virtual method có hiệu lực khi build/link auth subclass mới, nên delivery/compatibility conditional trên extension C++ ngoài cây. Commit `a578cedea38` gọi API này unused; chưa có inventory extension của môi trường để khẳng định nó đang áp dụng. Trước thay package giữ auth extension, headers và libraries cùng một bộ; mixed binary trong một process không có feature negotiation cho vtable. Rollback phải phục hồi bộ artifact tương thích và restart process sau khi drain request. API cục bộ này không xoay credential, còn auth-store/release checkpoint ở MON vẫn quyết định khả năng quay lại daemon cũ.

### MSG-043 — Throttle chọn perf counter Crimson theo build

**CSV:** `src/common/Throttle.h`. Target include header perf counter Crimson khi `WITH_SEASTAR && !WITH_ALIEN`, bỏ trường `cct` không dùng của `BackoffThrottle`; không đổi công thức throttle trong hunk. **Điều kiện:** build Crimson/Seastar hoặc extension C++ phụ thuộc layout class; mixed-version có counters theo binary, full upgrade cần rà metric. **Confidence:** high cho compile gate, medium cho runtime. **Kiểm chứng:** build Seastar/Alien/classic, chạy workload throttle và so perf counters/ABI extension.

**Activation, tác động và rollback:** include branch tự động chọn ở compile; tác động delivery/observability là Crimson native phải dùng collection của shard, Alien/classic dùng collection CephContext. Việc bỏ member `cct` (`d34aae8c862`) cũng đổi layout C++ của consumer tự build, dù công thức delay giữ nguyên. Giữ build flags cùng library/header để failback, không thay shared library dưới process đang sử dụng layout khác. Counter đã xuất vào collector là evidence lịch sử và không đổi schema trở lại khi hạ package; so counter và throttle occupancy theo từng build trong mixed và full lab. Chưa có runtime cho lifetime/logger của cấu hình dự án.

### MSG-044 — `dummy_atomic` sửa assignment và ràng buộc toán tử

**CSV:** `src/common/ceph_atomic.h`. Base `operator=` khai báo trả `T` nhưng thiếu return; target trả `*this`. Các phép toán số nguyên dùng template SFINAE, loại enum. Đây là đổi source API/biểu thức gán có dùng giá trị trả về, không chứng minh memory ordering đổi. **Điều kiện:** consumer dùng `dummy_atomic`; mixed-version chỉ khác trong từng binary. **Confidence:** high cho source, medium cho áp dụng. **Kiểm chứng:** build unit với integral/enum và gán lồng, chạy consumer dưới sanitizer.

**Activation, tác động và rollback:** toán tử assignment/SFINAE tự động áp ở build consumer chọn `dummy_atomic`; correctness/delivery liên quan expression dùng return và kiểu enum/integral. Target `operator=(T)` vẫn trả `T`, với `return *this` chuyển qua conversion operator; không trả reference tới atomic. Commit `2badc8987ed` giải thích loại arithmetic cho enum. Trước phát hành giữ consumer binary/toolchain; rollback cần rebuild hoặc phục hồi artifact đồng bộ, không đổi memory-order config vì dummy implementation không có atomic ordering thật. Giá trị assignment đã dẫn tới I/O hay thay state của caller không được undo khi thay header. Chưa xác định mọi instantiation ngoài cây, nên probe phải gồm chained assignment và enum không hỗ trợ `++`.

### MSG-045 — LRU không còn dọn entry trong destructor

**CSV:** `src/common/intrusive_lru.h`. Base destructor gọi `set_target_size(0)` để evict entry không tham chiếu; target bỏ destructor. Crimson object-context manager có đường stop chủ động set size 0; RGW bucket sync cache cũng dùng LRU nhưng cần kiểm lifetime riêng. Không suy memory leak trong steady state. **Điều kiện:** hủy cache khi còn entry; mixed-version là hành vi nội bộ từng daemon. **Confidence:** high cho code, medium cho hậu quả. **Kiểm chứng:** destroy cache còn entry dưới ASan/LSan, so destructor/assertion trên RGW và Crimson.

**Activation, tác động và rollback:** thay đổi tự động ở lúc owner hủy LRU, tác động correctness/availability conditional trên thứ tự reference và teardown. `src/crimson/osd/object_context.cc` target `stop()` gọi `obc_lru.set_target_size(0UL)`; `src/test/common/test_intrusive_lru.cc` có case `lookup_lru_size` dọn chủ động nhưng chưa chứng minh hủy owner khi còn reference. Hai source/test đã đọc, chưa chạy. Trước rollback phải drain object-context và sync work theo owner; restart không thay thế việc xác định entry nào đã được commit. Giữ sanitizer trace nếu leak/assert/UAF, và dừng failback trên store clone có replay sai; không suy cache RAM đổi nghĩa là dữ liệu persistent có thể quay về Pacific.

### MSG-046 — Thêm log subsystem riêng

**CSV:** `src/common/subsys.h`. Target thêm `rgw_datacache`, nhiều `seastore_*`, `alienstore`, `mclock`, `ceph_exporter` với mặc định riêng; `mClockScheduler` dùng subsystem mới. **Điều kiện:** cấu hình `debug_*` hoặc parser log theo tên subsystem; mixed-version daemon Pacific chưa biết tên mới. **Confidence:** high cho danh mục/call site, medium cho mức bao phủ. **Kiểm chứng:** trên lab bật các debug selector mới, so log và pipeline alert.

**Activation, tác động và rollback:** subsystem mới được đăng ký tự động theo binary, nhưng tăng `debug_mclock`, `debug_seastore_*` hoặc selector khác là thao tác cấu hình explicit. Tác động observability/capacity là collector có thể mất dòng do không nhận tên mới hoặc log volume tăng khi operator dùng selector; đây không phải evidence scheduler/storage tự nhanh hơn. Commit `3c210e17dab` thêm mclock, `632916721b9` tách SeaStore và `685bb97332c` thêm exporter. Sau full upgrade phải giữ mapping subsystem–severity cùng effective debug config; trong mixed so từng binary. Rollback selector/parser có thể phục hồi ingest cho log mới, không tái tạo dòng đã bị lọc. Chưa có volume/retention và parser As-Is để xác định độ áp dụng; trước restart giữ log canary cùng tên subsystem.

### MSG-047 — Tracing OSD/RGW chuyển sang OpenTelemetry Jaeger

**CSV:** `src/common/tracer.cc/.h`. Base dùng OpenTracing Jaeger và YAML config/fallback; target tạo OpenTelemetry Jaeger exporter với `SimpleSpanProcessor`, resource `service.name`, chỉ phát span khi `jaeger_tracing_enable` và build `HAVE_JAEGER`. Header có stub khi không build Jaeger; target thêm encode/decode span context version 1. OSD/RGW có init và span call sites. **Điều kiện:** tracing được bật; mặc định config là false. Mixed-version có thể tạo trace theo hai SDK/schema; full upgrade cần kiểm collector và parent-child. **Confidence:** high cho source/gate, medium cho ingest thực tế. **Kiểm chứng:** build bật/tắt Jaeger, chạy IO lab khi flag bật, so span, parent ID và ingest; thử rolling mix rồi tắt flag đo overhead.

**Tác động và rollback:** compatibility/observability nằm ở exporter SDK, resource và propagation; `SimpleSpanProcessor` khiến chi phí export cần đo trên request path thay vì suy từ collector có span. Ranh giới phục hồi là trước bật `jaeger_tracing_enable` trên build có Jaeger: giữ effective flag, exporter dependencies và collector fixture. Tắt flag phục hồi đường no-op cho span mới, nhưng không xóa span đã gửi hoặc sửa parent-child của trace đang bay; hạ package cũng không đổi record collector cũ. Trước failback cần drain request, kiểm retry không tạo duplicate application operation và xác minh propagation giữa peer khác version. Chưa có ingest/overhead test, nên thiếu trace không đủ để đánh giá I/O thất bại.

### MSG-048 — Đọc cgroup memory limit chỉ trên Linux

**CSV:** `src/common/util.cc`. Base mở đường cgroup Linux trên mọi Unix không phải Windows; target chỉ làm thế trên Linux. Nhánh ngoài Linux trả status 0 nhưng không gán `*limit`, trong khi `collect_sys_info` khai báo `uint64_t cgroup_limit` chưa khởi tạo rồi đọc nó khi status bằng 0. Caller này nằm dưới `#elif !defined(_WIN32)` sau nhánh `__APPLE__`, nên đường đọc giá trị không khởi tạo mới áp trên platform ngoài Linux, Apple và Windows, chẳng hạn FreeBSD; không được diễn giải status 0 là memory limit bằng 0. Windows/Apple không đi qua caller cgroup đã đọc. Commit `7c0ed157d75`; nhánh Linux không đổi từ hunk. **Điều kiện:** build/chạy trên Unix ngoài Linux/Apple có đường `collect_sys_info` này; mixed-version sysinfo có thể khác, sau full upgrade vẫn cần kiểm đường platform đó. **Confidence:** high cho guard/caller và giá trị chưa khởi tạo, medium cho biểu hiện thực tế. **Kiểm chứng:** probe helper với sentinel output trên Linux và Unix mục tiêu; chạy caller dưới công cụ phát hiện uninitialized read, ghi `mem_cgroup_limit` và dashboard. Chưa thực thi probe.

**Activation, tác động và rollback:** nhánh platform tự động chạy khi thu sysinfo; correctness/observability conditional vì `mem_cgroup_limit` có thể thiếu hoặc thành số không xác định, không phải evidence host có memory headroom như vậy. Ranh giới phục hồi là trước dùng field ấy cho rollout gate: giữ platform/build và kết quả OS-native làm đối chứng. Failback collector có thể bỏ field không đáng tin, còn hạ daemon chỉ đổi lần thu tiếp theo, không sửa record đã lưu. Dừng quyết định capacity dựa riêng trên field cho tới khi output initialized được xác minh; chưa có As-Is Unix ngoài Linux để kết luận dự án gặp trigger.

### MSG-049 — LogClock dùng probe `HAVE_SUSECONDS_T`

**CSV:** `src/log/LogClock.h`. Base kiểm `#ifndef suseconds_t` dù đây thường là typedef; target dùng probe build `HAVE_SUSECONDS_T`. Có thể ảnh hưởng compile/kiểu log clock trên platform định nghĩa typedef khác `long`; không chứng minh format log Linux đổi. **Điều kiện:** toolchain có typedef/probe liên quan; mixed-version khác ở gói build. **Confidence:** high cho guard, medium cho ABI platform. **Kiểm chứng:** build probe bật/tắt trên platform mục tiêu, so kiểu và timestamp test.


**Activation, tác động và rollback:** type probe tự chọn khi compile logger; tác động delivery/compatibility phụ thuộc việc generated `config.h` khớp libc/toolchain. Commit `731ec948315` đưa `CHECK_TYPE_SIZE` vào lựa chọn; không thể đổi typedef của binary đang chạy bằng runtime option. Giữ CMake cache, generated header và logger consumer cùng bộ artifact để failback; không mix object file được build với typedef khác. Trong mixed và sau full upgrade, dùng epoch đã giải mã để kiểm timestamp thay vì giả định typedef luôn là `long`. Log đã phát ra không được viết lại khi rollback. Chưa có ABI/probe ở platform triển khai, nên không quy lỗi timestamp Linux cho hunk này.

### MSG-050 — POWER8 CRC32C đổi đường assembly và Barrett reduction

**CSV:** `src/common/crc32c_ppc_asm.S`, `crc32c_ppc_fast_zero_asm.S`, `ppc-asm.h`, `ppc-opcode.h`. `src/common/CMakeLists.txt` chỉ thêm các assembly này khi `HAVE_POWER8 && HAVE_PPC64LE`. Target cho Clang dùng header assembler nội bộ, mở tùy chọn tên symbol/constants, và trong fast-zero đổi hai hằng Barrett từ dạng CRC32C `0x1edc6f41` sang `0x04c11db7`, thêm reducer reflected. `ceph_crc32c_ppc()` gọi `append_zeros()` khi `data == NULL`, còn dữ liệu thường đi qua `__crc32_vpmsum`; do đó có nguy cơ CRC khác trên đường zero-fill, nhưng cần chạy mới xác nhận. Đây là đường checksum dữ liệu, không chỉ là chỉnh cú pháp assembler.

**Điều kiện:** gói POWER8 PPC64LE dùng CRC32C, đặc biệt tính checksum của vùng zero/null; Clang ảnh hưởng build. Mixed-version checksum khác nếu hai binary xử lý cùng payload theo đường khác; full upgrade cần bảo đảm đọc dữ liệu cũ và mới vẫn qua checksum. **Evidence confidence:** high cho constant/call path/build gate, medium cho kết quả CRC vì chưa có lab PPC.

**Kiểm chứng:** trên POWER8, build GCC và Clang, chạy vector CRC32C chuẩn cho buffer thật và `NULL` với length 0, 1, 16, 4 KiB và lệch alignment; so với software reference và bản Pacific. Đặc biệt đối chiếu `ceph_crc32c_zeros`/bufferlist zero data, thử đọc dữ liệu clone đã ghi trước nâng cấp và ghi sau nâng cấp.


**Activation, tác động và rollback:** implementation tự động được chọn khi build/CPU gate POWER8 PPC64LE thỏa; integrity/compatibility phải được chứng minh bằng vector, không bằng tên CRC32C của symbol. Ranh giới phục hồi là trước ghi workload target trên store clone: giữ dữ liệu, checksum và reference CRC đúng polynomial. Nếu vector target lệch, dừng acceptance cho artifact PPC đó; hạ binary không tính lại checksum hay sửa dữ liệu đã ghi dưới kết quả khác. Trường hợp đọc lại dữ liệu cần phân biệt mismatch do reducer với corruption thật trước repair. Các checkpoint BlueStore/MON vẫn là gate failback toàn cluster, và chưa có kết quả PPC để kết luận mismatch chắc xảy ra.

### MSG-051 — Worker messenger giữ tên DPDK để tách affinity

**CSV:** `src/msg/async/Stack.cc/.h`. Base `NetworkStack::add_thread` đặt tên mọi worker theo `msgr-worker-<id>`; target gọi virtual `rename_thread`, mặc định vẫn đặt tên ấy, nhưng `DPDKStack` override thành no-op trong `src/msg/async/dpdk/DPDKStack.h`. DPDK EAL đặt tên lcore riêng; cùng với MSG-041, `set_cpu_affinity_all_threads` target bỏ qua thread có tên `lcore-worker`. Hunk này không đổi event loop của worker thông thường.

**Điều kiện:** build với DPDK và có thao tác gán CPU affinity toàn daemon. Trong mixed-version, DPDK worker có thể bị đổi tên/pin CPU khác theo binary; sau full upgrade cần so mapping của worker, reactor và NIC. **Evidence confidence:** high cho call path/override, medium cho tên thực tế do DPDK đặt và hiệu quả latency chưa chạy.

**Kiểm chứng:** lab DPDK ghi TID, `/proc/self/task/*/comm` và mask affinity trước/sau khi stack khởi động; so Pacific/Quincy ở cùng cấu hình, kiểm `lcore-worker` được bỏ qua đúng, còn worker TCP thường vẫn nhận tên `msgr-worker-*`.


**Activation, tác động và rollback:** tên mặc định/override được áp tự động khi worker target start; tác động performance/compatibility của affinity nối trực tiếp MSG-041. Trước thay package giữ EAL version, lcore mask và danh sách TID–comm–CPU đã kiểm. Rollback worker cần stop/drain network stack rồi khởi động bộ binary/EAL đồng bộ; chỉ đổi comm của thread hiện hữu không phục hồi event loop hoặc affinity. Op đang bay có thể reconnect/resend nên phải so completion và packet drop trước tiếp tục. Chưa đo tên do bản DPDK triển khai tạo; full Quincy vẫn phải chứng minh filter khớp tên thực tế.

### MSG-052 — Fallback khóa block device khi thiếu OFD lock constant

**CSV:** `src/include/compat.h`. Target định nghĩa `F_OFD_SETLK` thành `F_SETLK` khi header hệ thống thiếu hằng OFD. `KernelDevice::_lock()` gọi `fcntl(fd, F_OFD_SETLK, ...)`, sau đó chỉ fallback `flock` khi `EINVAL`. Vì vậy trên build thiếu constant, target dùng POSIX process lock trực tiếp thay vì OFD lock/đường `EINVAL`; đời khóa khi descriptor khác đóng cần kiểm. Trên Linux có `F_OFD_SETLK`, macro này không thay đổi hành vi.

**Điều kiện:** gói target build với libc/header thiếu `F_OFD_SETLK` nhưng dùng `KernelDevice`. Mixed-version là khác biệt khóa thiết bị tại từng OSD; sau full upgrade cần bảo đảm một thiết bị không bị hai process mở cùng lúc trong restart. **Evidence confidence:** high cho fallback/call path, medium cho tổ hợp toolchain/kernel thực tế.

**Kiểm chứng:** ghi macro effective khi build; trên host lab phù hợp, mở cùng block-device clone từ hai process, mô phỏng udev mở/đóng descriptor và restart OSD, so lock owner, `EAGAIN`/`EINVAL`, log retry và khả năng mở trùng.

**Tác động và rollback:** safety/availability của exclusive device open đổi khi build dùng fallback: POSIX lock thuộc process khác vòng đời OFD lock, nên descriptor khác trong cùng process có thể ảnh hưởng khóa. Tự động có hiệu lực ở `KernelDevice::_lock()` khi OSD mở device, không cần operator bật config. Trước failback phải dừng owner hiện tại, xác minh không còn process/descriptor nắm device, rồi thử mở clone bằng một owner; thay macro/binary không giành lại khóa đã mất ở process đang chạy. Hạ OSD không undo write do hai owner mở trùng, nên lỗi overlap là stop condition để giữ device snapshot/log và đối soát integrity. Chưa có toolchain/kernel As-Is để khẳng định fallback áp dụng.

### MSG-053 — Thêm cờ OSD map và client nhận pool EIO

**CSV:** `src/include/rados.h`. Target thêm `CEPH_OSDMAP_NOAUTOSCALE`, `CEPH_RELEASE_QUINCY`/tăng `CEPH_RELEASE_MAX`, và `CEPH_OSD_FLAG_SUPPORTSPOOLEIO`. MON dùng cờ noautoscale khi xử lý `osd set/unset`; `Objecter` đặt cờ SUPPORTSPOOLEIO trên op, `PrimaryLogPG` phân nhánh khi pool có `FLAG_EIO`: client mới được để tự xử lý, client không có cờ nhận `-EIO` từ OSD. Cùng hành vi nằm ở [MON-001](./04-mon-osdmap-crush.md) và [OSD-015](./01-osd-pg-recovery.md); đây là các constant chia sẻ của đường ấy.

**Điều kiện:** đặt noautoscale, dùng pool EIO, hoặc logic so release trong rolling upgrade. Mixed-version client/OSD có thể mang/không mang cờ SUPPORTSPOOLEIO; sau full upgrade cần kiểm command và error trả về. **Evidence confidence:** high cho constant và call sites, medium cho ma trận client thực tế chưa chạy.

**Kiểm chứng:** lab tạo pool thử có EIO, gửi op từ client Pacific/Quincy tới OSD Quincy, quan sát flag request, reply/timeout và lỗi client cuối cùng; đặt/bỏ `noautoscale` trên MON đủ release và so OSDMap/PG autoscaler.

**Activation, tác động và rollback:** client target tự gắn SUPPORTSPOOLEIO trên op; noautoscale là thay đổi explicit ở OSDMap, còn release constants chỉ cung cấp giá trị cho handler. Compatibility/availability của pool EIO phải quan sát terminal client result và timeout ở mixed lab, không chỉ cờ đã xuất hiện. Rollback client không xóa pool flag hoặc OSDMap đã persist; cần giữ map/pool state trước thao tác và đối soát request chưa rõ completion. Bỏ noautoscale có thể cho autoscaler hoạt động trở lại, vì vậy không dùng nó như rollback trung tính với placement. Các gate release/BlueStore quyết định khả năng hạ OSD sau full upgrade; bài probe này chưa chạy và không chứng minh downgrade an toàn.

### MSG-054 — Formatter thời gian scrub dùng UTC

**CSV:** `src/include/utime_fmt.h`. Target thêm `fmt::formatter<utime_t>`: thời gian tương đối vẫn ở dạng giây.microsecond, còn thời gian tuyệt đối dùng `fmt::gmtime` và `%z`. `operator<<` cũ của `utime_t` dùng `localtime_r`; target formatter được `osd_scrub_sched.cc` và `osd_types.cc` dùng cho trạng thái lịch scrub. Hai đường có thể hiển thị múi giờ khác trên host không chạy UTC; giá trị `utime_t` và lịch thực tế không đổi chỉ từ formatter.

**Điều kiện:** operator hoặc parser đọc thời gian lịch scrub trong log/status trên host timezone khác UTC. Mixed-version chuỗi từ mỗi OSD có thể khác timezone; sau full upgrade phải diễn giải timestamp nhất quán khi kiểm scrub. **Evidence confidence:** high cho formatter/call site, medium cho đầu ra cụ thể chưa chạy.

**Kiểm chứng:** cùng lịch scrub trên lab timezone UTC và Asia/Ho_Chi_Minh, so ostream/fmt output, trạng thái scrub CLI/log và parser cảnh báo; kiểm timestamp epoch bên dưới vẫn tương đương.


**Activation, tác động và rollback:** formatter mới tự động áp ở call site fmt của scrub, tác động observability khi parser coi UTC là giờ local hoặc so deadline khác múi giờ. Lưu epoch gốc và timezone của host/collector trước rollout; rollback parser có thể sửa cách diễn giải bản ghi, nhưng hạ binary không sửa timestamp string đã ghi. Nếu chuỗi mới khiến alarm báo scrub overdue, dừng gate dựa trên parser đó và đối chiếu epoch/scrub state thật trước thay schedule. Chưa thực thi formatter trên platform mục tiêu, và thay hiển thị không chứng minh thời gian scrub đã đổi.

### MSG-055 — Clone packet DPDK giữ đúng RSS hash

**CSV:** `src/msg/async/dpdk/Packet.h`. Base khi `Packet::impl::allocate_if_needed` tạo storage mới gọi `n->rss_hash.construct(old->rss_hash)`: `Tub<uint32_t>` có phép đổi ngầm sang bool, nên đối số cho `uint32_t` có thể thành 0/1 thay vì giá trị RSS gốc. Target dùng `std::optional<uint32_t>` và gán cả optional, giữ trạng thái rỗng cùng hash. `DPDK.cc` điền RSS hash từ `rte_mbuf`, còn `net.cc` đọc nó để chọn luồng nhận; thay đổi có đường tới phân phối packet khi storage phải mở rộng. Commit `3dbcaf5606e` là cụm chuyển Tub sang optional, nhưng kết luận ở đây dựa trên biểu thức hai endpoint.

**Điều kiện:** DPDK nhận packet có RSS hash rồi Packet phải cấp lại storage do số fragment/headroom. Mixed-version mỗi daemon có thể chọn queue khác cho cùng flow; sau full upgrade cần theo dõi phân phối flow và mất gói. **Evidence confidence:** high cho phép chuyển kiểu/call path, medium cho tần suất tái cấp phát thực tế.

**Kiểm chứng:** lab tạo packet có hash khác 0/1, buộc `allocate_if_needed`, so hash trước/sau trên hai tag và qid nhận; chạy traffic nhiều fragment, ghi per-queue distribution, reorder/drop và CPU affinity.

**Activation, tác động và rollback:** optional copy tự động áp khi packet storage được mở rộng; correctness/performance liên quan flow steering vì hash không còn bị biến thành giá trị engaged 0/1 trong biểu thức base. Trước restart giữ hash/qid và fragment shape của packet probe; rollback network stack cần drain traffic và khởi tạo lại packet RAM, không truyền object layout qua hai binary. Packets đã drop/reorder không được phục hồi khi đổi optional; đối soát completion/checksum ở ứng dụng và pause canary nếu flow concentration hoặc mất gói tăng. Chưa chạy test tái cấp phát, nên chưa định lượng tỷ lệ flow đổi queue trong workload thực tế.

### MSG-056 — DPDK EAL có vòng đời và xử lý lỗi khởi tạo riêng

**CSV:** `src/msg/async/dpdk/DPDKStack.cc/.h`, `dpdk_rte.cc/.h`. Base EAL là state static, thread master detach và vòng đợi không có stop; target đặt EAL trong `DPDKStack`, `start()` trả lỗi khi `rte_eal_init` thất bại, `join_worker` gọi `stop()`/join sau worker cuối. Target reserve vector callback và truyền địa chỉ phần tử `funcs.back()` cho remote launch, thêm `ms_dpdk_devs_allowlist` vào argv EAL; đổi tên thread đã mô tả tại MSG-051. Các thay đổi này ảnh hưởng start/restart DPDK, chọn NIC và shutdown.

**Điều kiện:** messenger DPDK được bật, nhất là nhiều worker, NIC allowlist hoặc EAL init lỗi. Mixed-version từng OSD có NIC/lcore/khả năng restart khác; sau full upgrade cần bảo đảm không giữ master thread cũ hoặc thiếu NIC. **Evidence confidence:** high cho code và config path, medium cho khả năng tương tác với NVMeDevice/DPDK EAL global khi chạy thật.

**Kiểm chứng:** lab start/stop/restart DPDK với coremask hợp lệ và lỗi, NIC allowlist một/nhiều thiết bị, nhiều worker và DPDK dùng chung NVMe; ghi PID/TID, lcore, trạng thái `rte_eal_init`, NIC enumerate, hang/abort lúc shutdown.

**Tác động và rollback:** EAL lifecycle/allowlist ảnh hưởng delivery/availability lúc start, stop và restart; config explicit được lấy lúc dựng argv, lỗi init trở thành `-EIO` trả từ `start()` thay vì luồng detach chờ vô hạn. Target vẫn có static `rte_initialized`, nên EAL đã khởi tạo thành công không được re-init chỉ vì tạo stack mới; đổi allowlist sau đó chưa chứng minh NIC được enumerate lại. Trước failback giữ argv/lcore/hugepage và chứng minh toàn bộ worker đã join; hạ package trong khi EAL thread còn sống không phục hồi master state. Op đang bay phải đối soát reconnect/resend. Chưa diễn tập DPDK dùng chung NVMe nên không khẳng định stop một stack giải phóng mọi EAL resource.

### MSG-057 — Cấu hình TSO, tương thích mbuf và thống kê PMD

**CSV:** `src/msg/async/dpdk/DPDK.cc/.h`. Base bật TSO nếu NIC báo hỗ trợ; target còn yêu cầu `ms_dpdk_enable_tso`, mặc định true, cho phép tắt trên NIC/DPDK có TSO lỗi. Target đổi trường/ API `buf_physaddr`/`rte_mem_virt2phy` sang `buf_iova`/`rte_mem_virt2iova`, thêm `show_pmd_stats`/`show_pmd_xstats` qua admin socket, và một số lỗi init từ `rte_exit` sang return/assert. Commit liên quan `f84196ac0f0`, `43b5f960935`, `744b197052c`. Đây là đường NIC/offload và tín hiệu vận hành, không suy throughput tăng từ source.

**Endpoint delivery defect:** `XstatSocketHook::call` tại target `DPDK.cc:402–405` có năm tham số và `override`, còn `AdminSocketHook::call` tại target `src/common/admin_socket.h:60–66` là pure virtual sáu tham số, thêm `const ceph::buffer::list& inbl`. Không có overload tương ứng trong base class đã đọc. Vì vậy hook target không override interface, còn `make_unique<XstatSocketHook>` tạo class chưa implement pure virtual: đây là lỗi compile theo chữ ký khi source DPDK được build. `src/msg/CMakeLists.txt` đưa `DPDK.cc` vào `common_async_dpdk` chỉ dưới `WITH_DPDK`; root CMake default OFF. Không thể coi hai PMD command là tín hiệu usable của tag nguyên bản trước khi delivery gate này được giải quyết. Đã đối chiếu source, chưa chạy compiler hoặc sửa source Ceph.

**Điều kiện:** build target với `WITH_DPDK=ON`, rồi chạy messenger DPDK với NIC hỗ trợ TSO; API iova phụ thuộc bản DPDK build. Trong mixed-version, artifact DPDK target nguyên bản vướng chữ ký hook trước khi có thể thay daemon; nếu vendor có patch phải lưu patch/package provenance. Sau full upgrade bằng artifact đã build được vẫn cần xác nhận TX checksum/segmentation và alert mapping. **Evidence confidence:** high cho config/API và mismatch chữ ký source, medium cho package/NIC thực tế chưa kiểm.

**Kiểm chứng:** trên lab NIC/DPDK mục tiêu, so build/link và TX traffic với TSO bật/tắt, packet capture/checksum, lỗi NIC init, kết quả hai admin commands, tốc độ và drop/xstats; chỉ kết luận cải thiện khi đo workload tương ứng.

**Tác động và rollback:** delivery/observability gate đến trước TSO runtime gate. `ms_dpdk_enable_tso` là config explicit được dùng lúc init NIC; tắt nó không sửa compile mismatch của hook. Trước phát hành giữ build log, DPDK ABI và vendor patch nếu có; failback phải phục hồi binary–DPDK pair đã thử, stop/drain traffic rồi init NIC đúng profile. Thay package không undo packet lỗi hoặc I/O đã được ứng dụng chấp nhận, nên giữ checksum/return completion trước restart. Khi build chưa qua, kế hoạch canary không được phụ thuộc vào PMD commands mới.


### MSG-058 — Test DPDK networkstack phụ thuộc cấu hình lab

**CSV:** `src/test/msgr/test_async_networkstack.cc`. Base test tự gán `ms_type=async+dpdk`, coremask `0x7` và ba IPv4 cố định; target bỏ các giá trị đó, lấy `ms_dpdk_host_ipv4_addr` từ config hiện hành để dựng endpoint, vẫn đặt `ms_async_op_threads=2`. Bởi vậy cùng test binary có thể chạy hoặc thất bại theo cấu hình lab và NIC được cấp, không còn tự tạo toàn bộ test setup. Hunk không thay đổi production network stack.

**Điều kiện:** dùng test này làm gate DPDK trước rollout. Trong mixed-version lab, bản test của hai source tree yêu cầu setup khác; sau full upgrade phải lưu rõ config để kết quả có thể lặp lại. **Evidence confidence:** high cho SetUp, medium cho cấu hình runner hiện tại chưa biết.

**Kiểm chứng:** chạy test trên lab DPDK với config hiện hành được ghi lại, gồm coremask, NIC allowlist, host/gateway/netmask và hugepages; chạy trường hợp thiếu config để thấy failure signal, rồi kiểm traffic và cleanup worker.

**Tác động và rollback:** test configuration ảnh hưởng validation/delivery của DPDK: thiếu host/coremask/NIC hợp lệ có thể tạo failure từ setup trước khi exercised messenger behavior. Việc chọn runner/config là thao tác explicit; target chỉ tự lấy giá trị hiện hành khi SetUp chạy. Rollback acceptance path cần phục hồi test binary cùng fixture/argv/host allocation đã lưu, không chỉ checkout file test base. Kết quả PASS của posix hoặc test skip không thay cho DPDK gate, và lỗi compile MSG-057 phải được xử lý trước bài runtime. Chưa chạy test; giữ failure/cleanup log để phân biệt setup lỗi với regression mạng.

### MSG-059 — Mở rộng validation msgr2 compression

**CSV:** `src/test/msgr/test_comp_registry.cc`, `test_frames_v2.cc`. Target thêm `unittest_comp_registry` vào CMake để kiểm chọn algorithm/mode, secure compression và min size; frame roundtrip mở từ bốn mode rev/secure sang tám tổ hợp có/không compression, tạo handler Snappy và kiểm chiều dài frame. Đây là coverage của đường msgr2 compression đã được phân tích trong các finding trước, không tự chứng minh mixed-version production tương thích.

**Điều kiện:** pipeline nâng cấp chạy các unit test messenger như acceptance gate. Mixed-version cần bổ sung test giữa binary Pacific/Quincy vì roundtrip này dùng cùng binary; sau full upgrade test giúp bắt regression encode/decode/compression. **Evidence confidence:** high cho CMake/test matrix, medium cho CI/lab thực tế và interoperability chưa chạy.

**Kiểm chứng:** chạy hai target test trên build Quincy với và không có Snappy, ghi số case/skip/fail; ngoài unit test, gửi message lớn/nhỏ qua client/daemon khác version và secure/nonsecure, so payload, negotiated method và wire size.


**Activation, tác động và rollback:** coverage mới chỉ có hiệu lực khi pipeline build và thực thi các test target explicit; tác động validation là thêm điều kiện encode/decode và registry cần pass trước bật compression. `test_comp_registry` được đọc có no-common-method, secure flag và min-size; frame test so payload cùng binary, nên không tự kiểm protocol feature negotiation với Pacific. Rollback runner phải giữ test matrix, Snappy dependency và kết quả từng mode để tránh mất coverage khi đổi artifact. Tắt production compression là checkpoint riêng MSG-003; rollback test không undo session hay op của lab/cluster. Chưa chạy unit tests hoặc mixed peers, mọi kịch bản vẫn là kế hoạch kiểm chứng.

### MSG-060 — `ceph_le` chuyển đổi endian qua Boost

**CSV:** `src/include/byteorder.h`. Base dùng `mswab` theo `CEPH_BIG_ENDIAN` và các helper `init_le16/32/64`; target dùng `boost::endian::native_to_little`/`little_to_native`, thêm constructor tường minh và bỏ helper cũ. Các trường `ceph_le*` được dùng trong cấu trúc wire/disk, nên cùng giá trị phải sinh đúng byte trên little/big-endian; diff tự nó chưa chứng minh có thay đổi byte. Code C++ ngoài cây gọi helper cũ cũng cần sửa/build lại.

**Điều kiện:** build trên big-endian, dùng dữ liệu/wire được tạo bởi binary khác version, hoặc extension C++ dùng API cũ. Mixed-version có thể phát hiện sai khác byte nếu hai endian implementations không tương đương; sau full upgrade cần đọc dữ liệu cũ. **Evidence confidence:** high cho API/code, medium cho byte thực tế chưa roundtrip trên các kiến trúc.

**Kiểm chứng:** build LE/BE mục tiêu, encode/decode vector 16/32/64-bit có bit cao, so byte với Pacific và golden fixtures, thử trên message/OSDMap/metadata clone; build extension nội bộ với header Quincy.

**Activation, tác động và rollback:** conversion mới tự động dùng ở mọi constructor/assignment/read của `ceph_le` trong binary target; compatibility/integrity còn phụ thuộc Boost/toolchain và kiến trúc. Commit `144e49052bd`, `a606fedf07f`, `f80ead83041` nối thay swab, constructor và bỏ helper. Trước target write trên clone phải lưu golden byte fixtures và verify cả chiều đọc Pacific data, không chỉ encode rồi decode bằng cùng implementation mới. Nếu byte khác reference thì stop gate và giữ raw bytes; hạ binary không sửa các field đã persist. Không suy global failback từ struct packed/layout local giữ nguyên: MON/BlueStore/MDS feature state vẫn cần gate riêng. Chưa thực thi cross-endian roundtrip.

### MSG-061 — Header cấu hình sinh thêm/bỏ các feature gate

**CSV:** `src/include/config-h.in.cmake`. Target thêm `HAVE_MEMSET_S`, `HAVE_SUSECONDS_T`, `WITH_SYSTEMD`, `WITH_EC_ISA_PLUGIN`, `WITH_RADOSGW_DBSTORE`, `WITH_LIBCEPHSQLITE`; bỏ các macro LevelDB, một số RGW frontend, ISA-L cũ và cryptsetup legacy. Một số gate có caller trực tiếp: `Journald.h` dựa `WITH_SYSTEMD`, MGR dùng `WITH_LIBCEPHSQLITE`, RGW dùng DBStore, MSG-031/049 dùng hai probe platform. Header chỉ là template: hiệu lực phụ thuộc CMake option/probe của gói target.

**Điều kiện:** chọn build option/package tương ứng hoặc migrate binary từ builder khác. Mixed-version có thể có logging, backend và plugin khác theo gói; full upgrade cần inventory feature đã compile. **Evidence confidence:** high cho macro/call site, medium cho effective values của gói triển khai.

**Kiểm chứng:** lưu `config.h` đã sinh của Pacific/Quincy, CMake cache và package manifest; đối chiếu từng gate với binary (`ldd`/symbol) và chạy smoke test journald, MGR SQLite, RGW DBStore/ISA-L nếu bật.

**Tác động và rollback:** generated macro ảnh hưởng delivery/compatibility của artifact; template không tự bảo đảm package có plugin/backend được MOP kỳ vọng. Config build explicit được chốt khi generate header rồi code branch tự hoạt động ở runtime. Ranh giới phục hồi là coherent binary–plugin–dependency package với CMake cache/config.h đã lưu; rollback template đơn lẻ không tắt feature trong binary. Backend/store đã dùng DBStore hoặc SQLite có state riêng và không được xem là dữ liệu có thể hạ phiên bản chỉ vì macro cũ không tồn tại. Chưa có manifest package As-Is/target, nên cần kiểm cả những gate OFF trước full deployment và giữ smoke results theo build.

### MSG-062 — Hiển thị MON subscription ép về `long`

**CSV:** `src/include/types.h`. Base stream trực tiếp `ceph_mon_subscribe_item.start` kiểu `__le64`; target ép `(long)i.start` trước khi in. `ceph_le` đổi endian ở MSG-060 vẫn giải mã giá trị; nhưng trên 32-bit hoặc LLP64, `long` 32-bit nên epoch/version trên `LONG_MAX` có thể bị cắt khi xuất log. Wire struct/encode không đổi từ hunk này.

**Điều kiện:** client/daemon build với `sizeof(long)==4`, hoặc version lớn vượt dải signed long. Mixed-version log subscription có thể khác dù request giống nhau; full upgrade cần tránh dùng chuỗi đã cắt làm bằng chứng version. **Evidence confidence:** high cho cast/kiểu, medium cho platform/version thực tế.

**Kiểm chứng:** unit in `start` gần `2^31`/`2^32` trên toolchain 32/64-bit, so Pacific/Quincy với giá trị wire đã decode; xác nhận metric/parser dùng field này nếu có.

**Activation, tác động và rollback:** cast tự động áp khi ostream in subscription, tác động observability trên ABI `long` hẹp; chuyển unsigned 64-bit ngoài dải signed long có kết quả phụ thuộc implementation, nên không dùng string làm nguồn epoch. Ranh giới phục hồi là parser/fixture theo raw decoded `start` và giới hạn platform; hạ binary chỉ đổi log mới, không khôi phục số bị cắt trong log lịch sử. Khi so subscription để quyết định MON hội tụ, giữ wire field/JSON tương ứng và dừng gate dựa riêng vào stream output khác nhau. Chưa có epoch/platform As-Is; không gán lỗi wire negotiation cho cast hiển thị.

### MSG-063 — Callback mã hóa QAT trả giá trị hợp lệ

**CSV:** `src/crypto/qat/qcccrypto.cc`. Base `QccCrypto::crypt_thread(void*)` gọi `do_crypt` rồi đi hết hàm mà không trả `void*`; target trả `thread_args`. `perform_op` tạo pthread và `pthread_join` nhưng bỏ qua return value, nên khác biệt chủ yếu là loại bỏ undefined behavior ở đường thread callback, không đổi thuật toán crypto từ hunk này.

**Điều kiện:** gói bật QAT và workload dùng accelerator trong cửa sổ nâng cấp. Mixed-version mỗi daemon/client thực thi callback của binary mình; full upgrade cần kiểm mã hóa/giải mã vẫn ra cùng ciphertext/plaintext. **Evidence confidence:** high cho control flow, medium cho ảnh hưởng thực tế của UB/compiler.

**Kiểm chứng:** chạy QAT encrypt/decrypt trên lab với cùng test vector, nhiều thread và restart, ghi lỗi pthread, sanitizer và kết quả join; không dùng key production.

**Tác động và rollback:** callback return tự động áp ở thread QAT, ảnh hưởng correctness/availability ở code từng đi khỏi hàm non-void mà không trả. `pthread_join` không lấy result, nên không gán cải thiện throughput hoặc thay cipher cho return mới. Trước failback phải hoàn thành/drain crypto operations rồi phục hồi QAT dependency–binary pair; hạ library dưới thread đang chạy không đưa callback về phiên bản khác. Ciphertext/plaintext đã đưa tới ứng dụng cần test vector/checksum để đối soát, không undo bằng restart. Chưa có accelerator/toolchain As-Is hoặc sanitizer run để định lượng UB ở base.

### MSG-064 — Log entry move không còn `noexcept`

**CSV:** `src/log/Entry.h`. Base `ConcreteEntry(ConcreteEntry&&)` được đánh dấu `noexcept`; target bỏ qualifier nhưng vẫn move `str`. `Log.h` dùng `std::vector<ConcreteEntry>` và `boost::circular_buffer<ConcreteEntry>`; khi vector tăng dung lượng, `std::move_if_noexcept` có thể chọn copy thay vì move, gây cấp phát/tốn thời gian hơn trong đường lưu log. Không có bằng chứng log bị mất hay latency tăng trong workload thực tế từ source đơn lẻ.

**Điều kiện:** daemon tạo nhiều log entry làm vector tăng dung lượng, nhất là khi tăng debug trong canary. Mixed-version footprint logging có thể khác; full upgrade cần quan sát RSS/CPU của logger nếu dùng log làm stop/go signal. **Evidence confidence:** high cho qualifier/container, medium cho hiệu năng runtime.

**Kiểm chứng:** benchmark growth của EntryVector ở hai tag với message ngắn/dài, đo copy/move/allocation và latency; trong lab bật mức debug dự kiến rồi so log throughput và RSS.


**Activation, tác động và rollback:** exception specification tác động tự động khi container chọn construction/reallocation; performance/capacity của logging conditional trên growth và allocator, không cần operator bật feature mới. Ranh giới phục hồi là trước thay logger binary/dependency: giữ debug level, message-size distribution và allocation/RSS baseline. Hạ package không lấy lại memory/latency đã tiêu tốn hay log dropped vì resource pressure; restart còn mất buffer log chưa flush, nên giữ evidence/flush status trước đó. Chưa đo `EntryVector` của toolchain triển khai nên chỉ giữ giả thuyết copy/move cost để kiểm, không coi nó là regression đã xảy ra.

### MSG-065 — Crimson đọc `CEPH_ARGS` vào cấu hình khởi động

**CSV:** `src/crimson/common/config_proxy.h`. Base `ConfigProxy` không có `parse_env()` trong header; target gọi `get_config().parse_env(CEPH_ENTITY_TYPE_OSD, ...)` qua `do_change`, và `src/crimson/osd/main.cc` gọi nó trước khi chạy OSD. Getter cũng nhận `string_view`. **Điều kiện:** triển khai Crimson truyền override qua `CEPH_ARGS`; mixed-version effective config có thể khác theo binary, full upgrade cần đối chiếu config thực tế. **Confidence:** high cho call path, medium cho môi trường triển khai. **Kiểm chứng:** lab đặt `CEPH_ARGS` cho option vô hại, start hai tag, so config effective, log khởi động và priority so với config file/CLI.

**Activation, tác động và rollback:** parse môi trường chạy tự động khi Crimson target khởi động; operator/wrapper đặt `CEPH_ARGS` explicit, nên availability/config compatibility có thể đổi ngay ở restart đầu. Target `main.cc` gọi parse config files, rồi `parse_env()`, rồi `parse_argv()`; commit `7b75040d257` thêm bước môi trường. Thứ tự call đã đọc nhưng precedence cuối cùng phải so effective value khi cùng option có ở cả ba nơi. Trước failback giữ service environment, argv và config hiệu dụng; xóa biến hoặc phục hồi wrapper chỉ tác động process start tiếp theo. Hạ binary không trả config persistent/cluster state đã bị daemon thay đổi về trước restart; cần kiểm các MON/store gate riêng. Chưa có service environment As-Is và chưa chạy precedence probe.

### MSG-066 — Future Crimson truyền interruption qua recovery/SeaStore

**CSV:** `src/crimson/common/condition_variable.h`, `errorator-loop.h`, `errorator.h`, `exception.h`, `interruptible_future.h`, `utility.h`. Base có future/errorator hạn chế hơn; target thêm `repeat`, typed `parallel_for_each`, condition variable chờ có interrupt, visitor trả ready future, base exception `interruption` cho shutdown/acting-set và các continuation hỗ trợ interrupt. SeaStore dùng condition variable ở segment rotation; Crimson recovery dùng `interruptor::parallel_for_each`. Đây là đường hủy/hoàn thành operation khi shutdown hoặc acting set đổi, không phải đổi wire format từ các header này.

**Điều kiện:** chạy Crimson OSD/SeaStore, nhất là peering/recovery hoặc rotate segment đồng thời stop. Mixed-version từng OSD có thể hủy hoặc chờ future khác nhau; full upgrade cần xác nhận không còn operation treo sau chuyển acting set. **Confidence:** high cho API/call sites, medium cho thứ tự race thực tế. **Kiểm chứng:** lab gây acting-set change và stop/restart khi recovery + SeaStore rotate, so completed/cancelled futures, operation blockers, hang, log lỗi và data checksum sau restart.

**Tác động và rollback:** correctness/availability của shutdown và recovery phụ thuộc continuation được interrupted hay hoàn thành, cơ chế tự động khi shutdown/acting-set trigger thay đổi điều kiện. Call sites target `recovery_backend.cc:178` và `replicated_recovery_backend.cc:57,142,602` dùng interruptible parallel-for-each; commit `e3ad392fd04` và `f7d3c14f2de` giải thích operation/typed-future path. Ranh giới phục hồi là trước stop/acting-set transition: giữ danh sách op, completion và durable transaction state rồi replay clone sau restart. Hạ future headers không khôi phục continuation RAM đã hủy hoặc undo transaction đã commit; kiểm cancellation không bỏ write ở cả mixed và full lab. SeaStore format/release gates vẫn quyết định failback toàn store. Chưa chạy race/interrupt probe và không suy mọi shutdown giờ hết hang.

### MSG-067 — Crash Crimson có stacktrace, siginfo và core reraise

**CSV:** `src/crimson/common/fatal_signal.cc/.h`. Base chưa có class này; target `crimson/osd/main.cc` tạo `FatalSignal`, lắp handler cho SIGSEGV/ABRT/BUS/ILL/FPE và một số tín hiệu fatal khác, in stacktrace, `siginfo`/`/proc/self/maps`, rồi reraise signal mặc định để tạo core. **Điều kiện:** Crimson OSD gặp crash trên Linux. Mixed-version artifact crash có nội dung khác; full upgrade cần chắc pipeline thu log/core vẫn nhận diện. **Confidence:** high cho handler/call site, medium cho hành vi của service manager. **Kiểm chứng:** trong process lab riêng gây SIGABRT/SIGSEGV có kiểm soát, so exit signal, core, stderr, stacktrace và bản ghi crash collector; không gây crash production.

**Activation, tác động và rollback:** handler tự động được lắp trong startup Crimson; tác động observability/availability là stderr có backtrace/maps và termination dùng signal mặc định. Commit `b018f86cd83` thêm reraise; source còn TODO dump crash metadata tới crash_dir, nên không coi nó đã có đầy đủ classic crash JSON. Core có thực sự được lưu phụ thuộc ulimit/service manager và collector. Trước restart/rollback giữ stderr/core cùng debug symbols đúng build; hạ binary không tái tạo maps/backtrace của crash trước đó. Nếu crash giữa I/O cần đối soát durable state/replay riêng, không suy handler đã bảo toàn write. Chưa diễn tập signal dưới service manager dự án.

### MSG-068 — SeaStore đổi tìm bound trong fixed-key node sang nhị phân

**CSV:** `src/crimson/common/fixed_kv_node_layout.h`. Base `lower_bound`/`upper_bound` quét tuần tự từng key; target dùng `std::lower_bound`/`upper_bound` qua counting iterator, thêm decrement iterator. Node layout/encoding không đổi trong hunk; kết quả phải tương đương nếu key được sắp xếp, còn workload đọc nhiều entry có đường giảm số lần so sánh. **Điều kiện:** Crimson SeaStore dùng fixed-key node ở LBA/omap. Mixed-version mỗi OSD có cách tìm khác trên dữ liệu riêng; full upgrade cần kiểm kết quả tìm và restart/replay. **Confidence:** high cho thuật toán, medium cho hiệu năng/biên dữ liệu. **Kiểm chứng:** trên node clone có 0, 1, nhiều key và duplicate/biên, so vị trí bound hai tag, scan omap/LBA, checksum và latency lookup; không suy cải thiện trước khi đo.

**Activation, tác động và rollback:** binary search tự động áp khi caller tìm bound, tác động correctness/performance conditional trên invariant key đã sắp xếp. Commit `6c3297d497c` đổi thuật toán; test phải so return index với scan reference, cả giá trị dưới key đầu và trên key cuối, trước đo lookup latency. Ranh giới failback là node/store clone trước target mutate: hạ binary đổi cách tìm trong lần chạy sau nhưng không sửa node đã bị cập nhật sai nếu invariant vi phạm. Khi scan và bound không thống nhất, stop acceptance và giữ node raw/replay log; không repair từ giả định hunk chỉ tối ưu. Chưa có lookup/restart result và global SeaStore gate không được thay bằng kết luận layout local không đổi.

### MSG-069 — Level 5 của Crimson log thành info

**CSV:** `src/crimson/common/log.h`. Base `to_log_level(5)` đi nhánh debug (`level < 5` cho info); target đổi thành `level <= 5`, nên level 5 thành info, các mức khác giữ nhánh cũ. **Điều kiện:** dùng log level 5 ở Crimson hoặc bộ lọc Seastar theo severity; mixed-version số dòng/nhãn log khác, full upgrade cần chỉnh alert và lưu lượng log. **Confidence:** high cho ranh giới, medium cho khối lượng log thực tế. **Kiểm chứng:** lab phát cùng message level 4/5/6 ở hai tag, so severity và bộ lọc collector, RSS/IO log khi canary.

**Activation, tác động và rollback:** mức severity mới tự động được chọn cho message level 5; observability/capacity đổi nếu collector chỉ giữ info trở lên hoặc alert trên info. Log level/config filter là thao tác explicit và phải lưu cùng template; rollback collector có thể trở lại mapping cũ cho log mới nhưng không biến severity/volume của record đã ingest về debug. Khi lượng log tăng, so IO/RSS và retention trước tiếp tục canary; mất dòng ở parser/filter cần phục hồi nguồn raw để đối soát. Sau full upgrade vẫn phải kiểm level 4/5/6, chưa có volume/collector As-Is để gán mức ảnh hưởng.

### MSG-070 — Crimson gửi cluster log và nhận ack từ MON

**CSV:** `src/crimson/common/logclient.cc/.h`. Base chưa có LogClient/LogChannel Crimson; target queue `LogEntry`, đóng thành `MLog` giới hạn theo `mon_client_max_log_entries_per_message`, nhận `MLogAck` để xóa entry đã xác nhận, định tuyến channel tới MON/syslog/Graylog. `crimson/osd/osd.cc` sở hữu client, `MonClient` được nối với nó. **Điều kiện:** chạy Crimson OSD và giám sát cluster log/health khi upgrade. Mixed-version đường phát log của Crimson thay đổi; sau full upgrade cần kiểm entry không mất/nhân đôi khi MON session reset. **Confidence:** high cho queue/ack/call path, medium cho delivery dưới lỗi mạng chưa thử. **Kiểm chứng:** lab tạo cluster warning, ngắt/reconnect MON, so seq/ack, số entry MON/syslog/Graylog, backlog và duplicate; quan sát sau restart OSD.

**Tác động và rollback:** log client mới chạy tự động trong Crimson target, còn `clog_to_monitors/syslog/graylog` explicit quyết định route; observability/availability của rollout gate phụ thuộc queue/ack và collector. Source `LogClient::queue`, `_get_mon_log_message`, `handle_log_ack` dùng queue RAM và xóa entry tới seq ACK, không persist backlog trong hunk. `reset()` xóa queue khi route monitor đổi, nên trước rollback/restart cần xuất pending seq/log và xác minh MON/collector đã nhận; hạ binary không phục hồi entry chưa ACK bị mất cùng process. ACK log cũng không chứng minh application I/O đã commit. Commit `7b5cb61bd92`; chưa chạy delivery dưới reset/network fault nên không cam kết exactly-once.

### MSG-071 — Operation pipeline và blocker của Crimson

**CSV:** `src/crimson/common/operation.cc/.h`. Base chưa có abstraction `Operation`/`Blocker` này; target theo dõi operation ID, blocker, stage có thứ tự/không thứ tự, xuất dump; `UnorderedStage` được SeaStore ordering handle dùng cho out-of-line writes. **Điều kiện:** Crimson SeaStore thực hiện IO đồng thời/recovery. Mixed-version các OSD lập lịch operation nội bộ khác; full upgrade cần xem không có op kẹt ở stage và dump phản ánh đúng blocker. **Confidence:** high cho kiểu/call site, medium cho fairness/latency thực tế. **Kiểm chứng:** lab chạy IO song song và shutdown/recovery, dump active operations, so stage/blocker, hoàn thành IO/checksum và độ trễ tail.

**Activation, tác động và rollback:** registry/stage được dùng tự động khi operation target thực thi; tác động correctness/availability và observability conditional trên Crimson/SeaStore concurrent IO. `ordering_handle.h:88` gắn `UnorderedStage` cho out-of-line writes, commit `55b37c35e7f` thêm stage; dump blocker chỉ phản ánh future đang chờ, không phải durable commit record. Trước stop/failback giữ operation ID/stage/blocker và kiểm pending writes được drain hoặc replay; restart mất registry RAM, không chứng minh op đã hoàn tất hoặc data đúng. Nếu hang ở stage, pause canary và giữ dump/checksum/replay log. Chưa stress fairness/shutdown và các SeaStore state gates vẫn áp dụng sau full upgrade.

### MSG-072 — Perf counter Crimson xuất qua admin socket

**CSV:** `src/crimson/common/perf_counters_collection.cc/.h`. Base collection chưa có `dump_formatted`; target chuyển tiếp tới implementation, `crimson/admin/osd_admin.cc` dùng nó. Target thêm deleter gỡ counter khỏi collection trước khi xóa. **Điều kiện:** dùng Crimson OSD admin socket/metric khi rollout. Mixed-version tên/nội dung dump và lifetime counter khác; full upgrade cần sửa dashboard nếu đọc cấu trúc mới. **Confidence:** high cho method/call site, medium cho metric cụ thể. **Kiểm chứng:** lab tạo/xóa counter và gọi admin dump nhiều lần, so JSON schema, số counter, dangling pointer/assertion, collector ingestion.

**Activation, tác động và rollback:** dump/deleter tự động được admin caller/lifetime counter target dùng; observability/correctness liên quan collector schema và removal trước `delete`. Bộ đếm RAM không chuyển qua restart; rollback parser cần fixture của cả version để tránh missing metric bị hiểu thành zero, và hạ package không hồi tố sửa time series đã lưu. Ranh giới phục hồi là trước đổi artifact dùng counter làm stop/go: giữ raw dump cùng labels/shard và kiểm create/remove trên đúng `CephContext`. Counter biến mất không đủ để kết luận op đã drain. Chưa chạy lifetime/ingest probe nên chưa chứng minh collection không có stale pointer dưới teardown.

### MSG-073 — SharedLRU không assert khi weak reference còn sống lúc hủy

**CSV:** `src/crimson/common/shared_lru.h`. Base destructor clear cache rồi `assert(weak_refs.empty())`; target clear `weak_refs` thay vì assert. Source chú thích interruption có thể để reference sống lâu hơn cache. Deleter của `shared_ptr` vẫn giữ pointer tới `SharedLRU` để `_erase_weak`, nên không thể từ hunk này kết luận an toàn nếu owner bị hủy trước reference cuối. **Điều kiện:** Crimson OSD shutdown/recovery với object-context reference đang bay. Mixed-version base có thể assert sớm, target có thể đi tiếp; full upgrade cần kiểm lifetime thực tế dưới sanitizer. **Confidence:** high cho destructor/deleter, medium cho thứ tự hủy production. **Kiểm chứng:** lab giữ reference qua destructor bằng ASan/UBSan, ghi assert/UAF; thử shutdown giữa peering/recovery và kiểm object-context cleanup.

**Activation, tác động và rollback:** destructor mới tự động chạy khi owner hủy cache, ảnh hưởng correctness/availability dưới interruption. Commit `82bfb2eef63` bỏ giả định reference không sống lâu hơn owner, nhưng `Deleter::operator()` tại target vẫn gọi `cache->_erase_weak(key)` qua raw pointer; nếu reference cuối được thả sau khi owner hủy thì có đường truy cập owner hết lifetime. Đây là điều kiện cần sanitizer/lifetime proof, không claim đã xảy ra production. `src/test/crimson/test_lru.cc` đã đọc kiểm add/empty/lookup với cache còn sống, chưa chứng minh owner-before-reference. Trước rollback cần drain/release references đúng thứ tự, giữ UAF/assert trace và object-state checksum; hạ binary chỉ có thể đưa assert cũ trở lại, không sửa op đã commit. Chưa chạy sanitizer và không coi destructor đi tiếp là evidence shutdown an toàn.

### MSG-074 — Adapter khóa exclusive đúng loại trong object context

**CSV:** `src/crimson/common/tri_mutex.h`. Base `excl_from_excl()` trả `excl_lock_from_write&`; target trả `excl_lock_from_excl&`, đúng với tên method. `crimson/osd/object_context.h` dùng adapter này khi `_with_lock` đi từ trạng thái exclusive. `tri_mutex.cc` chỉ đổi so sánh unsigned về 0, không đổi thuật toán khóa. **Điều kiện:** Crimson ObjectContext chuyển lock mode trong IO đồng thời; mixed-version có thể khác đường adapter/build, full upgrade cần kiểm không deadlock. **Confidence:** high cho type/call site, medium cho runtime vì chưa stress. **Kiểm chứng:** lab stress read/write/exclusive transition trên cùng object, bật lock diagnostics, so hang, assertion, kết quả IO và cleanup sau restart.

**Activation, tác động và rollback:** đúng adapter tự động được chọn ở object-context `_with_lock` khi đã có exclusive lock; correctness/availability liên quan tránh dùng write-to-exclusive conversion sai. Commit `1f98a44688c` xác nhận sửa return type; call sites target `object_context.h:181,194` đã đọc. Trong mixed mỗi OSD dùng template của binary mình; sau full upgrade vẫn cần stress transition và interrupted operation. Ranh giới phục hồi là trước thay process có active lock/op: drain hoặc ghi completion/replay checkpoint trên clone, không truyền mutex state RAM qua binary. Hạ header/package không undo transaction đã hoàn tất và có thể phục hồi adapter sai của base. Chưa chạy stress nên chưa khẳng định deadlock đã bị loại bỏ; kiểm data checksum và SeaStore/MON gates riêng.

## Thay đổi trivial

71 hàng `trivial` đã đọc gồm forward declaration không dùng, pragma cảnh báo trong Crypto, chú thích nhánh msgr1, helper endian giữ cùng trường/chỉ số signature, include/namespace/brace thuần cú pháp, chữ ký pointer const của armor, thay cú pháp `flock` và timeout test giữ nguyên 10 giây. `MStatfs`/`MKVData` đổi kiểu optional nhưng giữ cùng presence byte/payload encode và message version; `Policy.h` giữ mask production, cho test riêng gán mask. `ceph_crypto` chỉ thêm pragma, `exact_timespan_str` chỉ có call site test trong cây, còn `Tub` không còn include/caller target. `obj_bencher` chỉ đổi qualifier kiểu, `get_str_vec` vẫn dùng cùng hàm tách token. `weighted_shuffle.h` bỏ nhánh all-zero nhưng caller production `MonClient` đã xử lý all-zero bằng `std::shuffle` trước khi gọi helper. OpenSSL options handler chỉ đổi qualifier/pragma, còn log test theo API argv mới mà giữ input. Kqueue, socket nonblocking, RDMA include và entity formatter chỉ có thay đổi cơ học/hiển thị tương đương. Nhóm header còn có comment, qualifier, formatter tương đương và denc_lba khởi tạo biến đã được mọi nhánh switch gán; không đổi byte encode. Các file DPDK còn lại trong lượt này chỉ chuyển Tub sang optional với cùng kiểm tra engaged và cùng thao tác queue/timer; EventDPDK/TCP log chỉ đổi qualifier. Nhóm test còn lại chỉ cập nhật argv helper, import và test-only feature mask mà không thêm case chạy. QAT factory chỉ đổi qualifier; B-tree multiset node API không có caller production trong cây, còn neorados fmt, Windows dlfcn shim và xlist iterator không đổi đường dữ liệu đã đọc. Crimson throttle/tri_mutex.cc chỉ viết lại phép thử số unsigned tương đương; không gán `trivial` theo đường dẫn.

## Kiểm chứng sau binary gate

- Đối soát trên lab các đường mixed-version có tác động wire/auth: pending key, msgr2 compression, pool EIO và endian; dùng client/daemon hai tag và dữ liệu clone.
- Với triển khai DPDK hoặc Crimson, chạy các kịch bản NIC/lcore, interruptible recovery, SeaStore lookup, shutdown và shared-reference lifetime đã ghi ở MSG-055–074.
- Trên POWER8, kiểm vector CRC32C cho vùng dữ liệu thật và vùng zero/null trước khi coi đường checksum tương thích.
- Thu As-Is cluster, build flags và kết quả canary để xác định finding nào thực sự áp dụng; báo cáo này chưa thay cho quyết định GO/NO-GO.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
