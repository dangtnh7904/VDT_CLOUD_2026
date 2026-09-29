"""Record reviewed service-option YAML verdicts for owner 06."""

import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "06-config-defaults.csv"
review = {
    "src/common/config.h": ("trivial", "", "T06-variant: endpoint hunk changes boost::variant/get to std::variant/get for same ConfigValues members; no changed option value, precedence, or rollout API."),
    "src/common/options/ceph-exporter.yaml.in": ("affect", "CFG-013", "CFG-013: target adds ceph-exporter service options used by exporter HTTP endpoint; conditional rollout monitoring path."),
    "src/common/options/cephfs-mirror.yaml.in": ("trivial", "", "T06-yaml-parity: all 9 options exist in base options.cc; mount_timeout default 10 and caller match both endpoints; YAML extraction only."),
    "src/common/options/crimson.yaml.in": ("affect", "CFG-012", "CFG-012: target adds SeaStore segment/journal/cache/device options consumed by Crimson OSD; conditional activation and recovery path."),
    "src/common/options/immutable-object-cache.yaml.in": ("trivial", "", "T06-yaml-parity: all 13 options exist in base; watermark default 0.9 matches base after target YAML fix; no changed rollout setting."),
    "src/common/options/mds-client.yaml.in": ("trivial", "", "T06-yaml-parity: existing 64 MDS-client option names/defaults move from C++; startup/no_mon_update flags on fake inos match base."),
    "src/common/options/mds.yaml.in": ("affect", "CFG-009", "CFG-009: new default-true mds_symlink_recovery is read by MDCache and changes symlink target persistence for future writes."),
    "src/common/options/mgr.yaml.in": ("affect", "CFG-010", "CFG-010: new default-true mgr_pool option gates mgr SQLite DB/open/create .mgr pool; affects mgr data migration and startup."),
    "src/common/options/mon.yaml.in": ("affect", "CFG-011", "CFG-011: default-true mon_warn_on_filestore_osds makes MON emit OSD_FILESTORE HEALTH_WARN when legacy FileStore OSDs remain."),
    "src/common/options/rbd-mirror.yaml.in": ("trivial", "", "T06-yaml-parity: 24 existing options migrate from C++; apparent PRIO_USEFUL defaults remain 5 at both endpoints; no new mirror default."),
    "src/common/options/rbd.yaml.in": ("trivial", "", "T06-optional-feature: existing defaults preserved; new rbd_qos_exclude_ops has no enabled default and needs explicit operator setting, with no demonstrated upgrade path effect."),
    "src/common/options/rgw.yaml.in": ("affect", "CFG-008", "CFG-008: FastCGI rgw_host/port/socket/backlog options disappear alongside rgw_fcgi_process.cc; conditional RGW frontend compatibility."),
}
with csv_path.open(encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert sum(row["path"] in review for row in rows) == len(review)
for row in rows:
    if row["path"] in review:
        assert not row["upgrade_impact"] or row["upgrade_impact"] == review[row["path"]][0]
        row["upgrade_impact"], row["finding_id"], row["impact_reason"] = review[row["path"]]
with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
