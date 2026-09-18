# Checklist nâng cấp Ceph Pacific 16.2.5 → 16.2.15

> **Trạng thái:** Pha 3 — bộ so sánh `00`–`15` đã qua acceptance và mapping finding→control đã hoàn tất ở mức tài liệu. Mỗi finding có điểm vào applicability, gate, test, rollout, STOP hoặc rollback; đây là traceability thiết kế, không phải bằng chứng scenario đã chạy hay PASS.
>
> **Quyết định mặc định hiện tại:** **HOLD / chưa đủ điều kiện GO Production** cho tới khi có As-Is của cluster đích, mọi gate áp dụng được đánh dấu PASS, test lab/canary có bằng chứng và owner ký nhận. Hoàn thành phân tích source không thay thế runtime validation.
>
> **Giới hạn:** đây là checklist chuẩn bị, kiểm chứng và ra quyết định; không phải lệnh cho phép thay đổi cluster. Không có lệnh nâng cấp, repair, migrate, trim hay thay cấu hình nào đã được chạy khi tạo tài liệu.
>
> **Ngày lập:** 2026-09-17. **Cập nhật:** 2026-09-18 — PA1/PA2 + H0 chọn nguồn đúng và kiểm chứng trước khi X trở lại.
>
> **Phạm vi bổ sung:** dùng checksum H0 độc lập để chọn replica đúng, cập nhật payload sai trên OSD vừa nâng, đọc lại xác minh rồi mới cho primary/nguồn recovery. Hai phương án nâng vẫn là PA1 spare/upmap và PA2 drain weight; không đổi chúng thành “backup so với H0”. Cụm 100 TB không là prerequisite mặc định của lab H0; bỏ yêu cầu đó ở production cần quyết định phạm vi phục hồi có bằng chứng.
>
> **Provenance:** các dấu đã kiểm trong bộ source comparison `00`–`15` là trạng thái kế thừa từ file gốc; lần sửa này không tái kiểm bộ source đó. G14–G16, T30–T38 và R3A/R3B/R3H dưới đây là thiết kế dự án mới, mọi kết quả thực thi vẫn chưa được điền.

## 1. Phạm vi và cách dùng

### 1.1 Phạm vi đã có bằng chứng

- [x] Base: v16.2.5, commit đã peel tag là **0883bdea7337b95e4b611c768c0279868462204a**.
- [x] Target: v16.2.15, commit đã peel tag là **618f440892089921c3e944a991122ddc44e60516**.
- [x] Base là ancestor của target; source tree dùng để phân tích sạch và không shallow.
- [x] Inventory net diff có 2.665 file: A605, M1842, D162, R56; tổng +323.147/-176.246 dòng.
- [x] Checklist dùng finding đã kiểm chứng trong toàn bộ `00`–`15`; P0/P1/P2 chỉ là ưu tiên đọc, không phải mức rủi ro hay quyết định GO/NO-GO.
- [ ] Xác nhận **artifact base đang chạy** map tới v16.2.5: repo snapshot, package NEVRA/image digest, build SHA và mọi downstream/vendor delta.
- [ ] Xác nhận image/package thực tế sẽ triển khai đúng v16.2.15 nêu trên.
- [ ] Liệt kê mọi vendor patch hoặc custom backport. Nếu build triển khai khác endpoint đã so sánh, phải đánh giá delta đó trước khi dùng checklist này.
- [ ] Chạy review security riêng cho advisory của distro/vendor, container layers, dependencies/SBOM và downstream patches. `SEC-001–005` chỉ là cross-reference trong comparison range, không phải danh sách CVE đầy đủ của artifact.

| Nguồn | Nội dung dùng trong checklist |
| --- | --- |
| [00 — File inventory](./00-file-inventory.md) | Chốt nguồn, độ phủ và giới hạn của inventory |
| [01 — OSD/PG/recovery](./01-osd-pg-recovery.md) | EC, peering, recovery/backfill, scrub, PGLog và primary-version behavior |
| [02 — BlueStore/BlueFS](./02-bluestore-bluefs.md) | Replay/durability, OMAP, fsck/repair, allocator và rollback BlueFS |
| [03 — RocksDB/block device](./03-rocksdb-block-device.md) | OMAP iterator, range delete, reshard, exclusive device open và error handling |
| [04 — MON/OSDMap/CRUSH](./04-mon-osdmap-crush.md) | Quorum, map/state gate, release flag, placement và MON store |
| [05 — Messaging/auth/common](./05-messaging-auth-common.md) | CephX, messenger lifecycle, mixed messages, platform và connectivity |
| [06 — Config/defaults](./06-config-defaults.md) | Key bị bỏ/đổi tên, default mới và điều kiện activation |
| [07 — MGR/modules/monitoring](./07-mgr-modules-monitoring.md) | MGR failover, custom modules, Prometheus, Dashboard, autoscaler và alerts |
| [08 — Cephadm/orchestrator](./08-cephadm-orchestrator.md) | Upgrade state machine, MDS sequence, migration, registry và daemon lifecycle |
| [09 — Ceph-volume/activation](./09-ceph-volume-activation.md) | Host namespace, discovery, LVM/raw activation, dm-crypt và DB/WAL workflows |
| [10 — RADOS/RBD clients](./10-rados-rbd-clients.md) | Fast-diff/object-map, persistent cache, journal, mirror và lock recovery |
| [11 — CephFS/MDS](./11-cephfs-mds.md) | Session/caps/replay, mixed clients, CVE-2022-0670, volumes, NFS và mirror |
| [12 — RGW](./12-rgw.md) | Browser POST, write integrity, reshard, auth, TLS/MON security và multisite |
| [13 — Build/package/submodule](./13-build-packaging-submodules.md) | Package lifecycle, service policy, dependencies, dencoder và ISA-L gitlink |
| [14 — Security cross-reference](./14-security-cross-reference.md) | CVE applicability theo endpoint và liên kết về runtime owner |
| [15 — Upgrade validation](./15-upgrade-validation.md) | Bằng chứng chéo, validation gaps và ma trận kiểm chứng tổng hợp |

### 1.2 Quy ước quyết định

- **PASS:** đã có bằng chứng môi trường, kết quả test và owner ký nhận.
- **FAIL/BLOCK:** không được mở rộng phase bị ảnh hưởng.
- **N/A:** chỉ được dùng khi có bằng chứng điều kiện kích hoạt không tồn tại.
- **STOP:** dừng rollout, giữ nguyên bằng chứng và phân loại sự cố trước khi quyết định forward-fix hay rollback.
- **Conditional blocker:** chỉ chặn role, dịch vụ hoặc feature tương ứng; không tự động chặn toàn bộ binary upgrade.

Mỗi checkbox khi đóng phải có tối thiểu: owner, thời điểm, kết quả, đường dẫn bằng chứng và tiêu chí PASS đã dùng. Không đánh dấu PASS chỉ dựa vào HEALTH_OK hoặc HTTP 200.

### 1.3 Thông tin change cần điền

| Trường | Giá trị |
| --- | --- |
| Cluster / môi trường | |
| Change ID | |
| Người chỉ huy thay đổi | |
| Kênh liên lạc / escalation / incident commander dự phòng | |
| Owner MON/MGR/OSD | |
| Owner storage/network/security/monitoring | |
| Deployment mode / control path | cephadm / package-manual / khác (ghi rõ) |
| Distro, kiến trúc và cohort host | |
| Phạm vi daemon, client và external consumer | |
| Artifact base đang chạy: repo snapshot, NEVRA/image digest/build SHA | |
| Artifact target: repo snapshot, NEVRA hoặc image digest | |
| Cửa sổ dự kiến | |
| Time budget tối đa / thời gian soak tối thiểu mỗi phase | |
| Phương án rollback được chọn | |
| Last reversible point / boundary forward-only | |
| Nguồn telemetry độc lập khi Prometheus lỗi | |
| Evidence root, quy ước tên file và retention | |
| Phương án nâng OSD | PA1 — spare/upmap/giữ store; hoặc PA2 — drain CRUSH weight/canary/tăng từng nấc |
| Lựa chọn bảo vệ / mức triển khai | H + H-LAB hoặc H-ENFORCE; hoặc B100 với điểm phục hồi được giữ |
| X / S / Y–Z / PG canary và mọi PG ảnh hưởng | |
| H0 manifest, thuật toán, identity/version/range và nơi giữ độc lập | |
| Nguồn payload phục hồi đã khớp H0 / thời hạn giữ | |
| Build/verifier/enforcement và recovery API/procedure được review | |
| Quyết định về yêu cầu cụm 100 TB | PENDING / chấp thuận phạm vi thay thế / vẫn bắt buộc |
| Owner H0 / nguồn phục hồi / người chấp thuận residual risk | |
| Trạng thái cuối | HOLD / GO LAB / GO CANARY / GO PRODUCTION / NO-GO |

### 1.4 Ma trận applicability bắt buộc

Điền `YES`, `NO` hoặc `UNKNOWN` cho từng hàng. Nếu một hàng gom các subcondition dùng chung gate, cột bằng chứng phải trả lời từng subcondition: ghi `YES` nếu có ít nhất một điều kiện đúng, `UNKNOWN` nếu chưa có điều kiện đúng nhưng còn điều kiện chưa biết, và chỉ ghi `NO` khi tất cả đều không tồn tại. Chỉ `NO` có bằng chứng mới chuyển gate/test liên quan thành `N/A`; `UNKNOWN` là blocker của phase chịu tác động.

| Điều kiện / feature | YES/NO/UNKNOWN | Bằng chứng As-Is | Owner | Gate/test phát sinh |
| --- | --- | --- | --- | --- |
| Cephadm quản lý cluster | | | | G08, T26, R1 |
| Có kế hoạch dùng staggered filters/limit | | | | G08, T26A, R1 |
| Topology có từ 3 MGR | | | | G08, T26A |
| Registry private cần credential | | | | G08, T26 |
| Registry insecure/TLS bypass | | | | G08, T26 |
| Air-gap/offline artifact distribution | | | | G00/G08, T00/T26 |
| Có host unreachable hoặc maintenance khi mở change | | | | G08, T26B |
| Ingress/HAProxy do cephadm quản lý | | | | G08, T26B |
| iSCSI do cephadm quản lý | | | | G08, T26B |
| NFS do cephadm quản lý hoặc legacy NFS migration | | | | G08, T26/T26B |
| Monitoring stack do cephadm quản lý | | | | G05/G08, T04/T13/T14A/T26B |
| Direct RPM v16.2.5 → v16.2.15 | | | | G12, T29A |
| DEB deployment hoặc custom DEB pipeline | | | | G12, T09A |
| Custom/vendor package hoặc image delta | | | | G00, T00 |
| Custom source build/CMake/toolchain | | | | G00/G12, T09A |
| AArch64 host/artifact | | | | G07/G12, T05/T09A/T29B |
| FIPS/OpenSSL policy | | | | G07/G11, T05/T24C |
| Mixed distro hoặc architecture cohort | | | | G00/G12, T00/T29 |
| EC pool | | | | G01/G07, T05/T16 |
| Stretch mode | | | | G03/G07, T25 |
| mClock scheduler | | | | G04, T20 |
| CIDR range-blocklist được automation/runbook dự định dùng | | | | G03/G13, T10B |
| `require_osd_release` dưới Pacific hoặc có OSD pre-Pacific/offline | | | | G03, T10A |
| Pool automation dùng `pg_num_min/max`, ratio, bulk/noautoscale | | | | G06/G07, T15/T15A |
| Recovery runbook dùng `ceph-monstore-tool`/`osdmaptool` write path | | | | G03, T10D |
| Store/history pre-Pacific hoặc legacy OMAP/SnapMapper | | | | G01/G02, T06 |
| Raw OSD | | | | G09, T27 |
| LVM OSD | | | | G09, T27 |
| dm-crypt OSD | | | | G09, T27 |
| Multipath device | | | | G04/G09, T02/T27 |
| Separate block.db/block.wal | | | | G02/G09, T01/T19/T27 |
| CephFS đang phục vụ | | | | G07/G11, T23 |
| CephFS multi-rank hoặc standby-replay | | | | G08/G11, T23A/T26 |
| Manila native CephFS **và** cluster đã nâng từ Nautilus hoặc cũ hơn | | | | G11, T23B |
| CephFS NFS export | | | | G08/G11, T23B/T26 |
| CephFS subvolume/clone/purge | | | | G11, T23B |
| CephFS snapshot mirror | | | | G11/G12, T09A/T23B |
| RGW Browser POST | | | | G11, T24B |
| RGW Vault | | | | G07/G11, T05/T24C |
| RGW IAM/STS/CORS/cross-tenant policy | | | | G11, T24B |
| RGW dynamic reshard | | | | G11, T24A |
| RGW lifecycle/GC/FIFO/notification | | | | G11, T24A |
| RGW multisite | | | | G11, T24A |
| Cluster cố ý tắt CephX | | | | G11, T24 |
| TLS 1.0/1.1 hoặc TLS 1.2-only client/proxy | | | | G06/G11, T14/T24 |
| RBD fast-diff/object-map | | | | G10, T28 |
| RBD journal | | | | G10, T28/T28A |
| RBD PWL/persistent cache | | | | G10, T28/T28A |
| RBD mirror | | | | G10, T24C/T28B |
| Custom/third-party MGR module | | | | G06, T12 |
| Dashboard/VIP/LB/API client | | | | G06, T14 |
| Custom Prometheus/metric consumer/alert automation | | | | G05/G06, T04/T13/T14A |
| Progress module được dùng làm rollout/recovery signal | | | | G06, T17A |
| `ceph-crash` được cài/enabled/running trên host | | | | G12, T29 |
| `cls/cmpomap` U64/empty-value consumer | | | | G13, T08 |
| MON IPv6 mount path | | | | G13, T09 |
| Automation dùng target CLI msgr/range/named args | | | | G13, T09 |
| `ceph-dencoder` dùng cho recovery/debug/package validation | | | | G12/G13, T09A |
| PA1 dùng spare/upmap, dừng X sớm để giữ store | | | | G14, T30, R3A |
| PA2 drain CRUSH weight=0 rồi canary/tăng weight | | | | G14, T31, R3B |
| H0 chọn nguồn khớp và sửa payload trên X | | | | G15/G16, T32–T37, R3H |
| H0 cần bao phủ dữ liệu đang ghi/metadata/mapping biến đổi | | | | G15, T32/T33/T35/T37 |
| Không dùng cụm payload 100 TB trong production | | | | G16, T36/T38, quyết định phạm vi phục hồi |
| Có giữ/dự định dùng B100 làm nguồn độc lập | | | | G16, T38; G10/G11 và mirror/multisite tests nếu áp dụng |

RBD mirror/RGW multisite không được tự đánh N/A chỉ vì bỏ đề xuất cụm 100 TB: dịch vụ có thể đã được dùng ở nơi khác. Chỉ N/A sau inventory. EC hoặc CephFS đang có trên X vẫn phải giữ các gate hiện hữu; MVP H0 chỉ replicated RGW/RBD không bao phủ chúng.

### 1.5 Guardrail, time budget và điều kiện resume

Không có ngưỡng số chung an toàn cho mọi cluster. Mỗi hàng phải lấy từ SLO, baseline và capacity thực; để trống hoặc ghi “quan sát” không đủ điều kiện GO.

| Signal | Baseline / cửa sổ đo | Warning | STOP | Nguồn độc lập | Phase áp dụng | Điều kiện recovery/resume | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Quorum/election, daemon availability và restart count | | | | | | | |
| Client error rate, p95/p99 latency và throughput | | | | | | | |
| PG degraded/incomplete/inconsistent/unfound/stuck | | | | | | | |
| Recovery/backfill/scrub rate và backlog | | | | | | | |
| OSD device/DB/WAL free space, latency và fragmentation | | | | | | | |
| MON store size/free/trend và retained maps | | | | | | | |
| CPU/RSS, disk queue, network reset/reconnect | | | | | | | |
| Prometheus scrape/parser/golden-query và alert delivery | | | | | | | |
| RBD/CephFS/RGW correctness hoặc service-specific SLO | | | | | | | |
| H0 MATCH/MISMATCH/STALE/UNKNOWN, backlog/tuổi và coverage | | | | | | | |
| Thời gian phát hiện→chặn, quyền primary/source/read ngoài phạm vi | | | | | | | |
| Nguồn H0 còn hợp lệ, job sửa/retry, version drift và read-back sau sửa | | | | | | | |
| PA1 degraded PG-seconds / PA2 PG ngoài canary / byte ra-về | | | | | | | |

- [ ] Mỗi phase có deadline, soak tối thiểu, người ra quyết định và thời điểm tự động STOP nếu thiếu telemetry.
- [ ] Resume chỉ sau khi signal trở lại trong ngưỡng qua một cửa sổ ổn định đã định, nguyên nhân có disposition và owner ký; không resume chỉ vì `HEALTH_OK` xuất hiện lại.

