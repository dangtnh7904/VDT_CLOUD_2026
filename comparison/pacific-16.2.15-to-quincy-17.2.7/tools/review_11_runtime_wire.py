"""Classify owner-11 CephFS runtime/wire and screened documentation clusters."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "11-cephfs-mds.csv"
md_path = root / "11-cephfs-mds.md"
readme_path = root / "README.md"
plan_path = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, path: str) -> str:
    return git("show", f"{tag}:{path}").stdout


def ancestor(commit: str, ref: str) -> bool:
    return git("merge-base", "--is-ancestor", commit, ref, check=False).returncode == 0


def replace_known(path: Path, old: str, new: str, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if old in text:
        assert text.count(old) == expected, (path, old, text.count(old))
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    else:
        assert text.count(new) == expected, (path, new, text.count(new))


def insert_before_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if block in text:
        assert text.count(block) == 1
        return
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, block + marker), encoding="utf-8", newline="")


doc_paths = {
    "doc/cephfs/Makefile",
    "doc/cephfs/administration.rst",
    "doc/cephfs/api/index.rst",
    "doc/cephfs/cache-configuration.rst",
    "doc/cephfs/capabilities.rst",
    "doc/cephfs/cephfs-mirroring.rst",
    "doc/cephfs/cephfs-top.rst",
    "doc/cephfs/client-auth.rst",
    "doc/cephfs/client-config-ref.rst",
    "doc/cephfs/createfs.rst",
    "doc/cephfs/disaster-recovery-experts.rst",
    "doc/cephfs/dynamic-metadata-management.rst",
    "doc/cephfs/fs-volumes.rst",
    "doc/cephfs/health-messages.rst",
    "doc/cephfs/index.rst",
    "doc/cephfs/journaler.rst",
    "doc/cephfs/lazyio.rst",
    "doc/cephfs/mds-config-ref.rst",
    "doc/cephfs/mds-state-diagram.svg",
    "doc/cephfs/mds-states.rst",
    "doc/cephfs/mount-using-kernel-driver.rst",
    "doc/cephfs/multimds.rst",
    "doc/cephfs/nfs.rst",
    "doc/cephfs/quota.rst",
    "doc/cephfs/snap-schedule.rst",
    "doc/cephfs/standby.rst",
    "doc/cephfs/troubleshooting.rst",
    "doc/dev/cephfs-mirroring.rst",
    "doc/man/8/ceph-mds.rst",
    "doc/man/8/cephfs-mirror.rst",
    "doc/man/8/cephfs-shell.rst",
}
assert len(doc_paths) == 31

event_paths = {
    "src/mds/events/ECommitted.h",
    "src/mds/events/EExport.h",
    "src/mds/events/EFragment.h",
    "src/mds/events/EImportFinish.h",
    "src/mds/events/EImportStart.h",
    "src/mds/events/EMetaBlob.h",
    "src/mds/events/EOpen.h",
    "src/mds/events/EPeerUpdate.h",
    "src/mds/events/EPurged.h",
    "src/mds/events/EResetJournal.h",
    "src/mds/events/ESession.h",
    "src/mds/events/ESessions.h",
    "src/mds/events/ESubtreeMap.h",
    "src/mds/events/ETableClient.h",
    "src/mds/events/ETableServer.h",
    "src/mds/events/EUpdate.h",
}
assert len(event_paths) == 16

message_paths = {
    "src/messages/MCacheExpire.h",
    "src/messages/MClientCapRelease.h",
    "src/messages/MClientCaps.h",
    "src/messages/MClientLease.h",
    "src/messages/MClientMetrics.h",
    "src/messages/MClientQuota.h",
    "src/messages/MClientReclaim.h",
    "src/messages/MClientReclaimReply.h",
    "src/messages/MClientReconnect.h",
    "src/messages/MClientReply.h",
    "src/messages/MClientRequest.h",
    "src/messages/MClientRequestForward.h",
    "src/messages/MClientSession.h",
    "src/messages/MClientSnap.h",
    "src/messages/MDentryLink.h",
    "src/messages/MDentryUnlink.h",
    "src/messages/MDirUpdate.h",
    "src/messages/MDiscover.h",
    "src/messages/MDiscoverReply.h",
    "src/messages/MExportCaps.h",
    "src/messages/MExportCapsAck.h",
    "src/messages/MExportDir.h",
    "src/messages/MExportDirAck.h",
    "src/messages/MExportDirCancel.h",
    "src/messages/MExportDirDiscover.h",
    "src/messages/MExportDirDiscoverAck.h",
    "src/messages/MExportDirFinish.h",
    "src/messages/MExportDirNotify.h",
    "src/messages/MExportDirNotifyAck.h",
    "src/messages/MExportDirPrep.h",
    "src/messages/MExportDirPrepAck.h",
    "src/messages/MGatherCaps.h",
    "src/messages/MHeartbeat.h",
    "src/messages/MInodeFileCaps.h",
    "src/messages/MLock.h",
    "src/messages/MMDSBeacon.h",
    "src/messages/MMDSCacheRejoin.h",
    "src/messages/MMDSFindIno.h",
    "src/messages/MMDSFindInoReply.h",
    "src/messages/MMDSFragmentNotify.h",
    "src/messages/MMDSFragmentNotifyAck.h",
    "src/messages/MMDSLoadTargets.h",
    "src/messages/MMDSMap.h",
    "src/messages/MMDSMetrics.h",
    "src/messages/MMDSOpenIno.h",
    "src/messages/MMDSOpenInoReply.h",
    "src/messages/MMDSPeerRequest.h",
    "src/messages/MMDSPing.h",
    "src/messages/MMDSResolve.h",
    "src/messages/MMDSResolveAck.h",
    "src/messages/MMDSScrub.h",
    "src/messages/MMDSScrubStats.h",
    "src/messages/MMDSSnapUpdate.h",
    "src/messages/MMDSTableRequest.h",
}
assert len(message_paths) == 54

affect_paths = {
    "src/mds/Beacon.cc": "FS-009",
    "src/mds/MDSRank.cc": "FS-009",
    "src/mds/Server.cc": "FS-009",
    "src/mds/Server.h": "FS-009",
    "src/messages/MMDSBeacon.h": "FS-009",
    "src/mds/CDentry.h": "FS-010",
    "src/mds/MDCache.cc": "FS-010",
    "src/mds/MDCache.h": "FS-010",
    "src/messages/MDentryUnlink.h": "FS-010",
    "src/client/Client.cc": "FS-011",
    "src/messages/MClientRequest.h": "FS-012",
}
assert len(affect_paths) == 11

runtime_trivial_paths = {
    "src/client/MetaRequest.h",
    "src/mds/cephfs_features.cc",
    "src/mds/cephfs_features.h",
}

message_trivial_paths = message_paths - set(affect_paths)
assert len(message_trivial_paths) == 51
trivial_paths = doc_paths | event_paths | message_trivial_paths | runtime_trivial_paths
assert len(trivial_paths) == 101
paths = set(affect_paths) | trivial_paths
assert len(paths) == 112

# Endpoint inventory check deliberately disables heuristic rename pairing.
touched = set(
    git("diff", "--no-renames", "--name-only", "v16.2.15", "v17.2.7", "--", *sorted(paths))
    .stdout.splitlines()
)
assert touched == paths, (sorted(paths - touched), sorted(touched - paths))

# Target-side implementations and mechanical refactors.
for commit in (
    "7005de0f6ff9bb1c154b3d28e7dfaad9abcf7030",
    "75c1c754d14ea300c7123995680a864212104b8c",
    "078cee3a247b0b5896f19ff060b1e7c433a0acf3",
    "4aad45133a439f6088442686246c0bff7b4baf5e",
    "13302a16aa32ba63bcceb2e2994f942cc38bab76",
):
    assert ancestor(commit, "v17.2.7"), commit

# Pacific-only backports that remain present at the base endpoint.
for commit in (
    "798cb2c306ec648d10cf14296de28f903df27e9d",
    "6168e621f68728f066f1c7a41058a4dd2bda7370",
    "5452e25942bc1601bf6a05937aafdc3a9b681ab6",
    "69602dbee0f33cdbb239ec7307128c181b163688",
    "4f2c462923c0636c38e14c2d3fb37f759bd3739d",
):
    assert ancestor(commit, "v16.2.15"), commit
    assert not ancestor(commit, "v17.2.7"), commit

# FS-009: Pacific defers eviction and reports affected clients; Quincy has no
# corresponding option, state set, or health metric at the endpoint. Pacific
# defaults this guard to true, so applicability does not require manual opt-in.
base_server = show("v16.2.15", "src/mds/Server.cc")
target_server = show("v17.2.7", "src/mds/Server.cc")
base_beacon = show("v16.2.15", "src/mds/Beacon.cc")
target_beacon = show("v17.2.7", "src/mds/Beacon.cc")
base_options = show("v16.2.15", "src/common/options.cc")
target_options = show("v17.2.7", "src/common/options.cc")
for needle in ("defer_client_eviction_on_laggy_osds", "laggy_clients"):
    assert needle in base_server
    assert needle not in target_server
assert "MDS_HEALTH_CLIENTS_LAGGY" in base_beacon
assert "MDS_HEALTH_CLIENTS_LAGGY" not in target_beacon
assert "defer_client_eviction_on_laggy_osds" in base_options
assert "defer_client_eviction_on_laggy_osds" not in target_options
base_defer_option = base_options.split(
    'Option("defer_client_eviction_on_laggy_osds"', 1
)[1].split("Option(", 1)[0]
assert ".set_default(true)" in base_defer_option

# FS-010: target adds a version-compatible flag plus a new ACK message and
# waits for replica acknowledgement before retrying namespace work.
base_unlink = show("v16.2.15", "src/messages/MDentryUnlink.h")
target_unlink = show("v17.2.7", "src/messages/MDentryUnlink.h")
target_cache = show("v17.2.7", "src/mds/MDCache.cc")
assert "MDentryUnlinkAck" not in base_unlink
assert "MDentryUnlinkAck" in target_unlink
assert "static constexpr int HEAD_VERSION = 2" in target_unlink
assert "WAIT_UNLINK_STATE" in target_cache
assert "handle_dentry_unlink_ack" in target_cache

# FS-011: the base client has an explicit upgrade path for refreshing MDS
# feature bits on a repeated OPEN; the target client returns without it.
base_client = show("v16.2.15", "src/client/Client.cc")
target_client = show("v17.2.7", "src/client/Client.cc")
assert "reinit_mds_features(session, m);" in base_client
assert "reinit_mds_features(session, m);" not in target_client
assert "if (session->state == MetaSession::STATE_OPEN)" in target_client

# FS-012: both endpoints expose extended counters, but only Pacific copies the
# legacy 8-bit values into them on the old request-header decode path.
base_request = show("v16.2.15", "src/messages/MClientRequest.h")
target_request = show("v17.2.7", "src/messages/MClientRequest.h")
for needle in ("head.ext_num_retry = head.num_retry;", "head.ext_num_fwd = head.num_fwd;"):
    assert needle in base_request
    assert needle not in target_request
assert "return head.ext_num_retry" in target_request
assert "return head.ext_num_fwd" in target_request

# Journal-event changes are namespace qualification/container spelling only;
# no encode/decode version marker changes in this selected endpoint cluster.
event_diff = git("diff", "--unified=0", "v16.2.15", "v17.2.7", "--", *sorted(event_paths)).stdout
for forbidden in ("+  ENCODE_START", "+    ENCODE_START", "+  DECODE_START", "+    DECODE_START"):
    assert forbidden not in event_diff
assert "+  void print(std::ostream&" in event_diff

# Non-exception message headers do not change message versions or payload
# encode/decode calls. Most only add the Crimson factory friend; MMDSMap drops
# an unused, non-encoded fs_name copy.
message_diff = git(
    "diff", "--unified=0", "v16.2.15", "v17.2.7", "--", *sorted(message_trivial_paths)
).stdout
for forbidden in (
    "+  static constexpr int HEAD_VERSION",
    "+  static constexpr int COMPAT_VERSION",
    "+    encode(",
    "+    decode(",
):
    assert forbidden not in message_diff
assert "crimson::make_message" in message_diff

# Documentation is reference material rather than an executed upgrade recipe;
# it includes normal command/feature/recovery updates, so keep it in the ledger
# but outside the affecting queue.
assert all(path.startswith("doc/") for path in doc_paths)
assert not any("upgrade" in path for path in doc_paths)

reasons = {
    "FS-009": (
        "FS-009: Pacific 16.2.15 contains branch-only logic that, when "
        "defer_client_eviction_on_laggy_osds has effective value true, including Pacific's "
        "default true and an OSD is laggy, records "
        "affected clients, defers eviction, and emits MDS_CLIENTS_LAGGY. Quincy 17.2.7 "
        "has none of the option, state, guard, or health metric, changing client continuity "
        "and rollout observability for deployments with that effective value."
    ),
    "FS-010": (
        "FS-010: Quincy adds MDentryUnlink v2 plus MDentryUnlinkAck and waits on "
        "replica_unlinking_ref/WAIT_UNLINK_STATE before retrying same-dentry namespace work. "
        "Pacific 16.2.15 lacks the ACK path, so multi-active mixed-version MDS peers require "
        "explicit validation of unlink/create progress."
    ),
    "FS-011": (
        "FS-011: Pacific's userspace client refreshes MDS feature and metric bits when an "
        "already-open session receives OPEN after an MDS upgrade; Quincy returns without that "
        "refresh. A client-upgraded-first sequence can therefore retain stale negotiated bits "
        "until the session is recreated."
    ),
    "FS-012": (
        "FS-012: on legacy MClientRequest decode Pacific copies 8-bit num_retry/num_fwd into "
        "the extended counters used by getters, while Quincy leaves the extended values zero. "
        "Requests from clients using the legacy header can therefore be interpreted with "
        "different retry/forward counts during compatibility operation."
    ),
}
doc_reason = (
    "FS-DOC-01: screened endpoint hunks and commit intent cover CephFS reference, command, "
    "feature, recovery, mount, NFS, mirroring and man-page updates. These files are not an "
    "executed upgrade recipe or acceptance filter and have no independent rollout effect."
)
event_reason = (
    "FS-CODE-01: journal-event headers only qualify standard-library types/streams or use "
    "equivalent container construction; endpoint wire/journal encode versions and field order "
    "are unchanged, so this is build cleanup without an upgrade causal path."
)
message_reason = (
    "FS-CODE-02: screened non-exception CephFS message headers add Crimson factory friendship, "
    "qualify std types, or remove the unused non-encoded MMDSMap fs_name copy. Message version "
    "and payload encoding are unchanged; behavioral exceptions are FS-009, FS-010 and FS-012."
)
runtime_reason = (
    "FS-CODE-03: MetaRequest member initialization and cephfs_features namespace/formatting plus "
    "the unused CURRENT_RELEASE macro update are source cleanup/release labeling with no changed "
    "caller, persisted format, negotiated feature bit, or upgrade execution path."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert paths <= set(by_path)

for path, finding in affect_paths.items():
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect"
        assert row["finding_id"] == finding
        assert row["impact_reason"] == reasons[finding]

for cluster, reason in (
    (doc_paths, doc_reason),
    (event_paths, event_reason),
    (message_trivial_paths, message_reason),
    (runtime_trivial_paths, runtime_reason),
):
    for path in cluster:
        row = by_path[path]
        if row["upgrade_impact"]:
            assert row["upgrade_impact"] == "trivial"
            assert not row["finding_id"]
            assert row["impact_reason"] == reason

for path, finding in affect_paths.items():
    row = by_path[path]
    row["upgrade_impact"] = "affect"
    row["finding_id"] = finding
    row["impact_reason"] = reasons[finding]
for cluster, reason in (
    (doc_paths, doc_reason),
    (event_paths, event_reason),
    (message_trivial_paths, message_reason),
    (runtime_trivial_paths, runtime_reason),
):
    for path in cluster:
        row = by_path[path]
        row["upgrade_impact"] = "trivial"
        row["finding_id"] = ""
        row["impact_reason"] = reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

affect_count = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial_count = sum(row["upgrade_impact"] == "trivial" for row in rows)
blank_count = sum(not row["upgrade_impact"] for row in rows)
assert affect_count + trivial_count + blank_count == 427
assert (affect_count, trivial_count, blank_count) == (72, 216, 139)

finding_md = """### FS-009 — Quincy mất cơ chế trì hoãn eviction client khi OSD laggy của Pacific

