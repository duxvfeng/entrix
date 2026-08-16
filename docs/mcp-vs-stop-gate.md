# Entrix MCP vs Stop Gate 调用关系

> 说明 `entrix serve`（MCP）和 `entrix stop-gate`（Claude Code Hook）是两套不同的集成机制。

## 调用方式对比

```mermaid
flowchart TB
    subgraph Claude["Claude Code"]
        C1[用户对话进行中]
        C2[Agent 准备结束任务<br/>触发 Stop 生命周期]
    end

    subgraph MCP["MCP 通道"]
        M1[Claude 调用工具]
        M2[entrix serve<br/>stdio 长连接]
        M3[tool: run_fitness]
        M4[tool: get_dimension_status]
        M5[tool: analyze_change_impact]
    end

    subgraph Hook["Stop Gate Hook 通道"]
        H1[Claude Code 调用 Stop Hook]
        H2[hooks/stop-gate.sh]
        H3[entrix stop-gate]
        H4[读取 stdin payload]
        H5[StopGateEngine 裁决]
    end

    subgraph Result["结果"]
        R1[JSON 工具结果<br/>返回给对话上下文]
        R2[stdout block decision<br/>阻止/放行停止]
    end

    C1 -->|主动调用| M1
    M1 --> M2
    M2 --> M3
    M2 --> M4
    M2 --> M5
    M3 --> R1
    M4 --> R1
    M5 --> R1

    C2 -->|生命周期触发| H1
    H1 --> H2
    H2 --> H3
    H3 --> H4
    H4 --> H5
    H5 --> R2

    style M2 fill:#fff3e0
    style H3 fill:#ffebee
    style R1 fill:#e8f5e9
    style R2 fill:#f3e5f5
```

## Stop Gate Hook 执行细节

```mermaid
sequenceDiagram
    autonumber
    participant Claude as Claude Code
    participant Hook as hooks/stop-gate.sh
    participant CLI as entrix stop-gate
    participant Adapter as StopGateAdapter
    participant Engine as StopGateEngine
    participant Collector as EvidenceCollector
    participant Arbiter as GateArbiter

    Claude->>Hook: 触发 Stop 生命周期
    Hook->>CLI: 执行 entrix stop-gate
    CLI->>CLI: read_hook_payload(stdin)
    CLI->>Adapter: on_before_stop(context)
    Adapter->>Engine: process_stop_request(attempt)
    Engine->>Collector: collect_evidence(attempt)
    Collector-->>Engine: evidence_pack
    Engine->>Arbiter: arbitrate(evidence_pack)
    Arbiter-->>Engine: verdict
    Engine-->>Adapter: decision
    Adapter-->>CLI: decision
    alt 允许停止
        CLI-->>Hook: exit 0, 无 stdout
        Hook-->>Claude: 放行，任务结束
    else 阻止停止
        CLI-->>Hook: exit 0, stdout JSON
        Hook-->>Claude: {"decision": "block", "reason": "..."}
        Claude->>Claude: 继续修复问题
    end
```

## 关键区别

| 特性 | MCP Server (`entrix serve`) | Stop Gate Hook (`entrix stop-gate`) |
|------|---------------------------|-----------------------------------|
| 触发时机 | 对话中 Claude 主动调用 | Claude Code 准备停止任务时自动触发 |
| 调用入口 | `plugin.json` 中 `mcpServers` | `hooks/hooks.json` 中 `Stop` hook |
| 通信方式 | stdio JSON-RPC | stdin 输入 payload，stdout 输出决策 |
| 返回值 | 工具结果 JSON | 阻断时输出 `{"decision": "block"}` |
| 是否可见 | 用户可见工具调用 | 通常不展示，只决定是否放行 |
| 配置位置 | `.mcp.json` / `plugin.json` | `.claude/settings.json` + `hooks/hooks.json` |

## Stop Gate  payload 示例

Claude Code 通过 stdin 发送给 `entrix stop-gate` 的 JSON：

```json
{
  "session_id": "uuid",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/Users/apple/entrix",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "reason": "agent_completed"
}
```

## 手动测试 Stop Gate

```bash
# 1. 确保当前仓库有 docs/fitness/ 配置
ls docs/fitness/

# 2. 模拟 Claude Code 输入
echo '{"session_id": "test", "cwd": "'"$PWD"'"}' | entrix stop-gate

# 3. 输出为空 -> 放行
#    输出 {"decision": "block", "reason": "..."} -> 阻止
```

## 禁用 Stop Gate

```bash
export ENTRIX_STOP_GATE_DISABLED=1
```

## 本地开发时让 Stop Gate 使用当前源码

```bash
# 使用当前 venv 的 entrix
source .venv/bin/activate

# 手动调用 stop-gate 查看行为
echo '{"session_id": "test", "cwd": "'"$PWD"'"}' | entrix stop-gate
```
