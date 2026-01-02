import unittest
import os
import shutil
from modules.storage import Storage
from modules.files import FileModule
from modules.chat import ChatModule

class TestAgentModules(unittest.TestCase):
    
    def setUp(self):
        # Створюємо тимчасову папку для тестів storage
        self.test_dir = "test_sessions"
        self.storage = Storage(session_dir=self.test_dir)
        self.files = FileModule()
        self.chat = ChatModule()

    def tearDown(self):
        # Видаляємо тимчасові файли після тестів
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists("test_file.txt"):
            os.remove("test_file.txt")

    def test_storage_save(self):
        """Перевірка збереження історії"""
        self.storage.save_message("user", "Hello Test")
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, self.storage.current_session)))

    def test_chat_mock(self):
        """Перевірка заглушки чату"""
        response = self.chat.get_response("test")
        self.assertIn("AI відповідає на: test", response)

    def test_file_write_and_diff(self):
        """Перевірка роботи з файлами та diff"""
        filename = "test_file.txt"
        content = "Line 1"
        self.files.write_file(filename, content)
        
        with open(filename, "r") as f:
            self.assertEqual(f.read(), content)
            
        # Тест diff (повинен повернути True, бо є різниця)
        has_diff = self.files.show_diff(filename, content, "Line 2")
        self.assertTrue(has_diff)

if __name__ == "__main__":
    unittest.main()