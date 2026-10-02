"""Classify common logging transport, persistent summary and route parsing."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
findings = {
    "src/common/LRUSet.h": ("MSG-013", "New encodable LRU set stores recent LogEntry keys for MON LogSummary dedup across checkpoints."),
    "src/common/LogEntry.cc": ("MSG-013", "LogSummary encoding advances to v4 with channel_info/recent_keys and drops pre-Mimic/pre-Nautilus encode branches."),
    "src/common/LogEntry.h": ("MSG-013", "LogSummary adds per-channel sequence ranges and recent-key LRU used by MON persistent logging."),
    "src/common/Journald.cc": ("MSG-014", "New systemd journald client sends local and cluster entries, including large-entry fd fallback and conditional no-journal behavior."),
    "src/common/Journald.h": ("MSG-014", "New journald logger APIs are real under WITH_SYSTEMD and no-op otherwise, changing available log destinations."),
    "src/common/Graylog.cc": ("MSG-014", "Graylog construction delegates and set_hostname now asserts a nonempty host; logger initialization supplies host/fsid before sending."),
    "src/log/Log.cc": ("MSG-014;MSG-016", "Local log can be sent to journald/Graylog with host/fsid; set_max_recent now changes only m_max_recent, leaving EntryRing capacity unchanged."),
    "src/log/Log.h": ("MSG-014;MSG-016", "Logger exposes journald destination and separate m_max_recent field while recent ring retains its existing capacity."),
    "src/common/LogClient.cc": ("MSG-015", "Cluster-log route config now uses per-channel get_value_via_strmap; multi-entry maps yield empty and explicit channel keys can return key rather than value."),
    "src/common/LogClient.h": ("MSG-015", "LogChannel config interface changes from parsed per-option maps to per-channel strings used by routing decisions."),
    "src/common/str_map.cc": ("MSG-015", "String-map parser changes duplicate-key behavior via emplace and new get_value_via_strmap only handles single-entry maps, affecting channel-specific log routes."),
    "src/include/str_map.h": ("MSG-015", "New for_each_pair and get_value_via_strmap helpers form the route parser used by LogClient, changing multi-key and explicit-channel semantics."),
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    path = row["path"]
    if path not in findings:
        continue
    assert not row["upgrade_impact"], path
    fid, reason = findings[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
