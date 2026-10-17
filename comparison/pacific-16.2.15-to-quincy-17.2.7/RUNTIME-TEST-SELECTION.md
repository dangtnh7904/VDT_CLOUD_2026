# Test-selection manifest — Pacific 16.2.15 lên Quincy 17.2.7

**Trạng thái ngày 13/10/2026: 15/15 test pack `NOT_RUN`.** Manifest ánh xạ 43 LAB gate sang source suite ở tag `v17.2.7` hoặc harness cần viết thêm. Source path tồn tại không phải runtime result và không cấp quyền chạy thao tác destructive trên production.

## Phân loại coverage

- `NATIVE_HOP`: recipe được thiết kế đúng hop nhưng vẫn phải khóa branch, image và harness.
- `REUSABLE`: component suite phù hợp hành vi nhưng phải ghép vào topology upgrade.
- `HYBRID`: có source recipe một phần, còn cần exact pin, fixture hoặc assertion riêng.
- `CUSTOM`: chưa có recipe nguồn đủ để đóng gate; cần job hoặc collector được review.

Subtree `qa/suites/upgrade/pacific-x` là nguồn native gần nhất nhưng chứa branch và image selector nổi. Vì chưa có artifact pin và run result, pack tương ứng được giữ `HYBRID` thay vì tuyên bố exact-hop hợp lệ.

## Test packs

