> **Tài liệu nghiên cứu/lịch sử — 09/10/2026:** quyết định triển khai và lộ trình hiện hành nằm ở [README](README.md) và [plan tổng PA2](plan-tổng.md). Nội dung PA1, H0, phương án so sánh hoặc target tương lai bên dưới không phải backlog/gate đang dùng; giữ để đối chiếu nguồn.

Đúng, nếu đem phương án này đi bảo vệ trước sếp thì tôi sẽ không bảo vệ theo kiểu “PA1 lúc nào cũng tốt hơn mọi cách khác”. Tôi sẽ nói rõ:

> **PA1 là cơ chế kiểm soát rủi ro. Full-drain được dùng ở canary/high-risk; khi scale production thì Controller + Web cho phép giảm xuống targeted drain/targeted validation để tránh phải di chuyển 24 PB qua lại.**

MOP lab của bạn hiện đã làm đúng tinh thần này ở mức OSD: `pg-upmap-items X → S` theo batch, chờ `active+clean`, rồi mới nâng X. MOP OSD MOP OSD

---

# 1. “Tại sao không dùng drain?”

Câu trả lời đầu tiên phải là:

> **Thực ra PA1 có dùng drain. `pg-upmap-items` chính là controlled drain của phương án này.**

Điểm khác biệt là **không drain bằng cách `out`/reweight X rồi để CRUSH tự remap toàn bộ một lượt**.

Nếu làm:

```text
osd.X out
    ↓
CRUSH tính lại placement
    ↓
toàn bộ PG trên X bắt đầu remap/recovery
    ↓
nhiều OSD đích cùng nhận dữ liệu
```

thì bạn kiểm soát kém hơn:

- PG nào đi trước;
- PG nào đi sau;
- PG nào là canary;
- đích cụ thể là OSD nào;
- bao nhiêu PG đang recovery cùng lúc.

Trong khi `upmap` là exception trong OSDMap cho phép điều chỉnh placement từng PG rất chi tiết. Ceph cũng mô tả upmap là cơ chế fine-grained để điều chỉnh PG→OSD. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/balancer/?utm_source=chatgpt.com)

PA1:

```text
PG 1 → X → S
       ↓
      clean
       ↓
PG 2 → X → S
PG 3 → X → S
...
```

nên có thể:

```text
10 PG
 ↓
observe
 ↓
PASS
 ↓
10 PG tiếp
```

### Nhưng production 1.600 OSD thì sao?

Ở đây tôi **không khuyến nghị full-drain bằng upmap từng PG cho cả 1.600 OSD**.

Tôi chia PA1 thành hai mode:

| Mode                | Dùng ở đâu                                                        | Drain                                            |
| ------------------- | --------------------------------------------------------------------- | ------------------------------------------------ |
| **PA1-Full**  | Canary đầu tiên, hardware class mới, major upgrade, OSD nghi ngờ | Drain toàn X                                    |
| **PA1-Scale** | Rollout diện rộng sau khi canary PASS                               | Chỉ targeted/canary PG + native rolling upgrade |

Như vậy `upmap-items` là **công cụ drain**, nhưng không bắt buộc biến toàn bộ production thành hàng triệu thao tác manual.

Controller của bạn chính là thứ tự động quản lý PG scope, epoch và evidence để upmap không trở thành gánh nặng vận hành.

---

# 2. “Tại sao không upgrade S trước rồi đổ toàn bộ dữ liệu X sang S, sau đó upgrade X?”

Phương án này **không sai**.

Thậm chí:

```text
S 16.2.5
   ↓ upgrade
S 16.2.15
   ↓
X 16.2.5 ─────→ S 16.2.15
                  ↑
          recovery/backfill
```

có một lợi ích:

> Nó test được OSD version mới nhận recovery/backfill từ OSD version cũ.

Nhưng tôi sẽ không chọn nó làm **quy trình chính** vì 4 vấn đề.

