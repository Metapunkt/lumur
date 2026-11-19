# 0021 — Godot import step before `class_name` use

- **Status:** Accepted
- **Date:** 2026-11-19
- **Area:** godot / ci / developer experience
- **Relates to:** ADR 0004
- **Refines:** first-run workflow for the Godot 4 addon

## Context

Godot 4 resolves `class_name` via the `.godot/` global class cache. A fresh
checkout without that cache fails GDScript parse until the editor (or an
import pass) has run once. CI previously skipped Godot or continued on error,
so the failure mode was easy to miss.

## Decision

Document and script a headless import (`tools/godot_import.sh`: prefer
`godot --headless --import`, else `--editor --quit`). README quickstart, local
tests that need Godot, and CI all run this before loading demos or
Godot-marked pytest. The Godot CI job downloads Godot 4.3 and does **not** use
`continue-on-error`.

## Consequences

- First-run and CI need network (or a cached binary) and a short import step.
- Addon / demo scripts that rely on `class_name` are reliable after import.
