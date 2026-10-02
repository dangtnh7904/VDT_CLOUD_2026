"""Classify reviewed msgr2 compression, CRC and address-announcement paths."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
findings = {
    "src/include/msgr.h": ("MSG-003", "msgr2 supported feature mask gains COMPRESSION while required mask remains zero, allowing feature-negotiated mixed-peer fallback."),
    "src/msg/Messenger.cc": ("MSG-003;MSG-005", "Messenger initializes live compressor registry and bindv can pass distinct public addresses to underlying bind path."),
    "src/msg/Messenger.h": ("MSG-003;MSG-005", "Messenger interface exposes compression registry and separate bind/public addresses, changing connection setup and published endpoint API."),
    "src/msg/async/AsyncMessenger.cc": ("MSG-005", "AsyncMessenger saves public addresses across delayed bind/rebind, fills negotiated port and advertises them separately from socket bind addresses."),
    "src/msg/async/AsyncMessenger.h": ("MSG-005", "AsyncMessenger bind/bindv API now accepts and retains public address vector for advertisement after bind/rebind."),
    "src/msg/async/ProtocolV2.cc": ("MSG-003;MSG-004", "msgr2 negotiates compression after authentication and resets/reuses handlers across reconnects; frame assemblers now honor ms_crc_data."),
    "src/msg/async/ProtocolV2.h": ("MSG-003", "msgr2 state machine adds compression request/accept states and per-session compression metadata/handlers."),
    "src/msg/async/frames_v2.cc": ("MSG-003;MSG-004", "Frame assembler compresses/decompresses flagged segments and conditionally calculates/checks CRC based on ms_crc_data."),
    "src/msg/async/frames_v2.h": ("MSG-003;MSG-004", "msgr2 frame format gains compression tags/flag and assembler carries compression/CRC state."),
    "src/msg/async/compression_meta.h": ("MSG-003", "New per-connection compression mode/method metadata feeds msgr2 negotiation and frame encoding."),
    "src/msg/async/compression_onwire.cc": ("MSG-003", "New segment compressor/decompressor implements negotiated on-wire compression with size threshold and fallback."),
    "src/msg/async/compression_onwire.h": ("MSG-003", "New compression handler interface stores per-session algorithm/mode and minimum size used by frame assembler."),
    "src/msg/compressor_registry.cc": ("MSG-003", "New registry reads live ms_osd_compress settings and chooses compatible mode/method by peer type and secure mode."),
    "src/msg/compressor_registry.h": ("MSG-003", "New registry API exposes peer-specific compression mode, method and threshold to msgr2 handshake."),
}
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in findings} == set(findings)
for row in rows:
    path = row["path"]
    if path not in findings:
        continue
    assert not row["upgrade_impact"], path
    fid, reason = findings[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = fid
    row["impact_reason"] = f"{fid}: {reason}"
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
