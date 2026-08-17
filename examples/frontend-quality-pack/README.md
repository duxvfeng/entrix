# Frontend Quality Pack

This example shows how a consuming web application can express layered frontend
quality gates in one `harness.yaml` without hardcoding product-specific policy
into the Entrix engine.

It models four surfaces:

- `code_quality`: CSS and token-hygiene style checks
- `design_system`: component-layer accessibility and visual-contract checks
- `ui_consistency`: page-shell and browser-flow consistency checks
- `performance`: zero-weight runtime/perf smoke guidance

## Layout

Copy `harness.yaml` into your application repository and adapt the commands,
dimensions, review triggers, producers, and gate policies to your own scripts.

## Suggested Commands

```bash
entrix validate
entrix run --tier fast
entrix run --tier normal --scope ci --min-score 0
entrix review-trigger --base HEAD~1
```

## Why This Pack Exists

The point is not to prescribe Storybook, Chromatic, Playwright, or Lighthouse as
mandatory tooling. The point is to show a reusable shape:

- cheap local code-quality checks
- CI-scoped component and page checks
- zero-weight performance evidence until runtime collection is trustworthy
- review-trigger rules that escalate risky shell and navigation changes
