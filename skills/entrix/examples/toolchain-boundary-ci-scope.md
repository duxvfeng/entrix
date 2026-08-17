# Toolchain Boundary Example

If the repository clearly uses a command but the current machine is below the
required runtime or compiler version, preserve the signal without poisoning the
default local path.

Add these metrics under the appropriate `harness.yaml` `fitness.dimensions[].metrics` list:

```yaml
- name: local_smoke
  command: cargo fmt --manifest-path crates/app/Cargo.toml --all --check 2>&1
  hard_gate: true
  tier: fast
  description: Cheap local wrapper that still runs on the current machine.

- name: clippy_workspace
  command: cargo clippy --workspace --all-targets -- -D warnings 2>&1
  hard_gate: true
  tier: normal
  execution_scope: ci
  description: The authoritative workspace lint requires the repo's CI Rust toolchain.
```
