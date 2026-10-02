"""Classify inspected admin, signal, and Crimson messenger endpoint diffs."""

import csv
from pathlib import Path


csv_path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/common/admin_socket.cc": ("MSG-018", "Synchronous admin hooks accept the input buffer already carried by tell/admin execution; built-in hooks inspected here ignore it."),
    "src/common/admin_socket.h": ("MSG-018", "Default call_async now forwards inbl to synchronous call; custom hooks can consume command input and must match the new C++ interface."),
    "src/common/ceph_context.cc": ("MSG-014", "Runtime log observer now starts/stops Journald and passes host/FSID to Graylog; diagnostic lockdep and leak-test hunks are secondary."),
    "src/common/ceph_context.h": ("MSG-019", "Crimson CephContext now exposes a plugin-registry pointer but endpoint constructor does not initialize it; plugin-loading path needs a build/runtime check."),
    "src/crimson/net/Connection.h": ("MSG-022", "Crimson connection send interface changes to unique message ownership, feeding the revised resend/ack queues."),
    "src/crimson/net/Messenger.h": ("MSG-021", "Crimson messenger gains address completion and address-not-available bind error for boot/bind call paths."),
    "src/crimson/net/Protocol.cc": ("MSG-022", "Crimson sweep now serializes outbound messages then moves reliable messages directly from out_q into sent before clearing out_q."),
    "src/crimson/net/Protocol.h": ("MSG-022", "Crimson protocol send/sweep API takes uniquely owned messages and centralizes the sent-queue transition."),
    "src/crimson/net/ProtocolV1.cc": ("MSG-020", "Crimson msgr1 protocol implementation is deleted; target SocketConnection only constructs ProtocolV2."),
    "src/crimson/net/ProtocolV1.h": ("MSG-020", "Crimson msgr1 protocol interface is deleted, removing the previous legacy-address connection branch."),
    "src/crimson/net/ProtocolV2.cc": ("MSG-023", "Crimson msgr2 advertises REVISION_1 without compression, switches frame disassembly, and adjusts peer-address checks; CRC option is in paired header."),
    "src/crimson/net/ProtocolV2.h": ("MSG-023", "Crimson frame assemblers now use ms_crc_data and compression-handler pointers; compressor feature remains disabled in Crimson banner."),
    "src/crimson/net/Socket.cc": ("MSG-021", "Crimson socket detects short read as EOF and propagates address-not-available from listen instead of aborting it."),
    "src/crimson/net/Socket.h": ("MSG-021", "Crimson socket exposes local address for address learning, distinguishes listen errors, and preserves accepted address type."),
    "src/crimson/net/SocketConnection.cc": ("MSG-020", "Crimson SocketConnection always constructs ProtocolV2; no runtime msgr1 selection remains."),
    "src/crimson/net/SocketConnection.h": ("MSG-022", "Crimson resend/sent queues use unique message ownership and remove pending_q; socket local address is exposed for learning."),
    "src/crimson/net/SocketMessenger.cc": ("MSG-021", "Crimson bind retries and address learning change; connect explicitly aborts for non-msgr2 addresses and boot fills blank IPs."),
    "src/crimson/net/SocketMessenger.h": ("MSG-021", "Crimson messenger declares retry-capable bind and address-completion interface used during OSD boot."),
    "src/global/signal_handler.cc": ("MSG-024", "Fatal handler becomes one-shot per process, explicitly resets signal disposition before re-raise, and shared crash dump accepts extra MGR fields."),
    "src/global/signal_handler.h": ("MSG-024", "Crash dump helper accepts additional fields, used by MGR Python exception handling."),
    "src/global/global_init.cc": ("MSG-025", "Source build now requires std::filesystem here instead of accepting experimental/filesystem fallback on older toolchains."),
}
trivial = {
    "src/crimson/net/Interceptor.h": "T05-crimson: Explicit std::chrono::seconds(10) replaces the same 10s timeout in test socket blocker.",
    "src/global/pidfile.cc": "T05-global: Rewrites the same four flock fields as assignments before the same F_SETLK call.",
}
selected = set(affect) | set(trivial)
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
assert {row["path"] for row in rows if row["path"] in selected} == selected
for row in rows:
    path = row["path"]
    if path not in selected:
        continue
    assert not row["upgrade_impact"], path
    if path in affect:
        fid, reason = affect[path]
        row["upgrade_impact"] = "affect"
        row["finding_id"] = fid
        row["impact_reason"] = f"{fid}: {reason}"
    else:
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = trivial[path]
with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
