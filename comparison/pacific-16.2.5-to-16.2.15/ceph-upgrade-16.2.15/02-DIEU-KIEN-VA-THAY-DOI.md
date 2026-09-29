# Điều kiện áp dụng và thay đổi thực sự cần làm

[Mục lục](00-README.md) · [Phase 1](03-PHASE-1-TRUOC-NANG-CAP.md) · [Gate](06-GATE-VA-NGUONG.md)

## 1. Trả lời cho mục “4.3 Sửa bắt buộc theo điều kiện” cũ

**Không phải mọi dòng trong mục 4.3 đều buộc mọi cluster sửa.** Tách thành: kiểm tra bắt buộc; sửa khi có điều kiện; khuyến nghị vận hành; và thay đổi riêng. Không có override, không dùng tính năng hoặc kiểm thử đã đạt thì không tự tạo thêm cấu hình để “đủ checklist”.

Trong các bảng dưới, `YES` = có điều kiện; `NO` = có bằng chứng không có; `UNKNOWN` = cần kiểm trước khi nâng thành phần chịu ảnh hưởng. UNKNOWN của CephFS không mặc định chặn một lab chỉ chạy RGW/RBD sau khi đã chứng minh CephFS vắng mặt.

## 2. Những kiểm tra áp dụng cho tất cả các đợt nâng

| ID | Phải xác nhận | Khi nào phải sửa? | Nơi xử lý |
| --- | --- | --- | --- |
| C01 | Base/target đúng version, digest, kiến trúc; custom/vendor delta được hiểu | Sai artifact hoặc không có đường pull/activation đã thử | Registry, manifest image, host/container runtime |
| C02 | Quorum, PG, dịch vụ, dung lượng và thời gian ổn định | Có blocker tại G1/G2 | NTP/network/MON disk/OSD/service bị lỗi cụ thể |
| C03 | Config thực của từng cohort parse được và effective value đúng | Có key không còn hợp lệ, giá trị ngoài miền, hoặc override bị áp khác ý định | Config DB đúng entity/mask; ceph.conf, service spec, argv/env hoặc automation sở hữu giá trị đó |
| C04 | Telemetry và client probe vẫn hoạt động sau MGR failover | Scrape/parser/query/alert thực tế lỗi và không có nguồn thay thế đủ tiêu chí gate | Prometheus module/image, scraper, queries, rules, route |
| C05 | Nguồn phục hồi và đường fallback/rebuild đã thử | Runbook chỉ có “hạ image rồi chạy lại” hoặc thiếu nguồn phục hồi | Runbook phục hồi; bản sao/config checkpoint phù hợp |

Các mục này yêu cầu **bằng chứng kiểm tra**, không đồng nghĩa phải thay cấu hình trên cụm khỏe.

## 3. Bảng thay đổi có điều kiện