### 1.6. Liên kết với kế hoạch PA1/PA2 + H0

Đọc cùng `ceph-osd-upgrade-lab-production-plan(1).md`, đặc biệt mục 5–8.7 và ma trận lỗi mục 9. Checklist này vẫn chỉ xác nhận hop **16.2.5 → 16.2.15**; không tự chuyển PASS sang Quincy/Reef.

| Nhãn trong plan | Nghĩa | Gate checklist |
| --- | --- | --- |
| U0–U5 | Chuẩn bị, rút PG, nâng, canary và hoàn tất một X | G14 + R3A/R3B |
| HG0–HG2 | Tham chiếu/nguồn tốt, cách ly rejoin, kiểm bản replica X | G15/G16 + R3H |
| HG3–HG5 | Cấp quyền đúng version, primary canary và mở rộng | G15 + R3H/R4 |
| PA1-H / PA2-H | Hai cách nâng dùng chung H0; H-LAB hoặc H-ENFORCE được ghi riêng | T30/T31 + T32–T37 |
| B100 | Đối chiếu hoặc giải pháp payload độc lập được giữ | G16/T38 |

**Chuẩn dữ liệu:** checksum H0 chỉ chọn nguồn đúng nếu được tin cậy và gắn đúng identity/version/range. Dữ liệu từ nguồn khớp phải được sao chép qua recovery/procedure đã kiểm, rồi đọc lại X đối chiếu. Không thay checksum metadata để làm dữ liệu sai thành “đúng”; không dùng đa số thay nguồn H0.

**Giới hạn:** H-LAB là quan sát/phát hiện, chưa phải cơ chế chặn dùng bản chưa verify. H-ENFORCE và H0 điều phối recovery là phần cần phát triển/review/test, không có sẵn chỉ bằng affinity/upmap. H0 không phục hồi được khi không còn payload nào khớp; nếu requirement production vẫn cần bản độc lập thì nhánh H đơn lẻ chưa đáp ứng.

## 2. Gate tổng hợp trước khi nâng cấp

| Gate | Điều kiện PASS tối thiểu | FAIL/BLOCK khi | Finding |
| --- | --- | --- | --- |
| G00 — Artifact | Chốt cả base đang chạy và target bằng repo snapshot/signature, package NEVRA hoặc image digest/build SHA theo từng cohort; SBOM/package manifest, vendor/custom delta và security advisories/dependencies đã review; giữ artifact base phục vụ failback | Không map được base về v16.2.5 đã phân tích, không truy vết được target, host pull khác digest, downstream delta/CVE review chưa đóng | 00, BLD-004–008, SEC-001/002 |
| G01 — Cluster health | Mọi WARN/ERR, PG bất thường, scrub backlog, daemon down và counter/alert đổi nghĩa đều có baseline, owner và disposition | Có mount/replay error, checksum mismatch, unexplained inconsistent/unfound, scrub stuck, quorum bất ổn hoặc daemon restart loop | OSD-002/003/004/008/010/012/014, BS-002/003/008/010, MON-003 |
| G02 — Rollback storage | Có restore per-OSD đã test, hoặc forward-only/rebuild strategy được phê duyệt và diễn tập | Runbook chỉ ghi “hạ package về 16.2.5” sau khi OSD target đã ghi BlueFS | BS-001, OSD-007 |
| G03 — MON control plane | Quorum/rank ổn định; MON store, retained maps và free space đủ theo guardrail môi trường | Election loop, Paxos không catch-up, store gần cạn hoặc headroom chưa biết | MON-003/006/009 |
| G04 — Device/config safety | Device ownership duy nhất; allocator override hợp lệ; effective config đã được so | Alias cùng major:minor chưa giải thích, invalid allocation unit, stale/renamed key chưa có xử lý | BS-007, KVBD-005/006, CFG-002–007 |
| G05 — Monitoring stop/go | Target active MGR scrape parse được, up=1, golden queries có dữ liệu; hoặc có telemetry độc lập đã phê duyệt | Duplicate HELP/TYPE, scrape fail, hoặc standby body rỗng bị coi là healthy | MGR-005/006 |
| G06 — MGR/mixed consumers | ms_die_on_bad_msg giữ false/default hoặc không tạo mixed target-MON/base-MGR; custom module, Dashboard TLS/API, autoscaler và consumer schema đã qua canary | Fatal option true khi còn pairing này, unknown-message crash/reset loop, metadata không hội tụ, callback im lặng, TLS client lỗi hoặc PG action bất ngờ | MSG-009, MGR-001–008 |
| G07 — Service-specific | Mọi dịch vụ đang dùng có test theo điều kiện: CephFS, RGW, RBD, stretch, FIPS/AArch64 | Dịch vụ áp dụng nhưng chưa có inventory hoặc test tương ứng | MON-005/007, MSG-005/008, CFG-003/004, MGR-008, RBD-001–007, CEPHFS-001–008, RGW-001–008 |
| G08 — Cephadm state/rollback | Chụp migration/action/host state; registry pull từng host PASS; MDS preparation/cleanup và stop/resume đã rehearsal; manifest staggered, old/new container name và config specialized service đã kiểm; đã chọn forward-only hoặc failback trước migration 5 | Migrate lên 5 nhưng còn dựa vào base reconciliation; host unreachable chưa xử lý; action chỉ `scheduled/starting`; MDS/config/service state không phục hồi hoặc render sai | ADM-001–009 |
| G09 — Activation/device | Inventory base và target khớp device/LV/raw topology; encrypted OSD canary activation/restart PASS; migrate/zap/provision tách change | Host namespace/discovery sai, DB/WAL không tìm thấy, dm-crypt mapper/key lỗi hoặc destructive workflow bị gộp | CVOL-001–006 |
| G10 — RBD clients/cache | Có client/image-feature matrix; SSD PWL base cache đã chứng minh clean/empty và procedure đưa nó sang trạng thái target-compatible do integration/vendor phê duyệt đã rehearsal; mirror/failover và diff correctness PASS nếu áp dụng | Cache layout 0 bị target từ chối, dirty state chưa xử lý, procedure bị giả định là in-place migration, hoặc checksum/diff/journal/mirror không hội tụ | RBD-001–007 |
| G11 — CephFS/RGW security và correctness | Applicability CVE đã audit; mọi serving endpoint/daemon được canary/drain; CephFS session/mixed-client/replay và RGW write/auth/TLS/multisite/worker tests áp dụng PASS; bucket repair bị tách change | CephX path caps chưa audit khi CVE-2022-0670 áp dụng; Browser POST còn base; session/write checksum/auth decision/TLS/MON connection sai hoặc repair bị dùng như smoke test | CEPHFS-001–008, RGW-001–008, SEC-003/005 |
| G12 — Package/service boundary | Đúng direct base→target transaction đã rehearsal; systemd/sudoers/cephadm-user/SELinux/ceph-crash đã kiểm trên OS thực; DEB/dependency/Python layout, dencoder plugins, custom build/toolchain, mirror assets và ISA-L/AArch64 smoke PASS hoặc N/A có provenance | Old scriptlet xóa key/user; service policy chặn device; ceph-crash lỗi quyền; dependency/plugin/build/service asset không đồng bộ hoặc không tái lập | BLD-001–010, VAL-001/005, SEC-004 |
| G13 — Validation coverage | Có run artifact cho exact base→target hoặc plan bù từng exclusion; cmpomap empty-U64, IPv6 mount, CLI parser và dencoder test áp dụng đã PASS; release-note/legacy suite chỉ là evidence hỗ trợ | Dùng recipe chưa chạy, legacy suite hay release note làm acceptance duy nhất; intentional skip không có compensating test | VAL-002–008 |
| G14 — Phương án nâng và placement | PA1 hoặc PA2 đã rehearsal; X/S/peer/C hợp lệ, đúng up/acting/primary; đủ capacity, ownership, budget và điều kiện dừng | PA1 giảm replica vượt budget; PA2 có PG ngoài canary; nhầm weight/affinity, remap drift, native cleanup giữ store khác giả định | Thiết kế PA1/PA2, T30/T31 |
| G15 — H0 chọn nguồn, sửa và cấp quyền | HG0–HG5 đúng phase; tham chiếu/version/coverage rõ; chọn nguồn khớp, ràng buộc source+version, sửa payload/read-back đạt; enforcement trước primary/source/read đã test | Chỉ GET qua Y nhưng chứng nhận X; dùng majority hoặc version cũ; sửa hash thay dữ liệu; auto-promote/source trước verify; stale/UNKNOWN vẫn mở quyền | Thiết kế H0, T32–T37 |
| G16 — Khả năng phục hồi và yêu cầu 100 TB | Nguồn payload đúng, retention/checkpoint và bài phục hồi đã thử; mô hình H/B100 cùng residual risk được duyệt; production có quyết định rõ nếu bỏ cụm thứ hai | Không nguồn đúng nhưng coi H0 là backup; requirement payload độc lập còn bắt buộc nhưng chưa đáp ứng; restore/RPO/RTO chỉ giả định | Thiết kế phục hồi, T36/T38 |

**Ý nghĩa của HOLD hiện tại:** acceptance của tài liệu đã hoàn tất, nhưng chưa có As-Is, lab/canary evidence và sign-off của cluster đích. Đây chưa phải kết luận rằng 16.2.15 không thể nâng cấp.

## 3. Checklist As-Is bắt buộc

### 3.1 Cluster, topology và baseline chung

- [ ] Ghi deployment mode và cơ chế quản lý daemon. Chỉ inventory ở pha này; procedure cephadm/orchestrator thuộc phần 08.
- [ ] Chốt nhánh rollout sẽ dùng: cephadm, package/manual hay orchestrator khác; không trộn semantics/state machine của các nhánh trong một runbook.
- [ ] Lưu version từng MON, MGR, OSD và daemon dịch vụ; liệt kê daemon down/offline có thể rejoin.
- [ ] Lưu health summary/detail và phân loại từng cảnh báo: có từ trước, chấp nhận tạm thời, hay phải sửa trước rollout.
- [ ] Chụp MonMap, OSDMap, CRUSH map, pool properties, daemon tree và config database.
- [ ] Lưu baseline client error rate, p95/p99 latency, throughput, recovery/backfill rate, CPU/RSS, disk latency và network reset.
- [ ] Định nghĩa guardrail bằng số theo SLO/capacity của cluster. Các báo cáo không cung cấp ngưỡng Production chung, nên không tự bịa threshold.
- [ ] Chọn failure domain cho canary; không restart đồng thời nhiều daemon trong cùng failure domain khi chưa chứng minh an toàn.
- [ ] Inventory client ngoài cluster, automation/operator CLI và external consumer; xác định chúng có nằm trong change hay vẫn ở base sau khi daemon full-target.

### 3.2 OSD, PG, recovery và workload

- [ ] Inventory pool replicated/EC, size/min_size, EC profile và async-recovery override. [OSD-001/002]
- [ ] Ghi PG degraded, incomplete, inconsistent, unfound, peering, remapped và stuck; lưu acting set/primary baseline. [OSD-001/002/004/006/007/008]
- [ ] Ghi các cờ noout, noin, noup, nodown, norecover, nobackfill, noscrub, nodeep-scrub và lý do tồn tại.
- [ ] Ghi scrub/deep-scrub backlog, timestamp cuối, reservation và lỗi đang mở. [OSD-004]
- [ ] Đo PGLog dups, RocksDB/DB free space, OSD boot status và headroom. [OSD-003]
- [ ] Ghi recovery/backfill overrides, capacity headroom, stretch mode và lịch sử backfill interruption. [OSD-005/006]
- [ ] Ghi compat feature SNAPMAPPER2 và nguồn gốc các store rất cũ. [OSD-010]
- [ ] Xác định có profile rbd-read-only, cache tier, dedup/object manifest, set_chunk hoặc snapshot clone hay không. [OSD-013/014]
- [ ] Lưu OSD startup/shutdown duration, map-delivery lag và lịch sử daemon boot/restart fault; không coi process start là OSD đã sẵn sàng phục vụ. [OSD-012, MSG-003]

### 3.3 BlueStore, BlueFS, RocksDB và block device

- [ ] Với từng OSD, lưu media class và topology block, block.db, block.wal; dung lượng, free space, spillover và fragmentation. [BS-006/007/010]
- [ ] Ghi effective bluestore_prefer_deferred_size và layout WAL/DB/SLOW. [BS-003]
- [ ] Ghi mọi override bluefs_shared_alloc_size, allocator block size/unit và volume-selection policy. [BS-006/007]
- [ ] Ghi legacy OMAP warning/state, lịch sử fsck/repair, repair-on-open, shared-blob error, clone/snapshot density và osd_memory_target. [BS-004/005]
- [ ] Ghi kiến trúc/page size, đặc biệt AArch64 64 KiB, nếu có provisioning hoặc label/device path tương ứng. [BS-009]
- [ ] Lưu cache/onode/refcount/small-write workload đại diện và baseline counter/alert đã đổi nghĩa; không suy hiệu năng từ code diff. [BS-008/010]
- [ ] Ghi effective bluestore_rocksdb_cf/cfs, CF sharding spec, iterator-bounds, delete-range threshold và compact-on-deletion options. [KVBD-001–004]
- [ ] Đối chiếu device/LVM/symlink/container path về major:minor; chứng minh mỗi device chỉ có một writer/owner. [KVBD-005/006]
- [ ] Xác nhận runbook có hay không các thao tác reshard, compact, repair, import, migrate, set-superblock hoặc relabel.

### 3.4 MON, maps, placement và auth/messaging

- [ ] Lưu MON quorum, rank, leader, election epoch/history, quorum age, connection score và clock/network health. [MON-003]
- [ ] Lưu dung lượng/free space và trend của MON store, retained OSDMap epochs, health-store/mute state. [MON-006/009]
- [ ] Lưu require_osd_release, feature bits và mọi OSD pre-Pacific, kể cả OSD đang offline. [MON-001/002]
- [ ] Xác định có CIDR/range blocklist state hoặc automation gọi feature này hay không. [MON-001, MSG-007]
- [ ] Ghi pending PG merge, pg_temp, upmap exception và balancer/pool automation. [MON-006/008]
- [ ] Nếu stretch: lưu tiebreaker, MonMap, CRUSH rules/buckets/weights và site recovery state; nếu không, ghi N/A có bằng chứng. [MON-007]
- [ ] Inventory config mask theo location, host và device class; lấy effective config trên OSD đại diện mỗi nhóm. [MON-011]
- [ ] Ghi msgr1/msgr2 usage, ms_die_on_bad_msg, reconnect/reset baseline, fast-shutdown flags và MON priority/weight. [MSG-002/003/009]
- [ ] Ghi explicit/auto public_addr và cluster_addr, interface state và crush_location_hook. [MSG-006]
- [ ] Lưu CephX rotating-key version, auth retry/session reopen và MON↔MGR reconnect baseline. [MON-004, MSG-001/009]
- [ ] Liệt kê việc dùng `ceph-monstore-tool`/`osdmaptool` hay offline map/store repair trong runbook; mọi write path của tool phải bị tách khỏi rolling upgrade. [MON-010]

### 3.5 Config và dịch vụ có điều kiện

- [ ] Export cả stored config database và effective config theo từng daemon/role; không chỉ lưu config dump thô. [CFG-001–007, MON-011]
- [ ] Tìm sáu key cũ nêu ở bảng mục 4.1 và ghi scope/owner của từng occurrence.
- [ ] Ghi effective OSD defaults đổi ở mục 4.2 và mọi override tương ứng.
- [ ] Nếu dùng mClock: lưu scheduler, media classification, capacity HDD/SSD, skip/force benchmark, thời gian boot và I/O baseline. [OSD-011, CFG-002]
- [ ] Nếu dùng CephFS: lưu fs dump, compat flags, active/standby-replay, MDS/client config, client type/version và consumer perf-stat. [MON-005, MSG-008, CFG-003, MGR-008]
- [ ] Nếu dùng RGW Vault: lưu CA, certificate policy, rgw_verify_ssl và rgw_crypt_vault_*; ghi FIPS/OpenSSL mode nếu áp dụng. [MSG-005, CFG-004]
- [ ] Nếu dùng RBD mirror/PWL: lưu mirror snapshot count/backlog và telemetry hiện tại. [CFG-004/007]
- [ ] Inventory CPU architecture và compiler/package trên fleet; đánh dấu host AArch64. [MSG-005]
- [ ] Ghi storage/KV opt-in và effective values (iterator bounds, compact-on-deletion, RocksDB sharding/CF, pool/autoscaler controls); phân biệt default tự kích hoạt với operator action. [CFG-005/006]

### 3.6 MGR, Dashboard và monitoring

