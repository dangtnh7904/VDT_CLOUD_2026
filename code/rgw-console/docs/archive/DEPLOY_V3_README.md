# Lưu trữ lịch sử — deployment v3

Tài liệu tiếng Anh bên dưới là bản trước RC v5, không phải hợp đồng triển khai hiện tại. Các đường dẫn tương đối giữ nguyên theo vị trí README gốc `deploy/README.md`. Xem [README deployment hiện tại](../../deploy/README.md).

# Storage Lab Console release deployment

This directory is the image-only deployment contract. It does not build from a
source checkout. Every application role uses the exact value of
`STORAGE_LAB_CONSOLE_IMAGE`; PostgreSQL is an external dependency or a separately
pinned image under the optional `bundled-db` profile.

The published lab candidate is
[`dang7904/storage-lab-console:3.0.0-rc.1`](https://hub.docker.com/r/dang7904/storage-lab-console).
Use [`releases/3.0.0-rc.1.yaml`](releases/3.0.0-rc.1.yaml) for its registry
digests and security/acceptance status, and
[`code/README.md`, section 7](../../README.md#7-cài-và-sử-dụng-image-docker-hub)
for the Vietnamese setup guide. This candidate has open security findings;
production acceptance remains incomplete.

## Files and persistent data

- `compose.release.yml` runs migration, API and optional role profiles.
- `.env.release.example` contains non-secret runtime settings and image refs.
- `config/profiles/lab.yaml.example` is the non-secret cluster/profile snapshot.
- `secrets/README.md` lists secret files that must be provisioned out of band.
- `release-manifest.example.yaml` records immutable digests, compatibility and
  acceptance outcomes. It is a template, not proof of a published release.
- `export-offline-bundle.ps1` exports already-built local images plus this
  deployment contract, an SPDX SBOM, metadata and checksums. It refuses to
  overwrite an existing output directory and never treats a missing
  vulnerability report as release-ready.
- Named volumes `postgres-data`, `evidence` and `executor-state` survive normal
  container replacement. Do not use `down --volumes` during an upgrade.

## Prepare a deployment

1. Verify the supplied image archive, SBOM, scan report and release manifest by
   the receiving site's trust policy. For offline installation, load the
   application image and any selected dependency images, then verify that their
   local content/repository digests match the manifest. Do not allow a rebuild.
2. Copy `.env.release.example` to `.env.release`; replace every applicable
   placeholder, choose a deployment-specific `COMPOSE_PROJECT_NAME`, and use
   the immutable application digest. Use `RELEASE_PULL_POLICY=never` for
   offline operation.
3. Copy `config/profiles/lab.yaml.example` to `config/profiles/lab.yaml`. Resolve
   FSID, hosts, OSDs, pools and device classes from approved inventory. Values in
   the profile and `.env.release` must agree.
4. Provision the secret files listed in `secrets/README.md` through an approved
   secret workflow. Do not place secret values on a command line or in shell
   history.
5. Validate the rendered model before starting anything:

   ```sh
   docker compose --env-file .env.release -f compose.release.yml config --quiet
   docker compose --env-file .env.release -f compose.release.yml config --images
   ```

   The second command must show the same application image reference for every
   application role. The only other image may be the separately pinned
   PostgreSQL dependency.

To create a candidate transfer bundle after the application and optional
PostgreSQL images are already present locally:

```powershell
.\export-offline-bundle.ps1 `
  -ApplicationImage storage-lab-console:3.0.0-dev `
  -DependencyImages postgres:16-alpine `
  -OutputDirectory .\dist\storage-lab-console-3.0.0-dev
```

Pass the approved scanner output through `-VulnerabilityReportPath` for a real
release candidate. An export without it remains a local candidate even though
`SHA256SUMS`, the image archive and SBOM are complete.

## Start and verify

For a supported external PostgreSQL endpoint, run migration and the core API:

```sh
docker compose --env-file .env.release -f compose.release.yml up -d migrate api
docker compose --env-file .env.release -f compose.release.yml ps
```

For the bundled database, first include its profile. The connection URL secret
must use host `postgres` and the same password as the PostgreSQL secret:

```sh
docker compose --env-file .env.release -f compose.release.yml --profile bundled-db up -d postgres migrate api
```

Enable only the role groups required by the configured features:

```sh
# Internal executor plus capacity/lifecycle workers.
docker compose --env-file .env.release -f compose.release.yml --profile ceph-ssh up -d

# Performance aggregation.
docker compose --env-file .env.release -f compose.release.yml --profile collectors up -d

# Legacy application jobs; requires separately provisioned RGW/corpus settings.
docker compose --env-file .env.release -f compose.release.yml --profile legacy-workers up -d
```

When `FEATURE_UPGRADE=true`, start the `ceph-ssh` profile and require readiness,
executor identity/FSID checks, remote collector version/hash and fresh inventory
before any workflow. Keep `UPGRADE_MUTATIONS_ENABLED=false` unless the release
manifest and environment-specific live acceptance explicitly permit otherwise.

The API is published on loopback by default. Put a trusted management ingress
with TLS and authentication in front of it before changing the bind address.
Executor and PostgreSQL have no published host ports.

## Upgrade, backup and recovery boundaries

Before replacing an application digest, pause new work, reconcile in-flight
leases, and back up PostgreSQL plus evidence at a consistent checkpoint. Run the
one-shot migration with the new image, then recreate roles and verify readiness,
schema version, evidence hashes and executor fencing state. An older application
image is safe only when its manifest supports the current DB schema; Compose does
not perform down-migration or replay old actions.

Back up `executor-state` with the deployment state even though it is not a
business-data store: deleting it can remove fencing/idempotency information.
Evidence write failures must remain visible and block operations that require an
audit trail.

## Acceptance status

The example manifest intentionally records every environment test as `NOT_RUN`.
A release is portable only after the same application digest is exercised on two
differently configured environments without a source checkout or rebuild, and
after persistence/recreate, fresh/upgrade migration, backup/restore and offline
no-pull behavior are recorded. Unit tests or a successfully rendered Compose file
do not replace that acceptance evidence.
