from __future__ import annotations

from typing import Any

from ..base import BaseTool
from ._kotlin_symbol_extractor import KotlinSymbolExtractor


class ExtractSymbolTool(BaseTool):
    name = "extract_symbol"
    description = (
        "Extracts a Kotlin symbol using tree-sitter. Supports function, composable, class, enum, object, "
        "interface, method, and property. Params: 'path' (str), 'symbol_name' (str), optional "
        "'symbol_kind' (str: auto|function|composable|class|enum|object|interface|method|property), "
        "'container_name' (str), 'occurrence' (int, default 1), 'include_signature' (bool, default True), "
        "'include_body' (bool, default True), and 'include_line_range' (bool, default True). "
        "Returns symbol kind, signature, optional body, and precise line range."
    )

    def __init__(self):
        self.extractor = KotlinSymbolExtractor()

    async def execute(
        self,
        path: str,
        symbol_name: str,
        symbol_kind: str | None = None,
        container_name: str | None = None,
        occurrence: int = 1,
        include_signature: bool = True,
        include_body: bool = True,
        include_line_range: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        try:
            return self.extractor.extract_symbol(
                path=path,
                symbol_name=symbol_name,
                symbol_kind=symbol_kind,
                container_name=container_name,
                occurrence=occurrence,
                include_body=include_body,
                include_signature=include_signature,
                include_line_range=include_line_range,
            )
        except Exception as exc:
            return {
                "status": "error",
                "error_code": "INTERNAL",
                "recoverable": False,
                "output": f"extract_symbol failed: {exc}",
            }
