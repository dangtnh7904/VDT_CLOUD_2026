"""Classify inspected common-container, wire-helper and message ownership diffs."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/common/RefCountedObj.h": ("MSG-022", "New UniquePtrDeleter calls put() for uniquely owned Crimson messages, preserving intrusive reference-counted destruction."),
    "src/msg/MessageRef.h": ("MSG-022", "Adds MURef/MessageURef ownership types used by Crimson send and resend queues."),
    "src/common/bit_vector.hpp": ("MSG-026", "BitVector postfix increment now advances only the returned copy, leaving the original iterator unchanged; BitVector is used by RBD object maps."),
    "src/common/bloom_filter.cc": ("MSG-027", "Bloom table encode/decode changes from bufferptr/raw array to mempool vector and empty-table density now divides by zero."),
    "src/common/bloom_filter.hpp": ("MSG-027", "Bloom table storage and compression operations move from raw mempool allocation to vector; HitSet and BlueStore consumers use this type."),
    "src/common/buffer.cc": ("MSG-028", "Bufferlist append growth, c_str rebuild decision and new iov batching change allocation and Crimson SeaStore writev behavior."),
    "src/common/buffer_instrumentation.h": ("MSG-028", "New instrumented raw base is used by KernelDevice hugepage buffer pool, while inspection helpers are used by tests."),
    "src/common/assert.cc": ("MSG-008", "Assertion and abort diagnostics now instantiate ClibBackTrace, whose frame cap differs from base BackTrace."),
    "src/msg/msg_types.cc": ("MSG-029", "Entity name parsing moves to string_view and address parsing accepts explicit default type; both feed daemon identity/address handling."),
    "src/msg/msg_types.h": ("MSG-029", "Entity name parse API changes to string_view and address parse default-type argument is exposed to callers."),
}
trivial = {
    "src/messages/MKVData.h": "T05-optional: Replaces boost::optional<bufferlist> with std::optional; presence byte and contained bufferlist encoding remain the same in encoding.h, and message version is unchanged.",
    "src/messages/MStatfs.h": "T05-optional: Replaces boost::optional<int64_t> with std::optional; both encode one presence byte then the same int64_t, with unchanged message version and fallback for old header.",
    "src/msg/Policy.h": "T05-policy: Production supported-feature mask remains CEPH_FEATURES_SUPPORTED_DEFAULT; only the messenger unit test macro retains mutability, and no production assignment exists at either endpoint.",
}
selected = set(affect) | set(trivial)
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in affect:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
