import ctypes
import os
import platform
import logging
from tree_sitter import Language, Parser

class CodeParser:
    def __init__(self):
        self.log = logging.getLogger("angelica.code_parser")
        self.languages = {}
        # Конфігурація вузлів для різних мов
        self.configs = {
            ".kt": {
                "so": "kotlin.so", "name": "kotlin",
                "nodes": ["class_declaration", "function_declaration", "property_declaration", "object_declaration", "interface_declaration"],
                "bodies": ["class_body", "function_body", "enum_class_body", "initializer"]
            },
            ".py": {
                "so": "python.so", "name": "python",
                "nodes": ["class_definition", "function_definition"],
                "bodies": ["block"]
            },
            ".go": {
                "so": "go.so", "name": "go",
                "nodes": ["function_declaration", "method_declaration", "type_declaration"],
                "bodies": ["block", "struct_type", "interface_type"]
            }
        }

    def _get_lib_path(self, so_filename):
        """Визначає шлях до бібліотеки залежно від архітектури."""
        machine = platform.machine().lower()
        if machine in ['arm64', 'aarch64']: machine = 'aarch64'
        system = "android" if 'android' in os.environ.get('PREFIX', '').lower() else "linux"
        arch_folder = f"{system}_{machine}"

        # Шукаємо libs в корені проекту (на рівень вище від modules/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "libs", arch_folder, so_filename)

    def _get_language(self, ext):
        """Завантажує мову з підтримкою різних версій API tree-sitter."""
        if ext in self.languages:
            return self.languages[ext]

        conf = self.configs.get(ext)
        if not conf: return None

        lib_path = self._get_lib_path(conf["so"])
        if not os.path.exists(lib_path):
            self.log.warning(f"SO file not found: {lib_path}")
            return None

        try:
            lib = ctypes.cdll.LoadLibrary(lib_path)
            lang_func = getattr(lib, f"tree_sitter_{conf['name']}")
            lang_func.restype = ctypes.c_void_p
            ptr = lang_func()
            
            try:
                lang = Language(ptr) # API v0.22+
            except TypeError:
                lang = Language(ptr, conf["name"]) # API <0.22
            
            self.languages[ext] = lang
            return lang
        except Exception as e:
            self.log.error(f"Failed to load language {ext}: {e}")
            return None

    def get_skeleton(self, filename, content):
        """Повертає текстовий 'скелет' файлу (сигнатури)."""
        ext = os.path.splitext(filename)[1]
        lang = self._get_language(ext)
        conf = self.configs.get(ext)
        
        if not lang or not conf:
            return content[:500] + "\n... (skeleton not supported for this file type) ..."

        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(lang)
        else:
            parser.language = lang

        if isinstance(content, str):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = content

        tree = parser.parse(content_bytes)
        lines = []

        def _get_sig(node):
            start, end = node.start_byte, node.end_byte
            has_body = False
            
            for child in node.children:
                if child.type in conf["bodies"]:
                    end = child.start_byte
                    has_body = True
                    break
                    
            sig = content_bytes[start:end].decode('utf-8', errors='ignore').strip()
            sig = " ".join(sig.split())
            
            # Додаємо маркер пропущеного коду
            if has_body:
                if ".py" in filename:
                    sig += " : # ... implementation hidden ..."
                else:
                    sig += " { /* ... implementation hidden ... */ }"
                    
            return sig

        def _walk(node, depth=0):
            if node.type in conf["nodes"]:
                sig = _get_sig(node)
                indent = "    " * (depth - 1) + "└── " if depth > 0 else ""
                icon = "📦" if "class" in node.type or "interface" in node.type else "ƒ"
                lines.append(f"{indent}{icon} {sig}")
                depth += 1
            for child in node.children:
                _walk(child, depth)

        _walk(tree.root_node)
        return "\n".join(lines) if lines else "... (no signatures found) ..."