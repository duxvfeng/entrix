# 发布清单（Release Checklist）

本文档描述从版本号变更到双远程（GitHub + Gitee）发布完成的完整时序。
核心约束：**Gitee marketplace 从 main 分支安装插件，插件钉住固定版本的二进制；
二进制资产托管在 GitHub Release。顺序错了，marketplace 用户会下载到不存在的资产（404）。**

## 版本号出现的位置

版本号 `X.Y.Z` 同步出现在 5 处，由脚本统一修改：

| 文件 | 出现次数 | 内容 |
|------|---------|------|
| `pyproject.toml` | 1 | `project.version` |
| `.claude-plugin/plugin.json` | 3 | `version` + 2 × `ENTRIX_BINARY_VERSION` |
| `.claude-plugin/marketplace.json` | 2 | `version` + `asset_prefix` |
| `tests/test_plugin_binary_contract.py` | 1 | 硬编码版本断言 |

`tests/test_plugin_versions_match_package_version` 在每次 CI 全量测试中校验以上一致性；
`build.yml` 在发布时再次校验 tag 与各文件版本一致。

## 发布步骤

### 1. 提升版本号

```bash
python scripts/bump_version.py X.Y.Z
```

脚本先校验全部 5 处的出现次数，再原子写入；任何一处计数不符会整体中止，不会留下半改状态。

### 2. 本地验证（与 CI 一致）

```bash
ruff check .
pytest
mypy
python -m entrix validate
```

### 3. 提交并推送 GitHub（二进制宿主，先行）

```bash
git commit -am "chore: release vX.Y.Z"
git push github main
```

### 4. 打 tag 并推送 GitHub，触发构建

```bash
git tag vX.Y.Z
git push github refs/tags/vX.Y.Z:refs/tags/vX.Y.Z
# 或：python scripts/push_current_tag.py --remote github
```

`build.yml` 随即自动执行：

1. 五平台单文件二进制（windows/linux-amd64/linux-arm64/macos-amd64/macos-arm64），每个跑 `--help` 冒烟
2. 生成 `.sha256` sidecar、`.sha256.sig`、`release-manifest.json` 和 `release-manifest.json.sig`
3. 使用仓库 Secret `ENTRIX_RELEASE_SIGNING_KEY` 签名；私钥只写入 runner 临时目录
4. 创建 GitHub Release 并上传全部资产（允许覆盖，CI 使用 `overwrite_files: true`）

### 5. 等待 Release 资产就绪

在 GitHub Releases 页面确认以下资产齐全后再继续：

```
entrix-X.Y.Z-{windows-amd64.exe,linux-amd64,linux-arm64,macos-amd64,macos-arm64}
entrix-X.Y.Z-*.sha256（5 个）
entrix-X.Y.Z-*.sha256.sig（5 个）
release-manifest.json
release-manifest.json.sig
```

### 6. 发布 PyPI（publish.yml）

publish.yml 由 `release: published` 事件触发（若 Release 处于草稿态，先正式发布）：

- 构建 sdist/wheel 并发布到 PyPI
- 将 Python 包附加到 Release 资产

注意：publish job 声明了 `environment: PUBLISH`，若该 environment 配置了审批人，需要人工批准。

### 7. 推送 Gitee（marketplace 源，最后）

**必须在前两步完成后执行**——这一步之后，marketplace 安装的用户就会开始拉取新版本二进制：

```bash
git push dxf main
python scripts/push_current_tag.py --remote dxf
```

### 8. 发布后验证

- [ ] Release 页面：5 个二进制 + 5 个 sha256 + 5 个 checksum 签名 + manifest 及其签名 + sdist/wheel
- [ ] PyPI 页面出现 `X.Y.Z`
- [ ] 干净机器上 `/plugin marketplace add https://gitee.com/duxvfeng/entrix.git && /plugin install entrix@entrix`，重启后 MCP 工具可调用
- [ ] `entrix --help` 经插件二进制正常输出

## 故障恢复

- **构建失败**：修复后可直接重推 tag（`git push github -f refs/tags/vX.Y.Z`）或在 Actions 页面 `workflow_dispatch` 重跑 `build.yml`（要求 tag 可从 HEAD 到达）
- **PyPI 发布失败**：Actions 页面 `workflow_dispatch` 重跑 `publish.yml`
- **版本校验失败**（tag 与文件版本不一致）：本地重跑步骤 1 修正，重新提交打 tag
- **签名校验失败**：确认 `ENTRIX_RELEASE_SIGNING_KEY` 与仓库内 `security/release-public-key.pem` 匹配，并确认所有签名资产来自同一次构建；不要只覆盖二进制而保留旧 checksum 或 manifest

### 公钥轮换

1. 生成新的 RSA 私钥，并将公钥更新到 `security/release-public-key.pem`
2. 更新 GitHub Secret `ENTRIX_RELEASE_SIGNING_KEY`
3. 用新 key 重新生成并验证一整个版本的五平台资产
4. 保留旧版本 Release 资产，直到旧插件版本不再需要旧公钥
