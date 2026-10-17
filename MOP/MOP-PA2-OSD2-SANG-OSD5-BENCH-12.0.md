# MOP PA2 tích hợp benchmark — osd.2 → osd.5, pool bench_pa2 / PG 12.0

**Bản zsh cập nhật 12/10/2026 — NOT_RUN.** Đây là bản hợp nhất để đọc và chạy theo thứ tự; không cần mở hai tài liệu MOP/BENCH cũ để lấy lệnh. Các kết quả chỉ điền sau khi chạy thật.

**Mục tiêu đo chính:** trong khi chuyển dữ liệu từ osd.2 sang osd.5, I/O trên pool `bench_pa2` (một PG `12.0`) giảm bao nhiêu, khoảng không hoàn tất I/O kéo dài bao lâu, và mất bao lâu để hiệu năng phục hồi. Đo riêng lúc chuyển chính `12.0` và lúc chuyển các PG khác. Phần nâng daemon vẫn giữ ở cuối để hoàn tất PA2, nhưng thống kê riêng, không trộn vào tác động handoff.

**Phạm vi thao tác:** vẫn drain toàn bộ PG của osd.2 trước nâng; benchmark chỉ phát tải vào image RBD mới trong `bench_pa2`. Không rút `handoff.txt` xuống còn một PG. Không tạo lại pool, ép pool ID hoặc thay `size/min_size`.

**Topology của lượt 2 → 5:** xác minh live osd.2 và osd.5 cùng host, cùng root/class phù hợp. Khi thay replica 2 bằng 5 trên cùng host, tập host của PG không đổi nếu các peer còn lại vốn ở host khác. Bản này **giữ rule host**, không đổi sang failure-domain `osd` chỉ để handoff [S3]. Gate mục 6 kiểm giả thiết này; nếu rule/topology thực khác thì HOLD để sửa kế hoạch. Giữ failure domain không đồng nghĩa đã kiểm thử HA; verdict HA ban đầu là `NOT_TESTED`.

**Phụ thuộc chưa có trong file đính kèm:** bản gốc gọi helper Python ngoài tài liệu nhưng không cung cấp mã nguồn. Bản này yêu cầu `$HOME/pa2-osd2-spare5/pa2_osd2_spare5_check.py` đã được chỉnh và kiểm tra cho **source=2, destination=5**, gồm `plan`, `progress`, `isolate`, `scrub`. **Không chỉ đổi tên helper cũ:** biến `X=2` của shell không tự thay hằng số bên trong Python. Không thể xác nhận helper tương thích khi chưa có mã nguồn; thiếu helper đúng phiên bản thì HOLD tại mục 2. Tài liệu này chưa chạy trên cluster.

## 0 Cách đọc, terminal và các mốc đo

Đi từ mục 1 tới 14, đọc gate QoS mục 16 trước khi bắt đầu. Trong lúc T2/T3 chạy liên tục, thực hiện thao tác cluster ở T1. Không dán toàn tài liệu thành một script: có bước phải đợi, xác minh và điền giá trị thực.

**Shell là zsh; `.zshrc` là file cấu hình của shell. Không cần sửa `.zshrc`, không chạy `bash`, không mở cephadm shell trong quy trình mới.** Mọi cửa sổ T1–T4 đều SSH vào cùng host `ceph-master`, bằng cùng tài khoản của bạn. Bản này dùng Ceph/RBD CLI native trên host, truy cập config/keyring qua sudo; daemon Ceph vẫn chạy container như cũ.

| Terminal | Môi trường bắt buộc | Nhiệm vụ | Khi nào để chạy liên tục |
|---|---|---|---|
| **T1 — ĐIỀU KHIỂN** | zsh trên host ceph-master | Nạp phiên, gate, event, scrub/upmap/nâng daemon | Luôn sẵn dấu nhắc để thao tác |
| **T2 — COLLECTOR** | zsh trên cùng host | Chỉ thu PG/cluster, mục 3.2 | Giữ vòng collector suốt phép đo |
| **T3 — FIO** | zsh trên cùng host | Tạo/map image riêng, prefill, chạy fio, mục 3.3–3.5 | Giữ fio suốt phép đo |
| **T4 — KIỂM TRA** | zsh trên cùng host | Tail log, đọc sentinel và kiểm mapping | Mở khi cần trong lúc T3 đang bận |
| **T5 — LOG OSD** | zsh trên host actual primary được xác minh | Chỉ lấy journal scrub khi cần, mục 8 | Không thực hiện mutation cluster ở đây |

**Bắt đầu lượt 2 → 5:**

1. Dừng đúng fio/collector của lượt trước và giữ evidence cũ. Xác minh cluster ổn định; osd.5 phải chưa thuộc `up[]/acting[]` của bất kỳ PG nào. Nếu vẫn chứa PG của lượt trước thì HOLD, không tự xóa upmap.
2. T1 làm mục **2.1**, chuẩn bị helper đúng cặp 2 → 5, rồi **2.2B** để tạo phiên mới. Sau đó nạp RUN_ID vừa tạo ở từng terminal và làm **2.3**, **3.1** trở đi.
3. Chỉ dùng **2.2A** khi tiếp tục một phiên **2 → 5** đã tạo. Không source `run.env`, `client.env`, plan hoặc ledger của lượt nguồn khác.
4. Giữ pool `bench_pa2` / PG `12.0`; gate đầu vào yêu cầu PG có osd.2, chưa có osd.5. Không mặc định acting set hoặc số lượng PG từ lượt trước.

Mọi đường dẫn evidence trong bản này đều là **đường dẫn host** `$HOME/pa2-osd2-spare5/evidence/<RUN_ID>`. File `run.env` cũ có thể chứa `/mnt/...`; hàm nạp phiên sẽ đổi biến về host sau khi source, **không sửa `run.env` cũ**. Không dùng đường dẫn `/mnt` trong các lệnh tiếp theo.

Mỗi khối lệnh mang nhãn terminal. Khối dài được bọc bằng hàm zsh ẩn danh `() { ... }`: lỗi sẽ dừng khối đó, nhưng không thoát cửa sổ SSH. Phải dán **cả khối**, chờ kết quả rồi mới chạy khối tiếp theo. Thông báo HOLD/lỗi có nghĩa là chưa được sang bước sau. Tùy chọn `INTERACTIVE_COMMENTS` cho phép dán dòng `# ...` trong zsh.

| Mốc | Thời lượng | Ý nghĩa |
|---|---|---|
| BEFORE | 600 giây | Mốc toàn bài trước freeze/rule/affinity/scrub |
| RULE_UNCHANGED_STABLE | 300 giây | Quan sát sau kiểm rule, không đổi placement |
| PRE_TRANSFER | 600 giây | **Baseline chính**, sau affinity và toàn PRE scrub đã xong, ngay trước upmap đầu tiên |
| HANDOFF:12.0:BEGIN → CONVERGED | Theo thực tế | Chuyển chính PG đang chịu tải; độ trễ phát hiện hội tụ phụ thuộc chu kỳ poll |
| HANDOFF:12.0:CONVERGED → OBSERVE_END | 300 giây | Quan sát phục hồi trước khi bắt đầu POST scrub hoặc chuyển PG khác |
| POST scrub và handoff các PG khác | Theo thực tế | Ghi event riêng để nhận diện nhiễu tài nguyên dùng chung |
| AFTER_TRANSFER | 600 giây | Sau toàn handoff/POST đã xong, osd.2 rỗng và cluster ổn định; trước promote/nâng daemon |
| SOURCE_UPGRADE / AFTER | Theo MOP / 600 giây | Bổ sung cho hoàn tất PA2; không trộn vào kết quả handoff |

Nếu đang làm dở phiên: dùng `pa2_load_run` ở mục 2.1 để nạp đúng `run.env`, đọc ledger và live state rồi tiếp tục đúng bước. Không tạo RUN_ID mới, chụp lại `00-*`, chạy prefill hoặc tạo profile lên cùng evidence. Nếu đã mutation trước khi bắt đầu đo, ghi rõ BEFORE thiếu. Nếu đã chuyển 12.0, không có phép đo handoff 12.0 của lần chuyển đó; không tự chuyển ngược để làm lại.

## 1 Đầu vào và kết quả cần giữ

| Mục | Giá trị trong bài này |
|---|---|
| Nguồn U | `osd.2` |
| Đích D và spare đầu S | `osd.5`, đã tạo và đã cấu hình weight-set |
| CRUSH weight gốc của 5 | Đang hiển thị khoảng `0.00009`, phải đọc lại giá trị thực |
| Compat weight của 5 | `0`; OSD override reweight `1`; daemon `up/in` |
| Loại pool | Replicated; giữ rule host đơn giản `take → chooseleaf firstn 0 type host → emit` |
| Handoff và scrub | Một PG mỗi lần; mọi PRE scrub xong trước PG handoff đầu tiên |
| Bản đích | Pacific `16.2.15`, image/digest chốt trong phiên |
| End state | `KEEP_ROTATED_PLACEMENT`, giữ upmap `2 → 5`, giữ dependency weight-set và rule host hiện hành |
| HA | `NOT_TESTED`; kiểm giữ phân tách host, chưa phải kiểm thử failover |
| Phạm vi benchmark | fio/RBD trên riêng pool `bench_pa2` (ID 12), một PG `12.0`; đo một lượt `2 → 5` |

Giá trị hiển thị `0.00009` thường tương ứng số nguyên CRUSH `6`, tức `6/65536 = 0.000091552734375`, sau khi yêu cầu `0.0001`. Kiểm tra số thực; **không chạy lại reweight để làm tròn về một số nhìn đẹp**. CRUSH weight gốc, compat weight và OSD reweight là ba thứ khác nhau. Per-pool weight-set, nếu có, được ưu tiên hơn compat [S3].

**Các đoạn bỏ khỏi MOP cũ:** tạo lại spare, dựng lại weight-set, vòng `rm-pg-upmap-items` trả PG, đưa CRUSH weight của 5 về 0. Không dùng `osd out 2`, không hạ CRUSH/compat weight của 2 trong lượt này: các upmap vẫn phụ thuộc raw placement có 2.

## 2 T1 — cấu hình zsh và nạp phiên trên host

### 2.1 T1 một lần — tạo bộ nạp phiên; T1/T2/T3/T4 đều source trước khi làm việc

