# 14 — Security cross-reference và CVE boundary

> **Trạng thái:** hoàn thành evidence review cho owner `14-security-cross-reference`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), lấy endpoint net diff trực tiếp trong `ceph16.2.15/ceph` với `--find-renames`.
>
> **Ledger đầy đủ:** [14-security-cross-reference.csv](./14-security-cross-reference.csv). Report này chỉ phân tích source và thiết kế validation; chưa chạy test hay thao tác trên cluster thật.

## 1. Kết luận điều hành

Owner `14` có **8/8 dòng**, tất cả là documentation được thêm mới (`A 8`, `+518/-0`). Không dòng nào là runtime implementation. Bốn advisory cho CVE-2021-20288, CVE-2021-3509, CVE-2021-3524 và CVE-2021-3531 được đưa vào cây tài liệu trong range, nhưng fix tương ứng đã có từ Pacific `16.2.1` hoặc `16.2.4`; cả hai tag đều là ancestor của base `v16.2.5`. Vì vậy đây là **documentation delta, không phải security delta giữa hai endpoint**.

Ba CVE-labelled runtime change trong evidence set của range này nằm ở owner khác:

- **CVE-2022-0670** — fix từ Pacific `16.2.10`, điều kiện rất hẹp: OpenStack Manila xuất native CephFS trên cluster có lịch sử nâng từ Nautilus hoặc cũ hơn. Owner chính là [CEPHFS-005](./11-cephfs-mds.md); target binary không tự sửa mọi CephX key đã cấp sai path trước đó.
- **CVE-2022-3650** — `ceph-crash` bỏ quyền root và chạy bằng user/group `ceph`. Owner chính là [VAL-001](./15-upgrade-validation.md).
- **CVE-2023-43040** — RGW sửa bucket validation đối với S3 Browser POST policy. Owner chính là [RGW-001](./12-rgw.md).

Kết luận “ba CVE-labelled runtime change” chỉ áp dụng cho tập bằng chứng đã kiểm: endpoint diff, commit history có nhãn CVE và release notes chính thức của Pacific trong range. Nó **không phải** tuyên bố rằng mọi CVE của dependency, distro package, container image hoặc downstream patch đã được bao phủ.

## 2. Phạm vi, ownership và độ phủ

Changed-file rows thuộc owner `14` chỉ gồm advisory/index/process documentation dưới `doc/security/`. Runtime rows được giữ độc quyền ở report thành phần để partition của inventory không bị trùng. Report này cross-reference kết luận và validation gate; không chép lại row của owner `11`, `12` hay `15`.

Mỗi dòng đã được đọc ở endpoint target, đối chiếu commit tạo/sửa tài liệu, lịch sử tag và — khi có runtime fix trong range — code/test/owner report liên quan. Final dispositions trong CSV:

| Disposition | Số dòng | Ý nghĩa |
| --- | ---: | --- |
| `material` | 0 | Owner `14` không sở hữu runtime implementation |
| `conditional` | 0 | Conditional runtime rows nằm ở owner thành phần |
| `support` | 2 | Advisory/index hỗ trợ SEC-003 / CEPHFS-005 |
| `trivial` | 6 | Bốn advisory có fix trước base, cộng navigation/process docs |
| `mixed` | 0 | Không có file chứa cả runtime và documentation hunk |
| **Tổng** | **8** | Khớp ledger 8/8 dòng |

Các cột mở rộng của CSV là `upgrade_disposition`, `finding_id`, `disposition_reason`, `symbols`, `commit_shas`, `evidence_status`; 21 cột gốc vẫn là prefix bất biến của master inventory.

## 3. Security boundary theo endpoint

