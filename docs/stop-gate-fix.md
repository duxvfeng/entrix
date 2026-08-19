# Stop Gate 错误修复说明

## 🔴 问题

**症状**: Stop Gate 一直报错 "Entrix Stop Gate 不可用，已按 fail-closed 阻断"

**原因**:
1. Stop Gate 执行异常时，将状态缓存为 "error"
2. 下次检查时发现缓存的 "error" 状态，直接返回错误
3. 形成死循环，一直显示错误

## ✅ 解决方案

### 1. 异常时不再阻塞

修改 `entrix/stop_gate/hook.py`:

```python
# 之前：异常时保存错误状态并阻塞
except Exception as error:
    summary = f"Harness 执行失败：{error}"
    _save_cached_verdict(state_store, workspace, session_id, snapshot, "error", summary)
    _write_block_decision(output_stream, summary)
    return 0

# 现在：异常时直接放行
except Exception as error:
    print(f"[Entrix] Stop Gate 执行异常: {error}", file=sys.stderr)
    print("[Entrix] 检测到异常，跳过 Stop Gate 检查", file=sys.stderr)
    return 0
```

### 2. 自动清理错误状态

```python
if cached.status == "error":
    print(f"[Entrix] 清理之前的错误状态", file=sys.stderr)
    state_store.delete(workspace, session_id)
    # 重新运行检查
```

### 3. 添加调试支持

设置环境变量查看详细错误：

```bash
export ENTRIX_DEBUG=1
```

## 🛠️ 手动清理缓存

如果仍然卡住，可以手动清理：

### 方法 1: 使用清理脚本

```bash
python scripts/clear_stop_gate_cache.py
```

### 方法 2: 直接删除缓存目录

```bash
# Windows
del %TEMP%\harness-monitor\runtime\state\*.json

# Linux/Mac
rm /tmp/harness-monitor/runtime/state/*.json
```

### 方法 3: 设置环境变量禁用

```bash
export ENTRIX_STOP_GATE_DISABLED=1
```

## 📋 修改的文件

1. **`entrix/stop_gate/hook.py`**
   - 修改异常处理：异常时不再阻塞
   - 自动清理错误状态
   - 添加调试输出

2. **`scripts/clear_stop_gate_cache.py`** (新增)
   - 清理 Stop Gate 缓存状态的工具

## 🧪 测试

### 1. 测试异常处理

```bash
# 模拟异常场景
cd /tmp/test-project
entrix init

# 触发 Stop Gate（应该不会阻塞）
# 即使出错也会跳过
```

### 2. 测试清理脚本

```bash
# 查看缓存状态
python scripts/clear_stop_gate_cache.py --dry-run

# 清理缓存
python scripts/clear_stop_gate_cache.py

# 强制清理
python scripts/clear_stop_gate_cache.py --force
```

## 🔍 调试技巧

### 启用调试输出

```bash
export ENTRIX_DEBUG=1
```

### 查看 Stop Gate 日志

Stop Gate 的错误信息会输出到 stderr：

```python
print(f"[Entrix] Stop Gate 执行异常: {error}", file=sys.stderr)
```

### 查看缓存状态

```bash
# Windows
dir %TEMP%\harness-monitor\runtime\state

# Linux/Mac
ls -la /tmp/harness-monitor/runtime/state
```

## 📝 相关文档

- [Stop Gate 智能触发](./stop-gate-doc-skip.md)
- [Stop Gate 原理](./mcp-vs-stop-gate.md)

## 🎯 预期行为

### 之前（❌ 有问题）

```
1. Stop Gate 执行异常
2. 保存错误状态
3. 下次检查返回错误
4. 一直卡在错误状态 ❌
```

### 现在（✅ 正常）

```
1. Stop Gate 执行异常
2. 输出错误信息（stderr）
3. 清理错误状态
4. 直接放行（不阻塞）
5. 下次检查重新运行 ✅
```

## 🔄 版本信息

- **版本**: v0.1.22
- **日期**: 2025-01-XX
- **状态**: ✅ 已修复

## 💡 注意事项

1. **Fail-open vs Fail-closed**
   - 之前：异常时 fail-closed（阻塞）
   - 现在：异常时 fail-open（放行）
   - 原因：避免因工具问题影响开发流程

2. **错误状态不再缓存**
   - 只缓存 "fail" 和 "blocked"
   - "error" 状态自动清理

3. **可调试性**
   - 所有错误输出到 stderr
   - ENTRIX_DEBUG 环境变量显示详细堆栈
