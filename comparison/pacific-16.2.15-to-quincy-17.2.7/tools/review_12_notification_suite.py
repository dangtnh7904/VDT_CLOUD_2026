"""Classify the target-only RGW bucket-notification QA suite and support."""

import csv
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
repo = root.parents[1] / "ceph16.2.15" / "ceph"


def show(tag: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{tag}:{path}"],
        text=True,
        encoding="utf-8",
    )


def exists(tag: str, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{tag}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


suite_paths = {
    "qa/suites/rgw/notifications/%",
    "qa/suites/rgw/notifications/.qa",
    "qa/suites/rgw/notifications/beast.yaml",
    "qa/suites/rgw/notifications/bluestore-bitmap.yaml",
    "qa/suites/rgw/notifications/fixed-2.yaml",
    "qa/suites/rgw/notifications/overrides.yaml",
    "qa/suites/rgw/notifications/supported-all-distro$/$",
    "qa/suites/rgw/notifications/supported-all-distro$/centos_8.yaml",
    "qa/suites/rgw/notifications/tasks/+",
    "qa/suites/rgw/notifications/tasks/0-install.yaml",
    "qa/suites/rgw/notifications/tasks/test_amqp.yaml",
    "qa/suites/rgw/notifications/tasks/test_kafka.yaml",
    "qa/suites/rgw/notifications/tasks/test_others.yaml",
}
support_paths = {
    "src/test/rgw/bucket_notification/README.rst",
    "src/test/rgw/bucket_notification/__init__.py",
    "src/test/rgw/bucket_notification/api.py",
    "src/test/rgw/bucket_notification/bntests.conf.SAMPLE",
    "src/test/rgw/bucket_notification/bootstrap",
    "src/test/rgw/bucket_notification/requirements.txt",
    "src/test/rgw/bucket_notification/setup.py",
}

for path in suite_paths | support_paths:
    assert not exists("v16.2.15", path), path
    assert exists("v17.2.7", path), path

# The endpoint suite deliberately fixes the main environment while splitting
# transport coverage into independent task variants.
assert show("v17.2.7", "qa/suites/rgw/notifications/.qa").strip() == "../.qa"
assert show("v17.2.7", "qa/suites/rgw/notifications/beast.yaml").strip() == ".qa/rgw_frontend/beast.yaml"
assert show("v17.2.7", "qa/suites/rgw/notifications/bluestore-bitmap.yaml").strip() == ".qa/objectstore/bluestore-bitmap.yaml"
assert show("v17.2.7", "qa/suites/rgw/notifications/fixed-2.yaml").strip() == ".qa/clusters/fixed-2.yaml"
assert show("v17.2.7", "qa/suites/rgw/notifications/supported-all-distro$/centos_8.yaml").strip() == "../.qa/distros/supported-all-distro/centos_8.yaml"

overrides = show("v17.2.7", "qa/suites/rgw/notifications/overrides.yaml")
assert "debug rgw: 20" in overrides
assert "rgw crypt s3 kms backend: testing" in overrides
assert "storage classes: LUKEWARM, FROZEN" in overrides

install = show("v17.2.7", "qa/suites/rgw/notifications/tasks/0-install.yaml")
assert "- openssl_keys:" in install
assert "- rgw:" in install
assert "rgw lc debug interval: 10" in install

amqp = show("v17.2.7", "qa/suites/rgw/notifications/tasks/test_amqp.yaml")
kafka = show("v17.2.7", "qa/suites/rgw/notifications/tasks/test_kafka.yaml")
others = show("v17.2.7", "qa/suites/rgw/notifications/tasks/test_others.yaml")
assert "- rabbitmq:" in amqp and 'extra_attr: ["amqp_test"]' in amqp
assert "- kafka:" in kafka and "kafka_version: 2.6.0" in kafka
assert 'extra_attr: ["kafka_test"]' in kafka
assert "- notification-tests:" in others and "extra_attr" not in others

# The task implementation is cross-owner evidence: default/basic selection
# excludes transport/manual categories, while task-specific YAML overrides it.
# It clones tests from the job's suite branch/repository; the suite itself does
# not pin v16.2.15/v17.2.7 or a test SHA.
notification_task = show("v17.2.7", "qa/tasks/notification_tests.py")
assert "branch = ctx.config.get('suite_branch')" in notification_task
assert "repo = ctx.config.get('suite_repo')" in notification_task
assert "args=['git', 'clone', '-b', branch, repo" in notification_task
assert "sha1 = client_config.get('sha1')" in notification_task
assert 'attr = ["!kafka_test", "!amqp_test", "!amqp_ssl_test", "!modification_required", "!manual_test"]' in notification_task
assert "if 'extra_attr' in client_config:" in notification_task
assert "'-a', ','.join(attr)" in notification_task

# The target test module contains the three selected families, but important
# persistent/recovery/idle paths remain manual or modification-required.
tests = show("v17.2.7", "src/test/rgw/bucket_notification/test_bn.py")
for marker in ("@attr('basic_test')", "@attr('http_test')", "@attr('amqp_test')", "@attr('kafka_test')"):
    assert marker in tests
for marker in ("@attr('manual_test')", "@attr('modification_required')", "@attr('amqp_ssl_test')"):
    assert marker in tests
assert "test_ps_s3_notification_kafka_idle_behaviour" in tests
assert "test_ps_s3_persistent_gateways_recovery" in tests
assert "test_ps_s3_persistent_multiple_gateways" in tests

readme = show("v17.2.7", "src/test/rgw/bucket_notification/README.rst")
assert "Kafka tests" in readme and "RabbitMQ tests" in readme
assert "-a 'kafka_test'" in readme and "-a 'amqp_test'" in readme
requirements = show("v17.2.7", "src/test/rgw/bucket_notification/requirements.txt")
assert "boto3" in requirements and "nose" in requirements
bootstrap = show("v17.2.7", "src/test/rgw/bucket_notification/bootstrap")
assert "virtualenv" in bootstrap and "requirements.txt" in bootstrap


reason = (
    "RGW-035: Adds the target-only bucket-notification validation matrix and its local test infrastructure for "
    "basic/HTTP, AMQP and Kafka endpoints; the job clones tests from suite_branch/suite_repo rather than pinning "
    "the compared tag SHAs, while manual, modification-required and AMQP-SSL cases are excluded from default variants."
)
updates = {path: ("affect", "RGW-035", reason) for path in suite_paths | support_paths}

csv_path = root / "12-rgw.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(stream, delimiter=";")
    fields = reader.fieldnames
    rows = list(reader)
assert fields is not None
by_path = {row["path"]: row for row in rows}
assert len(by_path) == len(rows)
for path, (impact, finding, impact_reason) in updates.items():
    row = by_path[path]
    if not row["upgrade_impact"] and not row["finding_id"] and not row["impact_reason"]:
        row.update(upgrade_impact=impact, finding_id=finding, impact_reason=impact_reason)
    else:
        assert row["upgrade_impact"] == impact, path
        assert row["finding_id"] == finding, path
        assert row["impact_reason"] == impact_reason, path

with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Classified {len(updates)} bucket-notification suite/support rows affect")
