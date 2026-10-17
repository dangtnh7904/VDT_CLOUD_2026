# 10 — librados/RBD, client, mirror và object class: v16.2.15 → v17.2.7

**Trạng thái: đã hoàn tất binary gate.** [CSV đầy đủ của owner](./10-rados-rbd-clients.csv) có 320 hàng, là subset theo thứ tự của [master inventory](./00-file-inventory.csv). Kết quả `affect = 58`, `trivial = 262`, **chưa phân loại = 0**; chưa có kết quả lab/runtime.

## Phạm vi và phương pháp

Owner này phụ trách librados/RBD, client, mirror và object class. Nguồn là endpoint net diff của `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`) và `v17.2.7` (`b12291d110049b2f35e32e0de30d70e9a4c060d2`) trong cùng repo `ceph16.2.15/ceph`. Hai tag ở hai release branch, nên base không phải ancestor của target. Priority trong CSV là thứ tự đọc, không phải rủi ro.

Rollback trong các finding dưới đây xác định ranh giới của client, cache, ứng dụng hoặc artifact kiểm thử. Không có hunk chuyển format riêng ở một client không chứng minh có thể hạ daemon: các gate BlueStore, MDS, release/feature và trạng thái cluster ở owner tương ứng vẫn chi phối quyết định toàn hop. Cần kiểm đúng cặp executable, thư viện, Python binding và dependency thực tế; thay file package trên đĩa chưa thay code đã được process đang chạy nạp vào bộ nhớ.

## Findings liên quan nâng cấp

Các finding chi tiết dưới đây chỉ dùng hàng `affect`; hàng `trivial` vẫn nằm trong CSV đầy đủ.

### RADOS-001 — Client hoàn tất I/O khi pool được đặt cờ EIO

**CSV:** bốn hàng `src/osdc/Objecter.cc`, `Objecter.h`, `error_code.cc`, `error_code.h` (index 2541–2544). Cùng hành vi ở OSD được ghi tại [OSD-015](./01-osd-pg-recovery.md); test hỗ trợ là `src/test/librados/aio_cxx.cc` (index 3875, nhãn `trivial`). Hunk endpoint: `Objecter::_calc_target`, `_op_submit`, `_scan_requests`, `_linger_submit`, `_prepare_osd_op` và `osdc_error_category`. Commits: `45ffdda22142943fe35af4f4827a7f3faa70f24e`, `f1c495b7a220ed2bd67d19f5b88a2c31e8c82ddd`, `14367571fc026ca926f8fb85e012ae071946b386`, `6992a1cd7436a0d99ef243f25ff16b7690be2928`; test `c2f753c57ef3bf6ac7524b341c78eeeb267ceea1`.

Ở Pacific, `_calc_target` chưa xét `FLAG_EIO`; `osdc_errc` chưa có `pool_eio` và `Objecter` chưa gắn `CEPH_OSD_FLAG_SUPPORTSPOOLEIO`. Ở Quincy, khi OSDMap của pool có `FLAG_EIO`, client mới hoàn tất op vừa submit bằng `pool_eio/-EIO`, hoàn tất op đang chờ khi quét map, và chặn đăng ký linger mới. `osdc_error_category` ánh xạ lỗi sang `io_error/-EIO`. OSD Quincy nhận op từ client hỗ trợ cờ mới thì bỏ op để client xử lý; với client cũ, OSD trả `-EIO` trực tiếp theo OSD-015. Vì vậy response và nơi phát sinh lỗi có thể khác trong giai đoạn chuyển phiên bản.

**Điều kiện và tác động:** chỉ áp dụng nếu pool thực sự bật EIO và OSDMap mới tới client; thay đổi tự động, không cần chuyển định dạng dữ liệu. Nó ảnh hưởng availability và tín hiệu lỗi của RADOS/RBD client khi pool bị đặt vào trạng thái này, chứ không suy ra tác động cho mọi pool. `Objecter::_check_linger_pool_eio` trong endpoint Quincy lại defer callback watch/notify bằng `pool_dne`, ánh xạ thành `-ENOENT`; cần kiểm riêng đường này, không gộp nó vào cam kết `-EIO` của I/O thường. Reading priority P1; rủi ro vận hành **có điều kiện** theo việc dùng pool EIO và client/watch workload. Evidence confidence **high** cho nhánh code và test I/O, **medium** cho khả năng áp dụng vào cluster chưa có As-Is.

**Mixed/full và rollback:** khi mixed client, cần ghi cả phiên bản client lẫn OSD phục vụ op; sau full Quincy, nhánh client-side EIO áp dụng cho mọi client đã nạp thư viện mới nhưng vẫn chỉ khi map có cờ. Hạ package client không xóa `FLAG_EIO` khỏi OSDMap và không hồi sinh op/linger đã hoàn tất hoặc bị unregister. Ranh giới cần giữ là trước khi đặt cờ và trước khi ứng dụng xử lý completion lỗi; nếu đã vượt qua, việc cho phép I/O trở lại cần xử lý nguyên nhân pool EIO, xác minh map hiện hành và đăng ký lại watch theo contract ứng dụng. Không retry mù write có kết quả chưa rõ chỉ vì vừa đổi binary.

**Kiểm chứng đề xuất:** trên pool lab riêng sau khi cluster cho phép cờ EIO, tạo I/O mới và I/O đang chờ bằng client Pacific/Quincy qua các OSD tương ứng, ghi mã lỗi, timeout, OSDMap epoch và log; xác nhận không có I/O treo hoặc được chấp nhận trái kỳ vọng. Thử thêm watch/notify đang tồn tại và đăng ký mới để đối chiếu `-ENOENT`/`-EIO`. Test `LibRadosAio.PoolEIOFlag` đã được đọc từ repository nhưng chưa chạy; không có kết quả lab hay cơ sở GO/NO-GO production.

### RADOS-002 — PWL compare-and-write đổi cách giới hạn vùng so sánh

**CSV:** `src/librbd/cache/pwl/AbstractWriteLog.cc` (index 2100). Commit chỉ có ở Quincy `c4c4f7e763beeaf9d234d00ea198629e078ab1d5`.

