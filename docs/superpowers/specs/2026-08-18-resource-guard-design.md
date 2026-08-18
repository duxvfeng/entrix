# Entrix 资源保护升级设计

## 目标

避免 Harness 和 Fitness 在资源敏感的项目中无意启动多个重量级构建命令。重点覆盖 Maven、Surefire、Failsafe 和 Gradle 等可能继续派生多个 JVM 的工具，同时保持 Evidence 和 Gate 的工具无关性。

本次升级不试图根据命令文本猜测 Java、Maven 或 Gradle，也不改写目标项目的 `pom.xml`、`build.gradle` 或构建命令。Entrix 负责限制自身启动的外层并发；项目配置负责限制构建工具内部的进程与线程并发。

`entrix init` 是初始化命令，不是检查命令。它只能创建或重建 `.mcp.json` 与 `harness.yaml`，不得直接或通过成功后的自动工作流执行 `harness validate`、`run`、`harness run` 或 Stop Gate。Claude 在初始化完成后必须询问用户是否继续检查，并仅在收到明确肯定答复后运行检查命令。

## 问题与根因

当前系统存在两个独立的并发层：

1. Fitness 层：`entrix run --parallel` 会让 `ShellRunner` 同时执行多个 metric，当前 worker 数固定为 4。
2. Harness 层：`HarnessRunContext.parallel_producers` 默认值为 `True`。因此手工执行 `entrix harness run` 时，`EvidenceEngine` 最多并行执行 4 个 producer。

Stop Hook 的 `HarnessRunner` 显式传入 `parallel_producers=False`，因此它目前保持串行，但手工 Harness 命令与 Stop Hook 的默认资源语义不一致。

外层的一次 Maven producer 还可能因 Maven Reactor 的 `-T`、Surefire/Failsafe 的 `forkCount`，或 Gradle worker 配置派生额外 JVM。`-Xmx256m` 仅限制一个 JVM 堆，不能限制所有 JVM 的总内存。

## 设计原则

- 默认串行：没有显式并行意图时，每次只启动一个 Harness producer 或 Fitness metric。
- 配置上限优先：CLI 请求的 worker 数不得超过 `harness.yaml` 中的资源上限。
- Stop Hook 保守：Stop Hook 始终串行收集 producer，不因项目配置而提高并发。
- 工具无关：核心运行时不识别 Maven、Surefire、Gradle 或 Java 命令。
- 分层控制：Entrix 限制外层命令数；项目命令限制构建工具内部 fork 数。
- 可验证：配置校验、并发行为和 CLI 参数均有自动化测试。

## 配置契约

`settings` 增加可选字段 `max_parallel_producers`：

```yaml
version: "harness/v1"
settings:
  failure_mode: closed
  max_parallel_producers: 1
```

约束：

- 缺省值为 `1`。
- 必须是正整数，布尔值无效。
- 它是 Harness producer 的硬上限，而非自动开启并行的开关。

Java 项目应在命令本身限制内部并发。示例：

```yaml
fitness:
  dimensions:
    - dimension: java_build
      weight: 100
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: compile_fast
          command: mvn -B -T1 -Dmaven.test.skip=true compile
          tier: fast
          hard_gate: true
          timeout_seconds: 600
        - name: tests_serial
          command: mvn -B -T1 -DforkCount=1 -DreuseForks=true test
          tier: normal
          hard_gate: true
          timeout_seconds: 1200
```

`-T1` 限制 Maven Reactor，`forkCount=1` 与 `reuseForks=true` 限制测试 JVM。若 POM 固定了 Surefire/Failsafe 配置，应在对应插件配置中设置相同值。Gradle 项目应使用 `--max-workers=1`。

## 运行时设计

### Harness

`HarnessRunContext.parallel_producers` 的默认值改为 `False`。`HarnessRunContext` 增加可选的 `max_parallel_producers` 请求值。

`EvidenceEngine` 根据以下规则计算有效 worker 数：

```text
parallel_producers 为 false  -> 1
parallel_producers 为 true   -> min(context 请求值（缺省为配置上限）, 配置上限)
```

