# Test-selection manifest cho Quincy 17.2.7 → Reef 18.2.7

**Trạng thái ngày 12/10/2026: 19/19 test pack `NOT_RUN`.** Manifest này chỉ ra source suite/task/workunit ở tag `v18.2.7` có thể tái sử dụng cho từng runtime gate, đồng thời đánh dấu phần phải adapt hoặc viết riêng. Source path tồn tại không phải test result và không cấp quyền chạy fault injection hay thay đổi cluster production.

## Phân loại coverage

- `NATIVE_HOP`: target có suite được thiết kế trực tiếp cho Quincy→Reef. Vẫn phải thay floating branch/image bằng exact artifacts và lưu harness pins.
- `REUSABLE`: target có component suite/workunit phù hợp hành vi, nhưng không phải exact-hop; phải ghép vào topology upgrade và chạy ở đúng mixed/full phase.
- `HYBRID`: có một phần source recipe, phần còn lại cần fixture/manual assertion riêng.
- `CUSTOM`: không có ready-made source recipe đủ cho gate; phải viết job/collector mới, review trước khi chạy.

Mỗi pack chỉ là một nguồn coverage. Một gate chỉ được `PASS` khi đạt toàn bộ precondition/action/evidence/STOP condition trong `LAB-RUNTIME-GATES.md`, không phải khi một suite liên quan trả exit code 0.

Các pack native/hybrid phải đóng [12 exact-hop pins](./EXACT-HOP-PINS.md) tương ứng trước khi job được gắn nhãn `EXACT_HOP_VALID`.

## Audit graph native suite ở target

`tools/audit_native_suite_graph.py --strict` đọc trực tiếp tree của target SHA `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad` cho `qa/suites/upgrade/quincy-x` và `qa/suites/upgrade/telemetry-upgrade/quincy-x`. Audit hiện xác nhận 57 entry gồm 40 file thường và 17 symlink; cả 17 symlink, kể cả chuỗi `.qa` lồng nhau, đều resolve tới đích tồn tại. Toàn bộ 33 file YAML parse được, không có lỗi cú pháp.

Audit cũng giữ nguyên các lý do native suite chưa phải exact-hop result: 16 occurrence `branch: quincy`, 3 `cephadm_branch: quincy`, 3 base image tag nổi, 3 target image dùng `$sha1` và 7 phép kiểm version dựa trên `$sha1`. Trong source có 2 occurrence kiểm `require_osd_release`, 26 occurrence thao tác cephadm upgrade, 4 pause, 4 resume và 5 thrasher; không thấy selector trực tiếp cho `set-require-min-compat-client`, zap hay repair trong hai subtree này. Đây là số occurrence trong source graph, không phải số test case độc lập hay bằng chứng execution. Audit chỉ chứng minh topology, link integrity và YAML loadability ở endpoint target; 19/19 pack vẫn `NOT_RUN`.

## Test packs

