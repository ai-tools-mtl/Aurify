"""Verify distribution metadata, entrypoints, skills, rubric and Python assets."""
import hashlib
import json
import re
import sys
from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
for directory in ('bundle-patent', 'tool-patent', 'command-patent-review'):
    source = json.loads((root / 'packages' / directory / 'package.json').read_text())
    stem = source['name'].replace('@', '').replace('/', '-')
    archive = dist / f"{stem}-{source['version']}.tgz"
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
        assert not any(part.startswith('._') for name in names for part in name.split('/'))
        manifest = json.load(tar.extractfile('package/package.json'))
        assert manifest['version'] == source['version']
        for group in ('dependencies', 'peerDependencies', 'devDependencies'):
            assert not any(v.startswith('workspace:') for v in manifest.get(group, {}).values())
        for key, value in manifest['exports'].items():
            if '*' in key:
                continue
            for target in (value.values() if isinstance(value, dict) else [value]):
                assert 'package/' + target.removeprefix('./') in names, target
        if directory == 'bundle-patent':
            assert sum(n.endswith('/SKILL.md') for n in names) == 14
            client = tar.extractfile('package/lib/client.js').read().decode()
            # The monorepo tsdown build keeps spaces ("textContent = css"); the
            # standalone scripts/build-dist.mjs minifies them away — accept both.
            assert 'window.__ModuleLoader__.load' in client and 'textContent' in client
            assert 'createElement("style")' in client or 'createElement(\'' + 'style' + '\')' in client
            assert 'node:fs' not in client
        if directory == 'command-patent-review':
            rubric = json.load(tar.extractfile('package/rubric/default.json'))
            assert len(rubric['dimensions']) == 7
    print('Verified', archive.name)
version = re.search(r'^version = "([^"]+)"', (root / 'python/patent-services/pyproject.toml').read_text(), re.MULTILINE).group(1)
wheel = next(dist.glob(f'deepseek_harness_patent_services-{version}-*.whl'))
with zipfile.ZipFile(wheel) as z:
    assert 'patent_services/assets/disclosure-template.docx' in z.namelist()
    assert 'set -e;' in z.read('patent_services/experiments.py').decode()
    assert f'Version: {version}'.encode() in z.read(f'deepseek_harness_patent_services-{version}.dist-info/METADATA')
print('Verified', wheel.name)
# Require the sdist, helper files, and dependency archives used by the installer.
expected = {f"deepseek_harness_patent_services-{version}.tar.gz",
            'deepseek-ai-schemastery-3.18.2.tgz', 'deepseek-ai-cosmokit-1.8.3.tgz',
            'install-patent-profile.ps1', 'persona.patch.yml', 'README.md', 'INSTALL-NEW-PROFILE.md'}
for directory in ('bundle-patent', 'tool-patent', 'command-patent-review'):
    m = json.loads((root / 'packages' / directory / 'package.json').read_text())
    expected.add(f"{m['name'].replace('@', '').replace('/', '-')}-{m['version']}.tgz")
bundle_version = json.loads((root / 'packages/bundle-patent/package.json').read_text())['version']
zipname = f'aurify-{bundle_version}.zip'
expected.add(wheel.name)
for name in expected:
    assert (dist / name).is_file() and (dist / name).stat().st_size, name
with zipfile.ZipFile(dist / zipname) as z:
    assert set(z.namelist()) == expected, 'ZIP file list differs'
    for name in expected:
        assert z.read(name) == (dist / name).read_bytes(), name
expected.add(zipname)
assert {p.name for p in dist.iterdir() if p.name != 'SHA256SUMS'} == expected, 'Unexpected/stale release files'
artifacts = [dist / name for name in sorted(expected)]
checksums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in artifacts)
if '--write-checksums' in sys.argv:
    (dist / 'SHA256SUMS').write_text(checksums)
else:
    assert (dist / 'SHA256SUMS').read_text() == checksums, 'Distribution checksums differ'
print('SHA-256 checksums verified')
