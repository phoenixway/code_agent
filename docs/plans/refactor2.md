# Завдання: впровадити ProtocolSpec + grammar/AST/IR compiler-style pipeline для Angelica AI response protocol

## Контекст

У runtime автономного coding agent-а повторюються bugs одного класу:

- модель порушує response protocol;
- runtime іноді неправильно це детектить;
- recovery prompt описує не той root cause;
- модель виправляє не ту помилку;
- виникає новий protocol shape error або recovery loop.

Поточні симптоми з dumps:

- literal protocol tags у markdown/plain text, наприклад `` `<action>` `` або `` `<intent>` ``, можуть бути помилково розпізнані як real control blocks;
- visible prose + `<action>` в одному response може класифікуватись як generic malformed action, хоча root cause — mixed visible/control;
- `<think>` recovery іноді каже “protocol tags inside think”, хоча реальний root cause інший;
- intent/action bundle має бути atomic all-or-nothing, але trace не завжди явно показує `transition_applied=false`, `action_dispatched=false`;
- action payload array / multiple actions у atomic bundle спричиняють recovery loops;
- read-only batch policy конфліктує з atomic bundle policy, якщо це не розведено явно;
- stale intent examples у recovery можуть дезорієнтувати модель;
- stale plan/subgoal board може протікати між intent lineage;
- memory/subgoal prompt іноді провокує зайві/rejected tags.

Мета — не додати ще один локальний prompt patch, а почати перехід до **formal protocol compiler pipeline**.

Зовнішній protocol для моделі НЕ міняємо.

Модель і далі може відповідати блоками типу:

```xml
<think>...</think>
<memory_update_done />
<intent mode="activate">...</intent>
<action>...</action>
<file_content>...</file_content>
````

Але runtime має обробляти це не набором незалежних regex/stage scans, а як маленьку мову:

```text
raw model output
→ ProtocolSpec
→ markdown-aware/custom lexer
→ formal protocol parser
→ AST
→ ResponseShape
→ IR
→ semantic/runtime validation
→ transaction plan / effect preview
→ executor
→ recovery from typed ErrorValue / RecoveryStrategy
```

## Головний архітектурний принцип

> The model is never trusted with control flow or state mutation. It only proposes. The pipeline decides and verifies.

У коді це має означати:

```text
Model output may create proposals.
Only validated ExecutionPlan may mutate runtime state.
Only Executor may commit side effects.
Recovery is generated from typed ErrorValue, not from ad hoc parser/stage strings.
```

Інваріанти:

```text
- invalid response never dispatches action;
- rejected intent never mutates active intent;
- invalid bundle never partially applies;
- visible/control protocol error never dispatches action;
- plan board from another intent lineage is never injected as current state.
```

---

# Phase -1: ProtocolSpec as first-class artifact

## Goal

Зробити protocol definition declarative і machine-readable.

Це найважливіший етап. Правила protocol не мають жити одночасно в prompt text, parser regex, action policy, recovery strings і tests.

Створити `ProtocolSpec` або еквівалентний artifact, який стане single source of truth для:

```text
- known protocol blocks;
- block attributes;
- payload types;
- allowed structural contexts;
- response shapes;
- constraints;
- error codes;
- recovery ids;
- prompt/doc snippets;
- test generation.
```

Не треба одразу генерувати весь lexer/parser/recovery з ProtocolSpec. Спершу ProtocolSpec має бути readable registry, на який посилаються parser/validators/recovery/tests.

## Conceptual structure

```python
@dataclass(frozen=True)
class ProtocolSpec:
    version: str
    blocks: dict[str, BlockSpec]
    shapes: dict[str, ShapeSpec]
    constraints: list[ConstraintSpec]
    errors: dict[str, ErrorSpec]
```

### BlockSpec

```python
BlockSpec(
    name="intent",
    kind="closed",
    attrs={
        "mode": EnumSpec(["activate", "complete", "reuse", "replace"])
    },
    payload=PayloadSpec(type="json"),
    structural_only=True,
    allowed_contexts=["root"],
)
```

Examples of blocks to include:

```text
think
intent
action
file_content
memory_update_done
fact
finding
decision
path
progress
memory_review
subgoal
```

### ShapeSpec

```python
ShapeSpec(
    name="INTENT_ACTION_BUNDLE",
    sequence=[
        OptionalBlock("think"),
        ManyBlocks("memory_or_subgoal"),
        OptionalBlock("memory_update_done"),
        RequiredBlock("intent"),
        RequiredBlock("action"),
        OptionalBlock("file_content"),
    ],
    constraints=[
        "exactly_one_intent",
        "exactly_one_action",
        "no_visible_text",
        "file_content_only_for_write_action",
        "atomic_all_or_nothing",
    ],
)
```

Initial shapes to model:

```text
PLAINTEXT_ONLY
MEMORY_TEXT
ACTION_ONLY
READ_ONLY_BATCH_CANDIDATE
INTENT_ONLY
INTENT_ACTION_BUNDLE
INTENT_COMPLETE_WITH_TEXT
INVALID
```

### ConstraintSpec

```python
ConstraintSpec(
    id="atomic_bundle_requires_exactly_one_action",
    phase="shape",
    applies_to="INTENT_ACTION_BUNDLE",
    error_code="E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION",
)
```

### ErrorSpec

```python
ErrorSpec(
    code="E_MIXED_VISIBLE_TEXT_AND_CONTROL",
    phase="shape",
    recovery_id="mixed_visible_control",
    default_message="Visible text cannot be mixed with protocol/action blocks.",
)
```

## Required design choice

ProtocolSpec should initially be a source of shared constants/rules and documentation.

Full code generation from ProtocolSpec is optional and should be deferred until the grammar stabilizes.

## Acceptance

```text
- ProtocolSpec exists as a first-class artifact.
- Known blocks, shapes, constraints, and error codes are declared there.
- Parser/validator/recovery/tests can import or reference it.
- Existing external model protocol remains unchanged.
```

---

# Phase 0: Inventory and safety baseline

## Goal

Before changing behavior, identify current response parsing/classification/recovery flow and add a minimal test harness around it.

## Required work

Find the runtime components responsible for:

```text
- parsing protocol blocks
- classifying response shape
- detecting malformed `<think>`
- detecting `<action>` / `<intent>` / `<file_content>`
- visible text extraction
- intent transition handling
- action policy validation
- output recovery prompt generation
- loop/retry/recovery tracking
- plan board and memory board state injection/mutation
```

Do not assume file names from this prompt are current. Locate by behavior, symbols, tests, and references.

## Add a behavior fixture corpus

Create fixture-based tests for real model outputs.

Example organization:

```text
tests/fixtures/model_outputs/
  valid/
  invalid/
  recovery/
