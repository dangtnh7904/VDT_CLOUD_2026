"""Classify remaining non-Crimson owner-05 headers and QAT source."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/include/buffer.h": ("MSG-028", "Declares prepare_iovs used by Crimson SeaStore segmented writes and retains C++11-compatible append syntax for librados headers."),
    "src/include/byteorder.h": ("MSG-060", "Endian conversion switches to Boost.Endian and ceph_le gains explicit constructor while init_le helpers disappear; persisted/wire fields need cross-endian verification."),
    "src/include/config-h.in.cmake": ("MSG-061", "Generated feature header adds systemd, memset_s, suseconds_t, EC ISA, RGW dbstore and libcephsqlite gates while removing legacy build macros."),
    "src/include/types.h": ("MSG-062", "MON subscription start rendering now casts 64-bit little-endian value to long, potentially narrowing diagnostic value on 32-bit/LLP64."),
    "src/crypto/qat/qcccrypto.cc": ("MSG-063", "QAT pthread crypt callback now returns its argument rather than falling off a void* function, removing undefined callback return behavior."),
    "src/log/Entry.h": ("MSG-064", "ConcreteEntry move constructor loses noexcept, allowing EntryVector growth to copy instead of move and changing log-buffer resource pressure."),
}
trivial = {
    "src/crypto/qat/qat_crypto_plugin.h": "T05-qat-namespace: Qualifies std::ostream in factory override; signature and factory body are unchanged.",
    "src/include/cpp-btree/btree_container.h": "T05-btree-unused: Removes btree_multiset node-handle insert overloads; no in-tree production btree_multiset instantiation/call found.",
    "src/include/cpp-btree/btree_set.h": "T05-btree-unused: Removes matching btree_multiset extract exposure/docs; no in-tree production use found.",
    "src/include/neorados/RADOS_Decodable.hpp": "T05-neorados-fmt: Adds fmt>=9 ostream formatter for Entry; no in-tree fmt formatting call for Entry found, and encoding is unchanged.",
    "src/include/win32/dlfcn.h": "T05-win-dlfcn: New one-line forwarding header has no in-tree include found; no observed build/runtime path.",
    "src/include/xlist.h": "T05-xlist-iterator: Replaces deprecated std::iterator inheritance with equivalent traits; list traversal and mutation bodies unchanged.",
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
