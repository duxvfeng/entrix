# Ruff Lint 错误修复

## 🔴 错误

GitLab CI 报告 Ruff E712 错误：

```
E712 Avoid equality comparisons to `False`; use `not has_code_change(changed):` for false checks
E712 Avoid equality comparisons to `True`; use `has_code_change(changed):` for truth checks
```

## ✅ 修复

### 之前（❌ 错误）

```python
assert has_code_change(changed) == False
assert has_code_change(changed) == True
```

### 现在（✅ 正确）

```python
assert not has_code_change(changed)
assert has_code_change(changed)
```

## 📋 修改的测试用例

| 测试用例 | 之前 | 现在 |
|---------|------|------|
| test_only_documentation | `assert has_code_change(changed) == False` | `assert not has_code_change(changed)` |
| test_only_readme | `assert has_code_change(changed) == False` | `assert not has_code_change(changed)` |
| test_code_change | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_config_change | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_test_change | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_no_change | `assert has_code_change(changed) == False` | `assert not has_code_change(changed)` |
| test_mixed_doc_only | `assert has_code_change(changed) == False` | `assert not has_code_change(changed)` |
| test_markdown_in_docs | `assert has_code_change(changed) == False` | `assert not has_code_change(changed)` |
| test_python_change | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_github_workflow | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_yaml_change | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |
| test_shell_script | `assert has_code_change(changed) == True` | `assert has_code_change(changed)` |

## 🧪 测试结果

```bash
pytest tests/test_doc_skip.py -v

# 结果：12 passed ✅
```

## 📖 Python PEP 8 规范

根据 [PEP 8](https://peps.python.org/pep-0008/#programming-recommendations)：

> Don't compare boolean values to True or False using `==`.
>
> ```python
> # 正确
> if greeting:
>     pass
>
> # 错误
> if greeting == True:
>     pass
>
> # 正确
> if not greeting:
>     pass
>
> # 错误
> if greeting == False:
>     pass
> ```

## 💡 最佳实践

### 布尔值检查

```python
# ✅ 推荐
if has_code_change(files):
    pass

if not has_code_change(files):
    pass

# ❌ 不推荐
if has_code_change(files) == True:
    pass

if has_code_change(files) == False:
    pass
```

### 断言布尔值

```python
# ✅ 推荐
assert has_code_change(files)
assert not has_code_change(files)

# ❌ 不推荐
assert has_code_change(files) == True
assert has_code_change(files) == False
```

## 🎯 Ruff E712 规则

**规则**: `E712 Avoid equality comparisons to `False`; use `not has_code_change(changed):` for false checks`

**原因**:
1. 更符合 Python 风格
2. 代码更简洁
3. 避免潜在的类型错误

## 📊 对比

### 之前

```python
# 12 个 E712 错误
assert has_code_change(changed) == False  # ❌
assert has_code_change(changed) == True   # ❌
```

### 现在

```python
# 0 个 E712 错误
assert not has_code_change(changed)  # ✅
assert has_code_change(changed)      # ✅
```

## 🔍 相关规则

- **E711**: 不要使用 `==` 或 `!=` 与 `None` 比较（应该用 `is` 或 `is not`）
- **E712**: 不要使用 `==` 或 `!=` 与 `True`/`False` 比较（直接用或 `not`）

## ✅ 总结

- ✅ 修复了 12 个 Ruff E712 错误
- ✅ 符合 PEP 8 规范
- ✅ 代码更简洁清晰
- ✅ 所有测试通过

现在代码完全符合 Ruff 的 linting 规则！
