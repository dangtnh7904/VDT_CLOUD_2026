# OSD inventory topology and daemon/device identity

## Scope

This read-only slice indexes fields already emitted by OSD Info Collector
1.0.2. It adds no Ceph command, executor action, credential input, or mutation
path.

Migration `0018_osd_inventory_topology_fields.sql` extends each immutable OSD
record with:

- CRUSH location and device class;
- all reported public and cluster addresses;
- BlueStore data, DB and WAL paths, physical devices, and reported sizes;
- device IDs from Ceph metadata;
- daemon status;
- short/full Ceph version and container image/digest.

The original per-OSD collector payload remains the source evidence. Indexed
values are projections for search, planning, display and phase comparison.

## Quality behavior

Missing CRUSH location or device class downgrades an otherwise `VALID` record
to `PARTIAL` and adds `CRUSH_LOCATION_NOT_REPORTED` or
`DEVICE_CLASS_NOT_REPORTED`. Optional DB/WAL devices remain `null`/empty when
the daemon does not use separate devices. No device path, address, topology, or
image digest is inferred.

Before/after comparison includes every new indexed field. Address, physical
device, and device-ID lists are order-insensitive; `null` remains distinct from
zero and from an empty string.

## UI

The OSD table now separates topology, network, BlueStore roles, capacity,
placement/state, and version/image. The detail drawer shows the indexed values
alongside the preserved collector payload, including effective configuration
and command evidence.

## Validation — 2026-10-09

- focused topology/domain/repository/comparison/migration tests: `15 passed`;
- complete backend suite: `191 tests`, `180 passed`, `11 skipped` because
  PostgreSQL-only tests require `TEST_DATABASE_URL`;
- standalone OSD Info Collector: `12 passed`;
- frontend contract suite: `5 passed`;
- frontend production build: succeeded.

The repository-shape test verifies that the PostgreSQL record insert has one
value for every SQL placeholder. Migration discovery reaches version 18, but
actual PostgreSQL application remains unverified without `TEST_DATABASE_URL`.
No live Ceph collection was executed in this validation run.
