"""Read-only production target readiness: explicit domain, verified CA and viewer."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import ssl
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from production_acceptance import AcceptanceError, utc_now
from production_target import approved_api_base, runtime_values

_spec = importlib.util.spec_from_file_location('console_staging_ready_client', Path(__file__).with_name('check-staging-ready.py'))
client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(client)


def validate_production_runtime(payload: dict, project: str, version: str) -> None:
    if (payload.get('environment') != 'production' or payload.get('deployment_scope') != 'production'
            or payload.get('deployment_id') != project or payload.get('console_role') != 'viewer'
            or payload.get('application_version') != version or payload.get('console_read_only') is not True
            or payload.get('ceph_mutations_enabled') is not False):
        raise client.ReadyCheckError('PRODUCTION_IDENTITY_OR_READONLY_MISMATCH')
    features = payload.get('features')
    if (not isinstance(features, dict) or features.get('upgrade') is not True
            or any(features.get(key) is not False for key in ('lab', 'legacy_rgw', 'legacy_rbd'))):
        raise client.ReadyCheckError('PRODUCTION_FEATURE_SCOPE_MISMATCH')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-directory', required=True, type=Path)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--ca-file', required=True, type=Path)
    parser.add_argument('--auth-user-file', required=True, type=Path)
    parser.add_argument('--expected-version', default='5.2.0-rc.1')
    parser.add_argument('--expected-schema', type=int, default=21)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    result = {'kind': 'PRODUCTION_TARGET_READINESS', 'status': 'FAIL', 'checked_at': utc_now(),
              'not_a_production_signoff': True, 'certificate_revocation_policy_not_validated': True,
              'dedicated_ssh_authority_and_image_signature_not_checked': True}
    output = None
    try:
        output = client.reserve_report(args.report)
        if not (args.deployment_directory / 'compose.production.yml').is_file():
            raise AcceptanceError('PRODUCTION_COMPOSE_REQUIRED')
        values = runtime_values(args.deployment_directory)
        project = values.get('COMPOSE_PROJECT_NAME', '')
        if (not re.fullmatch(r'storage-lab-console-production[a-z0-9_-]{0,64}', project)
                or values.get('APP_INSTANCE_ID') != project or values.get('APP_DEPLOYMENT_SCOPE') != 'production'):
            raise AcceptanceError('EXPLICIT_PRODUCTION_DEPLOYMENT_REQUIRED')
        if not 1 <= args.expected_schema <= 9999 or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', args.expected_version):
            raise AcceptanceError('EXPECTED_RELEASE_INVALID')
        base = approved_api_base(args.deployment_directory, args.base_url, 8443)
        authorization = client.viewer_authorization(args.auth_user_file)
        context = ssl.create_default_context(cafile=str(args.ca_file))
        opener = client.request.build_opener(client.request.ProxyHandler({}), client.request.HTTPSHandler(context=context), client.NoRedirect())
        validate_production_runtime(client.get_json(opener, base + '/api/runtime-config', authorization), project, args.expected_version)
        client.validate_ready(client.get_json(opener, base + '/api/ready', authorization), args.expected_schema)
        result.update(status='PASS', deployment_id=project, version=args.expected_version,
                      schema=args.expected_schema, tls_ca_and_hostname_verified=True,
                      origin_bound_to_deployment=True, viewer_authenticated=True)
    except client.ReadyCheckError as exc:
        result.update(error_code=str(exc), http_status=exc.http_status)
    except AcceptanceError as exc:
        result.update(error_code=str(exc))
    except (OSError, ValueError, TypeError, KeyError):
        result.update(error_code='PRODUCTION_CHECK_CONFIGURATION_INVALID')
    client.finish_report(output, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
