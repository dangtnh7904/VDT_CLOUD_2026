event DURING PREPARE_AFFINITY
ceph osd primary-affinity osd.0 0
ceph osd primary-affinity osd.5 0
ceph pg ls-by-primary 0
ceph pg ls-by-primary 5
ceph -s
