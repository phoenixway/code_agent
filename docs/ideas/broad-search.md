Так. Якщо **не чіпаємо multi-file/action-array**, тоді конкретно треба правити не recovery після broad search, а **базовий system prompt Анжеліки**, бо зараз широкий пошук усе ще “дешево доступний” як перший рефлекс.

У dump видно головний симптом: перший реальний пошук був `search_content` по кореню/без path, результат `Found 771 matches`, і перші hits пішли з `docs/` . А останній patch покращив саме recovery prompt, тобто “що робити після занадто широкого пошуку”, але не “як не зробити його першим” .

## Що саме поправити в default system prompt

### 1. У `TOOL STRATEGY → PATH & TARGET DISCOVERY PRIORITY`

Зараз там є правильна ідея:

```text
broad project-wide reconnaissance as a last resort
```

Але вона занадто м’яка. Треба додати **операційний gate** перед broad search.

Додай після priority list:

```text
### BROAD SEARCH GATE

Before using `search_content` with `path=""`, `path="."`, or another project-wide/root-like path, you MUST pass this gate:

1. No exact path, filename, source root, package, class, symbol, or previously returned candidate path is available.
2. `search_files` cannot answer the path question more cheaply.
3. A narrower source root is not obvious from the project type.
4. The search payload uses at least TWO bounding parameters:
   - specific path/source root,
   - specific exact symbol/class/function pattern,
   - `include_extensions`,
   - `exclude_dirs`,
   - `code_only: true`,
   - low `limit`.

If you cannot satisfy the gate, do not run root-level `search_content`.
Use `search_files`, `list_directory`, a source-root search, or exact read instead.
```

Це робить широкий пошук не “забороненим”, а **платним мостом із турнікетом**.

---

### 2. У `SEARCH & BATCHING PROTOCOL`

Зараз там є:

```text
Search Discipline: Narrow by default (`code_only: true`, `recursive: false`, `include_extensions`, `exclude_dirs`). If too broad → next search must narrow ≥1 parameter.
```

Це добре, але слабко: модель все одно зробила `search_content` без `path`. Треба переформулювати жорсткіше:

```text
### SEARCH_CONTENT FIELD DISCIPLINE

For `search_content`, root-level search is not the default.

Default valid `search_content` must include:
- `path`: a concrete source root or known candidate file/directory,
- `code_only: true` when looking for code,
- `include_extensions` when language is known,
- `exclude_dirs` for noisy locations.

For Android/Kotlin projects, prefer source roots such as:
- `app/src/main/java`
- `core-data-models/src/main/java`
- module `src/main/java` roots

Avoid `path=""` or `path="."` unless the BROAD SEARCH GATE is satisfied.

Docs/log/build/.git are noisy by default:
- exclude `docs`, `build`, `.git`, logs unless explicitly relevant;
- docs may suggest terms, but code must confirm claims.
```

Це напряму б’є в проблему з `docs/how_to_add_capability_guide.md` як першим hit.

---

### 3. Додати “exact symbols from user” правило

У твоєму smoke-запиті були exact anchors: `CapabilityId`, `CapabilityRegistry`, `CapabilityCatalog`, `ContextConfiguration`. Модель не мала права шукати це по всьому кореню.

Додай у `PATH & TARGET DISCOVERY PRIORITY` або `SEARCH & BATCHING PROTOCOL`:

```text
### USER-PROVIDED EXACT ANCHORS

If the user provides exact symbols, class names, filenames, package names, or known feature names, treat them as anchors.

First try:
1. `search_files` for exact filenames if the anchor looks like a file/class name.
2. `search_content` scoped to likely source roots with `include_extensions`.
3. Exact reads/skeletons if the search result returns candidate paths.

Do not start with project-root `search_content` for exact anchors unless all narrower strategies are unavailable.
```

Тут важливо: не “заборонити `search_content`”, а змусити його бути **scoped**.

---

### 4. Додати правило “candidate paths terminate reconnaissance”

Це вже є в recovery prompt, але треба в system prompt, бо recovery може не спрацювати до того, як агент витратить 2–3 кроки.

Додай:

