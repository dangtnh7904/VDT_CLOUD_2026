"""Classify the reviewed opt-in D3N RGW runtime and supporting doc rows."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
runtime_paths = {
    "src/rgw/rgw_aio.cc",
    "src/rgw/rgw_aio.h",
    "src/rgw/rgw_d3n_cacherequest.h",
    "src/rgw/rgw_d3n_datacache.cc",
    "src/rgw/rgw_d3n_datacache.h",
    "src/rgw/rgw_rados.h",
    "src/rgw/rgw_sal.cc",
}
doc_path = "doc/radosgw/d3n_datacache.rst"


def show(tag, path):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True, encoding="utf-8")


main = show("v17.2.7", "src/rgw/rgw_main.cc")
options = show("v17.2.7", "src/common/options/rgw.yaml.in")
sal = show("v17.2.7", "src/rgw/rgw_sal.cc")
cache = show("v17.2.7", "src/rgw/rgw_d3n_datacache.cc")
cache_h = show("v17.2.7", "src/rgw/rgw_d3n_datacache.h")
read = show("v17.2.7", "src/rgw/rgw_d3n_cacherequest.h")
rados = show("v17.2.7", "src/rgw/rgw_rados.cc")
aio = show("v17.2.7", "src/rgw/rgw_aio.cc")
doc = show("v17.2.7", doc_path)

assert "rgw_d3n_l1_local_datacache_enabled" not in show("v16.2.15", "src/rgw/rgw_main.cc")
assert "D3nRGWDataCache" not in show("v16.2.15", "src/rgw/rgw_sal.cc")
assert "if (rgw_d3n_datacache_enabled && (cct->_conf->rgw_max_chunk_size != cct->_conf->rgw_obj_stripe_size))" in main
assert "if (rgw_d3n_datacache_enabled && !cct->_conf->rgw_beast_enable_async)" in main
assert 'std::string rgw_store = (!rgw_d3n_datacache_enabled) ? "rados" : "d3n";' in main
assert "- name: rgw_d3n_l1_local_datacache_enabled\n  type: bool\n  level: advanced" in options
assert "default: false" in options[options.index("- name: rgw_d3n_l1_local_datacache_enabled"):][:200]
assert "- name: rgw_d3n_l1_evict_cache_on_start" in options
assert "default: true" in options[options.index("- name: rgw_d3n_l1_evict_cache_on_start"):][:200]
assert 'else if (svc.compare("d3n") == 0)' in sal
assert "new D3nRGWDataCache<RGWRados>" in sal
assert "d3n_data_cache->init(cct)" in rados
assert "efs::remove_all(p.path())" in cache
assert "catch (const efs::filesystem_error& e)" in cache
assert "D3nDataCache::get(const string& oid, const off_t len)" in cache
assert "st.st_size == len" in cache
assert "rgwrados->d3n_data_cache->put(bl, bl.length(), oid)" in rados
assert "if (read_ofs != 0 || astate->size != astate->accounted_size || is_compressed || is_encrypted)" in cache_h
assert "d->rgwrados->d3n_data_cache->get(oid, len)" in cache_h
assert "rgw::Aio::d3n_cache_op" in cache_h
assert "return d3n_cache_aio_abstract" in aio
assert "async_read(dpp, context" in read
assert "D3N will be disabled if" in doc
assert "each time the Rados Gateway is restarted" in doc
assert "rgw_d3n_datacache.cc" in show("v17.2.7", "src/rgw/CMakeLists.txt")

path = root / "12-rgw.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for source in runtime_paths | {doc_path}:
    row = by_path[source]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], source
    if source == doc_path:
        row.update(
            upgrade_impact="trivial", finding_id="RGW-018",
            impact_reason="RGW-018 support: Documentation describes opt-in D3N requirements, cache directory and restart purge; it is not an executed upgrade recipe or validation gate.")
    else:
        row.update(
            upgrade_impact="affect", finding_id="RGW-018",
            impact_reason="RGW-018: Opt-in Quincy D3N backend adds local tail-object read/write AIO and startup cache-directory eviction; it can change RGW restart, disk I/O and read results when enabled during rollout.")

with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(runtime_paths)} D3N runtime rows affect and one supporting doc row trivial")
