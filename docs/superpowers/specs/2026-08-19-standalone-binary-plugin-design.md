# Entrix 免 Python 二进制插件设计

## 状态

已选择方案：GitHub Release 发布平台二进制，Claude 插件通过无 Python 启动器按平台下载并缓存。

## 1. 背景与目标

当前插件的 MCP 配置使用 `uvx entrix serve`，Stop Hook 依赖 `entrix`、`uvx` 或 Python。这样会带来三个问题：

1. 用户必须安装 Python 或 uv；
2. `uvx` 可能下载到与当前插件配置不匹配的旧 PyPI 版本；
3. `.claude-plugin/marketplace.json` 中虽然声明了平台二进制映射，但 GitHub Actions 没有把构建产物接入插件运行入口。

本设计的目标是：

- 为 Windows x64、Linux x64、Linux arm64、macOS x64、macOS arm64 构建单文件 Entrix 可执行程序；
- 将 FastMCP、Tree-sitter 运行资源和 Entrix 代码打入可执行程序；
- 用户安装插件后，MCP 和 Stop Hook 均可在没有 Python 的环境中运行；
- 首次调用自动下载对应平台二进制，校验后缓存，后续离线运行；
- 版本、下载地址和校验值可追溯，不使用不固定的 `latest`；
- 二进制不可用、下载失败或校验失败时，Stop Gate 保持 fail-closed。

## 2. 非目标

- 不把五个平台的二进制直接提交到 Git 仓库；
- 不在运行时自动升级到最新版本；
- 不把 FastMCP 改成 Entrix 的基础依赖；
- 不在本次设计中重写 Python 业务逻辑为 Go、Rust 或其他语言；
- 不移除开发者使用 Python 源码运行 Entrix 的能力。

## 3. 架构

运行时数据流如下：

```text
Claude Plugin
    |
    +-- MCP stdio --> platform launcher -- download/verify/cache --> entrix binary serve
    |
    +-- Stop hook --> platform launcher -- download/verify/cache --> entrix binary stop-gate
```

### 3.1 二进制构建

`.github/workflows/build.yml` 使用 PyInstaller `--onefile` 构建五个目标：

| 目标 | GitHub runner | 产物 |
| --- | --- | --- |
| Windows x64 | `windows-latest` | `entrix-windows-amd64.exe` |
| Linux x64 | `ubuntu-latest` | `entrix-linux-amd64` |
| Linux arm64 | `ubuntu-24.04-arm` | `entrix-linux-arm64` |
| macOS x64 | `macos-13` | `entrix-macos-amd64` |
| macOS arm64 | `macos-14` | `entrix-macos-arm64` |

PyInstaller 构建必须：

- 安装 `entrix[mcp]`，而不是不受版本约束的裸 `fastmcp`；
- 使用 `--collect-all fastmcp`，收集 FastMCP 的动态模块和资源；
- 使用 `--collect-all tree_sitter_language_pack`，收集语言包的动态库和语法资源；
- 保留 YAML、Tree-sitter 和 FastMCP 的必要 hidden import；
- 构建后执行二进制 `--help` smoke test；
- 为每个发布资产生成 SHA-256 文件；
- 仅在 tag/release 版本发布，资产名必须包含版本、平台和架构。

Python wheel/sdist 仍然只发布 Entrix 源码和依赖元数据。它包含 `entrix/server.py`，但不内置 FastMCP；需要 MCP 的 Python 用户继续使用 `pip install entrix[mcp]`。

### 3.2 启动器

插件携带无 Python 依赖的启动器：

- Unix：`bin/entrix`，使用 POSIX shell；
- Windows：`bin/entrix.bat`，调用系统 PowerShell 完成下载、校验和执行；
- 启动器只向 stderr 输出下载进度和错误，stdout 保留给 MCP JSON-RPC 或 Stop Gate JSON；
- 启动器接收 `serve`、`stop-gate` 以及其他 Entrix CLI 参数并原样转发。

启动器使用插件版本作为二进制版本，不请求 `latest`。默认发布仓库为 `duxvfeng/entrix`，并允许 `ENTRIX_RELEASE_REPOSITORY` 和 `ENTRIX_RELEASE_BASE_URL` 覆盖，以支持 fork 和镜像。

### 3.3 下载、校验与缓存

启动器按当前系统选择目标名：

