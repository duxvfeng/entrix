# GitHub Actions 自动构建说明

## 🚀 自动构建流程

当你在 GitHub 上创建 Release 时，GitHub Actions 会自动：

1. **构建跨平台可执行文件**
   - Windows (entrix.exe)
   - Linux (entrix)
   - macOS (entrix)

2. **构建 Python 包**
   - Wheel (.whl)
   - 源码包 (.tar.gz)

3. **自动发布到 Release**
   - 所有平台的可执行文件
   - Python 包
   - 可选择发布到 PyPI

## 📋 使用步骤

### 1. 推送代码到 GitHub

```bash
git remote add github https://github.com/phodal/entrix.git
git push github main
```

### 2. 创建 Release

在 GitHub 上：
1. 进入 "Releases" 页面
2. 点击 "Draft a new release"
3. 选择标签（如 `v0.1.22`）
4. 标题填写版本号
5. 发布

### 3. 自动构建

GitHub Actions 会自动：
- ✅ 构建 Windows 可执行文件
- ✅ 构建 Linux 可执行文件
- ✅ 构建 macOS 可执行文件
- ✅ 构建 Python 包
- ✅ 上传到 Release 页面

### 4. 下载可执行文件

用户可以直接从 Release 页面下载对应平台的可执行文件。

## 📦 Release 产物

每个版本会包含：

```
Release v0.1.22/
├── entrix-windows-amd64.zip       # Windows 可执行文件
├── entrix-linux-amd64.tar.gz      # Linux 可执行文件
├── entrix-macos-amd64.tar.gz      # macOS 可执行文件
├── entrix-0.1.22-py3-none-any.whl  # Python Wheel
└── entrix-0.1.22.tar.gz            # 源码包
```

## 🎯 手动触发构建

也可以手动触发构建（不创建 Release）：

```bash
# 使用 GitHub CLI
gh workflow run build.yml

# 或在 GitHub Actions 页面点击 "Run workflow"
```

## ⚙️ 配置 PyPI 发布（可选）

如果要自动发布到 PyPI：

1. 在 GitHub 仓库设置中添加 Secret：
   - Name: `PYPI_API_TOKEN`
   - Value: 你的 PyPI API token

2. 创建 Release 时会自动发布到 PyPI

## 🔧 本地测试构建

在推送前，可以先在本地测试：

```bash
# 安装 PyInstaller
pip install pyinstaller

# 构建可执行文件
pyinstaller --onefile --name entrix entrix/cli.py

# 测试
./dist/entrix --version
```

## 📝 版本号规范

使用语义化版本号（Semantic Versioning）：

- `v0.1.22` - 补丁版本（bug 修复）
- `v0.2.0` - 次版本（新功能）
- `v1.0.0` - 主版本（重大变更）

## 🎉 自动构建的好处

1. **无需手动编译** - GitHub Actions 自动构建
2. **跨平台支持** - 一次配置，三个平台
3. **自动发布** - Release 时自动上传
4. **可追溯** - 每个构建都有日志记录
5. **CI/CD 集成** - 与测试、发布流程集成

## 📚 相关文档

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [PyInstaller 文档](https://pyinstaller.org/)
- [Semantic Versioning](https://semver.org/)
