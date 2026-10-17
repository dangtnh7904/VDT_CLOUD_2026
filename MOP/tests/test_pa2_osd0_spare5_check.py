"""Synthetic offline regression checks; never invokes Ceph."""
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("pa2check", HERE.parent / "pa2_osd0_spare5_check.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def row(pg, members, primary=1):
    return {"pgid": pg, "state": "active+clean", "up": list(members), "acting": list(members),
            "up_primary": primary, "acting_primary": primary,
            "last_deep_scrub_stamp": "2026-10-11T03:00:00.000000+0000",
            "stat_sum": {"num_scrub_errors": 0, "num_deep_scrub_errors": 0,
                         "num_shallow_scrub_errors": 0, "num_objects": 10}}


def fixtures(osd_rule=False, colocated=False):
    members = [0, 1, 2]
    rows = {"pg_stats": [row("1.0", members), row("1.1", [4, 1, 2])]}
    om = {"fsid": "fixture-fsid", "epoch": 100, "pools": [
        {"pool": 1, "pool_name": "lab", "type": 1, "size": 3, "min_size": 2,
         "pg_num": 2, "crush_rule": 0}], "osds": [
        {"osd": n, "up": 1, "in": 1, "weight": 1, "uuid": "fixture-uuid-" + str(n)}
        for n in [0, 1, 2, 4, 5]], "pg_upmap": [], "pg_upmap_items": [],
        "pg_temp": [], "primary_temp": []}
    buckets = [
        {"id": -1, "name": "default", "type_id": 2, "items": [{"id": -3}, {"id": -5}, {"id": -7}]},
        {"id": -3, "name": "ceph-master", "type_id": 1, "items": [{"id": 0}, {"id": 4}] + ([] if colocated else [{"id": 5}])},
        {"id": -5, "name": "ceph-node2", "type_id": 1, "items": [{"id": 1}]},
        {"id": -7, "name": "ceph-node3", "type_id": 1, "items": [{"id": 2}] + ([{"id": 5}] if colocated else [])}]
    crush = {"types": [{"type_id": 0, "name": "osd"}, {"type_id": 1, "name": "host"}, {"type_id": 2, "name": "root"}],
             "devices": [{"id": n, "name": "osd." + str(n)} for n in [0, 1, 2, 4, 5]],
             "buckets": buckets, "rules": [{"rule_id": 0, "rule_name": "lab", "steps": [
                 {"op": "take", "item": -1},
                 {"op": "choose_firstn" if osd_rule else "chooseleaf_firstn", "num": 0, "type": "osd" if osd_rule else "host"},
                 {"op": "emit"}]}]}
    return rows, om, crush


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=HERE)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def call(self, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = CHECK.main(list(args))
        return code, output.getvalue()

    def plan(self, data=None, allow=False):
        rows, om, crush = data or fixtures()
        args = ["plan", "--pgs", self.write("pgs.json", rows), "--osdmap", self.write("osd.json", om),
                "--crush", self.write("crush.json", crush), "--out", str(self.root / "plan.json")]
        if allow:
            args.append("--allow-host-colocation")
        return self.call(*args)

    def progress(self, rows, accepted="", pending=None, promote=False):
        path = self.root / "accepted.txt"
        path.write_text(accepted, encoding="utf-8")
        args = ["progress", "--pgs", self.write("current.json", rows), "--plan", str(self.root / "plan.json"), "--accepted", str(path)]
        if pending:
            args += ["--pending", pending]
        if promote:
            args += ["--allow-destination-primary"]
        return self.call(*args)

    def scrub(self, before, after, requested="2026-10-11T03:01:00Z"):
        return self.call("scrub", "--before", self.write("before.json", before), "--after", self.write("after.json", after), "--requested", requested)

    def test_cli_help_and_missing_subcommand(self):
        for args, expected in ((["--help"], 0), ([], 2)):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                self.call(*args)
            self.assertEqual(caught.exception.code, expected)

    def test_timestamp_equivalent_timezone_and_fraction_forms(self):
        expected = CHECK.timestamp("2026-10-11T03:02:00.123000Z")
        for value in ("2026-10-11T03:02:00.123+0000",
                      "2026-10-11T03:02:00.123+00:00",
                      "2026-10-11T10:02:00.123+07:00",
                      "2026-10-10T23:02:00.123-0400",
                      "2026-10-11 03:02:00.123000+00:00"):
            with self.subTest(value=value):
                self.assertEqual(CHECK.timestamp(value), expected)
        self.assertEqual(CHECK.timestamp("2026-10-11T03:02:00Z"),
                         CHECK.timestamp("2026-10-11T03:02:00.000000+0000"))

    def test_timestamp_rejects_naive_and_invalid_values(self):
        for value in (None, "2026-10-11T03:02:00", "2026-02-30T03:02:00Z",
                      "2026-10-11T03:02:00+24:00", "not-a-date",
                      "2026-10-11T03:02:00.1234567Z"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CHECK.timestamp(value)

    def test_valid_host_replacement_and_nested_pg_schema(self):
        data = fixtures()
        data = ({"pg_map": data[0]}, data[1], data[2])
        code, message = self.plan(data)
        self.assertEqual(code, 0, message)
        plan = json.loads((self.root / "plan.json").read_text())
        self.assertEqual(plan["handoff"]["1.0"]["expected"], [5, 1, 2])
        self.assertEqual(plan["osd_uuids"]["5"], "fixture-uuid-5")
        self.assertEqual(len(plan["crush_sha256"]), 64)

    def test_host_conflict_even_with_lab_ack(self):
        code, message = self.plan(fixtures(colocated=True), allow=True)
        self.assertEqual(code, 1)
        self.assertIn("1.0", message)
        self.assertIn("ceph-node3", message)
        self.assertIn("acknowledgement cannot override CRUSH", message)

    def test_osd_rule_explicit_exception(self):
        code, message = self.plan(fixtures(osd_rule=True, colocated=True), allow=True)
        self.assertEqual(code, 0, message)
        plan = json.loads((self.root / "plan.json").read_text())
        self.assertEqual(plan["host_colocation_exceptions"][0]["hosts"], {"ceph-node3": [5, 2]})

    def test_osd_rule_requires_ack(self):
        self.assertEqual(self.plan(fixtures(osd_rule=True, colocated=True))[0], 1)

    def test_invalid_and_incomplete_pg_dumps(self):
        for bad in ({}, {"pg_stats": []}, {"pg_stats": [row("1.0", [0, 1, 2])]}, {"pg_stats": [row("1.0", [0, 1, 2])] * 2}):
            with self.subTest(bad=bad):
                self.assertEqual(self.plan((bad, fixtures()[1], fixtures()[2]))[0], 1)

    def test_spare_existing_membership_rejected(self):
        data = fixtures()
        data[0]["pg_stats"][1] = row("1.1", [5, 1, 2])
        self.assertEqual(self.plan(data)[0], 1)

    def test_source_primary_rejected(self):
        data = fixtures()
        data[0]["pg_stats"][0] = row("1.0", [0, 1, 2], 0)
        self.assertEqual(self.plan(data)[0], 1)

    def test_existing_override_conflicts(self):
        data = fixtures()
        data[1]["pg_upmap_items"] = [{"pgid": "1.0", "mappings": [{"from": 0, "to": 4}]}]
        self.assertEqual(self.plan(data)[0], 1)
        data[1]["pg_upmap_items"] = [{"pgid": "1.1", "mappings": [{"from": 4, "to": 5}]}]
        self.assertEqual(self.plan(data)[0], 1)

    def test_device_class_take_shadow_exclusion(self):
        data = fixtures()
        data[2]["buckets"].append({"id": -9, "name": "default~hdd", "type_id": 2, "items": [{"id": 0}, {"id": 1}, {"id": 2}, {"id": 4}]})
        data[2]["rules"][0]["steps"][0]["item"] = -9
        code, message = self.plan(data)
        self.assertEqual(code, 1)
        self.assertIn("root/class", message)

    def test_progress_pending_converged_and_wait(self):
        self.assertEqual(self.plan()[0], 0)
        data = fixtures()[0]
        self.assertEqual(self.progress(data, pending="1.0")[0], 3)
        data["pg_stats"][0]["up"] = [5, 1, 2]
        data["pg_stats"][0]["state"] = "active+remapped+backfilling"
        self.assertEqual(self.progress(data, pending="1.0")[0], 3)
        data["pg_stats"][0] = row("1.0", [5, 1, 2])
        self.assertEqual(self.progress(data, pending="1.0")[0], 0)
        self.assertEqual(self.progress(data, accepted="1.0\n")[0], 0)

    def test_progress_changed_extra_pg_holds(self):
        self.assertEqual(self.plan()[0], 0)
        data = fixtures()[0]
        data["pg_stats"][1] = row("1.1", [4, 2, 1])
        self.assertEqual(self.progress(data)[0], 1)
        data = fixtures()[0]
        data["pg_stats"].append(row("1.2", [4, 1, 2]))
        self.assertEqual(self.progress(data)[0], 1)

    def test_progress_wrong_pending_mapping_is_hold(self):
        self.assertEqual(self.plan()[0], 0)
        data = fixtures()[0]
        data["pg_stats"][0] = row("1.0", [4, 1, 2])
        self.assertEqual(self.progress(data, pending="1.0")[0], 1)

    def test_promotion_allows_order_and_primary_but_not_membership(self):
        self.assertEqual(self.plan()[0], 0)
        data = fixtures()[0]
        data["pg_stats"][0] = row("1.0", [5, 2, 1], 5)
        self.assertEqual(self.progress(data, accepted="1.0\n")[0], 1)
        self.assertEqual(self.progress(data, accepted="1.0\n", promote=True)[0], 0)
        data["pg_stats"][0] = row("1.0", [5, 4, 1], 5)
        self.assertEqual(self.progress(data, accepted="1.0\n", promote=True)[0], 1)

    def test_isolation_requires_nonempty_schema(self):
        self.assertEqual(self.call("isolate", "--pgs", self.write("empty.json", {}), "--osd", "5")[0], 1)
        self.assertEqual(self.call("isolate", "--pgs", self.write("valid.json", fixtures()[0]), "--osd", "5")[0], 0)
        self.assertEqual(self.call("isolate", "--pgs", self.write("valid.json", fixtures()[0]), "--osd", "0")[0], 1)

    def test_scrub_fresh_and_stale_and_pending(self):
        before = row("1.0", [0, 1, 2])
        after = copy.deepcopy(before)
        self.assertEqual(self.scrub(before, after)[0], 3)
        after["last_deep_scrub_stamp"] = "2026-10-11T03:02:00.123456+0000"
        self.assertEqual(self.scrub(before, after)[0], 0)
        after["state"] = "active+clean+scrubbing+deep"
        self.assertEqual(self.scrub(before, after)[0], 3)

    def test_scrub_missing_nonzero_or_boolean_errors_hold(self):
        before = row("1.0", [0, 1, 2])
        for value in (None, 1, False, "0"):
            with self.subTest(value=value):
                after = copy.deepcopy(before)
                after["last_deep_scrub_stamp"] = "2026-10-11T03:02:00Z"
                if value is None:
                    del after["stat_sum"]["num_deep_scrub_errors"]
                else:
                    after["stat_sum"]["num_deep_scrub_errors"] = value
                self.assertEqual(self.scrub(before, after)[0], 1)

    def test_scrub_mapping_change_or_pre_request_completion_holds(self):
        before = row("1.0", [0, 1, 2])
        after = row("1.0", [5, 1, 2])
        after["last_deep_scrub_stamp"] = "2026-10-11T03:02:00Z"
        self.assertEqual(self.scrub(before, after)[0], 1)
        after = copy.deepcopy(before)
        after["last_deep_scrub_stamp"] = "2026-10-11T03:00:30Z"
        self.assertEqual(self.scrub(before, after)[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