Pacific chỉ tạo `aligned_read_bl` khi compare buffer ngắn hơn dữ liệu đọc rồi dùng buffer đã chọn để tìm byte lệch. Quincy assert `read_bl.length() <= cmp_bl.length()`, cắt `sub_cmp_bl` đúng bằng độ dài dữ liệu đọc và giới hạn vòng tìm mismatch trên prefix đó. Vì vậy PWL compare-and-write có compare buffer/extent khác độ dài không còn đi qua cùng nhánh và có thể trả kết quả match hoặc offset mismatch khác sau khi thay client.

**Điều kiện và tác động:** chỉ áp dụng khi RBD persistent write log cache được bật và workload dùng compare-and-write với kích thước biên không đồng nhất; không phải thay đổi format on-disk. Đây là thay đổi client-side, nên trong giai đoạn chạy lẫn phiên bản hai host có thể cho kết quả khác nhau trên cùng image. Evidence confidence **high** cho endpoint branch, **medium** cho mức độ xuất hiện vì chưa có inventory PWL/workload.

**Activation, mixed/full và rollback:** với PWL đã bật, thay đổi tự động ở `AbstractWriteLog::compare_and_write` sau khi process nạp librbd Quincy; không có thao tác bật riêng cho fix. Trong mixed fleet, host sở hữu cache thực thi nhánh theo phiên bản của mình; full Quincy thống nhất cách lấy prefix nhưng vẫn phải thỏa kiểm tra buffer ở API RADOS-012. Trước failback client cần dừng nguồn I/O, xác nhận flush/drain hoàn tất và trạng thái cache sạch; giữ PMEM/cache file nếu còn dirty thay vì xóa nó để ép mở bằng binary cũ. Write đã được so sánh thành công rồi ghi vào cache/backend không bị đảo ngược khi thay thư viện; khôi phục nội dung cần checkpoint dữ liệu ứng dụng. Case compare ngắn hơn `len` phải kiểm cả API rejection, không gọi trực tiếp nhánh nội bộ vi phạm assert để kết luận public API crash.

**Kiểm chứng đề xuất:** tạo image lab bật PWL, chạy compare-and-write với compare ngắn hơn, bằng và dài hơn extent bằng client hai phiên bản; đối chiếu return code, mismatch offset, dữ liệu cuối cùng và log cache. Chưa chạy test runtime.

### RADOS-003 — RWL tránh `front()` trên danh sách rỗng và đóng PMEM pool ở nhánh lỗi

**CSV:** `src/librbd/cache/pwl/rwl/WriteLog.cc` (index 2112). Commits chỉ có ở Quincy `3407262de6e1b567c70ffe87b278f1d02b3683b2`, `265cedbf360f4b87ee73b26ef16b19c3921e032b`.

Pacific lấy `m_log_entries.front()` trước khi kiểm tra danh sách rỗng trong `retire_entries`; Quincy kiểm `!m_log_entries.empty()` trước. Quincy cũng thêm `err_close_pool` và `pmemobj_close(m_log_pool)` khi kiểm layout hoặc khởi tạo RWL thất bại, trong khi Pacific rời nhánh lỗi mà chưa đóng handle đã mở.

**Điều kiện và tác động:** chỉ áp dụng cho PMEM RWL cache, cụ thể nhánh retire khi queue rỗng hoặc nhánh mở pool rồi lỗi layout/init. Quincy giảm nguy cơ dereference container rỗng và rò handle/tài nguyên; không cần chuyển đổi cache layout. Evidence confidence **high** cho control flow, **medium** cho applicability.

**Activation, mixed/full và rollback:** fix tự động khi process Quincy mở RWL hoặc retire entry; PMEM pool hợp lệ vẫn được mở bằng layout đang có, còn nhánh mismatch đóng handle rồi trả lỗi thay vì chuyển layout. Trong mixed fleet chỉ cache owner chạy code mới được bảo vệ; full Quincy không sửa sẵn cache file hỏng. Rollback client về Pacific đưa nhánh `front()` cũ trở lại và không phục hồi transaction PMEM đã commit. Điểm kiểm soát là quiesce I/O, flush/drain thành công và giữ bản chụp/cache metadata trước đổi artifact; nếu layout/init lỗi thì giữ cache file cùng log để điều tra, chưa có cơ sở cho phép discard dirty cache. Chưa xác minh PMDK version, layout và dirty state của host triển khai.

**Kiểm chứng đề xuất:** fault-inject lỗi layout/init sau `pmemobj_open`, lặp mở/đóng và theo dõi descriptor/mapping; đồng thời ép retire khi queue vừa rỗng dưới sanitizer. Không dùng image production cho phép thử.

### RADOS-004 — Quincy thiếu các backport snapshot-diff mới hơn của Pacific

**CSV:** chín hàng gồm `src/librbd/ObjectMap.h`, `api/DiffIterate.{cc,h}`, `object_map/DiffRequest.{cc,h}`, `object_map/Types.h`, `io/ObjectRequest.cc`, `deep_copy/ImageCopyRequest.cc` và `src/librados/snap_set_diff.cc` (index 2071, 2084, 2088–2089, 2119, 2131, 2140–2141, 2143). Các backport chỉ có ở Pacific gồm `2749dd34f1edddd33ba9b8c3d522d7df0e52eb90`, `78bf5b166c33341316eda2065d58779ca0027d89`, `557be66f34617cea0600755afa3ee45a40b54bb3`, `a08c7da7dcc0e7f754f5e224c5cf79e25f097d71`, `0c98b16b7933276c56c8be896cf72e3eb35df7e3`, `79ff4c63fac378345885c70a793fb0b3697a1819`, `32d4a7a620c2ed73e649d94755117c1dfc9b7b95`, `df8ecf3dda1b6b6eaa79f8f82f5470c0c4e2cc2b`, `d2ee564a78f480b3261338bbab67fac418de6e3a` và `10a45d3a5e17e811f5737dad2ffcf18a2f3dcbae`.

