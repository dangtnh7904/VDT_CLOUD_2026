"""Sync reviewed impact counts in owner reports, suite README, and plan."""

import csv
import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
counts = Counter()
for path in root.glob("[0-1][0-9]-*.csv"):
    if path.name == "00-file-inventory.csv":
        continue
    with path.open(encoding="utf-8-sig", newline="") as stream:
        counts.update(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))

owner_counts = Counter()
with (root / "05-messaging-auth-common.csv").open(encoding="utf-8-sig", newline="") as stream:
    owner_counts.update(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))

rgw_counts = Counter()
with (root / "12-rgw.csv").open(encoding="utf-8-sig", newline="") as stream:
    rgw_counts.update(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, changes = re.subn(pattern, replacement, content, count=1)
    assert changes == 1, (path, pattern)
    path.write_text(updated, encoding="utf-8")


owner = root / "05-messaging-auth-common.md"
replace_once(
    owner,
    r"Hiện `affect = [\d.]+`, `trivial = [\d.]+`, \*\*chưa phân loại = [\d.]+\*\*",
    f"Hiện `affect = {owner_counts['affect']}`, `trivial = {owner_counts['trivial']}`, **chưa phân loại = {owner_counts['']}**",
)

readme = root / "README.md"
replace_once(
    readme,
    r"[\d.]+ hàng `affect`[.,] [\d.]+ hàng `trivial`[.,] [\d.]+ hàng chưa phân loại",
    f"{counts['affect']:,} hàng `affect`, {counts['trivial']:,} hàng `trivial`, {counts['']:,} hàng chưa phân loại".replace(",", "."),
)
finding_numbers = [
    int(n)
    for n in re.findall(r"^### MSG-(\d+) ", owner.read_text(encoding="utf-8"), re.M)
]
assert finding_numbers
replace_once(readme, r"\[MSG-001–\d+\]", f"[MSG-001–{max(finding_numbers):03d}]")

rgw_owner = root / "12-rgw.md"
replace_once(
    rgw_owner,
    r"Hiện `affect = [\d.]+`, `trivial = [\d.]+`, \*\*chưa phân loại = [\d.]+\*\*",
    f"Hiện `affect = {rgw_counts['affect']}`, `trivial = {rgw_counts['trivial']}`, **chưa phân loại = {rgw_counts['']}**",
)
replace_once(
    rgw_owner,
    r"Không coi [\d.]+ hàng trống là `trivial`\.",
    f"Không coi {rgw_counts['']} hàng trống là `trivial`.",
)
replace_once(
    rgw_owner,
    r"\*\*[\d.]+ hàng đã phân loại `trivial`:\*\*",
    f"**{rgw_counts['trivial']} hàng đã phân loại `trivial`:**",
)
replace_once(
    rgw_owner,
    r"Các cụm hành vi/QA đã xem giữ [\d.]+ hàng `affect`; [\d.]+ hàng RGW còn lại chưa được xem đủ hunk/metadata và context để gắn nhãn\.",
    f"Các cụm hành vi/QA đã xem giữ {rgw_counts['affect']} hàng `affect`; {rgw_counts['']} hàng RGW còn lại chưa được xem đủ hunk/metadata và context để gắn nhãn.",
)

trivial_note = (
    "Sáu hàng vừa chốt tiếp gồm tài liệu S3 Select, hai file quota chỉ đổi SAL/DPP "
    "và ba file encoder/website chỉ di chuyển method sang source của class; không tạo "
    "semantics runtime độc lập."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if trivial_note not in rgw_content:
    anchor = (
        "Bốn hàng vừa chốt giữ encoding bucket-topic v3, chỉ tài liệu hóa lifecycle hoặc "
        "theo rename cùng ordinal `REMOVE_OBJ` → `INVALIDATE_OBJ`/`remove` → "
        "`invalidate_remove`; runtime tương ứng đã tách sang RGW-036/RGW-038."
    )
    assert anchor in rgw_content
    rgw_owner.write_text(rgw_content.replace(anchor, anchor + " " + trivial_note, 1), encoding="utf-8")

sts_trivial_note = (
    "Chín hàng STS/OIDC vừa chốt giữ encoding/provider operations và các behavior JWT, "
    "principal tags, resource-policy/user-policy đã có ở cả hai endpoint; net diff chỉ là "
    "SAL/DPP/qualification hoặc tài liệu, còn write user metadata được tách sang RGW-040."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if sts_trivial_note not in rgw_content:
    assert trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(trivial_note, trivial_note + " " + sts_trivial_note, 1),
        encoding="utf-8",
    )

user_stats_trivial_note = (
    "Tám hàng cơ học kế tiếp chỉ qualification kiểu queue/user-service/object-lock, bỏ future "
    "import Python 2, chuyển dump tag/interface DataProcessor sang source/SAL tương ứng; nhánh "
    "synchronous user-stats thực sự được tách sang RGW-041."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if user_stats_trivial_note not in rgw_content:
    assert sts_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(sts_trivial_note, sts_trivial_note + " " + user_stats_trivial_note, 1),
        encoding="utf-8",
    )

tracing_trivial_note = (
    "Ảnh Jaeger mới chỉ minh họa UI và không tự bật build/config; đường request span cùng "
    "multipart trace attr đã được tách sang RGW-042."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if tracing_trivial_note not in rgw_content:
    assert user_stats_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            user_stats_trivial_note,
            user_stats_trivial_note + " " + tracing_trivial_note,
            1,
        ),
        encoding="utf-8",
    )

reshard_trivial_note = (
    "Ba hàng reshard vừa chốt giữ cùng behavior dọn shard/OLH/lock ở hai endpoint; "
    "source/header chỉ đổi SAL/DPP/style, còn test target-only chỉ xác nhận PUT foreground "
    "và không phủ async completion retry của RGW-043."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if reshard_trivial_note not in rgw_content:
    assert tracing_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            tracing_trivial_note,
            tracing_trivial_note + " " + reshard_trivial_note,
            1,
        ),
        encoding="utf-8",
    )

