# Claude Stop Gate 使用指南

Entrix Harness 将 Stop Hook、物证收集和门禁裁决分开：Hook 负责生命周期，
Evidence Engine 只产生标准化 Evidence，Gate Engine 只根据 Evidence 仲裁。
因此，同一套运行时可用不同的 `harness.yaml` 适配不同项目的 DoD。

## Stop 行为

安装 Claude Code 插件后，`hooks/stop-gate.sh` 调用 `entrix stop-gate`。没有
`harness.yaml` 或 `.harness/harness.yaml` 的工作区不会启用 Harness；一旦找到配置，
以下路径均为 fail-closed：配置无效、收集器异常、Evidence 保存失败、Gate 无法裁决或
运行器不可用时，Hook 都输出 `{"decision":"block","reason":"..."}`。

`PASS` 不会缓存，下一次 Stop 必定再次运行 producer。未变化工作区上的 `FAIL`、
`BLOCKED` 与 `error` 会缓存，避免代理重复执行已知失败的慢检查。工作区内容、分支、
base ref、Harness 配置或 `when.env` 依赖发生变化时，缓存失效并重新收集。

唯一的紧急旁路是：

```bash
ENTRIX_STOP_GATE_DISABLED=1 entrix stop-gate
```

该旁路会在 stderr 写入审计警告，不能作为常规配置项替代门禁。

## 最小严格配置

`settings.failure_mode` 只能是 `closed`。每个配置至少包含一个 producer 和一个 Gate：

```yaml
version: "harness/v1"
settings: {failure_mode: closed}
evidence_producers:
  - id: api-test
    type: test
    name: API tests
    command: pytest -q --junitxml=artifacts/api.xml
    producer: pytest
    parser: {type: junit, path: artifacts/api.xml}
gate_policies:
  - name: API tests pass
    severity: hard
    rule: {evidence_id: api-test, condition: 'status == "pass"'}
```

每个成功或失败的收集都会写入标准 Evidence Bundle，保存位置由 Stop Hook 的外部状态目录
控制。Gate 不识别 `pytest`、Playwright 或 Maven 等工具名，只识别如 `status`、`summary`
和 artifact 构成的 Evidence。

## 条件激活

`when` 可出现在 Harness、producer、Gate 三个层级。块内谓词为 AND，模式列表为 ANY：

```yaml
when:
  changed_any: [frontend/**]
  files_exist: [package.json]
  branch:
    exclude: [docs/**]

evidence_producers:
  - id: ui-tests
    type: test
    name: UI tests
    when: {changed_any: [frontend/**]}
    command: npm test -- --reporter=junit
    parser: {type: junit, path: reports/junit.xml}
```

未激活的 Harness 保存 `active: false` Bundle 并跳过裁决；未激活的 producer 会产生
`skipped` Evidence；未激活的 Gate 仅记录为非活动。活动 Harness 中缺失必要 Evidence，
或没有任何活动 Gate，都会得到 `BLOCKED`。

## 报告 Parser

所有报告路径都必须相对工作区，不能逃逸工作区。命令 producer 支持：

- `exit_code`：进程退出码。
- `regex`：从 stdout / stderr 捕获字段。
- `junit`：聚合 JUnit XML 的测试数、失败数与 artifact。
- `json`：用只读点路径映射项目自有 JSON 报告。
- `evidence_json`：导入已经符合 `evidence/v1` 的标准 Evidence。
- `sarif`：聚合 SARIF 2.x 结果，默认 `error` 会失败。

自有 JSON 报告映射示例：

```yaml
parser:
  type: json
  path: reports/api.json
  status_path: result.status
  status_map: {success: pass, failed: fail}
  summary: {total: stats.total, failed: stats.failed}
```

SARIF 示例：

```yaml
parser:
  type: sarif
  path: reports/scan.sarif
  blocking_levels: [error, warning]
```

标准 Evidence 输入示例。Harness 保留自己的 `id`、`type`、`producer`、任务和时间身份，
不会信任输入文件对这些字段的覆盖：

```json
{
  "schema_version": "evidence/v1",
  "status": "pass",
  "summary": {"total": 18, "passed": 18, "failed": 0},
  "artifacts": [{"type": "junit", "path": "artifacts/api.xml"}]
}
```

```yaml
parser: {type: evidence_json, path: reports/api-evidence.json}
```

## 本地检查

```bash
entrix harness validate harness.yaml
entrix harness run --config harness.yaml --json
echo "{\"session_id\": \"manual-check\", \"cwd\": \"$PWD\"}" | entrix stop-gate
```

第二条命令输出裁决和 Evidence；第三条命令在失败时只输出 Claude Hook 契约所需的 block
JSON。生产接入前至少手工验证一次：失败被阻断、修复后通过、设置紧急旁路时 stderr 出现
审计警告。
