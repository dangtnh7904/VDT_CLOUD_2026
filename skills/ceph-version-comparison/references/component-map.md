# Default Ceph component map

Use this map for the standard `00`–`15` upgrade comparison. A user-provided map takes precedence, but must retain one primary owner per changed-file row and the Markdown/CSV pairing contract.

## Report map

| Group | Owner report | Primary scope |
| --- | --- | --- |
| `01` | `01-osd-pg-recovery` | OSD, PG, peering, PGLog, recovery/backfill, scrub, replication, and erasure coding. |
| `02` | `02-bluestore-bluefs` | BlueStore/BlueFS data and metadata paths, replay, fsck, repair, and allocation. |
| `03` | `03-rocksdb-block-device` | KV/RocksDB integration, block devices, DB/WAL I/O, flush, and compaction. |
| `04` | `04-mon-osdmap-crush` | MON/quorum, OSDMap, CRUSH, placement, pool flags, and map compatibility. |
| `05` | `05-messaging-auth-common` | Messenger/messages, protocol, encoding, auth, caps, shared runtime, and feature bits. |
| `06` | `06-config-defaults` | Options, defaults, schema, limits, and activation conditions. |
| `07` | `07-mgr-modules-monitoring` | MGR core/modules, dashboard, metrics, alerts, autoscaling, balancing, and monitoring. |
| `08` | `08-cephadm-orchestrator` | cephadm/orchestrator upgrade logic, stop checks, daemon lifecycle, redeploy, and error handling. |
| `09` | `09-ceph-volume-activation` | ceph-volume, device inventory, LVM, activation, encryption, and DB/WAL migration. |
| `10` | `10-rados-rbd-clients` | librados, RADOS clients/classes, RBD, snapshot, fast-diff, object-map, mirror, and client tools. |
| `11` | `11-cephfs-mds` | MDS, CephFS client/libcephfs, sessions, caps, journal, volumes, NFS integration, and Manila conditions. |
| `12` | `12-rgw` | RGW, S3, auth/policy, bucket/object, multisite, and RGW tools/classes/tests. |
| `13` | `13-build-packaging-submodules` | CMake, build dependencies, gitlinks, packages, systemd, install scripts, and service permissions. |
| `14` | `14-security-cross-reference` | Direct security advisory/CVE material and verified cross-reference entries. |
| `15` | `15-upgrade-validation` | Cross-component QA, release notes, validation scenarios, source-claim reconciliation, and residual gaps. |

Group `00` is the master inventory itself and is not an owner for source rows.

## Ownership precedence

Apply rules from most specific to most general:

1. explicit exceptions established by inspected behavior;
2. dedicated service or module subtree;
3. component-specific tests, tools, classes, and documentation;
4. shared runtime tree whose behavior serves multiple components;
5. build/package/dependency ownership;
6. cross-component validation or release-note ownership.

Use the rename target path for ownership. Retain `old_path` only as diff metadata. Never infer ownership from an empty-marker rename alone.

Examples of rules that prevent keyword mistakes:

- A nested dashboard file belongs to `07` even if its text contains `rbd`, `rgw`, or `cephfs`.
- A suite under a clearly named `qa/suites/rbd`, `qa/suites/fs`, or RGW tree follows that component, not a generic QA catch-all.
- RBD mirror, fast-diff, object-map, snapshot, librados, class, and relevant tools belong to `10`.
- CephFS/MDS client, volumes, and NFS-related changes belong to `11` when their behavior is CephFS-owned.
- Packaging, CMake, systemd, and changed gitlinks belong to `13`, even when the dependency accelerates another component.
- Only direct, verified security material belongs to `14`; a security-relevant runtime fix stays with its component and is cross-referenced from `14`.
- `15` owns validation artifacts that are genuinely cross-component or not defensibly owned by one subsystem. Do not route all tests there.

If multiple rules still match, inspect imports, callers, build targets, suite composition, and commit context. Record a stable exception rather than relying on a transient keyword.

## Reading priority

Priority controls reading order, not final upgrade risk:

- `P0`: persistent data, mount/replay, crash/deadlock, quorum/availability, protocol/auth, cluster state, or compatibility-critical runtime.
- `P1`: runtime behavior, recovery performance, client paths, configuration/defaults, orchestration, activation, build/package, and dependencies.
- `P2`: tests, documentation, generated/data assets, mechanical changes, and ancillary tooling unless evidence elevates their operational impact.

Do not assign risk from path alone. A P2 test can be decisive evidence for a P0 finding; a large P1 generated file can have negligible runtime impact.

## Review mode

- `deep`: read hunk, symbols, history, and tests as a primary analysis candidate.
- `conditional`: analyze when the deployment uses the feature or when another finding depends on it.
- `support`: use as corroborating test, documentation, fixture, or integration evidence.
- `reference-only`: retain for inventory completeness without spending deep-analysis time unless new evidence changes the decision.

Review mode is triage, not automatic admission to Markdown. Even a `deep` row becomes only an aggregate trivial/support item if inspection finds no credible upgrade impact; a `support` or `reference-only` row can be cited when it proves a material finding. `analysis_decision` explains the initial task-specific reading choice, not the final verdict. Record the post-review verdict in the final disposition fields defined by `csv-schema.md`; do not alter base fields in only a component subset. Avoid generic text that says only “analyze this file.”