| ID | Điều kiện kích hoạt | Việc cần làm, vị trí | Thời điểm / phạm vi bị chặn | Sau nâng |
| --- | --- | --- | --- | --- |
| C06 | Dùng cephadm 16.2.5 và muốn `--limit`/filter canary | Nâng standby MGR, chuyển active có kiểm soát, hoàn tất nhóm MGR theo hướng dẫn Pacific; kiểm migration state | Trước dùng filtered upgrade; chặn bước lọc khi active MGR còn base | Giữ MGR target; không tự failback sau migration |
| C07 | Có override allocator lạ hoặc activation fail | Đối chiếu unit thực và thử trên clone; chỉ sửa cấu hình gây lỗi/alignment sai | Trước OSD thuộc cohort đó | Giữ giá trị đã được xác minh; không tuning thêm |
| C08 | `osd_op_queue=mclock_scheduler` và đang phụ thuộc generic capacity key cũ | Chuyển ý định capacity sang `_hdd`/`_ssd` theo media; thử boot benchmark trên một OSD | Trước target OSD tương ứng | So capacity thực và QoS; WPQ tiếp tục WPQ nếu đó là baseline |
| C09 | Device alias trỏ sai thiết bị, nhiều owner/writer hoặc target không mở được device | Sửa đúng mapping/ownership/activation; kiểm bằng serial/WWN/LV/major:minor | Trước restart OSD bị ảnh hưởng | Xác nhận block/DB/WAL vẫn đúng; không zap để chữa lỗi mapping |
| C10 | Dashboard HTTPS và client/proxy kết nối tới Dashboard chỉ hỗ trợ TLS 1.2 | Nâng khả năng TLS của đúng chặng client/proxy → Dashboard; exception TLS phải theo policy hiện hữu | Trước target MGR phục vụ Dashboard | Test direct và LB; không hạ TLS trên toàn cụm |
| C11 | RGW dùng Vault và trust/CA hiện tại không đáp ứng verify riêng | Đặt CA/trust đúng trong môi trường container; kiểm `rgw_crypt_vault_verify_ssl` và đường encrypt/decrypt | Trước RGW restart | Giữ CA/policy đã kiểm; không tự trả về verify=false |
| C12 | Automation parse JSON/XML `ceph config dump` hoặc dùng key đã bỏ | Sửa parser để giữ localized name/scope; xử lý từng key theo bảng mục 4 | Trước target MON/client khiến consumer bị ảnh hưởng | So effective config; bỏ cấu hình tạm đã hết nhu cầu |
| C13 | Dùng custom MGR module/alert/query phụ thuộc API/metric cũ | Test callback, `NOTIFY_TYPES`, schema và rules thật; sửa những consumer hỏng | Trước promote MGR hoặc reload rules liên quan | Test lại sau active failover; giữ phiên bản rules có thể khôi phục |
| C14 | RGW phục vụ Browser POST | Chạy negative policy test; nâng/drain đủ endpoint để đạt mục tiêu security | Khi nâng RGW; chưa đóng security gate nếu base endpoint vẫn nhận luồng này | Re-test qua LB và từng endpoint |
| C15 | Có CephFS/NFS/Manila | Review remount client, MDS session/eviction, ranks/standby và migration NFS; audit cap cũ nếu có điều kiện Manila lịch sử | Trước cohort MGR/MDS/NFS chịu tác động | Kiểm ranks/flags/export/caps đúng dự kiến |
| C16 | Nâng client librbd dùng SSD PWL cũ | Thử đúng cache layout/procedure trên recovery copy; flush sạch theo tích hợp, giữ khả năng phục hồi | Trước client target; không mặc định chặn OSD-only nếu client vẫn giữ nguyên và đã tương thích | Không mở cache mới bằng client cũ khi chưa kiểm |
| C17 | Có transaction RPM/DEB trên host, custom build hoặc AArch64/FIPS | Rehearsal package lifecycle, dependency, user/key/unit và platform cần dùng | Trước transaction/cohort đó | Kiểm activation, quyền và service; container upgrade đơn thuần không tự kéo mọi test RPM vào scope |
| C18 | Store từ trước Pacific và có quick-fix/repair-on-mount trên base | Kiểm effective `bluestore_fsck_quick_fix_on_mount`; ngăn repair tự động rủi ro trước restart base, điều tra dữ liệu nếu đã bị tác động | Trước thao tác có thể kích hoạt đường lỗi cũ | Không tự bật repair-on-mount chỉ vì đã nâng |
| C19 | Scope dự án PA1 + H0-R | Chuẩn bị S/upmap và local verifier X; reference H0-static, corpus/writer ổn định; deep-scrub mới sau recovery | Trước cho X vào primary workload; thiếu local evidence thì chưa RETURN_VERIFIED | Lặp cho PG mới; không gán GET qua peer thành local-X PASS |
| C20 | Chọn H0-W Level 1/2/3 | Build generator/primary/gate cho L1; thêm peer protocol/verifier cho L2; thêm reader sau commit X+peers cho L3 | Trước arm workload; mọi required peer đủ capability; giữ native completion | Giữ policy từng operation, reconcile trước đổi level; không tự fallback |

**Chỉnh chính xác C07:** mã `BlueFS.cc` của target lấy `max(unit, bluefs_shared_alloc_size)` rồi kiểm alignment bằng `p2phase`. Vì vậy, “giá trị cấu hình nhỏ hơn unit” riêng lẻ **không đủ chứng minh phải sửa**. Giá trị hiệu lực sai alignment hoặc lỗi activation mới là lý do chặn OSD tương ứng. [S09](13-NGUON-VA-DOI-CHIEU.md)

