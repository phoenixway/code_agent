#!/bin/bash
# Script to build the standalone executable
./venv/bin/pyinstaller --onefile --add-data "tui.css:." --name angelica tui.py
echo "Build complete. Executable is at dist/angelica"
