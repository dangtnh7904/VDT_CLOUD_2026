"""Explicit HTTPS target binding for read-only production operator clients."""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

from production_acceptance import AcceptanceError


def runtime_values(directory: Path) -> dict[str, str]:
    path = directory / '.env'
    if not path.is_file() or path.stat().st_size > 65536:
        raise AcceptanceError('BOUNDED_DEPLOYMENT_CONFIG_REQUIRED')
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([A-Z0-9_]+)=([^\r\n]*)', line)
        if match:
            if match[1] in values:
                raise AcceptanceError('DUPLICATE_RUNTIME_KEY')
            values[match[1]] = match[2]
    return values


def https_origin(value: str) -> str:
    if not isinstance(value, str) or len(value) > 512 or any(char.isspace() or ord(char) < 32 for char in value):
        raise AcceptanceError('EXPLICIT_HTTPS_ORIGIN_REQUIRED')
    try:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 443
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment or not 1 <= port <= 65535):
            raise ValueError()
        if ':' in host:
            host = '[' + str(ipaddress.IPv6Address(host)) + ']'
        else:
            host = host.encode('idna').decode('ascii').lower()
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) or '..' in host:
                raise ValueError()
        return 'https://' + host + (f':{port}' if port != 443 else '')
    except (ValueError, UnicodeError):
        raise AcceptanceError('EXPLICIT_HTTPS_ORIGIN_REQUIRED') from None


def approved_api_base(directory: Path, base_url: str | None, port: int) -> str:
    # The historic implicit endpoint is loopback only. A non-loopback endpoint
    # requires explicit CLI choice AND binding to this deployment's reviewed
    # non-secret CORS origins before any password is read or request is sent.
    if base_url is None:
        return f'https://localhost:{port}'
    target = https_origin(base_url)
    origins = runtime_values(directory).get('CORS_ORIGINS', '').split(',')
    if not 1 <= len(origins) <= 16 or not all(origin.strip() for origin in origins):
        raise AcceptanceError('DEPLOYMENT_HTTPS_ORIGIN_ALLOWLIST_REQUIRED')
    allowed = {https_origin(origin.strip()) for origin in origins}
    if target not in allowed:
        raise AcceptanceError('API_ORIGIN_NOT_IN_DEPLOYMENT_ALLOWLIST')
    return target
