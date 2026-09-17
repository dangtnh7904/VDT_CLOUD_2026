# 04 — MON, OSDMap, CRUSH và placement: v16.2.5 → v16.2.15

> **Kết quả:** CSV giữ đủ 52 dòng do `04-mon-osdmap-crush` sở hữu. Markdown tập trung vào các thay đổi có thể tác động rolling upgrade, quorum, feature gate, map compatibility, placement/recovery hoặc rollback. Test, build và command-only diff vẫn nằm trong CSV nhưng chỉ được dùng làm bằng chứng hỗ trợ hoặc kết luận trivial/conditional.
>
> **Trạng thái kiểm chứng:** đã đọc net diff hai endpoint, caller/encoding liên quan, lịch sử commit và test trong repository; chưa build, chưa chạy test, chưa thao tác cluster và chưa thay đổi OSDMap/MonMap/CRUSH map.

## 1. Phạm vi và nguồn

- Base: `v16.2.5` → `0883bdea7337b95e4b611c768c0279868462204a`.
- Target: `v16.2.15` → `618f440892089921c3e944a991122ddc44e60516`.
- Repository: `ceph16.2.15/ceph`; base là ancestor của target, working tree nguồn sạch và repository không shallow.
- Inventory chi tiết: [04-mon-osdmap-crush.csv](./04-mon-osdmap-crush.csv), đúng 21 cột và thứ tự master inventory.
- Owner set: 52 dòng (`A=1`, `M=51`), tổng `+1990/-554`; `P0=37`, `P1=3`, `P2=12`; routing ban đầu gồm 38 `deep`, 2 `conditional`, 12 `reference-only`.

Các dòng được sàng lọc gồm inventory `395`–`397`, `1061`–`1066`, `1490`–`1524`, `1583`–`1585`, `2496`–`2498`, `2563`, `2591`. Báo cáo không lặp 52 path thành bảng; ledger ở mục 7 cho disposition cuối của từng index.

Phạm vi này có giao cắt hành vi với:

- `01-osd-pg-recovery.md`: peering/recovery, PG merge và fast shutdown;
- `05-messaging-auth-common.md`: CephX, MonClient và wire feature;
- `06-config-defaults.md`: `require-osd-release`, mClock/default OSD và pool/autoscaler controls.

## 2. Kết luận điều hành

1. **Feature gate đáng chú ý nhất là range blocklist.** Target thêm state mới vào OSDMap incremental/full map và chỉ cho command tạo range khi cluster quảng bá feature tương ứng. Không nên tạo range entry trong rolling phase hoặc trước rollback rehearsal.
2. **`require-osd-release` trở thành checkpoint rõ hơn.** Target phát `OSD_UPGRADE_FINISHED` khi mọi OSD đang up đã có feature release mới nhưng flag còn cũ. Với cặp endpoint này, cả `v16.2.5` và `v16.2.15` đều là Pacific: đặt flag `pacific` không chặn rollback giữa hai patch, nhưng sẽ loại OSD pre-Pacific còn sót hoặc đang offline.
3. **MON restart/quorum an toàn hơn nhưng vẫn phải tuần tự.** Chuỗi sửa rank removal, connection score, quorum age và shutdown session trực tiếp giảm race/crash khi MON thay đổi trạng thái. Chúng không thay thế quorum-safe runbook.
4. **CephX và MonClient có sửa lỗi continuity.** Rotating keys chỉ thành live sau Paxos commit; MonClient gặp `-EAGAIN` mà mất active connection sẽ reopen session. Trong mixed MON phase, hành vi vẫn phụ thuộc node/leader đang chạy code cũ hay mới.
5. **FSMap cũ và standby-replay được xử lý chắc hơn.** Đây là đường tương thích trực tiếp cho CephFS/MDS trong upgrade, nhất là cluster có epoch cũ hoặc failover.
6. **Placement/PG fixes chủ yếu tự có hiệu lực theo binary target; pool/stretch commands là conditional.** PG merge không còn giữ OSDMap trim vô hạn, stale `pg_temp`/invalid upmap được dọn đúng hơn; stretch mode cần checklist riêng nếu đang dùng.
7. **Monitor DB capacity vẫn là preflight bắt buộc.** Target sửa health-store không trim; upgrade không cứu được MON đã hết disk trước khi daemon target lên được.
8. **Config mask theo CRUSH location có thể bắt đầu áp dụng đúng sau reconnect.** Target ConfigMonitor lấy location trực tiếp từ OSD entity; cluster có `ceph config set ... location:`/host/class mask phải so effective config trước và sau canary.

