import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest


script = Path(__file__).resolve().parents[2] / 'scripts' / 'verify_oci_candidate.py'
spec = importlib.util.spec_from_file_location('candidate_verifier', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OciCandidateVerificationTests(unittest.TestCase):
    def test_revision_must_be_exact_commit_not_branch(self):
        with self.assertRaisesRegex(ValueError, 'EXACT_SOURCE_REVISION_REQUIRED'):
            module.inspect_archive('unused', 'main', 'sha256:' + 'a' * 64)

    def test_digest_must_be_exact_not_mutable_tag(self):
        with self.assertRaisesRegex(ValueError, 'EXACT_INDEX_DIGEST_REQUIRED'):
            module.inspect_archive('unused', 'a' * 40, 'candidate:latest')

    def test_tampered_blob_rejected_before_provenance_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.tar'
            with tarfile.open(path, 'w') as archive:
                content = b'tampered'
                item = tarfile.TarInfo('blobs/sha256/' + 'a' * 64)
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, 'BLOB_CHECKSUM_MISMATCH'):
                module.inspect_archive(path, 'a' * 40, 'sha256:' + 'a' * 64)

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.tar'
            with tarfile.open(path, 'w') as archive:
                for _ in range(2):
                    content = json.dumps({'schemaVersion': 2}).encode()
                    item = tarfile.TarInfo('index.json'); item.size = len(content)
                    archive.addfile(item, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, 'DUPLICATE_ARCHIVE_MEMBER'):
                module.inspect_archive(path, 'a' * 40, 'sha256:' + 'a' * 64)


if __name__ == '__main__':
    unittest.main()
