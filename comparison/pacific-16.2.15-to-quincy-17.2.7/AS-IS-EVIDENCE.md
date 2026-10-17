# As-Is evidence — Pacific 16.2.15 trước khi lên Quincy 17.2.7

Đây là sổ thu thập hiện trạng bắt buộc trước quyết định vận hành. Tài liệu không chạy lệnh trên cluster và không suy ra kết quả lab. Mỗi artifact phải ghi timestamp, nguồn lệnh hoặc truy vấn, cluster identity đã che phù hợp, checksum và người review.

| ID | Phạm vi | Cách thu thập bắt buộc | Artifact tối thiểu | Runtime gates được phục vụ | Trạng thái |
|---|---|---|---|---|---|
| AS-001 | Exact artifact và nguồn cài đặt | Chốt image digest, package NEVRA, repository snapshot, signing key và binary hai đầu hop. | Manifest có SHA256, provenance, timestamp và chữ ký reviewer độc lập. | LAB-001, LAB-004, LAB-006 | NOT_CAPTURED |
| AS-002 | Health và capacity baseline | Chụp health detail, df, osd df tree, pool detail và headroom lúc cluster ổn định. | Bundle JSON và text có ngưỡng stop cùng giải thích mọi cảnh báo. | LAB-002, LAB-020, LAB-021, LAB-024, LAB-025 | NOT_CAPTURED |
| AS-003 | Version và daemon coverage | Liệt kê version từng daemon, host, image hoặc package và nhận diện daemon thiếu inventory. | Bảng coverage toàn bộ daemon có liên kết tới nguồn inventory. | LAB-001, LAB-004, LAB-012, LAB-051 | NOT_CAPTURED |
| AS-004 | MON, quorum và release floor | Chụp mon dump, quorum status, monmap, feature map và require-osd-release hiện tại. | Snapshot control-plane có epoch, quorum member và floor trước hop. | LAB-010, LAB-011, LAB-050 | NOT_CAPTURED |
| AS-005 | OSD, CRUSH và placement | Xuất osd tree, crush dump, rules, pool mapping, affinity và failure-domain. | Bộ JSON đủ tái dựng placement và so sánh trước sau. | LAB-020, LAB-021, LAB-024, LAB-025 | NOT_CAPTURED |
| AS-006 | Backend và thiết bị OSD | Kiểm kê BlueStore, legacy backend, DB WAL, encryption, mapper, allocator và device health. | Device matrix từng OSD có backend, path, encryption và dấu vết repair. | LAB-014, LAB-017, LAB-022, LAB-023, LAB-026, LAB-027, LAB-028 | NOT_CAPTURED |
| AS-007 | Cấu hình và default hiệu lực | Xuất config dump, overrides, scheduler, bind range, compression và option đã bị loại. | Diff cấu hình chuẩn hóa có scope daemon và quyết định giữ hoặc bỏ. | LAB-002, LAB-010, LAB-015, LAB-020, LAB-028 | NOT_CAPTURED |
| AS-008 | Cephadm và orchestrator | Chụp orch status, hosts, daemons, specs, upgrade state, registry và migration state. | Inventory orchestrator cùng bản sao spec và secret reference đã che. | LAB-003, LAB-012, LAB-013, LAB-014, LAB-018, LAB-019 | NOT_CAPTURED |
| AS-009 | MGR và module | Chụp active standby, module list, module config, device health, autoscaler và balancer. | Snapshot MGR có module owner, failover expectation và storage state. | LAB-003, LAB-013, LAB-015, LAB-016, LAB-018, LAB-019 | NOT_CAPTURED |
| AS-010 | Monitoring và alert contract | Lưu scrape targets, metric names, dashboards, alerts, telemetry và exporter topology. | Export giám sát có query kiểm schema, duplicate và data gap. | LAB-015, LAB-016, LAB-020, LAB-021 | NOT_CAPTURED |
| AS-011 | PG, scrub và recovery | Chụp PG states, stuck set, scrub schedule, recovery queue, flags và inconsistent objects. | Baseline PG có zero hoặc waiver được ký cho mọi bất thường. | LAB-020, LAB-021, LAB-022, LAB-023, LAB-024, LAB-025 | NOT_CAPTURED |
| AS-012 | RADOS và RBD | Kiểm kê pool, image features, mirror, encryption, lock watch, cache và workload đại diện. | Ma trận image workload có oracle dữ liệu, latency và failback. | LAB-033, LAB-034, LAB-035 | NOT_CAPTURED |
| AS-013 | Client estate | Liệt kê kernel, librados, librbd, mount helper, SDK, cryptsetup và client thực tế. | Ma trận client production với owner, version và test case tương ứng. | LAB-005, LAB-031, LAB-035 | NOT_CAPTURED |
| AS-014 | CephFS và MDS | Chụp fs dump, MDS ranks, sessions, caps, mirror, volumes, clone và NFS export. | Bundle CephFS có session inventory và oracle failover replay. | LAB-030, LAB-031, LAB-032 | NOT_CAPTURED |
| AS-015 | RGW và multisite | Chụp realm, zonegroup, zone, period, sync, bucket index, reshard, IAM STS và notification. | Bundle RGW có sync lag, request oracle và cấu hình frontend. | LAB-040, LAB-041, LAB-042, LAB-043, LAB-044, LAB-045, LAB-046, LAB-047, LAB-048, LAB-049 | NOT_CAPTURED |
| AS-016 | External integration và security | Kiểm kê TLS, CephX caps, KMS, registry, tracing, proxy, NFS và consumer API. | Ma trận integration có owner, secret reference đã che và ca xác minh. | LAB-019, LAB-040, LAB-042, LAB-046, LAB-047, LAB-049 | NOT_CAPTURED |
| AS-017 | Host, runtime và package | Chụp OS, kernel, architecture, container runtime, systemd unit, repo và package closure. | Host matrix có compatibility verdict và lệnh tái tạo package set. | LAB-001, LAB-006, LAB-014, LAB-017, LAB-028, LAB-031, LAB-035 | NOT_CAPTURED |
| AS-018 | Snapshot, restore và rollback | Xác nhận backup control-plane, snapshot data, restore drill và mọi irreversible boundary. | Biên bản restore gần nhất có RTO RPO, checksum và người duyệt. | LAB-003, LAB-022, LAB-023, LAB-026, LAB-027, LAB-032, LAB-050 | NOT_CAPTURED |
| AS-019 | Workload, SLO và headroom | Ghi IOPS, latency, throughput, recovery budget, placement và capacity của workload đại diện. | Dashboard export và replay result có ngưỡng canary, stop, resume. | LAB-020, LAB-021, LAB-023, LAB-024, LAB-025, LAB-030, LAB-033, LAB-040, LAB-041 | NOT_CAPTURED |
| AS-020 | Evidence index và sign-off | Lập chỉ mục immutable cho artifact, owner, checksum, thời gian, waiver và gate. | Evidence index được reviewer ký và không chứa đường dẫn mơ hồ. | LAB-004, LAB-050, LAB-051 | NOT_CAPTURED |

## Quy tắc trạng thái

- `NOT_CAPTURED`: chưa có artifact thực tế; đây là mặc định hiện tại.
- `CAPTURED`: artifact tồn tại, đọc được, có provenance và đã qua review.
- `BLOCKED`: không thể thu thập và đã ghi nguyên nhân, owner, thời hạn.
- `NOT_APPLICABLE`: chỉ dùng khi inventory chứng minh phạm vi không tồn tại.
