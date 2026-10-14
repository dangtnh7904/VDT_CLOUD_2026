# Validation status

**Rà bộ cài và storage monitor — 14/10/2026:** 21/21 unit mới nhất đạt trên Python 3.10 Windows và Python 3.12 Linux trong image pin Hub. Kiểm thật chỉ đọc readiness/fresh OSD metric 200/VALID, backup metadata đúng `source_project`, container/named-volume ID/nhãn khớp. Filesystem DB/evidence/executor dùng chung báo 6% (ngưỡng bảo thủ 7%), nhưng ổ host chứa VHD Docker C 90.40% và deployment/backup D 86.26%: report ALERT `HOST_DISK_HIGH`, không PASS dung lượng. Không xóa/di chuyển/compact dữ liệu, lab giữ 2 As-is/2 events và staging 6/6. Parser thiếu/sai số liệu hoặc container shape/ID lỗi fail-closed; backup project khác không xóa cảnh báo. README sửa `pull --policy always`, `curl --fail`, đường dẫn script backup và quyền Linux; Compose dry-run tái hiện skip trước sửa và có đủ ba image sau sửa. Scripts/docs này không nằm trong application image, không cần đổi digest RC hoặc gán source binary thành commit docs mới. Secret ownership trên host Linux mới và cài sạch host mới chưa được kiểm trong lượt này. [Biên bản](docs/PRODUCTION_ACCEPTANCE_STATUS.md).

**Chốt core staging/RC — 14/10/2026:** Hub `5.2.0-rc.1`, index `98994c2ae671d70613bb33bc3932dff1058af52b016b13e0767c4682b6ae1342`, source `d1d43a28a644f8d079dec48d3c280d8377525ea8`, đã pull/pin staging. Backend image Linux/PostgreSQL 446/446 và executor image Node22 42/42 PASS/0 skip; frontend 33/type/build đạt. Harness cuối 8/8: tải 40/40, p95 25.781s, error/429=0; pressure 12 caller sau shared admission 48/48; 3 fault cuối PASS/hash/audit giữ nguyên. Backup/restore cuối 6 As-is/audit/21 migrations/9 checksums PASS (restore11.466s). Hub SPDX/SLSA đúng revision/subject; Scout167/0 finding. Smoke Hub 7PASS/1NOT_RUN, tổng PARTIAL vì chủ động không tạo collection; không ghi thành 8/8. Giữ FAIL 38/40 đầu, chưa khẳng định source cause của hai partial. SSH authority lab, cert/telemetry/backup-policy/scheduler/alert/SLO/signing và host đích còn gate; **chưa nghiệm thu production**, không đổi tag cũ/latest/8080 hoặc `.env`/DB gốc. [Biên bản](docs/PRODUCTION_ACCEPTANCE_STATUS.md). Các checkpoint bên dưới là lịch sử.

**Kiểm sau khởi động lại Docker — 14/10/2026:** staging riêng HTTPS 8446 đã chạy; image sạch source `f5a573bfe7f2c50fde9a06552791972891c75ebb`, index `91c1540deb28447ef88b73059ce2017f3ea63ef0b2709934597f51867ff0e1c0`. Backend đóng gói Linux/PostgreSQL **444/444 PASS, 0 skip**, gồm DB grants, Linux process guard và lỗi DB/OCI. Smoke HTTPS/RBAC/actor/fresh metric/export/filter/comparison đạt 8/8. Fault executor/DB/API thật đạt; DB outage từng trả 500 plaintext đã sửa thành 503 DATABASE_UNAVAILABLE có budget 5s, lịch sử/audit không đổi. Restore riêng hai As-is/audit/schema21/9 checksum đạt 11.854s sau sửa lỗi PowerShell DateTime locale; monitor sửa ISO Z/7 fraction trên Python3.10 và ghi cảnh báo host disk >85% đúng thực tế. Tải 2×20 đang chạy. SBOM/provenance thật cùng source/subject/26 hashes đạt, Scout 167 package/0 findings; chưa publish/sign RC mới. CA chỉ localhost, secret Windows mode/SSH authority lab, scheduler/cảnh báo/retention/SLO/metric/cert đích và signing policy vẫn mở. **Chưa nghiệm thu production.** [Biên bản hiện tại](docs/PRODUCTION_ACCEPTANCE_STATUS.md) giữ các báo cáo FAIL trước sửa và giới hạn. Phần “chuẩn bị staging” kế tiếp là lịch sử trước khi Engine hoạt động.

**Kiểm mới nhất — chuẩn bị staging production, 14/10/2026:** source đã thêm multi-account RBAC, audit actor đã xác thực, DB grants audit append-only/collection không physical DELETE, telemetry diagnostics/FSID+MGR binding/redirect rejection, live window monotonic tối thiểu 15 giây, SSH forced-command guard và harness nghiệm thu. Backend **389 case: 364 PASS, 25 skip** (DB và Linux-runtime), frontend **33 PASS**, executor **31 PASS**, TypeScript/build/PowerShell parse và Compose staging merge đạt. OpenSSL CA→localhost leaf verify đạt. Một lượt unit ban đầu lỗi vì fixture bỏ qua wait làm monotonic Windows chưa sang tick mới; đã sửa fixture riêng, giữ report lỗi và chạy lại toàn bộ đạt, không bỏ assertion hoặc thay nguồn production để che lỗi.

SSH đọc trực tiếp xác nhận MGR active đổi host; endpoint cũ trả HTTP 200/0 byte, endpoint active trả HTTP 200/174600 byte với bốn counter I/O và 6 OSD. `ceph mgr services` cùng FSID khớp; config `mgr/prometheus/scrape_interval` tại thời điểm kiểm là 15 giây. Chưa xác minh mọi override/phiên bản hoặc xác định đủ toàn bộ metric bắt buộc của hệ thống đích.

**Staging HTTP thật FAIL, chưa nghiệm thu:** Docker Desktop lỗi `initializing Inference manager` ở `dockerInference`, chưa có pipe `dockerDesktopLinuxEngine`. Harness tại HTTPS 8446 ghi HTTP=null, `NETWORK_UNAVAILABLE`, không tạo collection. Config/CA/accounts riêng ở runtime đã chuẩn bị nhưng chưa có container chạy. Chưa chạy SQL grants thật, load/restart/restore mới, scheduler/alert delivery, build/push/sign/SBOM image mới hoặc kiểm Browser staging. `.env` localhost giữ nguyên SHA256. Xem [biên bản chuẩn bị](docs/PRODUCTION_ACCEPTANCE_STATUS.md); report runtime private không đưa lên Git. Các kết quả bên dưới là lịch sử của image cũ.

**Kiểm mới nhất — phát hành và cài sạch 5.1.2-rc.1, 14/10/2026:** image đã push/pin digest, code và bộ cài đã push trên nhánh `codex/console-5.1.2-rc.1`. Clone lại repo, giữ cấu hình riêng, xóa tài nguyên Console sau backup, pull lại image Hub rồi chạy README đạt sáu role/readiness/schema 21 và DB ban đầu rỗng. `.env`, profile, SSH key và secret gốc không đổi SHA; 13 container dự án khác giữ nguyên. Backend 319, frontend 31, executor 31, helper 26, worker/guard/diagnostics 43, TypeScript/SSR/build và app Scout đạt như [manifest RC](deploy/releases/5.1.2-rc.1.yaml). Browser đã lưu hai As-is mới MON+OSD, tải bộ B đúng SHA API, lọc/so sánh riêng osd.2 và đọc mới đúng hai daemon trong trang metric với danh mục 14 daemon vẫn giữ nguyên. **Tải JSON so sánh bị quyền trình duyệt chặn, kể cả sau xác nhận bằng văn bản; chưa xác nhận tải được và không tính PASS.** Worker security/stability và nghiệm thu production toàn bộ vẫn chưa đạt. Những mục dưới đây là lịch sử.

**Lịch sử kiểm local preview — 14/10/2026:** localhost cập nhật `5.1.2-preview.1`; 319 backend test với PostgreSQL không skip và 31 frontend test + TypeScript/build đạt. Đã thử hủy hai HTTP observations thật rồi đọc MON mới: 200, 9,432 giây. Collection MON + hai OSD còn nguyên SHA; lọc OSD xuất hai OSD, exact osd.2 xuất một. Mười kiểm tra render component SSR cũng đạt, không thay cho Browser. Sau khi người dùng mở lại tab truy cập được, **đã kiểm trực tiếp Browser**: xem/xuất mới đúng MON + OSD đã chọn, xem OSD trong collection hỗn hợp, tải bản lọc chỉ osd.2, cảnh báo thu gọn và so sánh hai bộ theo đúng osd.2 đều đạt. Hai tệp JSON đã tải vào Downloads, có checksum; không thấy lỗi đầy hàng chờ hay JavaScript trong lượt này. Vẫn 5 collection/19 events và SHA gốc không đổi. [Manifest mới](deploy/releases/5.1.2-preview.1.yaml) giữ ảnh/checksum/phạm vi. Preview chưa đăng Hub; đây không phải kiểm tải dài hạn hoặc nghiệm thu production toàn bộ. Kết quả release cũ bên dưới là lịch sử.