trim_trivial_note = (
    "Hai implementation bilog/datalog vừa chốt giữ nguyên marker, lock, watcher và coroutine; "
    "net diff chỉ theo SAL/DPP/ownership, còn việc bỏ qua cả lượt trim do topology lỗi được "
    "tách sang RGW-044 ở mdlog factory/caller."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if trim_trivial_note not in rgw_content:
    assert reshard_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            reshard_trivial_note,
            reshard_trivial_note + " " + trim_trivial_note,
            1,
        ),
        encoding="utf-8",
    )

opslog_trivial_note = (
    "Ba hàng ops-log hỗ trợ vừa chốt giữ schema v14, file sink/reopen/store-reference ở cả hai "
    "endpoint hoặc chỉ điều chỉnh QA/local runner; behavior ghi request không có bucket được "
    "tách sang RGW-046 trong `rgw_log.cc`."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if opslog_trivial_note not in rgw_content:
    assert trim_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            trim_trivial_note,
            trim_trivial_note + " " + opslog_trivial_note,
            1,
        ),
        encoding="utf-8",
    )

dead_admin_user_note = (
    "Hai file `rgw_admin_user` bị xóa là source/header mồ côi: thư viện, public header và test "
    "tiêu thụ duy nhất đã bị loại trước Pacific; cả hai endpoint không build, package, export hay "
    "gọi các symbol còn sót."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if dead_admin_user_note not in rgw_content:
    assert opslog_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            opslog_trivial_note,
            opslog_trivial_note + " " + dead_admin_user_note,
            1,
        ),
        encoding="utf-8",
    )

user_admin_trivial_note = (
    "`rgw_rest_user.cc` giữ cùng đường fetch/persist access key từ master zone ở hai endpoint "
    "nhờ backport Pacific; phần còn lại chỉ chuyển SAL và bỏ parse `user-caps` không được "
    "user-modify tiêu thụ."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if user_admin_trivial_note not in rgw_content:
    assert dead_admin_user_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            dead_admin_user_note,
            dead_admin_user_note + " " + user_admin_trivial_note,
            1,
        ),
        encoding="utf-8",
    )

lifecycle_support_note = (
    "Tám hàng QA/metadata tiếp theo gồm suite lifecycle chạy một phiên bản, cấu hình multisite "
    "tắt notification để kiểm polling và danh sách maintainer; chúng hỗ trợ coverage/chủ sở hữu "
    "nhưng không tạo recipe Pacific–Quincy hay thay đổi runtime."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if lifecycle_support_note not in rgw_content:
    assert user_admin_trivial_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            user_admin_trivial_note,
            user_admin_trivial_note + " " + lifecycle_support_note,
            1,
        ),
        encoding="utf-8",
    )

sync_docs_qa_note = (
    "Mười bốn hàng vừa chốt gồm sáu tài liệu option/frontend/multisite/placement/role/S3, "
    "bốn task QA một phiên bản/legacy và bốn file sync hỗ trợ; chúng chỉ đổi tài liệu, "
    "nhánh test ngoài, qualification/di chuyển helper hoặc giữ endpoint parity qua backport. "
    "Các behavior metadata-sync và resolve topology đã tách sang RGW-048/049."
)
rgw_content = rgw_owner.read_text(encoding="utf-8")
if sync_docs_qa_note not in rgw_content:
    assert lifecycle_support_note in rgw_content
    rgw_owner.write_text(
        rgw_content.replace(
            lifecycle_support_note,
            lifecycle_support_note + " " + sync_docs_qa_note,
            1,
        ),
        encoding="utf-8",
    )

