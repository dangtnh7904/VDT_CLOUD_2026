# OSD inventory cluster planning context

Date: 2026-10-09 (Asia/Saigon)

## Implemented boundary

Migration `0019_osd_inventory_cluster_context.sql` adds a collection-level,
read-only projection for evidence already emitted by OSD Info Collector:

- health status and structured health checks;
- OSDMap epoch and cluster flags;
- cluster PG count and OSD total/up/in counts;
- pool ID/name/type, size/min_size, PG/PGP count, CRUSH rule and EC profile;
- daemon-version summary.

Normalization accepts only successful command envelopes. Missing, failed or
unsupported evidence stays `null`, `{}` or `[]` as appropriate. It is never
converted to zero. A real epoch or PG count of zero remains zero. Pool paths,
types and rules are reported from evidence and are not synthesized.

The collection journal shows health and epoch. The selected snapshot exposes a
cluster-context strip and pool-policy table above the existing plan binding and
down-set assessment. These values are point-in-time observations; the UI does
not translate `HEALTH_OK` into a production gate or mutation permit.

## Automated evidence

- Focused normalization, SQL-shape and migration-contract run: 9 passed and 3
  PostgreSQL-only tests skipped.
- Full backend run: 202 discovered, 191 passed, 11 PostgreSQL-only skipped.
- Frontend contract run: 6 tests passed.
- Frontend production build completed with the existing bundle-size advisory.
- Migration discovery reaches contiguous schema version 19.

## Not claimed

- Migration 0019 was not applied to PostgreSQL because `TEST_DATABASE_URL` was
  unavailable.
- No live Ceph health, pool policy, epoch or daemon-version snapshot was
  collected in this slice.
- Cluster context is evidence for later gates, not a replacement for live PG,
  health, lease, fencing or replica validation at a mutation boundary.