Pacific 16.2.15 đã có các sửa đổi cho ranged/parent fast-diff, image lớn lên hoặc thu nhỏ, bỏ qua snapshot trung gian, không báo “new hole” khi hai đầu đều là hole, chỉ giữ `end_size` khi object cuối tồn tại và tách đúng fallback `read_whole_object` khỏi cờ `LIST_SNAPS_FLAG_WHOLE_OBJECT`. Quincy 17.2.7 là endpoint lịch sử cũ hơn và thiếu các backport này. Vì vậy cùng một image/snapshot chain có thể trả tập extent/state khác sau khi thay binary client; đường deep-copy cũng dùng cùng snapshot delta.

**Điều kiện và tác động:** nổi bật với fast-diff/object-map, clone có parent, diff theo range, resize, discard và snapshot trung gian. Nó có thể ảnh hưởng `rbd diff`, `export-diff`, incremental backup và deep-copy; không chứng minh dữ liệu nguồn bị sửa. Đây là client-side behavior nên mixed client có thể tạo kết quả không đồng nhất. Evidence confidence **high** cho endpoint và commit lineage, **medium** cho rủi ro dữ liệu sao lưu vì chưa chạy corpus thực tế.

**Activation và rollback:** hành vi tự động khi consumer đã nạp librbd Quincy gọi diff/deep-copy với snapshot chain tương ứng; nâng daemon đầy đủ không bổ sung backport vào client này. Full Quincy có thể cho kết quả nhất quán giữa host nhưng vẫn thiếu các xử lý Pacific nêu trên. Ranh giới rollback của pipeline là trước khi chấp nhận manifest/delta mới và trước khi xóa snapshot hoặc backup gốc; giữ snapshot nguồn và bản backup đã kiểm hash. Đổi client trở lại chỉ thay lần tính diff tiếp theo, không sửa delta đã lưu hay destination deep-copy đã được ghi. Nếu restore hash sai, dừng công bố backup đó và dựng lại từ nguồn còn giữ bằng quy trình đã kiểm chứng; chưa có corpus backup thực tế để xác nhận phạm vi ảnh hưởng.

**Kiểm chứng đề xuất:** tạo ma trận image grow/shrink/discard, parent clone và snapshot trung gian; chạy `rbd diff --whole-object`, `export-diff` và deep-copy bằng cả hai client, chuẩn hóa rồi so sánh extent/state và hash ảnh restore. Không tái sử dụng incremental chain production nếu hai binary cho manifest khác nhau.

### RADOS-005 — Python ObjectIterator giữ đầy đủ tên có byte NUL

**CSV:** `src/pybind/rados/c_rados.pxd`, `rados.pyx` (index 3256, 3258); mock hỗ trợ ở index 3257 là `trivial`. Commit chỉ có ở Quincy `da5d4c813ffdd391da54dcf5022763616bab4b21`.

Pacific binding gọi `rados_nobjects_list_next()` rồi decode C-string, nên object name, locator hoặc namespace có byte NUL bị cắt. Quincy gọi `rados_nobjects_list_next2()`, nhận độ dài riêng và decode slice đúng kích thước. C API `next2` đã có ở cả hai endpoint; thay đổi nằm ở Python binding.

**Điều kiện và tác động:** chỉ đáng kể nếu pool đã có identifier chứa NUL, thường do client khác tạo, và automation dùng Python `Ioctx.list_objects()`. Sau nâng package Python, script có thể thấy tên đầy đủ thay vì alias bị cắt; logic đối chiếu/xóa dựa trên chuỗi cũ cần kiểm lại. Evidence confidence **high** cho binding, **low-to-medium** cho applicability.

**Activation, mixed/full và rollback:** thay đổi tự động khi process Python nạp binding Quincy rồi gọi iterator. Mixed host có thể tạo inventory khác nhau cho cùng pool; full Quincy đồng nhất việc giữ byte NUL nhưng chưa chứng minh mọi consumer downstream xử lý được chuỗi đó. Listing không đổi tên object. Trước khi chạy job reconcile/delete dựa trên inventory mới, lưu danh sách identifier theo encoding bảo toàn byte và thử dry-run; rollback binding không hoàn tác object đã bị script sửa/xóa, còn binding Pacific sẽ lại cắt tên. Nếu downstream không round-trip được identifier, dừng job mutation và sửa contract tên trước, không coi việc quay lại danh sách bị cắt là khôi phục dữ liệu đúng.

**Kiểm chứng đề xuất:** tạo object/namespace có NUL bằng client có API độ dài, list bằng binding hai phiên bản và xác nhận không thao tác nhầm object khi round-trip tên.

### RADOS-006 — Mất backport truy vấn self-managed snapshots đáng tin cậy

**CSV:** `src/include/rados/librados.hpp`, `src/librados/RadosClient.{cc,h}`, `librados_cxx.cc` và `src/tools/rados/rados.cc` (index 2027, 2067–2068, 2070, 4142). Backport chỉ có ở Pacific `319ada6774d5e6f4fdf0b06eace63da7f82941b7`.

Pacific thêm `int pool_is_in_selfmanaged_snaps_mode()`: chờ OSDMap và trả lỗi như `-ENOENT`; `rados cppool`/`mksnap` dừng khi truy vấn lỗi và `cppool` yêu cầu `--yes-i-really-mean-it` nếu pool từng dùng self-managed snapshots. Quincy 17.2.7 chỉ có API bool cũ, không chờ map và trả `false` nếu map chưa có hoặc pool không tìm thấy. Nâng từ endpoint Pacific mới hơn về code Quincy cũ vì vậy tái tạo false-negative mà backport đã sửa. Symbol int của Pacific cũng không tồn tại ở Quincy.

**Điều kiện và tác động:** `rados cppool` chạy trên client vừa kết nối có thể bỏ qua cảnh báo/gate và tạo bản sao không bảo toàn self-managed snapshots; `mksnap` cũng có thể đi tiếp sau false-negative. Ứng dụng C++ đã build trực tiếp với symbol int của Pacific có nguy cơ lỗi nạp/link sau khi chỉ thay shared library. Evidence confidence **high**; applicability phụ thuộc việc dùng pool self-managed snapshots và ứng dụng C++ ngoài cây.

