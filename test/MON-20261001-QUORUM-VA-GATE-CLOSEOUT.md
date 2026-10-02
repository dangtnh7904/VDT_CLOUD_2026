# Đối chiếu bốn mẫu quorum và đóng gate MON của run 01/10/2026

**Run ID:** `mon-20261001T092850Z-f9f494b7`  
**FSID:** `17c77e12-a16a-11f1-838e-cf68e9c001d8`  
**Phạm vi:** ba MON trên `ceph-node2`, `ceph-node3`, `ceph-master`; 16.2.5 → 16.2.15  
**Đối chiếu:** đọc file gốc trên `ceph-master` qua SSH ngày 02/10/2026; [MOP MON run](<../MOP/MOP-MON-16.2.5-to-16.2.15 (1).md>), [GATE MON run](<./GATE-MON-16.2.5-to-16.2.15 (1).md>) và ảnh trong `MOP/MOP MON.docx`.

## 1. Trạng thái có thể kết luận hiện nay

Ảnh cuối và `after-orch.json` xác nhận cả ba MON `running` ở 16.2.15, cùng image ID rút gọn `f15b41add2c0`. Timeline gốc có **2.083 mẫu, 2.079 mẫu hợp lệ đều quorum 3/3**; leader của các mẫu hợp lệ là `ceph-master`. Bốn mẫu `rc=1` đều xảy ra **trước yêu cầu redeploy đầu tiên lúc 14:51:27Z**. File `quorum-errors.log` chứa đúng bốn traceback giống nhau: `cephadm` gọi `_infer_config → list_daemons → with_units_to_int`, parse giá trị memusage `--` rồi ném `ValueError: could not convert string to float: '--'`. Đây là lỗi của đường gọi CLI/observer trước khi truy vấn Ceph hoàn tất; không có bằng chứng tại bốn mốc cho thấy MON mất quorum.

**MG0–MG8 vẫn HOLD ở mức gate tổng thể.** Phân loại được bốn mẫu chỉ giải quyết một finding của MG6. Auth và S3 dừng lúc 16:33Z, trước khi đủ 30 phút sau MON cuối; hồ sơ còn thiếu digest từng host, corpus/manifest, reopen/checksum, journal rollout của hai host follower và cleanup. Không đổi HOLD sang PASS dựa trên việc đã nâng xong phiên bản.

S3 smoke độc lập ngày 02/10 (`mon-s3-smoke-20261002T042757Z-4cc3dedd`) có 58/58 mẫu PUT+GET thành công trong 120,716 giây, GET/checksum bằng boto3 client mới và cleanup PASS. Đây là kết quả **S3-only hai phút**, không kiểm MON/quorum, auth hay RBD và không đủ gate client 30 phút của run 01/10; chi tiết ở mục 6.

Bốn bản ghi `ok=false, rc=1` ở `13:26:38Z`, `13:31:35Z`, `14:37:09Z`, `14:41:28Z` ngày 01/10 cho thấy **observer không thu được mẫu quorum hợp lệ**. Vòng observer trong GATE dùng chung biến `rc` cho lệnh `ceph quorum_status` và bước `jq -e`; chỉ riêng `rc=1` không xác định được nhánh lỗi. File stderr gốc đã phân loại nhánh `cephadm`. `quorum-errors.log` không có timestamp riêng cho từng traceback, nên ghép bốn lỗi theo số lượng và thứ tự ghi; `quorum-current.json` và `.err` bị ghi đè ở vòng sau.

| Mẫu UTC 01/10 | Giờ Việt Nam | Cửa sổ đối chiếu UTC, ±3 phút |
| --- | --- | --- |
| 13:26:38Z | 20:26:38 | 13:23:38–13:29:38 |
| 13:31:35Z | 20:31:35 | 13:28:35–13:34:35 |
| 14:37:09Z | 21:37:09 | 14:34:09–14:40:09 |
| 14:41:28Z | 21:41:28 | 14:38:28–14:44:28 |

Timeline có hai khoảng trống lớn **10:09:14–12:41:08** (9.114 giây) và **13:32:40–13:50:29** (1.069 giây), đều trước rollout. Trong các đoạn hợp lệ sau từng MON, epoch lần lượt lên 546, 550, 552; leader không đổi. Các đoạn quorum 3/3 liên tiếp sau `ceph-node2`, `ceph-node3`, `ceph-master` lần lượt dài **55 phút 19 giây**, **15 phút 16 giây**, **46 phút 45 giây**. Các đoạn này hỗ trợ tiêu chí thời gian của quorum; hai khoảng trống cũ vẫn phải ghi trong hồ sơ MG3.

