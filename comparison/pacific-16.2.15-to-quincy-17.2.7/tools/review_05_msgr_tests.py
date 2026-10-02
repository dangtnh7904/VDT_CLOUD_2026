"""Classify messenger test changes by actual validation coverage."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/test/msgr/test_async_networkstack.cc": ("MSG-058", "DPDK networkstack test no longer injects fixed coremask/IP config; test execution now depends on external DPDK address/device setup."),
    "src/test/msgr/test_comp_registry.cc": ("MSG-059", "New ctest target checks compressor method/mode selection and secure compression, extending executed messenger validation when ctest is a gate."),
    "src/test/msgr/test_frames_v2.cc": ("MSG-059", "Frame roundtrip matrix expands from four modes to eight compression/secure/revision combinations, changing executed validation coverage."),
}
trivial = {
    "src/test/msgr/perf_msgr_client.cc": "T05-msgr-test-argv: Perf client passes same argv range through new argv_to_vec signature; benchmark body unchanged.",
    "src/test/msgr/perf_msgr_server.cc": "T05-msgr-test-argv: Perf server passes same argv range through new argv_to_vec signature; benchmark body unchanged.",
    "src/test/msgr/test_async_driver.cc": "T05-msgr-test-namespace: Adds std namespace import only; driver assertions unchanged.",
    "src/test/msgr/test_msgr.cc": "T05-msgr-test-policy: Enables test-only mutable Policy feature mask and follows argv helper; existing messenger cases unchanged.",
    "src/test/testmsgr.cc": "T05-msgr-test-argv: Standalone test entrypoint follows return-value argv helper with same argument range.",
}
selected = set(affect) | set(trivial)
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    name = row["path"]
    if name not in selected:
        continue
    assert not row["upgrade_impact"], name
    if name in affect:
        fid, reason = affect[name]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[name]
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
