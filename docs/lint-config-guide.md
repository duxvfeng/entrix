# 可配置的 Lint 系统使用指南

## 概述

Entrix 现在支持通过 YAML 配置文件来自定义不同编程语言的 lint 检查项，而不是硬编码在代码中。这让你可以根据项目需求灵活配置代码质量工具。

## 配置文件位置

系统会按以下优先级查找配置文件：

1. `.claude/lint-config.yaml` (项目级别，最高优先级)
2. `lint-config.yaml` (项目根目录)
3. `skills/entrix/lint-config.yaml` (默认配置)

## 配置文件结构

```yaml
version: "1.0"

languages:
  python:
    code_quality:
      - name: ruff_lint
        command: ruff check . 2>&1
        description: Ruff linting must pass with no errors
        tier: fast
        enabled: true
        required: false

      - name: mypy_check
        command: mypy . 2>&1
        description: Type checking with mypy
        tier: normal
        enabled: false
        required: false

    testability:
      - name: pytest_pass
        command: python -m pytest 2>&1
        description: The Python test suite must pass
        tier: normal
        enabled: true
        required: true

    release_readiness:
      - name: package_build_pass
        command: python -m build --no-isolation 2>&1
        description: The Python package must build
        tier: normal
        enabled: true
        required: false

dimension_weights:
  code_quality: 40
  testability: 35
  release_readiness: 25

defaults:
  enable_first_lint_only: true  # 只启用每个维度的第一个工具
  require_all_enabled: false    # 是否要求所有启用的检查项都必须通过
```

## 配置字段说明

### 工具级别字段

- `name`: 检查项的唯一标识符
- `command`: 执行检查的命令
- `description`: 检查项的描述
- `tier`: 执行级别 (`fast`, `normal`, `deep`)
- `enabled`: 是否启用该检查项
- `required`: 是否为必需项（必需项失败会阻止提交）

### 维度权重字段

- `code_quality`: 代码质量维度的权重
- `testability`: 测试性维度的权重
- `release_readiness`: 发布准备性维度的权重

权重总和必须为 100。

### 默认策略字段

- `enable_first_lint_only`: 只启用每个维度的第一个工具（推荐用于快速开始）
- `require_all_enabled`: 是否要求所有启用的检查项都必须通过

## 支持的编程语言

当前支持以下编程语言的 lint 配置：

- `python` - Python 项目
- `node-typescript` - Node.js/TypeScript 项目
- `java-maven` - Java Maven 项目
- `java-gradle` - Java Gradle 项目
- `go` - Go 项目
- `rust` - Rust 项目

## 使用方法

### 1. 使用默认配置

直接使用项目提供的默认配置：

```bash
entrix init --repo . --profile auto
```

### 2. 自定义配置

创建项目级别的配置文件：

```bash
# 复制默认配置
cp skills/entrix/lint-config.yaml .claude/lint-config.yaml

# 编辑配置文件
vim .claude/lint-config.yaml
```

### 3. 选择性启用工具

修改配置文件中的 `enabled` 字段：

```yaml
# 只启用 ruff 和 mypy
python:
  code_quality:
    - name: ruff_lint
      enabled: true
    - name: mypy_check
      enabled: true
    - name: black_format_check
      enabled: false  # 禁用
```

### 4. 交互式选择

使用 skill 交互式选择要启用的工具：

```bash
# 通过 entrix skill 交互式选择
/entrix init
```

## 示例配置

### Python 项目（严格模式）

```yaml
languages:
  python:
    code_quality:
      - name: ruff_lint
        enabled: true
        required: true

      - name: mypy_check
        enabled: true
        required: true

      - name: black_format_check
        enabled: true
        required: false
```

### Vue 项目（宽松模式）

```yaml
languages:
  node-typescript:
    code_quality:
      - name: eslint_lint
        enabled: true
        required: false

      - name: vue_lint
        enabled: true
        required: false

      - name: prettier_check
        enabled: false
```

## 与传统硬编码的区别

### 优势

1. **灵活性**: 可以根据项目需求自定义工具
2. **可维护性**: 配置文件易于理解和修改
3. **团队协作**: 可以共享统一的 lint 配置
4. **渐进式采用**: 可以逐步启用更多检查项

### 向后兼容

如果没有找到配置文件，系统会回退到传统的硬编码配置，确保现有项目继续正常工作。

## 故障排除

### 配置文件未生效

1. 检查配置文件路径是否正确
2. 确认 YAML 语法是否正确
3. 查看日志中的错误信息

### 权重总和不正确

确保三个维度的权重总和为 100：

```yaml
dimension_weights:
  code_quality: 40
  testability: 35
  release_readiness: 25
  # 总和: 40 + 35 + 25 = 100 ✓
```

### 工具未找到

确保工具命令在项目环境中可用：

```bash
# 测试工具是否可用
which ruff
which mypy
which black
```

## 进阶配置

### 自定义工具

可以添加任何自定义的 lint 工具：

```yaml
python:
  code_quality:
    - name: custom_security_check
      command: ./scripts/security-check.sh 2>&1
      description: Custom security analysis
      tier: normal
      enabled: true
      required: true
```

### 条件执行

某些工具可以设置为仅在特定条件下执行：

```yaml
# 与现有 harness.yaml 的 execution_scope 配合
- name: expensive_analysis
  command: sonar-scanner 2>&1
  execution_scope: ci  # 仅在 CI 环境中执行
  enabled: true
```

## 配置模板

完整的配置模板请参考 `skills/entrix/lint-config.yaml` 文件。

## 相关文件

- `entrix/harness/lint_config.py` - 配置读取和处理逻辑
- `entrix/harness/template.py` - 模板生成和配置应用
- `skills/entrix/lint-config.yaml` - 默认配置文件

## 总结

这个可配置的 lint 系统让你能够：

1. 根据项目需求选择合适的代码质量工具
2. 灵活控制检查的严格程度
3. 逐步采用更严格的代码质量标准
4. 在团队间共享统一的配置

通过配置文件而不是硬编码，Entrix 现在更加灵活和易于维护。