from modules.tools.definitions._kotlin_symbol_extractor import KotlinSymbolExtractor


KOTLIN_CLASS_SAMPLE = """package demo

@HiltViewModel
class ChecklistViewModel @Inject constructor(
    private val repo: ChecklistRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ChecklistUiState())

    fun onToggleSearch(active: Boolean) {
        _uiState.update { it.copy(isSearchActive = active) }
    }
}
"""


def test_extract_symbol_kotlin_class_with_body_returns_full_class(tmp_path):
    path = tmp_path / "ChecklistViewModel.kt"
    path.write_text(KOTLIN_CLASS_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="ChecklistViewModel",
        symbol_kind="class",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "class"
    assert "@HiltViewModel" in result["file_content"]
    assert "class ChecklistViewModel @Inject constructor" in result["file_content"]
    assert "private val _uiState" in result["file_content"]
    assert "fun onToggleSearch" in result["file_content"]
    assert result["file_content"].strip().endswith("}")
    assert result["body"] == result["file_content"]
    assert result["end_line"] > result["start_line"] + 5


def test_extract_symbol_kotlin_class_signature_only_excludes_body(tmp_path):
    path = tmp_path / "ChecklistViewModel.kt"
    path.write_text(KOTLIN_CLASS_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="ChecklistViewModel",
        symbol_kind="class",
        include_signature=True,
        include_body=False,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert "class ChecklistViewModel @Inject constructor" in result["file_content"]
    assert "fun onToggleSearch" not in result["file_content"]
    assert result["body"] == ""
    assert result["file_content"].strip().endswith(": ViewModel()")


def test_extract_symbol_kotlin_interface_with_body_returns_interface_kind(tmp_path):
    path = tmp_path / "CapabilityDescriptor.kt"
    path.write_text(
        "package demo\n\n"
        "interface CapabilityDescriptor {\n"
        "    val id: CapabilityId\n"
        "    val label: String\n"
        "    val supportedViews: Set<ViewId>\n"
        "}\n",
        encoding="utf-8",
    )

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="CapabilityDescriptor",
        symbol_kind="interface",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "interface"
    assert "interface CapabilityDescriptor" in result["file_content"]
    assert "val label: String" in result["file_content"]
    assert result["file_content"].strip().endswith("}")


def test_extract_symbol_kotlin_interface_with_body_returns_interface_kind(tmp_path):
    path = tmp_path / "CapabilityDescriptor.kt"
    path.write_text(
        "package demo\n\n"
        "interface CapabilityDescriptor {\n"
        "    val id: CapabilityId\n"
        "    val label: String\n"
        "    val supportedViews: Set<ViewId>\n"
        "}\n",
        encoding="utf-8",
    )

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="CapabilityDescriptor",
        symbol_kind="interface",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "interface"
    assert "interface CapabilityDescriptor" in result["file_content"]
    assert "val label: String" in result["file_content"]
    assert result["file_content"].strip().endswith("}")


def test_extract_symbol_kotlin_object_with_body_returns_full_object(tmp_path):
    path = tmp_path / "ChecklistActions.kt"
    path.write_text(
        "package demo\n\nobject ChecklistActions {\n    fun run() = Unit\n}\n",
        encoding="utf-8",
    )

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="ChecklistActions",
        symbol_kind="object",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "object"
    assert "object ChecklistActions" in result["file_content"]
    assert "fun run() = Unit" in result["file_content"]
    assert result["file_content"].strip().endswith("}")
