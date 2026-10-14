"""Inspect actual local OCI blobs; this is not signature/SLSA-level approval."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile


def inspect_archive(path, revision, expected_digest):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('EXACT_SOURCE_REVISION_REQUIRED')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', expected_digest):
        raise ValueError('EXACT_INDEX_DIGEST_REQUIRED')
    with tarfile.open(path, 'r:*') as archive:
        members = {entry.name: entry for entry in archive.getmembers()}
        if len(members) != len(archive.getmembers()):
            raise ValueError('DUPLICATE_ARCHIVE_MEMBER')
        count = 0
        for name, entry in members.items():
            if not re.fullmatch(r'blobs/sha256/[0-9a-f]{64}', name):
                continue
            if not entry.isfile() or entry.size > 512 * 1024 * 1024:
                raise ValueError('INVALID_BLOB_ENTRY')
            digest = hashlib.sha256()
            with archive.extractfile(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != name.rsplit('/', 1)[1]:
                raise ValueError('BLOB_CHECKSUM_MISMATCH')
            count += 1

        def read_json(name):
            entry = members[name]
            if not entry.isfile() or entry.size > 8 * 1024 * 1024:
                raise ValueError('JSON_BLOB_EXCEEDS_BOUND')
            return json.load(archive.extractfile(entry))

        def blob(descriptor):
            digest = descriptor['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('INVALID_DESCRIPTOR_DIGEST')
            name = 'blobs/sha256/' + digest.split(':')[1]
            if members[name].size != descriptor['size']:
                raise ValueError('DESCRIPTOR_SIZE_MISMATCH')
            return read_json(name)

        root = read_json('index.json')
        descriptors = root['manifests']
        if len(descriptors) == 1 and descriptors[0]['mediaType'].endswith('image.index.v1+json'):
            if descriptors[0]['digest'] != expected_digest:
                raise ValueError('INDEX_DIGEST_MISMATCH')
            descriptors = blob(descriptors[0])['manifests']
        else:
            with archive.extractfile(members['index.json']) as stream:
                if 'sha256:' + hashlib.sha256(stream.read()).hexdigest() != expected_digest:
                    raise ValueError('INDEX_DIGEST_MISMATCH')
        amd64 = [row for row in descriptors if row.get('platform') == {'architecture': 'amd64', 'os': 'linux'}]
        if len(amd64) != 1:
            raise ValueError('ONE_LINUX_AMD64_MANIFEST_REQUIRED')
        subject = amd64[0]['digest']
        manifest = blob(amd64[0])
        labels = blob(manifest['config'])['config']['Labels']
        if labels.get('org.opencontainers.image.revision') != revision:
            raise ValueError('OCI_REVISION_MISMATCH')
        attestations = [row for row in descriptors if row.get('annotations', {}).get('vnd.docker.reference.type') == 'attestation-manifest'
                        and row.get('annotations', {}).get('vnd.docker.reference.digest') == subject]
        if len(attestations) != 1:
            raise ValueError('ONE_BOUND_ATTESTATION_MANIFEST_REQUIRED')
        receipts = {}
        for layer in blob(attestations[0])['layers']:
            document = blob(layer)
            if not document.get('subject') or any(row.get('digest', {}).get('sha256') != subject.split(':')[1] for row in document['subject']):
                raise ValueError('ATTESTATION_SUBJECT_MISMATCH')
            kind = document.get('predicateType')
            predicate = document['predicate']
            if kind == 'https://spdx.dev/Document':
                receipts['sbom'] = {'digest': layer['digest'], 'spdx_version': predicate['spdxVersion'],
                                    'package_count': len(predicate.get('packages', [])),
                                    'creators': predicate.get('creationInfo', {}).get('creators', [])}
            elif kind == 'https://slsa.dev/provenance/v1':
                vcs = predicate['runDetails']['metadata']['buildkit_metadata']['vcs']
                if vcs.get('revision') != revision or vcs.get('dirty') not in (None, False, 'false'):
                    raise ValueError('PROVENANCE_SOURCE_REVISION_OR_CLEANLINESS_MISMATCH')
                receipts['provenance'] = {'digest': layer['digest'], 'source_revision': vcs['revision'],
                                          'source': vcs.get('source'), 'not_a_slsa_level_claim': True}
        if set(receipts) != {'sbom', 'provenance'}:
            raise ValueError('SBOM_AND_PROVENANCE_REQUIRED')
        return {'status': 'PASS', 'index_digest': expected_digest, 'amd64_manifest_digest': subject,
                'oci_revision': revision, 'blob_checksums_verified': count, **receipts,
                'signature_verified': False, 'production_approved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--index-digest', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit('REFUSING_TO_OVERWRITE_RECEIPT')
    try:
        result = inspect_archive(args.archive, args.source_revision, args.index_digest)
    except (KeyError, ValueError, OSError, tarfile.TarError) as exc:
        result = {'status': 'FAIL', 'error_code': str(exc) if isinstance(exc, ValueError) else 'INVALID_OCI_ARCHIVE',
                  'production_approved': False}
    args.report.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'report': str(args.report)}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
