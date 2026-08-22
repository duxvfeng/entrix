# 跨平台命令入口修复 TDD 证据

## 来源计划

来源为用户 `/ecc:plan` 请求，目标是修复 Windows CI 的 SARIF 回归失败，并修复
VS Code tag 推送任务在没有 `python` 命令时无法启动的问题。仓库未安装
`ecc-plan-canvas` CLI，因此本轮未能启动画布审批；计划和审查结论通过本报告及代码
测试保留。

## 用户旅程

- 作为项目维护者，我希望 SARIF 命令失败在 Windows、macOS 和 Linux 上都被识别为
  `SARIF command failed`，以便错误诊断不被空 stdout 的解析错误覆盖。
- 作为 VS Code 用户，我希望 tag 推送任务使用当前选中的 Python 解释器，而不是依赖
  PATH 中恰好存在名为 `python` 的命令，以便任务在 macOS、Windows 和虚拟环境中可用。

## RED -> GREEN

| 阶段 | 命令或证据 | 结果 |
| --- | --- | --- |
| RED | 用户提供的 Windows CI：`printf broken >&2; exit 2` | 失败，实际输出为 `SARIF parse error: empty stdout`，期望包含 `SARIF command failed`。根因是 POSIX 命令分隔符不能作为 Windows `cmd.exe` 命令使用。 |
| RED | `pytest tests/test_task_configuration.py::test_tag_tasks_use_the_selected_python_interpreter -q` | 失败，现有任务命令为 `python`，不等于 `${command:python.interpreterPath}`。 |
| RED | 同一回归测试增加 `type == process` 断言 | 失败，现有任务类型为 `shell`。 |
| GREEN | `pytest tests/test_task_configuration.py tests/test_sarif_runner.py -q` | `9 passed`。 |
| GREEN | `env PATH=<interpreter-alias>:$PATH PYTHONPATH=/Users/apple/entrix python3 -m pytest -q` | `547 passed, 26 skipped`。 |

## 修改保证

| # | 保证 | 测试或检查 | 类型 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | SARIF 命令非零退出时保留 `SARIF command failed` 错误分类 | `tests/test_sarif_runner.py::test_sarif_runner_returns_unknown_when_command_fails` | 回归测试 | PASS |
| 2 | SARIF 失败测试不依赖 POSIX `printf`、`;` 或 shell 重定向 | `tests/test_sarif_runner.py` | 跨平台单元测试 | PASS |
| 3 | GitHub/Gitee tag 任务使用 VS Code 当前 Python 解释器 | `tests/test_task_configuration.py::test_tag_tasks_use_the_selected_python_interpreter` | 配置回归测试 | PASS |
| 4 | Python tag 任务以 process 模式传递解释器路径，避免 shell 路径引号问题 | 同上 | 配置回归测试 | PASS |
| 5 | `.vscode/tasks.json` 仍保持 remote 参数和顺序编排 | `tests/test_task_configuration.py` | 配置测试 | PASS |
| 6 | 静态质量检查通过 | `python3 -m ruff check .` | 静态检查 | PASS |
| 7 | 类型检查通过 | `python3 -m mypy` | 类型检查 | PASS，24 个源文件 |
| 8 | 包可以构建 | `python3 -m build --no-isolation` | 构建 | PASS，生成 `entrix-0.1.24` sdist 和 wheel |

## 覆盖率与已知缺口

使用正确的解释器 PATH 运行覆盖率后，测试结果为 `547 passed, 26 skipped`，但总覆盖率
为 `61.77%`，低于 `pyproject.toml` 中现有的 `75%` `fail-under`。缺口主要来自
结构分析、CLI 和 reporter 等既有模块；本次只修改跨平台回归测试和 VS Code 任务配置，
没有为无关模块扩大范围。

## Fresh-context 审查

重新从最终 diff 检查了三个代码/配置文件：生产 SARIF runner 未被改动，回归测试覆盖了用户
报告的失败语义，VS Code 两个 Python 任务使用 `${command:python.interpreterPath}`
和 `process` 类型。未发现行为回归或需要追加的测试。
