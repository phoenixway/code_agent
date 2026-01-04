# Angelica-AI Agent

Angelica-AI is a Python-based AI agent that can perform various tasks based on user commands. It is designed to be extensible, with a modular architecture that allows for easy addition of new functionalities.

## Features

-   **Modular Architecture**: The agent is divided into several modules, each responsible for a specific functionality. This makes the code easy to understand, maintain, and extend.
-   **Multiple AI Providers**: The agent can be configured to use different AI providers, such as OpenAI, DeepSeek, Ollama, and Gemini.
-   **File Operations**: The agent can read, write, create, and edit files on the local filesystem.
-   **Command Execution**: The agent can execute shell commands and return the output.
-   **Permission Policy**: The agent has a permission policy that can be configured to "ask", "always", or "never" allow sensitive operations.
-   **Session Management**: The agent can save and load sessions, allowing to continue a conversation from where you left off.
-   **Context Management**: The agent can keep track of the files in the current context, which is provided to the AI model with each request.

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-username/angelica-ai.git
    cd angelica-ai
    ```
2.  Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The agent is configured using a `config.yaml` file located in the `~/.config/angelica-ai` directory. You need to create this file and add the necessary configuration.

1.  Create the configuration directory:
    ```bash
    mkdir -p ~/.config/angelica-ai
    ```
2.  Create the `config.yaml` file:
    ```bash
    touch ~/.config/angelica-ai/config.yaml
    ```
3.  Add your configuration to the file. Here is an example:
    ```yaml
    default_model: "ollama/qwen:4b"
    max_history_tokens: 4000
    permission_policy: "ask" # can be "ask", "always", or "never"
    ```
4.  Set the required environment variables. For example, if you are using Ollama, you might need to set the `OLLAMA_BASE_URL`. If you are using OpenAI, you need to set `OPENAI_API_KEY`.

## Usage

To run the agent, simply execute the `agent.py` script:
```bash
python3 agent.py
```

## Testing

To run the tests, execute the following command:
```bash
python3 -m unittest tests/test_modules.py
```

## Modules

-   `agent.py`: The main entry point of the application.
-   `modules/chat.py`: Handles the communication with the AI model.
-   `modules/config_loader.py`: Loads the configuration from the `config.yaml` file.
-   `modules/context.py`: Manages the files in the current context.
-   `modules/defaults.py`: Contains the default system prompt.
-   `modules/files.py`: Provides file operation functionalities.
-   `modules/history.py`: Manages the conversation history.
-   `modules/policy.py`: Handles the permission policy.
-   `modules/processor.py`: Processes the actions received from the AI.
-   `modules/session.py`: Manages the sessions.
-   `modules/storage.py`: (Does not exist anymore)
-   `modules/ui.py`: Handles the user interface.

## Actions

The agent can perform the following actions:
-   `run_command`: Executes a shell command.
-   `read_file`: Reads the content of a file.
-   `write_file`: Writes content to a file, overwriting it if it exists.
-   `create_file`: Creates a new file.
-   `edit_file`: Edits a file by searching and replacing text.
