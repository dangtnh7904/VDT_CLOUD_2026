# BÁO CÁO THỰC HÀNH: KVM NESTED VIRTUALIZATION & SDN

---

# PHẦN 1: CHUẨN BỊ & BÀI BASIC

## Tạo máy ảo và mạng NAT

---

## 1. Chuẩn bị Host qua Hyper-V Manager

### 1.1. Bật tính năng Hyper-V trên Windows 11 Home

Sử dụng script `.bat` sau để kích hoạt Hyper-V.
Chạy file với quyền **Administrator**.

```bat
pushd "%~dp0"
dir /b %SystemRoot%\servicing\Packages\*Hyper-V*.mum >hyper-v.txt
for /f %%i in ('findstr /i . hyper-v.txt 2^>nul') do dism /online /norestart /add-package:"%SystemRoot%\servicing\Packages\%%i"
del hyper-v.txt
Dism /online /enable-feature /featurename:Microsoft-Hyper-V -All /LimitAccess /ALL
```

---

### 1.2. Cấu hình mạng mặc định trên Hyper-V

Sử dụng **Default Switch** có cấu hình giống NAT:

* Chia sẻ Internet từ máy tính thật.
* Cấp IP tự động qua DHCP.
* Giúp các Host Ubuntu có thể truy cập Internet.

---

### 1.3. Cấp quyền Nested Virtualization cho máy ảo Ubuntu

Mở PowerShell với quyền **Administrator**, lấy danh sách máy ảo bằng lệnh:

```powershell
Get-VM
```

Sau đó bật Nested Virtualization cho máy ảo Ubuntu:

```powershell
Set-VMProcessor -VMName "Tên_Máy_Ảo_Của_Bạn" -ExposeVirtualizationExtensions $true
```

---

## 2. Thiết lập môi trường trên Ubuntu Host 1 và Host 2