| Client CSV của run | Khoảng UTC | Mẫu hợp lệ/lỗi | p95 toàn file | Phủ bốn mốc `rc=1` |
| --- | --- | ---: | ---: | --- |
| RBD | 13:21:01–16:55:41 | 12.708 / 0 | 26,389 ms | Cả bốn; lần lượt 357, 356, 357, 357 mẫu thành công trong cửa sổ ±3 phút |
| Auth | 14:25:21–16:33:44 | 1.301 / 0 | 1 748 ms | Chỉ hai mốc sau: 62, 61 mẫu thành công |
| S3 | 13:52:49–16:33:31 | 1.103 / 0 | 8 491 ms | Chỉ hai mốc sau: 43, 41 mẫu thành công |

Journal `mon.ceph-master` đọc được bằng `journalctl` tại bốn cửa sổ ±60 giây vẫn ghi trạng thái leader; không tìm thấy election/quorum change ở các cửa sổ đó. SSH đến `ceph-node2` và `ceph-node3` bằng khóa hiện có bị từ chối, nên chưa có journal hai host trong cửa sổ rollout. RBD CSV có 180 byte NUL ở cuối sau bản ghi hợp lệ cuối; đã bỏ phần NUL khi đếm, giữ file gốc để đối chiếu. S3 `s3-get.bin` khớp `s3-last-verified.bin`; `s3-payload.bin` được ghi lại sau mẫu thành công cuối, nên chênh hash giữa payload hiện tại và bản đã xác minh không chứng minh lỗi của vòng đã hoàn tất.

## 2. File gốc và dấu vết kiểm tra

Trên `ceph-master`, evidence chia ở ba thư mục. Giữ file nguyên bản, mtime, host, timezone UTC và SHA-256 khi sao lưu; không chạy lại probe rồi gán kết quả cho run 01/10.

```bash
RUN_ID='mon-20261001T092850Z-f9f494b7'
EVIDENCE="/home/dangg/mgr-mop-20260930T093558Z/evidence-$RUN_ID"
CLIENT_EVIDENCE="/home/dangg/mgr-mop-20260930T093558Z/client-evidence-$RUN_ID"
RBD_EVIDENCE="/home/dangg/evidence-$RUN_ID"

find "$EVIDENCE" -maxdepth 2 -type f -printf '%P\t%s bytes\t%TY-%Tm-%TdT%TH:%TM:%TS\n' | sort
jq -c 'select(.ok == false)' "$EVIDENCE/quorum-timeline.jsonl"
sha256sum "$EVIDENCE/quorum-timeline.jsonl" "$EVIDENCE/quorum-errors.log" \
  "$CLIENT_EVIDENCE/auth.csv" "$CLIENT_EVIDENCE/s3.csv" "$RBD_EVIDENCE/rbd.csv"
```

| File | SHA-256 trên host ngày 02/10 |
| --- | --- |
| `quorum-timeline.jsonl` | `fead487e6e0de45b4f056b722301b9099eda321f9dc8268f712d715817ca8c7e` |
| `quorum-errors.log` | `ff4c9615165df6446d324e9b7d461849f01ef6160ed7096f3196cdb9b1c6eb06` |
| `auth.csv` ở `CLIENT_EVIDENCE` | `0d51e2d8a9684e298c18aac7b0432ff5de45f0061c5532a3989db41d0efa853a` |
| `s3.csv` ở `CLIENT_EVIDENCE` | `6f2424da10548b09597b53ca956bc879d944ba7c49488a3bf6a67ff308bb99d5` |
| `rbd.csv` ở `RBD_EVIDENCE` | `a0e68f8ea06d3c5172cd2f334f89f9fa43aefa160351e26b2b86008c150b0890` |

Không chép keyring, secret S3 hoặc file cấu hình chứa khóa vào báo cáo. Thư mục admin không có `phases.tsv`, manifest corpus hoặc các file post/cleanup đầy đủ; hai thư mục client cũng không có bằng chứng reopen RBD sau khi dừng probe.

