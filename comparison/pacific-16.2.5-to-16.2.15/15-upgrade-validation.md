# 15 — Cross-component validation, release-note reconciliation và residual gaps

> **Trạng thái:** hoàn thành static analysis cho owner `15-upgrade-validation`.
>
> **Hai đầu so sánh:** `v16.2.5` (`0883bdea7337b95e4b611c768c0279868462204a`) → `v16.2.15` (`618f440892089921c3e944a991122ddc44e60516`), net diff lấy từ `ceph16.2.15/ceph` với `--find-renames`.
>
> **Ledger đầy đủ:** [15-upgrade-validation.csv](./15-upgrade-validation.csv). Báo cáo này không ghi lại danh sách file trong Markdown và không xác nhận bất kỳ test runtime/live-cluster nào đã chạy.

## 1. Phạm vi, phương pháp và độ phủ

Owner `15` giữ các QA artifacts liên thành phần, release-note material và source/tool residual không thuộc owner chuyên môn hơn. CSV có đúng **266 dòng**, giữ nguyên 21 cột prefix của master inventory và bổ sung sáu cột phân tích: `upgrade_disposition`, `finding_id`, `disposition_reason`, `symbols`, `commit_shas`, `evidence_status`.

- Git status: `A 58`, `D 34`, `M 168`, `R 6`.
- Text churn: `+22,225 / -47,282`; có `5` binary rows.
- Reading priority: `P1 28`, `P2 238`.
- Initial review mode: `deep 12`, `conditional 16`, `support 20`, `reference-only 218`.
- Final disposition: `material 2`, `conditional 13`, `support 37`, `trivial 211`, `mixed 3`; tổng bằng `266`.

Mỗi row đã được screen từ endpoint hunk/special metadata và commit history. Chỉ behavior có causal path tới rollout, compatibility, security hoặc acceptance mới được promote. Test recipe được coi là **thiết kế coverage**, không phải bằng chứng test đã chạy/pass. Release-note text chỉ được dùng khi version scope và endpoint code tương ứng cùng khớp.

## 2. Kết luận điều hành

| ID | Kết luận quyết định | Activation | Risk | Confidence |
| --- | --- | --- | --- | --- |
| `VAL-001` | `ceph-crash` bỏ quyền root và chạy bằng user/group `ceph`; đây là runtime fix của CVE-2022-3650 | Lần process target khởi động | Security material; availability conditional theo account/path permissions | high |
| `VAL-002` | `cls/cmpomap` coi empty stored U64 là `0` thay vì decode error; behavior phụ thuộc OSD phục vụ request trong mixed phase | U64 compare trên empty omap value | Correctness/compatibility conditional | high |
| `VAL-003` | Mount helper dùng formatter có IPv6 brackets cho địa chỉ MON | Target `mount.ceph` + MON IPv6 | Client continuity conditional | high |
| `VAL-004` | Target CLI parser hiểu msgr-prefixed/range-blocklist address và misordered named args tốt hơn | Dùng target CLI với các input này | Operator/CLI compatibility thấp | high |
| `VAL-005` | `ceph-dencoder` chuyển sang plugin modules; binary và module package phải đồng bộ | Offline decode/incident workflow | Validation/tooling conditional | high |
| `VAL-006` | Pacific p2p recipe bắt đầu đúng `v16.2.5`, nhưng có intentional filters và không kèm run result | Khi chọn suite làm acceptance evidence | Coverage gap, không phải runtime risk | high |
| `VAL-007` | Nautilus/Octopus→Pacific suites là evidence gián tiếp; không chứng minh riêng endpoint `16.2.5→16.2.15` | Khi tái sử dụng legacy suite | Evidence applicability | high |
| `VAL-008` | `PendingReleaseNotes` trộn notice đúng range, nội dung `>=17` và text kế thừa trước base; phải reconcile từng claim với history/code | Khi lập checklist từ release notes | False-positive/false-negative analysis risk | high |

Không có đủ As-Is inventory hoặc execution evidence để đưa ra production GO/NO-GO.

## 3. Findings

### VAL-001 — `ceph-crash` drop privileges, CVE-2022-3650