**Activation, mixed/full và rollback:** regression tự động theo cặp executable/librados nạp lúc khởi chạy; các lệnh `cppool`/`mksnap` là tác vụ explicit, không tự chạy do upgrade. Mixed client có gate truy vấn khác nhau; full Quincy vẫn giữ API bool thiếu đợi map, nên hoàn tất daemon rollout không giải quyết false-negative. Ranh giới artifact là trước thay shared library cho consumer còn tham chiếu symbol int Pacific: giữ cả ứng dụng và thư viện cùng build để có thể failback process. Ranh giới dữ liệu là trước lệnh copy/snapshot; đổi lại CLI không tái tạo snapshot lineage đã không được copy, không xóa bản copy đã sinh, và không hoàn tác snapshot đã tạo. Cần giữ nguồn cùng snapshot list và kiểm destination trước khi cho pipeline chuyển sang dùng nó.

**Kiểm chứng đề xuất:** trước rollout, inventory binary phụ thuộc librados; dùng pool lab self-managed và client fresh để chạy `cppool` không/ có force, pool không tồn tại và `mksnap`, ghi mã lỗi. Kiểm exported symbols và chạy smoke binary Pacific với librados Quincy trước khi thay package trên host ứng dụng.

### RADOS-007 — `ObjectReadOperation::sparse_read` đổi C++ ABI

**CSV:** cùng hai hàng `src/include/rados/librados.hpp`, `src/librados/librados_cxx.cc` (index 2027, 2070). Commit chỉ có ở Quincy `0ea387dd941b60113a2c0af7928a48dd6a84058f`.

Pacific export phương thức năm tham số. Quincy thêm `truncate_size` và `truncate_seq`; hai đối số có default nên source cũ vẫn compile, nhưng tên symbol C++ đã mangled theo chữ ký bảy tham số và implementation không giữ overload năm tham số. Binary đã build với Pacific vì vậy không được bảo đảm nạp/chạy chỉ bằng việc đổi `librados` sang Quincy; rebuild sẽ gọi symbol mới. Các tham số mới còn cho phép chuyển metadata truncate xuống sparse-read op.

**Điều kiện và tác động:** chỉ áp dụng cho ứng dụng C++ gọi trực tiếp `ObjectReadOperation::sparse_read`; C API và wrapper cấp cao không tự động chịu cùng lỗi symbol. Đây là compatibility của client artifact, không phải wire/on-disk conversion. Evidence confidence **high** cho header/implementation, **medium** cho fleet vì chưa có SBOM.

**Mixed/full và rollback:** lỗi symbol phụ thuộc artifact của từng host, không phụ thuộc primary OSD là Pacific hay Quincy; full Quincy daemon vẫn không làm consumer cũ có thêm symbol phù hợp. Activation xảy ra khi loader resolve symbol, có thể lúc process khởi chạy hoặc lần gọi đầu nếu lazy binding. Rebuild với header Quincy chuyển consumer sang symbol bảy tham số, nên rollback chỉ thư viện về Pacific cũng có thể làm consumer mới lỗi link/load. Điểm failback cần giữ là cặp ứng dụng và librados đã kiểm ABI, kèm dependency closure; triển khai và phục hồi cặp đó rồi restart process có kiểm soát. Đường đọc này không tự chuyển dữ liệu, nhưng khả năng client cũ kết nối cluster sau các gate khác vẫn cần kiểm riêng.

**Kiểm chứng đề xuất:** compile một probe năm tham số với Pacific, chạy/link lại không rebuild với librados Quincy, rồi rebuild bằng header Quincy; kiểm symbol bằng công cụ ABI của nền tảng. Rebuild và phát hành đồng bộ mọi consumer bị ảnh hưởng trước khi gỡ librados Pacific.

### RADOS-008 — Quincy cho phép loại từng loại I/O khỏi RBD QoS

**CSV:** chín hàng `src/librbd/ImageCtx.cc`, `io/ImageDispatcher.{cc,h}`, `ImageDispatcherInterface.h`, `QosImageDispatch.{cc,h}`, `IoOperations.{cc,h}`, `Types.h` (index 2077, 2124–2126, 2129–2130, 2132–2134). Commit chỉ có ở Quincy `e87e1806d8658321bc239a8d690b0376ee36ebc8`.

Quincy đọc option runtime `rbd_qos_exclude_ops`, chấp nhận bitmask hoặc các tên `read`, `write`, `discard`, `write_same`, `compare_and_write`, rồi bỏ qua token-bucket QoS cho loại op đã chọn. Pacific không có option hay mask dispatch này và tiếp tục throttle các op theo limit hiện hành. Giá trị mặc định tương đương mask 0 nên không đổi hành vi nếu không cấu hình.

**Điều kiện và tác động:** khi đặt option ở global config hoặc image metadata, client Quincy và Pacific truy cập cùng image sẽ áp chính sách QoS khác nhau; latency/throughput và tải backend có thể lệch ngay trong mixed-client phase. Đây là thay đổi runtime client-side, không đổi dữ liệu. Evidence confidence **high** cho source/config, **medium** cho applicability.

**Full Quincy và rollback:** sau khi mọi consumer dùng Quincy, mask nonzero tiếp tục bỏ throttle cho loại op đã chọn; việc hết version skew không khôi phục giới hạn cũ. Ranh giới thay đổi là trước khi ghi config/image metadata và trước khi client áp effective mask. Để rollback chính sách, phục hồi mask hiệu dụng về 0 tại đúng scope đã thay, kiểm cả override image lẫn config và xác nhận client đã nhận lại chính sách; chỉ hạ một host không xóa metadata tồn tại để host Quincy khác còn đọc. Bypass đã gây burst/backend queue không bị thu hồi bởi config rollback, nên stop condition của lab là saturation/latency vượt ngưỡng đã đặt và phải đợi queue ổn định trước đo lại. Chưa có effective config hoặc số đo headroom để kết luận mức tải chấp nhận được.

**Kiểm chứng đề xuất:** chụp `ceph config dump` và metadata `conf_rbd_qos_exclude_ops`; trên image lab đặt limit thấp rồi lần lượt exclude từng op, đo IOPS/BPS và latency bằng client hai phiên bản. Giữ mask 0 trong rollout nếu chưa có capacity test cho hành vi bypass.

