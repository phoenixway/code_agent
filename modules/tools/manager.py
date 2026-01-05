# modules/tools/manager.py
import importlib
import inspect
import pkgutil
from typing import Dict
from .base import BaseTool

class ToolManager:
    def __init__(self, definitions_pkg="modules.tools.definitions"):
        self.tools: Dict[str, BaseTool] = {}
        self._pkg = definitions_pkg

    def load_tools(self):
        """Динамічно завантажує всі класи інструментів."""
        self.tools.clear()
        try:
            package = importlib.import_module(self._pkg)
            for _, name, _ in pkgutil.iter_modules(package.__path__):
                mod = importlib.import_module(f"{self._pkg}.{name}")
                for _, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        t = obj()
                        self.tools[t.name] = t
            return list(self.tools.keys())
        except Exception as e:
            print(f"Error loading tools: {e}")
            return []

    def get_tools_prompt(self) -> str:
        """Генерує опис інструментів для ШІ."""
        if not self.tools:
            return "No tools available."
        prompt = "AVAILABLE TOOLS:\n"
        for name, tool in self.tools.items():
            prompt += f"- {name}: {tool.description}\n"
        return prompt

    async def call(self, name: str, **kwargs):
        """ВИПРАВЛЕНО: Метод тепер називається 'call'"""
        tool = self.tools.get(name)
        if not tool:
            return {"status": "error", "output": f"Unknown tool: {name}"}
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return {"status": "error", "output": f"Tool execution failed: {str(e)}"}
