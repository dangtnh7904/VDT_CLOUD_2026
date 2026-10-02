"""Classify inspected small async messenger and entity formatting changes."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/msg/async/Stack.cc": ("MSG-051", "Worker start now calls virtual rename_thread; DPDKStack overrides it to keep DPDK lcore-worker names for affinity handling."),
    "src/msg/async/Stack.h": ("MSG-051", "Adds virtual rename_thread defaulting to prior msgr-worker naming, enabling DPDK override and distinct thread-name handling."),
}
trivial = {
    "src/msg/async/EventKqueue.cc": "T05-kqueue: event_wait only qualifies std::vector and wraps the signature; event loop body is unchanged.",
    "src/msg/async/EventKqueue.h": "T05-kqueue: std::vector qualification preserves the override type and callback behavior.",
    "src/msg/async/net_handler.cc": "T05-net-handler: Moves flags declaration into non-Windows branch and normalizes preprocessor indentation; socket calls and errors are unchanged.",
    "src/msg/async/rdma/RDMAStack.cc": "T05-rdma-include: Removes unused Tub include; dispatcher behavior has no changed hunk.",
    "src/msg/msg_fmt.h": "T05-entity-fmt: New fmt formatter emits the same type.? or type.number text as existing entity_name_t ostream formatter, with no wire encoding change.",
}
selected = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name not in selected:
        continue
    assert not row["upgrade_impact"], name
    if name in affect:
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
