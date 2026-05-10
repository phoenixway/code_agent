from types import SimpleNamespace
import unittest

from modules.agent.orchestration.prompts import OrchestratorPromptBuilder
from modules.agent.orchestration.runtime.filesystem_path_failure import (
    INVALID_PATH_ERROR_CODE,
    INVALID_PATH_RECOVERY_KIND,
    classify_filesystem_path_failure,
)


class FilesystemPathFailureClassifierTests(unittest.TestCase):
    def test_fd_not_a_directory_is_classified(self):
        failure = classify_filesystem_path_failure(
            {"type": "search_files", "path": "app/src/main/java/com/romankozak/forward/"},
            {
                "status": "failed",
                "output": (
                    "Search path 'app/src/main/java/com/romankozak/forward/' is not a directory.\n"
                    "No valid search paths given."
                ),
            },
        )

        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(INVALID_PATH_ERROR_CODE, failure.error_code)
        self.assertEqual(INVALID_PATH_RECOVERY_KIND, failure.recovery_kind)
        self.assertEqual("search_files", failure.failed_action_type)
        self.assertEqual("directory", failure.expected_kind)
        self.assertEqual("app/src/main/java/com/romankozak/forward/", failure.invalid_path)

    def test_rg_no_such_file_is_classified(self):
        failure = classify_filesystem_path_failure(
            {"type": "search_content", "path": "app/src/main/java/com/mranrg/m", "pattern": "Forward"},
            {
                "status": "failed",
                "stderr": "rg: app/src/main/java/com/mranrg/m: No such file or directory",
            },
        )

        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual("missing", failure.actual_kind)
        self.assertEqual(".", failure.known_valid_roots[0])

    def test_no_match_search_is_not_invalid_path_recovery(self):
        failure = classify_filesystem_path_failure(
            {"type": "search_content", "path": ".", "pattern": "Forward"},
            {
                "status": "success",
                "output": "No matches found.",
            },
        )

        self.assertIsNone(failure)


class PromptBuilderInvalidPathRecoveryTests(unittest.TestCase):
    def _builder(self):
        agent = SimpleNamespace(
            state=SimpleNamespace(
                active_intent=SimpleNamespace(
                    intent_id="investigate_invalid_search",
                    intent_type="INVESTIGATE",
                    goal="Find the correct source root before reading files.",
                    allowed_actions=["list_directory", "search_files", "search_content", "read_file", "read_chunk"],
                ),
                last_action_fingerprint="",
                last_action_status="",
                last_failed_action_command=None,
                last_failed_action_result=None,
                operational_journal=[],
                memory_tag_expected_next_step=False,
                memory_tag_reason="",
                memory_tag_expected_intent_id="",
            ),
            config=SimpleNamespace(),
            memory_board_store=None,
            log=None,
        )
        return OrchestratorPromptBuilder(agent)

    def test_invalid_path_recovery_prompt_forbids_reuse_and_derivation(self):
        builder = self._builder()

        prompt = builder.build_current_intent_retry_recovery_query(
            ["list_directory", "search_files", "search_content"],
            error_code=INVALID_PATH_ERROR_CODE,
            error_details={
                "recovery_kind": INVALID_PATH_RECOVERY_KIND,
                "invalid_path": "missing/android/root",
                "failed_action_type": "search_files",
                "known_valid_roots": ["."],
                "recommended_next_actions": [
                    {"type": "list_directory", "path": "."},
                    {"type": "search_files", "path": "."},
                    {"type": "search_content", "path": "."},
                ],
                "message": "Search path 'missing/android/root' is not a directory.",
            },
            command={"type": "search_files", "path": "missing/android/root"},
        )

        self.assertIn("invalid: missing/android/root", prompt)
        self.assertIn("Do not reuse the failed path", prompt)
        self.assertIn("Do not derive sibling, child, or package paths", prompt)
        self.assertIn("Do not guess Android/Kotlin package roots", prompt)
        self.assertIn('"type":"list_directory","path":"."', prompt.replace(" ", ""))

    def test_invalid_path_recovery_uses_known_existing_parent_when_available(self):
        builder = self._builder()

        prompt = builder.build_current_intent_retry_recovery_query(
            ["list_directory", "search_files", "search_content"],
            error_code=INVALID_PATH_ERROR_CODE,
            error_details={
                "recovery_kind": INVALID_PATH_RECOVERY_KIND,
                "invalid_path": "modules/agent/missing_file.py",
                "failed_action_type": "read_file",
                "known_valid_roots": ["modules/agent"],
                "recommended_next_actions": [
                    {"type": "list_directory", "path": "modules/agent"},
                    {"type": "search_files", "path": "."},
                    {"type": "search_content", "path": "."},
                ],
                "message": "No such file or directory",
            },
            command={"type": "read_file", "path": "modules/agent/missing_file.py"},
        )

        self.assertIn('"type":"list_directory","path":"modules/agent"', prompt.replace(" ", ""))
