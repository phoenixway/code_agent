from __future__ import annotations

from typing import Any

from ..base import BaseTool
from ._kotlin_symbol_extractor import KotlinSymbolExtractor


class ExtractKotlinFunctionTool(BaseTool):
    name = "extract_kotlin_function"
    description = (
        "Backward-compatible wrapper around extract_symbol for Kotlin functions and methods. "
        "Params: 'path' (str), 'function_name' (str), optional 'class_name' (str), optional "
        "'occurrence' (int, default 1), optional 'include_body' (bool, default True). "
        "Returns exact source, signature, and line range."
    )

    def __init__(self):
        self.extractor = KotlinSymbolExtractor()

    async def execute(
        self,
        path: str,
        function_name: str,
        class_name: str | None = None,
        occurrence: int = 1,
        include_body: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        try:
            result = self.extractor.extract_symbol(
                path=path,
                symbol_name=function_name,
                symbol_kind="function",
                container_name=class_name,
                occurrence=occurrence,
                include_body=include_body,
                include_signature=True,
                include_line_range=True,
            )
            if result.get("status") != "success":
                return result

            result["tool_variant"] = "extract_kotlin_function"
            result["function_name"] = result.get("symbol_name")
            result["class_name"] = result.get("container_name")
            result["output"] = result.get("file_content") or result.get("output")
            return result
        except Exception as exc:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"extract_kotlin_function failed: {exc}",
            }
