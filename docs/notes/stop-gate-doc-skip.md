# Stop Gate 智能跳过 - 只有代码变更才触发

## 🎯 功能说明

Stop Gate 现在采用**智能触发策略**：**只有代码变更才触发质量检查**，文档性/思路性工作自动跳过。

## 📋 触发条件

### ✅ 会触发检查的场景（有代码变更）

1. **修改源代码**
   - `src/`, `lib/`, `app/`, `packages/`, `entrix/` 目录
   - `*.py`, `*.js`, `*.ts`, `*.tsx`, `*.java`, `*.go`, `*.rs`, `*.cpp`, `*.c` 等

2. **修改配置文件**
   - `pyproject.toml`, `package.json`, `Cargo.toml`
   - `go.mod`, `pom.xml`, `build.gradle`
   - `harness.yaml`, `.github/`, `Makefile`
   - `Dockerfile`, `.dockerignore`

3. **修改测试文件**
   - `tests/`, `test/`, `__tests__` 目录
   - 文件名包含 `.test.`

4. **修改脚本**
   - `*.sh`, `*.yml`, `*.yaml`

### ❌ 不会触发检查的场景（无代码变更）

1. **只修改文档**
   - `docs/`, `doc/` 目录
   - `README.md`, `CHANGELOG.md`
   - `*.md`, `*.rst`, `*.txt`, `*.adoc`

2. **没有任何变更**

## ✨ 使用场景

### 场景 1：编写文档（不触发）

```bash
# 用户：帮我写一个 API 使用文档
# Claude：[编写 docs/api-guide.md]
# 用户：好的，结束
# Stop Gate：未检测到代码变更 -> 跳过检查 ✅
```

### 场景 2：实现功能（触发）

```bash
# 用户：帮我实现一个新功能
# Claude：[修改 src/main.py，更新 docs/api.md]
# Stop Gate：检测到代码变更 -> 执行检查 ❌
```

### 场景 3：架构讨论（不触发）

```bash
# 用户：帮我分析这个架构设计
# Claude：[创建 docs/architecture-analysis.md]
# Stop Gate：未检测到代码变更 -> 跳过检查 ✅
```

### 场景 4：修改配置（触发）

```bash
# 用户：帮我添加一个新的 GitHub Action
# Claude：[修改 .github/workflows/test.yml]
# Stop Gate：检测到代码变更 -> 执行检查 ❌
```

## 🔍 工作原理

Stop Gate Hook 在执行检查前，先分析变更文件：

```python
# 伪代码
changed_files = get_git_changes()
if has_code_change(changed_files):
    run_harness_checks()
else:
    print("未检测到代码变更，跳过检查")
    return 0  # 直接放行
```

### 检测逻辑

```python
def has_code_change(changed_files: list[str]) -> bool:
    """判断是否有代码变更"""
    # 检查是否有源代码
    if any(path.startswith("src/") or path.endswith(".py") for path in changed_files):
        return True

    # 检查是否有配置文件
    if any("pyproject.toml" in path or ".github" in path for path in changed_files):
        return True

    # 检查是否有测试文件
    if any("tests/" in path for path in changed_files):
        return True

    # 没有代码变更
    return False
```

## 🧪 测试

运行测试验证功能：

```bash
pytest tests/test_doc_skip.py -v
```

测试覆盖 12 个场景：
- ✅ 只修改文档
- ✅ 只修改 README
- ✅ 修改源代码
- ✅ 修改配置文件
- ✅ 修改测试文件
- ✅ 没有变更
- ✅ 混合文档类型
- ✅ docs 下的 markdown
- ✅ Python 文件变更
- ✅ GitHub Actions 变更
- ✅ YAML 文件变更
- ✅ Shell 脚本变更

## 🎯 与现有跳过机制的关系

### 现有跳过机制（保留）

1. **Planning 阶段跳过**
   ```python
   if phase == "planning":
       return 0
   ```

2. **Init 阶段跳过**
   ```python
   if consume_phase(workspace, "init"):
       return 0
   ```

3. **环境变量禁用**
   ```bash
   ENTRIX_STOP_GATE_DISABLED=1
   ```

4. **没有 harness.yaml**
   - 未配置的仓库自动跳过

### 新增跳过机制

**智能代码变更检测** - 基于文件类型的智能判断

### 优先级

```
1. ENTRIX_STOP_GATE_DISABLED          （最高优先级，全局禁用）
2. 没有 harness.yaml                   （未配置，不检查）
3. Planning / Init 阶段               （特定阶段，不检查）
4. 没有代码变更                       （新增，智能跳过）⭐
5. 有代码变更                         （执行检查）
```

## 💡 设计理念

### 问题
- Claude Code 每次结束对话都会调用 Stop Gate
- 文档性、思路性的对话也触发检查
- 用户被打扰，体验不佳

### 解决方案
- **只有代码变更才触发检查**
- 简化逻辑：检查"是否有代码"，而不是"是否只有文档"
- 保持质量门禁的有效性

### 原则
1. **不打扰**：文档工作不应该被代码质量检查打扰
2. **不降级**：代码变更必须严格检查
3. **简单清晰**：逻辑易理解，行为可预测

## 📊 对比

### 旧逻辑（文档跳过）

```python
if is_documentation_or_thinking_work(changed_files):
    # 只有文档且没有代码 -> 跳过
    return 0
```

**问题**：需要同时检查"有文档"和"没代码"，逻辑复杂

### 新逻辑（代码触发）

```python
if not has_code_change(changed_files):
    # 没有代码 -> 跳过
    return 0
```

**优势**：只需检查"有代码"，逻辑简单清晰

## 🚀 实现细节

### 集成位置

文件：`entrix/stop_gate/hook.py`

在 `run_stop_gate_hook()` 函数中：

```python
if consume_phase(workspace, "init") or phase == "planning":
    return 0

detected_changed_files = derive_changed_files(workspace)
changed_files = detected_changed_files or []
detection_failed = detected_changed_files is None

# 🎯 新增：只有代码变更才触发
if not detection_failed and not has_code_change(changed_files):
    print("[Entrix] 未检测到代码变更，跳过 Stop Gate 检查", file=sys.stderr)
    return 0

should_collect = phase == "implementation" or bool(changed_files) or detection_failed
```

## 📚 相关文档

- [Stop Gate 原理](./mcp-vs-stop-gate.md)
- [GitHub Actions 配置](./github-actions-guide.md)
- [MCP 服务说明](../README.md#mcp-服务)

## 🔄 版本历史

- **v0.1.22** - 新增智能触发：只有代码变更才触发检查
- **v0.1.21** - Stop Gate 基础功能
