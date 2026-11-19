// Run without the host monorepo:
// node --test packages/tool-patent/tests/threshold-sync.standalone.test.mjs
// The review-score constants live in two places that must not drift apart:
// the authoritative copy in tool-patent/src/loop.ts and the client mirror in
// bundle-patent/src/client/project-model.ts (a cross-package import would pull
// server-side host packages into the client bundle, so the mirror stays — this
// guard turns silent drift into a caught failure instead).
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const read = (p) => readFile(resolve(repoRoot, p), 'utf8')
const constant = (source, name) => {
  const match = source.match(new RegExp(`(?:const|readonly)\\s+${name}\\s*=\\s*(\\d+)`))
  assert.ok(match, `${name} not found as a numeric const`)
  return Number(match[1])
}

test('review threshold mirror stays in sync with loop.ts', async () => {
  const loop = await read('packages/tool-patent/src/loop.ts')
  const client = await read('packages/bundle-patent/src/client/project-model.ts')
  assert.equal(
    constant(loop, 'DEFAULT_REVIEW_THRESHOLD'),
    constant(client, 'DEFAULT_THRESHOLD'),
    'DEFAULT_REVIEW_THRESHOLD (loop.ts) drifted from DEFAULT_THRESHOLD (project-model.ts) — update both or lower the mirror',
  )
})

test('degraded-review delta mirror stays in sync with loop.ts', async () => {
  const loop = await read('packages/tool-patent/src/loop.ts')
  const client = await read('packages/bundle-patent/src/client/project-model.ts')
  assert.equal(
    constant(loop, 'DEGRADED_REVIEW_DELTA'),
    constant(client, 'DEGRADED_DELTA'),
    'DEGRADED_REVIEW_DELTA (loop.ts) drifted from DEGRADED_DELTA (project-model.ts) — update both or lower the mirror',
  )
})
