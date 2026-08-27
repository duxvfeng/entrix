# Worktree 隔离工作规范

## 核心原则

**所有写操作必须在隔离的 worktree 中进行，严禁直接在受保护分支（`main`、`master`、`develop`）上修改文件。**

**隔离区只能创建在项目根目录 `.claude/worktrees/<分支或任务名>/` 下。禁止在项目外部目录创建 worktree，也禁止使用临时目录、用户目录或其他仓库目录作为隔离区。**

---

## 适用场景

以下操作**必须**使用 worktree 隔离：

✅ **写操作（必须隔离）**：
- 生成/修改代码文件
- 创建/更新文档
- 修改配置文件
- 批量文件操作
- 数据库迁移脚本
- 构建脚本修改

❌ **读操作（无需隔离）**：
- 查看文件内容
- 搜索代码
- 分析项目结构
- 读取配置

---

## 工作流程

### 1. 启动写操作前

```bash
# 检查当前状态
git status

# 如果在受保护分支且有未提交的更改，询问用户
```

**Claude 应执行**：
1. 检测是否在 `main`、`master` 或 `develop` 分支
2. 检测是否有未跟踪的新文件或未提交的更改
3. **询问用户**：`是否创建 worktree 隔离环境？(推荐)`

### 2. 创建 Worktree

```bash
# 创建命名的 worktree
EnterWorktree("name", "<功能名称>")

# 示例
EnterWorktree("name", "init-docs")        # 文档初始化
EnterWorktree("name", "add-user-api")     # 添加用户API
EnterWorktree("name", "fix-auth-bug")     # 修复认证问题
```

若原生 `EnterWorktree` 工具不可用，回退命令也只能使用项目内路径：

```bash
git worktree add .claude/worktrees/<name> -b <branch>
```

创建前必须确认 `.claude/worktrees/` 已被 Git 忽略；未忽略时先补充忽略规则并提交，禁止改用项目外目录绕过。

### 3. 在 Worktree 中工作

worktree 必须创建在 `.claude/worktrees/<name>/`，包含：
- 独立的 Git 工作副本
- 独立的分支（基于 origin/main 或当前 HEAD）
- 隔离的文件系统修改

### 4. 完成后处理

根据用户需求提供选项：

#### 选项 A：保留（keep）
```bash
ExitWorktree("action": "keep")
```
- 保留 worktree 和分支
- 适合持续开发的功能
- 可随时返回继续工作

#### 选项 B：清理（remove）
```bash
ExitWorktree("action": "remove", "discard_changes": false)
```
- **仅当变更已提交时使用**
- 删除 worktree 目录
- 保留分支（已安全提交）

#### 选项 C：强制清理（有风险）
```bash
ExitWorktree("action": "remove", "discard_changes": true)
```
- ⚠️ **会丢失未提交的更改**
- 需要用户明确确认
- 适用于实验性工作

---

## 检测规则

Claude 在执行**任何写操作前**必须检查：

```javascript
// 伪代码
function shouldUseWorktree() {
  const branch = getCurrentGitBranch();
  const hasWriteOperation = true;
  
  if (branch === 'main' || branch === 'master' || branch === 'develop') {
    if (hasWriteOperation) {
      return 'MUST_CREATE_WORKTREE';
    }
  }
  
  return 'SAFE_TO_PROCEED';
}
```

---

## 常见场景示例

### 场景 1：生成文档

❌ **错误**：
```
直接在受保护分支生成 CLAUDE.md
```

✅ **正确**：
```
1. 检测到在 `main`、`master` 或 `develop` 分支
2. 询问：是否创建 worktree？
3. EnterWorktree("name", "init-docs")
4. 生成文档
5. 询问：保留还是清理？
```

### 场景 2：修复 Bug

❌ **错误**：
```
直接在受保护分支修改代码文件
```

✅ **正确**：
```
1. EnterWorktree("name", "fix-auth-bug")
2. 修改代码
3. 运行测试
4. ExitWorktree("action": "keep")
// 用户后续可提交 PR
```

### 场景 3：添加新功能

❌ **错误**：
```
在受保护分支创建多个新文件
```

✅ **正确**：
```
1. EnterWorktree("name", "add-payment-module")
2. 创建文件和代码
3. 运行质量检查
4. ExitWorktree("action": "keep")
```

---

## 例外情况

**以下情况无需 worktree**：

1. **只读分析**：查看文件、搜索代码、理解架构
2. **临时文件**：在 `.claude/` 或 `target/` 等临时目录的文件
3. **用户明确豁免**：用户明确说"直接修改，不需要隔离"

---

## 用户提示模板

当检测到需要 worktree 时，Claude 应提示：

```
⚠️ 检测到写操作

当前分支：`main`、`master` 或 `develop`
操作类型：[具体操作，如"生成文档"]

💡 推荐做法：创建 worktree 隔离环境

选项：
1. 创建 worktree（推荐）
2. 直接在当前分支修改（不推荐）
3. 取消操作

请选择：[1/2/3]
```

---

## 记忆点

- ✅ **写操作 = worktree**
- ✅ **受保护分支（main/master/develop）= 只读**
- ✅ **完成后 = 询问 keep/remove**
- ❌ **永远不要直接污染 main/master/develop 分支**

---

**此规则自 2026-08-21 起生效，基于最佳实践经验制定。**
