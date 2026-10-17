# Exact-hop pin register cho Pacific 16.2.15 → Quincy 17.2.7

**Trạng thái ngày 12/10/2026: 12/12 pin `PENDING_INPUT`.** Audit target SHA `b12291d110049b2f35e32e0de30d70e9a4c060d2` xác nhận `qa/suites/upgrade/pacific-x` có 38 entry, 25 YAML parse sạch và 9/9 symlink resolve hợp lệ. Source vẫn có 14 `branch: pacific`, 2 `cephadm_branch: pacific`, 2 base image tag nổi, 2 target image `$sha1` và 6 version check `$sha1`; vì vậy source suite không tự chứng minh một run exact `v16.2.15→v17.2.7`.

[Manifest template](./EXACT-HOP-PIN-MANIFEST.template.json) cố ý mang nhãn `NOT_EXACT_HOP_VALID`. Chỉ bản sao lưu trong archive của run, điền evidence thật và qua shared validator `comparison/tools/validate_exact_hop_manifest.py --mode locked`, mới được mang nhãn `EXACT_HOP_VALID`.

| Pin | Khoảng trống cần khóa | Evidence bắt buộc | Gate chính | Trạng thái |
| --- | --- | --- | --- | --- |
| PIN-01 | 14 selector branch Pacific chưa ghim patch endpoint | Expanded YAML, checkout/package identity đúng base SHA | `LAB-004`, `LAB-020`→`LAB-049` | PENDING_INPUT |
| PIN-02 | 2 `cephadm_branch: pacific` | Checksum và provenance cephadm bootstrap | `LAB-004`, `LAB-012` | PENDING_INPUT |
| PIN-03 | 2 base image tag `:pacific` | Immutable digest, image inspect, package list và `ceph version` | `LAB-001`, `LAB-004`, `LAB-012` | PENDING_INPUT |
| PIN-04 | 2 target image `$sha1` | Immutable digest của build target và registry manifest | `LAB-001`, `LAB-004`, `LAB-012` | PENDING_INPUT |
| PIN-05 | 6 assertion/poll `grep $sha1` | Versions + orch state + digest + expected daemon counts | `LAB-004`, `LAB-012`, `LAB-051` | PENDING_INPUT |
| PIN-06 | Distro selectors và chuỗi symlink `.qa` dùng chung | OS/kernel/runtime lane cố định khớp As-Is | `LAB-002`, `LAB-004` | PENDING_INPUT |
| PIN-07 | Registry/mirror và retention chưa biết | Pull-by-digest test, mirror policy, credential reference đã redaction | `LAB-001`, `LAB-012` | PENDING_INPUT |
| PIN-08 | Chỉ parallel lane bật `use_repo_digest`; stress lane khác semantics | Effective config và digest từng lane, disposition sai khác | `LAB-004`, `LAB-012` | PENDING_INPUT |
| PIN-09 | Ceph tree không pin teuthology/task plugin/local patch | Ceph/teuthology SHA, patch checksum và expanded YAML | `LAB-004`, `LAB-006` | PENDING_INPUT |
| PIN-10 | Client-old/new hai hướng không được suy từ daemon image | Package/digest client, library binding và kết quả từng hướng | `LAB-005`, `LAB-030`→`LAB-049` | PENDING_INPUT |
| PIN-11 | Release/client floor là boundary riêng | Quarantine fixture, approval và old-client negative result | `LAB-011`, `LAB-050` | PENDING_INPUT |
| PIN-12 | Console loop không định nghĩa archive completeness | Run ID, seed, timeline, topology, archive checksum, rerun và owner | `LAB-004`, `LAB-051` | PENDING_INPUT |

PIN-01→09 và PIN-12 phải `LOCKED`; PIN-10/11 phải `LOCKED` hoặc `NOT_APPLICABLE` có lý do và evidence. Validator chỉ kiểm tính đầy đủ/nhất quán của manifest, không chứng minh test hành vi đã PASS.
