# Primary-affinity goc de ban giao dung chinh sach.
jq -r '.osds[] | select(.osd==0 or .osd==5)
  | [.osd,.primary_affinity] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/affinity.before.tsv"

# Du lieu de restore sau nay; chua restore o cuoi luot lab nay.
jq -r '.pools[] | [.pool_name,.pg_autoscale_mode] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/autoscale.before.tsv"
jq -r '.pools[] | [.pool_name,.crush_rule,.size,.min_size] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/pools.before.tsv"

python3 "$HELPER" isolate --pgs "$EVIDENCE/00-pgs.json" --osd 5
jq '.osds[] | select(.osd==0 or .osd==5)
  | {osd,up,in,weight,primary_affinity,uuid}' "$EVIDENCE/00-osd.json"
jq '{choose_args,buckets}' "$EVIDENCE/00-crush.json"