| Pack | Tier | Mode | Source assets ở `v17.2.7` | Mục đích và adaptation bắt buộc | Runtime gates đóng góp | Trạng thái |
|---|---|---|---|---|---|---|
| TP-01 | P0 | CUSTOM | Không có recipe duy nhất; dùng artifact collector của dự án | Khóa package, image, repo, signing key, harness, config override và evidence layout trước run. | LAB-001, LAB-004, LAB-006, LAB-051 | NOT_RUN |
| TP-02 | P0 | HYBRID | `qa/suites/upgrade/pacific-x` | Thay branch và image nổi bằng exact v16.2.15, v17.2.7; giữ quorum, OSD cohorts, workload, pause resume và release-floor guard. | LAB-002, LAB-010, LAB-011, LAB-012, LAB-020, LAB-021, LAB-024, LAB-025, LAB-050 | NOT_RUN |
| TP-03 | P0 | HYBRID | `qa/suites/orch/cephadm/upgrade`<br>`qa/suites/orch/cephadm/orchestrator_cli`<br>`qa/suites/orch/cephadm/workunits`<br>`qa/suites/orch/cephadm/osds` | Kiểm pause resume failover, spec round-trip, host and device inventory, registry, placement và service continuity. | LAB-003, LAB-012, LAB-013, LAB-014, LAB-018, LAB-019 | NOT_RUN |
| TP-04 | P0 | REUSABLE | `qa/suites/rados/mgr`<br>`qa/suites/rados/dashboard` | Chạy MGR failover, .mgr state, Prometheus exporter, module configuration, dashboard và alert assertions. | LAB-003, LAB-013, LAB-015, LAB-016, LAB-018, LAB-019 | NOT_RUN |
| TP-05 | P0 | REUSABLE | `qa/suites/rados/basic`<br>`qa/suites/rados/monthrash`<br>`qa/suites/rados/objectstore`<br>`qa/suites/rados/perf`<br>`qa/suites/rados/singleton` | Ghép mClock, PG, scrub, recovery, SnapMapper, BlueStore và CRUSH oracle vào exact-hop cohort. | LAB-020, LAB-021, LAB-022, LAB-023, LAB-024, LAB-025, LAB-026, LAB-027, LAB-028 | NOT_RUN |
| TP-06 | P0 | HYBRID | `src/ceph-volume/ceph_volume/tests`<br>`qa/suites/orch/cephadm/osds` | Unit guard phải đi cùng disposable disks để kiểm device identity, mapper, dm-crypt, activation, zap và restore. | LAB-014, LAB-017, LAB-022, LAB-023, LAB-026, LAB-027, LAB-028 | NOT_RUN |
| TP-07 | P0 | HYBRID | `qa/suites/rbd/librbd`<br>`qa/suites/rbd/cli`<br>`qa/suites/rbd/encryption`<br>`qa/suites/rbd/migration`<br>`qa/suites/rbd/mirror`<br>`qa/suites/rbd/pwl-cache` | Tạo old-client new-daemon và new-client old-daemon lanes; thêm LUKS alignment, PWL, mirror, diff và checksum oracle. | LAB-005, LAB-033, LAB-034, LAB-035 | NOT_RUN |
| TP-08 | P0 | HYBRID | `qa/suites/fs/functional`<br>`qa/suites/fs/mixed-clients`<br>`qa/suites/fs/mirror`<br>`qa/suites/fs/thrash` | Ghép MDS ordering với kernel FUSE matrix, session replay, legacy volume import, mirror, clone và failback. | LAB-030, LAB-031, LAB-032 | NOT_RUN |
| TP-09 | P0 | HYBRID | `qa/suites/rgw/verify`<br>`qa/suites/rgw/singleton`<br>`qa/suites/rgw/multisite` | Chạy two-order upgrade, S3 object oracle, multisite sync, reshard, IAM STS, frontend và persistence paths. | LAB-040, LAB-041, LAB-042, LAB-043, LAB-044, LAB-045 | NOT_RUN |
| TP-10 | P0 | HYBRID | `qa/suites/rgw/lifecycle`<br>`qa/suites/rgw/notifications`<br>`qa/suites/rgw/multisite` | Thêm HTTP AMQP Kafka collector, lifecycle, cloud transition, notification dedupe, sync retry và tracing assertions. | LAB-043, LAB-044, LAB-045, LAB-046, LAB-047, LAB-048, LAB-049 | NOT_RUN |
| TP-11 | P0 | CUSTOM | Không có recipe end-to-end cho package và host estate thực tế | Rehearse split package, weak dependency, systemd, container runtime, client library và distro closure trong VM disposable. | LAB-001, LAB-006, LAB-014, LAB-017, LAB-028, LAB-031, LAB-035 | NOT_RUN |
| TP-12 | P0 | CUSTOM | Không có recipe state-aware đủ cho mọi rollback boundary | Snapshot control-plane và data clone, diễn tập downgrade trước floor cùng forward recovery sau irreversible boundary. | LAB-003, LAB-022, LAB-023, LAB-026, LAB-027, LAB-032, LAB-050 | NOT_RUN |
| TP-13 | P0 | HYBRID | `qa/suites/rados/basic`<br>`qa/suites/rados/mgr`<br>`qa/suites/rgw/singleton` | Capture effective config trước sau restart, kiểm scheduler, bind range, module state và removed RGW option. | LAB-002, LAB-010, LAB-015, LAB-020, LAB-028 | NOT_RUN |
| TP-14 | P0 | HYBRID | `qa/suites/rados/perf`<br>`qa/suites/rados/monthrash`<br>`qa/suites/rbd/librbd`<br>`qa/suites/fs/functional`<br>`qa/suites/rgw/verify` | Chạy workload đại diện với SLO, capacity, placement, recovery budget và service latency lấy từ As-Is. | LAB-020, LAB-021, LAB-023, LAB-024, LAB-025, LAB-030, LAB-033, LAB-040, LAB-041 | NOT_RUN |
| TP-15 | P0 | CUSTOM | Không có source suite thay thế evidence-board closure | Gom run ID, raw output, digest, rerun, blocker, waiver, owner và reviewer cho mọi LAB gate trước sign-off. | LAB-004, LAB-050, LAB-051 | NOT_RUN |

## Thứ tự triển khai

1. TP-01 khóa artifact, sau đó TP-02 và TP-03 dựng exact-hop control-plane.
2. TP-04 đến TP-06 chạy MGR, OSD, device và observability trên clone.
3. TP-07 đến TP-10 chạy RBD, CephFS và RGW theo As-Is applicability.
4. TP-11 và TP-12 phải đạt trước canary; TP-13 và TP-14 đóng config cùng SLO.
5. TP-15 chỉ đóng khi mọi gate applicable có artifact độc lập và reviewer.

Exit code 0 của một suite không tự đóng LAB gate. PASS còn cần đúng precondition, expected result, STOP signal và evidence quy định trong `LAB-RUNTIME-GATES.md`.
