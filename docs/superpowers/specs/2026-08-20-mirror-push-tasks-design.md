# GitHub/Gitee 推送任务设计

## 目标

为仓库提供一组精简的 VS Code 任务，支持将当前分支或当前已有 tag 推送到 GitHub、
Gitee，且可以分别或一次性推送到两个 remote。发布 workflow 只使用触发时已有的
tag，不创建新 tag。

## 方案

- `.vscode/tasks.json` 提供 7 个任务：GitHub/Gitee/双 remote 的只推送代码任务，
  GitHub/Gitee/双 remote 的只推送当前 tag 任务，以及一个按顺序推送代码和 tag 的双 remote 任务。
- 不带 tag 的任务执行 `git push <remote> HEAD`，只推送当前分支提交。
- 带 tag 的任务调用 `scripts/push_current_tag.py`。脚本使用
  `git describe --tags --abbrev=0 HEAD` 读取 `HEAD` 可追溯到的最近已有 tag；没有可追溯
  的 tag 时失败；它只推送已有 tag，不执行 `git tag`。
- 双 remote 任务通过 `dependsOn` 顺序复用对应的单 remote 任务，避免复制推送逻辑。
- “一键推送代码 + 当前 tag 到 GitHub + Gitee”先依赖双 remote 代码任务，再依赖双 remote tag
  任务，确保代码先于 tag 推送。
- `.github/workflows/build.yml` 的 release job 支持 release 事件、tag push 和手动运行。
  手动运行时使用当前提交可追溯的最近已有 `v*` tag 更新 Release，并覆盖同名附件；
  不创建或移动 tag。

## 错误处理

- 未配置 `github` 或 `dxf` remote 时由 Git 返回错误。
- 当前 `HEAD` 没有可追溯的已有 tag 时，tag 推送任务在本地失败并显示原因，不产生远端变更。
- 手动构建时当前提交没有可追溯的已有 `v*` tag，release job 明确失败，不创建新 tag。
- 任一 remote 推送失败时，双 remote 任务按顺序停止，不掩盖失败。

## 验证

- 单元测试覆盖最近可追溯 tag、无可追溯 tag 失败路径，以及实际推送命令参数。
- JSON/YAML 解析检查验证任务和 workflow 配置结构。
- Ruff 与相关 pytest 测试必须通过。
