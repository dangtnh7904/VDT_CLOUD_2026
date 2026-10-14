from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID

from app.platform.leases import LeaseToken


class UpgradeLeaseDomainTests(unittest.TestCase):
    def test_fencing_generation_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "generation"):
            LeaseToken(
                cluster_id="lab-a",
                resource_type="OSD",
                resource_id="0",
                owner_run_id=UUID("11111111-1111-4111-8111-111111111111"),
                generation=0,
                expires_at=datetime.now(timezone.utc),
            )

    def test_expiry_must_be_timezone_aware(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            LeaseToken(
                cluster_id="lab-a",
                resource_type="OSD",
                resource_id="0",
                owner_run_id=UUID("11111111-1111-4111-8111-111111111111"),
                generation=1,
                expires_at=datetime.now(),
            )


if __name__ == "__main__":
    unittest.main()
