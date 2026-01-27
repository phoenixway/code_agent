import json
from rich.markup import escape

# Simulate the current _render_tool_call_widget method
tool_name = 'search_files'
args = {'pattern': '*.txt', 'path': '.'}

md_lines = []
# Add two spaces at the end of each line for Markdown line breaks
md_lines.append(f'**Tool Call: {tool_name}**  ')

if args:
    for i, (key, value) in enumerate(args.items()):
        display_value = escape(str(value))
        # Add two spaces at the end for Markdown line break (except for last line)
        if i < len(args) - 1:
            md_lines.append(f'**{key}** : {display_value}  ')
        else:
            md_lines.append(f'**{key}** : {display_value}')

result = '\n'.join(md_lines)

print('Test output:')
print('-' * 40)
print(result)
print('-' * 40)
print('\nRaw lines:')
for i, line in enumerate(result.split('\n')):
    print(f'{i}: {repr(line)}')

print('\nExpected format:')
print('**Tool Call: search_files**')
print('**pattern** : *.txt')
print('**path** : .')