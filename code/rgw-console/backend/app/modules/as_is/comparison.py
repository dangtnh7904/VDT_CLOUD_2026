from __future__ import annotations

import math


class ComparisonError(ValueError):
    pass


def _numeric(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _delta(before, after):
    value = after - before
    return value if _numeric(value) else None


def _flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        if key in {'payload', 'orchestrator_observed_at'}:
            continue
        field = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, field))
        else:
            result[field] = item
    return result


def compare_collections(a, b, daemon_type, daemon_keys=None):
    if a['fsid'] != b['fsid']:
        raise ComparisonError('Chỉ so sánh collection trong cùng cluster FSID.')
    def index(collection):
        return {row['key']: row for row in collection['daemons'] if row['type'] == daemon_type}
    left, right = index(a), index(b)
    if not left or not right:
        raise ComparisonError('Cả hai collection phải có dữ liệu của loại daemon đã chọn.')
    selected = set(daemon_keys or [])
    if selected and any(not key.startswith(daemon_type + '.') for key in selected):
        raise ComparisonError('Chỉ chọn daemon cùng loại để so sánh.')
    keys = set(left) | set(right)
    if selected - keys:
        raise ComparisonError('Daemon được chọn không có trong cả hai collection.')
    if selected:
        keys &= selected
    rows = []
    summary = {'both': 0, 'only_a': 0, 'only_b': 0, 'changed': 0}
    for key in sorted(keys):
        one, two = left.get(key), right.get(key)
        coverage = 'BOTH' if one and two else 'ONLY_A' if one else 'ONLY_B'
        summary[coverage.lower()] += 1
        changes = []
        if one and two:
            old, new = _flatten(one['fields']), _flatten(two['fields'])
            incarnation = 'osd_fsid' if daemon_type == 'osd' else 'gid'
            reset = old.get(incarnation) != new.get(incarnation) or any(
                old.get(k) != new.get(k) and old.get(k) is not None and new.get(k) is not None
                for k in ('container_id', 'started_at'))
            for field in sorted(set(old) | set(new)):
                before, after = old.get(field), new.get(field)
                if before == after:
                    continue
                numeric = all(_numeric(v) for v in (before, after))
                counter = any(word in field for word in ('counter', 'epoch', 'uptime'))
                reason = ('INCARNATION_CHANGED' if reset else 'FIELD_UNAVAILABLE' if before is None or after is None
                          else 'COUNTER_RESET' if counter and numeric and after < before else None)
                delta = _delta(before, after) if numeric and reason is None else None
                if numeric and reason is None and delta is None:
                    reason = 'NUMERIC_OUT_OF_RANGE'
                changes.append({'field': field, 'a': before, 'b': after, 'delta': delta, 'reason': reason})
            old_metrics = {m['metric_id']: m for m in one.get('metrics', [])}
            new_metrics = {m['metric_id']: m for m in two.get('metrics', [])}
            for metric_id in sorted(set(old_metrics) | set(new_metrics)):
                first, second = old_metrics.get(metric_id, {}), new_metrics.get(metric_id, {})
                before, after = first.get('value'), second.get('value')
                if before == after and first.get('quality') == second.get('quality') and first.get('unit') == second.get('unit') and first.get('kind') == second.get('kind'):
                    continue
                reason = ('INCARNATION_CHANGED' if reset else 'METRIC_UNAVAILABLE' if before is None or after is None
                    else 'UNIT_CHANGED' if first.get('unit') != second.get('unit')
                    else 'METRIC_KIND_CHANGED' if first.get('kind') != second.get('kind')
                    else 'QUALITY_INSUFFICIENT' if any(m.get('quality') != 'VALID' for m in (first, second)) else None)
                numeric = all(_numeric(v) for v in (before, after))
                if reason is None and not numeric and before is not None and after is not None and not all(isinstance(value, bool) for value in (before, after)):
                    reason = 'METRIC_VALUE_INVALID'
                if reason is None and first.get('kind') == 'counter' and numeric and after < before:
                    reason = 'COUNTER_RESET'
                delta = _delta(before, after) if numeric and reason is None else None
                if numeric and reason is None and delta is None:
                    reason = 'NUMERIC_OUT_OF_RANGE'
                changes.append({'field': 'metrics.' + metric_id, 'a': before, 'b': after,
                    'delta': delta, 'reason': reason,
                    'unit': first.get('unit'), 'window_a': first.get('window_seconds'), 'window_b': second.get('window_seconds')})
        if changes:
            summary['changed'] += 1
        rows.append({'key': key, 'coverage': coverage, 'changes': changes, 'a': one, 'b': two})
    def reference(collection):
        return {key: collection.get(key) for key in ('id', 'phase', 'started_at', 'completed_at', 'sha256', 'quality')}
    return {'kind': 'AS_IS_COMPARISON', 'fsid': a['fsid'], 'daemon_type': daemon_type,
            'config_changed': a.get('config_hash') != b.get('config_hash'),
            'collection_a': reference(a), 'collection_b': reference(b), 'rows': rows, 'summary': summary,
            'limitations': ['Đây là so sánh dữ liệu đã lưu; không phải kết luận nâng cấp thành công.',
                            'Daemon chỉ có ở một collection được ghi nhận riêng; không giả định daemon đã dừng.']}
