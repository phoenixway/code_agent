import os
import re
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class EditBlock:
    file_path: str
    search_text: str
    replace_text: str

@dataclass
class EditResult:
    success: bool
    message: str
    strategy: str = "none"

class FileModule:
    def write_file(self, file_path: str, content: str) -> bool:
        """Повний перезапис або створення нового файлу."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            return True
        except Exception as e:
            return str(e)

    def read_file(self, file_path: str) -> Optional[str]:
        """Зчитування вмісту."""
        path = Path(file_path)
        return path.read_text(encoding='utf-8') if path.exists() else None

    def apply_edit(self, block: EditBlock) -> EditResult:
        """Інтелектуальне редагування: Exact Match -> Normalized Match."""
        try:
            path = Path(block.file_path)
            if not path.exists():
                return EditResult(False, f"File not found: {block.file_path}")

            content = path.read_text(encoding='utf-8')
            
            # 1. Exact Match
            if block.search_text in content:
                new_content = content.replace(block.search_text, block.replace_text, 1)
                return self._finalize_edit(path, new_content, "exact")

            # 2. Normalized Match (ignore trailing whitespace/newlines)
            normalized_content = self._try_normalized_replace(content, block)
            if normalized_content:
                return self._finalize_edit(path, normalized_content, "normalized")

            return EditResult(False, "SEARCH block not found. Check indentation/context.")
        except Exception as e:
            return EditResult(False, f"Runtime error: {str(e)}")

    def apply_unified_diff(self, diff_content: str) -> EditResult:
        """Застосування стандартного Unified Diff через системний 'patch'."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as tmp:
                tmp.write(diff_content)
                tmp_path = tmp.name

            # --fuzz 2 дозволяє патчити навіть якщо номери рядків трохи збилися
            process = subprocess.run(
                ['patch', '-p1', '--fuzz', '2', '-i', tmp_path],
                capture_output=True, text=True
            )
            os.unlink(tmp_path)

            if process.returncode == 0:
                return EditResult(True, "Unified Diff applied.", "diff")
            return EditResult(False, f"Patch error: {process.stderr}")
        except Exception as e:
            return EditResult(False, f"Diff execution error: {str(e)}")

    def _try_normalized_replace(self, content: str, block: EditBlock) -> Optional[str]:
        """Гнучка заміна з ігноруванням розбіжностей у пробілах."""
        escaped_search = re.escape(block.search_text.strip())
        flexible_pattern = escaped_search.replace(r'\ ', r'\s+')
        match = re.search(flexible_pattern, content, re.DOTALL)
        if match:
            return content[:match.start()] + block.replace_text + content[match.end():]
        return None

    def _finalize_edit(self, path: Path, new_content: str, strategy: str) -> EditResult:
        path.write_text(new_content, encoding='utf-8')
        return EditResult(True, f"Success ({strategy})", strategy)