当有效 worker 数为 1 时，按配置顺序串行执行 producer；大于 1 时，使用该数值创建 `ThreadPoolExecutor`。Stop Hook 继续传入 `parallel_producers=False`，不会变为并行。

手工命令增加：

```text
entrix harness run --parallel --max-workers 2
```

未指定 `--parallel` 时串行。`--max-workers` 必须是正整数；配置上限为 1 时，即使显式传入 `--parallel` 也只能串行。

### Fitness

`GovernancePolicy` 增加 `max_workers`，默认仍为 4 以保持现有 `entrix run --parallel` 的显式并行兼容性。CLI 增加 `--max-workers N`，将值传递至 `run_fitness_report()`、`_run_metric_batch()` 和 `ShellRunner.run_batch()`。不加 `--parallel` 时该值不生效，保持串行。

这不改变 `entrix run --tier fast` 的默认串行行为；Java 项目应避免使用 `--parallel`，或显式使用 `--max-workers 1`。

### 超时与进程树

不修改现有超时行为。`ShellRunner` 和 `CommandProducer` 已在 Windows 使用 `taskkill /T /F`、在 POSIX 使用独立进程组终止超时命令及其后代。该机制用于清理超时任务，不替代正常的并发限制。

### 初始化与用户确认

`cmd_init()` 保持非交互式：成功时只报告创建的配置文件，不读取或执行任何检查。`cli_hints.NEXT_STEPS` 移除 `("init",)` 的下一步命令映射，防止 CLI 输出被代理解释为需要立即执行的命令。

打包的 `/entrix` skill 在初始化或修复 `harness.yaml` 后必须暂停并询问用户：

```text
配置已生成。是否现在运行配置校验或本地检查？
```

只有用户明确回答肯定时，skill 才可按用户允许的范围运行 `entrix harness validate harness.yaml`、`entrix run --dry-run`、`entrix run --tier fast` 或完整 Harness。拒绝、未回答或仅要求初始化时，skill 必须结束于配置变更摘要，不能执行检查。

## 变更范围

修改：

- `entrix/harness/config.py`：解析和保存 producer 并发上限。
- `entrix/harness/engine.py`：默认串行，并按有效上限执行 producer。
- `entrix/cli.py`：增加 Harness/Fitness 的显式 worker 参数。
- `entrix/governance.py`、`entrix/engine.py`、`entrix/runners/shell.py`：传递 Fitness worker 上限。
- `entrix/harness/template.py`：默认模板声明 `max_parallel_producers: 1`。
- `entrix/cli_hints.py`：移除初始化后的自动下一步检查提示。
- `skills/entrix/SKILL.md`：要求初始化后先获得用户对检查的明确确认。
- `README.md`、`docs/stop-gate-usage.md`：记录两层并发模型与 Java 示例。

新增或修改测试：

- `tests/harness/test_config.py`
- `tests/harness/test_engine.py`
- `tests/test_cli.py`
- `tests/test_engine.py`
- `tests/test_shell_runner.py`
- `tests/test_cli_hints.py`

## 非目标

- 不创建 Java 专用 parser、producer 或项目自动识别。
- 不注入或覆盖 `MAVEN_OPTS`、Surefire `argLine`、`forkCount` 或 Gradle 配置。
- 不实现 cgroup、Windows Job Object 或跨平台内存配额。
- 不改变 Gate DSL、Evidence 格式或 Stop Hook 的 fail-closed 语义。

## 验收标准

1. 缺少 `max_parallel_producers` 的有效 Harness 默认串行。
2. `max_parallel_producers` 拒绝 0、负数、布尔值与非整数。
3. 手工 `entrix harness run` 未带 `--parallel` 时不会同时运行多个 producer。
4. 手工并发时，实际并发数不超过配置上限和 CLI 请求值中较小者。
5. Stop Hook 保持串行 producer 收集。
6. `entrix run --parallel --max-workers N` 将 N 传入 ShellRunner；未启用 `--parallel` 时保持串行。
7. 默认模板和文档明确 Java 内外两层并发限制。
8. `entrix init` 不输出自动执行检查的下一步命令；打包 skill 在初始化后必须等待用户确认。
