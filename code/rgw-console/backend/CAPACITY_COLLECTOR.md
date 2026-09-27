# Read-only capacity collector

The collector calls the authenticated internal Node SSH executor and stores
per-OSD evidence in `capacity_snapshots` and `capacity_osds`. FastAPI and the
collector never accept an arbitrary shell command and never hold the SSH key.
The preferred `ceph.capacity_inventory` action captures the following bounded,
FSID-bound inventory in one request:

- `ceph status` before and after the sample
- `ceph osd df`
- `ceph osd tree`
- `ceph osd pool ls detail`
- `ceph osd crush rule dump`

Set `CEPH_EXPECTED_FSID`, `RBD_EXECUTOR_TOKEN`, the `RBD_SSH_*` settings,
`RGW_AFFECTED_POOLS`, and `RBD_ALLOWED_POOLS`. The executor does not discover
or add pools outside those allowlists. Keep `CAPACITY_OBSERVE_ONLY=true` until
the inventory has been compared with the Pacific CLI and every affected pool
resolves to a complete replicated CRUSH scope.

Run the internal executor and both Ceph workers with one Compose profile:

```bash
docker compose --profile ceph-ssh up --build -d
docker compose --profile ceph-ssh ps
```

The executor has no published host port. Its only execution endpoint is
`POST /internal/v1/execute` on the Compose network and requires the shared
token. Public diagnostics remain on FastAPI at `/api/rbd/ssh/health` and
`/api/rbd/ssh/capabilities`.

To run one collector cycle from a configured backend environment:

```bash
python -m app.capacity_collector --once
```

Malformed counters, an FSID mismatch, changing OSDMap epochs, stale/future
executor timestamps, incomplete pool scope, and executor failures never become
a zero-percent sample. Where possible the collector persists a failed sample so
the API can distinguish `EXECUTOR_UNAVAILABLE` from `COLLECTOR_ERROR`; otherwise
the last good sample becomes `STALE`.

Successful transient reservations remain `SETTLING` until the configured
minimum window has elapsed and the required consecutive samples are fresh,
current, same-FSID/same-epoch, healthy, and cover every reservation allocation.
`LEASE_EXPIRED_UNRECONCILED` and persistent volume commitments are never
released by this collector.
