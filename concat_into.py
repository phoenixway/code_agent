#!/usr/bin/env python3
import sys
import re
from pathlib import Path

SEPARATOR_LINE = "=" * 80

# Артефакти, які з’являються при копіюванні з терміналу
TRAILING_GARBAGE_RE = re.compile(r"[^\w\./\\-].*$")


def clean_path(line: str) -> str:
    """Повертає чистий шлях без пробілів, шуму та артефактів."""
    line = line.strip()
    line = TRAILING_GARBAGE_RE.sub("", line)  # вирізаємо '█', '▄', кольорові код
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


def read_input_paths(list_file: Path):
    if not list_file.exists():
        print(f"Файл списку не знайдено: {list_file}")
        sys.exit(1)

    cleaned = set()

    with list_file.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            path = clean_path(raw)
            if not path:
                continue
            cleaned.add(path)

    if not cleaned:
        print(f"Файл {list_file} не містить валідних шляхів.")
        sys.exit(1)

    return [Path(p) for p in sorted(cleaned)]

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


if __name__ == "__main__":
    main()


