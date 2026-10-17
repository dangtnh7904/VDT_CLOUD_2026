"""Classify Dashboard Prometheus alert/silence control and signal endpoints."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"
csv_path = root / "07-mgr-modules-monitoring.csv"
frontend = "src/pybind/mgr/dashboard/frontend/src/app/"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def show(tag: str, relative: str) -> str:
    return git("show", f"{tag}:{frontend}{relative}").stdout


def target_only(commit: str) -> None:
    assert git("merge-base", "--is-ancestor", commit, "v16.2.15", check=False).returncode != 0
    assert git("merge-base", "--is-ancestor", commit, "v17.2.7", check=False).returncode == 0


for commit in (
    "3db1eaa97ab2f0a32dc1da87de4a16d49c530ee7",
    "41788f0b611dae1934fb9678bcefcf7284f85004",
    "cef6e5b834bbe896a2e3deefb689b9d515916399",
    "1c62f21ef93d0aa262abc685476c3480faa8f0a5",
):
    target_only(commit)

base_alerts = show("v16.2.15", "shared/services/prometheus-alert.service.ts")
target_alerts = show("v17.2.7", "shared/services/prometheus-alert.service.ts")
assert "activeCriticalAlerts" not in base_alerts
assert "activeCriticalAlerts" in target_alerts
assert "activeWarningAlerts" in target_alerts
assert target_alerts.index("this.activeCriticalAlerts =") < target_alerts.index(
    "this.alerts = alerts;"
)
assert target_alerts.index("this.activeWarningAlerts =") < target_alerts.index(
    "this.alerts = alerts;"
)

base_form = show("v16.2.15", "ceph/cluster/prometheus/silence-form/silence-form.component.ts")
target_form = show("v17.2.7", "ceph/cluster/prometheus/silence-form/silence-form.component.ts")
assert "Object.keys(labels).forEach" in base_form
assert "Object.keys(labels).forEach" not in target_form
assert "name: 'alertname'" in target_form
assert "value: labels.alertname" in target_form
assert "return this.rules;" in target_form
assert target_form.index("this.prometheusService.getRules().subscribe(") < target_form.index(
    "return this.rules;"
)

target_list = show("v17.2.7", "ceph/cluster/prometheus/silence-list/silence-list.component.ts")
assert "const rules = this.silenceFormComponent.getRules();" in target_list
assert "silence.matchers.forEach" in target_list
assert "silence.silencedAlerts = alertNames;" in target_list

target_sidebar = show("v17.2.7", "shared/components/notifications-sidebar/notifications-sidebar.component.ts")
assert "moment().add(2, 'hours')" in target_sidebar
assert "name: 'alertname'" in target_sidebar
assert "value: data['title'].split(' ')[0]" in target_sidebar
assert target_sidebar.index("data.alertSilenced = true") < target_sidebar.index(
    "this.prometheusService.setSilence(silencePayload).subscribe"
)
assert target_sidebar.index("data.alertSilenced = false") < target_sidebar.index(
    "this.prometheusService.expireSilence(data.silenceId).subscribe"
)

target_tabs = show("v17.2.7", "ceph/cluster/prometheus/prometheus-tabs/prometheus-tabs.component.html")
assert "activeCriticalAlerts" in target_tabs
assert "activeWarningAlerts" in target_tabs

affect_paths = {
    "ceph/cluster/prometheus/active-alert-list/active-alert-list.component.ts",
    "ceph/cluster/prometheus/prometheus-tabs/prometheus-tabs.component.html",
    "ceph/cluster/prometheus/prometheus-tabs/prometheus-tabs.component.ts",
    "ceph/cluster/prometheus/rules-list/rules-list.component.ts",
    "ceph/cluster/prometheus/silence-form/silence-form.component.html",
    "ceph/cluster/prometheus/silence-form/silence-form.component.ts",
    "ceph/cluster/prometheus/silence-list/silence-list.component.ts",
    "shared/components/notifications-sidebar/notifications-sidebar.component.html",
    "shared/components/notifications-sidebar/notifications-sidebar.component.ts",
    "shared/enum/icons.enum.ts",
    "shared/models/alertmanager-silence.ts",
    "shared/models/cd-notification.ts",
    "shared/models/prometheus-alerts.ts",
    "shared/services/prometheus-alert.service.ts",
    "shared/services/prometheus-silence-matcher.service.ts",
}
assert len(affect_paths) == 15
helper_path = "shared/helpers/prometheus-list-helper.ts"

affect_reason = (
    "MGR-056: Dashboard changes Prometheus stop/go signals and silence control. "
    "Severity badges are calculated from the previous alert array, notification "
    "shortcuts create a two-hour alertname-only silence and flip local state before "
    "the API succeeds, while the silence list consumes asynchronously loaded rules "
    "synchronously and overwrites its displayed matches per matcher."
)
helper_reason = (
    "MGR-056-SUPPORT: R100/0-line relocation of PrometheusListHelper from the "
    "Prometheus feature directory into shared/helpers; endpoint behavior is "
    "unchanged and the affecting alert/silence consumers are covered by MGR-056."
)

with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}

for relative in affect_paths:
    path = frontend + relative
    row = by_path[path]
    if row["upgrade_impact"]:
        assert row["upgrade_impact"] == "affect", path
        assert row["finding_id"] == "MGR-056", path
        assert row["impact_reason"] == affect_reason, path
    else:
        row["upgrade_impact"] = "affect"
        row["finding_id"] = "MGR-056"
        row["impact_reason"] = affect_reason

row = by_path[frontend + helper_path]
assert row["status"] == "R" and row["additions"] == "0" and row["deletions"] == "0"
assert row["old_path"].endswith("ceph/cluster/prometheus/prometheus-list-helper.ts")
if row["upgrade_impact"]:
    assert row["upgrade_impact"] == "trivial"
    assert row["finding_id"] == ""
    assert row["impact_reason"] == helper_reason
else:
    row["upgrade_impact"] = "trivial"
    row["finding_id"] = ""
    row["impact_reason"] = helper_reason

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(
        stream, fieldnames=fields, delimiter=";", lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)

affect = sum(row["upgrade_impact"] == "affect" for row in rows)
trivial = sum(row["upgrade_impact"] == "trivial" for row in rows)
unclassified = sum(not row["upgrade_impact"] for row in rows)
assert affect >= 252 and trivial >= 375 and unclassified <= 99
print("Classified Prometheus alert/silence frontend: 15 affect, 1 trivial")
print(f"MGR totals: affect={affect} trivial={trivial} unclassified={unclassified}")
