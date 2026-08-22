# Entrix 当前改进路线图

> 更新日期：2026-08-22。本文只记录当前未完成工作；历史实施计划保留在
> `docs/superpowers/plans/`，不能作为当前测试或功能状态依据。

## 已完成

- [x] Harness 配置、Evidence 收集、Gate 仲裁和 Stop Hook 路由统一。
- [x] pytest 使用可并发、按进程隔离的临时目录，并加入 Windows CI。
- [x] Harness 自检命令移除 POSIX-only 管道和 `python3` 可执行文件假设。
- [x] MCP 三个公开工具增加行为、返回 schema 和真实 stdio 握手测试。

## 当前优先级

### 质量信号

- [x] 扩大 mypy 覆盖范围至 MCP server、reporting、reporters、CLI hints 和 graph runner。
- [x] 在 CI 生成覆盖率报告，并以 75% 作为初始基线阈值。
- [x] 将 observability/performance 占位探针移出生产 Harness，保留为显式示例。

### CI 与发布

- [x] 由基础 CI 执行完整测试，Defense workflow 只执行 fast/ci 变更治理检查。
- [x] 自动发布 pytest/JUnit、coverage、fitness 和 review-trigger 摘要/工件。
- [x] 保持发布 workflow 的五平台二进制、checksum、签名和版本一致性验证，
  并在上传前执行启动器 smoke test；同名 Release 资产允许覆盖更新。

### 结构治理

- [x] 第一阶段从 `entrix/cli.py` 抽取 runtime persistence 与 overview rendering，
  保持兼容入口、stdout/stderr 和退出码不变。
- [x] 第一阶段从 `entrix/structure/builtin.py` 抽取语言扩展名、AST 节点类型和查询类型元数据。
- [x] 将两个 legacy override 分别从 2053/1662 收紧至 1780/1591 行。
- [ ] 继续按 `run`、`harness`、`graph`、`release`、`hook` 拆分 CLI 命令实现。
- [ ] 继续迁移 Python/TypeScript 与 Go/Rust/Java 的结构分析适配逻辑。

## 验收基线

```bash
ruff check .
pytest -q
mypy
python -m build --no-isolation
python -m entrix harness validate harness.yaml
python -m entrix run --tier normal --scope local --min-score 0
python -m entrix harness run --config harness.yaml --json
```

MCP 可选依赖验收：

```bash
python -m pip install -e ".[dev,mcp]"
pytest tests/test_mcp_contract.py tests/test_mcp_stdio.py -q
```
