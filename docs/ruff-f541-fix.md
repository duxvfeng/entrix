# Ruff F541 和 F401 错误修复

## 🔴 错误

GitLab CI 报告 Ruff 错误：

- **F541**: f-string without any placeholders (没有占位符的 f-string)
- **F401**: imported but unused (导入但未使用)

## ✅ 修复

### F541 错误（12 个）

**问题**: 使用 `f""` 格式化字符串，但没有占位符

**之前（❌ 错误）**:
```python
print(f"✅ MCP 服务可用")
print(f"\n📝 下一步:")
print(f"   1. 重启 Claude Code 以加载 MCP 配置")
print(f"[Entrix] 清理之前的错误状态", file=sys.stderr)
```

**现在（✅ 正确）**:
```python
print("✅ MCP 服务可用")
print("\n📝 下一步:")
print("   1. 重启 Claude Code 以加载 MCP 配置")
print("[Entrix] 清理之前的错误状态", file=sys.stderr)
```

### F401 错误（2 个）

**问题**: 导入了模块但未使用

**之前（❌ 错误）**:
```python
import json  # 未使用
import sys   # 未使用
```

**现在（✅ 正确）**:
```python
import subprocess
from pathlib import Path
```

## 📋 修改的文件

1. **`entrix/cli.py`**
   - 修复 10 个 F541 错误
   - 移除不必要的 `f` 前缀

2. **`entrix/stop_gate/hook.py`**
   - 修复 1 个 F541 错误
   - 移除不必要的 `f` 前缀

3. **`tests/test_stop_gate_fix.py`**
   - 修复 2 个 F401 错误
   - 移除未使用的导入

4. **`scripts/clear_stop_gate_cache.py`**
   - 修复 1 个 F541 错误
   - 移除不必要的 `f` 前缀

## 🧪 测试

```bash
# 运行测试
pytest tests/test_doc_skip.py -v
pytest tests/test_stop_gate_fix.py -v

# 结果：所有测试通过 ✅
```

## 📖 Python 最佳实践

### F541: 避免 f-string 滥用

**规则**: 只在需要字符串插值时使用 f-string

```python
# ✅ 推荐：静态字符串用普通字符串
name = "Alice"
print("Hello")              # 静态字符串
print(f"Hello, {name}")     # 需要插值

# ❌ 不推荐：没有占位符的 f-string
print(f"Hello")             # 浪费，不需要 f
```

**原因**:
1. 性能：f-string 比普通字符串慢
2. 清晰：不需要时不要用
3. 规范：符合 PEP 8 风格

### F401: 避免未使用的导入

**规则**: 删除未使用的导入

```python
# ✅ 推荐：只导入需要的
import os
from pathlib import Path

# ❌ 不推荐：导入但不使用
import json    # 未使用
import sys     # 未使用
```

**原因**:
1. 命名空间污染
2. 潜在的循环导入
3. 代码清晰度

## 📊 修复统计

| 错误类型 | 数量 | 文件 |
|---------|------|------|
| F541 | 10 | entrix/cli.py |
| F541 | 1 | entrix/stop_gate/hook.py |
| F541 | 1 | scripts/clear_stop_gate_cache.py |
| F401 | 2 | tests/test_stop_gate_fix.py |
| **总计** | **14** | **4 个文件** |

## 🎯 Ruff 自动修复

Ruff 可以自动修复这些错误：

```bash
# 自动修复所有可修复的错误
ruff check . --fix

# 只修复特定错误
ruff check . --fix --select F541,F401
```

## ✅ 验证

```bash
# 检查是否还有错误
ruff check .

# 应该没有 F541 和 F401 错误 ✅
```

## 💡 注意事项

### f-string 性能

```python
import timeit

# 普通字符串（更快）
timeit.timeit('print("Hello")', number=1000000)

# f-string（更慢）
timeit.timeit('print(f"Hello")', number=1000000)
```

### 何时使用 f-string

```python
# ✅ 使用 f-string
name = "Alice"
print(f"Hello, {name}")  # 需要

# ❌ 不要用 f-string
print(f"Hello")           # 不需要
```

## 🔄 相关规则

- **F541**: f-string without any placeholders
- **F401**: imported but unused
- **F501**: line too long (行太长)
- **F504**: line contains trailing semicolon (行尾有分号)

## 📝 总结

- ✅ 修复了 14 个 Ruff 错误
- ✅ 符合 Python 最佳实践
- ✅ 提升代码质量和性能
- ✅ 所有测试通过

现在代码完全符合 Ruff 的 linting 规则！
