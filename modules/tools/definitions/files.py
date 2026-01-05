import os
from pathlib import Path
from ..base import BaseTool

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads the full content of a file. Use this before editing. Params: 'path' (str)"

    async def execute(self, path: str):
        try:
            p = Path(path)
            if not p.exists():
                return {"status": "error", "output": f"File not found: {path}"}
            content = p.read_text(encoding='utf-8')
            return {"status": "success", "output": content}
        except Exception as e:
            return {"status": "error", "output": str(e)}

class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Creates a NEW file with content. Fails if file exists. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        # Використовуємо твою логіку створення з перевіркою існування
        p = Path(path)
        if p.exists():
            return {"status": "error", "output": f"File {path} already exists. Use 'edit_file' or 'run_shell' to modify."}
        try:
            # Твоя логіка створення батьківських папок
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            return {"status": "success", "output": f"File created successfully: {path}"}
        except Exception as e:
            return {"status": "error", "output": f"Failed to create file: {str(e)}"}

class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Surgically edits an existing file by replacing a specific block of text. "
        "Params: 'path' (str), 'search_text' (str), 'replace_text' (str). "
        "The 'search_text' must exactly match a part of the file."
    )

    async def execute(self, path: str, search_text: str, replace_text: str):
        # Повна реалізація apply_edit з твого старого коду
        p = Path(path)
        if not p.exists():
            return {"status": "error", "output": f"File not found: {path}"}
        
        try:
            content = p.read_text(encoding='utf-8')
            
            # Твоя логіка пошуку та заміни одного входження
            if search_text in content:
                new_content = content.replace(search_text, replace_text, 1)
                p.write_text(new_content, encoding='utf-8')
                return {
                    "status": "success", 
                    "output": f"Successfully applied edit to {path}. Strategy: exact match replacement."
                }
            
            return {
                "status": "error", 
                "output": "Search block not found in the file. Ensure the 'search_text' matches exactly, including indentation."
            }
        except Exception as e:
            return {"status": "error", "output": f"Edit failed: {str(e)}"}
