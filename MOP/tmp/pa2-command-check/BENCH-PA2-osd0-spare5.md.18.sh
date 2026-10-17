touch "$EVIDENCE/collector.stop"
touch "$EVIDENCE/bench/job-observer.stop"
event END BENCH_STOPPED
ceph versions -f json > "$EVIDENCE/bench/daemon-versions.after.json"
