# Entrix 执行流程图

> 本文用 Mermaid 描述 `entrix` 从入口到各类子命令的完整执行路径。

## 1. 顶层入口与命令分发

```mermaid
flowchart TD
    A1[终端用户<br/>entrix &lt;command&gt;] --> B[entrix.cli:main]
    A2[python -m entrix] --> B
    A3[pyproject.toml entry point<br/>entrix=entrix.cli:main] --> B
    B --> C{解析命令}
    C -->|run| D[cmd_run]
    C -->|install / init| E[cmd_install<br/>生成 .mcp.json]
    C -->|serve| F[cmd_serve<br/>启动 MCP server]
    C -->|stop-gate| G[cmd_stop_gate<br/>Claude Code Stop Hook]
    C -->|validate| H[cmd_validate<br/>校验 dimension 权重]
    C -->|review-trigger| I[cmd_review_trigger]
    C -->|release-trigger| J[cmd_release_trigger]
    C -->|hook| K[hook 子命令<br/>file-length]
    C -->|analyze| L[analyze 子命令<br/>long-file]
    C -->|graph| M[graph 子命令<br/>build/stats/impact/...]
```

## 2. 核心 `entrix run` 流程

```mermaid
flowchart TD
    subgraph CLI["CLI 层 entrix/cli.py"]
        R1[cmd_run] --> R2[查找项目根目录<br/>_find_project_root]
        R2 --> R3[定位 fitness/ 配置目录<br/>_find_fitness_dir]
        R3 --> R4[选择项目预设<br/>get_project_preset]
        R4 --> R5[构建 GovernancePolicy<br/>tier/scope/parallel/dry-run/...]
        R5 --> R6[收集变更文件<br/>_collect_run_files]
        R6 --> R7[初始化 Reporter<br/>Terminal/Rich/Ascii]
    end

    subgraph Engine["引擎层 entrix/engine.py"]
        R7 --> E1[load_harness_config<br/>解析 Harness 配置]
        E1 --> E2[governance.filter_dimensions<br/>按 tier/scope/维度过滤]
        E2 --> E3{存在 changed_files?}
        E3 -->|是| E4[filter_dimensions_for_incremental<br/>只保留相关 metric]
        E3 -->|否| E5[全量 dimensions]
        E4 --> E6[实例化 Runner<br/>ShellRunner / SarifRunner / GraphRunner]
        E5 --> E6
        E6 --> E7[遍历每个 Dimension]
        E7 --> E8[_run_metric_batch]
        E8 --> E9[score_dimension<br/>按权重计算维度得分]
        E9 --> E10[score_report<br/>生成 FitnessReport]
    end

    subgraph Runners["执行器层 entrix/runners/"]
        E8 --> S1[ShellRunner<br/>执行 command/test 类型 metric]
        E8 --> S2[SarifRunner<br/>读取 .sarif 结果]
        E8 --> S3[GraphRunner<br/>执行 probe 类型 metric]
    end

    subgraph Output["输出与治理层"]
        E10 --> O1[Reporter 打印结果]
        E10 --> O2[write_report_output<br/>JSON/文件输出]
        E10 --> O3[governance.enforce<br/>计算 exit code]
        O3 --> O4{hard_gate_blocked?}
        O4 -->|是| O5[exit 1]
        O4 -->|否| O6{score_blocked?}
        O6 -->|是| O5
        O6 -->|否| O7[exit 0]
        O2 --> O8[_write_runtime_fitness_artifacts<br/>写入 /tmp/harness-monitor/runtime]
        O8 --> O9[_emit_runtime_fitness_event<br/>events.jsonl]
    end
```

## 3. Metric 执行细节

```mermaid
flowchart TD
    A[_run_metric_batch] --> B{evidence_type}
    B -->|COMMAND / TEST| C[ShellRunner.run_batch]
    B -->|PROBE| D[_run_probe_metric]
    B -->|SARIF| E[SarifRunner.run_batch]
    B -->|MANUAL_ATTESTATION| F[占位 UNKNOWN]

    C --> C1[并行或串行执行 shell]
    C --> C2[stream / capture 输出]
    C --> C3[匹配 pattern 判定 pass/fail]
    C1 --> C4[MetricResult]

    D --> D1{waiver 有效?}
    D1 -->|是| D2[WAIVED]
    D1 -->|否| D3{dry-run?}
    D3 -->|是| D4[DRY-RUN 占位]
    D3 -->|否| D5{probe 命令}
    D5 -->|graph:impact| E1[GraphRunner.probe_impact]
    D5 -->|graph:test-radius| E2[GraphRunner.probe_test_coverage]
    D5 -->|graph:test-mapping| E3[GraphRunner.probe_test_mapping]
    D5 -->|其他| E4[UNKNOWN 错误]

    E --> E5[读取命令指定 sarif 文件]<br/>E5 --> E6[汇总 violations] --> E7[MetricResult]
```