**Evidence.** CSV row `1101`, `src/ceph-crash.in`; symbols `drop_privs()`, `main()`, `scrape_path()`. Commit `d2a9a539d72e01750dcc245a11962fe574777cc0` ghi rõ CVE-2022-3650. Finding bảo mật được cross-reference tại [`SEC-004`](./14-security-cross-reference.md#sec-004--cve-2022-3650--val-001).

**Trước → sau.** Base process tiếp tục chạy với UID/GID ban đầu, thường là root. Target, nếu khởi động với UID 0, resolve user/group `ceph`, xóa supplementary groups, gọi `setgid()` rồi `setuid()`. Không drop được quyền thì log lỗi và exit `1`; scrape exception được log thay vì làm process im lặng thoát. Cùng file còn có stderr/log-level cleanup, vì vậy row có disposition `mixed`, không phải mọi hunk đều security-material.

**Activation và mixed version.** Có hiệu lực ở lần `ceph-crash` target được start/restart trên từng host; không cần on-disk migration. Host còn chạy script/base process vẫn có behavior cũ. Account `ceph` thiếu hoặc crash directories không đọc/ghi được sau khi hạ quyền có thể làm mất crash-posting trên host đó, nên package/account/path ownership là precondition thực tế.

**Impact.** Security material, availability/observability conditional. Risk cao nếu service vẫn chạy root hoặc target không thể post crash; confidence `high` từ endpoint code và commit mapping. Không tìm thấy dedicated repository test cho privilege path và không có service runtime test nào được chạy.

### VAL-002 — Empty U64 semantics của `cls/cmpomap` thay đổi trong mixed phase

**Evidence.** CSV rows `1189–1190`, `src/cls/cmpomap/{client.h,server.cc}`; symbols `compare_values_u64()`, `cmp_vals`, `cmp_set_vals`, `cmp_rm_keys`. Implementation và test cùng commit `01e4c1f3f96949d8ed55de9c49c138e3d8f1d808`; supporting rows `1047` và `2408`.

**Trước → sau.** Base cố decode mọi stored U64 value; buffer rỗng dẫn tới `-EIO` hoặc comparison failure. Target khởi tạo RHS bằng `0`, chỉ decode khi buffer có length, rồi so sánh bình thường. Malformed non-empty data vẫn giữ error behavior.

**Mixed-version evidence.** Commit `8e290c03193bfba743b1b110dad614748494d97e` sửa workunit để loại riêng `CmpOmap.cmp_vals_u64_invalid_default`, với comment rằng testcase đổi từ 16.2.6 và đã fail trong Pacific p2p upgrades. Điều này chứng minh expected result phụ thuộc serving OSD version; nó không chứng minh wire incompatibility. Trong rolling phase, cùng logical operation có thể nhận base hoặc target semantics tùy primary/OSD xử lý request.

**Applicability.** Chỉ khi workload trực tiếp/gián tiếp dùng `cls/cmpomap` U64 comparisons trên empty omap values. Behavior tự đổi khi OSD target phục vụ request; không có operator migration. Risk correctness trung bình theo điều kiện, confidence `high`. Repository tests đã đọc nhưng chưa chạy.

### VAL-003 — IPv6 MON address của mount helper

**Evidence.** CSV row `1526`, `src/mount/conf.cc`, `mount_ceph_get_config_info()`; commit `766edcc66e43ed1658afd823aaa4d24950f0e0bf`.

**Trước → sau.** Base ghép `ip_only_to_str() + ':' + port`, có thể tạo chuỗi IPv6 không có brackets. Target gọi `ip_n_port_to_str()`, tạo dạng `[IPv6]:port` phù hợp cho mount helper.

**Activation/mixed version.** Chỉ client host dùng target `mount.ceph` thay đổi; daemon rolling order không kích hoạt. IPv4 và deployment không dùng MON IPv6 không áp dụng. Risk continuity trung bình cho client IPv6, confidence `high`; commit không thêm test riêng cho mount helper và chưa có canary mount được chạy.

### VAL-004 — Target CLI parser chấp nhận address/named-argument forms mới

**Evidence.** CSV row `1625`, `src/pybind/ceph_argparse.py`; `CephIPAddr.valid()`, `CephEntityAddr.valid()`, `validate()`; commits `96293ec1725a7854bd7b87715cd35cd3cc6b8ea4` và `66383d8e5331a5eb633d8b189c6cc7f916a3ae71`. Row `2514` có relevant blocklist tests lẫn phần lớn mechanical conversion từ nose sang unittest, nên disposition `mixed`.

**Trước → sau.** Target tách prefix `v1:`, `v2:`, `any:`, xử lý nonce sau bracketed IPv6 và không báo thiếu required positional argument nếu argument đó đã được cung cấp sớm dưới dạng named argument. Đây là local CLI validation; không đổi persistent cluster format.

**Activation/mixed version.** Operator/automation gọi target `ceph` CLI với range blocklist/msgr address hoặc reordered named args mới thấy khác biệt. Client base có thể reject cùng input trước khi gửi request. Risk thấp nhưng cần giữ CLI version nhất quán trong automation; confidence `high`. Relevant unit expectations đã đọc, không chạy.

### VAL-005 — `ceph-dencoder` cần binary/plugin package đồng bộ

**Evidence.** CSV rows `2552–2562`; `load_plugins()`, `DencoderPlugin`, `DencoderRegistry`, `register_dencoders()`. Core commits gồm `8da660fe8ae15da3ed873af517358c76f298c417`, `796e990aae7a4e610e845ced2ad9bfdb50b18de2`, `33c110fadc64f16589c066595df78b08da5381ff`, `87feb5734b24ab0177481a7ef9ab7c8666c4ebd7`. Build/package owner được phân tích tại [`BLD-006`](./13-build-packaging-submodules.md).

**Trước → sau.** Base đăng ký types tĩnh trong monolithic executable. Target quét `CEPH_INSTALL_PKGLIBDIR/denc` (hoặc `CEPH_LIB`/dev `lib`) và `dlopen()` các `denc-mod-*` modules. Thiếu hoặc version-skewed module có thể làm `list_types` thiếu type hoặc decode báo unknown, dù daemon production không bị tác động.

**Activation.** Chỉ khi dùng `ceph-dencoder` cho offline validation/recovery/debug. Upgrade package phải giữ executable và plugin set cùng target build; không có cluster migration/restart dependency. Risk tooling trung bình theo điều kiện, confidence `high`; chưa chạy package smoke test.

### VAL-006 — Pacific p2p là recipe đúng base nhưng có intentional coverage gaps

**Evidence.** CSV rows `937–940` và supporting workunit row `1047`. Commit `f7ec7f63ad85bd80ca1496ee052ac96e96c77a81` chuyển starting release thành `v16.2.5`; các commits sau đưa intermediate hop lên `v16.2.7`, thêm `mon_mds_skip_sanity`, loại `TestClsRbd.mirror_snapshot`, và lấy librbd Python tests từ branch `pacific`.

**Ý nghĩa.** Recipe trực tiếp hơn legacy suites vì bắt đầu đúng base. Tuy nhiên endpoint recipe đi `v16.2.5 → v16.2.7 → latest Pacific`, không tự chứng minh mọi point release đã được test. `mon_mds_skip_sanity: true`, RBD filter và cmpomap workunit filter là deliberate exclusions phải được ghi lại trong acceptance; chúng tránh known false failures nhưng cũng để lại coverage cần bù.

**Evidence boundary.** Repository chỉ chứa recipe; không có artifact chứng minh suite đã chạy trên target SHA, pass rate, logs hoặc failure triage. Vì vậy các rows là `support`, không phải `material` runtime evidence.

### VAL-007 — Legacy upgrade suites chỉ là evidence gián tiếp

**Evidence.** CSV rows `915–936` gồm Nautilus→Pacific và Octopus→Pacific recipes. Commit `446a4ef6d446ee611435249006600dfaf6009571` pin Ragweed prepare/check về branch của starting release (`ceph-nautilus` hoặc `ceph-octopus`) thay vì vô tình dùng `ceph-pacific`. Upgrade sequences cũng đổi từ `wait-for-healthy` sang `wait-for-osds-up` quanh OSD/RGW restarts.

**Applicability.** Các recipes hữu ích để thiết kế legacy-client/RGW workload và restart observation, nhưng starting endpoint khác `v16.2.5`; pass ở đó không chứng minh `v16.2.5→v16.2.15`. Ragweed branch correction cải thiện fidelity của suite, không phải runtime RGW fix. Dùng các suites này làm supporting scenarios, còn acceptance hiện tại phải dựa trên Pacific p2p/canary đúng endpoints.

### VAL-008 — Release-note text phải được đối chiếu theo hunk, version và endpoint code

**Evidence.** CSV row `7`, `PendingReleaseNotes`, là `mixed`. Net diff thêm các sections `>=16.2.6` đến `>=16.2.15`, đồng thời thêm content dưới `>=17.0.0` và các older headings. File còn giữ nhiều text đã tồn tại trước base.

Ba rule áp dụng:

1. Notice dưới `>=17.0.0` nằm ngoài target Pacific và không được biến thành upgrade finding hiện tại.
2. Text về `radosgw-admin` `mdlog-list`/`datalog-list`/`sync-error-list` và `*-trim` không phải thay đổi endpoint này: blame trỏ về `26f5b2f58efc`/`ae5660fbb663` năm 2020 và text đã có ở base. Nó là legacy context, không phải residual RGW delta.
3. RGW secure-MON defaults là delta thật: `5943bb5a94bb37429bf3c1bb9f15d69ad636002d` đặt `ms_mon_client_mode=secure`; `77d704ab057c35e26004fe0a09386054da5235a4` đặt `auth_client_required=cephx` và thêm release-note hunk. Runtime code thuộc owner `12`, được phân tích tại [`RGW-007`](./12-rgw.md). Activation là **RGW process restart**, không phải lúc đọc/apply release notes; trong mixed phase RGW base/target có thể khác MON-auth defaults.

Các notice `>=16.2.x` khác chỉ là candidate index tới owner reports; endpoint diff/commit/test ở owner đó mới là evidence quyết định.

## 4. Validation matrix đề xuất

Các scenario dưới đây **chưa được chạy**. Chúng là thiết kế quan sát cho lab/canary được phê duyệt riêng; không phải lệnh vận hành hay ủy quyền thay đổi cluster.

| Scenario | Findings | Phase và precondition | Observation/expected result | Failure/stop condition |
| --- | --- | --- | --- | --- |
| `V15-01` | `VAL-001`, `SEC-004` | First target restart trên host có user/group `ceph` và realistic crash-dir ownership | Process UID/GID là `ceph`; readable crash được post; unreadable entry tạo warning nhưng loop còn sống | Process vẫn root, exit do drop failure, hoặc crash backlog tăng |
| `V15-02` | `VAL-002` | Disposable mixed OSD set; object có empty omap value; U64 compare pin lần lượt vào base/target primary | Base/target result khớp semantics đã ghi; sau full target empty value được so như `0` | `-EIO`/comparison result ngoài expected, OSD assert, hoặc client retry che sai lệch |
| `V15-03` | `VAL-003`, `CEPHFS-004` | Canary client dùng MON IPv6; target mount helper | Generated MON string có brackets và mount/IO/umount ổn định | Parse/mount failure, reconnect loop hoặc client không hồi phục |
| `V15-04` | `VAL-004`, `MON-001` | Local parser/unit environment và disposable cluster nếu cần integration | Accepted/rejected msgr/range inputs đúng unit matrix; automation không phụ thuộc CLI base | Parser chấp nhận malformed range hoặc target automation khác contract |
| `V15-05` | `VAL-005`, `BLD-006` | Target package set trong staging image | `ceph-dencoder list_types` thấy expected OSD/MDS/RBD/RGW types; representative decode dùng đúng plugin | Missing module, `dlopen` error, unknown type hoặc binary/module version skew |
| `V15-06` | `VAL-006`, `ADM-001`, `RBD-006` | Pacific p2p từ exact base SHA/tag tới target; record all filters | Workload tiếp tục qua intermediate/full target; exclusions được bù bằng targeted cases | Unexplained health transition, filtered case không có replacement, thiếu logs/result artifact |
| `V15-07` | `VAL-007`, `RGW-004` | Legacy suite chỉ khi estate thật có Nautilus/Octopus-origin clients/data | Ragweed prepare trước upgrade và check sau upgrade dùng đúng starting branch | Dùng legacy pass làm bằng chứng duy nhất cho current endpoints hoặc branch sai release |
| `V15-08` | `VAL-008`, `RGW-007` | Target RGW restart; biết trạng thái CephX, `ms_mon_client_mode`, proxies/TLS clients | RGW kết nối MON bằng intended auth và supported TLS clients vẫn hoạt động | RGW không authenticate MON, legacy client outage ngoài kế hoạch, hoặc mixed daemons trả khác nhau |
| `V15-09` | `OSD-001`, `OSD-002`, `OSD-003`, `OSD-004`, `OSD-007`, `OSD-010`; `BS-001`, `BS-002`, `BS-003`, `BS-004`, `BS-009` | Fault-injection lab với restart, EC, scrub, replay và repair copies | Recovery/replay converges; no assert/data mismatch; offline tools chỉ chạy trên copy | Data mismatch, daemon boot failure, repair làm đổi dữ liệu ngoài expected |
| `V15-10` | `MON-001`, `MON-002`, `MON-003`, `MON-004`, `MON-007`; `MSG-001`, `MSG-002`, `MSG-004`, `MSG-007`, `MSG-009` | Rolling MON/OSD/MGR with mixed feature set | Quorum/reconnect/feature gates ổn định; `require-osd-release` chỉ set ở completion checkpoint | Quorum loss, unsupported feature activation, deadlock hoặc irreversible checkpoint sớm |
| `V15-11` | `ADM-001`, `ADM-003`, `ADM-004`, `ADM-007`, `ADM-008`; `CVOL-001`, `CVOL-002`, `CVOL-003`, `CVOL-005`, `CVOL-006` | Orchestrated canary có encrypted/raw/LVM inventory phù hợp As-Is | MDS safety sequence, activation và device mapping ổn định qua restart | Migration boundary bị vượt, device nhận sai, daemon không activate hoặc rollback path mất |
| `V15-12` | `RBD-001`, `RBD-002`, `RBD-003`, `RBD-004`, `RBD-006`, `RBD-007`; `CEPHFS-001`–`CEPHFS-008`; `RGW-001`–`RGW-008` | Representative client/workload matrix pinned theo daemon version | Read/write/auth/session/multisite behavior nhất quán theo expected owner findings | Data/correctness mismatch, nondeterministic auth, session loss hoặc replication lag không hội tụ |

Mỗi live scenario cần bổ sung topology, SLO, backup/restore, người phê duyệt, time budget và rollback/stop procedure trước khi thực thi.

## 5. Trivial/support changes và reconciliation

| File class | Material/conditional/mixed/support/trivial | Diễn giải |
| --- | --- | --- |
| Runtime/source | `2 / 2 / 0 / 0 / 5` | Cmpomap được promote; mount/parser conditional; MemStore/helper additions còn lại không có upgrade causal path độc lập |
| Build/package | `0 / 0 / 1 / 0 / 1` | `ceph-crash` mixed; `init-ceph.in` chỉ thay dev build PATH |
| Tool/script | `0 / 11 / 0 / 0 / 5` | 11 dencoder rows conditional; dev/CI scripts còn lại trivial |
| Test/QA | `0 / 0 / 1 / 33 / 88` | Relevant repository/upgrade recipes là support hoặc mixed; phần còn lại là harness/coverage không gắn finding được promote |
| Documentation | `0 / 0 / 0 / 3 / 79` | Ba docs corroborate owner findings; còn lại không thay binary/state |
| Release-note | `0 / 0 / 1 / 0 / 19` | `PendingReleaseNotes` mixed; 19 archival/index rows không phải runtime evidence |
| Mechanical/assets/config | `0 / 0 / 0 / 1 / 14` | Một legacy-suite marker hỗ trợ recipe; rename markers, images, SVG và mypy config không có effect production |

Tổng cuối cùng: `material 2 + conditional 13 + mixed 3 + support 37 + trivial 211 = 266`. Chi tiết mapping, symbols, SHAs và evidence status nằm trong CSV; Markdown không lặp lại per-file ledger.

## 6. Residual gaps và handoff

- Chưa có As-Is topology, enabled features, client versions, CephX/TLS policy, IPv6 use, `cmpomap` consumers, packaging source hoặc crash-directory permissions.
- Không có unit/integration/Teuthology/live-cluster test nào được chạy trong lần phân tích này; repository recipes và test code chỉ được đọc.
- Pacific p2p recipe có intentional skips/overrides; acceptance plan phải bù hoặc chấp nhận rõ từng gap.
- `ceph-dencoder` cần package-content smoke test trên đúng artifact sẽ deploy, không chỉ source build review.
- Release-note claims phải tiếp tục trỏ về owner finding; text legacy/out-of-range không được dùng để tạo blocker.
- Production GO/NO-GO chỉ có thể đưa ra sau khi hoàn thành As-Is inventory và thu execution artifacts cho các scenario áp dụng.
