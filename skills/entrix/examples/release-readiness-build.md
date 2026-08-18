# Release Readiness 构建

将此条目添加到 `harness.yaml` 的 `fitness.dimensions` 下：

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
