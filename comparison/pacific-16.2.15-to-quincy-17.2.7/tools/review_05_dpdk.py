"""Classify DPDK net-diff by optional migration, RSS, EAL and NIC behavior."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/msg/async/dpdk/Packet.h": ("MSG-055", "RSS hash clone now copies optional value/state rather than constructing a uint32 from Tub's bool conversion; routing hash may differ after packet storage relocation."),
    "src/msg/async/dpdk/DPDKStack.cc": ("MSG-056", "DPDK worker launch/join now uses instance EAL start/execute/stop, reserves callback storage and takes stable function address."),
    "src/msg/async/dpdk/DPDKStack.h": ("MSG-056", "DPDKStack owns eal instance and overrides worker naming; startup/shutdown and lcore affinity paths differ."),
    "src/msg/async/dpdk/dpdk_rte.cc": ("MSG-056", "EAL initialization now reports failure, applies NIC allowlist, and stops/joins master thread instead of detached static loop."),
    "src/msg/async/dpdk/dpdk_rte.h": ("MSG-056", "EAL lifecycle and work queue move from static globals to per-instance state with explicit stop."),
    "src/msg/async/dpdk/DPDK.cc": ("MSG-057", "DPDK NIC init gates TSO on ms_dpdk_enable_tso and exposes PMD stats/xstats via admin socket; error paths and DPDK API compatibility also change."),
    "src/msg/async/dpdk/DPDK.h": ("MSG-057", "TX mbuf uses buf_iova/rte_mem_virt2iova, DPDK NIC registers stats hook and changes initialization error handling."),
}
trivial = {
    "src/msg/async/dpdk/ARP.cc": "T05-dpdk-optional: ARP packet queue return changes Tub to optional; same empty check, move and pop sequence.",
    "src/msg/async/dpdk/ARP.h": "T05-dpdk-optional: ARP get_packet declaration follows Tub-to-optional return with no protocol handling change.",
    "src/msg/async/dpdk/EventDPDK.cc": "T05-dpdk-namespace: Qualifies std::vector in event_wait definition; event body unchanged.",
    "src/msg/async/dpdk/EventDPDK.h": "T05-dpdk-namespace: Qualifies std::vector in override declaration; same callback signature.",
    "src/msg/async/dpdk/IP.cc": "T05-dpdk-optional: IPv4 queue return uses optional but retains provider loop, move and pop behavior.",
    "src/msg/async/dpdk/IP.h": "T05-dpdk-optional: Tub-to-optional swaps keep engaged state and same fragment timer IDs; emplace/assignment replace construct.",
    "src/msg/async/dpdk/TCP.cc": "T05-dpdk-namespace: Only qualifies std::ostream in TCB log-prefix method.",
    "src/msg/async/dpdk/TCP.h": "T05-dpdk-optional: Timer/packet/accept Tub-to-optional replacements preserve reset/emplace and queue behavior in inspected hunks.",
    "src/msg/async/dpdk/UserspaceEvent.cc": "T05-dpdk-optional: FD slots replace Tub construct/destroy with optional emplace/reset; mask and poll logic unchanged.",
    "src/msg/async/dpdk/UserspaceEvent.h": "T05-dpdk-optional: FD slot storage becomes optional with equivalent engaged checks and unchanged event masks.",
    "src/msg/async/dpdk/net.cc": "T05-dpdk-optional: Packet-provider local result becomes optional; provider iteration and dispatch unchanged.",
    "src/msg/async/dpdk/net.h": "T05-dpdk-optional: Packet-provider type declaration changes Tub to optional; no wire or route logic in hunk.",
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
