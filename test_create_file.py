#!/usr/bin/env python3
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.tools.definitions.files import CreateFileTool
from modules.files import FileModule
from modules.types import ChangeProposal

# Створюємо екземпляр тулу
files_module = FileModule()

# Створюємо тул з потрібними залежностями
# Перевіримо, як створюється тул у реальному коді
tool = CreateFileTool()
# Передаємо залежності через атрибути
setattr(tool, 'files', files_module)

# Тестуємо створення файлу
test_file = "test_create_file_output.txt"
test_content = "Test content for create_file tool"

print(f"Testing create_file tool with file: {test_file}")
print(f"Content: {test_content}")
print("-" * 50)

async def test_tool():
    # Викликаємо тул
    result = await tool.execute(
        path=test_file,
        content=test_content
    )
    
    print("Result from tool.execute():")
    print(f"Type: {type(result)}")
    print(f"Full result: {result}")
    print()
    
    # Перевіряємо, чи є це ChangeProposal
    if isinstance(result, ChangeProposal):
        print("Result is a ChangeProposal object:")
        print(f"  file_path: {result.file_path}")
        print(f"  original_content: {repr(result.original_content)}")
        print(f"  new_content: {repr(result.new_content)}")
        print(f"  success: {result.success}")
        print(f"  message: {result.message}")
        
        # Перевіримо, як це обробляється в agent.py
        # В agent.py використовується result.get('output', '')
        print("\n" + "=" * 50)
        print("Checking what should be displayed in chat:")
        
        # Спробуємо перетворити ChangeProposal в dict
        if hasattr(result, '__dict__'):
            result_dict = result.__dict__
            print(f"Result as dict: {result_dict}")
            output_text = result_dict.get('output', '')
            print(f"result_dict.get('output', ''): {repr(output_text)}")
        
        # Перевіримо, як обробляються ChangeProposal в системі
        # Можливо, що він конвертується в dict з ключами status та output
        print("\nTrying to convert ChangeProposal to expected format:")
        # Спроба конвертації
        if hasattr(result, 'success') and hasattr(result, 'message'):
            converted_result = {
                'status': 'success' if result.success else 'error',
                'output': result.message if result.message else 'File created successfully'
            }
            print(f"Converted result: {converted_result}")
            print(f"output for display: {converted_result.get('output', '')}")
    
    elif isinstance(result, dict):
        print("Result is a dict:")
        for key, value in result.items():
            print(f"  {key}: {value} (type: {type(value)})")
        
        print("\n" + "=" * 50)
        print("Checking what should be displayed in chat:")
        output_text_for_print = result.get('output', '')
        print(f"result.get('output', ''): {repr(output_text_for_print)}")
        print(f"Length of output: {len(output_text_for_print)}")
    else:
        print(f"Result is not a dict or ChangeProposal, it's: {type(result)}")
    
    # Очищаємо тестовий файл
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"\nTest file {test_file} removed")

# Запускаємо тест
asyncio.run(test_tool())