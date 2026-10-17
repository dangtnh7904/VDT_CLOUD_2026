"""Classify inspected Dashboard/RGW compatibility paths in owner 07."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "07-mgr-modules-monitoring.csv"
base = "src/pybind/mgr/dashboard/"
decisions = {
    "controllers/rgw.py": (
        "affect", "MGR-045;MGR-046",
        "T07-rgw-controller: Bucket get/set now always queries S3 ?encryption; "
        "set defaults encryption_state=false and deletes an enabled setting when "
        "the caller omits it. Daemon list newly int-parses frontend_config#0 "
        "with split('port='), which fails on accepted endpoint/civetweb formats."
    ),
    "services/rgw_client.py": (
        "affect", "MGR-045",
        "T07-rgw-encryption-client: New S3 GET/PUT/DELETE ?encryption calls; "
        "only the Quincy no-configuration error code is converted to Disabled. "
        "Pacific RGW has no bucket-encryption operation, creating a mixed-version "
        "Dashboard bucket-detail compatibility path."
    ),
    "services/ceph_service.py": (
        "affect", "MGR-045",
        "T07-rgw-encryption-config: Bucket form always requests new getEncryptionConfig; "
        "this service reads RGW vault settings via MON config get, while explicit "
        "form submission can write them via config set. send_command default "
        "JSON behavior remains unchanged."
    ),
    "frontend/src/app/ceph/rgw/rgw-bucket-form/rgw-bucket-form.component.ts": (
        "affect", "MGR-045",
        "T07-rgw-bucket-form: On initialization the Quincy form always fetches "
        "encryption config; on edit it reads bucket encryption status and sends "
        "the state explicitly with update, unlike legacy external API callers."
    ),
    "frontend/src/app/ceph/rgw/rgw-bucket-form/rgw-bucket-form.component.html": (
        "affect", "MGR-045",
        "T07-rgw-bucket-ui: New encryption checkbox and SSE/KMS fields feed the "
        "bucket edit call, whose state now controls whether default bucket "
        "encryption is added or removed."
    ),
    "frontend/src/app/shared/api/rgw-bucket.service.ts": (
        "affect", "MGR-045",
        "T07-rgw-bucket-api: Quincy frontend sends encryption_state/type/key in "
        "create/update and always uses the new getEncryptionConfig endpoint in "
        "the bucket form; external callers need to review the new edit default."
    ),
    "frontend/src/app/ceph/rgw/models/rgw-bucket-encryption.ts": (
        "trivial", "",
        "T07-rgw-optional-encryption-ui: Constants list Vault, auth methods and "
        "secret engines for the new manual configuration form; no automatic "
        "upgrade action or independent compatibility path."
    ),
    "frontend/src/app/ceph/rgw/models/rgw-daemon.ts": (
        "trivial", "",
        "T07-rgw-port-view: Adds the TypeScript port property for the new "
        "daemon-list column; MGR-046's failure path is in backend parsing."
    ),
    "frontend/src/app/ceph/rgw/rgw-bucket-details/rgw-bucket-details.component.html": (
        "trivial", "",
        "T07-rgw-encryption-view: Displays the encryption field returned by "
        "MGR-045, without changing bucket state or the GET compatibility path."
    ),
    "frontend/src/app/ceph/rgw/rgw-config-modal/rgw-config-modal.component.html": (
        "trivial", "",
        "T07-rgw-optional-encryption-ui: New SSE/KMS Vault input form opens "
        "only after a user clicks configuration; no upgrade recipe invokes it."
    ),
    "frontend/src/app/ceph/rgw/rgw-config-modal/rgw-config-modal.component.scss": (
        "trivial", "",
        "T07-rgw-optional-encryption-ui: Empty stylesheet marker for the "
        "manual RGW encryption configuration modal."
    ),
    "frontend/src/app/ceph/rgw/rgw-config-modal/rgw-config-modal.component.spec.ts": (
        "trivial", "",
        "T07-rgw-optional-encryption-unit: Isolated Angular create-component "
        "test for a manual config modal; no executed upgrade acceptance gate."
    ),
    "frontend/src/app/ceph/rgw/rgw-config-modal/rgw-config-modal.component.ts": (
        "trivial", "",
        "T07-rgw-optional-encryption-ui: Validation and config-set request occur "
        "only on explicit modal submission; no automatic config migration or "
        "documented role in this upgrade's acceptance path."
    ),
    "frontend/src/app/ceph/rgw/rgw-daemon-list/rgw-daemon-list.component.spec.ts": (
        "trivial", "",
        "T07-rgw-port-unit: Updates mock port and heading assertions for the "
        "MGR-046 presentation; no independent executed upgrade gate."
    ),
    "frontend/src/app/ceph/rgw/rgw-daemon-list/rgw-daemon-list.component.ts": (
        "trivial", "",
        "T07-rgw-port-view: Reorders Realm/Zone columns and displays the "
        "backend-supplied port; the compatibility failure is in MGR-046's "
        "backend parser, not this table configuration."
    ),
    "frontend/src/app/ceph/rgw/rgw.module.ts": (
        "trivial", "",
        "T07-rgw-optional-routes: Registers manual encryption modal, user tabs "
        "and role CRUD route; no automatic upgrade request or state migration."
    ),
    "tests/test_rgw.py": (
        "trivial", "",
        "T07-rgw-daemon-unit: Mock fixture adds beast port=80 and asserts the "
        "new port response; it supports MGR-046 but does not independently "
        "change an executed upgrade or acceptance recipe."
    ),
    "frontend/src/app/shared/api/rgw-bucket.service.spec.ts": (
        "trivial", "",
        "T07-rgw-bucket-unit: Angular HTTP mock assertions follow the new "
        "encryption query parameters in MGR-045; no independent rollout gate "
        "or production behavior in the test file."
    ),
}

with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None

for relative, (impact, finding, reason) in decisions.items():
    target = base + relative
    matches = [row for row in rows if row["path"] == target]
    assert len(matches) == 1, target
    row = matches[0]
    if row["upgrade_impact"]:
        assert (row["upgrade_impact"], row["finding_id"], row["impact_reason"]) == (impact, finding, reason), target
        continue
    assert not row["finding_id"] and not row["impact_reason"], target
    row["upgrade_impact"] = impact
    row["finding_id"] = finding
    row["impact_reason"] = reason

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
