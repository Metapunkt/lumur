# Lumur Product Requirements

Product requirement documents define who a capability serves, which problem it
addresses, what outcome it must produce, its scope, and how success is observed.

PRDs are a thin intent layer. They link to architectural decisions, and later
to user guides, technical contracts, implementation trackers and executable
specs, instead of copying them.

## Product flows

| ID | Product flow | Status | Last reviewed |
|---|---|---|---|
| [PRD-001](PRD-001-CALIBRATE-PAINT-RIPPLE.md) | Calibrate, paint the room, and footstep ripples | Draft | 2026-11-18 |

## Lifecycle

- **Draft:** intent is being consolidated; unresolved gaps are allowed.
- **Review:** evidence is consolidated and ready for product review.
- **Approved:** scope and success conditions are accepted.
- **Implementing:** engineering is active against the approved intent.
- **Shipped:** acceptance conditions are met for the stated version.
- **Parked:** work is explicitly deferred.
- **Superseded:** a successor PRD owns the product intent.

PRDs remain living documents until shipped. After shipping, change product intent
through a new version or successor rather than silently rewriting the original
scope.

## Rules

- Create PRDs for substantial user-facing capabilities, not internal refactors.
- Keep each PRD short. Link detailed workflows and contracts.
- Do not duplicate API payloads, schemas, or task lists.
- Give requirements stable IDs so future run specs and plans can reference them.
- Link an ADR only when an architectural choice affects the product flow.
- Link executable acceptance where a harness can observe the behaviour.
- Record manual acceptance explicitly when automation cannot reproduce the flow.

Use [`_template.md`](_template.md) for new PRDs.