### 2.1. Kiểm tra hỗ trợ VT-x bên trong Host

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo
```

Nếu kết quả lớn hơn `0` thì Nested Virtualization đã được kích hoạt thành công.

---

### 2.2. Cài đặt các thư viện cần thiết cho KVM và OVS

```bash
sudo add-apt-repository universe
sudo apt install -y qemu-system-x86 libvirt-daemon-system libvirt-clients bridge-utils virt-manager openvswitch-switch nfs-kernel-server rpcbind
```

---

### 2.3. Tạo mạng Underlay LAN-OVS và clone Host

Trên Hyper-V, tạo một **Virtual Switch** mới loại **Internal** và đặt tên là:

```text
LAN-OVS
```

Mạng `LAN-OVS` đóng vai trò là **Underlay Network**, tức đường mạng nền bên dưới để luân chuyển lưu lượng Overlay của Open vSwitch sau này.

Sau đó tiến hành:

* Clone Host 1 bằng cách nhân bản file `.vhdx`.
* Mount file `.vhdx` đó vào Host 2.
* Gắn card mạng `LAN-OVS` cho cả Host 1 và Host 2.

---

### 2.4. Đổi hostname cho Host 2

Trên Host 2, chạy:

```bash
sudo hostnamectl set-hostname host2
```

---

### 2.5. Bật dịch vụ ảo hóa libvirt

Thực hiện trên cả hai Host:

```bash
sudo systemctl enable --now libvirtd
```

---

## 3. Khởi tạo máy ảo CirrOS cho bài Basic

### 3.1. Tạo mạng Basic NAT

Trong `virt-manager`, tạo một Virtual Network mới:

```text
basic-network
```

Kiểm tra danh sách mạng bằng lệnh:

```bash
sudo virsh net-list --all
```

Kiểm tra card mạng ảo bridge:

```bash
ip a
```

---

### 3.2. Tải image CirrOS

```bash
wget http://download.cirros-cloud.net/0.5.2/cirros-0.5.2-x86_64-disk.img -O ~/Downloads/cirros.img
```

---

### 3.3. Tạo máy ảo trên virt-manager

Cấu hình máy ảo:

| Thành phần | Cấu hình        |
| ---------- | --------------- |
| OS type    | Generic Linux   |
| RAM        | 56 MB           |
| CPU        | 1 Core          |
| Disk       | `cirros.img`    |
| Network    | `basic-network` |

Thông tin đăng nhập CirrOS:

```text
Username: cirros
Password: gocubsgo
```

---

### 3.4. Kiểm tra kết nối Internet

Trong máy ảo CirrOS, chạy:

```bash
ping 8.8.8.8 -c 4
```

Nếu có phản hồi từ `8.8.8.8` thì máy ảo đã ra được Internet thông qua mạng NAT.

---

### 3.5. Snapshot và clone máy ảo

Sau khi máy ảo hoạt động bình thường:

* Tạo snapshot cho máy ảo.
* Tắt máy ảo.
* Tiến hành clone máy ảo để phục vụ các phần tiếp theo.

---

# PHẦN 2: BÀI ADVANCE

## Live Migration

---

## 1. Chuẩn bị kết nối SSH không mật khẩu

### 1.1. Đảm bảo hai Host dùng chung mạng

Cả Host 1 và Host 2 cần sử dụng chung cấu hình Virtual Network:

```text
basic-network
```

---

### 1.2. Cài đặt và bật SSH Server trên cả hai Host

```bash
sudo apt install openssh-server -y
sudo systemctl enable --now ssh
```

---

### 1.3. Tạo SSH Key trên Host 1

```bash
ssh-keygen -t rsa
```

---

### 1.4. Copy SSH Key từ Host 1 sang Host 2

```bash
ssh-copy-id host1@10.10.10.12
```

---

### 1.5. Kiểm tra kết nối giữa hai Host

Từ Host 1, ping sang Host 2:

```bash
ping 10.10.10.12 -c 4
```

Kiểm tra SSH:

```bash
ssh host1@10.10.10.12
```

Nếu SSH không yêu cầu nhập mật khẩu thì cấu hình SSH Key đã thành công.

---

## 2. Chuẩn bị Storage và tối ưu phần cứng KVM

### 2.1. Chuyển file image vào Storage Pool mặc định

Chuyển file `.img` của máy ảo vào thư mục mặc định của libvirt:

```bash
/var/lib/libvirt/images/
```

Ví dụ:

```bash
sudo mv ~/Downloads/cirros.img /var/lib/libvirt/images/
```

---

### 2.2. Cấu hình chuẩn ổ cứng VirtIO

Trong `virt-manager`, vào phần cấu hình phần cứng của máy ảo.

Đảm bảo ổ cứng đang sử dụng chuẩn kết nối:

```text
VirtIO
```

Không nên dùng:

```text
SATA
IDE
```

Lý do: VirtIO giúp tối ưu hiệu năng và tránh lỗi khi máy ảo khởi động sau khi migrate.

---

## 3. Thực hiện Live Migration

Đứng tại Host 1, chạy lệnh di chuyển nóng máy ảo `vm1` sang Host 2:

```bash
sudo virsh migrate --live --copy-storage-all --persistent --unsafe --verbose vm1 qemu+ssh://host1@10.10.10.12/system
```

Ý nghĩa chính:

| Tùy chọn             | Ý nghĩa                                |
| -------------------- | -------------------------------------- |
| `--live`             | Di chuyển máy ảo khi máy vẫn đang chạy |
| `--copy-storage-all` | Copy toàn bộ disk sang Host đích       |
| `--persistent`       | Giữ cấu hình VM ở Host đích            |
| `--unsafe`           | Cho phép migrate trong môi trường lab  |
| `--verbose`          | Hiển thị tiến trình migrate            |

---

## 4. Xin lại IP cho máy ảo sau khi di chuyển

Sau khi migrate sang Host 2, vào Console của máy ảo và chạy:

```bash
sudo udhcpc -i eth0
```

Sau đó kiểm tra mạng:

```bash
ping 8.8.8.8 -c 4
```

Nếu máy ảo vẫn có kết nối mạng sau khi migrate thì bài Live Migration hoàn thành.

---

# PHẦN 3: BÀI EXPERT

## SDN với Open vSwitch và GRE Tunnel

---

## Mục tiêu

Dựng mô hình mạng ảo hóa lồng nhau sử dụng:

* Open vSwitch.
* VLAN 10.
* GRE Tunnel.
* Hai Host KVM chạy trong môi trường Nested Virtualization.

Mục tiêu là để hai máy ảo nằm trên hai Host khác nhau có thể giao tiếp Layer 2 với nhau thông qua VLAN 10.

GRE Tunnel sẽ đóng vai trò là mạng **Overlay**, chạy bên trên mạng vật lý hoặc mạng nền **Underlay** `10.10.10.x`.

---

## Bước 1: Chuẩn bị môi trường trên cả hai Host

### 1.1. Tắt tường lửa UFW

Thực hiện trên cả Host 1 và Host 2:

```bash
sudo ufw disable
```

> 🚨 **Lưu ý quan trọng:**
> GRE sử dụng **IP Protocol 47**, không phải TCP hoặc UDP.
> Nếu tường lửa chặn GRE, hai Host vẫn có thể ping được nhau ở mạng Underlay, nhưng VM bên trong sẽ không ping được nhau qua GRE Tunnel.

---

## Bước 2: Tạo Open vSwitch Bridge và cấu hình GRE Tunnel

---

### 2.1. Cấu hình trên Host 1

Giả sử IP Underlay của Host 1 là:

```text
10.10.10.11
```

IP Underlay của Host 2 là:

```text
10.10.10.12
```

Trên Host 1, chạy:

```bash
sudo ovs-vsctl add-br br-ovs
sudo ovs-vsctl add-port br-ovs gre0 -- set interface gre0 type=gre options:remote_ip=10.10.10.12
```

---

### 2.2. Cấu hình trên Host 2

Trên Host 2, chạy:

```bash
sudo ovs-vsctl add-br br-ovs
sudo ovs-vsctl add-port br-ovs gre0 -- set interface gre0 type=gre options:remote_ip=10.10.10.11
```

---

### 2.3. Kiểm tra cấu hình OVS

Trên cả hai Host, chạy:

```bash
sudo ovs-vsctl show
```

Kết quả cần thấy:

```text
Bridge br-ovs
    Port br-ovs
        Interface br-ovs
            type: internal
    Port gre0
        Interface gre0
            type: gre
            options: {remote_ip="10.10.10.x"}
