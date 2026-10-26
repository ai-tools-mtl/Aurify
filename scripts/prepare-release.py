"""Stage release helpers, fetch two npm archives, and create a versioned ZIP."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
dist.mkdir(exist_ok=True)
# uv build adds this local build-directory marker; it is not a release asset.
(dist / '.gitignore').unlink(missing_ok=True)
version = json.loads((root / 'packages/bundle-patent/package.json').read_text())['version']
for name in ('install-patent-profile.ps1', 'persona.patch.yml'):
    shutil.copy2(root / 'scripts' / name, dist / name)
for name in ('README.md', 'INSTALL-NEW-PROFILE.md'):
    guide = (root / 'docs/install' / name).read_text()
    guide = guide.replace('../../scripts/persona.patch.yml', 'persona.patch.yml')
    guide = guide.replace('../../scripts/', 'https://github.com/ai-tools-mtl/Aurify/tree/main/scripts/')
    guide = guide.replace('../DEVELOPMENT.md', 'https://github.com/ai-tools-mtl/Aurify/blob/main/docs/DEVELOPMENT.md')
    guide = guide.replace('../RELEASING.md', 'https://github.com/ai-tools-mtl/Aurify/blob/main/docs/RELEASING.md')
    guide = guide.replace('-File scripts/install-patent-profile.ps1', '-File install-patent-profile.ps1')
    (dist / name).write_text(guide)
for spec in ('@deepseek-ai/schemastery@3.18.2', '@deepseek-ai/cosmokit@1.8.3'):
    subprocess.run(['npm', 'pack', spec, '--registry=https://registry.npmjs.org',
                    '--pack-destination', str(dist), '--ignore-scripts', '--quiet'], check=True)
# Only current source versions belong in the release. Verification rejects stale archives.
archive = dist / f'aurify-{version}.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(dist.iterdir()):
        if p.is_file() and p.name != 'SHA256SUMS' and p.suffix != '.zip':
            z.write(p, p.name)
print(archive.name)
