# As-Is evidence — Pacific 16.2.5 trước khi lên 16.2.15

Tài liệu này là sổ thu thập hiện trạng bắt buộc trước khi quyết định chạy hop. Nó chỉ mô tả bằng chứng cần có; không thực thi lệnh trên cluster. Mỗi artifact phải chứa timestamp, cluster FSID đã che phù hợp, người thu thập và lệnh hoặc truy vấn nguồn.

| ID | Phạm vi | Cách thu thập bắt buộc | Artifact tối thiểu | Runtime gates được phục vụ | Trạng thái |
|---|---|---|---|---|---|
| AS-001 | Exact artifact và nguồn cài đặt | Chốt digest image hoặc NEVRA package, repo snapshot, key và binary thực dùng cho hai đầu hop. | Manifest có SHA256, provenance, timestamp và chữ ký người xác nhận. | G00, G12, G13, T00, T09A, T09B, T29, T29A, T29B | NOT_CAPTURED |
| AS-002 | Health và dung lượng nền | Chụp health detail, df, osd df tree, pool detail và headroom tại cùng một thời điểm yên ổn. | Bundle JSON và text có timestamp, ngưỡng stop và diễn giải cảnh báo. | G01, G14, T17, T17A, T19, T20A, T30, T31 | NOT_CAPTURED |
| AS-003 | Phiên bản và daemon coverage | Liệt kê version theo từng daemon, host, container hoặc package và đối chiếu daemon bị thiếu. | Bảng coverage 100 phần trăm daemon kèm nguồn inventory. | G00, G06, G08, G13, T09B, T12, T26, T26A | NOT_CAPTURED |
| AS-004 | MON, quorum và release floor | Chụp mon dump, quorum status, monmap, feature map và các release flag hiện hành. | Snapshot control-plane có quorum member, epoch và floor trước hop. | G03, T10, T10A, T10B, T10C, T10D, T11 | NOT_CAPTURED |
| AS-005 | OSD, CRUSH và placement | Chụp osd tree, crush dump, rule, pool mapping, affinity và topology failure-domain. | Bộ JSON đủ tái dựng placement và so sánh trước sau. | G14, T16, T17, T17A, T17B, T20, T21B, T25, T30, T31 | NOT_CAPTURED |
| AS-006 | BlueStore, BlueFS và thiết bị | Kiểm kê backend, DB WAL, encryption, device alias, allocator và dấu vết repair từng OSD. | Bảng OSD đến thiết bị có serial đã che, layout, backend và cờ bất thường. | G02, G04, G09, T01, T02, T02A, T03, T03A, T06, T18A, T19, T19A, T27 | NOT_CAPTURED |
| AS-007 | Cấu hình và default hiệu lực | Xuất config dump, config assimilate-conf dry review, overrides và giá trị runtime quan trọng. | Diff cấu hình chuẩn hóa có nguồn, scope daemon và quyết định giữ hoặc bỏ. | G04, G07, T03, T05, T15A, T20, T20A, T21A, T24C | NOT_CAPTURED |
| AS-008 | Cephadm và orchestrator | Chụp orch status, host, daemon, service spec, upgrade state, registry và migration state. | Inventory orchestrator cùng bản sao spec và secret reference đã che. | G08, T26, T26A, T26B | NOT_CAPTURED |
| AS-009 | MGR và module | Chụp active standby, module list, module config, autoscaler và balancer state. | Snapshot MGR có module owner, failover expectation và cache consumer. | G05, G06, T11, T12, T15, T17A | NOT_CAPTURED |
| AS-010 | Monitoring và cảnh báo | Lưu rule, dashboard, scrape target, metric schema và alert đang firing ở baseline. | Export giám sát có query kiểm tra duplicate metric và khoảng trống dữ liệu. | G01, G05, T04, T13, T14, T14A, T19A, T20A | NOT_CAPTURED |
| AS-011 | PG, scrub và recovery | Chụp PG states, stuck set, scrub schedule, recovery queue, inconsistent objects và flags. | Baseline PG có zero hoặc waiver ký duyệt cho từng bất thường. | G01, G02, T07, T16, T17, T17A, T17B, T18, T19 | NOT_CAPTURED |
| AS-012 | RADOS và RBD | Kiểm kê pool, image feature, mirror, journal, PWL cache, lock watch và khách hàng nhạy cảm. | Ma trận image và workload với oracle dữ liệu, latency và rollback. | G10, T08, T22, T28, T28A, T28B | NOT_CAPTURED |
| AS-013 | Client estate | Liệt kê kernel, librados, librbd, mount helper, SDK, platform và phiên bản client thực tế. | Ma trận client production với owner, test case và thời gian nâng cấp. | G06, G07, G10, G11, T05, T08, T09, T21, T22, T23, T24, T28 | NOT_CAPTURED |
| AS-014 | CephFS và MDS | Chụp fs dump, MDS rank, session, cap, mirror, volume clone, NFS export và auth. | Bundle CephFS có session inventory và oracle failover replay. | G07, G11, T09, T23, T23A, T23B, T26 | NOT_CAPTURED |
| AS-015 | RGW | Chụp realm zonegroup zone, period, multisite sync, bucket index, lifecycle, IAM STS và notification. | Bundle RGW có sync lag, request oracle và cấu hình frontend. | G07, G11, T05, T05A, T24, T24A, T24B, T24C | NOT_CAPTURED |
| AS-016 | Tích hợp và bảo mật | Kiểm kê Manila, Ganesha, TLS, FIPS, CephX caps, KMS, registry và consumer metric. | Ma trận tích hợp có owner, credential reference đã che và ca xác minh. | G07, G11, G12, T05, T14, T14A, T24B, T24C, T29 | NOT_CAPTURED |
| AS-017 | Host, runtime và package | Chụp OS, kernel, container runtime, systemd unit, repo, package set, architecture và filesystem. | Host matrix có compatibility verdict và lệnh tái tạo package closure. | G00, G09, G12, T00, T05, T09A, T27, T29, T29A, T29B | NOT_CAPTURED |
| AS-018 | Snapshot, restore và rollback | Xác nhận backup control-plane, snapshot dữ liệu, restore drill và từng ranh giới không đảo ngược. | Biên bản restore gần nhất có RTO RPO, checksum và người phê duyệt. | G02, G08, G10, G11, G16, T01, T06, T10C, T10D, T17B, T18, T26, T28A, T32, T38 | NOT_CAPTURED |
| AS-019 | Workload, SLO và capacity | Ghi baseline IOPS, latency, throughput, recovery budget, placement và headroom của workload đại diện. | Dashboard export và kết quả replay có ngưỡng canary, stop, resume. | G01, G05, G14, G15, G16, T13, T16, T17, T19, T20A, T21, T23, T24, T25, T30, T31, T32, T33, T34, T35, T36, T37, T38 | NOT_CAPTURED |
| AS-020 | Evidence index và phê duyệt | Lập chỉ mục immutable cho artifact, owner, thời gian, checksum, waiver và liên kết gate. | Evidence index được reviewer độc lập ký và không có đường dẫn mơ hồ. | G13, G14, G15, G16, T09B, T30, T31, T32, T33, T34, T35, T36, T37, T38 | NOT_CAPTURED |

## Quy tắc trạng thái

- `NOT_CAPTURED`: chưa có artifact thực tế; đây là mặc định hiện tại.
- `CAPTURED`: artifact tồn tại, đọc được, có provenance và đã qua review.
- `BLOCKED`: không thể thu thập và đã ghi rõ nguyên nhân, owner, thời hạn.
- `NOT_APPLICABLE`: chỉ dùng khi có bằng chứng chứng minh phạm vi không tồn tại trên cluster.

Các mục `T30` đến `T38` là bằng chứng lịch sử hoặc nghiên cứu H0. Chúng vẫn được lập chỉ mục để quyết định applicability, nhưng không tự động trở thành yêu cầu PA2 mặc định.
