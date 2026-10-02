"""Synchronize owner 08 and suite progress counts after review batches."""

import csv
import re
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parents[1]
counts = Counter()
for csv_path in root.glob("[0-1][0-9]-*.csv"):
    if csv_path.name == "00-file-inventory.csv":
        continue
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        counts.update(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))

with (root / "08-cephadm-orchestrator.csv").open(encoding="utf-8-sig", newline="") as stream:
    owner_counts = Counter(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1)
    assert count == 1, (path, pattern)
    path.write_text(updated, encoding="utf-8")


replace_once(
    root / "08-cephadm-orchestrator.md",
    r"Hiện `affect = [\d.]+`, `trivial = [\d.]+`, \*\*chưa phân loại = [\d.]+\*\*",
    f"Hiện `affect = {owner_counts['affect']}`, `trivial = {owner_counts['trivial']}`, **chưa phân loại = {owner_counts['']}**",
)
readme = root / "README.md"
replace_once(
    readme,
    r"[\d.]+ hàng `affect`[.,] [\d.]+ hàng `trivial`[.,] [\d.]+ hàng chưa phân loại",
    f"{counts['affect']:,} hàng `affect`. {counts['trivial']:,} hàng `trivial`. {counts['']:,} hàng chưa phân loại".replace(",", "."),
)
finding_numbers = [
    int(n) for n in re.findall(
        r"^### ADM-(\d+) ",
        (root / "08-cephadm-orchestrator.md").read_text(encoding="utf-8"),
        re.M,
    )
]
assert finding_numbers
replace_once(readme, r"\[ADM-001–\d+\]", f"[ADM-001–{max(finding_numbers):03d}]")

plan = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"
replace_once(
    plan,
    r"`affect [\d.]+`[.,] `trivial [\d.]+`[.,] còn \*\*[\d.]+ hàng chưa phân loại\*\*",
    f"`affect {counts['affect']:,}`. `trivial {counts['trivial']:,}`. còn **{counts['']:,} hàng chưa phân loại**".replace(",", "."),
)
replace_once(
    plan,
    r"Owner 08 hiện `[\d.]+ affect`, `[\d.]+ trivial`, `[\d.]+` chưa phân loại",
    f"Owner 08 hiện `{owner_counts['affect']} affect`, `{owner_counts['trivial']} trivial`, `{owner_counts['']}` chưa phân loại",
)
