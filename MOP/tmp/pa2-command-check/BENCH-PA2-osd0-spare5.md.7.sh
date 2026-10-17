export RBD_MOUNT='/DIEN_MOUNT_RBD_LAB'
test "$RBD_MOUNT" != '/DIEN_MOUNT_RBD_LAB'
mountpoint -q "$RBD_MOUNT"
findmnt -T "$RBD_MOUNT" | tee "$EVIDENCE/bench/rbd-mount.txt"
rbd device list --format json > "$EVIDENCE/bench/rbd-devices.json"
df -h "$RBD_MOUNT"
export BENCH_DIR="$RBD_MOUNT/pa2-$RUN_ID"
test ! -e "$BENCH_DIR"
mkdir -p "$BENCH_DIR"
fio --version > "$EVIDENCE/bench/fio.version.txt"
uname -a > "$EVIDENCE/bench/client-kernel.txt"

fio --name=seed --filename="$BENCH_DIR/load.bin" \
  --rw=write --bs=1M --size=512M --ioengine=libaio \
  --direct=1 --iodepth=4 --refill_buffers=1 --end_fsync=1 \
  --output-format=json --output="$EVIDENCE/bench/fio-seed.json"
dd if=/dev/urandom of="$BENCH_DIR/sentinel.bin" \
  bs=1M count=4 conv=fsync status=none
sha256sum "$BENCH_DIR/sentinel.bin" \
  > "$EVIDENCE/bench/rbd-sentinel.before.sha256"