- [ ] Lưu active/standby MGR, enabled modules, service URI và failover baseline. [MGR-001/002]
- [ ] Liệt kê mọi custom/third-party MGR module, package/site path, method notify() và NOTIFY_TYPES. [MGR-003]
- [ ] Lưu autoscaler mode/flags, target_size_ratio, pg_num_min/max, bulk/noautoscale và pending recommendation. [MGR-004]
- [ ] Export golden Prometheus exposition: metric names, types, labels, cardinality và representative queries. [MGR-005/006]
- [ ] Ghi discovery/LB/scraper target; xác định liệu scraper có thể chạm MGR standby hay không. [MGR-006]
- [ ] Export runtime rules, checksum, Alertmanager routes/inhibitions/silences, ticket automation và notification destinations. [MGR-010]
- [ ] Inventory browser, API client, reverse proxy, VIP/LB, certificate chain và SNI; xác nhận TLS capability. [MGR-007]
- [ ] Nếu dùng stats/cephfs-top/parser riêng, lưu golden schema và rank-0 failover baseline. [MGR-008]

### 3.7 Cephadm, package và host activation

- [ ] Ghi deployment mode, `migration_current`, active/standby MGR, upgrade state/target, host maintenance/offline state, daemon actions đang pending và mọi staggered-upgrade filter/limit. [ADM-002–006]
- [ ] Với từng MGR, ghi image digest, `deployed_by`, restart count và topology có từ 3 MGR hay không. [ADM-002]
- [ ] Ghi SSH/reachability từng host, phân biệt maintenance với unreachable; map vị trí NFS/HAProxy và replacement candidate. [ADM-005]
- [ ] Nếu có legacy NFS, lưu service `nfs.ganesha-*`, `.nfs` pool/namespace, export count/content, grace; đồng thời lưu `_admin` placement và vị trí registry credential cũ/new config-key mà không lộ secret. [ADM-004]
- [ ] Lưu baseline action/progress terminal state, events và policy firewall/port; pending/scheduled/starting phải hiện rõ trong evidence. [ADM-006]
- [ ] Với staggered upgrade, lưu exact phase manifest: filter, daemon type, service/host set, limit, expected count và remaining count; ghi trạng thái trước/sau mỗi MGR handoff. [ADM-003]
- [ ] Inventory registry theo host: image digest, credentials, TLS/insecure policy và kết quả inspect/pull bằng artifact target; không suy từ một host đã pull thành công. [ADM-007]
- [ ] Nếu có CephFS do cephadm quản lý, lưu `max_mds`, standby-replay, FS flags và trạng thái MDS trước sequence chuẩn bị. [ADM-001]
- [ ] Inventory old dot-name/new dash-name container, effective systemd unit, timeout, orphan container và read-only exec path trên từng cohort chưa redeploy. [ADM-008]
- [ ] Export spec và rendered config của ingress/iSCSI/NFS/Prometheus/Alertmanager/Grafana; chụp VIP, port, TLS, session, retention và post-action baseline. [ADM-004/009]
- [ ] So device inventory từ host và container: LV/VG/tag, raw device, PARTUUID, multipath, DB/WAL, dm-crypt mapper/key và activation unit. [CVOL-001–003/006]
- [ ] Export drive-group/OSD specs và candidate diff theo stable serial/WWN allowlist; không dựa duy nhất vào `/dev/*` path. [CVOL-003/004]
- [ ] Với dm-crypt, lưu effective `osd_dmcrypt_key_size`, lockbox/config-key accessibility và mapper UUID; kiểm log evidence không chứa LUKS secret. [CVOL-006]
- [ ] Ghi distro/package manager, phiên bản systemd/SELinux, package ownership của sudoers/service files, cephadm user/home/`authorized_keys` và quyền `/var/lib/ceph/crash`. [BLD-001–003/009, VAL-001]
- [ ] Ghi local systemd/sudoers drop-ins, effective `CEPH_AUTO_RESTART_ON_UPGRADE`, và việc `rbd-immutable-object-cache` có được cài/chạy hay không cùng state/restart policy. [BLD-001–003/009]
- [ ] Theo từng host/cohort, ghi `ceph-crash` installed/enabled/running, effective unit/User/Group, process UID/GID/groups, crash-dir ownership và backlog. [VAL-001, SEC-004]
- [ ] Ghi package source/repo snapshot, dependency closure, Python install path, dencoder executable/plugins, custom compiler/CMake flags và `cephfs-mirror` service assets nếu áp dụng. [BLD-004–008/010, VAL-005]

### 3.8 Client và dịch vụ dữ liệu

- [ ] Inventory librbd/QEMU/krbd/rbd-nbd theo host; image features, fast-diff/object-map, journaling; PWL file/layout và `present/clean/empty`; exclusive-lock owner; recovery copy; client cohort; mirror version/primary/snapshot queue ở cả hai site; automation dùng `rados cppool`. [RBD-001–007]
- [ ] Với CephFS, ghi client kernel/FUSE/libcephfs, session encoded size/completed requests và `mds_session_metadata_threshold`; damaged/failed/laggy rank, pre-16.2.5 MDS, replay progress; Manila/history; clone/purge jobs; NFS FSAL user/path/access; mirror assignment và last-synced snapshot. [CEPHFS-001–008]
- [ ] Với RGW, ghi mọi daemon sau LB, frontend/certificate/TLS/header/timeouts, `ms_mon_client_mode`, `auth_client_required`, Browser POST, multipart/versioning/object-lock; shard instance/stats; planned bucket-check; IAM/STS/backend auth; LC/GC/FIFO/notification endpoint+ack/backlog; multisite allowed sources, markers và backlog. [RGW-001–008]
- [ ] Ghi consumer của `cls/cmpomap` U64/empty values, MON IPv6 mounts và automation dùng msgr/range address hoặc named CLI args; nếu không tìm được consumer thì ghi phương pháp tìm kiếm. [VAL-002–004]
- [ ] Audit security applicability bằng topology/config thực; không đánh dấu N/A chỉ vì CVE doc nằm trong target tree. [SEC-001–005]
- [ ] Ghi rõ SEC-001/002 đã được fix trước base và chỉ dùng làm provenance/hygiene; không tính chúng là lợi ích mới của target. [SEC-001/002]
- [ ] Kiểm `auth_allow_insecure_global_id_reclaim` và health alerts/client cũ liên quan; nếu còn insecure reclaim thì mở security workstream riêng, không ghi là target delta đã xử lý. [SEC-001]

### 3.9 H0 và phương án đưa OSD trở lại

- [ ] Inventory **mọi** PG của X trong up/acting, primary, pool/rule/class/failure domain; nếu lẫn EC/CephFS ngoài phạm vi H0 thì không gắn nhãn toàn X được bảo vệ.
- [ ] Lưu W0, R0, A0, balancer, autoscaler, cờ gồm norebalance và mọi ngoại lệ upmap/pg_temp; ghi ownership/restore theo từng entry.
- [ ] Chọn PA1/PA2, target S/peer, byte cần chuyển, capacity và khoảng giảm replica; giữ workload/offered load ngang nhau khi so hai PA.
- [ ] Lưu H0 manifest theo version/checkpoint từ nguồn độc lập, quyền sửa, retention, hash thuật toán và mapping ứng dụng↔RADOS.
- [ ] Có phép kiểm payload **trên bản X**, cùng version/range; không dùng một GET qua primary/cache để thay bằng chứng local X.
- [ ] Inventory OMAP/xattr/RGW index/RBD metadata, snapshot/discard/delete-recreate và phạm vi chưa có coverage.
- [ ] Lưu nguồn payload Y/Z/S đủ điều kiện phục hồi và bằng chứng hash/version; peer chạy bản cũ không tự được xem là đúng.
- [ ] Ghi capability H-LAB/H-ENFORCE, hook/API source selection và contract version/PG interval khi sửa; không có thì chưa tự sửa live.
- [ ] Inventory client replica-read/caching, failover/recovery paths, auto repair và automation có thể cấp quyền ngoài controller; đối chiếu effective config.
- [ ] Có trạng thái sau restart/partition, bảo vệ manifest khỏi rollback, dirty tracking và cơ chế vô hiệu hóa quyền; không có evidence thì không tự PASS.

## 4. Thay đổi hoặc sửa đổi cần chuẩn bị

### 4.1 Sáu key cấu hình cũ phải audit

| Key ở base | Target | Việc cần làm trước restart role liên quan |
| --- | --- | --- |
| osd_mclock_max_capacity_iops | Bị bỏ; target dùng key theo media _hdd hoặc _ssd | Nếu dùng mClock, map theo media thật, quyết định skip/force benchmark và canary; không copy mù |
| mds_max_retries_on_remount_failure | Đổi thành client_max_retries_on_remount_failure | Nếu dùng CephFS, chuyển có kiểm soát và test remount; giữ mapping rollback |
| ms_async_max_op_threads | Bị bỏ | Không map sang ms_async_reap_threshold vì khác nghĩa; test config thực và log unknown key |
| rgw_rados_pool_pg_num_min | Bị bỏ | Sửa automation tạo pool; không giả định pool hiện hữu tự thay |
| rgw_bucket_quota_soft_threshold | Bị bỏ | Xác nhận quota semantics và sửa automation/runbook phụ thuộc key |
| rbd_persistent_cache_log_periodic_stats | Bị bỏ | Không coi việc bỏ key là tắt cập nhật state; cập nhật monitoring/runbook và giữ rollback mapping |

- [ ] Chụp config snapshot trước khi sửa.
- [ ] Mỗi key có owner, decision giữ/chuyển/bỏ và test trên binary target.
- [ ] Không xóa stale key trước khi rollback rehearsal hoàn tất.
- [ ] Binary base phải được test với config dự kiến dùng khi failback.

### 4.2 Default mới cần chấp nhận hoặc override có chủ đích

| Default/behavior target | Điều cần xác nhận |
| --- | --- |
| osd_client_message_cap: 0 → 256 | Backpressure, memory và client latency trong canary |
| osd_fast_shutdown_notify_mon: false → true | OSD/MON shutdown/down signal không tạo false alarm |
| osd_max_write_op_reply_len: 32 → 64 | Workload RETURNVEC/client tương ứng và PGLog behavior |
| osd_aggregated_slow_ops_logging: true | Log parser, cluster-log rate và MON DB pressure |
| osd_pg_max_concurrent_snap_trims minimum 1 | Override 0 cũ và snap-trim behavior |
| log_max_recent minimum 1 | Override 0 cũ và config validation |
| osd_rocksdb_iterator_bounds_enabled: true | OMAP correctness/boundary test |
| Dashboard minimum TLS 1.3 | Client/proxy/VIP/LB/API tương thích |
| RGW Vault verify key riêng mặc định true | CA hợp lệ hoặc policy riêng đã duyệt |
| RGW `ms_mon_client_mode=secure`, `auth_client_required=cephx` | RGW target restart vẫn authenticate/kết nối MON; cluster cố ý tắt CephX có quyết định riêng |
| Beast tắt SSLv2/3 và TLS 1.0/1.1 khi có certificate | Mọi client/proxy được hỗ trợ dùng TLS 1.2+ hoặc exception đã security-approve |

- [ ] Không override hàng loạt chỉ vì default đổi; mọi override phải có mục tiêu, owner, benchmark và rollback.
- [ ] So effective config sau restart/reconnect, vì target có thể áp dụng đúng location mask mà base từng bỏ qua. [MON-011]

### 4.3 Sửa bắt buộc theo điều kiện

- [ ] **Device mapping:** sửa alias/ownership không rõ trước first target OSD. Target dùng O_EXCL và có thể fail sớm; mở được hai writer là lỗi nghiêm trọng. [KVBD-005/006]
- [ ] **Allocator:** mọi bluefs_shared_alloc_size phải không nhỏ hơn block size và chia hết cho allocation unit; unresolved/invalid override chặn OSD rollout. [BS-007]
- [ ] **mClock:** chuyển generic capacity sang đúng _hdd/_ssd; không để cả failure domain benchmark đồng thời; WPQ không cần bị đổi sang mClock. [OSD-011, CFG-002]
- [ ] **Custom MGR module:** module có notify() phải khai báo đúng subset mon_map, pg_summary, health, clog, osd_map, fs_map hoặc command. service_map không có ở endpoint này. [MGR-003]
- [ ] **Target MON → base MGR:** nếu tổ hợp mixed này có thể tồn tại, giữ ms_die_on_bad_msg ở false/default hoặc tránh tổ hợp đó cho tới khi rehearsal PASS. ms_die_on_bad_msg=true, MGR abort/reset loop hoặc metadata version không hội tụ là blocker mở rộng MON/MGR. [MSG-009]
- [ ] **Prometheus:** chuẩn bị package/backport đã verify parser hoặc telemetry độc lập đã được phê duyệt. Không có config workaround an toàn được chứng minh trong report. [MGR-005]
- [ ] **Dashboard:** nâng client/proxy/LB lên TLS 1.3. UNSAFE_TLS_v1_2 chỉ là escape hatch có security approval, restart và retest. [MGR-007]
- [ ] **Alerts:** map 18 alertname cũ sang 58 tên target hoặc quyết định deprecate; intersection exact bằng 0. Sửa route, inhibition, silence, ticket và runbook trước runtime reload. [MGR-010]
- [ ] **CephFS:** chuẩn bị key remount mới, schema perf v2 và expectation cho throttle/prefetch/grace/eviction/session guards. [CFG-003, MGR-008]
- [ ] **RGW Vault:** nếu base dựa vào rgw_verify_ssl=false hoặc self-signed certificate, cài CA đúng hoặc thiết lập policy riêng đã duyệt trước RGW restart. [CFG-004]
- [ ] **Config automation:** parser phải hỗ trợ output/name target và phải so effective values, không chỉ stored values. [MON-011, CFG-007]
- [ ] **Package selection:** đi thẳng tới endpoint 16.2.15 theo plan; không dừng ở 16.2.8 vì regression TTL-cache trung gian đã được sửa ở endpoint target. [MGR-002]
- [ ] **Cephadm migration:** chụp `migration_current` và quyết định rollback trước khi target active MGR chạy migration 3–5. Sau state 5, không coi binary base là đường rollback reconciliation mặc định. [ADM-004]
- [ ] **Cephadm MDS:** rehearsal sequence giảm rank/tắt standby-replay và cleanup khi stop/cancel; không giả định `upgrade stop` tự phục hồi state chuẩn bị. [ADM-001]
- [ ] **Cephadm staggered/offline/action:** chốt phase manifest và expected count; unresolved unreachable host chặn phase có daemon liên quan, đặc biệt NFS/HAProxy; `scheduled`, `starting` hoặc progress chưa terminal không phải success. [ADM-003/005/006]
- [ ] **Cephadm local/specialized service:** kiểm read-only exec và stop/start cho old dot-name container; diff rendered ingress/iSCSI/NFS/monitoring config và post-action trước khi redeploy. [ADM-008/009]
- [ ] **Ceph-volume:** test inventory/activation ở host namespace cho LVM/raw và một OSD dm-crypt đại diện; mọi `zap`, prepare, migrate/new-db/new-wal là change riêng. [CVOL-001–006]
- [ ] **RBD PWL:** nếu có SSD persistent cache từ base, xác minh `present/clean/empty`, giữ recovery copy và rehearsal procedure đưa cache sạch sang trạng thái target-compatible do integration/vendor phê duyệt; target trả `-EINVAL` cho layout 0 và endpoint không chứng minh in-place migration. [RBD-002/003]
- [ ] **CephFS security:** nếu Manila native CephFS có lịch sử cluster Nautilus hoặc cũ hơn, audit CephX path caps đã cấp trước rollout; nâng binary không thu hồi cap quá rộng. [CEPHFS-005, SEC-003]
- [ ] **RGW security:** mọi endpoint Browser POST phải ở target hoặc drain; test policy negative trên từng daemon. Kiểm RGW target kết nối MON với secure/CephX defaults và legacy TLS client matrix trước đổi pool. [RGW-001/007, SEC-005]
- [ ] **Package lifecycle:** rehearsal chính xác direct RPM base→target, vì `%postun` lưu trong package base chạy sau install scriptlet target và vẫn có thể `userdel -r` cephadm ở first hop. Chỉ tiếp tục khi key/user sống sót hoặc có mitigation/package path được RPM owner duyệt; đồng thời kiểm SELinux auto-restart, sudoers/unit và `ceph-crash` user. [BLD-001–003/009, VAL-001]
- [ ] **Build/package tooling:** với DEB/custom build, kiểm dependency/Python layout, bootstrap/source scripts, compiler/CMake và service assets; với mọi artifact có dùng dencoder, binary và `denc-mod-*` phải cùng target build. Nếu dùng vendor image, ghi provenance để đóng các nhánh custom-build bằng N/A. [BLD-004–008/010, VAL-005]
- [ ] **CLI/client compatibility:** pin phiên bản CLI trong automation và test msgr-prefixed/range/named arguments; test target `mount.ceph` với bracketed IPv6 MON khi áp dụng. [VAL-003/004]

