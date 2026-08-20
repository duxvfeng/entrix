# GitHub/Gitee 推送任务实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用
> `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 逐任务实现此计划。

**目标：** 恢复一个精简的 `.vscode/tasks.json`，支持当前分支和当前已有 tag 推送到
GitHub、Gitee 或两个 remote，并让 release workflow 不创建新 tag。

**架构：** VS Code task 只负责选择 remote 和编排单 remote 任务；Python 辅助脚本负责
跨平台读取 `HEAD` 可追溯到的最近已有 tag 并执行精确 tag push。GitHub Actions 只接受 release 事件
、已有 tag ref 或手动构建，softprops 使用解析出的当前已有 tag 并覆盖同名 Release 附件。

**技术栈：** VS Code Tasks JSON、Python 标准库 `argparse`/`subprocess`、GitHub Actions YAML、pytest。

---

### 任务 1：锁定当前 tag 推送行为

**文件：**
- 创建：`scripts/push_current_tag.py`
- 测试：`tests/test_push_current_tag.py`

- [x] **步骤 1：编写失败测试**

覆盖以下行为：找到最近可追溯 tag 时调用 `git push <remote> refs/tags/<tag>:refs/tags/<tag>`；
无可追溯 tag 时返回非零并说明原因；非法 remote 参数被拒绝。

- [x] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/test_push_current_tag.py -q`

预期：因 `scripts.push_current_tag` 尚不存在而失败。

- [x] **步骤 3：实现最少脚本**

脚本使用 `git describe --tags --abbrev=0 HEAD` 获取最近可追溯 tag；使用
`subprocess.run` 执行精确 tag refspec，不执行 `git tag` 或创建 tag。

- [x] **步骤 4：运行测试确认通过**

运行：`python -m pytest tests/test_push_current_tag.py -q`

预期：全部通过。

### 任务 2：恢复精简 VS Code 推送任务

**文件：**
- 创建：`.vscode/tasks.json`
- 测试：`tests/test_task_configuration.py`

- [x] **步骤 1：编写失败测试**

断言只存在 7 个任务：GitHub/Gitee/双 remote 的只推送代码和只推送当前 tag 任务，以及
双 remote 的代码 + tag 顺序任务；不保留 `origin`、所有分支、并行重复任务。

- [x] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/test_task_configuration.py -q`

预期：因任务文件已删除而失败。

- [x] **步骤 3：实现任务配置**

不带 tag 任务执行 `git push github HEAD` 或 `git push dxf HEAD`；带 tag 任务调用
`python scripts/push_current_tag.py --remote <remote>`；双 remote 任务通过
`dependsOrder: sequence` 编排对应单 remote 任务；新增代码 + tag 任务按顺序依赖两个双
remote 任务，先推送代码，再推送 tag。

- [x] **步骤 4：运行测试确认通过**

运行：`python -m pytest tests/test_task_configuration.py -q`

预期：全部通过。

### 任务 3：禁止 workflow 创建新 tag

**文件：**
- 修改：`.github/workflows/build.yml`
- 修改：`tests/test_ci_configuration.py`

- [x] **步骤 1：补充失败断言**

断言 workflow_dispatch 的 release job 运行，tag 解析使用当前提交可追溯的已有 tag，
上传动作开启同名附件覆盖，不从 package version 创建新 tag。

- [x] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/test_ci_configuration.py -q`

预期：当前 workflow_dispatch 分支会跳过 release job，且上传动作不会覆盖同名附件，断言失败。

- [x] **步骤 3：修改 workflow**

release job 条件加入 `workflow_dispatch`；release job 使用 `fetch-depth: 0` 和
`git describe --tags --abbrev=0 HEAD` 解析已有 tag；softprops 设置
`overwrite_files: true`，不添加任何创建或移动 tag 的步骤。

- [x] **步骤 4：运行验证**

运行：`python -m pytest tests/test_ci_configuration.py -q`
以及 `python -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml', encoding='utf-8'))"`

预期：测试通过且 YAML 可解析。

### 任务 4：完整验证

- [x] **步骤 1：运行相关测试**

运行：`python -m pytest tests/test_push_current_tag.py tests/test_task_configuration.py tests/test_ci_configuration.py -q`

- [x] **步骤 2：运行静态检查和 diff 检查**

运行：`python -m ruff check scripts/push_current_tag.py tests/test_push_current_tag.py tests/test_task_configuration.py tests/test_ci_configuration.py`；
`git diff --check`。