- **CSV owner 11:** 2155, 2180, 2198–2199, 2265. **Nguồn:** `Beacon::notify_health()`, `MDSRankDispatcher::tick()`, `Server::{find_idle_sessions,evict_cap_revoke_non_responders}()` và `MMDSBeacon.h`. `src/common/options.cc` thuộc owner 06 cũng chứa việc option biến mất nhưng không nhân đôi hàng tại đây. Các commit chỉ có ở nhánh Pacific gồm `6168e621f68728f066f1c7a41058a4dd2bda7370`, `5452e25942bc1601bf6a05937aafdc3a9b681ab6`, `69602dbee0f33cdbb239ec7307128c181b163688` và `4f2c462923c0636c38e14c2d3fb37f759bd3739d`.
- **Trước → sau:** Pacific có option `defer_client_eviction_on_laggy_osds` với default true; khi giá trị hiệu lực true và OSDMap còn OSD laggy, MDS gom client đáng lẽ bị evict vào `laggy_clients`, trì hoãn eviction rồi phát health `MDS_CLIENTS_LAGGY`. Điều kiện này gồm As-Is giữ mặc định, không cần operator bật bằng tay. Endpoint Quincy không có option, set, nhánh guard hay health metric này, nên đi theo eviction thông thường.
- **Điều kiện và tác động:** Chỉ áp dụng nếu As-Is đã bật option Pacific và xảy ra đồng thời client chậm/cap revoke timeout với OSD laggy. Khi đó nâng lên Quincy có thể đổi từ giữ client sang evict/blocklist, làm gián đoạn mount/I/O và đồng thời mất cảnh báo giải thích nguyên nhân. **Mixed-version:** mỗi active MDS hành xử theo binary của nó; **full Quincy:** bảo vệ/cảnh báo không còn. Đây là khác biệt endpoint do backport lệch nhánh, không suy từ commit title. **Độ tin cậy:** cao về code, chưa biết applicability. **Kiểm chứng:** inventory option trước nâng; trong lab tạo OSD laggy có kiểm soát và client vượt ngưỡng, so sánh session, blocklist, health và reconnect ở Pacific/Quincy; chưa chạy lab.