### Vấn đề 1 — S trở thành bottleneck

Nếu X có rất nhiều PG:

```text
X
├── PG1 ─┐
├── PG2  │
├── PG3  ├──→ S
├── ...  │
└── PGn ─┘
```

thì toàn bộ:

- dung lượng;
- recovery I/O;
- network;
- PG count;

dồn vào S.

Với cluster đang khoảng **70%**, điều này đặc biệt nguy hiểm.

Ceph có thể rơi vào `backfill_toofull` nếu target không còn đủ headroom để nhận recovery. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/health-checks/?utm_source=chatgpt.com)

### Vấn đề 2 — failure domain

Không phải PG nào của X cũng có thể hợp lệ để thay X bằng cùng một S.

Ví dụ:

```text
PG = [X@hostA, OSD@hostB, OSD@hostC]

S nằm hostB
```

nếu CRUSH rule yêu cầu replica tách host thì:

```text
X → S@hostB
```

không phải placement hợp lệ.

Do đó production phải là:

```text
X
├── PG1 → S1
├── PG2 → S2
├── PG3 → S3
└── ...
```

theo CRUSH/failure domain/capacity chứ không phải một S duy nhất.

### Vấn đề 3 — chưa chứng minh X sau upgrade

S PASS không có nghĩa:

```text
X 16.2.15 PASS
```

Cuối cùng X vẫn phải được nâng và test lại.

Vậy bạn vẫn phải có:

```text
upgrade X
 ↓
X replica validation
 ↓
X primary validation
```

### Vấn đề 4 — dữ liệu đi hai lần

Nếu cuối cùng muốn trả placement về:

```text
X → S
```

rồi:

```text
S → X
```

thì bạn trả phí network/recovery hai lần.

---

### Tuy nhiên có một biến thể production rất đáng xem xét

**Rotating spare**:

```text
S là spare
      ↓
X → S
upgrade X
      ↓
X trở thành spare mới
      ↓
Y → X
upgrade Y
      ↓
Y trở thành spare mới
...
```

Không cần ngay lập tức:

```text
S → X
```

sau mỗi OSD.

Cách này có khả năng giảm một nửa lượng dữ liệu phải di chuyển trong wave, nhưng sẽ làm mapping phức tạp hơn và cần Controller quản lý rất chặt.

Tôi coi đây là **optimization phase sau khi PA1 cơ bản được chứng minh**, không phải thứ đem vào production ngay.

---

# 3. “Nếu X lưu lỗi thì rollback thế nào?”

Đây là chỗ câu trả lời của bạn rất mạnh:

> **Rollback của PA1 trước hết là rollback placement/service, không nhất thiết là downgrade software.**

Giả sử:

```text
X vừa upgrade
 ↓
nhận PG canary
 ↓
Controller phát hiện mismatch
```

thì:

```text
           MISMATCH
              │
              ▼
         HOLD rollout
              │
       không return thêm PG
              │
              ▼
    primary-affinity X = 0
              │
              ▼
    isolate/remove X khỏi
       serving path
              │
              ▼
    healthy replicas phục vụ
              │
              ▼
    investigate X
```

Nói dân dã đúng như bạn bảo:

> **“Sút X ra khỏi đường phục vụ.”**

Nhưng phải phân biệt:

```text
ceph osd out X
```

hoặc stop/isolate X

với:

```text
ceph osd lost X
```

