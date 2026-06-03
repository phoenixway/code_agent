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


def test_extract_symbol_kotlin_enum_with_body_returns_full_enum(tmp_path):
    path = tmp_path / "DayManagementTab.kt"
    path.write_text(
        "package demo\n\n"
        "enum class DayManagementTab(val title: String, val description: String) {\n"
        "    PLAN(\"Plan\", \"Plan today\"),\n"
        "    FOCUS(\"Focus\", \"Focus work\"),\n"
        "    REVIEW(\"Review\", \"Review day\");\n"
        "\n"
        "    fun isPlanning(): Boolean = this == PLAN\n"
        "}\n",
        encoding="utf-8",
    )

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="DayManagementTab",
        symbol_kind="enum",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "enum"
    assert "enum class DayManagementTab" in result["file_content"]
    assert "PLAN(\"Plan\", \"Plan today\")" in result["file_content"]
    assert "fun isPlanning" in result["file_content"]
    assert result["file_content"].strip().endswith("}")


def test_extract_symbol_kotlin_enum_with_body_returns_full_enum(tmp_path):
    path = tmp_path / "DayManagementTab.kt"
    path.write_text(
        "package demo\n\n"
        "enum class DayManagementTab(val title: String) {\n"
        "    PLAN(\"Plan\"),\n"
        "    EXECUTE(\"Execute\"),\n"
        "    REVIEW(\"Review\");\n"
        "\n"
        "    fun isPrimary(): Boolean = this == PLAN\n"
        "}\n",
        encoding="utf-8",
    )

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="DayManagementTab",
        symbol_kind="enum",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "enum"
    assert "enum class DayManagementTab" in result["file_content"]
    assert "PLAN(\"Plan\")" in result["file_content"]
    assert "fun isPrimary" in result["file_content"]
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


KOTLIN_MEMBER_DUPLICATE_SAMPLE = """package sample

class ContextScreenViewModel @Inject constructor(
    private val contextViewActions: ContextViewActions,
    private val contextSettingsActions: ContextSettingsActions,
    private val ioDispatcher: CoroutineDispatcher,
) : ViewModel() {
    fun onProjectViewChange(mode: ContextViewMode) {
        val resolved = contextViewActions.applyViewChange(mode)
        viewModelScope.launch(ioDispatcher) {
            contextSettingsActions.persistContextViewMode(contextIdFlow.value, resolved)
        }
    }

    private fun helper() {
        println("helper")
    }
}

fun onProjectViewChange(mode: ContextViewMode) {
    println("top level")
}

class OtherViewModel {
    fun onProjectViewChange(mode: ContextViewMode) {
        println("other member")
    }
}

enum class ContextViewMode {
    Dashboard,
    Backlog
}
"""


def test_extract_symbol_finds_kotlin_member_function_as_method_with_container(tmp_path):
    path = tmp_path / "ContextScreenViewModel.kt"
    path.write_text(KOTLIN_MEMBER_DUPLICATE_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="onProjectViewChange",
        symbol_kind="method",
        container_name="ContextScreenViewModel",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_name"] == "onProjectViewChange"
    assert result["symbol_kind"] == "method"
    assert result["container_name"] == "ContextScreenViewModel"
    assert "fun onProjectViewChange(mode: ContextViewMode)" in result["signature"]
    assert "val resolved = contextViewActions.applyViewChange(mode)" in result["body"]
    assert "contextSettingsActions.persistContextViewMode" in result["file_content"]
    assert 'println("top level")' not in result["file_content"]
    assert 'println("other member")' not in result["file_content"]


def test_extract_symbol_method_container_disambiguates_from_top_level_function(tmp_path):
    path = tmp_path / "ContextScreenViewModel.kt"
    path.write_text(KOTLIN_MEMBER_DUPLICATE_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="onProjectViewChange",
        symbol_kind="method",
        container_name="OtherViewModel",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "method"
    assert result["container_name"] == "OtherViewModel"
    assert 'println("other member")' in result["file_content"]
    assert "val resolved = contextViewActions.applyViewChange(mode)" not in result["file_content"]
    assert 'println("top level")' not in result["file_content"]


def test_extract_symbol_method_wrong_container_returns_not_found(tmp_path):
    path = tmp_path / "ContextScreenViewModel.kt"
    path.write_text(KOTLIN_MEMBER_DUPLICATE_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="onProjectViewChange",
        symbol_kind="method",
        container_name="MissingViewModel",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "error"
    assert result["error_code"] == "NOT_FOUND"
    assert "MissingViewModel" in result["output"]


def test_extract_symbol_kotlin_member_function_still_extractable_as_function_with_container(tmp_path):
    path = tmp_path / "ContextScreenViewModel.kt"
    path.write_text(KOTLIN_MEMBER_DUPLICATE_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="onProjectViewChange",
        symbol_kind="function",
        container_name="ContextScreenViewModel",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "method"
    assert result["container_name"] == "ContextScreenViewModel"
    assert "val resolved = contextViewActions.applyViewChange(mode)" in result["file_content"]
    assert 'println("top level")' not in result["file_content"]


def test_extract_symbol_auto_can_find_kotlin_member_function_with_container(tmp_path):
    path = tmp_path / "ContextScreenViewModel.kt"
    path.write_text(KOTLIN_MEMBER_DUPLICATE_SAMPLE, encoding="utf-8")

    result = KotlinSymbolExtractor().extract_symbol(
        path=str(path),
        symbol_name="onProjectViewChange",
        symbol_kind="auto",
        container_name="ContextScreenViewModel",
        include_signature=True,
        include_body=True,
        include_line_range=True,
    )

    assert result["status"] == "success"
    assert result["symbol_kind"] == "method"
    assert result["container_name"] == "ContextScreenViewModel"
    assert "val resolved = contextViewActions.applyViewChange(mode)" in result["file_content"]
    assert 'println("top level")' not in result["file_content"]
