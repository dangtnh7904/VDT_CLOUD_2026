Được. Dưới đây là runbook chi tiết cho đúng Giai đoạn 1 và 2 trên Ceph Pacific 16.2.5 hiện tại, chưa nâng cấp và không tác động pool RBD đang có.

Mình chọn mô hình single-site, dùng `default` zone/zonegroup và tạo service `rgw.lab`. RGW chạy cổng `8080`; HAProxy/Keepalived cung cấp VIP cổng `7480`.

Topology đã được xác nhận trên cả ba node:

```text
Public/client network:  10.20.20.0/24 qua eth0
Cluster/OSD network:    10.20.30.0/24 qua eth2
RGW VIP:                10.20.20.100/24 qua eth0
S3 endpoint:            http://10.20.20.100:7480
```

## Thông số sẽ dùng

| Thành phần    | Giá trị                          |
| --------------- | ---------------------------------- |
| RGW service     | `rgw.lab`                        |
| Ingress service | `ingress.rgw.lab`                |
| RGW backend     | `8080/tcp`                       |
| Endpoint S3     | `http://10.20.20.100:7480`       |
| HAProxy monitor | `1967/tcp`                       |
| Placement       | `lab-placement`                  |
| Zone/zonegroup  | `default/default`                |
| Replication     | `size=3`, `min_size=2`         |
| PG ban đầu    | `8` mỗi pool, autoscaler `on` |

Với 77 GiB raw còn trống và replication 3, dung lượng logical tối đa lý thuyết chỉ khoảng 25 GiB, thực tế thấp hơn vì ngưỡng `nearfull/backfillfull/full` và RBD cùng dùng OSD.

Các lệnh `ceph` dưới đây chạy trong `cephadm shell` — tức prompt `ceph-master%` hiện tại của bạn.

# Giai đoạn 1 — Triển khai 3 RGW và Ingress VIP

## 1.1. Kiểm tra bắt buộc trước khi triển khai

```bash
ceph -s
ceph health detail
ceph version
ceph versions

ceph orch status
ceph orch host ls

for HOST in ceph-master ceph-node2 ceph-node3; do
    ceph cephadm check-host "$HOST"
done

ceph osd tree
ceph osd df tree
ceph df detail

ceph osd crush rule ls
ceph osd crush rule dump replicated_rule

ceph osd pool ls detail
ceph osd pool autoscale-status
```

Chỉ tiếp tục khi:

* `HEALTH_OK`.
* Có đúng ba host trong `ceph orch host ls`.
* Ba lệnh `check-host` thành công.
* Ba OSD đều `up` và `in`.
* CRUSH rule dự kiến có failure domain là `host`.
* Không có PG degraded/recovering/backfilling.
* Tất cả daemon Ceph đang dùng đúng phiên bản mong muốn.

Nếu rule không tên `replicated_rule`, dùng tên rule replicated thực tế ở các bước sau.

## 1.2. Chọn VIP và kiểm tra cổng

Trên hệ điều hành host, không phải bên trong container:

```bash
ip -br -4 address
ip route
sudo ss -lntp | grep -E ':(7480|8080|1967)\b'
timedatectl show -p NTPSynchronized
```

Ba node hiện có địa chỉ public/client:

```text
ceph-master  10.20.20.11/24
ceph-node2   10.20.20.12/24
ceph-node3   10.20.20.13/24
```

Cấu hình được chọn:

```text
PUBLIC_CIDR=10.20.20.0/24
VIP_CIDR=10.20.20.100/24
```

Kiểm tra VIP chưa được sử dụng:

```bash
ping -c 3 10.20.20.100 || true
sudo arping -D -I eth0 -c 5 10.20.20.100
echo "arping_exit=$?"
```

VIP phải được loại khỏi DHCP và nằm cùng Layer 2 với ba node.

Firewall cần cho phép:

* Client → VIP: `TCP/7480`.
* Các node ingress → RGW: `TCP/8080`.
* Giữa các node ingress: VRRP/IP protocol 112.
* `TCP/1967` chỉ mở cho mạng quản trị nếu cần xem HAProxy stats.

## 1.3. Tạo RGW service spec

Trong `cephadm shell`, khai báo mạng thật của bạn:

