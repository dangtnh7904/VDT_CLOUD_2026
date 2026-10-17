"""Screen exact small RGW documentation diffs with no executable upgrade path."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
editorial = {
    "doc/man/8/rgw-orphan-list.rst": ("http://ceph.com/docs", "https://docs.ceph.com"),
    "doc/radosgw/cloud-sync-module.rst": ("conection_id", "connection_id"),
    "doc/radosgw/api.rst": ("", ".. _radosgw api:"),
    "doc/radosgw/index.rst": ("", "D3N Data Cache"),
    "doc/radosgw/bucketpolicy.rst": ("s3:ExistingOBjectTag", "s3:ExistingObjectTag"),
    "doc/radosgw/swift.rst": ("", ".. _radosgw swift:"),
    "doc/radosgw/swift/tempurl.rst": ("print rest_uri", "print(rest_uri)"),
    "doc/radosgw/multisite-sync-policy.rst": ("Destinatino storage class", "Destination storage class"),
    "doc/radosgw/swift/python.rst": ("print container", "print(container"),
    "doc/radosgw/pubsub-module.rst": ("the ropic", "the topic"),
    "doc/radosgw/rgw-cache.rst": ("", "D3N RGW Data Cache"),
}
support = {
    "doc/radosgw/dynamicresharding.rst": ("process is transparent to the user.", "Write I/Os to the target bucket"),
    "doc/radosgw/s3/authentication.rst": ("", "s3:GetBucketEncryption"),
}
all_paths = editorial.keys() | support.keys()
assert len(all_paths) == 13


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True,
        encoding="utf-8",
    )
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:].strip())
    return old, new


path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for source in sorted(all_paths):
    old, new = changed_lines(source)
    old_needle, new_needle = (editorial | support)[source]
    assert new and (not old_needle or any(old_needle in line for line in old)), source
    assert any(new_needle in line for line in new), source
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    # The CSV counts include non-empty and empty lines; this screen inspects
    # all non-empty changed text above and limits the hunk size to the reviewed batch.
    assert len(old) + len(new) <= 8, source
    if source == "doc/radosgw/s3/authentication.rst":
        reason = "RGW-DOC-01: Documents the BucketEncryption ACL mapping already analyzed in RGW-002; this text does not alter request authorization or upgrade validation."
        finding = "RGW-002"
    elif source == "doc/radosgw/dynamicresharding.rst":
        reason = "RGW-DOC-01: Adds an operational description of read/write behavior during reshard; the doc hunk changes no daemon, recipe, or acceptance gate."
        finding = ""
    else:
        reason = "RGW-DOC-01: Only corrects RGW documentation spelling/Python example or adds a documentation link/label; no daemon, recipe, or upgrade gate changes."
        finding = ""
    row.update(upgrade_impact="trivial", finding_id=finding, impact_reason=reason)

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(all_paths)} small RGW documentation diffs trivial")
