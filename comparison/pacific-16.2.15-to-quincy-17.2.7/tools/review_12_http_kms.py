"""Classify RGW outbound HTTP HEAD/SigV4 and nearby KMS support rows."""

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


# Pacific sent a custom HEAD method but still let libcurl expect a response
# body. Quincy explicitly selects CURLOPT_NOBODY, and its unit test covers a
# valid HEAD response that advertises Content-Length without sending a body.
base_http = show("v16.2.15", "src/rgw/rgw_http_client.cc")
target_http = show("v17.2.7", "src/rgw/rgw_http_client.cc")
assert 'if (method == "HEAD")' not in base_http
assert 'if (method == "HEAD")' in target_http
assert "curl_easy_setopt(easy_handle, CURLOPT_NOBODY, 1L);" in target_http

base_http_test = show("v16.2.15", "src/test/rgw/test_http_manager.cc")
target_http_test = show("v17.2.7", "src/test/rgw/test_http_manager.cc")
assert "TEST(HTTPManager, Head)" not in base_http_test
assert "TEST(HTTPManager, Head)" in target_http_test
assert '"Content-Length: 1024\\r\\n"' in target_http_test
assert 'RGWHTTPClient client{g_ceph_context, "HEAD", url};' in target_http_test
assert "EXPECT_EQ(0, RGWHTTP::process(&client, null_yield));" in target_http_test

# The live Quincy caller is the cloud-tier idempotence check. HEAD failure is
# logged as best effort and the worker can continue to upload the object.
target_lc_tier = show("v17.2.7", "src/rgw/rgw_lc_tier.cc")
target_rest_conn = show("v17.2.7", "src/rgw/rgw_rest_conn.cc")
assert "req_params.get_op = !head;" in target_lc_tier
assert "cloud_tier_get_object(tier_ctx, true, headers)" in target_lc_tier
assert "failed to check object on the cloud endpoint" in target_lc_tier
assert "RGWRESTStreamHeadRequest" in target_rest_conn

# A non-OK libcurl result on an otherwise successful HTTP status is exposed as
# -EAGAIN by both endpoints, which explains the observable Pacific failure.
for source in (base_http, target_http):
    assert "if (result != CURLE_OK && status == 0)" in source
    assert "status = -EAGAIN;" in source

# Custom CA and client-certificate handling is present at both endpoints and
# must not be reported as a new Quincy transport contract.
for source in (base_http, target_http):
    assert "CURLOPT_CAINFO" in source
    assert "CURLOPT_SSLCERT" in source
    assert "CURLOPT_SSLKEY" in source
base_kms = show("v16.2.15", "src/rgw/rgw_kms.cc")
target_kms = show("v17.2.7", "src/rgw/rgw_kms.cc")
for source in (base_kms, target_kms):
    assert "set_ca_path" in source
    assert "set_client_cert" in source
    assert "set_client_key" in source

# Quincy parses the outbound URL into host/resource components consumed by the
# SigV4 forwarding path already owned by RGW-030.
base_http_h = show("v16.2.15", "src/rgw/rgw_http_client.h")
target_http_h = show("v17.2.7", "src/rgw/rgw_http_client.h")
for field in ("std::string protocol;", "std::string host;", "std::string resource_prefix;"):
    assert field not in base_http_h
    assert field in target_http_h
target_rest_client = show("v17.2.7", "src/rgw/rgw_rest_client.cc")
assert "scope_from_api_name(dpp, cct, host, api_name" in target_rest_client
assert "headers_gen->init(method, host, resource_prefix" in target_rest_client

# Documentation and QA additions describe/enable the SSE-S3 behavior already
# owned by RGW-002. The Vault TLS controls themselves predate both endpoints.
base_encryption_doc = show("v16.2.15", "doc/radosgw/encryption.rst")
target_encryption_doc = show("v17.2.7", "doc/radosgw/encryption.rst")
assert "SSE-S3\n======" not in base_encryption_doc
assert "SSE-S3\n======" in target_encryption_doc
assert "Bucket Encryption APIs\n======================" in target_encryption_doc

base_vault_doc = show("v16.2.15", "doc/radosgw/vault.rst")
target_vault_doc = show("v17.2.7", "doc/radosgw/vault.rst")
assert "rgw_crypt_sse_s3_vault_prefix" not in base_vault_doc
assert "rgw_crypt_sse_s3_vault_prefix" in target_vault_doc
for source in (base_vault_doc, target_vault_doc):
    assert "rgw crypt vault ssl cacert" in source
    assert "rgw crypt vault ssl clientcert" in source

base_vault_qa = show("v16.2.15", "qa/suites/rgw/crypt/2-kms/vault_transit.yaml")
target_vault_qa = show("v17.2.7", "qa/suites/rgw/crypt/2-kms/vault_transit.yaml")
assert "rgw crypt sse s3 backend" not in base_vault_qa
assert "rgw crypt sse s3 backend: vault" in target_vault_qa
assert "with-sse-s3: true" in target_vault_qa
assert show("v17.2.7", "qa/suites/rgw/crypt/supported-random-distro$").strip() == ".qa/distros/supported-random-distro$"

# These unit-test rows retain their cases/assertions while following DPP, SAL,
# SSEContext or argv API changes. Runtime behavior is owned by source rows.
for path in (
    "src/test/rgw/test_rgw_crypto.cc",
    "src/test/rgw/test_rgw_kms.cc",
    "src/test/test_rgw_ldap.cc",
    "src/test/test_rgw_token.cc",
):
    base = show("v16.2.15", path)
    target = show("v17.2.7", path)
    assert base.count("TEST(") + base.count("TEST_F(") == target.count("TEST(") + target.count("TEST_F("), path
    assert base.count("ASSERT_") == target.count("ASSERT_"), path
