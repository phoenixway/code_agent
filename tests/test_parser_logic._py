import unittest
from modules.parser import ResponseParser, Segment

class TestResponseParser(unittest.TestCase):
    def setUp(self):
        self.parser = ResponseParser()

    def test_basic_thought_and_action(self):
        text = '<think>I should list files.</think><action>{"type": "run_shell", "command": "ls"}</action>'
        segments = self.parser.parse(text)
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].type, 'thought')
        self.assertEqual(segments[0].content, "I should list files.")
        self.assertEqual(segments[1].type, 'action')
        self.assertEqual(segments[1].content['command'], "ls")

    def test_text_action_text(self):
        text = 'I will run ls. <action>{"type": "run_shell", "command": "ls"}</action> Done.'
        segments = self.parser.parse(text)
        
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].type, 'text')
        self.assertEqual(segments[0].content, "I will run ls.")
        self.assertEqual(segments[1].type, 'action')
        self.assertEqual(segments[2].type, 'text')
        self.assertEqual(segments[2].content, "Done.")

    def test_multiple_actions(self):
        text = 'Step 1 <action>{"type": "cmd1"}</action> Step 2 <action>{"type": "cmd2"}</action>'
        segments = self.parser.parse(text)
        
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[1].type, 'action')
        self.assertEqual(segments[1].content['type'], "cmd1")
        self.assertEqual(segments[3].type, 'action')
        self.assertEqual(segments[3].content['type'], "cmd2")

    def test_single_action_object(self):
        text = '<action>{"type": "read_file", "path": "a.txt"}</action>'
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "action")
        self.assertEqual(segments[0].content["type"], "read_file")
        self.assertEqual(segments[0].content["path"], "a.txt")

    def test_multiple_separate_action_tags(self):
        text = (
            '<action>{"type": "list_directory", "path": "a"}</action>\n'
            '<action>{"type": "list_directory", "path": "b"}</action>'
        )
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 2)
        self.assertTrue(all(segment.type == "action" for segment in segments))
        self.assertEqual([segment.content["path"] for segment in segments], ["a", "b"])

    def test_single_action_with_array_of_valid_objects(self):
        text = """<action>
[
  {"type": "list_directory", "path": "a"},
  {"type": "list_directory", "path": "b"}
]
</action>"""
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 2)
        self.assertTrue(all(segment.type == "action" for segment in segments))
        self.assertEqual([segment.content["path"] for segment in segments], ["a", "b"])

    def test_single_action_with_array_where_some_objects_invalid(self):
        text = """<action>
[
  {"type": "list_directory", "path": "a"},
  {"path": "missing-type"},
  42,
  {"command": "list_directory", "path": "b"}
]
</action>"""
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 2)
        self.assertTrue(all(segment.type == "action" for segment in segments))
        self.assertEqual(segments[0].content["path"], "a")
        self.assertEqual(segments[1].content["path"], "b")

    def test_single_action_with_array_and_type_in_tag_attribute(self):
        text = """<action type="list_directory">
[
  {"path": "a"},
  {"path": "b"}
]
</action>"""
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 2)
        self.assertTrue(all(segment.type == "action" for segment in segments))
        self.assertEqual([segment.content["type"] for segment in segments], ["list_directory", "list_directory"])
        self.assertEqual([segment.content["path"] for segment in segments], ["a", "b"])

    def test_single_action_with_malformed_json_array(self):
        text = """<action>
[
  {"type": "list_directory", "path": "a",
  {"type": "list_directory", "path": "b"}
]
</action>"""
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("<action>", segments[0].content)

    def test_single_action_with_scalar_json_payload_is_text(self):
        text = '<action>"read_file"</action>'
        segments = self.parser.parse(text)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        self.assertIn('<action>"read_file"</action>', segments[0].content)

    def test_json_inside_thought_ignored(self):
        text = '<think>I am thinking about <action>{"type": "bad"}</action></think> <action>{"type": "good"}</action>'
        segments = self.parser.parse(text)
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].type, 'thought')
        self.assertIn('<action>{"type": "bad"}</action>', segments[0].content) # JSON remains as string in thought
        self.assertEqual(segments[1].type, 'action')
        self.assertEqual(segments[1].content['type'], "good")

    def test_fallback_malformed_tags(self):
        """Test the greedy fallback for mismatched tags."""
        text = 'I am thinking... </think> Real content <action>{"type": "act"}</action>'
        segments = self.parser.parse(text)
        
        # Expectation: Thought, then mixed content (Text, Action)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].type, 'thought')
        self.assertEqual(segments[0].content, "I am thinking...")
        self.assertEqual(segments[1].type, 'text')
        self.assertIn("Real content", segments[1].content)
        self.assertEqual(segments[2].type, 'action')
        self.assertEqual(segments[2].content['type'], "act")
        
    def test_fallback_complex(self):
        text = 'Think 1 </think> Think 2 </think> <action>{"type": "act"}</action>'
        segments = self.parser.parse(text)
        
        self.assertEqual(segments[0].type, 'thought')
        # Should catch everything up to last </think>
        self.assertIn("Think 2", segments[0].content)
        
        # The rest is action
        # The parser splits remaining text mixed content
        # segments[0] is thought. segments[1] might be empty text if stripped, then segments[2] action
        # Let's check the last segment is action
        self.assertEqual(segments[-1].type, 'action')
        self.assertEqual(segments[-1].content['type'], "act")

    def test_mixed_sequence(self):
        text = 'Start <think>Thinking</think> Middle <action>{"type": "a"}</action> End'
        segments = self.parser.parse(text)
        self.assertEqual(segments[0].type, 'text') # Start
        self.assertEqual(segments[1].type, 'thought') # Thinking
        self.assertEqual(segments[2].type, 'text') # Middle
        self.assertEqual(segments[3].type, 'action') # a
        self.assertEqual(segments[4].type, 'text') # End

    def test_non_command_json(self):
        """JSON that is valid but not a command should be treated as text."""
        text = 'Here is data: <action>{"key": "value"}</action>'
        segments = self.parser.parse(text)
        # Should be text -> text (json) or just text
        # Parser implementation: text "Here is data:", then text '<action>{"key": "value"}</action>'
        self.assertTrue(all(s.type == 'text' for s in segments))

    def test_cdata_json_payload_keeps_structured_fields(self):
        text = (
            '<action type="read_file_skeleton"><![CDATA[{'
            '"path":"go_examples/00_basic_types.go","before_execution":"x"'
            '}]]></action>'
        )
        segments = self.parser.parse(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "action")
        self.assertEqual(segments[0].content["type"], "read_file_skeleton")
        self.assertEqual(segments[0].content["path"], "go_examples/00_basic_types.go")
        self.assertNotIn("command", segments[0].content)

    def test_value_name_tags_are_parsed_as_action_fields(self):
        text = (
            '<action type="read_file">'
            '<value name="path">go_examples/00_operations.go</value>'
            '<value name="before_execution">b</value>'
            '<value name="during_execution">d</value>'
            '<value name="after_execution">a</value>'
            "</action>"
        )
        segments = self.parser.parse(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "action")
        self.assertEqual(segments[0].content["type"], "read_file")
        self.assertEqual(segments[0].content["path"], "go_examples/00_operations.go")
        self.assertEqual(segments[0].content["before_execution"], "b")

    def test_action_attributes_include_path_when_payload_uses_xml_tags(self):
        text = (
            '<action type="read_file" path="go_examples/05_control_flow.go">'
            "<before_execution>b</before_execution>"
            "<during_execution>d</during_execution>"
            "<after_execution>a</after_execution>"
            "</action>"
        )
        segments = self.parser.parse(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "action")
        self.assertEqual(segments[0].content["type"], "read_file")
        self.assertEqual(segments[0].content["path"], "go_examples/05_control_flow.go")

if __name__ == "__main__":
    unittest.main()
