Non-authoritative working note.
Canonical governance lives in docs/architecture/.
If this file conflicts with docs/architecture/*, docs/architecture wins.

1. Governance repair: done.
2. Consumer Inventory: done / approved.
3. Accessor API Design: done / approved.
4. Accessor implementation (`semantic_accessors.py` + tests): done.
5. Phase 4 first migration design (`has_any_action_proposal`): approved.
6. Phase 4 first migration implementation (`has_any_action_proposal`): done.
7. Phase 4 Batch 1 plan: approved.
8. Phase 4 Batch 1 implementation: done.
9. Fast-lane migrations complete.
10. Next accessor batch design: approved.
11. Next accessor batch implementation: done.
12. Phase 4 Batch 2 migration design: approved.
13. Phase 4 Batch 2 implementation: done.
14. Phase 4 remaining migration review: done.
15. Conclusion: Phase 4 is complete. Next: plan for Phase 5+.
16. Phase 5 design (`TransitionSemanticValidator`): approved.
17. Phase 5 Step 1 (scaffolding): done.
18. Phase 5 Step 2A (core logic migration) design: approved.
19. Phase 5 Step 2A (core logic migration) implementation: done.
20. Phase 5 Step 2B (context-sensitive logic migration) design: approved.
21. Phase 5 Step 2B (context-sensitive logic migration) implementation: done.
22. Phase 5 Step 3 (consumer migration) design: approved for first narrow slice.
23. Phase 5 Step 3 (consumer migration) implementation: done for first narrow slice.
24. Phase 5 review (next slice): done. Approved `NO_FOLLOWUP` and `FOLLOWUP_ACTION` for Step 4.
25. Phase 5 Step 4 (second consumer migration) design: approved.
26. Phase 5 Step 4 (second consumer migration) implementation: done.
27. Phase 5 boundary review: done. Phase 5 is complete.
28. Phase 6 (Bundle Semantic Validation Pass) design: approved.
29. Phase 6 Step 1 (scaffolding): done.
30. Phase 6 Step 2A (error-code logic) implementation: done.
31. Phase 6 Step 2B.1 (INTENT_ACTION_BUNDLE shape) implementation: done.
32. Phase 6 Step 2B.2 (READONLY_ACTION_BATCH_CANDIDATE shape) implementation: done.
33. Phase 6 Step 2B.3 (NO_BUNDLE_SHAPE for INTENT_ONLY) implementation: done.
34. Phase 6 Step 2C (parity testing) implementation: done.
35. Phase 6 Step 3 (first consumer migration) implementation: done.
36. Phase 6 Step 4 (next consumer migration review): done.
37. Phase 6 is complete.
38. Post-Phase 6 planning review: done.
39. Phase 7 (ActionPolicy-Dependent Bundle Validation) design: approved.
40. Phase 7 Step 2 (characterization tests): done.
41. Phase 7 Step 3 (design review): done. Approved Step 3A (scaffolding).
42. Phase 7 Step 3A (scaffolding): done.
43. Phase 7 Step 3B (`ActionPolicyHandler` internal refactor) design: approved.
44. Phase 7 Step 3B implementation: done.
45. Phase 7 Step 4 (consumer migration) design: approved.
46. Phase 7 Step 4 implementation: done.
47. Phase 7 closure review: done.
48. Phase 7 is complete.
49. Next phase selected: Visible Text / Terminal Answer Semantics (Phase 8).
50. Phase 8 Step 1 (design-only inventory): done.
51. Phase 8 Step 2 (characterization tests) design: approved.
52. Phase 8 Step 2 (characterization tests) implementation: done.
53. Phase 8 Step 3 (Design Review): done. Approved typed model scaffolding.
54. Phase 8 Step 3A (scaffolding): done.
55. Phase 8 Step 4A (Design-Only Review): done. Conclusion: signals insufficient.
56. Phase 8 Step 4C (Design): done.
57. Phase 8 Step 4D (Design): done.
58. Phase 8 Step 4D.1 (Implementation): done.
59. Phase 8 Step 4E design gate: done.
60. Phase 8 Step 4E implementation: done.
61. Phase 8 Step 4F shadow sufficiency / parity review: done.
62. Note: parser atom coverage prerequisite recorded.
63. Phase 8 Step 4B (Redux): TerminalAnswerClassifier Shadow Mode Design: done.
64. Phase 8 Step 4G: TerminalAnswerClassifier Shadow Implementation (isolated): done.
65. Phase 8 Step 4H: Shadow Wiring / Diagnostic Logging (shadow signal only): done.
66. Phase 8 Step 4I (Part 1): Parity Matrix Logging: done.
67. Phase 8 Step 4I (Part 2): Legacy Helper Integration (LEAKED_SYSTEM_RESULT): done.
68. Phase 8 Step 4I (Part 3) design gate (INVALID_OR_TRUNCATED): done.
69. Phase 8 Step 4I (Part 3) implementation: done.
70. Phase 8 Step 4I (Part 4) design gate (`INTERNAL_SUMMARY_LIKE_TEXT`): done.
71. Phase 8 Step 4I (Part 4) implementation (`INTERNAL_SUMMARY_LIKE_TEXT`): done.
72. Phase 8 Step 4I parity matrix / closure docs: done.
73. Phase 8 Step 4I: complete.
74. Phase 8 Step 4J Consumer Migration Design Gate: done.
75. Phase 8 Step 4K First Consumer Migration (Design): done.
76. Step 4K design correction from read-only preflight: typed result primary signal plus legacy fallback; strict replacement forbidden for Step 4L.
77. Phase 8 Step 4L First Consumer Migration (Implementation): done.
78. Step 4L migrated only the leaked-system-result guard in `ResponsePipelineStagesMixin`; typed classifier result is primary signal, legacy accessor remains production fallback.
79. Phase 8 Step 4M Terminal Answer Consumer Migration Batch Plan: done.
80. Step 4M conclusion: keep the Terminal Answers slice open; migrate remaining legacy consumers in narrow behavior-preserving steps only.
81. Phase 8 Step 4M.1 `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer migration design: done.
82. Phase 8 Step 4M.2 `INVALID_OR_TRUNCATED_TERMINAL_TEXT` consumer migration implementation: done.
83. Phase 8 Step 4N.1 `INTERNAL_SUMMARY_LIKE_TEXT` consumer migration design: done.
84. Phase 8 Step 4N.2 `INTERNAL_SUMMARY_LIKE_TEXT` consumer migration implementation: done.
85. Phase 8 Step 4O Terminal Answer Remaining Consumer Review / Final-Answer Path Preflight: done.
86. Step 4O conclusion: NO-GO for `PLAINTEXT_TERMINAL_ANSWER` migration in the current slice; defer final-answer-path migration.
87. Phase 8 Step 4P Terminal Answers slice closure / deferred final-answer migration: done.
88. Phase 9 Step 1 Plan-First Bundle Execution Design Gate: done.
89. Phase 9 Step 2 ExecutionPlan Producer/Consumer Contract Design: done.
90. Phase 9 Step 3 ExecutionPlan Contract Characterization Tests: done.
91. Phase 9 Step 4 ExecutionPlan First Producer Migration / Dispatch Consumer Preflight: done.
92. Phase 9 Step 5A Dispatch Bridge Parity Probe: done.
93. Phase 9 Step 5B IR-Derived Dispatch Candidate Contract: done.
94. Phase 9 Step 5C IR-Derived Dispatch Candidate Implementation: done.
95. Phase 9 Step 5D Candidate-to-Dispatcher Bridge Preflight: done.
96. Phase 9 Step 5E Candidate Metadata Bridge Implementation: done.
97. Phase 9 Step 5F Metadata Bridge Parity Review / Candidate Adapter Decision: done.
98. Phase 9 Step 6 Plan-First Producer Narrowing / ExecutionPlan Enrichment Review: done.
99. Phase 9 Step 6A ExecutionPlan Observational Enrichment Implementation: done.
100. Phase 9 Step 6B ExecutionPlan Enrichment Parity Review / Consumer Narrowing Decision: done.
101. Phase 9 Step 6C Candidate Eligibility Metadata Alignment: done.
102. Phase 9 Step 6D Metadata Alignment Review / Producer-Consumer Contract Closure: done.
103. Phase 9 Step 7 Plan-First Dispatch Boundary Closure / Next Slice Selection: done.
104. Phase 10 Step 1: Board/Checkpoint Consumer Slice Preflight: done.
105. Phase 10 Step 2: Board/Checkpoint Characterization Tests: done.
106. Phase 10 Step 3: Pipeline Reordering Design: done.
107. Phase 10 Step 4: Pure Structural Diagnosis Extraction + Early Prepass: done.
108. Phase 10 Step 4B: Structural Prepass Parity / Reuse Decision: done.
109. Phase 10 Step 5: First Board/Checkpoint Consumer Migration (Design): done.
110. Phase 10 Step 6: Board/Checkpoint Structural Parity Logging Implementation: done.
111. Phase 10 Step 7: Board/Checkpoint Parity Review / First Authority Migration Decision: done.
112. Phase 10 Step 8: Direct Board Handler Parsing/Commit Characterization Tests: done.
113. Phase 10 Step 9: Board/Checkpoint Semantic Model Design: done.
114. Phase 10 Step 10: Board/Checkpoint Semantic Model Skeleton + Shadow Population: done.
115. Phase 10 Step 11: Board/Checkpoint Semantic Model Parity Review / First Consumer Migration Decision: done.
116. Phase 10 Step 12: BoardCheckpoint Semantic Model Refinement + Pure Builder Extraction: done.
117. Phase 10 Step 13: First Narrow BoardCheckpoint Consumer Migration: done.
118. Phase 10 Step 14: Complete Legacy-Derived Typed Read-Through for Board Checkpoint Routing: done.
119. Phase 10 Step 16: done. Effective checkpoint-flag resolution is now centralized in a pure helper, with no routing or commit behavior change.
120. Phase 10 Step 17: done. `_run_checkpoint_stage(...)` now uses `EffectiveCheckpointFlags` as the single local checkpoint routing/state surface after resolution. No compiler/prepass authority was introduced, and no observable routing or commit behavior changed.
121. Phase 10 Step 18: done. First true authority candidate for memory-checkpoint-only branch implemented with legacy disagreement guard. Typed result cannot change memory branch category. No behavior change.
122. Phase 10 Step 19: done. Extended typed-primary candidate pattern to remaining memory branches. No behavior change.
123. Phase 10 Step 20: done. Extended typed-primary candidate pattern to plan branches. No behavior change.
124. Phase 10 Step 21: done. Consolidated board/checkpoint typed-primary candidate helpers. No behavior change.
125. Phase 10 Step 22: done. Introduced first default-off compiler-authority switch for `PLAN_CHECKPOINT_ONLY`. Default behavior unchanged.
126. Phase 10 Step 23: done. Hardened PLAN_CHECKPOINT_ONLY authority switch. Smoke tests passed. Decision: close slice, move to Phase 11.
127. Governance update: new strategy is branch-level authority switches, documented in `board-checkpoint-consumer-slice-design.md`.
128. Phase 10 Step 24: done. Central TOML registry for refactor switches introduced.
129. Phase 10 Step 25: done. Added smoke profile support for refactor switch registry via env var.
130. Phase 10 Step 26B: done. Fixed compiler recognition for self-closing `<subgoal ... />` checkpoints and added deterministic synthetic smoke coverage for the PLAN_CHECKPOINT_ONLY smoke-authority branch.
131. Phase 10 Step 26D: done. Added explicit board/checkpoint authority-source diagnostics so smoke logs distinguish shadow parity from real compiler-authority selection.
132. Phase 27 Step 1: done. Expanded deterministic board/checkpoint synthetic smoke coverage across plan, memory, mixed, action-only, plaintext-only, and invalid checkpoint controls.
133. Phase 27 Step 2: done. Enabled and validated smoke-profile compiler authority for `board_checkpoint.plan_checkpoint_with_text` with positive and negative synthetic controls, while keeping the default registry legacy.
134. Phase 27 Step 3: done. Targeted live Angelica smoke for `board_checkpoint.plan_checkpoint_with_text` passed under the smoke profile with compiler authority selected, no fallback, and no runtime crash.
135. Phase 27 Step 4: done. Enabled and validated smoke-profile compiler authority for `board_checkpoint.plan_checkpoint_with_action` with positive and negative synthetic controls, while keeping the default registry legacy and leaving dispatch behavior unchanged.
136. Phase 27 Step 5: done. Targeted live Angelica smoke for `board_checkpoint.plan_checkpoint_with_action` passed under the smoke profile with compiler authority selected, no fallback, preserved dispatch path, and no runtime crash.
137. Phase 27 Step 6: done. Closed the plan-domain board/checkpoint compiler-authority smoke slice; smoke profile may keep validated plan branches enabled, while default production behavior remains legacy.
138. Phase 28 Step 1: done. Inventoried terminal/final-answer consumers, confirmed existing terminal-answer switch placeholders remain legacy, and defined the initial synthetic smoke matrix without changing runtime behavior.
139. Phase 28 Step 2: done. Added a lightweight terminal-answer synthetic smoke harness plus observational plaintext-terminal authority diagnostics, with no authority transfer and no runtime behavior change.
140. Phase 28 Step 3: done. Expanded the terminal-answer synthetic matrix, hardened observational plaintext-terminal diagnostics, and recorded a NO-GO for `terminal_answer.plaintext_terminal_answer` authority transfer because `Done.`, markdown-ish plaintext, checkpoint-with-visible-text, and leaked-system-result cases still overlap the current legacy plaintext path.
141. Phase 28 Step 4: done. Hardened plaintext-terminal diagnostics with explicit overlap/candidate buckets and direct resolver characterization, while keeping all terminal-answer switches legacy and leaving runtime behavior unchanged.
142. Phase 28 Step 5: done. Narrowed the typed plaintext classifier so short punctuated plaintext like `Done.` and markdown-ish plaintext now align as typed plaintext terminal answers in shadow mode, without changing runtime authority or default registry values.
143. Phase 28 Step 6: done. Re-reviewed plaintext terminal authority after the typed classifier fix, enabled a smoke-profile-only compiler candidate for clean plaintext in diagnostics, and kept actual routing legacy with strict fallback for all overlaps and negative controls.
144. Phase 28 Step 7: done. Live Angelica smoke for plaintext terminal answer passed under the smoke profile with compiler authority diagnostics selected, no fallback, no overlap blockers, and no runtime crash, while actual routing was still legacy at that point.
145. Phase 28 Step 8: done. Introduced the first actual smoke-profile-only local routing use of plaintext terminal authority via an agreement-gated effective value, while keeping the default registry legacy and preserving fallback for all negative controls.
146. Phase 28 Step 9: done. Live Angelica smoke for the actual plaintext terminal routing flip passed under the smoke profile; `terminal_answer_authority_resolution` selected `compiler` with no fallback, no overlap blockers, and no runtime crash.
147. Phase 28 Step 10: done. Closed the plaintext terminal authority smoke slice, kept default production behavior legacy, and selected `terminal_answer.checkpoint_only` as the next synthetic-first terminal branch while deferring checkpoint-with-visible-text and action-bearing/recovery-sensitive branches.
148. Phase 28 Step 11: done. Added the synthetic-first `terminal_answer.checkpoint_only` authority candidate with smoke-profile-only compiler switch, explicit diagnostics, and negative controls, while keeping the default registry legacy and leaving production authority unchanged.
149. Phase 28 Step 12: not exercised / defer. Live smoke produced a clean `<memory_update_done />`, but the turn was consumed by the memory-board checkpoint stage before terminal checkpoint-only authority could own it.
150. Phase 28 Step 13: done. Reviewed the ownership boundary and marked `terminal_answer.checkpoint_only` as NO-GO / DEFER for terminal-authority migration; reverted the smoke-profile switch back to legacy to avoid implying live authority validation.
151. Phase 28 Step 14: done. Cleaned up `terminal_answer_classifier_shadow` so safe short plaintext no longer shows stale mismatch against the old completion guard, and added explicit comparator-scope fields to distinguish parity logs from authority logs.
152. Phase 28 Step 15: done. Closed the terminal plaintext slice for now; plaintext terminal authority is smoke-validated, checkpoint terminal branches remain deferred, and `terminal_answer_classifier_shadow` is now clearly parity-only.
153. Phase 29 Step 1: done. Inventoried recovery/invalid-output consumers, confirmed no recovery-domain switch family exists yet, and defined the initial synthetic smoke matrix plus the need for dedicated recovery authority diagnostics.
154. Phase 29 Step 2: done. Added the observational `RecoveryAuthorityDiagnostic`, logged `recovery_authority_resolution` for compiler-invalid mapping and prevalidation invalid-output routing, and created the first deterministic recovery synthetic smoke harness.
155. Phase 29 Step 3: done. Expanded the recovery synthetic matrix, hardened observational recovery diagnostics, and recorded a NO-GO for authority transfer in this slice; the cleanest future candidate is `recovery.compiler_invalid_kind_mapping`.
156. Phase 29 Step 4: done. Added `resolve_compiler_invalid_kind_mapping_authority(...)`, routed both prevalidation and output-recovery invalid-kind mapping through it, and added a default/smoke-legacy `[recovery] compiler_invalid_kind_mapping` placeholder without changing runtime behavior.
157. Phase 29 Step 5: done. Enabled smoke-profile compiler mode for `recovery.compiler_invalid_kind_mapping`, clarified switch-vs-effective-source diagnostics, added behavior-preserving `E_MEMORY_TAG_INSIDE_THINK` mapping, and validated the branch synthetically with preserved fallback behavior.
158. Phase 29 Step 6: done. Closed the `recovery.compiler_invalid_kind_mapping` smoke slice, kept default authority legacy, retained smoke-only compiler mode, and selected `recovery.prevalidation_reject_invalid_output` as the next recovery authority branch.
159. Phase 29 Step 7: done. Added `resolve_prevalidation_reject_invalid_output_authority(...)`, routed the prevalidation reject path through its effective decision behavior-preservingly, and added default/smoke-legacy placeholders for the branch.
160. Phase 29 Step 8: done. Added a real compiler-side prevalidation recovery decision candidate builder, extended the resolver to compare candidate vs legacy decision shape/prompt equivalence, and deferred smoke switch enablement because candidate coverage is still partial.
161. Phase 29 Step 9: done. Enabled smoke-only compiler mode for `recovery.prevalidation_reject_invalid_output`, validated compiler-selected cases for fenced stateless candidates, and kept unsupported/stateful cases on explicit legacy fallback without changing runtime behavior.
162. Phase 29 Step 10: done. Closed `recovery.prevalidation_reject_invalid_output` as a smoke-validated fenced compiler-authority slice, clarified that `mixed_intent_transition_and_visible_answer` is intent-followup recovery rather than normal terminal plaintext authority, and selected `recovery.leaked_system_result` as the next branch.
163. Phase 29 Step 11: done. Added leaked-system-result recovery authority resolver/accessor coverage, wired the post-classification leak guard through the resolver behavior-preservingly, added default/smoke switch entries, and enabled smoke-only compiler authority for canonical typed leak cases with strict legacy fallback elsewhere.
164. Phase 29 Step 12: done. Closed `recovery.leaked_system_result` as a smoke-validated fenced compiler-authority slice, kept default authority legacy, and selected `recovery.invalid_truncated_terminal_text` as the next recovery branch.
165. Phase 29 Step 13: done. Added a resolver and diagnostic-only logging for `recovery.invalid_truncated_terminal_text`, added default/smoke legacy switch placeholders, and added synthetic smoke coverage without changing runtime behavior.
166. Phase 29 Step 14: done. Recorded NO-GO for smoke switch on `recovery.invalid_truncated_terminal_text` because it is a diagnostic-only branch without a recovery decision to own. Added more synthetic coverage.
167. Phase 29 Step 15: done. Closed the invalid/truncated terminal text slice as diagnostic-only, and decided to close Phase 29 to avoid expanding into deep policy or stateful guard refactoring.
168. Phase 29 Step 16: done. Closed Phase 29 (Recovery Core), documented smoke-validated and deferred branches, and selected Phase 30 (Board/Memory Commit Policy on Compiler-IR Foundation) as the next major phase.
169. Phase 30 Step 1: done. Inventoried board/memory commit policy, documented blockers, and designed a commit-equivalence harness plan, with `MEMORY_CHECKPOINT_ONLY` as the first target.
170. Phase 30 Step 2: done. Created a synthetic harness in `tests/test_board_memory_commit_equivalence.py` to capture legacy memory commit behavior for `MEMORY_CHECKPOINT_ONLY` and other branches using a controlled static memory stage, without changing any production code.
171. Phase 30 Step 3: done. Hardened the commit-equivalence harness to snapshot the real `MemoryBoardStageHandler`, improved the `LegacyCommitSnapshot` model, and added a test to prove the real handler's `MEMORY_CHECKPOINT_ONLY` commit behavior can be captured. No production behavior changed.
172. Phase 30 Step 4: done. Added a typed `MemoryCommitCandidate` model and a `resolve_memory_checkpoint_only_commit_authority` resolver. The candidate is narrow and blocks on commit-count equivalence. Added a `legacy`-only switch placeholder. No production authority was transferred, and no runtime behavior was changed.
173. Phase 30 Step 5: done. Hardened commit-equivalence validation for `MEMORY_CHECKPOINT_ONLY` using an "observed-equivalence" model where the resolver proves equivalence by checking the observed legacy commit result against structural expectations. The smoke switch remains `legacy`. No runtime behavior changed.
174. Phase 30 Step 6: done. Enabled the smoke-only switch for `board_memory.memory_checkpoint_only` and added synthetic tests to validate compiler authority selection for clean, observed-equivalent cases, with appropriate fallback controls. Default registry remains legacy. No production behavior changed.
175. Phase 30 Step 7: done. Decided NO-GO for live smoke due to integrated observability blocker; resolver is not yet wired into the runtime pipeline. Next step is to add diagnostic integration. No runtime behavior changed.
176. Phase 30 Step 8: done. Integrated the memory commit authority resolver for diagnostic logging only. No runtime behavior changed.
177. Phase 30 Step 9: done. Hardened runtime diagnostic extraction for real handler state fields. Diagnostic-only change. No runtime behavior changed.
178. Phase 30 Step 10: done. Live smoke for MCO was run. It was NOT a pass. `commit_equivalent` was false due to a mismatch between synthetic expectations and real handler behavior for marker-only checkpoints.
179. Phase 30 Step 11: done. Reconciled synthetic equivalence model with live `MemoryBoardStageHandler` behavior for marker-only checkpoints (`accepted_count=0`). Content-bearing MCO tests were removed as invalid. No runtime behavior changed.
180. Phase 30 — Step 12/12: done. Closed the `MEMORY_CHECKPOINT_ONLY` slice. A second live smoke run was not required. The next branch is `MEMORY_CHECKPOINT_WITH_TEXT`. No runtime behavior changed.
181. Phase 31 — Step 1/10: done. Inventoried `MEMORY_CHECKPOINT_WITH_TEXT` behavior and designed the harness extension. No runtime behavior changed.
182. Phase 31 — Step 2/10: done. Extended the commit-equivalence harness for `MEMORY_CHECKPOINT_WITH_TEXT`, characterizing visible text preservation, pass-through behavior, and zero-count commit semantics. No runtime behavior changed.
183. Phase 31 — Step 3/10: done. Added a candidate model and resolver for `MEMORY_CHECKPOINT_WITH_TEXT`, modeling visible text preservation and pass-through behavior. No runtime behavior changed.
184. Phase 31 — Step 4/10: done. Hardened `MEMORY_CHECKPOINT_WITH_TEXT` commit-equivalence validation. A clean real-handler case now proves full `commit_equivalent=True`, while any mismatch correctly falls back to legacy. No runtime behavior was changed, and no authority was transferred. The smoke switch remains `legacy`.
185. Phase 31 — Step 5/10: done. Enabled smoke-only compiler switch for `board_memory.memory_checkpoint_with_text`. Clean real-handler MCT selects compiler authority under smoke profile, with fallback on mismatch and for negative controls. No production behavior changed.
186. Phase 31 — Step 6/10: done. Added diagnostic-only MCT resolver call in `_run_checkpoint_stage` to enable live observability. Resolver `effective_commit` is not consumed. No runtime behavior changed.
187. Phase 31 — Step 7/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Validation (Complete). Live smoke was run manually. Observability works, but the result was NOT A PASS. `commit_equivalent` was `False`, causing `legacy_fallback`. Runtime behavior was preserved.
188. Phase 31 — Step 8/10: MEMORY_CHECKPOINT_WITH_TEXT Live Semantics Reconciliation (Complete). Detailed live diagnostics identified the exact mismatch: only `commit_attempted_agreement` was `False`. The candidate/resolver model is now live-faithful: marker-with-text is treated as a pass-through, not a content commit attempt (`expected_commit_attempted=False`). No runtime behavior was changed.
189. Phase 31 — Step 9/10: MEMORY_CHECKPOINT_WITH_TEXT Live Smoke Re-run / Closure Decision (Complete). Manual live smoke re-run passed. MCT diagnostic showed `switch_value="compiler"`, `authority_source="compiler"`, `selected_by_switch=True`, `candidate_available=True`, and `commit_equivalent=True`. Runtime behavior was preserved.
190. Phase 31 — Step 10/10: MEMORY_CHECKPOINT_WITH_TEXT Closure / Next Branch Selection (Complete). The MCT slice is closed. The branch is now fully validated under smoke profile. Default registry remains `legacy`. No production behavior was changed. Next branch is `MEMORY_CHECKPOINT_WITH_ACTION`.
191. Phase 32 is now `Operational Speed / Recovery Protocol Hardening`. `MEMORY_CHECKPOINT_WITH_ACTION` is deferred.
192. Phase 32 — Step 1/8: Invalid Path + Atomic Bundle Recovery Characterization (Complete). Narrowed root cause from path recovery to failure-mode atomic bundle rejection. Characterized that valid intent+single-action bundles after recoverable failure should be protocol-valid. Updated tests to distinguish protocol validity from action/tool feasibility. No runtime behavior changed.
193. Phase 32 — Step 2/8: Permit Valid Intent+Single-Action Bundles after Recoverable Failure (Complete). The `intent_atomic_bundle_guard` no longer rejects structurally valid intent+single-action bundles during retry/continuation-after-failure. Mutating actions are not rejected at this layer solely for being mutating. Normal action/tool policy still applies. Malformed and unsupported multi-action bundles remain blocked. No Angelica/live agent was run.
194. Phase 32 — Step 3/8: E_ACTION_PAYLOAD_ARRAY / Read-only Multi-action Discovery Bundle Characterization (Complete). Added characterization tests for current multi-action rejection (`E_ACTION_PAYLOAD_ARRAY` / `multiple_actions`) and future desired read-only discovery batch support. No production behavior changed.
195. Phase 32 — Step 4/8: Read-only Multi-action Discovery Bundle Support (Complete). Bounded one-intent read-only discovery bundles with 2–3 actions are now protocol-valid. No tool execution behavior changed. Mutating, run_shell, malformed, >3 actions, and unbounded discovery bundles remain blocked. This reduces recovery/discovery round-trips for common “inspect/search docs” model outputs. No Angelica/live agent was run.
196. Phase 32 — Step 4.5/8: Extracted Intent Payload + Single Action Recovery Bundle Reconciliation (Complete). Fixed a live regression where a valid `intent+action` recovery bundle was blocked because the intent was extracted into `step.intent_payload` before prevalidation. The guard now correctly handles this case. No production behavior changed for non-recovery paths.
197. Phase 32 — Step 5/8: Structure-only Think Repair Atomicity Characterization (Complete). Characterized current behavior where possible think repair can be blocked by atomicity constraints. Added a negative control for unsafe repairs and a future xfail for structure-only think repair allowance. No runtime behavior was changed.
198. Phase 32 — Step 4.6/8: Runtime-State Recoverable Failure Detection for Extracted Intent Bundles (Complete). New smoke dump showed `step.intent_error` can be empty while recoverable failure exists in runtime state. `_reject_invalid_atomic_bundle_before_transition` now detects recoverable failure from runtime/context state as well as step intent_error. Extracted intent payload + single valid ACTION_ONLY recovery action now passes atomic bundle guard in this live shape. Malformed and unsupported multi-action bundles remain blocked. No tool execution behavior changed. No search/path normalization changed. No Angelica/live agent was run.
199. Phase 32 — Step 6/8: Structure-only Think Repair Allowance (Complete). Structure-only trailing `</think>` repair is now allowed under atomicity constraints when protocol-relevant payloads are unchanged. The allowance is intentionally narrow: currently only simple trailing think closure is allowed. Repairs that alter action/intent/file/protocol blocks remain blocked. Think repair inside action JSON remains blocked. Malformed reuse/followup atomicity remains protected. No tool execution behavior changed. No search/path normalization changed. No Angelica/live agent was run.
200. Phase 32 — Step 7/8: Broad Search Result Shaping (Complete). Broad `search_content` results now return compact path histogram summaries when result volume is too high. Top files are grouped by match count. Broad search output includes non-prescriptive narrowing hints. Small search behavior remains unchanged. No search matching semantics changed. No path normalization changed. No automatic recovery actions were added. No memory-board anchoring was added. No Angelica/live agent was run.
201. Phase 32 — Step 7.5/8: Stale Retry Guard Reconciliation (Complete). `retry_or_continuation_after_failure` now requires an actual active recoverable failure context. Stale retry context with `last_error_recoverable=False` no longer blocks valid `ACTION_ONLY` recovery actions. True recoverable failure behavior remains preserved. No search shaping, tool execution, or path normalization was changed. No Angelica/live agent was run.
202. Phase 32 — Step 8/8: Repeat Broad Search Guard / Path Memory Anchoring Decision (Complete). Decided not to add hard repeat broad search blocking or automatic memory-board path anchoring in Phase 32. Broad search histogram from Step 7 is the primary mitigation. Path memory anchoring and repeat broad search guard are deferred to a future phase. Refined broad search hint wording to prefer skeleton/chunk before full read. No search matching, path normalization, tool execution, or protocol guard behavior changed. No Angelica/live agent was run.
203. Phase 34 — Step 1/N: Think Boundary Auto-Closure Normalization (Complete). Safe open `<think>` is auto-closed before known top-level protocol boundary tags and at EOF. This intentionally changes prior E_UNCLOSED_THINK recovery behavior for safe boundary-repairable cases. Protected contexts (action JSON, quotes, code fences) remain safe. Repair is normalization only; compiler/prevalidation/action policy still decide validity/dispatch. No Angelica/live agent was run.
204. Phase 35 — Step 1/10: MEMORY_CHECKPOINT_WITH_ACTION Commit Policy Inventory / Harness Plan (Complete). Inventoried legacy behavior for memory checkpoint + action, where the pipeline ensures pass-through for dispatch. Documented the observation-boundary issue and the harness plan for Step 2. Docs-only step. No production code or tests changed.
205. Phase 35 — Step 2/10: MEMORY_CHECKPOINT_WITH_ACTION Synthetic Commit-Equivalence Harness (Complete). Extended the commit-equivalence harness to characterize `MEMORY_CHECKPOINT_WITH_ACTION`. The new real-handler-backed snapshot test (with mocked board engine) confirms action preservation and pass-through behavior, and explicitly documents the observation-boundary issue where the compiler shape is `ACTION_ONLY` after marker stripping. No production code changed.
206. Phase 35 — Step 3/10: MEMORY_CHECKPOINT_WITH_ACTION Candidate Model / Resolver Design (Complete). Added a typed candidate model and resolver for `MEMORY_CHECKPOINT_WITH_ACTION`, covering action preservation and pass-through behavior. The resolver is not yet wired into the runtime. No production behavior changed.
207. Phase 35 — Step 4/10: MEMORY_CHECKPOINT_WITH_ACTION Commit-Equivalence Hardening (Complete). Hardened the MCTA candidate builder and resolver with more negative controls and stricter agreement checks. Added tests for candidate availability and resolver fallback. No production behavior changed.
208. Phase 35 — Step 5/10: MEMORY_CHECKPOINT_WITH_ACTION Smoke Switch Validation (Complete). Added smoke-only switch coverage for MCTA candidate/resolver authority validation. Default registry remains legacy. Resolver is not yet wired into runtime. No production behavior changed.
209. Phase 35 — Step 6/10: MEMORY_CHECKPOINT_WITH_ACTION Runtime Diagnostic Integration (Complete). The MCTA resolver is now called from `_run_checkpoint_stage` for diagnostic logging only. The resolver's `effective_commit` is not consumed, and no runtime behavior was changed. The default registry remains `legacy`, and the smoke registry remains `compiler` for this branch for validation purposes. No dispatch, action, or `MemoryBoardStageHandler` behavior was changed.
210. Phase 35 — Step 7/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Validation (Complete). Manual live smoke was run for MCTA under the smoke profile. The diagnostic was observable, but `commit_equivalent` was `False` due to a mismatch in `commit_attempted_agreement`. Runtime behavior was preserved.
211. Phase 35 — Step 8/10: MEMORY_CHECKPOINT_WITH_ACTION Live Semantics Reconciliation (Complete). Reconciled MCTA commit semantics: bare marker + action does not count as a durable memory content commit attempt. `expected_commit_attempted` is now `False` for marker-only + action. No runtime behavior changed.
212. Phase 35 — Step 9/10: MEMORY_CHECKPOINT_WITH_ACTION Live Smoke Re-run / Closure Decision (Complete). Manual live smoke re-run passed. MCTA diagnostic showed `commit_equivalent=True` and `authority_source="compiler"`. Runtime behavior was preserved.
213. Phase 35 — Step 10/10: MEMORY_CHECKPOINT_WITH_ACTION Closure / Next Branch Selection (Complete). Phase 35 is complete. MCTA branch is validated. Default registry remains legacy. No production behavior changed.
214. Phase 36 — Step 1/N: MEMORY_CONTENT_WITH_ACTION Commit Policy Characterization / Inventory (Complete). Inventoried the distinct live/runtime case where a checkpoint includes a durable memory content tag and an action. Added a characterization test. No production behavior changed.
215. Phase 36 — Step 2/N: MEMORY_CONTENT_WITH_ACTION Candidate / Resolver Model Design (Complete). Added a candidate/resolver model for durable memory content + action, distinct from Phase 35 bare-marker MCTA. No runtime behavior changed.
216. Phase 36 — Step 3/N: MEMORY_CONTENT_WITH_ACTION Commit-Equivalence Hardening / Smoke Switch Planning (Complete). Strengthened commit-equivalence tests and negative controls for the durable memory content + action case. Documented the smoke switch plan for `board_memory.memory_content_with_action` without adding registry entries. No runtime behavior was changed, no diagnostic wiring was added, and `effective_commit` is not consumed.
217. Phase 36 — Step 4/N: MEMORY_CONTENT_WITH_ACTION Smoke Switch Registration / Validation (Complete). Added `board_memory.memory_content_with_action` switch key. Default registry remains legacy; smoke registry uses compiler. Added smoke validation tests. No runtime behavior change.
218. Phase 36 — Step 5/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Integration (Complete). The resolver is now called from `_run_checkpoint_stage` for diagnostic logging only; `effective_commit` is not consumed, and no runtime behavior was changed.
219. Phase 36 — Step 6/N: MEMORY_CONTENT_WITH_ACTION Runtime Diagnostic Smoke Validation (Complete). Manual/live smoke validated `board_memory.memory_content_with_action` under the smoke profile: compiler authority was selected diagnostically with `commit_equivalent=True`, while runtime dispatch remained preserved and `effective_commit` was not consumed.
220. Phase 36 — Step 7/N: MEMORY_CONTENT_WITH_ACTION Live Smoke Closure / Reconciliation Decision (Complete). No reconciliation is required. The diagnostic-only branch-name delta is expected; runtime behavior remains legacy/default-safe and Phase 35 MCTA semantics remain unchanged.
221. Phase 36 — Step 8/N: MEMORY_CONTENT_WITH_ACTION Closure / Next Branch Selection (Complete). Phase 36 is complete. Durable memory content + action is validated under the smoke profile with `commit_equivalent=True`; runtime behavior remains legacy/default-safe, `effective_commit` is not consumed, and Phase 35 MCTA semantics remain unchanged.
222. Phase 37 — Step 1/N: Board/Memory Remaining Branch Selection / Next Slice Planning (Complete). Confirmed that the board-memory commit-policy line now covers `memory_checkpoint_only`, `memory_checkpoint_with_text`, `memory_checkpoint_with_action`, and `memory_content_with_action`. `board_checkpoint.plan_*` authority branches are a separate slice and must not be folded into board-memory commit-policy closure. No production behavior changed.
223. Phase 37 — Step 2/N: Board/Memory Commit-Policy Closure / Cross-Slice Boundary Review (Complete). Closed the board-memory commit-policy line for the characterized branches. Completed board-memory branches remain default-legacy and smoke-compiler where validated; runtime behavior remains legacy/default-safe and `effective_commit` is not consumed. `board_checkpoint.plan_*` authority work remains a separate slice.
224. Phase 38 — Step 1/N: Board-Checkpoint Plan Authority Boundary Review / Inventory (Complete). Confirmed that `board_checkpoint.plan_checkpoint_only`, `board_checkpoint.plan_checkpoint_with_text`, and `board_checkpoint.plan_checkpoint_with_action` remain default-legacy and smoke-compiler, and that Phase 27 already validated the plan-domain board/checkpoint smoke slice with synthetic coverage, authority diagnostics, and live smoke. No production behavior changed.
225. Phase 38 — Step 2/N: Board-Checkpoint Plan Authority Closure / Remaining Work Decision (Complete). Closed the `board_checkpoint.plan_*` authority slice based on prior Phase 27 validation. The plan-domain branches already have synthetic smoke coverage, authority diagnostics, and live smoke validation under the smoke profile. Default registry remains legacy; smoke registry remains compiler. No production behavior changed.
226. Phase 39 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory (Complete). Inventoried candidate next slices after closing board/checkpoint and board-memory authority work: Phase 33 Search/Path Recovery UX Hardening, terminal-answer remaining boundaries, recovery deferred branches, dispatch/action boundary work, and legacy cleanup after a consumer map. No production behavior changed.
227. Phase 39 — Step 2/N: Select Next Active Slice (Complete). Selected Phase 33 — Search/Path Recovery UX Hardening as the next active slice. The slice must proceed characterization-first and diagnostic/hint-first, with no hard repeat-search blocking, automatic memory-board path anchoring, production authority transfer, broad recovery rewrite, or legacy cleanup.
228. Phase 33 — Step 1/N: Search/Path Recovery UX Hardening Inventory (Complete). Inventoried existing Phase 32 broad-search result shaping and deferred repeat broad-search/path anchoring decisions. Identified candidate implementation areas around filesystem path failure/validation, search quality, recovery prompts/state, and search tool result shaping. No production behavior changed.
229. Phase 33 — Step 2/N: Search/Path Current Behavior Characterization (Complete). Characterized current broad search shaping, diagnostic search quality classification, filesystem path validation, invalid filesystem path failure recovery, and invalid-path recovery prompt behavior. No search matching, path normalization, tool execution, recovery authority, or memory-board behavior changed.
230. Phase 33 — Step 3/N: Repeat Broad Search / Invalid Path Gap Decision (Complete). Selected repeat broad-search characterization as the next active gap. Invalid-path prompt hardening and hint-only path anchoring remain deferred; hard repeat-search blocking and automatic memory-board path anchoring remain forbidden.
231. Phase 33 — Step 4/N: Repeat Broad Search Characterization (Complete). Added prompt-level characterization for `low_value_broad_search_repeat`: recovery remains UX guidance, not hard blocking; bounded reconnaissance or targeted reads are preferred, and repeated broad search is discouraged. No runtime behavior changed.
232. Phase 33 — Step 5/N: Repeat Broad Search Guard / Hint Hardening Decision (Complete). Chose prompt-only hint hardening instead of a hard repeat-search guard. The recovery prompt now explicitly forbids repeating the same root-level or weakly bounded `search_content` query and requires any follow-up search to be materially narrower. No runtime behavior changed.
233. Phase 33 — Step 6/N: Invalid-Path Recovery Prompt Hardening Decision (Complete). Chose minimal prompt-only hardening. The invalid-path recovery prompt now also forbids substituting another guessed replacement path and requires proving a valid root with an allowed read-only action first. No runtime behavior changed.
234. Phase 33 — Step 7/N: Search/Path Recovery UX Hardening Closure (Complete). Closed Phase 33 after characterization and prompt-only UX hardening. Hint-only path anchoring is deferred to a future characterization-first slice because it risks hidden stateful path memory. No hard blocking, memory-board writes, path normalization change, search matching change, tool execution change, recovery authority change, or broad recovery rewrite was added.
235. Phase 40 — Step 1/N: Next Semantic Runtime Slice Selection / Candidate Inventory (Complete). Inventoried candidate next slices after closing Phase 33: Terminal Answer deferred/final-answer migration review, Dispatch/action boundary review, RecoveryStrategy or deferred recovery branch review, and consumer map before legacy cleanup. No production behavior changed.
236. Phase 40 — Step 2/N: Select Next Active Slice (Complete). Selected Terminal Answer Deferred / Final-Answer Migration Review as the next active slice. Phase 41 will begin with preflight/inventory only. Stop lines: no final-answer stop/continue behavior changes, dispatch changes, ActionPolicy changes, recovery behavior changes, authority transfer, or legacy cleanup.
237. Phase 41 — Step 1/N: Terminal Answer Deferred Final-Answer Path Preflight / Inventory (Complete). Inventoried the Terminal Answer deferred final-answer path state. Confirmed prior Phase 8/28/29 work, smoke-validated plaintext terminal authority under smoke profile, deferred checkpoint/action/recovery-sensitive branches, and high-risk final-answer stop/continue boundaries. No production behavior changed.
238. Phase 41 — Step 2/N: Final-Answer Consumer Map (Complete). Mapped final-answer-related consumers across classifier/shadow evidence, prevalidation/truncated terminal paths, response-pipeline recovery/final-answer boundaries, output-recovery/internal-summary paths, prompt-only final-answer guidance, and adjacent board/memory visible-text preservation tests. No migration candidate is approved yet. No production behavior changed.
239. Phase 41 — Step 3/N: Final-Answer Risk Boundary Review / Migration Candidate Decision (Complete). Recorded NO-GO for real final-answer migration in this step. Final-answer consumers remain tied to stop/continue behavior, sufficiency policy, visible text, recovery, dispatch, and ActionPolicy boundaries. Only design-only candidate review is approved next. No production behavior changed.
240. Phase 41 — Step 4/N: Final-Answer Slice Exit / Next Slice Selection (Complete). Deferred real final-answer migration after the risk boundary review. Selected Semantic Runtime Consumer Map / Legacy Cleanup Preflight as the next active slice so cleanup decisions are based on an explicit consumer map. No production behavior changed.
241. Phase 42 — Step 1/N: Semantic Runtime Consumer Map / Legacy Cleanup Preflight Inventory (Complete). Inventoried semantic-runtime legacy and compatibility surfaces including `ResponseSemantics`, semantic accessors, `RuntimeProtocolSemantics`, `ParsedModelOutput` compatibility fields, output-recovery metadata fallback, and visible consumer groups across response pipeline, output recovery, terminal-answer, action policy, board/memory, parser/protocol, and tests. No cleanup is approved yet. No production behavior changed.
242. Phase 42 — Step 2/N: Consumer Classification / Cleanup Risk Matrix (Complete). Classified semantic-runtime legacy and compatibility consumers by risk. Protected compatibility/recovery-evidence surfaces, active runtime compatibility fields, dispatch/action policy consumers, final-answer/recovery consumers, diagnostic/transitional layers, test-only construction surfaces, and future cleanup candidates were separated. No cleanup is approved yet. No production behavior changed.
243. Phase 42 — Step 3/N: Cleanup Candidate Selection / Defer Decision (Complete). Selected exactly one narrow cleanup candidate for characterization only: consolidating `runtime_protocol_semantics.output_recovery_compiler_metadata(...)` into `semantic_accessors.get_compiler_metadata(...)`. All other cleanup surfaces remain deferred. No implementation or production behavior change was approved.
244. Next: Phase 42 — Step 4/N: Output-Recovery Compiler Metadata Fallback Parity Characterization.
