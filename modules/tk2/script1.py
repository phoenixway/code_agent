import ctypes
import os
import sys
from tree_sitter import Language, Parser

# Конфігурація для різних мов
LANG_CONFIG = {
    ".kt": {
        "so": "kotlin.so",
        "name": "kotlin",
        "interesting": ["class_declaration", "function_declaration", "property_declaration"],
        "body_nodes": ["class_body", "function_body", "enum_class_body"]
    },
    ".py": {
        "so": "python.so",
        "name": "python",
        "interesting": ["class_definition", "function_definition"],
        "body_nodes": ["block"]
    }
}

def load_lang(ext):
    conf = LANG_CONFIG.get(ext)
    if not conf: return None, None
    lib_path = os.path.abspath(conf["so"])
    if not os.path.exists(lib_path):
        print(f"❌ Файл {conf['so']} не знайдено!")
        return None, None
    
    lib = ctypes.cdll.LoadLibrary(lib_path)
    lang_func = getattr(lib, f"tree_sitter_{conf['name']}")
    lang_func.restype = ctypes.c_void_p
    return Language(lang_func(), conf["name"]), conf

def get_signature(node, source, body_nodes):
    """Витягує текст від початку вузла до початку його тіла"""
    start = node.start_byte
    end = node.end_byte
    
    for child in node.children:
        if child.type in body_nodes:
            end = child.start_byte
            break
            
    sig = source[start:end].decode('utf-8').strip()
    return " ".join(sig.split()) # Прибираємо зайві переноси

def walk_tree(node, source, conf, depth=0):
    """Рекурсивно обходить дерево і друкує цікаві вузли"""
    is_interesting = node.type in conf["interesting"]
    
    if is_interesting:
        sig = get_signature(node, source, conf["body_nodes"])
        indent = "  " * depth
        prefix = "📦 " if "class" in node.type else "ƒ "
        print(f"{indent}{prefix}{sig}")
        new_depth = depth + 1
    else:
        new_depth = depth

    # Рекурсивно йдемо по дітях
    for child in node.children:
        walk_tree(child, source, conf, new_depth)

def process_file(file_path):
    ext = os.path.splitext(file_path)[1]
    lang, conf = load_lang(ext)
    if not lang: return

    with open(file_path, "rb") as f:
        source_code = f.read()

    parser = Parser()
    parser.set_language(lang)
    tree = parser.parse(source_code)

    print(f"\n--- STRUCTURE: {file_path} ---")
    walk_tree(tree.root_node, source_code, conf)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for f in sys.argv[1:]:
            process_file(f)
    else:
        print("Використання: python script.py file.kt file.py")