## 3. Cách tái kiểm bốn mẫu `rc=1`

Đọc bản ghi trước/sau lỗi trong `quorum-timeline.jsonl`, stderr cùng mốc trong `quorum-errors.log`, mốc redeploy và CSV client. Ví dụ cho mẫu đầu:

```bash
FROM='2026-10-01T13:23:38Z'
TO='2026-10-01T13:29:38Z'
jq -c --arg from "$FROM" --arg to "$TO" \
  'select(.at >= $from and .at <= $to)' \
  "$EVIDENCE/quorum-timeline.jsonl"

for file in auth.csv s3.csv; do
  awk -F, -v from="$FROM" -v to="$TO" \
    '$1 >= from && $1 <= to {print}' "$CLIENT_EVIDENCE/$file"
done
awk -F, -v from="$FROM" -v to="$TO" \
  '$1 >= from && $1 <= to {print}' "$RBD_EVIDENCE/rbd.csv"
```

Lặp với ba cửa sổ còn lại trong bảng. Tính số mẫu thành công, lỗi, khoảng mất mẫu và p95 theo từng pha từ CSV gốc; không bỏ bốn mẫu observer lỗi khỏi mẫu số timeline. `quorum-errors.log` của run này chỉ có bốn traceback nối nhau, không có dòng timestamp hoặc `rc=`. Stderr rỗng trong một run khác cũng không tự chứng minh nhánh `jq` lỗi, vì lệnh Ceph có thể trả nonzero mà không in stderr.

Trên **cả ba host MON**, đọc journal của đúng unit trong bốn cửa sổ. Ví dụ cho mẫu đầu trên host tương ứng; thay `MON_ID` và cửa sổ theo bảng:

```bash
FSID='17c77e12-a16a-11f1-838e-cf68e9c001d8'
MON_ID='ceph-node2' # lặp ceph-node3 và ceph-master trên đúng host
journalctl -u "ceph-$FSID@mon.$MON_ID.service" \
  --since '2026-10-01 13:23:38 UTC' \
  --until '2026-10-01 13:29:38 UTC' \
  --utc --no-pager
```

Ghi các sự kiện stop/start, election, rejoin, auth, Paxos, crash hoặc lỗi network/clock. Đối chiếu `election_epoch`, leader, quorum 3/3 và các mẫu client cùng mốc. Journal `ceph-master` đọc được bằng `journalctl` không cần sudo; SSH đến `ceph-node2` và `ceph-node3` bằng khóa hiện có bị từ chối. File `ceph-master-mon-journal-before-cleanup.txt` trong evidence chỉ đến `13:44:17Z`, không phủ hai lỗi sau hoặc rollout. `ceph quorum_status` chạy hôm nay chỉ xác nhận trạng thái hôm nay.

**Verdict riêng cho bốn mẫu:** lỗi `cephadm` ở đường CLI/observer; không phân loại là sự cố MON/quorum. Mỗi mẫu có quorum 3/3, leader `ceph-master`, epoch 542 ở hai phía của mẫu lỗi; RBD probe thành công trong cả bốn cửa sổ. Journal leader không có sự kiện election/quorum change tại ±60 giây quanh bốn mốc. Auth/S3 chưa chạy tại hai mốc đầu, nên không ghi rằng cả ba client stream đã chứng minh continuity cho hai mốc đó. Các khoảng trống timeline cũ và thiếu journal hai follower ngăn việc phát biểu “không gián đoạn trong toàn run”.

## 4. Ma trận đóng MG0–MG8