```text
windows + amd64  -> entrix-windows-amd64.exe
linux   + amd64  -> entrix-linux-amd64
linux   + arm64  -> entrix-linux-arm64
darwin  + amd64  -> entrix-macos-amd64
darwin  + arm64  -> entrix-macos-arm64
```

缓存目录：

- Unix：`${XDG_CACHE_HOME:-$HOME/.cache}/entrix/bin/<version>/<target>/`；
- Windows：`%LOCALAPPDATA%\\entrix\\bin\\<version>\\<target>\\`。

下载流程：

1. 检查目标版本的缓存二进制和校验文件；
2. 缓存完整且 SHA-256 匹配时直接执行；
3. 缓存不存在或校验失败时下载二进制和对应 `.sha256`；
4. 写入临时文件，完成校验后原子重命名；
5. 设置 Unix 可执行权限；
6. 执行缓存文件并返回其退出码。

下载使用超时、临时文件和进程级锁，避免多个 Claude 进程同时写入同一缓存。任何 URL、HTTP、文件权限或 SHA-256 错误都必须停止执行；Stop Hook 由上层输出阻断 JSON。

## 4. Claude 插件接入

`.claude-plugin/plugin.json` 的 MCP server 不再调用 `uvx`，改为调用插件启动器并传入 `serve`。Stop Hook 的 `hooks/stop-gate.sh` 优先调用插件启动器；源码 checkout、PATH 上的 Entrix 和 uvx 仅作为开发 fallback，不作为发布插件的必需依赖。

`marketplace.json` 的 `binaries` 映射改为真实的发布资产/启动器入口，版本与 `plugin.json`、Git tag 保持一致。插件安装后的 MCP 配置只引用插件根目录，不写入用户机器上的 Python 路径。

`entrix install` 在二进制模式下生成 `command: entrix`、`args: [serve]` 的项目配置；插件模式优先使用 plugin.json 中的 MCP 配置，避免项目配置固定到某台机器的绝对路径。

## 5. 失败与兼容策略

- MCP 启动器下载失败：只向 stderr 输出诊断，MCP 进程以非零状态退出；
- Stop Hook 下载失败、二进制启动失败或返回结构化错误：输出 `decision: block`；
- 缓存损坏：删除当前版本缓存后只允许重新下载，不执行未校验文件；
- 无网络但已有有效缓存：继续离线运行；
- `ENTRIX_BINARY_PATH` 存在时允许开发者指定本地二进制，仍执行可执行文件检查；
- `ENTRIX_STOP_GATE_DISABLED=1` 的现有显式绕过语义保持不变。

## 6. 验收标准

### 构建验收

- 五个目标均生成单文件可执行程序；
- 每个程序能够执行 `--help`；
- `serve` 能启动 FastMCP stdio 服务并完成最小握手；
- `stop-gate` 能读取测试 payload 并返回结构化结果；
- 构建日志和 SHA-256 文件上传到同一 GitHub Release；
- Python wheel 的 metadata 仍提供 `entrix[mcp]`，且默认安装不强制安装 FastMCP。

### 插件验收

- 在没有 `python`、`python3`、`uv`、`uvx` 的测试环境中安装插件；
- 首次 MCP 调用下载正确平台资产并通过 SHA-256 校验；
- 第二次调用命中缓存且不产生网络依赖；
- 五个平台均能执行 MCP 和 Stop Hook；
- 修改校验文件或二进制后，MCP 启动失败，Stop Hook 输出 block；
- 插件升级到新版本时使用新版本目录，不覆盖旧版本缓存；
- 开发 checkout 仍可通过 Python/uvx fallback 运行。

### 回归验收

- 现有 Harness、Stop Gate 和完整 pytest 测试保持通过；
- CI 的 Defense workflow 继续使用当前 checkout 的 `harness.yaml`；
- skill regression 不再引用 `docs/fitness`；
- 发布流程不再让生产插件依赖 PyPI 上可能滞后的 Entrix 版本。

## 7. 发布与回滚

发布顺序固定为：

1. 更新 `pyproject.toml`、`plugin.json` 和 release manifest 的同一版本；
2. GitHub Actions 构建五个平台资产和校验文件；
3. 在 Release 中上传并验证所有资产；
4. 发布插件版本；
5. 新插件版本首次调用时按版本下载资产。

如果某个平台资产构建失败，Release 不得标记为可安装。发现已发布资产错误时，保留旧版本目录和校验文件，回滚插件版本指向上一组完整资产。
