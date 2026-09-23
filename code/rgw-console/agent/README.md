# Fenced Ceph/RBD host agent

The agent exposes a closed Ceph inventory and manual RBD lifecycle API over one
Unix domain socket. It never accepts arbitrary commands, argv, device paths,
mount paths, or image names outside configured allowlists. There is no TCP
listener. Every mutation binds a managed volume UUID, stable action UUID,
monotonic fence token, immutable image ID, and (after map) device major/minor.

## Protocol

Each request and response is exactly one UTF-8 JSON line. The current protocol
version is `1`.

```json
{"version":1,"request_id":"4a5da3aa-03cb-4b39-a595-b93d0ac36d86","action":"health","params":{}}
```

Successful responses contain `ok: true` and `result`. Failures contain
`ok: false` and a stable `error.code`, safe message, and `retryable` flag. The
agent rejects duplicate JSON fields, non-canonical request UUIDs, unknown
fields, oversized lines, and every action outside this allowlist:

- `health`
- `capabilities`
- `ceph.status`
- `ceph.fsid`
- `ceph.versions`
- `ceph.osd_df`
- `ceph.osd_tree`
- `ceph.pool_ls_detail`
- `ceph.crush_rule_dump`
- `rbd.pool.list`
- `rbd.image.list`
- `rbd.image.info`
- `rbd.device.list`
- `rbd.image.create`
- `rbd.image.map`
- `rbd.device.format_ext4`
- `rbd.device.mount`
- `rbd.device.unmount`
- `rbd.device.unmap`
- `rbd.image.remove`

Every request first runs `ceph fsid` and compares it with
`CEPH_EXPECTED_FSID`. A mismatch fails closed. Ceph commands use fixed argv
lists, `shell=False`, a minimal subprocess environment, a timeout, and an
output limit. Responses and command errors redact secret-like fields; neither
the keyring content nor raw command argv is returned.

The agent keeps an fsync'd per-volume registry under
`CEPH_RBD_STATE_ROOT`. Format is restricted to a newly created, never-formatted
managed image. Before `mkfs.ext4 -m 0`, it verifies the image ID, device
major/minor, sysfs identity, absence of mounts/holders, and absence of an
existing signature. Mountpoints are derived only from the volume UUID beneath
`CEPH_RBD_MOUNT_ROOT`; force remove, lazy unmount, snapshot purge, and a file
browser are not exposed.

## Install with systemd

The example assumes the repository (including the `agent` package) is deployed
at `/opt/rgw-console` and the host has Python 3.10+, `ceph`, and `rbd` installed.

```bash
sudo groupadd --system rgw-console 2>/dev/null || true
sudo install -d -o root -g root -m 0755 /opt/rgw-console
sudo install -d -o root -g root -m 0750 /etc/rgw-console
sudo install -d -o root -g rgw-console -m 0750 /run/rgw-console
sudo install -d -o root -g root -m 0700 /var/lib/rgw-console-agent
sudo install -d -o root -g root -m 0750 /srv/ceph-lab/rbd
sudo install -o root -g root -m 0640 agent/systemd/agent.env.example /etc/rgw-console/agent.env
sudo install -o root -g root -m 0644 agent/systemd/rgw-console-agent.service /etc/systemd/system/rgw-console-agent.service
```

Edit `/etc/rgw-console/agent.env` and replace the zero FSID with the exact
output of `ceph fsid`. Do not copy a key into this environment file; point
`CEPH_KEYRING_PATH` at the existing root-readable keyring. Keep
`CEPH_AGENT_ALLOWED_UIDS` restricted to the backend's mapped host UID. Make
the agent-side RBD pool and image-prefix allowlists match the backend
allowlists exactly. For the default namespace use `default` in backend
`RBD_ALLOWED_NAMESPACES` and `@default` in agent
`CEPH_RBD_ALLOWED_NAMESPACES`. The
socket directory is `0750`, the socket is `0660`, Linux `SO_PEERCRED` is
checked for every connection, and the systemd service starts with no ambient
network listener. Its capability bounding set contains only `CAP_SYS_ADMIN`,
which is required for kernel RBD map/mount; load the `rbd` kernel module before
starting the unit if the host does not load it automatically.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rgw-console-agent
sudo systemctl status rgw-console-agent
sudo journalctl -u rgw-console-agent --since today
```

Bind-mount `/run/rgw-console` into the backend and RBD lifecycle worker
containers and set
`CEPH_AGENT_SOCKET` to `/run/rgw-console/ceph-agent.sock`. Do not publish the
socket directory through a TCP proxy. If the backend later runs as a non-root
container user, map a stable host UID, add only that UID to
`CEPH_AGENT_ALLOWED_UIDS`, and ensure it can traverse the `rgw-console` group
directory. The capacity collector uses the same socket but calls only the
read-only Ceph inventory actions.

## Tests

The unit suite has no Ceph dependency and mocks subprocess/socket calls, so it
also runs on Windows:

```powershell
Set-Location code/rgw-console
python -m unittest discover -s agent/tests -v
```