```

---

## Bước 3: Định nghĩa mạng OVS-VLAN trong KVM

Tạo file XML để libvirt hoặc virt-manager có thể hiểu và kết nối máy ảo vào bridge `br-ovs`.

Mạng này mặc định gắn VLAN tag 10 cho máy ảo.

Thực hiện trên cả hai Host.

---

### 3.1. Tạo file cấu hình XML

```bash
cat <<EOF > /tmp/ovs-vlan.xml
<network>
  <name>ovs-vlan</name>
  <forward mode='bridge'/>
  <bridge name='br-ovs'/>
  <virtualport type='openvswitch'/>
  <portgroup name='vlan10' default='yes'>
    <vlan>
      <tag id='10'/>
    </vlan>
  </portgroup>
</network>
EOF
```

---

### 3.2. Nạp cấu hình vào libvirt

```bash
sudo virsh net-define /tmp/ovs-vlan.xml
```

---

### 3.3. Khởi động mạng OVS-VLAN

```bash
sudo virsh net-start ovs-vlan
```

---

### 3.4. Cho phép mạng tự khởi động cùng hệ thống

```bash
sudo virsh net-autostart ovs-vlan
```

---

### 3.5. Kiểm tra danh sách mạng

```bash
sudo virsh net-list --all
```

Kết quả cần có mạng:

```text
ovs-vlan
```

ở trạng thái:

```text
active
```

---

## Bước 4: Cấu hình card mạng cho máy ảo

Thực hiện trên cả hai Host.

### 4.1. Tắt máy ảo trước khi cấu hình

Đảm bảo hai máy ảo đều đang ở trạng thái:

```text
Shut down
```

---

### 4.2. Chuyển Network Source sang ovs-vlan

Trong `virt-manager`:

```text
VM Details → NIC → Network source
```

Chọn:

```text
Virtual network 'ovs-vlan' : Bridge network
```

Sau đó Apply cấu hình.

---

### 4.3. Xử lý lỗi trùng MAC do clone máy ảo

> 🚨 **Lưu ý quan trọng:**
> Nếu máy ảo ở Host 2 được clone từ máy ảo ở Host 1, hai máy có thể bị trùng địa chỉ MAC.
> Trong mạng Layer 2, trùng MAC sẽ khiến switch học sai địa chỉ và làm gói tin bị mất.

Cách khắc phục:

* Vào phần cấu hình NIC của một trong hai máy ảo.
* Thay đổi một ký tự bất kỳ ở cuối địa chỉ MAC.
* Apply cấu hình.
* Sau đó mới bật máy ảo.

---

## Bước 5: Bật máy ảo, ép VLAN tag và cấp IP tĩnh

---

### 5.1. Bật hai máy ảo

Sau khi bật VM, libvirt sẽ tự động tạo cổng dạng `vnetX` và gắn vào bridge `br-ovs`.

Kiểm tra bằng lệnh:

```bash
sudo ovs-vsctl show
```

Ví dụ có thể thấy:

```text
Port vnet0
    Interface vnet0
