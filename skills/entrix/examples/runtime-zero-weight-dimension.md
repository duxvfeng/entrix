# 零权重运行时维度

当信号有价值、但可靠性不足以纳入本地加权评分时，将此条目添加到
`harness.yaml` 的 `fitness.dimensions` 下：

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
