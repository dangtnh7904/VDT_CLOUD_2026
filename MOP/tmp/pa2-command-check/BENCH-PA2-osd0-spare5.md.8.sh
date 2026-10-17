fio --name=pa2-rbd --filename="$BENCH_DIR/load.bin" \
  --rw=randrw --rwmixread=70 --bs=4k --size=512M \
  --ioengine=libaio --direct=1 --iodepth=8 --numjobs=1 \
  --time_based=1 --runtime=21600 --ramp_time=60 \
  --group_reporting=1 --percentile_list=50:95:99 \
  --write_bw_log="$EVIDENCE/bench/fio" \
  --write_iops_log="$EVIDENCE/bench/fio" \
  --write_hist_log="$EVIDENCE/bench/fio" \
  --log_avg_msec=1000 --log_hist_msec=1000 --log_unix_epoch=1 \
  --output-format=json+ --output="$EVIDENCE/bench/fio-total.json"
