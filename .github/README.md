# GitHub Actions CI/CD

这个目录包含 Entrix 的 CI/CD 配置。

## 📁 文件说明

- `build.yml` - 自动构建跨平台可执行文件
- `test.yml` - 自动运行测试
- `README.md` - 使用说明

## 🔄 工作流程

### Push 到 main 分支
```
代码推送 → 运行测试 → 验证通过
```

### 创建 Release
```
创建 Release → 构建可执行文件 → 上传到 Release → 发布
```

### 手动触发
```
GitHub Actions 页面 → 选择 workflow → Run workflow
```

## 📦 构建产物

每个平台会生成独立的可执行文件：

| 平台 | 文件名 | 格式 |
|------|--------|------|
| Windows | entrix-windows-amd64.zip | ZIP |
| Linux | entrix-linux-amd64.tar.gz | TAR.GZ |
| macOS | entrix-macos-amd64.tar.gz | TAR.GZ |

## 🎯 自动化优势

- ✅ 跨平台自动构建
- ✅ 无需本地编译环境
- ✅ 版本化管理
- ✅ 自动发布
- ✅ CI/CD 集成
