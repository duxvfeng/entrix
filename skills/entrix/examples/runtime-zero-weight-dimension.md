# Zero-Weight Runtime Dimension

Add this item to `harness.yaml` under `fitness.dimensions` when the signal is
valuable but not trustworthy enough for the weighted local score:

```yaml
- dimension: observability
  weight: 0
  threshold: {pass: 100, warn: 80}
  metrics:
    - name: tracing_signal_available
      command: ./scripts/obs/check-tracing-signal.sh 2>&1
      pattern: signal_ok
      tier: deep
      execution_scope: staging
      gate: advisory
      evidence_type: probe
      confidence: high
      stability: noisy
      description: Verify tracing signal is visible in staging.
```
