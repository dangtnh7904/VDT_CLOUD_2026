# Terminal collector: EVIDENCE da tro dung run.
mkdir -p "$EVIDENCE/collector"
while [[ ! -f "$EVIDENCE/collector.stop" ]]; do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  for KIND in status osd_perf osd_df pg_stat; do
    case "$KIND" in
      status) CMD=(ceph -s -f json) ;;
      osd_perf) CMD=(ceph osd perf -f json) ;;
      osd_df) CMD=(ceph osd df -f json) ;;
      pg_stat) CMD=(ceph pg stat -f json) ;;
    esac
    RC=0
    timeout 15 "${CMD[@]}" \
      > "$EVIDENCE/collector/$T.$KIND.json" \
      2> "$EVIDENCE/collector/$T.$KIND.stderr" || RC=$?
    printf '%s\t%s\t%s\t%s\n' "$T" "$KIND" "$RC" \
      "$(date -u +%FT%TZ)" >> "$EVIDENCE/collector/manifest.tsv"
  done
  sleep 10
done
