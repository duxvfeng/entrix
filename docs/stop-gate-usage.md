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

### Claude 如何调用 Stop Gate

插件的 `hooks/hooks.json` 注册了 `Stop` matcher。Claude Code 准备结束一次操作时，
会把 Stop 事件 JSON 写入 hook 的 stdin，并执行：

```text
Claude Stop 事件
  -> hooks/stop-gate.sh
  -> entrix stop-gate
  -> 阶段判定与 harness.yaml 发现
  -> Evidence Engine
  -> Evidence Store
  -> Gate Engine
```

典型 payload 如下：

```json
{
  "session_id": "current-session",
  "cwd": "D:/project/my-app",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "reason": "agent_completed"
}
```

Hook 契约是退出码 `0`：stdout 为空表示放行；stdout 为
`{"decision":"block","reason":"..."}` 表示阻断。阻断原因会回传给 Claude，
Claude 继续修复后再次尝试停止。MCP 的 `entrix serve` 是主动工具调用通道，
不参与这条任务结束链路。

Stop Gate 只应服务于实现阶段的 DoD。头脑风暴或规划阶段运行：

```bash
entrix phase planning --repo .
```

用户批准开始开发后切换为：

```bash
entrix phase implementation --repo .
```

`entrix init` 会写入一次性初始化阶段，Stop Hook 消费该标记后放行当前回合。阶段状态保存在
独立 CLI 未指定 session 时使用 `.harness/runtime/phase.json`；Stop Hook 收到
`session_id` 后使用用户级缓存中的 workspace/session 状态，属于短期运行时状态，不是 `harness.yaml` 中的永久豁免。没有
阶段标记时，只有检测到工作区变更才进入门禁，兼容直接编辑项目的使用方式。

阶段标记按工作区保存，默认有效 8 小时，不是 Claude 会话级锁。一个仓库存在并发会话时，
后设置的阶段可能覆盖先设置的阶段；开始任何实现工作前都应显式执行
`entrix phase implementation --repo .`，不要依赖遗留的 `planning` 标记。

排查和恢复：

- `entrix status --repo . --session-id <session-id>` 查看当前 phase、Harness trust 和缓存 verdict。
- `entrix doctor --repo .` 检查配置、状态目录、Node.js、OpenSSL 和 MCP runtime。
- `entrix stop-gate retry --repo . --session-id <session-id>` 删除当前 session 的缓存裁决，让下一次 Stop Gate 重新收集证据。
- `entrix phase clear --repo . --session-id <session-id>` 同时清理 session phase 和旧版 workspace phase。

唯一的紧急旁路是：

```bash
ENTRIX_STOP_GATE_DISABLED=1 entrix stop-gate
```

该旁路会在 stderr 写入审计警告，不能作为常规配置项替代门禁。

## 最小严格配置

`settings.failure_mode` 只能是 `closed`。`max_parallel_producers` 是手工 Harness 运行时的
producer 硬上限，缺省为 `1`；Stop Gate 始终串行。每个配置至少包含一个 producer 和一个 Gate：

```yaml
version: "harness/v1"
settings: {failure_mode: closed, max_parallel_producers: 1}
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

## 资源保护

默认 `entrix harness run` 串行收集 producer。需要并行时，必须显式传入 `--parallel`；实际
并发数取 `--max-workers` 请求值与 `settings.max_parallel_producers` 中的较小者：

```bash
entrix harness run --parallel --max-workers 2 --config harness.yaml --json
```

Entrix 不识别或改写 Java 构建命令。一个 Maven 或 Gradle producer 仍可能在内部派生多个 JVM，
所以 Java 项目应在命令或项目配置中限制内部并发：Maven Reactor 用 `-T1`，Surefire/Failsafe
用 `forkCount=1` 和 `reuseForks=true`，Gradle 用 `--max-workers=1`。例如：

```yaml
- id: java-tests
  type: test
  name: Java tests
  command: mvn -B -T1 -DforkCount=1 -DreuseForks=true test
  parser: {type: exit_code}
```

`-Xmx` 只限制单个 JVM 的堆内存。它不能限制 Reactor、测试 fork 或 Gradle worker 的总内存；
项目内限制需要和 Entrix 的外层上限一起使用。

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