```

Each fixture should have expected metadata, for example:

```yaml
shape: INTENT_ACTION_BUNDLE
valid: false
invalid_kind: atomic_bundle_action_invalid
invalid_part: action
reason: atomic_bundle_requires_exactly_one_action
transition_applied: false
action_dispatched: false
recovery_id: atomic_bundle_exactly_one_action
```

Start with fixtures for known recurring cases:

```text
1. valid closed think + marker + action
2. visible text only mentioning `<action>` in inline code
3. fenced XML example containing `<intent>` and `<action>`
4. real unclosed `<think>`
5. real `<action>` inside open `<think>`
6. visible prose before `<action>`
7. valid intent/action/file_content bundle
8. intent/action bundle with action JSON array
9. intent/action bundle with two action blocks
10. write action missing file_content
11. intent-only activate
12. intent complete + plaintext answer
13. plain markdown documentation that explains `<think>`, `<intent>`, `<action>`
14. `<file_content>` containing code with `<`, `>`, `&&`, XML-looking strings
```

Acceptance:

```text
- Existing tests still pass.
- New fixtures can be loaded by tests.
- No runtime behavior change yet unless needed to add diagnostics safely.
```

---

# Phase 1: Formal grammar spec

## Goal

Document Angelica response protocol as formal grammar.

The grammar is for **top-level protocol structure**, not full markdown/XML/JSON.

Create a grammar document, for example:

```text
docs/protocol/response_grammar.md
```

or, if using a parser generator later:

```text
modules/protocol/response_grammar.lark
modules/protocol/response_grammar.g4
```

Exact path can differ.

## Important guidance

Do NOT use raw `lxml.fromstring("<response>" + raw + "</response>")` as the main parser.

The Angelica response protocol is XML-like, not real XML:

```text
- no single root element;
- plain text responses are valid;
- markdown/code may contain `<action>` as text;
- `<file_content>` may contain raw code with `<`, `>`, `&`;
- fenced XML examples must not become protocol nodes;
- inline code like `` `<intent>` `` must not become protocol nodes.
```

Use a formal grammar for top-level structure and custom lexer modes for raw/literal contexts.

## Initial EBNF-style target

Use this as a starting point. Adapt names to implementation.

```ebnf
response
  ::= plaintext_response
   | protocol_response ;

protocol_response
  ::= leading_section? output_section ;

leading_section
  ::= think_block? board_section? marker? ;

board_section
  ::= board_node* ;

board_node
  ::= memory_node
   | subgoal_node ;

output_section
  ::= action_output
   | read_only_batch_candidate
   | intent_output
   | intent_action_output
   | intent_completion_output
   | memory_text_output ;

action_output
  ::= action_block file_content_block? ;

read_only_batch_candidate
  ::= action_block action_block action_block? action_block? ;

intent_output
  ::= intent_block ;

intent_action_output
  ::= intent_block action_block file_content_block? ;

intent_completion_output
  ::= intent_complete_block plaintext_tail ;

memory_text_output
  ::= plaintext_tail ;

think_block
  ::= THINK_OPEN think_body THINK_CLOSE ;

intent_block
  ::= INTENT_OPEN json_payload INTENT_CLOSE ;

intent_complete_block
  ::= INTENT_COMPLETE_OPEN json_payload INTENT_CLOSE ;

action_block
  ::= ACTION_OPEN json_payload ACTION_CLOSE ;

file_content_block
  ::= FILE_CONTENT_OPEN raw_file_content FILE_CONTENT_CLOSE ;

marker
  ::= MEMORY_UPDATE_DONE ;

plaintext_response
  ::= plaintext_tail ;
```

## Semantic notes in grammar doc

Document separately from syntax:

```text
- FILE_CONTENT_BLOCK is semantically allowed only when paired with write-like action.
- READ_ONLY_BATCH_CANDIDATE is semantically allowed only when all actions are read-only, no intent block exists, and existing batch policy permits it.
- INTENT_ACTION_OUTPUT is atomic and requires exactly one action.
- Intent/action bundle rejects action arrays and multiple action blocks.
- Visible text mixed with action/control is invalid unless it is the defined intent-complete-with-text shape.
- Protocol-looking tags inside inline code/fenced code/plain documentation are literals, not structural blocks.
```

## Parser generator decision

Generated parser is optional.

Recommended path:

```text
Phase 1:
  write formal grammar doc + ProtocolSpec

