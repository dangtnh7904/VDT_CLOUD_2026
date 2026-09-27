# Validation status

Last updated: 2026-09-24 (Asia/Saigon).

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
