import importlib.util
import ast
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "collect_osd.py"
SPEC = importlib.util.spec_from_file_location("collect_osd", MODULE_PATH)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


FSID = "11111111-2222-3333-4444-555555555555"


class FakeRunner:
    def __call__(self, args):
        command = " ".join(args)
        data = self._data(command)
        return {
            "command": list(args),
            "started_at": "2026-10-08T05:00:00Z",
            "completed_at": "2026-10-08T05:00:01Z",
            "exit_code": 0,
            "stderr": "",
            "format": "json" if not isinstance(data, str) else "text",
            "data": data,
        }

    @staticmethod
    def _data(command):
        if command == "ceph fsid":
            return FSID
        if "ceph osd df tree" in command:
            return {
                "nodes": [
                    {
                        "id": 7,
                        "type": "osd",
                        "device_class": "hdd",
                        "kb": 10_000,
                        "kb_used": 2_500,
                        "kb_avail": 7_500,
                        "utilization": 25.0,
                        "pgs": 2,
                        "crush_weight": 9.7,
                        "reweight": 1.0,
                    }
                ]
            }
        if "ceph osd tree" in command:
            return {"nodes": [{"id": 7, "name": "osd.7", "type": "osd", "status": "up"}]}
        if "ceph osd dump" in command:
            return {"osds": [{"osd": 7, "up": 1, "in": 1, "primary_affinity": 1.0}]}
        if "ceph osd metadata 7" in command:
            return {
                "id": 7,
                "osd_fsid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                "hostname": "storage-02",
                "ceph_version": "ceph version 17.2.7",
                "front_addr": "[v2:10.10.0.22:6800/1,v1:10.10.0.22:6801/1]",
                "back_addr": "v2:10.20.0.22:6802/1",
                "bluestore_bdev_partition_path": "/dev/mapper/ceph-data",
                "bluestore_bdev_devices": "sdc",
                "bluestore_bdev_size": "10240000",
                "bluefs_db_partition_path": "/dev/nvme0n1p2",
                "bluefs_db_devices": "nvme0n1",
            }
        if "ceph osd find 7" in command:
            return {"osd": 7, "crush_location": {"root": "default", "rack": "rack-a", "host": "storage-02"}}
        if "ceph pg ls-by-primary osd.7" in command:
            return {"pg_stats": [{"pgid": "1.2"}]}
        if "ceph pg ls-by-osd osd.7" in command:
            return {"pg_stats": [{"pgid": "1.2"}, {"pgid": "1.3"}]}
        if "ceph config show-with-defaults osd.7" in command:
            return {"osd_memory_target": "4294967296"}
        if "ceph device ls-by-daemon osd.7" in command:
            return [{"devid": "ATA_disk_SERIAL"}]
        if "ceph status" in command:
            return {"health": {"status": "HEALTH_OK"}}
        return {}