```text
### CANDIDATE PATH STOP RULE

When any search result returns exact candidate source paths, broad reconnaissance is over.

Next action should usually be one of:
- `read_file_skeleton` on the strongest candidate,
- `read_chunk` around the matching line,
- `extract_symbol` if symbol and file are known,
- `read_file` only for small files.

Do not run another broad `search_content` unless you can name a new missing detail and narrow at least one parameter.
```

Це зробить “побачив path → читай path”, а не “побачив path → ще пошукай”.

---

### 5. У `ACTION / OUTPUT BLOCK` описі `search_content`

Там зараз просто перелік параметрів інструмента. Треба додати “shape requirements”:

```text
For `search_content`:
- prefer non-empty `path`;
- include `code_only: true` for code investigations;
- include `include_extensions` when language is known;
- include `exclude_dirs` for noisy dirs;
- set a small `limit`.

Root/project-wide search_content is allowed only as bounded reconnaissance and must satisfy the BROAD SEARCH GATE.
```

Це корисно, бо модель часто орієнтується саме на tool schema area.

---

## Мінімальний patch, який я б просив у aider

```text
Update default system prompt search discipline only.

Do not touch action array / multi-action behavior.
Do not change runtime code.
Do not change ProtocolCompiler, RuntimeProtocolSemantics, ActionPolicy, dispatch, or recovery routing.

Goal:
Make broad/root-level search_content harder to use as the first investigative reflex, while still allowing bounded reconnaissance when exact files are unknown.

Relevant file:
- modules/defaults.py
or wherever the default system prompt text is generated/stored

Also inspect:
- tests that snapshot/assert default prompt text, if any
- docs/architecture/response_protocol.md only if there is already a matching search policy section

Required prompt changes:

1. Add BROAD SEARCH GATE near TOOL STRATEGY / PATH & TARGET DISCOVERY PRIORITY:
- before search_content with path="" or path=".", model must prove no exact path/filename/source-root/symbol/candidate path is available;
- search_files cannot answer more cheaply;
- no narrower source root is obvious;
- payload uses at least two bounding parameters:
  specific path, specific pattern, include_extensions, exclude_dirs, code_only, low limit.

2. Add USER-PROVIDED EXACT ANCHORS rule:
- if user provides exact symbols/classes/files, first use search_files or scoped search_content;
- do not start with project-root search_content for exact anchors.

3. Add SEARCH_CONTENT FIELD DISCIPLINE:
- default search_content should include non-empty path, code_only true for code, include_extensions when language known, exclude_dirs for docs/build/.git/logs, and small limit.
- for Android/Kotlin, prefer app/src/main/java, core-data-models/src/main/java, or module src/main/java roots before project root.

4. Add CANDIDATE PATH STOP RULE:
- once search results expose exact source paths, broad reconnaissance is over;
- next action should usually be read_file_skeleton/read_chunk/extract_symbol/read_file on candidate paths;
- another broad search requires a named missing detail and at least one narrowed parameter.

5. Keep broad search allowed:
- do not say "never broad search";
- phrase it as "single bounded reconnaissance is allowed when exact files are unknown."

6. Add or update prompt tests:
- default prompt contains "BROAD SEARCH GATE" or equivalent;
- contains "path=\"\"" / "path=\".\"" root search warning;
- contains "exact anchors" rule;
- contains "candidate paths" -> "read_file_skeleton/read_chunk/extract_symbol";
- contains Android/Kotlin source root examples;
- contains docs/log/build/.git exclusion guidance.

Run:
pytest tests -k "default_prompt or prompt or search_narrowing or broad_search"
pytest -q tests

Show:
git diff --stat
git diff -- modules/defaults.py docs/architecture/response_protocol.md tests
```

## Ключова фраза, яку треба вшити

Ось найцінніший шматок, я б прямо вставив майже дослівно:

```text
Broad search is a reconnaissance tool, not a default first action.

Use one bounded reconnaissance search only when exact files are unknown.
A bounded search must use at least two narrowing controls: specific path/source root, specific pattern, include_extensions, exclude_dirs, code_only, or low limit.

If the user provides exact symbols/classes/filenames, do not start with project-root search_content.
Use search_files or scoped search_content first.

Once candidate source paths appear, broad reconnaissance is over.
The next action should read or inspect one candidate path.
```

Це не робить широкий пошук неможливим. Воно робить його **дорогим за умовами**, а не безкоштовною кнопкою “шукати все в усій печері”.
