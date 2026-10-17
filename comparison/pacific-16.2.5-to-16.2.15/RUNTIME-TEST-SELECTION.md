# Test-selection manifest — Pacific 16.2.5 lên 16.2.15

**Trạng thái ngày 13/10/2026: 16/16 test pack `NOT_RUN`.** Manifest ánh xạ 85 gate/test sang source suite ở tag `v16.2.15` hoặc harness phải viết thêm. Sự tồn tại của source path chỉ là bằng chứng thiết kế, không phải kết quả test và không cho phép chạy fault injection trên production.

## Phân loại coverage

- `NATIVE_HOP`: recipe được thiết kế đúng direct hop và vẫn phải khóa exact artifact.
- `REUSABLE`: component suite phù hợp hành vi nhưng phải ghép vào topology upgrade.
- `HYBRID`: có source recipe một phần, còn thiếu exact-hop pin, fixture hoặc assertion.
- `CUSTOM`: chưa có recipe nguồn đủ để đóng gate; cần collector hoặc job được review riêng.

Native subtree `qa/suites/upgrade/pacific-p2p` ở target parse sạch nhưng đi qua `v16.2.7` trước latest Pacific, vì vậy pack dùng subtree này được xếp `HYBRID`, không phải `NATIVE_HOP`. Tất cả selector phải được thay bằng artifact trong `EXACT-HOP-PIN-MANIFEST` trước execution.

## Test packs