### RADOS-009 — `sparse_size` của RBD sparsify đổi từ `size_t` sang `uint64_t`

**CSV:** `src/cls/rbd/cls_rbd.cc`, `cls_rbd_client.{cc,h}` và `src/librbd/WatchNotifyTypes.h` (index 1577, 1579–1580, 2086). Commit chỉ có ở Quincy `72a5993da70955182a73755ddba35005a6d9fc11`.

Pacific mã hóa/giải mã tham số `sparse_size` của cls/rbd và `SparsifyPayload` bằng `size_t`, nên độ rộng phụ thuộc kiến trúc build. Quincy dùng `uint64_t` xuyên suốt client wrapper, object-class method và watch/notify payload. Theo commit, thay đổi tương thích ngược trên hệ 64-bit; mục tiêu là làm ổn định encoding giữa hệ 32-bit và 64-bit và tránh build không có dencoder phù hợp cho `size_t`.

**Điều kiện và tác động:** chỉ có đường tác động wire/ABI thực tế khi fleet hoặc artifact ngoài cây có build 32-bit/độ rộng `size_t` khác, hoặc khi custom consumer gọi trực tiếp chữ ký cls client nội bộ. Với x86_64/aarch64 64-bit thông thường, hai endpoint vẫn encode 64-bit và không cần chuyển dữ liệu. Trong mixed-client phase có kiến trúc lẫn nhau, Pacific có thể tạo hoặc chờ payload có độ rộng khác Quincy/OSD object class; kết quả có thể là decode thất bại hoặc sparsify không chạy như yêu cầu. Evidence confidence **high** cho kiểu dữ liệu và điều kiện kiến trúc, **low** cho applicability vì chưa có inventory kiến trúc/client ngoài cây.

**Activation và rollback:** chỉ lệnh sparsify explicit hoặc consumer gọi cùng API tạo payload này; upgrade không tự sparsify image. Full Quincy chuẩn hóa kiểu hai đầu thành `uint64_t`, nhưng consumer Pacific ngoài inventory vẫn có thể gửi payload theo kiến trúc cũ. Trước cho phép sparsify cần giữ image checkpoint và kiểm đường request qua lock owner/watch-notify lẫn cls trên OSD; khi đã sparsify, allocation/extent đã thay đổi không được phục hồi bằng hạ client hay cls. Hành vi mong muốn giữ nguyên byte đọc phải được đối chiếu hash, còn khả năng khôi phục layout phân bổ cũ không được bảo đảm. Với artifact 32-bit hoặc wrapper nội bộ chưa chứng minh decode chéo, giữ tác vụ chưa chạy; không dùng lời khẳng định tương thích 64-bit để mở gate cho kiến trúc khác.

**Kiểm chứng đề xuất:** inventory kiến trúc và binary phụ thuộc librbd/cls wrapper; tạo golden encoded payload trên build 32-bit và 64-bit cho cùng `sparse_size`, giải mã chéo bằng hai endpoint, rồi chạy sparsify trên object lab và kiểm extent/return code. Commit không kèm test mới; chưa chạy cross-architecture lab.

### RADOS-010 — Quincy bỏ tương thích libcryptsetup cũ khi tính LUKS data alignment

**CSV:** `src/librbd/crypto/luks/Header.cc` (index 2118). Commit chỉ có ở Quincy `8de47b212bafa38f73a4ceaadeecfe4b3dd53497`; thay đổi CMake cùng commit thuộc owner build/package và chỉ được dùng làm context ở đây.

Pacific còn nhánh `LIBCRYPTSETUP_LEGACY_DATA_ALIGNMENT`: với API cũ nó chia `data_alignment` cho sector size, còn API mới chia cho 512. Quincy luôn chia cho 512 và đồng thời nâng minimum build dependency lên libcryptsetup 2.0.5. Các sửa format/load và kiểm return code khác đã có ở cả hai endpoint dưới lineage backport khác, nên không được gộp vào finding này.

**Điều kiện và tác động:** ảnh hưởng có điều kiện cho custom/source build dùng libcryptsetup cũ hoặc quy trình đóng gói không thực thi minimum version; package Quincy hợp lệ phải thỏa dependency mới. Đường code nằm ở lúc format LUKS header, đặc biệt cần chú ý sector size khác 512; không chứng minh existing encrypted image cần migration. Trong mixed-client phase, chỉ client thực hiện format mới chịu semantics của thư viện mà nó được build cùng. Evidence confidence **high** cho source/minimum version, **medium** cho vận hành vì chưa biết package provenance và libcryptsetup version thực tế.

**Rollback boundary:** lệnh format là activation explicit có ghi LUKS header/data offset; điểm quay lại có thể kiểm soát là trước khi format, với image nguồn và vật liệu khóa được giữ theo quy trình của môi trường. Sau khi format, đổi libcryptsetup hoặc librbd về bản cũ không đổi header đã ghi và không khôi phục nội dung trước format; cần artifact đọc được header đó cùng khóa đúng, hoặc phục hồi checkpoint của cả image. Full Quincy bằng dependency hợp lệ loại bỏ nhánh legacy của client mới, nhưng không tự làm cho artifact Pacific/custom cũ mở được mọi ảnh vừa format. Chưa có image fixture, header dump hay cross-open/hash để xác nhận đường khôi phục cụ thể.

**Kiểm chứng đề xuất:** kiểm SBOM/package dependency và CMake cache của mọi custom librbd; trong lab format LUKS1/LUKS2 với sector size 512 và 4096 bằng artifact Pacific/Quincy được giao thực tế, ghi data offset, mở chéo và so hash dữ liệu. Không dùng image production cho phép thử format.

### RADOS-011 — `rbd info` bắt đầu hiển thị feature `dirty-cache`

**CSV:** `src/tools/rbd/ArgumentTypes.cc` (index 4144). Commit chỉ có ở Quincy `b2a8d13a1a4635aba0128adfdbc43a7aaf04504d`.

