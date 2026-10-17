"""Classify CORS CR formatting regression and exact RGW type-only diffs."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
trivial_paths = {
    "src/rgw/rgw_compression.h",
    "src/rgw/rgw_cors.h",
    "src/rgw/rgw_etag_verifier.cc",
    "src/rgw/rgw_etag_verifier.h",
}
cors_path = "src/rgw/rgw_cors.cc"


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
            old.append(line[1:].strip())
        if line.startswith("+") and line[1:].strip():
            new.append(line[1:].strip())
    return old, new


for source in trivial_paths:
    old, new = changed_lines(source)
    if source.endswith("rgw_etag_verifier.cc"):
        assert old == ["CephContext* cct, DataProcessor* filter,"]
        assert new == ['#include "rgw_obj_manifest.h"', "CephContext* cct, rgw::sal::DataProcessor* filter,"]
    elif source.endswith("rgw_etag_verifier.h"):
        assert len(old) == len(new) == 6
        for before, after in zip(old, new):
            transformed = before.replace("rgw::putobj::DataProcessor", "rgw::sal::DataProcessor")
            transformed = transformed.replace("CephContext* cct, DataProcessor* next", "CephContext* cct, rgw::sal::DataProcessor* next")
            transformed = transformed.replace("string calculated_etag", "std::string calculated_etag")
            transformed = transformed.replace("string get_calculated_etag", "std::string get_calculated_etag")
            assert transformed == after, (source, before, after)
    elif source.endswith("rgw_compression.h"):
        assert len(old) == len(new) == 4
        for before, after in zip(old, new):
            transformed = before.replace("map<string, bufferlist>", "std::map<std::string, bufferlist>")
            transformed = transformed.replace("vector<compression_block>", "std::vector<compression_block>")
            transformed = transformed.replace("rgw::putobj::DataProcessor", "rgw::sal::DataProcessor")
            assert transformed == after, (source, before, after)
    else:
        assert source.endswith("rgw_cors.h")
        assert len(old) == len(new) == 7
        for before, after in zip(old, new):
            assert before.replace("<string>", "<std::string>").rstrip() == after.rstrip(), (source, before, after)

old_cors = show("v16.2.15", cors_path)
new_cors = show("v17.2.7", cors_path)
assert 'boost::replace_all_copy(std::back_inserter(s), tmp, "\\r", "\\\\r");' in old_cors
assert 'boost::replace_all_copy(std::back_inserter(s), header, "\\n", "\\\\n");' in new_cors
assert 'boost::replace_all_copy(std::back_inserter(s), tmp, "\\r", "\\\\r");' not in new_cors
assert "exposable_hdrs.push_back(obj->get_data());" in show("v17.2.7", "src/rgw/rgw_cors_s3.cc")
assert "rule->format_exp_headers(exp_hdrs);" in show("v17.2.7", "src/rgw/rgw_op.cc")
assert 'dump_header(s, "Access-Control-Expose-Headers", exp_hdr);' in show("v17.2.7", "src/rgw/rgw_rest.cc")
assert "sent += txbuf.sputn(value.data(), value.length());" in show("v17.2.7", "src/rgw/rgw_asio_client.cc")

def ancestor(commit, tag):
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag]).returncode == 0


assert ancestor("4f078710d393", "v16.2.15")
assert not ancestor("4f078710d393", "v17.2.7")

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in trivial_paths | {cors_path}:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source == cors_path:
        row.update(
            upgrade_impact="affect", finding_id="RGW-020",
            impact_reason="RGW-020: Pacific escapes CR in configured CORS ExposeHeader before Access-Control-Expose-Headers; Quincy endpoint omits that escape, so response bytes can differ on a CORS request with CR-bearing metadata.")
    else:
        row.update(
            upgrade_impact="trivial", finding_id="",
            impact_reason="RGW-TYPE-02: Exact endpoint hunk only adds an include, qualifies standard types, or follows the putobj-to-SAL DataProcessor type move; processing, data encoding and test acceptance logic are unchanged.")

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified one CORS runtime row affect and {len(trivial_paths)} exact type-only rows trivial")
