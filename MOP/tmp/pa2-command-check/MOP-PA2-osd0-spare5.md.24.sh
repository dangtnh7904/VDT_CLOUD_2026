event DURING HANDOFF_COMPLETE
export A5_SERVING=1
ceph osd primary-affinity osd.5 "$A5_SERVING"
ceph pg ls-by-primary 5
ceph -s
