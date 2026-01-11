from dataclasses import dataclass
from pathlib import Path
import difflib

@dataclass
class ChangeProposal:
    """Class representing a proposed file change before it is applied."""
    file_path: str
    original_content: str
    new_content: str
    
    @property
    def diff(self) -> str:
        """Generates a unified diff string."""
        # Handle new file case
        from_file = f"a/{self.file_path}" if self.original_content else "/dev/null"
        to_file = f"b/{self.file_path}"
        
        from_lines = self.original_content.splitlines(keepends=True) if self.original_content else []
        to_lines = self.new_content.splitlines(keepends=True)
        
        diff_lines = list(difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=from_file,
            tofile=to_file,
            n=3 # context lines
        ))
        
        return "".join(diff_lines) if diff_lines else "No changes detected."

    def apply(self):
        """Applies the changes to the actual file system."""
        p = Path(self.file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.new_content, encoding='utf-8')
