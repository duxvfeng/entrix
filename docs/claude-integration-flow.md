# Entrix × Claude 集成全景流程图

> 本图重点展示 Entrix 在 Claude Code / Claude Desktop 环境下的完整调用链路与数据回流路径。

## 全景总览

```mermaid
flowchart TB
    subgraph Claude["Claude 侧"]
        C1[Claude Code 编辑器/终端]
        C2[Claude Desktop / MCP Client]
        C3[.mcp.json 配置]
        C4[Claude Code Stop Hook]
    end

    subgraph Entrix["Entrix 进程"]
        E1[entrix CLI<br/>entrix/cli.py]
        E2[entrix serve<br/>entrix/server.py]
        E3[entrix stop-gate<br/>entrix/stop_gate/]
        E4[entrix run<br/>fitness guardrail]
        E5[entrix graph<br/>代码图分析]
    end

    subgraph Runtime["运行时产物 /tmp/harness-monitor/runtime/<hash>"]
        R1[events.jsonl]
        R2[artifacts/fitness/*.json]
        R3[mailbox/fitness/new/*.json]
    end

    subgraph Project["项目目录"]
        P1[fitness/*.md 配置]
        P2[.claude/settings.json]
        P3[.claude/stop-gate/ 状态]
        P4[target/coverage/ 可选]
    end

    C1 <-->|1. 安装配置| E1
    C1 -->|2a. 变更文件| C4
    C4 -->|2b. 调用 stop-gate| E3
    C2 <-->|3. MCP stdio| E2
    E2 -->|4. 调用工具| E4
    E2 -->|5. 调用工具| E5
    E1 -->|6. 直接命令| E4
    E1 -->|7. 直接命令| E5
    E4 -->|8. 写入| R1
    E4 -->|9. 写入| R2
    E5 -->|10. 写入| R2
    R1 -->|11. 消费| C1
    R2 -->|12. 消费| C1
    R3 -->|13. 邮箱待处理| C1
    P1 -->|14. 配置来源| E4
    P2 -->|15. 配置来源| C4
    P3 -->|16. 状态来源| E3
    P4 -->|17. 覆盖率输入| E4

    style C1 fill:#e1f5fe
    style C2 fill:#e1f5fe
    style E2 fill:#fff3e0
    style E3 fill:#ffebee
    style E4 fill:#e8f5e9
    style E5 fill:#e8f5e9
    style R1 fill:#f3e5f5
    style R2 fill:#f3e5f5
    style R3 fill:#f3e5f5
```

---

## 1. Claude Code Stop Gate 拦截流程

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户
    participant CC as Claude Code
    participant Hook as .claude/stop-gate<br/>hook 脚本
    participant SG as entrix stop-gate
    participant SE as StopGateEngine
    participant SM as StateManager
    participant Arb as Arbiter
    participant Col as Collector

    User->>CC: 请求修改/提交代码
    CC->>CC: 检查 .claude/settings.json<br/>pre_submit hook 配置
    alt hook 已启用
        CC->>Hook: 调用 pre_submit hook
        Hook->>SG: 执行 entrix stop-gate
        SG->>SE: 解析 stdin payload
        SE->>Col: 收集变更上下文
        Col->>CC: 读取 diff / 文件状态
        Col-->>SE: 返回变更数据
        SE->>SM: 读取/写入 stop-gate 状态
        SE->>Arb: 裁决是否放行
        Arb-->>SE: 裁决结果
        SE-->>SG: exit code + 消息
        SG-->>Hook: 返回结果
        Hook-->>CC: 返回结果
        alt 通过
            CC-->>User: 继续执行用户请求
        else 拦截
            CC-->>User: 显示拦截原因 + 建议
        end
    else hook 未启用
        CC-->>User: 直接执行
    end
```

---

## 2. MCP Server 工具调用流程

```mermaid
sequenceDiagram
    autonumber
    participant Claude as Claude Desktop / MCP Client
    participant MCP as entrix serve<br/>FastMCP Server
    participant Tool1 as tool: run_fitness
    participant Tool2 as tool: get_dimension_status
    participant Tool3 as tool: analyze_change_impact
    participant Engine as engine.run_fitness_report
    participant Graph as GraphRunner
    participant Report as FitnessReport

    Claude->>MCP: 启动 MCP stdio 连接
    MCP-->>Claude: 注册可用工具列表
    Claude->>MCP: 调用 run_fitness(tier=fast)
    MCP->>Tool1: 路由到工具函数
    Tool1->>Engine: 执行 fitness run
    Engine->>Report: 生成报告
    Engine-->>Tool1: 返回报告
    Tool1-->>MCP: report_to_dict
    MCP-->>Claude: JSON 结果

    Claude->>MCP: 调用 get_dimension_status("security")
    MCP->>Tool2: 路由
    Tool2->>Engine: 执行全量 run
    Engine-->>Tool2: 报告
    Tool2-->>MCP: 指定维度状态
    MCP-->>Claude: 维度详情

    Claude->>MCP: 调用 analyze_change_impact(files)
    MCP->>Tool3: 路由
    Tool3->>Graph: GraphRunner.probe_impact
    Graph-->>Tool3: 影响半径结果
    Tool3-->>MCP: JSON
    MCP-->>Claude: 影响分析
