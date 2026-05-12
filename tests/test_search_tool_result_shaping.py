import unittest

from modules.tools.definitions.search import _compact_large_result


class TestSearchToolResultShaping(unittest.TestCase):
    def test_broad_search_content_returns_histogram_summary(self):
        """
        Tests that a broad search_content result is shaped into a histogram summary.
        """
        # 3 matches in b.kt, 2 in a.kt, 1 in c.kt
        # Order should be b.kt, a.kt, c.kt
        search_output_text = "\n".join([
            "a.kt:10: line with match",
            "b.kt:5: another match",
            "c.kt:120: third file match",
            "a.kt:25: second match in a.kt",
            "b.kt:15: another match in b",
            "b.kt:25: third match in b",
        ])

        result = _compact_large_result("matches", search_output_text, limit=100, exit_code=0)

        self.assertTrue(result["search_too_broad"])
        self.assertEqual(result["result_kind"], "broad_search_summary")

        output = result["output"]
        self.assertIn("Search was broad: 6 matches across 3 files.", output)
        self.assertIn("Top files by match count:", output)
        self.assertIn("Hint: This result is broad. Useful narrowing options include requesting a file skeleton, reading a chunk of one listed file", output)
        self.assertNotIn("Next step", output)

        # Check order of files
        expected_order_lines = [
            "- b.kt — 3 matches",
            "- a.kt — 2 matches",
            "- c.kt — 1 match",
        ]
        
        # Check that all expected lines are present
        for line in expected_order_lines:
            self.assertIn(line, output)

        # Verify the exact order in the output string
        b_pos = output.find("b.kt")
        a_pos = output.find("a.kt")
        c_pos = output.find("c.kt")
        self.assertTrue(0 < b_pos < a_pos < c_pos, "Files are not in the correct order")

    def test_histogram_summary_sorts_by_count_then_path_alphabetically(self):
        """
        Tests that files with the same match count are sorted alphabetically by path.
        """
        # 2 matches in z.kt, 2 in a.kt. Order should be a.kt, z.kt
        search_output_text = "\n".join([
            "z.kt:1: match",
            "a.kt:1: match",
            "z.kt:2: match",
            "a.kt:2: match",
        ])

        result = _compact_large_result("matches", search_output_text, limit=100, exit_code=0)
        output = result["output"]

        self.assertIn("Search was broad: 4 matches across 2 files.", output)
        
        # Check order of files
        a_pos = output.find("a.kt — 2 matches")
        z_pos = output.find("z.kt — 2 matches")
        self.assertTrue(0 < a_pos < z_pos, "a.kt should appear before z.kt for alphabetical tie-breaking")

    def test_broad_search_files_retains_old_preview_format(self):
        """
        Tests that broad search_files results still use the old preview format, not the histogram.
        """
        search_output_text = "\n".join([f"file_{i}.txt" for i in range(20)])
        
        result = _compact_large_result("files", search_output_text, limit=15, exit_code=0)

        self.assertTrue(result["search_too_broad"])
        self.assertNotIn("result_kind", result) # The old format doesn't have this key

        output = result["output"]
        self.assertIn("Search query is too broad", output)
        self.assertIn("Found 20 files; showing only the first 10.", output)
        self.assertNotIn("Top files by match count:", output)
        self.assertNotIn("Hint:", output)
        
        # Check that it contains the preview
        self.assertIn("file_0.txt", output)
        self.assertIn("file_9.txt", output)
        self.assertNotIn("file_10.txt", output)

    def test_histogram_summary_handles_more_than_10_files(self):
        """
        Tests that the summary correctly reports "...and X more files" when there are more than 10 files.
        """
        lines = []
        for i in range(12):
            lines.append(f"file_{i:02d}.txt:1: match")
        
        search_output_text = "\n".join(lines)
        result = _compact_large_result("matches", search_output_text, limit=100, exit_code=0)
        output = result["output"]

        self.assertIn("Search was broad: 12 matches across 12 files.", output)
        self.assertIn("...and 2 more files.", output)
        self.assertIn("file_09.txt", output)
        self.assertNotIn("file_10.txt", output)
        self.assertNotIn("file_11.txt", output)