| Pack | Tier | Mode | Source assets ở `v16.2.15` | Mục đích và adaptation bắt buộc | Runtime gates đóng góp | Trạng thái |
|---|---|---|---|---|---|---|
| TP-01 | P0 | CUSTOM | Không có recipe duy nhất; dùng artifact collector của dự án | Khóa package, image, repo, harness, config overrides và archive layout trước mọi run. | G00, G12, G13, T00, T09A, T09B, T29, T29A, T29B | NOT_RUN |
| TP-02 | P0 | HYBRID | `qa/suites/upgrade/pacific-p2p` | Adapt recipe thành direct v16.2.5 đến v16.2.15, bỏ intermediate 16.2.7, pin exact artifacts và ghi version timeline. | G01, G03, G06, G08, G13, G14, T09B, T10, T10A, T10B, T10C, T10D, T11, T12, T17, T17A, T19, T20A, T26, T26A, T30, T31 | NOT_RUN |
| TP-03 | P0 | REUSABLE | `qa/suites/rados/basic`<br>`qa/suites/rados/monthrash`<br>`qa/suites/rados/objectstore`<br>`qa/suites/rados/perf`<br>`qa/suites/rados/singleton` | Ghép PG, scrub, recovery, EC, CRUSH và objectstore oracle vào cohort exact-hop; threshold lấy từ As-Is. | G01, G02, G14, T07, T16, T17, T17A, T17B, T18, T19, T20, T21B, T25, T30, T31 | NOT_RUN |
| TP-04 | P0 | HYBRID | `qa/suites/rados/objectstore`<br>`src/ceph-volume/ceph_volume/tests` | Thêm disposable block devices để kiểm BlueFS replay, allocator, alias, errno, DB WAL và activation; cấm dùng production disk. | G02, G04, G09, T01, T02, T02A, T03, T03A, T06, T18A, T19, T19A, T27 | NOT_RUN |
| TP-05 | P0 | HYBRID | `qa/suites/rados/basic`<br>`qa/suites/rados/mgr` | Capture effective config trước sau restart, kiểm removed keys, autoscaler, pool command và address lifecycle. | G04, G07, T03, T05, T15A, T20, T20A, T21A, T24C | NOT_RUN |
| TP-06 | P0 | HYBRID | `qa/suites/orch/cephadm/upgrade`<br>`qa/suites/orch/cephadm/orchestrator_cli`<br>`qa/suites/orch/cephadm/workunits`<br>`qa/suites/orch/cephadm/osds` | Pin direct hop, kiểm pause resume failover, spec round-trip, registry, migration state và device activation. | G08, T26, T26A, T26B | NOT_RUN |
| TP-07 | P0 | REUSABLE | `qa/suites/rados/mgr`<br>`qa/suites/rados/dashboard` | Chạy MGR failover, module state, Prometheus parser, dashboard query và alert-route assertions trong mixed phase. | G05, G06, T04, T11, T12, T13, T14, T14A, T15, T17A, T19A, T20A | NOT_RUN |
| TP-08 | P0 | HYBRID | `qa/suites/rbd/librbd`<br>`qa/suites/rbd/cli`<br>`qa/suites/rbd/encryption`<br>`qa/suites/rbd/migration`<br>`qa/suites/rbd/mirror`<br>`qa/suites/rbd/pwl-cache` | Tạo old-client new-daemon và new-client old-daemon lanes; thêm PWL layout, mirror, lock, diff và checksum oracle. | G06, G10, T05, T08, T09, T21, T22, T28, T28A, T28B | NOT_RUN |
| TP-09 | P0 | HYBRID | `qa/suites/fs/functional`<br>`qa/suites/fs/mixed-clients`<br>`qa/suites/fs/mirror`<br>`qa/suites/fs/thrash` | Ghép MDS ordering với kernel FUSE matrix, session replay, caps, clone purge, NFS và mirror evidence. | G07, G11, T09, T23, T23A, T23B, T26 | NOT_RUN |
| TP-10 | P0 | HYBRID | `qa/suites/rgw/verify`<br>`qa/suites/rgw/singleton`<br>`qa/suites/rgw/multisite` | Chạy mixed daemon order, Browser POST negative, timeout write, reshard, multisite, IAM STS và TLS auth oracle. | G07, G11, T05, T05A, T24, T24A, T24B, T24C | NOT_RUN |
| TP-11 | P0 | CUSTOM | Không có recipe end-to-end cho toàn bộ integration và security estate | Dựng fixture cho Manila, Ganesha, TLS, FIPS, CephX caps, Vault, registry và alert consumer theo applicability. | G07, G11, G12, T05, T14, T14A, T24B, T24C, T29 | NOT_RUN |
| TP-12 | P0 | CUSTOM | Không có recipe duy nhất cho direct package transition trên mọi distro | Rehearse RPM scriptlet, DEB dependency, systemd, cephadm user home key và AArch64 artifact trong disposable VM. | G00, G09, G12, T00, T05, T09A, T27, T29, T29A, T29B | NOT_RUN |
| TP-13 | P0 | CUSTOM | Không có recipe state-aware đủ cho downgrade và restore boundary | Snapshot control-plane và data clone, diễn tập rollback package, store, cephadm, RBD, CephFS và RGW với checksum. | G02, G08, G10, G11, G16, T01, T06, T10C, T10D, T17B, T18, T26, T28A, T32, T38 | NOT_RUN |
| TP-14 | P0 | HYBRID | `qa/suites/rados/perf`<br>`qa/suites/rados/monthrash`<br>`qa/suites/rbd/librbd`<br>`qa/suites/fs/functional`<br>`qa/suites/rgw/verify` | Chạy workload đại diện với SLO, placement rotation, recovery budget và capacity threshold lấy từ As-Is. | G01, G05, G14, G15, G16, T13, T16, T17, T19, T20A, T21, T23, T24, T25, T30, T31, T32, T33, T34, T35, T36, T37, T38 | NOT_RUN |
| TP-15 | P0 | CUSTOM | Không có source suite thay thế evidence-board closure | Gom run ID, digest, raw output, rerun, blocker, waiver, owner và reviewer cho từng gate trước sign-off. | G13, G14, G15, G16, T09B, T30, T31, T32, T33, T34, T35, T36, T37, T38 | NOT_RUN |
| TP-16 | P1 | CUSTOM | Không có direct recipe chứng minh thiết kế H0 lịch sử cho PA2 hiện hành | Quyết định applicability riêng cho T30 đến T38; nếu chạy thì dùng clone, không biến evidence gián tiếp thành PASS exact-hop. | T30, T31, T32, T33, T34, T35, T36, T37, T38 | NOT_RUN |

## Thứ tự triển khai

1. TP-01 khóa artifact; TP-02 tạo direct-hop harness thay vì dùng nguyên recipe có intermediate.
2. TP-03 đến TP-07 chạy control-plane, OSD, device và observability trước stateful client services.
3. TP-08 đến TP-11 chạy RBD, CephFS, RGW và integration theo As-Is applicability.
4. TP-12 và TP-13 phải đạt trước canary; TP-14 chạy workload; TP-15 đóng evidence.
5. TP-16 chỉ chạy khi change authority xác nhận thiết kế lịch sử còn áp dụng.

Exit code 0 của một suite không tự đóng gate. PASS còn cần đúng precondition, action, expected result, STOP condition và artifact quy định trong checklist.