```

---

### 5.2. Kiểm tra VLAN tag trên cổng vnet

Nếu dưới cổng `vnetX` chưa có dòng:

```text
tag: 10
```

thì cần ép VLAN tag thủ công.

Ví dụ:

```bash
sudo ovs-vsctl set port vnet0 tag=10
```

Trong đó `vnet0` là tên cổng thực tế của máy ảo.

Nếu máy ảo dùng cổng khác, ví dụ `vnet1`, thì chạy:

```bash
sudo ovs-vsctl set port vnet1 tag=10
```

---

### 5.3. Cấp IP tĩnh cho VM 1

Trên VM 1 ở Host 1:

```bash
sudo ifconfig eth0 172.16.10.1 netmask 255.255.255.0 up
```

---

### 5.4. Cấp IP tĩnh cho VM 2

Trên VM 2 ở Host 2:

```bash
sudo ifconfig eth0 172.16.10.2 netmask 255.255.255.0 up
```

---

### 5.5. Lưu ý về CirrOS

> 🚨 **Lưu ý quan trọng:**
> Lệnh `ifconfig` trên CirrOS chỉ lưu tạm trong RAM.
> Nếu máy ảo khởi động lại, IP sẽ mất và cần cấu hình lại.

Ngoài ra, mạng VLAN này là mạng Layer 2 thuần túy, không có NAT và không có gateway ra Internet.
Vì vậy, việc máy ảo không ping được `8.8.8.8` là đúng với thiết kế.

---

## Bước 6: Kiểm tra kết nối nghiệm thu

Từ VM 1, ping sang VM 2:

```bash
ping 172.16.10.2 -c 4
```

Kết quả mong muốn:

```text
64 bytes from 172.16.10.2: icmp_seq=1 ttl=64 time=...
64 bytes from 172.16.10.2: icmp_seq=2 ttl=64 time=...
64 bytes from 172.16.10.2: icmp_seq=3 ttl=64 time=...
64 bytes from 172.16.10.2: icmp_seq=4 ttl=64 time=...
```

Nếu nhận được phản hồi từ `172.16.10.2`, bài Expert đã hoàn thành.

---

# Tổng kết luồng hoạt động

Mô hình hoạt động như sau:

```text
VM1
 |
 | VLAN 10
 |
br-ovs trên Host 1
 |
 | GRE Tunnel
 |
Mạng Underlay 10.10.10.0/24
 |
 | GRE Tunnel
 |
br-ovs trên Host 2
 |
 | VLAN 10
 |
VM2
```

Gói tin từ VM 1 đến VM 2 đi theo luồng:

```text
VM1 → vnet trên Host 1 → br-ovs → VLAN 10 → GRE Tunnel → Underlay 10.10.10.x → GRE Tunnel → br-ovs Host 2 → vnet Host 2 → VM2
```

---

# Kết luận

Qua bài thực hành này, em đã hoàn thành ba phần chính:

## Basic

* Cài đặt môi trường KVM/libvirt.
* Tạo mạng NAT.
* Tạo máy ảo CirrOS.
* Start, stop, snapshot và clone máy ảo.

## Advance

* Cấu hình SSH không mật khẩu giữa hai Host.
* Chuẩn bị storage cho máy ảo.
* Thực hiện Live Migration bằng `virsh migrate`.
* Kiểm tra máy ảo sau khi migrate sang Host đích.

## Expert

* Cài đặt và cấu hình Open vSwitch.
* Tạo bridge `br-ovs`.
* Tạo GRE Tunnel giữa hai Host.
* Tạo mạng `ovs-vlan` trong libvirt.
* Gắn máy ảo vào VLAN 10.
* Cấp IP tĩnh cho hai VM.
* Kiểm tra kết nối Layer 2 giữa hai VM qua GRE Tunnel.

Kết quả cuối cùng: hai máy ảo nằm trên hai Host khác nhau có thể ping được nhau qua mạng VLAN 10 chạy trên GRE Tunnel.
