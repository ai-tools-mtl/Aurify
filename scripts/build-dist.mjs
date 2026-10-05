// Standalone distribution build. dsh runtime packages remain external.
import { build } from 'esbuild';
import { mkdtemp, mkdir, readFile, writeFile, cp, rm, readdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'dist');
const work = await mkdtemp(join(tmpdir(), 'aurify-build-'));
const packages = ['tool-patent', 'command-patent-review', 'bundle-patent'];
try {
  for (const dir of packages) {
    const src = join(root, 'packages', dir);
    const manifest = JSON.parse(await readFile(join(src, 'package.json'), 'utf8'));
    const stem = manifest.name.replace('@', '').replace('/', '-');
    const seeds = (await readdir(dist)).filter(n => n.startsWith(stem + '-') && n.endsWith('.tgz')).sort();
    if (!seeds.length) throw new Error(`Missing published dependency metadata for ${manifest.name}`);
    const published = JSON.parse(execFileSync('tar', ['-xOf', join(dist, seeds.at(-1)), 'package/package.json'], { encoding: 'utf8' }));
    for (const group of ['dependencies', 'peerDependencies', 'devDependencies']) {
      for (const [name, spec] of Object.entries(manifest[group] ?? {})) {
        if (!spec.startsWith('workspace:')) continue;
        const replacement = name.startsWith('@mtl-academic/') ? manifest.version : published[group]?.[name];
        if (!replacement || replacement.startsWith('workspace:')) throw new Error(`Unresolved ${name}`);
        manifest[group][name] = replacement;
      }
    }
    const stage = join(work, dir, 'package');
    await mkdir(join(stage, 'lib'), { recursive: true });
    const entries = { index: join(src, 'src/index.ts'), invariant: join(src, 'src/invariant.ts') };
    if (dir === 'tool-patent') entries.fingerprint = join(src, 'src/fingerprint.ts');
    await build({ entryPoints: entries, outdir: join(stage, 'lib'), bundle: true, packages: 'external',
      platform: 'node', format: 'esm', target: 'node20', tsconfigRaw: {}, logLevel: 'warning' });
    if (dir === 'bundle-patent') {
      const client = await build({ entryPoints: [join(src, 'src/client/index.ts')], outfile: join(stage, 'lib/client.js'),
        bundle: true, packages: 'external', platform: 'browser', format: 'cjs', target: 'es2022', jsx: 'automatic',
        loader: { '.css': 'local-css' }, tsconfigRaw: {}, write: false, logLevel: 'warning' });
      const js = client.outputFiles.find(f => f.path.endsWith('.js')).text;
      const css = client.outputFiles.find(f => f.path.endsWith('.css'))?.text ?? '';
      await writeFile(join(stage, 'lib/client.js'), `window.__ModuleLoader__.load({id:${JSON.stringify(manifest.name)},factory:(require)=>{\nvar module={exports:{}};var exports=module.exports;\nif(typeof document!=='undefined'&&!document.querySelector('style[data-plugin-css=\"@mtl-academic/dsh-patent/client\"]')){const style=document.createElement('style');style.dataset.plugin='@mtl-academic/dsh-patent';style.dataset.pluginCss='@mtl-academic/dsh-patent/client';style.textContent=${JSON.stringify(css)};document.head.appendChild(style);}\n${js}\nreturn module.exports;\n}});\n`);
    }
    // Emit declarations without resolving the absent monorepo. This is not a type check.
    const config = join(work, `${dir}.tsconfig.json`);
    await writeFile(config, JSON.stringify({ compilerOptions: { target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler',
      declaration: true, emitDeclarationOnly: true, noCheck: true, allowImportingTsExtensions: true, jsx: 'react-jsx',
      rootDir: join(src, 'src'), outDir: join(stage, 'lib/types') }, include: [join(src, 'src/**/*')] }));
    execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'), '-p', config], { stdio: 'inherit' });
    for (const asset of ['README.md', 'README.zh.md', ...(dir === 'bundle-patent' ? ['skills', 'cordis.patch.yml'] : []), ...(dir === 'command-patent-review' ? ['rubric'] : [])]) {
      await cp(join(src, asset), join(stage, asset), { recursive: true });
    }
    await writeFile(join(stage, 'package.json'), JSON.stringify(manifest, null, 2) + '\n');
    const filename = `${stem}-${manifest.version}.tgz`;
    execFileSync('tar', ['-czf', join(dist, filename), '-C', dirname(stage), 'package'], { env: { ...process.env, COPYFILE_DISABLE: '1' } });
    console.log(filename);
  }
} finally { await rm(work, { recursive: true, force: true }); }
