# 12 — RGW, S3, auth/policy, bucket/object và multisite: v16.2.5 → v16.2.15

> **Kết quả:** đã đối soát đủ **237 dòng** do owner `12-rgw` sở hữu. Target chứa một security fix cho Browser POST policy (CVE-2023-43040), các fix tránh mất/corrupt object ở timeout và POST write failure, hardening bucket-index/reshard, multisite, IAM/STS, lifecycle/notification và Beast frontend. Hai gate mặc định tại lần restart RGW là Beast tắt SSLv2/3 và TLS 1.0/1.1 khi có certificate, đồng thời RGW yêu cầu kết nối MON `secure` với `cephx`; client cũ và cluster tắt CephX phải được inventory trước rollout.
>
> **Trạng thái kiểm chứng:** đã đọc endpoint diff, symbols, commit history, release note và test/QA trong repository. Chưa chạy S3 conformance, network fault injection, dynamic reshard, IAM negative tests, multisite failover hoặc TLS client matrix trên cluster thật; chưa có inventory frontend, tenant/policy, buckets, object-lock/versioning, lifecycle, notifications hay zone topology.

## 1. Phạm vi và ledger

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Base là ancestor của target; source tree non-shallow và sạch; net diff dùng `--find-renames` với Git `2.49.0.windows.1`.
- Inventory chi tiết: [12-rgw.csv](./12-rgw.csv). CSV có 237 dòng, giữ nguyên 21 cột nền của master inventory và nối 6 cột phân tích.
- Thống kê owner: `A21/D10/M203/R3`, `+10.433/-9.658`; `P1=141`, `P2=96`; một binary test asset.

Disposition cuối của 237 dòng:

| Disposition | Số dòng | Ý nghĩa trong báo cáo này |
| --- | ---: | --- |
| `conditional` | 16 | Runtime effect chỉ khi notification/LC/GC/FIFO feature hoặc failure path tương ứng hoạt động |
| `mixed` | 81 | File có cả hunk finding-relevant và thay đổi chức năng/refactor khác |
| `support` | 66 | Test, QA hoặc docs trực tiếp hỗ trợ finding |
| `trivial` | 74 | Đã sàng lọc nhưng không có causal chain nâng cấp độc lập |
| **Tổng** | **237** | Khớp chính xác CSV |

Không có dòng `material` vô điều kiện: mỗi risk cần API/feature/topology hoặc fault cụ thể. CVE-2023-43040 và write-integrity paths vẫn là gate nghiêm trọng khi Browser POST hoặc workload tương ứng tồn tại.

## 2. Kết luận dùng cho kế hoạch nâng cấp

1. **Inventory RGW theo traffic thực.** Ghi frontend/endpoint/TLS, S3 Browser POST, multipart, object versioning/lock, dynamic reshard, IAM/STS/Keystone/OPA, LC/GC, notifications, realms/zonegroups/zones và từng daemon sau load balancer.
2. **Ưu tiên security gate cho Browser POST.** Target lấy bucket thật của request làm authoritative sau khi đọc form fields; base cho form field `bucket` ghi đè policy environment. Nếu endpoint này được dùng, vá trước exposure kéo dài và rà access logs/policies theo incident process.
3. **Canary write integrity bằng checksum và read-back.** PUT/POST/multipart dưới timeout/network jitter phải xác nhận object body, ETag/version và tail/head consistency; HTTP error hoặc client retry alone không đủ chứng minh write thất bại hay thành công.
4. **Không reshard production để “test nhanh”.** Target sửa race có thể ghi vào shard đã decommission và cleanup racing deletes. Dùng bucket staging với concurrent PUT/DELETE/LIST; production chỉ tiếp tục khi index/stats/read-back hội tụ.
5. **Draining theo daemon là bắt buộc cho auth semantics.** IAM/STS/CORS fixes chạy trong từng RGW process. Trong mixed-version window, cùng request qua load balancer có thể nhận quyết định khác nhau; canary từng daemon rồi drain base nodes.
6. **Kiểm TLS và kết nối MON trước khi đổi pool.** Beast target mặc định `no_sslv2:no_sslv3:no_tlsv1:no_tlsv1_1`; client phải hỗ trợ TLS 1.2+ hoặc cấu hình được phê duyệt. RGW target còn mặc định `ms_mon_client_mode=secure` và `auth_client_required=cephx`; cluster cố ý tắt CephX cần xử lý có chủ đích trước lần restart. Không hạ security mặc định chỉ để qua smoke test mà không có quyết định riêng.
7. **Multisite pass/fail dựa trên data convergence, không chỉ `sync status`.** Target sửa cả allowed-zone filtering, log generation/trim và metadata retry. Đo lag, errors, bilog/datalog/mdlog và checksum/object versions giữa zones.
8. **`bucket check --fix` là repair operation riêng.** Target thêm OLH/unlinked checks và sửa nhiều edge, nhưng không ủy quyền chạy `--fix` đại trà trong upgrade window. Chạy read-only check trước, backup evidence và rehearse trên clone/staging.

