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

## 自动化发布（release 工作流）

`.github/workflows/release.yml` 让「合并进 main」成为发布动作：工作流读 `packages/bundle-patent/package.json` 的版本号，远端不存在 `v<版本>` 标签时自动执行 Python 测试 → 构建校验 → 推标签 → npm 三包（预发布版本走对应 dist-tag）→ PyPI（wheel + sdist）→ GitHub Release（`dist/` 全量附件，`--generate-notes`）→ 双 Docker 镜像（`dsh-patent` / `dsh-patent-experiment`，打 `v<版本>` 与 `latest`）。纯文档或无版本推进的合并不发布；`workflow_dispatch` 可手动补发（各渠道幂等：已占用的版本号自动跳过，不会覆盖）。

标准发版路径因此收敛为：

```sh
python scripts/bump-version.py 0.2.1   # 同步三个 package.json 与 pyproject.toml
# 更新 CHANGELOG.md 未发布节；提交；合并进 main —— 余下由 release 工作流完成
```

**首次启用前需在 GitHub 仓库 Settings → Secrets and variables → Actions 配置**：

| Secret | 用途 | 缺失时的行为 |
|---|---|---|
| `NPM_TOKEN` | 发布 `@mtl-academic` 三包（automation token） | 跳过 npm 渠道并在总结中登记 |
| `PYPI_API_TOKEN` | 发布 `deepseek-harness-patent-services` | 跳过 PyPI 渠道并在总结中登记 |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | 推送两个 Docker 镜像 | 跳过 Docker 渠道并在总结中登记 |

PyPI 也可改用 Trusted Publishing（在 PyPI 项目页配置 GitHub OIDC 发布方后删除 token 步骤中的 token 依赖）；插件市场同步仍为手动步骤，不在工作流范围内。

## 分发渠道

`release` 工作流已覆盖 npm、PyPI、GitHub Release 与双 Docker 镜像；插件市场更新仍需手动执行。手动补发（如工作流密钥缺失期间）时各渠道单独发布，核对版本是否已占用、凭据与 npm dist-tag；不要把 Release 完成写成所有渠道已同步。

ZIP 提供本地包安装材料，不是全依赖离线镜像。断网机器还需预备宿主、npm/Python 传递依赖和 Docker 镜像。解包的 `bundle/` 被档案以绝对路径引用，安装后需保留。

版本专用的旧流程见[归档](archive/README.md)。
