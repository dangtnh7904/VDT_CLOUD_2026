ceph tell osd.5 version
ceph orch ps --daemon_type osd --daemon_id 5 \
  --format json --refresh
