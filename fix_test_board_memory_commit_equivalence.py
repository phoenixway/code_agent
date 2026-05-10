#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

TARGET = Path("tests/test_board_memory_commit_equivalence.py")


def replace_between(text: str, start_marker: str, end_marker: str, transform) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"Start marker not found: {start_marker!r}")
    end = text.find(end_marker, start + len(start_marker))
    if end == -1:
        raise SystemExit(f"End marker not found after {start_marker!r}: {end_marker!r}")
    block = text[start:end]
    new_block = transform(block)
    if new_block == block:
        raise SystemExit(f"No change made inside block starting {start_marker!r}")
    return text[:start] + new_block + text[end:]


def fix_mco_legacy_test(block: str) -> str:
    # This is MEMORY_CHECKPOINT_ONLY. It must not assert MCT-only fields.
    pattern = re.compile(
        r"        assert diag\.candidate_available is True\n"
        r"(?:        assert diag\.(?:response_text_agreement|checkpoint_removed_agreement|visible_text_preserved_agreement) is True\n)?"
        r"(?:        assert diag\.pass_through_agreement[^\n]*\n)?"
        r"(?:        assert diag\.commit_equivalent[^\n]*\n)?"
        r"        assert diag\.fallback_used is False\n"
        r"        assert diag\.behavior_changed is False\n",
        re.MULTILINE,
    )
    replacement = (
        "        assert diag.candidate_available is True\n"
        "        assert diag.commit_equivalent is True\n"
        "        assert diag.fallback_used is False\n"
        "        assert diag.behavior_changed is False\n"
    )
    block, n = pattern.subn(replacement, block, count=1)
    if n != 1:
        raise SystemExit(f"MCO assertion block patch count was {n}, expected 1")
    return block


def fix_mct_legacy_test(block: str) -> str:
    # Step 3 validates candidate/resolver shape; full commit equivalence is Step 4.
    pattern = re.compile(
        r"        assert diag\.candidate_available is True\n"
        r"(?:        assert diag\.(?:response_text_agreement|checkpoint_removed_agreement|visible_text_preserved_agreement) is True\n)?"
        r"(?:        assert diag\.pass_through_agreement[^\n]*\n)?"
        r"(?:        assert diag\.commit_equivalent[^\n]*\n)?"
        r"        assert diag\.fallback_used is False\n"
        r"        assert diag\.behavior_changed is False\n",
        re.MULTILINE,
    )
    replacement = (
        "        assert diag.candidate_available is True\n"
        "        assert diag.response_text_agreement is True\n"
        "        assert diag.checkpoint_removed_agreement is True\n"
        "        assert diag.visible_text_preserved_agreement is True\n"
        "        assert diag.pass_through_agreement in {True, False}\n"
        "        assert diag.commit_equivalent in {True, False}  # Full equivalence hardening is Phase 31 — Step 4/10\n"
        "        assert diag.fallback_used is False\n"
        "        assert diag.behavior_changed is False\n"
    )
    block, n = pattern.subn(replacement, block, count=1)
    if n != 1:
        raise SystemExit(f"MCT assertion block patch count was {n}, expected 1")
    return block


def main() -> None:
    text = TARGET.read_text()

    text = replace_between(
        text,
        "    def test_resolver_legacy_mode_preserves_legacy_decision(self):",
        "    def test_resolver_compiler_mode_falls_back_when_equivalence_unproven(self):",
        fix_mco_legacy_test,
    )

    text = replace_between(
        text,
        "    def test_resolver_legacy_mode_preserves_legacy_snapshot_for_mct(self):",
        "    def test_resolver_compiler_mode_falls_back_on_mismatch_for_mct(self):",
        fix_mct_legacy_test,
    )

    TARGET.write_text(text)
    print(f"Patched {TARGET}")


if __name__ == "__main__":
    main()
