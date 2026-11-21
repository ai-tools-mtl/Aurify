"""把发版版本号同步到四个版本落点并校验一致性。

用法：python scripts/bump-version.py 0.2.1

落点：packages/bundle-patent、tool-patent、command-patent-review 三个 package.json
的 "version"，以及 python/patent-services/pyproject.toml 的 version = "..."。
脚本只改版本号；CHANGELOG 与发布说明仍按 docs/RELEASING.md 手工维护。

提交并合并进 main 后，release 工作流读到新版本号即自动发布（docs/RELEASING.md
「自动化发布」节）。版本已在远端存在时合并不会发布——先换一个新版本号。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_VERSIONS = [
    ROOT / 'packages/bundle-patent/package.json',
    ROOT / 'packages/tool-patent/package.json',
    ROOT / 'packages/command-patent-review/package.json',
]
PYPROJECT = ROOT / 'python/patent-services/pyproject.toml'
UVLOCK = ROOT / 'python/patent-services/uv.lock'
_SEMVER = re.compile(r'^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$')


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    version = sys.argv[1]
    if not _SEMVER.match(version):
        print(f'版本号不符合 semver：{version!r}（示例：0.2.1、0.3.0-rc.1）')
        return 2

    for path in PACKAGE_VERSIONS:
        text = path.read_text(encoding='utf-8')
        # 只替换首个 "version" 键行——避免整体重写 JSON 引入无关格式差异
        new_text, count = re.subn(r'(?m)^(\s*"version"\s*:\s*)"[^"]+"', rf'\1"{version}"', text, count=1)
        if count != 1:
            print(f'未在 {path.relative_to(ROOT)} 找到 "version" 键行')
            return 1
        json.loads(new_text)  # 改完必须仍是合法 JSON
        path.write_text(new_text, encoding='utf-8')
        old = json.loads(text).get('version')
        print(f'{path.relative_to(ROOT)}: {old} -> {version}')

    text = PYPROJECT.read_text(encoding='utf-8')
    new_text, count = re.subn(r'(?m)^(version\s*=\s*)"[^"]+"', rf'\1"{version}"', text, count=1)
    if count != 1:
        print(f'未在 {PYPROJECT.relative_to(ROOT)} 找到 version = "..." 行')
        return 1
    PYPROJECT.write_text(new_text, encoding='utf-8')
    print(f'{PYPROJECT.relative_to(ROOT)}: version -> {version}')

    # uv.lock 的根包版本必须随 pyproject 一起推进：CI 的 `uv run --locked`
    # 会校验锁与 pyproject 一致（含项目自身版本），不同步则发版工作流测试步失败。
    lock = UVLOCK.read_text(encoding='utf-8')
    new_lock, lock_count = re.subn(
        r'(\[\[\s*package\s*\]\]\s*\nname\s*=\s*"deepseek-harness-patent-services"\s*\nversion\s*=\s*)"[^"]+"',
        rf'\g<1>"{version}"', lock, count=1)
    if lock_count != 1:
        print(f'未在 {UVLOCK.relative_to(ROOT)} 找到根包版本行')
        return 1
    UVLOCK.write_text(new_lock, encoding='utf-8', newline='')
    print(f'{UVLOCK.relative_to(ROOT)}: 根包 version -> {version}')

    print('\n后续步骤：更新 CHANGELOG.md 未发布节 -> 提交 -> 合并进 main（release 工作流自动发布）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
