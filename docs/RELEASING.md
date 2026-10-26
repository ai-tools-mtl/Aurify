# 发布流程

Git 保存源码、模板、技能和手写文档。npm tarball、Python wheel/sdist、安装器、ZIP 和校验文件生成到 Git 忽略的 `dist/`，作为 GitHub Release 附件分发。

## 准备版本

1. 确认目标分支、远程和提交，检查工作区差异。
2. 同步三个 npm 包版本；按 Python 变更决定服务版本，更新 [CHANGELOG](../CHANGELOG.md)。宿主依赖映射维护在 `scripts/workspace-versions.json`。
3. 按[开发指南](DEVELOPMENT.md)在空 `dist/` 中构建并校验，运行 Python 测试。
4. 记录实际执行的验证范围，区分独立构建、完整 TS 类型检查、宿主 UI、Windows 安装和 Docker 实测。
5. 提交源码与文档。`git ls-files dist` 应无输出；不要覆盖已发布的 tag 或同版本资产。

## 创建 tag 和 Release

以下为仓库根目录下的 POSIX shell 示例。先准备本版发布说明，将 `RELEASE_NOTES` 改为其路径；执行前核对 `VERSION`、目标提交和 `dist/` 清单：

```sh
VERSION=$(node -p "JSON.parse(require('fs').readFileSync('packages/bundle-patent/package.json', 'utf8')).version")
TAG="v$VERSION"
RELEASE_NOTES=/absolute/path/to/release-notes.md

git tag -a "$TAG" -m "Aurify $TAG"
git push origin HEAD
git push origin "$TAG"
gh release create "$TAG" dist/* \
  --repo ai-tools-mtl/Aurify --verify-tag --prerelease \
  --title "Aurify $TAG" --notes-file "$RELEASE_NOTES"
```

alpha/beta/rc 使用 `--prerelease`；稳定版本移除此参数。推送前确认 `HEAD` 位于本次目标分支。发布后核对 tag 指向、附件清单和下载后的 SHA-256。CI 在 main push/PR 中构建并上传短期附件，Release 是长期下载入口。

## 分发渠道

GitHub Release 不会执行 `npm publish`、PyPI 上传或插件市场更新。各渠道需单独发布，核对版本是否已占用、凭据与 npm dist-tag；不要把 Release 完成写成所有渠道已同步。

ZIP 提供本地包安装材料，不是全依赖离线镜像。断网机器还需预备宿主、npm/Python 传递依赖和 Docker 镜像。解包的 `bundle/` 被档案以绝对路径引用，安装后需保留。

版本专用的旧流程见[归档](archive/README.md)。
