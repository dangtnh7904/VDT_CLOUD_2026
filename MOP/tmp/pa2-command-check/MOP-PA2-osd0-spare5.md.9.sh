export ROOT='DIEN_ROOT_THUC'
export CLASS='DIEN_CLASS_HOAC_DE_TRONG'
export LAB_RULE="pa2_lab_osd_${RUN_ID}_${POOL}"
test "$ROOT" != 'DIEN_ROOT_THUC'
test "$CLASS" != 'DIEN_CLASS_HOAC_DE_TRONG'
if [[ -n "$CLASS" ]]; then
  ceph osd crush rule create-replicated "$LAB_RULE" "$ROOT" osd "$CLASS"
else
  ceph osd crush rule create-replicated "$LAB_RULE" "$ROOT" osd
fi
ceph osd crush rule dump "$LAB_RULE"
printf '%s\t%s\t%s\n' "$POOL" "$OLD_RULE_NAME" "$LAB_RULE" \
  >> "$EVIDENCE/rule-ledger.tsv"
event DURING "LAB_RULE_SWITCH:$POOL"
ceph osd pool set "$POOL" crush_rule "$LAB_RULE"