| ID | Security item | Base `v16.2.5` → target `v16.2.15` | Điều kiện áp dụng / phase | Owner chính |
| --- | --- | --- | --- | --- |
| `SEC-001` | CVE-2021-20288, CephX `global_id` reclaim | Không có runtime delta; fix từ `16.2.1` | Carry-forward hygiene cho client cũ; không phải finding của patch upgrade này | `14` exclusion |
| `SEC-002` | CVE-2021-3509 / 3524 / 3531 | Không có runtime delta; fix từ `16.2.4` | Dashboard hoặc RGW exposure không đổi bởi endpoint diff này | `14` exclusion |
| `SEC-003` | CVE-2022-0670, Manila/native CephFS path restriction | Base chưa có fix, target có fix | Historical topology; mixed active-mgr state và audit key sau upgrade | [CEPHFS-005](./11-cephfs-mds.md) |
| `SEC-004` | CVE-2022-3650, `ceph-crash` privilege drop | Base có thể tiếp tục bằng root; target gọi `drop_privs()` | Host chạy `ceph-crash`; có hiệu lực khi process target khởi động | [VAL-001](./15-upgrade-validation.md) |
| `SEC-005` | CVE-2023-43040, RGW Browser POST policy | Base thiếu bucket check đúng chỗ; target có fix | S3 Browser POST; mọi serving RGW cũ đều còn exposure | [RGW-001](./12-rgw.md) |

Không dùng CVSS trong report vì source Ceph được kiểm không cung cấp một thang điểm nhất quán cho cả năm mục, và điểm số không thay thế kiểm tra applicability của deployment.

## 4. Kết quả sàng lọc owner `14`

### SEC-001 — CVE-2021-20288 là fix trước base

