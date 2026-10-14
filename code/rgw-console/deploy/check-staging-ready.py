"""Strict-CA, read-only localhost staging smoke check (Python standard library)."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from http.client import HTTPException
import json
from pathlib import Path
import re
import ssl
from urllib import error, request


class ReadyCheckError(Exception):
    def __init__(self, code: str, http_status: int | None = None):
        super().__init__(code)
        self.http_status = http_status


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def limited_text(path: Path, maximum: int) -> str:
    if path.stat().st_size > maximum:
        raise ReadyCheckError('CONFIGURATION_FILE_TOO_LARGE')
    return path.read_text(encoding='utf-8')


def staging_identity(directory: Path) -> tuple[str, int]:
    if not (directory / 'compose.production.yml').is_file():
        raise ReadyCheckError('STAGING_COMPOSE_REQUIRED')
    values = {}
    for line in limited_text(directory / '.env', 65536).splitlines():
        match = re.fullmatch(r'([A-Z0-9_]+)=([^\r\n]*)', line)
        if match:
            if match[1] in values:
                raise ReadyCheckError('DUPLICATE_RUNTIME_KEY')
            values[match[1]] = match[2]
    project = values.get('COMPOSE_PROJECT_NAME', '')
    if (not re.fullmatch(r'storage-lab-console-staging[a-z0-9_-]{0,64}', project)
            or values.get('APP_INSTANCE_ID') != project or values.get('APP_DEPLOYMENT_SCOPE') != 'staging'):
        raise ReadyCheckError('EXPLICIT_STAGING_ID_REQUIRED')
    port = int(values.get('CONSOLE_HTTPS_PORT', '8446'))
    if not 1024 <= port <= 65535:
        raise ReadyCheckError('INVALID_HTTPS_PORT')
    return project, port


def viewer_authorization(path: Path) -> str:
    payload = json.loads(limited_text(path, 65536))
    if not isinstance(payload, dict) or not isinstance(payload.get('accounts'), list):
        raise ReadyCheckError('CLIENT_ACCOUNTS_INVALID')
    accounts = payload['accounts']
    if len(accounts) > 32 or any(not isinstance(row, dict) for row in accounts):
        raise ReadyCheckError('CLIENT_ACCOUNTS_INVALID')
    viewers = [row for row in accounts if row.get('role') == 'viewer']
    if len(viewers) != 1:
        raise ReadyCheckError('EXACTLY_ONE_VIEWER_REQUIRED')
    viewer = viewers[0]
    username = viewer.get('username', '')
    secret_path = viewer.get('password_file')
    if (not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,128}', username)
            or not isinstance(secret_path, str) or not Path(secret_path).is_absolute()):
        raise ReadyCheckError('VIEWER_CREDENTIAL_REFERENCE_INVALID')
    password = limited_text(Path(secret_path), 4096).rstrip('\r\n')
    if not 32 <= len(password) <= 1024 or '\n' in password or '\r' in password:
        raise ReadyCheckError('VIEWER_PASSWORD_FILE_INVALID')
    return 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode('ascii')


def get_json(opener, url: str, authorization: str) -> dict:
    observed_status = None
    try:
        call = request.Request(url, headers={'Authorization': authorization, 'Accept': 'application/json'})
        with opener.open(call, timeout=10) as response:
            observed_status = response.status
            if response.status != 200:
                raise ReadyCheckError('HTTP_NOT_OK', response.status)
            if response.headers.get_content_type() != 'application/json':
                raise ReadyCheckError('NON_JSON_RESPONSE', response.status)
            body = response.read(65537)
            if len(body) > 65536:
                raise ReadyCheckError('RESPONSE_TOO_LARGE', response.status)
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ReadyCheckError('RESPONSE_SHAPE_INVALID', response.status)
            return result
    except error.HTTPError as exc:
        # No response body, credentials, URL or exception text in diagnostics.
        raise ReadyCheckError('HTTP_NOT_OK', exc.code) from None
    except HTTPException:
        raise ReadyCheckError('HTTP_PROTOCOL_INVALID', observed_status) from None
    except (error.URLError, ssl.SSLError, TimeoutError, OSError):
        raise ReadyCheckError('TLS_OR_CONNECTION_FAILED') from None
    except (ValueError, UnicodeError):
        raise ReadyCheckError('RESPONSE_JSON_INVALID', observed_status) from None


def validate_runtime(runtime: dict, project: str, version: str) -> None:
    if (runtime.get('environment') != 'production' or runtime.get('deployment_scope') != 'staging'
            or runtime.get('deployment_id') != project or runtime.get('console_role') != 'viewer'
            or runtime.get('application_version') != version
            or runtime.get('console_read_only') is not True
            or runtime.get('ceph_mutations_enabled') is not False):
        raise ReadyCheckError('RUNTIME_IDENTITY_OR_READONLY_MISMATCH')


def validate_ready(ready: dict, schema: int) -> None:
    dependencies = ready.get('dependencies')
    if not isinstance(dependencies, dict) or not isinstance(dependencies.get('database'), dict):
        raise ReadyCheckError('READINESS_SHAPE_INVALID')
    if (ready.get('ready') is not True or ready.get('status') != 'ready'
            or ready.get('blocking_dependencies') != []
            or dependencies['database'].get('schema_version') != schema
            or dependencies['database'].get('status') != 'ready'):
        raise ReadyCheckError('DEPENDENCY_OR_SCHEMA_NOT_READY')
    for key in ('config', 'frontend', 'ceph_executor'):
        item = dependencies.get(key)
        if not isinstance(item, dict) or item.get('status') != 'ready' or item.get('required') is not True:
            raise ReadyCheckError('DEPENDENCY_OR_SCHEMA_NOT_READY')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-directory', required=True, type=Path)
    parser.add_argument('--ca-file', required=True, type=Path)
    parser.add_argument('--auth-user-file', required=True, type=Path)
    parser.add_argument('--expected-version', default='5.2.0-rc.1')
    parser.add_argument('--expected-schema', type=int, default=21)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    result = {'kind': 'STAGING_INSTALL_READINESS', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'status': 'FAIL', 'not_a_production_signoff': True,
              'certificate_revocation_policy_not_validated': True}
    try:
        if not 1 <= args.expected_schema <= 9999 or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', args.expected_version):
            raise ReadyCheckError('EXPECTED_RELEASE_INVALID')
        project, port = staging_identity(args.deployment_directory)
        authorization = viewer_authorization(args.auth_user_file)
        context = ssl.create_default_context(cafile=str(args.ca_file))
        # Explicit CA + normal hostname/certificate validation, no proxy or
        # redirects carrying credentials elsewhere. This staging smoke does
        # not implement an organization's certificate revocation policy.
        opener = request.build_opener(request.ProxyHandler({}), request.HTTPSHandler(context=context), NoRedirect())
        base = f'https://localhost:{port}'
        validate_runtime(get_json(opener, base + '/api/runtime-config', authorization), project, args.expected_version)
        validate_ready(get_json(opener, base + '/api/ready', authorization), args.expected_schema)
        result.update(status='PASS', deployment_id=project, version=args.expected_version,
                      schema=args.expected_schema, tls_ca_and_hostname_verified=True, viewer_authenticated=True)
    except ReadyCheckError as exc:
        result.update(error_code=str(exc), http_status=exc.http_status)
    except (OSError, ValueError, TypeError, KeyError):
        result.update(error_code='INSTALL_CHECK_CONFIGURATION_INVALID')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as output:
            json.dump(result, output, sort_keys=True)
            output.write('\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
