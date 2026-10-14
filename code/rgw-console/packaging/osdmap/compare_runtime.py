"""Compare offline runtimes against the same generated (never live) maps.

Run --prepare once with the pinned donor; then --evaluate under each runtime.
The resulting canonical JSON files must have identical SHA-256 values. Only
the known stdout notification's temporary CRUSH export path is normalized;
original worker JSON and original stdout remain separate evidence files.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from worker import TOOL, run_tool, simulate

CASES = ('no-op', 'multiple-weights', 'upmap-no-op')


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        source = scratch / 'generated.osdmap'
        run_tool([str(source), '--createsimple', '6', '--with-default-pool',
                  '--mark-up-in', '--osd-crush-chooseleaf-type', '0'], scratch)
        for name in CASES:
            if name == 'upmap-no-op':
                run_tool([str(source), '--adjust-crush-weight', '0:0.5',
                          '--upmap', str(scratch / 'generated-commands'),
                          '--upmap-max', '10', '--save'], scratch)
            decoded = json.loads(run_tool([str(source), '--dump', 'json'], scratch))
            if name == 'upmap-no-op' and not decoded['pg_upmap_items']:
                raise RuntimeError('Generated override fixture has no pg_upmap_items')
            raw = source.read_bytes()
            changes = ([{'osd_id': 0, 'crush_weight': 0.5}] if name == 'upmap-no-op'
                       else [{'osd_id': osd, 'crush_weight': 0 if name == 'multiple-weights' else 1}
                             for osd in (0, 1)])
            request = {'map': base64.b64encode(raw).decode(),
                       'base_sha256': hashlib.sha256(raw).hexdigest(),
                       'fsid': decoded['fsid'], 'pool_id': None,
                       'allowed_pool_ids': [pool['pool'] for pool in decoded['pools']],
                       'changes': changes}
            (root / (name + '.json')).write_text(json.dumps(request, sort_keys=True))
            metadata = {'fsid': decoded['fsid'], 'epoch': decoded['epoch'],
                        'pools': decoded['pools'], 'osds': decoded['osds'],
                        'tool_version': run_tool(['--version'], scratch).strip(),
                        'scope': 'GENERATED_OFFLINE_FIXTURE_NOT_LIVE_CEPH'}
            (root / (name + '.metadata.json')).write_text(json.dumps(metadata, sort_keys=True))
    print('Prepared three isolated generated-map cases; no cluster was contacted.')


def evaluate(root, output):
    results = {}
    version = run_tool(['--version'], root).strip()
    for name in CASES:
        request = json.loads((root / (name + '.json')).read_text())
        captured = []
        def capture_output(args, cwd, tool=TOOL):
            text = run_tool(args, cwd, tool)
            if '--test-map-pgs-dump-all' in args:
                filename = 'before.crush' if not captured else 'after.crush'
                notice = '/usr/bin/osdmaptool: exported crush map to ' + str(cwd / filename)
                if text.splitlines().count(notice) != 1:
                    raise RuntimeError('Unexpected CRUSH export notification; cannot normalize output')
                normalized = text.replace(notice, '/usr/bin/osdmaptool: exported crush map to <scratch>/' + filename)
                captured.append((text, normalized))
            return text
        with tempfile.TemporaryDirectory() as tmp:
            with patch('worker.run_tool', side_effect=capture_output):
                results[name] = simulate(request, Path(tmp), version)
        if len(captured) != 2:
            raise RuntimeError('Expected exactly two placement output streams')
        # Keep original results/hashes. Do not rewrite production evidence to
        # make two processes look byte-identical when their scratch paths differ.
        (root / (output + '.' + name + '.worker.json')).write_text(
            json.dumps(results[name], sort_keys=True, separators=(',', ':')))
        for index, (text, normalized) in enumerate(captured):
            (root / (output + '.' + name + '.' + str(index) + '.txt')).write_text(text)
            key = 'before' if index == 0 else 'after'
            original_hash = results[name]['output_sha256'].pop(key)
            if original_hash != hashlib.sha256(text.encode()).hexdigest():
                raise RuntimeError('Captured stdout does not match original worker hash')
            results[name].setdefault('normalized_mapping_output_sha256', {})[key] = hashlib.sha256(normalized.encode()).hexdigest()
        if name != 'multiple-weights' and results[name]['summary']['changed_pgs']:
            raise RuntimeError('No-op fixture unexpectedly changes placement')
        if name == 'multiple-weights' and not results[name]['summary']['changed_pgs']:
            raise RuntimeError('Weight fixture did not exercise changed placement')
    encoded = json.dumps(results, sort_keys=True, separators=(',', ':')).encode()
    (root / output).write_bytes(encoded)
    print(json.dumps({'cases': len(results), 'bytes': len(encoded),
                      'sha256': hashlib.sha256(encoded).hexdigest(), 'result': output}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--evaluate', choices=('rc1-result.json', 'minimal-result.json'))
    args = parser.parse_args()
    if args.prepare:
        prepare(args.root)
    else:
        evaluate(args.root, args.evaluate)
