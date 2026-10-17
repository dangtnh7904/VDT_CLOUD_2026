"""Verify and classify the final RGW runtime/support inventory batch."""

import csv
import re
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


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


def section(source: str, start: str, end: str | None = None) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) if end else len(source)
    return source[begin:finish]


target_only_commits = {
    "sync_policy_params": "04691a82c91b7719890e846a9b8cbb98db98af05",
    "data_sync_cleanup": "be9c8bc96b57205ceafca6fd02e51f02128419c3",
    "inline_data": "ae1c2689cda6a19b4540fc3e2530f5b364cd7d4f",
    "compression_hint": "edde516a26cedc705af793501e86ad3f1094ca5c",
    "sigv4_body": "0214b4a7afb8921e85517f4ad980f66c2957af3a",
    "sigv4_region": "81ad2261280ef54a5b8335adba9481a139a51ba3",
    "multipart_alias": "6380481f0538f0b0655f0a1c1c05db623447ec03",
    "raw_oid": "267bcb767dff0cf845968b8b9472730c9a19ed75",
    "swift_names": "bf8e5503191496fbe1284e108cd1da0eff9f830e",
}
for commit in target_only_commits.values():
    assert not is_ancestor(commit, "v16.2.15"), commit
    assert is_ancestor(commit, "v17.2.7"), commit

# Policy selection now records the first same-priority rule before comparing
# later rules. Pacific's ++i == 0 branch is unreachable and leaves mode
# uninitialized, so non-default/common parameters can force a remote stat or
# be returned from undefined state.
base_bucket_sync = show("v16.2.15", "src/rgw/rgw_bucket_sync.cc")
target_bucket_sync = show("v17.2.7", "src/rgw/rgw_bucket_sync.cc")
base_basic = section(
    base_bucket_sync,
    "bool RGWBucketSyncFlowManager::pipe_rules::find_basic_info_without_tags(",
    "bool RGWBucketSyncFlowManager::pipe_rules::find_obj_params(",
)
target_basic = section(
    target_bucket_sync,
    "bool RGWBucketSyncFlowManager::pipe_rules::find_basic_info_without_tags(",
    "bool RGWBucketSyncFlowManager::pipe_rules::find_obj_params(",
)
assert "if (++i == 0)" in base_basic
assert "rgw_sync_pipe_params::Mode _mode;" in base_basic
assert "bool first_iter = true" in target_basic
assert "Mode _mode{rgw_sync_pipe_params::Mode::MODE_SYSTEM}" in target_basic

# Both endpoints retain the same 20-child data-sync window through different
# release-branch backports. Quincy additionally removes the temporary full-sync
# index after persisting the transition to incremental sync.
base_data_sync = show("v16.2.15", "src/rgw/rgw_data_sync.cc")
target_data_sync = show("v17.2.7", "src/rgw/rgw_data_sync.cc")
assert base_data_sync.count("yield_spawn_window(sync_single_entry(") >= 2
assert target_data_sync.count("yield_spawn_window(sync_single_entry(") >= 2
assert "BUCKET_SHARD_SYNC_SPAWN_WINDOW 20" in base_data_sync
assert "BUCKET_SHARD_SYNC_SPAWN_WINDOW 20" in target_data_sync
assert is_ancestor("0fcda11d74db1f1e16da2c5e7e0611967a7e235c", "v16.2.15")
assert not is_ancestor("0fcda11d74db1f1e16da2c5e7e0611967a7e235c", "v17.2.7")
assert not is_ancestor("6aa1a283af585fa89dad57b53c9cf581362bb0b5", "v16.2.15")
assert is_ancestor("6aa1a283af585fa89dad57b53c9cf581362bb0b5", "v17.2.7")
assert "// clean up full sync index" not in base_data_sync
assert "// clean up full sync index" in target_data_sync

# Both endpoints check BucketShard::init() before bilog trimming through
# release-specific backports. The remaining net diff is SAL/DPP/namespace
# maintenance, so this is endpoint parity rather than an upgrade finding.
base_cr_rados = show("v16.2.15", "src/rgw/rgw_cr_rados.cc")
target_cr_rados = show("v17.2.7", "src/rgw/rgw_cr_rados.cc")
base_trim = section(base_cr_rados, "RGWRadosBILogTrimCR::RGWRadosBILogTrimCR(", "int RGWAsyncFetchRemoteObj::_send_request")
target_trim = section(target_cr_rados, "RGWRadosBILogTrimCR::RGWRadosBILogTrimCR(", "int RGWAsyncFetchRemoteObj::_send_request")
assert "bs.init(dpp, bucket_info" in base_trim
assert "int r = bs.init(dpp, bucket_info" in base_trim
assert "bucket shard init failed" in base_trim
assert "int r = bs.init(dpp, bucket_info" in target_trim
assert "bucket shard init failed" in target_trim
assert is_ancestor("b15e2c3c7a02de5b10d9e7521140af64d87bf853", "v16.2.15")
assert not is_ancestor("b15e2c3c7a02de5b10d9e7521140af64d87bf853", "v17.2.7")
assert not is_ancestor("ad3e390e0dc275abdbff07876418ce2e98ca9997", "v16.2.15")
assert is_ancestor("ad3e390e0dc275abdbff07876418ce2e98ca9997", "v17.2.7")