```bash
PUBLIC_CIDR="10.20.20.0/24"
: "${PUBLIC_CIDR:?PUBLIC_CIDR chưa được đặt}"
```

Tạo spec:

```bash
cat >/tmp/rgw-lab.yaml <<EOF
service_type: rgw
service_id: lab
placement:
  label: rgw
  count_per_host: 1
networks:
  - ${PUBLIC_CIDR}
spec:
  rgw_frontend_type: beast
  rgw_frontend_port: 8080
EOF
```

Kiểm tra lại trước khi apply:

```bash
cat /tmp/rgw-lab.yaml
```

Apply:

```bash
sudo /usr/local/sbin/cephadm shell \
  --mount /tmp/rgw-lab.yaml \
  -- ceph orch apply -i /mnt/rgw-lab.yaml
```

Cephadm hỗ trợ triển khai nhiều RGW bằng placement và cấu hình frontend port qua service spec. [Ceph Pacific RGW service](https://docs.ceph.com/en/pacific/cephadm/services/rgw/)

Theo dõi:

```bash
ceph orch ls --service-name rgw.lab
ceph orch ps --service-name rgw.lab --refresh
```

Kết quả cần có ba RGW ở trạng thái `running`, mỗi host một daemon.

Nếu có lỗi:

```bash
ceph health detail
ceph log last cephadm
ceph orch ps --service-name rgw.lab --refresh --format json-pretty
```

## 1.4. Kiểm tra trực tiếp từng RGW

Lấy địa chỉ từng host:

```bash
ceph orch host ls
```

Từ một máy truy cập được các node:

```bash
curl -i http://10.20.20.11:8080/
curl -i http://10.20.20.12:8080/
curl -i http://10.20.20.13:8080/
```

Kết quả `HTTP 403` kèm XML `AccessDenied` là bình thường: HTTP frontend đã chạy nhưng request chưa được ký bằng access key.

Nếu connection refused:

```bash
ceph orch ps --service-name rgw.lab --refresh
```

Sau đó kiểm tra listener/firewall trên host tương ứng.

## 1.5. Triển khai HAProxy + Keepalived

Khai báo VIP:

```bash
VIP_CIDR="10.20.20.100/24"
: "${VIP_CIDR:?VIP_CIDR chưa được đặt}"
```

Tạo ingress spec:

```bash
cat >/tmp/ingress-rgw-lab.yaml <<EOF
service_type: ingress
service_id: rgw.lab
placement:
  hosts:
    - ceph-master
    - ceph-node2
    - ceph-node3
spec:
  backend_service: rgw.lab
  virtual_ip: ${VIP_CIDR}
  frontend_port: 7480
  monitor_port: 1967
  virtual_interface_networks:
    - ${PUBLIC_CIDR}
EOF
```

Kiểm tra:

```bash
cat /tmp/ingress-rgw-lab.yaml
```

Apply:

```bash
ceph orch apply -i /tmp/ingress-rgw-lab.yaml
```

Ingress của Cephadm triển khai HAProxy và Keepalived; VIP chỉ active trên một ingress node, còn HAProxy phân phối request tới các RGW backend. [Ceph Pacific RGW ingress specification](https://docs.ceph.com/en/pacific/cephadm/services/rgw/#high-availability-service-for-rgw)

Theo dõi:

```bash
ceph orch ls --service-name ingress.rgw.lab
ceph orch ps --daemon-type haproxy --refresh
ceph orch ps --daemon-type keepalived --refresh
```

Mong đợi:

* 3 HAProxy `running`.
* 3 Keepalived `running`.
* Một node đang giữ VIP.

Kiểm tra VIP trên ba host:

```bash
ip -br -4 address | grep 10.20.20.100
```

Kiểm tra endpoint:

```bash
curl -i http://10.20.20.100:7480/
```

Tiếp tục mong đợi `403 AccessDenied`, không phải connection refused hoặc timeout.

Chốt Giai đoạn 1:

```bash
ceph -s
ceph orch ps --service-name rgw.lab --refresh
ceph orch ps --daemon-type haproxy --refresh
ceph orch ps --daemon-type keepalived --refresh
```

# Giai đoạn 2 — Pool, placement, user và bucket

## 2.1. Xác nhận realm/zone hiện tại

```bash
radosgw-admin realm list
radosgw-admin zonegroup list
radosgw-admin zone list

radosgw-admin zonegroup get --rgw-zonegroup=default
radosgw-admin zone get --rgw-zone=default
```

Runbook phía dưới giả định kết quả là:

```text
zonegroup: default
zone:      default
realm:     không có realm explicit
```

Nếu zone/zonegroup không phải `default`, dừng lại và thay bằng tên thực tế. Không tự tạo thêm realm/zone vì có thể vô tình chuyển cluster sang cấu hình multisite khác.

Đặt biến:

```bash
ZONEGROUP="default"
ZONE="default"
PLACEMENT="lab-placement"
CRUSH_RULE="replicated_rule"
```

Kiểm tra lại CRUSH rule:

```bash
ceph osd crush rule dump "$CRUSH_RULE"
```

Phải thấy failure domain theo `host`. Với ba OSD, tốt nhất mỗi host có một OSD.

## 2.2. Tạo ba pool custom

```bash
for POOL in \
    default.rgw.lab.data \
    default.rgw.lab.index \
    default.rgw.lab.data-extra
do
    if ! ceph osd pool ls | grep -Fxq "$POOL"; then
        ceph osd pool create "$POOL" 8 8 replicated "$CRUSH_RULE"
    fi

    ceph osd pool set "$POOL" size 3
    ceph osd pool set "$POOL" min_size 2
    ceph osd pool set "$POOL" pg_autoscale_mode on
    ceph osd pool application enable "$POOL" rgw
done
```

Pool tạo thủ công phải được gắn application `rgw`; autoscaler có thể tự điều chỉnh PG theo mức sử dụng. [Ceph Pacific pool management](https://docs.ceph.com/en/pacific/rados/operations/pools/), [PG autoscaler](https://docs.ceph.com/en/pacific/rados/operations/placement-groups/#autoscaling-placement-groups)

Không bật `bulk` lúc này. Cluster chỉ có ba OSD và còn chạy RBD; để autoscaler quan sát tải trước sẽ an toàn hơn.

Kiểm tra:

```bash
for POOL in \
    default.rgw.lab.data \
    default.rgw.lab.index \
    default.rgw.lab.data-extra
do
    echo "===== $POOL ====="
    ceph osd pool get "$POOL" size
    ceph osd pool get "$POOL" min_size
    ceph osd pool get "$POOL" pg_num
    ceph osd pool get "$POOL" pg_autoscale_mode
    ceph osd pool get "$POOL" crush_rule
    ceph osd pool application get "$POOL"
done

ceph osd pool autoscale-status
ceph -s
```

Chờ tất cả PG về `active+clean` trước khi đi tiếp.

## 2.3. Tạo placement target

Xem placement hiện tại:

```bash
radosgw-admin zonegroup placement list \
    --rgw-zonegroup="$ZONEGROUP"

radosgw-admin zone placement list \
    --rgw-zone="$ZONE"
```

Nếu chưa có `lab-placement`, chạy:

```bash
radosgw-admin zonegroup placement add \
    --rgw-zonegroup="$ZONEGROUP" \
    --placement-id="$PLACEMENT"
```

Ánh xạ placement vào ba pool:

```bash
radosgw-admin zone placement add \
    --rgw-zone="$ZONE" \
    --placement-id="$PLACEMENT" \
    --data-pool=default.rgw.lab.data \
    --index-pool=default.rgw.lab.index \
    --data-extra-pool=default.rgw.lab.data-extra
```

Nếu lệnh báo placement đã tồn tại do từng chạy trước đó, dùng:

```bash
radosgw-admin zone placement modify \
    --rgw-zone="$ZONE" \
    --placement-id="$PLACEMENT" \
    --data-pool=default.rgw.lab.data \
    --index-pool=default.rgw.lab.index \
    --data-extra-pool=default.rgw.lab.data-extra
```

Placement phải được cấu hình trước khi tạo bucket vì placement của bucket được chọn lúc bucket được tạo và không thể đổi trực tiếp sau đó. [Ceph Pacific pool placement](https://docs.ceph.com/en/pacific/radosgw/placement/)

Kiểm tra mapping:

```bash
radosgw-admin zonegroup get \
    --rgw-zonegroup="$ZONEGROUP" |
jq '.placement_targets, .default_placement'

radosgw-admin zone get \
    --rgw-zone="$ZONE" |
jq '.placement_pools'
```

## 2.4. Kích hoạt thay đổi placement

Với single-site implicit default zone:

```bash
ceph orch restart rgw.lab
```

Theo dõi:

```bash
ceph orch ps --service-name rgw.lab --refresh
ceph -s
```

Nếu `radosgw-admin realm list` cho thấy có realm explicit/multisite, phải commit period trước:

```bash
radosgw-admin period update \
    --rgw-realm=<TEN_REALM> \
    --commit

ceph orch restart rgw.lab
```

Tài liệu Pacific phân biệt rõ: default single-site cần restart RGW; multisite cần commit period. [Ceph placement activation](https://docs.ceph.com/en/pacific/radosgw/placement/#zonegroup-zone-configuration)

## 2.5. Tạo hai RGW user

Không đặt access key cố định trong command hoặc Git. Cho RGW sinh key ngẫu nhiên:

```bash
umask 077
```

App user:

```bash
if ! radosgw-admin user info --uid=rgw-app >/tmp/rgw-app.json 2>/dev/null; then
    radosgw-admin user create \
        --uid=rgw-app \
        --display-name="RGW Lab Application" \
        --max-buckets=10 \
        --gen-access-key \
        --gen-secret \
        --format=json >/tmp/rgw-app.json
fi

radosgw-admin user modify \
    --uid=rgw-app \
    --placement-id=lab-placement \
    --format=json >/tmp/rgw-app.json
```

Warp user:

```bash
if ! radosgw-admin user info --uid=rgw-warp >/tmp/rgw-warp.json 2>/dev/null; then
    radosgw-admin user create \
        --uid=rgw-warp \
        --display-name="RGW Warp Benchmark" \
        --max-buckets=10 \
        --gen-access-key \
        --gen-secret \
        --format=json >/tmp/rgw-warp.json
fi

radosgw-admin user modify \
    --uid=rgw-warp \
    --placement-id=lab-placement \
    --format=json >/tmp/rgw-warp.json
```

Kiểm tra mà không in secret key:

```bash
radosgw-admin user info --uid=rgw-app |
jq '{user_id, display_name, default_placement, max_buckets}'

radosgw-admin user info --uid=rgw-warp |
jq '{user_id, display_name, default_placement, max_buckets}'
```

Cả hai phải có:

```json
"default_placement": "lab-placement"
```

`radosgw-admin` hỗ trợ tạo user, sinh access/secret key và cấu hình placement cho user. [Pacific radosgw-admin reference](https://docs.ceph.com/en/pacific/man/8/radosgw-admin/)

## 2.6. Tạo bucket qua S3 API

Bucket phải tạo bằng S3 client, không dùng `radosgw-admin`; công cụ admin chỉ quản lý/link/check bucket đã tồn tại.

Chạy phần này trên host/client có AWS CLI và truy cập được VIP:

```bash
RGW_ENDPOINT="http://10.20.20.100:7480"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_EC2_METADATA_DISABLED="true"
```

Ép path-style cho endpoint IP:

```bash
export AWS_CONFIG_FILE="/tmp/rgw-aws-config"

cat >"$AWS_CONFIG_FILE" <<'EOF'
[default]
region = us-east-1
s3 =
    addressing_style = path
EOF
```

Lấy key của app user từ Ceph:

```bash
APP_ACCESS_KEY=$(
    sudo cephadm shell -- \
    radosgw-admin user info --uid=rgw-app |
    jq -r '.keys[0].access_key'
)

APP_SECRET_KEY=$(
    sudo cephadm shell -- \
    radosgw-admin user info --uid=rgw-app |
    jq -r '.keys[0].secret_key'
)
```

Tạo bucket ứng dụng:

```bash
AWS_ACCESS_KEY_ID="$APP_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$APP_SECRET_KEY" \
aws --no-cli-pager \
    --endpoint-url="$RGW_ENDPOINT" \
    s3api create-bucket \
    --bucket rgw-lab-data
```

Lấy key Warp:

```bash
WARP_ACCESS_KEY=$(
    sudo cephadm shell -- \
    radosgw-admin user info --uid=rgw-warp |
    jq -r '.keys[0].access_key'
)

WARP_SECRET_KEY=$(
    sudo cephadm shell -- \
    radosgw-admin user info --uid=rgw-warp |
    jq -r '.keys[0].secret_key'
)
```

Tạo bucket benchmark:

```bash
AWS_ACCESS_KEY_ID="$WARP_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$WARP_SECRET_KEY" \
aws --no-cli-pager \
    --endpoint-url="$RGW_ENDPOINT" \
    s3api create-bucket \
    --bucket rgw-warp-bench
```

Không truyền `LocationConstraint`: `default_placement` của từng user đã được đặt thành `lab-placement`.

## 2.7. Kiểm tra bucket và placement thật

Trong `cephadm shell`:

```bash
radosgw-admin bucket stats --bucket=rgw-lab-data |
jq '{bucket, owner, placement_rule, num_shards}'

radosgw-admin bucket stats --bucket=rgw-warp-bench |
jq '{bucket, owner, placement_rule, num_shards}'
```

Mong đợi:

```text
rgw-lab-data   owner=rgw-app    placement_rule=lab-placement
rgw-warp-bench owner=rgw-warp   placement_rule=lab-placement
```

Nếu `placement_rule` là `default-placement`, hãy xoá bucket khi còn rỗng, sửa placement của user rồi tạo lại. Không benchmark khi placement chưa đúng.

## 2.8. Smoke test PUT/GET qua VIP

```bash
printf 'Ceph RGW smoke test\n' >/tmp/rgw-smoke.txt
sha256sum /tmp/rgw-smoke.txt
```

PUT:

```bash
AWS_ACCESS_KEY_ID="$APP_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$APP_SECRET_KEY" \
aws --no-cli-pager \
    --endpoint-url="$RGW_ENDPOINT" \
    s3api put-object \
    --bucket rgw-lab-data \
    --key smoke/rgw-smoke.txt \
    --body /tmp/rgw-smoke.txt \
    --content-type text/plain
```

HEAD:

```bash
AWS_ACCESS_KEY_ID="$APP_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$APP_SECRET_KEY" \
aws --no-cli-pager \
    --endpoint-url="$RGW_ENDPOINT" \
    s3api head-object \
    --bucket rgw-lab-data \
    --key smoke/rgw-smoke.txt
```

GET và so sánh:

```bash
AWS_ACCESS_KEY_ID="$APP_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$APP_SECRET_KEY" \
aws --no-cli-pager \
    --endpoint-url="$RGW_ENDPOINT" \
    s3api get-object \
    --bucket rgw-lab-data \
    --key smoke/rgw-smoke.txt \
    /tmp/rgw-smoke.downloaded

cmp /tmp/rgw-smoke.txt /tmp/rgw-smoke.downloaded
sha256sum /tmp/rgw-smoke.txt /tmp/rgw-smoke.downloaded
```

`cmp` không in gì và hai SHA-256 giống nhau là đạt.

Xoá biến secret khỏi shell:

```bash
unset APP_ACCESS_KEY APP_SECRET_KEY
unset WARP_ACCESS_KEY WARP_SECRET_KEY
```

## Tiêu chí hoàn tất Giai đoạn 1–2

```bash
ceph -s
ceph orch ps --service-name rgw.lab --refresh
ceph orch ps --daemon-type haproxy --refresh
ceph orch ps --daemon-type keepalived --refresh
ceph osd pool autoscale-status
ceph df detail
```

Bạn chỉ chuyển sang benchmark khi:

* `HEALTH_OK`.
* 3 RGW, 3 HAProxy và 3 Keepalived đều `running`.
* VIP `:7480` hoạt động.
* PUT/HEAD/GET qua VIP thành công.
* Hai bucket đều có `placement_rule=lab-placement`.
* Ba custom pool đều `size=3`, `min_size=2`, app `rgw`.
* PG đều `active+clean`.
* Pool RBD cũ không bị thay đổi.
