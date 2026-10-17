"""Verify the RGW metadata-log trim endpoint sanity gate."""

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


commit = "aa9781d9634c5b26c02cdcb3da51c039d8e7ee13"
message = subprocess.check_output(
    ["git", "-C", str(repo), "show", "-s", "--format=%B", commit],
    text=True,
    encoding="utf-8",
)
assert "Report empty endpoints as error instead of crashing" in message
assert not is_ancestor(commit, "v16.2.15")
assert is_ancestor(commit, "v17.2.7")

base_trim = show("v16.2.15", "src/rgw/rgw_trim_mdlog.cc")
target_trim = show("v17.2.7", "src/rgw/rgw_trim_mdlog.cc")
assert "sanity_check_endpoints" not in base_trim
assert "sanity_check_endpoints" in target_trim

sanity_start = target_trim.index("bool sanity_check_endpoints")
sanity_end = target_trim.index("RGWCoroutine* create_meta_log_trim_cr", sanity_start)
sanity = target_trim[sanity_start:sanity_end]
assert "period.get_map().zonegroups" in sanity
assert "if (zonegroup.endpoints.empty())" in sanity
assert "WARNING: Cluster is is misconfigured!" in sanity
assert "if (zone.endpoints.empty())" in sanity
assert "has no endpoints! Trimming is impossible." in sanity
assert "retval = false;" in sanity

# Both the background and admin autotrim factories reject a topology with an
# empty zone endpoint. A zonegroup-level endpoint omission alone is warning-only.
for signature in (
    "RGWCoroutine* create_meta_log_trim_cr",
    "RGWCoroutine* create_admin_meta_log_trim_cr",
):
    start = target_trim.index(signature)
    body = target_trim[start:start + 900]
    assert "if (!sanity_check_endpoints(dpp, store))" in body
    assert "return nullptr;" in body

zonegroup_block = sanity[
    sanity.index("if (zonegroup.endpoints.empty())"):
    sanity.index("for (const auto& [_, zone]", sanity.index("if (zonegroup.endpoints.empty())"))
]
assert "retval = false" not in zonegroup_block

base_rados = show("v16.2.15", "src/rgw/rgw_rados.cc")
target_rados = show("v17.2.7", "src/rgw/rgw_rados.cc")
assert "Bailing out of trim thread!" not in base_rados
assert "Bailing out of trim thread!" in target_rados
target_process_start = target_rados.index("int process(const DoutPrefixProvider *dpp) override {", target_rados.index("class RGWSyncLogTrimThread"))
target_process_end = target_rados.index("// implements DoutPrefixProvider", target_process_start)
target_process = target_rados[target_process_start:target_process_end]
assert target_process.index("if (!metatrimcr)") < target_process.index("create_data_log_trim_cr")
assert target_process.index("return -EINVAL;") < target_process.index("create_data_log_trim_cr")
assert target_process.index("return -EINVAL;") < target_process.index("create_bucket_trim_cr")

base_admin = show("v16.2.15", "src/rgw/rgw_admin.cc")
target_admin = show("v17.2.7", "src/rgw/rgw_admin.cc")
assert "Cluster misconfigured! Unable to trim." not in base_admin
assert "Cluster misconfigured! Unable to trim." in target_admin
admin_start = target_admin.index("if (opt_cmd == OPT::MDLOG_AUTOTRIM)")
admin_end = target_admin.index("if (opt_cmd == OPT::MDLOG_TRIM)", admin_start)
admin_autotrim = target_admin[admin_start:admin_end]
assert "if (!mltcr)" in admin_autotrim
assert "return -EIO;" in admin_autotrim

# Explicit marker-based mdlog trim remains a separate direct operation in both
# endpoints and is not routed through the new topology sanity check.
for admin in (base_admin, target_admin):
    direct_start = admin.index("if (opt_cmd == OPT::MDLOG_TRIM)")
    direct_end = admin.index("if (opt_cmd == OPT::SYNC_INFO)", direct_start)
    direct = admin[direct_start:direct_end]
    assert "meta_log->trim" in direct
    assert "sanity_check_endpoints" not in direct

