# Validation status

Last updated: 2026-09-23 (Asia/Saigon).

This report separates code/test evidence from live Ceph evidence. `PASS` is
used only for checks executed in this workspace; unavailable lab checks remain
`NOT_RUN`.

| Area | Status | Evidence |
|---|---|---|
| PostgreSQL migration | PASS | Host database `rgw_console` migrated through version `0006`; rerun reported no pending migration and current-schema check passed. |
| Backend unit/integration suite | PASS | 64 tests passed against host PostgreSQL, including fresh/legacy migration, collector persistence, concurrent capacity admission, performance rate/reset/rollup semantics, strict RBD-format health gating, and per-step RBD fence allocation. |
| Host-agent unit suite | PASS | 13 tests passed, including bounded subprocess output/timeout, closed RBD parameter schemas, response binding, and replay/fence behavior. |
| Frontend production build | PASS | Vite production build completed successfully with the Performance view. |
| Compose rendering | PASS | Default and `ceph-collector` + `ceph-rbd` profile service graphs, including `performance-collector`, rendered successfully. |
| Default Docker deployment | PASS | Images rebuilt; migration exited successfully; backend, frontend, worker and performance collector are running. `/api/health` reports schema `6`. |
| Application performance telemetry | PASS | Collector wrote 15-second application samples; current/history/SSE returned through FastAPI and the Vite proxy; 1-minute rollup, retention, stale history, reset and unsupported-source behavior are covered by tests. |
| Live Ceph performance telemetry | PASS | FSID `17c77e12-a16a-11f1-838e-cf68e9c001d8` was cross-checked with saved inventory; active exporter `10.20.20.12:9283/metrics` exposed the required Pacific counters. Collector stored one cluster plus five OSD scopes; cluster and `osd.0` current APIs returned `FRESH` after warm-up. |
| Performance visual browser QA | NOT_RUN | Production build and live HTTP/proxy smoke passed, but no controllable browser surface was available to the computer-use runtime for screenshot-based visual QA. |
| Live RGW exact-object smoke | PASS | Created one isolated 1 KiB object under `console-jobs/smoke/`, replayed the same idempotency key, verified HEAD and SHA-256 GET, hard-deleted it, then confirmed zero objects remained in the smoke prefix. |
| RGW endpoint/bucket scope | PASS | Configured endpoint answered health/bucket/list/versioning probes; only the allowlisted lab bucket was exposed. |
| Live Ceph inventory / affected-pool-to-OSD mapping | NOT_RUN | `CEPH_EXPECTED_FSID`, affected pools, and Linux host-agent socket are not provisioned on this Windows workstation. |
| Live RBD create/map/ext4/mount/delete | NOT_RUN | Requires a Linux Ceph client host, reviewed pool/namespace allowlists, kernel RBD, host-agent systemd service, and calibrated capacity policy. The API/UI currently fail closed. |
| Capacity enforcement | NOT_RUN | Configuration remains `CAPACITY_OBSERVE_ONLY=true`; metadata budget and per-OSD safety calibration are intentionally unset. |
| Versioned/suspended RGW cleanup matrix | NOT_RUN | The connected smoke bucket reports versioning disabled. |
| Upgrade/recovery/backfill and external-writer fault matrix | NOT_RUN | Requires the dedicated Ceph lab and an approved fault-test window. |

## Known limitations

- Manual RBD lifecycle is implemented; RBD file browsing and RBD lifecycle
  streaming remain outside the currently delivered slice.
- Performance cluster cards use verified Ceph client counters. The application
  source remains separate and must not be relabeled as cluster or physical-device
  IOPS. The configured exporter URL names the current active mgr; an mgr failover
  requires updating the URL unless a stable proxy/service address is added.
- The host-agent uses the lab CephX identity configured by the operator. Moving
  from `client.admin` to least-privilege caps is a separate productionization
  task.
- A capacity reservation is credited back only after telemetry settlement;
  successful delete responses do not claim immediate physical reclamation.
- Do not switch capacity enforcement on based only on unit tests. First collect
  fresh stable samples for every affected replicated pool and validate the
  participating OSD set against Ceph Pacific CLI output.
