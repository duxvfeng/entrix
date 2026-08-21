# 测试状态说明

> 本文不再保存手工测试数量。测试数量和通过状态会随代码变化，当前事实以 CI 和本地命令输出为准。

## 标准验证

```bash
ruff check .
pytest -q
mypy
python -m build --no-isolation
```

CI 在 Python 3.11、Python 3.12 和 Windows Python 3.12 上执行基础验证。MCP 可选依赖由
独立 `mcp-contract` job 安装，并执行工具行为契约和真实 stdio 握手测试。

## Windows 临时目录

pytest 通过 `tests/conftest.py` 为每个进程选择 `.pytest-runs/tmp-<pid>`，避免多个任务共享
同一个 `basetemp` 导致 ACL 或文件锁错误。`.pytest-runs/` 是本地产物并已忽略。

如果测试出现环境级错误，应先区分：

- assertion failure：实现或契约回归；
- setup/permission/tool unavailable：测试基础设施问题；
- skipped：可选平台或可选依赖未安装。

不得以“非核心测试”为由跳过 Stop Gate、MCP 或发布契约失败。
