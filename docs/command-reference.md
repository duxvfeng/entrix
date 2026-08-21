# Entrix 命令快速参考

## 🚀 常用命令

### 初始化与配置
```bash
/entrix init                                  # 自动检测语言并初始化
/entrix init --profile python                 # 指定语言配置
/entrix harness validate                       # 验证配置文件
```

### 质量检查
```bash
/entrix run                                   # 运行快速检查
/entrix run --tier normal                     # 运行完整检查
/entrix harness run                           # 执行完整 Harness
```

### 阶段管理
```bash
/entrix phase planning                        # 开始规划阶段
/entrix phase implementation                   # 开始实现阶段
```

### 分析与调试
```bash
/entrix review-trigger                        # 检查需要审查的文件
/entrix graph build                           # 构建代码图
```

## 🎯 按使用场景

### 首次使用
```bash
/entrix init --repo . --profile auto
/entrix harness validate
/entrix run --tier fast
```

### 日常开发
```bash
/entrix run --tier fast                      # 快速检查
/entrix phase planning                       # 开始新功能规划
```

### 提交前检查
```bash
/entrix run                                  # 完整检查
/entrix review-trigger                       # 需要审查吗？
```

## 🔧 可配置 Lint 工具

### 自定义配置
```bash
# 编辑配置文件
vim harness.yaml

# 验证配置
/entrix harness validate
```

### 支持的语言
- **Python**: ruff, mypy, black, flake8, pylint
- **Node/TypeScript**: eslint, typescript, vue, prettier
- **Java Maven**: spotbugs, checkstyle, pmd
- **Java Gradle**: spotbugs, checkstyle, detekt
- **Go**: gofmt, go vet, golangci-lint, staticcheck
- **Rust**: cargo fmt, cargo clippy

## 📝 选项说明

| 选项 | 说明 | 示例 |
|------|------|------|
| `--repo <path>` | 指定仓库路径 | `--repo ./my-project` |
| `--profile <name>` | 语言配置 | `--profile python` |
| `--tier <level>` | 执行层级 | `--tier fast` |
| `--json` | JSON 输出 | 用于脚本解析 |

## 💡 提示

1. **首次使用**: 先运行 `/entrix init` 初始化配置
2. **日常开发**: 使用 `/entrix run --tier fast` 快速检查
3. **提交代码**: 运行 `/entrix run` 完整检查
4. **自定义工具**: 编辑 `.claude/lint-config.yaml` 文件
