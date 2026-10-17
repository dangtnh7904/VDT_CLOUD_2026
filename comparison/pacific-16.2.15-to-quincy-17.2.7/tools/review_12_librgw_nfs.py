"""Classify the librgw/RGW-NFS endpoint delta and its LDAP failure path."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


base_file_h = show("v16.2.15", "src/rgw/rgw_file.h")
target_file_h = show("v17.2.7", "src/rgw/rgw_file.h")
target_sal = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")

# Pacific's LDAP fallback performs its uid lookup through a value object. The
# Quincy endpoint changes that member to a unique_ptr and dereferences it in the
# same fallback after get_user_by_access_key() has failed.
assert "RGWUserInfo user;" in base_file_h
assert "std::unique_ptr<rgw::sal::User> user;" in target_file_h
assert "get_info_by_uid(dpp, rgw_user(token.id), &user, null_yield)" in base_file_h
assert "if (user->load_user(dpp, null_yield) < 0)" in target_file_h

# RadosStore only resets the output pointer after a successful backend lookup.
# On the failure branch that activates LDAP, a newly constructed RGWLibFS still
# has a null user pointer, so valid LDAP credentials can reach a null dereference.
lookup_start = target_sal.index("int RadosStore::get_user_by_access_key")
lookup_end = target_sal.index("int RadosStore::get_user_by_email", lookup_start)
lookup = target_sal[lookup_start:lookup_end]
assert lookup.index("if (r < 0)") < lookup.index("user->reset(u);")
assert "if (r < 0)\n    return r;" in lookup
assert "user->reset(u);" in lookup

ctor_start = target_file_h.index("RGWLibFS(CephContext*")
ctor_end = target_file_h.index("/* pointer to self */", ctor_start)
ctor = target_file_h[ctor_start:ctor_end]
assert "user(" not in ctor and "user{" not in ctor

# The non-LDAP parts of rgw_file are Zipper/SAL ownership adapters. In
# particular, Quincy's Writer delegates to the same AtomicObjectProcessor and
# the copy operation moves src_object ownership into req_state, which is where
# Quincy's RGWCopyObj consumes it.
base_file = show("v16.2.15", "src/rgw/rgw_file.cc")
target_file = show("v17.2.7", "src/rgw/rgw_file.cc")
target_op = show("v17.2.7", "src/rgw/rgw_op.cc")
target_sal_h = show("v17.2.7", "src/rgw/rgw_sal_rados.h")
assert "std::optional<rgw::putobj::AtomicObjectProcessor> processor;" in base_file_h
assert "std::unique_ptr<rgw::sal::Writer> processor;" in target_file_h
assert "rgw::putobj::AtomicObjectProcessor processor;" in target_sal_h
assert "return processor.prepare(y);" in target_sal
assert "return processor.process(std::move(data), offset);" in target_sal
assert "src_object = rgwlib.get_store()->get_object(k);" in base_file_h
assert "s->src_object = s->bucket->get_object(k);" in target_file_h
assert "s->src_object->copy_object(obj_ctx," in target_op
assert "rgwlib.get_store()->get_user(user.user_id)" in base_file
assert "user->clone()" in target_file

# librgw remains explicitly backed by RADOS and maps the same uid into the same
# RGWUserInfo; the surrounding changes are SAL/DPP/API adapters.
base_librgw = show("v16.2.15", "src/rgw/librgw.cc")
target_librgw = show("v17.2.7", "src/rgw/librgw.cc")
assert "RGWStoreManager::get_storage(this, g_ceph_context," in base_librgw
assert 'StoreManager::get_storage(this, g_ceph_context,\n\t\t\t\t\t "rados",' in target_librgw
assert "get_info_by_uid(&dp, uid, &user_info, null_yield)" in base_librgw
assert "std::unique_ptr<rgw::sal::User> user = store->get_user(uid);" in target_librgw
assert "user_info = user->get_info();" in target_librgw

# The documentation delta only corrects spelling/config-section examples, and
# all seven tests retain their TEST bodies while adopting the returned-vector
# argv_to_vec API (plus one unused annotation).
base_doc = show("v16.2.15", "doc/radosgw/nfs.rst")
target_doc = show("v17.2.7", "doc/radosgw/nfs.rst")
assert "embeddding" in base_doc and "embeddding" not in target_doc
assert "[client.radosgw.{instance-name}]" in base_doc
assert "[client.rgw.{instance-name}]" in target_doc

tests = (
    "src/test/librgw_file.cc",
    "src/test/librgw_file_aw.cc",
    "src/test/librgw_file_cd.cc",
    "src/test/librgw_file_gp.cc",
    "src/test/librgw_file_marker.cc",
    "src/test/librgw_file_nfsns.cc",
    "src/test/librgw_file_xattr.cc",
)
for path in tests:
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert base.count("TEST(") == target.count("TEST("), path
    assert "argv_to_vec(argc, const_cast<const char**>(argv), args);" in base, path
    assert "auto args = argv_to_vec(argc, argv);" in target, path


updates = {
    "src/rgw/rgw_file.h": (
        "affect",
        "RGW-031",
        "RGW-031: In the RGW-NFS LDAP fallback, Quincy dereferences the SAL user pointer after an access-key lookup failure even though RadosStore only assigns that pointer on success; a valid LDAP token can therefore reach a null dereference instead of Pacific's value-object uid lookup.",
    ),
    "doc/radosgw/nfs.rst": (
        "trivial",
        "",
        "RGW-NFS-DOC-01: Corrects spelling and RGW ceph.conf section names in narrative examples; no executable daemon, mount recipe, or validation gate changes in this endpoint row.",
    ),
    "src/rgw/librgw.cc": (
        "trivial",
        "",
        "RGW-NFS-SAL-01: Keeps librgw on the RADOS backend and maps the same uid/user info while adapting storage, zone, service-map, logging, DPP and argv APIs to SAL/Zipper.",
    ),
    "src/rgw/rgw_file.cc": (
        "trivial",
        "",
        "RGW-NFS-SAL-02: Clones the same authenticated user and routes writes through the RADOS SAL Writer, which delegates to the same AtomicObjectProcessor; request operations and file semantics are unchanged in this source row.",
    ),
}
for path in tests:
    updates[path] = (
        "trivial",
        "",
        "RGW-NFS-TEST-01: Retains the same librgw TEST cases and expectations while adopting the returned-vector argv_to_vec API, namespace qualification, and warning cleanup.",
    )

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for path, (impact, finding, reason) in updates.items():
    row = by_path[path]
    assert not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"], path
    row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified one RGW-NFS LDAP row affect and ten librgw/NFS adapter rows trivial")