### FS-010 — Quincy chờ ACK unlink từ replica MDS trước khi tái tạo cùng dentry

- **CSV:** 2157, 2169–2170, 2198–2199, 2244; hai hàng `Server` được ánh xạ chính sang FS-009 vì cùng file còn chứa cơ chế eviction. **Nguồn:** `CDentry::replica_unlinking_ref`, `MDCache::{send,handle}_dentry_unlink*()`, `Server` và `MDentryUnlink{,Ack}`; commit target `7005de0f6ff9bb1c154b3d28e7dfaad9abcf7030`. Pacific từng nhận backport tương tự nhưng endpoint 16.2.15 đã revert chuỗi đó, nên kết luận dựa vào net diff.
- **Trước → sau:** Pacific gửi unlink replica dạng v1 rồi tiếp tục luồng namespace. Quincy nâng `MDentryUnlink` lên v2/compat v1, thêm cờ `unlinking`, message ACK mới, pin dentry và đặt waiter `WAIT_UNLINK_STATE` đến khi mọi replica trả ACK; mục tiêu là tránh xung đột khi tạo lại cùng tên.
- **Điều kiện và tác động:** Kích hoạt khi namespace có dentry replica trên nhiều active MDS và unlink/rename cạnh tranh với create cùng tên. Quincy tránh race nhưng trong pha nhiều active rank chạy lẫn phiên bản, Pacific hiểu phần v1 song không có handler gửi ACK mới; rank Quincy có thể giữ waiter nếu không có feature gate khác. Recipe cần giảm active-rank skew hoặc chứng minh progress. **Full Quincy:** ACK hội tụ và tránh conflict. **Độ tin cậy:** cao về wire/caller, trung bình về mixed-version vì chưa chạy cluster. **Kiểm chứng:** lab multi-active với một Pacific/Quincy rank, lặp unlink-create/rename cùng dentry qua subtree replica, theo dõi waiter, request latency, message ACK và failover; chưa chạy lab.