Phase 2:
  implement custom markdown-aware streaming lexer and small parser over clean tokens

Later:
  if parser grows too complex, move to Lark/ANTLR using the grammar
```

Do not require Lark/ANTLR in the first implementation unless it clearly reduces complexity.

Acceptance:

```text
- Grammar document exists.
- Grammar explicitly separates syntax from semantic/runtime validation.
- Grammar explicitly documents batch vs bundle distinction.
- Grammar explicitly documents markdown/code literal handling as lexer responsibility.
```

---

# Phase 2: Markdown-aware streaming lexer

## Goal

Create a lexer that produces protocol tokens and literal/text tokens with spans.

This can be implemented as a single-pass scanner over the full response string. It does not need true incremental token streaming yet.

Do not use a generic XML parser as the core parser.

## Token/event model

Implement events/tokens equivalent to:

```python
@dataclass(frozen=True)
class Span:
    start: int
    end: int
    excerpt: str

@dataclass(frozen=True)
class StartTag:
    name: str
    attrs: dict[str, str]
    span: Span

@dataclass(frozen=True)
class EndTag:
    name: str
    span: Span

@dataclass(frozen=True)
class SelfClosingTag:
    name: str
    attrs: dict[str, str]
    span: Span

@dataclass(frozen=True)
class TextToken:
    text: str
    span: Span

@dataclass(frozen=True)
class InlineCodeToken:
    text: str
    span: Span

@dataclass(frozen=True)
class FencedCodeToken:
    lang: str | None
    text: str
    span: Span
```

Names can differ.

## Structural tag recognition

Use the ProtocolSpec block whitelist.

A protocol tag should be structural only when:

```text
- not inside fenced code;
- not inside inline code;
- not inside file_content raw mode;
- tag name is whitelisted by ProtocolSpec;
- tag appears at a structural boundary.
```

Initial structural boundary rule can be conservative:

```text
- beginning of response; or
- after a newline with only whitespace before the tag; or
- immediately after a previous protocol block end/marker.
```

This means:

```xml
<action>{"type":"read_file","path":"x"}</action>
```

is structural.

But:

```markdown
Тег `<action>` означає tool call.
```

is literal.

And:

```markdown
У тексті <action> не на початку структурного рядка.
```

should not become a real action block.

If this boundary rule is too strict for existing valid outputs, adjust carefully and add fixtures.

## Lexer modes

Implement modes conceptually:

```text
TOP_LEVEL
IN_INLINE_CODE
IN_FENCED_CODE
IN_THINK
IN_INTENT
IN_ACTION
IN_FILE_CONTENT_RAW
```

Important behavior:

```text
IN_FILE_CONTENT_RAW:
  read raw content until structural closing </file_content>;
  do not tokenize tags/code inside;
  preserve raw body exactly.

IN_FENCED_CODE / IN_INLINE_CODE:
  protocol-looking tags become literal tokens, not StartTag/EndTag.

IN_INTENT / IN_ACTION:
  capture raw JSON payload until closing tag;
  JSON parse happens after extraction.
```

## file_content delimiter

Define and document delimiter rule.

Recommended:

```xml
<file_content>
raw body
</file_content>
```

The closing `</file_content>` should be recognized only at a structural boundary, preferably start of line with optional whitespace. This reduces accidental closing inside raw code.

Acceptance:

```text
- Lexer recognizes structural tags with spans.
- Lexer ignores protocol-like tags inside inline code and fenced code.
- Lexer preserves file_content raw body.
- Lexer does not require the whole response to be valid XML.
- Tests cover markdown/code/file_content edge cases.
```

---

# Phase 3: Strict parser over lexer tokens

## Goal

Build a strict syntax parser that consumes lexer tokens and emits AST or typed parse ErrorValue.

The parser should follow the formal grammar from Phase 1 and ProtocolSpec from Phase -1.

## AST model

Implement a model equivalent to:

```python
@dataclass(frozen=True)
class ResponseAst:
    nodes: list["Node"]
    raw: str

@dataclass(frozen=True)
class Node:
    span: Span

@dataclass(frozen=True)
class ThinkNode(Node):
    content: str

@dataclass(frozen=True)
class MemoryNode(Node):
    tag: str
    attrs: dict[str, str]
    content: str | None

@dataclass(frozen=True)
class SubgoalNode(Node):
    action: str | None
    attrs: dict[str, str]
    content: str | None

@dataclass(frozen=True)
class MarkerNode(Node):
    pass

@dataclass(frozen=True)
class IntentNode(Node):
    mode_attr: str | None
    raw_payload: str
    json_payload: dict | None
    json_error: str | None

@dataclass(frozen=True)
class ActionNode(Node):
    raw_payload: str
    json_payload: object | None
    json_error: str | None

@dataclass(frozen=True)
class FileContentNode(Node):
    content: str

@dataclass(frozen=True)
class VisibleTextNode(Node):
    text: str

@dataclass(frozen=True)
class LiteralProtocolTagNode(Node):
    text: str
    context: str
