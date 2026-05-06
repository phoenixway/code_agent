# Golden Tests for Protocol Compiler

This directory contains golden tests for the `ProtocolCompiler`.

The purpose of these tests is to establish a behavioral baseline for the compiler by itself, separate from the full response pipeline. This provides a safety net for refactoring and ensures that compiler changes have predictable outcomes.

As legacy response semantics are migrated to the compiler and its Intermediate Representation (IR), these tests should be updated and expanded to cover new capabilities and edge cases.
