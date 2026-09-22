# Read-only capacity collector

The collector polls the Unix-socket host agent and stores per-OSD evidence in
`capacity_snapshots` and `capacity_osds`. It never runs Ceph CLI itself and only
uses these agent actions:

- `ceph.status` (before and after each sample)
- `ceph.osd_df`
- `ceph.osd_tree`
- `ceph.pool_ls_detail`
- `ceph.crush_rule_dump`

Set `CEPH_EXPECTED_FSID`, `CEPH_AGENT_SOCKET`, `RGW_AFFECTED_POOLS`, and/or
`RBD_ALLOWED_POOLS`. Keep `CAPACITY_OBSERVE_ONLY=true` until the output has been
compared with the Pacific CLI on the lab cluster and all affected pools resolve
to complete replicated CRUSH scopes.

Run one sample:

```bash
python -m app.capacity_collector --once
```

Run continuously using `CAPACITY_COLLECTOR_INTERVAL_SECONDS`:

```bash
python -m app.capacity_collector
```

The optional Compose service is behind a profile so a workstation without the
agent socket still starts normally:

```bash
CEPH_AGENT_SOCKET_DIR=/run/rgw-console \
  docker compose --profile ceph-collector up capacity-collector
```

Malformed counters, changing OSDMap epochs, stale/future agent timestamps, and
agent failures never become a zero-percent sample. If cluster identity and epoch
are still trustworthy, the collector writes an explicit `fresh=false` snapshot;
otherwise the previous snapshot naturally becomes stale and admission fails
closed.

Successful transient reservations remain `SETTLING` until the configured minimum
window has elapsed and the configured number of consecutive samples are fresh,
current, same-FSID/same-epoch, healthy, and cover every reservation allocation.
`LEASE_EXPIRED_UNRECONCILED` and persistent volume commitments are never released
by this collector.