# inline_data is a placement-schema v8 field, defaults true for backward
# compatibility, and only changes the head chunk when explicitly false.
base_zone_h = show("v16.2.15", "src/rgw/rgw_zone.h")
target_zone_h = show("v17.2.7", "src/rgw/rgw_zone.h")
base_put = show("v16.2.15", "src/rgw/rgw_putobj_processor.cc")
target_put = show("v17.2.7", "src/rgw/rgw_putobj_processor.cc")
assert "bool inline_data" not in base_zone_h
assert "bool inline_data" in target_zone_h
assert "ENCODE_START(8, 1, bl)" in target_zone_h
assert "placement_info.inline_data" not in base_put
assert "placement_info.inline_data" in target_put

# Quincy's writer marks RGW-compressed tail writes incompressible to the OSD.
# The ETIMEDOUT tail-cleanup safeguard and multipart random-name fix are
# endpoint parity through different release-branch backports, so they are not
# separate findings in this comparison.
assert "ALLOC_HINT_FLAG_INCOMPRESSIBLE" not in base_put
assert "ALLOC_HINT_FLAG_INCOMPRESSIBLE" in target_put
for source in (base_put, target_put):
    assert "if (r == -ETIMEDOUT)" in source
    assert "writer.clear_written();" in source
    assert "gen_rand_alphanumeric(store->ctx(), 32)" in source

# The new RGWOp wrappers call SigV4 completion but discard its failure return.
# read_all_input also omits allow_chunked when forwarding to the body reader,
# so calls that passed false change from LengthRequired to accepting chunked.
base_op_h = show("v16.2.15", "src/rgw/rgw_op.h")
target_op_h = show("v17.2.7", "src/rgw/rgw_op.h")
assert "std::tuple<int, bufferlist> read_all_input(" not in base_op_h
target_read_all = section(target_op_h, "std::tuple<int, bufferlist> read_all_input(", "template <class T>")
assert "const bool allow_chunked=true" in target_read_all
assert "rgw_rest_read_all_input(s, max_len);" in target_read_all
assert "rgw_rest_read_all_input(s, max_len, allow_chunked)" not in target_read_all
target_json_input = section(
    target_op_h, "int get_json_input(", "  public:"
)
for wrapper in (target_read_all, target_json_input):
    assert "      do_aws4_auth_completion();" in wrapper
    assert "= do_aws4_auth_completion()" not in wrapper
target_auth_completion = section(
    show("v17.2.7", "src/rgw/rgw_op.cc"),
    "int RGWOp::do_aws4_auth_completion()",
    "int RGWOp::init_quota()",
)
assert "return -ERR_AMZ_CONTENT_SHA256_MISMATCH;" in target_auth_completion
assert "op_ret =" not in target_auth_completion
target_op_types = show("v17.2.7", "src/rgw/rgw_op_type.h")
for token in ("RGW_OP_SYNC_DATALOG_NOTIFY", "RGW_OP_SYNC_MDLOG_NOTIFY", "RGW_OP_PERIOD_POST"):
    assert token not in show("v16.2.15", "src/rgw/rgw_op_type.h")
    assert token in target_op_types

# SigV4 callers now carry an explicit zonegroup/config region. Regionless
# endpoints still use hostname/config fallback, so activation is conditional
# on signed outbound requests and their configured endpoint names.
base_aws = show("v16.2.15", "src/rgw/rgw_sync_module_aws.cc")
target_aws = show("v17.2.7", "src/rgw/rgw_sync_module_aws.cc")
assert "std::optional<string> region" not in base_aws
assert "std::optional<string> region" in target_aws
assert "root_conf->region" in target_aws
base_pusher = show("v16.2.15", "src/rgw/rgw_period_pusher.cc")
target_pusher = show("v17.2.7", "src/rgw/rgw_period_pusher.cc")
assert "zonegroup.endpoints, zonegroup.api_name" not in base_pusher
assert "zonegroup.endpoints, zonegroup.api_name" in target_pusher