## 3. Ma trận finding

| ID | Chủ đề | Điều kiện kích hoạt | Pha chính | Rủi ro khi kích hoạt | Confidence |
| --- | --- | --- | --- | --- | --- |
| RGW-001 | Browser POST bucket-policy validation / CVE-2023-43040 | S3 Browser POST signed policy | ngay khi endpoint base còn phục vụ | **Cao; security** | High |
| RGW-002 | PUT/POST/multipart durability và timeout | Write failure, network jitter, multipart/FIPS | canary/mixed traffic | **Cao; data integrity** | High |
| RGW-003 | Bucket index, reshard, versioned delete/list | Dynamic reshard hoặc concurrent object mutations | canary/post-upgrade | Cao | High |
| RGW-004 | Multisite data/metadata logs, status và sync policy | Multisite realm/zone topology | mixed zones/post-upgrade | Cao | High |
| RGW-005 | Notification, lifecycle, GC và FIFO workers | Feature tương ứng bật; reshard/failure path | post-upgrade | Trung bình-cao | High |
| RGW-006 | IAM/STS/auth policy evaluation | IAM/STS/Keystone/OPA/CORS in use | mixed daemons | **Cao; authorization** | High |
| RGW-007 | Beast TLS, secure MON defaults, timeout/shutdown và S3 surface | Beast/Civetweb, legacy TLS, CephX-disabled cluster hoặc timeout edges | pre/during rollout | Cao | High |
| RGW-008 | Bucket check/OLH/unlinked repair | Operator chạy admin check/fix | maintenance riêng | Cao theo thao tác | High |

Mức rủi ro là hậu quả khi điều kiện đúng; applicability cần inventory As-Is.

## 4. Phát hiện chi tiết

### RGW-001 — Target sửa Browser POST policy bucket override (CVE-2023-43040)

