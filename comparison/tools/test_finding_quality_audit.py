"""Regression checks for evidence leaking across Markdown heading boundaries."""

import unittest

from audit_finding_quality import DIMENSIONS, finding_sections


class FindingSectionTests(unittest.TestCase):
    def test_footer_cannot_supply_missing_evidence(self):
        text = "### TST-001 — Limited finding\nCSV: source.cc. Pacific differs from Quincy.\n"
        text += "## Validation and limits\nrollback mixed full config impact confidence lab chưa\n"
        sections = finding_sections(text)
        self.assertEqual([finding_id for finding_id, _ in sections], ["TST-001"])
        body = sections[0][1]
        for dimension in ("rollback_boundary", "mixed_full", "confidence", "validation"):
            self.assertIsNone(DIMENSIONS[dimension].search(body), dimension)

    def test_every_supported_heading_level_ends_the_finding(self):
        for level in range(1, 5):
            with self.subTest(level=level):
                text = "### TST-001 — Finding\nlocal evidence\n"
                text += "#" * level + " Boundary\nrollback from outside\n"
                self.assertNotIn("rollback from outside", finding_sections(text)[0][1])

    def test_parent_heading_ids_are_not_findings(self):
        text = "## TST-999 — Aggregate\n### TST-001 and TST-002\nshared evidence\n"
        text += "#### TST-003 — Child\nchild evidence\n## Footer\nfooter evidence\n"
        sections = finding_sections(text)
        self.assertEqual([finding_id for finding_id, _ in sections], ["TST-001", "TST-002", "TST-003"])
        self.assertEqual(sections[0][1], sections[1][1])
        self.assertNotIn("child evidence", sections[0][1])
        self.assertNotIn("footer evidence", sections[2][1])

    def test_final_finding_keeps_own_evidence_and_crlf(self):
        text = "### TST-001 — Final\r\nCSV Pacific Quincy khi mixed rollback impact confidence lab automatic chưa\r\n"
        sections = finding_sections(text)
        self.assertEqual(sections, [("TST-001", text)])
        self.assertTrue(all(pattern.search(sections[0][1]) for pattern in DIMENSIONS.values()))


if __name__ == "__main__":
    unittest.main()
