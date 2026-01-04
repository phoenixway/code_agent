# modules/project.py
import os

class ProjectModule:
    def get_project_tree(self, root_path, max_depth=3):
        """Повертає дерево каталогів проєкту."""
        tree = []
        for root, dirs, files in os.walk(root_path):
            depth = root[len(root_path):].count(os.sep)
            if depth < max_depth:
                indent = "  " * depth
                tree.append(f"{indent}📁 {os.path.basename(root)}/")
                for f in files:
                    if f.endswith(('.kt', '.xml', '.gradle', '.kts')):
                        tree.append(f"{indent}  📄 {f}")
        return "\n".join(tree)

    def read_source_file(self, file_path):
        """Зчитує вміст конкретного файлу."""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return "⚠️ Файл не знайдено."