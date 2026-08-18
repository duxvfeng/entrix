# 工具链边界示例

如果仓库明确使用某个命令，但当前机器低于所需的运行时或编译器版本，应保留该信号，
同时不要污染默认本地路径。

将以下 metric 添加到适用的 `harness.yaml` `fitness.dimensions[].metrics` 列表中：

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
