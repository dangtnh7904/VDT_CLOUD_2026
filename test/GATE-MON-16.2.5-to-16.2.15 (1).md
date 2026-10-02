# Kiểm tra và nghiệm thu nâng cấp Ceph MON từ 16.2.5 lên 16.2.15

**Ngày lập:** 02/10/2026  
**Lần lab được đánh giá:** `mon-20261001T092850Z-f9f494b7`  
**Tài liệu thao tác:** [MOP MON](./MOP-MON-16.2.5-to-16.2.15.md)

## 1 Mục đích và nguyên tắc đánh giá

Tài liệu quy định các kiểm tra trước, trong và sau khi nâng ba MON. Mỗi điểm kiểm tra có mã MG để MOP dẫn chiếu; bảng ở mục 3 liên kết các mã này với checklist chung của dự án.

Ba MON trong lần lab đã nâng xong. Ảnh cuối xác nhận cả ba chạy 16.2.15. Việc đánh giá các điều kiện trong quá trình nâng phải dựa vào log và ảnh của lần chạy đó. Kiểm tra thực hiện thêm sau ngày nâng chỉ xác nhận trạng thái tại thời điểm mới, không thay thế baseline hoặc khoảng theo dõi đã thiếu.

### 1.1 Cách ghi kết quả

| Kết quả | Cách sử dụng |
| --- | --- |
| PASS | Có đủ bằng chứng và đáp ứng tiêu chí đã xác định |
| FAIL | Có bằng chứng vi phạm tiêu chí |
| HOLD | Chưa thể quyết định vì thiếu dữ liệu hoặc còn sự kiện cần điều tra |
| NOT RUN | Chưa thực hiện phép kiểm tra |
| N/A | Không áp dụng; phải nêu lý do và dẫn chứng về phạm vi |

Khi đang rollout, HOLD hoặc FAIL ở điều kiện bắt buộc chặn bước nâng tiếp theo. Khi tổng hợp hồ sơ của lần đã hoàn thành, HOLD thể hiện chưa đủ căn cứ nghiệm thu tiêu chí đó; không thay đổi sự thật rằng ba daemon đã chạy bản mới.

Không chuyển lỗi thành PASS bằng cách bỏ mẫu lỗi, khởi động lại phép đo rồi chỉ lấy đoạn tốt, hoặc thay ngưỡng sau khi đã nhìn thấy kết quả.

### 1.2 Ngưỡng đánh giá

Các ngưỡng dưới đây kế thừa bản GATE v2 và là ngưỡng đề xuất cho lab. Checklist dự án yêu cầu chốt ngưỡng theo môi trường trước khi thực hiện. Hồ sơ nghiệm thu cần ghi nhận việc sử dụng các ngưỡng này; chúng không phải cam kết SLA của Ceph.

| Chỉ tiêu | Tiêu chí lab |
| --- | --- |
| Trước mỗi lần redeploy | Đủ đúng ba MON trong quorum; `mon ok-to-stop` của MON được chọn trả mã 0 |
| Trong lúc một MON dừng | Hai MON còn lại duy trì khả năng hình thành quorum; không mất MON thứ hai |
| Yêu cầu redeploy chưa được xử lý | Quá 300 giây thì HOLD để điều tra hàng đợi |
| Thời gian MON trở lại quorum | Không quá 300 giây tính từ lúc daemon thực sự dừng |
| Sau mỗi MON | Quorum 3/3 ổn định ít nhất 5 phút, không có bầu chọn mới trong khoảng này |
| Baseline trước canary | Ít nhất 10 phút với các luồng theo dõi hoạt động |
| Theo dõi canary | Ít nhất 15 phút kể từ khi canary trở lại quorum |
| Theo dõi sau MON cuối | Ít nhất 30 phút kể từ khi MON cuối trở lại quorum |
| Xác thực và lệnh quản trị | Thành công trong 30 giây; lỗi phải được phân loại |
| RBD | Không lỗi hoặc sai dữ liệu; mỗi vòng write, flush, read, compare không quá 10 giây |
| RGW/S3 | Không lỗi hoặc sai dữ liệu; mỗi vòng PUT, GET, compare không quá 30 giây |
| Độ trễ RBD và S3 | p95 từng dịch vụ không vượt `max(2 × p95 baseline, 1.000 ms)` |
| Health và dữ liệu | Không có lỗi mới chưa giải thích về quorum, clock, auth, disk, PG, OSD hoặc checksum |
| Sau dọn tài nguyên thử | Theo dõi ít nhất 5 phút và lưu trạng thái bàn giao |

Một lần truy vấn quorum lỗi không đủ để kết luận đã mất quorum. Ngược lại, ảnh quorum tốt ở một thời điểm không chứng minh toàn bộ quá trình không gián đoạn. Cần kết hợp log MON, chuỗi mẫu và kết quả client.

## 2 Danh mục điểm kiểm tra

| Mã | Thời điểm | Nội dung |
| --- | --- | --- |
| MG0 | Trước chuẩn bị thay đổi | Đúng cụm, phiên bản, topology và hồ sơ phục hồi |
| MG1 | Trước canary và trước từng MON | Host, thời gian, mạng, dung lượng và image |
| MG2 | Trước canary; đối chiếu lại sau nâng | Cấu hình trung tâm, cấu hình hiệu lực và các thay đổi có điều kiện |
| MG3 | Trước canary; duy trì xuyên rollout | Baseline, quorum observer, xác thực, RBD và RGW |
| MG4 | Trước và sau mỗi MON | Quyền dừng MON, phiên bản chạy thực tế và khả năng trở lại quorum |
| MG5 | Sau canary | Hoạt động khi MON còn đồng thời hai phiên bản |
| MG6 | Khi có bầu chọn; sau MON leader | Quorum, leader, auth và kết nối giữa daemon |
| MG7 | Sau MON cuối | Phiên bản, dịch vụ, dữ liệu và trạng thái sau nâng |
| MG8 | Khi kết thúc lần chạy | Hoàn nguyên cấu hình tạm, xử lý tài nguyên thử và bàn giao |

## 3 Đối chiếu checklist của dự án

Nguồn đối chiếu là [UPGRADE-CHECKLIST(1).md](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), Git blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`. Các mã MG tổ chức việc kiểm tra cho chặng MON, không thay đổi ý nghĩa của mã G, T và R trong checklist chung.

| Mã checklist | Nội dung liên quan | Điểm kiểm tra MON |
| --- | --- | --- |
| G00, T00 | Nguồn image, digest và cấu hình | MG0, MG1, MG2 |
| G01 | Health, PG, daemon và cảnh báo | MG0, MG3–MG7 |
| G03, T10 | Quorum, election, Paxos và MON store | MG1, MG4, MG5, MG6 |
| G04, T20, T20A | Cấu hình hiệu lực, mask và thay đổi default | MG2, MG5, MG7 |
| G05, T04 | Hệ thống giám sát dùng để ra quyết định | MG3, MG7 |
| G06, T11 | CephX, reconnect và MON–MGR | MG0, MG3, MG6; phân biệt smoke auth với rotation |
| G07, T23, T24; phạm vi RBD tương ứng | Dịch vụ đang dùng | MG3, MG7; kiểm tra continuity RBD/RGW trong chặng MON |
| G08, T26 | Trạng thái cephadm, image trên host, vòng đời action | MG0, MG1, MG4, MG8 |
| T17A, T21 | Map, MON store, progress và messenger | MG5, MG6, MG7 |
| G13, T09B | Bằng chứng đúng đường nâng và phần chưa được kiểm chứng | MG0, mục 13 |
| R2 | Canary follower và chuyển leader | MG4–MG7 và các nhánh T10/T11 áp dụng |
| Mục 9, T10C, T10D | Failback MON và công cụ phục hồi | MG0 và mục 12 |

G02 trong checklist chung tập trung vào khả năng phục hồi storage/OSD. Chặng MON kế thừa hồ sơ đó; không tuyên bố đóng G02 hoặc toàn bộ checklist bằng kết quả nâng ba MON.

Các phép thử chuyên biệt như RBD cache/mirror, RGW multisite/security, CephFS và stretch được thực hiện theo phạm vi tương ứng. Probe RBD/S3 trong tài liệu này kiểm tra dịch vụ tiếp tục hoạt động khi MON thay đổi, không thay thế toàn bộ các bộ thử chuyên biệt.

## 4 MG0 xác nhận trạng thái trước thay đổi

### 4.1 Thu thập thông tin

**Mục đích:** Lưu trạng thái trước nâng để xác định đúng cụm, biết daemon nào được phép thay đổi và có dữ liệu đối chiếu sau nâng.

Trong terminal quản trị, dùng các biến và hàm `c` tại mục 4 của MOP. Block dưới đây dùng trước một lần nâng mới. Với lần lab đã hoàn thành, đọc các file `pre-*.json` đã lưu.

```bash
c fsid > "$EVIDENCE/fsid-check.txt"
c -s --format json-pretty > "$EVIDENCE/pre-status.json"
c health detail --format json-pretty > "$EVIDENCE/pre-health.json"
c versions --format json-pretty > "$EVIDENCE/pre-versions.json"
c quorum_status --format json-pretty > "$EVIDENCE/pre-quorum.json"
c mon dump --format json-pretty > "$EVIDENCE/pre-monmap.json"
c mon metadata --format json-pretty > "$EVIDENCE/pre-mon-metadata.json"
c mgr dump --format json-pretty > "$EVIDENCE/pre-mgr.json"
c orch ps --refresh --format json-pretty > "$EVIDENCE/pre-orch-ps.json"
c orch host ls --format json-pretty > "$EVIDENCE/pre-hosts.json"
c orch ls --export > "$EVIDENCE/pre-service-specs.yaml"
c orch upgrade status --format json-pretty > "$EVIDENCE/pre-upgrade.json"
c osd dump --format json-pretty > "$EVIDENCE/pre-osdmap.json"
c osd tree --format json-pretty > "$EVIDENCE/pre-osd-tree.json"
c osd metadata --format json-pretty > "$EVIDENCE/pre-osd-metadata.json"
c osd pool ls detail --format json-pretty > "$EVIDENCE/pre-pools.json"
c pg stat --format json-pretty > "$EVIDENCE/pre-pg.json"
c fs ls --format json-pretty > "$EVIDENCE/pre-filesystems.json"
c crash ls-new --format json-pretty > "$EVIDENCE/pre-crashes.json"

