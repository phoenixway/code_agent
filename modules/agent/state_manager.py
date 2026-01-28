"""Управління станом сесії агента."""

import json


class AgentState:
    """Зберігає динамічний стан агента: токени, циклічність, задачі."""
    
    def __init__(self):
        # Відстеження токенів
        self.session_tokens = 0
        
        # Виявлення нескінченних циклів
        self.last_action_fingerprint = None
        self.last_action_status = None
        self.consecutive_failed_repeats = 0
        
        # Асинхронні задачі
        self.current_task = None
        
        # Стан інтерфейсу
        self.is_awaiting_model_selection = False
    
    def get_action_fingerprint(self, command: dict) -> str:
        """Створює стабільний відбиток дії для перевірки циклів."""
        cmd_type = command.get("type") or command.get("action") or "unknown"
        
        # Ігноруємо службові поля, які змінюються при виконанні
        ignored_fields = {
            "before_execution", "during_execution", "after_execution", 
            "return_control", "id"
        }
        
        args = {k: v for k, v in command.items() if k not in ignored_fields}
        
        # sort_keys=True гарантує, що {a:1, b:2} == {b:2, a:1}
        return f"{cmd_type}:{json.dumps(args, sort_keys=True)}"
    
    def update_loop_tracker(self, command: dict, status: str):
        """Оновлює лічильники повторюваних помилок."""
        fingerprint = self.get_action_fingerprint(command)
        
        # Якщо дія та сама, і вона знову впала -> збільшуємо лічильник
        if fingerprint == self.last_action_fingerprint and self.last_action_status in ["failed", "error"]:
            self.consecutive_failed_repeats += 1
        else:
            self.consecutive_failed_repeats = 0
        
        self.last_action_fingerprint = fingerprint
        self.last_action_status = status
        
    def add_tokens(self, prompt: int, completion: int):
        self.session_tokens += (prompt + completion)
