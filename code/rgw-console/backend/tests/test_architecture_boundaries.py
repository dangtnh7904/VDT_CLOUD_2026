from __future__ import annotations

import ast
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_FILES = tuple((BACKEND_ROOT / "app" / "modules").glob("*/domain.py")) + (
    BACKEND_ROOT / "app" / "platform" / "leases" / "domain.py",
)
FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "fastapi",
    "psycopg",
    "boto3",
    "botocore",
    "httpx",
    "pydantic",
    "pydantic_settings",
}


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_modules_do_not_import_framework_or_adapter_dependencies(self):
        violations = []
        for path in DOMAIN_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".", 1)[0] in FORBIDDEN_TOP_LEVEL_IMPORTS:
                        violations.append(f"{path.name}:{node.lineno}:{name}")

        self.assertEqual(violations, [])

    def test_domain_files_are_present_for_new_bounded_modules(self):
        relative = {path.relative_to(BACKEND_ROOT).as_posix() for path in DOMAIN_FILES}

        self.assertIn("app/modules/cluster_profiles/domain.py", relative)
        self.assertIn("app/modules/sessions/domain.py", relative)
        self.assertIn("app/modules/upgrade_common/domain.py", relative)


if __name__ == "__main__":
    unittest.main()
