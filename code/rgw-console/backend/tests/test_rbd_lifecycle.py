from __future__ import annotations

import os
import unittest
import uuid
from contextlib import nullcontext
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.migrations.runner import migrate
from app.services.rbd_lifecycle import ClaimedAction, RbdLifecycleWorker, granular_action_id


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


class RbdLifecycleIdentityTests(unittest.TestCase):
    def test_step_action_ids_are_stable_and_step_specific(self) -> None:
        action_id = uuid.uuid4()
        first = granular_action_id(action_id, "rbd.image.create")
        self.assertEqual(first, granular_action_id(action_id, "rbd.image.create"))
        self.assertNotEqual(first, granular_action_id(action_id, "rbd.image.map"))


@unittest.skipUnless(DATABASE_URL, "set TEST_DATABASE_URL to run RBD fencing integration tests")
class RbdFenceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        self.schema = f"rbd_fence_test_{uuid.uuid4().hex}"
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
        migrate(self.conn)

    def tearDown(self) -> None:
        self.conn.rollback()
        self.conn.close()

    def test_step_fence_is_reused_for_reconcile_and_advanced_for_next_step(self) -> None:
        request_id = uuid.uuid4()
        action_id = uuid.uuid4()
        volume_id = uuid.uuid4()
        idem = self.conn.execute(
            """
            INSERT INTO idempotency_requests (
              scope,idempotency_key,http_method,resource,request_fingerprint,
              state,owner_id,fencing_generation,request_id,action_id
            ) VALUES ('test','test-key','POST','rbd:test',%s,'IN_PROGRESS','test',1,%s,%s)
            RETURNING id
            """,
            ("sha256:" + "0" * 64, request_id, action_id),
        ).fetchone()
        self.conn.execute(
            """
            INSERT INTO rbd_volumes (
              id,pool,namespace,image_name,logical_size_bytes,desired_state,
              observed_state,transition_generation
            ) VALUES (%s,'rbd-lab',NULL,'rgw-console-test',16777216,'READY','CREATED',1)
            """,
            (volume_id,),
        )
        self.conn.execute(
            """
            INSERT INTO rbd_actions (
              id,idempotency_request_id,volume_id,action_type,intended_state,
              observed_state,state,volume_generation,lease_owner,lease_generation
            ) VALUES (%s,%s,%s,'CREATE','READY','CREATED','RUNNING',1,'worker-test',1)
            """,
            (action_id, idem["id"], volume_id),
        )
        claimed = ClaimedAction(
            action={
                "id": action_id,
                "lease_generation": 1,
                "volume_generation": 1,
            },
            volume={"id": volume_id},
            request_id=str(request_id),
        )
        worker = RbdLifecycleWorker.__new__(RbdLifecycleWorker)
        worker.worker_id = "worker-test"
        worker.lease_seconds = 120

        with patch(
            "app.services.rbd_lifecycle.connection",
            side_effect=lambda: nullcontext(self.conn),
        ):
            create_fence = worker._set_current_step(claimed, "rbd.image.create")
            replay_fence = worker._set_current_step(claimed, "rbd.image.create")
            map_fence = worker._set_current_step(claimed, "rbd.image.map")

        self.assertEqual(create_fence, replay_fence)
        self.assertGreater(map_fence, create_fence)
        row = self.conn.execute(
            "SELECT executor_fence_token FROM rbd_volumes WHERE id=%s", (volume_id,)
        ).fetchone()
        self.assertEqual(row["executor_fence_token"], map_fence)


if __name__ == "__main__":
    unittest.main()
