"""Read-only configuration/secret recovery manifests for an explicit private copy.

This does not create a backup, encrypt secrets, contact Docker/Ceph, restore DB
roles, install certificates, or prove production acceptance. Reports contain
only allowlisted relative names, sizes, hashes and bounded non-secret facts.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import parse_qsl, unquote, urlsplit


FORMAT_VERSION = 1
KIND = 'CONSOLE_PRIVATE_CONFIGURATION_RECOVERY'
PROJECT = re.compile(r'^storage-lab-console-(?:production|staging)[a-z0-9_-]{0,64}$')
IMAGE = re.compile(r'^[a-z0-9][a-z0-9._:/-]{1,255}@sha256:[a-f0-9]{64}$')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
REQUIRED_FILES = (
    '.env', 'compose.production.yml', 'compose.access-control.yml',
    'config/profiles/production.yaml', 'nginx/production.conf',
    'secrets/console_users.json', 'secrets/console_password_hash',
    'secrets/database_url', 'secrets/migration_database_url',
    'secrets/database_runtime_password', 'secrets/postgres_password',
    'secrets/executor_token', 'secrets/tls_certificate.pem',
    'secrets/tls_private_key.pem', 'secrets/ssh_private_key',
    'secrets/ssh_known_hosts',
)
OPTIONAL_FILES = (
    'compose.staging.yml', 'client/accounts.json', 'client/viewer.password',
    'client/operator.password', 'client/admin.password', 'client/staging-ca.crt',
    'client/staging-ca.key', 'client/staging-ca.srl', 'client/localhost.csr',
    'client/leaf.ext',
)
ALLOWED_FILES = frozenset(REQUIRED_FILES + OPTIONAL_FILES)
PRIVATE_DIRECTORIES = ('config', 'secrets', 'nginx', 'client')
LIMITATIONS = [
    'PRIVATE_COPY_DECLARED_BY_OPERATOR_NOT_LIVE_DEPLOYMENT_INSPECTION',
    'PRIVATE_COPY_MUST_BE_QUIESCENT_NOT_UNTRUSTED_CONCURRENTLY_MUTABLE',
    'CONFIGURATION_AND_SECRET_FILE_CHECKSUMS_ONLY_NOT_A_BACKUP_OR_ENCRYPTION',
    'CERTIFICATE_CHAIN_KEY_MATCH_EXPIRY_AND_HOSTNAME_NOT_VERIFIED',
    'LINUX_UID_GID_WINDOWS_ACL_AND_CONTAINER_READABILITY_NOT_VERIFIED',
    'CLIENT_ACCOUNT_PASSWORD_PATH_REFERENCES_NOT_REWRITTEN_OR_VERIFIED',
    'NO_DATABASE_ROLE_RESTORE_NO_DOCKER_OR_NETWORK_OPERATIONS',
    'NO_OFFSITE_RECOVERY_OR_SITE_RPO_RTO_SIGNOFF',
    'REFERENCE_CHECKSUM_IS_NOT_A_DIGITAL_SIGNATURE',
]


class RecoveryConfigError(Exception):
    """Only stable, non-secret error codes may reach a receipt or stdout."""


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryConfigError('DUPLICATE_JSON_PROPERTY')
        result[key] = value
    return result


def safe_name(value: str) -> str:
    if (not isinstance(value, str) or value not in ALLOWED_FILES
            or '\\' in value or ':' in value or '\x00' in value
            or PurePosixPath(value).is_absolute()
            or any(part in {'', '.', '..'} for part in value.split('/'))):
        raise RecoveryConfigError('UNSAFE_OR_UNSUPPORTED_RELATIVE_NAME')
    return value


def no_link_path(path: Path, *, require_exists: bool = True) -> Path:
    """Reject symlinks and Windows junction/reparse points in every ancestor."""
    absolute = Path(os.path.abspath(path))
    for component in reversed((absolute, *absolute.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if component == absolute and not require_exists:
                continue
            raise RecoveryConfigError('PATH_UNAVAILABLE') from None
        except OSError:
            raise RecoveryConfigError('PATH_UNAVAILABLE') from None
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise RecoveryConfigError('SYMLINK_OR_REPARSE_POINT_FORBIDDEN')
    return absolute


def regular_bytes(path: Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    path = no_link_path(path)
    try:
        before = path.stat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size > maximum):
            raise RecoveryConfigError('REGULAR_SINGLE_LINK_BOUNDED_FILE_REQUIRED')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(path, flags), 'rb') as source:
            opened = os.fstat(source.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink) != (
                    before.st_dev, before.st_ino, before.st_size, before.st_nlink):
                raise RecoveryConfigError('FILE_CHANGED_DURING_VALIDATION')
            content = source.read(maximum + 1)
            after = os.fstat(source.fileno())
        current = path.stat()
        no_link_path(path)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if (len(content) > maximum or len(content) != before.st_size
                or identity(before) != identity(after)
                or identity(before) != identity(current)):
            raise RecoveryConfigError('FILE_CHANGED_DURING_VALIDATION')
        return content
    except OSError:
        raise RecoveryConfigError('FILE_UNAVAILABLE') from None


def decode(content: bytes) -> str:
    try:
        return content.decode('utf-8-sig')
    except UnicodeError:
        raise RecoveryConfigError('UTF8_CONFIGURATION_REQUIRED') from None


def parse_env(content: bytes) -> dict[str, str]:
    values = {}
    for line in decode(content).splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]{0,127})=([^\r\n\x00]*)', line)
        if not match or len(match[2]) > 4096:
            raise RecoveryConfigError('BOUNDED_LITERAL_ENV_REQUIRED')
        if match[1] in values:
            raise RecoveryConfigError('DUPLICATE_ENV_KEY')
        if any(part in match[2] for part in ('${', '$(', '`')):
            raise RecoveryConfigError('ENV_INTERPOLATION_FORBIDDEN')
        values[match[1]] = match[2]
    if len(values) > 256:
        raise RecoveryConfigError('TOO_MANY_ENV_KEYS')
    # Settings not used by the reviewed file-secret overlay must not become a
    # hidden, inline credential fallback through env_file or Compose overrides.
    for key, value in values.items():
        if value and (re.search(r'(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY)', key)
                      and not key.endswith(('_FILE', '_PATH'))):
            raise RecoveryConfigError('INLINE_SECRET_ENV_FORBIDDEN')
        if value and key in {'DATABASE_URL', 'MIGRATION_DATABASE_URL', 'CONSOLE_AUTH_USERS'}:
            raise RecoveryConfigError('INLINE_SECRET_ENV_FORBIDDEN')
        if value and key.endswith('URL'):
            try:
                uri = urlsplit(value)
                if uri.username is not None or uri.password is not None:
                    raise RecoveryConfigError('INLINE_SECRET_ENV_FORBIDDEN')
            except ValueError:
                raise RecoveryConfigError('INVALID_ENV_URL') from None
    return values


def validate_hash(value: str) -> None:
    try:
        if not isinstance(value, str) or len(value) > 256:
            raise ValueError
        algorithm, count, salt_text, result_text = value.split('$')
        salt = base64.b64decode(salt_text, validate=True)
        result = base64.b64decode(result_text, validate=True)
        if (algorithm != 'pbkdf2_sha256' or not 600000 <= int(count) <= 2000000
                or not 16 <= len(salt) <= 64 or len(result) != 32):
            raise ValueError
    except (ValueError, TypeError, binascii.Error):
        raise RecoveryConfigError('ACCOUNT_PASSWORD_HASH_INVALID') from None


def account_roles(content: bytes) -> dict:
    try:
        if len(content) > 65536:
            raise ValueError
        document = json.loads(decode(content), object_pairs_hook=unique_object)
        if (not isinstance(document, dict) or set(document) != {'version', 'users'}
                or type(document['version']) is not int or document['version'] != 1
                or not isinstance(document['users'], list)
                or not 3 <= len(document['users']) <= 128):
            raise ValueError
        users = set(); roles = {'viewer': 0, 'operator': 0, 'admin': 0}
        for user in document['users']:
            if (not isinstance(user, dict) or set(user) != {'username', 'role', 'password_hash'}
                    or not isinstance(user['username'], str)
                    or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}', user['username'])
                    or user['username'] in users or user['role'] not in roles):
                raise ValueError
            users.add(user['username']); roles[user['role']] += 1
            validate_hash(user['password_hash'])
        if not all(roles.values()):
            raise ValueError
        return roles
    except (ValueError, TypeError, KeyError, RecursionError):
        raise RecoveryConfigError('THREE_UNIQUE_ACCOUNT_ROLES_REQUIRED') from None


def database_facts(files: dict[str, bytes]) -> dict:
    urls = []; passwords = []
    for file_name, role, password_file in (
            ('secrets/database_url', 'storage_lab_runtime', 'secrets/database_runtime_password'),
            ('secrets/migration_database_url', 'storage_lab_console', 'secrets/postgres_password')):
        try:
            value = decode(files[file_name]).strip()
            url = urlsplit(value)
            password = decode(files[password_file]).strip()
            query = parse_qsl(url.query, strict_parsing=True) if url.query else []
            if (url.scheme not in {'postgres', 'postgresql'} or not url.hostname
                    or url.username != role or url.port != 5432
                    or url.path != '/storage_lab_console' or url.fragment
                    or not url.password or len(password) < 32
                    or any(key not in {'sslmode', 'sslrootcert', 'sslcert', 'sslkey'}
                           for key, _ in query)
                    or len({key for key, _ in query}) != len(query)
                    or any(not value or '\x00' in value for _, value in query)
                    or any(key == 'sslmode' and value != 'verify-full' for key, value in query)
                    or not hmac.compare_digest(unquote(url.password).encode('utf-8'), password.encode('utf-8'))):
                raise ValueError
            urls.append(url); passwords.append(password)
        except (ValueError, KeyError):
            raise RecoveryConfigError('DATABASE_SECRET_ROLE_OR_PASSWORD_MISMATCH') from None
    if (urls[0].hostname != urls[1].hostname or urls[0].path != urls[1].path
            or hmac.compare_digest(passwords[0].encode('utf-8'), passwords[1].encode('utf-8'))):
        raise RecoveryConfigError('SEPARATE_DATABASE_ROLE_SECRETS_REQUIRED')
    return {'runtime_role': 'storage_lab_runtime', 'migration_role': 'storage_lab_console',
            'separate_passwords': True, 'password_files_match_urls': True,
            'actual_database_privileges_not_checked': True}


def same_template(content: bytes, name: str) -> None:
    trusted = Path(__file__).resolve().parents[1] / 'deploy' / name
    if decode(content).replace('\r\n', '\n') != decode(regular_bytes(trusted)).replace('\r\n', '\n'):
        raise RecoveryConfigError('REVIEWED_STATIC_TEMPLATE_REQUIRED')


def collect(directory: Path, expected_project: str, expected_instance: str,
            expected_image: str) -> dict:
    if (not PROJECT.fullmatch(expected_project) or expected_instance != expected_project
            or not IMAGE.fullmatch(expected_image)):
        raise RecoveryConfigError('EXPLICIT_PROJECT_INSTANCE_AND_DIGEST_REQUIRED')
    root = no_link_path(directory)
    if not root.is_dir() or root == Path(root.anchor):
        raise RecoveryConfigError('SEPARATE_PRIVATE_DEPLOYMENT_DIRECTORY_REQUIRED')
    files = {}; total = 0
    for name in sorted(ALLOWED_FILES):
        path = root / safe_name(name)
        if not path.exists() and not path.is_symlink():
            if name in REQUIRED_FILES:
                raise RecoveryConfigError('REQUIRED_CONFIGURATION_FILE_MISSING')
            continue
        content = regular_bytes(path)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise RecoveryConfigError('PRIVATE_COPY_TOO_LARGE')
        files[name] = content
    # Unknown private/configuration files must not be silently omitted from a
    # purported complete recovery receipt. Never recurse into backup/DB data.
    for name in PRIVATE_DIRECTORIES:
        directory_path = root / name
        if not directory_path.exists():
            continue
        no_link_path(directory_path)
        pending = [directory_path]; visited = 0
        while pending:
            current = pending.pop()
            for child in current.iterdir():
                no_link_path(child); visited += 1
                if visited > 64:
                    raise RecoveryConfigError('PRIVATE_COPY_TOO_MANY_ENTRIES')
                if child.is_dir():
                    pending.append(child)
                elif child.relative_to(root).as_posix() not in files:
                    raise RecoveryConfigError('UNSUPPORTED_CONFIGURATION_FILE')
    unexpected_compose = [item for item in root.iterdir()
                          if item.name.startswith('compose.') and item.name.endswith(('.yml', '.yaml'))
                          and item.name not in files]
    if unexpected_compose:
        raise RecoveryConfigError('UNREVIEWED_COMPOSE_OVERLAY_FORBIDDEN')
    values = parse_env(files['.env'])
    scope = values.get('APP_DEPLOYMENT_SCOPE')
    if (values.get('COMPOSE_PROJECT_NAME') != expected_project
            or values.get('APP_INSTANCE_ID') != expected_instance
            or scope not in {'production', 'staging'}
            or not expected_project.startswith('storage-lab-console-' + scope)
            or values.get('STORAGE_LAB_CONSOLE_IMAGE') != expected_image):
        raise RecoveryConfigError('EXPECTED_DEPLOYMENT_IDENTITY_MISMATCH')
    if any(not IMAGE.fullmatch(values.get(name, '')) for name in (
            'STORAGE_LAB_CONSOLE_IMAGE', 'POSTGRES_IMAGE', 'INGRESS_IMAGE')):
        raise RecoveryConfigError('ALL_IMAGES_MUST_BE_PINNED_BY_DIGEST')
    if values.get('RUNTIME_ENV_FILE', '.env') != '.env':
        raise RecoveryConfigError('ALTERNATE_RUNTIME_ENV_FORBIDDEN')
    if values.get('CONSOLE_AUTH_USERNAME', '') or values.get('CONSOLE_AUTH_PASSWORD_HASH_FILE', ''):
        raise RecoveryConfigError('MULTI_ACCOUNT_FILE_AUTH_REQUIRED')
    forbidden = {'CONSOLE_READ_ONLY': 'true', 'UPGRADE_MUTATIONS_ENABLED': 'false',
                 'LAB_ALLOW_WRITE': 'false', 'RBD_TERMINAL_ENABLED': 'false',
                 'FEATURE_LEGACY_RGW': 'false', 'FEATURE_LEGACY_RBD': 'false',
                 'FEATURE_LAB': 'false'}
    if any(key in values and values[key] != expected for key, expected in forbidden.items()):
        raise RecoveryConfigError('READ_ONLY_CONFIGURATION_REQUIRED')
    if (values.get('RBD_SSH_HOST_KEY_REQUIRED') != 'true'
            or not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}=?', values.get('RBD_SSH_HOST_KEY_SHA256', ''))):
        raise RecoveryConfigError('PINNED_SSH_HOST_IDENTITY_REQUIRED')
    for name in ('compose.production.yml', 'compose.access-control.yml', 'nginx/production.conf'):
        same_template(files[name], name)
    if 'compose.staging.yml' in files:
        if scope != 'staging' or not re.fullmatch(
                r"services:\s*\n  executor:\s*\n    environment:\s*\n      RBD_SSH_KNOWN_HOSTS_PATH: '(?:/run/secrets/ssh_known_hosts)?'\s*\n?",
                decode(files['compose.staging.yml']).replace('\r\n', '\n')):
            raise RecoveryConfigError('REVIEWED_STAGING_OVERLAY_REQUIRED')
    roles = account_roles(files['secrets/console_users.json'])
    validate_hash(decode(files['secrets/console_password_hash']).strip())
    if len(decode(files['secrets/executor_token']).strip()) < 32:
        raise RecoveryConfigError('BOUNDED_EXECUTOR_TOKEN_REQUIRED')
    for name in ('secrets/tls_certificate.pem', 'secrets/tls_private_key.pem', 'secrets/ssh_private_key'):
        if not files[name].strip():
            raise RecoveryConfigError('NONEMPTY_PRIVATE_KEY_OR_CERTIFICATE_REQUIRED')
    return {
        'format_version': FORMAT_VERSION, 'kind': KIND, 'status': 'PASS',
        'collected_at': datetime.now(timezone.utc).isoformat(),
        'source_directory_fingerprint': digest(os.path.normcase(str(root)).encode('utf-8')),
        'identity': {'project': expected_project, 'instance': expected_instance,
                     'application_image': expected_image, 'scope': scope},
        'files': [{'name': name, 'bytes': len(content), 'sha256': digest(content)}
                  for name, content in sorted(files.items())],
        'facts': {'reviewed_static_compose_and_ingress': True,
                  'secret_mount_roles_verified_statically_not_at_runtime': True,
                  'console_role_counts': roles, 'database': database_facts(files),
                  'all_images_digest_pinned': True, 'ssh_host_fingerprint_present': True},
        'limitations': list(LIMITATIONS), 'not_production_signoff': True,
    }


def validate_reference(content: bytes) -> dict:
    try:
        manifest = json.loads(decode(content), object_pairs_hook=unique_object)
        if (not isinstance(manifest, dict) or type(manifest.get('format_version')) is not int
                or manifest.get('format_version') != FORMAT_VERSION
                or manifest.get('kind') != KIND or manifest.get('status') != 'PASS'
                or manifest.get('mode') != 'SOURCE_MANIFEST'
                or not SHA256.fullmatch(manifest.get('source_directory_fingerprint', ''))
                or not isinstance(manifest.get('identity'), dict)
                or set(manifest['identity']) != {'project', 'instance', 'application_image', 'scope'}
                or not isinstance(manifest.get('files'), list)
                or not len(REQUIRED_FILES) <= len(manifest['files']) <= len(ALLOWED_FILES)):
            raise RecoveryConfigError('REFERENCE_MANIFEST_INVALID')
        names = set()
        for item in manifest['files']:
            if (not isinstance(item, dict) or set(item) != {'name', 'bytes', 'sha256'}
                    or type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_FILE_BYTES
                    or not isinstance(item['sha256'], str) or not SHA256.fullmatch(item['sha256'])):
                raise RecoveryConfigError('REFERENCE_MANIFEST_INVALID')
            name = safe_name(item['name'])
            if name in names:
                raise RecoveryConfigError('DUPLICATE_MANIFEST_FILE')
            names.add(name)
        if not set(REQUIRED_FILES) <= names or sum(item['bytes'] for item in manifest['files']) > MAX_TOTAL_BYTES:
            raise RecoveryConfigError('REFERENCE_MANIFEST_INVALID')
        return manifest
    except (ValueError, TypeError, KeyError, RecursionError):
        raise RecoveryConfigError('REFERENCE_MANIFEST_INVALID') from None


def compare(reference: dict, restored: dict) -> dict:
    if reference['source_directory_fingerprint'] == restored['source_directory_fingerprint']:
        raise RecoveryConfigError('RESTORED_COPY_MUST_BE_SEPARATE_FROM_SOURCE')
    if reference['identity'] != restored['identity']:
        raise RecoveryConfigError('REFERENCE_DEPLOYMENT_IDENTITY_MISMATCH')
    source = {item['name']: item for item in reference['files']}
    target = {item['name']: item for item in restored['files']}
    result = {'missing': sorted(source.keys() - target.keys()),
              'unexpected': sorted(target.keys() - source.keys()),
              'changed': sorted(name for name in source.keys() & target.keys()
                                if source[name] != target[name])}
    result['matched'] = not any(result.values())
    return result


def report_path_check(path: Path, directories: list[Path], reference: Path | None) -> Path:
    report = no_link_path(path, require_exists=False)
    if report.exists():
        raise RecoveryConfigError('REFUSING_TO_OVERWRITE_RECOVERY_REPORT')
    if any(report == directory or directory in report.parents for directory in directories):
        raise RecoveryConfigError('REPORT_MUST_BE_OUTSIDE_PRIVATE_COPY')
    if reference is not None and report == reference:
        raise RecoveryConfigError('REPORT_MUST_NOT_REPLACE_REFERENCE_MANIFEST')
    return report


def write_report(path: Path, report: dict) -> None:
    content = (json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8')
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(path, flags, 0o600), 'wb') as target:
            target.write(content)
    except FileExistsError:
        raise RecoveryConfigError('REFUSING_TO_OVERWRITE_RECOVERY_REPORT') from None
    except OSError:
        raise RecoveryConfigError('RECOVERY_REPORT_UNAVAILABLE') from None


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    mode = command.add_mutually_exclusive_group(required=True)
    mode.add_argument('--deployment-directory', type=Path, help='Explicit PRIVATE SOURCE COPY, never a live deployment')
    mode.add_argument('--restored-directory', type=Path, help='Separate PRIVATE RESTORED COPY to validate')
    command.add_argument('--confirm-private-copy', action='store_true', help='Attest the selected directory is a private copy')
    command.add_argument('--expected-project', required=True)
    command.add_argument('--expected-instance', required=True)
    command.add_argument('--expected-image', required=True, help='Application reference pinned by sha256 digest')
    command.add_argument('--reference-manifest', type=Path)
    command.add_argument('--reference-manifest-sha256', help='Expected reference digest from a trusted independent record')
    command.add_argument('--report', type=Path, required=True, help='New private output file OUTSIDE selected copies; parent must exist')
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    report = {'format_version': FORMAT_VERSION, 'kind': KIND, 'status': 'FAIL',
              'not_production_signoff': True, 'limitations': list(LIMITATIONS)}
    output = None
    try:
        if not args.confirm_private_copy:
            raise RecoveryConfigError('EXPLICIT_PRIVATE_COPY_CONFIRMATION_REQUIRED')
        directory = no_link_path(args.deployment_directory or args.restored_directory)
        reference_path = no_link_path(args.reference_manifest) if args.reference_manifest else None
        output = report_path_check(args.report, [directory], reference_path)
        if bool(args.restored_directory) != bool(reference_path):
            raise RecoveryConfigError('RESTORE_REQUIRES_REFERENCE_SOURCE_MANIFEST')
        if args.deployment_directory and args.reference_manifest_sha256:
            raise RecoveryConfigError('SOURCE_MODE_CANNOT_ACCEPT_REFERENCE_DIGEST')
        reference = None
        if reference_path:
            if directory in reference_path.parents:
                raise RecoveryConfigError('REFERENCE_MANIFEST_MUST_BE_OUTSIDE_RESTORED_COPY')
            content = regular_bytes(reference_path, MAX_MANIFEST_BYTES)
            if (not args.reference_manifest_sha256
                    or not SHA256.fullmatch(args.reference_manifest_sha256)
                    or not hmac.compare_digest(digest(content), args.reference_manifest_sha256)):
                raise RecoveryConfigError('TRUSTED_REFERENCE_MANIFEST_DIGEST_MISMATCH')
            reference = validate_reference(content)
            if reference['source_directory_fingerprint'] == digest(os.path.normcase(str(directory)).encode('utf-8')):
                raise RecoveryConfigError('RESTORED_COPY_MUST_BE_SEPARATE_FROM_SOURCE')
        report = collect(directory, args.expected_project, args.expected_instance, args.expected_image)
        report['mode'] = 'SOURCE_MANIFEST' if reference is None else 'RESTORED_COPY_VERIFICATION'
        if reference is not None:
            report['reference_manifest_sha256'] = args.reference_manifest_sha256
            report['comparison'] = compare(reference, report)
            if not report['comparison']['matched']:
                report['status'] = 'FAIL'
                report['error_code'] = 'RESTORED_CONFIGURATION_FILE_SET_OR_CONTENT_MISMATCH'
    except RecoveryConfigError as exc:
        report.update(status='FAIL', error_code=str(exc))
    except Exception:
        report.update(status='FAIL', error_code='RECOVERY_CONFIGURATION_VALIDATION_FAILED')
    if output is None:
        print(json.dumps({'status': 'FAIL', 'error_code': report['error_code']}))
        return 1
    try:
        write_report(output, report)
    except RecoveryConfigError as exc:
        print(json.dumps({'status': 'FAIL', 'error_code': str(exc)}))
        return 1
    print(json.dumps({'status': report['status'], 'error_code': report.get('error_code'),
                      'receipt_sha256': digest(regular_bytes(output, MAX_MANIFEST_BYTES))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
