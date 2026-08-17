Add this metric under the appropriate `harness.yaml` `fitness.dimensions[].metrics` list:

```yaml
- name: graph_test_radius_probe
  command: graph:test-radius
  tier: normal
  execution_scope: ci
  gate: advisory
  kind: holistic
  analysis: static
  evidence_type: probe
  confidence: medium
  stability: deterministic
  run_when_changed:
    - src/**
    - crates/**
  description: Estimate whether changed targets still have adequate test radius.
```