```

Exact names can differ.

## Parser responsibilities

Parser validates syntax:

```text
- block boundaries are balanced;
- `<think>` is closed;
- protocol blocks do not have malformed nesting;
- marker syntax is exact;
- intent/action blocks have extractable payload;
- intent/action payload JSON parse is attempted and errors are captured;
- file_content has a closing delimiter;
- no ambiguous tag structure.
```

Parser does NOT validate runtime semantics:

```text
- whether action is allowed;
- whether intent is required;
- whether read-only batch policy allows batch;
- whether intent transition is valid in current state;
- whether plan board is stale.
```

## Typed ErrorValue

Create typed parser errors using a shared structure.

```python
@dataclass(frozen=True)
class ErrorValue:
    code: str
    phase: Literal["lex", "parse", "shape", "lowering", "semantic", "transaction"]
    severity: Literal["recoverable", "fatal"]
    message: str
    span: Span | None
    offending_node_kind: str | None
    expected: list[str]
    actual: str | None
    invalid_part: str | None = None
    transaction_applied: bool = False
    action_dispatched: bool = False
    recovery_id: str | None = None
    repeat_fingerprint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

Use Result-style returns for model output errors:

```text
Ok(ResponseAst) | Err(ErrorValue)
```

Do not use exceptions as normal control flow for model mistakes. Internal impossible states may still raise exceptions.

## Required parse error codes

At minimum:

```text
E_UNCLOSED_THINK
E_ACTION_INSIDE_THINK
E_INTENT_INSIDE_THINK
E_FILE_CONTENT_INSIDE_THINK
E_MEMORY_TAG_INSIDE_THINK
E_ACTION_JSON_INVALID
E_INTENT_JSON_INVALID
E_FILE_CONTENT_UNCLOSED
E_AMBIGUOUS_PROTOCOL_SYNTAX
```

Acceptance:

```text
- Parser consumes lexer tokens and emits AST.
- Parser returns typed ErrorValue with span.
- Parser tests cover all fixture parse cases.
- Existing runtime behavior is not replaced yet unless explicitly intended.
```

---

# Phase 4: Run grammar/AST compiler in shadow mode

## Goal

Run the new lexer/parser beside the legacy pipeline and log disagreements.

Do not replace behavior yet.

For every model response:

```text
legacy_result = current_runtime_classification(raw)
compiler_result = new_parser_and_shape_classifier(raw)
```

Log if they disagree:

```json
{
  "legacy_invalid_kind": "malformed_incomplete_think",
  "compiler_phase": "shape",
  "compiler_code": "E_MIXED_VISIBLE_TEXT_AND_CONTROL",
  "compiler_shape": "INVALID",
  "span_excerpt": "Перепрошую...",
  "shadow_only": true
}
```

Acceptance:

```text
- Shadow parser runs without side effects.
- Disagreements are logged with enough evidence to debug.
- No behavior change yet.
```

---

# Phase 5: ResponseShape classifier over AST

## Goal

Classify AST into one canonical response shape. This removes stage disagreement where multiple components interpret raw text differently.

## Response shapes

Implement equivalent to:

```python
class ResponseShape(Enum):
    PLAINTEXT_ONLY = "plaintext_only"
    MEMORY_TEXT = "memory_text"
    ACTION_ONLY = "action_only"
    READ_ONLY_BATCH_CANDIDATE = "read_only_batch_candidate"
    INTENT_ONLY = "intent_only"
    INTENT_ACTION_BUNDLE = "intent_action_bundle"
    INTENT_COMPLETE_WITH_TEXT = "intent_complete_with_text"
    INVALID = "invalid"
```

Use ProtocolSpec shape definitions where possible.

## Initial valid shapes

Keep protocol conservative. Do not expand model freedom yet.

Allowed:

```text
1. Plain final answer only.
2. Optional single leading think, optional memory/subgoal review, marker, then plain final answer.
3. Optional single leading think, optional memory/subgoal review, marker, then exactly one action.
4. Read-only batch candidate only when no intent block exists.
5. Exactly one intent only.
6. Exactly one intent followed by exactly one action and required file_content if needed.
7. Intent complete followed by final plaintext answer.
```

Rejected at shape level:

```text
- visible prose before action/intent/control protocol;
- visible prose mixed with action protocol;
- action arrays where a single action object is required;
- multiple action blocks inside an intent/action bundle;
- file_content without an action;
- file_content not associated with a write-like action;
- think after intent/action/visible answer;
- protocol tags inside open think.
```

Important:

```text
Valid node != valid response.

Parser can build an ActionNode.
Shape validator can still reject VisibleTextNode + ActionNode.
```

## Batch vs bundle

Hard distinction:

```text
Read-only action batch:
  candidate shape only when there is NO intent block.

Intent/action bundle:
  exactly one intent + exactly one action.
  no action arrays.
  no multiple action blocks.
```

Acceptance:

```text
- Shape classifier consumes AST only.
- No shape classifier stage scans raw text.
- Mixed visible/control is detected from AST with specific ErrorValue.
- Protocol tag literals in markdown/code do not create control blocks.
```

---

# Phase 6: AST → IR lowering

## Goal

Introduce typed Intermediate Representation after AST.

AST answers:

```text
What did the model write?
```

IR answers:

```text
What is the runtime proposal represented by this response?
```

Do not skip directly from AST to executor.

## IR model

Conceptual structure:

```python
@dataclass(frozen=True)
class ResponseIR:
    shape: ResponseShape
    annotations: list[AnnotationIR]       # think/debug only
    board_ops: list[BoardOpIR]
    intent_ops: list[IntentOpIR]
    action_ops: list[ActionOpIR]
    visible_answer: str | None
    file_content: str | None
    effects_preview: list[EffectPreview]
```