## 3. Ma trận finding

| ID | Chủ đề | Activation | Pha | Rủi ro nếu kích hoạt | Confidence |
|---|---|---|---|---|---|
| MON-001 | Range blocklist và OSDMap v11 | Tạo/còn range entry | mixed/rollback | Cao | High |
| MON-002 | `require-osd-release` warning/gate | Flag còn dưới Pacific hoặc có OSD legacy bị bỏ sót | full/legacy rejoin | Cao với OSD pre-Pacific; thấp cho rollback giữa hai endpoint | High |
| MON-003 | Election, rank removal, quorum age, shutdown | MON restart/remove/replace/leader churn | mixed | Cao | High |
| MON-004 | CephX rotating keys và MonClient `-EAGAIN` | Auth rotation/reconnect | mixed | Cao | High |
| MON-005 | FSMap/MDS compatibility | Có CephFS, old epochs hoặc standby replay | mixed | Cao theo điều kiện | High |
| MON-006 | PG merge, map trim, `pg_temp`, upmap | PG merge/placement state tương ứng | mixed/stabilization | Trung bình-cao | High |
| MON-007 | Stretch-mode MonMap/CRUSH | Cluster stretch | mixed/full | Cao theo điều kiện | High |
| MON-008 | Pool/autoscaler command semantics | Operator/automation tạo hoặc resize pool | full/stabilization | Trung bình | High |
| MON-009 | Mgr/Paxos proposal và health-store trim | MGR failover, health mute/store tăng | mixed/preflight | Trung bình-cao | High |
| MON-010 | Offline repair tools | Chỉ khi recovery thủ công | recovery | Cao theo điều kiện | High |
| MON-011 | Config mask theo CRUSH location và tên key | OSD reconnect hoặc automation đọc/ghi config | mixed/validation | Trung bình theo điều kiện | High |

Rủi ro là severity khi điều kiện đúng, không phải xác suất trong cluster chưa có As-Is. Confidence được đánh giá riêng từ bằng chứng endpoint/commit.

## 4. Phát hiện chi tiết

### MON-001 — Range blocklist thêm state OSDMap mới nhưng được chặn bằng feature gate

**Owner/evidence.** Inventory `1519`–`1520`, `1583`–`1585`; chuỗi commit:

- `361e159a2e738d8b1e4a70ff66fe6ac5d3338610`: thêm `new_range_blocklist`/`old_range_blocklist` vào incremental và `range_blocklist` vào full OSDMap.
- `fd4a577317b7bb84168afca2a574513c0d823aac`: command path gọi `check_cluster_features(CEPH_FEATUREMASK_RANGE_BLOCKLIST, ...)` trước khi proposal.
- `8994ee2aacbe9429621d2fe84e1ba47457c7b87e`, `1b993ba06128ea0c3b521f217ad953f0c6e6255d`, `b9eec41dde00f640e5f2a1ee1f61e19028bc69ba`, `0053fc1bf4a332f559ff85c0e8a0421c163086a2`, `7a8e5608f0d009bc3d215e79a2c30fb02b65d00b`: trim, CLI semantics, enumeration/dump và enforcement range.

**Encoding và compatibility.** Base chỉ có exact-address blocklist. Target dùng extended OSDMap struct version `11` **khi range state không rỗng**; decode chỉ đọc trường mới khi `struct_v >= 11`. Nếu không có range entry, target không buộc map lên v11 chỉ vì binary mới. Đây là bằng chứng quan trọng: feature được kích hoạt bởi state, không tự kích hoạt ngay lúc restart.

**Mixed phase.** Command thêm CIDR/range bị từ chối nếu cluster feature check chưa đạt, nhờ đó monitor không nên proposal state mà OSD cũ không hỗ trợ. Tuy vậy automation bảo mật cần xử lý failure rõ ràng; không được fallback âm thầm sang kỳ vọng rằng range đã được áp dụng. Exact-address blocklist cũ tiếp tục là đường tương thích.

**Full upgrade và rollback.** Sau khi mọi endpoint cần thiết quảng bá feature, range entry có thể được commit và OSD target thực sự match CIDR trong `is_blocklisted()`. Vì state mới đã đi vào OSDMap v11, rollback sang base sau khi tạo range entry cần lab verification và kế hoạch loại range entries trước downgrade; report không khẳng định decoder base an toàn với mọi map/state chỉ từ forward decoder target.

