ceph orch ps --daemon_type osd --daemon_id 0 --format json --refresh
ceph tell osd.0 version
ceph osd metadata 0 -f json
ceph osd tree
ceph health detail
ceph crash ls-new
