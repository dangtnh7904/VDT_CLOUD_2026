# Runtime secret inventory

Create these files outside source control before starting the release stack. The
Compose file mounts each file only into the roles that need it. Files must be
readable by container UID/GID `10001:10001` without making them world-readable.

| File | Content | Consumer |
|---|---|---|
| `database_url` | One PostgreSQL URL, including required TLS parameters | migration, API and DB-backed workers |
| `executor_token` | One random token of at least 32 characters | API/executor clients and executor |
| `ssh_private_key` | Restricted key for the approved Ceph management host | executor only |
| `ssh_known_hosts` | Pinned host-key entry for the approved SSH target | executor only |
| `postgres_password` | Password for the optional bundled PostgreSQL role | PostgreSQL only |

For an external database, `database_url` should name that endpoint. For the
`bundled-db` profile it should name service `postgres`, and its password must
match `postgres_password`. Never put credentials in `.env.release`, the cluster
profile, image layers, evidence, or the release archive.

The executor fails closed when the mounted known-hosts file is missing, has no
plain entry for the configured host, or presents a different key. Unit coverage
does not validate the lab key itself: verify that key through an independent
trusted channel and keep `UPGRADE_MUTATIONS_ENABLED=false` until the target
environment acceptance passes.