**Hành động.** Trong runbook, cấm tạo range blocklist cho tới full upgrade và rollback checkpoint; kiểm tra automation/API error; test add/list/expire/remove và enforcement trên canary network. Nếu feature không dùng, finding vẫn tồn tại về capability nhưng không kích hoạt runtime.

**Đánh giá.** Rủi ro **cao khi dùng**, confidence **high**. Không có data migration, nhưng đây là map-state/wire compatibility gate thực sự.

### MON-002 — `require-osd-release` là checkpoint hoàn tất upgrade, không phải thao tác đầu vòng

**Owner/evidence.** Inventory `1519`–`1520`, `1583`–`1584`:

- `655a5304274d0fc700595da9bf7bfa94853f8820` thêm `OSDMap::pending_require_osd_release()` và health warning `OSD_UPGRADE_FINISHED` khi toàn bộ up OSD có feature Pacific/Octopus/Nautilus tương ứng nhưng flag thấp hơn.
- `aa6aaab36d97a49cf9fbf544f9c5fbdaf85c3143` thay assertion bằng validation/`--yes-i-really-mean-it` cho khoảng cách release quá cũ.
- `88fbb12766e2a31a9af366465f012920c8ca5279` sửa điều kiện metadata version mismatch của MON, giúp MGR nhận metadata phiên bản đúng sau election; đây là observability hỗ trợ checkpoint.

**Tác động.** Health warning mới xuất hiện sau khi tất cả **OSD đang up** đã đủ feature, nên có thể làm health chuyển WARN trong giai đoạn kết thúc dù data path không hỏng. Đây là tín hiệu phải audit flag và cả OSD đang down, không phải lý do tự động set để làm sạch health. Command path vẫn cấm hạ `require_osd_release` sau khi đã nâng.

**Quy tắc upgrade/rollback.** `v16.2.5` và `v16.2.15` đều quảng bá Pacific, nên `require_osd_release=pacific` **không phải** rào cản rollback target → base trong phạm vi báo cáo này. Tính one-way chỉ quan trọng với OSD pre-Pacific: nếu flag As-Is còn thấp hơn Pacific, xác nhận không có OSD legacy—kể cả OSD tạm down—trước khi nâng. Nếu flag đã là Pacific từ đầu, không cần thay nó trong rolling patch upgrade.

**Hành động.** Chụp `require_osd_release`, OSD versions/features và danh sách OSD down trước rollout. Chỉ khi As-Is flag dưới Pacific mới cần change record nâng flag sau legacy-OSD audit; test rejoin một OSD `v16.2.5` để xác nhận rollback trong cùng Pacific vẫn hợp lệ.

**Đánh giá.** Rủi ro **cao nếu còn OSD pre-Pacific bị bỏ sót**, nhưng **thấp đối với rollback `16.2.15` → `16.2.5`**; confidence **high**.

### MON-003 — Election/rank-removal và shutdown path giảm race trong rolling MON

**Owner/evidence.** Inventory `1496`–`1500`, `1514`–`1518`, test `2497`; các commit chính:

- `dba421cbe66b55bbe35ef7ca74856fef36d7d696` và `147979a4e2f4a9a6dfd0a35338a4371a73419618`: refactor rồi sửa regression tính `quorum_age()`.
- `03989d33c6af38be9740824154f443013b3bfd9f`, `03271171b5378b5d59ec5af9850f55f2050323d0`, `4e7993f8e660952ff7a0b648a23d93e06c4735e6`, `7572521a02f3cfe31b407d5bb0c599cb65f74908`, `b90f2cdb270165332965d88f991a8b5283ef83d1`, `7885566246927cb7c03513d2fb2f961d5771bca3`, `db95449e9c1702f75f6f064a841fac8f255ed5f8`, `b3d10b35fcc62152b7b4b31cfa54f67f71430bb0`: bounds/rank removal, reset peer rank và connection score, xử lý rank không tồn tại.
- `6b441f6ed94d8bf1de8d78b816dca87a3e79d36b` và follow-up `9de077dabb72f74153fc2510795669c82bd6a6f3`: không tạo session/auth mới khi MON đã đi vào shutdown.

**Tác động.** Rolling MON upgrade tạo đúng loại transition mà code này xử lý: connection rớt, election, leader đổi và daemon shutdown. Các rank-removal fixes đặc biệt quan trọng khi runbook còn remove/replace MON hoặc thay MonMap, không chỉ restart cùng identity. `quorum_age` còn được MDSMonitor dùng để phân biệt quorum mới và grace khi đánh dấu MDS laggy, nên regression có thể lan sang availability CephFS.

