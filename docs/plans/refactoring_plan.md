# Angelica AI Refactoring Plan ("Phoenix")

## Final Architectural Diagnosis

The core architecture suffers from several "God Objects," a critical anti-pattern leading to a fragile and complex system.

1.  **`ActionDispatcher`**: A monolithic class responsible for action execution, validation, normalization, batching, budget management, and error recovery generation.
2.  **`IntentRuntime`**: The central "brain" managing intent logic, lifecycle, goal changes, step budgets, and policy application.
3.  **`AgentState`**: A mix of global state management, current execution loop tracking, technical interruption handling, and redundant intent validation.
4.  **`IntentPolicyEngine`**: Contains policy logic, but this logic is critically **duplicated** within `IntentRuntime`.
5.  **`RecoveryCoordinator`**: Tightly coupled with `ActionDispatcher`, forming a convoluted error handling and recovery system.

**Core Problem:** Responsibilities are not separated but smeared across these classes. They are tightly coupled, know too much about each other, and perform redundant work. This makes the system brittle, difficult to test, and nearly impossible to modify safely.

---

## Step-by-Step Refactoring Plan

This plan is designed to incrementally "rebirth" the architecture without a full-stop rewrite.

### Step 1: Implement a Service Container

*   **Goal:** Centralize service creation and access.
*   **Actions:**
    1.  Create a new `ServiceContainer` class.
    2.  Move all service initialization logic from `Orchestrator.__init__` into the `ServiceContainer`.
    3.  Refactor `Orchestrator` to accept only the `ServiceContainer` in its constructor, from which it will retrieve necessary services.
*   **Outcome:** Immediate simplification of `Orchestrator` and centralized configuration.

### Step 2: Isolate the `IntentPolicyEngine`

*   **Goal:** Establish `IntentPolicyEngine` as the single source of truth for all policies.
*   **Actions:**
    1.  Define a formal interface (`typing.Protocol`) that `IntentPolicyEngine` implements.
    2.  Remove all duplicated policy and validation logic (e.g., `_normalize_goal`, `_goal_similarity`) from `IntentRuntime`.
    3.  Modify `IntentRuntime` to query the `IntentPolicyEngine` through its formal interface for all policy decisions.
*   **Outcome:** Elimination of code duplication. Policy logic becomes isolated, transparent, and easily testable.

### Step 3: Restructure `AgentState` into `TurnContext` + `SessionState`

*   **Goal:** Separate global (session-long) state from transient (turn-specific) state.
*   **Actions:**
    1.  Create a `TurnContext` class to hold all data related to the **current** turn (active intent, counters, temporary errors). `Orchestrator` will instantiate a new `TurnContext` for each user request.
    2.  Rename the existing `AgentState` to `SessionState` and strip it down to only hold data that must persist for the entire session (e.g., history, global settings).
    3.  Refactor all components to receive `TurnContext` as an explicit parameter instead of relying on a global state object.
*   **Outcome:** Clear state separation, improved predictability, and elimination of potential race conditions.

### Step 4: Decompose God Objects (`IntentRuntime` & `ActionDispatcher`)

*   **Goal:** Break down monolithic classes into smaller, single-responsibility components.
*   **Actions:**
    *   From `IntentRuntime`, extract:
        *   `IntentValidator`
        *   `IntentTransitionManager`
        *   `StepBudgetManager`
    *   From `ActionDispatcher`, extract:
        *   `CommandNormalizer`
        *   `BatchPlanner`
        *   `RecoveryPayloadBuilder`
        *   `ToolExecutor`
*   **Outcome:** The system will transform into a collection of simple, understandable, and independent components that interact through well-defined interfaces.

Executing this plan will evolve the current codebase from a monolithic and brittle state into a modular, robust architecture ready for future development.
