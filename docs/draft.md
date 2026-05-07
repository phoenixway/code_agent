Task:
Fix typed recovery prompt crash when typed_recovery_header helper returns None for next_hint.

Context:
Runtime dump shows Critical error after dispatch_recovery reason=low_value_broad_search_repeat.

Traceback:
  modules/agent/orchestration/runtime/recovery.py:597 handle_dispatch_stop
  modules/agent/orchestration/prompts/recovery_prompt_builder.py:579 build_orchestrated_recovery_prompt
  modules/agent/orchestration/prompts/recovery_prompt_builder.py:224 build_typed_stop_recovery_prompt
  modules/agent/orchestration/prompts/action_format_prompt_builder.py:670 typed_recovery_header
    return headers[reason] + next_hint
TypeError:
  can only concatenate str (not "NoneType") to str

Goal:
Make recovery prompt building defensive.
Do not change dispatch recovery behavior.
Do not change low_value_broad_search_repeat detection.
Do not change compiler/protocol code.

Tasks:
1. Open:
   modules/agent/orchestration/prompts/action_format_prompt_builder.py
   modules/agent/orchestration/prompts/recovery_prompt_builder.py
   tests/agent/orchestration/prompts/test_recovery_prompt_builder.py

2. In typed_recovery_header, find:
   return headers[reason] + next_hint

3. Make it safe against None:
   - coerce header to str
   - coerce next_hint to str
   - use a safe fallback if headers.get(reason) is missing

Example:
   header = str(headers.get(reason, headers.get("default", "")) or "")
   next_hint = str(next_hint or "")
   return header + next_hint

Use the existing style in the file.

4. Add/adjust regression tests:
   - low_value_broad_search_repeat builds a string prompt and does not crash
   - typed_recovery_header handles next_hint None
   - build_typed_stop_recovery_prompt handles typed_recovery_header returning None
   - assertions should be semantic, not exact brittle wording:
       assert isinstance(prompt, str)
       assert "read-only" in prompt.lower()
       assert "search_content" in prompt

5. Do not assert exact phrase:
   "Return EXACTLY ONE materially different read-only action"
because current prompt wording may use:
   "prefer exactly one"

6. Run:
   python -m py_compile modules/agent/orchestration/prompts/action_format_prompt_builder.py \
                        modules/agent/orchestration/prompts/recovery_prompt_builder.py

   pytest tests/agent/orchestration/prompts/test_recovery_prompt_builder.py
   pytest tests -k "recovery_prompt or typed_stop or low_value_broad_search_repeat"

   pytest -q tests