**Mixed phase.** Mỗi MON chạy local election code của binary nó; leader/base node vẫn có thể đi qua path cũ cho tới khi được nâng. Vì vậy upgrade MON từng node, đợi quorum ổn định giữa các bước, và tránh đồng thời thay topology/rank nếu không bắt buộc.

**Hành động.** Xác nhận odd quorum khỏe, clock/network ổn; canary follower trước leader; kiểm `quorum_age`, election epoch, connection score và session cleanup. Nếu cần remove/replace MON, tách thành change riêng hoặc test exact rank transition.

**Đánh giá.** Rủi ro **cao** vì quorum là control-plane critical; confidence **high**. Những commit này giảm lỗi chứ không cho phép phá quorum safety.

### MON-004 — CephX rotating keys chỉ publish sau Paxos commit; MonClient tự nối lại sau `-EAGAIN`

**Owner/evidence.** Inventory `1490`–`1491`, `1511`–`1512`; ngữ cảnh messenger/auth ở report 05:

- `6619e2052580ca372899c942b122c524fd6686b9`: `AuthMonitor::check_rotate()` chuyển từ cập nhật live key server trước proposal sang `prepare_rotating_update()`; key chỉ trở thành live qua `update_from_paxos()` sau commit.
- `19a322e73b473c02eb9ab534bd91d6f4805a7100`: `MonClient::_finish_auth()` gọi `_reopen_session()` khi auth trả `-EAGAIN` và không còn `active_con`.
- `9af4d681fb83030ba502a3392bbea8f4c7fab23a`: monstore rebuild bao gồm rotating keys; chỉ áp dụng cho recovery tool, xem MON-010.

**Tác động.** Base có cửa sổ live state khác committed state, có thể phân phối stale/divergent rotating keys giữa MON. Target buộc tính nhất quán Paxos trước khi key được dùng. MonClient target tránh trạng thái tick tiếp nhưng không còn session để thử auth lại—một failure mode có thể xuất hiện đúng lúc monitor restart/leader churn.

**Mixed phase.** Tính chất proposal phụ thuộc leader/AuthMonitor đang chạy target; client reconnect behavior phụ thuộc binary của từng daemon/client. Không có migration key format được thấy ở owner set, nhưng continuity chưa đồng nhất cho tới full rollout. Các client/daemon lâu đời không được loại khỏi phân tích vì chúng cần auth thành công trong upgrade.

**Hành động.** Theo dõi auth `EAGAIN`, session reopen, ticket/rotating-key logs và reconnect của OSD/MDS/MGR qua từng MON restart. Không rotate/import key thủ công đồng thời nếu không cần. Nếu rebuild store, dùng procedure riêng và bản sao store.

**Đánh giá.** Rủi ro **cao nếu race xảy ra**, likelihood phụ thuộc election/auth timing; confidence **high**.

### MON-005 — Target chủ động xử lý FSMap cũ và các edge case standby-replay

**Owner/evidence.** Inventory `1501`–`1502`, `1504`–`1505`; commits:

- `289aa7544aa2937bf93c40738dc71558be7f9fb9`: trả lỗi rõ khi FSMap struct quá cũ.
- `65168b62e721307d7f9be6b0a6cb6227ffca020f`: leader proposal để flush/upgrade FSMap struct cũ.
- `e47b6aef4da868e0fc43cbe11a68b77ae081ea7a` và `ef6cea0186ab69fec101374112732f88b20cf3fd`: tránh assert/crash khi đọc old FSMap epochs và `allow_standby_replay` cũ.
- `0118b953a589fccae9b86c785618e5c2d8b35903`: áp join `fscid` đúng với pending FSMap lúc boot.
- `02aeb59cf730274513808f4369395eda8b2f2d7f`, `cbd9a7b354abb06cd395753f93564bdc687cdb04`, `aea19718eb2111fa2f5abec20367b38b1f41e2d4`: tương thích per-MDS/replacement và damaged standby-replay.

**Tác động.** Đây là đường upgrade trực tiếp cho cluster CephFS: monitor target có thể gặp epoch FSMap được tạo bởi binary trước hoặc failover MDS trong khi MON/MDS không đồng thời ở cùng patch level. Thay vì assert/crash hoặc giữ struct cũ, target xử lý/flush qua Paxos có kiểm soát hơn.

**Mixed/full phase.** MON leader target mang phần lớn benefit; MDS base/target vẫn cần matrix failover riêng. Proposal nâng FSMap là state change, nên trước rollback cần xác minh base đọc state endpoint thực tế—không chỉ giả định vì cùng major release.

