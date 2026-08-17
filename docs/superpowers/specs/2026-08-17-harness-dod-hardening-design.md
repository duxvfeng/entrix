# Harness DoD 强门禁设计

## 目标

把现有 YAML 驱动的 Claude Code Stop Gate 从可用的质量辅助机制强化为默认拒绝、证据可审计、条件可配置的 DoD 门禁。保留当前 `HarnessRunner -> EvidenceEngine -> EvidenceStore -> GateEngine` 主链路，不扩展旧版 `stop_gate.collector` 与 `stop_gate.arbiter`。

本次范围包括：

- 有 Harness 配置时全链路 fail-closed；
- 顶层、producer 和 Gate 三级条件激活；
- `exit_code`、`regex`、JUnit XML、通用 JSON、SARIF、`evidence_json` 六种解析器；
- 标准 Evidence、artifact 引用和 Evidence Bundle 的完整持久化；
- FAIL/BLOCKED 缓存、PASS 强制重验和可靠的工作区指纹；
- 配置校验、路径安全、原子存储和可操作的 Claude 阻断反馈。

不包含远程 Evidence Store、动态第三方 Python 插件、分布式 worker、Web 管理界面或旧 collector 的重构。

## 架构

```text
Claude Code Stop Hook
  -> 定位并严格加载 harness.yaml
  -> 构造 RunContext
       changed_files / branch / base_ref / env / workspace fingerprint
  -> EvidenceEngine
       -> evaluate global and producer when
       -> CommandProducer / BuiltinProducer
       -> ParserRegistry
            exit_code / regex / junit / json / sarif / evidence_json
       -> EvidenceBundle
       -> EvidenceStore
  -> GateEngine
       -> evaluate gate when
       -> arbitrate from Evidence only
  -> PASS: allow Stop
     FAIL/BLOCKED/ERROR: block Stop and return actionable feedback
```

职责边界如下：

- Producer 只负责运行工具和取得原始输出，不决定 Stop 是否放行。
- Parser 只负责把进程输出或报告文件转换为 `evidence/v1`。
- Evidence Store 保存不可变的单次 attempt bundle，不参与业务仲裁。
- Gate Engine 只认识 Evidence、运行上下文和声明式 GatePolicy，不导入 pytest、Playwright、Maven 等工具代码。
- Stop Hook 负责生命周期协议、缓存和最终 fail-closed 行为。

## Harness YAML 契约

```yaml
version: "harness/v1"

settings:
  failure_mode: closed

when:
  files_exist: [package.json]
  changed_any: [frontend/**]
  branch:
    exclude: [docs/**]

evidence_producers:
  - id: web-e2e
    type: test
    name: Web E2E
    command: npx playwright test
    producer: playwright
    timeout_seconds: 300
    when:
      changed_any: [frontend/**]
    parser:
      type: junit
      path: playwright-results.xml
    artifacts:
      - type: junit
        path: playwright-results.xml

gate_policies:
  - name: Frontend tests must pass
    severity: hard
    when:
      changed_any: [frontend/**]
    rule:
      evidence_id: web-e2e
      condition: status == "pass"
```

`settings.failure_mode` 在 v1 中只接受 `closed`。字段可以省略，省略时仍为 `closed`。项目配置不能自行降级为 fail-open。

有效配置至少包含一个 producer 和一个 Gate。若顶层 `when` 已激活，但本次没有任何 Gate 激活，则返回配置/裁决错误并阻断；只有顶层 `when` 明确不满足时，Harness 才以 inactive 状态放行。

## 条件语义

支持 `files_exist`、`changed_any`、`branch.include`、`branch.exclude` 和 `env`：

- 同一个 `when` 中不同谓词为 AND；
- 同一列表中的模式为 ANY；
- `files_exist` 支持仓库相对路径和 glob；
- 条件路径必须解析在工作区内，拒绝绝对路径和 `..` 逃逸；
- 未知谓词和错误类型在配置加载阶段拒绝；
- producer 条件不满足时不执行命令，但生成 `status: skipped` Evidence；
- Gate 条件不满足时生成 inactive GateResult，不参与最终 PASS/FAIL 计算；
- 激活 Gate 引用不存在的 Evidence 时返回 BLOCKED，不能静默 PASS。

顶层 `when` 不满足时仍保存一份 inactive Evidence Bundle，以保留本次 Stop attempt 的审计事实。

## Evidence 契约

每个 producer 产出一个标准对象：

```json
{
  "schema_version": "evidence/v1",
  "id": "web-e2e",
  "type": "test",
  "name": "Web E2E",
  "status": "pass",
  "producer": "playwright",
  "task_id": "session-id",
  "started_at": "2026-08-17T08:00:00Z",
  "duration_ms": 8231,
  "summary": {
    "total": 18,
    "passed": 18,
    "failed": 0,
    "skipped": 0
  },
  "artifacts": [
    {
      "type": "junit",
      "path": "playwright-results.xml",
      "metadata": {}
    }
  ],
  "raw": {}
}
```