`lost` là một thao tác nguy hiểm và Ceph cảnh báo có thể làm mất dữ liệu nếu không còn replica; không dùng nó như một rollback bình thường. [Ceph Documentation](https://docs.ceph.com/en/reef/man/8/ceph/?utm_source=chatgpt.com)

### Nếu X đang là replica

Dễ nhất:

```text
healthy primary
    │
    ├── healthy replica
    └── X SUSPECT
```

Controller:

1. HOLD;
2. không trả thêm PG;
3. lấy `list-inconsistent-obj`;
4. xác định healthy/authoritative copies;
5. remove X khỏi serving path;
6. recover lại replica trên OSD lành.

### Nếu X đang primary

```text
X suspect primary
      │
      ├── replica A good
      └── replica B good
```

thì isolate X:

```text
X out/down
  ↓
peering
  ↓
A/B trở thành primary
```

rồi recover.

Ceph có `pg repair`, nhưng tài liệu cũng cảnh báo repair không phải trường hợp nào cũng tự xác định authoritative copy chính xác; vì vậy **không chạy repair mù trước khi giữ evidence và xác định shard lỗi**. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/troubleshooting/troubleshooting-pg/?utm_source=chatgpt.com)

Đó cũng là lý do canary quan trọng:

```text
Mismatch khi 5 PG
```

khác hoàn toàn:

```text
Mismatch sau khi đã trả 500 PG vào X
```

---

# 4. “Checksum thế nào khi X làm replica và khi X làm primary?”

Đây là phần Controller/Web của bạn giải quyết tốt nhất.

## A. Khi X vừa nhận dữ liệu và đang làm replica

Luồng:

```text
Primary cũ
    │
    │ recovery/backfill
    ▼
X 16.2.15
  REPLICA
```

Bạn **không cần deep-scrub toàn cluster**.

Chỉ deep-scrub:

> **các PG vừa được return vào X.**

Ví dụ:

```text
return PG 9.6
return PG 9.a
return PG 9.f
```

Controller chạy:

```bash
ceph pg deep-scrub 9.6
ceph pg deep-scrub 9.a
ceph pg deep-scrub 9.f
```

Deep scrub đọc data và checksum, rồi so primary với replicas. Nếu replica khác authoritative copy, PG bị đánh dấu inconsistent. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/pg-repair/?utm_source=chatgpt.com)

Do đó:

```text
Không phải:

deep-scrub 24 PB

Mà:

deep-scrub canary PG scope của osd.X
```

Đây là khác biệt cực lớn.

Web của bạn lưu:

```text
osd.1
Replica validation

PG 9.6   deep-scrub PASS
PG 9.a   deep-scrub PASS
PG 9.f   deep-scrub PASS
```

---

## B. Nhưng nếu tất cả replicas đều lưu cùng một dữ liệu sai thì sao?

Đây là giới hạn của deep-scrub.

Giả sử client muốn:

```text
ABC
```

nhưng vì một lỗi nào đó, storage path nhận:

```text
ABX
```

và tất cả replicas đều có:

```text
ABX
```

thì:

```text
Replica1 = ABX
Replica2 = ABX
Replica3 = ABX
```

Deep scrub thấy:

```text
MATCH
```

Nó **không biết client ban đầu muốn ABC**.

Đó là lý do web của bạn cần một lớp khác:

### Client-intent checksum

Trước write:

```text
Client payload = ABC

SHA256(ABC) = H1
```

lưu H1 vào Controller DB.

Sau ACK:

```text
GET object
 ↓
SHA256(data) = H2
```

Gate:

```text
H1 == H2
```

Nếu:

```text
H1 != H2
```

HOLD.

Đây không phải vì ta khẳng định upgrade gây lỗi này.

Mà đơn giản là:

> **bài validation end-to-end chứng minh dữ liệu nhận lại đúng với dữ liệu client đã gửi.**

---

# Khi X trở thành primary

Đây là nơi dùng **exact targeted RADOS probe**.

Controller không bắn request ngẫu nhiên rồi hy vọng nó vào X.

Nó làm:

```text
generate object name
       ↓
ceph osd map pool object
       ↓
primary == X ?
   │          │
  NO         YES
   │          ↓
 thử tên    dùng object
 khác
```

Khi có:

```text
PG 9.6
acting [X,A,B]
primary = X
```

Controller tạo:

```text
payload known-good
SHA256 = H1
```

rồi:

