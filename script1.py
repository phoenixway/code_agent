import ctypes
import os
import sys
import platform
from tree_sitter import Language, Parser

# --- КОНФІГУРАЦІЯ ---
LANG_CONFIG = {
    ".kt": {
        "so_name": "kotlin.so",
        "lang_name": "kotlin",
        "interesting": ["class_declaration", "function_declaration", "property_declaration", "object_declaration", "interface_declaration"],
        "body_nodes": ["class_body", "function_body", "enum_class_body", "initializer"]
    },
    ".py": {
        "so_name": "python.so",
        "lang_name": "python",
        "interesting": ["class_definition", "function_definition", "decorated_definition"],
        "body_nodes": ["block"]
    },
    ".go": {
        "so_name": "go.so",
        "lang_name": "go",
        "interesting": ["function_declaration", "method_declaration", "type_declaration"],
        "body_nodes": ["block", "struct_type", "interface_type"]
    }
}

def get_lib_path(so_filename):
    machine = platform.machine().lower()
    if machine in ['arm64', 'aarch64']: machine = 'aarch64'
    
    system = "android" if 'android' in os.environ.get('PREFIX', '').lower() else "linux"
    arch_folder = f"{system}_{machine}"
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "libs", arch_folder, so_filename)

def load_lang(ext):
    """Завантажує мову, адаптуючись до змін API 2025-2026 років"""
    conf = LANG_CONFIG.get(ext)
    if not conf: return None, None
    
    lib_path = get_lib_path(conf["so_name"])
    if not os.path.exists(lib_path):
        print(f"⚠️  Бібліотеку не знайдено: {lib_path}")
        return None, None
    
    try:
        lib = ctypes.cdll.LoadLibrary(lib_path)
        lang_func = getattr(lib, f"tree_sitter_{conf['lang_name']}")
        lang_func.restype = ctypes.c_void_p
        ptr = lang_func()
        
        # Спроба завантаження з врахуванням різних версій конструктора
        try:
            # Нове API (0.22+)
            return Language(ptr), conf
        except TypeError:
            # Старе API (<0.22)
            return Language(ptr, conf["lang_name"]), conf
            
    except Exception as e:
        print(f"❌ Помилка завантаження {lib_path}: {e}")
        return None, None

def get_signature(node, source, body_nodes):
    start, end = node.start_byte, node.end_byte
    for child in node.children:
        if child.type in body_nodes:
            end = child.start_byte
            break
    text = source[start:end].decode('utf-8', errors='ignore').strip()
    return " ".join(text.split())

def walk_tree(node, source, conf, depth=0):
    if node.type in conf["interesting"]:
        sig = get_signature(node, source, conf["body_nodes"])
        indent = "    " * (depth - 1) + "└── " if depth > 0 else ""
        icon = "📦" if "class" in node.type or "interface" in node.type else "ƒ"
        print(f"{indent}{icon} {sig}")
        depth += 1

    for child in node.children:
        walk_tree(child, source, conf, depth)

def process_file(file_path):
    if not os.path.exists(file_path): return

    ext = os.path.splitext(file_path)[1]
    lang, conf = load_lang(ext)
    if not lang: return

    with open(file_path, "rb") as f:
        source_code = f.read()

    parser = Parser()
    
    # ПЕРЕВІРКА API: set_language() vs .language property
    if hasattr(parser, "set_language"):
        parser.set_language(lang)
    else:
        parser.language = lang

    tree = parser.parse(source_code)

    print(f"\n📄 STRUCTURE: {os.path.basename(file_path)}")
    print("═" * 50)
    walk_tree(tree.root_node, source_code, conf)
    print("═" * 50)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Використання: python3 script1.py <file.kt>")
    else:
        for arg in sys.argv[1:]:
            process_file(arg)