"""Bounded, filter-scoped keyset cursors for immutable As-is history.

Cursors are navigation hints, not authorization tokens. Cluster/FSID filtering is
always enforced independently by the repository, even for a forged cursor.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID


class InvalidCursor(ValueError):
    pass


def filter_hash(filters):
    body = json.dumps(filters, ensure_ascii=True, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def encode_cursor(row, filters):
    body = json.dumps({'v': 1, 'at': str(row['started_at']), 'id': str(row['id']),
                       'filters': filter_hash(filters)}, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip('=')


def decode_cursor(cursor, filters):
    if cursor is None:
        return None
    try:
        if not cursor or len(cursor) > 1024 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in cursor):
            raise ValueError('invalid encoding')
        value = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
        if not isinstance(value, dict) or set(value) != {'v', 'at', 'id', 'filters'} or value['v'] != 1 or value['filters'] != filter_hash(filters):
            raise ValueError('different scope')
        at = datetime.fromisoformat(value['at'].replace('Z', '+00:00'))
        if at.tzinfo is None:
            raise ValueError('missing timezone')
        return at, UUID(value['id'])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InvalidCursor('Mã phân trang không hợp lệ hoặc không khớp bộ lọc. Hãy tải lại từ trang đầu.') from exc
