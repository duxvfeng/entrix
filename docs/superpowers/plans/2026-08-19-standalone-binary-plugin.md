# Entrix 免 Python 二进制插件实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 Claude 插件提供包含 MCP 和 Stop Gate 的跨平台单文件 Entrix 二进制，插件首次调用时自动下载并缓存，用户无需安装 Python。

**架构：** GitHub Actions 使用 PyInstaller 为五个平台构建并发布原始可执行文件、压缩包和 SHA-256 校验文件。插件携带不依赖 Python 的 Unix/Windows 启动器，按插件版本和当前平台下载经校验的 Release 资产到用户缓存，再转发 `serve`、`stop-gate` 和其他 CLI 参数；开发环境仍保留 PATH、uvx 和源码 Python fallback。

**技术栈：** PyInstaller、GitHub Actions、POSIX shell、PowerShell、SHA-256、Claude Code plugin.json/marketplace.json、pytest。

---

## 文件清单

创建：

- `bin/entrix-bootstrap.sh`：Unix 平台下载、校验、缓存和执行逻辑。
- `bin/entrix-bootstrap.ps1`：Windows 平台下载、校验、缓存和执行逻辑。
- `scripts/build_release_assets.py`：从构建目录生成带版本和平台信息的资产清单及 SHA-256 文件。
- `tests/test_release_assets.py`：资产命名、目标映射和清单生成测试。
- `tests/test_plugin_binary_contract.py`：插件元数据、启动器入口和无 Python fallback 合约测试。

修改：

- `.github/workflows/build.yml`：增加五平台矩阵、MCP 资源收集、原始二进制和 checksum Release 资产。
- `.claude-plugin/plugin.json`：MCP server 改为插件启动器，版本与 Release 版本保持一致。
- `.claude-plugin/marketplace.json`：平台二进制映射指向真实启动器/资产，版本同步。
- `bin/entrix`：从 Python wrapper 改为 Unix 启动器入口。
- `bin/entrix.bat`：从 Python wrapper 改为 Windows PowerShell 启动器入口。
- `hooks/stop-gate.sh`：优先使用插件二进制入口，保留开发 fallback，并在二进制不可用时输出 block JSON。
- `entrix/cli.py`：`entrix install/init` 生成 `command: entrix`、`args: [serve]`，不再固定 Python 解释器路径。
- `tests/test_cli.py`：锁定生成的 MCP 配置使用二进制命令。
- `README.md`、`docs/local-plugin-install.md`、`.github/workflows/README.md`：记录无 Python 安装、缓存目录、平台资产和开发 fallback。

## 任务 1：锁定 Release 资产协议

**文件：**

- 创建：`scripts/build_release_assets.py`
- 测试：`tests/test_release_assets.py`

- [ ] **步骤 1：编写失败测试，定义目标和资产名**

测试必须覆盖：

```python
def test_release_target_names() -> None:
    assert target_name("Windows", "AMD64") == "windows-amd64"
    assert target_name("Linux", "x86_64") == "linux-amd64"
    assert target_name("Linux", "aarch64") == "linux-arm64"
    assert target_name("Darwin", "x86_64") == "macos-amd64"
    assert target_name("Darwin", "arm64") == "macos-arm64"


def test_asset_name_includes_version_and_windows_extension() -> None:
    assert asset_name("0.1.22", "windows-amd64") == "entrix-0.1.22-windows-amd64.exe"
    assert asset_name("0.1.22", "linux-amd64") == "entrix-0.1.22-linux-amd64"


def test_manifest_contains_sha256_and_download_url(tmp_path: Path) -> None:
    binary = tmp_path / "entrix-0.1.22-linux-amd64"
    binary.write_bytes(b"binary")
    manifest = build_manifest("0.1.22", "https://github.com/duxvfeng/entrix", [binary])
    assert manifest["version"] == "0.1.22"
    assert manifest["assets"][0]["sha256"] == hashlib.sha256(b"binary").hexdigest()
    assert manifest["assets"][0]["url"].endswith("/v0.1.22/" + binary.name)
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_release_assets.py -q
```

预期：FAIL，报告 `target_name`、`asset_name` 或 `build_manifest` 尚未定义。

- [ ] **步骤 3：实现最小资产协议模块**

实现以下纯函数，避免依赖 CI 环境：