```text
PUT
 ↓
X = PRIMARY
 ↓
replication
 ↓
ACK
 ↓
GET
 ↓
SHA256 = H2
```

bắt buộc:

```text
H1 == H2
```

Sau đó:

```text
deep-scrub PG 9.6
```

Như vậy có **hai lớp độc lập**:

```text
Client intent
H1 == H2
     +
Replica/local consistency
deep-scrub PASS
```

Đây là cách giải thích H0/Controller hợp lý hơn nhiều.

---

# RGW/RBD thì sao?

Web hiện tại của bạn vốn đã có thiết kế:

- baseline text + image + binary;
- lưu checksum;
- sau upgrade remap/mount;
- verify checksum;
- preview;
- thử write mới;
- theo dõi IOPS/throughput/latency. plan(5)(1)

Nên Controller sử dụng:

```text
RADOS exact probe
        +
RGW service test
        +
RBD service test
```

RADOS chứng minh **đúng X primary**.

RGW/RBD chứng minh **dịch vụ end-to-end vẫn chạy đúng**.

---

# 5. “1.600 OSD, 24 PB, 70% full thì làm sao xong trong ≤1 năm?”

Đây là chỗ tôi sẽ **không bảo vệ full-PA1 trên cả 1.600 OSD**.

Nếu yêu cầu 1 năm:

```text
1600 / 365 ≈ 4.4 OSD/ngày
```

tức trung bình khoảng:

```text
31 OSD/tuần
133 OSD/tháng
```

Nếu chỉ tính khoảng 250 ngày thực thi thực tế:

```text
≈ 6.4 OSD/ngày
```

Do đó **một OSD/lần cho toàn production không đáp ứng mục tiêu**.

---

## Và full drain mọi OSD còn có vấn đề lớn hơn

Nếu 24 PB là raw data hiện đang sử dụng:

```text
drain ra + trả lại
≈ 2 × 24 PB
≈ 48 PB movement
```

Chỉ riêng lượng đó muốn hoàn tất trong một năm đã tương đương trung bình khoảng:

```text
~1.5 GB/s
```

liên tục 24/7, chưa tính:

- replication overhead;
- client I/O;
- recovery throttling;
- retries;
- scrub;
- network contention.

Nếu 24 PB là **logical data** với replication size=3 thì lượng raw movement tiềm năng còn lớn hơn rất nhiều.

Vì vậy production phải khác lab.

---

## Tôi đề xuất rollout 3 tầng

### Tầng 1 — Qualification Canary

Full PA1:

```text
1 OSD
 ↓
full drain
 ↓
upgrade
 ↓
replica validation
 ↓
primary validation
 ↓
benchmark
```

Sau đó thêm OSD đại diện:

```text
HDD class A
HDD class B
host/rack class khác
```

---

### Tầng 2 — Small batch

Ví dụ:

```text
5 → 10 → 20 OSD
```

nhưng **parallelism không bằng batch size**.

Ví dụ batch có 20 OSD nhưng chỉ:

```text
4 OSD active upgrading
```

cùng lúc.

Controller chọn OSD không có PG conflict/failure-domain conflict.

---

### Tầng 3 — Production wave

Không full-drain mọi OSD.

Một OSD:

```text
targeted canary PG
        +
ok-to-stop
        +
redeploy
        +
per-OSD validation
```

Web vẫn test **từng OSD**:

```text
osd.501 PASS
osd.502 PASS
osd.503 PASS
...
```

nhưng không cần deep-scrub toàn data của từng OSD.

Chỉ:

```text
sampled/targeted PG
+
exact RADOS probe
+
service workload
+
telemetry
```