Pacific thiếu `RBD_FEATURE_DIRTY_CACHE` trong `ImageFeatures::FEATURE_MAPPING`, nên `rbd info` không hiện token này dù feature đã bật. Quincy bổ sung mapping. Thay đổi chỉ sửa bề mặt quan sát/parse của CLI; nó không tự bật feature và không đổi bit lưu trên image.

**Điều kiện và tác động:** chỉ áp dụng cho image đang có bit `dirty-cache` và automation/người vận hành đọc feature list từ `rbd info` hoặc help. Trong giai đoạn client lẫn phiên bản, cùng image có thể cho danh sách text/JSON/XML khác nhau; parser dùng allowlist cứng hoặc baseline output cũ có thể báo sai drift, trong khi readiness check mới có thêm tín hiệu đúng. Evidence confidence **high** cho output mapping, **medium** cho applicability vì chưa có script acceptance/SBOM của môi trường.

**Activation, mixed/full và rollback:** token tự động xuất hiện khi chạy CLI Quincy đọc image có bit này; không cần bật feature thêm. Mixed CLI tạo khác biệt bề mặt quan sát; full Quincy giúp mọi collector thấy token nhưng parser phải chấp nhận nó trước rollout collector. Rollback CLI hoặc parser chỉ thay cách hiển thị/diễn giải, không xóa bit và không flush dữ liệu dirty trong persistent cache. Giữ output gốc kèm phiên bản CLI để đối chiếu; nếu parser mới lỗi, có thể phục hồi parser đã kiểm với fixture mới, nhưng không dùng kết quả Pacific thiếu token để kết luận image sạch. Việc làm sạch cache cần workflow cache riêng, chưa được thực thi trong báo cáo.

**Kiểm chứng đề xuất:** trên image lab có/không có `dirty-cache`, thu `rbd info` plain/JSON/XML bằng cả hai binary; chạy parser acceptance hiện hữu với token mới và xác nhận chính sách stop/go không dựa vào việc Pacific vô tình ẩn feature. Chưa chạy CLI runtime.

### RADOS-012 — Compare-and-write đổi contract, giới hạn request, journal và cache coherence

**CSV:** bảy hàng `src/include/rbd/librbd.h`, `src/librbd/{Journal.cc,Journal.h,librbd.cc}`, `src/librbd/io/ImageRequest.{cc,h}` và `src/librbd/cache/ObjectCacherObjectDispatch.cc` (index 2028, 2080–2081, 2097, 2127–2128, 2136). Commits chỉ có ở Quincy gồm `2ecd52888b4`, `9eb2ddbde3749b0a740d86183ac92e2ce811765d`, `3016e16199e31ebcb09d11500f26cd010bc157ae` và `20c0a96ab96132fb86694b548edea84ffb88fa34`.

Pacific C++ API chỉ kiểm độ dài write buffer và có thể thực hiện compare theo toàn bộ compare buffer thay vì `len`; request còn bị giới hạn ở một sector. Quincy yêu cầu cả compare/write buffer dài ít nhất `len`, chỉ xử lý đúng `len`, cho phép request căn chỉnh tới stripe unit và tách compare/write payload lớn thành nhiều journal entry. Quincy còn bỏ trạng thái ObjectCacher chồng lấn sau khi compare-and-write thành công ở OSD; Pacific chỉ flush trước op nên cache writeback/writethrough có thể giữ dữ liệu cũ. C API Quincy đồng thời thêm symbol `rbd_aio_compare_and_writev`. Sửa iovec overflow, snap-context và discard/journal liên quan đã có ở cả hai endpoint dưới SHA backport khác nên không được gộp vào finding này.

**Điều kiện và tác động:** chỉ áp dụng cho consumer dùng compare-and-write; nhánh cache cần `rbd_cache_policy` writeback/writethrough, còn nhánh journal cần journaling bật. Khi tổng payload vượt giới hạn một journal entry, writer Quincy tách nó thành nhiều entry. Trong mixed-client phase, cùng image có thể nhận `-EINVAL`, phạm vi compare/write, mismatch offset và cache visibility khác nhau tùy client. Ứng dụng link symbol vector mới của Quincy không thể rollback chỉ bằng cách thay shared library về Pacific. Không có migration on-disk riêng. Evidence confidence **high** cho contract và control flow, **medium** cho applicability vì chưa có inventory tcmu/custom consumer, cache policy và journaling.

**Giới hạn coherence từ endpoint:** `ObjectCacherObjectDispatch::compare_and_write` gọi `discard_set()` trong completion thành công. Comment ngay tại hunk Quincy nói rõ khi read đang ở trạng thái RX, `release_set()` không invalidate đáng tin cậy còn `discard_set()` có thể điền extent bằng zero; tác giả chọn kết quả xác định hơn, không khẳng định đã xử lý đúng mọi racing read. Vì vậy phải thử read chồng lấn đồng thời và đối chiếu dữ liệu trả qua cache với read độc lập; bất kỳ mismatch/zero ngoài dữ liệu dự kiến đều là stop signal, kể cả op compare-and-write trả thành công.

**Activation và rollback:** contract/check cache tự động khi client mới xử lý op; vector API là opt-in qua consumer đã link symbol mới. Full Quincy thống nhất contract nhưng vẫn cần thử journal replay và cache race nói trên. Trước failback giữ cặp ứng dụng/librbd tương thích, quiesce op, flush cache và ghi nhận journal/replay position; chưa chứng minh cho phép client/replayer Pacific nhận mọi chuỗi entry được request lớn của Quincy tạo ra. Write đã commit và entry journal đã append không bị undo bởi hạ package; không xóa journal hoặc cache để né lỗi mở lại. Nếu kết quả dữ liệu sai, giữ evidence và phục hồi checkpoint ứng dụng đã kiểm thay vì dựa vào binary rollback.

**Kiểm chứng đề xuất:** chạy sync/async C++ và C API với compare/write buffer ngắn hơn, bằng và dài hơn `len`; thử request 512 byte, nhiều sector và đúng stripe unit, cả cache bật/tắt và journal bật/tắt. Sau op thành công đọc lại qua cache và client khác, so mismatch offset, return code, journal replay và dữ liệu. Compile probe dùng `rbd_aio_compare_and_writev`, kiểm symbol khi đổi thư viện hai chiều. Unit test repository đã được đọc nhưng chưa chạy.

