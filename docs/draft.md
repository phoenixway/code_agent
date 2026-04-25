Потрібно додати raw-block file writing tool/mode для великих файлів. і підключити в промпті, рекавері тексті, тд

## Problem

Current `write_file` / `create_file` expects large file content inside JSON string:
{
  "type": "write_file",
  "path": "generate_app.py",
  "content": "huge escaped content..."
}

For generated Kotlin/XML/Gradle/Python files this is fragile and often causes malformed_action.

## Required tool

Add:

<action>
{
  "type": "write_file_block",
  "path": "generate_app.py",
  "overwrite": true
}
</action>
<file_content>
raw content here
</file_content>

Behavior:
- action JSON contains only metadata;
- raw file content is read from <file_content>;
- preserve newlines and UTF-8;
- no JSON escaping needed for file body.

Also optionally:
<action>
{
  "type": "append_file_block",
  "path": "generate_app.py"
}
</action>
<file_content>
raw chunk
</file_content>

## Guard

If `write_file.content` or `create_file.content` length exceeds threshold, e.g. 4000 chars:
- block with `content_too_large_for_json_file_action`
- recovery says: use `write_file_block` with raw `<file_content>`.

## Tests

1. small write_file still works.
2. huge write_file JSON is blocked with clear reason.
3. write_file_block writes raw Kotlin/XML/Python content.
4. write_file_block without file_content rejected.
5. file_content without write_file_block rejected/ignored safely.
6. malformed huge file action recovery suggests write_file_block.
7. regression: generate_app.py can be written using write_file_block.

Final report: changed files, tests, git diff --stat.