Cephadm cũng hỗ trợ staggered upgrade với filters/`limit` từ Pacific 16.2.11; khi đi từ 16.2.5 thì MGR phải được đưa lên version hỗ trợ trước khi dùng các limiting parameters. [Ceph Documentation](https://docs.ceph.com/en/pacific/cephadm/upgrade/?utm_source=chatgpt.com)

---

# Cluster đang 70% thì đặc biệt thế nào?

Đây là nơi **Capacity Guard của web** của bạn trở thành một phần thực sự hữu ích.

Plan web hiện tại đã thiết kế:

- không dùng cluster-average;
- nhìn OSD đầy nhất;
- pause khi recovery/backfill;
- có `failure_reserve_mode=one_osd|one_host`. plan(5)(1)

Và plan cũng đã ghi rõ: 70% không tự chứng minh đủ headroom để drain một OSD; cần kiểm failure reserve/failure domain thực tế. plan(5)(1)

Vậy trước mỗi batch:

```text
Capacity Controller
      ↓
simulate target scope
      ↓
headroom đủ?
      ↓
recovery target hợp lệ?
      ↓
one-OSD failure reserve đủ?
```

không đủ thì:

```text
BLOCK BATCH
```

chứ không cố chạy.

---

# 6. “Đang nâng X mà một OSD khác cùng acting set chết thì sao?”

Giả sử:

```text
size = 3
min_size = 2

PG:
[X, A, B]
```

Nếu X đang down:

```text
[A, B]
```

vẫn còn 2 copies.

Với `min_size=2`, I/O vẫn có thể chạy.

Ceph định nghĩa `min_size` là số replica tối thiểu để cho phép I/O; với `min_size=2`, object không nhận I/O khi số replica khả dụng thấp hơn 2. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/pools/?utm_source=chatgpt.com)

Bây giờ A lại chết:

```text
[B]
```

thì:

```text
available replicas = 1
min_size = 2
```

Ceph phải **dừng I/O của PG đó**.

Điểm cực kỳ quan trọng khi trả lời sếp:

> **min_size=2 bảo vệ consistency/safety bằng cách ngừng phục vụ khi chỉ còn một copy; nó không bảo đảm dịch vụ vẫn available sau hai OSD unavailable.**

---

## Muốn vừa upgrade X vừa chịu thêm một OSD chết mà vẫn phục vụ thì sao?

Trước khi stop X, phải biến:

```text
[X,A,B]
```

thành:

```text
[C,A,B]
```

và chờ:

```text
active+clean
```

tức PG vẫn có đủ 3 copies **mà không phụ thuộc X**.

Lúc đó:

```text
X down
```

không ảnh hưởng.

Nếu sau đó A chết:

```text
[C,B]
```

vẫn còn:

```text
2 replicas
```

= `min_size`.

Đây chính là một lý do kỹ thuật rất mạnh để **full drain X ở những trường hợp cần N+1 maintenance safety**.

---

## Controller phải thêm một gate

Tôi sẽ gọi:

> **Maintenance N+1 Gate**

Trước stop X:

```text
for every PG originally touching X:

X NOT in acting set
AND acting count == pool.size
AND PG active+clean
AND replicas span valid failure domains
AND capacity failure reserve PASS
```

Sau đó mới:

```text
UPGRADE X
```

