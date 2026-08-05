import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_stroller_attributes import audit_attributes


class StrollerAttributeAuditTests(unittest.TestCase):
    def test_audit_has_decision_for_each_field(self):
        report = audit_attributes([{"product_id":"p1", "attributes":[{"key":"frame_weight", "value":"5", "unit":"kg"}]}])
        self.assertEqual(report["field_count"], 21)
        self.assertEqual(len(report["decisions"]), 21)
        self.assertTrue(all(item["role"] in {"scored", "informational", "identity", "excluded"} for item in report["decisions"]))

    def test_empty_source_is_reported_as_zero_coverage(self):
        report = audit_attributes([])
        self.assertTrue(all(item["coverage"] == 0 for item in report["decisions"]))


if __name__ == "__main__": unittest.main()
