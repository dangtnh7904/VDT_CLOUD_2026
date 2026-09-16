review: 0

ip cố định, MAC thay đổi theo điểm đến tiếp theo 

> OSI không phải thứ tự thiết bị ngoài đời, nó là abstract
> 

lap → switch → router → internet → router

- **BGP(border gateway protocol) : ví dụ: tao biết đường đi đến 142.250.x.x**

Flow: đọc MAC xong bỏ header MAC thì thấy IP xong lại bọc MAC mới để gửi tiếp

# Thiết kế mạng

## Classic Spanning-Tree

STProtocol chặn 1 vài các link để tranh looping 

⇒ mua 2 link dự phòng mà chỉ dùng được 1 thôi, HA kém do mất thời gian mở các cổng kia ra

## vPC

hoạt động như 1 switch duy nhất 

⇒ bằng cách tạo thành 1 vPC domain

dùng port channel để hợp nhất 2 link(đã xử lý việc nhận gói tin ⇒ không có loop)

drawbacks: max là 2 switch, nếu đứt thì dùng anti split-brain(tắt 1 con)

định tuyến khó do vPC layer 2 Peer-Link(đồng bộ hóa metadata ở control plane)

## Clos network

Spine with multiple leaf that connected via vPC

# underlay and overlay network

maximum number of vlan in a single DC iss 4096

VM is migrated(cant change IP)

⇒ we need to separate to 2 different infra: underlay and overlay

**Underlay chỉ kết nối các tunnel VTEP (chỉ làm layer 3 : kết nối IP giữa các Edge Device)**

NVE: network virtual edge: điều phối gói tin trong mạng ảo

VTEP(VxLAN Tunnel End-Point): điểm đầu và cuối encap decap(ip vật lý)

VTEP phải nằm trên NVE để ảo hóa trong mạng ảo thì mới có thể encap decap ⇒ gọi gộp là edge device

underlay NVE cần 1 IP vật lý để định tuyến, nó cũng chính là VTEP IP để các thiết bị Router/Switch vật lý biết để chuyển tiếp

## Control plane for overlay

- Flood and Learn : đơn giản nhưng tốn băng thông, unicasst hết tất cả VTEPs
- Central SDN controller: điều phối forward đúng VTEP
- BGP EVPN(host distribution protocol): nó broadcast MAC/IP btw VTE (common nowadays)

# Openstack Networking

> neutron:
> 

Cinder là quản lý, Ceph là nơi lưuu trữ

SNAT tập trung: tất cả VM trong subnet đều chung 1 IP gatewoay của router để ra ngoài

VM→ VM khác subnet thì phải đi qua network node còn nếu không thì chỉ cần đi qua overlay

VM ra internet phải có Floating IP thì mới nhận kết nối được

Thêm outer header để lên max 16tr mạng cô lập thay vì 4096 như vlan( ngoài ra còn đỡ lo vụ VM đổi cluster)

VM đổi cluster thì nó sẽ được thông báo cho toàn bộ CP qua centralize hay BGP, thì rồi nó sẽ điều phối gói tin ra đúng vxlan và đúng IP VM, 

đến lúc ra ngoài thì nó đã được đóng lại bởi qrouter(gateway)

# Namespace(qrouter)(quản lý định tuyến)(hộp ảo hóa mạng)

unique :

- network interfaces
- routing table
- iptables rules
    - port numbers