#!/usr/bin/env python3
import sys
import re
from pathlib import Path

SEPARATOR_LINE = "=" * 80

# Артефакти, які з’являються при копіюванні з терміналу
TRAILING_GARBAGE_RE = re.compile(r"[^\w\./\\-].*$")

# Папки, які треба ігнорувати при рекурсивному обході
IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
}

# Файли, які зазвичай не треба включати
IGNORE_FILES = {
    ".DS_Store",
}

# Розширення, які краще не читати як текст
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyc",
    ".pyo",
    ".class",
    ".jar",
    ".sqlite",
    ".db",
}


def clean_path(line: str) -> str:
    """Повертає чистий шлях без пробілів, шуму та артефактів."""
    line = line.strip()
    line = TRAILING_GARBAGE_RE.sub("", line)
    return line.strip()


def parse_args():
    input_list_file = None
    output_file = None

    args = sys.argv[1:]
    i = 0

    while i < len(args):
        if args[i] == "-i":
            if i + 1 >= len(args):
                print("Помилка: після -i потрібно вказати файл.")
                sys.exit(1)

            input_list_file = Path(args[i + 1])
            i += 2
        else:
            if output_file is None:
                output_file = Path(args[i])
                i += 1
            else:
                print(f"Невідомий аргумент: {args[i]}")
                sys.exit(1)

    if not input_list_file:
        print("Помилка: потрібно вказати -i <file> з шляхами.")
        sys.exit(1)

    if not output_file:
        print("Помилка: потрібно вказати вихідний файл.")
        sys.exit(1)

    return output_file, input_list_file


def should_ignore_dir(path: Path) -> bool:
    """Перевіряє, чи треба ігнорувати папку."""
    return path.name in IGNORE_DIRS


def should_ignore_file(path: Path) -> bool:
    """Перевіряє, чи треба ігнорувати файл."""
    if path.name in IGNORE_FILES:
        return True

    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    return False


def collect_files_from_directory(directory: Path):
    """
    Рекурсивно збирає файли з папки,
    ігноруючи службові директорії типу __pycache__, .git, node_modules.
    """
    files = []

    try:
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                if should_ignore_dir(child):
                    continue

                files.extend(collect_files_from_directory(child))

            elif child.is_file():
                if should_ignore_file(child):
                    continue

                files.append(child)

    except Exception as e:
        print(f"Попередження: не вдалося прочитати папку {directory}: {e}")

    return files


def read_input_paths(list_file: Path):
    if not list_file.exists():
        print(f"Файл списку не знайдено: {list_file}")
        sys.exit(1)

    raw_paths = set()

    with list_file.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            path = clean_path(raw)

            if not path:
                continue

            raw_paths.add(path)

    if not raw_paths:
        print(f"Файл {list_file} не містить валідних шляхів.")
        sys.exit(1)

    collected_files = []

    for raw_path in sorted(raw_paths):
        path = Path(raw_path)

        if path.is_dir():
            if should_ignore_dir(path):
                continue

            collected_files.extend(collect_files_from_directory(path))

        elif path.is_file():
            if should_ignore_file(path):
                continue

            collected_files.append(path)

        else:
            print(f"Попередження: шлях не знайдено, пропускаю: {path}")

    # Дедуплікація після рекурсивного збору
    unique_files = []
    seen = set()

    for file_path in collected_files:
        resolved = file_path.resolve()

        if resolved in seen:
            continue

        seen.add(resolved)
        unique_files.append(file_path)

    if not unique_files:
        print("Не знайдено жодного файлу для обробки.")
        sys.exit(1)

    return unique_files


def main():
    output_file, list_file = parse_args()
    input_files = read_input_paths(list_file)

    # Готуємо дані TOC
    toc_entries = []

    for index, src in enumerate(input_files, start=1):
        toc_entries.append((f"FILE_{index}", src.resolve()))

    # Пишемо вихідний файл
    with output_file.open("w", encoding="utf-8") as out:
        # TABLE OF CONTENTS
        out.write("TABLE OF CONTENTS\n")
        out.write(SEPARATOR_LINE + "\n\n")

        for anchor, abs_path in toc_entries:
            out.write(f"- [{abs_path}](##<<{anchor}>>)\n")

        out.write("\n" + SEPARATOR_LINE + "\n\n")

        # FILE SECTIONS
        for index, src in enumerate(input_files, start=1):
            abs_path = src.resolve()
            anchor = f"FILE_{index}"

            out.write(f"## <<{anchor}>>\n")
            out.write(SEPARATOR_LINE + "\n")
            out.write(f"BEGIN FILE: {abs_path} (ID: {anchor})\n")
            out.write(SEPARATOR_LINE + "\n\n")

            try:
                with abs_path.open("r", encoding="utf-8", errors="replace") as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"[Помилка читання файлу {abs_path}: {e}]\n")

            out.write("\n\n")
            out.write(SEPARATOR_LINE + "\n")
            out.write(f"END FILE: {abs_path}\n")
            out.write(SEPARATOR_LINE + "\n\n")

    print(f"Готово! Файл створено: {output_file.resolve()}")
    print(f"Файлів додано: {len(input_files)}")


if __name__ == "__main__":
    main()
