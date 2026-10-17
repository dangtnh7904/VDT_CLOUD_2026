hostname
date -u +%FT%TZ
iostat -x -t 5 > pa2-iostat.txt
# Terminal rieng khac:
sar -n DEV 5 > pa2-network.txt
