import importlib
import inspect
import pkgutil
import logging
from typing import Dict
from .base import BaseTool

class ToolManager:
    def __init__(self, package_path="modules.tools.definitions"):
        self.tools: Dict[str, BaseTool] = {}
        self.package_path = package_path
        self.logger = logging.getLogger('tools')

    def load_tools(self):
        """Динамічно завантажує всі класи інструментів з папки definitions."""
        self.tools.clear()
        try:
            package = importlib.import_module(self.package_path)
            for _, name, _ in pkgutil.iter_modules(package.__path__):
                module_name = f"{self.package_path}.{name}"
                module = importlib.import_module(module_name)
                
                for _, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseTool) and 
                        obj is not BaseTool):
                        instance = obj()
                        self.tools[instance.name] = instance
            
            self.logger.info(f"Loaded tools: {list(self.tools.keys())}")
        except Exception as e:
            self.logger.error(f"Error loading tools: {e}")

    def get_tools_prompt(self) -> str:
        """Генерує текст для системного промпту."""
        if not self.tools:
            return "No tools available."
            
        prompt = "AVAILABLE TOOLS:\n"
        for name, tool in self.tools.items():
            prompt += f"- {name}: {tool.description}\n"
        prompt += "\nTo use a tool, return a JSON object: {\"type\": \"tool_name\", \"param1\": \"value\"}"
        return prompt

    async def run_tool(self, name: str, **kwargs) -> dict:
        """Виконує інструмент за назвою."""
        tool = self.tools.get(name)
        if not tool:
            return {"status": "error", "output": f"Tool '{name}' not found."}
        
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return {"status": "error", "output": f"Exception during {name}: {str(e)}"}
