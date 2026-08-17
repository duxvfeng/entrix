# Design System Dimension Spec

Use this when editing the `design_system` dimension in `harness.yaml`.

## Purpose

Guard component-system fidelity, tokens, accessibility layers, and visual
contracts that are broader than one page shell.

## Typical Signals

- token or CSS contract checks
- component-layer visual regression
- accessibility-focused checks
- design-system coverage matrices

## Boundary

Keep this dimension focused on reusable system quality.

Move page-shell or navigation-shell concerns to `ui_consistency` when the
repository treats them as a separate surface.
