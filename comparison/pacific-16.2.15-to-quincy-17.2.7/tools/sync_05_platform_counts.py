"""Refresh suite counters after owner-05 platform review."""

from pathlib import Path


root = Path(__file__).resolve().parents[1]
readme = root / "README.md"
text = readme.read_text(encoding="utf-8")
old = "666 hàng `affect`, 407 hàng `trivial`, 3.106 hàng chưa phân loại"
assert text.count(old) == 1
text = text.replace(old, "673 hàng `affect`, 411 hàng `trivial`, 3.095 hàng chưa phân loại")
assert text.count("[MSG-001–029]") == 1
text = text.replace("[MSG-001–029]", "[MSG-001–034]")
readme.write_text(text, encoding="utf-8")

plan = root.parent / "PLAN-pacific-16.2.15-to-quincy-17.2.7.md"
text = plan.read_text(encoding="utf-8")
old = "`affect 666`, `trivial 407`, còn **3.106 hàng chưa phân loại**"
assert text.count(old) == 1
plan.write_text(
    text.replace(old, "`affect 673`, `trivial 411`, còn **3.095 hàng chưa phân loại**"),
    encoding="utf-8",
)
