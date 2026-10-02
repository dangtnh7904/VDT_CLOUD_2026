"""Record reviewed OSD protocol, store, EC and offline-tool endpoint hunks."""

import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "01-osd-pg-recovery.csv"

protocol = [
    "MOSDBoot.h", "MOSDFailure.h", "MOSDMarkMeDown.h", "MOSDPGInfo.h",
    "MOSDPGLog.h", "MOSDPGNotify.h", "MOSDPGScan.h", "MOSDRepOp.h",
    "MOSDRepOpReply.h",
]
affect = {
    **{f"src/messages/{name}": (
        "OSD-028",
        "Removes legacy OSD message encode/decode path or raises compatibility floor; inspect peer feature and header version in OSD-028."
    ) for name in protocol},
    "src/os/ObjectStore.cc": (
        "OSD-029", "Factory returns unique_ptr; two/three-argument forms change Seastar MemStore/BlueStore support while classic factory retains FileStore and gated KStore."
    ),
    "src/os/ObjectStore.h": (
        "OSD-029;OSD-024", "Factory signatures and store ownership change; virtual fast-shutdown/null-manager hooks connect to OSD-024."
    ),
    "src/erasure-code/ErasureCode.cc": (
        "OSD-030", "EC rule creation no longer writes CRUSH rule mask max_size; deprecated mask removal is covered by MON-006."
    ),
    "src/erasure-code/lrc/ErasureCodeLrc.cc": (
        "OSD-030", "LRC rule allocation no longer checks ruleset or passes min/max; malformed profile now returns parse error before parsing crush-steps."
    ),
    "src/tools/ceph_objectstore_tool.cc": (
        "OSD-031", "Offline tool removes get/set-superblock, accepts meta collection object iteration, changes PG log rollback flag and unmounts FUSE store."
    ),
}
trivial = {
    "src/messages/MRemoveSnaps.h": "Only grants Crimson make_message friendship for construction; no message payload, version or operator procedure changes in this hunk.",
    "src/erasure-code/clay/ErasureCodeClay.cc": "Removes plane_count local and increment; variable was never read in the repair loop.",
    "src/os/FuseStore.cc": "Changes string-keyed xattr map to transparent std::less<> comparator; ordering and FUSE operation are unchanged.",
    "src/os/Transaction.cc": "Test-instance attribute map uses transparent std::less<>; same string keys and encoded values.",
    "src/os/Transaction.h": "Zero-initializes endian wrappers with literal zero and uses transparent string comparator; operation count, setattrs encoding and ordering stay the same.",
    "src/tools/ceph_osdomap_tool.cc": "Adds using namespace std only; no function body or command behavior changes.",
    "src/tools/erasure-code/ceph-erasure-code-tool.cc": "Uses argv_to_vec return value instead of output argument; same argument vector reaches global_init; namespace declaration only otherwise.",
}
assert not set(affect) & set(trivial)
with path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {r["path"] for r in rows if r["path"] in affect or r["path"] in trivial} == set(affect) | set(trivial)
for row in rows:
    name = row["path"]
    if name in affect:
        assert not row["upgrade_impact"], name
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    elif name in trivial:
        assert not row["upgrade_impact"], name
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = f"T01-source: {trivial[name]}"
with path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
