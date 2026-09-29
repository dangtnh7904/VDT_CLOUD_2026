# Nguồn, phạm vi kiểm chứng và đối chiếu bản cũ

[Mục lục](00-README.md) · [Điều kiện cần sửa](02-DIEU-KIEN-VA-THAY-DOI.md)

## 1. Nguồn được dùng ngày 28/09/2026

| ID | Nguồn | Nội dung dùng |
| --- | --- | --- |
| S01 | [Ceph release index](https://docs.ceph.com/en/latest/releases/) | Pacific 16.2.15 và trạng thái vòng đời upstream |
| S02 | [16.2.15 release announcement](https://ceph.io/en/news/blog/2024/v16-2-15-pacific-released/) và [Pacific release history](https://docs.ceph.com/en/latest/releases/pacific/) | Lợi ích đúng phạm vi: Browser POST, RBD diff, MON/OSD, config output; lịch sử bản vá |
| S03 | [Pacific cephadm upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/) | Bootstrap MGR từ bản chưa có filters, order, Quay, monitoring refresh và host tools |
| S04 | [16.2.7 release announcement](https://ceph.io/en/news/blog/2021/v16-2-7-pacific-released/) | OMAP format fix có điều kiện lịch sử store; mClock behavior |
| S05 | [BlueStore configuration](https://docs.ceph.com/en/pacific/rados/configuration/bluestore-config-ref/) | Checksum và mô hình storage; không suy H0 từ checksum local |
| S06 | [CRUSH maps](https://docs.ceph.com/en/pacific/rados/operations/crush-map/) | Placement, failure domain, weights và primary-affinity |
| S07 | [PG repair](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/) | Chẩn đoán inconsistency và giới hạn repair native |
| S08 | [options.cc v16.2.5](https://github.com/ceph/ceph/blob/v16.2.5/src/common/options.cc), [options.cc v16.2.15](https://github.com/ceph/ceph/blob/v16.2.15/src/common/options.cc) | Đã đối chiếu key bị bỏ/đổi, WPQ, message cap, quick-fix, min values và Vault verify |
| S09 | [BlueFS.cc target](https://github.com/ceph/ceph/blob/v16.2.15/src/os/bluestore/BlueFS.cc), [BlueFS.cc base](https://github.com/ceph/ceph/blob/v16.2.5/src/os/bluestore/BlueFS.cc), [types target](https://github.com/ceph/ceph/blob/v16.2.15/src/os/bluestore/bluefs_types.h), [types base](https://github.com/ceph/ceph/blob/v16.2.5/src/os/bluestore/bluefs_types.h) | Đã kiểm logic allocator và opcode incremental vs old reader; đây là proof source, không phải proof chạy downgrade |
| S10 | [Dashboard target module](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/dashboard/module.py) | Đã kiểm TLS minimum 1.3 mặc định trong HTTPS và option exception |
| S11 | [Prometheus target module](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/prometheus/module.py) | Đã thấy đường tạo metadata `pool_objects_repaired` lặp; runtime parser phải kiểm trên artifact thật |
| S12 | [Cephadm migrations target](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/migrations.py) | Đã kiểm các transition tới migration 5; không coi hạ binary tự undo state |
| S13 | [Cephadm upgrade target](https://github.com/ceph/ceph/blob/v16.2.15/src/pybind/mgr/cephadm/upgrade.py) | Filters, order validation, pause/resume/stop và engine state |
| S14 | [fio documentation](https://fio.readthedocs.io/en/latest/fio_doc.html) | Options tham khảo; pin version tool trước benchmark |
| S15 | [Warp official repository](https://github.com/minio/warp) | Công cụ S3 benchmark; dùng workload riêng, giữ version/config |
| S16 | [rbd manual Pacific](https://docs.ceph.com/en/pacific/man/8/rbd/), [rados manual Pacific](https://docs.ceph.com/en/pacific/man/8/rados/) | Công cụ kiểm thử quản trị/client; không thay RBD/RGW benchmark bằng RADOS đơn thuần |
| S17 | [H0 Feature v2.1 trong repo, commit c29c4272](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/c29c4272c2c3b69ceb1d68aac234731fe2f07f01/H0_Feature_Ket_hop_PA1_va_Web_Canary%20%283%29.md) | Nguồn chính cho H0-R, H0-W Level 1–2–3, hook A–E, ACK contract, capability, giới hạn prototype và test R/W/P |
| S18 | [Plan trong repo, phần PA1, commit c29c4272](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/c29c4272c2c3b69ceb1d68aac234731fe2f07f01/plan%283%29%20%281%29.md) | PA1 Maintenance-DR: X online khi chuyển PG, S/upmap, DR_READY rồi mới stop, return và map control; chỉ lấy phần PA1 theo scope người dùng đã chốt |

Các bảng gate, ngưỡng, thiết kế test và quyết định bố trí file là **đề xuất vận hành của bộ này**, không phải yêu cầu nguyên văn Ceph. URL `latest` chỉ dùng đọc lịch sử release/vòng đời; không lấy tính năng vận hành mới ở latest áp cho Pacific.

## 2. Đã xác minh gì và chưa xác minh gì?

- Đã đọc checklist gốc được đính kèm, release documentation và các đoạn source nêu ở S08–S13.
- Đã đọc H0 hiện tại và phần PA1 của repo tại commit được pin ở S17–S18. H0 v2.1 là **thiết kế**, không phải bằng chứng feature đã implement hoặc test PASS.
- Chưa truy cập cluster, pull/execute image target, chạy lab/benchmark/restore hoặc xác nhận As-Is production.
- Repo có bộ source-comparison mà checklist cũ dẫn tới; đợt chỉnh này chưa tái kiểm toàn bộ các file đó. Không lặp lại số dòng diff, coverage hoặc dấu PASS như bằng chứng mới.
- Những chi tiết theo platform như PWL layout, RPM scriptlet, legacy Manila và custom module được giữ dưới dạng applicability/test. Cần kiểm artifact triển khai thật trước khi biến thành blocker cụ thể.
- Mã upstream không chứng minh vendor/custom image giống hệt. C01 phải xác nhận digest/build và delta.

## 3. Những kết luận được sửa so với mục 4.3 cũ

| Nội dung cũ | Cách dùng trong v2 |
| --- | --- |
| Gọi mọi mục “sửa bắt buộc theo điều kiện” | Tách kiểm tra / sửa khi áp dụng / khuyến nghị / change riêng; có nơi sửa và thời điểm |
| Allocator nhỏ hơn block/unit là invalid | Sửa theo logic `max(unit, value)` rồi kiểm alignment; không kết luận lỗi chỉ từ giá trị nhỏ |
| Chuẩn bị Prometheus package/backport như bước mặc định | Bắt buộc kiểm parser/telemetry; chỉ cần fix artifact/consumer khi runtime thực lỗi hoặc chưa có nguồn thay thế phù hợp |
| Mọi client Dashboard phải nâng TLS | Chỉ chặng TLS tới Dashboard HTTPS chịu minimum target; xét proxy termination/backend riêng |
| Map chính xác 18 alert cũ → 58 alert mới | Không giữ con số làm yêu cầu runtime khi chưa có actual rules; diff rules đang dùng và sửa consumer bị tác động |
| Mọi feature/service đều có gate | Chỉ chặn phạm vi áp dụng; chứng minh vắng mặt thì N/A |
| PWL/RPM issue chặn toàn cluster | Gate ở transaction/client/cohort thực sự liên quan |
| Gọi PA1 + H0 là prerequisite của mọi nâng Ceph | Đây là phạm vi pilot người dùng đã chọn: phải qua gate PA1/H0 tương ứng; không trình bày H0 như yêu cầu upstream cho mọi cluster |
| Downgrade package là rollback OSD | Giữ boundary store và chọn đường phục hồi đã thử |
| Một file chứa test/research/MOP/biểu mẫu | Tách 16 file và dùng link tương đối; test H0 Level 1–2–3 ở file 15 |
| Trộn H0-static, hậu kiểm và enforce thành ba level | Theo S17: H0-R dùng chung; H0-W L1 buffer primary, L2 thêm buffer replica, L3 thêm persisted readback mọi required copy; cả ba chặn trước SUCCESS_ACK |

## 4. Ánh xạ phần cũ sang file mới

| Checklist cũ | File v2 |
| --- | --- |
| §1 phạm vi/applicability/guardrail | 00, 02, 06, 12 |
| §2 G00–G13 core và service gates | 06 G0–G9 + 02 C01–C20 + 08 CON-* |
| §2 G14–G16 phương án/H0/khả năng phục hồi | 10, 11, 15 và H0-G0/GR/GW/GC tại 06; thay bằng contract H0 hiện tại |
| §3 As-Is | 03, 12, 14 |
| §4 thay đổi/config/guardrail | 02, 07, 10 |
| §5 activation | 01, 02, 04, 11 |
| §6 test | 08 chức năng, 09 hiệu năng, 15 H0 theo từng level; chỉ mục điều kiện bên dưới |
| §7 rollout | 03, 04, 05, 14 |
| §8–§9 STOP/rollback | 06, 10 |
| §10 evidence/sign-off | 12 |
| §11 read-only commands | 14 |
| §12–§13 traceability/nguồn H0 | File này và 11 |

## 5. Test cũ nào được kéo vào khi có điều kiện?

Đây là chỉ mục chọn bài, không khẳng định mọi scenario cũ đã được chạy hoặc vẫn là prerequisite. Chi tiết cũ còn trong file gốc của người dùng; v2 chỉ giữ yêu cầu có ích cho scope.

| Test ID cũ | Định tuyến v2 / khi cần |
| --- | --- |
| T00, T09B | PRE-01/PRE-02: artifact và exact-path rehearsal |
| T01, T17B | PRE-05 + CON-STORAGE: downgrade/restore boundary; old-reader tests chỉ trên clone nếu đường rollback đó nằm trong plan |
| T02/T02A/T03/T03A | PRE-01 + CON-STORAGE: identity/allocator; fault errno/fragmentation sâu nếu có custom delta hoặc lỗi tái hiện |
| T04, T12–T15/T14A/T15A | PRE-04, CAN-01, CON-CONSUMER: metrics/module/alerts/PG automation đang dùng |
| T05/T05A/T09/T09A/T29/T29A/T29B | CON-PLATFORM/CON-CONSUMER: kiến trúc, crypto, CLI, package và source build thật; buffer/LRU fault khi path áp dụng |
| T06/T07/T18/T18A/T19/T19A/T20/T20A | CON-STORAGE + CAN-03/04: legacy OMAP/PGLog/OMAP range/shared blobs/scheduler; deep fixture khi history/workload liên quan |
| T08 | Custom `cls/cmpomap` consumer: empty-U64 semantics giữa primary base/target; không chạy trên pool business |
| T10/T10A–D/T11/T17/T17A/T21/T21A/T21B | CAN-02/03 + PRE-05; FSMap/offline MON-tool/recovery decode hoặc transport fault chỉ khi topology/runbook cần |
| T16/T25 | CON-EC; stretch topology có dùng thì bổ sung lab mất/phục hồi site và tiebreaker; không inject production |
| T22 | Consumer `rbd-read-only`, cache-tier/object-manifest/refcount đặc biệt: quyền và dữ liệu trên fixture riêng |
| T23/T23A/T23B | CON-FS: CephFS/MDS/Manila/NFS/mirror thực sự dùng |
| T24/T24A/T24B/T24C | CON-RGW/CON-RGW-BG/CON-RBD theo Vault/mirror/multisite/worker |
| T26/T26A/T26B/T27 | PRE-02/CAN-01/CAN-03: cephadm lifecycle + device activation; test 3+ MGR/unreachable NFS/HAProxy khi topology có |
| T28/T28A/T28B | CON-RBD: cache, journal, diff, lock và mirror theo client scope |
| T30 | EXT-PA1 + P-04; điều kiện hiện tại là DR_READY trước stop |
| T32–T37 | Không giữ nguyên expected result cũ; thay bằng H0-R/W/P ở 15 theo contract S17. Không chuyển dấu PASS cũ sang bộ test mới |
| T38 | PRE-05/P-06 và quyết định RPO/RTO tại 10; không có cụm thứ hai thì ghi chưa thử B100, không suy H0 tương đương backup |

## 6. Giới hạn sử dụng lại

Đây là bộ v2.1 cho hop Pacific với PA1 + H0 theo S17–S18. Đổi target, image custom, topology, scheduler hoặc H0 contract phải đánh giá lại các phần bị tác động. Test lab nhỏ có thể chứng minh logic, nhưng không chứng minh throughput/khả năng hoàn tất rollout 24 PB nếu chưa có số đo production có kiểm soát.
