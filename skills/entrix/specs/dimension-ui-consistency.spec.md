# UI Consistency Dimension Spec

Use this when editing the `ui_consistency` dimension in `harness.yaml`.

## Purpose

Guard end-user consistency across shells, key journeys, and high-value UI
surfaces.

## Typical Signals

- shell coverage checks
- page-level navigation or layout evidence
- manual or automated QA matrices
- browser-flow validation for critical journeys

## Split Guidance

This dimension is a good candidate for multiple evidence files when the
repository needs to separate:

- shell-level consistency
- web QA or e2e journey evidence

If you keep the same dimension name across files, explain the split clearly in
the file body and keep manifest entries accurate.
