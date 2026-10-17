#!/usr/bin/env python3
"""Offline helpers for the spare weight-set MOP. Never writes to a cluster.

build: runs crushtool on local files only; starts with no choose_args.
maps: validates all PG mappings against their actual pool sizes.
live: compares PG snapshots, optionally allowing one exact X -> S canary.
canary: validates a simple replicated host rule and prepares expected mapping.
"""
import argparse
import copy
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def cmd(*args):
    p = subprocess.run([str(x) for x in args], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    need(p.returncode == 0, 'Command failed: ' + ' '.join(map(str, args)) + '\n' + p.stderr + p.stdout)
    return p.stdout


def dump(path):
    return json.loads(cmd('crushtool', '-i', path, '--dump', '-f', 'json'))


def canonical(m):
    d = copy.deepcopy(m)
    d.pop('choose_args', None)
    return d


def fixed(w):
    need(isinstance(w, int) and w >= 0, 'Expected nonnegative fixed-point CRUSH weight')
    return format(Decimal(w) / Decimal(65536), 'f')


def exact_text(text, m):
    """Repair Pacific's 3-decimal decompiler output using integer JSON weights."""
    buckets = {b['name']: b for b in m['buckets']}
    names = {x['id']: x['name'] for x in m['devices'] + m['buckets']}
    active = None
    seen = set()
    result = []
    for line in text.splitlines():
        start = re.match(r'^\S+\s+(\S+)\s*\{\s*$', line)
        if start and start.group(1) in buckets:
            active = buckets[start.group(1)]
        item = re.match(r'^(\s*item\s+)(\S+)(\s+weight\s+)(\S+)(.*)$', line)
        if active is not None and item:
            items = {names[x['id']]: x for x in active['items']}
            need(item.group(2) in items, 'Unknown bucket item')
            v = items[item.group(2)]
            line = item.group(1) + item.group(2) + item.group(3) + fixed(v['weight']) + item.group(5)
            seen.add((active['id'], v['id']))
        result.append(line)
        if line.strip() == '}':
            active = None
    expected = {(b['id'], i['id']) for b in m['buckets']
                if '~' not in b['name'] for i in b['items']}
    need(expected <= seen, 'Not all ordinary bucket weights were repaired')
    return '\n'.join(result) + '\n'


def verify_weightset(baseline, candidate, spare):
    need(all(b['alg'] == 'straw2' for b in baseline['buckets']), 'Only straw2 is supported')
    args = candidate.get('choose_args', {})
    need(len(args) == 1, 'Expected exactly one compat weight set')
    key = next(iter(args))
    need(int(key) in (-1, 18446744073709551615), 'Expected compat key')
    vectors = {x['bucket_id']: x for x in args[key]}
    need(set(vectors) == {b['id'] for b in baseline['buckets']}, 'Missing or extra compat buckets')
    hits = []
    for bucket in baseline['buckets']:
        arg = vectors[bucket['id']]
        need(not arg.get('ids'), 'Unexpected IDs override')
        ws = arg.get('weight_set', [])
        need(len(ws) == 1 and len(ws[0]) == len(bucket['items']), 'Wrong compat vector shape')
        for item, weight in zip(bucket['items'], ws[0]):
            need(round(float(weight) * 65536) == item['weight'], 'Effective weight differs from A0')
            if item['id'] == spare:
                need(weight == 0, 'Spare compat weight is not zero')
                hits.append(bucket['name'])
    need(hits, 'Spare missing from CRUSH')
    return hits


def build(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = dump(a.baseline)
    need(not base.get('choose_args'), 'Existing weight sets: stop and use a dedicated change plan')
    need(all(b['alg'] == 'straw2' for b in base['buckets']), 'Non-straw2 bucket: stop')
    leaves = [i for b in base['buckets'] for i in b['items'] if i['id'] == a.spare]
    need(leaves and all(i['weight'] == 0 for i in leaves), 'A0 spare canonical weight must be zero')
    need(Decimal(a.weight) > 0, 'Positive weight required')
    a1 = out / 'A1.crush'
    need(Path(a.baseline).resolve() != a1.resolve(), 'Do not overwrite baseline')
    cmd('crushtool', '-i', a.baseline, '--reweight-item', 'osd.' + str(a.spare), a.weight, '-o', a1)
    d1 = dump(a1)
    d0_byid = {b['id']: b for b in base['buckets']}
    need(set(d0_byid) == {b['id'] for b in d1['buckets']}, 'Bucket IDs changed')
    for bucket in d1['buckets']:
        need([i['id'] for i in bucket['items']] == [i['id'] for i in d0_byid[bucket['id']]['items']], 'Bucket order changed')
    txt = out / 'A1.decompiled.txt'
    cmd('crushtool', '-d', a1, '-o', txt)
    precise = exact_text(txt.read_text(), d1)
    rt_text, rt_bin = out / 'A1.exact.txt', out / 'A1.roundtrip.crush'
    rt_text.write_text(precise)
    cmd('crushtool', '-c', rt_text, '-o', rt_bin)
    need(dump(rt_bin) == d1, 'A1 round trip changed the map; STOP')
    parts = [precise, 'choose_args 18446744073709551615 {']
    for bucket in base['buckets']:
        weights = ' '.join(fixed(i['weight']) for i in bucket['items'])
        parts += ['  {', '    bucket_id ' + str(bucket['id']), '    weight_set [', '      [ ' + weights + ' ]', '    ]', '  }']
    parts += ['}', '']
    btxt, bbin = out / 'B.txt', out / 'B.crush'
    btxt.write_text('\n'.join(parts))
    cmd('crushtool', '-c', btxt, '-o', bbin)
    b = dump(bbin)
    need(canonical(b) == canonical(d1), 'B canonical fields differ from A1; STOP')
    buckets = verify_weightset(base, b, a.spare)
    positive = [i['weight'] for x in b['buckets'] for i in x['items'] if i['id'] == a.spare]
    need(positive and all(w > 0 for w in positive), 'Spare canonical weight is not positive')
    write(out / 'A0.crush.json', base)
    write(out / 'A1.crush.json', d1)
    write(out / 'B.crush.json', b)
    print('PASS A1 round trip; B canonical equals A1; B compat equals A0')
    print('Spare canonical fixed-point weights:', positive)
    print('Spare compat zero in buckets:', buckets)
    print('Created', bbin)


MAP_RE = re.compile(r'^(\d+\.[0-9a-f]+)\s+raw\s+\(\[([^\]]*)\],\s*p(-?\d+)\)\s+up\s+\(\[([^\]]*)\],\s*p(-?\d+)\)\s+acting\s+\(\[([^\]]*)\],\s*p(-?\d+)\)')


def mapping(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        m = MAP_RE.match(line)
        if m:
            need(m[1] not in rows, 'Duplicate PG in mapping')
            row = {}
            for label, index in [('raw', 2), ('up', 4), ('acting', 6)]:
                row[label] = [int(x.strip()) for x in m[index].split(',') if x.strip()]
                row[label + '_primary'] = int(m[index + 1])
            rows[m[1]] = row
    need(rows, 'No PG mapping parsed; cannot PASS an empty file')
    return rows


def maps(a):
    old, new, osdmap = mapping(a.before), mapping(a.after), read(a.osdmap)
    pools = {int(x['pool']): x for x in osdmap['pools']}
    expected = {str(pid) + '.' + format(n, 'x') for pid, p in pools.items() for n in range(p['pg_num'])}
    need(set(old) == set(new) == expected, 'PG coverage differs from pool pg_num')
    osds = {x['osd'] for x in osdmap['osds']}
    for pg, row in new.items():
        size = pools[int(pg.split('.')[0])]['size']
        for label in ('raw', 'up', 'acting'):
            ids = row[label]
            need(len(ids) == size and len(set(ids)) == size and set(ids) <= osds,
                 pg + ' invalid ' + label + ' set')
            need(row[label + '_primary'] in ids, pg + ' invalid primary')
            need(a.spare not in ids, pg + ' unexpectedly maps to spare')
    changed = [pg for pg in old if old[pg] != new[pg]]
    need(not changed, 'Unexpected mapping changes: ' + ', '.join(changed[:30]))
    print('PASS', len(new), 'PGs; all raw/up/acting and primary unchanged; spare absent')


def pgs(path):
    d = read(path)
    rows = d.get('pg_stats', d.get('pg_map', {}).get('pg_stats'))
    need(isinstance(rows, list) and rows, 'Missing PG rows')
    result = {x['pgid']: x for x in rows}
    need(len(result) == len(rows), 'Duplicate PG rows')
    return result


def clean(rows):
    for pg, row in rows.items():
        states = set(row['state'].split('+'))
        need({'active', 'clean'} <= states and states <= {'active', 'clean', 'scrubbing', 'deep'}, pg + ' not stable active+clean')
        need(row['up'] == row['acting'], pg + ' up differs from acting')
        need(row['up_primary'] == row['acting_primary'], pg + ' primary differs')


def live(a):
    old, new = pgs(a.before), pgs(a.after)
    need(set(old) == set(new), 'PG set changed')
    clean(old)
    clean(new)
    canary = read(a.canary) if a.canary else None
    for pg in old:
        for field in ('up', 'acting', 'up_primary', 'acting_primary'):
            expected = old[pg][field]
            if canary and pg == canary['pgid'] and field in ('up', 'acting'):
                expected = canary['expected']
            need(new[pg][field] == expected, pg + ' changed unexpectedly: ' + field)
        hit = a.spare in new[pg]['up'] or a.spare in new[pg]['acting']
        need(hit == bool(canary and pg == canary['pgid']), pg + ' unexpected spare membership')
    print('PASS live', len(new), 'PGs; stable; expected spare membership')


def canary(a):
    rows, om, crush = pgs(a.pgs), read(a.osdmap), read(a.crush)
    clean(rows)
    need(a.pg in rows, 'PG absent')
    row = rows[a.pg]
    need(a.source != a.spare and a.source in row['up'] and a.spare not in row['up'], 'Invalid source/spare')
    need(a.source != row['up_primary'], 'Choose a replica for first canary')
    pool = next(x for x in om['pools'] if x['pool'] == int(a.pg.split('.')[0]))
    need(pool['type'] == 1 and len(row['up']) == pool['size'], 'Replicated pool required')
    for name in ('pg_upmap', 'pg_upmap_items', 'pg_temp', 'primary_temp'):
        need(not any(x.get('pgid') == a.pg for x in om.get(name, [])), 'Existing ' + name + ' on canary')
    types = {x['type_id']: x['name'] for x in crush['types']}
    host_ids = {t for t, name in types.items() if name == 'host'}
    host = {}
    for b in crush['buckets']:
        if b['type_id'] in host_ids and '~' not in b['name']:
            for i in b['items']:
                if i['id'] >= 0:
                    need(i['id'] not in host, 'OSD belongs to multiple hosts')
                    host[i['id']] = b['id']
    need(a.source in host and a.spare in host and host[a.source] == host[a.spare], 'Source and spare must share host')
    expected = [a.spare if x == a.source else x for x in row['up']]
    need(len({host[x] for x in expected}) == pool['size'], 'Duplicate failure domain')
    rule = next(x for x in crush['rules'] if x['rule_id'] == pool['crush_rule'])
    steps = rule['steps']
    need(len(steps) == 3 and [x['op'] for x in steps] == ['take', 'chooseleaf_firstn', 'emit'], 'Only simple take/chooseleaf/emit rule supported')
    need(steps[1]['type'] == 'host' and steps[1]['num'] == 0, 'Expected chooseleaf firstn 0 type host')
    buckets = {x['id']: x for x in crush['buckets']}
    def descendants(item):
        if item >= 0:
            return {item}
        need(item in buckets, 'Unknown rule root')
        return set().union(*(descendants(x['id']) for x in buckets[item]['items']))
    need(set(expected) <= descendants(steps[0]['item']), 'Spare is outside rule root or device class')
    objects = row.get('stat_sum', {}).get('num_objects', 0)
    need(objects > 0, 'Choose a PG with existing data for data-movement evidence')
    osds = {x['osd']: x for x in om['osds']}
    for osd in expected + [a.source]:
        need(osds[osd]['up'] == 1 and osds[osd]['in'] == 1 and osds[osd]['weight'] == 1, 'OSD must be up/in/reweight 1')
    write(a.out, {'pgid': a.pg, 'source': a.source, 'spare': a.spare,
                  'pool': pool['pool_name'], 'before': row['up'], 'expected': expected,
                  'primary': row['up_primary'], 'num_objects': objects})
    print('PASS canary', a.pg, row['up'], '->', expected, 'objects', objects)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action')
    b = sub.add_parser('build')
    b.add_argument('baseline'); b.add_argument('--spare', type=int, required=True)
    b.add_argument('--weight', default='0.0001'); b.add_argument('--out', required=True)
    m = sub.add_parser('maps')
    m.add_argument('before'); m.add_argument('after'); m.add_argument('osdmap')
    m.add_argument('--spare', type=int, required=True)
    l = sub.add_parser('live')
    l.add_argument('before'); l.add_argument('after'); l.add_argument('--spare', type=int, required=True)
    l.add_argument('--canary')
    c = sub.add_parser('canary')
    for x in ('pgs', 'osdmap', 'crush'): c.add_argument(x)
    c.add_argument('--pg', required=True); c.add_argument('--source', type=int, required=True)
    c.add_argument('--spare', type=int, required=True); c.add_argument('--out', required=True)
    a = p.parse_args()
    if not a.action:
        p.error('Specify build, maps, live, or canary')
    try:
        {'build': build, 'maps': maps, 'live': live, 'canary': canary}[a.action](a)
    except (ValueError, KeyError, StopIteration, OSError, subprocess.SubprocessError) as e:
        print('STOP:', str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
