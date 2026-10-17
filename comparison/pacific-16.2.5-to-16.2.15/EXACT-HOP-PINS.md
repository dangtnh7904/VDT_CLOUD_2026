# Exact-hop pin register cho Pacific 16.2.5 → 16.2.15

**Trạng thái ngày 12/10/2026: 12/12 pin `PENDING_INPUT`.** Audit target SHA `618f440892089921c3e944a991122ddc44e60516` xác nhận `qa/suites/upgrade/pacific-p2p` có 29 entry, 24 YAML parse sạch và không có symlink. Tuy nhiên recipe parallel ghi rõ đường `v16.2.5→v16.2.7→latest Pacific`, stress-split dùng `latest.point→latest`, có 4 `branch: pacific`, một workload `branch: octopus`, distro `ubuntu_latest`, cùng lệnh đặt release/client floor. Vì vậy recipe này **không phải direct-hop evidence** cho `v16.2.5→v16.2.15` nếu chưa adapt và pin.

[Manifest template](./EXACT-HOP-PIN-MANIFEST.template.json) cố ý mang nhãn `NOT_EXACT_HOP_VALID`. Chỉ bản sao theo từng run, có artifact/harness/archive evidence thật và qua shared validator ở `--mode locked`, mới được mang nhãn `EXACT_HOP_VALID`.

| Pin | Khoảng trống cần khóa | Evidence bắt buộc | Gate/test chính | Trạng thái |
| --- | --- | --- | --- | --- |
| PIN-01 | Base artifact phải đúng `v16.2.5`, không chỉ “latest.point-1” | Package/image identity và source SHA từ deployed payload | `G00`, `T00` | PENDING_INPUT |
| PIN-02 | Recipe parallel chen mốc `v16.2.7` | Expanded job chứng minh direct hop, hoặc disposition lane trung gian tách biệt | `G13`, `T09B` | PENDING_INPUT |
| PIN-03 | `latest Pacific`, `force-branch` và 4 branch selector nổi | Exact ref/package/image cho từng install/workunit | `G00`, `G13`, `T09` | PENDING_INPUT |
| PIN-04 | Target artifact phải đúng `v16.2.15` | Immutable digest/NEVRA, image inspect, source/package provenance | `G00`, `T00` | PENDING_INPUT |
| PIN-05 | Install task không có completion oracle theo digest/role | Versions, daemon inventory, expected/observed counts và checksum | `G01`, `G13`, `T09` | PENDING_INPUT |
| PIN-06 | `ubuntu_latest` không phải distro lane bất biến | OS image, kernel, runtime và architecture khớp cohort As-Is | `G12`, `T29`, `T29A`, `T29B` | PENDING_INPUT |
| PIN-07 | Delivery registry/repository/retention chưa khóa | Pull/install reproducibility và mirror evidence | `G00`, `G08`, `T00`, `T26` | PENDING_INPUT |
| PIN-08 | Workload branch Pacific/Octopus không đồng nhất endpoint | Workload commit/package và lý do legacy-client lane | `G07`, `G10`, `G13`, `T28` | PENDING_INPUT |
| PIN-09 | Ceph suite, teuthology/helper/local patch chưa pin | Git SHA, expanded YAML và patch checksum | `G13`, `T09`, `T09A` | PENDING_INPUT |
| PIN-10 | Client-old/new và external consumers cần matrix riêng | Client package/digest, bindings và kết quả hai hướng | `G06`, `G07`, `G10`, `T15`, `T28` | PENDING_INPUT |
| PIN-11 | Recipe tự đặt require-osd-release và min-compatible-client Pacific | Fixture quarantine, approval và rollback/old-client negative evidence | `G03`, `G13`, `T10`, `T17A` | PENDING_INPUT |
| PIN-12 | Recipe không định nghĩa archive completeness/rerun identity | Run ID, seed, topology, timeline, raw output, archive hash và owner | `G13`, mọi `T00`→`T38` applicable | PENDING_INPUT |

PIN-01→09 và PIN-12 phải `LOCKED`; PIN-10/11 phải `LOCKED` hoặc `NOT_APPLICABLE` có evidence. Đặc biệt, một run đi qua 16.2.7 có thể hữu ích như lane riêng nhưng không được dán nhãn direct exact-hop 16.2.5→16.2.15.
