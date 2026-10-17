set -euo pipefail
umask 077
export X=0 S=5
export EXPECTED_FSID='DIEN_FSID_LAB'
export TARGET_IMAGE='quay.io/ceph/ceph:v16.2.15'
export MOP_DIR="$HOME/pa2-osd0-spare5"
export HELPER="$MOP_DIR/pa2_osd0_spare5_check.py"
export RUN_ID="pa2-0-to-5-$(date -u +%Y%m%dT%H%M%SZ)"
export EVIDENCE="$MOP_DIR/evidence/$RUN_ID"
export TIMEOUT=1800 STABLE=300
test -f "$HELPER"
test "$EXPECTED_FSID" != 'DIEN_FSID_LAB'
test "$(ceph fsid)" = "$EXPECTED_FSID"
mkdir -p "$EVIDENCE"
declare -p X S EXPECTED_FSID TARGET_IMAGE MOP_DIR HELPER \
  RUN_ID EVIDENCE TIMEOUT STABLE > "$EVIDENCE/run.env"
