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
172. Next: Phase 30 Step 4: MEMORY_CHECKPOINT_ONLY Commit Candidate Model / Resolver Design.
