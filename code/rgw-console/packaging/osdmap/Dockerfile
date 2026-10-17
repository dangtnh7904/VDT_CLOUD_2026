# This image is only an offline placement simulator, not a Ceph daemon.
FROM quay.io/ceph/ceph:v16.2.15@sha256:f15b41add2c01a65229b0db515d2dd57925636ea39678ccc682a49e2e9713d98
ARG APP_VERSION=16.2.15-rc.1
ARG BUILD_DATE=unknown
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Storage Lab Console offline OSDMap worker" \
      org.opencontainers.image.description="Optional lab-only Pacific placement predictor; legacy base has known CVEs; network isolation required" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      storage-lab-console.security-status="legacy-base-known-vulnerabilities-not-production-approved" \
      storage-lab-console.supported-platform="linux/amd64"
COPY worker.py /opt/osdmap-preview/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OSDMAP_PREVIEW_SPOOL=/spool
USER 10001:10001
ENTRYPOINT ["/usr/bin/python3", "/opt/osdmap-preview/worker.py"]