**Lịch sử phát hành Hub (13/10/2026): app 5.1.1-rc.1 và worker preview.2 đã phát hành Hub; localhost tại thời điểm đó chạy đúng digest release.** [Manifest Hub](deploy/releases/5.1.1-rc.1.yaml) · [Kịch bản demo](docs/DEMO.md). Kết quả release nằm ở [mục phát hành demo/lab cuối tài liệu](#phát-hành-demolab-511-rc1--13102026); các mục preview/RC cũ ở dưới giữ nguyên như lịch sử, không mô tả deployment hiện tại.

## Report integration đầy đủ chẩn đoán — 13/10/2026

Đã thay logging chỉ ở bước tamper bằng report schema 2 cho mọi HTTP request/create/worker path: named stage, status/code, envelope, decode/validation, exception type/code/status/errno, duration, source sequence và trạng thái storage. `failure_context` chỉ gắn service/capability của đúng request; transport chưa có HTTP ghi null, diagnostic phụ lỗi không che lỗi gốc. Có bản sao source theo SHA cho các report mới, không sao chép body/header/env/SQL/exception text. [Hướng dẫn đọc report](docs/INTEGRATION_REPORTING.md).

26 unit tests (9 guard + 17 diagnostic), bốn lỗi chủ động tạo và integration thật 38/38 đạt. Map hỏng qua worker thật trả 409 `OSDMAP_TOOL_FAILED`, envelope `ok=false` và storage không đổi, dù lỗi xảy ra ngay create đầu trước tamper. Capability stale, transport và non-JSON response cũng giữ đúng ngữ cảnh. [Report lỗi mẫu](deploy/dist/integration-reporting-20261013/failure-corrupt-map-with-sources.json) · [Report PASS](deploy/dist/integration-reporting-20261013/success-with-source-snapshots.json) · [Manifest](deploy/releases/integration-reporting-20261013.yaml). Report lịch sử không đổi; lỗi lịch sử vẫn OPEN. Không đổi image/cấu hình localhost trong lát cắt chỉ sửa runner này.

## Điều tra lỗi integration lịch sử — 13/10/2026

[Báo cáo điều tra](docs/INTEGRATION_FAILURE_INVESTIGATION.md) đã khôi phục script gốc đúng SHA và lệnh chạy cũ. Lệnh lỗi chỉ mất 8,005 giây, nên không phải timeout 90 giây; worker trước đã dừng và spool worker sau riêng. 20 replay đạt 38/38 (7 cold starts, 15 có trace, 5 không bọc API), chưa tái hiện lỗi. Ba fault controls cho capability/tool/OSError đều làm script gốc thất bại cùng assertion sau 32 bước nhưng nhận mã HTTP khác nhau. Chúng là lỗi chủ động tiêm để chứng minh report cũ thiếu khả năng phân biệt, không phải nguyên nhân lịch sử được xác nhận.

Đã bổ sung logging capability/envelope/decode/source sequence/thời lượng/no-save trong script hiện hành, bắt buộc marker tamper khi xét PASS. Guard 9/9 và integration diagnostic mới 38/38 đạt. [Manifest điều tra](deploy/releases/integration-rootcause-20261013.yaml) giữ hashes/report/DB synthetic archive; report lỗi đầu không đổi. **Nguyên nhân nền của lượt đầu vẫn UNCONFIRMED, stability OPEN**. Localhost/image/Ceph không đổi trong lần điều tra này.

## Bản sửa localhost 5.1.1-preview.2 — 13/10/2026, Asia/Saigon

Đã sửa ba lỗi xác nhận được: A/B bị xóa khi đổi bộ lọc lịch sử, cảnh báo dung lượng thiếu diễn giải làm UI báo không có cảnh báo, và checkbox daemon bị kích thước ô nhập văn bản. [Manifest bản sửa](deploy/releases/5.1.1-preview.2.yaml) giữ digest `sha256:44c809d6ebc46c66e43152b746ba167e83fbbcebfa6f905bcd79c21f0c395c84`, source hashes, report integration và checkpoint. Localhost đang dùng app preview.2; worker vẫn `16.2.15-minimal-preview.2`. Các mục bên dưới là lịch sử, không ghi đè report lỗi hoặc dữ liệu kiểm cũ.

20/20 frontend test, TypeScript và build local/trong image đạt. 61 backend case liên quan đạt (capacity telemetry/decision 8, As-is/history/OSDMap/security 42, release safety 11). Lần gọi release-safety theo module package ban đầu lỗi import sibling fixture; chạy đúng unittest discovery `-s tests -p test_as_is_release_safety.py` đạt 11/11. Đây là điều chỉnh cách chạy test, không thay production code để che lỗi. Test ngưỡng 67/68/70%, NORMAL, ghi chú vận hành và pool ngoài scope kiểm đúng state/reasons; capacity service SHA `575dc26aa38158a95e94ade395e0cc79122d03159ea2025dd1e05a25d94fe7c9` khớp image.

API–worker–PostgreSQL thực chạy trên DB riêng `osdmap_synthetic_20261013_fix`, network internal/spool evidence synthetic, worker khởi động từ dừng. **38/38 đạt**, hai row hợp lệ được lưu, marker `tamper_injection_executed=true`, kết quả bị sửa hash trả 503 `OSDMAP_RESULT_IDENTITY_MISMATCH` trước save. Report `deploy/dist/bugfix-20261013/integration-preview2-current-diagnostic.json`, SHA `fd06a51af6de15460f2b9a49f6113f37dfbfd71155713562c6538fdeb26e5f1d`; script SHA `61f6d1e497b924ed4c92c37dcba31ef3dbd3da90af441c4b443585ffd4b0de6a`. Lỗi đầu lịch sử chưa tái hiện được hoặc có root cause; gate vẫn OPEN. Service synthetic được dừng sau kiểm, evidence giữ riêng.

Browser đã tái hiện mất A/B trên preview.1, sau reload preview.2 chọn A ở Trước/B ở Sau giữ được cặp qua ngày/tìm kiếm, so sánh ba RGW thành công. Đổi loại daemon xóa cặp/kết quả đúng; checkbox đo 16×16 px trong DOM. [Ảnh giao diện](runtime/comparison-fixed-20261013.png). **Kiểm tải file trên browser lượt này bị chặn do quyền tải xuống bị từ chối; không kiểm bằng browser khác hoặc công cụ khác để vượt chặn.** Test checksum/export dùng synthetic đã đạt, không ghi bước tải browser là PASS.

Backup DB riêng trước swap, SHA `17592eb26df7991cfede82741e7785ae76b1d38899dcd1978c3488670fabfd30`, trong `runtime/local-bugfix-20261013` có ACL hạn chế. DB container/volume/schema 21, bốn collection cùng SHA/deletion state/tám events và cả chín evidence files path/size/SHA giữ nguyên. Mọi SSH/config/secret/state mount khớp container trước; giữ container trước với suffix `before-v5-20261013-151203`. Năm service mới chạy không restart/OOM, readiness/read-only đúng và worker heartbeat/parser/tool SHA hợp lệ. Các POST ghi vẫn bị chặn 403. Docker Hub/production-test giữ nguyên; app mới chưa scan lại, worker còn ba vendor-affected và production chưa nghiệm thu.

## Đổi cấu hình localhost lab — 13/10/2026, Asia/Saigon

Đã đổi **localhost 8080** sang app `5.1.1-preview.1` + worker `16.2.15-minimal-preview.2` theo digest trong [cấu hình local](deploy/local-images.preview.json). Chỉ lab/chỉ đọc, không push Hub hoặc thay production-test 8443. [Biên bản](deploy/releases/localhost-20261013-preview.yaml) giữ phạm vi, digest, rollback và smoke evidence; các kết quả RC1/preview.1/preview.2 bên dưới là bằng chứng lịch sử, không bị ghi đè.

Backup PostgreSQL custom trước migration/recreate, SHA `453ad31ca9af87f18bb05a34cccf7b9a9cbafdbba4e05f30c2e23ea46117c805`, đọc TOC đạt; chưa restore rehearsal riêng checkpoint này. Thư mục `runtime/local-preview-switch-20261013` có ACL riêng, không đưa DB dump vào image/repo/Hub. DB container/volume giữ nguyên, schema 21/không pending migration. Bốn collection cùng IDs/SHA/deletion state/tám events và tám file evidence cũ cùng path/size/hash không đổi. Mọi mount DB/evidence/SSH/config/secret/state so với container cũ khớp; container RC1 giữ dừng với suffix `before-v5-20261013-135150` để rollback, không xóa volume.

Năm service mới đang chạy, không restart/OOM tại lần kiểm, UID 10001/rootfs chỉ đọc/cap-drop ALL/no-new-privileges. API chỉ bind `127.0.0.1:8080`; worker network-none/CPU 1/RAM 1536 MiB/PIDs 32/chỉ spool. Readiness 200, schema 21, runtime version mới/read-only đúng; mutation/lab/legacy tắt. Capability available/parser 2/version/tool SHA đúng. POST body rỗng vào benchmark/RBD/Apply/upgrade đều 403 `CONSOLE_READ_ONLY`; thiếu header CSRF ở observe cũng bị chặn trước nguồn.

Smoke chỉ đọc qua SSH thật: observe `mon.ceph-master`/`osd.2` mới có FSID đúng, window 13:54:29–13:54:37 UTC+7. Quality **PARTIAL** do CPU/RAM orchestrator nguồn cũ được báo STALE; không giả dữ liệu thiếu thành VALID. Không tạo As-is collection mới. Preview offline no-op `osd.2`, weight `0.029296875`, pool 13 trả epoch 3888/1 PG/0 thay đổi, map ứng viên không lưu hoặc áp dụng; export SHA khớp header. Đây không phải kiểm failure-domain hoặc mọi tình huống live/site.

Browser hiện `v5.1.1-preview.1`; chọn hai RGW collection cũ, so sánh ba daemon và tải JSON thành công. File 10.795 byte có SHA `08a5340cd95b83532c1003b0c1ca24bc951310e96a53950c8da97ed0e28240a3`, trùng export trước swap. Production-test API ID/trạng thái dừng giữ nguyên. **Local lab smoke không đóng stability review OPEN của lượt synthetic lỗi đầu hoặc gate production NOT_PASSED; ba vendor-affected vẫn còn.**

Kiểm cuối: cấu hình pinned khớp cả năm service đang chạy; tám file evidence cũ vẫn nguyên, chỉ thêm một artifact preview offline hợp lệ (tổng chín file). Readiness/version/read-only tiếp tục đạt. Ba manifest preview/local parse được; **20 checksum artifact được tham chiếu khớp**. Không thay các report/hash lịch sử để đạt kiểm tra.

## Worker minimal preview.2 — 13/10/2026, chưa phát hành

Đã build `storage-lab-osdmap:16.2.15-minimal-preview.2`, index `sha256:baf1c9e802990b88c8910bbb94a45bb80f8de9ec5f0b5eada0dd6076e6a8d893`, bằng flag build `STRIP_PACKAGE_MANAGER_EXTRAS=true`. Gỡ thật 13 package quản lý qua dependency solver, không xóa file để che scanner/giả RPM DB. Giữ 103 RPM headers (trial preview.1 là 101; build mới thêm hai package locale khi update glibc), RPM query/chown/Python, ba Ceph ELF pin và 22 closure entries. 25 hash checks (3 ELF + 22 dependencies) đạt; glibc lên `2.28-251.el8_10.48`, libxml2 lên `2.9.7-21.el8_10.10`. Default worker RC1 và hai tag thử trước không bị thay.

Scout index 133 package: raw **1 Critical / 21 High / 35 Medium / 2 Low / 0 unspecified**. Compressed image báo 80 MB, lớn hơn preview.1 66 MB do update/layers; không tuyên bố image nhỏ hơn chỉ vì bớt package. Scan explicit Ceph SBOM vẫn 0 findings, không phải chứng nhận an toàn mọi mã Ceph. Đối chiếu 22 Critical/High còn lại: **12 vendor-fixed / 3 vendor-not-affected / 4 CNA-rejected / 3 vendor-affected**. Critical vẫn là CVE SQLite đã bị CNA rút; ba affected còn lại là OpenSSL `CVE-2026-84782`, PCRE2 `CVE-2026-103111`, Expat `CVE-2026-77214`. Không suppress/waiver hoặc đổi số raw scan.

17/17 worker test đạt; ba differential scenario cùng map RC1 đạt canonical SHA `b5dad984d27f13ff56b1c093222dc6ceb106f830af29217828b35332457742d5`. API–worker thật–PostgreSQL synthetic có **bốn lượt liên tiếp đạt 38/38** sau bổ sung response diagnostics. **Lượt đầu lỗi ở kiểm tra tampered identity sau 32 bước; response lỗi chưa được ghi ở lúc đó, nguyên nhân chưa tái hiện/xác nhận.** Giữ nguyên report lỗi, không thay bằng lượt PASS; truy vấn DB của lượt lỗi xác nhận chỉ hai artifact hợp lệ, không lưu kết quả thứ ba sai identity. Các lượt sau nhận đúng 503/`OSDMAP_RESULT_IDENTITY_MISMATCH`, không save. Stability review của lượt đầu vẫn OPEN, vì vậy không promote từ các lượt chạy lại.

Đã siết guard riêng của script synthetic: reject query/fragment libpq có thể override host/DB, user/port khác và các `PGHOST/PGDATABASE/PGSERVICE/PGOPTIONS` cùng biến override liên quan; thực hiện trước mở app DB pool. **9/9 guard unit tests đạt**. Không giảm bảo vệ hoặc sửa DB connection config của ứng dụng production. Phiên bản script dùng cho các report replay này có SHA `41d1f80589e41e8a9183ec268386a17ddce06063616509a998acbbf9bfb3830e`; report preview.1 phía dưới vẫn là bằng chứng lịch sử của script cũ và URI test đã được scope đúng. Marker diagnostic được thêm sau đó không được coi là đã chạy lại trong các report lịch sử này.

[Manifest preview.2](deploy/releases/osdmap-16.2.15-minimal-preview.2.yaml) giữ digest, SBOM/scan/hash, report lỗi và bốn report PASS, cùng gate OPEN/NOT_PASSED. Tại thời điểm kiểm thử này Hub/localhost/production-test/Ceph vẫn nguyên; lần đổi localhost theo yêu cầu riêng ghi ở mục mới phía trên. Cần giải quyết ba affected và stability/live-site acceptance trước quyết định phát hành hay chạy production.

## Nối API–worker thật và đối chiếu vendor — 13/10/2026

Đã chạy [script integration](packaging/osdmap/test_api_worker_integration.py) với API/middleware/service/repository thật của image local `5.1.1-preview.1`, worker thật `16.2.15-minimal-preview.1` và PostgreSQL 16 schema 21 trên DB riêng `osdmap_synthetic_20261013`. Spool/evidence volumes đều tách biệt, worker network=none/non-root/read-only/cap-drop ALL/no-new-privileges/CPU1/RAM1536MiB/PIDs32; client chỉ ở network test internal, DB không publish host port. Script bắt buộc marker opt-in, host `postgres`, DB prefix `osdmap_synthetic_*`; auth chỉ tắt ở synthetic lab có guard, không sửa deployment production. Nguồn Ceph là adapter trong bộ nhớ giới hạn đúng ba hành động đọc; map, FSID, epoch, pool tên/ID và OSD IDs đều từ cùng map tạo offline. Không đọc SSH key, gọi executor thật hoặc kết nối Ceph lab.

**38/38 kiểm tra đạt**, hai kịch bản no-op/nhiều weight tạo hai DB row và hai artifact có checksum thật. Kiểm: handshake strict của worker; 201/create; fresh-read action sequence; thiếu header CSRF/foreign Origin/Apply bị chặn trước nguồn; artifact bền vững giữ map nguồn; export attachment/hash và không thêm lần đọc nguồn; đổi epoch giả lập chỉ làm GET báo stale, không đổi artifact/export bytes; thiếu capability/sai binary/NaN/stale heartbeat fail closed; fault injection vào identity của kết quả worker thật trả 503 trước lưu DB/artifact. Mọi job UUID do script tạo được dọn, source fixtures không đổi. Không phải thử nghiệm TLS/auth production hoặc live-cluster acceptance. Report `deploy/dist/api-worker-smoke-20261013/report/integration.json`, SHA `184f1db6ba865c11fb14570aa2e9f64c425dce32d5776d6cd27529d0f8fbe665`; bản ghi synthetic giữ riêng trong DB/volume kiểm thử.

[Đối chiếu bảo mật](docs/OSDMAP_SECURITY_TRIAGE.md) kiểm 29 finding Critical/High bằng đúng installed RPM/source package/epoch, đúng RHEL8 product/component và RPM EVR semantics: **15 vendor-fixed, 5 vendor-not-affected, 4 CNA-rejected, 5 vendor-affected**. Đây là evidence triage, không thay số scan gốc 1 Critical/28 High/40 Medium/6 Low, không tạo VEX/suppression/waiver. Bản ghi Critical SQLite đã được CNA rút, không được diễn giải như lỗ hổng Critical còn chưa vá đã xác nhận. Năm vendor-affected còn lại thuộc GnuTLS (hai), OpenSSL, PCRE2 và Expat; chưa có bản vá phù hợp được xác minh cho đúng component đang cài. Medium/Low và mọi đường mã Ceph/dynamic backend chưa được miễn trừ bằng bảng này.

Tại thời điểm kiểm thử synthetic này Hub/localhost/production-test chưa được thay; schema/profile/SSH/dữ liệu Ceph không đổi. Worker **vẫn chưa được nghiệm thu production**. [Manifest local](deploy/releases/5.1.1-preview.1.yaml) thêm checksum report/triage và gate synthetic PASS; trạng thái local hiện tại ghi riêng ở mục đổi cấu hình phía trên. Các kết quả trước đó ở dưới được giữ làm lịch sử, không ghi đè raw scan hay nguồn.

## Nhánh local chưa phát hành — 13/10/2026, Asia/Saigon

Đã hoàn tất kiểm tra phần sửa dở sau RC1. Ứng dụng local `storage-lab-console:5.1.1-preview.1` có index `sha256:8fee0b7383ceb64a4b464ff0dadaad7f8fc6b52a9f132d42eb83123b60eea3cc`. Backend OSDMap bắt buộc handshake đúng version/commit, parser 2, replicated/crush_weight và hai tool hashes đã pin; kiểm identity/phạm vi pool của kết quả trước artifact/DB save, cờ ok boolean và error code có giới hạn. Saved evidence cũ không bị sửa hoặc chặn đọc theo handshake mới. Source service SHA-256 `d43931a85927dcd8341a82e20b04a70e15fe0705f9690d110ce075636d033543` khớp file trong image. Đây là integrity contract, không xác thực mật mã một worker có thể đã bị xâm nhập.

Full backend **296/296 test đạt, không skip** trên PostgreSQL 16 cô lập, giữ `CONSOLE_READ_ONLY=true` ở ENV container. Lượt đầu có 4 lỗi do fixture lab kế thừa ENV chỉ đọc; đã sửa factory test_config/test_health và hai lab fixture security để policy lab/auth được khai báo rõ. Production fixture vẫn read-only và tests 403/CSRF/auth không đổi; không giảm bảo vệ trong app hay deployment. Source/image app không bị sửa để che lỗi fixture. Scout 1.20.4 index 167 package app, 0 findings ở mọi mức đã báo cáo.

Worker thử nghiệm `storage-lab-osdmap:16.2.15-minimal-preview.1`, index `sha256:452ba2b9b3e4c1660b5e1e89a45b0d2a8aba6190d4d0bfa84d058403b147cff5`, dùng UBI8-minimal pinned `sha256:9ba99bcb387bdb7203f6d778a081950832a5fc500824431d10ec9d3ceacf949f` và update/install từ repo UBI. Chỉ ba ELF được lấy từ donor Ceph pinned: osdmaptool/crushtool giữ hash RC1, `libceph-common.so.2` SHA `e6a4768ebf2e3836c7d38258840b27620bb0ea6bf1070fe90be635ce899462b9`. Closure kiểm 22 dependency entries/114 RPM owners thật; không copy OS lib cũ hoặc tạo RPM record giả. License/source và SBOM Ceph trích file được giữ trong image.

**313 unit/integration cases chạy ở lát cắt này:** backend 296 + worker 17. Cùng 17 worker cases chạy thành công trên RC1 để giữ baseline. Thêm **3 differential scenarios** cùng map tạo offline (no-op, hai weight, upmap no-op) cho canonical JSON giống nhau, 104.600 byte, SHA `b5dad984d27f13ff56b1c093222dc6ceb106f830af29217828b35332457742d5`. Mọi placement, primary, CRUSH bytes, effective weights, choose_args và quality diagnostics được so. Chỉ dòng stdout cố định thông báo đường dẫn tạm xuất CRUSH được chuẩn hóa; hash stdout gốc không bị giả thành giống nhau và raw worker JSON/stdout vẫn lưu riêng dưới `deploy/dist/minimal-worker-preview-20261013/compatibility/`. Không dùng map hoặc credential Ceph thật trong thử nghiệm này. Frontend/executor/collector không đổi ở lát cắt này; số test 20/25/26 trong RC1 bên dưới là bằng chứng lịch sử, không phải lượt chạy lại hôm nay.

Full image scan worker index 144 package, **1 Critical / 28 High / 40 Medium / 6 Low / 0 unspecified**, giảm từ RC1 9 / 333 / 1333 / 481 / 18. Đây là raw scanner findings, không tự đồng nhất với lỗ hổng đã xác nhận. Scout báo SQLite `CVE-2026-51302` là Critical/Not Fixed, nhưng [bản ghi CNA chính thức](https://cveawg.mitre.org/api/cve/CVE-2026-51302) đã **REJECTED ngày 31/07/2026**, lý do không phải vấn đề bảo mật; [SQLite upstream](https://www.sqlite.org/cves.html) cũng ghi nhóm sáu ID liên quan không phải bug/tái hiện được. Không gọi đây là “đã vá” hoặc sửa raw scan/checksum; cần đối chiếu feed và các finding khác, không tạo waiver/VEX/suppress để vượt gate. Explicit Ceph component SBOM có 2 package, scan không phát hiện CVE nhưng không chứng minh mọi mã EOL/dynamic backend đã an toàn. Full SPDX scanner cũng nhận ceph-base/librados2 được trích; không chỉ scan base hay suppress findings. Báo cáo/SBOM/closure nằm ở `deploy/dist/minimal-worker-preview-20261013/`, checksum ghi trong [manifest local](deploy/releases/5.1.1-preview.1.yaml).

**Tại thời điểm kiểm thử preview.1 chưa publish/promote/cập nhật deployment:** Hub và localhost 8080 còn RC1; production-test 8443 không thay đổi. Lần đổi local theo yêu cầu riêng ghi ở mục mới phía trên. Dockerfile RC1/default image/env vẫn nguyên. Nhánh minimal là prototype, gate production **NOT_PASSED**, còn CVE và site acceptance. Không thay giao diện So sánh, schema, SSH hoặc dữ liệu Ceph. [Hướng dẫn thử riêng](docs/OSDMAP_PREVIEW.md#runtime-tối-giản-thử-nghiệm-chưa-phát-hành) ghi cách build/test độc lập. Kết quả RC1 dưới đây là lịch sử deployment đã phát hành.

## Bản phát hành chỉ đọc 5.1.0-rc.1 — 12/10/2026, Asia/Saigon

Đã build, push lên Docker Hub, kiểm tra tag qua Docker Hub API/registry và kéo lại theo digest bất biến. Ứng dụng: `dang7904/storage-lab-console:5.1.0-rc.1`, index `sha256:36b6b7b1664958b792dda841cf7140ab9e0006d3aff436d8b8823056451c86f4`, manifest linux/amd64 `sha256:8a32c445ed2fc2c5068b0c7095133d5e9937da0c7de09f6a829de8948b59a993`, build `2026-10-12T15:20:33Z`, schema 0021. Helper 1.0.5 giữ SHA-256 `66e8d8199c1060e11ef34a6f75e475b567e5c752e782945be8c709b1f0884d79`. Image mặc định chỉ đọc, không chứa SSH private key, cấu hình riêng hay dữ liệu cụm của lab. Kiểm tra vệ sinh nội dung runtime đọc 1.039 file, không phát hiện các nội dung bị cấm đã kiểm.

Worker tùy chọn: `dang7904/storage-lab-osdmap:16.2.15-rc.1`, index `sha256:65025d1fb24e90b87ec623b805946bcc6252bce43f8bfd198e70d6ef2a63cdad`, manifest linux/amd64 `sha256:ba0eb4888890ed23770d21e3d79e72cab96269d8bff29f2f91769a86e2c7b15e`. Parser 2 chỉ chấp nhận pool replicated và thao tác CRUSH weight có kiểu/giới hạn rõ ràng; từ chối EC, pool/PG ngoài phạm vi, dữ liệu map sai và FSID không khớp. Kết quả tách raw/up/acting, kiểm tool/map hashes và cảnh báo mapping thiếu/undersized; không tuyên bố đã chứng minh failure-domain. Worker UID 10001, root filesystem chỉ đọc, network=none, không nhận Ceph credential/config; không có Apply hay ghi map lên cụm.

**Security gate không đồng nhất giữa hai image.** Docker Scout 1.20.4 kiểm đúng RC1 ngày 12/10/2026: ứng dụng có 167 package, 0 Critical/High/Medium/Low/unspecified. Worker nền Pacific có 651 package, 9 Critical, 333 High, 1.333 Medium, 481 Low và 18 unspecified; **chỉ LAB/OFFLINE, không được nghiệm thu production và mặc định tắt trong cấu hình production**. SBOM, báo cáo và hashes nằm trong `deploy/dist/dockerhub-5.1.0-rc.1/`, được ghi chính xác trong [manifest phát hành](deploy/releases/5.1.0-rc.1.yaml). Không có ngoại lệ bảo mật hoặc chứng nhận production toàn bộ từ việc push image.

374 test đạt, không bỏ qua: backend 292/292 trên PostgreSQL 16 cô lập (bao gồm migration 0021, checksum, keyset 215 collection, soft-delete/restore, allowlist và source schema); frontend 20/20 cùng TypeScript/Vite build; executor/SSH 25/25; collector 26/26; worker 11/11 với osdmaptool/crushtool thật. npm audit runtime executor không phát hiện lỗ hổng. Vite còn cảnh báo kích thước chunk, không phải lỗi build. Đã sửa timestamp nguồn cũ/tương lai, số không hữu hạn/schema sai, so sánh giá trị không hợp lệ, ngày kết thúc 9999, quyền đọc collection theo allowlist hiện tại, stale response/double-click, phân trang lỗi và export stream có trần 16 MiB + SHA-256 bắt buộc.

Smoke production riêng `slc-v51-production-smoke` ở loopback HTTPS 8445 đạt: TLS 1.3 với CA/certificate được kiểm, HSTS/nosniff/CSP/no-store, chưa xác thực trả 401, ready có xác thực trả 200/schema 21, mutation/benchmark/Apply và CSRF không hợp lệ trả 403. API non-root, read-only, drop ALL capabilities; DB runtime role không có quyền superuser/DDL. Không cấu hình SSH vào Ceph trong stack smoke; stack production-test 8443 có sẵn không bị thay đổi.

Backup/restore kiểm thử thành công với schema 21, 21 migration checksums, 6 archive hashes, 1 evidence link/file và 2 As-is payloads (gồm 1 bản xóa mềm). Report: `deploy/dist/v51-production-smoke/backups/restore-schema21-asis-20261012/restore-report.json`; source_modified=false, restore DB network=none. Dữ liệu này được sinh riêng cho smoke, không phải nghiệm thu RPO/RTO của môi trường đích. Script backup/verify không còn hard-code schema 19 và giữ dữ liệu/volume nguồn.

Localhost 8080 đã thay bốn service app và worker bằng RC1; DB/evidence volumes và cấu hình SSH riêng được giữ nguyên. `/api/ready` ready=true, không có migration chờ; capability worker có version 16.2.15/parser 2/replicated. Smoke đọc MON/OSD/RGW thật xác nhận source schema, môi trường SSH PARTIAL được ghi đúng; không nâng cấp daemon hoặc thay Ceph weight/flag/map/data. Browser sau reload hiển thị `v5.1.0-rc.1`, lọc RGW, so sánh A `145fce08` với B `8d09923c` đủ 3 daemon và không tính delta từ nguồn STALE. Đã tải thật `C:/Users/Dang/Downloads/so-sanh-comparison (2).json`, 10.795 byte, SHA-256 `08a5340cd95b83532c1003b0c1ca24bc951310e96a53950c8da97ed0e28240a3`; ảnh [giao diện RC1](runtime/v51-rc1-comparison-20261012.png).

Sau nghiệm thu đã dừng riêng ba container `slc-v51-production-smoke` và DB fixture `slc-v51-test-db`, sau khi xác minh nhãn project/scope. Không xóa container, volume, cấu hình hoặc báo cáo; localhost 8080 và production-test 8443 vẫn chạy.

Đây là **release candidate chỉ đọc**, chỉ build linux/amd64. Nghiệm thu production tổng thể vẫn PARTIAL: worker CVE, signing, môi trường Ceph thứ hai cùng digest, offline distribution rehearsal, telemetry request/session/latency RGW/MDS và A0 đa host còn thiếu. Giới hạn thu đồng bộ 128 daemon/16 MiB và import lịch sử session cũ chưa được giải quyết. Hướng dẫn dùng/cấu hình/cập nhật nằm trong [README phần code](../README.md) và [README triển khai](deploy/README.md); plan mục 21–22 ghi rõ phạm vi và gate còn lại. Các mục dưới đây là lịch sử, không phải trạng thái image đang chạy.

## Lịch sử localhost v5.1 preview.4 — 12/10/2026, Asia/Saigon

Image đang chạy: `storage-lab-console:5.1.0-preview.4`, index `sha256:791bcd7775b1fef69b4ab86b24d2419f4e6801a09f2b86d7184da8660a0021b2`, build `2026-10-12T14:22:15Z`. Schema giữ 0021, không có migration mới. Worker offline giữ `16.2.15-preview.2`. Helper SSH và bundle image cùng version 1.0.5, SHA-256 `66e8d8199c1060e11ef34a6f75e475b567e5c752e782945be8c709b1f0884d79`; helper cũ có bản sao `collect_osd.py.before-1.0.5-20261012` trên SSH client host. Bốn service local đã thay image, containers trước đó và mọi volume DB/evidence giữ lại. Stack production-test và Docker Hub không bị cập nhật.

`/api/ready` trả ready=true. Giao diện đọc 14 daemon thật: 3 MON, 2 MGR, 6 OSD, 3 RGW; 10 daemon/trang. RGW lọc được, chọn cả ba, lưu và tải As-is qua browser. MDS được hỗ trợ qua FSMap/orchestrator; lab thật không có MDS: observe MDS trả 0 daemon, FSMap epoch 1, nguồn VALID, filesystems/standbys rỗng. Fixture active/standby MDS đạt nhưng chưa nghiệm thu MDS đang chạy thật. Schema daemon nguồn sai và timestamp cache tương lai bất hợp lệ bị đánh không khả dụng, không giả dữ liệu mới.

Môi trường As-is ghi `SSH_CLIENT_HOST_ONLY`: ceph-master, Ubuntu 22.04.5 LTS, kernel 5.15.0-198-generic x86_64, Python 3.10.12, shell khai báo /usr/bin/zsh, NTP bật và synchronized=true. Ceph **client** thực tế là 17.2.9, không bị thay bằng phiên bản daemon/worker 16.2.15. Chất lượng môi trường PARTIAL vì probe/tool version chưa đầy đủ; không cài thêm tool hoặc suy ra offset/PASS toàn cụm.

Collection RGW BEFORE `145fce08-867e-5691-9d73-89d0a46ee086`, payload SHA `1831fb94d925d5457cd241128ca62e9e551f7947449661f8a323a61398e6a36b`; AFTER `8d09923c-4a7c-55a9-9fa9-35c47f933518`, SHA `2a76d78d1f645867dcbe0790a3e811e8e04c47d5dea33100dffa3872edfe8a1a`. Đều là nhãn kiểm thử, không thực hiện nâng cấp. Collection AFTER đã xóa mềm qua API, xem lại với include_deleted=true, khôi phục và kiểm SHA không đổi. Comparison qua browser có cả 3 RGW, không tạo delta số từ mẫu CPU/RAM STALE. File As-is tải thật `collection-da-luu-145fce08-867e-5691-9d73-89d0a46ee086.json`, 60,887 byte, file SHA `3396931015a00231bd7882f18260fa72f6c3c706a28f94f0a4c6c7f5e868486e`; so sánh tải thành `so-sanh-comparison (1).json`. Screenshot thực tế `runtime/v5-preview4-rgw-comparison-20261012.png`.

Lịch sử API dùng keyset `(started_at,id)`, mặc định 10 dòng/trang, tối đa 200 **mỗi trang**, next_cursor/has_more và filter binding. Fixture kiểm đủ 215 collection có cùng timestamp, không bỏ/trùng bản ghi sau 200. Truy vấn PostgreSQL live limit=1 đã đi từ trang một sang trang hai đúng ID/has_more. Search/filter chạy trên server; UI giữ A/B và lựa chọn qua trang. API thiếu X-Console-Request/Origin đã bị CSRF gate từ chối như thiết kế; kiểm thử local có header hợp lệ không cần giảm bảo vệ.

Kiểm thử: backend 273 tổng / 257 qua / 16 DB-fixture-dependent bỏ qua; frontend 14 qua, TypeScript và build image Vite qua; executor/SSH 25 qua; helper 26 qua và kiểm grammar Python 3.6. Worker không thay đổi, 4 test tool thật đã qua tại lát cắt preview.3. Còn giới hạn job progress/128 daemon/16 MiB, telemetry RGW/MDS request/session/latency, A0 toàn host, import hồ sơ cũ và production gate trong plan mục 21. Các kiểm thử console chỉ đọc Ceph, chỉ thêm/quản lý dữ liệu cục bộ của console.

File so sánh RGW có 10,795 byte, SHA-256 `08a5340cd95b83532c1003b0c1ca24bc951310e96a53950c8da97ed0e28240a3`. Adapter dùng [cấu trúc MDSMap Pacific 16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/mds/MDSMap.cc#L94-L106) và [lệnh đọc FSMap/Orchestrator](https://docs.ceph.com/en/pacific/api/mon_command_api/); timestamp cache được giữ riêng, không coi request orch mới là daemon sample mới.

## Lịch sử nghiệm thu v5.1 preview.3 — 12/10/2026, Asia/Saigon

Current application: `storage-lab-console:5.1.0-preview.3`, index `sha256:4f25f26149db507dd2e2241c79617f5bd82e8b21fcc40cb8bf6c2e0ea7c023ab`, built `2026-10-12T13:36:42Z`, schema 0021, embedded OSD collector 1.0.4. Offline worker: `storage-lab-osdmap:16.2.15-preview.2`, index `sha256:bfe2bf1d39577dbe7433d680470581f877783c06c54b459bf4696418fa013c93`; network none, UID 10001, read-only filesystem, no Ceph credentials.

Verified `/api/ready` and the Vietnamese main navigation. Retired benchmark and dry-run routers are absent; the executor refuses retired benchmark actions before SSH. The four prior local services were retained stopped/disconnected, with database/evidence volumes preserved. Database dump before migration is `runtime/slc-before-v5-20261012.dump` (1,030,232 bytes); pg_restore listed 364 TOC entries. Only additive migration 0021 ran.

Real FSID `17c77e12-a16a-11f1-838e-cf68e9c001d8`: fresh reads produced 3 MON, 2 MGR, 6 OSD, with 10 daemon rows per page. Browser selection of osd.2 persisted to page 2, then osd.5 was selected. Collection `1fe9b81f-a22a-56d9-ba8e-6e1c77ebc9a2` captured MON + OSD2/5, BEFORE; collection `0da0f164-301e-579f-b62d-39aeed75e733` captured OSD2/5, DURING. Both were test-labelled observations, not upgrades. A/B comparison worked in reverse phase/time order with date/type filtering. Soft deletion + restore of the first retained source SHA-256 `748fecb9c191857151b5c471f5dcc1aef159976480e2d51141b626e1412ec2be`.

Actual browser downloads: `collection-da-luu-0da0f164-301e-579f-b62d-39aeed75e733.json` (964,465 bytes, file SHA-256 `c4966c323a80adc1ce76866f36ab4db4250660372ae12ed66324a0c8835fd8c2`), `so-sanh-comparison.json`, and prediction JSON. Fresh deep observation with collector `as-is-1.1` captured 267 PG rows and one choose_args group; both CRUSH/PG source statuses VALID. Overall PARTIAL correctly reflects missing/stale optional metrics; A0 coverage states remaining gaps.

Real pool 13 prediction changed PG 13.0 acting `[0,2,1]` to `[0,5,1]` for OSD2 weight 0 / OSD5 weight 0.029296875; acting primary stayed 0 while raw primary changed 2→5. Worker verified fixed-point effective weights and choose_args hashes, reported weight-set synchronization. Prediction `a3189efd-528f-4ae8-a864-d5798bc418d3` used epoch 3826 with final epoch 3826 and verified every MON effective weight-set setting true / MON version 16.2.15. An earlier 3825 prediction opened at epoch 3826 visibly warned that its source map was old. No Ceph map/config mutation was issued by console tests; cluster check showed HEALTH_OK, 6 up/in OSD and 267 active+clean PGs.

Tests: backend 259 total / 243 passed / 16 DB-fixture-dependent skipped; frontend 13 passed plus TypeScript; executor/SSH 23 passed; offline worker 4 passed with real osdmaptool/crushtool no-op and multi-weight fixtures. Live PostgreSQL CRUD/compare/delete/restore and browser downloads were separately checked. Preview limitations remain in plan section 21; Docker Hub and the separate production-test stack have not been updated to v5.

## Historical v3 SSH-key read-only configuration — 2026-10-12

The prior localhost image was `storage-lab-console:3.0.0-ssh-readonly-preview.1`.
Local index ID: `sha256:f827b5ca52a8dba8dc8e10a753eab82901a613afe10101652984bf2caa412d37`;
AMD64 manifest: `sha256:aef560e552815792b2b981e4921d19731089fdea52f37306f007cb31fd6a755b`.
It includes collector 1.0.4 and schema 20; the published rc.1 image is unchanged.

Verified existing SSH key authentication to dangg@10.20.20.11, pinned the trusted
host fingerprint, and checked FSID `17c77e12-a16a-11f1-838e-cf68e9c001d8` before
configuration. Installed the user-owned collector without granting sudo Python.
The new opt-in collector mode uses fixed `sudo -n ceph` commands only. Updated
Pacific pool aliases and OSD-map UUID fallback based on actual read evidence.
Fixed PostgreSQL UUID JSON serialization found during real inventory persistence.
ZIP machine-readable members now omit pretty-print whitespace; the existing
16 MiB, row/node/depth limits, redaction and checksums remain enforced.

API readiness/executor dependency passed. Live Ceph performance returned FRESH
cluster/OSD samples from the verified MGR Prometheus endpoint. Saved cluster
snapshot `c934ab33-6fb6-50d1-ba6b-470130c9e229` includes 3 MON, 2 MGR, 6 OSD,
3 hosts and 12 pools. OSD baseline `18d94d48-7588-443f-bfd5-37ba0cff044a` is
COMPLETE/VALID (all six OSDs), HEALTH_OK, epoch 3812, 267 PGs; artifact SHA-256
`54f12f0c640a70cddf7ee2aa786b3847dec8e6676bdef4a92850899498ac1d39`.
Failed and inconclusive attempts remain preserved.

Browser verified saved inventory and downloaded a real ZIP to Downloads, not
just a simulated export. Download SHA-256:
`5c01f2d26137f3e0fed4484b7cafe1da0e213c53ff85735cf3b22763b88c3ad3`;
five checksum-listed members verified. Full backend discovery ran 275 tests:
251 passed, 24 DB-dependent tests skipped (TEST_DATABASE_URL not configured).
Node executor suite: 28 passed. Standalone collector: 14 passed.

This is live read-only inventory acceptance, **not** live benchmark acceptance,
full A0 coverage, a capacity admission PASS or production certification. Mutation,
fio/Warp runner and write flags remain disabled. Capacity is observe-only and
its protected-pool proof remains incomplete. Existing DB/evidence volumes and
stopped prior containers were retained; no Ceph placement/flags/data were changed.
See [local SSH setup and usage](docs/LOCAL_SSH_READONLY.md).

## Configurable fio/Warp, Start/Stop and saved results — 2026-10-12

The local preview at `http://127.0.0.1:8080/#view=benchmark` now serves
`storage-lab-console:3.0.0-benchmark-preview.1`. Its local image index ID is
`sha256:76466e1c330f1f47139cf8f96e5f7ba0a9b30c2bd9035f1c052a2f875a7a8fbd`;
Linux AMD64 manifest is
`sha256:617e68bd43ef5768f9f60347353e5f7556a5a0aecc55af8432bac1e9b06e6030`.
The image version command reports schema 20 and runner protocol 1; bundled
helper SHA-256 is
`eb701c3d7e5871bb1127a380f619fef3f7ff2d805202b04edd39a552aa7df908`.
This local preview has not replaced the published Docker Hub rc.1 tag.

Implemented typed editable fio/Warp profiles, immutable saved runs, profile
cloning, fresh live preflight, target-digest binding, Start/Stop, durable Linux
supervisor ownership, PostgreSQL intent/attempt/result persistence, and status
reconciliation after page/API restart. The UI exposes measured job/operation
windows, partial/failed/stopped states, and export of saved results. fio uses
source JSON timestamp/runtime and completion-latency units; Warp uses operation
TSV and labels GET setup PUTs. No merged percentile or synthetic metric is used.

Verification passed:

- Backend full suite: 271 test cases on a dedicated PostgreSQL acceptance DB,
  with both TEST_DATABASE_URL and DATABASE_URL pointing only to that DB. All
  cases passed, including schema 0020 migration and capacity locking. The final
  benchmark-focused suite passed 15 cases after the preflight UI detail change.
- Frontend: 15 tests, TypeScript type check and container Vite build passed.
  Vite retains the existing bundle-size warning; it is not a build failure.
- Node executor: 27 tests passed, including closed benchmark fields, pinned
  helper digest, disabled-start policy and stop after write flags are disabled.
- Linux helper: 6 tests passed in a network-isolated Docker container. They
  cover closed profiles/argv, actual fio/Warp output schema and units, live
  placement/versioning/quota fixtures, target-change refusal, definite no-launch
  failure, and stopping a fake child while preserving partial results and an
  unrelated process. No Ceph workload was used in these tests.
- Browser: the new version is visible; fio randrw/write mix/I/O depth and Warp
  mixed/object bytes/concurrency fields were exercised. Performance ZIP export
  completed in the in-app browser and saved to Downloads. ZIP members include
  manifest, summary, records, report and checksums; quality remains UNAVAILABLE
  because this preview has no cluster credentials. Download SHA-256:
  `d85d34c4ab735dddd8c1f5997a809303f1ad0974f2387242d7f79f99cb241d01`.
- Local `/api/ready` reports ready with schema 20. A Start request is rejected
  with 403 CONSOLE_READ_ONLY. An untrusted Origin is rejected with 403
  CONSOLE_CSRF_REJECTED. Local CORS_ORIGINS was corrected to include port 8080,
  resolving a browser-only export rejection found during QA.

Before migration, the preview database was backed up in ignored runtime storage:
`runtime/backups/local-preview-before-benchmark-20261012.dump`. SHA-256:
`95c1b28af625dc246b1bd50544a040592b5ab8afaaecd536a17a58646ab35353`.
pg_restore read its archive listing successfully. Original database/evidence
volumes remain attached. Earlier API containers remain stopped and retained;
their older builds require a compatible database schema before rollback. The
separate production-test HTTPS stack was left unchanged.

Live Ceph/fio/Warp acceptance remains NOT_RUN. Local writes/runner are disabled
and read-only is true. Running in a lab requires installing the bundled helper
and pinned tools on the SSH host, configuring dedicated assets, credentials,
placement/ownership and quota/headroom, then enabling the lab flags described in
[the usage guide](docs/EXPORT_AND_BENCHMARK.md). RGW quota caching can overshoot;
it is not a strict byte guarantee. Pause/resume, automatic cleanup, raw runner
stdout download and PG/SLO attribution remain unsupported. No production-ready
or live benchmark performance claim is made by these local tests.

## Docker Hub publication — 2026-10-12

Published the `linux/amd64` lab candidate
`dang7904/storage-lab-console:3.0.0-rc.1` to the public repository
[Docker Hub](https://hub.docker.com/r/dang7904/storage-lab-console). The registry
index digest is
`sha256:2b2ca753cde297b4d00d013d2c249c5a9a7d6bcdb9a2e2dac70a39c5c2a9d0b5`;
the Linux AMD64 manifest digest is
`sha256:f4d28922d323df29aacb723e5f7839e68878d341b91045feda65324f37e1a190`.

Registry inspection, Docker Hub tag API verification, digest-pinned pull and the
image `version` command passed. The image reports app `3.0.0-rc.1`, schema `19`
and collector `1.0.2`. Candidate API readiness/schema, frontend/SPA routing and
unknown API 404 checks passed against the local preview PostgreSQL. The focused
config/health/legacy API suite passed 28 tests and executor suite passed 20.
Runtime content scanning and `pip check` passed. Temporary smoke containers and
volume were removed; existing localhost deployments were preserved.

Docker Scout indexed 271 packages and reported 85 findings: 2 Critical, 16 High,
15 Medium, 49 Low and 3 unspecified. The production security gate is
`NOT_PASSED`; no clean-scan claim is made. The local SPDX/report files and hashes,
published ref and remaining environment acceptance are recorded in
[`deploy/releases/3.0.0-rc.1.yaml`](deploy/releases/3.0.0-rc.1.yaml).
The coordinated FastAPI/Starlette and multipart update required for patched
Python dependencies remains a follow-up release, rather than an untested change
to this published tag. Live PA2 and two-environment acceptance remain `NOT_RUN`.

Usage instructions are in [`code/README.md`](../README.md), section 7. The
release cluster-profile example was corrected to contain only supported fields;
`resolve_settings` validated the supplied example successfully.

## Unified image and release deployment checkpoint — 2026-10-09

This checkpoint validates the I0–I2 implementation on the local Docker runtime.
It is not a published release, a second-environment acceptance, or evidence of a
live Ceph upgrade.

### Build and runtime identity

- Built `linux/amd64` image `storage-lab-console:3.0.0-dev` from
  `code/rgw-console/packaging/Dockerfile` with the deny-all build context in
  `code/.dockerignore`.
- Local image/content ID:
  `sha256:7a57e266598f258e082bce0684c69aa8eb6aace6e715aa3dd6afda514499939d`;
  size `131852027` bytes; default user `10001:10001`.
- The Python, Node and frontend base images are pinned by digest. OCI labels
  record application version, source revision and build time. `version` reports
  DB schema `19`, config schema `1`, collector `1.0.2` and collector SHA-256
  `7ce07463cb5cc7d3a5d71c17030d7049286d88a824a4b3dfb82b265be9dfb470`.
- The same image dispatches API, worker, performance/capacity collectors,
  lifecycle worker, executor, migrate and version roles. An unknown role exits
  `64`; canonical/legacy executor-token conflicts also fail closed.

### Automated, database and container checks

| Check | Result | Evidence |
|---|---|---|
| Backend with PostgreSQL | PASS | All 213 tests passed with `TEST_DATABASE_URL` and `DATABASE_URL` set to an isolated PostgreSQL 16 instance; no PostgreSQL integration test was skipped. Fresh migrations `0001`–`0019` and `migrate --check` reached schema `0019`. |
| Frontend | PASS | 6/6 contract tests passed and Vite production build completed (1842 modules; bundle-size advisory only). |
| Node executor | PASS | 20/20 tests passed, including fail-closed SSH host-key fingerprint/known-host checks and token validation. |
| Standalone OSD collector | PASS | 12/12 tests passed. |
| Runtime dependency integrity | PASS | Image `pip check` reported no broken requirements; Node loaded the packaged `express` and `ssh2` runtime modules. |
| Runtime content hygiene | PASS | Executor `*.test.js` files and `ssh2` package test-key fixtures are excluded. A runtime scan found no private-key file, key payload, `.env`, known lab FSID or source unit test under `/opt/storage-lab-console`. |
| Same-origin application smoke | PASS | `/api/live` and `/api/ready` returned healthy/ready for the feature-disabled local profile; `/`, a SPA route and the built JS asset returned 200; an unknown `/api/*` route remained 404. |
| Release Compose model | PASS | Default and optional profiles rendered with Compose v5.1.3; seven application services use the same `STORAGE_LAB_CONSOLE_IMAGE`, while PostgreSQL is a separate image. Only API publishes a loopback port. |
| Evidence persistence | PASS | UID 10001 wrote `portable-evidence-v1` to a fresh named volume; a second read-only container read the same bytes with SHA-256 `4c2b621ea4cca7cb719fb38326be894120ce8e9feb94b67e97943009e780665e`. |
| Basic offline transport | PASS | The combined application + PostgreSQL archive is `248622080` bytes with SHA-256 `c96a949d16d21fc846bcead6d7ed68eb7fe109879b0c323cab66ec8cd4b70917`; after removing the application tag and loading the archive, both image IDs were restored and `version` ran with `--network none`. |
| Package inventory | PARTIAL | Docker Scout SBOM indexed 271 packages. Production `npm audit` reported 0 vulnerabilities for both frontend and executor dependency trees at test time. Full OS/Python/Node image CVE reporting is not claimed: `docker scout cves` required Docker login in this environment. |

The reusable exporter also produced the ignored local candidate bundle
`deploy/dist/storage-lab-console-3.0.0-dev-local/`. Its combined application +
PostgreSQL archive is `248622080` bytes with SHA-256
`c96a949d16d21fc846bcead6d7ed68eb7fe109879b0c323cab66ec8cd4b70917`;
all nine shipped files pass `SHA256SUMS`, and a remove/load cycle restored both
expected image IDs. The bundle contains only deployment examples, metadata,
the SPDX SBOM and image archive—no validation history, runtime secrets or real
cluster profile. It remains `candidate_local_export` because no vulnerability
report, signature or environment acceptance is included.

The API smoke used an isolated temporary PostgreSQL and no cluster credentials.
Upgrade-only readiness did not instantiate an S3 client. The release image did
not contain the test database, evidence volume, secret values or a lab profile.

### Acceptance not claimed

| Check | Status | Required next evidence |
|---|---|---|
| Registry digest, signature and published bundle | NOT_RUN | Publish through the approved registry/release pipeline, then record immutable registry/platform digests, signatures, SBOM and vulnerability report hashes. |
| Full CVE policy gate | NOT_RUN | Run the approved authenticated/offline scanner across OS, Python and Node packages and resolve or explicitly accept findings. |
| Lab A and a second system using the same digest | NOT_RUN | Supply the two approved profiles/secrets and record startup, inventory, saved OSD list and config hashes without rebuild. |
| Full offline Compose startup | NOT_RUN | Load every selected image, block registry/Internet access, then run bundled/external DB migration, API and read-only collection. The archive/version smoke above is narrower. |
| Backup/restore and full recreate | NOT_RUN | Restore PostgreSQL, evidence and executor fencing state at one consistent checkpoint and verify hashes/references. |
| Remote collector and real SSH known-host | NOT_RUN | Independently verify the target host key, install/attest the collector and exercise read-only FSID/inventory preflight. |
| Live PA2/controller mutation and Ceph upgrade | NOT_RUN | Requires a separately approved lab window and all production safety gates; `UPGRADE_MUTATIONS_ENABLED` remains false. |

The local image is therefore suitable as an I0–I2 candidate for lab acceptance,
not as a production-ready or PA2-complete release.

## Portable controller foundation — 2026-10-08

Implementation scope in this change:

- P0 compatibility lock for the existing RGW API surface.
- P1 typed feature/profile configuration, non-secret profile overlay,
  deterministic redacted config snapshots, forward migration `0009`, and
  FSID-bound session creation.
- P2 read-only `/api/v1/cluster/profile`, `capabilities`, and `inventory`
  endpoints over the existing closed executor protocol.
- No PA1/PA2 mutation action, production replica verdict, or live upgrade claim
  was added.

Baseline captured before implementation:

- Backend: 76 tests passed, 8 PostgreSQL integration tests skipped because
  `TEST_DATABASE_URL` was not supplied.
- Frontend: 4 tests passed.
- Node executor: 16 tests passed.

Current backend verification on 2026-10-09 discovered 202 tests: 191 passed and
11 PostgreSQL integration tests skipped because `TEST_DATABASE_URL` was not
configured. Frontend contract tests passed 6/6 and the production build
completed; Node executor tests passed 17/17. PostgreSQL migration/integration
coverage still requires `TEST_DATABASE_URL`. No live cluster workflow was
executed, so PA1, PA2, replica validation, rollback, QoS, and Lab Test remain
`NOT_RUN`/`NOT_EXERCISED` as applicable.

## Evidence and dry-run controller slice

Added after the foundation:

- Forward migrations `0010`–`0012` for evidence artifacts, inventory snapshots,
  capabilities, transactional outbox, phase events, leases/fences, action jobs,
  change ledger, upgrade batches/runs, and dry-run placement plans.
- Pure PA1/PA2 planner with explicit strategy/end-state validation.
- `UpgradeSafetyGate` for FSID, inventory quality, OSD up/in and allowlist,
  failure-domain separation, health, replicated-pool support, and failure
  headroom.
- FSID/config-snapshot-bound batch and run repositories with idempotent create
  semantics.
- Preflight action journal with stale-state/revision checks, retryable-failure
  replay, evidence SHA-256, inventory/capability persistence, and outbox event.
- Session timeline and report skeleton keep operation/QoS/Lab/rollback results
  separate.
- PostgreSQL lease adapter uses database time and monotonically increasing
  fencing generations; no upgrade mutation consumes a lease yet.

This slice still makes no live-upgrade claim. In particular:

- The executor action allowlist was not expanded with placement, redeploy,
  stop, removal, affinity, or scrub mutations.
- PG up/acting/primary, per-OSD image digest, new deep-scrub completion,
  cephadm redeploy, and safe-to-destroy remain `UNSUPPORTED`.
- `operation_result` is persisted as `NOT_EXERCISED`, even when the dry-run plan
  itself returns `PASS`.
- The backend unit/contract suite is green. PostgreSQL integration checks remain
  skipped until `TEST_DATABASE_URL` is supplied.

## PA1/replica/rollback simulator domain slice

The following P4 foundations are implemented but not wired to live mutation:

- Forward migration `0013` adds placement entries, return groups, PG role
  observations, scrub evidence, affinity restores, and operational rollback
  entities without changing migrations `0001`–`0012`.
- PA1 transition evaluator covers drain isolation, maintenance, exact
  version/digest/incarnation readiness, bounded return groups, replica checks,
  affinity restore, ledger cleanup, and stable-window completion.
- Production Replica Checker requires actual `up[]` and `acting[]` membership,
  replica rather than primary role, active+clean, a new scrub after convergence,
  completion evidence, unchanged mapping fingerprint, and explicit zero
  inconsistency/I/O-error/repair counts.
- Operational rollback evaluator keeps `ok-to-stop` separate from
  `safe-to-destroy`, uses current replica sources, requires a clean replacement
  incarnation, checks binary/device compatibility, and waits for rebuild plus a
  stable window.

These are domain/simulator gates only. No route can submit `PASS`, no production
state machine calls the executor, and no PA1 or rollback live result is claimed.

## PA2 spare-chain simulator slice

- Forward migration `0014` is loaded from the canonical migration package and
  adds wave, spare registry, chain, handoff group, rotation and end-state rows.
- The state machine keeps `HANDOFF_COMPLETE` distinct from `WAVE_COMPLETE`,
  blocks source upgrade while the source remains in any `up[]`/`acting[]`, and
  reconciles resume/recovery from current mapping.
- An unexercised final spare reports `NOT_EXERCISED`; dependency-aware cleanup
  holds instead of removing resources used by another chain.
- PA2 domain and migration contract checks pass. PostgreSQL application of
  migration `0014` remains skipped without `TEST_DATABASE_URL`.

No PA2 executor action or live-cluster result was added.

## QoS Observer foundation slice

- Forward migration `0015` adds independent QoS runs, segments, metric windows
  and benchmark attempts.
- `BenchmarkRunnerPort` and capability contracts are provider-neutral.
- fio and shared application telemetry are normalized to canonical windows;
  stale/gap/reset evidence is preserved rather than zero-filled.
- Attribution derives `REMAP`, `NEIGHBOR`, `CONTROL` or `UNATTRIBUTED` from
  evidence. Endpoint-only data is forced to `SERVICE_ONLY`.
- Segment mismatches return `NOT_COMPARABLE`; a zero or missing baseline never
  produces a percentage.
- QoS runner outcomes remain separate from the production `operation_result`.
- Create/read/results APIs are versioned under `/api/v1/qos-runs`.

Warp/fio lifecycle actions are still `UNSUPPORTED`; start/pause/resume/stop are
not exposed until fencing, raw-artifact persistence and crash reconciliation
are complete. No benchmark or QoS PASS is claimed.

## OSD Info Collector integration slice

- Forward migration `0016` adds point-in-time collection state plus indexed
  per-OSD records linked to the existing action journal and evidence artifacts.
- The versioned API exposes create/read/per-OSD detail under
  `/api/v1/osd-inventory/collections`.
- Read-only list APIs expose current-cluster sessions and a session's immutable
  collection journal. The `OSD inventory` screen uses them to select a
  production-upgrade session, collect by phase, inspect indexed OSD planning
  fields, warnings, artifact identity and preserved raw payload.
- Selecting a persisted upgrade run now lists its source/destination OSDs with
  PA1 or PA2 role labels and checks their presence in the opened inventory
  snapshot without modifying the batch or plan.
- A `BEFORE` collection can be bound append-only to an upgrade run/plan
  revision. The binding gate rechecks session, cluster ID, FSID, config snapshot,
  artifact hash, complete/VALID quality, full source/destination OSD coverage
  and `UPGRADE_INVENTORY_MAX_AGE_SECONDS`.
- The readiness API recalculates age instead of trusting the stored READY value.
  Preflight links an eligible binding to `placement_plans`; missing/stale
  evidence forces `execution_readiness=BLOCKED` while operation result remains
  `NOT_EXERCISED`.
- A read-only phase comparison returns per-OSD/per-field raw changes between
  `BEFORE` and `AFTER_START`/`AFTER_STABLE`. Identity or OSD-scope mismatch is
  explicit `NOT_COMPARABLE`; partial quality is `INCONCLUSIVE`, and missing
  values remain unknown rather than zero.
- A separate config-evidence comparison verifies both artifacts before
  normalizing cluster config-database rows and per-OSD effective config. It
  reports added/removed/changed options, ignores row order, marks missing
  command evidence `INCONCLUSIVE`, and detects secret drift without returning
  either secret value.
- A read-only pre-down-set assessment binds a persisted `BEFORE`/`DURING`
  snapshot to the current run state/revision/config/resource tokens, requires
  exact full-allowlist scope, and counts already unavailable OSDs against
  `max_simultaneous_down`. `inventory_result=READY` never changes
  `mutation_readiness=BLOCKED`; PG up/acting, cluster health, lease/fence and
  live mutation remain explicit unmet gates.
- The Node executor has one new read-only closed action,
  `ceph.osd_info_collect`; it invokes a fixed collector path with numeric OSD
  IDs only, checks `UPGRADE_ALLOWED_OSDS`, remains FSID-bound, and applies
  timeout/output limits.
- FastAPI rechecks the OSD allowlist and collector FSID, validates that the
  returned OSD set exactly matches the request, stores the full JSON as a
  checksummed append-only artifact, and indexes planning fields.
- A collection evidence read endpoint exposes only the stored cluster-wide
  evidence. It accepts a collection ID rather than a path, rechecks filesystem
  containment, byte count, SHA-256 and collector protocol/metadata, then
  redacts credential-shaped fields, sensitive Ceph config values and local
  config/keyring argv values without rewriting the immutable artifact.
- Missing core capacity/PG/up-in fields remain `null` and force
  `INCONCLUSIVE`. Missing network/version/device fields cannot silently remain
  `VALID`; device paths are never synthesized.
- Additive migration `0018` indexes CRUSH location, device class, complete
  public/cluster address lists, BlueStore data/DB/WAL roles, device IDs,
  daemon status and container image/digest. The UI shows these fields and the
  phase comparator includes them without treating list ordering as a change.
- Additive migration `0019` projects cluster health/checks, OSDMap epoch,
  flags, pool size/min_size/PG/CRUSH policy, daemon-version summary and cluster
  OSD/PG counts onto each immutable collection. Missing values remain unknown,
  numeric zero remains zero, and the UI labels the context as observational.
- Collection phases include `BEFORE`, `DURING`, `AFTER_START` and
  `AFTER_STABLE`, plus `MANUAL` for an ad-hoc snapshot.

Automated evidence: the backend unittest suite discovered 202 tests (191
passed, 11 PostgreSQL-only tests skipped). The focused phase-comparison and
down-set suite passed 16/16. The frontend contract suite passed 6/6 and its
production build completed. The standalone collector previously passed 12
tests, and the Node suite previously passed 17 tests including fixed-argv and
allowlist enforcement. Migrations `0016`–`0019` were discovered contiguously
through schema version 19,
but actual PostgreSQL application remains unverified without
`TEST_DATABASE_URL`. No collector call was made against a live Ceph host, so no
live inventory quality or baseline is claimed. The binding migration and its
foreign keys were not applied to PostgreSQL because `TEST_DATABASE_URL` was not
available.

The phase-comparison and pre-down-set increments are validated as read-only
software paths only. No live collector invocation, PostgreSQL migration
application, PG gate, or Ceph mutation was exercised by this run.

Last updated: 2026-10-09 (Asia/Saigon).

This report separates automated evidence from live Ceph evidence. `PASS` is
used only where the stated check was executed; incomplete matrices are marked
`PARTIAL` or `NOT_RUN`.

## PR status

| PR | Status | Evidence and remaining scope |
|---|---|---|
| PR1 migrations/job lease | PASS | Fresh/legacy migration tests reach schema `0008`; `0007` preserves the executor-fence rename and `0008` adds durable RBD validation runs. The live stack applied `0008` and reported schema version 8 before PR8/PR9 mutation. |
| PR2 capacity dashboard | PASS | Live Node inventory produced consecutive fresh, complete snapshots. `/api/capacity` returned `FRESH`, source `node-ssh`, OSDs 0–4, the four allowlisted pools, and a current age below one collector interval. |
| PR2A performance | PARTIAL | Application telemetry is live and `FRESH`. The last Ceph sample is currently `STALE`; the configured mgr/Prometheus endpoint refused the collector connection during this validation. No current Ceph performance PASS is claimed. |
| PR3 capacity guard | PASS | Guard/reservation/concurrency regressions passed and the live policy is deliberately `OBSERVE_ONLY`. Enforcement was not enabled, as requested; this status validates the chosen observe-only policy, not a production enforcement rollout. |
| PR4 manual RGW CRUD | PARTIAL | The earlier isolated exact-object create/replay/HEAD/SHA-256 GET/hard-delete smoke passed and the current full regression remains green. The connected bucket has versioning disabled, so the versioned/suspended overwrite/delete matrix is `NOT_RUN`. |
| PR5 RGW CRUD stream | PARTIAL | Frontend now exposes operation weights and per-operation PUT/GET/HEAD/LIST/UPDATE/DELETE results; frontend contract tests and production build passed. A new live six-operation stream job was not started in this validation window. |
| PR6 Node SSH | PASS | Node executor is healthy in Compose, is not host-published, and public health/capabilities proxy through FastAPI. Fourteen Node tests cover validation/injection, path escape, FSID binding, output cap, timeout, reconnect, redaction, inventory, SFTP behavior and fake full lifecycle. |
| PR7 RBD lifecycle | PASS | A live 1 GiB image completed create → exclusive map → ext4 → mount → checksum write → unmount/unmap → remap/mount → checksum verify → final unmount/unmap/delete. Cleanup evidence is recorded below. |
| PR8 RBD SFTP browser | PASS | A live 256 MiB ext4 canary exercised mkdir, list/stat, overwrite, delete, bounded upload/download, text/PNG/PDF preview, a 6 MiB streamed file, path traversal and symlink containment, and checksum preservation across unmount/remap. |
| PR9 terminal + upgrade checks | PASS | A live PTY was opened through the public Nginx/FastAPI WebSocket path, started in the managed mountpoint, read the expected checksum, rejected ticket reuse, and fenced unmount while active. A durable four-file baseline passed immediately and after remount, detected an intentional overwrite as `FAIL`, then returned to `PASS` after restoration. No Ceph version change was performed. |

## Automated and deployment checks

| Check | Status | Evidence |
|---|---|---|
| PostgreSQL migration | PASS | Isolated fresh/legacy migration tests applied versions `0001`–`0008`, reran idempotently and verified the validation table. The deployed migration container then applied `0008` to the live stack successfully. |
| Backend unit/integration suite | PASS | `python -m unittest discover -s tests` with the configured PostgreSQL connection: 73 tests passed. Coverage includes the closed file/terminal executor actions and migration 0008 in addition to the earlier guard/lifecycle cases. |
| Node executor suite | PASS | `npm test`: 14 tests passed, including path rejection, MIME sniffing, non-empty-directory rejection, pipeline-based checksums, single-use/expiry tickets and active-access lifecycle fencing. |
| Frontend contract suite | PASS | `npm test`: 4 tests passed, including mounted-only file access and fail-closed preview classification. |
| Frontend production build | PASS | Vite transformed 1841 modules and completed the production build; it emitted only the existing bundle-size advisory. |
| Compose rendering | PASS | Both default `docker compose config --quiet` and `docker compose --profile ceph-ssh config --quiet` completed successfully. |
| Container image build | PASS | `docker compose --profile ceph-ssh build backend rbd-console frontend` completed with the pinned WebSocket and xterm dependencies. |
| Running `ceph-ssh` profile | PASS | Backend, frontend, worker, Node executor, capacity collector and lifecycle worker are running; Node healthcheck is healthy. Collector logs show repeated HTTP 200 inventory calls and fresh complete samples. |

## Live capacity evidence

The live comparison was performed in one collection window:

| Field | FastAPI/collector | Ceph CLI | Result |
|---|---|---|---|
| FSID | `17c77e12-a16a-11f1-838e-cf68e9c001d8` | same | PASS |
| OSDMap epoch | `2175` | `2175` | PASS |
| Participating OSDs | `0,1,2,3,4` | `0,1,2,3,4` | PASS |
| Most-full OSD | `osd.3` | `osd.3` | PASS |
| Most-full ratio | `13.8091%` | `13.8091%` | PASS; difference `0.0` percentage points |
| Pool scope | `default.rgw.lab.data`, `default.rgw.lab.data-extra`, `default.rgw.lab.index`, `rbd-lab` | reviewed allowlist | PASS |

The final PR8/PR9 post-cleanup read remained `FRESH` at epoch `2230`, with
`osd.3` at `14.0694%` and telemetry age below one collector interval.
The cluster had 5/5 OSDs up and in, 265/265 PGs `active+clean`, no degraded,
recovery/backfill, full or backfillfull state. `HEALTH_WARN` was reviewed before
mutation: the three current `RECENT_CRASH` records were `osdmaptool` CLI crashes
under `client.admin`, not crashed OSD/MON/MGR daemons. They were not archived.

## Live PR7 smoke and cleanup

- Image: `rbd-lab/lab-pr7-85223afe-4541-469f-9196-1a64660aa1b4`
- Logical size: 1 GiB
- Managed volume: `83b394e9-e14c-5200-95a2-4f809a8874db`
- Device during mounted phases: `/dev/rbd0`
- ext4 UUID: `cafbb450-0411-4d71-888a-f5f252d7ce84`
- Probe SHA-256 before and after remount:
  `1b63c04988c2da96284b8c2adbadb40ebb6ae6fc8316ffea17680c4639de9295`
- Create, first unmount, remount, final unmount and delete actions all reached
  `SUCCEEDED`; the final volume state is `DELETED`.
- Post-cleanup checks: zero images in `rbd-lab`, zero `rbd device list`
  mappings, no active mount for the managed mountpoint, zero active lifecycle
  actions and zero orphan-candidate capacity reservations.

## Live PR8/PR9 smoke and cleanup

- Image: `rbd-lab/lab-pr89-e9f6379a44a6`
- Managed volume: `e4423697-5b77-537a-868e-c83877a7e6c9`
- Logical size: 256 MiB; image ID: `e21f1441951d9`
- Mounted device: `/dev/rbd1`; ext4 UUID:
  `605a89f8-55e6-4d44-9210-51f06e702c54`
- SFTP live matrix uploaded text, PNG, PDF, binary and a 6 MiB streamed file.
  Download SHA-256 for the 6 MiB file was
  `e09195b42eb81f998c99cebf46fa0a95a2836ddc258b1d90aa31611a46060c4e`.
- Preview returned `200` with `nosniff` and sandbox CSP for text/PNG/PDF,
  `415 PREVIEW_UNSUPPORTED` for arbitrary binary and `413 PREVIEW_TOO_LARGE`
  for the 6 MiB preview. Traversal returned `422 PATH_ESCAPE`; a shell-created
  symlink to `/etc/passwd` returned `422 SYMLINK_NOT_ALLOWED`.
- A live failure exposed that non-empty directory deletion returned a generic
  503. The executor now checks directory contents first and returns
  `409 DIRECTORY_NOT_EMPTY`; the new regression test passes.
- Validation run `7a4c4112-90c3-44d8-8b92-4f46665e88e3` recorded four SHA-256
  files at FSID `17c77e12-a16a-11f1-838e-cf68e9c001d8`, OSDMap epoch `2229`.
  Immediate verify and post-remount verify passed. An intentional text-file
  overwrite produced `FAIL/CHANGED_OR_MISSING`; restoring the original bytes
  returned the same run to `PASS`.
- The public `/ws/terminal` path opened a real SSH PTY in the managed
  mountpoint, returned the baseline text checksum, rejected ticket reuse, and
  returned `409 VOLUME_BUSY` when an unmount probe was made during an active
  terminal session.
- Repeated manifests initially exposed an unhandled late SFTP `ReadStream`
  error that restarted the Node container. Hashing now uses `stream.pipeline()`;
  five consecutive live verifies passed afterward with executor restart count
  remaining `0` and telemetry `NORMAL/FRESH`.
- File cleanup succeeded, then volume delete completed
  unmount → unmap → image remove with final state `DELETED`. Post-cleanup checks
  found zero active canary actions, zero active canary reservations and no
  canary image/mapping/mount. The pre-existing `hehe` volume/image remained the
  sole `rbd-lab` mapping and was not modified.

## Checks not claimed

| Check | Status | Reason |
|---|---|---|
| Versioned/suspended RGW cleanup matrix | NOT_RUN | The connected allowlisted bucket reports versioning disabled. |
| Live six-operation PR5 workload | NOT_RUN | No new stream job was created during the PR7 validation window. |
| Current Ceph performance telemetry | PARTIAL | Historical data exists but is stale because the configured Prometheus endpoint is currently unavailable. |
| Visual browser screenshot QA | NOT_RUN | Both available browser surfaces reported unavailable in this runtime. Public HTTP/WebSocket paths, frontend contracts and the production build were tested instead. |
| Actual Ceph version upgrade between baseline and verify | NOT_RUN | This validation tested the live pre/post-remount boundary and checksum change detection; it did not alter the cluster version. |
| Upgrade/recovery/backfill and external-writer fault matrix | NOT_RUN | Requires a separately approved fault-test window; it is outside PR7. |

## Operational limits

- `CAPACITY_OBSERVE_ONLY=true` remains in force. Fresh telemetry removes the
  `BLOCKED_TELEMETRY` display but does not silently enable enforcement.
- `rbd-lab` is the only mutation pool. No pool was provisioned and
  `volumes_hdd` was not touched.
- Successful delete does not claim immediate physical reclamation; transient
  reservation release still follows telemetry settlement rules.
- PR8/PR9 live paths are validated. The stored baseline/verify API is ready to
  be called on the two sides of a separately controlled Ceph upgrade window;
  this run does not claim that an actual version upgrade occurred.
# Phát hành demo/lab 5.1.1-rc.1 — 13/10/2026

Trạng thái tại ngày 13/10/2026: localhost 8080 chạy `5.1.1-rc.1`; app và worker `16.2.15-minimal-preview.2` đã push, xác minh Docker Hub tag/index và pull theo digest. [Manifest release](deploy/releases/5.1.1-rc.1.yaml) giữ checksum/report; [README demo](docs/DEMO.md) là kịch bản sử dụng. Những kết quả cũ phía trên là lịch sử, không ghi đè hoặc tự promote production.

- Đã sửa nguồn bận: tối đa hai lần thu đang chạy + hai yêu cầu chờ tối đa 30 giây, không chia sẻ cache; UI single-flight, hủy khi rời trang, thử lại chỉ lỗi `COLLECTION_BUSY` có giới hạn. Timestamp orchestrator rỗng/sai kiểu trả PARTIAL, không lỗi server.
- Backend image 304/304, không skip PostgreSQL; frontend 24/24, TypeScript/build đạt; executor 31/31, helper 26/26, real worker 17/17, diagnostics/guard 26/26. Test DB trắng ban đầu thiếu schema cho bốn persistence test cũ; chạy migration 0021 rồi toàn bộ 304 test đạt. Không sửa database lab để chữa fixture kiểm thử.
- Integration API–worker thật–PostgreSQL riêng đạt 38/38, tamper trả HTTP 503/`OSDMAP_RESULT_IDENTITY_MISMATCH` trước lưu kết quả sai. Report schema 2 cùng nguồn runner bất biến nằm ở `deploy/dist/dockerhub-5.1.1-rc.1/`; lỗi integration đầu lịch sử vẫn UNCONFIRMED/stability OPEN.
- App Scout: 167 package, 0 finding mọi mức; worker raw scan mới: 133 package, 1C/21H/35M/2L, giữ riêng triage vendor/CNA. Worker **chưa đạt production**; image signing, ARM64, cluster thứ hai và nghiệm thu production toàn bộ chưa thực hiện.
- Trình duyệt thật: đọc mới FSID/14 daemon, trang 1 có 10 hàng và trang 2 có 4; chọn MON/OSD qua trang rồi xuất mới tải tệp thật (20.336 byte), timestamp mới hơn bảng. So sánh hai collection OSD cũ đạt; lọc giai đoạn giữ A/B/kết quả; tải JSON so sánh thật (1.764.424 byte). Đã thu và lưu một bộ demo mới `d5b038a3-7dc2-5444-a968-61ccae127ec2` gồm osd.2/osd.5, ghi rõ không nâng cấp/ghi Ceph.
- Backup DB/evidence/executor trước swap trong thư mục ACL riêng. Bốn collection cũ/checksum/deleted state, tám events và archive evidence giữ nguyên ngay sau deploy; mọi mount RO/RW giữ nguyên, PostgreSQL/container volume không thay; thêm một collection demo có chủ đích sau kiểm chứng. Stack 8443 giữ nguyên, không thực hiện Ceph mutation. Các container cũ vẫn giữ để phục hồi.

---
