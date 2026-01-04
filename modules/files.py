# modules/files.py
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

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
    def create_file(self, file_path: str, content: str) -> EditResult:
        path = Path(file_path)
        if path.exists():
            return EditResult(False, f"File {file_path} already exists.")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            return EditResult(True, f"File created: {file_path}", "create")
        except Exception as e:
            return EditResult(False, str(e))

    def apply_edit(self, block: EditBlock) -> EditResult:
        path = Path(block.file_path)
        if not path.exists():
            return EditResult(False, f"File not found: {block.file_path}")
        
        content = path.read_text(encoding='utf-8')
        if block.search_text in content:
            new_content = content.replace(block.search_text, block.replace_text, 1)
            path.write_text(new_content, encoding='utf-8')
            return EditResult(True, f"Applied to {block.file_path}", "exact")
        
        return EditResult(False, "Search block not found.")

    def read_file(self, file_path: str) -> Optional[str]:
        path = Path(file_path)
        return path.read_text(encoding='utf-8') if path.exists() else None
