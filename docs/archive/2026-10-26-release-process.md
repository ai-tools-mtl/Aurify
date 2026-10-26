> 历史快照：2026-10-26 整理文档前的版本专用发布说明。文中版本、命令和“本次”描述只代表当时的计划，不证明发布已执行。当前操作请使用[发布流程](../RELEASING.md)。

# 发布流程

Git 仓库保存源码和手写资产，生成的 npm tarball、Python wheel/sdist、ZIP 与 `SHA256SUMS` 统一作为 GitHub Release 附件。旧提交内的安装包不会通过本次整理重写历史。

## 版本规则

本版 tag 为 `v0.1.6-alpha.7`，三个 npm 包版本为 `0.1.6-alpha.7`，Python 服务版本为 `0.1.2`。alpha tag 使用 GitHub prerelease。下一次代码发布应同步三个 npm 包的版本，并按 Python 变更决定是否递增服务版本；已发布的 tag 和资产不覆盖重发。

## 验证与准备

1. 确认工作区、远程仓库和目标分支，更新版本与 `CHANGELOG.md`。
2. 按[开发指南](../DEVELOPMENT.md)从空 `dist/` 构建、打包并验证校验和。
3. 运行 Python 测试。记录 TypeScript 完整类型检查、宿主集成、Windows 安装与 Docker 操作中哪些实际执行过。
4. 提交源码和文档。`git ls-files dist` 应无输出；`dist/` 里的发布文件只作为附件上传。

## 创建 tag 和 Release

以下命令发布到 `ai-tools-mtl/Aurify`；执行前确认本次版本和目标提交：

```sh
git tag -a v0.1.6-alpha.7 -m 'Aurify v0.1.6-alpha.7'
git push origin main
git push origin v0.1.6-alpha.7
gh release create v0.1.6-alpha.7 dist/* \
  --repo ai-tools-mtl/Aurify --verify-tag --prerelease \
  --title 'Aurify v0.1.6-alpha.7' --notes-file /path/to/release-notes.md
```

`dist/*` 应只包含本次生成的附件；请先检查清单。发布后核对 tag 指向提交、附件名称和下载后的 SHA-256。CI 在 main push/PR 中构建验证，并上传短期构建附件；GitHub Release 是明确发布的长期下载入口。

## registry 与安装通道

GitHub Release 不会执行 `npm publish` 或 PyPI 上传，也不会自动更新桌面插件市场。它们是独立发布动作；发布 registry 前核对版本是否已占用、凭据和 prerelease dist-tag。本次流程不隐含这些通道的发布。

Release ZIP 提供本地包安装材料，不是全依赖离线镜像。完全断网运行还需提前准备 dsh 宿主、其 npm 传递依赖、Python 依赖和所需 Docker 镜像。解包出的 `bundle/` 被档案以绝对路径引用，安装后不能随意移动或删除。