class CollectorTests(unittest.TestCase):
    def test_cli_sudo_ceph_prefix_is_fixed_and_opt_in(self):
        for options, prefix in (([], []), (["--sudo-ceph"], ["sudo", "-n"])):
            with self.subTest(options=options):
                fake = FakeRunner()
                seen = []

                def runner(args, **kwargs):
                    seen.append(list(args))
                    return fake(args[len(prefix):])

                with patch.object(collector, "run_command", side_effect=runner):
                    with redirect_stdout(io.StringIO()):
                        result = collector.main(["--osd", "7", *options])
                self.assertEqual(result, 0)
                self.assertEqual(seen[0], [*prefix, "ceph", "fsid"])
                self.assertTrue(all(command[:len(prefix)] == prefix for command in seen))

    def test_cli_starts_without_ceph_for_version_and_help(self):
        for option, expected in (("--version", collector.COLLECTOR_VERSION), ("--help", "--keyring")):
            with self.subTest(option=option):
                result = subprocess.run(
                    [sys.executable, "-B", str(MODULE_PATH), option],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_run_command_captures_json_and_text_with_separate_stderr(self):
        for output, expected_format, expected_data in (
            ('{"osd": 0}', "json", {"osd": 0}),
            (FSID, "text", FSID),
        ):
            with self.subTest(output=output):
                result = collector.run_command([
                    sys.executable, "-c",
                    "import sys; print({!r}); sys.stderr.write('diagnostic')".format(output),
                ])
                self.assertEqual(result["exit_code"], 0)
                self.assertEqual(result["format"], expected_format)
                self.assertEqual(result["data"], expected_data)
                self.assertEqual(result["stderr"], "diagnostic")

    def test_run_command_preserves_real_process_failure(self):
        result = collector.run_command([
            sys.executable, "-c",
            "import sys; sys.stderr.write('missing keyring'); sys.exit(13)",
        ])
        self.assertEqual(result["exit_code"], 13)
        self.assertEqual(result["stderr"], "missing keyring")
        self.assertEqual(result["error"], "COMMAND_FAILED")
        self.assertNotIn("data", result)

    def test_run_command_times_out(self):
        with self.assertRaisesRegex(collector.CollectionError, "command timed out"):
            collector.run_command(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout_seconds=0.1,
            )

    def test_main_writes_baseline_in_a_new_directory(self):
        fake = FakeRunner()
        with tempfile.TemporaryDirectory(prefix="osd-collector-test-") as directory:
            output = Path(directory) / "evidence" / "before.json"
            with patch.object(collector, "run_command", side_effect=lambda args, **kwargs: fake(args)):
                with redirect_stdout(io.StringIO()):
                    result = collector.main(["--osd", "7", "--output", str(output)])
            self.assertEqual(result, 0)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["cluster_fsid"], FSID)
            self.assertEqual(saved["osds"][0]["identity"]["osd_id"], 7)
            self.assertEqual(list(output.parent.iterdir()), [output])

    def test_atomic_write_preserves_existing_baseline_if_replace_fails(self):
        with tempfile.TemporaryDirectory(prefix="osd-collector-test-") as directory:
            output = Path(directory) / "before.json"
            output.write_text('{"previous": true}\n', encoding="utf-8")
            with patch.object(collector.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    collector._atomic_write(output, {"new": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"previous": True})
            self.assertEqual(list(output.parent.iterdir()), [output])

    def test_fsid_failure_reports_exit_code_and_stderr(self):
        def runner(args):
            return {
                "command": list(args),
                "exit_code": 13,
                "stderr": "RADOS permission denied",
                "error": "COMMAND_FAILED",
            }

        with self.assertRaisesRegex(
            collector.CollectionError,
            r"exit_code=13.*RADOS permission denied",
        ):
            collector.collect(osd_ids=[7], runner=runner)

    def test_collects_requested_osd_summary_and_raw_evidence(self):
        result = collector.collect(osd_ids=[7], runner=FakeRunner())

        self.assertEqual(result["cluster_fsid"], FSID)
        self.assertEqual(result["osd_count"], 1)
        osd = result["osds"][0]
        self.assertEqual(osd["identity"]["hostname"], "storage-02")
        self.assertEqual(osd["network"]["public_ip"], "10.10.0.22")
        self.assertEqual(osd["devices"]["data"]["path"], "/dev/mapper/ceph-data")
        self.assertEqual(osd["devices"]["data"]["physical_devices"], ["/dev/sdc"])
        self.assertEqual(osd["capacity"]["total_bytes"], 10_240_000)
        self.assertEqual(osd["capacity"]["used_percent"], 25.0)
        self.assertEqual(osd["placement_groups"]["count"], 2)
        self.assertEqual(osd["placement_groups"]["primary_count"], 1)
        self.assertIn("config_effective", osd["evidence"])
        self.assertIn("config_dump", result["cluster_evidence"])

    def test_all_discovers_osd_ids_from_df(self):
        result = collector.collect(osd_ids=None, runner=FakeRunner())

        self.assertEqual([row["identity"]["osd_id"] for row in result["osds"]], [7])

    def test_pacific_osd_uuid_comes_from_matching_osdmap_when_metadata_omits_it(self):
        fake = FakeRunner()
        expected = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

        def runner(args):
            result = fake(args)
            if "ceph osd metadata" in " ".join(args):
                result["data"].pop("osd_fsid")
            if "ceph osd dump" in " ".join(args):
                result["data"]["osds"].append({"osd": 9, "uuid": "not-the-requested-osd"})
                result["data"]["osds"][0]["uuid"] = expected
            return result

        result = collector.collect(osd_ids=[7], runner=runner)
        self.assertEqual(result["osds"][0]["identity"]["osd_fsid"], expected)
        self.assertEqual(result["cluster_evidence"]["osd_dump"]["data"]["osds"][0]["uuid"], expected)

    def test_ceph_auth_arguments_are_passed_before_subcommands(self):
        seen = []
        fake = FakeRunner()

        def runner(args):
            seen.append(list(args))
            stripped = [args[0], *args[7:]]
            return fake(stripped)

        collector.collect(
            osd_ids=[7],
            ceph_args=[
                "--conf",
                "/etc/ceph/ceph.conf",
                "--name",
                "client.admin",
                "--keyring",
                "/etc/ceph/ceph.client.admin.keyring",
            ],
            runner=runner,
        )

        self.assertEqual(seen[0][:7], [
            "ceph",
            "--conf",
            "/etc/ceph/ceph.conf",
            "--name",
            "client.admin",
            "--keyring",
            "/etc/ceph/ceph.client.admin.keyring",
        ])
        self.assertEqual(seen[0][7:], ["fsid"])

    def test_missing_optional_device_command_is_partial_not_zero(self):
        fake = FakeRunner()

        def runner(args):
            if "ceph device ls-by-daemon" in " ".join(args):
                return {"command": list(args), "exit_code": 22, "stderr": "unsupported"}
            return fake(args)

        result = collector.collect(osd_ids=[7], runner=runner)

        osd = result["osds"][0]
        self.assertEqual(osd["quality"], "PARTIAL")
        self.assertIsNone(osd["devices"]["wal"]["size_bytes"])
        self.assertTrue(any(error["command"].startswith("ceph device") for error in osd["errors"]))

    def test_required_osd_evidence_failure_is_inconclusive_without_losing_other_data(self):
        fake = FakeRunner()

        def runner(args):
            if "ceph pg ls-by-primary" in " ".join(args):
                return {"command": list(args), "exit_code": 5, "stderr": "daemon unavailable"}
            return fake(args)

        result = collector.collect(osd_ids=[7], runner=runner)

        osd = result["osds"][0]
        self.assertEqual(result["quality"], "INCONCLUSIVE")
        self.assertEqual(osd["quality"], "INCONCLUSIVE")
        self.assertIsNone(osd["placement_groups"]["primary_count"])
        self.assertIn("PRIMARY_PG_LIST_UNAVAILABLE", osd["warnings"])
        self.assertTrue(any(error["required"] for error in osd["errors"]))


class EnvironmentCollectorTests(unittest.TestCase):
    @staticmethod
    def fake_runner(args):
        output = (
            "NTP=yes\nNTPSynchronized=yes\nTimezone=UTC\nLocalRTC=no\n"
            if args[0] == "timedatectl" else "OpenSSH_9.6p1"
            if args[0] == "ssh" else "ceph version 16.2.15"
        )
        return {
            "command": list(args), "started_at": "2026-10-12T00:00:00Z",
            "completed_at": "2026-10-12T00:00:01Z", "exit_code": 0,
            "data": "" if args[0] == "ssh" else output,
            "stderr": output if args[0] == "ssh" else "", "format": "text",
        }

    def test_module_still_parses_as_python_36(self):
        ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 6))

    def test_complete_environment_has_fixed_scope_and_real_source_status(self):
        seen = []

        def runner(args):
            seen.append(list(args))
            return self.fake_runner(args)

        with patch.object(collector, "_environment_os", return_value={"id": "ubuntu", "quality": "VALID", "source": "/etc/os-release"}), patch.dict(collector.os.environ, {"SHELL": "/bin/bash"}):
            result = collector.collect_environment(runner=runner)
        self.assertEqual(result["kind"], "CEPH_CLIENT_ENVIRONMENT")
        self.assertEqual(result["collector_version"], "1.0.5")
        self.assertEqual(result["scope"], "SSH_CLIENT_HOST_ONLY")
        self.assertEqual(result["quality"], "VALID")
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["host"]["hostname"])
        self.assertEqual(result["tools"]["ssh"]["version"], "OpenSSH_9.6p1")
        self.assertTrue(result["clock"]["synchronized"])
        self.assertFalse(result["clock"]["local_rtc"])
        self.assertEqual(len(seen), 7)
        self.assertEqual(set(command[0] for command in seen), {"ceph", "rbd", "rados", "ssh", "osdmaptool", "crushtool", "timedatectl"})
        self.assertNotIn("cluster_fsid", result)
        self.assertNotIn("osds", result)
        self.assertIn("not all cluster", result["coverage"]["host_scope"])

    def test_missing_tool_and_clock_remain_unknown_not_zero_or_synchronized(self):
        def runner(args):
            if args[0] in {"rbd", "timedatectl"}:
                return {"exit_code": None, "error": "COMMAND_NOT_FOUND", "stderr": ""}
            return self.fake_runner(args)

        result = collector.collect_environment(runner=runner)
        self.assertEqual(result["quality"], "PARTIAL")
        self.assertFalse(result["tools"]["rbd"]["available"])
        self.assertIsNone(result["tools"]["rbd"]["version"])
        self.assertIsNone(result["clock"]["synchronized"])
        self.assertEqual(result["clock"]["reason"], "CLOCK_STATUS_UNAVAILABLE")

    def test_unsynchronized_clock_is_evidenced_but_not_reported_as_safe(self):
        def runner(args):
            result = self.fake_runner(args)
            if args[0] == "timedatectl":
                result["data"] = "NTP=yes\nNTPSynchronized=no\nTimezone=UTC\nLocalRTC=no"
            return result

        result = collector.collect_environment(runner=runner)
        self.assertFalse(result["clock"]["synchronized"])
        self.assertEqual(result["clock"]["quality"], "VALID")
        self.assertEqual(result["quality"], "PARTIAL")
        self.assertTrue(any(error["code"] == "CLOCK_UNSYNCHRONIZED" for error in result["errors"]))

    def test_environment_cli_sudo_applies_only_to_fixed_ceph_version_command(self):
        seen = []

        def runner(args, **kwargs):
            seen.append((list(args), kwargs))
            return self.fake_runner(args[2:] if args[:2] == ["sudo", "-n"] else args)

        stream = io.StringIO()
        with patch.object(collector, "run_environment_command", side_effect=runner), redirect_stdout(stream):
            code = collector.main(["--environment-only", "--sudo-ceph", "--timeout", "2"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["kind"], "CEPH_CLIENT_ENVIRONMENT")
        ceph_commands = [command for command, _ in seen if "ceph" in command]
        self.assertEqual(ceph_commands, [["sudo", "-n", "ceph", "--version"]])
        self.assertEqual(sum(command[0] == "sudo" for command, _ in seen), 1)
        self.assertTrue(all(kwargs["timeout_seconds"] == 2 for _, kwargs in seen))

    def test_environment_mode_is_mutually_exclusive_with_osd_selection(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            collector.parse_args(["--environment-only", "--all"])

    def test_environment_probes_are_bounded_and_truncation_is_not_valid_version(self):
        result = collector.run_environment_command([
            sys.executable, "-c",
            "import sys; sys.stdout.write('x'*100000); sys.stderr.write('y'*100000)",
        ])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["error"], "OUTPUT_TRUNCATED")
        self.assertEqual(len(result["data"].encode("utf-8")), collector.ENVIRONMENT_OUTPUT_BYTES)
        self.assertEqual(len(result["stderr"].encode("utf-8")), collector.ENVIRONMENT_ERROR_BYTES)
        self.assertEqual(result["stdout_bytes"], 100000)

        def runner(args):
            return {"exit_code": 0, "data": "x" * 100000, "stderr": ""}

        result = collector.collect_environment(runner=runner)
        self.assertIsNone(result["tools"]["ceph"]["version"])
        self.assertEqual(result["tools"]["ceph"]["quality"], "PARTIAL")
        self.assertLessEqual(len(result["tools"]["ceph"]["evidence"]["data"]), collector.ENVIRONMENT_OUTPUT_BYTES)

    def test_environment_probe_timeout_preserves_partial_evidence(self):
        result = collector.run_environment_command([
            sys.executable, "-c", "import time; time.sleep(10)",
        ], timeout_seconds=0.05)
        self.assertEqual(result["error"], "COMMAND_TIMED_OUT")
        self.assertNotEqual(result["exit_code"], 0)

    def test_only_whitelisted_os_release_metadata_is_collected(self):
        with patch("builtins.open", return_value=io.BytesIO(b'ID=ubuntu\nNAME="Ubuntu"\nSECRET_TOKEN=must-not-appear\n')):
            data = collector._environment_os()
        self.assertEqual(data["id"], "ubuntu")
        self.assertEqual(data["name"], "Ubuntu")
        self.assertNotIn("must-not-appear", json.dumps(data))

    def test_no_unrelated_environment_variables_or_secret_process_arguments(self):
        with patch.dict(collector.os.environ, {"SHELL": "/bin/bash", "SECRET_TOKEN": "must-not-appear"}):
            with patch.object(collector.os, "readlink", return_value="/usr/sbin/sshd"):
                result = collector._environment_shell()
        self.assertEqual(result["configured_path"], "/bin/bash")
        self.assertEqual(result["observed_parent_executable"], "/usr/sbin/sshd")
        self.assertNotIn("must-not-appear", json.dumps(result))

    def test_no_shell_sources_make_environment_explicitly_partial(self):
        with patch.dict(collector.os.environ, {}, clear=True), patch.object(collector.os, "readlink", side_effect=OSError("unavailable")), patch.object(collector, "_environment_os", return_value={"id": "ubuntu", "quality": "VALID"}):
            result = collector.collect_environment(runner=self.fake_runner)
        self.assertIsNone(result["shell"]["configured_path"])
        self.assertIsNone(result["shell"]["observed_parent_executable"])
        self.assertEqual(result["shell"]["quality"], "PARTIAL")
        self.assertEqual(result["shell"]["reason"], "SHELL_SOURCE_UNAVAILABLE")
        self.assertEqual(result["quality"], "PARTIAL")
        self.assertTrue(any(error["code"] == "SHELL_SOURCE_UNAVAILABLE" for error in result["errors"]))

    def test_nonfinite_timeouts_are_rejected(self):
        for value in ("nan", "inf", "-inf", "0"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()):
                self.assertEqual(collector.main(["--environment-only", "--timeout=" + value]), 2)


if __name__ == "__main__":
    unittest.main()