```python
TARGETS = {
    ("Windows", "AMD64"): "windows-amd64",
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-arm64",
    ("Darwin", "x86_64"): "macos-amd64",
    ("Darwin", "arm64"): "macos-arm64",
}


def target_name(system: str, machine: str) -> str:
    try:
        return TARGETS[(system, machine)]
    except KeyError as error:
        raise ValueError(f"unsupported release target: {system}/{machine}") from error


def asset_name(version: str, target: str) -> str:
    suffix = ".exe" if target == "windows-amd64" else ""
    return f"entrix-{version}-{target}{suffix}"
```

`build_manifest()` 必须写入版本、目标、文件名、Release URL 和 SHA-256；脚本入口接收 `--version`、`--repository`、`--input-dir` 和 `--output`，同时生成每个资产旁边的 `<asset>.sha256` 文件。

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
python -m pytest tests/test_release_assets.py -q
```

预期：全部资产协议测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add scripts/build_release_assets.py tests/test_release_assets.py
git commit -m "feat(release): define standalone binary asset contract"
```

## 任务 2：实现 Unix 启动器

**文件：**

- 创建：`bin/entrix-bootstrap.sh`
- 修改：`bin/entrix`
- 测试：`tests/test_plugin_binary_contract.py`、Linux shell smoke test

- [ ] **步骤 1：编写启动器合约测试**

测试临时目录中的 fake downloader 和 fake binary，验证启动器：

- 将 `uname -s`/`uname -m` 映射到 `linux-amd64`、`linux-arm64`、`macos-amd64`、`macos-arm64`；
- 使用 `ENTRIX_BINARY_VERSION` 固定版本，默认读取插件版本文件；
- 使用 `XDG_CACHE_HOME` 覆盖缓存目录；
- 下载 `<asset>` 和 `<asset>.sha256`；
- 校验通过后执行二进制并传递所有参数；
- 已有有效缓存时不再次下载；
- SHA-256 不匹配时返回非零且不执行文件。

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
bash -n bin/entrix-bootstrap.sh
python -m pytest tests/test_plugin_binary_contract.py -q
```

预期：脚本缺失或合约测试失败。

- [ ] **步骤 3：实现下载和缓存**

`bin/entrix-bootstrap.sh` 必须：

1. 读取 `ENTRIX_RELEASE_REPOSITORY`、`ENTRIX_RELEASE_BASE_URL`、`ENTRIX_BINARY_VERSION`；
2. 将 `uname` 结果归一化为 Release target；
3. 优先使用 `curl -fsSL`，没有 curl 时使用 `wget -q`；
4. 将下载写入缓存目录的临时文件；
5. 用 `sha256sum` 或 `shasum -a 256` 计算摘要；
6. 摘要匹配后使用 `mv` 原子替换目标文件，并 `chmod 755`；
7. 所有诊断写 stderr，最后使用 `exec "$cached_binary" "$@"` 保留退出码；
8. 任何下载、校验、权限或目标平台错误返回非零。

`bin/entrix` 只负责定位同目录的 bootstrap 脚本并转发参数，不能再调用 `python3`。

- [ ] **步骤 4：运行测试确认通过**

运行：

```bash
bash -n bin/entrix bin/entrix-bootstrap.sh
python -m pytest tests/test_plugin_binary_contract.py -q
```

预期：脚本语法和 Unix 启动器测试全部 PASS。

- [ ] **步骤 5：Commit**

```bash
git add bin/entrix bin/entrix-bootstrap.sh tests/test_plugin_binary_contract.py
git commit -m "feat(plugin): add python-free Unix binary launcher"
```

## 任务 3：实现 Windows 启动器

**文件：**

- 创建：`bin/entrix-bootstrap.ps1`
- 修改：`bin/entrix.bat`
- 测试：`tests/test_plugin_binary_contract.py`、PowerShell smoke test

- [ ] **步骤 1：编写 Windows 合约测试**

测试必须验证 PowerShell 源码包含：

- `RuntimeInformation.ProcessArchitecture` 的 AMD64 判断；
- `%LOCALAPPDATA%\\entrix\\bin\\<version>\\windows-amd64\\` 缓存路径；
- `Invoke-WebRequest` 下载；
- `Get-FileHash -Algorithm SHA256` 校验；
- `ValueFromRemainingArguments` 参数转发；
- 非零错误退出。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
python -m pytest tests/test_plugin_binary_contract.py -q
```

预期：Windows 启动器文件或关键协议尚不存在。

- [ ] **步骤 3：实现 PowerShell 启动器**

`bin/entrix-bootstrap.ps1` 使用以下接口：