### FS-011 — Quincy client không refresh feature bits khi MDS đã upgrade mở lại session

- **CSV:** 1547. **Nguồn:** `Client::handle_client_session()`; commit chỉ có ở endpoint Pacific `798cb2c306ec648d10cf14296de28f903df27e9d` (`client: always refresh mds feature bits on session open`).
- **Trước → sau:** Khi session đã `STATE_OPEN` lại nhận `CEPH_SESSION_OPEN`, Pacific vẫn gọi `reinit_mds_features()` rồi mới return, với chú thích trực tiếp cho trường hợp MDS vừa được upgrade. Quincy log “already opened, ignore it” và return mà không cập nhật `mds_features`/`mds_metric_flags`.
- **Điều kiện và tác động:** Cần client userspace được nâng trước hoặc giữ session trong lúc MDS đổi binary và gửi OPEN mới với feature set khác. Client Quincy có thể tiếp tục quyết định request/metric dựa trên bit cũ cho đến khi session được tạo lại; không kết luận kernel client bị ảnh hưởng. **Mixed-version:** là pha chính; **full-version sau reconnect:** bit được nạp khi mở session bình thường. **Độ tin cậy:** cao về code, trung bình về trigger. **Kiểm chứng:** nâng client trước MDS trong lab, giữ mount/I/O, chụp session feature bits trước/sau restart MDS và buộc reconnect để so sánh; chưa chạy lab.

