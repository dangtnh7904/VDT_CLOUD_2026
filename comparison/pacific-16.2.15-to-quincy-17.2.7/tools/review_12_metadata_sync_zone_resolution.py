"""Verify metadata-sync convergence and RGW zone-resolution endpoint changes."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


def section(source: str, start: str, end: str | None = None) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) if end else len(source)
    return source[begin:finish]


metadata_commits = {
    "retry_success": "a906f78d435e887e87ba36ae4890f6ef045cddf5",
    "cleanup_index": "42b94e7ae282f67d0a71af748e3a454c5cb1fede",
    "empty_mdlog": "60ef5d8d4f09caea9fbe4547fa22e453ec6283d2",
    "consume_clone": "0011b181f144225205f4b3b07766b052c6966937",
}
zone_resolve_commit = "40039e1f914eff1eaa0c0859c6da7292c3361c50"
target_status_filter_commit = "ba3267d78928a03dec8eaa6e1f95108a45d8d930"
base_status_filter_commit = "097d574ab3e0cf288118759cb8575655452fbb94"
target_policy_guard_commit = "bb84fce4eae81e6c37cfc035f1d969649100b97c"
base_policy_guard_commit = "7019eef18323df73f261204a98bdfc081f2182ae"
for commit in (*metadata_commits.values(), zone_resolve_commit, target_status_filter_commit, target_policy_guard_commit):
    assert not is_ancestor(commit, "v16.2.15")
    assert is_ancestor(commit, "v17.2.7")
assert is_ancestor(base_status_filter_commit, "v16.2.15")
assert not is_ancestor(base_status_filter_commit, "v17.2.7")
assert is_ancestor(base_policy_guard_commit, "v16.2.15")
assert not is_ancestor(base_policy_guard_commit, "v17.2.7")

zone_message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", zone_resolve_commit],
    text=True,
    encoding="utf-8",
)
assert "Don't allow a zone to run under wrong zonegroup" in zone_message
assert "if only zone is provided" in zone_message

status_message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", target_status_filter_commit],
    text=True,
    encoding="utf-8",
)
assert "zones within a zonegroup can be configured" in status_message
assert "Filter such zones while reading sync" in status_message

# Pacific retries successful remote reads and local stores through all ten
# iterations. Quincy only retries negative results. Quincy also removes the
# temporary full-sync index and uses the truncated state to force/consume a
# remote mdlog fetch instead of stalling at an empty local tip.
base_sync = show("v16.2.15", "src/rgw/rgw_sync.cc")
target_sync = show("v17.2.7", "src/rgw/rgw_sync.cc")
base_entry = section(
    base_sync,
    "int RGWMetaSyncSingleEntryCR::operate(",
    "class RGWMetaSyncShardCR",
)
target_entry = section(
    target_sync,
    "int RGWMetaSyncSingleEntryCR::operate(",
    "class RGWMetaSyncShardCR",
)
assert "if (tries < NUM_TRANSIENT_ERROR_RETRIES - 1)" in base_entry
assert "if ((retcode < 0) && (tries < NUM_TRANSIENT_ERROR_RETRIES - 1))" not in base_entry
assert "if ((retcode < 0) && (tries < NUM_TRANSIENT_ERROR_RETRIES - 1))" in target_entry
assert target_entry.index("if (sync_status < 0)") < target_entry.index(
    "failed to fetch remote metadata"
)
assert "// clean up full sync index" not in base_sync
assert "// clean up full sync index" in target_sync
assert "if (mdlog_marker <= max_marker)" in base_sync
assert "if (mdlog_marker <= max_marker || !truncated)" in target_sync
assert "truncated = true;" not in base_sync
assert "truncated = true;" in target_sync

# The role metadata section is part of RGW-030 and was previously missing from
# this row's mapping. It is independent of the metadata-loop fixes above.
assert 'append_section_from_set(all_sections, "roles");' not in base_sync
assert 'append_section_from_set(all_sections, "roles");' in target_sync

# Quincy resolves an explicitly named zone back to its realm/current period,
# rejects a mismatched explicit zonegroup, and restricts default creation to
# the default single-site case. Pacific has neither search nor mismatch guard.
base_zone_svc = show("v16.2.15", "src/rgw/services/svc_zone.cc")
target_zone_svc = show("v17.2.7", "src/rgw/services/svc_zone.cc")
base_zone_h = show("v16.2.15", "src/rgw/rgw_zone.h")
target_zone_h = show("v17.2.7", "src/rgw/rgw_zone.h")
for token in (
    "int RGWSI_Zone::search_realm_with_zone(",
    "searching for the correct realm",
    "ERROR: incorrect zonegroup:",
    "ERROR: could not find zonegroup (",
    "int RGWSI_Zone::create_default_zg(",
):
    assert token not in base_zone_svc
    assert token in target_zone_svc
assert "bool find_zone(const DoutPrefixProvider *dpp" not in base_zone_h
assert target_zone_h.count("find_zone(const DoutPrefixProvider *dpp") >= 2

# `sync status` is endpoint parity, despite different release-branch commits:
# both endpoints require membership in the policy-derived source list. Do not
# promote the target commit title to a false upgrade finding.
base_admin = show("v16.2.15", "src/rgw/rgw_admin.cc")
target_admin = show("v17.2.7", "src/rgw/rgw_admin.cc")
base_status = section(base_admin, "static void get_data_sync_status(", "static void tab_dump(")
target_status = section(target_admin, "static void get_data_sync_status(", "static void tab_dump(")
assert "zone_syncs_from(*sz)" in base_status
assert "zone_syncs_from(*sz)" in target_status
assert "for (auto s : data_sync_source_zones)" in base_zone_svc
assert "for (auto s : data_sync_source_zones)" in target_zone_svc

# Adjacent rows are support/refactor only. The sync-policy JSON methods move
# from rgw_json_enc.cc into their owning source. The null guard in the policy
# helper has endpoint parity through release-specific commits. Dencoder test-
# instance bodies likewise move to their owning runtime sources.
base_policy = show("v16.2.15", "src/rgw/rgw_sync_policy.cc")
target_policy = show("v17.2.7", "src/rgw/rgw_sync_policy.cc")
base_json = show("v16.2.15", "src/rgw/rgw_json_enc.cc")
target_json = show("v17.2.7", "src/rgw/rgw_json_enc.cc")
assert "void rgw_sync_policy_info::dump(" not in base_policy
assert "void rgw_sync_policy_info::dump(" in target_policy
assert "void rgw_sync_policy_info::dump(" in base_json
assert "void rgw_sync_policy_info::dump(" not in target_json
base_set_bucket = section(base_policy, "void rgw_sync_bucket_entities::set_bucket(", "void rgw_sync_bucket_entities::remove_bucket(")
target_set_bucket = section(target_policy, "void rgw_sync_bucket_entities::set_bucket(", "void rgw_sync_bucket_entities::remove_bucket(")
assert "if (!bucket)" in base_set_bucket
assert "if (!bucket)" in target_set_bucket
assert "return;" in base_set_bucket
assert "return;" in target_set_bucket

base_dencoder = show("v16.2.15", "src/rgw/rgw_dencoder.cc")
target_dencoder = show("v17.2.7", "src/rgw/rgw_dencoder.cc")
target_manifest = show("v17.2.7", "src/rgw/rgw_obj_manifest.cc")
target_log = show("v17.2.7", "src/rgw/rgw_log.cc")
for token, owner_source in (
    ("void RGWObjManifest::generate_test_instances(", target_manifest),
    ("void rgw_log_entry::generate_test_instances(", target_log),
):
    assert token in base_dencoder
    assert token not in target_dencoder
    assert token in owner_source


new_rows = {
    "src/rgw/rgw_sync.cc": (
        "affect",
        "RGW-030,RGW-048",
        "RGW-030: Adds roles to the full metadata-sync section list. RGW-048: Quincy stops retrying successful metadata reads/writes ten times, cleans completed full-sync index objects, and fixes truncated-state handling so incremental mdlog fetch can converge from an empty/local-tip state.",
    ),
    "src/rgw/services/svc_zone.cc": (
        "affect",
        "RGW-049",
        "RGW-049: Quincy resolves a configured zone through realm/period metadata and rejects a mismatched explicit zonegroup instead of allowing startup under the wrong topology; the adjacent policy-aware sync-status filter is already present in Pacific through a release-specific backport.",
    ),
    "src/rgw/services/svc_zone.h": (
        "affect",
        "RGW-049",
        "RGW-049: Declares the realm search and explicit default-zone/zonegroup initialization paths used during RGW startup; the policy-aware zone_syncs_from overload has endpoint parity.",
    ),
    "src/rgw/rgw_sync.h": (
        "trivial",
        "RGW-048",
        "RGW-048 support: Header net diff qualifies STL/SAL types, removes an unused include and follows destructor placement; the metadata retry, index cleanup and truncated-state behavior is implemented in rgw_sync.cc.",
    ),
    "src/rgw/rgw_dencoder.cc": (
        "trivial",
        "",
        "RGW-DENCODER-MOVE-01: Moves generate_test_instances helpers to their owning sources and adds a bucket-encryption dencoder fixture; it changes test-tool organization/coverage, not daemon encoding or upgrade execution.",
    ),
    "src/rgw/rgw_sync_policy.cc": (
        "trivial",
        "",
        "RGW-SYNC-POLICY-MAINT-01: Moves existing JSON dump/decode methods from rgw_json_enc.cc; the bucket-null guard exists at both endpoints through release-specific commits, so no policy migration or endpoint behavior change is introduced here.",
    ),
    "src/rgw/rgw_sync_policy.h": (
        "trivial",
        "",
        "RGW-SYNC-POLICY-MAINT-01: Qualifies existing string/vector/map declarations with std:: while retaining the same version-1 policy encoders and matching contract.",
    ),
}

existing_rows = {
    "src/rgw/rgw_zone.cc": (
        "RGW-049",
        "RGW-049: Implements realm/period lookup of a zone so startup can recover the correct topology when only the zone is configured.",
    ),
    "src/rgw/rgw_zone.h": (
        "RGW-049",
        "RGW-049: Declares period-map, realm and period zone lookup APIs consumed by Quincy's startup resolver.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

for path, (finding, reason) in existing_rows.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    ids = [item for item in row["finding_id"].split(",") if item]
    if finding not in ids:
        row["finding_id"] = ",".join(ids + [finding])
    if reason not in row["impact_reason"]:
        row["impact_reason"] = row["impact_reason"].rstrip() + " " + reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified metadata-sync/zone-resolution cluster: 3 affect, 4 trivial; enriched 2 affect rows")