`ceph osd ok-to-stop` vẫn phải dùng, nhưng không đủ để chứng minh N+1. Chính Ceph mô tả `ok-to-stop` là kiểm cluster vẫn readable/writeable sau khi stop OSD, trong khi redundancy có thể bị giảm. [Ceph Documentation](https://docs.ceph.com/en/reef/man/8/ceph/?utm_source=chatgpt.com)

Do đó:

```text
ok-to-stop
      +
Maintenance N+1 Gate
```

mới là gate của bạn.

---

## Khi upgrade song song nhiều OSD

Controller xây **PG conflict graph**.

Ví dụ:

```text
osd.1 ─ PG 1.a ─ osd.20
```

thì:

```text
osd.1 và osd.20
```

không được nằm cùng parallel set nếu dừng cả hai sẽ vi phạm `min_size`.

Có thể coi:

```text
OSD = vertex
cùng PG = edge
```

Batch scheduler chọn các OSD **không có edge conflict** và không nằm cùng failure domain rủi ro.

Đây là một feature rất hợp lý để thêm vào Controller production của bạn.

---

# 7. “Tại sao canary, sao không rebalance cả cluster?”

Vì **canary và rebalance giải quyết hai bài toán khác nhau**.

Rebalance trả lời:

> “Dữ liệu nên phân bố thế nào trên toàn cluster?”

Canary trả lời:

> “Version mới có an toàn để mở rộng rollout không?”

Nếu bạn rebalance toàn cụm:

```text
24 PB cluster
     ↓
CRUSH/balancer thay đổi placement diện rộng
     ↓
mass recovery/backfill
     ↓
network
disk
latency
     ↓
rất khó biết lỗi do upgrade
hay do massive rebalance
```

Bạn vừa tăng blast radius vừa tạo một đống noise.

Ceph balancer/upmap vốn có thể thay đổi PG placement; tài liệu cũng cho phép tắt balancer khi dùng custom upmap để tránh hai bên đồng thời thay mapping. [Ceph Documentation](https://docs.ceph.com/en/pacific/rados/operations/balancer/?utm_source=chatgpt.com)

Canary của bạn:

```text
1 PG
 ↓
1 OSD
 ↓
1 hardware class
 ↓
small batch
 ↓
large batch
```

giúp cô lập nguyên nhân.

---

# Và đây là lúc 3 feature của bạn ghép lại thành một hệ hoàn chỉnh

```text
                       PA1
                        │
            kiểm soát DATA MOVEMENT
                        │
                        ▼
                OSD mới upgrade
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
          REPLICA              PRIMARY
          CANARY               CANARY
              │                   │
      targeted deep-scrub     client SHA256
      baseline checksum       exact RADOS probe
              │                   │
              └─────────┬─────────┘
                        ▼
                  CONTROLLER
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
     PG scope      N+1 safety      PASS/HOLD
     + epoch       + conflict       decision
                        │
                        ▼
                STORAGE LAB WEB
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
     RGW              RBD            Benchmark
    checksum         checksum       fio/rbd/Warp
       │                │                │
       └────────────────┼────────────────┘
                        ▼
                    EVIDENCE
                        │
                        ▼
                next OSD / HOLD
```

Web hiện tại của bạn vốn đã có định hướng baseline checksum trước upgrade, theo dõi IOPS/throughput/latency trong/sau upgrade và verify checksum sau upgrade. plan(5)(1) Vì vậy đây không phải xây thêm một hệ thống tách rời; nó là mở rộng tự nhiên của console.

## Nếu tôi phải chốt toàn bộ phương án trước sếp bằng khoảng 30 giây

> **“Chúng tôi không rebalance toàn cụm để phục vụ upgrade. Với OSD canary hoặc trường hợp yêu cầu N+1, chúng tôi dùng `pg-upmap-items` để drain có chủ đích, chỉ di chuyển các PG của OSD mục tiêu và kiểm soát theo batch. Sau khi nâng, OSD được đưa trở lại theo hai gate: trước tiên làm replica và targeted deep-scrub các PG vừa recovery; sau đó làm primary trên scope nhỏ, dùng payload có checksum từ client, targeted RADOS write/read và deep-scrub để kiểm cả end-to-end lẫn local consistency. Nếu phát hiện lỗi, rollout dừng và OSD nghi ngờ được loại khỏi serving path, dữ liệu phục hồi từ replica tốt. Khi mở rộng lên 1.600 OSD, full-PA1 chỉ dùng cho canary/high-risk; rollout diện rộng dùng batch theo failure domain, PG-conflict scheduling, Capacity Guard và validation theo từng OSD để đạt tốc độ triển khai mà không phải di chuyển toàn bộ 24 PB qua lại.”**

Đây là phiên bản mà tôi nghĩ **bảo vệ được cả tính an toàn lẫn tính khả thi production**.
