"""Classify torrent OMAP target change and exact declaration-only RGW rows."""

import csv
import re
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
torrent = "src/rgw/rgw_torrent.cc"
trivial = {
    "src/rgw/rgw_torrent.h",
    "src/rgw/rgw_gc.h",
    "src/rgw/rgw_period_pusher.h",
}


def show(tag, source):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{source}"],
        text=True, encoding="utf-8")


def changed_lines(source):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", source],
        text=True, encoding="utf-8")
    old, new = [], []
    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("-") and line[1:].strip():
            old.append(line[1:])
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:])
    return old, new


for source in trivial:
    old, new = changed_lines(source)
    if source.endswith("rgw_torrent.h"):
        assert '#include "rgw_rados.h"' in old
        old.remove('#include "rgw_rados.h"')
    assert len(old) == len(new) and len(old) >= 4, source
    for before, after in zip(old, new):
        transformed = before.replace("rgw::sal::RGWRadosStore", "rgw::sal::Store")
        transformed = transformed.replace("rgw::sal::RGWObject", "rgw::sal::Object")
        transformed = transformed.replace("RGWRadosStore", "Store")
        transformed = re.sub(r"(?<![:\w])string\b", "std::string", transformed)
        transformed = re.sub(r"(?<![:\w])vector\b", "std::vector", transformed)
        assert transformed != before, (source, before)
        assert re.sub(r"\s+", "", transformed) == re.sub(r"\s+", "", after), (
            source, before, after)

old_torrent = show("v16.2.15", torrent)
new_torrent = show("v17.2.7", torrent)
assert "rgw_obj obj(s->bucket->get_key(), s->object->get_name());" in old_torrent
assert "store->getRados()->obj_to_raw(s->bucket->get_info().placement_rule, obj, &raw_obj);" in old_torrent
assert "op_ret = sysobj.omap().set(s, key, bl, y);" in old_torrent
assert "op_ret = s->object->omap_set_val_by_key(s, key, bl, false, y);" in new_torrent
rados_obj = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
assert "int RadosObject::omap_set_val_by_key" in rados_obj
assert "rgw_obj obj = get_obj();" in rados_obj
assert "store->getRados()->obj_to_raw(bucket->get_placement_rule(), obj, &raw_meta_obj);" in rados_obj
sal = show("v17.2.7", "src/rgw/rgw_sal.h")
assert "rgw_obj obj(bucket->get_key(), key);" in sal
op = show("v17.2.7", "src/rgw/rgw_op.cc")
assert "s->object->set_instance(version_id);" in op
assert "s->object->gen_rand_obj_instance_name();" in op
assert "torrent.complete(y);" in op
assert "torrent.get_torrent_file(s->object.get(), total_len, bl, obj);" in op
assert "default: false" in show("v17.2.7", "src/common/options/rgw.yaml.in").split("- name: rgw_torrent_flag", 1)[1].split("- name:", 1)[0]

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in trivial | {torrent}:
    row = by_path[source]
    assert row["status"] == "M" and not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source == torrent:
        row.update(
            upgrade_impact="affect", finding_id="RGW-023",
            impact_reason="RGW-023: Torrent OMAP write now uses the request Object's full key through SAL instead of reconstructing a name-only rgw_obj; with versioning and rgw_torrent_flag, the raw metadata target can differ.")
    else:
        row.update(
            upgrade_impact="trivial", finding_id="",
            impact_reason="RGW-TYPE-04: Exact endpoint hunk only removes an unused direct include or qualifies standard types/follows the SAL Store/Object declaration rename; no processing or wire logic in this file.")
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
print("Classified one torrent runtime row affect and three exact declaration-only rows trivial")
