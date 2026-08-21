# Advisory runtime signal template

`harness.fragment.yaml` contains non-blocking observability and performance examples. They are
kept outside Entrix's own production Harness because this repository does not ship the referenced
runtime telemetry or latency probes.

Copy a dimension into a project's `fitness.dimensions` only after replacing its command with a
real, deterministic signal. Keep the dimension weight at zero until the signal is trusted, and set
an explicit owner and execution scope.
