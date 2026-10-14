import json
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.db import json_ready


class JsonReadyTests(unittest.TestCase):
    def test_real_postgres_uuid_and_timestamp_are_serializable_without_mutating_row(self):
        identity = uuid4()
        observed_at = datetime(2026, 10, 12, tzinfo=timezone.utc)
        row = {"id": identity, "session_id": identity, "fsid": identity,
               "collected_at": observed_at, "config": '{"read_only": true}'}
        result = json_ready(row)
        self.assertEqual(json.loads(json.dumps(result))["id"], str(identity))
        self.assertEqual(result["collected_at"], observed_at.isoformat())
        self.assertEqual(result["config"], {"read_only": True})
        self.assertIs(row["id"], identity)

