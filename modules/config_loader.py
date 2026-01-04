import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from modules.defaults import DEFAULT_SYSTEM_PROMPT

# 1. Визначаємо шлях до конфігурації (стандарт XDG)
CONFIG_DIR = Path.home() / ".config" / "angelica-ai"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"
PROMPT_FILE = CONFIG_DIR / "system_prompt.txt"

def init_config():
    """Створює структуру папок та дефолтні файли, якщо їх немає."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
    # Створюємо базовий config.yaml
    if not CONFIG_FILE.exists():
        default_settings = {
            "default_model": "ollama/deepseek-coder:6.7b",
            "temperature": 0.1,
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(default_settings, f)
            
    # Створюємо шаблон .env для ключів
    if not ENV_FILE.exists():
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            f.write("# Angelica-AI API Keys\nDEEPSEEK_API_KEY=\nGEMINI_API_KEY=\nOPENAI_API_KEY=\n")

    # Створюємо системний промпт (копіюємо з defaults)
    if not PROMPT_FILE.exists():
        with open(PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_SYSTEM_PROMPT)

    # Завантажуємо змінні з .env у середовище (os.environ)
    load_dotenv(ENV_FILE)

def load_settings():
    """Завантажує налаштування з YAML файлу."""
    init_config() # Гарантуємо, що файл існує
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            settings = yaml.safe_load(f)
            return settings if settings else {}
    except Exception:
        return {}

def load_system_prompt():
    """Зчитує текст системного промпту для передачі в ШІ."""
    init_config()
    try:
        if PROMPT_FILE.exists():
            return PROMPT_FILE.read_text(encoding='utf-8')
        return DEFAULT_SYSTEM_PROMPT
    except Exception:
        return DEFAULT_SYSTEM_PROMPT