import json
from rich.markdown import Markdown as RichMarkdown
from rich.markup import escape

# Simulate the _render_tool_call_widget method
def test_render_tool_call_widget(command):
    tool_name = command.get("type") or command.get("action", "unknown")

    args = {
        k: v for k, v in command.items()
        if k not in {
            "type",
            "action",
            "before_execution",
            "during_execution",
            "after_execution",
            "return_control",
        }
    }

    md_lines = [""]  # Empty line before
    md_lines.append(f"**🔧 Tool Call: {tool_name}**")
    
    if args:
        for key, value in args.items():
            # Format value for display
            if isinstance(value, str):
                # Escape any markdown in the value
                display_value = escape(str(value))
            else:
                display_value = escape(json.dumps(value, ensure_ascii=False))
            # Make key bold and value normal for visual distinction
            # Add indentation for better readability
            md_lines.append(f'  **{key}** : {display_value}  ')
    
    md_lines.append("")  # Empty line after
    
    return "\n".join(md_lines)

# Test with a search_files command
command = {
    "type": "search_files",
    "pattern": "*.txt",
    "path": ".",
    "before_execution": "Searching for files...",
    "during_execution": "Searching...",
    "after_execution": "Search complete"
}

print("Test output:")
print("-" * 40)
result = test_render_tool_call_widget(command)
print(result)
print("-" * 40)
print("\nRaw lines:")
for i, line in enumerate(result.split('\n')):
    print(f"{i}: {repr(line)}")