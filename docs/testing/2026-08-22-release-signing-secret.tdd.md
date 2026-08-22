# Release 签名 Secret 修复 TDD 证据

## 问题

GitHub Actions 的 `build.yml` 在生成签名 manifest 前检测到
`RELEASE_SIGNING_KEY` 为空并退出。`publish.yml` 已使用 `PUBLISH` 环境，但
`build.yml` 的 release job 没有声明该环境，因此配置在 `PUBLISH` 环境中的
`ENTRIX_RELEASE_SIGNING_KEY` 无法被读取。

## RED -> GREEN

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| RED | `pytest tests/test_ci_configuration.py::test_signed_release_reads_key_from_protected_publish_environment -q` | 失败，`build.yml` 的 release job 缺少 `environment` 字段。 |
| GREEN | `pytest tests/test_ci_configuration.py -q` | `12 passed`。 |
| GREEN | `ruff check .` | `All checks passed!` |

## 修改保证

- `build.yml` 的签名 release job 使用受保护的 `PUBLISH` 环境。
- 缺少 Secret 时，错误信息明确指出应在 `Settings > Environments > PUBLISH > Environment secrets`
  配置 `ENTRIX_RELEASE_SIGNING_KEY`。
- 私钥仍只通过 GitHub Secret 注入 runner 临时目录，不写入仓库。
- 文档已统一说明 Secret 的环境位置，并要求它与
  `security/release-public-key.pem` 匹配。

## 外部配置前置条件

代码不能替用户创建 GitHub Secret。若当前私钥与仓库公钥匹配，可执行：

```bash
gh secret set ENTRIX_RELEASE_SIGNING_KEY --env PUBLISH < /path/to/entrix-release-signing.key
```

如果私钥丢失，需要生成新的 RSA 密钥对、提交对应的
`security/release-public-key.pem`，再将私钥写入该环境 Secret；不要把私钥提交到仓库。
