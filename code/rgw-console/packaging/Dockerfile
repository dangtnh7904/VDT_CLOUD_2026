# syntax=docker/dockerfile:1.7

ARG FRONTEND_NODE_IMAGE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
ARG NODE_IMAGE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
ARG PYTHON_IMAGE=python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4

FROM ${FRONTEND_NODE_IMAGE} AS frontend-build
WORKDIR /build/frontend
COPY rgw-console/frontend/package.json rgw-console/frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY rgw-console/frontend/index.html rgw-console/frontend/tsconfig.json rgw-console/frontend/vite.config.ts ./
COPY rgw-console/frontend/src ./src
RUN npm run build

FROM ${NODE_IMAGE} AS executor-deps
WORKDIR /build/executor
COPY rgw-console/rbd-console/package.json rgw-console/rbd-console/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --ignore-scripts \
    && rm -rf /build/executor/node_modules/ssh2/test \
    && npm cache clean --force

FROM ${PYTHON_IMAGE} AS python-deps
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv --without-pip "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
COPY rgw-console/backend/requirements.txt /tmp/requirements.txt
COPY rgw-console/backend/requirements.lock /tmp/requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    /usr/local/bin/python -m pip --python /opt/venv install --disable-pip-version-check --requirement /tmp/requirements.txt

FROM ${NODE_IMAGE} AS node-runtime

FROM ${PYTHON_IMAGE} AS runtime

# Alpine's patched zlib removes the remaining high finding in the pinned base.
RUN apk add --no-cache 'zlib=1.3.2-r1'
# Package installation belongs to the build stage, not the deployed runtime.
RUN /usr/local/bin/python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.12/ensurepip

ARG APP_VERSION=0.0.0-dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG APP_UID=10001
ARG APP_GID=10001

LABEL org.opencontainers.image.title="Storage Lab Console" \
      org.opencontainers.image.description="Unified multi-role Storage Lab Console application image" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="code/rgw-console"

ENV APP_VERSION="${APP_VERSION}" \
    CONSOLE_READ_ONLY="true" \
    UPGRADE_MUTATIONS_ENABLED="false" \
    FEATURE_LEGACY_RGW="false" \
    FEATURE_LEGACY_RBD="false" \
    FEATURE_LAB="false" \
    LAB_ALLOW_WRITE="false" \
    RBD_TERMINAL_ENABLED="false" \
    CAPACITY_OBSERVE_ONLY="true" \
    APP_REVISION="${VCS_REF}" \
    APP_BUILD_DATE="${BUILD_DATE}" \
    APP_CONFIG_SCHEMA_VERSION="1" \
    FRONTEND_DIST_PATH="/opt/storage-lab-console/frontend" \
    OSD_INFO_COLLECTOR_BUNDLE_PATH="/opt/storage-lab-console/collector/collect_osd.py" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    VIRTUAL_ENV="/opt/venv" \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}" \
    PYTHONPATH="/opt/storage-lab-console/backend:/opt/storage-lab-console/bin" \
    NODE_ENV="production"

COPY --from=python-deps /opt/venv /opt/venv
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/lib/libstdc++.so.6* /usr/lib/
COPY --from=node-runtime /usr/lib/libgcc_s.so.1 /usr/lib/
COPY --from=frontend-build /build/frontend/dist /opt/storage-lab-console/frontend
COPY --from=executor-deps /build/executor/node_modules /opt/storage-lab-console/executor/node_modules

COPY rgw-console/backend/app /opt/storage-lab-console/backend/app
COPY rgw-console/rbd-console/src /opt/storage-lab-console/executor/src
COPY osd-info-collector/collect_osd.py /opt/storage-lab-console/collector/collect_osd.py
COPY rgw-console/packaging/entrypoint.sh /opt/storage-lab-console/bin/entrypoint.sh
COPY rgw-console/packaging/version_info.py /opt/storage-lab-console/bin/version_info.py

RUN addgroup -g "${APP_GID}" storage-lab \
    && adduser -D -H -u "${APP_UID}" -G storage-lab -h /nonexistent -s /sbin/nologin storage-lab \
    && mkdir -p /etc/storage-lab-console /var/lib/storage-lab-console/evidence /var/lib/rbd-executor /tmp/storage-lab-console \
    && sha256sum /opt/storage-lab-console/collector/collect_osd.py > /opt/storage-lab-console/collector/SHA256SUMS \
    && chmod 0555 /opt/storage-lab-console/bin/entrypoint.sh \
    && chmod 0444 /opt/storage-lab-console/collector/SHA256SUMS \
    && chown -R "${APP_UID}:${APP_GID}" /var/lib/storage-lab-console /var/lib/rbd-executor /tmp/storage-lab-console

WORKDIR /opt/storage-lab-console/backend
USER ${APP_UID}:${APP_GID}

EXPOSE 8000 3001

ENTRYPOINT ["/opt/storage-lab-console/bin/entrypoint.sh"]
CMD ["api"]

