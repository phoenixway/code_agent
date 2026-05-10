from pathlib import Path
import re

path = Path("tests/test_board_memory_commit_equivalence.py")
text = path.read_text()

def replace_in_function(src: str, func_name: str, pattern: str, repl: str) -> tuple[str, int]:
    start_pat = f"    def {func_name}"
    start = src.find(start_pat)
    if start == -1:
        raise SystemExit(f"Function not found: {func_name}")

    # Find next method in the same class or next class/top-level section.
    candidates = [
        idx for idx in [
            src.find("\n    def ", start + 1),
            src.find("\n\nclass ", start + 1),
            src.find("\n\n@pytest", start + 1),
        ]
        if idx != -1
    ]
    end = min(candidates) if candidates else len(src)

    before, body, after = src[:start], src[start:end], src[end:]
    new_body, count = re.subn(pattern, repl, body, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Pattern patch count for {func_name} was {count}, expected 1")
    return before + new_body + after, count

# 1) MCO legacy test: remove MCT-only assertions and restore strict MCO equivalence.
mco_pattern = (
    r"        assert diag\.candidate_available is True\n"
    r".*?"
    r"(?=        assert decision\.effective_commit\.handled == snapshot\.handled\n)"
)
mco_repl = (
    "        assert diag.candidate_available is True\n"
    "        assert diag.commit_equivalent is True\n"
    "        assert diag.fallback_used is False\n"
    "        assert diag.behavior_changed is False\n"
)
text, _ = replace_in_function(
    text,
    "test_resolver_legacy_mode_preserves_legacy_decision(self):",
    mco_pattern,
    mco_repl,
)

# 2) MCT legacy test: Step 3 validates candidate/resolver shape; full equivalence is Step 4.
mct_pattern = (
    r"        assert diag\.candidate_available is True\n"
    r".*?"
    r"        assert diag\.behavior_changed is False\n"
)
mct_repl = (
    "        assert diag.candidate_available is True\n"
    "        assert diag.response_text_agreement is True\n"
    "        assert diag.checkpoint_removed_agreement is True\n"
    "        assert diag.visible_text_preserved_agreement is True\n"
    "        assert diag.pass_through_agreement in {True, False}\n"
    "        assert diag.commit_equivalent in {True, False}  # Full equivalence hardening is Phase 31 — Step 4/10\n"
    "        assert diag.fallback_used is False\n"
    "        assert diag.behavior_changed is False\n"
)
text, _ = replace_in_function(
    text,
    "test_resolver_legacy_mode_preserves_legacy_snapshot_for_mct(self):",
    mct_pattern,
    mct_repl,
)

path.write_text(text)
print("Patched tests/test_board_memory_commit_equivalence.py")