### 4.4 Guardrail: không gộp vào rolling binary upgrade

- [ ] Không chạy offline PGLog trim hoặc mark_unfound_lost như bước preventive.
- [ ] Không chạy quick-fix legacy OMAP, fsck repair, shared-blob repair hoặc repair-on-open mới chưa test.
- [ ] Không chạy BlueFS import/migrate/new DB/WAL, set-superblock, relabel hoặc provisioning trong cùng change.
- [ ] Không reshard RocksDB, bật compact-on-deletion hoặc destructive repair trong cùng change.
- [ ] Không tạo CIDR range-blocklist trong mixed phase.
- [ ] Không nâng require_osd_release chỉ để xóa health warning.
- [ ] Không đổi stretch topology, remove/replace MON, merge/expand PG hoặc chạy balancer lớn đồng thời nếu không phải change riêng đã test.
- [ ] Không rotate/import auth key thủ công hoặc rebuild monstore/viết lại OSDMap như bước upgrade thường lệ.
- [ ] Không reload/redeploy bộ alert target trước khi Prometheus parser gate và alert mapping đã PASS.
- [ ] Không dùng `orch host rm --offline --force`, forced container rename/remove hoặc daemon replacement để xử lý nhanh host mất kết nối trong canary. [ADM-005/008]
- [ ] Không trigger RGW dynamic reshard, bucket repair/`--fix`, GC/LC trim hay multisite log trim như smoke test; read-only diagnostics phải được phân biệt với mutation. [RGW-003/004/005/008]
- [ ] Không dùng `rados cppool`, self-managed snapshot mutation, lock break/blocklist mutation hoặc cache discard như test thường lệ trên dữ liệu Production. [RBD-002/003/005/007]
- [ ] Không chạy `ceph-monstore-tool`, `osdmaptool` write mode hay `ceph-objectstore-tool` repair trên live state để “sửa nhanh” rollout. [MON-010, BS-004/005/009, KVBD-007]

Các thao tác trên cần change riêng, backup/clone phục hồi được, peer review, tiêu chí dừng và test chuyên biệt.

### 4.5 H0 repair và enforcement là thay đổi thiết kế riêng

- [ ] Chốt fault model và threat boundary: lỗi local media, sai logic cùng checksum, cùng sai giữa replica, sai ghi mới sau promote; không nói một lần H0 PASS bảo vệ mọi bug tương lai.
- [ ] Tách build native và custom H0; review diff/hook, protocol negotiation, crash/restart và mixed-version trước khi gộp vào upgrade.
- [ ] Recovery chỉ được tự động khi có nguồn khớp H0 đúng version, phạm vi hẹp, cơ chế tuần tự hóa, read-back và budget retry đã test. NO_VALID_SOURCE/UNKNOWN/STALE chặn apply; có disposition riêng.
- [ ] Chuẩn bị barrier/dirty tracking để không sửa đè ghi mới; không trộn restore checkpoint cũ với repair replica current version.
- [ ] Định nghĩa quyền primary/source/replica-read theo PG/version; affinity OSD-wide và polling không đủ chứng minh enforcement trước I/O.
- [ ] Không tắt gate bắt buộc vì p99 tăng; giảm tốc/mở batch chậm lại, đo chờ I/O. Hậu kiểm bất đồng bộ giữ nguyên ACK thì phải báo cửa sổ phát hiện trễ.

Mục 4.4 vẫn chặn repair tùy tiện trong rolling change. H0-guided repair chỉ được đưa vào MOP sau khi phần chức năng này đã có rehearsal và scope riêng được review; không coi một lần `pg repair` là đã chọn đúng nguồn theo H0.

## 5. Activation: điều gì tự xảy ra, điều gì không

| Nhóm | Activation | Lưu ý |
| --- | --- | --- |
| OSD/PG fixes | Tự động theo binary OSD/primary target | Trong mixed phase, đổi primary có thể đổi outcome; phải test primary base và target |
| BlueFS replay/durability và opcode mới | Local theo OSD target khi mount/ghi metadata | Không phải wire incompatibility, nhưng tạo rollback boundary per-OSD |
| OMAP iterator/range delete và O_EXCL | Tự động sau OSD target restart/data path | Compact-on-deletion vẫn mặc định tắt |
| MON election/auth/map/config mask fixes | Theo MON leader/session target | Leader base vẫn giữ behavior cũ trong mixed phase |
| Messenger/lifecycle fixes | Local theo process target | Peer base vẫn có race cũ ở phía của nó |
| Default/config changes | Khi role target restart hoặc đi qua code path tương ứng | Stored config giống nhau không bảo đảm effective behavior giống nhau |
| mClock benchmark | Chỉ khi scheduler là mclock_scheduler và điều kiện skip/force/capacity đúng | Có thể tăng boot time/I/O và ghi capacity vào MON config |
| MGR behavior | Theo MGR đang active | Failover base ↔ target có thể đổi metrics, events và recommendation |
| Prometheus duplicate metadata | Target MGR active, module được scrape và có ít nhất một pool | HTTP 200 không chứng minh parser chấp nhận |
| Dashboard TLS 1.3 | Khi target Dashboard server khởi động/promote | Client TLS 1.2-only có thể mất kết nối |
| CIDR range-blocklist, pool/bulk controls, repair/tools | Opt-in/operator action | Không cần kích hoạt để hoàn tất patch upgrade |
| Alert rules mới | Chỉ khi runtime file được thay và Prometheus reload/redeploy | File package đổi không chứng minh runtime rules đã đổi |
| Cephadm migration 2→5 | Khi target MGR active chạy reconciliation/migration | State 5 là rollback boundary cho base MGR; NFS/_admin side effects cần backup và rehearsal |
| Cephadm MDS preparation | Khi upgrade engine vào MDS phase | Giảm rank/tắt standby-replay; stop/cancel không tự bảo đảm restore state |
| Ceph-volume discovery/activation fixes | Khi inventory/reconcile hoặc OSD target được activate/restart | Migrate/new-db/new-wal, zap và provisioning vẫn là operator action riêng |
| RBD client fixes và PWL layout 1 | Theo từng client target mở image/cache | Daemon cluster target không nâng client; SSD layout 0 có thể bị target từ chối |
| CephFS/MDS fixes | Theo MDS/client/MGR module đang chạy target | Mixed client/MDS và failover quyết định outcome; CephX cap cũ không tự sửa |
| RGW auth/TLS/MON defaults | Theo từng RGW target restart và daemon nhận request | Base/target sau LB có thể trả auth khác; secure/CephX và TLS defaults có hiệu lực per process |
| systemd/sudoers/RPM lifecycle | Khi package được cài/nâng và unit/scriptlet chạy | Package manager/distro và policy auto-restart quyết định activation |
| `ceph-crash` hạ quyền | Khi service target khởi động | Không hạ được quyền thì process thoát; crash files phải đọc được bởi user `ceph` |
| ISA-L AArch64 relocation fix | Khi build/link target dùng gitlink mới | Không phải state migration; cần smoke trên artifact/architecture thực nếu áp dụng |
| H0-guided repair và quyền HG | Chỉ khi verifier/enforcement/recovery contract tùy biến đã triển khai và kích hoạt theo MOP | Không tự xuất hiện khi nâng 16.2.15; H0 nguồn độc lập, version binding và source selection phải có bằng chứng |

## 6. Kế hoạch test bắt buộc

Tất cả test fault injection, corruption, power-cut, repair, map trim, device mutation hoặc old-reader mount phải chạy trên lab/fixture/clone disposable. Checklist này không cho phép chạy chúng trên Production.

### 6.1 Pre-upgrade / lab

| Test | Tiền điều kiện và hành động | PASS | FAIL/STOP | Finding |
| --- | --- | --- | --- | --- |
| T00 — Artifact/config | Chốt base+target repo snapshot/signature, NEVRA hoặc image digest/build SHA theo cohort; map base thực tới v16.2.5 hoặc review downstream delta; diff package manifest/SBOM/vendor patch và review vendor/dependency advisories; nạp config thực bằng binary target trong môi trường an toàn | Mỗi host/cohort map tới đúng endpoint artifact; pre-base CVE provenance và broader artifact vulnerability review rõ; không có delta chưa review; config issue có disposition; artifact base còn truy xuất được | Base/target không truy vết, digest lệch, downstream/security delta chưa review hoặc config critical không parse | 00, CFG-007, BLD-004–008, SEC-001/002 |
| T01 — BlueFS rollback | Clone OSD 16.2.5, mount target và phát sinh đủ metadata để xác nhận target đã ghi opcode log mới; thử target replay và old reader trên clone khác | Target replay sạch; old reader chạm đúng unrecognized op/-EIO dự kiến; restore pre-upgrade image đã được chứng minh | Không chứng minh được opcode/biên downgrade, restore thất bại, hoặc runbook vẫn dựa vào package downgrade trên cùng store | BS-001 |
| T02 — Device alias | Dùng block aliases cùng major:minor trên device disposable | Target chặn writer thứ hai; ownership Production rõ | Hai writer mở được hoặc mapping Production chưa giải thích | KVBD-005/006 |
| T02A — Block read errno | Mock/fault-injection `pread` trên fixture với `allow_eio=true/false`, regular file và missing path; không dùng device thật | `allow_eio=true` trả `-EIO`; nhánh false theo policy; missing path fail-closed và actual errno/log được ghi nhận, automation chấp nhận endpoint có thể còn trả generic `-1`/EPERM | Read failure bị coi là success, assert, hoặc automation phân loại sai generic error thành device an toàn | KVBD-005/006 |
| T03 — Allocator config | Kiểm divisibility và khởi động scratch store với override thực | Không assert/false ENOSPC | Assert, init fail hoặc value không hợp lệ | BS-007 |
| T03A — Allocator fragmentation | Scratch store có fragmentation/layout đại diện; fill/trim qua fallback và cooldown với override thực | Allocation/fallback/cooldown có progress, metric giải thích được và không false ENOSPC | Init/allocation assert, false ENOSPC, retry không tiến hoặc resource vượt guardrail | BS-007 |
| T04 — Prometheus parser | Cho target MGR active trên staging/canary; parse toàn bộ /metrics bằng parser thật | Parse pass, target up=1, golden queries có data | Duplicate HELP/TYPE, scrape error hoặc body standby rỗng bị coi healthy | MGR-005/006 |
| T05 — Platform | Nếu áp dụng, chạy known CRC vectors trên AArch64 build/compiler thật và RGW ETag, multipart, encryption paths dưới đúng FIPS/OpenSSL package/policy | Vector/request/ETag/body đúng, không abort | Checksum/request/data mismatch hoặc abort | MSG-005 |
| T05A — Buffer/LRU fault paths | Nếu workload áp dụng, chạy fixture zero-length-tail buffer và concurrency của RGW file/NFS LRU | Không SIGABRT, double-unlock hoặc deadlock | Abort, lock fault hoặc data-path lỗi | MSG-004 |
| T06 — Conditional storage fixtures | Nếu áp dụng: legacy SnapMapper/OMAP, shared blobs, `block_cache={type=binned_lru}` reshard; compact-on-deletion với tombstone/window/trigger stats; direct-backend repair; AArch64 label | Cardinality/checksum/sharding/reopen/fsck đúng trên clone; compaction chỉ trigger đúng window và không đổi correctness | Data mismatch, memory/latency vượt budget, parse/repair/reshard/compaction lỗi | OSD-010, BS-004/005/009, KVBD-003/004/007 |
| T07 — PGLog duplicate inflation | Fixture PGLog có dups vượt ngưỡng; tạo thêm activity để quan sát warning và bounded auto-trim; chỉ thử offline trim trên stopped clone khi thật sự cần, rồi reopen DB | Warning đúng ngưỡng, auto-trim tiến có giới hạn; clone sau offline trim reopen được; RSS/DB/tombstone trong guardrail | OSD không boot/mount, PGLog decode lỗi, DB không reopen hoặc resource vượt guardrail | OSD-003 |
| T08 — cmpomap empty U64 | Trên pool disposable, tạo empty OMAP value và pin U64 compare lần lượt vào primary base/target; tách malformed non-empty case | Kết quả khớp semantics đã ghi: base failure/`-EIO` theo fixture, target coi empty là `0`; malformed vẫn lỗi; client retry không che outcome | Outcome không ổn định theo serving version, assert hoặc workload thực không chấp nhận mixed semantics | VAL-002 |
| T09 — IPv6 mount/CLI parser | Dùng target `mount.ceph` với MON IPv6; test local parser cho `v1:`/`v2:`/`any:`, bracketed IPv6+nonce, range và named args theo automation thực | MON string có brackets, mount/I/O/umount ổn định; accepted/rejected input đúng matrix và automation pin đúng CLI | Parse/mount/reconnect lỗi, malformed range được nhận hoặc automation phụ thuộc behavior base | VAL-003/004 |
| T09A — Package/build/dencoder | Trên artifact target thực: với DEB kiểm dependency/Python `dist-packages`, imports và MGR smoke; với custom pipeline build sạch hai lần, so checksum/link manifest và selected tests; parse/start/stop mirror unit nếu dùng; chạy `ceph-dencoder list_types` và representative encode/decode round-trip cho enabled common/OSD/MDS/RBD/RGW/CephFS types | Dependency/layout/import/unit đúng; custom build tái lập; binary/plugin cùng build; expected types hiện diện và round-trip được | Missing dependency/asset/plugin, import/link/`dlopen`/unknown type, version skew hoặc build không tái lập | BLD-004–008/010, VAL-005 |
| T09B — Exact-path coverage | Chạy hoặc thu run artifact của đúng base/artifact/upgrade path/target; lập register cho mọi filter/skip và compensating test. Nếu Pacific p2p đi qua 16.2.7, bổ sung direct-hop rehearsal phù hợp runbook | Có logs/result/target SHA; `cmpomap` invalid-default, `mon_mds_skip_sanity` và filtered RBD mirror-snapshot đều có disposition/test bù; legacy suites/release notes chỉ hỗ trợ | Recipe chưa chạy, endpoint/path không khớp, skip không bù hoặc release-note/legacy pass bị dùng làm acceptance duy nhất | VAL-006–008 |

### 6.2 Mixed-version / canary

