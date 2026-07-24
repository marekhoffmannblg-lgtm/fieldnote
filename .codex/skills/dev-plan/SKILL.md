---
name: dev-plan
description: Plan technical implementations as durable, reviewable documents built from requirements, repository research, explicit decisions, risks, file paths, test scenarios, and sequenced Implementation Units. Use when the user asks to plan a feature, bug fix, refactor, migration, or cross-cutting engineering change without implementing code; when converting a requirements document into an executable technical plan; or when updating an existing plan in docs/plans/.
---

# Dev Plan

Create a technical implementation plan. Do not implement code, run runtime experiments, or execute the plan.

## Input

Accept either:

- a feature, bug-fix, refactor, or migration description;
- a path to an existing requirements or plan document;
- an instruction to resume or revise a recent plan.

If the input is unclear, ask one blocking question at a time. Prefer a concise single-choice question when natural options exist.

## Core workflow

1. Check `docs/CONCEPTS.md` when present and use its domain terminology.
2. Locate a relevant recent `docs/brainstorms/*-requirements.md` and treat it as the source of truth when one exists.
3. Resolve product-scope blockers before technical planning. Keep runtime-dependent unknowns explicitly deferred to implementation.
4. Research the repository before structuring the plan. Identify existing patterns, affected files, tests, project guidance, and institutional knowledge.
5. Decide whether external research materially improves accuracy. Skip it when local patterns are sufficient.
6. For UI work, identify the design source of truth before creating Implementation Units.
7. Write a portable plan with traceable requirements, scope boundaries, technical decisions, exact file paths, dependencies, risks, test scenarios, and automated verification criteria.
8. Save the plan under `docs/plans/YYYY-MM-DD-NNN-<type>-<descriptive-name>-plan.md` before offering next steps.
9. Never implement the plan in this workflow.

## Required plan qualities

- State the problem and explicit non-goals.
- Trace requirements back to the user request or source document.
- Prefer decisions and rationale over code snippets or shell choreography.
- Use checkable Implementation Units sized like atomic commits.
- Include exact implementation and test file paths.
- Separate automated verification from manual operator checks.
- Record unresolved implementation discoveries instead of inventing certainty.
- Keep the plan compact for small work and deeper only when risk or scope justifies it.

## Detailed procedure and template

Read [references/dev-plan-workflow.md](references/dev-plan-workflow.md) before producing a plan. It contains the complete phase workflow, UI/design handling, Implementation Unit structure, delegation guidance, plan template, review checklist, save rules, and handoff options.

## Compatibility notes

- Use platform-native question, repository exploration, design, and browser tools when available.
- When a named tool or subagent from the reference is unavailable, preserve the intent with the closest available capability rather than fabricating execution.
- Treat references to `/dev-brainstorm`, `/dev-docs`, and `/dev-docs-execute` as handoff conventions; do not claim they ran unless they are actually available and invoked.