**Evidence.** Target advisory [CVE-2021-20288.rst](../../ceph16.2.15/ceph/doc/security/CVE-2021-20288.rst) ghi Pacific `16.2.1+` là fixed. [Release note chính thức 16.2.1](https://ceph.io/en/news/blog/2021/v16-2-1-pacific-released/) mô tả secure `global_id` reclaim và hai health alerts dành cho client chưa được patch. Git ancestry xác nhận `v16.2.1` là ancestor của base `v16.2.5`. Commit `93fbac498ccf37733ba115b8b6586d3ab9d70a53` chỉ thêm advisory vào docs trong comparison range.

**Trước → sau / mixed-version.** Cả hai endpoint đã nằm sau fixed tag, nên report không tìm thấy runtime transition để gán cho upgrade `16.2.5 → 16.2.15`. Health alerts hoặc cấu hình `auth_allow_insecure_global_id_reclaim` vẫn là hygiene cần xem xét nếu còn client cũ, nhưng không được trình bày như target-only fix.

**Disposition.** `trivial` cho endpoint comparison; confidence `high` nhờ official release mapping, target advisory và tag ancestry. Nếu cluster vẫn báo client reclaim không an toàn, xử lý đó là As-Is security workstream riêng trước khi harden cấu hình.

### SEC-002 — ba advisory 16.2.4 cũng là fix trước base

Target docs [CVE-2021-3509.rst](../../ceph16.2.15/ceph/doc/security/CVE-2021-3509.rst), [CVE-2021-3524.rst](../../ceph16.2.15/ceph/doc/security/CVE-2021-3524.rst) và [CVE-2021-3531.rst](../../ceph16.2.15/ceph/doc/security/CVE-2021-3531.rst) đều ghi Pacific `16.2.4+` là fixed. [Release note chính thức 16.2.4](https://ceph.io/en/news/blog/2021/v16-2-4-pacific-released/) map lần lượt Dashboard cookie injection, RGW CORS header injection và Swift malformed-URL denial of service tới release này. Git ancestry xác nhận `v16.2.4` là ancestor của base.

Do đó ba row advisory là documentation additions từ commit `93fbac498ccf37733ba115b8b6586d3ab9d70a53`, không phải code delta giữa endpoint. Chúng được giữ với `SEC-002` để không làm mất audit trail, nhưng disposition là `trivial`, risk cho **upgrade delta** là none và confidence `high`. Việc xác minh provenance của package `v16.2.5` đang chạy vẫn là prerequisite chung nếu binary thực tế không khớp Git tag.

## 5. Cross-owner findings trong range

### SEC-003 — CVE-2022-0670 / CEPHFS-005

**Evidence.** Target advisory [CVE-2022-0670.rst](../../ceph16.2.15/ceph/doc/security/CVE-2022-0670.rst) và [release note chính thức 16.2.10](https://www.ceph.io/en/news/blog/2022/v16-2-10-pacific-released/) giới hạn applicability ở OpenStack Manila cung cấp native CephFS trên cluster đã nâng từ Nautilus hoặc cũ hơn. Code commits `1d7e95ba3a34436ea0dee4042dc41db884a283b4` và `cf41172621f7462aef745ad72fb1a9b0512f11ad` sửa legacy subvolume discovery; `5250508f45675b2552928bcef896ee4a8676c38b` thêm QA upgrade coverage. Phân tích code chính nằm ở [report 11, CEPHFS-005](./11-cephfs-mds.md).

**Before/after và activation.** Base có thể discover legacy subvolume sai trong đúng historical topology; target có fix. Nếu cluster chưa từng từ Nautilus-or-earlier hoặc không dùng Manila native CephFS thì finding không áp dụng. Fix tự có khi active mgr volumes code đã target, nhưng các CephX keys đã cấp trước đó không được chứng minh là tự sửa.

**Mixed/full effect.** Trong rolling phase, kết quả command phụ thuộc version của active mgr; failover về mgr cũ có thể đưa logic base trở lại. Sau khi tất cả mgr liên quan ở target, discovery path đã fix, nhưng audit entity-to-subvolume path vẫn là action riêng.

**Risk/confidence.** Security consequence cao khi điều kiện khớp; applicability conditional; confidence `high`. Owner-14 rows `CVE-2022-0670.rst` và `cves.rst` là `support`, không nhân đôi runtime rows.

### SEC-004 — CVE-2022-3650 / VAL-001

**Evidence.** Commit `d2a9a539d72e01750dcc245a11962fe574777cc0` (`src/ceph-crash.in`) được [release note chính thức 16.2.13](https://ceph.io/en/news/blog/2023/v16-2-13-pacific-released/) map tới CVE-2022-3650. Base không có `drop_privs()`; target, khi start với UID 0, xóa supplementary groups rồi chuyển GID/UID sang account `ceph`. Nếu lookup hoặc privilege drop thất bại, process log lỗi và thoát. Phân tích/ledger chính nằm ở [report 15, VAL-001](./15-upgrade-validation.md).

**Activation và phase.** Chỉ tác động host chạy `ceph-crash`; có hiệu lực khi process target được khởi động lại. Đây là host-local behavior, nên mixed cluster có thể đồng thời có host cũ còn chạy root và host mới đã drop privilege.

**Operational effect.** Target giảm quyền của long-running scraper, nhưng account/group hoặc quyền đọc crash directory sai có thể khiến target process thoát hoặc không scrape được. Package/staging validation phải chứng minh cả effective UID/GID và end-to-end crash submission; chỉ thấy service “active” là chưa đủ.

**Risk/confidence.** Security relevance có bằng chứng trực tiếp; deployment applicability conditional; confidence `high`. Không có row owner `14` cho finding này.

### SEC-005 — CVE-2023-43040 / RGW-001

**Evidence.** Commit `479976538fe8f51edfea597443ba0c0209d3f39f` thay đổi `RGWPostObj_ObjStore_S3::get_params()`; [release note chính thức 16.2.15](https://ceph.io/en/news/blog/2024/v16-2-15-pacific-released/) map fix tới CVE-2023-43040. Code, test và policy semantics được phân tích tại [report 12, RGW-001](./12-rgw.md).

**Before/after và activation.** Base có thể để form field ảnh hưởng bucket value dùng khi check signed POST policy; target gắn bucket canonical sau khi parse fields. Chỉ áp dụng khi endpoint phục vụ S3 Browser POST signed policy.

**Mixed/full effect.** Một RGW base còn nhận traffic vẫn giữ behavior cũ; security closure chỉ đạt khi mọi serving instance đã target hoặc bị drain. Không có config toggle để biến target fix thành remediation cho request đã xử lý trước đó.

**Risk/confidence.** Security consequence cao khi Browser POST tồn tại; applicability conditional; confidence `high` từ endpoint diff, commit và official release mapping. Không có row owner `14` cho finding này.

## 6. Validation scenarios đề xuất

Các scenario sau là acceptance design, chưa được thực thi và không cho phép tự động thay đổi production:

| Scenario | Preconditions / phase | Action và quan sát | Expected result | Failure / stop signal |
| --- | --- | --- | --- | --- |
| `SEC-V01` — provenance boundary | Artifact/package inventory trước rollout | Đối chiếu build SHA/tag của MON, Dashboard và RGW với source provenance | Base thực tế không cũ hơn các fixed tags `16.2.1/16.2.4` | Binary provenance không xác định hoặc downstream patch lệch |
| `SEC-V02` — Manila historical audit | Chỉ khi SEC-003 applicability khớp; pre + mixed + full | Inventory Manila backend, upgrade history, CephX entity→subvolume path; canary negative access | Không entity nào vượt path cap; kết quả không đổi khi active mgr failover | Key không truy vết được, access ngoài subvolume, hoặc mgr cũ lại active |
| `SEC-V03` — ceph-crash privilege | Package/staging host có account `ceph`; sau service restart | Quan sát UID/GID/groups của process và submit một synthetic crash trong môi trường cô lập | Process chạy bằng `ceph`, đọc được intended crash path và upload thành công | Process thoát ở `drop_privs`, permission denied hoặc crash không được archive |
| `SEC-V04` — Browser POST negative policy | RGW staging; mixed rồi full; Browser POST enabled | Gửi valid canary và bucket-mismatch/tampered form; correlate instance version | Valid request giữ compatibility; mismatched policy bị từ chối trên mọi serving RGW | Request tampered được chấp nhận hoặc traffic còn tới base RGW |
| `SEC-V05` — closure | Sau rollout | Chứng minh không còn mgr/RGW/ceph-crash process base trong relevant path và lưu test evidence | Cross-owner gates đều có artifact, timestamp và owner sign-off | Thiếu version evidence hoặc validation chỉ chạy trên một instance |

Không áp dụng test SEC-V02/03/04 lên production nếu chưa có test-data boundary, rollback/stop condition và owner phê duyệt riêng.

## 7. Trivial/support changes

Đã screen đủ **8/8 dòng**:

- **2 `support`:** advisory CVE-2022-0670 và target security index trực tiếp hỗ trợ SEC-003 / CEPHFS-005. Chúng không tự thay đổi runtime.
- **6 `trivial`:** bốn advisory có fix trước base, security navigation page và vulnerability-management process. Chúng bổ sung tài liệu/đường dẫn/quy trình, không thay đổi delivery, compatibility hoặc daemon behavior của endpoint.

Không có row `material`, `conditional` hay `mixed` trong owner `14`. Các runtime security findings vẫn được tính ở owner `11`, `12` và `15`, đúng partition semantics.

## 8. Giới hạn và quyết định

- Chưa có As-Is topology, Manila history, Browser POST usage, package provenance, account/permission state hoặc traffic routing; vì vậy report không đưa GO/NO-GO production.
- Repository tests và commit tests được đọc, chưa chạy. Validation table là kế hoạch cho môi trường được cấp quyền riêng.
- Official Ceph release pages xác minh mapping upstream; chúng không bao phủ security bulletin của distro/vendor, image layer, Python/system dependency hoặc downstream patch.
- Không suy CVE applicability chỉ từ version string. SEC-003/004/005 cần xác minh feature, process và routing condition tương ứng.

Security acceptance cho upgrade chỉ có thể đóng sau khi: provenance xác nhận đúng artifacts; SEC-003 được loại trừ hoặc hoàn tất audit; mọi `ceph-crash` target qua privilege/submission canary; và nếu dùng Browser POST, không RGW base nào còn nhận traffic cùng negative policy test đạt.
