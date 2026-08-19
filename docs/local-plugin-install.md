# Entrix Claude 插件本地安装教程

> 本文介绍如何在本地安装 Entrix Claude Code 插件（开发调试或离线使用），而不是从官方 marketplace 安装。

## 前置条件

- Python 3.10+
- Claude Code 客户端
- 当前仓库已创建 `.venv` 并安装依赖（见项目 README）

> GitHub marketplace 的正式插件不需要以上 Python 前置条件。安装后首次调用会下载对应平台
> 的 Entrix 二进制，完成 SHA-256 校验并缓存到用户目录；本节的 Python 环境仅用于源码调试、
> 离线开发和手动 fallback。

```bash
cd /Users/apple/entrix
source .venv/bin/activate
entrix --help
```

---

## 方式一：官方 marketplace 安装（非本地，但最稳定）

```text
/plugin marketplace add https://gitee.com/duxvfeng/entrix.git
/plugin install entrix@entrix
```

安装后重启 Claude Code。MCP + Stop Gate 同时生效。

正式插件支持 Windows x64、Linux x64、Linux arm64、macOS x64 和 macOS arm64。启动器固定使用
插件版本对应的 `entrix-<version>-<target>` Release 资产，不会自动切换到 PyPI 上的 `latest`。
缓存命中后不需要网络；缓存目录为 Unix 的 `~/.cache/entrix/bin/` 或 Windows 的
`%LOCALAPPDATA%\entrix\bin\`。开发时可以设置 `ENTRIX_BINARY_PATH` 指定本地二进制，设置
`ENTRIX_RELEASE_REPOSITORY` / `ENTRIX_RELEASE_BASE_URL` 指向测试 Release；只有明确设置
`ENTRIX_STOP_GATE_DISABLED=1` 才会绕过 Stop Gate。

---

## 方式二：本地源码作为插件安装（推荐用于开发调试）

### 1. 确认本地包可运行

```bash
cd /Users/apple/entrix
source .venv/bin/activate
python -m build --wheel
entrix serve
# 按 Ctrl+C 退出
```

### 2. 安装到 Claude Code 的本地插件目录

Claude Code 插件通常安装在以下位置：

```bash
# macOS
$HOME/.claude/plugins

# 或 Claude Code 指定的插件目录
```

将当前仓库作为插件源安装：

```bash
PLUGIN_DIR="$HOME/.claude/plugins/entrix-dev"
rm -rf "$PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"

# 复制插件所需文件
cp -R .claude-plugin "$PLUGIN_DIR/"
cp -R hooks "$PLUGIN_DIR/"
cp -R entrix "$PLUGIN_DIR/"
cp -R pyproject.toml "$PLUGIN_DIR/"
cp -R README.md "$PLUGIN_DIR/"
```

### 3. 修改本地 plugin.json 指向本地入口

编辑 `$HOME/.claude/plugins/entrix-dev/.claude-plugin/plugin.json`：

```json
{
  "name": "entrix-dev",
  "version": "0.1.21",
  "mcpServers": {
    "entrix-dev": {
      "command": "/Users/apple/entrix/.venv/bin/python",
      "args": ["-m", "entrix", "serve"]
    }
  }
}
```

### 4. 修改 hooks/stop-gate.sh 指向本地 entrix

编辑 `$HOME/.claude/plugins/entrix-dev/hooks/stop-gate.sh`，将第一行调用改为本地 venv：

```bash
exec /Users/apple/entrix/.venv/bin/python -m entrix stop-gate "$@"
```

### 5. 在 Claude Code 中加载本地插件

```text
/plugin install /Users/apple/entrix
```

或：

```text
/plugin marketplace add /Users/apple/entrix
/plugin install entrix-dev@entrix-dev
```

> 注意：Claude Code 插件 CLI 的具体语法可能因版本不同而变化，以上命令基于常见的本地插件安装模式。如不支持，请使用方式三的手动配置。

---

## 方式三：手动配置 MCP + Stop Gate（最可靠，不依赖插件市场）

如果你只需要在当前项目里使用本地 Entrix，推荐这种方式。

### 1. 在当前项目生成 `.mcp.json`

```bash
# 进入你要使用 Entrix 的目标项目，不是 entrix 源码目录
cd /path/to/your-project

