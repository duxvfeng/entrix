# CI 范围的权威 Metric

当真实测试套件需要 CI 提供环境、但默认本地路径必须保持绿色时，使用此
`harness.yaml` 维度：

```yaml
- dimension: testability
  weight: 40
  threshold: {pass: 100, warn: 90}
  metrics:
    - name: import_smoke
      command: python3 -c "import app; print(app.answer())" 2>&1
      hard_gate: true
      tier: fast
      description: Cheap local smoke check.
    - name: pytest_suite
      command: python3 -m pytest -q 2>&1
      hard_gate: true
      tier: normal
      execution_scope: ci
      description: Full suite runs in the provisioned CI environment.
```