### FS-012 — Quincy bỏ sao chép retry/forward legacy vào bộ đếm mở rộng

- **CSV:** 2239. **Nguồn:** `MClientRequest::decode_payload()`, `get_retry_attempt()` và `get_num_fwd()`; các backport Pacific `1c2334b778b18719fd259d44d60fc3cd38b0789`, `2644fbdba5a10038f242f1bf55906eca9805acc7`, `de4eba597007cae7bbdd7d2eca93d7e9db6d0242` giải thích nguồn khác biệt.
- **Trước → sau:** Cả hai endpoint có `ext_num_retry/ext_num_fwd` và getter đọc trường mở rộng. Với message header cũ (`header.version < 4`), Pacific sau `copy_from_legacy_head()` còn chép `num_retry/num_fwd` 8-bit sang trường mở rộng; Quincy không làm bước này, để giá trị mở rộng từ vùng head đã zero-init.
- **Điều kiện và tác động:** Chỉ request từ client đi qua encoding legacy mới khác; request header mới không bị ảnh hưởng. MDS Quincy có thể nhìn retry/forward thành 0, thay đổi xử lý replay/forward hoặc log chẩn đoán trong thời gian còn client cũ. **Mixed-version/full Quincy:** phụ thuộc phiên bản client, không chỉ phiên bản MDS. **Độ tin cậy:** cao về decode/getter, trung bình về tập client As-Is. **Kiểm chứng:** tạo request có retry/forward khác 0 từ client dùng legacy header đến MDS hai phiên bản, đối chiếu decoded counters, forward/replay và duplicate handling; chưa chạy lab.