### RADOS-013 — Quincy mất backport bảo vệ Python async mirror-info khi completion lỗi

**CSV:** `src/pybind/rbd/rbd.pyx` (index 3260). Backport chỉ có ở Pacific `0d32001b83002016fc5b3f411e5de4ff987fba10`.

Pacific gọi `get_return_value()` trong callback `aio_mirror_image_get_info`; chỉ khi completion thành công mới decode `c_info`, còn lỗi thì callback nhận `info=None`. Quincy 17.2.7 thiếu backport này và unconditionally gọi `decode_cstr(c_info[0].global_id)` rồi cleanup. Theo commit, khi client bị blocklist chẳng hạn, buffer không chứa kết quả hợp lệ và binding có thể truy cập bộ nhớ không hợp lệ thay vì báo lỗi sạch qua completion.

**Điều kiện và tác động:** cần automation Python dùng đúng API async mirror-info và request hoàn tất bằng lỗi; API đồng bộ và các đường list/status khác không tự động chịu cùng lỗi. Đây là regression theo chiều Pacific → Quincy ở package client, nên host Python nâng trước có thể crash hoặc hành xử không xác định trong khi host Pacific trả `info=None`. Không đổi metadata mirroring. Evidence confidence **high** cho endpoint/commit, **medium** cho vận hành vì chưa có inventory caller và fault history.

**Activation, mixed/full và rollback:** regression tự động ở callback lỗi sau khi process Python nạp binding Quincy; full Quincy daemon không bổ sung kiểm tra return value trong binding. Trong mixed fleet, cần pin riêng version của automation gọi API này. Rollback process yêu cầu bộ Python extension và librbd/librados khớp nhau, dừng job rồi nạp lại artifact đã kiểm; chỉ thay wheel/shared library dưới process đang chạy không phục hồi callback đã crash. API đọc info không tự sửa mirroring metadata, nhưng job đã dựa trên kết quả thiếu/sai hoặc chết giữa chuỗi hành động phải đối soát checkpoint và state thực tế trước retry. Chưa có caller trace nên không suy ra mọi job mirroring đều idempotent.

**Kiểm chứng đề xuất:** trên image mirror lab, gọi `aio_mirror_image_get_info()` bình thường rồi tạo lỗi có kiểm soát bằng blocklist/quyền/đóng image; ghi completion return, callback argument và exit signal bằng binding hai phiên bản dưới ASAN hoặc faulthandler. Không fault-inject trên client production.

### RADOS-014 — Quincy mất backport tránh deadlock `rbd-nbd` khi disable feature

**CSV:** `src/tools/rbd_nbd/rbd-nbd.cc` (index 4169). Backport chỉ có ở Pacific `68637d3e5e537d07a84ed112c01549f352f9e6fa`; workunit đi kèm nằm ngoài hàng finding.

Pacific chuyển việc gọi `image.size()`, resize NBD, rescan partition và invalidate cache sang thread riêng; callback update-watch chỉ đặt cờ và đánh thức thread. Quincy 17.2.7 thực hiện `image.stat()`/refresh trực tiếp trong callback. Theo commit, `DisableFeaturesRequest` phát update notification khi exclusive-lock path còn chặn refresh, làm `rbd-nbd` kẹt trong `ImageState::refresh_if_required()`. Các option Quincy-only như `--snap-id` và `--notrim`, cùng sửa block size LUKS2 đã có tương đương ở Pacific, không phải nguyên nhân finding.

**Điều kiện và tác động:** cần image đang map qua `rbd-nbd` và thao tác disable feature phát notification; resize notification cũng đi qua callback này. Nâng binary mapper Pacific lên Quincy có thể tái tạo hang ở control path, giữ process/device và I/O đang chờ; đây không phải format conversion. Mixed fleet chỉ mapper chạy Quincy chịu đường cũ. Evidence confidence **high** cho regression/commit, **medium** cho applicability vì chưa có inventory `rbd-nbd` và workflow disable feature.

**Activation và rollback:** đường callback tự động hoạt động trong mapper Quincy sau map/reattach; trigger disable feature hoặc resize là explicit. Full Quincy mapper vẫn có đường refresh trong callback, nên hết mixed fleet không loại nguy cơ này. Điểm dễ failback nhất là trước khi đổi mapper và trước lệnh đổi feature: giữ device/image mapping, cookie nếu dùng, feature set và checkpoint I/O. Khi mapper đã treo, hạ file executable không thay process; cần quy trình quiesce/unmap hoặc detach/reattach đã chứng minh cho host/kernel đó và xác nhận write đang chờ. Feature bit hoặc image size đã commit không tự quay về khi chạy mapper Pacific; re-enable/resize ngược là thay đổi riêng cần kiểm điều kiện, không được suy ra từ fix deadlock. Chưa có bằng chứng cho phép kill mapper đang có I/O mà không mất continuity.

**Kiểm chứng đề xuất:** map image lab, chạy I/O nền rồi disable lần lượt feature hợp lệ với timeout; đồng thời resize và theo dõi update-watch, thread stack, device size, partition rescan và I/O completion bằng hai binary. Xác nhận unmap/reattach vẫn phục hồi được; không thử disable trên image production đang phục vụ workload.

### RADOS-015 — Bộ đếm `rbd bench` không còn wrap sau 2^32 I/O

**CSV:** `src/tools/rbd/action/Bench.cc` (index 4147). Commit chỉ có ở Quincy `4a287e8fcd1`.

Pacific dùng `unsigned ios`; trên nền tảng thông thường bộ đếm 32-bit quay vòng sau 2^32 operation, kéo theo tổng ops và phép tính ops/sec cuối sai. Quincy dùng `uint64_t` và bỏ cast hẹp khi in tiến độ; help cũng nói rõ `io-size < 4G`, phù hợp kiểm tra runtime vốn đã có.