# Both endpoints already emit an unprefixed S3-compatible eventName through
# release-specific backports. CompletedMultipartUpload becomes an accepted XML
# alias for clients that send the non-standard root element only in Quincy.
base_pubsub = show("v16.2.15", "src/rgw/rgw_sync_module_pubsub.cc")
target_pubsub = show("v17.2.7", "src/rgw/rgw_sync_module_pubsub.cc")
assert "e->eventName = rgw::notify::to_event_string(event_type);" in base_pubsub
assert "e->eventName = rgw::notify::to_event_string(event_type);" in target_pubsub
assert is_ancestor("cb4f077d231", "v16.2.15")
assert not is_ancestor("cb4f077d231", "v17.2.7")
assert not is_ancestor("893ce6b64a6138cea9428803a13d287c05a93244", "v16.2.15")
assert is_ancestor("893ce6b64a6138cea9428803a13d287c05a93244", "v17.2.7")
base_multi = show("v16.2.15", "src/rgw/rgw_multi.cc")
target_multi = show("v17.2.7", "src/rgw/rgw_multi.cc")
assert 'strcmp(el, "CompletedMultipartUpload")' not in base_multi
assert 'strcmp(el, "CompletedMultipartUpload")' in target_multi
assert 'find_first("CompletedMultipartUpload")' not in show("v16.2.15", "src/rgw/rgw_op.cc")
assert 'find_first("CompletedMultipartUpload")' in show("v17.2.7", "src/rgw/rgw_op.cc")

# The raw-object decoder must skip underscores inside the bucket marker. Swift
# independently drops the common minimum-three-byte name check, retaining its
# own maximum length, leading-dot, UTF-8, 0xff and slash checks.
base_tier = show("v16.2.15", "src/rgw/services/svc_tier_rados.h")
target_tier = show("v17.2.7", "src/rgw/services/svc_tier_rados.h")
assert "raw_obj.oid.find('_');" in base_tier
assert "raw_obj.oid.find('_', bucket.marker.length())" in target_tier
base_swift = show("v16.2.15", "src/rgw/rgw_rest_swift.cc")
target_swift = show("v17.2.7", "src/rgw/rgw_rest_swift.cc")
base_validate = section(base_swift, "int RGWHandler_REST_SWIFT::validate_bucket_name(", "static void next_tok")
target_validate = section(target_swift, "int RGWHandler_REST_SWIFT::validate_bucket_name(", "static void next_tok")
assert "RGWHandler_REST::validate_bucket_name(bucket)" in base_validate
assert "RGWHandler_REST::validate_bucket_name(bucket)" not in target_validate
base_common_validate = section(
    show("v16.2.15", "src/rgw/rgw_rest.cc"),
    "int RGWHandler_REST::validate_bucket_name(",
    "int RGWHandler_REST::validate_object_name(",
)
assert "if (len < 3)" in base_common_validate
assert "len < 3" not in target_validate
for token in ("MAX_BUCKET_NAME_LEN", "bucket[0] == '.'", "check_utf8", "== '/'"):
    assert token in target_validate

# DBStore is new, built by default but selected only by an explicit backend
# configuration. It is documented as experimental and has its own SQLite data,
# so it is not a transparent migration target for an existing RADOS RGW.
target_root_cmake = show("v17.2.7", "CMakeLists.txt")
target_rgw_cmake = show("v17.2.7", "src/rgw/CMakeLists.txt")
target_main = show("v17.2.7", "src/rgw/rgw_main.cc")
target_db_readme = show("v17.2.7", "src/rgw/store/dbstore/README.md")
assert 'option(WITH_RADOSGW_DBSTORE "DBStore backend for Rados Gateway" ON)' in target_root_cmake
assert "add_subdirectory(store/dbstore)" in target_rgw_cmake
assert 'config_store == "dbstore"' in target_main
assert "Standalone Rados Gateway (RGW) on DBStore (Experimental)" in target_db_readme
assert "rgw backend store = dbstore" in target_db_readme

# Cluster FSID backs the already-documented /info response. The new rgwam.py
# file is a standalone source-tree wrapper with no CMake/install reference;
# manager/core behavior is inventoried by its respective owners.
base_svc_rados = show("v16.2.15", "src/rgw/services/svc_rados.cc")
target_svc_rados = show("v17.2.7", "src/rgw/services/svc_rados.cc")
assert "RGWSI_RADOS::cluster_fsid()" not in base_svc_rados
assert "RGWSI_RADOS::cluster_fsid()" in target_svc_rados
assert not is_ancestor("cfe546991a5f6529a23a55110a19b824f3a49655", "v16.2.15")
assert is_ancestor("cfe546991a5f6529a23a55110a19b824f3a49655", "v17.2.7")
assert "rgwam.py" not in target_root_cmake
assert "rgwam.py" not in target_rgw_cmake


