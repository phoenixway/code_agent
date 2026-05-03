# Angelica Response Grammar

This grammar documents the top-level response protocol as a small language.
It does not treat the model output as full XML.

## Scope

- Plain text responses are valid.
- XML-like protocol tags are structural only when recognized by the protocol lexer.
- Tags inside inline code, fenced code, or raw `<file_content>` are literals.
- Syntax and semantic/runtime validation are separate phases.

## EBNF

```ebnf
response
  ::= plaintext_response
   | protocol_response ;

plaintext_response
  ::= plaintext_tail ;

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
```

## Lexer Responsibilities

- Recognize structural tags only from the `ProtocolSpec` whitelist.
- Ignore protocol-looking tags inside:
  - inline code
  - fenced code
  - quoted literal examples
  - raw `<file_content>` payload
- Apply conservative structural-boundary rules.
- Preserve spans for diagnostics and replay.

## Semantic Notes

- `FILE_CONTENT_BLOCK` is allowed only when paired with a write-like action.
- `READ_ONLY_BATCH_CANDIDATE` is valid only when there is no intent block and every action is read-only.
- `INTENT_ACTION_OUTPUT` is atomic and requires exactly one action.
- Action arrays are rejected inside atomic bundles.
- Multiple `<action>` blocks are rejected inside atomic bundles.
- Visible text mixed with action/control is invalid except for the defined intent-complete-with-text shape.
- Plan/memory tags are operational context, not dispatch authority.

## Current Implementation Choice

- Parser is hand-written.
- Lexer is custom and markdown-aware.
- `ProtocolSpec` is the shared artifact for blocks, shapes, constraints, and error codes.
- Code generation from the spec is deferred until grammar stability improves.
