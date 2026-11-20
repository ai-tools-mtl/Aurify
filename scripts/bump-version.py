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

    print('\n后续步骤：更新 CHANGELOG.md 未发布节 -> 提交 -> 合并进 main（release 工作流自动发布）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
