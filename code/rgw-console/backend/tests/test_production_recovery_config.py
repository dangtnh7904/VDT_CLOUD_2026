"""Synthetic private copies only; no deployed secret, Docker or network access."""
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from production_recovery_config import (
    ALLOWED_FILES, MAX_FILE_BYTES, MAX_MANIFEST_BYTES, REQUIRED_FILES,
    RecoveryConfigError, account_roles, collect, compare, digest, main,
    no_link_path, parse_env, regular_bytes, safe_name, validate_reference,
)


PROJECT = 'storage-lab-console-staging-synthetic'
IMAGE = 'dang7904/storage-lab-console@sha256:' + 'a' * 64
HASH = 'pbkdf2_sha256$600000$' + base64.b64encode(b's' * 32).decode() + '$' + base64.b64encode(b'h' * 32).decode()
SENTINEL = 'SYNTHETIC_SECRET_NEVER_IN_RECEIPT_0123456789'


class RecoveryConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'private-source-copy'
        self.source.mkdir()
        self.fixture(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def fixture(directory):
        for name in REQUIRED_FILES:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((SENTINEL + '\n').encode())
        for name in ('compose.production.yml', 'compose.access-control.yml', 'nginx/production.conf'):
            shutil.copyfile(SCRIPTS.parent / 'deploy' / name, directory / name)
        (directory / 'config/profiles/production.yaml').write_text('{}\n')
        env = ('COMPOSE_PROJECT_NAME=' + PROJECT + '\nAPP_INSTANCE_ID=' + PROJECT
               + '\nAPP_DEPLOYMENT_SCOPE=staging\nSTORAGE_LAB_CONSOLE_IMAGE=' + IMAGE
               + '\nPOSTGRES_IMAGE=postgres:16-alpine@sha256:' + 'b' * 64
               + '\nINGRESS_IMAGE=nginx:stable-alpine@sha256:' + 'c' * 64
               + '\nRBD_SSH_HOST_KEY_REQUIRED=true\nRBD_SSH_HOST_KEY_SHA256=SHA256:' + 'd' * 43
               + '\nCONSOLE_AUTH_USERNAME=\nCONSOLE_AUTH_PASSWORD_HASH_FILE=\n')
        (directory / '.env').write_text(env)
        users = [{'username': 'synthetic-' + role, 'role': role, 'password_hash': HASH}
                 for role in ('viewer', 'operator', 'admin')]
        (directory / 'secrets/console_users.json').write_text(json.dumps({'version': 1, 'users': users}))
        (directory / 'secrets/console_password_hash').write_text(HASH + '\n')
        (directory / 'secrets/database_runtime_password').write_text('r' * 40 + '\n')
        (directory / 'secrets/postgres_password').write_text('m' * 40 + '\n')
        (directory / 'secrets/database_url').write_text('postgresql://storage_lab_runtime:' + 'r' * 40 + '@postgres:5432/storage_lab_console\n')
        (directory / 'secrets/migration_database_url').write_text('postgresql://storage_lab_console:' + 'm' * 40 + '@postgres:5432/storage_lab_console\n')

    def invoke(self, directory=None, report=None, restored=False, reference=None, extra=()):
        arguments = ['--restored-directory' if restored else '--deployment-directory',
                     str(directory or self.source), '--confirm-private-copy',
                     '--expected-project', PROJECT, '--expected-instance', PROJECT,
                     '--expected-image', IMAGE, '--report', str(report or self.root / 'manifest.json')]
        if reference:
            arguments += ['--reference-manifest', str(reference),
                          '--reference-manifest-sha256', digest(reference.read_bytes())]
        arguments += list(extra)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(arguments)
        return code, json.loads(stdout.getvalue())

    def source_manifest(self):
        manifest = self.root / 'source-manifest.json'
        self.assertEqual(self.invoke(report=manifest)[0], 0)
        return manifest

    def test_source_receipt_exposes_only_allowlisted_names_hashes_and_safe_facts(self):
        before = {name: (self.source / name).read_bytes() for name in REQUIRED_FILES}
        report = self.root / 'manifest.json'
        code, stdout = self.invoke(report=report)
        self.assertEqual(code, 0)
        payload = json.loads(report.read_bytes())
        self.assertEqual(payload['mode'], 'SOURCE_MANIFEST')
        self.assertEqual(payload['identity']['project'], PROJECT)
        self.assertEqual(payload['facts']['console_role_counts'], {'viewer': 1, 'operator': 1, 'admin': 1})
        self.assertEqual(set(item['name'] for item in payload['files']), set(REQUIRED_FILES))
        encoded = report.read_text() + json.dumps(stdout)
        for sensitive in (SENTINEL, str(self.source), 'r' * 40, 'm' * 40, HASH, 'postgresql://', 'synthetic-admin'):
            self.assertNotIn(sensitive, encoded)
        self.assertEqual(before, {name: (self.source / name).read_bytes() for name in REQUIRED_FILES})
        self.assertEqual(stdout['receipt_sha256'], hashlib.sha256(report.read_bytes()).hexdigest())

    def test_separate_copy_matches_source_without_mutating_either_copy(self):
        manifest = self.source_manifest()
        restored = self.root / 'private-restored-copy'
        shutil.copytree(self.source, restored)
        before = {name: (restored / name).read_bytes() for name in REQUIRED_FILES}
        output = self.root / 'restore-report.json'
        code, _ = self.invoke(restored, output, True, manifest)
        self.assertEqual(code, 0)
        report = json.loads(output.read_bytes())
        self.assertEqual(report['mode'], 'RESTORED_COPY_VERIFICATION')
        self.assertEqual(report['comparison'], {'missing': [], 'unexpected': [], 'changed': [], 'matched': True})
        self.assertEqual(before, {name: (restored / name).read_bytes() for name in REQUIRED_FILES})

    def test_changed_config_is_detected_with_no_contents_in_receipt(self):
        manifest = self.source_manifest()
        restored = self.root / 'restored'; shutil.copytree(self.source, restored)
        (restored / 'config/profiles/production.yaml').write_text('private_note: ' + SENTINEL)
        output = self.root / 'changed-report.json'
        code, _ = self.invoke(restored, output, True, manifest)
        self.assertEqual(code, 1)
        report = json.loads(output.read_bytes())
        self.assertEqual(report['comparison']['changed'], ['config/profiles/production.yaml'])
        self.assertNotIn(SENTINEL, output.read_text())

    def test_missing_required_and_optional_files_are_detected(self):
        optional = self.source / 'client/leaf.ext'; optional.parent.mkdir(); optional.write_text('synthetic-ext')
        manifest = self.source_manifest()
        restored = self.root / 'restored'; shutil.copytree(self.source, restored)
        (restored / 'client/leaf.ext').unlink()
        output = self.root / 'missing-optional.json'
        self.assertEqual(self.invoke(restored, output, True, manifest)[0], 1)
        self.assertEqual(json.loads(output.read_bytes())['comparison']['missing'], ['client/leaf.ext'])
        (restored / 'secrets/database_url').unlink()
        output = self.root / 'missing-required.json'
        self.assertEqual(self.invoke(restored, output, True, manifest)[0], 1)
        self.assertEqual(json.loads(output.read_bytes())['error_code'], 'REQUIRED_CONFIGURATION_FILE_MISSING')

    def test_restored_same_resolved_source_directory_is_rejected(self):
        manifest = self.source_manifest()
        output = self.root / 'same-source.json'
        code, _ = self.invoke(self.source / '.', output, True, manifest)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.read_bytes())['error_code'], 'RESTORED_COPY_MUST_BE_SEPARATE_FROM_SOURCE')

    def test_untrusted_or_modified_reference_digest_is_rejected(self):
        manifest = self.source_manifest()
        restored = self.root / 'restored'; shutil.copytree(self.source, restored)
        output = self.root / 'wrong-reference.json'
        code, _ = self.invoke(restored, output, True, manifest,
                             extra=['--reference-manifest-sha256', '0' * 64])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.read_bytes())['error_code'], 'TRUSTED_REFERENCE_MANIFEST_DIGEST_MISMATCH')

    def test_safe_names_reject_absolute_windows_and_traversal_names(self):
        for name in ('../.env', '/.env', 'C:/secret', 'secrets\\database_url', '.env\x00',
                     'secrets/../database_url', './.env', 'secrets//database_url', 'unknown.key'):
            with self.subTest(name=name), self.assertRaises(RecoveryConfigError):
                safe_name(name)
        for name in ALLOWED_FILES:
            self.assertEqual(safe_name(name), name)

    def test_duplicate_env_json_and_manifest_entries_fail_closed(self):
        with self.assertRaisesRegex(RecoveryConfigError, 'DUPLICATE_ENV_KEY'):
            parse_env(b'A=1\nA=2\n')
        with self.assertRaisesRegex(RecoveryConfigError, 'DUPLICATE_JSON_PROPERTY'):
            account_roles(b'{"version":1,"version":1,"users":[]}')
        manifest = json.loads(self.source_manifest().read_bytes())
        manifest['files'].append(manifest['files'][0])
        with self.assertRaisesRegex(RecoveryConfigError, 'DUPLICATE_MANIFEST_FILE'):
            validate_reference(json.dumps(manifest).encode())

    def test_manifest_bad_shapes_names_and_sizes_are_rejected(self):
        baseline = json.loads(self.source_manifest().read_bytes())
        for mutation in (lambda doc: doc.update(status='FAIL'),
                         lambda doc: doc.update(format_version=True),
                         lambda doc: doc.update(files=[]),
                         lambda doc: doc['files'][0].update(name='../secret'),
                         lambda doc: doc['files'][0].update(bytes=True),
                         lambda doc: doc['files'][0].update(bytes=MAX_FILE_BYTES + 1),
                         lambda doc: doc['files'][0].update(sha256='not-a-hash')):
            row = json.loads(json.dumps(baseline)); mutation(row)
            with self.assertRaises(RecoveryConfigError):
                validate_reference(json.dumps(row).encode())
        for content in (b'[]', b'null', b'42', b'{', b'\xff'):
            with self.assertRaises(RecoveryConfigError):
                validate_reference(content)

    def test_symlink_file_and_symlink_ancestor_are_rejected(self):
        external = self.root / 'outside'; external.mkdir()
        (external / 'target').write_text(SENTINEL)
        link = self.root / 'link'
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('OS does not grant symlink creation')
        with self.assertRaisesRegex(RecoveryConfigError, 'SYMLINK_OR_REPARSE_POINT'):
            regular_bytes(link / 'target')
        key = self.source / 'secrets/ssh_private_key'; key.unlink(); key.symlink_to(external / 'target')
        with self.assertRaisesRegex(RecoveryConfigError, 'SYMLINK_OR_REPARSE_POINT'):
            collect(self.source, PROJECT, PROJECT, IMAGE)

    def test_windows_reparse_attribute_is_rejected_without_following_target(self):
        original = Path.lstat
        def reparse(path):
            info = original(path)
            if path == self.source:
                class Reparse:
                    st_mode = info.st_mode
                    st_file_attributes = 0x400
                return Reparse()
            return info
        with patch.object(Path, 'lstat', reparse), self.assertRaisesRegex(RecoveryConfigError, 'REPARSE_POINT'):
            no_link_path(self.source)

    def test_hard_link_secret_is_rejected(self):
        path = self.source / 'secrets/ssh_private_key'
        try:
            os.link(path, self.root / 'alias-private-key')
        except OSError:
            self.skipTest('OS does not support hardlinks')
        with self.assertRaisesRegex(RecoveryConfigError, 'SINGLE_LINK'):
            regular_bytes(path)

    def test_bounded_read_rejects_oversized_and_non_regular_files(self):
        path = self.root / 'large'
        path.write_bytes(b'x' * (MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(RecoveryConfigError, 'BOUNDED_FILE'):
            regular_bytes(path)
        with self.assertRaises(RecoveryConfigError):
            regular_bytes(self.source)

    def test_report_cannot_overwrite_reference_existing_file_or_private_copy(self):
        manifest = self.source_manifest(); before = manifest.read_bytes()
        self.assertEqual(self.invoke(report=manifest)[0], 1)
        self.assertEqual(manifest.read_bytes(), before)
        code, stdout = self.invoke(report=self.source / 'new-report.json')
        self.assertEqual(code, 1)
        self.assertEqual(stdout['error_code'], 'REPORT_MUST_BE_OUTSIDE_PRIVATE_COPY')
        self.assertFalse((self.source / 'new-report.json').exists())

    def test_unknown_private_file_and_compose_overlay_are_not_silently_omitted(self):
        unknown = self.source / 'secrets/unknown_private_secret'; unknown.write_text(SENTINEL)
        with self.assertRaisesRegex(RecoveryConfigError, 'UNSUPPORTED_CONFIGURATION_FILE'):
            collect(self.source, PROJECT, PROJECT, IMAGE)
        unknown.unlink()
        (self.source / 'compose.extra.yml').write_text('services: {}')
        with self.assertRaisesRegex(RecoveryConfigError, 'UNREVIEWED_COMPOSE_OVERLAY'):
            collect(self.source, PROJECT, PROJECT, IMAGE)

    def test_identity_and_floating_dependency_are_rejected(self):
        env = self.source / '.env'; original = env.read_text()
        for changed in (original.replace(PROJECT, 'other-project'),
                        original.replace('APP_DEPLOYMENT_SCOPE=staging', 'APP_DEPLOYMENT_SCOPE=production'),
                        original.replace(IMAGE, 'dang7904/storage-lab-console:latest'),
                        original.replace('postgres:16-alpine@sha256:' + 'b' * 64, 'postgres:latest')):
            env.write_text(changed)
            with self.assertRaises(RecoveryConfigError):
                collect(self.source, PROJECT, PROJECT, IMAGE)
        env.write_text(original)
        with self.assertRaises(RecoveryConfigError):
            collect(self.source, PROJECT, 'other-instance', IMAGE)

    def test_inline_credentials_interpolation_and_writable_flags_are_rejected(self):
        for content in (b'EXECUTOR_TOKEN=inline-secret\n', b'DATABASE_URL=postgres://secret\n',
                        b'PERFORMANCE_PROMETHEUS_URL=http://user:secret@host/metrics\n',
                        b'A=${SECRET}\n', b'A=$(command)\n', b'A=`command`\n', b'not an env line'):
            with self.assertRaises(RecoveryConfigError):
                parse_env(content)
        env = self.source / '.env'
        env.write_text(env.read_text() + 'UPGRADE_MUTATIONS_ENABLED=true\n')
        with self.assertRaisesRegex(RecoveryConfigError, 'READ_ONLY_CONFIGURATION'):
            collect(self.source, PROJECT, PROJECT, IMAGE)

    def test_altered_compose_or_unsafe_staging_override_is_rejected(self):
        compose = self.source / 'compose.production.yml'
        original = compose.read_bytes(); compose.write_bytes(original + b'\nservices: {}\n')
        with self.assertRaisesRegex(RecoveryConfigError, 'STATIC_TEMPLATE'):
            collect(self.source, PROJECT, PROJECT, IMAGE)
        compose.write_bytes(original)
        overlay = self.source / 'compose.staging.yml'
        overlay.write_text("services:\n  executor:\n    environment:\n      RBD_SSH_KNOWN_HOSTS_PATH: ''\n")
        self.assertEqual(collect(self.source, PROJECT, PROJECT, IMAGE)['status'], 'PASS')
        overlay.write_text('services:\n  executor:\n    privileged: true\n')
        with self.assertRaisesRegex(RecoveryConfigError, 'STAGING_OVERLAY'):
            collect(self.source, PROJECT, PROJECT, IMAGE)

    def test_database_role_and_password_separation_is_checked_without_secret_output(self):
        url = self.source / 'secrets/database_url'
        original = url.read_text()
        for value in (original.replace('storage_lab_runtime', 'storage_lab_console'),
                      original.replace('r' * 40, 'wrong-secret'),
                      original.replace('@postgres', '@other-db'),
                      original.strip() + '?options=-c%20role%3Dstorage_lab_console',
                      original.strip() + '?user=storage_lab_console',
                      original.strip() + '?sslmode=disable',
                      original.strip() + '?sslmode=verify-full&sslmode=verify-full'):
            url.write_text(value)
            with self.assertRaises(RecoveryConfigError):
                collect(self.source, PROJECT, PROJECT, IMAGE)

    def test_database_tls_query_allows_verify_full_but_does_not_claim_ca_validation(self):
        for name in ('secrets/database_url', 'secrets/migration_database_url'):
            file = self.source / name
            file.write_text(file.read_text().strip() + '?sslmode=verify-full&sslrootcert=/run/secrets/db_ca')
        report = collect(self.source, PROJECT, PROJECT, IMAGE)
        self.assertEqual(report['status'], 'PASS')
        self.assertTrue(report['facts']['database']['actual_database_privileges_not_checked'])
        self.assertNotIn('/run/secrets/db_ca', json.dumps(report))

    def test_private_copy_acknowledgement_and_reference_mode_are_required(self):
        stdout = io.StringIO()
        args = ['--deployment-directory', str(self.source), '--expected-project', PROJECT,
                '--expected-instance', PROJECT, '--expected-image', IMAGE,
                '--report', str(self.root / 'unacknowledged.json')]
        with redirect_stdout(stdout):
            self.assertEqual(main(args), 1)
        self.assertEqual(json.loads(stdout.getvalue())['error_code'], 'EXPLICIT_PRIVATE_COPY_CONFIRMATION_REQUIRED')
        self.assertFalse((self.root / 'unacknowledged.json').exists())
        report = self.root / 'missing-reference.json'
        self.assertEqual(self.invoke(report=report, restored=True)[0], 1)
        self.assertEqual(json.loads(report.read_bytes())['error_code'], 'RESTORE_REQUIRES_REFERENCE_SOURCE_MANIFEST')

    def test_reference_identity_mismatch_is_not_allowed_to_cross_deployments(self):
        source = collect(self.source, PROJECT, PROJECT, IMAGE)
        restored = json.loads(json.dumps(source))
        restored['source_directory_fingerprint'] = 'f' * 64
        restored['identity']['project'] = 'other-project'
        with self.assertRaisesRegex(RecoveryConfigError, 'REFERENCE_DEPLOYMENT_IDENTITY'):
            compare(source, restored)

    def test_failed_validation_receipt_has_stable_code_not_exception_details(self):
        output = self.root / 'failed.json'
        with patch('production_recovery_config.collect', side_effect=OSError(SENTINEL + str(self.source))):
            code, stdout = self.invoke(report=output)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.read_bytes())['error_code'], 'RECOVERY_CONFIGURATION_VALIDATION_FAILED')
        self.assertNotIn(SENTINEL, output.read_text() + json.dumps(stdout))
        self.assertNotIn(str(self.source), output.read_text() + json.dumps(stdout))


if __name__ == '__main__':
    unittest.main()
