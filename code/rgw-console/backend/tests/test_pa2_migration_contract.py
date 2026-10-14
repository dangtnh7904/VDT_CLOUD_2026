from pathlib import Path
import unittest


class Pa2MigrationContractTests(unittest.TestCase):
    def test_pa2_migration_contains_durable_wave_ledger(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "migrations"
            / "versions"
            / "0014_pa2_spare_chain_ledger.sql"
        ).read_text(encoding="utf-8")

        for table in (
            "upgrade_waves",
            "spare_registry",
            "spare_chains",
            "handoff_groups",
            "rotation_steps",
            "end_state_handoffs",
        ):
            with self.subTest(table=table):
                self.assertIn(f"CREATE TABLE {table}", migration)

        self.assertIn("HANDOFF_COMPLETE", migration)
        self.assertIn("WAVE_COMPLETE", migration)
        self.assertIn("NOT_EXERCISED", migration)


if __name__ == "__main__":
    unittest.main()
