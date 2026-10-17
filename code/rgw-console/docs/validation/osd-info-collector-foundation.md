# OSD Info Collector foundation validation

Date: 2026-10-08 (Asia/Saigon)

## Implemented boundary

The console reuses `code/osd-info-collector/collect_osd.py` version `1.0.2` as
the canonical point-in-time snapshot producer. Browser input is limited to a
session, collection phase and numeric OSD IDs. The internal executor exposes
only `ceph.osd_info_collect`, builds fixed argv, independently enforces
`UPGRADE_ALLOWED_OSDS`, verifies the cluster FSID before dispatch and caps both
runtime and output.

The backend validates schema/kind/version/FSID, exact requested-versus-returned
OSD membership and quality. The full JSON is written once to the filesystem
evidence store and registered by ID/SHA-256. PostgreSQL indexes host/IP/device,
capacity, PG/primary count, up/in/weights and version while retaining each OSD's
raw evidence payload. Additive migration 0018 extends that projection with
CRUSH location, device class, full address lists, data/DB/WAL roles and
container image identity. Additive migration 0019 projects collection-level
health, epoch, flags, pool policy, version summary and cluster OSD/PG counts.

The `OSD inventory` screen consumes read-only session and collection-list
endpoints. It creates phase-labelled snapshots, retains the immutable history,
shows `UNKNOWN` separately from numeric zero, and opens redacted views of the
per-OSD payload and collection-level cluster evidence. The latter is read only
after URI containment, size, SHA-256 and collector protocol checks. Sensitive
field names, Ceph config rows and config/keyring argv values are redacted only
in the API response; the append-only source artifact is unchanged.
The browser has no command, collector-path, config-path, keyring or credential
input.

An operator can select a `CREATED` upgrade run and bind a fresh `BEFORE`
collection as its plan baseline. The backend—not the browser—checks identity,
config revision, complete/VALID quality, SHA-256, source/destination OSD coverage
and age. Readiness is recomputed whenever it is read, and preflight stores the
eligible binding ID on the placement plan. Missing or stale binding evidence
keeps execution readiness blocked.

## Automated evidence

- Backend: 202 discovered, 191 passed, 11 PostgreSQL-dependent skipped.
- Node executor: 17 passed.
- Standalone collector: 12 passed.
- Frontend: 6 passed and the production build completed.
- Targeted cases cover FSID mismatch, exact OSD set, all-allowlisted selection,
  out-of-scope rejection before collection, hashed artifact storage, missing
  device without invention, and missing core values remaining `null` with an
  `INCONCLUSIVE` result. Artifact read tests cover round-trip verification,
  path escape rejection, tamper detection and response redaction.
- Config comparison cases cover cluster config and per-OSD effective config,
  order-insensitive rows, missing evidence, and changed secret values that stay
  redacted in the response.
- Migration discovery is contiguous through
  `0019_osd_inventory_cluster_context.sql`.

## Not claimed

- No live SSH/Ceph collector execution was performed in this change.
- PostgreSQL migration/repository integration is not claimed without
  `TEST_DATABASE_URL`.
- A plan baseline, cross-phase diff and read-only pre-down-set inventory
  assessment now exist. None authorizes a live down-set; enforcement at an
  eventual fenced mutation boundary remains future work.
- No production upgrade action or result was added.