**Hành động.** Nếu có CephFS: chụp `fs dump`, standby/replay topology, compat flags và damaged state; nâng MON trước MDS theo runbook; test active failover, standby-replay và decode các epoch lưu. Không dùng `fs new --recover` hay command sửa state như một bước upgrade thường lệ.

**Đánh giá.** Rủi ro **cao theo điều kiện CephFS**, confidence **high**.

### MON-006 — PG merge không còn giữ OSDMap trim; placement state được dọn đúng hơn

**Owner/evidence.** Inventory `1519`–`1522`, `1583`–`1585`:

- `d29fd74b77a411b7a1ee38c21fcc2e30b9fdeb43`: `LastEpochClean` resize `epoch_by_pg` theo `pg_num`, bỏ report của PG đã bị merge; base có thể giữ lower bound ở PG không còn tồn tại và không trim OSDMap cho tới khi MON leader restart.
- `751b722e674cb65d1635a449e1855761b1445148`: dọn `pg_temp` của PG không còn tồn tại.
- `084d64e45b99125149164dcead3d904c3a364530`: hủy upmap có `up` set lớn hơn pool size.
- `d07efdf464e814ec710798ecb34ce8b360481daf`: tránh báo threadpool timeout giả trong OSDMap mapping.
- `80d8dedc2345f05f51cb6943c5582a16bc252789`: đặt `last_force_op_resend` đúng trong stretch transition; giao cắt report 01.

**Tác động.** Với pool từng giảm `pg_num`/PG merge, base leader có thể làm monitor giữ nhiều OSDMap hơn cần thiết, tăng store/disk cho tới restart. Khi target leader nhận beacon, accounting theo `pg_num` mới cho phép lower bound tiến. Dọn stale `pg_temp` và invalid upmap giảm mapping bất hợp lệ/không còn mục tiêu; chúng có thể gây remap/recovery khi state thực sự tồn tại, nên cần quan sát chứ không coi là log-only.

**Mixed phase.** Benefit accounting phụ thuộc MON leader target. OSDMap mới sau proposal được toàn cluster tiêu thụ; không có format mới trong nhóm fix này. Chênh lệch mapping code local có thể làm warning/timeout khác nhau giữa daemon/tool base và target nhưng authoritative map vẫn qua MON.

**Hành động.** Trước upgrade, kiểm monitor DB size, retained OSDMap range, pending PG merge, `pg_temp` và upmap exceptions. Sau canary/leader switch, xác minh trim tiến và recovery không tăng bất thường. Không chủ động merge PG hoặc chạy balancer lớn trong cùng cửa sổ nếu không cần.

**Đánh giá.** Rủi ro **trung bình-cao khi có state liên quan**, confidence **high**.

### MON-007 — Stretch cluster có thay đổi MonMap, tiebreaker và CRUSH riêng

**Owner/evidence.** Inventory `1514`, `1518`–`1520`, `1583`–`1584`:

- `de8ae3cd31c4512239b12fc843e3ed3e70d0a5ea`: command thay tiebreaker mới.
- `d4be0bade7f1381254db30394639154615edb2ce`: không cho remove tiebreaker trực tiếp khỏi MonMap.
- `d405828d0443c1dbb6557dd495d3a67b2ca028a1`: cập nhật `MonMap::last_changed` cho stretch commands.
- `e93a38983436f8840b534a1feb1f72ba5b5fa5ed`: không bump `mon_info_t` compat version sai trong stretch mode.
- `a569c37abb41253b2a87a0c1ca00d254822cb195`: chọn default CRUSH rule hợp lý khi tạo pool ở stretch mode.
- `f40269ed40f0519f4be359a6d9fee2e41ad761c6`: kiểm unequal weights và bucket count khác 2; `cbbb3589cf0998014e584ce1c0c018fa42e6e6cc` thêm guard trước recovery stretch mode.

**Tác động.** Các hunk này thay state/control path chứ không chỉ CLI wording. Với stretch deployment, tiebreaker identity, bucket topology, weights, default rule và transition degraded/recovery đều có thể ảnh hưởng quorum/placement trong lúc site hoặc MON restart.

**Mixed/full phase.** Không thay stretch topology trong mixed MON/OSD rollout. Nếu phải replace tiebreaker, dùng command target và xác minh MonMap epoch/`last_changed`; tránh remove-add thủ công. Pool tạo mới sau target có thể chọn rule khác base theo stretch-aware default, nên automation phải chỉ định rule khi cần tính xác định.