"""

replace_known(
    md_path,
    "`affect = 61`, `trivial = 115`, chưa phân loại = 251",
    "`affect = 72`, `trivial = 216`, chưa phân loại = 139",
)
insert_before_once(md_path, "## Trivial changes", finding_md)
replace_known(
    md_path,
    "**115 hàng** đã sàng lọc: ngoài các cụm support `FS-QA-04–11`, bảy hàng `FS-QA-12` chỉ refactor framework hoặc sửa test/thrash tổng quát. Hai ngoại lệ harness được giữ `affect`: mount syntax trong FS-002 và hội tụ rank pre-upgrade trong FS-008.",
    "**216 hàng** đã sàng lọc: ngoài các cụm QA `FS-QA-04–12`, batch mới có 31 hàng tài liệu `FS-DOC-01`, 16 header journal-event `FS-CODE-01`, 51 message header không đổi wire payload `FS-CODE-02` và ba cleanup runtime `FS-CODE-03`. Các ngoại lệ hành vi/wire được giữ `affect` trong FS-009–012.",
)
replace_known(md_path, "Phân loại 251 hàng còn trống", "Phân loại 139 hàng còn trống")

replace_known(
    readme_path,
    "1.486 hàng `affect`. 1.611 hàng `trivial`. 1.082 hàng chưa phân loại.",
    "1.497 hàng `affect`. 1.712 hàng `trivial`. 970 hàng chưa phân loại.",
)
replace_known(
    readme_path,
    "[FS-001–008](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence/mount syntax, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy và hội tụ rank pre-upgrade",
    "[FS-001–012](./11-cephfs-mds.md) cho baseline client, MDS upgrade sequence/mount syntax, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy, hội tụ rank pre-upgrade, eviction khi OSD laggy, ACK unlink, refresh feature bits và legacy retry/fwd",
)
replace_known(
    readme_path,
    "[FS-001–008](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy và hội tụ rank pre-upgrade",
    "[FS-001–012](./11-cephfs-mds.md) về baseline client, MDS upgrade sequence, cephadm workload, no-FS gate, upgraded-client matrix, khoảng trống import legacy, hội tụ rank pre-upgrade, eviction khi OSD laggy, ACK unlink, refresh feature bits và legacy retry/fwd",
)
replace_known(readme_path, "vì 1.082 hàng còn thiếu nhãn và lý do", "vì 970 hàng còn thiếu nhãn và lý do")

replace_known(
    plan_path,
    "`affect 1.486`, `trivial 1.611`, còn **1.082 hàng chưa phân loại**",
    "`affect 1.497`, `trivial 1.712`, còn **970 hàng chưa phân loại**",
)
replace_known(
    plan_path,
    "owner 11 hiện `61 affect`, `115 trivial`, `251` chưa phân loại",
    "owner 11 hiện `72 affect`, `216 trivial`, `139` chưa phân loại",
)

print("Classified owner-11 runtime/wire batch: 11 affect, 101 trivial")
print(f"Owner totals: affect={affect_count} trivial={trivial_count} unclassified={blank_count}")
