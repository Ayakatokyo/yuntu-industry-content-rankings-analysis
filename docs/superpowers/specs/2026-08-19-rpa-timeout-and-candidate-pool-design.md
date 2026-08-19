# RPA Timeout And Candidate Pool Design

## Goal

Prevent a single unresponsive RPA request from blocking a rankings-analysis batch while retaining enough ranked candidates to replace failed detail requests.

## Decisions

- The rankings-list RPA request and every material-detail RPA request use a 300-second transport timeout.
- A list timeout remains terminal for the batch and is recorded through the existing `list_failed` path.
- A detail timeout is already converted into a per-material rejection by the batch worker; the worker continues in ranking order until it reaches `targetTopN` successful materials or exhausts the candidate pool.
- When omitted, `candidateTopN` is `targetTopN * 2`. An explicitly supplied `--candidate-top-n` remains authoritative.

## Scope

Modify the connector's gateway timeout and default candidate-pool calculation, synchronize the skill contract, and add regression coverage. The batch scheduler and retry semantics remain unchanged.

## Verification

Tests must demonstrate that both invocation types send `timeout=300`, and that a target of five uses ten candidates by default. The full test suite must pass.
