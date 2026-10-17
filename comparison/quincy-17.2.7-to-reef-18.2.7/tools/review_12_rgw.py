#!/usr/bin/env python3
"""Apply reviewed binary verdicts for owner 12 RGW rows."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "12-rgw.csv"


def affect(ids: str, reason: str) -> tuple[str, str, str]:
    return "affect", ids, reason


def trivial(reason: str) -> tuple[str, str, str]:
    return "trivial", "", reason


def has_any(path: str, tokens: tuple[str, ...]) -> bool:
    return any(token in path for token in tokens)


def verdict(row: dict[str, str]) -> tuple[str, str, str]:
    path = row["path"]

    # The target contains a purpose-built RGW rolling-upgrade graph. Only the
    # Quincy source selector and shared setup/sequences apply to this hop.
    if path.startswith("qa/suites/rgw/upgrade/"):
        if "/1-install/pacific/" in path:
            return trivial(
                "RGW-VAL-OTHER: Pacific source selector belongs to a different RGW hop and is not selected for v17.2.7 to v18.2.7."
            )
        return affect(
            "RGWVAL-001",
            "Changes the RGW Quincy-to-Reef rolling-upgrade graph, source selector, shared setup, OSD/RGW restart order, or ragweed prepare/check acceptance path; suite source is not an executed exact-tag result.",
        )

    if path.startswith("doc/"):
        return trivial(
            "RGW-DOC: documentation/manpage source only; it supports interpretation but is not runtime code or an executed upgrade result."
        )
    if path.startswith("qa/"):
        return trivial(
            "RGW-QA: functional, multisite, notification, crypto, DBStore, service-token, workload, or harness source outside the selected exact-hop graph; it was not executed and does not itself change production rollout behavior."
        )
    if path.startswith("src/test/") or "/tests/" in path:
        return trivial(
            "RGW-TEST: unit/integration/benchmark source only; useful supporting coverage, but no exact-hop execution result is present."
        )
    if path.endswith("README.md") or path.endswith("README.rst"):
        return trivial(
            "RGW-README: backend/test documentation only; it does not activate a driver or mutate gateway state."
        )

    # Several rows are exact-content moves into driver/rados. The build owner
    # covers source-list delivery; the 0/0 hunk itself has no runtime semantic.
    if row["status"] == "R" and row["additions"] == "0" and row["deletions"] == "0":
        return trivial(
            "RGW-MOVE: Git reports an exact-content rename with no endpoint hunk; source-path delivery is covered by owner 13 and this row adds no independent runtime behavior."
        )

    # New alternative drivers/frontends are not selected by the default RADOS
    # RGW path. They remain conditional delivery choices rather than upgrade
    # effects for an existing deployment that has not opted in.
    if (
        path.startswith("src/rgw/driver/daos/")
        or path.startswith("src/rgw/rgw_sal_daos")
        or path.startswith("src/rgw/rgw_sal_motr")
        or path.startswith("src/rgw/rgw_flight")
    ):
        return trivial(
            "RGW-OPTIN: target-only DAOS/Motr/Arrow-Flight implementation is not automatically selected for an existing RADOS RGW; activation/build delivery is conditional and covered separately."
        )

    if path.startswith("src/rgw/store/dbstore/"):
        return trivial(
            "RGW-DBDOC: removal of the old DBStore README path accompanies the driver move and has no independent runtime effect."
        )
    if path.startswith("src/rgw/driver/dbstore/") or path.startswith("src/rgw/rgw_sal_dbstore"):
        return affect(
            "RGWDBSTORE-001",
            "Changes the opt-in DBStore SAL, SQLite schema/config store, connection pool, persistence operations, and manager path; relevant only where this experimental backend is built and selected.",
        )
    if path.startswith("src/rgw/driver/immutable_config/") or path.startswith("src/rgw/driver/json_config/"):
        return affect(
            "RGWMETA-001",
            "Adds selectable RGW configuration-store implementations used to load realm/zone/period state; applicability depends on the configured config-store path.",
        )

    if path.startswith("src/cls/fifo/") or path.startswith("src/cls/rgw/"):
        return affect(
            "RGWCLS-001",
            "Changes RGW/FIFO object-class operations and versioned bucket-index, reshard, lifecycle, GC, usage, multipart, OLH or queue encodings executed by mixed RGW and OSD cohorts.",
        )

    if path.startswith("src/rgw/driver/rados/"):
        name = Path(path).name
        if has_any(name, ("data_sync", "datalog", "bucket_sync", "sync_", "rgw_sync.", "trim_bilog", "trim_datalog", "trim_mdlog")):
            ids = "RGWSYNC-001"
            if "datalog" in name:
                ids += ", CFG-010"
            return affect(
                ids,
                "Changes default-RADOS multisite full/incremental sync, bucket-generation markers, data-log notification/polling, retry/error repository, leases, or log trimming used during mixed-version convergence.",
            )
        if has_any(name, ("bucket", "reshard")):
            return affect(
                "RGWBUCKET-001, RGWRESHARD-001",
                "Changes bucket layout/generation, index access, dynamic reshard state, bucket sync metadata, or reshard recovery in the default RADOS driver.",
            )
        if has_any(name, ("notify", "pubsub")):
            return affect(
                "RGWNOTIFY-001",
                "Changes persistent notification queues, reservation/commit, topic ownership, retry/failover, and endpoint delivery in the default RADOS driver.",
            )
        if has_any(name, ("lc_", "object_expirer")):
            return affect(
                "RGWLC-001",
                "Changes lifecycle cloud-tier transfer/resume or object-expirer execution reached after an RGW restart; existing lifecycle state and target endpoints require canary validation.",
            )
        if has_any(name, ("gc", "log_backing")):
            return affect(
                "RGWGC-001",
                "Changes garbage-collection/log backing operations and their persisted queue access in the default RADOS driver.",
            )
        if has_any(name, ("putobj", "obj_manifest", "etag")):
            return affect(
                "RGWOBJ-001",
                "Changes default-RADOS object ingest, manifest/stripe handling, or ETag verification on existing objects and multipart uploads.",
            )
        if path.startswith("src/rgw/driver/rados/config/") or has_any(name, ("metadata", "period", "zone", "realm", "user")):
            return affect(
                "RGWMETA-001",
                "Changes RADOS-backed realm, zone, period, user or metadata/config-store read/write paths used when the target gateway starts and reloads configuration.",
            )
        if "otp" in name:
            return affect(
                "RGWAUTH-001",
                "Changes RADOS-backed OTP metadata access used by configured MFA authentication paths.",
            )
        return affect(
            "RGWSAL-001",
            "Changes the active RADOS SAL/service/coroutine implementation used by the default RGW backend; startup and representative existing-object operations must be replayed on target artifacts.",
        )

    if path.startswith("src/rgw/services/"):
        name = Path(path).name
        if has_any(name, ("bilog", "bucket_sync", "mdlog")):
            return affect(
                "RGWSYNC-001",
                "Changes RGW metadata/bucket log and sync service operations used to converge multisite state and trim logs.",
            )
        if has_any(name, ("svc_bi", "bucket")):
            return affect(
                "RGWBUCKET-001",
                "Changes bucket-index or bucket metadata services used by existing bucket operations and reshard generations.",
            )
        if "notify" in name:
            return affect(
                "RGWNOTIFY-001",
                "Changes the RGW notification service wiring used for data-log and persistent-topic delivery.",
            )
        if "quota" in name:
            return affect(
                "RGWQUOTA-001",
                "Changes quota service lookup/cache integration used to enforce existing user and bucket limits.",
            )
        if has_any(name, ("user", "role", "otp")):
            return affect(
                "RGWAUTH-001",
                "Changes persisted user/role/OTP service access used by authentication and IAM operations.",
            )
        if has_any(name, ("zone", "meta")):
            return affect(
                "RGWMETA-001, RGWSYNC-001",
                "Changes zone/metadata backend services used for period reload and multisite metadata-log convergence.",
            )
        return affect(
            "RGWSAL-001",
            "Changes active RGW RADOS/system-object service interfaces and cache/core operations reached by the target daemon.",
        )

    # Operator utilities are conditional, but their changed behavior matters
    # whenever they are used for inspection or repair during the rollout.
    if path in {
        "src/rgw/rgw-gap-list", "src/rgw/rgw-orphan-list",
        "src/rgw/rgw-restore-bucket-index",
    }:
        return affect(
            "RGWREPAIR-001",
            "Changes RGW gap/orphan/bucket-index recovery tooling; it is conditional and must be rehearsed on cloned state, never inferred as an automatic upgrade step.",
        )
    if path == "src/rgw/rgw_admin.cc" or path.endswith("/rgw_tools.cc"):
        return affect(
            "RGWADMIN-001",
            "Changes radosgw-admin or shared operator tooling commands/output for bucket, user, period, sync, reshard and metadata workflows used during validation.",
        )

    name = Path(path).name
    if has_any(name, ("librgw", "rgw_file", "rgw_lib")):
        return affect(
            "RGWNFS-001",
            "Changes librgw/RGWFile/NFS-facing initialization, namespace, metadata and I/O behavior for deployments using the embedded gateway library.",
        )
    if "lua" in name:
        return affect(
            "RGWLUA-001",
            "Changes opt-in RGW Lua request/background/data-filter execution and package/context handling; existing scripts need target-runtime replay.",
        )
    if has_any(name, ("auth", "iam", "sts", "role", "token", "keystone", "ldap", "acl", "policy", "oidc", "public_access", "cors", "web_idp", "rgw_user")):
        return affect(
            "RGWAUTH-001",
            "Changes S3/Swift/Keystone authentication, service-token/STS/IAM role-policy parsing, signature validation, ACL/CORS or identity metadata behavior observable by existing clients.",
        )
    if has_any(name, ("pubsub", "notify", "amqp", "kafka")):
        return affect(
            "RGWNOTIFY-001",
            "Changes topic/filter persistence, event matching, AMQP/Kafka/HTTP endpoint connection, retry, acknowledgement, or persistent notification delivery.",
        )
    if has_any(name, ("crypt", "kms", "kmip", "object_lock")):
        return affect(
            "RGWENC-001",
            "Changes server-side encryption/KMS/KMIP or object-lock request/data handling; applies when those features or retained objects are present.",
        )
    if has_any(name, ("rgw_lc", "object_expirer")):
        return affect(
            "RGWLC-001",
            "Changes lifecycle queue traversal, shard head/lock/status persistence, expiration and cloud transition behavior after gateway restart.",
        )
    if has_any(name, ("multipart", "rgw_multi.")):
        return affect(
            "RGWOBJ-001",
            "Changes multipart request, metadata filtering, upload completion or delete behavior for existing S3 objects.",
        )
    if has_any(name, ("dmclock",)):
        return affect(
            "RGWCORE-001",
            "Changes active RGW request scheduling helpers; target canary must compare admission, cancellation and tail latency under the configured scheduler.",
        )
    if has_any(name, ("sync", "period", "zone", "realm", "metadata", "mdlog")):
        return affect(
            "RGWSYNC-001, RGWMETA-001",
            "Changes realm/zone/period metadata reload or multisite metadata/data sync, checkpoint, policy and compatibility paths.",
        )
    if has_any(name, ("bucket", "reshard")):
        return affect(
            "RGWBUCKET-001, RGWRESHARD-001",
            "Changes persisted bucket layout/generation, index selection, reshard progress/recovery, bucket metadata or bucket operation behavior.",
        )
    if has_any(name, ("quota", "ratelimit", "usage")):
        return affect(
            "RGWQUOTA-001",
            "Changes quota/rate-limit/usage accounting, cache or REST/admin output used for admission control and rollout observability.",
        )
    if has_any(name, ("gc", "orphan")):
        return affect(
            "RGWGC-001",
            "Changes garbage-collection or orphan discovery against existing manifests and queue entries after restart.",
        )
    if has_any(name, ("s3select", "putobj", "obj_", "multipart", "compression", "torrent")):
        return affect(
            "RGWOBJ-001",
            "Changes object ingest/read, multipart metadata, manifests, compression, S3 Select usage or object response behavior for existing S3 data.",
        )
    if has_any(name, ("rest", "op.", "op_", "website")):
        return affect(
            "RGWAPI-001",
            "Changes S3/Swift/admin REST dispatch, request parsing, operation routing or response/error behavior visible to existing clients and automation.",
        )
    if has_any(name, ("main", "appmain", "frontend", "process", "signal", "client_io", "worker")) or path.endswith("/radosgw.cc"):
        return affect(
            "RGWSTART-001",
            "Changes RGW daemon initialization, frontend/process/thread/signal lifecycle or request I/O reached on each gateway restart.",
        )
    if has_any(name, ("sal", "coroutine", "aio", "http_client", "cache", "common", "basic_types", "obj_types", "pool_types", "placement_types")):
        return affect(
            "RGWSAL-001",
            "Changes active SAL/common asynchronous, HTTP, cache or persisted-type plumbing used by the default RADOS gateway implementation.",
        )
    if has_any(name, ("rgw_log",)):
        return affect(
            "RGWOBS-001, CFG-010",
            "Changes RGW operations logging used to observe rollout behavior; the default ops-log sink also changes in owner 06.",
        )
    if has_any(name, ("perf_counters", "tracer")):
        return affect(
            "RGWOBS-001",
            "Changes RGW counters or tracing used to observe target gateway and request behavior during rollout.",
        )

    if path.startswith("src/rgw/"):
        return affect(
            "RGWCORE-001",
            "Changes an active RGW request/runtime helper in the default gateway binary; representative existing-client and restart behavior must be validated even though no standalone wire break is inferred.",
        )

    raise RuntimeError(f"owner 12 has an unreviewed row: {path!r}")


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        header = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 689:
        raise RuntimeError(f"owner 12 expected 689 rows, found {len(rows)}")
    if len({row["path"] for row in rows}) != len(rows):
        raise RuntimeError("owner 12 CSV contains duplicate paths")

    for row in rows:
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = verdict(row)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)

    affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
    trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
    print(f"Classified owner 12: affect={affect_count} trivial={trivial_count} unclassified=0")


if __name__ == "__main__":
    main()