base_crypto_test = show("v16.2.15", "src/test/rgw/test_rgw_crypto.cc")
target_crypto_test = show("v17.2.7", "src/test/rgw/test_rgw_crypto.cc")
assert "rgw::putobj::DataProcessor" in base_crypto_test
assert "rgw::sal::DataProcessor" in target_crypto_test
assert "set_parts_len" in base_crypto_test
assert "set_parts_len" not in target_crypto_test
assert "create_mp_parts(obj_size, part_size)" in target_crypto_test

base_kms_test = show("v16.2.15", "src/test/rgw/test_rgw_kms.cc")
target_kms_test = show("v17.2.7", "src/test/rgw/test_rgw_kms.cc")
assert "SSEContext & kctx" not in base_kms_test
assert "SSEContext & kctx" in target_kms_test
assert base_kms_test.count("TEST_F(") == target_kms_test.count("TEST_F(")

base_common_test = show("v16.2.15", "src/test/rgw/test_rgw_common.h")
target_common_test = show("v17.2.7", "src/test/rgw/test_rgw_common.h")
assert "static void generate_test_instances(list<old_rgw_bucket*>& o);" in base_common_test
assert "static void generate_test_instances(std::list<old_rgw_bucket*>& o);" in target_common_test

base_layout_doc = show("v16.2.15", "doc/radosgw/layout.rst")
target_layout_doc = show("v17.2.7", "doc/radosgw/layout.rst")
assert "up to 512 kilobytes of object data" in base_layout_doc
assert ":confval:`rgw_max_chunk_size`" in target_layout_doc
base_python_doc = show("v16.2.15", "doc/radosgw/s3/python.rst")
target_python_doc = show("v17.2.7", "doc/radosgw/s3/python.rst")
assert 'print "{name}\\t{created}".format(' in base_python_doc
assert 'print("{name}\\t{created}".format(' in target_python_doc


updates = {
    "src/rgw/rgw_http_client.cc": (
        "affect",
        "RGW-034",
        "RGW-034: Quincy sets CURLOPT_NOBODY for outbound HEAD so a valid response with Content-Length and no body does not become libcurl -EAGAIN; the active cloud-tier preflight caller uses this as a best-effort idempotence check before upload. The same file's URL parsing also supports RGW-030 SigV4 forwarding.",
    ),
    "src/rgw/rgw_http_client.h": (
        "affect",
        "RGW-030",
        "RGW-030: Stores parsed protocol, host and resource-prefix state consumed by Quincy's SigV4 outbound forwarding path; CA/client-certificate setters already exist at both endpoints.",
    ),
    "doc/radosgw/encryption.rst": (
        "trivial",
        "RGW-002",
        "RGW-002 support: Documents SSE-S3 and bucket-encryption APIs already owned by runtime rows; it does not alter encryption state or add an independent validation gate.",
    ),
    "doc/radosgw/vault.rst": (
        "trivial",
        "RGW-002",
        "RGW-002 support: Adds SSE-KMS/SSE-S3 Vault separation guidance and typo fixes; custom CA/client-certificate settings are already present at both endpoints and the document does not change runtime behavior.",
    ),
    "qa/suites/rgw/crypt/2-kms/vault_transit.yaml": (
        "affect",
        "RGW-002",
        "RGW-002: Extends the Vault transit QA recipe with the SSE-S3 backend and with-sse-s3 test flag, changing encryption acceptance coverage but adding no Pacific/Quincy mixed-version or rollback case.",
    ),
    "qa/suites/rgw/crypt/supported-random-distro$": (
        "affect",
        "RGW-002",
        "RGW-002: Adds the supported-random-distro selector used to schedule the RGW crypt suite that now exercises SSE-S3 Vault coverage.",
    ),
    "src/test/rgw/test_rgw_common.h": (
        "trivial",
        "",
        "RGW-TEST-01: Test compatibility types only gain explicit std:: qualification; their encoding helpers and behavior are unchanged.",
    ),
    "src/test/rgw/test_rgw_crypto.cc": (
        "trivial",
        "RGW-002",
        "RGW-002 support: Existing crypto test cases and assertions follow DPP/SAL constructor changes and pass multipart lengths at construction; no new acceptance case or endpoint contract is introduced by this test row.",
    ),
    "src/test/rgw/test_rgw_kms.cc": (
        "trivial",
        "RGW-002",
        "RGW-002 support: Existing Vault KMS mocks/tests follow SSEContext and DPP signatures while retaining the same test cases and assertions; runtime key behavior is owned by RGW-002 source rows.",
    ),
    "src/test/test_rgw_ldap.cc": (
        "trivial",
        "",
        "RGW-TEST-01: LDAP test main adopts the returning argv_to_vec API and namespace import while preserving argument parsing and all test cases/assertions.",
    ),
    "src/test/test_rgw_token.cc": (
        "trivial",
        "",
        "RGW-TEST-01: Token test main adopts the returning argv_to_vec API and namespace import while preserving argument parsing and all test cases/assertions.",
    ),
    "doc/radosgw/layout.rst": (
        "trivial",
        "",
        "RGW-DOC-01: Corrects wording and replaces the fixed head-data size in prose with the existing rgw_max_chunk_size configuration reference; no runtime or upgrade recipe changes.",
    ),
    "doc/radosgw/s3/python.rst": (
        "trivial",
        "",
        "RGW-DOC-01: Modernizes Python print examples and adds a file-upload example; it does not change RGW behavior or an upgrade validation gate.",
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
for path, (impact, finding, reason) in updates.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print("Classified four HTTP/KMS rows affect and nine documentation/test rows trivial")
