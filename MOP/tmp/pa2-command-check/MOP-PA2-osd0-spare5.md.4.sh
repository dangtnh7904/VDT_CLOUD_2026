event DURING FREEZE_PLACEMENT
ceph balancer off
while IFS=$'\t' read -r POOL MODE; do
  case "$MODE" in
    on|off|warn) ceph osd pool set "$POOL" pg_autoscale_mode off ;;
    *) echo "HOLD: unknown mode for $POOL"; exit 1 ;;
  esac
done < "$EVIDENCE/autoscale.before.tsv"
ceph osd dump -f json | jq '{flags,pools:
  [.pools[] | {pool,pool_name,pg_num,pg_placement_num,
    pg_num_target,pg_placement_num_target}]}'
ceph -s