Example IR nodes:

```python
ActivateIntentIR(...)
ReuseIntentIR(...)
ReplaceIntentIR(...)
CompleteIntentIR(...)
ToolActionIR(...)
WriteFileActionIR(...)
FinalAnswerIR(...)
MemoryOpIR(...)
SubgoalOpIR(...)
```

Important:

```text
ThinkNode must not become a runtime effect.
ThinkNode is annotation/debug only.
```

## Lowering rules

Examples:

```text
AST: ThinkNode + IntentNode + ActionNode + FileContentNode
→ IR: IntentActionBundleProposal

AST: ActionNode + ActionNode
→ IR: ReadOnlyBatchCandidate

AST: IntentCompleteNode + VisibleTextNode
→ IR: IntentCompletionWithFinalAnswer

AST: VisibleTextNode only
→ IR: FinalAnswer
```

Lowering should be a pure function:

```text
ResponseAst + ResponseShape -> Result[ResponseIR, ErrorValue]
```

Acceptance:

```text
- IR layer exists.
- Think is annotation only.
- No side effects happen during lowering.
- IR represents runtime proposal clearly.
```

---

# Phase 7: Semantic validators over IR + state

## Goal

Move semantic validation from raw text/legacy segment parsing to IR/ResponseShape.

Each pass should be a pure function as much as possible:

```text
IR -> Result[IR, ErrorValue]
IR + CurrentRuntimeState -> Result[ValidatedIR, ErrorValue]
```

## Validators to migrate

Start with high-impact validators:

```text
- formal intent required
- intent-only activation
- reuse without active intent
- replace/complete rules
- intent mode XML/body mismatch
- action allowed by active/proposed intent
- create/write action file_content pairing
- action payload array
- multiple actions
- mixed visible text + action/control
- intent complete + final answer
```

## Formal intent required

If action requires formal intent and no active contract exists, recovery should be consistent with atomic bundle policy:

```text
Return a valid formal intent before the action.

You may either:
1. Return only one <intent mode="activate">...</intent>, then wait for acceptance.
2. Or return an atomic bundle: one <intent mode="activate">...</intent> followed by exactly one valid <action>...</action> and required <file_content> if the action needs it.
```

Do not use old contradictory wording:

```text
Return EXACTLY ONE <intent> JSON block first.
If you also need an action now, place the <intent> block before the action.
```

Do not use strict intent-only wording for normal formal-intent-required recovery unless escalation or an explicitly strict recovery mode is active.

## Strict-only exceptions

Strict intent-only recovery is still allowed for ambiguity/repeated failures:

```text
- conflicting intent transitions
- multiple intent blocks where only one transition is allowed
- malformed/nested intent XML
- repeated reuse without active intent
- repeated atomic bundle action-shape error after escalation
- explicit runtime state says transition-only recovery is required
```

Acceptance:

```text
- Validators use IR/AST/shape rather than raw scans.
- Old contradictory recovery wording is removed or unreachable.
- Intent/action bundle policy is consistent.
```

---

# Phase 8: Transaction planner, effect preview, and executor

## Goal

Ensure all side effects happen only after full validation.

No stage should mutate runtime state directly from AST nodes or raw text.

## Execution model

```text
ResponseIR
→ ValidatedIR
→ ExecutionPlan
→ EffectPreview
→ Commit
```

Conceptual plan:

```python
@dataclass(frozen=True)
class ExecutionPlan:
    shape: ResponseShape
    state_effects: list[StateEffect]
    action_effects: list[ActionEffect]
    output_effects: list[OutputEffect]
    transaction_kind: str
```

## Atomic bundle invariant

```text
If response shape is INTENT_ACTION_BUNDLE:
  validate intent transition without mutating active state;
  preview post-transition state;
  validate exactly one action under proposed state;
  validate file_content pairing if needed;
  if all valid:
    plan transition + action dispatch;
  else:
    plan nothing and return ErrorValue.
```

## Required trace fields

For every bundle success/failure, trace must explicitly include:

```text
bundle_validated: true|false
invalid_part: intent|action|file_content|mixed_visible|None
bundle_reason: ...
transition_applied: true|false
active_intent_unchanged: true|false
action_dispatched: true|false
after_active_intent_id: ...
before_active_intent_id: ...
```

Do not leave `transition_applied: None` on rejected bundle. It should be `false`.

## Runtime assertions

Add impossible-state assertions or invariant checks:

```python
assert not (error and action_dispatched)
assert not (invalid_bundle and transition_applied)
assert not (rejected_intent and active_intent_changed)
assert not (visible_control_error and dispatch)
```

These should be testable. If production behavior cannot raise, log a P0 invariant breach.

## Tests

```text
1. valid intent/action/write_file_block/file_content bundle
   Expected:
   - transition_applied=true
   - action_dispatched=true

2. valid intent but action type not allowed by proposed intent
   Expected:
   - transition_applied=false
   - active_intent unchanged
   - action_dispatched=false
   - invalid_part=action

3. invalid intent followed by otherwise valid action
   Expected:
   - transition_applied=false
   - active_intent unchanged
   - action_dispatched=false
   - invalid_part=intent

4. write action missing file_content
   Expected:
   - transition_applied=false
   - active_intent unchanged
   - action_dispatched=false
   - invalid_part=file_content

5. intent + action JSON array
   Expected:
   - transition_applied=false
   - no dispatch
   - invalid_part=action
   - bundle_reason=atomic_bundle_requires_exactly_one_action

6. intent + two action blocks
   Expected:
   - same as above

7. no intent + valid read-only batch, after narrowed search, if existing policy allows it
   Expected:
   - not rejected as bundle
   - handled by read-only batch policy

8. intent + read-only batch
   Expected:
   - rejected as invalid atomic bundle
```