new_rows = {
    "src/rgw/rgw_bucket_sync.cc": (
        "affect", "RGW-050",
        "RGW-050: Fixes first-rule initialization and same-priority conflict detection for bucket sync policy parameters; Pacific compares against empty/uninitialized state and can force extra source stat calls or return an undefined mode.",
    ),
    "src/rgw/rgw_bucket_sync.h": (
        "trivial", "RGW-050",
        "RGW-050 support: Header changes only thread DoutPrefixProvider through policy-map initialization/reflection and qualify existing STL types; rule selection is changed in rgw_bucket_sync.cc.",
    ),
    "src/rgw/rgw_coroutine.h": (
        "trivial", "RGW-051",
        "RGW-051 support: The yield_spawn_window macro and 20-child data-sync use are identical at both endpoints through different backports; this header only qualifies STL types, moves an existing destructor body, and accepts an unused admin-socket input buffer.",
    ),
    "src/rgw/rgw_cr_rados.cc": (
        "trivial", "",
        "RGW-BILOG-PARITY-01: Both endpoints check BucketShard::init() before bilog trim through release-specific backports; the remaining net diff is SAL rename, DoutPrefixProvider plumbing and a diagnostic typo fix.",
    ),
    "src/rgw/rgw_cr_rados.h": (
        "trivial", "",
        "RGW-BILOG-PARITY-01: Both endpoints already retain bucket_info and shard_id for checked initialization in send_request(); header net diff is SAL and namespace maintenance.",
    ),
    "src/rgw/rgw_cr_rest.cc": (
        "trivial", "",
        "RGW-COROUTINE-DPP-02: Threads DoutPrefixProvider into the same REST stream decode/read path and otherwise preserves buffering, retry, splice, and HTTP coroutine behavior.",
    ),
    "src/rgw/rgw_cr_rest.h": (
        "trivial", "",
        "RGW-COROUTINE-DPP-02: Qualifies existing string/map declarations and adds DoutPrefixProvider parameters consumed only for logging; no request format, retry rule, or stream limit changes.",
    ),
    "src/rgw/rgw_cr_tools.cc": (
        "trivial", "RGW-060",
        "RGW-060 support: Re-expresses user, bucket and lifecycle coroutine helpers through equivalent SAL objects so alternate stores can implement them; the RADOS endpoint behavior is unchanged here.",
    ),
    "src/rgw/rgw_cr_tools.h": (
        "trivial", "RGW-060",
        "RGW-060 support: Replaces copied bucket fields with a SAL Bucket pointer and qualifies types; it does not itself add a backend or change wire/persistence behavior.",
    ),
    "src/rgw/rgw_data_sync.cc": (
        "affect", "RGW-051",
        "RGW-051: Removes the temporary full-data-sync index after the incremental marker is persisted; the 20-child spawn window already exists at both endpoints through release-specific backports.",
    ),
    "src/rgw/rgw_data_sync.h": (
        "trivial", "RGW-051",
        "RGW-051 support: Header net diff is SAL rename, STL qualification and moved dump/test-instance declarations; the target-only index cleanup is implemented in rgw_data_sync.cc.",
    ),
    "src/rgw/rgw_lib.h": (
        "trivial", "",
        "RGW-LIB-SAL-02: Converts librgw request declarations from the concrete RADOS SAL to the common Store interface and removes duplicate sysobj context state; no standalone protocol or upgrade behavior originates in this header.",
    ),
    "src/rgw/rgw_mdlog.h": (
        "trivial", "",
        "RGW-MDLOG-MAINT-02: Removes an unused RWLock include, qualifies STL names and threads DoutPrefixProvider for logging while preserving mdlog shard/marker interfaces.",
    ),
    "src/rgw/rgw_metadata.cc": (
        "trivial", "RGW-030",
        "RGW-030 support: Moves obj_version and RGWMetadataLogInfo JSON helpers into their owning source and passes DoutPrefixProvider through listing; encoded fields and listing semantics are unchanged.",
    ),
    "src/rgw/rgw_metadata.h": (
        "trivial", "RGW-030",
        "RGW-030 support: Adds a base constructor used by the new role metadata object and qualifies/list-logging signatures; role synchronization behavior is owned by RGW-030 runtime rows.",
    ),
    "src/rgw/rgw_multi.cc": (
        "affect", "RGW-058",
        "RGW-058: Accepts the non-standard CompletedMultipartUpload XML root and looks it up during complete-MPU parsing, whereas Pacific returns MalformedXML for that client payload.",
    ),
    "src/rgw/rgw_multi.h": (
        "trivial", "RGW-058",
        "RGW-058 support: Header changes only move multipart ownership through SAL, qualify types and relocate a destructor; the accepted XML alias is implemented in rgw_multi.cc/rgw_op.cc.",
    ),
    "src/rgw/rgw_period_pusher.cc": (
        "affect", "RGW-055",
        "RGW-055: Supplies zonegroup api_name as the SigV4 region when the master pushes a period to zonegroup/zone endpoints, avoiding hostname/config fallback for non-AWS endpoint names.",
    ),
    "src/rgw/rgw_putobj_processor.cc": (
        "affect", "RGW-053,RGW-054",
        "RGW-053: Honors placement inline_data=false by setting head chunk size to zero and placing all object data in tail stripes. RGW-054: Marks RGW-compressed RADOS writes incompressible so OSD compression is bypassed; timeout and multipart-name fixes have endpoint parity through separate backports.",
    ),
    "src/rgw/rgw_putobj_processor.h": (
        "affect", "RGW-054",
        "RGW-054: Declares the per-write allocation-hint hook used by RadosWriter to mark RGW-compressed tail data incompressible to OSD.",
    ),
    "src/rgw/rgw_rest.h": (
        "affect", "RGW-056",
        "RGW-056: Converted all-body readers use RGWOp wrappers that call SigV4 completion but discard its failure return; read_all_input also fails to forward allow_chunked=false, widening accepted transfer framing.",
    ),
    "src/rgw/rgw_rest_bucket.cc": (
        "affect", "RGW-056",
        "RGW-056: Bucket admin JSON/body reads use wrappers that call SigV4 completion but ignore its failure return and may accept chunked bodies when callers previously required Content-Length; bucket removal error/final behavior has endpoint parity via backports.",
    ),
    "src/rgw/rgw_rest_config.cc": (
        "trivial", "RGW-060",
        "RGW-060 support: Uses the common Store zone accessor and an explicit RadosStore cast for the existing zonegroup-map backend; response schema and operation behavior are unchanged.",
    ),
    "src/rgw/rgw_rest_log.cc": (
        "affect", "RGW-056",
        "RGW-056: Datalog/mdlog notification body reads use distinct operation types and wrappers that call but do not propagate SigV4 completion failures, while inheriting read_all_input's chunked-framing behavior.",
    ),
    "src/rgw/rgw_rest_log.h": (
        "affect", "RGW-056",
        "RGW-056: Assigns explicit datalog/mdlog notification operation types so the authentication-completion path recognizes signed body-bearing sync requests.",
    ),
    "src/rgw/rgw_rest_metadata.cc": (
        "trivial", "RGW-060",
        "RGW-060 support: Routes metadata list methods through the Store interface while RADOS get/put/delete retain explicit backend access; keys, markers, pagination and sync mode are unchanged.",
    ),
    "src/rgw/rgw_rest_pubsub_common.cc": (
        "trivial", "RGW-060",
        "RGW-060 support: Converts topic/notification ownership checks to equivalent SAL user/bucket lookups with the same error-before-dereference and owner comparison order.",
    ),
    "src/rgw/rgw_rest_realm.cc": (
        "affect", "RGW-056",
        "RGW-056: Period POST receives its own operation type and uses an all-body wrapper that calls but ignores SigV4 completion failure returns, and accepts chunked framing through the unforwarded flag.",
    ),
    "src/rgw/rgw_rest_swift.cc": (
        "affect", "RGW-006,RGW-061",
        "RGW-061: Swift drops the common validator's minimum three-byte name check, allowing otherwise Swift-valid one/two-byte container names; maximum length, leading-dot, UTF-8, 0xff and slash checks remain. RGW-006: The internal Swift website error request is routed through the shared store-aware authenticated path.",
    ),
    "src/rgw/rgw_rest_swift.h": (
        "trivial", "RGW-061",
        "RGW-061 support: Updates Swift declarations to the common SAL Store and qualifies types; the changed name-validation policy is implemented in rgw_rest_swift.cc.",
    ),
    "src/rgw/rgw_sync_module_aws.cc": (
        "affect", "RGW-055",
        "RGW-055: AWS cloud-sync connection JSON accepts/dumps an optional region and passes it into S3RESTConn for SigV4 scope selection.",
    ),
    "src/rgw/rgw_sync_module_es.cc": (
        "trivial", "RGW-055",
        "RGW-055 support: Passes an explicit null optional region to the extended REST connection constructor; Elasticsearch endpoint/auth/index behavior remains unchanged.",
    ),
    "src/rgw/rgw_sync_module_log.cc": (
        "trivial", "",
        "RGW-SYNC-MODULE-MAINT-02: Threads DoutPrefixProvider into the same log sync-module callbacks and qualifies types; emitted operations and data are unchanged.",
    ),
    "src/rgw/rgw_sync_module_pubsub.cc": (
        "trivial", "",
        "RGW-NOTIFY-PARITY-01: Both endpoints emit the unprefixed AWS-compatible eventName through release-specific backports; remaining pubsub-sync changes are SAL/DoutPrefixProvider maintenance.",
    ),
    "src/rgw/rgw_tools.cc": (
        "trivial", "RGW-030,RGW-060",
        "RGW-030/RGW-060 support: Adds an unreferenced system-object stat helper, passes DPP to MIME logging, and rewrites data-access helpers through SAL; role-tag and FIPS behavior is covered by existing runtime rows.",
    ),
    "src/rgw/rgw_tools.h": (
        "trivial", "RGW-030,RGW-060",
        "RGW-030/RGW-060 support: Declares the unused stat helper and common Store data-access surface, qualifies types, and keeps the same hashing/sharding contracts.",
    ),
    "src/rgw/rgw_xml.h": (
        "trivial", "",
        "RGW-XML-NAMESPACE-01: Only qualifies list/string with std:: in XML parser declarations; parser state and accepted elements are unchanged here.",
    ),
    "src/rgw/rgwam.py": (
        "trivial", "",
        "RGW-RGWAM-WRAPPER-01: Adds a source-tree standalone wrapper around python-common RGWAM, but no CMake/install/package reference consumes this file; mgr/core operational behavior belongs to their inventory owners.",
    ),
    "src/rgw/services/svc_bi_rados.h": (
        "trivial", "",
        "RGW-SERVICE-MAINT-03: Qualifies STL types and threads DoutPrefixProvider into existing bucket-index service methods without changing index operations or encoding.",
    ),
    "src/rgw/services/svc_bucket.h": (
        "trivial", "",
        "RGW-SERVICE-MAINT-03: Qualifies map/vector declarations and DPP signatures while preserving bucket read/store/remove and sync-hint service contracts.",
    ),
    "src/rgw/services/svc_cls.h": (
        "trivial", "",
        "RGW-SERVICE-MAINT-03: Qualifies existing CLS service types and log context parameters; class methods, inputs and outputs are unchanged.",
    ),
    "src/rgw/services/svc_rados.cc": (
        "affect", "RGW-005",
        "RGW-005: Exposes librados cluster_fsid through the RADOS service, providing the cluster_id value returned by Quincy's new Admin /info endpoint; remaining changes are DPP/namespace maintenance.",
    ),
    "src/rgw/services/svc_rados.h": (
        "affect", "RGW-005",
        "RGW-005: Declares the cluster_fsid provider consumed by the SAL /info implementation; remaining pool/list/security changes only add DPP or qualify types.",
    ),
    "src/rgw/services/svc_tier_rados.h": (
        "affect", "RGW-059",
        "RGW-059: raw_obj_to_obj starts searching for the object separator after bucket.marker, so underscores inside a zone-derived marker no longer truncate/misparse raw object names.",
    ),
    "src/rgw/store/dbstore/README.md": (
        "trivial", "RGW-060",
        "RGW-060 support: Documents the explicitly experimental DBStore backend, selection option and local SQLite file; documentation does not activate or migrate a deployment.",
    ),
    "src/rgw/store/dbstore/common/dbstore.cc": (
        "affect", "RGW-060",
        "RGW-060: Implements the new experimental database-backed RGW user/bucket/object/lifecycle operation layer selected by rgw_backend_store=dbstore.",
    ),
    "src/rgw/store/dbstore/common/dbstore.h": (
        "affect", "RGW-060",
        "RGW-060: Defines DBStore records and operation contracts for the new non-RADOS backend, including user, bucket, object, data and lifecycle tables.",
    ),
    "src/rgw/store/dbstore/common/dbstore_log.h": (
        "affect", "RGW-060",
        "RGW-060: Defines the backend-specific logging context used by the selectable DBStore implementation.",
    ),
    "src/rgw/store/dbstore/dbstore_main.cc": (
        "affect", "RGW-060",
        "RGW-060: Adds a standalone DBStore sample binary that initializes the backend and exercises persistent operations against its local database.",
    ),
    "src/rgw/store/dbstore/dbstore_mgr.cc": (
        "affect", "RGW-060",
        "RGW-060: Implements per-tenant DBStore handle creation, lookup, deletion and shutdown used by the selected backend.",
    ),
    "src/rgw/store/dbstore/dbstore_mgr.h": (
        "affect", "RGW-060",
        "RGW-060: Defines the manager and default SQLite backend/plugin contract used by DBStore runtime selection.",
    ),
    "src/rgw/store/dbstore/sqlite/sqliteDB.cc": (
        "affect", "RGW-060",
        "RGW-060: Implements SQLite schema, queries and transactions that persist DBStore users, buckets, objects, data, omap and lifecycle state.",
    ),
    "src/rgw/store/dbstore/sqlite/sqliteDB.h": (
        "affect", "RGW-060",
        "RGW-060: Declares the SQLite DBStore backend and prepared-operation surface used by the experimental runtime.",
    ),
    "src/rgw/store/dbstore/tests/dbstore_tests.cc": (
        "trivial", "RGW-060",
        "RGW-060 support: Adds unit coverage for the new experimental DBStore tables and operations; it is not a Pacific-to-Quincy migration or mixed-version recipe.",
    ),
    "src/test/cls_rgw/test_cls_rgw_stats.cc": (
        "trivial", "",
        "RGW-CLS-STATS-TEST-01: Adds a randomized CLS bucket-index stats simulator, including multipart modeling; it changes repository coverage only, not daemon code or an upgrade recipe.",
    ),
    "src/test/rgw/test-rgw-common.sh": (
        "trivial", "",
        "RGW-MULTISITE-SHELL-02: Allows extra radosgw parameters and passes an explicit unused SSL port to the local mrgw helper; runtime multisite semantics are unchanged.",
    ),
    "src/test/rgw/test-rgw-multisite.sh": (
        "trivial", "",
        "RGW-MULTISITE-SHELL-02: Forwards optional user-supplied RGW parameters to every local test daemon; it does not add a cross-version matrix, assertion or production procedure.",
    ),
}


