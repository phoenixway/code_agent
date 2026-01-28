#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.types import ChangeProposal

# Створюємо тестовий ChangeProposal
proposal = ChangeProposal(
    file_path="test_file.txt",
    original_content="",
    new_content="New content\nSecond line\nThird line"
)

print("Testing ChangeProposal:")
print(f"file_path: {proposal.file_path}")
print(f"original_content: {repr(proposal.original_content)}")
print(f"new_content: {repr(proposal.new_content)}")
print(f"diff:\n{proposal.diff}")
print()

print("Testing apply() method:")
try:
    # Спробуємо застосувати зміни
    proposal.apply()
    print("Changes applied successfully")
    
    # Перевіримо, чи файл створено
    if os.path.exists("test_file.txt"):
        with open("test_file.txt", "r", encoding="utf-8") as f:
            content = f.read()
        print(f"File content: {repr(content)}")
        
        # Очистимо файл
        os.remove("test_file.txt")
        print("Test file removed")
    else:
        print("ERROR: File was not created!")
except Exception as e:
    print(f"ERROR applying changes: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("Checking what agent.py expects:")
print("1. agent.py calls result.get('output', '')")
print("2. For ChangeProposal, there is no 'output' key")
print("3. So result.get('output', '') returns empty string")
print("4. This causes empty line in chat")
print()
print("Solution: ChangeProposal should be converted to dict")
print("with 'output' key before returning to agent.py")