Acceptance:

```text
- Invalid bundle never mutates active intent.
- Invalid bundle never dispatches action.
- Valid bundle applies transition and dispatches exactly once.
- Trace makes no-op explicit.
- Only executor commits side effects.
```

---

# Phase 9: RecoveryStrategy registry

## Goal

Replace ad hoc recovery prompt strings with a strategy registry:

```text
ErrorValue.code / recovery_id → RecoveryStrategy
```

Recovery component must not parse raw model output and must not know parser internals. It only receives ErrorValue and strategy context.

## RecoveryStrategy model

```python
@dataclass(frozen=True)
class RecoveryStrategy:
    id: str
    error_codes: list[str]
    allowed_next_shapes: list[str]
    forbidden_next_patterns: list[str]
    message_template: str
    escalation: EscalationSpec | None
    example_policy: ExamplePolicy
```

ExamplePolicy should prevent stale examples:

```python
ExamplePolicy(
    mode="contextual_or_neutral",
    forbidden_terms=["fix_ksp_build_error"],
    prefer_intent_type_from_task=True,
)
```

## Template contract

Each strategy should define and test:

```text
- must_include fragments
- must_not_include fragments
- allowed next shapes
- forbidden next shapes
- whether to mention transaction no-op
- whether to escalate after repeats
```

### Mixed visible/control

For:

```text
E_MIXED_VISIBLE_TEXT_AND_CONTROL
```

Recovery meaning:

```text
Your response mixed a user-visible answer with internal protocol/tool use.
Choose exactly one:
1. Return only final plain-text answer, with no <think>, <intent>, <action>, or other control tags.
2. Or return internal protocol only: optional <think>, memory/subgoal tags if needed, <memory_update_done />, then intent/action protocol if needed.

Do not put visible prose before internal protocol.
```

Must not say:

```text
malformed action JSON
unclosed think
```

unless that is the actual ErrorValue.

### Action array inside atomic bundle

For:

```text
E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION
```

Recovery meaning:

```text
Your atomic intent/action bundle is invalid because the action part contains multiple actions or an action array.

Atomic intent/action bundles require exactly one action:
<intent mode="activate">...</intent>
<action>{ one JSON object }</action>

The entire bundle was rejected:
- no intent was activated;
- no action was dispatched.

Return a corrected response from the beginning:
- either one valid <intent mode="activate">...</intent> only;
- or one valid atomic bundle with exactly one <action>.
Do not return an action array.
Do not return multiple <action> blocks.
Do not include visible final answer text in the same response as an action.
```

### Unclosed think

For:

```text
E_UNCLOSED_THINK
```

Recovery meaning:

```text
Your response opened <think> but did not close it before later output.
<think> may contain draft reasoning, but it must be closed with </think> before any memory tag, subgoal tag, marker, intent, action, file_content, or visible answer text.
Return the corrected response from the beginning.
```

### Ambiguous protocol syntax

For:

```text
E_AMBIGUOUS_PROTOCOL_SYNTAX
```

Recovery meaning:

```text
Your response contains protocol-like tag text in a position ambiguous to the protocol parser.
Return either:
1. plain answer only, with protocol tag names escaped or inside safe code text;
2. or real protocol blocks only, with no visible prose.
```

Prefer parser improvements over asking the model to escape everything, but keep this error for genuinely ambiguous cases.

## Snapshot tests

Add recovery snapshot tests.

For each important ErrorValue, assert:

```text
- required fragments are present
- forbidden stale/wrong fragments are absent
- recovery_id is stable
```

Acceptance:

```text
- No ad hoc recovery strings for covered errors.
- Recovery uses ErrorValue only.
- Wrong root-cause recovery is prevented by tests.
- Recovery strategy can control next allowed shapes.
```

---

# Phase 10: Loop escalation by protocol fingerprint

## Goal

Stop repeated recovery loops for the same protocol shape error.

## Fingerprint

Create a repeat fingerprint from:

```text
ErrorValue.code
ErrorValue.invalid_part
ErrorValue.actual
ErrorValue.recovery_id
ResponseShape or candidate shape
bundle_reason if any
```

Examples:

```text
E_ATOMIC_BUNDLE_REQUIRES_EXACTLY_ONE_ACTION|action|array|INTENT_ACTION_BUNDLE
E_MIXED_VISIBLE_TEXT_AND_CONTROL|shape|VISIBLE+ACTION
E_UNCLOSED_THINK|parse|think
```

## Escalation policy

```text
First occurrence:
  normal recovery

Second same fingerprint:
  stricter recovery, fewer allowed shapes

Third same fingerprint:
  stop/handoff with concise explanation, or force safest shape if runtime supports it
```

For repeated atomic bundle action-shape error:

```text
1st:
  explain exactly-one-action bundle

2nd:
  force intent-only:
  Return only one <intent mode="activate">...</intent>.
  Do not include <action>, <file_content>, visible text, or multiple blocks.

3rd:
  stop/handoff or final diagnostic depending on current runtime policy
```

Acceptance:

```text
- Same protocol shape error does not loop indefinitely.
- Recovery becomes stricter after repeat.
- Trace logs repeat_count and escalation level.
```

---

# Phase 11: Observable compiler pipeline and replay

## Goal

Make response compilation/debugging observable and replayable.

Current dumps are useful but too late and too coarse. Add structured trace for each compiler stage.

## Pipeline stages

```python
pipeline = Pipeline([
    Lexer(),
    Parser(),
    ShapeValidator(),
    LoweringPass(),
    SemanticValidator(state),
    TransactionPlanner(),
    Executor(),
], observers=[
    LoggingObserver(),
    MetricsObserver(),
    ReplayObserver(),
])
```

Exact names can differ.

## Replay artifact

For each model response, optionally record:

```json
{
  "raw_excerpt": "...",
  "tokens": [...],
  "ast": [...],
  "shape": "INTENT_ACTION_BUNDLE",
  "ir": {...},
  "error": null,
  "plan": {...},
  "commit": {...}
}
```

For errors:

```json
{
  "raw_excerpt": "...",
  "tokens": [...],
  "ast": [...],
  "shape": "INVALID",
  "error": {
    "code": "E_MIXED_VISIBLE_TEXT_AND_CONTROL",
    "phase": "shape",
    "span": {...},
    "recovery_id": "mixed_visible_control"
  }
}
```

Optional but useful:

```text
- Mermaid visualization of AST/IR for dev logs;
- span excerpts in dump;
- old-vs-new diagnosis comparison while shadow mode is active.
```

Acceptance:

```text
- A failed response can be replayed through lexer/parser/shape/IR/semantic stages.
- Dumps include compiler diagnosis and spans.
- Observability has no side effects on runtime behavior.
```

---

# Phase 12: Plan board / memory board lineage hardening

## Goal

Prevent stale plan/subgoal board from leaking across intent lineage.

## Plan board invariant

Plan board must be scoped to active intent lineage.

Conceptual model:

```python
@dataclass
class PlanBoard:
    intent_id: str
    lineage_id: str
    subgoals: list[Subgoal]
```

Hard rules:

```text
on intent complete:
  close or clear plan board for that intent_id

on new activate with different intent_id:
  start with empty plan board

on reuse of same intent lineage:
  keep board

on replace:
  clear board unless transition explicitly transfers selected subgoals

when injecting plan board:
  if plan_board.intent_id != active_intent.intent_id:
    do not inject it
    log stale_plan_board_suppressed
```

## Memory distinction

Do not rely on model-generated memory tags for routine operational events.

Prefer this split eventually:

```text
SemanticMemory:
  model-authored facts/findings/decisions

OperationalJournal:
  runtime-authored actions attempted/succeeded/failed, files changed, recoveries issued, intent transitions
```

If full split is too large, at least ensure routine action success is recorded by runtime journal/history, not forced through model memory tags.

## Prompt wording

Replace unsafe memory wording:

```text
CRITICAL: Omitting memory tags after a <think> block is a protocol violation.
Mandatory Emission: AFTER every <think> ...
```

with:

```text
If you open <think>, close it with </think> before memory/subgoal review.
Only after </think>, emit memory/subgoal tags if durable state changed.
If no durable state changed, emit <memory_update_done /> alone.
Never place memory tags, subgoal tags, <memory_update_done />, <intent>, <action>, or <file_content> inside <think>.
Do not invent memory tags only because <think> exists.
```

For routine tool success:

```text
Do not emit memory tags for routine successful tool usage unless the resulting path/state must survive compression.
If saving a user-requested artifact and recording progress, include WHERE path and WHAT was saved.
```

Acceptance:

```text
- New intent does not receive old plan board.
- Completed intent clears or closes plan board.
- Memory prompt no longer requires tags solely because `<think>` exists.
- Routine action success does not require model-authored memory tag.
```

---

# Phase 13: Think/file_content discipline

## Goal

Reduce protocol breakage caused by large drafts inside `<think>`.

Do not introduce style/length validation for closed think.

Do add behavioral prompt guidance:

```text
<think> is a draft reasoning workspace, but do not draft large file bodies inside <think>.
For write-like actions, keep <think> to the decision/path/format choice.
Put the final raw file body only in <file_content>.
Do not copy long markdown/code intended for write_file_block into <think>.
```

Parser should still accept long closed think if structurally valid.

Semantic validator should reject only real structural violations:

```text
- unclosed think
- real protocol blocks inside open think
- nested ambiguous think if unsupported
```

Acceptance:

```text
- Long closed think is not rejected for style/length.
- Large file body guidance exists in prompt.
- Real unclosed think remains invalid.
- Real action/intent inside open think remains invalid.
```

---

# Phase 14: Correction-aware investigation behavior

## Goal

When user says the previous answer misunderstood the architecture, the agent should not answer again from partial evidence.

Triggers include:

```text
ти не зрозумів
не це
я мав на увазі
а як взагалі
це специфічна штука
```

Runtime/prompt should lower trust in previous answer:

```text
previous_answer_trust = low
must_target_new_entity = true
do_not_answer_from_previous_partial_evidence = true
```

For architecture “how to create/register X” questions, require evidence coverage before final answer.

Suggested coverage heuristic:

```text
- one core definition/interface file
- one registry/bootstrap/DI file
- one existing implementation/example
- one UI/view integration file if the question mentions view
```

Do not over-generalize; this is for architecture-how-to answers after user correction or explicit request to inspect code.