existing_rows = {
    "src/rgw/rgw_admin.cc": [
        ("RGW-053", "RGW-053: Adds the placement inline-data admin option that persists the v8 zone-placement field."),
        ("RGW-055", "RGW-055: Adds --region for URL-based realm/period operations and supplies zonegroup api_name to remote signed connections."),
    ],
    "src/rgw/rgw_main.cc": [
        ("RGW-060", "RGW-060: Selects the compiled experimental DBStore only when rgw_backend_store is explicitly dbstore; the normal default remains RADOS."),
    ],
    "src/rgw/rgw_op.cc": [
        ("RGW-054", "RGW-054: Propagates RGW compression state into the write processor whose RADOS tail writes receive the incompressible allocation hint."),
        ("RGW-056", "RGW-056: Converts body-bearing operations to wrappers that call but discard SigV4 completion failure returns and inherit the unforwarded allow_chunked side effect."),
        ("RGW-058", "RGW-058: Falls back to the non-standard CompletedMultipartUpload parsed root when completing an MPU."),
    ],
    "src/rgw/rgw_op.h": [
        ("RGW-056", "RGW-056: Defines body-reader wrappers that call do_aws4_auth_completion but discard its failure return; read_all_input also does not forward allow_chunked."),
    ],
    "src/rgw/rgw_op_type.h": [
        ("RGW-056", "RGW-056: Adds operation identifiers for signed datalog notification, mdlog notification and period POST bodies."),
    ],
    "src/rgw/rgw_rados.cc": [
        ("RGW-054", "RGW-054: Consumes write allocation flags on the RADOS object path used by RGW-compressed tail data."),
    ],
    "src/rgw/rgw_rados.h": [
        ("RGW-054", "RGW-054: Carries the RADOS allocation-hint flags required by compressed object writes."),
    ],
    "src/rgw/rgw_rest.cc": [
        ("RGW-056", "RGW-056: Converted signed operations call shared body readers through RGWOp wrappers that ignore SigV4 completion failure returns and do not forward allow_chunked; byte-rate accounting remains RGW-006."),
    ],
    "src/rgw/rgw_rest_client.cc": [
        ("RGW-055", "RGW-055: Selects SigV4 region/service from explicit api_name/region before hostname and config fallback."),
    ],
    "src/rgw/rgw_rest_client.h": [
        ("RGW-055", "RGW-055: Carries optional region/api_name through outbound REST signing interfaces."),
    ],
    "src/rgw/rgw_rest_conn.cc": [
        ("RGW-055", "RGW-055: Implements region-aware REST connections used by period propagation and AWS cloud sync."),
    ],
    "src/rgw/rgw_rest_conn.h": [
        ("RGW-055", "RGW-055: Extends REST connection constructors with optional SigV4 region/api_name state."),
    ],
    "src/rgw/rgw_sal.cc": [
        ("RGW-060", "RGW-060: Instantiates DBStore when explicitly requested and keeps RADOS as the default backend."),
    ],
    "src/rgw/rgw_sal.h": [
        ("RGW-054", "RGW-054: Exposes compression state through the shared writer contract used to select RADOS allocation hints."),
        ("RGW-060", "RGW-060: Defines the common Store surface implemented by the new DBStore backend."),
    ],
    "src/rgw/rgw_sal_dbstore.cc": [
        ("RGW-060", "RGW-060: Adapts the new database implementation to RGW's selectable SAL Store interface."),
    ],
    "src/rgw/rgw_sal_dbstore.h": [
        ("RGW-060", "RGW-060: Declares the selectable DBStore SAL objects and backend capability surface."),
    ],
    "src/rgw/rgw_sal_rados.cc": [
        ("RGW-054", "RGW-054: RADOS SAL writer forwards compression/allocation state to the object writer."),
    ],
    "src/rgw/rgw_sal_rados.h": [
        ("RGW-054", "RGW-054: Declares the RADOS writer support used by the incompressible allocation hint path."),
    ],
    "src/rgw/rgw_trim_mdlog.cc": [
        ("RGW-055", "RGW-055: Supplies zonegroup api_name when constructing signed remote connections for metadata-log purge/status work."),
    ],
    "src/rgw/rgw_zone.cc": [
        ("RGW-053", "RGW-053: Dumps/decodes inline_data in zone placement JSON."),
    ],
    "src/rgw/rgw_zone.h": [
        ("RGW-053", "RGW-053: Advances zone placement encoding from v7 to v8 with backward-compatible inline_data=true default."),
    ],
    "src/rgw/services/svc_zone.cc": [
        ("RGW-055", "RGW-055: Supplies zonegroup api_name to master/zonegroup REST connections used for signed outbound control traffic."),
    ],
}