# The background trimmer is active by default every 1200 seconds in both tags.
base_options = show("v16.2.15", "src/common/options.cc")
target_options = show("v17.2.7", "src/common/options/rgw.yaml.in")
base_option_start = base_options.index('Option("rgw_sync_log_trim_interval"')
target_option_start = target_options.index("- name: rgw_sync_log_trim_interval")
assert ".set_default(1200)" in base_options[base_option_start:base_option_start + 350]
assert "default: 20_min" in target_options[target_option_start:target_option_start + 300]
for source in (base_rados, target_rados):
    assert "if (interval > 0)" in source
    assert "sync_log_trimmer->start();" in source

# Bilog/datalog endpoint diffs retain their algorithms; they only follow the
# SAL/DPP/interface migration. Their automatic execution is nevertheless
# skipped by the target caller when the mdlog topology gate rejects the pass.
base_bilog = show("v16.2.15", "src/rgw/rgw_trim_bilog.cc")
target_bilog = show("v17.2.7", "src/rgw/rgw_trim_bilog.cc")
for token in (
    "take_min_status",
    "BucketTrimShardCollectCR",
    "RGWRadosBILogTrimCR",
    "create_bucket_trim_cr",
):
    assert token in base_bilog and token in target_bilog

base_datalog = show("v16.2.15", "src/rgw/rgw_trim_datalog.cc")
target_datalog = show("v17.2.7", "src/rgw/rgw_trim_datalog.cc")
for token in (
    "take_min_markers",
    "DatalogTrimImplCR",
    "DataLogTrimPollCR",
    "create_data_log_trim_cr",
):
    assert token in base_datalog and token in target_datalog


new_rows = {
    "src/rgw/rgw_trim_mdlog.cc": (
        "affect",
        "RGW-044",
        "RGW-044: Quincy scans every current-period zone before metadata-log trimming and returns no coroutine when any zone has no endpoints; background sync-log trimming then skips mdlog, datalog and bilog for that pass, while admin mdlog autotrim returns EIO instead of entering Pacific's crash-prone path.",
    ),
    "src/rgw/rgw_trim_bilog.cc": (
        "trivial",
        "",
        "RGW-TRIM-MECH-01: Bilog marker selection, watcher protocol and trim coroutines are unchanged; net hunks follow the RadosStore/DPP migration and use equivalent unique_ptr construction. RGW-044's cross-log skip is owned by the caller/mdlog gate.",
    ),
    "src/rgw/rgw_trim_datalog.cc": (
        "trivial",
        "",
        "RGW-TRIM-MECH-01: Datalog marker correlation, locking and trim loop are unchanged; all net hunks rename the SAL RADOS store type. RGW-044's cross-log skip occurs before this coroutine is created.",
    ),
}

existing_additions = {
    "src/rgw/rgw_admin.cc": (
        "RGW-044",
        "RGW-044: Quincy detects a null mdlog-autotrim coroutine for an empty-zone-endpoint topology and returns EIO with an explicit misconfiguration error.",
    ),
    "src/rgw/rgw_rados.cc": (
        "RGW-044",
        "RGW-044: The target background sync-log trim pass aborts before constructing mdlog, datalog or bucket/bilog trim stacks when endpoint sanity rejects the current period topology.",
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

for path, (finding, reason) in existing_additions.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    findings = row["finding_id"].split(",") if row["finding_id"] else []
    if finding not in findings:
        row["finding_id"] = ",".join(findings + [finding])
        row["impact_reason"] = (row["impact_reason"] + " " + reason).strip()
    else:
        assert reason in row["impact_reason"], path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified sync-log trim: 1 affect, 2 trivial; extended 2 existing affect rows")