Acceptance:

```text
- After “ти не зрозумів”, agent performs targeted investigation of newly clarified entity.
- It does not immediately produce confident answer from previous partial evidence.
```

---

# Phase 15: Golden corpus + property/metamorphic tests

## Goal

Stop whack-a-mole by testing grammar space, not just individual dumps.

Use ProtocolSpec to drive test generation where practical.

## Property tests

Generate variants across dimensions:

```text
- think present/absent
- think closed/unclosed
- intent present/absent
- action object/action array
- one action/two actions
- file_content present/missing/orphan
- visible text before/after control
- protocol tags in inline code
- protocol tags in fenced code
- memory tags before/after marker
```

Assert invariants:

```text
- visible text before action never dispatches
- action array in bundle never applies intent
- tag literals inside markdown never create control nodes
- real action inside open think is invalid
- valid bundle has exactly one action
- missing file_content for write-like action rejects
```

## Metamorphic tests

Base:

```text
Ось відповідь.
```

Transform:

```text
Ось відповідь. У документації тег `<action>` означає дію.
```

Expected:

```text
still PLAINTEXT_ONLY
no ActionNode
no dispatch
```

Fenced example transform:

````markdown
```xml
<action>{"type":"read_file","path":"x"}</action>
```
````

Expected:

```text
still visible/code example
no ActionNode
no dispatch
```

## Fixture-to-regression workflow

Every new dump-derived bug should become:

```text
- fixture raw response
- expected AST/shape/error
- expected recovery_id
- expected transaction flags
```

Acceptance:

```text
- Core recurring protocol bugs are covered by fixture/property/metamorphic tests.
- New parser/compiler changes run against corpus.
- ProtocolSpec is used to avoid drift between rules and tests where practical.
```

---

# Phase 16: Gradual rollout

## Goal

Avoid risky full rewrite.

## Rollout plan

### Step A: Shadow grammar/AST compiler

```text
Run lexer/parser/classifier in parallel.
Log old vs new diagnosis disagreements.
Do not alter runtime behavior.
```

### Step B: Use compiler diagnosis for syntax/shape errors only

Switch these first:

```text
- unclosed think
- real protocol block inside think
- visible text + control/action
- tag literals in markdown/plain text
- action array
- multiple actions
- file_content pairing
```

### Step C: Use AST/shape/IR for atomic bundle validator

Switch:

```text
- intent/action bundle shape
- exactly one action
- file_content requirement
- no transition on invalid bundle
```

### Step D: Move semantic validators

Switch:

```text
- formal intent required
- action allowed by active/proposed intent
- reuse without active intent
- intent mode mismatch
```

### Step E: Execution planner

Eventually replace stage-by-stage side effects with:

```text
AST/shape
→ IR
→ semantic validation
→ ExecutionPlan
→ transaction commit
```

### Step F: Optional parser generator/codegen

Only after grammar and lexer boundaries are stable:

```text
- evaluate Lark/ANTLR/textX/pyparsing;
- do not force generator if hand-written parser remains simpler;
- consider generating docs/tests/recovery skeletons from ProtocolSpec first;
- consider parser generation only if custom parser grows complex.
```

Acceptance:

```text
- Each phase can be merged independently.
- Current behavior is preserved unless explicitly replaced by tested compiler diagnosis.
- No broad rewrite required.
```

---

# Required final report per phase

When done with each phase, report:

```text
- which phase was implemented
- whether ProtocolSpec was extended
- whether grammar is documented or generator-backed
- whether parser is hand-written or generated, and why
- which new AST/ErrorValue/ResponseShape/IR types were added
- which legacy behavior remains
- which invalid kinds are now compiler-driven
- which recovery strategies are ErrorValue-driven
- tests added
- whether any old/new diagnosis disagreements remain in shadow mode
- known non-goals or deferred semantic validators
```

---

# Final acceptance criteria for the full effort

The effort is complete when:

```text
1. ProtocolSpec exists as a machine-readable first-class artifact.
2. Formal grammar for Angelica response protocol exists.
3. Raw model output is lexed with markdown/code/file_content-aware modes.
4. Raw model output is parsed once into AST before validation.
5. Real protocol tags are distinguished from literal tag mentions in markdown/code/prose.
6. Parser returns typed syntax errors with spans.
7. Shape validator returns typed shape errors.
8. AST lowers into typed IR representing runtime proposals.
9. Semantic validator works from IR/AST/ResponseShape, not raw text scans.
10. Atomic intent/action bundle is all-or-nothing.
11. Rejected bundle explicitly logs transition_applied=false and action_dispatched=false.
12. Recovery strategies are rendered from ErrorValue, not ad hoc parser/stage strings.
13. Repeated same protocol defect escalates to stricter shape.
14. Plan board is scoped to intent lineage and cannot leak into unrelated intent.
15. Memory prompt no longer requires tags solely because `<think>` exists.
16. Fixture/property/metamorphic tests cover recurring protocol bugs.
17. Existing external model protocol remains unchanged.
18. Only validated ExecutionPlan may mutate runtime state or dispatch actions.
```

## One-sentence architecture target

Keep the current XML-like model protocol, but internally treat it as a small programming language:

```text
source text → ProtocolSpec-aware lexer → formal parser → AST → shape validator → IR lowering → semantic validator → transaction plan → executor
```

and treat recovery as compiler diagnostics plus strategy:

```text
ErrorValue → RecoveryStrategy → deterministic recovery prompt
```