c mon getmap -o /evidence/pre-monmap.bin
c osd getmap -o /evidence/pre-osdmap.bin
```

Mỗi lệnh phải trả thành công và tạo file có nội dung hợp lệ. Lỗi gọi lệnh hoặc file JSON rỗng làm hồ sơ chưa đủ. Không gộp stderr của cephadm vào file JSON.

Đọc nhanh phần MON và vai trò:

```bash
jq '{quorum_names,quorum_leader_name,election_epoch,quorum_age}' \
  "$EVIDENCE/pre-quorum.json"

jq -r '.[] | select(.daemon_type=="mon") |
  [.daemon_name,.hostname,.status_desc,.version,.container_image_name] | @tsv' \
  "$EVIDENCE/pre-orch-ps.json"
```

### 4.2 Tiêu chí đạt

- FSID đúng; MonMap, service spec và inventory cùng chỉ ra ba MON của lab.
- Quorum đủ ba MON; health và trạng thái PG có thể giải thích, không có lỗi dữ liệu hoặc recovery/backfill bất thường đang diễn ra.
- Hai MGR đã chạy 16.2.15, có active và standby; ghi rõ ID của OSD target và OSD còn base.
- Không có vòng upgrade đang chạy, bị pause hoặc yêu cầu redeploy trước đó còn chờ.
- Có cách truy cập từng host nếu CLI của cụm không trả lời.
- Có phương án phục hồi phù hợp; export MonMap/config không được ghi là bản backup đầy đủ của MON store.

**Minh chứng hiện có:** MC01 và ảnh quorum baseline MC08 của MOP xác nhận đúng cụm, ba MON 16.2.5, hai MGR 16.2.15 và cơ cấu phiên bản OSD/RGW. Ảnh `ceph versions` không tự chứng minh vai trò active/standby MGR hoặc ID của OSD target; các nội dung này cần file inventory gốc.

### 4.3 Phạm vi có điều kiện

| Điều kiện | Xử lý |
| --- | --- |
| Có CephFS | Bổ sung trạng thái FSMap/MDS và client CephFS; không dùng số MDS bằng 0 làm chứng cứ duy nhất rằng không có filesystem |
| Có stretch hoặc tiebreaker | Dùng kế hoạch quorum theo site; tài liệu ba MON thông thường này chưa đủ |
| Có OSD offline hoặc trước Pacific | Audit inventory và release flag theo T10A |
| Base image là image tùy biến | Ghi digest/build và khác biệt với upstream theo G00/T00 |
| Có mask cấu hình theo host/class/location | Lập danh sách daemon chịu tác động và giá trị hiệu lực dự kiến |
| Có công cụ sửa monstore trong phương án phục hồi | Diễn tập trên bản sao cô lập theo T10D |

Trong lab, base image thuộc repository `trangtran97/ceph`. Kết quả `ceph --version` xác nhận phiên bản binary nhưng chưa thay thế việc đối chiếu toàn bộ nội dung image với upstream.

## 5 MG1 kiểm tra host và image

**Mục đích:** Loại trừ lỗi môi trường có thể làm MON không khởi động lại hoặc không trở về quorum.

Chạy trên từng host MON; đặt `MON_ID` bằng tên MON trên host đó và dùng FSID/image trong MOP. Lưu output theo tên host và thời gian.

```bash
date -u +%FT%TZ
timedatectl status
chronyc tracking
chronyc sources -v
sudo df -hT "/var/lib/ceph/$FSID/mon.$MON_ID"
sudo df -i "/var/lib/ceph/$FSID/mon.$MON_ID"
sudo du -sh "/var/lib/ceph/$FSID/mon.$MON_ID/store.db"
sudo systemctl status "ceph-$FSID@mon.$MON_ID.service" --no-pager
sudo ss -lntp
sudo docker image inspect --format '{{json .RepoDigests}}' "$TARGET_IMAGE"
sudo docker run --rm --entrypoint ceph "$TARGET_IMAGE" --version
```

Nếu host dùng dịch vụ đồng bộ thời gian khác chrony, dùng công cụ tương ứng. Tại terminal quản trị:

```bash
c time-sync-status --format json-pretty
c health detail
c config show "mon.$MON_ID" --format json-pretty
```

**PASS khi:** clock không lệch vượt ngưỡng hiệu lực; filesystem và inode đủ, free space cao hơn ngưỡng cảnh báo MON và còn dự phòng cho image/log/store; unit không restart loop; image trên host có đúng RepoDigest và binary 16.2.15.

Các host MON và client phải kết nối được đến địa chỉ, port thực tế trong MonMap. Dùng `nc -vz -w 3 <IP> <PORT>` cho từng endpoint đang sử dụng; việc `ss` thấy port lắng nghe chỉ xác nhận trạng thái local. Không tăng ngưỡng clock hoặc disk để bỏ qua cảnh báo.

**Minh chứng cần lưu:** thời gian đồng bộ, dung lượng/inode, endpoint, RepoDigest và phiên bản image của cả ba host.

## 6 MG2 kiểm tra cấu hình

### 6.1 Thu cấu hình trung tâm và cấu hình hiệu lực

**Mục đích:** Phân biệt giá trị đã lưu trong cụm với giá trị daemon đang sử dụng, đặc biệt khi có file cấu hình hoặc mask ghi đè.

```bash
c config dump --format json-pretty > "$EVIDENCE/config-original.json"
c balancer status --format json-pretty > "$EVIDENCE/balancer-original.json"
c osd pool ls detail --format json-pretty > "$EVIDENCE/pools-original.json"

