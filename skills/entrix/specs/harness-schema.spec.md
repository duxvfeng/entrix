# Harness Schema Spec

Entrix reads one repository-root `harness.yaml`. The file contains all
executable Fitness, review, evidence, and gate policy data.

## Required Shape

```yaml
version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
review_triggers: {rules: []}
evidence_producers: []
gate_policies: []
```

## Dimension Rules

- `fitness.dimensions` is a list of uniquely named dimensions.
- Each dimension has `dimension`, non-negative `weight`, `threshold`, and a
  `metrics` list.
- Active weighted dimensions must total exactly `100`.
- Metric names are unique within a dimension. Each metric needs a non-empty
  `name` and `command`.
- Use `snake_case` for dimension and metric names.

## Metric Fields

Start with `name`, `command`, `pattern`, `hard_gate`, `tier`, and
`description`. Add `execution_scope`, `timeout_seconds`, `gate`,
`evidence_type`, `confidence`, `stability`, `kind`, `analysis`, `owner`,
`run_when_changed`, or `waiver` only when there is a repository-specific need.

Commands run from the repository root. Prefer existing repository wrappers and
put CI-only authority behind `execution_scope: ci`.

## Review, Producers, and Gates

- Put review rules in `review_triggers.rules`.
- Define command or builtin producers in `evidence_producers`.
- Reference one evidence id or type from each `gate_policies[].rule`.
- Use `entrix-fitness`, `entrix-review-trigger`, and `diff-stats` for Entrix's
  builtin producers.

## Anti-Patterns

- duplicate dimension or metric names
- weights that do not total `100`
- placeholder commands such as `echo TODO`
- local hard gates that depend on uninstalled tooling
- separate files for dimensions, manifests, or review rules