```

---

## 3. `entrix run` 在 Claude 上下文中的完整执行链

```mermaid
flowchart LR
    A[Claude 触发<br/>run / review / stop-gate] --> B{调用方式}
    B -->|直接 CLI| C1[entrix run]
    B -->|MCP 工具| C2[tool: run_fitness]
    B -->|Stop Gate| C3[entrix stop-gate]

    C1 --> D[engine.run_fitness_report]
    C2 --> D
    C3 --> D

    D --> E1[load_dimensions<br/>读取 fitness/ YAML]
    D --> E2[get_project_preset<br/>识别项目类型]
    D --> E3[collect_changed_files<br/>git diff 增量]

    E1 --> F[GovernancePolicy<br/>tier/scope/parallel/dry-run]
    E2 --> F
    E3 --> F

    F --> G[filter_dimensions<br/>过滤 metric]
    G --> H1[ShellRunner<br/>shell/test metric]
    G --> H2[SarifRunner<br/>sarif metric]
    G --> H3[GraphRunner<br/>probe metric]

    H1 --> I1[MetricResult
    pass/fail/unknown]
    H2 --> I1
    H3 --> I1

    I1 --> J[score_dimension
    score_report]
    J --> K[FitnessReport]

    K --> L1[Reporter 输出<br/>Terminal/Rich/Ascii]
    K --> L2[write_report_output<br/>JSON 文件]
    K --> L3[governance.enforce<br/>exit code]
    K --> L4[Runtime artifacts<br/>/tmp/harness-monitor/...]

    L4 --> M[Claude 读取<br/>events.jsonl + artifacts]
    L3 --> N{是否阻塞?}
    N -->|是| O[Claude 停止/提示]
    N -->|否| P[Claude 继续]

    style A fill:#e1f5fe
    style D fill:#fff3e0
    style K fill:#e8f5e9
    style L4 fill:#f3e5f5
    style O fill:#ffebee
    style P fill:#e8f5e9
```

---

## 4. Graph 代码图分析在 Claude 中的使用路径

```mermaid
flowchart TB
    subgraph Init["初始化"]
        I1[Claude 请求分析变更影响]
        I2[entrix graph build]
    end

    subgraph Build["构建代码图"]
        B1[BuiltinGraphAdapter]
        B2[tree-sitter 解析源码]
        B3[构建符号索引]
        B4[持久化缓存]
    end

    subgraph Query["查询分析"]
        Q1[impact 影响半径]
        Q2[test-radius 测试半径]
        Q3[test-mapping 测试映射]
        Q4[review-context 审查上下文]
        Q5[history 变更历史]
    end

    subgraph Output["输出给 Claude"]
        O1[JSON 报告]
        O2[文本摘要]
        O3[推荐审查文件列表]
    end

    I1 --> I2
    I2 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> Q1
    B4 --> Q2
    B4 --> Q3
    B4 --> Q4
    B4 --> Q5
    Q1 --> O1
    Q2 --> O1
    Q3 --> O2
    Q4 --> O3
    Q5 --> O2

    style I1 fill:#e1f5fe
    style B1 fill:#fff3e0
    style Q1 fill:#e8f5e9
    style O3 fill:#f3e5f5
```

---

## 5. 运行时事件与 Claude 反馈闭环

```mermaid
flowchart LR
    A[entrix run 结束] --> B{执行结果}
    B -->|通过| C1[status: passed]
    B -->|失败| C2[status: failed]
    B -->|跳过| C3[status: skipped]

    C1 --> D[_build_runtime_fitness_snapshot]
    C2 --> D
    C3 --> D

    D --> E1[snapshot JSON]
    E1 --> F1[_write_runtime_fitness_artifacts]
    E1 --> F2[_emit_runtime_fitness_event]

    F1 --> G1["/tmp/harness-monitor/runtime/<hash>/artifacts/fitness/<timestamp>.json"]
    F2 --> G2["/tmp/harness-monitor/runtime/<hash>/events.jsonl"]
    F2 --> G3["mailbox/fitness/new/<timestamp>.json"]

    G1 --> H[Claude 读取产物]
    G2 --> H
    G3 --> H
    H --> I[Claude 生成反馈/建议]
    I --> J[用户查看结果]

    style A fill:#fff3e0
    style D fill:#e8f5e9
    style G1 fill:#f3e5f5
    style G2 fill:#f3e5f5
    style G3 fill:#f3e5f5
    style H fill:#e1f5fe
```

---

## 6. 配置与数据流关系图

```mermaid
flowchart TB
    subgraph Config["配置层"]
        CFG1[fitness/*.md<br/>Dimension + Metric]
        CFG2[.claude/settings.json<br/>hook 配置]
        CFG3[pyproject.toml<br/>可选依赖/项目元数据]
        CFG4[review-triggers.yaml]
        CFG5[release-manifest.yaml]
    end

    subgraph Engine["Entrix 引擎"]
        ENG1[CLI / MCP 入口]
        ENG2[engine.run_fitness_report]
        ENG3[StopGateEngine]
        ENG4[GraphRunner]
        ENG5[Trigger 评估]
    end

    subgraph State["状态/产物"]
        ST1[.claude/stop-gate/]
        ST2[/tmp/harness-monitor/runtime/]
        ST3[stdout / JSON 报告]
    end

    subgraph Consumer["Claude 消费"]
        CON1[Claude Code 拦截提示]
        CON2[Claude 工具返回结果]
        CON3[Runtime 事件面板/日志]
    end

    CFG1 --> ENG2
    CFG2 --> ENG3
    CFG3 --> ENG1
    CFG4 --> ENG5
    CFG5 --> ENG5

    ENG1 --> ENG2
    ENG1 --> ENG3
    ENG1 --> ENG4
    ENG1 --> ENG5

    ENG2 --> ST2
    ENG2 --> ST3
    ENG3 --> ST1
    ENG3 --> ST3
    ENG4 --> ST2
    ENG5 --> ST3

    ST1 --> CON1
    ST3 --> CON2
    ST2 --> CON3

    style Config fill:#e1f5fe
    style Engine fill:#fff3e0
    style State fill:#f3e5f5
    style Consumer fill:#e8f5e9
```