**Hành động.** Chỉ áp dụng nếu As-Is xác nhận stretch mode. Chụp MonMap, tiebreaker, CRUSH rule, bucket count/weights và recovery state; test một site outage/failback trong lab. Nếu không dùng stretch, finding này là conditional và không cần test production.

**Đánh giá.** Rủi ro **cao theo điều kiện**, confidence **high**.

### MON-008 — Pool/autoscaler controls thay validation và state khi operator gọi command

**Owner/evidence.** Inventory `1501`–`1502`, `1513`, `1519`–`1520`, QA `1062`–`1066`:

- `a5b24bce105111a8c60d78bee57e108c109ebadc`, `b8da2e893478bee7f0101d4eb51d9ec3f49e944d`, `12bef02faa4a3621f821c653e52741f96cfa94d1`: thêm `pg_num_max`, create argument và từ chối `pg_num` ngoài min/max.
- `d41ef37be9be70d242296d8b6b83ed3af4b4b588`: pool-create `--bulk`/bulk flag.
- `117a82869ff04ed2196c98e997fde4d917d8a137` và `1eb82bbe3311a607f454d9d9bee2441000eaf1a3`: sửa range command và từ chối `target_size_ratio < 0`.
- `f1bc29056794aad38a5cbf87fdf7ce7419f3b7ef` và `7891368a7a498ba5930404cbbcd3ccc2231dd5ad`: chặn monitor-managed/pool snapshots trên CephFS data pool.
- `99249c49671872219715c82edbdcebc57ba5ac3b`: unknown `osd pool get` option trả `-EINVAL`.

**Tác động.** Đây không phải auto-mutation khi daemon restart. Nó kích hoạt khi operator/autoscaler/automation tạo pool, resize PG, set ratio/flags hoặc tạo pool snapshot. Target có thể từ chối command base từng chấp nhận, hoặc tạo pool với property mới; automation cần coi non-zero return là failure thật.

`pg_num_max` và bulk flag có thể thay lộ trình autoscale/placement sau upgrade. Chặn snapshot trên CephFS pool là safety correctness, nhưng runbook cũ dựa vào pool snapshot sẽ fail và không nên bypass.

**Hành động.** Freeze pool topology/balancer changes trong rolling window nếu không cần; inventory min/max/autoscale/bulk/ratio; test idempotency và error handling của automation. QA rows là bằng chứng support, không phải runtime finding độc lập.

**Đánh giá.** Rủi ro **trung bình theo điều kiện**, confidence **high**.

### MON-009 — Proposal races của MGR và health-store không trim ảnh hưởng control-plane stabilization

**Owner/evidence.** Inventory `1503`, `1506`–`1509`, `1523`–`1524`, `1517`:

- `0d5f436fbbaf1aff63231c8f1e6a75221cdf2711`, `30d1463eb77268b4245e6a69ba10b8d1ef361a4d`, `70254f324180949f28f674da463fec66b0f53d5b`, `046af0b6f21616edf2b9e23bec46128be920f4a6`, `c9be0bc213bbb79c25844e9a8a26113adde6ec32`: sửa race/return/proposal cho `mgr fail`, beacon, active change và batched MgrMap/OSDMap.
- `efcddbbd36dd83286df78e3d5064ba638b77d5a5`: `HealthMonitor::check_mutes()` bắt đầu với `changed=false`; base luôn proposal health, làm `maybe_trim` bị chặn và health store tăng không giới hạn.

**Tác động.** MGR active/failover thường thay đổi quanh upgrade; proposal sai hoặc lặp có thể kéo dài convergence và làm module/autoscaler unavailable. Health-store growth là rủi ro dung lượng MON DB: target ngừng tạo proposal giả khi mute không đổi, cho phép trim chạy, nhưng chỉ sau khi target leader/service active.

**Hành động.** Preflight dung lượng MON store và free disk trước mọi restart; nếu store đã lớn, không giả định upgrade tự compact ngay. Trong rollout, theo dõi Paxos proposal rate, health epochs/trim, MGR active/standby và module readiness. Tránh `mgr fail` thủ công trùng đúng lúc MON leader election nếu không phải test có kiểm soát.

**Đánh giá.** Rủi ro **trung bình-cao**, confidence **high**.

### MON-010 — Hai tool được sửa nhưng chỉ thuộc đường recovery thủ công

**Owner/evidence.** Inventory `2563`, `2591`:

- `0795d44c1939b13adc3788b3bf9314d9866ab1df`: `ceph-monstore-tool` dùng Paxos `first_committed/last_committed` đủ lớn khi rebuild.
- `9af4d681fb83030ba502a3392bbea8f4c7fab23a`: rebuild monitor store kèm rotating CephX keys.
- `acd845f8ba0f409c5ba56d54a04ae7988367a49e`: `osdmaptool` tránh segfault khi có OSD down.

**Tác động.** Không tool nào tự chạy trong upgrade bình thường. Nếu MON store phải rebuild, thiếu rotating keys hoặc epoch không phù hợp có thể làm auth/Paxos state không usable; fix target làm recovery đáng tin hơn nhưng thao tác vẫn có blast radius rất cao. `osdmaptool` fix giúp offline inspection/map manipulation khi down OSD tồn tại.

**Hành động.** Chỉ dùng binary/tool đúng target trên bản sao verified; backup store/map, ghi checksum và có peer review. Không biến monstore rebuild hoặc map rewrite thành bước preventive của runbook.

**Đánh giá.** Rủi ro runtime mặc định **không áp dụng**; severity **cao nếu recovery**, confidence **high**.

### MON-011 — OSD reconnect có thể nhận config mask theo CRUSH location khác base

**Owner/evidence.** Inventory `1493`–`1495` (`ConfigMap`/`ConfigMonitor`, disposition `mixed`):

- `7059a108807678cb3a4e97f71cec60d6e4d25339`: trong `ConfigMonitor::refresh_config()`, target gọi `get_full_location()` bằng OSD entity trước khi `generate_entity_map()`. Base chỉ dựng location từ `remote_host`, nên config mask theo host/CRUSH location có thể không match đúng cho OSD session.
- `0ab3058f7b3a394b5f1995d0484fb57ac438fd62`: normalize khoảng trắng thành underscore cho `config help/get/set/rm`.
- `7f1d13d2abd6590ec98f566d28c4810558227ac8`: JSON `config dump` trả `localized_name` của masked option thay vì normalized option name.

**Tác động upgrade.** Khi một OSD reconnect vào MON target trong rolling restart, config mask theo `location:`/host có thể bắt đầu áp dụng đúng nơi mà base bỏ qua hoặc resolve khác. Nếu masked value điều khiển recovery, scheduler, memory hoặc device behavior, effective config đổi mà stored config không hề được sửa trong cửa sổ upgrade. Hai thay đổi tên key không đổi daemon data path trực tiếp nhưng có thể làm automation preflight/config-diff đọc hoặc ghi key khác trước.

**Mixed/full/rollback.** Behavior phụ thuộc ConfigMonitor/MON xử lý session, không chỉ version của OSD. Trong mixed MON phase, leader/session path nào phục vụ reconnect quyết định effective map; sau full MON target thì resolution đồng nhất. Rollback về base có thể làm location-masked override ngừng match như trước, nên phải so effective config chứ không chỉ `config dump` thô.

**Hành động.** Inventory mọi config entry có location/device-class mask và mọi parser dùng JSON `config dump`; canary một OSD ở mỗi CRUSH host/class, so effective values trước/sau reconnect. Chuẩn hóa automation để chấp nhận localized name và không dựa vào khoảng trắng mơ hồ.

**Đánh giá.** Rủi ro **trung bình theo điều kiện**, confidence **high**; applicability phụ thuộc cluster có masked config hoặc parser automation hay không.

## 5. Các thay đổi không cần phân tích sâu riêng

- `src/mon/CMakeLists.txt` chỉ điều chỉnh build composition; không tìm thấy đường thay package runtime chính thức hoặc artifact compatibility riêng trong endpoint diff.
- Các thay đổi formatting, thêm log/debug, wording/error message và helper refactor không được nâng thành finding nếu không đổi state/branch quan trọng.
- QA/workunit/test rows chứng minh intended behavior cho config, autoscaler, pool ops, election và PGMap; chúng không tự tác động cluster.
- `MonCap`, `MgrMap/MgrStatMonitor` và `PGMap` có hunk hữu ích nhưng được gộp vào finding tương ứng hoặc đánh dấu mixed, thay vì tạo finding theo từng file. `ConfigMap/ConfigMonitor` đã được giữ ở MON-011 vì effective config có thể đổi khi OSD reconnect.

## 6. Phân kỳ mixed/full/rollback

