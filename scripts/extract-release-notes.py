"""从 CHANGELOG.md 提取指定版本的发布说明。

用法：python scripts/extract-release-notes.py 0.3.0

打印 `## <version> …` 节标题之后的全部正文（直到下一个 `## ` 标题或文末）。
release 工作流用它生成 GitHub Release 的 notes；CHANGELOG 无该版本节时
以非零退出，调用方自行回退（如生成占位说明）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / 'CHANGELOG.md'


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    version = sys.argv[1]
    lines = CHANGELOG.read_text(encoding='utf-8').splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith('## ') and line[3:].strip().startswith(version):
            start = index + 1
            break
    if start is None:
        print(f'CHANGELOG.md 无 {version} 的节', file=sys.stderr)
        return 1
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith('## '):
            break
        body.append(line)
    text = '\n'.join(body).strip()
    if not text:
        print(f'{version} 的节为空', file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
