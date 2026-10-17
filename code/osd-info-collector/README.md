# Ceph OSD Info Collector

Tool độc lập, chỉ đọc, dùng để lưu baseline của một hoặc nhiều OSD trước, trong
và sau nâng cấp. Storage Lab Console gọi tool qua action schema đóng, lưu nguyên
artifact và index các trường quy hoạch; tool vẫn có thể chạy độc lập ngoài
Console.

## Dữ liệu thu thập

Mỗi OSD có phần tóm tắt:

- cluster FSID, OSD ID/FSID, version/image, host và CRUSH location;
- public/cluster IP;
- đường dẫn data/DB/WAL và physical device như `/dev/sdb`, UUID/serial nếu Ceph
  metadata cung cấp;
- dung lượng OSD, used/free và phần trăm sử dụng;
- trạng thái up/in, weight/reweight/primary-affinity;
- tổng PG và số PG mà OSD đang làm primary;
- effective config của OSD và raw output của các lệnh dùng làm evidence.

Phần `cluster_evidence` lưu một lần các snapshot chung: status, health detail,
PG stat, pool detail, versions, OSD tree/dump/df và config database. Phần
`osds[].evidence` lưu metadata/find/PG/config/device riêng của từng OSD.

`devices.mapping_source=ceph_osd_metadata` nói rõ đường `/dev/*` được lấy từ
metadata daemon. Trên BlueStore dùng LVM, path có thể là LV hoặc `/dev/dm-*`;
`physical_devices` giữ tên ổ nền nếu metadata có `*_devices`. Tool không đoán
ổ vật lý khi Ceph không cung cấp và sẽ ghi warning
`DEVICE_PATH_NOT_REPORTED_BY_CEPH_METADATA`.

## Chạy

Yêu cầu Python 3.6+ và Ceph CLI đã được cấu hình quyền đọc cluster. Collector
1.0.2 tương thích cả Python 3.6 và 3.7 trong các môi trường cũ, không cần nâng
Python của image chỉ để chạy tool.

```bash
python3 collect_osd.py --version
python3 collect_osd.py --osd 0
python3 collect_osd.py --osd 0 --osd 4 --output evidence/before.json
python3 collect_osd.py --all --output evidence/all-osds.json
```

Với cluster được quản lý bằng cephadm, chạy tool trong `cephadm shell` để shell
tự nhận config và keyring của cluster:

```bash
# Kiểm tra Python và file đã chép vào /home/dangg/code.
sudo cephadm shell -- python3 --version
sudo cephadm shell --mount /home/dangg/code -- \
  python3 /mnt/code/collect_osd.py --version

# Xác nhận Ceph CLI xác thực được trước khi collect.
sudo cephadm shell -- ceph fsid

mkdir -p /home/dangg/code/evidence
sudo cephadm shell --mount /home/dangg/code -- \
  python3 /mnt/code/collect_osd.py \
    --osd 0 \
    --output /mnt/code/evidence/osd-0-before.json
```

Lệnh `--version` cần hiển thị `collect_osd.py 1.0.2`. Nếu vẫn gặp lỗi cú pháp
ở toán tử `:=`, bạn đang chạy bản cũ và cần chép lại file. Thư mục
`/mnt/code/evidence` trong shell tương ứng `/home/dangg/code/evidence` trên host.

File JSON hợp lệ chưa có nghĩa là đã thu đủ baseline. Kiểm tra `quality`,
`errors` ở cấp collection và `quality`, `warnings`, `errors` của từng OSD;
`PARTIAL` hoặc `INCONCLUSIVE` cần được xem lỗi chi tiết trước khi dùng làm
baseline cho plan nâng cấp.

Nếu user hiện tại không dùng config/keyring mặc định:

```bash
python3 collect_osd.py --osd 0 \
  --conf /etc/ceph/ceph.conf \
  --name client.admin \
  --keyring /etc/ceph/ceph.client.admin.keyring \
  --output evidence/osd-0-before.json
```

Nên thu ba artifact riêng cho mỗi đợt:

```text
before.json
during.json
after-stable.json
```

Nếu OSD đang down, `config show-with-defaults osd.N` có thể không trả được
effective config. Tool vẫn giữ lỗi trong evidence và đánh dấu `PARTIAL`; không
chuyển dữ liệu thiếu thành 0.

## Lệnh Ceph được dùng

Các lệnh dùng argv, không qua shell:

```text
ceph fsid
ceph status --format=json
ceph health detail --format=json
ceph pg stat --format=json
ceph osd pool ls detail --format=json
ceph versions --format=json
ceph osd tree --format=json
ceph osd dump --format=json
ceph osd df tree --format=json
ceph config dump --format=json
ceph osd metadata N --format=json
ceph osd find N --format=json
ceph pg ls-by-osd osd.N --format=json
ceph pg ls-by-primary osd.N --format=json
ceph config show-with-defaults osd.N --format=json
ceph device ls-by-daemon osd.N --format=json
```

Lệnh device inventory và effective config được giữ theo best effort để tương
thích nhiều phiên bản. Bốn lệnh identity/placement riêng của OSD là bắt buộc;
lỗi của chúng khiến lần thu thập OSD đó không được coi là baseline đầy đủ.

## Contract tích hợp Console

Console nên lưu nguyên artifact bất biến và index các trường sau để dựng plan:

```text
collection_id, collected_at, cluster_fsid
osd_id, osd_fsid, hostname, crush_location, device_class
public_ip/public_ips, cluster_ip/cluster_ips
devices.data/db/wal.path, physical_devices, size_bytes, device_ids
capacity.total_bytes, capacity.used_bytes, capacity.used_percent
placement_groups.count, placement_groups.primary_count
state.up, state.in, state.crush_weight, state.reweight
version.ceph_version, version.container_image/container_image_id
quality, warnings
```

Plan tham chiếu artifact bằng ID/hash thay vì copy một vài giá trị vào form.
Trước từng down-set phải collect lại vì PG count, primary role, usage và trạng
thái up/in có thể đổi sau khi plan được tạo.

## Test

```bash
python3 -B -m unittest discover -s tests -v
```

Bản 1.0.2 đã chạy 12 test trên Python 3.6.8 và 3.10.9 trên Windows. Các test
kiểm tra khởi động CLI, subprocess thật (JSON/text/stderr/timeout), ghi JSON và
bảo toàn file cũ khi ghi thất bại; dữ liệu Ceph dùng fixture, chưa thay thế
việc chạy thử trên cluster và image thực tế.