| Test | Tiền điều kiện và hành động | PASS | FAIL/STOP | Finding |
| --- | --- | --- | --- | --- |
| T10 — MON transition | Canary follower, rồi leader transition có kiểm soát trong lab; quan sát quorum/election/Paxos | Quorum hội tụ, rank/age/session hợp lệ, no loop | Mất quorum, election loop, Paxos không catch-up | MON-003 |
| T10A — Release flag/rejoin | Hai state lab tách biệt: (a) giữ flag hiện tại và kiểm OSD/offline rejoin trước checkpoint; (b) trên fixture completion đặt flag Pacific, thử OSD v16.2.5 và pre-Pacific riêng | State (a) khớp As-Is không cần nâng sớm; state (b) vẫn cho v16.2.5 rejoin và gate pre-Pacific đúng expectation | OSD hợp lệ không rejoin, legacy được nhận sai, hoặc Production phải nâng flag sớm để clear warning | MON-002 |
| T10B — CIDR mixed negative gate | Disposable mixed lab có ít nhất một up base OSD; target CLI thử CIDR range-blocklist trước full-target rồi kiểm map/state và base-OSD rejoin | Request bị feature-gate (`ENOTSUP`/`EAGAIN` theo path) và không commit range state; base OSD vẫn rejoin. Chỉ test add/list/enforce/expire/remove sau full-target checkpoint | Range state xuất hiện trong mixed phase, base OSD decode/rejoin lỗi hoặc automation coi rejection là success | MON-001, MSG-007, VAL-004 |
| T10C — Old FSMap/failback | Disposable monstore có old FSMap epochs và CephFS topology đại diện; target MON flush/propose/decode; nếu MON rollback nằm trong plan, thử base-MON decode/failback trên clone | Target xử lý epoch cũ và topology hội tụ; base decode/failback PASS, hoặc MON được ghi rõ forward-only khi chưa có proof | FSMap decode/proposal lỗi, damaged topology, base failback không đọc state nhưng runbook vẫn gọi rollback | MON-005 |
| T10D — MON recovery tools | Chỉ khi `ceph-monstore-tool`/`osdmaptool` còn trong approved recovery runbook: dùng snapshot copy với target tool để rebuild/inspect rồi validate Paxos epochs, rotating keys và map có down OSD; nếu không dùng, đóng N/A có runbook evidence | Tool status rõ; epoch/key/map checksum và decode đúng; bản gốc không bị chạm | Tool mutation ngoài copy, epoch/key/map sai hoặc runbook Production dựa vào tool chưa rehearsal | MON-010 |
| T11 — CephX/MON↔MGR | Ép auth rotation quanh leader change; target MON nói chuyện base MGR | Chỉ key committed được publish; MGR không restart, metadata hội tụ | Auth loop, key divergence, unknown-message fatal/reset loop | MON-004, MSG-001/009 |
| T12 — MGR promote/failback | Target standby → active → base failback; test module/service-map/cache/event rebuild; trong staging làm chậm callback của một module và xác nhận module khác còn phản hồi | Không assert/deadlock; custom callbacks đến; service URI đúng; finisher/backlog của một module không chặn module khác | Module im lặng, restart loop, callback mất, cross-module stall hoặc state không hội tụ | MGR-001–003 |
| T13 — Metrics/LB | Direct active, direct standby và qua LB; diff schema/types/labels/version/cardinality | Scraper chọn active, parser pass, queries đúng | Chọn standby 200/body rỗng, parse fail hoặc schema consumer hỏng | MGR-005/006 |
| T14 — Dashboard | Direct/LB login, session, redirect, API Accept và TLS 1.3 | Tất cả client path/cert/SNI pass | Client/proxy/LB mất kết nối hoặc redirect/API sai | MGR-007 |
| T14A — Alert contract | Syntax/unit check rules target; simulate route/inhibition/silence rồi inject một alert có kiểm soát trước runtime reload | Map/deprecate đủ 18 tên cũ; checksum/runtime rules, pending/firing và notification destination đúng | Rule parse/eval lỗi, route/inhibition sai, ticket/notification mất hoặc file khác runtime | MGR-010 |
| T15 — Autoscaler | So recommendation quanh active flip; giữ PG changes không cần thiết ở trạng thái freeze theo runbook | Không có PG action bất ngờ; guards/min/max đúng | Tự thay PG ngoài expectation hoặc recommendation không giải thích được | MON-008, CFG-006, MGR-004 |
| T15A — Pool command contract | Trên pool disposable, chạy automation thật với valid/invalid `pg_num_min/max`, negative ratio, `bulk`/`noautoscale`, CephFS-pool snapshot rejection và lặp idempotency; kiểm exit code | Valid state đúng expectation; invalid input/rejection trả nonzero mà automation xử lý đúng; không PG mutation ngoài manifest | Automation bỏ qua nonzero, accept invalid state, snapshot/PG mutation ngoài kế hoạch hoặc retry không idempotent | MON-008, CFG-006, MGR-004 |
| T16 — EC/hinfo | EC pool lab, đổi primary base/target, async recovery; hinfo fixture có một nguồn authoritative tốt và case không đủ nguồn tốt | Acting không xuống dưới min_size; target không assert; nguồn tốt phục hồi sạch/checksum đúng; thiếu nguồn tạo `unfound`/`read_error` đúng thay vì đoán dữ liệu | Mất I/O ngoài policy, assert, nguồn tốt không được dùng, case thiếu nguồn trả data sai hoặc checksum mismatch | OSD-001/002 |
| T17 — Scrub/peering/backfill | Remap, delayed reservation, primary failover và interrupted backfill | Scrub FSM thoát, đúng acting, accounting đúng, không bypass full guard | Stuck/incomplete/stale PG hoặc vượt capacity guard | OSD-004/006/007 |
| T17A — Map/placement/store/progress | Pool lab có PG merge; quan sát `last_epoch_clean`, OSDMap trim, stale `pg_temp`/upmap cleanup; tạo/expire health mute; trong bounded recovery failover active MGR và so progress với PG/OSD counters | Trim/cleanup tiến, health mute hết hạn, recovery không spike; proposal/store và MGR readiness hội tụ; progress event cache rebuild, không là tín hiệu duy nhất | Map/store giữ tăng, stale placement state, proposal loop, progress stale/mất sau failover hoặc recovery vượt guardrail | MON-006/009, MGR-009 |
| T17B — OSDMap lower-bound rollback | Fixture cô lập OSDSuperblock/local-map lag và past intervals; target persist `cluster_osdmap_trim_lower_bound`, restart/failover; trên clone khác rehearsal target→base writer→target nếu downgrade nằm trong plan. Nếu BlueFS opcode BS-001 chặn base mount trước, ghi đó là dominant boundary và không quy lỗi cho OSD-007 | Lower bound đơn điệu qua restart; past-interval peering hoàn tất; isolated old-writer round-trip+re-upgrade decode PASS, hoặc OSD được ghi forward-only khi chưa chứng minh | Lower bound lùi, incomplete/stale PG, warning giả, generic base-mount failure bị gán sai nguyên nhân, hoặc runbook cho downgrade khi proof chưa PASS | OSD-007, BS-001 |
| T18 — Partial recovery/OMAP | Restart giữa large-object partial recovery; đo `clean_regions`/bytes và xác nhận chỉ missing ranges tiếp tục; range delete và missing EC copy trên fixture | Recovery bytes/regions tiếp tục đúng phần thiếu; checksum/key cardinality/errno đúng; scrub clean | Whole-object reread ngoài expectation, clean-region state mất, checksum mismatch, inconsistent hoặc boundary sai | OSD-005/008, KVBD-001/002 |
| T18A — Delete-range threshold | DB fixture có boundary keys qua nhiều shard; chạy default threshold và override `0`, kiểm `[start,end)` cùng key liền trước/sau, tombstone/compaction stats | Chỉ range mong đợi bị xóa; neighbor keys còn; threshold hiện thời/fast path không đổi correctness | Thiếu/thừa key, boundary lệch, iterator vượt tail hoặc compaction/resource ngoài guardrail | KVBD-001/002 |
| T19 — BlueStore mixed workload | Object/OMAP/snapshot workload qua từng target OSD canary | PG ổn định, mount/replay sạch, client checksum đúng | Replay/mount error, corruption, ENOSPC/assert hoặc recovery bất thường | BS-001/002/003/006–008 |
| T19A — BlueStore metadata/observability | Fixture clone/snapshot/shared-ref, small writes và onode/cache churn; so refcount/checksum và counter/alert base↔target theo version | Refcount/bookkeeping đúng, reopen/fsck sạch; counter/alert delta được giải thích, không dùng làm claim hiệu năng | Data/refcount mismatch, stale metadata, memory vượt budget hoặc alert/counter bị diễn giải sai | BS-008/010 |
| T20 — mClock/effective config | Một OSD mỗi media/host/class; so WPQ/mClock boot và location mask | Benchmark đúng policy, capacity/effective values đúng, latency trong guardrail | Unexpected benchmark, boot timeout, wrong config hoặc guardrail breach | OSD-011, CFG-002, MON-011 |
| T20A — Default activation | Canary representative client burst/RETURNVEC, shutdown notification, snap-trim và aggregated slow-op logging; so cap/reply limits, OSD memory, latency, PGLog, log rate và MON DB | Effective defaults đúng decision; no false timeout/backpressure; resource/log/store trong guardrail | Client stall, memory/log/DB spike, false shutdown/down signal hoặc snap-trim behavior ngoài expectation | CFG-001, MSG-003 |
| T21 — Messenger lifecycle | Trên từng path msgr1/msgr2 thực sự enabled, chạy representative traffic, peer restart/network flap/shutdown trong lab | Reconnect hội tụ, no coredump/stuck thread/reset storm | Hang, abort, reset storm hoặc false timeout không giải thích được | MSG-002/003 |
| T21A — Address/hook/MON-weight edge | Nếu áp dụng, test auto-address selection, crush_location_hook và MonClient với MON weight bằng 0 | Advertised address/location đúng; client hunt không abort và hội tụ | Bind/advertise sai, hook sai hoặc client abort/không kết nối | MSG-006 |
| T21B — OSD lifecycle/map delivery | OSD lab có inflight op và local map lag; restart, fast shutdown và peer map delivery qua base/target | Không coredump; down/dead notification đúng; map catch-up và timeout/heartbeat phản ánh state thật | Teardown crash, false timeout/down, map lag không hội tụ hoặc OSD process start nhưng không ready | OSD-012, MSG-003 |
| T22 — RBD caps/manifest | Primary base/target với rbd-read-only; manifest/snapshot fixture nếu dùng | Target chỉ cho metadata_list đúng scope; refcount/checksum đúng | Quyền ngoài scope, denial sai, crash hoặc data/refcount mismatch | OSD-013/014 |
| T23 — CephFS/MDS | Base client↔target MDS và ngược lại; oversized completed-request/session eviction, replay+blocklist race, retry/remount/caps; target IPv6 mount/perf v2; nếu dùng thì clone/cancel/purge dưới OSD-full, dynamic NFS RO/caps và mirror permission/restart | Session/cap/replay/failover hội tụ; eviction không đẩy MDS read-only; cap audit đúng; clone/NFS/mirror workflow và v2 consumer đúng/fresh | Client stuck, replay/decode fault, eviction/cap sai, clone/purge/NFS/mirror không hội tụ, mount IPv6 lỗi hoặc parser hỏng | MON-005, MSG-008, CFG-003, MGR-008, CEPHFS-001–008, VAL-003 |
| T23A — CephFS session/topology | Lab multi-rank/standby-replay với base/target clients; ép retry/forward qua biên 8-bit 255→256 và kiểm legacy byte/extended 32-bit theo negotiated feature; tạo completed-request metadata lớn, readdir/cap throttle/OFT warm-up; MON election/beacon grace, laggy eviction, fail/replay/blocklist | Legacy/extended field decode đúng theo capability; eviction counter/target session đúng; MDS không read-only; damaged/failed/laggy/replay hội tụ; retry/caps không mất hoặc nhân đôi | Decode/counter sai qua biên, eviction storm, rank damaged/read-only, replay đứng, session/cap leak, warm-up/grace sai hoặc request treo | MSG-008, CFG-003, CEPHFS-001–004 |
| T23B — CephFS security/volumes/NFS/mirror | Với legacy Manila applicability, chạy subvolume discovery/cap issuance + negative path dưới target-active MGR, base-active failback nếu còn được phép, rồi full-target; trên fixture chạy clone/cancel/purge+OSD-full, RW→RO export và mirror restart | Mọi active-MGR phase có outcome đã duyệt hoặc base failback bị chặn; không key/cap vượt subvolume; clone cancel/purge hội tụ; RO chặn write; đúng một replayer và data/mode/last-synced parity đúng | Base MGR tái tạo vulnerable discovery, key cũ không truy vết/cap quá rộng, clone chạy sau cancel, NFS bypass, duplicate/stuck mirror hoặc parity mismatch | CEPHFS-005–008, SEC-003 |
| T24 — RGW | Pin request vào từng base/target daemon: Browser POST negative, PUT/POST/multipart timeout + checksum/read-back, IAM/STS allow/deny, TLS 1.2/1.3, secure MON reconnect; nếu dùng thì disposable reshard/delete-list race, multisite version/checksum convergence, LC/GC/FIFO/notification delivery. Bucket check chỉ read-only; repair là change riêng | Policy không bypass; body/ETag/version đúng; auth nhất quán per daemon; supported TLS/MON PASS; index/zones/workers hội tụ; diagnostics không mutate | Policy bypass, mất/corrupt object, auth nondeterministic, TLS/MON failure, worker delivery sai, sync/index divergence hoặc repair bị cần để đạt PASS | CFG-004, RGW-001–008, SEC-005 |
| T24A — RGW reshard/multisite/workers | Disposable bucket với concurrent write/delete/list trong reshard; record old/new shard IDs/stats; multisite markers/logs/checksum/version; LC/GC/FIFO/notification có delivery oracle và expiry expectation | Không write vào stale shard; listing/stats đúng; mdlog/datalog/bilog markers và backlog hội tụ; event không mất/nhân đôi ngoài contract, expiry đúng | Stale index/stat mismatch, unbounded lag, missing policy forwarding, lost/duplicate event hoặc worker backlog không giảm | RGW-003–005 |
| T24B — RGW auth/frontend/diagnostic | Pin Browser POST, IAM/STS/CORS/cross-tenant allow/deny từng daemon; slow upload/header/graceful drain; `bucket check` read-only. `--fix` chỉ trên clone trong change repair riêng | Quyết định auth nhất quán và deny đúng; body/headers/checksum đúng; drain không cắt request; diagnostic không mutate | Bypass/nondeterministic auth, tail data sai, header/body mismatch, drain violation hoặc cần `--fix` để pass rollout | RGW-001/002/006–008, SEC-005 |
| T24C — RGW/RBD config conditionals | Với RGW Vault, dùng CA/cert và encrypt/decrypt thật; inject cache-notify failure trong lab, kiểm quota/pool-create/multi-delete. Với RBD mirror, theo dõi snapshot count/backlog qua failover | TLS policy đúng, data giải mã/đọc lại đúng; retry/quota/pool/multi-delete đúng; mirror telemetry hội tụ | Vault verify/decrypt fail, cache/quota/delete sai, automation còn phụ thuộc removed key hoặc mirror backlog tăng vô hạn | CFG-004 |
| T25 — Stretch conditional | Site degrade/recover và tiebreaker/rule validation trong lab | Quorum/placement/failback đúng | Topology/weight/rule sai hoặc recovery không hội tụ | MON-007 |
| T26 — Cephadm state machine | Clone state ở migration 2; với topology áp dụng test MGR 3+, staggered manifest/limit và active handoff; rehearsal MDS pause/stop/restore, offline NFS/HAProxy host, failed redeploy/action, registry pull từng host, old-name exec/restart và specialized-service config diff | Migration/action đạt terminal; NFS export/grace, `_admin` và credential location khớp; image+`deployed_by`, selected/remaining count và service config hội tụ; MDS flags/ranks restore và `mon_mds_skip_sanity` được gỡ/khôi phục; offline reschedule không duplicate; pull đúng digest; không orphan container | Base failback sau state 5, migration side effect lệch, active loop, daemon ngoài manifest đổi trái dự kiến, action treo/giả success, MDS state/sanity option bỏ lại, duplicate serving, old-name/unit lỗi hoặc host pull sai | ADM-001–009 |
| T26A — MGR ≥3/staggered | Controlled promotions; so digest+`deployed_by`; thử rejection out-of-order và `limit` nhỏ; diff exact selected/remaining set sau handoff | Active hội tụ, manifest/count/order giữ nguyên, daemon ngoài manifest không đổi ngoài monitoring contract | Failover loop, metadata không hội tụ, order được bypass hoặc daemon ngoài manifest đổi | ADM-002/003 |
| T26B — Offline/lifecycle/render | Mất management connectivity NFS/HAProxy trong staging; inject redeploy failure; test old-name read-only exec/stop/restart; diff gateway/monitoring render | Replacement/VIP liên tục và không duplicate; action fail terminal rõ; đúng container/unit; endpoint/session/scrape còn hoạt động | Action trên offline host, duplicate serving, non-terminal progress, wrong container/orphan hoặc config/endpoint mất | ADM-005/006/008/009 |
| T27 — Ceph-volume activation | So inventory host/container và stable serial/WWN allowlist/candidate diff; restart một LVM, raw và dm-crypt OSD đại diện; kiểm DB/WAL/mapper UUID/key-size/config-key access/unit và log secret scan | Cùng identity/device mapping; không false-positive candidate; activation idempotent; OSD mount đúng DB/WAL; log không lộ key | Device biến mất/đổi identity, false candidate, mapper/key lỗi, secret lộ, activation treo/sai path | CVOL-001–003/006 |
| T28 — RBD clients/PWL | Matrix client base/target; fast-diff so full-diff reference; journaled discard multi-object; mirror demote/promote failover+failback; lock/watch/blocklist fault injection trên client thật; trên recovery copy thử procedure target-compatible cho cache layout 0 đã clean/empty. Nếu automation dùng `rados cppool`, chỉ test trên pool disposable | Checksum/diff/journal/mirror đúng; không hang/assert; lock recovery hội tụ; cache xử lý theo procedure được duyệt và target mở được; cppool trả đúng semantics | Dirty cache, procedure dựa vào in-place migration chưa chứng minh, `-EINVAL`, mismatch/hang/assert, stale lock/blocklist hoặc mirror/cppool outcome không hội tụ | RBD-001–007 |
| T28A — PWL crash/recovery | Recovery copy; overlapping write/flush/discard, abrupt client stop/restart và lock handover; đo dirty entry/count | Checksum, ordering, replay và dirty-count hội tụ; không mất acknowledged write | Init/recovery lỗi, dirty count không drain, stale data/order hoặc cache file bị xử lý khi chưa clean | RBD-002–004 |
| T28B — Mirror/lock/watch | Controlled mirror demote/promote/failback, contention, disconnect, blocklist và rewatch trên client thật | Một primary hợp lệ, queue hội tụ; lock owner đúng, rewatch và I/O hoàn tất; không unexpected trash | Split-brain/livelock, stale/invalid lock owner, blocklist loop, I/O treo hoặc unexpected trash | RBD-006/007 |
| T29 — Package-common/service/ceph-crash | Sau direct base→target package transaction áp dụng (RPM hoặc DEB) trên VM từng distro/cohort, so old/new sudoers package ownership, mode/syntax và local drop-in; kiểm weak-dep policy cùng `smartctl`/`nvme`, effective MON `PrivateDevices`, quorum+device-health scrape; nếu ceph-crash áp dụng, ghi UID/GID/groups, synthetic archive/upload và unreadable-entry loop | Package owner/mode/tools/unit/device-health đúng; ceph-crash có UID/GID `ceph`; root-start thì groups rỗng sau drop, direct-ceph start thì groups khớp policy; archive/upload và loop PASS | Sudoers owner/mode/dependency sai, MON/quorum/device-health lỗi, ceph-crash quyền/groups ngoài policy, thoát hoặc mất archive/upload | BLD-001–003, VAL-001, SEC-004 |
| T29A — RPM lifecycle | Chỉ RPM: direct base→target với scriptlet expansion/order; tách target→target và uninstall; kiểm cephadm key/user/home/UID, immutable-cache state, `CEPH_AUTO_RESTART_ON_UPGRADE`, SELinux label/context và restart events | Key/user/cache/labels sống đúng hoặc mitigation do RPM owner duyệt; restart/uninstall/second hop khớp policy | Old `%postun` xóa state, label/context lỗi, restart trái policy, cache state sai hoặc mitigation chưa chứng minh | BLD-009 |
| T29B — AArch64 ISA-L | Chỉ AArch64 artifact có ISA-L EC: kiểm text relocation/loader và EC read/write/scrub trên build target thật | Không text relocation/loader error; checksum/scrub sạch | Relocation còn tồn tại, loader fail hoặc EC data mismatch | BLD-008 |

