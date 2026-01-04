import subprocess
import os
import re

class ResponseProcessor:
    def __init__(self, ui, files, chat, policy):
        """
        Initializes the processor with necessary modules.
        Args:
            ui: UI instance for console output.
            files: FileModule instance for file operations.
            chat: Chat provider instance.
            policy: PermissionPolicy instance for safety checks.
        """
        self.ui = ui
        self.files = files
        self.chat = chat
        self.policy = policy

    def process_single_action(self, action):
        """
        Routes the action to the appropriate handler based on its type.
        Returns: dict with 'status' and 'output'.
        """
        action_type = action.get("type")
        
        # Check permissions before sensitive operations
        if action_type in ["run_command", "write_file", "create_file"]:
            if not self.policy.check(action):
                return {"status": "cancelled", "output": "Action denied by user policy."}

        # Dispatcher logic
        handlers = {
            "run_command": self._handle_run_command,
            "read_file": self._handle_read_file,
            "write_file": self._handle_write_file,
            "create_file": self._handle_create_file,
            "edit_file": self._handle_edit_file
        }

        handler = handlers.get(action_type)
        if not handler:
            return {"status": "failed", "output": f"Unknown action type: {action_type}"}

        try:
            return handler(action)
        except Exception as e:
            return {"status": "failed", "output": f"Execution error: {str(e)}"}

    def _handle_run_command(self, action):
        """Executes shell commands and captures output."""
        cmd = action.get("command")
        if not cmd:
            return {"status": "failed", "output": "No command provided."}

        try:
            # Using shell=True to support pipes and environment variables in Termux/Fedora
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=300 # 5 minute safety timeout
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nError Output:\n{result.stderr}"
            
            status = "success" if result.returncode == 0 else "failed"
            return {"status": status, "output": output.strip() or "Command finished with no output."}
            
        except subprocess.TimeoutExpired:
            return {"status": "failed", "output": "Command timed out after 5 minutes."}

    def _handle_read_file(self, action):
        """Reads file content safely."""
        path = action.get("path") or action.get("file_path")
        content = self.files.read_file(path) # Assuming files.py handles exceptions
        if content is None:
            return {"status": "failed", "output": f"Could not read file: {path}"}
        return {"status": "success", "output": content}

    def _handle_create_file(self, action):
        """Creates a new file. Fails if file exists to prevent accidental overwrite."""
        path = action.get("path") or action.get("file_path")
        content = action.get("content", "")

        if os.path.exists(path):
            return {"status": "failed", "output": f"File already exists: {path}. Use edit_file instead."}

        self.files.write_file(path, content)
        return {"status": "success", "output": f"File {path} created successfully."}

    def _handle_write_file(self, action):
        """Standard file writing (overwrites content)."""
        path = action.get("path") or action.get("file_path")
        content = action.get("content", "")
        self.files.write_file(path, content)
        return {"status": "success", "output": f"File {path} written successfully."}

    def _handle_edit_file(self, action):
        """
        Implements search-and-replace editing.
        Expects 'edits' list with 'search' and 'replace' blocks.
        """
        path = action.get("path") or action.get("file_path")
        edits = action.get("edits", [])
        
        content = self.files.read_file(path)
        if content is None:
            return {"status": "failed", "output": f"File not found for editing: {path}"}

        original_content = content
        for edit in edits:
            search_text = edit.get("search")
            replace_text = edit.get("replace")
            
            if search_text not in content:
                return {
                    "status": "failed", 
                    "output": f"Search block not found in {path}. Ensure exact matching (spaces/newlines)."
                }
            
            content = content.replace(search_text, replace_text)

        if content == original_content:
            return {"status": "failed", "output": "No changes applied during edit_file operation."}

        self.files.write_file(path, content)
        return {"status": "success", "output": f"Successfully applied {len(edits)} edits to {path}."}