Evidence 状态只允许 `pass`、`fail`、`skipped`、`error` 和 `timeout`。Harness 覆盖 `id`、`type`、`name`、`producer`、`task_id`、`started_at` 等身份字段，外部报告不能伪造本次运行上下文。

Evidence Bundle 补充 `attempt_id`、`collected_at`、revision、workspace fingerprint、Evidence 列表和结构化 `collection_errors`。Store 使用临时文件和同目录原子替换写入，写入失败必须阻断，不能只记录错误后继续 PASS。

## Parser Registry

Parser 使用稳定的内部注册表按 `parser.type` 分派。v1 不加载任意 Python import 路径。

### exit_code

退出码 0 映射为 `pass`，其他退出码映射为 `fail`。stdout、stderr 和 exit code 放入 `raw`。

### regex

对 stdout 执行配置的正则表达式，命名捕获组写入 `summary`，整数和小数安全转换为数字。未匹配或正则错误产生 `error` Evidence。

### junit

通过标准 XML 解析器读取工作区内报告文件，聚合所有 `testsuite` 的 tests、failures、errors、skipped 和 time。`failures + errors > 0` 为 `fail`，否则为 `pass`。XML 损坏、缺少报告或数值非法为 `error`。

### json

读取工作区内 JSON，并通过声明式点路径映射取得 status 与 summary 字段。例如：

```yaml
parser:
  type: json
  path: reports/result.json
  status_path: result.status
  status_map: {success: pass, failed: fail}
  summary:
    total: stats.total
    passed: stats.passed
    failed: stats.failed
```

映射器只做字典/列表路径读取，不执行 `eval`、模板或任意函数。

### sarif

读取 SARIF 2.x JSON，聚合 runs、results、ruleId 和 level。默认 `error` 级 result 使 Evidence 为 `fail`；配置可把 `warning` 纳入阻断级别。摘要至少包含 runs、results、errors、warnings、notes 和 rules。

### evidence_json

读取已符合 `evidence/v1` 的 JSON。解析器验证 schema、状态和字段类型，再由 Harness 覆盖身份字段并规范化 artifacts。该解析器为以后让工具原生产出标准 Evidence 的迁移路径。

## Artifact 安全

YAML 中声明的 artifact 会写入 Evidence，不复制任意外部文件。每个路径必须：

- 是工作区相对路径；
- 解析后仍位于工作区内；
- 在 producer 完成后存在且为普通文件；
- 保存为 POSIX 风格的规范化相对路径。

必需的 parser 报告不存在会产生 `error` Evidence；额外 artifact 不存在会写入 `collection_errors` 并使该 Evidence 为 `error`，避免发布不可审计的 PASS。

## Gate 仲裁

GatePolicy 增加可选 `when`。GateResult 增加 `active`，并保留 policy、severity、匹配 Evidence 和错误信息。

- hard：条件对所有匹配 Evidence 为真才通过；任一不满足则 FAIL；
- blocked：任一匹配 Evidence 触发条件即 BLOCKED；
- soft/advisory：记录失败但不改变最终 PASS；
- missing evidence：激活的 hard/blocked Gate 返回 BLOCKED；
- inactive Gate：记录但不计入最终状态；
- zero active gates：顶层 Harness 已激活时返回 BLOCKED。

Gate Engine 不读取 Evidence `raw` 中的工具私有结构作为隐式规则；如需仲裁该字段，parser 必须先把事实提升到稳定的 Evidence 字段或 summary。

## Stop Hook 与错误策略

存在 `harness.yaml` 或 `.harness/harness.yaml` 时执行严格模式：

- 配置错误、Runner 异常、Evidence Store 写入失败和未预期内部异常均输出 `{"decision":"block","reason":"..."}`；
- shell 包装器找不到 `entrix`、`uvx` 或可用 Python 时也输出 block JSON；
- `ENTRIX_STOP_GATE_DISABLED=1` 作为唯一人工紧急旁路，使用时向 stderr 输出审计警告；
- 没有 Harness 配置的项目保持未启用状态并直接放行。

阻断反馈按 Gate 列出 Evidence 状态、摘要、错误和 artifact 路径，使 Claude 能据此继续修复。

## 缓存与工作区指纹

PASS 不作为后续 Stop 的授权缓存，每次新的 Stop 请求都重新执行 Harness。

FAIL/BLOCKED 可以在以下输入全部不变时复用：

- 工作区内容与 Harness 配置；
- 当前分支和 base ref；
- `when.env` 引用的环境变量；
- session id。

任何输入变化都会触发重新取证。Git 指纹只有在 `git rev-parse --show-toplevel` 与受检工作区相同时使用；若工作区只是父仓库的子目录、被忽略目录或非 Git 目录，则对受检目录使用文件系统指纹。Evidence runtime 目录继续位于工作区外，避免证据写入使缓存失效。