```powershell
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $EntrixArgs
)
```

它读取版本和 Release URL，下载 `.exe` 与 `.sha256` 到临时文件，使用 `Get-FileHash` 比较大小写不敏感的 64 位十六进制摘要，校验成功后移动到 `%LOCALAPPDATA%` 缓存并执行：

```powershell
& $cachedBinary @EntrixArgs
exit $LASTEXITCODE
```

`bin/entrix.bat` 只调用：

```bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0entrix-bootstrap.ps1" %*
exit /b %ERRORLEVEL%
```

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
.\bin\entrix.bat --help
python -m pytest tests/test_plugin_binary_contract.py -q
```

预期：Windows 本地或 CI 上能执行 `--help`，合约测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add bin/entrix.bat bin/entrix-bootstrap.ps1 tests/test_plugin_binary_contract.py
git commit -m "feat(plugin): add python-free Windows binary launcher"
```

## 任务 4：接入 MCP、Stop Hook 和 CLI 生成配置

**文件：**

- 修改：`.claude-plugin/plugin.json`
- 修改：`.claude-plugin/marketplace.json`
- 修改：`hooks/stop-gate.sh`
- 修改：`entrix/cli.py`
- 修改：`tests/test_cli.py`
- 修改：`tests/test_plugin_binary_contract.py`

- [ ] **步骤 1：编写入口回归测试**

加入以下断言：

```python
def test_default_mcp_config_uses_binary_command() -> None:
    config = _default_mcp_config()
    assert config["mcpServers"]["entrix"] == {
        "command": "entrix",
        "args": ["serve"],
    }


def test_plugin_manifest_does_not_use_uvx_or_python() -> None:
    manifest = json.loads(Path(".claude-plugin/plugin.json").read_text())
    server = manifest["mcpServers"]["entrix"]
    assert "uvx" not in server["command"]
    assert "python" not in server["command"]
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_cli.py tests/test_plugin_binary_contract.py -q
```

预期：当前默认配置仍为 `python -m entrix.cli serve`，plugin manifest 仍为 `uvx`。

- [ ] **步骤 3：修改 MCP 和 Stop Hook 入口**

`.claude-plugin/plugin.json` 的 server 改为插件根目录下的启动器并传入 `serve`；`marketplace.json` 的五个平台映射使用同一版本的启动器/资产，不保留虚假的 arm64 路径。

`hooks/stop-gate.sh` 的顺序改为：

1. `CLAUDE_PLUGIN_ROOT/bin/entrix` 或平台对应的 `entrix.bat`；
2. PATH 上的 `entrix`；
3. `uvx` 和源码 Python，仅供开发 fallback；
4. 输出固定的 `{"decision":"block",...}`。

插件入口调用时设置 `ENTRIX_BINARY_VERSION` 为 plugin manifest 版本，避免下载未固定版本。

`entrix/cli.py` 的 `_default_mcp_config()` 返回 `command: entrix` 和 `args: [serve]`，使二进制安装和项目级 `.mcp.json` 保持一致。

- [ ] **步骤 4：运行入口测试确认通过**

运行：

```bash
python -m pytest tests/test_cli.py tests/test_plugin_binary_contract.py tests/stop_gate/test_hook_cli.py -q
```

预期：所有 MCP 配置、manifest 和 Stop Hook 回归测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/stop-gate.sh entrix/cli.py tests/test_cli.py tests/test_plugin_binary_contract.py
git commit -m "feat(plugin): route MCP and Stop Gate through binary launcher"
```

## 任务 5：改造 GitHub Release 构建矩阵

**文件：**

- 修改：`.github/workflows/build.yml`
- 修改：`scripts/build_release_assets.py`
- 测试：`tests/test_release_assets.py`、workflow YAML 解析测试

- [ ] **步骤 1：编写 workflow 合约测试**

测试必须读取 YAML 并确认：

- 包含 `windows-latest`、`ubuntu-latest`、`ubuntu-24.04-arm`、`macos-13`、`macos-14`；
- 安装命令包含 `pip install -e ".[mcp]"`；
- PyInstaller 命令包含 `--onefile`、`--collect-all fastmcp`、`--collect-all tree_sitter_language_pack`；
- Release 上传 `.sha256` 和原始二进制；
- Python wheel job 仍单独构建，不把 FastMCP 改成基础依赖。

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
python -m pytest tests/test_release_assets.py -q
```