| Pack | Tier | Mode | Source assets ở `v18.2.7` | Mục đích và adaptation bắt buộc | Runtime gates đóng góp | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| TP-01 | P0 | CUSTOM | Không có recipe duy nhất; dùng artifact manifest và collector do dự án tạo | Pin base/target package, image, cephadm, SBOM, harness commit, overrides và archive layout trước mọi job | `LAB-001`, `LAB-004`, `LAB-054` | NOT_RUN |
| TP-02 | P0 | NATIVE_HOP | `qa/suites/upgrade/quincy-x/filestore-remove-check` | Chạy FileStore negative trên disposable fixture và BlueStore positive control bằng exact artifacts; không dùng production OSD | `LAB-002`, `LAB-007` | NOT_RUN |
| TP-03 | P0 | NATIVE_HOP | `qa/suites/upgrade/quincy-x/parallel` | Thay branch/image nổi bằng v17.2.7/v18.2.7 digest; giữ RADOS/RBD workloads, version timeline và checksum xuyên cephadm upgrade | `LAB-004`, `LAB-012`, `LAB-019`, `LAB-020`, `LAB-031`, `LAB-032` | NOT_RUN |
| TP-04 | P0 | NATIVE_HOP | `qa/suites/upgrade/quincy-x/stress-split` | Pin exact endpoints; giữ minority/majority/all MON, half-OSD, pause/resume, thrasher và workload archive; thêm rollback checkpoint | `LAB-010`, `LAB-011`, `LAB-021`, `LAB-023`, `LAB-024`, `LAB-053` | NOT_RUN |
| TP-05 | P0 | REUSABLE | `qa/tasks/dencoder.py`<br>`qa/workunits/dencoder/test-dencoder.sh`<br>`qa/workunits/dencoder/test_readable.py` | Sinh và checksum Quincy corpus, chạy Reef decoder với correct/missing/wrong library path; ghi type registry và expected incompatibility | `LAB-006` | NOT_RUN |
| TP-06 | P0 | HYBRID | `qa/suites/orch/cephadm/upgrade`<br>`qa/suites/orch/cephadm/orchestrator_cli`<br>`qa/suites/orch/cephadm/workunits`<br>`qa/suites/orch/cephadm/osds` | Ghép exact-hop control-state clone; kiểm pause/resume/failover, spec round-trip, agent/SSH, placement/device preview và service continuity | `LAB-003`, `LAB-012`, `LAB-013`, `LAB-014`, `LAB-015`, `LAB-018`, `LAB-019` | NOT_RUN |
| TP-07 | P0 | HYBRID | `qa/suites/upgrade/telemetry-upgrade/quincy-x`<br>`qa/suites/rados/mgr/tasks/4-units/prometheus.yaml`<br>`qa/suites/rados/dashboard` | Pin exact images, dùng telemetry sink giả; thêm ceph-exporter scrape, labels/cardinality, TLS/auth, alert và dashboard raw-query oracle | `LAB-016`, `LAB-017` | NOT_RUN |
| TP-08 | P0 | REUSABLE | `qa/suites/rados/monthrash`<br>`qa/suites/rados/mgr`<br>`qa/suites/rados/multimon` | Chạy command commit/election, MGR failover/module state và balancer/autoscaler assertions trong mixed cohort; giữ correlation IDs | `LAB-010`, `LAB-011`, `LAB-013`, `LAB-016`, `LAB-018` | NOT_RUN |
| TP-09 | P0 | REUSABLE | `qa/suites/rados/basic`<br>`qa/suites/rados/objectstore`<br>`qa/suites/rados/perf`<br>`qa/suites/rados/singleton` | Ghép restart/replay/recovery/scrub/watch/snapshot/allocator/device paths vào exact-hop OSD cohorts; threshold lấy từ As-Is, không từ suite default | `LAB-020`, `LAB-021`, `LAB-022`, `LAB-023`, `LAB-024`, `LAB-025`, `LAB-026`, `LAB-027` | NOT_RUN |
| TP-10 | P0 | HYBRID | `src/ceph-volume/ceph_volume/tests`<br>`src/ceph-volume/ceph_volume/tests/functional` | Unit tests chỉ làm guard; activation/dm-crypt/migrate/zap phải chạy thêm trên serial-allowlisted disposable disks và thử reboot/restore | `LAB-028`, `LAB-029` | NOT_RUN |
| TP-11 | P1 | REUSABLE | `qa/suites/crimson-rados/basic`<br>`qa/suites/crimson-rados/thrash`<br>`qa/suites/crimson-rados/rbd` | Chỉ chạy khi As-Is/roadmap applicable; pin backend/build flags, bật recovery/admin/metrics assertions và ghi các selector disabled | `LAB-030` | NOT_RUN |
| TP-12 | P0 | HYBRID | `qa/suites/rbd/librbd`<br>`qa/suites/rbd/cli`<br>`qa/suites/rbd/device`<br>`qa/suites/rbd/encryption`<br>`qa/suites/rbd/migration`<br>`qa/suites/rbd/mirror`<br>`qa/suites/rbd/pwl-cache` | Rebuild old-client/new-daemon và new-client/old-daemon lanes; thêm diff/restore oracle, cache crash, encryption, migration, mirror và mapping cohorts | `LAB-005`, `LAB-031`, `LAB-032`, `LAB-033`, `LAB-034`, `LAB-035` | NOT_RUN |
| TP-13 | P0 | HYBRID | `qa/suites/fs/mixed-clients`<br>`qa/suites/fs/functional`<br>`qa/suites/fs/fscrypt`<br>`qa/suites/fs/mirror`<br>`qa/suites/fs/nfs`<br>`qa/suites/fs/thrash` | Ghép MDS exact-hop ordering với kernel/FUSE matrix; giữ session/failover/journal/snapshot/fscrypt/schedule/mirror/repair evidence trên clone | `LAB-036`, `LAB-037`, `LAB-038`, `LAB-039`, `LAB-040`, `LAB-041` | NOT_RUN |
| TP-14 | P0 | HYBRID | `qa/suites/rgw/verify`<br>`qa/suites/rgw/lifecycle`<br>`qa/suites/rgw/singleton` | Chạy hai upgrade order, class/bucket/reshard, object/lifecycle/GC, auth/API/encryption/quota/admin; repair chỉ trên clone | `LAB-042`, `LAB-043`, `LAB-045`, `LAB-047`, `LAB-048`, `LAB-050` | NOT_RUN |
| TP-15 | P0 | HYBRID | `qa/suites/rgw/multisite`<br>`qa/suites/rgw/notifications` | Ghép zone-by-zone exact-hop ordering; thêm marker/lag/checksum oracle và HTTP/AMQP/Kafka collector có correlation/dedupe | `LAB-044`, `LAB-046` | NOT_RUN |
| TP-16 | P1 | HYBRID | `qa/suites/rgw/dbstore`<br>`qa/suites/fs/nfs` | DBStore/NFS có source suite nhưng RGW Lua không có ready QA selector trong target; viết fixture Lua/package/error-isolation riêng nếu applicable | `LAB-049` | NOT_RUN |
| TP-17 | P0 | CUSTOM | Không có recipe end-to-end đủ cho package downgrade và state-aware rollback | Dùng snapshot host/VM và exact repos để rehearsal package/container failback, control-state checkpoint và forward recovery; cấm production fixture | `LAB-051`, `LAB-053` | NOT_RUN |
| TP-18 | P0 | HYBRID | `qa/releases/reef.yaml` | Chỉ chạy trên clone sau full Reef inventory; thêm old-client/old-daemon negative lane và approval guard trước release/client floor | `LAB-052` | NOT_RUN |
| TP-19 | P0 | CUSTOM | Không có source suite thay thế evidence-board closure | Gom run IDs, raw outputs, digests, reruns, blocker/waiver, owner/expiry và quyết định; kiểm mọi P0 applicable trước sign-off | `LAB-054` | NOT_RUN |

## Thứ tự triển khai test pack

1. TP-01→02 khóa artifact và backend eligibility.
2. TP-03→08 chạy native hop và control-plane/telemetry trước data-plane destructive fixtures.
3. TP-09→11 chạy OSD/device/backend; TP-10 chỉ dùng disposable disks, TP-11 chỉ khi applicable.
4. TP-12→16 chạy client và stateful services theo As-Is applicability.
5. TP-17 rehearsal rollback trước canary; TP-18 chỉ sau full Reef và stable window; TP-19 đóng evidence cuối.

Không chạy toàn bộ target component suites một cách mù. Selector phải được thu hẹp theo As-Is, nhưng mọi gate P0 applicable vẫn cần result riêng; skip phải có reason/owner và không được biến thành PASS.