**T1 · HOST ceph-master · zsh — chạy trước mọi khối khác.** Không ở prompt root của cephadm shell.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
printf 'zsh=%s\nuser=%s\nhost=%s\n' "${ZSH_VERSION:-CHUA_PHAI_ZSH}" "$(id -un)" "$(hostname)"
setopt INTERACTIVE_COMMENTS
unsetopt ERR_EXIT ERR_RETURN
```

Nếu `zsh=CHUA_PHAI_ZSH` thì chưa đúng cửa sổ host; chưa chạy tiếp. Các tùy chọn trên chỉ áp dụng cửa sổ hiện tại, không ghi vào `.zshrc`.

**T1 · HOST · zsh — kiểm công cụ native và credentials, không in keyring:**

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  typeset -gx PA2_HOST_DIR="$HOME/pa2-osd2-spare5"
  mkdir -p "$PA2_HOST_DIR"
  for TOOL in ceph rbd fio jq python3 timeout sha256sum; do
    whence -p "$TOOL" || { print -u2 -- "HOLD: thieu binary native $TOOL"; return 1; }
  done
  sudo -v
  sudo -n test -r /etc/ceph/ceph.conf
  sudo -n test -r /etc/ceph/ceph.client.admin.keyring
  test -r "$PA2_HOST_DIR/pa2_osd2_spare5_check.py"
  python3 "$PA2_HOST_DIR/pa2_osd2_spare5_check.py" --help
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

`whence -p` tìm binary trên host, không coi alias `ceph='sudo cephadm shell ...'` là CLI native. Nếu thiếu ceph/rbd, chuẩn bị gói `ceph-common` từ repository/version client phù hợp lab rồi quay lại kiểm tra; thiếu fio/jq thì chuẩn bị các công cụ đó trên host. Không tự đổi repository, nâng daemon hay cài gói vào image container. Nếu config/keyring nằm nơi khác, điền đường dẫn thật trong bộ nạp dưới; không chép secret vào báo cáo. Thiếu quyền sudo thì dừng ở setup.

**T1 · HOST · zsh — tạo file cấu hình của bài thử một lần.** Nếu file đã tồn tại, bỏ khối tạo và dùng khối source; không ghi đè trong lúc runner đang chạy.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  typeset -gx PA2_HOST_DIR="$HOME/pa2-osd2-spare5"
  test ! -e "$PA2_HOST_DIR/pa2-session-zsh-v1.zsh"
  cat > "$PA2_HOST_DIR/pa2-session-zsh-v1.zsh" <<'ZSH_SESSION'
if [[ -z ${ZSH_VERSION-} ]]; then
  printf 'HOLD: source file nay bang zsh tren host\n' >&2
  return 1
fi
setopt INTERACTIVE_COMMENTS
unsetopt ERR_EXIT ERR_RETURN
typeset -gx PA2_HOST_DIR="$HOME/pa2-osd2-spare5"
typeset -gx PA2_CEPH_BIN="$(whence -p ceph)"
typeset -gx PA2_RBD_BIN="$(whence -p rbd)"
typeset -gx PA2_CONF=/etc/ceph/ceph.conf
typeset -gx PA2_KEYRING=/etc/ceph/ceph.client.admin.keyring
function pa2_ceph {
  command sudo -n "$PA2_CEPH_BIN" --conf "$PA2_CONF" --id admin --keyring "$PA2_KEYRING" "$@"
}
function pa2_rbd {
  command sudo -n "$PA2_RBD_BIN" --conf "$PA2_CONF" --id admin --keyring "$PA2_KEYRING" "$@"
}
function pa2_load_run {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  local pa2_requested_run="${1:?dien RUN_ID}"
  [[ "$pa2_requested_run" != */* && "$pa2_requested_run" == pa2-2-to-5-* ]]
  test -x "$PA2_CEPH_BIN"
  test -x "$PA2_RBD_BIN"
  sudo -v
  sudo -n test -r "$PA2_CONF"
  sudo -n test -r "$PA2_KEYRING"
  local pa2_env_file="$PA2_HOST_DIR/evidence/$pa2_requested_run/run.env"
  test -r "$pa2_env_file"
  source "$pa2_env_file"
  [[ "$RUN_ID" == "$pa2_requested_run" ]]
  [[ "${X:-}" == 2 && "${S:-}" == 5 ]] || { print -u2 -- "HOLD: run.env khong phai 2 -> 5"; return 1; }
  [[ "$EXPECTED_FSID" == 17c77e12-a16a-11f1-838e-cf68e9c001d8 ]]
  typeset -gx MOP_DIR="$PA2_HOST_DIR"
  typeset -gx HELPER="$MOP_DIR/pa2_osd2_spare5_check.py"
  typeset -gx EVIDENCE="$MOP_DIR/evidence/$RUN_ID"
  typeset -gx BENCH_POOL=bench_pa2 BENCH_PG=12.0
  typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
  test -d "$EVIDENCE"
  test -w "$EVIDENCE"
  test -r "$HELPER"
  [[ "$(pa2_ceph fsid)" == "$EXPECTED_FSID" ]]
  printf 'RUN_ID=%s\nEVIDENCE=%s\n' "$RUN_ID" "$EVIDENCE"
}
ZSH_SESSION
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**T1/T2/T3/T4 · HOST · zsh — trong từng cửa sổ, source cấu hình và nạp cùng RUN_ID.** Source cấu hình không tự nạp phiên. Với phiên mới, T1 chỉ source cấu hình rồi làm 2.2B trước lệnh nạp phiên. Với phiên 2 → 5 đã có, làm 2.2A trước nếu evidence đang thuộc root.

**Chạy khối dưới tại T1 / T2 / T3 / T4 — mỗi cửa sổ nạp riêng · zsh trên host.**

```zsh
source "$HOME/pa2-osd2-spare5/pa2-session-zsh-v1.zsh"
# Phien moi: T1 lam 2.2B truoc, sau do moi nap RUN_ID vua tao.
pa2_load_run 'DIEN_RUN_ID_2_TO_5_DANG_LAM' 
```

Thay placeholder bằng đúng tên thư mục evidence; dùng **cùng giá trị trong cả bốn cửa sổ**, không chọn phiên khác chỉ vì mới nhất. Hàm nạp sẽ báo lỗi nếu file chưa đọc được, thiếu quyền hoặc sai FSID. Chỉ tiếp tục khi in đúng RUN_ID/EVIDENCE và không có lỗi. Lệnh `pa2_ceph`/`pa2_rbd` dùng tên riêng nên không thay alias/function `ceph`/`rbd` trong `.zshrc` của bạn.

### 2.2A T1 — chỉ tiếp tục phiên 2 → 5 đã tạo trước đó

**T1 · HOST · zsh — liệt kê phiên; không ghi file:**

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
sudo ls -lt "$HOME/pa2-osd2-spare5/evidence/"
```

