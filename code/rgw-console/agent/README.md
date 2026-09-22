# Read-only Ceph host agent

This P1 agent exposes a closed inventory API over one Unix domain socket. It
does not accept a command, argv, pool, image, device, or path from the caller.
There is no TCP listener and there are no RBD mutation actions.

## Protocol

Each request and response is exactly one UTF-8 JSON line. The current protocol
version is `1`.

```json
{"version":1,"request_id":"4a5da3aa-03cb-4b39-a595-b93d0ac36d86","action":"health","params":{}}
```

Successful responses contain `ok: true` and `result`. Failures contain
`ok: false` and a stable `error.code`, safe message, and `retryable` flag. The
agent rejects duplicate JSON fields, non-canonical request UUIDs, unknown
fields, non-empty parameters, oversized lines, and every action outside this
allowlist:

- `health`
- `capabilities`
- `ceph.status`
- `ceph.fsid`
- `ceph.versions`
- `ceph.osd_df`
- `ceph.osd_tree`
- `ceph.pool_ls_detail`
- `ceph.crush_rule_dump`

Every request first runs `ceph fsid` and compares it with
`CEPH_EXPECTED_FSID`. A mismatch fails closed. Ceph commands use fixed argv
lists, `shell=False`, a minimal subprocess environment, a timeout, and an
output limit. Responses and command errors redact secret-like fields; neither
the keyring content nor raw command argv is returned.

## Install with systemd

The example assumes the repository (including the `agent` package) is deployed
at `/opt/rgw-console` and the host has Python 3.10+, `ceph`, and `rbd` installed.

```bash
sudo groupadd --system rgw-console 2>/dev/null || true
sudo install -d -o root -g root -m 0755 /opt/rgw-console
sudo install -d -o root -g root -m 0750 /etc/rgw-console
sudo install -o root -g root -m 0640 agent/systemd/agent.env.example /etc/rgw-console/agent.env
sudo install -o root -g root -m 0644 agent/systemd/rgw-console-agent.service /etc/systemd/system/rgw-console-agent.service
```

Edit `/etc/rgw-console/agent.env` and replace the zero FSID with the exact
output of `ceph fsid`. Do not copy a key into this environment file; point
`CEPH_KEYRING_PATH` at the existing root-readable keyring. Keep
`CEPH_AGENT_ALLOWED_UIDS` restricted to the backend's mapped host UID. The
socket directory is `0750`, the socket is `0660`, Linux `SO_PEERCRED` is
checked for every connection, and the systemd service starts with no ambient
or bounding capabilities in this read-only phase.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rgw-console-agent
sudo systemctl status rgw-console-agent
sudo journalctl -u rgw-console-agent --since today
```

Bind-mount `/run/rgw-console` into the backend container and set its
`CEPH_AGENT_SOCKET` to `/run/rgw-console/ceph-agent.sock`. Do not publish the
socket directory through a TCP proxy. If the backend later runs as a non-root
container user, map a stable host UID, add only that UID to
`CEPH_AGENT_ALLOWED_UIDS`, and ensure it can traverse the `rgw-console` group
directory.

The hardening in the supplied unit is deliberately appropriate to inventory
only. A later phase that adds map/format/mount must use a separately reviewed
capability and filesystem policy; it must not silently weaken this unit.

## Tests

The unit suite has no Ceph dependency and mocks subprocess/socket calls, so it
also runs on Windows:

```powershell
Set-Location code/rgw-console
python -m unittest discover -s agent/tests -v
```
