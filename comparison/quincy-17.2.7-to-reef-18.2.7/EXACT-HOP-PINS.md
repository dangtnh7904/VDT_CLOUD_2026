# Exact-hop pin register cho native Quincy→Reef suites

**Trạng thái ngày 12/10/2026: 12/12 pin `PENDING_INPUT`.** Audit target source xác nhận native suites vẫn chứa 16 selector `branch: quincy`, 3 `cephadm_branch: quincy`, 3 base image tag nổi, 3 target image `$sha1`, 7 phép kiểm version bằng `$sha1` và 3 distro selector dùng chung. Không được gọi một run là exact `v17.2.7→v18.2.7` cho đến khi toàn bộ pin applicable được khóa và lưu trong job archive.

[Manifest template](./EXACT-HOP-PIN-MANIFEST.template.json) và `tools/validate_exact_hop_manifest.py` biến register này thành gate máy kiểm được. Template cố ý mang nhãn `NOT_EXACT_HOP_VALID`; không sửa trực tiếp file template thành bằng chứng chạy. Mỗi run phải copy sang archive riêng, điền evidence thật và chỉ đặt `EXACT_HOP_VALID` khi validator `--mode locked` pass.

Base source SHA đã biết là `b12291d110049b2f35e32e0de30d70e9a4c060d2`; target source SHA là `6b0e988052ec84cf2d4a54ff9bbbc5e720b621ad`. Source SHA không tự cung cấp package NEVRA, image digest, cephadm payload hay teuthology commit.

## Pin register

| Pin | Source selector hiện tại | Exact input bắt buộc | Evidence để khóa | Áp dụng cho pack | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| PIN-01 | 16 chỗ `branch: quincy` cho install/workunit | Base ref phải resolve đúng `v17.2.7` và base SHA; workload nào chủ đích target phải ghi target ref riêng | Expanded job config, fetched commit, package/source checksum và log checkout | `TP-02`, `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-02 | 3 chỗ `cephadm_branch: quincy` | cephadm bootstrap payload phải lấy từ đúng base SHA hoặc checksum-equivalent packaged artifact | cephadm file checksum, source/ref metadata và bootstrap log | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-03 | Hai image `quay.ceph.io/ceph-ci/ceph:quincy` và một `quay.io/ceph/daemon-base:latest-quincy` | Base container phải pin immutable digest và chứng minh version/source SHA bên trong | Registry manifest, repo digest, image inspect, `ceph version` và package list | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-04 | 3 lệnh target dùng `quay.ceph.io/ceph-ci/ceph:$sha1` | Target image phải pin immutable digest của build từ target SHA; `$sha1` chỉ là lookup input, không phải digest evidence | Registry manifest, resolved digest, image inspect và per-daemon image ID | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-05 | 7 assertion/poll dùng `grep $sha1` | Completion phải kiểm đồng thời version string, source SHA, image digest và expected daemon count/role | Raw `ceph versions`, `ceph orch ps`, image inspect và role inventory theo timestamp | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-06 | 3 selector trỏ `.qa/distros/supported-container-hosts` | Chọn distro/kernel/runtime lane cố định khớp từng host cohort As-Is; cấm random selector cho acceptance run | Expanded distro fragment, host image ID, OS release, kernel, runtime và storage/network driver | `TP-02`, `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-07 | Source registry gồm `quay.ceph.io/ceph-ci` và `quay.io/ceph/daemon-base` | Chốt registry/mirror, authentication, retention và pull-by-digest availability cho toàn bộ lab window | Registry endpoint, mirror policy, digest pull test và redacted credential reference | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-08 | Parallel/telemetry bật `mgr/cephadm/use_repo_digest true`; stress lane không cùng đoạn config | Ghi effective setting từng lane và resolved digest semantics; không so kết quả giữa lane nếu delivery mode khác mà chưa disposition | Effective config, upgrade command, orch status và daemon image digest từng lane | `TP-03`, `TP-04`, `TP-07` | PENDING_INPUT |
| PIN-09 | Ceph suite source ở target tree nhưng teuthology/helper repository không nằm trong hai endpoint SHA | Pin Ceph suite commit, teuthology commit, task plugin revisions và mọi local patch/override | Job metadata, Git SHAs, diff/patch checksum và expanded YAML | `TP-02`, `TP-03`, `TP-04`, `TP-05`, `TP-07` | PENDING_INPUT |
| PIN-10 | Native client exact-hop suite đã bị repurpose; daemon suites gọi base-branch RBD workunits | Dựng explicit old-client/new-daemon và new-client/old-daemon artifacts, không suy client version từ daemon image | Client package/image digest, host cohort, library binding versions và per-direction results | `TP-12`, `TP-13`, `TP-14` | PENDING_INPUT |
| PIN-11 | `qa/releases/reef.yaml` trực tiếp đặt require-osd-release và min-compatible-client Reef | Quarantine fixture khỏi rolling lanes; chỉ enable bằng approval flag sau full Reef inventory và rollback sign-off | Expanded job chứng minh fixture absent/present đúng phase, approval record và old-client negative result | `TP-18` | PENDING_INPUT |
| PIN-12 | Native loops lưu console nhưng không tự định nghĩa archive completeness hay rerun identity | Pin run ID, start/end UTC, topology, workload seed, timeout, archive URI/checksum và rerun linkage | Evidence manifest có checksum, raw outputs, failure triage, rerun reason và owner | `TP-01`, `TP-19` | PENDING_INPUT |

## Acceptance rule cho exact-hop label

Một job chỉ được gắn nhãn `EXACT_HOP_VALID` khi PIN-01→09 và PIN-12 là `LOCKED`; PIN-10/11 phải `LOCKED` hoặc `NOT_APPLICABLE` theo loại job. Nếu registry không còn giữ image tag nhưng digest artifact đã được mirror và chứng minh source/package identity thì dùng mirror digest; không rebuild âm thầm rồi coi là cùng artifact.

Các loop dựa vào `grep $sha1` phải được giữ như signal phụ, không phải oracle duy nhất. Một cluster có một version string vẫn có thể chạy image digest hoặc package payload ngoài manifest; ngược lại digest đúng nhưng daemon count thiếu cũng không được coi là hoàn tất.

## Dùng manifest validator

Kiểm template/schema mà không đòi runtime evidence:

```powershell
python .\tools\validate_exact_hop_manifest.py `
  --manifest .\EXACT-HOP-PIN-MANIFEST.template.json `
  --mode template
```

Kiểm manifest của một run trước khi gắn nhãn exact-hop:

```powershell
python .\tools\validate_exact_hop_manifest.py `
  --manifest <archive>\exact-hop-pin-manifest.json `
  --mode locked
```

Locked mode yêu cầu endpoint refs/SHA chính xác; package và immutable image digest cho base/target; cephadm provenance; expanded job hash; workload seed/timestamps/topology; registry pull-by-digest; disposition `use_repo_digest`; ít nhất một distro lane; Ceph/teuthology/plugin/patch pins; version/image/role completion oracle; client matrix và release-floor guard; archive checksum/owner/triage; cùng evidence cho từng PIN. `PIN-10` phải khớp disposition client matrix và `PIN-11` phải khớp release-floor guard. Validator chỉ kiểm completeness/consistency của manifest, không chứng minh nội dung evidence là đúng hoặc job đã PASS về hành vi.
