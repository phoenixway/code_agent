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
        self.assertEqual("not_applicable", quality["path_validity"])

    def test_search_files_with_pattern_is_exact_lookup(self):
        quality = classify_search_action_quality({"type": "search_files", "pattern": "CapabilityRegistry.kt"})
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.EXACT_LOOKUP, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])
        self.assertEqual("known_valid", quality["path_validity"])

    def test_bounded_recon_search_is_ok(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "modules",
                "pattern": "CapabilityRegistry",
                "include_extensions": ["kt"],
                "code_only": True,
            }
        )
        self.assertTrue(quality["is_search"])
        self.assertEqual(SearchQualityKind.BOUNDED_RECON, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])
        self.assertEqual(SearchQualitySeverity.OK, quality["boundedness_severity"])
        self.assertEqual("known_valid", quality["path_validity"])
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
        self.assertEqual("known_valid", quality["path_validity"])

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
        self.assertEqual(".", quality["path"])
        self.assertEqual("known_valid", quality["path_validity"])

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

    def test_search_content_with_nonexistent_path_is_invalid(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "app/src/main/java/com/mranrg/m",
                "pattern": "journal",
                "include_extensions": ["kt"],
                "code_only": True,
            }
        )

        self.assertEqual(SearchQualityKind.BOUNDED_RECON, quality["kind"])
        self.assertEqual(SearchQualitySeverity.OK, quality["boundedness_severity"])
        self.assertEqual("invalid", quality["path_validity"])
        self.assertEqual("missing", quality["actual_path_kind"])
        self.assertEqual("SEARCH_ROOT_NOT_FOUND", quality["path_validation_error_code"])
        self.assertEqual(SearchQualitySeverity.BLOCK, quality["severity"])
        self.assertEqual("invalid_search_root", quality["reason"])

    def test_search_files_with_nonexistent_path_is_invalid(self):
        quality = classify_search_action_quality(
            {
                "type": "search_files",
                "path": "missing/root",
                "pattern": "CapabilityRegistry.kt",
            }
        )

        self.assertEqual("invalid", quality["path_validity"])
        self.assertEqual("SEARCH_ROOT_NOT_FOUND", quality["path_validation_error_code"])
        self.assertEqual(SearchQualitySeverity.BLOCK, quality["severity"])

    def test_list_directory_with_nonexistent_path_is_invalid(self):
        quality = classify_search_action_quality({"type": "list_directory", "path": "missing/root"})

        self.assertFalse(quality["is_search"])
        self.assertTrue(quality["is_filesystem_action"])
        self.assertEqual("invalid", quality["path_validity"])
        self.assertEqual("SEARCH_ROOT_NOT_FOUND", quality["path_validation_error_code"])
        self.assertEqual(SearchQualitySeverity.BLOCK, quality["severity"])

    def test_read_file_with_nonexistent_path_is_invalid(self):
        quality = classify_search_action_quality({"type": "read_file", "path": "missing/file.kt"})

        self.assertFalse(quality["is_search"])
        self.assertEqual("invalid", quality["path_validity"])
        self.assertEqual("INVALID_ACTION_PATH", quality["path_validation_error_code"])
        self.assertEqual("file", quality["expected_path_kind"])
        self.assertEqual(SearchQualitySeverity.BLOCK, quality["severity"])

    def test_read_chunk_with_nonexistent_path_is_invalid(self):
        quality = classify_search_action_quality({"type": "read_chunk", "path": "missing/file.kt"})

        self.assertEqual("invalid", quality["path_validity"])
        self.assertEqual("INVALID_ACTION_PATH", quality["path_validation_error_code"])
        self.assertEqual(SearchQualitySeverity.BLOCK, quality["severity"])

    def test_bounded_search_under_invalid_path_does_not_return_ok(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": "missing/root",
                "pattern": "Journal",
                "include_extensions": ["kt"],
                "code_only": True,
            }
        )

        self.assertEqual(SearchQualitySeverity.OK, quality["boundedness_severity"])
        self.assertNotEqual(SearchQualitySeverity.OK, quality["severity"])

    def test_valid_no_match_candidate_is_not_invalid_path(self):
        quality = classify_search_action_quality(
            {
                "type": "search_content",
                "path": ".",
                "pattern": "DefinitelyNoSuchSymbol",
                "include_extensions": ["py"],
                "code_only": True,
            }
        )

        self.assertEqual("known_valid", quality["path_validity"])
        self.assertIsNone(quality["path_validation_error_code"])
        self.assertEqual(SearchQualitySeverity.OK, quality["severity"])
