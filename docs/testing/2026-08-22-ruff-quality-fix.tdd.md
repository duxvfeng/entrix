# Ruff 质量修复 TDD 证据

## 来源计划

本轮计划由 Codex `/ecc:plan` 会话确认，目标是修复用户提供的 `ruff check .` 错误，
并完成 RED、GREEN、独立审查及最终验收。

## 用户旅程

- 作为项目维护者，我希望质量检查不因导入排序、异常链或测试脚本风格问题失败，
  以便 CI 能继续验证真正的行为问题。
- 作为发布流程维护者，我希望 release launcher smoke test 保持可读且可被 Ruff 检查，
  以便五平台发布验证不会被静态检查阻断。

## RED -> GREEN

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| RED | `python -m ruff check .` | 失败，4 项：`cli.py`/`hook.py` 两项 `I001`、`shell.py` 一项 `B904`、`release_launcher_smoke.py` 一项 `E731`。 |
| GREEN | `python -m ruff check .` | `All checks passed!` |
| 相关测试 | `pytest tests/test_shell_runner.py tests/test_plugin_binary_contract.py tests/test_release_assets.py tests/test_ci_configuration.py -q` | `56 passed, 1 skipped` |

## 修复保证

| # | 保证 | 测试或检查 | 类型 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | CLI 导入块遵循 Ruff/isort 排序 | `ruff check .` | 静态检查 | PASS |
| 2 | Stop Hook 导入块遵循 Ruff/isort 排序 | `ruff check .` | 静态检查 | PASS |
| 3 | Streaming shell 超时重新抛出的异常明确不携带内部清理异常链 | `tests/test_shell_runner.py`、`ruff check .` | 单元/静态检查 | PASS |
| 4 | Release launcher smoke server 使用具名 handler，行为保持不变 | `tests/test_plugin_binary_contract.py`、`ruff check .` | 集成/静态检查 | PASS |
| 5 | 包可以构建 | `python -m build --no-isolation` | 构建 | PASS，生成 `entrix-0.1.24.tar.gz` 和 wheel |
| 6 | 类型检查通过 | `python -m mypy` | 类型检查 | PASS，24 个源文件 |
| 7 | 完整测试套件通过 | `python -m pytest -q` | 单元/集成 | PASS，`546 passed, 26 skipped` |

## 覆盖率与已知缺口

带覆盖率运行的完整测试同样得到 `546 passed, 26 skipped`，但全项目覆盖率为
`61.77%`，低于 `pyproject.toml` 中现有的 `75%` `fail-under`。该缺口主要来自
尚未覆盖的 CLI、结构分析和 reporter 模块；本次变更只涉及静态质量修复，没有扩大
范围补齐这些既有覆盖率缺口。

## 检查点

- RED/GREEN 修复提交：`2418378 fix(质量): 修复 Ruff 规范错误`
- 独立上下文审查：未发现行为回归或需要追加的业务测试。