**Điều kiện và tác động:** chỉ ảnh hưởng benchmark rất dài hoặc I/O rất nhỏ đủ vượt 2^32 operation; dữ liệu RBD và I/O phát sinh không đổi. Tuy vậy output benchmark có thể là evidence acceptance/capacity, nên sau thay client kết quả dài hạn khác với baseline Pacific. Ở 100.000 IOPS, ngưỡng 2^32 xấp xỉ 11,9 giờ. Evidence confidence **high** cho overflow, **medium** cho applicability vì chưa có quy trình benchmark thực tế.

**Activation, mixed/full và rollback:** thay đổi tự động trong mỗi tiến trình `rbd bench` Quincy; không có option bật counter rộng. Khi mixed client tạo benchmark evidence phải ghi version từng binary và số op; full Quincy sửa phép đếm của lần chạy mới, không sửa log Pacific đã wrap. Rollback công cụ không cần chuyển counter vì counter chỉ sống trong process, nhưng quay về Pacific tái đưa overflow vào phép đo và không hoàn tác I/O write benchmark đã ghi. Giữ raw log trước/sau cùng tổng byte và duration để loại hoặc tính lại run cũ nếu đủ evidence, nếu không phải chạy lại trên image thử riêng. Kết quả counter chính xác hơn không phải bằng chứng backend nhanh hơn.

**Kiểm chứng đề xuất:** dùng harness/instrumented build đặt counter gần `UINT_MAX` rồi chạy qua biên, hoặc chạy workload lab đủ dài; đối chiếu progress, tổng ops và ops/sec. Không dùng `rbd bench --io-type write` trên image chứa dữ liệu cần giữ.

### RADOS-016 — Upstream iSCSI QA chuyển từ bare-metal package sang cephadm

**CSV:** mười hàng `qa/suites/rbd/iscsi/{0-single-container-host.yaml,base/install.yaml,cluster/fixed-3.yaml,conf,pool/datapool.yaml,supported-random-distro$/centos_8.yaml,supported-random-distro$/rhel_8.yaml,workloads/cephadm_iscsi.yaml}` và `qa/tasks/ceph_iscsi{,_client}.py` (index 960–967, 1345–1346). Commits chỉ có ở Quincy `cbd2c71398b`, `a7952949a87` và `9b306af4213`.

Pacific suite cài `tcmu-runner` và `ceph-iscsi` trực tiếp, dùng gateway/client role bare-metal và task `ceph_iscsi.py` để cấu hình gateway. Quincy bỏ task đó, dùng cephadm triển khai service iSCSI, thêm task `ceph_iscsi_client.py` chỉ chuẩn bị initiator/multipath, đổi role thành `ceph.iscsi.*`, bỏ pool/distro matrix cũ và chạy workload qua các client role mới. Đây là thay đổi bằng chứng kiểm thử upstream; các file QA không tự thay đổi daemon/runtime production.

**Điều kiện và tác động:** tổ chức đang nâng gateway iSCSI kiểu package/bare-metal của Pacific không thể coi suite Quincy này là bằng chứng trực tiếp cho in-place transition, rollback hay coexistence của mô hình cũ. Cấu hình suite định nghĩa đường triển khai cephadm ở endpoint mới nhưng để lại khoảng trống cho migration legacy, cấu hình multipath và gateway failover hiện hữu; source QA không phải kết quả chạy test. Evidence confidence **high** cho phạm vi suite, **medium** cho applicability vì chưa có inventory gateway/deployment mode thực tế.

**Activation, mixed/full và rollback:** phạm vi QA đổi khi explicit chọn suite Quincy; full Quincy deployed bằng cephadm không chứng minh đã kiểm mixed legacy/cephadm gateway. Task client còn ghi initiator IQN, nối thêm multipath config và restart dịch vụ, vì vậy ngay cả rollback test environment cũng cần snapshot config/service state riêng. Trước migration gateway cần lưu gateway config, target/LUN mapping, secret tham chiếu, initiator/multipath và deployment spec; chạy lại suite Pacific hay hạ package không phục hồi các thay đổi topology/config đã áp. Điểm rollback phải được đo trên cùng lab topology với đường I/O và target ownership rõ ràng; chưa có run result của suite nào trong bộ phân tích này.

**Kiểm chứng đề xuất:** inventory gateway Pacific đang chạy package hay cephadm, phiên bản `ceph-iscsi`/tcmu-runner, target/LUN/multipath và client initiator. Nếu có legacy gateway, dựng lab cùng topology, thực hiện chuyển sang cephadm hoặc upgrade được chọn, kiểm discovery/login, ALUA/multipath, I/O liên tục, failover, cấu hình REST/gwcli và rollback. Kể cả khi có một run suite Quincy PASS, vẫn cần evidence đúng topology và đường migration trước khi kết luận support production.

## Thay đổi trivial

262 hàng đã sàng lọc gồm tài liệu/man page, file PWL chỉ đổi namespace/logging/diagnostic, `rbd-mirror` thích ứng API mà không đổi replay, test/mock/example object class, namespace/include/constructor/parser/filesystem/argv/AdminSocket adapter tương đương và CLI chỉ thêm option/help/front-end/output không đổi default hoặc state. Batch mới chứng minh riêng QCOW chỉ thay hàm big-endian tương đương, trash move thay `erase_if` bằng `find_if` cùng predicate, WNBD chỉ đổi adapter/thông báo và header C++ compare-and-write chỉ thêm tài liệu. Đáng chú ý, các sửa iovec overflow, snap context mới, adjusted discard journal, LUKS2 block size và nhiều commit Quincy khác đã có logic tương đương trong Pacific dưới SHA backport khác nên không được quảng bá thành finding. Internal `Image::snap_set(namespace, name)` có hunk thật nhưng mọi production caller ở endpoint vẫn truyền `UserSnapshotNamespace`; vì chưa có đường kích hoạt non-user nên hàng đó là `trivial`. Lý do từng hàng nằm trong `impact_reason` của CSV.

## Kiểm chứng cần hoàn thành

- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.
- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.
- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.
- Binary gate đã đối soát đủ `58 affect + 262 trivial = 320`; tiếp theo là inventory As-Is và lab/canary cho các finding có điều kiện.

## Giới hạn hiện tại

Chưa có As-Is cluster hoặc lab/canary cho cặp endpoint. Không đưa GO/NO-GO production từ báo cáo đang phân tích này.
