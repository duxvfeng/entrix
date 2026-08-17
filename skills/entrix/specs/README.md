# Fitness Skill Specs

Use this index the same way `slide-skill/artifact_tool/README.md` is used: it
is a second-level map, not the full implementation.

## Foundation Specs

- `harness-schema.spec.md`: required and optional `harness.yaml` fields, plus
  when to use advanced metric metadata.
- `dimension-boundaries.spec.md`: how to decide whether a metric belongs in an
  existing dimension or a new quality surface.

## Dimension Specs

- `dimension-code-quality.spec.md`
- `dimension-engineering-governance.spec.md`
- `dimension-testability.spec.md`
- `dimension-security.spec.md`
- `dimension-api-contract.spec.md`
- `dimension-release-readiness.spec.md`
- `dimension-design-system.spec.md`
- `dimension-ui-consistency.spec.md`
- `dimension-runtime.spec.md`

## Examples

- `../examples/minimal-dimension.md`
- `../examples/advisory-probe-metric.md`
- `../examples/runtime-zero-weight-dimension.md`
- `../examples/entry-doc-topology.md`
- `../examples/ci-scoped-authoritative-metric.md`
- `../examples/toolchain-boundary-ci-scope.md`

## Reading Guidance

Read only the specs needed for the current task:

- adding or editing metrics: `harness-schema.spec.md` + one dimension spec
- adding or consolidating dimensions: `dimension-boundaries.spec.md`
- deciding whether to add a dimension: `dimension-boundaries.spec.md`
- adding runtime evidence: `dimension-runtime.spec.md`
- deciding what to do with build or packaging signals:
  `dimension-release-readiness.spec.md`
- resolving agent-entry ambiguity: `../examples/entry-doc-topology.md`
- modeling CI-only authoritative checks:
  `../examples/ci-scoped-authoritative-metric.md`
- modeling local toolchain boundaries:
  `../examples/toolchain-boundary-ci-scope.md`