预期：当前 workflow 没有 arm64 矩阵、资源收集和 checksum 合约。

- [ ] **步骤 3：实现五平台构建**

将 `build` job 改成每个矩阵目标构建原始文件：

```bash
pyinstaller --onefile --name "$BINARY_NAME" \
  --add-data "entrix${DATA_SEPARATOR}entrix" \
  --collect-all fastmcp \
  --collect-all tree_sitter_language_pack \
  --hidden-import yaml \
  entrix/cli.py
```

Windows 使用 `;` 作为 `--add-data` 分隔符，Unix 使用 `:`。构建后运行 `dist/<binary> --help`，生成带版本的原始二进制、zip/tar.gz 和 SHA-256 文件，上传到 GitHub Release。

使用 `scripts/build_release_assets.py` 生成 `release-manifest.json`，清单中每个资产必须包含 `version`、`target`、`filename`、`url` 和 `sha256`。

- [ ] **步骤 4：运行 workflow 静态验证**

运行：

```bash
python -c "import yaml; from pathlib import Path; yaml.safe_load(Path('.github/workflows/build.yml').read_text(encoding='utf-8')); print('build workflow YAML parsed')"
python -m pytest tests/test_release_assets.py -q
```

预期：workflow YAML 和资产构建合约测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add .github/workflows/build.yml scripts/build_release_assets.py tests/test_release_assets.py
git commit -m "feat(ci): build verified standalone binaries for five targets"
```

## 任务 6：更新文档和安装路径

**文件：**

- 修改：`README.md`
- 修改：`docs/local-plugin-install.md`
- 修改：`.github/workflows/README.md`
- 测试：`tests/test_plugin_binary_contract.py`

- [ ] **步骤 1：编写文档合约测试**

确认文档包含：

- `/plugin install` 后不需要 Python；
- 首次调用下载、SHA-256 校验和缓存行为；
- `pip install entrix[mcp]` 仍是 Python 用户的可选方式；
- Windows/Linux/macOS 五个平台资产名；
- `ENTRIX_BINARY_PATH` 和 `ENTRIX_STOP_GATE_DISABLED` 的开发/故障处理说明。

- [ ] **步骤 2：更新安装说明**

将插件安装流程改为：

```text
/plugin marketplace add https://gitee.com/duxvfeng/entrix.git
/plugin install entrix@entrix
```

说明插件首次使用时获取对应 Release 二进制；不要再把 `uvx entrix serve` 描述为生产插件的必要路径。

- [ ] **步骤 3：运行文档和静态检查**

运行：

```bash
python -m pytest tests/test_plugin_binary_contract.py -q
ruff check entrix tests
```

预期：文档合约和代码静态检查 PASS。

- [ ] **步骤 4：Commit**

```bash
git add README.md docs/local-plugin-install.md .github/workflows/README.md tests/test_plugin_binary_contract.py
git commit -m "docs(plugin): document python-free binary installation"
```

## 任务 7：完整验证和发布前检查

**文件：**

- 检查：所有实现任务涉及的文件
- 测试：完整 pytest、workflow 合约、shell/PowerShell smoke test、构建产物

- [ ] **步骤 1：运行完整 Python 回归**

```bash
python -m pytest -q --tb=short
```

预期：所有测试通过，允许既有明确 skip，不允许失败或 error。

- [ ] **步骤 2：运行静态和构建检查**

```bash
ruff check .
python -m build
python -c "import yaml; from pathlib import Path; [yaml.safe_load(Path(p).read_text(encoding='utf-8')) for p in Path('.github/workflows').glob('*.yml')]; print('all workflow YAML parsed')"
```

预期：lint、wheel/sdist 和所有 workflow YAML 均通过。

- [ ] **步骤 3：运行启动器 smoke test**

Linux/macOS：

```bash
bash -n bin/entrix bin/entrix-bootstrap.sh
ENTRIX_BINARY_PATH="$(pwd)/dist/entrix-linux-amd64" bin/entrix --help
```

Windows：

```powershell
.\bin\entrix.bat --help
```

预期：不需要 Python，二进制能输出 CLI help；无网络时有效缓存仍能执行。

- [ ] **步骤 4：核对发布清单**

逐项确认五个平台资产、checksum、manifest、plugin.json 版本和 Git tag 完全一致；缺少任意目标时停止发布。

- [ ] **步骤 5：Commit**

```bash
git status --short
git diff --check
git commit -m "release: verify python-free plugin distribution"
```

