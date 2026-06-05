# BTVN: Mô phỏng Virtual Router bằng Linux Network Namespace

---

## 1. Tên bài tập

**Mô phỏng hệ thống mạng ảo gồm 2 VM và 1 Virtual Router bằng Linux Network Namespace**

Mục tiêu chính của bài:

- Tạo 2 namespace đại diện cho 2 VM: `ns-a`, `ns-b`.
- Tạo 1 namespace đóng vai trò Virtual Router: `ns-router`.
- Kết nối các namespace bằng `veth pair`.
- Cấu hình định tuyến để kiểm tra:
  - **East-West traffic**: `ns-a` ping được `ns-b`.
  - **North-South traffic**: `ns-a` đi được ra Internet thông qua NAT.

---

## 2. Mô hình triển khai

```text
ns-a                    ns-router                    ns-b
10.0.1.2/24  <---->  10.0.1.1/24
                         |
                         | 10.0.2.1/24
                         |
                    10.0.2.2/24

ns-router               Host                  Internet
10.99.99.2/24  <---->  10.99.99.1/24  <----> eth0
```

Luồng East-West:

```text
ns-a → ns-router → ns-b
```

Luồng North-South:

```text
ns-a → ns-router → Host → Internet
```

---

## 3. Các bước thực hiện

### Bước 1: Tạo Network Namespace

Tạo 3 namespace:

```bash
sudo ip netns add ns-a
sudo ip netns add ns-b
sudo ip netns add ns-router
```

Kiểm tra:

```bash
sudo ip netns list
```

---

### Bước 2: Tạo veth pair để kết nối các namespace

Tạo các cặp dây mạng ảo:

```bash
sudo ip link add veth-a type veth peer name veth-router-a
sudo ip link add veth-b type veth peer name veth-router-b
sudo ip link add veth-router-ext type veth peer name veth-host
```

Gắn các interface vào namespace tương ứng:

```bash
sudo ip link set veth-a netns ns-a
sudo ip link set veth-router-a netns ns-router

sudo ip link set veth-b netns ns-b
sudo ip link set veth-router-b netns ns-router

sudo ip link set veth-router-ext netns ns-router
```

`veth-host` giữ lại trên Host để làm cổng trung chuyển ra ngoài.

---

### Bước 3: Cấu hình IP và default route

#### Cấu hình `ns-a`

```bash
sudo ip netns exec ns-a ip addr add 10.0.1.2/24 dev veth-a
sudo ip netns exec ns-a ip link set veth-a up
sudo ip netns exec ns-a ip link set lo up
sudo ip netns exec ns-a ip route add default via 10.0.1.1
```

#### Cấu hình `ns-b`

```bash
sudo ip netns exec ns-b ip addr add 10.0.2.2/24 dev veth-b
sudo ip netns exec ns-b ip link set veth-b up
sudo ip netns exec ns-b ip link set lo up
sudo ip netns exec ns-b ip route add default via 10.0.2.1
```

#### Cấu hình `ns-router`

```bash
sudo ip netns exec ns-router ip addr add 10.0.1.1/24 dev veth-router-a
sudo ip netns exec ns-router ip link set veth-router-a up

sudo ip netns exec ns-router ip addr add 10.0.2.1/24 dev veth-router-b
sudo ip netns exec ns-router ip link set veth-router-b up

sudo ip netns exec ns-router ip addr add 10.99.99.2/24 dev veth-router-ext
sudo ip netns exec ns-router ip link set veth-router-ext up

sudo ip netns exec ns-router ip link set lo up
sudo ip netns exec ns-router ip route add default via 10.99.99.1
```

#### Cấu hình Host

```bash
sudo ip addr add 10.99.99.1/24 dev veth-host
sudo ip link set veth-host up
```

---

### Bước 4: Bật IP Forwarding

Bật chuyển tiếp gói tin trên `ns-router`:

```bash
sudo ip netns exec ns-router sysctl -w net.ipv4.ip_forward=1
```

Bật chuyển tiếp gói tin trên Host:

