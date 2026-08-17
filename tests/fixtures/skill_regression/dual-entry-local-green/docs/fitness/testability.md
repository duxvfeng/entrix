---
dimension: testability
weight: 40
tier: normal
threshold:
  pass: 100
  warn: 90
metrics:
  - name: tests_pass
    command: python -c "print('tests passed')"
    hard_gate: true
    tier: fast
    description: The repository test wrapper must pass.
---

# Testability

This fixture keeps behavioral evidence locally runnable.
