# Angelica AI Agent `v0.1.0`

Angelica AI is a modular, CLI-based AI agent designed to autonomously perform software engineering tasks. It features a modern Terminal User Interface (TUI) and a robust tool-based architecture.

## 🚀 Features

-   **Interactive TUI**: Built with Textual, featuring a scrolling history, status bars, and modal selection widgets.
-   **Intelligent Reasoning**: Supports models that use `<think>` blocks (like DeepSeek) with specialized parsing.
-   **Advanced Context Management**: 
    -   Automatically builds project structure trees (respecting `.gitignore`).
    -   Manual context control via `/add` and `/drop` commands.
    -   Context window size adjustment (Small, Medium, Large).
-   **Comprehensive Toolset**:
    -   **Filesystem**: Create, read, and surgically edit files.
    -   **Shell**: Execute terminal commands with real-time feedback.
    -   **Search**: High-performance file and content search using `fd` and `ripgrep`.
-   **Security First**: Permission policy (`ask`, `always`, `never`) to control agent actions.
-   **Smart History**: Automatic conversation summarization to maintain context efficiency.
-   **Modular Design**: Easily extensible with new tools and AI providers.

## 🛠 Installation

1.  **Clone & Enter**:
    ```bash
    git clone https://github.com/your-username/angelica-ai.git
    cd angelica-ai
    ```
2.  **Environment Setup**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Requirements**:
    -   `fd-find` and `ripgrep` for search tools.
    -   `python 3.10+`

## ⚙️ Configuration

Settings are loaded from `~/.config/angelica-ai/config.yaml`.

```yaml
default_model: "ollama/qwen2.5-coder:7b"
max_history_tokens: 4000
permission_policy: "ask" # options: ask, always, never
autosummarize_requires_confirmation: false # when true, asks before non-emergency auto-summary
theme: "hacker-green" # options: hacker-green, textual-dark, textual-light, auto(day/night)
history_size: "small" # options: small, medium, large
max_consecutive_calls: 12
max_step_seconds: 120
max_session_seconds: 900
planner_enabled: false # bool; enable taskboard planner protocol
planner_mode: "auto" # auto | always
planner_max_steps: 12
planner_max_visible_steps: 4
planner_always_missing_retry_limit: 2 # stop if model repeatedly omits <taskboard> in always mode
allow_side_effect_tools: true
max_shell_command_length: 1000
shell_blocklist:
  - "rm -rf /"
  - "mkfs"
shell_allowlist_prefixes: [] # optional; when not empty, only these command prefixes are allowed
available_models: 
  - "ollama/qwen2.5-coder:7b"
  - "openai/gpt-4o"
  - "vertexai/gemini-2.5-flash"

vertexai:
  project_id: "your-google-cloud-project-id"
  location: "us-central1"
  use_adc: true
```

## ⌨️ Usage

Run the agent:
```bash
make run
# or directly:
python tui.py
```

### CLI Commands:
- `/add <path>`: Add files or directories to AI context.
- `/drop [path]`: Remove specific paths or clear context (if no path).
- `/models`: Switch between available AI models via a selection widget.
- `/theme`: Switch interface theme.
- `/history-size`: Change history context window size.
- `/cd <path>`: Change current working directory.
- `/export [filename]`: Save chat history to a Markdown file.
- `/dump [--full] [filename]`: Save runtime log dump (default: current session only; `--full` includes full logs).
- `/import <filename>`: Load chat history from a file.

## 🧪 Testing & Development

Comprehensive tests and development tools are available via `Makefile`.

```bash
make test          # Run all 40+ tests
make smoke         # Run end-to-end smoke flow (/add -> tool -> /drop)
make test-core     # Core logic (parser, processor, context)
make test-tools    # Tool definitions (files, shell, search)
make test-commands # CLI command logic
make test-compiler # Protocol compiler golden tests
make test-gaps     # Protocol compiler coverage gap matrix

# Versioning (requires bump-my-version)
make bump-patch    # 0.1.0 -> 0.1.1
make bump-minor    # 0.1.0 -> 0.2.0
make bump-major    # 0.1.0 -> 1.0.0
```

## 📚 Documentation

Detailed guides are available in the `docs/` folder:
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Testing Manual](docs/TESTING.md)
- [Creating New Tools](docs/CREATING_TOOLS.md)
- [Development Log](docs/DEV_LOG.md)

## 🧩 Modules

- `tui.py`: Main TUI application entry point.
- `modules/agent/`: Modular orchestrator and main agent logic.
- `modules/processor.py`: Action parsing and execution management.
- `modules/tools/`: Dynamic tool loading and definitions.
- `modules/context.py`: Project tree and file basket management.
- `modules/history.py`: Conversation history and summarization.
- `modules/policy.py`: Security and permission checks.
- `modules/tui_ui.py`: Textual TUI implementation.
