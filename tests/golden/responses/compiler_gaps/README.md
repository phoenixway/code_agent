# Compiler Coverage Gap Matrix

This test suite documents known gaps where the `ProtocolCompiler` does not yet fully cover behaviors handled by the legacy regex-based `ResponseSemantics` and `OutputRecovery` systems.

## Purpose

The primary goal is to make the migration path from legacy semantics to compiler-driven semantics safe and explicit. These tests serve as a "to-do list" for the compiler, ensuring that no legacy feature is lost during the transition.

A passing test in this suite **does not** mean the compiler is "correct" or "ready". It only means that the compiler's *current* behavior (whether complete, partial, or missing) matches what is documented in the corresponding YAML case file.

## Test Suites Overview

-   **Compiler Golden Tests**: Define the behavioral contract for what the compiler *currently does*. A passing suite means the compiler has not regressed.
-   **Semantic Shadow Tests**: Compare the semantic output of the legacy system vs. the compiler for the same input, documenting disagreements.
-   **Compiler Gap Tests (This Suite)**: Explicitly document legacy-handled cases that the compiler does not yet support, or supports only partially.

This structured approach ensures that we can incrementally migrate to the compiler as the single source of truth without losing functionality.
