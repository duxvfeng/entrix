---
dimension: release_readiness
weight: 20
tier: normal
threshold:
  pass: 100
  warn: 90
metrics:
  - name: build_pass
    command: python -c "print('build passed')"
    hard_gate: true
    tier: fast
    description: The repo's release wrapper must stay runnable.
---

# Release Readiness

This fixture proves that build or packaging signals can remain in the local
bootstrap path when the repository already exposes a cheap wrapper.
