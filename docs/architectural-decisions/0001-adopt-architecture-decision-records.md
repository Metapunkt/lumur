# 0001 — Adopt Architecture Decision Records

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** tooling / documentation

## Context

Lumur is being designed before any code exists. The founding conversation
already contains choices that will be expensive to re-litigate from chat
history: sensing method, runtime shape, hardware limits, and the relationship
with Synesyn. Rationale that lives only in discussion will evaporate between
sessions and between agents.

## Options considered

1. **Keep decisions implicit** in the scratchpad and in future commit messages.
   Zero process overhead, but rationale stays scattered and easy to overwrite.
2. **Numbered ADRs** under `docs/architectural-decisions/`, indexed here, and
   **append-only**. A small per-decision cost; durable and greppable.

## Decision

Adopt ADRs. Files are `NNNN-<slug>.md`, indexed in `README.md`. A reversal is
a new ADR that marks the old one `Superseded by NNNN` rather than editing it
away. The [scratchpad](../scratchpad.md) remains a notebook; it is not the
record of decisions.

## Consequences

- Positive: founding choices are reviewable without reconstructing a chat.
- Trade-off: light overhead per decision, and discipline to record the next
  one.
- Follow-up: product intent is recorded separately, as thin PRDs under
  `docs/product-requirements/`.