### 6.3 Full target / stabilization

- [ ] Mọi daemon trong scope đã ở target và service-map/quorum ổn định.
- [ ] Đối chiếu OSD offline trước khi xử lý OSD_UPGRADE_FINISHED; không tự nâng release flag để clear WARN. [MON-002]
- [ ] Xác minh OSDMap trim tiến, pg_temp/upmap cleanup không tạo recovery spike và MON store/free space ổn định. [MON-006/009]
- [ ] Chạy correctness test OMAP iterator/range-delete trên fixture đại diện; tập key/header phải giống và range phải đúng [start,end). [KVBD-001/002]
- [ ] Trong lab tương đồng Production, test BlueFS crash durability, deferred replay và DB/WAL topology; replay, fsck, checksum và DB reopen phải sạch. [BS-002/003/006]
- [ ] So effective config theo role/location, xử lý stale key chỉ sau khi rollback mapping đã PASS. [MON-011, CFG-007]
- [ ] Đối chiếu autoscaler recommendation/action, progress output và PG/OSD recovery counters; không dùng ceph progress làm tín hiệu duy nhất. [MGR-004/009]
- [ ] Chỉ sau Prometheus gate mới reload bộ rules target; xác nhận runtime checksum, reload success, pending/firing và notification destination. [MGR-005/006/010]
- [ ] Nếu dự định dùng CIDR range blocklist, test add/list/enforce/expire/remove, offline-OSD rejoin và rollback trên disposable lab; nếu thiếu bằng chứng, tiếp tục để feature unused. [MON-001, MSG-007]
- [ ] Xác nhận cephadm migration/action queue đạt terminal, không còn preparation state MDS, host/action không bị suppress ngoài ý muốn, mọi daemon có đúng target digest/`deployed_by`, không orphan old-name container và registry credentials không persist sai. [ADM-001–008]
- [ ] Diff lại rendered ingress/iSCSI/NFS/monitoring config và xác nhận VIP/session/export/scrape/retention/TLS vẫn đúng sau post-actions. [ADM-009]
- [ ] Re-run inventory/activation diff và kiểm encrypted mapper/DB/WAL sau toàn bộ restart; không chạy migrate/zap/provision để “dọn” sai lệch trong stabilization. [CVOL-001–006]
- [ ] Với RBD/CephFS/RGW đang dùng, chạy lại checksum/convergence/auth/worker matrix sau khi không còn base process/client trong phạm vi change; xác nhận không cần mutation/repair để đạt PASS. [RBD-001–007, CEPHFS-001–008, RGW-001–008]
- [ ] Nếu có `cmpomap` consumer, chạy lại empty-U64 case khi full-target và ghi rõ thời điểm semantics không còn phụ thuộc primary version. [VAL-002]
- [ ] Xác nhận `ceph-crash` target chạy user `ceph`, crash directory đọc được, và package/service files trên mọi distro cohort đúng owner/mode/effective unit. [BLD-001–003/009, VAL-001]
- [ ] Nếu `ceph-dencoder`/custom build/DEB/mirror được dùng, lưu package-content smoke, `list_types` và representative encode/decode round-trip từ chính artifact deployed. [BLD-004–008/010, VAL-005]
- [ ] Reconcile với baseline mọi cờ `no*`, maintenance mode, paused upgrade/action, temporary config, autoscaler freeze, alert silence và traffic drain; chỉ hoàn tác state được tạo bởi change, không xóa state có trước.
- [ ] So baseline trước/sau cho latency, error, recovery, CPU/RSS, disk, network, MON DB, MGR và monitoring theo guardrail đã định.
- [ ] Hoàn thành soak time, không có sự cố mới hoặc trend xấu chưa giải thích.
- [ ] Bàn giao aftercare: owner/on-call, thời gian theo dõi tiếp, evidence retention, exception expiry và tiêu chí reopen incident đã được ghi vào change record.

### 6.4 PA1/PA2 và H0 — ma trận bổ sung

T30–T38 là test thiết kế mới, không phải finding được phát hiện sẵn trong source diff. Chạy trên fixture disposable trước; **không inject lỗi vào production**. Mỗi bài cần artifact SHA/digest, H0/version, tập PG, timestamp, nguồn/đích thực, kết quả payload/metadata và số đo QoS. Trong lab phát triển được phép có test đang FAIL để tìm lỗi; chưa dùng nó làm GO CANARY production.

| Test | Kịch bản | PASS | FAIL / giới hạn |
| --- | --- | --- | --- |
| **T30 — PA1-H** | Chuyển primary, dừng X giữ store, upmap tới S, nâng X, trả C rồi batch; thử norebalance và cleanup | U0–U5 đúng; degraded time/byte ra-về đo đủ; HG1 trước rejoin và HG2–HG5 trước mở quyền | Copy kẹt, cleanup khác giả định chưa xử lý, thiếu replica quá budget, PG ngoài phạm vi hoặc H0 chỉ quan sát nhưng gọi enforce |
| **T31 — PA2-H** | Drain CRUSH weight=0 khi X chạy; nâng; Wε/upmap C; tăng weight theo budget | X drain đầy đủ trước dừng; đúng C; mọi PG mới có HG; phục hồi W0/R0/A0 theo journal | Nhầm override/CRUSH weight, PG ngoài C, auto-primary khi hoàn nguyên affinity, bước tăng chỉ theo thời gian |
| **T32 — Tham chiếu và bản X** | X sai, Y/Z đúng; GET qua Y vẫn đúng; thêm sai metadata/missing object và version mapping | Đọc đúng X và phát hiện sai theo H0; coverage app/RADOS/metadata rõ; H0 không bị ghi đè | Hash tự khai hoặc GET qua peer/cache tạo false PASS; payload đúng nhưng metadata chưa phủ lại ghi toàn PG PASS |
| **T33 — Chặn trước sử dụng** | Y primary chết khi X chưa đạt; X được chọn làm source recovery hoặc replica-read; thử khôi phục affinity toàn X | Các quyền chưa đạt HG bị chặn trước sử dụng, đúng từng PG/version; đo availability khi không còn peer hợp lệ | Chỉ cảnh báo sau truyền dữ liệu, X tự primary/source/read, hoặc hạ min_size/bỏ gate để giữ IOPS |
| **T34 — H0 chọn đúng nguồn** | Cùng version: X/Z sai, chỉ Y khớp; lặp case nhiều nguồn khớp và hash local hợp lệ nhưng payload sai | Chọn Y dù thiểu số; recovery dùng đúng source, cập nhật payload X và metadata, read-back khớp H0; có bằng chứng durability | Lấy đa số, cập nhật checksum thay payload, actual source khác source đã verify, repair success nhưng đọc lại sai |
| **T35 — Ghi mới/TOCTOU** | Overwrite, delete/recreate, remap, snapshot head đổi sau verify/trước sửa hoặc promote; source chết giữa copy | Stale token bị loại, không đè version mới, partial repair chưa được publish như verified; retry với nguồn/version hợp lệ | So H0 cũ với head mới, bỏ mất ghi đã ACK, publish nửa bản hoặc cấp quyền bằng kết quả stale |
| **T36 — Không còn nguồn tốt** | Tất cả bản sai cùng nội dung; mọi bản thiếu/không đọc được; chỉ còn hash đúng | NO_VALID_SOURCE/UNKNOWN; không tự ghi sửa hay chọn đa số; B100 nếu có thì restore nguồn tốt và đo RPO/RTO | Báo “đã phục hồi” dù không payload đúng, tạo lại H0 từ bản sai; case H chỉ chứng minh dừng đúng, không chứng minh phục hồi |
| **T37 — Sau promote và lỗi bộ kiểm** | Ghi mới sai khi X primary; verifier crash, manifest rollback, partition; controller/OSD restart; nâng peer tiếp theo | Theo dõi expected version mới; phát hiện/thu hồi đúng contract; không dùng token cũ sau restart; nguồn tốt/aftercare rõ | Một lần HG3 PASS bị dùng cho mọi ghi sau này; fail-open; nguồn tốt biến mất; hậu kiểm bị ghi thành chặn trước ACK |
| **T38 — So sánh H/B100 và quyết định phục hồi** | PA1-H/PA2-H cùng tải/coverage; nếu có lab thứ hai thử sync, retention, write/delete sai, failover/restore | Bảng chi phí, coverage, recovery cases, detection/fence lag và RPO/RTO thực đo; quyết định requirement 100 TB có owner | Không có B100 thì NOT_RUN cho bài đó; chưa được kết luận H tương đương backup độc lập hoặc performance 100 TB từ lab nhỏ |

**Ánh xạ ma trận plan:** T30/T31 bao phủ các run PA1-H/PA2-H; T32–T37 mở rộng F9–F20 của plan. PA1/PA2 vẫn phải chạy các test native T00–T29 áp dụng, gồm store history, peering, BlueStore, RBD/RGW. Không dùng gate H0 để bỏ gate version/durability hiện có.

## 7. Gate rollout theo deployment path

Các mục này là gate logic, không phải lệnh nâng cấp. Runbook chỉ được chọn **một** nhánh dưới đây; thứ tự của nhánh này không được áp sang nhánh khác nếu chưa có bằng chứng của orchestrator/package thực tế.

### 7.1 Chọn và khóa nhánh thực thi

| Nhánh | Thứ tự/contract phải dùng | Điều kiện đóng nhánh khác |
| --- | --- | --- |
| Cephadm target | Source target cưỡng chế `mgr → mon → crash → osd → mds → rgw → rbd-mirror → cephfs-mirror → iscsi → nfs → node-exporter → prometheus → alertmanager → grafana`; staggered filter không cho phép bỏ qua order | Không được dùng MON-first của manual runbook; G08/T26 bắt buộc |
| Package/manual | Dùng thứ tự role trong runbook đã peer-review và rehearsal; vẫn áp dụng mọi gate data/control-plane tương ứng | ADM-001–009 chỉ N/A khi chứng minh không có cephadm control state/service |
| Orchestrator khác | Ghi sản phẩm/version, order, state migration và rollback contract từ artifact/vendor evidence, rồi map sang các gate bên dưới | Không mặc định semantics cephadm hay package/manual |

- [ ] Deployment path, exact order, canary unit, failure domain và batch size đã được change owner ký trước first target process.
- [ ] Với cephadm, base 16.2.5 không nhận staggered filters/limit của target: ghi riêng bước bootstrap target MGR và chỉ gửi filtered phase sau khi target MGR active, checkpoint migration/rollback đã chốt. [ADM-003/004]
- [ ] Nếu client binary nằm trong scope, sequencing client/MDS/RGW/RBD được ghi riêng; full-target daemon không tự có nghĩa client đã target.

### 7.2 R0 — Trước first target process

- [ ] G00–G16 áp dụng đã PASS theo phase; G14–G16 có evidence lab trước production canary. Exception/waiver phải có owner, phạm vi, expiry và compensating control, không thay correctness evidence.
- [ ] T02 device alias đã PASS. Với rollback OSD, T01 đã PASS **hoặc** forward-only/rebuild strategy đã được phê duyệt và rehearsal; với monitoring, T04 đã PASS **hoặc** Prometheus không phải stop/go và telemetry độc lập đã verify.
- [ ] Migration/upgrade/action/host state, package/service state, registry pull từng host, ceph-volume device mapping và client/service applicability đã được chụp. [ADM-003–009, CVOL-001–003, BLD-009, RBD-001–007, CEPHFS-001–008, RGW-001–008]
- [ ] Config/map/control-state artifacts và nguồn phục hồi theo H hoặc B100 có checksum/retention và test phù hợp; H có manifest cùng payload source đúng, B100 có điểm restore độc lập. Artifact base/target vẫn truy xuất được; không tự suy phải dựng thêm cụm 100 TB để chạy lab.
- [ ] Mọi cờ `no*`, maintenance mode, traffic drain, autoscaler freeze và alert silence dự kiến có owner, reason, TTL/restore point; state có trước change được đánh dấu riêng.
- [ ] Change freeze, time budget, communication path, STOP/resume conditions và người quyết định đã được truyền đạt.

### 7.3 R1 — MGR/control-state canary của nhánh cephadm

- [ ] Target MGR standby load/can-run, service URI, target digest và `deployed_by` đúng; topology 3+ không quay vòng active. [ADM-002]
- [ ] Trước target promotion, xác nhận checkpoint migration và rollback decision; sau state 5, không dùng base MGR reconciliation như failback mặc định. Đối chiếu NFS export/grace/spec, `_admin` và registry side effects nếu áp dụng. [ADM-004]
- [ ] Staggered manifest/limit/expected count còn đúng sau active handoff; daemon ngoài manifest chỉ được đổi khi contract monitoring redeploy đã ghi nhận. [ADM-003]
- [ ] Prometheus parser được kiểm **đầu tiên** sau target promotion; custom notify, Dashboard TLS/API, metric schema/LB và autoscaler diff đều PASS.
- [ ] Với package/manual có order khác, mục này được chạy đúng checkpoint của runbook; không đánh dấu N/A các test MGR chỉ vì không dùng cephadm.

### 7.4 R2 — MON transition

- [ ] Quorum, rank, leader, MON store và network/clock ổn định; target follower ổn định trước leader transition trong rehearsal.
- [ ] CephX rotation, MonClient reconnect và MON↔MGR edge đã PASS.
- [ ] Nếu còn base MGR, `ms_die_on_bad_msg` là false/default và không có abort/reset loop hoặc metadata stale không hội tụ.
- [ ] Không bật CIDR range state, không thay MonMap topology và không nâng release flag trong canary.

### 7.5 R3 — Crash/OSD canary

- [ ] Với cephadm, `crash` cohort đã qua trước OSD theo engine order; `ceph-crash` chạy user `ceph` và backlog không tăng. [VAL-001]
- [ ] Chọn một OSD đại diện mỗi media/layout/host/class mà không phá failure-domain safety.
- [ ] Device ownership, allocator config, mClock policy và effective location mask đã PASS.
- [ ] Host/container inventory khớp; raw/LVM/dm-crypt activation canary tìm đúng identity, block/DB/WAL, mapper và unit. [CVOL-001–003/006]
- [ ] Mount/replay sạch; PG peering/recovery/scrub và client workload trong guardrail; với nhánh H chỉ mở primary target sau HG2/HG3, sau đó chạy HG4. Không promote trước để “thử xem H0 có bắt lỗi không” trên production.
- [ ] Không dùng package-only downgrade nếu OSD đã ghi BlueFS target; batch record phải đánh dấu OSD nào đã vượt boundary.

### 7.5.1 R3A — PA1: spare/upmap và giữ store