| Gate | Phần đã đối chiếu từ file gốc | Phần còn thiếu hoặc finding giữ HOLD |
| --- | --- | --- |
| MG0 | FSID, quorum 3/3, pre-version; MGR active `ceph-node3.eniabu`, standby `ceph-master.ezhuly`; upgrade không chạy | Thiếu `pre-hosts`, service spec, OSD/map export và bằng chứng phục hồi; pre-health lúc 09:49 có `MON_DISK_LOW` |
| MG1 | Target image và runtime version có trong file | Thiếu clock, disk/inode, endpoint, RepoDigest từng host trước thao tác; chưa giải thích `MON_DISK_LOW` (ceph-master 23% available) dù health về OK trước rollout |
| MG2 | `config-original.json`, ba MON config-before | Thiếu OSD effective config, snapshot sau nâng, diff và sổ thay đổi/hoàn nguyên |
| MG3 | Có ứng viên baseline bốn luồng 14:42–14:56, không lỗi được ghi; auth 141, S3 96, RBD 836 mẫu | Thiếu corpus/manifest cố định; timeline có khoảng trống lớn trước rollout và gap 18 giây trong baseline; thiếu phase manifest |
| MG4 × 3 | `after-orch` và `mon-status` xác nhận target 16.2.15; timeline có ba đoạn quorum ổn định 55m19s, 15m16s, 46m45s | `ceph-node2.after-quorum.json` rỗng; thiếu mã trả về ok-to-stop, RepoDigest/runtime từng host, mốc stop/rejoin và journal follower. Khoảng 15:32–15:53 của node3 cần giải thích theo ngưỡng queue 300 giây |
| MG5 | Canary có 3/3 từ 14:57:35–15:52:54; auth 566, S3 386, RBD 3.279 mẫu, đều không lỗi; p95 nằm trong ngưỡng đề xuất | Thiếu corpus, journal/map/store và diff cấu hình trong cửa sổ mixed-version |
| MG6 | Bốn lỗi observer đã phân loại; epoch 546/550/552 sau redeploy; leader của mẫu hợp lệ không đổi | Thiếu journal rollout trên follower, đối chiếu MON store/map và nhánh CephX rotation T11 nếu thuộc phạm vi |
| MG7 | Quorum timeline và RBD tiếp tục đến 16:55Z; ba MON có runtime target | Auth dừng 16:33:44Z, S3 dừng 16:33:31Z, trước mốc 30 phút sau MON cuối; thiếu reopen/checksum RBD, corpus và post inventory/config/host state của run 01/10 |
| MG8 | Chưa thấy evidence kết thúc của run 01/10 trong ba thư mục | Thiếu stop marker, cleanup/giữ fixture, hoàn nguyên, hậu kiểm ≥5 phút và bàn giao của run đó |

Mỗi gate chỉ đổi HOLD sang PASS sau khi người review đối chiếu file gốc, mốc thời gian, ngưỡng đã chốt và N/A có lý do theo inventory. T11 CephX rotation và nhánh failback cần kết luận riêng; smoke auth và ba MON ở target không đóng các nhánh đó. Với MG7, kể cả lấy mốc quorum 3/3 sớm nhất sau MON cuối là `16:08:44Z`, auth/S3 đều dừng trước `16:38:44Z`; mốc xác nhận runtime target `16:12:48Z` làm khoảng thiếu dài hơn.

Nếu dữ liệu lịch sử không đủ, giữ run 01/10 với kết quả **nâng phiên bản 3/3 MON đã xác nhận, nghiệm thu vận hành HOLD**. Có thể thu bổ sung trạng thái hiện tại để chứng minh current health, song phải gắn mốc 02/10 hoặc mới hơn. Muốn chứng minh toàn bộ quy trình 16.2.5 → 16.2.15, lập run mới trên lab/clone phục hồi từ baseline trước nâng, thu bốn luồng từ trước canary qua sau MON cuối; không redeploy lại ba MON đang ở target chỉ để tạo hồ sơ cho run cũ.

## 5. Sửa observer cho run kế tiếp

Ở vòng lặp hiện tại, lưu riêng `command_rc` và `json_rc`, cùng stdout/stderr theo timestamp và host; chỉ ghi `ok=true` khi cả hai bằng 0. Khi lỗi, giữ nguyên bản `quorum-current.json/.err` của mẫu đó thay vì để vòng sau ghi đè. Ghi timestamp bắt đầu/kết thúc để thấy thời gian CLI bị treo, và ghi parser error khi JSON sai schema. Mọi mẫu lỗi vẫn nằm trong timeline và ma trận gate.