## Entrix 子命令提示

CLI 增加独立的 `entrix/cli_hints.py`，集中维护子命令纠错、命令组帮助和成功后的下一步建议。命令 handler 继续只返回退出码，不自行拼接通用提示。

### 拼写纠错

根命令和嵌套命令组都使用统一的 ArgumentParser 子类。仅当 argparse 正在校验 subparser choice 时，使用标准库 `difflib.get_close_matches()` 从该层已注册子命令中选择一个高置信度候选：

```text
$ entrix harnes validate
entrix: error: invalid choice: 'harnes'
你是否想输入：entrix harness validate
```

纠错只针对子命令，不处理文件路径、自由文本或普通参数 choice。没有达到相似度阈值时保留原生错误，不输出猜测。非法命令保持 argparse 退出码 2。

### 缺少子命令

每个命令组在构建 parser 时记录自己的命令路径和帮助 parser。解析成功但没有 leaf handler 时，统一显示当前命令组帮助并返回 0：

- `entrix` 显示根命令帮助和常用入口；
- `entrix harness` 显示 `validate`、`run`；
- `entrix graph`、`entrix hook`、`entrix analyze` 显示各自子命令。

这取代 `main()` 中针对 graph/hook/analyze 的硬编码分支，并修复当前 `entrix harness` 因缺少 `func` 而抛出 AttributeError 的行为。

### 下一步建议

提示模块维护声明式 `tuple[str, ...] -> tuple[str, ...]` 映射。leaf handler 返回 0 后，CLI 根据命令路径打印明确的下一条或数条命令。现有 `cmd_init()` 内硬编码提示迁移到该映射，避免重复。

下一步提示写入 stderr，保护 stdout 的机器可读契约。以下情况自动静默：

- handler 返回非 0；
- `--json`；
- `--output -`；
- `stop-gate`、`serve` 等 Hook、机器协议或长驻命令；
- 映射中没有明确后续动作的命令。

首批映射覆盖 `init -> harness validate -> run -> harness run` 主流程，并让 `review-trigger` 成功后提示执行完整 Harness。提示不自动执行命令，也不改变原命令退出码。

## 测试策略

所有行为按 TDD 实现，每个生产变更之前先看到对应测试以预期原因失败。

- 条件测试：glob、ANY/AND、路径逃逸、未知谓词、producer skipped、Gate inactive；
- parser 测试：六种 parser 的成功、工具失败、缺失文件、损坏文件和路径越界；
- store 测试：完整字段、原子替换、冲突文件名、写入失败；
- arbiter 测试：hard 全匹配、blocked 任一触发、missing evidence、zero active gates；
- hook 测试：运行器缺失、内部异常、紧急旁路、FAIL 缓存、PASS 重跑、嵌套工作区指纹；
- CLI 提示测试：根/嵌套拼写纠错、相似度阈值、命令组帮助、退出码、stderr/stdout 隔离、JSON 静默和下一步映射；
- 集成测试：真实执行 `FAIL -> 修改 -> PASS`，并检查标准 Evidence Bundle 与 Claude block JSON；
- 验证命令：全量 pytest、Ruff、Mypy、Harness 配置校验和 package build。

当前实现前基线为 361 个测试通过、1 个测试失败；唯一失败是仓库内 pytest 临时目录被 Git 识别为父/当前仓库导致的非 Git 指纹用例，本设计明确包含该修复。

## 兼容性与迁移

当前有效的单文件 `harness.yaml` 保持可加载，`settings`、Gate `when` 和新 parser 均为增量能力。以下旧行为有意收紧：

- 空 producer 或空 Gate 配置不再有效；
- 有 Harness 时基础设施错误不再放行；
- producer 条件未命中会保存 skipped Evidence；
- PASS 不再跨 Stop 复用；
- artifact 声明从被动配置变为强校验的 Evidence 引用。

仓库中描述 Stop Hook “未实现”的旧状态文档需要同步标记为历史资料，README 和使用文档需要说明 fail-closed、紧急旁路与 parser 配置。

## 验收标准

1. Claude Stop Hook 在配置仓库内只接受本次新鲜 Evidence 对应的 PASS。
2. 配置、执行、解析、持久化或仲裁异常都产生 block decision。
3. `when` 在顶层、producer 和 Gate 三层按既定语义工作。
4. 六种 parser 均生成可序列化的 `evidence/v1`，artifact 路径可审计且不能逃逸工作区。
5. Gate Engine 不依赖具体测试、构建或扫描工具。
6. FAIL/BLOCKED 在输入未变化时可复用，任一相关输入变化后重新执行；PASS 始终重新执行。
7. Entrix 对根命令和嵌套子命令提供高置信度纠错、缺失子命令帮助和不污染机器输出的下一步建议。
8. 默认测试套件无失败，Ruff、Mypy、配置校验和构建命令成功。
