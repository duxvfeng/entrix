# Dimension Boundaries Spec

This file answers the main design question: should each dimension be a separate
spec?

## Short Answer

Usually, a stable dimension should have its own spec guidance. But a dimension
is not the only boundary that matters.

Use three layers:

- skill entrypoint for workflow
- foundation specs for shared rules
- dimension specs for stable quality surfaces

## Important Distinctions

- `dimension` is an execution and reporting concept used by Entrix
- `dimension` is one uniquely named item in `harness.yaml` under
  `fitness.dimensions`
- `skill spec` is agent-facing reference material

These three layers often align, but they do not have to be identical.

## When One Dimension Deserves Its Own Spec

Create a dedicated dimension spec when the quality surface has:

- distinct goals
- distinct metric patterns
- distinct owners or reviewers
- distinct failure meaning
- a stable place in CI or scoring

Examples in Routa.js:

- `code_quality`
- `engineering_governance`
- `testability`
- `security`
- `api_contract`
- `release_readiness`
- `design_system`
- `ui_consistency`

## When To Merge Or Group

Group small or closely related surfaces into one spec when they share most of
the same authoring rules.

Example:

- `observability` and `performance` are both runtime evidence surfaces with
  weight `0`, so one `dimension-runtime.spec.md` is enough for skill guidance.

## When One Dimension Has Multiple Metrics

A single dimension can keep multiple executable checks in its `metrics` list.
Use metric metadata such as `tier`, `execution_scope`, and `run_when_changed`
to express lifecycle differences without splitting configuration across files.

## Decision Rules

Ask these questions in order:

1. Is this a new concern, or just a new metric inside an existing concern?
2. Does the concern already have a stable dimension name?
3. Does the concern need separate metrics for distinct checks, such as shell
   coverage and an E2E matrix?
4. Is there a real build or packaging signal that should become
   `release_readiness` instead of being ignored?
5. Would merging increase confusion more than it reduces file count?

## Authoring Recommendation

For most repositories:

- one foundation spec for schema
- one foundation spec for split vs merge rules
- one skill spec per stable dimension family
- one or more examples

That gives agents enough structure without recreating a giant monolith.