# 使用本地 venv 的 entrix serve
cat > .mcp.json << 'JSON'
{
  "mcpServers": {
    "entrix": {
      "command": "/Users/apple/entrix/.venv/bin/python",
      "args": ["-m", "entrix", "serve"]
    }
  }
}
JSON
```

Python 用户也可以选择 `pip install entrix[mcp]` 后使用 `entrix serve`；这只适用于 Python
开发路径，正式插件仍使用上面的版本化二进制启动器。

### 2. 配置 Claude Code Stop Gate Hook

编辑目标项目的 `.claude/settings.json`，添加 Stop hook：

```json
{
  "permissions": {
    "allow": [
      "Bash(/Users/apple/entrix/.venv/bin/python -m entrix stop-gate)"
    ]
  },
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash /Users/apple/entrix/hooks/stop-gate.sh",
            "timeout": 295
          }
        ]
      }
    ]
  }
}
```

> 如果 Claude Code 的 `settings.json` 不支持 `hooks` 字段，说明你需要通过完整插件安装（方式一或二）来启用 Stop Gate。

### 3. 在目标项目创建护栏配置

```bash
cd /path/to/your-project
entrix init --repo .
```

随后在根目录的 `harness.yaml` 中按项目的真实命令调整指标：

```yaml
fitness:
  dimensions:
    - dimension: code_quality
      weight: 100
      threshold: {pass: 90, warn: 80}
      metrics:
        - name: ruff_pass
          command: ruff check . 2>&1
          hard_gate: true
          tier: fast
          description: Ruff must pass.
```

### 4. 重启 Claude Code

```text
# 在 Claude Code 中执行
/reload
```

或完全退出重启。

---

## 验证是否安装成功

### 验证 MCP 工具

在 Claude Code 中询问：

```text
请使用 entrix 工具运行一次 fast tier 的 fitness check。
```

如果 Claude 调用了 `run_fitness`，说明 MCP 配置成功。

### 验证 Stop Gate

在 Claude Code 中让 Agent 完成一个小任务后尝试结束，观察是否有 Stop Gate 输出：

```text
任务完成了，请结束当前会话。
```

如果终端出现 `entrix stop-gate` 相关输出或 Claude 继续修复问题，说明 Stop Gate 生效。

### 手动测试 Stop Gate

```bash
cd /path/to/your-project
echo '{"session_id": "test", "cwd": "'"$PWD"'"}' | /Users/apple/entrix/.venv/bin/python -m entrix stop-gate
```

- 输出为空 → 放行
- 输出 `{"decision": "block", ...}` → 阻断

---

## 常见问题

### Q1: Claude Code 说找不到 /plugin install 本地路径的命令？

Claude Code 的插件 CLI 可能不支持本地路径。请使用方式三的手动配置。

### Q2: Stop Gate 没有触发？

检查以下几点：

1. 目标项目是否有可校验的 `harness.yaml` 配置
2. 是否设置了 `ENTRIX_STOP_GATE_DISABLED=1`
3. Claude Code 是否完整重启
4. 插件是否完整安装（不只是 MCP 配置）

### Q3: 如何禁用 Stop Gate？

```bash
export ENTRIX_STOP_GATE_DISABLED=1
```

或在 `.claude/settings.json` 中移除 Stop hook。

### Q4: 我想在多个项目使用本地 Entrix？

为每个目标项目复制方式三中的 `.mcp.json` 和 `.claude/settings.json` 配置即可。MCP Server 共用同一个本地 `entrix` 源码/venv。

---

## 快速检查清单

```bash
# 1. 本地 entrix 可运行
/Users/apple/entrix/.venv/bin/python -m entrix --help

# 2. MCP server 可启动
/Users/apple/entrix/.venv/bin/python -m entrix serve

# 3. Stop Gate 可运行
/Users/apple/entrix/.venv/bin/python -m entrix stop-gate --help

# 4. 目标项目有 Harness 配置
ls /path/to/your-project/harness.yaml
```
