# MCP 实现与验收状态

Entrix 通过 `entrix serve` 暴露三个 MCP 工具：

- `run_fitness`
- `get_dimension_status`
- `analyze_change_impact`

工具业务逻辑位于 `entrix/server.py` 的普通函数中，FastMCP 层只负责协议注册。这样核心行为可以
在未安装可选依赖时测试，协议层则由专用 CI 验证。

当前自动化覆盖：

- `tests/test_mcp_contract.py`：参数校验、fitness/dimension schema、JSON 序列化、graph 降级与委托。
- `tests/test_mcp_stdio.py`：启动 `python -m entrix serve`，完成 MCP stdio initialize 和 tools/list 握手。
- `.github/workflows/ci.yml` 的 `mcp-contract` job：安装 `.[dev,mcp]` 后执行上述测试。

运行方式：

```bash
python -m pip install -e ".[dev,mcp]"
pytest tests/test_mcp_contract.py tests/test_mcp_stdio.py -q
```

本文不记录固定测试数量；请以命令和 CI 输出为准。
