# modules/context.py
import os
from pathlib import Path

class ContextManager:
    def __init__(self, files_module):
        self.files = files_module
        self.basket = {}
        # Стандартні ігнори, якщо .gitignore відсутній
        self.default_ignore = {'.git', '__pycache__', 'node_modules', 'venv', '.idea', 'build'}

    def _get_ignore_list(self, root_dir):
        """Зчитує .gitignore та повертає набір правил."""
        ignore_path = Path(root_dir) / ".gitignore"
        ignore_list = self.default_ignore.copy()
        if ignore_path.exists():
            try:
                with open(ignore_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Прибираємо слеші для простого порівняння
                            ignore_list.add(line.replace('/', ''))
            except:
                pass
        return ignore_list

    def get_project_structure(self, root_dir=".", max_depth=3):
        """Будує текстове дерево проекту з урахуванням ігнорів."""
        ignore_list = self._get_ignore_list(root_dir)
        output = ["Project Structure:"]
        
        def _build_tree(current_dir, depth, prefix=""):
            if depth > max_depth:
                return
            
            try:
                # Сортуємо: спочатку папки, потім файли
                items = sorted(Path(current_dir).iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except PermissionError:
                return

            for i, item in enumerate(items):
                if item.name in ignore_list:
                    continue
                
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                output.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
                
                if item.is_dir():
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    _build_tree(item, depth + 1, new_prefix)

        _build_tree(root_dir, 1)
        return "\n".join(output)

    def add_path(self, path):
        """Додає файл або всі файли з папки до контексту."""
        p = Path(path)
        if not p.exists():
            return 0

        added_count = 0
        
        if p.is_file():
            content = self.files.read_file(str(p))
            if content:
                self.basket[str(p)] = content
                added_count = 1
        elif p.is_dir():
            # Додаємо всі файли з папки (тільки перший рівень, щоб не перевантажити)
            ignore_list = self._get_ignore_list(p)
            for item in p.iterdir():
                if item.is_file() and item.name not in ignore_list:
                    content = self.files.read_file(str(item))
                    if content:
                        self.basket[str(item)] = content
                        added_count += 1
        
        return added_count

    def remove_path(self, path):
        """Видаляє шлях з контексту. Якщо папка - видаляє всі файли, що починаються з цього шляху."""
        # Якщо точний збіг (файл)
        if path in self.basket:
            del self.basket[path]
            return 1
            
        # Якщо це папка або частковий шлях
        to_remove = [k for k in self.basket.keys() if k.startswith(path)]
        count = len(to_remove)
        for k in to_remove:
            del self.basket[k]
        return count

    def get_context_prompt(self):
        """Збирає структуру та вміст кошика в один промпт."""
        # 1. Додаємо дерево проекту
        structure = self.get_project_structure()
        
        # 2. Додаємо вміст файлів з кошика
        files_content = ""
        if self.basket:
            files_content = "\n\n--- OPEN FILES CONTENT ---\n"
            for p, c in self.basket.items():
                files_content += f"FILE: {p}\n{c}\n---\n"
        
        return f"{structure}{files_content}"

    def clear(self):
        self.basket.clear()