## 4. Graph 子系统

```mermaid
flowchart TD
    subgraph GraphCLI["graph 子命令"]
        G1[graph build] --> G2[GraphRunner.build_graph]
        G3[graph stats] --> G4[GraphRunner.stats]
        G5[graph impact] --> G6[GraphRunner.analyze_impact]
        G7[graph test-radius] --> G8[GraphRunner.analyze_test_radius]
        G9[graph test-mapping] --> G10[GraphRunner.analyze_test_mapping]
        G11[graph query] --> G12[GraphRunner.query]
        G13[graph history] --> G14[GraphRunner.analyze_history]
        G15[graph review-context] --> G16[GraphRunner.review_context]
    end

    subgraph Adapter["Graph 适配器"]
        G2 --> A1[BuiltinGraphAdapter<br/>entrix/structure/builtin.py]
        G4 --> A1
        G6 --> A1
        G8 --> A1
        G10 --> A1
        G12 --> A1
        G14 --> A1
        G16 --> A1
    end

    subgraph Cache["缓存与索引"]
        A1 --> C1[解析源码 tree-sitter]
        C1 --> C2[构建符号索引]
        C2 --> C3[持久化到 .claude/ 或 target/]
        C3 --> C4[查询 / 影响半径 / 测试映射]
    end
```

## 5. Trigger 与 Stop Gate 流程

```mermaid
flowchart TD
    subgraph Review["review-trigger"]
        R1[collect_changed_files] --> R2[collect_diff_stats]
        R2 --> R3[load_review_triggers]
        R3 --> R4[evaluate_review_triggers]
        R4 --> R5[输出需要人工 review 的文件/规则]
    end

    subgraph Release["release-trigger"]
        L1[load_release_manifest] --> L2[load_release_triggers]
        L2 --> L3[evaluate_release_triggers]
        L3 --> L4[输出 release 风险报告]
    end

    subgraph StopGate["stop-gate"]
        S1[Claude Code 调用<br/>stop-gate hook] --> S2[cmd_stop_gate]
        S2 --> S3[读取 stdin payload]
        S3 --> S4[StopGateEngine<br/>entrix/stop_gate/]
        S4 --> S5[Collector 收集上下文]
        S5 --> S6[Arbiter 裁决是否拦截]
        S6 --> S7{通过?}
        S7 -->|是| S8[exit 0]
        S7 -->|否| S9[exit 非0 + 拦截提示]
    end
```

## 6. MCP Server 集成

```mermaid
flowchart TD
    A[entrix serve] --> B[server.create_server]
    B --> C[FastMCP 实例]
    C --> D1[tool: run_fitness]
    C --> D2[tool: get_dimension_status]
    C --> D3[tool: analyze_change_impact]

    D1 --> E1[复用 engine.run_fitness_report]
    D2 --> E2[复用 engine.run_fitness_report]
    D3 --> E3[复用 GraphRunner.probe_impact]

    E1 --> F1[report_to_dict]
    E2 --> F2[report_to_dict]
    E3 --> F3[返回 JSON]
```

## 7. 数据与配置加载

```mermaid
flowchart TD
    A[fitness/ 目录] --> B[evidence_loader.py]
    B --> C[解析 frontmatter YAML]
    C --> D[构建 Dimension + Metric 对象]
    D --> E[model.py 领域模型]

    F[项目根目录] --> G[presets/base.py]
    G --> H[ProjectPreset]
    H --> I[fitness_dir / domains_from_files<br/>should_ignore_changed_file]

    J[pyproject.toml / .mcp.json] --> K[ GovernancePolicy ]
    K --> L[filter_dimensions / enforce]
```

## 8. 整体汇总图

```mermaid
flowchart LR
    subgraph Input["输入层"]
        I1[CLI 命令]
        I2[MCP 工具]
        I3[Stop Gate Hook]
        I4[配置文件 fitness/]
    end

    subgraph Core["核心引擎"]
        C1[CLI 解析]
        C2[Dimension/Metric 加载]
        C3[过滤与增量选择]
        C4[Runner 执行]
        C5[评分与报告]
    end

    subgraph Subsystem["子系统"]
        S1[Graph 分析]
        S2[Review/Release Trigger]
        S3[Stop Gate]
        S4[Runtime 事件/产物]
    end

    subgraph Output["输出层"]
        O1[终端/Reporter]
        O2[JSON 报告]
        O3[Runtime artifacts]
        O4[Exit Code]
    end

    I1 --> C1
    I2 --> C1
    I3 --> C1
    I4 --> C2
    C1 --> C2
    C2 --> C3
    C3 --> C4
    C4 --> C5
    C4 --> S1
    C1 --> S2
    C1 --> S3
    C5 --> S4
    C5 --> O1
    C5 --> O2
    S4 --> O3
    C5 --> O4
    S1 --> O2
    S2 --> O2
    S3 --> O4
```