Tham chiếu vận hành: [Ceph Pacific monitor troubleshooting](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-mon/), [Cephadm daemon logs](https://docs.ceph.com/en/pacific/cephadm/operations/) và [Ceph health checks](https://docs.ceph.com/en/pacific/rados/operations/health-checks/).

## 6 Kiểm tra trực tiếp bổ sung ngày 02/10/2026

SSH vào `ceph-master` bằng tài khoản `dangg` lúc 04:00–04:07 UTC. File `quorum-errors.log` trên host vẫn chứa đúng bốn traceback `cephadm` parse `MemUsage='--'`; mốc lỗi trong timeline đều trước yêu cầu redeploy MON đầu tiên. Đây là xác nhận lại phân loại từ raw evidence của run 01/10, không phải một phép thử upgrade mới.

Tại 04:07:15Z, unit `mon.ceph-master` ở trạng thái `active`, `NRestarts=0`, tiến trình hiện tại bắt đầu lúc 03:58:22Z. Journal của unit ghi `ceph-master` trở thành leader và quorum gồm `ceph-master`, `ceph-node2`, `ceph-node3` lúc 03:58:23Z sau khi host khởi động. Đây là ảnh trạng thái trên **một host** sau lần khởi động mới; chưa chứng minh 30 phút liên tục của quorum và client I/O.

Tại thời điểm kiểm 04:07Z, `dangg` không đọc được `/etc/ceph/ceph.client.admin.keyring`; `sudo -n ceph` yêu cầu mật khẩu. Vì vậy chưa chạy được `ceph -s`, `quorum_status`, auth/RBD/S3 probe đồng thời trong một cửa sổ mới. Quyền Ceph CLI đang được bổ sung. Khi chạy được, tạo RUN_ID và thư mục raw evidence riêng cho phép kiểm chung; không sửa CSV/timeline của run 01/10 và không đổi MG7 sang PASS chỉ bằng trạng thái hiện tại.

### S3 smoke độc lập lúc 04:27–04:29Z

| Thuộc tính | Kết quả |
| --- | --- |
| RUN_ID | `mon-s3-smoke-20261002T042757Z-4cc3dedd` |
| Evidence trên `ceph-master` | `/home/dangg/mon-s3-smoke-20261002T042757Z-4cc3dedd` |
| Bản sao trong workspace | [manifest.json](./evidence-s3-20261002/manifest.json), [summary.json](./evidence-s3-20261002/summary.json), [s3.csv](./evidence-s3-20261002/s3.csv) |
| Cửa sổ UTC | 02/10/2026 04:27:58–04:29:58; elapsed 120,716 giây |
| S3 PUT+GET | 58 mẫu, 0 failure |
| Reopen/checksum | PASS: tạo boto3 client mới rồi GET/checksum **cùng object** ở cuối run |
| Cleanup | PASS |

CSV có 58 bản ghi `PUT_GET_MATCH`, `rc=0`; mẫu đầu 04:27:58Z, mẫu cuối 04:29:56Z, run kết thúc 04:29:58Z. SHA-256 của bản sao workspace: `s3.csv` = `caa42458a3080d77b986c868da25dffa68bb51393791a34fab6115c7f9262f2d`; `summary.json` = `4b9706b3f1e0eea028ced9c200e241519a547078996c49bf0a9e5ea401d82e1d`.

Kết quả này chứng minh đường S3 PUT+GET và phép GET/checksum cuối run hoạt động trong đúng cửa sổ **hai phút** đã ghi. `Reopen=PASS` không có nghĩa RGW/host đã restart hoặc object được reopen sau thời gian soak dài. Probe không chạy Ceph MON/quorum CLI, auth hay RBD; do đó không suy ra các luồng đó hoạt động trong cửa sổ trên. Nó cũng không nối dài CSV S3 của run 01/10 hoặc bổ sung đủ 30 phút sau MON cuối của run cũ. **MG0–MG8, gồm MG7, giữ HOLD.** Một phép kiểm chung ≥30 phút phải có RUN_ID, timestamp và raw evidence riêng, với quyền Ceph CLI và các luồng client cần thiết.

### Phép kiểm đầy đủ sẽ chạy sau

Đã chuẩn bị bản nháp [script MON/quorum](./mon_current_soak_20261002.sh) và [script auth/RBD/S3](./mon_current_clients_20261002.py) cho run mới. Chúng đã qua kiểm cú pháp và ca kiểm giả lập, **chưa chạy trên lab**. Trước khi thực thi cần xác nhận quyền Ceph CLI, FSID, pool/bucket test, khả năng dọn image/object tạm và được người vận hành duyệt thao tác ghi; sau run phải đối chiếu raw log, thời gian giao nhau đủ 30 phút và cleanup rồi mới xem lại gate. Kết quả run mới sẽ có RUN_ID riêng, không ghi đè hồ sơ 01/10.