Nếu thư mục/log tạo từ container thuộc root, **dừng collector cũ và các writer của phiên trước**, rồi chuyển quyền sở hữu chỉ thư mục evidence đã chọn cho tài khoản hiện tại:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  typeset -gx PA2_HOST_DIR="$HOME/pa2-osd2-spare5"
  typeset -gx PA2_RESUME_RUN='DIEN_RUN_ID_2_TO_5_DANG_LAM'
  [[ "$PA2_RESUME_RUN" != DIEN_RUN_ID_2_TO_5_DANG_LAM && "$PA2_RESUME_RUN" != */* && "$PA2_RESUME_RUN" == pa2-2-to-5-* ]]
  test -d "$PA2_HOST_DIR/evidence/$PA2_RESUME_RUN"
  test ! -L "$PA2_HOST_DIR/evidence/$PA2_RESUME_RUN"
  sudo chown -R -h "$(id -u):$(id -g)" "$PA2_HOST_DIR/evidence/$PA2_RESUME_RUN"
  source "$PA2_HOST_DIR/pa2-session-zsh-v1.zsh"
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  pa2_load_run "$PA2_RESUME_RUN"
  ls -la "$BENCH_EVIDENCE"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Chown đổi owner để host ghi tiếp evidence; không sửa nội dung baseline. Không áp dụng lên `/var/lib/ceph`, `/etc/ceph` hoặc thư mục evidence của phiên khác. Giữ nguyên `run.env` cũ. `declare -x` cho biến scalar do bản cũ ghi được zsh đọc; sau source, bộ nạp thay đường dẫn `/mnt` bằng đường dẫn host.

**Nhánh resume bỏ 2.2B, 2.3 và các bước tạo file/asset đã hoàn tất.** Nếu chưa rõ bước nào xong, đọc file/ledger trước. Sau chuyển sang native client, ghi client version mới và collector gap; không trộn baseline đo trước và sau đổi client thành một điều kiện giống nhau.

### 2.2B T1 — chỉ tạo phiên MỚI khi chưa có phiên đang làm

**Chạy nhánh này cho lượt 2 → 5 mới; không tái sử dụng RUN_ID của lượt nguồn khác.**

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  source "$HOME/pa2-osd2-spare5/pa2-session-zsh-v1.zsh"
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  sudo -v
  umask 077
  typeset -gx X=2 S=5
  typeset -gx EXPECTED_FSID=17c77e12-a16a-11f1-838e-cf68e9c001d8
  typeset -gx TARGET_IMAGE=quay.io/ceph/ceph:v16.2.15
  typeset -gx MOP_DIR="$PA2_HOST_DIR"
  typeset -gx HELPER="$MOP_DIR/pa2_osd2_spare5_check.py"
  typeset -gx RUN_ID="pa2-2-to-5-$(date -u +%Y%m%dT%H%M%SZ)"
  typeset -gx EVIDENCE="$MOP_DIR/evidence/$RUN_ID"
  typeset -gx TIMEOUT=1800 STABLE=300
  test -r "$HELPER"
  [[ "$(pa2_ceph fsid)" == "$EXPECTED_FSID" ]]
  mkdir -p "$MOP_DIR/evidence"
  mkdir "$EVIDENCE"
  typeset -p X S EXPECTED_FSID TARGET_IMAGE MOP_DIR HELPER RUN_ID EVIDENCE TIMEOUT STABLE > "$EVIDENCE/run.env"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

TIMEOUT=1800 và STABLE=300 là cấu hình lab ban đầu. Dùng digest đã kiểm chứng trước redeploy theo mục 5. Không tạo lại run.env của phiên cũ.

### 2.3 T1 — baseline As Is, CHỈ CHẠY MỘT LẦN ở phiên mới

Bản resume đọc evidence cũ, không chạy lại các khối dưới nếu đã có file. Snapshot `00-*` và bảng `.before.tsv` là dữ liệu gốc để đối chiếu, không cập nhật bằng trạng thái hiện tại.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph -s > "$EVIDENCE/00-status.txt"
pa2_ceph health detail > "$EVIDENCE/00-health.txt"
pa2_ceph fsid > "$EVIDENCE/00-fsid.txt"
pa2_ceph versions -f json > "$EVIDENCE/00-versions.json"
pa2_ceph quorum_status -f json > "$EVIDENCE/00-quorum.json"
pa2_ceph osd dump -f json > "$EVIDENCE/00-osd.json"
pa2_ceph osd crush dump -f json > "$EVIDENCE/00-crush.json"
pa2_ceph osd crush rule dump -f json > "$EVIDENCE/00-rules.json"
pa2_ceph osd crush weight-set ls > "$EVIDENCE/00-weightsets.txt"
pa2_ceph osd tree > "$EVIDENCE/00-tree.txt"
pa2_ceph osd df tree > "$EVIDENCE/00-df.txt"
pa2_ceph pg dump pgs -f json > "$EVIDENCE/00-pgs.json"
pa2_ceph osd getmap -o "$EVIDENCE/00-osdmap.bin"
pa2_ceph osd getcrushmap -o "$EVIDENCE/00-crushmap.bin"
pa2_ceph config dump -f json > "$EVIDENCE/00-config.json"
pa2_ceph balancer status -f json > "$EVIDENCE/00-balancer.json"
pa2_ceph osd pool autoscale-status > "$EVIDENCE/00-autoscale.txt"
pa2_ceph orch ls --service_type osd --export \
  > "$EVIDENCE/00-osd-specs.yaml"
pa2_ceph orch upgrade status > "$EVIDENCE/00-upgrade-status.txt"
for ID in 2 5; do
  pa2_ceph osd find "$ID" -f json > "$EVIDENCE/00-find-$ID.json"
  pa2_ceph osd metadata "$ID" -f json > "$EVIDENCE/00-meta-$ID.json"
done
pa2_ceph orch ps --daemon_type osd --format json --refresh \
  > "$EVIDENCE/00-daemons.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Đọc health/quorum/capacity trước. Không tiếp tục khi inconsistent/unfound, thiếu replica, full/backfillfull/nearfull, recovery ngoài bài thử hoặc có sự cố daemon. `osd.5` phải chứa được toàn dữ liệu replica của 2 cộng ghi mới và headroom; kiểm tra cả DB/WAL và tải host chung với 2. Không suy dung lượng từ weight `0.00009`.

OSD service spec phải có quyền điều phối rõ; không để hai runner/upgrade/controller sửa cluster đồng thời. Đọc `unmanaged` trong spec nhưng không apply lại toàn bộ service chỉ để đổi một trường. Nếu upgrade toàn cluster đang chạy, điều phối/pause job đó trước lượt manual; `unmanaged: true` không thay thế việc kiểm tra upgrade đang chạy.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# Primary-affinity goc de ban giao dung chinh sach.
jq -r '.osds[] | select(.osd==2 or .osd==5)
  | [.osd,.primary_affinity] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/affinity.before.tsv"

# Du lieu de restore sau nay; chua restore o cuoi luot lab nay.
jq -r '.pools[] | [.pool_name,.pg_autoscale_mode] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/autoscale.before.tsv"
jq -r '.pools[] | [.pool_name,.crush_rule,.size,.min_size] | @tsv' \
  "$EVIDENCE/00-osd.json" > "$EVIDENCE/pools.before.tsv"

python3 "$HELPER" isolate --pgs "$EVIDENCE/00-pgs.json" --osd 5
jq '.osds[] | select(.osd==2 or .osd==5)
  | {osd,up,in,weight,primary_affinity,uuid}' "$EVIDENCE/00-osd.json"
jq '{choose_args,buckets}' "$EVIDENCE/00-crush.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**Gate S:** 5 phải vắng trong toàn `up[]` và `acting[]`, up/in và reweight 1. Kiểm canonical weight dương ở ordinary/shadow bucket; compat vector của 5 bằng 0. Nếu có per-pool choose_args, đối chiếu từng pool hoặc HOLD để sửa plan; không tự xóa chúng. Nếu 5 còn PG canary cũ: reconcile mapping và PRE/POST evidence của phiên cũ trước, không áp dụng nhánh clean-start này hoặc tự xóa upmap.

## 3 Khởi động benchmark trên bench_pa2 / 12.0

### 3.1 Kiểm pool, một PG và thư mục evidence

**T1 · HOST · zsh — đã nạp cùng phiên ở mục 2.1.** Chỉ chạy khi chưa có thư mục bench-12.0; nếu đã có, đọc kết quả cũ và tiếp tục bước chưa làm:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
: "${EVIDENCE:?nap phien bang pa2_load_run o muc 2.1}"
: "${RUN_ID:?nap phien bang pa2_load_run o muc 2.1}"
typeset -gx BENCH_POOL=bench_pa2 BENCH_PG=12.0
typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
# mkdir khong -p: neu da co thi dung, khong de baseline cu.
mkdir "$BENCH_EVIDENCE"
pa2_ceph osd dump -f json > "$BENCH_EVIDENCE/pool-check.osd.json"
jq -e --arg pool "$BENCH_POOL" '
  [.pools[] | select(.pool_name==$pool)] as $p
  | ($p|length)==1 and $p[0].pool==12 and $p[0].type==1
    and $p[0].pg_num==1 and $p[0].pg_placement_num==1
    and ($p[0].pg_num_target // $p[0].pg_num)==1
    and ($p[0].pg_placement_num_target // $p[0].pg_placement_num)==1
' "$BENCH_EVIDENCE/pool-check.osd.json"
jq '.pools[] | select(.pool_name=="bench_pa2")
  | {pool,pool_name,type,size,min_size,crush_rule,pg_num,
     pg_placement_num,pg_autoscale_mode}' \
  "$BENCH_EVIDENCE/pool-check.osd.json"
pa2_ceph pg dump pgs -f json > "$BENCH_EVIDENCE/pool-check.pgs.json"
jq -e '[(.pg_stats // .pg_map.pg_stats)[]
  | select(.pgid | startswith("12."))] as $p
  | ($p|length)==1 and $p[0].pgid=="12.0"
    and $p[0].state=="active+clean" and $p[0].up==$p[0].acting
    and ($p[0].acting|index(2))!=null
    and ($p[0].acting|index(5))==null
' "$BENCH_EVIDENCE/pool-check.pgs.json"
pa2_ceph pg map "$BENCH_PG" | tee "$BENCH_EVIDENCE/pg.before.txt"
pa2_ceph health detail
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Pool phải tồn tại, replicated, đúng ID, chỉ một PG ổn định; 2 thuộc mapping và 5 chưa thuộc mapping. Sai gate thì HOLD; không tạo lại pool để tìm ID 12, không tự ép upmap mới hoặc thu nhỏ PG. Nếu đang nối tiếp phiên đã chuyển `12.0` sang 5, đây không còn là BEFORE mới: giữ evidence cũ, ghi `LATE_START`, chỉ đo các bước còn lại.

Để giữ đúng một PG suốt benchmark, autoscale của riêng pool phải OFF trước warm-up. Nếu chưa OFF, block dưới lưu giá trị cũ rồi tắt, ghi rõ đây là preparation ngoài phép đo. File restore toàn cluster của MOP vẫn giữ nguyên.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
jq -r '.pools[] | select(.pool_name=="bench_pa2")
  | [.pool_name,.pg_autoscale_mode] | @tsv' \
  "$BENCH_EVIDENCE/pool-check.osd.json" \
  > "$BENCH_EVIDENCE/autoscale.before.tsv"
pa2_ceph osd pool set "$BENCH_POOL" pg_autoscale_mode off
printf 'bench_pa2 autoscale off: PREPARE / OUT_OF_MEASUREMENT\n' \
  > "$BENCH_EVIDENCE/preparation.txt"
typeset -p BENCH_POOL BENCH_PG > "$BENCH_EVIDENCE/bench.env"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Nếu pool được tạo sau baseline `00-*` của MOP, ghi rõ asset benchmark bổ sung; không ghi đè baseline cũ. Lưu cấu hình hiện tại ở thư mục này; gate/rule scope của MOP phải đọc pool mới từ snapshot live. Khi bàn giao, reconcile giá trị autoscale ở cả file này và baseline MOP, không tự bật lại trong chain.

### 3.2 Timeline T1 và collector T2

Định nghĩa trong **mỗi terminal gọi event**, kể cả sau mở lại shell:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
: "${EVIDENCE:?nap phien bang pa2_load_run o muc 2.1}"
event() {
  jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
    --arg phase "$1" --arg step "$2" \
    '{ts:$ts,phase:$phase,step:$step}' >> "$EVIDENCE/events.jsonl"
}
event PREPARE ZSH_SESSION_READY
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Trước đo, kiểm đồng bộ giờ ở host quản trị, runner và OSD hosts; lưu `date -u` và `chronyc tracking`/`chronyc sources -v` nếu dùng chrony. Chưa xử lý clock skew thì HOLD. Trên **T2 host zsh**, nạp cùng phiên theo mục 2.1 rồi chạy collector liên tục, chỉ một instance. Collector mới dùng thư mục riêng, giữ nguyên dữ liệu collector cũ. T1 ghi `event PREPARE COLLECTOR_ZSH_START` ngay trước khi T2 chạy; nếu có chuyển từ collector cũ thì bổ sung thời gian gap thật vào ghi chú. Nếu đã có collector.stop, xác minh phiên trước đã kết thúc và chuyển marker đó sang tên lưu trữ có timestamp trước khi chủ động resume, không xóa tự động:

**Chạy khối dưới tại T2 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
typeset -gx PA2_COLLECTOR_DIR="$BENCH_EVIDENCE/collector-zsh-$(date -u +%Y%m%dT%H%M%S.%NZ)"
mkdir "$PA2_COLLECTOR_DIR"
if [[ -f "$EVIDENCE/collector.stop" ]]; then
  print -u2 -- "HOLD: collector.stop da co; xac minh phien da dung truoc khi resume"
  return 1
fi
while [[ ! -f "$EVIDENCE/collector.stop" ]]; do
  T="$(date -u +%Y%m%dT%H%M%S.%NZ)"
  for KIND in pg12 status osd_perf pool_config; do
    case "$KIND" in
      pg12) CMD=(pg 12.0 query -f json) ;;
      status) CMD=(-s -f json) ;;
      osd_perf) CMD=(osd perf -f json) ;;
      pool_config) CMD=(osd pool get bench_pa2 all -f json) ;;
    esac
    START="$(date -u +%FT%T.%3NZ)"
    RC=0
    sudo -n timeout 5 "$PA2_CEPH_BIN" --conf "$PA2_CONF" --id admin --keyring "$PA2_KEYRING" "${CMD[@]}" \
      > "$PA2_COLLECTOR_DIR/$T.$KIND.json" \
      2> "$PA2_COLLECTOR_DIR/$T.$KIND.stderr" || RC=$?
    printf '%s\t%s\t%s\t%s\n' "$START" "$KIND" "$RC" \
      "$(date -u +%FT%T.%3NZ)" \
      >> "$PA2_COLLECTOR_DIR/manifest.tsv"
  done
  sleep 5
done
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Kiểm `pg_num/pgp_num` vẫn 1, autoscale OFF suốt run. PG query cung cấp state, up/acting, primary và scrub markers để gắn với QoS. Timeout/file lỗi là thiếu dữ liệu, không coi là số 0. Query cluster/OSD là bối cảnh chung, không gọi số liệu này là IOPS riêng của pool.

### 3.3 T3 — tạo image RBD riêng và map

**T3 · HOST ceph-master · zsh.** Nạp cùng phiên theo mục 2.1 ở T3 trước, không chạy khối này trong T2 đang thu log. Các lệnh sau kiểm client rồi lưu version vào thư mục mới để không ghi đè version của lần thử trước.

**Chạy khối dưới tại T3 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
: "${EVIDENCE:?nap phien theo muc 2.1}"
: "${BENCH_EVIDENCE:?nap phien theo muc 2.1}"
for TOOL in fio jq sha256sum python3; do
  whence -p "$TOOL" || { print -u2 -- "HOLD: thieu $TOOL"; return 1; }
done
sudo -v
test "$(pa2_ceph fsid)" = "$EXPECTED_FSID"
typeset -gx PA2_CLIENT_CHECK="$BENCH_EVIDENCE/client-check-$(date -u +%Y%m%dT%H%M%S.%NZ)"
mkdir "$PA2_CLIENT_CHECK"
pa2_ceph --version > "$PA2_CLIENT_CHECK/ceph.version.txt"
pa2_rbd --version > "$PA2_CLIENT_CHECK/rbd.version.txt"
fio --version | tee "$PA2_CLIENT_CHECK/fio.version.txt"
uname -a > "$PA2_CLIENT_CHECK/client-kernel.txt"
fio --enghelp=libaio > "$PA2_CLIENT_CHECK/fio-libaio.txt"
pa2_ceph osd pool application get "$BENCH_POOL"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**Nếu `$BENCH_EVIDENCE/client.env` đã có:** chưa chạy khối tạo image bên dưới; nạp và kiểm mapping theo phần T4 ở mục 3.4 trước. Nếu fio đã chạy thì không prefill lại. Khối tạo chỉ dành cho image mới chưa tồn tại.

Nếu pool chưa được khởi tạo dùng RBD, chạy `pa2_rbd pool init bench_pa2` **một lần trong PREPARE**, ghi vào `preparation.txt`. Pool này phải là pool lab dành cho bài thử. Không chuyển workload ứng dụng thật sang pool này.

**Chạy khối dưới tại T3 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx BENCH_IMAGE="pa2-${RUN_ID}"
# List thanh cong truoc; image cung ten da ton tai thi HOLD, khong tai su dung.
pa2_rbd ls --pool "$BENCH_POOL" --format json \
  > "$BENCH_EVIDENCE/images.before.json"
jq -e --arg name "$BENCH_IMAGE" 'index($name)==null' \
  "$BENCH_EVIDENCE/images.before.json"
pa2_rbd create "$BENCH_POOL/$BENCH_IMAGE" --size 1024 \
  --image-format 2 --image-feature layering
pa2_rbd info "$BENCH_POOL/$BENCH_IMAGE" --format json \
  > "$BENCH_EVIDENCE/image.json"
typeset -gx DEV="$(pa2_rbd device map "$BENCH_POOL/$BENCH_IMAGE")"
test -b "$DEV"
pa2_rbd device list --format json > "$BENCH_EVIDENCE/devices.json"
python3 - "$BENCH_EVIDENCE/devices.json" "$BENCH_POOL" "$BENCH_IMAGE" "$DEV" <<'PY'
import json, sys
path, pool, image, dev = sys.argv[1:]
x = json.load(open(path))
rows = list(x.values()) if isinstance(x, dict) else x
assert any(r.get('pool') == pool and r.get('name') == image
           and r.get('device') == dev and r.get('snap', '-') in ('-', '')
           for r in rows), 'HOLD: device does not match newly created image'
PY
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT "$DEV"
# Khong format/mount: fio dung raw RBD device cua image MOI vua tao.
# Neu co mount/holder ngoai du kien, dung lai de kiem tra.
typeset -p RUN_ID EVIDENCE BENCH_EVIDENCE BENCH_POOL BENCH_PG \
  BENCH_IMAGE DEV > "$BENCH_EVIDENCE/client.env"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Image 1 GiB; fio chỉ dùng 512 MiB đầu. Phần sentinel 4 MiB bắt đầu tại offset 768 MiB, không chồng vùng fio. Dự trù raw capacity theo số replica cộng headroom. Không thay `$DEV` bằng `/dev/sdX`, NVMe OSD hoặc image đang có dữ liệu.

### 3.4 T3/T4 — prefill, sentinel và kiểm mapping

Prefill ghi dữ liệu thật vào vùng fio trước BEFORE. Chưa prefill thì các read vào vùng thưa có thể không đại diện tải đọc dữ liệu đã tồn tại.

**Chạy khối dưới tại T3 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
sudo fio --name=prefill --filename="$DEV" --allow_file_create=0 \
  --rw=write --bs=1M --size=512M --ioengine=libaio \
  --direct=1 --iodepth=4 --refill_buffers=1 --end_fsync=1 \
  --output-format=json --output="$BENCH_EVIDENCE/fio-prefill.json"
jq -e 'all(.jobs[]; .error==0)' "$BENCH_EVIDENCE/fio-prefill.json"
dd if=/dev/urandom of="$BENCH_EVIDENCE/sentinel.bin" \
  bs=1M count=4 status=none
sudo dd if="$BENCH_EVIDENCE/sentinel.bin" of="$DEV" \
  bs=1M seek=768 count=4 oflag=direct conv=notrunc,fsync status=none
sha256sum "$BENCH_EVIDENCE/sentinel.bin" \
  > "$BENCH_EVIDENCE/sentinel.expected.sha256"
# Default layout, khong data-pool rieng: data object 0 cua image moi.
PREFIX="$(jq -er '.block_name_prefix' "$BENCH_EVIDENCE/image.json")"
pa2_ceph osd map "$BENCH_POOL" "${PREFIX}.0000000000000000" \
  | tee "$BENCH_EVIDENCE/data-object.map.txt"
pa2_ceph pg map "$BENCH_PG"
pa2_ceph -s
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Output `ceph osd map` phải chỉ đúng `12.0`. Kiểm image không có `data_pool` trỏ pool khác. Cùng pool có đúng một PG và image không dùng data pool khác thì data objects của image đều vào PG đó. Đây là bằng chứng phạm vi workload, không chứng minh mọi replica vật lý đều được client đọc.

**T4 · HOST ceph-master · zsh — nạp cùng phiên theo mục 2.1, rồi nạp client.env.** Không dùng T3 khi fio đang chạy. Chạy khối dưới mỗi lần mở T4 hoặc trước khi sử dụng lại `$DEV`; không đoán `/dev/rbd0`.

**Chạy khối dưới tại T4 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
: "${BENCH_EVIDENCE:?nap phien theo muc 2.1}"
typeset -gx PA2_CLIENT_ENV="$BENCH_EVIDENCE/client.env"
test -r "$PA2_CLIENT_ENV"
source "$PA2_CLIENT_ENV"
typeset -gx MOP_DIR="$PA2_HOST_DIR"
typeset -gx EVIDENCE="$MOP_DIR/evidence/$RUN_ID"
typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
test "$BENCH_POOL" = bench_pa2
test "$BENCH_PG" = 12.0
test -b "$DEV"
pa2_rbd device list --format json | python3 -c '
import json,sys
x=json.load(sys.stdin)
rows=list(x.values()) if isinstance(x,dict) else x
pool,image,dev=sys.argv[1:]
assert any(r.get("pool")==pool and r.get("name")==image and r.get("device")==dev for r in rows), "HOLD: mapping khong khop"
' "$BENCH_POOL" "$BENCH_IMAGE" "$DEV"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**T4 · HOST · zsh — đọc sentinel tại BEFORE, PRE_TRANSFER, AFTER_HANDOFF, AFTER_TRANSFER, AFTER_UPGRADE hoặc AFTER.** Đặt CHECKPOINT đúng lần đang đo, không dùng lại tên có file. Trước mỗi lần đọc, T1 ghi event `SENTINEL:<checkpoint>`.

**Chạy khối dưới tại T4 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx CHECKPOINT=BEFORE
OUT="$BENCH_EVIDENCE/sentinel.$CHECKPOINT.sha256"
test ! -e "$OUT"
sudo dd if="$DEV" bs=1M skip=768 count=4 iflag=direct status=none \
  | sha256sum > "$OUT"
test "$(awk '{print $1}' "$BENCH_EVIDENCE/sentinel.expected.sha256")" = \
     "$(awk '{print $1}' "$OUT")"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Ghi event `SENTINEL:<checkpoint>` ở T1 trước mỗi lần đọc. Mismatch là HOLD; không ghi lại sentinel để lấy PASS. Sentinel chỉ kiểm vùng bất biến, không kiểm toàn bộ vùng fio đang thay đổi. Deep-scrub PRE/POST của MOP vẫn phải làm đầy đủ.

### 3.5 T3 — chạy fio liên tục

Sau prefill, cluster sạch/ổn định, lưu profile rồi chạy trong một terminal riêng. Không khởi động lại fio giữa BEFORE/DURING/AFTER.

**Chạy khối dưới tại T3 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
test ! -e "$BENCH_EVIDENCE/workload.fio"
cat > "$BENCH_EVIDENCE/workload.fio" <<EOF_FIO
[global]
filename=$DEV
allow_file_create=0
ioengine=libaio
direct=1
rw=randrw
rwmixread=70
bs=4k
offset=0
size=512M
iodepth=8
numjobs=1
time_based=1
runtime=21600
group_reporting=1
percentile_list=50:95:99
write_bw_log=$BENCH_EVIDENCE/fio
write_iops_log=$BENCH_EVIDENCE/fio
write_hist_log=$BENCH_EVIDENCE/fio
log_avg_msec=1000
log_hist_msec=1000
log_hist_coarseness=0
log_unix_epoch=1
[pa2-pg12]
EOF_FIO
sha256sum "$BENCH_EVIDENCE/workload.fio" \
  > "$BENCH_EVIDENCE/workload.sha256"
sudo fio "$BENCH_EVIDENCE/workload.fio" \
  --output-format=json+ --output="$BENCH_EVIDENCE/fio-total.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Warm-up **ít nhất 60 giây sau khi fio đã phát I/O**, quan sát ổn định rồi T1 mới mở BEFORE. Không dùng ramp_time trong profile này để tránh bỏ log warm-up; khi phân tích chỉ lấy timestamp thuộc các window đã đánh dấu. Log có thể được buffer; không suy stall chỉ từ việc file chưa tăng kích thước, đối chiếu trạng thái fio/client và collector.

Runtime là trần 6 giờ, không đảm bảo MOP kết thúc trong 6 giờ. Nếu runner tự kết thúc trước AFTER, ghi gap, không gọi là continuous; lên kế hoạch runtime lớn hơn trước run sau. Profile là closed-loop depth 8: IOPS có thể giảm khi latency tăng, không phải fixed offered IOPS. p95/p99 từ histogram là **completion latency (clat)**, không phải toàn bộ thời gian request ứng dụng.

## 4 T1 — đo BEFORE của toàn bài

Chờ fio warm-up ít nhất 60 giây, tải và cluster ổn định, đồng hồ đồng bộ. Trước mutation ở mục 5:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
event BEFORE BEGIN
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Giữ tải **600 giây**, không thao tác placement. Sau đủ cửa sổ:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event BEFORE END
pa2_ceph -s > "$BENCH_EVIDENCE/before.status.txt"
pa2_ceph pg 12.0 query -f json > "$BENCH_EVIDENCE/before.pg12.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Đánh giá chất lượng baseline và gate ở mục 16. Fio/collector tiếp tục chạy; không restart giữa các phase. Nếu đã có mutation trước cửa sổ này, đánh dấu `BEFORE=BASELINE_MISSING`; không gọi trạng thái hiện tại là baseline gốc. Một PRE_TRANSFER hợp lệ ở mục 9 vẫn có thể đo tác động các handoff **chưa thực hiện**.

## 5 T1 — đóng băng placement, kiểm/nâng spare osd.5

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING FREEZE_PLACEMENT
pa2_ceph balancer off
while IFS=$'\t' read -r POOL MODE; do
  case "$MODE" in
    on|off|warn) pa2_ceph osd pool set "$POOL" pg_autoscale_mode off ;;
    *) echo "HOLD: unknown mode for $POOL"; return 1 ;;
  esac
done < "$EVIDENCE/autoscale.before.tsv"
pa2_ceph osd dump -f json | jq '{flags,pools:
  [.pools[] | {pool,pool_name,pg_num,pg_placement_num,
    pg_num_target,pg_placement_num_target}]}'
pa2_ceph -s
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Chờ split/merge, PG/PGP target và recovery đã bắt đầu hoàn tất. Kiểm global/per-OSD/per-pool flags và cấu hình chặn recovery/backfill/scrub. Không bật `norecover`, `nobackfill`, `norebalance`, `noscrub`, `nodeep-scrub` cho bài này. Cờ cũ có owner khác phải reconcile; không unset hàng loạt.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph tell osd.5 version
pa2_ceph orch ps --daemon_type osd --daemon_id 5 \
  --format json --refresh
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Nếu 5 **đã** ở đúng target version/image digest, bỏ block redeploy dưới. Nếu còn bản cũ, phải nâng 5 khi vẫn rỗng rồi mới được nhận PG. Kiểm MGR/MON/crash prerequisite của hop đã hoàn tất, CLI hỗ trợ `redeploy --image` và registry pull được. Đối chiếu digest trên host thực; dùng digest đã xác minh cho `TARGET_IMAGE` thay tag khi thực hiện chính thức [S4].

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# Chi chay neu osd.5 chua dung target; planned down set luc nay chi co 5.
event DURING SPARE_UPGRADE
pa2_ceph pg dump pgs -f json > "$EVIDENCE/S-before-upgrade.pgs.json"
python3 "$HELPER" isolate \
  --pgs "$EVIDENCE/S-before-upgrade.pgs.json" --osd 5
pa2_ceph osd ok-to-stop 5
pa2_ceph orch daemon redeploy osd.5 --image "$TARGET_IMAGE"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Chờ daemon `running`, up/in, version 16.2.15 và đúng image digest; thu lại metadata/daemon output và toàn PG để kiểm 5 vẫn isolate. Redeploy đã bao gồm stop/start, không cần dừng daemon thêm một lần. Nếu dùng scoped `noout`, chỉ đặt/gỡ cờ do phiên mình sở hữu; lưu trạng thái cũ. Chưa xong bước này thì không handoff.

## 6 T1 — kiểm topology và giữ CRUSH rule host

Lượt này thay **osd.2 bằng osd.5**, không thêm replica thứ hai cùng host vào final mapping. Giả thiết cần kiểm: hai OSD cùng host; rule replicated đơn giản chọn host; 5 nằm trong root/class mà rule cho phép; từng expected set vẫn có đủ OSD và host phân biệt. Gate này chỉ đọc cluster.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  [[ "$X" == 2 && "$S" == 5 ]]
  pa2_ceph osd find 2 -f json > "$EVIDENCE/topology-find-2.json"
  pa2_ceph osd find 5 -f json > "$EVIDENCE/topology-find-5.json"
  pa2_ceph osd crush dump -f json > "$EVIDENCE/pre-rule.crush.json"
  pa2_ceph osd crush rule dump -f json > "$EVIDENCE/pre-rule.rules.json"
  pa2_ceph osd dump -f json > "$EVIDENCE/pre-rule.osd.json"
  pa2_ceph pg dump pgs -f json > "$EVIDENCE/pre-rule.pgs.json"
  python3 - "$EVIDENCE" <<'PY'
import json, sys
from pathlib import Path
e = Path(sys.argv[1])
def read(name):
    return json.loads((e / name).read_text())
f2, f5 = (read(f'topology-find-{i}.json') for i in (2, 5))
h2 = f2['crush_location']['host']
h5 = f5['crush_location']['host']
assert h2 and h2 == h5, 'HOLD: 2/5 khac host; can revision topology'
crush = read('pre-rule.crush.json')
buckets = {b['id']: b for b in crush['buckets']}
hosts = {}
for b in buckets.values():
    if b['type_name'] == 'host' and '~' not in b['name']:
        for item in b['items']:
            if item['id'] >= 0:
                assert item['id'] not in hosts, 'HOLD: ambiguous OSD host'
                hosts[item['id']] = b['name']
assert hosts[2] == h2 and hosts[5] == h5, 'HOLD: host map mismatch'
def leaves(item_id, seen=None):
    seen = set() if seen is None else seen
    assert item_id not in seen, 'HOLD: CRUSH cycle'
    if item_id >= 0:
        return {item_id}
    return set().union(*(leaves(x['id'], seen | {item_id})
                         for x in buckets[item_id]['items']))
osdmap = read('pre-rule.osd.json')
pools = {p['pool']: p for p in osdmap['pools']}
rules = {r['rule_id']: r for r in read('pre-rule.rules.json')}
dump = read('pre-rule.pgs.json')
pgs = dump['pg_stats'] if 'pg_stats' in dump else dump['pg_map']['pg_stats']
assert pgs, 'HOLD: empty PG snapshot'
assert all(5 not in p['up'] and 5 not in p['acting'] for p in pgs), 'HOLD: spare 5 still has PG'
scope = [p for p in pgs if 2 in p['up'] or 2 in p['acting']]
assert scope, 'HOLD: no PG on source 2'
rows = {}
for p in scope:
    assert p['state'] == 'active+clean' and p['up'] == p['acting'], f"HOLD: unstable {p['pgid']}"
    pool = pools[int(p['pgid'].split('.')[0])]
    assert pool['type'] == 1, 'HOLD: EC outside this MOP'
    rule = rules[pool['crush_rule']]
    steps = rule['steps']
    assert len(steps) == 3, 'HOLD: custom CRUSH rule needs review'
    assert steps[0]['op'] == 'take' and steps[2]['op'] == 'emit'
    assert steps[1]['op'] == 'chooseleaf_firstn' and steps[1]['type'] == 'host' and steps[1]['num'] == 0, 'HOLD: rule is not simple host rule'
    eligible = leaves(steps[0]['item'])
    expected = [5 if i == 2 else i for i in p['acting']]
    assert len(expected) == pool['size'] and len(set(expected)) == pool['size']
    assert set(expected) <= eligible, 'HOLD: root/class mismatch'
    assert len({hosts[i] for i in expected}) == pool['size'], 'HOLD: duplicate host in expected set'
    rows[pool['pool']] = [pool['pool'], pool['pool_name'], pool['crush_rule'], pool['type'], pool['size'], pool['min_size']]
(e / 'rule-scope.tsv').write_text(''.join('\t'.join(map(str, rows[k])) + '\n' for k in sorted(rows)))
print(f'PASS: osd.2 / osd.5 host={h2}; {len(scope)} PG expected host sets valid; rule unchanged')
PY
  event DURING RULE_UNCHANGED_STABLE
  pa2_ceph -s
  pa2_ceph health detail
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: topology/rule chua dat; chua sang muc 7"
fi
```

Giữ tải ổn định **300 giây** rồi sang mục 7. Không chạy `create-replicated`, không đổi `crush_rule`, không sửa CRUSH map ở bước này. Nếu phiên trước đã đổi live sang rule `osd`, gate sẽ HOLD; không tự đổi ngược khi còn upmap phụ thuộc. Snapshot này không thay helper plan, kiểm weight-set, canary live hay kiểm HA. Khi chuyển xong, expected mapping phải chỉ thay **2 → 5**, primary vẫn ở peer khác.

## 7 T1 — dịch primary, chốt toàn handoff set

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING PREPARE_AFFINITY
pa2_ceph osd primary-affinity osd.2 0
pa2_ceph osd primary-affinity osd.5 0
pa2_ceph pg ls-by-primary 2
pa2_ceph pg ls-by-primary 5
pa2_ceph -s
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Chờ ổn định. Cả 2 và 5 không được là actual primary trong handoff. Affinity không phải cơ chế isolate replica. Nếu không dịch được primary khỏi 2, kiểm affinity peer và lập revision, không đổi tùy tiện các peer.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph pg dump pgs -f json > "$EVIDENCE/bind.pgs.json"
pa2_ceph osd dump -f json > "$EVIDENCE/bind.osd.json"
pa2_ceph osd crush dump -f json > "$EVIDENCE/bind.crush.json"
python3 "$HELPER" plan \
  --pgs "$EVIDENCE/bind.pgs.json" \
  --osdmap "$EVIDENCE/bind.osd.json" \
  --crush "$EVIDENCE/bind.crush.json" \
  --out "$EVIDENCE/plan.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Helper phải kiểm toàn PG, `up=acting`, đúng số replica phân biệt, root/class/rule, 5 chưa có PG, không có override xung đột trong handoff set. Không dùng `--allow-host-colocation` trong nhánh giữ rule host. Helper phải tạo plan đúng cặp 2 → 5 và xác minh failure domain/root/class. Kết quả offline không thay thế canary live, capacity, digest, workload hay scrub gate.

Nếu đã có `pg_upmap`, `pg_upmap_items`, `pg_temp`, `primary_temp` trong scope, nhánh này HOLD để reconcile before/current/desired và owner. `pg-upmap-items` ghi đè danh sách cặp cho PG, không append. Không xóa override cũ để vượt gate.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# Chot danh sach tu toan up/acting, sau khi tat autoscale va kiem rule.
jq -r '(.pg_stats // .pg_map.pg_stats)[]
  | select((.up|index(2))!=null or (.acting|index(2))!=null)
  | .pgid' "$EVIDENCE/bind.pgs.json" \
  | sort -V > "$EVIDENCE/handoff.txt"
test -s "$EVIDENCE/handoff.txt"
wc -l "$EVIDENCE/handoff.txt"
: > "$EVIDENCE/pre.accepted.txt"
: > "$EVIDENCE/post.accepted.txt"
: > "$EVIDENCE/upmaps.intent.tsv"
sha256sum "$EVIDENCE"/bind.*.json "$EVIDENCE/plan.json" \
  "$EVIDENCE/handoff.txt" > "$EVIDENCE/bind.sha256"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

## 8 T1 — deep-scrub PRE toàn handoff set

**Làm toàn bộ mục này cho mọi PG trong `handoff.txt` trước lệnh upmap đầu tiên.** Không interleave kiểu scrub PRE một PG rồi chuyển ngay PG đó trong khi các PG còn lại chưa PRE.

Với mỗi PG, chạy block dưới. `PG` lấy từ `handoff.txt`; sau đó lặp đủ danh sách. Tải benchmark vẫn chạy; giữ scrub concurrency 1.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx PG='DIEN_PG_TRONG_handoff.txt'
grep -Fxq "$PG" "$EVIDENCE/handoff.txt"
typeset -gx STAGE=PRE_HANDOFF
typeset -gx D="$EVIDENCE/scrub/$STAGE/$PG"
mkdir -p "$D"
pa2_ceph pg "$PG" query -f json > "$D/before.query.json"
pa2_ceph pg dump pgs -f json | jq -e --arg pg "$PG" \
  '(.pg_stats // .pg_map.pg_stats)[] | select(.pgid==$pg)' \
  > "$D/before.json"
date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$D/requested.txt"
event DURING "$STAGE:$PG:REQUEST"
pa2_ceph pg deep-scrub "$PG" | tee "$D/request.out.txt"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Theo dõi lượt scrub mới bằng query/log. Chạy block lấy mẫu dưới nhiều lần, chờ completion mới; không queue lại `deep-scrub` mỗi lần lấy mẫu. Lưu timestamp quan sát start/scrubbing/deep; nếu scrub nhanh quá không quan sát được start, thu log scrub từ primary/OSD và đối chiếu interval. Thiếu bằng chứng thì INCONCLUSIVE, không bấm PASS bằng marker cũ.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
DEADLINE=$((SECONDS + TIMEOUT))
READY=0
while (( SECONDS < DEADLINE )); do
  T="$(date -u +%Y%m%dT%H%M%SZ)"
  pa2_ceph pg "$PG" query -f json > "$D/query-$T.json"
  pa2_ceph pg dump pgs -f json | jq -e --arg pg "$PG" \
    '(.pg_stats // .pg_map.pg_stats)[] | select(.pgid==$pg)' \
    > "$D/after.json"
  cp "$D/after.json" "$D/stat-$T.json"
  if jq -e '(.stat_sum.num_scrub_errors // 0)>0 or
      (.stat_sum.num_deep_scrub_errors // 0)>0 or
      (.stat_sum.num_shallow_scrub_errors // 0)>0 or
      (.state|test("inconsistent|unfound|incomplete"))' \
      "$D/after.json" > /dev/null; then
    echo 'HOLD: scrub/data error'; return 1
  fi
  if python3 "$HELPER" scrub --before "$D/before.json" \
      --after "$D/after.json" --requested "$(cat "$D/requested.txt")"; then
    READY=1; break
  else
    RC=$?
    test "$RC" = 3 || { echo 'HOLD: invalid scrub evidence'; return 1; }
  fi
  sleep 5
done
test "$READY" = 1 || { echo 'HOLD: scrub timeout or invalid evidence'; return 1; }
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Helper chỉ chấp nhận marker deep-scrub mới, thời điểm sau request, state đã trở về active+clean, mapping/primary không đổi, các bộ đếm lỗi tồn tại và bằng 0. Ngoài helper, operator kiểm `ceph health detail`, log request/start/completion, incarnation và không có mapping đổi rồi đổi lại trong interval. Không coi `last_deep_scrub` version phải tăng khi PG không ghi; dùng completion timestamp mới. Không tự `repair`.

Để lấy log đúng primary, đọc ID từ `before.json`, tra host và chạy journalctl trên host đó. Chép kết quả về thư mục `D` của PG trên máy quản trị. Nếu logging hiện tại không có start/completion và query cũng không quan sát được, giữ INCONCLUSIVE, không tự tăng debug toàn cluster trong lúc benchmark.

**T1 · HOST ceph-master · zsh — tìm actual primary và host:**

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  typeset -gx PRIMARY="$(jq -er '.acting_primary' "$D/before.json")"
  pa2_ceph osd find "$PRIMARY"
  cat "$D/requested.txt"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**T5 · HOST actual primary vừa tìm · zsh — chỉ lấy log.** Nếu primary trên ceph-master, T5 cũng là SSH mới vào ceph-master. Điền FSID/PRIMARY/request UTC theo output T1; T5 không tự có biến của T1. Chép log về thư mục `$D` ở T1 sau đó.

**Chạy khối dưới tại T5 — host actual primary · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
  local PA2_LOG_PRIMARY='DIEN_OSD_ID'
  local PA2_LOG_SINCE='DIEN_REQUEST_UTC'
  [[ "$PA2_LOG_PRIMARY" != DIEN_OSD_ID && "$PA2_LOG_SINCE" != DIEN_REQUEST_UTC ]]
  local PA2_LOG_FILE="$HOME/scrub-primary-$(date -u +%Y%m%dT%H%M%S.%NZ).txt"
  sudo journalctl -u "ceph-17c77e12-a16a-11f1-838e-cf68e9c001d8@osd.${PA2_LOG_PRIMARY}.service" --since "$PA2_LOG_SINCE" --no-pager > "$PA2_LOG_FILE"
  print -r -- "$PA2_LOG_FILE"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```


**Chỉ sau khi cả evidence và gate đạt**, ghi nhận PG:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph health detail > "$D/health.txt"
printf '%s\n' "$PG" >> "$EVIDENCE/pre.accepted.txt"
event DURING "PRE_HANDOFF:$PG:ACCEPTED"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Cuối PRE, kiểm đủ coverage và baseline chưa đổi:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
sort -Vu "$EVIDENCE/handoff.txt" > "$EVIDENCE/need.sorted"
sort -Vu "$EVIDENCE/pre.accepted.txt" > "$EVIDENCE/pre.sorted"
diff -u "$EVIDENCE/need.sorted" "$EVIDENCE/pre.sorted"
pa2_ceph pg dump pgs -f json > "$EVIDENCE/pre-complete.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/pre-complete.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
pa2_ceph osd dump -f json > "$EVIDENCE/pre-complete.osd.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Recheck OSD UUID/incarnation, related pool/rule/weight-set và version/digest so với bind. Set/mapping/incarnation thay đổi liên quan thì invalidate evidence đó và lập revision. Epoch tăng do cập nhật không liên quan không tự làm hỏng toàn evidence.

## 9 T1 — PRE_TRANSFER: baseline chính ngay trước chuyển

Sau toàn bộ PRE scrub ở mục 8 đạt, chờ cluster và workload ổn định. Trong PRE_TRANSFER không chạy đổi rule, affinity, upmap, scrub chủ động hay thao tác nâng daemon. Scrub tự động/tải ngoài nếu xảy ra phải đánh dấu; cửa sổ bị nhiễu không đủ điều kiện làm baseline sạch.

Kiểm lại PG benchmark sau kiểm rule và affinity; không dùng mapping trước preparation:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx BENCH_POOL=bench_pa2 BENCH_PG=12.0
typeset -gx BENCH_EVIDENCE="$EVIDENCE/bench-12.0"
typeset -gx PG=12.0
grep -Fxq "$PG" "$EVIDENCE/handoff.txt"
grep -Fxq "$PG" "$EVIDENCE/pre.accepted.txt"
pa2_ceph pg 12.0 query -f json > "$BENCH_EVIDENCE/pre-transfer.pg12.json"
jq -e '.state=="active+clean" and .up==.acting
  and (.acting|index(2))!=null and (.acting|index(5))==null
  and (.acting_primary|type)=="number"
  and .acting_primary!=2 and .acting_primary!=5' \
  "$BENCH_EVIDENCE/pre-transfer.pg12.json"
pa2_ceph osd pool get bench_pa2 all -f json \
  > "$BENCH_EVIDENCE/pre-transfer.pool.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Xác nhận PG/PGP/target vẫn 1, autoscale OFF. Nếu 12.0 không còn có osd.2 thì HOLD kế hoạch test này, không tự thêm upmap để vượt gate. Kiểm sentinel PRE_TRANSFER ở T4 theo mục 3.4, ghi event riêng rồi chờ tải ổn định trước mở cửa sổ.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event PRE_TRANSFER BEGIN
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Giữ fio và collector **600 giây**. Sau đó:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event PRE_TRANSFER END
pa2_ceph -s > "$BENCH_EVIDENCE/pre-transfer.status.txt"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Đây là mốc so sánh chính của handoff, giữ nguyên BEFORE cũ. Chốt ngưỡng/đơn vị/cách tính ở mục 16 trước mutation đầu tiên. Không đặt 12.0 làm primary trên 2 khi mục tiêu là đo handoff replica; actual primary khác 2 và 5 ở gate trên. Nếu QoS chưa ổn định thì chưa chuyển.

## 10 T1 — chuyển canary 12.0, quan sát phục hồi, rồi các PG còn lại

Chọn **một PG có dữ liệu** trong `handoff.txt`, 2 đang là replica, 5 chưa trong mapping. Với BENCH hiện tại, canary là `12.0` sau khi qua gate mục 9; nếu không còn trong handoff set hoặc 2 không thuộc mapping thì HOLD test. Đặt `PG`, chạy một vòng dưới; PG đầu là canary. Sau canary ổn định đủ `STABLE`, tiếp tục cùng vòng cho các PG còn lại, mỗi lần một PG.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
typeset -gx PG='12.0'  # canary; cac vong sau thay bang PG ke trong handoff.txt
grep -Fxq "$PG" "$EVIDENCE/handoff.txt"
grep -Fxq "$PG" "$EVIDENCE/pre.accepted.txt"
if grep -Fxq "$PG" "$EVIDENCE/post.accepted.txt"; then
  echo 'HOLD: PG da accepted'; return 1
fi
pa2_ceph pg dump pgs -f json > "$EVIDENCE/before-$PG.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/before-$PG.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
pa2_ceph osd dump -f json > "$EVIDENCE/before-$PG.osd.json"
pa2_ceph pg map "$PG"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Recheck hiện không có override của tác nhân khác cho PG, weight/rule/UUID còn khớp và telemetry chưa vượt stop threshold. Ghi intent **trước** mutation, giữ nguyên journal nếu command timeout:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
printf '%s\t%s\t2\t5\n' "$(date -u +%FT%TZ)" "$PG" \
  >> "$EVIDENCE/upmaps.intent.tsv"
event DURING "HANDOFF:$PG:BEGIN"
pa2_ceph osd pg-upmap-items "$PG" 2 5
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Poll các lệnh dưới cho tới khi hội tụ, tối đa `TIMEOUT`. Expected mapping là thay duy nhất 2 bằng 5, giữ thứ tự peer. Không chấp nhận chỉ vì cluster active+clean: MON có thể đã gỡ upmap và PG quay về 2.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
DEADLINE=$((SECONDS + TIMEOUT))
READY=0
while (( SECONDS < DEADLINE )); do
  pa2_ceph pg map "$PG"
  pa2_ceph pg dump pgs -f json > "$EVIDENCE/after-$PG.pgs.json"
  if python3 "$HELPER" progress --pgs "$EVIDENCE/after-$PG.pgs.json" \
      --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
      --pending "$PG"; then
    READY=1; break
  else
    RC=$?
    test "$RC" = 3 || { echo 'HOLD: unexpected mapping/state'; return 1; }
  fi
  pa2_ceph health detail
  sleep 5
done
test "$READY" = 1 || { echo 'HOLD: handoff timeout or invalid mapping'; return 1; }
pa2_ceph osd dump -f json | jq --arg pg "$PG" \
  '.pg_upmap_items[]? | select(.pgid==$pg)'
pa2_ceph health detail
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Gate: đúng up/acting expected, replica đủ, **actual primary khác 5**, các PG ngoài nhóm không đổi ngoài những PG đã accepted. Upmap còn tồn tại đúng cặp `2 → 5`, không bị MON hủy. Không mở nhóm tiếp nếu QoS/health lỗi.

Sau hội tụ và qua gate mapping, ghi:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING "HANDOFF:$PG:CONVERGED"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

**Riêng canary 12.0:** giữ nguyên workload, quan sát **300 giây trước POST scrub**, chưa chuyển PG khác và chưa đổi affinity. Dùng collector để kiểm mapping/primary và QoS. Đây là khoảng quan sát I/O hồi phục sau handoff, không gọi thời điểm PG clean là thời điểm QoS đã hồi phục. Nếu có recovery/tải khác hoặc scrub tự động xen vào, ghi contamination. Sau đủ 300 giây:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
if [[ "$PG" == 12.0 ]]; then
  event DURING "HANDOFF:12.0:OBSERVE_END"
fi
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Nếu chưa hồi phục đến ngưỡng trong cửa sổ, báo chưa quan sát được hồi phục, HOLD mutation kế tiếp theo stop policy; không tự gán thời gian hồi phục =300 giây. Nếu cần kéo dài quan sát, ghi event và lý do. Gate dữ liệu/QoS vẫn có thể HOLD ngay, không phải đợi hết window.

Sau cửa sổ quan sát canary (hoặc ngay sau hội tụ đối với PG kế tiếp), thực hiện **lượt deep-scrub mới** cho chính PG này bằng block mục 8, nhưng gán `STAGE=POST_HANDOFF` và thư mục `D` mới. Lấy before/request/start/after độc lập, chạy helper `scrub`. Khi POST đạt, ghi vào file POST, **không ghi lại PRE**:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# Chi sau POST scrub va QoS gate da dat.
printf '%s\n' "$PG" >> "$EVIDENCE/post.accepted.txt"
event DURING "POST_HANDOFF:$PG:ACCEPTED"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Với canary, theo dõi ít nhất `STABLE` giây dưới workload: mapping vẫn đúng, upmap không bị dọn, latency/error đạt profile. Sau đó ghi event `event DURING OTHER_PGS_BEGIN` trước PG thứ hai, rồi lặp mục 10 cho PG tiếp theo (chỉ ghi mốc này một lần). Không có vòng for mù chạy cả set sau chỉ một PASS.

## 11 T1 — kiểm osd.2 rỗng và đo AFTER_TRANSFER

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
sort -Vu "$EVIDENCE/post.accepted.txt" > "$EVIDENCE/post.sorted"
diff -u "$EVIDENCE/need.sorted" "$EVIDENCE/post.sorted"
pa2_ceph pg dump pgs -f json > "$EVIDENCE/handoff-complete.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/handoff-complete.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt"
python3 "$HELPER" isolate \
  --pgs "$EVIDENCE/handoff-complete.pgs.json" --osd 2
pa2_ceph osd dump -f json > "$EVIDENCE/handoff-complete.osd.json"
pa2_ceph -s
pa2_ceph health detail
pa2_ceph osd df tree
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```



Sau gate toàn set đạt, ghi:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING TRANSFER_ALL_COMPLETE
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Kiểm sentinel AFTER_HANDOFF tại T4 theo mục 3.4; ghi event riêng cho tải đọc bổ sung. Chờ ít nhất `STABLE` giây: cluster clean, không scrub/backfill/recovery, osd.2 vắng toàn up/acting, workload ổn định. Chưa promote 5, chưa redeploy 2.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event AFTER_TRANSFER BEGIN
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Giữ cùng tải **600 giây**. Sau đó:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event AFTER_TRANSFER END
pa2_ceph pg 12.0 query -f json > "$BENCH_EVIDENCE/after-transfer.pg12.json"
pa2_ceph -s > "$BENCH_EVIDENCE/after-transfer.status.txt"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Đọc sentinel AFTER_TRANSFER ở T4 ngoài cửa sổ đo. Kết thúc phần số liệu chính cho tác động chuyển: `PRE_TRANSFER → HANDOFF 12.0 / PG khác → AFTER_TRANSFER`. Tổng thời gian drain bao gồm scrub/chờ; thời gian handoff thuần từng PG là BEGIN→CONVERGED, không đánh đồng hai đại lượng.

**Nếu mục tiêu phiên này chỉ là chuyển và đo:** có thể dừng tại đây, sang mục 14 để dừng tải/collector; ghi `TRANSFER_ONLY`, `SOURCE_UPGRADE=NOT_RUN`, chưa kết luận toàn PA2 hoàn tất. Giữ placement/rule/weight-set, chưa tự cleanup. Nếu tiếp tục nâng trong phiên sau, đọc lại trạng thái, khởi động workload/collector trong evidence segment mới và thực hiện lại readiness/gate; không dùng gate cũ để redeploy.

**Nếu hoàn tất cả PA2 trong phiên này:** giữ fio/collector chạy, tiếp tục mục 12–13 rồi mới sang 14. Dữ liệu upgrade được báo riêng.

## 12 T1 — nhánh tiếp tục: promote 5 và nâng osd.2

Chỉ lúc này mới cho 5 được chọn làm primary theo policy. Đọc affinity cũ; nếu 5 đã có affinity 0 từ giai đoạn chuẩn bị spare thì không hiểu nhầm 0 là chính sách phục vụ lâu dài. Với bài lab này chọn `A5_SERVING=1`; nếu policy thực khác, dùng giá trị đã chốt.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING HANDOFF_COMPLETE
typeset -gx A5_SERVING=1
pa2_ceph osd primary-affinity osd.5 "$A5_SERVING"
pa2_ceph pg ls-by-primary 5
pa2_ceph -s
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Đợi lại stable window dưới benchmark; lưu actual primary mới. Chuyển primary sau đủ POST không thay thế bài kiểm đường ghi/đọc primary; chỉ ghi PASS đường đó khi workload/PG evidence có thật. Sau promote, dùng `--allow-destination-primary`: helper vẫn kiểm đúng tập replica và up=acting, nhưng cho phép primary và thứ tự vector đổi do affinity. Không dùng mode này cho gate replica trong mục 10.

Chốt **planned down set chỉ có 2**, không thao tác đồng thời với osd.5, OSD peer hoặc reboot host chung của 2/5; vẫn yêu cầu `ok-to-stop`, đủ replica hiện hành và capacity. Nếu có thêm daemon down/planned down, HOLD và đánh giá cả tập; không dùng PASS chỉ riêng 2.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING SOURCE_UPGRADE_BEGIN
pa2_ceph pg dump pgs -f json > "$EVIDENCE/upgrade-ready.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/upgrade-ready.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/upgrade-ready.pgs.json" --osd 2
pa2_ceph osd ok-to-stop 2
pa2_ceph orch upgrade status
pa2_ceph osd find 2
pa2_ceph osd metadata 2 -f json > "$EVIDENCE/2-before.metadata.json"
pa2_ceph orch ps --daemon_type osd --daemon_id 2 \
  --format json --refresh > "$EVIDENCE/2-before.daemon.json"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Lưu flag baseline. Chỉ nếu `osd.2` chưa có scoped noout trước phiên, đặt và ghi quyền sở hữu:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# Chi chay neu scoped noout cua 2 chua ton tai.
pa2_ceph osd set-group noout osd.2
printf 'osd.2\n' > "$EVIDENCE/noout.owned.txt"

# Recheck ngay truoc redeploy; lenh chi dinh chinh xac osd.2.
pa2_ceph osd ok-to-stop 2
pa2_ceph orch daemon redeploy osd.2 --image "$TARGET_IMAGE"
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Không cần `orch daemon stop` riêng. Lệnh được enqueue không chứng minh daemon đã nâng xong. Poll đúng daemon, deadline theo `TIMEOUT`:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph orch ps --daemon_type osd --daemon_id 2 --format json --refresh
pa2_ceph tell osd.2 version
pa2_ceph osd metadata 2 -f json
pa2_ceph osd tree
pa2_ceph health detail
pa2_ceph crash ls-new
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Gate: 2 running/up/in, 16.2.15 đúng image digest; cùng OSD ID/UUID, đúng host/device/DB/WAL; không crash mới liên quan. Container ID/pid có thể đổi, không nhầm chúng với OSD incarnation. Metadata/daemon output/version phải cùng xác nhận, không chỉ nhìn tổng `ceph versions`.

## 13 T1 — nhánh tiếp tục: giữ placement và đo AFTER nâng

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
pa2_ceph pg dump pgs -f json > "$EVIDENCE/after-upgrade.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/after-upgrade.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/after-upgrade.pgs.json" --osd 2
pa2_ceph osd dump -f json > "$EVIDENCE/after-upgrade.osd.json"
pa2_ceph osd crush dump -f json > "$EVIDENCE/after-upgrade.crush.json"
pa2_ceph orch ps --daemon_type osd --format json --refresh \
  > "$EVIDENCE/after-upgrade.daemons.json"
pa2_ceph tell osd.2 version > "$EVIDENCE/2-after.version.txt"
pa2_ceph osd metadata 2 -f json > "$EVIDENCE/2-after.metadata.json"
pa2_ceph health detail > "$EVIDENCE/after-upgrade.health.txt"

# Chi go scoped flag ma phien nay da dat.
if [[ -f "$EVIDENCE/noout.owned.txt" ]] && \
   grep -Fxq 'osd.2' "$EVIDENCE/noout.owned.txt"; then
  pa2_ceph osd unset-group noout osd.2
fi
event DURING SPARE_ROTATED
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Kiểm toàn `handoff.txt` vẫn ở expected membership có 5, không có 2; actual primary được phép thay sau promotion. Đọc upmap/weight-set/rule để bảo đảm dependency còn đúng. `osd.2` giữ affinity 0 và weight hiện hữu. Đây là spare candidate được isolate bởi mapping của **tập PG hiện tại**, chưa phải spare bị CRUSH loại vĩnh viễn.

**Disposition cuối lượt:**

| Thành phần | Bàn giao |
|---|---|
| Upmap 2 → 5 | KEEP; owner quản lý chain/phiên lab |
| Weight-set và weight 5 | KEEP; 5 đang chứa PG production/lab của lượt này |
| Rule host của pool | KEEP; mục 6 chỉ kiểm tra, không thay rule |
| Affinity 5 | Chính sách phục vụ đã chốt, lab mặc định 1 |
| Affinity osd.2 | Giữ 0 cho spare candidate; không hiểu là chặn replica |
| Balancer | OFF có owner, thừa kế từ preparation; không bật tự động khi giữ mapping/weight-set này |
| Autoscaler | OFF có owner trong chain lab; giữ file giá trị trước để reconcile sau |
| Scoped noout | Gỡ đúng cờ do phiên tạo khi daemon khỏe |
| Replica validation của 2 sau nâng | `NOT_EXERCISED` tới khi 2 thật sự nhận và được kiểm PG ở lượt kế |

Khi muốn kết thúc toàn chain hoặc thay chính sách HA, cần plan reconcile riêng cho topology, rule, mapping và autoscaler/balancer; tính movement đó vào benchmark. Không tự nạp CRUSH map cũ, không xóa toàn bộ upmap và không bật balancer như bước dọn cuối MOP cũ.

Chờ ít nhất `STABLE` giây liên tục với PG clean, membership giữ đúng, 2 không thuộc bất cứ up/acting nào, telemetry khỏe và workload đạt ngưỡng. Có thay đổi liên quan thì bắt đầu lại window và re-evaluate evidence.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event DURING AFTER_ITERATION_STABLE
event AFTER BEGIN
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Giữ cùng workload/dataset/profile **đủ 600 giây**. Chỉ sau đó chạy block kết thúc:

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
event AFTER END
pa2_ceph -s > "$EVIDENCE/final.status.txt"
pa2_ceph health detail > "$EVIDENCE/final.health.txt"
pa2_ceph osd dump -f json > "$EVIDENCE/final.osd.json"
pa2_ceph pg dump pgs -f json > "$EVIDENCE/final.pgs.json"
python3 "$HELPER" progress --pgs "$EVIDENCE/final.pgs.json" \
  --plan "$EVIDENCE/plan.json" --accepted "$EVIDENCE/post.accepted.txt" \
  --allow-destination-primary
python3 "$HELPER" isolate --pgs "$EVIDENCE/final.pgs.json" --osd 2
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

Kiểm sentinel AFTER_UPGRADE sau khi nâng, và AFTER sau khi kết thúc window, theo mục 3.4.

AFTER ở đây là **AFTER_ITERATION** cho một lượt. Chưa gọi `AFTER_WAVE_STABLE`/`WAVE_COMPLETE`: canary chain tối thiểu còn cần một nguồn kế chuyển vào 2, kiểm 2 sau nâng thực sự phục vụ dữ liệu.

## 14 Dừng fio/collector, unmap đúng image và giữ evidence

Sau AFTER_TRANSFER END nếu chỉ đo chuyển, hoặc AFTER END nếu làm đủ PA2, Ctrl-C **đúng terminal fio**, chờ JSON/log ghi xong. Ghi stop có chủ ý; kiểm `.jobs[].error` và stderr, không coi mọi exit code signal là lỗi storage, cũng không bỏ qua error có thật.

**Chạy khối dưới tại T1 · zsh trên host.**

```zsh
() {
  emulate -L zsh
  setopt ERR_RETURN PIPE_FAIL NO_UNSET GLOBAL_EXPORT
# T1
: "${EVIDENCE:?}"
touch "$EVIDENCE/collector.stop"
event END BENCH_STOPPED
}
PA2_BLOCK_RC=$?
if (( PA2_BLOCK_RC != 0 )); then
  print -u2 -- "HOLD: khoi lenh dung, rc=$PA2_BLOCK_RC; chua chay khoi tiep theo"
fi
```

T3/T4 sau khi fio và sentinel read đã dừng, kiểm mapping đúng pool/image bằng khối kiểm mapping T4 ở mục 3.4; không tự gán lại `/dev/rbd0` khi mở terminal mới. Sau đó mới `pa2_rbd device unmap "$DEV"`. Unmap chỉ tháo thiết bị ở client, không xóa image hay dữ liệu. Giữ image/sentinel/log để báo cáo; không có bước xóa pool/image/upmap trong phụ lục này. Nếu resume, dùng `client.env` và xác minh mapping hiện tại trước bất kỳ I/O nào.

## 15 HOLD và tiếp tục sau gián đoạn

- Lỗi dữ liệu, scrub không có completion mới, sai mapping, upmap bị gỡ, thiếu capacity, sai digest hoặc QoS vượt ngưỡng: dừng mutation mới, giữ collector/evidence. Recovery đang chạy có thể tiếp tục.
- Timeout của upmap/redeploy: đọc map/daemon thực trước retry. Không coi timeout là lệnh chưa chạy; dùng intent journal đối chiếu current state.
- Nếu chưa chuyển PG: sửa nguyên nhân, chờ ổn định và thu lại evidence bị ảnh hưởng. Nếu đã chuyển một phần: giữ accepted PG trên 5, bảo toàn dữ liệu và lập revision; không tự RETURN toàn set.
- Không repair để tạo PASS; không hạ `size/min_size`, không `destroy/purge/zap`. Nâng daemon không yêu cầu các thao tác này.
- Nếu binary mới đã mở/ghi store: không chạy binary cũ lên store đó như rollback mặc định. Giữ PG đang phục vụ trên 5, điều tra và ưu tiên forward-fix theo boundary của hop.
- Upmap không hợp lệ hoặc bị MON gỡ: HOLD, kiểm root/class/weight-set/failure-domain và override hiện hữu; không tắt kiểm tra MON hoặc tự đổi rule để ép mapping.

## 16 Cách tính mức giảm hiệu năng, gián đoạn và báo cáo

### 16.1 Những con số trả lời đúng câu hỏi

| Chỉ số | Định nghĩa/cách tính |
|---|---|
| IOPS baseline B | Trung bình theo thời gian của tổng read+write trong PRE_TRANSFER hợp lệ |
| Mức tụt thấp nhất (%) | `100 × (B − IOPS_min_1s) / B`; ghi đây là đáy cửa sổ 1 giây |
| Mức giảm trung bình (%) | `100 × (B − IOPS_mean_phase) / B`; không thay bằng mức tụt đáy |
| Latency tăng (%) | `100 × (p95_phase / p95_PRE_TRANSFER − 1)`, tương tự p99, tách read/write |
| Thời gian suy giảm | Ngưỡng mô tả đề xuất: từ mẫu 1 giây đầu <80% B đến mẫu bắt đầu chuỗi 5 mẫu 1 giây liên tiếp ≥90% B; giữ ngưỡng cố định trước chuyển |
| Thời điểm đáy → phục hồi | Timestamp mẫu IOPS thấp nhất trong episode → đầu chuỗi phục hồi trên; báo riêng với thời gian suy giảm |
| Khoảng không có completion | Chỉ báo gián đoạn I/O ở client nếu runner vẫn hoạt động và evidence đủ; không suy từ file log thiếu hoặc chưa flush |
| Error/timeout | Đếm từ lỗi fio/client; phân biệt yêu cầu hoàn tất chậm với yêu cầu thất bại |
| Handoff elapsed | Event HANDOFF:PG:BEGIN → CONVERGED; gồm thời gian command và độ trễ poll phát hiện |
| Drain elapsed | Từ HANDOFF:12.0:BEGIN → TRANSFER_ALL_COMPLETE; bao gồm POST scrub, quan sát và các khoảng chờ |

Nếu nhiều lần tụt, báo từng episode và episode dài nhất. Quy ước mẫu theo khoảng kết thúc log, nêu sai số khoảng 1 giây và interval qua biên. Nếu chưa thấy chuỗi phục hồi khi hết quan sát thì ghi `NOT_RECOVERED_WITHIN_WINDOW`, không ép một con số bằng độ dài window. B hoặc percentile baseline bằng 0/missing thì không chia tỷ lệ.

**Hiệu năng suy giảm không đồng nghĩa downtime.** IOPS còn dương nghĩa là vẫn có I/O hoàn tất trong window. Log interval 1 giây hiện tại không chứng minh thời điểm gián đoạn dưới một giây và không đủ tự khẳng định “0 downtime”. Muốn gap từng completion chính xác cần bổ sung instrumentation/per-I/O log đã kiểm overhead trước run; bản này báo giới hạn quan sát theo giây và `DOWNTIME_EXACT=UNMEASURED` nếu không có bằng chứng đó.

### 16.2 Gate và phương pháp xử lý log

Ngưỡng lab gợi ý, chốt trước mutation tương ứng; handoff dùng PRE_TRANSFER làm baseline chính: dữ liệu lỗi/inconsistent/unfound, lỗi I/O mới hoặc timeout thì HOLD; mất collector bắt buộc >30 giây thì HOLD; không completion >30 giây khi xác minh fio còn phát tải thì HOLD. Không gọi output missing là 0 lỗi.

Với cửa sổ 60 giây đủ dữ liệu, xem riêng read/write: HOLD mutation kế tiếp nếu p95 clat >2× baseline hoặc tổng IOPS <70% baseline trong hai cửa sổ liên tiếp. Baseline không ổn định/0/missing thì chưa đủ điều kiện áp tỷ lệ; dừng để chuẩn bị lại benchmark. Đây là ngưỡng thí nghiệm đề xuất, không phải SLO production hay gate tự động đã triển khai. Muốn dùng gate percentile ngay khi chạy cần parser tương thích fio để đọc histogram; nếu chưa có, theo dõi lỗi/health trực tiếp và để verdict latency `PENDING_ANALYSIS`, không tự điền PASS.

- Lưu logs `fio_bw.*.log`, `fio_iops.*.log`, `fio_clat_hist.*.log`, `fio-total.json`, profile/hash, version, events và collector. Tên log cụ thể phụ thuộc phiên bản fio; kiểm file thực sau dừng.
- Chia theo timestamp Unix milliseconds và event UTC; tách read/write. Dùng parser histogram đúng phiên bản fio; gộp bin counts rồi tính p50/p95/p99 từng window. Không lấy trung bình p99, không lấy JSON toàn run làm p99 của BEFORE.
- Interval histogram cắt ngang ranh giới event phải được xử lý nhất quán: loại interval đó và ghi thời lượng loại, hoặc ghi sai số ranh giới tối đa một interval. Chưa xử lý thì kết quả phase rất ngắn chỉ là tham khảo.
- IOPS/bandwidth là từ client fio. Disk IOPS và counter PG/OSD là số liệu khác. `log_avg_msec` tạo các mẫu interval, cần trọng số thời lượng khi gộp; ghi đơn vị theo phiên bản fio.
- Báo lỗi từ job JSON/stderr, clock/gap, số mẫu, primary/up/acting tại từng phase. Thiếu bằng chứng thì INCONCLUSIVE.



### 16.3 Bảng báo cáo sau chạy

| Phase | IOPS trung bình / thấp nhất 1s | Giảm % so PRE_TRANSFER | Read p95/p99 | Write p95/p99 | Suy giảm / đáy→hồi phục | Error / gap | Verdict |
|---|---|---|---|---|---|---|---|
| PRE_TRANSFER | — | baseline | — | — | — | — | NOT_RUN |
| HANDOFF 12.0 + quan sát phục hồi | — | — | — | — | — | — | NOT_RUN |
| POST scrub 12.0 | — | — | — | — | — | — | NOT_RUN |
| Chuyển PG khác (đo trên 12.0) | — | — | — | — | — | — | NOT_RUN |
| AFTER_TRANSFER | — | — | — | — | — | — | NOT_RUN |
| SOURCE_UPGRADE nếu chạy | — | báo riêng | — | — | — | — | NOT_RUN |

Tách handoff thuần BEGIN→CONVERGED và giai đoạn quan sát phục hồi khi phân tích chi tiết; không gộp POST scrub vào handoff. Báo thêm primary/acting của 12.0 từng phase, mọi tải ngoài, dữ liệu log thiếu, clock skew, thời gian scrub và lượng dữ liệu chuyển nếu có bằng chứng.

Một PG không đại diện toàn cluster hoặc RGW. AFTER_TRANSFER khác PRE_TRANSFER về placement; AFTER nâng còn khác binary/policy primary. Một run chưa chứng minh PA2 tốt hơn rolling upgrade nếu thiếu đối chứng cùng workload/topology. Khi osd.2 rỗng, workload không kiểm dữ liệu trên osd.2 sau nâng: `replica_validation=NOT_EXERCISED`.

Verdict tách: `transfer_operation`, `pre/post_scrub`, `checksum_sentinel`, `service_qos`, `source_upgrade`, `ha`, `tail_spare_validation`. Nhánh TRANSFER_ONLY không được ghi source_upgrade PASS. Nhánh PA2 đầy đủ chỉ hoàn tất khi qua mọi gate mục 12–13. HA để `NOT_TESTED` nếu chưa có bài failover; gate mapping chỉ chứng minh phân tách host của các replica theo snapshot kiểm tra.

## 17 Nguồn đối chiếu

- MOP nguồn: [MOP OSD.docx](MOP%20OSD.docx); [MOP weight-set](../MOP_Spare_CRUSH_Weight_Set.docx).
- Chính sách dự án: [plan tổng](../plan-tổng.md); [protocol benchmark](../benchmark/README.md). Bản 2 → 5 không kế thừa mặc định ngoại lệ cùng-host của lượt nguồn khác; policy rollout vẫn phải được đối chiếu riêng.
- S1: [Ceph v16.2.15 OSDMap check_pg_upmaps](https://github.com/ceph/ceph/blob/v16.2.15/src/osd/OSDMap.cc#L1901-L2024).
- S2: [Ceph v16.2.15 CrushWrapper verify_upmap](https://github.com/ceph/ceph/blob/v16.2.15/src/crush/CrushWrapper.cc#L871-L976).
- S3: [Ceph Pacific CRUSH maps và weight sets](https://docs.ceph.com/en/pacific/rados/operations/crush-map/).
- S4: [Ceph Pacific upgrade](https://docs.ceph.com/en/pacific/cephadm/upgrade/), [service và daemon management](https://docs.ceph.com/en/pacific/cephadm/services/).
- S5: [Ceph Pacific cephadm shell và mount — tham khảo bản cũ](https://docs.ceph.com/en/pacific/man/8/cephadm/#shell).
- B1: [Ceph Pacific rbd](https://docs.ceph.com/en/pacific/man/8/rbd/).
- B2: [fio workload và histogram/log](https://fio.readthedocs.io/en/master/fio_doc.html).

Các cửa sổ, ngưỡng và profile là thiết kế lab; chưa có kết quả đo thật.

- Z1: [Zsh options: INTERACTIVE_COMMENTS, ERR_RETURN, GLOBAL_EXPORT](https://zsh.sourceforge.io/Doc/Release/Options.html).
- Z2: [Ceph Pacific: native CLI / ceph-common](https://docs.ceph.com/en/pacific/cephadm/install/#enable-ceph-cli).
