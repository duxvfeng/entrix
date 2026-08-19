# 项目质量检查 - Lint 配置说明

## ✅ 已配置的 Lint 检查

项目在 `harness.yaml` 中已配置 **Ruff Lint 检查**：

```yaml
- name: ruff_pass
  command: ruff check . 2>&1
  hard_gate: true
  tier: fast
  description: Ruff must pass with no lint errors.
```

**关键信息**：
- ✅ **Hard Gate**（硬门禁）：失败会阻止合并
- ✅ **Fast Tier**（快速）：运行速度快
- ✅ **自动执行**：每次质量检查都会运行

## 📋 当前配置

### Ruff 规则选择

**之前（❌ 不完整）**:
```toml
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
```

**现在（✅ 完整）**:
```toml
[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "F",     # pyflakes
    "W",     # pycodestyle warnings
    "I",     # isort
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "F401",  # imported but unused (sometimes needed for exports)
]
```

### 规则说明

| 规则 | 说明 | 示例 |
|------|------|------|
| **E** | pycodestyle errors | 语法错误、缩进错误 |
| **F** | pyflakes | 未使用的变量、重复定义 |
| **W** | pycodestyle warnings | 风格警告 |
| **I** | isort | import 排序 |

### 忽略的规则

| 规则 | 原因 |
|------|------|
| E501 | 行长度由 formatter 处理 |
| F401 | 某些导出需要未使用的导入 |

## 🧪 测试 Lint 检查

### 运行 Ruff

```bash
# 检查所有文件
ruff check .

# 检查特定文件
ruff check entrix/cli.py

# 显示详细信息
ruff check . --verbose

# 自动修复
ruff check . --fix
```

### 运行质量检查

```bash
# 快速检查（包含 Ruff）
entrix run --tier fast

# 完整检查
entrix run

# 只检查 code_quality 维度
entrix run --dimension code_quality
```

## 📊 检查输出示例

```
[RUNNING] ruff_pass [HARD GATE] [fast]
[DONE] ruff_pass: PASS [HARD GATE] [fast] in 0.5s

## CODE_QUALITY (weight: 35%)
   - ruff_pass: ✅ PASS [HARD GATE] [fast]
   - cli_help_smoke: ✅ PASS [HARD GATE] [fast]
✅ Code quality checks passed
```

## 🔍 常见 Ruff 错误

### F541 - f-string without placeholders

**错误**:
```python
print(f"Hello")  # ❌ 没有占位符
```

**修复**:
```python
print("Hello")   # ✅ 静态字符串
```

### F401 - imported but unused

**错误**:
```python
import json  # ❌ 未使用
```

**修复**:
```python
# 删除未使用的导入
```

### E712 - comparison to False/True

**错误**:
```python
assert x == True   # ❌ 不推荐
assert y == False  # ❌ 不推荐
```

**修复**:
```python
assert x           # ✅ 推荐
assert not y       # ✅ 推荐
```

## 🎯 CI/CD 集成

### GitLab CI

在 `.gitlab-ci.yml` 中：

```yaml
lint:
  stage: test
  script:
    - ruff check .
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

### GitHub Actions

在 `.github/workflows/test.yml` 中：

```yaml
- name: Run Ruff
  run: |
    ruff check .
```

## 💡 最佳实践

### 1. 开发时实时检查

```bash
# 安装 Ruff
pip install ruff

# 设置编辑器集成
# VSCode: 安装 Ruff 扩展
# PyCharm: 内置支持
```

### 2. 提交前检查

```bash
# Pre-commit hook
ruff check . --fix
```

### 3. CI 中检查

```bash
# CI 环境中运行
entrix run --tier fast
```

## 📈 质量门禁配置

### 当前配置

| 维度 | 权重 | Ruff 检查 |
|------|------|----------|
| code_quality | 35% | ✅ Hard Gate |
| testability | 40% | - |
| release_readiness | 25% | - |

### 为什么是 Hard Gate？

- **代码质量是基础**：lint 错误表明代码有潜在问题
- **快速失败**：在早期发现问题
- **保持一致性**：所有代码必须符合规范

## 🔧 调整规则

### 添加新规则

```toml
[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "F",     # pyflakes
    "W",     # pycodestyle warnings
    "I",     # isort
    "N",     # pep8-naming
    "UP",    # pyupgrade
]
```

### 忽略特定文件

```toml
[tool.ruff.lint.per-file-ignores]
"tests/*.py" = ["F401"]  # Allow unused imports in tests
"__init__.py" = ["F401"]  # Allow unused imports in __init__.py
```

### 忽略特定错误

```toml
[tool.ruff.lint]
ignore = [
    "E501",  # line too long
    "F401",  # imported but unused
    "F841",  # local variable assigned but never used
]
```

## 📝 相关文档

- [Ruff 官方文档](https://docs.astral.sh/ruff/)
- [Harness 配置](./harness.yaml)
- [质量门禁说明](./docs/mcp-vs-stop-gate.md)

## ✅ 总结

1. **已配置**：项目已经配置了 Ruff Lint 检查
2. **硬门禁**：lint 错误会阻止合并
3. **自动执行**：每次质量检查都会运行
4. **规则完善**：已启用所有重要规则

**质量检查流程**：

```
1. 代码提交
   ↓
2. Ruff Lint (Hard Gate)
   ↓
3. 测试 (pytest)
   ↓
4. 其他检查
   ↓
5. 通过 ✅
```

现在项目的 Lint 检查已经完善！