# Two candidate findings were rejected after endpoint-parity checks. Compact
# the still-new IDs so the published report continues directly after RGW-049.
finding_id_renames = {
    "053": "052",  # placement inline_data
    "054": "053",  # OSD incompressible allocation hint
    "055": "054",  # explicit SigV4 region
    "056": "055",  # body-auth completion/chunked side effect
    "058": "056",  # CompletedMultipartUpload alias
    "059": "057",  # raw oid separator
    "060": "058",  # experimental DBStore
    "061": "059",  # Swift bucket-name policy
}
finding_id_pattern = re.compile(
    r"RGW-(" + "|".join(finding_id_renames) + r")\b"
)


def compact_finding_ids(value: str) -> str:
    return finding_id_pattern.sub(
        lambda match: "RGW-" + finding_id_renames[match.group(1)], value
    )


new_rows = {
    path: (impact, compact_finding_ids(finding), compact_finding_ids(reason))
    for path, (impact, finding, reason) in new_rows.items()
}
existing_rows = {
    path: [
        (compact_finding_ids(finding), compact_finding_ids(reason))
        for finding, reason in additions
    ]
    for path, additions in existing_rows.items()
}


csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for row in rows:
    row["finding_id"] = compact_finding_ids(row["finding_id"])
    row["impact_reason"] = compact_finding_ids(row["impact_reason"])

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

for path, additions in existing_rows.items():
    row = by_path[path]
    assert row["upgrade_impact"] in ("affect", "trivial"), path
    ids = [item for item in row["finding_id"].split(",") if item]
    for finding, reason in additions:
        if finding not in ids:
            ids.append(finding)
        if reason not in row["impact_reason"]:
            row["impact_reason"] = row["impact_reason"].rstrip() + " " + reason
    row["finding_id"] = ",".join(ids)

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in by_path.values())
trivial = sum(row["upgrade_impact"] == "trivial" for row in by_path.values())
unclassified = sum(not row["upgrade_impact"] for row in by_path.values())
assert (affect, trivial, unclassified) == (244, 302, 0)
print("Classified final RGW batch: 24 affect, 33 trivial; enriched 21 existing rows")
print(f"RGW totals: affect={affect} trivial={trivial} unclassified={unclassified}")
