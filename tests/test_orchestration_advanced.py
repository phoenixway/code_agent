import unittest
from agent import AngelicaAgent
import json

class TestOrchestrationAdvanced(unittest.TestCase):
    def setUp(self):
        # Minimal init
        self.agent = AngelicaAgent()
        # Suppress logging for clean test output
        self.agent.comm_log.disabled = True
        self.agent.log.disabled = True

    def test_parse_standard_command(self):
        """Standard case: Thoughts followed by a clean JSON command."""
        text = '<think>I should list files.</think>{"type": "run_shell", "command": "ls"}'
        segments = self.agent.parser.parse(text)
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].type, "thought")
        self.assertEqual(segments[0].content, "I should list files.")
        self.assertEqual(segments[1].type, "action")
        self.assertIsNotNone(segments[1].content)
        self.assertEqual(segments[1].content.get("command"), "ls")

    def test_parse_nested_json(self):
        """Parsing JSON with nested objects (braces inside braces)."""
        text = '{"type": "write_file", "content": "if (a) { return b; }"}'
        segments = self.agent.parser.parse(text)
        
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "action")
        self.assertIsNotNone(segments[0].content)
        self.assertEqual(segments[0].content.get("content"), "if (a) { return b; }")

    def test_parse_multiple_jsons(self):
        """The model might output two JSONs. The parser should create two action segments."""
        text = '<think>First step</think>{"type": "cmd1"}<think>Then</think>{"type": "cmd2"}'
        segments = self.agent.parser.parse(text)
        
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0].type, "thought")
        self.assertEqual(segments[1].type, "action")
        self.assertEqual(segments[1].content.get("type"), "cmd1")
        self.assertEqual(segments[2].type, "thought")
        self.assertEqual(segments[3].type, "action")
        self.assertEqual(segments[3].content.get("type"), "cmd2")

    def test_parse_json_surrounded_by_text(self):
        """JSON embedded in heavy text."""
        text = """
        I will run the command now.
        {"type": "run_shell", "command": "echo 'hello'"}
        This command will print hello.
        """
        segments = self.agent.parser.parse(text)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("I will run the command now.", segments[0].content)
        self.assertEqual(segments[1].type, "action")
        self.assertEqual(segments[1].content.get("command"), "echo 'hello'")
        self.assertEqual(segments[2].type, "text")
        self.assertIn("This command will print hello.", segments[2].content)

    def test_parse_malformed_json(self):
        """Should treat malformed JSON as text."""
        text = '{"type": "run_shell", "command": "oops" # Missing quote and brace'
        segments = self.agent.parser.parse(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        self.assertIn('{"type":', segments[0].content)

if __name__ == "__main__":
    unittest.main()