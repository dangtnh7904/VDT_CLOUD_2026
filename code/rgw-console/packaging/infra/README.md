# Infrastructure image candidates

Build from the `code/` directory:

```sh
docker build -f rgw-console/packaging/infra/Dockerfile.nginx -t slc-infra-nginx:1.30.5-rc.1 .
docker build -f rgw-console/packaging/infra/Dockerfile.postgres -t slc-infra-postgres:16.15-rc.1 .
docker scout cves --only-severity critical,high slc-infra-nginx:1.30.5-rc.1
docker scout cves --only-severity critical,high slc-infra-postgres:16.15-rc.1
```

Both Dockerfiles start from digest-pinned Docker Official Images and retain
their package database. They apply available Alpine security updates. Nginx
keeps its core TLS, reverse-proxy and basic-auth support, while removing unused
ACME, GeoIP, image-filter, JavaScript and XSLT modules and their dependencies.
The production Compose configuration runs nginx as UID/GID `101:101` with a
read-only filesystem and a writable `/tmp`.

PostgreSQL stays on version 16 with the same data directory and official
initialization scripts, including `POSTGRES_PASSWORD_FILE` and init hooks. Only
the privilege-drop command changes from the old Go-based `gosu` binary to the
native Alpine `su-exec` executable. Passwords are supplied at deployment time;
the image contains no default password. Do not switch an existing PostgreSQL
volume between Alpine and Debian builds without checking locale/collation
compatibility and taking a tested backup.

## Security gate

Scan reports are local build evidence, not permanent certification. Re-scan the
exact image digest before each deployment. The nginx candidate was tested on
2026-10-12 with zero Critical/High findings and the actual production TLS config
passed `nginx -t` under the non-root, read-only runtime settings.

The optional bundled Alpine PostgreSQL image remains a test candidate until its
security gate passes. Its exact candidate scan on 2026-10-12 found zero Critical
and one High vulnerability across 63 packages. Its linked `libxml2` package has an unpatched High finding,
`CVE-2026-86140`; deleting that library would break PostgreSQL XML support and
server startup. As checked on 2026-10-12, stable Debian alternatives are affected
too; [Debian's primary tracker](https://security-tracker.debian.org/tracker/CVE-2026-86140)
identifies libxml2 2.15.4 as fixed. Use an independently patched, vendor-managed
PostgreSQL 16 service for production until an audited patched package is
available. Keep the residual finding in the release manifest; do not ignore the
package or change its metadata to make a scanner pass.

The PostgreSQL candidate passed fresh initialization with `POSTGRES_PASSWORD_FILE`,
missing-password rejection, privilege drop to the `postgres` account, volume
persistence after container recreation, and an XML query. The patched runtime
filesystem is copied into a fresh layer to remove the obsolete Go binary's
bytes from the distributed artifact; its complete package database remains
available to scanners. This preserves PostgreSQL behavior but does not waive the
remaining libxml2 finding.