- **MON mixed:** leader quyết định phần lớn proposal behavior. Đợi quorum/election ổn định và service Paxos catch-up sau từng node; không thay MonMap topology cùng lúc nếu không cần.
- **OSD mixed:** không thay `require-osd-release` chỉ vì patch rollout; không tạo range blocklist; theo dõi map decode, PG remap, `pg_temp`, upmap và retained epochs.
- **Full MON/OSD:** xử lý `OSD_UPGRADE_FINISHED` bằng checkpoint riêng, rồi mới bật capability/state mới. Pool/stretch changes cũng nên tách khỏi binary rollout.
- **Rollback:** flag `pacific` không chặn `16.2.15` → `16.2.5`; rào cản cần rehearsal là state/capability mới như range blocklist, FSMap và effective masked config. Giữ MonMap/OSDMap/CRUSH dumps và config snapshot từ trước rollout.

## 7. Coverage/disposition ledger

Mỗi dòng CSV có đúng một disposition; các nhóm không chồng lặp và tổng bằng 52:

- `material` — 25 dòng: `1490`–`1491`, `1496`–`1500`, `1504`–`1505`, `1507`–`1508`, `1511`–`1512`, `1514`–`1518`, `1521`–`1524`, `1583`–`1585`.
- `conditional` — 8 dòng: `1501`–`1502`, `1510`, `1513`, `1519`–`1520`, `2563`, `2591`. Tác động phụ thuộc command, feature/state hoặc offline recovery; các finding tương ứng vẫn được phân tích vì severity có thể cao.
- `mixed` — 6 dòng: `1493`–`1495`, `1503`, `1506`, `1509`. Mỗi file trộn hunk upgrade-relevant với refactor/log/support.
- `support` — 12 dòng: `395`–`397`, `1061`–`1066`, `2496`–`2498`. Test/QA dùng để xác nhận intent và nêu test gap, không phải runtime diff độc lập.
- `trivial` — 1 dòng: `1492`.

Tổng: `25 + 8 + 6 + 12 + 1 = 52`. `priority` và `review_mode` trong CSV là routing cơ học; ledger là kết luận sau evidence review.

## 8. Validation đề xuất — chưa chạy

1. **MON rolling:** restart lần lượt follower/leader trong lab, kiểm quorum/election epoch, rank, `quorum_age`, connection scores, session count và Paxos catch-up.
2. **Range blocklist:** xác nhận add CIDR bị feature-gate trong mixed matrix, rồi add/list/enforce/expire/remove sau full upgrade; thử decode/rollback trên bản sao map.
3. **Release gate:** nếu As-Is flag dưới Pacific, giữ OSD `v16.2.5` và một legacy-version fixture riêng, kiểm health/rejoin; xác nhận flag Pacific vẫn cho base endpoint rejoin nhưng chặn OSD pre-Pacific như dự kiến.
4. **Auth:** gây leader change trong chu kỳ rotating key và auth retry; kiểm không phân phối key trước commit và MonClient target reopen sau `-EAGAIN`.
5. **CephFS:** replay old FSMap epoch, restart/failover active/standby-replay và xác minh compat/damaged state.
6. **PG/placement:** trên pool test thực hiện PG merge, theo dõi `last_epoch_clean`, OSDMap trim, stale `pg_temp`/upmap cleanup và recovery load.
7. **Stretch-only:** nếu có, test tiebreaker replacement, site degrade/recover, rule selection, bucket/weight validation và `last_force_op_resend`.
8. **MGR/store:** failover MGR có kiểm soát, theo dõi proposal rate/autoscaler readiness; tạo/expire health mute và xác minh health store trim/free space.
9. **Masked config:** với OSD ở các host/class đại diện, so effective config trước/sau reconnect vào MON target; diff cả JSON/text output của automation.
10. **Offline tools:** chỉ trên snapshot copy; rebuild monstore và inspect OSDMap có down OSD, sau đó validate epoch/key/map trước khi cân nhắc recovery thật.

## 9. Giới hạn và kết luận

Chưa có MonMap/OSDMap/CRUSH dump, daemon versions, feature bits, monitor-store size, stretch/CephFS usage, pool automation hoặc lịch sử PG merge của cluster. Vì thế báo cáo phân biệt rõ activation và severity thay vì giả định mọi finding đều áp dụng.

Runbook nên ưu tiên: **quorum-safe MON rollout; không tạo range blocklist trong mixed phase; chỉ xử lý flag dưới Pacific sau khi loại trừ OSD legacy; audit masked config; và kiểm MON DB/FSMap/placement state trước khi restart**. Các diff còn lại vẫn được bảo toàn đầy đủ trong CSV nhưng không được phóng đại thành rủi ro nâng cấp nếu chỉ là build, test, logging hoặc command không được gọi.
