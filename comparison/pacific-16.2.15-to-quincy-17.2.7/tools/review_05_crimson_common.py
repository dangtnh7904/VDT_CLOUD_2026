"""Classify inspected Crimson common runtime, recovery and diagnostic paths."""

import csv
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "05-messaging-auth-common.csv"
affect = {
    "src/crimson/common/config_proxy.h": ("MSG-065", "Crimson ConfigProxy now parses CEPH_ARGS environment through parse_env invoked by OSD main, changing effective startup config."),
    "src/crimson/common/condition_variable.h": ("MSG-066", "New interruption-aware condition variable is used by SeaStore segment rotation wait/action loop."),
    "src/crimson/common/errorator-loop.h": ("MSG-066", "New parallel_for_each propagates typed errors from concurrent futures used by Crimson recovery and SeaStore writes."),
    "src/crimson/common/errorator.h": ("MSG-066", "Typed future/error handling adds repeat, parallel_for_each and visitor result paths used during interrupted operations."),
    "src/crimson/common/exception.h": ("MSG-066", "Shutdown and acting-set exceptions now share interruption base, altering typed cancellation handling in Crimson OSD."),
    "src/crimson/common/interruptible_future.h": ("MSG-066", "New interruptible future/condition and parallel continuation machinery changes cancellation propagation in Crimson recovery and PG operations."),
    "src/crimson/common/utility.h": ("MSG-066", "New assert_moveable helper is used by errorator future continuations to reject const move-out at build time."),
    "src/crimson/common/fatal_signal.cc": ("MSG-067", "Crimson installs one-shot fatal signal handlers, emits stacktrace/siginfo/proc maps, then reraises for core handling."),
    "src/crimson/common/fatal_signal.h": ("MSG-067", "Declares FatalSignal installed by Crimson OSD main during startup."),
    "src/crimson/common/fixed_kv_node_layout.h": ("MSG-068", "SeaStore fixed-key node lower/upper bound switches from linear scan to binary search over indexed keys."),
    "src/crimson/common/log.h": ("MSG-069", "Crimson debug level 5 maps to Seastar info instead of debug, changing rollout log volume and filtering."),
    "src/crimson/common/logclient.cc": ("MSG-070", "New Crimson LogClient queues cluster log entries, sends MLog and handles MLogAck while routing channels to MON/syslog/Graylog."),
    "src/crimson/common/logclient.h": ("MSG-070", "Declares Crimson cluster log queue/channel lifecycle used by OSD and MonClient."),
    "src/crimson/common/operation.cc": ("MSG-071", "New Operation/Blocker dump implementation exposes active operation and blocker details for Crimson diagnostics."),
    "src/crimson/common/operation.h": ("MSG-071", "New operation pipeline/blocker/UnorderedStage abstractions are used by SeaStore ordering and Crimson OSD operations."),
    "src/crimson/common/perf_counters_collection.cc": ("MSG-072", "Crimson perf counter collection adds admin dump and deleter that unregisters counters on destruction."),
    "src/crimson/common/perf_counters_collection.h": ("MSG-072", "Declares sharded perf dump/deleter used by Crimson admin socket and counter owners."),
    "src/crimson/common/shared_lru.h": ("MSG-073", "SharedLRU destructor clears weak_refs instead of asserting empty, changing shutdown handling when external references outlive cache."),
    "src/crimson/common/tri_mutex.h": ("MSG-074", "excl_from_excl now returns the matching lock adapter type used by ObjectContext exclusive flows."),
}
trivial = {
    "src/crimson/common/throttle.cc": "T05-crimson-throttle: Rewrites unsigned max truth tests as ==0u; count/wait/put branches unchanged.",
    "src/crimson/common/tri_mutex.cc": "T05-crimson-trimutex: Rewrites unsigned readers/writers truth tests as ==0u/!=0u; lock transitions unchanged.",
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
