import unittest
from agent import AngelicaAgent
import json

class TestOrchestrationAdvanced(unittest.TestCase):
    def setUp(self):
        # Minimal init
        self.agent = AngelicaAgent()
        # Suppress logging for clean test output
        self.agent.comm_log.disabled = True

    def test_parse_standard_command(self):
        """Standard case: Thoughts followed by a clean JSON command."""
        text = '<think>I should list files.</think>\n```json\n{"type": "run_shell", "command": "ls"}\n```'
        thoughts, command, plain = self.agent._parse_output(text)
        
        self.assertEqual(thoughts, ["I should list files."])
        self.assertIsNotNone(command)
        self.assertEqual(command.get("command"), "ls")

    def test_parse_nested_json(self):
        """Parsing JSON with nested objects (braces inside braces)."""
        text = '{"type": "write_file", "content": "if (a) { return b; }"}'
        thoughts, command, plain = self.agent._parse_output(text)
        
        self.assertIsNotNone(command)
        self.assertEqual(command.get("content"), "if (a) { return b; }")

    def test_parse_multiple_jsons(self):
        """
        The model might output two JSONs. 
        The parser should ideally pick the first valid one or handle it gracefully.
        Current Greedy Regex behavior: Fails or picks both as one string.
        Desired behavior: Pick first valid command.
        """
        text = 'First step: {"type": "cmd1"} and then {"type": "cmd2"}'
        thoughts, command, plain = self.agent._parse_output(text)
        
        self.assertIsNotNone(command)
        self.assertEqual(command.get("type"), "cmd1")

    def test_parse_json_surrounded_by_text(self):
        """JSON embedded in heavy text."""
        text = """
        I will run the command now.
        {
            "type": "run_shell",
            "command": "echo 'hello'"
        }
        This command will print hello.
        """
        thoughts, command, plain = self.agent._parse_output(text)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("command"), "echo 'hello'")

    def test_parse_malformed_json(self):
        """Should return None for command if JSON is broken."""
        text = '{"type": "run_shell", "command": "oops" # Missing quote and brace'
        thoughts, command, plain = self.agent._parse_output(text)
        self.assertIsNone(command)
        self.assertIn('{"type":', plain)

if __name__ == "__main__":
    unittest.main()