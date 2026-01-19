import os
from pathlib import Path
from ..base import BaseTool
from modules.types import ChangeProposal

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads the full content of a file. Use this before editing. Params: 'path' (str)"

    async def execute(self, path: str, ui=None):
        try:
            p = Path(path)
            if not p.exists():
                return {"status": "error", "output": f"File not found: {path}"}

            # Check file size
            file_size = p.stat().st_size
            if file_size > 1024 * 1024:  # 1MB
                if ui:
                    if not await ui.confirm_action({
                        "type": "read_large_file",
                        "path": path,
                        "size": f"{file_size / (1024 * 1024):.2f} MB"
                    }):
                        return {"status": "error", "output": "User denied reading large file."}
                    else:
                        # User confirmed reading the large file, so we should not truncate it.
                        content = p.read_text(encoding='utf-8')
                        return {"status": "success", "output": content, "skip_truncation": True}
                else:
                    # No UI, so we can't ask for confirmation.
                    # For now, we will proceed with reading the file.
                    # In the future, we might want to have a different behavior here.
                    pass

            content = p.read_text(encoding='utf-8')
            return {"status": "success", "output": content}
        except Exception as e:
            return {"status": "error", "output": str(e)}

class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Creates a NEW file with content. Fails if file exists. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        p = Path(path)
        if p.exists():
            return {"status": "error", "output": f"File {path} already exists. Use 'edit_file' or 'run_shell' to modify."}
        
        # Return proposal instead of writing directly
        proposal = ChangeProposal(
            file_path=path,
            original_content="",
            new_content=content
        )
        return proposal

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Overwrites an existing file. Params: 'path' (str), 'content' (str)"

    async def execute(self, path: str, content: str):
        p = Path(path)
        original = ""
        if p.exists():
            original = p.read_text(encoding='utf-8')
        
        # Return proposal
        proposal = ChangeProposal(
            file_path=path,
            original_content=original,
            new_content=content
        )
        return proposal

class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Surgically edits an existing file by replacing a specific block of text. "
        "Params: 'path' (str), 'search_text' (str), 'replace_text' (str). "
        "The 'search_text' must exactly match a part of the file."
    )

    async def execute(self, path: str, search_text: str, replace_text: str):
        p = Path(path)
        if not p.exists():
            return {"status": "error", "output": f"File not found: {path}"}
        
        try:
            content = p.read_text(encoding='utf-8')
            
            # Verify search text exists
            if search_text not in content:
                # If exact match fails, try relaxed matching (strip)
                if search_text.strip() in content:
                    # Adjust search_text to match content exactly
                    # This is tricky without knowing exact whitespace. 
                    # Let's stick to strict matching for safety, but improve error message.
                    pass
                
                return {
                    "status": "error", 
                    "output": "Search block not found. Ensure whitespace and indentation match exactly."
                }
            
            # Perform replacement
            new_content = content.replace(search_text, replace_text, 1)
            
            # Return proposal
            proposal = ChangeProposal(
                file_path=path,
                original_content=content,
                new_content=new_content
            )
            return proposal
            
        except Exception as e:
            return {"status": "error", "output": f"Edit failed: {str(e)}"}