- [ ] U0/U1: X/S/C, W0/R0/A0, upmap trước phiên, headroom và nguồn H0 đã ghi; spare hợp lệ từng PG.
- [ ] Chuyển primary khỏi X và kiểm primary thực tế; affinity không thay HG1.
- [ ] Đánh giá cửa sổ thiếu replica của **toàn bộ P_X** trước khi dừng X; ok-to-stop tại thời điểm dừng, norebalance/noout đúng ownership.
- [ ] Áp mapping X→S đã kiểm; không chặn recovery cần thiết bằng nobackfill/norecover; đợi U2 đủ replica và không phụ thuộc X trước mở store bằng B.
- [ ] Store block/DB/WAL có lịch sử được giữ tại lúc dừng; ghi cleanup/reuse thực tế sau start, không coi store cũ là backup current version.
- [ ] HG1 có hiệu lực trước X nhận lại C; mở backfill cân bằng theo journal; chưa cho PG ngoài C vào X.
- [ ] Chạy R3H cho C; mỗi batch PG mới lặp HG2–HG5; chưa khôi phục affinity rộng khi còn PG chưa đủ điều kiện.
- [ ] U5: phục hồi cấu hình sở hữu, giám sát remap/balancer và giữ nguồn phục hồi theo retention; mới xét OSD tiếp theo.

### 7.5.2 R3B — PA2: drain weight và tăng từng nấc

- [ ] U0/U1: chốt **CRUSH weight** là biến điều khiển, lưu W0/R0/A0; không nhầm CRUSH weight với override reweight.
- [ ] Giữ X chạy khi weight về 0; mọi PG đã rời X đủ replica/up-acting hội tụ và ok-to-stop đạt trước dừng.
- [ ] Start B tại weight=0; HG1 chặn quyền chưa cấp, không PG vào ngoài kế hoạch.
- [ ] Dự đoán Wε dương hợp lệ, áp weight/upmap không nguyên tử; kiểm toàn bộ map qua epoch, chỉ C được vào X.
- [ ] Không coi norebalance hoặc weight nhỏ là allowlist; PG ngoài C hoặc remap drift thì dừng mở rộng.
- [ ] Chạy R3H cho C trước tăng weight; mỗi nấc dựa vào PG/byte/QoS và coverage HG mới.
- [ ] Trả W0/R0/A0 và xử lý upmap theo ownership khi HG5/U5 đạt; theo dõi sau bật balancer.

### 7.5.3 R3H — H0 chọn nguồn và sửa trước khi cấp quyền

Checklist này chạy **trong cả PA1 và PA2**. Từng ô cần timestamp, binding, actual source/target và evidence; không chỉ một cột “checksum OK”.

- [ ] **HG0:** H0 tin cậy, đúng identity/version/range và coverage metadata; manifest độc lập, nguồn payload tốt còn sẵn.
- [ ] **HG1:** X chưa được primary/source/replica-read ở phạm vi chưa verify; thực thi cả khi failover/restart, không chỉ giá trị affinity.
- [ ] **HG2:** đọc lại đúng bản X. MATCH còn hiệu lực mới qua bước; STALE/UNKNOWN retry/hold; MISMATCH đi luồng sửa dưới đây.
- [ ] Khi MISMATCH: giữ evidence, chặn quyền X liên quan; liệt kê các replica còn có payload theo PG history hiện tại.
- [ ] Đọc/hash từng nguồn ứng viên, so với H0 **cùng version**; chọn nguồn khớp. Nếu chỉ một nguồn khớp vẫn chọn theo bằng chứng, không theo đa số.
- [ ] **Không có nguồn khớp:** NO_VALID_SOURCE; không auto-repair/ghi đè, không tạo lại H0. Escalate hoặc restore payload độc lập nếu thực sự có.
- [ ] Trước sửa kiểm lại version/PG interval, ghim version nguồn hoặc staging đã verify, ràng buộc dirty writes/ordering theo barrier đã test; có ghi mới thì hủy/retry với reference mới. Bản copy một phần chưa được publish thành verified.
- [ ] Recovery/rebuild **truyền payload đúng** từ nguồn đã xác minh vào X qua procedure/API đã test; giữ metadata/PG history và retry budget. Lưu actual source để chứng minh không bị Ceph chọn lại nguồn khác chưa kiểm.
- [ ] X hoàn tất ghi theo durability contract; đọc lại/hash khớp H0 và kiểm metadata. Reopen/restart durability test có evidence lab; không chỉ đọc lại checksum metadata hoặc cache.
- [ ] **HG3:** version/token/coverage còn hợp lệ tại điểm cấp quyền; không dùng result của snapshot cũ cho head mới hoặc một PG cho cả OSD.
- [ ] **HG4:** primary canary có read/write/overwrite/delete và kiểm expected version mới; báo detection/fence lag của hậu kiểm sau ACK.
- [ ] **HG5:** mọi PG mới hoặc batch mới đạt gate tương ứng, không pending/stale bị bỏ qua; giữ nguồn tốt và aftercare tới mốc đã chốt.

Trạng thái bắt buộc phân biệt: `MATCH`, `MISMATCH`, `STALE`, `UNKNOWN`, `NO_VALID_SOURCE`, `REPAIRING`, `REVERIFY`, `VERIFIED`. Lệnh sửa trả success chưa đủ thành VERIFIED. Nếu H-LAB chưa có enforcement/source binding thì ghi trạng thái chức năng chưa đạt; không dùng để thay requirement backup production.

### 7.6 R4 — Mở rộng mixed fleet và service cohort

- [ ] Mỗi batch chỉ mở sau soak, guardrail và review evidence của batch trước; không có unexplained PG state, checksum mismatch, daemon loop, reset storm hoặc recovery spike. Nhánh H phải đạt HG5 và lặp HG cho PG/version mới; không kế thừa PASS của C cho toàn bộ X.
- [ ] Nhánh cephadm tiếp tục đúng order còn lại: MDS safety sequence; RGW; RBD/CephFS mirror; iSCSI/NFS; cuối cùng monitoring stack. Không dùng filter để nhảy qua type trước đó. [ADM-001/003]
- [ ] Host unreachable/maintenance và action queue có disposition; `scheduled`/`starting` không được coi là complete; NFS/HAProxy reschedule không tạo duplicate serving. [ADM-005/006]
- [ ] Trước mỗi specialized-service redeploy, diff rendered config; sau đó kiểm VIP/port/TLS/session/export/scrape/rules. [ADM-009]
- [ ] Canary traffic thực gồm RBD cache/journal/mirror/lock, CephFS session/replay/caps/volumes/NFS/mirror và RGW Browser POST/write/auth/TLS/multisite/workers; drain endpoint base theo security gate. [RBD-001–007, CEPHFS-001–008, RGW-001–008]
- [ ] Monitoring stop/go vẫn độc lập, parse được và đáng tin cậy trong suốt các service cohort.

### 7.7 R5 — Full target và stabilization

- [ ] Hoàn thành mục 6.3 và không còn daemon/client base ngoài phạm vi đã được exception rõ ràng.
- [ ] Mọi external consumer/rule/runbook đã chuyển đổi hoặc được giữ ở phiên bản tương thích có chủ đích.
- [ ] Chỉ kích hoạt capability mới sau checkpoint rollback/change riêng.
- [ ] Chỉ tuyên bố GO Production khi evidence package, test matrix, soak, rollback strategy, exception register và sign-off áp dụng đều hoàn tất; acceptance tài liệu `00`–`15` một mình không đủ.

### 7.8 Nhật ký bắt buộc cho từng batch

| Batch ID | Path/role/type | Host/daemon/failure domain | Version/digest trước → sau | Bắt đầu/kết thúc | Health + guardrail trước/sau | Evidence | Boundary đã vượt | Quyết định/approver |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

- [ ] Ghi expected và actual daemon count, action terminal state, primary/active transitions, time budget, soak và mọi deviation. Nhánh H ghi PA/H-mode, H0 manifest/version, HG, source–target sửa, hash trước/sau, dirty token, byte/metadata coverage, detection/fence lag và nguồn tốt còn lại.
- [ ] Nếu STOP, giữ nguyên record, gắn incident/evidence và mở một quyết định resume/forward-fix/rollback mới; không sửa đè kết quả cũ.

## 8. STOP conditions và phạm vi bị chặn

Dừng batch hiện tại ngay khi có một trong các dấu hiệu sau:

- Mất quorum, election loop, Paxos không catch-up hoặc MON store chạm guardrail.
- OSD mount/replay fail, unrecognized BlueFS op ở đường rollback, assert/coredump hoặc restart loop.
- Checksum/data/refcount/key-cardinality mismatch.
- PG mới chuyển incomplete/inconsistent/unfound, peering/scrub stuck hoặc recovery vượt guardrail mà chưa giải thích.
- Hai writer có thể mở cùng block device, hoặc ownership device không còn chắc chắn.
- mClock benchmark ngoài kế hoạch, boot time/I/O vượt guardrail hoặc capacity bị persist sai.
- Messenger hang, stuck thread, reset storm, auth loop hoặc MGR unknown-message fatal.
- MGR/module callback im lặng, service-map không hội tụ hoặc autoscaler tạo PG action bất ngờ.
- Prometheus parse/scrape fail mà không còn nguồn telemetry độc lập đã duyệt.
- Dashboard/API, CephFS, RGW Vault hoặc business-critical consumer fail ở path đang được nâng.
- Alert route/silence/notification sai sau reload.
- MGR active quay vòng, image/`deployed_by` không hội tụ, staggered daemon ngoài manifest đổi hoặc selected/remaining count sai.
- Cephadm migration/action loop, action không terminal, MDS rank/standby state bị bỏ lại, unexpected NFS/HAProxy replacement/duplicate serving, old-name container/unit sai, rendered config chưa review, registry sai digest hoặc host không pull được target.
- Ceph-volume inventory/activation đổi identity, false-positive candidate, mất DB/WAL, dm-crypt key/mapper lỗi, log lộ secret hoặc OSD unit trỏ sai device.
- RBD target từ chối cache layout 0 khi chưa clean/empty, PWL init/recovery/dirty-count không hội tụ, diff/journal checksum sai, invalid lock owner, mirror split-brain/livelock hoặc unexpected trash.
- CephFS rank damaged/read-only, replay không tiến, eviction storm, cap/session sai, clone tiếp tục sau cancel, NFS path/RO bypass, duplicate/stuck mirror hoặc data/mode parity sai.
- RGW Browser POST bypass, write checksum/tail mismatch, auth decision khác nhau, stale shard/index/stat, multisite lag không hội tụ, worker backlog/event/expiry sai, graceful drain vi phạm, target mất MON connection hoặc supported TLS client fail.
- Package upgrade mất cephadm user/key, dependency/plugin/service asset thiếu, chạy restart trái policy, MON mất device visibility hoặc `ceph-crash` không thể hạ quyền/đọc crash directory.
- Artifact/version/digest thực tế khác manifest đã duyệt, hoặc mất nguồn telemetry bắt buộc quá thời gian budget.

Với PA1/PA2 + H0, STOP còn gồm:

- X có PG/quyền primary/source/read ngoài phạm vi HG, kể cả do failover hoặc khôi phục affinity cả OSD.
- H0 mismatch, metadata mismatch, nguồn duy nhất chưa verify hoặc actual recovery source khác nguồn đã chốt.
- Manifest mất/sai/rollback, token stale, version đổi khi apply, ghi mới bị đè hoặc job sửa vượt retry budget.
- Không còn payload khớp, hoặc mất nguồn phục hồi bắt buộc khi nâng peer tiếp theo.
- Coverage chỉ lấy mẫu nhưng báo đủ; H0 hết ngân sách/telemetry mà vẫn cấp quyền mới.
- Requirement phục hồi độc lập chưa đáp ứng nhưng production vẫn dự định mở rộng không có quyết định thay thế.

STOP nghĩa dừng mở rộng và chặn quyền nguy hiểm theo MOP; không mặc định tắt cả cụm. Nếu không còn peer đủ điều kiện thì phải báo khả năng mất I/O, không bypass HG/min_size.

Khi STOP:

1. Không mở rộng sang batch/role tiếp theo.
2. Giữ log, map/config dump, metrics và image/clone liên quan; không repair để “thử”.
3. So với baseline và xác định lỗi đã có trước hay do phase vừa thực hiện.
4. Chọn forward-fix, failback role hoặc restore state theo ma trận rollback; không mặc định hạ package OSD. Với dữ liệu sai, chỉ sửa từ nguồn khớp H0 cùng version theo R3H; thiếu nguồn thì NO_VALID_SOURCE, không dùng hash làm payload.
5. Chỉ resume sau khi owner tương ứng ký PASS mới.

## 9. Rollback: có thể hay không?

**Trả lời ngắn:** có thể rollback một số role/config, nhưng **không có một rollback package-only chung cho toàn cluster**. BlueFS tạo ranh giới theo từng OSD; state mới, config ngoài Ceph và external monitoring cần rollback riêng.

| Đối tượng | Mức | Điều kiện và giới hạn |
| --- | --- | --- |
| Messenger/local runtime fixes | Có điều kiện | Không có migration bền vững được chứng minh; failback trả lại race/default cũ |
| MGR binary active ↔ standby | Có điều kiện | Phải rehearsal service-map, module events, metrics/schema, Dashboard và consumer behavior |
| MON 16.2.15 → 16.2.5 | Có điều kiện | Quorum-safe failback và state decode phải test; FSMap/state mới cần kiểm riêng |
| require_osd_release=pacific | Không chặn cặp patch này | Cả hai endpoint là Pacific; flag vẫn one-way đối với OSD pre-Pacific và command không cho hạ |
| OSD sau target mount/BlueFS write | **Không an toàn bằng package-only downgrade** | Base reader không hiểu opcode mới và có thể -EIO; cần restore image/device snapshot đã test hoặc forward-only/rebuild plan |
| OSD superblock lower bound | Có điều kiện, cần rehearsal | Target persist cluster_osdmap_trim_lower_bound trong OSDSuperblock v10 với compat 5; base có thể decode nhưng old-writer round-trip sau downgrade chưa được chứng minh. Test clone theo chuỗi downgrade → ghi lại → re-upgrade trước khi coi an toàn |
| CIDR range-blocklist đã tạo | Boundary mạnh | OSDMap có state/encoding mới; giữ unused cho tới khi rollback rehearsal chứng minh procedure |
| Config rename/default | Có điều kiện | Cần snapshot config DB và mapping old↔new; base có thể không hiểu target-only key hoặc lại cần key cũ |
| Alert/Prometheus/Dashboard config | Có thể nếu có artifact | Binary rollback không tự phục hồi 18 rule cũ, routes, silences, query schema hoặc LB selection |
| Cephadm MGR sau migration state 5 | **Không coi base reconciliation là rollback mặc định** | Base 16.2.5 không có transition cho state 5; cần checkpoint/forward-fix strategy và rehearsal trước target promotion |
| Cephadm MDS preparation/stop | Có điều kiện | Stop/cancel không tự chứng minh restore `max_mds`, standby-replay và FS flags; runbook phải lưu/khôi phục state rõ ràng |
| Cephadm container/gateway/monitoring render | Có điều kiện theo service/host | Giữ old/new container name, unit và rendered config artifacts. Binary failback không tự hoàn tác VIP/port/TLS/export/session/retention hoặc post-action đã apply |
| Ceph-volume activation | Có điều kiện | Binary failback không sửa device discovery/tag/mapper sai; giữ inventory, units, keys và test activation theo topology |
| Ceph-volume DB/WAL migration | **Không phải binary rollback** | Undo tag hay hạ package không chứng minh device/data mutation đã đảo. Chỉ restore từ pre-action image hoặc dùng reverse workflow đã rehearsal trong change riêng |
| RBD SSD PWL base → target-compatible | Boundary theo cache/client | Target từ chối layout 0; không xóa cache khi chưa chứng minh clean/empty. Giữ recovery copy và procedure integration/vendor đã test; không mở layout 1 bằng client base vì chiều target→base chưa được endpoint chứng minh an toàn |
| CephFS MDS/client | Theo từng MDS/client và replay direction | Chỉ failback sau khi cả target→base và base→target replay/session/cap path đã rehearsal; restore FS flags/ranks và giữ client drain plan |
| RGW request/shared state | Theo từng process/site; security-limited | Không trả Browser POST traffic về base vulnerable daemon. Binary rollback không undo index/log/orphan/multisite state; drain, endpoint pin và shared-state recovery cần plan riêng |
| Package/service state | Có điều kiện theo distro | First-hop base `%postun` có thể chạy sau target install; cần backup cephadm key/user state, mitigation đã test và package config. Binary rollback không tự hoàn tác scriptlet side effects |
| Repair/quick-fix/migrate/import/reshard/set-superblock | Không phải rollback thường lệ | Restore pre-action image; không chain repair trên state lỗi |
| H0-guided repair một replica | Phục hồi dữ liệu trong phạm vi có nguồn đúng | Phải truyền payload cùng version, giữ metadata/history, đọc lại verify; không phải rollback binary hoặc phục hồi mọi ghi mới |
| Chỉ còn H0, không còn payload khớp | **Không thể restore từ hash** | Giữ incident; cần nguồn dữ liệu độc lập còn tốt nếu muốn phục hồi; không suy từ metadata manifest rằng có backup |