**Evidence.** Commit `479976538fe8f51edfea597443ba0c0209d3f39f` trong `RGWPostObj_ObjStore_S3::get_params()` di chuyển `env.add_var("bucket", s->bucket->get_name())` xuống sau vòng đọc form fields. [Release note chính thức của Pacific 16.2.15](https://ceph.io/en/news/blog/2024/v16-2-15-pacific-released/) map fix này tới CVE-2023-43040.

**Trước → sau.** Base đưa request bucket vào policy environment trước, sau đó một multipart form part tên `bucket` có thể ghi đè giá trị đó trước policy evaluation. Target ghi lại bucket thật sau parsing, nên form input không còn là authority cho condition bucket.

**Security boundary.** Chỉ Browser POST policy path bị chứng minh ở đây; không mở rộng sang mọi PUT/signature flow. Fix ngăn request mới nhưng không tự phân tích access logs, xóa object đã upload hay rotate credential. Quyền thực tế vẫn bị giới hạn bởi credential/policy khác, vì vậy incident scope cần log và IAM context.

**Mixed-version.** Mỗi RGW daemon tự parse/evaluate request. Khi load balancer còn base node, retry có thể rơi vào vulnerable node; security gate chỉ đóng sau khi mọi serving daemon đã target hoặc base nodes bị drain khỏi endpoint.

**Kiểm chứng.** Tạo policy hợp lệ cho bucket A, gửi request tới bucket B với form field `bucket=A` bằng credential test có quyền được kiểm soát; target phải reject theo expected S3 error. Chạy positive Browser POST tới bucket A và pin request vào từng daemon. Stop nếu bất kỳ serving base/target endpoint nào chấp nhận negative case.

**Đánh giá.** Rủi ro **cao, security**, confidence **high**.

### RGW-002 — Target tránh xóa tail data sau timeout và dừng POST ngay khi write filter lỗi

**Evidence.** `b1ef8f95eb533cb63695e54f11ce49d8b5e2a3cf` xử lý `-ETIMEDOUT` ở `AtomicObjectProcessor::complete()`: head write có thể thành công muộn, nên target clear danh sách tail objects khỏi destructor cleanup để tránh xóa data vẫn được manifest tham chiếu. Trade-off được code nêu rõ: nếu head không thành công, có thể để orphan thay vì corrupt object sống.

`387cc1b14afdf0adc3fae9090e27626d7bcb102a` làm `RGWPostObj::execute()` return ngay khi `filter->process()` lỗi; base vẫn tăng offset/tiếp tục flush và có thể hoàn tất một object thiếu data. Multipart path còn được sửa để writer dùng part head object (`5a98f505fc4176f02b26673a0ab863b60c1ed92e`) và ghi metadata part đúng pool (`f91364fca23ab57244a9af88afadee5107026a8b`). `13c3028a705ec1e7931b35cdc1fd436f56541851` tránh FIPS segfault khi tính multipart ETag cho previously-completed request.

**Trước → sau.** Base có hai causal chains data-integrity trực tiếp: ambiguous timeout có thể cleanup tails của successful-late head, và POST filter error có thể bị bỏ qua. Target ưu tiên bảo toàn referenced data và propagate error sớm.

**Giới hạn.** Timeout vẫn ambiguous cho client; target không biến retry thành exactly-once. Orphan possibility cần quy trình riêng, không được chạy cleanup tùy ý trong canary. FIPS fix cho MD5 dùng mục đích ETag, không phải thay đổi cryptographic policy chung.

**Mixed-version.** Daemon nhận request quyết định writer/cleanup behavior; client retry qua base và target có thể tạo version/ETag khác nhau tùy versioning/idempotency semantics.

**Kiểm chứng.** Trên bucket staging, inject latency/timeout quanh head commit cho PUT/POST/multipart; giữ request IDs, read-back full body, checksum, ETag, version listing và raw manifest/tail evidence. Test multipart complete retry và FIPS nếu áp dụng. Stop nếu successful response có checksum lệch, referenced tail mất, object body ngắn hoặc state retry không giải thích được.

**Đánh giá.** Rủi ro **cao, data integrity**, confidence **high**.

### RGW-003 — Dynamic reshard và concurrent delete/listing sửa nhiều index-consistency races

**Evidence.** `b11c10acc9026d92b90cfb88f6a3381274ccb9bc` thêm `assert_exists()` cho bucket index shard, coi `-ENOENT` như dấu hiệu reshard vừa hoàn tất, refresh bucket id và retry thay vì ghi vào shard đã decommission. `315981003ed5ccf2bc567e960a4d699e956e8d6f` đảm bảo index entry được remove sau khi cancel racing delete cuối; chuỗi helper trước đó truyền `remove_objs` cả ở cancel path. `1e575378b00fc2c8b56b09834276e68dddbb1385` sửa extra delete marker trong versioned bucket.

Target còn sửa non-ASCII/filtered ordered listing, reshard stats accounting, stale OLH entries, lifecycle crash trong reshard (`f5b2615caa7e8e2f93ee61d0158feb51d6a15c02`) và notification/index-completion ordering (`32f87a92565277110931c261e2ee34f5c11b3583`).

**Trước → sau.** Base operation giữ stale bucket info có thể complete vào old shard sau reshard. Target kiểm object tồn tại, refresh instance id và trả NoSuchBucket cho delete race; versioned delete/index cleanup cũng xác định hơn.

**Mixed-version.** Bucket index là shared state. Trong rolling window, target daemon có guards mới nhưng base daemon vẫn có thể dùng stale path; do đó reshard + heavy writes nên tránh trong mixed-version window nếu không bắt buộc.

**Kiểm chứng.** Trên staging bucket bật dynamic reshard, chạy concurrent PUT/DELETE/multipart/LIST với ASCII và non-ASCII keys, versioning on/off. Sau hội tụ so object listing với HEAD/read-back, bucket stats, shard instance ids và read-only `bucket check`. Stop nếu object có data nhưng mất index, index trỏ object mất, duplicate marker, stats lệch hoặc request tiếp tục dùng old shard.

**Đánh giá.** Rủi ro **cao theo reshard/concurrency**, confidence **high**.

### RGW-004 — Multisite thay đổi cả log generation, retry, status và sync-policy control plane

**Evidence.** `9d7a80b5901351fe769df974f336714e62712d7b` làm multisite data-logging flag thực sự điều khiển data log; `097d574ab3e0cf288118759cb8575655452fbb94` chỉ đọc `sync status` từ zones được phép sync. `46802213a28490d59bf6b546c0791382175d0fd9` giới hạn metadata-sync concurrency; `ed481ece74610a94a2cfc2280232e3daf82a0349` coi metadata sync errors là transient để retry thay vì dừng vĩnh viễn; `0fcda11d74db1f1e16da2c5e7e0611967a7e235c` đổi data sync sang bounded spawn window.

Control plane còn reject sync-policy group rỗng (`7e137287e6f86ff6095a48fe64323a11edc21daf`), tránh pipe modify crash khi thiếu zone params (`4563c6297d84128e99036e6c1bb517e5de989ce0`), forward delete bucket policy/public-access-block tới master (`56d5899a4f28988bbb15476d433487be5984b047`) và harden bilog/datalog trim (`b15e2c3c7a02de5b10d9e7521140af64d87bf853`, `25004d961fca0d99f67f80df9ffa3a321386cd06`).

**Trước → sau.** Base có thể báo status từ zone không hợp lệ, mất khả năng retry một số metadata error, log khi flag không yêu cầu hoặc crash ở admin/trim edge. Target làm selection/retry/validation rõ hơn.

**Giới hạn.** “Transient” không có nghĩa mọi error tự hết; persistent auth/network/schema lỗi vẫn tạo backlog. Status output đúng hơn không thay thế object/version checksum.

**Mixed-version.** Source daemon tạo logs, sync daemon tiêu thụ, master xử lý forwarded operation và admin command có thể khác version. Canary phải bao cả source/target zones; không chỉ nâng một zone rồi kết luận global.

**Kiểm chứng.** Chụp realm/period/zonegroup, allowed sync sources, policy/flow/pipe, mdlog/datalog/bilog markers, error shards và lag. Trong staging tạo object/version/delete/policy changes ở từng source được phép, xác nhận chỉ intended zones nhận, errors retry/hội tụ và trim không đi trước consumers. Stop nếu lag tăng không giới hạn, object/version/checksum lệch hoặc policy operation không tới master.

**Đánh giá.** Rủi ro **cao nếu multisite bật**, confidence **high**.

### RGW-005 — Notification, lifecycle và FIFO workers được harden nhưng delivery semantics vẫn cần canary

**Evidence.** `7abfaf086ba393959df15a684dabeddbb9ba188d` tránh persistent notification hang khi `ack-level=none`; `d59fe5c12d9e893179cb1c840120fbf50ca8b88d` làm notification không phụ thuộc bucket instance id sau reshard. `48f34daa188beeb3293e8929d231ca0885b712dc` chặn một bucket lifecycle vượt worker time budget; `f5b2615caa7e8e2f93ee61d0158feb51d6a15c02` tránh LC segfault khi reshard; `aa90cbdf74f4368aa6a989f35142110d8a57d5d1` dọn LC entry khi bucket bị xóa.

Legacy FIFO code thay đổi lớn: remove part tags, merge duplicate journal entries, serialize version update, fix `_prepare_new_head` race và retry push khi part chưa tồn tại (`c641dc66452d4f225a2dd845b414a1d146d5e4d6` đến `266522a031f4716903c00f8e598203efe543d4b0`).

**Trước → sau.** Target giảm worker hang/crash và queue races. Đây không phải guarantee exactly-once; notification consumer vẫn phải chịu retry/duplicate theo interface contract.

**Mixed-version.** RGW tạo event và notification worker/queue implementation có thể khác version; reshard trong mixed window tăng số state transitions cần kiểm. Lifecycle/GC là background, nên lỗi có thể lộ sau canary ngắn.

**Kiểm chứng.** Với feature đang dùng, gửi create/copy/multipart/delete events, test endpoint ack modes và reshard; theo dõi queue depth, retry, duplicate/lost event. Chạy lifecycle trên bucket staging với expired versions/multipart, đo progress và daemon stability; xác nhận GC convergence nhưng không ép trim trước retention. Stop nếu worker treo, backlog không giảm, event mất theo test oracle hoặc object bị expire sai.

**Đánh giá.** Rủi ro **trung bình-cao theo feature**, confidence **high**.

### RGW-006 — IAM/STS policy semantics thay đổi; mixed daemons có thể trả quyết định khác nhau

**Evidence.** `685cb25135be4fd39440026b764eac46f4535af3` consult user IAM policies khi object ACL/policy lookup trả ENOENT. `36d428be572ecf6fb7bc3cceb15489a1be323207` đánh giá identity policy không truyền identity như một Principal; `f4ab5e2e4a537cfb79ed062bb85acbb15a06111f` reject policy resource thuộc tenant khác; `7df41ea66e7f5a12c2c89837dfba9359e7c42698` trả lỗi khi Resource không hợp lệ thay vì âm thầm discard; `5ba1b947bee13bf0001a1f988990859a76c2b04e` đưa session policy vào CreateBucket authorization.

Chuỗi CORS/HTTP OPTIONS thay đổi canonical/auth handling (`2d78f81aae15efc8fd096e6edf8bf5bc679004fa`, `5b7b1526ca5c567f4f9766eaf416cd1d2ea2829f`, `34c71dadba01470d3dc6a2158b5dcab8ea2ab5fc`). OPA path tránh null dereference (`3cecb8862dc941f75644689c9cae21df8075a740`). STS còn bổ sung session tags/web identity condition support và sửa temporary-credential/copy paths.

**Trước → sau.** Target reject một số policy/resource trước đây bị parse bỏ qua, áp identity/session policy đúng context hơn và harden external auth backends. Đây là behavior change có thể biến request từ allow→deny hoặc ngược lại khi base behavior sai.

**Mixed-version.** Authorization diễn ra tại daemon nhận request. Load balancer phân phối giữa base/target có thể tạo nondeterministic 2xx/4xx cho cùng credential. Period/user metadata propagation cũng phải hoàn tất trước khi kết luận policy bug.

**Kiểm chứng.** Lập golden matrix allow/explicit-deny/implicit-deny cho user, role, STS session, cross-tenant resource, invalid Resource, CORS preflight và backend thực dùng. Pin cùng signed request vào từng daemon, kiểm status/error code và Cloud/audit logs. Stop nếu quyết định khác giữa target nodes, deny bypass hoặc policy hợp lệ bị drop không giải thích được.

**Đánh giá.** Rủi ro **cao, authorization**, confidence **high**.

### RGW-007 — RGW đổi TLS và MON-auth defaults, đồng thời harden timeout/shutdown

**Evidence.** `4d3b01dbc1b547f2d589420b3f27d6b59163ad7e` đặt Beast default `ssl_options` thành `no_sslv2:no_sslv3:no_tlsv1:no_tlsv1_1` khi có certificate và option không được khai báo. Trong `radosgw_Main()`, `5943bb5a94bb37429bf3c1bb9f15d69ad636002d` đặt `ms_mon_client_mode=secure` và `77d704ab057c35e26004fe0a09386054da5235a4` đặt `auth_client_required=cephx`; release-note hunk cùng commit cảnh báo cluster tắt CephX có thể cần điều chỉnh. `584cc66ee133a2a75b5ae1b4920b680d06ce4aee` thêm `max_header_size`, mặc định 16 KiB, tối đa 64 KiB thay cho limit 4 KiB.

Timeout implementation được refactor sang timer riêng; `671de0a3923831224655c76bb365b56494670b55` tránh concurrent socket-use segfault và `403c285a09fe50d0bf9daad033904ee9981c95d8` nhớ stream error để shutdown graceful. `93f31b70dfdd32a13ec3b170cccb89a153a14ff5` drain async request queue khi shutdown. Civetweb được đánh dấu deprecated trong Pacific (`0ec3be56d14da9d958f682a4d59f1e6d0886d264`).

S3 surface còn sửa truncated ListBuckets, DeleteMultiObj empty optional, content-length-range minimum, static website crashes và object-lock retention overflow. Các hunk này là correctness/stability, không phải wire-format migration.

**Trước → sau.** Legacy TLS 1.0/1.1 client có thể kết nối ở base nhưng fail handshake với target default. RGW base không ép hai override MON này, còn target yêu cầu secure messenger và CephX khi process khởi động; deployment cố ý dùng auth khác có thể không kết nối MON nếu không có cấu hình đã phê duyệt. Ngược lại, header hợp lệ 4–16 KiB có thể được target chấp nhận. Timeout/disconnect paths ít crash hơn nhưng proxy/client retry vẫn cần test.

**Kiểm chứng.** Export effective `rgw_frontends`, certificate, ciphers/options, `ms_mon_client_mode`, `auth_client_required`, trạng thái CephX, proxies và client TLS matrix. Pin TLS 1.2/1.3 positive tests; xác nhận intended rejection của TLS 1.0/1.1 và một RGW target restart có thể authenticate/kết nối MON. Test headers gần configured limit, slow upload, timeout, keepalive/100-continue và graceful drain under load. Stop nếu supported clients fail, RGW không kết nối MON, daemon crash, request bị double-complete hoặc shutdown bỏ request ngoài SLO.

**Đánh giá.** Rủi ro **cao theo frontend/client estate**, confidence **high**.

### RGW-008 — Target thêm bucket-check diagnostics nhưng repair vẫn là thao tác phá hủy có điều kiện

**Evidence.** `1c1569b66084754511f2933d2247d132cf6018b6` thêm `radosgw-admin bucket check olh` và `unlinked` cùng QA. Target sửa versioned bucket stat accounting (`d828c761a114138914eb6e0ab6e237b6c22c8059`), chỉ in object details khi có `--check-objects` (`c4a9aebb49a739a85c1b0787ca4097f258a54bcb`), stat calculation (`bf1a1956eadde7d81d0ca995ff8eebe87843d1e7`) và pool id khi `bucket check --fix` (`526da161a5d509056a02c832731e3a792c58d3c9`). `4817bcaf9d385cb60ef36373ac0262e466953994` tránh check xóa multipart meta index khi `pending_map` còn entry.

**Trước → sau.** Target quan sát được OLH/unlinked states và sửa một số false/unsafe repair edges. Điều này không chứng minh `--fix` an toàn cho mọi bucket state hay thay thế backup.

**Activation.** Không có effect chỉ vì daemon được nâng; finding kích hoạt khi operator chạy admin check/repair. Read-only output và repair mutation phải là hai change steps riêng.

**Kiểm chứng/hành động.** Trước hết chạy read-only check trên bucket staging có versioning/multipart/reshard history, lưu raw output và so listing/HEAD/stats. Rehearse `--fix` trên clone hoặc disposable data, kiểm object versions/OLH/multipart meta sau repair. Không chạy production `--fix` nếu chưa có object-level backup, peer/multisite impact analysis và rollback/restore procedure.

**Đánh giá.** Rủi ro **cao theo operator action**, confidence **high**.

## 5. Trivial/support changes

- **66 support rows** gồm RGW multisite/STS/reshard/bucket-check QA, unit tests và docs dùng để chứng minh tám finding; chúng chưa được chạy trong môi trường này.
- **74 trivial rows** gồm build/test topology, docs feature reference, logging/formatting, ancillary tools, refactor và hunk không có causal chain upgrade riêng.
- **16 conditional + 81 mixed rows** được map tới RGW-001…RGW-008 trong CSV. Một file có thể map nhiều finding nên không cộng số occurrence ID để suy ra row total.

Tổng `16 conditional + 81 mixed + 66 support + 74 trivial = 237`; mọi owner row đã có disposition và reason.

## 6. Validation matrix đề xuất

| Scenario | Tiền điều kiện / pha | Quan sát bắt buộc | Stop condition |
| --- | --- | --- | --- |
| Daemon/feature inventory | Trước rollout | frontend/TLS, APIs, policies, buckets, zones, workers | Còn endpoint/owner/topology không xác định |
| Browser POST negative test | Credential/bucket staging | target reject forged `bucket` form; positive still works | Bất kỳ serving node chấp nhận negative case |
| Write fault injection | PUT/POST/multipart staging | response, request id, body checksum, ETag/version, manifest | Successful response với data lệch/mất tail |
| Reshard concurrency | Dynamic reshard staging | instance ids, PUT/DELETE/LIST, stats, bucket check | Stale shard write, orphan index hoặc stat mismatch |
| Auth golden matrix | Pin từng daemon | allow/deny/error code cho IAM/STS/CORS/backend | Nondeterministic hoặc deny bypass |
| Beast compatibility | Client/proxy matrix | TLS version, header limit, timeout, graceful drain | Supported client fail hoặc daemon crash |
| Multisite convergence | Từng allowed source/target zone | log markers, lag/errors, versions/checksum/policy | Lag không hội tụ hoặc data/policy lệch |
| LC/notification/FIFO | Feature staging | progress, queue depth, delivery oracle, daemon health | Worker hang/crash, event mất hoặc expiry sai |
| Bucket repair rehearsal | Clone/disposable bucket | read-only evidence, OLH/unlinked/meta after fix | Object/version/multipart metadata bị mất |

Các scenario là thiết kế kiểm chứng; chúng không ủy quyền tắt TLS security, reshard/trim production, inject network fault vào traffic thật hay chạy `bucket check --fix` đại trà.

## 7. Giới hạn và kết luận

- Chưa có As-Is nên chưa biết Browser POST, legacy TLS, IAM/STS, multisite, dynamic reshard, lifecycle hay notification finding nào áp dụng.
- Tests/QA và release note upstream đã được đọc nhưng chưa chạy; không có benchmark latency/throughput hoặc live object checksum corpus.
- Security fix RGW-001 chỉ đóng hoàn toàn khi mọi serving daemon đã target/drained; log/object review vẫn là incident task riêng.
- RGW-002 ưu tiên tránh corrupt referenced data nhưng có thể để orphan ở ambiguous timeout; report không đề xuất orphan cleanup trong upgrade window.
- Chưa đủ bằng chứng môi trường để đưa GO/NO-GO Production; gate tối thiểu là daemon/feature inventory, Browser POST security test, write-integrity canary, TLS/auth matrix và — nếu dùng — multisite/reshard/worker validation.
