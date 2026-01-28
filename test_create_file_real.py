#!/usr/bin/env python3
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.tools.definitions.files import CreateFileTool
from modules.files import FileModule
from modules.types import ChangeProposal
from modules.processor import ResponseProcessor

# Створюємо екземпляр тулу
files_module = FileModule()
tool = CreateFileTool()
setattr(tool, 'files', files_module)

# Тестовий файл
test_file = "test_create_file_real_output.txt"
test_content = "Test content for create_file tool\nSecond line\nThird line"

print(f"Testing create_file tool with file: {test_file}")
print(f"Content:\n{test_content}")
print("-" * 50)

async def test_tool():
    # Викликаємо тул
    result = await tool.execute(
        path=test_file,
        content=test_content
    )
    
    print("1. Result from tool.execute():")
    print(f"   Type: {type(result)}")
    print(f"   Is ChangeProposal: {isinstance(result, ChangeProposal)}")
    
    if isinstance(result, ChangeProposal):
        print(f"   file_path: {result.file_path}")
        print(f"   original_content length: {len(result.original_content)}")
        print(f"   new_content length: {len(result.new_content)}")
        print(f"   diff:\n{result.diff}")
    
    print("\n2. Simulating ResponseProcessor logic:")
    
    # Симулюємо логіку ResponseProcessor
    if isinstance(result, ChangeProposal):
        print("   Result is ChangeProposal")
        print("   In real system, UI would show diff preview")
        print("   For test, we'll simulate user approving the changes")
        
        # Симулюємо підтвердження змін
        try:
            result.apply()
            print("   Changes applied successfully")
            processor_result = {
                "status": "success", 
                "output": f"Changes applied to {result.file_path}"
            }
        except Exception as e:
            print(f"   Failed to apply changes: {e}")
            processor_result = {
                "status": "error", 
                "output": f"Failed to apply changes: {e}"
            }
    else:
        print("   Result is not ChangeProposal")
        processor_result = result
    
    print("\n3. Result after ResponseProcessor:")
    print(f"   Type: {type(processor_result)}")
    if isinstance(processor_result, dict):
        print(f"   Keys: {list(processor_result.keys())}")
        print(f"   status: {processor_result.get('status')}")
        print(f"   output: {processor_result.get('output')}")
    
    print("\n4. What would be displayed in chat:")
    if isinstance(processor_result, dict):
        output_text = processor_result.get('output', '')
        print(f"   output_text: {repr(output_text)}")
        print(f"   Length: {len(output_text)}")
        if not output_text:
            print("   WARNING: Empty output! This would show empty line in chat.")
    
    # Очищаємо тестовий файл
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"\nTest file {test_file} removed")

# Запускаємо тест
asyncio.run(test_tool())