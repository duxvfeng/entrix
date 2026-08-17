# Minimal Dimension

Add this item to `harness.yaml` under `fitness.dimensions`:

```yaml
- dimension: code_quality
  weight: 20
  threshold: {pass: 90, warn: 80}
  metrics:
    - name: lint_pass
      command: npm run lint 2>&1
      hard_gate: true
      tier: fast
      description: Lint must pass.
```
