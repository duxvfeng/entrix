# 最小维度

将此条目添加到 `harness.yaml` 的 `fitness.dimensions` 下：

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
