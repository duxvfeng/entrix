# 更新日志

本文件记录 Entrix 用户可感知的变更。版本号遵循语义化版本;每个版本的完整变更见对应的 [GitHub Release](https://github.com/duxvfeng/entrix/releases) 页面。

## [未发布]

### 清理与工程化

- 版本库清理:移除误提交的 Stop Gate 运行时状态文件,删除无引用的死代码(JSON reporter、structure queries、stop_gate model、CLI 运行时 shim);`entrix run` 不再以 stub 快照重复写 fitness artifact(`#2b09c60`)
- CI:全部 workflow 增加 concurrency 组,skill-regression 补充只读权限,测试矩阵新增 macOS,新增 Dependabot 配置
- mypy 类型检查覆盖扩展到整个 `entrix` 包与 `scripts`,并取消 `follow_imports = "skip"`
- 为核心结构分析器(`entrix/structure/builtin.py`)补充单元测试

## [0.1.25] - 2026-08-27

### 新增

- 插件新增六个斜杠命令
- Stop Gate 支持会话感知生命周期;放行 `stop_hook_active` 重试,避免无限阻断
- 发布签名密钥改从 `PUBLISH` 受保护环境读取,tag 与 pyproject/plugin/marketplace 版本一致性强校验

### 修复

- 启动器:Windows 缓存文件替换、单次尝试下残留缓存锁回收,修复残留缓存锁导致的 Stop Hook 超时
- Stop Gate 语义、命令执行统一与发布链路收敛(三批质量与架构修复)

### 文档

- 补充会话门禁设计文档与实施计划;完善 README

## [0.1.24] - 2026-08-20

### 新增

- 插件 Skill 默认要求使用简体中文回复(用户明确要求英文时除外)
- 插件固定使用与版本匹配的二进制,不再混用最新源码与旧版本二进制

## [0.1.23] - 2026-08-20

### 修复

- 插件启动器修正 Windows x64 架构识别

## [0.1.22] - 2026-08-20

### 修复

- 修复 Marketplace 插件安装与市场插件停止钩子的路径解析

### 新增

- 新增 GitHub 和 Gitee 发布推送任务

## [0.1.21] - 2026-08-20

### 修复

- 修复手动触发 workflow 无法创建 release 的问题
- 修复插件 Hook 路径问题和安装指南

### 新增

- 添加 `/entrix` 命令概览自动显示

## 更早的版本

0.1.x 早期版本(0.1.5–0.1.18)发布于 [PyPI](https://pypi.org/project/entrix/) 与 GitHub Release,未维护结构化变更日志。
