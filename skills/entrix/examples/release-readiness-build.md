# Release Readiness Build

Add this item to `harness.yaml` under `fitness.dimensions`:

```yaml
- dimension: release_readiness
  weight: 10
  threshold: {pass: 90, warn: 80}
  metrics:
    - name: build_pass
      command: npm run build 2>&1
      hard_gate: true
      tier: normal
      description: Production build must pass.
```
