"""Classify reviewed RGW QA branch selection and D3N cache validation rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"

branch_paths = {
    "qa/suites/rgw/crypt/4-tests/s3tests.yaml",
    "qa/suites/rgw/multifs/tasks/rgw_ragweed.yaml",
    "qa/suites/rgw/multifs/tasks/rgw_s3tests.yaml",
    "qa/suites/rgw/sts/tasks/first.yaml",
    "qa/suites/rgw/sts/tasks/ststests.yaml",
    "qa/suites/rgw/thrash/workload/rgw_s3tests.yaml",
    "qa/suites/rgw/verify/tasks/ragweed.yaml",
    "qa/suites/rgw/verify/tasks/s3tests-java.yaml",
    "qa/suites/rgw/verify/tasks/s3tests.yaml",
    "qa/suites/rgw/website/tasks/s3tests-website.yaml",
}
cache_paths = {
    "qa/suites/rgw/verify/0-install.yaml",
    "qa/suites/rgw/verify/datacache/no_datacache.yaml",
    "qa/suites/rgw/verify/datacache/rgw-datacache.yaml",
    "qa/workunits/rgw/run-datacache.sh",
    "qa/workunits/rgw/test_rgw_datacache.py",
}


def show(tag, path):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True, encoding="utf-8")


def changed_lines(path):
    diff = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "-U0", "v16.2.15", "v17.2.7", "--", path],
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


for path in branch_paths:
    old, new = changed_lines(path)
    assert len(old) == len(new) == (2 if path.endswith("multifs/tasks/rgw_ragweed.yaml") else 1), path
    assert all("ceph-pacific" in line for line in old), path
    assert [line.replace("ceph-pacific", "ceph-quincy") for line in old] == new, path

s3_task = show("v17.2.7", "qa/tasks/s3tests.py")
ragweed_task = show("v17.2.7", "qa/tasks/ragweed.py")
java_task = show("v17.2.7", "qa/tasks/s3tests_java.py")
assert "s3tests_branch = client_config.get('force-branch', None)" in s3_task
assert "'git', 'clone'," in s3_task and "'-b', s3tests_branch," in s3_task
assert "default_branch = client_conf.get('default-branch', None)" in ragweed_task
assert "return [branch, default_branch]" in ragweed_task
assert "'-b', branch," in java_task and "branch = self.config[client]['force-branch']" in java_task

cache_recipe = show("v17.2.7", "qa/suites/rgw/verify/datacache/rgw-datacache.yaml")
cache_test = show("v17.2.7", "qa/workunits/rgw/test_rgw_datacache.py")
cache_runner = show("v17.2.7", "qa/workunits/rgw/run-datacache.sh")
install = show("v17.2.7", "qa/suites/rgw/verify/0-install.yaml")
assert "rgw d3n l1 local datacache enabled: true" in cache_recipe
assert "rgw/run-datacache.sh" in cache_recipe
assert "RGW_DATACACHE_PATH: /tmp/rgw_datacache" in cache_recipe
assert "pip install configobj" in cache_runner and "test_rgw_datacache.py" in cache_runner
assert "deb: ['s3cmd']" in install and "rpm: ['s3cmd']" in install
assert "if chk_cache_dir == 0:" in cache_test
assert "datacache test object not found" in cache_test
assert "if chk_cache_dir == 0:\n        log.info(" in cache_test
assert "        return\n\n    # list the files" in cache_test
assert "assert(basename_cmd_out in rados_ls_out)" in cache_test
assert show("v17.2.7", "qa/suites/rgw/verify/datacache/no_datacache.yaml") == ""

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for source in branch_paths | cache_paths:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source in branch_paths:
        row.update(
            upgrade_impact="affect", finding_id="RGW-014",
            impact_reason="RGW-014: Selected RGW QA recipe changes external s3tests/java_s3tests clone branch or ragweed fallback from ceph-pacific to ceph-quincy; this changes possible acceptance coverage and is not pinned to these two tag SHAs.")
    else:
        row.update(
            upgrade_impact="affect", finding_id="RGW-015",
            impact_reason="RGW-015: Selected rgw/verify QA matrix gains a D3N cache variant, install dependencies and workunit; the test returns success when the cache directory is empty, so its pass alone cannot prove caching worked.")

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(branch_paths)} RGW QA branch rows and {len(cache_paths)} D3N QA rows affect")
