import unittest

from modules.agent.orchestration.runtime.search_quality import (
    classify_search_action_quality,
    SearchQualityKind,
    SearchQualitySeverity,
)


class TestSearchQualityClassifier(unittest.TestCase):
    def test_non_search_action_is_ok(self):
        quality = classify_search_action_quality({"type": "read_file_skeleton", "path": "a.py"})
        self.assertFalse(quality["is_search"])
        self.assertEqual(SearchQualityKind.NON_SEARCH_ACTION, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])

    def test_search_files_with_pattern_is_exact_lookup(self):
        quality = classify_search_action_quality({"type": "search_files", "pattern": "CapabilityRegistry.kt"})
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.EXACT_LOOKUP, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])

    def test_bounded_recon_search_is_ok(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "app/src/main/java",
                "pattern": "CapabilityRegistry",
                "include_extensions": ["kt"],
                "code_only": True,
            }
        )
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.BOUNDED_RECON, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])
        self.assertGreaterEqual(quality["bound_count"], 2)

    def test_unbounded_broad_search_is_warn(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": ".",
                "pattern": "CapabilityRegistry",
            }
        )
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.UNBOUNDED_BROAD, quality["kind"])
        self.assertEqual(SearchQualitySeverity.WARN, quality["severity"])
        self.assertEqual("root_search_without_bounds", quality["reason"])

    def test_unbounded_broad_search_with_empty_path_is_warn(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "",
                "pattern": "CapabilityRegistry",
            }
        )
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.UNBOUNDED_BROAD, quality["kind"])
        self.assertEqual(SearchQualitySeverity.WARN, quality["severity"])
        self.assertEqual("root_search_without_bounds", quality["reason"])

    def test_exact_anchor_unscoped_search_is_warn(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "",
                "pattern": "CapabilityId|CapabilityRegistry|CapabilityCatalog",
                "code_only": True,
            }
        )
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.UNBOUNDED_BROAD, quality["kind"])
        self.assertEqual(SearchQualitySeverity.WARN, quality["severity"])
        self.assertEqual("exact_anchor_unscoped", quality["reason"])
        self.assertLess(quality["bound_count"], 2)
        self.assertIn("path", quality["missing_bounds"])
        self.assertIn("include_extensions", quality["missing_bounds"])