Nguồn C06, C10–C14, C18: [S02–S04, S08–S13](13-NGUON-VA-DOI-CHIEU.md). C15–C17 giữ rủi ro có điều kiện từ bản gốc; chi tiết layout/package trên artifact đích phải xác minh bằng test, không suy thành lỗi đang tồn tại.

## 4. Sáu key cũ: audit nơi đang dùng, không xóa hàng loạt

Đã đối chiếu sự có mặt của key trong `options.cc` upstream của hai tag. Đây là kiểm source; binary vendor và effective config vẫn cần kiểm riêng. [S08](13-NGUON-VA-DOI-CHIEU.md)

| Key cũ | 16.2.15 upstream | Chỉ hành động nếu… |
| --- | --- | --- |
| `osd_mclock_max_capacity_iops` | Không còn generic key; có `_hdd` và `_ssd` | Dùng mClock và override generic có ý nghĩa; map đúng media |
| `mds_max_retries_on_remount_failure` | Thay bằng `client_max_retries_on_remount_failure` | Client CephFS đang phụ thuộc override; đặt đúng scope client, không suy từ tiền tố `mds_` |
| `ms_async_max_op_threads` | Không còn | Template/argv/config còn truyền key; không thay bằng `ms_async_reap_threshold` vì khác nghĩa |
| `rgw_rados_pool_pg_num_min` | Không còn | Automation tạo pool còn dựa vào nó; không đổi PG pool hiện hữu theo quán tính |
| `rgw_bucket_quota_soft_threshold` | Không còn | Consumer phụ thuộc cấu hình/semantics cũ; test quota thay vì đoán key thay thế |
| `rbd_persistent_cache_log_periodic_stats` | Không còn | Client PWL/monitoring còn dùng key; không coi xóa key là đã tắt cache |

Snapshot trước; sửa ở nguồn cấu hình sở hữu giá trị; chuẩn bị cấu hình đúng phiên bản cho mỗi cohort. Không xóa key mà daemon base còn cần trong mixed phase. Key target-only cũng không được đẩy mù vào argv của daemon base.

## 5. Thay default: phải quan sát, không bắt buộc override

| Thay đổi source | Kiểm khi canary |
| --- | --- |
| `osd_client_message_cap`: 0 → 256 | Queue, RSS, p99 và offered load |
| `osd_fast_shutdown_notify_mon`: false → true | Thời điểm down/up, alert và recovery |
| `osd_aggregated_slow_ops_logging`: thêm default true | Parser/log rate; không dùng số dòng log làm số slow-op |
| `osd_pg_max_concurrent_snap_trims`, `log_max_recent`: min 1 | Chỉ cần sửa nếu cấu hình thực đang đặt 0 hoặc ngoài miền |
| `osd_rocksdb_iterator_bounds_enabled`: thêm default true | Tính đúng OMAP trên fixture phù hợp |

## 6. Không phải prerequisite chung của hop này

Đổi WPQ sang mClock; tăng PG; bật feature RBD mới; nâng `require_osd_release` khi đã Pacific; reshard RocksDB; migrate DB/WAL; repair toàn cụm; dựng cụm backup đúng 100 TB; hoặc đổi mọi OSD service sang `unmanaged` đều không phải yêu cầu chung của 16.2.15.

H0 là yêu cầu riêng của pilot PA1 + H0 trong bộ này, không phải cấu hình Ceph native có sẵn. C19/C20 chặn việc tuyên bố H0 canary đạt khi verifier/protocol chưa implement; không yêu cầu lập tức triển khai cả ba level. Chọn level nào thì nghiệm thu đủ capability và test của level đó. H0-R dùng chung mọi level. [S17–S18](13-NGUON-VA-DOI-CHIEU.md)

Nếu chính sách phục hồi yêu cầu backup độc lập thì phải đáp ứng **phạm vi/RPO/RTO đó**, nhưng không gán một con số dung lượng cố định thành yêu cầu của Ceph. Xem [10](10-STOP-FALLBACK-ROLLBACK.md).