### 9.1 Checklist rollback readiness

- [ ] Chọn một trong hai strategy cho OSD: restoreable snapshot/image **hoặc** forward-only/rebuild được phê duyệt.
- [ ] Nếu chọn image/snapshot restore: chứng minh restore trên clone, không chỉ snapshot tạo thành công. Nếu chọn forward-only/rebuild: chứng minh nguồn payload hợp lệ và rebuild/read-back. Nhánh H chạy thêm T34/T36; không áp bắt buộc snapshot cho mọi nhánh.
- [ ] Lưu MonMap, OSDMap, CRUSH map, FSMap nếu dùng CephFS, config DB và effective config baseline.
- [ ] Lưu package/image repository cần cho failback và xác minh artifact.
- [ ] Lưu rules, routes, silences, Dashboard/LB và custom module artifact tương thích base.
- [ ] Lưu cephadm migration/upgrade state, FS flags/MDS ranks, registry config và daemon placement trước target MGR promotion.
- [ ] Lưu old/new container names, effective units và rendered ingress/iSCSI/NFS/monitoring config cùng service-specific rollback artifact.
- [ ] Nếu có DB/WAL migration change riêng, giữ pre-action device image/tag/map và bằng chứng reverse/restore độc lập với package rollback.
- [ ] Với SSD PWL, lưu cache metadata/copy theo procedure và chứng minh dirty state đã được xử lý trước client target.
- [ ] Với CephFS/RGW, lưu endpoint drain/pin, MDS replay/session state, RGW index/log/marker baseline và security constraint ngăn traffic quay về vulnerable behavior.
- [ ] Lưu package database, effective units/sudoers/SELinux policy, cephadm user/home/key ownership và ceph-volume device/LV/mapper inventory.
- [ ] Định nghĩa role nào được failback, role nào chỉ forward-fix và ai có quyền quyết định.
- [ ] Không tạo CIDR range state hoặc state/tool mutation mới trước rollback checkpoint.
- [ ] Sau rollback, chạy lại health/quorum/PG/data-path/client/monitoring acceptance; rollback command thành công chưa phải rollback hoàn tất.

## 10. Gói bằng chứng và sign-off

Mỗi artifact nên có timestamp UTC, cluster/cohort/batch, lệnh hoặc scenario tạo ra nó, checksum và quyền truy cập/retention. Không ghi secret vào evidence package.

| Hạng mục | Applicability / N-A proof | Gate/test | Owner | PASS/FAIL | Artifact hash/time/cohort | Exception/expiry | Ký/ngày |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Base/target artifact, package/SBOM và vendor-advisory provenance | | G00, T00/T09A | | | | | |
| As-Is health/topology + guardrails | | G01–G04 | | | | | |
| MON quorum/store/maps | | T10/T11/T25 | | | | | |
| OSD/PG/recovery/scrub | | T01–T07, T16–T22 | | | | | |
| BlueStore/BlueFS/RocksDB/device | | G02/G04/G09 | | | | | |
| Config migration/effective values | | T00/T20 | | | | | |
| MGR/custom modules/autoscaler | | T12/T15/T26A | | | | | |
| Prometheus/Dashboard/alerts + independent telemetry | | G05/G06, T04/T13/T14 | | | | | |
| Cephadm topology/staggered/host/lifecycle/render | | G08, T26/T26A/T26B | | | | | |
| Cephadm migration/MDS/NFS/registry | | G08, T26 | | | | | |
| Ceph-volume activation/dm-crypt/device candidates | | G09, T27 | | | | | |
| RBD fast-diff/PWL/journal | | G10, T28/T28A | | | | | |
| RBD mirror/lock/watch/blocklist | | G10, T28B | | | | | |
| CephFS topology/session/mixed-client | | G11, T23/T23A | | | | | |
| CephFS security/volumes/NFS/mirror | | G11, T23B | | | | | |
| RGW per-daemon security/write/auth/TLS | | G11, T24/T24B | | | | | |
| RGW reshard/multisite/workers/repair disposition | | G11, T24A | | | | | |
| Package-common/systemd/sudoers/ceph-crash | | G12, T29 | | | | | |
| RPM first-hop lifecycle/SELinux/cache | | G12, T29A | | | | | |
| AArch64 ISA-L artifact | | G12, T29B | | | | | |
| DEB/custom-build/dencoder/mirror assets | | G12, T09A | | | | | |
| Exact-path suite + coverage exclusions | | G13, T08/T09/T09B | | | | | |
| SEC-001/002 provenance + insecure-reclaim hygiene | | G00, T00 | | | | | |
| SEC-003 Manila/CephFS path-cap audit | | G11, T23B | | | | | |
| SEC-004 ceph-crash privilege/submission | | G12, T29 | | | | | |
| SEC-005 Browser POST closure | | G11, T24B | | | | | |
| Canary batch/soak records | | R0–R5 | | | | | |
| Rollback/restore rehearsal | | G02, §9 | | | | | |
| PA1/PA2 placement, batch/weight, store cleanup và QoS | | G14, T30/T31, R3A/R3B | | | | | |
| H0 provenance, coverage, bản X, dirty/version và source chọn theo hash | | G15, T32/T34/T35, R3H | | | | | |
| Payload repair, durability/read-back, NO_VALID_SOURCE | | G15/G16, T34/T36 | | | | | |
| Enforcement primary/source/read, failover/restart và ghi sau promote | | G15, T33/T35/T37 | | | | | |
| H/B100, nguồn phục hồi và quyết định requirement 100 TB | | G16, T38 | | | | | |

### 10.1 Exception/waiver register

| ID | Gate/test | Phạm vi/cohort | Lý do và residual risk | Compensating control | Owner/approver | Expiry / điều kiện đóng | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

- [ ] Exception không được dùng để bỏ qua artifact mismatch, mất dữ liệu/correctness, rollback boundary chưa hiểu, security bypass đang phục vụ traffic hoặc thiếu telemetry stop/go.
- [ ] Exception hết hạn khi scope/batch thay đổi; phải re-approve trước khi mở rộng.

### 10.2 Tiêu chí ra quyết định cuối

| Quyết định | Điều kiện tối thiểu |
| --- | --- |
| GO LAB | Applicability và G00/G02/G04 đủ cho fixture disposable; G12–G16 áp dụng có artifact, nguồn tái tạo dữ liệu/manifest, plan và owner. Được thử H-LAB để tạo evidence, chưa yêu cầu H-ENFORCE PASS hoặc dựng cụm 100 TB mới |
| GO CANARY | Canary production: mọi gate áp dụng G00–G16 có evidence; PA1/PA2 và H0 tests bắt buộc PASS đúng mức tuyên bố; source/repair/enforcement và telemetry sẵn sàng; nếu bỏ cụm 100 TB có quyết định phạm vi phục hồi được duyệt |
| GO PRODUCTION | Cho phép mở rộng trong phạm vi pilot đã PASS: artifact/coverage/HG, soak, nguồn phục hồi, boundary và sign-off đầy đủ, không STOP mở. Mỗi batch tiếp theo vẫn lặp gate; hoàn tất toàn rollout chỉ sau stabilization tương ứng |
| NO-GO | Có blocker không thể đóng trong window, correctness/security failure, artifact mismatch, enforcement/source/version thiếu, hoặc requirement phục hồi/telemetry chưa đạt. H0 không tự thay requirement payload độc lập |

- [ ] Quyết định ghi timestamp, người phê duyệt, evidence snapshot và danh sách exception còn mở; `HEALTH_OK` hoặc acceptance tài liệu riêng lẻ không đủ cho GO.

## 11. Gợi ý thu thập read-only

Các lệnh dưới đây chỉ là ví dụ thu thập trạng thái; phải review quyền truy cập, output chứa thông tin nhạy cảm và cách lưu bằng chứng của môi trường. Chúng không thay thế inventory device/LVM/dm-crypt, cephadm migration/registry, package state hay client/service-specific evidence.

    ceph -s
    ceph health detail
    ceph versions
    ceph quorum_status -f json-pretty
    ceph mon dump -f json-pretty
    ceph osd dump -f json-pretty
    ceph osd tree -f json-pretty
    ceph osd df tree -f json-pretty
    ceph osd perf -f json-pretty
    ceph df detail -f json-pretty
    ceph pg stat
    ceph config dump -f json-pretty
    ceph mgr dump -f json-pretty
    ceph mgr module ls -f json-pretty
    ceph osd pool autoscale-status
    ceph fs dump -f json-pretty

Nếu nhánh cephadm áp dụng, có thể bổ sung các truy vấn read-only sau sau khi xác nhận CLI endpoint hỗ trợ:

    ceph orch status --format json-pretty
    ceph orch host ls --format json-pretty
    ceph orch ps --format json-pretty
    ceph orch ls --format json-pretty
    ceph orch upgrade status --format json-pretty
    ceph device ls --format json-pretty

Không thu secret/config-key credential vào evidence. Không đưa lệnh repair, trim, mark-lost, map rewrite, config set, feature enable hay daemon upgrade vào phần này.

## 12. Traceability và evidence còn thiếu

### 12.1 Finding → điểm kiểm soát

| Báo cáo / finding | Điểm kiểm soát chính trong checklist |
| --- | --- |
| `00` inventory | §1.1, G00, T00, evidence artifact |
| `OSD-001–008`, `OSD-010–014` | G01/G02/G07, §3.2, T06/T07/T10A/T16–T22/T17B/T21B, R3, STOP/rollback |
| `BS-001–010` | G01/G02/G04, §3.3, T01/T03/T03A/T06/T19/T19A, stabilization, STOP/rollback |
| `KVBD-001–007` | G04/G09, §3.3, T02/T02A/T06/T18/T18A, stabilization và mutation guardrail |
| `MON-001–011` | G01/G03/G07, §3.4, T10/T10A–T10D/T11/T15/T15A/T17A/T20/T25, R2, STOP/rollback |
| `MSG-001–009` | G06/G07, §3.4, T05/T05A/T11/T21/T21A/T23, R2 |
| `CFG-001–007` | G04/G07, §3.5, §4.1–4.3, T00/T15/T15A/T20/T20A/T23/T24/T24C |
| `MGR-001–010` | G05/G06, §3.6, T04/T12–T15/T14A/T15A, R1, stabilization/rollback |
| `ADM-001–009` | G08, §3.7/§4.3, T26/T26A/T26B, R0/R1/R4, STOP/rollback |
| `CVOL-001–006` | G09, §3.7/§4.3, T27, R3, STOP/rollback |
| `RBD-001–007` | G10, §3.8/§4.3, T22/T28/T28A/T28B, R4, STOP/rollback |
| `CEPHFS-001–008` | G07/G11, §3.8/§4.3, T23/T23A/T23B, R4, STOP/rollback |
| `RGW-001–008` | G07/G11, §3.8/§4.3, T24/T24A/T24B, R4, STOP/rollback |
| `BLD-001–010` | G00/G12, §3.7/§4.3, T09A/T29/T29A/T29B, STOP/rollback |
| `SEC-001/002` | §1.1/§3.8, G00, T00; provenance/hygiene pre-base và broader vendor/SBOM review riêng |
| `SEC-003` | G11, T23B; active-MGR legacy Manila discovery/cap audit |
| `SEC-004` | G12, T29; `ceph-crash` privilege + archive/upload |
| `SEC-005` | G11, T24B; Browser POST negative test trên từng serving daemon |
| `VAL-001–008` | G12/G13, §1.4, T08/T09/T09A/T09B/T29, coverage register bên dưới |
| Thiết kế PA1/PA2 mới | §1.6/3.9, G14, T30/T31, R3A/R3B, STOP và journal |
| Thiết kế H0 chọn nguồn/sửa/cấp quyền | §4.5, G15/G16, T32–T37, R3H, STOP, §9 |
| Quyết định về cụm 100 TB | §1.3/1.6, G16, T38, §10.2 |

### 12.2 Test coverage và exclusion register

Không đánh dấu PASS cho một suite nếu không có target SHA/artifact, exact path, filter list, logs/result và failure triage. Repository recipe chỉ là thiết kế test cho tới khi có run artifact.

| Gap/evidence | Endpoint/path thực | Assertion phải chứng minh | Replacement test | PASS/FAIL/accepted gap | Run artifact | Owner/approver |
| --- | --- | --- | --- | --- | --- | --- |
| Pacific p2p exact-path evidence | Recipe bắt đầu `v16.2.5` nhưng đi qua `v16.2.7` rồi latest Pacific | Workload/health liên tục trên đúng target SHA/artifact và path production dự kiến | T09B + direct-hop rehearsal khi runbook không đi qua 16.2.7 | | | |
| Override `mon_mds_skip_sanity` | Pacific p2p để option true | MDS rank/standby/flags và sanity option restore sau success, pause và stop | T23A + T26; ghi exact state trước/sau | | | |
| Filter `TestClsRbd.mirror_snapshot` | Pacific p2p loại testcase | Mirror snapshot demote/promote, lifecycle/backlog, blocklist shutdown và failback đúng assertion owner report | T28B phải lưu từng assertion/result; nếu không chạy thì residual gap cần approver | | | |
| Filter `CmpOmap.cmp_vals_u64_invalid_default` | Workunit loại case đổi semantics | Empty-U64 khác biệt base/target và malformed non-empty behavior đúng, client retry không che kết quả | T08 với result pin theo serving primary | | | |
| Nautilus/Octopus → Pacific suites | Starting endpoint khác base hiện tại | Chỉ hỗ trợ legacy-client/data-origin scenario, không chứng minh current endpoint | Chạy khi estate có nguồn gốc tương ứng; exact path vẫn bắt buộc | | | |
| Unit/integration/package smoke | Phải build/chạy từ artifact target hoặc package set thực | Expected tests/types/imports/packages thật sự PASS trên deployed artifact | T08/T09/T09A và scenario owner; ghi pass/fail/skip riêng | | | |
| `PendingReleaseNotes` | Chỉ claim trong endpoint range và đã reconcile với hunk/history/code | Mỗi claim có owner finding/code evidence; `>=17`/pre-base/archive không tạo blocker | Reconciliation record; không dùng text làm PASS evidence | | | |

### 12.3 Trạng thái closure

- [x] `00`–`15` có đủ cặp Markdown/CSV; component partition và schema đã được validator kiểm tra.
- [x] Mọi finding ID trong `01`–`15` đã có điểm kiểm soát cấu trúc ở applicability/gate/test/rollout/STOP/rollback; điều này **không** có nghĩa scenario đã PASS.
- [ ] As-Is của cluster, deployment path, client estate, service applicability, guardrail số và artifact thực tế chưa được điền.
- [ ] Chưa có run artifact cho build, unit/integration, exact-path suite, lab fault injection, canary, rollback rehearsal hoặc Production soak; mọi scenario mục 6 vẫn là kế hoạch kiểm chứng.
- [ ] Coverage exclusion register, batch records, exception register và owner sign-off chưa được điền.
- [ ] G14–G16/T30–T38 mới là thiết kế, chưa có kết quả H0 chọn nguồn/sửa payload/enforcement, PA1/PA2 so sánh hoặc quyết định bỏ cụm 100 TB.
- [ ] Chưa chứng minh nguồn tốt và aftercare qua nhiều OSD; H0 checksum không được ghi thành bản backup payload.

Vì vậy trạng thái vẫn là **HOLD**. Bước tiếp theo là điền dữ liệu môi trường, đóng `UNKNOWN`, phê duyệt test plan rồi thu execution evidence; không được diễn giải acceptance của tài liệu là phê duyệt Production.


## 13. Nguồn cho phần H0 bổ sung

- [Ceph Pacific — Architecture](https://docs.ceph.com/en/pacific/architecture/): vai trò PG/replication và scrub. Đổi primary không tự đồng nghĩa chép toàn store đè các bản còn lại.
- [Ceph Pacific — Repairing PG inconsistencies](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/): chẩn đoán và lựa chọn bản authoritative; không suy `pg repair` nhận được H0 ngoại sinh.
- [Ceph Pacific — CRUSH maps / primary affinity](https://docs.ceph.com/en/pacific/rados/operations/crush-map/#primary-affinity): affinity là đầu vào lựa chọn primary, không phải hàng rào H0 cho mọi nguồn dữ liệu.
- [Ceph Pacific — RBD mirroring](https://docs.ceph.com/en/pacific/rbd/rbd-mirroring/), [RGW multisite](https://docs.ceph.com/en/pacific/radosgw/multisite/): đối chiếu mô hình dịch vụ B100.

Phần H0-guided repair, HG0–HG5 và enforcement là đề xuất cần phát triển và kiểm chứng của dự án. Lần cập nhật chỉ sửa tài liệu; chưa chạy Ceph hoặc xác nhận source build tùy biến hoạt động.