rgw_finding_numbers = [
    int(n)
    for n in re.findall(r"^### RGW-(\d+) ", rgw_owner.read_text(encoding="utf-8"), re.M)
]
assert rgw_finding_numbers
replace_once(readme, r"\[RGW-001–\d+\]", f"[RGW-001–{max(rgw_finding_numbers):03d}]")
rgw_summary_note = (
    "gate bucket-notification theo HTTP/AMQP/Kafka, lifecycle notification khi chạy lẫn phiên bản, "
    "payload notification mới, watcher metadata-cache mất backport tự phục hồi và S3 Select "
    "CSV/Parquet phụ thuộc build"
)
readme_content = readme.read_text(encoding="utf-8")
if rgw_summary_note not in readme_content:
    anchor = "gate bucket-notification theo HTTP/AMQP/Kafka"
    assert anchor in readme_content
    readme.write_text(readme_content.replace(anchor, rgw_summary_note, 1), encoding="utf-8")
rgw_040_note = " và STS `AssumeRole` ghi user metadata không dùng"
readme_content = readme.read_text(encoding="utf-8")
if rgw_040_note not in readme_content:
    assert rgw_summary_note in readme_content
    readme.write_text(
        readme_content.replace(rgw_summary_note, rgw_summary_note + rgw_040_note, 1),
        encoding="utf-8",
    )
rgw_041_note = " và synchronous user stats phân biệt user/header"
readme_content = readme.read_text(encoding="utf-8")
if rgw_041_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_041_note, 1),
        encoding="utf-8",
    )
rgw_042_note = " và Jaeger request/multipart tracing phụ thuộc artifact/config"
readme_content = readme.read_text(encoding="utf-8")
if rgw_042_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_042_note, 1),
        encoding="utf-8",
    )
rgw_043_note = " và retry bucket-index completion sau reshard thiếu `assert_exists`"
readme_content = readme.read_text(encoding="utf-8")
if rgw_043_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_043_note, 1),
        encoding="utf-8",
    )
rgw_044_note = " và sync-log trim fail-closed khi zone thiếu endpoint"
readme_content = readme.read_text(encoding="utf-8")
if rgw_044_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_044_note, 1),
        encoding="utf-8",
    )
rgw_045_note = " và usage REST mở rộng scope khi lookup bucket thất bại"
readme_content = readme.read_text(encoding="utf-8")
if rgw_045_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note + rgw_044_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_045_note, 1),
        encoding="utf-8",
    )
rgw_046_note = " và ops log mới ghi request không gắn bucket"
readme_content = readme.read_text(encoding="utf-8")
if rgw_046_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note + rgw_044_note + rgw_045_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_046_note, 1),
        encoding="utf-8",
    )
rgw_047_note = " và chown bucket/user sửa mapping owner cùng ACL object"
readme_content = readme.read_text(encoding="utf-8")
if rgw_047_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note + rgw_044_note + rgw_045_note + rgw_046_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_047_note, 1),
        encoding="utf-8",
    )
rgw_048_note = " và metadata sync sửa retry/index/truncated để hội tụ"
readme_content = readme.read_text(encoding="utf-8")
if rgw_048_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note + rgw_044_note + rgw_045_note + rgw_046_note + rgw_047_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_048_note, 1),
        encoding="utf-8",
    )
rgw_049_note = " và RGW startup resolve/fail-closed realm-zonegroup"
readme_content = readme.read_text(encoding="utf-8")
if rgw_049_note not in readme_content:
    anchor = rgw_summary_note + rgw_040_note + rgw_041_note + rgw_042_note + rgw_043_note + rgw_044_note + rgw_045_note + rgw_046_note + rgw_047_note + rgw_048_note
    assert anchor in readme_content
    readme.write_text(
        readme_content.replace(anchor, anchor + rgw_049_note, 1),
        encoding="utf-8",
    )
replace_once(
    readme,
    r"vì [\d.]+ hàng còn thiếu nhãn và lý do",
    f"vì {counts['']:,} hàng còn thiếu nhãn và lý do".replace(",", "."),
)

plan = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"
replace_once(
    plan,
    r"`affect [\d.]+`[.,] `trivial [\d.]+`[.,] còn \*\*[\d.]+ hàng chưa phân loại\*\*",
    f"`affect {counts['affect']:,}`, `trivial {counts['trivial']:,}`, còn **{counts['']:,} hàng chưa phân loại**".replace(",", "."),
)
