"""Validate the read-only CLI shapes consumed by the As-is projections.

Missing or unrecognized source data is not a successful empty inventory. Keep
this validation local to the new collector so legacy stored schemas stay intact.
"""
from __future__ import annotations

import json
import re

from ..cluster_metrics.normalization import daemon_source_valid


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _named(row, field):
    return isinstance(row, dict) and isinstance(row.get(field), str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,256}', row[field]) is not None


def source_valid(action, value):
    try:
        # JSON parsers can accept NaN/Infinity although export/JSONB cannot.
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        return False
    if not daemon_source_valid(action, value):
        return False
    if action in {'ceph.daemon_ls', 'ceph.fs_dump', 'ceph.client_environment'}:
        return True
    if action == 'ceph.host_ls':
        return isinstance(value, list) and all(_named(row, 'hostname') for row in value)
    if action == 'ceph.pool_ls_detail':
        return isinstance(value, list) and all(isinstance(row, dict) and isinstance(row.get('pool_name'), str) and bool(row['pool_name']) and _integer(row.get('pool', row.get('pool_id'))) for row in value)
    if not isinstance(value, dict):
        return False
    if action == 'ceph.status':
        return isinstance(value.get('health'), dict) and isinstance(value.get('pgmap'), dict)
    if action == 'ceph.health_detail':
        return isinstance(value.get('status'), str) and isinstance(value.get('checks'), dict)
    if action == 'ceph.df':
        return isinstance(value.get('stats'), dict) and isinstance(value.get('pools'), list) and all(isinstance(row, dict) for row in value['pools'])
    if action == 'ceph.versions':
        return all(isinstance(versions, dict) for versions in value.values())
    if action == 'ceph.mon_dump':
        return isinstance(value.get('mons'), list) and all(_named(row, 'name') and _integer(row.get('rank')) for row in value['mons'])
    if action == 'ceph.quorum_status':
        return isinstance(value.get('quorum'), list) and all(_integer(rank) for rank in value['quorum'])
    if action == 'ceph.mgr_dump':
        return ('active_name' in value or 'standbys' in value) and isinstance(value.get('active_name', ''), str) and isinstance(value.get('standbys', []), list) and all(_named(row, 'name') for row in value.get('standbys', []))
    if action == 'ceph.mgr_modules':
        return isinstance(value.get('enabled_modules'), list) and all(isinstance(name, str) for name in value['enabled_modules'])
    if action in {'ceph.osd_df', 'ceph.osd_tree'}:
        return isinstance(value.get('nodes'), list) and all(isinstance(row, dict) and _integer(row.get('id')) for row in value['nodes'])
    if action == 'ceph.osd_dump':
        return isinstance(value.get('osds'), list) and isinstance(value.get('pools'), list) and all(isinstance(row, dict) and _integer(row.get('osd')) for row in value['osds']) and all(isinstance(row, dict) and _integer(row.get('pool')) for row in value['pools'])
    if action == 'ceph.crush_dump':
        return all(isinstance(value.get(key), list) and all(isinstance(row, dict) for row in value[key]) for key in ('buckets', 'rules', 'devices'))
    if action == 'ceph.pg_dump':
        return isinstance(value.get('pg_stats'), list) and all(isinstance(row, dict) for row in value['pg_stats'])
    return True
