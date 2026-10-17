"""Synchronize owner-07 and suite progress after reviewed MGR batches."""

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
with (root / "07-mgr-modules-monitoring.csv").open(encoding="utf-8-sig", newline="") as stream:
    owner = Counter(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))
with (root / "12-rgw.csv").open(encoding="utf-8-sig", newline="") as stream:
    owner12 = Counter(row["upgrade_impact"] for row in csv.DictReader(stream, delimiter=";"))


def change(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, n = re.subn(pattern, replacement, content, count=1)
    assert n == 1, (path, pattern)
    path.write_text(updated, encoding="utf-8")


change(root / "07-mgr-modules-monitoring.md",
       r"Hiện `affect = [\d.]+`, `trivial = [\d.]+`, \*\*chưa phân loại = [\d.]+\*\*",
       f"Hiện `affect = {owner['affect']}`, `trivial = {owner['trivial']}`, **chưa phân loại = {owner['']}**")
change(root / "07-mgr-modules-monitoring.md",
       r"\d+ hàng gồm tài liệu, ảnh Dashboard",
       f"{owner['trivial']} hàng gồm tài liệu, ảnh Dashboard")
change(root / "12-rgw.md",
       r"Hiện `affect = \d+`, `trivial = \d+`, \*\*chưa phân loại = \d+\*\*\. Không coi \d+ hàng trống là `trivial`",
       f"Hiện `affect = {owner12['affect']}`, `trivial = {owner12['trivial']}`, **chưa phân loại = {owner12['']}**. Không coi {owner12['']} hàng trống là `trivial`")
change(root / "12-rgw.md",
       r"\*\*\d+ hàng đã phân loại `trivial`:",
       f"**{owner12['trivial']} hàng đã phân loại `trivial`:")
change(root / "12-rgw.md",
       r"Các cụm hành vi/QA đã xem giữ \d+ hàng `affect`; \d+ hàng RGW còn lại",
       f"Các cụm hành vi/QA đã xem giữ {owner12['affect']} hàng `affect`; {owner12['']} hàng RGW còn lại")
readme = root / "README.md"
change(readme, r"[\d.]+ hàng `affect`[.,] [\d.]+ hàng `trivial`[.,] [\d.]+ hàng chưa phân loại",
       f"{counts['affect']:,} hàng `affect`. {counts['trivial']:,} hàng `trivial`. {counts['']:,} hàng chưa phân loại".replace(",", "."))
finding_numbers = [int(number) for number in re.findall(
    r"^### MGR-(\d+) ", (root / "07-mgr-modules-monitoring.md").read_text(encoding="utf-8"), re.M)]
assert finding_numbers
change(readme, r"\[MGR-001(?:–\d+)?\]", f"[MGR-001–{max(finding_numbers):03d}]")
rgw_finding_numbers = [int(number) for number in re.findall(
    r"^### RGW-(\d+) ", (root / "12-rgw.md").read_text(encoding="utf-8"), re.M)]
assert rgw_finding_numbers
change(readme, r"\[RGW-001(?:–\d+)?\]", f"[RGW-001–{max(rgw_finding_numbers):03d}]")
change(readme, r"cho `\.mgr`/SQLite[^;]*;",
       "cho `.mgr`/SQLite, progress event, Prometheus exporter, telemetry opt-in, crash health, Influx, Zabbix, Telegraf, MGR activation, OSD/device metadata, retry clock, reweight CLI, lỗi cấu hình module, Dashboard service/alert/CRUSH API, host inventory/RBD detail, RBD mirroring health, RGW bucket encryption/daemon list, frontend build/Jest/Cypress gate, landing page v3/IOPS, daemon ceph-exporter, diskprediction local, khoảng trống metric Grafana, PG autoscaler/noautoscale, danh sách pool balancer, JSON/lỗi metadata của status, format thời lượng, RESTful OSD inventory, gate tox MGR, lệnh/snapshot scheduler, cache perf RBD và CLI orchestrator;")
change(readme, r"vì [\d.]+ hàng còn thiếu nhãn và lý do",
       f"vì {counts['']:,} hàng còn thiếu nhãn và lý do".replace(",", "."))
plan = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"
change(plan, r"`affect [\d.]+`[.,] `trivial [\d.]+`[.,] còn \*\*[\d.]+ hàng chưa phân loại\*\*",
       f"`affect {counts['affect']:,}`. `trivial {counts['trivial']:,}`. còn **{counts['']:,} hàng chưa phân loại**".replace(",", "."))
