"""Verify and classify build/config-conditional RGW Jaeger tracing."""

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


def exists(tag: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{tag}:{path}"],
        check=False,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def is_ancestor(commit: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, tag],
        check=False,
    )
    assert result.returncode in (0, 1)
    return result.returncode == 0


# RGW request tracing and the multipart parent trace are target-only endpoint
# behavior. The implementation and multipart follow-up commits are ancestors of
# Quincy but not Pacific.
for commit, subject in (
    ("05d2e5f1aa46b621792f71bb4cfe21be3f5c63bb", "Tracer implementation"),
    ("14b151c381bcb68a6c52ea1b9da3c12e87e450e4", "single trace for multipart upload ops"),
    ("317b1cfd5d0dcb8b08cc1cf7954fd52d4b5358bf", "get attrs in AbortMultipart only if tracing is enabled"),
):
    message = subprocess.check_output(
        ["git", "-C", str(repo), "show", "-s", "--format=%B", commit],
        text=True,
        encoding="utf-8",
    )
    assert subject in message
    assert not is_ancestor(commit, "v16.2.15")
    assert is_ancestor(commit, "v17.2.7")

assert not exists("v16.2.15", "src/rgw/rgw_tracer.cc")
assert not exists("v16.2.15", "src/rgw/rgw_tracer.h")
assert exists("v17.2.7", "src/rgw/rgw_tracer.cc")
assert exists("v17.2.7", "src/rgw/rgw_tracer.h")

target_tracer_cc = show("v17.2.7", "src/rgw/rgw_tracer.cc")
target_tracer_h = show("v17.2.7", "src/rgw/rgw_tracer.h")
assert 'thread_local tracing::Tracer tracer("rgw");' in target_tracer_cc
assert "tracing::Tracer tracer;" in target_tracer_cc
for token in (
    'const auto OP = "op";',
    'const auto BUCKET_NAME = "bucket_name";',
    'const auto USER_ID = "user_id";',
    'const auto OBJECT_NAME = "object_name";',
    'const auto RETURN = "return";',
    'const auto UPLOAD_ID = "upload_id";',
    "extract_span_context",
    "RGW_ATTR_TRACE",
):
    assert token in target_tracer_h

# Activation is gated twice: compile-time Jaeger support and a runtime option
# whose endpoint default is false. Packaging files contain both ON and OFF paths,
# so the actual artifact must be inspected rather than inferred from source.
target_cmake = show("v17.2.7", "CMakeLists.txt")
target_src_cmake = show("v17.2.7", "src/CMakeLists.txt")
target_rgw_cmake = show("v17.2.7", "src/rgw/CMakeLists.txt")
target_options = show("v17.2.7", "src/common/options/global.yaml.in")
target_spec = show("v17.2.7", "ceph.spec.in")
target_debian = show("v17.2.7", "debian/rules")
assert 'option(WITH_JAEGER "Enable jaegertracing and it\'s dependent libraries" OFF)' in target_cmake
assert "if(WITH_JAEGER)" in target_src_cmake
assert "rgw_tracer.cc" in target_rgw_cmake
option_start = target_options.index("- name: jaeger_tracing_enable")
option_block = target_options[option_start:option_start + 240]
assert "type: bool" in option_block
assert "default: false" in option_block
assert "- rgw" in option_block
assert "-DWITH_JAEGER:BOOL=ON" in target_spec
assert "-DWITH_JAEGER:BOOL=OFF" in target_spec
assert "-DWITH_JAEGER=ON" in target_debian
assert "-DWITH_JAEGER=OFF" in target_debian

# A non-Jaeger build compiles a no-op stub. A Jaeger build installs a
# SimpleSpanProcessor/Jaeger exporter; runtime enablement controls real spans.
target_common_tracer_h = show("v17.2.7", "src/common/tracer.h")
target_common_tracer_cc = show("v17.2.7", "src/common/tracer.cc")
assert "#ifdef HAVE_JAEGER" in target_common_tracer_h
assert "bool is_enabled() const { return false; }" in target_common_tracer_h
assert "SimpleSpanProcessor" in target_common_tracer_cc
assert "JaegerExporter" in target_common_tracer_cc
assert "jaeger_tracing_enable" in target_common_tracer_cc

# Every authenticated request gets a root span plus permission/execute spans and
# tags. These exact endpoint tokens are absent from Pacific.
base_process = show("v16.2.15", "src/rgw/rgw_process.cc")
target_process = show("v17.2.7", "src/rgw/rgw_process.cc")
for token in (
    'add_span("verify_permission", s->trace)',
    'add_span("execute", s->trace)',
    "tracer.start_trace(trace_name)",
    "SetAttribute(tracing::rgw::OP",
    "SetAttribute(tracing::rgw::RETURN",
    "SetAttribute(tracing::rgw::USER_ID",
    "SetAttribute(tracing::rgw::BUCKET_NAME",
    "SetAttribute(tracing::rgw::OBJECT_NAME",
):
    assert token not in base_process
    assert token in target_process