```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

Kiểm tra:

```bash
sysctl net.ipv4.ip_forward
```

Kết quả mong muốn:

```text
net.ipv4.ip_forward = 1
```

---

### Bước 5: Mở firewall cho traffic forward

Cho phép Host nhận và forward traffic từ `veth-host`:

```bash
sudo iptables -I INPUT -i veth-host -j ACCEPT
sudo iptables -I FORWARD -i veth-host -j ACCEPT
```

Cho phép `ns-router` forward gói tin:

```bash
sudo ip netns exec ns-router iptables -I FORWARD -j ACCEPT
```

---

### Bước 6: Cấu hình NAT

NAT lớp 1 trên `ns-router`:

```bash
sudo ip netns exec ns-router iptables -t nat -A POSTROUTING -o veth-router-ext -j MASQUERADE
```

NAT lớp 2 trên Host:

```bash
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
```

> Nếu interface ra Internet của Host không phải `eth0`, kiểm tra bằng:
>
> ```bash
> ip route
> ```
>
> Sau đó thay `eth0` bằng interface thực tế, ví dụ `ens33`, `enp0s3`, `wlp...`

---

## 4. Kiểm tra kết quả

### 4.1. Kiểm tra East-West traffic

Từ `ns-a` ping sang `ns-b`:

```bash
sudo ip netns exec ns-a ping -c 4 10.0.2.2
```

Kết quả mong muốn:

```text
0% packet loss
```

---

### 4.2. Kiểm tra North-South traffic

Từ `ns-a` ping ra Internet:

```bash
sudo ip netns exec ns-a ping -c 4 8.8.8.8
```

Kết quả mong muốn:

```text
0% packet loss
```

---

### 4.3. Kiểm tra đường đi gói tin

Dùng `traceroute` để xem packet đi qua router ảo:

```bash
sudo ip netns exec ns-a traceroute 8.8.8.8
```

Kết quả mong muốn: hop đầu tiên là `10.0.1.1`, tức `ns-router`.

---

## 5. Lưu ý khi triển khai

### Lưu ý 1: Cần dùng quyền `sudo`

Các thao tác như tạo namespace, tạo veth, gán IP, bật interface, sửa route, bật NAT đều cần quyền quản trị.

Nếu gặp lỗi:

```text
Operation not permitted
```

thì cần kiểm tra lại lệnh đã chạy với `sudo` chưa.

---

### Lưu ý 2: Cần bật IP Forwarding

Nếu chưa bật IP Forwarding, Linux chỉ nhận gói tin cho chính nó, không chuyển tiếp gói tin sang interface khác.

Cần bật ở cả:

- `ns-router`
- Host

---

### Lưu ý 3: Firewall/UFW có thể chặn traffic forward

Nếu East-West traffic hoạt động nhưng North-South traffic không hoạt động, nguyên nhân thường là Host không cho phép forward packet.

Có thể kiểm tra và xử lý bằng:

```bash
sudo iptables -L FORWARD -n -v
sudo iptables -I FORWARD -i veth-host -j ACCEPT
```

---

### Lưu ý 4: Dải mạng trung chuyển không được trùng với mạng có sẵn trên Host

Ban đầu có thể dùng nhầm dải:

```text
192.168.100.0/24
```

Tuy nhiên dải này có thể bị trùng với mạng ảo của KVM/libvirt như `virbr1`.

Cách xử lý: đổi sang dải khác, ví dụ:

```text
10.99.99.0/24
```

Trong bài này sử dụng:

| Interface | IP |
|---|---|
| `veth-router-ext` | `10.99.99.2/24` |
| `veth-host` | `10.99.99.1/24` |

---

### Lưu ý 5: NAT trên Host phải dùng đúng interface ra Internet

Lệnh NAT trên Host phụ thuộc vào interface thật đang đi ra Internet.

Ví dụ:

```bash
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
```

Nếu máy không dùng `eth0`, cần thay bằng interface đúng sau khi kiểm tra bằng:

```bash
ip route
```

---

## 6. Kết quả cuối cùng

Sau khi hoàn thành bài lab:

- `ns-a` ping được `ns-b` qua `ns-router`.
- `ns-a` đi được ra Internet qua Host.
- Mô hình thể hiện được:
  - Network Namespace.
  - veth pair.
  - Linux routing.
  - IP Forwarding.
  - NAT bằng iptables.
  - East-West và North-South traffic trong môi trường mạng ảo.

