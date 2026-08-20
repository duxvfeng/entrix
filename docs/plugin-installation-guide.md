# Entrix 插件安装指南

## 🚀 快速安装

### 方法一：从本地路径安装（推荐用于开发）

1. **在 Claude Code 设置中添加本地插件路径：**

   ```json
   {
     "plugins": {
       "entrix": {
         "path": "D:\\python-project\\entrix"
       }
     }
   }
   ```

2. **或者使用 MCP 配置文件：**

   创建 `.mcp.json`：
   ```json
   {
     "mcpServers": {
       "entrix": {
         "command": "python",
         "args": ["-m", "entrix.cli", "serve"]
       }
     }
   }
   ```

### 方法二：从发布版本安装

1. **下载最新版本**
   ```bash
   git clone https://gitee.com/duxvfeng/entrix.git
   cd entrix
   ```

2. **安装依赖**
   ```bash
   pip install -e .
   ```

3. **在 Claude Code 中配置插件路径**

## 🔧 故障排除

### 问题：`bash: ./hooks/stop-gate.sh: No such file or directory`

**原因**：插件 Hook 路径配置不正确

**解决方案**：
1. 确保使用最新版本的 `.claude-plugin/plugin.json`
2. Hook 现在使用 `${CLAUDE_PLUGIN_ROOT}/bin/entrix stop-gate` 而不是直接调用脚本
3. 重新加载插件

### 问题：权限错误

**解决方案**：
```bash
# Windows
chmod +x bin/entrix
chmod +x hooks/stop-gate.sh

# 或者使用管理员权限运行 Claude Code
```

### 问题：Python 模块找不到

**解决方案**：
```bash
# 确保 entrix 已安装
pip install -e .

# 或者使用绝对路径
python -m entrix --version
```

## 🎯 验证安装

安装完成后，运行以下命令验证：

```bash
# 1. 检查版本
python -m entrix --version

# 2. 测试 stop-gate
python -m entrix stop-gate --help

# 3. 查看命令概览
python -m entrix

# 4. 运行快速检查
python -m entrix run --tier fast
```

## 📋 配置说明

### Stop Hook 配置

插件的 Stop Hook 现在使用：
```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "node",
            "args": ["${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs", "stop-gate"],
            "timeout": 295
          }
        ]
      }
    ]
  }
}
```

这个配置：
- ✅ 使用插件根目录的绝对路径
- ✅ 直接调用 entrix 命令而不是 shell 脚本
- ✅ 跨平台兼容（Windows/Linux/Mac）

### MCP Server 配置

```json
{
  "mcpServers": {
    "entrix": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/bin/entrix-bootstrap.mjs", "serve"],
      "env": {
        "ENTRIX_BINARY_VERSION": "0.1.24"
      }
    }
  }
}
```

## 🛠️ 开发模式设置

如果你正在开发 Entrix：

1. **设置环境变量**：
   ```bash
   export ENTRIX_DEV_MODE=1
   ```

2. **使用本地安装**：
   ```bash
   pip install -e .
   ```

3. **验证更改**：
   ```bash
   python -m entrix --version
   ```

## 📱 使用提示

安装成功后，在 Claude Code 中：

1. **初始化项目**：`/entrix init`
2. **查看命令**：`/entrix` （显示所有可用命令）
3. **运行检查**：`/entrix run --tier fast`
4. **阶段管理**：`/entrix phase planning`

## 🔗 相关文档

- [命令快速参考](command-reference.md)
- [可配置 Lint 系统](lint-config-guide.md)
- [项目主页](https://gitee.com/duxvfeng/entrix)

---

如果问题仍然存在，请查看：
1. Claude Code 的错误日志
2. `.claude/` 目录下的配置文件
3. 确保 Python 环境正确配置