# Multipart init stores an encoded trace context in its metadata attrs. Later
# part/complete/abort paths recover or extend the context. Abort avoids the
# extra metadata read unless runtime tracing is enabled.
base_common = show("v16.2.15", "src/rgw/rgw_common.h")
target_common = show("v17.2.7", "src/rgw/rgw_common.h")
base_op = show("v16.2.15", "src/rgw/rgw_op.cc")
target_op = show("v17.2.7", "src/rgw/rgw_op.cc")
base_op_h = show("v16.2.15", "src/rgw/rgw_op.h")
target_op_h = show("v17.2.7", "src/rgw/rgw_op.h")
assert "RGW_ATTR_TRACE" not in base_common
assert "RGW_ATTR_TRACE" in target_common
for token in (
    "attrs[RGW_ATTR_TRACE] = tracebl;",
    "extract_span_context(meta_obj->get_attrs(), trace_ctx);",
    "if (tracing::rgw::tracer.is_enabled())",
    "multipart_trace = tracing::rgw::tracer.add_span",
):
    assert token not in base_op
    assert token in target_op
assert "jspan multipart_trace;" not in base_op_h
assert "jspan multipart_trace;" in target_op_h

base_sal = show("v16.2.15", "src/rgw/rgw_sal.h")
target_sal = show("v17.2.7", "src/rgw/rgw_sal.h")
target_sal_rados = show("v17.2.7", "src/rgw/rgw_sal_rados.cc")
assert "jspan_context trace_ctx" not in base_sal
assert "jspan_context trace_ctx" in target_sal
assert "extract_span_context(meta_obj->get_attrs(), trace_ctx);" in target_sal_rados

# Documentation illustrates the feature but does not activate the binary.
assert not exists("v16.2.15", "doc/jaegertracing/rgw_jaeger.png")
assert exists("v17.2.7", "doc/jaegertracing/rgw_jaeger.png")
target_tracing_doc = show("v17.2.7", "doc/jaegertracing/index.rst")
assert "tracing in Ceph is disabled by default" in target_tracing_doc
assert "every user request is being traced" in target_tracing_doc
assert "Multipart upload" in target_tracing_doc


new_rows = {
    "src/rgw/rgw_tracer.cc": (
        "affect",
        "RGW-042",
        "RGW-042: Adds the build-conditional RGW OpenTelemetry/Jaeger tracer instance; a Jaeger-enabled artifact can emit per-request spans when runtime tracing is enabled.",
    ),
    "src/rgw/rgw_tracer.h": (
        "affect",
        "RGW-042",
        "RGW-042: Defines request/span attributes and extraction of the persisted multipart trace context from RGW_ATTR_TRACE.",
    ),
    "doc/jaegertracing/rgw_jaeger.png": (
        "trivial",
        "",
        "RGW-TRACING-DOC-01: Adds a Jaeger UI screenshot that documents RGW tracing; build/config/runtime behavior is tracked by RGW-042.",
    ),
}

existing_additions = {
    "src/rgw/rgw_common.h": (
        "RGW-042",
        "RGW-042: Adds the internal trace attribute name and a request span handle used by build/config-conditional RGW tracing.",
    ),
    "src/rgw/rgw_op.cc": (
        "RGW-042",
        "RGW-042: Persists and recovers multipart trace context, tags upload IDs, and conditionally reads abort metadata when tracing is enabled.",
    ),
    "src/rgw/rgw_op.h": (
        "RGW-042",
        "RGW-042: Adds multipart span state and starts the multipart parent trace used across upload operations.",
    ),
    "src/rgw/rgw_process.cc": (
        "RGW-042",
        "RGW-042: Wraps authenticated request permission/execute stages in spans and records operation, return, user, bucket, and object attributes.",
    ),
    "src/rgw/rgw_sal.h": (
        "RGW-042",
        "RGW-042: Carries decoded multipart trace context through the SAL multipart-upload abstraction.",
    ),
    "src/rgw/rgw_sal_rados.cc": (
        "RGW-042",
        "RGW-042: Extracts persisted trace context from RADOS multipart metadata for later upload operations.",
    ),
}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)

for path, (impact, finding, reason) in new_rows.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

for path, (finding, reason) in existing_additions.items():
    row = by_path[path]
    assert row["upgrade_impact"] == "affect", path
    findings = row["finding_id"].split(",") if row["finding_id"] else []
    if finding not in findings:
        row["finding_id"] = ",".join(findings + [finding])
        row["impact_reason"] = (row["impact_reason"] + " " + reason).strip()
    else:
        assert reason in row["impact_reason"], path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified RGW tracing: 2 affect, 1 trivial; extended 6 existing affect rows")
