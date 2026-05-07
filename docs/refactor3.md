Так, це **правильний наступний великий напрям**, але я б не називав це просто “compiler migration”. Це вже наступна фаза:

```text id="gf3btx"
legacy semantic extraction
→ compiler AST
→ compiler IR
→ runtime decisions consume IR snapshots
```

Тобто ми зараз мігрували **authority for structural diagnostics**, а наступний рівень — мігрувати **semantic understanding**: `has_action`, `action_count`, `visible_answer`, `intent_ops`, `memory/subgoal ops`, `effects_preview`, etc.

## Чому це варто робити

Зараз у shadow tests часто бачимо mismatches типу:

```text id="7k5oe8"
legacy has_visible_answer=True
compiler has_visible_answer=False
```

Для invalid protocol responses це ок, але для valid responses нам треба поступово зробити compiler IR canonical, бо legacy regex/parser семантика слабка.

Ціль:

```text id="yohqbl"
compiler AST/IR = source of truth for protocol semantics
legacy = fallback / shadow / compatibility
```

Але не для policy decisions.

## Важлива межа

IR може стати authority для:

```text id="r88c25"
- action_count
- action payload extraction
- visible_text extraction
- pre_action_text
- file_content pairing
- intent ops extraction
- memory/subgoal op extraction
- effects_preview
- structural invalid reasons
```

IR **не має** ставати authority для:

```text id="awaaqj"
- чи action дозволений active intent-ом
- чи доказів достатньо
- чи final answer правильний
- чи subgoal mark_done валідний
- чи search low-value
- чи dispatch має виконатись
```

## Як це робити безпечно

Не “перемкнути все на IR”, а додати **SemanticSnapshot / RuntimeProtocolIR adapter** і мігрувати consumer-и по одному.

Я б почав з audit:

```text id="rt1wmo"
Task:
Audit migration of runtime semantic extraction from legacy parser fields to compiler AST/IR.

Context:
We completed structural compiler authority migration:
- ProtocolDecisionBridge owns precise structural diagnostics
- ACTION_ONLY / PLAINTEXT_ONLY / INTENT_ACTION_BUNDLE broad shape authority remains runtime-governed
- compiler owns structure; runtime owns policy

Next phase:
Move protocol semantic extraction toward compiler AST/IR.

Goal:
Audit where runtime currently uses legacy ParsedModelOutput fields that could be sourced from compiler IR instead.

Do not change behavior yet.

Key distinction:
Compiler IR may become authoritative for protocol semantics:
- has_action_segment
- action_count
- action payloads
- visible_text / visible_answer
- pre_action_text
- intent_ops
- memory/subgoal operations
- file_content
- effects_preview

Runtime remains authoritative for policy:
- ActionPolicy
- evidence sufficiency
- final answer correctness
- intent completion
- subgoal validation
- search narrowing
- dispatch side effects

Tasks:
1. Search for legacy semantic fields:
   - has_action_segment
   - action_segment
   - action_count
   - visible_text
   - visible_answer
   - has_visible_answer
   - intent_payload
   - intent_error
   - memory_update_done
   - subgoal
   - plan_board
   - action_segments
   - ParsedModelOutput
   - compiler_ir
   - effects_preview
   - protocol_shadow
   - get_legacy_semantics
   - get_compiler_semantics

2. Inventory consumers by stage:
   A. response_pipeline_stages.py
   B. output_recovery_routing.py
   C. response_pipeline_prevalidation.py
   D. intent_transition_routing.py
   E. plan_board / memory_board stages
   F. dispatch_pipeline.py
   G. tests/golden semantic shadow

For each consumer document:
   - field currently read
   - legacy source
   - compiler IR equivalent if any
   - risk of switching
   - test coverage
   - recommended migration order

3. Propose an adapter design:
   RuntimeProtocolSemantics or ProtocolSemanticSnapshot

It should be built from compiler analysis when available and expose:
   - shape
   - is_valid
   - error_code
   - recovery_id
   - action_count
   - action_ops
   - intent_ops
   - visible_text
   - has_visible_answer
   - pre_action_text
   - memory_ops
   - subgoal_ops
   - file_content
   - effects_preview

4. It should preserve legacy fallback:
   - if compiler_ir missing or invalid for a field, fallback to ParsedModelOutput legacy fields
   - log protocol_shadow disagreement where useful

5. Add docs only:
   "Compiler IR Semantic Migration Plan"
   with phased migration:
   Phase 1: add adapter + tests, no behavior change
   Phase 2: read-only consumers use adapter
   Phase 3: output recovery uses adapter for structural semantics
   Phase 4: intent/memory/subgoal extraction migrate carefully
   Phase 5: legacy semantic parser becomes fallback/shadow only

6. Do not change behavior.
7. Do not change ProtocolDecisionBridge authority.
8. Do not change parser/classifier unless audit finds a missing IR field.
9. Do not touch prompts or runtime policy.

Run:
grep -R "has_action_segment\|action_segment\|action_count\|visible_text\|visible_answer\|has_visible_answer\|intent_payload\|intent_error\|memory_update_done\|subgoal\|plan_board\|action_segments\|ParsedModelOutput\|compiler_ir\|effects_preview\|protocol_shadow\|get_legacy_semantics\|get_compiler_semantics" -n modules/agent/orchestration tests docs

pytest tests/golden/responses/test_semantic_shadow.py \
       tests/test_protocol_compiler_pipeline.py \
       tests/test_protocol_compiler_runtime_integration.py \
       tests/test_protocol_decision_bridge.py

pytest -q tests
```

## Мій рекомендований перший real implementation після audit

Не міняти pipeline одразу. Спершу додати окремий модуль:

```text id="8hxwcm"
modules/agent/orchestration/responses/protocol_semantics.py
```

з функцією:

```python id="6dy0xg"
build_protocol_semantics(parsed_output) -> ProtocolSemanticSnapshot
```

і snapshot dataclass:

```python id="k9ojx5"
@dataclass(frozen=True)
class ProtocolSemanticSnapshot:
    source: str  # compiler | legacy | mixed
    shape: str
    is_valid: bool
    error_code: str
    recovery_id: str
    action_count: int
    has_action: bool
    has_visible_answer: bool
    visible_text: str
    pre_action_text: str
    action_effects: list[str]
    intent_op_count: int
    memory_op_count: int
    subgoal_op_count: int
    has_file_content: bool
```

Спершу тільки tests/shadow:

```text id="ybqif3"
legacy snapshot vs compiler snapshot vs runtime snapshot
```

Потім consumer migration.

## Чому не одразу “IR authority”

Бо зараз IR уже добре показує structure, але semantic consumers мають різні policy assumptions. Якщо перемкнути все одразу, можна зламати:

```text id="02boyp"
- active intent transition handling
- memory/subgoal board parsing
- visible answer extraction
- recovery prompts
- dispatch plans
```

Тому правильний шлях: **adapter first, consumers later**.
