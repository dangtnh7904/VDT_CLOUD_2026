"""Update owner-08 completion wording after its binary gate is closed."""

import re
from pathlib import Path


root = Path(__file__).resolve().parents[1]


def edit(path: Path, substitutions: list[tuple[str, str]]) -> None:
    content = path.read_text(encoding="utf-8")
    for old, new in substitutions:
        assert old in content, (path, old)
        content = content.replace(old, new, 1)
    path.write_text(content, encoding="utf-8")


edit(root / "08-cephadm-orchestrator.md", [
    ("**Trạng thái: đang phân tích.**", "**Trạng thái: đã hoàn tất binary gate của owner; lab/canary còn mở.**"),
    ("; các hàng trống chưa có kết luận.", "; `95 + 39 = 134`, không còn hàng trống."),
    ("Các hàng khác vẫn để trống `upgrade_impact` cho tới khi đọc diff/metadata; không gán `trivial` theo đường dẫn.",
     "Bảy hàng unit test/fixture còn lại và tài liệu developer/MDS, license, README image keepalived được gắn `trivial` sau khi đọc hunk: chúng bổ sung regression mock hoặc ví dụ không đổi đường upgrade độc lập. Tox gate được giữ `affect` ở ADM-025 vì thay dependency validation."),
    ("- Đọc hunk và context cho các cụm hành vi trong owner; xét riêng khác biệt mixed-version, full-version, rollback và activation.\n- Đối chiếu commit, test repository và tài liệu chính thức khi claim cần xác minh thêm.\n- Gắn từng hàng `affect|trivial` cùng lý do; mỗi `affect` phải trỏ tới finding ID có mô tả trước/sau, applicability, confidence và kịch bản validation.\n- Chỉ sau khi binary gate hoàn tất mới đối soát `affect + trivial = 134` và viết tóm tắt các cụm trivial.",
     "- Đã đọc hunk/context và gắn `affect|trivial` cùng lý do cho cả 134 hàng; mọi `affect` trỏ đến finding ID.\n- Đã đối soát `95 affect + 39 trivial = 134` và mô tả các cụm trivial.\n- Còn cần lab/canary cho SSH, failover, OSD, ingress, monitoring và acceptance QA; đối chiếu commit/tài liệu chính thức bổ sung khi áp vào As-Is cluster."),
])

readme = root / "README.md"
content = readme.read_text(encoding="utf-8")
content = content.replace(
    "[owner 06](./06-config-defaults.md), [owner 09](./09-ceph-volume-activation.md)",
    "[owner 06](./06-config-defaults.md), [owner 08](./08-cephadm-orchestrator.md), [owner 09](./09-ceph-volume-activation.md)", 1)
assert "[owner 08](./08-cephadm-orchestrator.md)" in content
old = "| 08 — cephadm | [Báo cáo](./08-cephadm-orchestrator.md) | [CSV](./08-cephadm-orchestrator.csv) | Đang phân tích |"
assert old in content
content = content.replace(old, old.replace("Đang phân tích", "Binary gate owner đã hoàn tất; lab còn mở"), 1)
content, n = re.subn(r"vì [\d.]+ hàng còn thiếu nhãn và lý do", "vì 2.851 hàng còn thiếu nhãn và lý do", content, count=1)
assert n == 1
content = content.replace(
    "MON CRUSH location và NFS VIP; cùng",
    "MON CRUSH location, NFS VIP, Rook QA, runbook, Keepalived image và tox; cùng", 1)
readme.write_text(content, encoding="utf-8")

plan = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"
edit(plan, [
    ("Owner 01, 02, 03, 04, 05, 06, 09, 14 đã hoàn tất binary gate;",
     "Owner 01, 02, 03, 04, 05, 06, 08, 09, 14 đã hoàn tất binary gate;"),
    ("Owner 08 hiện `95 affect`, `39 trivial`, `0` chưa phân loại.",
     "Owner 08 đã chốt `95 affect`, `39 trivial`, `0` chưa phân loại."),
    ("rà owner 07 MGR và 08 cephadm theo đường restart, mixed-version;",
     "rà owner 07 MGR theo đường restart, mixed-version;"),
])