jq '.[] | select((.mask // "") != "" or
  ((.name // "") | test("container_image|public_network|log_max_recent|ms_async_max_op_threads|ms_die_on_bad_msg|mon_mds_skip_sanity")))' \
  "$EVIDENCE/config-original.json" > "$EVIDENCE/config-focus.json"

for MON_ID in ceph-master ceph-node2 ceph-node3; do
  c config show "mon.$MON_ID" --format json-pretty \
    > "$EVIDENCE/mon.$MON_ID.config-before.json" || break
done
```

Với lab nhỏ, lấy thêm `config show` cho toàn bộ OSD, bao gồm OSD base và OSD target. Sau canary và cuối rollout, thu lại cùng danh sách và so với cấu hình ngay trước canary. Giữ nguyên bộ `section, mask, name, value` khi đối chiếu; không bỏ mask để làm hai cấu hình khác nhau trông giống nhau.

### 6.2 Nội dung đánh giá

| Hạng mục | Tiêu chí |
| --- | --- |
| Image mong muốn và image đang chạy | Phân biệt rõ; chỉ daemon được chỉ định đổi image |
| Public network | File, cấu hình trung tâm, MonMap và service spec phù hợp |
| `log_max_recent` | Không còn giá trị 0 không hợp lệ áp dụng cho MON target |
| `ms_async_max_op_threads` | Có quyết định giữ/sửa/bỏ đúng consumer; không xóa global ảnh hưởng daemon base |
| `ms_die_on_bad_msg` | Đã xác định giá trị và tổ hợp MON–MGR; không thay giá trị để che lỗi |
| `mon_mds_skip_sanity` | Biết nguồn và mục đích nếu tồn tại; không tự bật hoặc xóa trong chặng MON |
| Mask theo host/class/location | Đã xác định daemon chịu tác động; giá trị sau nâng phù hợp kỳ vọng |
| Release flag và range blocklist | Giữ theo baseline; không kích hoạt khả năng mới trong lúc mixed-version |
| CRUSH, pool, PG, upmap và cờ OSD | Mọi thay đổi có giải thích; không phát sinh điều chỉnh ngoài phạm vi |
| Cấu hình tạm | Có giá trị trước, sau và cách hoàn nguyên |

Sáu key cũ trong checklist mục 4.1 thuộc nhiều loại daemon. Chỉ xử lý key thực sự áp dụng trong chặng này và sau điều kiện phục hồi của checklist; không dùng danh sách đó như một block xóa cấu hình hàng loạt.

**Kết quả có trong ảnh:** Ba MON có public network `10.20.20.0/24` phù hợp giữa các nguồn; image mong muốn trỏ tới target trước khi binary MON được redeploy. Ảnh cấu hình không đủ để đóng toàn bộ MG2 cho OSD mask và các key khác.

| Thời gian | Key hoặc tài nguyên | Phạm vi | Giá trị trước | Giá trị sau | Giữ hay hoàn nguyên | Căn cứ |
| --- | --- | --- | --- | --- | --- | --- |
| Ghi theo nhật ký thực tế | | | | | | |

## 7 MG3 chuẩn bị và duy trì các luồng theo dõi

### 7.1 Bố trí và hồ sơ

**Mục đích:** Thu dữ liệu trước canary để so sánh, đồng thời phát hiện lỗi trong lúc MON thay đổi.

| Luồng | File kết quả | Nội dung chứng minh |
| --- | --- | --- |
| Quorum observer | `quorum-timeline.jsonl` và `quorum-errors.log` | Quorum, leader, election và lỗi truy vấn theo thời gian |
| Client Ceph cũ | `auth.csv` | Kết nối mới và truy cập status |
| RBD | `rbd.csv`, manifest và kết quả reopen | Ghi, flush, đọc, so nội dung qua session dài và session mới |
| RGW/S3 | `s3.csv`, payload và kết quả GET cuối | PUT, GET và so nội dung qua endpoint dịch vụ |

RBD và RGW có hai bộ dữ liệu tách biệt: dữ liệu cố định tạo trước nâng, và dữ liệu probe thay đổi trong lúc nâng. Dữ liệu cố định được đọc lại sau nâng để đối chiếu với giá trị SHA-256 lưu bên ngoài cụm.

Dùng một terminal riêng cho mỗi luồng; terminal quản trị gửi lệnh redeploy không chạy vòng lặp giám sát. Các máy cùng RUN_ID và đồng bộ clock.

### 7.2 Quorum observer

Chạy tại terminal quản trị riêng, đã khai báo `c` và `EVIDENCE`. Vòng lặp xác thực cả exit code lẫn nội dung JSON để tránh ghi thành công cho một mẫu không hợp lệ.

```bash
while [[ ! -e "$EVIDENCE/stop-quorum" ]]; do
  at=$(date -u +%FT%TZ)
  c quorum_status --format json \
    > "$EVIDENCE/quorum-current.json" \
    2> "$EVIDENCE/quorum-current.err"
  rc=$?

  if (( rc == 0 )); then
    jq -e '(.quorum_names | type)=="array" and
           (.quorum_leader_name | type)=="string"' \
      "$EVIDENCE/quorum-current.json" >/dev/null
    rc=$?
  fi

  if (( rc == 0 )); then
    jq -c --arg at "$at" \
      '{at:$at,ok:true,quorum_names,quorum_leader_name,
        election_epoch,quorum_age,monmap_epoch:.monmap.epoch}' \
      "$EVIDENCE/quorum-current.json" >> "$EVIDENCE/quorum-timeline.jsonl"
  else
    jq -nc --arg at "$at" --argjson rc "$rc" \
      '{at:$at,ok:false,rc:$rc}' >> "$EVIDENCE/quorum-timeline.jsonl"
    {
      printf '\n%s rc=%s\n' "$at" "$rc"
      cat "$EVIDENCE/quorum-current.err"
    } >> "$EVIDENCE/quorum-errors.log"
    echo 'HOLD: mẫu quorum lỗi, cần đối chiếu log'
  fi
  sleep 5
done
```

Chu kỳ giữa hai mẫu gồm thời gian gọi CLI và khoảng nghỉ 5 giây; không mặc định chính xác 5 giây. Việc mất mẫu cần được phân biệt với việc MON mất quorum.

### 7.3 Client xác thực RBD và RGW

Phụ lục A cung cấp môi trường client, vòng xác thực, RBD probe và S3 probe. Dùng client cũ giữ nguyên phiên bản trong toàn bộ cửa sổ so sánh. Client quản trị 16.2.15 không thay thế phép kiểm tra client cũ.

Ảnh 08 trong Word thể hiện RBD chạy qua container client cũ. Phương án phụ lục giữ cách triển khai này và gắn rõ file config, keyring để tránh lỗi client không tìm thấy khóa. Mật khẩu, secret key và nội dung keyring không đưa vào báo cáo.

### 7.4 Giám sát MGR khi đang sử dụng Prometheus

```bash
# PROM_URL là endpoint Prometheus thực tế của lab.
curl --fail --silent --show-error --max-time 15 \
  "$PROM_URL/api/v1/targets" > "$EVIDENCE/prom-targets-baseline.json"

jq '.data.activeTargets[] |
  {job:.labels.job,scrapeUrl,health,lastScrape,lastError}' \
  "$EVIDENCE/prom-targets-baseline.json"
```

Danh sách phải có đủ target đang dùng; scrape gần thời điểm đánh giá, `health=up` và `lastError` rỗng. HTTP 200 ở `/metrics` chưa chứng minh Prometheus đã parse và nạp số liệu.

Nếu Prometheus đã lỗi trước MON, giữ kết quả FAIL cho phép thử đó và xác nhận nguồn giám sát độc lập đủ dữ liệu theo G05. Không đổi FAIL thành N/A. Kết quả MGR đã có từ chặng trước được dẫn chiếu, không cần tạo lại một lần failover MGR trong khi nâng MON.

### 7.5 Kết luận baseline

**PASS khi:** ít nhất 10 phút quan sát có đủ mẫu của bốn luồng, không lỗi dữ liệu và không khoảng mất quan sát chưa giải thích; dữ liệu cố định đã tạo và đọc lại thành công; các probe vẫn đang chạy khi bắt đầu canary.

Ghi UTC bắt đầu và kết thúc từng giai đoạn trong `phases.tsv`. Dữ liệu latency dùng để tính p95 phải thuộc đúng cửa sổ baseline, canary hoặc sau nâng. Mẫu chạy qua ranh giới redeploy được giữ trong phần chuyển tiếp, không bị loại khỏi đánh giá.

## 8 MG4 kiểm tra trước và sau từng MON

### 8.1 Trước redeploy

**Mục đích:** Xác nhận MON được chọn có thể tạm dừng tại thời điểm chuẩn bị thao tác.

```bash
c quorum_status --format json-pretty \
  > "$EVIDENCE/$MON_ID.before-quorum.json"
c orch ps --daemon-type mon --refresh --format json-pretty \
  > "$EVIDENCE/$MON_ID.before-orch.json"

c mon ok-to-stop "$MON_ID" \
  > "$EVIDENCE/$MON_ID.ok-to-stop.txt" \
  2> "$EVIDENCE/$MON_ID.ok-to-stop.err"
rc=$?
printf '%s\n' "$rc" > "$EVIDENCE/$MON_ID.ok-to-stop.rc"
printf 'ok-to-stop rc=%s\n' "$rc"
```

`MON_ID` không có tiền tố `mon.` trong lệnh `mon ok-to-stop`. Phải có quorum 3/3, đúng MON định nâng, hai MON còn lại khỏe và mã trả về bằng 0. Nếu trạng thái thay đổi hoặc thao tác bị gián đoạn, chạy lại trước redeploy.

### 8.2 Sau redeploy

**Mục đích:** Xác nhận tiến trình đang chạy phiên bản mới, đã tham gia quorum và action đã có kết quả thực tế.

```bash
c orch ps --daemon-type mon --refresh --format json-pretty \
  > "$EVIDENCE/$MON_ID.after-orch.json"
c tell "mon.$MON_ID" version \
  > "$EVIDENCE/$MON_ID.running-version.txt"
c tell "mon.$MON_ID" mon_status \
  > "$EVIDENCE/$MON_ID.mon-status.json"
c quorum_status --format json-pretty \
  > "$EVIDENCE/$MON_ID.after-quorum.json"
c health detail > "$EVIDENCE/$MON_ID.health.txt"
c pg stat > "$EVIDENCE/$MON_ID.pg.txt"
c mgr dump --format json-pretty > "$EVIDENCE/$MON_ID.mgr.json"
c crash ls-new --format json-pretty > "$EVIDENCE/$MON_ID.crashes.json"
```

Trên host của MON, dùng container ID lấy từ inventory đã refresh để đối chiếu image thực tế:

```bash
# MON_CID lấy từ container của đúng mon.$MON_ID trên chính host đó.
MON_IMAGE_ID=$(sudo docker inspect --format '{{.Image}}' "$MON_CID")
sudo docker image inspect --format '{{json .RepoDigests}}' "$MON_IMAGE_ID"

sudo journalctl -u "ceph-$FSID@mon.$MON_ID.service" \
  --since "$WINDOW_START_UTC" --until "$WINDOW_END_UTC" \
  --utc --no-pager
```

**PASS khi:** runtime 16.2.15; RepoDigest đúng; MON có trạng thái `leader` hoặc `peon` phù hợp và nằm trong quorum; hoàn thành trong ngưỡng đã chốt; sau đó quorum 3/3 ổn định ít nhất 5 phút, dịch vụ không có lỗi mới chưa xử lý.

Thời điểm gửi lệnh, thời điểm daemon dừng và thời điểm trở lại quorum là ba mốc khác nhau. Không lấy tuổi `running` trong ảnh hoặc thời điểm `Scheduled` làm thời gian phục hồi.

## 9 MG5 đánh giá canary

**Mục đích:** Xác nhận một MON 16.2.15 có thể hoạt động cùng hai MON 16.2.5 trước khi nâng tiếp.

| Nội dung | Bằng chứng | Tiêu chí |
| --- | --- | --- |
| Quorum | Timeline và journal trong ít nhất 15 phút | 3/3 ổn định, không election/sync lặp |
| Xác thực | Client cũ và CLI quản trị | Kết nối mới thành công, không auth loop |
| RBD và RGW | CSV và dữ liệu đối chiếu | Không lỗi, không mismatch, độ trễ trong ngưỡng |
| MGR và OSD | Inventory, mgr dump, PG và health | Giữ số lượng/phiên bản theo baseline ngoài MON được chọn |
| Cấu hình | Snapshot cùng danh sách daemon | Sai khác đúng kỳ vọng, không config invalid/unknown |
| Map và store | OSDMap, PG, dung lượng, log MON | Không thay đổi placement hoặc tăng store bất thường chưa giải thích |

Một lệnh client thành công có thể đi qua MON khác. Nếu kết luận riêng về xác thực trên canary, cần log endpoint/kết nối phù hợp; việc chỉ đặt địa chỉ bootstrap canary không bảo đảm mọi kết nối tiếp theo đều đến daemon đó.

Nếu mask cấu hình có tác động tới OSD, cần chứng cứ OSD đã nhận cấu hình từ MON target hoặc một phép thử reconnect riêng đã được kiểm soát. Không restart OSD trong chặng này chỉ để tạo thêm bằng chứng.

**Minh chứng hiện có:** MC04 xác nhận trạng thái một MON target và hai MON base. Ảnh đó chưa thay cho đủ log canary, CSV và thống kê latency.

## 10 MG6 đánh giá election và leader sau nâng

### 10.1 Tiêu chí

**Mục đích:** Xác nhận cụm ổn định sau bầu chọn và khi leader chạy phiên bản mới.

- Quorum hội tụ rồi đủ 3/3 trong ít nhất 5 phút; không lặp electing/synchronizing.
- Ghi được leader và phiên bản leader sau sự kiện.
- Client kết nối mới được; session RBD, đường S3 và MGR tiếp tục hoạt động.
- Không có auth loop, unknown-message/assert, Paxos không tiến triển hoặc crash mới chưa giải thích.
- OSDMap, PG, pool, upmap và dung lượng MON store có sai khác được giải thích.

Tăng `election_epoch` là dấu hiệu đã có bầu chọn. Nó không tự chứng minh đã có gián đoạn dịch vụ hoặc có lỗi bầu chọn.

### 10.2 Bốn mẫu observer lỗi trong hồ sơ lab

Ảnh 16 trong Word ghi nhận:

| Thời gian UTC ngày 01/10/2026 | Kết quả | Kết luận từ ảnh |
| --- | --- | --- |
| 13:26:38Z | `ok=false, rc=1` | Lệnh truy vấn quorum lỗi |
| 13:31:35Z | `ok=false, rc=1` | Lệnh truy vấn quorum lỗi |
| 14:37:09Z | `ok=false, rc=1` | Lệnh truy vấn quorum lỗi |
| 14:41:28Z | `ok=false, rc=1` | Lệnh truy vấn quorum lỗi |

Chưa đủ căn cứ gán nguyên nhân cho bốn mẫu này. Đối chiếu `quorum-errors.log`, stderr còn giữ, journal ba MON và `auth.csv`, `rbd.csv`, `s3.csv` cùng thời gian. Không mặc định đây là lỗi keyring, lỗi observer hoặc mất quorum nếu chưa có log tương ứng.

```bash
# Truy xuất mẫu lỗi từ file gốc, không sửa nội dung file.
jq -c 'select(.ok == false)' "$EVIDENCE/quorum-timeline.jsonl"

# Ví dụ lấy log quanh mẫu 13:26:38Z; chạy trên từng host MON.
# Lặp lại với ba khoảng thời gian còn lại.
sudo journalctl -u "ceph-$FSID@mon.$MON_ID.service" \
  --since '2026-10-01 13:24:00 UTC' \
  --until '2026-10-01 13:29:00 UTC' \
  --utc --no-pager
```

Nếu xác định lỗi nằm ở công cụ thu thập và nguồn độc lập chứng minh dịch vụ vẫn hoạt động, ghi rõ nguyên nhân và bằng chứng thay thế. Nếu log không còn, giữ HOLD cho kết luận tính liên tục của khoảng đó. Kiểm tra tốt ở thời điểm hiện tại không bù được log lịch sử đã thiếu.

```bash
# MINH CHỨNG GT01 — Xử lý bốn mẫu observer lỗi
# Chèn ảnh 16 trong MOP MON.docx.
# Bổ sung trích đoạn stderr/journal và kết quả client đúng bốn khoảng thời gian.
# Ghi nguyên nhân, tác động và kết luận cho từng khoảng sau khi đối chiếu.
```

### 10.3 Phạm vi T11 về CephX

Fresh-client `ceph -s` chỉ kiểm tra xác thực và truy cập thông thường. Để đóng nhánh rotation trong T11, cần bằng chứng key được commit/publish đúng và reconnect quanh sự kiện leader theo phép thử đã được kiểm soát.

Hồ sơ đính kèm chưa có bằng chứng rotation; ghi NOT RUN hoặc HOLD theo trạng thái thực tế. Không tự thay TTL, import/xóa key hoặc hạ MGR để tạo tổ hợp kiểm thử trên cụm đã nâng. Nhánh target-MON/base-MGR không áp dụng cho run này nếu inventory xác nhận cả hai MGR đã target và không có failback MGR trong cửa sổ.

R2 chỉ được đóng đầy đủ khi các nhánh áp dụng của checklist đã có bằng chứng; ba MON chạy 16.2.15 chưa tự đóng R2.

## 11 MG7 kiểm tra sau khi cả ba MON đã nâng

### 11.1 Thu trạng thái sau nâng

**Mục đích:** Xác nhận trạng thái cuối và sai khác so với baseline.

Với lần lab đã hoàn thành, tìm các file post đã có trước. Nếu thu bổ sung hiện tại, dùng thư mục có thời gian riêng như dưới đây, không ghi đè file pre/post gốc.

```bash
export REVIEW_DIR="$EVIDENCE/review-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$REVIEW_DIR"
date -u +%FT%TZ > "$REVIEW_DIR/capture-utc.txt"

c -s --format json-pretty > "$REVIEW_DIR/post-status.json"
c health detail --format json-pretty > "$REVIEW_DIR/post-health.json"
c versions --format json-pretty > "$REVIEW_DIR/post-versions.json"
c quorum_status --format json-pretty > "$REVIEW_DIR/post-quorum.json"
c mon metadata --format json-pretty > "$REVIEW_DIR/post-mon-metadata.json"
c mgr dump --format json-pretty > "$REVIEW_DIR/post-mgr.json"
c orch ps --refresh --format json-pretty > "$REVIEW_DIR/post-orch-ps.json"
c orch upgrade status --format json-pretty > "$REVIEW_DIR/post-upgrade.json"
c config dump --format json-pretty > "$REVIEW_DIR/post-config.json"
c osd dump --format json-pretty > "$REVIEW_DIR/post-osdmap.json"
c osd pool ls detail --format json-pretty > "$REVIEW_DIR/post-pools.json"
c pg stat --format json-pretty > "$REVIEW_DIR/post-pg.json"
c crash ls-new --format json-pretty > "$REVIEW_DIR/post-crashes.json"

for MON_ID in ceph-master ceph-node2 ceph-node3; do
  c tell "mon.$MON_ID" version > "$REVIEW_DIR/$MON_ID.version.txt" || break
  c tell "mon.$MON_ID" mon_status > "$REVIEW_DIR/$MON_ID.mon-status.json" || break
  c config show "mon.$MON_ID" --format json-pretty \
    > "$REVIEW_DIR/$MON_ID.config.json" || break
done
```

Đối chiếu RepoDigest thực tế trên từng host theo MG4; đọc log, clock và dung lượng theo MG1. Nếu đang đo một cửa sổ sau nâng mới, ghi riêng thời gian bắt đầu/kết thúc.

### 11.2 Đọc lại dữ liệu

Sau cửa sổ theo dõi cuối, dừng RBD và S3 bằng stop-file để chúng hoàn tất vòng đang chạy. Đọc lại bằng process mới, so với manifest/payload đã giữ từ trước. Cách thực hiện ở phụ lục A.

Phải có cả kết quả dữ liệu cố định trước nâng và dữ liệu ghi trong rollout. Nếu dữ liệu cố định chưa từng được tạo trước nâng, không tạo mới rồi gọi đó là kiểm chứng dữ liệu trước nâng; ghi rõ phần chưa có bằng chứng.

Kết quả checksum chỉ áp dụng cho các block và object thử đã kiểm tra. Nó không chứng minh đã đọc và xác minh toàn bộ dữ liệu trong cụm.

### 11.3 Tiêu chí nghiệm thu

| Nội dung | Điều kiện |
| --- | --- |
| Phiên bản MON | Ba MON 16.2.15, image đúng RepoDigest, không còn MON base ngoài inventory |
| Quorum | Đủ ba MON và ổn định trong cửa sổ sau nâng |
| MGR và daemon khác | Vai trò, số lượng, phiên bản phù hợp baseline; không thay đổi ngoài phạm vi |
| Client và dữ liệu | CSV đủ các pha, không lỗi dữ liệu; reopen RBD và GET lại S3 thành công |
| Cấu hình và placement | Mọi delta được giải thích, không phát sinh config/PG/OSD bất thường |
| Host và MON store | Clock, filesystem, inode và xu hướng store ổn định |
| Giám sát | Nguồn dùng để quyết định hoạt động và có dữ liệu trong cửa sổ nâng |
| Hồ sơ | Các sự kiện lỗi đã phân loại; có kết quả và người xác nhận |

Ảnh 20 đủ xác nhận kết quả phiên bản/running trong `orch ps`. Cần bổ sung phần còn lại để kết luận MG7 đầy đủ. Việc cụm còn OSD/RGW 16.2.5 là phù hợp phạm vi chặng MON nếu khớp baseline, không yêu cầu toàn bộ `ceph versions` chỉ còn một phiên bản.

## 12 MG8 hoàn nguyên dọn tài nguyên và kiểm tra phục hồi

### 12.1 Kết thúc probe và xử lý tài nguyên thử

Sau khi đã lưu kết quả MG7, xử lý đúng image/object do RUN_ID tạo. Phụ lục A nêu lệnh dừng và đọc lại; lệnh xóa dưới đây chỉ dùng sau khi đối chiếu tên với manifest và kết quả đã đạt.

```bash
# Đọc tình trạng trước khi xóa; phải không còn watcher hoặc snapshot ngoài dự kiến.
client_rbd status "$RBD_POOL/$TEST_IMAGE"
client_rbd snap ls "$RBD_POOL/$TEST_IMAGE"
client_rbd status "$RBD_POOL/$RBD_CORPUS_IMAGE"
client_rbd snap ls "$RBD_POOL/$RBD_CORPUS_IMAGE"

# Chỉ xóa hai image riêng của lần chạy.
test "$TEST_IMAGE" = "mon-gate-$RUN_ID" || exit 1
test "$RBD_CORPUS_IMAGE" = "mon-corpus-$RUN_ID" || exit 1
client_rbd rm "$RBD_POOL/$TEST_IMAGE"
client_rbd rm "$RBD_POOL/$RBD_CORPUS_IMAGE"

# Chỉ dùng cho bucket chưa từng bật versioning theo nhánh phụ lục A.
test "$TEST_KEY" = "mon-gate/$RUN_ID/probe.bin" || exit 1
test "$CORPUS_KEY" = "mon-gate/$RUN_ID/corpus.bin" || exit 1
s3api delete-object --bucket "$TEST_BUCKET" --key "$TEST_KEY"
s3api delete-object --bucket "$TEST_BUCKET" --key "$CORPUS_KEY"
```

Kiểm tra lại bằng `client_rbd ls --pool "$RBD_POOL"` và `s3api list-objects-v2` trên prefix của RUN_ID. Chỉ kết luận đã xóa khi lệnh liệt kê thành công và không còn tài nguyên đó; AccessDenied hoặc timeout không phải bằng chứng đã xóa.

Không xóa pool, bucket, keyring, MON store hoặc các tài nguyên PA1. Nếu giữ fixture để điều tra, ghi người quản lý và thời hạn giữ; không bắt buộc xóa khi còn sự cố.

### 12.2 Hoàn nguyên cấu hình tạm

Đối chiếu sổ thay đổi ở MG2. Nếu trước đó có override, trả đúng giá trị và phạm vi; nếu trước đó không có override, chỉ xóa giá trị tạm do lần này tạo. Giữ image đích của MON và các sửa đổi cần thiết cho target.

Sau hoàn nguyên, lưu health, config, pool mode và theo dõi ít nhất 5 phút. Cân bằng trở lại sau khi bật đúng balancer/autoscaler được ghi riêng, không gán nhầm cho chặng đổi MON.

Dừng các observer bằng stop-file và chờ terminal kết thúc:

```bash
touch "$CLIENT_EVIDENCE/stop-auth"
touch "$EVIDENCE/stop-quorum"
```

**PASS khi:** probe đã dừng; fixture đã xử lý đúng; cấu hình tạm đã hoàn nguyên; thay đổi giữ lại có danh sách; hồ sơ và các vấn đề còn mở được bàn giao.

### 12.3 Điều kiện phục hồi và failback

Nếu một MON lỗi trong rollout, giữ hai MON tốt, thu journal/systemd và xử lý theo mục 8 của MOP. Khi CLI không trả lời, dùng admin socket tại host đang chạy daemon; xác định đúng socket trước khi gọi `ceph --admin-daemon <socket> mon_status` trong môi trường có thể truy cập socket đó.

Muốn xác nhận khả năng failback, cần hồ sơ diễn tập riêng gồm image base/target, cấu hình, trạng thái MON nhất quán, phương án quorum và kết quả đọc state bằng binary dự định sử dụng. T10D chỉ áp dụng nếu phương án phục hồi thực sự dùng các công cụ monstore/map; mọi thao tác ghi của công cụ chạy trên bản sao cô lập.

**Trạng thái hồ sơ hiện tại:** chưa có bằng chứng diễn tập failback MON. Không ghi PASS cho rollback; phương án trong MOP là phục hồi tại phiên bản target.

## 13 Kết quả đối chiếu hồ sơ lab

### 13.1 Các kết quả đã xác nhận từ ảnh

| Hạng mục | Minh chứng | Kết quả |
| --- | --- | --- |
| Ba MON trước nâng ở 16.2.5 | Ảnh 01–02 | Đã xác nhận |
| Quorum baseline gồm ba MON, leader ceph-master | Ảnh 03 | Đã xác nhận; epoch 530 |
| Public network hiệu lực trên ba MON | Ảnh 06 | Đã xác nhận 10.20.20.0/24 |
| Canary ceph-node2 lên trước | Ảnh 13 | Đã xác nhận; hai MON còn lại ở 16.2.5 |
| Hai follower đã nâng trước leader | Ảnh 17 | Đã xác nhận; quorum 3/3, epoch 550 |
| Ba MON sau nâng chạy 16.2.15 | Ảnh 20 | Đã xác nhận |
| Image ID rút gọn sau nâng | Ảnh 20 | Cả ba là f15b41add2c0 |
| Có mẫu truy vấn quorum lỗi | Ảnh 16 | Bốn mẫu rc=1 cần phân loại |

### 13.2 Trạng thái nghiệm thu theo điểm kiểm tra

| Mã | Đã có bằng chứng | Cần bổ sung để đóng điểm kiểm tra | Trạng thái hồ sơ |
| --- | --- | --- | --- |
| MG0 | Cụm, phiên bản, quorum baseline | Inventory chi tiết, MGR active/standby, trạng thái action và hồ sơ phục hồi | HOLD |
| MG1 | Image đích đã xác định | Clock, dung lượng, endpoint và RepoDigest trên từng host | HOLD |
| MG2 | Public network và image mong muốn | Diff cấu hình đầy đủ, mask/OSD và sổ thay đổi | HOLD |
| MG3 | Ảnh thiết lập các luồng theo dõi | Chuỗi mẫu baseline đủ thời gian, corpus và manifest trước nâng | HOLD |
| MG4 ceph-node2 | Canary target; ảnh ok-to-stop | Mốc stop/rejoin, runtime digest, journal và khoảng ổn định | HOLD |
| MG5 | Tổ hợp một MON target, hai MON base | Log 15 phút, CSV và kết quả canary | HOLD |
| MG4 ceph-node3 | Đã target trước MON cuối | Mốc stop/rejoin, runtime digest và khoảng ổn định | HOLD |
| MG4 ceph-master | Ảnh chọn MON, rc=0; ảnh cuối target | Quorum sau bước cuối, runtime digest và thời gian trở lại | HOLD |
| MG6 | Epoch và quorum ở các mốc; bốn mẫu lỗi | Nguyên nhân mẫu lỗi, leader target, client/journal; T11 rotation chưa có evidence | HOLD |
| MG7 | Ba MON running 16.2.15 | Quorum/health sau cuối, CSV, checksum, thời gian theo dõi cuối | HOLD |
| MG8 | Chưa có ảnh kết thúc/cleanup | Dừng probe, tài nguyên thử, hoàn nguyên và bàn giao | HOLD |

Bảng này phản ánh mức đầy đủ của tài liệu được cung cấp. Kết luận về phiên bản là **đã hoàn thành nâng ba MON**. Kết luận nghiệm thu toàn bộ điều kiện vận hành được cập nhật khi đính kèm đủ file gốc.

### 13.3 Bảng số liệu dịch vụ

| Giai đoạn | Dịch vụ | Thời gian UTC | Số mẫu | Số lỗi | p95 ms | Max ms | Kết quả |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | Auth / RBD / S3 | Chưa tổng hợp | | | | | HOLD |
| Canary ceph-node2 | Auth / RBD / S3 | Chưa tổng hợp | | | | | HOLD |
| Nâng ceph-node3 | Auth / RBD / S3 | Chưa tổng hợp | | | | | HOLD |
| Nâng ceph-master | Auth / RBD / S3 | Chưa tổng hợp | | | | | HOLD |
| Sau MON cuối | Auth / RBD / S3 | Chưa tổng hợp | | | | | HOLD |

Khi điền, tách thành một dòng cho mỗi dịch vụ. Không điền số 0 vào ô lỗi hoặc mismatch khi chưa đọc log.

```bash
# MINH CHỨNG GT02 — Nghiệm thu sau nâng
# Chèn ảnh 20 trong MOP MON.docx cho kết quả phiên bản.
# Bổ sung ảnh/log quorum và health sau MON cuối.
# Bổ sung thống kê auth.csv, rbd.csv, s3.csv và kết quả đọc lại dữ liệu.
```

## Phụ lục A Công cụ theo dõi và kiểm tra dữ liệu

Các đoạn dưới đây chuẩn hóa cách chạy cho một lần lab. Với lần đã hoàn thành, ưu tiên giữ script, CSV và manifest gốc; không chạy lại seed dữ liệu hoặc tạo baseline mới để thay hồ sơ cũ. Những đoạn được chuẩn hóa trong tài liệu cần được chạy thử ở bước chuẩn bị client trước một lần rollout mới.

### A1 Môi trường client Ceph cũ

Dùng file cấu hình và keyring đã hoạt động của lab. Hai đường dẫn dưới đây là đường dẫn đã sử dụng trong quá trình chuẩn bị client; nếu file nằm ở nơi khác, sửa đường dẫn trước khi chạy. Không tạo key mới chỉ để vượt lỗi kết nối.

```bash
export RUN_ID='mon-20261001T092850Z-f9f494b7'
export CLIENT_EVIDENCE="$PWD/client-evidence-$RUN_ID"
export CLIENT_ID='admin'
export CLIENT_CONF='/tmp/ceph-client.conf'
export CLIENT_KEYRING='/tmp/client.keyring'
export OLD_CLIENT_IMAGE='docker.io/trangtran97/ceph@sha256:3694ab472a483b17b920e04fd8f924dd5c072096a3f0c46ca2dd00f84d094d59'
export RBD_POOL='rbd-lab'
export TEST_IMAGE="mon-gate-$RUN_ID"
export RBD_CORPUS_IMAGE="mon-corpus-$RUN_ID"
umask 077
mkdir -p "$CLIENT_EVIDENCE"

# File phải tồn tại và chỉ tài khoản cần dùng được đọc keyring.
sudo test -r "$CLIENT_CONF"
sudo test -r "$CLIENT_KEYRING"

client_ceph() {
  sudo docker run --rm --network host \
    -v "$CLIENT_CONF:/etc/ceph/ceph.conf:ro" \
    -v "$CLIENT_KEYRING:/tmp/client.keyring:ro" \
    --entrypoint timeout "$OLD_CLIENT_IMAGE" --kill-after=2s 30s \
    ceph --conf /etc/ceph/ceph.conf --id "$CLIENT_ID" \
    --keyring /tmp/client.keyring "$@"
}
client_rbd() {
  sudo docker run --rm --network host \
    -v "$CLIENT_CONF:/etc/ceph/ceph.conf:ro" \
    -v "$CLIENT_KEYRING:/tmp/client.keyring:ro" \
    --entrypoint timeout "$OLD_CLIENT_IMAGE" --kill-after=2s 30s \
    rbd --conf /etc/ceph/ceph.conf --id "$CLIENT_ID" \
    --keyring /tmp/client.keyring "$@"
}
rbd_py() {
  sudo docker run --rm --network host \
    -e RUN_ID -e CLIENT_ID -e RBD_POOL -e TEST_IMAGE -e RBD_CORPUS_IMAGE \
    -e CLIENT_EVIDENCE=/evidence \
    -v "$CLIENT_CONF:/etc/ceph/ceph.conf:ro" \
    -v "$CLIENT_KEYRING:/tmp/client.keyring:ro" \
    -v "$CLIENT_EVIDENCE:/evidence" \
    --entrypoint python3 "$OLD_CLIENT_IMAGE" /evidence/rbd_probe.py "$@"
}

client_ceph --version | tee "$CLIENT_EVIDENCE/client-version.txt"
client_ceph -s
client_rbd ls --pool "$RBD_POOL"
sudo docker run --rm --entrypoint python3 "$OLD_CLIENT_IMAGE" \
  -c 'import rados, rbd; print("rados/rbd available")'
```

Chỉ bắt đầu baseline khi các lệnh chuẩn bị đều thành công. Nếu thiếu module Python, sửa môi trường client; không ghi N/A cho RBD đang được sử dụng. Các terminal client khác khai báo cùng biến và hàm.

Thời gian auth với wrapper này bao gồm việc khởi động container và gọi CLI. Giữ nguyên cách chạy trong toàn bộ phép so sánh; số liệu này không phải độ trễ thuần của giao thức CephX.

### A2 Vòng xác thực bằng kết nối mới

```bash
while [[ ! -e "$CLIENT_EVIDENCE/stop-auth" ]]; do
  at=$(date -u +%FT%TZ)
  start_ns=$(date +%s%N)
  client_ceph -s \
    > "$CLIENT_EVIDENCE/auth-last.out" \
    2> "$CLIENT_EVIDENCE/auth-last.err"
  rc=$?
  end_ns=$(date +%s%N)
  ms=$(( (end_ns-start_ns)/1000000 ))
  printf '%s,%s,%s\n' "$at" "$rc" "$ms" >> "$CLIENT_EVIDENCE/auth.csv"
  if (( rc != 0 )); then
    {
      printf '\n%s rc=%s\n' "$at" "$rc"
      cat "$CLIENT_EVIDENCE/auth-last.err"
    } >> "$CLIENT_EVIDENCE/auth-errors.log"
    echo 'HOLD: client xác thực hoặc truy cập status lỗi'
  fi
  sleep 5
done
```

Mỗi vòng gọi một process mới. Nếu CSV không còn sinh mẫu, xem là mất quan sát và điều tra ngay; không chờ hết cửa sổ nâng mới kiểm tra.

### A3 RBD ghi đọc và dữ liệu cố định

Chỉ tạo hai image riêng của RUN_ID trong pool lab có sẵn. Nếu image đã tồn tại, dừng để xác định nó thuộc lần chạy nào; không ghi đè. Các lệnh tạo chỉ dùng trước một lần chạy mới.

```bash
client_rbd create "$RBD_POOL/$RBD_CORPUS_IMAGE" --size 64
client_rbd create "$RBD_POOL/$TEST_IMAGE" --size 64
client_rbd info "$RBD_POOL/$RBD_CORPUS_IMAGE" --format json \
  > "$CLIENT_EVIDENCE/rbd-corpus-fixture.json"
client_rbd info "$RBD_POOL/$TEST_IMAGE" --format json \
  > "$CLIENT_EVIDENCE/rbd-fixture.json"
```

Lưu script sau thành `$CLIENT_EVIDENCE/rbd_probe.py`. Script chỉ thao tác hai image thử đã nêu, sử dụng 256 block 4 KiB trong mỗi image. `rbd_cache=false` áp dụng cho process thử để giảm khả năng đọc lại từ cache client; không thay cấu hình cụm và không chứng minh đã bỏ qua mọi lớp cache phía server.

```python
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import rados
import rbd

mode = sys.argv[1]
if mode not in ("seed", "run", "verify-corpus", "verify-probe"):
    raise ValueError("mode: seed, run, verify-corpus, verify-probe")
ev = Path(os.environ["CLIENT_EVIDENCE"])
run_id = os.environ["RUN_ID"]
pool = os.environ["RBD_POOL"]
corpus = mode in ("seed", "verify-corpus")
name = os.environ["RBD_CORPUS_IMAGE" if corpus else "TEST_IMAGE"]
expected = ("mon-corpus-" if corpus else "mon-gate-") + run_id
if name != expected:
    raise ValueError("Tên image không khớp RUN_ID")
manifest_path = ev / ("rbd-corpus.json" if corpus else "rbd-last-blocks.json")
block_size = 4096
blocks = {}

def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def save_manifest():
    data = {"run_id": run_id, "pool": pool, "image": name,
            "block_size": block_size, "blocks": blocks}
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(manifest_path)

if mode in ("seed", "run") and manifest_path.exists():
    raise RuntimeError("Đã có manifest; không ghi đè lần chạy cũ")
if mode == "run" and (ev / "rbd.csv").exists():
    raise RuntimeError("Đã có rbd.csv; giữ hồ sơ cũ để điều tra")

client = rados.Rados(conffile="/etc/ceph/ceph.conf",
                     name="client." + os.environ["CLIENT_ID"])
client.conf_set("keyring", "/tmp/client.keyring")
client.conf_set("rbd_cache", "false")
client.conf_set("rados_osd_op_timeout", "10")
client.conf_set("rados_mon_op_timeout", "10")
client.connect()
try:
    with client.open_ioctx(pool) as ioctx:
        with rbd.Image(ioctx, name) as im:
            if im.size() != 64 * 1024 * 1024:
                raise RuntimeError("Kích thước image không đúng fixture 64 MiB")
            if mode.startswith("verify"):
                manifest = json.loads(manifest_path.read_text())
                if (manifest["run_id"], manifest["pool"], manifest["image"]) != (
                        run_id, pool, name):
                    raise RuntimeError("Manifest không khớp fixture")
                if manifest["block_size"] != block_size or not manifest["blocks"]:
                    raise RuntimeError("Manifest không hợp lệ hoặc không có block")
                for offset, wanted in manifest["blocks"].items():
                    got = hashlib.sha256(im.read(int(offset), block_size)).hexdigest()
                    if got != wanted:
                        raise IOError("Checksum mismatch offset=" + offset)
                print(utc(), "PASS", mode, len(manifest["blocks"]), "blocks")
            elif mode == "seed":
                for n in range(256):
                    offset = n * block_size
                    payload = hashlib.sha256(
                        (run_id + ":corpus:" + str(n)).encode()).digest() * 128
                    if im.write(payload, offset) != block_size:
                        raise IOError("Short write")
                    blocks[str(offset)] = hashlib.sha256(payload).hexdigest()
                im.flush()
                for offset, wanted in blocks.items():
                    if hashlib.sha256(im.read(int(offset), block_size)).hexdigest() != wanted:
                        raise IOError("Corpus read-back mismatch")
                save_manifest()
                print(utc(), "PASS seed", len(blocks), "blocks")
            else:
                n = 0
                with (ev / "rbd.csv").open("a", newline="", buffering=1) as f:
                    log = csv.writer(f)
                    try:
                        while not (ev / "stop-rbd").exists():
                            at, started = utc(), time.monotonic()
                            offset = (n % 256) * block_size
                            payload = hashlib.sha256(
                                (run_id + ":probe:" + str(n)).encode()).digest() * 128
                            try:
                                if im.write(payload, offset) != block_size:
                                    raise IOError("Short write")
                                im.flush()
                                if im.read(offset, block_size) != payload:
                                    raise IOError("Read-back mismatch")
                                ms = round((time.monotonic() - started) * 1000, 3)
                                blocks[str(offset)] = hashlib.sha256(payload).hexdigest()
                                save_manifest()
                                if ms > 10000:
                                    raise RuntimeError("RBD round exceeded 10 s")
                            except Exception as err:
                                log.writerow([at, 1, round(
                                    (time.monotonic() - started) * 1000, 3), str(err)])
                                raise
                            log.writerow([at, 0, ms, n])
                            n += 1
                            time.sleep(1)
                        im.flush()
                        if not blocks:
                            raise RuntimeError("Không có vòng probe thành công")
                        print(utc(), "Probe stopped after", n, "rounds")
                    except KeyboardInterrupt:
                        log.writerow([utc(), 1, 0, "Interrupted mid-run"])
                        raise
finally:
    client.shutdown()
```

Trước nâng, ghi và đọc lại dữ liệu cố định, sau đó bắt đầu probe trong terminal riêng:

```bash
rbd_py seed > "$CLIENT_EVIDENCE/rbd-seed.txt" \
  2> "$CLIENT_EVIDENCE/rbd-seed.err"
rbd_py verify-corpus > "$CLIENT_EVIDENCE/rbd-corpus-before.txt" \
  2> "$CLIENT_EVIDENCE/rbd-corpus-before.err"
rbd_py run > "$CLIENT_EVIDENCE/rbd-run.out" \
  2> "$CLIENT_EVIDENCE/rbd-run.err"
```

Sau thời gian theo dõi cuối, từ terminal khác tạo stop-file, chờ `rbd_py run` kết thúc rồi chạy hai phép đọc lại bằng process mới:

```bash
touch "$CLIENT_EVIDENCE/stop-rbd"

# Chỉ chạy sau khi terminal probe đã kết thúc.
rbd_py verify-probe > "$CLIENT_EVIDENCE/rbd-reopen.txt" \
  2> "$CLIENT_EVIDENCE/rbd-reopen.err"
rbd_py verify-corpus > "$CLIENT_EVIDENCE/rbd-corpus-after.txt" \
  2> "$CLIENT_EVIDENCE/rbd-corpus-after.err"
```

Mọi lệnh phải trả 0. Nếu probe bị ngắt giữa vòng, không tự chạy lại và bỏ log lỗi. Manifest giữ các block đã xác minh; nó không đủ để khẳng định mọi ghi đang dở đều đã đạt.

### A4 RGW và S3

Dùng AWS CLI, profile đã có và endpoint thực tế phục vụ client. Thay hai giá trị `DIEN_...` trước khi chạy; tên bucket phải là bucket lab được phép dùng dữ liệu thử.

```bash
export AWS_PROFILE='rgw-lab'
export AWS_PAGER=''
export AWS_MAX_ATTEMPTS=1
export AWS_RETRY_MODE=standard
export S3_ENDPOINT='DIEN_ENDPOINT_RGW_THUC_TE'
export TEST_BUCKET='DIEN_BUCKET_LAB_DA_XAC_NHAN'
export TEST_KEY="mon-gate/$RUN_ID/probe.bin"
export CORPUS_KEY="mon-gate/$RUN_ID/corpus.bin"

s3api() {
  timeout --kill-after=2s 20s \
    aws --endpoint-url "$S3_ENDPOINT" \
    --cli-connect-timeout 5 --cli-read-timeout 10 s3api "$@"
}

aws --version > "$CLIENT_EVIDENCE/aws-version.txt" 2>&1
s3api head-bucket --bucket "$TEST_BUCKET"
s3api get-bucket-versioning --bucket "$TEST_BUCKET" \
  > "$CLIENT_EVIDENCE/s3-versioning.json"
s3api list-objects-v2 --bucket "$TEST_BUCKET" \
  --prefix "mon-gate/$RUN_ID/" \
  > "$CLIENT_EVIDENCE/s3-prefix-before.json"
```

Nhánh này dùng bucket chưa từng bật versioning: `Status` phải không có `Enabled` hoặc `Suspended`. Prefix của lần chạy mới phải rỗng và lệnh liệt kê phải thành công. Bucket có versioning cần manifest từng VersionId và cách dọn tương ứng; không tắt versioning chỉ để dùng phép thử này.

Tạo dữ liệu cố định trước nâng:

```bash
head -c 1048576 /dev/urandom > "$CLIENT_EVIDENCE/rgw-corpus.bin"
sha256sum "$CLIENT_EVIDENCE/rgw-corpus.bin" \
  > "$CLIENT_EVIDENCE/corpus-rgw.sha256"

s3api put-object --bucket "$TEST_BUCKET" --key "$CORPUS_KEY" \
  --body "$CLIENT_EVIDENCE/rgw-corpus.bin" \
  > "$CLIENT_EVIDENCE/corpus-rgw-put.json"
s3api get-object --bucket "$TEST_BUCKET" --key "$CORPUS_KEY" \
  "$CLIENT_EVIDENCE/rgw-corpus-before.bin" \
  > "$CLIENT_EVIDENCE/corpus-rgw-get-before.json"
cmp "$CLIENT_EVIDENCE/rgw-corpus.bin" "$CLIENT_EVIDENCE/rgw-corpus-before.bin"
```

Giữ object và file local này đến MG7. Vòng probe dùng một key khác, payload mới ở mỗi vòng:

```bash
n=0
while [[ ! -e "$CLIENT_EVIDENCE/stop-s3" ]]; do
  at=$(date -u +%FT%TZ)
  start_ns=$(date +%s%N)
  rc=0
  detail="$n"

  if ! head -c 65536 /dev/urandom > "$CLIENT_EVIDENCE/s3-payload.bin"; then
    rc=1; detail='PAYLOAD'
  elif ! s3api put-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
    --body "$CLIENT_EVIDENCE/s3-payload.bin" \
    > "$CLIENT_EVIDENCE/s3-put-last.json" \
    2> "$CLIENT_EVIDENCE/s3-put-last.err"; then
    rc=1; detail='PUT'
  elif ! s3api get-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
    "$CLIENT_EVIDENCE/s3-get.bin" \
    > "$CLIENT_EVIDENCE/s3-get-last.json" \
    2> "$CLIENT_EVIDENCE/s3-get-last.err"; then
    rc=1; detail='GET'
  elif ! cmp -s "$CLIENT_EVIDENCE/s3-payload.bin" "$CLIENT_EVIDENCE/s3-get.bin"; then
    rc=1; detail='CHECKSUM'
  fi

  end_ns=$(date +%s%N)
  ms=$(( (end_ns-start_ns)/1000000 ))
  if (( rc == 0 && ms > 30000 )); then
    rc=1; detail='LATENCY'
  fi
  if (( rc == 0 )); then
    if ! cp "$CLIENT_EVIDENCE/s3-payload.bin" "$CLIENT_EVIDENCE/s3-last-verified.bin"; then
      rc=1; detail='EVIDENCE'
    fi
  fi
  printf '%s,%s,%s,%s\n' "$at" "$rc" "$ms" "$detail" \
    >> "$CLIENT_EVIDENCE/s3.csv"
  if (( rc != 0 )); then
    echo "HOLD: S3 $detail"; break
  fi
  n=$((n+1))
  sleep 2
done
```

Sau thời gian theo dõi cuối, tạo stop-file và chờ vòng hiện tại kết thúc. Dùng lệnh mới đọc lại cả object probe và object cố định:

```bash
touch "$CLIENT_EVIDENCE/stop-s3"

# Chỉ chạy sau khi terminal S3 probe đã kết thúc.
s3api get-object --bucket "$TEST_BUCKET" --key "$TEST_KEY" \
  "$CLIENT_EVIDENCE/s3-reopen.bin" > "$CLIENT_EVIDENCE/s3-reopen.json"
cmp "$CLIENT_EVIDENCE/s3-last-verified.bin" "$CLIENT_EVIDENCE/s3-reopen.bin"

s3api get-object --bucket "$TEST_BUCKET" --key "$CORPUS_KEY" \
  "$CLIENT_EVIDENCE/rgw-corpus-after.bin" \
  > "$CLIENT_EVIDENCE/corpus-rgw-get-after.json"
cmp "$CLIENT_EVIDENCE/rgw-corpus.bin" "$CLIENT_EVIDENCE/rgw-corpus-after.bin"

sha256sum "$CLIENT_EVIDENCE/rgw-corpus.bin" \
  "$CLIENT_EVIDENCE/rgw-corpus-after.bin" \
  "$CLIENT_EVIDENCE/s3-last-verified.bin" \
  "$CLIENT_EVIDENCE/s3-reopen.bin" \
  > "$CLIENT_EVIDENCE/s3-final-sha256.txt"
```

Lưu riêng exit code của từng GET và `cmp`. ETag không được sử dụng thay cho SHA-256 của payload. Không xóa fixture nếu kết quả chưa rõ hoặc có mismatch.

### A5 Tổng hợp số mẫu lỗi và độ trễ

Đoạn dưới tính theo thời gian bắt đầu của mẫu, với `FROM_UTC` bao gồm đầu khoảng và `TO_UTC` không bao gồm cuối khoảng. Điền hai mốc từ nhật ký giai đoạn. Lặp lại cho ba CSV và từng giai đoạn; giữ riêng các mẫu chạy qua ranh giới thay đổi để đối chiếu.

```bash
python3 - "$CLIENT_EVIDENCE/rbd.csv" "$FROM_UTC" "$TO_UTC" <<'PY'
import csv
import datetime as dt
import math
import sys

path, begin, end = sys.argv[1:]
def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
start, stop = parse_time(begin), parse_time(end)
if stop <= start:
    raise ValueError("Khoảng thời gian không hợp lệ")
with open(path, newline="") as f:
    rows = [r for r in csv.reader(f) if r and start <= parse_time(r[0]) < stop]
if not rows:
    raise SystemExit("HOLD: không có mẫu trong khoảng được chọn")
errors = sum(int(r[1]) != 0 for r in rows)
lat = sorted(float(r[2]) for r in rows if int(r[1]) == 0)
times = sorted(parse_time(r[0]) for r in rows)
max_gap = max([(b-a).total_seconds() for a, b in zip(times, times[1:])] or [0])
print("file:", path, "samples:", len(rows), "errors:", errors)
print("first:", times[0].isoformat(), "last:", times[-1].isoformat(),
      "max_gap_s:", max_gap)
if lat:
    print("p95_success_ms:", lat[math.ceil(0.95*len(lat))-1],
          "max_success_ms:", max(lat))
else:
    print("HOLD: không có mẫu thành công")
print("max_all_ms:", max(float(r[2]) for r in rows))
PY
```

Không kết luận PASS chỉ từ p95. Phải đọc số lỗi, thời điểm mẫu đầu/cuối, khoảng cách giữa mẫu, đủ thời gian theo dõi và checksum. Các CSV không có header; cột lần lượt là UTC, mã kết quả, thời gian mili giây và nội dung phụ nếu có.

## Phụ lục B Các nhánh kiểm tra ngoài cửa sổ nâng MON

| Nhánh checklist | Điều kiện áp dụng | Cách ghi nhận |
| --- | --- | --- |
| T10A release flag/rejoin | Có thay release flag hoặc OSD legacy/offline cần kiểm chứng | Thử theo kế hoạch riêng; chặng MON giữ state hiện tại |
| T10B range blocklist | Có kế hoạch dùng CIDR range | Thử trên môi trường cô lập; không tạo range state trong mixed rollout |
| T10C old FSMap/failback | Có CephFS lịch sử hoặc yêu cầu hạ MON | Cần fixture/clone và bằng chứng decode; chưa có thì giữ forward-only |
| T10D recovery tools | Runbook dùng công cụ ghi monstore/map | Diễn tập trên bản sao; không thao tác lên store đang phục vụ |
| T11 rotation | Cần đóng đầy đủ nhánh CephX của R2 | Ghi NOT RUN khi mới có smoke auth; không thay bằng soak ngắn |
| T26A staggered/filter/limit | Dùng native staggered hoặc topology MGR tương ứng | Per-daemon redeploy không tự kiểm chứng nhánh này |
| T26B lỗi host/action/render | Có nhánh lifecycle tương ứng | Kế thừa evidence phù hợp hoặc thử cô lập, không gây lỗi thêm trong rollout |
| PA1 và H0 cho OSD | Thuộc chặng nâng OSD | Quản lý trong MOP/GATE OSD; không đóng từ báo cáo MON |

## Tài liệu tham chiếu

1. [MOP MON](./MOP-MON-16.2.5-to-16.2.15.md) và 20 ảnh trong `MOP MON.docx`.
2. [Checklist nâng cấp của dự án](https://github.com/dangtnh7904/VDT_CLOUD_2026/blob/main/comparison/pacific-16.2.5-to-16.2.15/UPGRADE-CHECKLIST%281%29.md), blob `4ec335f8045aa56e3e9c5223eaf15e5d164c12d6`.
3. [Ceph Pacific — Monitor troubleshooting](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-mon/).
4. [Ceph Pacific — Librbd Python API](https://docs.ceph.com/en/pacific/rbd/api/librbdpy/) và [Librados Python API](https://docs.ceph.com/en/pacific/rados/api/python/).
5. [AWS CLI PutObject](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html), [GetObject](https://docs.aws.amazon.com/cli/latest/reference/s3api/get-object.html) và [Prometheus targets API](https://prometheus.io/docs/prometheus/latest/querying/api/#targets).
